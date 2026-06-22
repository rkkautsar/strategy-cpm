# Regime B Stress Blend Experiment — Results

## Overview

Four variants were tested over the full backtest period (2008-06 to 2026-04, 17 years):

| # | Variant | Trigger | 
|---|---------|---------|
| 1 | Baseline | Never (always normal weights) |
| 2 | Sahm stress | SahmREALTIME >= 0.50 (current production) |
| 3 | Regime B stress | SPY 12m return <= 0 OR realized vol in top tercile |
| 4 | Hybrid | Regime B OR Sahm fires |

Normal weights: CPM=60%, NDX=15%, VAL=15%, RPV=10%
Stress weights: CPM=60%, NDX=7.5%, VAL=7.5%, RPV=25%

Signal at month-end, applied T+1, 10bps/side cost.

---

## Overall Metrics

| Variant | CAGR | Vol | Sharpe | MaxDD | Calmar | Stress Days |
|---------|------|-----|--------|-------|--------|-------------|
| Baseline | 16.53% | 10.09% | 1.0720 | -9.48% | 1.74 | 0d |
| Sahm stress | 16.03% | 9.52% | 1.0848 | -7.07% | 2.27 | 840d |
| Regime B stress | 15.79% | 9.72% | 1.0426 | -9.48% | 1.67 | 1448d |
| Hybrid | 15.64% | 9.43% | 1.0576 | -7.07% | 2.21 | 1699d |
| Golden Master (prod) | 16.05% | 9.53% | 1.0847 | -7.07% | 2.27 | (matches Sahm) |

**Key finding**: Sahm stress (current production) achieves the best Sharpe and Calmar. Regime B and Hybrid degrade risk-adjusted performance despite more frequent RPV overweighting.

---

## Signal Frequency

| Signal | Dates | % of Total |
|--------|-------|-----------|
| Sahm stress | 40/215 | 18.6% |
| Regime B stress | 69/215 | 32.1% |
| Hybrid | 81/215 | 37.7% |
| Overlap | 28/215 | 13.0% |

### Sahm fires only in:
- **2008-06 to 2010-06** (GFC, 25 dates)
- **2020-05 to 2021-04** (COVID recovery, 12 dates)
- **2024-08 to 2024-10** (3 dates)

### Regime B adds:
- **2010-06 to 2012-06** (Eurozone crisis / slow recovery)
- **2015-09 to 2016-04** (China scare / growth scare)
- **2018-04, 2018-05** (Feb 2018 vol event aftermath)
- **2018-12 to 2019-03** (Q4 2018 vol event)
- **2022-03 to 2023-04** (Rate hike cycle, all 14 dates)
- **2025-05 to 2025-07** (beyond eval window)

### Regime B missed:
- **2010-01 to 2010-05** Sahm-only period (Sahm still elevated from GFC)

---

## Annual Returns (Focus Years)

| Variant | 2018 | 2020 | 2022 | 2025 |
|---------|------|------|------|------|
| Baseline | +9.47% | +35.23% | -0.95% | +30.12% |
| Sahm stress | +9.47% | +27.08% | -0.95% | +30.12% |
| Regime B stress | +9.56% | +27.45% | -1.36% | +28.28% |
| Hybrid | +9.56% | +27.45% | -1.36% | +28.28% |

Note: Sahm stress doesn't fire in 2018 or 2022, so those years are identical to baseline.

---

## Stress Window Returns

| Window | Baseline | Sahm | Regime B | Hybrid |
|--------|----------|------|----------|--------|
| Oct 2018 | -2.99% | -2.99% | -2.99% | -2.99% |
| Mar 2020 (COVID crash) | +2.57% | +2.57% | +2.57% | +2.57% |
| Jan-Oct 2022 | -1.41% | -1.41% | -1.44% | -1.44% |
| Apr 2025 (+0.04% all) | +0.04% | +0.04% | +0.04% | +0.04% |

All stress windows show minimal-to-no differentiation because:
- The signals fire AFTER the crisis onset (month-end + T+1 application)
- The RPV sleeve doesn't significantly diverge from NDX/VAL in window-level returns

---

## Monthly Difference Analysis (vs Baseline)

| Variant | Months Different | Mean Diff | | Max Up | Max Down |
|---------|-----------------|-----------|---------|--------|---------|
| Sahm stress | 43/216 | -0.20% | 1.32% | -2.86% |
| Regime B stress | 80/216 | -0.15% | 1.32% | -2.86% |
| Hybrid | 92/216 | -0.16% | 1.32% | -2.86% |

---

## Turnover

| Variant | Rebalances | Total Turnover | Annual Turnover |
|---------|-----------|---------------|----------------|
| Baseline | 214 | 0.000 | 0.000 |
| Sahm stress | 214 | 1.800 | 0.101 |
| Regime B stress | 214 | 6.600 | 0.369 |
| Hybrid | 214 | 6.600 | 0.369 |

---

## Conclusions

### 1. Sahm stress outperforms both Regime B alternatives.
Current production (Sahm stress) delivers Sharpe 1.085, MaxDD -7.07%, Calmar 2.27. Both Regime B and Hybrid variants underperform across risk-adjusted metrics.

### 2. Regime B fires too frequently (32.1% vs 18.6%).
It triggers in historically mild drawdowns (2011, 2015-16, 2018-19, 2022) where RPV overweighting was a net drag. The overweight-to-RPV increases vol-spending in non-crisis periods without compensation.

### 3. Timing mismatch.
All variants apply the shift at the next month-end after the signal. This means the first ~2-4 weeks of a crisis (e.g., March 2020 crash peak) are never protected. The benefit comes during the recovery phase when RPV acts as a vol dampener.

### 4. Hybrid has the worst CAGR (15.64%) while achieving a decent Calmar (2.21).
It fires the most (37.7% of dates) but the extra RPV exposure during non-stress regimes drags return more than it improves drawdown control.

### 5. Recommendation: **Keep current Sahm stress.**
Regime B does not add value as a blend weight trigger. The Sahm indicator's rarity and accuracy as a recession/labor-market stress signal makes it the superior choice. Consider Regime B only as a secondary overlay to watch (not to trade), e.g., a dashboard signal for regime awareness.

