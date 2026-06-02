# Memo Review-2 Robustness: A1 (Vol-Lookback Standardization) + A2 (US-Equity De-Tilt)

Status: research only. Does NOT edit `cpm_memo.md` or production. Not committed.
Harness: `research/memo_review2_A1_A2_harness.py` (reuses `cpm_live.compute_target_weights`
engine logic and the `exec_lag_moo_validation_2026_05_30` mooex T+1 MOO harness).
Run: `.venv/bin/python research/memo_review2_A1_A2_harness.py`
Artifacts: `research/memo_review2_A1_A2_findings.json` (raw metrics).

## 0. Anchor reproduction (gate)

Reproduced the production CPM clean anchor with the exact mooex T+1 MOO harness before
any robustness test:

| Metric | Target | Reproduced |
|---|---|---|
| Sharpe | 1.1910 | 1.1910 |
| MaxDD | -12.67% | -12.67% |
| Calmar | 1.0615 | 1.0615 |
| Martin | (n/a) | 3.9646 |

Anchor matches to 4 decimals. All A1/A2 results below run through the identical engine and
harness, changing only the lookback parameters (A1) or the risky universe (A2).

Windows: Clean = 2008-05-30 to 2026-05-22 (primary lens). Extended = 1999-03-10 to
2026-05-22 (robustness; proxy-backed pre-ETF segments, harness convention). Costs 10 bps/side.
Metrics are raw Sharpe (rf=0), MaxDD, Calmar, Martin, all post-cost.

---

## A1. Vol-Lookback Standardization

Production ranks on `faber / rv_252d` but inverse-vol WEIGHTS on `1/rv_504d` (252-vs-504
mismatch the review flags as a possible overfit signature). Test removes the mismatch by
standardizing both legs to the same lookback.

### A1 results

CLEAN window (2008-05-30 .. 2026-05-22):

| Config | Sharpe | dSharpe vs prod | CAGR | Vol | MaxDD | Calmar | Martin |
|---|---:|---:|---:|---:|---:|---:|---:|
| prod (rank252 / wt504) | 1.1910 | -- | 13.44% | 11.16% | -12.67% | 1.062 | 3.965 |
| both-252 (rank252 / wt252) | 1.1658 | -0.0252 | 13.15% | 11.18% | -12.97% | 1.014 | 3.691 |
| both-504 (rank504 / wt504) | 1.2039 | +0.0129 | 13.56% | 11.12% | -13.73% | 0.988 | 4.034 |

EXTENDED window (1999-03-10 .. 2026-05-22):

| Config | Sharpe | dSharpe vs prod | CAGR | MaxDD | Calmar | Martin |
|---|---:|---:|---:|---:|---:|---:|
| prod (rank252 / wt504) | 1.2142 | -- | 13.71% | -15.93% | 0.861 | 3.820 |
| both-252 (rank252 / wt252) | 1.2004 | -0.0138 | 13.48% | -15.73% | 0.857 | 3.676 |
| both-504 (rank504 / wt504) | 1.2194 | +0.0052 | 13.80% | -17.29% | 0.798 | 3.862 |

### A1 verdict: ROBUST PLATEAU (refutes the overfit charge)

- Production is NOT the Sharpe peak. both-504 has a HIGHER clean Sharpe (1.2039 > 1.1910)
  and higher Martin (4.034 > 3.965). If the mismatch were a Sharpe-tuned overfit, the
  standardized configs would degrade; instead one of them beats it on Sharpe.
- Sharpe band across all three configs is tiny: clean 1.1658-1.2039 (spread 0.038, ~3.2% of
  level); extended 1.2004-1.2194 (spread 0.019). Standardizing the lookback "barely changes"
  the risk-adjusted return -> plateau, not a tuned peak.
- Where production DOES win is drawdown control: it has the shallowest MaxDD (-12.67% vs
  -12.97% / -13.73% clean) and the highest Calmar (1.062 vs 1.014 / 0.988). The rank252/wt504
  mismatch is therefore selected on the DRAWDOWN axis, not the Sharpe axis. both-504 buys a
  little extra Sharpe but pays it back in a 1.06pp deeper MaxDD and a worse Calmar.
- Interpretation: the 252/504 mismatch is a mild capital-preservation tilt (the longer 504d
  weighting de-emphasizes recent vol spikes when sizing, slightly improving tail behavior),
  not evidence of curve-fitting. The cross-asset edge is invariant to the lookback choice.

Quantified delta: standardizing degrades clean Sharpe by at most 0.025 (-2.1%) and can even
improve it by +0.013; clean Calmar moves -0.05 to -0.07. This is a plateau. The "252-vs-504
mismatch = overfit signature" charge is REFUTED on Sharpe; production is best read as a
drawdown-optimal point on a flat Sharpe surface.

---

## A2. US-Equity De-Tilt

Review charge: the edge may be a US-large-cap-growth/quality-beta wrapper (LOO: QQQ -0.177,
SPHQ -0.157 Sharpe).

### A2 PRIMARY -- replace BOTH QQQ and SPHQ with a single plain SPY

Universe: SPY, EFA, EEM, VNQ, GLD, TLT, DBC (broad US equity, no tech/quality tilt; 7 assets).

| Series | Sharpe | CAGR | Vol | MaxDD | Calmar | Martin |
|---|---:|---:|---:|---:|---:|---:|
| Production (QQQ+SPHQ, clean) | 1.1910 | 13.44% | 11.16% | -12.67% | 1.062 | 3.965 |
| De-tilt SPY (clean) | 1.0122 | 10.62% | 10.57% | -11.75% | 0.903 | 2.547 |
| De-tilt SPY (ext) | 1.0993 | 11.53% | 10.42% | -13.45% | 0.857 | 2.881 |
| --- benchmarks (clean) --- | | | | | | |
| SPY buy-hold | 0.660 | 11.73% | -- | -50.70% | 0.231 | 1.060 |
| 60/40 SPY/IEF | 0.795 | 8.76% | -- | -29.78% | 0.294 | 1.405 |

Delta vs production (clean): Sharpe -0.179 (-15%), Calmar -0.159, CAGR -2.82pp, MaxDD actually
SHALLOWER (-11.75% vs -12.67%, +0.92pp better).

### A2 SECONDARY -- growth-engine specificity (single-ticker swaps)

Each swaps ONE of QQQ/SPHQ, keeping the other 7 production assets. Late-inception tickers
(QUAL 2013-07, MTUM 2013-04) start at first_valid+400d; their baseline is production restricted
to the same start (apples-to-apples). VUG/IWF/IWD have data from clean-window start.

| Swap | Eff. start | Sharpe | MaxDD | Calmar | Martin | prod baseline (same start) | dSharpe |
|---|---|---:|---:|---:|---:|---:|---:|
| QQQ->VUG | 2008-05-30 | 1.1573 | -14.04% | 0.920 | 3.652 | 1.1910 | -0.034 |
| QQQ->IWF | 2008-05-30 | 1.1547 | -14.10% | 0.910 | 3.666 | 1.1910 | -0.036 |
| QQQ->IWD (cyclical/value) | 2008-05-30 | 1.1028 | -12.20% | 0.987 | 2.981 | 1.1910 | -0.088 |
| SPHQ->QUAL | 2014-08-22 | 1.2941 | -12.95% | 1.080 | 4.135 | 1.2906 | +0.004 |
| SPHQ->MTUM | 2014-05-23 | 1.2677 | -13.42% | 1.068 | 3.842 | 1.3162 | -0.048 |

### A2 verdict: ROBUST CROSS-ASSET FRAMEWORK (edge survives de-tilting)

PRIMARY answer -- the cross-asset edge SURVIVES replacing QQQ+SPHQ with plain SPY:
- De-tilted-SPY CPM keeps Sharpe ~1.01, Calmar ~0.90, MaxDD -11.75% (clean). That is FAR above
  any passive benchmark on the same window: Sharpe +0.35 over 60/40 and +0.35 over SPY-buy-hold;
  Calmar ~3x (0.90 vs 0.23-0.29); MaxDD roughly a quarter of SPY buy-hold's -50.70%. It does
  NOT collapse toward the benchmark when the growth/quality tilt is removed.
- The preservation machinery (HYG-or-TIP canary, breadth-scaled partial-safe routing, top-4
  vol-adjusted momentum across the remaining 7 cross-asset sleeve, inverse-vol weighting) is
  intact and dominant. Drawdown control even IMPROVES slightly (-11.75% vs -12.67%) because SPY
  is lower-beta than QQQ.

Honest caveat -- the growth/quality tilt IS a real return enhancer, not free: it adds ~0.18
Sharpe and ~2.8pp CAGR (clean). So part of the headline return is US large-cap-growth/quality
beta (the LOO finding is directionally confirmed). But this is an enhancer layered on a robust
cross-asset core, not the source of the edge.

SECONDARY answer -- the edge is NOT QQQ/SPHQ-ticker-specific:
- Growth-engine swaps are near-interchangeable: QQQ->VUG (-0.034), QQQ->IWF (-0.036),
  SPHQ->QUAL (+0.004 on 2014+), SPHQ->MTUM (-0.048 on 2014+). Deltas are all within +/-0.05
  Sharpe. Any reasonable US large-growth / quality / momentum proxy plugged into the slot
  reproduces production within noise.
- Even a cyclical/value substitute (QQQ->IWD) keeps Sharpe ~1.10 and the shallowest MaxDD
  of the equity swaps (-12.20%); value costs ~0.09 Sharpe vs growth but preserves the
  drawdown profile. This rules out a tech-bubble / single-ticker overfit.

Bottom line: CPM is a robust cross-asset capital-preservation framework. Its return is
enhanced (~0.18 Sharpe) by a US large-cap-growth/quality tilt that is interchangeable across
growth proxies, but the strategy is NOT growth-beta-DEPENDENT: de-tilted to plain SPY it still
clears Sharpe ~1.0 / Calmar ~0.9 with -11.75% MaxDD, far above any passive benchmark.

---

## Caveats and confidence

- Single in-sample backtest per config; no walk-forward re-optimization of lookbacks/universe.
  Treat all configs as evaluated in-sample (same caveat the memo applies to production).
- A1 and A2-primary use the full clean window; A2-secondary QUAL/MTUM windows start 2014
  (post-inception+400d warmup) and are compared only against production restricted to the same
  start. Do not compare 2014-start swaps against the 2008-start anchor directly.
- Extended window = 1999-03-10 (harness convention, includes proxy-backed pre-ETF segments).
  A2-secondary extended not reported because VUG (2004), QUAL/MTUM (2013) lack pre-inception
  history; their clean/effective windows are the honest comparison.
- mooex T+1 MOO: real OHLC fetched for all swap tickers (VUG/IWF/QUAL/MTUM/IWD/SPY); the
  mooex override falls back to close-to-close only on the single monthly rebalance day where a
  ticker's open is unavailable (rare), identical to the production-harness fallback behavior.
- A2 clean window (2008+) uses live QQQ, so the de-tilt test is not contaminated by the
  pre-2008 NDX-index QQQ proxy in the base panel.
- Confidence: HIGH on the qualitative verdicts (plateau for A1; cross-asset survival for A2),
  which hold with comfortable margins. MEDIUM on the exact Sharpe-delta magnitudes given the
  single-sample / no-walk-forward limitation.

## Handoff

None required. Pure analysis. If production change is ever desired (e.g. adopt both-504 for
marginally higher Sharpe, or document the de-tilt robustness in the memo), route memo/prod
edits to the fixer; this analyst does not edit memo/prod.
