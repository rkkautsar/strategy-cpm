# When (if ever) does the 50/50 min-var PAIR beat continuous min-var?

**Config:** CPM sleeve, production universe + vol-adjusted ranker + HYG-or-TIP
canary held fixed (U=1, R=1, C=1). The ONLY toggle is the weighting step:
`P=1` = equal-weight 50/50 minimum-variance **pair** of the two lowest-variance
positive-trend survivors (production); `P=0` = **continuous** minimum-variance
weighting over all positive-trend survivors (alternative).

**Execution:** realistic T+1 MOO exact (mooex), 10 bps/side, real yfinance OHLC
opens. Cov lookback 504d.
**Windows:** CLEAN 18y (2008-05-30..2026-05-22, 17.98y) and EXT 27y
(1999-03-10..2026-05-22, 27.20y).
**Harness:** `research/pair_when_wins.py` (reuses
`research/pair_vs_continuous_minvar.py` weighting fns +
`exec_lag_moo_validation_2026_05_30._segment_returns_conv`). Data:
`research/pair_when_wins.json`.

**Reproduction check (CLEAN, 10 bps) - exact, both schemes:**

| scheme | Sharpe | Calmar | MaxDD | anchor |
|---|---|---|---|---|
| pair 50/50 | 1.2424 | 0.8704 | -16.35% | 1.2424/0.8704/-16.35% OK |
| continuous min-var | 1.2935 | 0.9618 | -15.15% | 1.2935/0.9618/-15.15% OK |

Both schemes reproduce their anchors to 4 dp before the rolling/regime analysis.

**Full-window levels (10 bps):**

| window | scheme | Sharpe | Calmar | CAGR | MaxDD |
|---|---|---|---|---|---|
| CLEAN | pair | 1.2424 | 0.8704 | 14.23% | -16.35% |
| CLEAN | continuous | 1.2935 | 0.9618 | 14.57% | -15.15% |
| EXT | pair | 1.1640 | 0.8322 | 13.95% | -16.76% |
| EXT | continuous | 1.2091 | 0.8760 | 13.27% | -15.15% |

Note the EXT split: the pair earns a HIGHER CAGR (13.95% vs 13.27%) but a LOWER
Sharpe and a deeper MaxDD. This is the whole story in one line - the pair tilts
into higher-return, higher-volatility, more-concentrated positions; continuous
min-var trades a little return for materially less risk and wins on every
risk-adjusted aggregate metric.

---

## Verdict (headline)

**There is no reliable estimation-stress / crash regime where the pair wins.**
The DeMiguel (2009) 1/N-regularization hypothesis - that the pair should
outperform when continuous min-var overfits the sample covariance, concentrates
into a low-variance asset, and that asset then reverses/crashes - is only
**weakly and partially supported** in this sample.

The pair DOES win in specific, persistent stretches (2006-2008, 2013-2015,
2023-2025), but the winning condition is NOT "estimation stress." It is
**momentum continuation in a higher-volatility asset that the trend ranker
selected and that continuous min-var down-weights or corner-avoids.** When that
asset keeps trending up, the pair's forced 50% floor captures it; continuous's
variance-minimization treats the trend as a drag and misses it.

In actual crash/stress regimes the result is MIXED, not pro-pair:

- GFC 2008-2009: pair wins (but mostly from the 2007-2008H1 commodity run-up,
  with only a minor true crash-avoidance contribution in 2009H1).
- COVID 2020: pair **loses** decisively.
- 2022 rate-hike: tie (both mostly in cash).
- dot-com 2000-2002: pair **loses**.
- Euro crisis 2011: pair **loses**.

So the pair is **not** a reliable tail/OOS-robustness hedge. Continuous min-var
dominates the aggregate and wins most crash and recovery regimes. The pair's
edge is real but conditional on trend persistence, not on estimation stress.
**The 1/N regularization benefit does not robustly show up in our in-sample
stress episodes; the pair is best understood as a momentum-tilt plus an
operational/governance choice (hard 50% cap, fewer trade events), not a
measured risk-adjusted or crash-protection improvement.**

---

## 1. Rolling difference (pair minus continuous)

Trailing-window Sharpe, Calmar and rolling-MaxDD computed at each month-end over
each window, for both schemes. "Pair wins" = positive difference (for MaxDD,
pair wins = a shallower / less-negative trailing drawdown). Window counts: 217
month-ends (CLEAN), 326 (EXT).

| window | roll | n | Sharpe win % | Calmar win % | MaxDD win % | mean dSharpe | median dSharpe | dSharpe p10 / p90 | mean dMaxDD |
|---|---|---|---|---|---|---|---|---|---|
| CLEAN | 12m | 217 | 47.0% | 47.5% | 33.2% | +0.0125 | -0.0305 | -0.341 / +0.438 | -0.35% |
| CLEAN | 36m | 217 | 48.8% | 47.9% | 25.8% | +0.0223 | -0.0058 | -0.196 / +0.299 | -0.45% |
| EXT | 12m | 326 | 43.3% | 44.8% | 26.4% | -0.0473 | -0.0622 | -0.407 / +0.430 | -0.84% |
| EXT | 36m | 326 | 37.7% | 39.6% | 17.2% | -0.0830 | -0.0707 | -0.346 / +0.232 | -1.52% |

**Reading.** The pair loses the majority of rolling windows on all three metrics
in every window/horizon (Sharpe win 38-49%, Calmar 40-48%, MaxDD 17-33%). MaxDD
is the worst: continuous has the shallower trailing drawdown 67-83% of the time.

The one near-coin-flip is CLEAN Sharpe (47-49% win, slightly POSITIVE mean
+0.012/+0.022 despite a negative median). That positive mean is driven entirely
by a few large, fat right-tail pair wins (p90 +0.30 to +0.44) concentrated in the
GFC and 2023-2025 trend stretches - not by broad-based outperformance. EXT,
which adds the 1999-2007 history, pushes the mean negative (-0.047 / -0.083): the
pair underperforms more often and more deeply once the dot-com bear is in scope.

**Persistence - top contiguous pair-win stretches (12m rolling Sharpe):**

| window | stretch | months | max dSharpe | cumulative dSharpe |
|---|---|---|---|---|
| EXT | 2006-08 .. 2008-11 | 28 | +1.058 | +14.37 |
| CLEAN/EXT | 2023-01 .. 2025-03 | 27 | +0.572 | +8.88 |
| CLEAN/EXT | 2013-08 .. 2015-04 | 21 | +0.560 | +6.19 |
| CLEAN/EXT | 2017-07 .. 2018-06 | 12 | +0.572 | +3.00 |
| CLEAN/EXT | 2009-07 .. 2010-05 | 11 | +0.502 | +2.57 |

36m rolling shows the same clusters as long persistent blocks: EXT
2007-01..2011-01 (49 months, cum +12.74) and 2023-05..2026-05 (37 months, cum
+5.10). When the pair wins it wins persistently - but the stretches are
trend-continuation regimes (run-up to GFC, 2013-2015 equity/EM trend, 2023-2025
bull), interspersed with the GFC recovery, NOT generic volatility/estimation
stress.

---

## 2. Per-regime (pair vs continuous)

Per named regime, full-period Sharpe / CAGR / MaxDD for each scheme; "pair wins?"
flags compare the schemes directly.

| regime | window | pair S | cont S | pair CAGR | cont CAGR | pair MaxDD | cont MaxDD | pair wins S? | pair wins DD? |
|---|---|---|---|---|---|---|---|---|---|
| dot-com | 2000-03..2002-12 | 1.115 | 1.253 | 8.2% | 8.7% | -8.4% | -6.4% | no | no |
| GFC | 2007-10..2009-06 | 0.561 | 0.114 | 8.1% | 0.8% | -16.8% | -15.1% | **yes** | no |
| COVID | 2020-02..2020-06 | 0.958 | 1.466 | 19.0% | 26.2% | -13.1% | -12.3% | no | no |
| rate-hike | 2022-01..2022-12 | 0.575 | 0.766 | 5.6% | 7.0% | -9.6% | -8.7% | no | no |
| euro crisis | 2011-05..2011-12 | 0.804 | 1.129 | 10.0% | 15.7% | -8.1% | -7.4% | no | no |
| taper | 2013-05..2013-12 | 2.707 | 2.130 | 33.8% | 26.3% | -5.6% | -5.4% | **yes** | no |
| vol 2015-16 | 2015-07..2016-02 | 1.566 | 1.539 | 7.2% | 7.2% | -2.9% | -2.9% | ~tie | tie |
| Q4 2018 | 2018-09..2018-12 | -0.989 | -1.269 | -9.1% | -10.1% | -8.3% | -6.8% | yes(S) | no(DD) |
| 2023-24 bull | 2023-01..2024-12 | 1.289 | 0.968 | 13.0% | 9.8% | -7.3% | -9.1% | **yes** | **yes** |

**Reading.** The pair wins Sharpe in GFC, taper-2013, ~tie 2015-2016, Q4-2018
(both negative), and 2023-2024 bull. It loses dot-com, COVID, 2022, euro-2011.
It almost never wins on MaxDD (only 2023-2024). The clean, unambiguous pair wins
(GFC, taper, 2023-2024) are all **strong-trend** episodes; the losses
(dot-com bear, COVID V-recovery, euro/2022 de-risking) are episodes where
continuous's broader, lower-vol allocation was the better call. This is the
opposite of a "pair wins in stress" pattern: of the four classic crashes, the
pair clearly wins one (GFC), loses two (dot-com, COVID), and ties one (2022).

---

## 3. Worst-episode / drawdown attribution + weight diagnosis

Largest peak-to-trough drawdown episodes (EXT, daily, 10 bps):

| pair | depth | | continuous | depth |
|---|---|---|---|---|
| 2008-05-21 -> 2008-10-14 | -16.76% | | 2008-12-30 -> 2009-05-01 | -15.15% |
| 1999-04-26 -> 1999-10-08 | -15.78% | | 2006-05-10 -> 2006-06-13 | -15.15% |
| 2006-05-10 -> 2006-06-14 | -15.71% | | 2004-04-01 -> 2004-05-17 | -14.28% |
| 2004-04-01 -> 2004-05-17 | -14.68% | | 2022-03-08 -> 2023-10-26 | -13.14% |
| 2020-03-09 -> 2020-03-18 | -13.12% | | 2020-03-06 -> 2020-03-18 | -12.31% |
| 2022-03-08 -> 2023-10-05 | -11.36% | | 2025-02-19 -> 2025-04-08 | -10.87% |

The pair's worst drawdowns are uniformly deeper than continuous's at the same
calendar dates (2008, 2006, 2004, 2020), confirming the rolling-MaxDD result: the
pair does not protect drawdowns; it amplifies them.

### Mechanism diagnosis - where the pair WINS

**GFC 2007-2009 (pair +12.96% vs continuous +1.12% over the regime).** Decomposed:

| sub-period | pair | continuous | driver |
|---|---|---|---|
| 2007 | +10.04% | +3.96% | pair holds higher-vol trending assets at 50% |
| 2008 H1 | +13.26% | +1.86% | **commodity (DBC) spike** |
| 2008 H2 | -1.24% | +8.05% | continuous's TLT-heavy book wins the actual crash |
| 2009 H1 | -3.69% | -9.55% | **TLT reversal** - continuous over-concentrated |
| 2009 H2 | +17.50% | +15.57% | recovery, both long GLD/QQQ |

Held weights (selected months):

```
2008-06-30  pair: DBC 0.50 / TLT 0.50     cont: TLT 0.747 / DBC 0.183 / GLD 0.070
2008-12-31  pair: TLT 0.50 / GLD 0.50     cont: TLT 0.778 / GLD 0.222
2009-03-31  pair: TLT 0.50 / GLD 0.50     cont: TLT 0.752 / GLD 0.248
```

The pair's GFC edge is dominated by 2008 H1: the trend ranker selected DBC
(commodities, then spiking to the oil peak), and the pair held it at 50%.
Continuous min-var saw DBC as high-variance and down-weighted it to ~18% in
favor of low-vol TLT, missing the commodity run. In the ACTUAL crash (2008 H2)
continuous's TLT concentration WON (+8.05% vs -1.24%) - the opposite of the
hypothesis. Only in 2009 H1 does the hypothesized mechanism appear: continuous,
concentrated ~0.75 in TLT, took -9.55% when TLT reversed, while the pair's 50%
cap limited it to -3.69%. That is one clean instance of "min-var over-concentrates
into a low-vol asset that reverses," but it is a minority of the total edge.

**Taper 2013 (pair S 2.707 vs continuous 2.130).** Clean corner-solution case:

```
2013-04..09  pair: SPHQ 0.50 / QQQ 0.50    cont: SPHQ 1.00 (single-asset corner)
```

Continuous min-var collapsed to a 100% SPHQ corner solution (the single
lowest-variance survivor). The pair's cap forced 50% into QQQ, the higher-vol
asset, which out-trended SPHQ in the 2013 rally. The concentrated asset (SPHQ)
did NOT crash - it merely lagged - so the pair won via diversification into the
higher-return asset, not via crash avoidance.

**2023-2024 bull (pair S 1.289 vs 0.968, pair MaxDD -7.3% vs -9.1%).**

```
2023-06..2024-06  pair: SPHQ 0.50 + {EEM,EFA,GLD,DBC} 0.50
                  cont: GLD 0.60-0.68 / SPHQ 0.33-0.41 (+EFA/VNQ)
```

Continuous tilted heavily into low-vol GLD and under-weighted the trending equity
SPHQ to ~0.33; the pair held SPHQ at 50% throughout and captured the equity bull.
Same mechanism as GFC-2007 and taper: min-var down-weights the trending,
higher-vol winner; the pair's floor captures it. This is the ONLY regime where
the pair also won MaxDD - because in a steady bull the higher-equity book simply
drew down less than the gold-heavy book.

### Mechanism diagnosis - where CONTINUOUS wins

**COVID 2020 (continuous S 1.466 vs pair 0.958).**

```
2020-01..05  pair: TLT 0.50 / {SPHQ,GLD} 0.50   (effN 2.0)
             cont: TLT 0.42-0.46 / GLD 0.28-0.32 / QQQ/SPHQ 0.24  (effN 2.8-2.9)
```

Here continuous is MORE diversified than the pair (effN 2.8 vs 2.0). In the
V-recovery, spreading across TLT/GLD plus equity beat the pair's 50/50 TLT/GLD,
which under-held the equity rebound. No estimation-stress penalty for continuous
- its broader allocation was simply better.

**dot-com 2000-2002 (continuous S 1.253 vs pair 1.115, shallower DD -6.4% vs
-8.4%).** Continuous ran effN 2.2-2.7 (TLT/VNQ/DBC spread) vs the pair's 2.0; the
broader bond/REIT diversification rode the equity bear with a shallower drawdown.

**2022 rate-hike (continuous 0.766 vs pair 0.575).** Both schemes spent almost the
entire year in cash (SHV 100%); the only difference is the single risk-on month
(Feb, GLD/DBC), where continuous's GLD-tilt beat the pair's 50/50. Essentially a
tie with a tiny continuous edge from one reweighting.

**Calm-regime steady edge.** Outside the trend stretches, continuous's advantage
is exactly the "steady small reweighting" pattern: it spreads across 3-4 assets
(higher average effective N, per the prior study) and continuously trims the
trending/high-vol leg, which is the right risk-adjusted call in mean-reverting or
broad-recovery regimes.

---

## 4. Final verdict

1. **Does the pair ever reliably win?** Yes, but only in **persistent
   strong-trend regimes** where the trend ranker selected a higher-volatility
   asset (commodities 2007-2008H1, QQQ 2013, SPHQ 2023-2024) that continuous
   min-var down-weights or corner-avoids. In those regimes the pair's forced 50%
   floor captures the trend and the win is large and persistent (12-28 month
   stretches).

2. **Is that an estimation-stress / tail hedge?** No. The pair loses the
   majority of rolling windows on Sharpe, Calmar and (badly) MaxDD in both
   windows, its worst drawdowns are deeper than continuous's at every shared
   crash date, and across the four classic crashes it wins one (GFC, mostly from
   pre-crash trend capture), loses two (dot-com, COVID), and ties one (2022).
   The DeMiguel "overfit -> concentrate -> reverse/crash" mechanism appears
   cleanly only once (2009 H1 TLT reversal) and as a corner-solution lag (2013
   SPHQ 100%), never as broad crash protection.

3. **What the pair actually is.** A momentum/trend tilt with a hard 50% cap. It
   buys higher return (EXT CAGR 13.95% vs 13.27%) at the cost of higher
   volatility and deeper drawdowns (EXT Sharpe 1.164 vs 1.209, MaxDD -16.76% vs
   -15.15%). Continuous min-var dominates every risk-adjusted aggregate and wins
   most crash and recovery regimes by allocating more broadly and trimming the
   trending leg.

4. **Bottom line (honest).** The 1/N regularization benefit does **not** show up
   as in-sample stress robustness here. The pair is not a reliable tail or
   OOS-robustness hedge; choosing it is a deliberate momentum tilt plus an
   operational/governance decision (hard concentration cap, no optimizer corner
   solutions, ~2x fewer trade-months per the prior study), accepting a modest
   risk-adjusted give-up for those properties. If the only goal is
   Sharpe/Calmar/MaxDD, continuous min-var dominates everywhere except the
   trend-continuation tail.

**Caveats.** Single data vintage (yfinance auto_adjust; stitched BIL/AGG not used
by CPM). Regime windows are hand-drawn calendar ranges; per-regime Sharpe over
short windows (e.g. COVID ~100 days, taper ~170 days) is high-variance and should
be read as directional, not precise. Rolling metrics evaluated at month-ends with
365d/1095d trailing windows; rolling Calmar is sensitive to whether any drawdown
occurs inside the window. The mechanism diagnosis is from held-weight inspection
plus sub-period return decomposition (GFC), high confidence on direction; the
attribution of the GFC edge to commodity capture vs TLT-reversal avoidance is
quantitative (sub-period table). Confidence: high on the win-fraction and
drawdown-amplification findings (direct accounting, anchors reproduce exact);
high on the trend-capture mechanism (consistent across three independent
episodes); medium on the precise per-regime Sharpe magnitudes (short-window
noise).
