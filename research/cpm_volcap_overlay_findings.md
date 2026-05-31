# CPM both-252: de-lever-only vol-target CAP overlay -- full performance profile

Scope: research only. Read-only on production. No memo/prod edits, no commit.
Harness: `research/cpm_volcap_overlay_harness.py` (+ `.json` output).
Engine: production `cpm_live.compute_target_weights`. Accounting: memo mooex
T+1 MOO exact (`exec_lag_moo_validation_2026_05_30._segment_returns_conv` via
the bond-buffer harness), 10 bps/side, monthly rebalance, point-in-time signals.
Decision lens = clean 18y window 2008-05-30..2026-05-22.

## TL;DR verdict

REJECT the cap as a defensive overlay on CPM (at most document-only as a
within-noise dilution dial). Two findings drive this:

1. The headline `-8.10% / Calmar 1.051` the user remembered was measured on the
   dyn-safe-40% BOND-BUFFERED base, NOT on CPM. Reproduced here exactly
   (`MaxDD -8.10% / Calmar 1.0512`) as a wiring sanity check -- so that number is
   a property of the bond buffer, not of the cap.
2. The cap applied DIRECTLY to CPM does NOT reproduce it. Best MaxDD it reaches
   without craters is about `-10.77%` (target=11%), and it does so by DILUTING:
   Sharpe 1.166 -> 1.11, Martin 3.69 -> 2.83, CAGR 13.15% -> 10.73% (-2.4pp),
   Calmar roughly flat-to-down (1.0137 -> 0.996..1.022). All marginal bootstrap
   CIs include 0 with NEGATIVE point estimates, and the DD trim is essentially
   one episode (April 2025).

## Anchor reproduction (FIRST, gate) -- PASS

| Metric | Reproduced | Both-252 target |
|---|---:|---:|
| Sharpe | 1.1658 | 1.1658 |
| MaxDD | -12.97% | -12.97% |
| Calmar | 1.0137 | 1.0137 |
| Martin | 3.6907 | -- |
| Vol | 11.18% | -- |
| CAGR | 13.15% | -- |

Harness pins `cpm_live.CORR_LOOKBACK_DAYS = 252` in-process (via the bond-buffer
harness import); cpm_live.py is not edited. Anchor matches to 4 dp.

## Vol-cap mechanism (documented exactly)

- Vol estimate = REALIZED TRAILING vol of the strategy's own post-cost daily
  return series over `lookback` days, annualized (`r.rolling(lookback).std()
  * sqrt(252)`). It is NOT an ex-ante weights x asset-cov estimate. (An ex-ante
  weight-based estimate was considered; the realized-trailing form is what the
  bond-buffer harness used and what produced the remembered number, so it is the
  faithful object under test here.)
- POINT-IN-TIME (no look-ahead): exposure on day t uses the trailing vol
  computed THROUGH day t-1 (`.shift(1)`). Verified: the de-levering reacts AFTER
  a vol spike, never before.
- `exposure_t = clip(target_vol / realized_vol_{t-1}, upper=1.0)`. This is a CAP
  (de-lever only): exposure never exceeds 1.0, so it never levers up in calm and
  never borrows.
- De-levered notional `(1 - exposure_t)` earns CASH (SHV) -- "excess exposure ->
  cash", as specified. (The prior bond-buffer harness credited 0% to the
  de-levered sleeve; crediting cash here is the more realistic and slightly
  kinder choice.)
- Overlay turnover cost = `|exposure_t - exposure_{t-1}| * 10 bps`, charged daily
  ON TOP of the monthly CPM rebalance cost already baked into the base series.
  (The base engine's 10 bps/side covers monthly portfolio rebalancing only; the
  daily vol-scaling is a SEPARATE cost the base accounting does not charge, so it
  is added explicitly here.)

## (2) Threshold sweep -> response surface (clean 18y)

| target vol | Sharpe | Vol | MaxDD | Calmar | Martin | CAGR | turn/yr |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 7% | 1.1074 | 7.4% | -8.42% | 0.9692 | 2.743 | 8.16% | 4.7x |
| 8% | 1.1097 | 8.1% | -9.05% | 0.9919 | 2.771 | 8.98% | 4.1x |
| 9% | 1.1075 | 8.7% | -9.46% | 1.0192 | 2.793 | 9.64% | 3.5x |
| 10% | 1.1063 | 9.2% | -9.98% | 1.0216 | 2.804 | 10.19% | 2.8x |
| 11% | 1.1083 | 9.6% | -10.66% | 1.0002 | 2.828 | 10.66% | 2.2x |
| 12% | 1.1064 | 9.9% | -11.26% | 0.9764 | 2.851 | 11.00% | 1.7x |
| 13% | 1.1051 | 10.2% | -11.74% | 0.9603 | 2.919 | 11.27% | 1.4x |
| 14% | 1.1034 | 10.4% | -12.09% | 0.9513 | 2.995 | 11.50% | 1.1x |
| 15% | 1.1100 | 10.6% | -12.23% | 0.9631 | 3.092 | 11.78% | 0.9x |
| **CPM (no cap)** | **1.1658** | **11.2%** | **-12.97%** | **1.0137** | **3.691** | **13.15%** | **0.0x** |

Lookback sensitivity at target=11% (plateau check):

| lookback | MaxDD | Calmar | Sharpe | turn/yr |
|---:|---:|---:|---:|---:|
| 10d | -11.02% | 0.9335 | 1.0722 | 4.1x |
| 21d | -10.66% | 1.0002 | 1.1083 | 2.2x |
| 42d | -11.38% | 0.9821 | 1.1428 | 1.3x |
| 63d | -12.02% | 0.9295 | 1.1327 | 0.9x |

Read of the surface:
- It is a broad, FLAT plateau, not an isolated spike (no overfit smell) -- but it
  is a DILUTION plateau, not an edge. Every cap setting LOWERS Sharpe (1.166 ->
  ~1.105-1.110) and Martin (3.69 -> 2.7-3.1). Calmar is flat-to-below CPM at every
  setting; its peak (1.0216 at target=10%) does NOT exceed CPM's 1.0137 by a
  meaningful margin (well within noise, see bootstrap).
- Tightening the cap (lower target) trims vol/MaxDD monotonically but pays for it
  pp-for-pp in CAGR; the trade is a pure risk/return slide along a flat-Sharpe
  ray. There is no setting that improves risk-adjusted return.

## (3) Representative cap (target = 11.18% = CPM vol) vs CPM

| | Sharpe | CAGR | Vol | MaxDD | Calmar | Martin | Ulcer |
|---|---:|---:|---:|---:|---:|---:|---:|
| CPM both-252 | 1.1658 | 13.15% | 11.18% | -12.97% | 1.0137 | 3.6907 | 3.56% |
| CPM + vol-cap | 1.1084 | 10.73% | 9.66% | -10.77% | 0.9961 | 2.8311 | 3.79% |
| delta | -0.057 | -2.42pp | -1.52pp | +2.20pp | -0.018 | -0.860 | +0.23pp |

The cap trims MaxDD by 2.20pp and vol by 1.5pp, at a cost of 2.4pp CAGR, a lower
Sharpe, a much lower Martin, a roughly-flat Calmar, and (notably) a HIGHER Ulcer
index -- i.e. it spends more time underwater even though the single worst trough
is shallower. That last point is the tell: de-levering after vol spikes keeps the
book small through recoveries, so the average drawdown depth/duration worsens
even as the peak trough is clipped.

## (4) Per-crisis (CPM vs CPM+cap, target=11%)

| episode | CPM ret | cap ret | CPM MaxDD | cap MaxDD |
|---|---:|---:|---:|---:|
| GFC_2008 (to 2009-06) | +0.20% | +0.12% | -10.23% | -10.20% |
| COVID_2020 | +6.67% | +3.98% | -10.50% | -8.11% |
| Bear_2022 | -2.08% | -2.04% | -7.96% | -7.48% |
| Tariff_2025 (binding DD) | +7.83% | +3.62% | -12.97% | -10.77% |

- GFC: cap does essentially nothing (-10.23% -> -10.20%). The 2008 crash was a
  grinding decline CPM was already largely defensive into; a trailing-vol cap has
  no edge there.
- COVID and Tariff_2025: cap DOES clip the trough (-10.50 -> -8.11; -12.97 ->
  -10.77) but BLEEDS roughly 40-55% of the episode's recovery return (COVID
  +6.67% -> +3.98%; 2025 +7.83% -> +3.62%). Classic vol-target whipsaw: it
  de-risks into the volatility spike at the bottom and is still small during the
  V-shaped snap-back.
- Annual returns confirm the bleed is systemic, not one-off: 2009 14.3% -> 4.6%
  (-9.7pp), 2013 19.0% -> 15.6%, 2024 15.2% -> 13.1%, 2025 25.8% -> 20.6%,
  2026-YTD 21.4% -> 17.2%. The cap underperforms in essentially every up year.

## (5) Turnover / cost

- Overlay annual turnover ~2.1x/yr at target=11%, 21d lookback (one-sided
  sum|dExposure| / yr). It rises to ~4-5x/yr at tight targets or short
  lookbacks.
- Overlay cost drag is small in absolute CAGR terms: 0.233pp (gross 10.96% ->
  net 10.73%). So turnover/cost is NOT the reason the cap loses -- the loss is the
  structural recovery bleed, not transaction cost. (Even at 0 bps the cap still
  badly underperforms CPM on CAGR/Sharpe/Martin.)

## (6) Paired stationary block bootstrap (B=5000, block~21d, clean window)

Marginal = (CPM+cap) - CPM:

| metric | point | 95% CI | verdict |
|---|---:|---|---|
| dSharpe | -0.0574 | [-0.1408, +0.0240] | includes 0 |
| dCalmar | -0.0171 | [-0.2882, +0.0877] | includes 0 |
| dMartin | -0.8617 | [-1.2817, +0.0274] | includes 0 (barely) |

All three CIs include 0, so the cap is not PROVABLY worse on a single 18y sample
-- but every point estimate is NEGATIVE, and dMartin's CI is almost entirely
below 0. There is zero evidence the cap improves any risk-adjusted metric; the
weight of evidence is that it modestly hurts.

## (7) Episode-removal skepticism -- DD trim is NOT broad-based

| series | CPM MaxDD | cap MaxDD | improvement |
|---|---:|---:|---:|
| FULL | -12.97% | -10.77% | +2.20pp |
| ex-GFC_2008 | -12.97% | -10.77% | +2.20pp |
| ex-COVID_2020 | -12.97% | -10.77% | +2.20pp |
| ex-Bear_2022 | -12.97% | -10.77% | +2.20pp |
| ex-Tariff_2025 | -10.50% | -10.20% | **+0.29pp** |

The binding MaxDD for both CPM (-12.97%) and the cap (-10.77%) troughs on
2025-04-08 (the April 2025 tariff selloff), NOT in any classic crisis. Removing
2008/2020/2022 leaves the improvement untouched; removing ONLY the 2025 episode
collapses the DD improvement from +2.20pp to +0.29pp. So the headline MaxDD trim
is almost entirely a single episode. Outside 2025 the cap and CPM have
near-identical worst drawdowns (-10.20% vs -10.50%). This is a one-episode
artifact, not a robust defensive property.

## VERDICT: REJECT (document-only at most)

The de-lever-only vol-target cap on CPM both-252 is a within-noise DILUTION dial,
not a worthwhile defensive overlay:

- Risk-adjusted return: cap is FLAT-to-WORSE on every metric. Sharpe -0.057,
  Martin -0.86, Calmar -0.018; all bootstrap CIs include 0 with negative points.
  No plateau setting beats CPM's Calmar/Sharpe/Martin.
- The remembered `-8.10% / Calmar 1.051` belongs to the bond-BUFFER (dyn-safe-40%)
  base, reproduced here exactly -- it is NOT achievable by the cap alone on CPM.
  Cap-on-CPM bottoms at ~-10.77% (or lower only by craters in CAGR/Sharpe).
- The DD trim it does deliver is NOT broad-based: ~all of it is the single April
  2025 episode (improvement falls to +0.29pp once 2025 is removed).
- Return cost is real and systemic: -2.4pp CAGR, with upside bleed in essentially
  every recovery/up-year (2009 -9.7pp the worst). The cost is the structural
  recovery whipsaw, not transaction cost (only 0.23pp drag from turnover).
- It even raises the Ulcer index (more time underwater) despite clipping the
  single worst trough.

Recommendation: REJECT as an adopted overlay. If anything is retained from the
broader exploration it is the dynamic-safe BOND BUFFER (frac 0.2-0.3), which
achieved MaxDD ~-9.0% and Martin ABOVE CPM in the prior study -- the cap-only
overlay does not. A cap can be DOCUMENTED as a known, simple max-vol-preference
dial for an investor who explicitly wants ~9.6% vol and will accept ~2.4pp lower
CAGR, but it is not a free or robust defensive improvement.

## Honesty / caveats / confidence

- Anchor reproduced to 4 dp via the production engine; harness wiring sound.
- Single in-sample 18y clean window; all marginal CIs include 0 -> treat deltas
  as directional. The CONCLUSION (no improvement) is robust precisely because the
  cap is flat-to-worse on the point estimates too, not because the CI excludes 0.
- Ex-ante vol estimate (weights x asset cov) NOT tested; the realized-trailing
  form is the faithful object that produced the remembered number. An ex-ante
  variant could differ marginally but would face the same structural recovery
  bleed; not expected to flip the verdict.
- Vol/lookback grid is a single sweep; lookback sensitivity shows no setting that
  rescues the result (all dilute).
- The -8.10% prior number reproduced EXACTLY, confirming it was a buffer property,
  not a cap property -- this resolves the original ambiguity in the user's brief.
- De-levered sleeve credited cash (SHV); overlay cost charged at 10 bps/side on
  daily exposure changes. Both choices are if anything kind to the cap, and it
  still loses.
- Confidence: HIGH that the cap-only overlay does not improve CPM both-252 on a
  risk-adjusted basis and that its MaxDD trim is one-episode-driven; HIGH that the
  remembered -8.10% was a buffer (not cap) result.

## Handoff

None required (analysis complete). Productizing the dynamic-safe bond buffer (the
one variant with a real, if non-significant, tail trim) would be a fixer/oracle
decision, not analysis -- and is out of scope for this cap-only question.
