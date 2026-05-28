"""
Full 60/20/20 benchmark: CPM-ext + BULL-ext + existing NDX.

Uses ndx_sleeve_live.run_ndx_backtest for the NDX series, our new CPM-ext and
BULL-ext from earlier benchmark script for the other two sleeves. Compares to
literature blends.
"""
import sys, socket
socket.setdefaulttimeout(15)
sys.path.insert(0, "/Users/rkautsar/personal/scripts/strategy_cpm")
sys.path.insert(0, "/Users/rkautsar/personal/scripts/strategy_cpm/research")

import pandas as pd
import numpy as np
from cpm_live import load_panel, perf_metrics
from ndx_sleeve_live import load_ndx_panel, run_ndx_backtest
from vol_cap import compute_dd_circuit_scale, DD_CIRCUIT_THRESHOLD, DD_CIRCUIT_SCALE
from benchmark_comparison_2026_05 import (
    run_aaa, run_haa_simple, run_qqq_trend, run_ours_cpm, run_ours_bull,
    alpha_beta_corr, summary, blend, CLEAN7,
)


if __name__ == "__main__":
    panel = load_panel(start=pd.Timestamp("1993-01-01"))
    ndx_panel = load_ndx_panel()
    start = pd.Timestamp("2008-04-30")
    end = pd.Timestamp("2026-05-22")

    print("Running individual strategies...")
    b2 = run_aaa(panel, start, end, CLEAN7, use_canary=True)
    b3 = run_haa_simple(panel, start, end, "SPY")
    b4 = run_haa_simple(panel, start, end, "QQQ")
    b5 = run_qqq_trend(panel, start, end)
    ocpm = run_ours_cpm(panel, start, end)
    obull = run_ours_bull(panel, start, end)
    print("Running NDX sleeve (existing live spec) + applying DD circuit...")
    ondx_raw, _hist = run_ndx_backtest(panel, ndx_panel, start, end)
    sigs = (pd.DataFrame({"x": 1}, index=ondx_raw.index)
            .groupby(pd.Grouper(freq="ME")).tail(1).index.tolist())
    ndx_dd_scale = compute_dd_circuit_scale(ondx_raw, sigs, DD_CIRCUIT_THRESHOLD, DD_CIRCUIT_SCALE)
    ondx = ndx_dd_scale * ondx_raw
    print(f"NDX DD circuit applied (threshold={DD_CIRCUIT_THRESHOLD}, scale={DD_CIRCUIT_SCALE}). Raw vs post-circuit:")
    print(f"  Raw NDX     Sharpe={perf_metrics(ondx_raw)['sharpe']:.3f} | DD={perf_metrics(ondx_raw)['max_drawdown']*100:.2f}%")
    print(f"  Post-circuit Sharpe={perf_metrics(ondx)['sharpe']:.3f} | DD={perf_metrics(ondx)['max_drawdown']*100:.2f}%")

    common = panel.index[(panel.index >= start) & (panel.index <= end)]
    spybh = panel["SPY"].ffill().pct_change().reindex(common).fillna(0.0)
    qqqbh = panel["QQQ"].ffill().pct_change().reindex(common).fillna(0.0)

    print("Running blends...")
    # Literature blends
    bb1 = blend((b2, 0.60), (b3, 0.40))
    bb4 = blend((b2, 0.60), (b3, 0.20), (b5, 0.20))
    # Our blends
    ours_60_40 = blend((ocpm, 0.60), (obull, 0.40))
    ours_60_20_20_ndx = blend((ocpm, 0.60), (obull, 0.20), (ondx, 0.20))
    ours_60_20_20_qqqtrend = blend((ocpm, 0.60), (obull, 0.20), (b5, 0.20))

    rows = []
    rows.append(summary("SPY buy-hold", spybh))
    rows.append(summary("QQQ buy-hold", qqqbh))
    rows.append(("---", 0, 0, 0, 0, 0))
    rows.append(summary("B2: AAA + TIP canary (CLEAN-7)", b2))
    rows.append(summary("B3: HAA-Simple SPY", b3))
    rows.append(summary("B4: HAA-Simple QQQ", b4))
    rows.append(summary("B5: QQQ 12mo trend (Antonacci GEM)", b5))
    rows.append(("---", 0, 0, 0, 0, 0))
    rows.append(summary("OURS CPM-ext (AAA Pair-EW + GPM, CLEAN-7, TIP)", ocpm))
    rows.append(summary("OURS BULL-ext (HAA-S + HYG-OR-TIP + DD-10%)", obull))
    rows.append(summary("NDX sleeve raw (no DD circuit)", ondx_raw))
    rows.append(summary("NDX sleeve + DD-10% circuit (live spec)", ondx))
    rows.append(("---", 0, 0, 0, 0, 0))
    rows.append(summary("BB1: 60% B2 + 40% B3", bb1))
    rows.append(summary("BB4: 60 AAA + 20 HAA-S SPY + 20 QQQ-trend (best lit)", bb4))
    rows.append(("---", 0, 0, 0, 0, 0))
    rows.append(summary("OURS 60/40 (CPM-ext + BULL-ext)", ours_60_40))
    rows.append(summary("OURS 60/20/20 + QQQ-trend", ours_60_20_20_qqqtrend))
    rows.append(summary("OURS 60/20/20 + NDX (NEW HEADLINE)", ours_60_20_20_ndx))

    print("\n" + "=" * 115)
    print("BENCHMARK COMPARISON WITH NDX (2008-04 to 2026-05, 10bps/side, no leverage)")
    print("=" * 115)
    print(f"{'Strategy':<55} {'Sharpe':>8} {'CAGR':>8} {'Vol':>8} {'MaxDD':>9} {'Calmar':>8}")
    print("-" * 115)
    for r in rows:
        if r[0] == "---":
            print("-" * 115); continue
        print(f"{r[0]:<55} {r[1]:>8.3f} {r[2]:>7.2f}% {r[3]:>7.2f}% {r[4]:>8.2f}% {r[5]:>8.2f}")
    print("=" * 115)

    # Alpha/beta against headline benchmark
    pairs = [
        (ours_60_20_20_ndx, bb4, "OURS 60/20/20 + NDX", "vs BB4 (best lit 60/20/20)"),
        (ours_60_20_20_ndx, bb1, "OURS 60/20/20 + NDX", "vs BB1 60/40 simplest"),
        (ours_60_20_20_ndx, spybh, "OURS 60/20/20 + NDX", "vs SPY buy-hold"),
        (ours_60_20_20_ndx, qqqbh, "OURS 60/20/20 + NDX", "vs QQQ buy-hold"),
        (ondx, qqqbh, "NDX sleeve", "vs QQQ buy-hold (closest passive)"),
    ]
    print("\n" + "=" * 115)
    print("ALPHA / BETA / CORR vs BENCHMARKS (headline 60/20/20+NDX focus)")
    print("=" * 115)
    print(f"{'Strategy':<28} {'Benchmark':<55} {'Alpha':>9} {'Beta':>8} {'Corr':>8}")
    print("-" * 115)
    for s, b, sl, bl in pairs:
        a, beta, c = alpha_beta_corr(s, b)
        print(f"{sl:<28} {bl:<55} {a:>+8.2f}% {beta:>8.3f} {c:>8.3f}")
    print("=" * 115)
