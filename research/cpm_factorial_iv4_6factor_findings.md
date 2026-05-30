# CPM 2^6 factorial -- splitting partial-safe (scale risky exposure by breadth) out of weighting

Role: analyst (read-only re production; no production files changed; no commit). Throwaway harness in `research/`.

Script: `research/cpm_factorial_iv4_6factor.py` -> `research/cpm_factorial_iv4_6factor.json`.

> EXTENDS `research/cpm_factorial_iv4_5factor.py` from 5 factors to 6 by SPLITTING the partial-safe (scale risky exposure by breadth) mechanism (P) out of the weighting factor (W). In the 5-factor harness W=ON did two things at once -- inverse-vol weighting AND strict-4 partial-safe routing. Here W controls only weighting (equal vs inverse-vol over the held set) and the NEW factor P controls partial-safe exposure scaling. Methodology is otherwise identical: shared T+1 MOO exact (mooex) execution, 10 bps/side, cov tail(504), AAA-anchored baseline, same factorial_effects math, CLEAN 18y + EXT 27y. The 5-factor harness is left intact; it is the P==W diagonal of this 6-factor cube.

## Why split partial-safe out of weighting

Inverse-vol weighting and partial-safe exposure scaling are two independent design choices that the 5-factor harness conflated under a single W toggle. Inverse-vol decides HOW the held set is weighted; partial-safe (scale risky exposure by breadth) decides HOW MUCH total risky exposure to take when breadth is thin -- it scales risky exposure to min(positive_count,4)/4 and routes the emptied slots to timed safe. Decomposing P separately exposes the S x P interaction (partial-safe only bites when the positive-trend screen leaves fewer than 4 names held) and the W x P interaction.

## Factor definitions (off = AAA baseline setting / on = production setting)

| factor | OFF (baseline) | ON (production) |
|---|---|---|
| **C** canary | AAA TIP canary (TIP 13612U>0) | HYG-OR-TIP any-positive 13612U gate |
| **U** universe | canonical AAA SPY-set `[SPY,EFA,EEM,VNQ,GLD,TLT,DBC]` | CPM 8-asset `[QQQ,SPHQ,EFA,EEM,VNQ,GLD,TLT,DBC]` |
| **R** ranker | plain 12-month momentum | vol-adjusted Faber (10m-SMA-distance / rv_252d) |
| **S** screen (positive-trend / absolute-momentum filter) | hold all top-K regardless of momentum sign (AAA-style, fully invested in the top-K) | positive-trend screen -- only hold names with positive trend; non-positive slots empty |
| **W** weighting | equal-weight the held set | inverse-vol over the held set |
| **P** partial-safe (scale risky exposure by breadth) | fully invested (risky_fraction = 1) | risky_fraction = min(positive_count,4)/4; remainder routed to timed safe (SHV/IEF) |

**S x P coherence.** The held set = top-K (top-half, ceil(n/2) = 4); breadth = len(held). With S OFF the held set is the full top-K (sign ignored), so breadth = 4 and partial-safe routes nothing (risky_fraction = 1 even when P is ON) -- P is INERT. With S ON the held set is the positive-trend subset, so breadth < 4 is possible and P (when ON) routes the emptied slots (4 - breadth) to safe. Therefore P only bites when breadth < 4 (S on AND fewer than 4 positive-trend names), so a strong S x P interaction is expected. W controls only weighting (equal vs inverse-vol over the held set). Common fixed-on settings (NOT factors): top-half K cap (ceil(n/2) = 4 in both universes), SHV/IEF best-of-safe timed by 13612U, cov lookback tail(504). all-ON (C,U,R,S,W,P = 1,1,1,1,1,1) reproduces production CPM.

## Execution convention (every table below)

Realistic T+1 MOO exact (`mooex`), post-cost 10 bps/side, via the shared `_segment_returns_conv` harness so cost/window/execution are byte-identical across all 64 cells. CPM sleeve has NO vol gate. Windows: CLEAN 18y (2008-05-30 .. 2026-05-22), EXT 27y (1999-03-10 .. 2026-05-22). Full panel runs once over EXT and is sliced to each window.

## Anchor gate -- all-ON cell vs production CPM

Binding gate: all-ON parametric cell == live production `compute_target_weights` (param==prod) in both windows, AND the CLEAN all-ON cell == the task-specified anchor (Sharpe 1.1910 / MaxDD -12.67% / Calmar 1.0615; EXT 1.2142 / -15.93% / 0.8608).

| window | all-ON Sharpe | all-ON MaxDD | all-ON Calmar | production-direct Sharpe | gate target (Sharpe/MaxDD/Calmar) | param==prod | matches anchor |
|---|---:|---:|---:|---:|---|---|---|
| CLEAN | 1.1910 | -12.67% | 1.0615 | 1.1910 | 1.1910/-12.67%/1.0615 | YES | YES |
| EXT | 1.2142 | -15.93% | 0.8608 | 1.2142 | 1.2142/-15.93%/0.8608 | YES | YES |

Gate PASS: the all-ON cell equals live production `cpm_live.compute_target_weights` in both windows and reproduces the task-specified CLEAN anchor EXACTLY. Grid proceeds.

## Full 64-cell grid -- CLEAN (mooex, 10 bps/side)

Config column order: C,U,R,S,W,P.

| C | U | R | S | W | P | Sharpe | CAGR | Vol | MaxDD | Calmar |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 0 | 0 | 0 | 0 | 0 | 0.8561 | 9.52% | 11.46% | -19.43% | 0.4902 |
| 0 | 0 | 0 | 0 | 0 | 1 | 0.8561 | 9.52% | 11.46% | -19.43% | 0.4902 |
| 0 | 0 | 0 | 0 | 1 | 0 | 0.8332 | 8.75% | 10.83% | -17.42% | 0.5020 |
| 0 | 0 | 0 | 0 | 1 | 1 | 0.8332 | 8.75% | 10.83% | -17.42% | 0.5020 |
| 0 | 0 | 0 | 1 | 0 | 0 | 0.7163 | 7.79% | 11.46% | -19.43% | 0.4008 |
| 0 | 0 | 0 | 1 | 0 | 1 | 0.7182 | 7.57% | 11.08% | -19.43% | 0.3894 |
| 0 | 0 | 0 | 1 | 1 | 0 | 0.7130 | 7.47% | 11.03% | -17.42% | 0.4286 |
| 0 | 0 | 0 | 1 | 1 | 1 | 0.7188 | 7.31% | 10.68% | -17.42% | 0.4194 |
| 0 | 0 | 1 | 0 | 0 | 0 | 0.9481 | 10.71% | 11.47% | -18.21% | 0.5880 |
| 0 | 0 | 1 | 0 | 0 | 1 | 0.9481 | 10.71% | 11.47% | -18.21% | 0.5880 |
| 0 | 0 | 1 | 0 | 1 | 0 | 1.0198 | 10.72% | 10.59% | -15.90% | 0.6742 |
| 0 | 0 | 1 | 0 | 1 | 1 | 1.0198 | 10.72% | 10.59% | -15.90% | 0.6742 |
| 0 | 0 | 1 | 1 | 0 | 0 | 0.8996 | 10.02% | 11.38% | -17.34% | 0.5776 |
| 0 | 0 | 1 | 1 | 0 | 1 | 0.9250 | 9.58% | 10.54% | -13.81% | 0.6939 |
| 0 | 0 | 1 | 1 | 1 | 0 | 0.9729 | 10.41% | 10.83% | -13.14% | 0.7921 |
| 0 | 0 | 1 | 1 | 1 | 1 | 1.0026 | 10.06% | 10.12% | -12.81% | 0.7855 |
| 0 | 1 | 0 | 0 | 0 | 0 | 0.9625 | 11.14% | 11.75% | -16.40% | 0.6793 |
| 0 | 1 | 0 | 0 | 0 | 1 | 0.9625 | 11.14% | 11.75% | -16.40% | 0.6793 |
| 0 | 1 | 0 | 0 | 1 | 0 | 0.9833 | 10.73% | 11.04% | -16.37% | 0.6553 |
| 0 | 1 | 0 | 0 | 1 | 1 | 0.9833 | 10.73% | 11.04% | -16.37% | 0.6553 |
| 0 | 1 | 0 | 1 | 0 | 0 | 0.8891 | 10.20% | 11.76% | -16.16% | 0.6308 |
| 0 | 1 | 0 | 1 | 0 | 1 | 0.9113 | 10.20% | 11.44% | -16.16% | 0.6313 |
| 0 | 1 | 0 | 1 | 1 | 0 | 0.8982 | 9.87% | 11.25% | -16.58% | 0.5956 |
| 0 | 1 | 0 | 1 | 1 | 1 | 0.9275 | 9.98% | 10.96% | -16.37% | 0.6093 |
| 0 | 1 | 1 | 0 | 0 | 0 | 1.0743 | 12.51% | 11.65% | -16.97% | 0.7372 |
| 0 | 1 | 1 | 0 | 0 | 1 | 1.0743 | 12.51% | 11.65% | -16.97% | 0.7372 |
| 0 | 1 | 1 | 0 | 1 | 0 | 1.1481 | 12.43% | 10.76% | -14.22% | 0.8744 |
| 0 | 1 | 1 | 0 | 1 | 1 | 1.1481 | 12.43% | 10.76% | -14.22% | 0.8744 |
| 0 | 1 | 1 | 1 | 0 | 0 | 1.0352 | 11.85% | 11.50% | -16.86% | 0.7028 |
| 0 | 1 | 1 | 1 | 0 | 1 | 1.0874 | 11.90% | 10.93% | -13.05% | 0.9118 |
| 0 | 1 | 1 | 1 | 1 | 0 | 1.1043 | 12.07% | 10.90% | -12.67% | 0.9530 |
| 0 | 1 | 1 | 1 | 1 | 1 | 1.1546 | 12.16% | 10.46% | -12.67% | 0.9601 |
| 1 | 0 | 0 | 0 | 0 | 0 | 0.8913 | 10.54% | 12.13% | -19.43% | 0.5425 |
| 1 | 0 | 0 | 0 | 0 | 1 | 0.8913 | 10.54% | 12.13% | -19.43% | 0.5425 |
| 1 | 0 | 0 | 0 | 1 | 0 | 0.8710 | 9.76% | 11.51% | -17.42% | 0.5600 |
| 1 | 0 | 0 | 0 | 1 | 1 | 0.8710 | 9.76% | 11.51% | -17.42% | 0.5600 |
| 1 | 0 | 0 | 1 | 0 | 0 | 0.7693 | 8.93% | 12.14% | -19.43% | 0.4596 |
| 1 | 0 | 0 | 1 | 0 | 1 | 0.7734 | 8.67% | 11.70% | -19.43% | 0.4463 |
| 1 | 0 | 0 | 1 | 1 | 0 | 0.7664 | 8.59% | 11.71% | -17.42% | 0.4929 |
| 1 | 0 | 0 | 1 | 1 | 1 | 0.7750 | 8.40% | 11.30% | -17.42% | 0.4821 |
| 1 | 0 | 1 | 0 | 0 | 0 | 0.9550 | 11.36% | 12.08% | -18.21% | 0.6237 |
| 1 | 0 | 1 | 0 | 0 | 1 | 0.9550 | 11.36% | 12.08% | -18.21% | 0.6237 |
| 1 | 0 | 1 | 0 | 1 | 0 | 1.0195 | 11.35% | 11.21% | -15.90% | 0.7139 |
| 1 | 0 | 1 | 0 | 1 | 1 | 1.0195 | 11.35% | 11.21% | -15.90% | 0.7139 |
| 1 | 0 | 1 | 1 | 0 | 0 | 0.9076 | 10.66% | 12.01% | -17.34% | 0.6150 |
| 1 | 0 | 1 | 1 | 0 | 1 | 0.9406 | 10.17% | 10.99% | -13.81% | 0.7365 |
| 1 | 0 | 1 | 1 | 1 | 0 | 0.9758 | 11.05% | 11.46% | -16.35% | 0.6756 |
| 1 | 0 | 1 | 1 | 1 | 1 | 1.0122 | 10.62% | 10.57% | -11.75% | 0.9035 |
| 1 | 1 | 0 | 0 | 0 | 0 | 1.0230 | 12.63% | 12.44% | -16.40% | 0.7704 |
| 1 | 1 | 0 | 0 | 0 | 1 | 1.0230 | 12.63% | 12.44% | -16.40% | 0.7704 |
| 1 | 1 | 0 | 0 | 1 | 0 | 1.0367 | 12.11% | 11.75% | -16.37% | 0.7397 |
| 1 | 1 | 0 | 0 | 1 | 1 | 1.0367 | 12.11% | 11.75% | -16.37% | 0.7397 |
| 1 | 1 | 0 | 1 | 0 | 0 | 0.9479 | 11.61% | 12.47% | -16.16% | 0.7182 |
| 1 | 1 | 0 | 1 | 0 | 1 | 0.9817 | 11.77% | 12.14% | -16.16% | 0.7281 |
| 1 | 1 | 0 | 1 | 1 | 0 | 0.9504 | 11.17% | 11.96% | -16.58% | 0.6741 |
| 1 | 1 | 0 | 1 | 1 | 1 | 0.9916 | 11.43% | 11.66% | -16.37% | 0.6983 |
| 1 | 1 | 1 | 0 | 0 | 0 | 1.1148 | 13.81% | 12.33% | -16.97% | 0.8138 |
| 1 | 1 | 1 | 0 | 0 | 1 | 1.1148 | 13.81% | 12.33% | -16.97% | 0.8138 |
| 1 | 1 | 1 | 0 | 1 | 0 | 1.1785 | 13.66% | 11.47% | -14.22% | 0.9606 |
| 1 | 1 | 1 | 0 | 1 | 1 | 1.1785 | 13.66% | 11.47% | -14.22% | 0.9606 |
| 1 | 1 | 1 | 1 | 0 | 0 | 1.0875 | 13.28% | 12.20% | -16.86% | 0.7878 |
| 1 | 1 | 1 | 1 | 0 | 1 | 1.1317 | 13.24% | 11.63% | -13.05% | 1.0147 |
| 1 | 1 | 1 | 1 | 1 | 0 | 1.1491 | 13.44% | 11.61% | -12.67% | 1.0614 |
| 1 | 1 | 1 | 1 | 1 | 1 | **1.1910** | 13.44% | 11.16% | **-12.67%** | **1.0615** |

## Full 64-cell grid -- EXT (mooex, 10 bps/side)

Config column order: C,U,R,S,W,P.

| C | U | R | S | W | P | Sharpe | CAGR | Vol | MaxDD | Calmar |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 0 | 0 | 0 | 0 | 0 | 1.0336 | 11.46% | 11.09% | -19.43% | 0.5898 |
| 0 | 0 | 0 | 0 | 0 | 1 | 1.0336 | 11.46% | 11.09% | -19.43% | 0.5898 |
| 0 | 0 | 0 | 0 | 1 | 0 | 1.0259 | 10.72% | 10.46% | -17.42% | 0.6150 |
| 0 | 0 | 0 | 0 | 1 | 1 | 1.0259 | 10.72% | 10.46% | -17.42% | 0.6150 |
| 0 | 0 | 0 | 1 | 0 | 0 | 0.9245 | 10.12% | 11.10% | -19.43% | 0.5211 |
| 0 | 0 | 0 | 1 | 0 | 1 | 0.9411 | 10.07% | 10.82% | -19.43% | 0.5186 |
| 0 | 0 | 0 | 1 | 1 | 0 | 0.9295 | 9.74% | 10.60% | -17.42% | 0.5590 |
| 0 | 0 | 0 | 1 | 1 | 1 | 0.9471 | 9.71% | 10.35% | -17.42% | 0.5572 |
| 0 | 0 | 1 | 0 | 0 | 0 | 1.0195 | 11.14% | 10.95% | -18.48% | 0.6026 |
| 0 | 0 | 1 | 0 | 0 | 1 | 1.0195 | 11.14% | 10.95% | -18.48% | 0.6026 |
| 0 | 0 | 1 | 0 | 1 | 0 | 1.0714 | 10.85% | 10.09% | -15.90% | 0.6823 |
| 0 | 0 | 1 | 0 | 1 | 1 | 1.0714 | 10.85% | 10.09% | -15.90% | 0.6823 |
| 0 | 0 | 1 | 1 | 0 | 0 | 0.9994 | 10.90% | 10.95% | -20.87% | 0.5219 |
| 0 | 0 | 1 | 1 | 0 | 1 | 1.0332 | 10.62% | 10.28% | -16.46% | 0.6452 |
| 0 | 0 | 1 | 1 | 1 | 0 | 1.0397 | 10.75% | 10.34% | -15.06% | 0.7139 |
| 0 | 0 | 1 | 1 | 1 | 1 | 1.0731 | 10.55% | 9.79% | -13.45% | 0.7839 |
| 0 | 1 | 0 | 0 | 0 | 0 | 1.0624 | 12.18% | 11.44% | -16.40% | 0.7427 |
| 0 | 1 | 0 | 0 | 0 | 1 | 1.0624 | 12.18% | 11.44% | -16.40% | 0.7427 |
| 0 | 1 | 0 | 0 | 1 | 0 | 1.0734 | 11.59% | 10.76% | -16.37% | 0.7080 |
| 0 | 1 | 0 | 0 | 1 | 1 | 1.0734 | 11.59% | 10.76% | -16.37% | 0.7080 |
| 0 | 1 | 0 | 1 | 0 | 0 | 0.9992 | 11.38% | 11.45% | -16.16% | 0.7043 |
| 0 | 1 | 0 | 1 | 0 | 1 | 1.0263 | 11.49% | 11.21% | -16.16% | 0.7109 |
| 0 | 1 | 0 | 1 | 1 | 0 | 1.0031 | 10.91% | 10.91% | -16.58% | 0.6579 |
| 0 | 1 | 0 | 1 | 1 | 1 | 1.0331 | 11.05% | 10.70% | -16.37% | 0.6750 |
| 0 | 1 | 1 | 0 | 0 | 0 | 1.0980 | 12.40% | 11.22% | -19.00% | 0.6526 |
| 0 | 1 | 1 | 0 | 0 | 1 | 1.0980 | 12.40% | 11.22% | -19.00% | 0.6526 |
| 0 | 1 | 1 | 0 | 1 | 0 | 1.1368 | 11.86% | 10.32% | -15.92% | 0.7447 |
| 0 | 1 | 1 | 0 | 1 | 1 | 1.1368 | 11.86% | 10.32% | -15.92% | 0.7447 |
| 0 | 1 | 1 | 1 | 0 | 0 | 1.0926 | 12.21% | 11.11% | -20.18% | 0.6047 |
| 0 | 1 | 1 | 1 | 0 | 1 | 1.1331 | 12.17% | 10.64% | -15.73% | 0.7738 |
| 0 | 1 | 1 | 1 | 1 | 0 | 1.1198 | 11.82% | 10.47% | -15.09% | 0.7835 |
| 0 | 1 | 1 | 1 | 1 | 1 | 1.1575 | 11.84% | 10.11% | -13.38% | 0.8855 |
| 1 | 0 | 0 | 0 | 0 | 0 | 0.9945 | 11.95% | 12.09% | -19.43% | 0.6152 |
| 1 | 0 | 0 | 0 | 0 | 1 | 1.0111 | 12.13% | 12.05% | -19.43% | 0.6245 |
| 1 | 0 | 0 | 0 | 1 | 0 | 0.9958 | 11.34% | 11.45% | -17.98% | 0.6308 |
| 1 | 0 | 0 | 0 | 1 | 1 | 1.0135 | 11.52% | 11.40% | -17.98% | 0.6408 |
| 1 | 0 | 0 | 1 | 0 | 0 | 0.9447 | 11.24% | 12.04% | -19.43% | 0.5784 |
| 1 | 0 | 0 | 1 | 0 | 1 | 0.9575 | 11.10% | 11.71% | -19.43% | 0.5713 |
| 1 | 0 | 0 | 1 | 1 | 0 | 0.9518 | 10.87% | 11.54% | -17.98% | 0.6046 |
| 1 | 0 | 0 | 1 | 1 | 1 | 0.9655 | 10.76% | 11.24% | -17.98% | 0.5982 |
| 1 | 0 | 1 | 0 | 0 | 0 | 1.0082 | 11.82% | 11.77% | -18.48% | 0.6396 |
| 1 | 0 | 1 | 0 | 0 | 1 | 1.0254 | 12.00% | 11.73% | -18.48% | 0.6493 |
| 1 | 0 | 1 | 0 | 1 | 0 | 1.0613 | 11.61% | 10.91% | -15.90% | 0.7299 |
| 1 | 0 | 1 | 0 | 1 | 1 | 1.0804 | 11.79% | 10.86% | -15.90% | 0.7412 |
| 1 | 0 | 1 | 1 | 0 | 0 | 1.0240 | 11.98% | 11.72% | -20.87% | 0.5739 |
| 1 | 0 | 1 | 1 | 0 | 1 | 1.0600 | 11.61% | 10.93% | -16.46% | 0.7058 |
| 1 | 0 | 1 | 1 | 1 | 0 | 1.0635 | 11.84% | 11.10% | -16.35% | 0.7239 |
| 1 | 0 | 1 | 1 | 1 | 1 | 1.0993 | 11.53% | 10.42% | -13.45% | 0.8573 |
| 1 | 1 | 0 | 0 | 0 | 0 | 1.0459 | 13.36% | 12.77% | -17.88% | 0.7474 |
| 1 | 1 | 0 | 0 | 0 | 1 | 1.0616 | 13.54% | 12.73% | -17.88% | 0.7576 |
| 1 | 1 | 0 | 0 | 1 | 0 | 1.0639 | 12.76% | 11.96% | -17.98% | 0.7095 |
| 1 | 1 | 0 | 0 | 1 | 1 | 1.0810 | 12.94% | 11.91% | -17.98% | 0.7196 |
| 1 | 1 | 0 | 1 | 0 | 0 | 1.0234 | 12.99% | 12.73% | -17.88% | 0.7267 |
| 1 | 1 | 0 | 1 | 0 | 1 | 1.0504 | 13.13% | 12.49% | -17.88% | 0.7345 |
| 1 | 1 | 0 | 1 | 1 | 0 | 1.0300 | 12.40% | 12.05% | -17.98% | 0.6894 |
| 1 | 1 | 0 | 1 | 1 | 1 | 1.0600 | 12.58% | 11.84% | -17.98% | 0.6994 |
| 1 | 1 | 1 | 0 | 0 | 0 | 1.1175 | 13.90% | 12.33% | -19.00% | 0.7320 |
| 1 | 1 | 1 | 0 | 0 | 1 | 1.1341 | 14.09% | 12.29% | -19.00% | 0.7416 |
| 1 | 1 | 1 | 0 | 1 | 0 | 1.1586 | 13.33% | 11.36% | -15.93% | 0.8372 |
| 1 | 1 | 1 | 0 | 1 | 1 | 1.1772 | 13.52% | 11.32% | -15.93% | 0.8486 |
| 1 | 1 | 1 | 1 | 0 | 0 | 1.1567 | 14.27% | 12.17% | -20.18% | 0.7069 |
| 1 | 1 | 1 | 1 | 0 | 1 | 1.1868 | 14.13% | 11.72% | -16.21% | 0.8718 |
| 1 | 1 | 1 | 1 | 1 | 0 | 1.1857 | 13.78% | 11.44% | -15.93% | 0.8651 |
| 1 | 1 | 1 | 1 | 1 | 1 | **1.2142** | 13.71% | 11.09% | **-15.93%** | **0.8608** |

## Main effects (background-averaged, coded +-1; effect = mean|on - mean|off)

Sign-flip flag = factor's on-minus-off delta changes sign across backgrounds (direction not robust).

### CLEAN

| factor | dSharpe | flip | dCalmar | flip |
|---|---:|---|---:|---|
| **R** | +0.1603 | | +0.2038 | |
| **U** | +0.1596 | | +0.2035 | |
| **C** | +0.0377 | SIGN-FLIP | +0.0663 | SIGN-FLIP |
| **W** | +0.0347 | SIGN-FLIP | +0.0631 | SIGN-FLIP |
| **P** | +0.0144 | | +0.0283 | SIGN-FLIP |
| **S** | -0.0564 | SIGN-FLIP | +0.0058 | SIGN-FLIP |

### EXT

| factor | dSharpe | flip | dCalmar | flip |
|---|---:|---|---:|---|
| **U** | +0.0815 | | +0.1080 | |
| **R** | +0.0815 | SIGN-FLIP | +0.0718 | SIGN-FLIP |
| **W** | +0.0232 | SIGN-FLIP | +0.0537 | SIGN-FLIP |
| **C** | +0.0159 | SIGN-FLIP | +0.0450 | SIGN-FLIP |
| **P** | +0.0184 | | +0.0311 | SIGN-FLIP |
| **S** | -0.0202 | SIGN-FLIP | -0.0017 | SIGN-FLIP |

## Two-way interactions

Calmar (both windows), sorted by |CLEAN|:

| interaction | CLEAN | EXT |
|---|---:|---:|
| RxS | +0.0730 | +0.0389 |
| RxW | +0.0665 | +0.0593 |
| SxP | +0.0283 | +0.0260 |
| RxP | +0.0281 | +0.0272 |
| CxU | +0.0228 | +0.0022 |
| WxP | -0.0129 | -0.0084 |
| UxS | +0.0115 | +0.0118 |
| SxW | +0.0087 | +0.0116 |
| CxP | +0.0083 | +0.0009 |
| CxR | -0.0066 | +0.0180 |
| UxW | -0.0039 | -0.0204 |
| UxP | +0.0024 | +0.0010 |
| CxW | -0.0012 | -0.0050 |
| CxS | +0.0008 | +0.0019 |
| UxR | -0.0007 | -0.0173 |

Sharpe (both windows), sorted by |CLEAN|:

| interaction | CLEAN | EXT |
|---|---:|---:|
| RxS | +0.0352 | +0.0342 |
| RxW | +0.0337 | +0.0169 |
| UxS | +0.0187 | +0.0134 |
| CxR | -0.0146 | +0.0124 |
| SxP | +0.0144 | +0.0098 |
| CxU | +0.0119 | +0.0117 |
| UxR | -0.0064 | +0.0156 |
| UxP | +0.0053 | +0.0015 |
| UxW | +0.0052 | -0.0009 |
| RxP | +0.0052 | +0.0033 |
| CxS | +0.0046 | +0.0166 |
| CxW | -0.0025 | +0.0018 |
| SxW | +0.0016 | -0.0032 |
| CxP | +0.0008 | +0.0036 |
| WxP | +0.0008 | +0.0003 |

### Key requested interactions

| interaction | meaning | CLEAN Calmar | EXT Calmar | CLEAN Sharpe | EXT Sharpe |
|---|---|---:|---:|---:|---:|
| SxP | positive-trend screen vs partial-safe (P bites only when S thins breadth < 4) | +0.0283 | +0.0260 | +0.0144 | +0.0098 |
| WxP | inverse-vol weighting vs partial-safe exposure scaling | -0.0129 | -0.0084 | +0.0008 | +0.0003 |
| SxW | screen vs weighting | +0.0087 | +0.0116 | +0.0016 | -0.0032 |
| RxW | ranker vs weighting | +0.0665 | +0.0593 | +0.0337 | +0.0169 |
| CxS | canary risk-off vs absolute screen (overlap) | +0.0008 | +0.0019 | +0.0046 | +0.0166 |
| RxS | ranker vs screen | +0.0730 | +0.0389 | +0.0352 | +0.0342 |
| CxP | canary vs partial-safe | +0.0083 | +0.0009 | +0.0008 | +0.0036 |
| RxP | ranker vs partial-safe | +0.0281 | +0.0272 | +0.0052 | +0.0033 |
| UxP | universe vs partial-safe | +0.0024 | +0.0010 | +0.0053 | +0.0015 |

## Derived contribution ladder (best ordered cumulative path)

Ordering = factors by CLEAN Calmar main effect, largest first, value-subtractors last: **R -> U -> C -> W -> P -> S**.

### CLEAN cumulative path

| step | config (C,U,R,S,W,P) | Sharpe | Calmar | MaxDD |
|---|---|---:|---:|---:|
| all-OFF (AAA baseline) | `000000` | 0.8561 | 0.4902 | -19.43% |
| + R | `001000` | 0.9481 | 0.5880 | -18.21% |
| + U | `011000` | 1.0743 | 0.7372 | -16.97% |
| + C | `111000` | 1.1148 | 0.8138 | -16.97% |
| + W | `111010` | 1.1785 | 0.9606 | -14.22% |
| + P | `111011` | 1.1785 | 0.9606 | -14.22% |
| + S = all-ON (production) | `111111` | 1.1910 | 1.0615 | -12.67% |

### EXT cumulative path

| step | config (C,U,R,S,W,P) | Sharpe | Calmar | MaxDD |
|---|---|---:|---:|---:|
| all-OFF (AAA baseline) | `000000` | 1.0336 | 0.5898 | -19.43% |
| + R | `001000` | 1.0195 | 0.6026 | -18.48% |
| + U | `011000` | 1.0980 | 0.6526 | -19.00% |
| + C | `111000` | 1.1175 | 0.7320 | -19.00% |
| + W | `111010` | 1.1586 | 0.8372 | -15.93% |
| + P | `111011` | 1.1772 | 0.8486 | -15.93% |
| + S = all-ON (production) | `111111` | 1.2142 | 0.8608 | -15.93% |

## Caveats / confidence

- all-ON cell reproduces production `cpm_live.compute_target_weights` exactly (param==prod) and the task-specified anchor (clean 1.1910 / -12.67% / 1.0615; ext 1.2142 / -15.93% / 0.8608). Confidence high.
- P (partial-safe: scale risky exposure by breadth) is defined coherently with S and W: with S OFF breadth == 4 so P is inert (risky_fraction == 1); with S ON the emptied slots route to safe at risky_fraction = min(breadth,4)/4. W controls only weighting (equal vs inverse-vol). all-ON (W=1,P=1) equals the 5-factor all-ON; the 5-factor cube is the P==W diagonal of this 6-factor cube.
- Grid internally consistent: shared harness, single EXT run sliced per window, identical cost/execution across all 64 cells.
- Main-effect averaging hides structure; read main effects together with the interaction table (especially S x P and W x P) and the ladder, not in isolation. The P main effect is diluted because P is inert across the entire S-OFF half of the cube.
- All numbers mooex / T+1 MOO exact / 10 bps/side / no vol gate (CPM has none). EXT 27y is partly proxy-backed pre-2006 for the trend universe; CLEAN 18y has full real-open coverage and is the decisive lens.
