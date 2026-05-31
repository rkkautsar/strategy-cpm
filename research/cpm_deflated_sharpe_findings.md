# CPM Deflated Sharpe Ratio + Forward Expectation

Role: analyst (read-only research; no production/memo edits; no commit).
Scripts: ad-hoc (`/tmp/anchor_stats.py`, `/tmp/dsr.py`, `/tmp/final.py`) reusing the
production engine (`cpm_robust_param_sweep.run_series`, K=4/faber_voladj/504/invvol)
and the 80-cell grid SR distribution in `research/cpm_grid_interaction_findings.json`.
Anchor gate: reproduced clean Sharpe 1.1908 (matches headline 1.1910).

## Question

The memo offers ~1.02 ("Faber-family median") as the "conservative central expectation",
but that is the in-sample grid-family median, not a forward estimate. It ignores the full
design degrees-of-freedom, execution realism, and regime non-stationarity. Produce a
defensible FORWARD (OOS) Sharpe expectation.

## 1. Full selection space (degrees of freedom)

The 1.19 config is the argmax of a search far larger than the 80-cell grid.

| Axis | Documented? | Choices | DoF |
|---|---|---|---|
| Top-K | yes (grid) | {3,4,5,6} | 4 |
| Momentum fn | yes (grid) | {faber_voladj, 13612U, 12m, 6m, 3m} | 5 |
| cov/vol lookback | yes (grid) | {252, 504} | 2 (degenerate under equal-wt) |
| Weighting | yes (grid) | {invvol, equal} | 2 |
| Canary combinator | NO | OR vs AND | 2 |
| Canary asset pair | NO | HYG/TIP vs LQD/IEF/... | ~3-6 |
| 13612U horizon set | NO | {r1,r3,r6,r12} is a tuned form vs r1,r4,r8,r12 etc. | ~3-5 |
| strict-K partial-safe | NO | 4-of-8 chosen from {1..8} | ~5-8 |
| 6-factor design (C,U,R,S,W,P) | partly | inclusion lattice 2^6=64 nominal; ~6-10 explored | ~6-10 |

- Grid = 4 x 5 x 2 x 2 = **80 cells (40 distinct**; lookback is unused under equal-weight).
- Nominal product across ALL axes is **~1e3 to ~1e4** trials.

### Effective number of independent-ish trials N

The nominal product massively overstates independence. The cross-config SR dispersion
across the grid (**std 0.073 ann**) is far BELOW the standard error of a SINGLE config's
SR (**0.24 ann**, Lo/Mertens). That means the configs share most of the same return
stream -- they are highly correlated, not independent draws.

- Effective independent-ish **N ~ 50-300, central ~150**.
- DSR is insensitive to N across this band (and beyond, to N=2000), so the exact value
  does not change the verdict.

## 2. Deflated Sharpe Ratio (Bailey & Lopez de Prado, 2014)

Formula (all SR in per-period units; gamma = 0.5772 Euler-Mascheroni):

```
SR0 (expected max over N trials) = sqrt(V_trials) * [ (1-gamma)*Z^-1(1 - 1/N)
                                                    + gamma*Z^-1(1 - 1/(N*e)) ]
DSR = Phi( (SR_hat - SR0) * sqrt(n-1)
           / sqrt( 1 - skew*SR_hat + ((kurt-1)/4) * SR_hat^2 ) )
```

Inputs (daily frame, consistent with the 1.1910 anchor):

| input | value |
|---|---|
| SR_hat (per-day) | 0.07502 (ann 1.1908) |
| n (daily obs) | 4524 |
| skew | -0.3740 |
| excess kurtosis | 4.0282 |
| V_trials (grid SR var, per-day) | 2.094e-5 (std 0.073 ann) |

Results -- expected-max SR0 and DSR vs N:

| N | SR0 (ann) | DSR | z |
|---|---|---|---|
| 40 | 0.159 | 1.0000 | 4.29 |
| 80 | 0.178 | 1.0000 | 4.22 |
| 200 | 0.201 | 1.0000 | 4.13 |
| 500 | 0.222 | 1.0000 | 4.03 |
| 1000 | 0.236 | 1.0000 | 3.97 |
| 2000 | 0.250 | 1.0000 | 3.91 |

Monthly frame (n=217, skew +0.15, excess-kurt -0.05) gives DSR ~ 1.0000 with even
larger z (4.82-5.39). **Verdict robust to frame.**

### Reading the DSR

- **DSR ~ 1.0 (z > 3.9 everywhere): the 1.19 Sharpe is statistically distinguishable
  from the expected maximum of searching this correlated family.** Selection-from-noise
  ALONE does not manufacture the result -- real signal is present. This is a genuine
  honesty COUNTERWEIGHT.
- DSR answers "is skill real", NOT "what is forward SR". The expected-max benchmark
  **SR0 (ann 0.16-0.25) is the selection-inflation haircut**: ~0.16-0.25 of the 1.19 is
  attributable to picking the argmax.
- **Convergence check:** SR0 (0.16-0.25) matches the empirical peak-vs-median gap
  (1.19 - 0.94 = 0.25 vs grid median; 1.19 - 1.02 = 0.17 vs Faber-family region median).
  Two independent methods agree on the selection haircut.

**Selection-deflated in-sample Sharpe ~ 0.94-1.03 (central ~1.00).** Still ideal
execution, still the 2008-26 regime.

## 3. Forward central expectation

The forward estimate stacks three separable haircuts the DSR null does not capture
(multiplicative on annualized SR):

| Step | Factor (central / band) | Result |
|---|---|---|
| Headline argmax (T+1 MOO, in-sample) | -- | 1.19 |
| x selection de-peak | 0.82 / [0.79, 0.86] | ~0.98 (0.94-1.02) |
| x execution realism | 0.85 / [0.765, 0.93] | ~0.83 (0.72-0.95) |
| x regime non-stationarity | 0.88 / [0.80, 0.95] | ~0.72 (0.62-0.85) |

- **Execution:** disclosed cliff is real operational cost. Rebal-day {EOM, +1, +2, +3 bd}
  = Sharpe {1.21, 1.01, 0.97, 0.91}. Factor 0.765 = full EOM+3 (0.91/1.19); 0.93 =
  disciplined T+1; central 0.85 allows occasional slippage.
- **Regime:** 2008-26 was a trending / risk-on tailwind. Subperiod 2017-26 SR 1.38 vs
  2008-16 SR 1.00. Cross-asset momentum OOS-decay literature realizes ~0.5-0.7 of IS;
  0.80-0.95 here is conservative because DSR confirms a real (non-noise) core.

### FORWARD SHARPE: central ~0.72, defensible range 0.62-0.85 (forward/OOS, not in-sample).

The critique's ~0.65-0.85 is **confirmed and slightly widened on the downside to 0.62**
(if execution slips AND the regime mean-reverts hard). Note the forward haircut is driven
by de-peaking + execution + regime, NOT by failing the deflation test (the strategy
PASSES DSR decisively).

## 4. Ready-to-fold honesty summary

- Selection space is larger than the 80-cell grid: + canary OR/AND and pair, + 13612U
  horizon form, + strict-K safe threshold, + 6-factor inclusion lattice. Effective
  independent-ish trials N ~ 50-300 (central ~150); nominal product ~1e3-1e4.
- **DSR ~ 1.0 (z ~ 4-5)**: 1.19 is NOT a selection-from-noise artifact; real signal
  present. Selection-inflation haircut (expected-max SR0) ~ 0.16-0.25 ann -> selection-
  deflated in-sample Sharpe ~ 1.00.
- **Forward central Sharpe ~ 0.72, range 0.62-0.85** (OOS), after de-peaking, execution
  realism, and regime non-stationarity. Use this -- not the in-sample 1.02 -- as the
  forward expectation. Keep 1.19 labeled as the in-sample peak.

## Caveats / confidence

- DSR assumption-sensitive but ROBUST here: daily n=4524 overstates independence for a
  monthly strategy and daily kurtosis is heavy (4.03); monthly frame (n=217) is more
  honest and gives a higher z. Both -> DSR ~ 1.0.
- V_trials uses the 80-cell grid only; broader DoF raises N and SR0 modestly (still
  << 1.19), bounded by the N=2000 row.
- The three forward haircuts are applied as independent multiplicative factors; if
  execution slippage correlates with regime stress the low tail can fall below 0.62.
- The forward range is a reasoned synthesis, not a forward backtest; unvalidatable until
  OOS data accrues. Confidence: medium-high on "real signal + ~0.16-0.25 selection
  haircut" (two methods agree); medium on the exact forward central (regime factor is
  the softest input).
