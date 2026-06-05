# COHERENT-IV vs COHERENT-EW: apples-to-apples sizing significance

Throwaway research. Read-only re production; no prod/memo/cpm_live edits; no commit.

Anchor (clean, via harness): Sharpe 1.2622, MaxDD -0.1135, Calmar 1.2196.


## Question

Is COHERENT-IV (ivobj selection + IV sizing) SIGNIFICANTLY different from COHERENT-EW (ewobj selection + EW sizing) on PATH-INDEPENDENT metrics (Sharpe + Sortino + CVaR)? Each sizing paired with its OWN matched variance objective = the fair apples-to-apples sizing comparison. Prior coherence study bootstrapped Sharpe ONLY for this pair (dSharpe +0.021 p0.71); Sortino/CVaR never tested.


## Method

- Engine: research/cpm_harness.py (mooex T+1, both-252, 10 bps/side). Anchor verified first.

- Cells (research/cpm_minvar_coherence.make_weight_fn): COHERENT-IV = minvar_ivobj + IV; COHERENT-EW = minvar_ewobj + EW. m=3 of top-4, full-risk-on-drop, else byte-identical to prod.

- Contrast d = COHERENT-IV - COHERENT-EW. Paired block bootstrap (research/cpm_bootstrap_multimetric) B=2000 seed=42, block=21 (primary) + block=42 (robustness). Path-independent metrics: Sharpe, Sortino, CVaR-ratio.

- Path-dependent metrics (Calmar/Martin/MaxDD): POINT-EST context only (CIs soft under block resampling).


## Point estimates (both windows)

| cell | window | Sharpe | Calmar | Martin | MaxDD |
|---|---|---|---|---|---|
| COHERENT-IV | clean | 1.2501 | 1.1846 | 3.8999 | -0.1154 |
| COHERENT-EW | clean | 1.2711 | 1.0883 | 4.1685 | -0.1303 |
| COHERENT-IV | ext | 1.2657 | 0.9960 | 3.8663 | -0.1363 |
| COHERENT-EW | ext | 1.2969 | 0.9458 | 4.0211 | -0.1522 |

## Significance: path-independent contrast d = COHERENT-IV - COHERENT-EW (clean)

Positive d = COHERENT-IV ahead. p>0 = bootstrap P(IV>EW).


### block=21 (primary)

| metric | mean | 95% CI | p(IV>EW) | CI excludes 0? |
|---|---|---|---|---|
| dSharpe | -0.0214 | [-0.0980, 0.0579] | 0.293 | no |
| dSortino | -0.0315 | [-0.1510, 0.0958] | 0.293 | no |
| dCVaR | -0.1520 | [-0.6998, 0.4492] | 0.294 | no |

### block=42 (robustness)

| metric | mean | 95% CI | p(IV>EW) | CI excludes 0? |
|---|---|---|---|---|
| dSharpe | -0.0206 | [-0.0949, 0.0545] | 0.296 | no |
| dSortino | -0.0303 | [-0.1467, 0.0865] | 0.303 | no |
| dCVaR | -0.1463 | [-0.6871, 0.4133] | 0.298 | no |

## Path-dependent context blocks (soft CIs -- NOT used for significance)


### block=21

| metric | mean | 95% CI | p(IV>EW) |
|---|---|---|---|
| dCalmar | -0.0265 | [-0.2064, 0.1521] | 0.346 |
| dMartin | -0.1591 | [-0.7526, 0.4218] | 0.275 |
| dMaxDD | 0.0011 | [-0.0216, 0.0259] | 0.550 |

### block=42

| metric | mean | 95% CI | p(IV>EW) |
|---|---|---|---|
| dCalmar | -0.0256 | [-0.2173, 0.2025] | 0.366 |
| dMartin | -0.1656 | [-0.8578, 0.5063] | 0.296 |
| dMaxDD | 0.0019 | [-0.0205, 0.0326] | 0.522 |

## Verdict

INDISTINGUISHABLE. Every path-independent contrast (dSharpe, dSortino, dCVaR) spans 0 at BOTH block sizes (21 and 42). COHERENT-IV is NOT significantly different from COHERENT-EW on any path-independent metric. Even apples-to-apples -- each sizing paired with its own matched variance objective -- the sizing/objective choice is statistical noise.


All CIs (signed, both block sizes) tabulated above. Single in-sample test; path-independent metrics drive significance; path-dependent point-est is context only. No recommendation.
