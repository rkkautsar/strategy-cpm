# CPM-BULL-NDX

**60% CPM + 20% BULL + 20% NDX.** Personal runbook. Sleeve-level
canaries plus trend/vol gates are the defensive machinery.

- **Cross-asset Parity Momentum (CPM) (60%)** - 8-asset risky universe
  (QQQ, SPHQ, EFA, EEM, VNQ, GLD, TLT, DBC), TIP-only canary,
  EAA-style Vol-Adj (Faber/Vol) ranker, positive-trend screen, top-K=4 candidate screen,
  equal-weight risky block, n_pos=4 min-var holds 3 of those 4 candidates,
  strict-4 partial-safe, timed best-safe (SHV/IEF).
- **BULL (20%)** - HAA-Simple Extension on SPY with 2-layer monthly gate:
  Canary (TIP), Trend (SPY mom_13612U > 0).
  Either fully invested in SPY (when both pass) or fully in HAA
  best-of-safe (SHV/IEF).
- **NDX (20%)** - top-5 PIT Nasdaq-100 stocks by raw 13612U momentum
  (positive only), 20% each, independently gated by Canary (TIP),
  Trend (SPY mom_13612U > 0), and RV Crossover
  (vol_ok: rv_20d(SPY) < rv_252d(SPY)).
  If all three pass, NDX runs equal-weight top-5; otherwise,
  NDX allocates 100% best_safe (SHV/IEF).

Monthly rebalance on the last trading day of each calendar month, ETF +
individual stocks, no leverage, 10 bps/side cost. Total-return prices
(yfinance `auto_adjust=True`). Tax-advantaged accounts only.

> WARNING: **Not yet live-traded.** All validation is backtest.

## Headline performance

Clean live-ETF window 2008-05-30 -> 2026-05-22 (18.0y, mooex = T+1 market-on-open execution, post-cost).

| Strategy | Raw Sharpe (0rf) | Excess Sharpe (vs SHV) | CAGR | Vol | MaxDD | Calmar |
|---|---:|---:|---:|---:|---:|---:|
| **PROD 60/20/20** | **1.442** | **1.321** | **16.33%** | **10.93%** | **-10.49%** | **1.56** |
| Best literature blend (BB4) | 1.194 | 1.061 | 12.03% | 9.94% | -14.55% | 0.83 |
| Simplest literature 60/40 (BB1) | 1.122 | 0.985 | 10.90% | 9.65% | -14.80% | 0.74 |
| SPY buy-hold | 0.660 | 0.591 | 11.73% | 19.82% | -50.70% | 0.23 |
| QQQ buy-hold | 0.816 | 0.755 | 16.94% | 22.30% | -49.37% | 0.34 |

Sleeve (clean window, post-cost):

| Sleeve | Raw Sharpe (0rf) | Excess Sharpe (vs SHV) | CAGR | Vol | MaxDD | Calmar |
|---|---:|---:|---:|---:|---:|---:|
| CPM | 1.2557 | 1.1262 | 13.13% | 10.28% | -13.03% | 1.0076 |
| BULL | 0.984 | 0.872 | 11.60% | 11.92% | -20.41% | 0.57 |
| NDX | 1.206 | 1.149 | 29.12% | 23.54% | -31.77% | 0.92 |
| PROD 60/20/20 | 1.442 | 1.321 | 16.33% | 10.93% | -10.49% | 1.56 |

Clean-window anchors (CPM-focused):

| Variant | Sharpe | CAGR | Vol | MaxDD | Calmar | Martin |
|---|---:|---:|---:|---:|---:|---:|
| Cross-asset Parity Momentum (CPM) | 1.2557 | 13.13% | 10.28% | -13.03% | 1.0076 | 4.2571 |
| CPM-BULL 60/40 (two-sleeve, no NDX) | 1.2685 | 12.65% | 9.80% | -11.19% | 1.1312 | 4.4093 |

CPM concentration (clean, average dollar-weight / exposure share):
SPHQ 23.1%, GLD 18.1%, QQQ 13.4%, TLT 12.7%, EFA 12.1%, DBC 9.0%, VNQ 6.8%, EEM 4.9%.

Cross-note: this is an exposure-share metric. `cpm_memo.md` reports risk-contribution share, which is a different metric.

NDX is a leveraged-beta expression of Nasdaq growth via top-5 raw 13612U momentum under its own monthly TIP + SPY trend + SPY RV20<RV252 gate. Treat it as a beta amplifier with bounded downside (20% weight + 4% single-name cap), because its +0.12 Sharpe edge vs plain gated QQQ is roughly offset by selection-stage survivorship bias (~-0.11).

Raw-momentum checkpoints:

| Window | NDX Sharpe | NDX CAGR | NDX MaxDD | Blend Sharpe | Blend CAGR | Blend MaxDD |
|---|---:|---:|---:|---:|---:|---:|
| Clean | 1.206 | 29.12% | -31.77% | 1.442 | 16.33% | -10.49% |
| Stress (live-ETF 1999-03-10 start) | 1.079 | 21.58% | -31.77% | 1.389 | 14.42% | -10.49% |

## Alpha decomposition

OLS daily-return regression `r_strat = alpha + beta * r_bench`:

| Strategy | Benchmark | Alpha (%/yr) | Beta | Corr |
|---|---|---:|---:|---:|
| CPM | B2: AAA + TIP canary (same universe) | +4.96 | 0.813 | 0.838 |
| BULL | B3: HAA-Simple SPY | Equivalent (TIP-only gate; no residual alpha) | 1.000 | 1.000 |
| **PROD 60/20/20** | **BB4 (best lit 60/20/20)** | **+5.27** | **0.932** | **0.848** |
| PROD 60/20/20 | BB1 (60% AAA+TIP + 40% HAA-S SPY) | +5.92 | 0.962 | 0.849 |
| NDX | QQQ buy-hold | +24.16 | 0.329 | 0.311 |

Buy-hold equity alpha is mechanically inflated by time spent in cash/safe (low realized beta) and is not analytically meaningful. The peer-blend alpha (+5.27 vs BB4, +5.92 vs BB1) is the real claim.

See `research/alpha_beta_refresh_2026_05_28.log`.

## Strategy specification

```python
# ------------------------------------------------------------------------
# Shared definitions (monthly signal date T = last trading day of month)
# ------------------------------------------------------------------------
mom_13612U(A)     = (r1 + r3 + r6 + r12) / 4                # Keller HAA canonical
faber_score(A)    = (price[T] - SMA_10mo) / SMA_10mo        # Faber 2007
vol_252d(A)       = annualized daily standard deviation of A over last 252d
rv_20d(A)         = annualized daily standard deviation of A over last 20d
rv_252d(A)        = annualized daily standard deviation of A over last 252d
eaa_score(A)      = faber_score(A) / vol_252d(A)            # EAA Vol-Adj (CPM sleeve)
is_fully_valid(t) =
    has 12m momentum history
    and has current adjusted price
    and is tradable at T+1 open
best_safe         = argmax({mom_13612U(s) for s in [SHV, IEF]})

# ------------------------------------------------------------------------
# Cross-asset Parity Momentum (CPM) (60%)
# ------------------------------------------------------------------------
CPM_UNIVERSE = [QQQ, SPHQ, EFA, EEM, VNQ, GLD, TLT, DBC]         # N=8

canary_ok = (mom_13612U(TIP) > 0)

if not canary_ok:
    cpm = {best_safe: 1.0}
else:
    ranked = top_K(CPM_UNIVERSE, key=eaa_score, K=4)              # K=4 candidate screen
    pos    = [A for A in ranked if faber_score(A) > 0]           # positive-trend survivors
    n_pos  = len(pos)
    if n_pos == 0:
        cpm = {best_safe: 1.0}
    else:
        risky_fraction = min(n_pos, 4) / 4.0                      # n_pos<4 => each survivor gets 1/4
        safe_fraction  = 1.0 - risky_fraction
        risky_set = pos
        if n_pos == 4:
            risky_set = min_var_subset_3_of_4(pos)                # full breadth: hold 3 of 4 candidates
        eq_w = 1.0 / len(risky_set)
        cpm = {A: eq_w * risky_fraction for A in risky_set}
        if safe_fraction > 0:
            cpm[best_safe] = cpm.get(best_safe, 0.0) + safe_fraction

# ------------------------------------------------------------------------
# BULL (20%) -- HAA-Simple Extension on SPY
# 2-layer gate: TIP Canary + SPY Trend
# ------------------------------------------------------------------------
canary_ok    = (mom_13612U(TIP) > 0)
asset_mom_ok = (mom_13612U(SPY) > 0)

if canary_ok AND asset_mom_ok:
    bull = {SPY: 1.0}
else:
    bull = {best_safe: 1.0}

# ------------------------------------------------------------------------
# NDX (20%) -- independent top-K PIT Nasdaq-100 momentum
# ------------------------------------------------------------------------
canary_ok = (mom_13612U(TIP) > 0)
trend_ok  = (mom_13612U(SPY) > 0)
vol_ok    = (rv_20d(SPY) < rv_252d(SPY))

if not (canary_ok AND trend_ok AND vol_ok):
    ndx = {best_safe: 1.0}
else:
    pool     = PIT_NDX100_constituents(T)
    eligible = [t for t in pool if mom_13612U(t) > 0 and is_fully_valid(t)]
    picks    = top_K(eligible, key=lambda t: mom_13612U(t), K=5)
    if len(picks) == 0:
        ndx = {best_safe: 1.0}
    else:
        ndx = {t: 0.20 for t in picks}               # 20% each, K=5
        if len(picks) < 5:                           # partial-fill -> safe
            ndx[best_safe] = 1.0 - 0.20 * len(picks)
```

**NDX de-risk overlay (researched, not adopted).** A discrete vol target -- sending the lowest-momentum slots to safe when the basket's short-window realized vol exceeds ~1.0x QQQ's expanding long-run vol (~24%), anchored to the parent index rather than a fixed constant -- cuts the sleeve's 2021 growth-unwind drawdown from -31% to -22%. It is not used in production: at the 20% blend weight NDX's drawdown already diversifies away (the binding blend drawdown sits in the CPM and BULL sleeves), so the overlay only costs ~1pp blend CAGR without improving headline risk. NDX runs top-5 EW as the portfolio's CAGR engine.

```
# ------------------------------------------------------------------------
# Blend
# ------------------------------------------------------------------------
portfolio = 0.60 * cpm + 0.20 * bull + 0.20 * ndx
```

**Universe:**

| Pool | Tickers |
|---|---|
| Cross-asset Parity Momentum (CPM) universe (8) | QQQ, SPHQ, EFA, EEM, VNQ, GLD, TLT, DBC |
| BULL (1) | SPY |
| Safe pool (HAA best-of by 13612U) | SHV (ultra-short), IEF (7-10y) |
| Cross-asset Parity Momentum (CPM) canary | TIP |
| BULL canary | TIP |
| BULL trend gate | SPY mom_13612U > 0 |
| NDX gate | TIP canary AND SPY mom_13612U > 0 AND rv_20d(SPY) < rv_252d(SPY) |
| NDX pool | point-in-time Nasdaq-100 (top-5 by raw 13612U momentum, 20% each) |

**Method lineage:**

| Component | Source |
|---|---|
| Cross-asset Parity Momentum (CPM) top-4 candidate screen + equal-weight risky block + n_pos=4 min-var 3-of-4 hold + strict-4 partial-safe | This work |
| Timed safe sleeve (SHV/IEF by 13612U) | Keller & Keuning 2022 HAA family |
| 13612U momentum | Keller & Keuning 2022 HAA canonical |
| TIP canary | Keller & Keuning 2022 HAA canonical |
| HAA-Simple skeleton (N=1) | AllocateSmartly summary of Keller HAA |
| EAA Vol-Adj (Faber/Vol) ranker | Elastic Asset Allocation (Keller & Butler 2014) |
| US factor-ETF universe (QQQ, SPHQ) | This work |
| Independent NDX sleeve gate (TIP + SPY trend + RV20<RV252) | This work |
| Top-K cross-sectional (NDX) | Jegadeesh & Titman 1993 |
| PIT NDX-100 constituents | `index-constitution` library (>= 2006-01) |
| Deflated Sharpe | Bailey & Lopez de Prado 2012 |

**Execution:**

- Signal date: last trading day of each calendar month (close).
- Trade date: T+1 OPEN (next-day MOO).
- Accounting: mooex T+1 exact on apply day; old basket earns overnight
  close[T] -> open[T+1], new basket earns intraday open[T+1] -> close[T+1].
- Cost: 10 bps/side on any state change (full A->B switch = 20 bps).
- Cron: monthly, 10am SGT (first business day after month-end).

**Performance-stat conventions:**

- CAGR = `eq[-1] ** (1/years) - 1`, years = calendar_days / 365.25.
- Sharpe = annualized at 0% rf (`daily.mean() * 252 / (daily.std() * sqrt(252))`).
- Excess Sharpe = excess.mean() * 252 / (excess.std(ddof=0) * sqrt(252)), excess_daily = strategy_daily - SHV_daily.
- Vol = `std(daily) * sqrt(252)`, ddof=0.
- MaxDD = trough below highest prior peak.
- Calmar = CAGR / |MaxDD|.
- Alpha/beta: OLS daily returns, annualized as `alpha_daily * 252`.

## Literature benchmarks

| Strategy | Source | Sharpe | CAGR | MaxDD |
|---|---|---:|---:|---:|
| B1: AAA standard (no canary) | Butler-Philbrick 2012 | 0.861 | 10.05% | -19.87% |
| B2: AAA + TIP canary | This + Keller TIP | 0.964 | 10.11% | -18.80% |
| B3: HAA-Simple SPY | Keller 2022 | 0.981 | 11.65% | -20.28% |
| B4: HAA-Simple QQQ | Keller 2022 variant | 0.859 | 13.13% | -28.56% |
| B5: QQQ 12mo trend (Antonacci-family TSMOM single-asset) | Faber/Antonacci 12mo absolute trend | 0.909 | 16.44% | -28.56% |
| BB1: 60 B2 + 40 B3 (60 AAA+TIP / 40 HAA-S SPY) | Two-sleeve blend | 1.122 | 10.90% | -14.80% |
| BB4: 60 B2 + 20 B3 + 20 B5 | Three-sleeve blend (best lit) | 1.194 | 12.03% | -14.55% |
| **PROD 60/20/20** | This work | **1.442** | **16.33%** | **-10.49%** |

## Robustness

PROD 60/20/20 bootstrap CI on mooex-accounted daily returns (B=2000, block=21d, seed=42):

| Metric | Point | p2.5 | p25 | p50 | p75 | p97.5 |
|---|---:|---:|---:|---:|---:|---:|
| Sharpe | 1.4424 | 1.0315 | 1.2939 | 1.4448 | 1.5932 | 1.8764 |
| CAGR | 16.33% | 11.31% | 14.50% | 16.35% | 18.25% | 21.84% |
| Vol | 10.93% | 10.12% | 10.66% | 10.94% | 11.22% | 11.80% |
| MaxDD | -10.49% | -20.59% | -15.22% | -13.14% | -11.64% | -9.47% |
| Calmar | 1.5566 | 0.6423 | 0.9877 | 1.2339 | 1.4818 | 2.0900 |

95% CI summary: **Sharpe [1.03, 1.88]**, CAGR [11.31%, 21.84%], MaxDD
[-20.59%, -9.47%], Calmar [0.64, 2.09].
Extended-window Sharpe point/CI (live-ETF 1999-03-10 start): **1.389 [0.952, 1.640]**. Difference block bootstrap
for strategy deltas vs BB4/benchmarks is summarized in win probabilities below.
Script + log + JSON in `research/bootstrap_ci_2026_05_28.{py,log,json}`.

Cost sensitivity (clean 2008-05-30..2026-05-22, mooex, both-252)

```
                CPM sleeve                          PROD 60/20/20 blend
Cost/side   Sharpe  Calmar    CAGR   MaxDD      Sharpe  Calmar    CAGR   MaxDD
10 bps      1.2557  1.0076   13.13%  -13.03%    1.4424  1.5566   16.33%  -10.49%
25 bps      1.1504  0.8978   11.93%  -13.29%    1.3397  1.4259   15.05%  -10.55%
50 bps      0.9712  0.7257    9.96%  -13.73%    1.1648  1.1690   12.94%  -11.07%

Extended-window Sharpe (1999-03-10..): CPM 1.2549 / 1.1518 / 0.9760;
                                       PROD 1.3888 / 1.2854 / 1.1091.
```

Execution-lag sensitivity, CLEAN 2008-05-30..2026-05-22 (both-252, 10 bps/side)

```
CPM sleeve            T+0 MOC   T+1 MOO   T+1 MOC
  Sharpe              1.2926    1.2557    1.2230
  CAGR                13.55%    13.13%    12.76%
  MaxDD              -11.57%   -13.03%   -13.61%
  Calmar              1.1709    1.0076    0.9371

PROD 60/20/20         T+0 MOC   T+1 MOO   T+1 MOC
  Sharpe              1.4960    1.4424    1.3911
  CAGR                17.02%    16.33%    15.69%
  MaxDD              -10.46%   -10.49%   -10.34%
  Calmar              1.6263    1.5566    1.5179

Extended-window Sharpe: CPM 1.2913 / 1.2549 / 1.2307; PROD 1.4308 / 1.3888 / 1.3479.
```

T+1 MOO is realistic executable convention (signal at month-end close, fill at next-session open), and remains close to T+0 MOC ideal with tail nearly invariant across lag conventions.

## Key caveats

**Tax & live status**

- Monthly rotation creates short-term gains. Tax-advantaged accounts only.
- Strategy is NOT live-traded. All performance is backtest.
- DBC inception 2006-02 is the binding universe start; backtest starts
  2008-05-30 to give 13mo momentum warmup with all-live ETFs.

**Reproducibility**

- Stitched proxy series for pre-ETF history are documented in
  `cpm_live.py:load_panel`. Source: `data/proxy_adjusted_close_daily.csv`.
- yfinance retroactively re-adjusts splits/dividends, causing minor drift
  over time (+/-0.05 Sharpe across reproductions). Headline numbers use a
  frozen panel snapshot.
- Third-party reproductions on yfinance ETF-only data typically land within
  Sharpe -0.05 to -0.15 of headline due to signal-date convention, cost
  application timing, NaN handling, and `pandas.cov` ddof choice.
- The realized backtest Sharpe is 1.442. Retail-data reproductions may be
  modestly lower due to implementation differences. For capital planning, use
  materially lower forward assumptions, such as 0.7-1.0 Sharpe, and treat 1.3+
  as an upside case until live/paper trading confirms signal fidelity.
- **Vs BB4 lit blend (paired block bootstrap, B=5000, block=21d):**
  Clean P(dSharpe > 0) = 87.92%, P(dSharpe > 0.10) = 69.02%.
  Extended P(dSharpe > 0) = 90.60%, P(dSharpe > 0.10) = 68.08%.
- **Vs Static 80% PP + 20% QQQ:** P(dSharpe > 0) = 98.26%,
  P(dSharpe > 0.20) = 89.42%, P(dCAGR > 0) = 99.98%,
  P(MaxDD shallower) = 74.56%.
- **Vs SPY buy-hold:** P(dSharpe > 0) = 99.98%,
  P(MaxDD shallower) = 99.96%.
- **Vs QQQ buy-hold:** P(dSharpe > 0) = 99.78%,
  P(MaxDD shallower) = 99.98%. Details in
  `research/prod_vs_bb4_pwin_2026_05_28.log`.

**What this strategy does NOT do**

- No vol targeting / leverage (max weight = 1.0 per sleeve).
- No factor tilts, sector caps, or sleeve-level rebalance bands.
- NDX risk gate is sleeve-local: TIP canary + SPY trend + SPY RV20<RV252.
- NDX stock picking depends on continuous PIT Nasdaq-100 constituent data;
  any data outage forces NDX to safe.

## Files

- `cpm_live.py` - Cross-asset Parity Momentum (CPM) sleeve engine + monthly rebalance signal.
- `bull_spy_live.py` - BULL sleeve engine.
- `ndx_sleeve_live.py` - NDX stock-picking sleeve engine.
- `build_dashboard.py` - daily blend assembly + dashboard generation.
- `cpm_dashboard.html` - generated dashboard.
- `research/` - research scripts and audit logs.
