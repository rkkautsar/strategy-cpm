# CPM-BULL-NDX

**60% CPM + 20% BULL + 20% NDX.** Personal runbook. Sleeve-level
canaries plus monthly sleeve-state gating are the defensive machinery.

- **Cross-asset Parity Momentum (CPM) (60%)** — 8-asset risky universe
  (QQQ, SPHQ, EFA, EEM, VNQ, GLD, TLT, DBC), HYG OR TIP canary,
  EAA-style Vol-Adj (Faber/Vol) ranker, positive-trend screen, top-K=4,
  inverse-vol weights across all surviving positives, strict-4 partial-safe,
  timed best-safe (SHV/IEF).
- **BULL (20%)** — HAA-Simple Extension on SPY with 3-layer monthly gate:
  Canary (HYG OR TIP), Trend (SPY mom_13612U > 0), and RV Crossover
  (vol_ok: Monthly realized volatility gate (RV_60d < RV_252d)).
  Either fully invested in SPY (when all three pass) or fully in HAA
  best-of-safe (SHV/IEF).
- **NDX (20%)** — top-5 PIT Nasdaq-100 stocks by raw 13612U momentum
  (positive only), 20% each, strictly gated on monthly BULL active state.
  If BULL is active, NDX runs equal-weight top-5; if BULL is defensive,
  NDX allocates 100% best_safe (SHV/IEF).

Monthly rebalance on the last trading day of each calendar month, ETF +
individual stocks, no leverage, 10 bps/side cost. Total-return prices
(yfinance `auto_adjust=True`). Tax-advantaged accounts only.

> ⚠️ **Not yet live-traded.** All validation is backtest.

## Headline performance

Clean live-ETF window 2008-05-30 -> 2026-05-22 (18.0y, post-cost).

| Strategy | Raw Sharpe (0rf) | Excess Sharpe (vs SHV) | CAGR | Vol | MaxDD | Calmar |
|---|---:|---:|---:|---:|---:|---:|
| **PROD 60/20/20** | **1.370** | **1.257** | **16.64%** | **11.78%** | **-12.16%** | **1.37** |
| Best literature blend (BB4) | 1.194 | 1.061 | 12.03% | 9.94% | -14.55% | 0.83 |
| Simplest literature 60/40 (BB1) | 1.122 | 0.985 | 10.90% | 9.65% | -14.80% | 0.74 |
| SPY buy-hold | 0.660 | 0.591 | 11.73% | 19.82% | -50.70% | 0.23 |
| QQQ buy-hold | 0.816 | 0.755 | 16.94% | 22.30% | -49.37% | 0.34 |

Sleeve (clean window, post-cost):

| Sleeve | Raw Sharpe (0rf) | Excess Sharpe (vs SHV) | CAGR | Vol | MaxDD | Calmar |
|---|---:|---:|---:|---:|---:|---:|
| CPM | 1.191 | 1.072 | 13.44% | 11.16% | -12.67% | 1.06 |
| BULL | 1.081 | 0.955 | 11.44% | 10.57% | -13.35% | 0.86 |
| NDX | 1.186 | 1.132 | 30.01% | 24.77% | -35.92% | 0.84 |
| PROD 60/20/20 | 1.370 | 1.257 | 16.64% | 11.78% | -12.16% | 1.37 |

Clean-window anchors (CPM-focused):

| Variant | Sharpe | CAGR | Vol | MaxDD | Calmar | Martin |
|---|---:|---:|---:|---:|---:|---:|
| Cross-asset Parity Momentum (CPM) | 1.1910 | 13.44% | 11.16% | -12.67% | 1.0615 | 3.9646 |
| CPM-BULL 60/40 (two-sleeve, no NDX) | 1.2485 | 12.74% | 10.05% | -10.68% | 1.1928 | 4.354 |

CPM concentration (clean, per-asset share of risky sleeve exposure):
SPHQ 20.9%, QQQ 16.9%, GLD 15.0%, EFA 11.7%, TLT 10.5%, VNQ 9.8%, EEM 8.1%, DBC 7.2%.

NDX is a leveraged-beta expression of Nasdaq growth via top-5 raw 13612U momentum under monthly BULL gating. Treat it as a beta amplifier with bounded downside (20% weight + 4% single-name cap), because its +0.12 Sharpe edge vs plain BULL-gated QQQ is roughly offset by selection-stage survivorship bias (~-0.11).

Raw-momentum checkpoints:

| Window | NDX Sharpe | NDX CAGR | NDX MaxDD | Blend Sharpe | Blend CAGR | Blend MaxDD |
|---|---:|---:|---:|---:|---:|---:|
| Clean | 1.186 | 30.01% | -35.92% | 1.370 | 16.64% | -12.16% |
| Stress | 1.014 | 21.48% | -35.92% | 1.298 | 14.73% | -12.63% |

## Alpha decomposition

OLS daily-return regression `r_strat = alpha + beta · r_bench`:

| Strategy | Benchmark | Alpha (%/yr) | Beta | Corr |
|---|---|---:|---:|---:|
| CPM | B2: AAA + TIP canary (same universe) | +4.75 | 0.834 | 0.791 |
| BULL | B3: HAA-Simple SPY | +4.48 | 0.589 | 0.668 |
| **PROD 60/20/20** | **BB4 (best lit 60/20/20)** | **+4.85** | **0.947** | **0.800** |
| PROD 60/20/20 | BB1 (60% AAA+TIP + 40% HAA-S SPY) | +6.01 | 0.933 | 0.764 |
| NDX | QQQ buy-hold | +22.09 | 0.400 | 0.360 |

Buy-hold equity alpha (vs SPY +13.12%/yr, vs QQQ +11.73%/yr) is mechanically inflated by time spent in cash/safe (low realized beta) and is not analytically meaningful. The peer-blend alpha (+4.85 vs BB4, +6.01 vs BB1) is the real claim.

See `research/alpha_beta_refresh_2026_05_28.log`.

## Strategy specification

```python
# ------------------------------------------------------------------------
# Shared definitions (monthly signal date T = last trading day of month)
# ------------------------------------------------------------------------
mom_13612U(A)     = (r1 + r3 + r6 + r12) / 4                # Keller HAA canonical
faber_score(A)    = (price[T] - SMA_10mo) / SMA_10mo        # Faber 2007
vol_252d(A)       = annualized daily standard deviation of A over last 252d
rv_60d(A)         = annualized daily standard deviation of A over last 60d
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

canary_ok = (mom_13612U(HYG) > 0) OR (mom_13612U(TIP) > 0)

if not canary_ok:
    cpm = {best_safe: 1.0}                            # defensive only when both HYG and TIP fail
else:
    ranked = top_K(CPM_UNIVERSE, key=eaa_score, K=4)
    pos    = [A for A in ranked if faber_score(A) > 0]           # positive-trend filter
    n_pos  = len(pos)
    if n_pos == 0:
        cpm = {best_safe: 1.0}
    else:
        risky_fraction = min(n_pos, 4) / 4.0                      # strict-4 partial-safe
        safe_fraction  = 1.0 - risky_fraction
        invvol = inverse_vol_weights(pos, lookback=504)
        cpm = {A: invvol[A] * risky_fraction for A in pos}
        if safe_fraction > 0:
            cpm[best_safe] = cpm.get(best_safe, 0.0) + safe_fraction

# ------------------------------------------------------------------------
# BULL (20%) -- HAA-Simple Extension on SPY
# 3-layer gate: Canary + Trend + RV Crossover
# ------------------------------------------------------------------------
canary_ok     = (mom_13612U(HYG) > 0) OR (mom_13612U(TIP) > 0)
asset_mom_ok  = (mom_13612U(SPY) > 0)
vol_ok        = (rv_60d(SPY) < rv_252d(SPY))  # Monthly realized volatility gate (RV_60d < RV_252d)

if canary_ok AND asset_mom_ok AND vol_ok:
    bull = {SPY: 1.0}
else:
    bull = {best_safe: 1.0}

# ------------------------------------------------------------------------
# NDX (20%) -- monthly BULL-gated top-K PIT Nasdaq-100 momentum
# ------------------------------------------------------------------------
bull_active = (bull.get(SPY, 0.0) > 0)

if not bull_active:
    ndx = {best_safe: 1.0}
else:
    pool     = PIT_NDX100_constituents(T)
    eligible = [t for t in pool if mom_13612U(t) > 0 and is_fully_valid(t)]
    picks    = top_K(eligible, key=lambda t: mom_13612U(t), K=5)
    ndx      = {t: 0.20 for t in picks}               # 20% each, K=5
    if len(picks) < 5:                                # partial-fill -> safe
        ndx[best_safe] = 1.0 - 0.20 * len(picks)

# ------------------------------------------------------------------------
# Blend
# ------------------------------------------------------------------------
portfolio = 0.60 * cpm + 0.20 * bull + 0.20 * ndx
```

### BULL volatility gate

| Blocked-month cohort | Count | Mean fwd SPY | Fwd vol (ann) |
|---|---:|---:|---:|
| False-positive (market rose) | 27 (66%) | +3.06% | 11.8% |
| True-positive (market fell) | 14 (34%) | -3.54% | 21.1% |

"The RV gate is a volatility filter, not a direction predictor. False-positive months average +3.06% SPY return but at 11.8% forward vol; true-positive months average -3.54% at 21.1% vol. The vol asymmetry (~2:1) is the operative signal. Net effect: -0.81% CAGR drag offset by MaxDD compression and Calmar improvement (1.28 -> 1.37). Consistent with Moreira-Muir vol-managed logic. Known limitation: ~1-month lag on V-shaped recoveries."

**Universe:**

| Pool | Tickers |
|---|---|
| Cross-asset Parity Momentum (CPM) universe (8) | QQQ, SPHQ, EFA, EEM, VNQ, GLD, TLT, DBC |
| BULL (1) | SPY |
| Safe pool (HAA best-of by 13612U) | SHV (ultra-short), IEF (7-10y) |
| Cross-asset Parity Momentum (CPM) canary (2, OR) | HYG, TIP |
| BULL canary (2, OR) | HYG, TIP |
| BULL trend gate | SPY mom_13612U > 0 |
| BULL vol gate | vol_ok: Monthly realized volatility gate (RV_60d < RV_252d) |
| NDX gate | monthly BULL active state (BULL_SPY) |
| NDX pool | point-in-time Nasdaq-100 (top-5 by raw 13612U momentum, 20% each) |

**Method lineage:**

| Component | Source |
|---|---|
| Cross-asset Parity Momentum (CPM) top-4 + inverse-vol weight-all + strict-4 partial-safe | This work |
| Timed safe sleeve (SHV/IEF by 13612U) | Keller & Keuning 2022 HAA family |
| 13612U momentum | Keller & Keuning 2022 HAA canonical |
| TIP canary | Keller & Keuning 2022 HAA canonical |
| HAA-Simple skeleton (N=1) | AllocateSmartly summary of Keller HAA |
| EAA Vol-Adj (Faber/Vol) ranker | Elastic Asset Allocation (Keller & Butler 2014) |
| US factor-ETF universe (QQQ, SPHQ) | This work |
| HYG breadth canary extension | Keller HAA-extension family |
| Monthly sleeve-state gate (NDX follows BULL active state) | This work |
| Top-K cross-sectional (NDX) | Jegadeesh & Titman 1993 |
| PIT NDX-100 constituents | `index-constitution` library (≥ 2006-01) |
| Deflated Sharpe | Bailey & Lopez de Prado 2012 |

**Execution:**

- Signal date: last trading day of each calendar month (close).
- Trade date: T+1 OPEN (next-day MOO).
- Accounting: close-to-close on apply day; t+1 MOO honest monthly sleeve
  updates (weights chosen at signal date apply from next trading day open).
- Cost: 10 bps/side on any state change (full A→B switch = 20 bps).
- Cron: monthly, 10am SGT (first business day after month-end).

**Performance-stat conventions:**

- CAGR = `eq[-1] ** (1/years) - 1`, years = calendar_days / 365.25.
- Sharpe = annualized at 0% rf (`daily.mean() · 252 / (daily.std() · sqrt(252))`).
- Excess Sharpe = excess.mean() * 252 / (excess.std(ddof=0) * sqrt(252)), excess_daily = strategy_daily - SHV_daily.
- Vol = `std(daily) · sqrt(252)`, ddof=0.
- MaxDD = trough below highest prior peak.
- Calmar = CAGR / |MaxDD|.
- Alpha/beta: OLS daily returns, annualized as `alpha_daily · 252`.

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
| **PROD 60/20/20** | This work | **1.370** | **16.64%** | **-12.16%** |

## Robustness

Single-strategy bootstrap CI on PROD daily returns (B=2000, block=21d, seed=42):

| Metric | Point | p2.5 | p25 | p50 | p75 | p97.5 |
|---|---:|---:|---:|---:|---:|---:|
| Sharpe | 1.370 | 0.954 | 1.224 | 1.372 | 1.521 | 1.823 |
| CAGR | 16.69% | 11.25% | 14.81% | 16.66% | 18.68% | 22.61% |
| Vol | 11.78% | 11.01% | 11.50% | 11.78% | 12.07% | 12.64% |
| MaxDD | -12.16% | -24.58% | -18.18% | -15.56% | -13.52% | -10.85% |
| Calmar | 1.372 | 0.525 | 0.843 | 1.069 | 1.314 | 1.901 |

95% CI summary: **Sharpe [0.954, 1.823]**, CAGR [11.25%, 22.61%], MaxDD
[-24.58%, -10.85%], Calmar [0.525, 1.901].
Extended-window Sharpe point/CI: **1.298 [0.952, 1.640]**. Difference block bootstrap
for strategy deltas vs BB4/benchmarks is summarized in win probabilities below.
Script + log + JSON in `research/bootstrap_ci_2026_05_28.{py,log,json}`.

## Key caveats

**Tax & live status**

- Monthly rotation creates short-term gains. Tax-advantaged accounts only.
- Strategy is NOT live-traded. All performance is backtest.
- DBC inception 2006-02 is the binding universe start; backtest starts
  2008-05-30 to give 504d inverse-vol lookback warmup + 13mo HYG warmup with all-live ETFs.

**Reproducibility**

- Stitched proxy series for pre-ETF history are documented in
  `cpm_live.py:load_panel`. Source: `data/proxy_adjusted_close_daily.csv`.
- yfinance retroactively re-adjusts splits/dividends, causing minor drift
  over time (±0.05 Sharpe across reproductions). Headline numbers use a
  frozen panel snapshot.
- Third-party reproductions on yfinance ETF-only data typically land within
  Sharpe -0.05 to -0.15 of headline due to signal-date convention, cost
  application timing, NaN handling, and `pandas.cov` ddof choice.
- The realized backtest Sharpe is 1.370. Retail-data reproductions may be
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
- NDX risk gate is monthly BULL-state only.
- NDX stock picking depends on continuous PIT Nasdaq-100 constituent data;
  any data outage forces NDX to safe.

## Files

- `cpm_live.py` — Cross-asset Parity Momentum (CPM) sleeve engine + monthly rebalance signal.
- `bull_qqq_live.py` — BULL sleeve engine.
- `ndx_sleeve_live.py` — NDX stock-picking sleeve engine.
- `build_dashboard.py` — daily blend assembly + dashboard generation.
- `cpm_dashboard.html` — generated dashboard.
- `research/` — research scripts and audit logs.
