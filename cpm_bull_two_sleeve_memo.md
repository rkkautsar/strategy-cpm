# CPM-BULL 60/40 Two-Sleeve Investment Strategy Memo

Current state: convention-locked monthly two-sleeve ETF implementation; clean-window results use live ETF coverage, extended-window results include proxy-backed pre-ETF history; post-cost results reported at signal close then next-session open execution.

Audit status: backtest implementation internally reproduced; not yet live-traded; external replication not yet completed; extended history is proxy-backed.

## 0. Header and metadata

- Strategy: 60 percent CPM sleeve (trend sleeve) plus 40 percent BULL sleeve (equity sleeve).
- Universe:
  - Trend sleeve risky assets: QQQ, SPHQ, EFA, EEM, VNQ, GLD, TLT, DBC.
  - Equity sleeve risky asset: SPY.
  - Safe assets: SHV, IEF.
- Windows:
  - Clean window: 2008-05-30 to 2026-05-22 (18.0 years).
  - Extended window: 1999-03-10 to 2026-05-22 (27 years), with partial proxy history before live ETF coverage in parts of the panel.
- Costs: 10 bps per side, post-cost metrics throughout; a full A-to-B switch therefore costs 20 bps on the switched notional.
- Sharpe convention: raw Sharpe at zero risk-free rate; excess Sharpe versus SHV is also available in cited studies.
- Rebalance and leverage: monthly rebalance, unlevered.
- Execution convention: signal at month-end close, trade at next-session open.


## 1. Executive summary

This memo defines an unlevered monthly two-sleeve ETF strategy: 60 percent CPM sleeve plus 40 percent BULL sleeve with a gated SPY risk-on rule. On next-session open exact execution, clean-window blend results are Sharpe 1.321, CAGR 13.25 percent, MaxDD -10.66 percent, Calmar 1.243; extended-window blend results are Sharpe 1.235, CAGR 12.32 percent, MaxDD -11.18 percent, Calmar 1.101. Parameters are convention-locked across windows and are not refit per period. Forward base-case expectation is haircut to 0.9 to 1.2 Sharpe and 8 to 12 percent CAGR. Dominant limitation is a structural drawdown floor in the low double digits, with residual drawdown concentration driven mainly by the BULL sleeve in adverse monthly paths.

This is not an equity-replacement strategy and not a maximum-CAGR strategy. It is a monthly, ETF-only, drawdown-controlled compounding strategy that trades some upside versus QQQ for materially lower drawdown, lower beta, and broader cross-asset participation. The intended role is a tactical core allocation, not a levered equity substitute.

Reader map: Sections 1-4 cover strategy and data, Section 5 covers headline results and benchmark families, Sections 6-7 cover risk behavior and design choices, Section 8 covers robustness, Sections 9-10 cover statistical limits and forward expectations, and Section 12 covers replication and factorial decomposition.


## 2. Investment thesis and economic rationale

Cross-asset time-series momentum exists because risk-taking and de-risking flows persist across horizons, especially in crisis and recovery transitions. A minimum-variance pair inside trend-qualified assets seeks diversification without giving up trend directionality, so the CPM sleeve is not a single-asset momentum bet. A separate equity regime gate in the BULL sleeve cuts left-tail equity participation when credit and realized volatility conditions are unfavorable. The two sleeves share a broad-risk canary and a common safe-asset timing convention, and the system uses monthly sleeve-level gates rather than intramonth overlays. The canary uses high-yield credit and inflation-protected bonds as permissive signals to reduce single-market dependence, while the safe sleeve uses duration timing between SHV and IEF to handle flight-to-quality and rate-hike defensive regimes.


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

1. Score each risky asset by m_faber divided by rv_252d.
2. Keep only assets with positive m_faber.
3. Candidate pool cap: K = ceil(N/2) = 4 from N = 8 risky assets.
4. If canary is off, allocate full sleeve to safe asset selector.
5. If canary is on:
   - Fewer than 1 positive candidate: 100 percent safe.
   - Exactly 1 positive candidate: 50 percent that asset plus 50 percent safe.
   - At least 2 positive candidates: choose the 50/50 pair with minimum portfolio variance using 504d covariance across surviving candidates.

### 3.3 BULL sleeve (40 percent gross sleeve weight)

Hold SPY if all conditions pass:

1. Canary passes.
2. SPY m_13612U > 0.
3. Production volatility gate = 60 trading days versus 252 trading days: rv_60d(SPY) < rv_252d(SPY).

Else allocate BULL sleeve to safe asset selector.

Rationale: the slower 60d versus 252d crossover is selected for lag robustness and reduced whipsaw versus faster short-volatility gates; faster crossovers can show edge under same-bar assumptions but degrade under realistic next-session-open fills.

### 3.4 Shared canary and safe selector

- Canary on if either high-yield trend or inflation-protected trend is positive:
  - m_13612U(HYG) > 0 OR m_13612U(TIP) > 0.
- Safe asset selector:
  - choose argmax of m_13612U over {SHV, IEF}.

### 3.5 Portfolio blend and implementation

- Portfolio = 0.60 * CPM sleeve + 0.40 * BULL sleeve.
- Rebalance monthly.
- Signals computed on month-end close.
- Orders executed at next-session open.

### 3.6 Parameter table

| Component | Parameter | Value |
|---|---|---|
| Trend risky universe size | N | 8 |
| Trend candidate cap | K | 4 |
| Trend score | Rank metric | m_faber / rv_252d |
| Trend positivity filter | Threshold | m_faber > 0 |
| Pair engine | Rule | minimum variance 50/50 pair |
| Pair covariance lookback | Cov window | 504 trading days |
| Equity trend filter | Threshold | m_13612U(SPY) > 0 |
| Equity vol gate | Rule | rv_60d < rv_252d |
| Canary | Rule | m_13612U(HYG) > 0 OR m_13612U(TIP) > 0 |
| Safe selector | Rule | argmax m_13612U over SHV, IEF |
| Transaction cost | Side cost | 10 bps |
| Rebalance frequency | Cadence | monthly |
| Leverage | Gross leverage | 1.0x |
| Execution | Fill convention | next-session open |


## 4. Data and methodology

- Data panel uses live ETFs where available plus audited mutual-fund or index stitches in pre-ETF portions of history.
- Extended history before full live ETF coverage (especially pre-2006 or pre-2007 depending on ticker) is proxy-backed and is treated as lower-fidelity evidence.
- The extended window is used to test rule behavior across additional regimes, not to claim fully investable ETF history back to 1999.
- Two windows are reported: clean 18-year and extended 27-year.
- Costs are 10 bps per side, included in all reported metrics.
- Execution is modeled as signal at close on date T and fill at open on next trading session.
- Validation of rebalance-day overnight gaps shows per-asset mean absolute gap 0.2 percent to 0.9 percent; this acts only on turned-over notional, so net timing impact is 0.6 percent per year, 5 bps per rebalance.
- All headline numbers in this memo use realistic next-session open execution.


## 5. Headline results

### 5.1 Clean window (2008-05-30 to 2026-05-22), next-session open execution

| Series | Sharpe | CAGR | Vol | MaxDD | Calmar |
|---|---:|---:|---:|---:|---:|
| 60/40 blend | 1.321 | 13.25% | 9.82% | -10.66% | 1.243 |
| CPM sleeve solo | 1.242 | 14.23% | 11.27% | -16.35% | 0.870 |
| BULL sleeve solo | 1.081 | 11.44% | 10.57% | -13.35% | 0.857 |

### 5.2 Extended window (1999-03-10 to 2026-05-22), next-session open execution

| Series | Sharpe | CAGR | Vol | MaxDD | Calmar |
|---|---:|---:|---:|---:|---:|
| 60/40 blend | 1.235 | 12.32% | 9.80% | -11.18% | 1.101 |

### 5.3 Benchmark comparison against literature-inspired benchmark families (same execution, costs, and windows)

Both sleeve and benchmark-family runs use identical assumptions: monthly rebalance, signal at close, T+1 open fill, and 10 bps per side. These anchors are literature-inspired strategy-family implementations under the same data, execution, and cost harness, not claims of exact replication of any manager production strategy.

- CPM benchmark family in plain language: canonical Adaptive Asset Allocation (AAA): same cross-asset universe, 13612U momentum top-half selection, minimum-variance weighting, and duration-timed SHV/IEF safe selection, with no canary and no TIP gate.
- BULL benchmark family in plain language: HAA-Simple benchmark, hold SPY when TIP 13612U > 0 and SPY 13612U > 0, else hold the stronger of BIL or AGG by 13612U.

#### CPM sleeve versus canonical AAA benchmark

| Window | Series | Sharpe | CAGR | Vol | MaxDD | Calmar |
|---|---|---:|---:|---:|---:|---:|
| Clean | CPM sleeve | 1.242 | 14.23% | 11.27% | -16.35% | 0.870 |
| Clean | Canonical AAA benchmark | 0.970 | 11.48% | 12.00% | -20.65% | 0.556 |
| Extended | CPM sleeve | 1.164 | 13.95% | 11.82% | -16.76% | 0.832 |
| Extended | Canonical AAA benchmark | 1.032 | 11.91% | 11.55% | -20.65% | 0.577 |

| Window | dCAGR | dCalmar | dSharpe | dMaxDD | Information ratio | Return correlation | Tracking error |
|---|---:|---:|---:|---:|---:|---:|---:|
| Clean | +2.76pp | +0.315 | +0.273 | +4.30pp shallower | +0.343 | 0.827 | 6.89% |
| Extended | +2.04pp | +0.256 | +0.132 | +3.89pp shallower | +0.242 | 0.789 | 7.60% |

Verdict: CPM sleeve adds value over the canonical AAA benchmark across both windows and all core axes.

#### BULL sleeve versus HAA-Simple benchmark

| Window | Series | Sharpe | CAGR | Vol | MaxDD | Calmar |
|---|---|---:|---:|---:|---:|---:|
| Clean | BULL sleeve | 1.081 | 11.44% | 10.57% | -13.35% | 0.857 |
| Clean | HAA-Simple benchmark {BIL,AGG} | 0.960 | 11.08% | 11.70% | -19.74% | 0.561 |
| Extended | BULL sleeve | 0.920 | 9.49% | 10.45% | -13.96% | 0.680 |
| Extended | HAA-Simple benchmark {BIL,AGG} | 0.946 | 10.14% | 10.83% | -19.74% | 0.514 |

| Window | dCAGR | dCalmar | dSharpe | dMaxDD | Information ratio |
|---|---:|---:|---:|---:|---:|
| Clean | +0.36pp | +0.296 | +0.122 | +6.39pp shallower | +0.021 |
| Extended | -0.65pp | +0.166 | -0.027 | +5.78pp shallower | -0.068 |

Crisis reference points: GFC +22.3% versus -5.7%, 2022 +0.9% versus -0.1%, COVID -8.4% versus -10.6%.

COVID is the only loss episode for both series; monthly gating does not dodge a one-month gap crash.

Verdict: BULL sleeve value is drawdown control rather than return dominance; in the extended window it gives up 0.65pp CAGR and 0.027 Sharpe versus the HAA-Simple benchmark, but improves MaxDD by 5.78pp and Calmar by 0.166.

Data caveat: BIL and AGG do not provide real-open OHLC in this harness, so rebalance-day fills for those legs fall back to close-to-close; impact is immaterial.

### 5.4 SPY and QQQ buy-and-hold excess with exposure caveat (clean window)

| Series | CAGR | Sharpe | MaxDD | Calmar | Excess CAGR vs SPY | Excess CAGR vs QQQ | Beta to SPY | Avg risky exposure |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 60/40 blend | 13.25% | 1.321 | -10.66% | 1.243 | +1.52% | -3.70% | 0.16 | 75.7% |
| CPM sleeve solo | 14.23% | 1.242 | -16.35% | 0.870 | +2.51% | -2.71% | 0.15 | 86.6% |
| BULL sleeve solo | 11.44% | 1.081 | -13.35% | 0.857 | -0.29% | -5.50% | 0.17 | 59.4% |
| SPY buy-and-hold | 11.73% | 0.660 | -50.70% | 0.231 | 0.00% | -5.22% | 1.00 | 100.0% |
| QQQ buy-and-hold | 16.94% | 0.816 | -49.37% | 0.343 | +5.22% | 0.00% | 1.04 | 100.0% |

The blend improves drawdown-adjusted risk versus SPY and QQQ, but it trails QQQ on clean-window CAGR.

Excess versus always-long SPY and QQQ is largely lower-beta de-risking plus cross-asset diversification, not stock-selection skill; the blend trails QQQ on raw CAGR.

### 5.5 Structural decomposition versus benchmark families

All decomposition cells use the same execution and cost assumptions as the headline sleeves: signal at month-end close, trade at next-session open (T+1 MOO exact), and 10 bps per side. CPM uses the canonical AAA anchor as all-off (U,R,P,C = 0,0,0,0: 0.970 / 0.556 / -20.65%) and production CPM as all-on (1,1,1,1: 1.242 / 0.870 / -16.35%).

On the canonical-AAA-anchored CPM factorial, canary and universe are the first-order contributors. Main effects are canary +0.1612 Sharpe and +0.2277 Calmar, universe +0.1683 Sharpe and +0.1512 Calmar. Within the production CPM structure, adding the canary to the no-canary variant moves clean MaxDD from -35.27% to -16.35%, with +0.2205 Sharpe, +0.5061 Calmar, and +18.92pp MaxDD. Universe dependence remains explicit: on canonical AAA itself, none -> canary moves clean MaxDD from -20.65% to -20.82%, while on the production CPM structure it moves from -35.27% to -16.35%.

Ranker is the weakest CPM factor and sign-flips across metrics and windows (clean +0.0370 Sharpe and +0.0402 Calmar; extended -0.0078 Sharpe and -0.0206 Calmar), so vol-adjusted Faber is treated as a convention and parsimony choice, not a strong standalone contributor. Pairing main effect is negative in both windows (clean -0.0931 Sharpe and -0.1152 Calmar; extended -0.0701 Sharpe and -0.0692 Calmar). The no-pair clean grid point 1.294 / 0.962 / -15.15% (U,R,C on; P off) dominates all-on CPM; this is a factorial observation, not a production recommendation, and pairing remains for governance and concentration control. Dominant interactions are R x P -0.1226 clean and -0.1118 extended, plus P x C +0.1112 clean and +0.1058 extended, and R x C +0.1112 clean and +0.1006 extended.

The derived CPM ladder is C -> U -> R -> P, with clean cumulative path 0.970 / 0.556 / -20.65% (0000) -> 1.070 / 0.572 / -20.82% (0001) -> 1.218 / 0.691 / -20.40% (1001) -> 1.294 / 0.962 / -15.15% (1101) -> 1.242 / 0.870 / -16.35% (1111). BULL decomposition is unchanged and remains interaction-dominated. Full CPM 16-cell and BULL 8-cell grids, main effects, and interactions are in Sections 12.5 and 12.6.


## 6. Risk and drawdown analysis

- Structural drawdown floor: in the tested monthly framework, blend troughs cluster near -10 percent to -12 percent across major stress slices.
- Blend crisis MaxDD under the selected slow volatility gate (from the lag-robust crisis table):
  - Dot-com: -5.98 percent.
  - GFC: -10.00 percent.
  - COVID-2020: -9.82 percent.
  - 2022: -5.84 percent.
- BULL sleeve crisis MaxDD under the same gate:
  - Dot-com: -12.49 percent.
  - GFC: -13.66 percent.
  - COVID-2020: -12.44 percent.
  - 2022: -0.30 percent.
- CPM sleeve crisis profile from the canary crisis table and full-sample anchors:
  - GFC MaxDD: -15.91 percent.
  - COVID-2020 MaxDD: -13.12 percent.
  - 2022 MaxDD: -9.60 percent.
  - Extended-window full-sample MaxDD: -16.76 percent.
- Contiguous worst stretches for the blend show the same floor behavior:
  - Worst 1-year Sharpe -0.986 with MaxDD only -4.74 percent.
  - Worst 3-year Sharpe 0.701 with MaxDD -10.66 percent.
- Monthly-cadence blind spot is explicit: 2020 flash dynamics are not solved by monthly signal updates, and intramonth overlays show material whipsaw cost.


## 7. Design rationale (principled, present tense)

The two sleeves share a broad-risk canary and a common safe-asset timing convention, and the system uses monthly sleeve-level gates rather than intramonth overlays. Faster intramonth overlays add churn and do not improve full-system drawdown-adjusted compounding after costs.

Production volatility gate in the BULL sleeve is rv_60d(SPY) < rv_252d(SPY). This slower crossover is kept for lag robustness and reduced whipsaw under realistic next-session-open fills. Section 8.11 shows gate-OFF months are genuinely higher-volatility regimes, and even false-positive months still run above gate-ON baseline volatility.

The canary keeps two permissive inputs, HYG OR TIP. High-yield carries most of the historical signal, and TIP is retained as a second permissive input for governance robustness and reduced single-proxy dependence, despite lower tested performance than high-yield only. This is a governance choice, not a backtest-optimal choice; Section 8.6 reports the tradeoff directly.

K=4 is the floor for real pair-selection freedom. The minimum-variance pair is drawn from C(K,2) candidate pairs: K=4 gives 6 pairs while all candidates remain top-half trend-qualified, K=3 gives 3 pairs, and K=2 gives 1 pair with no combinatorial choice. Section 8.1 shows K=4 as the best clean-extended balance with K=5 as a close shoulder.

The positive-trend screen is kept because per-asset breakdowns still occur when the broad canary is permissive. Section 8.2 shows materially deeper drawdown when the positive-trend screen is removed.

The ranker stays 10m-SMA-distance divided by rv_252d for extended-window drawdown robustness and parsimony. Section 8.3 shows faster 13612U and rv variants are competitive in clean-window Sharpe but give up extended-window drawdown robustness.

The pair engine stays minimum-variance because it delivers the best clean-window drawdown-adjusted profile and the most balanced clean-extended tradeoff. Section 8.4 also shows the lowest-average-volatility pair slightly edges minimum-variance on extended MaxDD and extended Calmar.

The 504-day covariance lookback is kept because it is the joint clean-window Sharpe and Calmar optimum with a short local stability shelf at 504 to 756 days. Section 8.10 shows a gradual and graceful decline for longer windows, not a knife-edge parameter.

The safe sleeve keeps SHV versus IEF timing instead of fixed cash or fixed duration because defensive regimes differ; one static safe asset cannot capture both 2008-style duration rallies and 2022-style duration stress.

The strategy does not add extra CPM sleeve complexity to solve a BULL sleeve drawdown floor. Governance principle is to solve drawdown where it originates and avoid added complexity that lowers total-system compounding.


## 8. Robustness and sensitivity

### 8.1 Selection-count sensitivity (60/40 blend, K in {2,3,4,5,6})

| K | Clean Sharpe | Clean CAGR | Clean MaxDD | Clean Calmar | Extended Sharpe | Extended CAGR | Extended MaxDD | Extended Calmar |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2 | 0.936 | 10.41% | -15.12% | 0.688 | 0.989 | 11.11% | -15.12% | 0.735 |
| 3 | 1.137 | 11.94% | -12.80% | 0.933 | 1.159 | 12.03% | -12.80% | 0.940 |
| 4 (base) | 1.321 | 13.25% | -10.66% | 1.243 | 1.235 | 12.32% | -11.18% | 1.101 |
| 5 | 1.300 | 12.51% | -10.66% | 1.174 | 1.208 | 11.63% | -11.18% | 1.040 |
| 6 | 1.293 | 12.06% | -10.17% | 1.186 | 1.174 | 10.89% | -14.24% | 0.765 |

Read: K=4 gives the best clean and extended balance, K=5 is a close shoulder, K=6 keeps acceptable clean Sharpe but degrades extended MaxDD and Calmar, and K=2 or K=3 is structurally weak from candidate-pair starvation.

### 8.2 Screen 2x2 sensitivity

| Variant | Clean Sharpe | Clean CAGR | Clean MaxDD | Clean Calmar | Extended Sharpe | Extended CAGR | Extended MaxDD | Extended Calmar |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| K-cap ON + positive-trend ON (base) | 1.321 | 13.25% | -10.66% | 1.243 | 1.235 | 12.32% | -11.18% | 1.101 |
| K-cap OFF + positive-trend ON | 1.286 | 11.72% | -10.17% | 1.151 | 1.163 | 10.52% | -14.24% | 0.739 |
| K-cap ON + positive-trend OFF | 1.328 | 13.23% | -15.46% | 0.855 | 1.214 | 12.02% | -15.46% | 0.777 |
| K-cap OFF + positive-trend OFF | 1.374 | 11.22% | -15.28% | 0.734 | 1.247 | 10.16% | -15.28% | 0.664 |

Read: positive-trend screening is the main drawdown control in this 2x2, while removing the K-cap weakens extended-window drawdown.

### 8.3 Ranker sensitivity

| Ranker design | Clean Sharpe | Clean CAGR | Clean MaxDD | Clean Calmar | Extended Sharpe | Extended CAGR | Extended MaxDD | Extended Calmar |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 10m-SMA-distance divided by rv_252d (base) | 1.321 | 13.25% | -10.66% | 1.243 | 1.235 | 12.32% | -11.18% | 1.101 |
| Multi-horizon 13612U divided by rv_252d, positive 10m-SMA screen | 1.346 | 13.59% | -10.66% | 1.276 | 1.284 | 13.11% | -13.23% | 0.990 |
| Multi-horizon 13612U divided by rv_252d, positive 13612U screen | 1.349 | 13.57% | -13.04% | 1.040 | 1.295 | 13.19% | -13.23% | 0.997 |
| Plain 12-month momentum | 1.229 | 12.80% | -14.83% | 0.863 | 1.147 | 12.57% | -14.83% | 0.848 |

Read: faster multi-horizon 13612U and vol variants are competitive on clean-window Sharpe, but the base ranker keeps better extended-window drawdown robustness and a simpler rule set.

### 8.4 Pairing-rule sensitivity

| Pair rule | Clean Sharpe | Clean CAGR | Clean MaxDD | Clean Calmar | Extended Sharpe | Extended CAGR | Extended MaxDD | Extended Calmar |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Minimum-variance pair on 504d covariance (base) | 1.321 | 13.25% | -10.66% | 1.243 | 1.235 | 12.32% | -11.18% | 1.101 |
| Minimum-correlation pair | 1.276 | 13.50% | -12.70% | 1.063 | 1.236 | 12.86% | -12.70% | 1.013 |
| Top-ranked anchor plus lowest-correlation partner | 1.243 | 13.45% | -12.77% | 1.053 | 1.135 | 12.14% | -12.77% | 0.951 |
| Lowest average-volatility pair | 1.275 | 13.06% | -10.67% | 1.225 | 1.216 | 12.02% | -10.67% | 1.127 |

Read: minimum-variance provides the best clean-window drawdown-adjusted profile and the most balanced clean-extended tradeoff. Lowest average-volatility slightly edges it on extended MaxDD (-10.67% versus -11.18%) and extended Calmar (1.127 versus 1.101), so the choice is balanced rather than dominant on every axis.

### 8.5 Blend weight sensitivity (CPM/BULL 80/20 to 30/70)

| CPM/BULL | Clean Sharpe | Clean CAGR | Clean MaxDD | Clean Calmar | Extended Sharpe | Extended MaxDD | Extended Calmar |
|---|---:|---:|---:|---:|---:|---:|---:|
| 80/20 | 1.300 | 13.76% | -13.03% | 1.056 | 1.218 | -13.69% | 0.961 |
| 70/30 | 1.316 | 13.51% | -11.33% | 1.192 | 1.233 | -12.33% | 1.034 |
| 60/40 (base) | 1.321 | 13.25% | -10.66% | 1.243 | 1.235 | -11.18% | 1.101 |
| 50/50 | 1.312 | 12.97% | -11.10% | 1.169 | 1.221 | -11.10% | 1.070 |
| 40/60 | 1.289 | 12.69% | -11.55% | 1.099 | 1.189 | -11.55% | 0.990 |
| 30/70 | 1.253 | 12.39% | -11.99% | 1.033 | 1.139 | -11.99% | 0.914 |

Read: weight sensitivity is a broad plateau, not a narrow spike; 60/40 sits near the center.

### 8.6 Canary and safe-sleeve sensitivity

#### Canary sensitivity

| Canary design | Clean Sharpe | Clean CAGR | Clean MaxDD | Clean Calmar | Extended Sharpe | Extended CAGR | Extended MaxDD | Extended Calmar |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Dual canary: high-yield OR inflation-protected trend (base) | 1.321 | 13.25% | -10.66% | 1.243 | 1.235 | 12.32% | -11.18% | 1.101 |
| No canary | 1.151 | 12.25% | -21.36% | 0.574 | 1.127 | 11.73% | -22.18% | 0.529 |
| Inflation-protected only | 1.274 | 11.95% | -10.66% | 1.121 | 1.227 | 10.95% | -10.77% | 1.017 |
| High-yield only | 1.363 | 13.48% | -10.66% | 1.265 | 1.282 | 12.69% | -11.18% | 1.134 |

Read: canary remains essential for drawdown control; no-canary materially deepens drawdown. High-yield carries most of the historical signal, and production keeps TIP as a second permissive input for governance robustness and reduced single-proxy dependence, despite lower tested performance than high-yield only; this is governance, not backtest-optimality.

#### Safe sleeve sensitivity

| Safe design | Clean Sharpe | Clean CAGR | Clean MaxDD | Clean Calmar | Extended Sharpe | Extended CAGR | Extended MaxDD | Extended Calmar |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Timed SHV or IEF by 13612U (base) | 1.321 | 13.25% | -10.66% | 1.243 | 1.235 | 12.32% | -11.18% | 1.101 |
| SHV only | 1.263 | 11.92% | -14.08% | 0.847 | 1.195 | 11.32% | -14.28% | 0.793 |
| IEF only | 1.282 | 13.31% | -16.94% | 0.786 | 1.225 | 12.55% | -16.94% | 0.741 |
| Static 50/50 SHV and IEF | 1.297 | 12.65% | -12.09% | 1.046 | 1.228 | 11.96% | -12.09% | 0.989 |

Read: timed duration selection captures both defensive regimes.

### 8.7 Rolling-window out-of-sample stability (fixed convention-locked parameters)

No parameters are re-estimated or optimized within rolling folds; rolling results evaluate the fixed final rules only. In-sample bias exists at the design and structure-selection level. Only forward live or paper-traded data is truly out-of-sample.

Method definition used for rolling metrics: lookbacks are calendar-day windows with days_lookback = int(N * 365.25), so 3-year uses 1095 days and 5-year uses 1826 days. Windows require at least 100 trading-day observations. Rolling Sharpe uses raw annualized Sharpe = (mean(daily) * 252) / (std(daily, ddof=0) * sqrt(252)), with annualization factor 252. The worst-contiguous-stretch scan uses the same calendar-day window lengths and the same 100-observation floor.

| Metric | Value |
|---|---:|
| Clean rolling 5-year Sharpe above 1.0 | 97.0% |
| Clean rolling 5-year Sharpe above 0.7 | 100.0% |
| Clean rolling 5-year minimum Sharpe | 0.727 |
| Clean rolling 3-year Sharpe above 0.7 | 100.0% |
| Clean 5-year minimum Sharpe, CPM sleeve solo | 0.526 |
| Clean 5-year minimum Sharpe, BULL sleeve solo | 0.692 |
| Worst contiguous 1-year blend Sharpe | -0.986 |
| Worst contiguous 1-year blend MaxDD | -4.74% |
| Worst contiguous 3-year blend Sharpe | 0.701 |
| Worst contiguous 3-year blend MaxDD | -10.66% |

Read: the blend raises the rolling worst-case floor versus either solo sleeve on multi-year windows.

### 8.8 Execution cost and timing sensitivity

Scenario definitions:
- Next-session open exact (headline basis): old weights earn signal-close to next-open return, then new weights apply from the open onward.
- Conservative open-fill: rebalance overnight segment is removed or penalized to avoid any close-to-open attribution ambiguity; this is a stress lower bound.

The next-session open exact scenario is the headline basis because it matches the implemented timing convention without injecting extra pessimism.

| Scenario (slow volatility gate) | Clean Sharpe | Clean CAGR | Clean MaxDD | Clean Calmar |
|---|---:|---:|---:|---:|
| Next-session open exact (headline basis) | 1.321 | 13.25% | -10.66% | 1.243 |
| Conservative open-fill assumption (stress lower bound) | 1.165 | 11.39% | -11.13% | 1.023 |

Additional timing facts from the execution study:
- Rebalance-day mean absolute overnight gaps are 0.2 percent to 0.9 percent by asset.
- Because only turnover notional is exposed to timing mismatch, net effect on portfolio CAGR is 0.6 percent per year, 5 bps per rebalance.

Read: execution convention matters, but realistic next-session open implementation remains close to close-signal proxy once turnover weighting is handled correctly.

### 8.9 Asset-concentration check (CPM sleeve contribution shares)

| Asset | Clean share of 8 risky | Extended share of 8 risky |
|---|---:|---:|
| SPHQ | 28.1% | 16.8% |
| GLD | 21.8% | 16.4% |
| QQQ | 17.6% | 20.4% |
| EFA | 8.9% | 10.5% |
| VNQ | 3.4% | 11.3% |
| TLT | 11.7% | 10.2% |
| DBC | 8.1% | 13.9% |
| EEM | 0.4% | 0.6% |
| Total | 100.0% | 100.0% |

Note: contribution shares are selection-driven and reported across all 8 risky assets; no asset is dropped from the concentration table.

Read: clean-window concentration is led by SPHQ, GLD, and QQQ, while extended-window shares are more balanced; EEM remains a low-weight, low-share member of the universe.

### 8.10 Covariance-lookback sensitivity (CPM sleeve pair engine)

| Cov lookback | Clean Sharpe | Clean MaxDD | Clean Calmar |
|---|---:|---:|---:|
| 126d | 1.265 | -14.80% | 0.859 |
| 252d | 1.216 | -12.70% | 0.946 |
| 504d (base) | 1.321 | -10.66% | 1.243 |
| 756d | 1.307 | -10.66% | 1.224 |
| 1008d | 1.275 | -12.70% | 1.011 |
| 1260d | 1.257 | -12.70% | 1.000 |

Read: 504d is the joint Sharpe and Calmar optimum and the balanced drawdown choice. The slope is gradual and graceful with no sharp breakpoint: clean Sharpe steps 1.321 at 504d to 1.307 at 756d to 1.275 at 1008d to 1.257 at 1260d, and clean Calmar steps 1.243 to 1.224 to 1.011 to 1.000. This supports a non-fragile parameter choice, with nearby 252d to 756d windows in a similar range and only a slow decline at longer lookbacks; short 126d and 252d are weaker on MaxDD.

### 8.11 RV-gate false-positive versus true-positive forward-vol cohorts

| Window | Cohort | Count | Mean forward SPY return | Mean forward realized vol |
|---|---|---:|---:|---:|
| Clean | True-positive gate-OFF (SPY fell) | 33 | -5.32% | 29.94% |
| Clean | False-positive gate-OFF (SPY rose) | 41 | 4.11% | 15.96% |
| Clean | Gate-ON baseline | 142 | 1.62% | 12.95% |
| Extended | True-positive gate-OFF (SPY fell) | 52 | -4.73% | 27.24% |
| Extended | False-positive gate-OFF (SPY rose) | 68 | 3.81% | 16.01% |
| Extended | Gate-ON baseline | 206 | 1.17% | 13.61% |

Read: the gate selects elevated-volatility regimes even when direction is wrong; false-positive cohorts still sit above gate-ON baseline volatility in both windows.


## 9. Statistical honesty and significance

Bootstrap Sharpe confidence intervals on clean-window next-session open returns are wide:

- 60/40 blend: point 1.321, 95 percent CI [0.909, 1.751], width 0.842.
- CPM sleeve solo: point 1.242, 95 percent CI [0.832, 1.652], width 0.821.
- BULL sleeve solo: point 1.081, 95 percent CI [0.635, 1.553], width 0.918.

Interpretation:

1. Bootstrap CIs quantify sampling variability of the fixed final rule only.
2. Deltas materially smaller than single-series CI width should not be overinterpreted without paired-difference tests. This applies to core benchmark deltas as well as sensitivity variants.
3. Bootstrap CIs do not eliminate model-selection bias from the research process, because design choices were made on historical evidence.
4. The stability study is fixed-rule rolling evaluation, not fold-wise retuning.
5. Forward expectations must haircut backtest point estimates.

Reconciling backtest Sharpe 1.3 with forward expectation 0.9 to 1.2:

- Backtest includes design-level in-sample selection.
- Extended pre-ETF segments rely on stitched proxies.
- Regime mix in the test sample includes long momentum-favorable periods.
- Real deployment includes execution frictions, implementation drift, and live behavioral constraints.


## 10. Limitations and forward expectations

Hard boundary: only forward live or paper-traded data is truly out-of-sample; all reported clean and extended windows are in-sample to the design process.

- In-sample design bias is unavoidable at the structure-selection level.
- Extended history includes pre-2006 and pre-2007 proxy segments for parts of the universe.
- Sharpe confidence intervals are wide, so fine-grained ranking claims are weak.
- Structural residual drawdown floor remains in low double digits in this monthly architecture.
- Residual drawdown concentration remains tied to equity sleeve regime timing in adverse sequences.
- Monthly cadence has intramonth latency; it cannot fully react to flash-crash style paths.

Forward base-case remains:

- Sharpe 0.9 to 1.2.
- CAGR 8 to 12 percent.

Even at the lower end of this range, the strategy remains attractive for a drawdown-controlled compounding role rather than maximum equity-like CAGR.


## 11. Implementation and operational notes

- Rebalance cadence: monthly, signal at month-end close, execution at next-session open.
- Parameters are convention-locked and not refit each month.
- Instruments: liquid ETFs for risky and safe sleeves, with stitched proxy history only for historical backtest continuity.
- Scope note: this memo covers only the 60/40 two-sleeve CPM-BULL strategy and does not include any three-sleeve scorecard.


## 12. Reproduction and appendix

### 12.1 Code pointers

- `cpm_live.py` (trend sleeve construction, canary, safe selector, backtest wiring)
- `bull_qqq_live.py` (equity sleeve gating and safe fallback)
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
| pair_rule | minimum-variance 50/50 pair |
| pair_cov_lookback_days | 504 |
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

- `research/two_sleeve_60_40_ci_walkforward_findings.md`
- `research/exec_lag_moo_validation_findings_2026_05_30.md`
- `research/vol_gate_calmar_objective_findings.md`
- `research/two_sleeve_cpm_bull_findings.md`
- `research/cpm_topk_sweep_findings.md`
- `research/cpm_screen_2x2_findings.md`
- `research/cpm_ranker_13612u_vol_findings.md`
- `research/cpm_pairing_rules_findings.md`
- `research/cpm_safe_isolation_findings.md`
- `research/cpm_canary_ablation_findings.md`
- `research/cpm_hyglqd_canary_findings.md`
- `research/bull_daily_trend_overlay_findings.md`
- `research/bull_kmlm_convex_safe_findings.md`
- `research/factorial_decomposition_findings.md`
- `research/cpm_factorial_canonical_aaa_findings.md`
- `research/cpm_vs_canonical_aaa_findings.md`

### 12.5 Full factorial grids (canonical-AAA-anchored CPM + BULL benchmark decomposition)

Execution label for every row in this section: month-end close signal, T+1 MOO exact fill, post-cost 10 bps per side.

#### 12.5.1 CPM canonical-AAA-anchored factorial (2^4 cells)

Config order is U,R,P,C where 1 means production setting and 0 means canonical AAA setting.

| Config (U,R,P,C) | CLEAN Sharpe | CLEAN Calmar | CLEAN MaxDD | EXT Sharpe | EXT Calmar | EXT MaxDD |
|---|---:|---:|---:|---:|---:|---:|
| 0,0,0,0 (canonical AAA) | 0.970 | 0.556 | -20.65% | 1.032 | 0.577 | -20.65% |
| 0,0,0,1 | 1.070 | 0.572 | -20.82% | 1.096 | 0.578 | -20.82% |
| 0,0,1,0 | 0.873 | 0.441 | -23.74% | 0.928 | 0.466 | -24.54% |
| 0,0,1,1 | 0.994 | 0.634 | -17.68% | 0.982 | 0.624 | -18.54% |
| 0,1,0,0 | 1.002 | 0.585 | -20.66% | 1.026 | 0.566 | -20.66% |
| 0,1,0,1 | 1.197 | 0.828 | -16.17% | 1.151 | 0.766 | -16.17% |
| 0,1,1,0 | 0.802 | 0.272 | -36.09% | 0.929 | 0.310 | -36.76% |
| 0,1,1,1 | 1.068 | 0.687 | -17.42% | 1.091 | 0.685 | -18.28% |
| 1,0,0,0 | 1.100 | 0.676 | -20.22% | 1.166 | 0.702 | -20.22% |
| 1,0,0,1 | 1.218 | 0.691 | -20.40% | 1.249 | 0.706 | -20.40% |
| 1,0,1,0 | 1.064 | 0.604 | -22.76% | 1.146 | 0.712 | -23.13% |
| 1,0,1,1 | 1.210 | 0.846 | -17.21% | 1.222 | 0.931 | -17.96% |
| 1,1,0,0 | 1.170 | 0.771 | -18.32% | 1.140 | 0.719 | -18.32% |
| 1,1,0,1 | 1.294 | 0.962 | -15.15% | 1.209 | 0.876 | -15.15% |
| 1,1,1,0 | 1.022 | 0.364 | -35.27% | 1.047 | 0.375 | -35.59% |
| 1,1,1,1 (CPM) | 1.242 | 0.870 | -16.35% | 1.164 | 0.832 | -16.76% |

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

Conclusion: BULL is a joint gate-and-safe design, not a sum of independent improvements; the realized-vol gate alone does not reliably improve Calmar, and its drawdown benefit appears when paired with the SHV/IEF defensive selector.

### 12.6 Main effects and interactions (config + window + execution)

Execution label for every effect in this section: month-end close signal, T+1 MOO exact fill, post-cost 10 bps per side. CPM effects here are from the canonical-AAA-anchored sensitivity grid in Section 12.5.1.

Note: "Heuristic average across listed deltas" mixes Sharpe and Calmar deltas and is a directional summary, not a formal test statistic.

#### 12.6.1 CPM main effects

| Factor | CLEAN dSharpe | CLEAN dCalmar | EXT dSharpe | EXT dCalmar | Heuristic average across listed deltas |
|---|---:|---:|---:|---:|---:|
| Universe (U) | +0.1683 | +0.1512 | +0.1385 | +0.1601 | +0.1545 |
| Canary (C) | +0.1612 | +0.2277 | +0.0938 | +0.1963 | +0.1698 |
| Ranker (R) | +0.0370 [SIGN-FLIP] | +0.0402 [SIGN-FLIP] | -0.0078 [SIGN-FLIP] | -0.0206 [SIGN-FLIP] | +0.0122 |
| Pair weighting (P) | -0.0931 | -0.1152 [SIGN-FLIP] | -0.0701 | -0.0692 [SIGN-FLIP] | -0.0869 |

Dominant CPM two-way interactions from the factorial (Calmar deltas):

| Interaction | CLEAN dCalmar | EXT dCalmar | Interpretation |
|---|---:|---:|---|
| R x P | -0.1226 | -0.1118 | Ranker and pairing are substitutes. |
| P x C | +0.1112 | +0.1058 | Canary unlocks pairing value. |
| R x C | +0.1112 | +0.1006 | Canary unlocks ranker value. |

#### 12.6.2 BULL main effects

| Factor | CLEAN dSharpe | CLEAN dCalmar | EXT dSharpe | EXT dCalmar | Heuristic average across listed deltas |
|---|---:|---:|---:|---:|---:|
| Safe pool (S) | +0.005 [FLIP] | +0.137 [FLIP] | +0.009 | +0.114 [FLIP] | +0.066 |
| Vol gate (V) | +0.081 | +0.089 [FLIP] | +0.006 [FLIP] | +0.027 [FLIP] | +0.051 |
| Canary breadth (K) | +0.006 [FLIP] | +0.048 | -0.069 | +0.017 [FLIP] | +0.000 |

Dominant BULL two-way interactions from the factorial:

| Interaction | CLEAN dCalmar | EXT dCalmar |
|---|---:|---:|
| V x S | +0.143 | +0.115 |
| K x V | -0.036 | n/a |
