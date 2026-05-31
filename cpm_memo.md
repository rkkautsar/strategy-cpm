# CPM Research Memo

Current state: convention-locked monthly ETF implementation. Clean window uses full real-open coverage. Extended window includes proxy-backed pre-ETF segments. Metrics are post-cost and use month-end signal with next-session-open execution.

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
CPM is a capital-preservation-first momentum strategy. Drawdown-adjusted point gaps are large: Calmar 1.06 and Martin 3.96 versus 0.23-0.42 and 1.0-1.6 across the benchmark set, with MaxDD -12.67% versus -21.76% to -34.92%. The edge is broad, not GFC-only: CPM's own worst drawdown is 2025-04-08 at -12.67%, while the GFC drawdown is -11.88% (extended continuous-curve, capturing the full episode), and ex-GFC point metrics still lead. The edge is canary-independent: no-canary MaxDD is -15.01%, still shallower than every benchmark. Honesty: versus canonical AAA and 60/40, significance tests are underpowered at this sample length. MaxDD and Calmar are single-path high-variance statistics, so difference-CIs are wide; this supports both a real structural edge and luck, not a no-edge claim. Drawdown differences are still significant versus naive 12m and buy-hold inverse-vol.

2) RETURN - real but modest.
Signal quality is real, with DSR z about 3.9-5.4 and selection inflation about 0.16-0.25 Sharpe, so edge is not only a search artifact. Forward Sharpe is about 0.72 (range 0.62-0.85). Raw-Sharpe edge versus canonical AAA and 60/40 is within statistical noise.

3) RISK - execution discipline is load-bearing.
Month-end alignment matters: EOM to EOM+1 drops Sharpe 1.21 to 1.01 (close-to-close frame), and EOM+3 is 0.91. Turn-of-month premium is regime-cyclical, not a steady decay, and is dormant in the live tail. Canary is cheap crisis optionality: about -0.08 Sharpe drag in calm regimes in exchange for about 2.35 points of overall MaxDD protection (-15.01% no-canary to -12.67%), concentrated in crises. This canary leg is independent of the broader drawdown-control leg.

4) INVESTOR FIT - capital-preservation-first.
CPM fits investors who want tail control plus a real but modest return edge. Practical relative headline is the 2021-22 inflation analog (2021-04..2022-12, n=21): CPM 1.21 versus 60/40 -0.19, where conventional portfolios have the least defense. B-regime conditional scenario is about 0.59 (just below the unconditional forward-range low of 0.62 by construction, since it conditions on a choppy regime persisting); still positive. CPM is not a raw-return or high-Sharpe maximizer.

Turnover:
- Clean: 2.616 one-way per year, 13.4% fully-safe months.
- Extended: 2.733 one-way per year, 10.1% fully-safe months.

## 2. Investment thesis and economic rationale

CPM is a tail-control vehicle built on cross-asset momentum. The return engine is the R plus U stack (vol-adjusted Faber ranker plus CPM universe), with W as a smaller helper. C, S, and P are protective layers that reduce crash depth and speed recovery, with value concentrated in crisis regimes.

### 2.1 Execution-timing cliff and operational risk

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
  - rv_252d = stdev(simple daily returns, 252d) * sqrt(252).

### 3.2 CPM rule stack

1. Compute score = m_faber / rv_252d for each risky asset in {QQQ, SPHQ, EFA, EEM, VNQ, GLD, TLT, DBC}.
2. Keep only assets with m_faber > 0.
3. Rank by score and keep top 4.
4. If canary is off, allocate full capital to safe selector.
5. If canary is on:
   - n_pos = number of surviving positives (0..4).
   - risky_fraction = min(n_pos, 4) / 4.
   - safe_fraction = 1 - risky_fraction.
   - risky block uses inverse-vol weights across surviving positives with 504-day volatility window (covariance diagonal).
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
| Volatility lookback (covariance diagonal) | Window | 504 trading days |
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

## 5. Headline results

### 5.1 CPM headline metrics

Clean Sharpe is 1.1910 with bootstrap 95% CI [0.7866, 1.5969].

| Window | Sharpe | CAGR | Vol | MaxDD | Calmar | Martin | Ulcer | Excess Sharpe vs SHV |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Clean | 1.1910 | 13.44% | 11.16% | -12.67% | 1.0615 | 3.9646 | 3.39% | 1.0719 |
| Extended | 1.2643 | 14.00% | 10.78% | -15.93% | 0.8791 | 3.9767 | 3.52% | 1.0007 |

Extended Sharpe bootstrap (stationary block bootstrap, B=2000, block=21, seed=42): point 1.2643, 95% CI [0.9430, 1.5986], median 1.2619.

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
| Extended | 2.733 | 10.1% |

### 5.5 Canonical benchmark set and significance

Headline benchmark set uses canonical AAA (Adaptive Asset Allocation; Butler, Philbrick, Gordillo, Varadi; SSRN 2328254) plus investor alternatives. AAA here is the full 10-asset universe; this supersedes the older internal 8-of-10 factorial baseline for headline comparison.

Clean window (2008-05-30 to 2026-05-22):

| Series | Sharpe | CAGR | MaxDD | Calmar | Martin |
|---|---:|---:|---:|---:|---:|
| CPM | 1.19 | 13.44% | -12.67% | 1.06 | 3.96 |
| Canonical AAA (SPY, EZU, EWJ, EEM, IYR, RWX, IEF, TLT, DBC, GLD) | 0.94 | 9.23% | -21.76% | 0.42 | 1.62 |
| 60/40 (SPY/IEF) | 0.79 | 8.75% | -29.82% | 0.29 | 1.40 |
| Naive 12m momentum (no canary, equal-weight) | 0.65 | 8.14% | -26.59% | 0.31 | 1.02 |
| Buy-hold inverse-vol | 0.69 | 8.15% | -34.92% | 0.23 | 1.11 |

Sharpe difference test (CPM minus benchmark, paired block bootstrap, 95% CI):

| Comparator | dSharpe | 95% CI | Includes zero? |
|---|---:|---|---|
| Canonical AAA | +0.25 | [-0.069, +0.607] | Yes |
| 60/40 | +0.40 | [-0.069, +0.826] | Yes |
| Naive 12m | +0.54 | [+0.178, +0.925] | No |
| Buy-hold inverse-vol | +0.51 | [+0.086, +0.907] | No |

Drawdown-adjusted difference tests (CPM minus benchmark, paired block bootstrap, 95% CI):

| Metric | Comparator | Point diff | 95% CI | Includes no-diff point? |
|---|---|---:|---|---|
| MaxDD gap (percentage points, positive = shallower CPM DD) | Canonical AAA | +9.10 | [-5.86, +13.54] | Yes |
| MaxDD gap (percentage points, positive = shallower CPM DD) | 60/40 | +17.16 | [-3.00, +23.71] | Yes |
| MaxDD gap (percentage points, positive = shallower CPM DD) | Naive 12m | +13.92 | [+1.52, +31.09] | No |
| MaxDD gap (percentage points, positive = shallower CPM DD) | Buy-hold inverse-vol | +22.25 | [+0.06, +30.21] | No |
| Calmar difference (positive = better CPM) | Canonical AAA | +0.6399 | [-0.1162, +0.9142] | Yes |
| Calmar difference (positive = better CPM) | 60/40 | +0.7713 | [-0.0213, +1.1070] | Yes |
| Calmar difference (positive = better CPM) | Naive 12m | +0.7579 | [+0.1548, +1.1379] | No |
| Calmar difference (positive = better CPM) | Buy-hold inverse-vol | +0.8313 | [+0.1109, +1.1800] | No |
| Martin difference (positive = better CPM) | Canonical AAA | +2.3504 | [-0.1371, +3.8059] | Yes |
| Martin difference (positive = better CPM) | 60/40 | +2.5738 | [-0.3145, +4.5695] | Yes |
| Martin difference (positive = better CPM) | Naive 12m | +2.9550 | [+0.7683, +4.7088] | No |
| Martin difference (positive = better CPM) | Buy-hold inverse-vol | +2.8682 | [+0.4540, +4.7908] | No |

Read:
- Versus canonical AAA and 60/40, difference-CI tests are underpowered at this 18y sample length: Sharpe, MaxDD, and Calmar intervals are structurally wide.
- Underpowered is not absent: evidence is consistent with both structural advantage and luck, not with a no-edge conclusion. Practical point gaps still matter: CPM MaxDD is -12.67% versus -21.76% to -34.92%.
- Class-norm context: sub-significance versus 60/40 is not CPM-specific. Adaptive Asset Allocation (SSRN 2328254, 1995-2015) has in-sample dSharpe +0.084 (not significant), and the Keller/Keuning HAA paper variant (SSRN 4346906) over about 52 years has dSharpe +0.246 with CI [-0.058, +0.540] (still not significant).
- CPM point edge is competitive or better: dSharpe versus 60/40 is +0.40, while peer 18y point edges are about +0.20 (HAA) and +0.18 (AAA). CPM Calmar is 1.06 versus peer 0.66-0.74 (HAA 0.656, AAA 0.743 at 18y) and 60/40 at 0.29. Peer comparisons use a monthly-close engine, so cross-engine comparison to mooex is approximate.
- Canary independence is explicit: disabling canary moves MaxDD from -12.67% to -15.01%, and -15.01% still beats every benchmark MaxDD. Canary adds about 2.35 points of protection; drawdown control is load-bearing in the trend, screen, and inverse-vol stack, not dependent on canary signal quality.
- Significance still clears versus naive 12m and buy-hold inverse-vol.

Extended window (per-series start where available):

| Series | Start | Sharpe | CAGR | MaxDD | Calmar | Martin |
|---|---|---:|---:|---:|---:|---:|
| CPM | 1995-01-31 | 1.26 | 14.00% | -15.93% | 0.88 | 3.98 |
| Canonical AAA | 2008-01-19 | 0.93 | 9.07% | -21.76% | 0.42 | 1.60 |
| 60/40 | 1999-03-10 | 0.69 | 7.31% | -31.44% | 0.23 | 1.07 |
| Naive 12m momentum | 1999-03-10 | 0.82 | 10.11% | -26.59% | 0.38 | 1.43 |
| Buy-hold inverse-vol | 1999-03-10 | 0.84 | 9.56% | -35.61% | 0.27 | 1.44 |

Canonical AAA remains limited by RWX inception plus momentum warmup; that is why canonical AAA does not extend to the 1995 CPM extended start in this framework.

## 6. CPM 2^6 decomposition

The CPM 2^6 decomposition runs from an AAA all-OFF baseline (000000) to CPM all-ON (111111), where OFF uses 6-month momentum (R), minimum-variance weighting on weighted 126d/20d covariance (W), the 8-of-10 SPY-set universe (U; EWJ and RWX excluded, EFA and VNQ stand in for EZU and IYR slash-pairs per benchmark_audit), and no canary (C).

This 000000 AAA line is the internal factorial baseline only. It is not the headline external benchmark in Section 5.5.

- Baseline all-OFF (factorial AAA baseline, 8-of-10 available assets): clean Sharpe 0.7869, MaxDD -23.21%, Calmar 0.3188; extended Sharpe 0.9040, Calmar 0.3626.
- All-ON is production CPM: clean Sharpe 1.1910, MaxDD -12.67%, Calmar 1.0615; extended Sharpe 1.2643, MaxDD -15.93%, Calmar 0.8791.

Factor mapping is C,U,R,S,W,P where OFF is AAA baseline and ON is CPM. [FLIP] means on-minus-off changes sign across backgrounds.

Clean-lens decomposition story:
- R is top first-order driver (+0.2048 Sharpe, +0.2411 Calmar [FLIP]).
- C is large contributor (+0.1104 Sharpe, +0.2172 Calmar [FLIP]) because AAA has no canary.
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
| Baseline (AAA) | 000000 | 0.7869 | 0.3188 | -23.21% | 0.9040 | 0.3626 | -23.21% |
| +R | 001000 | 0.9128 | 0.3637 | -23.54% | 0.9645 | 0.3591 | -23.54% |
| +C | 101000 | 1.0527 | 0.7203 | -12.96% | 1.0479 | 0.6347 | -13.90% |
| +U | 111000 | 1.2062 | 0.7491 | -17.52% | 1.1707 | 0.6929 | -17.52% |
| +W | 111010 | 1.1785 | 0.9606 | -14.22% | 1.2405 | 0.8887 | -15.93% |
| +S | 111110 | 1.1491 | 1.0614 | -12.67% | 1.2533 | 0.9069 | -15.93% |
| +P (all-ON production CPM) | 111111 | 1.1910 | 1.0615 | -12.67% | 1.2643 | 0.8791 | -15.93% |

Clean ladder Calmar is monotone from 0.3188 to 1.0615. Extended ladder is not monotone: +R dips Calmar from 0.3626 to 0.3591 and +P dips Calmar from 0.9069 to 0.8791.

## 7. Design notes

### 7.1 Ranker comparison

CPM ranker comparison remains vol-adjusted Faber versus plain 12-month momentum. Section 6 reports R-factor effects versus AAA's native 6-month ranker (+0.2048 clean dSharpe), while this section isolates a different baseline (+0.1994 clean, +0.1488 extended).

- Clean Sharpe lift: +0.1994, paired 95% CI [-0.0275, +0.4480].
- Extended Sharpe lift: +0.1488, paired 95% CI [-0.0270, +0.3275].
- Directional signal remains high but not significant at 95%: P=95.3% clean and about 94.7% extended.

### 7.2 Universe analysis

Universe factor U is positive in Sharpe and Calmar by window (+0.0837 clean dSharpe, +0.0824 extended dSharpe; +0.0657 clean dCalmar, +0.0148 extended dCalmar). Interaction terms U x R and C x R carry major contribution.

### 7.3 Weighting interpretation

Weighting appears as W factor in the decomposition: AAA baseline minimum-variance versus CPM inverse-vol over surviving positives. This is decomposition attribution, not a CPM variant family.

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

Stagflation defense in CPM comes from cross-asset rotation plus absolute-momentum screening. Historical 1970s proxy reconstructions are artifact-prone, so precise percentage outcomes are unreliable and are not used as headline evidence. Keep only the qualitative read: CPM can rotate into inflation-linked leaders when those trends dominate.

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
- Protective stack is crisis-concentrated: C, S, and P do most work in 2008-16; canary is cheap optionality, with about -0.08 Sharpe drag in 2017-26 for crisis insurance.
- Independence check is strong: no-canary MaxDD is -15.01%, still better than every benchmark, so drawdown control is load-bearing in trend, screen, and inverse-vol layers.
- Strong 2017-26 Sharpe is not driven by protection layers; forward reliability rests on R plus U, with C/S/P as crash insurance.

Decomposition caveat: R is a selected factor and was chosen partly in-sample, so attribution is partly retrospective. Per-half persistence is evidence against pure overfit, not proof of future magnitude.

## 8. Statistical honesty and caveats

Lead honesty statement:
- Selection-robust signal is real (DSR z about 3.9-5.4), and forward degradation is driven by execution sensitivity and regime uncertainty, not overfitting.
- Natural overfitting concern is turn-of-month inflation, but the strong 2017-26 half is momentum-core driven: day-1 bp is flat (14.8 to 14.9) while gains come from rest-of-month.

Three-number framing for Sharpe:
- In-sample peak: 1.19.
- Selection-deflated in-sample: about 1.00.
- Forward expectation: about 0.72, range 0.62-0.85.

Forward haircut ladder:
- Start 1.19 in-sample peak.
- De-peak for selection.
- Haircut for execution cliff discipline.
- Haircut for regime non-stationarity.
- Result about 0.72 central, 0.62-0.85 range.

Significance framing:
- Versus canonical AAA and 60/40, this sample is too short to statistically confirm the edge at 95%; wide difference-CIs reflect low power, not evidence of no edge.

### 8.1 Regime scenario decomposition (not prediction)

| Regime | Historical CPM Sharpe | Forward scenario | Note |
|---|---|---|---|
| A trending or low-vol (historical classifier share: 65%) | 1.41 (SPY 0.81, 60/40 0.94) | about 0.86 | 2017-26 is mostly this regime. |
| B choppy or high-vol (historical classifier share: 35%) | 0.96 (SPY 0.62, 60/40 0.68) | about 0.59 | B-regime conditional scenario: just below the unconditional low 0.62 by construction because it conditions on a choppy regime persisting; still positive. |
| C stagflation or inflation-rotation | 1970s proxy 0.8-1.0; 2021-22 analog CPM 1.21 versus 60/40 -0.19 | about 0.77 | Practical relative headline: this is where conventional 60/40 defense is weakest. |

Read:
- Practical headline relative result is the inflation analog: 2021-22 shows CPM 1.21 versus 60/40 -0.19.
- B-regime conditional scenario is about 0.59 (just below the unconditional forward-range low of 0.62 by construction, since it conditions on a choppy regime persisting); still positive.
- The 65/35 split is historical frequency from this sample's classifier, not a forward assumption; regime mix is non-stationary.
- Use the three-row scenario table with your own regime prior; do not mix-weight to a single forward point estimate such as about 0.77.
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
- U, R, and W effects attribute to the full AAA -> CPM toggle as defined; each bundles multiple sub-changes.
- Concentration risk is disclosed: top holding is 20.9% clean, top-3 are 52.8% clean.
- Extended-window interpretation carries proxy-tail uncertainty; clean window is decisive.

## 9. Robustness

Clean Sharpe unless noted.

| Check | Result |
|---|---|
| Universe SPY-swap (drop QQQ/SPHQ) | 1.01 (-0.18) \| AAA variant: 1.03 \| Keller-GTAA10: 0.99 \| Faber-GTAA5: 0.81; all remain in the same quality band, and all MaxDD are shallower than 13.7% |
| Top-K {3,4,5,6} | 0.95 / 1.19 / 1.09 / 1.02 |
| Ranking momentum {Faber-voladj, 13612U, 12m, 6m, 3m} | 1.19 / 1.08 / 0.99 / 0.93 / 0.92 |
| Covariance lookback {252, 504} | gap <= 0.03, with 504 > 252 |
| Interaction grid (80 cells; 40 distinct configs) | Production config (K=4, Faber-voladj, 504d, inverse-vol) is #1 on both Sharpe and Calmar; Sharpe median 0.94, IQR 0.92-0.98, min 0.83, max 1.19; 21% of cells > 1.0 and 5% > 1.1 |
| Cost {0, 10, 30 bps/side} | 1.24 / 1.19 / 1.10 |
| Weighting {inverse-vol, equal-weight} | 1.19 / 1.13 |
| Subperiod {2008-16, 2017-26} | 1.00 / 1.38; rolling-36m Sharpe min 0.71 / median 1.41 / max 2.26 (never negative) |
| Execution lag {same-day MOC, T+1 MOO, T+1 close, T+2 open} | 1.2063 / 1.1910 / 1.15 / 1.15; lag cost from same-day to headline T+1 MOO is -0.015 Sharpe |
| Rebalance day {EOM, +1, +2, +3 bd} | 1.2063 / 1.01 / 0.97 / 0.91 |
| Lookahead audit | none; signal is point-in-time (loc[:sig_d]) and execution is strictly future (> sig_d); headline 1.1910 is conservative true T+1-MOO re-accounting versus same-day MOC 1.2063 |

The 80-cell interaction grid shows the baseline is the literal argmax, with selection-on-peak bias of +0.25 Sharpe versus grid median and +0.025 versus the second-best cell. Cliffs exist: dropping Faber ranker to 6m costs about 0.26 Sharpe, and K=4 to K=3 costs about 0.24. Interactions are material: Faber leads at K=4 but trails 13612U at K=3, and with a 3m ranker the K optimum flips from 4 to 6.

Mitigants: region and direction are stable across both windows (Faber + K=4-5 + inverse-vol stays top, and extended 1.2643 is also grid-top), and bootstrap CI is [0.7866, 1.5969]. Residual risks: execution discipline matters (a few-day slip to EOM+3 drops Sharpe to 0.91), and selection-on-peak inflation remains in the last about 0.025-0.06 Sharpe slice (504-vs-252 and inverse-vol-vs-equal at optimum). Treat 1.19 as in-sample peak, about 1.00 as selection-deflated in-sample, and about 0.72 (0.62-0.85) as forward expectation.

## 10. Conclusion

In backtest over both windows, CPM's strongest claim is capital preservation and tail control: shallower drawdown point estimates, stronger drawdown-adjusted ratios, and fast crisis recovery under month-end signal and next-session-open execution. Those drawdown gaps are broad and canary-independent in point terms, with no-canary MaxDD still at -15.01%, better than every benchmark. Versus canonical AAA and 60/40, difference tests are underpowered at this sample length, so non-significance does not imply no edge; significance still clears versus naive 12m and buy-hold inverse-vol. Raw Sharpe is credible but moderate after honesty haircuts: 1.19 in-sample peak, about 1.00 selection-deflated in-sample, and about 0.72 forward range center. Canonical benchmark comparison, decomposition, and robustness checks support CPM as a capital-preservation-first vehicle with a real but modest forward Sharpe edge, not a raw-return maximizer.

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
| volatility_lookback_days (covariance diagonal) | 504 |
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
- research/memo_fix_numbers.json
