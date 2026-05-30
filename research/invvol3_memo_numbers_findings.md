# CPM INVVOL-3 memo numbers (fresh re-run)

All CPM-side numbers regenerated under the **production INVVOL-3** CPM sleeve weighting (min-variance 3-subset from the top-K=4 positive-trend pool, then inverse-vol weight; fallbacks 0->safe, 1->50/50 risky+safe, 2->invvol-2).

**Convention (every table):** execution T+1 MOO exact (`mooex`, real auto_adjust opens); post-cost 10 bps/side; BULL equity vol gate slow rv_60d<rv_252d; blend = 0.60*CPM(INVVOL-3) + 0.40*BULL; cov lookback 504d; K=4. Clean window 2008-05-30..2026-05-22 (18y); extended 1999-03-10..2026-05-22 (27y).

Source harness: `research/invvol3_memo_numbers.py` (read-only; CPM-solo and concentration use production `cpm_live.compute_target_weights`; Section-8 variants use a generalized INVVOL-3 weight fn whose base config reproduces production exactly).

## 0. Anchor check

| Window | Sharpe | MaxDD | Calmar | Expected | Match |
|---|---:|---:|---:|---|---|
| clean | 1.2453 | -13.19% | 1.0824 | 1.2453/-13.19%/1.0824 | CONFIRMED |
| ext | 1.2249 | -15.18% | 0.9148 | 1.2249/-15.18%/0.9148 | CONFIRMED |

CPM-solo INVVOL-3 reproduces the research anchor exactly in both windows; the rest of this file is trusted on that basis.

## 1. Headline results (config INVVOL-3, T+1 MOO exact, 10 bps/side)

### 1.1 Clean window (18y)

| Series | Sharpe | CAGR | Vol | MaxDD | Calmar |
|---|---:|---:|---:|---:|---:|
| CPM-solo (INVVOL-3) | 1.245 | 14.28% | 11.27% | -13.19% | 1.082 |
| BULL-solo | 1.081 | 11.44% | 10.57% | -13.35% | 0.857 |
| 60/40 blend | 1.311 | 13.26% | 9.91% | -10.58% | 1.254 |

### 1.2 Extended window (27y)

| Series | Sharpe | CAGR | Vol | MaxDD | Calmar |
|---|---:|---:|---:|---:|---:|
| CPM-solo (INVVOL-3) | 1.225 | 13.89% | 11.12% | -15.18% | 0.915 |
| BULL-solo | 0.920 | 9.49% | 10.45% | -13.96% | 0.680 |
| 60/40 blend | 1.247 | 12.25% | 9.64% | -10.82% | 1.132 |

**KEY NEW HEADLINE -- 60/40 blend (CPM-INVVOL-3 + BULL), clean:** Sharpe 1.311, CAGR 13.26%, Vol 9.91%, MaxDD -10.58%, Calmar 1.254.

**MATERIAL CHANGE vs pair-era memo blend** (pair clean 1.321/13.25%/9.82%/-10.66%/1.243): the INVVOL-3 blend Sharpe is 1.311 (was 1.321), MaxDD -10.58% (was -10.66%), Calmar 1.254 (was 1.243). The old 1.321 blend headline is stale and must not be reused. BULL-solo is unchanged from the pair era (BULL is independent of the CPM weighting).

## 2. Crisis windows (INVVOL-3; MaxDD and total return)

| Crisis window | Blend MaxDD | Blend return | CPM-solo MaxDD | CPM-solo return |
|---|---:|---:|---:|---:|
| Dot-com (2000-03..2002-12) | -5.46% | 23.44% | -7.49% | 28.37% |
| GFC (2007-10..2009-06) | -9.83% | 12.13% | -13.54% | 10.55% |
| COVID (2020-02..2020-06) | -10.58% | 4.31% | -12.09% | 9.80% |
| 2022 bear (2022-01..2022-12) | -5.62% | 1.95% | -9.24% | 2.42% |

Note: crisis-window MaxDD is computed within each window (peak-to-trough inside the window), execution T+1 MOO exact, post-cost. Dot-com and GFC pre-2008 sit in the proxy-backed extended history for the CPM trend universe.

## 3. Bootstrap CI (clean window, stationary block bootstrap B=2000, block=21, seed=42)


### 60/40 blend

| Metric | Point | 95% CI | CI width |
|---|---:|---|---:|
| Sharpe | 1.311 | [0.896, 1.743] | 0.847 |
| CAGR | 13.26% | [8.87%, 17.91%] | 9.04pp |
| MaxDD | -10.58% | [-22.08%, -9.30%] | 12.78pp |
| Calmar | 1.254 | [0.474, 1.758] | 1.284 |

### CPM-solo (INVVOL-3)

| Metric | Point | 95% CI | CI width |
|---|---:|---|---:|
| Sharpe | 1.245 | [0.840, 1.659] | 0.819 |
| CAGR | 14.28% | [9.27%, 19.45%] | 10.18pp |
| MaxDD | -13.19% | [-24.73%, -10.91%] | 13.82pp |
| Calmar | 1.082 | [0.442, 1.608] | 1.166 |

### BULL-solo

| Metric | Point | 95% CI | CI width |
|---|---:|---|---:|
| Sharpe | 1.081 | [0.635, 1.553] | 0.918 |
| CAGR | 11.44% | [6.57%, 16.87%] | 10.30pp |
| MaxDD | -13.35% | [-29.96%, -11.65%] | 18.31pp |
| Calmar | 0.857 | [0.251, 1.302] | 1.052 |

**MATERIAL CHANGE vs pair-era CI:** pair-era blend Sharpe CI was [0.909, 1.751] width 0.842. INVVOL-3 blend Sharpe 95% CI = [0.896, 1.743], width 0.847.

## 4. Rolling-window stability -- 60/40 blend (INVVOL-3)

| Window | Min | Median | Max | % < 1.0 | % < 0.7 | N |
|---|---:|---:|---:|---:|---:|---:|
| Clean 3y | 0.531 | 1.364 | 1.880 | 12.4% | 1.7% | 3768 |
| Clean 5y | 0.960 | 1.331 | 1.825 | 0.2% | 0.0% | 3266 |
| Ext 3y | 0.531 | 1.219 | 1.880 | 22.2% | 1.5% | 6091 |
| Ext 5y | 0.704 | 1.233 | 1.825 | 12.0% | 0.0% | 5588 |

Worst contiguous stretches (blend):

| Window | Length | Dates | Sharpe | CAGR | MaxDD |
|---|---|---|---:|---:|---:|
| clean | 1y | 2022-03-09..2023-03-09 | -1.000 | -2.60% | -4.71% |
| clean | 2y | 2021-10-29..2023-10-29 | -0.390 | -3.26% | -10.12% |
| clean | 3y | 2022-04-08..2025-04-07 | 0.547 | 4.20% | -8.99% |
| ext | 1y | 2022-03-09..2023-03-09 | -1.000 | -2.60% | -4.71% |
| ext | 2y | 2021-10-29..2023-10-29 | -0.390 | -3.26% | -10.12% |
| ext | 3y | 2022-04-08..2025-04-07 | 0.547 | 4.20% | -8.99% |

## 5. Benchmark -- CPM-solo (INVVOL-3) vs canonical AAA (no canary)

| Window | Series | Sharpe | CAGR | Vol | MaxDD | Calmar |
|---|---|---:|---:|---:|---:|---:|
| clean | CPM-solo INVVOL-3 | 1.245 | 14.28% | 11.27% | -13.19% | 1.082 |
| clean | Canonical AAA | 0.970 | 11.48% | 12.00% | -20.65% | 0.556 |
| ext | CPM-solo INVVOL-3 | 1.225 | 13.89% | 11.12% | -15.18% | 0.915 |
| ext | Canonical AAA | 1.032 | 11.91% | 11.55% | -20.65% | 0.577 |

| Window | dCAGR | dCalmar | dSharpe | dMaxDD | Info ratio | Return corr | Tracking err |
|---|---:|---:|---:|---:|---:|---:|---:|
| clean | +2.80pp | +0.527 | +0.276 | +7.46pp | +0.341 | 0.820 | 7.01% |
| ext | +1.98pp | +0.338 | +0.193 | +5.47pp | +0.256 | 0.828 | 6.65% |

BULL vs HAA-Simple is UNCHANGED by the INVVOL-3 weighting (BULL is independent of the CPM sleeve). Re-cited from the memo: clean BULL 1.081/11.44%/10.57%/-13.35%/0.857 vs HAA-Simple {BIL,AGG} 0.960/11.08%/11.70%/-19.74%/0.561; ext BULL 0.920/9.49%/10.45%/-13.96%/0.680 vs HAA-Simple 0.946/10.14%/10.83%/-19.74%/0.514.

## 6. Section-8 sensitivity sweeps (INVVOL-3 weighting)

Every base row below uses the INVVOL-3 production config and equals the new headline. Tables show CPM-solo and 60/40 blend, clean + ext.

### 6.1 Selection-count K (INVVOL-3)

**CPM-solo:**

| variant | Clean Sharpe | Clean CAGR | Clean MaxDD | Clean Calmar | Ext Sharpe | Ext MaxDD | Ext Calmar |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2 | 0.736 | 9.50% | -22.26% | 0.427 | 0.845 | -22.26% | 0.517 |
| 3 | 0.934 | 11.38% | -13.23% | 0.860 | 1.026 | -16.16% | 0.783 |
| 4 (base) | 1.245 | 14.28% | -13.19% | 1.082 | 1.225 | -15.18% | 0.915 |
| 5 | 1.209 | 13.00% | -14.22% | 0.914 | 1.219 | -14.25% | 0.914 |
| 6 | 1.145 | 11.95% | -12.66% | 0.944 | 1.185 | -15.26% | 0.803 |

**60/40 blend:**

| variant | Clean Sharpe | Clean CAGR | Clean MaxDD | Clean Calmar | Ext Sharpe | Ext MaxDD | Ext Calmar |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2 | 0.948 | 10.45% | -14.26% | 0.733 | 0.987 | -14.26% | 0.765 |
| 3 | 1.088 | 11.54% | -11.65% | 0.991 | 1.107 | -11.65% | 0.991 |
| 4 (base) | 1.311 | 13.26% | -10.58% | 1.254 | 1.247 | -10.82% | 1.132 |
| 5 | 1.294 | 12.50% | -10.76% | 1.162 | 1.243 | -10.76% | 1.090 |
| 6 | 1.265 | 11.88% | -10.58% | 1.123 | 1.236 | -10.86% | 1.039 |

Note (vs pair-era 8.1): K=4 remains the joint clean+ext optimum on Sharpe AND Calmar under INVVOL-3 (blend clean 1.311/1.254 vs K=5 1.294/1.162, K=6 1.265/1.123); K=5 is a close shoulder, K=2/K=3 structurally weak (candidate starvation -> 3-subset selection degenerates). No ranking change; the K=4 pool is confirmed correct under inverse-vol weighting.

### 6.2 Screen 2x2 (K-cap x positive-trend, INVVOL-3)

**CPM-solo:**

| variant | Clean Sharpe | Clean CAGR | Clean MaxDD | Clean Calmar | Ext Sharpe | Ext MaxDD | Ext Calmar |
|---|---:|---:|---:|---:|---:|---:|---:|
| K-cap ON + positive-trend ON (base) | 1.245 | 14.28% | -13.19% | 1.082 | 1.225 | -15.18% | 0.915 |
| K-cap OFF + positive-trend ON | 1.036 | 10.30% | -13.97% | 0.737 | 1.114 | -15.26% | 0.713 |
| K-cap ON + positive-trend OFF | 1.279 | 14.33% | -13.69% | 1.047 | 1.235 | -15.18% | 0.905 |
| K-cap OFF + positive-trend OFF | 1.007 | 8.41% | -16.56% | 0.508 | 1.159 | -16.56% | 0.574 |

**60/40 blend:**

| variant | Clean Sharpe | Clean CAGR | Clean MaxDD | Clean Calmar | Ext Sharpe | Ext MaxDD | Ext Calmar |
|---|---:|---:|---:|---:|---:|---:|---:|
| K-cap ON + positive-trend ON (base) | 1.311 | 13.26% | -10.58% | 1.254 | 1.247 | -10.82% | 1.132 |
| K-cap OFF + positive-trend ON | 1.209 | 10.90% | -10.58% | 1.029 | 1.197 | -10.86% | 0.964 |
| K-cap ON + positive-trend OFF | 1.331 | 13.29% | -12.40% | 1.072 | 1.252 | -12.40% | 0.981 |
| K-cap OFF + positive-trend OFF | 1.267 | 9.77% | -12.83% | 0.761 | 1.273 | -12.83% | 0.752 |

Note (vs pair-era 8.2): same direction. Positive-trend screen is the main drawdown control (removing it deepens blend MaxDD to -12.40% and CPM-solo to -13.69%); removing the K-cap hurts CAGR and Calmar. Base (both ON) is the best blend Calmar in both windows. No ranking change.

### 6.3 Ranker (INVVOL-3)

**CPM-solo:**

| variant | Clean Sharpe | Clean CAGR | Clean MaxDD | Clean Calmar | Ext Sharpe | Ext MaxDD | Ext Calmar |
|---|---:|---:|---:|---:|---:|---:|---:|
| 10m-SMA-distance / rv_252d (base) | 1.245 | 14.28% | -13.19% | 1.082 | 1.225 | -15.18% | 0.915 |
| 13612U / rv_252d (positive-13612U screen) | 1.236 | 13.99% | -16.71% | 0.837 | 1.240 | -17.06% | 0.820 |
| plain 12-month momentum | 0.955 | 10.89% | -17.33% | 0.628 | 1.024 | -17.33% | 0.685 |

**60/40 blend:**

| variant | Clean Sharpe | Clean CAGR | Clean MaxDD | Clean Calmar | Ext Sharpe | Ext MaxDD | Ext Calmar |
|---|---:|---:|---:|---:|---:|---:|---:|
| 10m-SMA-distance / rv_252d (base) | 1.311 | 13.26% | -10.58% | 1.254 | 1.247 | -10.82% | 1.132 |
| 13612U / rv_252d (positive-13612U screen) | 1.301 | 13.09% | -14.13% | 0.926 | 1.253 | -14.13% | 0.871 |
| plain 12-month momentum | 1.133 | 11.26% | -14.05% | 0.801 | 1.126 | -14.05% | 0.788 |

Note (vs pair-era 8.3): base 10m-SMA ranker keeps best clean Calmar (blend 1.254) and shallowest MaxDD; under INVVOL-3 the 13612U/vol variant gains clean Sharpe (1.301) but deepens both windows' MaxDD (clean -14.13% vs -10.58%), so its pair-era clean-MaxDD parity does NOT survive INVVOL-3. Plain 12m remains clearly worst. No production-choice ranking change.

### 6.4 Canary (INVVOL-3)

**CPM-solo:**

| variant | Clean Sharpe | Clean CAGR | Clean MaxDD | Clean Calmar | Ext Sharpe | Ext MaxDD | Ext Calmar |
|---|---:|---:|---:|---:|---:|---:|---:|
| dual high-yield OR inflation-protected (base) | 1.245 | 14.28% | -13.19% | 1.082 | 1.225 | -15.18% | 0.915 |
| no canary | 1.085 | 13.36% | -21.86% | 0.611 | 1.119 | -22.65% | 0.591 |
| high-yield only | 1.333 | 14.81% | -12.09% | 1.225 | 1.330 | -15.18% | 0.969 |
| inflation-protected only | 1.204 | 12.93% | -12.66% | 1.022 | 1.155 | -14.25% | 0.833 |

**60/40 blend:**

| variant | Clean Sharpe | Clean CAGR | Clean MaxDD | Clean Calmar | Ext Sharpe | Ext MaxDD | Ext Calmar |
|---|---:|---:|---:|---:|---:|---:|---:|
| dual high-yield OR inflation-protected (base) | 1.311 | 13.26% | -10.58% | 1.254 | 1.247 | -10.82% | 1.132 |
| no canary | 1.218 | 12.75% | -12.94% | 0.986 | 1.188 | -14.21% | 0.842 |
| high-yield only | 1.355 | 13.56% | -10.58% | 1.282 | 1.302 | -10.82% | 1.176 |
| inflation-protected only | 1.306 | 12.47% | -10.58% | 1.179 | 1.218 | -10.58% | 1.045 |

Note (vs pair-era 8.6): same direction. Canary essential (dropping it blows blend MaxDD to -12.94%/-14.21% and CPM-solo to -21.86%/-22.65%); high-yield-only posts higher in-sample blend Sharpe/Calmar (1.355/1.282) than the dual gate, exactly as before; dual kept for governance. No ranking change.

### 6.5 Safe sleeve (INVVOL-3)

**CPM-solo:**

| variant | Clean Sharpe | Clean CAGR | Clean MaxDD | Clean Calmar | Ext Sharpe | Ext MaxDD | Ext Calmar |
|---|---:|---:|---:|---:|---:|---:|---:|
| timed SHV/IEF by 13612U (base) | 1.245 | 14.28% | -13.19% | 1.082 | 1.225 | -15.18% | 0.915 |
| SHV only | 1.175 | 13.14% | -22.32% | 0.589 | 1.174 | -23.10% | 0.566 |
| IEF only | 1.222 | 14.36% | -17.65% | 0.814 | 1.209 | -17.65% | 0.790 |
| static 50/50 SHV+IEF | 1.209 | 13.72% | -16.62% | 0.826 | 1.199 | -17.46% | 0.773 |

**60/40 blend:**

| variant | Clean Sharpe | Clean CAGR | Clean MaxDD | Clean Calmar | Ext Sharpe | Ext MaxDD | Ext Calmar |
|---|---:|---:|---:|---:|---:|---:|---:|
| timed SHV/IEF by 13612U (base) | 1.311 | 13.26% | -10.58% | 1.254 | 1.247 | -10.82% | 1.132 |
| SHV only | 1.274 | 12.59% | -11.05% | 1.140 | 1.219 | -12.35% | 0.953 |
| IEF only | 1.301 | 13.32% | -12.73% | 1.047 | 1.240 | -12.73% | 0.966 |
| static 50/50 SHV+IEF | 1.292 | 12.94% | -11.68% | 1.107 | 1.232 | -11.68% | 1.028 |

Note (vs pair-era 8.6 safe): timed SHV/IEF is best blend Calmar/MaxDD in both windows; every fixed rule is worse. Same direction, no ranking change.

## 7. Concentration -- per-asset contribution share of the 8 risky (INVVOL-3)

Share = sum of applied daily weight on the asset / sum of total risky daily weight, over the window (selection + inverse-vol driven). All 8 risky included; shares sum to 100%.

| Asset | Clean share | Ext share |
|---|---:|---:|
| SPHQ | 25.3% | 18.1% |
| GLD | 18.1% | 16.2% |
| QQQ | 14.5% | 11.2% |
| TLT | 13.3% | 17.4% |
| EFA | 11.9% | 12.6% |
| DBC | 8.4% | 9.0% |
| VNQ | 4.4% | 10.4% |
| EEM | 4.2% | 5.0% |
| **Total** | 100.0% | 100.0% |

Note (vs pair-era 8.9): INVVOL-3 spreads exposure more evenly than the 50/50 pair. SPHQ/GLD/QQQ still lead the clean window but at lower peaks (SPHQ 25.3% vs pair-era 28.1%); the floor lifts -- EEM rises to 4.2%/5.0% (was 0.4%/0.6%) and VNQ/TLT carry more, consistent with holding 3 names at inverse-vol weights rather than 2 equal-weight. Concentration is materially lower under INVVOL-3.

## 8. Cov-lookback sweep -- CPM-solo (INVVOL-3)

| Cov lookback | Clean Sharpe | Clean MaxDD | Clean Calmar | Ext Sharpe | Ext MaxDD | Ext Calmar |
|---|---:|---:|---:|---:|---:|---:|
| 126d | 1.167 | -13.97% | 0.951 | 1.222 | -13.97% | 0.972 |
| 252d | 1.214 | -13.92% | 0.994 | 1.226 | -14.92% | 0.916 |
| 504d (base) | 1.245 | -13.19% | 1.082 | 1.225 | -15.18% | 0.915 |
| 756d | 1.213 | -13.26% | 1.049 | 1.193 | -15.12% | 0.905 |
| 1008d | 1.199 | -12.98% | 1.061 | 1.205 | -15.62% | 0.894 |
| 1260d | 1.172 | -12.99% | 1.042 | 1.172 | -15.08% | 0.908 |

Verdict: 504d remains the INVVOL-3 clean-window Sharpe optimum (1.245) and sits at the top of a broad, graceful Calmar shelf (504d 1.082, 756d 1.049, 1008d 1.061), with no knife-edge; 126d/252d are weaker on Sharpe and 1260d declines gently. Combined with Section 6.1 (K=4 best on both Sharpe and Calmar), both the 504d cov lookback and the K=4 pool are confirmed still correct under INVVOL-3 weighting. No change to either choice vs the pair era.

## Caveats

- All post-cost (10 bps/side), T+1 MOO exact using real yfinance auto_adjust opens (/tmp/cpm_open_cache); CPM sleeve has no equity vol gate (gate only affects BULL/blend).
- Ext 27y is partially proxy-backed for the CPM trend universe (several ETFs lack real opens pre-2006 -> close-to-close fallback on ~80 rebal days); clean 18y has full real-open coverage and is the decisive lens.
- CPM-solo, concentration, and the cov/K/canary/safe sweeps drive INVVOL-3 selection from production primitives; ranker and screen-OFF variants use a generalized INVVOL-3 weight fn whose base config matches production exactly (anchor confirmed).
- BULL-solo and BULL-vs-HAA-Simple are independent of the CPM weighting and are unchanged from the pair-era memo; re-cited, not re-derived as new.
- Static 50/50 safe variant uses a synthetic daily-rebalanced SHV+IEF column (no opens -> rebal-day close-to-close fallback on the safe leg).
