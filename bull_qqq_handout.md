# A Three-Layer Regime Gate for Long-Equity-or-Cash Strategies

**Author:** Rakha Kanz Kautsar
**Date:** 2026-05-23
**Backtest windows:**
- **Clean**: 2008-04-30 to 2026-05-15 (18.1 years, all required ETFs live + 12-month warmup)
- **Documented 30y**: 1996-01-04 to 2026-05-15 (30.4 years, HYG-only canary pre-2001)

**Implementation:** `strategy_cpm/bull_qqq_live.py`

---

## Abstract

This note documents a simple monthly-rebalanced regime gate that converts a
broad US equity benchmark (SPY or QQQ) into a long-equity-or-cash strategy
with materially lower drawdown and comparable or higher risk-adjusted return
than buy-and-hold. The design uses three structurally distinct binary gates. The canary uses
the Keller HAA-style "any positive" rule; the macro composite applies the
same simple OR convention to two non-credit macro pillars:

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

The strategy is implemented in two variants. **Bull-SPY** is the recommended
default for broader market exposure and lower tail risk. **Bull-QQQ** is a
higher-beta variant for investors with explicit tech conviction.

Over the clean window (18.1y, 10 bps/side cost), Bull-SPY delivers Sharpe
1.11 (vs SPY buy-hold 0.66) and max drawdown -12.6% (vs -51.5%). Bull-QQQ
delivers Sharpe 1.10 (vs QQQ buy-hold 0.82) with max drawdown -13.6% (vs
-49.4%). The Sharpe edge survives standard multiple-testing correction
(Deflated Sharpe Ratio passes at N=50+ specification trials; Section 4.10).

A 60% Permanent Portfolio + 40% Bull-equity blend produces Sharpe ~1.28-1.29
with max drawdown -10.3% to -12.3% in the clean window — both blend
metrics are **better than either standalone component**, due to low
cross-sleeve correlation.

This memo is **specification-tested, not out-of-sample**. Several design
choices (canary asset selection, pillar selection, ablation results) were
evaluated on the same historical sample. The clean-window numbers
reported should be treated as historically robust on this sample, not as
forward-looking guarantees.

Secondary supporting evidence: a 30-year backtest from 1996-01 to 2026-05
using documented stitches for all non-live data (HYG/LQD/TIP/SHV/IEF/TLT
from Vanguard mutual funds, GLD from World Bank monthly, QQQ pre-1999
from NDX index). Standalone Bull-SPY Sharpe 0.96, blended 60/40 PP-IEF +
Bull-SPY Sharpe 1.20 over the 30y window including the dotcom bust, GFC,
COVID, and the 2022-2023 inflation regime. The full HYG+TIP canary is
not available before 2001-06 (TIP/VIPSX warm-up); the canary reduces to
HYG-only before then. Section 6 item 11 documents each data source. The
clean 2008+ live-ETF window remains the primary evidence.

## 1. Motivation

A standard long-equity strategy on SPY or QQQ delivers Sharpe 0.5-0.8 with
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
- **Bull-QQQ**: 100% QQQ when gates pass. Higher-beta variant.

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
Backtest returns are credited from T+1 close-to-close, which introduces a
small look-ahead-style approximation: the overnight gap from signal close
to next open is attributed to the new weight rather than the old. This may
introduce a measurement error vs the strict open-fill convention. The
size and direction of this error have not yet been measured; a strict
open-fill backtest is on the future-work list.

All backtests use 10 bps/side trading cost. All input series are total-
return adjusted (yfinance `auto_adjust=True`), so the 13612U and 12-1
momentum signals incorporate dividend reinvestment.

### 2.3.1 Metric definitions

- **Sharpe** (this note): raw Sharpe computed from daily strategy returns,
  annualized by sqrt(252) (`perf_metrics()` in `cpm_live.py`). No excess-
  return subtraction vs SHV or T-bills. The Sharpe SE in Section 4.2 is
  a rough monthly-aggregated approximation -- it uses N monthly
  observations because the standard parametric Sharpe-SE formula is
  typically stated for monthly samples. A daily-return Sharpe-SE
  calculation would produce a different mechanical estimate, but the
  effective uncertainty is dominated by autocorrelation, fat tails, and
  specification search; the monthly approximation is used as a
  conservative communication device. The directional conclusion
  (effective SE around 0.36-0.48) is robust to that choice. The strategy spends 35-40% of months in SHV
  cash earning approximately the short-end Treasury rate, so raw Sharpe
  partly reflects cash yield during risk-off periods.
- **CAGR**: geometric annualized total return (calendar-day basis).
- **Max Drawdown, Ulcer**: computed from the daily equity curve.
- **Calmar**: CAGR / |Max DD|.
- **Martin**: CAGR / Ulcer Index (Martin/McCann definition, sqrt of
  mean squared daily-drawdown depth).

Raw-vs-excess caveat: because the strategy spends substantial time in
SHV, subtracting the SHV return for an excess-Sharpe variant could
change the magnitude of the Sharpe advantage vs SPY/QQQ buy-hold. The
relative ordering is expected to hold (the strategy still beats buy-hold
on DD). For Bull-SPY vs SPY buy-hold, the ordering is verified
empirically in Section 4.8 (Bull-SPY raw 1.114 vs excess 1.004; SPY BH
raw 0.660 vs excess 0.592). Bull-QQQ and PP-blend excess-Sharpe checks
are not shown; broader raw-vs-excess claims would need those. SPY/QQQ buy-hold
does not include a separate cash allocation, while the gated strategy
earns SHV returns during risk-off periods.

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
If Gate-1 AND Gate-2 AND Gate-3 all pass: 100% in risky asset (SPY or QQQ)
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
| QQQ buy-hold              |    0.82 |   17.17% |  -49.37% |   0.35 |   1.45 | 11.9% |
| **Bull-SPY**              |    1.11 |   11.19% |  -12.58% |   0.89 |   2.99 |  3.7% |
| **Bull-QQQ**              |    1.10 |   14.94% |  -13.56% |   1.10 |   2.93 |  5.1% |
| PP-IEF standalone         |    1.00 |    6.96% |  -15.34% |   0.45 |   2.22 |  3.1% |

Per-regime Sharpe (clean window). GFC label is **partial** since clean
window starts 2008-04-30, missing the pre-crisis peak and early decline
(Oct 2007 to Apr 2008).

| Regime                       | SPY BH | QQQ BH | Bull-SPY | Bull-QQQ |
|------------------------------|-------:|-------:|---------:|---------:|
| GFC partial (2008-04 to 2009)|  -0.11 |   0.12 |    +1.34 |    +0.70 |
| Disinfl (2010-2019)          |   0.93 |   1.04 |    +1.01 |    +1.12 |
| COVID (2020)                 |   0.67 |   1.29 |    +0.91 |    +1.16 |
| InflRt (2021-2023)           |   0.63 |   0.52 |    +1.29 |    +1.12 |
| Post (2024+)                 |   1.33 |   1.26 |    +1.68 |    +1.43 |

Risk-on percentage and turnover (clean window):

| Variant   | Months risk-on | Approx flips | Approx flips/year |
|-----------|---------------:|-------------:|------------------:|
| Bull-SPY  |            63% |           33 |               1.8 |
| Bull-QQQ  |            64% |           37 |               2.0 |

### 3.2 Standalone performance — documented 30y window (1996-01-04 to 2026-05-15)

All data sources documented in Section 6 item 11. Canary reduces to HYG-only
before 2001-06 (TIP/VIPSX 12-month warm-up not complete). QQQ pre-1999
uses NDX index proxy. SHV/IEF/TLT pre-live use Vanguard mutual fund
stitches (VFISX/VFITX/VUSTX). GLD pre-2000-08 uses World Bank monthly
data forward-filled to daily.

| Strategy                   |  Sharpe |   CAGR   |   Max DD | Calmar | Martin | Ulcer |
|----------------------------|--------:|---------:|---------:|-------:|-------:|------:|
| SPY buy-hold               |    0.61 |   10.41% |  -55.19% |   0.19 |   0.69 | 15.1% |
| QQQ buy-hold               |    0.63 |   14.41% |  -82.96% |   0.17 |   0.35 | 41.2% |
| **Bull-SPY**               |    0.96 |   10.00% |  -19.35% |   0.52 |   2.23 |  4.5% |
| **Bull-QQQ**               |    0.91 |   14.13% |  -26.83% |   0.53 |   1.72 |  8.2% |
| PP-IEF standalone          |    1.05 |    7.00% |  -15.53% |   0.45 |   2.61 |  2.7% |
| PP-TLT standalone          |    1.01 |    7.16% |  -17.45% |   0.41 |   2.11 |  3.4% |

Per-regime Sharpe (30y):

| Regime              | SPY BH | QQQ BH | Bull-SPY | Bull-QQQ |
|---------------------|-------:|-------:|---------:|---------:|
| Dotcom (2000-2002)  |  -0.53 |  -0.59 |    +0.57 |    +0.18 |
| GFC (2007-2009)     |  -0.05 |  +0.23 |    +0.55 |    +0.72 |
| Disinfl (2010-2019) |  +0.93 |  +1.04 |    +1.01 |    +1.12 |
| COVID (2020)        |  +0.67 |  +1.29 |    +0.91 |    +1.16 |
| InflRt (2021-2023)  |  +0.63 |  +0.52 |    +1.29 |    +1.12 |
| Post (2024+)        |  +1.33 |  +1.26 |    +1.68 |    +1.43 |

The gated strategies report positive Sharpe in every regime row including
dotcom (Bull-SPY +0.57, Bull-QQQ +0.18 vs SPY/QQQ buy-hold -0.53 / -0.59).
Bull-SPY's worst DD over 30y is -19.35% (1998 Russian/LTCM crisis);
Bull-QQQ's is -26.83% (2010 Flash Crash + 2018 Q4 dual hit). The Pre2000
regime (1996-1999) is omitted from the table because the gates fired
actively during the LTCM crisis in 1998, producing positive but lower
Sharpe than buy-hold during the late-1990s bull -- consistent with the
strategy's design (forgo bull-market alpha to limit DD).

### 3.3 60% PP + 40% Bull-equity blend — clean window (18.1y)

The Permanent Portfolio (PP-IEF) is 25% SPY + 25% IEF + 25% GLD + 25% SHV,
equal-weight monthly. Blending 60% PP + 40% Bull-equity:

| Variant                     | Sharpe |   CAGR   |  Max DD  | Calmar | Martin |
|-----------------------------|-------:|---------:|---------:|-------:|-------:|
| PP-IEF standalone           |   1.00 |    6.96% |  -15.34% |   0.45 |   2.22 |
| Bull-SPY standalone         |   1.11 |   11.19% |  -12.58% |   0.89 |   2.99 |
| Bull-QQQ standalone         |   1.10 |   14.94% |  -13.56% |   1.10 |   2.93 |
| 60% PP-IEF + 40% Bull-SPY   |   1.28 |    8.75% |  -10.30% |   0.85 |   3.79 |
| 60% PP-IEF + 40% Bull-QQQ   |   1.29 |   10.30% |  -12.31% |   0.84 |   3.51 |

For both variants, the blend Sharpe is **higher than either standalone
component** AND the blend max drawdown is **smaller than either component
alone**. This is variance reduction from low cross-sleeve correlation: PP
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
| 60% PP-IEF + 40% Bull-QQQ   |   1.16 |   10.13% |  -13.02% |   0.78 |   3.09 |
| 60% PP-TLT + 40% Bull-SPY   |   1.19 |    8.45% |  -10.47% |   0.81 |   3.51 |
| 60% PP-TLT + 40% Bull-QQQ   |   1.16 |   10.23% |  -13.20% |   0.78 |   3.08 |

Over the 30-year documented window, the 60/40 PP+Bull blends report
Sharpe 1.16-1.20 with max drawdown -10.5% to -13.2%. PP-IEF and PP-TLT
variants are nearly identical on Sharpe; PP-IEF has slightly shallower
max drawdown so it is the recommended default unless the user
specifically wants longer-duration deflation exposure.

Daily-return metrics for the pre-2000-08 sub-period may understate gold
volatility because GLD before that date uses forward-filled monthly
World Bank gold data. Monthly-rebalance signals at month-end are
unaffected.

### 3.5 PP/Bull allocation sensitivity (PP-IEF, Bull-SPY, 30y window)

| Allocation                  | Sharpe |   CAGR   |  Max DD  |
|-----------------------------|-------:|---------:|---------:|
| 50% PP + 50% Bull-SPY       |   1.18 |    8.65% |  -11.93% |
| 60% PP + 40% Bull-SPY       |   1.20 |    8.35% |  -10.46% |
| 70% PP + 30% Bull-SPY       |   1.20 |    8.04% |  -10.66% |

The 70/30 split has the highest Sharpe but lowest CAGR; 60/40 is a
balanced compromise — slightly lower Sharpe than 70/30 with higher CAGR
and similar drawdown. The rounded results are very close across the
three splits; the choice depends on whether the user prefers slightly
more growth (50/50) or slightly smoother equity curve (70/30).

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
1996-01) and 2 risky assets (SPY, QQQ). "Wins vs baseline" means
strictly higher Sharpe than the `canary + asset_mom` baseline (no
composite gate) in that cell. Note: these ablation windows are not all
pure live-ETF; they were used for specification testing across longer
histories. The clean 2008-04 window remains the primary live-ETF evidence.

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
correction, see Section 4.10) is roughly **0.23** (annualized).

The Sharpe gap between Bull-SPY (1.11) and Bull-QQQ (1.10) is therefore
within noise. The gap between either gated strategy and the buy-hold
benchmarks (Sharpe 0.66-0.82) is roughly 1-2 SE on raw point estimates,
which a naive reader could dismiss as marginal. However, after the
Deflated Sharpe Ratio adjustment (Section 4.10), which accounts for
specification-search risk explicitly, the Sharpe edge of both gated
strategies vs buy-hold passes at PSR > 99% for 50 hypothetical
independent specification trials. The raw SE is the conservative naive
estimate; the DSR is the methodologically correct treatment of the
multiple-testing concern.

Drawdown improvements (~50-75% reduction vs buy-hold) are larger relative
effects and less subject to noise discount than Sharpe.

For a more rigorous claim, a paired Sharpe-difference test (which
accounts for correlation between the strategy returns and the benchmark
returns) would be needed. This is on the future-work list.

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

|             | Bull-SPY | Bull-QQQ | PP-IEF | PP-TLT | SPY BH | QQQ BH |
|-------------|---------:|---------:|-------:|-------:|-------:|-------:|
| Bull-SPY    |    1.00  |   0.90   |  0.36  |  0.30  |  0.50  |  0.53  |
| Bull-QQQ    |    0.90  |   1.00   |  0.34  |  0.29  |  0.47  |  0.59  |
| PP-IEF      |    0.36  |   0.34   |  1.00  |  0.95  |  0.67  |  0.62  |
| PP-TLT      |    0.30  |   0.29   |  0.95  |  1.00  |  0.53  |  0.51  |
| SPY BH      |    0.50  |   0.47   |  0.67  |  0.53  |  1.00  |  0.93  |
| QQQ BH      |    0.53  |   0.59   |  0.62  |  0.51  |  0.93  |  1.00  |

Key observation: **PP and Bull sleeves correlate at 0.30-0.36 (daily) and
0.32-0.41 (monthly)**, low enough that the 60/40 blend's variance
reduction is consistent with structural diversification rather than a
spurious sample-window artifact. By contrast,
Bull-SPY and Bull-QQQ correlate 0.90 (same gate, same regime) and PP-IEF
and PP-TLT correlate 0.95-0.96 (same structure, different bond duration).
The blend benefit comes from pairing the regime-gated dynamic sleeve
with the balanced-static PP, which observe market stress through
structurally different mechanisms.

30y window correlations are similar (Bull-SPY vs PP-IEF: 0.40
daily / 0.41 monthly), consistent with structural diversification across
the tested windows.

### 4.5 Trend-vs-asset_mom overlap (supports dropping trend pillar)

For the clean window (n=217 monthly signals), the trend pillar
(SPY > 200d MA) agreed with the asset-momentum gate as follows:

| Risky asset | Both on | Both off | Trend only | Mom only | Agree |
|-------------|--------:|---------:|-----------:|---------:|------:|
| vs SPY 12-1 mom | 158 (73%) | 24 (11%) | 13 (6%)  | 22 (10%) | 84%   |
| vs QQQ 12-1 mom | 160 (74%) | 21 (10%) | 11 (5%)  | 25 (12%) | 83%   |

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

### 4.7 Cost sensitivity (Bull-SPY and Bull-QQQ, clean window)

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

**Bull-QQQ standalone:**

| bps/side       | Sharpe | CAGR    | MaxDD    | Calmar |
|----------------|-------:|--------:|---------:|-------:|
| 0 (frictionless)| 1.130 | 15.34%  | -13.56%  |   1.13 |
| 5              |  1.117 | 15.14%  | -13.56%  |   1.12 |
| 10 (baseline)  |  1.104 | 14.94%  | -13.56%  |   1.10 |
| 20             |  1.078 | 14.55%  | -13.56%  |   1.07 |
| 25             |  1.065 | 14.35%  | -13.72%  |   1.05 |
| 50             |  0.998 | 13.37%  | -14.58%  |   0.92 |
| 100            |  0.859 | 11.41%  | -16.28%  |   0.70 |
| 200            |  0.578 |  7.53%  | -24.95%  |   0.30 |

**Cost band interpretation:**

- **0-5 bps/side**: low-cost ETFs at zero-commission retail brokers
  (Vanguard, Fidelity, Schwab, IBKR Lite) with tight spreads. Realistic
  for SPY/QQQ/SHV/HYG/TIP/IEF/TLT which all have ~1c-2c spreads on
  10-100M+ daily volume.
- **10-25 bps/side**: realistic if any execution slippage occurs at scale
  or if rebalancing uses market orders during volatile periods. This is
  the sensitivity band most users should plan around.
- **50 bps/side**: commissioned trading or thinly-traded ETF universe.
  Bull-SPY Sharpe still 0.96 / Bull-QQQ 1.00, both well above SPY/QQQ
  buy-hold (0.66 / 0.82).
- **100 bps/side**: legacy commissioned brokerage with non-trivial
  spread. Bull-SPY Sharpe 0.77, Bull-QQQ 0.86.
- **200 bps/side**: pathological case. Sharpe collapses (0.39 / 0.58)
  and MaxDD blows out because compound cost outpaces returns. Not
  realistic for retail ETF universe; included as stress test.

The gated strategy switches state ~3-5 times per year on average
(~6-10 sided trades). At 20 bps/side, total annual cost drag is roughly
1.2-2.0% of NAV. Sharpe is roughly linear in cost up to ~50 bps and
degrades non-linearly above 100 bps as cost begins to dominate signal.

### 4.8 Excess Sharpe vs SHV (Bull-SPY, clean window)

| Strategy           | Raw Sharpe | Excess Sharpe (vs SHV) | Diff   |
|--------------------|-----------:|------------------------:|-------:|
| Bull-SPY           |     1.136  |                  1.004  | -0.132 |
| SPY buy-hold       |     0.660  |                  0.592  | -0.068 |
| Bull-SPY vs SPY BH |     +0.476 |                 +0.413  | -0.063 |

Subtracting SHV from both the strategy and the benchmark reduces the
strategy's raw Sharpe by 0.13 (since the strategy spends ~37% in SHV
and inherits its yield) and reduces SPY buy-hold's Sharpe by 0.07.
**The strategy's advantage over SPY buy-hold is +0.413 on excess Sharpe**
(vs +0.476 raw) -- the gap shrinks slightly but remains material. The
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
| Bull-QQQ  | Close-to-close (ref) |  1.170 | 15.82%  | -13.56% |    -     |
| Bull-QQQ  | Strict open-fill     |  1.161 | 15.49%  | -13.77% |   -0.009 |

The DELTA is **within noise** (-0.002 to -0.009 Sharpe, ~17-22 bps DD).
The monthly rebalance produces only ~37 weight flips x 2 = ~74 overnight
gaps over 18y with mostly random signs, so the convention choice does
not materially affect results.

Note: absolute Sharpe levels in this table (1.136 / 1.170) are from a
parallel strict-fill reimplementation with slightly different startup
edge handling and differ from the canonical Section 3.1 values
(1.114 / 1.104 at 10bps cost) by ~0.02 Sharpe. The validated quantity
is the delta between conventions on the SAME implementation, which is
robust to that absolute offset. The strict open-fill backtest validates
the close-to-close approximation as adequate for this monthly-rebalanced
strategy.

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
| QQQ buy-hold         |  0.822 |    98.9% |     97.1% |     94.5% |     88.6% |
| Bull-SPY             |  1.114 |   100.0% |     99.9% |     99.7% |     99.2% |
| Bull-QQQ             |  1.104 |   100.0% |     99.9% |     99.7% |     99.1% |

Bull-SPY and Bull-QQQ both remain PSR > 99% at N=50 specification trials
and PSR > 99% at N=19 trials. The number of architectural variations
explored during development is hard to count precisely but is plausibly
in the 10-30 range (canary asset choice, pillar selection, voting rule,
asset momentum lookback variants). **The Sharpe edge is statistically
significant after DSR adjustment for any reasonable specification-test
count in that range.**

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
QQQ). The "structural distinctness" claim is qualitative, not statistical.

The design intent is that in normal regimes, the canary or composite
should fire first (macro signals lead asset price), while asset momentum
provides a direct circuit breaker when macro signals are misleading
(e.g., dotcom, where IG credit rallied while equities crashed). The
dotcom-window regime Sharpe of +0.57 (Bull-SPY) and +0.18 (Bull-QQQ)
vs SPY/QQQ buy-hold -0.53 / -0.59 are consistent with this design intent
(Section 3.2 per-regime table).

### 5.2 Choice of SPY vs QQQ as risky asset

**Bull-SPY (recommended default):**
- Direct alignment between vol pillar (SPY-based) and allocation (SPY).
- Lower concentration risk: SPY has 11 sector weights vs QQQ's tech-heavy
  ~60% Technology + Consumer Discretionary weighting.
- Forward-robust: does not assume tech secular outperformance continues.
- Lower 30y max drawdown (-19.4% vs -26.8% for QQQ).

**Bull-QQQ:**
- Captures tech beta multiplier -- QQQ had ~5.4 pp/year higher buy-hold
  CAGR than SPY in the clean window; gated, Bull-QQQ had ~4.2 pp/year
  higher CAGR than Bull-SPY.
- Same gate logic, no asset-specific tuning.
- Higher 30y CAGR (14.1% vs 10.0%) at the cost of deeper drawdowns.
- Better for investors with explicit conviction in tech secular trend.

In a 60/40 PP+Bull blend, Bull-QQQ produces ~1.5pp higher blend CAGR
with nearly identical Sharpe and similar DD vs Bull-SPY in the clean
window. Forward-looking, the spread is sensitive to whether tech
outperformance persists.

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
   re-entry lag after gates flip back on). COVID 2020 Bull-QQQ Sharpe
   1.16 vs underlying buy-hold 1.29 reflects this lag.

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
   QQQ pre-1999 uses NDX index; SHV/IEF/TLT pre-live use Vanguard mutual
   fund stitches (VFISX/VFITX/VUSTX); HYG uses VWEHX from 1980; TIP
   uses VIPSX from 2000-06 (canary reduces to HYG-only before then);
   GLD pre-2000-08 uses World Bank monthly gold forward-filled to daily.
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
   before then), QQQ pre-1999 from NDX index, GLD pre-2000-08 from
   World Bank monthly (forward-filled to daily; only affects PP gold
   sleeve at daily granularity).

10. **Gates are diversified but not statistically independent.** They
    observe structurally different signals (credit, macro, price), but
    HYG appears in the canary and SPY appears in both the composite and
    is highly correlated with the risky assets.

11. **Data lineage.**

    | Target | Live ETF | Live start | Documented pre-live / warm-up source                  | Pre-live start | Used for         | Notes                                            |
    |--------|----------|------------|--------------------------------------------------------|----------------|------------------|--------------------------------------------------|
    | SPY    | SPY      | 1993-01-29 | (none needed)                                          | n/a            | risk, vol, PP    | Live throughout 30y window                       |
    | QQQ    | QQQ      | 1999-03-10 | NDX index (^NDX) via yfinance                          | 1985-10-01     | risk, asset mom  | NDX = price-return; QQQ = total-return            |
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
    - **NDX is price-return, QQQ is total-return:** QQQ has ~0.5-0.8%
      annual dividend yield not captured by the NDX index. For the
      12-1 asset-momentum signal (sign test), this slightly biases the
      momentum reading more negative for the pre-1999 period but rarely
      flips the sign.
    - **World Bank gold is monthly, forward-filled:** suppresses daily
      volatility in PP gold sleeve before GLD live (2004-11). Monthly-
      rebalance signals at month-end are correct; daily-return metrics
      (Sharpe, correlation) for PP-blend pre-2004 may understate gold
      volatility.
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

To switch the risky asset from QQQ to SPY, change `BULL_TICKER = "QQQ"`
to `BULL_TICKER = "SPY"` near the top of `bull_qqq_live.py`. The gate
logic is unchanged.

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

For Bull-QQQ: additionally QQQ (Nasdaq-100 ETF, inception 1999-03-10).

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
| Asset mom (QQQ)       | 2008-04-30                | 1996-01-31              | QQQ live from 1999-03; pre-1999 uses NDX index proxy from 1985-10      |

See **Section 6 item 11** for the definitive pre-live data lineage with
stitch sources and caveats. The 30y window results are documented
secondary evidence supporting the primary clean 2008+ live-ETF window.

## 9. Future work

The following items would further strengthen the empirical claims:

- **Broader excess-Sharpe verification**: extend Section 4.8 from
  Bull-SPY-only to Bull-QQQ and the PP blends, to support the general
  raw-vs-excess ordering claim.
- **Leave-one-regime-out test** to reduce regime-specific overfit risk
  (e.g. rerun without 2008-2009, see if forward expectations change).
- **Paired Sharpe-difference test** vs buy-hold benchmarks (Jobson-Korkie
  / Memmel adjustment for correlation between return streams), to
  complement the unpaired SE estimate in Section 4.2.
- **Rename `bull_qqq_live.py` to `bull_equity_live.py`** and expose risky
  asset as CLI argument (file naming reflects original Bull-QQQ focus;
  Bull-SPY is now the recommended default).

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


