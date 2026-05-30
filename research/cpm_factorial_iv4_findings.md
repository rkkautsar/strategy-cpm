# CPM 2^4 factorial -- current production spec (top-4 inverse-vol, no sub-selection)

Role: analyst (read-only re production; no production files changed; no commit). Throwaway harness in `research/`.

Script: `research/cpm_factorial_iv4.py` -> `research/cpm_factorial_iv4.json`.

> SUPERSEDES the CPM side of `research/cpm_factorial_canonical_aaa.py` / `research/cpm_factorial_canonical_aaa_findings.md`, whose 4th factor was the 50/50 minimum-variance pair. The production CPM spec is now single-stage top-4 inverse-vol with NO pair / NO sub-selection, so that 4th factor no longer exists and is REPLACED by a weighting/selection factor (W). The BULL 8-cell factorial is independent of CPM and is NOT recomputed; cite the existing BULL decomposition as-is.

## Factor definitions (off = AAA baseline setting / on = production setting)

| factor | OFF (baseline) | ON (production) |
|---|---|---|
| **C** canary | AAA TIP canary (TIP 13612U>0) | HYG-OR-TIP any-positive 13612U gate |
| **U** universe | canonical AAA SPY-set `[SPY,EFA,EEM,VNQ,GLD,TLT,DBC]` | CPM 8-asset `[QQQ,SPHQ,EFA,EEM,VNQ,GLD,TLT,DBC]` |
| **R** ranker | plain 12-month momentum | vol-adjusted Faber (10m-SMA-distance / rv_252d) |
| **W** weighting/selection | equal-weight top-half, fully invested in positives | top-4 inverse-vol with strict-4 partial-safe (risky_fraction = min(n,4)/4, remainder to timed safe) |

W replaces the former pairing factor. Common fixed-on settings (NOT factors): top-half K cap (ceil(n/2) = 4 in both universes), positive-momentum/positive-trend screen, SHV/IEF best-of-safe timed by 13612U, cov lookback tail(504). all-ON (C,U,R,W = 1,1,1,1) reproduces production CPM.

## Execution convention (every table below)

Realistic T+1 MOO exact (`mooex`), post-cost 10 bps/side, via the shared `_segment_returns_conv` harness so cost/window/execution are byte-identical across all 16 cells. CPM sleeve has NO vol gate. Windows: CLEAN 18y (2008-05-30 .. 2026-05-22), EXT 27y (1999-03-10 .. 2026-05-22). Full panel runs once over EXT and is sliced to each window.

## Anchor gate -- all-ON cell vs production CPM

Binding gate: all-ON parametric cell == live production `compute_target_weights` (param==prod) in both windows, AND the CLEAN all-ON cell == the task-specified expected anchor (Sharpe 1.1910 / MaxDD -12.67% / Calmar 1.0615). EXT is gated against current production-direct.

| window | all-ON Sharpe | all-ON MaxDD | all-ON Calmar | production-direct Sharpe | gate target (Sharpe/MaxDD/Calmar) | param==prod | gate pass |
|---|---:|---:|---:|---:|---|---|---|
| CLEAN | 1.1910 | -12.67% | 1.0615 | 1.1910 | 1.1910/-12.67%/1.0615 | YES | YES |
| EXT | 1.2142 | -15.93% | 0.8608 | 1.2142 | 1.2142/-15.93%/0.8608 | YES | YES |

Gate PASS: the all-ON cell equals live production `cpm_live.compute_target_weights` in both windows and reproduces the task-specified CLEAN anchor (Sharpe 1.1910 / MaxDD -12.67% / Calmar 1.0615) EXACTLY. Grid proceeds.

Note on EXT drift: the pre-existing `cpm_iv4_final_numbers_findings.md` (2026-05-30) reported EXT all-ON Sharpe 1.2161 / MaxDD -15.93% / Calmar 0.8654. That harness no longer imports (`min_vol_pair` was deleted from `cpm_live.py` when pairing was removed), so its EXT figure predates the current production code/data. Current live production EXT is 1.2142 / -15.93% / 0.8608; MaxDD is identical, Sharpe/Calmar drift ~0.002/0.005. The parametric all-ON cell reproduces the CURRENT production EXT exactly.

## Full 16-cell grid -- CLEAN (mooex, 10 bps/side)

Config column order: C,U,R,W.

| C | U | R | W | Sharpe | CAGR | Vol | MaxDD | Calmar |
|---|---|---|---|---|---|---|---|---|
| 0 | 0 | 0 | 0 | 0.7163 | 7.79% | 11.46% | -19.43% | 0.4008 |
| 0 | 0 | 0 | 1 | 0.7188 | 7.31% | 10.68% | -17.42% | 0.4194 |
| 0 | 0 | 1 | 0 | 0.8996 | 10.02% | 11.38% | -17.34% | 0.5776 |
| 0 | 0 | 1 | 1 | 1.0026 | 10.06% | 10.12% | -12.81% | 0.7855 |
| 0 | 1 | 0 | 0 | 0.8891 | 10.20% | 11.76% | -16.16% | 0.6308 |
| 0 | 1 | 0 | 1 | 0.9275 | 9.98% | 10.96% | -16.37% | 0.6093 |
| 0 | 1 | 1 | 0 | 1.0352 | 11.85% | 11.50% | -16.86% | 0.7028 |
| 0 | 1 | 1 | 1 | 1.1546 | 12.16% | 10.46% | -12.67% | 0.9601 |
| 1 | 0 | 0 | 0 | 0.7693 | 8.93% | 12.14% | -19.43% | 0.4596 |
| 1 | 0 | 0 | 1 | 0.7750 | 8.40% | 11.30% | -17.42% | 0.4821 |
| 1 | 0 | 1 | 0 | 0.9076 | 10.66% | 12.01% | -17.34% | 0.6150 |
| 1 | 0 | 1 | 1 | 1.0122 | 10.62% | 10.57% | -11.75% | 0.9035 |
| 1 | 1 | 0 | 0 | 0.9479 | 11.61% | 12.47% | -16.16% | 0.7182 |
| 1 | 1 | 0 | 1 | 0.9916 | 11.43% | 11.66% | -16.37% | 0.6983 |
| 1 | 1 | 1 | 0 | 1.0875 | 13.28% | 12.20% | -16.86% | 0.7878 |
| 1 | 1 | 1 | 1 | **1.1910** | 13.44% | 11.16% | **-12.67%** | **1.0615** |

## Full 16-cell grid -- EXT (mooex, 10 bps/side)

Config column order: C,U,R,W.

| C | U | R | W | Sharpe | CAGR | Vol | MaxDD | Calmar |
|---|---|---|---|---|---|---|---|---|
| 0 | 0 | 0 | 0 | 0.9245 | 10.12% | 11.10% | -19.43% | 0.5211 |
| 0 | 0 | 0 | 1 | 0.9471 | 9.71% | 10.35% | -17.42% | 0.5572 |
| 0 | 0 | 1 | 0 | 0.9994 | 10.90% | 10.95% | -20.87% | 0.5219 |
| 0 | 0 | 1 | 1 | 1.0731 | 10.55% | 9.79% | -13.45% | 0.7839 |
| 0 | 1 | 0 | 0 | 0.9992 | 11.38% | 11.45% | -16.16% | 0.7043 |
| 0 | 1 | 0 | 1 | 1.0331 | 11.05% | 10.70% | -16.37% | 0.6750 |
| 0 | 1 | 1 | 0 | 1.0926 | 12.21% | 11.11% | -20.18% | 0.6047 |
| 0 | 1 | 1 | 1 | 1.1575 | 11.84% | 10.11% | -13.38% | 0.8855 |
| 1 | 0 | 0 | 0 | 0.9447 | 11.24% | 12.04% | -19.43% | 0.5784 |
| 1 | 0 | 0 | 1 | 0.9655 | 10.76% | 11.24% | -17.98% | 0.5982 |
| 1 | 0 | 1 | 0 | 1.0240 | 11.98% | 11.72% | -20.87% | 0.5739 |
| 1 | 0 | 1 | 1 | 1.0993 | 11.53% | 10.42% | -13.45% | 0.8573 |
| 1 | 1 | 0 | 0 | 1.0234 | 12.99% | 12.73% | -17.88% | 0.7267 |
| 1 | 1 | 0 | 1 | 1.0600 | 12.58% | 11.84% | -17.98% | 0.6994 |
| 1 | 1 | 1 | 0 | 1.1567 | 14.27% | 12.17% | -20.18% | 0.7069 |
| 1 | 1 | 1 | 1 | **1.2142** | 13.71% | 11.09% | **-15.93%** | **0.8608** |

## Main effects (background-averaged, coded +-1; effect = mean|on - mean|off)

Sign-flip flag = factor's on-minus-off delta changes sign across backgrounds (direction not robust).

### CLEAN

| factor | dSharpe | flip | dCalmar | flip |
|---|---:|---|---:|---|
| **R** | +0.1944 | | +0.2469 | |
| **U** | +0.1779 | | +0.1907 | |
| **W** | +0.0651 | | +0.1284 | SIGN-FLIP |
| **C** | +0.0423 | | +0.0800 | |

### EXT

| factor | dSharpe | flip | dCalmar | flip |
|---|---:|---|---:|---|
| **W** | +0.0482 | | +0.1224 | SIGN-FLIP |
| **U** | +0.0949 | | +0.1089 | |
| **R** | +0.1149 | | +0.0918 | SIGN-FLIP |
| **C** | +0.0326 | | +0.0435 | SIGN-FLIP |

## Two-way interactions (Calmar, both windows)

| interaction | CLEAN | EXT |
|---|---:|---:|
| RxW | +0.1285 | +0.1226 |
| UxR | -0.0330 | -0.0287 |
| CxW | +0.0128 | -0.0150 |
| CxU | +0.0108 | -0.0124 |
| UxW | -0.0060 | -0.0279 |
| CxR | +0.0055 | +0.0072 |

Key requested analogues: R x W (ranker vs weighting), W x C and R x C (canary unlocks).

Two-way interactions (Sharpe, both windows):

| interaction | CLEAN | EXT |
|---|---:|---:|
| RxW | +0.0425 | +0.0197 |
| UxR | -0.0163 | +0.0114 |
| CxR | -0.0157 | +0.0102 |
| UxW | +0.0112 | +0.0001 |
| CxU | +0.0106 | +0.0103 |
| CxW | -0.0007 | -0.0006 |

## Derived contribution ladder (best ordered cumulative path)

Ordering = factors by clean Calmar main effect, largest first, value-subtractors last: **R -> U -> W -> C**.

### CLEAN cumulative path

| step | config (C,U,R,W) | Sharpe | Calmar | MaxDD |
|---|---|---:|---:|---:|
| all-OFF (AAA baseline) | `0000` | 0.7163 | 0.4008 | -19.43% |
| + R | `0010` | 0.8996 | 0.5776 | -17.34% |
| + U | `0110` | 1.0352 | 0.7028 | -16.86% |
| + W | `0111` | 1.1546 | 0.9601 | -12.67% |
| + C = all-ON (production) | `1111` | 1.1910 | 1.0615 | -12.67% |

### EXT cumulative path

| step | config (C,U,R,W) | Sharpe | Calmar | MaxDD |
|---|---|---:|---:|---:|
| all-OFF (AAA baseline) | `0000` | 0.9245 | 0.5211 | -19.43% |
| + R | `0010` | 0.9994 | 0.5219 | -20.87% |
| + U | `0110` | 1.0926 | 0.6047 | -20.18% |
| + W | `0111` | 1.1575 | 0.8855 | -13.38% |
| + C = all-ON (production) | `1111` | 1.2142 | 0.8608 | -15.93% |

## Caveats / confidence

- all-ON cell reproduces production `cpm_live.compute_target_weights` exactly (param==prod) and the expected current-spec anchor (clean 1.1910 / -12.67% / 1.0615) in both windows. Confidence high.
- Grid internally consistent: shared harness, single EXT run sliced per window, identical cost/execution across all 16 cells.
- Main-effect averaging hides structure; read main effects together with the interaction table and the ladder, not in isolation.
- All numbers mooex / T+1 MOO exact / 10 bps/side / no vol gate (CPM has none). Ext 27y is partly proxy-backed pre-2006 for the trend universe; clean 18y has full real-open coverage and is the decisive lens.
- W replaces the former pairing factor: W-off is equal-weight top-half fully invested; W-on is the production top-4 inverse-vol with strict-4 partial-safe. The AAA baseline (all-OFF) here uses the TIP canary, plain 12m momentum, AAA SPY universe, and equal-weight top-half, so it differs from the prior no-canary/min-var canonical-AAA all-OFF.
