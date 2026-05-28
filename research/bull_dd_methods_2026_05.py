"""
BULL-ext: compare three DD circuit methodologies on the live engine.

  M1. No DD circuit (baseline)
  M2. Sleeve-equity DD (current cpm_live impl via vol_cap.compute_dd_circuit_scale)
      Measures DD from rolling 63d peak of (1 + sleeve_returns).cumprod().
      When sleeve is in cash, equity is flat, so peak resets after re-entry.
  M3. Raw SPY-price DD (critic's reproduction methodology)
      Measures DD from rolling 63d peak of SPY's adjusted close.
      Trips only when SPY's actual price drops from its 63d high.
"""
import sys, socket
socket.setdefaulttimeout(15)
sys.path.insert(0, "/Users/rkautsar/personal/scripts/strategy_cpm")

import pandas as pd
import numpy as np
from cpm_live import load_panel, perf_metrics
from bull_qqq_live import run_bull_qqq_backtest
from vol_cap import compute_dd_circuit_scale, DD_CIRCUIT_THRESHOLD, DD_CIRCUIT_SCALE


def raw_asset_dd_circuit(sleeve_returns, sleeve_state_indicator, asset_price,
                          sig_dates, threshold=-0.10, lookback=63):
    """Raw asset-DD circuit: scale BULL sleeve to safe when SPY's own DD < threshold.
    sleeve_state_indicator: True when sleeve holds SPY, False when in safe.
    """
    common = sleeve_returns.index
    spy = asset_price.reindex(common).ffill()
    spy_peak = spy.rolling(lookback, min_periods=1).max()
    spy_dd = spy / spy_peak - 1.0
    scale = pd.Series(1.0, index=common)
    sig_set = set(sig_dates)
    current = 1.0
    for i, day in enumerate(common):
        if day in sig_set:
            current = 1.0
        elif sleeve_state_indicator.iloc[i] and pd.notna(spy_dd.iloc[i]) and spy_dd.iloc[i] < threshold:
            current = 0.0
    # Above only sets transitions, need to forward-fill
    state = 1.0
    out = pd.Series(1.0, index=common)
    for i, day in enumerate(common):
        if day in sig_set:
            state = 1.0
        elif sleeve_state_indicator.iloc[i] and pd.notna(spy_dd.iloc[i]) and spy_dd.iloc[i] < threshold:
            state = 0.0
        out.iloc[i] = state
    return out


def determine_sleeve_state(panel, start, end):
    """Heuristic: BULL holds SPY when (HYG OR TIP) AND SPY mom > 0. Use the
    monthly signal output and forward-fill across the month."""
    from cpm_live import sig_13612U, best_safe
    sigs = (pd.DataFrame({"x": 1}, index=panel.loc[start:end].index)
            .groupby(pd.Grouper(freq="ME")).tail(1).index)
    sigs = sigs[(sigs >= start) & (sigs <= end)]
    state_per_sig = {}
    for sd in sigs:
        monthly = panel.loc[:sd].resample("ME").last()
        hygm = sig_13612U(monthly["HYG_stitched"]) if "HYG_stitched" in monthly.columns else -999.0
        tipm = sig_13612U(monthly["TIP"]) if "TIP" in monthly.columns else -999.0
        c_ok = (pd.notna(hygm) and hygm > 0) or (pd.notna(tipm) and tipm > 0)
        spym = sig_13612U(monthly["SPY"])
        a_ok = pd.notna(spym) and spym > 0
        state_per_sig[sd] = c_ok and a_ok
    # Build daily series: state on day t = state set at most recent sig < t
    daily_idx = panel.loc[start:end].index
    out = pd.Series(False, index=daily_idx)
    sig_list = sorted(state_per_sig.keys())
    cur = False
    for i, d in enumerate(daily_idx):
        for sd in sig_list:
            if sd < d:
                cur = state_per_sig[sd]
        out.iloc[i] = cur
    return out


if __name__ == "__main__":
    panel = load_panel(start=pd.Timestamp("1993-01-01"))
    start = pd.Timestamp("2008-04-30")
    end = pd.Timestamp("2026-05-22")
    bull_raw = run_bull_qqq_backtest(panel, start, end)
    sigs = (pd.DataFrame({"x": 1}, index=bull_raw.index)
            .groupby(pd.Grouper(freq="ME")).tail(1).index.tolist())

    m1 = bull_raw
    m2_scale = compute_dd_circuit_scale(bull_raw, sigs, DD_CIRCUIT_THRESHOLD, DD_CIRCUIT_SCALE)
    m2 = m2_scale * bull_raw

    # M3 raw SPY-price DD
    spy_price = panel["SPY"].ffill()
    bull_in_spy = determine_sleeve_state(panel, start, end)
    bull_in_spy = bull_in_spy.reindex(bull_raw.index).fillna(False)
    m3_scale = raw_asset_dd_circuit(bull_raw, bull_in_spy, spy_price, sigs,
                                       threshold=DD_CIRCUIT_THRESHOLD, lookback=63)
    m3 = m3_scale * bull_raw

    n_trips_m2 = int((m2_scale.diff() < 0).sum())
    n_trips_m3 = int((m3_scale.diff() < 0).sum())

    rows = [
        ("M1. No DD circuit (baseline)", m1, 0),
        ("M2. Sleeve-equity DD (live impl, vol_cap.py)", m2, n_trips_m2),
        ("M3. Raw SPY-price DD (critic's methodology)", m3, n_trips_m3),
    ]

    print("\n" + "=" * 100)
    print("BULL-ext DD circuit methodology comparison (2008-04 to 2026-05, 10bps)")
    print("=" * 100)
    print(f"{'Variant':<55} {'Sharpe':>8} {'CAGR':>8} {'Vol':>8} {'MaxDD':>9} {'Trips':>6}")
    print("-" * 100)
    for label, p, trips in rows:
        m = perf_metrics(p)
        print(f"{label:<55} {m['sharpe']:>8.3f} {m['cagr']*100:>7.2f}% {m['vol']*100:>7.2f}% "
              f"{m['max_drawdown']*100:>8.2f}% {trips:>6d}")
    print("=" * 100)
    print(f"Critic's M3 reproduction: Sharpe 0.99, CAGR 11.82%, MaxDD -15.61%, 7 trips")
