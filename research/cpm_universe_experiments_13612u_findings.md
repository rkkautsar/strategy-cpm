# CPM Universe Add/Swap/Remove Experiments under the 13612U Trend Metric

Analyst, read-only re production. No production files touched. No commit.
Single in-sample evaluation. This is the metric-robustness twin of
`cpm_universe_experiments_findings.md` (the Faber sweep): same universe variants,
same full-CPM stack, with the coupled trend metric flipped Faber -> 13612U.

## Question

Are the Faber-sweep universe conclusions METRIC-ROBUST or Faber-specific?
Holding ALL non-universe CPM machinery fixed but swapping the coupled trend
metric from Faber (10-month SMA) to 13612U, do the same add/swap/remove
verdicts (- GLD is bad, EEM/EFA swaps are washes, + IWM dilutes, + IEF is a
within-noise DD tool, QQQ -> SPY costs) replicate with the same signs and
comparable magnitudes?

## Method

- Engine: `cpm_live` production functions wrapped in `cpm_wf(close, sd, universe,
  trend)` (same wrapper shape as `cpm_faber_vs_13612u_growth.py`). The `trend`
  argument flips BOTH the rank numerator AND the absolute screen metric
  (coupled): rank = `sig_13612U(monthly) / rv_252`; screen = `sig_13612U > 0`.
- Held fixed at full CPM otherwise: TOP_K = 4; inverse-vol weights (cov tail
  252); HYG-or-TIP any-positive 13612U canary; best-of-safe {SHV, IEF} by
  13612U; partial-safe breadth scaling (risky_fraction = n_picks / 4); both-252
  lookbacks.
- Execution: mooex T+1 MOO realistic (prev basket earns overnight close[T] ->
  open[af]; new basket earns intraday open[af] -> close[af], compounded), 10
  bps/side, real cached yfinance opens. Identical to the Faber sweep.
- Windows: CLEAN = 2008-05-30 .. 2026-05-22 (decision lens); EXT = 1999-03-10 ..
  2026-05-22 (proxy-stitched pre-inception tail, lower confidence for swaps).
- Crisis MaxDD: GFC (2007-10..2009-06), COVID (2020-02..2020-04),
  2022 (2022-01..2022-10), 2025-tariff (2025-02..2025-05-22).
- Bootstrap: paired block bootstrap (B = 5000, block = 21 trading days) on the
  marginal (variant - baseline) over CLEAN, triggered on any variant beating the
  baseline on BOTH Sharpe and Calmar; plus a targeted MaxDD-marginal bootstrap on
  the Treasury-in / gold-out variants.
- TOP_K held FIXED at 4 for all variants including 9-asset (+IEF/+IWM) and
  7-asset (- GLD) universes (deliberate held-constant choice, same as Faber sweep).

## Reproduction gates (BOTH PASS)

- Gate 1 (Faber prod anchor): `cpm_wf(CPM, faber)` matches production
  `compute_target_weights` weight-by-weight, 0 mismatch months; CLEAN Sharpe
  1.1658 / MaxDD -12.97% / Calmar 1.0137 reproduced exactly.
- Gate 2 (13612U-CPM baseline): `cpm_wf(CPM, 13612u)` CLEAN reproduces the study
  baseline exactly: Sharpe 1.1540 / MaxDD -13.32% / Calmar 0.9876
  (Martin 3.5434).

## Results under 13612U (CLEAN, decision lens)

Baseline = 13612U-CPM. "vs base" deltas in the side-by-side table below.

| Variant | Sharpe | Calmar | Martin | MaxDD | vs base |
|---|---|---|---|---|---|
| BASE (13612U-CPM) | 1.1540 | 0.9876 | 3.5434 | -13.32% | - |
| 1. +IEF (offensive) | 1.1131 | 0.8661 | 3.3700 | -13.17% | worse (DD ~flat) |
| 2. +IWM (US small) | 1.1045 | 0.8835 | 3.2188 | -14.82% | worse |
| 3. -GLD | 1.0083 | 0.6928 | 2.8356 | -17.16% | clearly worse |
| 4. EEM -> VWO | 1.1421 | 0.9746 | 3.5304 | -13.32% | wash |
| 5. EFA -> VEA | 1.1483 | 0.9691 | 3.4093 | -13.54% | wash |
| 6. QQQ -> SPY | 1.1234 | 0.9115 | 2.9984 | -13.60% | worse |
| 7a. cheap-ETF (VWO+VEA) | 1.1322 | 0.9530 | 3.3583 | -13.54% | slightly worse |
| 7b. HAA-leaning | 0.9754 | 0.7790 | 2.5311 | -12.89% | clearly worse |
| 7c. +IEF -GLD | 1.0090 | 0.7970 | 2.8274 | -12.73% | worse (best DD pt-est) |

EXT window (proxy tail, secondary): baseline Sharpe 1.1808 / Calmar 0.7170 /
MaxDD -18.72%. Cheap-ETF / VWO / VEA swaps actually edge baseline Sharpe up in
EXT (VWO+VEA 1.2075, EEM->VWO 1.1981) but at equal-or-deeper EXT MaxDD; - GLD,
+IEF-GLD, and HAA-leaning show the shallowest EXT MaxDD (-17.16 / -14.50 /
-15.81) at materially lower Sharpe. Same ordering pattern as the Faber EXT.

## Per-crisis MaxDD under 13612U (%)

| Variant | GFC | COVID | 2022 | 2025-tariff |
|---|---|---|---|---|
| BASE (13612U-CPM) | -11.76 | -10.50 | -7.96 | -12.71 |
| 1. +IEF | -13.17 | -8.42 | -7.96 | **-6.67** |
| 2. +IWM | -13.04 | -10.50 | -7.96 | -14.15 |
| 3. -GLD | -13.90 | **-12.17** | -7.96 | **-15.26** |
| 4. EEM->VWO | -11.60 | -11.62 | -7.96 | -12.76 |
| 5. EFA->VEA | -11.76 | -10.50 | -7.96 | -12.33 |
| 6. QQQ->SPY | -13.49 | -8.97 | -7.21 | -12.28 |
| 7a. VWO+VEA | -11.60 | -11.74 | -7.96 | -13.00 |
| 7b. HAA-leaning | -11.78 | -7.11 | -7.21 | -11.41 |
| 7c. +IEF -GLD | -11.27 | -7.00 | -7.96 | **-10.61** |

As in the Faber sweep, Treasury-in variants (+IEF, +IEF-GLD) cut the 2025-tariff
episode sharply (+IEF -6.67% vs base -12.71%) and - GLD deepens COVID and
2025-tariff. New nuance under 13612U: +IEF DEEPENS the GFC drawdown (-13.17 vs
base -11.76) whereas under Faber +IEF helped GFC slightly; the faster 13612U
holds IEF into the GFC equity bounce differently. Minor, episode-specific.

## Selection frequency of added offensive assets (291 risk-on months)

- +IEF: picked top-4 in 128 / 291 risk-on months (44.0%) -- essentially
  identical to Faber (129 / 291). Binds frequently and competes for risky slots.
- +IWM: picked in 104 / 291 (35.7%) -- identical to Faber (103 / 291). Binds
  regularly, worse risk-adjusted than what it displaces.
- +IEF-GLD: IEF picked in 142 / 291 (48.8%) -- matches Faber (143 / 291);
  removing GLD opens a diversifier slot IEF fills.

The added assets bind at nearly the same rate under both metrics, so the
dilution mechanism is metric-agnostic.

## Bootstrap (discipline)

No variant beats the 13612U baseline on BOTH Sharpe and Calmar (CLEAN), so the
Sharpe-and-Calmar marginal bootstrap was not triggered for any variant -- same
outcome as the Faber sweep.

Targeted MaxDD-marginal paired block bootstrap (CLEAN, B = 5000, block = 21),
marginal = variant_dd - base_dd in pp (positive = shallower / better drawdown):

| Variant | DD marginal | 95% CI | p(improve) |
|---|---|---|---|
| 1. +IEF | +1.99 pp | [-2.82, +8.08] pp | 0.783 |
| 7c. +IEF -GLD | +0.32 pp | [-6.24, +6.61] pp | 0.552 |
| 3. -GLD | -2.89 pp | [-9.56, +2.43] pp | 0.154 |

All three CIs straddle 0. The +IEF drawdown improvement is directionally larger
than under Faber (+1.99pp vs +1.08pp) but remains statistically indistinguishable
from noise; the - GLD drawdown deterioration is larger (-2.89pp vs -2.09pp) and
more consistently directional but still within noise. Same qualitative read as
Faber.

## Side-by-side: variant effect under Faber vs under 13612U (CLEAN)

Deltas = variant minus its own baseline (Faber base 1.1658 / 1.0137 / -12.97%;
13612U base 1.1540 / 0.9876 / -13.32%). dMaxDD positive = shallower (better).
Faber numbers from `cpm_universe_experiments_findings.md`.

| Variant | dSharpe Faber | dSharpe 13612U | dCalmar Faber | dCalmar 13612U | dMaxDD Faber | dMaxDD 13612U | Sign match? |
|---|---|---|---|---|---|---|---|
| 1. +IEF | -0.058 | -0.041 | -0.054 | -0.122 | +1.00pp | +0.15pp | YES |
| 2. +IWM | -0.094 | -0.050 | -0.131 | -0.104 | -1.25pp | -1.50pp | YES |
| 3. -GLD | -0.125 | -0.146 | -0.192 | -0.295 | -1.48pp | -3.84pp | YES (bigger 13612U) |
| 4. EEM->VWO | -0.045 | -0.012 | -0.055 | -0.013 | -0.05pp | 0.00pp | YES (wash both) |
| 5. EFA->VEA | -0.006 | -0.006 | -0.077 | -0.019 | -1.06pp | -0.22pp | YES (wash both) |
| 6. QQQ->SPY | -0.044 | -0.031 | -0.110 | -0.076 | -0.71pp | -0.28pp | YES |
| 7a. VWO+VEA | -0.052 | -0.022 | -0.129 | -0.035 | -1.11pp | -0.22pp | YES |
| 7b. HAA-leaning | -0.132 | -0.179 | -0.319 | -0.209 | -2.72pp | +0.43pp | Sharpe/Calmar YES; DD flips |
| 7c. +IEF -GLD | -0.101 | -0.145 | -0.151 | -0.191 | +0.24pp | +0.59pp | YES |

## Answers to the key comparison questions

(a) Is - GLD still WORSE (GLD diversifier robust across metrics)? YES, and MORE
so. Under Faber - GLD costs -0.125 Sharpe / -0.192 Calmar / -1.48pp DD; under
13612U it costs -0.146 Sharpe / -0.295 Calmar / -3.84pp DD. - GLD is the worst
single-change variant under 13612U (only the multi-change HAA-leaning is worse on
Sharpe). The faster 13612U is MORE dependent on the gold diversifier. Conclusion
"do not remove gold" is metric-robust and strengthened.

(b) Are EEM -> VWO / EFA -> VEA still ~WASH (ticker-agnostic robust)? YES, and
even cleaner. Under 13612U: EEM->VWO dSharpe -0.012 / dCalmar -0.013 / dMaxDD
0.00pp; EFA->VEA dSharpe -0.006 / dCalmar -0.019 / dMaxDD -0.22pp. Both are
closer to free than under Faber (where EFA->VEA cost -1.06pp DD). Ticker-agnostic
washes replicate.

(c) Is +IWM still dilutive? YES. Faber -0.094 Sharpe / -0.131 Calmar / -1.25pp
DD; 13612U -0.050 Sharpe / -0.104 Calmar / -1.50pp DD. Dilutive on Sharpe and
Calmar and deepens MaxDD under both metrics. Replicates.

(d) Does +IEF still give a within-noise DD reduction in rate shocks? YES. The
2025-tariff cut is even larger under 13612U (+IEF -6.67% vs base -12.71%; ~6.0pp)
than under Faber (-8.09% vs -12.97%; ~4.9pp), and the full-CLEAN DD-marginal
bootstrap is larger (+1.99pp vs +1.08pp) but still within noise (CI
[-2.82, +8.08], p(improve) 0.783). The "+IEF = within-noise rate-shock DD tool,
not a Sharpe upgrade" verdict replicates. Caveat: +IEF deepens the GFC episode
under 13612U (opposite of Faber there), so the DD benefit is concentrated in the
rate-shock regime, not uniform.

(e) QQQ -> SPY cost under 13612U? Negative but milder than Faber. dSharpe -0.031
(Faber -0.044), dCalmar -0.076 (Faber -0.110), dMaxDD -0.28pp (Faber -0.71pp).
The de-tilt is a net negative under both metrics; the cost shrinks modestly under
the faster metric but does not flip. Replicates.

## Verdict: METRIC-ROBUST

The universe conclusions are metric-robust, not Faber-artifacts. Every variant
keeps the SAME SIGN on Sharpe and Calmar across the two trend metrics (all nine
variants worse-or-wash under both; no flips). The single-change verdicts (- GLD
bad, EEM/EFA swaps washes, +IWM dilutive, +IEF within-noise rate-shock DD tool,
QQQ->SPY mild cost) all hold under 13612U with comparable magnitudes. The only
DIRECTIONAL sign flip anywhere in the matrix is the dMaxDD of the multi-change
7b. HAA-leaning variant (Faber -2.72pp deeper vs 13612U +0.43pp shallower), and
even there Sharpe and Calmar both stay clearly negative -- the universe verdict
(HAA-leaning is clearly worse) is unchanged.

Magnitude notes (do not change any sign):
- The gold dependence is LARGER under 13612U (- GLD penalty roughly doubles on
  Calmar and DD). The faster metric needs the diversifier more -- consistent with
  the prior finding that 13612U whipsaws harder and leans more on the crisis tail.
- The international/EM swaps are CLOSER to free under 13612U (smaller costs).
- The +IEF rate-shock DD benefit is LARGER under 13612U but equally within noise.

Bottom line: the CPM universe findings are properties of the universe + full-CPM
diversifier frame, not of the Faber metric. Swapping to 13612U preserves every
sign and leaves the practical conclusions intact. As before, this remains a
single in-sample point on a high-overfit-risk lever; no variant is an in-sample
upgrade under either metric, so there is no positive signal to carry to OOS. The
+IEF rate-shock drawdown effect is the only candidate worth a regime-conditioned
walk-forward, and only as a risk-management experiment, not a Sharpe upgrade.

## Caveats and confidence

- Single in-sample evaluation; universe changes are high overfit risk. None of
  these point estimates are adoption recommendations.
- mooex T+1 MOO uses real opens where available; pre-ETF-inception months
  (VWO 2005-03, VEA 2007-07, IWM 2000-05) fall back to close-to-close and use
  proxy-stitched closes in EXT, so EXT swap numbers are lower confidence than
  CLEAN.
- 2025-tariff crisis MaxDD window ends at the EVAL_END pin (2026-05-22).
- TOP_K fixed at 4 even for 9-asset universes is a held-constant choice; a
  ceil(N/2) cap would be a different (untested) configuration -- same caveat as
  the Faber sweep, so the two are directly comparable.
- Confidence: HIGH on the metric-robustness verdict (both gates exact; all signs
  match across metrics; mechanism, selection frequency, and bootstrap outcomes
  all align). HIGH that no variant is an in-sample upgrade under either metric.
  MEDIUM that "+IEF helps rate-shock DD" is a real (non-2025-specific) effect --
  point estimate strong and larger than under Faber, bootstrap inconclusive under
  both.

## Artifacts

- Harness: `research/cpm_universe_experiments_13612u.py`
- Data: `research/cpm_universe_experiments_13612u.json`
- Faber comparator: `research/cpm_universe_experiments.py`,
  `research/cpm_universe_experiments_findings.md`
- Run: `.venv/bin/python research/cpm_universe_experiments_13612u.py`
