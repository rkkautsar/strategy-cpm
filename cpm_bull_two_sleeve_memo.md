# CPM-BULL 60/40 Two-Sleeve Investment Strategy Memo

Current state: convention-locked monthly two-sleeve ETF implementation. Clean window uses live ETF coverage. Extended window includes proxy-backed pre-ETF segments. Metrics are post-cost and use signal-close then next-session-open execution.

Audit status: backtest implementation internally reproduced. Not yet live-traded. External replication not yet completed.

## 0. Header and metadata

- Strategy: 60 percent CPM sleeve (Cross-asset Parity Momentum) plus 40 percent BULL sleeve.
- CPM risky universe: QQQ, SPHQ, EFA, EEM, VNQ, GLD, TLT, DBC.
- BULL risky asset: SPY.
- Safe assets: SHV, IEF.
- Windows:
  - Clean window: 2008-05-30 to 2026-05-22 (18.0 years).
  - Extended window: 1999-03-10 to 2026-05-22 (27.0 years), with proxy-backed segments before full ETF coverage.
- Costs: 10 bps per side, embedded in all tables.
- Sharpe convention: raw Sharpe (rf = 0) and excess Sharpe versus SHV.
- Rebalance and leverage: monthly rebalance, unlevered.
- Execution convention: signal at month-end close, trade at next-session open.


## 1. Executive summary

This memo defines an unlevered monthly two-sleeve ETF strategy: 60 percent CPM plus 40 percent BULL with a gated SPY risk-on rule.

Headline blend metrics on next-session-open execution:
- 60/40 clean: raw Sharpe 1.248, excess Sharpe 1.116, CAGR 12.74 percent, Vol 10.05 percent, MaxDD -10.68 percent, Calmar 1.19, 2022 return +0.12 percent.
- 60/40 extended: raw Sharpe 1.219, CAGR 12.13 percent, Vol 9.78 percent, MaxDD -11.31 percent, Calmar 1.07.
- 50/50 clean: raw Sharpe 1.243, excess Sharpe 1.109, CAGR 12.55 percent, Vol 9.95 percent, MaxDD -11.12 percent, Calmar 1.13, 2022 return +0.27 percent.

CPM anchors:
- Clean: Sharpe 1.1910, CAGR 13.44 percent, MaxDD -12.67 percent, Calmar 1.0615.
- Extended: Sharpe 1.2142, MaxDD -15.93 percent, Calmar 0.8608.

Weight split sensitivity is broad, not knife-edge: clean Sharpe band 0.046 across 30/70 to 80/20, stress Sharpe band 0.126 across the same sweep. Stress band sits slightly above a 0.10 flat-band cutoff, so split choice is stable but not fully indifferent.

CPM-BULL return correlation is 0.676 in clean and 0.609 in stress: diversification is real and modest.

2022 for the 60/40 blend is roughly flat and non-negative (+0.12 percent), not a standout year.

Reader map: Sections 1-4 cover strategy and data, Section 5 covers headline and benchmark families, Sections 6-7 cover risk behavior and design logic, Section 8 covers robustness, Sections 9-10 cover statistical limits, and Section 12 covers replication and factorial decomposition.


## 2. Investment thesis and economic rationale

Cross-asset time-series momentum persists through risk-on and risk-off cycles. CPM applies this with a unified pipeline: cross-asset momentum to vol-adjusted Faber ranking, positive-trend screen, top-4 selection, inverse-vol weighting across all surviving positives, then strict-4 partial-safe scaling. The BULL sleeve adds an equity regime gate, and both sleeves share the same canary and timed safe logic. The result is broad market participation with explicit risk scaling when breadth is thin.


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
  - rv_60d = stdev(simple daily returns, 60d) * sqrt(252).
  - rv_252d = stdev(simple daily returns, 252d) * sqrt(252).
  - In the rule rv_60d < rv_252d, the common annualization factor sqrt(252) cancels.

### 3.2 CPM sleeve (60 percent gross sleeve weight)

Cross-asset Parity Momentum (CPM) rule stack:

1. Compute score = m_faber / rv_252d for each risky asset in {QQQ, SPHQ, EFA, EEM, VNQ, GLD, TLT, DBC}.
2. Keep only assets with m_faber > 0.
3. Rank by score and keep top 4.
4. If canary is off, allocate full sleeve to safe selector.
5. If canary is on:
   - n_pos = number of surviving positives (0..4).
   - risky_fraction = min(n_pos, 4) / 4.
   - safe_fraction = 1 - risky_fraction.
   - risky block uses inverse-vol weights across all surviving positives.
   - safe block goes to timed SHV or IEF by 13612U.

This is strict-4 partial-safe behavior:
- n_pos = 0 -> 0/4 risky, 4/4 safe.
- n_pos = 1 -> 1/4 risky, 3/4 safe.
- n_pos = 2 -> 2/4 risky, 2/4 safe.
- n_pos = 3 -> 3/4 risky, 1/4 safe.
- n_pos = 4 -> 4/4 risky, 0/4 safe.

### 3.3 BULL sleeve (40 percent gross sleeve weight)

Hold SPY if all conditions pass:

1. Canary passes.
2. SPY m_13612U > 0.
3. rv_60d(SPY) < rv_252d(SPY).

Else allocate BULL sleeve to safe selector.

### 3.4 Shared canary and safe selector

- Canary is on if m_13612U(HYG) > 0 OR m_13612U(TIP) > 0.
- Safe selector chooses argmax of m_13612U over {SHV, IEF}.

### 3.5 Portfolio blend and implementation

- Portfolio = 0.60 * CPM sleeve + 0.40 * BULL sleeve.
- Rebalance monthly.
- Signals computed on month-end close.
- Orders executed at next-session open.

### 3.6 Parameter table

| Component | Parameter | Value |
|---|---|---|
| Trend risky universe size | N | 8 |
| Trend selection count | K | 4 |
| Trend score | Rank metric | m_faber / rv_252d |
| Trend positivity filter | Threshold | m_faber > 0 |
| Risky block weighting | Rule | inverse-vol over all surviving positives |
| Risky fraction control | Rule | strict-4 partial-safe, min(n_pos,4)/4 |
| Covariance lookback | Window | 504 trading days |
| Equity trend filter | Threshold | m_13612U(SPY) > 0 |
| Equity vol gate | Rule | rv_60d < rv_252d |
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
- Execution: signal at month-end close, fill at next-session open (T+1 MOO exact for CPM and BULL series in source runs).
- Extended-window interpretation: proxy-backed segments exist before full ETF coverage; clean window is decisive lens.


## 5. Headline results

### 5.1 Clean window (2008-05-30 to 2026-05-22), next-session open execution

| Portfolio / Split | CAGR | Vol | Raw Sharpe | Excess Sharpe vs SHV | MaxDD | Calmar | 2022 Return |
|---|---:|---:|---:|---:|---:|---:|---:|
| CPM/BULL 60/40 | 12.74% | 10.05% | 1.248 | 1.116 | -10.68% | 1.19 | +0.12% |
| CPM/BULL 50/50 | 12.55% | 9.95% | 1.243 | 1.109 | -11.12% | 1.13 | +0.27% |
| CPM | 13.44% | 11.16% | 1.1910 | 1.072 | -12.67% | 1.0615 | -0.50% |
| BULL | 11.44% | 10.57% | 1.081 | 0.955 | -13.35% | 0.857 | +0.94% |

### 5.2 Extended window (1999-03-10 to 2026-05-22), next-session open execution

| Portfolio / Split | CAGR | Vol | Raw Sharpe | Excess Sharpe vs SHV | MaxDD | Calmar |
|---|---:|---:|---:|---:|---:|---:|
| CPM/BULL 60/40 | 12.13% | 9.78% | 1.219 | 0.986 | -11.31% | 1.07 |
| CPM/BULL 50/50 | 11.71% | 9.66% | 1.194 | 0.958 | -11.12% | 1.05 |
| CPM | 13.71% | 11.09% | 1.2142 | n/a | -15.93% | 0.8608 |
| BULL | 9.49% | 10.45% | 0.920 | n/a | -13.96% | 0.680 |

### 5.3 Benchmark comparison against literature-inspired benchmark families

#### CPM sleeve versus canonical AAA benchmark

| Window | Series | Sharpe | CAGR | Vol | MaxDD | Calmar |
|---|---|---:|---:|---:|---:|---:|
| Clean | CPM | 1.1910 | 13.44% | 11.16% | -12.67% | 1.0615 |
| Clean | Canonical AAA benchmark | 0.9695 | 11.48% | 12.00% | -20.65% | 0.5558 |
| Extended | CPM | 1.2142 | 13.71% | 11.09% | -15.93% | 0.8608 |
| Extended | Canonical AAA benchmark | 1.0319 | 11.91% | 11.55% | -20.65% | 0.5767 |

CPM leads canonical AAA on Sharpe, CAGR, Calmar, and drawdown depth in both windows.

#### BULL sleeve versus HAA-Simple benchmark

| Window | Series | Sharpe | CAGR | Vol | MaxDD | Calmar |
|---|---|---:|---:|---:|---:|---:|
| Clean | BULL sleeve | 1.081 | 11.44% | 10.57% | -13.35% | 0.857 |
| Clean | HAA-Simple benchmark {BIL,AGG} | 0.960 | 11.08% | 11.70% | -19.74% | 0.561 |
| Extended | BULL sleeve | 0.920 | 9.49% | 10.45% | -13.96% | 0.680 |
| Extended | HAA-Simple benchmark {BIL,AGG} | 0.946 | 10.14% | 10.83% | -19.74% | 0.514 |

BULL contribution remains drawdown control first, return maximization second.

### 5.4 Clean side-by-side: two-sleeve vs PROD 60/20/20

| Metric | CPM | BULL | NDX | Two-sleeve 60/40 | Two-sleeve 50/50 | PROD 60/20/20 |
|---|---:|---:|---:|---:|---:|---:|
| CAGR | 13.44% | 11.44% | 30.01% | 12.74% | 12.55% | 16.64% |
| Vol | 11.16% | 10.57% | 24.77% | 10.05% | 9.95% | 11.78% |
| Raw Sharpe | 1.191 | 1.081 | 1.186 | 1.248 | 1.243 | 1.370 |
| Excess Sharpe | 1.072 | 0.955 | 1.132 | 1.116 | 1.109 | 1.257 |
| MaxDD | -12.67% | -13.35% | -35.92% | -10.68% | -11.12% | -12.16% |
| Calmar | 1.06 | 0.86 | 0.84 | 1.19 | 1.13 | 1.37 |
| 2022 Return | -0.50% | +0.94% | +0.94% | +0.12% | +0.27% | +0.12% |

60/40 versus PROD 60/20/20 in clean window:
- Gives up CAGR -3.89pp, raw Sharpe -0.121, excess Sharpe -0.141.
- Gains Vol -1.73pp and MaxDD -1.48pp.
- Calmar difference is -0.17 (1.19 vs 1.37).

### 5.5 Structural decomposition versus benchmark families

CPM 2^6 decomposition now uses factors C,U,R,S,W,P:
- C = canary (TIP-only baseline to HYG-or-TIP production gate).
- U = universe (canonical AAA set to CPM 8-asset set).
- R = ranker (plain 12m momentum to vol-adjusted Faber).
- S = Screen (positive-trend / absolute-momentum): hold top-K regardless of sign to hold only positive-trend names, with non-positive slots left empty.
- W = weighting only: equal-weight versus inverse-vol over the held set.
- P = partial-safe: off is fully invested (risky_fraction=1), on is risky_fraction=min(breadth,4)/4 with remainder routed to timed SHV/IEF (strict-4 partial-safe).

Clean main effects on Sharpe:
- R +0.1603
- U +0.1596
- C +0.0377 [FLIP]
- W +0.0347 [FLIP]
- P +0.0144
- S -0.0564 [FLIP]

Clean main effects on Calmar:
- R +0.2038
- U +0.2035
- C +0.0663 [FLIP]
- W +0.0631 [FLIP]
- P +0.0283 [FLIP]
- S +0.0058 [FLIP]

EXT main effects on Calmar:
- U +0.1080
- R +0.0718 [FLIP]
- W +0.0537 [FLIP]
- C +0.0450 [FLIP]
- P +0.0311 [FLIP]
- S -0.0017 [FLIP]

R and U are the first-order drivers. Partial-safe P has a near-zero Sharpe effect in isolation (+0.0144) because P is inert whenever breadth is already 4. P only acts when screen S thins breadth below 4, so P value lives mostly in S x P (+0.0283 clean Calmar, +0.0260 EXT Calmar).

W x P is mildly negative (-0.0129 clean Calmar, -0.0084 EXT Calmar): inverse-vol weighting and partial-safe partly substitute for drawdown control. S remains negative in isolation as a Sharpe effect (-0.0564), while S and P together deliver conditional drawdown control.

Contribution ladder R -> U -> C -> W -> S -> P (clean), ordered so each factor follows its dependency (P only acts once S thins breadth):
- 000000: Sharpe 0.8561, Calmar 0.4902, MaxDD -19.43%
- +R (001000): Sharpe 0.9481, Calmar 0.5880, MaxDD -18.21%
- +U (011000): Sharpe 1.0743, Calmar 0.7372, MaxDD -16.97%
- +C (111000): Sharpe 1.1148, Calmar 0.8138, MaxDD -16.97%
- +W (111010): Sharpe 1.1785, Calmar 0.9606, MaxDD -14.22%
- +S (111110): Sharpe 1.1491, Calmar 1.0614, MaxDD -12.67%
- +P all-ON production (111111): Sharpe 1.1910, Calmar 1.0615, MaxDD -12.67%

The screen step trades a little Sharpe (1.1785 to 1.1491) for drawdown control (Calmar 0.9606 to 1.0614, MaxDD -14.22% to -12.67%) by concentrating into fewer fully invested positive-trend names; partial-safe then recovers the Sharpe (1.1491 to 1.1910) at the same drawdown by routing the freed slots to timed safe instead of over-concentrating. The ladder is monotonic in Calmar and drawdown; the screen step is a deliberate Sharpe-for-drawdown trade that partial-safe reverses.

BULL decomposition numbers remain unchanged and are kept in Sections 12.5.2 and 12.6.2.


## 6. Risk and drawdown analysis

Crisis windows (window-local drawdown and total return):

| Crisis window | Blend MaxDD | Blend return | CPM MaxDD | CPM return |
|---|---:|---:|---:|---:|
| Dot-com (2000-03..2002-12) | -5.61% | 23.45% | -6.03% | 28.44% |
| GFC (2007-10..2009-06) | -9.90% | 11.68% | -11.88% | 9.86% |
| COVID (2020-02..2020-06) | -10.68% | 3.22% | -10.06% | 8.00% |
| 2022 bear (2022-01..2022-12) | -3.86% | 0.12% | -6.33% | -0.50% |

Worst contiguous stretches for 60/40 blend:

| Span | Dates | Sharpe | CAGR | MaxDD |
|---|---|---:|---:|---:|
| 1 year | 2022-03-09..2023-03-09 | -1.015 | -2.51% | -5.14% |
| 2 years | 2021-10-29..2023-10-29 | -0.428 | -3.13% | -8.63% |
| 3 years | 2022-04-08..2025-04-07 | 0.589 | 4.73% | -8.63% |

Observed drawdown floor for the blend remains in low double digits in major stress slices. 2022 outcome for blend is roughly flat and non-negative.


## 7. Design rationale (principled, present tense)

The two sleeves share a broad-risk canary and a common safe timing rule. Monthly sleeve-level gates keep turnover controlled and keep implementation simple.

BULL sleeve gate rv_60d(SPY) < rv_252d(SPY) stays in production for lag robustness and lower whipsaw under next-session-open fills.

Canary keeps two permissive inputs: HYG OR TIP. High-yield-only variant is slightly stronger in backtest metrics, while dual-input canary keeps dependence lower on one proxy.

K-selection rationale uses direct K sweep evidence. In the 60/40 blend, K=4 is best clean Sharpe (1.2485) and best clean Calmar (1.1928), with K=5 close but lower. K=2 and K=3 lose material Sharpe; K=6 loses risk quality in extended drawdown.

Positive-trend screen remains required. Removing it increases drawdown depth and weakens Calmar.

Ranker remains vol-adjusted Faber. In CPM, vol-adjusted Faber beats plain 12-month momentum by +0.1994 Sharpe in clean and +0.1553 in extended.

Weighting choice is inverse-vol across all surviving positives. ERC is near-tied on headline metrics but needs a numerical solver; equal-weight is weaker. Inverse-vol keeps robust behavior without solver dependency.

Strict-4 partial-safe stays active because low-breadth drawdown protection is explicit and material in stress slices.

Covariance lookback stays at 504 trading days. Sensitivity around 504 to 756 is stable; longer windows degrade gradually, not abruptly.

Safe sleeve keeps timed SHV/IEF by 13612U to capture both duration-friendly and duration-hostile defensive states.


## 8. Robustness and sensitivity

### 8.1 Selection-count sensitivity (60/40 blend, K in {2,3,4,5,6})

| K | Clean Sharpe | Clean CAGR | Clean MaxDD | Clean Calmar | Extended Sharpe | Extended MaxDD | Extended Calmar |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 2 | 1.0662 | 8.35% | -9.91% | 0.8424 | 1.0808 | -9.91% | 0.8492 |
| 3 | 1.1370 | 10.23% | -9.47% | 1.0803 | 1.1407 | -9.47% | 1.0674 |
| 4 (base) | 1.2485 | 12.74% | -10.68% | 1.1928 | 1.2199 | -11.31% | 1.0761 |
| 5 | 1.1677 | 11.64% | -11.59% | 1.0041 | 1.1580 | -11.59% | 0.9740 |
| 6 | 1.1310 | 11.11% | -12.10% | 0.9186 | 1.1369 | -12.10% | 0.8991 |

K=4 is the selection-count anchor: highest clean Sharpe and Calmar, with balanced extended behavior.

### 8.2 Screen 2x2 sensitivity

| Variant | Clean Sharpe | Clean CAGR | Clean MaxDD | Clean Calmar | Extended Sharpe | Extended MaxDD | Extended Calmar |
|---|---:|---:|---:|---:|---:|---:|---:|
| K-cap ON + positive-trend ON (base) | 1.2485 | 12.74% | -10.68% | 1.1928 | 1.2199 | -11.31% | 1.0761 |
| K-cap OFF + positive-trend ON | 1.0882 | 10.51% | -12.27% | 0.8568 | 1.1148 | -12.27% | 0.8516 |
| K-cap ON + positive-trend OFF | 1.2571 | 12.89% | -13.26% | 0.9721 | 1.2101 | -13.26% | 0.9104 |
| K-cap OFF + positive-trend OFF | 1.1593 | 10.73% | -17.95% | 0.5975 | 1.1544 | -17.95% | 0.5712 |

Positive-trend screen is key for drawdown control.

### 8.3 Ranker sensitivity

| Ranker design | Clean Sharpe | Clean CAGR | Clean MaxDD | Clean Calmar | Extended Sharpe | Extended MaxDD | Extended Calmar |
|---|---:|---:|---:|---:|---:|---:|---:|
| vol-adjusted Faber / rv_252d (base) | 1.2485 | 12.74% | -10.68% | 1.1928 | 1.2199 | -11.31% | 1.0761 |
| 13612U / rv_252d (positive 13612U screen) | 1.2402 | 12.71% | -11.52% | 1.1031 | 1.2020 | -13.15% | 0.9179 |
| plain 12-month momentum | 1.1457 | 11.58% | -13.29% | 0.8715 | 1.1410 | -13.29% | 0.8671 |

Ranker choice remains additive under the production stack.

### 8.4 Weighting sensitivity

| Weighting design (CPM) | Clean Sharpe | Clean Calmar | Clean Martin | Clean MaxDD | Extended Sharpe | Extended Calmar |
|---|---:|---:|---:|---:|---:|---:|
| inverse-vol across surviving positives (base) | 1.1910 | 1.0615 | 3.9646 | -12.67% | 1.2142 | 0.8608 |
| ERC (equal-risk-contribution) | 1.1944 | 1.0602 | 3.9896 | -12.67% | 1.2184 | 0.8647 |
| equal-weight | 1.1317 | 1.0147 | 3.7413 | -13.05% | 1.1868 | 0.8718 |

Inverse-vol and ERC are near-tied; inverse-vol keeps solver-free simplicity while preserving headline quality.

### 8.5 Blend weight sensitivity (CPM/BULL 80/20 to 30/70)

| CPM/BULL | Clean Sharpe | Clean MaxDD | Stress Sharpe | Stress MaxDD |
|---|---:|---:|---:|---:|
| 80/20 | 1.233 | -10.09% | 1.235 | -13.63% |
| 70/30 | 1.245 | -10.25% | 1.232 | -12.47% |
| 60/40 | 1.248 | -10.68% | 1.219 | -11.31% |
| 50/50 | 1.243 | -11.12% | 1.194 | -11.12% |
| 40/60 | 1.227 | -11.56% | 1.157 | -11.56% |
| 30/70 | 1.202 | -12.01% | 1.109 | -12.01% |

Clean Sharpe band is 0.046 (1.202 to 1.248): very flat. Stress Sharpe band is 0.126 (1.109 to 1.235): slightly above a 0.10 flat-band cutoff.

### 8.6 Canary and safe sensitivity

#### Canary variants (60/40 blend)

| Canary design | Clean Sharpe | Clean CAGR | Clean MaxDD | Clean Calmar | Extended Sharpe | Extended MaxDD | Extended Calmar |
|---|---:|---:|---:|---:|---:|---:|---:|
| HYG OR TIP (base) | 1.2485 | 12.74% | -10.68% | 1.1928 | 1.2199 | -11.31% | 1.0761 |
| no canary | 1.2158 | 12.56% | -10.68% | 1.1757 | 1.2000 | -11.31% | 1.0688 |
| HYG only | 1.2528 | 12.77% | -10.68% | 1.1954 | 1.2387 | -11.31% | 1.0935 |
| TIP only | 1.2457 | 11.99% | -10.68% | 1.1219 | 1.1988 | -10.68% | 1.0323 |

#### Safe variants (60/40 blend)

| Safe design | Clean Sharpe | Clean CAGR | Clean MaxDD | Clean Calmar | Extended Sharpe | Extended MaxDD | Extended Calmar |
|---|---:|---:|---:|---:|---:|---:|---:|
| timed SHV/IEF by 13612U (base) | 1.2485 | 12.74% | -10.68% | 1.1928 | 1.2199 | -11.31% | 1.0761 |
| SHV only | 1.2297 | 12.18% | -10.42% | 1.1682 | 1.2088 | -11.31% | 1.0396 |
| IEF only | 1.2304 | 12.71% | -12.06% | 1.0541 | 1.2074 | -12.06% | 1.0081 |
| static half-half SHV+IEF | 1.2357 | 12.44% | -10.53% | 1.1818 | 1.2120 | -11.31% | 1.0568 |

### 8.7 Rolling-window stability

| Window | Min Sharpe | Median Sharpe | Max Sharpe | Share < 1.0 | Share < 0.7 |
|---|---:|---:|---:|---:|---:|
| Clean 3y | 0.570 | 1.269 | 1.849 | 13.1% | 0.7% |
| Clean 5y | 0.898 | 1.266 | 1.714 | 0.6% | 0.0% |
| Extended 3y | 0.570 | 1.209 | 1.849 | 20.6% | 0.8% |
| Extended 5y | 0.802 | 1.224 | 1.714 | 11.1% | 0.0% |

Worst contiguous blend spans:
- 1y: Sharpe -1.015, CAGR -2.51%, MaxDD -5.14%.
- 2y: Sharpe -0.428, CAGR -3.13%, MaxDD -8.63%.
- 3y: Sharpe 0.589, CAGR 4.73%, MaxDD -8.63%.

### 8.8 Execution and cost

All headline rows in this memo use next-session-open exact execution with 10 bps per side cost.

### 8.9 Asset concentration (CPM risky contribution share)

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

Clean concentration matches the expected 8-asset distribution.

### 8.10 Covariance lookback sensitivity under inverse-vol

| Cov lookback (days) | Clean Sharpe | Clean CAGR | Clean MaxDD | Clean Calmar | Extended Sharpe | Extended MaxDD | Extended Calmar |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 126 | 1.2286 | 12.57% | -11.71% | 1.0734 | 1.2145 | -11.71% | 1.0292 |
| 252 | 1.2338 | 12.57% | -11.56% | 1.0877 | 1.2116 | -11.56% | 1.0369 |
| 504 (base) | 1.2485 | 12.74% | -10.68% | 1.1928 | 1.2199 | -11.31% | 1.0761 |
| 756 | 1.2485 | 12.76% | -10.93% | 1.1682 | 1.2128 | -11.32% | 1.0733 |
| 1008 | 1.2461 | 12.76% | -11.26% | 1.1329 | 1.2140 | -11.41% | 1.0679 |
| 1260 | 1.2471 | 12.78% | -11.37% | 1.1232 | 1.2164 | -11.39% | 1.0730 |

504 sits on the top stability shelf with 756 nearby; longer windows decay gradually.

### 8.11 BULL gate cohort note

BULL gate cohort decomposition stays in dedicated BULL studies and is outside this memo scope.


## 9. Statistical honesty and significance

Bootstrap confidence intervals are wide, so small deltas are not decisive.

Clean-window Sharpe CI (stationary block bootstrap):
- 60/40 blend: point 1.2485, 95 percent CI [0.8367, 1.6741], width 0.8374.
- CPM: point 1.1910, 95 percent CI [0.7866, 1.5969], width 0.8103.
- BULL: point 1.0813, 95 percent CI [0.6352, 1.5533], width 0.9181.

Interpretation:
1. CI covers sampling variability for the fixed rule set.
2. Delta claims smaller than CI width need extra caution.
3. Design-level selection bias still exists in backtest evidence.
4. Rolling stability is fixed-rule evaluation, not fold-wise retuning.


## 10. Limitations and forward expectations

Boundary: only forward live or paper-traded data is true out-of-sample.

- Design-level selection bias exists.
- Extended window includes proxy-backed segments before full ETF coverage.
- Sharpe CI widths are large, so fine ranking claims are weak.
- Drawdown floor remains low double digits in monthly architecture.
- Monthly cadence has intramonth latency.

Role fit: drawdown-aware compounding core, not max-CAGR equity substitute.


## 11. Implementation and operational notes

- Rebalance cadence: monthly, signal at month-end close, execution at next-session open.
- Parameters are convention-locked and not refit each month.
- Instruments: liquid ETFs for risky and safe sleeves, with proxy-backed segments in extended window only.
- Scope: this memo covers CPM/BULL two-sleeve implementation only.


## 12. Reproduction and appendix

### 12.1 Code pointers

- `cpm_live.py` (CPM sleeve construction, canary, safe selector, backtest wiring)
- `bull_qqq_live.py` (BULL sleeve gating and safe fallback)
- `build_dashboard.py` (reporting and summary generation)

### 12.2 Full parameter dictionary

| Key | Value |
|---|---|
| trend_universe | [QQQ, SPHQ, EFA, EEM, VNQ, GLD, TLT, DBC] |
| equity_asset | SPY |
| safe_pool | [SHV, IEF] |
| ranker | m_faber / rv_252d |
| trend_filter | m_faber > 0 |
| top_k | 4 |
| risky_weight_rule | inverse-vol over all surviving positives |
| risky_fraction_rule | strict-4 partial-safe, min(n_pos,4)/4 |
| cov_lookback_days | 504 |
| canary_rule | m_13612U(HYG) > 0 OR m_13612U(TIP) > 0 |
| equity_trend_rule | m_13612U(SPY) > 0 |
| equity_vol_rule | rv_60d(SPY) < rv_252d(SPY) |
| safe_rule | argmax m_13612U over SHV and IEF |
| rebalance | monthly |
| execution | month-end close signal, next-session open fill |
| transaction_cost_per_side | 10 bps |
| leverage | unlevered |
| reporting_sharpe_rf | 0 |
| excess_sharpe_reference | SHV |

### 12.3 Window dates used in this memo

- Clean window: 2008-05-30 to 2026-05-22.
- Extended window: 1999-03-10 to 2026-05-22.

### 12.4 Source anchors

- CPM final numbers findings
- Two-sleeve memo numbers findings
- CPM factorial findings

### 12.5 Full factorial grids (CPM + BULL decomposition)

Execution label for every row in this section: month-end close signal, T+1 MOO exact fill, post-cost 10 bps per side.

#### 12.5.1 CPM factorial (2^6 cells)

Config order is C,U,R,S,W,P. S means Screen (positive-trend / absolute-momentum), W means weighting only (equal versus inverse-vol over held set), and P means partial-safe. P is distinct from BULL safe-pool S in Section 12.6.2.

The full 64-cell grid (CLEAN and EXT, all six factors) is in research/cpm_factorial_iv4_6factor_findings.md and research/cpm_factorial_iv4_6factor.json. The relevant summary -- main effects, key interactions, and the contribution ladder -- is in Section 12.6.1.

#### 12.5.2 BULL benchmark to sleeve factorial (2^3 cells)

Config order is K,V,S where 1 means production setting and 0 means benchmark setting.

| Config (K,V,S) | CLEAN Sharpe | CLEAN Calmar | CLEAN MaxDD | EXT Sharpe | EXT Calmar | EXT MaxDD |
|---|---:|---:|---:|---:|---:|---:|
| 0,0,0 (HAA-Simple) | 0.989 | 0.581 | -19.74% | 0.973 | 0.530 | -19.74% |
| 0,0,1 | 0.984 | 0.569 | -20.41% | 0.974 | 0.526 | -20.41% |
| 0,1,0 | 1.107 | 0.549 | -19.17% | 1.019 | 0.468 | -19.17% |
| 0,1,1 | 1.101 | 0.819 | -13.35% | 1.021 | 0.710 | -13.35% |
| 1,0,0 | 1.020 | 0.644 | -19.74% | 0.937 | 0.578 | -19.74% |
| 1,0,1 | 1.038 | 0.643 | -20.41% | 0.953 | 0.580 | -20.41% |
| 1,1,0 | 1.067 | 0.567 | -19.17% | 0.900 | 0.464 | -19.17% |
| 1,1,1 (BULL) | 1.081 | 0.857 | -13.35% | 0.920 | 0.680 | -13.96% |

### 12.6 Main effects and interactions

#### 12.6.1 CPM main effects

In this CPM subsection, S means Screen (positive-trend / absolute-momentum), W means weighting only, and P means partial-safe. P is distinct from BULL safe-pool S in Section 12.6.2.

| Factor | CLEAN dSharpe | CLEAN dCalmar | EXT dSharpe | EXT dCalmar |
|---|---:|---:|---:|---:|
| Ranker (R) | +0.1603 | +0.2038 | +0.0815 [FLIP] | +0.0718 [FLIP] |
| Universe (U) | +0.1596 | +0.2035 | +0.0815 | +0.1080 |
| Canary (C) | +0.0377 [FLIP] | +0.0663 [FLIP] | +0.0159 [FLIP] | +0.0450 [FLIP] |
| Weighting only (W) | +0.0347 [FLIP] | +0.0631 [FLIP] | +0.0232 [FLIP] | +0.0537 [FLIP] |
| Partial-safe (P) | +0.0144 | +0.0283 [FLIP] | +0.0184 | +0.0311 [FLIP] |
| Screen (S, positive-trend) | -0.0564 [FLIP] | +0.0058 [FLIP] | -0.0202 [FLIP] | -0.0017 [FLIP] |

CPM key two-way interactions (Calmar deltas):

| Interaction | CLEAN dCalmar | EXT dCalmar |
|---|---:|---:|
| R x S | +0.0730 | +0.0389 |
| R x W | +0.0665 | +0.0593 |
| S x P | +0.0283 | +0.0260 |
| R x P | +0.0281 | +0.0272 |
| W x P | -0.0129 | -0.0084 |
| S x W | +0.0087 | +0.0116 |
| C x P | +0.0083 | +0.0009 |
| U x P | +0.0024 | +0.0010 |

R x S is the largest clean Calmar interaction. S x P is the key partial-safe coupling, and W x P is mildly negative.

Contribution ladder (clean) follows R -> U -> C -> W -> S -> P (dependency order; P only acts once S thins breadth):

| Step | Config (C,U,R,S,W,P) | Sharpe | Calmar | MaxDD |
|---|---|---:|---:|---:|
| Baseline | 000000 | 0.8561 | 0.4902 | -19.43% |
| +R | 001000 | 0.9481 | 0.5880 | -18.21% |
| +U | 011000 | 1.0743 | 0.7372 | -16.97% |
| +C | 111000 | 1.1148 | 0.8138 | -16.97% |
| +W | 111010 | 1.1785 | 0.9606 | -14.22% |
| +S | 111110 | 1.1491 | 1.0614 | -12.67% |
| +P (all-ON production CPM, 1,1,1,1,1,1) | 111111 | 1.1910 | 1.0615 | -12.67% |

#### 12.6.2 BULL main effects

| Factor | CLEAN dSharpe | CLEAN dCalmar | EXT dSharpe | EXT dCalmar | Heuristic average across listed deltas |
|---|---:|---:|---:|---:|---:|
| Safe pool (S) | +0.005 [FLIP] | +0.137 [FLIP] | +0.009 | +0.114 [FLIP] | +0.066 |
| Vol gate (V) | +0.081 | +0.089 [FLIP] | +0.006 [FLIP] | +0.027 [FLIP] | +0.051 |
| Canary breadth (K) | +0.006 [FLIP] | +0.048 | -0.069 | +0.017 [FLIP] | +0.000 |

Dominant BULL two-way interactions:

| Interaction | CLEAN dCalmar | EXT dCalmar |
|---|---:|---:|
| V x S | +0.143 | +0.115 |
| K x V | -0.036 | n/a |
