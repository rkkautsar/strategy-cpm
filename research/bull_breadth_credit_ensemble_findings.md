# BULL breadth / credit / ensemble-vote vs production RV vol gate (V0)

Role: analyst (hypothesis-driven; READ-ONLY re production; writes only to research/; NO production/memo edits; NO commit). EXPLORATION ONLY; OOS-gated before adoption. Harness `research/bull_breadth_credit_ensemble.py` (reuses `bull_volgate_variants` sleeve machinery verbatim; swaps ONLY the vol-slot decision rule / vote).

**Question.** Do BREADTH, CREDIT, or an ENSEMBLE-VOTE of {V0 + breadth + credit} beat V0 (RV60<RV252) on **Calmar AND Martin** while KEEPING the 2008/2020 crash + 2018-Q4/2022 grind catches, net of execution lag? Canary (TIP 13612U>0) + trend (SPY 13612U>0) held at production in every variant; only the vol slot changes.

## 0. DATA-AVAILABILITY (load-bearing)

- **BREADTH (the hardest).** The literature signal is % of S&P500 constituents > their 200d MA. **FRED does NOT carry it**, and full constituent reconstruction is out of scope. PROXY used = **RSP/SPY equal-weight-vs-cap-weight relative strength** (coverage 2003-05-01..2026-05-29). When equal-weight lags cap-weight (ratio below its 200d MA) breadth is narrowing / mega-cap-led -> de-risk. **GAP: this is a PROXY, not the true %>200dMA; RSP starts 2003-05 so there is NO pre-2003 coverage -- the 1999 dot-com narrowing is NOT testable, only 2008+ (and the 2024 narrow-rally episode).** Breadth results are therefore clean-18y-only and proxy-bound.
- **CREDIT.** HY OAS (FRED `BAMLH0A0HYM2`) is **license-truncated to the last ~3 years** via fredgraph (confirmed: returns only 2023-05+, n~794) -- UNUSABLE for an 18-27y backtest. Substitute = **Moody's Baa-Aaa spread** (FRED `BAA`,`AAA`; monthly; coverage 1919-01-01..2026-04-01) as the credit-quality slope, plus **SLOOS** net% tightening C&I standards (FRED `DRTSCILM`; quarterly; 1990-04-01..2026-04-01). Both have full clean+ext history.
- **EXECUTION LAG.** Engine = T+1 MOO exact: signal uses data <= month-end sig_d, executed next open. Baa-Aaa lagged 1 month; SLOOS lagged 1 full quarter + 1mo release buffer (only a fully-released survey reading is used at decision time -- no release look-ahead).

## 1. Anchor gate

BULL V0 clean Sharpe **1.1005** / Calmar **0.8189** / Martin **3.0714** / MaxDD **-13.35%** vs anchor 1.1005 / 0.8189 / 3.0714 / -13.35% -> **CONFIRMED**.

## 2. PRIMARY -- Calmar / Martin (+ Sharpe / MaxDD / CAGR), BULL clean 18y

| Variant | Calmar | Martin | Sharpe | MaxDD | CAGR | Vol |
|---|---:|---:|---:|---:|---:|---:|
| V0 RV60<RV252 (PROD) | 0.8189 | 3.0714 | 1.1005 | -13.35% | 10.93% | 9.90% |
| Breadth proxy RSP/SPY (REPLACE) | 0.3488 | 1.7218 | 0.8416 | -20.41% | 7.12% | 8.65% |
| RV AND breadth (ADD) | 0.6190 | 2.4396 | 0.9456 | -12.09% | 7.48% | 8.00% |
| Credit Baa-Aaa slope (REPLACE) | 0.4130 | 1.3480 | 0.7038 | -17.31% | 7.15% | 10.66% |
| RV AND credit slope (ADD) | 0.6193 | 2.0616 | 0.8853 | -13.35% | 8.27% | 9.52% |
| RV AND credit level (ADD) | 0.6055 | 2.1804 | 1.0299 | -13.35% | 8.08% | 7.88% |
| SLOOS tightening (REPLACE) | 0.2844 | 0.9936 | 0.5542 | -17.31% | 4.92% | 9.54% |
| RV AND SLOOS (ADD) | 0.4423 | 1.4331 | 0.8332 | -13.35% | 5.90% | 7.23% |
| Ensemble vote frac (V0+breadth+credit)/3 | 0.6105 | 2.5380 | 0.9992 | -13.95% | 8.52% | 8.58% |
| Ensemble >=2 of 3 (V0,breadth,credit) | 0.5232 | 1.9956 | 0.8621 | -16.05% | 8.40% | 9.97% |
| Ensemble all-3 (==ADD-all) | 0.6012 | 2.3620 | 0.9315 | -12.09% | 7.27% | 7.90% |

### Delta vs V0 (clean)

| Variant | dCalmar | dMartin | dSharpe | dMaxDD (pp) | dCAGR (pp) |
|---|---:|---:|---:|---:|---:|
| V0 RV60<RV252 (PROD) | +0.0000 | +0.0000 | +0.0000 | +0.00 | +0.00 |
| Breadth proxy RSP/SPY (REPLACE) | -0.4701 | -1.3497 | -0.2589 | +7.06 | -3.81 |
| RV AND breadth (ADD) | -0.1999 | -0.6319 | -0.1549 | -1.26 | -3.45 |
| Credit Baa-Aaa slope (REPLACE) | -0.4058 | -1.7234 | -0.3968 | +3.96 | -3.78 |
| RV AND credit slope (ADD) | -0.1996 | -1.0098 | -0.2152 | -0.00 | -2.66 |
| RV AND credit level (ADD) | -0.2134 | -0.8910 | -0.0706 | -0.00 | -2.85 |
| SLOOS tightening (REPLACE) | -0.5344 | -2.0778 | -0.5464 | +3.96 | -6.01 |
| RV AND SLOOS (ADD) | -0.3766 | -1.6383 | -0.2674 | -0.00 | -5.03 |
| Ensemble vote frac (V0+breadth+credit)/3 | -0.2083 | -0.5334 | -0.1013 | +0.61 | -2.41 |
| Ensemble >=2 of 3 (V0,breadth,credit) | -0.2956 | -1.0758 | -0.2385 | +2.70 | -2.53 |
| Ensemble all-3 (==ADD-all) | -0.2177 | -0.7094 | -0.1691 | -1.26 | -3.66 |

*dCalmar/dMartin/dSharpe>0 = better. dMaxDD>0 = deeper (worse). dCAGR>0 = more return. Breadth (B_*) + any breadth-containing ensemble (E_*) are PROXY-bound 2008+; credit/SLOOS span full history.*

### Ext 27y (partly proxy-backed; breadth proxy only 2003-05+, neutral-ON before)

| Variant | Calmar | Martin | Sharpe | MaxDD | CAGR |
|---|---:|---:|---:|---:|---:|
| V0 RV60<RV252 (PROD) | 0.7101 | 2.5820 | 1.0207 | -13.35% | 9.48% |
| Breadth proxy RSP/SPY (REPLACE) | 0.3685 | 1.9921 | 0.8899 | -20.41% | 7.52% |
| RV AND breadth (ADD) | 0.5708 | 2.0355 | 0.8780 | -12.09% | 6.90% |
| Credit Baa-Aaa slope (REPLACE) | 0.3788 | 1.3815 | 0.6931 | -17.31% | 6.56% |
| RV AND credit slope (ADD) | 0.5428 | 1.7469 | 0.8436 | -13.35% | 7.24% |
| RV AND credit level (ADD) | 0.5308 | 1.8729 | 0.9516 | -13.35% | 7.08% |
| SLOOS tightening (REPLACE) | 0.3297 | 1.2733 | 0.6482 | -17.31% | 5.71% |
| RV AND SLOOS (ADD) | 0.4183 | 1.3462 | 0.7898 | -13.35% | 5.58% |
| Ensemble vote frac (V0+breadth+credit)/3 | 0.5709 | 2.5079 | 0.9801 | -13.95% | 7.97% |
| Ensemble >=2 of 3 (V0,breadth,credit) | 0.4917 | 1.9860 | 0.8591 | -16.05% | 7.89% |
| Ensemble all-3 (==ADD-all) | 0.5370 | 1.7612 | 0.8656 | -12.09% | 6.49% |

## 3. Whipsaw (single-gate variants, clean 18y monthly signals)

Vol-slot de-risk = canary_ok AND trend_ok AND NOT gate_ok. False de-risk = next-month SPY return > 0.

| Variant | de-risk mo | false-pos | false-pos rate | mean SPY next | turnover/yr |
|---|---:|---:|---:|---:|---:|
| V0 RV60<RV252 (PROD) | 32 | 19 | 59.4% | +0.50% | 378.3% |
| Breadth proxy RSP/SPY (REPLACE) | 81 | 55 | 67.9% | +0.98% | 244.8% |
| RV AND breadth (ADD) | 90 | 61 | 67.8% | +0.95% | 200.3% |
| Credit Baa-Aaa slope (REPLACE) | 39 | 28 | 71.8% | +1.94% | 467.3% |
| RV AND credit slope (ADD) | 50 | 33 | 66.0% | +1.06% | 400.5% |
| RV AND credit level (ADD) | 77 | 51 | 66.2% | +0.94% | 289.3% |
| SLOOS tightening (REPLACE) | 69 | 53 | 76.8% | +1.49% | 333.8% |
| RV AND SLOOS (ADD) | 90 | 65 | 72.2% | +1.21% | 244.8% |

## 4. Crash + grind protection (BULL sleeve MaxDD / total return in window)

Must KEEP: 2008 GFC + 2020 COVID crashes; 2018-Q4 + 2022 grinds (V0: 2018-Q4 -2.14%, 2022 -0.30%).

| Variant | 2008 GFC DD/Ret | 2018 Q4 DD/Ret | 2020 COVID DD/Ret | 2022 bear DD/Ret |
|---|---|---|---|---|
| V0 RV60<RV252 (PROD) | -12.09% / 6.57% | -2.14% / 15.33% | -13.35% / -3.82% | -0.30% / 0.94% |
| Breadth proxy RSP/SPY (REPLACE) | -12.09% / 6.57% | -4.05% / -0.88% | -4.68% / 11.21% | -4.94% / 5.18% |
| RV AND breadth (ADD) | -12.09% / 6.57% | -2.17% / -0.87% | -4.68% / 11.21% | -0.30% / 0.94% |
| Credit Baa-Aaa slope (REPLACE) | -12.09% / 6.57% | -4.05% / -0.88% | -13.35% / -3.82% | -10.11% / -0.33% |
| RV AND credit slope (ADD) | -12.09% / 6.57% | -2.17% / -0.87% | -13.35% / -3.82% | -0.30% / 0.94% |
| RV AND credit level (ADD) | -10.40% / 8.66% | -2.14% / 6.82% | -13.35% / -4.11% | -0.30% / 0.94% |
| SLOOS tightening (REPLACE) | -10.40% / 8.66% | -10.10% / 10.42% | -13.35% / -2.29% | -10.11% / -0.33% |
| RV AND SLOOS (ADD) | -10.40% / 8.66% | -2.14% / 15.33% | -13.35% / -3.82% | -0.30% / 0.94% |
| Ensemble vote frac (V0+breadth+credit)/3 | -12.09% / 6.57% | -2.38% / 4.30% | -8.39% / 1.05% | -4.97% / 1.99% |
| Ensemble >=2 of 3 (V0,breadth,credit) | -12.09% / 6.57% | -4.05% / -0.88% | -13.35% / -3.82% | -4.94% / 5.18% |
| Ensemble all-3 (==ADD-all) | -12.09% / 6.57% | -2.17% / -0.87% | -4.68% / 11.21% | -0.30% / 0.94% |

*Windows: 2008 GFC 2008-05-30..2009-06-30; 2018 Q4 2018-01-01..2018-12-31; 2020 COVID 2020-01-01..2020-06-30; 2022 bear 2022-01-01..2022-12-31.*

## 5. Live current state (latest signal month)

| Variant | signal date | canary | trend | gate/vote | SPY weight |
|---|---|:--:|:--:|---|---:|
| V0 RV60<RV252 (PROD) | 2026-05-22 | Y | Y | OFF | 0% |
| Breadth proxy RSP/SPY (REPLACE) | 2026-05-22 | Y | Y | OFF | 0% |
| RV AND breadth (ADD) | 2026-05-22 | Y | Y | OFF | 0% |
| Credit Baa-Aaa slope (REPLACE) | 2026-05-22 | Y | Y | OFF | 0% |
| RV AND credit slope (ADD) | 2026-05-22 | Y | Y | OFF | 0% |
| RV AND credit level (ADD) | 2026-05-22 | Y | Y | OFF | 0% |
| SLOOS tightening (REPLACE) | 2026-05-22 | Y | Y | OFF | 0% |
| RV AND SLOOS (ADD) | 2026-05-22 | Y | Y | OFF | 0% |
| Ensemble vote frac (V0+breadth+credit)/3 | 2026-05-22 | Y | Y | 0/3 on | 0% |
| Ensemble >=2 of 3 (V0,breadth,credit) | 2026-05-22 | Y | Y | 0/3 on | 0% |
| Ensemble all-3 (==ADD-all) | 2026-05-22 | Y | Y | 0/3 on | 0% |

## 6. VERDICT (PRIMARY = Calmar AND Martin; keep crash + grind)

V0 baseline: Calmar 0.8189, Martin 3.0714, Sharpe 1.1005, MaxDD -13.35%. keeps crash = 2008 & 2020 DD not >2pp deeper; keeps grind = 2018-Q4 & 2022 DD not >3pp deeper; beats = BOTH Calmar AND Martin above V0.

| Rank | Variant | Calmar | Martin | Sharpe | MaxDD | keeps crash? | keeps grind? | beats C+M? |
|---:|---|---:|---:|---:|---:|:--:|:--:|:--:|
| - | V0 RV60<RV252 (PROD) | 0.8189 | 3.0714 | 1.1005 | -13.35% | Y | Y | - |
| 1 | RV AND credit slope (ADD) | 0.6193 | 2.0616 | 0.8853 | -13.35% | Y | Y | NO |
| 2 | RV AND breadth (ADD) | 0.6190 | 2.4396 | 0.9456 | -12.09% | Y | Y | NO |
| 3 | Ensemble vote frac (V0+breadth+credit)/3 | 0.6105 | 2.5380 | 0.9992 | -13.95% | Y | NO | NO |
| 4 | RV AND credit level (ADD) | 0.6055 | 2.1804 | 1.0299 | -13.35% | Y | Y | NO |
| 5 | Ensemble all-3 (==ADD-all) | 0.6012 | 2.3620 | 0.9315 | -12.09% | Y | Y | NO |
| 6 | Ensemble >=2 of 3 (V0,breadth,credit) | 0.5232 | 1.9956 | 0.8621 | -16.05% | Y | NO | NO |
| 7 | RV AND SLOOS (ADD) | 0.4423 | 1.4331 | 0.8332 | -13.35% | Y | Y | NO |
| 8 | Credit Baa-Aaa slope (REPLACE) | 0.4130 | 1.3480 | 0.7038 | -17.31% | Y | NO | NO |
| 9 | Breadth proxy RSP/SPY (REPLACE) | 0.3488 | 1.7218 | 0.8416 | -20.41% | Y | NO | NO |
| 10 | SLOOS tightening (REPLACE) | 0.2844 | 0.9936 | 0.5542 | -17.31% | Y | NO | NO |

**No candidate beats V0 on BOTH Calmar AND Martin while keeping crash AND grind protection.** Keep production V0 (RV60<RV252).

## 7. Caveats / OVERFITTING / OOS

- EXPLORATION ONLY; READ-ONLY re production; NO production/memo edits; NO commit.
- **Breadth is a PROXY** (RSP/SPY relative strength), NOT the literature %>200dMA series, and is limited to 2003-05+ (clean 18y only; no 1999). Any breadth/ensemble verdict is proxy-bound and must be re-tested on a true breadth series before adoption.
- **HY OAS unusable** via fredgraph (3y license truncation); credit uses Moody's Baa-Aaa (investment-grade quality slope, not high-yield) + SLOOS. A true daily HY OAS backtest requires a licensed data source.
- Execution: T+1 MOO exact (no same-day application). Baa-Aaa lagged 1mo; SLOOS lagged 1 quarter +1mo buffer (no release look-ahead). Monthly RV/credit signals are robust to a 1-day shift by construction (month-end close data, next-open execution).
- Single 18y in-sample; any winner needs OOS / walk-forward (freeze pre-2015, test 2015+) + paired bootstrap on Calmar/Martin deltas before a live change.
- Only the vol slot changes; canary (TIP 13612U>0) + trend (SPY 13612U>0) + safe (best{SHV,IEF}) held at production. mooex T+1, 10 bps/side, via exec_lag_moo_validation_2026_05_30._segment_returns_conv.
