#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Analytical script to calculate exact daily Raw Sharpe (0rf) and Excess Sharpe (vs SHV)
for the five README benchmarks over the Clean window (2008-05-30 to 2026-05-22).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd
import numpy as np
import cpm_live as cpm
from ndx_sleeve_live import load_ndx_panel
from build_dashboard import (
    build_artifacts,
    bench_aaa_tip,
    bench_haa_simple,
    bench_bb4_blend
)

def main():
    print("Loading data panel from 1995-01-01 for signal stability warmup...")
    panel_start = pd.Timestamp('1995-01-01')
    end_date = pd.Timestamp('2026-05-22')
    panel = cpm.load_panel(start=panel_start, end=end_date)
    ndx_panel = load_ndx_panel()
    
    start = pd.Timestamp('2008-05-30')
    end = pd.Timestamp('2026-05-22')
    
    print("Computing strategy daily returns over the Clean window...")
    # 1. PROD (blend of CPM, BULL, NDX)
    art = build_artifacts(panel, ndx_panel, start, end)
    prod = art.blend
    
    # 2. BB4 (bench_bb4_blend)
    bb4 = bench_bb4_blend(panel, start, end)
    
    # 3. BB1 (0.60 * B2 + 0.40 * B3)
    b2 = bench_aaa_tip(panel, start, end)
    b3 = bench_haa_simple(panel, start, end, asset="SPY")
    common_b1 = b2.index.intersection(b3.index)
    bb1 = 0.60 * b2.reindex(common_b1).fillna(0.0) + 0.40 * b3.reindex(common_b1).fillna(0.0)
    
    # 4. SPY buy-hold
    spy = panel['SPY'].ffill().pct_change().loc[start:end].fillna(0.0)
    
    # 5. QQQ buy-hold
    qqq = panel['QQQ'].ffill().pct_change().loc[start:end].fillna(0.0)
    
    # Align SHV return
    shv = panel['SHV'].ffill().pct_change().loc[start:end].fillna(0.0)
    
    # Confirm identical indices and align them
    common_all = prod.index.intersection(bb4.index).intersection(bb1.index).intersection(spy.index).intersection(qqq.index).intersection(shv.index)
    
    strategies = {
        "PROD 60/20/20": prod.reindex(common_all),
        "BB4 (60% B2 + 20% B3 + 20% B5)": bb4.reindex(common_all),
        "BB1 (60% B2 + 40% B3)": bb1.reindex(common_all),
        "SPY buy-hold": spy.reindex(common_all),
        "QQQ buy-hold": qqq.reindex(common_all)
    }
    
    shv_aligned = shv.reindex(common_all)
    
    rows = []
    for name, r in strategies.items():
        m = cpm.perf_metrics(r, shv_aligned)
        rows.append({
            "Strategy": name,
            "Raw Sharpe": f"{m['sharpe']:.4f}",
            "Excess Sharpe": f"{m['excess_sharpe']:.4f}",
            "CAGR": f"{m['cagr']*100:.2f}%",
            "Vol": f"{m['vol']*100:.2f}%",
            "MaxDD": f"{m['max_drawdown']*100:.2f}%",
            "Calmar": f"{m['calmar']:.4f}"
        })
        
    headers = ["Strategy", "Raw Sharpe", "Excess Sharpe", "CAGR", "Vol", "MaxDD", "Calmar"]
    col_widths = {h: len(h) for h in headers}
    for row in rows:
        for h in headers:
            col_widths[h] = max(col_widths[h], len(row[h]))
            
    header_row = "| " + " | ".join(h.ljust(col_widths[h]) if h == "Strategy" else h.rjust(col_widths[h]) for h in headers) + " |"
    separator_row = "| " + " | ".join("-" * col_widths[h] for h in headers) + " |"
    data_rows = []
    for row in rows:
        data_rows.append("| " + " | ".join(row[h].ljust(col_widths[h]) if h == "Strategy" else row[h].rjust(col_widths[h]) for h in headers) + " |")
        
    markdown_table = "\n".join([header_row, separator_row] + data_rows)
    
    print("\n" + "="*80)
    print(f"BENCHMARKS PERFORMANCE SUMMARY: CLEAN WINDOW ({start.date()} to {end.date()})")
    print("="*80)
    print(markdown_table)
    print("="*80 + "\n")
    
    # Also write to a markdown file
    out_path = ROOT / "research" / "benchmark_sharpe_analysis_results.md"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(f"# Benchmark Performance Summary (Clean Window: {start.date()} to {end.date()})\n\n")
        f.write(markdown_table)
        f.write("\n")
    print(f"Results successfully saved to {out_path}")

if __name__ == '__main__':
    main()
