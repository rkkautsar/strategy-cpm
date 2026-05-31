# CPM lookahead / execution-realism battery (CPM sleeve)

Date: 2026-05-31
Role: analyst (read-only). No production or memo file changed. No commit.
Harness: `research/cpm_robust_lookahead.py` (reuses cpm_live.py signal/weight fns
UNCHANGED; varies only execution timing). Real yfinance auto_adjust opens from
`/tmp/cpm_open_cache/`.
Artifacts: this file + `research/cpm_robust_lookahead_findings.json`.

## Question

Does CPM's edge survive realistic execution lag (T+1 MOO and beyond), and is the
headline free of same-day lookahead? Quantify the Sharpe lost going from the
optimistic same-day-close fill to the realistic T+1 MOO baseline.

## Anchor confirmation

CPM clean (2008-05-30..2026-05-22), T+1 MOO exact, 10 bps/side:
Sharpe **1.1910**, MaxDD **-12.67%**, Calmar **1.0615** -> reproduced EXACTLY by
this independent harness (`part1_exec_lag.clean.t1_moo`). Memo anchor confirmed.

Note: the production close-to-close engine (`run_cpm_backtest`, cpm_live.py:565-567)
gives Sharpe 1.2036 / MaxDD -12.28% (= the `same_day_moc` convention). The MEMO
does NOT report that number; it reports the harder, realistic T+1 MOO value via
`research/cpm_final_memo_numbers.py:17` ("T+1 MOO exact (mooex) with real opens").
So the published headline is already the conservative-execution number.

## 1. Execution-day lag (CPM sleeve, 4 conventions)

Conventions (af = first trading day after month-end signal close T):
- `same_day_moc` (optimistic / lookahead-ish): signal AND fill at close[T]; new
  basket earns close[T]->close[T+1]. = production close-to-close accounting.
- `t1_moo` (BASELINE, the memo headline): old basket earns overnight
  close[T]->open[af], new basket earns intraday open[af]->close[af].
- `t1_close`: fill at close[T+1]; new basket earns close[T+1]->close[T+2].
- `t2_open`: fill at open of T+2; old basket held to open[af2], new basket earns
  intraday open[af2]->close[af2].

### CLEAN 18y (2008-05-30 -> 2026-05-22), 10 bps/side

| convention | Sharpe | Calmar | MaxDD | CAGR | d Sharpe vs same-day | d Sharpe vs t1_moo |
|---|---:|---:|---:|---:|---:|---:|
| same_day_moc (optimistic) | 1.2063 | 1.1111 | -12.28% | 13.65% | -- | +0.0153 |
| **t1_moo (BASELINE/headline)** | **1.1910** | **1.0615** | **-12.67%** | 13.44% | **-0.0153** | -- |
| t1_close | 1.1515 | 0.9775 | -13.26% | 12.96% | -0.0548 | -0.0395 |
| t2_open | 1.1492 | 0.9691 | -13.35% | 12.94% | -0.0571 | -0.0418 |

### EXTENDED ~27y (1999-03-10 -> 2026-05-22; pre-2006 CPM opens missing -> 82 of 327 MOO days fall back to cc)

| convention | Sharpe | Calmar | MaxDD | CAGR |
|---|---:|---:|---:|---:|
| same_day_moc | 1.2444 | 0.8636 | -16.32% | 14.10% |
| t1_moo | 1.2244 | 0.8689 | -15.93% | 13.84% |
| t1_close | 1.1878 | 0.8533 | -15.71% | 13.40% |
| t2_open | 1.1880 | 0.8783 | -15.27% | 13.41% |

### Lag-cost quantification (the headline question)

- Optimistic same-day-close -> realistic T+1 MOO baseline: **-0.0153 Sharpe**
  (1.2063 -> 1.1910, ~1.3% relative), CAGR -0.21%/yr, MaxDD +0.39pp deeper.
- Same-day and T+1 MOO are effectively EQUAL. Per the brief, this confirms NO
  same-day dependence: the edge does not rely on filling at the same close that
  produced the signal.
- Pushing all the way to a full extra session (t1_close) or t2_open costs only
  -0.055 to -0.057 Sharpe vs same-day; Sharpe stays ~1.15, Calmar ~0.97,
  MaxDD ~-13.3%. The strategy is far from the ~0.1 Sharpe "collapse" threshold.

## 2. Trading-day-of-month sensitivity (close-to-close, eom + {0,1,2,3} bdays)

| shift | clean Sharpe | clean Calmar | clean MaxDD | ext Sharpe |
|---|---:|---:|---:|---:|
| eom+0 (convention) | 1.2063 | 1.1111 | -12.28% | 1.2444 |
| eom+1 | 1.0127 | 0.7454 | -15.57% | 1.1426 |
| eom+2 | 0.9747 | 0.5628 | -19.77% | 1.0738 |
| eom+3 | 0.9090 | 0.5429 | -18.66% | 1.0514 |

(Note: eom+0 here is the same_day_moc / close-to-close number 1.2063 because part 2
holds accounting fixed and varies only the rebalance DAY; compare within column.)

- Clean Sharpe range across the 4 days: **0.909 - 1.206** (~0.30 spread).
- Extended Sharpe range: **1.051 - 1.244** (~0.19 spread, more robust).
- The edge IS sensitive to the exact rebalance day: degradation is monotonic with
  lag past month-end (Sharpe and Calmar both fall, MaxDD deepens to ~-20% at eom+2).
- Interpretation: month-end is the canonical, a-priori convention (not the best of
  an ex-post sweep of arbitrary days). Monotonic decay with delay is consistent
  with momentum-signal freshness / turn-of-month effect, not a lucky single day.
  No day produces a collapse (all stay Sharpe > 0.9, positive Calmar). Mild yellow
  flag: the convention day is also the strongest, so a few-day execution slip in
  practice would cost real Sharpe -- but this is execution discipline, not lookahead.

## 3. Lookahead audit (point-in-time guards in cpm_live.py)

All signal computation truncates to data available at close[T] (sig_d):

- `monthly = close_panel.loc[:sig_d].resample("ME").last()` -- cpm_live.py:400.
  The `.loc[:sig_d]` slice happens BEFORE `resample("ME").last()`, so month-end
  labeling is point-in-time: the last monthly bar is close[T] itself; no future
  month can leak in. resample().last() is PIT-safe here.
- Safe-asset 13612U: `sub = monthly.loc[:sig_d]` -- cpm_live.py:361.
- Risky availability uses `close_panel.loc[sig_d]` (the signal close only) --
  cpm_live.py:431.
- 252d ranking vol: `daily_rets[t].loc[:sig_d].tail(252)` -- cpm_live.py:438
  (strictly <= T).
- 504d inverse-vol covariance: `csub = close_panel.loc[:sig_d]` -- cpm_live.py:461.
- Momentum legs (1/3/6/12m returns, 10m SMA) all read from the truncated monthly
  frame; no forward / full-month return leakage.

Execution alignment:
- `signal_dates` are month-end grouper tails -- cpm_live.py:527-528.
- `future = close.index[close.index > sig_d]; apply_from = future[0]` --
  cpm_live.py:536-539. New weights are NEVER applied on or before the signal day;
  they apply strictly from the first trading day after T.
- Returns are close-to-close: `daily_ret = close.ffill().pct_change()` /
  `(df_w * daily_ret).sum(...)` -- cpm_live.py:565-567. Because new weights start on
  the af row, the af-day return close[T]->close[af] accrues to the NEW vector. This
  is a mild same-day-close dependence in the PRODUCTION ENGINE accounting only.
- The published memo neutralizes that dependence by re-accounting with real opens
  (true T+1 MOO) in `research/cpm_final_memo_numbers.py:293` (run_cpm) / :17 (header),
  which forfeits the overnight gap on the turned-over fraction. That is why the
  headline (1.1910) is lower than the engine close-to-close (1.2036).

Plain statement: **No material lookahead exists.** The only same-day element is
the production engine's close-to-close accounting, worth +0.0153 Sharpe, and the
memo headline already reports the realistic T+1 MOO number that removes it. The
signal pipeline reads strictly data <= close[T]; execution is strictly > T.

## VERDICT

**The CPM edge survives realistic execution lag and is free of same-day lookahead.**

- Optimistic same-day-close -> realistic T+1 MOO baseline costs only **-0.0153
  clean Sharpe** (1.2063 -> 1.1910). Same-day and T+1 MOO are ~equal => no same-day
  dependence. The headline 1.1910 IS already the realistic conservative number.
- Even a harsher full-session lag (t1_close 1.1515, t2_open 1.1492) keeps clean
  Sharpe ~1.15 and Calmar ~0.97 -- nowhere near collapse.
- Pipeline PIT guards (cpm_live.py:400, 431, 438, 461, 536-539, 565-567) confirm
  signals use only data through close[T]; the memo re-accounts to true T+1 MOO
  (cpm_final_memo_numbers.py:17,293). resample("ME").last() labeling is point-in-time.
- Caveat (yellow, not a lookahead): the edge is moderately sensitive to the exact
  rebalance day (clean Sharpe 0.91 at eom+3 vs 1.21 at eom+0, monotonic). Month-end
  is the canonical convention, but real-world execution slippage past month-end
  would cost Sharpe. This is an execution-discipline risk, not a lookahead artifact.

Confidence: high on the lag/lookahead verdict (independent reproduction of the
exact anchor + code-level PIT trace). Moderate on the magnitude of the
day-of-month sensitivity (single-path, no bootstrap).

## Caveats

- Real auto_adjust OHLC from yfinance; overnight gap = open[af]/close[af-1] from
  one source. CPM ETF opens missing pre-2006 -> 82/327 extended-window rebal days
  fall back to close-to-close for the MOO conventions (clean 18y has full real-open
  coverage, 217/217). Clean window is the decisive lens.
- Production close panel uses stitched proxy adjusted-closes; yfinance opens use
  current re-adjustment. Only the open/close RATIO drives the MOO override, so level
  mismatch does not bias conventions.
- Day-of-month and lag deltas are single-path, not bootstrapped; treat magnitudes
  directionally.

## Reproduce

```
.venv/bin/python research/cpm_robust_lookahead.py
```
