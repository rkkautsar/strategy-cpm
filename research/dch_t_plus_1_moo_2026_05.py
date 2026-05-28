"""
DCH20 with strict t+1 MOO execution lag:
  Trigger evaluated at day t close (STRICT: today's close <= 20d low excluding today)
  Scale applied STARTING day t+1 (model execution at next-day open / MOO)

Compare:
  V0. Production buggy: trigger[t] -> scale[t]=0 (same-day, has lookahead)
  V1. T+1 MOO honest: trigger[t] -> scale[t+1]=0 (next-day execution)
  V2. Baseline (no circuit)
  V3. Current DD-10%/63d (the rollback target)

Plus: NDX sleeve with same audit applied to validate NDX DD-10% has no analogous lookahead.
"""
import sys, socket
socket.setdefaulttimeout(15)
sys.path.insert(0, "/Users/rkautsar/personal/scripts/strategy_cpm")

import pandas as pd
import numpy as np
from cpm_live import load_panel, perf_metrics
from bull_qqq_live import run_bull_qqq_backtest
from ndx_sleeve_live import load_ndx_panel, run_ndx_backtest
from vol_cap import (compute_dd_circuit_scale,
                      DD_CIRCUIT_THRESHOLD, DD_CIRCUIT_SCALE)


def dch_scale_sameday(asset_price, sleeve_index, sig_dates, window=20):
    """V0: trigger[t] fires -> scale[t]=0. The buggy production version."""
    price = asset_price.reindex(sleeve_index).ffill()
    rolling_low = price.shift(1).rolling(window).min()
    trigger = (price <= rolling_low) & price.notna() & rolling_low.notna()
    scale = pd.Series(1.0, index=sleeve_index)
    sig_set = set(sig_dates)
    state = 1.0
    for i, day in enumerate(sleeve_index):
        if day in sig_set:
            state = 1.0
        elif bool(trigger.iloc[i]):
            state = 0.0
        scale.iloc[i] = state
    return scale


def dch_scale_t_plus_1(asset_price, sleeve_index, sig_dates, window=20):
    """V1: trigger[t] fires -> scale[t+1]=0. Proper next-day execution.
    Trigger evaluated at day t close (STRICT, today excluded from window).
    Defensive scale APPLIES STARTING day t+1 (model T+1 execution).
    Resets at monthly signal date as before.
    """
    price = asset_price.reindex(sleeve_index).ffill()
    rolling_low = price.shift(1).rolling(window).min()
    trigger = (price <= rolling_low) & price.notna() & rolling_low.notna()
    scale = pd.Series(1.0, index=sleeve_index)
    sig_set = set(sig_dates)
    state = 1.0
    # Process: on day t, set scale[t]=current state FIRST, THEN check trigger to update state for tomorrow.
    for i, day in enumerate(sleeve_index):
        if day in sig_set:
            state = 1.0
        scale.iloc[i] = state
        # AFTER setting today's scale, check trigger for tomorrow
        if bool(trigger.iloc[i]):
            state = 0.0
    return scale


def dch_scale_sleeve_state_aware(asset_price, holding_asset_indicator, sleeve_index,
                                   sig_dates, window=20):
    """V1 variant: only fire when sleeve currently holds SPY (don't zero safe returns)."""
    price = asset_price.reindex(sleeve_index).ffill()
    rolling_low = price.shift(1).rolling(window).min()
    trigger = (price <= rolling_low) & price.notna() & rolling_low.notna()
    scale = pd.Series(1.0, index=sleeve_index)
    sig_set = set(sig_dates)
    state = 1.0
    for i, day in enumerate(sleeve_index):
        if day in sig_set:
            state = 1.0
        scale.iloc[i] = state
        # T+1 execution + sleeve-state-aware:
        if bool(trigger.iloc[i]) and bool(holding_asset_indicator.iloc[i]):
            state = 0.0
    return scale


def determine_sleeve_state(panel, sleeve_index, sig_dates):
    """T/F daily series for 'BULL holds SPY'."""
    from cpm_live import sig_13612U
    out = pd.Series(False, index=sleeve_index)
    cur = False
    for sd in sig_dates:
        monthly = panel.loc[:sd].resample("ME").last()
        hygm = sig_13612U(monthly["HYG_stitched"]) if "HYG_stitched" in monthly.columns else -999
        tipm = sig_13612U(monthly["TIP"]) if "TIP" in monthly.columns else -999
        c_ok = (pd.notna(hygm) and hygm > 0) or (pd.notna(tipm) and tipm > 0)
        spym = sig_13612U(monthly["SPY"])
        a_ok = pd.notna(spym) and spym > 0
        cur = c_ok and a_ok
        mask = (sleeve_index > sd)
        if cur:
            out.loc[mask] = True
        else:
            out.loc[mask] = False
    return out


def summarize(label, ret):
    m = perf_metrics(ret)
    cal = m["cagr"] / abs(m["max_drawdown"]) if m["max_drawdown"] != 0 else float("nan")
    return (label, m["sharpe"], m["cagr"] * 100, m["vol"] * 100,
             m["max_drawdown"] * 100, cal)


if __name__ == "__main__":
    panel = load_panel(start=pd.Timestamp("1993-01-01"))
    ndx_panel = load_ndx_panel()
    start, end = pd.Timestamp("2008-04-30"), pd.Timestamp("2026-05-22")

    bull_raw = run_bull_qqq_backtest(panel, start, end)
    common = bull_raw.index[(bull_raw.index >= start) & (bull_raw.index <= end)]
    bull_raw = bull_raw.reindex(common)
    sigs = (pd.DataFrame({"x": 1}, index=common).groupby(pd.Grouper(freq="ME")).tail(1).index.tolist())
    spy_close = panel["SPY"].ffill()
    holding_spy = determine_sleeve_state(panel, common, sigs)

    rows = []

    # V2 baseline (no circuit)
    rows.append(summarize("V2. Baseline BULL (no intramonth circuit)", bull_raw))

    # V3 DD-10% (rollback target)
    s_dd = compute_dd_circuit_scale(bull_raw, sigs, DD_CIRCUIT_THRESHOLD, DD_CIRCUIT_SCALE)
    rows.append(summarize("V3. DD-10%/63d sleeve-equity (rollback target)", s_dd * bull_raw))

    # V0 buggy (lookahead)
    s0 = dch_scale_sameday(spy_close, common, sigs, 20)
    rows.append(summarize("V0. DCH20 STRICT same-day (LOOKAHEAD-BUGGY)", s0 * bull_raw))

    # V1 proper t+1 MOO execution
    s1 = dch_scale_t_plus_1(spy_close, common, sigs, 20)
    rows.append(summarize("V1. DCH20 STRICT + T+1 MOO execution (honest)", s1 * bull_raw))

    # V1' state-aware (only fire when holding SPY)
    s1_sa = dch_scale_sleeve_state_aware(spy_close, holding_spy, common, sigs, 20)
    rows.append(summarize("V1'. V1 + sleeve-state-aware (only fire holding SPY)", s1_sa * bull_raw))

    # Run a few different N for V1 to see if N=20 was the issue
    for N in [10, 15, 20, 25, 30]:
        s_n = dch_scale_t_plus_1(spy_close, common, sigs, N)
        rows.append(summarize(f"V1. DCH{N} STRICT + T+1 MOO (honest)", s_n * bull_raw))

    print("\n" + "=" * 110)
    print("DCH20 honest T+1 MOO execution test (2008-04 to 2026-05, 10bps, live BULL engine)")
    print("=" * 110)
    print(f"{'Variant':<55} {'Sharpe':>8} {'CAGR':>8} {'Vol':>8} {'MaxDD':>9} {'Calmar':>7}")
    print("-" * 110)
    for r in rows:
        print(f"{r[0]:<55} {r[1]:>8.3f} {r[2]:>7.2f}% {r[3]:>7.2f}% {r[4]:>8.2f}% {r[5]:>7.2f}")
    print("=" * 110)

    # Quick sanity: NDX DD-10% audit (does the existing NDX circuit have same lookahead?)
    ndx_raw, _ = run_ndx_backtest(panel, ndx_panel, start, end)
    ndx_raw = ndx_raw.reindex(common).fillna(0.0)
    sigs_ndx = sigs

    def shift_dd_scale(sleeve_returns, sig_dates, threshold=-0.10, lookback=63):
        """Same-day NDX DD scale shifted by 1 day to test for analogous lookahead."""
        eq = (1.0 + sleeve_returns).cumprod()
        rolling_peak = eq.rolling(lookback, min_periods=1).max()
        dd = eq / rolling_peak - 1.0
        scale = pd.Series(1.0, index=sleeve_returns.index)
        sig_set = set(sig_dates)
        state = 1.0
        for i, day in enumerate(sleeve_returns.index):
            if day in sig_set:
                state = 1.0
            scale.iloc[i] = state  # set TODAY's scale FIRST
            if dd.iloc[i] < threshold:
                state = 0.0  # then trigger fires for TOMORROW
        return scale

    ndx_dd_sameday = compute_dd_circuit_scale(ndx_raw, sigs_ndx, DD_CIRCUIT_THRESHOLD, DD_CIRCUIT_SCALE)
    ndx_dd_t1 = shift_dd_scale(ndx_raw, sigs_ndx)
    print("\n" + "=" * 110)
    print("NDX DD-10%/63d audit: same-day vs t+1 MOO execution")
    print("=" * 110)
    print(f"{'Variant':<55} {'Sharpe':>8} {'CAGR':>8} {'Vol':>8} {'MaxDD':>9} {'Calmar':>7}")
    print("-" * 110)
    for label, ret in [("NDX raw (no circuit)", ndx_raw),
                         ("NDX + DD-10% same-day (production)", ndx_dd_sameday * ndx_raw),
                         ("NDX + DD-10% T+1 MOO (causally honest)", ndx_dd_t1 * ndx_raw)]:
        m = perf_metrics(ret)
        cal = m["cagr"] / abs(m["max_drawdown"]) if m["max_drawdown"] != 0 else float("nan")
        print(f"{label:<55} {m['sharpe']:>8.3f} {m['cagr']*100:>7.2f}% {m['vol']*100:>7.2f}% "
              f"{m['max_drawdown']*100:>8.2f}% {cal:>7.2f}")
    print("=" * 110)
