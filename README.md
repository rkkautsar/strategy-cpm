# CPM-BULL-NDX

**60% CPM + 20% BULL + 20% NDX.** Personal runbook. Sleeve-level
canaries plus a daily LQD/IEF credit-spread intramonth circuit on the NDX
sleeve are the defensive machinery.

- **CPM (60%)** — AAA Pair-EW Extension over the 9-asset risky universe with
  13612U momentum (Faber) ranker, HYG OR TIP canary (BULL-style breadth), and
  504d simple daily covariance for min-variance pair selection. Top-K = ceil(9/2)
  = 5 candidates. Equal-weighted 50/50 on the chosen pair.
- **BULL (20%)** — HAA-Simple Extension on SPY with HYG OR TIP canary.
  Either fully invested in SPY (when canary AND SPY mom_13612U > 0 both pass)
  or fully in HAA best-of-safe (SHV/IEF).
- **NDX (20%)** — top-5 PIT Nasdaq-100 stocks by GPM score (13612U momentum
  penalized by 260d correlation), 20% each, gated on QQQ 13612U trend (asset-class self-trend filter). Daily LQD/IEF
  intramonth circuit latches defensive (to best_safe) when ratio LQD/IEF falls
  below its 50-day EMA; releases at next monthly signal. The ratio is
  duration-cancelled (LQD ~8y, IEF ~7y), making the signal an approximate pure
  credit-spread proxy: falling LQD/IEF = IG corporates underperforming
  Treasuries = credit-spread widening = risk-off.

Monthly rebalance on the last trading day of each calendar month, ETF +
individual stocks, no leverage, 10 bps/side cost. Total-return prices
(yfinance `auto_adjust=True`). Tax-advantaged accounts only.

> ⚠️ **Not yet live-traded.** All validation is backtest.

## Headline performance

Clean live-ETF window 2008-05-30 → 2026-05-22 (18.0y, post-cost). Raw backtest.

| Strategy | Sharpe | CAGR | Vol | MaxDD | Calmar |
|---|---:|---:|---:|---:|---:|
| **PROD 60/20/20** | **1.440** | **15.42%** | **10.33%** | **-11.04%** | **1.40** |
| Best literature blend (BB4) | 1.194 | 12.03% | 9.94% | -14.55% | 0.83 |
| Simplest literature 60/40 (BB1) | 1.122 | 10.90% | 9.65% | -14.80% | 0.74 |
| SPY buy-hold | 0.660 | 11.73% | 19.82% | -50.70% | 0.23 |
| QQQ buy-hold | 0.815 | 16.94% | 22.30% | -49.37% | 0.34 |

PROD beats the best literature blend (BB4 = 60% AAA+TIP + 20% HAA-Simple SPY +
20% Antonacci QQQ-trend) by **+0.25 Sharpe**, **-3.50pp shallower MaxDD**, and
**+0.57 Calmar**. Vs SPY buy-hold, PROD has β ≈ 0.18 with correlation ≈ 0.37
— a portfolio diversifier, not a levered equity play.

Sleeve standalone (clean window, post-cost):

| Sleeve | Sharpe | CAGR | Vol | MaxDD |
|---|---:|---:|---:|---:|
| CPM | 1.291 | 15.07% | 11.67% | -15.41% |
| BULL | 1.034 | 13.14% | 12.75% | -20.28% |
| NDX + LQD/IEF circuit | 1.077 | 20.42% | 18.93% | -21.08% |
| NDX raw (no circuit, reference) | 0.975 | 27.06% | 28.90% | -42.48% |

NDX LQD/IEF circuit is Sharpe-positive vs raw (1.077 vs 0.975) and cuts
standalone MaxDD from -42.48% to -21.08%; selected for tail-risk reduction
at near-zero Sharpe cost, not for Sharpe lift.

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
| NDX (with LQD/IEF circuit) | QQQ buy-hold | +15.74 | 0.257 | 0.302 |

Numbers refreshed 2026-05-28 against current locked spec; see
`research/alpha_beta_refresh_2026_05_28.log`.

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
# CPM (60%) -- AAA Pair-EW Extension
# ------------------------------------------------------------------------
CPM_UNIVERSE = [SPY, QQQ, SPHQ, EFA, EEM, VNQ, GLD, TLT, DBC]    # N=9

canary_ok = (mom_13612U(HYG) > 0) OR (mom_13612U(TIP) > 0)

if not canary_ok:
    cpm = {best_safe: 1.0}                            # any-positive canary defensive
else:
    cands = [A in CPM_UNIVERSE if faber_score(A) > 0] # positive-trend filter
    top   = top_K(cands, key=faber_score, K=ceil(N/2)=5)
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
# NDX (20%) -- top-K PIT Nasdaq-100 stock momentum
# ------------------------------------------------------------------------
if mom_13612U(QQQ) <= 0:
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
#   evaluated EVERY trading day d (not just at monthly T):
#     if ratio[d] < ratio.ewm(span=50)[d] -> latch defensive starting d+1
#     state stays defensive until next monthly signal date resets to 1.0
#   t+1 MOO honest: scale on day d is set BEFORE day-d trigger evaluation
ratio = LQD_close / IEF_close
ema50 = ratio.ewm(span=50, adjust=False).mean()
state = 1.0                              # 1.0 = NDX holds picks, 0.0 = defensive
for d in trading_days(T_prev_signal+1, T_next_signal):
    if d == T_next_signal:               # monthly reset
        state = 1.0
    apply scale[d] = state to NDX sleeve_return[d]
    if ratio[d] < sma50[d]:              # trigger fires for tomorrow
        state = 0.0                      # defensive starting day d+1

# ------------------------------------------------------------------------
# Blend
# ------------------------------------------------------------------------
portfolio = 0.60 * cpm + 0.20 * bull + 0.20 * ndx
```

**Universe:**

| Pool | Tickers |
|---|---|
| CPM (9) | SPY, QQQ, SPHQ, EFA, EEM, VNQ, GLD, TLT, DBC |
| BULL (1) | SPY |
| Safe pool (HAA best-of by 13612U) | SHV (ultra-short), IEF (7-10y) |
| CPM canary (2, OR) | HYG, TIP |
| BULL canary (2, OR) | HYG, TIP |
| NDX canary (1) | QQQ |
| NDX intramonth circuit (2) | LQD, IEF (duration-cancelled ratio; IEF supplied via SAFE_POOL) |
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
| US factor-ETF universe extension (QQQ, SPHQ) | This work (best Sharpe + Calmar in factor add-back sweep, see `research/cpm_universe_factor_addback_2026_05_28.py`) |
| HYG breadth canary extension | Keller HAA-extension family |
| LQD/IEF credit-spread (duration-cancelled ratio) | Practitioner macro standard |
| EMA crossover trigger (50-day) | Practitioner technical-analysis family (Faber TAA precedent) |
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
| B2: AAA + TIP canary | This + Keller TIP | 0.964 | 10.11% | -18.80% |
| B3: HAA-Simple SPY | Keller 2022 | 0.981 | 11.65% | -20.28% |
| B4: HAA-Simple QQQ | Keller 2022 variant | 0.859 | 13.13% | -28.56% |
| B5: QQQ 12mo trend (Antonacci-family TSMOM single-asset) | Faber/Antonacci 12mo absolute trend | 0.909 | 16.44% | -28.56% |
| BB1: 60 B2 + 40 B3 (60 AAA+TIP / 40 HAA-S SPY) | Two-sleeve blend | 1.122 | 10.90% | -14.80% |
| BB4: 60 B2 + 20 B3 + 20 B5 | Three-sleeve blend (best lit) | 1.194 | 12.03% | -14.55% |
| **PROD 60/20/20** | This work | **1.466** | **14.57%** | **-9.94%** |

## Robustness

Stationary block bootstrap on PROD daily returns (B=2000, block=21d, seed=42;
refreshed at each spec change, current run 2026-05-28):

| Metric | Point | p2.5 | p25 | p50 | p75 | p97.5 |
|---|---:|---:|---:|---:|---:|---:|
| Sharpe | 1.466 | 1.053 | 1.328 | 1.473 | 1.617 | 1.896 |
| CAGR | 14.57% | 10.34% | 13.06% | 14.61% | 16.18% | 19.23% |
| Vol | 9.61% | 9.02% | 9.40% | 9.60% | 9.80% | 10.21% |
| MaxDD | -9.94% | -20.51% | -14.66% | -12.60% | -10.95% | -8.93% |
| Calmar | 1.47 | 0.58 | 0.92 | 1.15 | 1.42 | 1.97 |

95% CI summary: **Sharpe [1.05, 1.90]**, CAGR [10.34%, 19.23%], MaxDD [-20.51%,
-8.93%], Calmar [0.58, 1.97]. Lower bound of Sharpe ~1.05, comfortably above
literature blends (BB4: 1.19, BB1: 1.11) and SPY (0.66). Script + log + JSON
in `research/bootstrap_ci_2026_05_28.{py,log,json}`.

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
- Reasonable forward Sharpe expectation for retail-data reproductions:
  **1.00-1.20** on the 60/40 (CPM+BULL only, no NDX); **1.30-1.60** on the
  60/20/20 PROD blend (with NDX). Anchors: bootstrap 95% CI on PROD Sharpe is
  [1.03, 1.87] with point 1.440; subtract ~0.05-0.15 for typical retail-data
  reproduction drift to get a forward range. The LQD/IEF intramonth circuit
  depends on credit spreads being a regime-shift signal for equity stress; in
  a low-credit-vol regime the circuit fires less, but downside floor is
  bounded by NDX-raw Sharpe (~1.0).
- **P(PROD beats BB4 on Sharpe) ≈ 97.0%** by paired block bootstrap (B=5000,
  block=21d); P(beats by ≥0.10 Sharpe) ≈ 87.1%, P(beats by ≥0.20) ≈ 62.7%.
  P(shallower MaxDD than BB4) ≈ 60.3%.
- **P(PROD beats Static 80/20 on Sharpe) ≈ 97.1%** by same bootstrap; P(beats
  by ≥0.10 Sharpe) ≈ 92.3%, P(beats by ≥0.20) ≈ 83.9%, P(shallower MaxDD)
  ≈ 75.7%. Vs SPY/QQQ buy-hold: P(higher Sharpe) >99%. Details in
  `research/prod_vs_bb4_pwin_2026_05_28.log`.

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
- `circuit_breaker.py` — LQD/IEF credit-spread intramonth circuit (NDX sleeve).
- `build_dashboard.py` — daily blend assembly + dashboard generation.
- `circuit_check.py` — daily LQD/IEF circuit canary (cron-monitored).
- `cpm_dashboard.html` — generated dashboard.
- `research/` — research scripts, audit logs, archived spec versions.
