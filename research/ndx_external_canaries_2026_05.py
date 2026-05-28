"""
NDX intramonth canary using EXTERNAL macro signals (VIX term, LQD credit, HYG).

External canary advantages over sleeve-equity DD:
  - Reacts to broader risk-off independent of NDX sleeve P&L
  - Cited published rationale (VIX term structure for stress, LQD/HYG for credit)
  - Self-adaptive (VIX level/term itself is a market-priced vol signal)

External signals tested:
  VIX-based:
    [V1] VIX > rolling 252d mean + K*sigma (vol-spike z-score)
    [V2] VIX/VIX3M > threshold (term inversion / backwardation = stress)
    [V3] VIX > absolute level threshold (20, 25, 30)
    [V4] VIX dd-from-1y-low > K (vol-expansion ratio)

  LQD-based (investment-grade credit):
    [L1] LQD DD < -gamma from 63d peak
    [L2] LQD < SMA200 daily (trend below)
    [L3] LQD 13612W < 0 (HAA-style momentum on LQD)

  HYG-based (high-yield credit, narrower):
    [H1] HYG_stitched DD < -gamma
    [H2] HYG/LQD ratio < SMA50 (credit-spread proxy)
    [H3] HYG_stitched 13612W < 0

  Combos:
    [C1] [V2 VIX/VIX3M > 1.0] OR [L1 LQD DD < -5%]
    [C2] [REF DD -10%/63d] OR [V1 VIX z>2]
"""
import sys, socket, os
socket.setdefaulttimeout(60)
sys.path.insert(0, "/Users/rkautsar/personal/scripts/strategy_cpm")

import pandas as pd
import numpy as np
import yfinance as yf
from cpm_live import load_panel, perf_metrics
from ndx_sleeve_live import load_ndx_panel, run_ndx_backtest
from vol_cap import compute_dd_circuit_scale, DD_CIRCUIT_SCALE


def fetch_external_panel(start="2003-01-01", end="2026-05-31"):
    cache = "/tmp/ndx_external_canary_panel.csv"
    if os.path.exists(cache):
        df = pd.read_csv(cache, index_col=0, parse_dates=True)
        if {"VIX", "VIX3M", "LQD", "HYG_yf"}.issubset(df.columns):
            print(f"Loaded external panel cache: {df.shape}")
            return df
    print("Downloading VIX, VIX3M, LQD, HYG via yfinance...")
    data = yf.download(["^VIX", "^VIX3M", "LQD", "HYG"],
                        start=start, end=end, auto_adjust=True,
                        progress=False, threads=True)["Close"]
    data.columns = ["VIX", "VIX3M", "LQD", "HYG_yf"]
    data.to_csv(cache)
    print(f"Saved: {cache} {data.shape}")
    return data


def apply_t_plus_1(sleeve_returns, trigger, sig_dates):
    daily_idx = sleeve_returns.index
    trigger_d = trigger.reindex(daily_idx).fillna(False)
    sig_set = set(sig_dates)
    scale = pd.Series(1.0, index=daily_idx)
    state = 1.0
    trips = 0
    for i, day in enumerate(daily_idx):
        if day in sig_set:
            state = 1.0
        scale.iloc[i] = state
        if bool(trigger_d.iloc[i]):
            if state == 1.0:
                trips += 1
            state = 0.0
    return scale * sleeve_returns, trips


def metrics_row(label, ret, trips):
    m = perf_metrics(ret)
    cal = m["cagr"] / abs(m["max_drawdown"]) if m["max_drawdown"] != 0 else float("nan")
    return (label, m["sharpe"], m["cagr"] * 100, m["vol"] * 100,
             m["max_drawdown"] * 100, trips, cal)


def print_table(rows, title):
    print("\n" + "=" * 120)
    print(title)
    print("=" * 120)
    print(f"{'Variant':<65} {'Sharpe':>7} {'CAGR':>7} {'Vol':>7} {'MaxDD':>9} {'Trips':>6} {'Calmar':>7}")
    print("-" * 120)
    for r in rows:
        if r[0] == "---":
            print("-" * 120); continue
        print(f"{r[0]:<65} {r[1]:>7.3f} {r[2]:>6.2f}% {r[3]:>6.2f}% {r[4]:>8.2f}% {r[5]:>6d} {r[6]:>7.2f}")
    print("=" * 120)


if __name__ == "__main__":
    panel = load_panel(start=pd.Timestamp("1993-01-01"))
    ndx_panel = load_ndx_panel()
    start, end = pd.Timestamp("2008-04-30"), pd.Timestamp("2026-05-22")
    ndx_raw, _ = run_ndx_backtest(panel, ndx_panel, start, end)
    common = ndx_raw.index[(ndx_raw.index >= start) & (ndx_raw.index <= end)]
    ndx_raw = ndx_raw.reindex(common).fillna(0.0)
    sigs = (pd.DataFrame({"x": 1}, index=common).groupby(pd.Grouper(freq="ME")).tail(1).index.tolist())

    ext = fetch_external_panel()
    vix = ext["VIX"].reindex(common).ffill()
    vix3m = ext["VIX3M"].reindex(common).ffill()
    lqd = ext["LQD"].reindex(common).ffill()
    hyg_yf = ext["HYG_yf"].reindex(common).ffill()
    hyg_stitched = panel["HYG_stitched"].reindex(common).ffill()

    print(f"VIX range: {vix.dropna().index.min().date()} -> {vix.dropna().index.max().date()}")
    print(f"VIX3M range: {vix3m.dropna().index.min().date()} -> {vix3m.dropna().index.max().date()}")
    print(f"LQD range: {lqd.dropna().index.min().date()} -> {lqd.dropna().index.max().date()}")

    rows = []
    # References
    rows.append(metrics_row("[REF1] NDX raw (no circuit)", ndx_raw, 0))
    s_curr = compute_dd_circuit_scale(ndx_raw, sigs, -0.10, DD_CIRCUIT_SCALE)
    rows.append(metrics_row("[REF2] DD -10%/63d sleeve (current prod)", s_curr * ndx_raw, int((s_curr.diff() < 0).sum())))
    s_125 = compute_dd_circuit_scale(ndx_raw, sigs, -0.125, DD_CIRCUIT_SCALE)
    rows.append(metrics_row("[REF3] DD -12.5%/63d sleeve (best fixed)", s_125 * ndx_raw, int((s_125.diff() < 0).sum())))
    # Lo-Kaminski J=3mo gamma=8% as canonical reference
    def lo_kaminski(sleeve, J, gamma):
        cum = (1.0 + sleeve).rolling(J).apply(lambda x: x.prod() - 1.0, raw=True)
        return cum < -gamma
    out_lk, t_lk = apply_t_plus_1(ndx_raw, lo_kaminski(ndx_raw, 63, 0.08), sigs)
    rows.append(metrics_row("[REF4] Lo-Kaminski J=63d, gamma=8% (canonical)", out_lk, t_lk))
    rows.append(("---", 0, 0, 0, 0, 0, 0))

    # === V. VIX-based ===
    # V1 VIX z-score vs 252d
    vix_mu = vix.rolling(252).mean()
    vix_sd = vix.rolling(252).std()
    vix_z = (vix - vix_mu) / vix_sd
    for K in [1.0, 1.5, 2.0, 2.5]:
        trig = vix_z > K
        out, t = apply_t_plus_1(ndx_raw, trig, sigs)
        rows.append(metrics_row(f"[V1] VIX z-score (vs 252d) > {K}", out, t))
    # V2 VIX/VIX3M term inversion
    vix_ratio = vix / vix3m
    for thr in [0.95, 1.00, 1.05]:
        trig = vix_ratio > thr
        out, t = apply_t_plus_1(ndx_raw, trig, sigs)
        rows.append(metrics_row(f"[V2] VIX/VIX3M > {thr:.2f} (term inversion)", out, t))
    # V3 VIX absolute level
    for lvl in [20, 25, 30, 35]:
        trig = vix > lvl
        out, t = apply_t_plus_1(ndx_raw, trig, sigs)
        rows.append(metrics_row(f"[V3] VIX > {lvl} (absolute level)", out, t))
    rows.append(("---", 0, 0, 0, 0, 0, 0))

    # === L. LQD-based ===
    # L1 LQD DD
    lqd_eq_peak = lqd.rolling(63, min_periods=1).max()
    lqd_dd = lqd / lqd_eq_peak - 1.0
    for gamma in [0.02, 0.03, 0.05, 0.08]:
        trig = lqd_dd < -gamma
        out, t = apply_t_plus_1(ndx_raw, trig, sigs)
        rows.append(metrics_row(f"[L1] LQD DD < -{gamma*100:.0f}% from 63d peak", out, t))
    # L2 LQD < SMA200
    sma200 = lqd.rolling(200).mean()
    trig = lqd < sma200
    out, t = apply_t_plus_1(ndx_raw, trig, sigs)
    rows.append(metrics_row("[L2] LQD < SMA200 daily", out, t))
    # L3 LQD 13612W daily < 0
    r1 = lqd.pct_change(22); r3 = lqd.pct_change(64); r6 = lqd.pct_change(127); r12 = lqd.pct_change(253)
    lqd_13612W = (12*r1 + 4*r3 + 2*r6 + r12) / 19
    trig = lqd_13612W < 0
    out, t = apply_t_plus_1(ndx_raw, trig, sigs)
    rows.append(metrics_row("[L3] LQD 13612W daily < 0", out, t))
    rows.append(("---", 0, 0, 0, 0, 0, 0))

    # === H. HYG-based ===
    # H1 HYG_stitched DD
    hyg_peak = hyg_stitched.rolling(63, min_periods=1).max()
    hyg_dd = hyg_stitched / hyg_peak - 1.0
    for gamma in [0.02, 0.03, 0.05, 0.08]:
        trig = hyg_dd < -gamma
        out, t = apply_t_plus_1(ndx_raw, trig, sigs)
        rows.append(metrics_row(f"[H1] HYG_stitched DD < -{gamma*100:.0f}% from 63d peak", out, t))
    # H2 HYG/LQD ratio falling: credit spread proxy
    hl_ratio = hyg_yf / lqd
    hl_sma50 = hl_ratio.rolling(50).mean()
    trig = hl_ratio < hl_sma50
    out, t = apply_t_plus_1(ndx_raw, trig, sigs)
    rows.append(metrics_row("[H2] HYG/LQD ratio < SMA50 (credit spread)", out, t))
    # H3 HYG 13612W
    r1 = hyg_stitched.pct_change(22); r3 = hyg_stitched.pct_change(64); r6 = hyg_stitched.pct_change(127); r12 = hyg_stitched.pct_change(253)
    hyg_13612W = (12*r1 + 4*r3 + 2*r6 + r12) / 19
    trig = hyg_13612W < 0
    out, t = apply_t_plus_1(ndx_raw, trig, sigs)
    rows.append(metrics_row("[H3] HYG_stitched 13612W daily < 0", out, t))
    rows.append(("---", 0, 0, 0, 0, 0, 0))

    # === Combos with sleeve DD ===
    # C1: REF DD -10% OR V2 VIX/VIX3M > 1.0
    dd_scale = compute_dd_circuit_scale(ndx_raw, sigs, -0.10, DD_CIRCUIT_SCALE)
    dd_triggered = (dd_scale == 0.0).reindex(common)
    for ext_label, ext_trig in [
        ("V2 VIX/VIX3M > 1.0", vix_ratio > 1.0),
        ("V2 VIX/VIX3M > 1.05", vix_ratio > 1.05),
        ("L1 LQD DD<-3%", lqd_dd < -0.03),
        ("L1 LQD DD<-5%", lqd_dd < -0.05),
        ("H2 HYG/LQD<SMA50", hl_ratio < hl_sma50),
    ]:
        combo = dd_triggered | ext_trig.reindex(common).fillna(False)
        out, t = apply_t_plus_1(ndx_raw, combo, sigs)
        rows.append(metrics_row(f"[C-OR] [REF DD -10%] OR [{ext_label}]", out, t))

    # Sort rest by Sharpe (keep refs at top)
    refs = []
    core = []
    in_refs = True
    for r in rows:
        if r[0] == "---":
            if in_refs:
                refs.append(r); in_refs = False
            continue
        if r[0].startswith("[REF"):
            refs.append(r)
        else:
            core.append(r)
    core.sort(key=lambda r: -r[1])
    final = refs + core
    print_table(final, "NDX external macro canaries (HONEST t+1 MOO, 2008-04 to 2026-05, 10bps)\nSorted by Sharpe within external candidates.")
