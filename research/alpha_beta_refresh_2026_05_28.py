import sys, socket
socket.setdefaulttimeout(15)
sys.path.insert(0, "/Users/rkautsar/personal/scripts/strategy_cpm")

import pandas as pd
import numpy as np
from cpm_live import load_panel, run_cpm_backtest, perf_metrics
from bull_qqq_live import run_bull_qqq_backtest
from ndx_sleeve_live import load_ndx_panel, run_ndx_backtest
from circuit_breaker import compute_lqd_ief_circuit_scale, LQD_IEF_EMA_SPAN
from build_dashboard import (
    bench_aaa_tip, bench_haa_simple, bench_qqq_12mo_trend,
    bench_static_pp_qqq, bench_bb4_blend, alpha_beta_corr
)

def main():
    print("Computing sleeves (current locked spec) ...")
    panel = load_panel(start=pd.Timestamp("1993-01-01"))
    ndx_panel = load_ndx_panel()
    start = pd.Timestamp("2008-04-30")
    end = pd.Timestamp("2026-05-22")

    cpm, _ = run_cpm_backtest(panel, start, end)
    bull_raw = run_bull_qqq_backtest(panel, start, end)
    ndx_raw, _ = run_ndx_backtest(panel, ndx_panel, start, end)
    common = cpm.index.intersection(bull_raw.index).intersection(ndx_raw.index)
    cpm = cpm.reindex(common)
    bull_raw = bull_raw.reindex(common)
    ndx_raw = ndx_raw.reindex(common).fillna(0.0)
    sigs = (pd.DataFrame({"x": 1}, index=cpm.index).groupby(pd.Grouper(freq="ME")).tail(1).index.tolist())

    ndx_scale = compute_lqd_ief_circuit_scale(panel["LQD"], panel["IEF"],
                                                 common, sigs, ema_span=LQD_IEF_EMA_SPAN)
    ndx = ndx_scale * ndx_raw
    bull = bull_raw  # no intramonth circuit
    blend = 0.60 * cpm + 0.20 * bull + 0.20 * ndx

    print("Computing benchmarks ...")
    bench_b2 = bench_aaa_tip(panel, start, end)
    bench_b3 = bench_haa_simple(panel, start, end, asset="SPY")
    bench_b5 = bench_qqq_12mo_trend(panel, start, end)
    bb4_blend = bench_bb4_blend(panel, start, end)
    bb1_blend = 0.60 * bench_b2.reindex(common).fillna(0) + 0.40 * bench_b3.reindex(common).fillna(0)
    static_pp_qqq = bench_static_pp_qqq(panel, start, end, pp_weight=0.80, growth_ticker="QQQ")

    print("\nSleeve standalone (current spec, honest t+1 MOO):")
    for name, s in [
        ("CPM-ext (CLEAN-9)", cpm),
        ("BULL-ext (no circuit)", bull),
        ("NDX raw", ndx_raw),
        ("NDX + LQD/IEF circuit", ndx),
        ("PROD 60/20/20", blend),
        ("BB4 lit", bb4_blend),
        ("BB1 lit", bb1_blend),
    ]:
        m = perf_metrics(s)
        print(f"  {name:<30} Sh={m['sharpe']:.3f} CAGR={m['cagr']*100:.2f}% Vol={m['vol']*100:.2f}% DD={m['max_drawdown']*100:.2f}%")

    print("\n" + "="*120)
    print("ALPHA / BETA / CORR refresh (current locked spec, 2008-04 to 2026-05)")
    print("="*120)
    print(f"{'Strategy':<38} {'Benchmark':<56} {'Alpha (%/yr)':>14} {'Beta':>7} {'Corr':>7}")
    print("-" * 120)

    spy_d = panel["SPY"].ffill().pct_change().loc[start:end].fillna(0.0)
    qqq_d = panel["QQQ"].ffill().pct_change().loc[start:end].fillna(0.0)

    for label, strat, bench, bench_label in [
        ("CPM-ext (CLEAN-9)", cpm, bench_b2, "B2: AAA + TIP canary (CLEAN-9, same universe)"),
        ("BULL-ext (no circuit)", bull, bench_b3, "B3: HAA-Simple SPY"),
        ("PROD 60/20/20", blend, bb4_blend, "BB4: 60 AAA+TIP / 20 HAA-S SPY / 20 QQQ-trend"),
        ("PROD 60/20/20", blend, bb1_blend, "BB1: 60 AAA+TIP / 40 HAA-S SPY"),
        ("PROD 60/20/20", blend, spy_d, "SPY buy-hold"),
        ("PROD 60/20/20", blend, qqq_d, "QQQ buy-hold"),
        ("NDX sleeve (with LQD/IEF circuit)", ndx, qqq_d, "QQQ buy-hold"),
    ]:
        m = alpha_beta_corr(strat, bench)
        print(f"{label:<38} {bench_label:<56} {m['alpha_ann_pct']:>+13.2f}% {m['beta']:>7.3f} {m['corr']:>7.3f}")
    print("="*120)

if __name__ == '__main__':
    main()
