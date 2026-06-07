# CPM TAA composite macro stress score experiments

## Provenance

- Persisted: 2026-06-07
- Repo: `/Users/rkautsar/personal/scripts/strategy_cpm`
- Source temp reports:
  - `/tmp/taa_macro_score_vt_experiment.md`
  - `/tmp/taa_macro_score_rebudget_experiment.md`
- Source temp scripts:
  - `/tmp/taa_macro_score_vt_run.py`
  - `/tmp/taa_macro_score_rebudget_run.py`
- Related prior notes:
  - `research/cpm_taa_novel_overlay_experiments.md`
  - `research/cpm_taa_overlay_validation_current_blend.md`
- Process: consolidated verified tmp reports into one durable research note; no experiment reruns.

## Executive verdict

The composite macro stress score is REJECTED for both tested implementations:

- VT amplifier path: composite variants did not beat simpler comparators and were weaker than Sahm-only on risk-adjusted outcome after costs/turnover.
- Sleeve rebudget path: composite variants left binding drawdown unchanged and were dominated by Sahm-only R3-half on practical risk-return tradeoff.
- Sahm-only stress-amp and Sahm-only rebudget remain better than the composite variants in these runs.
- A true 5-signal production-grade version remains data-blocked by HY OAS full-history access issues.

## Data access caveats

- FRED `fredgraph.csv` access was unstable/timeouting in these runs.
- HY OAS `BAMLH0A0HYM2` graph endpoint returned clipped history (about 2023+) even with `cosd`/`coed` parameters.
- Official full-history FRED API path requires API key; without key/licensed alternate source, full HY OAS history remained blocked.
- `pandas_datareader` was not installed in this environment during these runs; even if installed, it likely would not solve HY full-history if backend route still depends on the same FRED graph limitations without proper API/key/licensed source.
- NFCI/claims availability differed by run:
  - VT amplifier run: NFCI and initial claims unavailable.
  - Rebudget run: full NFCI and IC4WSA history fetched and used.

## Full Experiment 1 content (`/tmp/taa_macro_score_vt_experiment.md`)

# Composite Macro Stress-Score VT Amplifier -- Current CPM Blend

Question: does a composite macro stress score (0..N votes) used to amplify the
VT-6040-expand volatility-target overlay add value beyond the existing
plain VT-6040-expand and Sahm-only stress-amp overlays on the current
`0.60*CPM + 0.15*NDX + 0.15*VAL + 0.10*RPV` blend, or does it just add noise/drag?

Pre-registered guardrail (per user refinement): each macro signal is first put
through a Signal quality gate (lag + false-positive audit). Signals that are too
laggy or noisy are excluded/downweighted before any overlay verdict. The composite
result is not allowed to hide bad input quality.

Hardware/conventions match prior TAA work: monthly month-end signals, executed
t+1 MOO, 10 bps on |delta exposure|, de-risk-only (scale in [0,1], residual to SHV
cash). Clean window 2008-05-30+, ext window 1999-03-10+. Overlays are exact
post-processing on the cached canonical baseline blend (blend = linear sum of
sleeve daily returns; reconstruction max abs err = 6.9e-18).


## Baseline

Source: `/tmp/taa_baseline_series.parquet` (canonical blend daily-return series,
mtime current; rebuilt by prior probe from build_artifacts). Reconstruction from
sleeve returns at config weights validates the linear-sum overlay assumption.

| window | Sharpe | CAGR | MaxDD | Calmar | vol |
|---|---|---|---|---|---|
| baseline clean (2008-05-30+) | 1.627 | 17.60% | -9.53% | 1.846 | 10.32% |
| baseline ext (1999-03-10+) | 1.544 | 15.53% | -9.94% | 1.562 | 9.65% |

Comparators reproduced (clean):

| config | Sharpe | CAGR | MaxDD | Calmar | vol | TO/yr | cost bps |
|---|---|---|---|---|---|---|---|
| VT-6040-expand (plain) | 1.626 | 15.47% | -7.22% | 2.143 | 9.13% | 0.130 | 1 |
| Sahm-only stress-amp (tgt -20%) | 1.646 | 14.84% | -6.50% | 2.284 | 8.65% | 0.165 | 2 |

These match prior reports (VT-6040-expand clean MaxDD -7.22%, Sharpe ~1.63;
Sahm-only amp clean MaxDD floor about -6.5%). They are the bars the composite must beat.


## Macro votes

Point-in-time-ish votes, decided at month-end T, executed t+1. No same-day lookahead:
revised series publication-lagged 1m+7d; market series known at close but still
applied t+1.

Data availability in this environment (FRED fredgraph endpoint UNREACHABLE; confirmed
3x timeouts):

| candidate (task) | status | what was used |
|---|---|---|
| HY OAS `BAMLH0A0HYM2` | UNAVAILABLE | FRED down AND fredgraph license-truncates HY OAS to ~3y (documented in repo). Credit vote uses Moody's BAA-AAA IG spread (local cache, low-revision) as a labelled PROXY. |
| NFCI `NFCI` | UNAVAILABLE | FRED down, no local cache. Vote SKIPPED entirely (excluded). |
| initial claims `IC4WSA`/`ICSA` | UNAVAILABLE | FRED down, no local cache. Real/labor lane uses the Sahm rule (UNRATE local) as a labelled PROXY. |
| VIX term `VIXCLS/VXVCLS` | AVAILABLE | yfinance ^VIX/^VIX3M (cached), live 2006-07-17+. |
| curve `T10Y3M` | AVAILABLE | built from local DGS10 - DGS3MO (daily, revision-free), 1981-09+. |

Vote definitions actually evaluated (sparse, defensible):

- credit (HY-OAS proxy): IG BAA-AAA level > 1.5 OR trailing-12m z-score > 1.5.
- sahm (claims/labor proxy): Sahm rule (3m-MA unemployment minus trailing-12m low) >= 0.50.
- vix term: VIX/VIX3M > 1.0 at month-end (sensitivity: 5d avg > 1.0).
- curve re-steepen: prior 24m had T10Y3M < 0 AND current spread re-steepened
  >= 100 bp from its post-inversion trough (sensitivity 50 bp).

Caveat: credit, sahm use REVISED FRED series; vintage correctness is not claimed
(low-revision series, pub-lagged, but not true ALFRED vintages). HY OAS and NFCI
votes are absent, so the composite is effectively a 4-vote score (max realized = 4),
not the 5-vote score the brief envisioned.


## Signal quality gate

Required pre-overlay audit (clean window 2008-05-30+). FP% = fires that are
outside all known stress windows AND not followed by a material drawdown (forward
6-month blend drawdown > -5%). miss = stress windows with no fire in
[start-12m, end] over the 8-window stress set
{GFC, 2010 flash, Euro 2011, 2015-16, 2018Q4, COVID, 2022, 2025}.
CPMovl = share of fire months where the CPM sleeve had ALREADY de-risked
(low overlap = more orthogonal / more incremental action).

| signal | fire% | medDur (mo) | miss | FP% | CPMovl | class | gate |
|---|---|---|---|---|---|---|---|
| credit (IG proxy) | 19.3% | 4 | 1/8 | 26% | 52% | leading* | INCLUDE |
| sahm (labor proxy) | 17.4% | 11 | 2/8 | 5% | 32% | leading* | INCLUDE |
| vix term | 11.0% | 1 | 0/8 | 8% | 62% | leading* | INCLUDE |
| curve re-steepen | 28.0% | 10 | 3/8 | 31% | 26% | leading* | INCLUDE |
| NFCI tight | n/a | n/a | n/a | n/a | n/a | UNAVAIL | exclude (no data) |

Inclusion rule applied: keep if FP% <= 50% AND miss-rate <= 50%. All four available
signals pass and are included.

*Lead/lag caveat: the "leading" label is inflated by the 12-month first-fire
detection window and should not be read literally. The honest per-window timing
(first fire vs stress-window start, + = before) tells the real story:

- vix term: best coverage (0/8 misses) and near-coincident timing
  (2018Q4 -1.0mo, COVID +0.0, 2022 -1.9), BUT whippy (median fire run = 1 month)
  and highest CPM overlap (62%, i.e. it mostly fires when price has already
  de-risked -> low incremental value). Coincident, low orthogonality.
- credit (IG proxy): decent lead in big events (GFC +5.1, 2018Q4 +5.1, COVID +12)
  but lags Euro 2011 (-7.0) and MISSED 2025; 52% CPM overlap. Moderate noise (FP 26%).
- sahm (labor proxy): cleanest (FP 5%) and orthogonal (32% overlap), but lags at
  onset (GFC -6.0mo, COVID -3.9mo) and MISSES mid-cycle corrections (2015-16,
  2018Q4). Strong only in genuine recessions. Lagging at turns.
- curve re-steepen: orthogonal (26% overlap), fires for the deep recessions
  (GFC +1.0, COVID -1.9) but MISSES the non-recession corrections (Euro 2011,
  2015-16, 2018Q4) and is the noisiest (FP 31%, 28% fire rate, 10-month runs).

Signal-inclusion verdict (before any overlay verdict): the two market-lane signals
(vix, credit) are timely but largely REDUNDANT with CPM's own price de-risk
(52-62% overlap); the two real-lane signals (sahm, curve) are orthogonal but LAGGY
and miss mid-cycle stress. None is dominant. This already predicts that blending
them into a single score nets to a wash: orthogonal-but-late + timely-but-redundant.


## Results

Composite stress score = number of active (gate-included) votes, 0..4.
Distribution (clean): score 0 = 50.5%, 1 = 33.5%, 2 = 8.3%, 3 = 5.5%, 4 = 2.3%.
score >= 2 in 35 months; OUTSIDE GFC in 21 of them (2010 flash, 2018Q4, the 2020
COVID cluster, 2022, 2024-10, 2025-03). So unlike Sahm-only it does fire outside
the GFC -- but mostly via the redundant market-lane votes during COVID/2018/2022.

Amplifier variants (clean 2008-05-30+):

| config | Sharpe | CAGR | MaxDD | Calmar | vol | TO/yr | cost bps |
|---|---|---|---|---|---|---|---|
| baseline | 1.627 | 17.60% | -9.53% | 1.846 | 10.32% | - | - |
| VT-6040-expand (plain) | 1.626 | 15.47% | -7.22% | 2.143 | 9.13% | 0.130 | 1 |
| Sahm-only stress-amp | 1.646 | 14.84% | -6.50% | 2.284 | 8.65% | 0.165 | 2 |
| score step-target [gated] | 1.619 | 14.86% | -6.50% | 2.288 | 8.82% | 0.215 | 2 |
| score step-cap [gated] | 1.619 | 14.87% | -6.50% | 2.289 | 8.83% | 0.234 | 2 |
| two-lane confirm [gated] | 1.577 | 13.70% | -6.50% | 2.109 | 8.38% | 0.513 | 5 |

ext (1999-03-10+): every overlay leaves the binding ext MaxDD at -9.94%
(unchanged); the binding ext drawdown sits outside the gated stress months, so no
overlay touches it (consistent with prior reports).

Per-crisis MaxDD (clean):

| crisis | baseline | plain VT | Sahm-only | step-target | step-cap | two-lane |
|---|---|---|---|---|---|---|
| GFC | -7.22% | -7.22% | -6.10% | -6.18% | -5.63% | -3.61% |
| Euro 2011 | -5.19% | -4.89% | -4.89% | -4.89% | -4.89% | -4.89% |
| COVID | -6.13% | -6.13% | -6.13% | -6.13% | -6.13% | -5.21% |
| 2022 bear | -3.18% | -2.17% | -2.17% | -2.17% | -2.17% | -2.17% |
| 2025 tariff | -6.28% | -5.43% | -5.43% | -4.94% | -5.43% | -3.71% |

Path checks (peak-to-trough within episode): 2010 flash -9.49% baseline ->
-6.36% (plain VT / step variants) / -5.10% (Sahm-only); COVID -6.13% ->
-5.21% only under two-lane; 2022 -3.18% -> -2.17% all overlays; 2025 -6.28% ->
-4.94% step-target / -3.28% two-lane.

Paired block bootstrap (clean, B=2000, block=21):

dSharpe:

| config | vs baseline (P>0) | vs plain VT (P>0) | vs Sahm-amp (P>0) |
|---|---|---|---|
| VT-6040-expand | -0.002 (47%) | 0.000 (--) | -0.021 (14%) |
| Sahm-only amp | +0.019 (64%) | +0.021 (86%) | 0.000 (--) |
| score step-target | -0.009 (40%) | -0.007 (34%) | -0.028 (4%) |
| score step-cap | -0.008 (41%) | -0.007 (43%) | -0.027 (16%) |
| two-lane confirm | -0.051 (16%) | -0.049 (12%) | -0.069 (4%) |

dMaxDD vs baseline (+ = shallower):

| config | dMaxDD | CI95 | P(better) |
|---|---|---|---|
| VT-6040-expand | +1.69% | [-0.00,+4.05]% | 97% |
| Sahm-only amp | +2.31% | [+0.08,+5.54]% | 98% |
| score step-target | +1.98% | [+0.04,+4.42]% | 98% |
| score step-cap | +1.96% | [+0.09,+4.32]% | 98% |
| two-lane confirm | +2.24% | [+0.08,+4.85]% | 98% |

Read:

- The composite step variants converge on the SAME clean MaxDD floor (-6.50%) as
  the far simpler Sahm-only amp, with LOWER Sharpe (1.619 vs 1.646) and HIGHER
  turnover (0.215-0.234 vs 0.165).
- dSharpe vs Sahm-amp is negative with P(>0) of just 4-16%: the composite is
  significantly WORSE than Sahm-only on risk-adjusted return. It adds drag, not lift.
- dSharpe vs baseline and vs plain VT is also negative-mean for every composite
  arm: no risk-adjusted improvement over either simpler benchmark.
- The drawdown benefit (dMaxDD +1.96 to +2.24%) is real and robust (P 98%), but it
  is NOT better than what Sahm-only already delivers (+2.31%) or what plain VT
  delivers (+1.69%). The composite buys no extra binding-MaxDD relief.
- two-lane confirmation is the worst trade: best per-crisis tail relief (GFC -3.61%,
  2025 -3.71%, COVID -5.21%) but Sharpe 1.577 and 4x the turnover (0.513, 5 bps/yr
  drag), and dSharpe vs baseline P(>0) only 16%. Tail relief is paid for with
  steady bleed.

Sensitivity (limited): vix 5d-avg lowers fire rate 11.0% -> 9.2% (mild de-whip);
curve re-steepen at 50 bp raises fire rate 28.0% -> 33.9% (noisier, not adopted).


## Verdict

REJECT the composite stress-score VT amplifier as an upgrade.

The composite does NOT add value beyond the existing Sahm-only stress-amp (or plain
VT-6040-expand). It reaches the identical clean MaxDD floor (-6.50%) but with lower
Sharpe and higher turnover, and bootstrap dSharpe vs Sahm-amp is materially negative
(P>0 = 4-16%). The binding ext-window MaxDD is untouched (-9.94%), same as all
overlays. Mechanistically this is exactly what the Signal quality gate predicted:
the two timely votes (vix, credit) are 52-62% redundant with CPM's own price
de-risk, and the two orthogonal votes (sahm, curve) are laggy and miss mid-cycle
stress. Summing them produces a noisier, costlier signal that nets to drag.

The one place the composite (specifically two-lane confirmation) buys extra TAIL
relief -- GFC -3.61%, COVID -5.21%, 2025 -3.71% -- it pays for with the lowest
Sharpe and 4x turnover, and the relief is again GFC/deep-crisis concentrated. Not a
free-lunch tail hedge.

Recommendation:
- Keep the prior best for drawdown hardening: plain VT-6040-expand (parameter-light,
  lowest turnover, +1.69% dMaxDD at P97%).
- Sahm-only stress-amp remains the only macro overlay with both orthogonality and a
  positive (if not significant) Sharpe tilt; keep it a WATCH-item, not an adopt.
- Do NOT adopt the composite score or the two-lane variant: added complexity,
  turnover, and drag for no incremental risk-adjusted or binding-MaxDD benefit.
- If tail-risk hardening becomes the explicit objective (accept Sharpe cost), the
  two-lane confirm variant is the only arm worth revisiting, and only after wiring
  in the genuinely missing inputs (HY OAS full history via a licensed/ALFRED source,
  NFCI, and weekly initial claims), since 3 of the 5 intended votes were unavailable
  here.

Confidence: medium-high on the rejection (robust to the gate and to two amplifier
designs; bootstrap is clear). Medium on generality: 3 of 5 intended macro votes were
unavailable, credit/labor use revised (non-vintage) proxies, and VIX term only
exists from 2006-07, so the composite tested is a degraded 4-vote version. A
full-input rerun could change the two-lane tail-relief picture but is unlikely to
overturn the "no Sharpe lift over Sahm-only" conclusion.


## Reproduction artifacts

- Driver script: `/tmp/taa_macro_score_vt_run.py`
  Run: `cd /Users/rkautsar/personal/scripts/strategy_cpm && .venv/bin/python /tmp/taa_macro_score_vt_run.py`
- Raw console output: `/tmp/taa_macro_score_vt_raw.md`
- This report: `/tmp/taa_macro_score_vt_experiment.md`
- Inputs:
  - `/tmp/taa_baseline_series.parquet` (canonical baseline blend/sleeve daily returns)
  - `/tmp/taa_vix_term_cache.csv` (yfinance ^VIX/^VIX3M, cached; rebuild with the
    yfinance snippet in the driver header if missing)
  - repo local: `data/fred_DGS10.csv`, `data/fred_DGS3MO.csv`, `data/fred_BAA.csv`,
    `data/fred_AAA.csv`, `research/_macro_cache/UNRATE.csv`
- Method deps: `core.perf_metrics`, `cpm_live` (load_panel / compute_target_weights),
  `research.cpm_bootstrap_multimetric.paired_block_bootstrap_mm`.
- Assumptions: 10 bps on |delta exposure|; t+1 MOO; de-risk-only scale in [0,1];
  pub lag 1m+7d on revised series; no same-day lookahead; revised-series vintage
  correctness NOT claimed; HY OAS / NFCI / initial-claims votes ABSENT (documented).

## Full Experiment 2 content (`/tmp/taa_macro_score_rebudget_experiment.md`)

# Experiment: Composite Macro Stress-Score Sleeve Rebudget on the Current 60/15/15/10 CPM Blend

## Provenance

- Date: 2026-06-07. Analyst run. Research/analysis ONLY: NO production files edited,
  NO commit/push, NO strategy-config change. All overlays are post-processing on the
  cached canonical daily sleeve-return series produced by the production engine.
- Repo: `/Users/rkautsar/personal/scripts/strategy_cpm`.
- Predecessor: `/tmp/taa_macro_budget_experiment.md` (Sahm-only / IG-credit sleeve
  rebudget). Landscape/overlay context: `research/cpm_taa_novel_overlay_experiments.md`,
  `research/cpm_taa_overlay_validation_current_blend.md`. Macro-gate menu audit:
  `/tmp/macrogates/findings.md`.
- This run is DISTINCT: it builds a five-source COMPOSITE STRESS SCORE (HY OAS, NFCI,
  initial claims, VIX term structure, yield-curve re-steepening) and tests whether a
  multi-regime score adapts sleeve weights across MORE regimes than the single-source
  Sahm rule, without killing CAGR. Per refinement, every input signal is first put
  through a SIGNAL QUALITY GATE (lag / false-positive audit) before any rebudget test.

## Question / Hypothesis

H: A composite, multi-source macro stress score fires in more crisis regimes than the
Sahm rule and, when used to rebudget the four sleeves toward CPM + RPV (and optional
SHV cash), improves non-GFC crisis drawdown or reduces the Sahm result's single-episode
dependence WITHOUT materially cutting CAGR. Constraints: no ML, no broad parameter
optimization, a-priori transparent thresholds, all signals point-in-time through T,
executed t+1, no same-day lookahead.

Bottom line up front: H is REJECTED. The composite is built mostly from low-quality
inputs (one lagging/sticky proxy, one poor-coverage index, one cried-wolf curve, one
noisy claims series; only VIX has full crisis coverage and it is too fast for a monthly
t+1 cadence to act on). The resulting rebudget leaves the binding MaxDD UNCHANGED
(-9.53% clean, identical to baseline), does not move ANY non-GFC crisis drawdown, costs
~4x the turnover of the Sahm overlay, and is strictly dominated by `Sahm-only` R3-half
on Sharpe / Calmar / MaxDD. The signal-quality gate predicted this before the rebudget
was run.

## Sleeve identities

- CPM (0.60): canary-protected trend/momentum core (the blend's defensive engine).
- NDX (0.15): Nasdaq-100 momentum; aggressive equity beta.
- VAL (0.15): fundamental value + quality equity; equity beta.
- RPV (0.10): multi-asset risk-premia ballast (term / IG / HY / equity premia carry).
- Cash leg (SHV daily return) available in the baseline parquet, so cash sensitivity
  is testable for the deepest defensive maps.

Rebudget cuts NDX + VAL (aggressive equity) and rotates into CPM + RPV (and optionally
SHV), so shed equity risk keeps earning carry in RPV rather than sitting in dead cash.

---

## Baseline (reconstructed from cached sleeve returns, canonical engine)

The blend daily return is an exact linear sum of sleeve daily returns:
`0.60*cpm + 0.15*ndx + 0.15*val + 0.10*rpv` reproduces the stored engine blend to
max abs error 6.94e-18 (floating-point exact). This validates applying a time-varying
weight vector to the cached sleeve returns. Each sleeve's own t+1 MOO / 10 bps
execution is already baked into its daily return; the overlay adds only the
cross-sleeve reallocation cost (10 bps on gross sum|dw| per weight change).

| window | Sharpe | CAGR | MaxDD | Calmar | vol |
|---|---:|---:|---:|---:|---:|
| clean (2008-05-30..2026-06-05) | 1.627 | 17.60% | -9.53% | 1.846 | 10.32% |
| ext (1999-03-10..2026-06-05) | 1.544 | 15.53% | -9.94% | 1.562 | 9.65% |

Baseline per-crisis MaxDD (fixed windows): GFC -7.22%, Euro -5.19%, COVID -6.13%,
2022 -3.18%, 2025 tariff -6.28%; 2010 flash-crash window -8.51%. The binding clean
MaxDD (-9.53%) spans the continuous 2008-2010 stress stretch, OUTSIDE the GFC calendar
window edges (this matters for why the composite fails to move it).

---

## Macro votes (composite stress score)

Five a-priori votes, each in {0,1}, monthly at month-end trading day T, executed t+1.
Composite stress score = sum of votes (0..5). Two lanes for the confirmation variant:
- Market-stress lane: HY OAS stress, NFCI tight, VIX backwardation.
- Real / late-cycle lane: claims deterioration, curve re-steepening.

| vote | definition (a-priori, NOT tuned) | series | lag handling |
|---|---|---|---|
| HY OAS stress | HY proxy 12m-high drawdown <= -5% | HYG stitched (proxy) | daily, same-day observable |
| NFCI tight | NFCI > 0 (tighter than average) | NFCI (FRED) | weekly, lagged 7d (release-safe) |
| claims deterioration | 4wk-MA initial claims >= +10% vs trailing 12m low | IC4WSA (FRED) | weekly, lagged 7d |
| VIX backwardation | VIX / VIX3M >= 1.0 (term structure inverted) | ^VIX, ^VIX3M (yfinance) | daily, same-day observable |
| curve re-steepening | 10y-3m inverted in last 12m AND rising vs 3m ago | DGS10-DGS3MO (FRED) | daily, same-day observable |

Lag conventions (no same-day lookahead): the weight vector chosen at month-end T applies
to every trading day strictly after T (t+1). Daily market series use the last value
dated <= T. Weekly series (NFCI, IC4WSA) require obs-date <= T - 7 days so the value was
released by T. The Sahm comparison arm uses revised UNRATE with a 1-month+7-day
publication lag (identical to the predecessor run).

Data-availability adjustments (documented per scope; "if you adjust due data
availability, document clearly"):

- HY OAS (`BAMLH0A0HYM2`): TRUE FULL HISTORY UNAVAILABLE. The FRED graph CSV endpoint
  serves a CDN-cached 3-year clip (2023-06-06..2026-06-04) regardless of cosd/coed
  params; a cache-busting full-history request 504s under current load (same blocker
  the macro-gate menu hit). SUBSTITUTE: HYG 12m-high drawdown proxy (full history,
  already a repo input). Validation vs actual HY OAS over the 36-month overlap:
  corr(HYG_dd, HY_OAS) = -0.478 -- weak, but the overlap is a low-stress window
  (OAS range 2.68-4.42, no real widening), so the correlation is uninformative by
  construction. The audit below shows the proxy behaves as a sticky / lagging credit
  signal, which is the relevant property for the verdict.
- VIX term structure: VIX3M (`^VIX3M`) starts 2006-07, so the VIX vote contributes 0
  before 2006-07 (the ext window 1999-2006 has at most a 4-vote ceiling). Documented.
- Curve uses DGS10 - DGS3MO constructed from repo data (full history) instead of the
  `T10Y3M` series (which also 504'd); identical economic content.
- NFCI, ICSA/IC4WSA fetched full history from FRED (1971+, 1967+).

Vote coverage (clean window): HY, NFCI, claims, curve all 218/218 months; VIX 218/218
(VIX3M available from 2006-07, before the clean window start).

Composite score distribution (clean, 218 months): score 0 = 56.4%, 1 = 25.2%,
2 = 10.1%, 3 = 5.0%, 4 = 3.2%, 5 = 0.0%. Both-lane confirmed (>=1 market AND >=1 real)
= 27 months.

---

## Signal quality gate (per-vote audit, BEFORE any rebudget)

All votes monthly t+1, no same-day lookahead. Fire / FP / overlap stats over the clean
window (2008-05..2026-06); crisis-timing scanned over full ext history where data
exists. Crisis windows: GFC 2007-10..2009-06 (trough 2009-03), Euro 2011-04..2012-01
(trough 2011-10), COVID 2020-02..2020-06 (trough 2020-03), 2022 cal-yr (trough
2022-10), 2025 tariff cal-yr (trough 2025-04).

### Audit table

| vote | fire% | medDur (mo) | miss/5 crises | FP% | CPM-already-off% | class |
|---|---:|---:|---:|---:|---:|---|
| HY (proxy) | 14.2 | 8 | 1 | 100 | 77 | lagging |
| NFCI | 9.6 | 10 | 3 | 100 | 57 | coincident |
| claims | 20.6 | 1 | 1 | 96 | 31 | coincident |
| VIX | 9.6 | 1 | 0 | 89 | 67 | coincident |
| curve re-steepen | 19.3 | 4 | 2 | 93 | 10 | leading |

- medDur = median consecutive-fire run length. miss/5 = crises with zero fire inside
  the window. CPM-already-off% = share of fire months where the CPM sleeve was already
  de-risked (high = redundant, not orthogonal). class = lead/coincident/lag from mean
  first-fire vs crisis starts.
- FP% = of fire-months OUTSIDE the 5 crisis windows, the share with a NON-negative
  forward-6m blend return (fired but no drawdown materialized). IMPORTANT CAVEAT: the
  blend's forward-6m return is positive ~85% of the time, so FP% is dominated by the
  market base rate and is a WEAK discriminator across signals (every signal looks
  "noisy" on it). The verdict therefore leans on miss-rate, lead/lag, CPM-overlap
  (orthogonality), and persistence -- not FP% alone.

### First-fire timing vs crisis START (months; negative = leads the start)

| vote | GFC | Euro | COVID | 2022 | 2025 |
|---|---:|---:|---:|---:|---:|
| HY | -3 | +5 | +1 | +4 | miss |
| NFCI | -1 | miss | +2 | miss | miss |
| claims | +2 | miss | -1 | +1 | -2 |
| VIX | -3 | +5 | -1 | +1 | -3 |
| curve | -3 | miss | -3 | miss | -3 |

(Trough-relative timing in the raw output; all signals "lead the trough" trivially
because troughs are mid-crisis -- the START-relative table is the meaningful one.)

### Per-signal verdict (inclusion decision)

- VIX backwardation: the ONLY vote with full crisis coverage (0/5 misses), leads or is
  coincident at GFC/COVID/2025. BUT medDur = 1 (single-month spikes) and is too fast for
  a monthly + t+1 cadence to convert into protection (see COVID below); also late for
  Euro (+5). INCLUDE in the market lane, but understand it cannot drive monthly DD
  relief.
- curve re-steepening: genuinely LEADING and the most orthogonal to CPM (only 10% of
  fires while CPM already off, i.e. it adds new information), but cried-wolf: 93% FP,
  misses 2022 and Euro, and produced a clear false positive at 2024-11 (curve un-inverts
  after the 2022-24 inversion + claims + a VIX blip -> score 3 in a continuing bull).
  INCLUDE in the real lane with explicit cried-wolf caveat / downweight.
- claims deterioration: orthogonal-ish (31% CPM overlap) but NOISY (medDur 1), high FP.
  Weak standalone; include in real lane only as confirmation, downweighted.
- HY (proxy): LAGGING, very sticky (medDur 8), 77% redundant with CPM already-off, 100%
  FP outside crises. It mostly just stays on through 2008 and adds little orthogonal
  signal. EXCLUDE / heavily downweight (also a proxy with weak validation).
- NFCI: misses 3 of 5 crises (Euro, 2022, 2025), sticky (medDur 10), 100% FP, 57%
  redundant. Poor coverage. EXCLUDE / heavily downweight.

Pre-rebudget conclusion: only ONE of five inputs (VIX) has clean crisis coverage, and it
is structurally too fast for monthly action; the two "slow" inputs (HY proxy, NFCI) are
lagging/redundant; the leading input (curve) is cried-wolf and misses 2022; claims is
noisy. A composite of mostly-weak inputs is expected to be weak -- which the rebudget
results confirm. This gate is the decisive part of the experiment: the composite result
is not allowed to hide bad input quality.

---

## Rebudget variants

Target weight maps (cpm, ndx, val, rpv, cash; each sums to 1.0):
- mild (score 2): halve NDX/VAL, split freed weight to CPM/RPV -> 67.5 / 7.5 / 7.5 / 17.5 / 0
- R3-half (score 3): 60 / 7.5 / 7.5 / 25 / 0 (the predecessor's best Sahm map)
- equity-cap-7.5 (score 3, variant B): 71.25 / 3.75 / 3.75 / 21.25 / 0 (NDX+VAL capped 7.5%)
- defensive (score >=4): 70 / 0 / 0 / 30 / 0 (fully invested) OR 70 / 0 / 0 / 20 / 10 SHV (cash)

Variants:
- A graduated: score 2 -> mild; 3 -> R3-half; >=4 -> defensive.
- B equity-cap: score 2 -> NDX+VAL cap 15% (= mild); 3 -> cap 7.5%; >=4 -> cap 0.
- C two-lane confirmation: heavy maps (R3-half / defensive) ONLY when both lanes fire;
  single-lane fires are capped at mild regardless of score.
- "+SHV" suffix routes the deepest (score>=4) map into the 10% SHV cash leg.
- Sahm-only R3-half: the predecessor's winner (R3-half map gated on Sahm>=0.50), as the
  direct comparator.

### Results -- clean (2008-05-30..end)

| config | Sharpe | CAGR | MaxDD | Calmar | vol | TO/yr |
|---|---:|---:|---:|---:|---:|---:|
| baseline | 1.627 | 17.60% | -9.53% | 1.846 | 10.32% | 0.000 |
| A graduated | 1.641 | 17.21% | -9.53% | 1.805 | 10.01% | 0.468 |
| A graduated +SHV | 1.634 | 17.02% | -9.53% | 1.786 | 9.95% | 0.497 |
| B equity-cap | 1.637 | 17.20% | -9.53% | 1.805 | 10.03% | 0.448 |
| B equity-cap +SHV | 1.631 | 17.03% | -9.53% | 1.786 | 9.97% | 0.455 |
| C two-lane | 1.641 | 17.21% | -9.53% | 1.805 | 10.01% | 0.468 |
| C two-lane +SHV | 1.634 | 17.02% | -9.53% | 1.786 | 9.95% | 0.497 |
| Sahm-only R3-half | 1.667 | 17.02% | -7.08% | 2.405 | 9.74% | 0.110 |

### Results -- ext (1999-03-10..end)

| config | Sharpe | CAGR | MaxDD | Calmar | vol | TO/yr |
|---|---:|---:|---:|---:|---:|---:|
| baseline | 1.544 | 15.53% | -9.94% | 1.562 | 9.65% | 0.000 |
| A graduated | 1.546 | 15.24% | -9.94% | 1.533 | 9.47% | 0.468 |
| B equity-cap | 1.544 | 15.27% | -9.94% | 1.536 | 9.50% | 0.448 |
| C two-lane | 1.546 | 15.24% | -9.94% | 1.533 | 9.47% | 0.468 |
| Sahm-only R3-half | 1.579 | 15.19% | -9.94% | 1.528 | 9.23% | 0.110 |

### Per-crisis MaxDD

| crisis | baseline | A grad | B cap | C two-lane | Sahm R3-half |
|---|---:|---:|---:|---:|---:|
| GFC 2007-10..2009-06 | -7.2% | -6.9% | -6.8% | -6.9% | -6.7% |
| Euro 2011-04..2012-01 | -5.2% | -5.2% | -5.2% | -5.2% | -5.2% |
| COVID 2020-02..2020-06 | -6.1% | -6.1% | -6.1% | -6.1% | -6.1% |
| 2022 bear | -3.2% | -3.2% | -3.2% | -3.2% | -3.2% |
| 2025 tariff | -6.3% | -6.3% | -6.3% | -6.3% | -6.3% |

Only GFC moves, by a hair, and by LESS than Sahm-only. Every non-GFC crisis is
byte-identical to baseline for every composite variant. The composite's broader vote
coverage does NOT translate into any non-GFC drawdown relief.

### Orthogonality and overlap (clean)

- Composite fire (score>=2): 40 months (18.3%). Overlap with Sahm-only fire: 28 months
  (70% of composite fires). Composite fires while CPM already risk-OFF: 40%; risk-ON
  (orthogonal new action): 60%. Sahm-only fire total: 38 months. So the composite is
  ~70% the same months as Sahm in the clean window, plus extra cried-wolf / fast-shock
  fires that do not help.

### Paired block bootstrap dSharpe vs baseline (clean, B=2000, block=21, seed=42)

| config | dSharpe | CI95 | P(d>0) | dMaxDD |
|---|---:|---:|---:|---:|
| A graduated | +0.0119 | [-0.0462, +0.0748] | 63.9% | +0.36% |
| B equity-cap | +0.0087 | [-0.0531, +0.0713] | 59.8% | +0.31% |
| C two-lane | +0.0119 | [-0.0462, +0.0748] | 63.9% | +0.36% |
| C two-lane +SHV | +0.0058 | [-0.0509, +0.0669] | 55.8% | +0.39% |
| Sahm-only R3-half | +0.0385 | [-0.0248, +0.1079] | 86.7% | +1.13% |

Every composite arm's dSharpe is positive but small, with CIs spanning zero and P(d>0)
~56-64% -- weaker than Sahm-only (P=86.7%) and with a much smaller dMaxDD (+0.3% vs
+1.1%). The composite is inside bootstrap noise AND dominated by the single-signal
overlay it was meant to beat.

### Why the composite fails (mechanism)

- Binding MaxDD untouched (-9.53%): the binding clean drawdown spans 2008-2010. Sahm
  (sticky labor) fires CONTINUOUSLY 2008-05..2010-07 and holds R3-half across the whole
  binding stretch. The composite's score decays in the 2009-2010 recovery (claims/VIX/
  curve turn off), dropping back to mild/baseline weights and leaving the tail of the
  binding drawdown undefended -- so the binding number never improves.
- COVID detected but too late: composite score = 3 at 2020-03-31 and 4 at 2020-04-30
  (it DID fire, unlike Sahm). But the month-end + t+1 cadence executes from April,
  AFTER the 2020-03-23 trough. The fast V-shape is over before the rebudget acts, so
  COVID MaxDD is unchanged. Broader detection without faster cadence buys no protection.
- 2022 / Euro / 2025 unchanged: same fast/atypical-shock blindness as the predecessor;
  the votes either miss (curve misses 2022, NFCI misses Euro/2022/2025) or fire too
  late.
- Cried-wolf cost: 2024-11 hits score 3 (curve un-inversion + claims + a VIX blip) in a
  continuing bull, triggering an unnecessary heavy rebudget -- the exact failure the
  curve signal's audit flagged.
- Turnover: composite churns at 0.45-0.50/yr vs Sahm's 0.11/yr (~4x), because multiple
  noisy votes flip the score in and out. More cost, no benefit.

### Comparison to stress-amplified VT

Not reproducible here: no standalone "VT" (vol-target / stress-amplified) overlay series
or harness exists in the available artifacts (the referenced prior macro work,
`/tmp/macrogates`, is a CPM-external-gate menu, not a VT overlay). The composite vote
definitions were taken from the prompt as instructed. The direct, reproducible
comparator is `Sahm-only` R3-half, shown above; the composite loses to it on every
risk metric.

---

## Key decision

Does the composite stress score improve non-GFC crises or reduce Sahm episode-dependence
without killing CAGR? NO on all three:

- Non-GFC crises: ZERO improvement. Euro, COVID, 2022, 2025 drawdowns are identical to
  baseline for every composite variant.
- Sahm episode-dependence: NOT reduced. The composite is ~70% the same fire months as
  Sahm in the clean window; its only DD movement is GFC (smaller than Sahm's), and it
  fails to defend the binding 2008-2010 stretch that Sahm covers. It trades Sahm's
  single-episode dependence for a mix of redundant + cried-wolf + too-fast signals that
  net to no protection.
- CAGR: slightly LOWER than baseline (17.21% vs 17.60% clean) and similar to Sahm, but
  with 4x the turnover and none of the drawdown relief.

The composite is strictly dominated by `Sahm-only` R3-half (60/7.5/7.5/25): same/lower
CAGR, far worse MaxDD/Calmar, ~4x turnover, weaker bootstrap signal. The signal-quality
gate explains why -- four of the five inputs are low-quality for this purpose, and the
one good input (VIX) is too fast for the monthly t+1 cadence.

---

## Verdict

REJECT the composite stress-score rebudget for this blend, in all tested variants
(A graduated, B equity-cap, C two-lane, +/- SHV cash). It does not clear even the soft
bar the Sahm overlay reached (which itself is only WATCH). Specific dispositions:

- Composite score (5-vote) rebudget: REJECT. No binding-DD relief, no non-GFC crisis
  relief, dominated by Sahm-only R3-half, 4x turnover, dSharpe inside noise.
- Cash (SHV) sensitivity: the +SHV variants are marginally LOWER Sharpe/CAGR than their
  fully-invested twins with no DD benefit (the binding DD is unchanged either way), so
  the cash leg adds nothing here. REJECT.
- Input signals for any future single-signal use: VIX backwardation is the only one with
  clean crisis coverage but needs a faster-than-monthly cadence to be useful; curve
  re-steepening is leading and orthogonal but cried-wolf (needs a recession confirmer);
  HY-proxy and NFCI are lagging/redundant; claims is noisy. None justifies adoption as a
  monthly sleeve-rebudget driver on this blend.
- Standing recommendation unchanged: if any defensive macro overlay is pursued, the
  single-signal `Sahm-only` R3-half remains the best-on-the-tradeoff candidate (WATCH,
  not adopt), gated on vintage UNRATE + walk-forward + a real HY OAS series. Adding more
  macro sources via a naive composite makes it worse, not better.

---

## Caveats and confidence

- HY OAS full history unavailable (FRED CDN clip + 504); HYG drawdown proxy substituted,
  validation weak (quiet overlap). The proxy reads as lagging/sticky; a true HY OAS
  might behave differently, but the composite's failure is driven mainly by cadence and
  by the other inputs, not by the HY proxy alone.
- VIX vote has no data before 2006-07 (ext-window 4-vote ceiling pre-2006); documented.
- FP% is base-rate-dominated (blend forward-6m return positive ~85% of the time) and is
  a weak cross-signal discriminator; the verdict leans on miss-rate, lead/lag, CPM
  overlap, persistence, and the crisis-DD outcome, not FP% alone.
- Macro signals: NFCI/claims/VIX/curve are market- or release-clean; the Sahm comparison
  arm uses REVISED (non-vintage) UNRATE, so the Sahm numbers may be modestly optimistic
  (same limitation as the predecessor). No vintage / ALFRED point-in-time data used; no
  proprietary LEI/PMI used.
- No same-day lookahead: weekly series lagged 7d, monthly UNRATE lagged ~1mo+7d, all
  weights executed t+1. The monthly + t+1 cadence is itself the binding constraint for
  fast shocks (COVID), and is a structural feature of the blend's rebalance, not a bug
  introduced here.
- Point estimates + one paired block bootstrap (B=2000, block=21); NO walk-forward / OOS
  split. In-sample, development-window only.
- Confidence: HIGH that the composite does not beat Sahm-only R3-half and does not
  improve non-GFC crises (the crisis-DD identity and binding-DD non-movement are
  mechanistic, and the signal-quality gate independently predicts it). HIGH that the
  cash leg adds nothing here. MODERATE on the exact per-signal lead/lag labels (sensitive
  to threshold choices), but the qualitative ranking (VIX best coverage / too fast; HY,
  NFCI weak; curve cried-wolf) is robust.

---

## Reproduction artifacts

```bash
cd /Users/rkautsar/personal/scripts/strategy_cpm
# baseline cached daily sleeve series already at /tmp/taa_baseline_series.parquet
# macro cache (fetched this run) at /tmp/taa_macro_score_cache/
.venv/bin/python /tmp/taa_macro_score_rebudget_run.py    # ~2-3 min (CPM risk-state load)
```

- `/tmp/taa_macro_score_rebudget_run.py` -- this experiment (votes + signal-quality gate
  + composite score + rebudget variants + metrics + bootstrap); writes the raw output.
- `/tmp/taa_macro_score_rebudget_raw.md` -- raw run output.
- `/tmp/taa_macro_score_rebudget_experiment.md` -- this report.
- `/tmp/taa_baseline_series.parquet` -- cached canonical baseline daily series
  (blend + cpm/ndx/val/rpv/cash daily returns); reused from the prior analyst run.
- `/tmp/taa_macro_score_cache/` -- macro inputs: `fred_NFCI.csv`, `fred_ICSA.csv`,
  `fred_IC4WSA.csv`, `fred_BAMLH0A0HYM2.csv` (actual HY OAS, 2023+ only),
  `yf_VIX.csv`, `yf_VIX3M.csv`. Curve built from repo `data/fred_DGS10.csv` -
  `data/fred_DGS3MO.csv`; HY proxy from repo `data/hyg_stitched_daily.csv`;
  Sahm from `research/_macro_cache/UNRATE.csv`.
- Repo code reused (read-only): `core.perf_metrics`, `cpm_live.load_panel`,
  `cpm_live.compute_target_weights` (CPM risk-state), `config.py` weights,
  `research.cpm_bootstrap_multimetric.paired_block_bootstrap_mm`.
