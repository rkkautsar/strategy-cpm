# NDX sleeve: discrete slot-replacement vs continuous vol-target dial -- findings

Analyst role. Read-only re production (`ndx_sleeve_live.py` / prod / memo NOT
edited; no commit). Harness: `research/cpm_ndx_slotreplace_harness.py`. Run:
`research/cpm_ndx_slotreplace_run.py`. Raw: `research/cpm_ndx_slotreplace_findings.json`.

## Question

The incumbent best DD tool on the NDX sleeve is the CONTINUOUS monthly basket-vol
de-risk dial (shrink all 5 names uniformly, freed weight to safe). User idea:
instead of shrinking uniformly, DROP THE WEAKEST-RANKED SLOTS to safe -- discrete
slot-replacement. n_risky = round(scale*5), scale = min(1, target_vol/realized_vol)
is the IDENTICAL monthly basket-vol signal the continuous dial uses; keep the
top-n names equal-weight, each at 1/5 = 20% of book; remaining (5-n)*20% to safe.

At MATCHED average equity exposure the only difference vs the continuous dial is
CONCENTRATION: slot-replacement keeps full conviction in the strongest names and
sheds the marginal ones; the continuous dial holds all 5 smaller. Questions:
(a) does concentration-under-stress beat the dial on Sharpe/DD/tail (bootstrap)?
(b) 2021 unwind: does dropping the weakest slots cut the unwind more than uniform
shrink, or do the top names crash just as hard (co-movement)?
(c) turnover/whipsaw cost of the coarse 20% granularity + rounding fragility?
(d) net: better DD dial, equal, or worse than the continuous dial -- any alpha?

ADDITIONAL drop-rule test: slot-replacement must pick WHICH name to send to safe.
Two ranking rules at the SAME n_risky:
- R1 (MOM): drop the LOWEST-momentum-ranked name first (marginal selection slot)
  -- the original user design.
- R2 (VOL): drop the HIGHEST-trailing-vol name first (lagged, same vol window) --
  coherent with the vol-target OBJECTIVE, sheds the biggest variance contributor.
Hypothesis: R2 cuts more basket vol per slot dropped (vol-coherent) OR sheds
high-vol names that were actually top performers (high vol != bad). Measured.

## Method

- Engine IDENTICAL to `research/cpm_ndx_voltarget.py`: monkeypatch
  `compute_ndx_weights`, call UNMODIFIED `run_ndx_backtest` (gate TIP+SPY-trend
  +SPY-RV, safe rotation, T+1 MOO, 10bps/side, delisting haircut, PIT membership
  all identical). The SAME basket-vol scale (target 0.30, 60d trailing daily vol
  lagged through the month-end signal date, de-risk-only cap 1.0) drives BOTH the
  continuous dial (CONT) and every slot variant, so average equity exposure is
  ~matched and the contrast isolates concentration vs shrink-all.
- CONT = `cpm_ndx_voltarget.py` DERISK config (the incumbent). SLOT_* discretize
  the same scale: n = {round, floor, ceil}(scale*5), capped at names available.
- Implementable: lagged scale signal from prior-month realized vol, T+1 MOO,
  10bps on changes, PIT/delisting integrity inherited unchanged.
- Bootstrap: paired block bootstrap B=2000 block=21 seed=42, each variant vs PROD
  AND vs CONT, plus R2 vs R1 at matched mapping. Walk-forward 3-seg clean.
- Windows: clean (2008-05-30+, DECISION), stress/ext (1999-03-10+, confirm),
  per-crisis incl 2021 growth unwind (2021-02-12..2021-05-13) and COVID-V.

## Results (clean 2008+; gate/safe/T+1/10bps/delist/PIT fixed; basket-vol 60d t0.30)

| config         | Sharpe | Sortino | CVaR | MaxDD  | CAGR  | vol   | turnover | meanExp | keptRV | slot/yr |
|----------------|--------|---------|------|--------|-------|-------|----------|---------|--------|---------|
| PROD           | 1.281  | 1.962   | 8.40 | -31.4% | 31.4% | 23.6% | 5.16     | --      | --     | 0.0     |
| CONT (dial)    | 1.263  | 1.913   | 8.23 | -26.6% | 25.6% | 19.6% | 5.19     | 0.898   | --     | --      |
| SLOT_ROUND R1  | 1.262  | 1.922   | 8.30 | -27.8% | 26.4% | 20.2% | 5.12     | 0.901   | 0.328  | 1.65    |
| SLOT_FLOOR R1  | 1.274  | 1.949   | 8.45 | -26.2% | 25.1% | 19.0% | 5.05     | 0.857   | 0.338  | 1.60    |
| SLOT_CEIL  R1  | 1.295  | 1.983   | 8.52 | -29.6% | 28.5% | 21.1% | 5.12     | 0.934   | 0.320  | 0.89    |
| SLOT_ROUND_VOL R2 | 1.188 | 1.804 | 7.75 | -27.0% | 24.3% | 20.0% | 5.33     | 0.901   | 0.306  | 1.65    |
| SLOT_FLOOR_VOL R2 | 1.189 | 1.808 | 7.82 | -25.3% | 22.8% | 18.8% | 5.24     | 0.857   | 0.305  | 1.60    |
| SLOT_CEIL_VOL  R2 | 1.238 | 1.887 | 8.10 | -29.6% | 26.6% | 20.8% | 5.27     | 0.934   | 0.308  | 0.89    |

PROD reproduces the anchor (clean Sharpe 1.281, MaxDD -31.4%). CONT meanExp 0.898
and SLOT_ROUND meanExp 0.901 are MATCHED -- the clean concentration contrast.
keptRV = mean realized vol of the kept (held) basket: R2 sheds vol (0.306 vs R1
0.328 at the same exposure) = vol-coherent. The R1 vs R2 Sharpe gap is the cost.

## Paired block bootstrap (clean; B=2000, block=21, seed=42)

dMaxDD positive = DD reduced. dSharpe/dSortino/dCVaR positive = risk-adj improved.
Format: mean (p>0). dMaxDD CI is path-dependent (soft); dSharpe/dSortino/dCVaR are
the order-invariant classification metrics.

vs PROD:

| config            | dSharpe        | dSortino       | dCVaR          | dMaxDD             |
|-------------------|----------------|----------------|----------------|--------------------|
| CONT (dial)       | -0.016 (0.38)  | -0.048 (0.31)  | -0.162 (0.35)  | +0.049 (0.97)*     |
| SLOT_ROUND R1     | -0.017 (0.41)  | -0.037 (0.39)  | -0.090 (0.45)  | +0.039 (0.91)      |
| SLOT_FLOOR R1     | -0.006 (0.47)  | -0.012 (0.47)  | +0.054 (0.55)  | +0.053 (0.94)      |
| SLOT_CEIL  R1     | +0.016 (0.66)  | +0.024 (0.62)  | +0.135 (0.66)  | +0.024 (0.83)      |
| SLOT_ROUND_VOL R2 | -0.092 (0.12)  | -0.159 (0.14)  | -0.652 (0.15)  | +0.040 (0.91)      |
| SLOT_FLOOR_VOL R2 | -0.091 (0.16)  | -0.152 (0.18)  | -0.568 (0.21)  | +0.054 (0.93)      |
| SLOT_CEIL_VOL  R2 | -0.042 (0.25)  | -0.074 (0.26)  | -0.300 (0.26)  | +0.027 (0.83)      |

vs CONT (the KEY test -- matched-exposure concentration effect):

| config            | dSharpe        | dSortino       | dCVaR          | dMaxDD             |
|-------------------|----------------|----------------|----------------|--------------------|
| SLOT_ROUND R1     | -0.001 (0.51)  | +0.010 (0.56)  | +0.072 (0.60)  | -0.011 (0.22)      |
| SLOT_FLOOR R1     | +0.010 (0.59)  | +0.036 (0.68)  | +0.216 (0.74)  | +0.004 (0.58)      |
| SLOT_CEIL  R1     | +0.033 (0.80)  | +0.072 (0.86)  | +0.297 (0.85)  | -0.025 (0.09)      |
| SLOT_ROUND_VOL R2 | -0.076 (0.08)  | -0.111 (0.13)  | -0.490 (0.11)  | -0.010 (0.24)      |
| SLOT_FLOOR_VOL R2 | -0.074 (0.10)  | -0.105 (0.14)  | -0.406 (0.16)  | +0.005 (0.60)      |
| SLOT_CEIL_VOL  R2 | -0.025 (0.27)  | -0.026 (0.35)  | -0.139 (0.32)  | -0.023 (0.11)      |

R2 vs R1 (matched mapping; drop-highest-vol minus drop-lowest-momentum):

| pair                        | dSharpe        | dSortino       | dCVaR          | dMaxDD          |
|-----------------------------|----------------|----------------|----------------|-----------------|
| SLOT_ROUND_VOL vs SLOT_ROUND| -0.075 (0.14)  | -0.122 (0.15)  | -0.562 (0.12)  | +0.001 (0.54)   |
| SLOT_FLOOR_VOL vs SLOT_FLOOR| -0.085 (0.12)  | -0.141 (0.13)  | -0.622 (0.12)  | +0.001 (0.56)   |
| SLOT_CEIL_VOL  vs SLOT_CEIL | -0.058 (0.16)  | -0.098 (0.17)  | -0.436 (0.15)  | +0.003 (0.57)   |

No matched-exposure comparison reaches significance on Sharpe/Sortino/CVaR. The
only significant cell is CONT's dMaxDD vs PROD (p=0.97), already known. R1 vs CONT
is a statistical WASH on every metric. R2 underperforms R1 consistently (negative
dSharpe/dSortino/dCVaR p=0.12-0.16, directionally robust but not <0.05) at NO DD
benefit (dMaxDD ~0).

## Per-crisis MaxDD + 2021 unwind (stress 1999+)

| config            | dotcom | GFC    | COVID  | 2022   | 2025   | 2021unwind DD | 2021 cum |
|-------------------|--------|--------|--------|--------|--------|---------------|----------|
| PROD              | -12.1% | -9.1%  | -4.7%  | -0.3%  | -4.8%  | -31.4%        | -28.2%   |
| CONT (dial)       | -12.1% | -8.7%  | -4.7%  | -0.3%  | -2.9%  | -22.7%        | -19.8%   |
| SLOT_ROUND R1     | -12.1% | -10.5% | -4.7%  | -0.3%  | -4.4%  | -22.4%        | -18.6%   |
| SLOT_FLOOR R1     | -12.1% | -10.5% | -4.7%  | -0.3%  | -4.4%  | -19.6%        | -17.3%   |
| SLOT_CEIL  R1     | -12.1% | -9.5%  | -4.7%  | -0.3%  | -3.7%  | -26.1%        | -21.1%   |
| SLOT_ROUND_VOL R2 | -12.1% | -8.7%  | -4.7%  | -0.3%  | -2.9%  | -23.7%        | -20.8%   |
| SLOT_FLOOR_VOL R2 | -12.1% | -8.7%  | -4.7%  | -0.3%  | -2.9%  | -20.3%        | -16.6%   |
| SLOT_CEIL_VOL  R2 | -12.1% | -8.7%  | -4.7%  | -0.3%  | -2.9%  | -27.1%        | -25.4%   |

COVID-V is IDENTICAL (-4.7%) across all configs -- the gate covers it; vol scaling
never engages. The 2021 unwind is the event of interest. At MATCHED exposure
(meanExp ~0.90) SLOT_ROUND R1 (-22.4%) and CONT (-22.7%) cut the unwind almost
IDENTICALLY: dropping the weakest momentum slots does NOT beat uniform shrink. The
top-ranked names crashed about as hard as the marginal ones (sleeve-wide
co-movement confirmed). The 2021 DD ladder tracks EXPOSURE, not concentration:
FLOOR (exp 0.857) -19.6% < ROUND (0.901) -22.4% < CEIL (0.934) -26.1%. Note
SLOT_ROUND R1 slightly RAISES GFC DD (-10.5% vs PROD -9.1%) -- a small concentration
side-effect, but GFC is a gate-window crisis and not the target risk.

## Turnover / granularity / rounding fragility

- Coarse 20% slot jumps did NOT raise turnover: SLOT_ROUND 5.12 < CONT 5.19 (PROD
  5.16). Slot-count changes are infrequent (1.65/yr round-mapping, 0.89/yr ceil),
  so the chunky-turnover concern never materialized at monthly frequency. The
  feared whipsaw/turnover penalty of discretization is NOT real here.
- Rounding fragility (floor/round/ceil) is benign and monotone in EXPOSURE: lower
  mapping -> lower exposure -> lower DD + lower CAGR. No discontinuous blowup, no
  whipsaw. floor and round sit within noise of each other; ceil retains more
  equity. The mapping choice is just an exposure knob, not a fragile DoF.

## Walk-forward (3-seg, clean) -- Sharpe by segment

| config            | seg1  | seg2  | seg3  |
|-------------------|-------|-------|-------|
| PROD              | 1.179 | 1.252 | 1.471 |
| CONT (dial)       | 1.212 | 1.254 | 1.346 |
| SLOT_ROUND R1     | 1.179 | 1.271 | 1.367 |
| SLOT_FLOOR R1     | 1.186 | 1.269 | 1.377 |
| SLOT_CEIL  R1     | 1.213 | 1.251 | 1.449 |
| SLOT_ROUND_VOL R2 | 1.264 | 1.278 | 1.115 |
| SLOT_FLOOR_VOL R2 | 1.294 | 1.265 | 1.067 |
| SLOT_CEIL_VOL  R2 | 1.302 | 1.251 | 1.244 |

R1 tracks CONT across segments (no stable edge either way). R2 (drop-highest-vol)
looks good early but DEGRADES into the recent segment (1.264 -> 1.115), the
opposite of robust -- consistent with shedding high-vol winners that paid off in
the 2020-2026 growth regime. No config beats PROD across all segments.

## Answers

(a) **At matched exposure, does slot-replacement (drop-weakest-to-safe) beat the
continuous dial on Sharpe/DD/tail? Bootstrap-significant?** NO. R1 SLOT_ROUND vs
CONT at matched meanExp (~0.90) is a WASH on every metric: dSharpe -0.001 (0.51),
dSortino +0.010 (0.56), dCVaR +0.072 (0.60), dMaxDD -0.011 (0.22, slightly worse
DD). Nothing significant. Concentrating in the top names under stress neither
helps nor hurts at matched exposure -- the apparent SLOT_CEIL edge (dSharpe +0.033)
is a HIGHER-exposure effect (meanExp 0.934), not concentration.

(b) **2021 unwind: does dropping the weakest momentum slots cut the unwind more
than uniform shrink?** NO. SLOT_ROUND R1 -22.4% vs CONT -22.7% -- essentially
identical. The top momentum names crashed about as hard as the marginal ones; the
-31% is sleeve-wide risk-on CO-MOVEMENT, not a quality-dispersion event the
weakest slots uniquely drive. The unwind DD is governed by total exposure, not by
which names are dropped.

(c) **Turnover/whipsaw cost of the coarse 20% granularity + rounding fragility?**
NEGLIGIBLE. Slot turnover (5.05-5.12) is at or below CONT (5.19); slot-count
changes are rare (0.9-1.7/yr). floor/round/ceil are monotone in exposure with no
whipsaw or discontinuity. The discretization concern does not bite at monthly
frequency.

(d) **Net: better, equal, or worse DD dial than the continuous dial? Any alpha?**
EQUAL, with no alpha. Slot-replacement is statistically indistinguishable from the
continuous dial at matched exposure on Sharpe/Sortino/CVaR, slightly worse on DD
point estimate, and identical in mechanism -- still a risk-for-return DIAL (CAGR
and vol fall ~proportionally with exposure). It adds operational complexity
(discrete jumps, name churn, drop-rule choice) for ZERO measured benefit over the
smooth dial. It is neither better nor a source of edge.

(R1 vs R2 drop rule) R2 (drop highest-vol) IS vol-coherent -- at matched exposure
it holds a lower-vol kept basket (keptRV 0.306 vs R1 0.328) -- but that vol
coherence is RETURN-DESTRUCTIVE: it sheds high-vol names that were top performers,
costing ~0.06-0.09 Sharpe and ~0.4-0.6 CVaR vs R1 (directionally robust, p~0.12-
0.16) at NO incremental DD benefit (dMaxDD ~0), and it degrades out-of-sample in
walk-forward. In this momentum sleeve high vol != bad; the vol-target objective
should NOT also drive name selection. R1 (drop-lowest-momentum) dominates R2.

## Verdict

Discrete slot-replacement (drop weakest momentum names to safe, n=round(scale*5))
is EQUIVALENT to the incumbent continuous vol-target dial at matched exposure --
no significant Sharpe/Sortino/CVaR difference, slightly worse MaxDD point
estimate, and it does NOT cut the 2021 unwind any better (co-movement: top names
fall with the rest). Concentration-under-stress provides no edge here. The coarse
20% granularity is cheaper than feared (turnover at/below the dial, rare jumps, no
whipsaw, benign rounding), but cheap-and-equal is still just equal. The
vol-coherent drop rule (R2, drop highest-vol) is vol-coherent but return-
destructive and unstable OOS -- rejected. Net: the user idea is a valid,
implementable alternative but offers no improvement over the simpler continuous
dial; the continuous dial remains the preferred DD-control lever (simpler, no
drop-rule DoF, marginally better DD).

## Caveats / confidence

- DATASET LIMITATION (per user scope relaxation): runs on the cached daily panel
  (`data/ndx_constituents/prices.parquet`), partial vs a full survivorship-free
  PIT history. Mitigated: PROD, CONT, and EVERY slot variant run on the IDENTICAL
  dataset via the same monkeypatched engine, so the COMPARISON is apples-to-apples
  and the directional verdict is sound. Absolute levels (Sharpe ~1.28, MaxDD ~-31%)
  match prior NDX runs but are NOT a publishable survivorship-clean anchor.
- Matched exposure is APPROXIMATE: CONT meanExp 0.898 vs SLOT_ROUND 0.901 (gap
  0.003, well matched). FLOOR/CEIL deliberately shift exposure as the mapping
  sensitivity -- their metric gaps vs CONT are exposure-driven, not concentration,
  and are reported as such.
- dMaxDD/dCalmar CIs are path-dependent (soft) per the bootstrap helper design;
  dSharpe/dSortino/dCVaR are the order-invariant classification metrics.
- DoF: slot-mapping (floor/round/ceil) + drop-rule (mom/vol) are degrees of
  freedom; sensible a-priori defaults (round, drop-lowest-momentum) + full
  sensitivity reported, NOT optimized. Single in-sample (clean=decision,
  stress=confirm). PIT/delisting integrity, T+1 MOO, 10bps costing inherited
  unchanged from the prod engine.
- Confidence: MODERATE-HIGH on direction (slot=dial at matched exposure; no
  concentration edge; 2021 co-movement; R1>R2; turnover benign), given identical-
  engine comparison + consistent bootstrap + sensitivity + walk-forward. LOW on
  absolute magnitudes (dataset).

## Handoff

None required for analysis. No prod change warranted (slot-replacement offers no
improvement over the existing continuous dial). If a DD-control dial is adopted at
all, that DD-vs-return tradeoff is a risk/objective call for the ORACLE, and the
continuous dial (already studied in `cpm_ndx_voltarget_findings.md`) remains the
simpler choice; any code change routes to the FIXER.
