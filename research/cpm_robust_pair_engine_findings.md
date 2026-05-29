# CPM Robust Pair-Selection Engine: Parameter-Free Covariance vs PROD Min-Var

Tests whether a **parameter-free regime-robust covariance** in CPM pair selection beats the static 504d sample-covariance min-variance pair, folding the SIG-B "re-pick a still-diversified pair" idea into the optimizer with **no threshold and no safe-gating**. Evaluated in the 60/40 two-sleeve CPM+BULL baseline.

Fixed: canary (HYG OR TIP), positive-Faber filter, EAA vol-adjusted rank, K=4 candidates, 50/50 pair sizing. Varied: ONLY the covariance / pair-selection estimator.

Variants:
- **E0 (PROD)**: 504d sample covariance, min-variance 50/50 pair.
- **E1**: Ledoit-Wolf shrinkage covariance (analytic intensity), min-variance pair.
- **E2**: min-correlation pair (lowest 504d pairwise corr) -- re-pick-diversified directly.
- **E3 (ref)**: constant-correlation-target LW shrinkage (analytic), min-variance pair.

**E0 reproduction:** PASS (CPM Sharpe 1.263/14.58% CAGR target; 60/40 blend Sharpe 1.347/-9.82% MaxDD).


## 1. CPM standalone (clean + stress windows)

| Variant | Window | Raw Sharpe | Excess Sharpe | CAGR | Vol | MaxDD | Calmar | Turnover |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| E0_PROD_sample | Clean | 1.263 | 1.145 | 14.58% | 11.30% | -15.41% | 0.95 | 314% |
| E0_PROD_sample | Stress | 1.218 | 1.014 | 13.99% | 11.28% | -15.91% | 0.88 | 326% |
| E1_LedoitWolf | Clean | 1.263 | 1.145 | 14.58% | 11.30% | -15.41% | 0.95 | 314% |
| E1_LedoitWolf | Stress | 1.218 | 1.014 | 13.99% | 11.28% | -15.91% | 0.88 | 326% |
| E2_min_corr | Clean | 1.200 | 1.093 | 15.16% | 12.42% | -13.21% | 1.15 | 369% |
| E2_min_corr | Stress | 1.219 | 1.031 | 15.56% | 12.50% | -13.21% | 1.18 | 403% |
| E3_const_corr | Clean | 1.224 | 1.108 | 14.16% | 11.36% | -15.41% | 0.92 | 311% |
| E3_const_corr | Stress | 1.193 | 0.989 | 13.71% | 11.31% | -15.91% | 0.86 | 324% |

## 2. 60/40 CPM+BULL blend (clean + stress windows)

| Variant | Window | Raw Sharpe | Excess Sharpe | CAGR | Vol | MaxDD | Calmar |
| --- | --- | --- | --- | --- | --- | --- | --- |
| E0_PROD_sample | Clean | 1.347 | 1.212 | 13.59% | 9.84% | -9.82% | 1.38 |
| E0_PROD_sample | Stress | 1.291 | 1.056 | 12.65% | 9.58% | -11.79% | 1.07 |
| E1_LedoitWolf | Clean | 1.347 | 1.212 | 13.59% | 9.84% | -9.82% | 1.38 |
| E1_LedoitWolf | Stress | 1.291 | 1.056 | 12.65% | 9.58% | -11.79% | 1.07 |
| E2_min_corr | Clean | 1.314 | 1.186 | 13.97% | 10.37% | -9.45% | 1.48 |
| E2_min_corr | Stress | 1.302 | 1.076 | 13.61% | 10.20% | -10.55% | 1.29 |
| E3_const_corr | Clean | 1.321 | 1.187 | 13.34% | 9.86% | -9.82% | 1.36 |
| E3_const_corr | Stress | 1.274 | 1.038 | 12.48% | 9.60% | -11.79% | 1.06 |

## 3. Crisis sub-periods (2022 calendar, 2008 calendar)

| Variant | Cell | 2022 Return | 2022 Sharpe | 2022 MaxDD | 2008 Return | 2008 Sharpe | 2008 MaxDD |
| --- | --- | --- | --- | --- | --- | --- | --- |
| E0_PROD_sample | CPM | 7.49% | 0.759 | -9.60% | 12.98% | 0.972 | -15.91% |
| E0_PROD_sample | Blend | 4.95% | 0.819 | -5.84% | 15.17% | 1.420 | -9.99% |
| E1_LedoitWolf | CPM | 7.49% | 0.759 | -9.60% | 12.98% | 0.972 | -15.91% |
| E1_LedoitWolf | Blend | 4.95% | 0.819 | -5.84% | 15.17% | 1.420 | -9.99% |
| E2_min_corr | CPM | 4.85% | 0.497 | -9.60% | 8.49% | 0.606 | -12.31% |
| E2_min_corr | Blend | 3.41% | 0.554 | -5.84% | 12.54% | 1.155 | -8.40% |
| E3_const_corr | CPM | 7.49% | 0.759 | -9.60% | 12.98% | 0.972 | -15.91% |
| E3_const_corr | Blend | 4.95% | 0.819 | -5.84% | 15.17% | 1.420 | -9.99% |

## 4. Re-pick diagnostic (does divergence from E0 help?)

Clean window, CPM risk-on months only. "E0 poor" = E0 pair had both legs down over the forward 21d holding period OR forward-21d pair correlation exceeded its trailing-504d correlation by >0.30 (diversification break). Forward delta = candidate pair 50/50 forward-21d return minus E0 pair forward-21d return.

| Variant | Diverge from E0 | Mean fwd delta (all diverge) | E0 poor months | of those diverged | of diverged: cand better | Mean fwd delta (poor & diverge) |
| --- | --- | --- | --- | --- | --- | --- |
| E1_LedoitWolf | 0/187 (0.0%) | nanbps | 48 | 0 | 0 | nanbps |
| E2_min_corr | 110/187 (58.8%) | 8.5bps | 48 | 27 | 15 | 81.5bps |
| E3_const_corr | 4/187 (2.1%) | -126.8bps | 48 | 2 | 1 | -240.6bps |

## 5. Walk-forward / sub-period stability (is any edge broad?)

Rolling 3-year (756d) blend Sharpe vs E0; fraction of windows where candidate beats E0. Ex-crisis = clean-window blend Sharpe excluding calendar 2008 and 2020.

| Variant | Roll-3y win-frac vs E0 | Roll mean diff | Roll [min, max] diff | Full-window Sharpe delta | Ex-2008/2020 Sharpe delta |
| --- | --- | --- | --- | --- | --- |
| E1_LedoitWolf | 0% | +0.000 | [+0.000, +0.000] | +0.000 | +0.000 |
| E2_min_corr | 54% | -0.053 | [-0.612, +0.361] | -0.032 | -0.070 |
| E3_const_corr | 32% | -0.029 | [-0.192, +0.041] | -0.026 | +0.007 |

## 6. Why E1 (Ledoit-Wolf) is a provable no-op for this selection

E1 diverged from E0 in **0 / 187** months -- not a bug. Ledoit-Wolf shrinks the
sample covariance S toward a scaled-identity target F = mu*I (mu = trace(S)/n):

    cov' = (1-d) * S + d * mu * I

For an equal-weight (50/50) pair (a, b) the portfolio variance is
0.25*(S_aa + S_bb + 2*S_ab). Under the shrunk matrix:

    var'(a,b) = (1-d) * var_S(a,b) + 0.5 * d * mu

The term `0.5*d*mu` is the SAME constant added to every candidate pair, and `(1-d)`
scales all pairs uniformly. Both are monotone transforms, so **argmin over pairs is
invariant**: LW-to-identity can never change the chosen min-variance pair vs sample
covariance. Verified numerically: 0 pick flips across 3000 random 4-asset draws.

Consequence: any analytic shrinkage with a *diagonal* target (LW-identity, OAS) is a
no-op for equal-weight pair min-variance selection. Only a shrinkage target that
perturbs the **off-diagonal structure non-uniformly** (e.g. constant-correlation,
E3) can move the pick -- and E3 moved it in only 2.1% of months, unhelpfully.


## 7. Verdict: REJECT

No parameter-free robust covariance beats PROD min-var on risk-adjusted terms with a
broad edge.

- **E1 Ledoit-Wolf (identity target): REJECT -- provable no-op.** Pick-identical to E0
  in 100% of months (analytic argmin-invariance). Zero effect on any metric. The
  "shrinkage fixes pair selection" hypothesis is mathematically false for equal-weight
  pairs with a diagonal shrinkage target.
- **E2 min-correlation: REJECT as Sharpe play; it is a DD/Calmar trade, not an edge.**
  Clean blend Sharpe -0.032 (worse), ex-2008/2020 Sharpe -0.070 (edge is NOT broad and
  is, if anything, negative ex-crisis), rolling-3y win-frac only 54% with a wide
  [-0.612, +0.361] band. It DOES improve drawdown/Calmar (clean MaxDD -9.45% vs -9.82%,
  Calmar 1.48 vs 1.38; stress MaxDD -10.55% vs -11.79%, Calmar 1.29 vs 1.07) and stress
  Sharpe (+0.011) -- exactly the prior "near-miss, DD-tilted, ~-0.03 clean Sharpe,
  better stress/Calmar" characterization. Reconciled: E2 is a risk-shape preference, not
  a parameter-free Sharpe improvement. The re-pick diagnostic confirms the nuance: in
  E0's 48 poor months E2 diverged 27 times and was better in only 15 (~56%, near
  coin-flip), mean forward delta +81.5bps -- a weak, noisy signal that does not survive
  into broad risk-adjusted outperformance.
- **E3 constant-correlation shrinkage: REJECT.** Clean blend Sharpe -0.026, stress
  -0.017, ex-crisis +0.007 (flat). Diverges from E0 only 2.1% of months; those few
  re-picks were net harmful (mean poor-div forward delta -240.6bps). Essentially tracks
  E0 with slight noise drag.

**Bottom line:** Folding the "re-pick a still-diversified pair" idea into the optimizer
parameter-free does NOT beat the static 504d sample-cov min-var pair. The two genuinely
parameter-free shrinkage routes (E1, E3) are no-ops or near-no-ops by construction; the
one estimator that actually re-picks diversified (E2 min-corr) buys lower drawdown at a
small, crisis-concentrated Sharpe cost -- not a clean win. **Keep production E0.** If the
team later prioritizes drawdown/Calmar over raw Sharpe, E2 min-corr is the only candidate
worth a separate DD-objective discussion (hand to oracle), but it should not be adopted
as a Sharpe improvement.

Caveats: single execution model (T+1 MOO, 10bps/side); clean window 2008-05-30..2026-05-22,
stress 1999-03-10..2026-05-22; pre-ETF history uses audited mutual-fund proxy stitches.
Forward-outcome horizon fixed at 21 trading days. BULL sleeve held constant across all
variants (only the CPM covariance estimator varied), so blend turnover deltas flow solely
through the CPM sleeve (reported in Table 1).
