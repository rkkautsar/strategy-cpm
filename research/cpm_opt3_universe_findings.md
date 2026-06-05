# CPM on Optimum3's 15-asset universe -- sleeve-only findings

Status: exploratory ("try", do NOT adopt). Research-only, no prod edits, no commit.
Point estimates only (no bootstrap/WF). ASCII only.

## Hypothesis / question

The HAA->CPM factorial showed UNIVERSE is the dominant factor (+0.2215 Sharpe).
Optimum3 (CPM's cousin) uses a richer 15-asset global universe. Does porting CPM's
mechanism onto Optimum3's universe -- with min-var or MCA (min avg pairwise
correlation) selection, and a top-K {4,5,6} + Optimum3-faithful "top-half -> 3"
sweep -- beat the curated CPM-8 universe on a common clean window? (a)-(e) below.

## Method

- Harness `research/cpm_opt3_universe_harness.py`, runner `..._run.py`.
- CPM mechanism kept IDENTICAL except the risky universe / selection metric /
  cardinality: vol-adj Faber rank, positive-trend screen, TIP-only canary
  (any_positive), EW risky block, breadth-scaled partial-safe routing, best-of
  {SHV,IEF} safe, monthly, both-252, 10 bps/side, mooex T+1 MOO-exact execution.
- Faithfulness proven: clone at prod-8 / top_k=4 / minvar reproduces the both-252
  anchor exactly (Sharpe 1.2557, MaxDD -0.1303, Calmar 1.0076).
- Selection variants:
  - topk (CPM-faithful): rank vol-adj, take top-K, positive screen; when the
    positive set fills the top-K (>=4) select (n_pos-1)-of-n_pos by metric
    (prod 3-of-4 at the boundary); breadth scale /4.
  - half3 (Optimum3-faithful): pool = top-half of eligible by vol-adj
    (round(N/2) ~7-8 of 15); positive screen; pick FINAL 3 from pool by metric
    (exhaustive C(7,3)=35 etc.); EW 1/3; breadth scale /3 when <3 positives.
- Metrics: Sharpe, Sortino, Calmar, Martin, MaxDD, CVaR95, CAGR, vol,
  annualized one-way turnover.

## Effective universe / data reality (question b)

OPT3 (15, faithful -- bonds ARE momentum candidates per Optimum3):
SPY QQQ VNQ REM IEF TLT TIP VGK EWJ SCZ EEM RWX BWX DBC GLD.

- Dropped tickers: NONE. All 15 resolvable. Mappings used: EM=EEM, intl-REIT=RWX,
  commodities=DBC, gold=GLD (proxy-stitched).
- Dual roles kept (faithful): IEF/TLT/TIP are momentum candidates; TIP also the
  canary; SHV/IEF also the safe pool.
- Six tickers are freshly fetched yfinance ETFs with NO proxy stitch and NO PIT
  guarantee: REM (2007-05), VGK (2005-03), EWJ (2003-01), SCZ (2007-12, BINDING),
  RWX (2006-12), BWX (2007-10). The other 9 come from the in-repo proxy panel.
- Clean-window shrink: prod CPM-8 clean starts 2008-05-30; all-15-rankable common
  start is 2009-01-31 (SCZ inception + warmup). Shrink is only ~8 months -- the
  common-window comparison is reasonably FAIR. The binding limitation is NOT the
  window length but survivorship/PIT integrity of the 6 unstitched ETFs.

## Results -- common window 2009-01-31 .. 2026-05-22 (all 15 rankable)

```
config                     Sharpe Sortino Calmar Martin    MaxDD   CVaR   CAGR   Vol   Turn
CPM-8 minvar k4             1.315   1.571  1.278   4.98  -10.71%  -1.55%  13.68% 10.17%   3.56
OPT3 minvar k4             0.696   0.805  0.491   1.11  -12.60%  -1.48%   6.19%  9.30%   4.56
OPT3 minvar k5             0.852   1.012  0.637   1.71  -11.83%  -1.42%   7.53%  9.05%   4.14
OPT3 minvar k6             0.900   1.080  0.623   1.96  -12.29%  -1.34%   7.65%  8.65%   3.96
OPT3 MCA k4                0.707   0.825  0.440   1.30  -16.02%  -1.66%   7.04% 10.39%   5.08
OPT3 MCA k5                0.862   1.036  0.689   1.84  -11.98%  -1.52%   8.25%  9.75%   4.48
OPT3 MCA k6                0.915   1.108  0.611   2.02  -13.87%  -1.45%   8.47%  9.36%   4.29
OPT3 half->3 minvar        0.507   0.538  0.141   0.60  -27.96%  -1.28%   3.95%  8.41%   4.01
OPT3 half->3 MCA           0.769   0.829  0.230   1.23  -33.19%  -1.52%   7.62% 10.23%   4.97
```

Context (CPM-8 on FULL prod clean window 2008-05-30..): Sharpe 1.256, Calmar 1.008,
CAGR 13.13%, MaxDD -13.03%, turnover 3.55.

## Per-crisis + bull (total return %)

```
window                     C8 mv4  O3 mv4  O3 mv5  O3 mv6  O3 mca4 O3 mca5 O3 mca6 O3 h3-mv O3 h3-mca
Euro 2011-05..2011-10      -0.68%  -3.15%  -3.44%   1.34%   4.74%   0.71%  -0.13%  -0.58%   4.50%
Q4-2018                     0.53%   0.47%   0.42%   0.42%   0.50%   0.59%   0.45%   0.43%   0.50%
COVID 2020-02..2020-04      0.77%   0.45%   2.25%  -2.94%  -2.48%  -1.14%  -3.66% -20.81%  -26.90%
Bear 2022-01..2022-10      -0.33%  -4.38%  -1.54%  -1.79%  -5.47%  -2.43%  -2.50%  -1.83%   1.16%
Bull 2013-2017             50.06%  23.00%  27.67%  35.92%  20.84%  23.13%  35.84%  29.05%  29.14%
```

(GFC 2008-09 row excluded -- before the common start.)

## Answers

(a) Does richer universe improve CPM? NO -- it HURTS, large and consistently.
Best OPT3 (MCA k6) Sharpe 0.915 vs CPM-8 1.315; CAGR collapses 13.68% -> 6-8%;
Calmar 1.278 -> ~0.6. The factorial's "universe is dominant" referred to the
SPECIFIC curated CPM-8 (US-factor tilt QQQ/SPHQ + targeted diversifiers), NOT raw
global breadth. More raw breadth DILUTES momentum quality rather than adding it.
The bull window is the clearest tell: CPM-8 +50% vs OPT3 +21-36% (2013-2017).

(b) Data reality: all 15 usable, window shrink is minor (~8 months), so the
comparison is fair. BUT 6 of 15 are unstitched, non-PIT, possibly survivorship-
biased ETF pulls -- a real caveat that, if anything, FLATTERS OPT3. Even flattered,
OPT3 loses badly. Data availability is not the binding limitation; the universe
choice is.

(c) MCA vs min-var on the richer universe: MCA is marginally better at matched K
(k6: 0.915 vs 0.900; k5: 0.862 vs 0.852) and clearly better for half->3 (0.769 vs
0.507), consistent with MCA's natural fit for many correlated candidates -- but
MCA also runs higher MaxDD (k4 -16.0%, half3 -33.2%) and higher turnover. Neither
metric comes close to rescuing the richer universe.

(d) top-K sensitivity: monotonic improvement with K on the richer universe
(k4 < k5 < k6 for both metrics) -- more breadth recovers some lost ground, but
plateaus far below CPM-8. This is the opposite of prod's tuned top-K=4 optimum and
is itself evidence the richer universe needs MORE picks just to partially offset
its dilution.

(e) Verdict: NOT worth pursuing. A richer/global universe + (min-var or MCA) +
any cardinality underperforms CPM-8 on every risk-adjusted metric on the common
window. The Optimum3-faithful top-half->3 rule is the WORST (Sharpe 0.51-0.77,
MaxDD -28% to -33%, COVID -21% to -27%).

## Mechanism (why it fails)

1. Composition: global breadth replaces the US-factor tilt (QQQ/SPHQ) with
   lower-return intl/EM/REIT candidates -> structural CAGR drag.
2. Bonds-as-candidates + vol-adjusted ranker: the vol-adjustment inflates low-vol
   bond scores, pulling ~30% of book weight into IEF/TLT/TIP/BWX (vs ~17% TLT-only
   in CPM-8) -> further return drag at similar vol.
3. half->3 discards CPM's /4 breadth de-risking: with 15 candidates there are
   almost always >=3 positives, so half->3 stays fully invested in 3 risky names
   with no breadth-driven safe rotation -> catastrophic COVID drawdown (-21% to
   -27%). CPM's top-4 -> 3-of-4 with /4 breadth scaling de-risks far more often;
   that breadth mechanism is doing heavy lifting that half->3 throws away.

## Caveats / discipline

- HIGH OVERFIT CAUTION: universe + K + selection metric + cardinality = several
  DoF. This was an a-priori faithful Optimum3 port, NOT tuned -- and it still lost,
  which strengthens the negative conclusion (no cherry-picking could save it here).
- SHORT HISTORY / SURVIVORSHIP / PIT: 6 ETFs are unstitched cached yfinance pulls;
  no point-in-time membership guarantee. Caveat flagged prominently; it only biases
  in OPT3's favor, so the negative result is robust to it.
- Execution: lagged T+1 mooex, 10 bps/side; new tickers lack open-cache so a few
  rebalance days fall back to close-to-close overnight=0 (rare, immaterial to the
  large gaps observed).
- Cached-data caveat: frozen in-repo panel + /tmp ETF cache; eval cutoff 2026-05-22.
- Scope: sleeve only (blend SKIPPED per scope trim). No bootstrap/WF run.

## Flag for later

None compelling enough to warrant bootstrap/WF: every OPT3 config is dominated by
CPM-8 on the common window. The clean negative result is itself the deliverable --
richer/global universe does not help CPM; the curated CPM-8 tilt is the value.

## Reproduce

```
.venv/bin/python research/cpm_opt3_universe_run.py
# anchor check (clone == prod both-252):
.venv/bin/python -c "from research import cpm_harness as h; print(h.verify_anchor())"
```
Artifacts: `research/cpm_opt3_universe_harness.py`, `..._run.py`,
`..._results.json`, this file.
