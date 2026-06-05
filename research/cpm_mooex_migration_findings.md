# CPM full MOOEX migration: canonical numbers + replacement map + dashboard plan

Analyst pass. Research artifact only. No README/build_dashboard/cpm_live/sleeve-prod/
memo files edited; no commit. Everything recomputed from the frozen in-repo panel
(`load_panel(live=False)`, `EVAL_END = 2026-05-22`, `CORR_LOOKBACK_DAYS = 252`) via
`research/cpm_mooex_migration_recompute.py` (run with `.venv/bin/python`).

DECISION CONTEXT: the canonical execution convention for ALL reader-facing numbers
is now MOOEX T+1 exact (rebalance day: OLD basket earns the overnight gap
close[T]->open[T+1], NEW basket earns intraday open[T+1]->close[T+1] only), the
realistic convention the `cpm_harness.verify_anchor` already enforces for CPM
(anchor Sharpe 1.255673). This pass migrates BULL, NDX, the PROD 60/20/20 blend,
CPM-BULL 60/40, and the strategy-rebalanced benchmarks to the same convention.

## TL;DR (the headline change the user must see)

- NEW canonical PROD 60/20/20 headline (clean window, mooex): Sharpe **1.468**
  (was 1.494 close-to-close), CAGR **16.65%** (was 17.02%), MaxDD **-10.49%**
  (was -10.46%), Calmar **1.59** (was 1.63). The drop is modest (-0.026 Sharpe);
  MaxDD is essentially unchanged because the PROD trough is not on a rebalance day.
- CPM confirms the enforced anchor exactly: Sharpe **1.2557** / MaxDD **-13.03%** /
  Calmar **1.0076** (was 1.291 / -11.57% / 1.17 close-to-close).
- BULL is nearly convention-invariant (0.985 -> 0.984): it holds 100% SPY or 100%
  safe for long stretches, so few rebalance-day gaps to re-attribute.
- NDX could NOT be cleanly mooex'd (FLAG, see section (e)). Its individual NASDAQ-100
  constituents have no OHLC-open data in the macro open cache, so ~60% of NDX
  rebalance days fall back to close-to-close. NDX mooex is therefore a PARTIAL
  mooex (1.281 -> 1.264, MaxDD identical at -31.39%).
- Convention-invariant benchmarks (NO change): SPY buy-hold (0.660), QQQ buy-hold
  (0.816). Strategy-rebalanced benchmarks (BB4/BB1/60-40/static-PP) ARE
  convention-sensitive but the pure-convention shift is small (BB4 ~-0.016 Sharpe);
  none are hardcoded headline cells, so no value swap is required for them.

## (a) Full mooex metric table (all sleeves + blend + benchmarks)

Window/convention/costs/data for EVERY row below:
- Clean window: 2008-05-30 -> 2026-05-22 (~18.0y). Ext window: 1999-03-10 -> 2026-05-22.
- Convention: CC = close-to-close T+1 (OLD); MOOEX = T+1 MOO exact (NEW canonical).
- Both-252 baseline, 10 bps/side at each rebalance apply day, frozen panel EVAL_END 2026-05-22.
- Sharpe is raw (rf=0); ExcSh is excess vs SHV.

### Clean window 2008-05-30 -> 2026-05-22

| Series | Conv | Sharpe | ExcSh | CAGR | Vol | MaxDD | Calmar | Martin |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| PROD 60/20/20 | CC | 1.4960 | 1.3745 | 17.018% | 10.934% | -10.464% | 1.6263 | 6.7137 |
| **PROD 60/20/20** | **MOOEX** | **1.4680** | **1.3464** | **16.650%** | **10.927%** | **-10.490%** | **1.5873** | **6.3583** |
| CPM-BULL 60/40 | CC | 1.2928 | 1.1572 | 12.933% | 9.809% | -10.699% | 1.2088 | 4.6756 |
| **CPM-BULL 60/40** | **MOOEX** | **1.2685** | **1.1327** | **12.653%** | **9.800%** | **-11.185%** | **1.1312** | **4.4093** |
| CPM | CC | 1.2926* | 1.1630 | 13.548% | 10.266% | -11.571% | 1.1709 | 4.5704 |
| **CPM** | **MOOEX** | **1.2557** | **1.1262** | **13.131%** | **10.275%** | **-13.032%** | **1.0076** | **4.2571** |
| BULL | CC | 0.9851 | 0.8738 | 11.675% | 11.975% | -20.277% | 0.5758 | 2.4973 |
| **BULL** | **MOOEX** | **0.9840** | **0.8721** | **11.602%** | **11.915%** | **-20.408%** | **0.5685** | **2.3815** |
| NDX | CC | 1.2806 | 1.2241 | 31.441% | 23.565% | -31.389% | 1.0016 | 4.2328 |
| **NDX** | **MOOEX (partial)** | **1.2641** | **1.2075** | **30.914%** | **23.551%** | **-31.389%** | **0.9848** | **4.1425** |
| BB4 lit blend | CC (eng) | 1.2587 | 1.1253 | 12.717% | 9.945% | -14.444% | 0.8804 | 4.0476 |
| BB4 lit blend | MOOEX (eng) | 1.2425 | 1.1092 | 12.539% | 9.947% | -16.132% | 0.7773 | 3.7333 |
| 60/40 SPY/IEF | CC (eng) | 0.7952 | 0.6753 | 8.761% | 11.417% | -29.777% | 0.2942 | 1.4048 |
| 60/40 SPY/IEF | MOOEX (eng) | 0.7946 | 0.6748 | 8.755% | 11.418% | -29.820% | 0.2936 | 1.4023 |
| SPY buy-hold | INVARIANT | 0.6603 | 0.5912 | 11.727% | 19.815% | -50.699% | 0.2313 | 1.0599 |
| QQQ buy-hold | INVARIANT | 0.8163 | 0.7547 | 16.942% | 22.297% | -49.367% | 0.3432 | 1.4246 |

\* CPM CC here = 1.2926 (engine run from EXT start, then sliced clean). The README/
dashboard hardcoded CPM CC is 1.2912 (run_cpm_backtest started at CLEAN). The 0.0014
gap is first-segment warmup only; the canonical MOOEX CPM 1.2557 is exact to the
enforced anchor either way. Use the existing hardcoded 1.2912 as the OLD value in the
replacement map.

### Ext window 1999-03-10 -> 2026-05-22 (README "Stress")

| Series | Conv | Sharpe | ExcSh | CAGR | Vol | MaxDD | Calmar | Martin |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| PROD 60/20/20 | CC | 1.4308 | 1.2060 | 14.902% | 10.063% | -10.464% | 1.4240 | 5.8319 |
| **PROD 60/20/20** | **MOOEX** | **1.4056** | **1.1806** | **14.607%** | **10.060%** | **-10.490%** | **1.3925** | **5.5498** |
| CPM-BULL 60/40 | CC | 1.2861 | 1.0427 | 12.296% | 9.358% | -10.699% | 1.1492 | 4.5490 |
| **CPM-BULL 60/40** | **MOOEX** | **1.2647** | **1.0210** | **12.067%** | **9.355%** | **-11.185%** | **1.0788** | **4.3234** |
| CPM | CC | 1.2913 | 1.0629 | 13.154% | 9.955% | -11.571% | 1.1368 | 4.3945 |
| **CPM** | **MOOEX** | **1.2549** | **1.0265** | **12.763%** | **9.968%** | **-13.141%** | **0.9712** | **4.1168** |
| BULL | CC | 0.9691 | 0.7602 | 10.720% | 11.151% | -20.277% | 0.5287 | 2.5481 |
| **BULL** | **MOOEX** | **0.9735** | **0.7639** | **10.734%** | **11.108%** | **-20.408%** | **0.5259** | **2.4751** |
| NDX | CC | 1.1314 | 1.0148 | 22.903% | 19.993% | -31.389% | 0.7296 | 3.5201 |
| **NDX** | **MOOEX (partial)** | **1.1192** | **1.0026** | **22.589%** | **19.980%** | **-31.389%** | **0.7196** | **3.4436** |
| SPY buy-hold | INVARIANT | 0.5220 | 0.3939 | 8.504% | 19.244% | -55.189% | 0.1541 | 0.5334 |
| QQQ buy-hold | INVARIANT | 0.5193 | 0.4273 | 10.895% | 26.910% | -82.964% | 0.1313 | 0.2502 |

### Which benchmarks are convention-invariant vs sensitive

- INVARIANT (no rebalance, pure buy-hold daily close-to-close): SPY buy-hold,
  QQQ buy-hold. Their numbers are identical under both conventions; do NOT touch.
- SENSITIVE (monthly strategy-rebalanced, so the rebalance-day overnight gap is
  re-attributed): BB4, BB1, 60/40 SPY/IEF, static 80% PP + 20% QQQ, and the
  per-sleeve literature peers B1-B5. The pure-convention effect is small and same
  direction as the sleeves: slightly lower Sharpe, slightly deeper MaxDD.
  - BB4 engine-consistent delta: 1.2587 -> 1.2425 (MaxDD -14.44% -> -16.13%).
  - 60/40 SPY/IEF: 0.7952 -> 0.7946 (effectively invariant; mostly buy-and-hold).
  - NOTE: the engine reimplementation of the benchmarks uses a turnover-based cost
    model; the production `bench_*` functions in build_dashboard use a flip-based
    cost model. So the engine CC (1.2587) does not equal the prod-fn CC the README
    prints for BB4 (1.194). The clean convention delta MUST be read as engine-moc ->
    engine-mooex (both same cost model), NOT prod-fn-CC -> engine-mooex. If the
    benchmark rows are ever migrated, recompute them through the PRODUCTION bench
    functions with a mooex option (see fixer plan), not the research engine.

CONSEQUENCE for the narrative: under mooex, PROD drops (1.496 -> 1.468) while BB4
under its own convention delta moves less, so PROD's edge over BB4 shrinks modestly
but PROD still leads on Sharpe, MaxDD, and Calmar. None of the benchmark rows are
hardcoded headline cells that must be swapped, so the migration's required edits are
confined to PROD/CPM/BULL/NDX/CPM-BULL.

## (b) Exactly how each sleeve's mooex returns were computed

All three sleeves use the SAME mooex mechanism as `cpm_harness`: the engine
`research/exec_lag_moo_validation_2026_05_30._segment_returns_conv(..., "mooex", ...)`.
On each rebalance apply day `af`:
`ret[af] = (1 + sum_a prev_w[a]*overnight[a]) * (1 + sum_a new_w[a]*intraday[a]) - 1`,
where `overnight[a] = open[af]/close[af-1] - 1` and `intraday[a] = close[af]/open[af] - 1`
come from the real-OHLC open cache (`load_open_close()`, `/tmp/cpm_open_cache`,
yfinance auto_adjust). Held (non-rebalance) days are identical close-to-close in both
conventions; only rebalance-day gap attribution differs.

- CPM (canonical, exact): `cpm_harness.run_strategy(compute_target_weights)`. This IS
  the enforced-anchor path; `verify_anchor` reproduced Sharpe 1.255673 / MaxDD
  -0.130317 / Calmar 1.007646 to 6 dp through this harness. No reimplementation.

- BULL (faithful, full coverage): engine `_segment_returns_conv` driven by the
  PRODUCTION `bull_spy_live.compute_bull_spy_weights(panel, sd, panel[BULL_TICKER])[0]`
  with the production `_vol_gate_ok` (NOT monkeypatched). Verification: the engine's
  `moc` (close-to-close) convention reproduces `bull_spy_live.run_bull_spy_backtest`
  EXACTLY (clean Sharpe 0.9851, CAGR 11.675%, MaxDD -20.277%, Calmar 0.5758 identical
  to 4 dp). Because the close-to-close path is bit-faithful, the engine's `mooex`
  output is the faithful BULL mooex series. BULL holds only macro ETFs (SPY/SHV/IEF),
  all in the open cache, so rebalance-day attribution is fully real (clean window: no
  fallbacks).

- NDX (delta overlay, PARTIAL coverage -- see flag): to preserve the production NDX
  engine's delisting-haircut and holiday logic (which the generic engine lacks), NDX
  mooex = `run_ndx_backtest(close-to-close) + (engine_mooex - engine_moc)`. The delta
  is the pure convention effect isolated on rebalance days; it is overlaid on the
  production series so the held-period return stream (with delisting haircuts) is
  untouched. The engine was driven by production
  `ndx_sleeve_live.compute_ndx_weights(cpm_panel, ndx_panel, sd)[0]` on the joined
  `cpm_panel + ndx_panel`. Engine `moc` reproduced production NDX to within
  delisting-handling noise (clean Sharpe 1.2819 eng vs 1.2806 prod). CRITICAL LIMIT:
  the open cache contains macro ETFs ONLY (SPY,QQQ,SPHQ,EFA,EEM,VNQ,GLD,TLT,DBC,SHV,
  IEF,HYG,TIP,IWM,VEA,VWO), NOT the individual NASDAQ-100 constituents NDX actually
  holds when its gate is ON. So on NDX-active rebalance days the intraday/overnight
  legs are missing and the engine falls back to close-to-close for those days. Clean
  window: only 201 of the rebalance days carry a nonzero convention delta; ext window
  coverage was real=131 / fallback=195. NDX mooex is therefore a PARTIAL mooex.

- Blend: `0.6*CPM_mooex + 0.2*BULL_mooex + 0.2*NDX_mooex` on the common daily index.
  CPM-BULL 60/40 = `0.6*CPM_mooex + 0.4*BULL_mooex`.

Turnover is convention-INVARIANT (it depends on the weight vectors, not on execution
timing), so the existing turnover figures (CPM ~2.582 one-way/yr, ~13.4% fully-safe)
carry over unchanged; no turnover recompute was needed.

Reproduce: `.venv/bin/python research/cpm_mooex_migration_recompute.py`

## (c) Per-doc OLD (close-to-close) -> NEW (mooex) replacement map

Apply the mooex VALUE swaps below. Keep the window label "clean live-ETF window
2008-05-30 -> 2026-05-22" valid and add a convention tag "(mooex T+1 exact)" wherever
a CPM/PROD stat appears, so the same metric name resolves to one number across docs.

### README.md

| Line | Cell | OLD (close-to-close) | NEW (mooex) |
|---|---|---|---|
| 34 (headline PROD) | Sharpe / ExcSh / CAGR / Vol / MaxDD / Calmar | 1.494 / 1.373 / 17.02% / 10.93% / -10.46% / 1.63 | 1.468 / 1.346 / 16.65% / 10.93% / -10.49% / 1.59 |
| 44 (sleeve CPM) | Sharpe / ExcSh / CAGR / Vol / MaxDD / Calmar | 1.291 / 1.162 / 13.55% / 10.27% / -11.57% / 1.17 | 1.256 / 1.126 / 13.13% / 10.28% / -13.03% / 1.01 |
| 45 (sleeve BULL) | Sharpe / ExcSh / CAGR / Vol / MaxDD / Calmar | 0.984 / 0.872 / 11.67% / 11.98% / -20.28% / 0.58 | 0.984 / 0.872 / 11.60% / 11.92% / -20.41% / 0.57 |
| 46 (sleeve NDX) | Sharpe / ExcSh / CAGR / Vol / MaxDD / Calmar | 1.279 / 1.223 / 31.43% / 23.56% / -31.39% / 1.00 | 1.264 / 1.208 / 30.91% / 23.55% / -31.39% / 0.98 |
| 47 (sleeve PROD) | same as line 34 | 1.494 / 1.373 / 17.02% / 10.93% / -10.46% / 1.63 | 1.468 / 1.346 / 16.65% / 10.93% / -10.49% / 1.59 |
| 53 (CPM anchor) | Sharpe / CAGR / Vol / MaxDD / Calmar / Martin | 1.2912 / 13.55% / 10.27% / -11.57% / 1.1711 / 4.5711 | 1.2557 / 13.13% / 10.28% / -13.03% / 1.0076 / 4.2571 |
| 54 (CPM-BULL 60/40) | Sharpe / CAGR / Vol / MaxDD / Calmar / Martin | 1.2912 / 12.93% / 9.81% / -10.70% / 1.2089 / 4.6761 | 1.2685 / 12.65% / 9.80% / -11.19% / 1.1312 / 4.4093 |
| 65 (raw-mom Clean) | NDX Sh/CAGR/DD + Blend Sh/CAGR/DD | 1.279 / 31.43% / -31.39% / 1.494 / 17.02% / -10.46% | 1.264 / 30.91% / -31.39% / 1.468 / 16.65% / -10.49% |
| 66 (raw-mom Stress=ext) | NDX Sh/CAGR/DD + Blend Sh/CAGR/DD | 1.131 / 22.90% / -31.39% / 1.431 / 14.90% / -10.46% | 1.119 / 22.59% / -31.39% / 1.406 / 14.61% / -10.49% |
| 229 (lit table PROD) | Sharpe / CAGR / MaxDD | 1.494 / 17.02% / -10.46% | 1.468 / 16.65% / -10.49% |
| 252 (robustness ext Sharpe pt) | ext Sharpe point | 1.431 | 1.406 |
| 268 (forward-guidance prose) | "realized backtest Sharpe is 1.494" | 1.494 | 1.468 |

README cells NOT swapped in this map (flag, do not blind-edit):
- Lines 35-37 headline BENCHMARK rows (BB4 1.194, BB1 1.122, SPY 0.660, QQQ 0.816):
  SPY/QQQ are INVARIANT (leave). BB4/BB1 are sensitive but their README values come
  from the PRODUCTION bench functions (flip-cost model), so they must be re-derived
  through those functions under mooex, not via the research engine. Recommend the
  fixer add a mooex path to the bench functions OR leave benchmark rows on
  close-to-close with an explicit per-table convention note. Not a hard swap here.
- Lines 222-230 literature table B1-B5/BB1/BB4: same as above (sensitive, prod-fn).
- Lines 233-240 bootstrap CI table + line 252 ext CI bounds: generated by
  `research/bootstrap_ci_2026_05_28.py`. The Sharpe/CAGR/MaxDD POINT estimates shift
  to the mooex values, but the CI bounds must be regenerated by re-running that
  bootstrap script on the mooex PROD daily series. Out of this pass's recompute scope;
  flag to fixer as a script re-run (point estimates: Sharpe 1.494->1.468, ext
  1.431->1.406; bounds TBD by re-run).
- Line 70-78 alpha/beta table: live-rendered in the dashboard; shifts marginally
  under mooex. Re-derive via the dashboard once build_artifacts is on mooex.
- Line 56 concentration shares: convention-INVARIANT (weights unchanged); do not edit.

### build_dashboard.py (hardcoded cells)

| Line(s) | Cell | OLD (close-to-close) | NEW (mooex) |
|---|---|---|---|
| 57 (FORWARD_SHARPE_GUIDANCE) | "Sharpe 1.4944, CAGR 17.02%, MaxDD -10.46%, Calmar 1.6261" | 1.4944 / 17.02% / -10.46% / 1.6261 | **1.4680 / 16.65% / -10.49% / 1.5873** |
| 2317-2319 (sleeve_rows "CPM-BULL 60/40") | sharpe/cagr/vol/maxdd/calmar/martin | 1.2912 / 0.1293 / 0.0981 / -0.1070 / 1.2089 / 4.6761 | 1.2685 / 0.1265 / 0.0980 / -0.1119 / 1.1312 / 4.4093 |
| 2321-2323 (sleeve_rows "CPM, clean window") | sharpe/cagr/vol/maxdd/calmar/martin | 1.2912 / 0.1355 / 0.1027 / -0.1157 / 1.1711 / 4.5711 | 1.2557 / 0.1313 / 0.1028 / -0.1303 / 1.0076 / 4.2571 |
| 2402-2410 (cpm_bull_60_40_clean_anchor) | sharpe/cagr/vol/maxdd/calmar/martin | 1.2912 / 0.1293 / 0.0981 / -0.1070 / 1.2089 / 4.6761 | 1.2685 / 0.1265 / 0.0980 / -0.1119 / 1.1312 / 4.4093 |

The LIVE-rendered sleeve_rows cells (PROD via `perf_metrics(art.blend,...)`, CPM via
`art.cpm`, BULL via `art.bull`, NDX via `art.ndx`) are NOT string swaps -- they follow
whatever `build_artifacts` computes. See section (d): they must be switched to mooex at
the artifact layer, or the table will show mooex hardcoded rows next to close-to-close
live rows.

## (d) Dashboard live-render alignment plan (for the fixer)

VERDICT: this is a DEEP convention change at the artifact-computation layer, NOT a
localized string edit -- and full live mooex consistency is BLOCKED for NDX by missing
constituent OHLC-open data. The hardcoded swaps in (c) are localized and trivial; the
live rows are not.

Why live rows disagree if only strings are edited:
- `build_dashboard.build_artifacts()` (lines 620-680) is the single source of truth.
  It computes the sleeves close-to-close:
  - line 637: `cpm, _ = run_cpm_backtest(panel, start, end)`
  - line 638: `bull_raw = run_bull_spy_backtest(panel, start, end)`
  - line 641: `ndx_raw, _ = run_ndx_backtest(panel, ndx_panel, start, end)`
  - line 656: `blend_uncapped = CPM_W*cpm + BULL_W*bull + NDX_W*ndx`
- `art.cpm/bull/ndx/blend` then feed: sleeve_rows live cells (line 2315), the
  alpha/beta regression block (~2330+), the EXT artifacts (`ext_art`, ~2362), every
  equity/drawdown/rolling chart, and the HTML headline metrics (~2420+). Editing only
  the hardcoded strings leaves all of these on close-to-close.

What a mooex render requires:
1. A mooex engine in the prod path. The mechanism lives in
   `research/exec_lag_moo_validation_2026_05_30._segment_returns_conv` and
   `research/cpm_harness`. The fixer must either (a) import the research engine into
   build_dashboard (cross-layer prod->research import, a layering smell), or (b)
   promote the mooex overnight/intraday attribution into the prod sleeve modules
   (`cpm_live`, `bull_spy_live`, `ndx_sleeve_live`) behind a `convention="mooex"` flag
   (cleaner, larger surface). Recommended: (b) for cpm_live/bull_spy_live.
2. Per-asset OHLC-open data at runtime. The mooex formula needs open/close per held
   asset. Today this only exists as the FROZEN macro-only cache
   (`load_open_close()`, /tmp/cpm_open_cache). The dashboard defaults to live=True
   (end=today, fresh yfinance), so a live mooex render needs a live open/close fetch
   for every held ticker.
3. NDX BLOCKER. NDX holds individual NASDAQ-100 constituents when its gate is ON.
   There is NO open-cache entry for them, and no runtime open feed for them today.
   Even in research, NDX mooex falls back to close-to-close on ~60% of rebalance days.
   A truly faithful live NDX mooex needs an OHLC-open source for every NDX constituent
   -- new data infrastructure, out of scope for a render fix.

Recommended MINIMAL fixer plan (partial-consistent, ships now):
- Switch CPM and BULL in `build_artifacts` to mooex (both hold only macro ETFs with
  full open coverage):
  - line 637: replace `run_cpm_backtest(panel, start, end)` with the mooex CPM series
    (via `cpm_harness.run_strategy(compute_target_weights, ...)` or a promoted
    `run_cpm_backtest(..., convention="mooex")`).
  - line 638: replace `run_bull_spy_backtest(panel, start, end)` with the mooex BULL
    series (engine `_segment_returns_conv(..., "mooex", ...)` driven by
    `compute_bull_spy_weights`, or a promoted `run_bull_spy_backtest(..., convention=
    "mooex")`).
- Keep NDX (line 641) on close-to-close and add an explicit per-row note in the table
  ("NDX: close-to-close; no constituent OHLC opens for mooex"). Justification: NDX
  mooex ~= NDX cc anyway (Sharpe 1.281 -> 1.264, MaxDD identical -31.39%), and the
  blend impact at 0.2 weight is negligible.
- `blend_uncapped` (line 656) then auto-follows. With CPM+BULL mooex and NDX cc the
  PROD headline renders Sharpe **1.475** / CAGR **16.74%** / MaxDD **-10.49%** /
  Calmar **1.596** (clean). NOTE this differs slightly from the fully-mooex 1.468
  because NDX stays cc; if the hardcoded FORWARD_SHARPE in (c) uses the fully-mooex
  1.468, align the choice: either hardcode 1.475 (matches the partial-mooex live
  render) OR also overlay the NDX convention delta. Recommend hardcoding the value
  that matches whatever build_artifacts actually computes so live == hardcoded.
- Provide an open/close source at runtime: simplest is to compute the dashboard
  headline from the FROZEN panel (live=False) so the existing macro open cache applies;
  a live=True render needs a live open feed (larger change).

Functions/lines the fixer touches (minimal path): build_dashboard.py 637, 638, (641
note), 656 (auto), plus the hardcoded cells in (c) (57, 2317-2319, 2321-2323,
2402-2410). Optional promotion: add `convention="mooex"` to `cpm_live.run_cpm_backtest`
and `bull_spy_live.run_bull_spy_backtest` (prod sleeve files -- fixer's call, out of
this analyst pass).

LOCALIZED vs DEEP summary: hardcoded swaps = LOCALIZED. Live-render alignment = DEEP
(needs a prod mooex engine + runtime OHLC opens). Full NDX live mooex = BLOCKED
(missing constituent open data); ship NDX as cc with a note.

## (e) Sleeves where mooex could not be cleanly applied (FLAGS)

1. NDX (PARTIAL mooex). The macro open cache has no OHLC for individual NASDAQ-100
   constituents, so NDX-active rebalance days fall back to close-to-close. Only ~201
   of clean-window days carry a nonzero convention delta (ext coverage real=131 /
   fallback=195). The reported NDX mooex (1.2641) is a delta overlay that re-attributes
   the overnight gap ONLY where the held basket is macro-cached (defensive/safe legs).
   Magnitude is small (1.281 -> 1.264, MaxDD unchanged), so the partial result is a
   safe canonical NDX number, but it is NOT a fully-faithful mooex. To make it exact
   would require an OHLC-open feed for every NDX constituent.

2. Benchmarks via the research engine carry a cost-model mismatch vs the production
   `bench_*` functions (turnover-cost vs flip-cost), so their CC baseline through the
   engine (BB4 1.2587) differs from the README's prod-fn CC (BB4 1.194). The pure
   convention delta is reliable (engine-moc -> engine-mooex), but any benchmark VALUE
   swap must be recomputed through the production bench functions with a mooex option,
   not the engine. Not done here because benchmark rows are not hardcoded headline
   cells requiring a swap.

3. Bootstrap CI bounds and the alpha/beta table are downstream artifacts that need a
   re-run on the mooex PROD series (point estimates shift to mooex; bounds/alphas must
   be regenerated). Out of this recompute pass's scope.

## Caveats / confidence

- CONFIDENCE HIGH on CPM (anchor reproduced to 6 dp), BULL (engine moc == prod
  exactly), the PROD/CPM-BULL blends (deterministic blends of those series), and the
  invariance of buy-hold benchmarks.
- CONFIDENCE MEDIUM-HIGH on NDX mooex: the delta overlay is faithful where data exists,
  but it is a PARTIAL mooex (see flag); treat NDX 1.264 as a near-cc approximation.
- CONFIDENCE MEDIUM on the benchmark convention deltas: direction and rough magnitude
  are reliable; absolute values carry the engine cost-model caveat (flag 2).
- PIT/data caveat: all numbers use the FROZEN in-repo panel pinned to EVAL_END
  2026-05-22 (`load_panel(live=False)`) plus the frozen macro open cache. A live
  `python build_dashboard.py` (live=True, end=today) will print a slightly different
  later-window number and, for mooex, requires a runtime open feed not present today.
- Window/end-date/convention stated on every table: clean 2008-05-30..2026-05-22 and
  ext 1999-03-10..2026-05-22, mooex T+1 exact (NEW) vs close-to-close T+1 (OLD),
  both-252, 10 bps/side.

## Reproduction

    .venv/bin/python research/cpm_mooex_migration_recompute.py

Prints the full CC-vs-MOOEX table for every sleeve, blend, and benchmark over both
windows, plus NDX coverage/fallback counts, from the frozen panel.

## Next handoff

- fixer: apply section (c) hardcoded swaps; for live-render consistency implement the
  section (d) minimal plan (switch build_artifacts CPM+BULL to mooex, NDX cc + note,
  align the hardcoded PROD value to what build_artifacts renders). Decide whether to
  promote a `convention="mooex"` flag into cpm_live/bull_spy_live. Regenerate the
  bootstrap CI and alpha/beta artifacts on the mooex series.
- oracle (if needed): confirm the partial-NDX-mooex / cc-with-note resolution is an
  acceptable published convention given the constituent-open-data gap.
