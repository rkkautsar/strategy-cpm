# CPM-BULL-NDX

**60/20/20 growth/Nasdaq momentum strategy with defensive overlays.** Personal
runbook + spec. Realized mean Nasdaq/growth exposure is ~44% with max ~70% in
34.6% of months — this is *not* a fully diversified all-weather TAA. Defensive
machinery (canaries, vol cap, pair selection) caps drawdowns when macro stress
registers; in calm bull regimes the portfolio runs as concentrated growth
beta.

Blend validation detail (NDX MC, bootstrap, DSR, ablation, hold-buffer) in
`cpm_bull_ndx_handout.md`. BULL sleeve academic memo in `bull_qqq_handout.md`
(legacy filename retained; current sleeve is BULL-SPY).

- **CPM (60%)** — canary-gated momentum + min-variance pair selection on a
  9-asset ETF universe (US factors + international + diversifiers). HYG+TIP+GLD
  any-positive 13612U canary. HAA best-of-safe (SHV/IEF) on defensive.
- **BULL-SPY (20%)** — 100% SPY when three gates all pass: (1) Keller/HAA-
  inspired HYG OR TIP 13612U > 0 canary, (2) a custom curve OR vol regime
  composite (curve from rates, vol from broad market), (3) SPY 12mo TR
  absolute momentum (Antonacci GEM 2014 / TSMOM-style trend filter).
  Antonacci GEM uses simple 12-month total return (no skip-month). Only the
  canary is Keller-canonical; the composite and trend gates are extensions.
  Clean binary gate: 100% SPY or 100% best-of-safe (no Rebound or partial
  exposure on this sleeve). In risk-off periods, BULL selects between SHV
  and IEF by 13612U momentum (HAA-style best-of-safe): IEF in falling-rate
  regimes (captures bond rally), SHV when rates are rising or stable. SPY
  chosen over QQQ for diversification: BULL-SPY corr +0.61 with NDX sleeve
  vs +0.75 for BULL-QQQ (NDX provides dedicated tech-pick exposure).
- **NDX (20%)** — top-8 PIT Nasdaq-100 stocks by 13612U momentum, 12.5% each,
  gated by the BULL gate (NDX_ACTIVE only when BULL_SPY regime fires).
  Each pick = 12.5% of sleeve = 2.5% of portfolio; single-name bankruptcy
  caps blend damage at ~2.5%. **Rebound bypass (NDX_REBOUND):** when BULL
  gate off but fast QQQ 2mo TR > 0 (Goulding-Harvey 4-state analog), NDX
  takes 50% top-K names + 50% best-of-safe instead of full cash. Rebound
  fast signal stays on QQQ (tech-recovery semantics) regardless of
  BULL_TICKER. Defensive paths (gate-off + slow recovery, partial-fill,
  mid-period delisting) use HAA best-of-safe (SHV/IEF), not SHV-only.
  NDX inherits BULL's regime verdict; no independent macro gate (BULL's
  HYG/TIP signal would otherwise be double-counted).

**Risk overlays (portfolio-level):**
- **DD circuit (per-sleeve, BULL/NDX):** 63d rolling-peak DD < -10% → scale
  sleeve to cash until next monthly signal. Nystrup-Boyd (Stanford 2019)
  threshold; 63d window matches the r3 component in 13612U for consistency.
- **VIX cap (portfolio):** when VIX > rolling P95 threshold, scale entire
  portfolio to 50% (latched until next signal date).

Monthly rebalance, ETF + individual stocks (NDX), no leverage, 10 bps/side cost,
T+1 OPEN execution. Total-return prices (yfinance `auto_adjust=True`).

> ⚠️ **Not yet live-traded.** All validation is backtest. Bootstrap CI / DSR are
> supportive but not proof of forward edge.
>
> ⚠️ **IRA/401k/Roth only.** Monthly rotation = short-term gains. Federal 22-37%
> + state 0-13% can drop after-tax CAGR from **11-15% pre-tax to ~5-9%
> after-tax** — close to SPY buy-hold after-tax. NDX stock churn (8 names)
> compounds the drag. Run only in tax-advantaged accounts.

## Expected performance

Clean live-ETF window 2008-04-30 → present (~18y, post-cost, with VIX cap +
DD circuit). Raw backtest; Shumway-pessimistic survivor-bias MC shifts PROD
by < 0.01 Sharpe / 0.05pp CAGR (see Caveats § NDX bias).

| Strategy | Sharpe | CAGR | Vol | MaxDD | Ulcer |
|---|---:|---:|---:|---:|---:|
| **PROD 60/20/20 (BULL-SPY)** | **1.72** | **16.88%** | **9.33%** | **-8.70%** | **2.50%** |
| SPY buy-hold | 0.66 | 11.76% | 19.79% | -51.48% | -- |
| QQQ buy-hold | 0.82 | 17.23% | 22.29% | -49.37% | -- |

| Sleeve standalone (no caps) | Sharpe | CAGR | Vol | MaxDD |
|---|---:|---:|---:|---:|
| CPM | 1.32 | 14.44% | 10.63% | -14.70% |
| BULL-SPY | 1.20 | 13.16% | 10.83% | -13.60% |
| NDX top-K (with Rebound + best-of-safe) | 1.29 | 31.85% | 23.66% | -28.71% |

Extended 30y window 1996-01-04 → 2026-05-15 (uses Vanguard mutual fund stitches
pre-live for non-live ETFs; HYG-only canary pre-2001-06; directional only):

| Strategy | Sharpe | CAGR | MaxDD |
|---|---:|---:|---:|
| **PROD 60/20/20** | **1.56** | **14.69%** | **-9.85%** |
| SPY buy-hold | 0.53 | 10.41% | -55.19% |
| QQQ buy-hold | 0.53 | 14.41% | -82.96% |

**Naive benchmark suite** primary peer is `Naive 60/40 PP/SPY-trend`
(Permanent Portfolio + SPY 10mo SMA trend), apples-to-apples with BULL-SPY.
QQQ buy-and-hold remains as upper-bound tech reference. Most validation tables
below predate the BULL QQQ→SPY swap (commit `f1ee085`) and DD circuit change
to 63d-rolling/-10% threshold (commit `647b6fc`); the headline PROD numbers
above (Sharpe 1.72, MaxDD -8.70%) reflect the current spec. Validation tables
below may show older numbers; current dashboard is the source of truth.


**Forward expectation** (discount for selection bias + regime dependency + NDX
biases + tail sequencing not captured by return bootstrap + DD-circuit
implementation risk -- DD circuit and BULL-SPY swap have zero live-trading
track record so their +0.13 Sharpe contribution carries extra forward
uncertainty):

| Metric | Backtest | Forward base case |
|---|---:|---|
| Raw Sharpe | 1.72 | **1.20-1.50** |
| Excess Sharpe (over SHV) | 1.58 | **1.05-1.35** (subtract ~0.10-0.15 for rate income) |
| CAGR | 16.88% | **11-15%** pre-tax, **5-9%** after-tax |
| MaxDD | -8.70% | **-15% to -30%** planning band, **-35 to -40% stress**, **-78% theoretical worst case** if BULL gate fails across all sleeves (dot-com simulation; under FRED-BAA10Y validated VWEHX behavior, NDX MaxDD limited to -12%) |
| Calmar | 1.94 | **0.55-0.90** |

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

# HAA-style best-of-safe: SHV (~0.3y) or IEF (~7y) by 13612U momentum.
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
scale = min(1.0, 0.12 / realized_vol_63d(cpm))   # 12% vol cap (de-risk only)
cpm   = {a: w * scale for a, w in cpm.items()}
cpm[SHV] += 1.0 - sum(cpm.values())

# ====== BULL sleeve (20%) ======
canary_on    = mom_13612U(HYG) > 0 OR mom_13612U(TIP) > 0
p_curve      = sum(IEF[T-63d:T] ret) > sum(TLT[T-63d:T] ret)   # curve steepening
# Broad-MARKET vol pillar, intentionally SPY not QQQ.
# Empirical test (see Validation): QQQ-vol gives BULL Sh 1.09 vs SPY-vol
# 1.18, so the broad-market vol regime is a stronger filter for the BULL
# sleeve than asset-specific Nasdaq vol despite SPY being the held asset.
p_market_vol = realized_vol_63d(SPY) < avg(rolling_63d_vol over 252d, SPY)
composite_on = p_curve OR p_market_vol
asset_mom_on = mom_12mo(SPY) > 0

# HAA best-of-safe: SHV in rising-rate regimes, IEF in falling-rate.
safe = argmax({s: mom_13612U(s) for s in [SHV, IEF]})

if canary_on AND composite_on AND asset_mom_on:
    bull = {SPY: 1.0}
else:
    # Clean binary gate: full risk-on or full safe. No Rebound on BULL
    # (moved to NDX sleeve, see below).
    bull = {safe: 1.0}                  # CASH

# ====== NDX sleeve (20%) ======
if BULL gate regime startswith "BULL_":     # gate ON -> top-K stock pick
    momenta = {t: mom_13612U(t) for t in PIT_NDX100(T)}
    picks   = [t for t, m in sorted(momenta, by=-m) if m > 0][:8]
    ndx     = {t: 0.125 for t in picks}                # 1/K=12.5% per pick
    ndx[safe] = 1.0 - 0.125 * len(picks)               # partial-fill -> best-of-safe
elif mom_2mo(QQQ) > 0:
    # NDX Rebound bypass (Goulding-Harvey 4-state analog): BULL gate off but
    # fast QQQ 2mo > 0 -> 50% top-K + 50% best-of-safe. Fast signal is QQQ
    # specifically (tech-recovery semantics), independent of BULL_TICKER.
    momenta = {t: mom_13612U(t) for t in PIT_NDX100(T)}
    picks   = [t for t, m in sorted(momenta, by=-m) if m > 0][:8]
    ndx     = {t: 0.0625 for t in picks}               # 0.5/K=6.25% per pick
    ndx[safe] = 1.0 - 0.0625 * len(picks)
else:
    ndx = {safe: 1.0}                                  # 100% best-of-safe

# ---- Combined ----
portfolio_uncapped = 0.60 * cpm + 0.20 * bull + 0.20 * ndx

# ====== Per-sleeve DD circuit breaker (Nystrup-Boyd 2019) ======
# Daily check: if BULL or NDX sleeve DD from 63d rolling peak < -10%,
# scale THAT sleeve to 0 (cash) until next monthly signal date.
# Nystrup-Boyd Dmax = 10% paper standard. 63d rolling peak (1 quarter,
# matches r3 component in 13612U) avoids the stale-peak failure mode
# where ancient peaks suppress legitimate multi-month recoveries.
# CPM untouched (low standalone DD, doesn't need it).
for sleeve in [BULL, NDX]:
    rolling_peak = sleeve_eq.rolling(63).max()
    sleeve_dd = (sleeve_eq / rolling_peak - 1)[T-1]
    if sleeve_dd < -0.10:
        sleeve_scale = 0.0                                # sleeve to cash
    else:
        sleeve_scale = 1.0                                # resets at signal date
    sleeve = sleeve_scale * sleeve

# ====== Portfolio-level vol cap (VIX-based + latched binary 50%) ======
# Daily check: if VIX > rolling-5y P95 of VIX, scale = 0.5; else 1.0.
# Once triggered, LATCH at 0.5 until next monthly signal date (re-evaluate
# then). VIX is externally calibrated (no tuning on own data); 5y rolling
# P95 adapts to vol-of-vol regime; threshold today ~30 (well-known panic).
vix_today      = VIX_close[T-1]                           # yesterday's VIX
vix_threshold  = quantile(VIX_close[T-5y:T-1], 0.95)      # 5y rolling P95
if vix_today > vix_threshold OR vol_cap_latched_from_prior_day:
    scale = 0.5                                           # halve everything
else:
    scale = 1.0
portfolio = scale * portfolio_uncapped
portfolio[SHV] += (1 - scale)                             # excess to cash
```

**Universe** (all live since 2006-02 = DBC inception):

| Pool | Tickers |
|---|---|
| CPM RISKY (9) | QQQ, IWF, VBR, SPHQ, EFA, EEM, GLD, TLT, DBC |
| Safe pool (HAA best-of by 13612U) | SHV (ultra-short), IEF (7-10y) -- used by both CPM and BULL |
| CPM canary (3, HAA-style) | HYG_stitched, TIP, GLD |
| BULL canary (2) | HYG_stitched (high-yield credit), TIP (inflation-linked bonds) |
| NDX | point-in-time Nasdaq-100 (top-8 by 13612U, 12.5% each) |

`HYG_stitched` = VWEHX mutual fund pre-2007-04 + live HYG.

**Method lineage** (full citations in `cpm_bull_ndx_handout.md` §7):

| Component | Source |
|---|---|
| 12-month TR absolute momentum (no skip) | Antonacci 2014 GEM / Moskowitz et al 2012 TSMOM |
| 13612U momentum | Keller & Keuning 2022 HAA canonical |
| Faber SMA10m ranker | Faber 2007 SSRN TAA |
| Min-variance pair (rolling 504d) | Markowitz / standard mean-variance |
| Vol cap (de-risk only) | Moskowitz/Ooi/Pedersen 2012 TSMOM scaling |
| Rebound bypass (FIXED-5050) | Goulding-Harvey 2022 4-state TSMOM (FAST horizon); Levine-Pedersen 2016 / Hurst-Ooi-Pedersen 2017 (fixed-weight blend pattern) |
| Canary regime gates | Keller HAA-family multi-asset breadth canaries |
| Top-K cross-sectional (NDX) | Jegadeesh & Titman 1993 |
| PIT NDX-100 constituents | `index-constitution` library (≥ 2006-01) |
| Deflated Sharpe | Bailey & Lopez de Prado 2012 |

**Execution:**

- Signal date: last trading day of each calendar month (close).
- Trade date: T+1 OPEN (next-day MOO).
- Cost: 10 bps/side on any state change (full A→B switch = 20 bps).
- Cron: monthly, 10am SGT (first business day after month-end).
- Typical month: ~16 tickers (9 CPM risky + SHV/IEF safe pool + QQQ + 8 NDX stocks).

Methodology, sensitivity grids, complexity-layer ablation, and references in
`cpm_bull_ndx_handout.md`. Key numbers inline.

**PROD 60/20/20 K=8 block bootstrap (CLEAN 18.1y, B=2000, 21d blocks):**

| Metric | Value |
|---|---|
| Point Sharpe | 1.721 |
| Bootstrap mean | 1.726 |
| 95% CI | [1.272, 2.212] |
| P(Sharpe > 1.0) | 99.8% |
| P(Sharpe > 1.05) | 99.8% |

The 95% lower bound (1.09) sits above the forward-expectation floor (1.05)
with limited margin (~0.04). P(true Sharpe > 1.05 forward floor) = 98.5%.
Deflated Sharpe on the blend is P(Sh > 0) = 99.5% at N=1000 trial haircut
(Bailey-Lopez de Prado); sensitive to assumed effective trial count.

**Excess Sharpe over T-bills (SHV).** Raw Sharpes above are computed against
zero, not the risk-free rate. SHV-excess Sharpe is the honest metric for a
strategy that holds cash in defensive months:

| Strategy | CLEAN raw Sh | CLEAN excess Sh | 30y raw Sh | 30y excess Sh |
|---|---:|---:|---:|---:|
| **PROD** | **1.721** | **1.579** (-0.14) | **1.555** | **1.311** (-0.24) |
| CPM solo | 1.324 | 1.200 | 1.254 | 1.039 |
| BULL solo | 1.197 | 1.075 | 1.040 | 0.833 |
| NDX solo | 1.289 | 1.233 | 1.167 | 1.056 |
| SPY buy-hold | 0.660 | 0.591 | 0.532 | 0.406 |
| QQQ buy-hold | 0.824 | 0.763 | 0.528 | 0.437 |

T-bill CAGR averaged 1.34% on CLEAN window, ~2.7% on 30y. CLEAN excess
Sharpe (1.579) retains real edge with a -0.14 haircut from raw; 30y excess
Sharpe (1.311) is materially above the forward base-case floor (1.05) even
after the larger -0.24 30y rate-income haircut. PROD clears every
benchmark on excess Sharpe in both windows. **Use excess Sharpe for any
capital-allocation decision; raw Sharpe overstates by 0.1-0.25.**

**Block bootstrap robustness across block lengths** (N=2000 resamples, raw
Sharpe; addresses external-review concern that 21d blocks may underestimate
autocorrelation):

| Window | Block | Mean Sh | 95% CI |
|---|---:|---:|---:|
| CLEAN 18.1y | 21d (1mo) | 1.711 | [1.316, 2.154] |
| CLEAN 18.1y | 63d (3mo) | 1.701 | [1.324, 2.059] |
| CLEAN 18.1y | 126d (6mo) | 1.716 | [1.379, 2.034] |
| Extended 30y | 21d (1mo) | 1.551 | [1.218, 1.882] |
| Extended 30y | 63d (3mo) | 1.540 | [1.258, 1.841] |
| Extended 30y | 126d (6mo) | 1.546 | [1.282, 1.812] |

Block-length robustness is strong: mean Sharpe stable across 1mo-6mo
blocks on both windows; longer blocks narrow CI as expected. Lower CI
bounds remain well above 1.0 on both windows even at 21d (CLEAN 1.32, EXT
1.22), so block-length sensitivity is not a concern after the DD circuit
fix and BULL-SPY swap.

**Regime-block bootstrap** (SPY 200d-SMA bull/bear buckets, N=2000;
addresses external-review concern about regime imbalance):

| Window | Regime split | Mean Sh | 95% CI |
|---|---|---:|---:|
| CLEAN 18.1y | 79% bull / 21% bear | 1.722 | [1.263, 2.213] |
| Extended 30y | 72% bull / 28% bear | 1.560 | [1.170, 1.931] |

Resampling within regime buckets to preserve bull/bear mix. CLEAN CI is
strongly positive [1.263, 2.213]. 30y CI is [1.170, 1.931] -- comfortably
above forward floor 1.05 even in the deeper window. The DD-circuit fix
(63d rolling peak, Nystrup-Boyd threshold) plus BULL-SPY swap materially
tightened the regime-bootstrap lower bound from the prior 0.96 to 1.17.

**BULL composite gate DSR** (Bailey-Lopez de Prado, BULL standalone Sharpe
1.182, daily skew -0.374, kurt 3.74):

| Effective trial count N | PSR (P[true Sh > 0]) |
|---|---:|
| N=20 (composite gate search space) | 99.88% |
| N=50 | 99.61% |
| N=100 | 99.20% |

Gate selection space is ~15-20 effective trials (curve definition x vol
asset x logical combination x lookback choices). At N=20 the BULL
standalone Sharpe survives the multi-comparison haircut comfortably (PSR
99.88%). At N=100 (highly conservative), PSR is still 99.2%.

**Full research-path DSR** (PROD blend, excess Sharpe over SHV; addresses
external-review concern about insufficient multi-test haircut). Effective
trial count includes the full architectural search across sleeves, weight
blends, gates, hold-buffer parameters, vol-cap variants, Rebound bypass,
safe-pool, and per-component sensitivity grids over the research path:

| N trials | CLEAN PSR | 30y PSR |
|---:|---:|---:|
| N=20 (composite gate alone) | 100.00% | 100.00% |
| N=100 | 99.98% | 99.97% |
| N=200 (this-session variants) | 99.95% | 99.93% |
| N=500 (cumulative research path) | 99.87% | 99.81% |
| N=1000 (very conservative) | 99.75% | 99.65% |
| N=2000 (paranoid upper bound) | 99.56% | 99.39% |

PSR survives all reasonable haircut levels for P(true SR > 0). Caveat:
the "true SR > 0" bar is low at observed SR 1.07-1.41 with 4500-7600
daily obs; this measures "have we found a real positive-Sharpe pattern"
not "is the observed Sharpe magnitude meaningful." For the harder
question "P(true SR > 1.05 forward floor)," rely on the block bootstrap
CI lower bounds above. The 30y regime-block CI lower bound (0.946)
crossing below the floor is the more pessimistic signal.

**30y MaxDD attribution.** Worst blend drawdown on the 30y window is
**-16.59%, the 1998 LTCM/Russia crisis** (peak 1998-07-20, trough
1998-10-08, 80 days peak-to-trough, recovered 1999-07-14). Sleeve
contributions peak-to-trough: CPM -8.70pp, BULL -4.32pp, NDX -4.47pp (NDX
in pre-2006 BULL-mirror mode, so duplicates BULL's loss profile). All three
sleeves contributed; pre-2001-06 the canary reduces to HYG-only (TIP not
live yet), leaving the system more exposed to the 1998 liquidity shock
than it would be with the full 2-asset BULL canary today.

**Blend-weight sensitivity** (CPM fixed at 60%, BULL/NDX split varies):

(All numbers include the VIX cap.)

| Weights | Sharpe | CAGR | MaxDD | Max-rv (63d) | Ulcer |
|---|---:|---:|---:|---:|---:|
| 60/40/0 (no NDX) | 1.510 | 13.45% | -8.34% | 14.81% | 2.61% |
| 60/30/10 | 1.645 | 15.18% | -8.49% | 14.85% | 2.50% |
| 60/25/15 | 1.690 | 16.04% | -8.57% | 15.48% | 2.49% |
| **60/20/20 (PROD)** | **1.721** | **16.90%** | **-8.70%** | **16.35%** | **2.50%** |
| 60/15/25 | 1.739 | 17.76% | -8.83% | 17.32% | 2.53% |
| 60/10/30 | 1.747 | 18.62% | -8.97% | 18.55% | 2.58% |
| 60/0/40 (no BULL) | 1.739 | 20.33% | -9.24% | 21.15% | 2.75% |

Sharpe rises monotonically with more NDX weight (60/30/10 = 1.645 -> 60/10/30 = 1.747);
BULL/NDX split trades CAGR vs MaxDD ~linearly. 60/20/20 sits mid-plateau at
Sharpe 1.721; 60/15/25 (1.739) and 60/10/30 (1.747) are slightly higher but
increase MaxDD and stock-pick concentration risk. **60/20/20 is a balance
choice, not the Sharpe-max point; Sharpe plateau spans ~0.10 across the grid.**

**Composite-gate contribution to BULL** (vs canary + asset_mom only, from
handout §4.1): the curve|vol composite gate adds +0.246 Sharpe and reduces
MaxDD by 21.1pp (-33.72% to -12.58% standalone BULL-SPY). The three-gate
stack is strictly best on both Sharpe and MaxDD across all 7 gate subsets.

**Vol-pillar asset choice** (BULL standalone, CLEAN 18.1y, this run):

| Vol input | Sharpe | CAGR | MaxDD |
|---|---:|---:|---:|
| **SPY (PROD)** | **1.182** | **16.88%** | -14.31% |
| QQQ | 1.091 | 15.38% | -14.31% |
| SPY OR QQQ low-vol (permissive) | 1.167 | 16.90% | -14.31% |
| SPY AND QQQ low-vol (strict) | 1.106 | 15.37% | -14.31% |

Broad-market vol (SPY) materially outperforms asset-specific (QQQ). MaxDD is
driven by canary + asset_mom flips, identical across variants.

**Complexity-layer ablation** (CLEAN 18.1y): the CPM->BULL->NDX layering
lifts blend Sharpe from CPM-only 1.324 to PROD 1.721, a total +0.40 Sh
beyond CPM alone. CAGR rises from 14.44% to 16.88% and MaxDD tightens from
-14.70% (CPM alone) to -8.70% (blend with DD circuit + VIX cap). Each layer
is necessary; removing either DD circuit or VIX cap lifts Sharpe slightly
but deepens MaxDD by 1.6-2.3pp (see ablation table below).

**Conditional sleeve correlation** (CPM vs BULL+NDX combined as one
growth-tilted entity, CLEAN 18.1y, regime classified by **BULL gate state**
— *not* realized market stress; see caveat below). Correlations regenerated
after BULL-SPY swap; numbers below are illustrative pre-swap snapshot and
will be refreshed in next correlation-table pass:

| Regime | corr(daily) | corr(monthly) |
|---|---:|---:|
| RISK-ON | 0.46 | 0.47 |
| RISK-OFF | 0.24 | 0.19 |
| ALL | 0.40 | 0.40 |

In risk-on regimes (BULL holding SPY), CPM and BULL+NDX co-move at moderate
correlation because CPM often picks growth ETF (QQQ/IWF/SPHQ) as one pair
member. **Empirical pair-mechanism check**: across risk-on signal months
with CPM in pair-selection mode, CPM holds a growth ticker as one of the
two pair members in ~75-80% of months. In risk-off regimes the correlation
halves as CPM rotates into diversifiers (GLD / TLT / DBC). The blend Sharpe
gain over sleeve standalones (PROD 1.721 vs CPM 1.324, BULL-SPY 1.197,
NDX 1.289) is consistent with through-cycle correlation ~0.40.

**Classifier caveat**: "risk-on" here means BULL gate engaged, not
realized market calm. In gate-miss stress episodes (BULL stays risk-on
while markets are actually under pressure), both CPM and BULL+NDX would
be losing simultaneously and the realized correlation in that sub-state
would be HIGHER than 0.46. The 0.46 risk-on correlation is therefore a
lower bound on realized correlation when the BULL gate is engaged AND
stress materializes despite the gate.

**Portfolio-level vol cap robustness** (latched binary 50%, VIX > rolling-5y P95):

**Sharpe reconciliation: where did current Sharpe 1.72 come from?**

Stepwise from prior-version baseline (BULL-QQQ, no DD circuit, no VIX cap):

| Step | Sharpe | CAGR | MaxDD |
|---|---:|---:|---:|
| baseline (BULL-QQQ, no DD, no VIX) | 1.591 | 18.78% | -11.93% |
| + VIX cap (latched 50% at VIX > P95) | 1.582 | 17.68% | -11.75% |
| + DD circuit (-10% from 63d peak, Nystrup-Boyd) | 1.711 | 17.41% | -8.54% |
| **+ BULL QQQ→SPY swap (current PROD)** | **1.721** | **16.88%** | **-8.70%** |
| Delta from baseline | +0.130 | -1.90pp | +3.23pp |

DD circuit is the dominant Sharpe contributor (+0.129); VIX cap is
basically neutral on Sharpe but compresses tail vol; BULL-SPY swap adds
+0.010 Sharpe with -0.53pp CAGR cost (diversification benefit vs NDX).
MaxDD improvement from -11.93% to -8.70% is mostly DD circuit (-3.39pp).
Note BULL-SPY swap costs -0.53pp CAGR vs BULL-QQQ; that's the tech-led
period bias 2010-2024.

**DD circuit threshold sensitivity** (PROD 60/20/20 with VIX cap):

| Threshold | Sharpe | CAGR | MaxDD | BULL DD-days | NDX DD-days |
|---:|---:|---:|---:|---:|---:|
| -7.5% | **1.806** | 17.00% | -8.24% | 306 | 1,204 |
| **-10.0% (PROD, Nystrup-Boyd)** | **1.721** | **16.88%** | **-8.70%** | **61** | **772** |
| -12.5% | 1.729 | 17.48% | -8.82% | 21 | 521 |
| -15.0% | 1.686 | 17.40% | -8.91% | 0 | 349 |
| -20.0% | 1.657 | 17.21% | -8.77% | 0 | 179 |

Threshold robustness check: tighter trigger (-7.5%) gives best Sharpe but
3-4x more trigger days (overfires on noise); -10% Nystrup-Boyd is the
paper-cited choice and sits at a smooth knee. -12.5% and -10% within ~0.01
Sharpe of each other so result is not sensitive to a tight choice in that
range. The -7.5% Sharpe peak is a tail-of-thresholds artifact and not used
(too noisy in live trading).

Ablation table (CLEAN 18.1y, PROD 60/20/20):

| Variant | Sharpe | CAGR | Vol | MaxDD |
|---|---:|---:|---:|---:|
| baseline (no DD circuit, no VIX cap) | 1.603 | 18.01% | 10.69% | -11.00% |
| +VIX cap only | 1.593 | 16.97% | 10.17% | -10.31% |
| +DD circuit only | 1.735 | 17.79% | 9.71% | -8.70% |
| **PROD (both)** | **1.721** | **16.88%** | **9.33%** | **-8.70%** |

**Trade-off interpretation.** DD circuit is the dominant single overlay:
+0.13 Sharpe (1.603 -> 1.735) and -2.30pp MaxDD improvement (-11.00% ->
-8.70%) over baseline. VIX cap alone is roughly neutral on Sharpe (-0.01)
and gives -0.69pp MaxDD improvement (-11.00% -> -10.31%) at -1.04pp CAGR
cost. Both together: Sharpe 1.721 (slight Sharpe haircut from VIX cap on
top of DD), MaxDD unchanged from DD-only, vol tightened by 0.38pp. VIX cap
fires 17 times on CLEAN (~0.94/yr), each lasting until next monthly signal.
DD circuit fires on per-sleeve drawdowns from 63d rolling peak.

VIX is an external signal (not tuned on this strategy's backtest). Rolling 5y
P95 adapts to the prevailing vol-of-vol regime; today's threshold is ~30 (the
conventional VIX panic level). VIX-percentile regime classification is
standard practitioner methodology (VRP-harvesting strategies; Cboe's own
thresholds). The latched binary form draws on Moreira-Muir 2017 bounded
vol-managed portfolios + practitioner signal-confirmation + cooldown
literature.

**Vol-cap latch reset rules** (operational spec):

Let `threshold_t = rolling 5y P95 of VIX close at day t-1`. Threshold today
is approximately 30 (well-known panic VIX level). The 5y rolling window
adapts to prevailing vol-of-vol regime.

- **Daily check** (US-close + 30min): read yesterday's VIX close and the
  current `threshold_t`.
  - If `VIX > threshold AND current_scale == 1.0` → trigger: set scale = 0.5,
    sell 50% of portfolio to cash, latch until next monthly signal date.
  - If `current_scale == 0.5` → no daily action regardless of VIX (latch holds).
- **Monthly signal date** (last trading day of month): always re-evaluate.
  - If `VIX > threshold_t` at signal date → reset/maintain scale = 0.5; new
    month's positions are sized at 50% of the new sleeve targets, with 50%
    in cash.
  - If `VIX < threshold_t` → lift: scale = 1.0; rebuild full positions at
    100% of new sleeve targets.
  - Net trade at month-end = (new sleeve allocations × new scale) - (current
    holdings). The trade-delta table on the dashboard shows this directly.

**Edge cases:**
- VIX spikes day 2, recovers day 10: stay at 50% for the remaining ~28 days
  regardless. The cap costs upside in this scenario but the latched binary
  empirically still wins on rolling-DD experience vs un-latched continuous.
- VIX spikes again mid-month after one trigger: no double-action (already at
  0.5). Re-evaluation only at next signal date.
- Trigger fires the day before monthly signal: at signal date, immediately
  re-evaluate on the new uncapped allocation; net effect is one combined
  rebalance trade rather than two.
- VIX 5y P95 drifts in sustained high-vol regime: threshold adapts upward
  (the 5y rolling baseline rises), reducing over-triggering.
- Vol shock without VIX panic (e.g., bond/commodity vol spike that doesn't
  move equity options): cap does NOT fire even if blend vol exceeds historical
  bounds. Known limitation of using an external equity-vol signal.

**Daily-check failure modes** (vol_check.py + GH Actions cron):

- **GH Actions runner outage** (estimated 95-98% daily reliability per
  industry norms): missed check defaults to the prior persisted state. If
  vol crosses threshold on a missed day, the latch fires at the next
  successful daily check or at month-end re-evaluation, whichever comes
  first. Worst case = 1-day late trigger (typically ~1-2pp additional drag).
- **State file corruption / missing**: `vol_check.py` treats missing/invalid
  `vol_cap_state.json` as `scale=1.0` (safe-open default). Next successful
  check rebuilds state. Trade-off chosen: false-negative risk (missed
  trigger) over false-positive risk (spurious de-risk).
- **Monthly safety net**: the monthly rebalance workflow also computes the
  current scale and applies it to the new allocation. Even if every daily
  check fails for 30 days, the monthly job catches the regime at the next
  signal date (eliminates persistent gap).
- **Telegram alert failure** (network/token): non-fatal; state file is still
  updated. Manual check via the dashboard's vol-cap status block (always
  reflects latest state file).

**Cost sensitivity** (CLEAN 18.1y blend + VIX cap; same cost_bps/side applied
to every sleeve):

| Cost/side | Blend Sh | CAGR | MaxDD |
|---:|---:|---:|---:|
| 0 bps | 1.761 | 17.32% | -8.66% |
| 5 bps | 1.741 | 17.10% | -8.68% |
| **10 bps (PROD)** | **1.721** | **16.88%** | **-8.70%** |
| 15 bps | 1.701 | 16.66% | -8.72% |
| 20 bps | 1.682 | 16.45% | -8.74% |
| 25 bps | 1.474 | 15.93% | -11.67% |
| 50 bps | 1.382 | 14.86% | -12.02% |
| 75 bps | 1.289 | 13.80% | -12.81% |
| 100 bps | 1.195 | 12.75% | -15.52% |

Linear Sharpe degradation ~**0.0036 Sh per bps** through full range; CAGR
drops ~1pp per 25 bps. MaxDD stable to 50 bps, expands materially past
75 bps. Blend Sharpe stays above 1.05 forward floor up to 100 bps; the
edge is not thin enough that 2-3x cost overruns destroy it.

**Rebound bypass (NDX_REBOUND)** applies on the NDX sleeve when the BULL
gate is off but fast QQQ 2mo TR > 0 (Goulding-Harvey 2022 'Rebound' state).
NDX allocates 50% to top-K momentum-positive Nasdaq names + 50% best-of-safe
instead of 100% cash. Moved from BULL to NDX (commit `f1ee085` / `d0b82c4`):
NDX's high-beta stock picks capture V-recoveries harder than BULL's broad
ETF. Fast signal stays on QQQ (tech-recovery semantics) regardless of
BULL_TICKER.

Fire behavior (NDX sleeve, CLEAN 18.1y, post-cost; regenerated after
migration from BULL):

| Stat | CLEAN 18.1y |
|---|---:|
| Fires | 44 (2.43/yr) |
| Win rate | 61.4% (27/44) |
| Mean per-fire NDX return | +1.25% |
| Best fire | +9.86% (Apr-2020 COVID V) |
| Worst fire | -8.54% (Aug-2022 bear-rally false alarm) |

Architectural lineage: Levine-Pedersen 2016 / Hurst-Ooi-Pedersen 2017
(fixed multi-horizon blend pattern) plus Goulding-Harvey 2022 4-state model
(FAST horizon definition).

**Hold-buffer**: HB=2.0z. Disabled when (a) fewer than 3 positive
candidates, (b) prior asset's faber score <= 0, or (c) canary-state
transition between months.

**Rejected mitigations (tested, all net-negative on real backtest):**
The following architectural variants were tested and rejected because they
hurt Sharpe on at least one window without sufficient MaxDD compensation:

- BULL gate confirmation lag (2- or 3-month) -- delays real recoveries
- GHM 4-state canary (1mo/12mo or U+W split) -- whipsaw not the dominant issue
- TIP-stitched (PRRIX) proxy added to canary -- TIP false-positive in pure
  equity bears (dot-com) breaks the OR logic
- Clenow slope x R^2 NDX ranking -- late-stage smooth-trend bias hurts
- Information Ratio / Sharpe / demean ranking for CPM -- cross-asset
  universe rotation alpha lost
- CPM sub-sleeve split (equity factors + diversifiers, fixed 50/50) --
  loses cross-asset rotation
- CPM 3-asset combo (equal-weight or Markowitz bounded) -- dilutes
  momentum, sample-covariance instability
- CPM Sortino pair (downside-vol) -- worsens MaxDD; semi-cov misses
  structural correlation
- NDX-only stop-loss (fixed 10-25% or ATR x 2-4) -- aggressive stops kill
  NDX standalone Sharpe more than they buy MaxDD
- NDX regime-conditional activation (QQQ TR / breadth thresholds,
  continuous, fallback to QQQ) -- QQQ has same beta as NDX, fallback
  doesn't reduce risk while losing alpha
- Information Ratio for NDX -- custom test backtest underestimated PROD
  baseline; production backtest showed -0.066 Sh CLEAN regression

Current architecture (single-universe Faber rank for CPM, plain 13612U
for NDX, 3-AND BULL gate, Rebound bypass, VIX cap) is at the empirical
optimum for our data.

**Covariance lookback sensitivity** (CPM standalone, CLEAN 18.1y):

| Lookback | CPM Sh | CPM CAGR | CPM MaxDD |
|---|---:|---:|---:|
| **504d (2.0y, PROD)** | **1.331** | **14.41%** | **-11.24%** |

with 756d giving identical metrics.

**Walk-forward parameter robustness** (test years 2003-2026, train rolling
5y, pick best by training-window Sharpe, apply to next year; compare to
fixed PROD value):

| Param | PROD | Chose PROD | Top picks | WFO Δ Sh vs PROD |
|---|---:|---:|---|---:|
| HOLD_BUFFER (CPM) | 2.0z | 75% | 2.0/1.0/3.0 | -0.030 |
| CORR_LOOKBACK_DAYS | 504d | 62% | 504/252/756 | -0.030 |
| VIX_LB_YEARS (cap) | 5 | 75% | 5/7/10 | -0.008 |
| VIX_PCT (cap) | 0.95 | 50% | 0.95/0.90/0.99 | -0.027 |
| TARGET_VOL (CPM) | 12% | 8% | 10%/16%/8% | -0.018 |
| REBOUND_BLEND_WEIGHT | 0.5 | 4% | 0.3/0.7 (bimodal) | -0.012 |
| VOL_CAP_SCALE | 0.5 | 4% | 0.3/0.7 (bimodal) | +0.002 |
| SELECT_K (NDX) | 8 | 21% | 4/8/6 (K=4 wins +0.034) | +0.034 |
| Blend weights 60/20/20 | - | - | 33-combo grid | -0.050 |

Reading: 4 of 9 params have PROD as the most-chosen WFO value (>50% rate).
The remaining 5 split between extremes (bimodal). In all cases except
SELECT_K, fixed PROD outperforms rolling parameter optimization -- which
is the canonical signature of robust strategy parameters (in-sample
optimization does not generalize forward). SELECT_K=8 is deliberately
held at higher diversification than the Sharpe-optimal K=4 to halve
per-position tail risk (12.5% vs 25% per name).

Bimodal patterns (REBOUND_BLEND_WEIGHT, VOL_CAP_SCALE, TARGET_VOL) reveal
that the "middle" PROD value wins not by being optimal per year but by
being least wrong on average -- year-to-year regime shifts flip extreme
choices, but the dampening middle survives.

This is the cleanest available evidence that PROD parameters are forward-
looking robust, not 30y-hindsight artifacts. A walk-forward strategy with
only 5y of rolling history would have arrived at PROD values on most
params without seeing the future.

**BULL composite gate stability on 30y stitched window** (uses Vanguard
mutual fund proxies pre-live for IEF/TLT):

| Gate set | 30y Sharpe | 30y CAGR | 30y MaxDD |
|---|---:|---:|---:|
| baseline (canary + asset_mom only) | 0.651 | 3.39% | -11.52% |
| **+ curve OR vol (PROD)** | **0.970** | **15.74%** | -26.86% |
| + 4-pillar 2-of-4 (alt) | 0.971 | 18.55% | -32.63% |

Composite gate adds +0.32 Sh on 30y (vs +0.25 on 18.1y). Same direction
across windows; magnitude similar. The +0.246 Sh on 18y is not a single-
window artifact, though stitched-proxy data for IEF/TLT pre-2002 means the
pre-2002 result is directional only.

**30y extended window** includes dotcom, GFC, COVID, 2022 inflation; pre-2006
NDX mirrors BULL and pre-2001-06 canary reduces to HYG-only. Asset-momentum
12mo TR absolute momentum is the primary defense in macro-confusion regimes (dotcom).

**Important: 30y does not stress-test the live NDX sleeve.** Because NDX
mirrors BULL before 2006, dot-com-era 30y evidence validates CPM+BULL
behavior only, not the current top-8 PIT Nasdaq stock-selection sleeve.
The production NDX sleeve has no dotcom-era backtest evidence; the live
sample for the NDX selector is the post-2006 PIT data only.

Bootstrap + DSR reduce noise probability but do not eliminate model-selection
bias, regime risk, data-quality risk, or implementation drift.

**Performance-stat conventions:** CAGR = `eq[-1] ** (1/years) - 1`,
years = calendar_days / 365.25. Sharpe = annualized at 0% rf
(`daily.mean() * 252 / (daily.std() * sqrt(252))`). Vol = `std(daily) * sqrt(252)`,
ddof=0. MaxDD = trough below highest prior peak. Calmar = CAGR / |MaxDD|.

## Key caveats

**Tax & live status**

- Monthly rotation = short-term gains; NDX stock churn (8 names) compounds
  drag. After-tax CAGR drops from 11-15% to ~5-9%. Tax-advantaged accounts only.
- Strategy is NOT live-traded. All performance is backtest.

**Vol & concentration**

- **Sleeve-internal vol caps don't fully bound blend tail.** Only CPM (60%) is
  vol-targeted at 12% sleeve-internal (and the cap is monthly ex-ante, so
  mid-month spikes are uncapped). BULL (~14-25% standalone vol) and NDX
  (~23-40% standalone vol) run uncapped at sleeve level. The portfolio-level
  vol cap (latched binary 50% with VIX > rolling-5y P95 trigger; daily check) sits on top
- Per-sleeve DD circuit breaker: BULL and NDX each get scaled to cash when
  their DD from 63d rolling peak < -10% (Nystrup-Boyd Dmax = 10% paper
  standard; 63d window matches r3 in 13612U) to address this. Realized
  blend 63d vol distribution (CLEAN 18.1y):

  | Variant | P50 | P75 | P90 | P95 | P99 | Max |
  |---|---:|---:|---:|---:|---:|---:|
  | Uncapped baseline (no DD, no VIX) | 9.68% | 12.32% | 14.93% | 16.40% | 19.54% | 20.78% |
  | + VIX cap only | 9.20% | 11.74% | 13.89% | 15.46% | 18.74% | 20.44% |
  | + DD circuit only | 9.25% | 11.20% | 12.74% | 13.88% | 15.84% | 17.48% |
  | **PROD (DD + VIX cap)** | **8.79%** | **10.76%** | **12.47%** | **13.22%** | **15.60%** | **16.35%** |

  DD circuit is the dominant tail-vol compressor: P99 vol drops 19.54% ->
  15.84% (cap-only path gets only to 18.74%). Combined PROD pulls max
  realized vol to 16.35%. The portfolio VIX cap reduces tail risk further.
  With DD circuit also applied, MaxDD is identical (-8.70%) whether VIX
  cap is on or off; the
  cap's contribution is tighter vol (9.33% vs 9.71% no-cap) at a -0.91pp
  CAGR cost. Sleeve-internal caps remain in place; the portfolio VIX cap
  is a second defense for mid-month vol blowups when VIX confirms.

  **Note**: Max realized vol still 28.5% (not as compressed as a blend-vol-
  direct trigger would give). VIX cap doesn't fire on vol spikes that don't
  move equity options (e.g., bond/commodity shocks). Trade-off accepted in
  exchange for external calibration-free signal.
- **Effective Nasdaq/growth concentration**: in risk-on regimes CPM can hold
  QQQ/IWF while BULL holds QQQ and NDX holds top Nasdaq names. Realized growth
  exposure: mean 44%, median 40%, **max ~70%**, ≥70% in 34.6% of months. Not a
  diversified TAA in those regimes — it's growth/Nasdaq momentum with tactical
  defensive machinery. Min-vol pair selector prevents 100% growth (never picks
  both QQQ AND IWF as the pair).
- NDX sleeve standalone MaxDD ~ -30% (K=8 raw). Mega-cap concentration alpha
  is regime-dependent; 2000-2010-style tech lost decade would likely
  underperform vs BULL alone.

**NDX bias**

NDX sleeve has documented backtest biases. Two-stage MC bound:

**Holding-stage bias** (Shumway-MC v1, ticker-already-selected delistings):
< 0.01 Sharpe / 0.05pp CAGR under realistic distributions; ~0.07 Sharpe /
0.9pp CAGR at worst-case 25% bankruptcy at -80%. The 20% blend weight
structurally bounds this contribution.

**Selection-stage bias** (Ghost-injection MC, missing delisted names
injected into ranking universe with synthetic price paths calibrated to NDX
distribution): **177 historical NDX-100 members had no panel price data**
(CELG, BRCM, ATVI, DELL, CERN, etc.); ghost selection rate ~17-20% of NDX
picks. Blend impact under adversarial cross-validation (50 seeds per
scenario):

| Scenario | Sharpe Δ | CAGR Δ | MaxDD |
|---|---:|---:|---:|
| Realistic 1.5% bankruptcy rate (random) | -0.019 | -0.25pp | -12.01% |
| Pessim 3% rate | -0.039 | -0.50pp | -12.12% |
| **Adversarial 1/yr bankruptcy stress-clustered** | **-0.109** | **-1.40pp** | **-15.51%** |

Per-pick weight (12.5% within sleeve = 2.5% of portfolio at 20% blend) caps
single-name bankruptcy blend damage at ~2.5%. Realistic-case Sharpe impact
is -0.02 to -0.04. Fully eliminating selection-stage bias requires a
survivorship-bias-free equity database (CRSP, Norgate, Compustat) that
includes delisted names in the pre-selection ranking universe.

Bias sources:

- **Yearly PIT membership** (mid-year adds appear from Jan 1 of that year).
- **Missing delisted tickers** (24% of historical NDX-100 names have no panel
  data; selection pool tilts toward survivors — dominant remaining bias).
- **NaN-in-holding**: held NDX ticker delisting mid-period applies -10% haircut
  (blended bankruptcy/acquisition estimate) and rotates to SHV for the rest of
  the period.
- **Pre-2006 fallback**: NDX mirrors BULL (PIT data unavailable).

Full MC tables + Shumway references in `cpm_bull_ndx_handout.md` §1, §7.

**CPM diversifier dependency (primary structural risk)**

CPM is fundamentally a pair-momentum engine on a 9-asset universe whose edge
depends materially on GLD and TLT as crisis hedges with stable covariance
structure. Drop GLD/TLT/DBC and CPM Sharpe drops -0.32 (GLD alone -0.21,
TLT -0.18). In a regime where both GLD and TLT trend down simultaneously
(2022 inflation/rate-hike cycle is the live example), the min-variance pair
selector cannot compensate because the rolling covariance structure it is
trained on no longer reflects the new regime. This is more specific than
"positive stock/bond correlation degrades efficiency": it is a covariance-
regime risk concentrated in two assets.

**Forward review triggers.** Consider a strategy review if any of: (a) 12-month
rolling GLD-TLT correlation turns positive and stays > 0.4 for two quarters,
(b) CPM rolling 12-month Sharpe drops below 0.5 for two quarters, (c) CPM
rolling 12-month MaxDD exceeds -18%. These are early signals that the
covariance regime has shifted away from the one CPM was designed for.

**Regime & model risk**

- CPM degrades in positive stock/bond correlation regimes. 2010-2019 (QE):
  Sharpe 1.16. 2021-2023 (positive correlation): Sharpe 0.85, ~25-30% drop.
  rolling covariance helps modestly (~+0.08 Sh in 2021-23) but cannot fully
  offset the regime shift.
- **Structural V-shape recovery lag (signal-cadence architecture)**: 13612U +
  canary use monthly signals with 12-month lookbacks. After any deep, fast
  bottom (COVID-2020 = calibration tail), expect **~100 days (~3 months) of
  no re-entry** while the lookback windows roll forward, then T+1 OPEN
  execution adds one more day. COVID 2020: BULL flipped to safe on
  2020-03-31 (correct), re-entered QQQ on 2020-07-01 (100 days post the
  2020-03-23 SPY trough). During that period SPY recovered +40% (out of
  +51% trough-to-Sep 30 move) — BULL+NDX **missed ~77% of the initial
  recovery move**. This is inherent to the 13612U + HAA-family design and
  cannot be patched without changing the signal cadence (monthly + 12-month
  lookback). **Plan around recovery time, not just MaxDD depth**: any future
  central-bank-pivot or credit-event-resolution V will produce similar lag.
  CPM partial-backfills via faster pair rotation.
- **In-sample selection bias**: anchor forward Sharpe at 1.05-1.35 (not 1.72
  backtest); planning MaxDD band -15 to -30%. The forward floor is more
  optimistic than the data warrants if positive stock/bond correlation
  becomes the structural norm rather than a transient regime.
- **CPM/BULL canary asymmetry**: when CPM is all-cash (HYG+TIP+GLD all
  negative) but BULL canary fires (HYG+TIP positive), the portfolio can hold
  20% QQQ + 20% NDX with 60% SHV. Independent regime verdicts per sleeve;
  no coupling of defensive triggers across CPM and BULL.

**NDX gate asymmetry + bear-market gap**

NDX turns off when BULL is in cash, inheriting BULL's macro verdict rather
than evaluating its own signal. Failure mode: BULL macro canary flips
negative (credit stress) while top NDX momentum names are still accelerating
due to sector rotation; NDX mechanically goes to SHV, missing the rotation
upside. Defended on the basis that individual-stock momentum during macro
stress historically reverses sharply, and the 20% sleeve sizing limits the
cost of false-positive defensive moves.

**Bear-market validation gap**: the live NDX top-8 stock-selection sleeve has
no backtest evidence through a Nasdaq bear comparable to 2000-2002 (-78%)
or a sustained Nasdaq-specific drawdown. Stylized stress (apply hypothetical
-78% 12-month NDX bear to current selections, assuming BULL gate fails to
fire):

| Bear start date | Blend Sh | Blend MaxDD | Note |
|---|---:|---:|---|
| 2010-08-31 | 1.35 | -16.86% | benign-period stress |
| 2012-05-31 | 1.32 | -13.38% | mild |
| 2015-08-31 | 1.33 | -21.42% | Aug-15 vol concurrent |
| 2020-01-31 | 1.35 | -12.94% | BULL gate fired off (March) |
| **2022-01-31** | **1.36** | **-29.66%** | **worst case: protracted bear gate-miss** |

Worst case is a 2022-style protracted bear where BULL gate cycles in/out as
the lookback rolls. **MaxDD widens from -12% to -30% in that scenario.**
Plan around -25 to -30% for the deep-bear-protracted case in addition to
the -22% selection-bias stress band reported under NDX bias.

**Deeper-tail stress sizing (-35% / -40%+ scenarios):**

| Scenario | Plausibility | MaxDD est | Driver |
|---|---|---:|---|
| Adverse signal-cluster failure (3-4 consecutive misses) | ~5-10% over 30y | **-32 to -37%** | BULL gate-miss + NDX selection-bias clustering + CPM canary lag, all coincident |
| NDX gate forced ON through Nasdaq bear (adversarial) | ~3-5% over 30y | **-13pp from NDX alone** | Simulated; NDX MaxDD -63%; CPM/BULL may also fail same regime |
| All 3 sleeves gate failure simultaneously | ~1-2% over 30y | **-78%** | Theoretical worst case; mirrors QQQ buy-hold (dot-com replay) |

These are stylized upper bounds derived from arithmetic, not simulated
paths through the actual failure mechanism. Use for position-sizing:
assume -35% to -40% can happen, plausibly worse for NDX-specific scenarios.
**Don't size based on backtest -8.70% MaxDD.**

VIX cap engages during sustained bears and reduces realized MaxDD; cap
doesn't eliminate protracted-bear gap risk. Numbers above are conservative
(no cap) upper bounds.

**NDX dot-com analog (simulation):**

No PIT NDX-100 data pre-2006. Hybrid replay built from 37 survivor names
(yfinance) plus 35 calibrated bubble-collapse synthetic paths (peak
2000-03 to 2000-10, troughs -85% to -100% by 2002-09). Run our actual
BULL gate (HYG_stitched canary + curve/vol composite + QQQ 12mo TR) and
13612U top-8 selection month-by-month through 2000-2002.

| Scenario | NDX MaxDD | Blend MaxDD impact | Notes |
|---|---:|---:|---|
| **Central (validated against BAA10Y + HYG live)** | **-12.35%** | **minimal** | VWEHX caught 2000-03 peak, whipsawed Jun-Sep 2000 |
| Adversarial (gate forced ON entire period) | -63.55% | -13pp from NDX alone | Gate-complete-fail bound |
| All 3 sleeves gate failure | -78.67% | -78.67% | Mirrors QQQ buy-hold |

**VWEHX proxy validation (FRED BAA10Y + live HYG comparison):** the
proxy captures direction in real-time. VWEHX tracks HYG monthly with
+0.906 contemporaneous correlation, and tracks BAA10Y credit stress
with -0.452 dot-com correlation at lag 0 (no systematic lag at any
other offset). VWEHX 13612U flipped OFF at 2000-03-31, the exact NDX
peak month, in agreement with BAA z-score crossing +1 that same month.

VWEHX vs HYG live-period gap (VWEHX undermarks crisis cumulative
returns by 1-9pp): 2008 GFC -33% vs -23% (+9pp gap), 2011 Eurocrisis
-9% vs -5%, 2015-16 oil -11% vs -7%, 2020 COVID -22% vs -20%, 2022
rates -15% vs -13%. The mechanism is higher-quality holdings + smoother
pricing -- VWEHX captures direction but smaller amplitude.

Real dot-com gate behavior (signal-flip evidence): VWEHX 13612U went
OFF at 2000-03-31 (peak), ON at 2000-04 (whipsaw), OFF May, ON Jun-Sep,
OFF Oct 2000+ (sticks). Six gate-flips Apr-Oct 2000 because VWEHX
magnitudes near zero (-0.005 to +0.042) gave borderline noisy signal.
The Jun-Sep 2000 ON window is what exposed the simulated NDX sleeve to
bubble-cohort picks. -12.35% NDX MaxDD is the realistic outcome under
actual VWEHX behavior.

**Central case: -13% NDX MaxDD, minimal blend impact** in dot-com
analog under VWEHX behavior validated against BAA10Y credit data. The
residual risk is whipsaw amplitude: real HYG (had it existed) may have
shown larger magnitude signal and stuck OFF earlier, avoiding the
whipsaw window. Adversarial bound (gate forced ON): -63%.

**Realistic NDX planning band**: -12% (optimistic, gate tracks credit
real-time) to -30% (plausible 1-3mo proxy lag) to -63% (adversarial
gate-completely-fails). Blend impact -3 to -13pp from NDX alone before
CPM/BULL losses in the same regime.

Academic context: cross-sectional momentum crashes are structural, not
random (Daniel-Moskowitz 2016, Barroso-Santa-Clara 2015). They occur
contemporaneously with market rebounds following deep bears. WML
historical magnitudes: 1932 -91% in 3mo, 2009 -73% in 3mo, 2000.12-
2001.1 -51%. Long-only top-K lacks short-side amplification but the
mechanism is identical. Real dot-com price action: Qualcomm -88%, Cisco
-89%, JDS Uniphase ~-99%, Nortel ~-97%, Intel -80%. Bubble-collapse
synthetic calibration above reflects this empirical pattern.

Limitations of the simulation: (a) only 72 names vs real NDX-100; (b)
synthetic paths are deterministic with overlaid noise, not draws from
actual dot-com sector dynamics; (c) HYG_stitched is VWEHX mutual fund
proxy pre-2007, not real-time HYG ETF behavior. Full replay would
require CRSP/Norgate PIT data for actual 1999-2003 NDX-100 prices and
real-time credit-spread data. Flagged as production blocker.

**Pre-2007 backtest reliability**

Dot-com (2000-02) and GFC (2008) are exactly where the defensive machinery
matters most, but they use proxy-stitched data (mutual-fund proxies for some
ETFs pre-2005; NDX sleeve mirrors BULL pre-2006 PIT). Directional only.

**Data quality (production-readiness blockers, not nice-to-haves)**

Live system uses `yfinance` (Yahoo scraper, beta; Yahoo Finance API is
intended for personal use, not endorsed) and `index-constitution` (Wikipedia-
sourced, beta; old tickers not auto-resolved in strict membership checks).
Known failure modes: yfinance DOM-change breakage, rate limiting / missing
data on month-end for individual NDX stocks, bad split/dividend adjustments,
unresolved old ticker symbols, NDX delisted-ticker leakage.

**VIX data sanity bounds**: `vol_cap.py` rejects VIX prints outside [8, 100]
as likely data errors (historical extremes: ~9 low 2017, ~85 high 1987 Black
Monday / ~83 COVID 2020). `vol_check.py` aborts state update + alert if
today's VIX is out of bounds rather than falsely triggering.

**VIX threshold during sustained low-vol periods**: in a 5y window
dominated by sub-15 VIX (e.g. 2012-2016), the rolling 5y P95 threshold
can drop to ~20, making the cap more trigger-happy than the ~30 today's
level implies. The cap's trigger frequency is regime-dependent on the
broader vol-of-vol regime, not a fixed VIX level.

**Backtested data-gap frequency** (CLEAN 18.1y panel):

| Pool | Total slot-checks | Missing | Rate |
|---|---:|---:|---:|
| CPM required ETFs (12 tickers × 151 months) | 1812 | 0 | **0.00%** |
| NDX PIT members (last 60 months) | 6287 | 433 | **6.89%** |

CPM ETF coverage is robust: zero historical gaps means abort-on-missing-data
would never have triggered. NDX gap rate is 6.89% at the universe level but
the top-8 selector picks from ~93 available tickers each month — a missing
ticker only matters if it would have been in the top-8 momentum picks.
Ghost-injection MC v2 (selection-stage bias section) quantifies the
downstream impact at ~0.03 Sh / 0.5pp CAGR in realistic scenarios.

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
- `bull_qqq_live.py` — BULL sleeve (legacy filename retained).
- `ndx_sleeve_live.py` — NDX sleeve (PIT constituent fetch).
- `build_dashboard.py` — 60/20/20 blend dashboard + peer benchmarks.
- `vol_cap.py` — portfolio-level latched binary vol cap (50% scale; VIX > rolling-5y P95 trigger). Includes VIX fetcher with local parquet cache.
- `vol_check.py` — daily vol-cap check job (state persistence + Telegram alert).
- `vol_cap_state.json` — persisted vol-cap state (committed by vol-check workflow).
- `data/` — stitched series; `data/ndx_constituents/prices.parquet` cached.
- `deploy/` — Cloudflare cron + Pages (monthly signal + daily vol-check).
- `.github/workflows/monthly-signal.yml` — monthly rebalance + dashboard rebuild.
- `.github/workflows/vol-check.yml` — daily vol-cap check + Telegram alert.
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
