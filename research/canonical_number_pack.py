#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Canonical Number Pack Generator
Produces high-precision metrics and benchmark stats matching cpm_dashboard.html.
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import cpm_live as cpm
from build_dashboard import (
    build_artifacts, alpha_beta_corr,
    bench_aaa_tip, bench_haa_simple, bench_qqq_12mo_trend,
    bench_bb4_blend
)
from ndx_sleeve_live import load_ndx_panel

def fmt_pct(v, decimals=2, signed=False):
    if pd.isna(v): return "--"
    sign = "+" if signed and v > 0 else ""
    return f"{sign}{v*100:.{decimals}f}%"

def fmt_num(v, decimals=3, signed=False):
    if pd.isna(v): return "--"
    sign = "+" if signed and v > 0 else ""
    return f"{sign}{v:.{decimals}f}"

def main():
    # Setup dates
    start = pd.Timestamp("2008-05-30")
    ext_start = pd.Timestamp("1999-03-10")
    
    # Load panel
    panel_start = min(start - pd.DateOffset(years=20), pd.Timestamp("1995-01-01"))
    panel = cpm.load_panel(start=panel_start)
    ndx_panel = load_ndx_panel()
    end = panel.index[-1]
    
    cash_daily = panel["SHV"].ffill().pct_change().dropna()
    
    # 1. Clean Window artifacts
    art = build_artifacts(panel, ndx_panel, start, end, include_records=False)
    
    # Standalones
    strategies = {
        "PROD(60/20/20)": art.blend,
        "CPM": art.cpm,
        "BULL-SPY": art.bull,
        "NDX": art.ndx
    }
    
    # Benchmarks
    b2 = bench_aaa_tip(panel, start, end)
    b3 = bench_haa_simple(panel, start, end, asset="SPY")
    bb4 = bench_bb4_blend(panel, start, end)
    
    common_b = b2.index.intersection(b3.index)
    bb1 = 0.60 * b2.reindex(common_b) + 0.40 * b3.reindex(common_b)
    
    spy_d = panel["SPY"].ffill().pct_change().loc[start:end].fillna(0.0)
    qqq_d = panel["QQQ"].ffill().pct_change().loc[start:end].fillna(0.0)
    
    benchmarks = {
        "BB4": bb4,
        "BB1 (0.60*B2+0.40*B3)": bb1,
        "SPY buy-hold": spy_d,
        "QQQ buy-hold": qqq_d
    }
    
    # OLS daily regressions
    pairs = [
        ("CPM vs B2(AAA+TIP)", art.cpm, b2),
        ("BULL vs B3(HAA-Simple SPY)", art.bull, b3),
        ("PROD vs BB4", art.blend, bb4),
        ("PROD vs BB1", art.blend, bb1),
        ("PROD vs SPY", art.blend, spy_d),
        ("PROD vs QQQ", art.blend, qqq_d),
        ("NDX vs QQQ", art.ndx, qqq_d)
    ]
    
    # 2. Deep-history / stress window artifacts
    ext_art = build_artifacts(panel, ndx_panel, ext_start, end, include_records=False)
    
    # Assertions / Cross-Checks
    prod_metrics = cpm.perf_metrics(art.blend, cash_daily)
    ndx_vs_qqq = alpha_beta_corr(art.ndx, qqq_d)
    
    # Cross-checks definitions
    expected_blend_sharpe = 1.503
    expected_blend_cagr = 0.1793
    expected_blend_maxdd = -0.1162
    
    expected_alpha = 24.1544
    expected_beta = 0.3962
    expected_corr = 0.3530
    
    # We allow small tolerances due to floating point or minor version differences
    assert abs(prod_metrics["sharpe"] - expected_blend_sharpe) < 0.05, f"Blend Sharpe {prod_metrics['sharpe']} != {expected_blend_sharpe}"
    assert abs(prod_metrics["cagr"] - expected_blend_cagr) < 0.01, f"Blend CAGR {prod_metrics['cagr']} != {expected_blend_cagr}"
    assert abs(prod_metrics["max_drawdown"] - expected_blend_maxdd) < 0.01, f"Blend MaxDD {prod_metrics['max_drawdown']} != {expected_blend_maxdd}"
    assert abs(ndx_vs_qqq["alpha_ann_pct"] - expected_alpha) < 0.1, f"NDX alpha {ndx_vs_qqq['alpha_ann_pct']} != {expected_alpha}"
    assert abs(ndx_vs_qqq["beta"] - expected_beta) < 0.01, f"NDX beta {ndx_vs_qqq['beta']} != {expected_beta}"
    assert abs(ndx_vs_qqq["corr"] - expected_corr) < 0.01, f"NDX corr {ndx_vs_qqq['corr']} != {expected_corr}"
    
    print("Cross-checks verified successfully!")
    
    print("\n# CANONICAL NUMBER PACK (start=2008-05-30, end={})\n".format(end.strftime("%Y-%m-%d")))
    
    print("## 1. Blend & Sleeves Standalone Performance")
    print("| Strategy | Raw Sharpe | Excess Sharpe (vs SHV) | CAGR | Vol | MaxDD | Calmar |")
    print("| :--- | :---: | :---: | :---: | :---: | :---: | :---: |")
    for name, daily in strategies.items():
        m = cpm.perf_metrics(daily, cash_daily)
        print(f"| {name} | {fmt_num(m['sharpe'])} | {fmt_num(m['excess_sharpe'])} | {fmt_pct(m['cagr'])} | {fmt_pct(m['vol'])} | {fmt_pct(m['max_drawdown'])} | {fmt_num(m['calmar'])} |")
        
    print("\n## 2. Benchmark Performance")
    print("| Benchmark | Raw Sharpe | Excess Sharpe | CAGR | Vol | MaxDD | Calmar |")
    print("| :--- | :---: | :---: | :---: | :---: | :---: | :---: |")
    for name, daily in benchmarks.items():
        m = cpm.perf_metrics(daily, cash_daily)
        print(f"| {name} | {fmt_num(m['sharpe'])} | {fmt_num(m['excess_sharpe'])} | {fmt_pct(m['cagr'])} | {fmt_pct(m['vol'])} | {fmt_pct(m['max_drawdown'])} | {fmt_num(m['calmar'])} |")
        
    print("\n## 3. Alpha / Beta / Correlation (OLS Daily, vs Benchmark)")
    print("| Pair | Alpha (%/yr) | Beta | Correlation |")
    print("| :--- | :---: | :---: | :---: |")
    for name, strat, bench in pairs:
        m = alpha_beta_corr(strat, bench)
        print(f"| {name} | {fmt_pct(m['alpha_ann_pct'] / 100, signed=True)} | {fmt_num(m['beta'])} | {fmt_num(m['corr'])} |")
        
    print("\n## 4. Deep-History / Stress Window (start={}, end={})".format(ext_start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")))
    print("| Strategy | Raw Sharpe | CAGR | MaxDD |")
    print("| :--- | :---: | :---: | :---: |")
    for name, daily in [
        ("PROD(60/20/20)", ext_art.blend),
        ("NDX standalone", ext_art.ndx)
    ]:
        m = cpm.perf_metrics(daily, cash_daily)
        print(f"| {name} | {fmt_num(m['sharpe'])} | {fmt_pct(m['cagr'])} | {fmt_pct(m['max_drawdown'])} |")

if __name__ == "__main__":
    main()
