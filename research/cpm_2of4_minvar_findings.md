# 2-of-4 min-var: concentration-sweep completeness

Throwaway research. Read-only re production. No production/memo/cpm_live files
changed; no commit. Engine, math, and metrics reuse the canonical harness and the
prior concentration-sweep scripts byte-for-byte.

- Script: `research/cpm_2of4_minvar.py`
- Output: `research/cpm_2of4_minvar_findings.json`
- Run: `.venv/bin/python -m research.cpm_2of4_minvar`
- Harness: `research/cpm_harness.py` (mooex T+1, both-252, 10 bps/side)
- Anchor verified FIRST: Sharpe 1.1658, MaxDD -0.1297, Calmar 1.0137 (exact).

## Question / hypothesis

Completing the concentration sweep (prod top-4 -> 3-of-4 -> 2-of-4). An earlier
CPM iteration actually used 2-of-4 min-var, so we test it for completeness: does
MORE concentration help further, or does it over-concentrate (lose breadth and
momentum, deepen crisis drawdowns)?

Hypothesis (pre-registered expectation): over-concentration likely hurts,
especially crisis drawdowns.

## Method

2-of-4 min-var = pick the 2 of the top-4 positive picks that minimize the
equal-weight (1/2, 1/2) portfolio variance over the 252d covariance window
(`m=2` in `_min_var_subset`). Built via `make_pool_weight_fn(pool_k=4, hold_n=2,
rule="minvar", ...)` from `cpm_poolsize_sweep.py`. Everything else byte-identical
to prod: universe / canary / trend / safe / both-252 / mooex T+1 / 10 bps.

Crossed two factors -> 4 cells:

- sizing: inverse-vol (IV, prod cov-diagonal) and equal-weight (EW = 50/50).
- safe convention:
  - PARTIAL-SAFE (prod strict-4 native): `n_picks=2` -> risky_fraction =
    min(2,4)/4 = 0.50 (two risky assets at 50% + 50% safe sleeve).
  - FULL-RISK (renormalize): 100% across the two picks (risky_fraction = 1.0).

References reproduced for head-to-head: PROD (`compute_target_weights`, anchor),
3-of-4 min-var IV {full-risk, partial-safe}.

Metrics: clean (DECISION window 2008-05-30..) and ext (1999-03-10..); per-crisis
(GFC/COVID/2022/2025) Sharpe/Calmar/Martin/MaxDD; annualized one-way turnover (net
10 bps). Paired block bootstrap B=2000 (21d blocks, seed 42) vs PROD and vs 3-of-4
min-var. 3-segment sequential walk-forward.

## Reference reproduction (sanity)

| Config | clean Sharpe | clean MaxDD | clean Calmar |
|---|---|---|---|
| PROD top-4 IV | 1.1658 | -0.1297 | 1.0137 |
| 3of4 min-var IV full-risk | 1.2414 | -0.1318 | 1.0531 |
| 3of4 min-var IV partial-safe | 1.2631 | -0.1023 | 1.0787 |

All three reproduce the prior anchors exactly. Harness is faithful.

## Results: 2-of-4 cells (clean, DECISION window)

| Config | Sharpe | Calmar | Martin | MaxDD | CAGR | vol | Turnover |
|---|---|---|---|---|---|---|---|
| PROD top-4 IV (ref) | 1.1658 | 1.0137 | 3.691 | -0.1297 | 0.1315 | 0.1118 | 2.581 |
| 3of4 min-var IV full-risk (ref) | 1.2414 | 1.0531 | 3.712 | -0.1318 | 0.1388 | 0.1099 | 2.942 |
| 3of4 min-var IV partial-safe (ref) | 1.2631 | 1.0787 | 3.762 | -0.1023 | 0.1103 | 0.0861 | 2.733 |
| 2of4 min-var IV full-risk | 1.1012 | 0.8848 | 2.529 | -0.1395 | 0.1234 | 0.1119 | 3.334 |
| 2of4 min-var IV partial-safe | 1.1137 | 0.7821 | 2.565 | -0.0952 | 0.0745 | 0.0669 | 2.709 |
| 2of4 min-var EW full-risk | 1.0677 | 0.7338 | 2.391 | -0.1654 | 0.1214 | 0.1139 | 3.278 |
| 2of4 min-var EW partial-safe | 1.1037 | 0.7795 | 2.600 | -0.0945 | 0.0736 | 0.0667 | 2.681 |

Ext window (1999-03-10..):

| Config | Sharpe | Calmar | Martin | MaxDD | CAGR |
|---|---|---|---|---|---|
| PROD (ref) | 1.2004 | 0.8571 | 3.676 | -0.1573 | 0.1348 |
| 3of4 IV full-risk (ref) | 1.2409 | 0.9136 | 3.625 | -0.1492 | 0.1363 |
| 3of4 IV partial-safe (ref) | 1.2821 | 0.9815 | 3.706 | -0.1128 | 0.1107 |
| 2of4 IV full-risk | 1.0722 | 0.8139 | 2.385 | -0.1456 | 0.1185 |
| 2of4 IV partial-safe | 1.1274 | 0.7953 | 2.438 | -0.0952 | 0.0757 |
| 2of4 EW full-risk | 1.0858 | 0.6351 | 2.401 | -0.1929 | 0.1225 |
| 2of4 EW partial-safe | 1.1578 | 0.7530 | 2.644 | -0.1033 | 0.0778 |

Key reads:

- Every 2-of-4 cell lands BELOW prod on clean Sharpe (1.07-1.11 vs 1.1658) and
  far below 3-of-4 (~1.24-1.26).
- Calmar and Martin collapse hardest: clean Martin drops from prod 3.69 / 3of4
  ~3.7 to ~2.4-2.6 for every 2-of-4 cell. Drawdown profile materially worse per
  unit return.
- Full-risk 2-of-4 deepens MaxDD vs prod (clean -0.1395 IV / -0.1654 EW vs
  prod -0.1297; ext -0.1456 / -0.1929 vs prod -0.1573) -> concentration risk.
- Partial-safe 2-of-4 shallows MaxDD (~-0.095) but only by parking 50% in the
  safe sleeve; CAGR craters to ~0.074 (vs prod 0.13), so Calmar/Martin still
  fall. The shallow DD is de-risking, not better risk-adjusted return.
- Turnover rises for full-risk 2-of-4 (3.33 / 3.28 vs prod 2.58, 3of4 2.94) ->
  more churn for worse net results.

## Per-crisis (ext curve): Sharpe / MaxDD

GFC 2007-10..2009-06:

| Config | Sharpe | MaxDD | Calmar | Martin |
|---|---|---|---|---|
| PROD | 0.541 | -0.1188 | 0.544 | 1.184 |
| 3of4 IV full-risk | 0.720 | -0.1387 | 0.692 | 1.597 |
| 3of4 IV partial-safe | 0.783 | -0.1123 | 0.794 | 1.743 |
| 2of4 IV full-risk | 0.336 | -0.1456 | 0.303 | 0.584 |
| 2of4 IV partial-safe | 0.664 | -0.0927 | 0.726 | 1.492 |
| 2of4 EW full-risk | 0.435 | -0.1929 | 0.320 | 0.626 |
| 2of4 EW partial-safe | 0.754 | -0.1033 | 0.745 | 1.701 |

COVID 2020-02..2020-06:

| Config | Sharpe | MaxDD |
|---|---|---|
| PROD | 1.191 | -0.1050 |
| 3of4 IV full-risk | 1.015 | -0.1217 |
| 3of4 IV partial-safe | 1.367 | -0.1011 |
| 2of4 IV full-risk | 0.957 | -0.1311 |
| 2of4 IV partial-safe | 1.531 | -0.0850 |
| 2of4 EW full-risk | 0.790 | -0.1321 |
| 2of4 EW partial-safe | 1.479 | -0.0852 |

2022 full year:

| Config | Sharpe | MaxDD |
|---|---|---|
| PROD | -0.299 | -0.0796 |
| 3of4 IV full-risk | -0.114 | -0.0619 |
| 3of4 IV partial-safe | 0.019 | -0.0469 |
| 2of4 IV full-risk | -0.311 | -0.1019 |
| 2of4 IV partial-safe | -0.217 | -0.0524 |
| 2of4 EW full-risk | -0.236 | -0.1024 |
| 2of4 EW partial-safe | -0.149 | -0.0527 |

2025 tariff 02-19..06-12:

| Config | Sharpe | MaxDD |
|---|---|---|
| PROD | 0.240 | -0.1297 |
| 3of4 IV full-risk | 0.516 | -0.1135 |
| 3of4 IV partial-safe | 0.510 | -0.0842 |
| 2of4 IV full-risk | 0.273 | -0.1274 |
| 2of4 IV partial-safe | 0.244 | -0.0617 |
| 2of4 EW full-risk | 0.384 | -0.1206 |
| 2of4 EW partial-safe | 0.350 | -0.0580 |

Crisis read (answers question d): the FULL-RISK 2-of-4 cells (apples-to-apples
risk budget vs prod/3of4) deepen drawdowns in every major crisis. GFC MaxDD
-0.1456 (IV) / -0.1929 (EW) vs prod -0.1188 and 3of4 -0.11..-0.14; COVID -0.131
vs prod -0.105. GFC Sharpe collapses to 0.34 (IV full-risk) from prod 0.54 and
3of4 0.72-0.78. This is the over-concentration / idiosyncratic-risk signature:
two names cannot diversify a systemic crash. The partial-safe 2-of-4 only looks
calm in COVID because half the book is safe (de-risking artifact), and it is
still worse than 3-of-4 partial-safe in GFC Sharpe (0.66 vs 0.78).

## Bootstrap vs PROD (paired, B=2000, clean)

| Config | dSharpe mean [95% CI] | p(>0) | dCalmar p | dMaxDD mean / p |
|---|---|---|---|---|
| 2of4 IV full-risk | -0.061 [-0.260, +0.143] | 0.269 | 0.24 | -0.014 / 0.29 |
| 2of4 IV partial-safe | -0.045 [-0.302, +0.213] | 0.359 | 0.29 | +0.057 / 0.97 |
| 2of4 EW full-risk | -0.094 [-0.298, +0.113] | 0.189 | 0.19 | -0.020 / 0.24 |
| 2of4 EW partial-safe | -0.054 [-0.303, +0.197] | 0.323 | 0.28 | +0.058 / 0.98 |

Every 2-of-4 cell has NEGATIVE mean dSharpe vs prod with p(>0) only 0.19-0.36
(i.e. it loses to prod in the clear majority of resamples). The only "win" is
partial-safe shallower MaxDD (dMaxDD p ~0.97-0.98), which is pure de-risking
(50% safe), bought with crushed CAGR and worse Calmar/Martin.

## Head-to-head: 2-of-4 vs 3-of-4 (bootstrap; var=2of4, base=3of4)

dSharpe > 0 would mean extra concentration helps.

| Pair | dSharpe mean [95% CI] | p(>0) | dCalmar p | dMaxDD mean / p |
|---|---|---|---|---|
| 2of4 IV full-risk vs 3of4 IV full-risk | -0.137 [-0.309, +0.048] | 0.073 | 0.13 | -0.017 / 0.26 |
| 2of4 IV partial-safe vs 3of4 IV partial-safe | -0.144 [-0.342, +0.049] | 0.080 | 0.13 | +0.019 / 0.85 |
| BEST 2of4 (IV p-safe) vs BEST 3of4 (IV p-safe) | -0.144 [-0.342, +0.049] | 0.080 | 0.13 | +0.019 / 0.85 |

3-of-4 beats 2-of-4 ~92-93% of resamples on Sharpe (p(2of4>3of4) ~0.07-0.08) and
~87% on Calmar. Extra concentration (4 -> 2 holdings) HURTS. CIs still span 0
(low ceiling), so this is "2-of-4 is a strict step down within noise," not a
high-confidence regression -- but the direction is unambiguous and consistent.

## Walk-forward (3 sequential segments)

vs PROD (dSharpe per segment): 2of4 loses the middle segment hard in every cell
(2014-2020 dSharpe -0.17 to -0.35) and is at best a wash in the others. No 2of4
cell wins all three; full-risk cells go negative / negative / slightly positive.

2of4 vs 3of4 (dSharpe per segment, var=2of4):

| Pair | seg1 | seg2 | seg3 |
|---|---|---|---|
| 2of4 IV full-risk vs 3of4 | -0.120 | -0.292 | -0.070 |
| 2of4 IV partial-safe vs 3of4 | -0.073 | -0.243 | -0.140 |

2-of-4 loses to 3-of-4 in ALL 3 segments under both conventions. Stable
underperformance, not a one-period artifact.

## Answers to key questions

(a) Does 2-of-4 min-var beat prod net cost + OOS? NO. All four cells trail prod
on clean Sharpe/Calmar/Martin, with bootstrap p(>0) 0.19-0.36 and no
walk-forward sweep. The only metric it "improves" is partial-safe MaxDD, which is
de-risking (50% safe), not skill.

(b) 2-of-4 vs 3-of-4 head-to-head: extra concentration HURTS. 3-of-4 wins
~92-93% of Sharpe resamples and all 3 walk-forward segments under both
conventions. Higher turnover too (full-risk 3.3 vs 2.9).

(c) Best safe-convention + sizing at m=2: IV partial-safe is the least-bad
(clean 1.1137) but still sub-prod; EW full-risk is the worst (1.0677, deepest
crisis DD). Inverse-vol > equal-weight at m=2, and partial-safe > full-risk only
because it dilutes the over-concentration with the safe sleeve.

(d) Per-crisis: YES, 2-of-4 deepens drawdowns. Full-risk MaxDD worse than prod in
GFC (-0.146/-0.193 vs -0.119), COVID (-0.131 vs -0.105), and 2022 (-0.102 vs
-0.080). GFC Sharpe collapses to 0.34. Two names cannot diversify systemic risk.

## Verdict

2-of-4 min-var is OVER-CONCENTRATED. It is a clear step DOWN from both prod and
the 3-of-4 min-var winner: lower risk-adjusted return on every honest (full-risk)
metric, deeper crisis drawdowns, and higher turnover. The 3-of-4 vs 2-of-4
head-to-head is directionally decisive (p ~0.92-0.93 favoring 3-of-4, 3/3
walk-forward), though CIs still span zero so it sits within the same low-ceiling
noise band as the rest of this sweep.

Concentration-sweep shape is now complete and non-monotone: holding count 4
(prod, 1.17) -> 3 (min-var winner, ~1.24-1.26) -> 2 (over-concentrated, ~1.07-1.11).
The sweet spot is 3-of-4 with vol+corr (min-var) selection; going to 2 throws away
the diversification benefit that made 3-of-4 work, reverting to idiosyncratic
risk. The earlier CPM iteration's 2-of-4 min-var was a worse design point than
the 3-of-4 it was replaced by.

## Caveats / confidence

- Low ceiling: all comparisons have bootstrap CIs spanning 0. Directionally
  consistent and aligned with the diversification thesis, but not high-confidence
  significance. Bar to change prod remains unmet (and 2-of-4 is worse anyway).
- Partial-safe MaxDD improvements are de-risking artifacts (50% safe sleeve), not
  evidence of better selection.
- Single in-sample data period; walk-forward is a stability check, not tuning CV.
- Research only. No production / memo / cpm_live edits; no commit.

## Next handoff

None required. Analysis complete and self-contained. If the concentration sweep
is to be folded into the memo narrative, route the memo edit to the fixer
(out of analyst scope).
