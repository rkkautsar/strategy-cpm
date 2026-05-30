# CPM 2^5 factorial -- isolating the positive-trend screen / absolute-momentum filter

Role: analyst (read-only re production; no production files changed; no commit). Throwaway harness in `research/`.

Script: `research/cpm_factorial_iv4_5factor.py` -> `research/cpm_factorial_iv4_5factor.json`.

> EXTENDS `research/cpm_factorial_iv4.py` from 4 factors to 5 by promoting the positive-trend screen / absolute-momentum filter (S) from a fixed-on constant to a first-class toggled factor. Methodology is otherwise identical: shared T+1 MOO exact (mooex) execution, 10 bps/side, cov tail(504), AAA-anchored baseline, same factorial_effects math, CLEAN 18y + EXT 27y. The 4-factor harness is left intact.

## Why isolate the screen

Canonical AAA holds the top-K momentum assets even when their trend is negative -- it stays fully invested in the top-K. The production CPM applies an absolute-momentum filter: only names with positive trend are held, and the emptied top-K slots route to safe. That filter is a design CHOICE, not an inert constant, so it is decomposed here as factor S rather than held fixed-on.

## Factor definitions (off = AAA baseline setting / on = production setting)

| factor | OFF (baseline) | ON (production) |
|---|---|---|
| **C** canary | AAA TIP canary (TIP 13612U>0) | HYG-OR-TIP any-positive 13612U gate |
| **U** universe | canonical AAA SPY-set `[SPY,EFA,EEM,VNQ,GLD,TLT,DBC]` | CPM 8-asset `[QQQ,SPHQ,EFA,EEM,VNQ,GLD,TLT,DBC]` |
| **R** ranker | plain 12-month momentum | vol-adjusted Faber (10m-SMA-distance / rv_252d) |
| **S** screen (positive-trend / absolute-momentum filter) | no absolute filter -- hold all top-K regardless of momentum sign (AAA-style, fully invested in the top-K) | positive-trend screen -- only hold names with positive trend; emptied top-K slots route to safe |
| **W** weighting/selection | equal-weight the held set | inverse-vol over the held set with strict-4 partial-safe (risky_fraction = min(held,4)/4, remainder to timed safe) |

**S x W coherence.** The held set = top-K (top-half, ceil(n/2) = 4). With S OFF the held set is the full top-K (sign ignored), so the strict-4 partial-safe has no empty slots to route and is fully invested (partial-safe inactive). With S ON the held set is the positive-trend subset, and the strict-4 partial-safe routes the emptied slots to safe. W controls weighting over the held set (equal vs inverse-vol). Common fixed-on settings (NOT factors): top-half K cap (ceil(n/2) = 4 in both universes), SHV/IEF best-of-safe timed by 13612U, cov lookback tail(504). all-ON (C,U,R,S,W = 1,1,1,1,1) reproduces production CPM.

## Execution convention (every table below)

Realistic T+1 MOO exact (`mooex`), post-cost 10 bps/side, via the shared `_segment_returns_conv` harness so cost/window/execution are byte-identical across all 32 cells. CPM sleeve has NO vol gate. Windows: CLEAN 18y (2008-05-30 .. 2026-05-22), EXT 27y (1999-03-10 .. 2026-05-22). Full panel runs once over EXT and is sliced to each window.

## Anchor gate -- all-ON cell vs production CPM

Binding gate: all-ON parametric cell == live production `compute_target_weights` (param==prod) in both windows, AND the CLEAN all-ON cell == the task-specified anchor (Sharpe 1.1910 / MaxDD -12.67% / Calmar 1.0615; EXT 1.2142 / -15.93% / 0.8608).

| window | all-ON Sharpe | all-ON MaxDD | all-ON Calmar | production-direct Sharpe | gate target (Sharpe/MaxDD/Calmar) | param==prod | matches anchor |
|---|---:|---:|---:|---:|---|---|---|
| CLEAN | 1.1910 | -12.67% | 1.0615 | 1.1910 | 1.1910/-12.67%/1.0615 | YES | YES |
| EXT | 1.2142 | -15.93% | 0.8608 | 1.2142 | 1.2142/-15.93%/0.8608 | YES | YES |

Gate PASS: the all-ON cell equals live production `cpm_live.compute_target_weights` in both windows and reproduces the task-specified CLEAN anchor EXACTLY. Grid proceeds.

## Full 32-cell grid -- CLEAN (mooex, 10 bps/side)

Config column order: C,U,R,S,W.

| C | U | R | S | W | Sharpe | CAGR | Vol | MaxDD | Calmar |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 0 | 0 | 0 | 0 | 0.8561 | 9.52% | 11.46% | -19.43% | 0.4902 |
| 0 | 0 | 0 | 0 | 1 | 0.8332 | 8.75% | 10.83% | -17.42% | 0.5020 |
| 0 | 0 | 0 | 1 | 0 | 0.7163 | 7.79% | 11.46% | -19.43% | 0.4008 |
| 0 | 0 | 0 | 1 | 1 | 0.7188 | 7.31% | 10.68% | -17.42% | 0.4194 |
| 0 | 0 | 1 | 0 | 0 | 0.9481 | 10.71% | 11.47% | -18.21% | 0.5880 |
| 0 | 0 | 1 | 0 | 1 | 1.0198 | 10.72% | 10.59% | -15.90% | 0.6742 |
| 0 | 0 | 1 | 1 | 0 | 0.8996 | 10.02% | 11.38% | -17.34% | 0.5776 |
| 0 | 0 | 1 | 1 | 1 | 1.0026 | 10.06% | 10.12% | -12.81% | 0.7855 |
| 0 | 1 | 0 | 0 | 0 | 0.9625 | 11.14% | 11.75% | -16.40% | 0.6793 |
| 0 | 1 | 0 | 0 | 1 | 0.9833 | 10.73% | 11.04% | -16.37% | 0.6553 |
| 0 | 1 | 0 | 1 | 0 | 0.8891 | 10.20% | 11.76% | -16.16% | 0.6308 |
| 0 | 1 | 0 | 1 | 1 | 0.9275 | 9.98% | 10.96% | -16.37% | 0.6093 |
| 0 | 1 | 1 | 0 | 0 | 1.0743 | 12.51% | 11.65% | -16.97% | 0.7372 |
| 0 | 1 | 1 | 0 | 1 | 1.1481 | 12.43% | 10.76% | -14.22% | 0.8744 |
| 0 | 1 | 1 | 1 | 0 | 1.0352 | 11.85% | 11.50% | -16.86% | 0.7028 |
| 0 | 1 | 1 | 1 | 1 | 1.1546 | 12.16% | 10.46% | -12.67% | 0.9601 |
| 1 | 0 | 0 | 0 | 0 | 0.8913 | 10.54% | 12.13% | -19.43% | 0.5425 |
| 1 | 0 | 0 | 0 | 1 | 0.8710 | 9.76% | 11.51% | -17.42% | 0.5600 |
| 1 | 0 | 0 | 1 | 0 | 0.7693 | 8.93% | 12.14% | -19.43% | 0.4596 |
| 1 | 0 | 0 | 1 | 1 | 0.7750 | 8.40% | 11.30% | -17.42% | 0.4821 |
| 1 | 0 | 1 | 0 | 0 | 0.9550 | 11.36% | 12.08% | -18.21% | 0.6237 |
| 1 | 0 | 1 | 0 | 1 | 1.0195 | 11.35% | 11.21% | -15.90% | 0.7139 |
| 1 | 0 | 1 | 1 | 0 | 0.9076 | 10.66% | 12.01% | -17.34% | 0.6150 |
| 1 | 0 | 1 | 1 | 1 | 1.0122 | 10.62% | 10.57% | -11.75% | 0.9035 |
| 1 | 1 | 0 | 0 | 0 | 1.0230 | 12.63% | 12.44% | -16.40% | 0.7704 |
| 1 | 1 | 0 | 0 | 1 | 1.0367 | 12.11% | 11.75% | -16.37% | 0.7397 |
| 1 | 1 | 0 | 1 | 0 | 0.9479 | 11.61% | 12.47% | -16.16% | 0.7182 |
| 1 | 1 | 0 | 1 | 1 | 0.9916 | 11.43% | 11.66% | -16.37% | 0.6983 |
| 1 | 1 | 1 | 0 | 0 | 1.1148 | 13.81% | 12.33% | -16.97% | 0.8138 |
| 1 | 1 | 1 | 0 | 1 | 1.1785 | 13.66% | 11.47% | -14.22% | 0.9606 |
| 1 | 1 | 1 | 1 | 0 | 1.0875 | 13.28% | 12.20% | -16.86% | 0.7878 |
| 1 | 1 | 1 | 1 | 1 | **1.1910** | 13.44% | 11.16% | **-12.67%** | **1.0615** |

## Full 32-cell grid -- EXT (mooex, 10 bps/side)

Config column order: C,U,R,S,W.

| C | U | R | S | W | Sharpe | CAGR | Vol | MaxDD | Calmar |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 0 | 0 | 0 | 0 | 1.0336 | 11.46% | 11.09% | -19.43% | 0.5898 |
| 0 | 0 | 0 | 0 | 1 | 1.0259 | 10.72% | 10.46% | -17.42% | 0.6150 |
| 0 | 0 | 0 | 1 | 0 | 0.9245 | 10.12% | 11.10% | -19.43% | 0.5211 |
| 0 | 0 | 0 | 1 | 1 | 0.9471 | 9.71% | 10.35% | -17.42% | 0.5572 |
| 0 | 0 | 1 | 0 | 0 | 1.0195 | 11.14% | 10.95% | -18.48% | 0.6026 |
| 0 | 0 | 1 | 0 | 1 | 1.0714 | 10.85% | 10.09% | -15.90% | 0.6823 |
| 0 | 0 | 1 | 1 | 0 | 0.9994 | 10.90% | 10.95% | -20.87% | 0.5219 |
| 0 | 0 | 1 | 1 | 1 | 1.0731 | 10.55% | 9.79% | -13.45% | 0.7839 |
| 0 | 1 | 0 | 0 | 0 | 1.0624 | 12.18% | 11.44% | -16.40% | 0.7427 |
| 0 | 1 | 0 | 0 | 1 | 1.0734 | 11.59% | 10.76% | -16.37% | 0.7080 |
| 0 | 1 | 0 | 1 | 0 | 0.9992 | 11.38% | 11.45% | -16.16% | 0.7043 |
| 0 | 1 | 0 | 1 | 1 | 1.0331 | 11.05% | 10.70% | -16.37% | 0.6750 |
| 0 | 1 | 1 | 0 | 0 | 1.0980 | 12.40% | 11.22% | -19.00% | 0.6526 |
| 0 | 1 | 1 | 0 | 1 | 1.1368 | 11.86% | 10.32% | -15.92% | 0.7447 |
| 0 | 1 | 1 | 1 | 0 | 1.0926 | 12.21% | 11.11% | -20.18% | 0.6047 |
| 0 | 1 | 1 | 1 | 1 | 1.1575 | 11.84% | 10.11% | -13.38% | 0.8855 |
| 1 | 0 | 0 | 0 | 0 | 0.9945 | 11.95% | 12.09% | -19.43% | 0.6152 |
| 1 | 0 | 0 | 0 | 1 | 1.0135 | 11.52% | 11.40% | -17.98% | 0.6408 |
| 1 | 0 | 0 | 1 | 0 | 0.9447 | 11.24% | 12.04% | -19.43% | 0.5784 |
| 1 | 0 | 0 | 1 | 1 | 0.9655 | 10.76% | 11.24% | -17.98% | 0.5982 |
| 1 | 0 | 1 | 0 | 0 | 1.0082 | 11.82% | 11.77% | -18.48% | 0.6396 |
| 1 | 0 | 1 | 0 | 1 | 1.0804 | 11.79% | 10.86% | -15.90% | 0.7412 |
| 1 | 0 | 1 | 1 | 0 | 1.0240 | 11.98% | 11.72% | -20.87% | 0.5739 |
| 1 | 0 | 1 | 1 | 1 | 1.0993 | 11.53% | 10.42% | -13.45% | 0.8573 |
| 1 | 1 | 0 | 0 | 0 | 1.0459 | 13.36% | 12.77% | -17.88% | 0.7474 |
| 1 | 1 | 0 | 0 | 1 | 1.0810 | 12.94% | 11.91% | -17.98% | 0.7196 |
| 1 | 1 | 0 | 1 | 0 | 1.0234 | 12.99% | 12.73% | -17.88% | 0.7267 |
| 1 | 1 | 0 | 1 | 1 | 1.0600 | 12.58% | 11.84% | -17.98% | 0.6994 |
| 1 | 1 | 1 | 0 | 0 | 1.1175 | 13.90% | 12.33% | -19.00% | 0.7320 |
| 1 | 1 | 1 | 0 | 1 | 1.1772 | 13.52% | 11.32% | -15.93% | 0.8486 |
| 1 | 1 | 1 | 1 | 0 | 1.1567 | 14.27% | 12.17% | -20.18% | 0.7069 |
| 1 | 1 | 1 | 1 | 1 | **1.2142** | 13.71% | 11.09% | **-15.93%** | **0.8608** |

## Main effects (background-averaged, coded +-1; effect = mean|on - mean|off)

Sign-flip flag = factor's on-minus-off delta changes sign across backgrounds (direction not robust).

### CLEAN

| factor | dSharpe | flip | dCalmar | flip |
|---|---:|---|---:|---|
| **U** | +0.1594 | | +0.1913 | |
| **R** | +0.1597 | | +0.1889 | |
| **W** | +0.0491 | SIGN-FLIP | +0.0914 | SIGN-FLIP |
| **C** | +0.0377 | SIGN-FLIP | +0.0727 | |
| **S** | -0.0556 | SIGN-FLIP | -0.0071 | SIGN-FLIP |

### EXT

| factor | dSharpe | flip | dCalmar | flip |
|---|---:|---|---:|---|
| **U** | +0.0815 | | +0.1025 | |
| **W** | +0.0416 | SIGN-FLIP | +0.0848 | SIGN-FLIP |
| **R** | +0.0811 | SIGN-FLIP | +0.0625 | SIGN-FLIP |
| **C** | +0.0161 | SIGN-FLIP | +0.0434 | SIGN-FLIP |
| **S** | -0.0203 | SIGN-FLIP | -0.0104 | SIGN-FLIP |

## Two-way interactions

Calmar (both windows), sorted by |CLEAN|:

| interaction | CLEAN | EXT |
|---|---:|---:|
| RxW | +0.0946 | +0.0864 |
| RxS | +0.0581 | +0.0293 |
| SxW | +0.0370 | +0.0376 |
| CxU | +0.0149 | -0.0029 |
| UxR | -0.0142 | -0.0234 |
| CxS | +0.0072 | +0.0001 |
| CxW | +0.0072 | -0.0041 |
| UxW | -0.0015 | -0.0193 |
| UxS | -0.0007 | +0.0064 |
| CxR | -0.0002 | +0.0168 |

Sharpe (both windows), sorted by |CLEAN|:

| interaction | CLEAN | EXT |
|---|---:|---:|
| RxW | +0.0389 | +0.0202 |
| RxS | +0.0346 | +0.0338 |
| UxS | +0.0185 | +0.0134 |
| SxW | +0.0160 | +0.0066 |
| CxR | -0.0147 | +0.0125 |
| CxU | +0.0119 | +0.0117 |
| UxW | +0.0105 | +0.0006 |
| UxR | -0.0069 | +0.0154 |
| CxS | +0.0046 | +0.0165 |
| CxW | -0.0017 | +0.0054 |

### Key requested interactions

| interaction | meaning | CLEAN Calmar | EXT Calmar | CLEAN Sharpe | EXT Sharpe |
|---|---|---:|---:|---:|---:|
| SxW | screen vs weighting/partial-safe (drawdown complement/substitute) | +0.0370 | +0.0376 | +0.0160 | +0.0066 |
| CxS | absolute screen vs canary risk-off (overlap) | +0.0072 | +0.0001 | +0.0046 | +0.0165 |
| RxS | ranker vs screen | +0.0581 | +0.0293 | +0.0346 | +0.0338 |
| RxW | ranker vs weighting | +0.0946 | +0.0864 | +0.0389 | +0.0202 |

## Derived contribution ladder (best ordered cumulative path)

Ordering = factors by CLEAN Calmar main effect, largest first, value-subtractors last: **U -> R -> W -> C -> S**.

### CLEAN cumulative path

| step | config (C,U,R,S,W) | Sharpe | Calmar | MaxDD |
|---|---|---:|---:|---:|
| all-OFF (AAA baseline) | `00000` | 0.8561 | 0.4902 | -19.43% |
| + U | `01000` | 0.9625 | 0.6793 | -16.40% |
| + R | `01100` | 1.0743 | 0.7372 | -16.97% |
| + W | `01101` | 1.1481 | 0.8744 | -14.22% |
| + C | `11101` | 1.1785 | 0.9606 | -14.22% |
| + S = all-ON (production) | `11111` | 1.1910 | 1.0615 | -12.67% |

### EXT cumulative path

| step | config (C,U,R,S,W) | Sharpe | Calmar | MaxDD |
|---|---|---:|---:|---:|
| all-OFF (AAA baseline) | `00000` | 1.0336 | 0.5898 | -19.43% |
| + U | `01000` | 1.0624 | 0.7427 | -16.40% |
| + R | `01100` | 1.0980 | 0.6526 | -19.00% |
| + W | `01101` | 1.1368 | 0.7447 | -15.92% |
| + C | `11101` | 1.1772 | 0.8486 | -15.93% |
| + S = all-ON (production) | `11111` | 1.2142 | 0.8608 | -15.93% |

## Caveats / confidence

- all-ON cell reproduces production `cpm_live.compute_target_weights` exactly (param==prod) and the task-specified anchor (clean 1.1910 / -12.67% / 1.0615; ext 1.2142 / -15.93% / 0.8608). Confidence high.
- The screen S is defined coherently with W: S OFF holds the full top-K (partial-safe inactive); S ON holds the positive-trend subset and routes emptied slots to safe. This is the only addition over the 4-factor harness; all other factor definitions are unchanged.
- Grid internally consistent: shared harness, single EXT run sliced per window, identical cost/execution across all 32 cells.
- Main-effect averaging hides structure; read main effects together with the interaction table and the ladder, not in isolation.
- All numbers mooex / T+1 MOO exact / 10 bps/side / no vol gate (CPM has none). EXT 27y is partly proxy-backed pre-2006 for the trend universe; CLEAN 18y has full real-open coverage and is the decisive lens.
