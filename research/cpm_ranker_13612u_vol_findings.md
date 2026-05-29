# CPM Candidate-Ranker Swap: Faber/vol vs 13612U/vol

Measurement-only test. No production file edited. Production CPM stays Faber/vol (R0).

**Hypothesis:** swapping the CPM candidate ranker from EAA Vol-Adj (Faber/vol_252d) to 13612U/vol_252d improves risk-adjusted performance of the 60/40 two-sleeve CPM+BULL blend.

**Fixed (unchanged across variants):** HYG-OR-TIP canary gate, top-K=4 candidate pool, min-variance 50/50 pair on 504d covariance, best-of-safe leg, T+1 open execution, 10bps/side cost.

**Varied:** the candidate ranker (R1/R2) and, for R2, the positive-trend absmom filter to match (13612U instead of Faber).


## Variants

| Variant | Ranker | Positive-trend filter |
| --- | --- | --- |
| R0 (PROD) | faber_score / vol_252d | positive Faber |
| R1 | sig_13612U / vol_252d | positive Faber |
| R2 | sig_13612U / vol_252d | positive 13612U |

## R0 baseline verification (clean window)

- 60/40 blend: Sharpe **1.347** (expect 1.347), CAGR **13.59%** (expect 13.59%), MaxDD **-9.82%** (expect -9.82%) -> MATCH
- CPM standalone: Sharpe **1.263** (expect 1.263), CAGR **14.58%** (expect 14.58%) -> MATCH

## Clean window (2008-05-30 .. 2026-05-22)

### CPM standalone

| Variant | Raw Sharpe | Excess Sharpe vs SHV | CAGR | Vol | MaxDD | Calmar | Ann. Turnover | 2022 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| R0 | 1.263 | 1.145 | 14.58% | 11.30% | -15.41% | 0.95 | 627.8% | +7.49% |
| R1 | 1.277 | 1.161 | 14.98% | 11.47% | -15.41% | 0.97 | 566.7% | +7.60% |
| R2 | 1.285 | 1.168 | 15.01% | 11.41% | -15.41% | 0.97 | 583.3% | +7.60% |

### 60/40 two-sleeve CPM+BULL blend

| Variant | Raw Sharpe | Excess Sharpe vs SHV | CAGR | Vol | MaxDD | Calmar | Ann. Turnover | 2022 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| R0 | 1.347 | 1.212 | 13.59% | 9.84% | -9.82% | 1.38 | 627.8% | +4.95% |
| R1 | 1.368 | 1.234 | 13.84% | 9.85% | -10.63% | 1.30 | 566.7% | +5.02% |
| R2 | 1.375 | 1.240 | 13.86% | 9.81% | -10.94% | 1.27 | 583.3% | +5.02% |

## Stress window (1999-03-10 .. 2026-05-22)

### CPM standalone

| Variant | Raw Sharpe | Excess Sharpe vs SHV | CAGR | Vol | MaxDD | Calmar | Ann. Turnover | 2022 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| R0 | 1.218 | 1.014 | 13.99% | 11.28% | -15.91% | 0.88 | 651.5% | +7.49% |
| R1 | 1.260 | 1.060 | 14.81% | 11.48% | -19.74% | 0.75 | 629.4% | +7.60% |
| R2 | 1.279 | 1.077 | 14.99% | 11.44% | -19.74% | 0.76 | 633.1% | +7.60% |

### 60/40 two-sleeve CPM+BULL blend

| Variant | Raw Sharpe | Excess Sharpe vs SHV | CAGR | Vol | MaxDD | Calmar | Ann. Turnover | 2022 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| R0 | 1.291 | 1.056 | 12.65% | 9.58% | -11.79% | 1.07 | 651.5% | +4.95% |
| R1 | 1.332 | 1.097 | 13.14% | 9.61% | -13.63% | 0.96 | 629.4% | +5.02% |
| R2 | 1.346 | 1.110 | 13.25% | 9.59% | -13.63% | 0.97 | 633.1% | +5.02% |

## Selection overlap vs R0 (risk-on months where both risk-on)

Share of risk-on months where the variant picks the SAME min-var pair as R0, and where >=1 asset overlaps. Shows how much the ranker actually changes holdings.

| Window | Variant | Risk-on months (both) | Same pair % | >=1 asset overlap % |
| --- | --- | ---: | ---: | ---: |
| clean | R1 vs R0 | 187 | 83.4% | 97.3% |
| clean | R2 vs R0 | 187 | 79.7% | 97.3% |
| stress | R1 vs R0 | 290 | 82.1% | 98.3% |
| stress | R2 vs R0 | 290 | 79.3% | 98.3% |

## Asset selection frequency (clean window, risk-on pair appearances)

| Asset | R0 (Faber/vol) | R1 (13612U/vol) | R2 (13612U/vol, 13612U filter) |
| --- | ---: | ---: | ---: |
| DBC | 40 (21%) | 38 (20%) | 37 (20%) |
| EEM | 3 (2%) | 2 (1%) | 2 (1%) |
| EFA | 34 (18%) | 29 (16%) | 28 (15%) |
| GLD | 61 (33%) | 64 (34%) | 63 (34%) |
| QQQ | 41 (22%) | 43 (23%) | 43 (23%) |
| SPHQ | 125 (67%) | 132 (71%) | 133 (71%) |
| TLT | 64 (34%) | 57 (30%) | 58 (31%) |
| VNQ | 6 (3%) | 9 (5%) | 10 (5%) |

- R0: 187 risk-on pair-months.

- R1: 187 risk-on pair-months.

- R2: 187 risk-on pair-months.

## Note: which assets 13612U/vol favors differently than Faber/vol

Relative shift in clean-window pair appearances, R1 (13612U/vol) vs R0 (Faber/vol). Positive = 13612U/vol picks it more often.

| Asset | R0 % | R1 % | Shift (pp) |
| --- | ---: | ---: | ---: |
| SPHQ | 67% | 71% | +3.7 |
| GLD | 33% | 34% | +1.6 |
| VNQ | 3% | 5% | +1.6 |
| QQQ | 22% | 23% | +1.1 |
| EEM | 2% | 1% | -0.5 |
| DBC | 21% | 20% | -1.1 |
| EFA | 18% | 16% | -2.7 |
| TLT | 34% | 30% | -3.7 |

13612U/vol (a faster 1/3/6/12-month multi-horizon momentum) tilts toward faster-moving equity/factor names (SPHQ, QQQ, VNQ) and away from the slower diversifiers picked by Faber's 10-month SMA-distance (notably TLT and EFA). GLD and DBC are roughly unchanged. The tilt is modest: the min-var pair construction (504d covariance) anchors most of the selection, so the ranker swap mostly reshuffles the candidate ordering rather than wholesale changing holdings.


## Verdict

- **R1** (clean 60/40): dSharpe +0.021, dMaxDD +0.82pp vs R0 -> **WASH**
- **R2** (clean 60/40): dSharpe +0.028, dMaxDD +1.12pp vs R0 -> **WASH**

Rule applied: within ~0.03 Sharpe and similar MaxDD = wash (no reason to change production). Clearly higher Sharpe with non-worse MaxDD = flag as better.

**Bottom line: WASH, lean keep R0.** 13612U/vol buys a marginal +0.02-0.03 Raw Sharpe in the 60/40 blend (both windows) but pays for it with deeper drawdowns (clean MaxDD -9.82% -> -10.6/-10.9%; stress -11.79% -> -13.63%) and lower Calmar (1.38 -> 1.27-1.30 clean). Excess-Sharpe gain is the same ~+0.02-0.03 magnitude. Holdings barely move (80% identical pair, 97%+ >=1-asset overlap), so the swap is not a structural improvement -- it is a small return-for-drawdown trade inside Sharpe noise. No compelling reason to change production; Faber/vol remains preferable on drawdown/Calmar.


## Caveats

- All numbers post-cost (10 bps/side), T+1 open execution, close-to-close accounting on apply day (matches production engine).
- Excess Sharpe is vs SHV daily; Raw Sharpe uses 0 rf.
- Annualized turnover = mean per-rebalance two-way sum|dw| * 12 (CPM sleeve only; blend rows reuse the CPM-sleeve turnover).
- Overlap counts only months where BOTH R0 and the variant are risk-on with a 2-asset pair; partial-safe (single risk asset) and defensive months are excluded from the overlap denominator.
- Stress window relies on mutual-fund / index proxies pre-live-ETF (see cpm_live load_panel stitches); treat pre-2008 as proxy-based.
