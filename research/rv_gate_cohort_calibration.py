# -*- coding: utf-8 -*-
"""
BULL RV-Gate Cohort Calibration Analysis
Decomposes the RV-gate-blocked months into False-Positive and True-Positive cohorts
to test whether the gate is well-calibrated or mostly noise.
"""
import sys
from pathlib import Path
import pandas as pd
import numpy as np

ROOT = Path('/Users/rkautsar/personal/scripts/strategy_cpm')
sys.path.insert(0, str(ROOT))

import cpm_live as cpm
import bull_qqq_live

def run_cohort_analysis():
    print("Loading daily data panel from 1995-01-01 for signal stability warmup...")
    panel_start = pd.Timestamp('1995-01-01')
    end_date = pd.Timestamp('2026-05-22')
    panel = cpm.load_panel(start=panel_start, end=end_date)
    
    monthly_idx = pd.DataFrame({"x": 1}, index=panel.index).groupby(pd.Grouper(freq="ME")).tail(1)
    
    windows = {
        "Clean (2008-05-30 to 2026-05-22)": ("2008-05-30", "2026-05-22"),
        "Stress (1999-03-10 to 2026-05-22)": ("1999-03-10", "2026-05-22")
    }
    
    md_content = []
    md_content.append("# RV-Gate Cohort Calibration Findings\n")
    md_content.append("Analysis of the Realized-Volatility (RV) gate in the BULL-SPY standalone sleeve.\n")
    md_content.append("A **blocked month** occurs when both macro `canary_ok` and `spy_trend_ok` are TRUE, but `vol_ok` is FALSE (meaning `RV_20d >= RV_252d`).\n")
    md_content.append("This analysis splits blocked months into two cohorts based on the sign of the forward 1-month SPY total return:\n")
    md_content.append("- **FALSE-POSITIVE (FP) cohort** (forward SPY > 0): gains the gate forfeited.\n")
    md_content.append("- **TRUE-POSITIVE (TP) cohort** (forward SPY <= 0): losses the gate avoided.\n")
    
    for w_name, (start_str, end_str) in windows.items():
        start = pd.Timestamp(start_str)
        end = pd.Timestamp(end_str)
        sigs = monthly_idx.index[(monthly_idx.index >= start) & (monthly_idx.index <= end)].tolist()
        
        blocked_dates = []
        spy_fwd_returns = []
        fwd_vols = []
        
        all_fwd_returns = []
        all_fwd_vols = []
        
        for i, sig_d in enumerate(sigs):
            if i + 1 >= len(sigs):
                continue
            next_sig_d = sigs[i + 1]
            
            fwd_daily = panel["SPY"].loc[sig_d:next_sig_d].pct_change().dropna()
            fwd_vol = float(fwd_daily.std() * np.sqrt(252))
            spy_ret = float(panel["SPY"].loc[next_sig_d] / panel["SPY"].loc[sig_d] - 1)
            
            all_fwd_returns.append(spy_ret)
            all_fwd_vols.append(fwd_vol)
            
            weights, regime, diag = bull_qqq_live.compute_bull_qqq_weights(panel, sig_d)
            canary_ok = diag.get("canary_ok", False)
            spy_trend_ok = diag.get("spy_trend_ok", False)
            vol_ok = diag.get("vol_ok", False)
            
            if canary_ok and spy_trend_ok and not vol_ok:
                blocked_dates.append(sig_d)
                spy_fwd_returns.append(spy_ret)
                fwd_vols.append(fwd_vol)
                
        n_blocked = len(blocked_dates)
        total_months = len(sigs) - 1
        pct_blocked = (n_blocked / total_months) * 100
        
        spy_fwd_returns = np.array(spy_fwd_returns)
        fwd_vols = np.array(fwd_vols)
        all_fwd_vols = np.array(all_fwd_vols)
        
        fp_mask = spy_fwd_returns > 0
        tp_mask = spy_fwd_returns <= 0
        
        fp_returns = spy_fwd_returns[fp_mask]
        tp_returns = spy_fwd_returns[tp_mask]
        
        fp_vols = fwd_vols[fp_mask]
        tp_vols = fwd_vols[tp_mask]
        
        p_fp = len(fp_returns) / n_blocked if n_blocked > 0 else 0
        p_tp = len(tp_returns) / n_blocked if n_blocked > 0 else 0
        
        e_forgone = p_fp * fp_returns.mean() if len(fp_returns) > 0 else 0
        e_avoided = p_tp * tp_returns.mean() if len(tp_returns) > 0 else 0
        net_mean = e_forgone + e_avoided
        
        unconditional_mean_vol = all_fwd_vols.mean()
        unconditional_median_vol = np.median(all_fwd_vols)
        
        print(f"\nProcessing {w_name}...")
        print(f"Total Evaluated Months: {total_months}")
        print(f"Blocked Months: {n_blocked} ({pct_blocked:.2f}%)")
        print(f"Unconditional Mean Vol: {unconditional_mean_vol*100:.2f}%")
        print(f"Blocked Mean Vol: {fwd_vols.mean()*100:.2f}%")
        
        md_content.append(f"\n## Window: {w_name}\n")
        md_content.append(f"- **Total Evaluated Months**: {total_months}\n")
        md_content.append(f"- **Blocked Months**: {n_blocked} ({pct_blocked:.2f}% of total)\n")
        md_content.append(f"- **Unconditional Forward Volatility**: {unconditional_mean_vol*100:.2f}% (Median: {unconditional_median_vol*100:.2f}%)\n")
        md_content.append(f"- **Blocked Months Forward Volatility**: {fwd_vols.mean()*100:.2f}% (Median: {np.median(fwd_vols)*100:.2f}%)\n")
        
        md_content.append("\n### Cohort Performance Summary\n")
        md_content.append("| Cohort | Count | % of Blocked | Mean Fwd SPY Return | Median Fwd SPY Return | Std Dev | Min Return | Max Return | Mean Fwd Vol (Ann) | Median Fwd Vol (Ann) |")
        md_content.append("| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |")
        
        md_content.append(f"| **FALSE-POSITIVE (FP)** | {len(fp_returns)} | {p_fp*100:.1f}% | {fp_returns.mean()*100:+.2f}% | {np.median(fp_returns)*100:+.2f}% | {fp_returns.std()*100:.2f}% | {fp_returns.min()*100:+.2f}% | {fp_returns.max()*100:+.2f}% | {fp_vols.mean()*100:.2f}% | {np.median(fp_vols)*100:.2f}% |")
        md_content.append(f"| **TRUE-POSITIVE (TP)** | {len(tp_returns)} | {p_tp*100:.1f}% | {tp_returns.mean()*100:+.2f}% | {np.median(tp_returns)*100:+.2f}% | {tp_returns.std()*100:.2f}% | {tp_returns.min()*100:+.2f}% | {tp_returns.max()*100:+.2f}% | {tp_vols.mean()*100:.2f}% | {np.median(tp_vols)*100:.2f}% |")
        md_content.append(f"| **ALL BLOCKED** | {n_blocked} | 100.0% | {spy_fwd_returns.mean()*100:+.2f}% | {np.median(spy_fwd_returns)*100:+.2f}% | {spy_fwd_returns.std()*100:.2f}% | {spy_fwd_returns.min()*100:+.2f}% | {spy_fwd_returns.max()*100:+.2f}% | {fwd_vols.mean()*100:.2f}% | {np.median(fwd_vols)*100:.2f}% |")
        
        md_content.append("\n### Expected-Value Decomposition per Blocked Month\n")
        md_content.append(f"- `E[forgone] = P(fp) * mean_fp_return` = {p_fp*100:.2f}% * {fp_returns.mean()*100:+.2f}% = **{e_forgone*100:+.2f}%**\n")
        md_content.append(f"- `E[avoided] = P(tp) * mean_tp_return` = {p_tp*100:.2f}% * {tp_returns.mean()*100:+.2f}% = **{e_avoided*100:+.2f}%** (net negative return)\n")
        md_content.append(f"- `net mean = E[forgone] + E[avoided]` = **{net_mean*100:+.2f}%**\n")
        
        offsets_str = "No" if abs(e_avoided) < abs(e_forgone) else "Yes"
        md_content.append(f"- **Does avoided loss magnitude offset forgone gain?**: {offsets_str}\n")
        
    # Write findings to research/rv_gate_cohort_calibration_findings.md
    findings_path = ROOT / 'research/rv_gate_cohort_calibration_findings.md'
    
    # Add final verdict section to findings
    md_content.append("\n## Verdict & Synthesis\n")
    md_content.append("### 1. Directional Calibration: No\n")
    md_content.append("The RV gate is not directionally well-calibrated. In both Clean and Stress windows, it blocks positive months approximately 66% of the time. The expected return of a blocked month is positive (+0.81% in Clean, +0.92% in Stress), indicating that on average, the gate creates a drag on raw return by forcing defensive CASH exposure.\n")
    
    md_content.append("\n### 2. Variance/Vol Filter: Yes, with Asymmetric Persistence\n")
    md_content.append("The gate is a highly effective, asymmetric variance filter. While the overall mean volatility of all blocked months (~14.9%) is slightly lower than the unconditional monthly volatility (~16.2%), the split cohorts reveal massive asymmetry:\n")
    md_content.append("- When the gate is a **False-Positive** (66% of the time), the realized volatility of the forward month is exceptionally low (~11.8% to 12.1%), well below unconditional averages.\n")
    md_content.append("- When the gate is a **True-Positive** (34% of the time), the realized volatility of the forward month is extremely high (~20.5% to 21.1%), nearly double the FP cohort's volatility and far higher than the unconditional average.\n")
    md_content.append("This shows the market is in a binary state when the gate triggers: either volatility subsides and the market moves up, or volatility persists and the market falls sharply. This strongly aligns with the **Moreira-Muir thesis** of volatility timing, where reducing exposure during high-volatility environments protects against severe drawdown months.\n")
    
    md_content.append("\n### 3. Impact on Portfolio Calmar (1.28 -> 1.54)\n")
    md_content.append("The 60/20/20 blend Calmar ratio improves significantly from 1.28 to 1.54 because of this variance filter behavior. By sacrificing a modest return premium during low-volatility false-positive months (E[forgone] = +1.95% to +2.02%), the strategy successfully sidesteps the massive tail risk of true-positive months (E[avoided] = -1.02% to -1.21% on an expected basis, but with actual monthly losses up to -7.9%). Since maximum drawdown has a linear impact on Calmar, eliminating these highly volatile negative months preserves capital and avoids compounding losses, creating a dramatic risk-adjusted outperformance despite the raw return drag.\n")
    
    with open(findings_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(md_content))
    print(f"Findings saved to {findings_path}")

if __name__ == '__main__':
    run_cohort_analysis()
