# -*- coding: utf-8 -*-
"""
Analytical script to compute the exact daily raw Sharpe (0rf) and Excess Sharpe (vs SHV)
for CPM, BULL, NDX, and the 60/20/20 blend across both Clean and Stress windows.
"""
import sys
from pathlib import Path
ROOT = Path('/Users/rkautsar/personal/scripts/strategy_cpm')
sys.path.insert(0, str(ROOT))

import pandas as pd
import numpy as np
import cpm_live as cpm
from bull_qqq_live import run_bull_qqq_backtest
from ndx_sleeve_live import run_ndx_backtest, load_ndx_panel

def calc_stats(r_strategy, r_SHV):
    # Annualized Raw return (for reference)
    raw_mean = r_strategy.mean() * 252
    # Annualized Volatility of raw returns
    raw_vol = r_strategy.std(ddof=0) * np.sqrt(252)
    # Annualized Raw Sharpe (0rf)
    raw_sharpe = raw_mean / raw_vol if raw_vol > 0 else np.nan
    
    # Excess returns vs SHV
    excess_ret = r_strategy - r_SHV
    # Annualized Excess return (for reference)
    excess_mean = excess_ret.mean() * 252
    # Annualized Volatility of excess returns
    excess_vol = excess_ret.std(ddof=0) * np.sqrt(252)
    # Annualized Excess Sharpe (vs SHV)
    excess_sharpe = excess_mean / excess_vol if excess_vol > 0 else np.nan
    
    return {
        'raw_mean': raw_mean,
        'raw_vol': raw_vol,
        'raw_sharpe': raw_sharpe,
        'excess_mean': excess_mean,
        'excess_vol': excess_vol,
        'excess_sharpe': excess_sharpe
    }

def run_window_analysis(panel, ndx_panel, start_date, end_date):
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    
    # Execute backtests
    cpm_raw, _ = cpm.run_cpm_backtest(panel, start, end)
    bull_raw = run_bull_qqq_backtest(panel, start, end)
    ndx_raw, _ = run_ndx_backtest(panel, ndx_panel, start, end)
    
    # Intersection alignment (keep index consistent)
    common = cpm_raw.index.intersection(bull_raw.index).intersection(ndx_raw.index)
    cpm_s = cpm_raw.reindex(common)
    bull_s = bull_raw.reindex(common)
    ndx_s = ndx_raw.reindex(common).fillna(0.0)
    
    # 60/20/20 portfolio blend
    blend_s = 0.60 * cpm_s + 0.20 * bull_s + 0.20 * ndx_s
    
    # Daily returns of SHV (from the loaded panel columns)
    r_SHV = panel['SHV'].ffill().pct_change().reindex(common).fillna(0.0)
    
    strategies = {
        'CPMStandalone': cpm_s,
        'BULLStandalone': bull_s,
        'NDXStandalone': ndx_s,
        'Blend 60/20/20': blend_s
    }
    
    results = {}
    for name, r in strategies.items():
        results[name] = calc_stats(r, r_SHV)
        
    return results

def main():
    print("Loading data panel from 1995-01-01 for signal stability warmup...")
    panel_start = pd.Timestamp('1995-01-01')
    end_date = pd.Timestamp('2026-05-22')
    panel = cpm.load_panel(start=panel_start, end=end_date)
    ndx_panel = load_ndx_panel()
    
    # 1. Clean Window: 2008-04-30 to 2026-05-22
    print("Running backtests for Clean Window (2008-04-30 to 2026-05-22)...")
    clean_results = run_window_analysis(panel, ndx_panel, '2008-04-30', '2026-05-22')
    
    # 2. Stress Window: 1998-06-01 to 2026-05-22
    print("Running backtests for Stress Window (1998-06-01 to 2026-05-22)...")
    stress_results = run_window_analysis(panel, ndx_panel, '1998-06-01', '2026-05-22')
    
    # Comparative Table Output
    print("\n" + "="*95)
    print(f"{'STRATEGY CPM / BULL / NDX PERFORMANCE METRICS SUMMARY':^95}")
    print("="*95)
    print(f"{'Sleeve / Portfolio':<20} | {'Raw Sharpe':>10} | {'Raw Vol':>9} | {'Excess Sharpe':>13} | {'Excess Vol':>11} | {'Excess Return':>13}")
    print("-"*95)
    
    print("CLEAN WINDOW: 2008-04-30 to 2026-05-22")
    print("-"*95)
    for name in ['CPMStandalone', 'BULLStandalone', 'NDXStandalone', 'Blend 60/20/20']:
        res = clean_results[name]
        print(f"{name:<20} | {res['raw_sharpe']:>10.4f} | {res['raw_vol']*100:>8.2f}% | {res['excess_sharpe']:>13.4f} | {res['excess_vol']*100:>10.2f}% | {res['excess_mean']*100:>12.2f}%")
        
    print("-"*95)
    print("STRESS WINDOW: 1998-06-01 to 2026-05-22")
    print("-"*95)
    for name in ['CPMStandalone', 'BULLStandalone', 'NDXStandalone', 'Blend 60/20/20']:
        res = stress_results[name]
        print(f"{name:<20} | {res['raw_sharpe']:>10.4f} | {res['raw_vol']*100:>8.2f}% | {res['excess_sharpe']:>13.4f} | {res['excess_vol']*100:>10.2f}% | {res['excess_mean']*100:>12.2f}%")
    print("="*95)

if __name__ == '__main__':
    main()
