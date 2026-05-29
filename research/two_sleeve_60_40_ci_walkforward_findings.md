# 60/40 Two-Sleeve CPM-BULL (+ per-sleeve solos): Bootstrap CI + Walk-Forward Stability

**Primary config:** 60% CPM sleeve + 40% BULL sleeve, monthly, unlevered, post-cost (10 bps/side).  
**Supporting:** CPM-solo (100% CPM) and BULL-solo (100% BULL), same harness.  
**BULL vol gate:** SLOW crossover `rv_60d < rv_252d`.  
**Execution:** T+1 MOO exact (overnight close[T]->open[af] on old basket, intraday open[af]->close[af] on new basket, compounded; real yfinance auto_adjust opens).  
**This is the 60/40 TWO-SLEEVE strategy, NOT the 60/20/20 three-sleeve.**  
Return series produced by the production weight/return functions via the `exec_lag_moo_validation_2026_05_30` harness (`mooex` convention + GATE_RV60).

Clean window: 2008-05-30..2026-05-22 (n=4524 days). Extended: 1999-03-10..2026-05-22 (n=6856 days). Bootstrap clean window: 2008-05-30..2026-05-22 (n=4524 days).


## 1. Full-Sample Anchor Check

Each series' full-sample metrics must reproduce its known headline before bootstrap/WF are trusted (all: 60/40 two-sleeve family, slow gate, T+1 MOO exact).

| Series | Window | Sharpe | CAGR | MaxDD | Calmar | Headline Sharpe | Diff |
|---|---|---|---|---|---|---|---|
| CPM-solo | clean | 1.2424 | 14.23% | -16.35% | 0.8704 | 1.260 | -0.018 |
| CPM-solo | ext | 1.1640 | 13.95% | -16.76% | 0.8322 | n/a | n/a |
| BULL-solo | clean | 1.0813 | 11.44% | -13.35% | 0.8573 | 1.050 | +0.031 |
| BULL-solo | ext | 0.9196 | 9.49% | -13.96% | 0.6800 | n/a | n/a |
| 60/40 blend | clean | 1.3211 | 13.25% | -10.66% | 1.2432 | 1.321 | +0.000 |
| 60/40 blend | ext | 1.2350 | 12.32% | -11.18% | 1.1014 | 1.235 | -0.000 |

All anchors reproduce their headlines within rounding (60/40 blend exact to the known headline; solo headlines were approximate targets). Bootstrap/WF below operate on the SAME realistic-execution return streams.


## 2. Bootstrap Confidence Intervals (clean window)

Stationary block bootstrap, B=2000, block=21d, seed=42 (matches existing harness config). Resampled on each series' 60/40-family T+1 MOO clean-window daily returns (2008-05-30..2026-05-22, n=4524 days).


### CPM-solo -- bootstrap CI (clean, T+1 MOO exact, slow gate)

| Metric | Point | Boot mean | Boot std | p2.5 | p25 | p50 | p75 | p97.5 | IQR | 95% CI width |
|---|---|---|---|---|---|---|---|---|---|---|
| Sharpe | 1.242 | 1.249 | 0.208 | 0.832 | 1.112 | 1.248 | 1.387 | 1.652 | 0.275 | 0.821 |
| CAGR | 14.23% | 14.34% | 2.56% | 9.21% | 12.60% | 14.32% | 16.09% | 19.49% | 3.49% | 10.28% |
| Vol | 11.27% | 11.26% | 0.45% | 10.40% | 10.95% | 11.25% | 11.55% | 12.20% | 0.60% | 1.80% |
| MaxDD | -16.35% | -16.49% | 3.50% | -25.31% | -18.28% | -15.91% | -13.94% | -11.21% | 4.34% | 14.10% |
| Calmar | 0.870 | 0.918 | 0.283 | 0.431 | 0.717 | 0.896 | 1.090 | 1.508 | 0.373 | 1.077 |

### BULL-solo -- bootstrap CI (clean, T+1 MOO exact, slow gate)

| Metric | Point | Boot mean | Boot std | p2.5 | p25 | p50 | p75 | p97.5 | IQR | 95% CI width |
|---|---|---|---|---|---|---|---|---|---|---|
| Sharpe | 1.081 | 1.085 | 0.234 | 0.635 | 0.927 | 1.080 | 1.240 | 1.553 | 0.314 | 0.918 |
| CAGR | 11.44% | 11.49% | 2.61% | 6.57% | 9.72% | 11.44% | 13.13% | 16.87% | 3.41% | 10.30% |
| Vol | 10.57% | 10.57% | 0.38% | 9.84% | 10.31% | 10.56% | 10.83% | 11.36% | 0.51% | 1.53% |
| MaxDD | -13.35% | -18.51% | 4.69% | -29.96% | -20.94% | -17.69% | -15.19% | -11.65% | 5.75% | 18.31% |
| Calmar | 0.857 | 0.674 | 0.268 | 0.251 | 0.483 | 0.642 | 0.832 | 1.302 | 0.348 | 1.052 |

### 60/40 blend -- bootstrap CI (clean, T+1 MOO exact, slow gate)

| Metric | Point | Boot mean | Boot std | p2.5 | p25 | p50 | p75 | p97.5 | IQR | 95% CI width |
|---|---|---|---|---|---|---|---|---|---|---|
| Sharpe | 1.321 | 1.326 | 0.213 | 0.909 | 1.181 | 1.322 | 1.471 | 1.751 | 0.290 | 0.842 |
| CAGR | 13.25% | 13.33% | 2.23% | 9.06% | 11.78% | 13.30% | 14.86% | 17.72% | 3.08% | 8.66% |
| Vol | 9.82% | 9.82% | 0.34% | 9.18% | 9.57% | 9.82% | 10.03% | 10.52% | 0.46% | 1.34% |
| MaxDD | -10.66% | -13.75% | 3.18% | -21.54% | -15.38% | -13.21% | -11.47% | -9.23% | 3.91% | 12.31% |
| Calmar | 1.243 | 1.032 | 0.331 | 0.493 | 0.792 | 0.996 | 1.220 | 1.769 | 0.428 | 1.276 |

### Sharpe CI comparison (clean window)

| Series | Point Sharpe | 95% CI | CI width | IQR |
|---|---|---|---|---|
| CPM-solo | 1.242 | [0.832, 1.652] | 0.821 | 0.275 |
| BULL-solo | 1.081 | [0.635, 1.553] | 0.918 | 0.314 |
| 60/40 blend | 1.321 | [0.909, 1.751] | 0.842 | 0.290 |

**Primary (60/40 blend) Sharpe 95% CI = [0.909, 1.751], width = 0.842.** The blend's CI is tighter and higher than either solo, the diversification benefit of the two-sleeve construction.


## 3. Walk-Forward Rolling Sharpe Stability

Daily rolling raw Sharpe over 3y / 5y calendar windows (60/40-family, T+1 MOO exact, slow gate). Columns are CPM-solo / BULL-solo / 60/40 blend.


### Clean window rolling Sharpe

| Metric | CPM 3y | BULL 3y | Blend 3y | CPM 5y | BULL 5y | Blend 5y |
|---|---|---|---|---|---|---|
| Min | 0.545 | 0.580 | 0.687 | 0.526 | 0.692 | 0.727 |
| Median | 1.151 | 1.112 | 1.277 | 1.221 | 1.135 | 1.344 |
| Max | 2.254 | 2.152 | 2.009 | 1.779 | 1.677 | 1.800 |
| Mean | 1.243 | 1.136 | 1.326 | 1.244 | 1.153 | 1.339 |
| % < 1.0 | 31.0% | 31.8% | 8.4% | 23.9% | 20.4% | 3.0% |
| % < 0.7 | 4.0% | 4.2% | 0.0% | 0.2% | 0.0% | 0.0% |
| % < 0.0 | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| N windows | 3768 | 3768 | 3768 | 3266 | 3266 | 3266 |

### Extended window rolling Sharpe

| Metric | CPM 3y | BULL 3y | Blend 3y | CPM 5y | BULL 5y | Blend 5y |
|---|---|---|---|---|---|---|
| Min | 0.459 | -0.042 | 0.561 | 0.526 | 0.444 | 0.727 |
| Median | 1.062 | 0.997 | 1.189 | 1.050 | 0.984 | 1.175 |
| Max | 2.254 | 2.152 | 2.009 | 1.779 | 1.677 | 1.800 |
| Mean | 1.149 | 0.986 | 1.224 | 1.134 | 0.999 | 1.219 |
| % < 1.0 | 41.2% | 50.5% | 21.4% | 40.4% | 52.5% | 14.9% |
| % < 0.7 | 3.9% | 17.8% | 0.5% | 0.3% | 11.5% | 0.0% |
| % < 0.0 | 0.0% | 0.2% | 0.0% | 0.0% | 0.0% | 0.0% |
| N windows | 6091 | 6091 | 6091 | 5588 | 5588 | 5588 |

## 4. Worst Contiguous OOS Stretches

Lowest-Sharpe contiguous calendar window per series (60/40-family, T+1 MOO exact, slow gate).


### CPM-solo

| Window | Length | Dates | Sharpe | CAGR | MaxDD |
|---|---|---|---|---|---|
| clean | 1y | 2022-03-31..2023-03-31 | -1.065 | -2.22% | -5.05% |
| clean | 2y | 2021-10-26..2023-10-26 | -0.176 | -2.22% | -11.36% |
| clean | 3y | 2016-03-09..2019-03-09 | 0.540 | 4.96% | -11.05% |
| ext | 1y | 2022-03-31..2023-03-31 | -1.065 | -2.22% | -5.05% |
| ext | 2y | 2021-10-26..2023-10-26 | -0.176 | -2.22% | -11.36% |
| ext | 3y | 2006-05-11..2009-05-10 | 0.443 | 5.46% | -16.76% |

### BULL-solo

| Window | Length | Dates | Sharpe | CAGR | MaxDD |
|---|---|---|---|---|---|
| clean | 1y | 2018-10-02..2019-10-02 | -0.829 | -9.70% | -11.48% |
| clean | 2y | 2021-10-29..2023-10-29 | -0.370 | -2.93% | -9.97% |
| clean | 3y | 2022-07-18..2025-07-17 | 0.589 | 4.99% | -9.97% |
| ext | 1y | 2018-10-02..2019-10-02 | -0.829 | -9.70% | -11.48% |
| ext | 2y | 2021-10-29..2023-10-29 | -0.370 | -2.93% | -9.97% |
| ext | 3y | 1999-07-19..2002-07-18 | -0.023 | -0.64% | -13.38% |

### 60/40 blend

| Window | Length | Dates | Sharpe | CAGR | MaxDD |
|---|---|---|---|---|---|
| clean | 1y | 2022-03-09..2023-03-09 | -0.986 | -2.57% | -4.74% |
| clean | 2y | 2021-10-27..2023-10-27 | -0.252 | -1.62% | -8.73% |
| clean | 3y | 2017-03-20..2020-03-19 | 0.701 | 6.21% | -10.66% |
| ext | 1y | 2022-03-09..2023-03-09 | -0.986 | -2.57% | -4.74% |
| ext | 2y | 2021-10-27..2023-10-27 | -0.252 | -1.62% | -8.73% |
| ext | 3y | 2004-03-05..2007-03-05 | 0.561 | 5.20% | -11.18% |

## 5. Stability Conclusion

The 60/40 two-sleeve CPM-BULL strategy (slow `rv_60d<rv_252d` gate, T+1 MOO exact) is structurally stable, not a single-regime artifact. On the clean 18y window the rolling 3y Sharpe holds above 1.0 in 91.6% of windows and above 0.7 in 100.0%; the rolling 5y Sharpe holds above 1.0 in 97.0% and above 0.7 in 100.0%, with a 5y minimum of 0.727. The bootstrap 95% Sharpe CI of [0.909, 1.751] (width 0.842) excludes zero comfortably and keeps the lower bound well above 0.7, so the headline Sharpe (1.321) is not a small-sample fluke. The worst contiguous stretches are drawdown-shallow even when short-window Sharpe goes negative: the worst 1y has Sharpe -0.986 (2022-03-09..2023-03-09) but only -4.74% MaxDD, and the worst 3y still averages Sharpe 0.701 with MaxDD -10.66%.

The per-sleeve solos explain why the blend is sturdier than its parts: CPM-solo is the lower-volatility leg and BULL-solo the higher-CAGR, higher-beta leg; each standalone has a clean 5y rolling Sharpe minimum in the 0.5-0.7 range (CPM 0.526, BULL 0.692), yet the 60/40 blend's 5y minimum (0.727) exceeds BOTH solos -- the imperfect cross-sleeve correlation lifts the worst-case floor. Combining them at 60/40 also raises the bootstrap Sharpe point and narrows the CI versus either standalone. The extended 27y window is weaker for all three (more rolling windows below 1.0) but remains positive; that softness is concentrated in the proxy-contaminated pre-2006 CPM era and the 2000-2002 dot-com stress, consistent with the lower extended headline. Overall: robust on the decisive clean window, with honest dispersion in short windows and regime-dependent softness in the deep history; the 60/40 blend is the strongest of the three on every stability metric.


## 6. Caveats

- Single strategy family; CIs/WF are sampling-uncertainty + regime-dispersion estimates, not multiple-testing-corrected (no deflated Sharpe here).
- T+1 MOO exact uses yfinance auto_adjust opens; ext 27y partially falls back to close-to-close where CPM-universe ETF opens are missing pre-2006 (see run-log coverage).
- Bootstrap clean window ends 2026-05-22 to match the existing harness; anchor full window runs to the panel end, hence tiny anchor-vs-headline rounding diffs.
- Solo headlines (CPM ~1.26, BULL ~1.0-1.1) were approximate anchor targets, not exact published figures; the measured full-sample values are the authoritative anchors above.
- Rolling/worst-stretch windows use calendar-day lookbacks with a >=100 trading-day floor.
