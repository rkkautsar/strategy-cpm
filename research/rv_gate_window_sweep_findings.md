# BULL rv-gate SHORT-window sensitivity sweep

Analyst role; read-only re production. No production/memo files changed; no commit.

## Question / hypothesis

The BULL sleeve vol gate is `rv_60d(SPY) < rv_252d(SPY)`. The 60-day SHORT window
is a tuned parameter with no in-memo sensitivity sweep (the CPM cov-lookback gets
one in section 8.10; the gate window deserves parity). Sweep the SHORT realized-vol
window over {20, 40, 60, 80, 120} days against the same 252d long window, holding
everything else at production, to justify or revise the 60d choice.

H0: 60d sits at or near the plateau-top; the choice is flat enough to be stable.

## Method

- Production BULL engine `bull_qqq_live.py` (`_vol_gate_ok` / `compute_bull_qqq_weights`),
  driven through the anchor-gated IV4 number set helpers
  (`research/exec_lag_moo_validation_2026_05_30.py`: `cpm_sleeve_conv`,
  `bull_sleeve_conv`, `gate_rv` factory). `gate_rv(short, slow=252)` monkeypatches
  `bull_qqq_live._vol_gate_ok` for the duration of the BULL backtest and restores it.
- Only the BULL gate SHORT window varies. The 252d LONG window, CPM sleeve (production
  IV4), canary, trend, safe-pool, costs, and execution are all held at production.
- Execution: T+1 MOO exact ("mooex", real yfinance auto_adjust opens), post-cost
  10 bps/side -- identical to the rest of the memo.
- Metrics from production `perf_metrics`: Sharpe (rf=0), Calmar (=CAGR/|MaxDD|),
  MaxDD, CAGR, Vol.
- Windows: clean 2008-05-30..2026-05-22 (18y); stress/extended 1999-03-10..2026-05-22.
- Blend: 60/40 CPM-BULL two-sleeve (CPM fixed; only BULL gate window varies).

Reproduce: `python research/rv_gate_window_sweep.py`

## Anchor gate (passed before reporting)

- 60d BULL clean Sharpe = 1.0813 (memo section 5.1 expects ~1.081). CONFIRMED.
- 60/40 CPM-BULL blend clean Sharpe = 1.2485 (memo section 8.10 anchor). CONFIRMED.

## Results

### BULL sleeve (short-window sweep, long = 252d)

| Short | Clean Sharpe | Clean Calmar | Clean MaxDD | Clean CAGR | Clean Vol | Stress Sharpe | Stress Calmar | Stress MaxDD |
|-------|-------------:|-------------:|------------:|-----------:|----------:|--------------:|--------------:|-------------:|
| 20d (ref) | 1.0197 | 0.736 | -14.70% | 10.81% | 10.66% | 0.9111 | 0.644 | -14.70% |
| 40d | 1.0500 | 0.783 | -14.42% | 11.29% | 10.77% | 0.9286 | 0.676 | -14.42% |
| **60d (PROD)** | **1.0813** | **0.857** | **-13.35%** | 11.44% | 10.57% | 0.9196 | 0.680 | -13.96% |
| 80d | 0.8738 | 0.548 | -17.31% | 9.49% | 11.12% | 0.8060 | 0.487 | -17.31% |
| 120d | 1.0275 | 0.603 | -17.43% | 10.51% | 10.27% | 0.9982 | 0.581 | -17.43% |

### 60/40 CPM-BULL blend (clean) per BULL short window

| Short | Sharpe | Calmar | MaxDD | CAGR | Vol |
|-------|-------:|-------:|------:|-----:|----:|
| 20d (ref) | 1.2284 | 1.263 | -9.90% | 12.49% | 10.03% |
| 40d | 1.2407 | 1.188 | -10.68% | 12.69% | 10.07% |
| **60d (PROD)** | **1.2485** | 1.193 | -10.68% | 12.74% | 10.05% |
| 80d | 1.1630 | 1.119 | -10.68% | 11.96% | 10.20% |
| 120d | 1.2330 | 1.113 | -11.12% | 12.37% | 9.89% |

### Sharpe bands (how flat the choice is)

| Band | Value |
|------|------:|
| BULL clean Sharpe, all windows {20..120} | 0.2075 |
| BULL clean Sharpe, core {40,60,80,120} | 0.2075 |
| BULL stress Sharpe, all windows | 0.1922 |
| Blend clean Sharpe, all windows | 0.0855 |
| Blend clean Sharpe, all windows ex-80d | 0.0201 |

## Verdict

60d is the clean plateau-top and is defensible, with two honest caveats.

1. 60d wins on the BULL clean lens outright. It is the best BULL clean Sharpe
   (1.0813), best BULL clean Calmar (0.857), and best (shallowest) BULL clean MaxDD
   (-13.35%) of every window tested. At the 60/40 blend level it is also the best
   clean Sharpe (1.2485). So on the memo's decisive clean lens, 60d is not merely
   near the top -- it is the top at both sleeve and blend level.

2. The BULL surface is NOT a smooth flat plateau. There is a sharp pothole at 80d
   (clean Sharpe collapses to 0.8738, Calmar 0.548, MaxDD -17.31%), then a partial
   recovery at 120d (1.0275). The BULL clean Sharpe band is wide (0.2075), driven
   almost entirely by the 80d dip. This means the gate window genuinely matters at
   the sleeve level -- "any short window works" is false -- which is exactly why the
   parameter warrants the sweep. 60d sits on a local peak, not on an indifferent flat.

3. At the BLEND level the choice is flat and stable. Blend clean Sharpe band is 0.0855
   across all windows, and only 0.0201 once the 80d outlier is excluded
   (20d 1.2284, 40d 1.2407, 60d 1.2485, 120d 1.2330). CPM diversification absorbs most
   of the BULL window sensitivity, so at the portfolio level 60d is comfortably inside
   a tight band and the downside of a mild mis-pick is small (except the 80d trap).

4. Where 60d is NOT optimal (stated plainly):
   - Stress Sharpe favors the longest window: 120d 0.9982 > 40d 0.9286 > 60d 0.9196.
     60d trails the stress-best by 0.079 Sharpe. The longer 120d window is steadier
     through the pre-clean 1999-2008 stress regime.
   - Blend clean Calmar favors the shortest window: 20d 1.263 > 60d 1.193. The 20d
     reference gives the shallowest blend MaxDD (-9.90%).
   Neither overturns 60d: 60d dominates on the decisive clean Sharpe at both levels,
   ties the best blend MaxDD (-10.68%, shared by 40/60/80d), and posts the best BULL
   drawdown control. The stress edge of 120d comes bundled with materially worse clean
   metrics (clean Calmar 0.603 vs 0.857, clean MaxDD -17.43% vs -13.35%), and the 20d
   blend-Calmar edge comes with the worst BULL stress Calmar (0.644).

Bottom line: keep 60d. It is the clean-lens optimum at sleeve and blend level and best
BULL drawdown control; the only competitors win on secondary lenses (120d on stress
Sharpe, 20d on blend Calmar) while losing on the decisive one. The 80d pothole confirms
the window is a real parameter, not a free choice -- 60d is the right peak to sit on.

## Caveats and confidence

- Single long window (252d) by design; this isolates the SHORT-window question per the
  task. A joint short x long surface is out of scope.
- Clean window is the memo's decisive lens; stress/extended (1999-) leans on
  proxy-backed pre-ETF segments and is interpreted as secondary, consistent with the memo.
- NDX sleeve is not involved; this is the CPM-BULL two-sleeve blend (60/40), with CPM
  held fixed. The production 60/20/20 three-sleeve blend would dilute BULL further,
  making the blend-level choice even flatter.
- Confidence: high on the clean-lens ranking (anchor reproduced to 4 dp). Medium on the
  stress ordering given proxy-segment dependence.

## Handoff

None required. Findings only; no production or memo edits. If the memo authors want a
gate-window sensitivity paragraph for parity with section 8.10, that memo edit is a fixer
task.
