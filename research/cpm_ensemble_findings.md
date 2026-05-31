# CPM Parameter-Ensemble vs Single-Config: Fragility-First Evaluation

Analyst harness (read-only re production/memo). Tests the review's central
recommendation: replace the single point-selected production config (the #1 grid
cell, an overfit-on-peak risk) with a small parameter ensemble that averages the
target weights of several sleeves each month. Judged on FRAGILITY REDUCTION
first (execution/signal-offset stability, turnover/smoothness, K/ranker
selection independence), not Sharpe maximization.

- Harness: `research/cpm_ensemble_findings_harness.py`
- Data/JSON: `research/cpm_ensemble_findings.json`
- Run: `.venv/bin/python research/cpm_ensemble_findings_harness.py`

## Method and conventions

- Engine: the production CPM stack via `cpm_weights_param` (a verbatim
  parametrized mirror of `cpm_live.compute_target_weights`) and a 13612U/vol
  ranker sleeve built on the same stack. Universe, canary (HYG-OR-TIP),
  partial-safe breadth, and SHV/IEF safe selector are held at production for
  every sleeve; only the ranker and K vary.
- Headline metrics (Sharpe, MaxDD, Calmar, Martin, vol, turnover): mooex (T+1
  MOO exact), 10 bps/side, monthly month-end signal. Clean window 2008-05-30 to
  2026-05-22; extended window 1999-03-10 to 2026-05-22 (proxy-informed
  robustness only, per memo).
- Fragility (offset) metrics: cc (exec_lag=0) convention, matching the memo's
  execution-cliff and tranching batteries so the numbers are apples-to-apples.
  - Execution-offset stability: signal fixed at month-end, FILL shifted to
    EOM..EOM+3; Sharpe std across the four (this is the memo's "execution
    offset" metric; production single anchor = 0.0560).
  - Signal-offset stability: the harsher month-end-alignment cliff; the SIGNAL
    calendar itself is shifted EOM..EOM+3 (memo: 1.2063 -> 1.01 -> 0.97 -> 0.91).

### Anchor reproduction (gate)

Single production config (Core A, faber/vol, K=4, rank252/wt504) reproduces the
clean anchor exactly before any analysis:

| Metric | Reproduced | Memo target |
|---|---:|---:|
| Clean Sharpe | 1.1910 | 1.1910 |
| Clean MaxDD | -12.67% | -12.67% |
| Clean Calmar | 1.0615 | 1.0615 |
| Exec-offset std (cc, single) | 0.0560 | 0.0560 |

The standalone Core C (13612U/vol, K=4) extended MaxDD reproduces at -18.86%,
matching the R4 figure cited in the task, confirming the Core C ranker matches
what prior work tested.

## Configurations

- single = Core A only (production).
- full = 0.50 Core A + 0.25 Core B + 0.25 Core C
  - Core A: faber/vol, K=4, rank252/wt504 (= production)
  - Core B: faber/vol, K=5, rank252/wt504
  - Core C: 13612U/vol, K=4, rank252/wt504
- kblend = 0.67 Core A + 0.33 Core B (Faber-only K-blend, NO 13612U Core C)

Weights are averaged per ticker each month, then the blended target is run
through the same mooex/cc accounting.

## Results

### Headline performance (clean = decisive lens)

| Config | Clean Sharpe | Clean MaxDD | Clean Calmar | Clean Martin | Clean vol |
|---|---:|---:|---:|---:|---:|
| single | 1.1910 | -12.67% | 1.0615 | 3.965 | 11.16% |
| full | 1.1762 | -12.26% | 1.0534 | 3.901 | 10.87% |
| kblend | 1.1658 | -12.22% | 1.0427 | 3.788 | 10.84% |

- Sharpe cost vs single: full -0.0148, kblend -0.0252 (both inside the
  acceptable ~0.03-0.08 band, well under it).
- Both ensembles shave volatility (11.16% -> 10.87/10.84%) and IMPROVE clean
  MaxDD (-12.67% -> -12.26/-12.22%). Calmar/Martin slip only marginally.

### Extended window (proxy-informed robustness; 13612U tail check)

| Config | Ext Sharpe | Ext MaxDD | Ext Calmar | Ext Martin |
|---|---:|---:|---:|---:|
| single | 1.2142 | -15.93% | 0.8608 | 3.820 |
| full | 1.2046 | -16.61% | 0.7983 | 3.781 |
| kblend | 1.1991 | -15.84% | 0.8294 | 3.732 |

- The R4 concern is confirmed: Core C deepens the extended tail. Standalone
  Core C ext MaxDD is -18.86%, and the full ensemble inherits part of it
  (-16.61%, 0.68pp deeper than single).
- The Faber-only kblend AVOIDS this: ext MaxDD -15.84% (marginally shallower
  than single) and higher ext Calmar than full (0.829 vs 0.798).

### Fragility metrics

Execution-offset stability (signal fixed at EOM, fill EOM..EOM+3; lower std =
flatter cliff = more robust):

| Config | EOM | EOM+1 | EOM+2 | EOM+3 | std | std vs single |
|---|---:|---:|---:|---:|---:|---:|
| single | 1.2548 | 1.2068 | 1.1519 | 1.1062 | 0.0560 | -- |
| full | 1.2438 | 1.1925 | 1.1436 | 1.1097 | 0.0507 | -9.5% |
| kblend | 1.2363 | 1.1856 | 1.1297 | 1.0889 | 0.0558 | -0.4% |

Signal-offset stability (month-end alignment cliff; signal calendar shifted):

| Config | EOM | EOM+1 | EOM+2 | EOM+3 | std | std vs single |
|---|---:|---:|---:|---:|---:|---:|
| single | 1.2063 | 1.0127 | 0.9747 | 0.9090 | 0.1107 | -- |
| full | 1.1921 | 0.9806 | 1.0065 | 0.9605 | 0.0922 | -16.7% |
| kblend | 1.1852 | 0.9876 | 0.9750 | 0.9361 | 0.0967 | -12.6% |

Turnover (one-way per year; lower = smoother):

| Config | Turnover clean | Turnover ext |
|---|---:|---:|
| single | 2.584 | 2.747 |
| full | 2.525 | 2.702 |
| kblend | 2.558 | 2.705 |

Both ensembles modestly REDUCE turnover (weight-averaging smooths month-to-month
churn), so smoothness improves at no cost.

### K/ranker selection independence

Standalone clean Sharpe of each candidate sleeve an investor might point-select:

| Sleeve | Clean Sharpe | Clean MaxDD | Ext Sharpe | Ext MaxDD |
|---|---:|---:|---:|---:|
| Core A (faber, K4) | 1.1910 | -12.67% | 1.2142 | -15.93% |
| Core B (faber, K5) | 1.0901 | -11.32% | 1.1427 | -15.68% |
| Core C (13612U/vol, K4) | 1.1725 | -12.67% | 1.1859 | -18.86% |

- Standalone sleeve Sharpe dispersion: std 0.0443, range 0.101 (1.090 to 1.191).
- The production single config is the LITERAL MAX of this set (1.1910), i.e. the
  point selection sits on the top of a ~0.10 Sharpe spread. That is exactly the
  top-cell overfit the review flags.
- The full-ensemble clean Sharpe (1.1762) sits NEAR THE TOP of the component
  range and ABOVE the simple mean of sleeve Sharpes (1.1512), a +0.025
  diversification lift from weight-averaging (lower vol). The blend is not just
  averaging edge away.

## Interpretation

1. Both ensembles cost very little Sharpe (full -0.015, kblend -0.025 clean) and
   actually improve clean MaxDD, vol, and turnover. On the decisive clean lens,
   neither is a meaningful give-up.

2. The single config's clearest weakness is SELECTION RISK, not in-sample
   performance: it is the argmax of a ~0.10-Sharpe sleeve spread. Both ensembles
   eliminate the need to pick that top cell, and the full ensemble lands above
   the sleeve mean thanks to diversification. This is the strongest part of the
   review's case and it holds.

3. On the headline EXECUTION-offset fragility metric, the full ensemble flattens
   the cliff modestly (std 0.0560 -> 0.0507, -9.5%) while the Faber-only kblend
   barely moves it (-0.4%). The reason is decorrelation: Core C uses a different
   ranker (13612U/vol) with a different calendar sensitivity, whereas Core A and
   Core B share the Faber ranker and so share the same execution-timing exposure.
   For comparison, the memo's 2-tranche execution scheme cuts this std by -16%
   and 3-tranche by -31%, so ensembling is a weaker execution-cliff mitigant
   than tranching.

4. On the harsher SIGNAL-offset (month-end alignment) cliff, both ensembles help
   more materially (full -16.7%, kblend -12.6% std) and, importantly, cushion the
   worst case: single collapses to 0.909 Sharpe at EOM+3 while full holds 0.961
   and the full grid is flatter/non-monotone (EOM+2 0.9806 -> note it does not
   keep falling). This is a genuine robustness gain.

5. Core C is the swing factor. Including it (full vs kblend) buys better
   execution-offset stability (0.0507 vs 0.0558), better signal-offset stability
   (0.0922 vs 0.0967), and slightly better clean Sharpe/Martin -- but pays a
   deeper EXTENDED tail (ext MaxDD -16.61% vs -15.84%, ext Calmar 0.798 vs
   0.829). That ext-tail cost lives in the proxy-heavy pre-2008 segment, which
   the memo treats as robustness-only, not decisive.

## Key question answered

Does the ensemble materially reduce fragility at an acceptable Sharpe cost?

- Acceptable cost: YES for both (clean -0.015 to -0.025, under the ~0.03 floor;
  plus better clean MaxDD/vol/turnover).
- Material fragility reduction: PARTIAL. Selection-risk elimination is real and
  is the strongest benefit. Signal-offset cliff is cushioned meaningfully
  (-13 to -17% std, higher worst-case Sharpe). Execution-offset cliff is reduced
  only by the FULL ensemble (-9.5%, weaker than tranching) and essentially not at
  all by the Faber-only kblend.

Does Core C justify its ext-tail cost?

- For fragility-first priority on the clean (decisive) lens: YES -- Core C is the
  only component that decorrelates the execution-timing exposure, so it is what
  turns the ensemble from "removes selection risk" into "also flattens the
  execution cliff," and it does so with better clean Sharpe/Martin. Its cost is
  a 0.68pp deeper EXTENDED MaxDD in the proxy window.
- If the extended tail is treated as a hard constraint, the kblend is the safer
  trade (free, shallower ext tail) but it delivers almost no execution-offset
  benefit -- it mainly removes K-selection risk and cushions the signal cliff.

## Verdict

ADOPT-FULL-ENSEMBLE (lean), with the kblend as the conservative fallback.

- The full ensemble is the only variant that delivers the review's full thesis:
  it removes top-cell selection risk, beats the sleeve mean on clean Sharpe,
  improves clean MaxDD/vol/turnover, and is the only mix that flattens BOTH the
  execution-offset (-9.5%) and signal-offset (-16.7%) cliffs. Its price is a
  modest -0.015 clean Sharpe and a 0.68pp deeper EXTENDED (proxy-window) tail.
- Choose the Faber-only kblend instead if and only if the extended-window tail
  is a hard constraint; accept that it then provides essentially no execution-
  offset fragility relief (the headline metric), only selection-risk removal and
  signal-cliff cushioning.
- KEEP-SINGLE is the weakest option for the review's stated objective: it carries
  the full top-cell selection risk and the steepest worst-case offset Sharpe
  (0.909 at signal EOM+3) with only a ~0.015-0.025 Sharpe edge that is itself
  inside selection noise.

Caveat on magnitude: the fragility gains are real but modest; ensembling is a
weaker execution-cliff mitigant than tranching. The honest framing is that the
ensemble's primary value is eliminating point-selection risk at near-zero cost,
with a secondary, modest cliff-flattening benefit driven by the cross-ranker
(Core C) sleeve.

## Caveats and confidence

- Single in-sample evidence: all configs are evaluated on the same 2008-2026
  clean sample, so the relative fragility comparison is in-sample. The direction
  (ensemble reduces selection risk and offset dispersion) is structural and
  should be robust, but the exact magnitudes are not out-of-sample.
- Core C (13612U/vol) is itself a selected ranker (the task's "e.g."); a
  different 13612U variant could shift the ext-tail cost.
- Extended window is proxy-heavy pre-2008; the Core C ext-tail penalty is
  concentrated there and is robustness context, not a decisive-lens result.
- Offset metrics use the cc convention (matching the memo cliff/tranching
  batteries) while headline Sharpe/MaxDD use mooex; this cross-convention split
  is the same one the memo uses and is internally consistent.
- Costs are flat 10 bps/side; the ensemble's slightly lower turnover means its
  realized cost edge would persist or widen under higher cost assumptions.
- Confidence: HIGH on reproduction and on the qualitative ranking
  (full > kblend > single for fragility-first); MEDIUM on the materiality call
  (gains are modest and weaker than tranching); the full-vs-kblend choice hinges
  on how hard a constraint the proxy-window extended tail is.
