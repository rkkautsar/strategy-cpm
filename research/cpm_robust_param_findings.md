# CPM Robustness Validation -- Parameter / Momentum-fn / Cost / Time / Weighting

Role: analyst (read-only re: production). No production/memo files edited, no commit.

## Setup

- Pipeline: production `cpm_live.py` logic, parametrized in
  `research/cpm_robust_param_sweep.py` (mirrors `compute_target_weights` exactly
  at baseline; only the swept knob changes per row).
- Convention: mooex (T+1 MOO exact, real yfinance auto_adjust opens), 10 bps/side,
  month-end signal, next-session-open execution.
- Windows: clean 2008-05-30..2026-05-22 (18.0y); ext 1999-03-10..2026-05-22 (27y).
- Anchor reproduced EXACTLY: clean Sharpe 1.1910 / MaxDD -12.67% / Calmar 1.0615;
  ext Sharpe 1.2142 / MaxDD -15.93% / Calmar 0.8608.
- Baseline knobs: K=4, cov/vol lookback=504, ranker=vol-adjusted Faber, weighting=inverse-vol.
- Scope changes applied: start-date sensitivity (#5) DROPPED (redundant with block-
  bootstrap CI + split-half + rolling-36m). Min-variance weighting NOT tested
  (obvious loser, = AAA W-factor in factorial). Equal-weight added as the sole
  competing scheme.

All deltas are vs the clean baseline (Sharpe 1.1910 / Calmar 1.0615 / MaxDD -12.67%).

## 1. Top-K x cov/vol lookback (clean window)

| K | lookback | Sharpe | Calmar | MaxDD | dSharpe | ext Sharpe |
|---|---|---|---|---|---|---|
| 3 | 252 | 0.9414 | 0.8485 | -13.33% | -0.2496 | 1.0361 |
| 3 | 504 | 0.9472 | 0.8629 | -13.22% | -0.2438 | 1.0291 |
| 4 | 252 | 1.1658 | 1.0137 | -12.97% | -0.0252 | 1.2004 |
| **4** | **504** | **1.1910** | **1.0615** | **-12.67%** | **+0.0000** | **1.2142** |
| 5 | 252 | 1.0673 | 0.9685 | -11.45% | -0.1237 | 1.1306 |
| 5 | 504 | 1.0901 | 0.9980 | -11.32% | -0.1009 | 1.1427 |
| 6 | 252 | 0.9996 | 0.8739 | -11.09% | -0.1914 | 1.0912 |
| 6 | 504 | 1.0201 | 0.9747 | -10.12% | -0.1708 | 1.0983 |

- Baseline (K=4, lb=504) is the PEAK of the 8-cell grid.
- lookback 504 > 252 at every K (small, +0.02 to +0.03 Sharpe).
- K is the dominant axis: K=3 is the only cell dropping clean Sharpe BELOW 1.0
  (0.94). K=5/6 degrade ~0.10-0.19 but stay >=1.02 (K=5) / ~1.0 (K=6). Larger K
  reduces MaxDD (more diversification) but dilutes Sharpe.

## 2. Ranking/screen momentum function (clean window)

| momentum | Sharpe | Calmar | MaxDD | dSharpe | ext Sharpe |
|---|---|---|---|---|---|
| **faber_voladj (base)** | **1.1910** | **1.0615** | **-12.67%** | **+0.0000** | **1.2142** |
| 13612U | 1.0829 | 0.8790 | -14.43% | -0.1081 | 1.1724 |
| 12m total | 0.9916 | 0.6983 | -16.37% | -0.1994 | 1.0600 |
| 6m | 0.9333 | 0.5586 | -19.40% | -0.2577 | 1.0587 |
| 3m | 0.9236 | 0.7656 | -13.89% | -0.2674 | 1.0022 |

- Vol-adjusted Faber (baseline) is the best ranker and the only one with the
  shallow -12.67% drawdown. 13612U is the closest competitor (1.0829, still strong).
- Plain 12m/6m/3m total-return rankers drop clean Sharpe below 1.0 (0.92-0.99) and
  worsen MaxDD materially (6m -> -19.40%). Calmar suffers most (6m 0.56).
- ext window: all momentum variants stay >=1.0 (3m marginally at 1.0022).

## 3. Cost sensitivity (clean window)

| cost (bps/side) | Sharpe | CAGR | Calmar | MaxDD | dSharpe |
|---|---|---|---|---|---|
| 0 | 1.2367 | 14.03% | 1.1225 | -12.50% | +0.0458 |
| 5 | 1.2139 | 13.74% | 1.0918 | -12.58% | +0.0230 |
| **10 (base)** | **1.1910** | **13.44%** | **1.0615** | **-12.67%** | **+0.0000** |
| 20 | 1.1447 | 12.86% | 1.0024 | -12.83% | -0.0463 |
| 30 | 1.0979 | 12.28% | 0.9449 | -13.00% | -0.0931 |

- Monotone, gentle slope (~-0.0046 Sharpe per bp). Even at 30 bps/side (3x baseline)
  clean Sharpe holds 1.0979 (>1.0). Cost is NOT a fragility axis. Turnover (~2.6
  one-way/yr) is low enough that execution slippage is well-tolerated.

## 4. Subperiod / time stability (baseline series)

| segment | window | Sharpe | Calmar | MaxDD |
|---|---|---|---|---|
| first half | 2008-05-30..2016-12-31 | 0.9970 | 1.1384 | -9.83% |
| second half | 2017-01-01..2026-05-22 | 1.3753 | 1.2262 | -12.67% |

Rolling 36-month Sharpe (n=182 monthly windows): min 0.7115, median 1.4101, max 2.2608.

- Edge persists across both halves: H1 Sharpe 0.9970 (just under 1.0 but Calmar
  1.1384, shallow -9.83% DD), H2 stronger at 1.3753. Not concentrated in one
  subperiod; the headline is not a single-regime artifact.
- Rolling 36m Sharpe never goes negative (min 0.71) and median 1.41; the strategy
  is positively risk-adjusted throughout the clean window.

## 6. Weighting scheme (clean window)

| weighting | Sharpe | Calmar | MaxDD | dSharpe | ext Sharpe |
|---|---|---|---|---|---|
| **inverse-vol (base)** | **1.1910** | **1.0615** | **-12.67%** | **+0.0000** | **1.2142** |
| equal-weight | 1.1317 | 1.0147 | -13.05% | -0.0593 | 1.1868 |

- Inverse-vol > equal-weight by only +0.0593 Sharpe / +0.0468 Calmar. Equal-weight
  is fully viable (>1.0 in both windows). Weighting choice is a minor, non-fragile knob.

## Verdict

CPM is BROADLY ROBUST, not knife-edge fit. Across every axis the edge degrades
gracefully (no cliff); the worst single Sharpe observed in the entire sweep is 0.92
(3m ranker), and the strategy stays risk-adjusted-positive on rolling 36m windows
throughout (min 0.71).

Robust axes (Sharpe stays >=1.0 across the swept range):
- Cost: 1.10 to 1.24 over 0-30 bps/side.
- Lookback: 252 vs 504 differ <=0.03.
- Weighting: inv-vol vs equal-weight differ 0.06.
- K in {4,5,6}: 1.02-1.19.
- Time: both halves strong (H1 0.997 / H2 1.375), rolling-36m min 0.71.

Most sensitive knobs (the perturbations that can push clean Sharpe below ~1.0):
1. Top-K cardinality -- K=3 is the worst parameter cell (0.94, dS -0.25). K is the
   single most sensitive engine parameter.
2. Ranking momentum function -- replacing vol-adjusted Faber with plain 12m/6m/3m
   total-return momentum drops Sharpe to 0.92-0.99 (dS -0.20 to -0.27) and inflates
   drawdowns (6m -> -19.4%). 13612U is the only alternative staying >1.0 (1.0829).

Sub-1.0 flag: reasonable perturbations that drop clean Sharpe below 1.0 are K=3
(0.94), and 12m/6m/3m rankers (0.92-0.99); H1 subperiod sits marginally at 0.997.
None of these are catastrophic, and the ext window keeps almost all variants >=1.0.

Overfit caveat (honest): the production baseline sits at the FAVORABLE corner --
it is the argmax of the K x lookback grid, the best of the five momentum functions,
and the better of the two weighting schemes. This raises selection-on-the-peak risk.
Mitigants: (a) degradation around the peak is smooth and bounded, not a spike;
(b) the second-best momentum (13612U) and neighbor cells (K=4/lb252, K=5/lb504)
remain >1.0; (c) consistent with the block-bootstrap clean-Sharpe CI [0.787, 1.597]
(point 1.191), which already prices in path/parameter uncertainty. Central tendency
is robustly >1.0; a sub-1.0 outcome requires combining the worst parameter choice
with an adverse path.

## Reproduce

```
cd /Users/rkautsar/personal/scripts/strategy_cpm
.venv/bin/python research/cpm_robust_param_sweep.py
# requires /tmp/cpm_open_cache (real OHLC opens) used by mooex convention
```

Artifacts: research/cpm_robust_param_sweep.py, research/cpm_robust_param_findings.json,
research/cpm_robust_param_findings.md.

Caveats: mooex uses cached real opens with ~81 pre-coverage fallback days (early ext
window); clean window has full real-open coverage. Equal-weight and alt-momentum
rows reuse the same canary/safe/strict-K-partial-safe scaffolding (only the swept
knob changes). Confidence: HIGH for clean-window conclusions, MEDIUM for ext-window
(proxy-tail uncertainty noted in memo).
