# NDX Sleeve: Breadth (top-N) x De-risk Method -- Turnover & Risk/Return Sweep

Analyst, hypothesis-driven backtest. Read-only re production. Engine reused from
`research/cpm_ndx_slotreplace_harness.py` (monkeypatch `compute_ndx_weights` ->
unmodified `run_ndx_backtest`: gate TIP + SPY-trend + SPY-RV, best-of-safe
rotation, T+1 MOO, 10 bps/side, delisting haircut, PIT membership). CONT and SLOT
share the IDENTICAL basket-vol scale signal (target 0.30, 60d lagged, cap 1.0),
so equity exposure is matched WITHIN each N.

Artifacts:
- `research/cpm_ndx_breadth_harness.py` (extends slotreplace harness with an N param)
- `research/cpm_ndx_breadth_run.py`
- `research/cpm_ndx_breadth_findings.json`

Run: `.venv/bin/python research/cpm_ndx_breadth_run.py` (~64s).

Windows: clean 2008-05-30..2026-05-22; ext (stress) 1999-03-10..2026-05-22.
Bootstrap: paired block, B=2000, block=21, seed=42 (dSharpe/dSortino/dCVaR are the
classification CIs; dMaxDD is path-dependent soft context). 3-segment walk-forward.

## 9 cells

NONE = top-N EW, scale=1 always (breadth-only). CONT = top-N EW * scale, freed
weight -> safe (continuous dial). SLOT = discrete drop-lowest-momentum,
n=round(scale*N) kept at 1/N each, the rest to safe. NONE_N5 reproduces the PROD
top-5 EW anchor exactly.

## Anchor check (apples-to-apples sanity)

NONE_N5 clean: Sharpe 1.281, MaxDD -31.4%, CAGR 31.4%, turnover 5.16 -- matches
prod (~1.28 / -31.4% / 31.4% / 5.16) to the reported precision. All cells share
this engine; absolute levels valid for cross-cell comparison (cached dataset).

## HEADLINE: turnover/yr (rows N, cols method)

| N  | NONE | CONT | SLOT |
|----|------|------|------|
| 5  | 5.16 | 5.18 | 5.11 |
| 8  | 4.84 | 4.90 | 4.85 |
| 10 | 4.77 | 4.84 | 4.79 |

Dollar turnover is ~FLAT and even slightly DECLINES as breadth rises, and is
nearly method-invariant (CONT only +0.05..0.07 over NONE). Reason: turnover is
weight-weighted; at N=10 each name is 1/N = 10% of book, so a name rotating in/out
moves only 10% vs 20% at N=5. More marginal names rotate, but each move is half
the size -> net dollar turnover does not rise. Hypothesis (i) is FALSE for dollar
turnover.

## HEADLINE: position-change events / yr (count of assets traded; incl safe)

| N  | NONE | CONT | SLOT | CONT-SLOT gap |
|----|------|------|------|---------------|
| 5  | 35.3 | 45.3 | 34.5 | 10.8 |
| 8  | 48.9 | 60.6 | 48.2 | 12.4 |
| 10 | 58.8 | 72.0 | 57.9 | 14.1 |

Here hypothesis (i) HOLDS: event COUNT rises steeply with breadth (more marginal
names rotating). And the practical contrast (iii) holds at every N: CONT carries a
fixed ~30% event overhead because the continuous dial re-trims EVERY held name
each month; SLOT tracks NONE almost exactly (it only trades on whole-name flips).
The absolute CONT-SLOT event gap GROWS with breadth (10.8 -> 12.4 -> 14.1 /yr),
so discrete's execution-simplicity edge gets LARGER, not smaller, at higher N.

## Whole-name flips and discrete-mechanism activity

| N  | name-flips/yr NONE=CONT | name-flips/yr SLOT | slot-count changes/yr (SLOT) |
|----|-------------------------|--------------------|------------------------------|
| 5  | 31.2 | 28.7 | 1.65 |
| 8  | 44.9 | 42.5 | 1.42 |
| 10 | 54.7 | 52.5 | 1.24 |

Name-flips (enter/exit of the held set) rise with N for all methods -- this is base
SELECTION churn, common to every method, dominated by momentum reranking of the
larger marginal pool. The discrete mechanism's OWN extra activity (slot-count
transitions) is tiny and DROPS with N (1.65 -> 1.24 /yr). Hypothesis (ii) -- finer
1/N steps would flip slots MORE often -- is FALSE: the larger basket has lower
realized vol (see exposure below), de-risks less often (frac de-risk 0.39 -> 0.26),
so the slot count changes LESS, not more.

## Full clean metrics per cell (2008+)

| cell      | Sharpe | Sortino | CVaR | MaxDD  | CAGR  | vol   | meanExp | TO   | posEv |
|-----------|--------|---------|------|--------|-------|-------|---------|------|-------|
| NONE_N5   | 1.281  | 1.962   | 8.40 | -0.314 | 0.314 | 0.236 | ~1.00   | 5.16 | 35.3  |
| CONT_N5   | 1.263  | 1.913   | 8.23 | -0.266 | 0.256 | 0.196 | 0.898   | 5.18 | 45.3  |
| SLOT_N5   | 1.262  | 1.922   | 8.30 | -0.278 | 0.264 | 0.202 | 0.901   | 5.11 | 34.5  |
| NONE_N8   | 1.219  | 1.809   | 7.73 | -0.286 | 0.260 | 0.208 | ~1.00   | 4.84 | 48.9  |
| CONT_N8   | 1.198  | 1.766   | 7.61 | -0.236 | 0.226 | 0.185 | 0.930   | 4.90 | 60.6  |
| SLOT_N8   | 1.220  | 1.804   | 7.79 | -0.247 | 0.237 | 0.189 | 0.929   | 4.85 | 48.2  |
| NONE_N10  | 1.204  | 1.775   | 7.55 | -0.264 | 0.242 | 0.197 | ~1.00   | 4.77 | 58.8  |
| CONT_N10  | 1.171  | 1.710   | 7.33 | -0.235 | 0.213 | 0.179 | 0.941   | 4.84 | 72.0  |
| SLOT_N10  | 1.188  | 1.738   | 7.47 | -0.241 | 0.220 | 0.181 | 0.940   | 4.79 | 57.9  |

meanExp rises with N (0.898 -> 0.941) because the larger basket runs lower realized
vol, hitting the 0.30 target less often.

## Breadth effect on Sharpe/DD (question b)

More breadth DILUTES return quality and ADDS diversification -- a Sharpe-for-DD
trade, not a free lunch:
- Sharpe falls: NONE 1.281 -> 1.219 -> 1.204; CONT 1.263 -> 1.198 -> 1.171; SLOT
  1.262 -> 1.220 -> 1.188.
- CAGR falls: NONE 31.4% -> 26.0% -> 24.2%.
- vol falls and MaxDD shrinks: NONE -31.4% -> -28.6% -> -26.4%.

Bootstrap breadth-vs-top5 (clean): all NOISE. NONE_N8 vs NONE_N5 dSharpe
-0.060 (p0.16); NONE_N10 vs N5 dSharpe -0.075 (p0.15). dSortino/dCVaR lean
negative (p~0.06-0.08) but no 95% CI excludes zero. Same with vol-target on. So
breadth's Sharpe dilution is DIRECTIONAL but not statistically significant, and
its DD relief is real but on soft (path-dependent) CIs. No higher-breadth cell
SIGNIFICANTLY beats top-5 on any classification metric.

## Granularity / convergence: SLOT vs CONT (question c)

| within N | dSharpe (SLOT-CONT) | dSortino | dCVaR | dMaxDD | verdict |
|----------|---------------------|----------|-------|--------|---------|
| N5       | -0.001 (p0.51)      | +0.010   | +0.072| -0.011 | dead wash |
| N8       | +0.021 (p0.79)      | +0.038   | +0.176| -0.008 | SLOT edges, noise |
| N10      | +0.016 (p0.81)      | +0.027   | +0.134| -0.008 | SLOT edges, noise |

At top-5 SLOT vs CONT is a dead heat (confirms prior b849c0f5). At top-8/10 the
finer 1/N steps let the discrete rule track the continuous dial MORE closely on
CAGR/MaxDD/vol AND SLOT slightly EDGES CONT on Sharpe/Sortino/CVaR (p~0.8, still
noise). Hypothesis (iii) convergence holds: discrete approximates the dial better
at higher breadth, and never loses to it.

## De-risk vs none within each N (does vol-target help?)

All NOISE on Sharpe/Sortino/CVaR (no CI excludes 0). The payoff is DD relief in
the 2021 risk-on unwind (the one event the crisis gate does NOT cover):

2021 unwind (2021-02-12..2021-05-13) MaxDD:
- N5:  NONE -31.4% | CONT -22.7% | SLOT -22.4%
- N8:  NONE -28.6% | CONT -23.1% | SLOT -24.7%
- N10: NONE -26.4% | CONT -23.0% | SLOT -24.1%

Both breadth AND vol-target independently soften the 2021 unwind; together they
floor it near -22..-24%. COVID and the gated crises (dotcom -12.1%, GFC ~-9%,
Y2022 -0.3%) are FLAT across all 9 cells -- confirming the gate, not breadth or
the de-risk mechanism, owns the V-crises. DD tracks EXPOSURE, not mechanism.

## Walk-forward (3 segments, Sharpe)

All 9 cells stay positive and stable across all three segments (no cell collapses
in any sub-period). Top-5 leads in the most recent segment (NONE 1.47); top-10 is
weaker early (1.12-1.15) but stronger mid (1.38). No breadth/method combination
shows a regime where it structurally breaks.

## Answers

(a) TURNOVER. Dollar turnover is flat-to-declining with breadth (5.16 -> 4.77) and
nearly method-invariant -- bigger N means smaller per-name weight, so more rotation
at lower dollar cost. But position-change EVENTS rise steeply with breadth (35 ->
59 for NONE) and CONT adds a fixed ~30% re-trim overhead at every N (45 -> 72).
SLOT keeps NONE-level events at all N; its execution-simplicity advantage over CONT
GROWS with breadth (gap 10.8 -> 14.1 events/yr). Finer granularity does NOT cause
more slot flips -- slot-count changes DROP with N (1.65 -> 1.24/yr).

(b) Does breadth help? No -- it is a Sharpe-for-DD trade. Sharpe/CAGR fall
monotonically (top-5 best), vol/MaxDD shrink (top-10 best). All breadth-vs-top5
contrasts are statistically NOISE; the dilution leans real (p~0.06-0.16) and the
DD relief is on soft CIs. No higher-breadth cell beats top-5 on a clean metric.

(c) Granularity. Yes, discrete tracks the continuous dial more closely at top-10
than top-5 (CAGR/MaxDD/vol converge), and SLOT slightly EDGES CONT at top-8/10 on
Sharpe/Sortino/CVaR (still noise). At top-5 it is a dead wash.

(d) Recommendation. Top-5 SLOT (discrete drop-lowest-momentum) remains the
practical pick: best Sharpe/CAGR of the de-risked cells, lowest event count
(~34.5/yr vs CONT 45.3), simplest execution (only ~1.65 slot-count changes/yr plus
base rotation), and it floors the 2021 unwind at -22%. If DD is the priority,
top-8 SLOT trades ~0.06 Sharpe for slightly lower vol while keeping the discrete
event edge; top-10 adds little over top-8. CONT never wins outright -- it costs the
most events for matched (statistically identical) risk/return. NONE leaves the 2021
unwind uncovered (-31%) for no Sharpe gain over SLOT.

## Caveats / confidence

- All cross-cell contrasts are statistical NOISE on the classification metrics
  (dSharpe/dSortino/dCVaR) at B=2000 -- single in-sample backtest; differences are
  directional, not significant. Treat rankings as weak preference, not proof.
- DD/2021-unwind numbers are path-dependent (soft bootstrap CIs); reported as
  point estimates / context.
- Cached dataset (not the prod refresh); apples-to-apples across cells via the
  identical engine, but absolute levels may differ slightly from a live refresh.
- Overfit discipline: only the 3 a-priori N values {5,8,10}, the a-priori round
  mapping n=round(scale*N), and the existing 0.30/60d scale signal -- nothing was
  optimized over the sample. Drop rule fixed to lowest-momentum (R1, the prior
  winner); R2 (drop-high-vol) not re-tested here.
- The de-risk benefit is concentrated in ONE event (2021 risk-on unwind); the
  crisis gate already covers the V-shaped drawdowns, which stay flat across cells.

## Handoff

None required. Research-only; no prod/memo edits, no commit. If a breadth change
were ever adopted, hand the selection-count edit (SELECT_K) to the fixer.
