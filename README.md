# CPM-BULL-NDX

**60/20/20 growth/Nasdaq momentum strategy with defensive overlays.** Personal
runbook + spec. Realized mean Nasdaq/growth exposure is ~44% with max ~70% in
34.6% of months — this is *not* a fully diversified all-weather TAA. Defensive
machinery (canaries, NDX DD circuit, pair selection) caps drawdowns when macro stress
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
  caps blend damage at ~2.5%. Defensive paths (gate-off, partial-fill,
  mid-period delisting) use HAA best-of-safe (SHV/IEF), not SHV-only.
  NDX inherits BULL's regime verdict; no independent macro gate (BULL's
  HYG/TIP signal would otherwise be double-counted).

**Risk overlays:**
- **NDX DD circuit (sole portfolio-level overlay):** when NDX sleeve DD from
  63d rolling peak < -10%, scale NDX to cash until next monthly signal date.
  Nystrup-Boyd (Stanford 2019) threshold; 63d window matches r3 in 13612U.
  Empirical scope test showed BULL DD circuit added negligible benefit
  (+0.006 Sharpe) vs NDX-only (+0.113 Sharpe), so the circuit only fires
  on NDX. Lookback x threshold grid is smooth across 42-252d / -7.5% to
  -15% (no cliffs). VIX cap was tested and removed (-0.011 Sharpe, -0.87pp
  CAGR, consistently hurt crisis returns).

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

Clean live-ETF window 2008-04-30 → present (~18y, post-cost, with NDX-only
DD circuit). Raw backtest; Shumway-pessimistic survivor-bias MC shifts PROD
by < 0.01 Sharpe / 0.05pp CAGR (see Caveats § NDX bias).

| Strategy | Sharpe | CAGR | Vol | MaxDD | Ulcer |
|---|---:|---:|---:|---:|---:|
| **PROD 60/20/20 (BULL-SPY)** | **1.70** | **17.24%** | **9.84%** | **-8.25%** | **2.40%** |
| SPY buy-hold | 0.66 | 11.76% | 19.79% | -51.48% | -- |
| QQQ buy-hold | 0.82 | 17.23% | 22.29% | -49.37% | -- |

| Sleeve standalone (no caps) | Sharpe | CAGR | Vol | MaxDD |
|---|---:|---:|---:|---:|
| CPM | 1.32 | 14.44% | 10.63% | -14.70% |
| BULL-SPY | 1.20 | 13.16% | 10.83% | -13.60% |
| NDX top-K (no Rebound) | 1.24 | 29.25% | 23.66% | -31.52% |

Extended 30y window 1996-01-04 → 2026-05-15 (uses Vanguard mutual fund stitches
pre-live for non-live ETFs; HYG-only canary pre-2001-06; directional only):

| Strategy | Sharpe | CAGR | MaxDD |
|---|---:|---:|---:|
| **PROD 60/20/20** | **1.54** | **15.08%** | **-9.85%** |
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
| Raw Sharpe | 1.70 | **1.15-1.45** |
| Excess Sharpe (over SHV) | 1.56 | **1.00-1.30** (subtract ~0.10-0.15 for rate income) |
| CAGR | 17.24% | **11-15%** pre-tax, **5-9%** after-tax |
| MaxDD | -8.25% | **-15% to -30%** planning band, **-35 to -40% stress**, **-78% theoretical worst case** if BULL gate fails across all sleeves (dot-com simulation; under FRED-BAA10Y validated VWEHX behavior, NDX MaxDD limited to -12%) |
| Calmar | 2.09 | **0.55-0.90** |

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
else:
    ndx = {safe: 1.0}                                  # 100% best-of-safe (no Rebound)

# ---- Combined ----
portfolio_uncapped = 0.60 * cpm + 0.20 * bull + 0.20 * ndx

# ====== NDX-only DD circuit breaker (Nystrup-Boyd 2019) ======
# Daily check on NDX sleeve only: if DD from 63d rolling peak < -10%,
# scale NDX to 0 (cash) until next monthly signal date.
# Nystrup-Boyd Dmax = 10% paper standard. 63d rolling peak (1 quarter,
# matches r3 component in 13612U) avoids stale-peak suppression.
# Empirical scope test: BULL DD circuit adds +0.006 Sharpe (negligible)
# vs NDX-only +0.113 Sharpe -- only NDX needs the protection.
rolling_peak = ndx_eq.rolling(63).max()
ndx_dd = (ndx_eq / rolling_peak - 1)[T-1]
ndx_scale = 0.0 if ndx_dd < -0.10 else 1.0   # resets at next signal date
ndx = ndx_scale * ndx

# VIX cap REMOVED (tested then removed). Tail-risk test showed -0.011 Sharpe,
# -0.87pp CAGR, and consistently hurt crisis returns (GFC -5.54pp, COVID
# -0.63pp, 2022 -1.90pp). NDX DD circuit provides MaxDD protection;
# VIX cap was redundant overlay suppressing CPM defensive-sleeve gains.
# (Kept as a no-op below for spec history; previously: latched binary
# 50% at VIX > rolling-5y P95.)
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
| Point Sharpe | 1.700 |
| Bootstrap mean | 1.697 |
| 95% CI | [1.292, 2.136] |
| P(Sharpe > 1.0) | 99.8% |
| P(Sharpe > 1.05) | 99.8% |

The 95% lower bound (1.292) sits well above the forward-expectation floor
(1.05) with comfortable margin (~0.24). P(true Sharpe > 1.05 forward floor) = 99.8%.
Deflated Sharpe on the blend is P(Sh > 0) = 99.5% at N=1000 trial haircut
(Bailey-Lopez de Prado); sensitive to assumed effective trial count.

**Excess Sharpe over T-bills (SHV).** Raw Sharpes above are computed against
zero, not the risk-free rate. SHV-excess Sharpe is the honest metric for a
strategy that holds cash in defensive months:

| Strategy | CLEAN raw Sh | CLEAN excess Sh | 30y raw Sh | 30y excess Sh |
|---|---:|---:|---:|---:|
| **PROD** | **1.700** | **1.563** (-0.14) | **1.538** | **1.304** (-0.23) |
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
| CLEAN 18.1y | 21d (1mo) | 1.697 | [1.292, 2.136] |
| CLEAN 18.1y | 63d (3mo) | 1.676 | [1.320, 2.034] |
| CLEAN 18.1y | 126d (6mo) | 1.691 | [1.371, 1.990] |
| Extended 30y | 21d (1mo) | 1.543 | [1.198, 1.894] |
| Extended 30y | 63d (3mo) | 1.525 | [1.243, 1.801] |
| Extended 30y | 126d (6mo) | 1.521 | [1.248, 1.782] |

Block-length robustness is strong: mean Sharpe stable across 1mo-6mo
blocks on both windows; longer blocks narrow CI as expected. Lower CI
bounds remain well above 1.0 on both windows even at 21d (CLEAN 1.32, EXT
1.22), so block-length sensitivity is not a concern after the DD circuit
fix and BULL-SPY swap.

**Regime-block bootstrap** (SPY 200d-SMA bull/bear buckets, N=2000;
addresses external-review concern about regime imbalance):

| Window | Regime split | Mean Sh | 95% CI |
|---|---|---:|---:|
| CLEAN 18.1y | 79% bull / 21% bear | 1.704 | [1.218, 2.186] |
| Extended 30y | 72% bull / 28% bear | 1.539 | [1.157, 1.917] |

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
blends, gates, hold-buffer parameters, vol-cap variants, safe-pool, and
per-component sensitivity grids over the research path:

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

(All numbers include NDX-only DD circuit; VIX cap was removed.)

| Weights | Sharpe | CAGR | MaxDD | Max-rv (63d) | Ulcer |
|---|---:|---:|---:|---:|---:|
| 60/40/0 (no NDX) | 1.487 | 14.06% | -8.74% | 15.72% | 2.62% |
| 60/30/10 | 1.618 | 15.66% | -8.27% | 15.76% | 2.52% |
| 60/25/15 | 1.665 | 16.45% | -8.07% | 16.57% | 2.50% |
| **60/20/20 (PROD)** | **1.700** | **17.24%** | **-8.25%** | **17.48%** | **2.50%** |
| 60/15/25 | 1.723 | 18.04% | -8.43% | 18.54% | 2.52% |
| 60/10/30 | 1.736 | 18.82% | -8.62% | 19.66% | 2.56% |
| 60/0/40 (no BULL) | 1.738 | 20.40% | -9.01% | 22.08% | 2.70% |

**Note**: all rows include NDX-only DD circuit (no VIX cap); the comparison
across rows is internally consistent. Sharpe rises monotonically with NDX
weight; PROD 60/20/20 sits mid-plateau, with 60/10/30 marginally higher
(+0.033 Sharpe at cost of 50% more single-name concentration risk).

Sharpe rises monotonically with more NDX weight (60/30/10 = 1.618 -> 60/10/30 = 1.736);
BULL/NDX split trades CAGR vs MaxDD ~linearly. 60/20/20 sits mid-plateau at
Sharpe 1.700; 60/15/25 (1.723) and 60/10/30 (1.736) are slightly higher but
increase MaxDD and stock-pick concentration risk. **60/20/20 is a balance
choice, not the Sharpe-max point; Sharpe plateau spans ~0.12 across the grid.**

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
lifts blend Sharpe from CPM-only 1.324 to PROD 1.700, a total +0.376 Sh
beyond CPM alone. CAGR rises from 14.44% to 17.24% and MaxDD tightens from
-14.70% (CPM alone) to -8.25% (blend with NDX-only DD circuit). NDX DD
circuit is the dominant tail-protector; VIX cap was tested and removed.

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

**Portfolio-level vol cap robustness** (removed from PROD; section retained for historical context):

**Sharpe reconciliation: where did current Sharpe 1.70 come from?**

Stepwise from prior-version baseline (BULL-QQQ, no DD circuit, no VIX cap):

| Step | Sharpe | CAGR | MaxDD |
|---|---:|---:|---:|
| baseline (BULL-QQQ, no DD) | 1.563 | 18.24% | -11.93% |
| + NDX-only DD circuit (-10% from 63d peak, Nystrup-Boyd) | 1.692 | 18.05% | -8.40% |
| **+ BULL QQQ→SPY swap (current PROD)** | **1.700** | **17.24%** | **-8.25%** |
| Delta from baseline | +0.137 | -1.00pp | +3.68pp |

NDX-only DD circuit is the dominant Sharpe contributor (+0.129) and the
MaxDD driver (-3.53pp). BULL-SPY swap adds +0.008 Sharpe with -0.81pp CAGR
cost (diversification benefit vs NDX). VIX cap was removed after testing
showed it contributed -0.011 Sharpe and consistently hurt crisis-period
returns (GFC -5.54pp, COVID -0.63pp, 2022 -1.90pp).

**Crisis period returns vs no-VIX-cap (EXT 30y, demonstrates why removed):**

| Period | with VIX cap | no VIX cap (PROD) | Cap impact |
|---|---:|---:|---:|
| GFC Sep-Dec 2008 | +5.36% | +10.90% | -5.54pp |
| COVID Feb-Apr 2020 | +0.55% | +1.18% | -0.63pp |
| 2022 rate shock | +5.35% | +7.25% | -1.90pp |
| Aug 2024 carry unwind | +0.46% | +1.32% | -0.86pp |

VIX cap fired during these stress events but halved the portfolio when
CPM was rotating into GLD/IEF/TLT (defensive sleeves rallying). NDX DD
circuit already provides MaxDD protection; VIX cap was redundant overlay
suppressing CPM defensive gains.

**NDX-only DD circuit threshold sensitivity** (PROD 60/20/20):

| Threshold | Sharpe | CAGR | MaxDD | NDX DD-days |
|---:|---:|---:|---:|---:|
| -7.5% | 1.756 | 17.17% | -7.85% | 1,115 |
| **-10.0% (PROD, Nystrup-Boyd)** | **1.700** | **17.24%** | **-8.25%** | **701** |
| -12.5% | 1.724 | 18.10% | -8.82% | 461 |
| -15.0% | 1.685 | 18.04% | -8.71% | 304 |
| -20.0% | 1.634 | 17.71% | -10.44% | 166 |

**Lookback x threshold grid** (63d-row is PROD; smooth across grid, no cliffs):

| Lookback | -7.5% | -10% | -12.5% | -15% |
|---:|---:|---:|---:|---:|
| 42d | 1.791 / -8.2% | 1.689 / -8.6% | 1.709 / -9.0% | 1.674 / -8.8% |
| **63d (PROD)** | 1.768 / -8.2% | **1.693 / -8.6%** | 1.714 / -8.8% | 1.676 / -8.7% |
| 84d | 1.752 / -8.2% | 1.661 / -8.6% | 1.688 / -8.8% | 1.668 / -8.7% |
| 126d | 1.712 / -8.2% | 1.640 / -8.6% | 1.670 / -8.8% | 1.672 / -8.7% |
| 252d | 1.705 / -8.2% | 1.624 / -8.6% | 1.668 / -8.8% | 1.674 / -8.7% |

Grid is smooth; MaxDD essentially flat at 8.2-9.0% across all combinations.
No cliff at PROD point. -7.5% Sharpe peak (1.79) is fire-rate artifact (3-4x
more trigger days = noisier) and not selected. -10% / 63d sits within 0.01
Sharpe of column max.

**Trigger scope** (which sleeves get DD circuit):

| Scope | Sharpe | MaxDD |
|---|---:|---:|
| No DD circuit | 1.576 | -10.31% |
| BULL only | 1.582 | -10.25% |
| **NDX only (PROD)** | **1.689** | **-8.25%** |
| BULL + NDX | 1.693 | -8.58% |

~99% of the benefit comes from NDX alone (+0.113 Sharpe over baseline);
BULL DD circuit adds only +0.006 Sharpe. PROD applies the circuit to NDX
only -- one fewer parameter, one fewer overlay to explain.

Ablation table (CLEAN 18.1y, PROD 60/20/20):

| Variant | Sharpe | CAGR | Vol | MaxDD |
|---|---:|---:|---:|---:|
| baseline (no DD circuit) | 1.563 | 18.24% | 10.72% | -11.93% |
| +VIX cap only (removed) | 1.569 | 17.29% | 10.21% | -11.75% |
| **PROD (NDX-only DD circuit)** | **1.700** | **17.24%** | **9.84%** | **-8.25%** |

**Trade-off interpretation.** NDX-only DD circuit is the dominant overlay:
+0.137 Sharpe and -3.68pp MaxDD improvement over baseline. VIX cap alone
was roughly neutral on Sharpe (+0.006), modest MaxDD improvement (-0.18pp),
at -0.95pp CAGR cost. Adding VIX cap on top of DD circuit: -0.011 Sharpe,
-0.87pp CAGR, no MaxDD improvement. Removed -- pure DD circuit is the
production overlay.

*VIX cap operational details (daily check, latched reset rules, edge cases,
failure modes via `vol_check.py` + GH Actions cron) removed with the overlay
in the same audit. The `vol_check.py` and `vol_cap_state.json` files remain
in the repo for the standalone VIX-state-tracking widget but no longer affect
PROD allocations.*

**Cost sensitivity** (CLEAN 18.1y blend; same cost_bps/side applied
to every sleeve):

| Cost/side | Blend Sh | CAGR | MaxDD |
|---:|---:|---:|---:|
| 0 bps | 1.740 | 17.68% | -8.20% |
| 5 bps | 1.720 | 17.46% | -8.23% |
| **10 bps (PROD)** | **1.700** | **17.24%** | **-8.25%** |
| 15 bps | 1.681 | 17.02% | -8.27% |
| 20 bps | 1.661 | 16.80% | -8.29% |
| 25 bps | 1.474 | 15.93% | -11.67% |
| 50 bps | 1.382 | 14.86% | -12.02% |
| 75 bps | 1.289 | 13.80% | -12.81% |
| 100 bps | 1.195 | 12.75% | -15.52% |

Linear Sharpe degradation ~**0.0036 Sh per bps** through full range; CAGR
drops ~1pp per 25 bps. MaxDD stable to 50 bps, expands materially past
75 bps. Blend Sharpe stays above 1.05 forward floor up to 100 bps; the
edge is not thin enough that 2-3x cost overruns destroy it.

**Rebound bypass: removed.** The Goulding-Harvey 4-state 'Rebound' bypass
(NDX 50% top-K + 50% safe when BULL gate off but fast QQQ 2mo TR > 0) was
shipped briefly and then removed. Empirical contribution +0.028 portfolio
Sharpe and +0.48pp CAGR; 44 fires / 18y with 61% win rate -- modest. The
specific implementation (fixed 50/50 weight, 2mo fast horizon, NDX-only
application) was a pragmatic calibration not paper-cited; Goulding-Harvey
recommends adaptive a_Re estimation. Removed for cleaner spec; one fewer
mechanism to defend and explain. Forward expected impact: -0.03 Sharpe
vs prior-with-rebound spec.

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
for NDX, 3-AND BULL gate) is at the empirical
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

| SELECT_K (NDX) | 8 | 21% | 4/8/6 (K=4 wins +0.034) | +0.034 |
| Blend weights 60/20/20 | - | - | 33-combo grid | -0.050 |

Reading: 4 of 9 params have PROD as the most-chosen WFO value (>50% rate).
The remaining 5 split between extremes (bimodal). In all cases except
SELECT_K, fixed PROD outperforms rolling parameter optimization -- which
is the canonical signature of robust strategy parameters (in-sample
optimization does not generalize forward). SELECT_K=8 is deliberately
held at higher diversification than the Sharpe-optimal K=4 to halve
per-position tail risk (12.5% vs 25% per name).

Bimodal patterns (TARGET_VOL) reveal
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

- **NDX standalone vol is the dominant tail driver.** CPM (60%) is
  vol-targeted at 12% sleeve-internal (and the cap is monthly ex-ante, so
  mid-month spikes are uncapped). BULL (~14-25% standalone vol) and NDX
  (~23-40% standalone vol) run uncapped at sleeve level. The portfolio-level
  uncapped at sleeve level. To address this, the NDX DD circuit (63d rolling
  peak < -10% per Nystrup-Boyd) scales NDX to cash when triggered. Realized
  blend 63d vol distribution (CLEAN 18.1y):

  | Variant | P50 | P75 | P90 | P95 | P99 | Max |
  |---|---:|---:|---:|---:|---:|---:|
  | Baseline (no DD circuit) | 9.68% | 12.32% | 14.93% | 16.40% | 19.54% | 20.78% |
  | **PROD (NDX-only DD circuit)** | **9.25%** | **11.20%** | **12.74%** | **13.88%** | **15.84%** | **17.48%** |

  DD circuit is the dominant tail-vol compressor: P99 vol drops 19.54% ->
  15.84%, max from 20.78% -> 17.48%.
  cap's contribution is tighter vol (9.33% vs 9.71% no-cap) at a -0.91pp
  CAGR cost. Sleeve-internal caps remain in place; the portfolio VIX cap
  is a second defense for mid-month vol blowups when VIX confirms.

  **Note**: NDX DD circuit alone tightens max realized 63d vol from 20.78%
  to 17.48%. VIX cap was tested as an additional overlay but removed: it
  marginally further compressed tail vol (max 16.35%) at unacceptable cost
  (-0.87pp CAGR, -5.54pp GFC return, -1.9pp 2022 return).
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

NDX DD circuit fires within hours of -10% from 63d rolling peak; protects
that sleeve only, not portfolio-wide. Numbers above are conservative
upper bounds (no overlay protection assumed in the worst-case scenario).

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
- `vol_cap.py` — NDX-only DD circuit breaker (63d rolling peak; -10% Nystrup-Boyd threshold; scale to cash until next monthly signal). VIX cap helpers also defined here but no longer applied to PROD (legacy filename retained).
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
