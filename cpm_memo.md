# CPM Research Memo

Current state: convention-locked monthly ETF implementation. Clean window uses full real-open coverage. Extended window includes proxy-backed pre-ETF segments. Metrics are post-cost and use month-end signal with next-session-open execution.

Scope: this memo evaluates CPM-Core (cross-asset top-4 Faber vol-adjusted momentum, HYG-or-TIP canary, breadth-scaled partial-safe routing, SHV/IEF safe selector). Sleeve overlays are out of scope.

## 0. Header and metadata

- Strategy: CPM (Cross-asset Parity Momentum).
- Risky universe: QQQ, SPHQ, EFA, EEM, VNQ, GLD, TLT, DBC.
- Safe assets: SHV, IEF.
- Windows:
  - Clean: 2008-05-30 to 2026-05-22 (18.0 years).
  - Extended: 1995-01-31 to 2026-05-22 (~31.3 years), with proxy-backed segments before full ETF coverage.
- Costs: 10 bps per side, embedded in all tables.
- Sharpe convention: raw Sharpe (rf = 0) and excess Sharpe versus SHV.
- Rebalance and leverage: monthly rebalance, unlevered.
- Execution convention: signal at month-end close, trade at next-session open.

## 1. Executive summary

1) LEAD - capital preservation and tail control.
CPM is a capital-preservation-first momentum strategy. Drawdown-adjusted point gaps are large: Calmar 1.06 and Martin 3.96 versus 0.23-0.42 and 1.0-1.6 across the benchmark set, with MaxDD -12.67% versus -21.76% to -34.92%. Versus the AAA-style benchmark and 60/40, these are economically large point-estimate advantages, but clean-window difference CIs include zero, so the read is favorable but statistically unresolved over 18 years. Point-estimate advantage is not solely GFC-driven: CPM's worst clean drawdown is 2025-04-08 at -12.67%, while the GFC drawdown is -11.88% (extended continuous-curve, capturing the full episode), and ex-GFC point metrics still lead. Drawdown control is not solely canary-dependent: no-canary MaxDD is -15.01%, still shallower than every benchmark. MaxDD is intuitive but high-variance, so headline interpretation should pair MaxDD with Martin/Ulcer and paired-bootstrap difference framing. Drawdown differences are still significant versus naive 12m and buy-hold inverse-vol.

2) RETURN - real but modest.
Signal quality survives stated selection tests (DSR z about 3.9-5.4 and selection inflation about 0.16-0.25 Sharpe), but production configuration should still be treated as selected in-sample. Forward Sharpe is about 0.72 (range 0.62-0.85). Raw-Sharpe differences versus the AAA-style benchmark and 60/40 are favorable in point estimate but statistically unresolved in the clean window.

3) RISK - execution discipline is load-bearing.
Month-end signal alignment matters, and fill convention is a separate question. With a true month-end signal, T+1 MOO remains robust (1.1910 versus 1.2063 same-day MOC), but shifting the signal/rebalance calendar off month-end degrades performance (EOM+1 about 1.01; EOM+3 about 0.91). Turn-of-month premium is regime-cyclical, not a steady decay, and is dormant in the live tail. Canary is cheap crisis optionality: about -0.08 Sharpe drag in calm regimes in exchange for about 2.35 points of overall MaxDD protection (-15.01% no-canary to -12.67%), concentrated in crises.

4) INVESTOR FIT - capital-preservation-first.
CPM fits investors who want tail control plus a modest return profile. Practical relative headline is the 2021-22 inflation analog (2021-04..2022-12, n=21): CPM 1.21 versus 60/40 -0.19, where conventional portfolios have the least defense. B-regime conditional scenario is about 0.59 (just below the unconditional forward-range low of 0.62 by construction, since it conditions on a choppy regime persisting); still positive. CPM is not a raw-return or high-Sharpe maximizer.

Turnover:
- Clean: 2.616 one-way per year, 13.4% fully-safe months.
- Extended: 2.733 one-way per year, 10.1% fully-safe months.

## 2. Investment thesis and economic rationale

Cross-asset time-series momentum persists through risk-on and risk-off cycles because investor flows, risk budgets, and macro regimes adjust gradually rather than instantly. CPM expresses this through a breadth-scaled cross-asset momentum pipeline: rank assets by 10-month trend strength per unit of realized volatility, keep only positive-trend assets, select the top four, inverse-volatility weight the surviving risky block, and route unused risk slots to the timed safe asset. "Parity" in CPM refers to inverse-volatility weighting of the risky block, not full covariance-based risk parity or ERC optimization. The strict-4 partial-safe rule makes risk exposure proportional to breadth: when fewer than four assets qualify, the missing slots go to SHV or IEF. The HYG-OR-TIP canary provides a broad risk-permission layer; the SHV/IEF selector distinguishes duration-friendly from duration-hostile defensive regimes. This maps to decomposition evidence: R plus U drive return, W is a smaller helper, and C, S, and P are protective layers concentrated in crisis regimes.

### 2.1 Execution-timing cliff and operational risk

Terminology disambiguation (three distinct concepts):
- Signal date: month-end close used to compute rankings, canary state, and safe selector.
- Fill convention: price used to enter after a fixed signal date (same-day MOC, T+1 MOO, or T+1 close).
- Signal/rebalance-date offset: shifting the signal calendar away from true month-end (EOM, EOM+1, EOM+2, EOM+3 business days).

Schematic timeline:
- True month-end signal path: EOM close (signal date) -> T+1 open (T+1 MOO fill) or T+1 close (T+1 close fill).
- Shifted-calendar path: EOM+1/EOM+2/EOM+3 close becomes the signal date, then its own next-session fill follows.

These are different tests and should not be conflated:
- Fill-convention test at fixed month-end signal: same-day MOC 1.2063 versus T+1 MOO 1.1910 (robust to next-open fill).
- Signal/rebalance-date-offset test: EOM 1.2063 to EOM+1 1.01 and EOM+3 0.91 (degrades when signal calendar moves off month-end).

Headline performance depends on month-end alignment. Empirical day-1 attribution over the full clean sample:
- Day-1 after month-end rebalance earns 14.9 bp versus about 4.9 bp on the rest of the month.
- About 13% of total clean PnL is earned in that single day.
- Mid-month rebalance Sharpe is 0.93.

Subperiod day-1 attribution is empirical (not inference):

| Subperiod | day-1 bp | rest-of-month bp | day1/rest | Sharpe drop if day-1 removed |
|---|---:|---:|---:|---:|
| 2008-12 | 22.7 | 3.9 | 5.80x | 0.162 |
| 2013-17 | 9.4 | 5.0 | 1.89x | 0.054 |
| 2018-22 | 19.0 | 4.1 | 4.61x | 0.165 |
| 2023-26 | 6.2 | 7.1 | 0.87x | 0.001 |

Interpretation:
- Turn-of-month premium is regime-cyclical, not steadily decaying. The 2018-22 revival contradicts a simple crowding-erosion story.
- The stronger 2017-26 half is momentum-core driven, not turn-of-month inflated: day-1 bp is flat (14.8 to 14.9), while rest-of-month improved.
- Forward turn-of-month haircut should be state-contingent: about 0.00-0.05 in calm regimes, up to about 0.15 in high-vol or crisis regimes, not a flat 0.10-0.20.
- Execution alignment is a separate live risk: EOM to EOM+1 Sharpe falls 1.21 to 1.01, and EOM+3 is 0.91.
- Production T+1 MOO still captures most of same-day MOC (1.191 versus 1.206 close-to-close).

## 3. Strategy specification

### 3.1 Signal definitions

Let monthly sampled close series P_ME be built with resample("ME").last(), ie, each month uses the last available trading close and month-end labels.

Let monthly total return over h months be r_h = P_ME(t) / P_ME(t-h) - 1, measured from the sampled close h months earlier to the current sampled month-end close; when calendar month-end is non-trading, the sampled close is the nearest prior trading-day close.

- 13612U momentum:
  - m_13612U = (r_1 + r_3 + r_6 + r_12) / 4.
- 10-month trend distance:
  - SMA_10m = simple average of the latest 10 sampled month-end closes, including the current signal month-end close.
  - m_faber = price / SMA_10m - 1.
- Realized volatility:
  - rv_252d = stdev(simple daily returns, 252d) * sqrt(252), used in the rank score m_faber / rv_252d.
  - rv_504d = stdev(simple daily returns, 504d) * sqrt(252), used for risky-block inverse-vol weighting.

### 3.2 CPM rule stack

1. Compute score = m_faber / rv_252d for each risky asset in {QQQ, SPHQ, EFA, EEM, VNQ, GLD, TLT, DBC}.
2. Keep only assets with m_faber > 0.
3. Rank by score and keep top 4.
4. If canary is off, allocate full capital to safe selector.
5. If canary is on:
   - n_pos = number of surviving positives (0..4).
   - risky_fraction = min(n_pos, 4) / 4.
   - safe_fraction = 1 - risky_fraction.
   - risky block uses inverse-vol weights proportional to 1 / rv_504d across surviving positives.
   - safe block goes to timed SHV or IEF by 13612U.

This is strict-4 partial-safe behavior:
- n_pos = 0 -> 0/4 risky, 4/4 safe.
- n_pos = 1 -> 1/4 risky, 3/4 safe.
- n_pos = 2 -> 2/4 risky, 2/4 safe.
- n_pos = 3 -> 3/4 risky, 1/4 safe.
- n_pos = 4 -> 4/4 risky, 0/4 safe.

### 3.3 Canary and safe selector

- Canary is on if m_13612U(HYG) > 0 OR m_13612U(TIP) > 0.
- Safe selector chooses argmax of m_13612U over {SHV, IEF}.

### 3.4 Parameter table

| Component | Parameter | Value |
|---|---|---|
| Trend risky universe size | N | 8 |
| Trend selection count | K | 4 |
| Trend score | Rank metric | m_faber / rv_252d |
| Trend positivity filter | Threshold | m_faber > 0 |
| Risky block weighting | Rule | inverse-vol over surviving positives |
| Risky fraction control | Rule | strict-4 partial-safe, min(n_pos,4)/4 |
| Risky-block inverse-vol lookback | Window | 504 trading days |
| Canary | Rule | m_13612U(HYG) > 0 OR m_13612U(TIP) > 0 |
| Safe selector | Rule | argmax m_13612U over SHV, IEF |
| Transaction cost | Side cost | 10 bps |
| Rebalance frequency | Cadence | monthly |
| Leverage | Gross leverage | 1.0x |
| Execution | Fill convention | next-session open |

## 4. Data and methodology

- Data panel uses live ETFs where available plus audited proxy stitches in pre-ETF segments.
- Windows:
  - Clean: 2008-05-30 to 2026-05-22.
  - Extended: 1995-01-31 to 2026-05-22.
- Costs: 10 bps per side, embedded in all metrics.
- Execution: signal at month-end close, fill at next-session open (T+1 MOO exact).
- Reduced-universe engine behavior: the production engine ranks and selects among currently available assets and drops assets before their proxy start; this is why the extended curve starts at 1995-01-31.
- Extended proxy-coverage ladder (live risky ETFs out of 8): 0/8 in 1995-98, 1/8 by 1999, 3/8 by 2002, 7/8 by 2005, and 8/8 by 2006.
- Interpretation: the 1995-2007 segment is proxy-heavy, so the extended window is a proxy-informed robustness lens; the clean window (2008+, fully live) is the decisive lens.
- TIP canary note: the extended-window TIP leg also uses the synthetic pre-live proxy segment.

### 4.1 Proxy-construction audit (extended-window disclosure)

Proxy-backed history is disclosure and robustness context only. Clean window remains the decision lens.

| Asset | Group | Live ETF inception | Pre-inception proxy source | Proxy type | Total return? |
|---|---|---|---|---|---|
| QQQ | risky | 1999-03-10 | ^NDX Nasdaq-100 index (`data/qqq_stitched_daily.csv`) | index | price-index splice (QQQ tracks NDX closely) |
| SPHQ | risky | 2005-12-06 | synthetic (proxy-file floor; no tradeable quality fund pre-2005) | synthetic | adjusted-close synthetic |
| EFA | risky | 2001-08-14 | EAFE-type fund series (proxy file) | index/fund | adj-close |
| EEM | risky | 2003-04-07 | EM fund series (proxy-file floor) | index/fund | adj-close |
| VNQ | risky | 2004-09-23 | VGSIX (Vanguard REIT index fund) | mutual fund | yes (adj-close) |
| GLD | risky | 2004-11-18 | World Bank gold spot, monthly, pre-2000-08 (`data/gld_stitched_extended_daily.csv`) | spot price | spot (no carry) |
| TLT | risky | 2002-07-22 | VUSTX (Vanguard Long-Term Treasury) (`data/tlt_stitched_daily.csv`) | mutual fund | yes (adj-close) |
| DBC | risky | 2006-02-03 | synthetic commodity (proxy-file floor) | synthetic | adj-close synthetic |
| HYG | canary | 2007-04-11 | VWEHX (Vanguard High-Yield Corp) (`data/hyg_stitched_daily.csv`) | mutual fund | yes (adj-close) |
| TIP | canary | 2003-12-05 | IEF+CPI synthetic pre-2000-06, then VIPSX (`data/tip_stitched_daily.csv`) | synthetic + mutual fund | yes (IEF TR + realized CPI; VIPSX adj-close) |
| SHV | safe | 2007-01-11 | VFISX (Vanguard Short-Term Treasury) (`data/shv_stitched_daily.csv`) | mutual fund | yes (adj-close) |
| IEF | safe | 2002-07-22 | VFITX (Vanguard Intermediate Treasury) (`data/ief_stitched_daily.csv`) | mutual fund | yes (adj-close) |

Canary and safe proxy disclosure (review gap fix):
- HYG canary proxy is VWEHX (total return) pre-2007-04.
- TIP canary proxy is IEF+CPI synthetic pre-2000-06, then VIPSX to live TIP; this synthetic leg is weaker pre-1997 and is treated as robustness-only context.
- SHV safe proxy is VFISX.
- IEF safe proxy is VFITX.

Interpretation guardrail:
- Pre-ETF segments are proxy-informed and descriptive; clean 2008-05-30 onward remains inferential and decisive.

## 5. Headline results

### 5.1 CPM headline metrics

Clean Sharpe is 1.1910 with bootstrap 95% CI [0.7866, 1.5969].

Decision lens: clean window. Extended metrics in this section are proxy-informed robustness only.

| Window | Sharpe | CAGR | Vol | MaxDD | Calmar | Martin | Ulcer | Excess Sharpe vs SHV |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Clean | 1.1910 | 13.44% | 11.16% | -12.67% | 1.0615 | 3.9646 | 3.39% | 1.0719 |
| Extended (proxy-informed robustness only) | 1.2643 | 14.00% | 10.78% | -15.93% | 0.8791 | 3.9767 | 3.52% | 1.0007 |

Extended Sharpe bootstrap (stationary block bootstrap, B=2000, block=21, seed=42): point 1.2643, 95% CI [0.9430, 1.5986], median 1.2619.

The tighter extended CI is expected from larger N and slightly lower dispersion, not from data quality improvement: about 377 versus 217 monthly observations (roughly 1/sqrt(N), about 19% tighter) and 10.78% versus 11.16% volatility; the early extended segment remains proxy-backed, so clean remains decisive.

MaxDD framing by window: clean-window worst drawdown is 2025-04-08 at -12.67%; extended-window worst drawdown is the 2006 proxy-era episode at -15.93%.

### 5.2 Crisis behavior

Global drawdown episodes (extended continuous-curve basis):

| Crisis | Peak | Trough | Depth | Recovery | Trough to recovery | Live risky ETFs / 8 |
|---|---|---|---:|---|---:|---|
| LTCM (1998) | 1998-07-20 | 1998-09-02 | -9.88% | 1999-03-11 | +190d | 0 of 8 live (all proxy) |
| Dot-com era (2002 in-window dip) | 2002-05-29 | 2002-07-24 | -5.87% | 2002-08-29 | +36d | 1 of 8 live (QQQ only) |
| GFC (2008) | 2008-03-14 | 2008-10-14 | -11.88% | 2008-12-16 | +63d | 8 of 8 live |
| COVID (2020) | 2020-03-06 | 2020-03-18 | -10.06% | 2020-04-15 | +28d | 8 of 8 live |
| 2022 | 2021-11-24 | 2022-01-27 | -7.64% | 2022-03-08 | +40d | 8 of 8 live |

Dot-com labeling note: this is the deepest in-window drawdown of the dot-com era. CPM went defensive and largely sidestepped the 2000-02 bubble burst, so this row is not a bubble-peak-to-trough crash measurement.

Proxy caveat: LTCM and dot-com-era rows are proxy-heavy (0/8 and 1/8 live). They describe the proxy-informed extended lens, while GFC and later rows are fully live.

Within-calendar windows (same extended continuous-curve episodes):

| Crisis window | MaxDD | Return |
|---|---:|---:|
| GFC (2007-10..2009-06) | -11.88% | 9.86% |
| COVID (2020-02..2020-06) | -10.06% | 8.00% |
| 2022 bear (2022-01..2022-12) | -6.33% | -0.50% |

### 5.3 Bootstrap confidence interval (clean Sharpe)

| Statistic | Value |
|---|---:|
| point | 1.1910 |
| 2.5% | 0.7866 |
| 50% | 1.1964 |
| 97.5% | 1.5969 |

Method: stationary block bootstrap, B=2000, block=21 trading days, seed=42.

Use the clean headline as 1.1910 with CI [0.7866, 1.5969], not as a single precise forward estimate.

### 5.4 Turnover and fully-safe months

| Window | One-way turnover per year | Fully-safe months |
|---|---:|---:|
| Clean | 2.616 | 13.4% |
| Extended (proxy-informed robustness only) | 2.733 | 10.1% |

### 5.5 AAA-style available-panel benchmark and significance

Headline benchmark set uses an AAA-style available-panel benchmark (Adaptive Asset Allocation class; Butler, Philbrick, Gordillo, Varadi; SSRN 2328254) plus investor alternatives. This available-panel implementation keeps EWJ and RWX excluded, with EFA and VNQ as stand-ins for EZU and IYR; this supersedes the older internal 8-of-10 factorial baseline for headline comparison.

Benchmark glossary:

| Label | Role in this memo |
|---|---|
| CPM-Core | Main strategy under evaluation |
| AAA-style available-panel benchmark | Primary external headline comparator |
| AAA-like factorial baseline (internal all-OFF baseline) | Decomposition baseline only; not a headline comparator |
| 60/40 (SPY/IEF) | Investor reference comparator |
| Naive 12m momentum (no canary, equal-weight) | Simple dynamic baseline |
| Buy-hold inverse-vol | Static baseline |
| HAA/GTAA | Peer-context only |

Headline comparator is AAA-style available-panel benchmark; 60/40 is the investor reference.

Clean window (2008-05-30 to 2026-05-22):

| Series | Sharpe | CAGR | MaxDD | Calmar | Martin |
|---|---:|---:|---:|---:|---:|
| CPM | 1.19 | 13.44% | -12.67% | 1.06 | 3.96 |
| AAA-style available-panel benchmark | 0.94 | 9.23% | -21.76% | 0.42 | 1.62 |
| 60/40 (SPY/IEF) | 0.79 | 8.75% | -29.82% | 0.29 | 1.40 |
| Naive 12m momentum (no canary, equal-weight) | 0.65 | 8.14% | -26.59% | 0.31 | 1.02 |
| Buy-hold inverse-vol | 0.69 | 8.15% | -34.92% | 0.23 | 1.11 |

Sharpe difference test (CPM minus benchmark, paired block bootstrap, 95% CI):

| Comparator | dSharpe | 95% CI | Includes zero? |
|---|---:|---|---|
| AAA-style available-panel benchmark | +0.25 | [-0.069, +0.607] | Yes |
| 60/40 | +0.40 | [-0.069, +0.826] | Yes |
| Naive 12m | +0.54 | [+0.178, +0.925] | No |
| Buy-hold inverse-vol | +0.51 | [+0.086, +0.907] | No |

Drawdown-adjusted difference tests (CPM minus benchmark, paired block bootstrap, 95% CI):

| Metric | Comparator | Point diff | 95% CI | Includes no-diff point? |
|---|---|---:|---|---|
| MaxDD gap (percentage points, positive = shallower CPM DD) | AAA-style available-panel benchmark | +9.10 | [-5.86, +13.54] | Yes |
| MaxDD gap (percentage points, positive = shallower CPM DD) | 60/40 | +17.16 | [-3.00, +23.71] | Yes |
| MaxDD gap (percentage points, positive = shallower CPM DD) | Naive 12m | +13.92 | [+1.52, +31.09] | No |
| MaxDD gap (percentage points, positive = shallower CPM DD) | Buy-hold inverse-vol | +22.25 | [+0.06, +30.21] | No |
| Calmar difference (positive = better CPM) | AAA-style available-panel benchmark | +0.6399 | [-0.1162, +0.9142] | Yes |
| Calmar difference (positive = better CPM) | 60/40 | +0.7713 | [-0.0213, +1.1070] | Yes |
| Calmar difference (positive = better CPM) | Naive 12m | +0.7579 | [+0.1548, +1.1379] | No |
| Calmar difference (positive = better CPM) | Buy-hold inverse-vol | +0.8313 | [+0.1109, +1.1800] | No |
| Martin difference (positive = better CPM) | AAA-style available-panel benchmark | +2.3504 | [-0.1371, +3.8059] | Yes |
| Martin difference (positive = better CPM) | 60/40 | +2.5738 | [-0.3145, +4.5695] | Yes |
| Martin difference (positive = better CPM) | Naive 12m | +2.9550 | [+0.7683, +4.7088] | No |
| Martin difference (positive = better CPM) | Buy-hold inverse-vol | +2.8682 | [+0.4540, +4.7908] | No |

Read:
- Versus the AAA-style available-panel benchmark and 60/40, difference-CI tests are underpowered at this 18y sample length: Sharpe, MaxDD, and Calmar intervals are structurally wide.
- Economically large point-estimate advantages are present, but clean-window difference CIs versus AAA-style and 60/40 include zero, so the result is favorable but statistically unresolved. Practical point gaps still matter: CPM MaxDD is -12.67% versus -21.76% to -34.92%.
- Class-norm context: sub-significance versus 60/40 is not CPM-specific. Adaptive Asset Allocation (SSRN 2328254, 1995-2015) has in-sample dSharpe +0.084 (not significant), and the Keller/Keuning HAA paper variant (SSRN 4346906) over about 52 years has dSharpe +0.246 with CI [-0.058, +0.540] (still not significant).
- Honesty on benchmark OOS: AAA-style did not decay after its 1995-2015 paper window (Sharpe 1.068 to 1.228 in 2016-2026), while CPM's roughly +0.24 Sharpe edge in that slice matches the full-clean gap but remains within bootstrap noise and is CPM-in-sample versus AAA-OOS (2016-2026 sits inside CPM's selection window), so it is not clean OOS evidence that CPM beats AAA.
- CPM point edge is economically favorable in this sample: dSharpe versus 60/40 is +0.40, while peer 18y point edges are about +0.20 (HAA) and +0.18 (AAA). CPM Calmar is 1.06 versus peer 0.66-0.74 (HAA 0.656, AAA 0.743 at 18y) and 60/40 at 0.29. Peer comparisons use a monthly-close engine, so cross-engine comparison to mooex is approximate.
- Drawdown control is not solely canary-dependent: disabling canary moves MaxDD from -12.67% to -15.01%, and -15.01% still beats every benchmark MaxDD. Canary adds about 2.35 points of protection; drawdown control is load-bearing in the trend, screen, and inverse-vol stack, not solely dependent on canary signal quality.
- Significance still clears versus naive 12m and buy-hold inverse-vol.

Extended window (proxy-informed robustness only; per-series available start dates -- not a common-window ranking):

| Series | Start | Sharpe | CAGR | MaxDD | Calmar | Martin |
|---|---|---:|---:|---:|---:|---:|
| CPM | 1995-01-31 | 1.26 | 14.00% | -15.93% | 0.88 | 3.98 |
| AAA-style available-panel benchmark | 2008-01-19 | 0.93 | 9.07% | -21.76% | 0.42 | 1.60 |
| 60/40 | 1999-03-10 | 0.69 | 7.31% | -31.44% | 0.23 | 1.07 |
| Naive 12m momentum | 1999-03-10 | 0.82 | 10.11% | -26.59% | 0.38 | 1.43 |
| Buy-hold inverse-vol | 1999-03-10 | 0.84 | 9.56% | -35.61% | 0.27 | 1.44 |

AAA-style available-panel benchmark remains limited by available-panel history plus momentum warmup; that is why it does not extend to the 1995 CPM extended start in this framework.

### 5.6 Common-window extended comparison (robustness disclosure)

The per-series extended table above is not apples-to-apples because starts differ by series. Common-window tables below enforce single starts.

All-series common start is 2008-01-19 (bounded by AAA availability):

| Series | Sharpe | CAGR | MaxDD | Calmar | Martin |
|---|---:|---:|---:|---:|---:|
| CPM | 1.188 | 13.41% | -12.67% | 1.059 | 3.858 |
| AAA-style available-panel | 0.930 | 9.07% | -21.76% | 0.417 | 1.603 |
| 60/40 (SPY/IEF) | 0.798 | 8.81% | -30.83% | 0.286 | 1.372 |
| Naive 12m momentum | 0.665 | 8.48% | -26.59% | 0.319 | 1.067 |
| Buy-hold inverse-vol | 0.708 | 8.51% | -35.61% | 0.239 | 1.136 |

Ex-AAA common start is 1999-03-10 (genuinely extended 4-series comparison):

| Series | Sharpe | CAGR | MaxDD | Calmar | Martin |
|---|---:|---:|---:|---:|---:|
| CPM | 1.214 | 13.71% | -15.93% | 0.861 | 3.820 |
| 60/40 (SPY/IEF) | 0.691 | 7.31% | -31.44% | 0.232 | 1.071 |
| Naive 12m momentum | 0.816 | 10.11% | -26.59% | 0.380 | 1.428 |
| Buy-hold inverse-vol | 0.842 | 9.56% | -35.61% | 0.268 | 1.435 |

Guardrail: these common-window extended tables are robustness context only. Clean window remains decision lens.

### 5.7 Calendar-year returns and intra-year drawdown (clean window)

Boundary-year note: 2008 and 2026 are partial years for at least one series and are not cross-series comparable; full-year comparison is 2009-2025.

| Year | CPM ret | CPM intraDD | AAA ret | AAA intraDD | 60/40 ret | 60/40 intraDD |
|---|---:|---:|---:|---:|---:|---:|
| 2008* | +5.08% | -9.83% | +1.66% | -11.74% | -15.57% | -26.88% |
| 2009 | +14.47% | -7.09% | +0.80% | -11.03% | +13.23% | -17.62% |
| 2010 | +16.62% | -9.15% | +15.59% | -8.38% | +13.42% | -6.95% |
| 2011 | +10.44% | -7.49% | +8.99% | -10.42% | +8.29% | -8.56% |
| 2012 | +6.72% | -4.81% | -3.53% | -10.14% | +11.26% | -4.20% |
| 2013 | +19.47% | -8.79% | +23.75% | -8.34% | +15.60% | -5.24% |
| 2014 | +15.78% | -6.07% | +9.60% | -4.29% | +11.95% | -3.39% |
| 2015 | -0.97% | -6.51% | -1.00% | -6.48% | +1.76% | -6.94% |
| 2016 | +10.36% | -9.43% | +1.71% | -8.15% | +7.80% | -3.87% |
| 2017 | +22.43% | -2.26% | +10.58% | -3.30% | +13.76% | -1.49% |
| 2018 | +1.92% | -10.13% | +0.77% | -8.94% | -1.96% | -10.83% |
| 2019 | +12.41% | -3.72% | +9.18% | -3.03% | +21.78% | -2.68% |
| 2020 | +23.43% | -10.06% | +19.80% | -7.88% | +16.90% | -19.13% |
| 2021 | +26.22% | -4.70% | +25.42% | -5.70% | +15.10% | -3.70% |
| 2022 | -0.50% | -6.33% | -14.25% | -21.76% | -16.39% | -20.67% |
| 2023 | +1.60% | -7.93% | +7.80% | -9.17% | +16.97% | -8.26% |
| 2024 | +15.08% | -7.01% | +17.87% | -6.14% | +14.23% | -4.36% |
| 2025 | +26.47% | -12.67% | +19.12% | -6.29% | +14.33% | -10.60% |
| 2026* | +20.84% | -5.99% | +21.70% | -6.07% | +4.71% | -6.00% |

`*` partial year, not cross-series comparable.

### 5.8 Worst-interval and underwater-duration table (clean window)

| Metric | CPM | AAA-style | 60/40 |
|---|---:|---:|---:|
| Worst 1-month return | -6.00% | -7.08% | -9.77% |
| Worst 3-month return | -7.48% | -10.24% | -15.37% |
| Worst 12-month return | -5.24% | -16.86% | -16.39% |
| Longest underwater | 688 days | 903 days | 787 days |

These are single-path statistics from one sample; read as robustness evidence, not standalone inference.

## 6. CPM 2^6 decomposition

Extended-window figures in this section are proxy-informed robustness only; clean-window results remain the main decision lens.

The CPM 2^6 decomposition runs from an AAA-like factorial baseline (internal all-OFF baseline, 000000) to CPM all-ON (111111), where OFF uses 6-month momentum (R), minimum-variance weighting on weighted 126d/20d covariance (W), the 8-of-10 SPY-set universe (U; EWJ and RWX excluded, EFA and VNQ stand in for EZU and IYR slash-pairs per benchmark_audit), and no canary (C).

This 000000 AAA-like factorial baseline line is the internal decomposition baseline only. It is not the headline external benchmark in Section 5.5.

- Baseline all-OFF (AAA-like factorial baseline, internal all-OFF baseline, 8-of-10 available assets): clean Sharpe 0.7869, MaxDD -23.21%, Calmar 0.3188; extended Sharpe 0.9040, Calmar 0.3626.
- All-ON is production CPM: clean Sharpe 1.1910, MaxDD -12.67%, Calmar 1.0615; extended Sharpe 1.2643, MaxDD -15.93%, Calmar 0.8791.

Factor mapping is C,U,R,S,W,P where OFF is the AAA-like factorial baseline and ON is CPM. [FLIP] means on-minus-off changes sign across backgrounds.

Clean-lens decomposition story:
- R is top first-order driver (+0.2048 Sharpe, +0.2411 Calmar [FLIP]).
- C is large contributor (+0.1104 Sharpe, +0.2172 Calmar [FLIP]) because the AAA-like factorial baseline has no canary.
- U is moderate net positive and W is much stronger in the extended window; S is slightly Sharpe-negative but Calmar-positive (drawdown-control contribution).
- P is diluted in marginal averages (+0.0482 Sharpe, +0.0886 Calmar [FLIP]) because it is inert when S is OFF and breadth stays 4; P value is concentrated in S x P (+0.0886 clean Calmar, +0.0752 extended Calmar).

| Factor | CLEAN dSharpe | CLEAN dCalmar | EXT dSharpe | EXT dCalmar |
|---|---:|---:|---:|---:|
| Ranker (R) | +0.2048 | +0.2411 [FLIP] | +0.1110 | +0.1481 [FLIP] |
| Canary (C) | +0.1104 | +0.2172 [FLIP] | +0.0728 | +0.1790 [FLIP] |
| Universe (U) | +0.0837 [FLIP] | +0.0657 [FLIP] | +0.0824 [FLIP] | +0.0148 [FLIP] |
| Screen (S, positive-trend) | -0.0228 [FLIP] | +0.0463 [FLIP] | -0.0178 [FLIP] | +0.0346 [FLIP] |
| Weighting only (W) | +0.0127 [FLIP] | +0.0646 [FLIP] | +0.1054 | +0.1217 [FLIP] |
| Partial-safe (P) | +0.0482 | +0.0886 [FLIP] | +0.0282 [FLIP] | +0.0730 [FLIP] |

CPM key two-way interactions (Calmar deltas):

| Interaction | CLEAN dCalmar | EXT dCalmar |
|---|---:|---:|
| U x R | +0.1392 | +0.1012 |
| S x P | +0.0886 | +0.0752 |
| C x R | +0.0832 | +0.0497 |
| R x S | +0.0570 | +0.0367 |
| R x W | -0.0134 | -0.0045 |
| S x W | -0.0165 | +0.0033 |

Contribution ladder uses dependency order R -> C -> U -> W -> S -> P:

| Step | Config (C,U,R,S,W,P) | CLEAN Sharpe | CLEAN Calmar | CLEAN MaxDD | EXT Sharpe | EXT Calmar | EXT MaxDD |
|---|---|---:|---:|---:|---:|---:|---:|
| Baseline (AAA-like factorial baseline) | 000000 | 0.7869 | 0.3188 | -23.21% | 0.9040 | 0.3626 | -23.21% |
| +R | 001000 | 0.9128 | 0.3637 | -23.54% | 0.9645 | 0.3591 | -23.54% |
| +C | 101000 | 1.0527 | 0.7203 | -12.96% | 1.0479 | 0.6347 | -13.90% |
| +U | 111000 | 1.2062 | 0.7491 | -17.52% | 1.1707 | 0.6929 | -17.52% |
| +W | 111010 | 1.1785 | 0.9606 | -14.22% | 1.2405 | 0.8887 | -15.93% |
| +S | 111110 | 1.1491 | 1.0614 | -12.67% | 1.2533 | 0.9069 | -15.93% |
| +P (all-ON production CPM) | 111111 | 1.1910 | 1.0615 | -12.67% | 1.2643 | 0.8791 | -15.93% |

Clean ladder Calmar is monotone from 0.3188 to 1.0615. Extended ladder is not monotone: +R dips Calmar from 0.3626 to 0.3591 and +P dips Calmar from 0.9069 to 0.8791.

## 7. Design notes

Extended-window references in this section are proxy-informed robustness only.

### 7.1 Ranker comparison

CPM ranker comparison remains vol-adjusted Faber versus plain 12-month momentum. Section 6 reports R-factor effects versus the AAA-like factorial baseline's native 6-month ranker (+0.2048 clean dSharpe), while this section isolates a different baseline (+0.1994 clean, +0.1488 extended).

- Clean Sharpe lift: +0.1994, paired 95% CI [-0.0275, +0.4480].
- Extended Sharpe lift: +0.1488, paired 95% CI [-0.0270, +0.3275].
- Directional signal remains high but not significant at 95%: P=95.3% clean and about 94.7% extended.

### 7.2 Universe analysis

Universe factor U is positive in Sharpe and Calmar by window (+0.0837 clean dSharpe, +0.0824 extended dSharpe; +0.0657 clean dCalmar, +0.0148 extended dCalmar). Interaction terms U x R and C x R carry major contribution.

### 7.3 Weighting interpretation

Weighting appears as W factor in the decomposition: AAA-like factorial baseline minimum-variance versus CPM inverse-vol over surviving positives. This is decomposition attribution, not a CPM variant family.

The small factorial W effect (+0.0127 clean dSharpe) is measured against AAA-like factorial baseline minimum-variance, so it understates inverse-vol value because inverse-vol is the solver-free simplification of the same vol-aware idea. Against the naive equal-weight baseline at production settings, inverse-vol is 1.1910 versus 1.1317 clean Sharpe (+0.0593), with Calmar 1.0615 versus 1.0147 and MaxDD -12.67% versus -13.05%.

### 7.4 Asset concentration (CPM risky contribution share)

| Asset | Clean share | Extended share |
|---|---:|---:|
| SPHQ | 20.9% | 16.4% |
| QQQ | 16.9% | 13.7% |
| GLD | 15.0% | 12.3% |
| EFA | 11.7% | 11.6% |
| TLT | 10.5% | 15.5% |
| VNQ | 9.8% | 12.6% |
| EEM | 8.1% | 9.5% |
| DBC | 7.2% | 8.5% |

Extended concentration summary: top holding is SPHQ at 16.4%, and top-3 share is 45.5%.

### 7.5 Cross-asset stagflation resilience and proxy caveats

Historical proxy tests suggest CPM's cross-asset design can rotate toward gold and commodity leadership in stagflationary regimes, but the 1970s results rely on lower-fidelity proxy data and should be treated as directional only.

### 7.6 Factor stability across halves (at-production marginal dSharpe)

| Factor | 2008-16 | 2017-26 |
|---|---:|---:|
| R (ranker) | +0.30 | +0.11 |
| U (universe) | +0.25 | +0.10 |
| W (inverse-vol weighting) | +0.09 | +0.02 |
| C (canary) | +0.15 | -0.08 |
| S (positive-trend screen) | +0.04 | -0.01 |
| P (strict-4 partial-safe) | +0.07 | +0.02 |

Read:
- Return engine is regime-robust: R and U stay positive in both halves; ranker edge survives post-2016.
- W contribution compressed post-2016 (+0.09 to +0.02), consistent with inverse-vol as a small helper and with partial dependence on the bond-equity decorrelation regime that weakened around 2022; treat +0.02 as regime-contingent, not a primary forward lever.
- Protective stack is crisis-concentrated: C, S, and P do most work in 2008-16; canary is cheap optionality, with about -0.08 Sharpe drag in 2017-26 for crisis insurance.
- Independence check is strong: no-canary MaxDD is -15.01%, still better than every benchmark, so drawdown control is load-bearing in trend, screen, and inverse-vol layers.
- Strong 2017-26 Sharpe is not driven by protection layers; forward reliability rests on R plus U, with C/S/P as crash insurance.

Decomposition caveat: R is a selected factor and was chosen partly in-sample, so attribution is partly retrospective. Per-half persistence is evidence against pure overfit, not proof of future magnitude.

## 8. Statistical honesty and caveats

Lead honesty statement:
- Signal survives the stated selection tests (DSR z about 3.9-5.4), but production configuration should still be treated as selected in-sample; forward degradation is driven by execution sensitivity and regime uncertainty, not only overfitting concerns.
- Natural overfitting concern is turn-of-month inflation, but the strong 2017-26 half is momentum-core driven: day-1 bp is flat (14.8 to 14.9) while gains come from rest-of-month.

Three-number framing for Sharpe:
- In-sample peak: 1.19.
- Selection-deflated in-sample: about 1.00.
- Forward expectation: about 0.72, range 0.62-0.85.

Forward haircut ladder uses measured selection deflation plus explicitly judgmental execution and regime haircuts; details in Section 8.1.

Significance framing:
- Versus the AAA-style benchmark and 60/40, this sample is too short to statistically confirm an edge at 95%; difference-CIs include zero, so evidence is favorable but statistically unresolved.
- Statistical significance in this memo is reserved for comparisons versus naive 12m momentum and buy-hold inverse-vol.

### 8.1 Forward-Sharpe haircut ladder

| Step | Type | Factor (central / band) | Resulting Sharpe |
|---|---|---|---:|
| 0. In-sample argmax (clean, T+1 MOO) | measured | -- | 1.19 |
| 1. Selection de-peak (expected-max SR0 over correlated search) | measured (DSR) | x 0.82 / [0.79, 0.86] | ~1.00 (0.94-1.02) |
| 2. Execution-realism haircut (month-end cliff, slippage) | judgmental (J) | x 0.85 / [0.765, 0.93] | ~0.83 (0.72-0.95) |
| 3. Regime non-stationarity haircut (OOS trend decay) | judgmental (J) | x 0.88 / [0.80, 0.95] | ~0.72 (0.62-0.85) |
| Forward central | synthesis | -- | ~0.72, range 0.62-0.85 |

Step anchoring:
- Step 1 (measured): selection inflation about 0.16-0.25 Sharpe from expected-max SR0 and peak-versus-median gaps.
- Step 2 (JUDGMENTAL): execution cliff is measured (EOM/T+1/T+2/T+3), but chosen forward factor is judgmental.
- Step 3 (JUDGMENTAL): regime haircut is a reasoned forward assumption, not a backtested forward result.

### 8.2 DSR appendix inputs (measured vs assumed)

Measured inputs (from production return stream and committed grid):

| Input | Value |
|---|---:|
| Observed SR_hat (per-day) | 0.07502 (ann 1.1908) |
| n (daily obs) | 4524 |
| skew | -0.3740 |
| excess kurtosis | 4.0282 |
| V_trials (grid SR variance, per-day) | 2.094e-5 (std 0.073 ann) |

Assumed input:

| Input | Value |
|---|---|
| Effective independent trials N | about 50-300 (central about 150; tested wider) |

Resulting expected-max SR0 and deflated z by N (daily frame):

| N | SR0 (ann) | DSR | z |
|---|---:|---:|---:|
| 40 | 0.159 | 1.0000 | 4.29 |
| 80 | 0.178 | 1.0000 | 4.22 |
| 200 | 0.201 | 1.0000 | 4.13 |
| 500 | 0.222 | 1.0000 | 4.03 |
| 1000 | 0.236 | 1.0000 | 3.97 |
| 2000 | 0.250 | 1.0000 | 3.91 |

Monthly frame gives DSR about 1.0000 with z up to 5.39, so reported z band is 3.91-5.39. Interpretation: DSR answers signal reality (passes decisively), not forward Sharpe magnitude.

### 8.3 Regime scenario decomposition (not prediction)

| Regime | Historical CPM Sharpe | Forward scenario | Note |
|---|---|---|---|
| A trending or low-vol (historical classifier share: 65%) | 1.41 (SPY 0.81, 60/40 0.94) | about 0.86 | 2017-26 is mostly this regime. |
| B choppy or high-vol (historical classifier share: 35%) | 0.96 (SPY 0.62, 60/40 0.68) | about 0.59 | B-regime conditional scenario: just below the unconditional low 0.62 by construction because it conditions on a choppy regime persisting; still positive. |
| C stagflation or inflation-rotation | 1970s proxy 0.8-1.0; 2021-22 analog CPM 1.21 versus 60/40 -0.19 | about 0.77 | Practical relative headline: this is where conventional 60/40 defense is weakest. |

Read:
- Practical headline relative result is the inflation analog: 2021-22 shows CPM 1.21 versus 60/40 -0.19.
- B-regime conditional scenario is about 0.59 (just below the unconditional forward-range low of 0.62 by construction, since it conditions on a choppy regime persisting); still positive.
- The 65/35 split is historical frequency from this sample's classifier, not a forward assumption; regime mix is non-stationary.
- Use the three-row scenario table with your own regime prior; do not collapse scenarios into a single mix-weighted forward point estimate.
- This is scenario decomposition, not prediction.

Selection-space disclosure (beyond the 80-cell grid):
- Canary OR versus AND combinator and canary pair choice.
- 13612U horizon set choice {r1, r3, r6, r12}.
- Strict-4-of-8 safe threshold choice.
- 6-factor inclusion lattice.
- Effective search size is about 50-300 correlated trials, not only the visible 80 cells.

Other caveats:
- Bootstrap CI width is material; fine ranking claims carry uncertainty.
- Ladder monotonicity holds in clean Calmar and fails in extended Calmar.
- Ladder attribution is order-dependent by construction (R -> C -> U -> W -> S -> P).
- U, R, and W effects attribute to the full AAA-like factorial baseline -> CPM toggle as defined; each bundles multiple sub-changes.
- Concentration risk is disclosed: top holding is 20.9% clean, top-3 are 52.8% clean.
- Extended-window interpretation carries proxy-tail uncertainty; clean window is decisive.

## 9. Robustness

Clean Sharpe unless noted. Any extended-window references remain proxy-informed robustness only.

| Check | Result |
|---|---|
| Universe SPY-swap (drop QQQ/SPHQ) | 1.01 (-0.18) \| AAA variant: 1.03 \| Keller-GTAA10: 0.99 \| Faber-GTAA5: 0.81; all remain in the same quality band, and all MaxDD are shallower than 13.7% |
| Top-K {3,4,5,6} | 0.95 / 1.19 / 1.09 / 1.02 |
| Ranking momentum {Faber-voladj, 13612U, 12m, 6m, 3m} | 1.19 / 1.08 / 0.99 / 0.93 / 0.92 |
| Risky-block inverse-vol lookback {252, 504} | gap <= 0.03, with 504 > 252 |
| Interaction grid (80 cells; 40 distinct configs) | Production config (K=4, Faber-voladj, 504d, inverse-vol) is #1 on both Sharpe and Calmar; Sharpe median 0.94, IQR 0.92-0.98, min 0.83, max 1.19; 21% of cells > 1.0 and 5% > 1.1 |
| Cost {0, 10, 30 bps/side} | 1.24 / 1.19 / 1.10 |
| Weighting {inverse-vol, equal-weight} | 1.19 / 1.13 |
| Subperiod {2008-16, 2017-26} | 1.00 / 1.38; rolling-36m Sharpe min 0.71 / median 1.41 / max 2.26 (never negative) |
| Fill convention at fixed signal date {same-day MOC, T+1 MOO, T+1 close, T+2 open} | 1.2063 / 1.1910 / 1.15 / 1.15; lag cost from same-day to headline T+1 MOO is -0.015 Sharpe |
| Signal/rebalance-date offset {EOM, EOM+1, EOM+2, EOM+3 bd} | 1.2063 / 1.01 / 0.97 / 0.91 |
| Lookahead audit | none; signal is point-in-time (loc[:sig_d]) and execution is strictly future (> sig_d); headline 1.1910 is conservative true T+1-MOO re-accounting versus same-day MOC 1.2063 |

### 9.1 Leave-one-asset-out robustness (clean window)

Drop each risky asset one at a time and rerun full CPM stack over clean window.

| Dropped | Sharpe | dSharpe | MaxDD | Calmar | dCalmar |
|---|---:|---:|---:|---:|---:|
| (none) baseline | 1.1910 | -- | -12.67% | 1.0615 | -- |
| ex-QQQ | 1.0140 | -0.1770 | -11.34% | 0.9285 | -0.1330 |
| ex-SPHQ | 1.0339 | -0.1570 | -12.24% | 0.9126 | -0.1489 |
| ex-EFA | 1.1799 | -0.0111 | -11.36% | 1.1102 | +0.0487 |
| ex-EEM | 1.2069 | +0.0159 | -11.06% | 1.1457 | +0.0842 |
| ex-VNQ | 1.1163 | -0.0747 | -13.73% | 0.8813 | -0.1803 |
| ex-GLD | 1.0579 | -0.1331 | -14.57% | 0.8277 | -0.2338 |
| ex-TLT | 1.0823 | -0.1087 | -13.86% | 0.9132 | -0.1483 |
| ex-DBC | 1.1248 | -0.0662 | -12.44% | 1.0155 | -0.0460 |

Read:
- No single-asset dependence break: all ex-asset variants keep Sharpe >= 1.01 and MaxDD shallower than -14.57%.
- Return engine concentration sits in QQQ/SPHQ (largest dSharpe drops).
- Drawdown-control concentration sits in GLD and VNQ (largest Calmar and MaxDD deterioration when removed).

The 80-cell interaction grid shows the baseline is the literal argmax, with selection-on-peak bias of +0.25 Sharpe versus grid median and +0.025 versus the second-best cell. Cliffs exist: dropping Faber ranker to 6m costs about 0.26 Sharpe, and K=4 to K=3 costs about 0.24. Interactions are material: Faber leads at K=4 but trails 13612U at K=3, and with a 3m ranker the K optimum flips from 4 to 6.

Mitigants: region and direction are stable across both windows (Faber + K=4-5 + inverse-vol stays top, and extended 1.2643 is also grid-top), and bootstrap CI is [0.7866, 1.5969]. Residual risks: execution discipline matters (a few-day slip to EOM+3 drops Sharpe to 0.91), and selection-on-peak inflation remains in the last about 0.025-0.06 Sharpe slice (504-vs-252 and inverse-vol-vs-equal at optimum). CPM should not be judged on the 1.19 peak alone; the defensible claim is economically favorable point estimates for the Faber / top-4 / inverse-vol family, with stronger statistical support versus naive 12m and buy-hold inverse-vol than versus the AAA-style benchmark and 60/40 (where clean-window difference CIs include zero). Treat 1.19 as in-sample peak, about 1.00 as selection-deflated in-sample, and about 0.72 (0.62-0.85) as forward expectation.

## 10. Conclusion

In backtest over both windows, CPM's strongest claim is capital preservation and tail control: shallower drawdown point estimates, stronger drawdown-adjusted ratios, and fast crisis recovery under month-end signal and next-session-open execution. Drawdown control is not solely canary-dependent in point terms, with no-canary MaxDD still at -15.01%, better than every benchmark. Versus the AAA-style benchmark and 60/40, difference tests are underpowered at this sample length and CIs include zero, so results are favorable but statistically unresolved; significance still clears versus naive 12m and buy-hold inverse-vol. MaxDD should be read with Martin/Ulcer and paired-bootstrap difference framing because MaxDD alone is high-variance. Raw Sharpe is credible but moderate after honesty haircuts: 1.19 in-sample peak, about 1.00 selection-deflated in-sample, and about 0.72 forward range center. Benchmark comparison, decomposition, and robustness checks support CPM as a capital-preservation-first vehicle with a modest forward Sharpe profile, not a raw-return maximizer.

## 11. Reproduction appendix

### 11.1 Code pointers

- `cpm_live.py` (CPM construction, canary, safe selector, backtest wiring)
- `build_dashboard.py` (reporting and summary generation)

### 11.2 Full parameter dictionary

| Key | Value |
|---|---|
| trend_universe | [QQQ, SPHQ, EFA, EEM, VNQ, GLD, TLT, DBC] |
| safe_pool | [SHV, IEF] |
| ranker | m_faber / rv_252d |
| trend_filter | m_faber > 0 |
| top_k | 4 |
| risky_weight_rule | inverse-vol over surviving positives |
| risky_fraction_rule | strict-4 partial-safe, min(n_pos,4)/4 |
| risky-block inverse-vol lookback | 504 trading days |
| canary_rule | m_13612U(HYG) > 0 OR m_13612U(TIP) > 0 |
| safe_rule | argmax m_13612U over SHV and IEF |
| rebalance | monthly |
| execution | month-end close signal, next-session open fill |
| transaction_cost_per_side | 10 bps |
| leverage | unlevered |
| reporting_sharpe_rf | 0 |
| excess_sharpe_reference | SHV |

### 11.3 Window dates used in this memo

- Clean window: 2008-05-30 to 2026-05-22.
- Extended window: 1995-01-31 to 2026-05-22.

### 11.4 Source anchors

- research/cpm_headline_numbers_findings.md
- research/cpm_iv4_final_numbers_findings.md
- research/four_scheme_metrics_martin_findings.md
- research/memo_na_fills_findings.md
- research/cpm_factorial_aaa_findings.md
- research/benchmark_audit_findings.md
- research/stagflation_1970s_cpm_crossasset_findings.md
- research/cpm_robust_universe_findings.md
- research/cpm_robust_param_findings.md
- research/cpm_robust_lookahead_findings.md
- research/cpm_grid_interaction_findings.md
- research/cpm_benchmarks_proper_findings.md
- research/cpm_deflated_sharpe_findings.md
- research/cpm_execution_cliff_findings.md
- research/cpm_drawdown_stats_findings.md
- research/cpm_tom_decay_findings.md
- research/cpm_regime_scenarios_findings.md
- research/cpm_factor_stability_halves_findings.md
- research/cpm_class_significance_sanity_findings.md
- research/cpm_tip_proxy_compare_findings.md
- research/cpm_ext_extension_feasibility_findings.md
- research/cpm_ext_1995_recompute_findings.md
- research/cpm_ext_crises_findings.md
- research/memo_review_additions.md
- research/memo_review_additions_compute.json
- research/memo_fix_numbers.json
