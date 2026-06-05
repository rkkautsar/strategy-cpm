# Faithful standalone Optimum3 -- repro, validation, and CPM-8 comparison

Status: research benchmark / due-diligence. Research-only, no prod edits, no commit.
Point estimates only (no bootstrap/WF). ASCII only.

## Question / hypothesis

Implement OPTIMUM3 as faithfully as possible to its PUBLIC rules as a STANDALONE
strategy (NOT a CPM variant): pure dual-momentum gate -> top-half pool -> Varadi
MCA 3-asset min-correlation subset -> equal-weight 1/3 -> cash routing, monthly.
Backtest on our data, validate direction/ballpark vs AllocateSmartly's published
track record, and compare to CPM-8 + cheap benchmarks on the SAME common window.

## Method

- Harness `research/optimum3_faithful_harness.py`, runner `..._run.py`.
- Faithful Optimum3 logic implemented FRESH (the prior `cpm_opt3_universe_*` run
  used the CPM mechanism -- vol-adj ranker, TIP canary, breadth /4 scaling -- NOT
  faithful Optimum3). This implementation has NONE of those CPM-isms.
- Rules: rank 15 ETFs by momentum -> take top half (round(15/2)=8) -> keep only
  those with positive momentum (absolute/trend gate) = eligible pool -> if >=3,
  pick the 3-subset with LOWEST avg pairwise correlation (exhaustive C(pool,3),
  252d corr) -> EW 1/3. If <3 pass the gate, hold those at 1/3 each + remainder to
  cash (SHV); if 0 pass, 100% cash. No canary, no vol-adj, no vol-target.
- Engine reused from CPM: signals lagged, T+1 MOO-exact (mooex), 10 bps/side,
  monthly. CPM-8 clone reproduces the prod anchor (Sharpe 1.315 on this common
  window / 1.2557 on the full prod clean window) -> engine wiring verified.
- Data loader / 15-ETF resolution reused from `cpm_opt3_universe_harness`.

## STATED ASSUMPTIONS (this strategy is partly a black box)

- LOOKBACK is UNDISCLOSED (vendor: "daily fast-tactical"). PRIMARY proxy = 13612U
  (Keller avg of 1/3/6/12m total returns, the repo's canonical convention).
  SENSITIVITY tests 6m and 12m. The true lookback is unknowable -> the repro
  carries irreducible uncertainty (quantified below).
- CASH = SHV (Optimum3 says BIL/SHV). top-half = 8 of 15 (7 tested).
- Single month-end rebalance = CORE. 3-tranche (days ~2/9/16) = optional proxy.

## Effective universe / data reality

OPT3 (15): SPY QQQ VNQ REM IEF TLT TIP VGK EWJ SCZ EEM RWX BWX DBC GLD.
Bonds (IEF/TLT/TIP) ARE momentum candidates (faithful). Common all-rankable
window 2009-01-31 .. 2026-05-22 (SCZ inception 2007-12 binding + warmup).

- 6 of 15 are freshly fetched cached yfinance ETFs with NO proxy stitch and NO
  point-in-time guarantee: REM (2007-05), VGK (2005-03), EWJ (2003-01),
  SCZ (2007-12, BINDING), RWX (2006-12), BWX (2007-10). 9 come from the in-repo
  proxy panel. This flatters Optimum3 if anything (survivorship) -- yet it still
  loses badly (see below), so the negative read is robust to it.

## Results -- common window 2009-01-31 .. 2026-05-22

```
config                         Sharpe Sortino Calmar Martin    MaxDD   CVaR   CAGR   Vol   Turn
O3 13612U top8 MCA *  (PRIMARY)  0.650   0.798  0.235   1.08  -32.64%  -1.89%   7.66% 12.55%   4.99
-- lookback sensitivity (MCA-3, top8) --
O3 6m   top8 MCA                 0.730   0.871  0.253   1.32  -34.71%  -1.88%   8.77% 12.66%   4.61
O3 12m  top8 MCA                 0.487   0.597  0.154   0.65  -35.19%  -1.89%   5.43% 12.50%   3.59
O3 13612U top8 MCA               0.650   0.798  0.235   1.08  -32.64%  -1.89%   7.66% 12.55%   4.99
-- structure sensitivity (13612U) --
O3 13612U top7 MCA               0.720   0.889  0.270   1.18  -33.19%  -1.99%   8.97% 13.13%   4.55
O3 13612U top8 top3mom (no MCA)  0.735   0.963  0.411   1.21  -23.80%  -2.18%   9.79% 14.11%   3.95
-- optional 3-tranche proxy (ccT+1, smoothing illustration only) --
O3 3-tranche (proxy)             0.738   0.920  0.328   1.12  -24.99%  -1.80%   8.20% 11.60%    --
-- comparison (SAME window) --
CPM-8 minvar k4 (prod)           1.315   1.571  1.278   4.98  -10.71%  -1.55%  13.68% 10.17%   3.56
60/40 SPY/IEF                    1.040   1.336  0.505   2.31  -21.02%  -1.52%  10.61% 10.22%   0.03
SPY buy-hold                     0.909   1.130  0.462   2.48  -33.72%  -2.68%  15.58% 17.66%   0.03
```

## Per-crisis + bull (total return %)

```
window                       O3 primary   CPM-8    60/40    SPY-BH
GFC 2008-09..2009-03 (partial)    1.07%    1.99%   -0.59%   -3.31%
Euro 2011-05..2011-10             5.18%   -0.68%    0.54%   -7.08%
Q4-2018 2018-10..2018-12         -5.79%    0.53%   -6.76%  -13.53%
COVID 2020-02..2020-04          -25.93%    0.77%   -4.31%  -13.45%
Bear 2022-01..2022-10            -8.42%   -0.33%  -16.88%  -17.74%
Bull 2013-2017                   27.16%   50.06%   61.50%  107.15%
Tariff 2025 2025-02..2025-04     -8.45%   -0.76%   -3.68%   -8.77%
```

(GFC row partial -- common window starts 2009-01.)

## Answers

(a) HOW DOES FAITHFUL OPTIMUM3 PERFORM ON OUR DATA?
Mediocre and drawdown-prone. PRIMARY (13612U/MCA/top8): Sharpe 0.650, CAGR 7.66%,
MaxDD -32.64%, Vol 12.55%, Calmar 0.235. The -32.6% MaxDD lands on 2020-03-24
(COVID): the Feb-28 signal held QQQ + IEF + REM; REM (mortgage REIT) was MCA-picked
for LOW HISTORICAL correlation but cratered ~50% in the crash. Monthly signals
cannot react inside a fast crash, and the rule keeps the book FULLY INVESTED in 3
risky names whenever >=3 of the top-half are positive (almost always with 15 global
candidates) -> there is essentially no breadth-driven de-risking. This is the same
failure mode the prior CPM-mechanism "half->3" experiment flagged; faithful
Optimum3 IS that structure.

(b) VALIDATION vs ALLOCATESMARTLY (direction / ballpark):
AllocateSmartly (allocatesmartly.com/financial-mentors-optimum3-strategy, indep.
test, since 1987, net of costs, rules undisclosed) CONFIRMS our rule skeleton in
prose: "15 global asset classes", "selects roughly the top half that have exhibited
the strongest momentum", "dual momentum" (positive AND relative), and a "high
momentum diversification" optimization (= the Varadi MCA min-corr step). So the
STRUCTURE is faithful. A member-derived figure (Reddit, ~last 20y) is ~11.7% CAGR
vs -12.9% MaxDD (CAGR/MaxDD ~0.9, vol "roughly inline with diversified B&H").
- OUR REPRO: CAGR 7.66%, MaxDD -32.64%, CAGR/MaxDD 0.23. DIRECTIONALLY a momentum
  strategy, but materially WORSE on return and DRAMATICALLY worse on drawdown
  (-32.6% vs -12.9%, ~2.5x). We do NOT reproduce their headline numbers.
- Most likely reasons for divergence, in order of probable impact:
  1. UNDISCLOSED LOOKBACK. Vendor calls it "daily fast-tactical". A daily/fast
     trend filter would de-risk into COVID/2022 far faster than ANY monthly proxy
     -- exactly where our MaxDD is generated. Our best monthly proxy (6m) only
     trims to Sharpe 0.730. None of {6m,12m,13612U} gets near 0.9 CAGR/MaxDD.
  2. TRANCHING + intra-month execution (their real-money refinement). Our 3-tranche
     proxy alone cut MaxDD -32.6% -> -25.0% and lifted Sharpe to 0.738.
  3. DATA: their 1987 backtest spans many regimes; OUR 2009+ window is dominated by
     COVID and 2022 (single-event tail risk inflates MaxDD and depresses CAGR/MaxDD).
  4. Our 15-ETF set / cash asset / exact gate may differ from their internal set.
- Bottom line: our STRUCTURE matches their public description, but the NUMBERS do
  not validate -- the gap is consistent with the undisclosed fast lookback +
  tranching + a longer/cleaner sample, not with a logic error. We cannot match
  1987; recent-overlap only.

(c) VS CPM-8 + BENCHMARKS (same window):
CPM-8 DOMINATES on every risk-adjusted metric: Sharpe 1.315 vs 0.650, Calmar 1.278
vs 0.235, MaxDD -10.71% vs -32.64%, CAGR 13.68% vs 7.66% -- at LOWER vol (10.17%
vs 12.55%). Faithful Optimum3 also loses to a static 60/40 (Sharpe 1.040, MaxDD
-21%) and has a deeper drawdown than even SPY buy-hold (-32.6% vs -33.7% is a wash,
but Optimum3 gives up most of equity's upside: CAGR 7.66% vs 15.58%). Per-crisis,
CPM-8 is roughly flat through COVID (+0.77%) and 2022 (-0.33%) while Optimum3 takes
-25.9% / -8.4%. The CPM canary + breadth-scaled cash routing is doing the heavy
lifting that faithful Optimum3 lacks.

(d) LOOKBACK SENSITIVITY (repro uncertainty):
LARGE. Across {6m,12m,13612U}: Sharpe 0.487..0.730, CAGR 5.43%..8.77%, MaxDD
-32.6%..-35.2%. The undisclosed lookback swings Sharpe by ~0.24 and CAGR by ~3.3pp
-- i.e. the repro is genuinely uncertain on RETURN/Sharpe, but ROBUSTLY bad on
DRAWDOWN (every lookback is -32% to -35%). The drawdown problem is structural (no
fast de-risk), not a lookback artifact. 6m is the best monthly proxy here; 12m the
worst. Structure choices matter too: top3-by-momentum (NO MCA) actually BEAT MCA
(Sharpe 0.735 vs 0.650, MaxDD -23.8% vs -32.6%) -- MCA's "least-correlated" picks
loaded into assets (e.g. REM) whose low HISTORICAL correlation did not hold in the
crash, a known MCA tail-risk failure.

(e) NET READ:
Faithful Optimum3 is NOT competitive with CPM on our data -- it underperforms CPM-8
by ~0.66 Sharpe and runs a ~3x deeper drawdown, and it also loses to a static
60/40. This CONFIRMS CPM's curated-universe + canary + breadth-scaled-cash edge:
the value is in the de-risking machinery and the focused US-tilt universe, not in
raw global breadth + min-corr triplet selection. The one genuinely interesting
property is the MCA diversification IDEA, but on this sample plain top-3 momentum
beat it and the absent de-risk gate makes the whole strategy fragile. Useful as a
benchmark/cousin, not as a model to adopt or to dislodge CPM.

## Mechanism (why it underperforms)

1. NO breadth de-risk: with 15 global candidates there are almost always >=3
   positive top-half names, so the book stays fully invested in 3 risky assets;
   the only defensive trigger (<3 pass the absolute gate) almost never fires ->
   monthly signals get caught fully invested in fast crashes (COVID -25.9%).
2. MCA tail risk: min-correlation selection chases LOW HISTORICAL correlation,
   which can pick assets (REM mortgage-REIT) that decorrelate in calm markets but
   crash WITH equities -- exactly when diversification was supposed to help.
3. Global breadth dilution: intl/EM/REIT/commodity candidates dilute momentum
   quality vs CPM-8's curated US-factor tilt -> structural CAGR drag at higher vol.

## Caveats / discipline

- UNDISCLOSED LOOKBACK is the dominant repro caveat: this is a faithful-STRUCTURE
  port with a STATED proxy lookback, not the real (daily) signal. Direction valid,
  magnitude not validated.
- NON-PIT / SHORT HISTORY / SURVIVORSHIP: 6 ETFs are unstitched cached yfinance
  pulls; biases in Optimum3's favor, yet it still loses -> negative read robust.
- CANNOT MATCH 1987: our 15-ETF universe only exists ~2009+; recent-overlap only.
  The 2009+ window is COVID/2022-heavy, which inflates MaxDD vs a 1987 sample.
- Tranche row is a SMOOTHING illustration: it changes BOTH timing (mid-month vs
  month-end) and execution (ccT+1 vs mooex), so it is not a clean A/B.
- Point estimates only; not tuned toward AllocateSmartly's published numbers.
- Cached-data caveat: frozen in-repo panel + /tmp ETF cache; eval cutoff 2026-05-22.

## Reproduce

```
.venv/bin/python research/optimum3_faithful_run.py
```
Artifacts: `research/optimum3_faithful_harness.py`, `..._run.py`,
`..._results.json`, this file.
```
