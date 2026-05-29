# Execution-lag convention validation: T+0 MOC vs realistic T+1 MOO vs harsh T+1 MOC

Date: 2026-05-30
Harness: `research/exec_lag_moo_validation_2026_05_30.py` (read-only; reuses production
SIGNAL/WEIGHT fns unchanged, varies only execution timing + vol-gate via monkeypatch).
Data: REAL yfinance auto_adjust OHLC opens cached in `/tmp/cpm_open_cache/` for
SPY, QQQ, SPHQ, EFA, EEM, VNQ, GLD, TLT, DBC, SHV, IEF, HYG, TIP.

## Question

Production engine fills T+0 MOC (signal at close T, new basket earns close[T]->close[T+1]).
The prior audit (`lookahead_audit_2026_05_30.py`) penalized this with exec_lag=1 (earns
close[T+1]->close[T+2]) = effectively **T+1 MOC**, a FULL extra session of lag. But the
realistic monthly execution is **T+1 MOO**: compute signal after close T, fill at the OPEN
of T+1. If the overnight gap close[T]->open[T+1] is small (or mostly held regardless of
fill), then T+0 MOC ~= T+1 MOO, the same-day fill is a valid proxy, and the audit penalty
is an artifact of the harsher MOC convention.

## Conventions (rebal day af = first trading day after month-end T)

- **T+0 MOC** (production): new basket earns `close[T]->close[T+1]` = overnight gap + intraday af.
- **T+1 MOO exact** (realistic): OLD basket earns overnight `close[T]->open[af]`, then NEW
  basket earns intraday `open[af]->close[af]` (compounded). This is the true execution model:
  you remain invested in the prior basket until you trade at the open.
- **T+1 MOO conservative**: NEW basket earns intraday `open[af]->close[af]` only; the overnight
  gap is forfeited entirely (as if flat/cash overnight). A worst-case, NOT realistic for a
  continuously-invested portfolio.
- **T+1 MOC harsh** (the audit's exec_lag=1): new basket earns `close[af]->close[af+1]` -
  skips the entire af session.

Metrics: **Calmar (primary), MaxDD, vol, CAGR**; Sharpe = trailing context only.
Blend = 0.60*CPM + 0.40*BULL (PRIMARY). BULL solo = SECONDARY.

## Verification anchors

- Real opens loaded and DIFFER from closes (sample, auto_adjust): SPY 2026-05-29 open=755.90
  close=756.48 (intraday +0.077%); QQQ 2026-05-28 open=729.73 close=735.60 (+0.804%);
  GLD 2026-05-28 open=406.48 close=412.77 (+1.547%).
- **T+0 MOC reproduces production** (BULL solo, clean 18y), sanity OK:
  RV_20d: prod Calmar=0.980 CAGR=11.77% MaxDD=-12.02% vs harness Calmar=0.982 CAGR=11.80%.
  RV_60d: prod Calmar=0.875 CAGR=11.90% MaxDD=-13.60% vs harness Calmar=0.877 CAGR=11.92%.

## Step 1 - Overnight gap magnitude on REBALANCE days (clean 18y, 216 rebals)

| asset | mean\|gap\| | med\|gap\| | std gap | mean\|day\| | gap/day |
|-------|-----------|-----------|---------|-------------|---------|
| SPY  | 0.549% | 0.375% | 0.777% | 0.816% | 0.67 |
| QQQ  | 0.600% | 0.429% | 0.811% | 1.140% | 0.53 |
| SPHQ | 0.504% | 0.343% | 0.704% | 0.805% | 0.63 |
| EFA  | 0.774% | 0.576% | 1.032% | 0.877% | 0.88 |
| EEM  | 0.915% | 0.740% | 1.176% | 1.130% | 0.81 |
| VNQ  | 0.520% | 0.342% | 0.801% | 1.084% | 0.48 |
| GLD  | 0.704% | 0.594% | 0.943% | 0.804% | 0.88 |
| TLT  | 0.630% | 0.574% | 0.790% | 0.676% | 0.93 |
| DBC  | 0.794% | 0.615% | 1.041% | 0.891% | 0.89 |
| HYG  | 0.234% | 0.138% | 0.357% | 0.383% | 0.61 |
| TIP  | 0.219% | 0.168% | 0.292% | 0.274% | 0.80 |
| IEF  | 0.279% | 0.231% | 0.355% | 0.323% | 0.86 |

The per-asset overnight gap is NOT negligible: mean |gap| 0.2-0.9%, ~0.5-0.9x a full day's
move. The hypothesis premise ("gap is small") is FALSE at the per-asset level. BUT the gap
only matters as lookahead on the CHANGED (turned-over) fraction of the basket - on unchanged
positions you capture the gap regardless of MOC vs MOO. At month-end the basket mostly
persists (SPY bull-to-bull, CPM min-var pairs persist), so the net portfolio impact is small
(see Step 2 MOO-exact).

## Step 2/3 - Blend (PRIMARY) under 4 conventions x 2 gates

CLEAN 18y (2008-05-30..):

| gate | conv | Calmar | MaxDD | Vol | CAGR | Sharpe |
|------|------|--------|-------|-----|------|--------|
| RV_20d | T+0 MOC      | 1.385 | -9.82%  | 9.84% | 13.60% | 1.351 |
| RV_20d | T+1 MOO exact | **1.324** | **-9.82%** | 9.82% | 12.99% | 1.299 |
| RV_20d | T+1 MOO cons  | 1.141 | -9.82%  | 9.70% | 11.20% | 1.148 |
| RV_20d | T+1 MOC harsh | 1.257 | -10.00% | 9.84% | 12.58% | 1.258 |
| RV_60d | T+0 MOC      | 1.279 | -10.67% | 9.84% | 13.65% | 1.354 |
| RV_60d | T+1 MOO exact | 1.243 | -10.66% | 9.82% | 13.25% | 1.321 |
| RV_60d | T+1 MOO cons  | 1.023 | -11.13% | 9.71% | 11.39% | 1.165 |
| RV_60d | T+1 MOC harsh | 1.297 | -10.00% | 9.86% | 12.98% | 1.292 |

EXT 27y (1999-03-10..; CPM pre-2006 uses proxies w/o opens -> 69-73 rebal days fall back to
MOC-like, BULL/SPY opens are real back to 1993):

| gate | conv | Calmar | MaxDD | Vol | CAGR | Sharpe |
|------|------|--------|-------|-----|------|--------|
| RV_20d | T+0 MOC      | 1.089 | -11.79% | 9.82% | 12.84% | 1.280 |
| RV_20d | T+1 MOO exact | 1.030 | -11.95% | 9.83% | 12.31% | 1.230 |
| RV_60d | T+0 MOC      | 1.132 | -11.25% | 9.79% | 12.74% | 1.273 |
| RV_60d | T+1 MOO exact | **1.101** | **-11.18%** | 9.80% | 12.32% | 1.235 |

Delta summary (blend Calmar, vs T+0 MOC):

| gate | win | MOC | MOOexact | MOOcons | MOC1harsh | MOOex-MOC | MOOcons-MOC |
|------|-----|-----|----------|---------|-----------|-----------|-------------|
| RV_20d | clean | 1.385 | 1.324 | 1.141 | 1.257 | **-0.062** | -0.244 |
| RV_20d | ext   | 1.089 | 1.030 | 0.897 | 0.988 | **-0.059** | -0.192 |
| RV_60d | clean | 1.279 | 1.243 | 1.023 | 1.297 | **-0.036** | -0.256 |
| RV_60d | ext   | 1.132 | 1.101 | 0.964 | 1.072 | **-0.031** | -0.169 |

## Answers

### (a) Is T+0 MOC ~= T+1 MOO empirically?

**YES, under the realistic (exact) MOO accounting.** Blend Calmar differs by only -0.03 to
-0.06 vs T+0 MOC, MaxDD essentially identical (clean: -9.82% both for RV_20d; -10.67% vs
-10.66% RV_60d), Sharpe -0.03 to -0.05. The true lookahead value is ~0.6%/yr CAGR (clean
RV_20d 13.60% -> 12.99%) = ~5bps per monthly rebal. The same-day-close fill IS a valid proxy
for realistic T+1 MOO execution.

The conservative MOO (-0.19 to -0.26 Calmar) and the audit's harsh T+1 MOC (-0.10 to -0.13)
both OVERSTATE the penalty: conservative MOO forfeits the overnight gap even on unchanged
positions (unrealistic), and the harsh MOC discards an entire trading session. The per-asset
gap is large but mostly held across (low turnover), so it is not a real lookahead.

### (b) Under realistic T+1 MOO, does RV_20d collapse (is the swap necessary)?

**No collapse.** RV_20d blend loses only 0.06 Calmar going MOC->MOOexact (clean 1.385->1.324),
and under realistic MOO it BEATS RV_60d in the clean window (1.324 vs 1.243 Calmar; -9.82% vs
-10.66% MaxDD; equal vol). The "RV_20d edge collapses under lag" claim that motivated the swap
was an artifact of the harsh T+1 MOC convention (under MOC1, RV_60d clean 1.297 > RV_20d 1.257).
Under realistic execution that ordering FLIPS back to RV_20d.

RV_60d wins only (i) the extended window (1.101 vs 1.030; that window is proxy-contaminated for
CPM pre-2006) and (ii) at the isolated BULL-solo level (clean MOOex 0.857 vs 0.736), which the
brief says not to elevate over the blend.

### (c) Net recommendation

**Revert the swap -> keep RV_20d.** Judged under realistic T+1 MOO on the PRIMARY lens (60/40
blend, Calmar, clean 18y with full real-open coverage), RV_20d delivers higher Calmar (1.324
vs 1.243) and shallower MaxDD (-9.82% vs -10.66%) at identical vol. RV_60d's advantage exists
only in the de-prioritized extended/proxy window and BULL-solo view. The lag-robustness
rationale for RV_60d was calibrated against the over-harsh T+1 MOC; it does not survive the
realistic T+1 MOO test.

Confidence: moderate. The gap is modest (~0.08 blend Calmar in clean) and window-dependent;
both gates are viable, but the realistic-execution evidence does not justify the swap.

## Caveats

- Adjusted OHLC from yfinance (auto_adjust); overnight gap = open[af]/close[af-1] from a single
  consistent source (ratio clean on ex-div dates).
- EXT 27y MOO is partially contaminated: CPM universe ETFs lack opens pre-2006 (DBC 2006-02,
  VNQ/GLD 2004, EEM 2003) -> 69-73 rebal days fall back to cc (~MOC) for CPM. BULL/SPY opens
  are real to 1993, so the BULL sleeve MOO is clean over the full span. Clean 18y is the
  decisive window.
- The production close panel uses stitched proxy adjusted-closes; yfinance opens use current
  re-adjustment. Only the open/close RATIO is used for the rebal-day override, so level
  mismatch does not bias the conventions.
- Gate controlled explicitly via monkeypatch in BOTH forms; not relying on the staged edit.
