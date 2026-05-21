# CPM-BULL-NDX

**60/30/10 multi-sleeve tactical asset allocation strategy.** Three sleeves:

- **CPM (60%)** — canary-gated momentum + min-variance pair selection on a
  9-asset ETF universe (US factors + international + diversifiers).
- **BULL-QQQ (30%)** — 100% QQQ when QQQ 12-1 absolute momentum and a
  HYG/LQD/TIP macro canary both pass; SHV cash otherwise.
- **NDX (10%)** — top-4 PIT Nasdaq-100 stocks by 13612U momentum,
  equal-weighted 25% each, gated by the BULL-QQQ regime.

Monthly rebalance, ETF + individual stocks (NDX), no leverage, 10 bps/side
cost, T+1 OPEN execution. Total-return prices throughout (yfinance
`auto_adjust=True`, dividends reinvested).

> ⚠️ **Strategy is NOT yet live-traded.** All validation is backtest-based.
> Bootstrap CI and DSR are supportive but not proof of forward edge.
>
> ⚠️ **IRA/401k/Roth only.** Monthly rotation = short-term capital gains.
> Federal 22-37% + state 0-13% bracket can drop after-tax CAGR from
> 11-15% pre-tax forward expectation to **~5-9% after-tax** -- close to
> SPY buy-hold after-tax. NDX individual-stock churn compounds the drag.
> Run only in tax-advantaged accounts unless you've confirmed your tax
> situation absorbs the drag.

## Headline metrics

Canonical 2007-02-01 → 2026-05-15 (19.3y, post-cost):

| Strategy | Sharpe | CAGR | MaxDD | Calmar | Martin |
|---|---:|---:|---:|---:|---:|
| **PROD 60/30/10 CPM-BULL-NDX** | **1.41** | **18.35%** | **-15.43%** | **1.19** | **5.11** |
| SPY buy-hold | 0.61 | 10.59% | -55.19% | 0.19 | 0.93 |

| Sleeve standalone | Sharpe | CAGR | MaxDD |
|---|---:|---:|---:|
| CPM | 1.19 | 14.21% | -14.74% |
| BULL-QQQ | 1.02 | 17.89% | -28.56% |
| NDX | 1.19 | 39.32% | -48.54% |

## Forward expectation

Discounted from canonical backtest (selection bias + regime dependency +
NDX concentration + tail sequencing risk not captured by return bootstrap):

| Metric | Backtest | Forward base case |
|---|---:|---|
| Sharpe | 1.41 | **0.95-1.25** |
| CAGR | 18.35% | **11-15%** (post-cost, pre-tax) |
| MaxDD | -15.43% | **-18% to -30%** (planning band) |
| Calmar | 1.19 | **0.50-0.85** |
| Martin | 5.11 | **3.0-4.3** |

Base case (mid-band): Sharpe 1.05-1.15, CAGR 12-14%, DD low/mid-20s in a
bad cycle. After-tax drop in taxable accounts: ~5-9% CAGR (vs 11-15% pre-tax).

## Live-trade ticker mapping

Backtest uses long-history tickers; trade with live equivalents.

| Spec | Backtest ticker | Live ticker | Why |
|---|---|---|---|
| Large-cap growth | IWF | **SCHG** | 14bps cheaper, 0.994 daily correlation |
| Commodity basket | DBC | **PDBC** | no K-1 tax form, smarter optimum-yield roll, 0.956 corr |
| All others | (same ticker) | (same ticker) | already optimal |

## Strategy spec

```python
# ---- Helpers (signal date T = last trading day of each calendar month) ----
mom_12_1(asset)    = price[T-1mo] / price[T-13mo] - 1
mom_13612U(asset)  = (r1 + r3 + r6 + r12) / 4         # canonical HAA unweighted
faber_score(asset) = (price[T] - SMA_10mo) / SMA_10mo

# ====== CPM sleeve (60%) ======
RISKY = [QQQ, IWF, VBR, SPHQ,                         # US factor (4)
         EFA, EEM,                                     # international (2)
         GLD, TLT, DBC]                                # diversifiers (3)
canary_on = mom_13612U(HYG) > 0 OR mom_13612U(TIP) > 0 OR mom_13612U(GLD) > 0

if not canary_on:
    cpm = {SHV: 1.0}                                  # 100% cash
else:
    candidates = top_5 by faber_score, dropping faber_score <= 0
    if len(candidates) >= 2:
        pair = min_variance_pair(candidates, halflife=504d)  # EWMA cov, ~2y half-life
        cpm = {pair[0]: 0.5, pair[1]: 0.5}
    elif len(candidates) == 1:
        cpm = {candidates[0]: 0.5, SHV: 0.5}          # partial-safe fill
    else:
        cpm = {SHV: 1.0}

    # Hold buffer: retain prior pair member if its cross-sectional z-score
    # (sample std over positive candidates) is within HOLD_BUFFER=2.0z of
    # the worst new pick. Disabled when fewer than 3 positive candidates.

# Vol cap (de-risk only, scale <= 1.0, no leverage)
scale = min(1.0, 0.15 / realized_vol_63d(cpm))
cpm   = {a: w * scale for a, w in cpm.items()}
cpm[SHV] += 1.0 - sum(cpm.values())                   # cash absorbs residual

# ====== BULL-QQQ sleeve (30%) ======
trend_ok = mom_12_1(QQQ) > 0                          # Antonacci GEM
macro_on = mom_13612U(HYG) > 0 OR mom_13612U(LQD) > 0 OR mom_13612U(TIP) > 0
bull = {QQQ: 1.0} if (trend_ok AND macro_on) else {SHV: 1.0}

# ====== NDX sleeve (10%) ======
if BULL-QQQ regime != "BULL_QQQ":
    ndx = {SHV: 1.0}                                  # gate off
elif PIT NDX-100 data unavailable (pre-2006):
    ndx = bull                                        # mirror BULL-QQQ (extra QQQ)
else:
    momenta = {t: mom_13612U(t) for t in PIT_NDX100(T)}
    picks   = [t for t, m in sorted(momenta, by=-m) if m > 0][:4]
    n       = len(picks)
    ndx     = {t: 0.25 for t in picks}                # 1/K=25% per pick
    ndx[SHV] = 1.0 - 0.25 * n                         # rest in cash (partial fill)

# ---- Combined ----
portfolio = 0.60 * cpm + 0.30 * bull + 0.10 * ndx
# Execution: month-end signal T, trade T+1 OPEN (next-day MOO), 10 bps/side
# Cron: monthly, 10am SGT
```

## Component sources

| Component | Source |
|---|---|
| 12-1 absolute momentum (BULL trend) | Antonacci 2014 dual momentum / Moskowitz et al 2012 TSMOM (`p[T-1mo]/p[T-13mo] - 1`) |
| 13612U momentum (canaries + NDX selection) | Keller & Keuning 2022 HAA canonical; unweighted average of 1/3/6/12-month total returns |
| Faber SMA10m ranker (CPM) | Faber 2007 SSRN "A Quantitative Approach to TAA"; price vs trailing 10mo SMA |
| Min-variance pair selection | Markowitz mean-variance optimization; min equal-weight portfolio variance using EWMA covariance with 504d half-life (RiskMetrics-family estimator, JPM 1996) |
| Hold buffer dampener | Practitioner standard (AQR turnover-aware momentum notes) |
| Vol cap (de-risk only) | Moskowitz/Ooi/Pedersen 2012 TSMOM vol scaling; capped at 1.0 (no leverage) |
| Canary regime gates | Keller HAA-family multi-asset breadth canaries (HYG, LQD, TIP, GLD as credit/inflation/real-asset stress proxies) |
| Top-K cross-sectional selection (NDX) | Jegadeesh & Titman 1993 momentum family |
| PIT Nasdaq-100 constituents (NDX) | `index-constitution` Python library (coverage 2006-01+) |
| Deflated Sharpe Ratio | Bailey & Lopez de Prado 2012 multi-test haircut |

## Universe details

**CPM RISKY (9 assets, all live since 2006-02 = DBC inception):**

- US factors (4): `QQQ` (Nasdaq-100), `IWF` (Russell 1000 Growth → SCHG live),
  `VBR` (small-cap value), `SPHQ` (S&P 500 Quality).
- International (2): `EFA` (developed ex-US, live 2001-08), `EEM`
  (emerging markets, live 2003-04).
- Diversifiers (3): `GLD` (gold), `TLT` (long bonds), `DBC` (commodities → PDBC live).

**CPM safe / cash:** `SHV` (ultra-short Treasury, ~0.3y effective duration).

**CPM canary (3-asset, 13612U any-positive):** `HYG_stitched` (high-yield credit;
VWEHX mutual fund pre-2007-04 + live HYG), `TIP` (inflation-linked bonds),
`GLD` (real-asset / tail hedge).

**BULL-QQQ canary (3-asset, 13612U any-positive):** `HYG_stitched`, `LQD`
(investment-grade credit), `TIP`. Different from CPM canary by design —
BULL-QQQ is a pure equity overlay so the canary requires evidence that
equity risk-taking is healthy (credit markets bidding + real rates supportive).
CPM has cross-asset diversifiers so it uses GLD as the third canary instead.

**NDX universe:** point-in-time Nasdaq-100 constituents at each signal date
(individual stocks; e.g., top-4 might be NVDA / AAPL / MSFT / AVGO in a
tech-led regime).

## Execution

- **Signal date:** last trading day of each calendar month (close).
- **Trade date:** T+1 OPEN (next trading day, Market-On-Open).
- **Cost:** 10 bps per side on any state change.
- **Cron:** monthly, 10am SGT (first business day after month-end).
- **Rebalance frequency:** monthly only, no intramonth updates.
- **Total tickers in a given month:** ~12 (9 CPM risky + SHV cash + QQQ +
  4 NDX stocks; QQQ shared between BULL and CPM-eligible, SHV is universal cash).

## Validation

### Bootstrap CI (block bootstrap, B=2000, 21-day blocks, canonical 19.3y)

| Strategy | Sharpe | Bootstrap mean | 95% CI | P(Sh > 1.0) |
|---|---:|---:|---:|---:|
| CPM standalone | 1.113 | 1.120 | [0.708, 1.528] | 73.2% |
| BULL standalone | 1.011 | 1.011 | [0.578, 1.444] | 52.6% |
| NDX standalone | 1.131 | 1.117 | [0.669, 1.564] | 69.1% |
| **60/30/10 PROD** | **1.364** | **1.362** | **[0.946, 1.796]** | **95.1%** |

### Deflated Sharpe (Bailey-Lopez de Prado, P[true Sh > 0] after N-trial haircut)

| Strategy | N=50 | N=100 | N=500 | N=1000 |
|---|---:|---:|---:|---:|
| CPM standalone | 99.6% | 99.1% | 96.8% | 95.1% |
| BULL standalone | 98.6% | 97.3% | 92.2% | 88.9% |
| NDX standalone | 99.7% | 99.4% | 97.5% | 96.1% |
| **60/30/10 PROD** | **99.99%** | **99.97%** | **99.84%** | **99.70%** |

Bootstrap and DSR results are **supportive but not proof of forward edge**.
The bootstrap Sharpe lower bound (0.946) is roughly at the forward
expectation floor (0.95), so the strategy is supported by the tested data
but not comfortably above the floor. DSR depends heavily on the assumed
effective trial count -- the true hyperparameter search space (9-asset
universe, top-K=5, 504d EWMA cov, HOLD_BUFFER 2.0z, 15% vol cap, 63d
realized lookback, 12-1 trend, 13612U canary, NDX K=4, 60/30/10 blend,
etc.) is plausibly larger than N=1000 even at conservative count. These
results reduce the probability that the historical result is pure noise,
but they do not eliminate model-selection bias, regime risk, data-quality
risk, or implementation drift.

### Extended backtest (~27y, 1999-03-10 → 2026-05-15)

Includes dot-com bust (2000-02), GFC (2008), COVID (2020), 2022 inflation
spike. Pre-2006 the NDX sleeve mirrors BULL-QQQ (PIT constituent data
unavailable); pre-2002 the BULL canary falls back to HYG-only (LQD/TIP not
yet live). Treat pre-2007 as exploratory due to thin canary + universe
proxies.

### Complexity-layer ablation (canonical 19.3y)

Each added complexity layer should justify itself versus simpler adjacent
strategies after cost:

| Strategy | Sharpe | CAGR | MaxDD | Δ Sharpe vs prior |
|---|---:|---:|---:|---:|
| SPY buy-hold | 0.62 | 10.85% | -55.19% | (baseline) |
| QQQ buy-hold | 0.80 | 16.47% | -53.40% | +0.18 (beta switch) |
| QQQ 12-1 timing only | 0.86 | 15.37% | -28.72% | +0.06 (trend filter) |
| 60% CPM + 40% SHV (defensive) | 1.27 | 9.15% | -8.53% | +0.41 (CPM engine) |
| 100% CPM standalone | 1.19 | 14.21% | -14.74% | (alt: CPM full size) |
| **70/30 CPM-BULL (no NDX)** | **1.34** | **15.66%** | **-12.59%** | +0.15 (BULL adds) |
| **PROD 60/30/10 CPM-BULL-NDX** | **1.41** | **18.35%** | **-15.43%** | +0.07 (NDX adds, at +3pp DD cost) |

Each layer adds Sharpe. NDX is the smallest marginal gain (+0.07 Sh) at
the steepest DD cost (+3pp); justified by the +2.7pp CAGR contribution.

### Live-equivalent ETF drift (SCHG, PDBC since 2015)

Backtest uses IWF/DBC (long history); live trade uses SCHG/PDBC (cheaper,
no K-1). Drift over 2015+ common live window:

| Variant | Sharpe | CAGR | MaxDD |
|---|---:|---:|---:|
| Research (IWF, DBC) 2015+ | 1.44 | 19.15% | -15.43% |
| **Live equiv (SCHG, PDBC) 2015+** | **1.37** | **18.39%** | -15.43% |
| Drift | **-0.07** | **-0.76pp** | tied |

Swapping to live ETFs costs ~5% relative Sharpe (within bootstrap CI
noise). Forward expectation should be discounted slightly more for actual
live trading.

### Performance-stat conventions

- **CAGR**: `eq.iloc[-1] ** (1 / years) - 1`, years = calendar days / 365.25.
- **Sharpe**: annualized over zero risk-free rate (`daily.mean() * 252 / (daily.std() * sqrt(252))`).
- **Vol**: annualized daily, `std(daily) * sqrt(252)`, ddof=0.
- **MaxDD**: trough below highest prior peak in cumulative equity.
- **Calmar**: CAGR / |MaxDD|.
- **Martin (Ulcer)**: CAGR / Ulcer Index, where Ulcer = `sqrt(mean(drawdown^2))`.

## Caveats

1. **Tax inefficient outside tax-advantaged accounts.** Monthly rebalance =
   short-term gains. NDX sleeve (individual stocks) compounds tax drag.
   At federal 37% + state 13%, after-tax CAGR drops from 11-15% pre-tax to
   ~5-9%. Run only in IRA / Roth / 401k unless tax-advantaged space is
   fully utilized.

2. **Strategy is not yet live-traded.** All validation is backtest. Bootstrap
   95% CI on Sharpe is [0.946, 1.796] and DSR is 99.7% at N=1000 -- supportive
   but not proof. Future regime may differ from 2007-2026.

3. **Portfolio-level vol is NOT capped.** Only CPM (60%) is vol-targeted at
   15%. BULL (30% QQQ raw, ~18-25% vol) and NDX (10% top-4 stocks, ~30-40%
   vol) run uncapped. Realized blend vol distribution (21-day rolling):

   | Percentile | Annualized vol |
   |---|---:|
   | P50 | 10.3% |
   | P95 | 21.0% |
   | P99 | 27.8% |
   | **Max (COVID 2020-04)** | **38.7%** |

   COVID March-April 2020 showed the strategy can experience ~2.5x the CPM
   sleeve cap in worst-case monthly vol. Plan for this in position sizing.

4. **CPM efficiency degrades in positive stock/bond correlation regimes.**
   2010-2019 (QE / negative correlation): CPM Sh 1.16, CAGR 11.85%.
   2021-2023 (positive correlation regime): CPM Sh 0.85, CAGR 9.43%.
   Sharpe drops ~25-30% when GLD/TLT lose their crisis-hedge property
   (e.g., 2022 inflation/rate-hike cycle). EWMA covariance helps modestly
   (~+0.08 Sh in 2021-23 isolated stress) but can't fully offset the regime
   shift.

5. **NDX sleeve concentration + regime risk.** 4 names × 25% each =
   standalone MaxDD -47%. Mega-cap concentration alpha is regime-dependent;
   a 2000-2010-style tech-lost-decade would likely underperform vs BULL-QQQ
   alone. Pre-2006 PIT constituent data unavailable (NDX mirrors BULL in
   extended backtest).

6. **Effective Nasdaq/growth concentration.** In risk-on regimes, CPM can
   pick QQQ or IWF/SCHG while BULL holds QQQ and NDX holds top Nasdaq-100
   names. Realized growth-exposure distribution (canonical 19.3y):

   | Stat | Total growth/Nasdaq exposure |
   |---|---:|
   | Mean | 44% |
   | Median | 40% |
   | **Max** | **70%** |
   | Months ≥ 70% | **34.6%** (80/231) |

   In 34.6% of months the portfolio runs close to 70% Nasdaq/growth (30%
   CPM growth + 30% BULL QQQ + 10% NDX). This is not a diversified TAA model
   in those regimes -- it's a growth/Nasdaq momentum strategy with tactical
   defensive machinery. The min-vol pair selector prevents 100% growth
   concentration (never picks both QQQ AND IWF as the pair simultaneously).

7. **Cross-asset diversifier dependency.** Drop GLD/TLT/DBC and CPM standalone
   Sharpe drops by 0.32. GLD alone is the largest single-asset dependency
   (-0.21 Sh if dropped); TLT second (-0.18). The strategy is fundamentally
   pair-momentum, not factor rotation.

8. **Structural V-shape recovery lag.** 13612U + canary signals are slow by
   design and bleed 1-2 months of alpha at violent regime turns (COVID 2020).

9. **In-sample selection bias.** Forward Sharpe anchored at 0.95-1.25 (not
   the 1.41 backtest); MaxDD planning band widened to -18% to -30%.

10. **CPM canary HYG+TIP+GLD differs from BULL canary HYG+LQD+TIP.** When CPM
    is in cash (all three negative) but BULL has LQD+ → portfolio can hold
    30% QQQ while 60% of capital is in SHV. Intentional; CPM uses GLD as
    real-asset diversifier while BULL uses LQD as equity-confirmation signal.

11. **Pre-2007 extended backtest is least reliable in exactly the periods
    that matter most.** Dot-com (2000-02) and GFC (2008) are precisely when
    the defensive machinery is supposed to prove itself, but they use
    proxy-stitched data (mutual-fund proxies for some assets pre-2005;
    NDX sleeve mirrors BULL pre-2006 PIT). Treat pre-2007 results as
    directional only, not as confirmation.

12. **Data sources are research-grade, not production-grade.** Live system
    uses `yfinance` for price data and `index-constitution` for PIT NDX-100
    membership. Both are suitable for research/personal use but neither is
    audited institutional infrastructure. `yfinance` is not affiliated
    with Yahoo (free tier intended for personal use); `index-constitution`
    sources NDX-100 membership from Wikipedia (beta-status package).
    Production deployment should snapshot all raw inputs, constituent
    lists, missing-symbol logs, and orders for each rebalance for audit.
    NDX sleeve specifically may have survivorship leakage (delisted tickers
    missing from yfinance) that PIT lookups can't fully resolve.

13. **Live-equivalent ETF drift.** Backtest uses IWF + DBC (long history);
    live trade uses SCHG (large-cap growth, 4bps fee) + PDBC (no K-1
    commodity strategy). Drift over 2015+ common live: -0.07 Sh, -0.76pp
    CAGR (live underperforms research). Within bootstrap noise but real.

14. **Cost formula:** transaction cost charged as
    `cost = COST_BPS_PER_SIDE / 10000 * sum(abs(w_new - w_old))`,
    where the sum already includes both legs (one sell + one buy per asset).
    At 10bps/side, a full 100% A → 100% B switch costs **20 bps** of
    portfolio value (10 sell + 10 buy). Each sleeve charges this
    independently; CPM uses sleeve-level turnover, BULL/NDX use
    state-change turnover.

## Deployment

Monthly cron (10am SGT, first business day after month-end) + dashboard
hosting via Cloudflare + GitHub Actions ($0/mo):

```
CF Workers cron (durable, no 60d inactivity penalty, schedules 10am SGT monthly)
  → triggers GH Actions via repository_dispatch
GH Actions runner
  → uv run cpm_live.py allocate
  → uv run build_dashboard.py
  → wrangler pages deploy → https://cpm-bull-dashboard.pages.dev/
  → Telegram notification with signal + dashboard URL
```

One-shot setup: `bash deploy/setup.sh`
Details: `deploy/cf-pages/README.md`, `deploy/cf-cron/README.md`

## Files

- `cpm_live.py` — CPM sleeve (allocate + backtest CLI, panel loader)
- `bull_qqq_live.py` — BULL-QQQ sleeve (allocate + backtest CLI)
- `ndx_sleeve_live.py` — NDX sleeve (allocate + backtest, PIT constituent fetch)
- `build_dashboard.py` — dashboard generator (production 60/30/10 blend + peer benchmarks)
- `data/` — stitched price series (HYG, GLD, TIP)
- `data/ndx_constituents/prices.parquet` — cached NDX-100 historical prices
- `deploy/` — Cloudflare cron + Pages deployment
- `research/` — exploratory analyses (historical; not loaded by live spec)

## Usage

```bash
# Show current allocation (latest month-end signal)
uv run cpm_live.py allocate
uv run bull_qqq_live.py allocate
uv run ndx_sleeve_live.py

# Run a backtest
uv run cpm_live.py backtest --start 2007-02-01

# Rebuild dashboard
uv run build_dashboard.py
```
