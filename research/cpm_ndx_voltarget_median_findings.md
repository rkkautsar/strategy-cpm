# NDX top-5 slot vol-target: adaptive MEDIAN (and expanding) target estimators

Analyst study. Read-only re production (ndx_sleeve_live.py / prod / voltarget /
memo NOT edited). Research artifacts only; no commit.

Question: does a ROBUST adaptive target -- median of the trailing N MONTHLY
realized-vol observations -- recover the 2021 drawdown protection that the prior
adaptive (trailing-252d MEAN, ADAPT-RV252) FAILED to deliver, while staying
parameter-free? Follow-up: does the EXPANDING-window long-run average (academic
parameter-free anchor, Bongaerts-Kang-van Dijk 2020) -- the lookback->all
endpoint of the median spectrum -- match fixed-absolute on 2021 DD?

Mechanism (identical across all configs): TOP-5 discrete drop-lowest-momentum
slot-replacement. scale = min(1, target/RV_short); n_risky = round(scale*5)
clipped to [0,k]; drop the (5-n) lowest-momentum names to safe; keep top-n EW at
1/5 each. The ONLY variable = the TARGET feeding scale.

## Method / reproduction

- Harness: `research/cpm_ndx_voltarget_median_harness.py` (adds MEDIAN +
  EXPAND target modes; reuses spec-study `_basket_vol`, gate, partial-safe,
  cost/exposure helpers). Run: `research/cpm_ndx_voltarget_median_run.py`.
- Engine: unmodified `ndx_sleeve_live.run_ndx_backtest` (gate TIP+SPY-trend+SPY
  RV20<RV252, safe rotation, T+1 MOO, 10bps/side, delisting haircut, PIT
  membership) via monkeypatched `compute_ndx_weights`.
- MEDIAN target = percentile (default 50th) of trailing N completed-calendar-
  month RV observations (one RV/month = annualized std of that month's daily
  EW-basket returns, >=15 days; current partial month excluded -> lagged).
- EXPAND target = MEAN of ALL completed monthly RV obs from inception to t-1
  (lookback expands, never resets).
- Windows: clean 2008-05-30..2026-05-22; stress/ext 1999-03-10..2026-05-22.
  Bootstrap = paired block, B=2000, block=21, seed=42. WF = 3-seg.
- Cmd: `.venv/bin/python research/cpm_ndx_voltarget_median_run.py`
- Caveat: cached dataset; absolute levels may shift slightly vs a prod refresh.
  Apples-to-apples across configs (identical engine). All lookbacks/percentiles
  are A-PRIORI to MAP the relative->absolute spectrum, NOT to optimize a winner.

## Config table (clean 2008+)

| config         | Sharpe | Sortino | CVaR  | MaxDD  | CAGR  | vol   | TO/yr | slotEv/yr | meanExp | 2021unwind DD |
|----------------|--------|---------|-------|--------|-------|-------|-------|-----------|---------|---------------|
| NONE (prod)    | 1.281  | 1.962   | 8.40  | -0.314 | 0.314 | 0.236 | 5.16  | 0.00      | 1.000   | -0.314 |
| FIXED 0.25     | 1.311  | 2.019   | 8.78  | -0.224 | 0.256 | 0.188 | 4.98  | 1.77      | 0.839   | -0.196 |
| FIXED 0.30     | 1.262  | 1.922   | 8.30  | -0.278 | 0.264 | 0.202 | 5.11  | 1.65      | 0.901   | -0.224 |
| ADAPT-RV252 w20| 1.318  | 2.035   | 8.74  | -0.314 | 0.315 | 0.228 | 5.22  | 1.42      | 0.965   | -0.314 |
| ADAPT-RV252 w60| 1.302  | 1.998   | 8.59  | -0.314 | 0.308 | 0.226 | 5.10  | 1.12      | 0.965   | -0.314 |
| MED-12 w20     | 1.347  | 2.081   | 8.93  | -0.314 | 0.310 | 0.219 | 5.20  | 2.25      | 0.934   | -0.314 |
| MED-12 w60     | 1.314  | 2.016   | 8.70  | -0.314 | 0.299 | 0.218 | 5.03  | 2.01      | 0.925   | -0.314 |
| MED-24 w60     | 1.292  | 1.971   | 8.47  | -0.278 | 0.282 | 0.210 | 4.93  | 2.13      | 0.895   | -0.261 |
| MED-36 w60     | 1.275  | 1.940   | 8.35  | -0.284 | 0.269 | 0.204 | 4.92  | 2.42      | 0.884   | -0.284 |
| MED-12 p40 w60 | 1.294  | 1.977   | 8.53  | -0.314 | 0.279 | 0.207 | 4.92  | 2.42      | 0.888   | -0.314 |
| EXPAND w20     | 1.314  | 2.014   | 8.65  | -0.314 | 0.311 | 0.226 | 5.20  | 0.71      | 0.976   | -0.314 |
| EXPAND w60     | 1.265  | 1.922   | 8.25  | -0.314 | 0.293 | 0.223 | 5.13  | 0.53      | 0.971   | -0.314 |

Per-crisis (ext, MaxDD): dotcom/GFC/COVID/2022/2025 are IDENTICAL (~-0.12 /
-0.09..-0.10 / -0.05 / -0.00 / -0.04..-0.05) across ALL configs -- the prod gate
already covers every V-shaped vol crisis. The ONLY differentiating episode is
the 2021 risk-on slow-grind unwind (non-gated). Stress (ext 1999+) Sharpe/MaxDD
track clean: protection only ever appears in MaxDD via the 2021 episode.

## 2021 path: target vs RV_short (why median fails, w60)

```
month       RV_short  target  scale  n   exp     (target = trailing estimator)
ADAPT-RV252:  ~0.40    ~0.40   ~1.0   5   1.0   mean rides up with short -> blind
MED-12:       0.47     0.49    1.00   5   1.0   Jan21: median still >= short
              0.44     0.33    0.74   4   0.8   Mar21: brief de-risk...
              0.41     0.32    0.78   4   0.8   ...then short FALLS faster, re-risks
MED-24:       0.47     0.37    0.79   4   0.8   anchored lower -> de-risks Dec20-May21
MED-36:       0.47     0.43    0.92   5   1.0   anchor creeps up, weaker than MED-24
EXPAND:       0.47     0.46    0.99   5   1.0   long-run MEAN ~0.42-0.53 -> blind
```

The structural failure: every self-referential target anchors to the basket's
OWN realized vol, which for a 5-stock momentum tech basket is structurally HIGH
(~0.35-0.50 annualized). When 2021 short vol runs ~0.40-0.47, the trailing
reference sits at a similar level, so target/RV_short ~ 1 and the overlay never
de-risks. MED-12 (12-month robust) is still dominated by the 2020 COVID +
recovery high-vol months -> median ~0.40-0.49 -> blind, indistinguishable from
ADAPT-RV252 (MaxDD/2021 = -0.314, zero protection). Only stretching the median
lookback to 24-36 months lets a few pre-COVID low-vol months pull the median
DOWN (~0.32-0.37) so target finally sits below the 2021 short vol -> partial
de-risk.

## Lookback spectrum (relative -> absolute), 2021 unwind DD

| target                | 2021 unwind DD | clean MaxDD | meanExp |
|-----------------------|----------------|-------------|---------|
| ADAPT-RV252 (mean 1y) | -0.314 (none)  | -0.314      | 0.965   |
| MED-12                | -0.314 (none)  | -0.314      | 0.925   |
| MED-12 p40 (lower)    | -0.314 (none)  | -0.314      | 0.888   |
| MED-24                | -0.261         | -0.278      | 0.895   |
| MED-36                | -0.284         | -0.284      | 0.884   |
| EXPAND (all history)  | -0.314 (none)  | -0.314      | 0.971   |
| FIXED 0.30            | -0.224         | -0.278      | 0.901   |
| FIXED 0.25            | -0.196         | -0.224      | 0.839   |

Spectrum is NON-monotone and never reaches fixed. MED-12 ~ ADAPT (blind);
MED-24/36 recover PARTIAL protection (-0.26/-0.28, vs fixed -0.20/-0.22); the
EXPAND endpoint does NOT continue toward fixed -- it REVERTS to zero protection
(-0.314). Reason: the expanding MEAN is pulled UP by the dotcom/GFC/COVID crisis
months baked permanently into the long-run average (~0.42-0.53), far above the
0.25 absolute level needed to bind, and even above the 2021 short vol. The
robust 24/36-month median wins only because its trailing horizon DROPS the
oldest crisis months while a low-vol 2017-19 stretch sits in-window -- a
fragile, regime-timing accident, not a stable anchor. p40 of 12 months does NOT
help (still 2020-dominated).

## Bootstrap (clean, B=2000 block=21 seed=42; d = A - B)

| pair                          | dSharpe [lo,hi] p>0      | dMaxDD [lo,hi] p>0        |
|-------------------------------|--------------------------|---------------------------|
| MED-12 w20 vs FIXED-0.25      | +0.036 [-0.11,+0.18] 0.69| -0.043 [-0.12,+0.03] 0.18 |
| MED-12 w60 vs FIXED-0.25      | +0.004 [-0.14,+0.14] 0.51| -0.048 [-0.12,+0.02] 0.11 |
| MED-12 w20 vs ADAPT-RV252 w20 | +0.029 [-0.02,+0.08] 0.89| +0.015 [-0.01,+0.06] 0.76 |
| MED-12 w60 vs ADAPT-RV252 w60 | +0.012 [-0.03,+0.06] 0.68| +0.009 [-0.01,+0.05] 0.66 |
| MED-12 w20 vs NONE            | +0.067 [+0.00,+0.14] 0.98| +0.026 [-0.00,+0.09] 0.85 |
| MED-12 w60 vs NONE            | +0.034 [-0.04,+0.11] 0.83| +0.021 [-0.01,+0.08] 0.76 |
| MED-36 w60 vs FIXED-0.25      | -0.034 [-0.15,+0.09] 0.29| -0.045 [-0.11,+0.01] 0.07 |
| EXPAND w60 vs FIXED-0.25      | -0.044 [-0.17,+0.09] 0.25| -0.066 [-0.14,+0.00] 0.03 |
| EXPAND w20 vs FIXED-0.25      | +0.004 [-0.13,+0.15] 0.52| -0.064 [-0.13,+0.01] 0.04 |
| EXPAND w60 vs NONE            | -0.014 [-0.07,+0.04] 0.30| +0.003 [-0.02,+0.04] 0.49 |

Reading: median/expanding vs ADAPT-RV252 -> dMaxDD ~ 0 (indistinguishable; they
are the SAME blind family). vs FIXED-0.25 -> dMaxDD negative; EXPAND vs
FIXED-0.25 is the only SIGNIFICANT DD gap (p=0.03-0.04, CI excludes 0): fixed
absolute beats the expanding anchor on drawdown. Sharpe differences are noise
everywhere (CIs span 0). EXPAND vs NONE -> dMaxDD ~ 0 (p=0.49): expanding adds
NOTHING over no-de-risk -- it never binds.

## Walk-forward (3-seg Sharpe | MaxDD)

```
NONE          1.18 1.25 1.47 | -0.17 -0.17 -0.31
FIXED 0.25    1.20 1.27 1.46 | -0.17 -0.17 -0.22   <- only seg3 DD improves
FIXED 0.30    1.18 1.27 1.37 | -0.17 -0.17 -0.28
ADAPT-RV252   1.18 1.23 1.52 | -0.17 -0.17 -0.31
MED-12 w20    1.20 1.23 1.60 | -0.15 -0.15 -0.31
MED-12 w60    1.18 1.29 1.51 | -0.17 -0.17 -0.31
MED-24 w60    1.17 1.29 1.46 | -0.17 -0.17 -0.28
MED-36 w60    1.18 1.31 1.39 | -0.17 -0.17 -0.28
EXPAND w60    1.17 1.25 1.42 | -0.17 -0.17 -0.31
```

The decisive DD episode (2021) lives entirely in seg3. FIXED-0.25 is the only
config that cuts seg3 DD to -0.22; MED-24/36 reach -0.28; MED-12 / EXPAND /
ADAPT stay -0.31. Sharpe is WF-stable and statistically tied across the board.

## Verdict (a)-(e)

(a) NO. ADAPT-MEDIAN-12 does NOT de-risk in 2021 where ADAPT-RV252 did not:
both stay fully invested (exp ~0.93-0.97), 2021 unwind DD = -0.314 = the
no-de-risk floor. The 12-month median is still dominated by 2020 high-vol months
-> reference ~0.40-0.49 ~ RV_short -> scale ~ 1. Identical structural failure.

(b) NEITHER match nor clean intermediate. MED-12 = blind (= RV252-mean = prod
DD). Only the LONGER, more-anchored MED-24/36 become an intermediate (-0.26 /
-0.28), still strictly worse than FIXED-0.25 (-0.20) / 0.30 (-0.22). Parameter-
free MEDIAN does NOT recover the fixed floor.

(c) Spectrum CONFIRMS and SHARPENS the contamination thesis -- with a twist. As
the robust lookback lengthens (12 -> 24 -> 36 months) protection improves
PARTIALLY, consistent with "trailing-relative reference is regime-contaminated;
a longer horizon dilutes the recent spike." BUT the lookback->all endpoint
(EXPAND) does NOT converge to fixed -- it reverts to ZERO protection, because a
5-stock momentum basket's long-run AVERAGE vol is structurally high (~0.45) and
permanently inflated by past crises. The real lesson: the spectrum is
SELF-REFERENTIAL (anchored to the basket's own ~0.35-0.50 vol) at BOTH ends; it
only brushes fixed-like protection in a fragile middle (24/36mo) by accidentally
dropping old crisis months. Absolute protection requires an EXTERNAL fixed level
BELOW the basket's typical vol, which no self-referential estimator provides.

(d) No Sharpe cost vs fixed (all bootstrap CIs span 0; WF Sharpe tied). MEDIAN
trades MORE often (slotEv 2.0-2.4/yr vs fixed 1.65-1.77; EXPAND fewer 0.5-0.7
because it rarely moves off full risk). No WF stability advantage -- fixed's DD
is the more stable improvement (consistent seg3 cut); median's DD edge is
absent (MED-12) or accidental (MED-24/36).

(e) RECOMMENDATION: STICK WITH FIXED, level 0.25 (clean Sharpe 1.311, MaxDD
-0.224, 2021 -0.196; OOS winner from the prior spec study). It is the only
config that reliably recovers the 2021 floor. ADAPT-MEDIAN is NOT a parameter-
free equal: MED-12 is blind (= the failed RV252-mean), MED-24/36 are a worse,
lookback-tuned intermediate (re-introducing the very degrees of freedom the
"parameter-free" pitch was meant to remove), and the academically-motivated
EXPANDING anchor is fully blind here (dMaxDD vs fixed p=0.03). For a high-vol
concentrated NDX top-5 basket, only an EXTERNAL ABSOLUTE target de-risks the
non-gated 2021 grind; every self-referential (relative) estimator -- mean,
median, percentile, or expanding -- is contaminated by the basket's own high
vol. The BKvD expanding-anchor result does not transfer because their universe's
long-run vol sits near a sensible absolute cap; NDX top-5's does not.

## Caveats / confidence

- Confidence HIGH on the ranking/mechanism (DD differences are exposure-driven
  and explained by the explicit 2021 target-vs-RV_short paths; other crises are
  gate-covered and identical). Confidence MODERATE on exact DD magnitudes
  (cached dataset; absolute levels may shift slightly vs prod refresh).
- Single in-sample run; lookbacks/percentiles are a-priori to MAP the spectrum,
  not optimized -- MED-24/36 "wins" are explicitly flagged as fragile/accidental
  rather than a recommendation.
- Sharpe differences are statistically indistinguishable; the decision rests on
  MaxDD and parameter-freeness, both of which favor FIXED-0.25.
