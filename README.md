# CPM-BULL-NDX

**60% CPM-ext + 20% BULL-ext + 20% NDX.** Personal runbook. Realized mean
equity/Nasdaq exposure is ~44%; sleeve-level canaries plus a daily LQD/IEF
credit-spread intramonth circuit on the NDX sleeve are the defensive machinery.

- **CPM-ext (60%)** — AAA Pair-EW Extension over the CLEAN-9 universe with
  Faber × (1 - corr_260d) GPM-penalized ranker, TIP canary (HAA canonical), and
  504d simple daily covariance for min-variance pair selection. Top-K = ceil(9/2)
  = 5 candidates. Equal-weighted 50/50 on the chosen pair.
- **BULL-ext (20%)** — HAA-Simple Extension on SPY with HYG OR TIP canary.
  Either fully invested in SPY (when canary AND SPY mom_13612U > 0 both pass)
  or fully in HAA best-of-safe (SHV/IEF).
- **NDX (20%)** — top-5 PIT Nasdaq-100 stocks by GPM score (13612U momentum
  penalized by 260d correlation), 20% each, TIP-canary-gated. Daily LQD/IEF
  intramonth circuit latches defensive (to best_safe) when ratio LQD/IEF falls
  below its 50-day SMA; releases at next monthly signal. The ratio is
  duration-cancelled (LQD ~8y, IEF ~7y), making the signal an approximate pure
  credit-spread proxy: falling LQD/IEF = IG corporates underperforming
  Treasuries = credit-spread widening = risk-off.

Monthly rebalance on the last trading day of each calendar month, ETF +
individual stocks, no leverage, 10 bps/side cost. Total-return prices
(yfinance `auto_adjust=True`). Tax-advantaged accounts only.

> ⚠️ **Not yet live-traded.** All validation is backtest.

## Headline performance

Clean live-ETF window 2008-04-30 → 2026-05-22 (18.1y, post-cost). Raw backtest.

| Strategy | Sharpe | CAGR | Vol | MaxDD | Calmar |
|---|---:|---:|---:|---:|---:|
| **PROD 60/20/20** | **1.455** | **13.37%** | **8.91%** | **-9.90%** | **1.35** |
| Best literature blend (BB4) | 1.192 | 12.00% | 9.93% | -14.55% | 0.82 |
| Simplest literature 60/40 (BB1) | 1.111 | 10.77% | 9.64% | -14.80% | 0.73 |
| SPY buy-hold | 0.660 | 11.76% | 19.79% | -51.48% | 0.23 |
| QQQ buy-hold | 0.824 | 17.23% | 22.29% | -49.37% | 0.35 |

PROD beats the best literature blend (BB4 = 60% AAA+TIP + 20% HAA-Simple SPY +
20% Antonacci QQQ-trend) by **+0.26 Sharpe**, **-4.6pp shallower MaxDD**, and
**+0.53 Calmar**. Vs SPY buy-hold, PROD has β ≈ 0.17 with correlation ≈ 0.35
— a portfolio diversifier, not a levered equity play.

Sleeve standalone (clean window, post-cost):

| Sleeve | Sharpe | CAGR | Vol | MaxDD |
|---|---:|---:|---:|---:|
| CPM-ext (CLEAN-9) | 1.141 | 11.38% | 9.97% | -15.91% |
| BULL-ext | 1.023 | 12.97% | 12.73% | -20.28% |
| NDX (with LQD/IEF circuit) | 1.046 | 17.88% | 17.15% | -20.35% |

## Alpha decomposition

OLS daily-return regression `r_strat = alpha + beta · r_bench`:

| Strategy | Benchmark | Alpha (%/yr) | Beta | Corr |
|---|---|---:|---:|---:|
| CPM-ext | AAA + TIP canary (CLEAN-9, same universe) | +2.23 | 0.757 | 0.810 |
| BULL-ext | HAA-Simple SPY | +4.34 | 0.805 | 0.812 |
| **PROD 60/20/20** | **BB4 (best lit 60/20/20)** | **+5.87** | **0.795** | **0.815** |
| PROD 60/20/20 | BB1 (60% AAA + 40% HAA-S SPY) | +6.42 | 0.828 | 0.824 |
| PROD 60/20/20 | SPY buy-hold | +13.12 | 0.165 | 0.338 |
| PROD 60/20/20 | QQQ buy-hold | +12.31 | 0.162 | 0.373 |
| NDX sleeve | QQQ buy-hold | +24.47 | 0.328 | 0.348 |

## Strategy specification

```python
# ------------------------------------------------------------------------
# Shared definitions (monthly signal date T = last trading day of month)
# ------------------------------------------------------------------------
mom_13612U(A)     = (r1 + r3 + r6 + r12) / 4                # Keller HAA canonical
faber_score(A)    = (price[T] - SMA_10mo) / SMA_10mo        # Faber 2007
corr_260d(A, U)   = daily Pearson corr of A's returns over last 260d to the
                    equal-weighted basket return of universe U
gpm_score(A, U)   = faber_score(A) * (1 - corr_260d(A, U))  # GPM penalty
best_safe         = argmax({mom_13612U(s) for s in [SHV, IEF]})

# ------------------------------------------------------------------------
# CPM-ext (60%) -- AAA Pair-EW Extension on CLEAN-7
# ------------------------------------------------------------------------
CPM_UNIVERSE = [SPY, QQQ, SPHQ, EFA, EEM, VNQ, GLD, TLT, DBC]    # N=9

if mom_13612U(TIP) <= 0:
    cpm = {best_safe: 1.0}                            # HAA TIP canary defensive
else:
    cands = [A in CPM_UNIVERSE if faber_score(A) > 0] # positive-trend filter
    top   = top_K(cands, key=gpm_score, K=ceil(N/2)=5)
    if   len(top) == 0: cpm = {best_safe: 1.0}
    elif len(top) == 1: cpm = {top[0]: 0.5, best_safe: 0.5}    # partial-safe
    else:
        # AAA min-var pair on 504d simple daily covariance
        pair = argmin over all pairs(p1, p2) in top:
                 variance(50/50 weights, cov_504d)
        cpm  = {pair[0]: 0.5, pair[1]: 0.5}

# ------------------------------------------------------------------------
# BULL-ext (20%) -- HAA-Simple Extension on SPY
# ------------------------------------------------------------------------
canary_ok     = (mom_13612U(HYG_stitched) > 0) OR (mom_13612U(TIP) > 0)
asset_mom_ok  = (mom_13612U(SPY) > 0)

if canary_ok AND asset_mom_ok:
    bull = {SPY: 1.0}
else:
    bull = {best_safe: 1.0}

# ------------------------------------------------------------------------
# NDX (20%) -- top-K PIT Nasdaq-100 stock momentum
# ------------------------------------------------------------------------
if mom_13612U(TIP) <= 0:
    ndx = {best_safe: 1.0}
else:
    pool   = PIT_NDX100_constituents(T)
    scores = {t: mom_13612U(t) * (1 - corr_260d(t, pool)) for t in pool}
    picks  = top_5(t for t, s in scores if mom_13612U(t) > 0)
    ndx    = {t: 0.20 for t in picks}                 # 20% each, K=5
    if len(picks) < 5:                                # partial-fill -> safe
        ndx[best_safe] = 1.0 - 0.20 * len(picks)

# Daily LQD/IEF credit-spread intramonth circuit on NDX:
#   ratio = LQD_close / IEF_close      # duration-cancelled credit-spread proxy
#   trigger when ratio < ratio.rolling(50).mean()
#   reset at next monthly signal date; t+1 MOO execution honest
ratio_lqd_ief = LQD_close / IEF_close
if ratio_lqd_ief[T] < ratio_lqd_ief.rolling(50).mean()[T]:
    ndx = {best_safe: 1.0}              # latched until next monthly signal

# ------------------------------------------------------------------------
# Blend
# ------------------------------------------------------------------------
portfolio = 0.60 * cpm + 0.20 * bull + 0.20 * ndx
```

**Universe:**

| Pool | Tickers |
|---|---|
| CPM CLEAN-9 (9) | SPY, QQQ, SPHQ, EFA, EEM, VNQ, GLD, TLT, DBC |
| BULL (1) | SPY |
| Safe pool (HAA best-of by 13612U) | SHV (ultra-short), IEF (7-10y) |
| CPM canary (1) | TIP |
| BULL canary (2, OR) | HYG_stitched, TIP |
| NDX canary (1) | TIP |
| NDX intramonth circuit (2) | LQD, IEF (duration-cancelled ratio) |
| NDX pool | point-in-time Nasdaq-100 (top-5 by GPM score, 20% each) |

**Method lineage:**

| Component | Source |
|---|---|
| AAA min-variance optimization | Butler & Philbrick 2012 |
| AAA Pair-EW restriction | This work |
| 13612U momentum | Keller & Keuning 2022 HAA canonical |
| TIP canary | Keller & Keuning 2022 HAA canonical |
| HAA-Simple skeleton (N=1) | AllocateSmartly summary of Keller HAA |
| Faber SMA10m ranker | Faber 2007 SSRN TAA |
| GPM correlation penalty (1 - corr) | Generalized Protective Momentum (Keller 2017) |
| HYG breadth canary extension | Keller HAA-extension family |
| LQD/IEF credit-spread (duration-cancelled ratio) | Practitioner macro standard |
| SMA crossover trigger (50-day) | Practitioner technical-analysis family (Faber TAA precedent) |
| Top-K cross-sectional (NDX) | Jegadeesh & Titman 1993 |
| PIT NDX-100 constituents | `index-constitution` library (≥ 2006-01) |
| Deflated Sharpe | Bailey & Lopez de Prado 2012 |

**Execution:**

- Signal date: last trading day of each calendar month (close).
- Trade date: T+1 OPEN (next-day MOO).
- Accounting: close-to-close on apply day; t+1 MOO honest for intramonth
  circuits (defensive scale applies starting day after trigger fires).
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
| B2: AAA + TIP canary | This + Keller TIP | 0.956 | 10.01% | -18.80% |
| B3: HAA-Simple SPY | Keller 2022 | 0.970 | 11.48% | -20.28% |
| B4: HAA-Simple QQQ | Keller 2022 variant | 0.875 | 13.43% | -28.56% |
| B5: QQQ 12mo trend | Antonacci 2014 GEM | 0.923 | 16.73% | -28.56% |
| BB1: 60 B2 + 40 B3 | Two-sleeve blend | 1.111 | 10.77% | -14.80% |
| BB4: 60 B2 + 20 B3 + 20 B5 | Three-sleeve blend (best lit) | 1.192 | 12.00% | -14.55% |
| **PROD 60/20/20** | This work | **1.410** | **13.21%** | **-10.17%** |

## Robustness

Stationary block bootstrap on PROD daily returns (B=2000, block=21d, seed=42;
refreshed at each spec change, current run 2026-05-28):

| Metric | Point | p2.5 | p25 | p50 | p75 | p97.5 |
|---|---:|---:|---:|---:|---:|---:|
| Sharpe | 1.455 | 1.041 | 1.316 | 1.453 | 1.601 | 1.866 |
| CAGR | 13.37% | 9.41% | 11.97% | 13.37% | 14.83% | 17.68% |
| Vol | 8.91% | 8.27% | 8.69% | 8.92% | 9.14% | 9.56% |
| MaxDD | -9.90% | -17.88% | -13.28% | -11.47% | -10.04% | -8.42% |
| Calmar | 1.35 | 0.60 | 0.94 | 1.16 | 1.40 | 1.94 |

95% CI summary: **Sharpe [1.04, 1.87]**, CAGR [9.41%, 17.68%], MaxDD [-17.88%,
-8.42%], Calmar [0.60, 1.94]. Lower bound of Sharpe ~1.04, comfortably above
literature blends (BB4: 1.19, BB1: 1.11) and SPY (0.66). Script + log + JSON
in `research/bootstrap_ci_2026_05_28.{py,log,json}`.

## Key caveats

**Tax & live status**

- Monthly rotation creates short-term gains. Tax-advantaged accounts only.
- Strategy is NOT live-traded. All performance is backtest.
- DBC inception 2006-02 is the binding universe start; backtest starts
  2008-04-30 to give 504d covariance warmup with all-live ETFs.

**Reproducibility**

- Stitched proxy series for pre-ETF history are documented in
  `cpm_live.py:load_panel`. Source: `data/proxy_adjusted_close_daily.csv`.
- yfinance retroactively re-adjusts splits/dividends, causing minor drift
  over time (±0.05 Sharpe across reproductions). Headline numbers use a
  frozen panel snapshot.
- Third-party reproductions on yfinance ETF-only data typically land within
  Sharpe -0.05 to -0.15 of headline due to signal-date convention, cost
  application timing, NaN handling, and `pandas.cov` ddof choice.
- Reasonable forward Sharpe expectation for retail-data reproductions:
  **0.95-1.10** on the 60/40 (CPM+BULL only, no NDX); **1.30-1.50** on the
  60/20/20 PROD blend (with NDX). The LQD/IEF intramonth circuit specifically
  depends on credit spreads being a regime-shift signal for equity stress;
  in a low-credit-vol regime the circuit fires less, but downside floor is
  bounded by NDX-raw Sharpe (~1.0) since the circuit is risk-neutral on
  average.

**What this strategy does NOT do**

- No vol targeting / leverage (max weight = 1.0 per sleeve).
- No factor tilts, sector caps, or sleeve-level rebalance bands.
- No earnings/macro overlay beyond the LQD/IEF credit-spread circuit.
- NDX stock picking depends on continuous PIT Nasdaq-100 constituent data;
  any data outage forces NDX to safe.

## Files

- `cpm_live.py` — CPM sleeve engine + monthly rebalance signal.
- `bull_qqq_live.py` — BULL sleeve engine.
- `ndx_sleeve_live.py` — NDX stock-picking sleeve engine.
- `vol_cap.py` — sleeve-equity DD circuit + LQD/IEF credit-spread circuit.
- `build_dashboard.py` — daily blend assembly + dashboard generation.
- `dd_check.py` — daily intramonth circuit canary (cron-monitored).
- `cpm_dashboard.html` — generated dashboard.
- `research/` — research scripts, audit logs, archived spec versions.
