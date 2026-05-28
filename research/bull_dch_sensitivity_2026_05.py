"""
DCH (Donchian channel) breakdown sensitivity for BULL daily intramonth canary.

Tests:
  A. DCH window sweep: N = 5, 10, 15, 20, 25, 30, 40, 60, 90 days on full window
  B. Sub-period stability: 2008-2014, 2014-2020, 2020-2026 with DCH20
  C. Extended pre-2008 backtest (2002-2026, 24y) using HYG_stitched
  D. DCH20 vs other top contenders across sub-periods

All vs M2 (sleeve-equity DD-10% current live) as baseline reference.
"""
import sys, socket
socket.setdefaulttimeout(15)
sys.path.insert(0, "/Users/rkautsar/personal/scripts/strategy_cpm")

import pandas as pd
import numpy as np
from cpm_live import load_panel, perf_metrics, sig_13612U, best_safe
from bull_qqq_live import run_bull_qqq_backtest
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


def daily_dch_trigger(spy_close, window):
    """Returns bool series: True when SPY <= rolling N-day low (new N-day low)."""
    rolling_low = spy_close.rolling(window).min()
    return (spy_close <= rolling_low)


def daily_13612W_trigger(spy_close):
    r1 = spy_close.pct_change(22)
    r3 = spy_close.pct_change(64)
    r6 = spy_close.pct_change(127)
    r12 = spy_close.pct_change(253)
    return ((12 * r1 + 4 * r3 + 2 * r6 + r12) / 19 < 0)


def apply_circuit(returns, holding_spy, sigs, trigger):
    daily_idx = returns.index
    trigger_d = trigger.reindex(daily_idx).fillna(False)
    sig_set = set(sigs)
    scale = pd.Series(1.0, index=daily_idx)
    state = 1.0
    trips = 0
    for i, d in enumerate(daily_idx):
        if d in sig_set:
            state = 1.0
        else:
            if holding_spy.iloc[i] and state == 1.0 and bool(trigger_d.iloc[i]):
                state = 0.0
                trips += 1
        scale.iloc[i] = state
    return scale * returns, trips


def run_bull(panel, start, end):
    bull_raw = run_bull_qqq_backtest(panel, start, end)
    holding_spy, sigs = determine_sleeve_state(panel, start, end)
    holding_spy = holding_spy.reindex(bull_raw.index).fillna(False)
    return bull_raw, holding_spy, sigs


def metrics_row(label, returns, trips):
    m = perf_metrics(returns)
    cal = m["cagr"] / abs(m["max_drawdown"]) if m["max_drawdown"] != 0 else float("nan")
    return (label, m["sharpe"], m["cagr"] * 100, m["vol"] * 100,
             m["max_drawdown"] * 100, trips, cal)


def print_table(rows, title):
    print("\n" + "=" * 110)
    print(title)
    print("=" * 110)
    print(f"{'Variant':<55} {'Sharpe':>8} {'CAGR':>8} {'Vol':>8} {'MaxDD':>9} {'Trips':>6} {'Calmar':>7}")
    print("-" * 110)
    for r in rows:
        print(f"{r[0]:<55} {r[1]:>8.3f} {r[2]:>7.2f}% {r[3]:>7.2f}% {r[4]:>8.2f}% {r[5]:>6d} {r[6]:>7.2f}")
    print("=" * 110)


if __name__ == "__main__":
    panel = load_panel(start=pd.Timestamp("1993-01-01"))
    spy_close_full = panel["SPY"].ffill()

    # ----- A. DCH window sweep on full 2008-2026 window -----
    start, end = pd.Timestamp("2008-04-30"), pd.Timestamp("2026-05-22")
    bull_raw, hs, sigs = run_bull(panel, start, end)
    m2_scale = compute_dd_circuit_scale(bull_raw, sigs, DD_CIRCUIT_THRESHOLD, DD_CIRCUIT_SCALE)
    m2 = m2_scale * bull_raw
    rows = [
        metrics_row("M1. No intramonth defense", bull_raw, 0),
        metrics_row("M2. Sleeve-equity DD-10% (current live)", m2, int((m2_scale.diff() < 0).sum())),
        metrics_row("13612W reference", *apply_circuit(bull_raw, hs, sigs, daily_13612W_trigger(spy_close_full))),
    ]
    for N in [5, 10, 15, 20, 25, 30, 40, 60, 90]:
        trig = daily_dch_trigger(spy_close_full, N)
        out, trips = apply_circuit(bull_raw, hs, sigs, trig)
        rows.append(metrics_row(f"DCH{N}", out, trips))
    print_table(rows, "A. DCH window sweep (2008-04-30 to 2026-05-22)")

    # ----- B. Sub-period stability with DCH20 vs M2 -----
    periods = [
        ("2008-04 to 2014-04 (early, GFC + recovery)", pd.Timestamp("2008-04-30"), pd.Timestamp("2014-04-30")),
        ("2014-04 to 2020-04 (mid, low-vol bull + COVID)", pd.Timestamp("2014-04-30"), pd.Timestamp("2020-04-30")),
        ("2020-04 to 2026-05 (recent, post-COVID + 2022)", pd.Timestamp("2020-04-30"), pd.Timestamp("2026-05-22")),
    ]
    sub_rows = []
    for plabel, ps, pe in periods:
        bull_p, hs_p, sigs_p = run_bull(panel, ps, pe)
        # M2 and DCH20 only
        m2s = compute_dd_circuit_scale(bull_p, sigs_p, DD_CIRCUIT_THRESHOLD, DD_CIRCUIT_SCALE)
        m2p = m2s * bull_p
        m2_t = int((m2s.diff() < 0).sum())
        dch_out, dch_t = apply_circuit(bull_p, hs_p, sigs_p, daily_dch_trigger(spy_close_full, 20))
        sub_rows.append(metrics_row(f"   M2 (sleeve DD-10%) -- {plabel}", m2p, m2_t))
        sub_rows.append(metrics_row(f"   DCH20             -- {plabel}", dch_out, dch_t))
        sub_rows.append(("---", 0, 0, 0, 0, 0, 0))
    print("\n" + "=" * 110)
    print("B. Sub-period stability: M2 (sleeve DD-10%) vs DCH20")
    print("=" * 110)
    print(f"{'Variant':<55} {'Sharpe':>8} {'CAGR':>8} {'Vol':>8} {'MaxDD':>9} {'Trips':>6} {'Calmar':>7}")
    print("-" * 110)
    for r in sub_rows:
        if r[0] == "---":
            print("-" * 110); continue
        print(f"{r[0]:<55} {r[1]:>8.3f} {r[2]:>7.2f}% {r[3]:>7.2f}% {r[4]:>8.2f}% {r[5]:>6d} {r[6]:>7.2f}")
    print("=" * 110)

    # ----- C. Pre-2008 extension: 2002-04 to 2026-05 (24y) -----
    # HYG_stitched goes back to 1980 (VWEHX), TIP stitched from 2000-06.
    # 12-month warmup -> start 2001-06. Use 2002-01 for safety.
    ext_start = pd.Timestamp("2002-01-31")
    ext_end = pd.Timestamp("2026-05-22")
    try:
        bull_e, hs_e, sigs_e = run_bull(panel, ext_start, ext_end)
        ext_rows = [
            metrics_row("M1. No intramonth defense", bull_e, 0),
        ]
        m2es = compute_dd_circuit_scale(bull_e, sigs_e, DD_CIRCUIT_THRESHOLD, DD_CIRCUIT_SCALE)
        m2ep = m2es * bull_e
        ext_rows.append(metrics_row("M2. Sleeve-equity DD-10%", m2ep, int((m2es.diff() < 0).sum())))
        # 13612W and DCH variants
        for label, trig in [
            ("13612W", daily_13612W_trigger(spy_close_full)),
            ("DCH10", daily_dch_trigger(spy_close_full, 10)),
            ("DCH15", daily_dch_trigger(spy_close_full, 15)),
            ("DCH20", daily_dch_trigger(spy_close_full, 20)),
            ("DCH25", daily_dch_trigger(spy_close_full, 25)),
            ("DCH30", daily_dch_trigger(spy_close_full, 30)),
        ]:
            out, trips = apply_circuit(bull_e, hs_e, sigs_e, trig)
            ext_rows.append(metrics_row(label, out, trips))
        print_table(ext_rows, f"C. Pre-2008 extended backtest ({ext_start.date()} to {ext_end.date()}, ~{(ext_end-ext_start).days/365.25:.1f}y)")
    except Exception as e:
        print(f"\nC. Extended backtest failed: {e}")

    # ----- D. Out-of-sample style: pick winner from first half, evaluate on second half -----
    train_s, train_e = pd.Timestamp("2008-04-30"), pd.Timestamp("2017-04-30")
    test_s, test_e = pd.Timestamp("2017-04-30"), pd.Timestamp("2026-05-22")
    bull_tr, hs_tr, sigs_tr = run_bull(panel, train_s, train_e)
    bull_te, hs_te, sigs_te = run_bull(panel, test_s, test_e)

    train_rows = []
    test_rows = []
    candidates = [
        ("M2 sleeve DD-10%", None),
        ("13612W", daily_13612W_trigger(spy_close_full)),
    ] + [(f"DCH{N}", daily_dch_trigger(spy_close_full, N)) for N in [10, 15, 20, 25, 30]]

    for label, trig in candidates:
        if trig is None:
            s_tr = compute_dd_circuit_scale(bull_tr, sigs_tr, DD_CIRCUIT_THRESHOLD, DD_CIRCUIT_SCALE)
            o_tr, t_tr = s_tr * bull_tr, int((s_tr.diff() < 0).sum())
            s_te = compute_dd_circuit_scale(bull_te, sigs_te, DD_CIRCUIT_THRESHOLD, DD_CIRCUIT_SCALE)
            o_te, t_te = s_te * bull_te, int((s_te.diff() < 0).sum())
        else:
            o_tr, t_tr = apply_circuit(bull_tr, hs_tr, sigs_tr, trig)
            o_te, t_te = apply_circuit(bull_te, hs_te, sigs_te, trig)
        train_rows.append(metrics_row(label, o_tr, t_tr))
        test_rows.append(metrics_row(label, o_te, t_te))

    print("\n" + "=" * 110)
    print(f"D. Out-of-sample split: TRAIN {train_s.date()}-{train_e.date()} | TEST {test_s.date()}-{test_e.date()}")
    print("=" * 110)
    print(f"\n  TRAIN window:")
    print(f"  {'Variant':<53} {'Sharpe':>8} {'CAGR':>8} {'Vol':>8} {'MaxDD':>9} {'Trips':>6}")
    print("  " + "-" * 102)
    for r in train_rows:
        print(f"  {r[0]:<53} {r[1]:>8.3f} {r[2]:>7.2f}% {r[3]:>7.2f}% {r[4]:>8.2f}% {r[5]:>6d}")
    print(f"\n  TEST window (out-of-sample):")
    print(f"  {'Variant':<53} {'Sharpe':>8} {'CAGR':>8} {'Vol':>8} {'MaxDD':>9} {'Trips':>6}")
    print("  " + "-" * 102)
    for r in test_rows:
        print(f"  {r[0]:<53} {r[1]:>8.3f} {r[2]:>7.2f}% {r[3]:>7.2f}% {r[4]:>8.2f}% {r[5]:>6d}")
    print("=" * 110)
