# CPM-BULL

**Canary-gated Pair Momentum + BULL-QQQ overlay** -- a monthly tactical asset allocation strategy: canary-gated momentum
with min-variance pair selection (CPM), plus a trend-filtered Nasdaq
overlay (BULL-QQQ). See [TL;DR](#summary-card) for the
2-minute version, [Strategy spec](#strategy-spec-compact) for the
pseudocode, [Validation & Robustness](#validation--robustness) for the
full rigor.

## Summary Card

Two-sleeve monthly TAA: **70% CPM defensive engine + 30% BULL-QQQ overlay**.
Monthly rebalance, ETF-only, no leverage, 10 bps/side cost. Designed for
IRA/401k/Roth only (monthly rotation = short-term gains).

CPM = **canary-gated momentum + min-variance pair selection** across
an 11-asset universe. NOT marketed as factor rotation -- ETFs span
equity factors, sectors, international, and diversifiers, with GLD/TLT
structurally critical (~-0.32 Sh if removed).
BULL-QQQ = trend-filtered Nasdaq overlay, independently gated by its own
3-asset canary (HYG/LQD/TIP). Note the canaries differ by sleeve: CPM uses
HYG/TIP/GLD (real-asset/tail focus), BULL uses HYG/LQD/TIP (credit/inflation
focus). Documented in caveat 7 -- intentional, not a bug.

**Headline metrics** (ETF-live 18y, 2008-2026, 13612U canonical HAA signal,
10 bps/side cost):

| Strategy | Sharpe | CAGR | MaxDD |
|---|---:|---:|---:|
| **PROD 70/30 CPM-BULL** | **1.56** | **16.63%** | **-12.3%** |
| CPM standalone | 1.34 | 13.48% | -10.8% |
| BULL-QQQ standalone | 1.26 | 23.15% | -28.6% |
| Naive 70/30 PP/QQQ-trend (counterfactual) | 1.01 | 8.4% | -14.9% |
| QQQ buy-hold (raw target) | 0.89 | 18.95% | -35.1% |
| SPY buy-hold | 0.73 | 13.13% | -40.8% |

**Forward expectation** (heavily discounted from backtest):

| | Forward base case |
|---|---|
| Sharpe | **0.90-1.20** (not the 1.56 backtest) |
| CAGR | **8-12%** (not the 16.63% backtest) |
| MaxDD | **-15% to -25%** (closer to EXT than LIVE) |

**Top 3 caveats** (full list of 9 in Validation & Robustness section):
1. **Severe tax drag** -- economically unattractive outside tax-advantaged accounts (IRA/401k/Roth) for most investors. Monthly rotation = short-term gains, ~2-4pp/yr drag.
2. **CPM is cross-asset momentum + min-variance pair selection, not factor rotation.** Drop GLD/TLT = -0.32 Sh standalone. Heavily relies on stock/bond negative correlation; degrades in 2022-style positive-correlation regimes.
3. **Structural V-shape recovery lag is permanent.** 13612U slow-by-design; bleeds ~1-2 months of alpha at violent regime turns (COVID 2020 was the tail). Asymmetric-canary fix tested, rejected.

See **Strategy spec** (next section) for full pseudocode and component
sources. See **Validation & Robustness** (after spec) for detailed tables
on weight sensitivity, cost stress, joint stress, universe robustness,
bootstrap CI, DSR, XLP rule validation, and full 9 caveats.

## Strategy spec (compact)

```python
# Helpers (signal date T = last trading day of month)
mom_12_1(asset)    = price[T-1mo] / price[T-13mo] - 1
mom_13612U(asset)  = (r1 + r3 + r6 + r12) / 4    # canonical HAA unweighted average
                                                  # (U = Unweighted; matches Keller paper)
faber_score(asset) = (price[T] - SMA_10mo) / SMA_10mo

# ====== CPM sleeve (70% capital) ======
RISKY = [QQQ, IGM, XLE, VBR, SPHQ, XMHQ, XLV, VEA, VWO, GLD, TLT]   # 11 ETFs
canary_on = mom_13612U(HYG) > 0 OR mom_13612U(TIP) > 0 OR mom_13612U(GLD) > 0

if not canary_on:
    cpm = {SHV: 1.0}                                     # defensive: cash
else:
    candidates = [a for a in top_K=6 by faber_score if faber_score(a) > 0]
    # Candidate-count fallback (deterministic):
    if len(candidates) >= 2:
        pair = min_variance_pair(candidates, lookback=756d)  # ~3y covariance
        cpm = {pair[0]: 0.5, pair[1]: 0.5}
    elif len(candidates) == 1:
        cpm = {candidates[0]: 0.5, SHV: 0.5}                 # partial defensive
    else:
        cpm = {SHV: 1.0}                                     # full defensive
    # Hold-buffer (deterministic, leg-level): retain prior pair member if its
    # cross-sectional z-score (sample-std over positive candidates) is within
    # HOLD_BUFFER = 2.5 units of the worst new pick. Stale members (faber<=0)
    # NEVER retained. Buffer DISABLED if fewer than 3 positive candidates (small
    # sample makes z-score unstable). See research/hold_buffer_threshold_diagnosis.log.

# Vol cap (de-risk only, scale capped at 1.0; no leverage)
scale = min(1.0, 0.10 / realized_vol_63d(proposed_fcp_basket))
cpm = {asset: weight * scale for asset, weight in cpm.items()}
cpm[SHV] = cpm.get(SHV, 0.0) + (1.0 - sum(cpm.values()))   # cash absorbs residual

# ====== BULL-QQQ sleeve (30% capital) ======
trend_ok = mom_12_1(QQQ) > 0 OR mom_13612U(QQQ) > 0
macro_on = mom_13612U(HYG) > 0 OR mom_13612U(LQD) > 0 OR mom_13612U(TIP) > 0
late_cycle_infl = (HYG- AND LQD- AND TIP+)

if trend_ok AND macro_on:
    bull = {XLP if late_cycle_infl else QQQ: 1.0}
else:
    bull = {SHV: 1.0}

# Combined: 70% CPM + 30% BULL, T+1 MOC execution, 10 bps/side
```

## Component sources

| Component | Source |
|---|---|
| 12-1 skip-month absolute momentum (BULL trend) | GEM-inspired (Antonacci 2014); 12-month lookback with 1-month skip (`p[T-1mo]/p[T-13mo] - 1`), NOT the exact-12-month GEM formula. Uses adjusted total-return prices. |
| 13612U canonical HAA momentum | Keller & Keuning 2022 HAA canonical; simple unweighted average of 1/3/6/12-month total returns. Internal validation run confirmed: canonical form beats weighted 13612W (+0.08 Sh) AND matches actual paper. Use total-return adjusted prices. |
| Composite OR trend (12-1 OR 13612U) | Our extension |
| TIP canary | Keller HAA 2022 |
| HYG/LQD multi-canary | Our extension of Keller DAA (2018) |
| Faber 10mo SMA ranker (CPM) | Faber 2007 SSRN-inspired; uses adjusted total-return prices (yfinance auto_adjust=True, dividend-reinvested). |
| Min-variance pair selection | Optimum3/AllocateSmartly 2022-inspired; exact implementation is CPM's (756d covariance on total-return data). Beats lowest_corr (-0.22 Sh) and inv_vol (-0.08 Sh) variants; robust across 126-1260d lookback. |
| Vol cap (de-risk only, sleeve-level) | TSMOM/risk-parity-inspired de-risking; no leverage. NOT the strict Moskowitz/Ooi/Pedersen 2012 construction. Applied to CPM basket via 63d realized total-return vol; not portfolio-level. |
| Cross-sectional selection (top-K rank) | Conceptual inspiration: Jegadeesh & Titman 1993 JoF (return-rank momentum). Actual implementation: Faber 2007 SMA score. J&T listed for transparency of mechanism family, NOT as direct citation. |
| Hold-buffer dampener | Practitioner standard (AQR notes); applied as z-score of Faber distance |
| **XLP in HYG-/LQD-/TIP+** | Neuberger Berman 2024 (credit-spread sector rotation), Fidelity business cycle, Hartford Funds 2025 (inflation duration) |
| Multi-test haircut (DSR/PSR) | Bailey & Lopez de Prado 2012 |

## Validation & Robustness

Detailed validation tables that backstop the headline metrics and forward
expectation in the Summary Card. Each subsection is self-contained;
read the ones you care about.

### Performance-stat conventions

All reported metrics use these conventions consistently:

- **Returns**: daily portfolio returns from simulated month-end fills,
  compounded to CAGR via `(eq_end / eq_start) ^ (1 / years_calendar) - 1`
  where years_calendar = (date_end - date_start).days / 365.25
- **Sharpe**: annualized daily Sharpe over a **zero risk-free rate**
  (`mean(daily_returns) * 252 / (std(daily_returns) * sqrt(252))`,
  using population std `ddof=0`). NOT excess over T-bill -- chosen for
  simplicity and comparability; T-bill returns are small post-2008 so
  the difference vs excess-Sharpe is bounded (~+0.05 to +0.15 typical).
- **Volatility**: annualized daily, `std(daily) * sqrt(252)`, ddof=0
- **MaxDD**: daily equity-curve drawdown (`min(eq/eq.cummax() - 1)`),
  NOT monthly-only -- captures intramonth tails
- **Dividends/distributions**: reinvested via yfinance `auto_adjust=True`
  (dividend-adjusted total-return prices)
- **Transaction costs**: 10 bps per side on changed notional at each
  monthly rebalance (round-trip 20 bps on a full flip)
- **Risk-free for reference**: SHV ~ 3-month T-bill is ~4.3% currently;
  excess-Sharpe would be ~0.15-0.20 lower than reported zero-RF Sharpe

### Warm-up rule (early ETF history)

Deterministic handling of partial-history covariance estimation:

- Pair-selection covariance lookback is 756 trading days (~3 years)
- If fewer than 756 daily observations exist for a pair candidate,
  the available overlapping history is used (no padding/extrapolation),
  subject to minimum 252 days (~1 year)
- If fewer than 252 overlapping daily observations exist, the asset is
  excluded from pair selection until sufficient history accrues
- **Practical impact**: 2008 headline window has partial-history
  covariance in the first ~2 years for some pair candidates (e.g.,
  XMHQ launched 2006-12, HYG 2007-04). Strict fully-warmed-up start
  is ~2010. Post-2010 / post-2012 verification runs (Sh 1.65 / 1.71)
  confirm the warm-up period is not inflating headline numbers.

### Data-source replication

Research backtest uses `yfinance auto_adjust=True` (dividend-reinvested
adjusted Close). **Before deploying live capital**, replicate the headline
allocation history and returns against a second total-return data source:

- Norgate Data, Tiingo, CRSP, Bloomberg, Refinitiv, or Portfolio
  Visualizer-style total-return feeds
- Verify dividend-adjustment timing and reinvestment assumptions match
- Re-run the canonical CLI backtest and confirm Sharpe / CAGR / MaxDD
  within ~0.05 Sh / ~0.5pp CAGR of headline reported numbers

Faber's own replication guidance (Faber 2007) emphasizes total-return
data including dividends and income; this is a production hygiene
requirement, not a strategy-design issue.

### Extended 32y stress window

1994-2026, uses Vanguard mutual-fund proxies pre-ETF-inception for several
assets. Treat as regime stress-test, not as primary headline:

| Strategy | Sharpe | CAGR | MaxDD |
|---|---:|---:|---:|
| **PROD 70/30** | **1.28** | **13.95%** | **-16.7%** |

*Numbers across all V&R subsections are from the same canonical run
(CLI window 2008-09-30 for LIVE, 1994-01-01 for EXT; current 13612U +
hold-buffer-fixed spec; 10 bps/side cost unless explicitly stressed).*
| Naive 70/30 PP/QQQ-trend | 1.11 | 9.45% | -14.9% |
| QQQ buy-hold | 0.55 | 14.25% | **-83.0%** |

Earlier ETF-live note: All 11 risky ETFs tradable post-2008 (XMHQ launched
2006-12, HYG 2007-04, SHV 2007-01 -- earliest possible start with all ETFs
simultaneously live is Q3 2007). With 756d covariance lookback, signal-clean
start is ~2010. Reported 2008-2026 uses tradable ETFs with partial-history
covariance in first ~2 years; strict no-proxy / full-lookback runs
(post-2010, post-2012) show even stronger Sh 1.65/1.71.

### Headline deltas (ETF-live 18y)

- vs **Naive 70/30 PP/QQQ-trend** (apples-to-apples, same architecture, simpler
  components): **+0.55 Sh, +8.2pp CAGR**. Measures pure design value-add
  over thoughtful-but-simpler implementation of same meta-architecture.
- vs **QQQ buy-hold** (raw target): **+0.67 Sh, -2.32pp CAGR, MaxDD
  -12% vs -35%** (~3x lower DD). Trades CAGR for crisis protection.
- vs **CPM alone**: +0.22 Sh, +3.15pp CAGR (the 30% bull sleeve adds
  Nasdaq-100 upside in risk-on months without contaminating defensive logic).

### Universe robustness (asset-class drop, CPM standalone)

| Drop | Delta CPM Sh | Verdict |
|---|---:|---|
| International (VEA/VWO) | +0.02 | not load-bearing |
| Tech (QQQ/IGM) | +0.03 / -0.08 | mixed (older spec helped; current 13612U+756d hurts -- CPM-Core rejected) |
| Equity factors (XMHQ/SPHQ/VBR) | -0.02 | helpful, not overwhelming |
| Sectors (XLE/XLV) | -0.12 | matter |
| **Diversifiers (GLD/TLT)** | **-0.32** | **structurally essential** |

Strategy robust across equity-universe perturbations but diversifier
sleeve (GLD/TLT) is core, not decorative.

### Cost stress (canonical window, 10 bps base, 50 bps stress, 100 bps extreme)

| Cost | LIVE Sh | CAGR | MaxDD |
|---|---:|---:|---:|
| 5 bps | 1.58 | 16.77% | -12.3% |
| **10 bps (PROD)** | **1.56** | **16.63%** | **-12.3%** |
| 25 bps | 1.53 | 16.23% | -12.4% |
| **50 bps (stress)** | **1.47** | **15.55%** | **-12.5%** |
| 100 bps (extreme) | 1.35 | 14.19% | -12.8% |

Stress case (50 bps) covers bad fills, month-end stale liquidity, wider
spreads, slippage. Strategy still Sh 1.47 at that level. MaxDD barely
changes across cost regimes.

### Joint stress (correlated failure-mode: 50bps + no-diversifier-benefit + EXT 32y)

| Stress combination | EXT Sh | EXT CAGR | EXT MaxDD |
|---|---:|---:|---:|
| Baseline (10bps, full universe) | 1.276 | 13.95% | -16.7% |
| + 50 bps cost | 1.170 | 12.69% | -19.0% |
| + Drop GLD/TLT | 1.081 | 12.68% | -19.1% |
| **JOINT (50bps + drop GLD/TLT + EXT)** | **0.99** | **11.52%** | **-19.3%** |

Under simultaneous worst-case failures, Sharpe drops to **0.99** -- still
**within** the forward expectation band of 0.90-1.20, and well above SPY's
historical ~0.73. Even with three correlated failure modes hitting at
once, the strategy lands inside the discounted forward range -- moderate-
confidence robustness claim.

### Pair engine + proxy-free checks

**Pair engine robust to covariance lookback** (Sh range 1.48-1.55 across
126-1260d on LIVE, no needle-fit at PROD's 756d).

**Proxy-free verification**: ETF-live-period strictly post-2010/2012 shows
**better** Sharpe (1.65/1.71) than full 2008-2026 with stitched proxies
(1.53). Refutes "proxies inflate the edge" concern for the ETF-live
window. Pre-2010 regime coverage still proxy-dependent; treat EXT 32y
as stress-test, not headline.

### Forward expectation discipline

*Forward expectation NOT raised despite 13612U signal improvement. The
13612U switch is one more selected variant in the research trail -- it
improves backtest evidence AND citation integrity but does not justify
upgrading the forward promise. Backtest improvement increases confidence
in the design, not the magnitude of expected return.*

*All numbers in this document use canonical CLI window 2008-09-30 to
present, current 13612U spec, 10 bps/side cost.*

### Bootstrap CI + DSR

**Bootstrap CI is wide.** LIVE Sharpe 95% CI = **[0.86, 1.71]** -- a true
forward Sharpe of 0.90 is entirely plausible. DSR (Bailey & Lopez de
Prado 2012) at N=1000 effective trials shows 96-100% probability the
edge exceeds the data-mining null, but: (a) the 13612U signal-family
test is itself one more selected variant in the research trail, so N_eff
may be higher than logged; (b) PSR(>1.0) is only 94-98% even under the
assumed N. Anchor expectations to the discounted band, treat DSR as
"supportive under assumed N_eff" not "edge is proven real".

### Blend weight sensitivity

Flat surface 60/40 to 80/20, 70/30 peaks both windows, NOT a sharp peak
(robust to ratio choice):

| Blend | LIVE Sh | LIVE CAGR | LIVE MaxDD | EXT Sh |
|---|---:|---:|---:|---:|
| 80/20 | 1.534 | 15.61% | -10.7% | 1.255 |
| **70/30 (PROD)** | **1.564** | **16.63%** | **-12.3%** | **1.276** |
| 60/40 | 1.555 | 17.64% | -13.8% | 1.268 |
| 50/50 | 1.520 | 18.62% | -15.4% | 1.243 |

### Key caveats (full 9 -- Summary Card lists top 3)

1. In-sample selection on hyperparameters/universe. DSR @ N=1000 effective
   trials is supportive (93-100%) but N_eff is debatable -- if real trial
   count is higher, DSR confidence drops. Take as "supportive under
   assumed multi-test haircut", not "edge is proven real".
2. **CPM is a cross-asset momentum + pair-selection strategy. Do not market or interpret as factor rotation.**
   Drop GLD/TLT = -0.32 Sh standalone. The edge heavily relies on the
   negative correlation and crisis-alpha provided by gold and long-duration
   Treasuries. If stock/bond correlation remains positive for an extended
   secular period (like 2022), the CPM sleeve's efficiency degrades. This
   was a 2-2.5 sigma event historically but cannot be assumed away.
3. **Structural V-shape recovery lag is permanent.** 13612U momentum
   lookback (1/3/6/12-month avg) is slow by design. Strategy bleeds
   relative alpha during the first 1-2 months of a violent new bull
   market (COVID 2020 was the tail). Asymmetric-canary fix tested and
   REJECTED across all 3 windows -- modern era has too few V-recoveries
   to make slower re-engagement worth the missed bull months. This is
   an accepted permanent cost, not a fixable bug.
4. BULL CAGR is QQQ-era artifact (forward anchor 7-10%, not 18-20%)
5. **Severe tax drag -- economically unattractive outside tax-advantaged accounts for most investors.**
   Monthly rotation + hold-buffer optimizations on 11 underlying assets =
   exclusively short-term capital gains. ~2-4pp/yr drag at federal 22-37%
   + state 0-13%. Use only in IRA / 401k / Roth / tax-deferred. In a
   taxable account, after-tax CAGR drops to ~4-7% (vs 8-12% forward
   pre-tax expectation) -- not worth the operational complexity.
6. **Vol-target is sleeve-level, not portfolio-level**: CPM has 10% vol
   target (de-risk only, scale capped at 1.0, no leverage), BULL has none. Realized vol
   computed on 63-day daily total-return std of the proposed current CPM
   basket. Combined portfolio is NOT explicitly vol-targeted -- BULL
   contributes raw exposure. Tested adding vol-target to BULL (oracle-v6):
   hurts Sharpe across all caps 15-30% because cuts QQQ exposure exactly
   when rallies are hardest.
7. **LQD divergence quirk** -- psychological execution risk. BULL sleeve
   has independent macro gate (HYG OR LQD OR TIP positive 13612U). When
   CPM canary off (HYG- AND TIP- AND GLD-) but LQD+, BULL may remain risk-on:
   combined portfolio can hold 30% QQQ while CPM is 70% SHV. By design --
   BULL catches IG-credit-only recovery signals CPM's 2-asset canary
   misses -- but holding 30% Nasdaq-100 while the core engine screams
   "cash" will be psychologically difficult to execute in real-time.
   Have a written plan to not override the rule.
8. **Defensive avoids INTERMEDIATE-duration only**: CPM defensive mode is
   100% SHV (ultra-short Treasury, ~0.3y effective duration). But CPM
   risky universe still includes TLT when canary on -- strategy holds
   duration via TLT pair selection in risk-on. The cleaner claim:
   "defensive fallback uses short-treasury cash, not intermediate
   Treasuries". Not "avoids duration risk entirely".
9. **Asymmetric canary tested, rejected** -- requiring 2-month positive
   confirmation for risk-on (slower re-engagement, addresses V-recovery
   lag) was tested and net negative across all 3 windows (LIVE -0.05 Sh,
   TEST -0.04, EXT -0.02). Modern era too few V-recoveries to make the
   confirmation worth missed bull months. Single-month canary kept.

### XLP late-cycle rule validation (small-sample, low-conviction)


The HYG-/LQD-/TIP+ -> XLP substitution is the least-statistically-validated
element of the spec. Retained on mechanistic grounds (credit-stress sector
rotation literature, see Component sources). Honest stats:

| Metric | Value (n=18 firings across EXT 32y) |
|---|---|
| Mean edge (XLP - QQQ) | +0.94%/month |
| Median edge | +1.88%/month |
| Hit% (XLP > QQQ) | 67% |
| 95% Bootstrap CI on mean | **[-1.23%, +3.05%]** (includes zero) |
| P(edge > 0) | 81% |
| P(edge > 0.5%) | 66% |
| t-statistic vs zero | 0.85, **p = 0.41** (not stat-sig) |

Per-window edge (consistent direction across all 4 windows despite small n):

| Window | n | Mean edge | Hit% |
|---|---:|---:|---:|
| LIVE 18y | 12 | +1.17% | 67% |
| TRAIN 2008-16 | 2 | +2.89% | 100% (n=2 noise) |
| **TEST OOS 2017+** | **10** | **+0.83%** | **60%** |
| EXT pre-LIVE | 6 | +0.49% | 67% |

**Verdict**: mechanism-backed (Neuberger Berman 2024, Fidelity, Hartford
2025), directionally consistent across all OOS windows, but statistically
marginal (p=0.41, CI includes zero). Retained because: (a) mechanism
story is well-cited industry research, (b) OOS hit% is >= 60% in every
window tested, (c) downside is bounded -- replaces QQQ with XLP only in
the specific ~5-8% +-+ state, (d) sleeve impact is ~+0.04 Sh on 60/40
blend (real but small). Treat as low-conviction tail-shaping, not a
proven alpha source.

## Bottom line (full spec)

**Production deployment: 70% CPM defensive sleeve + 30% BULL-QQQ bull sleeve.**

CPM engine spec: 11 risky ETFs, `TOP_K_CANDIDATES=6`, `HOLD_BUFFER=2.5z`,
**HYG+TIP+GLD "any positive" 13612U canary**, vol-target 10% (de-risk only,
no leverage), 10 bps/side cost, SHV-only cash fallback. BULL-QQQ spec:
composite trend (12-1 momentum OR 13612U > 0) AND multi-canary
(HYG/LQD/TIP any-positive 13612U); bull asset is XLP in HYG-/LQD-/TIP+
state, QQQ elsewhere; SHV cash when filters fail.

| Metric (LIVE 18y, post-cost) | CPM only | BULL-QQQ only | **70/30 PROD** |
|---|---:|---:|---:|
| **Sharpe** | 1.34 | 1.26 | **1.56** |
| CAGR | 13.48% | 23.15% | **16.63%** |
| MaxDD | -9.74% | -28.56% | **-12.29%** |
| Vol | 9.48% | 16.99% | **9.66%** |

Production blend improves on CPM alone: +0.22 Sharpe (1.56 vs 1.34),
+3.15pp CAGR (16.63% vs 13.48%), with marginally wider DD (-12.3% vs
-10.8%). The 30% bull sleeve adds Nasdaq-100 upside in regime-on months
and sits in cash during regime stress.

CPM canary fires defensive when none of HYG/TIP/GLD has positive 13612U
momentum -- ~15% defensive on the live window. BULL-QQQ uses the same canary
plus QQQ 12-1 momentum > 0; sleeve is in cash ~29% of months. The two filters
catch different bear types: canary catches credit/inflation stress (2022);
12-1 momentum catches sustained equity bears (dot-com). Suitable for personal
capital with crisis-tolerant time horizon.

Two windows trade history length against data quality:
- **Live-only 18y** (2008-09 to today): primary headline window. Every risky
  ETF is live throughout this window (post-prune of zombies + proxy-heavy
  names). No SPY-proxy contamination.
- **Extended 28.7y** (1997-08 to today): longest history but heaviest
  proxying. Uses Vanguard mutual-fund proxies pre-ETF-inception (see Data
  lineage section).

vs SPY buy-hold over the same live window: SPY Sharpe 0.70, MaxDD -55%.
Production blend cuts drawdown ~5x with substantially better risk-adjusted return.

### Production blend

70/30 CPM-BULL: Sharpe 1.48, CAGR 14.25%, MaxDD -12.3% (live 18y).
Sensitivity grid (oracle-v3): Sharpe-optimal blend across LIVE/EXT/TEST OOS,
flat surface 60/40-80/20.

Bootstrap CI on the live window is wide (95% CI on Sharpe is [0.86, 1.71]),
not statistically distinguishable from CPM standalone within 95% bounds.
Honest forward base-case Sharpe expectation: 0.80-1.10.

## What it does

Production is a two-sleeve TAA strategy:

**CPM sleeve (70%)** selects two ETFs each month from a curated
11-asset universe (US factors + international + gold + long bond), weighted
50/50, with a canary risk-gate, defensive cash rotation when conditions warrant,
and 10% volatility targeting (de-risk only, no leverage).

**BULL-QQQ sleeve (30%)** holds equity when composite trend (QQQ 12-1
momentum > 0 OR QQQ 13612U > 0) passes AND either: (a) macro canary fires
risk-on (HYG OR LQD OR TIP 13612U > 0), OR (b) equity-strength override
fires (QQQ 12-month return > top tercile of expanding-window historical
distribution, Asness-style, truly OOS-calibrated).

Bull asset depends on canary state: 100% XLP (consumer staples) in `+-+`
state (HYG-, LQD-, TIP+; late-cycle inflation regime), else 100% QQQ.
Otherwise 100% SHV cash.

The combined strategy is a hybrid of:
- Antonacci 12-1 absolute momentum (BULL-QQQ per-asset filter)
- Faber 10-month SMA distance (CPM cross-sectional ranker)
- Min-variance pair selection (CPM sleeve)
- Keller HAA-style canary regime gating (CPM: 3-asset HYG+TIP+GLD any-positive 13612U; BULL: 3-asset HYG+LQD+TIP any-positive 13612U)
- AQR/Moskowitz vol targeting on CPM sleeve (de-risk only, no leverage)

## Strategy spec

### Universe (CPM sleeve)

**Risky (11 ETFs):**
- 7 US equity ETFs (factor + sector mix): QQQ, IGM, XLE, VBR, SPHQ, XMHQ, XLV
- International (2): VEA (developed ex-US), VWO (emerging markets)
- Diversifiers (2): GLD, TLT

The universe was selected via systematic drop-impact testing on a broader
candidate pool. Kept names showed positive net Sharpe contribution on this
same data window. All assets require $1B+ AUM and $20M+ ADV for liquid
execution. International (VEA, VWO) added as regime hedge for periods when
US factor leadership wanes.

**Universe-selection contamination flag:** universe was finalized using
in-sample sweep results, with the constraint that all 11 ETFs must be live
throughout the post-2008 backtest (no SPY-proxy contamination).
`TOP_K_CANDIDATES = ceil(11/2) = 6` selects the top half of momentum-ranked
candidates. Treat the universe as in-sample best-of-tested under the live-
data constraint, not as evidence of forward edge.

**Safe pool:** SHV only (short-treasury cash, ultra-short Treasury, ~0.3y effective duration). Earlier
best-of [BIL/SHV/SHY/IEF] rotation captured ~0.03 Sh of rotation alpha but
added operational complexity + IEF duration ambiguity; simplified to SHV-only
to match BULL-QQQ cash fallback and eliminate oracle-v4 "duration leak" worry.

**Canary assets (CPM):** HYG (stitched: VWEHX pre-2007-04 + live HYG), TIP, GLD

### Engine

Each month at month-end close (T):

1. **Canary check** - compute Keller 13612U on HYG (high-yield credit) and
   TIP (inflation-linked bonds). Risk-on if EITHER is positive (`any_positive`
   rule, `CANARY_RULE` in `cpm_live.py`). Defensive (100% best safe) only when
   BOTH are negative simultaneously. Pre-2007 HYG uses VWEHX (Vanguard
   High-Yield Corp Fund) as proxy; monthly correlation with live HYG is 0.91.
2. **Faber SMA10m ranker** - for each universe asset compute
   `(price - 10mo SMA) / 10mo SMA`. Monthly distance above SMA.
3. **Top-half + positive momentum filter** - sort by SMA distance. Take top
   half. Drop any with negative momentum.
4. **Min-variance pair selection** - from positive-momentum candidates, pick
   the 50/50 pair with lowest portfolio variance (full covariance, not just
   correlation) over the trailing 378 trading days (1.5y). Variance-based
   selection picks pairs that are both diversified AND individually low-vol;
   empirically +0.07 Sharpe over pure lowest-correlation selection.
5. **Hold buffer** - keep prior month's pair members unless new candidate
   exceeds prior's z-score by **2.5 z-units** (cross-section). Reduces churn.
6. **Partial-safe fill** - if only 1 positive momentum, allocate 50% to that
   asset + 50% best safe. If 0 positive, 100% best safe.
7. **Pair weighting** - 50/50 between the two selected names.
8. **Vol targeting overlay** - scale daily returns to 10% annualized vol using
   63-day realized vol, **MAX_LEVERAGE = 1.0 (no borrowing)**, shifted 1 day
   to avoid look-ahead. De-risks only - never leverages above 100% gross.

### Execution

- **Signal computed at month-end close (T)** - frozen, no intramonth refresh.
- **Trade at MOC of T+1** - next trading day.
- Single tranche per month. ~13 unique ETFs total when running the 70/30 blend
  (11 CPM risky + SHV cash + QQQ + XLP, with QQQ shared between
  sleeves and SHV shared with CPM safe pool).

### BULL-QQQ sleeve (30% bull capture)

**Bull universe:** `QQQ` (default Nasdaq-100) + `XLP` (consumer staples,
used in HYG-/LQD-/TIP+ canary state for late-cycle inflation regime).

QQQ is highly liquid and diversified across index constituents but
economically concentrated in Nasdaq-listed large-cap growth leadership.
Forward CAGR expectations should be discounted vs the LIVE-18y window,
which coincided with the longest sustained Nasdaq bull regime in modern
history plus the AI rally.

**Decision rule (BOTH must pass for equity exposure):**

1. **Macro canary (3-asset "any positive" 13612U):**
   - HYG (high-yield credit) OR LQD (investment-grade credit) OR TIP
     (inflation-linked bonds) > 0 13612U momentum
   - Catches credit/inflation regime stress
   - 3-asset OR rule validated by canary state matrix analysis (see
     `research/canary_state_rotation_notes.md`): all-negative state has
     mean fwd QQQ -0.65%, lone-positive states (HYG, LQD, or TIP) all
     have positive expected returns

2. **QQQ composite trend filter (any positive):**
   - 12-1 absolute momentum > 0 (Antonacci dual momentum) -- SLOW anchor,
     anti-whipsaw in sustained bears like dot-com
   - OR 13612U > 0 (Keller HAA-style weighted momentum) -- FAST signal,
     catches re-entry quickly after bears (caught 2023 AI rally in Feb
     vs 12-1-alone waiting until June)
   - Disjunction: long if EITHER signal positive -- slow anchors against
     whipsaw, fast rescues re-entry timing

**Bull asset depends on canary state (HYG/LQD/TIP sign pattern):**
- HYG-/LQD-/TIP+: hold **XLP** (consumer staples)
   * Late-cycle inflation regime: real yields rising, credit weakening
   * Defensive cash-flow sectors lead; tech (QQQ) lags due to duration sensitivity
   * **Mechanism family validated OOS** (XLP/XLV/XLU/SPY/DVY/NOBL/SCHD all
     beat QQQ-no-switch in TEST window 2017-2026). Specific XLP choice
     within family is bootstrap-noise distinguishable from alternatives
     (all within ~0.02 Sh across windows).
   * **XLP chosen over basket** for: (a) longest defensive ETF history
     (1998), (b) zero within-basket rebalancing cost, (c) operational
     simplicity (1 ticker), (d) tied-best Sharpe across LIVE FULL / TEST
     OOS / EXT 32y windows after switching costs.
   * **Small-sample caveat: n=14 LIVE state observations (8.6%), n=21
     EXT (5.4%). Treat as mechanism-backed regime substitution, not as
     a statistically distinguishable XLP-specific edge vs alternatives.**
- All other bull states: hold **QQQ** (default tech)

**Fallback:** 100% SHV (short-treasury cash) when either filter fails.
SHV chosen over IEF for cleaner defense -- ultra-short Treasury (~0.3y effective duration) on this sleeve.

**Filter design rationale:** 12-1 absolute momentum was selected over Faber
10mo SMA after empirical comparison (see `research/monthly_qqq_signals.md`).
Key findings:
- 12-1 momentum stays negative throughout sustained bear markets, avoiding
  whipsaws. SMA-based filters (Faber 10mo) bounced in/out during dot-com.
- Strongest academic backing (Antonacci dual momentum, Moskowitz TSMOM 2012).

**Why canary AND momentum (not just one):** filter ablation tests showed
canary+mom has +54% Martin Ratio over mom-only at small CAGR cost
(~1.5-2pp). Same Sharpe but materially less sustained pain.

**Standalone metrics (live-18y, post-cost):**
Sharpe 1.12, CAGR 19.97%, Vol 17.2%, MaxDD -28.56%.
(BULL-QQQ standalone is path-risky as single-asset bet; the 70/30 blend
is the production deployment.)

**Why it pairs with CPM:** the 70% CPM sleeve provides defensive alpha;
pairing it with a 30% bull-tilted sleeve adds Nasdaq-100 upside without
duplicating defensive picks. Blend math: 70% CPM + 30% BULL-QQQ lifts
Sharpe to 1.48 (vs 1.26 CPM alone) and CAGR to 14.25% (vs 12.12%) with
narrower DD (-12.3% vs -13.5%). Sensitivity grid: 70/30 is Sharpe-optimal
on both LIVE and EXT windows; surface flat 60/40-80/20.

**Why the blend math holds: regime-conditional correlation (LIVE):**

| Regime | n | CPM-BULL correlation |
|---|---:|---:|
| Overall | 221 | 0.23 |
| SPY risk-on (12-1 > 0) | 182 | 0.25 |
| SPY risk-off (12-1 < 0) | 39 | 0.09 |
| **SPY bear (DD < -20%)** | 17 | **-0.13** |

Diversification gets STRONGER in bears, not weaker. Bear-state negative
correlation is what makes the blend Sharpe lift real, not just a backtest
artifact of two equity-heavy sleeves.

**Known structural tail: V-shaped recoveries and fast crashes.** COVID
2020 is the calibration point: SPY -9.2%, BULL -16.8% (canary slow to
go defensive on a V-shaped intramonth crash), but blend held to -1.6%
because CPM absorbed it. Both sleeves share the canary-based defense lag
by design -- calibrated for sustained stress, not intramonth shocks.
Document as known tail, not a spec defect.

**Rejected BULL-QQQ variants:**
- Multi-ETF bull universe (SMH/SCHG/XLK/IWM/GLD/etc): no Sharpe benefit, more
  rotation noise; QQQ already provides diversified mega-cap tech exposure.
- VIX < 30 filter: gave ~0.05 Sharpe cost both windows; only catches COVID
  flash crash (n=1 evidence); marginal in blend.
- Vol-targeting (10-20% target): cleaner MaxDD but minimal avg-rolling-DD
  improvement; trades 1-3pp CAGR for tail protection on max DD only.
- Faber 10mo SMA eligibility filter: worse extended-window robustness.
- 12-1 alone (without 13612W OR disjunction): missed 2023 AI rally (only
  +3.8% capture vs +22.4% with composite trend).
- IHF rotation in `+-+`: highest raw Sharpe but Ulcer collapses on outlier
  removal (UNH-cycle concentration risk); XLP chosen for robustness.
- `--+` -> VBR/VNQ rotation: N=18 too small for deployment, parked as
  research; see `research/canary_state_rotation_notes.md`.
- XLE-rotation kill switch: threshold monotonicity passes but episode test
  fails (12 of 30 firings in 2022 alone); parked pending more episodes.
- Top-K momentum-weighted from multi-ETF universe: concentrates on highest vol, hurts Sharpe.
- 13612U (unweighted) eligibility filter: marginal differences.
- Daily EMA 50/200 golden cross: essentially tied, more complex.
- Keller 13612U as STANDALONE trend signal: designed for breadth, not
  single-asset; Sh 0.76 worst on QQQ timing in isolation. Used in disjunction
  with 12-1 (this design) it adds real value via fast re-entry.
- EMA(50/200) MONTHLY: math error (50 months / 200 months filter, useless).
- IEF fallback (intermediate bonds): +0.02 Sharpe but adds duration risk.
- CPM fallback: +0.85pp CAGR but worse Martin Ratio on extended; alpha duplicated with the 80% CPM sleeve.

### Cost assumption

10 bps per side per turnover. Mean monthly turnover ~60%, annual cost drag
~1.4%/yr (built into headline numbers).

## How it differs from peers

Faithfully-reproduced peer Sharpes (same data, same 10 bps/side cost, same
live-only window as CPM). Published "paper" Sharpes are excluded because
they use different windows, often zero-cost assumptions, and were overstated
by 0.10-0.95 vs faithful reproduction (e.g. VAA-G4 paper 1.44 vs reproduced
0.49). See `research/peer_strategy_faithful_reproduction.log` for engine
rules and assumptions.

| Strategy | Universe | Engine | Sh | CAGR | DD | Window |
|---|---|---|---:|---:|---:|---|
| Faber GTAA5 | Faber-5 | Faber | 0.50 | 5.8% | -25.4% | 17.6y |
| Antonacci GEM | GEM-3 | GEM | 0.54 | 7.9% | -33.7% | 17.6y |
| Keller VAA-G4 | VAA-7 | VAA | 0.49 | 6.0% | -27.8% | 17.6y |
| Keller HAA-Bal | HAA-Bal | HAA | 0.93 | 9.1% | -15.5% | 13.1y |
| ReSolve AAA (RDMIX) | live fund | live, net of 0.95% fee | 0.48 | 4.9% | -21.9% | 8.2y |
| **CPM standalone** | CPM-11 | CPM | **1.34** | 13.48% | -10.8% | 18y |
| **CPM + 30% BULL-QQQ (PROD 70/30)** | CPM-11 + QQQ | CPM+regime-bull | **1.56** | **16.63%** | **-12.29%** | 18y |
| **Naive 70/30 PP/QQQ-trend** | 25/25/25/25 + 10mo SMA | passive + Faber | 1.01 | 8.4% | -14.9% | 18y |

**Window-aligned CPM edge vs best fair peer**: CPM on the HAA window
(2013-04-18 to today, 13.1y) gives Sharpe 1.204. HAA gives 0.933. Same
window, same data, same cost: **+0.27 Sharpe edge**. Other peer engines
underperform by larger margins (+0.66 to +0.71 vs CPM), so HAA is the most
competitive fair benchmark.

**CPM has both engine and universe alpha, not just co-tuning**:
- CPM engine on peer universes beats peer engines on the same universes by
  +0.14 to +0.22 Sharpe (HAA engine is parity)
- CPM universe on peer engines beats peer universes on the same engines
  by +0.05 to +0.40 Sharpe
- Both components contribute independent edge

**Apples-to-apples 2-sleeve benchmark (dashboard primary comparison):**

| Strategy | Sh | CAGR | MaxDD |
|---|---:|---:|---:|
| **PROD 70/30 CPM-BULL** | **1.56** | **16.63%** | **-12.3%** |
| Naive 70/30 PP / QQQ-trend | 1.01 | 8.4% | -14.9% |
| QQQ buy-hold (raw target) | 0.86 | 18.66% | -50.0% (LIVE) |

The naive 70/30 PP/QQQ-trend benchmark uses identical 2-sleeve architecture
(70% defensive + 30% QQQ-timing) but with off-the-shelf components:
Permanent Portfolio (25/25/25/25 SPY/IEF/GLD/SHV) for the defensive sleeve,
Faber 10mo SMA on QQQ for the timing sleeve. **Net design value-add: +0.49
Sharpe / +7.0pp CAGR over a thoughtful but simpler implementation of the
same meta-architecture.**

Dashboard charts compare PROD against just these 2 benchmarks (naive
counterfactual + raw target) for clean apples-to-apples context.

## Component-by-component research backing

### Foundational (peer-reviewed)

- **Time-series momentum** - Moskowitz, Ooi, Pedersen (2012) JFE. 12-month
  trend signal works on 58 futures markets across 25 years.
- **Cross-sectional momentum** - Jegadeesh & Titman (1993) JoF. Buying winners,
  selling losers.
- **Vol targeting** - Moskowitz et al (2012) and AQR research. Scaling to
  target vol improves Sharpe across most TAA strategies.

### Practitioner-validated (SSRN, books)

- **Faber 10-month SMA** - Faber (2007 SSRN, 2009 book). Mainstream tactical
  filter, 30k+ downloads.
- **Antonacci dual momentum** - Antonacci (2012 CFA, 2014 book). Combines
  absolute and relative momentum.
- **Keller VAA/HAA** - Keller & Keuning (2017, 2023 SSRN). Canary-based regime
  classification.
- **Keller 13612U signal** - `(12r1 + 4r3 + 2r6 + r12)/19`. Recent-month-weighted
  momentum, designed for risk gates not asset selection.
- **Best-of-safes rotation** - Keller HAA (2023) uses momentum-rotated safe basket.

### Lit-adjacent / practitioner

- **Lowest-correlation pair selection** - Optimum3 (Tresidder/AllocateSmartly 2022)
  uses Varadi minimum-correlation idea on top-half momentum candidates.
  Conceptually adjacent to Choueifaty & Coignard (2008) Most Diversified Portfolio.
- **Hold buffer for churn dampening** - practitioner standard, AQR research
  notes mention turnover-aware momentum.
- **EMA(50/200) golden cross trend filter** - Edwards/Magee (1948) classic
  trend-following primitive; AQR/Faber (2007) confirm trend-filter Sharpe
  improvements vs buy-hold across global markets.

### Credit-stress regime sector rotation (BULL-QQQ +-+ rule)

The HYG-/LQD-/TIP+ state -> XLP defensive substitution rule has
strong mechanism backing in academic and industry literature, though
the specific multi-canary + sector-switch combination is novel.

**Direct mechanism evidence:**

- **Neuberger Berman (Feb 2024)** - "The Importance of Monitoring Credit
  Spreads In Positioning Equity Portfolios" (Hanafy/Wennett). Examined 6
  episodes since 2000 where Baa credit spreads widened from bottom-10%
  extremes. Finding: "cyclical sectors performed the worst -- Industrials,
  Consumer Discretionary, Materials -- whereas defensive sectors --
  Consumer Staples, Utilities, Healthcare -- held up the best". Directly
  validates the credit-stress -> defensive-sector mechanism.

- **Hartford Funds / Schroders (2025)** - sector performance under
  high+rising inflation (1973-2025). Consumer staples "performed
  comparatively better, as their cash flows tend to be concentrated in
  the shorter term". Tech (IT): "the bulk of cash flows are expected
  in the distant future, which may be worth far less when inflation
  increases". Validates TIP+ (real-rate sensitivity) -> tech-underperform
  mechanism via cash-flow-duration argument.

- **Fidelity Business Cycle Update** (2016, recurring). Late-cycle phase:
  defensives + energy lead, tech lags. Recession: "consumer staples sector
  has a perfect track record of outperforming the broader market
  throughout the entire recession phase". Sector-cycle rotation framework
  matches our +-+ -> XLP regime detection.

- **S&P Dow Jones (2024)** - factor index performance across macro regimes.
  Quality factor "consistently outperformed the S&P 500 in Falling Growth"
  regardless of inflation. Validates quality+defensive-equity tilt in
  credit-stress regimes.

**Academic foundations (credit-spread regime detection):**

- **Collin-Dufresne, Goldstein, Martin** - "Pricing of Credit Spreads".
  Credit spread changes for HY bonds explained ~67% by equity-related
  factors. High-yield (HYG) credit spreads = equity-stress proxy.
- **Gilchrist & Zakrajsek (GZ spread)** - excess bond premium has
  predictive power for real economy, leads investment cycle 2-4 quarters.

**Closest published strategy (TIP canary):**

- **Keller & Keuning (2022) "Hybrid Asset Allocation"** - SSRN 4346906.
  Uses TIP as single-asset canary + 13612U canonical momentum. When TIP
  momentum negative -> defensive (IEF/BIL). This IS the core mechanism
  we use; our extension is multi-canary (HYG+LQD+TIP "any positive") +
  state-conditional sector switch (XLP in -/-/+).

**Why the specific +-+ -> XLP rule is not in published literature:**

1. Academic momentum/canary papers operate at asset-class level (equity/
   bond/safe), not sector level
2. Most retail-facing TAA strategies (HAA, GEM, DAA) use single-canary
   rules, not multi-canary state interactions
3. Industry research describes the regime tilts qualitatively (Neuberger,
   Fidelity, Hartford) but rarely publishes ETF-specific rule books
4. Sector-state interactions like HYG-/LQD-/TIP+ -> XLP only become
   tractable when you discretize multi-canary signals into states --
   that's a recent quant-friendly framing

The spec is therefore a **novel combination of well-documented components**:
TIP canary (Keller HAA) + multi-asset stress detection (DAA-style) +
state-conditional defensive sector rotation (Neuberger Berman + Fidelity
business-cycle framework) + TSMOM/13612U composite trend filter.


### Bespoke / data-driven

- **11-asset universe (US factor + sector + intl + diversifier)** - curated for sector/asset-class diversity
  (size, value, quality, momentum, energy, retail, healthcare). Each
  constituent passes drop-impact test and liquidity threshold.
- **International additions (VEA, VWO)** - regime hedge for non-US-led periods.
- **GLD as universe diversifier** - adds Sharpe across all windows.
- **TLT in universe** - long-bond exposure for crisis pair-up with equity defensives.
- **Hyperparameters (buffer 2.5z, corr lookback 378d)** - selected by
  walk-forward hyperparameter testing across OOS slices.

## Decomposition: where the alpha comes from

Component contributions (additive vs SPY baseline). Each row is a component
in the deployed strategy.

| Component | Delta Sharpe |
|---|---:|
| SPY baseline | 0.58 |
| Curated 11-asset universe (factor + sector + intl + diversifier) | +0.26 |
| Min-variance pair selection (378d lookback) | +0.18 |
| Hold buffer 2.5z | +0.04 |
| Best-safe rotation (BIL/SHV/SHY/IEF) | +0.03 (removed in oracle-v4, simplified to SHV-only) |
| HYG+TIP+GLD "any+" 13612U canary | +0.18 |
| Partial-safe fill (1 positive momentum) | +0.02 |
| Vol targeting overlay (10% annual, no leverage) | +0.02 |
| Frozen-EOM signal + T+1 MOC execution | -0.01 |
| 10bps cost drag | -0.06 |
| **Total CPM standalone** | **1.20** |
| **+ 30% BULL-QQQ bull sleeve (70/30 PROD)** | **+0.22 -> 1.48, +2.13pp CAGR, narrower DD** |

## Validation hygiene

### What was tested

- **Walk-forward rule-freeze validation** (see
  `research/walk_forward_rule_freeze.log`): tested current spec at 6 freeze
  years. Mean OOS Sharpe 1.256 vs IS Sharpe 1.148. All 6 freezes show OOS-IS
  gap within bootstrap noise (none statistically significant). DD identical
  -10.7% across all freezes. Caveat: at freeze=2014, an older universe
  variant beats current spec OOS by +0.05 Sharpe (1.205 vs 1.151). Recent
  universe tuning is roughly neutral OOS, not a clear improvement.
- **Hyperparameter robustness** (walk-forward across 5 OOS slices): selected
  config wins on 4/5 slices.
- **Bootstrap CI on Sharpe** (B=2000, 21-day blocks): CPM standalone Sh 1.20,
  95% CI [0.78, 1.63]. 60/40 blend Sh 1.24, 95% CI ~[0.80, 1.65]. CIs are wide.
- **Head-to-head vs live ReSolve AAA fund (RDMIX)** (see
  `research/fcp_vs_resolve_live.log`): 2018-03 to 2026-05 (8.2y, aligned with
  RDMIX inception). CPM gross Sh 1.31 / CAGR 11.6% / MaxDD -10.7% vs RDMIX
  Sh 0.48 / CAGR 4.9% / MaxDD -21.9%. Bootstrap difference test: CPM-gross
  beats RDMIX by +0.82 Sharpe at 95% significance. CPM-net (with -1%/y fee
  drag) still beats by +0.71 Sh (just below 95%). CPM and RDMIX correlation
  only 0.22. Caveat: CPM universe finalized with hindsight, so RDMIX
  comparison contains selection bias.
- **Regime / crisis attribution** (see `research/fcp_regime_attribution.log`):
  8/8 crisis windows show CPM positive alpha vs SPY (mean +21.5pp). 3/3
  sustained bull rallies show CPM underperforms SPY (mean -28.6pp). Regime
  buckets: CPM wins risk-off (Sh +0.54 vs SPY -0.80) and high-vol (Sh +1.03
  vs +0.47), loses risk-on by small gap (Sh +2.29 vs +2.65). Top defensive
  pairs: TLT+XLV, GLD+TLT, SPHQ+TLT. Top bull pairs: GLD+SPHQ, IGM+XMHQ.
  Strategy gives up bull upside in exchange for crisis alpha as designed
  (`MAX_LEVERAGE=1.0` prevents bull leverage).
- **Cost sensitivity**: at 10bps/side strategy survives (built into headline);
  at 25bps Sharpe drops to ~0.85.
- **Year-by-year contribution** (2001-2026, 25 years vs SPY): cumulative
  arithmetic excess +25.1pp. Crisis years (2002, 2008, 2018, 2020, 2022)
  contribute +128.4pp = 5x total excess. Top 4 single years: 2008 (+45.8pp),
  2002 (+32.8pp), 2020 (+17.6pp), 2022 (+17.2pp).

### Validation vs critique (BULL-QQQ sleeve)

See `research/oracle_v2_validation_2026.log` for full output.

**QQQ trend-state matrix (full QQQ history 1996-2026, 364 month-ends):**

| 12-1 | 13612W | Months | Fwd QQQ mean | Hit% |
|:---:|:---:|---:|---:|---:|
| + | + | 250 | +1.46% | 62.0% |
| + | - | 50 | +2.81% | 58.0% |
| - | + | 19 | +2.18% | 63.2% |
| **-** | **-** | **45** | **-1.16%** | **53.3%** |

OR-rule justified: all three "any-positive" states have positive forward
mean; only --/-- state is negative. Validates composite trend (12-1 OR
13612W) over either signal alone.

**Canary 8-state matrix (LIVE 18y, HYG/LQD/TIP signs, n=217):**

| State | n | QQQ fwd | XLP fwd | XLP-QQQ |
|:---:|---:|---:|---:|---:|
| HYG+/LQD+/TIP+ | 121 | +1.86% | +0.83% | -1.03% |
| HYG+/LQD+/TIP- | 14 | +1.00% | +0.32% | -0.68% |
| HYG+/LQD-/TIP+ | 14 | +0.40% | +1.30% | +0.91% |
| HYG+/LQD-/TIP- | 16 | +1.95% | +0.34% | -1.61% |
| HYG-/LQD+/TIP+ | 10 | +1.95% | +0.86% | -1.09% |
| HYG-/LQD+/TIP- | 4 | +1.36% | +1.68% | +0.32% |
| HYG-/LQD-/TIP+ | 9 | +0.41% | +2.15% | +1.73% |
| HYG-/LQD-/TIP- | 29 | +0.55% | +0.36% | -0.19% |

XLP edge concentrated in two states (+/-/+ and -/-/+). Current spec only
switches on +/-/+ (the state where canary still fires as "any-positive"
and bull sleeve eligible); -/-/+ has stronger XLP edge but goes to cash
regardless because canary natural-state is risk-off.

**Canary-rule ablation (LIVE 18y, BULL standalone):**

| Rule | Sharpe | CAGR | Notes |
|---|---:|---:|---|
| **HYG/LQD/TIP any (PROD)** | **0.97** | **17.03%** | best |
| HYG/LQD/TIP >= 2 of 3 | 0.81 | 13.60% | too restrictive |
| HYG/LQD/TIP all | 0.74 | 11.55% | too restrictive |
| HYG+TIP any (prev) | 0.93 | 16.09% | LQD adds +0.04 Sh |
| HYG only | 0.82 | 13.39% | misses LQD/TIP signal |
| TIP only | 0.87 | 14.64% | inflation-only |
| LQD only | 0.85 | 14.06% | IG-credit-only |
| No macro (override only) | 0.38 | 4.50% | gate matters |

3-asset any-positive rule is best. LQD addition over 2-asset HYG+TIP
adds +0.04 Sharpe in LIVE. Rule is intentionally permissive: exits only
when ALL three credit/real-rate signals are non-positive (broad-stress
detector, not equity-correction detector).

**XLP-substitution ablation (production module with switching costs):**

| Asset in HYG-/LQD-/TIP+ | LIVE FULL Sh | TRAIN Sh | **TEST OOS Sh** | EXT 32y Sh |
|---|---:|---:|---:|---:|
| **XLP only (PROD)** | **1.430** | 1.270 | **1.531** | **1.222** |
| XLV only | 1.410 | **1.316** | 1.454 | 1.210 |
| XLU only | 1.406 | 1.182 | 1.564 | 1.197 |
| XLP/XLV 50/50 basket | 1.423 | 1.296 | 1.495 | 1.217 |
| XLP/XLU 50/50 basket | 1.421 | 1.228 | 1.551 | 1.211 |
| XLP/XLV/XLU 1/3 basket | 1.420 | 1.260 | 1.522 | 1.212 |
| QQQ (no switch) | 1.352 | 1.231 | 1.418 | 1.181 |

Mechanism family validated OOS (all defensive variants beat QQQ-no-switch
on TEST). TRAIN winner (XLV @ 1.316) did NOT generalize -- ranked 4th
on TEST -- classic single-asset overfit. XLP-only is consistently top-3
across all windows and wins LIVE FULL / TEST OOS (tied) / EXT 32y.

Broader defensive/dividend ETFs also tested (SCHD/NOBL/VIG/DGRO/USMV/SPLV/
VYM/DVY/HDV/RSP) on common 2014+ window: all cluster within 0.02 Sh of
XLP, no single ETF materially better. See `research/oracle_v2_validation_2026.log`.

**Dot-com stress (1999-2003, 60/40 PROD via production module):**

| Year | SPY | QQQ | CPM | BULL | 60/40 |
|---|---:|---:|---:|---:|---:|
| 1999 | +20.4% | +98.7% | +9.9% | +98.7% | +40.9% |
| 2000 | -9.7% | -36.1% | +4.4% | -16.3% | -2.2% |
| 2001 | -11.8% | -33.3% | -4.8% | +19.9% | +4.8% |
| 2002 | -21.6% | -37.4% | +4.7% | +4.9% | +5.0% |
| 2003 | +28.2% | +49.7% | +24.9% | +44.2% | +33.0% |

QQQ trend filter held through the most important Nasdaq stress period.
60/40 blend negative only in 2000; positive in 2001-2003 while SPY/QQQ
bled. Validates that the OR trend rule survives a sustained Nasdaq bear,
not just post-GFC corrections.

**EXT 32y blend performance (1994-2026, includes dot-com):**

| | Sharpe | CAGR | MaxDD | Ulcer |
|---|---:|---:|---:|---:|
| CPM standalone EXT | 1.09 | 10.24% | -14.2% | 4.35% |
| BULL-QQQ standalone EXT | 0.91 | 17.71% | -41.1% | 10.65% |
| **60/40 PROD EXT** | **1.22** | **13.63%** | **-18.4%** | **4.67%** |
| SPY buy-hold EXT | 0.57 | 10.50% | -55.2% | 14.72% |

EXT confirms blend adds value across regimes including dot-com, but
DD widens to -18.4% (vs -13.85% LIVE) -- larger drawdown is the honest
forward expectation, not the LIVE number.

### Deflated/Probabilistic Sharpe (oracle-v4 robustness)

Bailey & Lopez de Prado (2012) PSR/DSR framework: tests whether observed
Sharpe survives multiple-testing data-mining haircut.

**PROD 70/30 spec:**

| Window | SR | PSR(>0) | PSR(>0.5) | PSR(>1.0) | DSR (N=1000 trials) |
|---|---:|---:|---:|---:|---:|
| LIVE 18y | 1.41 | 100% | 100% | **95.7%** | **99.7%** |
| TEST OOS 2017-26 | 1.56 | 100% | 99.9% | 95.3% | 93.4% |
| EXT 32y | 1.22 | 100% | 100% | 89.6% | 100% |

**CPM standalone:**

| Window | SR | DSR (N=1000) |
|---|---:|---:|
| LIVE 18y | 1.21 | 97.5% |
| EXT 32y | 1.09 | 99.9% |

Interpretation: even with aggressive N=1000 trial-count multiple-testing
haircut (this session tested ~200-300 variants; N=1000 is conservative),
DSR shows 93-100% confidence that true Sharpe exceeds the data-mining
null expected-max. PSR(>1.0) = 89-96% supports institutional-grade
risk-adjusted return claim. Strategy is statistically robust against
data-mining concerns.

### What was NOT tested

- **Forward live performance** - strategy never traded live capital.
- **Smaller account constraints** - fractional ETF shares, $5K minimums per
  position assumed.

### Honest caveats

1. **In-sample selection bias.** Hyperparameters and universe selected after
   seeing this data. Forward Sharpe base case 0.80-1.10 for CPM standalone
   (point estimate 1.20 but bootstrap CI [0.78, 1.63]; walk-forward shows
   recent tuning is OOS-neutral, not a clear improvement). DSR (deflated
   Sharpe with N=1000 trials) shows 97.5%+ probability the edge is real.
   Override threshold pre-2005 was unstable (thin QQQ history); now removed
   in oracle-v4 cleanup.
2. **Universe risk.** Factor universe curated via drop-impact testing on this
   same window. Pre-2015 factor leadership was different.
3. **Stitched proxies degrade quality pre-2010.** XMHQ and SPHQ use MDY/SPY
   proxies pre-2005 inception (affects only the Extended-28y window; live-18y
   window is proxy-free).
4. **Strategy lags during V-shaped recoveries** (verified): 2009 -10.8pp
   vs SPY full-year (canary slow to re-engage from 2008 defensive); 2020-Q2
   -27.6pp vs SPY in the snap-back. Acceptable cost for crisis protection,
   but real - strategy is structurally late at re-entering after deep selloffs.
5. **Bull-rally underperformance is structural.** `MAX_LEVERAGE=1.0` prevents
   the vol-target from levering up in low-vol bull runs. The strategy is
   designed to win risk-off and lose risk-on by a small margin.
6. **BULL-QQQ sleeve adds tail risk from QQQ timing.** Standalone BULL
   MaxDD -28.56% (LIVE) / -41.1% (EXT 32y). 60/40 blend caps total impact
   to MaxDD -13.85% LIVE / -18.4% EXT. COVID 2020 is the calibration
   tail: SPY -9.2%, BULL -16.8% (canary slow on V-shaped intramonth
   crash), blend held to -1.6% only because CPM absorbed it. Both sleeves
   share canary-based-defense lag by design -- calibrated for sustained
   stress, not intramonth shocks.
7. **BULL-QQQ standalone CAGR is QQQ-era driven.** LIVE-18y 20% CAGR
   coincided with the longest Nasdaq bull regime in history plus the AI
   rally. Forward CAGR anchor: ~7-10% (QQQ long-run ~8-10% x 84%
   risk-on exposure), not 18-20%. Risk-adjusted edge over QQQ buy-hold
   (+0.35 Sharpe, half the MaxDD) is the real forward edge.
8. **Tax wrapper required for tax-efficiency.** Monthly rebalance =
   short-term capital gains on all winners. **Use only in IRA / 401k /
   Roth / tax-deferred accounts** to capture full backtest CAGR. In
   taxable accounts, expect 2-4pp CAGR drag depending on marginal bracket
   (federal 22-37%, state 0-13%). After-tax forward CAGR in taxable
   context could drop to 4-7% (vs 8-12% pre-tax forward expectation).
9. **Total-return data dependency.** All momentum/vol calculations use
   `yfinance` auto_adjust=True (Adjusted Close, dividend-reinvested). If
   data source changes, must verify total-return semantics — using raw
   prices instead of total returns would underestimate momentum on
   high-yield assets (TLT, GLD, dividend ETFs).

## Implementation notes

### Monthly rebalance procedure

At T (last trading day of month, after close):
1. Pull data for all CPM universe + canary + safe assets
2. Compute monthly returns up to month-end T
3. Apply canary check (HYG+TIP+GLD 13612U, any-positive rule)
4. If canary off: target = 100% best safe
5. If canary on: run pair selection
6. Apply hold-buffer comparison vs prior month
7. Apply vol target sizing (63d realized vol, 10% annual target, max 1.0x - de-risk only, no leverage)
8. Generate trade list = (target weights x portfolio NAV) - (current positions)
9. Place MOC orders for trade list at T+1

### BULL-QQQ sleeve procedure (if blending)

Exact pseudocode:

```python
# All momentum signals computed at signal date T (last trading day of month)
mom_12_1_qqq = QQQ_close[T-1mo] / QQQ_close[T-13mo] - 1   # total-return adjusted

def mom_13612U(series):
    # Canonical HAA unweighted (Keller & Keuning 2022, U = Unweighted)
    # Simple average of 1/3/6/12-month total returns
    r1, r3, r6, r12 = returns over [1, 3, 6, 12] months
    return (r1 + r3 + r6 + r12) / 4

# 1. Trend filter (composite OR)
trend_ok = (mom_12_1_qqq > 0) or (mom_13612U(QQQ) > 0)

# 2. Macro canary (3-asset any-positive)
macro_on = (
    mom_13612U(HYG) > 0
    or mom_13612U(LQD) > 0
    or mom_13612U(TIP) > 0
)

# 3. Equity-strength override (truly OOS-calibrated)
historical_12mo_returns = [QQQ_close[t-1mo] / QQQ_close[t-13mo] - 1
                           for t in panel_history if t < T]
threshold_67th = percentile(historical_12mo_returns, 67)
override_active = mom_12_1_qqq > threshold_67th

# 4. Late-cycle inflation state (HYG-/LQD-/TIP+ pattern)
late_cycle_inflation = (
    mom_13612U(HYG) <= 0
    and mom_13612U(LQD) <= 0
    and mom_13612U(TIP) > 0
)

# 5. Decision
if trend_ok and (macro_on or override_active):
    target = "XLP" if late_cycle_inflation else "QQQ"
else:
    target = "SHV"

# 6. Execute at T+1 MOC, 10bps/side cost on any state change
```

Spec definitions:
- **12-1 momentum**: total return from T-13mo to T-1mo (excludes most
  recent month to avoid mean-reversion bias, per Jegadeesh-Titman / Antonacci)
- **13612U**: simple (unweighted) average of 1/3/6/12-month total returns
  per canonical HAA paper. Earlier this spec used weighted 13612W
  (12/4/2/1 weights / 19); oracle-v6 confirmed canonical 13612U is both
  +0.08 Sh better AND matches the actual Keller HAA paper. Function name
  `sig_13612W` retained for back-compat; alias `sig_13612U` available.
- **Total returns**: dividend-adjusted via yfinance Adj Close
- **Signal date**: month-end close T
- **Trade date**: T+1 MOC (next trading day at market-on-close)
- **Costs**: 10 bps per side (20 bps round-trip) on any state change
  including QQQ <-> XLP <-> SHV switches
- **Rebalance frequency**: monthly only, no intramonth updates
- **Canary state notation**: HYG/LQD/TIP signs in that order; e.g. -/-/+ means
  HYG- LQD- TIP+ (compact form: HYG-/LQD-/TIP+)

See BULL-QQQ sleeve section above for rationale and rejected variants.

### Total portfolio composition

For $X total capital, with chosen CPM weight w:
- $wX to CPM strategy (11 risky ETFs + SHV cash)
- $(1-w)X to BULL-QQQ bull sleeve (QQQ + SHV cash fallback)

w=1.0 -> pure CPM. w=0.8 -> max-Sharpe blend. w=0.7 -> moderate bull tilt.
w=0.7 -> 70/30 production default (oracle-v3 Sharpe-optimal).
w=0.6 -> 60/40 alternate (more bull-tilted, accepted wider DD for CAGR).

### Daily monitoring

- Vol-target overlay scales gross exposure based on 63d realized vol
- Canary determines monthly risk-on / risk-off

## Data lineage

Pre-inception data is stitched from mutual-fund / index proxies via the
`build_proxy_returns()` chain (see `artifacts/cpa-1997-exact-core-proxy-research/`).
Proxy/live splice happens at each ETF's first trading day.

| Pool | Asset | Live ETF inception | Proxy chain pre-inception |
|---|---|---|---|
| RISKY | QQQ | 1999-03-10 | `^NDX -> QQQ` |
| RISKY | IGM | 2001-03-13 | `FSPTX -> IGM` |
| RISKY | XLE | 1998-12-22 | `FSENX -> XLE` |
| RISKY | XLV | 1998-12-22 | (none - live throughout backtest) |
| RISKY | VBR | 2004-01-30 | (none - live only from 2004) |
| RISKY | SPHQ | 2005-12-09 | `SPY -> SPHQ` (SPY proxy 1995-2005) |
| RISKY | XMHQ | 2005-12-09 | `MDY -> XMHQ` (MDY proxy 1995-2005) |
| RISKY | VEA | 2007-07-20 | `VGTSX -> VEA` |
| RISKY | VWO | 2005-03-04 | `VEIEX -> VWO` |
| RISKY/PP | GLD | 2004-11-18 | (none - pre-2000-08 GLD excluded entirely) |
| RISKY | TLT | 2002-07-22 | `VUSTX -> TLT` |
| SAFE | BIL | 2007-05-25 | (none - live only from 2007) |
| SAFE/PP | SHV | 2007-01-05 | `VFISX -> SHV` |
| SAFE | SHY | 2002-07-22 | (none - live only from 2002) |
| SAFE/PP | IEF | 2002-07-22 | `VFITX -> IEF` |
| CANARY | SPY | 1993-01-29 | (none - live throughout) |
| CANARY | TIP | 2003-12-04 | `VFITX -> VIPSX -> TIP` |

**Honest caveats on data:**
- The 11-asset universe (incl. XLE, VBR, SPHQ, XMHQ, XLV) is bespoke. SPHQ and XMHQ
  use MDY/SPY proxies pre-2005 inception. This only affects the
  Extended-28y window pre-2005 quality-factor exposure.
- **Live-only 18y window** (2008-09 to today): every risky ETF is live
  throughout the window. No SPY-proxy contamination. This is the primary
  reportable backtest.

## Forward expectations

**Anchor real-world Sharpe to 0.80-1.10 base case for CPM standalone**, not
the backtest 1.20. Reasons:
- `HOLD_BUFFER=2.5z` was tuned on this window (see
  `research/hold_buffer_threshold_diagnosis.log`)
- Universe was sweep-validated on full window; walk-forward shows recent
  tuning is OOS-neutral, not a clear improvement
- Bootstrap CI 95% width spans ~0.85 Sharpe units (`[0.78, 1.63]`)
- Forward factor leadership likely differs from backtest era
- Pre-2015 backtest relies heavily on factor-ETF proxies; pre-2010
  performance is essentially proxy-driven, not factor-mechanism driven
- Live execution friction not perfectly modeled

**Target return profile (forward 5y, CPM standalone, base case):**
- CAGR: 6-10%
- Vol: 8-11%
- MaxDD: -12% to -22% (vs backtest -10.7%)
- Sharpe: 0.80-1.10

**Upside case** (regime/crisis response persists, factor leadership stable):
Sharpe up to 1.20, CAGR up to 10%, DD held near -12%. Treat upside as a
condition to verify in live data, not a default expectation.

**70/30 production blend forward expectation (heavily discounted):**
- CAGR: 8-12% (NOT the backtest 14.25%)
- Sharpe: 0.90-1.20 (NOT the backtest 1.48)
- MaxDD: -15% to -25% (closer to EXT 32y -18.4% than LIVE -13.85%)

The BULL-QQQ sleeve was selected after observing the post-GFC Nasdaq regime
and AI rally. The LIVE-18y 20% CAGR for BULL standalone is QQQ-era driven:
BULL spends ~75% time in QQQ, ~16% in cash, ~9% in XLP, so standalone CAGR
~= QQQ-long-run-CAGR x 0.84 exposure. With QQQ long-run real return ~8-10%,
BULL standalone forward CAGR expectation is **~7-10%, not 18-20%**. The
risk-adjusted edge over QQQ buy-hold (+0.35 Sharpe, half the MaxDD) is the
real forward edge; absolute level is not.

Forward BULL-QQQ standalone Sharpe expectation: 0.65-0.95. The 60/40
weighting captures most of the diversification benefit while preserving
CPM's defensive bias and bounding the BULL sleeve's path risk contribution.

## Live review gates

Review deployment after 24-36 months of live data:

- **PROMOTE (consider larger sleeve)**: forward Sharpe >= 1.10, MaxDD <= -15%,
  positive vs 60/40 cumulative return
- **HOLD (continue pilot)**: forward Sharpe in [0.70, 1.10], MaxDD in [-15%, -25%]
- **DEMOTE (reduce sleeve)**: forward Sharpe in [0.40, 0.70], or MaxDD < -25%
- **KILL (archive)**: forward Sharpe < 0.40 sustained 12mo+, or MaxDD < -30%,
  or 60/40 outperforms by > 3%/y for 3+ years

If consistent underperformance vs SPY for 5+ years (no crisis to recover),
reconsider whether momentum regime has shifted.

BULL-QQQ sleeve specific: monitor regime-on % (~71% of months historically).
If canary is off for >12 consecutive months while QQQ continues rising,
reconsider whether HYG/TIP/GLD canary is still capturing regime correctly.

## Reproduction

Production code (in `strategy_cpm/`):
- `cpm_live.py` - CPM sleeve runner (allocate + backtest CLI)
- `bull_qqq_live.py` - BULL-QQQ sleeve runner (allocate + backtest CLI)
- `build_dashboard.py` - dashboard generator (production 70/30 blend + variants)
- `data/` - stitched price series (GLD-clean, TIP, AGG, KMLM)
- `research/` - archived research and validation scripts

Key research artifacts (in `strategy_cpm/research/`):
- `walk_forward_rule_freeze.log` - true OOS rule-freeze validation
- `fcp_vs_resolve_live.log` - head-to-head vs live RDMIX fund
- `fcp_regime_attribution.log` - crisis / regime attribution
- `fcp_pp_blend_revisit.log` - blend ratio sweep
- `hold_buffer_threshold_diagnosis.log` - buffer 2.5z vs 3.0z analysis
- `universe_audit_v2.log` - pick frequency and pair archetype audit
- `walk_forward.py` - OOS hyperparameter validation
- `stress_robustness.py` - bootstrap CI + crisis breakdown

Source data:
- `artifacts/cpa-1997-exact-core-proxy-research/proxy_adjusted_close_daily.csv`
- `support/data/kfa_mlm_index_tr_monthly_returns.csv`

Stitched series in `strategy_cpm/data/`:
- `gld_stitched_daily_clean.csv` (GC=F -> GLD)
- `kmlm_stitched_daily.csv` (KFA-MLM Index -> live KMLM)
- `tip_stitched_daily.csv` (VIPSX -> TIP)
- `agg_stitched_daily.csv` (VBMFX -> AGG)
- `dbmf_stitched_daily.csv` (SG CTA -> DBMF)

## References

### Academic
- Moskowitz, T., Ooi, Y., Pedersen, L. (2012). "Time Series Momentum." JFE.
- Jegadeesh, N., Titman, S. (1993). "Returns to Buying Winners and Selling Losers." JoF.
- Hurst, B., Ooi, Y., Pedersen, L. (2017). "A Century of Evidence on Trend-Following Investing." AQR.
- Choueifaty, Y., Coignard, Y. (2008). "Toward Maximum Diversification." JPM.

### Practitioner
- Faber, M. (2007, 2009). "A Quantitative Approach to Tactical Asset Allocation." SSRN.
- Antonacci, G. (2014). "Dual Momentum Investing." McGraw-Hill.
- Keller, W., Keuning, J. (2017). "Breadth Momentum and Vigilant Asset Allocation." SSRN.
- Keller, W., Keuning, J. (2018). "Defensive Asset Allocation." SSRN.
- Keller, W., Keuning, J. (2023). "Hybrid Asset Allocation." SSRN.

- Tresidder, T. (2022). "Optimum 3 Strategy." FinancialMentor.com / AllocateSmartly.
- Butler, A., Philbrick, M., Gordillo, R. (2012). "Adaptive Asset Allocation." Macquarie.

### Industry research
- Allocate Smartly. (2024). Multiple TAA strategy implementations and analyses.
- AQR Research. Various working papers on momentum, vol targeting.

## Research status

**Candidate-grade research, suitable for personal capital with measured ramp.
Not validated for managed-money / fiduciary deployment.**

Strategy passes most validation tests but contains in-sample contamination
in four areas:
1. Hyperparameters (buffer=2.5z, corr lookback=378d) selected by viewing this data
2. Universe (US factor + intl + GLD + TLT) curated via drop-impact testing on same window
3. BULL-QQQ composition (single-ticker + 2-filter selection + SHV fallback) selected from variant sweep
4. Blend weight (any of 50-70% CPM) selected from this same window

Walk-forward validation showed selected hyperparameters consistently win OOS,
partially mitigating concern (1). Universe and blend contamination remain
unmitigated and require live forward evidence.

Before live deployment (personal-capital context):
- **Freeze rule set in code** with versioned outputs (no parameter edits for 12mo)
- **Ramp deployment**: 40-50% of intended sleeve at month 0; 70-80% after 2-3
  clean rebalance cycles; full allocation after 6-12 months no rule drift
- **Audit broker execution slippage** at your retail brokerage (kill if > 25 bps/side)
- **Pre-write kill criteria** (slippage threshold, drawdown threshold, no-tinker rule)

## Status

Backtest period: 1997-08 to 2026-05 (28.7y extended, 18y live-only)
Author: rkautsar; CPM = Canary-gated Pair Momentum (cross-asset rotation
with canary regime gate + min-variance pair selection)
Live deployment: ready for ramped personal-capital pilot per oracle review
