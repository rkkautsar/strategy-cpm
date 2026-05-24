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
  composite (curve from rates, vol from broad market), (3) QQQ 12-1 absolute
  momentum (Antonacci/TSMOM-style trend filter). Only the canary is
  Keller-canonical; the composite and trend gates are extensions. In risk-off
  periods, BULL selects between SHV and IEF by 13612U momentum (HAA-style
  best-of-safe): IEF in falling-rate regimes (captures bond rally), SHV when
  rates are rising or stable. BULL is therefore an equity-or-defensive-sleeve
  strategy, not equity-or-cash; the defensive sleeve can carry duration risk.
- **NDX (20%)** — top-8 PIT Nasdaq-100 stocks by 13612U momentum, 12.5% each,
  gated by the BULL-QQQ regime (NDX = SHV cash when BULL flips to safe).
  K=8 chosen over a smaller K (4-6) for selection-stage bias mitigation: each
  pick is 12.5% of sleeve = 2.5% of portfolio, so a single-name bankruptcy
  caps blend damage at ~2.5%. K=8 halves the stress-clustered MaxDD vs K=4
  (-15.51% vs -25.70% under 1-bankruptcy-per-year stress-period simulation)
  at a -0.07 Sharpe edge cost. Annual turnover-bps is actually lower at K=8
  than K=4 (95 vs 100 bps) because per-pick rotation is smaller. Design
  choice for the regime asymmetry: BULL's macro canary acts as a portfolio-
  level circuit breaker for the growth sleeve. Individual-stock momentum
  during credit-stress or vol-blowup regimes is unreliable even when names
  appear strong, so NDX inherits BULL's regime verdict rather than running
  an independent macro gate (which would double-count HYG/TIP signal).

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
| **PROD 60/20/20 K=8 + vol cap** | **1.55** | **17.39%** | **10.85%** | **-12.00%** | **1.60** |
| PROD (no vol cap) | 1.51 | 17.66% | 11.17% | -12.00% | 1.47 |
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
| **PROD 60/20/20** | **1.34** | **16.42%** | **-16.59%** |
| SPY buy-hold | 0.61 | 10.41% | -55.19% |

**Forward expectation** (discount for selection bias + regime dependency + NDX
biases + tail sequencing not captured by return bootstrap):

| Metric | Backtest (+ vol cap) | Forward base case |
|---|---:|---|
| Sharpe | 1.55 | **1.05-1.35** |
| CAGR | 17.39% | **11-15%** pre-tax, **5-9%** after-tax |
| MaxDD | -12.00% | **-15% to -30%** planning band (K=8 caps selection-bias clustering at -22%; protracted Nasdaq bear with BULL gate-miss could reach -30%; vol cap reduces tail vol but doesn't always reduce MaxDD depth) |
| Calmar | 1.60 | **0.60-0.90** |

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
    picks   = [t for t, m in sorted(momenta, by=-m) if m > 0][:8]
    ndx     = {t: 0.125 for t in picks}                # 1/K=12.5% per pick
    ndx[SHV] = 1.0 - 0.125 * len(picks)

# ---- Combined ----
portfolio_uncapped = 0.60 * cpm + 0.20 * bull + 0.20 * ndx

# ====== Portfolio-level vol cap (latched binary 50% @ 22% trigger) ======
# Daily check: if blend trailing-21d realized vol > 22%, scale = 0.5; else 1.0.
# Once triggered, LATCH at 0.5 until next monthly signal date (re-evaluate then).
blend_vol_21d  = realized_vol_21d(portfolio_uncapped)
if blend_vol_21d > 0.22 OR vol_cap_latched_from_prior_day:
    scale = 0.5                                       # halve everything
else:
    scale = 1.0
portfolio = scale * portfolio_uncapped
portfolio[SHV] += (1 - scale)                         # excess to cash
```

**Universe** (all live since 2006-02 = DBC inception):

| Pool | Tickers |
|---|---|
| CPM RISKY (9) | QQQ, IWF, VBR, SPHQ, EFA, EEM, GLD, TLT, DBC |
| Safe / cash | SHV (BULL also uses IEF as best-of-safe) |
| CPM canary (3, HAA-style) | HYG_stitched, TIP, GLD |
| BULL canary (2) | HYG_stitched, TIP (LQD rejected: IG rallies on rate cuts during equity crashes, falsely keeps gate on in dotcom-style regimes) |
| NDX | point-in-time Nasdaq-100 (top-8 by 13612U, 12.5% each) |

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
- Typical month: ~16 tickers (9 CPM risky + SHV + QQQ + 8 NDX stocks).

Methodology, sensitivity grids, complexity-layer ablation, and references in
`cpm_bull_ndx_handout.md`. Key numbers inline:

**PROD 60/20/20 K=8 block bootstrap (CLEAN 18.1y, B=2000, 21d blocks):**

| Metric | Value |
|---|---|
| Point Sharpe | 1.514 |
| Bootstrap mean | 1.500 |
| 95% CI | [1.081, 1.940] |
| P(Sharpe > 1.0) | 99.2% |

The 95% lower bound (1.08) sits above the forward-expectation floor (1.00),
though less comfortably than the prior K=4 CI [1.13, 2.02]. Deflated Sharpe
on the blend is P(Sh > 0) = 99.5% at N=1000 trial haircut (Bailey-Lopez de
Prado); sensitive to assumed effective trial count.

**Blend-weight sensitivity (CPM fixed at 60%, BULL/NDX split varies):**

| Weights | Sharpe | CAGR | Vol | MaxDD |
|---|---:|---:|---:|---:|
| 60/40/0 (no NDX) | 1.470 | 15.43% | 10.12% | -9.85% |
| 60/30/10 | 1.560 | 17.49% | 10.72% | -11.33% |
| 60/25/15 | 1.581 | 18.51% | 11.15% | -12.13% |
| **60/20/20 (PROD)** | **1.590** | **19.53%** | **11.67%** | **-12.92%** |
| 60/15/25 | 1.590 | 20.55% | 12.25% | -13.86% |
| 60/10/30 | 1.582 | 21.56% | 12.89% | -15.01% |
| 60/0/40 (no BULL) | 1.552 | 23.57% | 14.31% | -17.52% |

Sharpe is on a flat plateau across 60/20/20 - 60/15/25 (both 1.590); BULL/NDX
split trades CAGR vs MaxDD ~linearly along that plateau. **Choice of 60/20/20
on this plateau is a personal preference for shallower DD over marginally
higher CAGR, not a model-evidence claim of superiority** — the Sharpe data
does not distinguish 60/20/20 from 60/15/25 within sample noise.

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
CPM→+BULL = +0.15 Sh, +BULL→+NDX = +0.07 Sh at +3pp DD cost.

**Portfolio-level vol cap robustness** (latched binary 50% @ 22% trigger):

| Test | Result |
|---|---|
| In-sample CLEAN 18.1y | Sharpe 1.554 vs baseline 1.515 (+0.039); Max realized vol 31.5% → 23.4% |
| Extended 30y (incl. dotcom) | Sharpe 1.311 vs 1.303 (+0.008); Max vol 33.1% → 24.9% |
| Out-of-window split (first half 2008-2017) | +0.042 Sharpe vs baseline (positive) |
| Out-of-window split (second half 2017-2026) | +0.032 Sharpe vs baseline (positive) |
| LB sensitivity (10/21/42/63d) | 21d is the optimum (Sh 1.554); others 1.498-1.510 |
| Alternative form: MM continuous @ 15% (Moreira-Muir 2017) | Sh 1.535 (worse), MaxDD -10.84% (better), 6 trades/yr |
| Alternative form: VIX-percentile @ 90th latched | Sh 1.472 (worst), worse on both windows |

Latched binary form empirically beats Moreira-Muir continuous and VIX-percentile
alternatives by Sharpe in both windows. MaxDD reduction is weaker than continuous
scaling but tail-vol compression is comparable. 22% threshold is the only one
positive across both in-sample halves. ~0.9 trades/yr.

**Hold-buffer sensitivity**: HB=2.0z reduces CPM MaxDD by 3.7pp vs HB=0 for
marginal Sharpe loss; flat plateau across HB ∈ [2, 5]z. Current vetos: buffer
disabled when (a) fewer than 3 positive candidates, (b) prior asset's faber
score <= 0, or (c) canary-state transition between months.

**EWMA halflife sensitivity** (CPM standalone, CLEAN 18.1y):

| Halflife | CPM Sh | CPM CAGR | CPM MaxDD |
|---|---:|---:|---:|
| 126d (0.5y) | 1.274 | 13.75% | -11.91% |
| 252d (1.0y) | 1.237 | 13.22% | -11.30% |
| **504d (2.0y, PROD)** | **1.284** | **13.75%** | **-11.30%** |
| 756d (3.0y) | 1.284 | 13.75% | -11.30% |
| 1008d (4.0y) | 1.187 | 12.68% | -15.12% |

PROD halflife sits on a flat 504d-756d plateau; 252d underperforms, 1008d
degrades sharply. Not cherry-picked: 504d is the lower-bound stable choice,
with 756d giving identical metrics.

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

**Additional vetos tested and rejected** (CLEAN 18.1y backtest):

| Variant | CPM Sh | CPM MaxDD | Blend Sh | Blend MaxDD |
|---|---:|---:|---:|---:|
| **PROD (current vetos)** | **1.308** | **-10.59%** | **1.590** | **-12.92%** |
| + (d) prior 13612U mom > 0 required | 1.242 | -12.49% | 1.533 | -13.94% |
| + (e) buf-var <= 1.10 * fresh-var | 1.267 | -12.49% | 1.552 | -13.94% |
| + both (d) + (e) | 1.267 | -12.49% | 1.552 | -13.94% |

Both proposed safety vetos hurt on both Sharpe and MaxDD. The buffer's value
is retaining weak-momentum prior members during noise; additional vetos
defeat its core function by forcing unnecessary swaps. Current minimal
veto set (faber>0 + small-sample + canary transition) is empirically at
the right balance.

**30y extended window** includes dotcom, GFC, COVID, 2022 inflation; pre-2006
NDX mirrors BULL and pre-2001-06 canary reduces to HYG-only. Asset-momentum
12-1 circuit breaker is primary defense in macro-confusion regimes (dotcom).

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

- **Portfolio-level vol is NOT capped.** Only CPM (60%) is vol-targeted at 12%.
  BULL (~18-25% vol) and NDX (~30-40% vol) run uncapped. Realized blend vol
  (21d rolling): P50 10.3%, P95 21.0%, P99 27.8%, **max 38.7%** (COVID 2020-04).
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

**Selection-stage bias** (Ghost-injection MC v2, missing delisted names
injected into ranking universe with synthetic price paths calibrated to NDX
distribution): **177 historical NDX-100 members had no panel price data**
(CELG, BRCM, ATVI, DELL, CERN, etc.). At K=8, ghost selection rate is
~17-20% of NDX picks (slightly higher than K=4 because more slots are
filled). Blend impact at K=8 under adversarial cross-validation (50 seeds
per scenario):

| Scenario | Sharpe Δ | CAGR Δ | MaxDD (K=8) | vs K=4 |
|---|---:|---:|---:|---:|
| Realistic 1.5% bankruptcy rate (random) | -0.019 | -0.25pp | -12.01% | (K=4: -13.17%) |
| Pessim 3% rate | -0.039 | -0.50pp | -12.12% | (K=4: -13.61%) |
| **Adversarial 1/yr bankruptcy stress-clustered** | **-0.109** | **-1.40pp** | **-15.51%** | **(K=4: -25.70%)** |

**K=8 cuts the stress-clustered MaxDD damage in half** (-25.70% → -15.51%)
because per-pick weight drops from 5% to 2.5% of portfolio. Realistic-case
damage is small (-0.02 to -0.04 Sharpe). Fully eliminating selection-stage
bias requires a survivorship-bias-free equity database (CRSP, Norgate,
Compustat) that includes delisted names in the pre-selection ranking
universe. The K=8 dilution + 20% sleeve weight are the structural caps.

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
selector cannot compensate because the EWMA covariance structure it is
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
  EWMA covariance helps modestly (~+0.08 Sh in 2021-23) but cannot fully
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
- **In-sample selection bias**: anchor forward Sharpe at 1.05-1.35 (not 1.58
  backtest); planning MaxDD band -15 to -25%. The forward floor is more
  optimistic than the data warrants if positive stock/bond correlation
  becomes the structural norm rather than a transient regime.
- **CPM/BULL canary asymmetry**: when CPM is all-cash (HYG+TIP+GLD all
  negative) but BULL canary fires (HYG+TIP positive), the portfolio can hold
  20% QQQ + 20% NDX with 60% SHV. Intentional. CPM uses GLD as a real-asset
  diversifier because it has alternative cross-asset rotations available;
  BULL-QQQ is a binary single-equity gate where a stricter 2-asset canary
  is preferred (a third asset adds redundant credit-rates signal rather
  than new structural information). Same-canary symmetry would couple the
  two sleeves' regime verdicts, reducing the value of running them as
  independent risk-management overlays.

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
- `vol_cap.py` — portfolio-level latched binary vol cap (50% @ 22% trigger).
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
