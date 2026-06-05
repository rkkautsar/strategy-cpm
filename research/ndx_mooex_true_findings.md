# TRUE NDX mooex with fetched constituent opens

Date: 2026-06-02. Analyst pass. No prod-loader edits, no commit.

## Summary

The prior NDX mooex was PARTIAL: the macro open cache holds OHLC only for the
13 macro ETFs, so ~60% of NDX-active rebalance days fell back to close-to-close
(real=131 / fallback=195). This pass FETCHES NDX-constituent open prices from
yfinance (auto_adjust, mirroring the close panel 1:1) and recomputes the EXACT
mooex overnight-gap attribution. Real-open coverage rose to real=273 /
fallback=53 over the ext window (~84%).

Key result: the TRUE NDX mooex is LOWER than the partial estimate -- the partial
fallback was OPTIMISTIC because cc-fallback days hid the real overnight-gap drag
that momentum-selected names incur on the apply day. The final true-mooex PROD
headline is Sharpe 1.442 (clean), below the partial estimate 1.468 and the
close-to-close 1.494.

## (a) Universe (descoped: mirror close panel 1:1)

- Source close panel: `data/ndx_constituents/prices.parquet` (auto_adjust=True
  closes), 269 tickers, span 1995-01-03..2026-05-28. This is the full PIT
  Nasdaq-100 membership union from `index_constitution.history("nasdaq100")`;
  delisting is already baked into the closes. No separate survivorship handling.
- Opens fetched for the SAME 269 tickers over the SAME span.

## (b) Open fetch + adjustment alignment

- Script: `research/ndx_fetch_opens.py`. `yfinance.download(..., auto_adjust=True)`
  in chunks of 25; persisted adjusted Open AND Close.
- Alignment: prices.parquet closes are yfinance auto_adjust=True. Fetching with
  auto_adjust=True back-adjusts Open by the IDENTICAL split/div factor as Close,
  so adjusted_open is on the same basis as the existing adjusted closes.
  Verified: fetched yf adj-close vs parquet adj-close drift is max |rel| ~1e-6
  (AAPL/MSFT/ADBE/NVDA), i.e. floating-point identical -- no re-adjustment drift.
- Legs mirror the macro loader (`load_open_close`) convention:
  intraday = Close/Open - 1 (scale-invariant, drift-free);
  overnight = Open / Close.shift(1) - 1 (yfinance-internal close shift).
  96 implausible cells (|intraday| > 0.5, thin/early data) masked to NaN ->
  those cells fall back to cc inside the engine.
- Opens obtained for 205/269 tickers. The 64 misses are tickers that delisted
  and no longer refetch from yfinance (e.g. XLNX, YHOO, VIAB, SPLK, SGEN, WBA,
  RIMM, SIAL, ...) although the parquet retains their historic closes. These are
  the sole residual cc-fallback source (53 ext rebal days, see below).

## (c) New opens cache file

`research/ndx_opens_cache.parquet`
- MultiIndex columns: top level {Open, Close}, second level ticker (269 each).
- shape (7903, 538), span 1995-01-03..2026-05-28.
- Existing `data/ndx_constituents/prices.parquet` (closes) was NOT touched; no
  prod loader edited.

## (d) Coverage (residual fallback, one line)

NDX rebalance days (ext window): real overnight attribution = 273, cc fallback
= 53 (~84% real, up from 40% partial). Residual fallback = apply days whose
held basket includes one of the 64 unfetchable delisted tickers. NDX delta
nonzero on 214 clean-window days.

## (e) TRUE NDX mooex metrics

Engine: `research/ndx_mooex_true_recompute.py` -- same NDX delta-overlay as
`research/cpm_mooex_migration_recompute.py` (`ndx_mooex = run_ndx_backtest_cc +
(engine_mooex - engine_moc)`), now with constituent intraday/overnight injected.

| window | series | Sharpe | ExcSh | CAGR | Vol | MaxDD | Calmar | Martin |
|--------|--------|--------|-------|------|-----|-------|--------|--------|
| CLEAN | NDX cc | 1.2806 | 1.2241 | 31.441% | 23.565% | -31.389% | 1.0016 | 4.2328 |
| CLEAN | NDX mooex PARTIAL (old) | 1.2641 | 1.2075 | 30.914% | 23.551% | -31.389% | 0.9848 | 4.1425 |
| CLEAN | **NDX mooex TRUE** | **1.2056** | **1.1490** | **29.116%** | **23.543%** | **-31.765%** | **0.9166** | **3.5762** |
| EXT | NDX cc | 1.1314 | 1.0148 | 22.903% | 19.993% | -31.389% | 0.7296 | 3.5201 |
| EXT | NDX mooex PARTIAL (old) | 1.1192 | 1.0026 | 22.589% | 19.980% | -31.389% | 0.7196 | 3.4436 |
| EXT | **NDX mooex TRUE** | **1.0785** | **0.9617** | **21.580%** | **19.964%** | **-31.765%** | **0.6794** | **3.0307** |

## (f) FINAL true-mooex PROD headline (0.6 CPM + 0.2 BULL + 0.2 NDX)

| window | series | Sharpe | ExcSh | CAGR | Vol | MaxDD | Calmar | Martin |
|--------|--------|--------|-------|------|-----|-------|--------|--------|
| CLEAN | PROD cc | 1.4960 | 1.3745 | 17.018% | 10.934% | -10.464% | 1.6263 | 6.7137 |
| CLEAN | PROD mooex (partial-NDX est) | 1.468 | -- | 16.65% | -- | -10.49% | -- | -- |
| CLEAN | **PROD mooex TRUE** | **1.4424** | **1.3208** | **16.327%** | **10.928%** | **-10.489%** | **1.5566** | **6.1600** |
| EXT | PROD cc | 1.4308 | 1.2060 | 14.902% | 10.063% | -10.464% | 1.4240 | 5.8319 |
| EXT | PROD mooex (partial-NDX est) | 1.406 | -- | 14.61% | -- | -10.49% | -- | -- |
| EXT | **PROD mooex TRUE** | **1.3888** | **1.1636** | **14.416%** | **10.063%** | **-10.489%** | **1.3745** | **5.4229** |

## Replacement-map deltas (vs partial-NDX numbers in cpm_mooex_migration_findings.md)

Migration doc rows 65/66 (raw-mom) replace as:

| row | metric set | cc (old headline) | partial-NDX mooex | **TRUE-NDX mooex (use this)** |
|-----|-----------|-------------------|-------------------|-------------------------------|
| 65 Clean | NDX Sh/CAGR/DD + Blend Sh/CAGR/DD | 1.279 / 31.43% / -31.39% ; 1.494 / 17.02% / -10.46% | 1.264 / 30.91% / -31.39% ; 1.468 / 16.65% / -10.49% | **1.206 / 29.12% / -31.77% ; 1.442 / 16.33% / -10.49%** |
| 66 Ext | NDX Sh/CAGR/DD + Blend Sh/CAGR/DD | 1.131 / 22.90% / -31.39% ; 1.431 / 14.90% / -10.46% | 1.119 / 22.59% / -31.39% ; 1.406 / 14.61% / -10.49% | **1.079 / 21.58% / -31.77% ; 1.389 / 14.42% / -10.49%** |
| 46 sleeve NDX | Sh/ExcSh/CAGR/Vol/MaxDD/Calmar | 1.279/1.223/31.43%/23.56%/-31.39%/1.00 | 1.264/1.208/30.91%/23.55%/-31.39%/0.98 | **1.206/1.149/29.12%/23.54%/-31.77%/0.92** |

README/dashboard: any hardcoded mooex PROD Sharpe should be 1.442 (clean) /
1.389 (ext), NOT the partial 1.468 / 1.406. NDX sleeve mooex Sharpe 1.206 (clean).
MaxDD for NDX shifts -31.389% -> -31.765% (overnight gap reassigns one drawdown
day); blend MaxDD unchanged at -10.489%.

## Verdict

True (near-full) NDX mooex IS now achievable. Constituent opens ARE fetchable
for all CURRENT-trading names with floating-point adjustment consistency, lifting
real-open coverage from 40% to ~84% of NDX rebalance days. The residual ~16%
fallback is a pure survivorship-fetch artifact: 64 delisted tickers whose closes
survive in the parquet but whose opens no longer refetch from yfinance. This is
a small, bounded residual (53 ext rebal days) and it biases the NDX mooex only
marginally toward cc on those days; the headline already reflects mostly-real
opens. Eliminating it would require an open-price source that preserves delisted
tickers (the same archive that built the close parquet) -- not free from
yfinance live. Net: ship PROD mooex headline 1.442 (clean) as the faithful
number; the prior partial 1.468 was optimistic by ~0.026 Sharpe.

## Artifacts / commands

- Fetch:    `.venv/bin/python research/ndx_fetch_opens.py`
- Recompute:`.venv/bin/python research/ndx_mooex_true_recompute.py`
- New cache: `research/ndx_opens_cache.parquet`
