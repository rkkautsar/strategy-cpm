"""
1. Audit DCH20 for look-ahead bias: re-run with strict prior-day comparison
   (SPY[t] <= 20-day low of SPY[t-20:t-1], i.e., excluding today)
2. Decompose DCH20 trips: forward 1/5/21-day SPY return after each trip
3. Test DCH on NDX sleeve (replace current DD-10%/63d with DCH20 on QQQ)
"""
import sys, socket
socket.setdefaulttimeout(15)
sys.path.insert(0, "/Users/rkautsar/personal/scripts/strategy_cpm")

import pandas as pd
import numpy as np
from cpm_live import load_panel, perf_metrics, sig_13612U, best_safe
from bull_qqq_live import run_bull_qqq_backtest
from ndx_sleeve_live import load_ndx_panel, run_ndx_backtest
from vol_cap import compute_dd_circuit_scale, DD_CIRCUIT_THRESHOLD, DD_CIRCUIT_SCALE


def determine_sleeve_state(panel, start, end):
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
    return out, list(sigs)


def dch_trigger_strict(spy_close, window):
    """Strict: SPY[t] <= min(SPY[t-window:t-1]). Excludes today from rolling window.
    Prevents same-day look-ahead leakage."""
    rolling_low = spy_close.shift(1).rolling(window).min()
    return (spy_close <= rolling_low)


def dch_trigger_inclusive(spy_close, window):
    """Inclusive (original): SPY[t] <= min(SPY[t-window+1:t]). Includes today."""
    return (spy_close <= spy_close.rolling(window).min())


def apply_circuit(returns, holding_asset, sigs, trigger):
    daily_idx = returns.index
    trigger_d = trigger.reindex(daily_idx).fillna(False)
    sig_set = set(sigs)
    scale = pd.Series(1.0, index=daily_idx)
    state = 1.0
    trips = 0
    trip_dates = []
    for i, d in enumerate(daily_idx):
        if d in sig_set:
            state = 1.0
        else:
            if holding_asset.iloc[i] and state == 1.0 and bool(trigger_d.iloc[i]):
                state = 0.0
                trips += 1
                trip_dates.append(d)
        scale.iloc[i] = state
    return scale * returns, trips, trip_dates


def forward_returns_after_trips(asset_close, trip_dates, horizons=(1, 5, 21)):
    """For each trip date, compute forward H-day cumulative asset return."""
    if not trip_dates: return {}
    out = {h: [] for h in horizons}
    for d in trip_dates:
        if d not in asset_close.index: continue
        idx = asset_close.index.get_loc(d)
        for h in horizons:
            if idx + h < len(asset_close):
                p0 = asset_close.iloc[idx]
                ph = asset_close.iloc[idx + h]
                out[h].append((ph / p0 - 1))
    return out


def metrics_row(label, returns, trips):
    m = perf_metrics(returns)
    cal = m["cagr"] / abs(m["max_drawdown"]) if m["max_drawdown"] != 0 else float("nan")
    return (label, m["sharpe"], m["cagr"] * 100, m["vol"] * 100,
             m["max_drawdown"] * 100, trips, cal)


if __name__ == "__main__":
    panel = load_panel(start=pd.Timestamp("1993-01-01"))
    ndx_panel = load_ndx_panel()
    start, end = pd.Timestamp("2008-04-30"), pd.Timestamp("2026-05-22")

    # ========== Part 1: Audit DCH20 look-ahead bias on BULL ==========
    print("=" * 110)
    print("PART 1. Look-ahead bias audit: DCH20 inclusive (same-day close in window) vs strict (prior-day only)")
    print("=" * 110)
    bull_raw = run_bull_qqq_backtest(panel, start, end)
    hs, sigs = determine_sleeve_state(panel, start, end)
    hs = hs.reindex(bull_raw.index).fillna(False)
    spy_close = panel["SPY"].ffill()

    m2_scale = compute_dd_circuit_scale(bull_raw, sigs, DD_CIRCUIT_THRESHOLD, DD_CIRCUIT_SCALE)
    rows = [
        metrics_row("M1. No defense (baseline)", bull_raw, 0),
        metrics_row("M2. Sleeve DD-10% (current live)", m2_scale * bull_raw, int((m2_scale.diff() < 0).sum())),
    ]
    for window in [10, 15, 20, 25, 30]:
        inc, t_inc, _ = apply_circuit(bull_raw, hs, sigs, dch_trigger_inclusive(spy_close, window))
        strict, t_strict, _ = apply_circuit(bull_raw, hs, sigs, dch_trigger_strict(spy_close, window))
        rows.append(metrics_row(f"DCH{window} inclusive (orig: today in window)", inc, t_inc))
        rows.append(metrics_row(f"DCH{window} STRICT (today excluded; look-ahead-safe)", strict, t_strict))
        rows.append(("---", 0, 0, 0, 0, 0, 0))

    print(f"{'Variant':<55} {'Sharpe':>8} {'CAGR':>8} {'Vol':>8} {'MaxDD':>9} {'Trips':>6} {'Calmar':>7}")
    print("-" * 110)
    for r in rows:
        if r[0] == "---":
            print("-" * 110); continue
        print(f"{r[0]:<55} {r[1]:>8.3f} {r[2]:>7.2f}% {r[3]:>7.2f}% {r[4]:>8.2f}% {r[5]:>6d} {r[6]:>7.2f}")
    print("=" * 110)

    # ========== Part 2: Forward-return distribution after DCH20 trips on SPY ==========
    print("\n" + "=" * 110)
    print("PART 2. Forward SPY return distribution after each DCH20 trip (strict)")
    print("=" * 110)
    _, _, trip_dates = apply_circuit(bull_raw, hs, sigs, dch_trigger_strict(spy_close, 20))
    fwd = forward_returns_after_trips(spy_close, trip_dates, horizons=(1, 5, 10, 21))
    print(f"Total trips: {len(trip_dates)}")
    for h, vals in fwd.items():
        if not vals: continue
        arr = np.array(vals)
        print(f"  Forward {h:>2}-day SPY return: "
              f"mean={arr.mean()*100:+.2f}% | median={np.median(arr)*100:+.2f}% | "
              f"pct_negative={(arr < 0).mean()*100:.1f}% | "
              f"hit-rate of >-2%: {(arr > -0.02).mean()*100:.1f}%")
    if fwd[1]:
        baseline = spy_close.pct_change(1).dropna().mean()
        baseline5 = (spy_close.pct_change(5).dropna()).mean()
        baseline21 = (spy_close.pct_change(21).dropna()).mean()
        print(f"  Unconditional baseline: 1d={baseline*100:+.3f}% | 5d={baseline5*100:+.3f}% | 21d={baseline21*100:+.3f}%")
    print("=" * 110)

    # ========== Part 3: Test DCH on NDX sleeve ==========
    print("\n" + "=" * 110)
    print("PART 3. NDX sleeve: current DD-10%/63d circuit vs DCH on QQQ proxy")
    print("=" * 110)
    ndx_raw, _ = run_ndx_backtest(panel, ndx_panel, start, end)
    qqq_close = panel["QQQ"].ffill()
    # NDX holds stocks when TIP canary on; use TIP-only canary state as "holding" indicator
    # For simplicity, infer "holding NDX stocks" from non-zero NDX returns (heuristic), or
    # from monthly TIP signal. Use monthly TIP canary state:
    sigs_ndx = (pd.DataFrame({"x": 1}, index=ndx_raw.index)
                .groupby(pd.Grouper(freq="ME")).tail(1).index.tolist())
    ndx_holding_per_sig = {}
    for sd in sigs_ndx:
        monthly = panel.loc[:sd].resample("ME").last()
        tipm = sig_13612U(monthly["TIP"]) if "TIP" in monthly.columns else -999.0
        ndx_holding_per_sig[sd] = pd.notna(tipm) and tipm > 0
    daily_idx = ndx_raw.index
    ndx_holding = pd.Series(False, index=daily_idx)
    cur = False
    sigs_sorted = sorted(ndx_holding_per_sig.keys())
    for i, d in enumerate(daily_idx):
        for sd in sigs_sorted:
            if sd < d:
                cur = ndx_holding_per_sig[sd]
        ndx_holding.iloc[i] = cur

    ndx_rows = [metrics_row("NDX raw (no circuit)", ndx_raw, 0)]
    ndx_dd_scale = compute_dd_circuit_scale(ndx_raw, sigs_ndx, DD_CIRCUIT_THRESHOLD, DD_CIRCUIT_SCALE)
    ndx_dd = ndx_dd_scale * ndx_raw
    ndx_rows.append(metrics_row("NDX + DD-10%/63d sleeve-equity (current live)", ndx_dd,
                                  int((ndx_dd_scale.diff() < 0).sum())))
    for window in [10, 15, 20, 25, 30]:
        out, trips, _ = apply_circuit(ndx_raw, ndx_holding, sigs_ndx, dch_trigger_strict(qqq_close, window))
        ndx_rows.append(metrics_row(f"NDX + DCH{window} STRICT on QQQ", out, trips))

    print(f"{'Variant':<55} {'Sharpe':>8} {'CAGR':>8} {'Vol':>8} {'MaxDD':>9} {'Trips':>6} {'Calmar':>7}")
    print("-" * 110)
    for r in ndx_rows:
        print(f"{r[0]:<55} {r[1]:>8.3f} {r[2]:>7.2f}% {r[3]:>7.2f}% {r[4]:>8.2f}% {r[5]:>6d} {r[6]:>7.2f}")
    print("=" * 110)
