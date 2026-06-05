# CPM mechanism on the 2-swap (GLD+SPHQ) universe -- recovery vs full CPM

ANALYST run, 2026-06-02. Research only; no prod/memo/docs touched; no commit.

Script: `research/cpm_mech_2swap_univ_2026_06_02.py`
Output: `research/cpm_mech_2swap_univ_2026_06_02.json`

## Question

Run the FULL CPM mechanism (R=1 vol-adjusted Faber ranker + raw-Faber screen;
M=1 min-var 3-of-4 selection at n_pos=4; TIP-only canary, top-4, equal-weight,
best-of {SHV,IEF} safe, strict-4 breadth) on the HAA universe with ONLY the two
best swaps applied (IEF->GLD, IWM->SPHQ). How much of full CPM (CLEAN Sharpe
1.2557) does the partially-upgraded universe + CPM mechanism recover, and do the
remaining swaps (SPY->QQQ, VEA->EFA, VWO->EEM) still add materially?

Universe under test (2-swap) = SPY, SPHQ, VEA, VWO, VNQ, DBC, GLD, TLT.

## Method

- Mechanism held FIXED at CPM (R=1, M=1). Only the universe varies.
- Weight function `cpm_mech_wf` is the universe-parametric generalization of
  `param_wf(U,R,M)` in `research/cpm_haa_coupled_factorial_v2.py` with R=1,M=1
  hardwired and the universe passed explicitly (same cpm_live primitives:
  `faber_sma_xs`, `_min_var_subset`, `best_safe`, `sig_13612U`).
- Execution: mooex / T+1 MOO, both-252, 10 bps/side, CLEAN window
  2008-05-30..2026-05-22, EXT window 1999-03-10..2026-05-22.
- Point-estimates only (bootstrap skipped per scope).

## Gates (reproduced first)

| Config (U,R,M)        | Target  | Actual    | Pass |
|-----------------------|---------|-----------|------|
| CPM mech on HAA-8 (011)| 0.9399 | 0.939900  | yes  |
| Full CPM-8 (111)       | 1.255673| 1.255673  | yes  |

Both anchors reproduced exactly -> mechanism + universe wiring is correct.

## Results -- full metrics (CLEAN, 2008-05-30..2026-05-22)

| Config        | Sharpe | Sortino | CVaR95 | Calmar | Martin | MaxDD%  | CAGR%  | Vol%  | Turn |
|---------------|--------|---------|--------|--------|--------|---------|--------|-------|------|
| CPM mech HAA-8| 0.9399 | 1.3424  | 6.0349 | 0.5507 | 2.4281 | -16.80  | 9.25   | 10.00 | 6.86 |
| CPM mech 2swap| 1.2000 | 1.7294  | 7.8508 | 0.9421 | 3.5327 | -13.03  | 12.28  | 10.10 | 7.38 |
| Full CPM-8    | 1.2557 | 1.8058  | 8.2295 | 1.0076 | 4.2571 | -13.03  | 13.13  | 10.28 | 7.08 |

EXT (1999-03-10..2026-05-22):

| Config        | Sharpe | Sortino | CVaR95 | Calmar | Martin | MaxDD%  | CAGR%  | Vol%  | Turn |
|---------------|--------|---------|--------|--------|--------|---------|--------|-------|------|
| CPM mech HAA-8| 1.0555 | 1.5170  | 6.8804 | 0.5913 | 2.7872 | -16.80  | 9.94   | 9.39  | 6.50 |
| CPM mech 2swap| 1.2338 | 1.7804  | 8.0984 | 0.8636 | 3.6450 | -14.14  | 12.21  | 9.72  | 7.09 |
| Full CPM-8    | 1.2549 | 1.8114  | 8.2770 | 0.9712 | 3.6450*| -13.14  | 12.76  | 9.97  | 6.80 |

(*EXT full-CPM Martin = 4.1168.)

## Anchor ladder (CLEAN Sharpe)

| Step                                            | Sharpe | vs HAA baseline |
|-------------------------------------------------|--------|-----------------|
| HAA baseline (HAA-8, HAA mech)                  | 0.8670 | --              |
| CPM mech on HAA-8 (config 011)                  | 0.9399 | +0.073          |
| HAA mech + GLD+SPHQ (2-swap, HAA mech)          | 1.028  | +0.161          |
| **CPM mech + 2-swap univ (THIS RUN)**           | **1.2000** | **+0.333**  |
| Full CPM (CPM-8, CPM mech, config 111)          | 1.2557 | +0.389          |

## Answers

### (a) CPM mech + 2-swap Sharpe, and closeness to full CPM 1.2557

- CLEAN Sharpe = **1.2000**; EXT Sharpe = **1.2338**.
- Gap to full CPM = only **0.0557** (CLEAN) / **0.0211** (EXT).
- 2-swap recovers **85.7%** of the full-CPM-vs-HAA-baseline gap
  (0.8670 -> 1.2557 = +0.3887; 2-swap lift +0.3330).
- Of the CPM-mechanism universe edge alone (0.9399 -> 1.2557 = +0.3158), the
  2-swap captures **82.4%** (+0.2601 of +0.3158).

### (b) Do the remaining swaps (SPY->QQQ, VEA->EFA, VWO->EEM) still add?

Marginally. Going 2-swap -> full CPM-8 adds only **+0.0557 Sharpe** (CLEAN) and
**+0.0211** (EXT). Secondary metrics improve a bit (Calmar 0.9421 -> 1.0076,
Martin 3.53 -> 4.26, CAGR 12.28% -> 13.13%) at slightly higher vol
(10.10% -> 10.28%) and lower turnover (7.38 -> 7.08); MaxDD is identical
(-13.03%). The QQQ/EFA/EEM block is NOT where the universe edge lives -- GLD+SPHQ
carry the overwhelming majority of it.

### (c) Does the CPM mechanism amplify the 2-swap universe more than the HAA mechanism did?

Yes, strongly. Same 2-swap universe:
- HAA mechanism: 1.028
- CPM mechanism: **1.2000**  (+0.172)

The vol-adjusted Faber ranker + min-var 3-of-4 selection extract materially more
from the GLD+SPHQ universe than the 13612U dual-momentum / hold-all-4 HAA
mechanism. Note universe and mechanism interact constructively: under HAA mech
the 2-swap lift over HAA-8 is +0.161, but the CPM mechanism turns the same
universe upgrade into a larger absolute level.

## Verdict

The combination "GLD+SPHQ universe upgrade + CPM mechanism" recovers ~86% of the
full-CPM-over-HAA edge and lands within 0.056 Sharpe of full CPM-8. The bulk of
CPM's advantage is (1) the GLD+SPHQ universe swaps and (2) the CPM mechanism's
amplification of that universe -- NOT the equity/intl swaps (QQQ/EFA/EEM), which
add only ~+0.056. Keeping SPY/VEA/VWO instead of QQQ/EFA/EEM costs little.

## Caveats / confidence

- HIGH overfit/selection caution: GLD and SPHQ were SELECTED as the top-2 single
  drivers in a prior in-sample attribution, so the in-sample 2-swap lift is
  selection-biased upward. The honest robustness test (paired block bootstrap)
  was run for the HAA-mech 2-swap in `cpm_haa_gld_sphq_run.py`; not re-run here
  (point-estimate scope). Treat the +0.056 "remaining swaps add nothing" claim
  as a single-window point estimate.
- Single in-sample window; PIT / cached-data; no walk-forward.
- Both gates reproduce exactly, so the mechanism/universe plumbing is trusted.
- Confidence: HIGH on the point estimates and gate reproduction; MEDIUM on
  generalization given the selection bias on GLD+SPHQ.

## Next handoff

None required. If decision-grade significance is wanted on "remaining swaps add
nothing under CPM mech", hand to analyst again for a paired block bootstrap of
(full CPM-8 minus CPM-mech-2swap) on the same return path.
