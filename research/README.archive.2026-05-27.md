# CPM-BULL-NDX

**60/20/20 growth/Nasdaq momentum strategy with defensive overlays.** Personal
runbook + spec. Realized mean Nasdaq/growth exposure is 44% with max 70% in
34.6% of months, so this is not a fully diversified all-weather TAA. Defensive
machinery is canaries, the NDX DD circuit, and CPM pair selection.

Research detail lives in `cpm_bull_ndx_handout.md` and `bull_qqq_handout.md`.

- **CPM (60%)** — canary-gated momentum + min-variance pair selection on a
  9-asset ETF universe (US factors + international + diversifiers). HYG+TIP+GLD
  canary is a triple-negative stress veto: CPM is defensive only when all three
  are negative; otherwise CPM can run normally. HAA best-of-safe (SHV/IEF) on defensive.
- **BULL-SPY (20%)** — 100% SPY when HYG OR TIP canary and SPY 13612U momentum both pass. Otherwise, HAA best-of-safe (SHV/IEF). SPY chosen over QQQ for lower overlap with NDX.
- **NDX (20%)** — top-5 PIT Nasdaq-100 stocks by GPM score (13612U momentum penalized by 260d correlation), 20% each, active strictly when the TIP canary passes. Each pick is 4.0% of the portfolio. Defensive paths use HAA best-of-safe (SHV/IEF).

**Risk overlay:** NDX DD circuit scales NDX to cash when NDX sleeve DD from its
63d rolling peak is below -10%, until the next monthly signal date.

Monthly rebalance, ETF + individual stocks (NDX), no leverage, 10 bps/side cost,
T+1 OPEN execution. Total-return prices (yfinance `auto_adjust=True`). Run only
in tax-advantaged accounts.

> ⚠️ **Not yet live-traded.** All validation is backtest.

## Expected performance

Clean live-ETF window 2008-04-30 → 2026-05-22 (18.1y, post-cost). Raw backtest.

| Strategy | Sharpe | CAGR | Vol | MaxDD | Ulcer |
|---|---:|---:|---:|---:|---:|
| **PROD 60/20/20 (BULL-SPY)** | **1.71** | **18.58%** | **10.32%** | **-10.89%** | **2.60%** |
| Naive 60/40 PP/SPY-trend | 0.99 | 7.70% | 7.79% | -14.41% | 4.08% |
| SPY buy-hold | 0.66 | 11.76% | 19.79% | -51.48% | -- |
| QQQ buy-hold | 0.82 | 17.23% | 22.29% | -49.37% | -- |

| Sleeve standalone | Sharpe | CAGR | Vol | MaxDD |
|---|---:|---:|---:|---:|
| CPM | 1.30 | 15.22% | 11.41% | -12.35% |
| BULL-SPY | 1.02 | 12.96% | 12.73% | -20.28% |
| NDX top-K | 1.45 | 32.63% | 20.98% | -18.33% |

**Naive benchmark suite** primary peer is `Naive 60/40 PP/SPY-trend`
(Permanent Portfolio + SPY 10mo SMA trend), apples-to-apples with BULL-SPY.
QQQ buy-and-hold remains as upper-bound tech reference.

## Strategy specification

```python
# Signal date T = last trading day of each calendar month.
mom_12mo(asset)    = price[T] / price[T-12mo] - 1                 # Antonacci GEM TR (no skip-month)
mom_13612U(asset)  = (r1 + r3 + r6 + r12) / 4         # canonical HAA unweighted
faber_score(asset) = (price[T] - SMA_10mo) / SMA_10mo

# ====== CPM sleeve (60%) ======
RISKY = [QQQ, IWF, VBR, SPHQ,                         # US factor (4)
         EFA, EEM,                                     # international (2)
         GLD, TLT, DBC]                                # diversifiers (3)
canary_on = mom_13612U(HYG) > 0 OR mom_13612U(TIP) > 0 OR mom_13612U(GLD) > 0

# HAA-style best-of-safe: SHV or IEF by 13612U momentum.
safe = argmax({s: mom_13612U(s) for s in [SHV, IEF]})

if not canary_on:
    cpm = {safe: 1.0}                                 # 100% HAA-safe
else:
    candidates = top_5 by faber_score, dropping faber_score <= 0
    if len(candidates) >= 2:
        pair = min_variance_pair(candidates, lookback=504d)  # simple rolling cov
        cpm = {pair[0]: 0.5, pair[1]: 0.5}
    elif len(candidates) == 1:
        cpm = {candidates[0]: 0.5, safe: 0.5}          # partial-safe fill
    else:
        cpm = {safe: 1.0}

    # Hold buffer: retain prior pair member if cross-sectional z-score
    # is within HOLD_BUFFER=2.0z of worst new pick. Off when < 3 positive.

# Vol cap (de-risk only, scale <= 1.0)
scale = min(1.0, 0.15 / realized_vol_63d(cpm))   # 15% vol cap (de-risk only)
cpm   = {a: w * scale for a, w in cpm.items()}
cpm[SHV] += 1.0 - sum(cpm.values())

# ====== BULL sleeve (20%) ======
canary_on    = (mom_13612U(HYG_stitched) > 0) OR (mom_13612U(TIP) > 0)
asset_mom_on = mom_13612U(SPY) > 0

# HAA best-of-safe: SHV in rising-rate regimes, IEF in falling-rate.
safe = argmax({s: mom_13612U(s) for s in [SHV, IEF]})

if canary_on AND asset_mom_on:
    bull = {SPY: 1.0}
else:
    # Clean binary gate: full risk-on or full safe.
    bull = {safe: 1.0}                  # CASH

# ====== NDX sleeve (20%) ======
ndx_active = mom_13612U(TIP) > 0  # Gating: TIP-only canary

if ndx_active:
    # Top-5 by GPM score: 13612U momentum penalized by 260d correlation
    scores = {t: mom_13612U(t) * (1.0 - corr_260d(t)) for t in PIT_NDX100(T)}
    picks  = [t for t, s in sorted(scores, by=-s) if mom_13612U(t) > 0][:5]
    ndx    = {t: 0.20 for t in picks}                  # 1/K=20.0% per pick
    ndx[safe] = 1.0 - 0.20 * len(picks)                # partial-fill -> best-of-safe
else:
    ndx = {safe: 1.0}                                  # 100% best-of-safe

# ====== NDX-only DD circuit breaker (Nystrup-Boyd 2019) ======
# Daily check on NDX sleeve only: if DD from 63d rolling peak < -10%,
# scale NDX to 0 (cash) until next monthly signal date.
# Nystrup-Boyd Dmax = 10% paper standard. 63d rolling peak (1 quarter,
# matches r3 component in 13612U) avoids stale-peak suppression.
rolling_peak = ndx_eq.rolling(63).max()
ndx_dd = (ndx_eq / rolling_peak - 1)[T-1]
ndx_scale = 0.0 if ndx_dd < -0.10 else 1.0   # resets at next signal date
ndx = ndx_scale * ndx

# ---- Combined ----
portfolio = 0.60 * cpm + 0.20 * bull + 0.20 * ndx
```

**Universe** (all live since 2006-02 = DBC inception):

| Pool | Tickers |
|---|---|
| CPM RISKY (9) | QQQ, IWF, VBR, SPHQ, EFA, EEM, GLD, TLT, DBC |
| Safe pool (HAA best-of by 13612U) | SHV (ultra-short), IEF (7-10y) -- used by both CPM and BULL |
| CPM canary (3, HAA-style) | HYG, TIP, GLD |
| BULL canary (2, OR) | HYG_stitched, TIP |
| NDX | point-in-time Nasdaq-100 (top-5 by GPM score, 20% each) |

**Method lineage** (full citations in `cpm_bull_ndx_handout.md`):

| Component | Source |
|---|---|
| 12-month TR absolute momentum (no skip) | Antonacci 2014 GEM / Moskowitz et al 2012 TSMOM |
| 13612U momentum | Keller & Keuning 2022 HAA canonical |
| Faber SMA10m ranker | Faber 2007 SSRN TAA |
| Min-variance pair (rolling 504d) | Markowitz / standard mean-variance |
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
- Typical month: 16 tickers (9 CPM risky + SHV/IEF safe pool + QQQ + 8 NDX stocks).

Methodology, robustness ledger, sensitivity grids, and references live in
`cpm_bull_ndx_handout.md`.

**Hold-buffer**: HB=2.0z. Disabled when (a) fewer than 3 positive
candidates, (b) held asset's faber score <= 0, or (c) canary-state
transition between months.

Current architecture (single-universe Faber rank for CPM, plain 13612U
for NDX, HYG OR TIP canary plus SPY 12m momentum for BULL) is the active
configuration.

**Performance-stat conventions:** CAGR = `eq[-1] ** (1/years) - 1`,
years = calendar_days / 365.25. Sharpe = annualized at 0% rf
(`daily.mean() * 252 / (daily.std() * sqrt(252))`). Vol = `std(daily) * sqrt(252)`,
ddof=0. MaxDD = trough below highest prior peak. Calmar = CAGR / |MaxDD|.

## Key caveats

**Tax & live status**

- Monthly rotation creates short-term gains. Tax-advantaged accounts only.
- Strategy is NOT live-traded. All performance is backtest.

**Vol & concentration**

- CPM is vol-targeted at 15% sleeve-internal. BULL and NDX are not
  sleeve-vol-targeted. NDX DD circuit is the sole portfolio-level tail overlay.
- Realized blend 63d vol distribution (CLEAN 18.1y):

  | Variant | P50 | P75 | P90 | P95 | P99 | Max |
  |---|---:|---:|---:|---:|---:|---:|
  | Baseline (no DD circuit) | 9.68% | 12.32% | 14.93% | 16.40% | 19.54% | 20.78% |
  | **PROD (NDX-only DD circuit)** | **9.25%** | **11.20%** | **12.74%** | **13.88%** | **15.84%** | **17.48%** |

- Effective Nasdaq/growth exposure: mean 44%, median 40%, max 70%, at least
  70% in 34.6% of months.
- NDX sleeve standalone MaxDD is -18.33% in the clean live-ETF window (with the daily -10% circuit breaker).

**NDX data caveat**

NDX backtest depends on PIT membership and available price history. Held ticker
delisting mid-period applies a -10% haircut and rotates to SHV for the rest of
the holding period.

**CPM diversifier dependency (primary structural risk)**

CPM is fundamentally a pair-momentum engine on a 9-asset universe whose edge
depends materially on GLD and TLT as crisis hedges with stable covariance
structure. Drop GLD/TLT/DBC and CPM Sharpe drops -0.32 (GLD alone -0.21,
TLT -0.18). In a regime where both GLD and TLT trend down simultaneously
(2022 inflation/rate-hike cycle is the live example), the min-variance pair
selector cannot compensate because the rolling covariance structure it is
trained on does not reflect the new regime. This is more specific than
"positive stock/bond correlation degrades efficiency": it is a covariance-
regime risk concentrated in two assets.

**Forward review triggers.** Consider a strategy review if any of: (a) 12-month
rolling GLD-TLT correlation turns positive and stays > 0.4 for two quarters,
(b) CPM rolling 12-month Sharpe drops below 0.5 for two quarters, (c) CPM
rolling 12-month MaxDD exceeds -18%. These are early signals that the
covariance regime has shifted away from the one CPM was designed for.

**Regime & model risk**

- CPM depends on GLD/TLT/DBC diversifier behavior and can degrade when those
  diversifiers stop offsetting equity risk.
- Monthly 12-month momentum signals can lag fast V-shaped recoveries.
- NDX inherits BULL's macro verdict, so macro defensive signals can override
  still-positive stock-level momentum.
- CPM and BULL have independent canaries; one sleeve can be defensive while
  another is risk-on.

**Data quality (production-readiness blockers, not nice-to-haves)**

Live system uses `yfinance` (Yahoo scraper, beta; Yahoo Finance API is
intended for personal use, not endorsed) and `index-constitution` (Wikipedia-
sourced, beta; old tickers not auto-resolved in strict membership checks).
Known failure modes: yfinance DOM-change breakage, rate limiting / missing
data on month-end for individual NDX stocks, bad split/dividend adjustments,
unresolved old ticker symbols, NDX delisted-ticker leakage.

**Backtested data-gap frequency** (CLEAN 18.1y panel):

| Pool | Total slot-checks | Missing | Rate |
|---|---:|---:|---:|
| CPM required ETFs (12 tickers × 151 months) | 1812 | 0 | **0.00%** |
| NDX PIT members (last 60 months) | 6287 | 433 | **6.89%** |

CPM ETF coverage is robust: zero historical gaps means abort-on-missing-data
would never have triggered. NDX gap rate is 6.89% at the universe level; a
missing ticker matters only if it would have ranked into the top-8 momentum
picks.

**For small personal capital this may be tolerable. For meaningful sizing
the following are required, not optional:**

- abort-on-missing-data for required ETFs;
- abort-on-suspicious split/dividend jumps (sanity check vs prior bar);
- per-rebalance raw data snapshot (price panel as fetched);
- per-rebalance constituent-list snapshot (NDX membership at signal date);
- per-rebalance signal snapshot (canary states, pillar values, picks);
- per-rebalance final allocation snapshot;
- broker order/fill snapshot;
- fallback data vendor (Tiingo / Polygon / IEX Cloud);
- alerting on stale data, missing tickers, and changed constituent counts.

None of these are currently implemented. They are blockers for scaling
beyond small pilot capital.

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
- `bull_qqq_live.py` — BULL sleeve.
- `ndx_sleeve_live.py` — NDX sleeve (PIT constituent fetch).
- `build_dashboard.py` — 60/20/20 blend dashboard + peer benchmarks.
- `vol_cap.py` — NDX DD circuit breaker helpers only (63d rolling peak; -10% Nystrup-Boyd threshold; scale to cash until next monthly signal).
- `data/` — input data; `data/ndx_constituents/prices.parquet` cached.
- `deploy/` — Cloudflare cron + Pages (monthly signal + daily DD check dispatch).
- `.github/workflows/monthly-signal.yml` — monthly rebalance + dashboard rebuild.
- `.github/workflows/dd-check.yml` — daily DD circuit check + Telegram alert.
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
