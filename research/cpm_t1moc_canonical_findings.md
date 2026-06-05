# CPM T+1 MOC canonical recompute (close-only, executable)

Role: analyst. Research-only. No production/doc files edited; no commit. Throwaway
harness in `research/`.

Scripts (this work):
- `research/cpm_t1moc_canonical_recompute.py` -> `research/cpm_t1moc_canonical_numbers.json`
  (all sleeves + blend + benchmarks, three conventions moc/mooex/moc1).
- Cross-check of published mooex anchors: `research/ndx_mooex_true_recompute.py`
  (true NDX constituent opens) confirms README mooex PROD/NDX exactly.

Engine: `research/exec_lag_moo_validation_2026_05_30._segment_returns_conv`
(the proven harness used by `cpm_harness` and `build_dashboard`).

## Decision / convention

Canonical execution convention = **T+1 MOC** (`moc1`, `exec_lag=1`): signal
finalizes after EOM close T; the new basket earns `close[af] -> close[af+1]`,
where `af` = first trading day after month-end T. Pure close-based.

Rationale (user, final): T+0 MOC is look-ahead (cannot trade the same close used
to compute the signal); T+1 MOO (`mooex`) needs market-on-open, which the broker
(IBKR mobile) cannot do; T+1 MOC is the honest, executable, close-only convention.
Bonus: close-only -> **no opens cache needed, full coverage, no delisted-opens
issue** (verified: BULL/NDX mooex-fallback was (280,46)/(131,195); under moc1 it is
(0,0)).

Window / data / costs (identical to current canonical run):
- CLEAN: 2008-05-30 .. 2026-05-22 (18.0y). EXT: 1999-03-10 .. 2026-05-22 (27y).
- Panel: `cpm_live.load_panel` frozen at `EVAL_END=2026-05-22` (n=7181 rows,
  1997-12-10..2026-05-22). Both-252 (`CORR_LOOKBACK_DAYS=252`). 10 bps/side.
- CLEAN is the decision lens; EXT is robustness (proxy-backed pre-2006).

Faithful-replication gates (all PASS):
- CPM mooex CLEAN Sharpe = 1.2557 == `cpm_harness.ANCHOR` 1.255673. Engine reproduces
  the canonical anchor exactly.
- CPM `moc` (T+0) == `cpm_live.run_cpm_backtest` (prod CC): Sharpe 1.2926 both.
- PROD blend(`moc`) == blend of prod sleeves: Sharpe 1.4960 both.
- BULL `moc` == `run_bull_spy_backtest` (verified in engine sanity block).
- mooex PROD/NDX (true-opens) == README headline (1.4424/1.2056 clean, 1.3888/1.0785 ext).

Caveats:
- PIT/cached-data: numbers reflect the frozen retail panel + cached macro opens used
  by the canonical harness; not a live-trading reconstruction.
- moc1 is opens-independent, so the NDX macro-only-delta vs true-constituent-opens
  distinction (which splits mooex into 1.2641 macro-only vs 1.2056 true) **vanishes**
  under T+1 MOC. The moc1 NDX/PROD numbers below are canonical regardless of opens path.
- Turnover is convention-invariant (same weight vectors, same rebal dates; only the
  apply-day return attribution differs). Existing figures carry over unchanged:
  CPM ~2.582 one-way/yr (~13.4% fully-safe). No turnover recompute needed.

---

## (a) Full T+1 MOC (moc1) metric set

### CLEAN 2008-05-30 .. 2026-05-22 (post-cost, T+1 MOC close-only)

| series | Sharpe | ExcSh(vs SHV) | CAGR | Vol | MaxDD | Calmar | Martin |
|---|---:|---:|---:|---:|---:|---:|---:|
| CPM | 1.2230 | 1.0934 | 12.76% | 10.28% | -13.61% | 0.9371 | 4.0093 |
| BULL | 0.9737 | 0.8625 | 11.53% | 11.98% | -20.71% | 0.5568 | 2.3958 |
| NDX | 1.1319 | 1.0753 | 26.93% | 23.57% | -34.93% | 0.7710 | 2.7609 |
| **PROD 60/20/20** | **1.3911** | **1.2693** | **15.69%** | **10.94%** | **-10.34%** | **1.5179** | **5.5587** |
| CPM-BULL 60/40 | 1.2428 | 1.1073 | 12.40% | 9.83% | -11.59% | 1.0703 | 4.2458 |
| BB4 (best lit blend) [engine] | 1.2449 | 1.1114 | 12.57% | 9.95% | -16.45% | 0.7640 | 3.6583 |
| BB1 (simplest lit 60/40) [engine] | 1.1595 | 1.0224 | 11.28% | 9.66% | -17.37% | 0.6493 | 3.3688 |
| 60-40 SPY/IEF [engine] | 0.7952 | 0.6753 | 8.76% | 11.42% | -29.78% | 0.2942 | 1.4048 |
| SPY buy-hold (invariant) | 0.6603 | 0.5912 | 11.73% | 19.82% | -50.70% | 0.2313 | 1.0599 |
| QQQ buy-hold (invariant) | 0.8163 | 0.7547 | 16.94% | 22.30% | -49.37% | 0.3432 | 1.4246 |

### EXT 1999-03-10 .. 2026-05-22 (robustness)

| series | Sharpe | ExcSh(vs SHV) | CAGR | Vol | MaxDD | Calmar | Martin |
|---|---:|---:|---:|---:|---:|---:|---:|
| CPM | 1.2307 | 1.0024 | 12.51% | 9.99% | -13.90% | 0.9005 | 3.9344 |
| BULL | 0.9567 | 0.7479 | 10.57% | 11.16% | -20.71% | 0.5106 | 2.4493 |
| NDX | 1.0181 | 0.9011 | 20.13% | 19.97% | -34.93% | 0.5763 | 2.3971 |
| **PROD 60/20/20** | **1.3479** | **1.1225** | **13.96%** | **10.07%** | **-10.34%** | **1.3505** | **5.0076** |
| CPM-BULL 60/40 | 1.2414 | 0.9981 | 11.86% | 9.38% | -11.59% | 1.0231 | 4.1693 |
| BB4 [engine] | 1.1873 | 0.9537 | 11.79% | 9.79% | -16.45% | 0.7168 | 3.6284 |
| BB1 [engine] | 1.1567 | 0.9105 | 10.84% | 9.27% | -17.37% | 0.6242 | 3.6078 |
| 60-40 SPY/IEF [engine] | 0.6922 | 0.4726 | 7.32% | 11.10% | -31.39% | 0.2332 | 1.0739 |
| SPY buy-hold (invariant) | 0.5220 | 0.3939 | 8.50% | 19.24% | -55.19% | 0.1541 | 0.5334 |
| QQQ buy-hold (invariant) | 0.5193 | 0.4273 | 10.89% | 26.91% | -82.96% | 0.1313 | 0.2502 |

**New PROD headline (canonical, CLEAN, T+1 MOC):** Sharpe **1.3911**, Excess-vs-SHV
**1.2693**, CAGR **15.69%**, Vol **10.94%**, MaxDD **-10.34%**, Calmar **1.5179**,
Martin 5.5587. Extended-window Sharpe **1.3479**.

Benchmark note: BB4/BB1/60-40 rows above are the **engine** (turnover-cost) path,
consistent harness with the sleeves. README's published BB4/BB1 (1.194/1.122) came
from `build_dashboard.bench_*` functions (flip-cost, close-to-close), a known
accounting offset (see `cpm_mooex_migration_findings.md`). For exact doc replacement
of the BB rows, the fixer should rerun the `bench_*` path under moc1; the
convention sensitivity is small (BB4 moc->moc1 = -0.014 Sharpe; BB1 = -0.029;
60-40 ~ 0).

---

## (b) Execution-lag table (T+0 MOC / T+1 MOO / T+1 MOC)

This is the memo/README robustness section. T+0 MOC = current prod engine
close-to-close (standard/comparable number, but look-ahead). T+1 MOO = `mooex`
(realistic open-fill, needs opens cache). T+1 MOC = canonical (close-only).
mooex column uses the published true-opens anchors for NDX/PROD (CPM mooex is
opens-cache exact at 1.2557).

### CPM (sleeve)

| window | metric | T+0 MOC | T+1 MOO | **T+1 MOC** |
|---|---|---:|---:|---:|
| CLEAN | Sharpe | 1.2926 | 1.2557 | **1.2230** |
| CLEAN | CAGR | 13.55% | 13.13% | **12.76%** |
| CLEAN | MaxDD | -11.57% | -13.03% | **-13.61%** |
| CLEAN | Calmar | 1.1709 | 1.0076 | **0.9371** |
| EXT | Sharpe | 1.2913 | 1.2549 | **1.2307** |
| EXT | MaxDD | -11.57% | -13.14% | **-13.90%** |
| EXT | Calmar | 1.1368 | 0.9712 | **0.9005** |

### PROD (60/20/20 blend)

| window | metric | T+0 MOC | T+1 MOO | **T+1 MOC** |
|---|---|---:|---:|---:|
| CLEAN | Sharpe | 1.4960 | 1.4424 | **1.3911** |
| CLEAN | CAGR | 17.02% | 16.33% | **15.69%** |
| CLEAN | MaxDD | -10.46% | -10.49% | **-10.34%** |
| CLEAN | Calmar | 1.6263 | 1.5566 | **1.5179** |
| EXT | Sharpe | 1.4308 | 1.3888 | **1.3479** |
| EXT | MaxDD | -10.46% | -10.49% | **-10.34%** |
| EXT | Calmar | 1.4240 | 1.3745 | **1.3505** |

Reading: each session of execution lag costs CPM ~0.033-0.037 Sharpe and PROD
~0.04-0.05 Sharpe per step. T+1 MOC is the harshest honest convention; the
strategy survives it (PROD Sharpe 1.39 clean / 1.35 ext, Calmar > 1.5 / > 1.35).
PROD MaxDD is essentially flat across conventions (-10.3% to -10.5%); the lag
cost is in return/Sharpe, not tail.

For reference, NDX lag table (CLEAN Sharpe): T+0 1.2806 / T+1 MOO 1.2056 / T+1 MOC
1.1319; MaxDD -31.39% / -31.77% / -34.93%.

---

## (c) New CPM anchor + factorial-endpoint implication

**New canonical CPM anchor (CLEAN, T+1 MOC):**
- Sharpe **1.2230** (was mooex 1.2557; delta -0.0327, -2.6%)
- MaxDD **-13.61%** (was -13.03%)
- Calmar **0.9371** (was 1.0076)
- Martin 4.0093 (was 4.2571), CAGR 12.76% (was 13.13%), Vol 10.28% (unchanged)

The `cpm_harness.ANCHOR` of {Sharpe 1.255673, MaxDD -0.130317, Calmar 1.007646} is
the **mooex** anchor. Under the canonical shift it becomes
{Sharpe ~1.2230, MaxDD ~-0.1361, Calmar ~0.9371}. (If the harness `CONVENTION` is
switched to `moc1`, `verify_anchor` must be re-targeted to these values - that is a
fixer change to `research/cpm_harness.py`, out of scope here, flagged.)

**Factorial / HAA->CPM ladder endpoint:** the ladder
(`research/cpm_haa_benchmark_ladder.py`, `CONV="mooex"`) ends at all-ON == CPM. Its
documented endpoint anchor (1.1658 in `cpm_haa_benchmark_ladder_findings.md`) does
**not** match the current canonical CPM mooex 1.2557 - that ladder predates / uses a
slightly different config and should be reconciled independently. Regardless of that,
under T+1 MOC the canonical CPM endpoint is **1.2230** (CLEAN Sharpe).

- Minimum reported: new CPM endpoint = 1.2230 (clean) / 1.2307 (ext).
- **Flag: the full 2^5 ladder needs a separate moc1 rerun** (swap `CONV="mooex"` ->
  `"moc1"` and rerun the 32 cells). Execution lag is approximately a parallel
  downshift (~-0.03 to -0.04 Sharpe per rung), so the mechanism-vs-universe
  attribution *direction* is preserved, but every absolute rung value moves down
  ~0.03-0.04 Sharpe. Same applies to the `bull_factorial_faithful_haa.py` and the
  memo factorial/sensitivity tables (sec. d).

---

## (d) Per-doc OLD (mooex) -> NEW (T+1 MOC) replacement map

Buy-holds (SPY/QQQ) are convention-invariant -> NO change anywhere.

### README.md

| location | OLD (mooex) | NEW (T+1 MOC) |
|---|---|---|
| L30 caption | "(18.0y, mooex T+1, post-cost)" | "(18.0y, T+1 MOC close-only, post-cost)" |
| L34/47 PROD 60/20/20 | 1.442 / 1.321 / 16.33% / 10.93% / -10.49% / 1.56 | 1.3911 / 1.2693 / 15.69% / 10.94% / -10.34% / 1.52 |
| L35 BB4 | 1.194 / 1.061 / 12.03% / 9.94% / -14.55% / 0.83 | 1.2449 / 1.1114 / 12.57% / 9.95% / -16.45% / 0.76 [engine path; see note] |
| L36 BB1 | 1.122 / 0.985 / 10.90% / 9.65% / -14.80% / 0.74 | 1.1595 / 1.0224 / 11.28% / 9.66% / -17.37% / 0.65 [engine path] |
| L44 CPM | 1.2557 / 1.1262 / 13.13% / 10.28% / -13.03% / 1.0076 | 1.2230 / 1.0934 / 12.76% / 10.28% / -13.61% / 0.9371 |
| L45 BULL | 0.984 / 0.872 / 11.60% / 11.92% / -20.41% / 0.57 | 0.9737 / 0.8625 / 11.53% / 11.98% / -20.71% / 0.56 |
| L46 NDX | 1.206 / 1.149 / 29.12% / 23.54% / -31.77% / 0.92 | 1.1319 / 1.0753 / 26.93% / 23.57% / -34.93% / 0.77 |
| L53 CPM anchor | 1.2557 / 13.13% / 10.28% / -13.03% / 1.0076 / 4.2571 | 1.2230 / 12.76% / 10.28% / -13.61% / 0.9371 / 4.0093 |
| L54 CPM-BULL 60/40 | 1.2685 / 12.65% / 9.80% / -11.19% / 1.1312 / 4.4093 | 1.2428 / 12.40% / 9.83% / -11.59% / 1.0703 / 4.2458 |
| L65 Clean checkpoint | NDX 1.206 / 29.12% / -31.77% ; Blend 1.442 / 16.33% / -10.49% | NDX 1.1319 / 26.93% / -34.93% ; Blend 1.3911 / 15.69% / -10.34% |
| L66 Stress (ext) | NDX 1.079 / 21.58% / -31.77% ; Blend 1.389 / 14.42% / -10.49% | NDX 1.0181 / 20.13% / -34.93% ; Blend 1.3479 / 13.96% / -10.34% |
| L203 Accounting | "mooex T+1 exact on apply day; old basket earns overnight..." | "T+1 MOC: new basket earns close[af]->close[af+1] (close-only, no opens)" |
| L229 PROD | 1.442 / 16.33% / -10.49% | 1.3911 / 15.69% / -10.34% |
| L237 alpha Sharpe row | 1.442 | 1.3911 |
| L268 prose | "realized backtest Sharpe is 1.442" | "realized backtest Sharpe is 1.3911" |

README flags (need separate moc1 reruns, NOT done here - out of scope):
- L245 extended Sharpe **point/CI** "1.389 [0.952, 1.640]": point -> 1.3479; the
  block-bootstrap CI must be re-run under moc1.
- L233-241 alpha/beta decomposition (alpha %/yr, beta, corr): regress under moc1.
- BB4/BB1 rows: README values came from the `bench_*` flip-cost path. Either accept
  the engine moc1 numbers above or rerun `bench_*` under moc1 for exact consistency.

### build_dashboard.py

| location | OLD | NEW |
|---|---|---|
| L66 summary string | "Sharpe 1.4424, CAGR 16.33%, MaxDD -10.49%, and Calmar 1.5566" | "Sharpe 1.3911, CAGR 15.69%, MaxDD -10.34%, and Calmar 1.5179" |
| L2454 CPM clean metrics dict | sharpe 1.2557, cagr 0.1313, vol 0.1028, max_drawdown -0.1303, calmar 1.0076, martin 4.2571 | sharpe 1.2230, cagr 0.1276, vol 0.1028, max_drawdown -0.1361, calmar 0.9371, martin 4.0093 |
| L2790 execution caption | "Execution (mooex T+1): ... T+1 OPEN trade (next trading day MOO)" | "Execution (T+1 MOC): month-end signal (T close), trade at CLOSE of next trading day (close-only)" |
| `build_artifacts` (L680-810) | three `"mooex"` convention args + opens-cache legs | three `"moc1"` args, drop opens legs (see sec. e) |

### cpm_memo.md

Principal anchor swaps (direct, safe):

| location(s) | OLD (mooex) | NEW (T+1 MOC) |
|---|---|---|
| L3, L20, L137, L563 prose | "mooex T+1" / "next-session-open" | "T+1 MOC (close-only, trade at next-session close)" |
| L25 RETURN PROFILE | "Sharpe is 1.2557" | "Sharpe is 1.2230" |
| L27 TAIL CONTROL | "MaxDD is -13.03%" | "MaxDD is -13.61%" |
| L31, L59 EOM anchor | 1.2557 (EOM) | 1.2230 (EOM) |
| L146 clean anchor | 1.2557 / -13.03% / 1.0076 | 1.2230 / -13.61% / 0.9371 |
| L150 CPM clean row | 1.2557 / 13.13% / 10.28% / -13.03% / 1.0076 / 4.2571 | 1.2230 / 12.76% / 10.28% / -13.61% / 0.9371 / 4.0093 |
| L185 point | 1.2557 | 1.2230 |
| L207, L251 CPM | 1.26 / 13.13% / -13.03% / 1.01 / 4.26 | 1.22 / 12.76% / -13.61% / 0.94 / 4.01 |
| L261 CPM ext | 1.255 / 12.76% / -13.14% / 0.971 / 4.117 | 1.2307 / 12.51% / -13.90% / 0.9005 / 3.9344 |
| L311 CPM clean | 1.2557 / 1.0076 / -13.03% / 13.13% | 1.2230 / 0.9371 / -13.61% / 12.76% |
| L455 SR_hat | "0.07910 (ann 1.2557)" | "ann 1.2230" (re-derive per-day SR_hat under moc1) |
| L635, L652 all-ON CPM | clean 1.2557 / 1.0076 / -13.03%; ext 1.2549 / 0.9712 / -13.14% | clean 1.2230 / 0.9371 / -13.61%; ext 1.2307 / 0.9005 / -13.90% |

memo flags (derived tables - need separate moc1 sub-analysis reruns, NOT done here):
- L31 signal-offset robustness (EOM/EOM+1/+2/+3): rerun the offset sweep under moc1.
- L330-374 HAA->CPM factor ladder rungs (1.0874->1.2557 etc.): full 2^5 moc1 rerun.
- L442-512 DSR/PBO/sensitivity tables (split rank/cov, both-504, universe rows): rerun.
- L290 yearly attribution table: regenerate under moc1.
- L27 benchmark comparison values (-21.76%/-29.82%/etc.): those peers are
  convention-invariant buy-holds/static -> mostly unchanged; verify the rebalanced ones.

---

## (e) build_artifacts render-change scope (for the fixer)

Goal: revert `build_dashboard.build_artifacts` to **moc1 close-only** so the dashboard
renders the canonical convention and the opens-cache dependency is dropped.

Changes in `build_dashboard.py`:
1. In `build_artifacts` (around L680-755): change all three `_segment_returns_conv`
   `convention` args from `"mooex"` to `"moc1"`:
   - CPM call (~L693), BULL call (~L709), and the NDX overlay.
2. NDX overlay (~L714-755): under moc1 keep the delta-overlay pattern to preserve
   prod delisting-haircut logic, but compute `ndx_delta = (ndx_moc1_full -
   ndx_moc_full)`. Both legs are close-only, so the constituent-opens legs are NOT
   needed. Simplest: pass `None` for intraday/overnight (moc/moc1 ignore them).
3. Remove opens-cache plumbing now unused:
   - `_load_macro_mooex_legs` call (~L680) - macro intraday/overnight no longer used.
   - `_load_ndx_constituent_mooex_legs` (~L585) and its call (~L722).
   - `NDX_OPENS_CACHE_PATH` constant (L64) and the `data/ndx_constituents/opens.parquet`
     file dependency can be REMOVED.
   - `MOOEX_INTRADAY_SANITY_MAX` (only used by the constituent-opens loader).
   - `mooex_coverage` block (~L790-810) becomes trivially full-coverage; either drop
     it or hard-set real=N, fallback=0.
4. The dependency on `research/exec_lag_moo_validation_2026_05_30.load_open_close()`
   (and thus the `/tmp/cpm_open_cache` macro OHLC) is removed; only
   `_segment_returns_conv` is still needed.
5. Update the captions/strings at L66 and L2790 and the CPM metrics dict at L2454
   per sec. (d).

Net effect: build dashboard becomes pure close-to-close-with-1-session-lag, full
coverage on all sleeves and all history, no opens cache, no delisted-opens fragility.

---

## Reproduce

```
.venv/bin/python research/cpm_t1moc_canonical_recompute.py   # full set + lag table + JSON
.venv/bin/python research/ndx_mooex_true_recompute.py         # confirm published mooex anchors
```

Outputs: `research/cpm_t1moc_canonical_numbers.json` (machine-readable, all sleeves x
{moc, mooex, moc1} x {clean, ext}).
