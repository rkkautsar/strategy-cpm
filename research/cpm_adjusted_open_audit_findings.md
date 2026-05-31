# CPM Backtest Return-Construction Audit (Review Item 4.5)

**Question:** Is the CPM backtest's return construction internally consistent, or does it
suffer the classic "adjusted-close mixed with raw-open" bug that would invalidate the
headline numbers (clean Sharpe 1.1910, MaxDD -12.67%, T+1 MOO execution results, and the
execution-cliff / MOC-vs-MOO comparisons)?

**Verdict (high confidence): NO BUG. The return construction is adjustment-consistent.
Both opens and closes come from the same yfinance `auto_adjust=True` scheme. Headline
numbers stand.**

Date: 2026-06-01. Read-only audit. Diagnostic: `research/_audit_open_close_consistency_tmp.py`
(run with `.venv/bin/python`).

---

## 1. Data-construction map (verified, file:line)

### Signal + bulk-return close panel
- `cpm_live.load_panel()` (`cpm_live.py:129`) builds the daily panel exclusively from
  **adjusted-close** sources:
  - In-repo proxy panel `data/proxy_adjusted_close_daily.csv` (adjusted close).
  - Stitched mutual-fund -> ETF series in `data/` (GLD/TIP/HYG/SHV/IEF/TLT/QQQ),
    each an adjusted/total-return stitch (`cpm_live.py:160-188`).
  - Any missing tickers fetched via `_download_adjusted_close()` using
    `yf.download(..., auto_adjust=True)` (`cpm_live.py:90-96`).
- Signals (13612U momentum, Faber SMA, inverse-vol covariance) are computed on this
  adjusted-close panel => **signals are on a total-return / adjusted basis.**

### Open prices for T+1 MOO execution
- The mooex (T+1 MOO-exact) harness sources opens from the OHLC cache
  `/tmp/cpm_open_cache/{TICKER}.csv` via `load_open_close()`
  (`research/exec_lag_moo_validation_2026_05_30.py:60-69`;
  replicated `research/cpm_lookback_unify_harness.py:72-79`). Each CSV has
  `Date,Open,Close` columns.
- The cache was generated from `yf.download(..., auto_adjust=True)` -- both Open and
  Close from the **same adjustment scheme**. The generating pattern and its explicit
  bug-avoidance rationale are documented in
  `research/exec_accounting_audit_2026_05.py:29-50`:
  > "Critical: opens and closes must come from the same adjustment scheme. Mixing
  > yfinance opens with our stitched panel closes gives 4-15x scale mismatches on split
  > days, which explodes overnight returns."
- Cache file inspection confirms same-scale adjustment: e.g. `SPY.csv` 1993-01-29 shows
  `Open=24.19, Close=24.18` (both back-adjusted; raw 1993 SPY traded ~$43). A raw-open
  bug would show open ~43 vs close ~24 (a 1.8x mismatch).

### Return construction in the mooex override
`_segment_returns_conv(... convention="mooex")`
(`research/exec_lag_moo_validation_2026_05_30.py:101-205`):
- Non-rebalance days: portfolio return = weights x panel close-to-close
  (`daily_ret = panel.ffill().pct_change()`).
- Rebalance day `af` (first trading day after month-end T): return is **overridden** with
  `(1 + overnight) * (1 + intraday) - 1`, where
  - `overnight[a] = open_cache[af] / close_cache[af-1] - 1` (old basket weights),
  - `intraday[a]  = close_cache[af] / open_cache[af] - 1` (new basket weights).
  - Both legs use the **same** auto_adjust cache (`intraday = close_yf/open_df - 1`,
    `overnight = open_df/close_yf.shift(1) - 1`, lines 264-268).
- Dividend reinvestment: handled implicitly by `auto_adjust=True` total-return
  back-adjustment (dividends folded into the price series). No separate reinvestment
  price is used; the entire series (open + close) is on one consistent total-return basis.

### Headline-number provenance
- `research/cpm_lookback_unify_harness.py:59` pins
  `ANCHOR = {"clean": (1.1910, -12.67, 1.0615), ...}` = (Sharpe, MaxDD%, Calmar).
  The anchor self-check (`:269-281`) confirms the production engine reproduces clean
  Sharpe 1.1910 / MaxDD -12.67% under the mooex convention. => The audited code path **is**
  the headline path.

---

## 2. Bug-check results (empirical, `_audit_open_close_consistency_tmp.py`)

### CHECK 1 -- open/close on same scale (raw-open bug detector)
Intraday `close/open - 1` per ticker over full history. A raw-open-vs-adj-close mismatch
would produce >100% intraday "returns" on split days. Result: **zero days >30%** across
all 13 tickers; max intraday move 19.6% (QQQ), means 0.01-0.97%. No split-day explosions.
=> Opens and closes are on the same adjustment scale.

### CHECK 3 -- overnight gap (ex-dividend fake-gap detector)
Overnight `open[t]/close[t-1] - 1`. A dividend on ex-date with mismatched adjustment would
inject a fake close-to-open gap. Result: **zero days >15%** across all tickers; max 13.5%,
means 0.01-0.78% (normal overnight magnitudes). => No dividend/split adjustment mismatch
in the overnight leg.

### CHECK 2 -- rebal-day seam (mooex override vs panel close-to-close)
The only place the cache enters is the rebal-day override. Compared cache close-to-close
vs panel adjusted close-to-close on all 216 clean-window rebal days x 13 assets:
- **max |seam| = 0.0 bps, mean |seam| = 0.002 bps, p99 = 0.0 bps** (n=2808).
- The mooex rebal-day return `(1+overnight)(1+intraday) = close_cache[af]/close_cache[af-1]`
  equals the panel close-to-close to numerical precision.

### CHECK 2b -- level ratio cache_close / panel_close on rebal days
QQQ/GLD/TLT ratio = 1.00000 (std 0). SPY ratio = 0.26512 (std 0) -- a *constant* scale
offset (different adjustment vintage) that **cancels exactly in pct_change**, which is why
the seam is still 0.0 bps. (SPY is the BULL sleeve, not in the CPM risky universe; the CPM
universe tickers all match at ratio 1.0.) The zero std proves cache and panel differ only
by a constant multiplicative factor => identical returns.

---

## 3. Impact estimate

The maximum possible distortion to the headline metrics from open/close adjustment
mismatch is bounded by the rebal-day seam = **0.0 bps**. There is no inconsistency to
quantify; the impact on Sharpe (1.1910), MaxDD (-12.67%), Calmar, the T+1 MOO results,
and the MOC-vs-MOO execution-cliff comparison is **nil (numerically zero, not merely
negligible)**.

The MOC-vs-MOO and execution-cliff comparisons are also valid: the overnight/intraday
split is adjustment-consistent (CHECK 1 + CHECK 3 both clean), so the difference between
"new basket earns full close-to-close" (MOC) and "new basket earns intraday only" (MOO)
is driven by a correctly-priced overnight gap, not an adjustment artifact.

---

## 4. Verdict

**T+1 MOO / MOC return construction is CORRECT (adjustment-consistent). Headline numbers
stand.**

- Verified: signals on adjusted/total-return closes; opens and closes from one
  `auto_adjust=True` scheme; intraday and overnight legs from the same cache; rebal-day
  override identical to panel close-to-close to 0.0 bps; no raw-open or ex-div fake-gap
  artifacts; the audited path reproduces the published anchor.
- Assumed / residual risk (stated honestly):
  1. yfinance `auto_adjust` adjustment is vendor-opaque and back-adjusts retroactively as
     new dividends accrue. This is benign here because opens and closes rescale *together*
     (constant ratio, CHECK 2b std=0), so returns are invariant; and the cache is a frozen
     2026-05-30 snapshot, so the published numbers are reproducible.
  2. The safety property depends on the cache being regenerated with `auto_adjust=True`
     for *both* O and C. If a future regeneration fetched raw opens (`auto_adjust=False`)
     while keeping adjusted closes, the classic bug would reappear. The current cache and
     all reader code paths use auto_adjust for both (confirmed by CHECK 1). Recommend a
     guard/assert that re-runs CHECK 1 (intraday sanity) on cache load, but that is a
     fixer task, out of scope for this read-only audit.

---

## Reproduce

```
cd /Users/rkautsar/personal/scripts/strategy_cpm
.venv/bin/python research/_audit_open_close_consistency_tmp.py
```

Key code paths: `cpm_live.py:90-96,129-188` (adjusted-close panel),
`research/exec_accounting_audit_2026_05.py:29-50` (same-scheme OHLC fetch + rationale),
`research/exec_lag_moo_validation_2026_05_30.py:60-69,101-205,264-268` (mooex override),
`research/cpm_lookback_unify_harness.py:59,269-281` (headline anchor + self-check).
