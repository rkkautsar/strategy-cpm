# +IEF OOS / Walk-Forward Robustness vs Production CPM

Analyst, read-only re production. No production/memo files touched. No commit.
Single in-sample stack (no re-fitting). Clean window = decision lens. mooex T+1 MOO,
10 bps/side, both-252 lookbacks.

## Question

Is the +IEF rate-shock drawdown benefit OOS-CONSISTENT across sequential sub-periods
AND does it survive leave-2025-out, or is it EPISODE-CONCENTRATED in the 2025-tariff
drawdown? Prior single-point work found the +IEF drawdown reduction is within noise
(DD-marginal bootstrap p=0.78) and the point benefit looks driven by the 2025-tariff
episode (Faber -8.09% / 13612U -6.67% vs base ~-12.7%); under 13612U +IEF even deepens
the GFC. This study is the walk-forward / OOS-stability read to decide adopt vs document.

+IEF is a FIXED universe addition (IEF added to the offensive/risk pool, full
Faber-CPM stack otherwise) with NO hyperparameter to fit. Therefore "walk-forward"
here means sequential OOS sub-period stability of the +IEF-vs-prod delta, NOT
parameter re-estimation.

## Method

- Harness: `research/cpm_harness.py` (`load_data`, `run_strategy(weight_fn)`,
  `metrics`, `verify_anchor`). Engine = canonical mooex T+1 MOO, 10 bps/side, both-252.
- +IEF construction reuses the EXACT cell from `research/cpm_universe_experiments.py`:
  `cpm_variant_wf(panel, sig_d, CPM_UNIVERSE + ["IEF"])`. Everything except the
  universe held at full CPM (faber/rv rank, faber>0 screen, top-4, inverse-vol cov-252,
  HYG-or-TIP 13612U canary, best-of-safe {SHV,IEF}, partial-safe breadth scaling).
- Prod series = `compute_target_weights` through the same engine.
- Look-ahead control: BOTH series are produced ONCE by the causal engine (each
  month's weights use only data up to the signal date). Folds are pure EVALUATION
  slices of those already-causal series. No re-fit, no peeking, no splicing.
- Folds: 4 equal contiguous calendar windows over clean 2008-05-30 .. 2026-05-22
  (~4.5yr each). Justification: +IEF has nothing to fit, so expanding-window adds no
  information beyond contiguous test-window stability; equal contiguous folds give a
  clean per-era sign read and isolate each major crisis to a fold.
- Leave-2025-out: the 2025-tariff drawdown is the TAIL of the clean window, so
  leave-2025-out = truncate at 2024-12-31 (clean tail truncation, no mid-series
  splice artifacts that would distort compounding/drawdown).
- Bootstrap: paired block bootstrap (B=5000, block=21) on marginals (ief - prod) for
  Sharpe, Calmar, MaxDD; positive MaxDD marginal = +IEF shallower drawdown.

## Gates (PASS)

- Prod anchor (clean both-252): Sharpe 1.1658 / MaxDD -12.97% / Calmar 1.0137. PASS.
- +IEF full-sample reproduction vs prior findings: Sharpe 1.1076 / Calmar 0.9598 /
  MaxDD -11.97% (expected 1.1076 / 0.9598 / -11.97%). EXACT. PASS.
- Full-sample delta (ief - prod): Sharpe -0.058, Calmar -0.054, MaxDD +1.00pp
  (shallower, point estimate). Confirms the prior single-point picture: +IEF is a
  lower-return / lower-risk profile, worse on Sharpe/Calmar, marginally shallower DD.

## Sequential OOS folds (delta = +IEF minus prod)

| Fold | Window | Major crisis | prod Sharpe | ief Sharpe | dSharpe | prod Calmar | ief Calmar | dCalmar | prod MaxDD | ief MaxDD | dMaxDD (pp) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 2008-05-30..2012-12-31 | GFC tail | 0.876 | 0.769 | -0.107 | 1.083 | 0.736 | -0.347 | -10.23% | -11.97% | **-1.74** |
| 2 | 2013-01-02..2017-06-30 | (calm) | 1.338 | 1.227 | -0.111 | 1.253 | 1.137 | -0.116 | -9.60% | -9.24% | +0.36 |
| 3 | 2017-07-03..2021-12-31 | COVID | 1.353 | 1.396 | +0.043 | 1.505 | 1.484 | -0.021 | -10.50% | -10.08% | +0.42 |
| 4 | 2022-01-03..2026-05-22 | 2022 + 2025-tariff | 1.232 | 1.163 | -0.069 | 1.059 | 1.414 | +0.355 | -12.97% | -8.43% | **+4.54** |

Read:

- MaxDD delta sign is NOT consistent: NEGATIVE in F1 (+IEF deepens the GFC-tail DD by
  1.74pp), tiny positive in F2/F3 (+0.36 / +0.42pp, near noise floor), and large
  positive ONLY in F4 (+4.54pp). The entire DD benefit lives in the fold that
  contains 2025-tariff.
- The F4 DD help is purely the 2025-tariff trough: the 2022 crisis DD delta is 0.00pp
  (see crisis table), so within F4 the +4.54pp comes from 2025, not 2022.
- Sharpe delta is NEGATIVE in 3 of 4 folds (only F3 is +0.043). +IEF is not a
  risk-adjusted-return upgrade in any era.
- Calmar delta is negative in 3 of 4 folds; the single positive (F4 +0.355) is again
  the 2025 fold driving denominator (MaxDD) shrinkage.

## Leave-2025-out (truncate at 2024-12-31)

| | Window | Sharpe | Calmar | MaxDD |
|---|---|---|---|---|
| prod | 2008-05-30..2024-12-31 | 1.0532 | 1.0903 | -10.50% |
| +IEF | 2008-05-30..2024-12-31 | 0.9924 | 0.8361 | -11.97% |
| delta | | **-0.0608** | **-0.2542** | **-1.48pp** |

Without 2025 the +IEF drawdown benefit not only VANISHES, it REVERSES: realized MaxDD
is 1.48pp DEEPER than prod (driven by the GFC-tail trough, which +IEF deepens). Sharpe
and Calmar are also clearly worse. The full-sample +1.00pp DD "benefit" is entirely a
2025-tariff artifact; strip 2025 and +IEF is strictly dominated.

## Per-crisis MaxDD

| Crisis | prod | +IEF | delta (pp) | +IEF effect |
|---|---|---|---|---|
| GFC | -10.23% | -11.27% | -1.04 | HURTS (deepens) |
| COVID | -10.50% | -8.42% | +2.08 | helps (within prior noise) |
| 2022 | -8.32% | -8.32% | 0.00 | neutral |
| 2025-tariff | -12.97% | -8.09% | +4.88 | helps (large) |

(GFC delta -1.04pp here is on the clean-window canary path; the -8.09% / -6.67% Faber vs
13612U split and the 13612U GFC-deepening are the prior cross-engine results. Direction
is consistent: +IEF helps 2025 strongly, neutral/mixed elsewhere, hurts the GFC.)

## Bootstrap

Paired block bootstrap (B=5000, block=21), marginal = ief - prod:

| Window | DD marg mean | DD 95% CI | p(DD improve) | Sharpe marg | p(Sharpe improve) |
|---|---|---|---|---|---|
| Full clean | +1.05pp | [-2.93, +5.80] pp | 0.697 | - | - |
| Leave-2025-out | +0.67pp | [-3.24, +5.30] pp | 0.639 | -0.064 | 0.174 |

Both DD CIs straddle 0 (full-clean p(improve)=0.70 reproduces the prior ~p=0.78
"within-noise" read at this block size). Leave-2025-out is even weaker. The
leave-2025-out Sharpe marginal is reliably negative (only 17% of resamples favor
+IEF). Note the bootstrap DD marginal (block-resampled, path-destroying) is mildly
positive even leave-2025-out while the REALIZED leave-2025-out MaxDD delta is -1.48pp;
both agree the DD effect is indistinguishable from noise without 2025, and the realized
path actually favors prod.

## Verdict: REJECT / document-only

+IEF's drawdown benefit is EPISODE-CONCENTRATED, not OOS-consistent. It fails both
stability tests:

1. Fold sign-consistency: MaxDD delta is negative in F1 (GFC), near-zero in F2/F3, and
   large-positive only in F4 (the 2025-tariff fold). Sharpe delta is negative in 3/4
   folds. No across-fold consistency.
2. Leave-2025-out: the DD benefit reverses to -1.48pp (deeper than prod), and
   Sharpe/Calmar degrade. Strip the single 2025 episode and +IEF is dominated.
3. Bootstrap: within noise full-sample (p~0.70) and weaker leave-2025-out (p~0.64),
   with a reliably negative Sharpe marginal.

This matches the pre-stated most-likely outcome (p=0.78 + episode concentration ->
reject). DO NOT adopt +IEF as a production change. It is a single-episode (2025-tariff)
drawdown coincidence carrying a real and consistent Sharpe/Calmar cost, and it deepens
the GFC. Document it as a rejected rate-shock-DD experiment: the apparent benefit does
not generalize out of the 2025 window.

If rate-shock drawdown protection remains a priority, the right next step is a
regime-CONDITIONED tool (explicitly switch on a rate-shock signal) evaluated on
multiple independent rate-shock episodes -- NOT a permanent IEF universe add, which
pays a standing Sharpe tax for a benefit that only appeared once.

## Caveats and confidence

- Single in-sample stack; +IEF has no fitted hyperparameter, so fold instability is a
  true OOS-generalization failure, not a fitting artifact.
- Folds are evaluation slices of one causal series; no look-ahead. Equal contiguous
  windows chosen so each major crisis lands in a distinct fold; alternate fold edges
  would not rescue a benefit that reverses under leave-2025-out.
- 2025-tariff MaxDD window ends at the EVAL_END pin (2026-05-22); it is the binding
  clean drawdown for prod, which is exactly why removing it flips the verdict.
- Block bootstrap on MaxDD marginals is path-destroying (distributional, not realized
  worst-path); used only as a noise check alongside the realized fold/leave-out deltas.
- Confidence: HIGH that +IEF is NOT OOS-consistent (gate exact, benefit concentrated in
  one fold, reverses leave-2025-out, Sharpe negative in 3/4 folds). HIGH on REJECT.

## Artifacts

- Harness/script: `research/cpm_ief_walkforward.py`
- Data: `research/cpm_ief_walkforward.json`
- Run: `.venv/bin/python research/cpm_ief_walkforward.py`
