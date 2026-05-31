# RV-Gate Cohort Calibration Findings -- RV_60d (Production-Matching)

Analysis of the Realized-Volatility (RV) gate in the BULL-SPY standalone sleeve, computed on **RV_60d** to match the production gate.

Production gate (`bull_qqq_live._vol_gate_ok`): gate is ON when `RV_60d < RV_252d` (annualized from daily returns). A **blocked month** occurs when both macro `canary_ok` and `spy_trend_ok` are TRUE, but `vol_ok` is FALSE (meaning `RV_60d >= RV_252d`).

`vol_ok` is taken directly from `compute_bull_qqq_weights`, so the cohort split is production-exact (no caveat).

Cohorts split blocked months by the sign of the forward 1-month SPY total return:

- **FALSE-POSITIVE (FP) cohort** (forward SPY > 0): gains the gate forfeited.

- **TRUE-POSITIVE (TP) cohort** (forward SPY <= 0): losses the gate avoided.


## Window: Clean (2008-05-30 to 2026-05-22)

- **Total Evaluated Months**: 216

- **Blocked Months**: 41 (18.98% of total)

- **Unconditional Forward Volatility (mean)**: 16.13% (Median: 12.92%)

- **All-Blocked Forward Volatility (mean)**: 15.28% (Median: 13.13%)

- **FP-cohort vs Unconditional vol contrast**: 12.63% vs 16.13% = **-3.50 pp**


### Cohort Summary (RV_60d gate)

| Cohort | Count | % of Blocked | Mean Fwd SPY Ret | Mean Fwd Vol (Ann) | Median Fwd Vol (Ann) |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **FALSE-POSITIVE (FP)** | 26 | 63.4% | +3.01% | 12.63% | 10.30% |
| **TRUE-POSITIVE (TP)** | 14 | 34.1% | -3.05% | 20.57% | 18.12% |
| **ALL BLOCKED** | 41 | 100.0% | +nan% | 15.28% | 13.13% |
| **UNCONDITIONAL** | 216 | -- | +nan% | 16.13% | 12.92% |

### Expected-Value Decomposition per Blocked Month

- E[forgone] = P(fp) * mean_fp_return = 63.41% * +3.01% = **+1.91%**

- E[avoided] = P(tp) * mean_tp_return = 34.15% * -3.05% = **-1.04%**

- net mean = E[forgone] + E[avoided] = **+0.87%**


## Window: Stress (1999-03-10 to 2026-05-22)

- **Total Evaluated Months**: 326

- **Blocked Months**: 66 (20.25% of total)

- **Unconditional Forward Volatility (mean)**: 16.30% (Median: 13.96%)

- **All-Blocked Forward Volatility (mean)**: 14.76% (Median: 13.08%)

- **FP-cohort vs Unconditional vol contrast**: 12.38% vs 16.30% = **-3.92 pp**


### Cohort Summary (RV_60d gate)

| Cohort | Count | % of Blocked | Mean Fwd SPY Ret | Mean Fwd Vol (Ann) | Median Fwd Vol (Ann) |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **FALSE-POSITIVE (FP)** | 44 | 66.7% | +2.95% | 12.38% | 10.36% |
| **TRUE-POSITIVE (TP)** | 21 | 31.8% | -2.65% | 19.96% | 17.99% |
| **ALL BLOCKED** | 66 | 100.0% | +nan% | 14.76% | 13.08% |
| **UNCONDITIONAL** | 326 | -- | +nan% | 16.30% | 13.96% |

### Expected-Value Decomposition per Blocked Month

- E[forgone] = P(fp) * mean_fp_return = 66.67% * +2.95% = **+1.97%**

- E[avoided] = P(tp) * mean_tp_return = 31.82% * -2.65% = **-0.84%**

- net mean = E[forgone] + E[avoided] = **+1.12%**


## Cross-Check vs RV_20d (Original Study)

RV_20d reference values (from rv_gate_cohort_calibration_findings.md): FP 11.77% clean / 12.10% stress; Unconditional 16.13% clean / 16.30% stress; TP ~20.5%-21.1%.


| Metric | RV_20d | RV_60d | Delta (pp) |
| :--- | :---: | :---: | :---: |
| FP mean fwd vol (clean) | 11.77% | 12.63% | +0.86 |
| FP mean fwd vol (stress) | 12.10% | 12.38% | +0.28 |
| Unconditional mean fwd vol (clean) | 16.13% | 16.13% | -0.00 |
| Unconditional mean fwd vol (stress) | 16.30% | 16.30% | -0.00 |
| TP mean fwd vol (clean) | ~20.5% | 20.57% | -- |
| TP mean fwd vol (stress) | ~21.1% | 19.96% | -- |

## Restated (No Recompute): BULL Factorial Vol-Gate Effect

From the existing factorial in the memo (carried forward verbatim for the fixer):

- V (vol-gate) main effect, clean window: dSharpe +0.081, dCalmar +0.089.

- V x S interaction: +0.143 clean Calmar.


## Notes on Methodology

- Panel loaded from 1995-01-01 (warmup) to 2026-05-22.

- Monthly signal dates = last trading day of each month within the window.

- `vol_ok` sourced from production `compute_bull_qqq_weights` (RV_60d gate), no reimplementation.

- Forward vol = annualized std (sqrt(252)) of daily SPY pct-change from sig_d to next sig_d.

- FP/TP split on forward 1-month SPY total return sign (FP > 0, TP <= 0).
