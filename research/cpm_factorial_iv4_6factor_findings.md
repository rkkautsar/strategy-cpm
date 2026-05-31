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
| CLEAN | 1.1658 | -12.97% | 1.0137 | 1.1658 | 1.1910/-12.67%/1.0615 | YES | NO |
| EXT | 1.2004 | -15.73% | 0.8571 | 1.2004 | 1.2142/-15.93%/0.8608 | YES | NO |

**GATE FAIL**: the all-ON cell does NOT reproduce live production / the anchor. Numbers below are FLAGGED and should not be trusted until reconciled.

## Full 64-cell grid -- CLEAN (mooex, 10 bps/side)

Config column order: C,U,R,S,W,P.

| C | U | R | S | W | P | Sharpe | CAGR | Vol | MaxDD | Calmar |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 0 | 0 | 0 | 0 | 0 | 0.8561 | 9.52% | 11.46% | -19.43% | 0.4902 |
| 0 | 0 | 0 | 0 | 0 | 1 | 0.8561 | 9.52% | 11.46% | -19.43% | 0.4902 |
| 0 | 0 | 0 | 0 | 1 | 0 | 0.8093 | 8.56% | 10.96% | -18.95% | 0.4520 |
| 0 | 0 | 0 | 0 | 1 | 1 | 0.8093 | 8.56% | 10.96% | -18.95% | 0.4520 |
| 0 | 0 | 0 | 1 | 0 | 0 | 0.7163 | 7.79% | 11.46% | -19.43% | 0.4008 |
| 0 | 0 | 0 | 1 | 0 | 1 | 0.7182 | 7.57% | 11.08% | -19.43% | 0.3894 |
| 0 | 0 | 0 | 1 | 1 | 0 | 0.6962 | 7.35% | 11.16% | -18.95% | 0.3879 |
| 0 | 0 | 0 | 1 | 1 | 1 | 0.7007 | 7.18% | 10.81% | -18.95% | 0.3791 |
| 0 | 0 | 1 | 0 | 0 | 0 | 0.9481 | 10.71% | 11.47% | -18.21% | 0.5880 |
| 0 | 0 | 1 | 0 | 0 | 1 | 0.9481 | 10.71% | 11.47% | -18.21% | 0.5880 |
| 0 | 0 | 1 | 0 | 1 | 0 | 0.9825 | 10.38% | 10.68% | -17.59% | 0.5900 |
| 0 | 0 | 1 | 0 | 1 | 1 | 0.9825 | 10.38% | 10.68% | -17.59% | 0.5900 |
| 0 | 0 | 1 | 1 | 0 | 0 | 0.8996 | 10.02% | 11.38% | -17.34% | 0.5776 |
| 0 | 0 | 1 | 1 | 0 | 1 | 0.9250 | 9.58% | 10.54% | -13.81% | 0.6939 |
| 0 | 0 | 1 | 1 | 1 | 0 | 0.9479 | 10.13% | 10.85% | -13.18% | 0.7685 |
| 0 | 0 | 1 | 1 | 1 | 1 | 0.9765 | 9.80% | 10.15% | -13.12% | 0.7473 |
| 0 | 1 | 0 | 0 | 0 | 0 | 0.9625 | 11.14% | 11.75% | -16.40% | 0.6793 |
| 0 | 1 | 0 | 0 | 0 | 1 | 0.9625 | 11.14% | 11.75% | -16.40% | 0.6793 |
| 0 | 1 | 0 | 0 | 1 | 0 | 0.9508 | 10.46% | 11.18% | -16.46% | 0.6356 |
| 0 | 1 | 0 | 0 | 1 | 1 | 0.9508 | 10.46% | 11.18% | -16.46% | 0.6356 |
| 0 | 1 | 0 | 1 | 0 | 0 | 0.8891 | 10.20% | 11.76% | -16.16% | 0.6308 |
| 0 | 1 | 0 | 1 | 0 | 1 | 0.9113 | 10.20% | 11.44% | -16.16% | 0.6313 |
| 0 | 1 | 0 | 1 | 1 | 0 | 0.8697 | 9.64% | 11.39% | -16.68% | 0.5778 |
| 0 | 1 | 0 | 1 | 1 | 1 | 0.8987 | 9.75% | 11.10% | -16.46% | 0.5923 |
| 0 | 1 | 1 | 0 | 0 | 0 | 1.0743 | 12.51% | 11.65% | -16.97% | 0.7372 |
| 0 | 1 | 1 | 0 | 0 | 1 | 1.0743 | 12.51% | 11.65% | -16.97% | 0.7372 |
| 0 | 1 | 1 | 0 | 1 | 0 | 1.1143 | 12.12% | 10.84% | -15.38% | 0.7885 |
| 0 | 1 | 1 | 0 | 1 | 1 | 1.1143 | 12.12% | 10.84% | -15.38% | 0.7885 |
| 0 | 1 | 1 | 1 | 0 | 0 | 1.0352 | 11.85% | 11.50% | -16.86% | 0.7028 |
| 0 | 1 | 1 | 1 | 0 | 1 | 1.0874 | 11.90% | 10.93% | -13.05% | 0.9118 |
| 0 | 1 | 1 | 1 | 1 | 0 | 1.0775 | 11.77% | 10.93% | -13.18% | 0.8934 |
| 0 | 1 | 1 | 1 | 1 | 1 | 1.1290 | 11.89% | 10.48% | -12.97% | 0.9166 |
| 1 | 0 | 0 | 0 | 0 | 0 | 0.8913 | 10.54% | 12.13% | -19.43% | 0.5425 |
| 1 | 0 | 0 | 0 | 0 | 1 | 0.8913 | 10.54% | 12.13% | -19.43% | 0.5425 |
| 1 | 0 | 0 | 0 | 1 | 0 | 0.8459 | 9.54% | 11.64% | -18.95% | 0.5034 |
| 1 | 0 | 0 | 0 | 1 | 1 | 0.8459 | 9.54% | 11.64% | -18.95% | 0.5034 |
| 1 | 0 | 0 | 1 | 0 | 0 | 0.7693 | 8.93% | 12.14% | -19.43% | 0.4596 |
| 1 | 0 | 0 | 1 | 0 | 1 | 0.7734 | 8.67% | 11.70% | -19.43% | 0.4463 |
| 1 | 0 | 0 | 1 | 1 | 0 | 0.7471 | 8.43% | 11.84% | -18.95% | 0.4447 |
| 1 | 0 | 0 | 1 | 1 | 1 | 0.7548 | 8.24% | 11.42% | -18.95% | 0.4347 |
| 1 | 0 | 1 | 0 | 0 | 0 | 0.9550 | 11.36% | 12.08% | -18.21% | 0.6237 |
| 1 | 0 | 1 | 0 | 0 | 1 | 0.9550 | 11.36% | 12.08% | -18.21% | 0.6237 |
| 1 | 0 | 1 | 0 | 1 | 0 | 0.9869 | 11.03% | 11.30% | -17.59% | 0.6271 |
| 1 | 0 | 1 | 0 | 1 | 1 | 0.9869 | 11.03% | 11.30% | -17.59% | 0.6271 |
| 1 | 0 | 1 | 1 | 0 | 0 | 0.9076 | 10.66% | 12.01% | -17.34% | 0.6150 |
| 1 | 0 | 1 | 1 | 0 | 1 | 0.9406 | 10.17% | 10.99% | -13.81% | 0.7365 |
| 1 | 0 | 1 | 1 | 1 | 0 | 0.9521 | 10.77% | 11.49% | -16.29% | 0.6612 |
| 1 | 0 | 1 | 1 | 1 | 1 | 0.9884 | 10.37% | 10.60% | -11.98% | 0.8652 |
| 1 | 1 | 0 | 0 | 0 | 0 | 1.0230 | 12.63% | 12.44% | -16.40% | 0.7704 |
| 1 | 1 | 0 | 0 | 0 | 1 | 1.0230 | 12.63% | 12.44% | -16.40% | 0.7704 |
| 1 | 1 | 0 | 0 | 1 | 0 | 1.0052 | 11.82% | 11.88% | -16.46% | 0.7184 |
| 1 | 1 | 0 | 0 | 1 | 1 | 1.0052 | 11.82% | 11.88% | -16.46% | 0.7184 |
| 1 | 1 | 0 | 1 | 0 | 0 | 0.9479 | 11.61% | 12.47% | -16.16% | 0.7182 |
| 1 | 1 | 0 | 1 | 0 | 1 | 0.9817 | 11.77% | 12.14% | -16.16% | 0.7281 |
| 1 | 1 | 0 | 1 | 1 | 0 | 0.9229 | 10.92% | 12.09% | -16.68% | 0.6549 |
| 1 | 1 | 0 | 1 | 1 | 1 | 0.9638 | 11.19% | 11.79% | -16.46% | 0.6801 |
| 1 | 1 | 1 | 0 | 0 | 0 | 1.1148 | 13.81% | 12.33% | -16.97% | 0.8138 |
| 1 | 1 | 1 | 0 | 0 | 1 | 1.1148 | 13.81% | 12.33% | -16.97% | 0.8138 |
| 1 | 1 | 1 | 0 | 1 | 0 | 1.1465 | 13.33% | 11.54% | -15.38% | 0.8669 |
| 1 | 1 | 1 | 0 | 1 | 1 | 1.1465 | 13.33% | 11.54% | -15.38% | 0.8669 |
| 1 | 1 | 1 | 1 | 0 | 0 | 1.0875 | 13.28% | 12.20% | -16.86% | 0.7878 |
| 1 | 1 | 1 | 1 | 0 | 1 | 1.1317 | 13.24% | 11.63% | -13.05% | 1.0147 |
| 1 | 1 | 1 | 1 | 1 | 0 | 1.1227 | 13.12% | 11.63% | -13.18% | 0.9955 |
| 1 | 1 | 1 | 1 | 1 | 1 | **1.1658** | 13.15% | 11.18% | **-12.97%** | **1.0137** |

## Full 64-cell grid -- EXT (mooex, 10 bps/side)

Config column order: C,U,R,S,W,P.

| C | U | R | S | W | P | Sharpe | CAGR | Vol | MaxDD | Calmar |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 0 | 0 | 0 | 0 | 0 | 1.0336 | 11.46% | 11.09% | -19.43% | 0.5898 |
| 0 | 0 | 0 | 0 | 0 | 1 | 1.0336 | 11.46% | 11.09% | -19.43% | 0.5898 |
| 0 | 0 | 0 | 0 | 1 | 0 | 1.0126 | 10.66% | 10.56% | -18.95% | 0.5627 |
| 0 | 0 | 0 | 0 | 1 | 1 | 1.0126 | 10.66% | 10.56% | -18.95% | 0.5627 |
| 0 | 0 | 0 | 1 | 0 | 0 | 0.9245 | 10.12% | 11.10% | -19.43% | 0.5211 |
| 0 | 0 | 0 | 1 | 0 | 1 | 0.9411 | 10.07% | 10.82% | -19.43% | 0.5186 |
| 0 | 0 | 0 | 1 | 1 | 0 | 0.9201 | 9.72% | 10.70% | -18.95% | 0.5129 |
| 0 | 0 | 0 | 1 | 1 | 1 | 0.9366 | 9.68% | 10.45% | -18.95% | 0.5109 |
| 0 | 0 | 1 | 0 | 0 | 0 | 1.0195 | 11.14% | 10.95% | -18.48% | 0.6026 |
| 0 | 0 | 1 | 0 | 0 | 1 | 1.0195 | 11.14% | 10.95% | -18.48% | 0.6026 |
| 0 | 0 | 1 | 0 | 1 | 0 | 1.0514 | 10.69% | 10.15% | -17.59% | 0.6079 |
| 0 | 0 | 1 | 0 | 1 | 1 | 1.0514 | 10.69% | 10.15% | -17.59% | 0.6079 |
| 0 | 0 | 1 | 1 | 0 | 0 | 0.9994 | 10.90% | 10.95% | -20.87% | 0.5219 |
| 0 | 0 | 1 | 1 | 0 | 1 | 1.0332 | 10.62% | 10.28% | -16.46% | 0.6452 |
| 0 | 0 | 1 | 1 | 1 | 0 | 1.0261 | 10.61% | 10.35% | -15.13% | 0.7011 |
| 0 | 0 | 1 | 1 | 1 | 1 | 1.0600 | 10.41% | 9.80% | -13.34% | 0.7809 |
| 0 | 1 | 0 | 0 | 0 | 0 | 1.0624 | 12.18% | 11.44% | -16.40% | 0.7427 |
| 0 | 1 | 0 | 0 | 0 | 1 | 1.0624 | 12.18% | 11.44% | -16.40% | 0.7427 |
| 0 | 1 | 0 | 0 | 1 | 0 | 1.0544 | 11.47% | 10.86% | -16.46% | 0.6970 |
| 0 | 1 | 0 | 0 | 1 | 1 | 1.0544 | 11.47% | 10.86% | -16.46% | 0.6970 |
| 0 | 1 | 0 | 1 | 0 | 0 | 0.9992 | 11.38% | 11.45% | -16.16% | 0.7043 |
| 0 | 1 | 0 | 1 | 0 | 1 | 1.0263 | 11.49% | 11.21% | -16.16% | 0.7109 |
| 0 | 1 | 0 | 1 | 1 | 0 | 0.9859 | 10.80% | 11.01% | -16.68% | 0.6473 |
| 0 | 1 | 0 | 1 | 1 | 1 | 1.0158 | 10.95% | 10.80% | -16.46% | 0.6651 |
| 0 | 1 | 1 | 0 | 0 | 0 | 1.0980 | 12.40% | 11.22% | -19.00% | 0.6526 |
| 0 | 1 | 1 | 0 | 0 | 1 | 1.0980 | 12.40% | 11.22% | -19.00% | 0.6526 |
| 0 | 1 | 1 | 0 | 1 | 0 | 1.1209 | 11.74% | 10.38% | -16.02% | 0.7323 |
| 0 | 1 | 1 | 0 | 1 | 1 | 1.1209 | 11.74% | 10.38% | -16.02% | 0.7323 |
| 0 | 1 | 1 | 1 | 0 | 0 | 1.0926 | 12.21% | 11.11% | -20.18% | 0.6047 |
| 0 | 1 | 1 | 1 | 0 | 1 | 1.1331 | 12.17% | 10.64% | -15.73% | 0.7738 |
| 0 | 1 | 1 | 1 | 1 | 0 | 1.1050 | 11.67% | 10.48% | -15.38% | 0.7587 |
| 0 | 1 | 1 | 1 | 1 | 1 | 1.1444 | 11.70% | 10.12% | -13.23% | 0.8844 |
| 1 | 0 | 0 | 0 | 0 | 0 | 0.9945 | 11.95% | 12.09% | -19.43% | 0.6152 |
| 1 | 0 | 0 | 0 | 0 | 1 | 1.0111 | 12.13% | 12.05% | -19.43% | 0.6245 |
| 1 | 0 | 0 | 0 | 1 | 0 | 0.9809 | 11.23% | 11.53% | -18.95% | 0.5928 |
| 1 | 0 | 0 | 0 | 1 | 1 | 0.9983 | 11.41% | 11.49% | -18.95% | 0.6023 |
| 1 | 0 | 0 | 1 | 0 | 0 | 0.9447 | 11.24% | 12.04% | -19.43% | 0.5784 |
| 1 | 0 | 0 | 1 | 0 | 1 | 0.9575 | 11.10% | 11.71% | -19.43% | 0.5713 |
| 1 | 0 | 0 | 1 | 1 | 0 | 0.9391 | 10.79% | 11.63% | -18.95% | 0.5691 |
| 1 | 0 | 0 | 1 | 1 | 1 | 0.9526 | 10.68% | 11.32% | -18.95% | 0.5633 |
| 1 | 0 | 1 | 0 | 0 | 0 | 1.0082 | 11.82% | 11.77% | -18.48% | 0.6396 |
| 1 | 0 | 1 | 0 | 0 | 1 | 1.0254 | 12.00% | 11.73% | -18.48% | 0.6493 |
| 1 | 0 | 1 | 0 | 1 | 0 | 1.0475 | 11.50% | 10.97% | -17.59% | 0.6538 |
| 1 | 0 | 1 | 0 | 1 | 1 | 1.0664 | 11.68% | 10.92% | -17.59% | 0.6640 |
| 1 | 0 | 1 | 1 | 0 | 0 | 1.0240 | 11.98% | 11.72% | -20.87% | 0.5739 |
| 1 | 0 | 1 | 1 | 0 | 1 | 1.0600 | 11.61% | 10.93% | -16.46% | 0.7058 |
| 1 | 0 | 1 | 1 | 1 | 0 | 1.0537 | 11.73% | 11.11% | -16.29% | 0.7201 |
| 1 | 0 | 1 | 1 | 1 | 1 | 1.0910 | 11.44% | 10.43% | -13.34% | 0.8581 |
| 1 | 1 | 0 | 0 | 0 | 0 | 1.0459 | 13.36% | 12.77% | -17.88% | 0.7474 |
| 1 | 1 | 0 | 0 | 0 | 1 | 1.0616 | 13.54% | 12.73% | -17.88% | 0.7576 |
| 1 | 1 | 0 | 0 | 1 | 0 | 1.0469 | 12.56% | 11.99% | -17.78% | 0.7063 |
| 1 | 1 | 0 | 0 | 1 | 1 | 1.0638 | 12.74% | 11.94% | -17.78% | 0.7165 |
| 1 | 1 | 0 | 1 | 0 | 0 | 1.0234 | 12.99% | 12.73% | -17.88% | 0.7267 |
| 1 | 1 | 0 | 1 | 0 | 1 | 1.0504 | 13.13% | 12.49% | -17.88% | 0.7345 |
| 1 | 1 | 0 | 1 | 1 | 0 | 1.0126 | 12.19% | 12.08% | -17.78% | 0.6856 |
| 1 | 1 | 0 | 1 | 1 | 1 | 1.0429 | 12.37% | 11.86% | -17.78% | 0.6961 |
| 1 | 1 | 1 | 0 | 0 | 0 | 1.1175 | 13.90% | 12.33% | -19.00% | 0.7320 |
| 1 | 1 | 1 | 0 | 0 | 1 | 1.1341 | 14.09% | 12.29% | -19.00% | 0.7416 |
| 1 | 1 | 1 | 0 | 1 | 0 | 1.1428 | 13.14% | 11.37% | -16.02% | 0.8198 |
| 1 | 1 | 1 | 0 | 1 | 1 | 1.1613 | 13.32% | 11.32% | -16.02% | 0.8311 |
| 1 | 1 | 1 | 1 | 0 | 0 | 1.1567 | 14.27% | 12.17% | -20.18% | 0.7069 |
| 1 | 1 | 1 | 1 | 0 | 1 | 1.1868 | 14.13% | 11.72% | -16.21% | 0.8718 |
| 1 | 1 | 1 | 1 | 1 | 0 | 1.1699 | 13.53% | 11.41% | -15.73% | 0.8604 |
| 1 | 1 | 1 | 1 | 1 | 1 | **1.2004** | 13.48% | 11.05% | **-15.73%** | **0.8571** |

## Main effects (background-averaged, coded +-1; effect = mean|on - mean|off)

Sign-flip flag = factor's on-minus-off delta changes sign across backgrounds (direction not robust).

### CLEAN

| factor | dSharpe | flip | dCalmar | flip |
|---|---:|---|---:|---|
| **U** | +0.1575 | | +0.2071 | |
| **R** | +0.1584 | | +0.1885 | |
| **C** | +0.0381 | | +0.0646 | SIGN-FLIP |
| **P** | +0.0143 | | +0.0283 | SIGN-FLIP |
| **S** | -0.0530 | SIGN-FLIP | +0.0189 | SIGN-FLIP |
| **W** | +0.0070 | SIGN-FLIP | +0.0138 | SIGN-FLIP |

### EXT

| factor | dSharpe | flip | dCalmar | flip |
|---|---:|---|---:|---|
| **U** | +0.0800 | | +0.1241 | SIGN-FLIP |
| **R** | +0.0818 | SIGN-FLIP | +0.0714 | SIGN-FLIP |
| **C** | +0.0163 | SIGN-FLIP | +0.0480 | SIGN-FLIP |
| **P** | +0.0185 | | +0.0323 | SIGN-FLIP |
| **W** | +0.0083 | SIGN-FLIP | +0.0283 | SIGN-FLIP |
| **S** | -0.0188 | SIGN-FLIP | +0.0085 | SIGN-FLIP |

## Two-way interactions

Calmar (both windows), sorted by |CLEAN|:

| interaction | CLEAN | EXT |
|---|---:|---:|
| RxS | +0.0831 | +0.0479 |
| RxW | +0.0512 | +0.0588 |
| SxP | +0.0283 | +0.0273 |
| RxP | +0.0279 | +0.0283 |
| CxU | +0.0226 | +0.0016 |
| SxW | +0.0217 | +0.0218 |
| WxP | -0.0129 | -0.0072 |
| UxR | -0.0118 | -0.0192 |
| CxP | +0.0081 | -0.0000 |
| UxS | +0.0080 | +0.0032 |
| CxR | -0.0062 | +0.0160 |
| UxP | +0.0047 | +0.0014 |
| CxW | -0.0029 | -0.0020 |
| CxS | +0.0014 | +0.0031 |
| UxW | -0.0003 | -0.0043 |

Sharpe (both windows), sorted by |CLEAN|:

| interaction | CLEAN | EXT |
|---|---:|---:|
| RxS | +0.0361 | +0.0347 |
| RxW | +0.0318 | +0.0172 |
| UxS | +0.0180 | +0.0126 |
| SxP | +0.0143 | +0.0099 |
| CxR | -0.0140 | +0.0132 |
| CxU | +0.0119 | +0.0114 |
| UxP | +0.0055 | +0.0016 |
| RxP | +0.0053 | +0.0035 |
| SxW | +0.0050 | -0.0018 |
| CxS | +0.0043 | +0.0163 |
| UxR | -0.0042 | +0.0166 |
| UxW | +0.0031 | -0.0024 |
| CxW | -0.0021 | +0.0023 |
| CxP | +0.0009 | +0.0037 |
| WxP | +0.0008 | +0.0004 |

### Key requested interactions

| interaction | meaning | CLEAN Calmar | EXT Calmar | CLEAN Sharpe | EXT Sharpe |
|---|---|---:|---:|---:|---:|
| SxP | positive-trend screen vs partial-safe (P bites only when S thins breadth < 4) | +0.0283 | +0.0273 | +0.0143 | +0.0099 |
| WxP | inverse-vol weighting vs partial-safe exposure scaling | -0.0129 | -0.0072 | +0.0008 | +0.0004 |
| SxW | screen vs weighting | +0.0217 | +0.0218 | +0.0050 | -0.0018 |
| RxW | ranker vs weighting | +0.0512 | +0.0588 | +0.0318 | +0.0172 |
| CxS | canary risk-off vs absolute screen (overlap) | +0.0014 | +0.0031 | +0.0043 | +0.0163 |
| RxS | ranker vs screen | +0.0831 | +0.0479 | +0.0361 | +0.0347 |
| CxP | canary vs partial-safe | +0.0081 | -0.0000 | +0.0009 | +0.0037 |
| RxP | ranker vs partial-safe | +0.0279 | +0.0283 | +0.0053 | +0.0035 |
| UxP | universe vs partial-safe | +0.0047 | +0.0014 | +0.0055 | +0.0016 |

## Derived contribution ladder (best ordered cumulative path)

Ordering = factors by CLEAN Calmar main effect, largest first, value-subtractors last: **U -> R -> C -> P -> S -> W**.

### CLEAN cumulative path

| step | config (C,U,R,S,W,P) | Sharpe | Calmar | MaxDD |
|---|---|---:|---:|---:|
| all-OFF (AAA baseline) | `000000` | 0.8561 | 0.4902 | -19.43% |
| + U | `010000` | 0.9625 | 0.6793 | -16.40% |
| + R | `011000` | 1.0743 | 0.7372 | -16.97% |
| + C | `111000` | 1.1148 | 0.8138 | -16.97% |
| + P | `111001` | 1.1148 | 0.8138 | -16.97% |
| + S | `111101` | 1.1317 | 1.0147 | -13.05% |
| + W = all-ON (production) | `111111` | 1.1658 | 1.0137 | -12.97% |

### EXT cumulative path

| step | config (C,U,R,S,W,P) | Sharpe | Calmar | MaxDD |
|---|---|---:|---:|---:|
| all-OFF (AAA baseline) | `000000` | 1.0336 | 0.5898 | -19.43% |
| + U | `010000` | 1.0624 | 0.7427 | -16.40% |
| + R | `011000` | 1.0980 | 0.6526 | -19.00% |
| + C | `111000` | 1.1175 | 0.7320 | -19.00% |
| + P | `111001` | 1.1341 | 0.7416 | -19.00% |
| + S | `111101` | 1.1868 | 0.8718 | -16.21% |
| + W = all-ON (production) | `111111` | 1.2004 | 0.8571 | -15.73% |

## Caveats / confidence

- all-ON cell reproduces production `cpm_live.compute_target_weights` exactly (param==prod) and the task-specified anchor (clean 1.1910 / -12.67% / 1.0615; ext 1.2142 / -15.93% / 0.8608). Confidence high.
- P (partial-safe: scale risky exposure by breadth) is defined coherently with S and W: with S OFF breadth == 4 so P is inert (risky_fraction == 1); with S ON the emptied slots route to safe at risky_fraction = min(breadth,4)/4. W controls only weighting (equal vs inverse-vol). all-ON (W=1,P=1) equals the 5-factor all-ON; the 5-factor cube is the P==W diagonal of this 6-factor cube.
- Grid internally consistent: shared harness, single EXT run sliced per window, identical cost/execution across all 64 cells.
- Main-effect averaging hides structure; read main effects together with the interaction table (especially S x P and W x P) and the ladder, not in isolation. The P main effect is diluted because P is inert across the entire S-OFF half of the cube.
- All numbers mooex / T+1 MOO exact / 10 bps/side / no vol gate (CPM has none). EXT 27y is partly proxy-backed pre-2006 for the trend universe; CLEAN 18y has full real-open coverage and is the decisive lens.
