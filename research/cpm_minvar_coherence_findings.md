# Min-var coherence: is the EW-sizing edge a selection-objective/sizing artifact?

Throwaway research. Read-only re production; no prod/memo/cpm_live edits; no commit.

Anchor (clean, via harness): Sharpe 1.1658, MaxDD -0.1297, Calmar 1.0137.


## Question / hypothesis

Current min-var subset minimizes EQUAL-WEIGHT portfolio variance (`_min_var_subset`: w=1/m, v=w^2*cov_sub.sum()). Prior study found MINVAR+EW-sizing the strongest Sharpe cell (clean 1.2711, only CI excluding 0). Is that a coherence artifact (select for low EW-variance, then EW-weight) rather than a real EW sizing edge? Fair test pairs each sizing with its OWN matched selection objective: build `minvar_ivobj` (minimize INVERSE-VOL portfolio variance over m-subsets) and compare COHERENT-EW vs COHERENT-IV.


## Method

- Engine: research/cpm_harness.py (mooex T+1, both-252, 10 bps/side). Anchor verified first.

- 2x2 selection objective {minvar_ewobj, minvar_ivobj} x sizing {EW, IV}, m=3 of top-4, full-risk-on-drop renormalize over kept trio. Everything else byte-identical to prod (universe/canary/trend/safe).

- References: PROD (top-4 IV, anchor), PROD_EW (top-4 + EW).

- Metrics: clean (DECISION) + ext + per-crisis + annualized one-way turnover (net 10 bps). Paired block bootstrap B=2000 (block=21) vs PROD and COHERENT-EW vs COHERENT-IV directly. 3-seg sequential walk-forward.


## 2x2 + references (clean = DECISION window)

| cell | clean Sharpe | clean Calmar | clean MaxDD | ext Sharpe | ext Calmar | ext MaxDD | turnover/yr |
|---|---|---|---|---|---|---|---|
| PROD (rank top-4 + IV) [anchor] | 1.1658 | 1.0137 | -0.1297 | 1.2004 | 0.8571 | -0.1573 | 2.581 |
| PROD_EW (rank top-4 + EW) | 1.1317 | 1.0147 | -0.1305 | 1.1868 | 0.8718 | -0.1621 | 2.444 |
| COHERENT-EW (ewobj + EW) [matched] | 1.2711 | 1.0883 | -0.1303 | 1.2969 | 0.9458 | -0.1522 | 2.958 |
| MINVAR_IV (ewobj + IV) [mismatch] | 1.2622 | 1.2196 | -0.1135 | 1.2624 | 0.9135 | -0.1492 | 2.988 |
| COHERENT-IV (ivobj + IV) [matched] | 1.2501 | 1.1846 | -0.1154 | 1.2657 | 0.9960 | -0.1363 | 2.998 |
| ivobj + EW [mismatch] | 1.2509 | 1.0688 | -0.1303 | 1.2906 | 1.0477 | -0.1362 | 2.977 |

## Per-crisis Sharpe (ext curve)

| cell | GFC_2007_10__2009_06 | COVID_2020_02__2020_06 | Y2022_full | Y2025_tariff_02_19__06_12 |
|---|---|---|---|---|
| PROD (rank top-4 + IV) [anchor] | 0.5407 | 1.1913 | -0.2992 | 0.2399 |
| PROD_EW (rank top-4 + EW) | 0.4433 | 1.0741 | -0.1572 | 0.2973 |
| COHERENT-EW (ewobj + EW) [matched] | 0.8152 | 1.1134 | 0.0958 | 0.3610 |
| MINVAR_IV (ewobj + IV) [mismatch] | 0.7443 | 1.2457 | -0.1136 | 0.2434 |
| COHERENT-IV (ivobj + IV) [matched] | 0.4903 | 1.2457 | -0.1136 | 0.2031 |
| ivobj + EW [mismatch] | 0.4325 | 1.1134 | 0.0958 | 0.2971 |

## Per-crisis MaxDD (ext curve)

| cell | GFC_2007_10__2009_06 | COVID_2020_02__2020_06 | Y2022_full | Y2025_tariff_02_19__06_12 |
|---|---|---|---|---|
| PROD (rank top-4 + IV) [anchor] | -0.1188 | -0.1050 | -0.0796 | -0.1297 |
| PROD_EW (rank top-4 + EW) | -0.1573 | -0.1121 | -0.0744 | -0.1275 |
| COHERENT-EW (ewobj + EW) [matched] | -0.1314 | -0.1020 | -0.0517 | -0.1070 |
| MINVAR_IV (ewobj + IV) [mismatch] | -0.1033 | -0.1011 | -0.0619 | -0.1135 |
| COHERENT-IV (ivobj + IV) [matched] | -0.1033 | -0.1011 | -0.0619 | -0.1154 |
| ivobj + EW [mismatch] | -0.1314 | -0.1020 | -0.0517 | -0.1100 |

## Paired bootstrap vs PROD (clean, B=2000, block=21)

| cell | dSharpe mean [95% CI] | p>0 | dCalmar mean [95% CI] | dMaxDD mean [95% CI] |
|---|---|---|---|---|
| PROD_EW (rank top-4 + EW) | -0.0347 [-0.0934, 0.0198] | 0.131 | -0.0274 [-0.1635, 0.0919] | -0.0068 [-0.0301, 0.0114] |
| COHERENT-EW (ewobj + EW) [matched] | 0.1057 [0.0017, 0.2126] | 0.977 | 0.1334 [-0.0911, 0.3982] | 0.0125 [-0.0198, 0.0528] |
| MINVAR_IV (ewobj + IV) [mismatch] | 0.0969 [-0.0053, 0.1962] | 0.968 | 0.1117 [-0.0837, 0.3339] | 0.0128 [-0.0141, 0.0469] |
| COHERENT-IV (ivobj + IV) [matched] | 0.0843 [-0.0244, 0.1891] | 0.941 | 0.1069 [-0.1022, 0.3417] | 0.0136 [-0.0152, 0.0460] |
| ivobj + EW [mismatch] | 0.0850 [-0.0226, 0.1931] | 0.932 | 0.1214 [-0.1132, 0.3992] | 0.0131 [-0.0212, 0.0526] |

## (a) COHERENT-EW vs COHERENT-IV head-to-head (clean, direct paired bootstrap)

Positive = COHERENT-EW minus COHERENT-IV.

| metric | mean | 95% CI | p(EW>IV) |
|---|---|---|---|
| dSharpe | 0.0214 | [-0.0579, 0.0980] | 0.707 |
| dCalmar | 0.0265 | [-0.1521, 0.2064] | 0.654 |
| dMaxDD | -0.0011 | [-0.0259, 0.0216] | 0.450 |

### COHERENT-EW vs COHERENT-IV 3-seg walk-forward (clean)

Positive dSharpe = COHERENT-EW ahead.

| segment | EW Sharpe | IV Sharpe | dSharpe | EW Calmar | IV Calmar | dCalmar |
|---|---|---|---|---|---|---|
| 2008-05-30..2014-05-27 | 1.0844 | 1.0809 | 0.0035 | 1.0359 | 1.2627 | -0.2267 |
| 2014-05-28..2020-05-21 | 1.1875 | 1.1681 | 0.0194 | 1.0409 | 1.0248 | 0.0161 |
| 2020-05-22..2026-05-22 | 1.5805 | 1.5252 | 0.0553 | 1.7230 | 1.5350 | 0.1881 |

(base = COHERENT-IV, var = COHERENT-EW.)


## (b) Subset overlap: ewobj vs ivobj trio choice

Selection-active months (n_pos==4): 168. Same trio: 158 (94.0%). Avg Jaccard: 0.9702. Differing months: 10.


Differing-month examples (date, ewobj trio, ivobj trio):

- 2010-08-31: ew=['EEM', 'GLD', 'TLT'] iv=['GLD', 'TLT', 'VNQ']
- 2010-11-30: ew=['DBC', 'GLD', 'QQQ'] iv=['GLD', 'QQQ', 'SPHQ']
- 2011-03-31: ew=['DBC', 'GLD', 'SPHQ'] iv=['GLD', 'QQQ', 'SPHQ']
- 2011-04-29: ew=['DBC', 'GLD', 'SPHQ'] iv=['GLD', 'QQQ', 'SPHQ']
- 2023-12-29: ew=['EFA', 'QQQ', 'SPHQ'] iv=['EFA', 'SPHQ', 'VNQ']
- 2024-01-31: ew=['EFA', 'QQQ', 'SPHQ'] iv=['EFA', 'SPHQ', 'VNQ']
- 2024-02-29: ew=['EFA', 'QQQ', 'SPHQ'] iv=['EFA', 'SPHQ', 'VNQ']
- 2024-09-30: ew=['EEM', 'GLD', 'SPHQ'] iv=['GLD', 'SPHQ', 'VNQ']
- 2025-02-28: ew=['EFA', 'GLD', 'SPHQ'] iv=['GLD', 'SPHQ', 'VNQ']
- 2026-01-30: ew=['DBC', 'EEM', 'EFA'] iv=['DBC', 'EFA', 'GLD']

## (c) Coherence premium within each sizing (clean, paired bootstrap)

Does the MATCHED objective beat the MISMATCHED one for that sizing?

| test | dSharpe mean | 95% CI | p>0 |
|---|---|---|---|
| IV sizing: ivobj(matched) - ewobj(mismatch) | -0.0126 | [-0.0601, 0.0397] | 0.310 |
| EW sizing: ewobj(matched) - ivobj(mismatch) | 0.0207 | [-0.0390, 0.0766] | 0.750 |

## (d) PROD top-4: EW vs IV (pure sizing on unchanged selection, clean)

Positive = PROD_EW minus PROD (IV).

| metric | mean | 95% CI | p(EW>IV) |
|---|---|---|---|
| dSharpe | -0.0347 | [-0.0934, 0.0198] | 0.131 |
| dCalmar | -0.0274 | [-0.1635, 0.0919] | 0.316 |
| dMaxDD | -0.0068 | [-0.0301, 0.0114] | 0.231 |

## Verdict

LARGELY a coherence artifact: once IV gets its own matched objective, the EW edge shrinks/vanishes (clean Sharpe EW 1.2711 vs IV 1.2501, EW-vs-IV mean dSharpe 0.0214, p(EW>IV)=0.707, CI includes 0). The prior 'EW beats IV on min-var' was driven by objective/sizing coherence, not a real sizing advantage. Best coherent pair (clean Sharpe): COHERENT-EW (EW 1.2711 / IV 1.2501); ext: COHERENT-EW (EW 1.2969 / IV 1.2657). Turnover/yr EW 2.958 vs IV 2.998 (net 10 bps already in returns). Objective choice barely matters: ewobj and ivobj pick the SAME trio 94.0% of active months (avg Jaccard 0.970); sizing is effectively the only lever. Low ceiling: all paired bootstrap CIs are wide; treat differences within the CI band as within-noise. Decision metric is the clean window.

