# CPM Research Memo

Current state: convention-locked monthly ETF implementation. Clean window uses full real-open coverage. Extended window includes proxy-backed pre-ETF segments. Metrics are post-cost and use month-end signal with next-session-open execution.

## 0. Header and metadata

- Strategy: CPM (Cross-asset Parity Momentum).
- Risky universe: QQQ, SPHQ, EFA, EEM, VNQ, GLD, TLT, DBC.
- Safe assets: SHV, IEF.
- Windows:
  - Clean: 2008-05-30 to 2026-05-22 (18.0 years).
  - Extended: 1999-03-10 to 2026-05-22 (27.2 years), with proxy-backed segments before full ETF coverage.
- Costs: 10 bps per side, embedded in all tables.
- Sharpe convention: raw Sharpe (rf = 0) and excess Sharpe versus SHV.
- Rebalance and leverage: monthly rebalance, unlevered.
- Execution convention: signal at month-end close, trade at next-session open.

## 1. Executive summary

In backtest, CPM posts strong risk-adjusted returns in both windows with shallow crisis drawdowns and fast recovery.

Headline metrics:
- Clean: Sharpe 1.1910, CAGR 13.44%, Vol 11.16%, MaxDD -12.67%, Calmar 1.0615, Martin 3.9646 (Ulcer 3.39%), Excess-Sharpe 1.0719.
- Extended: Sharpe 1.2142, CAGR 13.71%, Vol 11.09%, MaxDD -15.93%, Calmar 0.8608, Martin 3.8201 (Ulcer 3.59%), Excess-Sharpe 1.0062.

Crisis profile:
- GFC: -11.88% (2008-03..10), recovery +63d.
- COVID: -10.06% (2020-03), recovery +28d.
- 2022: -7.64% global episode and -6.33% within-calendar, recovery +40d.

Bootstrap 95% CI for clean Sharpe: [0.7866, 1.1964, 1.5969], point 1.1910.

Turnover:
- Clean: 2.616 one-way per year, 13.4% fully-safe months.
- Extended: 2.768 one-way per year, 11.0% fully-safe months.

## 2. Investment thesis and economic rationale

Cross-asset time-series momentum persists through risk-on and risk-off cycles. CPM applies a unified pipeline: vol-adjusted Faber ranking, positive-trend screen, top-4 selection, inverse-vol weighting across surviving positives, then strict-4 partial-safe scaling. HYG-OR-TIP canary and timed SHV/IEF safe selection add broad-market participation with explicit risk scaling when breadth is thin.

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
  - Extended: 1999-03-10 to 2026-05-22.
- Costs: 10 bps per side, embedded in all metrics.
- Execution: signal at month-end close, fill at next-session open (T+1 MOO exact).
- Extended-window interpretation: proxy-backed segments exist before full ETF coverage; clean window is decisive lens.
- TIP-proxy caveat: before real TIP history, extended-window TIP uses an inflation-blind proxy path, so TIP-canary-dependent extended conclusions are weaker than clean-window conclusions.

## 5. Headline results

### 5.1 CPM headline metrics

| Window | Sharpe | CAGR | Vol | MaxDD | Calmar | Martin | Ulcer | Excess Sharpe vs SHV |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Clean | 1.1910 | 13.44% | 11.16% | -12.67% | 1.0615 | 3.9646 | 3.39% | 1.0719 |
| Extended | 1.2142 | 13.71% | 11.09% | -15.93% | 0.8608 | 3.8201 | 3.59% | 1.0062 |

### 5.2 Crisis behavior

Global drawdown episodes:

| Crisis | Peak | Trough | Depth | Recovery | Trough to recovery |
|---|---|---|---:|---|---:|
| GFC | 2008-03-14 | 2008-10-14 | -11.88% | 2008-12-16 | +63d |
| COVID | 2020-03-06 | 2020-03-18 | -10.06% | 2020-04-15 | +28d |
| 2022 | 2021-11-24 | 2022-01-27 | -7.64% | 2022-03-08 | +40d |

Within-calendar windows:

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

CPM-over-AAA benchmark comparison in Section 5.5 is point-estimate only; no difference-CI is computed.

### 5.4 Turnover and fully-safe months

| Window | One-way turnover per year | Fully-safe months |
|---|---:|---:|
| Clean | 2.616 | 13.4% |
| Extended | 2.768 | 11.0% |

### 5.5 AAA benchmark comparison

AAA benchmark specification: 8-of-10 (EWJ and RWX excluded: not in the data panel; EFA and VNQ stand in for EZU and IYR slash-pairs per benchmark_audit), assets are SPY/EFA/EEM/VNQ/IEF/TLT/DBC/GLD, 6m momentum, top-half, minimum-variance, no canary.

| Window | Series | Sharpe | CAGR | Vol | MaxDD | Calmar |
|---|---|---:|---:|---:|---:|---:|
| Clean | CPM | 1.1910 | 13.44% | 11.16% | -12.67% | 1.0615 |
| Clean | AAA benchmark | 0.7869 | 7.40% | 9.71% | -23.21% | 0.3188 |
| Extended | CPM | 1.2142 | 13.71% | 11.09% | -15.93% | 0.8608 |
| Extended | AAA benchmark | 0.8696 | 8.41% | 9.84% | -23.21% | 0.3624 |

CPM leads the AAA benchmark on Sharpe, CAGR, Calmar, and drawdown depth in both windows.

This CPM-over-AAA benchmark read is a point-estimate comparison, not a tested difference.

## 6. CPM 2^6 decomposition

The CPM 2^6 decomposition runs from an AAA all-OFF baseline (000000) to CPM all-ON (111111), where OFF uses 6-month momentum (R), minimum-variance weighting on weighted 126d/20d covariance (W), the 8-of-10 SPY-set universe (U; EWJ and RWX excluded, EFA and VNQ stand in for EZU and IYR slash-pairs per benchmark_audit), and no canary (C).

- Baseline all-OFF (AAA, 8-of-10 available assets): clean Sharpe 0.7869, MaxDD -23.21%, Calmar 0.3188; extended Sharpe 0.8696, Calmar 0.3624.
- All-ON is production CPM: clean Sharpe 1.1910, MaxDD -12.67%, Calmar 1.0615; extended Sharpe 1.2142, MaxDD -15.93%, Calmar 0.8608.

Factor mapping is C,U,R,S,W,P where OFF is AAA baseline and ON is CPM. [FLIP] means on-minus-off changes sign across backgrounds.

Clean-lens decomposition story:
- R is top first-order driver (+0.2048 Sharpe, +0.2411 Calmar [FLIP]).
- C is large contributor (+0.1104 Sharpe, +0.2172 Calmar [FLIP]) because AAA has no canary.
- U and W are moderate net positive on both metrics; S is slightly Sharpe-negative but Calmar-positive (drawdown-control contribution).
- P is diluted in marginal averages (+0.0482 Sharpe, +0.0886 Calmar [FLIP]) because it is inert when S is OFF and breadth stays 4; P value is concentrated in S x P (+0.0886 clean Calmar, +0.0760 extended Calmar).

| Factor | CLEAN dSharpe | CLEAN dCalmar | EXT dSharpe | EXT dCalmar |
|---|---:|---:|---:|---:|
| Ranker (R) | +0.2048 | +0.2411 [FLIP] | +0.1002 | +0.1414 [FLIP] |
| Canary (C) | +0.1104 | +0.2172 [FLIP] | +0.0786 | +0.1788 [FLIP] |
| Universe (U) | +0.0837 [FLIP] | +0.0657 [FLIP] | +0.0584 [FLIP] | -0.0043 [FLIP] |
| Screen (S, positive-trend) | -0.0228 [FLIP] | +0.0463 [FLIP] | -0.0080 [FLIP] | +0.0386 [FLIP] |
| Weighting only (W) | +0.0127 [FLIP] | +0.0646 [FLIP] | +0.0872 | +0.1089 [FLIP] |
| Partial-safe (P) | +0.0482 | +0.0886 [FLIP] | +0.0392 | +0.0808 [FLIP] |

CPM key two-way interactions (Calmar deltas):

| Interaction | CLEAN dCalmar | EXT dCalmar |
|---|---:|---:|
| U x R | +0.1392 | +0.0979 |
| S x P | +0.0886 | +0.0760 |
| C x R | +0.0832 | +0.0480 |
| R x S | +0.0570 | +0.0364 |
| R x W | -0.0134 | -0.0073 |
| S x W | -0.0165 | +0.0029 |

Contribution ladder uses dependency order R -> C -> U -> W -> S -> P:

| Step | Config (C,U,R,S,W,P) | CLEAN Sharpe | CLEAN Calmar | CLEAN MaxDD | EXT Sharpe | EXT Calmar | EXT MaxDD |
|---|---|---:|---:|---:|---:|---:|---:|
| Baseline (AAA) | 000000 | 0.7869 | 0.3188 | -23.21% | 0.8696 | 0.3624 | -23.21% |
| +R | 001000 | 0.9128 | 0.3637 | -23.54% | 0.9350 | 0.3623 | -23.54% |
| +C | 101000 | 1.0527 | 0.7203 | -12.96% | 1.0153 | 0.6381 | -13.90% |
| +U | 111000 | 1.2062 | 0.7491 | -17.52% | 1.0950 | 0.6635 | -17.52% |
| +W | 111010 | 1.1785 | 0.9606 | -14.22% | 1.1586 | 0.8372 | -15.93% |
| +S | 111110 | 1.1491 | 1.0614 | -12.67% | 1.1857 | 0.8651 | -15.93% |
| +P (all-ON production CPM) | 111111 | 1.1910 | 1.0615 | -12.67% | 1.2142 | 0.8608 | -15.93% |

Clean ladder Calmar is monotone from 0.3188 to 1.0615. Extended ladder is not monotone: +R dips Calmar from 0.3624 to 0.3623 and +P dips Calmar from 0.8651 to 0.8608.

## 7. Design notes

### 7.1 Ranker comparison

CPM ranker comparison remains vol-adjusted Faber versus plain 12-month momentum. Section 6 reports R-factor effects versus AAA's native 6-month ranker (+0.2048 clean dSharpe), while this section isolates a different baseline (+0.1994 clean, +0.1542 extended).

- Clean Sharpe lift: +0.1994.
- Extended Sharpe lift: +0.1542.
- Clean directional signal: P=95.2%, paired 95% CI [-0.0275, 0.4480].

### 7.2 Universe analysis

Universe factor U is positive in Sharpe and mixed in Calmar by window (+0.0837 clean dSharpe, +0.0584 extended dSharpe; +0.0657 clean dCalmar, -0.0043 extended dCalmar). Interaction terms U x R and C x R carry major contribution.

### 7.3 Weighting interpretation

Weighting appears as W factor in the decomposition: AAA baseline minimum-variance versus CPM inverse-vol over surviving positives. This is decomposition attribution, not a CPM variant family.

### 7.4 Asset concentration (CPM risky contribution share)

| Asset | Clean share | Extended share |
|---|---:|---:|
| SPHQ | 20.9% | 15.6% |
| QQQ | 16.9% | 13.6% |
| GLD | 15.0% | 13.8% |
| EFA | 11.7% | 12.3% |
| TLT | 10.5% | 13.9% |
| VNQ | 9.8% | 12.6% |
| EEM | 8.1% | 9.6% |
| DBC | 7.2% | 8.5% |

### 7.5 Cross-asset stagflation resilience and proxy caveats

Stagflation defense in CPM comes from cross-asset rotation plus absolute-momentum screening. In 1970s windows, allocation rotates 90-92% into gold and commodity leaders with strong positive performance (+58.77% in 1973-74 and +209.49% in 1977-82; 0.92 in 1973-74, 0.90 in 1977-82). A PPIACO inverse-vol artifact inflates risk-adjusted metrics (Sharpe, drawdown) by concentrating about 82-86% weight in a smoothed commodity proxy and suppressing modeled volatility; quoted totals are the conservative inverse-vol construction, while de-artifacted equal-weight and WTI variants run higher. Rotation pattern and structural direction remain robust.

## 8. Statistical honesty and caveats

- Bootstrap CI width is material; fine ranking claims carry uncertainty.
- Vol-adjusted Faber ranker edge is directional in clean window, but paired 95% CI includes zero.
- Ladder monotonicity holds in clean Calmar and fails in extended Calmar.
- Ladder attribution is order-dependent by construction (R -> C -> U -> W -> S -> P).
- U, R, and W effects attribute to the full AAA -> CPM toggle as defined; each bundles multiple sub-changes and does not isolate one design parameter.
- Concentration risk is disclosed: top holding is 20.9% clean, top-3 are 52.8% clean.
- Extended-window interpretation carries proxy-tail uncertainty; clean window is decisive.

## 9. Robustness

Clean Sharpe unless noted.

| Check | Result |
|---|---|
| Universe SPY-swap (drop QQQ/SPHQ) | 1.01 (-0.18) \| AAA: 1.03 \| Keller-GTAA10: 0.99 \| Faber-GTAA5: 0.81; all above passive AAA benchmark 0.79; all MaxDD shallower than 13.7% |
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

Grid interaction view supersedes a smooth-corner claim: baseline is the literal argmax, with selection-on-peak bias of +0.25 Sharpe versus grid median and +0.025 versus the second-best cell. Cliffs exist: dropping Faber ranker to 6m costs about 0.26 Sharpe, and K=4 to K=3 costs about 0.24. Interactions are material: Faber leads at K=4 but trails 13612U at K=3, and with a 3m ranker the K optimum flips from 4 to 6.

Mitigants: region and direction are stable across both windows (Faber + K=4-5 + inverse-vol stays top, and extended 1.2142 is also grid-top), and bootstrap CI is [0.7866, 1.5969]. Residual risks: execution discipline matters (a few-day slip to EOM+3 drops Sharpe to 0.91), and selection-on-peak inflation remains in the last about 0.025-0.06 Sharpe slice (504-vs-252 and inverse-vol-vs-equal at optimum). Treat 1.19 as peak estimate; use about 1.02 (Faber-family median) as conservative central expectation.

## 10. Conclusion

In backtest over both windows, CPM delivers high risk-adjusted return, controlled drawdown depth, and fast crisis recovery under month-end signal and next-session-open execution. AAA baseline comparison, decomposition, and robustness checks align with this profile across clean and extended windows, with clean window as primary evidence.

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
- Extended window: 1999-03-10 to 2026-05-22.

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
- research/memo_fix_numbers.json
