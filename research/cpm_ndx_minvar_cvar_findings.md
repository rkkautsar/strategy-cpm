# NDX sleeve: min-var selection and CVaR/CDaR downside objectives vs momentum top-5 EW

Analyst role, research only. Production files (`ndx_sleeve_live.py`, prod blend,
memo) were NOT edited. No commit. Reproducible via
`research/cpm_ndx_minvar_cvar.py` (writes `cpm_ndx_minvar_cvar_findings.json`).

## Question

NDX was proposed as a better testbed than CPM for correlation-aware selection and
downside objectives because it has (a) a larger pool (~100-name PIT Nasdaq-100)
and (b) highly non-elliptical single-stock returns (skew/kurtosis) where variance
is a poor risk proxy. The current NDX sleeve is momentum top-5 equal-weight with
no correlation or min-var step. Three sub-questions:

- (a) Does min-var SELECTION beat momentum-only top-5 EW in the larger universe?
- (b) Given the fat tails, does a DOWNSIDE objective (CVaR, or especially CDaR for
  the -31% MaxDD problem) beat variance/EW net of cost and OOS, i.e. is NDX the
  regime where downside objectives finally pay (unlike CPM where they washed)?
- (c) Does just holding MORE names (top-15 EW vs top-5 EW) help?
- (d) What is the turnover cost of the optimizers on single stocks?

## Method

Engine reuse with zero production changes: the unmodified
`ndx_sleeve_live.run_ndx_backtest` was driven by monkeypatching
`compute_ndx_weights` per config. Gating (TIP canary + SPY trend + SPY RV20<RV252
crossover), best-of-safe rotation, T+1 MOO close-to-close accounting, 10 bps/side
cost, delisting haircut (-0.10), and PIT Nasdaq-100 membership are byte-identical
across every config. Only the selection/sizing of the held names varies.

Hierarchical workflow (required; raw ~100-name optimization is singular at
T/N ~ 2.5): each signal date the universe is momentum-pruned to the top-N
positive-13612U names (N=15 canonical; N=10/20 reported as sensitivity), THEN the
selection/weighting rule chooses and sizes the final K=5 (or weights all 15 for
the breadth reference). 252d window for covariance/CVaR/CDaR; Ledoit-Wolf
shrinkage on covariance for the variance-based optimizers (single-stock noise).
CVaR LP (Rockafellar-Uryasev, beta=0.95) and CDaR LP (Chekhlov-Uryasev) reused
from `research/cpm_cvar_cdar_objective.py`; min-var subset and bootstrap reused
from the corr-weighting and multimetric-bootstrap helpers.

Windows: clean = 2008-05-30..2026-05-22 (DECISION), stress/ext = 1999-03-10.. .
Paired block bootstrap B=2000, block=21, seed=42 vs PROD on dSharpe + dSortino +
dCVaR (path-independent), with dMaxDD as soft context. 3-seg walk-forward.

PROD reproduces clean Sharpe 1.281, MaxDD -31.4% on the refreshed NDX prices
(2026-05-28); ~0.03 Sharpe drift from the 1.253 memo figure is the price refresh.
All comparisons use the same data, so deltas are unaffected.

## Configs

| Config | Selection | Weighting |
|---|---|---|
| PROD | momentum top-5 | equal-weight (baseline) |
| MINVAR_SEL | momentum top-15 -> min-var subset of 5 (LW cov) | equal-weight |
| MIN_CVAR | momentum top-15 -> min-CVaR LP -> top-5 by weight | LP weights, renorm |
| MIN_CDAR | momentum top-15 -> min-CDaR LP -> top-5 by weight | LP weights, renorm |
| TOP15_EW | momentum top-15 | equal-weight (breadth ref) |
| INVVOL5 | momentum top-5 | inverse-vol (weighting ref) |
| MAXDIV5 | momentum top-5 | max-diversification (weighting ref) |

## Results

### Clean window (2008-05-30+, DECISION)

| Config | Sharpe | Sortino | CVaR | Calmar | Martin | MaxDD | CAGR | vol | TO/yr |
|---|---|---|---|---|---|---|---|---|---|
| PROD | 1.281 | 1.962 | 8.40 | 1.00 | 4.23 | -31.4% | 31.4% | 20.0% | 5.16 |
| MINVAR_SEL | 0.882 | 1.307 | 5.73 | - | - | -23.3% | - | - | 5.75 |
| MIN_CVAR | 0.851 | 1.285 | 5.69 | - | - | -25.6% | - | - | 6.23 |
| MIN_CDAR | 0.739 | 1.102 | 4.88 | - | - | -23.8% | - | - | 6.19 |
| TOP15_EW | 1.187 | 1.741 | 7.40 | - | - | -22.8% | - | - | 4.74 |
| INVVOL5 | 1.244 | 1.897 | 8.16 | - | - | -32.2% | - | - | 5.40 |
| MAXDIV5 | 1.247 | 1.905 | 8.19 | - | - | -32.3% | - | - | 5.52 |

### Stress window (1999-03-10+, CONFIRM)

| Config | Sharpe | Sortino | CVaR | MaxDD | CAGR | Calmar | Martin | vol |
|---|---|---|---|---|---|---|---|---|
| PROD | 1.131 | 1.721 | 7.39 | -31.4% | 22.9% | 0.73 | 3.52 | 20.0% |
| MINVAR_SEL | 0.871 | 1.291 | 5.73 | -23.3% | 11.7% | 0.50 | 1.90 | 13.7% |
| MIN_CVAR | 0.827 | 1.243 | 5.57 | -25.6% | 11.3% | 0.44 | 1.46 | 14.1% |
| MIN_CDAR | 0.735 | 1.092 | 4.85 | -23.8% | 10.1% | 0.42 | 1.12 | 14.6% |
| TOP15_EW | 1.094 | 1.602 | 6.93 | -22.8% | 16.8% | 0.74 | 3.47 | 15.3% |
| INVVOL5 | 1.105 | 1.673 | 7.22 | -32.2% | 21.8% | 0.68 | 3.34 | 19.6% |
| MAXDIV5 | 1.101 | 1.669 | 7.20 | -32.3% | 21.6% | 0.67 | 3.26 | 19.5% |

### Paired block bootstrap vs PROD (clean; mean [95% CI], p>0)

| Config | dSharpe | dSortino | dCVaR | dMaxDD (soft) |
|---|---|---|---|---|
| MINVAR_SEL | -0.396 [-0.72,-0.10] p=0.004 | -0.651 [-1.19,-0.15] p=0.004 | -2.66 [-4.94,-0.50] p=0.008 | +0.064 p=0.868 |
| MIN_CVAR | -0.425 [-0.81,-0.08] p=0.007 | -0.671 [-1.31,-0.07] p=0.009 | -2.68 [-5.44,-0.10] p=0.022 | +0.047 p=0.769 |
| MIN_CDAR | -0.536 [-0.89,-0.18] p=0.000 | -0.852 [-1.46,-0.26] p=0.000 | -3.49 [-6.09,-0.87] p=0.001 | +0.020 p=0.639 |
| TOP15_EW | -0.093 [-0.27,+0.10] p=0.152 | -0.221 [-0.53,+0.10] p=0.082 | -1.00 [-2.31,+0.38] p=0.069 | +0.073 p=0.957 |
| INVVOL5 | -0.036 [-0.09,+0.02] p=0.104 | -0.065 [-0.17,+0.03] p=0.097 | -0.25 [-0.67,+0.17] p=0.123 | +0.003 p=0.649 |
| MAXDIV5 | -0.032 [-0.10,+0.03] p=0.180 | -0.053 [-0.18,+0.07] p=0.197 | -0.20 [-0.74,+0.31] p=0.224 | -0.001 p=0.467 |

Convention: p>0 is the bootstrap probability the config beats PROD. p<=0.05 means
the config is SIGNIFICANTLY WORSE; p>=0.95 means SIGNIFICANTLY BETTER.

### Per-crisis MaxDD / Sharpe (stress curve)

| Config | dotcom 00-02 | GFC 07-09 | COVID 20 | 2022 | 2025 |
|---|---|---|---|---|---|
| PROD | -12%/0.95 | -9%/0.96 | -5%/2.71 | -0%/2.98 | -5%/0.89 |
| MINVAR_SEL | -12%/0.95 | -9%/1.05 | -5%/2.71 | -0%/2.98 | -3%/1.74 |
| MIN_CVAR | -12%/0.95 | -9%/1.09 | -5%/2.71 | -0%/2.98 | -3%/0.68 |
| MIN_CDAR | -12%/0.95 | -9%/1.08 | -5%/2.71 | -0%/2.98 | -3%/0.82 |
| TOP15_EW | -12%/0.95 | -9%/0.95 | -5%/2.71 | -0%/2.98 | -3%/1.36 |
| INVVOL5 | -12%/0.95 | -9%/0.97 | -5%/2.71 | -0%/2.98 | -4%/1.14 |
| MAXDIV5 | -12%/0.95 | -9%/1.07 | -5%/2.71 | -0%/2.98 | -4%/1.43 |

Crisis windows are nearly identical across configs because the gate (TIP + SPY
trend + vol crossover) de-risks the sleeve into best-of-safe through dotcom, GFC,
COVID, and 2022. Selection/weighting only acts in risk-on months, so it cannot
touch those crisis numbers. The -31% PROD MaxDD is NOT a crisis-window event; it
is single-stock concentration damage during risk-ON periods (see walk-forward
2020-2026 segment, PROD MaxDD -31%). That is the drawdown the held-names rule can
actually address, and it is exactly where breadth helps.

### N sensitivity (clean Sharpe / MaxDD / TO; N=10/15/20)

| Config | N=10 | N=15 (canon) | N=20 |
|---|---|---|---|
| MINVAR_SEL | 1.014 / -30.0% / 5.5 | 0.882 / -23.3% / 5.8 | 0.837 / -28.3% / 5.9 |
| MIN_CVAR | 0.826 / -31.2% / 6.2 | 0.851 / -25.6% / 6.2 | 0.917 / -30.3% / 6.3 |
| MIN_CDAR | 0.825 / -34.0% / 6.1 | 0.739 / -23.8% / 6.2 | 0.683 / -35.7% / 6.4 |

The optimizers swing 0.13-0.23 Sharpe and 6-12pp MaxDD across the prune width N
with no monotone pattern. High parameter sensitivity confirms estimation error
dominates; the prune-then-optimize N is itself an overfit degree of freedom.

### Walk-forward (3 sequential clean segments, Sharpe / MaxDD)

| Config | 2008-2014 | 2014-2020 | 2020-2026 |
|---|---|---|---|
| PROD | 1.18 / -17% | 1.25 / -17% | 1.47 / -31% |
| MINVAR_SEL | 1.14 / -14% | 0.60 / -13% | 0.92 / -23% |
| MIN_CVAR | 1.12 / -15% | 0.65 / -17% | 0.83 / -26% |
| MIN_CDAR | 0.80 / -23% | 0.88 / -13% | 0.64 / -24% |

PROD beats every variant on Sharpe in every segment. The optimizers are unstable
across segments (MINVAR_SEL 1.14 -> 0.60 -> 0.92). No segment supports adopting any
optimizer over PROD.

## Answers

(a) Min-var SELECTION does NOT help. Clean Sharpe falls 1.281 -> 0.882; dSharpe
-0.40, dSortino -0.65, dCVaR -2.66, all significantly NEGATIVE (p<=0.008). It cuts
MaxDD (-31% -> -23%), but that reduction is NOT significant on the bootstrap
(dMaxDD p=0.87) and is bought at roughly half the CAGR. Correlation-aware
selection on single momentum stocks discards the high-momentum names and keeps the
low-covariance ones, which throws away the momentum premium. Larger N did not
rescue it; it added an overfit knob.

(b) Downside objectives do NOT pay on NDX either - they hurt MORE than they washed
on CPM. MIN_CVAR clean Sharpe 0.851, MIN_CDAR 0.739; both significantly worse than
PROD on dSharpe/dSortino/dCVaR. CDaR, the supposed best fit for the -31% MaxDD
problem, is the WORST performer of the entire study. The fat tails do not save the
optimizers; 252 daily single-stock observations give a noisy tail estimate, and
optimizing against it sacrifices the momentum carry that drives the sleeve. NDX is
NOT the regime where downside objectives finally pay.

(c) Holding MORE names (TOP15_EW) is the only useful lever, and it works as a
DRAWDOWN tool, not a return tool. Clean Sharpe 1.187 vs 1.281 is NOT a significant
loss (dSharpe p=0.15; dSortino p=0.08; dCVaR p=0.07 all include zero), while MaxDD
improves -31% -> -23% and is the one SIGNIFICANT risk reduction in the study
(dMaxDD p=0.96). Calmar ties PROD on the stress window (0.74 vs 0.73) and turnover
is actually LOWER (4.7 vs 5.2/yr) because the EW top-15 set churns less than an
optimized 5. Concentration in 5 single stocks is the drawdown driver; breadth
fixes it more cheaply than any optimizer. Weighting-only refs (INVVOL5, MAXDIV5)
are statistical ties with PROD on every metric - the weighting lever is inert; the
name count is what matters.

(d) Turnover: the optimizers run ~6.2/yr vs PROD 5.16 (~20% higher) from
single-stock weight churn, exactly as expected, with no compensating benefit.

## Verdict

Neither min-var selection nor a CVaR/CDaR downside objective beats the momentum
top-5 EW baseline on the NDX sleeve. Despite the larger universe and fat tails -
the conditions that motivated the test - estimation error and the destruction of
the momentum premium dominate; the downside objectives do worse than they did on
CPM (where they merely washed), with CDaR the single worst config. Do not adopt
any optimizer for NDX selection or sizing.

The one finding worth carrying forward: the -31% MaxDD is single-stock
concentration damage in risk-on months (the gate already handles macro crises),
and simply holding more names (top-15 EW) removes ~8pp of MaxDD with no
statistically significant Sharpe loss and lower turnover. If drawdown reduction on
the NDX sleeve is the goal, breadth - not a fancy risk objective - is the lever.
This is a candidate for follow-up (e.g. top-8/10 EW to find the breadth/return
knee), but it is a single in-sample result and would itself need bootstrap +
walk-forward + cross-sleeve blend confirmation before any adoption claim.

## Caveats and confidence

- High overfit degrees of freedom: single-stock select+weight, prune-then-optimize,
  N/K choices. Treated clean as the decision window, stress + per-crisis +
  bootstrap + walk-forward as confirmation. The NEGATIVE conclusions on the
  optimizers are robust (significant and consistent across every lens). The
  POSITIVE breadth finding is weaker: a single in-sample MaxDD reduction with a
  non-significant Sharpe delta - suggestive, not adoptable as-is.
- T+1 MOO uses the NDX engine's close-to-close accounting (exact-open not supported
  for the per-stock universe); same convention for all configs so deltas are clean.
- PIT membership + delisting haircut applied identically; pre-2006 the PIT pool is
  unavailable and the gate is usually defensive, so the dotcom column reflects the
  safe sleeve, not stock selection.
- Bootstrap classifies on path-independent dSharpe/dSortino/dCVaR; dMaxDD CIs are
  soft (path-dependent) and used only as context.
- Single data vendor (yfinance), prices refreshed 2026-05-28; PROD Sharpe drifts
  ~0.03 vs the frozen memo. Same-data deltas are unaffected.
