# CPM Candidate-Ranker Ablation Remainder (R0..R4)

Measurement-only. No production file edited. Production CPM stays EAA Faber/vol (R0).

**Question:** is the vol-adjustment (R1 Faber-only) or the Faber form itself (R2/R3 plain momentum) necessary, or is a simpler ranker a defensible simplification of the production EAA ranker?

**Fixed across all variants:** HYG-OR-TIP canary gate, POSITIVE-FABER trend filter, top-K=4 candidate pool, min-variance 50/50 pair on 504d covariance, best-of-safe leg, T+1 open execution, 10 bps/side cost.

**Varied:** ONLY the ranker used to pick the top-4 candidates.


## Variants

| Variant | Ranker | Vol-adjusted? |
| --- | --- | --- |
| R0 (PROD) | faber_score / vol_252d | yes |
| R1 | faber_score | no |
| R2 | price/price_12m - 1 (plain 12m mom) | no |
| R3 | price/price_6m - 1 (plain 6m mom) | no |
| R4 | mean_252d_daily_ret / vol_252d (Sharpe-like) | yes |

## R0 baseline verification (clean window)

- 60/40 blend: Sharpe **1.347** (expect 1.347), CAGR **13.59%** (expect 13.59%), MaxDD **-9.82%** (expect -9.82%) -> MATCH
- CPM standalone: Sharpe **1.263** (expect 1.263), CAGR **14.58%** (expect 14.58%) -> MATCH

## Clean window (2008-05-30 .. 2026-05-22)

### CPM standalone

| Variant | Raw Sharpe | Excess Sharpe vs SHV | CAGR | Vol | MaxDD | Calmar | Ann. Turnover | 2022 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| R0 | 1.263 | 1.145 | 14.58% | 11.30% | -15.41% | 0.95 | 627.8% | +7.49% |
| R1 | 1.173 | 1.058 | 13.63% | 11.48% | -15.41% | 0.88 | 700.0% | +7.49% |
| R2 | 1.113 | 1.003 | 13.50% | 12.05% | -18.31% | 0.74 | 616.7% | +7.24% |
| R3 | 1.043 | 0.931 | 12.45% | 11.95% | -18.89% | 0.66 | 800.0% | +7.49% |
| R4 | 1.244 | 1.130 | 14.81% | 11.67% | -15.92% | 0.93 | 544.4% | +7.60% |

### 60/40 two-sleeve CPM+BULL blend

| Variant | Raw Sharpe | Excess Sharpe vs SHV | CAGR | Vol | MaxDD | Calmar | Ann. Turnover | 2022 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| R0 | 1.347 | 1.212 | 13.59% | 9.84% | -9.82% | 1.38 | 627.8% | +4.95% |
| R1 | 1.280 | 1.147 | 13.03% | 9.97% | -9.82% | 1.33 | 700.0% | +4.95% |
| R2 | 1.246 | 1.116 | 12.97% | 10.22% | -14.14% | 0.92 | 616.7% | +4.75% |
| R3 | 1.204 | 1.072 | 12.34% | 10.10% | -11.28% | 1.09 | 800.0% | +4.95% |
| R4 | 1.350 | 1.217 | 13.75% | 9.92% | -10.85% | 1.27 | 544.4% | +5.02% |

## Stress window (1999-03-10 .. 2026-05-22)

### CPM standalone

| Variant | Raw Sharpe | Excess Sharpe vs SHV | CAGR | Vol | MaxDD | Calmar | Ann. Turnover | 2022 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| R0 | 1.218 | 1.014 | 13.99% | 11.28% | -15.91% | 0.88 | 651.5% | +7.49% |
| R1 | 1.284 | 1.082 | 15.19% | 11.54% | -15.91% | 0.95 | 688.3% | +7.49% |
| R2 | 1.110 | 0.919 | 13.62% | 12.17% | -18.31% | 0.74 | 614.7% | +7.24% |
| R3 | 1.141 | 0.944 | 13.74% | 11.91% | -19.74% | 0.70 | 787.7% | +7.49% |
| R4 | 1.212 | 1.015 | 14.51% | 11.75% | -15.92% | 0.91 | 618.4% | +7.60% |

### 60/40 two-sleeve CPM+BULL blend

| Variant | Raw Sharpe | Excess Sharpe vs SHV | CAGR | Vol | MaxDD | Calmar | Ann. Turnover | 2022 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| R0 | 1.291 | 1.056 | 12.65% | 9.58% | -11.79% | 1.07 | 651.5% | +4.95% |
| R1 | 1.333 | 1.099 | 13.36% | 9.77% | -11.25% | 1.19 | 688.3% | +4.95% |
| R2 | 1.222 | 0.994 | 12.45% | 10.01% | -14.14% | 0.88 | 614.7% | +4.75% |
| R3 | 1.249 | 1.016 | 12.52% | 9.83% | -13.63% | 0.92 | 787.7% | +4.95% |
| R4 | 1.295 | 1.063 | 12.97% | 9.78% | -11.78% | 1.10 | 618.4% | +5.02% |

## Selection overlap vs R0 + EAA-rank stability

Share of risk-on months (both risk-on) where the variant picks the SAME min-var pair as R0 and where >=1 asset overlaps. Mean EAA-rank = average production-EAA rank position (1=best of 8) of the variant's selected pair; R0's own mean is the natural reference.

| Window | Variant | Risk-on months (both) | Same pair % | >=1 asset overlap % | Mean EAA-rank of picks |
| --- | --- | ---: | ---: | ---: | ---: |
| clean | R0 | 187 | 100.0% | 100.0% | 2.30 |
| clean | R1 | 187 | 84.5% | 99.5% | 2.23 |
| clean | R2 | 186 | 62.4% | 93.5% | 2.51 |
| clean | R3 | 186 | 68.3% | 94.1% | 2.40 |
| clean | R4 | 187 | 64.7% | 93.0% | 2.55 |
| stress | R0 | 290 | 100.0% | 100.0% | 2.27 |
| stress | R1 | 290 | 81.4% | 99.3% | 2.21 |
| stress | R2 | 289 | 56.4% | 93.8% | 2.53 |
| stress | R3 | 289 | 68.5% | 95.2% | 2.37 |
| stress | R4 | 290 | 61.4% | 93.4% | 2.57 |

## Asset selection frequency (clean window, risk-on pair appearances)

| Asset | R0 | R1 | R2 | R3 | R4 |
| --- | ---: | ---: | ---: | ---: | ---: |
| DBC | 40 (21%) | 44 (24%) | 33 (18%) | 53 (28%) | 33 (18%) |
| EEM | 3 (2%) | 5 (3%) | 6 (3%) | 4 (2%) | 8 (4%) |
| EFA | 34 (18%) | 35 (19%) | 22 (12%) | 33 (18%) | 22 (12%) |
| GLD | 61 (33%) | 61 (33%) | 71 (38%) | 62 (33%) | 74 (40%) |
| QQQ | 41 (22%) | 46 (25%) | 50 (27%) | 40 (22%) | 38 (20%) |
| SPHQ | 125 (67%) | 115 (61%) | 126 (68%) | 111 (60%) | 131 (70%) |
| TLT | 64 (34%) | 60 (32%) | 53 (28%) | 57 (31%) | 58 (31%) |
| VNQ | 6 (3%) | 8 (4%) | 11 (6%) | 12 (6%) | 10 (5%) |

- R0: 187 risk-on pair-months.

- R1: 187 risk-on pair-months.

- R2: 186 risk-on pair-months.

- R3: 186 risk-on pair-months.

- R4: 187 risk-on pair-months.

## Verdict

- **R1** (faber_score (Faber-only, no vol adj)): clean dSharpe -0.067, dMaxDD +0.00pp | stress dSharpe +0.041, dMaxDD -0.55pp vs R0 -> **WORSE**
- **R2** (price/price_12m - 1 (plain 12m mom)): clean dSharpe -0.101, dMaxDD +4.32pp | stress dSharpe -0.070, dMaxDD +2.35pp vs R0 -> **WORSE**
- **R3** (price/price_6m - 1 (plain 6m mom)): clean dSharpe -0.142, dMaxDD +1.46pp | stress dSharpe -0.042, dMaxDD +1.84pp vs R0 -> **WORSE**
- **R4** (mean_252d_daily_ret / vol_252d (Sharpe-like)): clean dSharpe +0.003, dMaxDD +1.03pp | stress dSharpe +0.004, dMaxDD -0.02pp vs R0 -> **WASH**

Change-threshold applied: a variant is a WASH (no reason to change production) if 60/40 blend Sharpe is within ~0.05 of R0 and MaxDD is not worse by more than ~1-2pp. BETTER requires clearly higher Sharpe (>0.05) with non-worse drawdown.


### Recommendation: KEEP EAA (Faber/vol)

- **Vol-adjustment IS doing real work.** Removing it (R1 Faber-only) costs -0.067 blend Sharpe in the clean window (1.347 -> 1.280) and lowers Calmar (1.38 -> 1.33). It does help the stress window (+0.041 Sharpe, shallower MaxDD), but the clean-window loss exceeds the change-threshold, so Faber-only is a net WORSE, not a defensible simplification.
- **The Faber form matters.** Both plain-momentum rankers are clearly WORSE in both windows: R2 (12m) -0.101 clean Sharpe with +4.3pp deeper MaxDD (-9.82% -> -14.14%); R3 (6m) -0.142 clean Sharpe, +1.5pp MaxDD, and the worst Calmar of the set. Plain momentum on two price endpoints is noisier than Faber's 10m SMA-distance and selects deeper-drawdown pairs even under the same positive-Faber filter and min-var pairing.
- **Only R4 (Sharpe-like) is a true wash** (clean +0.003, stress +0.004 Sharpe; comparable MaxDD; lowest turnover 544%). It is essentially a re-expression of the same vol-adjusted-trend idea, so it confirms the vol-adjustment family is the right one but offers no improvement worth a production change.
- **Bottom line:** neither dropping the vol-adjustment (R1) nor simplifying to plain momentum (R2/R3) is defensible within the change-threshold. The vol-adjustment in the ranker is doing real work; keep production EAA Faber/vol (R0).


## Caveats

- All numbers post-cost (10 bps/side), T+1 open execution, close-to-close accounting on apply day (matches production engine).
- Excess Sharpe is vs SHV daily; Raw Sharpe uses 0 rf.
- Annualized turnover = mean per-rebalance two-way sum|dw| * 12 (CPM sleeve only; blend rows reuse the CPM-sleeve turnover).
- Overlap counts only months where BOTH R0 and the variant are risk-on with a 2-asset pair; partial-safe / defensive months excluded.
- Mean EAA-rank uses production's Faber/vol ordering as the yardstick; lower = variant picks assets that production also rates highly.
- Positive-Faber filter is fixed for ALL variants, so even momentum rankers (R2/R3) can only select assets above their Faber 10m SMA.
- Stress window relies on mutual-fund / index proxies pre-live-ETF (see cpm_live load_panel stitches); treat pre-2008 as proxy-based.
