# 60/40 Two-Sleeve CPM-BULL: Memo-Gap Evidence (A-E)

**Headline convention (all tables):** blend = 0.60 CPM (trend sleeve) + 0.40 BULL-SPY (equity sleeve); slow rv_60d<rv_252d equity vol gate; realistic T+1 MOO exact execution (overnight close[T]->open[af] on the old basket, intraday open[af]->close[af] on the new basket, compounded; real yfinance auto_adjust opens); post-cost 10 bps/side. Two-sleeve only (NOT 60/20/20). Read-only harness `research/memo_gap_evidence.py`; reuses production weight/return functions via the `exec_lag_moo_validation_2026_05_30` engine.
Panel 1997-12-10..2026-05-22 (7181 rows). MOO real-open coverage: CPM real=253 fallback=73; BULL real=283 fallback=43.

## A. Covariance-Lookback Plateau (CPM min-variance pair)

**Config:** 60/40 two-sleeve (0.60 CPM + 0.40 BULL-SPY), slow rv_60d<rv_252d equity gate, T+1 MOO exact execution, post-cost 10 bps/side. Only the CPM min-variance pair's covariance lookback varies; everything else held at the headline config (PAIR_VAR_WEIGHT=1.0 pure min-variance, top-K=4, positive-trend screen, dual canary). BULL sleeve is identical across rows (gate-shared but lookback-independent).
**Windows:** clean 2008-05-30..2026-05-22 (18y); ext 1999-03-10..2026-05-22 (27y).

**Base anchor (504d, clean blend):** Sharpe 1.321 / CAGR 13.25% / MaxDD -10.66% / Calmar 1.243 vs headline 1.321 / 13.25% / -10.66% / 1.243 -> **CONFIRMED**.


### CPM-solo -- cov-lookback sweep [clean, mooex, slow gate]

| cov lookback | Sharpe | CAGR | MaxDD | Calmar |
|---|---:|---:|---:|---:|
| 126d | 1.159 | 13.33% | -18.72% | 0.712 |
| 252d | 1.068 | 12.14% | -16.54% | 0.734 |
| 504d (base) | 1.242 | 14.23% | -16.35% | 0.870 |
| 756d | 1.222 | 13.90% | -13.95% | 0.996 |
| 1008d | 1.160 | 13.53% | -13.67% | 0.990 |
| 1260d | 1.134 | 13.28% | -13.67% | 0.972 |

### CPM-solo -- cov-lookback sweep [ext, mooex, slow gate]

| cov lookback | Sharpe | CAGR | MaxDD | Calmar |
|---|---:|---:|---:|---:|
| 126d | 1.124 | 12.68% | -21.40% | 0.593 |
| 252d | 1.086 | 12.25% | -19.29% | 0.635 |
| 504d (base) | 1.164 | 13.95% | -16.76% | 0.832 |
| 756d | 1.145 | 14.35% | -21.07% | 0.681 |
| 1008d | 1.071 | 13.63% | -18.17% | 0.750 |
| 1260d | 1.042 | 13.42% | -23.90% | 0.562 |

### 60/40 blend -- cov-lookback sweep [clean, mooex, slow gate]

| cov lookback | Sharpe | CAGR | MaxDD | Calmar |
|---|---:|---:|---:|---:|
| 126d | 1.265 | 12.71% | -14.80% | 0.859 |
| 252d | 1.216 | 12.01% | -12.70% | 0.946 |
| 504d (base) | 1.321 | 13.25% | -10.66% | 1.243 |
| 756d | 1.307 | 13.05% | -10.66% | 1.224 |
| 1008d | 1.275 | 12.84% | -12.70% | 1.011 |
| 1260d | 1.257 | 12.69% | -12.70% | 1.000 |

### 60/40 blend -- cov-lookback sweep [ext, mooex, slow gate]

| cov lookback | Sharpe | CAGR | MaxDD | Calmar |
|---|---:|---:|---:|---:|
| 126d | 1.194 | 11.55% | -14.80% | 0.781 |
| 252d | 1.177 | 11.30% | -12.70% | 0.890 |
| 504d (base) | 1.235 | 12.32% | -11.18% | 1.101 |
| 756d | 1.230 | 12.58% | -14.42% | 0.872 |
| 1008d | 1.181 | 12.16% | -12.70% | 0.958 |
| 1260d | 1.160 | 12.05% | -15.34% | 0.785 |

### A. Verdict

Clean blend Sharpe: 504d=1.321, 756d=1.307, 1008d=1.275, 1260d=1.257; clean blend Calmar: 504d=1.243, 756d=1.224, 1008d=1.011, 1260d=1.000 (max deviation of 756/1008/1260 vs 504 = 0.064 Sharpe, 0.244 Calmar).

**Verdict: the '504d plateaus to 1000d+' claim is REFUTED as stated.** There is a NARROW plateau, but it spans only 504d-756d, not 1000d+. 504d and 756d are statistically flat on the clean blend (Sharpe 1.321 vs 1.307, identical MaxDD -10.66%, Calmar 1.243 vs 1.224) -- a genuine two-point stability shelf that supports 504d as a non-knife-edge choice. But extending to 1008d and 1260d DEGRADES the blend monotonically: clean Sharpe falls to 1.275 then 1.257, clean Calmar collapses from 1.243 to 1.011 then 1.000, and clean MaxDD deepens from -10.66% to -12.70%. The ext window is worse still for long lookbacks (756d/1008d/1260d Calmar 0.872/0.958/0.785 vs 504d 1.101, with 1260d MaxDD blowing out to -15.34%). The short end is also clearly inferior (252d Sharpe 1.216 / Calmar 0.946; 126d MaxDD -14.80%). So 504d sits at the LEFT EDGE of a short 504-756d plateau and is the joint Sharpe+Calmar optimum, with decay -- not a plateau -- beyond ~756d. CPM-solo tells a slightly different story (its MaxDD keeps improving out to 756-1008d as longer covariance smooths pair selection) but its Sharpe/Calmar still peak at 504-756d, and the blend (the headline object) decays past 756d. Bottom line: 504d is well-chosen and locally stable, but the specific claim that metrics stay flat out to 1000d+ does not hold.


## B. SPY / QQQ Naive-Benchmark Excess + Exposure Caveat

**Config:** strategies = 60/40 blend, CPM-solo, BULL-solo (slow rv_60d gate, T+1 MOO exact, post-cost 10 bps/side). Benchmarks = SPY buy-and-hold and QQQ buy-and-hold (close-to-close, one-time 10 bps entry cost, always 100% long). Beta = OLS slope of daily strategy returns on daily SPY returns. Avg exposure = mean daily fraction in risky/risk-on assets (CPM: sum of weight on the 8 risky ETFs; BULL: SPY weight; blend: 0.60*CPM_risky + 0.40*BULL_risky). Cash/safe legs count as 0 exposure.
**Windows:** clean 2008-05-30..2026-05-22; ext 1999-03-10..2026-05-22 (QQQ & SPY both have full history from the panel start).


### B. Strategy vs SPY/QQQ buy-and-hold [clean, mooex, slow gate]

| series | CAGR | Sharpe | MaxDD | Calmar | excess CAGR vs SPY | excess CAGR vs QQQ | beta to SPY | avg risky exposure |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 60/40 blend | 13.25% | 1.321 | -10.66% | 1.243 | 1.52% | -3.70% | 0.16 | 75.7% |
| CPM-solo | 14.23% | 1.242 | -16.35% | 0.870 | 2.51% | -2.71% | 0.15 | 86.6% |
| BULL-solo | 11.44% | 1.081 | -13.35% | 0.857 | -0.29% | -5.50% | 0.17 | 59.4% |
| SPY-BH | 11.73% | 0.660 | -50.70% | 0.231 | 0.00% | -5.22% | 1.00 | 100% |
| QQQ-BH | 16.94% | 0.816 | -49.37% | 0.343 | 5.22% | 0.00% | 1.04 | 100% |

### B. Strategy vs SPY/QQQ buy-and-hold [ext, mooex, slow gate]

| series | CAGR | Sharpe | MaxDD | Calmar | excess CAGR vs SPY | excess CAGR vs QQQ | beta to SPY | avg risky exposure |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 60/40 blend | 12.32% | 1.235 | -11.18% | 1.101 | 3.82% | 1.42% | 0.16 | 74.8% |
| CPM-solo | 13.95% | 1.164 | -16.76% | 0.832 | 5.44% | 3.05% | 0.15 | 88.8% |
| BULL-solo | 9.49% | 0.920 | -13.96% | 0.680 | 0.99% | -1.41% | 0.17 | 53.9% |
| SPY-BH | 8.50% | 0.522 | -55.19% | 0.154 | 0.00% | -2.39% | 1.00 | 100% |
| QQQ-BH | 10.89% | 0.519 | -82.96% | 0.131 | 2.39% | 0.00% | 1.19 | 100% |

### B. Honest read

The 60/40 blend beats SPY buy-and-hold on CAGR by a modest +1.52% (clean) / +3.82% (ext) but TRAILS QQQ buy-and-hold on CAGR in the clean window (-3.70%) and only edges it in the ext window (+1.42%). The blend's headline advantage is NOT raw return -- it is risk: clean Sharpe 1.321 vs SPY 0.660 / QQQ 0.816, clean MaxDD -10.66% vs SPY -50.70% / QQQ -49.37% (Calmar 1.243 vs 0.231 / 0.343). **Mechanical caveat (must be stated with any excess-return row):** the blend runs a realized beta to SPY of only ~0.16 and spends meaningful time de-risked -- average risky exposure ~75% (blend), ~87% (CPM-solo), ~59% (BULL-solo) -- so it is NOT an always-long equity book. A large part of the excess return versus always-long SPY/QQQ is therefore lower-beta de-risking and cross-asset diversification (the trend sleeve holds GLD/TLT/bonds), not pure stock-picking skill. Framed honestly: the blend is not a higher-return bet than QQQ; it is a far higher risk-adjusted, far shallower-drawdown bet that happens to roughly match SPY's long-run CAGR while taking ~1/6th the equity beta and a fifth of the peak drawdown.


## C. RV-Gate FP/TP Cohort Vol Asymmetry (fresh rv_60d)

**Gate:** BULL equity vol gate rv_60d(SPY) < rv_252d(SPY); gate ON = risk-on allowed, gate OFF (rv_60d >= rv_252d) = risk-off. Forward = next month-end signal date. Forward realized vol = annualized std of daily SPY returns over the forward month. Cohorts among gate-OFF months: TRUE-POSITIVE (SPY fell, fwd <= 0) vs FALSE-POSITIVE (SPY rose, fwd > 0). Computed fresh on the rv_60d gate (not the stale rv_20d cohort log).
**Windows:** clean 2008-05-30..2026-05-22; ext 1999-03-10..2026-05-22.


### C. rv_60d gate-OFF cohorts [clean]

Evaluated months: 216; gate-OFF (risk-off): 74 (34.3%); gate-ON: 142.

| cohort | count | mean fwd SPY return | mean fwd realized vol (ann) | median fwd vol |
|---|---:|---:|---:|---:|
| TRUE-POSITIVE (SPY fell) | 33 | -5.32% | 29.94% | 22.51% |
| FALSE-POSITIVE (SPY rose) | 41 | 4.11% | 15.96% | 13.01% |
| ALL gate-OFF | 74 | -0.10% | 22.19% | 18.22% |
| gate-ON (unconditional contrast) | 142 | 1.62% | 12.95% | 11.64% |

### C. rv_60d gate-OFF cohorts [ext]

Evaluated months: 326; gate-OFF (risk-off): 120 (36.8%); gate-ON: 206.

| cohort | count | mean fwd SPY return | mean fwd realized vol (ann) | median fwd vol |
|---|---:|---:|---:|---:|
| TRUE-POSITIVE (SPY fell) | 52 | -4.73% | 27.24% | 22.47% |
| FALSE-POSITIVE (SPY rose) | 68 | 3.81% | 16.01% | 13.86% |
| ALL gate-OFF | 120 | 0.11% | 20.88% | 17.84% |
| gate-ON (unconditional contrast) | 206 | 1.17% | 13.61% | 12.16% |

### C. Verdict + reconciliation

**The vol asymmetry is real: the rv_60d gate fires risk-off into a genuinely higher-volatility forward regime, not noise.** In the clean window, gate-OFF months average 22.19% forward realized vol vs 12.95% for gate-ON months -- a 1.7x vol step. Critically, the asymmetry holds even when the gate is 'wrong' on direction: the FALSE-POSITIVE cohort (SPY rose, +4.11% mean) still carries 15.96% forward vol, ABOVE the 12.95% gate-ON baseline, while the TRUE-POSITIVE cohort (SPY fell, -5.32% mean) carries 29.94% forward vol. So even the de-risk decisions that 'missed' upside landed in elevated-risk regimes; the gate is selecting real vol regimes, not random months. Mean forward return across all gate-OFF months is roughly flat (-0.10% clean / +0.11% ext) but at ~1.7x the volatility of gate-ON months -- a poor risk-adjusted payoff that justifies stepping aside. The ext window confirms it (gate-OFF 20.88% vs gate-ON 13.61% fwd vol; TP 27.24% vs FP 16.01%).

**Reconciliation with prior logs:** `rv_gate_cohort_calibration_findings.md` computed cohorts on the OLD rv_20d gate AND on the narrower 'blocked-month' subset (canary_ok AND trend_ok AND NOT vol_ok), reporting clean TP fwd vol ~21.1% vs FP ~11.8% on 41 blocked months. This fresh computation uses the CURRENT rv_60d gate over the FULL vol-gate-OFF set (74 clean months) and finds the SAME directional asymmetry but a WIDER spread (TP 29.94% vs FP 15.96%). Both agree on the core claim; the rv_60d full-set view is the cleaner test of the production gate and shows the asymmetry more strongly. (Note: the prior log's separate EV-decomposition point -- that forgone FP gains slightly exceed avoided TP losses in raw return terms -- is a return argument, not a vol argument; it does not contradict the vol-asymmetry justification, which is about risk-adjusted exposure, not unconditional return.)


## D. Asset Concentration / Contribution Share (all 8 risky assets, incl EEM)

**Config:** CPM sleeve, headline config (504d cov, top-K=4, slow-gate-independent), T+1 MOO weight placement. Contribution_i = sum over days of (weight_i * close-to-close daily return_i) within the window (arithmetic attribution of the headline-config weight vector). Risky-share = each asset's contribution as a fraction of the total of all 8 risky-asset contributions (sums to 100%); the safe leg (SHV/IEF cash) contribution is reported separately for completeness.
**Universe (8 risky):** QQQ, SPHQ, EFA, EEM, VNQ, GLD, TLT, DBC.
**Windows:** clean 2008-05-30..2026-05-22; ext 1999-03-10..2026-05-22.


### D. CPM-sleeve per-asset contribution [clean, mooex weight placement]

| asset | contribution (sum w*r) | share of 8 risky | avg weight (time-in-asset) |
|---|---:|---:|---:|
| QQQ | 43.26 pp | 17.6% | 9.5% |
| SPHQ | 68.94 pp | 28.1% | 28.9% |
| EFA | 21.95 pp | 8.9% | 7.9% |
| EEM | 0.99 pp | 0.4% | 0.7% |
| VNQ | 8.31 pp | 3.4% | 1.3% |
| GLD | 53.45 pp | 21.8% | 14.1% |
| TLT | 28.61 pp | 11.7% | 14.9% |
| DBC | 19.79 pp | 8.1% | 9.2% |
| **8 risky total** | 245.29 pp | 100.0% | - |
| safe leg (SHV/IEF) | 25.55 pp | (excl.) | 20.8% |

### D. CPM-sleeve per-asset contribution [ext, mooex weight placement]

| asset | contribution (sum w*r) | share of 8 risky | avg weight (time-in-asset) |
|---|---:|---:|---:|
| QQQ | 75.68 pp | 20.4% | 8.3% |
| SPHQ | 62.24 pp | 16.8% | 20.2% |
| EFA | 38.90 pp | 10.5% | 8.4% |
| EEM | 2.15 pp | 0.6% | 2.6% |
| VNQ | 41.74 pp | 11.3% | 8.9% |
| GLD | 60.64 pp | 16.4% | 12.7% |
| TLT | 37.65 pp | 10.2% | 18.4% |
| DBC | 51.62 pp | 13.9% | 9.4% |
| **8 risky total** | 370.63 pp | 100.0% | - |
| safe leg (SHV/IEF) | 34.39 pp | (excl.) | 16.8% |

No asset is silently dropped: EEM appears explicitly above with its own contribution share and average weight.

**Read:** EEM is a near-dormant member of the trend universe under the headline config -- 0.4% of clean risky contribution at 0.7% average weight (0.6% / 2.6% ext) -- it rarely ranks into the top-K=4 and is rarely selected into the min-variance pair, but it is NOT excluded from the universe and is shown here for completeness. Clean-window contribution concentrates in SPHQ (28.1%), GLD (21.8%) and QQQ (17.6%); the ext window is more balanced (QQQ 20.4%, SPHQ 16.8%, GLD 16.4%, DBC 13.9%). The eight risky shares sum to 100% by construction; the safe leg (SHV/IEF, ~21% average weight clean) is reported separately and is additive to the sleeve's total return.

## E. Rolling-Window Stability Methodology (cite-ready)

The rolling-window stability metrics in `research/two_sleeve_60_40_ci_walkforward.py` (`rolling_sharpe`) use **calendar-day** lookbacks, not a fixed trading-day count. For an N-year window the lookback is `days_lookback = int(N * 365.25)` calendar days, i.e. 1095 calendar days for the 3-year window and 1826 calendar days for the 5-year window. The rolling series starts at `daily.index[0] + days_lookback` and is evaluated on every trading day from that point forward; at each date `d` the window is the calendar slice `daily.loc[d - days_lookback : d]`. A window is skipped (NaN) unless it contains at least **100 trading days** of returns (the min-observations cutoff). Within each window the Sharpe is the raw (zero risk-free) annualized Sharpe: `(mean(daily) * 252) / (std(daily, ddof=0) * sqrt(252))`, so the **annualization factor is 252** and volatility uses the population standard deviation (`ddof=0`). The worst-contiguous-stretch scan (`worst_contiguous`) uses the same `int(N * 365.25)` calendar-day window length and the same >=100 trading-day floor, stepping the window start across every trading day. Because the windows are calendar-based, the actual number of trading days per window is approximately 252 * N (about 756 for 3y and about 1260 for 5y) but varies slightly with holidays and is not held fixed.
