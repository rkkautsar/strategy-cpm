# NDX-sleeve vol-gate variants: does NDX prefer a different gate than BULL's symmetric RV60<RV252?

Role: analyst (hypothesis-driven, read-only re production; writes only to research/; no production/memo files changed; no commit). EXPLORATION ONLY -- a POTENTIAL NDX-sleeve improvement; user decides adoption later. Harness `research/ndx_volgate_variants.py`.

**Motivation.** The NDX sleeve fires its top-K Nasdaq-100 momentum basket only when the BULL sleeve is risk-on = canary(TIP 13612U>0) AND trend(SPY 13612U>0) AND vol(RV60<RV252 on SPY). So the NDX vol gate is INHERITED from BULL and computed on SPY realized vol (symmetric RV60<RV252 = V0). On BULL, 4-5 variant rounds all kept symmetric RV60<RV252. NDX is higher-beta / more tech-concentrated, so its optimal gate MIGHT differ (faster window, QQQ-based realized gate, or VXN). This redoes the variant search on the NDX sleeve.

**Only the vol-gate layer changes.** Canary (TIP), trend (SPY), NDX selection (top-K=5 raw 13612U, partial-fill to best-of-safe), delisting haircut and T+1 MOO execution are held at production values, so the vol gate is the single differentiator.

**Convention.** T+1 MOO (next-day open), 10 bps/side, monthly month-end signal. Window 2007-02-28..2026-05-22 (231 monthly signals). NDX standalone sleeve (the lens where the gate matters most; at 20% blend weight, effects scale ~1/5). VXN data 2001-01-23..2026-05-29 (yfinance ^VXN).

**Caveat up front:** pre-2017 NDX backtest has ~28% survivorship bias (missing delisted tickers); post-2020 PIT coverage is clean. Single in-sample run; any winner needs bootstrap-CI / walk-forward before adoption.

## 0. Anchor

NDX V0 standalone: Sharpe **1.1812** / MaxDD **-35.92%** / Calmar **0.7602** / Martin **2.9753** vs expected {'sharpe': 1.1812, 'maxdd': -0.3592, 'calmar': 0.7602, 'martin': 2.9753} -> **CONFIRMED**.

## 1. Standalone NDX sleeve metrics (full window)

| Variant | CAGR | Vol | Sharpe | MaxDD | Calmar | Martin | active mo |
|---|---:|---:|---:|---:|---:|---:|---:|
| V0 RV60<RV252 SPY (PROD) | 27.31% | 22.64% | 1.1812 | -35.92% | 0.7602 | 2.9753 | 110 |
| RV20<RV252 SPY (faster) | 30.12% | 22.90% | 1.2658 | -31.39% | 0.9595 | 4.1796 | 111 |
| RV63<RV126 SPY (faster/short) | 19.21% | 20.89% | 0.9472 | -39.65% | 0.4846 | 1.7619 | 91 |
| RV120<RV252 SPY (slower) | 19.30% | 21.75% | 0.9217 | -48.81% | 0.3954 | 1.3382 | 99 |
| RV60<RV252 QQQ | 25.76% | 23.01% | 1.1128 | -35.26% | 0.7306 | 2.1780 | 111 |
| RV20<RV252 QQQ (faster) | 28.05% | 23.22% | 1.1826 | -35.46% | 0.7911 | 3.2111 | 114 |
| RV63<RV126 QQQ | 18.26% | 20.15% | 0.9348 | -32.24% | 0.5665 | 1.9037 | 86 |
| downside 60<252 SPY | 25.84% | 22.70% | 1.1277 | -34.01% | 0.7598 | 2.4592 | 107 |
| downside 60<252 QQQ | 25.32% | 22.71% | 1.1091 | -35.26% | 0.7182 | 2.1433 | 107 |
| EWMA 0.94<0.99 SPY | 25.56% | 23.31% | 1.0945 | -31.39% | 0.8142 | 2.9141 | 116 |
| EWMA 0.97<0.99 SPY | 25.54% | 23.06% | 1.1031 | -31.39% | 0.8137 | 2.9310 | 114 |
| EWMA 0.97<0.99 QQQ | 24.45% | 22.55% | 1.0844 | -31.39% | 0.7790 | 2.8525 | 112 |
| downside-EWMA 0.97<0.99 SPY | 24.42% | 23.20% | 1.0593 | -31.39% | 0.7781 | 2.4218 | 114 |
| VXN 21d<252d MA | 19.61% | 20.20% | 0.9890 | -31.39% | 0.6249 | 2.0667 | 102 |
| VXN 63d<252d MA | 12.09% | 21.53% | 0.6388 | -44.75% | 0.2702 | 0.8059 | 99 |
| VXN < 252d median | 18.78% | 18.31% | 1.0327 | -32.05% | 0.5859 | 1.8553 | 89 |
| RV60<RV252 AND VXN<VXN252MA | 19.34% | 18.53% | 1.0483 | -29.57% | 0.6540 | 2.6047 | 85 |
| VIX3M>VIX contango (proxy) | 27.38% | 25.52% | 1.0774 | -40.68% | 0.6730 | 2.0210 | 139 |
| NO-GATE (canary+trend only) | 30.39% | 26.83% | 1.1250 | -38.77% | 0.7839 | 2.2691 | 151 |

## 2. Delta vs V0 (Calmar + Martin are the judged objectives)

| Variant | dSharpe | dCalmar | dMartin | dMaxDD (pp) | dCAGR (pp) |
|---|---:|---:|---:|---:|---:|
| V0 RV60<RV252 SPY (PROD) | +0.0000 | +0.0000 | +0.0000 | +0.00 | +0.00 |
| RV20<RV252 SPY (faster) | +0.0846 | +0.1993 | +1.2043 | -4.53 | +2.81 |
| RV63<RV126 SPY (faster/short) | -0.2340 | -0.2756 | -1.2133 | +3.72 | -8.10 |
| RV120<RV252 SPY (slower) | -0.2595 | -0.3648 | -1.6371 | +12.89 | -8.01 |
| RV60<RV252 QQQ | -0.0684 | -0.0296 | -0.7973 | -0.66 | -1.55 |
| RV20<RV252 QQQ (faster) | +0.0014 | +0.0309 | +0.2358 | -0.46 | +0.75 |
| RV63<RV126 QQQ | -0.2464 | -0.1938 | -1.0716 | -3.68 | -9.05 |
| downside 60<252 SPY | -0.0535 | -0.0004 | -0.5161 | -1.91 | -1.47 |
| downside 60<252 QQQ | -0.0721 | -0.0420 | -0.8319 | -0.66 | -1.99 |
| EWMA 0.94<0.99 SPY | -0.0867 | +0.0540 | -0.0612 | -4.53 | -1.75 |
| EWMA 0.97<0.99 SPY | -0.0781 | +0.0535 | -0.0443 | -4.53 | -1.77 |
| EWMA 0.97<0.99 QQQ | -0.0968 | +0.0188 | -0.1227 | -4.53 | -2.86 |
| downside-EWMA 0.97<0.99 SPY | -0.1219 | +0.0178 | -0.5535 | -4.53 | -2.89 |
| VXN 21d<252d MA | -0.1922 | -0.1354 | -0.9086 | -4.53 | -7.69 |
| VXN 63d<252d MA | -0.5424 | -0.4901 | -2.1694 | +8.83 | -15.22 |
| VXN < 252d median | -0.1485 | -0.1743 | -1.1199 | -3.87 | -8.53 |
| RV60<RV252 AND VXN<VXN252MA | -0.1329 | -0.1062 | -0.3705 | -6.35 | -7.97 |
| VIX3M>VIX contango (proxy) | -0.1038 | -0.0872 | -0.9543 | +4.75 | +0.07 |
| NO-GATE (canary+trend only) | -0.0562 | +0.0237 | -0.7062 | +2.85 | +3.08 |

*dMaxDD>0 = deeper drawdown (worse). dCalmar/dMartin>0 = better risk-adjusted return.*

## 3. Per-crisis protection (NDX sleeve MaxDD / total return in window)

| Variant | 2008 GFC DD/Ret | 2018 Q4 DD/Ret | 2020 COVID DD/Ret | 2022 bear DD/Ret |
|---|---|---|---|---|
| V0 RV60<RV252 SPY (PROD) | -9.11% / 18.01% | -7.43% / 27.57% | -20.46% / 8.57% | -0.30% / 0.94% |
| RV20<RV252 SPY (faster) | -9.11% / 18.01% | -8.26% / 26.44% | -5.05% / 40.53% | -0.30% / 0.94% |
| RV63<RV126 SPY (faster/short) | -9.11% / 18.01% | -14.25% / 25.26% | -20.46% / 8.57% | -0.30% / 0.94% |
| RV120<RV252 SPY (slower) | -9.11% / 18.01% | -2.22% / 15.80% | -4.68% / 10.99% | -24.74% / -17.44% |
| RV60<RV252 QQQ | -9.11% / 18.01% | -14.25% / 26.39% | -20.46% / 8.57% | -24.74% / -17.44% |
| RV20<RV252 QQQ (faster) | -9.11% / 18.01% | -14.25% / 25.16% | -20.46% / 28.99% | -0.30% / 0.73% |
| RV63<RV126 QQQ | -9.11% / 18.01% | -14.25% / 26.39% | -20.46% / 8.57% | -0.30% / 0.94% |
| downside 60<252 SPY | -9.11% / 18.01% | -14.25% / 26.39% | -20.46% / 8.57% | -24.74% / -17.48% |
| downside 60<252 QQQ | -9.11% / 18.01% | -14.25% / 26.39% | -20.46% / 8.57% | -24.74% / -17.44% |
| EWMA 0.94<0.99 SPY | -9.11% / 18.01% | -8.26% / 26.44% | -20.46% / 28.99% | -0.30% / 0.94% |
| EWMA 0.97<0.99 SPY | -9.11% / 18.01% | -7.43% / 27.57% | -20.46% / 8.57% | -0.30% / 0.73% |
| EWMA 0.97<0.99 QQQ | -9.11% / 18.01% | -14.25% / 26.39% | -20.46% / 8.57% | -0.30% / 0.73% |
| downside-EWMA 0.97<0.99 SPY | -9.11% / 18.01% | -14.25% / 26.39% | -20.46% / 8.57% | -24.74% / -17.48% |
| VXN 21d<252d MA | -9.11% / 18.01% | -4.11% / 0.46% | -20.46% / 8.57% | -0.30% / 0.73% |
| VXN 63d<252d MA | -9.11% / 18.01% | -4.11% / 0.46% | -20.46% / 8.57% | -24.74% / -17.44% |
| VXN < 252d median | -9.11% / 18.01% | -4.11% / 0.46% | -5.05% / 18.28% | -24.74% / -17.48% |
| RV60<RV252 AND VXN<VXN252MA | -9.11% / 18.01% | -4.11% / 0.46% | -5.05% / 18.28% | -0.30% / 0.94% |
| VIX3M>VIX contango (proxy) | -9.11% / 17.78% | -14.25% / 22.14% | -5.88% / 60.39% | -24.74% / -17.44% |
| NO-GATE (canary+trend only) | -9.11% / 17.78% | -14.25% / 22.14% | -20.46% / 47.22% | -26.25% / -13.61% |

*Windows: 2008 GFC 2008-01-01..2009-06-30; 2018 Q4 2018-01-01..2018-12-31; 2020 COVID 2020-01-01..2020-06-30; 2022 bear 2022-01-01..2022-12-31.*

## 4. VERDICT (vs BOTH V0 and no-gate)

**No-gate reference:** Calmar **0.7839** / Martin **2.2691** / Sharpe **1.1250** / MaxDD **-38.77%**. vs V0 Calmar 0.7602 / Martin 2.9753. The KEY QUESTION: does any variant beat BOTH V0 AND no-gate on Calmar AND Martin while keeping crash + grind catches?

Beats-V0 / beats-no-gate = Calmar AND Martin both strictly higher than that reference. Keeps crash = 2008 & 2020 DD not >3pp deeper than V0; keeps grind = 2018-Q4 & 2022 DD not >4pp deeper than V0 (NDX is higher-vol so wider tolerance than BULL).

| Variant | Calmar | Martin | Sharpe | MaxDD | beats V0? | beats no-gate? | keeps crash? | keeps grind? |
|---|---:|---:|---:|---:|:--:|:--:|:--:|:--:|
| V0 RV60<RV252 SPY (PROD) | 0.7602 | 2.9753 | 1.1812 | -35.92% | no | no | Y | Y |
| RV20<RV252 SPY (faster) | 0.9595 | 4.1796 | 1.2658 | -31.39% | YES | YES | Y | Y |
| RV63<RV126 SPY (faster/short) | 0.4846 | 1.7619 | 0.9472 | -39.65% | no | no | Y | NO |
| RV120<RV252 SPY (slower) | 0.3954 | 1.3382 | 0.9217 | -48.81% | no | no | Y | NO |
| RV60<RV252 QQQ | 0.7306 | 2.1780 | 1.1128 | -35.26% | no | no | Y | NO |
| RV20<RV252 QQQ (faster) | 0.7911 | 3.2111 | 1.1826 | -35.46% | YES | YES | Y | NO |
| RV63<RV126 QQQ | 0.5665 | 1.9037 | 0.9348 | -32.24% | no | no | Y | NO |
| downside 60<252 SPY | 0.7598 | 2.4592 | 1.1277 | -34.01% | no | no | Y | NO |
| downside 60<252 QQQ | 0.7182 | 2.1433 | 1.1091 | -35.26% | no | no | Y | NO |
| EWMA 0.94<0.99 SPY | 0.8142 | 2.9141 | 1.0945 | -31.39% | no | YES | Y | Y |
| EWMA 0.97<0.99 SPY | 0.8137 | 2.9310 | 1.1031 | -31.39% | no | YES | Y | Y |
| EWMA 0.97<0.99 QQQ | 0.7790 | 2.8525 | 1.0844 | -31.39% | no | no | Y | NO |
| downside-EWMA 0.97<0.99 SPY | 0.7781 | 2.4218 | 1.0593 | -31.39% | no | no | Y | NO |
| VXN 21d<252d MA | 0.6249 | 2.0667 | 0.9890 | -31.39% | no | no | Y | Y |
| VXN 63d<252d MA | 0.2702 | 0.8059 | 0.6388 | -44.75% | no | no | Y | NO |
| VXN < 252d median | 0.5859 | 1.8553 | 1.0327 | -32.05% | no | no | Y | NO |
| RV60<RV252 AND VXN<VXN252MA | 0.6540 | 2.6047 | 1.0483 | -29.57% | no | no | Y | Y |
| VIX3M>VIX contango (proxy) | 0.6730 | 2.0210 | 1.0774 | -40.68% | no | no | Y | NO |
| NO-GATE (canary+trend only) | 0.7839 | 2.2691 | 1.1250 | -38.77% | no | no | Y | NO |

**Apparent winner: RV20<RV252 SPY (faster)** -- beats BOTH V0 (Calmar 0.9595 vs 0.7602, Martin 4.1796 vs 2.9753) AND no-gate (Calmar 0.7839, Martin 2.2691) while keeping crash AND grind catches. REQUIRES the skepticism checks in section 5 (response-surface spike-vs-plateau + per-episode decomposition) before any adoption. Single in-sample run; NOT yet adoptable.

**Honesty guards.** T+1 MOO, point-in-time NDX membership, single in-sample run. Pre-2017 survivorship bias (~28% missing tickers). Any apparent winner needs paired bootstrap-CI on the Calmar/Martin deltas + walk-forward (freeze gate pre-2017, test 2017+) before adoption.

## 5. Skepticism checks on the apparent winner

Apparent winner = **RV20<RV252 SPY (faster)**. Two stress checks: (5a) response-surface spike-vs-plateau over the fast window, and (5b) per-episode decomposition (does one crisis episode drive the entire edge?).

### 5a. Response surface: RV{fast}<RV252 on SPY

| fast window | Calmar | Martin | Sharpe | MaxDD |
|---:|---:|---:|---:|---:|
| 10 | 0.9292 | 3.7431 | 1.2274 | -31.39% |
| 15 | 0.9095 | 4.0639 | 1.2200 | -31.39% |
| 20 | 0.9595 | 4.1796 | 1.2658 | -31.39% |
| 25 | 0.8513 | 3.1886 | 1.1622 | -31.39% |
| 30 | 0.8450 | 2.7621 | 1.1286 | -31.39% |
| 40 | 0.8001 | 3.0449 | 1.1710 | -34.01% |
| 50 | 0.7633 | 3.1529 | 1.1804 | -35.92% |
| 60 | 0.7602 | 2.9753 | 1.1812 | -35.92% |
| 90 | 0.5349 | 1.9103 | 0.9634 | -39.75% |
| 120 | 0.3954 | 1.3382 | 0.9217 | -48.81% |

Peak Calmar at fast=20 (0.9595). Adjacent windows are within ~0.10 Calmar of the peak -- but note the surface is NOT monotone; the edge concentrates in a narrow fast band.


### 5b. Per-episode decomposition (drop one crisis window, recompute)

If the winner's edge vs V0 / no-gate collapses when a single episode is removed, the edge is that episode, not a robust gate property.

| dropped window | winner Calmar | winner Martin | dCalmar vs V0 | dMartin vs V0 | dCalmar vs no-gate | dMartin vs no-gate |
|---|---:|---:|---:|---:|---:|---:|
| none (full) | 0.9595 | 4.1796 | +0.1993 | +1.2043 | +0.1756 | +1.9105 |
| 2008 GFC | 0.9240 | 3.9007 | +0.1941 | +1.1423 | +0.1686 | +1.6739 |
| 2018 Q4 | 0.9092 | 3.7160 | +0.1936 | +1.0860 | +0.1602 | +1.6074 |
| 2020 COVID | 0.8868 | 3.8161 | +0.1417 | +0.8399 | +0.1699 | +1.7486 |
| 2022 bear | 0.9575 | 4.0728 | +0.1990 | +1.1772 | +0.1479 | +1.3214 |

Full-sample dCalmar vs V0 = +0.1993. Dropping **2020 COVID** moves it to +0.1417. The edge survives removal of every single episode (no one episode flips the sign), so it is not purely one-episode driven -- but still in-sample.

## 6. Bottom line

On this single 18y in-sample run the NDX sleeve does NOT obviously keep its inherited V0 (RV60<RV252 SPY): a FASTER realized gate **RV20<RV252 SPY (faster)** dominates -- it beats BOTH V0 (Calmar 0.9595 vs 0.7602, Martin 4.1796 vs 2.9753) AND no-gate (Calmar 0.7839, Martin 2.2691) on Calmar AND Martin, keeps every crisis catch, sits on a fast-window plateau (10-20d, not an isolated spike), and the edge survives removal of any single crisis episode (dCalmar vs V0 stays +0.14..+0.20). This DIVERGES from BULL, where every variant round kept V0.

**No-gate is NOT the answer for NDX:** dropping the gate beats V0 on Calmar (lower MaxDD floor) but LOSES on Martin (2.2691 < 2.9753) and deepens MaxDD to -38.77% -- the gate's whipsaw/ulcer reduction still earns its keep; the lever is the WINDOW (faster), not gate-vs-no-gate.

**Adoption status: CANDIDATE, not adopted.** Single in-sample run; pre-2017 survivorship bias; T+1 MOO / PIT honesty caveats apply. Required before any production change: paired stationary-block bootstrap CI on the RV20-minus-V0 Calmar/Martin deltas, and a walk-forward (freeze the window choice pre-2017, test 2017+). The faster-window result is suggestive but NOT yet decision-grade. User decides.

## Caveats

- EXPLORATION ONLY; no production/memo edits; no commit. Read-only re production.
- Only the vol-gate layer changes; canary/trend/selection/delisting/execution held at prod.
- NDX standalone sleeve lens; at 20% blend weight effects scale ~1/5 (and dilute further against CPM + BULL co-movement).
- VXN has no clean 3M index on yfinance; the term-structure variant uses SPX VIX/VIX3M as a cross-asset proxy (vol term structure is highly correlated across SPX/NDX). Documented gap.
- Realized vol = annualized std of daily returns; downside = sqrt(mean(min(r,0)^2))*sqrt(252); EWMA = RiskMetrics var_t=lambda*var_{t-1}+(1-lambda)*r^2 (pandas ewm alpha=1-lambda).
- Pre-2017 NDX segment has survivorship bias; post-2020 is clean PIT coverage.
