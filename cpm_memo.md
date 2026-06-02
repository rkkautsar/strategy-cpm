# CPM Research Memo

Current state: monthly ETF implementation, standardized to both-252 (rank-vol 252d plus min-var covariance 252d). Clean window uses full real-open coverage. Extended window includes proxy-backed pre-ETF segments. Metrics are post-cost and use mooex (T+1 market-on-open execution): month-end signal with next-session-open execution.

Scope: this memo evaluates CPM (cross-asset top-4 Faber vol-adjusted momentum, TIP-only canary, equal-weight risky block, min-var 3-of-4 selection at full breadth, breadth-scaled partial-safe routing, SHV/IEF safe selector). Sleeve overlays are out of scope.


## 0. Header and metadata

- Strategy: CPM (Cross-asset Parity Momentum).
- CPM standardization: both-252 (rank-vol 252d and min-var covariance 252d).
- Risky universe: QQQ, SPHQ, EFA, EEM, VNQ, GLD, TLT, DBC.
- Safe assets: SHV, IEF.
- Windows:
  - Clean: 2008-05-30 to 2026-05-22 (18.0 years).
  - Extended: 1995-01-31 to 2026-05-22 (proxy-informed robustness window).
- Costs: 10 bps per side, embedded in all tables.
- Sharpe convention: raw Sharpe (rf = 0) and excess Sharpe versus SHV.
- Rebalance and leverage: monthly rebalance, unlevered.
- Execution convention: signal at month-end close, trade at next-session open (mooex, T+1 market-on-open execution).


## 1. Executive summary

AAA-style available-panel benchmark = peer-style control inspired by Adaptive Asset Allocation (Butler-Philbrick 2012): momentum rank, top-half selection, then min-variance weights on the CPM available panel. It is not an exact historical Adaptive Asset Allocation replication.

- RETURN PROFILE: Against HAA-style baseline, CPM improves clean Sharpe 0.8670 -> 1.2557. Universe is the only statistically clear symmetric main-effect contributor; min-var is significant only at the (U1,R1) corner (full universe + vol-adjusted ranker, before adding min-var) (+0.1682 Sharpe, near-flat MaxDD), not as a symmetric main effect. Forward underwriting remains about 0.72 (0.62-0.85), not the 1.2557 in-sample point.

- TAIL CONTROL: Clean MaxDD is -13.03% versus -21.76% (AAA-style available-panel benchmark), -29.82% (60/40), -26.59% (naive 12m momentum), and -34.75% (buy-hold vol-parity).

- BENCHMARK INTERPRETATION: Versus AAA-style and 60/40, point gaps remain economically large, but clean-window Sharpe difference CIs include zero. Versus naive 12m and buy-hold vol-parity, Sharpe difference CIs exclude zero.

- CRITICAL VULNERABILITY: Month-end alignment is load-bearing. With CPM standardization (both-252), signal/rebalance offset Sharpe is 1.2557 (EOM), 1.1867 (EOM+1), 1.0826 (EOM+2), 1.0028 (EOM+3).

- PEER FRAMING: CPM is a universe-sensitive HAA-family hybrid, not a fully portable generic engine. It combines equal-weight strict-4 risky allocation with min-var 3-of-4 full-breadth selection, FAA/EAA-style risk-adjusted ranking, and HAA-style canary-plus-breadth defense.

- STRUCTURAL READ: GLD/TLT replacing a redundant IEF/TLT risky-universe duration pair is the structural sleeve change; US equity sleeve is leadership plus quality (QQQ+SPHQ). Clean IWF+IWD sensitivity is only about 0.014 Sharpe lower, which supports anti-fragility to exact US-equity pair choice.

- CONCLUSION STATUS: Verdict is tail-control-first with favorable benchmark point estimates. Longest underwater is 789 days, not materially better than 60/40 at 787 days; edge is shallower drawdown depth and better worst-interval losses.

Turnover:
- Clean: 2.582 one-way per year, 13.4% fully-safe months.
- Extended: about 2.58 one-way per year, 10.1% fully-safe months.


## 2. Investment thesis and economic rationale

Cross-asset time-series momentum can persist across risk-on and risk-off cycles because flows and risk budgets adjust with lag. CPM uses breadth-scaled cross-asset momentum: rank assets by 10-month trend strength per unit of realized volatility, screen K=4 candidates, keep positive-trend survivors, and use equal risky weights. At full breadth (n_pos = 4), CPM evaluates all four equal-weight 3-of-4 subsets and holds the subset with the lowest estimated 252-day covariance-based portfolio variance before routing any unused risky slots to timed safe asset. Informal intuition only: this can resemble dropping the highest-variance contributor.

Strict-4 partial-safe makes risky exposure proportional to breadth: if fewer than four assets pass, missing slots route to SHV or IEF.

TIP-only canary is the CPM canary gate. Trend, rank, screen, and partial-safe routing do most risk control work; canary adds an extra permission layer.


### 2.1 Execution-timing cliff and operational risk

Terminology:
- Signal date: month-end close used to compute rank, canary, and safe selector.
- Fill convention: execution price after fixed signal date.
- Signal/rebalance-date offset: shifting signal date away from true month-end.

```
Offset cliff, mooex (T+1 MOO exact), CLEAN 18y, 10 bps/side -- PRIMARY
(EOM matches CPM clean anchor 1.2557)

Strategy   EOM     EOM+1   EOM+2   EOM+3   abs deg   % deg
CPM        1.2557  1.1867  1.0826  1.0028  -0.2528   -20.1%   (shallowest)
AAA-style  0.9542  0.5476  0.6287  0.6702  -0.2840   -29.8%   (steepest)
HAA        0.9821  0.7398  0.7489  0.7397  -0.2425   -24.7%

Corroboration, close-to-close exec_lag=0 (T+0 MOC economics), CLEAN 18y
(research/cpm_execution_cliff_peer_sanity_2026_06_01.json)

Strategy   EOM     EOM+1   EOM+2   EOM+3   % deg
CPM        1.2063  1.0127  0.9747  0.9090  -24.6%   (shallowest)
AAA-style  0.9961  0.5462  0.6675  0.6991  -29.8%   (steepest)
HAA-Simple 0.9839  0.7420  0.7613  0.7215  -26.7%
```

Read:
- Offset cliff remains real in both-252.
- This is a monthly-TAA trait, not unique to CPM; CPM is least affected versus AAA-style and HAA in both conventions.
- AAA-style mooex row falls back to close-to-close on rebalance days because open coverage is incomplete; the degradation ranking is unchanged in the close-to-close corroboration row.


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
2. Screen top 4 candidates by rank (`K = 4`).
3. Apply positivity filter `m_faber > 0` to those candidates; survivors count is `n_pos` (0..4).
4. If canary is off, allocate 100% to safe selector.
5. If canary is on:
   - `risky_fraction = min(n_pos, 4) / 4`
   - `safe_fraction = 1 - risky_fraction`
   - if `n_pos < 4`, hold all `n_pos` survivors at `1/4` each, with remaining slots routed to safe
   - if `n_pos = 4`, evaluate all four equal-weight 3-of-4 subsets (`_min_var_subset(..., m=3)`) and hold the subset with the lowest estimated 252-day covariance-based portfolio variance
   - safe block goes to timed SHV or IEF by 13612U

Strict-4 partial-safe behavior:
- n_pos = 0 -> 0/4 risky, 4/4 safe
- n_pos = 1 -> 1/4 risky, 3/4 safe
- n_pos = 2 -> 2/4 risky, 2/4 safe
- n_pos = 3 -> 3/4 risky, 1/4 safe
- n_pos = 4 -> 4/4 risky, 0/4 safe (implemented as 3 held risky names after min-var 3-of-4 subset selection)


### 3.3 Canary and safe selector

- Canary on if `m_13612U(TIP) > 0`.
- Safe selector chooses argmax `m_13612U` over {SHV, IEF}.


### 3.4 Parameter table

| Component | Parameter | Value |
|---|---|---|
| Trend risky universe size | N | 8 |
| Trend candidate screen count | K | 4 (screen count before full-breadth min-var hold rule) |
| Trend rank value | Rank metric | m_faber / rv_252d |
| Trend positivity filter | Threshold | m_faber > 0 |
| Risky block weighting | Rule | if n_pos < 4 hold all survivors at 1/4 each; if n_pos = 4 hold min-var 3-of-4 equal-weight within risky_fraction |
| Min-var selector at full breadth | Rule | at n_pos = 4, evaluate all four equal-weight 3-of-4 subsets and hold the subset with the lowest estimated 252-day covariance-based portfolio variance |
| Risky fraction control | Rule | strict-4 partial-safe, min(n_pos,4)/4 |
| Min-var covariance lookback | Window | 252 trading days |
| Canary | Rule | m_13612U(TIP) > 0 |
| Safe selector | Rule | argmax m_13612U over SHV, IEF |
| Transaction cost | Side cost | 10 bps |
| Rebalance frequency | Cadence | monthly |
| Leverage | Gross leverage | 1.0x |
| Execution | Fill convention | next-session open |


## 4. Data and methodology

- Data panel uses live ETFs where available plus audited proxy stitches in pre-ETF segments.
- Clean window is decision lens: 2008-05-30 to 2026-05-22.
- Extended window is proxy-informed robustness lens: 1995-01-31 to 2026-05-22.
- Execution is month-end signal, next-session-open fill (mooex T+1 exact).
- Reduced-universe engine behavior in early history remains unchanged.


## 5. Headline results


### 5.1 CPM headline metrics

Clean anchor (decision lens): Sharpe 1.2557, MaxDD -13.03%, Calmar 1.0076.

| Window | Sharpe | CAGR | Vol | MaxDD | Calmar | Martin |
|---|---:|---:|---:|---:|---:|---:|
| Clean | 1.2557 | 13.13% | 10.28% | -13.03% | 1.0076 | 4.2571 |
| Extended (proxy-informed robustness) | 1.2549 | 12.76% | 9.97% | -13.14% | 0.9712 | 4.1168 |

Clean worst drawdown is 2025-04 tariff selloff: peak 2025-02-19, trough 2025-04-08, depth -13.03%, recovery 2025-06-12.

Extended worst drawdown remains a proxy-era 2006 episode at -13.14%.


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
| point | 1.2557 |
| 2.5% | 0.8633 |
| 50% | 1.2573 |
| 97.5% | 1.6689 |

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
| CPM | 1.26 | 13.13% | -13.03% | 1.01 | 4.26 |
| AAA-style available-panel benchmark | 0.94 | 9.23% | -21.76% | 0.42 | 1.62 |
| 60/40 (SPY/IEF) | 0.79 | 8.75% | -29.82% | 0.29 | 1.40 |
| Naive 12m momentum (no canary, equal-weight) | 0.65 | 8.14% | -26.59% | 0.31 | 1.02 |
| Buy-hold vol-parity | 0.66 | 7.88% | -34.75% | 0.23 | 1.03 |

Sharpe difference test (CPM minus benchmark, paired block bootstrap, 95% CI):

| Comparator | dSharpe | 95% CI | Includes zero? |
|---|---:|---|---|
| AAA-style available-panel benchmark | +0.31 | [-0.066, +0.682] | Yes |
| 60/40 | +0.46 | [-0.019, +0.895] | Yes |
| Naive 12m | +0.61 | [+0.230, +0.987] | No |
| Buy-hold vol-parity | +0.60 | [+0.178, +0.991] | No |

Drawdown-adjusted point gaps (CPM minus benchmark):

| Metric | AAA-style | 60/40 | Naive 12m | Buy-hold vol-parity |
|---|---:|---:|---:|---:|
| MaxDD gap (pp, positive = shallower CPM) | +8.79 | +16.85 | +13.62 | +21.78 |
| Calmar difference | +0.5896 | +0.7201 | +0.7076 | +0.7869 |
| Martin difference | +2.068 | +2.288 | +2.671 | +2.656 |

Read:
- Versus AAA-style and 60/40, evidence is favorable but statistically unresolved on Sharpe in this sample length.
- Versus naive 12m and buy-hold vol-parity, Sharpe edge remains statistically clear.

Extended per-series table (proxy-informed robustness, mixed starts):

| Series | Start | Sharpe | CAGR | MaxDD | Calmar | Martin |
|---|---|---:|---:|---:|---:|---:|
| CPM | 1995-01-31 | 1.25 | 12.76% | -13.14% | 0.97 | 4.12 |
| AAA-style available-panel benchmark | 2008-01-19 | 0.93 | 9.07% | -21.76% | 0.42 | 1.60 |
| 60/40 | 1999-03-10 | 0.69 | 7.31% | -31.44% | 0.23 | 1.07 |
| Naive 12m momentum | 1999-03-10 | 0.82 | 10.11% | -26.59% | 0.38 | 1.43 |
| Buy-hold vol-parity | 1999-03-10 | 0.81 | 9.24% | -35.44% | 0.26 | 1.37 |


### 5.6 All-series post-availability comparison

Start floor is 2008-01-19, but each series begins only when valid signals/returns exist.
Current reproduction checks show first valid returns on 2008-01-22 for all rows; CPM remains close to the clean-window row at displayed precision.

| Series | Sharpe | CAGR | MaxDD | Calmar | Martin |
|---|---:|---:|---:|---:|---:|
| CPM | 1.256 | 13.13% | -13.03% | 1.008 | 4.257 |
| AAA-style available-panel | 0.930 | 9.07% | -21.76% | 0.417 | 1.603 |
| 60/40 (SPY/IEF) | 0.798 | 8.81% | -30.83% | 0.286 | 1.372 |
| Naive 12m momentum | 0.665 | 8.48% | -26.59% | 0.319 | 1.067 |
| Buy-hold vol-parity | 0.684 | 8.26% | -35.44% | 0.233 | 1.067 |

Ex-AAA-style common start (1999-03-10):

| Series | Sharpe | CAGR | MaxDD | Calmar | Martin |
|---|---:|---:|---:|---:|---:|
| CPM | 1.255 | 12.76% | -13.14% | 0.971 | 4.117 |
| 60/40 (SPY/IEF) | 0.691 | 7.31% | -31.44% | 0.232 | 1.071 |
| Naive 12m momentum | 0.816 | 10.11% | -26.59% | 0.380 | 1.428 |
| Buy-hold vol-parity | 0.813 | 9.24% | -35.44% | 0.261 | 1.372 |


### 5.7 Calendar-year returns and intra-year drawdown (clean window)

Boundary-year note: 2008 and 2026 are partial years for at least one series and are not cross-series comparable.

| Year | CPM ret | CPM intraDD | AAA-style ret | AAA-style intraDD | 60/40 ret | 60/40 intraDD |
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
| 2025 | +25.78% | -13.03% | +19.12% | -6.29% | +14.33% | -10.60% |
| 2026* | +21.44% | -5.69% | +21.70% | -6.07% | +4.71% | -6.00% |


### 5.8 Worst-interval and underwater-duration table (clean window)

| Metric | CPM | AAA-style | 60/40 |
|---|---:|---:|---:|
| Worst 1-month return | -5.85% | -7.08% | -9.77% |
| Worst 3-month return | -7.34% | -10.24% | -15.37% |
| Worst 12-month return | -5.21% | -16.86% | -16.39% |
| Longest underwater | 789 days | 903 days | 787 days |

Read: CPM longest underwater (789d) is not materially better than 60/40 (787d). CPM edge is shallower drawdown depth and better worst-interval losses, not shorter underwater duration.


### 5.9 HAA benchmark and coupled decomposition

HAA head-to-head (same engine, costs, and window handling):

| Strategy | Window | Sharpe | Calmar | MaxDD | CAGR |
|---|---|---:|---:|---:|---:|
| HAA | Clean | 0.8670 | 0.6386 | -14.68% | 9.37% |
| CPM | Clean | 1.2557 | 1.0076 | -13.03% | 13.13% |

Coupled per-factor main effects (clean, background-averaged):

| Factor | dSharpe | dCalmar | dMaxDD | Sign-flip? |
|---|---:|---:|---:|---|
| Universe (HAA-8 -> CPM-8) | +0.2215 | +0.2542 | +1.10pp | no |
| Ranker (13612U -> vol-adj Faber, coupled rank+screen) | +0.0647 | +0.0425 | -0.03pp | yes (Calmar) |
| Min-var 3-of-4 selection at n_pos=4 | +0.0902 | +0.0327 | -0.07pp | yes (Calmar) |

Canary, risky-block weighting, safe selector, and breadth routing are no-op dimensions for HAA -> CPM in this decomposition because both endpoints share TIP-only canary, equal risky weights, SHV/IEF best-safe, and strict-4 partial-safe structure.

Sequential ladder (universe -> ranker -> min-var):

| Step | Sharpe | Calmar | MaxDD |
|---|---:|---:|---:|
| HAA baseline | 0.8670 | 0.6386 | -14.68% |
| +Universe (HAA-8 -> CPM-8) | 1.0189 | 0.7693 | -14.96% |
| +Ranker (vol-adj Faber, coupled rank+screen) | 1.0874 | 0.9118 | -13.05% |
| +Min-var 3-of-4 = CPM (all-ON, both-252) | 1.2557 | 1.0076 | -13.03% |

Min-var marginal effect by (U,R) corner (clean):

| Corner | Sharpe off -> on | dSharpe | dMaxDD | dCalmar |
|---|---|---:|---:|---:|
| U0 R0 (HAA univ, 13612U) | 0.8670 -> 0.9038 | +0.0369 | +1.14pp | +0.0487 |
| U0 R1 (HAA univ, Faber) | 0.8980 -> 0.9399 | +0.0419 | -0.17pp | -0.0099 |
| U1 R0 (CPM univ, 13612U) | 1.0189 -> 1.1326 | +0.1137 | -1.27pp | -0.0038 |
| U1 R1 (CPM univ, Faber) | 1.0874 -> 1.2557 | +0.1682 | +0.01pp | +0.0959 |

Read:
- Universe is the dominant single contributor.
- Min-var at the (U1,R1) corner adds +0.1682 Sharpe and +0.0959 Calmar with essentially flat MaxDD.
- Min-var contribution is universe-conditional: within-noise as a symmetric main effect, significant at the (U1,R1) corner.


## 6. CPM decomposition (2^3, HAA baseline to CPM)

Main takeaways:
- Universe (U) is dominant and statistically clear: clean dSharpe +0.2215 with 95% CI [+0.029, +0.402].
- Ranker (R) main effect is point-positive but within noise: +0.0647 with 95% CI [-0.048, +0.176].
- Min-var (M) main effect is point-positive but within noise: +0.0902 with 95% CI [-0.008, +0.189].
- Min-var at the (U1,R1) corner is significant: +0.1682 with 95% CI [+0.043, +0.291].
- Canary, risky-block weighting, safe selector, and breadth routing are structural no-op dimensions for this decomposition because endpoints match on those dimensions.

```
HAA->CPM rung-delta CIs (clean, mooex, both-252, 10 bps/side; B=2000 block=21 seed=42)

Effect                         Point    95% CI            p(>0)   Verdict
Universe (U main effect)      +0.2215  [+0.029, +0.402]   0.985   SIGNIFICANT (clears 0)
Ranker   (R main effect)      +0.0647  [-0.048, +0.176]   0.875   WITHIN NOISE (CI spans 0)
Min-var  (M main effect)      +0.0902  [-0.008, +0.189]   0.966   WITHIN NOISE (CI spans 0)
Min-var  (M at corner U1R1)   +0.1682  [+0.043, +0.291]   0.999   SIGNIFICANT (clears 0)

Sequential ladder rungs (point): +U 0.8670->1.0189 (+0.1519);
  +R 1.0189->1.0874 (+0.0685); +M 1.0874->1.2557 (+0.1682).
```

Read:
- Universe switch is the only unambiguous main-effect edge source.
- Ranker and symmetric min-var main effects are point-positive but statistically within noise.
- Min-var earns its keep at the (U1,R1) corner.


## 7. Design notes


### 7.1 Ranker comparison

Vol-adjusted Faber ranker is above plain momentum alternatives in clean and extended robustness sweeps. Effect size is similar across windows.


### 7.2 Universe analysis

Universe effect remains positive on Sharpe and Calmar, with interaction terms (especially U x R) carrying large attribution weight.


### 7.3 Min-var selection interpretation

At full breadth (n_pos = 4), CPM evaluates all four equal-weight 3-of-4 subsets and holds the subset with the lowest estimated 252-day covariance-based portfolio variance. The CPM risky block is equal-weight over the selected names.

- Main effect for M (clean): dSharpe +0.0902, dCalmar +0.0327.
- (U1,R1) corner marginal: Sharpe 1.0874 -> 1.2557 (+0.1682), Calmar +0.0959, MaxDD +0.01pp.
- HAA-universe marginal (U0,R0): Sharpe 0.8670 -> 0.9038 (+0.0369).

Read:
- M symmetric main effect is within bootstrap noise.
- M contribution is universe-conditional and statistically clear at the (U1,R1) corner.


### 7.4 Asset concentration (average risk-contribution share, QQQ-led)

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

Cross-note: README concentration line uses average dollar-weight / exposure share, not risk-contribution share. The two metrics are different by construction.


### 7.5 Peer framing (hybrid)

CPM framing used in this memo:
- Equal-weight strict-4 risky allocation with min-var 3-of-4 full-breadth selection.
- FAA/EAA-style risk-adjusted ranking lineage.
- HAA-style canary-plus-breadth defense lineage.

Closest single overall peer is HAA because universe overlap and defense structure are both near-identical.

Cash-instrument note:
- HAA literature uses BIL; this implementation uses SHV for longer history.
- SHV vs BIL is treated as cosmetic instrument wash, not a design edge.


### 7.6 Factor hierarchy (clean cube main effects)

| Factor | Clean dSharpe | Clean dCalmar | Clean dMaxDD |
|---|---:|---:|---:|
| Universe (U) | +0.2215 | +0.2542 | +1.10pp |
| Ranker (R) | +0.0647 | +0.0425 | -0.03pp |
| Min-var (M) | +0.0902 | +0.0327 | -0.07pp |

Read:
- U is dominant across Sharpe and Calmar.
- R and M are point-positive in this sample; symmetric main-effect CIs span zero.


### 7.7 Universe rationale and robustness

CPM US-equity sleeve expresses leadership plus quality, not a textbook style barbell. QQQ plus SPHQ is the CPM expression for US-equity growth/technology leadership (QQQ) plus quality/compounder tilt (SPHQ). This pairing fits a trend-following model: growth-leadership convexity plus a more defensive quality complement, with liquid ETFs and long history.

This is a US equity leadership plus US equity quality choice, selected as the stronger CPM expression, not because it is the cleanest academic style pair.

Clean growth/value sensitivity (IWF plus IWD) is a robustness check, not a CPM upgrade.

| Metric (clean) | QQQ+SPHQ | IWF+IWD |
|---|---:|---:|
| Sharpe | 1.256 | 1.242 |
| CAGR | 13.13% | 12.64% |
| MaxDD | -13.03% | -13.03% |
| Martin | 4.26 | 3.79 |

The clean style pair shows no drawdown improvement, weaker Martin/Calmar, and no realized diversification gain. The momentum ranker does rotate growth to value when signals change, but that rotation does not improve path or drawdown outcomes.

Nominal style-label orthogonality does not reliably map to ETF-level realized orthogonality. Correlations are nearly identical and window-dependent: clean corr(IWF,IWD)=0.864 versus corr(QQQ,SPHQ)=0.881; extended corr(IWF,IWD)=0.836 versus corr(QQQ,SPHQ)=0.819. The theoretical spanning benefit is small to nonexistent in practice because large-cap US style ETFs remain equity-beta dominated.

Interpretation: universe and engine behavior is not fragile to the exact US-equity pair (IWF plus IWD is only about 0.014 Sharpe lower), which reduces curve-fitting concern. Since the clean style pair does not improve drawdown, diversification, or path quality, QQQ plus SPHQ remains the CPM choice and IWF plus IWD remains a robustness sensitivity.

Structural universe rationale centers on crisis-hedge pairing, not duration pairing. The robust engine-neutral universe improvement versus a Keller-HAA-style universe is replacing redundant IEF plus TLT duration sleeves with GLD plus TLT crisis hedges. TLT hedges financial, deflation, and growth-shock regimes (for example 2008 and 2020). GLD hedges inflation and geopolitical regimes (for example 2022, when stocks and bonds both fall). IEF plus TLT are correlated bond sleeves that can fail together in inflation shocks. IEF remains the defensive safe asset, not a risky-universe member. In single-asset upgrade tests over an HAA-style universe, IEF to GLD is the largest single driver (about +0.07 Sharpe at flat drawdown).

Net design principle: optimize universe for economically distinct, liquid, persistent return and hedge sleeves that work inside the trend engine, not for nominal factor symmetry.

| Universe set | US equity | Foreign equity | Real assets | Crisis/duration block |
|---|---|---|---|---|
| CPM-8 | QQQ+SPHQ | EFA+EEM | VNQ+DBC | GLD+TLT |
| Clean style sensitivity | IWF+IWD | EFA+EEM (or VEA+VWO, about interchangeable, corr about 0.97) | VNQ+DBC | GLD+TLT |
| HAA peer baseline | SPY+IWM | VEA+VWO | VNQ+DBC | IEF+TLT |

The clean style pair IWF plus IWD confirms CPM is not highly sensitive to the exact US-equity pair; the structural universe improvement is GLD/TLT crisis hedges replacing a redundant duration pair, not growth/value replacing size.


## 8. Statistical honesty and caveats

Lead honesty statement:
- Signal survives selection-deflation checks comfortably.
- CPM setup is still selected in-sample.
- Forward uncertainty is dominated by execution timing and regime non-stationarity.

Three-number framing:
- In-sample peak: 1.26.
- Selection-deflated in-sample: about 0.96.
- Forward expectation: about 0.72 (0.62-0.85).


### 8.1 Forward-Sharpe haircut ladder

| Step | Type | Factor (central / band) | Resulting Sharpe |
|---|---|---|---:|
| 0. In-sample argmax (clean, mooex T+1) | measured | -- | 1.2557 |
| 1. Selection de-peak | judgmental, DSR-informed | x 0.76 | about 0.96 |
| 2. Execution-realism haircut | judgmental | x 0.85 / [0.765, 0.93] | about 0.81 (0.70-0.93) |
| 3. Regime non-stationarity haircut | judgmental | x 0.88 / [0.80, 0.95] | about 0.72 (0.62-0.85) |
| Forward central | synthesis | -- | about 0.72 (0.62-0.85) |

DSR evidence is separate from the underwriting haircut: Section 8.2 reports z-band 4.16 to 6.03 with DSR saturation (>0.9999 across tested N), supporting that observed Sharpe is unlikely pure selection noise.

### 8.2 DSR appendix inputs

Measured inputs:

| Input | Value |
|---|---:|
| Observed SR_hat (per-day) | 0.07910 (ann 1.2557) |
| n (daily obs) | 4524 |
| skew | -0.4298 |
| excess kurtosis | 5.5254 |
| V_trials (grid SR variance, per-day) | 2.094e-5 (std 0.073 ann) |

Assumed input:

| Input | Value |
|---|---|
| Effective independent trials N | about 50-300 (central about 150) |

Expected-max SR0 and deflated z by N (daily frame):

| N | SR0 (ann) | DSR | z |
|---|---:|---:|---:|
| 40 | 0.159 | >0.9999 | 4.54 |
| 80 | 0.178 | >0.9999 | 4.46 |
| 200 | 0.201 | >0.9999 | 4.37 |
| 500 | 0.222 | >0.9999 | 4.28 |
| 1000 | 0.236 | >0.9999 | 4.22 |
| 2000 | 0.250 | >0.9999 | 4.16 |

Monthly-frame z range is 5.61 to 6.03, so reported z band is 4.16 to 6.03.

DSR saturates at this effect size, so values print as >0.9999 across the N range above.


### 8.3 Data caveats

- TIP-canary proxy behavior before 2003 ETF inception carries an extra-large grain of salt.
- Proxy stitches and PIT handling carry survivorship/PIT risk; companion constituent-opens cache coverage is 84% and remains gitignored/local.
- Sample-period representativeness is limited: clean 2008-2026 is dominated by two long bull runs.


## 9. Robustness checks and rejected alternatives

- Ensemble variant is not adopted: extra complexity for about 0.015 Sharpe gain is not worth it.
- Bond-buffer plus leverage is not adopted: CPM already de-risks, and leverage fails on matched-vol comparisons.
- Vol-cap overlay is not adopted: broad dilution for protection concentrated in one episode (2025-04).
- Execution cliff is generic monthly-TAA behavior; CPM remains least-affected among tested peers.
- Implied-vol add-ons have low prior due long-history coverage gaps.
- Worst clean drawdown remains 2025-04 tariff selloff, not a classic crisis cluster.


### 9.1 Leave-one-asset-out (clean window)

| Dropped | Sharpe | dSharpe | MaxDD | Calmar | dCalmar |
|---|---:|---:|---:|---:|---:|
| (none) baseline | 1.2557 | -- | -13.03% | 1.0076 | -- |
| ex-QQQ | 0.9934 | -0.2623 | -11.60% | 0.8904 | -0.1172 |
| ex-SPHQ | 1.0068 | -0.2489 | -12.41% | 0.8759 | -0.1317 |
| ex-EFA | 1.1609 | -0.0948 | -11.62% | 1.0693 | +0.0617 |
| ex-EEM | 1.1897 | -0.0660 | -11.08% | 1.1282 | +0.1206 |
| ex-VNQ | 1.0905 | -0.1652 | -13.96% | 0.8462 | -0.1614 |
| ex-GLD | 1.0404 | -0.2153 | -14.45% | 0.8222 | -0.1854 |
| ex-TLT | 1.0581 | -0.1976 | -13.98% | 0.8859 | -0.1217 |
| ex-DBC | 1.1035 | -0.1522 | -12.55% | 0.9886 | -0.0190 |

Interpretation: LOO confirms concentration in the QQQ/SPHQ/GLD/TLT core. EFA and EEM are not dominant contributors and can improve Calmar when removed, but they remain included as foreign-equity diversification sleeves rather than individually proven alpha; removing them now would be post-hoc simplification.


### 9.2 US-equity de-tilt

| Setup | Universe | Sharpe | MaxDD | Calmar |
|---|---|---:|---:|---:|
| CPM | QQQ,SPHQ,EFA,EEM,VNQ,GLD,TLT,DBC | 1.2557 | -13.03% | 1.0076 |
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
| Live drawdown breach | Live MaxDD breaches -17% or exceeds 1.3x the clean/extended envelope depth | Cut allocation and re-underwrite |
| Turnover blowout | Trailing-12m one-way turnover > 4.0 without improved risk-adjusted return | Freeze changes; investigate churn source |
| Execution-cost decay | Realized slippage plus costs exceed modeled costs by 35-50 bps per year | Pause new capital; run execution redesign review |
| Rolling-36m Sharpe (relative) | Rolling 36m Sharpe < 0 and below both HAA-style and 60/40 over the same live window | Stop deployment; re-approve before restart |
| Canary failure | In at least two independent stress episodes, canary-enabled drawdown is worse than matched no-canary drawdown | Remove or replace canary rule |


### 10.2 CPM rules as of 2026-06-01

- Risky universe: QQQ, SPHQ, EFA, EEM, VNQ, GLD, TLT, DBC.
- Canary: 13612U TIP-only, canary on if TIP is positive.
- Ranking: m_faber / rv_252d.
- Candidate screen count: top 4 (K=4).
- Positivity filter: m_faber > 0 on the K=4 candidates.
- Risky weighting: if n_pos < 4 hold all n_pos survivors at 1/4 each; if n_pos = 4 hold min-var equal-weight 3-of-4 subset.
- Full-breadth selector: at n_pos = 4, evaluate all four equal-weight 3-of-4 subsets and hold the subset with the lowest estimated 252-day covariance-based portfolio variance.
- Breadth routing: strict-4 partial-safe, with remainder in safe when n_pos < 4.
- Safe selector: SHV or IEF by higher 13612U.
- Rebalance and execution: monthly month-end signal, mooex T+1 fill.


### 10.3 Investment-decision table

| Decision state | Evidence needed | Current reading |
|---|---|---|
| Allocate | Clean Sharpe > 1, MaxDD materially shallower than 60/40, no trigger breach | Pass |
| Hold and monitor | Sharpe edge unresolved vs AAA-style/60-40 but still favorable point estimates | Pass |
| Cut or stop | Any falsification rule in 10.1 triggered | Not triggered in this memo snapshot |


## 11. Conclusion

CPM is a universe-sensitive HAA-family, tail-control-first system, not a fully portable generic engine.

Against HAA-style baseline, clean Sharpe improves 0.8670 -> 1.2557. Universe is the only statistically clear symmetric main-effect contributor; min-var is significant only at the (U1,R1) corner (+0.1682 Sharpe, near-flat MaxDD), not as a symmetric main effect.

Structural read is GLD/TLT replacing a redundant IEF/TLT risky-universe duration pairing, with US-equity leadership plus quality (QQQ/SPHQ). IWF/IWD is only about 0.014 Sharpe lower in clean sensitivity, which supports anti-fragility to exact US-equity pair choice.

Forward underwriting expectation remains about 0.72 (0.62-0.85). Governance thresholds define when to stop using CPM.


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
| risky_weight_rule | if n_pos < 4 hold all survivors at 1/4 each; if n_pos = 4 hold min-var 3-of-4 equal-weight within risky_fraction |
| min_var_rule | at n_pos = 4, evaluate all four equal-weight 3-of-4 subsets and hold the subset with the lowest estimated 252-day covariance-based portfolio variance |
| risky_fraction_rule | strict-4 partial-safe, min(n_pos,4)/4 |
| canary_rule | m_13612U(TIP) > 0 |
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


## Appendix A. 2^3 decomposition details (HAA baseline to CPM)

Baseline all-OFF and all-ON CPM endpoints:

- Baseline all-OFF (000): clean Sharpe 0.8670, MaxDD -14.68%, Calmar 0.6386; extended Sharpe 1.0307, Calmar 0.7527.
- All-ON CPM (111): clean Sharpe 1.2557, MaxDD -13.03%, Calmar 1.0076; extended Sharpe 1.2549, MaxDD -13.14%, Calmar 0.9712.

Main effects (ON minus OFF):

| Factor | Clean dSharpe | Clean dCalmar | Ext dSharpe | Ext dCalmar |
|---|---:|---:|---:|---:|
| Universe (U) | +0.2215 | +0.2542 | +0.1450 | +0.1596 |
| Ranker (R) | +0.0647 | +0.0425 | +0.0228 | -0.0442 |
| Min-var (M) | +0.0902 | +0.0327 | +0.0600 | +0.0413 |

Contribution ladder uses order U -> R -> M:

| Step | Config | Clean Sharpe | Clean Calmar | Clean MaxDD | Ext Sharpe | Ext Calmar | Ext MaxDD |
|---|---|---:|---:|---:|---:|---:|---:|
| Baseline (all-OFF) | 000 | 0.8670 | 0.6386 | -14.68% | 1.0307 | 0.7527 | -14.68% |
| +U | 100 | 1.0189 | 0.7693 | -14.96% | 1.1141 | 0.8156 | -15.35% |
| +R | 110 | 1.0874 | 0.9118 | -13.05% | 1.1331 | 0.7738 | -15.73% |
| +M (all-ON CPM) | 111 | 1.2557 | 1.0076 | -13.03% | 1.2549 | 0.9712 | -13.14% |

Finding: canary, risky-block weighting, safe selector, and breadth routing are no-op dimensions for HAA -> CPM in this decomposition (0/327 endpoint weight mismatches) because both endpoints share TIP-only canary, equal risky weights, SHV/IEF best-safe, and strict-4 partial-safe structure.
