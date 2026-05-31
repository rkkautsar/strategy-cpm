# Strengthening BULL over HAA-Simple -- lever exploration

Role: analyst (hypothesis-driven, read-only re production; writes only to research/; no production/memo files changed; no commit). Harness `research/bull_strengthen_existing.py` reusing the canonical mooex engine `exec_lag_moo_validation_2026_05_30._segment_returns_conv`.

**Conventions:** T+1 MOO exact (`mooex`, real auto_adjust opens), 10 bps/side post-cost. Clean 2008-05-30..2026-05-22 (18y); ext/stress 1999-03-10..2026-05-22 (27y). Safe pool ['SHV', 'IEF'] (best-of by 13612U). Vol-target sigma_hat window = 60d. CPM sleeve UNCHANGED (HYG-OR-TIP) for the 60/40 blend.

## 0. Anchor gate

- CPM-solo clean Sharpe = **1.1910** (expect 1.1910) -> CONFIRMED
- BULL-TIP-only clean Sharpe = **1.1005** (expect ~1.10) -> CONFIRMED

## 1. BULL sleeve standalone (clean 18y + ext 27y)

| Variant | Win | CAGR | Vol | Sharpe | MaxDD | Calmar | TurnK/yr |
|---|---|---:|---:|---:|---:|---:|---:|
| HAA-Simple (TIP+SPY) | clean | 11.60% | 11.92% | **0.9840** | -20.41% | 0.5685 | 5.33 |
| | ext | 10.73% | 11.11% | 0.9735 | -20.41% | 0.5259 | |
| BULL-TIP-only (rv60<rv252) | clean | 10.93% | 9.90% | **1.1005** | -13.35% | 0.8189 | 5.33 |
| | ext | 9.48% | 9.30% | 1.0207 | -13.35% | 0.7101 | |
| L1 TIP-AND-HYG (rv60<rv252) | clean | 10.93% | 9.90% | **1.1005** | -13.35% | 0.8189 | 5.33 |
| | ext | 9.48% | 9.30% | 1.0207 | -13.35% | 0.7101 | |
| L2 rv63<rv126 | clean | 8.28% | 9.55% | **0.8841** | -14.70% | 0.5633 | 7.11 |
| | ext | 7.14% | 8.96% | 0.8146 | -14.92% | 0.4785 | |
| L2 rv42<rv126 | clean | 7.50% | 9.67% | **0.7992** | -14.63% | 0.5126 | 8.11 |
| | ext | 7.40% | 9.03% | 0.8354 | -14.63% | 0.5055 | |
| L2 rv63<rv189 | clean | 9.10% | 9.67% | **0.9517** | -13.35% | 0.6815 | 6.22 |
| | ext | 8.47% | 9.02% | 0.9464 | -13.35% | 0.6345 | |
| L2 rv42<rv252 | clean | 11.18% | 9.89% | **1.1247** | -13.35% | 0.8379 | 5.44 |
| | ext | 9.80% | 9.28% | 1.0532 | -13.35% | 0.7341 | |
| L3a VT15 (no binary gate) | clean | 10.11% | 10.85% | **0.9457** | -17.31% | 0.5843 | 5.39 |
| | ext | 9.76% | 10.23% | 0.9614 | -17.31% | 0.5639 | |
| L3a VT-rv126 (no binary gate) | clean | 11.24% | 11.24% | **1.0078** | -18.11% | 0.6211 | 5.49 |
| | ext | 10.33% | 10.53% | 0.9856 | -18.11% | 0.5703 | |
| L3a VT-rv252 (no binary gate) | clean | 11.06% | 11.11% | **1.0034** | -17.49% | 0.6324 | 5.35 |
| | ext | 10.28% | 10.37% | 0.9952 | -17.49% | 0.5876 | |
| L3b VT15 + rv60<rv252 | clean | 10.28% | 9.54% | **1.0767** | -13.35% | 0.7700 | 5.38 |
| | ext | 9.04% | 8.98% | 1.0092 | -13.35% | 0.6777 | |
| L3b VT-rv126 + rv60<rv252 | clean | 10.80% | 9.77% | **1.1016** | -13.35% | 0.8091 | 5.47 |
| | ext | 9.39% | 9.19% | 1.0224 | -13.35% | 0.7036 | |
| L3b VT-rv252 + rv60<rv252 | clean | 10.93% | 9.90% | **1.1005** | -13.35% | 0.8189 | 5.33 |
| | ext | 9.48% | 9.30% | 1.0207 | -13.35% | 0.7101 | |

## 2. BULL sleeve stress drawdowns (within clean window)

| Variant | 2022 DD | 2022 ret | COVID DD | COVID ret | GFC DD | GFC ret |
|---|---:|---:|---:|---:|---:|---:|
| HAA-Simple (TIP+SPY) | -10.11% | -0.33% | -13.35% | -4.14% | -12.09% | 2.70% |
| BULL-TIP-only (rv60<rv252) | -0.30% | 0.94% | -13.35% | -4.14% | -12.09% | 2.70% |
| L1 TIP-AND-HYG (rv60<rv252) | -0.30% | 0.94% | -13.35% | -4.14% | -12.09% | 2.70% |
| L2 rv63<rv126 | -0.30% | 0.94% | -13.35% | -4.14% | -12.09% | 2.70% |
| L2 rv42<rv126 | -0.30% | 0.94% | -13.35% | -4.14% | -12.09% | 2.70% |
| L2 rv63<rv189 | -0.30% | 0.94% | -13.35% | -4.14% | -12.09% | 2.70% |
| L2 rv42<rv252 | -0.30% | 1.03% | -13.35% | -4.14% | -12.09% | 2.70% |
| L3a VT15 (no binary gate) | -9.73% | -1.20% | -13.35% | -4.14% | -10.20% | 3.90% |
| L3a VT-rv126 (no binary gate) | -8.99% | -0.58% | -13.35% | -4.14% | -12.09% | 2.70% |
| L3a VT-rv252 (no binary gate) | -9.27% | -1.15% | -13.35% | -4.14% | -12.09% | 2.70% |
| L3b VT15 + rv60<rv252 | -0.30% | 0.94% | -13.35% | -4.14% | -10.20% | 3.90% |
| L3b VT-rv126 + rv60<rv252 | -0.30% | 0.94% | -13.35% | -4.14% | -12.09% | 2.70% |
| L3b VT-rv252 + rv60<rv252 | -0.30% | 0.94% | -13.35% | -4.14% | -12.09% | 2.70% |

*GFC window 2008-09-01..2009-06-30 partially inside clean 18y (starts 2008-05-30).*

## 3. 60/40 blend (0.60 CPM + 0.40 enhanced BULL)

| Variant | Win | CAGR | Vol | Sharpe | MaxDD | Calmar |
|---|---|---:|---:|---:|---:|---:|
| HAA-Simple (TIP+SPY) | clean | 12.85% | 10.28% | **1.2314** | -11.32% | 1.1350 |
| | ext | 12.65% | 9.95% | 1.2462 | -11.32% | 1.1171 |
| BULL-TIP-only (rv60<rv252) | clean | 12.55% | 9.65% | **1.2777** | -10.68% | 1.1746 |
| | ext | 12.13% | 9.26% | 1.2817 | -10.68% | 1.1349 |
| L1 TIP-AND-HYG (rv60<rv252) | clean | 12.55% | 9.65% | **1.2777** | -10.68% | 1.1746 |
| | ext | 12.13% | 9.26% | 1.2817 | -10.68% | 1.1349 |
| L2 rv63<rv126 | clean | 11.47% | 9.48% | **1.1969** | -10.68% | 1.0736 |
| | ext | 11.16% | 9.10% | 1.2084 | -10.83% | 1.0305 |
| L2 rv42<rv126 | clean | 11.16% | 9.43% | **1.1736** | -10.68% | 1.0444 |
| | ext | 11.28% | 9.09% | 1.2209 | -10.83% | 1.0408 |
| L2 rv63<rv189 | clean | 11.80% | 9.53% | **1.2230** | -10.68% | 1.1049 |
| | ext | 11.71% | 9.11% | 1.2611 | -10.68% | 1.0965 |
| L2 rv42<rv252 | clean | 12.65% | 9.63% | **1.2904** | -10.68% | 1.1844 |
| | ext | 12.26% | 9.24% | 1.2981 | -10.68% | 1.1474 |
| L3a VT15 (no binary gate) | clean | 12.23% | 9.97% | **1.2109** | -11.12% | 1.0997 |
| | ext | 12.23% | 9.71% | 1.2376 | -11.12% | 1.1005 |
| L3a VT-rv126 (no binary gate) | clean | 12.69% | 10.12% | **1.2357** | -10.96% | 1.1574 |
| | ext | 12.47% | 9.80% | 1.2477 | -10.96% | 1.1374 |
| L3a VT-rv252 (no binary gate) | clean | 12.61% | 10.09% | **1.2319** | -10.89% | 1.1575 |
| | ext | 12.45% | 9.76% | 1.2509 | -10.89% | 1.1425 |
| L3b VT15 + rv60<rv252 | clean | 12.28% | 9.51% | **1.2704** | -10.68% | 1.1497 |
| | ext | 11.95% | 9.15% | 1.2786 | -10.68% | 1.1182 |
| L3b VT-rv126 + rv60<rv252 | clean | 12.49% | 9.62% | **1.2766** | -10.68% | 1.1694 |
| | ext | 12.09% | 9.24% | 1.2817 | -10.68% | 1.1314 |
| L3b VT-rv252 + rv60<rv252 | clean | 12.55% | 9.65% | **1.2777** | -10.68% | 1.1746 |
| | ext | 12.13% | 9.26% | 1.2817 | -10.68% | 1.1349 |

## 4. 60/40 blend stress drawdowns (clean window)

| Variant | 2022 DD | COVID DD | GFC DD |
|---|---:|---:|---:|
| HAA-Simple (TIP+SPY) | -7.69% | -10.68% | -9.90% |
| BULL-TIP-only (rv60<rv252) | -3.86% | -10.68% | -9.90% |
| L1 TIP-AND-HYG (rv60<rv252) | -3.86% | -10.68% | -9.90% |
| L2 rv63<rv126 | -3.86% | -10.68% | -9.90% |
| L2 rv42<rv126 | -3.86% | -10.68% | -9.90% |
| L2 rv63<rv189 | -3.86% | -10.68% | -9.90% |
| L2 rv42<rv252 | -3.86% | -10.68% | -9.90% |
| L3a VT15 (no binary gate) | -7.69% | -10.68% | -9.12% |
| L3a VT-rv126 (no binary gate) | -7.39% | -10.68% | -9.90% |
| L3a VT-rv252 (no binary gate) | -7.50% | -10.68% | -9.90% |
| L3b VT15 + rv60<rv252 | -3.86% | -10.68% | -9.12% |
| L3b VT-rv126 + rv60<rv252 | -3.86% | -10.68% | -9.90% |
| L3b VT-rv252 + rv60<rv252 | -3.86% | -10.68% | -9.90% |

## 5. Paired block bootstrap -- 60/40 blend delta-Sharpe (clean)

Stationary block bootstrap, B=2000, block=21d, seed=42. Paired delta-Sharpe of variant blend minus baseline blend. p_win = fraction of resamples where variant > baseline.

| Variant | dSharpe vs HAA (med [95% CI]) | p_win | dSharpe vs BULL-TIP (med [95% CI]) | p_win |
|---|---|---:|---|---:|
| HAA-Simple (TIP+SPY) | +0.0000 [+0.000, +0.000] | 0.00 | -0.0463 [-0.195, +0.092] | 0.26 |
| BULL-TIP-only (rv60<rv252) | +0.0463 [-0.092, +0.195] | 0.74 | +0.0000 [+0.000, +0.000] | 0.00 |
| L1 TIP-AND-HYG (rv60<rv252) | +0.0463 [-0.092, +0.195] | 0.74 | +0.0000 [+0.000, +0.000] | 0.00 |
| L2 rv63<rv126 | -0.0325 [-0.192, +0.130] | 0.34 | -0.0771 [-0.176, +0.020] | 0.07 |
| L2 rv42<rv126 | -0.0621 [-0.217, +0.113] | 0.24 | -0.1061 [-0.208, -0.002] | 0.02 |
| L2 rv63<rv189 | -0.0057 [-0.163, +0.156] | 0.47 | -0.0535 [-0.126, +0.006] | 0.04 |
| L2 rv42<rv252 | +0.0578 [-0.082, +0.222] | 0.78 | +0.0123 [-0.044, +0.070] | 0.67 |
| L3a VT15 (no binary gate) | -0.0205 [-0.068, +0.026] | 0.19 | -0.0667 [-0.202, +0.052] | 0.15 |
| L3a VT-rv126 (no binary gate) | +0.0049 [-0.017, +0.026] | 0.67 | -0.0414 [-0.175, +0.083] | 0.26 |
| L3a VT-rv252 (no binary gate) | +0.0012 [-0.029, +0.031] | 0.53 | -0.0449 [-0.175, +0.069] | 0.23 |
| L3b VT15 + rv60<rv252 | +0.0391 [-0.104, +0.186] | 0.70 | -0.0077 [-0.028, +0.014] | 0.23 |
| L3b VT-rv126 + rv60<rv252 | +0.0454 [-0.093, +0.193] | 0.74 | -0.0013 [-0.008, +0.006] | 0.37 |
| L3b VT-rv252 + rv60<rv252 | +0.0463 [-0.092, +0.195] | 0.74 | +0.0000 [+0.000, +0.000] | 0.00 |

## 6. Ranked verdict

**Anchors confirmed:** CPM-solo clean Sharpe 1.1910; BULL-TIP-only clean Sharpe 1.1005 (sleeve) / blend 1.2777 (clean) / 1.2817 (ext); HAA-Simple blend 1.2314 (clean).

**Where BULL's edge over HAA-Simple actually lives:** the existing binary rv60<rv252 gate already delivers the entire economically meaningful improvement -- it is a 2022 crash dodge. Sleeve 2022 DD -0.30% vs HAA -10.11%; blend 2022 DD -3.86% vs HAA -7.69%; sleeve MaxDD -13.35% vs HAA -20.41%; blend Calmar 1.1746 vs 1.1350. The blend *Sharpe* edge over HAA (+0.046, p_win 0.74) sits inside the bootstrap CI [-0.092,+0.195], so the Sharpe gain alone is noise; the drawdown/Calmar/2022 gains are the real, robust edge.

### Lever ranking (strengthening power over current BULL-TIP-only)

1. **L2 rv42<rv252** -- ONLY lever that improves on current BULL on numbers: blend clean Sharpe 1.2904 (vs 1.2777), ext 1.2981 (vs 1.2817), Calmar 1.1844 (vs 1.1746), MaxDD and all stress DDs unchanged (2022 -3.86%, COVID -10.68%, GFC -9.90%), turnover ~flat (5.44 vs 5.33). BUT the gain over current BULL is noise-level (p_win 0.67, dSharpe +0.012, CI [-0.044,+0.070] straddles 0) and it is a 1-of-4 grid winner (the other 3 rv pairs all LOST) -> real overfitting risk. Robust across clean+ext+stress but marginal.
2. **L3b VT-rv126 + rv60<rv252** -- essentially neutral (blend 1.2766 ~ base 1.2777, same stress). Adds a continuous-scaling param for ~zero benefit. Not worth complexity.
3. **L1 TIP-AND-HYG** -- INERT: byte-identical to BULL-TIP-only on every metric. In the risk-on months (TIP>0 + SPY trend + vol gate) HYG 13612U is already positive, so the AND never binds. Confirms prior 'AND not adopt-worthy' finding; here it is a no-op.
4. **L3a vol-target REPLACING the binary gate** (VT15/VT-rv126/VT-rv252) -- WORSE: blend 1.21-1.24, sleeve Sharpe 0.95-1.01, and crucially LOSES the crash protection (2022 DD -7.4 to -9.7% vs -3.86%). Continuous de-risking does not cut 2022 the way the binary exit does. Reject.
5. **L2 faster-denominator pairs** (rv63<rv126, rv42<rv126, rv63<rv189) -- WORSE across the board (blend 1.17-1.22, higher turnover, sleeve Sharpe 0.80-0.95). Speeding up the SLOW leg whipsaws on grinds. Reject.

*Degenerate note:* VT-rv252+gate is mathematically identical to base -- when the gate is on (rv60<rv252) the target/sigma_hat ratio rv252/rv60 > 1 always caps at 100% SPY, so no scaling ever occurs.

### Bottom line

No lever *clearly* strengthens BULL beyond the existing rv60<rv252 gate. The gate already owns the edge over HAA-Simple (crash dodge -> drawdown/Calmar, not Sharpe). Vol-targeting adds nothing on top and is harmful as a replacement. TIP-AND-HYG is a no-op. The single directional improver, rv42<rv252, is within bootstrap noise and a grid-search winner; adopt only with explicit overfitting caveat (prefer keeping production rv60<rv252 for parsimony). Recommendation: do NOT adopt any lever as a strengthening change; if a single tweak is mandated, rv42<rv252 is the least-bad (weakly dominant, stress-neutral) but flag it as noise-level and grid-fitted.

