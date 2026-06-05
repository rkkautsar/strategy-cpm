# HAA->CPM Coupled Factorial: Statistical-Significance Audit (both-252)

Role: analyst (read-only re production; writes only `research/`; no commit).
Scope: HAA->CPM decomposition ONLY (Hybrid Asset Allocation baseline, TIP canary).
AAA is a separate decomposition audited by a different analyst and is untouched here.

## Question

Are the ADOPTED HAA->CPM production factors (T, V, W, C, U) individually
statistically significant, or are they marginal -- under the SAME lens applied
to the min-var 3-of-4 selection (clean window, B=2000 paired block bootstrap,
dSharpe CI + p(>0))? If the adopted factors are themselves marginal, then
"marginal" cannot be a fair, consistently-applied disqualifier for min-var 3-of-4.

Context: min-var 3-of-4 selection was labeled "marginal" (clean dSharpe +0.106
vs prod, 95% CI [+0.002, +0.213], p=0.977 -- the only cell in a large search
whose CI excludes 0).

## Method

- Engine: `research/cpm_harness.py` (mooex T+1 MOO exact, 10 bps/side, both-252).
- Factorial machinery reused as-is from `research/cpm_haa_coupled_factorial.py`
  (`param_wf`): the 2^5 coupled HAA<->CPM grid. all-OFF (00000) == canonical HAA;
  all-ON (11111) == production CPM both-252. This script is ALREADY both-252
  (W uses `CORR_LOOKBACK_DAYS=252`); no window change was made.
- Factors (config tuple order T,V,W,C,U):
  - T trend metric (13612U -> Faber; couples rank numerator AND screen)
  - V vol-adjust (raw -> rank numerator / rv_252d; rank denominator only)
  - W weighting (equal -> inverse-vol, cov tail 252)
  - C canary (TIP-only -> HYG-or-TIP)
  - U universe (HAA set -> CPM set)
- Bootstrap: `research/cpm_weighting_corr.paired_block_bootstrap`
  (B=2000, block=21, seed=42) -- byte-identical to the min-var studies.
- Lens: clean window 2008-05-30..2026-05-22 (decision lens). Single in-sample.
- Per-factor measure: leave-one-out (LOO) at the production corner --
  var = production (all-ON), base = production with ONE factor turned OFF.
  dSharpe = Sharpe(prod) - Sharpe(prod\X). This is a single change vs prod,
  exactly the structure of the min-var 3-of-4 comparison, so it is directly
  comparable. Background-averaged main effects (grid + return-space bootstrap)
  are reported as a secondary cross-check.
- Classification rule (same as the AAA sibling audit):
  SIGNIFICANT = 95% CI excludes 0; MARGINAL = CI spans 0 but p>=0.85 (or <=0.15);
  NOISE = CI spans 0 and 0.15 < p < 0.85.

Run: `.venv/bin/python research/cpm_haa_factorial_significance_audit.py`
Artifacts: `research/cpm_haa_factorial_significance_audit.py`,
`research/cpm_haa_factorial_significance_audit.json`.

## Gates (all pass)

| Gate | Target | Actual | Pass |
|---|---|---|---|
| G0 `cpm_harness.verify_anchor()` Sharpe | 1.1658 | 1.1658 (MaxDD -12.97%, Calmar 1.0137) | yes |
| G1 all-OFF (00000) clean Sharpe == HAA | 0.8670 | 0.8670 | yes |
| G2 all-ON (11111) clean Sharpe == prod both-252 | 1.1658 | 1.1658 | yes |
| both-252 guard | 252 | `CORR_LOOKBACK_DAYS=252`, not 504d (1.1910) | yes |

## Per-factor significance (LOO at production corner, clean, B=2000)

| Factor | what it flips | dSharpe | 95% CI | p(>0) | dCalmar | WF + segs | Class |
|---|---|---:|---|---:|---:|:--:|:--|
| T | trend metric 13612U->Faber | +0.012 | [-0.121, +0.152] | 0.549 | +0.001 | 1/3 | NOISE |
| V | vol-adjust (/rv_252d) | +0.070 | [-0.007, +0.153] | 0.962 | +0.060 | 2/3 | MARGINAL |
| W | weighting equal->inv-vol | +0.034 | [-0.020, +0.093] | 0.870 | +0.080 | 3/3 | MARGINAL |
| C | canary TIP->HYG-or-TIP | +0.037 | [-0.126, +0.205] | 0.657 | +0.071 | 2/3 | NOISE |
| U | universe HAA->CPM set | +0.208 | [-0.027, +0.430] | 0.959 | +0.301 | 3/3 | MARGINAL |

Background-averaged main effects (grid point estimate; return-space bootstrap CI)
agree on direction and class for every factor (T NOISE, V MARGINAL, W MARGINAL,
C NOISE, U MARGINAL); none has a CI that excludes 0.

### Counts

- SIGNIFICANT (95% CI excludes 0): **0 of 5**
- MARGINAL (CI spans 0, p>=0.85): **3 of 5** (V, W, U)
- NOISE (CI spans 0, 0.15<p<0.85): **2 of 5** (T, C)

## BH-FDR across the 5 factor p-values

One-sided p = 1 - p(>0); Benjamini-Hochberg at alpha=0.05.

Ordered p: V 0.038, U 0.042, W 0.131, C 0.343, T 0.451.
**Survivors: 0 of 5.** Not one adopted HAA->CPM factor clears multiplicity
correction. (V and U are borderline raw -- ~0.04 -- but fail the BH step
threshold; the rest are far off.)

## Sequential ladder (memo 5.9 order T -> V -> W -> C -> U), marginal-step CIs

| Step | cum Sharpe | step dSharpe | 95% CI | p(>0) | Class |
|---|---:|---:|---|---:|:--|
| +T | 0.8708 | +0.004 | [-0.124, +0.134] | 0.521 | NOISE |
| +V | 0.8980 | +0.027 | [-0.057, +0.117] | 0.742 | NOISE |
| +W | 0.9653 | +0.067 | [-0.018, +0.162] | 0.927 | MARGINAL |
| +C | 0.9575 | -0.008 | [-0.177, +0.157] | 0.470 | NOISE |
| +U | 1.1658 | +0.208 | [-0.027, +0.430] | 0.959 | MARGINAL |

Every single ladder step's CI spans 0. The biggest step (universe, +0.208) is
still only MARGINAL by p. No step is individually significant.

## Cumulative vs step

Whole-stack all-ON vs all-OFF (HAA 0.8670 -> CPM 1.1658):

- dSharpe point +0.299; 95% CI **[+0.027, +0.565]**; p(>0) **0.983**.
- 3-segment walk-forward dSharpe: +0.264, +0.473, +0.168 -- positive in all 3.
- Classification: **SIGNIFICANT** (CI excludes 0).

So the cumulative HAA->CPM edge IS statistically significant and sign-stable
across walk-forward thirds, even though not one of its five constituent steps is
individually significant and zero survive FDR. The stack's significance is an
aggregate of five small, mostly-non-significant moves, not a chain of
individually-proven steps.

## Min-var 3-of-4 ranking vs the adopted factors

Ranked by p(>0), single-change-vs-prod lens for all rows:

| Rank | Item | dSharpe | 95% CI | p(>0) | Class |
|---:|---|---:|---|---:|:--|
| 1 | **min-var 3-of-4** | +0.106 | **[+0.002, +0.213]** | **0.977** | SIGNIFICANT |
| 2 | factor V (vol-adjust) | +0.071 | [-0.007, +0.153] | 0.962 | MARGINAL |
| 3 | factor U (universe) | +0.208 | [-0.027, +0.430] | 0.959 | MARGINAL |
| 4 | factor W (weighting) | +0.035 | [-0.020, +0.093] | 0.870 | MARGINAL |
| 5 | factor C (canary) | +0.037 | [-0.126, +0.205] | 0.657 | NOISE |
| 6 | factor T (trend metric) | +0.011 | [-0.121, +0.152] | 0.549 | NOISE |

Min-var 3-of-4 ranks **#1 of all** -- ahead of every adopted HAA->CPM factor.
It is the only row whose 95% CI excludes 0 (ci_lo +0.002). Under the same
classification rule, min-var 3-of-4 is SIGNIFICANT while all five adopted
factors are MARGINAL or NOISE.

## Verdict

The HAA->CPM both-252 stack is built on a **chain of individually marginal-to-noise
steps, not individually-significant ones.**

- 0 of 5 adopted factors are individually significant (95% CI excludes 0).
- 0 of 5 survive BH-FDR.
- The strongest single adopted factor (universe, +0.208) is still only MARGINAL
  (p=0.959), and min-var 3-of-4 (p=0.977) outranks it on the same lens.
- The cumulative stack edge IS significant (CI [+0.027, +0.565], p=0.983,
  WF-positive 3/3) -- the edge lives in the aggregate, not in any provable step.

Therefore "marginal" is **not a consistently-applied disqualifier** -- applying
it as a rejection bar to min-var 3-of-4 while retaining T, V, W, C, U is a
**double standard.** Min-var 3-of-4 has a *strictly stronger* single-change
significance profile (higher p, CI excludes 0) than any factor already adopted
into the HAA->CPM stack. If min-var 3-of-4 is disqualified for being marginal,
the same bar disqualifies the entire adopted HAA->CPM mechanism; if the adopted
stack is justified by its aggregate edge, the identical logic admits min-var
3-of-4, which clears a higher individual bar than its parts.

This does not, by itself, argue FOR adopting min-var 3-of-4 (single in-sample;
both are vulnerable to the same overfitting critique). It argues only that the
"marginal" label cannot be used asymmetrically: by this lens min-var 3-of-4 is
better-supported individually than the factors it is being compared against.

## Caveats and confidence

- Single in-sample backtest, clean window decision lens. CIs are bootstrap
  sampling CIs, not out-of-sample guarantees; the same overfitting caution
  applies symmetrically to min-var 3-of-4 and to the adopted factors.
- LOO-at-prod-corner is the directly min-var-comparable per-factor measure
  (single swap vs prod). Background-averaged grid main effects are reported as a
  secondary view and agree on every classification.
- Calmar/MaxDD bootstrap under block resampling partially disrupts the drawdown
  path; dCalmar CIs are softer than dSharpe and are reported as point estimates
  plus directional context. dSharpe is the primary statistic (matches min-var).
- Factor interactions exist (the coupled grid is not perfectly additive); ladder
  step values are path-dependent on the memo 5.9 order. The headline counts
  (0 significant, 0 FDR survivors, min-var ranks #1) are order-independent.
- Confidence: HIGH on the qualitative verdict (double standard); the gap between
  min-var (CI excludes 0) and every adopted factor (CI spans 0) is robust to the
  measure chosen. Confidence MODERATE on exact p/CI third-decimal values
  (bootstrap noise, single seed=42 as specified).

## Handoff

- oracle: adjudication of whether "marginal" should remain an adoption/rejection
  bar given this symmetric evidence, and whether min-var 3-of-4 warrants OOS
  re-test before any decision.
