# FULL 2x2 (selection objective x sizing) significance on the min-var 3-of-4 trio

Throwaway research. Read-only re production; no prod/memo/cpm_live edits; no commit.

Anchor (clean, via harness): Sharpe 1.2622, MaxDD -0.1135, Calmar 1.2196.


## Question

Across the FULL 2x2 (selection objective {ewobj, ivobj} x sizing {EW, IV}) on the min-var 3-of-4 trio -- INCLUDING the incoherent (mismatched) cells -- are ALL pairwise differences within noise on the PATH-INDEPENDENT metrics (Sharpe/Sortino/CVaR), i.e. is sizing AND objective AND coherence uniformly statistical noise? A prior test (cpm_coherent_iv_vs_ew_significance) found coherent-IV vs coherent-EW indistinguishable; this adds the incoherent cells (esp. ivobj+EW) and the cross-contrasts.


## Method

- Engine: research/cpm_harness.py (mooex T+1, both-252, 10 bps/side). Anchor verified first.

- Cells via research/cpm_minvar_coherence.make_weight_fn (m=3 of top-4, full-risk-on-drop, else byte-identical to prod). objective in {minvar_ewobj, minvar_ivobj} x sizing in {EW, IV}.

- Pairwise contrasts: paired block bootstrap (research/cpm_bootstrap_multimetric) B=2000 seed=42, block=21 (primary) + block=42 (robustness). Path-independent metrics: dSharpe, dSortino, dCVaR. Contrast d = A - B (A = first cell named in the contrast).

- Path-dependent metrics (Calmar/Martin/MaxDD): POINT-EST context only (CIs soft under block resampling).


## Point estimates: all 4 cells, both windows (context)

| cell | window | Sharpe | Calmar | Martin | MaxDD |
|---|---|---|---|---|---|
| COHERENT-EW (ewobj + EW) [matched] | clean | 1.2711 | 1.0883 | 4.1685 | -0.1303 |
| INCOHERENT-IV (ewobj + IV) [= prod min-var; mismatch] | clean | 1.2622 | 1.2196 | 3.9522 | -0.1135 |
| COHERENT-IV (ivobj + IV) [matched] | clean | 1.2501 | 1.1846 | 3.8999 | -0.1154 |
| INCOHERENT-EW (ivobj + EW) [mismatch] | clean | 1.2509 | 1.0688 | 4.0880 | -0.1303 |
| COHERENT-EW (ewobj + EW) [matched] | ext | 1.2969 | 0.9458 | 4.0211 | -0.1522 |
| INCOHERENT-IV (ewobj + IV) [= prod min-var; mismatch] | ext | 1.2624 | 0.9135 | 3.8170 | -0.1492 |
| COHERENT-IV (ivobj + IV) [matched] | ext | 1.2657 | 0.9960 | 3.8663 | -0.1363 |
| INCOHERENT-EW (ivobj + EW) [mismatch] | ext | 1.2906 | 1.0477 | 4.1048 | -0.1362 |

## Significance: pairwise contrasts on path-independent metrics (clean)

Contrast d = A - B (A = first cell in the contrast name). Positive d = A ahead.


### C1 coherent-IV vs coherent-EW (prior check)


**block=21 (primary)**

| metric | mean | 95% CI | p(cohIV>cohEW) | CI excludes 0? |
|---|---|---|---|---|
| dSharpe | -0.0214 | [-0.0980, 0.0579] | 0.293 | no |
| dSortino | -0.0315 | [-0.1510, 0.0958] | 0.293 | no |
| dCVaR | -0.1520 | [-0.6998, 0.4492] | 0.294 | no |

**block=42 (robustness)**

| metric | mean | 95% CI | p(cohIV>cohEW) | CI excludes 0? |
|---|---|---|---|---|
| dSharpe | -0.0206 | [-0.0949, 0.0545] | 0.296 | no |
| dSortino | -0.0303 | [-0.1467, 0.0865] | 0.303 | no |
| dCVaR | -0.1463 | [-0.6871, 0.4133] | 0.298 | no |

### C2 INCOHERENT-EW (ivobj+EW) vs COHERENT-EW (ewobj+EW): objective effect under EW sizing


**block=21 (primary)**

| metric | mean | 95% CI | p(incEW>cohEW) | CI excludes 0? |
|---|---|---|---|---|
| dSharpe | -0.0207 | [-0.0766, 0.0390] | 0.250 | no |
| dSortino | -0.0286 | [-0.1148, 0.0664] | 0.271 | no |
| dCVaR | -0.1514 | [-0.5475, 0.3028] | 0.237 | no |

**block=42 (robustness)**

| metric | mean | 95% CI | p(incEW>cohEW) | CI excludes 0? |
|---|---|---|---|---|
| dSharpe | -0.0200 | [-0.0776, 0.0329] | 0.241 | no |
| dSortino | -0.0275 | [-0.1191, 0.0564] | 0.280 | no |
| dCVaR | -0.1461 | [-0.5671, 0.2495] | 0.237 | no |

### C3 INCOHERENT-IV (ewobj+IV=prod) vs COHERENT-IV (ivobj+IV): objective effect under IV sizing


**block=21 (primary)**

| metric | mean | 95% CI | p(incIV>cohIV) | CI excludes 0? |
|---|---|---|---|---|
| dSharpe | 0.0126 | [-0.0397, 0.0601] | 0.690 | no |
| dSortino | 0.0171 | [-0.0654, 0.0903] | 0.671 | no |
| dCVaR | 0.0980 | [-0.2982, 0.4356] | 0.707 | no |

**block=42 (robustness)**

| metric | mean | 95% CI | p(incIV>cohIV) | CI excludes 0? |
|---|---|---|---|---|
| dSharpe | 0.0118 | [-0.0335, 0.0583] | 0.695 | no |
| dSortino | 0.0161 | [-0.0587, 0.0908] | 0.672 | no |
| dCVaR | 0.0928 | [-0.2580, 0.4332] | 0.711 | no |

### C4 EW vs IV WITHIN ewobj (pure sizing at ewobj): ewobj+EW - ewobj+IV


**block=21 (primary)**

| metric | mean | 95% CI | p(EW>IV) | CI excludes 0? |
|---|---|---|---|---|
| dSharpe | 0.0088 | [-0.0469, 0.0651] | 0.628 | no |
| dSortino | 0.0143 | [-0.0714, 0.1009] | 0.635 | no |
| dCVaR | 0.0541 | [-0.3601, 0.4603] | 0.608 | no |

**block=42 (robustness)**

| metric | mean | 95% CI | p(EW>IV) | CI excludes 0? |
|---|---|---|---|---|
| dSharpe | 0.0087 | [-0.0474, 0.0637] | 0.635 | no |
| dSortino | 0.0142 | [-0.0742, 0.1003] | 0.636 | no |
| dCVaR | 0.0535 | [-0.3713, 0.4563] | 0.617 | no |

### C5 EW vs IV WITHIN ivobj (pure sizing at ivobj): ivobj+EW - ivobj+IV


**block=21 (primary)**

| metric | mean | 95% CI | p(EW>IV) | CI excludes 0? |
|---|---|---|---|---|
| dSharpe | 0.0007 | [-0.0534, 0.0539] | 0.510 | no |
| dSortino | 0.0029 | [-0.0819, 0.0866] | 0.525 | no |
| dCVaR | 0.0006 | [-0.4106, 0.3983] | 0.507 | no |

**block=42 (robustness)**

| metric | mean | 95% CI | p(EW>IV) | CI excludes 0? |
|---|---|---|---|---|
| dSharpe | 0.0006 | [-0.0549, 0.0553] | 0.520 | no |
| dSortino | 0.0028 | [-0.0856, 0.0893] | 0.536 | no |
| dCVaR | 0.0002 | [-0.4333, 0.4111] | 0.517 | no |

## Path-dependent context blocks (soft CIs -- NOT used for significance)


### C1 coherent-IV vs coherent-EW (prior check)


**block=21**

| metric | mean | 95% CI | p>0 |
|---|---|---|---|
| dCalmar | -0.0265 | [-0.2064, 0.1521] | 0.346 |
| dMartin | -0.1591 | [-0.7526, 0.4218] | 0.275 |
| dMaxDD | 0.0011 | [-0.0216, 0.0259] | 0.550 |

**block=42**

| metric | mean | 95% CI | p>0 |
|---|---|---|---|
| dCalmar | -0.0256 | [-0.2173, 0.2025] | 0.366 |
| dMartin | -0.1656 | [-0.8578, 0.5063] | 0.296 |
| dMaxDD | 0.0019 | [-0.0205, 0.0326] | 0.522 |

### C2 INCOHERENT-EW (ivobj+EW) vs COHERENT-EW (ewobj+EW): objective effect under EW sizing


**block=21**

| metric | mean | 95% CI | p>0 |
|---|---|---|---|
| dCalmar | -0.0120 | [-0.1309, 0.1217] | 0.354 |
| dMartin | -0.0690 | [-0.4691, 0.3506] | 0.344 |
| dMaxDD | 0.0006 | [-0.0166, 0.0192] | 0.492 |

**block=42**

| metric | mean | 95% CI | p>0 |
|---|---|---|---|
| dCalmar | -0.0154 | [-0.1000, 0.0834] | 0.295 |
| dMartin | -0.0623 | [-0.4299, 0.3002] | 0.329 |
| dMaxDD | 0.0003 | [-0.0090, 0.0109] | 0.427 |

### C3 INCOHERENT-IV (ewobj+IV=prod) vs COHERENT-IV (ivobj+IV): objective effect under IV sizing


**block=21**

| metric | mean | 95% CI | p>0 |
|---|---|---|---|
| dCalmar | 0.0048 | [-0.1280, 0.1086] | 0.605 |
| dMartin | 0.0416 | [-0.3187, 0.3826] | 0.622 |
| dMaxDD | -0.0009 | [-0.0177, 0.0136] | 0.406 |

**block=42**

| metric | mean | 95% CI | p>0 |
|---|---|---|---|
| dCalmar | 0.0082 | [-0.0939, 0.0794] | 0.670 |
| dMartin | 0.0372 | [-0.2666, 0.3369] | 0.637 |
| dMaxDD | -0.0005 | [-0.0113, 0.0076] | 0.487 |

### C4 EW vs IV WITHIN ewobj (pure sizing at ewobj): ewobj+EW - ewobj+IV


**block=21**

| metric | mean | 95% CI | p>0 |
|---|---|---|---|
| dCalmar | 0.0217 | [-0.1318, 0.1677] | 0.667 |
| dMartin | 0.1175 | [-0.3434, 0.6020] | 0.722 |
| dMaxDD | -0.0002 | [-0.0205, 0.0192] | 0.495 |

**block=42**

| metric | mean | 95% CI | p>0 |
|---|---|---|---|
| dCalmar | 0.0174 | [-0.1916, 0.1863] | 0.625 |
| dMartin | 0.1283 | [-0.4927, 0.6975] | 0.690 |
| dMaxDD | -0.0014 | [-0.0297, 0.0198] | 0.511 |

### C5 EW vs IV WITHIN ivobj (pure sizing at ivobj): ivobj+EW - ivobj+IV


**block=21**

| metric | mean | 95% CI | p>0 |
|---|---|---|---|
| dCalmar | 0.0145 | [-0.1429, 0.1636] | 0.621 |
| dMartin | 0.0902 | [-0.3765, 0.5747] | 0.682 |
| dMaxDD | -0.0005 | [-0.0205, 0.0186] | 0.487 |

**block=42**

| metric | mean | 95% CI | p>0 |
|---|---|---|---|
| dCalmar | 0.0101 | [-0.1964, 0.1786] | 0.595 |
| dMartin | 0.1033 | [-0.5147, 0.6950] | 0.657 |
| dMaxDD | -0.0016 | [-0.0297, 0.0193] | 0.507 |

## Verdict

UNIFORM NOISE. Across the FULL 2x2 (all matched and mismatched cells), EVERY pairwise contrast (C1-C5) on EVERY path-independent metric (dSharpe, dSortino, dCVaR) spans 0 at BOTH block sizes (21 and 42). On the min-var 3-of-4 trio, SIZING (EW vs IV), OBJECTIVE (ewobj vs ivobj), and COHERENCE (matched vs mismatched) are ALL statistical noise on the path-independent metrics. The incoherent cells -- including ivobj+EW (min-var TARGETING inv-vol, then sized equal-weight) -- are indistinguishable from the coherent ones.


DISCIPLINE: single in-sample test; path-independent metrics drive significance; path-dependent point-est is context only. All CIs (signed) reported at BOTH block sizes. Wide CIs = LOW POWER: 'cannot distinguish' is NOT 'proven equal'. No recommendation.
