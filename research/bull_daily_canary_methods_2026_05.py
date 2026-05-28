"""
BULL-ext intramonth defense: DD-10% circuits vs daily 13612W canary.

Variants (all on the live BULL engine, monthly signal = HYG OR TIP canary +
SPY mom_13612U > 0):
  M1. No intramonth defense (baseline)
  M2. Sleeve-equity DD-10% / 63d (current cpm_live impl via vol_cap.py)
  M3. Raw SPY-price DD-10% / 63d (critic's methodology)
  M4. Daily 13612W on SPY < 0 (proposed new fast canary)
  M5. Daily 13612U on SPY < 0 (for comparison; slower than M4)
  M4b. Daily 13612W + DD-10% combined (both must clear)

All daily checks use latching: tripped flag persists until next monthly signal
date (no intramonth re-entry, matching DD circuit convention).

Window: 2008-04-30 to 2026-05-22, 10bps.
"""
import sys, socket
socket.setdefaulttimeout(15)
sys.path.insert(0, "/Users/rkautsar/personal/scripts/strategy_cpm")

import pandas as pd
import numpy as np
from cpm_live import load_panel, perf_metrics
from bull_qqq_live import run_bull_qqq_backtest
from vol_cap import compute_dd_circuit_scale, DD_CIRCUIT_THRESHOLD, DD_CIRCUIT_SCALE


def sig_13612U_daily(p):
    """Daily-anchored 13612U using trading-day lookbacks (~21/63/126/252 days
    = approx 1/3/6/12 months). Returns NaN if insufficient history."""
    p = p.dropna()
    n = len(p)
    if n < 253:
        return np.nan
    last = p.iloc[-1]
    r1 = last / p.iloc[-22] - 1
    r3 = last / p.iloc[-64] - 1
    r6 = last / p.iloc[-127] - 1
    r12 = last / p.iloc[-253] - 1
    return (r1 + r3 + r6 + r12) / 4.0


def sig_13612W_daily(p):
    """Daily-anchored 13612W weighted average (Keller BAA: 12/4/2/1)."""
    p = p.dropna()
    n = len(p)
    if n < 253:
        return np.nan
    last = p.iloc[-1]
    r1 = last / p.iloc[-22] - 1
    r3 = last / p.iloc[-64] - 1
    r6 = last / p.iloc[-127] - 1
    r12 = last / p.iloc[-253] - 1
    return (12 * r1 + 4 * r3 + 2 * r6 + 1 * r12) / 19.0


def determine_sleeve_state(panel, start, end):
    """Determine which daily indices have BULL holding SPY (vs safe)."""
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
    daily_idx = panel.loc[start:end].index
    out = pd.Series(False, index=daily_idx)
    cur = False
    sig_list = sorted(state_per_sig.keys())
    for i, d in enumerate(daily_idx):
        for sd in sig_list:
            if sd < d:
                cur = state_per_sig[sd]
        out.iloc[i] = cur
    return out, sigs.tolist()


def daily_signal_circuit(panel, sleeve_state, sigs, signal_fn, label):
    """Latching daily circuit using signal_fn(SPY_window) < 0 as trigger.
    Returns scale series (1.0 normally, 0.0 after trip until next sig date).
    """
    spy_price = panel["SPY"].ffill()
    daily_idx = sleeve_state.index
    scale = pd.Series(1.0, index=daily_idx)
    sig_set = set(sigs)
    state = 1.0
    trips = 0
    for i, d in enumerate(daily_idx):
        if d in sig_set:
            if state == 0.0:
                trips += 0  # was already counted
            state = 1.0
        else:
            if sleeve_state.iloc[i] and state == 1.0:
                # Evaluate signal on SPY window up to and including today
                hist = spy_price.loc[:d]
                sig = signal_fn(hist)
                if pd.notna(sig) and sig < 0:
                    state = 0.0
                    trips += 1
        scale.iloc[i] = state
    return scale, trips


def raw_asset_dd_circuit(sleeve_state, sigs, panel, threshold=-0.10, lookback=63):
    spy_price = panel["SPY"].ffill()
    daily_idx = sleeve_state.index
    spy_aligned = spy_price.reindex(daily_idx).ffill()
    spy_peak = spy_aligned.rolling(lookback, min_periods=1).max()
    spy_dd = spy_aligned / spy_peak - 1.0
    scale = pd.Series(1.0, index=daily_idx)
    sig_set = set(sigs)
    state = 1.0
    trips = 0
    for i, d in enumerate(daily_idx):
        if d in sig_set:
            state = 1.0
        else:
            if sleeve_state.iloc[i] and state == 1.0:
                if pd.notna(spy_dd.iloc[i]) and spy_dd.iloc[i] < threshold:
                    state = 0.0
                    trips += 1
        scale.iloc[i] = state
    return scale, trips


if __name__ == "__main__":
    panel = load_panel(start=pd.Timestamp("1993-01-01"))
    start = pd.Timestamp("2008-04-30")
    end = pd.Timestamp("2026-05-22")

    bull_raw = run_bull_qqq_backtest(panel, start, end)
    sleeve_state, sigs = determine_sleeve_state(panel, start, end)
    sleeve_state = sleeve_state.reindex(bull_raw.index).fillna(False)

    # M1 baseline
    m1 = bull_raw

    # M2 sleeve-equity DD
    m2_scale = compute_dd_circuit_scale(bull_raw, sigs, DD_CIRCUIT_THRESHOLD, DD_CIRCUIT_SCALE)
    m2 = m2_scale * bull_raw
    trips_m2 = int((m2_scale.diff() < 0).sum())

    # M3 raw SPY-price DD
    m3_scale, trips_m3 = raw_asset_dd_circuit(sleeve_state, sigs, panel)
    m3 = m3_scale * bull_raw

    # M4 daily 13612W canary
    m4_scale, trips_m4 = daily_signal_circuit(panel, sleeve_state, sigs, sig_13612W_daily, "13612W")
    m4 = m4_scale * bull_raw

    # M5 daily 13612U canary (slower)
    m5_scale, trips_m5 = daily_signal_circuit(panel, sleeve_state, sigs, sig_13612U_daily, "13612U")
    m5 = m5_scale * bull_raw

    # M4b daily 13612W + DD-10% combined (either trips = defensive)
    combo_scale = m4_scale * m2_scale
    m4b = combo_scale * bull_raw
    trips_m4b = int((combo_scale.diff() < 0).sum())

    rows = [
        ("M1. No intramonth defense (baseline)", m1, 0),
        ("M2. Sleeve-equity DD-10% / 63d (current live)", m2, trips_m2),
        ("M3. Raw SPY-price DD-10% / 63d", m3, trips_m3),
        ("M4. Daily 13612W on SPY < 0 (proposed)", m4, trips_m4),
        ("M5. Daily 13612U on SPY < 0 (slower)", m5, trips_m5),
        ("M4b. Daily 13612W OR DD-10% (combined)", m4b, trips_m4b),
    ]

    print("\n" + "=" * 110)
    print("BULL-ext intramonth defense: DD circuits vs daily 13612W canary (2008-04 to 2026-05, 10bps)")
    print("=" * 110)
    print(f"{'Variant':<60} {'Sharpe':>8} {'CAGR':>8} {'Vol':>8} {'MaxDD':>9} {'Trips':>6}")
    print("-" * 110)
    for label, p, trips in rows:
        m = perf_metrics(p)
        calmar = m['cagr'] / abs(m['max_drawdown']) if m['max_drawdown'] != 0 else float('nan')
        print(f"{label:<60} {m['sharpe']:>8.3f} {m['cagr']*100:>7.2f}% {m['vol']*100:>7.2f}% "
              f"{m['max_drawdown']*100:>8.2f}% {trips:>6d}")
    print("=" * 110)
