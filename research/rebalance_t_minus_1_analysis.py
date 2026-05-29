# -*- coding: utf-8 -*-
"""
Rebalance T-1 vs T Signal and Return Impact Analysis.
This script compares the monthly rebalance decisions computed at signal date T-1
versus T across CPM, BULL_QQQ, and NDX sleeves, and computes the realized return
impact of using T-1 signals at T+0 close compared to the production T-signal rebalance.
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np
import warnings

# Suppress warnings for clean output
warnings.filterwarnings('ignore')

ROOT = Path('/Users/rkautsar/personal/scripts/strategy_cpm')
sys.path.insert(0, str(ROOT))

import cpm_live as cpm
import bull_qqq_live as bull
import ndx_sleeve_live as ndx

def get_prior_trading_day(index, date):
    date = pd.Timestamp(date)
    prior_dates = index[index < date]
    if len(prior_dates) == 0:
        return date
    return prior_dates[-1]

def run_analysis():
    print("Loading daily close price panels...")
    # Load panels from 1995-01-01 for signal stability warmup
    panel = cpm.load_panel(start=pd.Timestamp('1995-01-01'), end=pd.Timestamp('2026-05-22'))
    ndx_panel = ndx.load_ndx_panel()
    idx = panel.index

    # Find month-end rebalance dates T in Clean window: 2008-05-30 to 2026-05-22
    monthly_idx = pd.DataFrame({'x': 1}, index=idx).groupby(pd.Grouper(freq='ME')).tail(1).index
    dates = monthly_idx[(monthly_idx >= '2008-05-30') & (monthly_idx <= '2026-05-22')].tolist()
    total_months = len(dates)
    print(f"Analyzing {total_months} months from {dates[0].date()} to {dates[-1].date()}\n")

    # Mappings for monkey patching backtest
    rebalance_dates_map = {}
    for d in dates:
        rebalance_dates_map[d] = get_prior_trading_day(idx, d)

    # Sleeve target decision comparisons
    cpm_diff_count = 0
    bull_active_flip_count = 0
    ndx_pick_diff_count = 0
    any_diff_count = 0

    # BULL gates change tracking
    bull_canary_diff_count = 0
    bull_trend_diff_count = 0
    bull_vol_diff_count = 0

    # NDX names changed tracking
    ndx_changes = []
    ndx_sym_diffs = []
    ndx_regime_diff_count = 0

    print("Computing and comparing target decisions at T and T-1...")
    for T in dates:
        T1 = rebalance_dates_map[T]

        # 1. CPM Decision
        w_t, pair_t, regime_t, safe_t = cpm.compute_target_weights(panel, T)
        w_t1, pair_t1, regime_t1, safe_t1 = cpm.compute_target_weights(panel, T1)
        
        cpm_diff = (w_t != w_t1) or (regime_t != regime_t1)
        if cpm_diff:
            cpm_diff_count += 1

        # 2. BULL Decision
        bull_w_t, bull_regime_t, bull_diag_t = bull.compute_bull_qqq_weights(panel, T)
        bull_w_t1, bull_regime_t1, bull_diag_t1 = bull.compute_bull_qqq_weights(panel, T1)

        active_t = any(w > 0 for ticker, w in bull_w_t.items() if ticker == "SPY")
        active_t1 = any(w > 0 for ticker, w in bull_w_t1.items() if ticker == "SPY")
        bull_active_flip = (active_t != active_t1)
        if bull_active_flip:
            bull_active_flip_count += 1

        # Track gate changes
        if bull_diag_t.get("canary_ok") != bull_diag_t1.get("canary_ok"):
            bull_canary_diff_count += 1
        if bull_diag_t.get("spy_trend_ok") != bull_diag_t1.get("spy_trend_ok"):
            bull_trend_diff_count += 1
        if bull_diag_t.get("vol_ok") != bull_diag_t1.get("vol_ok"):
            bull_vol_diff_count += 1

        # 3. NDX Decision
        ndx_w_t, ndx_regime_t, ndx_diag_t = ndx.compute_ndx_weights(panel, ndx_panel, T)
        ndx_w_t1, ndx_regime_t1, ndx_diag_t1 = ndx.compute_ndx_weights(panel, ndx_panel, T1)

        sel_t = set(ndx_diag_t.get("selected", []))
        sel_t1 = set(ndx_diag_t1.get("selected", []))

        if not sel_t and not sel_t1:
            jaccard = 1.0
        else:
            jaccard = len(sel_t & sel_t1) / len(sel_t | sel_t1)

        ndx_pick_diff = (jaccard < 1.0)
        if ndx_pick_diff:
            ndx_pick_diff_count += 1
            ndx_changes.append(len(sel_t1 - sel_t))
            ndx_sym_diffs.append(len(sel_t1 ^ sel_t))
        
        ndx_reg_active_t = (ndx_regime_t != "GATE_OFF (BULL_defensive)")
        ndx_reg_active_t1 = (ndx_regime_t1 != "GATE_OFF (BULL_defensive)")
        if ndx_reg_active_t != ndx_reg_active_t1:
            ndx_regime_diff_count += 1

        # 4. ANY Decision Differs (Union)
        if cpm_diff or bull_active_flip or ndx_pick_diff:
            any_diff_count += 1

    # Print decision comparison results
    print("\n" + "="*80)
    print(f"{'REBALANCE SIGNAL DECISION MISMATCH RATES (T-1 vs T)':^80}")
    print("="*80)
    print(f"Total months analyzed: {total_months}")
    print(f"CPM decision differs (any change in assets/regime): {cpm_diff_count:3d} / {total_months:3d} ({cpm_diff_count/total_months*100:6.2f}%)")
    print(f"BULL active-state flips (SPY vs safe asset):         {bull_active_flip_count:3d} / {total_months:3d} ({bull_active_flip_count/total_months*100:6.2f}%)")
    print(f"  - Canary gate change rate:                        {bull_canary_diff_count:3d} / {total_months:3d} ({bull_canary_diff_count/total_months*100:6.2f}%)")
    print(f"  - Trend gate change rate:                         {bull_trend_diff_count:3d} / {total_months:3d} ({bull_trend_diff_count/total_months*100:6.2f}%)")
    print(f"  - Volatility gate change rate:                    {bull_vol_diff_count:3d} / {total_months:3d} ({bull_vol_diff_count/total_months*100:6.2f}%)")
    print(f"NDX pick-set differs (Jaccard < 1.0):                {ndx_pick_diff_count:3d} / {total_months:3d} ({ndx_pick_diff_count/total_months*100:6.2f}%)")
    mean_changes = np.mean(ndx_changes) if ndx_changes else 0.0
    mean_sym_diff = np.mean(ndx_sym_diffs) if ndx_sym_diffs else 0.0
    print(f"  - Mean names dropped & replaced (when differs):   {mean_changes:4.2f} / 5")
    print(f"  - Mean size of symmetric difference (when diff):  {mean_sym_diff:4.2f} / 10")
    print(f"  - NDX regime change rate (active vs safe):        {ndx_regime_diff_count:3d} / {total_months:3d} ({ndx_regime_diff_count/total_months*100:6.2f}%)")
    print(f"ANY sleeve decision differs (Union):                 {any_diff_count:3d} / {total_months:3d} ({any_diff_count/total_months*100:6.2f}%)")
    print("="*80 + "\n")


    # Realized Return Impact Analysis via Backtest Simulations
    print("Running return impact simulations...")
    start_dt = pd.Timestamp('2008-05-30')
    end_dt = pd.Timestamp('2026-05-22')

    # (a) Original T-signal/T+1-MOO
    cpm_ret_a, _ = cpm.run_cpm_backtest(panel, start_dt, end_dt)
    bull_ret_a = bull.run_bull_qqq_backtest(panel, start_dt, end_dt)
    ndx_ret_a, _ = ndx.run_ndx_backtest(panel, ndx_panel, start_dt, end_dt)

    common_a = cpm_ret_a.index.intersection(bull_ret_a.index).intersection(ndx_ret_a.index)
    cpm_s_a = cpm_ret_a.reindex(common_a)
    bull_s_a = bull_ret_a.reindex(common_a)
    ndx_s_a = ndx_ret_a.reindex(common_a).fillna(0.0)
    blend_s_a = 0.60 * cpm_s_a + 0.20 * bull_s_a + 0.20 * ndx_s_a


    # (b) Patched T-1-signal applied at T+0 close
    # Monkey-patch the decision functions
    print("Applying monkey patches for T-1 signal backtest simulation...")
    
    # Save original functions
    orig_compute_target_weights = cpm.compute_target_weights
    orig_compute_bull_weights = bull.compute_bull_qqq_weights
    orig_compute_ndx_weights = ndx.compute_ndx_weights

    # Define patch implementations
    def patched_cpm_weights(close_panel, sig_d, *args, **kwargs):
        if sig_d in rebalance_dates_map:
            sig_d = rebalance_dates_map[sig_d]
        return orig_compute_target_weights(close_panel, sig_d, *args, **kwargs)

    def patched_bull_weights(close_panel, sig_d, *args, **kwargs):
        if sig_d in rebalance_dates_map:
            sig_d = rebalance_dates_map[sig_d]
        return orig_compute_bull_weights(close_panel, sig_d, *args, **kwargs)

    def patched_ndx_weights(cpm_panel, ndx_panel, sig_d, *args, **kwargs):
        if sig_d in rebalance_dates_map:
            sig_d = rebalance_dates_map[sig_d]
        return orig_compute_ndx_weights(cpm_panel, ndx_panel, sig_d, *args, **kwargs)

    # Inject patches
    cpm.compute_target_weights = patched_cpm_weights
    bull.compute_bull_qqq_weights = patched_bull_weights
    ndx.compute_ndx_weights = patched_ndx_weights

    try:
        cpm_ret_b, _ = cpm.run_cpm_backtest(panel, start_dt, end_dt)
        bull_ret_b = bull.run_bull_qqq_backtest(panel, start_dt, end_dt)
        ndx_ret_b, _ = ndx.run_ndx_backtest(panel, ndx_panel, start_dt, end_dt)
    finally:
        # ALWAYS restore original functions in case of exceptions
        cpm.compute_target_weights = orig_compute_target_weights
        bull.compute_bull_qqq_weights = orig_compute_bull_weights
        ndx.compute_ndx_weights = orig_compute_ndx_weights

    common_b = cpm_ret_b.index.intersection(bull_ret_b.index).intersection(ndx_ret_b.index)
    cpm_s_b = cpm_ret_b.reindex(common_b)
    bull_s_b = bull_ret_b.reindex(common_b)
    ndx_s_b = ndx_ret_b.reindex(common_b).fillna(0.0)
    blend_s_b = 0.60 * cpm_s_b + 0.20 * bull_s_b + 0.20 * ndx_s_b

    # Find common dates for comparison between a and b
    common_all = blend_s_a.index.intersection(blend_s_b.index)
    b_a = blend_s_a.reindex(common_all)
    b_b = blend_s_b.reindex(common_all)

    # Cash daily for excess returns
    r_SHV = panel['SHV'].ffill().pct_change().reindex(common_all).fillna(0.0)

    # Calculate statistics
    stats_a = cpm.perf_metrics(b_a, r_SHV)
    stats_b = cpm.perf_metrics(b_b, r_SHV)

    # Tracking Difference: Daily return difference std annualized
    daily_diff = b_a - b_b
    tracking_diff = daily_diff.std(ddof=0) * np.sqrt(252)

    # Generate and print performance tables
    print("\n" + "="*95)
    print(f"{'REALIZED RETURN IMPACT ANALYSIS (60/20/20 BLEND)':^95}")
    print("="*95)
    print(f"{'Metric':<25} | {'(a) Production (T-sig/T+1-MOO)':<30} | {'(b) Proposed (T-1-sig/T+0-MOC)*':<30}")
    print("-"*95)
    print(f"{'CAGR':<25} | {stats_a['cagr']*100:>28.2f}% | {stats_b['cagr']*100:>28.2f}%")
    print(f"{'Annualized Volatility':<25} | {stats_a['vol']*100:>28.2f}% | {stats_b['vol']*100:>28.2f}%")
    print(f"{'Raw Sharpe (0rf)':<25} | {stats_a['sharpe']:>29.4f} | {stats_b['sharpe']:>29.4f}")
    print(f"{'Excess Sharpe (vs SHV)':<25} | {stats_a['excess_sharpe']:>29.4f} | {stats_b['excess_sharpe']:>29.4f}")
    print(f"{'Max Drawdown':<25} | {stats_a['max_drawdown']*100:>28.2f}% | {stats_b['max_drawdown']*100:>28.2f}%")
    print(f"{'Calmar Ratio':<25} | {stats_a['calmar']:>29.4f} | {stats_b['calmar']:>29.4f}")
    print(f"{'Ulcer Index':<25} | {stats_a['ulcer']:>29.4f} | {stats_b['ulcer']:>29.4f}")
    print(f"{'Martin Ratio':<25} | {stats_a['martin']:>29.4f} | {stats_b['martin']:>29.4f}")
    print("-"*95)
    print(f"Annualized Tracking Difference: {tracking_diff*100:.2f}%")
    print(f"*Note: Modeling of (b) approximates T+0 MOC via close-to-close from T.")
    print("="*95 + "\n")

    # Save to log file
    log_path = Path('/Users/rkautsar/personal/scripts/strategy_cpm/research/rebalance_t_minus_1_analysis.log')
    with open(log_path, 'w') as f:
        f.write("="*80 + "\n")
        f.write(f"{'REBALANCE SIGNAL DECISION MISMATCH RATES (T-1 vs T)':^80}\n")
        f.write("="*80 + "\n")
        f.write(f"Total months analyzed: {total_months}\n")
        f.write(f"CPM decision differs (any change in assets/regime): {cpm_diff_count:3d} / {total_months:3d} ({cpm_diff_count/total_months*100:6.2f}%)\n")
        f.write(f"BULL active-state flips (SPY vs safe asset):         {bull_active_flip_count:3d} / {total_months:3d} ({bull_active_flip_count/total_months*100:6.2f}%)\n")
        f.write(f"  - Canary gate change rate:                        {bull_canary_diff_count:3d} / {total_months:3d} ({bull_canary_diff_count/total_months*100:6.2f}%)\n")
        f.write(f"  - Trend gate change rate:                         {bull_trend_diff_count:3d} / {total_months:3d} ({bull_trend_diff_count/total_months*100:6.2f}%)\n")
        f.write(f"  - Volatility gate change rate:                    {bull_vol_diff_count:3d} / {total_months:3d} ({bull_vol_diff_count/total_months*100:6.2f}%)\n")
        f.write(f"NDX pick-set differs (Jaccard < 1.0):                {ndx_pick_diff_count:3d} / {total_months:3d} ({ndx_pick_diff_count/total_months*100:6.2f}%)\n")
        f.write(f"  - Mean names dropped & replaced (when differs):   {mean_changes:4.2f} / 5\n")
        f.write(f"  - Mean size of symmetric difference (when diff):  {mean_sym_diff:4.2f} / 10\n")
        f.write(f"  - NDX regime change rate (active vs safe):        {ndx_regime_diff_count:3d} / {total_months:3d} ({ndx_regime_diff_count/total_months*100:6.2f}%)\n")
        f.write(f"ANY sleeve decision differs (Union):                 {any_diff_count:3d} / {total_months:3d} ({any_diff_count/total_months*100:6.2f}%)\n")
        f.write("="*80 + "\n\n")

        f.write("="*95 + "\n")
        f.write(f"{'REALIZED RETURN IMPACT ANALYSIS (60/20/20 BLEND)':^95}\n")
        f.write("="*95 + "\n")
        f.write(f"{'Metric':<25} | {'(a) Production (T-sig/T+1-MOO)':<30} | {'(b) Proposed (T-1-sig/T+0-MOC)*':<30}\n")
        f.write("-"*95 + "\n")
        f.write(f"{'CAGR':<25} | {stats_a['cagr']*100:>28.2f}% | {stats_b['cagr']*100:>28.2f}%\n")
        f.write(f"{'Annualized Volatility':<25} | {stats_a['vol']*100:>28.2f}% | {stats_b['vol']*100:>28.2f}%\n")
        f.write(f"{'Raw Sharpe (0rf)':<25} | {stats_a['sharpe']:>29.4f} | {stats_b['sharpe']:>29.4f}\n")
        f.write(f"{'Excess Sharpe (vs SHV)':<25} | {stats_a['excess_sharpe']:>29.4f} | {stats_b['excess_sharpe']:>29.4f}\n")
        f.write(f"{'Max Drawdown':<25} | {stats_a['max_drawdown']*100:>28.2f}% | {stats_b['max_drawdown']*100:>28.2f}%\n")
        f.write(f"{'Calmar Ratio':<25} | {stats_a['calmar']:>29.4f} | {stats_b['calmar']:>29.4f}\n")
        f.write(f"{'Ulcer Index':<25} | {stats_a['ulcer']:>29.4f} | {stats_b['ulcer']:>29.4f}\n")
        f.write(f"{'Martin Ratio':<25} | {stats_a['martin']:>29.4f} | {stats_b['martin']:>29.4f}\n")
        f.write("-"*95 + "\n")
        f.write(f"Annualized Tracking Difference: {tracking_diff*100:.2f}%\n")
        f.write(f"*Note: Modeling of (b) approximates T+0 MOC via close-to-close from T.\n")
        f.write("="*95 + "\n")
    print(f"Results successfully saved to {log_path}")

if __name__ == '__main__':
    run_analysis()
