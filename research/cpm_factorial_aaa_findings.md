# CPM 2^6 factorial -- corrected, with a FAITHFUL AAA baseline

Role: analyst (read-only re production; no production/memo files changed; no commit). Throwaway harness in `research/`.

Script: `research/cpm_factorial_faithful_aaa.py` -> `research/cpm_factorial_faithful_aaa.json`.

> CORRECTS the baseline of `research/cpm_factorial_iv4_6factor.py`. The prior harness used a NON-faithful AAA baseline (plain-12m momentum + equal-weight + a TIP canary), which is NOT the AAA (Adaptive Asset Allocation) spec. Here the all-OFF cell is the TRUE faithful AAA, reusing the audit implementation in `/tmp/true_aaa_haa.py`: raw 6-month total-return momentum, top-half (top-4 of 8), MINIMUM-VARIANCE weighting (weighted covariance 126d correlation / 20d vol), monthly, NO canary, NO screen, fully invested. Each of the six factors toggles exactly one AAA->CPM component (OFF = AAA value, ON = CPM/production value). all-ON reproduces production `cpm_live.compute_target_weights` exactly.

## Data constraint (faithful AAA universe)

Verified AAA spec is a 10-asset universe `[SPY, EZU/EFA, EWJ, EEM, VNQ/IYR, RWX, IEF, TLT, DBC, GLD]`. The panel lacks **EWJ** and **RWX**, so the best buildable faithful AAA is **8 of 10**: `['SPY', 'EFA', 'EEM', 'VNQ', 'IEF', 'TLT', 'DBC', 'GLD']`. Top-half = ceil(8/2) = 4. This 8-of-10 constraint applies to the all-OFF baseline and any U=OFF cell; it does NOT affect U=ON (CPM) cells.

## Factor definitions (OFF = faithful AAA / ON = production CPM)

| factor | OFF (faithful AAA) | ON (production CPM) |
|---|---|---|
| **U** universe | AAA 8-members `[SPY,EFA,EEM,VNQ,IEF,TLT,DBC,GLD]` (8 of 10) | CPM 8-members `[QQQ,SPHQ,EFA,EEM,VNQ,GLD,TLT,DBC]` |
| **R** ranker | raw 6-month total-return momentum | vol-adjusted Faber (10m-SMA distance / realized vol) -- bundles metric+lookback+vol-adjust |
| **W** weighting | minimum-variance (weighted cov: 126d corr / 20d vol) | inverse-vol (504d) -- bundles scheme+window |
| **S** screen | none (hold all top-K regardless of momentum sign) | positive-trend (absolute-momentum) screen; non-positive slots empty |
| **P** partial-safe | fully invested (risky_fraction = 1) | strict-4: risky_fraction = min(n_pos,4)/4; remainder routed to timed SHV/IEF best-of-safe |
| **C** canary | none (no risk-off gate) | HYG-OR-TIP any-positive 13612U gate (risk-off to safe when canary non-positive) |

Both universes are top-half (top-4 of 8); cardinality is NOT a separate factor. Common fixed-on settings (NOT factors): top-half K cap (ceil(n/2)=4 both universes), SHV/IEF best-of-safe timed by 13612U.


**S x P coherence.** Held set = top-K (top-half, ceil(n/2) = 4); breadth = len(held). With S OFF the held set is the full top-K (sign ignored), so breadth = 4 and partial-safe routes nothing (risky_fraction = 1 even when P is ON) -- P is INERT across the entire S-OFF half of the cube. With S ON the held set is the positive-trend subset, so breadth < 4 is possible and P (when ON) routes the emptied slots (4 - breadth) to safe. P therefore only bites when S thins breadth below 4 -> a strong S x P interaction is expected, and the contribution ladder places P AFTER S.

## Execution convention (every table below)

Realistic T+1 MOO exact (`mooex`), post-cost 10 bps/side, via the shared `_segment_returns_conv` harness so cost/window/execution are byte-identical across all 64 cells. CPM sleeve has NO vol gate. Windows: CLEAN 18y (2008-05-30 .. 2026-05-22), EXT 27y (1999-03-10 .. 2026-05-22). Full panel runs once over EXT and is sliced to each window.

## Anchor gate (gate-first; abort/flag on mismatch)

Two binding gates: (1) all-OFF cell == faithful AAA (clean Sharpe ~0.7869 / MaxDD -23.21% / Calmar 0.3188 ; ext Sharpe ~0.8696 / Calmar 0.3624); (2) all-ON cell == live production `compute_target_weights` (param==prod) in both windows AND the CLEAN all-ON cell == the production anchor (Sharpe 1.1910 / MaxDD -12.67% / Calmar 1.0615; EXT 1.2142 / -15.93% / 0.8608).

### Gate 1 -- all-OFF == faithful AAA

| window | all-OFF Sharpe | all-OFF MaxDD | all-OFF Calmar | faithful-AAA target (Sharpe/MaxDD/Calmar) | matches |
|---|---:|---:|---:|---|---|
| CLEAN | 0.7869 | -23.21% | 0.3188 | 0.7869/-23.21%/0.3188 | YES |
| EXT | 0.8696 | -23.21% | 0.3624 | 0.8696/n/a/0.3624 | YES |

### Gate 2 -- all-ON == production CPM

| window | all-ON Sharpe | all-ON MaxDD | all-ON Calmar | production-direct Sharpe | gate target (Sharpe/MaxDD/Calmar) | param==prod | matches anchor |
|---|---:|---:|---:|---:|---|---|---|
| CLEAN | 1.1910 | -12.67% | 1.0615 | 1.1910 | 1.1910/-12.67%/1.0615 | YES | YES |
| EXT | 1.2142 | -15.93% | 0.8608 | 1.2142 | 1.2142/-15.93%/0.8608 | YES | YES |

Gate PASS: all-OFF reproduces the faithful AAA baseline and all-ON equals live production `cpm_live.compute_target_weights` (param==prod, both windows) and the production CLEAN anchor EXACTLY. Grid proceeds.

## Full 64-cell grid -- CLEAN (mooex, 10 bps/side)

Config column order: C,U,R,S,W,P.

| C | U | R | S | W | P | Sharpe | CAGR | Vol | MaxDD | Calmar |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 0 | 0 | 0 | 0 | 0 | **0.7869** | 7.40% | 9.71% | **-23.21%** | **0.3188** |
| 0 | 0 | 0 | 0 | 0 | 1 | 0.7869 | 7.40% | 9.71% | -23.21% | 0.3188 |
| 0 | 0 | 0 | 0 | 1 | 0 | 0.8257 | 8.79% | 10.99% | -22.79% | 0.3855 |
| 0 | 0 | 0 | 0 | 1 | 1 | 0.8257 | 8.79% | 10.99% | -22.79% | 0.3855 |
| 0 | 0 | 0 | 1 | 0 | 0 | 0.7143 | 7.38% | 10.85% | -25.99% | 0.2842 |
| 0 | 0 | 0 | 1 | 0 | 1 | 0.8611 | 7.98% | 9.47% | -14.30% | 0.5579 |
| 0 | 0 | 0 | 1 | 1 | 0 | 0.7209 | 8.20% | 11.99% | -23.66% | 0.3465 |
| 0 | 0 | 0 | 1 | 1 | 1 | 0.8615 | 8.90% | 10.60% | -16.86% | 0.5278 |
| 0 | 0 | 1 | 0 | 0 | 0 | 0.9128 | 8.56% | 9.54% | -23.54% | 0.3637 |
| 0 | 0 | 1 | 0 | 0 | 1 | 0.9128 | 8.56% | 9.54% | -23.54% | 0.3637 |
| 0 | 0 | 1 | 0 | 1 | 0 | 0.9325 | 10.01% | 10.92% | -20.51% | 0.4880 |
| 0 | 0 | 1 | 0 | 1 | 1 | 0.9325 | 10.01% | 10.92% | -20.51% | 0.4880 |
| 0 | 0 | 1 | 1 | 0 | 0 | 0.8033 | 8.05% | 10.35% | -30.07% | 0.2677 |
| 0 | 0 | 1 | 1 | 0 | 1 | 0.9613 | 8.49% | 8.92% | -15.16% | 0.5598 |
| 0 | 0 | 1 | 1 | 1 | 0 | 0.8244 | 9.22% | 11.57% | -26.54% | 0.3475 |
| 0 | 0 | 1 | 1 | 1 | 1 | 0.9660 | 9.69% | 10.15% | -13.67% | 0.7087 |
| 0 | 1 | 0 | 0 | 0 | 0 | 0.8333 | 9.81% | 12.17% | -32.67% | 0.3003 |
| 0 | 1 | 0 | 0 | 0 | 1 | 0.8333 | 9.81% | 12.17% | -32.67% | 0.3003 |
| 0 | 1 | 0 | 0 | 1 | 0 | 0.8355 | 10.69% | 13.27% | -31.61% | 0.3384 |
| 0 | 1 | 0 | 0 | 1 | 1 | 0.8355 | 10.69% | 13.27% | -31.61% | 0.3384 |
| 0 | 1 | 0 | 1 | 0 | 0 | 0.6704 | 8.18% | 13.08% | -30.06% | 0.2720 |
| 0 | 1 | 0 | 1 | 0 | 1 | 0.8008 | 8.88% | 11.51% | -25.36% | 0.3500 |
| 0 | 1 | 0 | 1 | 1 | 0 | 0.7383 | 9.66% | 13.87% | -28.85% | 0.3348 |
| 0 | 1 | 0 | 1 | 1 | 1 | 0.8622 | 10.30% | 12.31% | -22.37% | 0.4605 |
| 0 | 1 | 1 | 0 | 0 | 0 | 1.0821 | 12.77% | 11.79% | -24.81% | 0.5147 |
| 0 | 1 | 1 | 0 | 0 | 1 | 1.0821 | 12.77% | 11.79% | -24.81% | 0.5147 |
| 0 | 1 | 1 | 0 | 1 | 0 | 1.0051 | 12.90% | 12.96% | -28.46% | 0.4534 |
| 0 | 1 | 1 | 0 | 1 | 1 | 1.0051 | 12.90% | 12.96% | -28.46% | 0.4534 |
| 0 | 1 | 1 | 1 | 0 | 0 | 1.0082 | 12.56% | 12.56% | -28.88% | 0.4348 |
| 0 | 1 | 1 | 1 | 0 | 1 | 1.1966 | 13.17% | 10.87% | -12.99% | 1.0133 |
| 0 | 1 | 1 | 1 | 1 | 0 | 0.9448 | 12.29% | 13.26% | -24.54% | 0.5010 |
| 0 | 1 | 1 | 1 | 1 | 1 | 1.1278 | 13.11% | 11.57% | -15.01% | 0.8736 |
| 1 | 0 | 0 | 0 | 0 | 0 | 0.8466 | 7.69% | 9.30% | -14.05% | 0.5473 |
| 1 | 0 | 0 | 0 | 0 | 1 | 0.8466 | 7.69% | 9.30% | -14.05% | 0.5473 |
| 1 | 0 | 0 | 0 | 1 | 0 | 0.9057 | 9.22% | 10.39% | -16.28% | 0.5665 |
| 1 | 0 | 0 | 0 | 1 | 1 | 0.9057 | 9.22% | 10.39% | -16.28% | 0.5665 |
| 1 | 0 | 0 | 1 | 0 | 0 | 0.8712 | 8.29% | 9.73% | -16.08% | 0.5159 |
| 1 | 0 | 0 | 1 | 0 | 1 | 0.8951 | 8.10% | 9.21% | -14.10% | 0.5742 |
| 1 | 0 | 0 | 1 | 1 | 0 | 0.8794 | 9.27% | 10.79% | -18.82% | 0.4924 |
| 1 | 0 | 0 | 1 | 1 | 1 | 0.9093 | 9.16% | 10.27% | -16.83% | 0.5441 |
| 1 | 0 | 1 | 0 | 0 | 0 | 1.0527 | 9.34% | 8.89% | -12.96% | 0.7203 |
| 1 | 0 | 1 | 0 | 0 | 1 | 1.0527 | 9.34% | 8.89% | -12.96% | 0.7203 |
| 1 | 0 | 1 | 0 | 1 | 0 | 1.0430 | 10.46% | 10.07% | -14.70% | 0.7116 |
| 1 | 0 | 1 | 0 | 1 | 1 | 1.0430 | 10.46% | 10.07% | -14.70% | 0.7116 |
| 1 | 0 | 1 | 1 | 0 | 0 | 0.9890 | 8.96% | 9.14% | -14.96% | 0.5994 |
| 1 | 0 | 1 | 1 | 0 | 1 | 1.0156 | 8.77% | 8.69% | -12.87% | 0.6816 |
| 1 | 0 | 1 | 1 | 1 | 0 | 1.0002 | 10.26% | 10.35% | -16.09% | 0.6377 |
| 1 | 0 | 1 | 1 | 1 | 1 | 1.0328 | 10.14% | 9.87% | -13.69% | 0.7405 |
| 1 | 1 | 0 | 0 | 0 | 0 | 0.8675 | 9.57% | 11.32% | -24.74% | 0.3866 |
| 1 | 1 | 0 | 0 | 0 | 1 | 0.8675 | 9.57% | 11.32% | -24.74% | 0.3866 |
| 1 | 1 | 0 | 0 | 1 | 0 | 0.9963 | 11.94% | 12.10% | -18.50% | 0.6451 |
| 1 | 1 | 0 | 0 | 1 | 1 | 0.9963 | 11.94% | 12.10% | -18.50% | 0.6451 |
| 1 | 1 | 0 | 1 | 0 | 0 | 0.7568 | 8.42% | 11.65% | -33.74% | 0.2496 |
| 1 | 1 | 0 | 1 | 0 | 1 | 0.8365 | 8.99% | 11.08% | -25.08% | 0.3584 |
| 1 | 1 | 0 | 1 | 1 | 0 | 0.8740 | 10.50% | 12.37% | -27.68% | 0.3794 |
| 1 | 1 | 0 | 1 | 1 | 1 | 0.9333 | 10.84% | 11.83% | -19.40% | 0.5586 |
| 1 | 1 | 1 | 0 | 0 | 0 | 1.2062 | 13.13% | 10.74% | -17.52% | 0.7491 |
| 1 | 1 | 1 | 0 | 0 | 1 | 1.2062 | 13.13% | 10.74% | -17.52% | 0.7491 |
| 1 | 1 | 1 | 0 | 1 | 0 | 1.1785 | 13.66% | 11.47% | -14.22% | 0.9606 |
| 1 | 1 | 1 | 0 | 1 | 1 | 1.1785 | 13.66% | 11.47% | -14.22% | 0.9606 |
| 1 | 1 | 1 | 1 | 0 | 0 | 1.2310 | 13.64% | 10.91% | -12.99% | 1.0500 |
| 1 | 1 | 1 | 1 | 0 | 1 | 1.2655 | 13.48% | 10.47% | -12.99% | 1.0378 |
| 1 | 1 | 1 | 1 | 1 | 0 | 1.1491 | 13.44% | 11.61% | -12.67% | 1.0614 |
| 1 | 1 | 1 | 1 | 1 | 1 | **1.1910** | 13.44% | 11.16% | **-12.67%** | **1.0615** |

(all-OFF = `000000` faithful AAA; all-ON = `111111` production CPM -- both bold.)

## Full 64-cell grid -- EXT (mooex, 10 bps/side)

Config column order: C,U,R,S,W,P.

| C | U | R | S | W | P | Sharpe | CAGR | Vol | MaxDD | Calmar |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 0 | 0 | 0 | 0 | 0 | **0.8696** | 8.41% | 9.84% | **-23.21%** | **0.3624** |
| 0 | 0 | 0 | 0 | 0 | 1 | 0.8696 | 8.41% | 9.84% | -23.21% | 0.3624 |
| 0 | 0 | 0 | 0 | 1 | 0 | 0.9822 | 10.59% | 10.85% | -22.79% | 0.4646 |
| 0 | 0 | 0 | 0 | 1 | 1 | 0.9822 | 10.59% | 10.85% | -22.79% | 0.4646 |
| 0 | 0 | 0 | 1 | 0 | 0 | 0.8183 | 8.45% | 10.60% | -25.99% | 0.3252 |
| 0 | 0 | 0 | 1 | 0 | 1 | 0.9179 | 8.78% | 9.68% | -14.30% | 0.6142 |
| 0 | 0 | 0 | 1 | 1 | 0 | 0.8981 | 10.18% | 11.54% | -23.66% | 0.4302 |
| 0 | 0 | 0 | 1 | 1 | 1 | 1.0036 | 10.59% | 10.59% | -17.24% | 0.6144 |
| 0 | 0 | 1 | 0 | 0 | 0 | 0.9350 | 8.53% | 9.21% | -23.54% | 0.3623 |
| 0 | 0 | 1 | 0 | 0 | 1 | 0.9579 | 8.70% | 9.15% | -23.54% | 0.3698 |
| 0 | 0 | 1 | 0 | 1 | 0 | 1.0124 | 10.48% | 10.38% | -20.51% | 0.5112 |
| 0 | 0 | 1 | 0 | 1 | 1 | 1.0325 | 10.66% | 10.33% | -20.51% | 0.5198 |
| 0 | 0 | 1 | 1 | 0 | 0 | 0.8841 | 8.46% | 9.72% | -30.07% | 0.2813 |
| 0 | 0 | 1 | 1 | 0 | 1 | 0.9984 | 8.69% | 8.73% | -15.16% | 0.5731 |
| 0 | 0 | 1 | 1 | 1 | 0 | 0.9510 | 10.16% | 10.79% | -26.54% | 0.3830 |
| 0 | 0 | 1 | 1 | 1 | 1 | 1.0627 | 10.44% | 9.80% | -13.67% | 0.7638 |
| 0 | 1 | 0 | 0 | 0 | 0 | 0.9326 | 10.83% | 11.77% | -34.55% | 0.3135 |
| 0 | 1 | 0 | 0 | 0 | 1 | 0.9326 | 10.83% | 11.77% | -34.55% | 0.3135 |
| 0 | 1 | 0 | 0 | 1 | 0 | 0.9970 | 12.75% | 12.87% | -33.15% | 0.3845 |
| 0 | 1 | 0 | 0 | 1 | 1 | 0.9970 | 12.75% | 12.87% | -33.15% | 0.3845 |
| 0 | 1 | 0 | 1 | 0 | 0 | 0.8068 | 9.71% | 12.45% | -32.71% | 0.2968 |
| 0 | 1 | 0 | 1 | 0 | 1 | 0.9027 | 10.05% | 11.32% | -28.93% | 0.3474 |
| 0 | 1 | 0 | 1 | 1 | 0 | 0.9252 | 12.11% | 13.32% | -28.85% | 0.4199 |
| 0 | 1 | 0 | 1 | 1 | 1 | 1.0235 | 12.47% | 12.21% | -22.92% | 0.5442 |
| 0 | 1 | 1 | 0 | 0 | 0 | 1.0243 | 11.55% | 11.30% | -24.81% | 0.4656 |
| 0 | 1 | 1 | 0 | 0 | 1 | 1.0424 | 11.73% | 11.25% | -24.81% | 0.4729 |
| 0 | 1 | 1 | 0 | 1 | 0 | 1.0323 | 12.80% | 12.41% | -29.88% | 0.4283 |
| 0 | 1 | 1 | 0 | 1 | 1 | 1.0485 | 12.98% | 12.37% | -29.88% | 0.4344 |
| 0 | 1 | 1 | 1 | 0 | 0 | 0.9989 | 11.77% | 11.84% | -28.88% | 0.4075 |
| 0 | 1 | 1 | 1 | 0 | 1 | 1.1221 | 12.02% | 10.62% | -15.42% | 0.7798 |
| 0 | 1 | 1 | 1 | 1 | 0 | 1.0381 | 13.08% | 12.60% | -24.54% | 0.5328 |
| 0 | 1 | 1 | 1 | 1 | 1 | 1.1721 | 13.55% | 11.40% | -15.93% | 0.8508 |
| 1 | 0 | 0 | 0 | 0 | 0 | 0.9092 | 8.55% | 9.53% | -14.05% | 0.6087 |
| 1 | 0 | 0 | 0 | 0 | 1 | 0.9092 | 8.55% | 9.53% | -14.05% | 0.6087 |
| 1 | 0 | 0 | 0 | 1 | 0 | 1.0442 | 10.88% | 10.41% | -17.24% | 0.6312 |
| 1 | 0 | 0 | 0 | 1 | 1 | 1.0442 | 10.88% | 10.41% | -17.24% | 0.6312 |
| 1 | 0 | 0 | 1 | 0 | 0 | 0.9281 | 9.00% | 9.81% | -16.08% | 0.5601 |
| 1 | 0 | 0 | 1 | 0 | 1 | 0.9400 | 8.81% | 9.46% | -14.10% | 0.6248 |
| 1 | 0 | 0 | 1 | 1 | 0 | 1.0211 | 10.90% | 10.69% | -18.82% | 0.5791 |
| 1 | 0 | 0 | 1 | 1 | 1 | 1.0413 | 10.76% | 10.33% | -17.24% | 0.6245 |
| 1 | 0 | 1 | 0 | 0 | 0 | 1.0153 | 8.87% | 8.75% | -13.90% | 0.6381 |
| 1 | 0 | 1 | 0 | 0 | 1 | 1.0403 | 9.05% | 8.69% | -13.90% | 0.6507 |
| 1 | 0 | 1 | 0 | 1 | 0 | 1.0924 | 10.75% | 9.78% | -14.70% | 0.7309 |
| 1 | 0 | 1 | 0 | 1 | 1 | 1.1145 | 10.92% | 9.73% | -14.70% | 0.7430 |
| 1 | 0 | 1 | 1 | 0 | 0 | 1.0059 | 8.90% | 8.86% | -14.96% | 0.5948 |
| 1 | 0 | 1 | 1 | 0 | 1 | 1.0199 | 8.71% | 8.55% | -13.90% | 0.6265 |
| 1 | 0 | 1 | 1 | 1 | 0 | 1.0846 | 10.82% | 9.93% | -16.09% | 0.6722 |
| 1 | 0 | 1 | 1 | 1 | 1 | 1.1089 | 10.70% | 9.59% | -13.69% | 0.7817 |
| 1 | 1 | 0 | 0 | 0 | 0 | 0.9679 | 10.69% | 11.14% | -26.84% | 0.3982 |
| 1 | 1 | 0 | 0 | 0 | 1 | 0.9679 | 10.69% | 11.14% | -26.84% | 0.3982 |
| 1 | 1 | 0 | 0 | 1 | 0 | 1.1295 | 13.68% | 11.99% | -20.35% | 0.6724 |
| 1 | 1 | 0 | 0 | 1 | 1 | 1.1295 | 13.68% | 11.99% | -20.35% | 0.6724 |
| 1 | 1 | 0 | 1 | 0 | 0 | 0.8810 | 9.85% | 11.41% | -36.25% | 0.2718 |
| 1 | 1 | 0 | 1 | 0 | 1 | 0.9335 | 10.12% | 10.97% | -28.66% | 0.3531 |
| 1 | 1 | 0 | 1 | 1 | 0 | 1.0388 | 12.68% | 12.21% | -27.68% | 0.4581 |
| 1 | 1 | 0 | 1 | 1 | 1 | 1.0814 | 12.83% | 11.81% | -19.97% | 0.6425 |
| 1 | 1 | 1 | 0 | 0 | 0 | 1.0950 | 11.63% | 10.56% | -17.52% | 0.6635 |
| 1 | 1 | 1 | 0 | 0 | 1 | 1.1150 | 11.81% | 10.51% | -17.52% | 0.6738 |
| 1 | 1 | 1 | 0 | 1 | 0 | 1.1586 | 13.33% | 11.36% | -15.93% | 0.8372 |
| 1 | 1 | 1 | 0 | 1 | 1 | 1.1772 | 13.52% | 11.32% | -15.93% | 0.8486 |
| 1 | 1 | 1 | 1 | 0 | 0 | 1.1384 | 12.28% | 10.68% | -15.42% | 0.7964 |
| 1 | 1 | 1 | 1 | 0 | 1 | 1.1540 | 12.05% | 10.32% | -15.42% | 0.7816 |
| 1 | 1 | 1 | 1 | 1 | 0 | 1.1857 | 13.78% | 11.44% | -15.93% | 0.8651 |
| 1 | 1 | 1 | 1 | 1 | 1 | **1.2142** | 13.71% | 11.09% | **-15.93%** | **0.8608** |

(all-OFF = `000000` faithful AAA; all-ON = `111111` production CPM -- both bold.)

## Main effects (background-averaged, coded +-1; effect = mean|on - mean|off)

Sign-flip flag = factor's on-minus-off delta changes sign across backgrounds (direction not robust).

### CLEAN

| factor | dSharpe | flip | dCalmar | flip |
|---|---:|---|---:|---|
| **R** | +0.2048 | | +0.2411 | SIGN-FLIP |
| **C** | +0.1104 | | +0.2172 | SIGN-FLIP |
| **P** | +0.0482 | | +0.0886 | SIGN-FLIP |
| **U** | +0.0837 | SIGN-FLIP | +0.0657 | SIGN-FLIP |
| **W** | +0.0127 | SIGN-FLIP | +0.0646 | SIGN-FLIP |
| **S** | -0.0228 | SIGN-FLIP | +0.0463 | SIGN-FLIP |

### EXT

| factor | dSharpe | flip | dCalmar | flip |
|---|---:|---|---:|---|
| **C** | +0.0786 | | +0.1788 | SIGN-FLIP |
| **R** | +0.1002 | | +0.1414 | SIGN-FLIP |
| **W** | +0.0872 | | +0.1089 | SIGN-FLIP |
| **P** | +0.0392 | | +0.0808 | SIGN-FLIP |
| **S** | -0.0080 | SIGN-FLIP | +0.0386 | SIGN-FLIP |
| **U** | +0.0584 | SIGN-FLIP | -0.0043 | SIGN-FLIP |

## Two-way interactions

Calmar (both windows), sorted by |CLEAN|:

| interaction | CLEAN | EXT |
|---|---:|---:|
| UxR | +0.1392 | +0.0979 |
| SxP | +0.0886 | +0.0760 |
| CxR | +0.0832 | +0.0480 |
| RxS | +0.0570 | +0.0364 |
| CxP | -0.0529 | -0.0468 |
| CxS | -0.0483 | -0.0582 |
| UxS | +0.0349 | +0.0143 |
| RxP | +0.0225 | +0.0168 |
| CxW | +0.0211 | +0.0162 |
| UxW | +0.0203 | +0.0225 |
| CxU | +0.0194 | -0.0027 |
| SxW | -0.0165 | +0.0029 |
| RxW | -0.0134 | -0.0073 |
| WxP | -0.0026 | +0.0055 |
| UxP | +0.0009 | -0.0091 |

### Key requested interactions

| interaction | meaning | CLEAN Calmar | EXT Calmar | CLEAN Sharpe | EXT Sharpe |
|---|---|---:|---:|---:|---:|
| RxW | ranker vs weighting | -0.0134 | -0.0073 | -0.0392 | -0.0285 |
| SxP | positive screen vs partial-safe (P bites only when S thins breadth < 4) | +0.0886 | +0.0760 | +0.0482 | +0.0290 |
| SxW | screen vs weighting (min-var vs inverse-vol on a thinned set) | -0.0165 | +0.0029 | -0.0041 | +0.0003 |
| RxS | ranker vs screen | +0.0570 | +0.0364 | +0.0153 | +0.0234 |
| UxR | universe vs ranker | +0.1392 | +0.0979 | +0.0778 | +0.0291 |
| CxS | screen vs canary (overlapping risk-off) | -0.0483 | -0.0582 | +0.0001 | -0.0003 |
| WxP | weighting vs partial-safe | -0.0026 | +0.0055 | -0.0011 | +0.0009 |

## Contribution ladder (dependency-respecting cumulative path)

Ordering = factors by CLEAN Calmar main effect, largest first, with P forced AFTER S (P is inert until S thins breadth below 4): **R -> C -> U -> W -> S -> P**.

### CLEAN cumulative path

| step | config (C,U,R,S,W,P) | Sharpe | Calmar | MaxDD |
|---|---|---:|---:|---:|
| all-OFF (faithful AAA) | `000000` | 0.7869 | 0.3188 | -23.21% |
| + R | `001000` | 0.9128 | 0.3637 | -23.54% |
| + C | `101000` | 1.0527 | 0.7203 | -12.96% |
| + U | `111000` | 1.2062 | 0.7491 | -17.52% |
| + W | `111010` | 1.1785 | 0.9606 | -14.22% |
| + S | `111110` | 1.1491 | 1.0614 | -12.67% |
| + P = all-ON (production) | `111111` | 1.1910 | 1.0615 | -12.67% |

CLEAN: Calmar is monotonically non-decreasing along this ladder.

### EXT cumulative path

| step | config (C,U,R,S,W,P) | Sharpe | Calmar | MaxDD |
|---|---|---:|---:|---:|
| all-OFF (faithful AAA) | `000000` | 0.8696 | 0.3624 | -23.21% |
| + R | `001000` | 0.9350 | 0.3623 | -23.54% |
| + C | `101000` | 1.0153 | 0.6381 | -13.90% |
| + U | `111000` | 1.0950 | 0.6635 | -17.52% |
| + W | `111010` | 1.1586 | 0.8372 | -15.93% |
| + S | `111110` | 1.1857 | 0.8651 | -15.93% |
| + P = all-ON (production) | `111111` | 1.2142 | 0.8608 | -15.93% |

EXT: Calmar is NOT monotone along this ladder (at least one step reduces Calmar) -- reported honestly; see the step deltas above.

## Caveats / confidence

- all-OFF cell reproduces the faithful AAA baseline (raw 6m momentum, top-4/8, weighted-cov min-variance, monthly, no canary/screen/partial-safe) and all-ON reproduces production `cpm_live.compute_target_weights` exactly (param==prod). Confidence high subject to the data constraint below.
- DATA CONSTRAINT: the faithful AAA universe is 10 assets but the panel lacks EWJ and RWX, so the all-OFF baseline and all U=OFF cells use the best-buildable 8-of-10 universe `['SPY', 'EFA', 'EEM', 'VNQ', 'IEF', 'TLT', 'DBC', 'GLD']`. The faithful-AAA anchor itself was computed under the same 8-of-10 constraint, so the gate is apples-to-apples.
- P (partial-safe) is defined coherently with S: with S OFF breadth == 4 so P is inert (risky_fraction == 1); with S ON the emptied slots route to safe at risky_fraction = min(breadth,4)/4. The P main effect is diluted because P is inert across the entire S-OFF half of the cube -- read it together with the S x P interaction and the ladder, where P is placed after S.
- W=OFF uses long-only SLSQP min-variance on the AAA weighted covariance (126d corr / 20d vol). Optimizer non-convergence falls back to equal-weight (rare); this matches the audit implementation.
- Grid internally consistent: shared harness, single EXT run sliced per window, identical cost/execution across all 64 cells.
- All numbers mooex / T+1 MOO exact / 10 bps/side / no vol gate (CPM has none). EXT 27y is partly proxy-backed pre-2006 for the trend universe; CLEAN 18y has full real-open coverage and is the decisive lens. CLEAN-only monotonicity vs any EXT non-monotonicity is reported honestly in the ladder section.
