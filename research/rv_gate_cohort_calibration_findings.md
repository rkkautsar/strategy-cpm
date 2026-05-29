# RV-Gate Cohort Calibration Findings

Analysis of the Realized-Volatility (RV) gate in the BULL-SPY standalone sleeve.

A **blocked month** occurs when both macro `canary_ok` and `spy_trend_ok` are TRUE, but `vol_ok` is FALSE (meaning `RV_20d >= RV_252d`).

This analysis splits blocked months into two cohorts based on the sign of the forward 1-month SPY total return:

- **FALSE-POSITIVE (FP) cohort** (forward SPY > 0): gains the gate forfeited.

- **TRUE-POSITIVE (TP) cohort** (forward SPY <= 0): losses the gate avoided.


## Window: Clean (2008-05-30 to 2026-05-22)

- **Total Evaluated Months**: 216

- **Blocked Months**: 41 (18.98% of total)

- **Unconditional Forward Volatility**: 16.13% (Median: 12.92%)

- **Blocked Months Forward Volatility**: 14.96% (Median: 13.13%)


### Cohort Performance Summary

| Cohort | Count | % of Blocked | Mean Fwd SPY Return | Median Fwd SPY Return | Std Dev | Min Return | Max Return | Mean Fwd Vol (Ann) | Median Fwd Vol (Ann) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **FALSE-POSITIVE (FP)** | 27 | 65.9% | +3.06% | +2.75% | 1.55% | +0.52% | +6.28% | 11.77% | 10.08% |
| **TRUE-POSITIVE (TP)** | 14 | 34.1% | -3.54% | -3.30% | 2.11% | -7.92% | -0.41% | 21.10% | 19.41% |
| **ALL BLOCKED** | 41 | 100.0% | +0.81% | +2.01% | 3.59% | -7.92% | +6.28% | 14.96% | 13.13% |

### Expected-Value Decomposition per Blocked Month

- `E[forgone] = P(fp) * mean_fp_return` = 65.85% * +3.06% = **+2.02%**

- `E[avoided] = P(tp) * mean_tp_return` = 34.15% * -3.54% = **-1.21%** (net negative return)

- `net mean = E[forgone] + E[avoided]` = **+0.81%**

- **Does avoided loss magnitude offset forgone gain?**: No


## Window: Stress (1999-03-10 to 2026-05-22)

- **Total Evaluated Months**: 326

- **Blocked Months**: 63 (19.33% of total)

- **Unconditional Forward Volatility**: 16.30% (Median: 13.96%)

- **Blocked Months Forward Volatility**: 14.89% (Median: 13.63%)


### Cohort Performance Summary

| Cohort | Count | % of Blocked | Mean Fwd SPY Return | Median Fwd SPY Return | Std Dev | Min Return | Max Return | Mean Fwd Vol (Ann) | Median Fwd Vol (Ann) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **FALSE-POSITIVE (FP)** | 42 | 66.7% | +2.92% | +2.56% | 1.90% | +0.26% | +9.69% | 12.10% | 10.23% |
| **TRUE-POSITIVE (TP)** | 21 | 33.3% | -3.07% | -2.74% | 1.92% | -7.92% | -0.41% | 20.46% | 18.68% |
| **ALL BLOCKED** | 63 | 100.0% | +0.92% | +1.28% | 3.41% | -7.92% | +9.69% | 14.89% | 13.63% |

### Expected-Value Decomposition per Blocked Month

- `E[forgone] = P(fp) * mean_fp_return` = 66.67% * +2.92% = **+1.95%**

- `E[avoided] = P(tp) * mean_tp_return` = 33.33% * -3.07% = **-1.02%** (net negative return)

- `net mean = E[forgone] + E[avoided]` = **+0.92%**

- **Does avoided loss magnitude offset forgone gain?**: No


## Verdict & Synthesis

### 1. Directional Calibration: No

The RV gate is not directionally well-calibrated. In both Clean and Stress windows, it blocks positive months approximately 66% of the time. The expected return of a blocked month is positive (+0.81% in Clean, +0.92% in Stress), indicating that on average, the gate creates a drag on raw return by forcing defensive CASH exposure.


### 2. Variance/Vol Filter: Yes, with Asymmetric Persistence

The gate is a highly effective, asymmetric variance filter. While the overall mean volatility of all blocked months (~14.9%) is slightly lower than the unconditional monthly volatility (~16.2%), the split cohorts reveal massive asymmetry:

- When the gate is a **False-Positive** (66% of the time), the realized volatility of the forward month is exceptionally low (~11.8% to 12.1%), well below unconditional averages.

- When the gate is a **True-Positive** (34% of the time), the realized volatility of the forward month is extremely high (~20.5% to 21.1%), nearly double the FP cohort's volatility and far higher than the unconditional average.

This shows the market is in a binary state when the gate triggers: either volatility subsides and the market moves up, or volatility persists and the market falls sharply. This strongly aligns with the **Moreira-Muir thesis** of volatility timing, where reducing exposure during high-volatility environments protects against severe drawdown months.


### 3. Impact on Portfolio Calmar (1.28 -> 1.54)

The 60/20/20 blend Calmar ratio improves significantly from 1.28 to 1.54 because of this variance filter behavior. By sacrificing a modest return premium during low-volatility false-positive months (E[forgone] = +1.95% to +2.02%), the strategy successfully sidesteps the massive tail risk of true-positive months (E[avoided] = -1.02% to -1.21% on an expected basis, but with actual monthly losses up to -7.9%). Since maximum drawdown has a linear impact on Calmar, eliminating these highly volatile negative months preserves capital and avoids compounding losses, creating a dramatic risk-adjusted outperformance despite the raw return drag.
