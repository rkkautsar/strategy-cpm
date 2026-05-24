# CPM-BULL-NDX

**60/20/20 multi-sleeve tactical asset allocation.** Personal runbook + spec.
Blend validation detail (NDX MC, bootstrap, DSR, ablation, hold-buffer) in
`cpm_bull_ndx_handout.md`. BULL-QQQ academic memo in `bull_qqq_handout.md`.

- **CPM (60%)** — canary-gated momentum + min-variance pair selection on a
  9-asset ETF universe (US factors + international + diversifiers).
- **BULL-QQQ (20%)** — 100% QQQ when all three Keller-canonical "any positive"
  gates pass: (1) HYG OR TIP 13612U > 0 (canary), (2) curve OR vol regime
  pillar, (3) QQQ 12-1 absolute momentum > 0. HAA-style best-of-safe(SHV, IEF)
  by 13612U otherwise.
- **NDX (20%)** — top-4 PIT Nasdaq-100 stocks by 13612U momentum, 25% each,
  gated by the BULL-QQQ regime.

Monthly rebalance, ETF + individual stocks (NDX), no leverage, 10 bps/side cost,
T+1 OPEN execution. Total-return prices (yfinance `auto_adjust=True`).

> ⚠️ **Not yet live-traded.** All validation is backtest. Bootstrap CI / DSR are
> supportive but not proof of forward edge.
>
> ⚠️ **IRA/401k/Roth only.** Monthly rotation = short-term gains. Federal 22-37%
> + state 0-13% can drop after-tax CAGR from **12-16% pre-tax to ~6-10%
> after-tax** — close to SPY buy-hold after-tax. NDX stock churn compounds the
> drag. Run only in tax-advantaged accounts.

## Expected performance

Clean live-ETF window 2008-04-30 → 2026-05-15 (18.1y, post-cost). Raw backtest;
Shumway-pessimistic survivor-bias MC shifts PROD by < 0.01 Sharpe / 0.05pp CAGR
(see Caveats § NDX bias).

| Strategy | Sharpe | CAGR | Vol | MaxDD | Calmar |
|---|---:|---:|---:|---:|---:|
| **PROD 60/20/20 CPM-BULL-NDX** | **1.58** | **19.33%** | **11.64%** | **-12.93%** | **1.49** |
| SPY buy-hold | 0.66 | 11.78% | 19.81% | -51.48% | 0.23 |

| Sleeve standalone | Sharpe | CAGR | Vol | MaxDD |
|---|---:|---:|---:|---:|
| CPM | 1.28 | 13.75% | 10.48% | -11.30% |
| BULL-QQQ | 1.18 | 16.88% | 14.05% | -14.31% |
| NDX (raw) | 1.26 | 36.44% | 27.70% | -35.92% |
| NDX (Shumway-MC) | 1.22 | 35.97% | 27.73% | -37.31% |

Extended 30y window 1996-01-04 → 2026-05-15 (uses Vanguard mutual fund stitches
pre-live for non-live ETFs; HYG-only canary pre-2001-06; directional only):

| Strategy | Sharpe | CAGR | MaxDD |
|---|---:|---:|---:|
| **PROD 60/20/20** | **1.34** | **16.42%** | **-16.59%** |
| SPY buy-hold | 0.61 | 10.41% | -55.19% |

**Forward expectation** (discount for selection bias + regime dependency + NDX
biases + tail sequencing not captured by return bootstrap):

| Metric | Backtest | Forward base case |
|---|---:|---|
| Sharpe | 1.58 | **1.05-1.35** |
| CAGR | 19.33% | **12-16%** pre-tax, **6-10%** after-tax |
| MaxDD | -12.93% | **-15% to -25%** planning band |
| Calmar | 1.49 | **0.60-0.95** |

## Strategy specification

```python
# Signal date T = last trading day of each calendar month.
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
        pair = min_variance_pair(candidates, halflife=504d)  # EWMA cov
        cpm = {pair[0]: 0.5, pair[1]: 0.5}
    elif len(candidates) == 1:
        cpm = {candidates[0]: 0.5, SHV: 0.5}          # partial-safe fill
    else:
        cpm = {SHV: 1.0}

    # Hold buffer: retain prior pair member if cross-sectional z-score
    # is within HOLD_BUFFER=2.0z of worst new pick. Off when < 3 positive.

# Vol cap (de-risk only, scale <= 1.0)
scale = min(1.0, 0.15 / realized_vol_63d(cpm))
cpm   = {a: w * scale for a, w in cpm.items()}
cpm[SHV] += 1.0 - sum(cpm.values())

# ====== BULL-QQQ sleeve (20%) ======
canary_on    = mom_13612U(HYG) > 0 OR mom_13612U(TIP) > 0
p_curve      = sum(IEF[T-63d:T] ret) > sum(TLT[T-63d:T] ret)   # curve steepening
p_vol        = realized_vol_63d(SPY) < avg(rolling_63d_vol over 252d, SPY)
composite_on = p_curve OR p_vol
asset_mom_on = mom_12_1(QQQ) > 0

if canary_on AND composite_on AND asset_mom_on:
    bull = {QQQ: 1.0}
else:
    # HAA best-of-safe: SHV in rising-rate regimes, IEF in falling-rate.
    bull = {argmax({s: mom_13612U(s) for s in [SHV, IEF]}): 1.0}

# ====== NDX sleeve (20%) ======
if BULL-QQQ regime != "BULL_QQQ":
    ndx = {SHV: 1.0}
elif PIT NDX-100 data unavailable (pre-2006):
    ndx = bull                                        # mirror BULL-QQQ
else:
    momenta = {t: mom_13612U(t) for t in PIT_NDX100(T)}
    picks   = [t for t, m in sorted(momenta, by=-m) if m > 0][:4]
    ndx     = {t: 0.25 for t in picks}
    ndx[SHV] = 1.0 - 0.25 * len(picks)

# ---- Combined ----
portfolio = 0.60 * cpm + 0.20 * bull + 0.20 * ndx
```

**Universe** (all live since 2006-02 = DBC inception):

| Pool | Tickers |
|---|---|
| CPM RISKY (9) | QQQ, IWF, VBR, SPHQ, EFA, EEM, GLD, TLT, DBC |
| Safe / cash | SHV (BULL also uses IEF as best-of-safe) |
| CPM canary (3, HAA-style) | HYG_stitched, TIP, GLD |
| BULL canary (2) | HYG_stitched, TIP (LQD rejected: IG rallies on rate cuts during equity crashes, falsely keeps gate on in dotcom-style regimes) |
| NDX | point-in-time Nasdaq-100 (top-4 by 13612U) |

`HYG_stitched` = VWEHX mutual fund pre-2007-04 + live HYG.

**Method lineage** (full citations in `cpm_bull_ndx_handout.md` §7):

| Component | Source |
|---|---|
| 12-1 absolute momentum | Antonacci 2014 dual momentum / Moskowitz et al 2012 TSMOM |
| 13612U momentum | Keller & Keuning 2022 HAA canonical |
| Faber SMA10m ranker | Faber 2007 SSRN TAA |
| Min-variance pair (EWMA 504d) | Markowitz + RiskMetrics-family (JPM 1996) |
| Vol cap (de-risk only) | Moskowitz/Ooi/Pedersen 2012 TSMOM scaling |
| Canary regime gates | Keller HAA-family multi-asset breadth canaries |
| Top-K cross-sectional (NDX) | Jegadeesh & Titman 1993 |
| PIT NDX-100 constituents | `index-constitution` library (≥ 2006-01) |
| Deflated Sharpe | Bailey & Lopez de Prado 2012 |

**Execution:**

- Signal date: last trading day of each calendar month (close).
- Trade date: T+1 OPEN (next-day MOO).
- Cost: 10 bps/side on any state change (full A→B switch = 20 bps).
- Cron: monthly, 10am SGT (first business day after month-end).
- Typical month: ~12 tickers (9 CPM risky + SHV + QQQ + 4 NDX stocks).

## Validation summary

All validation detail (tables, methodology, sensitivity grids, complexity
ablation) lives in `cpm_bull_ndx_handout.md`. High-level conclusion:

- **Block bootstrap** (B=2000, 21d blocks): blend Sharpe 95% CI excludes the
  forward-expectation floor only modestly — lower bound roughly at the floor.
  Supportive, not proof.
- **Deflated Sharpe** (Bailey-Lopez de Prado): blend P[true Sh > 0] = 99.7% at
  N=1000 trial haircut. Sensitive to assumed effective trial count.
- **Complexity-layer ablation**: each layer (CPM → +BULL → +NDX) adds Sharpe.
  NDX is smallest marginal gain (+0.07 Sh) at steepest DD cost (+3pp).
- **Hold-buffer sensitivity**: HB=2.0z reduces CPM MaxDD by 3.7pp vs HB=0 for
  marginal Sharpe loss; flat plateau across HB ∈ [2, 5]z.
- **30y extended window**: includes dotcom, GFC, COVID, 2022 inflation;
  pre-2006 NDX mirrors BULL and pre-2001-06 canary reduces to HYG-only.
  Asset-momentum 12-1 circuit breaker is primary defense in macro-confusion
  regimes (dotcom).

Bootstrap + DSR reduce noise probability but do not eliminate model-selection
bias, regime risk, data-quality risk, or implementation drift.

**Performance-stat conventions:** CAGR = `eq[-1] ** (1/years) - 1`,
years = calendar_days / 365.25. Sharpe = annualized at 0% rf
(`daily.mean() * 252 / (daily.std() * sqrt(252))`). Vol = `std(daily) * sqrt(252)`,
ddof=0. MaxDD = trough below highest prior peak. Calmar = CAGR / |MaxDD|.

## Key caveats

**Tax & live status**

- Monthly rotation = short-term gains; NDX stock churn compounds drag. After-tax
  CAGR drops from 12-16% to ~6-10%. Tax-advantaged accounts only.
- Strategy is NOT live-traded. All performance is backtest.

**Vol & concentration**

- **Portfolio-level vol is NOT capped.** Only CPM (60%) is vol-targeted at 15%.
  BULL (~18-25% vol) and NDX (~30-40% vol) run uncapped. Realized blend vol
  (21d rolling): P50 10.3%, P95 21.0%, P99 27.8%, **max 38.7%** (COVID 2020-04).
- **Effective Nasdaq/growth concentration**: in risk-on regimes CPM can hold
  QQQ/IWF while BULL holds QQQ and NDX holds top Nasdaq names. Realized growth
  exposure: mean 44%, median 40%, **max ~70%**, ≥70% in 34.6% of months. Not a
  diversified TAA in those regimes — it's growth/Nasdaq momentum with tactical
  defensive machinery. Min-vol pair selector prevents 100% growth (never picks
  both QQQ AND IWF as the pair).
- NDX sleeve standalone MaxDD ~ -36% (raw) / -37% (Shumway-MC). Mega-cap
  concentration alpha is regime-dependent; 2000-2010-style tech lost decade
  would likely underperform vs BULL-QQQ alone.

**NDX bias**

NDX sleeve has documented backtest biases. Monte Carlo stress (Shumway 1999
academic distribution, 24% delist rate, 1000 sims) shows the impact on PROD
blend is **< 0.01 Sharpe / 0.05pp CAGR** under realistic distributions; even
worst-case (25% bankruptcy at -80%) bounds the impact at ~0.07 Sharpe / 0.9pp
CAGR. The 20% blend weight structurally bounds the bias. Bias sources:

- **Yearly PIT membership** (mid-year adds appear from Jan 1 of that year).
- **Missing delisted tickers** (24% of historical NDX-100 names have no panel
  data; selection pool tilts toward survivors — dominant remaining bias).
- **NaN-in-holding**: held NDX ticker delisting mid-period applies -10% haircut
  (blended bankruptcy/acquisition estimate) and rotates to SHV for the rest of
  the period.
- **Pre-2006 fallback**: NDX mirrors BULL (PIT data unavailable).

Full MC tables + Shumway references in `cpm_bull_ndx_handout.md` §1, §7.

**Regime & model risk**

- CPM degrades in positive stock/bond correlation regimes. 2010-2019 (QE):
  Sharpe 1.16. 2021-2023 (positive correlation): Sharpe 0.85, ~25-30% drop
  when GLD/TLT lose crisis-hedge property. EWMA covariance helps modestly
  (~+0.08 Sh in 2021-23) but can't fully offset the regime shift.
- **Cross-asset diversifier dependency**: drop GLD/TLT/DBC and CPM Sharpe drops
  -0.32 (GLD alone -0.21, TLT -0.18). Fundamentally pair-momentum, not factor
  rotation.
- **Structural V-shape recovery lag**: 13612U + canary are slow by design,
  bleeding 1-2 months of alpha at violent regime turns (COVID 2020).
- **In-sample selection bias**: anchor forward Sharpe at 1.05-1.35 (not 1.58
  backtest); planning MaxDD band -15 to -25%.
- **CPM/BULL canary asymmetry**: when CPM all-cash (HYG+TIP+GLD all negative)
  but BULL canary fires, portfolio can hold 20% QQQ + 20% NDX with 60% SHV.
  Intentional — different defensive geometries.

**Pre-2007 backtest reliability**

Dot-com (2000-02) and GFC (2008) are exactly where the defensive machinery
matters most, but they use proxy-stitched data (mutual-fund proxies for some
ETFs pre-2005; NDX sleeve mirrors BULL pre-2006 PIT). Directional only.

**Data quality (research-grade, not production-grade)**

Live system uses `yfinance` (Yahoo scraper, beta) and `index-constitution`
(Wikipedia-sourced, beta). Known failure modes: yfinance DOM-change breakage,
rate limiting / missing data on month-end for individual NDX stocks, bad
split/dividend adjustments, unresolved old ticker symbols, NDX delisted-ticker
leakage. Production deployment should add data-validation circuit breakers
(abort + alert on missing required ticker rather than silently exclude), and
snapshot raw inputs + constituent lists + orders per rebalance for audit.
Consider migrating to Tiingo / Polygon / IEX Cloud before scaling capital.

## Deployment and usage

Monthly cron via Cloudflare Workers + GitHub Actions ($0/mo):

```
CF Workers cron (10am SGT monthly, durable)
  → repository_dispatch → GH Actions runner
  → uv run cpm_live.py allocate
  → uv run build_dashboard.py
  → wrangler pages deploy → https://cpm-bull-dashboard.pages.dev/
  → Telegram notification with signal + dashboard URL
```

One-shot setup: `bash deploy/setup.sh`. Details in `deploy/cf-pages/README.md`,
`deploy/cf-cron/README.md`.

**Entry points:**

- `cpm_live.py` — CPM sleeve (allocate + backtest CLI, panel loader).
- `bull_qqq_live.py` — BULL-QQQ sleeve.
- `ndx_sleeve_live.py` — NDX sleeve (PIT constituent fetch).
- `build_dashboard.py` — 60/20/20 blend dashboard + peer benchmarks.
- `data/` — stitched series; `data/ndx_constituents/prices.parquet` cached.
- `deploy/` — Cloudflare cron + Pages.
- `research/` — exploratory analyses (not loaded by live spec).

```bash
# Current allocation (latest month-end signal)
uv run cpm_live.py allocate
uv run bull_qqq_live.py allocate
uv run ndx_sleeve_live.py

# Backtest
uv run cpm_live.py backtest --start 2008-04-30

# Rebuild dashboard
uv run build_dashboard.py
```
