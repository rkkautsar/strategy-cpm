# CPM n_pos=4 purposeful breadth-bonus slot vs blind renormalize / drop-to-safe

Exploratory, research-only. CPM prod unchanged. Sleeve-level (mooex T+1, 10 bps/side).
Single in-sample run, point estimates (no bootstrap). High overfit caution: the
50/25/25 tilt is a new degree of freedom, chosen a-priori with zero tuning.

## Question

At n_pos=4 the current rule lets min-var pick 3-of-4, then **renormalizes** the
survivors to 33.3% each (100% risky). This study asks: instead of that blind
renormalize, keep full-invest (100% risky) AND a consistent 25%-per-slot base,
but hand the freed 25% slot **purposefully** to ONE of the 3 chosen names
(two names stay 25%, the bonus name gets 50%). Two a-priori rules for who gets it:

- E-MOM: highest vol-adjusted momentum (faber / rv_252d) of the 3 (lean into conviction).
- E-LOWVOL: lowest trailing realized vol (rv_252d) of the 3 (lean into safety).

Compared against A (current renormalize) and B (drop freed slot to safe, 75% risky).
n_pos<4 is identical across all four modes (current breadth-scaled partial-safe, 25%/name).

## Method

- `research/cpm_npos4_bonus_slot_2026_06_02.py`. Reuses `cpm_harness` (canonical
  mooex engine, both-252 baseline) and a faithful `_core` replica of
  `cpm_live.compute_target_weights`. Only the n_pos=4 weighting branch differs per mode.
- Gates passed: prod anchor Sharpe=1.255673 reproduced; `current` replica matches
  prod weights exactly (max weight diff 0.00e+00).
- Run: `.venv/bin/python research/cpm_npos4_bonus_slot_2026_06_02.py`
- Raw: `research/cpm_npos4_bonus_slot_2026_06_02_raw.txt`

## Results -- SLEEVE clean (2008-05-30 .. 2026-05-22)

```
config              Sharpe  exSharpe  Sortino  CVaR95_d   Calmar   Martin     MaxDD     CAGR      vol  turnover
A current(33.3)      1.256     1.126    1.516    -1.57%    1.008    4.257   -13.03%   13.13%   10.28%    0.590
B drop-to-safe       1.243     1.083    1.518    -1.26%    0.802    3.776   -13.03%   10.45%    8.30%    0.525
E-MOM 50/25/25       1.093     0.968    1.293    -1.65%    0.898    3.215   -13.03%   11.70%   10.68%    0.657
E-LOWVOL 50/25/25    1.215     1.087    1.465    -1.59%    0.981    4.078   -13.03%   12.79%   10.38%    0.609
```

## Results -- SLEEVE ext (1999-03-10 .. 2026-05-22)

```
config              Sharpe  exSharpe  Sortino  CVaR95_d   Calmar   Martin     MaxDD     CAGR      vol  turnover
A current(33.3)      1.255     1.026    1.550    -1.51%    0.971    4.117   -13.14%   12.76%    9.97%    0.567
B drop-to-safe       1.266     0.990    1.585    -1.21%    0.737    3.773   -14.11%   10.40%    8.07%    0.508
E-MOM 50/25/25       1.100     0.881    1.334    -1.61%    0.829    3.130   -13.98%   11.59%   10.46%    0.624
E-LOWVOL 50/25/25    1.192     0.964    1.458    -1.52%    0.922    3.828   -13.03%   12.01%    9.93%    0.586
```

## Per-crisis (clean curve, MaxDD% / total-return%)

```
crisis                  A current(33.3)   B drop-to-safe   E-MOM 50/25/25   E-LOWVOL 50/25/25
GFC_2007_10__2009_06      -13.0%/+2.2%      -13.0%/+2.8%     -13.0%/+3.7%      -13.0%/+3.7%
COVID_2020_02__2020_06    -10.2%/+6.0%      -10.2%/+6.6%     -10.2%/+6.6%      -10.2%/+6.5%
Y2022_bear                 -5.2%/+0.4%       -4.9%/+1.0%      -6.8%/-1.4%       -6.1%/-0.0%
Y2025_tariff              -10.7%/+3.3%       -7.9%/+3.4%      -7.8%/+6.6%      -12.4%/+3.0%
```

n_pos=4 bonus-name audit (clean): 143 n_pos=4 months. E-MOM and E-LOWVOL pick the
SAME bonus name only 43.4% of the time (differ 56.6%), so the two tilts are
genuinely distinct -- yet both lose to A.

## Verdict

### (a) Does a purposeful breadth-bonus slot beat blind renormalize (A)? NO.

Both purposeful tilts underperform A on clean Sharpe, Calmar, Martin, Sortino,
and CAGR. The "blind" renormalize is actually the strongest config in the study.
The intuition is wrong because the renormalize is not blind: min-var already
selected the lowest-variance equal-weight triple, so equal-weighting (33.3% each)
IS the variance-minimizing allocation for those 3 names. Tilting 50% into any one
name departs from that optimum, adding intra-basket concentration risk with no
return compensation.

- E-MOM (conviction) is the WORST overall: clean Sharpe 1.093 (-0.16 vs A),
  Calmar 0.898, Martin 3.215, and it does NOT even buy more return (CAGR 11.70%
  < A 13.13% and < E-LOWVOL 12.79%) -- it just adds vol (10.68% highest).
- E-LOWVOL (safety) is the better of the two but still below A on every
  risk-adjusted metric: clean Sharpe 1.215 (-0.04 vs A), Calmar 0.981 (vs 1.008),
  Martin 4.078 (vs 4.257), CAGR 12.79% (vs 13.13%).

### (b) Improve on A, or within-noise? NEITHER E-* improves on A.

E-MOM is decisively below A (point gaps far exceed typical CPM noise of this
mechanism). E-LOWVOL is closer but consistently on the losing side of A across
Sharpe/Calmar/Martin/CAGR on both clean and ext -- it does not improve A on any
headline metric. MaxDD is identical at -13.03% across A/B/E-* on clean: the
binding drawdown is NOT driven by the n_pos=4 weighting choice (same trough for
all four), so this entire degree of freedom cannot help the worst drawdown.

Versus B drop-to-safe: E-LOWVOL dominates B on return-per-risk while staying
fully invested -- clean CAGR 12.79% vs 10.45%, Calmar 0.981 vs 0.802, Martin
4.078 vs 3.776, near-equal Sharpe (1.215 vs 1.243). So if one were forced to keep
100% risky with a consistent 25% base, E-LOWVOL is a better full-invest variant
than B. But A still beats E-LOWVOL, so neither is preferred over current.

### (c) Tradeoff (E-MOM more return / E-LOWVOL better tail)? Did NOT materialize.

- E-MOM did NOT deliver higher CAGR. It produced the lowest CAGR among the
  100%-risky configs (11.70% clean) with the highest vol -- pure concentration
  penalty, no conviction premium.
- E-LOWVOL did NOT deliver a better tail where it mattered most recently: it had
  the WORST Y2025 tariff drawdown (-12.4%, vs A -10.7%, E-MOM -7.8%), and its
  overall MaxDD merely tied A. The low-vol-name overweight concentrated into a
  name that drew down hard in the tariff episode.
- The crises confirm the n_pos=4 tilt is second-order: GFC and COVID drawdowns/
  returns are essentially identical across all four modes (those troughs sit in
  defensive or n_pos<4 regimes). Only Y2022 and Y2025 differ, and there the tilts
  are mixed, not systematically better.

## Bottom line

Purposefully allocating the CPM n_pos=4 freed slot (50/25/25 to the highest-momentum
or lowest-vol of the chosen 3) does not beat the current blind renormalize to
33.3% each, and does not beat drop-to-safe on risk-adjusted terms either. The
equal-weight renormalize is near-optimal precisely because min-var already
optimized the equal-weight triple; any single-name tilt re-introduces concentration
the selection stage worked to remove. Recommend NOT adopting E-MOM or E-LOWVOL.
Keep current. Treat as a closed negative result (new DoF, no tuning, single
in-sample -- still negative, which is the robust direction).

Confidence: medium-high on the ordering (gate-clean, exact-replica, consistent
across clean+ext). Caveat: point estimates only, single in-sample path; no
bootstrap CI computed (per scope), so small E-LOWVOL-vs-A gaps could be noise --
but they never favor the new variants, so the negative conclusion is safe.
