# CPM-BULL-NDX

**60% CPM + 20% BULL + 20% NDX.** Personal runbook. Sleeve-level
canaries plus monthly sleeve-state gating are the defensive machinery.

- **CPM (60%)** — AAA Pair-EW Extension over the 8-asset risky universe
  (QQQ, SPHQ, EFA, EEM, VNQ, GLD, TLT, DBC) with EAA-style Vol-Adj
  (Faber/Vol) ranker, HYG OR TIP canary (BULL-style breadth), and 504d simple
  daily covariance for min-variance pair selection. Top-K = ceil(8/2) = 4
  candidates. Equal-weighted 50/50 on the chosen pair.
- **BULL (20%)** — HAA-Simple Extension on SPY with HYG OR TIP canary.
  Either fully invested in SPY (when canary AND SPY mom_13612U > 0 both pass)
  or fully in HAA best-of-safe (SHV/IEF).
- **NDX (20%)** — top-5 PIT Nasdaq-100 stocks by raw 13612U momentum
  (positive only), 20% each, strictly gated on monthly BULL active state.
  If BULL is active, NDX runs equal-weight top-5; if BULL is defensive,
  NDX allocates 100% best_safe (SHV/IEF). No daily circuit breaker.

Monthly rebalance on the last trading day of each calendar month, ETF +
individual stocks, no leverage, 10 bps/side cost. Total-return prices
(yfinance `auto_adjust=True`). Tax-advantaged accounts only.

> ⚠️ **Not yet live-traded.** All validation is backtest.

## Headline performance

Clean live-ETF window 2008-05-30 → 2026-05-22 (18.0y, post-cost). Raw backtest.

| Strategy | Sharpe | CAGR | Vol | MaxDD | Calmar |
|---|---:|---:|---:|---:|---:|
| **PROD 60/20/20** | **1.50** | **17.93%** | **11.22%** | **-11.62%** | **1.42** |
| Best literature blend (BB4) | 1.194 | 12.03% | 9.94% | -14.55% | 0.83 |
| Simplest literature 60/40 (BB1) | 1.122 | 10.90% | 9.65% | -14.80% | 0.74 |
| SPY buy-hold | 0.660 | 11.73% | 19.82% | -50.70% | 0.23 |
| QQQ buy-hold | 0.815 | 16.94% | 22.30% | -49.37% | 0.34 |

PROD remains the 60/20/20 blend implementation with monthly rebalancing and
sleeve-level gating.

Sleeve standalone (clean window, post-cost):

| Sleeve | Sharpe | CAGR | Vol | MaxDD |
|---|---:|---:|---:|---:|
| CPM | 1.266 | 14.37% | 10.41% | -15.41% |
| BULL | 1.034 | 13.14% | 12.75% | -20.28% |
| NDX (monthly BULL-gated, no daily circuit) | 1.25 | 32.56% | 23.83% | -31.39% |

NDX remains the high-beta growth sleeve; risk is controlled at portfolio level
via 20% blend weight plus strict monthly BULL-state gating.

Choice C / raw-momentum checkpoints:

| Window | NDX Sharpe | NDX CAGR | NDX MaxDD | Blend Sharpe | Blend CAGR | Blend MaxDD |
|---|---:|---:|---:|---:|---:|---:|
| Clean | 1.25 | 32.56% | -31.39% | 1.50 | 17.93% | -11.62% |
| Stress | 1.06 | 22.71% | -31.39% | 1.36 | 15.04% | -12.69% |

## Alpha decomposition

OLS daily-return regression `r_strat = alpha + beta · r_bench`:

| Strategy | Benchmark | Alpha (%/yr) | Beta | Corr |
|---|---|---:|---:|---:|
| CPM | B2: AAA + TIP canary (same universe) | +4.47 | 0.766 | 0.780 |
| BULL | B3: HAA-Simple SPY | +1.56 | 0.989 | 0.929 |
| **PROD 60/20/20** | **BB4 (best lit 60/20/20)** | **+4.90** | **0.774** | **0.800** |
| PROD 60/20/20 | BB1 (60% AAA+TIP + 40% HAA-S SPY) | +5.65 | 0.780 | 0.783 |
| PROD 60/20/20 | SPY buy-hold | +11.72 | 0.182 | 0.374 |
| PROD 60/20/20 | QQQ buy-hold | +10.84 | 0.179 | 0.416 |
| NDX (monthly BULL-gated) | QQQ buy-hold | +16.79 | 0.207 | 0.274 |

Numbers refreshed 2026-05-28 against current locked spec; see
`research/alpha_beta_refresh_2026_05_28.log`.

## Strategy specification

```python
# ------------------------------------------------------------------------
# Shared definitions (monthly signal date T = last trading day of month)
# ------------------------------------------------------------------------
mom_13612U(A)     = (r1 + r3 + r6 + r12) / 4                # Keller HAA canonical
faber_score(A)    = (price[T] - SMA_10mo) / SMA_10mo        # Faber 2007
vol_252d(A)       = annualized daily standard deviation of A over last 252d
eaa_score(A)      = faber_score(A) / vol_252d(A)            # EAA Vol-Adj (CPM sleeve)
is_fully_valid(t) =
    has 12m momentum history
    and has current adjusted price
    and is tradable at T+1 open
best_safe         = argmax({mom_13612U(s) for s in [SHV, IEF]})

# ------------------------------------------------------------------------
# CPM (60%) -- AAA Pair-EW Extension
# ------------------------------------------------------------------------
CPM_UNIVERSE = [QQQ, SPHQ, EFA, EEM, VNQ, GLD, TLT, DBC]         # N=8

canary_ok = (mom_13612U(HYG) > 0) OR (mom_13612U(TIP) > 0)

if not canary_ok:
    cpm = {best_safe: 1.0}                            # defensive only when both HYG and TIP fail
else:
    cands = [A in CPM_UNIVERSE if faber_score(A) > 0] # positive-trend filter
    top   = top_K(cands, key=eaa_score, K=ceil(N/2)=4)
    if   len(top) == 0: cpm = {best_safe: 1.0}
    elif len(top) == 1: cpm = {top[0]: 0.5, best_safe: 0.5}    # partial-safe
    else:
        # AAA min-var pair on 504d simple daily covariance
        pair = argmin over all pairs(p1, p2) in top:
                 variance(50/50 weights, cov_504d)
        cpm  = {pair[0]: 0.5, pair[1]: 0.5}

# ------------------------------------------------------------------------
# BULL (20%) -- HAA-Simple Extension on SPY
# ------------------------------------------------------------------------
canary_ok     = (mom_13612U(HYG) > 0) OR (mom_13612U(TIP) > 0)
asset_mom_ok  = (mom_13612U(SPY) > 0)

if canary_ok AND asset_mom_ok:
    bull = {SPY: 1.0}
else:
    bull = {best_safe: 1.0}

# ------------------------------------------------------------------------
# NDX (20%) -- Choice C monthly BULL-gated top-K PIT Nasdaq-100 momentum
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

# No daily intramonth circuit breaker.

# ------------------------------------------------------------------------
# Blend
# ------------------------------------------------------------------------
portfolio = 0.60 * cpm + 0.20 * bull + 0.20 * ndx
```

**Universe:**

| Pool | Tickers |
|---|---|
| CPM (8) | QQQ, SPHQ, EFA, EEM, VNQ, GLD, TLT, DBC |
| BULL (1) | SPY |
| Safe pool (HAA best-of by 13612U) | SHV (ultra-short), IEF (7-10y) |
| CPM canary (2, OR) | HYG, TIP |
| BULL canary (2, OR) | HYG, TIP |
| NDX gate | monthly BULL active state (BULL_SPY) |
| NDX pool | point-in-time Nasdaq-100 (top-5 by raw 13612U momentum, 20% each) |

**Method lineage:**

| Component | Source |
|---|---|
| AAA min-variance optimization | Butler & Philbrick 2012 |
| AAA Pair-EW restriction | This work |
| 13612U momentum | Keller & Keuning 2022 HAA canonical |
| TIP canary | Keller & Keuning 2022 HAA canonical |
| HAA-Simple skeleton (N=1) | AllocateSmartly summary of Keller HAA |
| EAA Vol-Adj (Faber/Vol) ranker | Elastic Asset Allocation (Keller & Butler 2014) |
| US factor-ETF universe extension (QQQ, SPHQ) | This work (best Sharpe + Calmar in factor add-back sweep, see `research/cpm_universe_factor_addback_2026_05_28.py`) |
| HYG breadth canary extension | Keller HAA-extension family |
| Monthly sleeve-state gate (NDX follows BULL active state) | This work (Option B) |
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
| **PROD 60/20/20** | This work | **1.483** | **15.73%** | **-11.04%** |

## Robustness

Single-strategy bootstrap CI on PROD daily returns (B=2000, block=21d, seed=42;
refreshed at each spec change, current run 2026-05-28):

| Metric | Point | p2.5 | p25 | p50 | p75 | p97.5 |
|---|---:|---:|---:|---:|---:|---:|
| Sharpe | 1.483 | 1.074 | 1.347 | 1.495 | 1.635 | 1.914 |
| CAGR | 15.73% | 11.13% | 14.19% | 15.79% | 17.45% | 20.74% |
| Vol | 10.22% | 9.56% | 9.98% | 10.20% | 10.43% | 10.87% |
| MaxDD | -11.04% | -21.30% | -15.28% | -13.08% | -11.59% | -9.30% |
| Calmar | 1.424 | 0.607 | 0.961 | 1.183 | 1.443 | 2.021 |

95% CI summary: **Sharpe [1.074, 1.914]**, CAGR [11.13%, 20.74%], MaxDD
[-21.30%, -9.30%], Calmar [0.607, 2.021]. Paired-difference block bootstrap
for strategy deltas vs BB4/benchmarks uses B=5000 and shows
P(PROD > BB4 on Sharpe) = 98.76%. Script + log + JSON in
`research/bootstrap_ci_2026_05_28.{py,log,json}`.

## Key caveats

**Tax & live status**

- Monthly rotation creates short-term gains. Tax-advantaged accounts only.
- Strategy is NOT live-traded. All performance is backtest.
- DBC inception 2006-02 is the binding universe start; backtest starts
  2008-05-30 to give 504d covariance warmup + 13mo HYG warmup with all-live ETFs.

**Reproducibility**

- Stitched proxy series for pre-ETF history are documented in
  `cpm_live.py:load_panel`. Source: `data/proxy_adjusted_close_daily.csv`.
- yfinance retroactively re-adjusts splits/dividends, causing minor drift
  over time (±0.05 Sharpe across reproductions). Headline numbers use a
  frozen panel snapshot.
- Third-party reproductions on yfinance ETF-only data typically land within
  Sharpe -0.05 to -0.15 of headline due to signal-date convention, cost
  application timing, NaN handling, and `pandas.cov` ddof choice.
- The realized backtest Sharpe is 1.48. Retail-data reproductions may be
  modestly lower due to implementation differences. For capital planning, use
  materially lower forward assumptions, such as 0.7-1.0 Sharpe, and treat 1.3+
  as an upside case until live/paper trading confirms signal fidelity.
- **P(PROD beats BB4 on Sharpe) = 98.76%** by paired block bootstrap (B=5000,
  block=21d); P(beats by ≥0.10 Sharpe) = 93.20%, P(beats by ≥0.20) = 74.98%,
  P(shallower MaxDD than BB4) = 63.44%.
- **P(PROD beats Static 80/20 on Sharpe) = 98.24%** by same bootstrap;
  P(beats by ≥0.10 Sharpe) = 94.98%, P(beats by ≥0.20) = 88.00%,
  P(shallower MaxDD) = 77.80%. Vs SPY/QQQ buy-hold: P(higher Sharpe) >99%.
  Details in
  `research/prod_vs_bb4_pwin_2026_05_28.log`.

**What this strategy does NOT do**

- No vol targeting / leverage (max weight = 1.0 per sleeve).
- No factor tilts, sector caps, or sleeve-level rebalance bands.
- No daily intramonth circuit breaker; NDX risk gate is monthly BULL-state only.
- NDX stock picking depends on continuous PIT Nasdaq-100 constituent data;
  any data outage forces NDX to safe.

## Files

- `cpm_live.py` — CPM sleeve engine + monthly rebalance signal.
- `bull_qqq_live.py` — BULL sleeve engine.
- `ndx_sleeve_live.py` — NDX stock-picking sleeve engine.
- `build_dashboard.py` — daily blend assembly + dashboard generation.
- `cpm_dashboard.html` — generated dashboard.
- `research/` — research scripts, audit logs, archived spec versions.
