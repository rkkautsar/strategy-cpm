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
| **PROD 60/20/20 K=8 + VIX cap** | **1.53** | **16.58%** | **10.41%** | **-11.46%** | **1.45** |
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
| Sharpe | 1.53 | **1.05-1.35** |
| CAGR | 16.58% | **11-15%** pre-tax, **5-9%** after-tax |
| MaxDD | -11.46% | **-15% to -30%** planning band (per-pick weight caps selection-bias clustering at -22%; protracted Nasdaq bear with BULL gate-miss could reach -30%; VIX cap improves single-event MaxDD but doesn't fully address regime tail) |
| Calmar | 1.45 | **0.55-0.90** |

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
| Safe / cash | SHV (BULL also uses IEF as best-of-safe) |
| CPM canary (3, HAA-style) | HYG_stitched, TIP, GLD |
| BULL canary (2) | HYG_stitched (high-yield credit), TIP (inflation-linked bonds) |
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

The 95% lower bound (1.08) sits above the forward-expectation floor (1.00).
Deflated Sharpe on the blend is P(Sh > 0) = 99.5% at N=1000 trial haircut
(Bailey-Lopez de Prado); sensitive to assumed effective trial count.
Bootstrap CI is computed on the **uncapped blend** (point Sharpe 1.514);
the VIX-capped variant shifts Sharpe by ~+0.014 on the CLEAN window. Capped
variant CI lower bound is approximately **1.10** (1.08 + 0.014); above the
1.05 forward floor but with limited margin.

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

**30y MaxDD attribution.** Worst blend drawdown on the 30y window is
**-16.59%, the 1998 LTCM/Russia crisis** (peak 1998-07-20, trough
1998-10-08, 80 days peak-to-trough, recovered 1999-07-14). Sleeve
contributions peak-to-trough: CPM -8.70pp, BULL -4.32pp, NDX -4.47pp (NDX
in pre-2006 BULL-mirror mode, so duplicates BULL's loss profile). All three
sleeves contributed; pre-2001-06 the canary reduces to HYG-only (TIP not
live yet), leaving the system more exposed to the 1998 liquidity shock
than it would be with the full 2-asset BULL canary today.

**Blend-weight sensitivity** (CPM fixed at 60%, BULL/NDX split varies):

*Both columns shown so the headline (60/20/20 with VIX cap, Sharpe 1.53)
is comparable to the sensitivity grid.*


| Weights | Sharpe | CAGR | Vol | MaxDD |
|---|---:|---:|---:|---:|
| Weights | Uncap Sh | Uncap CAGR | Uncap MaxDD | Cap Sh | Cap CAGR | Cap MaxDD |
|---|---:|---:|---:|---:|---:|---:|
| 60/40/0 (no NDX) | 1.458 | 15.24% | -9.85% | 1.467 | 14.25% | -9.30% |
| 60/30/10 | 1.501 | 16.44% | -10.87% | 1.514 | 15.40% | -10.32% |
| 60/25/15 | 1.511 | 17.03% | -11.43% | 1.525 | 15.97% | -10.89% |
| **60/20/20 (PROD)** | **1.515** | **17.62%** | **-12.00%** | **1.529** | **16.53%** | **-11.46%** |
| 60/15/25 | 1.513 | 18.20% | -12.90% | 1.528 | 17.09% | -12.02% |
| 60/10/30 | 1.506 | 18.78% | -13.85% | 1.521 | 17.65% | -12.62% |
| 60/0/40 (no BULL) | 1.482 | 19.93% | -15.71% | 1.498 | 18.76% | -14.38% |

Sharpe is on a flat plateau spanning roughly 60/30/10 - 60/10/30; BULL/NDX
split trades CAGR vs MaxDD ~linearly along the plateau. The point estimates
show 60/20/20 at the Sharpe peak (1.529 capped / 1.515 uncapped), with
60/25/15 and 60/15/25 essentially tied within sample noise (±0.004 Sharpe).
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
~1y longer than CLEAN headline (18.1y); Sh increments expected to be
similar magnitude on CLEAN (no regime structurally different in the extra
1y of data).

**Conditional sleeve correlation** (CPM vs BULL+NDX combined as one
growth-tilted entity, CLEAN 18.1y, regime classified by BULL gate state):

| Regime | Months | Days | corr(daily) | corr(monthly) |
|---|---:|---:|---:|---:|
| RISK-ON | 139 | 2,912 | 0.46 | 0.47 |
| RISK-OFF | 79 | 1,628 | 0.24 | 0.19 |
| ALL | 218 | 4,540 | 0.40 | 0.40 |

In risk-on regimes (BULL holding QQQ), CPM and BULL+NDX co-move at
moderate correlation (~0.46) because CPM often picks QQQ/IWF/SPHQ as one
pair member. In risk-off regimes the correlation halves (~0.24) as CPM
rotates into diversifiers (GLD/TLT/DBC). The blend Sharpe gain over
sleeve standalones (blend 1.53 vs CPM 1.29, BULL 1.18, NDX 1.22) is
consistent with through-cycle correlation ~0.40.

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

- **Sleeve-internal vol caps don't fully bound blend tail.** Only CPM (60%) is
  vol-targeted at 12% sleeve-internal (and the cap is monthly ex-ante, so
  mid-month spikes are uncapped). BULL (~14-25% standalone vol) and NDX
  (~23-40% standalone vol) run uncapped at sleeve level. The portfolio-level
  vol cap (latched binary 50% with VIX > rolling-5y P95 trigger; daily check) was added on top
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

**Stress applied to uncapped variant.** The VIX cap would likely engage
during a 2022-style sustained bear (VIX consistently above 25-30) and
reduce realized MaxDD depth, but the cap doesn't fully eliminate
protracted-bear gap risk. The numbers above are conservative (no cap)
upper bounds on potential MaxDD.

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
