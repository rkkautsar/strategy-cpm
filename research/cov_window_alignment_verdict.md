# Covariance Window-Alignment Verdict: continuous min-var vs 50/50 pair

**Question (decisive):** Is continuous min-var's Sharpe edge over the 50/50 equal-weight
pair LEGITIMATE, or a one-bar covariance/return OVERLAP artifact (lookahead)?

**Verdict:** LEGITIMATE. The min-var covariance window is strictly trailing and
disjoint from the first earned return bar in BOTH the production engine and the
research harness. There is no one-bar overlap. A minimal one-trading-bar
de-overlap leaves continuous's Sharpe essentially unchanged (CLEAN 1.2935 ->
1.2928, -0.0007); ~85% of the +0.051 clean edge survives, and the small shrink
is driven by the PAIR rising, not continuous falling. Continuous is the
covariance-timing-stable scheme; the 50/50 pair is the noisier one.

Convention throughout: T+1 MOO exact (`mooex`), 10 bps/side, CLEAN 18y
(2008-05-30..2026-05-22) and EXT 27y (1999-03-10..). No codenames, no
same-day/MOC headline numbers, no approximations.

---

## Part 1 -- Code-level window-alignment verification (with file:line cites)

### 1a. On what return window is the min-var covariance computed at signal date `sig_d`?

**Production (`cpm_live.py`):**
- Risk-on weights selected via `min_vol_pair(close_panel.loc[:sig_d, candidates], candidates, CORR_LOOKBACK_DAYS)` -- `cpm_live.py:454-455`. The close panel is sliced `.loc[:sig_d]` (INCLUSIVE of `sig_d`).
- Inside `min_vol_pair`: `rets = daily[candidates].pct_change().dropna(how="all").tail(lookback)` then `cov = rets.cov()` -- `cpm_live.py:313,316`. `daily` here is the close panel passed in; `.pct_change()` makes the LAST return in the window the return realized ON `sig_d`, i.e. `close[sig_d]/close[sig_d-1] - 1` = the bar `[sig_d-1, sig_d]`.
- `CORR_LOOKBACK_DAYS = 504` (~2y) -- `cpm_live.py:64`.

**Research harness -- 50/50 pair vs continuous (`research/pair_vs_continuous_minvar.py`, `cpm_wf_lb`):**
- Pair (P=1): `pick = min_vol_pair(close.loc[:sig_d, positive], positive, lookback)` -- `pair_vs_continuous_minvar.py:89` (inclusive of `sig_d`).
- Continuous (P=0): `cov = daily.loc[:sig_d].tail(lookback)[positive].cov() * 252` -- `pair_vs_continuous_minvar.py:94`. `daily = close.ffill().pct_change()`, so `daily.loc[:sig_d]` last row is the `[sig_d-1, sig_d]` return. INCLUSIVE of `sig_d`'s own return.

**Lag harness (`research/cov_lookahead_check.py`, `cpm_wf_lag`):** identical except the window ends at a parametric `cov_d <= sig_d`: pair `close.loc[:cov_d, positive]` -- line 95; continuous `daily.loc[:cov_d].tail(lookback)[positive].cov()` -- line 100. `cov_d == sig_d` reproduces the lag0 baseline.

**Answer:** Covariance is computed on trailing daily returns up to and INCLUSIVE of
`sig_d`'s OWN return. The last bar in the cov window is `[sig_d-1, sig_d]` (the
return fully realized at `sig_d`'s close, the rebalance decision point). All
selection inputs (canary, ranker, vol, survivor set) are likewise `.loc[:sig_d]`.

### 1b. What is the FIRST bar the newly-applied weights earn?

**Production (`cpm_live.py`, `run` backtest):** `future = close.index[close.index > sig_d]; apply_from = future[0]` -- `cpm_live.py:528,531` (first trading day STRICTLY AFTER `sig_d`). Weights applied on `mask = (index >= apply_from) & (index < end_apply)` -- `cpm_live.py:550`; returns `(df_w * close.ffill().pct_change()).sum()` -- `cpm_live.py:559-561`. So the new weights' first earned bar = `close[apply_from]/close[sig_d] - 1` = the bar `[sig_d, apply_from]` (T+0 MOC accounting; docstring `cpm_live.py:511-514` confirms it assigns the `sig_d -> apply_from` overnight gap to the NEW vector).

**Research harness (`mooex`, `research/exec_lag_moo_validation_2026_05_30.py`, `_segment_returns_conv`):** `exec_lag = 0` for mooex (`:91`); `apply_from = fut[exec_lag]` = first bar > `sig_d` (`:96-100`). On the rebal day `af`, the close-to-close return is OVERRIDDEN: old weights earn the overnight `open[af]/close[sig_d]-1` (`:169-173`), and the NEW weights earn the INTRADAY `close[af]/open[af]-1` (`:178-180`). So under the headline mooex convention the new weights' first earned period is `[open(af), close(af)]`, where `af = sig_d + 1` trading bar.

**Answer:** First earned bar is STRICTLY AFTER `sig_d`'s close. Production: `[sig_d, af]`. Research mooex: `[open(af), close(af)]` (af = first bar > sig_d).

### 1c. Does the covariance window OVERLAP the first earned return bar?

NO. The cov window's last bar `[sig_d-1, sig_d]` and the first earned bar are disjoint:

| Convention | cov window last bar | new-weights first earned bar | Relationship |
|---|---|---|---|
| Production (cpm_live T+0 MOC) | `[sig_d-1, sig_d]` | `[sig_d, af]` | adjacent, share only the price point `close[sig_d]`; NO overlapping return period |
| Research mooex (headline) | `[sig_d-1, sig_d]` | `[open(af), close(af)]` | disjoint with a gap (the overnight `[sig_d, open(af)]` is earned by the OLD basket, not the new) |

The covariance is STRICTLY TRAILING. Including `sig_d`'s own return is NOT lookahead:
that return is fully known at `sig_d`'s close (the decision point), and the position
earns only AFTER `sig_d`'s close. There is no one-bar covariance/return overlap to
correct.

---

## Part 2 -- Interpreting the existing lag test (`research/cov_lookahead_check.json`)

The lag test steps the cov window back by whole MONTHLY rebalances (lag1 = prior
rebalance date, a FULL month of staleness -- NOT one bar). CLEAN Sharpes:

| scheme | lag0 | lag1 | lag2 | lag3 |
|---|---|---|---|---|
| continuous_minvar | 1.2935 | 1.2790 | 1.2727 | 1.2702 |
| pair_5050 | 1.2424 | 1.2916 | 1.2955 | 1.2700 |
| edge (cont - pair) dSharpe | +0.0511 | -0.0126 | -0.0228 | +0.0002 |

Reading:
- **Continuous is the cov-timing-STABLE scheme.** Its Sharpe decays smoothly and
  monotonically with staleness (1.2935 -> 1.2790 -> 1.2727 -> 1.2702): freshest
  trailing cov is best; older cov is worse. This is the signature of an estimate
  that simply benefits from recent data -- NOT of a lookahead artifact (a true
  one-bar leak would show a CLIFF the moment the overlapping bar is removed).
- **The pair is the NOISY scheme.** Its Sharpe is non-monotone and jumps
  (1.2424 -> 1.2916 -> 1.2955 -> 1.2700). Rank-based pair SELECTION flips on small
  cov perturbations; lag0 (1.2424) happens to be a local LOW point.
- **The lag0->lag1 edge "reversal" (+0.051 -> -0.013, a 0.064 swing) is driven
  ~entirely by the PAIR jumping +0.049** (1.2424 -> 1.2916), while continuous falls
  only -0.0145. So the reversal is pair-selection noise, not continuous overlap.

EXT shows the same pattern (continuous monotone 1.2091->1.1825->1.1743->1.1685;
pair noisy 1.1640->1.2235->1.1745->1.1680).

This is consistent with Part 1: there is no overlap, so lag1+ does not "remove a
leak" -- it just feeds continuous a needlessly month-stale covariance and reshuffles
the pair's rank-selection lottery.

---

## Part 3 -- Minimal one-bar de-overlap (the clean fix, NOT a full month lag)

Run: `research/cov_window_minus1bar_check.py` -> `cov_window_minus1bar_check.json`.
Shift the cov window back EXACTLY ONE TRADING BAR (`cov_d` = trading bar immediately
before `sig_d`), strictly excluding `sig_d`'s own (already non-overlapping) return.
Everything else identical (universe/canary/ranker/safe/survivor all still as-of
`sig_d`). mooex, 10 bps.

| window | align | pair Sh | cont Sh | edge dSh | cont MaxDD% | edge dCalmar |
|---|---|---|---|---|---|---|
| CLEAN | lag0 (incl sig_d) | 1.2424 | 1.2935 | +0.0511 | -15.15 | +0.0914 |
| CLEAN | minus1bar (excl sig_d) | 1.2495 | 1.2928 | +0.0433 | -15.19 | +0.0827 |
| EXT | lag0 (incl sig_d) | 1.1640 | 1.2091 | +0.0451 | -15.15 | +0.0438 |
| EXT | minus1bar (excl sig_d) | 1.1686 | 1.2080 | +0.0394 | -15.19 | +0.0370 |

Findings:
- **Continuous Sharpe is essentially UNCHANGED** by removing `sig_d`'s own return:
  CLEAN 1.2935 -> 1.2928 (-0.0007, -0.05%); EXT 1.2091 -> 1.2080 (-0.0011). If the
  edge were a one-bar overlap artifact, continuous would COLLAPSE here. It does not.
- **The edge survives:** CLEAN +0.0511 -> +0.0433 (84.7% retained); EXT +0.0451 ->
  +0.0394 (87.4% retained). Calmar edge survives too (+0.0914 -> +0.0827 CLEAN).
- **The small edge shrink is driven by the PAIR RISING, not continuous falling:**
  pair CLEAN 1.2424 -> 1.2495 (+0.0071), EXT 1.1640 -> 1.1686 (+0.0046). Confirms
  the pair's lag0 was a local low (Part 2), not that continuous was inflated.

Continuous staleness curve, one place (CLEAN), shows a smooth monotone decay with
NO cliff at the de-overlap step:

```
incl sig_d (lag0)   : 1.2935
excl sig_d (-1 bar) : 1.2928   (-0.0007  <- the de-overlap step: negligible)
-1 month (lag1)     : 1.2790   (-0.0145)
-2 month (lag2)     : 1.2727
-3 month (lag3)     : 1.2702
```

A lookahead artifact removed at the -1 bar step would drop sharply there; instead the
loss is negligible and accumulates only with genuine staleness.

---

## Part 4 -- Verdict and quantification

- **Continuous min-var's edge is LEGITIMATE, not a one-bar-overlap artifact.** The
  covariance window is strictly trailing/disjoint from the first earned bar in both
  production (`cpm_live.py:454-455,528,531,559-561`) and the research harness
  (`pair_vs_continuous_minvar.py:94`, `exec_lag_moo_validation_2026_05_30.py:96-100,178-180`).
- **How much of the +0.05 clean Sharpe edge survives a strictly-clean alignment:**
  84.7% (CLEAN +0.0511 -> +0.0433) and 87.4% (EXT +0.0451 -> +0.0394). The lost
  fraction comes from the pair rising, not continuous falling -- continuous moves
  -0.0007/-0.0011.
- **Which scheme is more covariance-timing-robust:** CONTINUOUS. Its Sharpe is
  smooth and monotone in cov freshness (de-overlap -0.0007; staleness costs
  accumulate gradually). The 50/50 PAIR is the timing-noisy scheme -- its
  rank-selection flips on small cov perturbations (lag0->lag1 +0.049 jump), and its
  lag0 was a local low that made the headline edge look slightly larger than its
  de-overlapped value.
- **lag1+ degradation is NOT evidence of overlap;** it is continuous using a
  needlessly month-stale covariance. Live trading uses the freshest trailing cov
  (as-of `sig_d`), which is exactly the correct, leak-free choice (cov known at
  decision close, earns after).

### Files / commands
- Audited (read-only, unchanged): `cpm_live.py`, `research/pair_vs_continuous_minvar.py`, `research/exec_lag_moo_validation_2026_05_30.py`, `research/cov_lookahead_check.py`, `research/cov_lookahead_check.json`.
- New throwaway (research/ only): `research/cov_window_minus1bar_check.py` (+ `.json`).
- Run: `.venv/bin/python research/cov_window_minus1bar_check.py`

### Caveats / confidence
- HIGH confidence on the code-level alignment claim (direct file:line; both prod and harness inclusive `.loc[:sig_d]` cov, first earned bar strictly after `sig_d`).
- HIGH confidence the lag0 continuous edge is not overlap-inflated (one-bar de-overlap moves continuous by -0.0007/-0.0011 and the edge retains ~85%).
- Single fixed cov lookback (504d) and one cost level (10 bps); the de-overlap test was run only at mooex. The lag test already shows the same qualitative shape at EXT. No same-day/MOC headline used. No production files changed; no commit.
