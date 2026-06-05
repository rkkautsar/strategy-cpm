# NDX Sleeve: SLEEVE-LEVEL Daily-Overlay Circuit Breakers -- findings

Research-only. No prod / `ndx_sleeve_live.py` / memo edits, no commit. Single
in-sample, high overfit caution (path-dependent design; k / level / MA / X /
window DoF -> a-priori defaults + sensitivity, not optimization).

Harness: `research/cpm_ndx_circuit_breaker_harness.py`.
Runner: `research/cpm_ndx_circuit_breaker_run.py`.
Raw: `research/cpm_ndx_circuit_breaker_results.json`.

## Question / Hypothesis

The NDX sleeve's ~-31% MaxDD is a SLEEVE-WIDE, multi-week, cross-rebalance
momentum/growth unwind (Feb 12 -> Mar 29 2021), NOT an idiosyncratic single-name
intramonth crash. The prior per-STOCK intramonth stop
(`research/cpm_ndx_stoploss_*`) structurally could not catch it (reference resets
monthly; single-name risk already capped ~4%). Does a SLEEVE-LEVEL (whole-basket)
DAILY-OVERLAY circuit breaker -- evaluated on the whole risky basket and rotating
the ENTIRE sleeve to safe for the rest of the month -- cut the -31% (especially
the 2021 unwind) NET of whipsaw / turnover / OOS, where the per-stock stop failed?
And does an ADAPTIVE (vol/trend) breaker beat a fixed-% trailing-DD trigger, or
the existing MONTHLY vol-target dial?

## Method

- Engine: PROD `ndx_sleeve_live` selection unchanged (13612U momentum top-5 EW,
  TIP+SPY-trend+RV gate, best-of-safe, T+1 MOO, 10bps/side, delisting haircut,
  PIT constituents). Reproduced PROD: clean Sharpe 1.273, MaxDD -31.39% (anchor
  ~1.281 / -31.4%); stress Sharpe 0.794.
- Daily-path overlay: walk DAILY through each holding month; evaluate a
  SLEEVE-LEVEL breaker on LAGGED daily data (decision at close t, fill from t+1
  -- prod T+1 convention; trigger-day move + next-day gap are borne). On trigger,
  rotate ALL risky stock weight -> period best-of-safe for the rest of the month;
  NO intramonth re-entry; re-enter at the next monthly rebalance. 10bps/side on
  the de-risk rotation.
- Breaker families (long-only de-risk; no shorting):
  - `volbrk` (ADAPTIVE, user lead): de-risk when trailing SHORT-window basket
    realized vol breaches `k * LONG-window vol` (k in 1.5/2.0/2.5; short 10/20,
    long 63) or an absolute annualized level (rv20 > 0.50).
  - `trend` (ADAPTIVE): de-risk when QQQ closes below MA(20 / 50 / 100).
  - `traildd` (FIXED-%, completeness): de-risk when the basket drops X% from its
    trailing INTRAMONTH peak (X in 10/15/20).
  - `voltarget` (reference): MONTHLY exposure dial, exposure =
    clip(0.30 / realized_basket_vol_60d, 0, 1), freed weight -> safe. Replicates
    the prior vol-target DERISK config ON THIS dataset for apples-to-apples.
- Metrics: Sharpe, Sortino, CVaR-ratio, CAGR, vol, MaxDD, Calmar, Martin,
  annualized turnover, triggers/yr, whipsaw% (= % of triggers where the held
  basket recovered above its exit value by the next rebalance -> sold low,
  rebounded). Paired block bootstrap each vs PROD (B=2000, block=21, seed=42) on
  the clean window. 3-segment walk-forward. Sensitivity sweep.
- Windows: clean 2008-04-30 -> 2026-05-22 (DECISION); stress 1999-01-01 (confirm);
  per-crisis incl explicit 2021unwind (2021-02 -> 2021-05) and COVID-V
  (2020-02 -> 2020-04, the whipsaw check).

### Inputs / data + caveats
- `data/ndx_constituents/prices.parquet` (auto-adjusted Close, from 1995). Daily
  Close only -> no true intraday breaker fills; T+1 close is the conservative
  proxy. PIT membership via index_constitution (>=2006); pre-2006 SPY proxy, so
  the dot-com per-crisis row and the -75.94% stress MaxDD are pre-2006 proxy-era
  CONTEXT only (the gate, not any breaker, drives behaviour there).
- PROD and EVERY breaker variant run on the IDENTICAL dataset (apples-to-apples).
  Scope-relaxed: goal is the comparable DIRECTIONAL verdict, not a publishable
  survivorship-clean absolute anchor.

## Results

### Config table -- CLEAN (2008-04 -> 2026-05)

| Variant            | Sharpe | Sortino | CVaR | CAGR%  | Vol%  | MaxDD%  | Calmar | Martin | Turn  | Trg/yr | Whip% |
|--------------------|--------|---------|------|--------|-------|---------|--------|--------|-------|--------|-------|
| PROD               | 1.273  | 1.950   | 8.35 | 31.15  | 23.52 | -31.39  | 0.99   | 4.20   | 9.38  | 0.00   | --    |
| VolBrk k1.5        | 1.243  | 1.901   | 8.04 | 28.10  | 21.90 | -31.17  | 0.90   | 3.80   | 11.68 | 1.02   | 54    |
| VolBrk k2.0        | 1.278  | 1.954   | 8.35 | 31.02  | 23.31 | -31.39  | 0.99   | 4.22   | 9.52  | 0.07   | 0     |
| VolBrk abs50       | 1.292  | 1.989   | 8.48 | 26.92  | 20.04 | -29.57  | 0.91   | 3.69   | 11.10 | 0.58   | 44    |
| Trend MA20         | 0.604  | 0.879   | 3.82 | 8.67   | 15.89 | -25.45  | 0.34   | 0.88   | 17.94 | 3.47   | 69    |
| Trend MA50         | 0.935  | 1.387   | 5.89 | 17.07  | 18.79 | -27.65  | 0.62   | 1.94   | 13.38 | 1.79   | 71    |
| TrailDD 10         | 1.124  | 1.683   | 7.16 | 23.97  | 21.15 | -26.52  | 0.90   | 2.97   | 11.61 | 0.80   | 55    |
| TrailDD 15         | 1.181  | 1.769   | 7.57 | 27.25  | 22.62 | -35.27  | 0.77   | 3.16   | 10.21 | 0.29   | 88    |
| TrailDD 20         | 1.234  | 1.862   | 7.97 | 28.98  | 22.78 | -33.69  | 0.86   | 3.43   | 9.71  | 0.11   | 67    |
| VolTarget(monthly) | 1.255  | 1.900   | 8.17 | 25.38  | 19.60 | -26.60  | 0.95   | 3.80   | 9.40  | 0.00   | --    |

### Per-crisis MaxDD% -- CONTEXT (path-dependent)

| Crisis        | PROD  | VBk1.5 | VBk2.0 | VBabs50 | TrMA20 | TrMA50 | TrDD10 | TrDD15 | TrDD20 | VolTgt |
|---------------|-------|--------|--------|---------|--------|--------|--------|--------|--------|--------|
| dotcom(00-02)*| -32.0 | -32.0  | -32.0  | -32.0   | -32.0  | -32.0  | -32.0  | -32.0  | -32.0  | -32.0  |
| GFC(07-09)    | -6.2  | -6.2   | -6.2   | -6.2    | -6.2   | -6.2   | -6.2   | -6.2   | -6.2   | -6.2   |
| COVID-V(20)   | -4.7  | -4.7   | -4.7   | -4.7    | -4.7   | -4.7   | -4.7   | -4.7   | -4.7   | -4.7   |
| **2021unwind**| **-31.4** | -31.2 | -31.4 | -28.6 | **-11.7** | -18.0 | -20.8 | -35.3 | -33.7 | **-22.7** |
| 2022          | -0.3  | -0.3   | -0.3   | -0.3    | -0.3   | -0.3   | -0.3   | -0.3   | -0.3   | -0.3   |
| 2025          | -2.9  | -2.9   | -2.9   | -2.9    | -2.9   | -2.9   | -2.9   | -2.9   | -2.9   | -2.9   |

`*` dot-com = pre-2006 SPY-proxy era, context only. 2021unwind CAGR within window:
PROD -34.7%, Trend MA20 **+32.3%** (dodges entirely), VolTarget -24.5%,
TrailDD15 -50.0% (sells low, re-enters into the continued decline).

### Paired block bootstrap each vs PROD (clean; B=2000, block=21, seed=42)

| Variant            | dSharpe (95% CI) p>0           | dMaxDD (pp) p>0         |
|--------------------|--------------------------------|-------------------------|
| VolBrk k1.5        | -0.029 [-0.191,+0.142] 0.36    | +0.003 0.48             |
| VolBrk k2.0        | +0.006 [-0.045,+0.068] 0.54    | +0.003 0.38             |
| VolBrk abs50       | +0.021 [-0.201,+0.227] 0.60    | +0.034 0.78             |
| Trend MA20         | **-0.670 [-1.071,-0.292] 0.00**| +0.011 0.57             |
| Trend MA50         | **-0.336 [-0.610,-0.065] 0.01**| +0.023 0.67             |
| TrailDD 10         | -0.150 [-0.395,+0.072] 0.10    | +0.016 0.61             |
| TrailDD 15         | **-0.093 [-0.203,+0.005] 0.03**| -0.037 0.13             |
| TrailDD 20         | -0.039 [-0.130,+0.039] 0.18    | -0.022 0.20             |
| VolTarget(monthly) | -0.018 [-0.123,+0.078] 0.37    | **+0.049 [-0.000,+0.107] 0.97** |

dSharpe/dSortino/dCVaR are the order-invariant classification metrics; dMaxDD CI
is path-dependent (soft). Trend MA20/MA50 and TrailDD15 are SIGNIFICANTLY WORSE on
Sharpe. The ONLY config with a bootstrap-significant DD cut is the MONTHLY
vol-target dial (dMaxDD +0.049, p=0.97) -- and it does so with NO Sharpe loss.

### Walk-forward (3 seg clean): Sharpe / MaxDD%

| Seg                     | PROD        | VBabs50     | TrMA20      | TrMA50      | TrDD20      | VolTgt      |
|-------------------------|-------------|-------------|-------------|-------------|-------------|-------------|
| 1: 2008-04 .. 2014-05   | 1.160/-17.3 | 1.274/-15.4 | 0.679/-20.7 | 0.757/-16.3 | 1.160/-17.3 | 1.192/-17.3 |
| 2: 2014-05 .. 2020-05   | 1.249/-17.0 | 1.249/-17.0 | 0.392/-21.8 | 0.879/-17.1 | 1.249/-17.0 | 1.251/-17.0 |
| 3: 2020-05 .. 2026-05   | 1.468/-31.4 | 1.378/-29.6 | 0.721/-25.4 | 1.146/-27.7 | 1.365/-33.7 | 1.343/-26.6 |

Trend is the WORST variant in all 3 segments. VolBrk abs50 looks good in Seg1 but
LAGS PROD in Seg3 (the segment that contains 2021) -- its mild 2021 "catch" does
not translate to segment outperformance (overfit signature of a picked absolute
level). VolTarget tracks PROD across all 3 with a consistent DD benefit in Seg3.

### Sensitivity (clean)

| variant      | Sharpe | MaxDD%  | CAGR% | Trg/yr | Whip% | Turn  |
|--------------|--------|---------|-------|--------|-------|-------|
| Trend MA100  | 0.943  | -32.7   | 19.0  | 1.17   | 78    | 12.06 |
| VolBrk k2.5  | 1.273  | -31.4   | 31.1  | 0.00   | --    | 9.38  |
| VolBrk s20k2 | 1.273  | -31.4   | 31.1  | 0.00   | --    | 9.38  |

Vol-breakdown is monotone toward no-op as k loosens (k>=2.0/2.5 == PROD: the
basket vol of momentum leaders rarely "breaks down" relative to its own trailing
vol). Trend is monotone toward return destruction as the MA lengthens stops
firing in normal pullbacks. Neither sweep produces a robust winner.

## Answers

(a) **Does a sleeve-level daily breaker cut the -31% (esp 2021) where the
per-stock stop failed?** YES on the mechanic, NO net of cost/OOS. The SLEEVE-LEVEL
TREND breaker DOES catch the 2021 unwind that the per-stock stop structurally
could not: Trend MA20 cuts the 2021unwind MaxDD -31.4% -> -11.7% and actually
EARNS +32% in that window (it exits while the basket keeps falling). This confirms
the diagnosis -- the failure mode is sleeve-wide and a trend signal that spans
rebalances catches it. BUT across the full clean sample the trend breaker is a
large NET LOSER: clean Sharpe 1.273 -> 0.604 (MA20) / 0.935 (MA50), bootstrap
dSharpe -0.670 / -0.336 (both p<=0.01 SIGNIFICANTLY WORSE), turnover 9.4 -> 18,
69-71% whipsaw. It catches the one event you aim it at and pays for it in every
normal pullback.

(b) **vol-breakdown vs trend vs trailing-DD; do adaptive beat fixed-%?** None
wins; the user-preferred adaptive lead (vol-breakdown) is the WEAKEST on the
actual objective.
- VOL-BREAKDOWN (adaptive): near no-op and FAILS to catch 2021 (k2.0 identical to
  PROD; abs50 only -28.6). The 2021 unwind was a slow multi-week de-rate, not a
  vol spike, so a vol-breakdown trigger never fires in time. Wrong signal for this
  failure mode.
- TREND (adaptive): the ONLY breaker that genuinely catches 2021, but
  bootstrap-significantly worse on Sharpe (see (a)).
- TRAILING-DD (fixed): structurally broken at this monthly-reset cadence -- loose
  X (15/20) makes the MaxDD WORSE (-35.3 / -33.7 vs -31.4) because it de-risks
  intramonth then re-enters at the next rebalance straight into the continuing
  decline (peak resets monthly); 88% whipsaw at X=15. Tight X=10 cuts DD to -26.5
  but costs ~7pp CAGR and is bootstrap-insignificant.
  So adaptive does NOT cleanly beat fixed: vol-breakdown (adaptive) doesn't catch
  the event; trend (adaptive) catches it but is net-negative; trailing-DD (fixed)
  is structurally counterproductive. No breaker family is a winner.

(c) **Whipsaw / COVID-V check -- does the breaker sell bottoms?** The gate already
covers the V-crashes. In COVID-V (and GFC, 2022) EVERY variant is IDENTICAL to
PROD (-4.7% / -6.2% / -0.3%): the gate has already rotated the sleeve to safe
before those drawdowns, so NO breaker fires and NONE sells the COVID bottom. The
whipsaw cost (54-88%) is therefore NOT a crisis-bottom problem -- it is a
steady-state bull-market drag (constantly dipping below the MA / DD threshold in
ordinary pullbacks, exiting, re-entering higher). That is precisely why trend
craters Sharpe while leaving named-crisis DDs untouched.

(d) **Does any daily breaker beat the monthly vol-target dial?** NO -- the monthly
dial DOMINATES every daily breaker. VolTarget(monthly): Sharpe 1.255 (dSharpe
-0.018, p0.37 NOT significant -- preserved), MaxDD -26.6 (dMaxDD +0.049, p0.97 --
the ONLY bootstrap-significant DD cut), turnover 9.40 (= PROD), ZERO triggers,
ZERO whipsaw, and it still trims 2021unwind to -22.7. It achieves the DD control
the daily breakers chase, with none of their turnover/whipsaw collateral and no
Sharpe loss. Intramonth daily complexity is NOT worth it on this sleeve.

(e) **Real improvement or just another (worse) risk dial?** No real improvement
from any daily breaker. None raises Sharpe (all flat-to-significantly-worse); the
only clean DD cut is the already-known monthly vol-target dial. The daily breakers
add DoF, turnover and whipsaw for no net gain.

## Verdict

A SLEEVE-LEVEL daily circuit breaker CONFIRMS the diagnosis but does NOT pay off.
The trend variant proves the -31% IS catchable at the sleeve level (2021unwind
-31% -> -12%, +32% in-window) -- exactly where the per-stock intramonth stop was
structurally blind -- but it is bootstrap-significantly WORSE on Sharpe
(-0.67 / -0.34, p<=0.01) and worst-in-class in all 3 walk-forward segments,
because catching one multi-week unwind costs ~3-4 exits/yr and ~70% whipsaw of
ordinary bull-market pullbacks. The user-preferred ADAPTIVE vol-breakdown does not
even fire on the 2021 slow de-rate (wrong signal for a non-spike unwind). The
fixed-% trailing-DD is structurally counterproductive at monthly-reset cadence
(loose X WORSENS MaxDD; 88% whipsaw). The gate already strips the V-crashes, so no
breaker sells the COVID bottom -- the whipsaw is steady-state drag, not
crisis-timing. NET: the existing MONTHLY vol-target dial dominates the entire daily
breaker family -- same DD control (-31% -> -27%, the only bootstrap-significant
cut), no Sharpe loss, no added turnover, zero whipsaw. Recommendation: do NOT adopt
a sleeve-level daily circuit breaker; if drawdown control is the goal, use the
monthly basket-vol de-risk dial (per `cpm_ndx_voltarget_findings.md`). Intramonth
overlay does not beat the monthly dial here.

## Caveats / confidence

- DATASET LIMITATION (per scope relaxation): cached adjusted-Close daily panel,
  partial vs survivorship-free PIT. Mitigated: PROD + every variant on the
  IDENTICAL dataset via the same engine, so the COMPARISON and DIRECTION are sound;
  absolute levels (Sharpe ~1.27, MaxDD ~-31%) are NOT a publishable anchor.
- No intraday -> T+1 close fill is the conservative proxy (a fill-at-level model
  would be strictly more favourable to the breakers; even so they lose).
- dMaxDD/dCalmar/dMartin CIs are path-dependent (soft); dSharpe/dSortino/dCVaR are
  the order-invariant classification metrics that drive the verdict.
- DoF (k / level / MA / X / window) -> a-priori defaults + sensitivity reported,
  single in-sample, bootstrap + walk-forward. The one mildly-favourable cell
  (VolBrk abs50) sits in a sweep corner and lags PROD in the 2021-containing
  walk-forward segment -- treated as overfit, not a winner.
- Per-crisis rows are CONTEXT (path-dependent), not classification.
- Confidence: MEDIUM-HIGH on direction (consistent across clean / stress /
  per-crisis / bootstrap / walk-forward; PROD reproduced; mechanic confirmed via
  the 2021 trend catch). LOW on absolute magnitudes (dataset).

## Handoff

None required for analysis. If a DD-control dial is to be adopted, route the
DD-vs-return objective tradeoff to the ORACLE (the monthly vol-target dial, not a
daily breaker, is the candidate) and any code change to the FIXER.
