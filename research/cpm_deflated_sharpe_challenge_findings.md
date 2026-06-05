# Search-aware Sharpe significance: does the min-var (COHERENT-EW) edge survive Deflated/Probabilistic Sharpe?

Role: analyst (read-only research; no prod/memo/cpm_live edits; no commit).
Lens: Bailey & Lopez de Prado (2014) Probabilistic Sharpe Ratio (PSR) + Deflated Sharpe Ratio (DSR).
Decision frame: CLEAN window, MONTHLY returns. Anchor verified first.

## Question / hypothesis

We have searched dozens of selection/sizing/objective cells. Does the min-var
candidate COHERENT-EW (ewobj min-var selection + EQUAL-WEIGHT sizing) survive a
multiple-testing-corrected Sharpe lens, or could the search manufacture it? Two
sub-questions: (1) is its true Sharpe credibly > 0 and credibly > the do-nothing
no-minvar top-4 baseline (PSR)? (2) Does its Sharpe survive deflation by the
search dispersion at a defensible number of trials N (DSR)?

## Method

- Engine: `research/cpm_harness.py` (mooex T+1 MOO, both-252, 10 bps/side).
  `verify_anchor()` gate PASSED: prod min-var anchor Sharpe 1.2622, MaxDD -0.1135,
  Calmar 1.2196.
- Configs via `research/cpm_minvar_coherence.make_weight_fn` (full-risk-on-drop
  renormalize over kept trio; everything else byte-identical to prod):
  - COHERENT-EW = `make_weight_fn("minvar_ewobj","ew")` (candidate)
  - NO-MINVAR = `make_weight_fn("rank","invvol")` (do-nothing prod top-4, OLD anchor)
  - COHERENT-IV = `make_weight_fn("minvar_ivobj","invvol")` (challenger)
  - NO-MINVAR-EW = `make_weight_fn("rank","ew")` (secondary no-minvar point)
- Streams: `H.run_strategy(..., window="clean")`; compounded to monthly; SR, skew,
  kurtosis, T from the monthly stream.
- PSR(SR0) = Phi( (SRhat - SR0)*sqrt(T-1) / sqrt(1 - skew*SRhat + (kurt-1)/4 * SRhat^2) ),
  all SR in per-MONTH units, kurt = non-excess (Fisher excess + 3).
- DSR: deflation benchmark SR0 = sqrt(Var[{SR_trials}]) * [(1-g)*Z^-1(1-1/N) + g*Z^-1(1-1/(N e))],
  g = Euler-Mascheroni 0.5772; DSR = PSR(SR0).
- Run: `.venv/bin/python -m research.cpm_deflated_sharpe_challenge`
- Artifacts: `research/cpm_deflated_sharpe_challenge.py`,
  `research/cpm_deflated_sharpe_challenge_findings.json`.

## Inputs (transparent)

Frame note: reported "clean Sharpe" headlines (e.g. COHERENT-EW 1.2711) are
DAILY-frame annualized. PSR/DSR use the MONTHLY frame per the decision-lens
instruction; monthly-frame annualized Sharpe runs higher (less daily vol-cluster
penalty). Both are reported; the monthly figures drive PSR/DSR.

| config | daily-frame SR (headline) | monthly-frame SR (ann, used) | T (months) | skew | excess kurt |
|---|---|---|---|---|---|
| COHERENT-EW (candidate) | 1.2711 | 1.4582 | 217 | +0.267 | +0.023 |
| NO-MINVAR (top-4 IV) | 1.1658 | 1.3513 | 217 | +0.143 | -0.097 |
| COHERENT-IV | 1.2501 | 1.4150 | 217 | +0.289 | +0.191 |
| NO-MINVAR-EW (top-4 EW) | 1.1317 | 1.3345 | 217 | +0.129 | -0.219 |

### Trial Sharpe universe for Var[{SR_trials}]

Assembled from this session's selection/sizing/objective studies (CLEAN, net
10 bps, annualized). n = 38 distinct cells; near-duplicates dropped (MINCORR ==
DROP1). Source JSONs: `cpm_minvar_coherence`, `cpm_simple_corr_selection`,
`weighting_consolidated`/`weighting_headtohead`, `cpm_weighting_selection_sensitivity`,
`cardinality_sweep`/`inverse_vol_weighting`, `cpm_poolsize_sweep`, `cpm_2of4_minvar`.

Families spanned:
- sizing: IV (2/3/4-name), EW (1/2/3/4-name), ERC, CONT (continuous min-var)
- selection: rank/top-4, top-3, drop-1, min-corr, min-var, min-vol, max-sharpe,
  max-calmar, min-dd; cardinality 2of4 / 3of4 / 4of5 / 5of6
- objective: ewobj vs ivobj min-var
- lookback: 252 vs 504

Dispersion: **std[{SR}] = 0.0965 ann** (var 9.32e-3 ann; per-month var 7.77e-4).
This is small -- the cells share most of the same return stream (highly
correlated), so the search dispersion is narrow.

### N governance (subjective; reported as sensitivity)

Counting ECONOMICALLY-DISTINCT choices (signal family x horizon x filter x
universe x sizing x selection-rule), not parameter nudges: the bulk of the 38
cells are sizing x selection-rule recombinations of one momentum signal family on
one universe. Defensible point estimate **N ~ 15-20 distinct trials**; reported
across the sensitivity band N in {5, 10, 20, 50}. DSR is reported across that band
and beyond.

## (1) Probabilistic Sharpe Ratio

PSR vs SR0 = 0 (is true SR > 0 credible?) and vs the NO-MINVAR top-4 benchmark
(is the candidate's true SR > the do-nothing SR?). Monthly frame.

| config | PSR vs 0 | z | PSR vs NO-MINVAR | z |
|---|---|---|---|---|
| COHERENT-EW | 1.0000 | 6.26 | **0.677** | 0.46 |
| NO-MINVAR (ref) | 1.0000 | 5.69 | 0.500 | 0.00 |
| COHERENT-IV | 1.0000 | 6.09 | **0.608** | 0.27 |
| NO-MINVAR-EW | 1.0000 | 5.62 | 0.472 | -0.07 |

Reading:
- **Every config's true SR > 0 is overwhelmingly credible** (PSR ~ 1.0, z > 5.6).
- **The min-var edge OVER no-minvar is NOT credible.** COHERENT-EW vs the do-nothing
  top-4: PSR only 0.677 (z 0.46) -- far below any 0.95 bar. COHERENT-IV vs top-4 is
  0.608. Accounting for non-normality + sample length, we cannot distinguish the
  min-var configs' true Sharpe from the no-minvar baseline.

## (2) Deflated Sharpe Ratio (N-sensitivity)

DSR = PSR(SR0_deflated). Deflates the WHOLE strategy Sharpe by the expected
maximum of N searched trials with the observed dispersion.

| N | SR0 deflation (ann) | DSR COHERENT-EW | z | DSR COHERENT-IV | z |
|---|---|---|---|---|---|
| 5 | 0.115 | 1.0000 | 5.76 | 1.0000 | 5.59 |
| 10 | 0.152 | 1.0000 | 5.61 | 1.0000 | 5.43 |
| 20 | 0.184 | 1.0000 | 5.47 | 1.0000 | 5.30 |
| 50 | 0.220 | 1.0000 | 5.31 | 1.0000 | 5.14 |

Robustness beyond the band: DSR stays ~1.0 up to absurd N -- DSR = 1.0000 at
N=1e6 (z 4.24), 0.9999 at N=1e9, 0.9995 at N=1e12. **COHERENT-EW never drops
below DSR 0.95 at any realistic (or unrealistic) N.** The whole-strategy Sharpe
(monthly ann 1.46) sits far above the narrow trial dispersion (std 0.097 ann), so
selection-from-noise cannot manufacture it.

## Answers to the key questions

(a) **PSR.** COHERENT-EW true SR > 0 is credible (PSR ~ 1.0, z 6.26). COHERENT-EW
true SR > the no-minvar top-4 benchmark is NOT credible (PSR 0.677). The strategy
is real; its lead over the do-nothing baseline is not statistically established.

(b) **DSR.** COHERENT-EW survives deflation (DSR > 0.95) at EVERY defensible N --
in fact at all N up to 1e12. It does not stop surviving in any practical range.
The deflation lens decisively confirms the strategy Sharpe is not a search artifact.

(c) **Does the min-var edge over no-minvar survive search-aware deflation, or
could the search explain it?** The DSR/PSR split is the crux:
- The DSR test deflates the WHOLE Sharpe, and that survives massively -- the
  strategy core is real.
- BUT the min-var INCREMENT over no-minvar is only **+0.107 ann** (monthly frame;
  COHERENT-EW 1.4582 - NO-MINVAR 1.3513). The expected-max selection haircut SR0
  is 0.152 ann at N=10 and 0.184 at N=20. **The increment (0.107) is SMALLER than
  the haircut the search could produce at N >= 10.** Consistent with the PSR-vs-
  benchmark of 0.677. **The search CAN plausibly explain the min-var increment
  specifically**, even though it cannot explain the strategy as a whole.

(d) **COHERENT-IV vs COHERENT-EW.** Materially the same conclusion, as expected
from the ~94% trio overlap. COHERENT-IV: DSR ~ 1.0 at all N; PSR vs 0 = 1.0; PSR
vs no-minvar = 0.608 (increment +0.064 ann, even smaller). EW leads IV by ~0.04
ann monthly -- well within noise. The choice between them is immaterial under this
lens.

## Verdict

The min-var COHERENT-EW strategy SURVIVES search-aware deflation overwhelmingly as
a standalone strategy: DSR ~ 1.0 at every defensible N (and beyond), PSR(true SR>0)
~ 1.0. Selection-from-noise does not manufacture a Sharpe of this magnitude given
the narrow trial dispersion.

HOWEVER, the specific EDGE of min-var over the do-nothing no-minvar top-4 baseline
is NOT search-robust: PSR(COHERENT-EW > NO-MINVAR) = 0.677 (z 0.46), and the
observed increment (+0.107 ann) is smaller than the expected-max selection haircut
at N >= 10. The min-var increment is within the band the search could explain.

Net: keep the min-var construction as a defensible, real strategy, but do NOT
claim a statistically established Sharpe edge of min-var over plain top-4 under the
multiple-testing lens. COHERENT-EW vs COHERENT-IV is immaterial.

## Caveats / confidence

- DSR is NECESSARY-not-sufficient. It rejects "pure noise"; it does not certify a
  forward Sharpe. Complementary OOS/walk-forward evidence (done elsewhere) and the
  prior forward-haircut analysis (`cpm_deflated_sharpe_findings.md`: forward central
  ~0.72) remain the relevant forward expectation.
- Frame: monthly (T=217) per the decision-lens instruction. Daily-frame headline
  Sharpes are lower (COHERENT-EW 1.2711 vs monthly 1.4582); the qualitative verdict
  is frame-robust (the prior daily-frame DSR study also gave DSR ~ 1.0).
- Var[{SR_trials}] uses 38 distinct session cells; broader DoF would widen
  dispersion and raise SR0, but the N=1e12 row shows even an enormous haircut leaves
  DSR ~ 1.0 for the whole strategy. The increment-vs-haircut conclusion (question c)
  is the part sensitive to N and is honestly only directional.
- N governance is subjective. Point estimate N ~ 15-20; reported across {5,10,20,50}.
  The whole-strategy DSR verdict is N-insensitive; the min-var-increment verdict
  flips toward "search-explainable" once N >= ~10.
- Confidence: HIGH that COHERENT-EW is a real (non-noise) strategy surviving
  deflation; HIGH that the min-var increment over no-minvar is NOT statistically
  established; the latter aligns across two methods (PSR-vs-benchmark and
  increment-vs-haircut).

## Next handoff

None required. If a forward Sharpe decision is needed, route to oracle with this
DSR/PSR evidence plus the existing forward-haircut analysis.
