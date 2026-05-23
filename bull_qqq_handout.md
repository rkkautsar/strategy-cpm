# Bull-SPY: A Three-Layer Regime Gate for Long-Equity-or-Cash on SPY

**Author:** Rakha Kanz Kautsar
**Date:** 2026-05-23
**Backtest windows:**
- **Clean**: 2008-04-30 to 2026-05-15 (18.1 years, all required ETFs live + 12-month warmup)
- **Documented 30y**: 1996-01-04 to 2026-05-15 (30.4 years, HYG-only canary pre-2001)

**Implementation:** `strategy_cpm/bull_qqq_live.py`

---

## Abstract

This note documents a simple monthly-rebalanced regime gate that converts
SPY into a long-equity-or-cash strategy with materially lower drawdown
and higher risk-adjusted return than buy-and-hold. The design uses three
structurally distinct binary gates. The canary uses the Keller HAA-style
"any positive" rule; the macro composite applies the same simple OR
convention to two non-credit macro pillars:

1. **Canary gate:** HYG OR TIP 13612U momentum > 0 (Keller HAA convention,
   2-asset credit + inflation signal).
2. **Macro composite gate:** curve OR vol pillar positive, where curve =
   `IEF 63d ret > TLT 63d ret` and vol = `SPY 63d realized vol < 252d
   avg vol`. Both pillars use natural sign-test cutoffs.
3. **Asset momentum gate:** risky asset 12-1 absolute momentum > 0
   (skip-month form, common in academic momentum / TSMOM practice). See
   Section 2.6 for the formula and relation to Antonacci GEM.

All three gates must pass for risk-on (100% in risky asset). Any gate
failure flips to 100% SHV cash.

Over the clean window (18.1y, 10 bps/side cost), Bull-SPY delivers
Sharpe 1.11 (vs SPY buy-hold 0.66) and max drawdown -12.6% (vs -51.5%).
CAGR is slightly lower than buy-hold (11.2% vs 11.8%) but vol is roughly
halved (10.0% vs 19.8%), giving the higher risk-adjusted return. Paired
Jobson-Korkie/Memmel Sharpe-difference test: Bull-SPY's Sharpe advantage
over SPY buy-hold is statistically significant at the 5% level (p=0.028
one-sided). The standalone DSR null check (Section 4.10) also passes
(PSR > 99% at N=50 specification trials).

A 60% Permanent Portfolio + 40% Bull-SPY blend produces Sharpe 1.28 with
max drawdown -10.3% in the clean window — both blend metrics are
**better than either standalone component**, due to low cross-sleeve
correlation.

The implementation supports any equity ticker via the `BULL_TICKER`
constant in `bull_qqq_live.py`; a Bull-QQQ variant exists but is not
recommended in this memo due to weaker paired statistical significance
(JK p=0.091) and lower CAGR yield from cost-of-cash drag relative to
QQQ buy-hold. See `research/` for separate Bull-QQQ artifacts.

This memo is **specification-tested, not out-of-sample**. Several design
choices (canary asset selection, pillar selection, ablation results) were
evaluated on the same historical sample. The clean-window numbers
reported should be treated as historically robust on this sample, not as
forward-looking guarantees.

Secondary supporting evidence: a 30-year backtest from 1996-01 to 2026-05
using documented stitches for all non-live data (HYG/TIP/SHV/IEF/TLT
from Vanguard mutual funds; GLD from World Bank monthly). Standalone
Bull-SPY Sharpe 0.96, blended 60/40 PP-IEF +
Bull-SPY Sharpe 1.20 over the 30y window including the dotcom bust, GFC,
COVID, and the 2022-2023 inflation regime. The full HYG+TIP canary is
not available before 2001-06 (TIP/VIPSX warm-up); the canary reduces to
HYG-only before then. Section 6 item 11 documents each data source. The
clean 2008+ live-ETF window remains the primary evidence.

## 1. Motivation

A standard long-equity strategy on SPY delivers Sharpe 0.6-0.8 with
50-83% peak-to-trough drawdowns. Single-asset trend filters (Faber 10m)
reduce drawdown to ~25-30% but also cost significant CAGR by being out of
the market during shallow corrections.

The design goal of this strategy is:

1. Keep most of the underlying benchmark's CAGR.
2. Cut drawdown materially, targeting absolute max drawdown shallower
   than 25%.
3. Use only freely-available ETF inputs and monthly rebalance frequency.
4. Avoid opaque continuous parameters and tuned numeric thresholds;
   disclose all specification choices selected through historical testing.
5. Demonstrate historical robustness across the full sample including
   dotcom-style crashes.

## 2. Strategy Specification

### 2.1 Risky asset

The strategy is implemented in two variants by choice of risky asset:

- **Bull-SPY** (recommended default): 100% SPY when gates pass. Broad-market
  exposure, less sector concentration, gate signals coherent with allocation.

The two variants use **identical** gate logic.

### 2.2 Cash fallback

When any gate fails, allocate 100% to **SHV** (iShares Short Treasury Bond
ETF). SHV holds U.S. Treasury bonds with remaining maturities of one year
or less (it is not strictly a 1-3 month T-bill fund). For backtest
purposes it provides short-duration Treasury exposure with negligible
credit risk and yields approximately the short-end Treasury rate.

### 2.3 Signal date and execution

Signals are computed at the close of the last trading day of each calendar
month. Trades execute at the OPEN of the next trading day (T+1 MOO).
Backtest returns are credited from T+1 close-to-close, a small
approximation vs strict open-fill: the overnight gap from signal close
to next open is attributed to the new weight rather than the old.
Section 4.9 validates this approximation by running a strict open-fill
backtest; the measured impact is within noise (~2-9 bps Sharpe).

All backtests use 10 bps/side trading cost. Live ETF and mutual-fund
data are total-return adjusted via yfinance `auto_adjust=True`. Index
and commodity proxy series are NOT necessarily total-return: World Bank
monthly gold (GLD pre-2004-11) is a spot commodity price series. Proxy
construction and total-return treatment are documented in Section 6
item 11.

### 2.3.1 Metric definitions

- **Sharpe** (this note): raw Sharpe computed from daily strategy returns,
  annualized by sqrt(252) (`perf_metrics()` in `cpm_live.py`). No excess-
  return subtraction vs SHV or T-bills. Sampling uncertainty, multiple-
  testing adjustment (DSR), and paired Sharpe-difference testing vs
  buy-hold are discussed in Sections 4.2, 4.10, and 4.11. The strategy
  spends 35-40% of months in SHV cash earning approximately the short-
  end Treasury rate, so raw Sharpe partly reflects cash yield during
  risk-off periods.
- **CAGR**: geometric annualized total return (calendar-day basis).
- **Max Drawdown, Ulcer**: computed from the daily equity curve.
- **Calmar**: CAGR / |Max DD|.
- **Martin**: CAGR / Ulcer Index (Martin/McCann definition, sqrt of
  mean squared daily-drawdown depth).

Raw-vs-excess caveat: because the strategy spends substantial time in
SHV, subtracting the SHV return for an excess-Sharpe variant could
change the magnitude of the Sharpe advantage vs SPY buy-hold. The
drawdown advantage is unaffected by the raw-vs-excess convention. For
Sharpe ordering, Bull-SPY vs SPY buy-hold is verified empirically in
Section 4.8 (Bull-SPY raw 1.114 vs excess 0.980; SPY BH raw 0.660 vs
excess 0.591; ordering preserved). PP-blend excess-Sharpe checks are
not shown; broader raw-vs-excess claims would need those.

### 2.4 Gate 1: Canary

Following Keller's Hybrid Asset Allocation (HAA) family of strategies,
the canary uses two credit/inflation-sensitive assets:

- **HYG** (iShares iBoxx $ High Yield Corporate Bond ETF)
- **TIP** (iShares TIPS Bond ETF)

For each asset, compute the 13612U momentum score (Keller normalized
multi-horizon momentum):

```
score(asset) = ( r_1m + r_3m + r_6m + r_12m ) / 4
```

where `r_Nm` is the total return over the trailing N months computed from
month-end close prices.

**Gate passes** if at least one of HYG, TIP has a positive score
("any-positive" rule, Keller HAA convention).

### 2.5 Gate 2: Macro composite

Two binary macro pillars are evaluated at each signal date:

| Pillar  | Test                                                        |
|---------|-------------------------------------------------------------|
| curve   | IEF total return (63d) > TLT total return (63d)             |
| vol     | SPY 63d realized vol < 252d average of 63d rolling vol      |

**Gate passes** if at least one pillar is positive ("any-positive" rule).

Each pillar uses a natural sign-test cutoff:
- `IEF 63d return > TLT 63d return` is the sign of the curve-shape spread.
  IEF outperforming TLT indicates long-duration Treasuries are
  underperforming intermediate Treasuries. Historically this often
  aligns with fewer deflationary/recession-scare dynamics, but it can
  also occur during inflationary rate selloffs; the canary and asset-
  momentum gates are intended to filter the inflationary cases.
- `63d vol < 252d avg vol` is a mean-centered volatility regime test:
  current realized volatility is below its trailing one-year average
  (this is a sign test against the rolling-vol mean, not a z-score).

### 2.6 Gate 3: Asset momentum

Compute 12-1 absolute momentum on the risky asset itself:

```
mom_12_1 = price(t-1m) / price(t-13m) - 1
```

**Gate passes** if `mom_12_1 > 0`. The skip-most-recent-month convention
(Moskowitz, Ooi, Pedersen 2012) is the standard academic TSMOM form;
related to but not exact Antonacci GEM (2014, which uses 12-month total
return without skip). The skip avoids microstructure / reversal noise
in the most recent month.

### 2.7 Allocation rule

```
If Gate-1 AND Gate-2 AND Gate-3 all pass: 100% SPY
Else:                                      100% in SHV cash
```

There is no partial scaling, no continuous tilt, no leverage.

### 2.8 Gate selection rationale

The canary (Gate 1) is HAA-inspired (Keller "any positive" rule on
credit/inflation proxies). The macro composite (Gate 2) was designed by
ablation: trend (SPY 200d MA) and credit (HYG 200d MA) pillars were
dropped as redundant with Gate 3 and Gate 1 respectively; LQD was
rejected as a canary asset because IG corporate bonds rally on rate cuts
during equity crashes (duration effect) and falsely keep canary
risk-on. Curve and vol were selected as the least redundant pair with
canary (credit/inflation) and asset_mom (price/trend).

Full ablation evidence (6 windows x assets) is in Section 4.1; key result
is that `curve OR vol` strictly beats `canary + asset_mom` baseline in
all 6 cells (avg +0.11 Sharpe). Curve OR vol was selected over the
4-pillar 2-of-4 alternative primarily for parsimony, not Sharpe
magnitude (+0.01 Sharpe / -2pp DD; within noise). Applying OR to a
custom curve/vol composite is a specification-tested extension, not a
published Keller rule.

## 3. Empirical Results

### 3.1 Standalone performance — clean window (2008-04 to 2026-05, 18.1y)

| Strategy                  |  Sharpe |   CAGR   |   Max DD | Calmar | Martin | Ulcer |
|---------------------------|--------:|---------:|---------:|-------:|-------:|------:|
| SPY buy-hold              |    0.66 |   11.78% |  -51.48% |   0.23 |   1.03 | 11.4% |
| **Bull-SPY**              |    1.11 |   11.19% |  -12.58% |   0.89 |   2.99 |  3.7% |
| PP-IEF standalone         |    1.00 |    6.96% |  -15.34% |   0.45 |   2.22 |  3.1% |

Per-regime Sharpe (clean window). GFC label is **partial** since clean
window starts 2008-04-30, missing the pre-crisis peak and early decline
(Oct 2007 to Apr 2008).

| Regime                       | SPY BH | Bull-SPY |
|------------------------------|-------:|---------:|
| GFC partial (2008-04 to 2009)|  -0.11 |    +1.34 |
| Disinfl (2010-2019)          |   0.93 |    +1.01 |
| COVID (2020)                 |   0.67 |    +0.91 |
| InflRt (2021-2023)           |   0.63 |    +1.29 |
| Post (2024+)                 |   1.33 |    +1.68 |

Risk-on percentage and turnover (clean window):

| Variant   | Months risk-on | Approx flips | Approx flips/year |
|-----------|---------------:|-------------:|------------------:|
| Bull-SPY  |            63% |           33 |               1.8 |

### 3.2 Standalone performance — documented 30y window (1996-01-04 to 2026-05-15)

All data sources documented in Section 6 item 11. Canary reduces to HYG-only
before 2001-06 (TIP/VIPSX 12-month warm-up not complete). SHV/IEF/TLT
pre-live use Vanguard mutual fund stitches (VFISX/VFITX/VUSTX). GLD
pre-2004-11 (live ETF inception) uses World Bank monthly gold data
forward-filled to daily.

| Strategy                   |  Sharpe |   CAGR   |   Max DD | Calmar | Martin | Ulcer |
|----------------------------|--------:|---------:|---------:|-------:|-------:|------:|
| SPY buy-hold               |    0.61 |   10.41% |  -55.19% |   0.19 |   0.69 | 15.1% |
| **Bull-SPY**               |    0.96 |   10.00% |  -19.35% |   0.52 |   2.23 |  4.5% |
| PP-IEF standalone          |    1.05 |    7.00% |  -15.53% |   0.45 |   2.61 |  2.7% |
| PP-TLT standalone          |    1.01 |    7.16% |  -17.45% |   0.41 |   2.11 |  3.4% |

Per-regime Sharpe (30y):

| Regime              | SPY BH | Bull-SPY |
|---------------------|-------:|---------:|
| Pre2000 (1996-1999) |  +1.39 |    +0.98 |
| Dotcom (2000-2002)  |  -0.53 |    +0.57 |
| GFC (2007-2009)     |  -0.05 |    +0.55 |
| Disinfl (2010-2019) |  +0.93 |    +1.01 |
| COVID (2020)        |  +0.67 |    +0.91 |
| InflRt (2021-2023)  |  +0.63 |    +1.29 |
| Post (2024+)        |  +1.33 |    +1.68 |

Bull-SPY reports positive Sharpe in every regime, including dotcom
(+0.57 vs SPY buy-hold -0.53). The Pre2000 (1996-1999) regime was a
strong bull where buy-hold dominates (+1.39) while the gated strategy
gives up some upside (+0.98) -- consistent with the strategy's design
to forgo bull-market alpha in exchange for limiting DD. Bull-SPY's
worst DD over the 30y window is -19.35% (1998 Russian/LTCM crisis).

### 3.3 60% PP + 40% Bull-equity blend — clean window (18.1y)

The Permanent Portfolio (PP-IEF) is 25% SPY + 25% IEF + 25% GLD + 25% SHV,
equal-weight monthly. Blending 60% PP + 40% Bull-equity:

| Variant                     | Sharpe |   CAGR   |  Max DD  | Calmar | Martin |
|-----------------------------|-------:|---------:|---------:|-------:|-------:|
| PP-IEF standalone           |   1.00 |    6.96% |  -15.34% |   0.45 |   2.22 |
| Bull-SPY standalone         |   1.11 |   11.19% |  -12.58% |   0.89 |   2.99 |
| 60% PP-IEF + 40% Bull-SPY   |   1.28 |    8.75% |  -10.30% |   0.85 |   3.79 |

The blend Sharpe (1.28) is **higher than either standalone component**
(PP-IEF 1.00, Bull-SPY 1.11) AND the blend max drawdown (-10.30%) is
**smaller than either component alone** (-15.34% PP-IEF, -12.58% Bull-SPY). This is variance reduction from low cross-sleeve correlation: PP
is balanced-static and weights toward defensive assets in equity
drawdowns; the Bull sleeve is equity-or-cash and weights toward cash in
equity drawdowns. The two sleeves provide defensive exposure through
structurally different mechanisms.

### 3.4 60% PP + 40% Bull-equity blend — documented 30y window (1996-01 to 2026-05)

| Variant                     | Sharpe |   CAGR   |  Max DD  | Calmar | Martin |
|-----------------------------|-------:|---------:|---------:|-------:|-------:|
| PP-IEF standalone           |   1.05 |    7.00% |  -15.53% |   0.45 |   2.61 |
| PP-TLT standalone           |   1.01 |    7.16% |  -17.45% |   0.41 |   2.11 |
| 60% PP-IEF + 40% Bull-SPY   |   1.20 |    8.35% |  -10.46% |   0.80 |   3.67 |
| 60% PP-TLT + 40% Bull-SPY   |   1.19 |    8.45% |  -10.47% |   0.81 |   3.51 |

Over the 30-year documented window, the 60/40 PP+Bull-SPY blends report
Sharpe 1.19-1.20 with max drawdown -10.5%. PP-IEF and PP-TLT variants
are nearly identical on Sharpe; PP-IEF has slightly shallower max
drawdown so it is the recommended default unless the user specifically
wants longer-duration deflation exposure.

Daily-return metrics before GLD live inception in 2004-11 may understate
gold volatility because the gold sleeve uses monthly World Bank gold
data forward-filled to daily up to that date. Monthly-rebalance signals
at month-end are unaffected.

### 3.5 PP/Bull allocation sensitivity (PP-IEF, Bull-SPY, 30y window)

| Allocation                  | Sharpe |   CAGR   |  Max DD  |
|-----------------------------|-------:|---------:|---------:|
| 50% PP + 50% Bull-SPY       |   1.18 |    8.65% |  -11.93% |
| 60% PP + 40% Bull-SPY       |   1.20 |    8.35% |  -10.46% |
| 70% PP + 30% Bull-SPY       |   1.20 |    8.04% |  -10.66% |

Rounded Sharpe is essentially tied between 60/40 and 70/30 (both 1.20).
60/40 has higher CAGR and slightly shallower max drawdown in the shown
table, making it the cleaner default compromise. The 50/50 variant has
the highest CAGR (8.65%) but slightly deeper drawdown (-11.93%).
Results are close enough that the choice depends on whether the user
prefers slightly more growth (50/50) or smoother equity curve (60/40 or
70/30).

## 4. Robustness Checks

### 4.1 Gate ablation across 6 (window × asset) configs

Each row tests one composite variant on top of canary + asset_mom,
which is the baseline:

| Composite                  | Avg Sharpe | Avg DD   | Wins vs baseline |
|----------------------------|-----------:|---------:|------------------|
| No composite (baseline)    |       0.89 |  -32.04% | --               |
| **curve OR vol (CHOSEN)**  |   **1.00** | -18.04%  | 6/6              |
| All 4 pillars >= 2 of 4    |       0.99 |  -19.98% | 6/6              |
| trend + vol OR             |       0.96 |  -19.87% | 6/6              |
| trend + curve OR           |       0.98 |  -20.25% | 5/6              |
| Each single pillar         |   0.76-0.93|  varied  | 0-4/6            |

The 6 configs are the cartesian product of 3 backtest windows (proxy-
assisted 22.8y from 2003-08, proxy-assisted 19.2y from 2007-02, 30y from
1996-01) and 2 risky assets (SPY and QQQ; QQQ included only for ablation
robustness across asset choice). "Wins vs baseline" means strictly
higher Sharpe than the `canary + asset_mom` baseline (no composite gate)
in that cell. The ablation tables here were recomputed on the v6
documented-stitch data stack and are retained as specification-selection
evidence rather than as headline performance numbers. The clean 2008-04
window remains the primary live-ETF performance evidence.

The macro-composite OR rule reuses the same simple OR convention used by
the canary, but applying OR to a custom curve/vol composite is a
specification-tested extension rather than a published Keller rule.

Key findings (rationale summarized in Section 2.8): no single pillar is
strictly helpful across all 6 configs; curve OR vol is the only 2-pillar
combination that strictly beats baseline in all 6; the 4-pillar 2-of-4
alternative ties on win-rate but loses slightly on Sharpe (-0.01) and DD
(+2pp), within noise.

### 4.2 Sharpe ratio standard error

Using daily returns (T~4540 in the clean window) and Bull-SPY annualized
Sharpe 1.11, the parametric SE under non-normality (Bailey & LdP 2014
correction) is roughly **0.23** (annualized).

This is the standalone marginal SE. Two more rigorous statistical
framings appear later:

- **Section 4.10 (DSR)** addresses specification-search risk: whether
  the observed standalone Sharpe could plausibly arise from a zero-true-
  Sharpe null after testing N variants. Bull-SPY passes at N=50 trials
  (PSR > 99%).
- **Section 4.11 (paired Jobson-Korkie/Memmel)** addresses benchmark-
  relative significance directly: whether Bull-SPY's Sharpe is
  statistically higher than SPY buy-hold's Sharpe, accounting for the
  correlation between the two return streams. Result: p=0.028 (one-
  sided), significant at 5%.

Drawdown improvements (~75% reduction vs buy-hold) are mechanically
larger relative effects, less subject to noise discount than Sharpe.

### 4.3 Pillar firing rates (22.8y proxy-assisted window)

For context, individual pillar firing rates:

| Pillar  | Firing rate | Role                                                  |
|---------|------------:|-------------------------------------------------------|
| curve   |         47% | Most selective; yield-curve regime                    |
| vol     |         62% | Moderately selective; equity vol regime               |
| trend   |         82% | (Dropped — redundant with asset_mom)                  |
| credit  |         79% | (Dropped — partially redundant with canary)           |

The combined `curve OR vol` fires approximately 80% of months, which is
selective enough to materially filter risk-off regimes without being so
restrictive that it disables the gate.

### 4.4 Sleeve correlation (supports the PP+Bull blend claim)

Daily return correlations among sleeves and benchmarks (clean window):

|             | Bull-SPY | PP-IEF | PP-TLT | SPY BH |
|-------------|---------:|-------:|-------:|-------:|
| Bull-SPY    |    1.00  |  0.36  |  0.30  |  0.50  |
| PP-IEF      |    0.36  |  1.00  |  0.95  |  0.67  |
| PP-TLT      |    0.30  |  0.95  |  1.00  |  0.53  |
| SPY BH      |    0.50  |  0.67  |  0.53  |  1.00  |

Key observation: **PP and Bull-SPY correlate at 0.30-0.36 (daily) and
0.32-0.41 (monthly)**, low enough that the 60/40 blend's variance
reduction is consistent with structural diversification rather than a
spurious sample-window artifact. PP-IEF and PP-TLT correlate 0.95-0.96
(same structure, different bond duration). The blend benefit comes
from pairing the regime-gated dynamic sleeve with the balanced-static
PP, which observe market stress through structurally different
mechanisms.

30y window correlations are similar (Bull-SPY vs PP-IEF: 0.40
daily / 0.41 monthly), consistent with structural diversification across
the tested windows.

### 4.5 Trend-vs-asset_mom overlap (supports dropping trend pillar)

For the clean window (n=217 monthly signals), the trend pillar
(SPY > 200d MA) agreed with the asset-momentum gate as follows:

| Risky asset | Both on | Both off | Trend only | Mom only | Agree |
|-------------|--------:|---------:|-----------:|---------:|------:|
| vs SPY 12-1 mom | 158 (73%) | 24 (11%) | 13 (6%)  | 22 (10%) | 84%   |

The trend pillar agreed with the asset-momentum gate ~83% of the time,
confirming the redundancy claim in Section 2.8.

### 4.6 Worst 10 drawdowns and gate attribution (Bull-SPY, clean window)

| Rank | Start      | Trough     | End        | Depth   | Days | Gate flip              |
|-----:|------------|------------|------------|--------:|-----:|------------------------|
|    1 | 2020-02-20 | 2020-03-02 | 2020-09-01 | -12.58% |  194 | composite (2020-02-28) |
|    2 | 2010-04-26 | 2010-05-26 | 2011-01-03 | -12.02% |  252 | none (stayed risk-on)  |
|    3 | 2011-05-02 | 2012-06-04 | 2012-09-06 | -10.88% |  493 | composite (2011-07-29) |
|    4 | 2025-02-20 | 2025-03-13 | 2025-06-24 | -10.04% |  124 | none                   |
|    5 | 2023-08-01 | 2023-10-27 | 2023-11-30 |  -9.97% |  121 | none                   |
|    6 | 2018-09-24 | 2018-10-29 | 2019-07-24 |  -9.72% |  303 | none                   |
|    7 | 2020-09-03 | 2020-09-23 | 2020-11-11 |  -9.44% |   69 | none                   |
|    8 | 2026-02-03 | 2026-03-30 | 2026-04-14 |  -8.88% |   70 | none                   |
|    9 | 2024-07-17 | 2024-08-05 | 2024-09-19 |  -8.41% |   64 | none                   |
|   10 | 2021-11-26 | 2022-03-08 | 2022-03-25 |  -8.00% |  119 | composite (2021-11-30) |

Observations: the gate flipped to cash in only 3 of 10 worst DDs (COVID,
2011 EU debt, 2021-22 inflation). The other 7 are normal -8% to -12%
equity volatility the strategy rides through. The gates catch **sustained
multi-month stress**, not flash crashes. When the gates DID fire, the
failing gate was always the **composite** (curve OR vol macro pillar);
canary and asset_mom did not independently flip first in any worst-10 DD,
suggesting the composite is the most reactive of the three gates. The
2011 episode took 493 days to fully recover, the longest underwater span.
None exceeded -13%.

### 4.7 Cost sensitivity (Bull-SPY, clean window)

Cost is applied as bps/side on the traded notional each rebalance, charged
on both sides of any state flip (sell + buy = 2 x bps). The implementation
debits cost from the daily return on rebalance days.

**Bull-SPY standalone:**

| bps/side       | Sharpe | CAGR    | MaxDD    | Calmar |
|----------------|-------:|--------:|---------:|-------:|
| 0 (frictionless)| 1.150 | 11.58%  | -12.44%  |   0.93 |
| 5              |  1.132 | 11.38%  | -12.49%  |   0.91 |
| 10 (baseline)  |  1.114 | 11.19%  | -12.58%  |   0.89 |
| 20             |  1.077 | 10.79%  | -12.76%  |   0.85 |
| 25             |  1.059 | 10.59%  | -12.84%  |   0.82 |
| 50             |  0.964 |  9.61%  | -13.28%  |   0.72 |
| 100            |  0.769 |  7.66%  | -15.20%  |   0.50 |
| 200            |  0.388 |  3.80%  | -31.01%  |   0.12 |

**Cost band interpretation:**

- **0-5 bps/side**: low-cost ETFs at zero-commission retail brokers
  (Vanguard, Fidelity, Schwab, IBKR Lite) with tight spreads. Realistic
  for the listed ETFs. These are highly liquid ETFs, but realized cost
  still depends on current spreads, order size, market conditions, and
  execution method.
- **10-25 bps/side**: realistic if any execution slippage occurs at scale
  or if rebalancing uses market orders during volatile periods. This is
  the sensitivity band most users should plan around.
- **50 bps/side**: commissioned trading or thinly-traded ETF universe.
  Bull-SPY Sharpe still 0.96, well above SPY buy-hold 0.66.
- **100 bps/side**: commissioned brokerage with non-trivial spread.
  Bull-SPY Sharpe 0.77.
- **200 bps/side**: pathological case. Sharpe collapses to 0.39 and
  MaxDD blows out because compound cost outpaces returns. Not realistic
  for the listed ETF universe; included as stress test.

The gated strategy switches state ~1.8 times per year in the clean
window (Section 3.1 turnover table: 33 flips over 18.1y), or roughly
3.6 sided trades per year. At 20 bps/side, total annual cost drag is
roughly 0.7% of NAV, consistent with the CAGR delta in the cost table
(11.58% at 0 bps falls to 10.79% at 20 bps). Sharpe is roughly linear
in cost up to ~50 bps and degrades non-linearly above 100 bps as cost
begins to dominate signal.

### 4.8 Excess Sharpe vs SHV cash (Bull-SPY, clean window)

This section tests whether the raw Sharpe shrinks meaningfully when
computed in excess of the short-Treasury risk-free rate (vs the
strategy's own cash leg) rather than as raw return / vol.

| Strategy           | Raw Sharpe | Excess Sharpe (vs SHV) | Diff   |
|--------------------|-----------:|------------------------:|-------:|
| Bull-SPY           |      1.114 |                   0.980 | -0.134 |
| SPY buy-hold       |      0.660 |                   0.591 | -0.069 |
| Bull-SPY vs SPY BH |     +0.453 |                  +0.389 | -0.064 |

Subtracting SHV from both the strategy and the benchmark reduces the
strategy's raw Sharpe by 0.13 (since the strategy spends ~37% in SHV
and inherits its yield) and reduces SPY buy-hold's Sharpe by 0.07.
**The strategy's advantage over SPY buy-hold is +0.389 on excess Sharpe**
(vs +0.453 raw) -- the gap shrinks slightly but remains material. The
ordering is robust.

### 4.9 Strict open-fill backtest (vs close-to-close approximation)

The main backtest uses close-to-close return attribution. A strict open-fill
backtest (overnight gap T+1 attributed to OLD weight; intraday T+1 to NEW)
was implemented to test whether the close-to-close convention overstates
performance by hiding overnight gap risk:

| Variant   | Convention            | Sharpe | CAGR    | MaxDD   | Delta Sh |
|-----------|----------------------|-------:|--------:|--------:|---------:|
| Bull-SPY  | Close-to-close (ref) |  1.136 | 11.59%  | -12.58% |    -     |
| Bull-SPY  | Strict open-fill     |  1.134 | 11.41%  | -12.41% |   -0.002 |

The DELTA is **within noise** (-0.002 Sharpe, ~17 bps DD). The monthly
rebalance produces only ~33 weight flips x 2 = ~66 overnight gaps over
18y with mostly random signs, so the convention choice does not
materially affect results.

Note: absolute Sharpe in this table (1.136) is from a parallel
strict-fill implementation with slightly different startup edge handling
and differs from the canonical Section 3.1 value (1.114 at 10bps cost)
by ~0.02 Sharpe. The validated quantity is the delta between conventions
on the SAME implementation, which is robust to that absolute offset.

### 4.10 Deflated Sharpe Ratio (DSR)

The Sharpe figures in Section 3 are point estimates from a sample where
multiple specification variants were tested in development. The Deflated
Sharpe Ratio (Bailey & Lopez de Prado 2014) adjusts for this multiple-
testing selection bias by computing the probability that the observed
Sharpe genuinely exceeds the maximum Sharpe expected from N independent
null (zero-skill) tests on the same data.

DSR with non-normal correction, clean window 2008-04 to 2026-05 (T=4540
daily returns):

| Strategy             | Sharpe | PSR(N=5) | PSR(N=10) | PSR(N=19) | PSR(N=50) |
|----------------------|-------:|---------:|----------:|----------:|----------:|
| SPY buy-hold         |  0.660 |    94.6% |     88.9% |     82.2% |     70.0% |
| Bull-SPY             |  1.114 |   100.0% |     99.9% |     99.7% |     99.2% |

Bull-SPY remains PSR > 99% at N=50 specification trials. The number of
architectural variations explored during development is hard to count
precisely but is plausibly in the 10-30 range (canary asset choice,
pillar selection, voting rule, asset momentum lookback variants).
**The standalone positive Sharpe is unlikely to be a multiple-testing
artifact.** This is a null-hypothesis test (Sharpe is greater than
zero accounting for spec-search), not a benchmark-relative test; for
the paired Bull-vs-buy-hold significance question see Section 4.11.

Implementation notes:
- Per-period (daily) Sharpe used in formula; annualized Sharpe divided
  by sqrt(252) before applying skew/kurt SE correction.
- Non-excess kurtosis used (normal = 3).
- `sr0_period = sqrt(1/(T-1)) * max_z` is the null-variance approximation
  used when actual trial Sharpe variances are not collected; if the full
  trial Sharpe distribution were tracked, V[trial Sharpe] would replace
  the 1/(T-1) term, potentially loosening the threshold.
- Validated against R `quantstrat::deflated.Sharpe` reference
  implementation and auditzk.com calculator (SR=2.0, T=252, N=1000
  reproduces published PSR ~10%).

Reference: Bailey, D. H. & Lopez de Prado, M. (2014). "The Deflated
Sharpe Ratio: Correcting for Selection Bias, Backtest Overfitting, and
Non-Normality." *Journal of Portfolio Management* 40(5), 94-107.

### 4.11 Paired Sharpe-difference test vs buy-hold (Jobson-Korkie/Memmel)

The DSR check (Section 4.10) tests whether each strategy's standalone
Sharpe is significantly different from zero accounting for specification
search. The paired Jobson-Korkie test (Jobson & Korkie 1981, corrected
by Memmel 2003) directly tests whether the GATED Sharpe is statistically
higher than the BUY-HOLD Sharpe on the same underlying asset, accounting
for the correlation between the two return streams. This is the
appropriate test for the benchmark-relative significance claim.

Memmel (2003) corrected variance of the paired Sharpe difference:

```
var(Sh_a - Sh_b) = (1/T) * [2*(1 - rho)
                            + 0.5*(Sh_a^2 + Sh_b^2 - 2*Sh_a*Sh_b*rho^2)]
z = (Sh_a - Sh_b) / sqrt(var)
```

where `rho` is the correlation between the two daily return series and
Sharpes are at the per-period (daily) scale. Results on the clean
window (T=4540 daily, 10 bps/side cost):

| Comparison                | Sh(Bull) | Sh(BH) | Diff   | rho   | z     | p (one-sided) | Verdict           |
|---------------------------|---------:|-------:|-------:|------:|------:|--------------:|-------------------|
| Bull-SPY vs SPY buy-hold  |    1.114 |  0.660 | +0.453 | 0.498 | +1.92 |        0.0276 | significant @ 5%  |

**Bull-SPY's Sharpe is statistically significantly higher than SPY
buy-hold's Sharpe at the 5% level (one-sided).**

**Note on active-return Sharpe tests:** an alternative framing applies
PSR/DSR to the active return stream `Bull-SPY - SPY buy-hold`. That
test measures whether the active return stream is significant relative
to its own tracking-error volatility. It is appropriate for active
managers tracking a benchmark on a TE-adjusted basis, but it is not the
right test here. Bull-SPY is structurally different from SPY buy-hold
(cash ~37% of time, vol roughly halved), not a TE-active variant. The
active-return Sharpe is negative (-0.11) because of the small CAGR drag
(0.6pp) combined with high tracking-error vol. This negative-active-
return-Sharpe result does not contradict the JK/Memmel result above:
the strategy delivers higher risk-adjusted return at the cost of
slightly lower raw return, and the right statistical question is the
paired Sharpe-difference test.

References:
- Jobson, J. D. & Korkie, B. M. (1981). Performance Hypothesis Testing
  with the Sharpe and Treynor Measures. *Journal of Finance* 36(4).
- Memmel, C. (2003). Performance Hypothesis Testing with the Sharpe
  Ratio. *Finance Letters* 1(1).

## 5. Discussion

### 5.1 Why each gate matters

| Component         | Role                                                     |
|-------------------|----------------------------------------------------------|
| HYG canary        | High-yield credit stress (widens before equity crashes)  |
| TIP canary        | TIPS total-return momentum (real-rate + inflation-sensitive) |
| Curve pillar      | Growth-on vs late-cycle (yield curve shape)              |
| Vol pillar        | Volatility regime (calm vs unstable)                     |
| Asset momentum    | Direct observation of risky asset (skip-month 12-1 abs mom) |

The components observe different market dimensions, but they are **not
statistically independent**. HYG appears in the canary; SPY appears in
both the vol pillar and is highly correlated with the risky assets (SPY,
QQQ in ablation phase). The "structural distinctness" claim is qualitative, not statistical.

The design intent is that in normal regimes, the canary or composite
should fire first (macro signals lead asset price), while asset momentum
provides a direct circuit breaker when macro signals are misleading
(e.g., dotcom, where IG credit rallied while equities crashed). The
dotcom-window regime Sharpe of +0.57 (Bull-SPY) vs SPY buy-hold -0.53 is
consistent with this design intent (Section 3.2 per-regime table).

## 6. Limitations and caveats

1. **Specification-tested, not out-of-sample.** Canary asset selection,
   pillar selection (curve+vol), and ablation choice (1-of-2 OR) were all
   evaluated on the same historical sample. The numbers reported should
   be treated as historically robust on this sample, not as forward-
   looking guarantees.

2. **Single regime per epoch.** Dotcom, GFC, COVID, and InflRt each
   appear once in the sample. Per-regime Sharpes are descriptive, not
   predictive.

3. **Gate lag.** Both 13612U and 12-1 momentum use trailing windows of
   12 months. Sharp V-recoveries are partially missed (typical 2-4 week
   re-entry lag after gates flip back on). COVID 2020 Bull-SPY Sharpe
   0.91 vs SPY buy-hold 0.67 reflects partial recapture of the V-shape.

4. **Single-asset all-or-nothing.** No partial scaling, no diversification
   when risk-on. In-market periods carry full equity beta.

5. **Bull market drag.** In calm bull markets (Disinfl 2010-2019), the
   gate occasionally flips to cash on minor signal trips and gives up
   some upside. Bull-SPY Disinfl Sharpe 1.01 vs SPY buy-hold 0.93 — a
   small premium, not a large one.

6. **Sample window bias.** 1999-2026 includes one major bond bull market
   (1999-2020) and one bond bear market (2020-2023). The curve pillar's
   behavior in a future regime that does not resemble either may differ.

7. **Documented-stitch 30y window.** Pre-live data sources are
   summarized in Section 6 item 11. Briefly: SPY is live throughout;
   SHV/IEF/TLT pre-live use Vanguard mutual fund stitches
   (VFISX/VFITX/VUSTX); HYG uses VWEHX from 1980; TIP uses VIPSX from
   2000-06 (canary reduces to HYG-only before then); GLD pre-2004-11
   uses World Bank monthly gold forward-filled to daily.
   **30y results are documented stress-test evidence, secondary to the
   clean 2008+ live-ETF window.**

8. **Backtest execution convention.** The main backtest credits the
   close[T]-to-close[T+1] return to the new weight (close-to-close
   approximation). Section 4.9 reports a strict open-fill backtest as
   validation: the strict convention puts the overnight gap from
   signal close to next open on the OLD weight. Measured impact is
   negligible (~2-9 bps Sharpe, ~20 bps DD), within noise for this
   monthly-rebalanced strategy. The close-to-close approximation is
   adequate.

9. **Missing data policy (single explicit rule).** Each gate input is
   evaluated against whatever data is in the panel at the signal date,
   regardless of whether that data is live-ETF or proxy-stitched. Each
   canary asset contributes to the "any positive" rule only when its
   13612U momentum can be computed (12-month lookback available). If
   neither HYG nor TIP has 12-month data, the canary gate fails
   (defensive default). Each composite pillar (curve, vol) contributes
   to the OR rule only when its underlying inputs are available
   (IEF/TLT 63d returns for curve; SPY 252d rolling-vol history for vol).
   If neither pillar is evaluable, the composite gate fails. The asset-
   momentum gate fails if 13 months of risky-asset price history are
   unavailable. This is the available-assets variant of the "any
   positive" rule; gates fail-closed when inputs are missing.

   In the 30y window, all gate inputs use documented stitches (Section
   6.11): SHV/IEF/TLT from Vanguard mutual funds (VFISX/VFITX/VUSTX),
   HYG from VWEHX, TIP from VIPSX (after 2000-06; HYG-only canary
   before then), GLD pre-2004-11 (live ETF inception) from World Bank
   monthly gold forward-filled to daily (only affects PP gold sleeve
   at daily granularity).

10. **Gates are diversified but not statistically independent.** They
    observe structurally different signals (credit, macro, price), but
    HYG appears in the canary and SPY appears in both the composite and
    is highly correlated with the risky assets.

11. **Data lineage.**

    | Target | Live ETF | Live start | Documented pre-live / warm-up source                  | Proxy data start | Used for         | Notes                                            |
    |--------|----------|------------|--------------------------------------------------------|----------------|------------------|--------------------------------------------------|
    | SPY    | SPY      | 1993-01-29 | (none needed)                                          | n/a            | risk, vol, PP    | Live throughout 30y window                       |
    | SHV    | SHV      | 2007-01-05 | VFISX (Vanguard Short-Term Treasury)                   | 1991-10-28     | cash fallback    | VFISX dur ~2y vs SHV ~0.3y                       |
    | IEF    | IEF      | 2002-07-22 | VFITX (Vanguard Intermediate-Term Treasury)            | 1991-10-28     | curve, PP-IEF    | VFITX dur ~5y vs IEF ~7-10y                      |
    | TLT    | TLT      | 2002-07-22 | VUSTX (Vanguard Long-Term Treasury)                    | 1986-05-19     | curve, PP-TLT    | VUSTX dur ~15-17y vs TLT ~17-20y                 |
    | HYG    | HYG      | 2007-04-04 | VWEHX (Vanguard High-Yield mutual fund)                | 1980-01-02     | canary, credit   | Well-established HY fund                         |
    | TIP    | TIP      | 2003-12-04 | VIPSX (Vanguard Inflation-Protected Securities)        | 2000-06-29     | canary           | Pre-2001-06 canary reduces to HYG-only           |
    | GLD    | GLD      | 2004-11-18 | World Bank monthly gold (freegoldapi.com), ffill->daily| 1995-01-02     | PP gold sleeve   | Monthly granularity; affects daily metrics only  |
    | LQD    | LQD      | 2002-07-22 | VFICX (Vanguard Intermediate-Term IG Corporate Bond)   | 1993-10-29     | (research only)  | Tested as canary asset, rejected (Section 2.8)   |

    Each stitch is built by a script in `research/archive/stitch_*.py`
    using the live ETF as anchor and rescaling the pre-live proxy so
    the splice date matches the live value. See those scripts for the
    exact build logic. Load order is in `cpm_live.load_panel()`.

    **Proxy/stitch caveats:**

    - **Mutual fund duration mismatch:** VFISX/VFITX/VUSTX have
      slightly different effective durations than the live SHV/IEF/TLT
      ETFs they proxy. Direction is consistent but magnitude can differ
      by ~10-20% on rate moves.
    - **World Bank gold is monthly, forward-filled:** suppresses daily
      volatility in PP gold sleeve before GLD live inception (2004-11).
      Monthly-rebalance results are less sensitive to the daily forward-
      fill than daily-return metrics, but the monthly-average versus
      month-end-price convention of the World Bank series remains a
      proxy caveat. Daily-return metrics (Sharpe, correlation) for PP-
      blend pre-2004-11 may understate gold volatility. The gold series
      itself extends from 1995-01 (World Bank Pink Sheet commodity data
      accessed via freegoldapi.com compilation).
    - **TIP pre-2000-06 gap:** no TIP proxy before VIPSX inception.
      Canary fails-closed on TIP signal during that period, effectively
      reducing to HYG-only canary.

    **Implication for 30y window:** documented stitches are sufficient
    to compute all gate signals from 1996-01 onwards.

## 7. Implementation

The strategy is implemented in `bull_qqq_live.py` in the repository
`github.com/rkkautsar/strategy-cpm`.

```bash
# Compute this month's allocation
python bull_qqq_live.py allocate

# Backtest (clean window)
python bull_qqq_live.py backtest --start 2008-04-30

# Backtest (extended window)
python bull_qqq_live.py backtest --start 1996-01-04
```

The risky asset is set via `BULL_TICKER = "SPY"` near the top of
`bull_qqq_live.py`. The gate logic is unchanged for other equity
tickers; this memo's results apply to the SPY default only.

## 8. Required Data Series

For Bull-SPY (live ETF only):

| Ticker | Role                                | Live ETF inception |
|--------|-------------------------------------|--------------------|
| SPY    | Risky asset + vol pillar            | 1993-01-29         |
| SHV    | Cash fallback                       | 2007-01-05         |
| HYG    | Canary                              | 2007-04-04         |
| TIP    | Canary                              | 2003-12-04         |
| IEF    | Curve pillar                        | 2002-07-22         |
| TLT    | Curve pillar                        | 2002-07-22         |

For 60/40 PP-IEF blend: additionally GLD (Gold ETF, inception 2004-11-18).

The latest required live ETF is HYG (2007-04-04). With a 12-month 13612U
warmup, the first valid pure-ETF signal date is approximately 2008-04-30.
This is the start of the "clean window" backtest.

### 8.1 First valid signal date by gate component

First month-end signal date at which the gate component is evaluable
(under the available-assets rule, gates fail-closed when inputs missing).
In the 30y window, every gate is evaluable from 1996-01-31 under the
available-assets rule. The full HYG+TIP canary is not available until
approximately 2001-06 (TIP/VIPSX 12-month warm-up); before then the
canary reduces to HYG-only.

| Component             | Clean window first signal | 30y window first signal | Notes                                                                  |
|-----------------------|---------------------------|-------------------------|------------------------------------------------------------------------|
| Canary HYG 13612U     | 2008-04-30                | 1996-01-31              | Clean: live HYG. 30y: VWEHX stitch from 1980                           |
| Canary TIP 13612U     | 2008-04-30                | 2001-06-30              | VIPSX live 2000-06; pre-2001 canary reduces to HYG-only                |
| Curve pillar (IEF/TLT)| 2008-04-30                | 1996-01-31              | Clean: live IEF/TLT. 30y: VFITX/VUSTX stitches pre-2002                |
| Vol pillar (SPY)      | 2008-04-30                | 1996-01-31              | 252d lookback on SPY (live since 1993)                                 |
| Asset mom (SPY)       | 2008-04-30                | 1996-01-31              | 13mo lookback on SPY (live since 1993)                                 |

See **Section 6 item 11** for the definitive pre-live data lineage with
stitch sources and caveats. The 30y window results are documented
secondary evidence supporting the primary clean 2008+ live-ETF window.

## 9. Future work

The following items would further strengthen the empirical claims:

- **Broader excess-Sharpe-vs-SHV verification**: extend Section 4.8 from
  Bull-SPY-only to the PP-IEF blend, to support the general raw-vs-
  excess ordering claim.
- **Leave-one-regime-out test** to reduce regime-specific overfit risk
  (e.g. rerun without 2008-2009, see if forward expectations change).
- **HAC / bootstrap robustness** for the paired Jobson-Korkie/Memmel
  Sharpe-difference test (Section 4.11) to relax the i.i.d. assumption
  on daily returns.
- **Rename `bull_qqq_live.py` to `bull_spy_live.py`** to reflect this
  memo's recommended default.

## 10. References

- Faber, M. (2007). A Quantitative Approach to Tactical Asset Allocation.
- Keller, W. & Keuning, J. (2023). HAA: Hybrid Asset Allocation. SSRN.
- Antonacci, G. (2014). Dual Momentum Investing.
- Moskowitz, T., Ooi, Y. & Pedersen, L. (2012). Time Series Momentum.
  *Journal of Financial Economics* 104(2).
- Browne, H. (1999). Fail-Safe Investing.
- Bailey, D. & Lopez de Prado, M. (2014). The Deflated Sharpe Ratio:
  Correcting for Selection Bias, Backtest Overfitting, and Non-Normality.
  *Journal of Portfolio Management* 40(5), 94-107.


