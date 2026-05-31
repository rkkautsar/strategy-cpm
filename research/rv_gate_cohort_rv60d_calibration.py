# -*- coding: utf-8 -*-
"""
BULL RV-Gate Cohort Calibration Analysis -- RV_60d (PRODUCTION-MATCHING).

Identical methodology to research/rv_gate_cohort_calibration.py, except the
vol gate is the PRODUCTION gate computed on RV_60d (the engine's
_vol_gate_ok uses rv_60 < rv_252). The original study text described
RV_20d; production has since swapped RV_20d -> RV_60d. This harness pulls
vol_ok directly from bull_qqq_live.compute_bull_qqq_weights so the cohort
split matches production exactly.

Cohort definition (unchanged from original):
- A BLOCKED month occurs when canary_ok AND spy_trend_ok are TRUE but
  vol_ok is FALSE (production gate: RV_60d >= RV_252d).
- FALSE-POSITIVE (FP) cohort: forward 1-month SPY total return > 0.
- TRUE-POSITIVE  (TP) cohort: forward 1-month SPY total return <= 0.
- Forward vol: annualized std of daily SPY pct-change from sig_d to the
  next monthly signal date (sqrt(252)).
- Unconditional baseline: all evaluated months in the window.
"""
import sys
import json
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
        "Stress (1999-03-10 to 2026-05-22)": ("1999-03-10", "2026-05-22"),
    }

    results = {}
    md = []
    md.append("# RV-Gate Cohort Calibration Findings -- RV_60d (Production-Matching)\n")
    md.append("Analysis of the Realized-Volatility (RV) gate in the BULL-SPY standalone sleeve, "
              "computed on **RV_60d** to match the production gate.\n")
    md.append("Production gate (`bull_qqq_live._vol_gate_ok`): gate is ON when `RV_60d < RV_252d` "
              "(annualized from daily returns). A **blocked month** occurs when both macro `canary_ok` "
              "and `spy_trend_ok` are TRUE, but `vol_ok` is FALSE (meaning `RV_60d >= RV_252d`).\n")
    md.append("`vol_ok` is taken directly from `compute_bull_qqq_weights`, so the cohort split is "
              "production-exact (no caveat).\n")
    md.append("Cohorts split blocked months by the sign of the forward 1-month SPY total return:\n")
    md.append("- **FALSE-POSITIVE (FP) cohort** (forward SPY > 0): gains the gate forfeited.\n")
    md.append("- **TRUE-POSITIVE (TP) cohort** (forward SPY <= 0): losses the gate avoided.\n")

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
        pct_blocked = (n_blocked / total_months) * 100 if total_months else 0

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

        uncond_mean_vol = float(all_fwd_vols.mean())
        uncond_median_vol = float(np.median(all_fwd_vols))

        fp_mean_vol = float(fp_vols.mean()) if len(fp_vols) else float('nan')
        tp_mean_vol = float(tp_vols.mean()) if len(tp_vols) else float('nan')
        fp_vs_uncond = fp_mean_vol - uncond_mean_vol

        results[w_name] = {
            "window": [start_str, end_str],
            "total_evaluated_months": total_months,
            "blocked_months": n_blocked,
            "pct_blocked": pct_blocked,
            "unconditional_mean_fwd_vol": uncond_mean_vol,
            "unconditional_median_fwd_vol": uncond_median_vol,
            "all_blocked_mean_fwd_vol": float(fwd_vols.mean()) if len(fwd_vols) else float('nan'),
            "fp": {
                "count": int(len(fp_returns)),
                "pct_of_blocked": p_fp,
                "mean_fwd_return": float(fp_returns.mean()) if len(fp_returns) else float('nan'),
                "mean_fwd_vol": fp_mean_vol,
                "median_fwd_vol": float(np.median(fp_vols)) if len(fp_vols) else float('nan'),
            },
            "tp": {
                "count": int(len(tp_returns)),
                "pct_of_blocked": p_tp,
                "mean_fwd_return": float(tp_returns.mean()) if len(tp_returns) else float('nan'),
                "mean_fwd_vol": tp_mean_vol,
                "median_fwd_vol": float(np.median(tp_vols)) if len(tp_vols) else float('nan'),
            },
            "fp_vs_unconditional_vol_delta": fp_vs_uncond,
            "ev_decomposition": {
                "e_forgone": float(e_forgone),
                "e_avoided": float(e_avoided),
                "net_mean": float(net_mean),
            },
        }

        print(f"\n{w_name}")
        print(f"  Total months: {total_months}  Blocked: {n_blocked} ({pct_blocked:.2f}%)")
        print(f"  Unconditional mean fwd vol: {uncond_mean_vol*100:.2f}%")
        print(f"  FP mean fwd vol: {fp_mean_vol*100:.2f}%  TP mean fwd vol: {tp_mean_vol*100:.2f}%")
        print(f"  FP - Unconditional: {fp_vs_uncond*100:+.2f} pp")

        md.append(f"\n## Window: {w_name}\n")
        md.append(f"- **Total Evaluated Months**: {total_months}\n")
        md.append(f"- **Blocked Months**: {n_blocked} ({pct_blocked:.2f}% of total)\n")
        md.append(f"- **Unconditional Forward Volatility (mean)**: {uncond_mean_vol*100:.2f}% "
                  f"(Median: {uncond_median_vol*100:.2f}%)\n")
        md.append(f"- **All-Blocked Forward Volatility (mean)**: {fwd_vols.mean()*100:.2f}% "
                  f"(Median: {np.median(fwd_vols)*100:.2f}%)\n")
        md.append(f"- **FP-cohort vs Unconditional vol contrast**: {fp_mean_vol*100:.2f}% vs "
                  f"{uncond_mean_vol*100:.2f}% = **{fp_vs_uncond*100:+.2f} pp**\n")

        md.append("\n### Cohort Summary (RV_60d gate)\n")
        md.append("| Cohort | Count | % of Blocked | Mean Fwd SPY Ret | Mean Fwd Vol (Ann) | Median Fwd Vol (Ann) |")
        md.append("| :--- | :---: | :---: | :---: | :---: | :---: |")
        md.append(f"| **FALSE-POSITIVE (FP)** | {len(fp_returns)} | {p_fp*100:.1f}% | "
                  f"{fp_returns.mean()*100:+.2f}% | {fp_mean_vol*100:.2f}% | {np.median(fp_vols)*100:.2f}% |")
        md.append(f"| **TRUE-POSITIVE (TP)** | {len(tp_returns)} | {p_tp*100:.1f}% | "
                  f"{tp_returns.mean()*100:+.2f}% | {tp_mean_vol*100:.2f}% | {np.median(tp_vols)*100:.2f}% |")
        md.append(f"| **ALL BLOCKED** | {n_blocked} | 100.0% | {spy_fwd_returns.mean()*100:+.2f}% | "
                  f"{fwd_vols.mean()*100:.2f}% | {np.median(fwd_vols)*100:.2f}% |")
        md.append(f"| **UNCONDITIONAL** | {total_months} | -- | {np.array(all_fwd_returns).mean()*100:+.2f}% | "
                  f"{uncond_mean_vol*100:.2f}% | {uncond_median_vol*100:.2f}% |")

        md.append("\n### Expected-Value Decomposition per Blocked Month\n")
        md.append(f"- E[forgone] = P(fp) * mean_fp_return = {p_fp*100:.2f}% * {fp_returns.mean()*100:+.2f}% "
                  f"= **{e_forgone*100:+.2f}%**\n")
        md.append(f"- E[avoided] = P(tp) * mean_tp_return = {p_tp*100:.2f}% * {tp_returns.mean()*100:+.2f}% "
                  f"= **{e_avoided*100:+.2f}%**\n")
        md.append(f"- net mean = E[forgone] + E[avoided] = **{net_mean*100:+.2f}%**\n")

    # RV_20d reference values (original study) for cross-check.
    rv20_ref = {
        "fp_clean": 0.1177, "fp_stress": 0.1210,
        "uncond_clean": 0.1613, "uncond_stress": 0.1630,
        "tp_clean_low": 0.205, "tp_stress_high": 0.211,
    }

    md.append("\n## Cross-Check vs RV_20d (Original Study)\n")
    md.append("RV_20d reference values (from rv_gate_cohort_calibration_findings.md): "
              "FP 11.77% clean / 12.10% stress; Unconditional 16.13% clean / 16.30% stress; "
              "TP ~20.5%-21.1%.\n")
    clean = results.get("Clean (2008-05-30 to 2026-05-22)")
    stress = results.get("Stress (1999-03-10 to 2026-05-22)")
    if clean and stress:
        md.append("\n| Metric | RV_20d | RV_60d | Delta (pp) |")
        md.append("| :--- | :---: | :---: | :---: |")
        md.append(f"| FP mean fwd vol (clean) | 11.77% | {clean['fp']['mean_fwd_vol']*100:.2f}% | "
                  f"{(clean['fp']['mean_fwd_vol']-rv20_ref['fp_clean'])*100:+.2f} |")
        md.append(f"| FP mean fwd vol (stress) | 12.10% | {stress['fp']['mean_fwd_vol']*100:.2f}% | "
                  f"{(stress['fp']['mean_fwd_vol']-rv20_ref['fp_stress'])*100:+.2f} |")
        md.append(f"| Unconditional mean fwd vol (clean) | 16.13% | {clean['unconditional_mean_fwd_vol']*100:.2f}% | "
                  f"{(clean['unconditional_mean_fwd_vol']-rv20_ref['uncond_clean'])*100:+.2f} |")
        md.append(f"| Unconditional mean fwd vol (stress) | 16.30% | {stress['unconditional_mean_fwd_vol']*100:.2f}% | "
                  f"{(stress['unconditional_mean_fwd_vol']-rv20_ref['uncond_stress'])*100:+.2f} |")
        md.append(f"| TP mean fwd vol (clean) | ~20.5% | {clean['tp']['mean_fwd_vol']*100:.2f}% | -- |")
        md.append(f"| TP mean fwd vol (stress) | ~21.1% | {stress['tp']['mean_fwd_vol']*100:.2f}% | -- |")

    md.append("\n## Restated (No Recompute): BULL Factorial Vol-Gate Effect\n")
    md.append("From the existing factorial in the memo (carried forward verbatim for the fixer):\n")
    md.append("- V (vol-gate) main effect, clean window: dSharpe +0.081, dCalmar +0.089.\n")
    md.append("- V x S interaction: +0.143 clean Calmar.\n")

    md.append("\n## Notes on Methodology\n")
    md.append("- Panel loaded from 1995-01-01 (warmup) to 2026-05-22.\n")
    md.append("- Monthly signal dates = last trading day of each month within the window.\n")
    md.append("- `vol_ok` sourced from production `compute_bull_qqq_weights` (RV_60d gate), no reimplementation.\n")
    md.append("- Forward vol = annualized std (sqrt(252)) of daily SPY pct-change from sig_d to next sig_d.\n")
    md.append("- FP/TP split on forward 1-month SPY total return sign (FP > 0, TP <= 0).\n")

    findings_md = ROOT / 'research/rv_gate_cohort_rv60d_findings.md'
    findings_json = ROOT / 'research/rv_gate_cohort_rv60d_findings.json'
    with open(findings_md, 'w', encoding='utf-8') as f:
        f.write("\n".join(md))
    with open(findings_json, 'w', encoding='utf-8') as f:
        json.dump({
            "gate": "RV_60d < RV_252d (production)",
            "rv20_reference": rv20_ref,
            "factorial_restated": {
                "V_main_clean_dSharpe": 0.081,
                "V_main_clean_dCalmar": 0.089,
                "VxS_clean_dCalmar": 0.143,
            },
            "windows": results,
        }, f, indent=2)
    print(f"\nFindings saved to {findings_md}")
    print(f"JSON saved to {findings_json}")
    return results


if __name__ == '__main__':
    run_cohort_analysis()
