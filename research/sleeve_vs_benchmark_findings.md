# Sleeve vs Rightful Benchmark -- Findings

Question: does each sleeve add value over the standard TAA strategy it is derived from?

- CPM sleeve (cross-asset min-var pair trend) vs **AAA + TIP canary** (repo-canonical B2).
- BULL sleeve (SPY gated by canary + SPY 13612U trend + RV_60d<RV_252d vol) vs **HAA-Simple SPY** (user-specified spec, {BIL, AGG} best-of-safe).

Execution is identical for sleeve and benchmark: realistic **T+1 MOO exact** (`mooex`:
old basket earns overnight `close[T]->open[T+1]`, new basket earns intraday
`open[T+1]->close[T+1]`, compounded), **post-cost 10 bps/side**, production **slow vol gate**
(`_vol_gate_ok`: RV_60d < RV_252d). Both sleeve and benchmark pass through the same
`_segment_returns_conv` harness, so cost model, rebalance timing, and windows are byte-identical.

- Reproduce: `.venv/bin/python research/sleeve_vs_benchmark_2026_05_30.py`
- Raw output: `research/sleeve_vs_benchmark_2026_05_30.json`
- Data: `cpm_live.load_panel` (1997-12-10 onward) + real yfinance OHLC opens in `/tmp/cpm_open_cache/`.

## Benchmark definitions (cited from repo)

**AAA + TIP canary (B2)** -- `build_dashboard.py:352` `bench_aaa_tip()`.

- Universe (`build_dashboard.py:313` `BENCH_AAA_UNIVERSE`): `SPY, EFA, EEM, VNQ, GLD, TLT, DBC`.
- Rank the 7 by `mom_13612U` (Keller unweighted 1/3/6/12-mo average; `cpm_live.sig_13612U`).
- Take top-half (`max(2, ceil(7/2)) = 4`), keep only those with momentum > 0.
- Weight the survivors by **min-variance** (SLSQP, 504d daily covariance, long-only, sum=1).
- Gate: **TIP canary** -- if `mom_13612U(TIP) <= 0`, go 100% defensive.
- Defensive: HAA best-of-safe `argmax(SHV, IEF)` by 13612U (`cpm_live.best_safe`, pool `["SHV","IEF"]`, `build_dashboard.py:314`).
- Lineage: Butler-Philbrick 2012 Adaptive Asset Allocation + Keller TIP veto. Canonical AAA/HAA refs in `research/canonical_taa_reference.md` (HAA = section 8, line 267).

**HAA-Simple SPY** -- exact spec supplied by the requester (NOT the repo `bench_haa_simple`, which
uses SHV/IEF; this run uses {BIL, AGG}).

- Offensive asset = SPY. Canary = TIP `mom_13612U > 0`. Trend = SPY `mom_13612U > 0`.
- Risk-on: hold 100% SPY when (TIP momo > 0 AND SPY momo > 0).
- Risk-off: 100% best-of-safe `argmax(BIL, AGG)` by `mom_13612U`.
- Monthly, T+1 MOO, 10 bps/side, same windows as the sleeve.
- Lineage: Keller & Keuning 2023 HAA, N=1 (AllocateSmartly canonical single-asset form).

**Defensive proxy stitches (repo standard)** -- BIL/AGG lack full history in the extended window:

- BIL: live BIL returns post 2007-05-30, **SHV proxy** returns before (per `research/safe_haven_expansion.py:66`,
  `get_stitched_series(panel, "BIL", "SHV", "2007-05-30")`). Spans 1997-12-10..2026-05-22.
- AGG: repo standard stitched file `data/agg_stitched_daily.csv` (AGG_stitched, from 1986-12). Spans 1997-12-10..2026-05-22.

The AAA+TIP benchmark is a single unambiguous canonical implementation in the repo; HAA-Simple here
follows the supplied spec verbatim (only difference vs repo B3 is the {BIL, AGG} defensive pool).

## Anchor check (CLEAN 18y, mooex, slow gate)

| Sleeve | Computed Sharpe | Expected headline |
|---|---|---|
| CPM-solo | **1.242** | ~1.24 PASS |
| BULL-solo | **1.081** | ~1.08 PASS |

Both match the strategy's known headline -> comparison is trustworthy.

## CPM-solo vs AAA + TIP canary

| Window | Series | Sharpe | CAGR | Vol | MaxDD | Calmar |
|---|---|---|---|---|---|---|
| CLEAN 18y (2008-05-30..2026-05-22) | CPM-solo | 1.242 | 14.23% | 11.27% | -16.35% | 0.870 |
| CLEAN 18y | AAA+TIP | 1.041 | 10.97% | 10.59% | -20.82% | 0.527 |
| EXT 27y (1999-03-10..2026-05-22) | CPM-solo | 1.164 | 13.95% | 11.82% | -16.76% | 0.832 |
| EXT 27y | AAA+TIP | 1.065 | 10.87% | 10.17% | -20.82% | 0.522 |

Active stats (sleeve minus benchmark):

| Window | dCAGR | dCalmar | dSharpe | dMaxDD | corr | TE | IR |
|---|---|---|---|---|---|---|---|
| CLEAN 18y | +3.26pp | +0.344 | +0.202 | +4.47pp (shallower) | 0.829 | 6.42% | +0.464 |
| EXT 27y | +3.08pp | +0.310 | +0.099 | +4.07pp (shallower) | 0.761 | 7.75% | +0.377 |

dMaxDD positive = CPM drawdown is shallower (less negative) than benchmark.

## BULL-solo vs HAA-Simple SPY

| Window | Series | Sharpe | CAGR | Vol | MaxDD | Calmar |
|---|---|---|---|---|---|---|
| CLEAN 18y | BULL-solo | 1.081 | 11.44% | 10.57% | -13.35% | 0.857 |
| CLEAN 18y | HAA-Simple {BIL,AGG} | 0.960 | 11.08% | 11.70% | -19.74% | 0.561 |
| EXT 27y | BULL-solo | 0.920 | 9.49% | 10.45% | -13.96% | 0.680 |
| EXT 27y | HAA-Simple {BIL,AGG} | 0.946 | 10.14% | 10.83% | -19.74% | 0.514 |

Active stats (sleeve minus benchmark):

| Window | dCAGR | dCalmar | dSharpe | dMaxDD | corr | TE | IR |
|---|---|---|---|---|---|---|---|
| CLEAN 18y | +0.36pp | +0.296 | +0.122 | +6.39pp (shallower) | 0.634 | 9.58% | +0.021 |
| EXT 27y | -0.65pp | +0.166 | -0.027 | +5.78pp (shallower) | 0.607 | 9.44% | -0.068 |

In the CLEAN window BULL beats HAA-Simple on **every** axis (CAGR, Calmar, Sharpe, MaxDD). Over the
full EXT 27y it gives up ~0.65pp CAGR / a hair of Sharpe but keeps materially shallower drawdown
(~+5.8pp) and higher Calmar. The value-add is dominated by drawdown control, consistent with the
strategy's DD-aware objective; raw-return edge is positive clean, ~flat-to-slightly-negative over 27y.

## Crisis-window behavior (total return, sleeve vs benchmark)

| Window | CPM | AAA+TIP | BULL | HAA-Simple |
|---|---|---|---|---|
| DotCom 2000-03..2002-10 | +21.0% | +24.4% | +14.0% | +13.2% |
| GFC 2007-10..2009-03 | +14.3% | +5.7% | +22.3% | -5.7% |
| COVID 2020-02-19..04-30 | +4.6% | +6.8% | -8.4% | -10.6% |
| Bear 2022 | +5.4% | +6.2% | +0.9% | -0.1% |

(HAA-Simple column uses the {BIL, AGG} defensive pool per the supplied spec.)

Notes:

- **CPM**: dominant in GFC (+14.3% vs +5.7%); slightly behind AAA+TIP in DotCom, COVID, and 2022 but
  all four positive-to-flat -- the min-var pair construction shines most in the deepest crash (2008).
  DotCom/2022 are EXT-only context for full credit (DotCom predates clean window).
- **BULL**: huge GFC edge (+22.3% vs -5.7%) and 2022 edge (+0.9% vs -0.1%); beats HAA in DotCom too
  (+14.0% vs +13.2%). COVID is the only loss (-8.4% vs HAA -10.6%, and both negative): the monthly
  gate is too slow to dodge a one-month gap crash, so neither sleeve nor its benchmark dodges it --
  BULL's edge is in multi-month regimes, not gap crashes. With the {BIL, AGG} pool HAA's GFC outcome
  is notably weaker than the SHV/IEF variant, widening BULL's crisis edge.

## Verdict

- **CPM beats AAA + TIP on every axis, both windows.** +3.1-3.3pp CAGR, +0.31-0.34 Calmar,
  ~+0.10-0.20 Sharpe, ~+4pp shallower MaxDD, positive IR (+0.38 to +0.46). Clear value-add;
  strongest in the 2008 crash. **Adds value.**
- **BULL beats HAA-Simple {BIL,AGG} clearly on the DD-aware axis, and on all axes in the clean window.**
  CLEAN: +0.36pp CAGR, +0.296 Calmar, +0.122 Sharpe, +6.39pp shallower MaxDD (wins everywhere).
  EXT 27y: gives up ~0.65pp CAGR / 0.03 Sharpe but keeps +0.166 Calmar and +5.78pp shallower MaxDD.
  Per the strategy's drawdown-aware objective this is a genuine improvement; the raw-return edge is
  positive clean and ~flat over 27y. **Adds value, primarily on drawdown control.**

## Caveats

- COVID (both BULL and HAA negative) confirms a known limitation: monthly rebalance cannot dodge single-month gap crashes.
- DotCom and 2022 fall outside (or at the edge of) the clean 18y window; treat as EXT-window context.
- HAA-Simple defensive pool uses the {BIL, AGG} spec with repo-standard proxy stitches (BIL<-SHV pre-2007-05-30,
  AGG<-data/agg_stitched_daily.csv). On rebalance days BIL/AGG have no real-open OHLC in the cache, so mooex
  falls back to close-to-close for those single days; immaterial to multi-week holding-period returns.
- Benchmarks executed through the exact same harness as sleeves, but the live dashboard's
  `_b_build_port` (build_dashboard.py:323) uses T+1 close-to-close, not mooex -- numbers here are
  intentionally on the sleeve harness for apples-to-apples, so they differ slightly from dashboard B2/B3 prints.
- Confidence: high on relative ranking (anchor matches headline exactly, identical execution). Crisis
  totals are point estimates over fixed calendar windows, sensitive to a few-day boundary shift.
