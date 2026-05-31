# CPM execution-cliff peer sanity: is the month-end cliff generic to monthly TAA?

**Date:** 2026-06-01
**Role:** analyst (read-only; research/ only; no memo/prod edits; no commit)
**Harness:** `research/cpm_execution_cliff_peer_sanity_2026_06_01.py`
**Artifact:** `research/cpm_execution_cliff_peer_sanity_2026_06_01.json`

## Question / hypothesis

The memo flags CPM's month-end **execution cliff** as a potential CPM-specific
crowding/fragility vulnerability: shifting the signal/rebalance calendar off true
month-end degrades CPM Sharpe (EOM ~1.21 -> EOM+1 ~1.01 -> EOM+2 ~0.97 -> EOM+3
~0.91, roughly -25%).

Hypothesis under test: the cliff is a **generic** property of monthly month-end
TAA (turn-of-month exposure shared by the whole class), not a CPM-specific
overfit/crowding defect. Test: run two canonical monthly month-end TAA strategies
through the *identical* offset battery and compare degradation.

## Method

- Reused the memo's cliff convention exactly: `cpm_execution_cliff.gen_sig_dates`
  + close-to-close (cc) accounting, `exec_lag=0`. This is the convention behind
  the published EOM 1.2063 anchor (production T+0 MOC economics: signal at the
  offset day's close, new basket applied from the next trading day's
  close-to-close return). Generalized `cc_returns()` to inject any weight
  function, so all three strategies share byte-identical timing/cost/window.
- **Offset battery:** EOM, EOM+1, EOM+2, EOM+3 business days (rebalance-CALENDAR
  shift, NOT a fill-convention change).
- **Window:** CLEAN 18y, 2008-05-30 .. 2026-05-22. **Costs:** 10 bps/side.
- Strategies:
  - **CPM**: production sleeve (`cpm_live.compute_target_weights`).
  - **AAA-style**: memo's primary external comparator = canonical 10-asset AAA
    (`cpm_benchmarks_proper.make_canonical_aaa_wf`): top-half by 6m momentum,
    SLSQP min-variance weights, no canary. Universe [SPY, EZU, EWJ, EEM, IYR,
    RWX, IEF, TLT, DBC, GLD]; SHV/IEF fallback.
  - **HAA-Simple**: TIP 13612U canary + SPY 13612U trend + best-of-safe{SHV,IEF}
    by 13612U (`sleeve_vs_benchmark_2026_05_30.make_haa_simple_wf`,
    safe_pool=[SHV,IEF]). Same config as the now-BULL sleeve.

Weight builders were inlined verbatim from the cited modules (those modules
import a now-broken harness, `exec_lag_moo_validation` -> removed
`bull_qqq_live._vol_gate_ok`, at load time, so direct import fails).

### Command

```
.venv/bin/python research/cpm_execution_cliff_peer_sanity_2026_06_01.py
```

## Baseline gate (true-EOM, reproduce before cliff)

| Strategy | EOM Sharpe | Note |
|---|---:|---|
| CPM | **1.2063** | reproduces memo cc anchor exactly (gate passed) |
| AAA-style | 0.9961 | own cc/EOM baseline |
| HAA-Simple | 0.9839 | own cc/EOM baseline |

## Side-by-side cliff table (Sharpe by offset, CLEAN 18y)

| Strategy | EOM | EOM+1 | EOM+2 | EOM+3 | abs deg (EOM->+3) | % deg |
|---|---:|---:|---:|---:|---:|---:|
| CPM | 1.2063 | 1.0127 | 0.9747 | 0.9090 | -0.2973 | **-24.6%** |
| AAA-style | 0.9961 | 0.5462 | 0.6675 | 0.6991 | -0.2971 | **-29.8%** |
| HAA-Simple | 0.9839 | 0.7420 | 0.7613 | 0.7215 | -0.2624 | **-26.7%** |

Memo-published CPM reference: EOM 1.2063 / EOM+1 1.01 / EOM+2 0.97 / EOM+3 0.91
(~-25%). Reproduced here within rounding.

## Verdict: GENERIC, not CPM-specific

The month-end execution cliff is a **generic property of monthly month-end TAA**,
shared by both canonical peers. Evidence:

1. **Near-identical absolute Sharpe loss.** EOM->EOM+3 absolute degradation is
   essentially the same for CPM (-0.297) and AAA-style (-0.297), and only
   slightly smaller for HAA-Simple (-0.262). The drop magnitude does not single
   out CPM.
2. **CPM's % degradation is the SMALLEST of the three**, not the steepest. CPM
   -24.6% vs AAA-style -29.8% (steepest) vs HAA-Simple -26.7%. If CPM were
   unusually month-end-dependent, its cliff would be *steeper* than peers; it is
   the shallowest.
3. **Whole-class turn-of-month exposure.** All three lose roughly a quarter to a
   third of EOM Sharpe when the rebalance calendar moves a few days off
   month-end. This is consistent with a shared turn-of-month return component,
   not a CPM-specific crowding artifact.

Nuance (does not change verdict): AAA-style's deepest point is EOM+1 (0.546) with
a partial recovery by EOM+3; CPM degrades closer to monotonically. The shape
differs slightly across strategies, but the magnitude class is the same.

**Implication:** the cliff is reassuring evidence of class membership, not a
CPM-specific overfit/fragility flag. It is still a real live *operational*
risk for the whole class (execution discipline near month-end matters), and worth
documenting as generic rather than as a CPM vulnerability. The memo's tranching
mitigation discussion applies class-wide.

## Caveats / confidence

- **Single in-sample window** (CLEAN 18y, 2008-05-30..2026-05-22), one TAA family
  per peer. Not a forward/OOS claim.
- **Convention is cc / exec_lag=0** (T+0 MOC economics) to match the published
  CPM cliff anchor (EOM 1.2063), NOT literal T+1 MOO. Chosen deliberately for
  apples-to-apples with the memo cliff; the offset *shape* is the object of
  study, and all three strategies use the identical convention.
- AAA-style / HAA-Simple EOM baselines are their *own* cc/EOM values (different
  universe + selector), not the memo headline benchmark numbers (which use the
  mooex headline convention). The comparison is of cliff *degradation*, which is
  convention-controlled here.
- AAA-style clean start is gated by RWX inception (2006-12) + 12m warmup; lands at
  2008-05-30 = the clean-window start, so no extra truncation.
- HAA-Simple safe pool fixed to {SHV, IEF} per task spec (the sleeve_vs_benchmark
  source defaults to {BIL, AGG}; safe pool was overridden).

## Next handoff

None required. If the memo is to be updated to reframe the cliff as generic
(class-wide turn-of-month) rather than a CPM-specific vulnerability, route the
memo edit to the **fixer**.
