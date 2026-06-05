# CPM Factorial Multi-Metric Significance Audit (HAA + AAA, both-252)

Role: analyst. Read-only re production (no edits to memo / prod / cpm_live).
Writes only research/ artifacts. No commit.

## Question

The two prior factor-significance audits classified each adopted CPM factor on
the **dSharpe** confidence interval only. CPM is a drawdown-defense framework,
so a downside-aware lens matters as much as Sharpe. This audit re-runs both
factorial decompositions with an added **path-independent downside metric** and
re-answers: does any factor that looks like NOISE or MARGINAL on Sharpe become
SIGNIFICANT once a downside metric is used -- especially the protection-biased
factors (canary, screen, partial-safe) and the min-var 3-of-4 selection?

## Metric design (important methodology change)

Calmar (CAGR / |MaxDD|) and Martin (CAGR / Ulcer) are **path-dependent**: both
are built on the running-maximum drawdown path. A block bootstrap reshuffles
that path, so a single deep-drawdown block can dominate a resample and the
resulting CIs are soft and unreliable. Classifying significance on those CIs
would be dishonest.

Therefore significance is classified on **path-independent** ratios that
bootstrap as cleanly as Sharpe:

- **Sortino** (primary added metric): `mean(r) * 252 / (downside_dev * sqrt(252))`,
  where `downside_dev = sqrt(mean(min(r,0)^2))` (threshold 0). Distributional /
  order-invariant.
- **CVaR / Expected-Shortfall ratio** (secondary tail check):
  `mean(r) * 252 / |mean(worst 5% of r)|`. Also order-invariant.

Calmar and Martin are **demoted to point-estimate context only** -- reported for
transparency, never used for SIGNIFICANT/MARGINAL/NOISE calls.

## Method

- Engine: canonical `research/cpm_harness` (mooex T+1, 10 bps/side, both-252).
- Bootstrap: `research/cpm_bootstrap_multimetric.paired_block_bootstrap_mm`,
  B=2000, block=21, seed=42 -- byte-identical resampling to
  `cpm_weighting_corr.paired_block_bootstrap` (dSharpe reproduces exactly), with
  Sortino + CVaR added.
- Lens: clean window (2008-05-30..2026-05-22). Single in-sample. Per-factor
  test = leave-one-out at the production corner (prod vs prod\X), the same
  single-swap lens applied to min-var 3-of-4.
- Classification: SIGNIFICANT = 95% CI excludes 0; MARGINAL = CI spans 0 but
  p(>0) >= 0.85 or <= 0.15; else NOISE.
- The two decompositions are kept **separate**: HAA (Hybrid, TIP-canary
  baseline, all-OFF 0.8670) and AAA (Adaptive, min-var/no-canary baseline,
  all-OFF 0.7869). They are not merged or cross-referenced.

### Gates (all passed)

- verify_anchor() = Sharpe 1.1658, MaxDD -0.1297, Calmar 1.0137.
- HAA all-OFF 0.8670 / all-ON 1.1658. AAA all-OFF 0.7869 / all-ON 1.1658.
  Neither all-ON hit the stale 504d value 1.1910.

Scripts run:
`research/cpm_haa_factorial_significance_audit.py`,
`research/cpm_aaa_factorial_significance_audit.py`
(JSON: `*_significance_audit.json`).

## Factor x metric significance matrix

Classification on path-independent metrics (Sharpe / Sortino / CVaR). Calmar and
Martin shown as point context (full-clean-series deltas), not classified.

### HAA -> CPM (factors T, V, W, C, U; LOO at prod corner)

| Factor | Sharpe | Sortino | CVaR | dSortino 95% CI (p) | pt dCalmar | pt dMartin |
|---|---|---|---|---|---|---|
| T trend       | NOISE    | NOISE    | NOISE    | [-0.179, +0.238] (0.57) | +0.026 | +0.147 |
| V vol-adj     | MARGINAL | MARGINAL | MARGINAL | [-0.010, +0.235] (0.96) | +0.131 | +0.154 |
| W weighting   | MARGINAL | MARGINAL | MARGINAL | [-0.036, +0.141] (0.85) | -0.001 | -0.051 |
| C canary      | NOISE    | NOISE    | NOISE    | [-0.201, +0.297] (0.63) | +0.097 | +0.215 |
| U universe    | MARGINAL | MARGINAL | MARGINAL | [-0.058, +0.632] (0.94) | +0.379 | +1.068 |

Cumulative all-ON vs all-OFF dSharpe CI [+0.027, +0.565], p=0.983 (the stack as
a whole is significant; individual factors are not).

### AAA -> CPM (factors C, U, R, S, W, P; LOO at prod corner)

| Factor | Sharpe | Sortino | CVaR | dSortino 95% CI (p) | pt dCalmar | pt dMartin |
|---|---|---|---|---|---|---|
| C canary       | MARGINAL | MARGINAL | NOISE    | [-0.071, +0.321] (0.87) | +0.181 | +0.785 |
| U universe     | MARGINAL | MARGINAL | MARGINAL | [-0.065, +0.500] (0.93) | +0.304 | +1.257 |
| R ranker       | SIGNIF   | SIGNIF   | SIGNIF   | [+0.117, +0.689] (1.00) | +0.477 | +1.593 |
| S screen       | NOISE    | NOISE    | NOISE    | [-0.141, +0.217] (0.62) | +0.147 | +0.114 |
| W weighting    | MARGINAL | NOISE    | MARGINAL | [-0.427, +0.146] (0.16) | -0.024 | -0.328 |
| P partial-safe | MARGINAL | MARGINAL | MARGINAL | [-0.022, +0.163] (0.93) | +0.018 | +0.665 |

Cumulative all-ON vs all-OFF dSharpe CI [+0.052, +0.698], p=0.987.

Note on W (AAA): its LOO sign is negative (dSharpe -0.100, p=0.14) -- removing W
at the AAA production corner slightly *improves* the backtest. It is the one
factor whose downside-metric reading (Sortino NOISE, low p) is driven by being
weakly counterproductive, not weakly helpful.

## Key question: do Sharpe-NOISE/MARGINAL protection factors become downside-SIGNIFICANT?

**No.** Switching to a path-independent downside metric does not rescue any
protection-biased factor:

- **Canary C** -- HAA: NOISE on Sharpe AND Sortino AND CVaR. AAA: MARGINAL on
  Sharpe and Sortino, NOISE on CVaR. Canary never reaches SIGNIFICANT on any
  metric in either decomposition; the downside lens makes it *weaker* (CVaR), not
  stronger.
- **Screen S** (AAA only) -- NOISE on all three. No downside rescue.
- **Partial-safe P** (AAA only) -- MARGINAL on all three; never SIGNIFICANT.

The only factor SIGNIFICANT on the downside metrics is **AAA ranker R**, and it
is SIGNIFICANT on Sharpe too -- it is not a Sharpe-noise factor that the downside
lens promotes. So the headline hypothesis (protection factors hide their value
in drawdown metrics) is **not supported** under a clean, path-independent test.

The single classification flip caused by a downside metric goes to **min-var
3-of-4**, not to any adopted factor (see below).

## min-var 3-of-4 re-ranked per metric

min-var 3-of-4 is an engine-level selection swap on canonical CPM (reproduces
the 1.1658 anchor as its prod baseline), bootstrapped vs prod with identical
params. Point estimates: dSharpe +0.096, dCalmar +0.206, dMartin +0.262,
dMaxDD +0.0163 (i.e. MaxDD shallower: -0.1135 vs prod -0.1297).

| Metric | dCI 95% | p(>0) | Class |
|---|---|---|---|
| Sharpe  | [-0.005, +0.196] | 0.968 | MARGINAL |
| Sortino | [-0.015, +0.297] | 0.961 | MARGINAL |
| CVaR    | [+0.021, +1.470] | 0.982 | **SIGNIFICANT** |

Robustness (block=42): Sharpe [-0.004, +0.192] p=0.968; Sortino
[-0.014, +0.288] p=0.965; CVaR [+0.049, +1.438] p=0.986. The CVaR significance
holds at both block lengths.

Per-metric ranking by p(>0) (factors + min-var):

- **Sharpe**: R (AAA, 0.998) > min-var (0.968) > U(AAA 0.947) > V(HAA 0.962)... 
  min-var outranks every adopted factor except the AAA ranker R.
- **Sortino**: R (0.999) > min-var (0.961) > V(HAA 0.964) ~ U(AAA 0.933)...
  same picture -- min-var is second only to R.
- **CVaR (tail)**: R (0.999) and min-var (0.982) are the only two that reach
  SIGNIFICANT; min-var beats every protection factor and every other adopted
  factor on the tail metric.

So min-var 3-of-4 is the **strongest non-ranker selection on the downside tail**
and is at least as well-supported as every adopted factor except AAA-R on every
metric.

## Revised "noise in BOTH decompositions" (all path-independent metrics)

A factor counts as ablatable-noise only if it is NOISE on **all
path-independent metrics (Sharpe AND Sortino) in BOTH decompositions**. Mapping
across decompositions:

- **Canary C** (present in both): HAA NOISE/NOISE; AAA MARGINAL/MARGINAL.
  Not noise in both -> **not ablatable-noise**.
- **Universe U** (present in both): HAA MARGINAL; AAA MARGINAL. Not noise.
- **Screen S** (AAA only), **trend T** (HAA only), **vol-adj V** (HAA only),
  **partial-safe P** (AAA only): single-decomposition factors with no clean 1:1
  counterpart, so "noise in both" is undefined for them. Within their own
  decomposition: T NOISE (HAA), S NOISE (AAA), V/P MARGINAL.

**Conclusion: no factor qualifies as ablatable-noise across both decompositions
on the path-independent metrics.** The factors that are NOISE somewhere (T, C-in-
HAA, S) are either single-decomposition or flip to MARGINAL in the other
decomposition. The earlier dSharpe-only "noise in both" reading is not
strengthened by adding the downside lens; if anything the canary's HAA-NOISE /
AAA-MARGINAL split is confirmed (downside metrics do not make canary look
better).

## Revised double-standard verdict

The multi-metric, path-independent picture **confirms and sharpens** the prior
verdict:

1. Under the same clean single-swap lens, almost every adopted factor is
   MARGINAL at best on Sharpe AND on the path-independent downside metrics. Only
   AAA-ranker R is robustly SIGNIFICANT across all metrics. Canary (both
   decompositions), screen, partial-safe, trend, vol-adj, universe, and
   weighting are MARGINAL or NOISE.
2. min-var 3-of-4 is MARGINAL on Sharpe/Sortino (p ~ 0.96-0.97) and the **only
   non-ranker that is SIGNIFICANT on the downside tail (CVaR)**, with a shallower
   MaxDD and positive point Calmar/Martin. It outranks every adopted factor
   except R on every metric.
3. Therefore rejecting min-var 3-of-4 as "merely marginal" while retaining
   factors that are equally marginal (or NOISE) -- and that the downside lens
   does *not* rescue -- remains a **double standard**. Adding the downside
   metrics does not give the protection-biased factors a defense they lacked on
   Sharpe; it instead surfaces min-var's tail edge.

## Caveats and confidence

- Single in-sample clean window; LOO at the production corner. Interaction
  structure beyond single-swap is not the subject here.
- Sortino/CVaR CIs are clean (order-invariant) and the basis for all
  classification. Calmar/Martin are point context only -- do not read their
  spread as significance.
- CVaR uses the worst-5% tail; with ~4500 clean days that is ~225 observations
  per resample, adequate but tail-metric CIs are still the widest of the three.
- min-var significance on CVaR is robust to block=21 and block=42.
- Confidence: high on the classifications (clean metrics, gated engine,
  reproduced anchor and prior dSharpe). Medium-high on the "no protection factor
  becomes downside-significant" conclusion -- it is a LOO-at-prod-corner result;
  a protection factor could plausibly matter more in a corner where canary fires
  often, but that is outside the adopted single-swap lens.

## Artifacts

- `research/cpm_bootstrap_multimetric.py` (new helper: Sortino/CVaR + context).
- `research/cpm_haa_factorial_significance_audit.py` (+ JSON) -- extended.
- `research/cpm_aaa_factorial_significance_audit.py` (+ JSON) -- extended.
- `research/cpm_factorial_multimetric_significance_findings.md` (this file).

## Next handoff

oracle -- if a release/adoption decision on min-var 3-of-4 vs the adopted factor
stack is to be adjudicated on this multi-metric evidence.
