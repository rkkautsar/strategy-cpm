# NDX-sleeve gate underlying: should the NDX sleeve gate on QQQ (its own underlying) instead of SPY?

Role: analyst (hypothesis-driven, read-only re production; writes only to research/; no production/memo files changed; no commit). EXPLORATION ONLY -- a POTENTIAL NDX-sleeve change; user decides adoption later. Harness `research/ndx_gate_underlying.py` (SEPARATE from `ndx_volgate_variants.py`, which holds trend on SPY and only sweeps the vol layer).

**Question.** The NDX sleeve fires its top-K Nasdaq-100 momentum basket only when BULL is risk-on = canary(TIP 13612U>0) AND trend(SPY 13612U>0) AND vol(RV60<RV252 on SPY). BOTH the trend gate and the vol gate are inherited 1:1 from BULL and computed on SPY. But the NDX sleeve TRADES Nasdaq-100 -- higher-beta / more tech-concentrated than SPY. Should it gate on its OWN underlying (QQQ) instead? And does QQQ-gating interact with the faster RV20 window?

**Design: 2x2x2 grid.** trend underlying {SPY,QQQ} x vol underlying {RV(SPY),RV(QQQ)} x window {RV20<RV252, RV60<RV252} = 8 cells. Canary stays TIP 13612U>0 (keep as-is). V0 = trend SPY / vol SPY / RV60. Only the gate underlyings/window change; selection (top-K=5 raw 13612U, partial-fill to best-of-safe), delisting haircut and T+1 MOO execution held at production. Judged on Calmar AND Martin, keeping crisis catches.

**Convention.** T+1 MOO (next-day open), 10 bps/side, monthly month-end signal. Window 2007-02-28..2026-05-22 (231 monthly signals). NDX STANDALONE sleeve (the lens where the gate matters most; at 20% blend weight effects scale ~1/5).

**Caveat up front:** pre-2017 NDX backtest has ~28% survivorship bias (missing delisted tickers); post-2020 PIT coverage is clean. Single 18y in-sample run; any winner needs paired bootstrap-CI / walk-forward before adoption.

## 0. Anchor (reproduced before deltas)

NDX V0 (trend SPY / vol SPY / RV60<RV252) standalone: Sharpe **1.1812** / MaxDD **-35.92%** / Calmar **0.7602** / Martin **2.9753** vs expected {'sharpe': 1.1812, 'maxdd': -0.3592, 'calmar': 0.7602, 'martin': 2.9753} -> **CONFIRMED**.

## 1. The 2x2x2 grid (full-window standalone metrics)

| Cell (trend / vol / window) | CAGR | Vol | Sharpe | MaxDD | Calmar | Martin | active mo |
|---|---:|---:|---:|---:|---:|---:|---:|
| SPY / SPY / RV20<RV252 | 30.12% | 22.90% | 1.2658 | -31.39% | 0.9595 | 4.1796 | 111 |
| SPY / SPY / RV60<RV252 (V0) | 27.31% | 22.64% | 1.1812 | -35.92% | 0.7602 | 2.9753 | 110 |
| SPY / QQQ / RV20<RV252 | 28.05% | 23.22% | 1.1826 | -35.46% | 0.7911 | 3.2111 | 114 |
| SPY / QQQ / RV60<RV252 | 25.76% | 23.01% | 1.1128 | -35.26% | 0.7306 | 2.1780 | 111 |
| QQQ / SPY / RV20<RV252 | 30.88% | 23.42% | 1.2680 | -31.39% | 0.9838 | 4.2732 | 115 |
| QQQ / SPY / RV60<RV252 | 27.54% | 22.96% | 1.1762 | -35.92% | 0.7667 | 3.0019 | 111 |
| QQQ / QQQ / RV20<RV252 | 28.80% | 23.73% | 1.1869 | -35.46% | 0.8123 | 3.2906 | 118 |
| QQQ / QQQ / RV60<RV252 | 25.99% | 23.32% | 1.1091 | -35.26% | 0.7372 | 2.1980 | 112 |

## 2. Delta vs V0 (Calmar + Martin are the judged objectives)

| Cell | dSharpe | dCalmar | dMartin | dMaxDD (pp) | dCAGR (pp) |
|---|---:|---:|---:|---:|---:|
| trend SPY / vol SPY RV20<RV252 | +0.0846 | +0.1993 | +1.2043 | -4.53 | +2.81 |
| trend SPY / vol SPY RV60<RV252 | +0.0000 | +0.0000 | +0.0000 | +0.00 | +0.00 |
| trend SPY / vol QQQ RV20<RV252 | +0.0014 | +0.0309 | +0.2358 | -0.46 | +0.75 |
| trend SPY / vol QQQ RV60<RV252 | -0.0684 | -0.0296 | -0.7973 | -0.66 | -1.55 |
| trend QQQ / vol SPY RV20<RV252 | +0.0868 | +0.2235 | +1.2979 | -4.53 | +3.57 |
| trend QQQ / vol SPY RV60<RV252 | -0.0050 | +0.0065 | +0.0266 | -0.00 | +0.23 |
| trend QQQ / vol QQQ RV20<RV252 | +0.0057 | +0.0521 | +0.3153 | -0.46 | +1.49 |
| trend QQQ / vol QQQ RV60<RV252 | -0.0721 | -0.0230 | -0.7772 | -0.66 | -1.32 |

*dMaxDD>0 = deeper drawdown (worse). dCalmar/dMartin>0 = better.*

## 3. Marginal effect: switch JUST trend vs JUST vol underlying

Isolates which gate (if either) benefits from QQQ. Each row holds everything else at V0 and flips one knob.

| Knob switched | Cell | dCalmar | dMartin | dSharpe | dMaxDD (pp) |
|---|---|---:|---:|---:|---:|
| trend SPY->QQQ (vol SPY RV60) | trend QQQ / vol SPY RV60<RV252 | +0.0065 | +0.0266 | -0.0050 | -0.00 |
| vol  SPY->QQQ (trend SPY RV60) | trend SPY / vol QQQ RV60<RV252 | -0.0296 | -0.7973 | -0.0684 | -0.66 |
| window RV60->RV20 (trend SPY vol SPY) | trend SPY / vol SPY RV20<RV252 | +0.1993 | +1.2043 | +0.0846 | -4.53 |
| trend+vol both ->QQQ (RV60) | trend QQQ / vol QQQ RV60<RV252 | -0.0230 | -0.7772 | -0.0721 | -0.66 |
| vol SPY->QQQ + RV20 (trend SPY) | trend SPY / vol QQQ RV20<RV252 | +0.0309 | +0.2358 | +0.0014 | -0.46 |
| ALL ->QQQ + RV20 | trend QQQ / vol QQQ RV20<RV252 | +0.0521 | +0.3153 | +0.0057 | -0.46 |
| trend QQQ + vol SPY RV20 | trend QQQ / vol SPY RV20<RV252 | +0.2235 | +1.2979 | +0.0868 | -4.53 |

## 4. Per-crisis protection (NDX sleeve MaxDD / total return in window)

| Cell | 2008 GFC DD/Ret | 2018 Q4 DD/Ret | 2020 COVID DD/Ret | 2022 bear DD/Ret |
|---|---|---|---|---|
| trend SPY / vol SPY RV20<RV252 | -9.11% / 18.01% | -8.26% / 26.44% | -5.05% / 40.53% | -0.30% / 0.94% |
| trend SPY / vol SPY RV60<RV252 | -9.11% / 18.01% | -7.43% / 27.57% | -20.46% / 8.57% | -0.30% / 0.94% |
| trend SPY / vol QQQ RV20<RV252 | -9.11% / 18.01% | -14.25% / 25.16% | -20.46% / 28.99% | -0.30% / 0.73% |
| trend SPY / vol QQQ RV60<RV252 | -9.11% / 18.01% | -14.25% / 26.39% | -20.46% / 8.57% | -24.74% / -17.44% |
| trend QQQ / vol SPY RV20<RV252 | -11.09% / 24.89% | -8.26% / 26.44% | -5.05% / 40.53% | -0.30% / 0.94% |
| trend QQQ / vol SPY RV60<RV252 | -11.09% / 25.26% | -7.43% / 27.57% | -20.46% / 8.57% | -0.30% / 0.94% |
| trend QQQ / vol QQQ RV20<RV252 | -11.09% / 24.89% | -14.25% / 25.16% | -20.46% / 28.99% | -0.30% / 0.73% |
| trend QQQ / vol QQQ RV60<RV252 | -11.09% / 25.26% | -14.25% / 26.39% | -20.46% / 8.57% | -24.74% / -17.44% |

*Windows: 2008 GFC 2008-01-01..2009-06-30; 2018 Q4 2018-01-01..2018-12-31; 2020 COVID 2020-01-01..2020-06-30; 2022 bear 2022-01-01..2022-12-31.*

## 5. VERDICT scorecard

Beats-V0 = Calmar AND Martin both strictly higher than V0. Keeps crash = 2008 & 2020 DD not >3pp deeper than V0; keeps grind = 2018-Q4 & 2022 DD not >4pp deeper than V0.

| Cell | Calmar | Martin | Sharpe | MaxDD | beats V0? | keeps crash? | keeps grind? |
|---|---:|---:|---:|---:|:--:|:--:|:--:|
| trend SPY / vol SPY RV20<RV252 | 0.9595 | 4.1796 | 1.2658 | -31.39% | YES | Y | Y |
| trend SPY / vol SPY RV60<RV252 | 0.7602 | 2.9753 | 1.1812 | -35.92% | no | Y | Y |
| trend SPY / vol QQQ RV20<RV252 | 0.7911 | 3.2111 | 1.1826 | -35.46% | YES | Y | NO |
| trend SPY / vol QQQ RV60<RV252 | 0.7306 | 2.1780 | 1.1128 | -35.26% | no | Y | NO |
| trend QQQ / vol SPY RV20<RV252 | 0.9838 | 4.2732 | 1.2680 | -31.39% | YES | Y | Y |
| trend QQQ / vol SPY RV60<RV252 | 0.7667 | 3.0019 | 1.1762 | -35.92% | YES | Y | Y |
| trend QQQ / vol QQQ RV20<RV252 | 0.8123 | 3.2906 | 1.1869 | -35.46% | YES | Y | NO |
| trend QQQ / vol QQQ RV60<RV252 | 0.7372 | 2.1980 | 1.1091 | -35.26% | no | Y | NO |

**Apparent winner: trend QQQ / vol SPY RV20<RV252** -- beats V0 (Calmar 0.9838 vs 0.7602, Martin 4.2732 vs 2.9753) while keeping crash AND grind catches. REQUIRES the skepticism checks in section 6 before any adoption.

## 6. Skepticism on the apparent winner

Apparent winner = **trend QQQ / vol SPY RV20<RV252**. (6a) response-surface spike-vs-plateau over the fast window (on the winner's vol underlying = SPY, trend = QQQ); (6b) per-episode decomposition (does one crisis drive the edge?).

### 6a. Response surface: RV{fast}<RV252 on SPY (trend QQQ)

| fast window | Calmar | Martin | Sharpe | MaxDD |
|---:|---:|---:|---:|---:|
| 10 | 0.8980 | 3.1123 | 1.1673 | -31.39% |
| 15 | 0.9335 | 4.1587 | 1.2230 | -31.39% |
| 20 | 0.9838 | 4.2732 | 1.2680 | -31.39% |
| 25 | 0.8749 | 3.2700 | 1.1664 | -31.39% |
| 30 | 0.8460 | 2.7255 | 1.1130 | -31.39% |
| 40 | 0.8010 | 3.0403 | 1.1538 | -34.01% |
| 50 | 0.7647 | 3.1521 | 1.1636 | -35.92% |
| 60 | 0.7667 | 3.0019 | 1.1762 | -35.92% |
| 90 | 0.5405 | 1.9308 | 0.9614 | -39.75% |
| 120 | 0.3801 | 1.2675 | 0.8558 | -48.81% |

Peak Calmar at fast=20 (0.9838). Adjacent windows within ~0.10 Calmar of the peak -- plateau, not a spike.


### 6b. Per-episode decomposition (drop one crisis window, recompute)

If the winner's edge vs V0 collapses when a single episode is removed, the edge IS that episode, not a robust gate property.

| dropped window | winner Calmar | winner Martin | dCalmar vs V0 | dMartin vs V0 |
|---|---:|---:|---:|---:|
| none (full) | 0.9838 | 4.2732 | +0.2235 | +1.2979 |
| 2008 GFC | 0.9358 | 3.9477 | +0.2060 | +1.1893 |
| 2018 Q4 | 0.9332 | 3.8040 | +0.2176 | +1.1740 |
| 2020 COVID | 0.9106 | 3.9076 | +0.1655 | +0.9315 |
| 2022 bear | 0.9817 | 4.1642 | +0.2232 | +1.2686 |

Full-sample dCalmar vs V0 = +0.2235. Dropping **2020 COVID** moves it to +0.1655. Edge survives removal of every single episode (no episode flips the sign) -- not purely one-episode driven, but still in-sample.

## 7. Bottom line: does NDX gate better on QQQ than SPY?

**Short answer: NO -- the NDX sleeve does NOT gate better on QQQ; the win is the WINDOW, not the underlying.** Decomposing the three knobs against V0:

- **VOL gate SPY->QQQ: HARMFUL.** Holding trend SPY / RV60, switching vol to QQQ moves Calmar 0.7602->0.7306 (-0.0296) and Martin 2.9753->2.1780 (-0.7973). Worse on BOTH objectives. The mechanism is the 2022 grind: the SPY vol gate goes defensive (2022 DD -0.30%) but the QQQ vol gate stays risk-on into the drawdown (2022 DD -24.74%). QQQ's own elevated trailing-vol baseline (RV252) means RV-fast rarely trips below it during a tech-led grind, so the higher-beta underlying gates LATER, not earlier. Every QQQ-vol cell FAILS the keeps-grind bar.

- **TREND gate SPY->QQQ: negligible.** Holding vol SPY / RV60, switching trend to QQQ moves Calmar 0.7602->0.7667 (+0.0065), Martin +0.0266. A sliver -- SPY and QQQ 13612U trend signals agree on almost every month-end, so the trend underlying barely matters.

- **WINDOW RV60->RV20: the real lever.** Holding trend SPY / vol SPY, RV20 moves Calmar 0.7602->0.9595 (+0.1993) and Martin +1.2043 -- an order of magnitude larger than either underlying switch, and it does NOT require QQQ.

- **QQQ x RV20 interaction: QQQ does NOT help the faster window either.** At RV20, switching vol SPY->QQQ DROPS Calmar 0.9595->0.7911 -- so RV20-on-QQQ is NOT best of all; RV20-on-SPY is clearly better. The faster window and the QQQ underlying do not stack; QQQ-vol degrades the RV20 win the same way it degrades RV60.

The apparent best cell (trend QQQ / vol SPY RV20<RV252, Calmar 0.9838 / Martin 4.2732) is essentially **RV20-on-SPY-vol** (Calmar 0.9595) plus a negligible QQQ-trend sliver (+0.0243 Calmar). The QQQ-own-underlying hypothesis is REJECTED for the vol gate and immaterial for the trend gate. The RV20 window finding (from the separate vol-window study) is reconfirmed and is the only load-bearing lever. The response surface (6a) is a 15-20d plateau (not a spike) and the edge survives every single-episode removal (6b), so the WINDOW result is robust in-sample -- but the QQQ-underlying part adds nothing.

**Adoption status: RESEARCH ONLY, not adopted.** Single in-sample run; pre-2017 survivorship bias; T+1 MOO / PIT honesty caveats. Before any production change: paired stationary-block bootstrap CI on the winning-cell-minus-V0 Calmar/Martin deltas, and a walk-forward (freeze the gate choice pre-2017, test 2017+). User decides.

## Caveats

- EXPLORATION ONLY; no production/memo edits; no commit. Read-only re production.
- Only the gate underlyings/window change; canary(TIP)/selection/delisting/execution held at prod.
- NDX standalone sleeve lens; at 20% blend weight effects scale ~1/5 (dilute further vs CPM+BULL co-movement).
- Realized vol = annualized std of daily returns over the trailing window at the signal date.
- Trend = 13612U momentum > 0 on monthly resampled closes (SPY vs QQQ).
- Pre-2017 NDX segment has ~28% survivorship bias; post-2020 is clean PIT coverage.
- Separate harness from ndx_volgate_variants.py to avoid a write race with another analyst.
