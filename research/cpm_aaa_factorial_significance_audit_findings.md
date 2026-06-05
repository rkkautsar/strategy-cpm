# AAA -> CPM factor significance audit (both-252)

Role: analyst (read-only re production; writes only `research/` artifacts; no
production/memo/`cpm_live` edits; no commit).

Script: `research/cpm_aaa_factorial_significance_audit.py` ->
`research/cpm_aaa_factorial_significance_audit.json`.

Scope: the AAA -> CPM decomposition ONLY (Adaptive Asset Allocation baseline:
min-var weighting, no canary). This is NOT the HAA decomposition; the two have
different baselines and are not mixed.

## Question

Are the ADOPTED AAA -> CPM production factors (U, R, W, S, P, C) individually
significant or marginal, judged under the SAME statistical lens that was applied
to the min-var 3-of-4 selection (clean window, B=2000 paired block bootstrap,
dSharpe CI + p(>0))? If the adopted factors are themselves mostly marginal, then
"marginal" cannot fairly disqualify min-var 3-of-4.

Context: min-var 3-of-4 was called "marginal" with clean dSharpe +0.106 vs prod,
95% CI [+0.002, +0.213], p 0.977 -- the only cell in a large search whose CI
excluded 0.

## Method

- Engine: `research/cpm_harness.py` (mooex T+1 MOO exact, 10 bps/side, both-252).
- Weight function: `cpm_wf` from `research/cpm_factorial_faithful_aaa.py`. Its
  W=ON path calls `inv_vol_weights(..., CORR_LOOKBACK_DAYS)` and
  `cpm_live.CORR_LOOKBACK_DAYS == 252`, so W=ON runs at 252 (both-252), NOT the
  stale 504d. Gated explicitly.
- Bootstrap: `paired_block_bootstrap` from `research/cpm_weighting_corr.py`
  (B=2000, block=21, seed=42) -- byte-identical to the min-var studies.
- Clean window (2008-05-30 .. 2026-05-22) is the decision lens. Single in-sample.
- Per-factor primary test = LEAVE-ONE-OUT at the production corner: var = full
  production (all-ON), base = production with exactly ONE factor turned OFF.
  dSharpe = Sharpe(prod) - Sharpe(prod\X) = the marginal value that adopted
  factor X actually contributes AT the production configuration. This is a single
  change measured against prod -- the same shape of comparison used for min-var
  3-of-4 (a single change measured against prod).

## Anchor gates (both PASS)

| gate | metric | got | target | pass |
|---|---|---:|---:|---|
| harness anchor (`verify_anchor`) | Sharpe / MaxDD / Calmar | 1.1658 / -12.97% / 1.0137 | 1.1658 / -12.97% / 1.0137 | YES |
| all-OFF == faithful AAA | clean Sharpe | 0.7869 | 0.7869 | YES |
| all-ON == production both-252 | clean Sharpe | 1.1658 | 1.1658 | YES |

all-ON is 1.1658, NOT 1.1910 -> confirmed both-252, not 504d. `CORR_LOOKBACK_DAYS
= 252`.

## Per-factor significance (leave-one-out at production corner)

Each row: how much the adopted factor adds to production. dSharpe is the
bootstrap mean; point estimate in parentheses. Walk-forward = number of 3
sequential clean segments with positive var-minus-base dSharpe.

| factor | meaning (OFF -> ON adopted) | dSharpe (point) | 95% CI | p(>0) | walk-fwd | class | CI excludes 0 |
|---|---|---:|---|---:|:---:|---|:---:|
| **R** ranker | raw 6m mom -> vol-adj Faber | +0.252 (+0.254) | [+0.070, +0.440] | 0.998 | 3/3 | **SIGNIFICANT** | YES |
| **U** universe | AAA 8 -> CPM 8 | +0.157 (+0.158) | [-0.030, +0.339] | 0.947 | 3/3 | MARGINAL | no |
| **P** partial-safe | fully invested -> strict-4 | +0.043 (+0.043) | [-0.013, +0.101] | 0.929 | 3/3 | MARGINAL | no |
| **C** canary | none -> HYG/TIP 13612U | +0.074 (+0.071) | [-0.044, +0.213] | 0.877 | 2/3 | MARGINAL | no |
| **S** screen | none -> positive-trend | +0.017 (+0.019) | [-0.090, +0.133] | 0.598 | 2/3 | NOISE | no |
| **W** weighting | min-var -> inverse-vol | **-0.102 (-0.100)** | [-0.291, +0.088] | 0.140 | 2/3 | MARGINAL | no |

Classification counts: **SIGNIFICANT 1 (R), MARGINAL 4 (U, P, C, W), NOISE 1 (S).**

Two findings stand out:

1. Only **R (the ranker)** is individually significant -- its 95% CI is the only
   one (among adopted factors) that excludes 0.
2. **W (the adopted weighting change) has a NEGATIVE point estimate**: replacing
   min-var with inverse-vol at the production corner COSTS about -0.10 Sharpe
   (p(inv-vol better) = 0.140, i.e. p(min-var better) ~ 0.86). The adopted
   weighting axis is the one production factor pointing the wrong way -- and it
   points back toward min-var.

## BH-FDR across the 6 factor p-values

One-sided p = 1 - p(>0). Benjamini-Hochberg at alpha = 0.05:

| rank | factor | one-sided p | survives FDR |
|---|---|---:|:---:|
| 1 | R | 0.0025 | YES |
| 2 | U | 0.0530 | no |
| 3 | P | 0.0705 | no |
| 4 | C | 0.1230 | no |
| 5 | S | 0.4025 | no |
| 6 | W | 0.8600 | no |

**1 of 6 adopted factors survives FDR (R only).** After multiplicity control,
five of the six adopted production factors are not distinguishable from noise.

## Min-var 3-of-4 ranked against the 6 adopted factors

Ranked by p(>0), with min-var 3-of-4 inserted on its published numbers:

| rank | item | dSharpe | 95% CI | p(>0) | CI excludes 0 |
|---|---|---:|---|---:|:---:|
| 1 | factor R | +0.252 | [+0.070, +0.440] | 0.998 | YES |
| 2 | **min-var 3-of-4** | +0.106 | [+0.002, +0.213] | 0.977 | **YES** |
| 3 | factor U | +0.157 | [-0.030, +0.339] | 0.947 | no |
| 4 | factor P | +0.043 | [-0.013, +0.101] | 0.929 | no |
| 5 | factor C | +0.074 | [-0.044, +0.213] | 0.877 | no |
| 6 | factor S | +0.017 | [-0.090, +0.133] | 0.598 | no |
| 7 | factor W | -0.102 | [-0.291, +0.088] | 0.140 | no |

min-var 3-of-4 ranks **#2 overall**. Critically, it is one of only **TWO** items
in this whole comparison whose 95% CI strictly excludes 0 -- the other is R. By
the exact bar used to call min-var "marginal" (CI spanning 0), min-var does NOT
span 0; four adopted factors (U, P, C, S) and the negative W DO. min-var
outranks every adopted factor except the ranker.

## Cumulative vs step

- Whole stack, all-ON vs all-OFF: dSharpe +0.379 (point), bootstrap mean +0.381,
  95% CI [+0.052, +0.698], p 0.987, walk-forward 3/3 positive (+0.26, +0.43,
  +0.49 across the three clean segments). **The full AAA -> CPM edge is
  significant** (CI excludes 0, survives walk-forward).
- Sequential ladder (add one factor at a time, order R, C, U, S, P, W with P
  after S): EVERY marginal step CI spans 0. Step classifications: +R MARGINAL,
  +C MARGINAL, +U MARGINAL, +S NOISE, +P MARGINAL, +W MARGINAL. **Not one
  individual ladder step is significant**, yet the cumulative is.

So the production stack is a **chain of individually-marginal steps that sums to
a significant whole**. The collective edge is real; the per-step attributions
are mostly not individually distinguishable from noise.

## Verdict

The production AAA -> CPM stack is built on a chain of marginal steps, not on
individually-significant ones. Under the identical lens used for min-var 3-of-4:

- Only 1 of 6 adopted factors (R, the ranker) is individually significant and
  the only FDR survivor.
- 4 of 6 are marginal; 1 is noise; the adopted weighting change (W: min-var ->
  inverse-vol) is the single factor with a negative point estimate, i.e. it
  argues FOR min-var, not against it.
- min-var 3-of-4 (dSharpe +0.106, CI [+0.002, +0.213], p 0.977) ranks #2 of 7,
  beats 4 of the 6 adopted factors on p, and is one of only two items whose 95%
  CI strictly excludes 0.

Therefore "marginal" is a **double standard** as a disqualifier for min-var
3-of-4. By that bar, five of the six adopted production factors should also be
disqualified, and min-var 3-of-4 is in fact STRONGER than all of them except the
ranker -- it clears the CI-excludes-0 bar that only R meets among adopted
factors. If marginal-but-positive single changes are acceptable for the adopted
stack (they are: the stack ships them), the same standard accepts min-var 3-of-4.
Honest caveat: min-var 3-of-4's CI lower bound (+0.002) is barely above 0, so
its significance is borderline -- but it is still no weaker, and on the strict
CI-exclusion test strictly stronger, than the adopted factors it is being held
below.

## Caveats / confidence

- Single in-sample, clean window only (the decision lens), both-252 throughout;
  no 504d numbers anywhere. Gates confirm all-OFF = 0.7869 and all-ON = 1.1658.
- LOO measures marginal value AT the production corner (the decision-relevant
  question: does each adopted factor pull its weight in the shipped config).
  Background-averaged main effects (in the JSON) tell a consistent story but
  dilute factors that interact (notably P, inert across the S-OFF half).
- min-var 3-of-4 numbers are taken from the prior min-var studies (same
  bootstrap config, B=2000 block=21 seed=42), not recomputed here; they were
  produced under the identical harness, so the comparison is apples-to-apples.
- Bootstrap means differ trivially from point estimates (resampling); both
  reported. Walk-forward is a 3-segment stability check, not a tuning CV.
- Confidence: high on the ordering and on the SIG/MARGINAL/NOISE split (gates
  pass, methodology mirrors the min-var studies exactly). The double-standard
  conclusion follows directly from min-var ranking above 4 of 6 adopted factors
  on the same bar.
