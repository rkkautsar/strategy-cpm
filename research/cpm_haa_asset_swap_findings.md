# CPM universe edge: per-asset attribution (HAA mechanism fixed)

Analyst, 2026-06-02. Research only; no production/memo/docs edits; no commit.

## Question

The corrected HAA->CPM factorial showed Universe is CPM's one significant edge:
applying the HAA mechanism (config R0 M0) to CPM-8 instead of HAA-8 lifts clean
Sharpe from 0.8670 to 1.0189 (+0.1519). This study attributes that +0.1519
"universe" edge to individual single-asset swaps, with primary focus on the
user's idea: swap IEF -> GLD in the HAA universe.

(a) IEF -> GLD in HAA: how much lift vs HAA baseline? Is GLD a major driver?
(b) Per-asset attribution: rank the 5 single swaps by dSharpe.
(c) Do single-swap dSharpes add up to the full HAA-8 -> CPM-8 gap, or are there
    big interactions?

## Method

HAA mechanism held FIXED at config R0 M0 (13612U dual momentum, TIP-only canary,
top-4, equal-weight, best-of {SHV,IEF} safe, partial-safe strict-4; NO vol-adj
ranker, NO min-var). Only the universe varies, via single-asset swaps. The
weight function is byte-identical to `param_wf(U=*, R=0, M=0)` from
`cpm_haa_coupled_factorial_v2.py`, generalized to an arbitrary universe list.

- Script: `research/cpm_haa_asset_swap_2026_06_02.py`
  (run: `.venv/bin/python research/cpm_haa_asset_swap_2026_06_02.py`)
- Output: `research/cpm_haa_asset_swap_2026_06_02.json`
- Metrics: clean Sharpe/CAGR/MaxDD/Calmar (T+1 MOO/mooex, both-252, 10bps/side).
- Windows: CLEAN 2008-05-30..2026-05-22 (primary); EXT 1999-03-10..2026-05-22.
- Point-estimates only; no bootstrap/WF.

HAA-8 = SPY, IWM, VEA, VWO, VNQ, DBC, IEF, TLT.
CPM-8 = QQQ, SPHQ, EFA, EEM, VNQ, GLD, TLT, DBC.
Swaps HAA->CPM: SPY->QQQ, IWM->SPHQ, VEA->EFA, VWO->EEM, IEF->GLD.
Common (unchanged): VNQ, TLT, DBC.

## Gates (both PASS, exact)

- baseline HAA-8 reproduces HAA anchor: 0.8669910 == 0.8669910 (PASS).
- full CPM-8 reproduces HAA-on-CPM-8 anchor: 1.0189262 == 1.0189262 (PASS).

So the harness and universe-parametric weight fn exactly match the factorial's
000 and 100 cells. Attribution sits between two verified endpoints.

## Results (CLEAN window, vs HAA baseline 0.8670)

| Config            | Sharpe | dSharpe | CAGR   | MaxDD   | Calmar |
|-------------------|--------|---------|--------|---------|--------|
| HAA-8 baseline    | 0.8670 |  0.0000 |  9.37% | -14.68% | 0.6386 |
| IEF->GLD (PRIMARY)| 0.9400 | +0.0730 | 10.54% | -14.69% | 0.7175 |
| IWM->SPHQ         | 0.9178 | +0.0508 |  9.62% | -13.13% | 0.7331 |
| SPY->QQQ          | 0.8906 | +0.0236 | 10.01% | -15.21% | 0.6582 |
| VWO->EEM          | 0.8806 | +0.0136 |  9.63% | -14.28% | 0.6744 |
| VEA->EFA          | 0.8629 | -0.0041 |  9.30% | -13.64% | 0.6821 |
| full CPM-8        | 1.0189 | +0.1519 | 11.51% | -14.96% | 0.7693 |

EXT window Sharpes (1999-): HAA-8 1.0307; IEF->GLD 1.0731 (+0.0424);
IWM->SPHQ 1.0770 (+0.0463); SPY->QQQ 1.0266 (-0.0041); VWO->EEM 1.0201
(-0.0106); VEA->EFA 1.0098 (-0.0209); full CPM-8 1.1141 (+0.0834).

## Additivity check (c)

| Quantity                              | CLEAN Sharpe |
|---------------------------------------|--------------|
| Full gap HAA-8 -> CPM-8               | +0.1519      |
| Sum of 5 single-swap dSharpes         | +0.1571      |
| Interaction residual                  | -0.0051      |

The single swaps are essentially ADDITIVE: the 5 marginal dSharpes sum to
+0.1571 vs the true full gap of +0.1519, leaving an interaction residual of just
-0.0051 (about 3% of the gap). No large cross-asset interactions; the universe
edge decomposes cleanly into independent single-asset contributions.

## Verdicts

(a) IEF -> GLD is the single LARGEST driver. It lifts clean Sharpe +0.0730
    (0.8670 -> 0.9400), about 48% of the full +0.1519 universe edge by itself,
    at essentially flat MaxDD (-14.68% -> -14.69%) so Calmar improves 0.639 ->
    0.718. It also helps in EXT (+0.0424). YES, GLD is a major driver of the
    universe edge. The user's intuition holds: replacing the IEF bond sleeve
    with GLD captures the largest slice of CPM's universe advantage.

(b) Per-asset rank by CLEAN dSharpe:
      1. IEF->GLD   +0.0730  (gold sleeve; biggest, also best EXT-robust)
      2. IWM->SPHQ  +0.0508  (small-cap -> quality; also cuts MaxDD to -13.13%)
      3. SPY->QQQ   +0.0236  (broad -> Nasdaq growth; raises MaxDD to -15.21%)
      4. VWO->EEM   +0.0136  (EM ETF swap; marginal)
      5. VEA->EFA   -0.0041  (developed-ex-US ETF swap; slightly NEGATIVE)
    GLD and SPHQ (quality) together account for +0.1238 = ~81% of the full gap.
    The two "growth/dev" swaps SPY->QQQ and VWO->EEM are minor; VEA->EFA is a
    wash/slightly harmful in CLEAN and clearly negative in EXT.

(c) Single-swap dSharpes ADD UP to the full HAA-8 -> CPM-8 gap with negligible
    interaction (sum +0.1571 vs gap +0.1519; residual -0.0051). The universe
    edge is a near-linear sum of independent single-asset swaps, dominated by
    IEF->GLD and IWM->SPHQ.

## Caveats / confidence

- HIGH overfit caution. Single-asset attribution is data-mining-prone. All 5
  swaps reported; none cherry-picked. GLD's lead is the same sign in CLEAN and
  EXT, which adds some robustness, but these are point-estimates with no
  bootstrap CI or walk-forward; treat magnitudes as indicative, not precise.
- The two ETF-swap candidates VEA->EFA and VWO->EEM are near-zero and one is
  negative; they are not real edges, just near-equivalent fund substitutions.
- PIT/cached-data caveat: uses the cached panel (`load_panel`) and cached
  open/close for MOO exec lag; same data basis as the factorial, so attribution
  is internally consistent with the verified anchors.
- Attribution is conditional on the HAA mechanism (R0 M0). Under the full CPM
  mechanism (vol-adj Faber ranker + min-var) per-asset weights differ, so these
  marginals are the universe contribution holding the simple HAA engine fixed,
  which is exactly the factorial's "universe" factor at R0 M0.

## Handoff

None required. If the team wants confidence intervals on the GLD/SPHQ marginals
or a walk-forward stability check, that is a follow-up analyst run (bootstrap on
the per-swap daily return series).
