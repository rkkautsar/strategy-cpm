# CPM final memo numbers -- DEFINITIVE set under IV4

Role: analyst (hypothesis-driven, read-only re production; no production files changed; no commit). Throwaway harness in `research/`.

All CPM-side numbers regenerated FRESH under the **FINAL production spec = IV4** (`cpm_live.compute_target_weights`): single-stage. Rank by vol-Faber (faber_score / rv_252d), take top-K=4, positive-trend screen (raw faber>0), then **INVERSE-VOL WEIGHT ALL surviving positives (NO min-var sub-selection)**, with **STRICT-4 PARTIAL-SAFE** fallback: risky_fraction = min(n_pos,4)/4, remainder to timed SHV/IEF safe (n_pos=0 -> 100% safe; n_pos=1 -> 1/4 risky + 3/4 safe; n_pos=2 -> 2/4 risky invvol-2 + 2/4 safe; n_pos=3 -> 3/4 risky invvol-3 + 1/4 safe; n_pos=4 -> 100% risky invvol-4). Canary HYG-OR-TIP (any positive).

> **SUPERSEDES `research/cpm_final_memo_numbers_findings.md`** (INVVOL-3 strict-3 min-var-3 sub-selection) and all earlier min-var-3-era memo runs, which are now STALE. Numbers that changed materially vs the min-var-3 set are flagged inline with **[CHANGED vs min-var-3]**.

**Convention (every table):** spec IV4; execution T+1 MOO exact (`mooex`, real auto_adjust opens); post-cost 10 bps/side; BULL equity vol gate slow rv_60d<rv_252d; blend = 0.60*CPM(IV4) + 0.40*BULL; cov lookback 504d; K=4. Clean window 2008-05-30..2026-05-22 (18y); extended 1999-03-10..2026-05-22 (27y). Martin = CAGR / UlcerIndex, UlcerIndex = sqrt(mean(dd_pct^2)).

Source harness: `research/cpm_iv4_final_numbers.py` (read-only; CPM-solo, concentration, partial-safe-A, and IV4-vs-min-var-3 use production `cpm_live.compute_target_weights`; Section-8 + rationale variants use a generalized IV4 weight fn whose base config reproduces production exactly).

## 0. Anchor gate

| Window | Sharpe | MaxDD | Calmar | Expected (IV4) | Match |
|---|---:|---:|---:|---|---|
| clean | 1.1910 | -12.67% | 1.0615 | 1.191/-12.67%/1.0615 | CONFIRMED |
| ext | 1.2161 | -15.93% | 0.8654 | 1.2161/-15.93%/0.8654 | CONFIRMED |

CPM-solo IV4 reproduces the FINAL research anchor exactly in both windows. Generalized weight-fn base config self-check: clean Sharpe 1.190980, matches production = True. The rest of this file is trusted on that basis.

## 1. Headline (IV4, T+1 MOO exact, 10 bps/side)

### 1.1 Clean window (18y)

| Series | Sharpe | CAGR | Vol | MaxDD | Calmar | Martin |
|---|---:|---:|---:|---:|---:|---:|
| CPM-solo (IV4) | 1.1910 | 13.44% | 11.16% | -12.67% | 1.0615 | 3.9646 |
| BULL-solo | 1.0813 | 11.44% | 10.57% | -13.35% | 0.8573 | 2.9220 |
| 60/40 blend | 1.2485 | 12.74% | 10.05% | -10.68% | 1.1928 | 4.3538 |

### 1.2 Extended window (27y)

| Series | Sharpe | CAGR | Vol | MaxDD | Calmar | Martin |
|---|---:|---:|---:|---:|---:|---:|
| CPM-solo (IV4) | 1.2161 | 13.78% | 11.13% | -15.93% | 0.8654 | 3.8409 |
| BULL-solo | 0.9196 | 9.49% | 10.45% | -13.96% | 0.6800 | 2.1945 |
| 60/40 blend | 1.2199 | 12.17% | 9.81% | -11.31% | 1.0761 | 4.0099 |

**KEY NEW HEADLINE -- 60/40 blend (CPM-IV4 + BULL):**
- Clean (18y): Sharpe 1.2485, CAGR 12.74%, Vol 10.05%, MaxDD -10.68%, Calmar 1.1928, Martin 4.3538.
- Ext (27y): Sharpe 1.2199, CAGR 12.17%, Vol 9.81%, MaxDD -11.31%, Calmar 1.0761, Martin 4.0099.

**[CHANGED vs min-var-3]** The min-var-3 strict-3 set is STALE. As expected, the IV4 blend clean Sharpe 1.2485 sits slightly below the prior min-var-3 strict-3 blend headline (1.3218) since IV4 CPM-solo clean Sharpe 1.1910 is ~0.08 below the min-var-3 strict-3 CPM Sharpe (1.2667). IV4 is the simpler, sub-selection-free production design; the trade is documented in Section 8. BULL-solo is unchanged (independent of CPM weighting). The old min-var-3-era CPM/blend numbers must not be reused.

## 2. Crisis windows (IV4; MaxDD and total return)

| Crisis window | Blend MaxDD | Blend return | CPM-solo MaxDD | CPM-solo return |
|---|---:|---:|---:|---:|
| Dot-com (2000-03..2002-12) | -5.61% | 23.45% | -6.03% | 28.44% |
| GFC (2007-10..2009-06) | -9.90% | 11.68% | -11.88% | 9.86% |
| COVID (2020-02..2020-06) | -10.68% | 3.22% | -10.06% | 8.00% |
| 2022 bear (2022-01..2022-12) | -3.86% | 0.12% | -6.33% | -0.50% |

MaxDD computed within each window (peak-to-trough inside the window), execution T+1 MOO exact, post-cost. Dot-com and GFC pre-2008 sit in the proxy-backed extended history.

## 3. Bootstrap CI (clean window, stationary block bootstrap B=2000, block=21, seed=42)


### 60/40 blend

| Metric | Point | 95% CI | CI width |
|---|---:|---|---:|
| Sharpe | 1.2485 | [0.8367, 1.6741] | 0.8374 |
| CAGR | 12.74% | [8.38%, 17.33%] | 8.95pp |
| MaxDD | -10.68% | [-23.43%, -9.74%] | 13.69pp |
| Calmar | 1.1928 | [0.4275, 1.6081] | 1.1806 |

### CPM-solo (IV4)

| Metric | Point | 95% CI | CI width |
|---|---:|---|---:|
| Sharpe | 1.1910 | [0.7866, 1.5969] | 0.8103 |
| CAGR | 13.44% | [8.57%, 18.48%] | 9.91pp |
| MaxDD | -12.67% | [-24.78%, -10.88%] | 13.90pp |
| Calmar | 1.0615 | [0.4103, 1.5647] | 1.1543 |

### BULL-solo

| Metric | Point | 95% CI | CI width |
|---|---:|---|---:|
| Sharpe | 1.0813 | [0.6352, 1.5533] | 0.9181 |
| CAGR | 11.44% | [6.57%, 16.87%] | 10.30pp |
| MaxDD | -13.35% | [-29.96%, -11.65%] | 18.31pp |
| Calmar | 0.8573 | [0.2507, 1.3023] | 1.0516 |

60/40 blend Sharpe 95% CI = [0.8367, 1.6741], width 0.8374 (clean window).

## 4. Rolling-window stability -- 60/40 blend (IV4)

| Window | Min | Median | Max | % < 1.0 | % < 0.7 | N |
|---|---:|---:|---:|---:|---:|---:|
| Clean 3y | 0.570 | 1.269 | 1.849 | 13.1% | 0.7% | 3768 |
| Clean 5y | 0.898 | 1.266 | 1.714 | 0.6% | 0.0% | 3266 |
| Ext 3y | 0.570 | 1.209 | 1.849 | 20.6% | 0.8% | 6091 |
| Ext 5y | 0.802 | 1.224 | 1.714 | 11.1% | 0.0% | 5588 |

Worst contiguous stretches (blend):

| Window | Length | Dates | Sharpe | CAGR | MaxDD |
|---|---|---|---:|---:|---:|
| clean | 1y | 2022-03-09..2023-03-09 | -1.015 | -2.51% | -5.14% |
| clean | 2y | 2021-10-29..2023-10-29 | -0.428 | -3.13% | -8.63% |
| clean | 3y | 2022-04-08..2025-04-07 | 0.589 | 4.73% | -8.63% |
| ext | 1y | 2022-03-09..2023-03-09 | -1.015 | -2.51% | -5.14% |
| ext | 2y | 2021-10-29..2023-10-29 | -0.428 | -3.13% | -8.63% |
| ext | 3y | 2022-04-08..2025-04-07 | 0.589 | 4.73% | -8.63% |

## 5. Benchmark -- CPM-solo (IV4) vs canonical AAA (no canary)

| Window | Series | Sharpe | CAGR | Vol | MaxDD | Calmar |
|---|---|---:|---:|---:|---:|---:|
| clean | CPM-solo IV4 | 1.1910 | 13.44% | 11.16% | -12.67% | 1.0615 |
| clean | Canonical AAA | 0.9695 | 11.48% | 12.00% | -20.65% | 0.5558 |
| ext | CPM-solo IV4 | 1.2161 | 13.78% | 11.13% | -15.93% | 0.8654 |
| ext | Canonical AAA | 1.0319 | 11.91% | 11.55% | -20.65% | 0.5767 |

| Window | dCAGR | dCalmar | dSharpe | dMaxDD | Info ratio | Return corr | Tracking err |
|---|---:|---:|---:|---:|---:|---:|---:|
| clean | +1.97pp | +0.5057 | +0.2214 | +7.98pp | +0.2256 | 0.8029 | 7.32% |
| ext | +1.88pp | +0.2887 | +0.1842 | +4.72pp | +0.2338 | 0.8150 | 6.91% |

BULL vs HAA-Simple is UNCHANGED by the IV4 weighting (BULL is independent of the CPM sleeve). Re-cited from the memo (unchanged): clean BULL 1.081/11.44%/10.57%/-13.35%/0.857 vs HAA-Simple {BIL,AGG} 0.960/11.08%/11.70%/-19.74%/0.561; ext BULL 0.920/9.49%/10.45%/-13.96%/0.680 vs HAA-Simple 0.946/10.14%/10.83%/-19.74%/0.514.

## 6. Section-8 sensitivity sweeps (IV4)

Every base row uses the IV4 production config and equals the new headline. Tables show CPM-solo and 60/40 blend, clean + ext.

### 6.1 Selection-count K (IV4 weight-all)

**CPM-solo:**

| variant | Clean Sharpe | Clean CAGR | Clean MaxDD | Clean Calmar | Ext Sharpe | Ext MaxDD | Ext Calmar |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2 | 0.8076 | 6.16% | -12.15% | 0.5069 | 0.9538 | -12.15% | 0.6186 |
| 3 | 0.9862 | 9.26% | -10.06% | 0.9202 | 1.0835 | -12.24% | 0.8436 |
| 4 (base) | 1.1910 | 13.44% | -12.67% | 1.0615 | 1.2161 | -15.93% | 0.8654 |
| 5 | 1.0753 | 11.61% | -13.10% | 0.8864 | 1.1355 | -15.68% | 0.7855 |
| 6 | 1.0205 | 10.74% | -11.85% | 0.9063 | 1.1047 | -16.34% | 0.7117 |

**60/40 blend:**

| variant | Clean Sharpe | Clean CAGR | Clean MaxDD | Clean Calmar | Ext Sharpe | Ext MaxDD | Ext Calmar |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2 | 1.0662 | 8.35% | -9.91% | 0.8424 | 1.0808 | -9.91% | 0.8492 |
| 3 | 1.1370 | 10.23% | -9.47% | 1.0803 | 1.1407 | -9.47% | 1.0674 |
| 4 (base) | 1.2485 | 12.74% | -10.68% | 1.1928 | 1.2199 | -11.31% | 1.0761 |
| 5 | 1.1677 | 11.64% | -11.59% | 1.0041 | 1.1580 | -11.59% | 0.9740 |
| 6 | 1.1310 | 11.11% | -12.10% | 0.9186 | 1.1369 | -12.10% | 0.8991 |

### 6.2 Screen 2x2 (K-cap x positive-trend, IV4)

**CPM-solo:**

| variant | Clean Sharpe | Clean CAGR | Clean MaxDD | Clean Calmar | Ext Sharpe | Ext MaxDD | Ext Calmar |
|---|---:|---:|---:|---:|---:|---:|---:|
| K-cap ON + positive-trend ON (base) | 1.1910 | 13.44% | -12.67% | 1.0615 | 1.2161 | -15.93% | 0.8654 |
| K-cap OFF + positive-trend ON | 0.9493 | 9.74% | -11.78% | 0.8272 | 1.0706 | -15.84% | 0.6891 |
| K-trend OFF | 1.1785 | 13.66% | -14.22% | 0.9606 | 1.1793 | -15.93% | 0.8533 |
| K-cap OFF + positive-trend OFF | 0.9555 | 10.00% | -21.33% | 0.4688 | 1.0332 | -21.33% | 0.4925 |

**60/40 blend:**

| variant | Clean Sharpe | Clean CAGR | Clean MaxDD | Clean Calmar | Ext Sharpe | Ext MaxDD | Ext Calmar |
|---|---:|---:|---:|---:|---:|---:|---:|
| K-cap ON + positive-trend ON (base) | 1.2485 | 12.74% | -10.68% | 1.1928 | 1.2199 | -11.31% | 1.0761 |
| K-cap OFF + positive-trend ON | 1.0882 | 10.51% | -12.27% | 0.8568 | 1.1148 | -12.27% | 0.8516 |
| K-trend OFF | 1.2571 | 12.89% | -13.26% | 0.9721 | 1.2101 | -13.26% | 0.9104 |
| K-cap OFF + positive-trend OFF | 1.1593 | 10.73% | -17.95% | 0.5975 | 1.1544 | -17.95% | 0.5712 |

### 6.3 Ranker (IV4)

**CPM-solo:**

| variant | Clean Sharpe | Clean CAGR | Clean MaxDD | Clean Calmar | Ext Sharpe | Ext MaxDD | Ext Calmar |
|---|---:|---:|---:|---:|---:|---:|---:|
| 10m-SMA-distance / rv_252d (base) | 1.1910 | 13.44% | -12.67% | 1.0615 | 1.2161 | -15.93% | 0.8654 |
| 13612U / rv_252d (positive-13612U screen) | 1.1725 | 13.37% | -12.67% | 1.0558 | 1.1877 | -18.86% | 0.7218 |
| plain 12-month momentum | 0.9916 | 11.43% | -16.37% | 0.6983 | 1.0607 | -17.98% | 0.7022 |

**60/40 blend:**

| variant | Clean Sharpe | Clean CAGR | Clean MaxDD | Clean Calmar | Ext Sharpe | Ext MaxDD | Ext Calmar |
|---|---:|---:|---:|---:|---:|---:|---:|
| 10m-SMA-distance / rv_252d (base) | 1.2485 | 12.74% | -10.68% | 1.1928 | 1.2199 | -11.31% | 1.0761 |
| 13612U / rv_252d (positive-13612U screen) | 1.2402 | 12.71% | -11.52% | 1.1031 | 1.2020 | -13.15% | 0.9179 |
| plain 12-month momentum | 1.1457 | 11.58% | -13.29% | 0.8715 | 1.1410 | -13.29% | 0.8671 |

### 6.4 Canary (IV4)

**CPM-solo:**

| variant | Clean Sharpe | Clean CAGR | Clean MaxDD | Clean Calmar | Ext Sharpe | Ext MaxDD | Ext Calmar |
|---|---:|---:|---:|---:|---:|---:|---:|
| dual high-yield OR inflation-protected (base) | 1.1910 | 13.44% | -12.67% | 1.0615 | 1.2161 | -15.93% | 0.8654 |
| no canary | 1.1278 | 13.11% | -15.01% | 0.8736 | 1.1742 | -15.93% | 0.8554 |
| high-yield only | 1.2087 | 13.51% | -12.67% | 1.0664 | 1.2603 | -15.93% | 0.8874 |
| inflation-protected only | 1.1546 | 12.16% | -12.67% | 0.9601 | 1.1582 | -13.38% | 0.8861 |

**60/40 blend:**

| variant | Clean Sharpe | Clean CAGR | Clean MaxDD | Clean Calmar | Ext Sharpe | Ext MaxDD | Ext Calmar |
|---|---:|---:|---:|---:|---:|---:|---:|
| dual high-yield OR inflation-protected (base) | 1.2485 | 12.74% | -10.68% | 1.1928 | 1.2199 | -11.31% | 1.0761 |
| no canary | 1.2158 | 12.56% | -10.68% | 1.1757 | 1.2000 | -11.31% | 1.0688 |
| high-yield only | 1.2528 | 12.77% | -10.68% | 1.1954 | 1.2387 | -11.31% | 1.0935 |
| inflation-protected only | 1.2457 | 11.99% | -10.68% | 1.1219 | 1.1988 | -10.68% | 1.0323 |

### 6.5 Safe sleeve (IV4)

**CPM-solo:**

| variant | Clean Sharpe | Clean CAGR | Clean MaxDD | Clean Calmar | Ext Sharpe | Ext MaxDD | Ext Calmar |
|---|---:|---:|---:|---:|---:|---:|---:|
| timed SHV/IEF by 13612U (base) | 1.1910 | 13.44% | -12.67% | 1.0615 | 1.2161 | -15.93% | 0.8654 |
| SHV only | 1.1431 | 12.48% | -13.73% | 0.9094 | 1.1852 | -15.93% | 0.8210 |
| IEF only | 1.1551 | 13.37% | -16.76% | 0.7980 | 1.1913 | -16.76% | 0.8204 |
| static 50/50 SHV+IEF | 1.1617 | 12.93% | -12.67% | 1.0206 | 1.1972 | -15.93% | 0.8419 |

**60/40 blend:**

| variant | Clean Sharpe | Clean CAGR | Clean MaxDD | Clean Calmar | Ext Sharpe | Ext MaxDD | Ext Calmar |
|---|---:|---:|---:|---:|---:|---:|---:|
| timed SHV/IEF by 13612U (base) | 1.2485 | 12.74% | -10.68% | 1.1928 | 1.2199 | -11.31% | 1.0761 |
| SHV only | 1.2297 | 12.18% | -10.42% | 1.1682 | 1.2088 | -11.31% | 1.0396 |
| IEF only | 1.2304 | 12.71% | -12.06% | 1.0541 | 1.2074 | -12.06% | 1.0081 |
| static 50/50 SHV+IEF | 1.2357 | 12.44% | -10.53% | 1.1818 | 1.2120 | -11.31% | 1.0568 |

### 6.6 Cov lookback (IV4)

**CPM-solo:**

| variant | Clean Sharpe | Clean CAGR | Clean MaxDD | Clean Calmar | Ext Sharpe | Ext MaxDD | Ext Calmar |
|---|---:|---:|---:|---:|---:|---:|---:|
| 126 | 1.1657 | 13.16% | -12.88% | 1.0219 | 1.2096 | -15.27% | 0.8903 |
| 252 | 1.1658 | 13.15% | -12.97% | 1.0137 | 1.1990 | -15.73% | 0.8560 |
| 504 (base) | 1.1910 | 13.44% | -12.67% | 1.0615 | 1.2161 | -15.93% | 0.8654 |
| 756 | 1.1930 | 13.48% | -11.94% | 1.1287 | 1.2024 | -15.93% | 0.8633 |
| 1008 | 1.1893 | 13.47% | -11.93% | 1.1293 | 1.2031 | -16.01% | 0.8622 |
| 1260 | 1.1909 | 13.50% | -11.62% | 1.1621 | 1.2044 | -15.98% | 0.8676 |

**60/40 blend:**

| variant | Clean Sharpe | Clean CAGR | Clean MaxDD | Clean Calmar | Ext Sharpe | Ext MaxDD | Ext Calmar |
|---|---:|---:|---:|---:|---:|---:|---:|
| 126 | 1.2286 | 12.57% | -11.71% | 1.0734 | 1.2145 | -11.71% | 1.0292 |
| 252 | 1.2338 | 12.57% | -11.56% | 1.0877 | 1.2116 | -11.56% | 1.0369 |
| 504 (base) | 1.2485 | 12.74% | -10.68% | 1.1928 | 1.2199 | -11.31% | 1.0761 |
| 756 | 1.2485 | 12.76% | -10.93% | 1.1682 | 1.2128 | -11.32% | 1.0733 |
| 1008 | 1.2461 | 12.76% | -11.26% | 1.1329 | 1.2140 | -11.41% | 1.0679 |
| 1260 | 1.2471 | 12.78% | -11.37% | 1.1232 | 1.2164 | -11.39% | 1.0730 |

## 7. Concentration -- per-asset contribution share of the 8 risky (IV4)

Share = sum of applied daily weight on the asset / sum of total risky daily weight over the window (inverse-vol weight on all top-4 positives + strict-4 risky-fraction driven). All 8 risky included; shares sum to 100%.

| Asset | Clean share | Ext share |
|---|---:|---:|
| SPHQ | 20.9% | 15.6% |
| QQQ | 16.9% | 13.6% |
| GLD | 15.0% | 13.8% |
| EFA | 11.7% | 12.3% |
| TLT | 10.5% | 13.9% |
| VNQ | 9.8% | 12.6% |
| EEM | 8.1% | 9.6% |
| DBC | 7.2% | 8.5% |
| **Total** | 100.0% | 100.0% |

## 8. Design-rationale supporting numbers (IV4)

For the memo's principled-choice section (NOT a scorecard). Each sub-axis holds the rest of the IV4 production design fixed; the base row reproduces the new headline.

### 8.1 Weighting: inverse-vol vs ERC vs continuous (equal-weight ref)

**CPM-solo:**

| weighting | Clean Sharpe | Clean Calmar | Clean Martin | Clean MaxDD | Ext Sharpe | Ext Calmar |
|---|---:|---:|---:|---:|---:|---:|
| inverse-vol (production) (base) | 1.1910 | 1.0615 | 3.9646 | -12.67% | 1.2161 | 0.8654 |
| ERC (equal-risk-contribution, SLSQP solver) | 1.1944 | 1.0602 | 3.9896 | -12.67% | 1.2184 | 0.8647 |
| equal-weight (continuous ref) | 1.1317 | 1.0147 | 3.7413 | -13.05% | 1.1868 | 0.8718 |

**Rationale:** inverse-vol 1.1910/3.9646 (Sharpe/Martin) is within noise of ERC 1.1944/3.9896 -- ERC adds a full-covariance SLSQP solver for no edge on the trend-filtered risk-similar menu (it degenerates toward the diagonal inverse-vol solution) -- and beats equal-weight 1.1317/3.7413. Choice: solver-free, robust inverse-vol.

### 8.2 Weight-all-4 (IV4) vs min-var-3 sub-selection (old strict-3)

Both share the vol-Faber ranker + top-4 + positive screen; they differ only in the risky block: IV4 inverse-vol weights ALL positives with strict-4 partial-safe, min-var-3 picks the min-variance 3-subset with strict-3 partial-safe.

| Window | IV4 Sharpe | IV4 Calmar | IV4 Martin | IV4 MaxDD | MV3 Sharpe | MV3 Calmar | MV3 Martin | MV3 MaxDD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| clean | 1.1910 | 1.0615 | 3.9646 | -12.67% | 1.2667 | 1.1306 | 3.9767 | -12.66% |
| ext | 1.2161 | 0.8654 | 3.8409 | -15.93% | 1.2349 | 0.9119 | 3.6946 | -15.18% |

| Crisis | IV4 MaxDD | MV3 MaxDD | IV4-MV3 MaxDD gap |
|---|---:|---:|---:|
| Dot-com (2000-03..2002-12) | -6.03% | -7.49% | +1.46pp |
| GFC (2007-10..2009-06) | -11.88% | -13.54% | +1.66pp |
| COVID (2020-02..2020-06) | -10.06% | -12.09% | +2.03pp |
| 2022 bear (2022-01..2022-12) | -6.33% | -6.23% | -0.10pp |

**Rationale:** min-var-3 had a slightly higher in-sample clean Sharpe (1.2667 vs IV4 1.1910) but the gap is within noise on Martin (3.9767 vs 3.9646) and the clean MaxDD is essentially DD-neutral (-12.66% vs -12.67%). IV4 drops a discrete combinatorial sub-selection stage (less overfit surface, simpler, no min-var solver) for a DD-neutral, within-noise cost. Choice: weight all positives, no sub-selection.

### 8.3 Ranker vol-adjustment is additive (vol-Faber vs plain 12m momentum)

| Window | vol-Faber Sharpe | plain-12m Sharpe | diff (vol-adj) | vol-Faber Calmar | plain-12m Calmar |
|---|---:|---:|---:|---:|---:|
| clean | 1.1910 | 0.9916 | +0.1994 | 1.0615 | 0.6983 |
| ext | 1.2161 | 1.0607 | +0.1553 | 0.8654 | 0.7022 |

Paired stationary-block bootstrap of the clean daily-return difference (vol-Faber minus plain-12m, B=2000, block=21, seed=42): Sharpe diff mean +0.2018, 95% CI [-0.0275, 0.4480], P(vol-Faber better) 95.2%, excludes-zero = False.

**Rationale:** the vol adjustment adds a large +0.1994 clean Sharpe point under IV4 (vs +0.1553 ext) with P(vol-Faber better) = 95.2% directionally; the paired-bootstrap 95% CI [-0.0275, 0.4480] just includes zero at the lower bound. **[CHANGED vs strict-3]** the prior strict-3 result was a smaller +0.110 clean Sharpe whose CI *excluded* zero; under IV4 the point effect is larger but the dispersion is wider so the CI lower bound dips just below zero -- still a strong, directionally consistent additive improvement (95.2% probability). Choice: vol-adjusted Faber ranker.

### 8.4 Strict-4 partial-safe (A, production) vs no-partial-safe (B)

(A) scales the risky block by min(n_pos,4)/4 and routes the remainder to timed safe; (B) holds qualifying positives fully invested, going to safe only at zero breadth. Both share the identical IV4 inverse-vol core; only the n_pos<4 branch differs.

| Window | (A) Sharpe | (A) MaxDD | (A) Calmar | (B) Sharpe | (B) MaxDD | (B) Calmar |
|---|---:|---:|---:|---:|---:|---:|
| clean | 1.1910 | -12.67% | 1.0615 | 1.1491 | -12.67% | 1.0614 |
| ext | 1.2161 | -15.93% | 0.8654 | 1.1878 | -15.93% | 0.8698 |

| Crisis | (A) MaxDD | (A) ret | (B) MaxDD | (B) ret | (A)-(B) MaxDD gap |
|---|---:|---:|---:|---:|---:|
| Dot-com (2000-03..2002-12) | -6.03% | 28.44% | -6.03% | 29.07% | -0.00pp |
| GFC (2007-10..2009-06) | -11.88% | 9.86% | -15.09% | 6.02% | +3.21pp |
| COVID (2020-02..2020-06) | -10.06% | 8.00% | -12.09% | 9.75% | +2.03pp |
| 2022 bear (2022-01..2022-12) | -6.33% | -0.50% | -9.24% | 0.84% | +2.91pp |

**Rationale:** 2022 bear CPM-solo MaxDD = **-6.33% (A strict-4 partial-safe)** vs **-9.24% (B no-partial-safe)** -- A is 2.91pp shallower in the 2022 low-breadth drawdown. Strict-4 partial-safe trades a sliver of upside for a materially shallower low-breadth drawdown. Choice: strict-4 partial-safe. (Positive (A)-(B) MaxDD gap = A shallower = more defensive.)

## Caveats

- All post-cost (10 bps/side), T+1 MOO exact using real yfinance auto_adjust opens; CPM sleeve has no equity vol gate (gate only affects BULL/blend).
- Ext 27y is partially proxy-backed for the CPM trend universe pre-2006 (close-to-close fallback on a minority of rebal days); clean 18y has full real-open coverage and is the decisive lens.
- CPM-solo, concentration, partial-safe-A, and IV4-vs-min-var-3 use production `cpm_live.compute_target_weights` (IV4) directly; Section-8 + rationale variants use a generalized IV4 weight fn whose base config matches production exactly (anchor + self-check confirmed).
- The min-var-3 comparison series (Section 8.2) is generated via the prior strict-3 harness (`cpm_final_memo_numbers.gcpm_wf`) for an apples-to-apples reference; it is the STALE design, shown only to justify the IV4 simplification.
- BULL-solo and BULL-vs-HAA-Simple are independent of the CPM weighting and are unchanged from the memo; re-cited, not re-derived.
- Static 50/50 safe variant uses a synthetic daily-rebalanced SHV+IEF column (no opens -> rebal-day close-to-close fallback on the safe leg).
- ERC uses a full-covariance SLSQP solver with inverse-vol fallback on failure; on the trend-filtered menu it degenerates toward the diagonal inverse-vol solution.
- Martin = CAGR / UlcerIndex with UlcerIndex = sqrt(mean(dd_pct^2)) over the window equity curve (from production perf_metrics).
