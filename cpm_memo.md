# CPM Research Memo

Current state: monthly ETF implementation, standardized to 252-day volatility windows for both ranking and risky-block inverse-vol weighting. Clean window uses full real-open coverage. Extended window includes proxy-backed pre-ETF segments. Metrics are post-cost and use month-end signal with next-session-open execution.

Scope: this memo evaluates CPM (cross-asset top-4 Faber vol-adjusted momentum, HYG-or-TIP canary, breadth-scaled partial-safe routing, SHV/IEF safe selector). Sleeve overlays are out of scope.


## 0. Header and metadata

- Strategy: CPM (Cross-asset Parity Momentum).
- Production standardization: rank-vol 252d and weight-vol 252d.
- Risky universe: QQQ, SPHQ, EFA, EEM, VNQ, GLD, TLT, DBC.
- Safe assets: SHV, IEF.
- Windows:
  - Clean: 2008-05-30 to 2026-05-22 (18.0 years).
  - Extended: 1995-01-31 to 2026-05-22 (proxy-informed robustness window).
- Costs: 10 bps per side, embedded in all tables.
- Sharpe convention: raw Sharpe (rf = 0) and excess Sharpe versus SHV.
- Rebalance and leverage: monthly rebalance, unlevered.
- Execution convention: signal at month-end close, trade at next-session open (T+1 MOO).


## 1. Executive summary

- RETURN PROFILE: Clean in-sample Sharpe is 1.1658. Forward expectation remains about 0.72 (0.62-0.85) after selection, execution, and regime haircuts. This is capital-preservation-first, not raw-return maximization.

- TAIL CONTROL: Clean MaxDD is -12.97% versus -21.76% (AAA-style available-panel benchmark), -29.82% (60/40), -26.59% (naive 12m momentum), and -34.75% (buy-hold inverse-vol).

- BENCHMARK INTERPRETATION: Versus AAA-style and 60/40, point gaps remain economically large, but clean-window Sharpe difference CIs include zero. Versus naive 12m and buy-hold inverse-vol, Sharpe difference CIs exclude zero.

- CRITICAL VULNERABILITY: Month-end alignment is load-bearing. With production both-252, signal/rebalance offset Sharpe is 1.1658 (EOM), 0.9743 (EOM+1), 0.9628 (EOM+2), 0.8714 (EOM+3).

- PEER FRAMING: CPM is a hybrid. It combines AAA-style inverse-vol weighting, FAA/EAA-style risk-adjusted ranking, and HAA-style canary-plus-breadth defense. HAA is the closest single overall published peer.

- CONCLUSION STATUS: Verdict is tail-control-first with favorable benchmark point estimates. Weighting Sharpe edge versus equal-weight is small (+0.0341), and longest underwater duration is 789 days.

Turnover:
- Clean: 2.582 one-way per year, 13.4% fully-safe months.
- Extended: about 2.58 one-way per year, 10.1% fully-safe months.


## 2. Investment thesis and economic rationale

Cross-asset time-series momentum can persist across risk-on and risk-off cycles because flows and risk budgets adjust with lag. CPM uses breadth-scaled cross-asset momentum: rank assets by 10-month trend strength per unit of realized volatility, keep positive-trend assets, select top four, inverse-vol weight survivors, route unused risky slots to timed safe asset.

"Parity" here means inverse-vol weighting in the risky block, not covariance optimization. Strict-4 partial-safe makes risky exposure proportional to breadth: if fewer than four assets pass, missing slots route to SHV or IEF.

HYG-or-TIP canary is permissive by design. Trend, rank, screen, and partial-safe routing do most risk control work; canary adds an extra permission layer.


### 2.1 Execution-timing cliff and operational risk

Terminology:
- Signal date: month-end close used to compute rank, canary, and safe selector.
- Fill convention: execution price after fixed signal date.
- Signal/rebalance-date offset: shifting signal date away from true month-end.

Production both-252 offset test:
- EOM: 1.1658
- EOM+1: 0.9743
- EOM+2: 0.9628
- EOM+3: 0.8714

Read:
- Offset cliff remains real in both-252.
- This is a monthly-TAA trait, not unique to CPM, but CPM is least affected versus steeper cliffs in simple AAA/HAA monthly variants.


## 3. Strategy specification


### 3.1 Signal definitions

Let monthly sampled close series be built with `resample("ME").last()`.

- 13612U momentum:
  - `m_13612U = (r_1 + r_3 + r_6 + r_12) / 4`.
- 10-month trend distance:
  - `m_faber = price / SMA_10m - 1`.
- Realized volatility:
  - `rv_252d = stdev(simple daily returns, 252d) * sqrt(252)`.


### 3.2 CPM rule stack

1. Compute rank value `m_faber / rv_252d` for each risky asset in {QQQ, SPHQ, EFA, EEM, VNQ, GLD, TLT, DBC}.
2. Keep only assets with `m_faber > 0`.
3. Keep top 4.
4. If canary is off, allocate 100% to safe selector.
5. If canary is on:
   - `n_pos = number of survivors (0..4)`
   - `risky_fraction = min(n_pos, 4) / 4`
   - `safe_fraction = 1 - risky_fraction`
   - risky block uses inverse-vol weights proportional to `1 / rv_252d` across survivors
   - safe block goes to timed SHV or IEF by 13612U

Strict-4 partial-safe behavior:
- n_pos = 0 -> 0/4 risky, 4/4 safe
- n_pos = 1 -> 1/4 risky, 3/4 safe
- n_pos = 2 -> 2/4 risky, 2/4 safe
- n_pos = 3 -> 3/4 risky, 1/4 safe
- n_pos = 4 -> 4/4 risky, 0/4 safe


### 3.3 Canary and safe selector

- Canary on if `m_13612U(HYG) > 0 OR m_13612U(TIP) > 0`.
- Safe selector chooses argmax `m_13612U` over {SHV, IEF}.


### 3.4 Parameter table

| Component | Parameter | Value |
|---|---|---|
| Trend risky universe size | N | 8 |
| Trend selection count | K | 4 |
| Trend rank value | Rank metric | m_faber / rv_252d |
| Trend positivity filter | Threshold | m_faber > 0 |
| Risky block weighting | Rule | inverse-vol over survivors |
| Risky fraction control | Rule | strict-4 partial-safe, min(n_pos,4)/4 |
| Risky-block inverse-vol lookback | Window | 252 trading days |
| Canary | Rule | m_13612U(HYG) > 0 OR m_13612U(TIP) > 0 |
| Safe selector | Rule | argmax m_13612U over SHV, IEF |
| Transaction cost | Side cost | 10 bps |
| Rebalance frequency | Cadence | monthly |
| Leverage | Gross leverage | 1.0x |
| Execution | Fill convention | next-session open |


## 4. Data and methodology

- Data panel uses live ETFs where available plus audited proxy stitches in pre-ETF segments.
- Clean window is decision lens: 2008-05-30 to 2026-05-22.
- Extended window is proxy-informed robustness lens: 1995-01-31 to 2026-05-22.
- Execution is month-end signal, next-session-open fill (T+1 MOO exact).
- Reduced-universe engine behavior in early history is unchanged.


## 5. Headline results


### 5.1 CPM headline metrics

Clean anchor (decision lens): Sharpe 1.1658, MaxDD -12.97%, Calmar 1.0137.

| Window | Sharpe | CAGR | Vol | MaxDD | Calmar | Martin | Ulcer | Excess Sharpe vs SHV |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Clean | 1.1658 | 13.15% | 11.18% | -12.97% | 1.0137 | 3.6907 | 3.56% | 1.0469 |
| Extended (proxy-informed robustness) | 1.2491 | 13.74% | 10.72% | -15.73% | 0.8736 | 3.8437 | 3.58% | 0.9841 |

Clean worst drawdown is 2025-04 tariff selloff: peak 2025-02-19, trough 2025-04-08, depth -12.97%, recovery 2025-06-12.

Extended worst drawdown remains a proxy-era 2006 episode at -15.73%.


### 5.2 Crisis behavior

Global drawdown episodes (extended continuous-curve basis):

| Crisis | Peak | Trough | Depth | Recovery | Trough to recovery |
|---|---|---|---:|---|---:|
| LTCM (1998) | 1998-07-20 | 1998-09-02 | -9.07% | 1999-01-29 | +149d |
| Dot-com era in-window dip | 2002-05-29 | 2002-07-24 | -6.03% | 2002-08-29 | +36d |
| GFC (2008) | 2008-03-14 | 2008-10-14 | -11.88% | 2008-12-16 | +63d |
| COVID (2020) | 2020-03-06 | 2020-03-18 | -10.11% | 2020-04-16 | +29d |
| 2022 path slice | 2021-11-24 | 2022-01-27 | -8.32% | 2024-01-22 | +725d |

Within-calendar windows:

| Crisis window | MaxDD | Return |
|---|---:|---:|
| GFC (2007-10..2009-06) | -11.88% | 11.56% |
| COVID (2020-02..2020-06) | -10.50% | 6.67% |
| 2022 bear (2022-01..2022-12) | -7.96% | -2.08% |


### 5.3 Bootstrap confidence interval (clean Sharpe)

Clean-window Sharpe bootstrap interval (stationary block bootstrap, B=2000, block=21 trading days, seed=42).

| Statistic | Value |
|---|---:|
| point | 1.1658 |
| 2.5% | 0.7866 |
| 50% | 1.1964 |
| 97.5% | 1.5969 |

Method: stationary block bootstrap, B=2000, block=21 trading days, seed=42.


### 5.4 Turnover and fully-safe months

| Window | One-way turnover per year | Fully-safe months |
|---|---:|---:|
| Clean | 2.582 | 13.4% |
| Extended (proxy-informed robustness) | about 2.58 | 10.1% |


### 5.5 Benchmarks and significance

Clean window:

| Series | Sharpe | CAGR | MaxDD | Calmar | Martin |
|---|---:|---:|---:|---:|---:|
| CPM | 1.17 | 13.15% | -12.97% | 1.01 | 3.69 |
| AAA-style available-panel benchmark | 0.94 | 9.23% | -21.76% | 0.42 | 1.62 |
| 60/40 (SPY/IEF) | 0.79 | 8.75% | -29.82% | 0.29 | 1.40 |
| Naive 12m momentum (no canary, equal-weight) | 0.65 | 8.14% | -26.59% | 0.31 | 1.02 |
| Buy-hold inverse-vol | 0.66 | 7.88% | -34.75% | 0.23 | 1.03 |

Sharpe difference test (CPM minus benchmark, paired block bootstrap, 95% CI):

| Comparator | dSharpe | 95% CI | Includes zero? |
|---|---:|---|---|
| AAA-style available-panel benchmark | +0.22 | [-0.113, +0.589] | Yes |
| 60/40 | +0.37 | [-0.093, +0.791] | Yes |
| Naive 12m | +0.52 | [+0.166, +0.889] | No |
| Buy-hold inverse-vol | +0.51 | [+0.090, +0.895] | No |

Drawdown-adjusted point gaps (CPM minus benchmark):

| Metric | AAA-style | 60/40 | Naive 12m | Buy-hold inverse-vol |
|---|---:|---:|---:|---:|
| MaxDD gap (pp, positive = shallower CPM) | +8.79 | +16.85 | +13.62 | +21.78 |
| Calmar difference | +0.5896 | +0.7201 | +0.7076 | +0.7869 |
| Martin difference | +2.068 | +2.288 | +2.671 | +2.656 |

Read:
- Versus AAA-style and 60/40, evidence is favorable but statistically unresolved on Sharpe in this sample length.
- Versus naive 12m and buy-hold inverse-vol, Sharpe edge remains statistically clear.

Extended per-series table (proxy-informed robustness, mixed starts):

| Series | Start | Sharpe | CAGR | MaxDD | Calmar | Martin |
|---|---|---:|---:|---:|---:|---:|
| CPM | 1995-01-31 | 1.25 | 13.74% | -15.73% | 0.87 | 3.84 |
| AAA-style available-panel benchmark | 2008-01-19 | 0.93 | 9.07% | -21.76% | 0.42 | 1.60 |
| 60/40 | 1999-03-10 | 0.69 | 7.31% | -31.44% | 0.23 | 1.07 |
| Naive 12m momentum | 1999-03-10 | 0.82 | 10.11% | -26.59% | 0.38 | 1.43 |
| Buy-hold inverse-vol | 1999-03-10 | 0.81 | 9.24% | -35.44% | 0.26 | 1.37 |


### 5.6 Common-window extended comparison

All-series common start (2008-01-19):

| Series | Sharpe | CAGR | MaxDD | Calmar | Martin |
|---|---:|---:|---:|---:|---:|
| CPM | 1.165 | 13.16% | -12.97% | 1.014 | 3.629 |
| AAA-style available-panel | 0.930 | 9.07% | -21.76% | 0.417 | 1.603 |
| 60/40 (SPY/IEF) | 0.798 | 8.81% | -30.83% | 0.286 | 1.372 |
| Naive 12m momentum | 0.665 | 8.48% | -26.59% | 0.319 | 1.067 |
| Buy-hold inverse-vol | 0.684 | 8.26% | -35.44% | 0.233 | 1.067 |

Ex-AAA common start (1999-03-10):

| Series | Sharpe | CAGR | MaxDD | Calmar | Martin |
|---|---:|---:|---:|---:|---:|
| CPM | 1.200 | 13.48% | -15.73% | 0.857 | 3.676 |
| 60/40 (SPY/IEF) | 0.691 | 7.31% | -31.44% | 0.232 | 1.071 |
| Naive 12m momentum | 0.816 | 10.11% | -26.59% | 0.380 | 1.428 |
| Buy-hold inverse-vol | 0.813 | 9.24% | -35.44% | 0.261 | 1.372 |


### 5.7 Calendar-year returns and intra-year drawdown (clean window)

Boundary-year note: 2008 and 2026 are partial years for at least one series and are not cross-series comparable.

| Year | CPM ret | CPM intraDD | AAA ret | AAA intraDD | 60/40 ret | 60/40 intraDD |
|---|---:|---:|---:|---:|---:|---:|
| 2008* | +5.27% | -10.23% | +1.66% | -11.74% | -15.57% | -26.88% |
| 2009 | +14.26% | -7.07% | +0.80% | -11.03% | +13.23% | -17.62% |
| 2010 | +16.00% | -9.19% | +15.59% | -8.38% | +13.42% | -6.95% |
| 2011 | +9.23% | -7.79% | +8.99% | -10.42% | +8.29% | -8.56% |
| 2012 | +6.89% | -4.87% | -3.53% | -10.14% | +11.26% | -4.20% |
| 2013 | +18.99% | -9.24% | +23.75% | -8.34% | +15.60% | -5.24% |
| 2014 | +15.84% | -6.08% | +9.60% | -4.29% | +11.95% | -3.39% |
| 2015 | -1.14% | -6.80% | -1.00% | -6.48% | +1.76% | -6.94% |
| 2016 | +10.16% | -9.60% | +1.71% | -8.15% | +7.80% | -3.87% |
| 2017 | +22.33% | -2.33% | +10.58% | -3.30% | +13.76% | -1.49% |
| 2018 | +1.04% | -10.08% | +0.77% | -8.94% | -1.96% | -10.83% |
| 2019 | +12.73% | -3.85% | +9.18% | -3.03% | +21.78% | -2.68% |
| 2020 | +21.77% | -10.50% | +19.80% | -7.88% | +16.90% | -19.13% |
| 2021 | +27.28% | -4.51% | +25.42% | -5.70% | +15.10% | -3.70% |
| 2022 | -2.08% | -7.96% | -14.25% | -21.76% | -16.39% | -20.67% |
| 2023 | +1.85% | -7.75% | +7.80% | -9.17% | +16.97% | -8.26% |
| 2024 | +15.24% | -7.19% | +17.87% | -6.14% | +14.23% | -4.36% |
| 2025 | +25.78% | -12.97% | +19.12% | -6.29% | +14.33% | -10.60% |
| 2026* | +21.44% | -5.69% | +21.70% | -6.07% | +4.71% | -6.00% |


### 5.8 Worst-interval and underwater-duration table (clean window)

| Metric | CPM | AAA-style | 60/40 |
|---|---:|---:|---:|
| Worst 1-month return | -5.85% | -7.08% | -9.77% |
| Worst 3-month return | -7.34% | -10.24% | -15.37% |
| Worst 12-month return | -5.21% | -16.86% | -16.39% |
| Longest underwater | 789 days | 903 days | 787 days |


### 5.9 HAA benchmark and decomposition

Canonical HAA head-to-head (same engine, costs, and window handling):

| Strategy | Window | Sharpe | Calmar | MaxDD | CAGR |
|---|---|---:|---:|---:|---:|
| HAA | Clean | 0.87 | 0.64 | -14.68% | 9.37% |
| CPM | Clean | 1.17 | 1.01 | -12.97% | 13.15% |

Mechanism-vs-universe split (clean):

| Configuration | Sharpe | Calmar | MaxDD |
|---|---:|---:|---:|
| HAA baseline | 0.87 | 0.64 | -14.68% |
| CPM machinery on HAA universe | 0.96 | 0.64 | -15.69% |
| CPM full | 1.17 | 1.01 | -12.97% |

Edge split (clean):
- Machinery piece: +0.09 Sharpe, about 0.00 Calmar, MaxDD slightly worse by 1.01 pp.
- Universe piece: +0.21 Sharpe, +0.38 Calmar, MaxDD better by 2.72 pp.
- Total CPM minus HAA: +0.30 Sharpe, +0.38 Calmar, +1.71 pp MaxDD improvement.

HAA-to-CPM factorial ladder (2^5 cube, clean background-averaged unless noted) complements Appendix A's AAA-to-CPM decomposition.

Per-factor main effects:

| Factor | dSharpe | dCalmar | dMaxDD | Robust? |
|---|---:|---:|---:|---|
| Universe | +0.1821 | +0.2295 | +0.75pp | yes (no sign flip) |
| Risk-adjusted ranker | +0.0634 | +0.0603 | +0.56pp | sign-flips across backgrounds |
| Inverse-vol weighting | +0.0297 | +0.0192 | +0.68pp | Calmar flips |
| Credit canary (HYG-or-TIP) | +0.0257 | +0.0777 | +0.13pp | Calmar robust |
| Trend screen | +0.0032 | -0.0414 | -1.02pp | flips, mildly negative |

Extended main effects for completeness (dSharpe/dCalmar): Universe +0.1154/+0.1013; Credit canary +0.0332/+0.0310; Risk-adjusted ranker +0.0265/-0.0091; Inverse-vol weighting +0.0198/+0.0194; Trend screen -0.0096/-0.0371.

Sequential ladder (canonical order: credit canary -> risk-adjusted ranker -> inverse-vol weighting -> trend screen -> universe):

| Step | Sharpe | Calmar | MaxDD |
|---|---:|---:|---:|
| HAA baseline | 0.8670 | 0.6386 | -14.68% |
| +Credit canary | 0.8929 | 0.7689 | -13.35% |
| +Risk-adjusted ranker | 0.9053 | 0.7088 | -14.12% |
| +Inverse-vol weighting | 0.9576 | 0.7618 | -12.97% |
| +Trend screen | 0.9575 | 0.6350 | -15.69% |
| +Universe (=CPM) | 1.1658 | 1.0137 | -12.97% |

Order-dependence note: adding universe first captures most of the edge immediately (HAA 0.8670/0.6386 -> +Universe 1.0189/0.7693), then mechanism factors layer additively; either way the universe swap is where the edge lives.

Key two-way interactions (clean Calmar):

| Interaction | Delta |
|---|---:|
| Risk-adjusted ranker x universe | +0.0787 |
| Trend screen x universe | +0.0537 |
| Inverse-vol weighting x universe | -0.0163 |
| Credit canary x universe | +0.0140 |

Reading: risk-adjusted ranker and trend screen pay off mostly on the CPM universe (complements to the universe, not standalone gains); credit canary is roughly universe-independent.

Honest takeaway: universe is the only first-order robust driver; credit canary is the only robustly valuable mechanism delta (largest Calmar step); ranker and weighting are second-order and interaction-dependent; trend-screen change is immaterial-to-negative.

Caveat: this is one in-sample path; many mechanism effects flip sign across backgrounds, so trust direction and robustness over tiny decimals.


## 6. CPM decomposition (2^6, faithful AAA baseline to production CPM)

Main takeaways:
- R and U remain top contributors.
- C, S, and P are protection-biased.
- W is modest and regime-dependent.
- The all-ON endpoint is the production configuration (rank-vol and weight-vol both 252d).


## 7. Design notes


### 7.1 Ranker comparison

Vol-adjusted Faber ranker is above plain momentum alternatives in clean and extended robustness sweeps. Effect size is similar across windows.


### 7.2 Universe analysis

Universe effect remains positive on Sharpe and Calmar, with interaction terms (especially U x R) carrying large attribution weight.


### 7.3 Weighting interpretation

Versus equal-weight, inverse-vol weighting has a small Sharpe edge (+0.0341) and near-tie Calmar in clean results.

- Factorial main effect for W (clean): dSharpe -0.0159, dCalmar +0.0343.
- Production inverse-vol versus equal-weight (clean):
  - Sharpe: 1.1658 vs 1.1317 (+0.0341)
  - Calmar: 1.0137 vs 1.0147 (near tie)
  - MaxDD: -12.97% vs -13.05%

Read:
- Inverse-vol is a free risk-parity simplification.
- At both-252, Sharpe help is small and Calmar is near flat versus equal-weight.
- Keep it for parsimony and stable behavior, not as a primary alpha claim.


### 7.4 Asset concentration (risky contribution share)

| Asset | Clean share | Extended share |
|---|---:|---:|
| QQQ | 21.7% | 18.5% |
| SPHQ | 18.7% | 11.0% |
| GLD | 15.5% | 13.2% |
| EFA | 12.5% | 14.8% |
| EEM | 9.0% | 13.9% |
| VNQ | 8.2% | 12.4% |
| TLT | 7.3% | 6.3% |
| DBC | 7.1% | 10.0% |

Clean top-3 share: 55.9%.


### 7.5 Peer framing (hybrid)

CPM framing used in this memo:
- AAA-style inverse-vol weighting lineage.
- FAA/EAA-style risk-adjusted ranking lineage.
- HAA-style canary-plus-breadth defense lineage.

Closest single overall peer is HAA because universe overlap and defense structure are both near-identical.

Cash-instrument note:
- HAA literature uses BIL; this implementation uses SHV for longer history.
- SHV vs BIL is treated as cosmetic instrument wash, not a design edge.


### 7.6 Factor stability across halves (marginal dSharpe at production)

| Factor | 2008-16 | 2017-26 |
|---|---:|---:|
| R (ranker) | +0.28 | +0.14 |
| U (universe) | +0.25 | +0.10 |
| W (inverse-vol weighting) | +0.06 | +0.00 |
| C (canary) | +0.15 | -0.07 |
| S (positive-trend screen) | +0.04 | -0.00 |
| P (strict-4 partial-safe) | +0.07 | +0.02 |

Subperiod all-ON Sharpe:
- 2008-16: 0.97
- 2017-26: 1.35

Read:
- Return engine stability remains in R and U.
- W stays small, nearly flat post-2016.
- Protection factors are crisis-concentrated.


## 8. Statistical honesty and caveats

Lead honesty statement:
- Signal survives selection-deflation checks decisively.
- Production setup is still selected in-sample.
- Forward uncertainty is dominated by execution timing and regime non-stationarity.

Three-number framing:
- In-sample peak: 1.17.
- Selection-deflated in-sample: about 0.96.
- Forward expectation: about 0.72 (0.62-0.85).


### 8.1 Forward-Sharpe haircut ladder

| Step | Type | Factor (central / band) | Resulting Sharpe |
|---|---|---|---:|
| 0. In-sample argmax (clean, T+1 MOO) | measured | -- | 1.17 |
| 1. Selection de-peak | measured (DSR) | x 0.82 / [0.79, 0.86] | about 0.96 (0.92-1.00) |
| 2. Execution-realism haircut | judgmental | x 0.85 / [0.765, 0.93] | about 0.81 (0.70-0.93) |
| 3. Regime non-stationarity haircut | judgmental | x 0.88 / [0.80, 0.95] | about 0.72 (0.62-0.85) |
| Forward central | synthesis | -- | about 0.72 (0.62-0.85) |


### 8.2 DSR appendix inputs

Measured inputs:

| Input | Value |
|---|---:|
| Observed SR_hat (per-day) | 0.07343 (ann 1.1656) |
| n (daily obs) | 4524 |
| skew | -0.3682 |
| excess kurtosis | 4.0204 |
| V_trials (grid SR variance, per-day) | 2.094e-5 (std 0.073 ann) |

Assumed input:

| Input | Value |
|---|---|
| Effective independent trials N | about 50-300 (central about 150) |

Expected-max SR0 and deflated z by N (daily frame):

| N | SR0 (ann) | DSR | z |
|---|---:|---:|---:|
| 40 | 0.159 | 1.0000 | 4.19 |
| 80 | 0.178 | 1.0000 | 4.11 |
| 200 | 0.201 | 1.0000 | 4.02 |
| 500 | 0.222 | 1.0000 | 3.93 |
| 1000 | 0.236 | 0.9999 | 3.87 |
| 2000 | 0.250 | 0.9999 | 3.81 |

Monthly-frame z range is 4.63 to 5.02, so reported z band is 3.81 to 5.02.


## 9. Robustness and reviewer-response notes

- Vol-window standardization to both-252 is statistically free in paired bootstrap comparisons versus split-window and both-504 alternatives; differences include zero.
- Ensemble variant was dropped: extra complexity for about 0.015 Sharpe gain is not worth it.
- Bond-buffer plus leverage was rejected: CPM already de-risks, and leverage failed on matched-vol comparisons.
- Vol-cap overlay was rejected: broad dilution for protection concentrated in one episode (2025-04).
- Execution cliff is generic monthly-TAA behavior; CPM remains least-affected among tested peers.
- Implied-vol add-ons have low prior due long-history coverage gaps.
- Worst clean drawdown remains 2025-04 tariff selloff, not a classic crisis cluster.


### 9.1 Leave-one-asset-out (clean window)

| Dropped | Sharpe | dSharpe | MaxDD | Calmar | dCalmar |
|---|---:|---:|---:|---:|---:|
| (none) baseline | 1.1658 | -- | -12.97% | 1.0137 | -- |
| ex-QQQ | 0.9934 | -0.1724 | -11.60% | 0.8904 | -0.1233 |
| ex-SPHQ | 1.0068 | -0.1589 | -12.41% | 0.8759 | -0.1378 |
| ex-EFA | 1.1609 | -0.0049 | -11.62% | 1.0693 | +0.0556 |
| ex-EEM | 1.1897 | +0.0239 | -11.08% | 1.1282 | +0.1145 |
| ex-VNQ | 1.0905 | -0.0752 | -13.96% | 0.8462 | -0.1675 |
| ex-GLD | 1.0404 | -0.1253 | -14.45% | 0.8222 | -0.1915 |
| ex-TLT | 1.0581 | -0.1077 | -13.98% | 0.8859 | -0.1278 |
| ex-DBC | 1.1035 | -0.0623 | -12.55% | 0.9886 | -0.0251 |


### 9.2 Volatility-lookback standardization

| Setup | Sharpe | MaxDD | Calmar |
|---|---:|---:|---:|
| Production both-252 | 1.1658 | -12.97% | 1.0137 |
| Split-window 252/504 | 1.1910 | -12.67% | 1.0615 |
| Both-504 | 1.2039 | -13.73% | 0.9877 |

Paired bootstrap (both-252 minus alternatives) includes zero for Sharpe, Calmar, and Martin.


### 9.3 US-equity de-tilt

| Setup | Universe | Sharpe | MaxDD | Calmar |
|---|---|---:|---:|---:|
| Production | QQQ,SPHQ,EFA,EEM,VNQ,GLD,TLT,DBC | 1.1658 | -12.97% | 1.0137 |
| De-tilt SPY | SPY,EFA,EEM,VNQ,GLD,TLT,DBC | 0.9884 | -11.98% | 0.8652 |

Ticker swaps (dSharpe versus matched baseline):
- QQQ->VUG: -0.035
- QQQ->IWF: -0.036
- QQQ->IWD: -0.087
- SPHQ->QUAL: about 0.000
- SPHQ->MTUM: -0.072

Read:
- De-tilted setup still sits above SPY buy-hold and 60/40 Sharpe.
- Growth/quality tilt is additive, not sole edge source.


## 10. Governance


### 10.1 Falsification criteria (stop-using triggers)

| Trigger family | Falsification rule | Action |
|---|---|---|
| Execution-cost decay | Realized execution costs and slippage erase the expected net edge in live data | Pause new capital; run execution redesign review |
| Live drawdown breach | Live MaxDD moves materially beyond historical envelope (clean -12.97%, extended -15.73%) | Cut allocation and re-underwrite |
| Defensive failure | In crash windows, defensive routing fails to keep drawdown behavior better than simple passive baselines | Pause; re-check canary and safe routing |
| Rolling-36m Sharpe | Rolling 36m Sharpe < 0 | Stop deployment; re-approve before restart |
| Turnover blowout | Sustained turnover materially above the 2.58 one-way baseline without compensating edge | Freeze changes; investigate churn source |
| Canary lagging crashes | Credit canary no longer improves drawdown-adjusted outcomes in stress windows | Remove or replace canary rule |


### 10.2 CPM production rules as of 2026-06-01

- Risky universe: QQQ, SPHQ, EFA, EEM, VNQ, GLD, TLT, DBC.
- Canary: 13612U HYG-or-TIP, canary on if either is positive.
- Ranking: m_faber / rv_252d.
- Selection count: top 4.
- Positivity filter: m_faber > 0.
- Risky weighting: inverse-vol with 252-day realized volatility.
- Breadth routing: strict-4 partial-safe.
- Safe selector: SHV or IEF by higher 13612U.
- Rebalance and execution: monthly month-end signal, T+1 MOO fill.


### 10.3 Investment-decision table

| Decision state | Evidence needed | Current reading |
|---|---|---|
| Allocate | Clean Sharpe > 1, MaxDD materially shallower than 60/40, no trigger breach | Pass |
| Hold and monitor | Sharpe edge unresolved vs AAA/60-40 but still favorable point estimates | Pass |
| Cut or stop | Any falsification rule in 10.1 triggered | Not triggered in this memo snapshot |


## 11. Conclusion

CPM remains a tail-control-first cross-asset monthly system with favorable benchmark point estimates, unresolved Sharpe significance versus AAA/60-40 at this sample length, and clear edge versus naive momentum baselines.

Peer framing is now explicit: CPM is a hybrid of AAA-style weighting, FAA/EAA-style risk-adjusted ranking, and HAA-style defense. HAA is closest single published peer. CPM beats HAA on clean Sharpe and Calmar, but decomposition says most edge comes from universe choice, not machinery alone.

Forward expectation remains about 0.72 (0.62-0.85). Governance triggers define when to stop using CPM.


## 12. Reproduction appendix


### 12.1 Code pointers

- `cpm_live.py` (construction, canary, safe selector, backtest wiring)
- `build_dashboard.py` (reporting and summary generation)


### 12.2 Full parameter dictionary

| Key | Value |
|---|---|
| trend_universe | [QQQ, SPHQ, EFA, EEM, VNQ, GLD, TLT, DBC] |
| safe_pool | [SHV, IEF] |
| ranker | m_faber / rv_252d |
| trend_filter | m_faber > 0 |
| top_k | 4 |
| risky_weight_rule | inverse-vol over survivors (252d) |
| risky_fraction_rule | strict-4 partial-safe, min(n_pos,4)/4 |
| canary_rule | m_13612U(HYG) > 0 OR m_13612U(TIP) > 0 |
| safe_rule | argmax m_13612U over SHV and IEF |
| rebalance | monthly |
| execution | month-end close signal, next-session open fill |
| transaction_cost_per_side | 10 bps |
| leverage | unlevered |
| reporting_sharpe_rf | 0 |
| excess_sharpe_reference | SHV |


### 12.3 Window dates used in this memo

- Clean window: 2008-05-30 to 2026-05-22.
- Extended window: 1995-01-31 to 2026-05-22.


### 12.4 Source anchors

- both-252 findings memo in `research/`
- both-252 consolidated metrics JSON in `research/`
- `research/cpm_haa_benchmark_ladder_findings.md`
- `research/cpm_haa_benchmark_ladder.json`
- `research/cpm_closest_taa_peer_findings.md`


## Appendix A. 2^6 decomposition details (faithful AAA baseline to production CPM)

Baseline all-OFF is unchanged. All-ON endpoint is production both-252.

- Baseline all-OFF (000000): clean Sharpe 0.7869, MaxDD -23.21%, Calmar 0.3188; extended Sharpe 0.8696, Calmar 0.3624.
- All-ON production CPM (111111): clean Sharpe 1.1658, MaxDD -12.97%, Calmar 1.0137; extended Sharpe 1.2004, MaxDD -15.73%, Calmar 0.8571.

Main effects (ON minus OFF):

| Factor | Clean dSharpe | Clean dCalmar | Extended dSharpe | Extended dCalmar |
|---|---:|---:|---:|---:|
| Ranker (R) | +0.2041 | +0.2326 | +0.1007 | +0.1387 |
| Canary (C) | +0.1130 | +0.2100 | +0.0808 | +0.1800 |
| Universe (U) | +0.0857 | +0.0615 | +0.0593 | -0.0023 |
| Screen (S) | -0.0238 | +0.0469 | -0.0092 | +0.0374 |
| Weighting (W) | -0.0159 | +0.0343 | +0.0696 | +0.0957 |
| Partial-safe (P) | +0.0481 | +0.0876 | +0.0394 | +0.0816 |

Selected two-way interactions (Calmar deltas):

| Interaction | Clean dCalmar | Extended dCalmar |
|---|---:|---:|
| U x R | +0.1320 | +0.0997 |
| S x P | +0.0876 | +0.0769 |
| C x R | +0.0784 | +0.0480 |
| R x S | +0.0585 | +0.0382 |
| R x W | -0.0219 | -0.0099 |
| S x W | -0.0159 | +0.0017 |

Contribution ladder uses order R -> C -> U -> S -> P -> W:

| Step | Config | Clean Sharpe | Clean Calmar | Clean MaxDD | Extended Sharpe | Extended Calmar | Extended MaxDD |
|---|---|---:|---:|---:|---:|---:|---:|
| Baseline (all-OFF) | 000000 | 0.7869 | 0.3188 | -23.21% | 0.8696 | 0.3624 | -23.21% |
| +R | 001000 | 0.9128 | 0.3637 | -23.54% | 0.9350 | 0.3623 | -23.54% |
| +C | 101000 | 1.0527 | 0.7203 | -12.96% | 1.0153 | 0.6381 | -13.90% |
| +U | 111000 | 1.2062 | 0.7491 | -17.52% | 1.0950 | 0.6635 | -17.52% |
| +S | 111100 | 1.2310 | 1.0500 | -12.99% | 1.1384 | 0.7964 | -15.42% |
| +P | 111101 | 1.2655 | 1.0378 | -12.99% | 1.1540 | 0.7816 | -15.42% |
| +W (all-ON production) | 111111 | 1.1658 | 1.0137 | -12.97% | 1.2004 | 0.8571 | -15.73% |

Read:
- Decomposition is qualitatively consistent: R and U are top contributors, C/S/P are protection-biased, and W is modest and regime-dependent.
- W is now near-neutral to slightly negative on clean Sharpe in factorial attribution, while still positive on clean Calmar.
