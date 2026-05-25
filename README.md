# CPM-BULL-NDX

**60/20/20 growth/Nasdaq momentum strategy with defensive overlays.** Personal
runbook + spec. Realized mean Nasdaq/growth exposure is ~44% with max ~70% in
34.6% of months — this is *not* a fully diversified all-weather TAA. Defensive
machinery (canaries, vol cap, pair selection) caps drawdowns when macro stress
registers; in calm bull regimes the portfolio runs as concentrated growth
beta.

Blend validation detail (NDX MC, bootstrap, DSR, ablation, hold-buffer) in
`cpm_bull_ndx_handout.md`. BULL-QQQ academic memo in `bull_qqq_handout.md`.

- **CPM (60%)** — canary-gated momentum + min-variance pair selection on a
  9-asset ETF universe (US factors + international + diversifiers).
- **BULL-QQQ (20%)** — 100% QQQ when three gates all pass: (1) Keller/HAA-
  inspired HYG OR TIP 13612U > 0 canary, (2) a custom curve OR vol regime
  composite (curve from rates, vol from broad market), (3) QQQ 12mo TR
  absolute momentum (Antonacci GEM 2014 / TSMOM-style trend filter).
  Antonacci GEM uses simple 12-month total return (no skip-month). Only the canary is
  Keller-canonical; the composite and trend gates are extensions. In risk-off
  periods, BULL selects between SHV and IEF by 13612U momentum (HAA-style
  best-of-safe): IEF in falling-rate regimes (captures bond rally), SHV when
  rates are rising or stable. BULL is therefore an equity-or-defensive-sleeve
  strategy, not equity-or-cash; the defensive sleeve can carry duration risk.
- **NDX (20%)** — top-8 PIT Nasdaq-100 stocks by 13612U momentum, 12.5% each,
  gated by the BULL-QQQ regime (NDX = SHV cash when BULL flips to safe).
  Each pick = 12.5% of sleeve = 2.5% of portfolio; single-name bankruptcy
  caps blend damage at ~2.5%. NDX inherits BULL's regime verdict; no
  independent macro gate (BULL's HYG/TIP signal would otherwise be
  double-counted).

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

Clean live-ETF window 2008-04-30 → 2026-05-15 (18.1y, post-cost). Raw backtest;
Shumway-pessimistic survivor-bias MC shifts PROD by < 0.01 Sharpe / 0.05pp CAGR
(see Caveats § NDX bias).

| Strategy | Sharpe | CAGR | Vol | MaxDD | Calmar |
|---|---:|---:|---:|---:|---:|
| **PROD 60/20/20 K=8** | **1.63** | **16.84%** | **9.86%** | **-9.12%** | **1.85** |
| SPY buy-hold | 0.66 | 11.74% | 19.81% | -51.48% | 0.23 |

| Sleeve standalone | Sharpe | CAGR | Vol | MaxDD |
|---|---:|---:|---:|---:|
| CPM | 1.29 | 13.83% | 10.49% | -11.30% |
| BULL-QQQ | 1.18 | 16.88% | 14.06% | -14.31% |
| NDX top-8 (K=8) | 1.19 | 28.02% | 23.03% | -29.51% |

Extended 30y window 1996-01-04 → 2026-05-15 (uses Vanguard mutual fund stitches
pre-live for non-live ETFs; HYG-only canary pre-2001-06; directional only):

| Strategy | Sharpe | CAGR | MaxDD |
|---|---:|---:|---:|
| **PROD 60/20/20** | **1.47** | **15.33%** | **-16.15%** |
| SPY buy-hold | 0.61 | 10.41% | -55.19% |

**Naive benchmark suite** (CLEAN 18.1y / Extended 30y; post-cost 10bps/side
where applicable). PROD vs single-asset buy-hold and naive QQQ-trend strategies:

| Benchmark | CLEAN Sh | CLEAN CAGR | CLEAN MaxDD | 30y Sh | 30y CAGR | 30y MaxDD |
|---|---:|---:|---:|---:|---:|---:|
| **PROD** | **1.53** | **16.78%** | **-11.46%** | **1.30** | **14.85%** | **-16.59%** |
| SPY buy-hold | 0.66 | 11.78% | -51.48% | 0.61 | 10.41% | -55.19% |
| QQQ buy-hold | 0.82 | 17.17% | -49.37% | 0.63 | 14.41% | -82.96% |
| QQQ + 10mo SMA (Faber) | 0.82 | 13.02% | -28.56% | 0.78 | 14.26% | -41.73% |
| QQQ + 12mo TR>0 (GEM-equiv) | 0.91 | 16.38% | -28.56% | 0.83 | 16.72% | -46.72% |
| SPY + 12mo TR>0 (GEM-equiv) | 0.74 | 10.62% | -33.72% | 0.79 | 11.21% | -33.72% |

Reading: QQQ-buy-hold matches PROD's CLEAN CAGR but loses ~5x on MaxDD. Naive
QQQ + 12mo TR (closest one-asset benchmark) has comparable CAGR but ~2.5x
worse MaxDD and 0.5-0.7 Sharpe gap. PROD's risk-adjusted edge over the best
naive single-asset trend benchmark is +0.5-0.7 Sharpe and 2-5× MaxDD
compression on both windows. Even after the forward base-case haircut
(Sh 1.05-1.35), PROD remains above QQQ+12mo-TR (Sh 0.83-0.91). The blend
architecture is doing real risk-adjusted work, not just QQQ regime-riding.


**Forward expectation** (discount for selection bias + regime dependency + NDX
biases + tail sequencing not captured by return bootstrap):

| Metric | Backtest | Forward base case |
|---|---:|---|
| Raw Sharpe | 1.63 | **1.15-1.45** |
| Excess Sharpe (over SHV) | 1.50 | **1.00-1.30** (subtract ~0.10-0.15 for rate income) |
| CAGR | 16.84% | **11-15%** pre-tax, **5-9%** after-tax |
| MaxDD | -11.46% | **-15% to -30%** planning band, **-35 to -40% stress**, **-78% theoretical worst case** if BULL gate fails across all sleeves (dot-com simulation; under FRED-BAA10Y validated VWEHX behavior, NDX MaxDD limited to -12%) |
| Calmar | 1.50 | **0.55-0.90** |

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

# ====== BULL-QQQ sleeve (20%) ======
canary_on    = mom_13612U(HYG) > 0 OR mom_13612U(TIP) > 0
p_curve      = sum(IEF[T-63d:T] ret) > sum(TLT[T-63d:T] ret)   # curve steepening
# Broad-MARKET vol pillar, intentionally SPY not QQQ.
# Empirical test (see Validation): QQQ-vol gives BULL Sh 1.09 vs SPY-vol
# 1.18, so the broad-market vol regime is a stronger filter for the BULL
# sleeve than asset-specific Nasdaq vol despite QQQ being the held asset.
p_market_vol = realized_vol_63d(SPY) < avg(rolling_63d_vol over 252d, SPY)
composite_on = p_curve OR p_market_vol
asset_mom_on = mom_12mo(QQQ) > 0

if canary_on AND composite_on AND asset_mom_on:
    bull = {QQQ: 1.0}
else:
    # HAA best-of-safe: SHV in rising-rate regimes, IEF in falling-rate.
    safe = argmax({s: mom_13612U(s) for s in [SHV, IEF]})
    # Rebound bypass (FIXED-5050): if slow gate says defensive but QQQ 2mo TR > 0
    # (Goulding-Harvey 'Rebound' state), blend 50/50 instead of full cash.
    # Symmetric with the 50% VIX cap. Zero free parameters; FIXED-5050 captures
    # ~88% of Goulding's adaptive a_Re lift with no estimator.
    fast_qqq_on = mom_2mo(QQQ) > 0
    if fast_qqq_on:
        bull = {QQQ: 0.5, safe: 0.5}    # REBOUND_BLEND
    else:
        bull = {safe: 1.0}              # CASH

# ====== NDX sleeve (20%) ======
if BULL-QQQ regime != "BULL_QQQ":
    ndx = {SHV: 1.0}
elif PIT NDX-100 data unavailable (pre-2006):
    ndx = bull                                        # mirror BULL-QQQ
else:
    momenta = {t: mom_13612U(t) for t in PIT_NDX100(T)}
    picks   = [t for t, m in sorted(momenta, by=-m) if m > 0][:8]
    ndx     = {t: 0.125 for t in picks}                # 1/K=12.5% per pick
    ndx[SHV] = 1.0 - 0.125 * len(picks)

# ---- Combined ----
portfolio_uncapped = 0.60 * cpm + 0.20 * bull + 0.20 * ndx

# ====== Per-sleeve DD circuit breaker (TT Market Vane #5 analog) ======
# Daily check: if BULL or NDX sleeve cumulative DD from peak < -15%,
# scale THAT sleeve to 0 (cash) until next monthly signal date.
# CPM untouched (low standalone DD, doesn't need it).
# Symmetric with VIX cap but DD-triggered instead of vol-triggered.
for sleeve in [BULL, NDX]:
    sleeve_dd = (sleeve_eq / sleeve_eq.cummax() - 1)[T-1]
    if sleeve_dd < -0.15 OR dd_circuit_latched_from_prior_day:
        sleeve_scale = 0.0                                # sleeve to cash
    else:
        sleeve_scale = 1.0
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
| Point Sharpe | 1.528 |
| Bootstrap mean | 1.515 |
| 95% CI | [1.088, 1.970] |
| P(Sharpe > 1.0) | 99.2% |
| P(Sharpe > 1.05) | 98.5% |

The 95% lower bound (1.09) sits above the forward-expectation floor (1.05)
with limited margin (~0.04). P(true Sharpe > 1.05 forward floor) = 98.5%.
Deflated Sharpe on the blend is P(Sh > 0) = 99.5% at N=1000 trial haircut
(Bailey-Lopez de Prado); sensitive to assumed effective trial count.

**Excess Sharpe over T-bills (SHV).** Raw Sharpes above are computed against
zero, not the risk-free rate. SHV-excess Sharpe is the honest metric for a
strategy that holds cash in defensive months:

| Strategy | CLEAN raw Sh | CLEAN excess Sh | 30y raw Sh | 30y excess Sh |
|---|---:|---:|---:|---:|
| **PROD** | **1.571** | **1.444** (-0.13) | **1.326** | **1.084** (-0.24) |
| CPM solo | 1.337 | 1.212 | 1.119 | 0.878 |
| BULL solo | 1.231 | 1.139 | 0.979 | 0.823 |
| NDX solo | 1.190 | 1.132 | 1.074 | 0.950 |
| SPY buy-hold | 0.662 | 0.593 | 0.610 | 0.465 |
| QQQ buy-hold | 0.824 | 0.762 | 0.631 | 0.527 |

T-bill CAGR averaged 1.34% on CLEAN window, 2.74% on 30y. The 30y excess
Sharpe (1.084) sits ~0.03 above the forward base-case floor (1.05) -- a
thin margin once rate income is netted out (HAA-safe expansion lifted it
from 1.065 to 1.084). CLEAN excess Sharpe (1.444) retains real edge with
a -0.13 haircut from raw. PROD clears every benchmark on excess Sharpe in
both windows. **Use excess Sharpe for any capital-allocation decision;
raw Sharpe overstates by 0.1-0.25.**

**Block bootstrap robustness across block lengths** (N=2000 resamples, raw
Sharpe; addresses external-review concern that 21d blocks may underestimate
autocorrelation):

| Window | Block | Mean Sh | 95% CI |
|---|---:|---:|---:|
| CLEAN 18.1y | 21d (1mo) | 1.558 | [1.119, 2.017] |
| CLEAN 18.1y | 63d (3mo) | 1.580 | [1.192, 1.942] |
| CLEAN 18.1y | 126d (6mo) | 1.604 | [1.256, 1.949] |
| Extended 30y | 21d (1mo) | 1.316 | [0.975, 1.667] |
| Extended 30y | 63d (3mo) | 1.328 | [1.045, 1.626] |
| Extended 30y | 126d (6mo) | 1.319 | [1.044, 1.576] |

Block-length robustness is good: mean Sharpe stable across 1mo-6mo blocks
on both windows; longer blocks narrow CI as expected (less effective
samples). 30y 21d-block CI lower bound dips to 0.975 -- below 1.0 raw
Sharpe -- suggesting the 21d-block default may understate dependence in
deeper-history data. Use 63-126d blocks for conservative inference (lower
bounds 1.04-1.05).

**Regime-block bootstrap** (SPY 200d-SMA bull/bear buckets, N=2000;
addresses external-review concern about regime imbalance):

| Window | Regime split | Mean Sh | 95% CI |
|---|---|---:|---:|
| CLEAN 18.1y | 79% bull / 21% bear | 1.581 | [1.129, 2.044] |
| Extended 30y | 74% bull / 26% bear | 1.324 | [0.963, 1.685] |

Resampling within regime buckets to preserve bull/bear mix. CLEAN CI
remains positive throughout. **30y regime-block CI lower bound 0.963 sits
below forward floor 1.05** -- the 30y window's bear-regime weight (26%) is
historical, but a future regime with >30% bear could push realized Sharpe
below the forward floor. Treat as a sensitivity warning, not a base case.

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

| Weights | Sharpe | CAGR | MaxDD | Max-rv |
|---|---:|---:|---:|---:|
| 60/40/0 (no NDX) | 1.467 | 14.25% | -9.30% | 24.9% |
| 60/30/10 | 1.514 | 15.40% | -10.32% | 26.7% |
| 60/25/15 | 1.525 | 15.97% | -10.89% | 27.6% |
| **60/20/20 (PROD)** | **1.529** | **16.53%** | **-11.46%** | **28.5%** |
| 60/15/25 | 1.528 | 17.09% | -12.02% | 29.5% |
| 60/10/30 | 1.521 | 17.65% | -12.62% | 30.5% |
| 60/0/40 (no BULL) | 1.498 | 18.76% | -14.38% | 32.5% |

Sharpe is on a flat plateau spanning roughly 60/30/10 - 60/10/30; BULL/NDX
split trades CAGR vs MaxDD ~linearly along the plateau. 60/20/20 sits at the
Sharpe peak (1.529); 60/25/15 and 60/15/25 are essentially tied within
sample noise (±0.004 Sharpe).
**The plateau is flat; this is a choice within a noise-equivalent range, not
a model-dominance claim.**

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

**Complexity-layer ablation** (alt 19.3y window): each layer adds Sharpe;
CPM→+BULL = +0.15 Sh, +BULL→+NDX = +0.07 Sh at +3pp DD cost. Window is
~1y longer than CLEAN headline (18.1y). The 19.3y increments sum to **+0.22
Sh**, comparable to the CLEAN-window blend (1.53) minus CPM standalone
(1.29) gap of **+0.24 Sh**; remaining ~0.02pp likely reflects the VIX cap
plus window-overlap differences.

**Conditional sleeve correlation** (CPM vs BULL+NDX combined as one
growth-tilted entity, CLEAN 18.1y, regime classified by **BULL gate state**
— *not* realized market stress; see caveat below):

| Regime | Months | Days | corr(daily) | corr(monthly) |
|---|---:|---:|---:|---:|
| RISK-ON | 139 | 2,912 | 0.46 | 0.47 |
| RISK-OFF | 79 | 1,628 | 0.24 | 0.19 |
| ALL | 218 | 4,540 | 0.40 | 0.40 |

In risk-on regimes (BULL holding QQQ), CPM and BULL+NDX co-move at moderate
correlation (~0.46) because CPM often picks QQQ/IWF/SPHQ as one pair member.
**Empirical pair-mechanism check**: across the 95 risk-on signal months
(BULL gate engaged) with CPM in pair-selection mode, CPM holds a growth
ticker (QQQ / IWF / SPHQ) as one of the two pair members in **73/95 =
76.8%** of months. In risk-off regimes the correlation halves (~0.24) as
CPM rotates into diversifiers (GLD / TLT / DBC). The blend Sharpe gain over
sleeve standalones (blend 1.53 vs CPM 1.29, BULL 1.18, NDX 1.22) is
consistent with through-cycle correlation ~0.40.

**Classifier caveat**: "risk-on" here means BULL gate engaged, not
realized market calm. In gate-miss stress episodes (BULL stays risk-on
while markets are actually under pressure), both CPM and BULL+NDX would
be losing simultaneously and the realized correlation in that sub-state
would be HIGHER than 0.46. The 0.46 risk-on correlation is therefore a
lower bound on realized correlation when the BULL gate is engaged AND
stress materializes despite the gate.

**Portfolio-level vol cap robustness** (latched binary 50%, VIX > rolling-5y P95):

| Window | Sharpe | CAGR | MaxDD | Max-rv | r12mo mean-DD | r24mo mean-DD | Trades/yr |
|---|---:|---:|---:|---:|---:|---:|---:|
| CLEAN 18.1y (baseline) | 1.51 | 17.66% | -12.00% | 31.5% | -7.28% | -8.31% | 0 |
| **CLEAN 18.1y (with cap)** | **1.53** | **16.58%** | **-11.46%** | **28.5%** | **-6.63%** | **-7.40%** | **1.8** |
| Extended 30y (baseline) | 1.30 | 15.41% | -16.59% | 33.1% | -8.30% | -9.64% | 0 |
| Extended 30y (with cap) | 1.30 | 14.66% | -16.59% | 33.1% | -7.88% | -9.09% | 1.6 |

**Trade-off interpretation.** On CLEAN 18.1y the cap improves single MaxDD
by 0.54pp (-12.00% → -11.46%), tail vol by 3.0pp (31.5% → 28.5%), and
rolling-12mo mean DD by 0.65pp, at the cost of -1.08pp CAGR. On Extended
30y the cap is **essentially flat on Sharpe and gives no MaxDD or Max-rv
improvement**, while costing -0.75pp CAGR; only rolling-DD experience
improves modestly (~0.4pp on 12mo mean). The cap's value comes from
shallower rolling drawdown experience and the external (non-data-tuned)
calibration; the headline Sharpe shift is within bootstrap-CI noise on
both windows. Pre-2002 stitched-proxy data + the 5y VIX lookback warmup
dampen the cap's effect on the early portion of the 30y window.

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
| 0 bps | 1.563 | 17.01% | -11.32% |
| 5 bps | 1.546 | 16.79% | -11.39% |
| **10 bps (PROD)** | **1.528** | **16.58%** | **-11.46%** |
| 15 bps | 1.510 | 16.36% | -11.53% |
| 25 bps | 1.474 | 15.93% | -11.67% |
| 50 bps | 1.382 | 14.86% | -12.02% |
| 75 bps | 1.289 | 13.80% | -12.81% |
| 100 bps | 1.195 | 12.75% | -15.52% |

Linear Sharpe degradation ~**0.0036 Sh per bps** through full range; CAGR
drops ~1pp per 25 bps. MaxDD stable to 50 bps, expands materially past
75 bps. Blend Sharpe stays above 1.05 forward floor up to 100 bps; the
edge is not thin enough that 2-3x cost overruns destroy it.

**Rebound bypass (FIXED-5050)** applies in Rebound state (slow gate says
DEFENSIVE but QQQ 2mo TR > 0). BULL holds 50% QQQ + 50% safe instead of
100% cash. FAST 2mo from Goulding-Harvey 2022; blend weight fixed 50/50.
BULL sleeve only.

Fire behavior (post-cost):

| Stat | CLEAN 18.1y | Extended 30y |
|---|---:|---:|
| Fires | 30 (1.67/yr) | 49 (1.62/yr) |
| Win rate | 63% | 59% |
| Avg lift on wins | +3.22pp BULL | +3.59pp BULL |
| Avg lift on losses | -1.60pp BULL | -2.91pp BULL |
| Win:loss size ratio | 2.0× | 1.23× |

Wins: 2009-03 GFC bottom (+13% QQQ next mo), 2020-04 COVID V (+13%),
2023-02/03 banking-crisis pivot (+8-9%). Losses (30y only): 2000-03,
2001-01 dotcom bear-market rallies (-24% to -26% QQQ next mo, BULL sleeve
hit -12 to -14pp). Architectural lineage: Levine-Pedersen 2016 / Hurst-
Ooi-Pedersen 2017 (fixed multi-horizon blend pattern) plus Goulding-Harvey
2022 4-state model (FAST horizon definition).

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
- Per-sleeve DD circuit breaker: BULL and NDX each get scaled to cash if
  their individual cumulative DD < -15% mid-month (TT Market Vane #5 analog)
  to address this. Realized blend 21d vol distribution:

  | Window | P50 | P75 | P90 | P95 | P97 | P99 | Max |
  |---|---:|---:|---:|---:|---:|---:|---:|
  | Uncapped (baseline) | 9.5% | 12.7% | 17.0% | 19.6% | 21.5% | 24.3% | **31.5%** (COVID 2020-04) |
  | **With VIX cap (PROD)** | **9.2%** | **12.1%** | **15.6%** | **17.4%** | **18.5%** | **22.0%** | **28.5%** |

  The portfolio VIX cap reduces tail risk across the distribution (P95 -2.2pp,
  P99 -2.3pp, Max -3.0pp) at a small CAGR cost (-1.1pp). MaxDD improves
  -12.00% → -11.46% on CLEAN; rolling-12mo mean DD improves -7.28% → -6.63%.
  Sleeve-internal caps remain in place; the portfolio VIX cap is a second
  defense for mid-month vol blowups when VIX confirms.

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
  underperform vs BULL-QQQ alone.

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
- **In-sample selection bias**: anchor forward Sharpe at 1.05-1.35 (not 1.53
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
**Don't size based on backtest -11.46% MaxDD.**

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
- `bull_qqq_live.py` — BULL-QQQ sleeve.
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
