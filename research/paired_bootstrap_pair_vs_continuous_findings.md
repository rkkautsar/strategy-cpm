# Paired bootstrap: continuous min-var vs 50/50 EW pair (CPM sleeve)

**Question.** Is "continuous minimum-variance beats the equal-weight 50/50 pair"
statistically robust, or within noise? Quantified with a **paired** stationary
block bootstrap: P(continuous beats pair) on Sharpe, MaxDD, Calmar, plus the
bootstrap distribution of the per-metric difference (continuous - pair), on both
the clean 18y and extended 27y windows.

## Config / window / execution / method

| Item | Value |
|---|---|
| Schemes | Same CPM selection (U=R=C=1), differing ONLY in weighting step: P=1 50/50 min-var pair (production) vs P=0 continuous min-var over survivors |
| Execution | T+1 MOO exact (`mooex`), 10 bps/side, cov lookback 504d |
| Windows | CLEAN 18y (2008-05-30 .. 2026-05-22), EXT 27y (1999-03-10 .. 2026-05-22) |
| Bootstrap | Stationary block bootstrap, B=2000, block=21 days, seed=42 (matches `bootstrap_ci_2026_05_28.py`) |
| Method (headline) | PAIRED: the SAME resampled block index applied to BOTH series each iteration (joint resampling preserving the daily pairing) |
| Method (contrast) | NAIVE: the two series resampled with INDEPENDENT block indices |
| Sign convention | Difference = continuous - pair. Sharpe/Calmar: >0 = continuous better. MaxDD: both negative, >0 = continuous shallower (better) |
| Script | `research/paired_bootstrap_pair_vs_continuous.py` -> `.json` |
| Source series | `research/pair_vs_continuous_minvar.py` (`returns_for`, `_segment_returns_conv`, `perf_metrics`) |

## Verify: full-sample point metrics reproduce anchors (10 bps)

| Window | Scheme | Sharpe | Calmar | MaxDD | Anchor |
|---|---|---|---|---|---|
| CLEAN | pair 50/50 | **1.2424** | **0.8704** | **-16.35%** | 1.2424/0.8704/-16.35% OK |
| CLEAN | continuous | **1.2935** | **0.9618** | **-15.15%** | 1.2935/0.9618/-15.15% OK |
| EXT | pair 50/50 | 1.1640 | 0.8322 | -16.76% | (no anchor) |
| EXT | continuous | 1.2091 | 0.8760 | -15.15% | (no anchor) |

Clean anchors reproduce to 4 dp before bootstrapping. Continuous's point edge:
+0.051 Sharpe / +1.20pp shallower MaxDD / +0.091 Calmar (clean);
+0.045 Sharpe / +1.61pp MaxDD / +0.044 Calmar (ext). Directionally favors
continuous on all metrics, both windows.

Daily-return correlation of the two schemes: **0.937 (clean), 0.894 (ext)** -- very
high, exactly why pairing matters.

## 1-3. Win probabilities P(continuous beats pair) across B=2000 resamples

### PAIRED (headline)

| Window | P(Sharpe) | P(MaxDD shallower) | P(Calmar) |
|---|---|---|---|
| CLEAN | **0.7430** | **0.6205** | **0.6540** |
| EXT | **0.7035** | **0.7140** | **0.5705** |

### NAIVE independent (contrast)

| Window | P(Sharpe) | P(MaxDD shallower) | P(Calmar) |
|---|---|---|---|
| CLEAN | 0.5765 | 0.5440 | 0.5450 |
| EXT | 0.5740 | 0.6075 | 0.5310 |

## 4. Bootstrap distribution of the difference (continuous - pair)

### PAIRED

| Window | Metric | mean | 95% CI | CI excludes 0? |
|---|---|---|---|---|
| CLEAN | Sharpe | +0.0508 | [-0.1041, +0.2160] | No |
| CLEAN | MaxDD | +0.0061 | [-0.0484, +0.0611] | No |
| CLEAN | Calmar | +0.0584 | [-0.2943, +0.4175] | No |
| EXT | Sharpe | +0.0468 | [-0.1214, +0.2202] | No |
| EXT | MaxDD | +0.0164 | [-0.0447, +0.0854] | No |
| EXT | Calmar | +0.0260 | [-0.2590, +0.3119] | No |

### NAIVE independent

| Window | Metric | mean | 95% CI | CI excludes 0? |
|---|---|---|---|---|
| CLEAN | Sharpe | +0.0516 | [-0.5212, +0.6089] | No |
| CLEAN | MaxDD | +0.0056 | [-0.0997, +0.1057] | No |
| CLEAN | Calmar | +0.0561 | [-0.7145, +0.8794] | No |
| EXT | Sharpe | +0.0475 | [-0.4484, +0.5593] | No |
| EXT | MaxDD | +0.0165 | [-0.0955, +0.1466] | No |
| EXT | Calmar | +0.0268 | [-0.6222, +0.6686] | No |

**Pairing matters a lot.** The difference *mean* is essentially identical between
paired and naive (the point edge is unchanged), but the *spread* collapses under
pairing because the shared market shocks cancel in the difference:

- Sharpe-diff 95% CI width: clean 0.324 (paired) vs 1.130 (naive) -- ~3.5x tighter;
  ext 0.342 vs 1.008 -- ~3x tighter.
- MaxDD-diff 95% CI width: clean 0.110 vs 0.205; ext 0.130 vs 0.242 -- ~2x tighter.
- Calmar-diff 95% CI width: clean 0.712 vs 1.594; ext 0.571 vs 1.310 -- ~2.2x tighter.

Naive independent bootstrap inflates difference variance ~2-3.5x, dragging the
win probabilities toward 0.5 (pure noise) and hiding the real, consistent
directional tilt. The paired design is the correct one for two variants of the
same selection.

## 5. Verdict: is continuous's edge statistically robust?

**No -- the edge is real in direction but NOT statistically robust at the 95%
bar on any metric or window. It is "better than a coin flip, within noise."**

- No difference CI (paired or naive) excludes zero on any metric/window.
- Under the correct PAIRED test, continuous wins **70-74% of resamples on Sharpe**,
  57-71% on MaxDD, 57-65% on Calmar. That is a consistent, repeatable lean toward
  continuous (well above 50/50) -- but short of the P>0.95 robustness threshold.
- Strongest single signal: paired Sharpe, both windows (~0.70-0.74) and paired
  MaxDD on EXT (0.714). Weakest: Calmar on EXT (0.57, near coin-flip).
- Interpretation: continuous min-var is **modestly and consistently favored**
  (point edge ~+0.05 Sharpe, ~+1.2-1.6pp shallower MaxDD), enough to justify a
  mild preference, but the historical sample cannot reject the hypothesis that the
  two weightings are equivalent. The 50/50 pair's simplicity/robustness is not
  statistically dominated.

## Caveats / confidence

- Single historical path; block bootstrap captures monthly-rebalance autocorr but
  not regime non-stationarity. Same data, same selection logic -> differences are
  purely the weighting step, as intended.
- MaxDD on a block-resampled path reorders 21d blocks, so the resampled drawdown
  is a path statistic on a shuffled history, not the literal realized DD; valid as
  a relative (paired) comparison, less so as an absolute MaxDD estimate.
- Confidence: HIGH that anchors reproduce and that pairing shrinks difference
  variance ~2-3.5x; HIGH that no metric clears P>0.95; MEDIUM-HIGH that continuous
  carries a genuine small directional edge (consistent across 6 of 6 metric/window
  cells, all means >0, win-prob >0.5 in all).

## Reproduce

```
.venv/bin/python research/paired_bootstrap_pair_vs_continuous.py
```

Outputs `research/paired_bootstrap_pair_vs_continuous.json`. No production files
touched, no commit.
