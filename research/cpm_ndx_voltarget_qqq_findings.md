# NDX Top-5 Slot Overlay -- External Parent-Index (QQQ) Vol Target

Analyst study. Research only. No prod/voltarget/spec/memo edits, no commit.
Harness: `research/cpm_ndx_voltarget_qqq_harness.py`;
runner: `research/cpm_ndx_voltarget_qqq_run.py`;
raw JSON: `research/cpm_ndx_voltarget_qqq_findings.json`.

Reproduce:

    .venv/bin/python research/cpm_ndx_voltarget_qqq_run.py

## Hypothesis / Question

Does an EXTERNAL parent-index anchor (QQQ trailing RV252) recover the 2021
drawdown protection that ALL self-referential (basket-own) vol targets failed to
deliver, while staying parameter-free?

Mechanism claim: a concentrated top-5 momentum basket has structurally high
own-vol (~40-50%), so any target derived from the basket's own history sits at
~basket-vol -> scale ~1 -> never de-risks (proven failure of ADAPT-RV252 /
MEDIAN / EXPAND). QQQ RV252 (~18-36%) is external + structurally below basket
vol + adaptive/parameter-free -> claimed to have the two proven-required
properties (external + sub-basket-vol).

Forms tested:
- QQQ_LEVEL: target = mult * QQQ_RV252; scale = min(1, target / basket_RV_short).
  Scale the basket DOWN to (mult x) the parent index vol LEVEL. mult dial in
  {1.0, 1.5, 2.0} (a-priori; basket runs ~2x QQQ vol so m>1 should lift the
  target toward the basket's natural vol -> de-risk only when basket vol blows
  out BEYOND the normal premium = conditional, not chronic).
- QQQ_RATIO: scale = min(1, QQQ_RV252 / QQQ_RV_short). De-risk the basket when
  the BROAD MARKET regime is high-vol (pure parameter-free regime signal).

## Method

- Engine identical to prior spec/median studies: monkeypatch
  `compute_ndx_weights`, call UNMODIFIED `ndx_sleeve_live.run_ndx_backtest`
  (gate TIP + SPY-trend + SPY RV20<RV252, safe rotation, T+1 MOO, 10bps/side,
  delisting haircut, PIT membership). Reuses `_basket_vol`, `_index_vol`,
  `_gate_and_candidates`, `_partial_safe_pack`, exposure/turnover/bootstrap/
  walk-forward helpers from the existing harnesses -> references byte-identical.
- Top-5 SLOT discrete drop-lowest-momentum: n_risky = round(scale*5) clipped to
  [0, k_avail]; drop the (5-n) lowest-momentum names to safe; de-risk-only
  cap 1.0; lagged / implementable.
- Basket short window 20d AND 60d. mult in {1.0, 1.5, 2.0}. Single in-sample
  pass; a-priori windows/mults, NOT optimized.

## Inputs / Data Sources

- `data/ndx_constituents/prices.parquet` (basket daily, PIT membership).
- `cpm_panel["QQQ"]` from `data/qqq_stitched_daily.csv`: actual QQQ ETF adjusted
  close 1999-03+, NDX index-level proxy 1985-10..1999-03 (equivalent for
  realized-vol). Trailing 252d / 20d / 60d computed lagged through signal date.
- Clean window 2008-05 .. 2026-05; ext/stress window 1999-+.

CAVEAT: cached frozen dataset; absolute levels may differ marginally from a prod
refresh. Comparisons are apples-to-apples across configs. Pre-1999 QQQ leg is a
stitched index proxy (does not affect the 2008+ clean verdict or the 2021
episode).

## Config Table (clean window 2008-05 .. 2026-05)

key            |  Sh   | Sort |CVaR |MaxDD |CAGR |vol  | TO  |slotEv|meanExp|u2021DD|y2021cum
-------------- |-------|------|-----|------|-----|-----|-----|------|-------|-------|--------
NONE (prod)    | 1.281 |1.962 |8.40 |-.314 |.314 |.236 |5.16 | 0.00 | 1.000 |-.314  | +.337
FIXED t25 w60  | 1.311 |2.019 |8.78 |-.224 |.256 |.188 |4.98 | 1.77 | 0.839 |-.196  | +.292
FIXED t30 w60  | 1.262 |1.922 |8.30 |-.278 |.264 |.202 |5.11 | 1.65 | 0.901 |-.224  | +.248
ADAPT w20      | 1.318 |2.035 |8.74 |-.314 |.315 |.228 |5.22 | 1.42 | 0.965 |-.314  | +.335
ADAPT w60      | 1.302 |1.998 |8.59 |-.314 |.308 |.226 |5.10 | 1.12 | 0.965 |-.314  | +.324
EXPAND w20     | 1.314 |2.014 |8.65 |-.314 |.311 |.226 |5.20 | 0.71 | 0.976 |-.314  | +.335
EXPAND w60     | 1.265 |1.922 |8.25 |-.314 |.293 |.223 |5.13 | 0.53 | 0.971 |-.314  | +.337
QQQL m1.0 w20  | 1.238 |1.901 |8.22 |-.314 |.242 |.190 |4.96 | 3.72 | 0.776 |-.314  | +.200
QQQL m1.0 w60  | 1.280 |1.987 |8.61 |-.261 |.241 |.182 |4.52 | 3.13 | 0.732 |-.261  | +.207
QQQL m1.5 w20  | 1.336 |2.050 |8.82 |-.314 |.305 |.218 |5.24 | 1.95 | 0.934 |-.314  | +.364
QQQL m1.5 w60  | 1.309 |2.007 |8.63 |-.314 |.296 |.217 |5.08 | 1.42 | 0.921 |-.314  | +.335
QQQL m2.0 w20  | 1.280 |1.952 |8.39 |-.314 |.301 |.226 |5.21 | 0.77 | 0.974 |-.314  | +.337
QQQL m2.0 w60  | 1.277 |1.946 |8.35 |-.314 |.302 |.228 |5.16 | 0.59 | 0.980 |-.314  | +.337
QQQR w20       | 1.281 |1.962 |8.40 |-.314 |.314 |.236 |5.16 | 0.00 | 1.000 |-.314  | +.337
QQQR w60       | 1.263 |1.926 |8.26 |-.314 |.304 |.232 |5.13 | 0.89 | 0.978 |-.314  | +.337

u2021DD = drawdown over the 2021-02-12 .. 2021-05-13 unwind (decisive). NONE and
all self-referential (ADAPT/EXPAND) anchors = -.314 (zero protection, baseline).
FIXED-0.25 = -.196 (the target to beat).

## Per-Crisis MaxDD (ext window, gate covers V-crises)

key            | dotcom | GFC  | COVID | 2022 | 2025
-------------- |--------|------|-------|------|------
NONE           | -.121  |-.091 | -.047 |-.003 |-.048
FIXED t25 w60  | -.121  |-.105 | -.047 |-.003 |-.044
QQQL m1.0 w60  | -.121  |-.095 | -.047 |-.003 |-.044
QQQL m1.5 w60  | -.121  |-.091 | -.047 |-.003 |-.037
QQQR w60       | -.121  |-.091 | -.047 |-.003 |-.037

All configs identical at the gated crises (dotcom/GFC/COVID/2022/2025) -- the
gate already covers those V-shaped vol spikes. The differentiator is purely the
NON-gated 2021 growth de-rate.

## (a) Does QQQ-EXT de-risk 2021?  -- LARGELY NO

Only QQQL m=1.0 w60 moved the 2021 unwind DD at all: -.261 vs -.314 (NONE).
Still far short of FIXED-0.25 (-.196). EVERY other QQQ config -- m=1.5, m=2.0
(both windows), and BOTH ratio forms -- gave -.314, i.e. ZERO 2021 protection,
identical to the self-referential failures.

2021 path, QQQL m=1.0 w60 (basket 60d vol vs QQQ RV252 target):

    date        basketRV60  QQQ_RV252  target  scale  n  exp
    2021-01-29    0.468       0.360     0.360   0.769  4  0.80
    2021-02-26    0.404       0.355     0.355   0.880  4  0.80
    2021-03-31    0.438       0.260     0.260   0.592  3  0.60
    2021-04-30    0.436       0.234     0.234   0.537  3  0.60
    2021-05-28    0.406       0.234     0.234   0.577  3  0.60

ROOT CAUSE (same lag pathology as ADAPT, milder because external): the trailing
252d QQQ vol into early 2021 was still CONTAMINATED by the 2020 COVID crash
(QQQ_RV252 ~0.36 in Jan-Feb 2021). basket RV60 ~0.40-0.47 was only marginally
above that -> scale 0.77-0.88 -> n stays 4-5 -> no de-risk during the actual
unwind onset. QQQ_RV252 only drops to ~0.23 by April (after the unwind had
already started), so de-risk arrives LATE. With m=1.5/2.0 the target lifts to
0.39-0.52 >= basket vol -> scale ~1 -> the de-risk never fires at all.

The 2021 unwind was an IDIOSYNCRATIC concentrated-growth de-rate; the broad QQQ
index was calm/declining-vol through it. An external anchor on a TRAILING
parent-index vol cannot see a basket-specific dispersion blowout that does not
show up in the index, and its 252d window carries stale 2020 vol exactly when
the basket needs de-risking. External-but-trailing is not enough; FIXED works
because its target (0.25) is an UNCONDITIONAL, contamination-free constant that
always sits well below basket vol.

## (b) Chronic-drag check -- DECISIVE FAILURE for the only protective config

Conditional vs drag, exposure split (low-vol vs high-vol months):

config         | meanExp | fracDerisk | exp(loVol) | exp(hiVol)
-------------- |---------|------------|------------|-----------
FIXED t25 w60  |  0.839  |   0.606    |   0.967    |   0.589
QQQL m1.0 w60  |  0.732  |   0.899    |   0.781    |   0.638
QQQL m1.5 w60  |  0.921  |   0.349    |   0.958    |   0.849
QQQR w60       |  0.978  |   0.138    |   0.994    |   0.946

FIXED-0.25 is CONDITIONAL: ~0.97 exposure in calm months, drops to ~0.59 in
high-vol months (de-risks 61% of months but stays near-full when calm).

QQQL m=1.0 (the only config with any 2021 protection) is CHRONIC DRAG: it
de-risks 90% of all months, exposure only 0.78 even in CALM low-vol months, and
barely lower (0.64) in high-vol months -- i.e. it runs a near-permanent ~0.73x
position rather than reacting to stress. Consequence: CAGR craters from 0.314
(NONE) / 0.256 (FIXED) to 0.241, and clean Sharpe 1.280 = NO improvement over
prod (1.281) despite the lower vol. The protection it does buy comes from being
permanently small, not from catching the crash.

QQQL m=1.5/2.0 and QQQR fix the drag (near-full calm exposure) but in doing so
stop de-risking 2021 entirely -> back to -.314. There is no mult that is both
conditional AND catches 2021: the dial trades one failure for the other.

## (c) QQQ-EXT vs FIXED-0.25

FIXED-0.25 dominates every QQQ-EXT config:
- DD: FIXED -.196 vs best QQQ (QQQL m1.0 w60) -.261; all other QQQ -.314.
- Sharpe: FIXED 1.311 vs QQQL m1.0 w60 1.280 (worse, = prod).
- CAGR: FIXED 0.256 vs QQQL m1.0 w60 0.241 (worse).
- meanExp: FIXED 0.839 (conditional) vs QQQL m1.0 0.732 (chronic).

QQQL m1.0 w60 also has the WORST turnover signature: slotEv 3.13/yr (vs FIXED
1.77) -- the noisy trailing-QQQ target flips n every other month.

## (d) Level (#4) vs market-regime ratio (#5)

Neither works. QQQ_RATIO (regime form) essentially NEVER de-risks the basket:
QQQR w20 is byte-identical to NONE (meanExp 1.000, slotEv 0.00, -.314); QQQR w60
de-risks 14% of months (meanExp 0.978) and gives zero 2021 protection. Reason:
within ON months the broad-market regime is rarely in a sustained high-vol state
not already captured by the gate -- and 2021 was a LOW broad-market-vol episode,
so the regime signal is structurally blind to it. The level form at least
de-risks (m=1.0) but only via chronic drag. Ratio avoids drag by doing nothing.

## Bootstrap (paired block, B=2000, block=21, seed=42; clean window)

pair                          | dSharpe (p>0) | dMaxDD (p>0)
----------------------------- |---------------|-------------
QQQL m1.0 w60 vs FIXED t25    | -0.029 (0.37) | -0.010 (0.41)
QQQL m1.5 w60 vs FIXED t25    | -0.001 (0.49) | -0.046 (0.14)
QQQL m2.0 w60 vs FIXED t25    | -0.033 (0.31) | -0.061 (0.05)
QQQR  w60     vs FIXED t25    | -0.048 (0.24) | -0.069 (0.03)
QQQL m1.0 w60 vs NONE         | +0.001 (0.52) | +0.059 (0.96)
QQQL m1.5 w60 vs NONE         | +0.030 (0.75) | +0.023 (0.76)
QQQL m1.0 w60 vs ADAPT w60    | -0.021 (0.40) | +0.048 (0.94)
QQQR  w60     vs ADAPT w60    | -0.040 (0.01) | -0.012 (0.19)

- No QQQ config beats FIXED-0.25 on Sharpe (all p<0.5) and all are worse on
  MaxDD (QQQR significantly worse, p=0.03-0.05).
- QQQL m1.0 vs NONE: MaxDD improvement is real (p=0.96) but Sharpe is a coin
  flip (p=0.52) -- the DD gain is fully paid back by drag. Net non-improvement.

## Walk-forward (3 segments, clean window)

Segment 3 (2020-05 .. 2026, contains the 2021 unwind) Sharpe / MaxDD:

config         | seg1 Sh | seg2 Sh | seg3 Sh | seg3 MaxDD
-------------- |---------|---------|---------|----------
NONE           |  1.179  |  1.252  |  1.471  |  -0.314
FIXED t25 w60  |  1.202  |  1.268  |  1.459  |  -0.224
QQQL m1.0 w60  |  1.168  |  1.209  |  1.477  |  -0.261
QQQL m1.5 w60  |  1.179  |  1.298  |  1.495  |  -0.314
QQQR w60       |  1.179  |  1.256  |  1.426  |  -0.314

Only FIXED meaningfully cuts the seg3 (2021-bearing) drawdown without losing
seg1/seg2 Sharpe. QQQL m1.0 cuts DD somewhat but drags seg1/seg2 Sharpe below
prod.

## (e) Recommendation -- HYPOTHESIS REJECTED; keep FIXED-absolute

QQQ-RV252 (level OR ratio) is NOT the parameter-free equal of fixed-absolute.

- It does NOT recover 2021 at acceptable exposure. The single config with any
  2021 protection (QQQL m=1.0 w60, -.261) does so via CHRONIC OVER-DE-RISK
  (meanExp 0.732, de-risks 90% of months incl. calm ones), craters CAGR to 0.241,
  and delivers Sharpe = prod (no edge) -- the exact "permanent ~0.5x drag"
  failure flagged a-priori.
- Lifting the dial (m=1.5/2.0) or switching to the regime-ratio form removes the
  drag but reinstates zero 2021 protection (-.314) -- no setting is both
  conditional and protective.
- ROOT CAUSE: the trailing 252d QQQ vol is (i) contaminated by 2020 exactly when
  the 2021 basket de-rate begins, and (ii) blind to a basket-idiosyncratic
  dispersion blowout that the broad index never registers. External alone is
  insufficient; the winning property is FIXED's UNCONDITIONAL constant target
  that always sits below basket structural vol without any trailing lag.

VERDICT: FIXED-0.25 (w60) remains the pick. It is the only target that is both
conditional (near-full in calm, de-risks in stress) and recovers the 2021 DD
(-.196 vs -.314), with the best Sharpe (1.311) and lowest turnover among
protective configs. Parameter-free adaptivity via a parent-index vol anchor does
NOT survive contact with the 2021 episode.

## Caveats / Confidence

- Single in-sample pass; mults/windows a-priori (not optimized) -> low overfit
  risk, but absolute levels carry the cached-dataset caveat above.
- 2021 is one episode; conclusion rests on it being the decisive non-gated
  co-movement crash (consistent with prior c07cecde/826b3765 framing).
- Bootstrap/walk-forward corroborate the point estimate (no QQQ config beats
  FIXED; QQQL m1.0 ties prod on Sharpe).
- Confidence HIGH that QQQ-RV252 does not match fixed-absolute on this sleeve.

## Next Handoff

None required. If a different external anchor is wanted, the lesson is to avoid
a TRAILING-window estimator (2020-contamination) -- an unconditional constant
(FIXED) already wins; further search risks overfitting a single episode.
