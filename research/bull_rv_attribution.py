# -*- coding: utf-8 -*-
"""
BULL Realized-Volatility Gate Attribution Analysis
Computes performance metrics with and without the RV gate for BULL and the 60/20/20 portfolio.
Counts blocked months and analyzes V-shaped rebound episodes.
"""
import sys
from pathlib import Path
import pandas as pd
import numpy as np

ROOT = Path('/Users/rkautsar/personal/scripts/strategy_cpm')
sys.path.insert(0, str(ROOT))

import cpm_live as cpm
import bull_qqq_live
from ndx_sleeve_live import run_ndx_backtest, load_ndx_panel

# ----------------- MONKEY-PATCHING FOR TOGGLING RV GATE -----------------
original_vol_gate_ok = bull_qqq_live._vol_gate_ok
RV_GATE_ACTIVE = True

def patched_vol_gate_ok(daily_spy, sig_d):
    vol_ok_actual, diag = original_vol_gate_ok(daily_spy, sig_d)
    if not RV_GATE_ACTIVE:
        diag["vol_ok_actual_before_patch"] = vol_ok_actual
        diag["vol_ok"] = True
        return True, diag
    else:
        return vol_ok_actual, diag

bull_qqq_live._vol_gate_ok = patched_vol_gate_ok

def run_backtest_suite(panel, ndx_panel, start_date, end_date, rv_active):
    global RV_GATE_ACTIVE
    RV_GATE_ACTIVE = rv_active
    
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    
    # Run backtests
    cpm_raw, _ = cpm.run_cpm_backtest(panel, start, end)
    bull_raw = bull_qqq_live.run_bull_qqq_backtest(panel, start, end)
    ndx_raw, _ = run_ndx_backtest(panel, ndx_panel, start, end)
    
    # Align indices
    common = cpm_raw.index.intersection(bull_raw.index).intersection(ndx_raw.index)
    cpm_s = cpm_raw.reindex(common)
    bull_s = bull_raw.reindex(common)
    ndx_s = ndx_raw.reindex(common).fillna(0.0)
    
    blend_s = 0.60 * cpm_s + 0.20 * bull_s + 0.20 * ndx_s
    
    # Load cash for excess return calculation
    cash_daily = panel['SHV'].ffill().pct_change().reindex(common).fillna(0.0)
    
    return {
        "cpm": cpm_s,
        "bull": bull_s,
        "ndx": ndx_s,
        "blend": blend_s,
        "cash": cash_daily
    }

def compute_metrics(strategy_rets, cash_rets):
    m = cpm.perf_metrics(strategy_rets, cash_rets)
    # Re-calculate or format clean fields
    return {
        "cagr": m.get("cagr", np.nan),
        "vol": m.get("vol", np.nan),
        "raw_sharpe": m.get("sharpe", np.nan),
        "excess_sharpe": m.get("excess_sharpe", np.nan),
        "max_dd": m.get("max_drawdown", np.nan),
        "calmar": m.get("calmar", np.nan)
    }

def main():
    print("Loading data panel from 1995-01-01 for signal stability warmup...")
    panel_start = pd.Timestamp('1995-01-01')
    end_date = pd.Timestamp('2026-05-22')
    panel = cpm.load_panel(start=panel_start, end=end_date)
    ndx_panel = load_ndx_panel()
    
    windows = {
        "Clean (2008-05-30 to 2026-05-22)": ("2008-05-30", "2026-05-22"),
        "Stress (1998-06-01 to 2026-05-22)": ("1998-06-01", "2026-05-22")
    }
    
    all_results = {}
    
    for w_name, (start_d, end_d) in windows.items():
        print(f"\nProcessing {w_name}...")
        # Config A: RV Gate Active
        res_a = run_backtest_suite(panel, ndx_panel, start_d, end_d, rv_active=True)
        # Config B: RV Gate Disabled
        res_b = run_backtest_suite(panel, ndx_panel, start_d, end_d, rv_active=False)
        
        all_results[w_name] = {
            "a": res_a,
            "b": res_b
        }
    
    # ----------------- PART 1: PERFORMANCE TABLES -----------------
    print("\n" + "="*95)
    print(f"{'BULL VOLATILITY GATE ATTRIBUTION METRICS SUMMARY':^95}")
    print("="*95)
    
    for w_name in windows.keys():
        print(f"\nWINDOW: {w_name}")
        print("-"*105)
        print(f"{'Strategy / Config':<45} | {'CAGR':>8} | {'Vol':>7} | {'Raw SR':>8} | {'Excess SR':>9} | {'MaxDD':>8} | {'Calmar':>7}")
        print("-"*105)
        
        res_a = all_results[w_name]["a"]
        res_b = all_results[w_name]["b"]
        
        # BULL Standalone
        m_bull_a = compute_metrics(res_a["bull"], res_a["cash"])
        m_bull_b = compute_metrics(res_b["bull"], res_b["cash"])
        print(f"{'BULL Standalone (a) [With RV Gate]':<45} | {m_bull_a['cagr']*100:>7.2f}% | {m_bull_a['vol']*100:>6.2f}% | {m_bull_a['raw_sharpe']:>8.4f} | {m_bull_a['excess_sharpe']:>9.4f} | {m_bull_a['max_dd']*100:>7.2f}% | {m_bull_a['calmar']:>7.3f}")
        print(f"{'BULL Standalone (b) [No RV Gate]':<45} | {m_bull_b['cagr']*100:>7.2f}% | {m_bull_b['vol']*100:>6.2f}% | {m_bull_b['raw_sharpe']:>8.4f} | {m_bull_b['excess_sharpe']:>9.4f} | {m_bull_b['max_dd']*100:>7.2f}% | {m_bull_b['calmar']:>7.3f}")
        print("-"*105)
        
        # Full Blend
        m_blend_a = compute_metrics(res_a["blend"], res_a["cash"])
        m_blend_b = compute_metrics(res_b["blend"], res_b["cash"])
        print(f"{'Full 60/20/20 Blend (a) [With RV Gate]':<45} | {m_blend_a['cagr']*100:>7.2f}% | {m_blend_a['vol']*100:>6.2f}% | {m_blend_a['raw_sharpe']:>8.4f} | {m_blend_a['excess_sharpe']:>9.4f} | {m_blend_a['max_dd']*100:>7.2f}% | {m_blend_a['calmar']:>7.3f}")
        print(f"{'Full 60/20/20 Blend (b) [No RV Gate]':<45} | {m_blend_b['cagr']*100:>7.2f}% | {m_blend_b['vol']*100:>6.2f}% | {m_blend_b['raw_sharpe']:>8.4f} | {m_blend_b['excess_sharpe']:>9.4f} | {m_blend_b['max_dd']*100:>7.2f}% | {m_blend_b['calmar']:>7.3f}")
        print("-"*105)
    
    # ----------------- PART 2: BLOCKED MONTHS ANALYSIS -----------------
    print("\n" + "="*95)
    print(f"{'BLOCKED MONTHS ANALYSIS (CANARY OK AND TREND OK BUT VOL BLOCKED)':^95}")
    print("="*95)
    
    # Let's perform diagnostics over the entire period to count blocked months and calculate forward returns
    monthly_idx = pd.DataFrame({"x": 1}, index=panel.index).groupby(pd.Grouper(freq="ME")).tail(1)
    
    for w_name, (start_d, end_d) in windows.items():
        start = pd.Timestamp(start_d)
        end = pd.Timestamp(end_d)
        sigs = monthly_idx.index[(monthly_idx.index >= start) & (monthly_idx.index <= end)].tolist()
        
        blocked_dates = []
        spy_fwd_returns = []
        shv_fwd_returns = []
        excess_fwd_returns = []
        
        # Set RV gate active to make sure compute_bull_qqq_weights calculates original/actual values
        global RV_GATE_ACTIVE
        RV_GATE_ACTIVE = True
        
        for i, sig_d in enumerate(sigs):
            if i + 1 >= len(sigs):
                continue # Skip last signal as we cannot compute forward 1-month return
            
            weights, regime, diag = bull_qqq_live.compute_bull_qqq_weights(panel, sig_d)
            
            canary_ok = diag.get("canary_ok", False)
            spy_trend_ok = diag.get("spy_trend_ok", False)
            vol_ok = diag.get("vol_ok", False)
            
            # Check if RV gate is the binding constraint
            if canary_ok and spy_trend_ok and not vol_ok:
                next_sig_d = sigs[i + 1]
                spy_ret = panel["SPY"].loc[next_sig_d] / panel["SPY"].loc[sig_d] - 1
                shv_ret = panel["SHV"].loc[next_sig_d] / panel["SHV"].loc[sig_d] - 1
                excess_ret = spy_ret - shv_ret
                
                blocked_dates.append(sig_d)
                spy_fwd_returns.append(spy_ret)
                shv_fwd_returns.append(shv_ret)
                excess_fwd_returns.append(excess_ret)
        
        n_blocked = len(blocked_dates)
        total_months = len(sigs) - 1
        pct_blocked = (n_blocked / total_months) * 100 if total_months > 0 else 0
        
        print(f"\nWindow: {w_name}")
        print(f"Total evaluated months: {total_months}")
        print(f"Number of blocked months: {n_blocked} ({pct_blocked:.1f}%)")
        
        if n_blocked > 0:
            spy_fwd_returns = np.array(spy_fwd_returns)
            shv_fwd_returns = np.array(shv_fwd_returns)
            excess_fwd_returns = np.array(excess_fwd_returns)
            
            neg_pct = (spy_fwd_returns < 0).sum() / n_blocked * 100
            excess_neg_pct = (excess_fwd_returns < 0).sum() / n_blocked * 100
            
            print(f"Forward 1-Month SPY returns for blocked months:")
            print(f"  Mean return:    {spy_fwd_returns.mean()*100:+.2f}%")
            print(f"  Median return:  {np.median(spy_fwd_returns)*100:+.2f}%")
            print(f"  % Negative:     {neg_pct:.1f}%")
            print(f"Forward 1-Month SPY excess return over cash (SHV) for blocked months:")
            print(f"  Mean return:    {excess_fwd_returns.mean()*100:+.2f}%")
            print(f"  Median return:  {np.median(excess_fwd_returns)*100:+.2f}%")
            print(f"  % Negative:     {excess_neg_pct:.1f}%")
            
            print("\nBlocked dates list and forward returns:")
            print(f"  {'Signal Date':<12} | {'SPY Fwd Ret':>11} | {'SHV Fwd Ret':>11} | {'Saved Return':>12}")
            print("  " + "-"*56)
            for d, s_ret, h_ret, e_ret in zip(blocked_dates, spy_fwd_returns, shv_fwd_returns, excess_fwd_returns):
                # Saved return is cash return - SPY return (the amount avoided)
                saved_ret = h_ret - s_ret
                print(f"  {str(d.date()):<12} | {s_ret*100:>10.2f}% | {h_ret*100:>10.2f}% | {saved_ret*100:>+11.2f}%")
        else:
            print("No blocked months found in this window.")
            
    # ----------------- PART 3: REBOUND BEHAVIOR EPISODES -----------------
    print("\n" + "="*95)
    print(f"{'V-SHAPED REBOUND BEHAVIOR EPISODES':^95}")
    print("="*95)
    
    episodes = {
        "2018Q4 Drawdown & Recovery": ("2018-08-31", "2019-04-30"),
        "2020 March COVID Crash": ("2020-01-31", "2020-08-31"),
        "2022 Bear Market": ("2021-11-30", "2023-04-30")
    }
    
    for ep_name, (start_d, end_d) in episodes.items():
        print(f"\nEpisode: {ep_name} ({start_d} to {end_d})")
        print("-"*105)
        print(f"{'Signal Date':<12} | {'Canary':<6} | {'Trend':<6} | {'Vol OK':<6} | {'Config A State':<18} | {'Config B State':<18} | {'SPY Month Ret':>13}")
        print("-"*105)
        
        start = pd.Timestamp(start_d)
        end = pd.Timestamp(end_d)
        sigs = monthly_idx.index[(monthly_idx.index >= start) & (monthly_idx.index <= end)].tolist()
        
        for i, sig_d in enumerate(sigs):
            # Compute monthly parameters
            weights_a, regime_a, diag_a = bull_qqq_live.compute_bull_qqq_weights(panel, sig_d)
            
            canary_ok = diag_a.get("canary_ok", False)
            spy_trend_ok = diag_a.get("spy_trend_ok", False)
            vol_ok = diag_a.get("vol_ok", False)
            
            # Config A holding
            hold_a = "BULL" if regime_a.startswith("BULL_") else "CASH"
            # Config B holding (vol_ok is forced to True)
            hold_b = "BULL" if (canary_ok and spy_trend_ok) else "CASH"
            
            # Compute return for current month (i.e. forward return from this signal if next exists, or backward return from prior)
            if i + 1 < len(sigs):
                next_sig_d = sigs[i + 1]
                spy_ret = panel["SPY"].loc[next_sig_d] / panel["SPY"].loc[sig_d] - 1
                spy_ret_str = f"{spy_ret*100:>+12.2f}%"
            else:
                spy_ret_str = f"{'N/A':>13}"
                
            print(f"{str(sig_d.date()):<12} | {'OK' if canary_ok else 'OFF':<6} | {'OK' if spy_trend_ok else 'OFF':<6} | {'OK' if vol_ok else 'OFF':<6} | {hold_a:<18} | {hold_b:<18} | {spy_ret_str}")
        print("-"*105)

if __name__ == '__main__':
    main()
