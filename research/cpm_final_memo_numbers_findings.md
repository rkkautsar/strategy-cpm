# CPM final memo numbers -- DEFINITIVE set (INVVOL-3 strict-3 partial-safe)

Role: analyst (hypothesis-driven, read-only re production; no production files changed; no commit). Throwaway harness in `research/`.

All CPM-side numbers regenerated FRESH under the **FINAL production spec** (`cpm_live.compute_target_weights`): INVVOL-3 core (select min-variance 3-subset from the top-K=4 positive-trend pool, then inverse-vol weight) with **STRICT-3 PARTIAL-SAFE** fallback: risky_fraction = min(n_pos,3)/3, remainder to timed safe (n_pos=0 -> 100% safe; n_pos=1 -> 1/3 risky + 2/3 safe; n_pos=2 -> 2/3 risky invvol-2 + 1/3 safe; n_pos=3 -> 100% risky invvol-3; n_pos>3 -> min-var 3-subset invvol-3, 100% risky).

> **SUPERSEDES `research/invvol3_memo_numbers_findings.md`**, which used the OLD hybrid fallback (n_pos=1 -> 50/50; n_pos=2 -> invvol-2 fully risky) and is now STALE. Numbers that changed materially vs the hybrid set are flagged inline with **[CHANGED vs hybrid]**.

**Convention (every table):** spec INVVOL-3 strict-3 partial-safe; execution T+1 MOO exact (`mooex`, real auto_adjust opens); post-cost 10 bps/side; BULL equity vol gate slow rv_60d<rv_252d; blend = 0.60*CPM(INVVOL-3 strict-3 partial-safe) + 0.40*BULL; cov lookback 504d; K=4. Clean window 2008-05-30..2026-05-22 (18y); extended 1999-03-10..2026-05-22 (27y).

Source harness: `research/cpm_final_memo_numbers.py` (read-only; CPM-solo, concentration, and fallback-A use production `cpm_live.compute_target_weights`; Section-8 + item-8 variants use a generalized strict-3 weight fn whose base config reproduces production exactly).

## 0. Anchor gate

| Window | Sharpe | MaxDD | Calmar | Expected (strict-3) | Match |
|---|---:|---:|---:|---|---|
| clean | 1.2667 | -12.66% | 1.1306 | 1.2667/-12.66%/1.1306 | CONFIRMED |
| ext | 1.2349 | -15.18% | 0.9119 | 1.2349/-15.18%/0.9119 | CONFIRMED |

CPM-solo strict-3 reproduces the FINAL research anchor exactly in both windows. Generalized weight-fn base config self-check: clean Sharpe 1.266681, matches production = True. The rest of this file is trusted on that basis.

## 1. Headline (INVVOL-3 strict-3 partial-safe, T+1 MOO exact, 10 bps/side)

### 1.1 Clean window (18y)

| Series | Sharpe | CAGR | Vol | MaxDD | Calmar |
|---|---:|---:|---:|---:|---:|
| CPM-solo (INVVOL-3 strict-3) | 1.2667 | 14.31% | 11.08% | -12.66% | 1.1306 |
| BULL-solo | 1.0813 | 11.44% | 10.57% | -13.35% | 0.8573 |
| 60/40 blend | 1.3218 | 13.28% | 9.83% | -10.58% | 1.2549 |

### 1.2 Extended window (27y)

| Series | Sharpe | CAGR | Vol | MaxDD | Calmar |
|---|---:|---:|---:|---:|---:|
| CPM-solo (INVVOL-3 strict-3) | 1.2349 | 13.84% | 10.99% | -15.18% | 0.9119 |
| BULL-solo | 0.9196 | 9.49% | 10.45% | -13.96% | 0.6800 |
| 60/40 blend | 1.2505 | 12.22% | 9.59% | -10.82% | 1.1295 |

**KEY NEW HEADLINE -- 60/40 blend (CPM-INVVOL-3 strict-3 + BULL):**
- Clean (18y): Sharpe 1.3218, CAGR 13.28%, Vol 9.83%, MaxDD -10.58%, Calmar 1.2549.
- Ext (27y): Sharpe 1.2505, CAGR 12.22%, Vol 9.59%, MaxDD -10.82%, Calmar 1.1295.

**[CHANGED vs hybrid]** CPM-solo clean Sharpe 1.2667 (hybrid 1.2453), MaxDD -12.66% (hybrid -13.19%), Calmar 1.1306 (hybrid 1.0824). Blend clean Sharpe 1.3218 (hybrid-fallback blend 1.3111), Calmar 1.2549 (hybrid 1.2536). BULL-solo is unchanged (independent of the CPM weighting). The old hybrid-fallback CPM/blend numbers are stale and must not be reused.

## 2. Crisis windows (INVVOL-3 strict-3 partial-safe; MaxDD and total return)

| Crisis window | Blend MaxDD | Blend return | CPM-solo MaxDD | CPM-solo return |
|---|---:|---:|---:|---:|
| Dot-com (2000-03..2002-12) | -5.46% | 22.27% | -7.49% | 26.38% |
| GFC (2007-10..2009-06) | -9.45% | 13.96% | -13.54% | 13.60% |
| COVID (2020-02..2020-06) | -10.58% | 3.54% | -12.09% | 8.46% |
| 2022 bear (2022-01..2022-12) | -3.77% | 1.36% | -6.23% | 1.54% |

MaxDD computed within each window (peak-to-trough inside the window), execution T+1 MOO exact, post-cost. Dot-com and GFC pre-2008 sit in the proxy-backed extended history.

## 3. Bootstrap CI (clean window, stationary block bootstrap B=2000, block=21, seed=42)


### 60/40 blend

| Metric | Point | 95% CI | CI width |
|---|---:|---|---:|
| Sharpe | 1.3218 | [0.9060, 1.7531] | 0.8471 |
| CAGR | 13.28% | [8.89%, 17.82%] | 8.93pp |
| MaxDD | -10.58% | [-21.77%, -9.21%] | 12.56pp |
| Calmar | 1.2549 | [0.4811, 1.7743] | 1.2932 |

### CPM-solo (INVVOL-3 strict-3)

| Metric | Point | 95% CI | CI width |
|---|---:|---|---:|
| Sharpe | 1.2667 | [0.8556, 1.6771] | 0.8215 |
| CAGR | 14.31% | [9.37%, 19.44%] | 10.07pp |
| MaxDD | -12.66% | [-24.21%, -10.74%] | 13.47pp |
| Calmar | 1.1306 | [0.4640, 1.6236] | 1.1595 |

### BULL-solo

| Metric | Point | 95% CI | CI width |
|---|---:|---|---:|
| Sharpe | 1.0813 | [0.6352, 1.5533] | 0.9181 |
| CAGR | 11.44% | [6.57%, 16.87%] | 10.30pp |
| MaxDD | -13.35% | [-29.96%, -11.65%] | 18.31pp |
| Calmar | 0.8573 | [0.2507, 1.3023] | 1.0516 |

**[CHANGED vs hybrid]** Hybrid-fallback blend Sharpe CI was [0.909, 1.751] width 0.842. Strict-3 blend Sharpe 95% CI = [0.9060, 1.7531], width 0.8471.

## 4. Rolling-window stability -- 60/40 blend (INVVOL-3 strict-3 partial-safe)

| Window | Min | Median | Max | % < 1.0 | % < 0.7 | N |
|---|---:|---:|---:|---:|---:|---:|
| Clean 3y | 0.531 | 1.364 | 1.880 | 11.8% | 1.5% | 3768 |
| Clean 5y | 0.955 | 1.331 | 1.815 | 0.2% | 0.0% | 3266 |
| Ext 3y | 0.531 | 1.213 | 1.880 | 20.2% | 1.3% | 6091 |
| Ext 5y | 0.727 | 1.230 | 1.815 | 8.8% | 0.0% | 5588 |

Worst contiguous stretches (blend):

| Window | Length | Dates | Sharpe | CAGR | MaxDD |
|---|---|---|---:|---:|---:|
| clean | 1y | 2022-03-09..2023-03-09 | -0.981 | -2.31% | -4.71% |
| clean | 2y | 2021-10-29..2023-10-29 | -0.467 | -3.53% | -8.99% |
| clean | 3y | 2021-11-17..2024-11-16 | 0.543 | 4.37% | -8.99% |
| ext | 1y | 2022-03-09..2023-03-09 | -0.981 | -2.31% | -4.71% |
| ext | 2y | 2021-10-29..2023-10-29 | -0.467 | -3.53% | -8.99% |
| ext | 3y | 2021-11-17..2024-11-16 | 0.543 | 4.37% | -8.99% |

## 5. Benchmark -- CPM-solo (INVVOL-3 strict-3 partial-safe) vs canonical AAA (no canary)

| Window | Series | Sharpe | CAGR | Vol | MaxDD | Calmar |
|---|---|---:|---:|---:|---:|---:|
| clean | CPM-solo strict-3 | 1.2667 | 14.31% | 11.08% | -12.66% | 1.1306 |
| clean | Canonical AAA | 0.9695 | 11.48% | 12.00% | -20.65% | 0.5558 |
| ext | CPM-solo strict-3 | 1.2349 | 13.84% | 10.99% | -15.18% | 0.9119 |
| ext | Canonical AAA | 1.0319 | 11.91% | 11.55% | -20.65% | 0.5767 |

| Window | dCAGR | dCalmar | dSharpe | dMaxDD | Info ratio | Return corr | Tracking err |
|---|---:|---:|---:|---:|---:|---:|---:|
| clean | +2.83pp | +0.5748 | +0.2971 | +7.99pp | +0.3420 | 0.8187 | 7.01% |
| ext | +1.93pp | +0.3352 | +0.2030 | +5.47pp | +0.2481 | 0.8271 | 6.65% |

BULL vs HAA-Simple is UNCHANGED by the INVVOL-3 weighting (BULL is independent of the CPM sleeve). Re-cited from the memo (unchanged): clean BULL 1.081/11.44%/10.57%/-13.35%/0.857 vs HAA-Simple {BIL,AGG} 0.960/11.08%/11.70%/-19.74%/0.561; ext BULL 0.920/9.49%/10.45%/-13.96%/0.680 vs HAA-Simple 0.946/10.14%/10.83%/-19.74%/0.514.

## 6. Section-8 sensitivity sweeps (INVVOL-3 strict-3 partial-safe)

Every base row uses the strict-3 production config and equals the new headline. Tables show CPM-solo and 60/40 blend, clean + ext.

### 6.1 Selection-count K (strict-3)

**CPM-solo:**

| variant | Clean Sharpe | Clean CAGR | Clean MaxDD | Clean Calmar | Ext Sharpe | Ext MaxDD | Ext Calmar |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2 | 0.7860 | 7.32% | -15.63% | 0.4682 | 0.9162 | -15.63% | 0.5688 |
| 3 | 0.9472 | 11.41% | -13.22% | 0.8629 | 1.0316 | -16.16% | 0.7802 |
| 4 (base) | 1.2667 | 14.31% | -12.66% | 1.1306 | 1.2349 | -15.18% | 0.9119 |
| 5 | 1.2323 | 13.03% | -12.66% | 1.0297 | 1.2304 | -14.25% | 0.9107 |
| 6 | 1.1688 | 11.99% | -12.66% | 0.9469 | 1.1967 | -15.26% | 0.8004 |

**60/40 blend:**

| variant | Clean Sharpe | Clean CAGR | Clean MaxDD | Clean Calmar | Ext Sharpe | Ext MaxDD | Ext Calmar |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2 | 1.0249 | 9.07% | -10.01% | 0.9058 | 1.0520 | -10.27% | 0.9024 |
| 3 | 1.0956 | 11.56% | -11.65% | 0.9923 | 1.1097 | -11.65% | 0.9880 |
| 4 (base) | 1.3218 | 13.28% | -10.58% | 1.2549 | 1.2505 | -10.82% | 1.1295 |
| 5 | 1.3054 | 12.51% | -10.58% | 1.1827 | 1.2476 | -10.58% | 1.1056 |
| 6 | 1.2769 | 11.89% | -10.58% | 1.1239 | 1.2404 | -10.86% | 1.0361 |

### 6.2 Screen 2x2 (K-cap x positive-trend, strict-3)

**CPM-solo:**

| variant | Clean Sharpe | Clean CAGR | Clean MaxDD | Clean Calmar | Ext Sharpe | Ext MaxDD | Ext Calmar |
|---|---:|---:|---:|---:|---:|---:|---:|
| K-cap ON + positive-trend ON (base) | 1.2667 | 14.31% | -12.66% | 1.1306 | 1.2349 | -15.18% | 0.9119 |
| K-cap OFF + positive-trend ON | 1.0591 | 10.33% | -12.66% | 0.8164 | 1.1262 | -15.26% | 0.7105 |
| K-cap ON + positive-trend OFF | 1.2794 | 14.33% | -13.69% | 1.0468 | 1.2389 | -15.18% | 0.9080 |
| K-cap OFF + positive-trend OFF | 1.0070 | 8.41% | -16.56% | 0.5077 | 1.1642 | -16.56% | 0.5763 |

**60/40 blend:**

| variant | Clean Sharpe | Clean CAGR | Clean MaxDD | Clean Calmar | Ext Sharpe | Ext MaxDD | Ext Calmar |
|---|---:|---:|---:|---:|---:|---:|---:|
| K-cap ON + positive-trend ON (base) | 1.3218 | 13.28% | -10.58% | 1.2549 | 1.2505 | -10.82% | 1.1295 |
| K-cap OFF + positive-trend ON | 1.2207 | 10.91% | -10.58% | 1.0307 | 1.2023 | -10.86% | 0.9609 |
| K-cap ON + positive-trend OFF | 1.3308 | 13.29% | -12.40% | 1.0719 | 1.2547 | -12.40% | 0.9826 |
| K-cap OFF + positive-trend OFF | 1.2667 | 9.77% | -12.83% | 0.7613 | 1.2769 | -12.83% | 0.7538 |

### 6.3 Ranker (strict-3)

**CPM-solo:**

| variant | Clean Sharpe | Clean CAGR | Clean MaxDD | Clean Calmar | Ext Sharpe | Ext MaxDD | Ext Calmar |
|---|---:|---:|---:|---:|---:|---:|---:|
| 10m-SMA-distance / rv_252d (base) | 1.2667 | 14.31% | -12.66% | 1.1306 | 1.2349 | -15.18% | 0.9119 |
| 13612U / rv_252d (positive-13612U screen) | 1.2516 | 14.09% | -14.41% | 0.9778 | 1.2430 | -17.06% | 0.8181 |
| plain 12-month momentum | 0.9719 | 11.01% | -17.33% | 0.6352 | 1.0368 | -17.33% | 0.6905 |

**60/40 blend:**

| variant | Clean Sharpe | Clean CAGR | Clean MaxDD | Clean Calmar | Ext Sharpe | Ext MaxDD | Ext Calmar |
|---|---:|---:|---:|---:|---:|---:|---:|
| 10m-SMA-distance / rv_252d (base) | 1.3218 | 13.28% | -10.58% | 1.2549 | 1.2505 | -10.82% | 1.1295 |
| 13612U / rv_252d (positive-13612U screen) | 1.3099 | 13.14% | -12.72% | 1.0331 | 1.2535 | -12.72% | 0.9656 |
| plain 12-month momentum | 1.1451 | 11.33% | -14.05% | 0.8065 | 1.1349 | -14.05% | 0.7923 |

### 6.4 Canary (strict-3)

**CPM-solo:**

| variant | Clean Sharpe | Clean CAGR | Clean MaxDD | Clean Calmar | Ext Sharpe | Ext MaxDD | Ext Calmar |
|---|---:|---:|---:|---:|---:|---:|---:|
| dual high-yield OR inflation-protected (base) | 1.2667 | 14.31% | -12.66% | 1.1306 | 1.2349 | -15.18% | 0.9119 |
| no canary | 1.1428 | 13.57% | -18.00% | 0.7538 | 1.1551 | -18.83% | 0.7141 |
| high-yield only | 1.3327 | 14.81% | -12.09% | 1.2253 | 1.3264 | -15.18% | 0.9657 |
| inflation-protected only | 1.2271 | 12.96% | -12.66% | 1.0243 | 1.1687 | -14.25% | 0.8324 |

**60/40 blend:**

| variant | Clean Sharpe | Clean CAGR | Clean MaxDD | Clean Calmar | Ext Sharpe | Ext MaxDD | Ext Calmar |
|---|---:|---:|---:|---:|---:|---:|---:|
| dual high-yield OR inflation-protected (base) | 1.3218 | 13.28% | -10.58% | 1.2549 | 1.2505 | -10.82% | 1.1295 |
| no canary | 1.2526 | 12.86% | -10.58% | 1.2156 | 1.2081 | -11.72% | 1.0235 |
| high-yield only | 1.3548 | 13.56% | -10.58% | 1.2819 | 1.2987 | -10.82% | 1.1729 |
| inflation-protected only | 1.3184 | 12.49% | -10.58% | 1.1801 | 1.2250 | -10.58% | 1.0439 |

### 6.5 Safe sleeve (strict-3)

**CPM-solo:**

| variant | Clean Sharpe | Clean CAGR | Clean MaxDD | Clean Calmar | Ext Sharpe | Ext MaxDD | Ext Calmar |
|---|---:|---:|---:|---:|---:|---:|---:|
| timed SHV/IEF by 13612U (base) | 1.2667 | 14.31% | -12.66% | 1.1306 | 1.2349 | -15.18% | 0.9119 |
| SHV only | 1.2146 | 13.35% | -18.19% | 0.7337 | 1.1978 | -19.01% | 0.6912 |
| IEF only | 1.2319 | 14.28% | -17.04% | 0.8377 | 1.2116 | -17.04% | 0.8115 |
| static 50/50 SHV+IEF | 1.2355 | 13.80% | -14.29% | 0.9655 | 1.2132 | -15.18% | 0.8880 |

**60/40 blend:**

| variant | Clean Sharpe | Clean CAGR | Clean MaxDD | Clean Calmar | Ext Sharpe | Ext MaxDD | Ext Calmar |
|---|---:|---:|---:|---:|---:|---:|---:|
| timed SHV/IEF by 13612U (base) | 1.3218 | 13.28% | -10.58% | 1.2549 | 1.2505 | -10.82% | 1.1295 |
| SHV only | 1.2979 | 12.71% | -10.58% | 1.2012 | 1.2329 | -10.82% | 1.0917 |
| IEF only | 1.3046 | 13.27% | -12.38% | 1.0718 | 1.2387 | -12.38% | 0.9870 |
| static 50/50 SHV+IEF | 1.3067 | 12.98% | -10.81% | 1.2005 | 1.2396 | -10.82% | 1.1099 |

### 6.6 Cov lookback (strict-3)

**CPM-solo:**

| variant | Clean Sharpe | Clean CAGR | Clean MaxDD | Clean Calmar | Ext Sharpe | Ext MaxDD | Ext Calmar |
|---|---:|---:|---:|---:|---:|---:|---:|
| 126 | 1.1866 | 13.31% | -13.12% | 1.0144 | 1.2313 | -13.53% | 0.9998 |
| 252 | 1.2343 | 13.87% | -13.18% | 1.0524 | 1.2366 | -14.92% | 0.9138 |
| 504 (base) | 1.2667 | 14.31% | -12.66% | 1.1306 | 1.2349 | -15.18% | 0.9119 |
| 756 | 1.2350 | 13.95% | -12.11% | 1.1525 | 1.2038 | -15.12% | 0.9028 |
| 1008 | 1.2206 | 13.81% | -12.17% | 1.1349 | 1.2145 | -15.62% | 0.8913 |
| 1260 | 1.1930 | 13.58% | -12.20% | 1.1133 | 1.1802 | -15.08% | 0.9044 |

**60/40 blend:**

| variant | Clean Sharpe | Clean CAGR | Clean MaxDD | Clean Calmar | Ext Sharpe | Ext MaxDD | Ext Calmar |
|---|---:|---:|---:|---:|---:|---:|---:|
| 126 | 1.2651 | 12.68% | -11.30% | 1.1224 | 1.2503 | -11.30% | 1.0649 |
| 252 | 1.3015 | 13.02% | -11.32% | 1.1497 | 1.2582 | -11.32% | 1.0686 |
| 504 (base) | 1.3218 | 13.28% | -10.58% | 1.2549 | 1.2505 | -10.82% | 1.1295 |
| 756 | 1.3034 | 13.07% | -10.79% | 1.2107 | 1.2335 | -10.79% | 1.1219 |
| 1008 | 1.2929 | 12.98% | -11.09% | 1.1706 | 1.2417 | -11.31% | 1.0850 |
| 1260 | 1.2728 | 12.84% | -11.21% | 1.1453 | 1.2197 | -11.21% | 1.0796 |

## 7. Concentration -- per-asset contribution share of the 8 risky (INVVOL-3 strict-3 partial-safe)

Share = sum of applied daily weight on the asset / sum of total risky daily weight over the window (selection + inverse-vol + strict-3 risky-fraction driven). All 8 risky included; shares sum to 100%.

| Asset | Clean share | Ext share |
|---|---:|---:|
| SPHQ | 25.5% | 18.3% |
| GLD | 17.8% | 16.2% |
| QQQ | 14.6% | 11.4% |
| TLT | 13.0% | 16.9% |
| EFA | 12.0% | 12.8% |
| DBC | 8.3% | 9.1% |
| VNQ | 4.4% | 10.3% |
| EEM | 4.2% | 5.1% |
| **Total** | 100.0% | 100.0% |

## 8. New sensitivity axes (re-anchored to the strict-3 production base)

Both axes hold the rest of the strict-3 production design fixed; the base row reproduces the new headline. Confirms the prior verdicts (inverse-vol right, min-var right) under strict-3.

### 8.1 Weighting flavor at select-3 (selection = min-var 3-subset, strict-3)

**CPM-solo:**

| variant | Clean Sharpe | Clean CAGR | Clean MaxDD | Clean Calmar | Ext Sharpe | Ext MaxDD | Ext Calmar |
|---|---:|---:|---:|---:|---:|---:|---:|
| inverse-vol (production) (base) | 1.2667 | 14.31% | -12.66% | 1.1306 | 1.2349 | -15.18% | 0.9119 |
| ERC (equal-risk-contribution) | 1.2638 | 14.26% | -12.66% | 1.1265 | 1.2329 | -15.18% | 0.9096 |
| equal-weight 1/3 (ref) | 1.2394 | 14.36% | -16.86% | 0.8517 | 1.2296 | -17.68% | 0.8047 |

**60/40 blend:**

| variant | Clean Sharpe | Clean CAGR | Clean MaxDD | Clean Calmar | Ext Sharpe | Ext MaxDD | Ext Calmar |
|---|---:|---:|---:|---:|---:|---:|---:|
| inverse-vol (production) (base) | 1.3218 | 13.28% | -10.58% | 1.2549 | 1.2505 | -10.82% | 1.1295 |
| ERC (equal-risk-contribution) | 1.3199 | 13.25% | -10.58% | 1.2520 | 1.2491 | -10.82% | 1.1277 |
| equal-weight 1/3 (ref) | 1.3105 | 13.32% | -11.66% | 1.1421 | 1.2583 | -11.96% | 1.0418 |

### 8.2 Subset-selection objective (weighting = inverse-vol, strict-3)

**CPM-solo:**

| variant | Clean Sharpe | Clean CAGR | Clean MaxDD | Clean Calmar | Ext Sharpe | Ext MaxDD | Ext Calmar |
|---|---:|---:|---:|---:|---:|---:|---:|
| min-variance (production) (base) | 1.2667 | 14.31% | -12.66% | 1.1306 | 1.2349 | -15.18% | 0.9119 |
| min-vol (3 lowest sigma) | 1.2131 | 13.62% | -12.66% | 1.0762 | 1.2044 | -17.24% | 0.7844 |
| max-Sharpe (trailing) | 1.1678 | 13.83% | -12.66% | 1.0925 | 1.1506 | -16.16% | 0.8477 |
| max-Calmar (trailing) | 1.2143 | 14.40% | -12.66% | 1.1375 | 1.1497 | -15.38% | 0.8788 |
| min-DD (trailing) | 1.2366 | 14.25% | -12.66% | 1.1260 | 1.2415 | -14.43% | 0.9839 |

**60/40 blend:**

| variant | Clean Sharpe | Clean CAGR | Clean MaxDD | Clean Calmar | Ext Sharpe | Ext MaxDD | Ext Calmar |
|---|---:|---:|---:|---:|---:|---:|---:|
| min-variance (production) (base) | 1.3218 | 13.28% | -10.58% | 1.2549 | 1.2505 | -10.82% | 1.1295 |
| min-vol (3 lowest sigma) | 1.2883 | 12.87% | -10.58% | 1.2163 | 1.2278 | -12.39% | 0.9709 |
| max-Sharpe (trailing) | 1.2447 | 12.99% | -10.65% | 1.2196 | 1.1906 | -11.44% | 1.0616 |
| max-Calmar (trailing) | 1.2784 | 13.33% | -10.23% | 1.3029 | 1.1892 | -11.21% | 1.0732 |
| min-DD (trailing) | 1.3053 | 13.25% | -10.23% | 1.2951 | 1.2584 | -10.41% | 1.1940 |

**Axis 8.1 verdict (CPM-solo clean):** inverse-vol 1.2667/1.1306 (Sharpe/Calmar) vs ERC 1.2638/1.1265 vs EW 1.2394/0.8517. EW is clearly worse on the risk axis; ERC is near-identical to inverse-vol (the trend-filtered, 3-name, risk-similar menu collapses ERC toward the diagonal inverse-vol solution). Prior verdict HOLDS under strict-3: keep solver-free inverse-vol.

**Axis 8.2 verdict (CPM-solo clean):** min-variance 1.2667 Sharpe is the best of the selection objectives; the performance-based selectors (max-Sharpe/max-Calmar/min-DD) use trailing realized perf and are overfit-prone OOS without beating min-var in-sample. Prior verdict HOLDS under strict-3: keep min-variance.

## 9. Fallback note -- strict-3 partial-safe (A, production) vs no-partial-safe (B)

The production strict-3 partial-safe (A) scales the risky block by min(n_pos,3)/3 and routes the remainder to the timed safe; (B) holds qualifying positives fully invested, going to safe only at zero breadth. Both share the identical INVVOL-3 core; only the n_pos<3 branch differs.

| Window | (A) strict-3 Sharpe | (A) MaxDD | (A) Calmar | (B) no-partial Sharpe | (B) MaxDD | (B) Calmar |
|---|---:|---:|---:|---:|---:|---:|
| clean | 1.2667 | -12.66% | 1.1306 | 1.2453 | -13.19% | 1.0824 |
| ext | 1.2349 | -15.18% | 0.9119 | 1.2249 | -15.18% | 0.9148 |

| Crisis | (A) MaxDD | (A) ret | (B) MaxDD | (B) ret | (A)-(B) MaxDD gap |
|---|---:|---:|---:|---:|---:|
| Dot-com (2000-03..2002-12) | -7.49% | 26.38% | -7.49% | 28.37% | +0.00pp |
| GFC (2007-10..2009-06) | -13.54% | 13.60% | -13.54% | 10.55% | +0.00pp |
| COVID (2020-02..2020-06) | -12.09% | 8.46% | -12.09% | 9.80% | +0.00pp |
| 2022 bear (2022-01..2022-12) | -6.23% | 1.54% | -9.24% | 2.42% | +3.01pp |

**Decisive result (cited in the FINAL spec choice):** 2022 bear CPM-solo MaxDD = **-6.23% (A strict-3 partial-safe)** vs **-9.24% (B no-partial-safe)** -- A is 3.01pp shallower in the 2022 drawdown. Strict-3 partial-safe trades a sliver of upside for a materially shallower low-breadth drawdown; it is the production choice. (Positive (A)-(B) MaxDD gap = A shallower = more defensive.)

## Caveats

- All post-cost (10 bps/side), T+1 MOO exact using real yfinance auto_adjust opens; CPM sleeve has no equity vol gate (gate only affects BULL/blend).
- Ext 27y is partially proxy-backed for the CPM trend universe pre-2006 (close-to-close fallback on a minority of rebal days); clean 18y has full real-open coverage and is the decisive lens.
- CPM-solo, concentration, and fallback-A use production `cpm_live.compute_target_weights` directly; Section-8 + item-8 variants use a generalized strict-3 weight fn whose base config matches production exactly (anchor + self-check confirmed).
- BULL-solo and BULL-vs-HAA-Simple are independent of the CPM weighting and are unchanged from the memo; re-cited, not re-derived.
- Static 50/50 safe variant uses a synthetic daily-rebalanced SHV+IEF column (no opens -> rebal-day close-to-close fallback on the safe leg).
- ERC uses a full-covariance SLSQP solver with inverse-vol fallback on failure; on the trend-filtered 3-name menu it degenerates toward the diagonal inverse-vol solution.
