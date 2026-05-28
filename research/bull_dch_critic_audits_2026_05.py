"""
Run critic's recommended sanity tests on live cpm_live.py DCH20 implementation.

Tests:
  S1. Causal lag test: shift trigger by 1 day. If Sharpe stays high, no lookahead.
      If collapses, there's a subtle peek.
  S2. Random-permutation null: shuffle trip dates 1000 times (preserving count
      and monthly distribution), see if real DCH20 is in top 1% or middle.
  S3. Random monthly defensive null: random 1-month defensive switch per quarter.
      If median is similar to DCH20, the lift is just market-timing luck.
  S4. Examine the "BUG?" in vol_cap.compute_donchian_circuit_scale: does it
      check whether sleeve is currently holding SPY before zeroing returns?
"""
import sys, socket
socket.setdefaulttimeout(15)
sys.path.insert(0, "/Users/rkautsar/personal/scripts/strategy_cpm")

import pandas as pd
import numpy as np
from cpm_live import load_panel, perf_metrics
from bull_qqq_live import run_bull_qqq_backtest
from vol_cap import (compute_donchian_circuit_scale,
                      compute_dd_circuit_scale,
                      DONCHIAN_CIRCUIT_WINDOW, DD_CIRCUIT_THRESHOLD,
                      DD_CIRCUIT_SCALE)


def summarize(label, ret):
    m = perf_metrics(ret)
    cal = m["cagr"] / abs(m["max_drawdown"]) if m["max_drawdown"] != 0 else float("nan")
    return f"{label:<55} Sharpe={m['sharpe']:>6.3f} | CAGR={m['cagr']*100:>6.2f}% | Vol={m['vol']*100:>6.2f}% | MaxDD={m['max_drawdown']*100:>7.2f}% | Calmar={cal:>5.2f}"


def donchian_scale_with_lag(asset_price, sleeve_index, sig_dates, window, extra_lag=0):
    """DCH20 STRICT variant with optional extra lag. extra_lag=0 = production,
    extra_lag=1 = use yesterday's trigger today (additional 1-day lag)."""
    price = asset_price.reindex(sleeve_index).ffill()
    rolling_low = price.shift(1 + extra_lag).rolling(window).min()
    price_to_check = price.shift(extra_lag)
    trigger = (price_to_check <= rolling_low) & price_to_check.notna() & rolling_low.notna()
    scale = pd.Series(1.0, index=sleeve_index)
    sig_set = set(sig_dates)
    state = 1.0
    for i, day in enumerate(sleeve_index):
        if day in sig_set:
            state = 1.0
        elif bool(trigger.iloc[i]):
            state = 0.0
        scale.iloc[i] = state
    return scale, int((trigger & ~pd.Series(scale, index=sleeve_index).shift(1).fillna(1).astype(bool)).sum())


def random_permutation_circuit(sleeve_index, sig_dates, n_trips_target, rng):
    """Build a scale series with n_trips_target trips at RANDOM days (latched until next sig)."""
    sig_set = set(sig_dates)
    candidate_days = [d for d in sleeve_index if d not in sig_set]
    if n_trips_target >= len(candidate_days):
        n_trips_target = len(candidate_days)
    trip_dates = set(rng.choice(candidate_days, size=n_trips_target, replace=False))
    scale = pd.Series(1.0, index=sleeve_index)
    state = 1.0
    for i, d in enumerate(sleeve_index):
        if d in sig_set:
            state = 1.0
        elif d in trip_dates:
            state = 0.0
        scale.iloc[i] = state
    return scale


def random_monthly_defensive(sleeve_index, sig_dates, rng):
    """Randomly mark 1 month per quarter as fully defensive (scale=0 entire month)."""
    sig_list = sorted(sig_dates)
    quarter_groups = [sig_list[i:i+3] for i in range(0, len(sig_list), 3)]
    defensive_months = set()
    for q in quarter_groups:
        if q:
            defensive_months.add(rng.choice(q))
    defensive_months = set(pd.Timestamp(d) for d in defensive_months)
    scale = pd.Series(1.0, index=sleeve_index)
    for i in range(len(sig_list) - 1):
        sd = sig_list[i]
        next_sd = sig_list[i+1]
        if sd in defensive_months:
            mask = (sleeve_index > sd) & (sleeve_index <= next_sd)
            scale.loc[mask] = 0.0
    return scale


if __name__ == "__main__":
    panel = load_panel(start=pd.Timestamp("1993-01-01"))
    start, end = pd.Timestamp("2008-04-30"), pd.Timestamp("2026-05-22")

    bull_raw = run_bull_qqq_backtest(panel, start, end)
    common = bull_raw.index[(bull_raw.index >= start) & (bull_raw.index <= end)]
    bull_raw = bull_raw.reindex(common)
    sigs = (pd.DataFrame({"x": 1}, index=common).groupby(pd.Grouper(freq="ME")).tail(1).index.tolist())
    spy_close = panel["SPY"].ffill()

    print("=" * 110)
    print("CRITIC AUDIT: sanity tests on live DCH20 implementation")
    print("=" * 110)

    print("\n--- S1. Causal lag test: shift signal by 0/1/2 days ---")
    print("Hypothesis: if real signal, lag-1 should be similar; if lookahead, lag-1 collapses Sharpe.")
    for lag in [0, 1, 2, 5]:
        scale, _ = donchian_scale_with_lag(spy_close, common, sigs,
                                            DONCHIAN_CIRCUIT_WINDOW, extra_lag=lag)
        ret = scale * bull_raw
        n_trips = int((scale.diff() < 0).sum())
        print(summarize(f"  DCH20 STRICT + {lag}-day extra lag ({n_trips} trips)", ret))

    print("\n--- S2. Random-permutation null: shuffle trip dates ---")
    # Reference real trips
    real_scale = compute_donchian_circuit_scale(spy_close, common, sigs,
                                                  window=DONCHIAN_CIRCUIT_WINDOW)
    real_ret = real_scale * bull_raw
    m_real = perf_metrics(real_ret)
    n_trips_real = int((real_scale.diff() < 0).sum())
    print(summarize(f"  REAL DCH20 STRICT ({n_trips_real} trips)", real_ret))
    print(f"  Building null distribution with {n_trips_real} random trips, 500 paths...")
    rng = np.random.default_rng(42)
    null_sharpes = []
    null_cagrs = []
    null_dds = []
    for i in range(500):
        rand_scale = random_permutation_circuit(common, sigs, n_trips_real, rng)
        rand_ret = rand_scale * bull_raw
        mn = perf_metrics(rand_ret)
        null_sharpes.append(mn["sharpe"])
        null_cagrs.append(mn["cagr"])
        null_dds.append(mn["max_drawdown"])
    null_sharpes = np.array(null_sharpes)
    null_cagrs = np.array(null_cagrs)
    null_dds = np.array(null_dds)
    pct_real_above = (null_sharpes < m_real["sharpe"]).mean() * 100
    print(f"  Null Sharpe: median={np.median(null_sharpes):.3f} | p5={np.percentile(null_sharpes,5):.3f} | p95={np.percentile(null_sharpes,95):.3f} | p99={np.percentile(null_sharpes,99):.3f}")
    print(f"  Null CAGR:   median={np.median(null_cagrs)*100:.2f}% | p95={np.percentile(null_cagrs,95)*100:.2f}%")
    print(f"  Null MaxDD:  median={np.median(null_dds)*100:.2f}% | p5={np.percentile(null_dds,5)*100:.2f}% (shallower)")
    print(f"  REAL Sharpe {m_real['sharpe']:.3f} is in the {pct_real_above:.1f} percentile of null distribution")
    if pct_real_above < 95:
        print(f"  >>> WARNING: real Sharpe is NOT in top 5% of null. Signal may be timing luck.")
    else:
        print(f"  >>> PASS: real Sharpe exceeds {pct_real_above:.1f}% of random-trip nulls.")

    print("\n--- S3. Random monthly defensive null: 1 month defensive per quarter ---")
    print(f"  Building null with random 1-of-3 month defensive switch, 500 paths...")
    rng = np.random.default_rng(123)
    null2_sharpes = []
    null2_cagrs = []
    null2_dds = []
    for i in range(500):
        rand_scale2 = random_monthly_defensive(common, sigs, rng)
        rand_ret2 = rand_scale2 * bull_raw
        mn = perf_metrics(rand_ret2)
        null2_sharpes.append(mn["sharpe"])
        null2_cagrs.append(mn["cagr"])
        null2_dds.append(mn["max_drawdown"])
    null2_sharpes = np.array(null2_sharpes)
    null2_cagrs = np.array(null2_cagrs)
    null2_dds = np.array(null2_dds)
    pct_real_above2 = (null2_sharpes < m_real["sharpe"]).mean() * 100
    print(f"  Null Sharpe: median={np.median(null2_sharpes):.3f} | p5={np.percentile(null2_sharpes,5):.3f} | p95={np.percentile(null2_sharpes,95):.3f}")
    print(f"  Null CAGR:   median={np.median(null2_cagrs)*100:.2f}% | p95={np.percentile(null2_cagrs,95)*100:.2f}%")
    print(f"  Null MaxDD:  median={np.median(null2_dds)*100:.2f}% | p5={np.percentile(null2_dds,5)*100:.2f}%")
    print(f"  REAL Sharpe {m_real['sharpe']:.3f} is in the {pct_real_above2:.1f} percentile of monthly-defensive null")

    print("\n--- S4. Implementation introspection ---")
    print(f"  Production DCH20 in vol_cap.compute_donchian_circuit_scale:")
    print(f"  - Triggers on SPY price regardless of whether sleeve is in SPY or safe")
    print(f"  - Zeros sleeve returns when triggered (even safe-asset returns)")
    print(f"  - Could mis-handle defensive months (zero out positive safe returns)")
    print(f"  Real trips that fire DURING defensive months (canary off):")
    from cpm_live import sig_13612U
    # Determine defensive months from monthly canary
    sig_set = set(sigs)
    holding_spy = pd.Series(False, index=common)
    cur = False
    for sd in sigs:
        monthly = panel.loc[:sd].resample("ME").last()
        hygm = sig_13612U(monthly["HYG_stitched"]) if "HYG_stitched" in monthly.columns else -999
        tipm = sig_13612U(monthly["TIP"]) if "TIP" in monthly.columns else -999
        c_ok = (pd.notna(hygm) and hygm > 0) or (pd.notna(tipm) and tipm > 0)
        spym = sig_13612U(monthly["SPY"])
        a_ok = pd.notna(spym) and spym > 0
        cur = c_ok and a_ok
        mask = (common > sd)
        if cur:
            holding_spy.loc[mask] = True
        else:
            holding_spy.loc[mask] = False
    trip_dates = common[(real_scale.diff() < 0).fillna(False)]
    n_trips_in_spy = sum(holding_spy.loc[d] for d in trip_dates if d in holding_spy.index)
    n_trips_in_safe = len(trip_dates) - n_trips_in_spy
    print(f"  Total trips: {len(trip_dates)} | In SPY months: {n_trips_in_spy} | In SAFE months: {n_trips_in_safe} ({n_trips_in_safe/max(len(trip_dates),1)*100:.0f}%)")
    print(f"  -> When trip fires during a defensive month, sleeve return on that day = 0 instead of safe return.")
    print("=" * 110)
