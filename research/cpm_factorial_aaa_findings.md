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
| CLEAN | 1.1658 | -12.97% | 1.0137 | 1.1658 | 1.1910/-12.67%/1.0615 | YES | NO |
| EXT | 1.2004 | -15.73% | 0.8571 | 1.2004 | 1.2142/-15.93%/0.8608 | YES | NO |

**GATE FAIL**: at least one anchor did not reproduce. Numbers below are FLAGGED and should not be trusted until reconciled.

## Full 64-cell grid -- CLEAN (mooex, 10 bps/side)

Config column order: C,U,R,S,W,P.

| C | U | R | S | W | P | Sharpe | CAGR | Vol | MaxDD | Calmar |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 0 | 0 | 0 | 0 | 0 | **0.7869** | 7.40% | 9.71% | **-23.21%** | **0.3188** |
| 0 | 0 | 0 | 0 | 0 | 1 | 0.7869 | 7.40% | 9.71% | -23.21% | 0.3188 |
| 0 | 0 | 0 | 0 | 1 | 0 | 0.7911 | 8.38% | 11.00% | -22.88% | 0.3663 |
| 0 | 0 | 0 | 0 | 1 | 1 | 0.7911 | 8.38% | 11.00% | -22.88% | 0.3663 |
| 0 | 0 | 0 | 1 | 0 | 0 | 0.7143 | 7.38% | 10.85% | -25.99% | 0.2842 |
| 0 | 0 | 0 | 1 | 0 | 1 | 0.8611 | 7.98% | 9.47% | -14.30% | 0.5579 |
| 0 | 0 | 0 | 1 | 1 | 0 | 0.6829 | 7.70% | 11.98% | -24.13% | 0.3191 |
| 0 | 0 | 0 | 1 | 1 | 1 | 0.8217 | 8.45% | 10.61% | -16.98% | 0.4974 |
| 0 | 0 | 1 | 0 | 0 | 0 | 0.9128 | 8.56% | 9.54% | -23.54% | 0.3637 |
| 0 | 0 | 1 | 0 | 0 | 1 | 0.9128 | 8.56% | 9.54% | -23.54% | 0.3637 |
| 0 | 0 | 1 | 0 | 1 | 0 | 0.9013 | 9.59% | 10.87% | -20.85% | 0.4602 |
| 0 | 0 | 1 | 0 | 1 | 1 | 0.9013 | 9.59% | 10.87% | -20.85% | 0.4602 |
| 0 | 0 | 1 | 1 | 0 | 0 | 0.8033 | 8.05% | 10.35% | -30.07% | 0.2677 |
| 0 | 0 | 1 | 1 | 0 | 1 | 0.9613 | 8.49% | 8.92% | -15.16% | 0.5598 |
| 0 | 0 | 1 | 1 | 1 | 0 | 0.7928 | 8.80% | 11.54% | -27.14% | 0.3243 |
| 0 | 0 | 1 | 1 | 1 | 1 | 0.9344 | 9.32% | 10.13% | -13.83% | 0.6737 |
| 0 | 1 | 0 | 0 | 0 | 0 | 0.8333 | 9.81% | 12.17% | -32.67% | 0.3003 |
| 0 | 1 | 0 | 0 | 0 | 1 | 0.8333 | 9.81% | 12.17% | -32.67% | 0.3003 |
| 0 | 1 | 0 | 0 | 1 | 0 | 0.8142 | 10.41% | 13.31% | -31.88% | 0.3265 |
| 0 | 1 | 0 | 0 | 1 | 1 | 0.8142 | 10.41% | 13.31% | -31.88% | 0.3265 |
| 0 | 1 | 0 | 1 | 0 | 0 | 0.6704 | 8.18% | 13.08% | -30.06% | 0.2720 |
| 0 | 1 | 0 | 1 | 0 | 1 | 0.8008 | 8.88% | 11.51% | -25.36% | 0.3500 |
| 0 | 1 | 0 | 1 | 1 | 0 | 0.7127 | 9.30% | 13.92% | -29.06% | 0.3201 |
| 0 | 1 | 0 | 1 | 1 | 1 | 0.8343 | 9.97% | 12.38% | -22.65% | 0.4404 |
| 0 | 1 | 1 | 0 | 0 | 0 | 1.0821 | 12.77% | 11.79% | -24.81% | 0.5147 |
| 0 | 1 | 1 | 0 | 0 | 1 | 1.0821 | 12.77% | 11.79% | -24.81% | 0.5147 |
| 0 | 1 | 1 | 0 | 1 | 0 | 0.9727 | 12.45% | 12.99% | -28.30% | 0.4401 |
| 0 | 1 | 1 | 0 | 1 | 1 | 0.9727 | 12.45% | 12.99% | -28.30% | 0.4401 |
| 0 | 1 | 1 | 1 | 0 | 0 | 1.0082 | 12.56% | 12.56% | -28.88% | 0.4348 |
| 0 | 1 | 1 | 1 | 0 | 1 | 1.1966 | 13.17% | 10.87% | -12.99% | 1.0133 |
| 0 | 1 | 1 | 1 | 1 | 0 | 0.9117 | 11.82% | 13.28% | -25.24% | 0.4683 |
| 0 | 1 | 1 | 1 | 1 | 1 | 1.0948 | 12.71% | 11.59% | -15.26% | 0.8326 |
| 1 | 0 | 0 | 0 | 0 | 0 | 0.8466 | 7.69% | 9.30% | -14.05% | 0.5473 |
| 1 | 0 | 0 | 0 | 0 | 1 | 0.8466 | 7.69% | 9.30% | -14.05% | 0.5473 |
| 1 | 0 | 0 | 0 | 1 | 0 | 0.8799 | 8.93% | 10.39% | -16.49% | 0.5414 |
| 1 | 0 | 0 | 0 | 1 | 1 | 0.8799 | 8.93% | 10.39% | -16.49% | 0.5414 |
| 1 | 0 | 0 | 1 | 0 | 0 | 0.8712 | 8.29% | 9.73% | -16.08% | 0.5159 |
| 1 | 0 | 0 | 1 | 0 | 1 | 0.8951 | 8.10% | 9.21% | -14.10% | 0.5742 |
| 1 | 0 | 0 | 1 | 1 | 0 | 0.8449 | 8.86% | 10.79% | -18.92% | 0.4680 |
| 1 | 0 | 0 | 1 | 1 | 1 | 0.8751 | 8.78% | 10.28% | -16.96% | 0.5178 |
| 1 | 0 | 1 | 0 | 0 | 0 | 1.0527 | 9.34% | 8.89% | -12.96% | 0.7203 |
| 1 | 0 | 1 | 0 | 0 | 1 | 1.0527 | 9.34% | 8.89% | -12.96% | 0.7203 |
| 1 | 0 | 1 | 0 | 1 | 0 | 1.0197 | 10.16% | 10.03% | -14.88% | 0.6828 |
| 1 | 0 | 1 | 0 | 1 | 1 | 1.0197 | 10.16% | 10.03% | -14.88% | 0.6828 |
| 1 | 0 | 1 | 1 | 0 | 0 | 0.9890 | 8.96% | 9.14% | -14.96% | 0.5994 |
| 1 | 0 | 1 | 1 | 0 | 1 | 1.0156 | 8.77% | 8.69% | -12.87% | 0.6816 |
| 1 | 0 | 1 | 1 | 1 | 0 | 0.9748 | 9.94% | 10.32% | -16.03% | 0.6202 |
| 1 | 0 | 1 | 1 | 1 | 1 | 1.0076 | 9.85% | 9.85% | -13.86% | 0.7102 |
| 1 | 1 | 0 | 0 | 0 | 0 | 0.8675 | 9.57% | 11.32% | -24.74% | 0.3866 |
| 1 | 1 | 0 | 0 | 0 | 1 | 0.8675 | 9.57% | 11.32% | -24.74% | 0.3866 |
| 1 | 1 | 0 | 0 | 1 | 0 | 0.9756 | 11.72% | 12.17% | -18.95% | 0.6182 |
| 1 | 1 | 0 | 0 | 1 | 1 | 0.9756 | 11.72% | 12.17% | -18.95% | 0.6182 |
| 1 | 1 | 0 | 1 | 0 | 0 | 0.7568 | 8.42% | 11.65% | -33.74% | 0.2496 |
| 1 | 1 | 0 | 1 | 0 | 1 | 0.8365 | 8.99% | 11.08% | -25.08% | 0.3584 |
| 1 | 1 | 0 | 1 | 1 | 0 | 0.8529 | 10.26% | 12.43% | -28.20% | 0.3639 |
| 1 | 1 | 0 | 1 | 1 | 1 | 0.9116 | 10.61% | 11.90% | -19.76% | 0.5368 |
| 1 | 1 | 1 | 0 | 0 | 0 | 1.2062 | 13.13% | 10.74% | -17.52% | 0.7491 |
| 1 | 1 | 1 | 0 | 0 | 1 | 1.2062 | 13.13% | 10.74% | -17.52% | 0.7491 |
| 1 | 1 | 1 | 0 | 1 | 0 | 1.1465 | 13.33% | 11.54% | -15.38% | 0.8669 |
| 1 | 1 | 1 | 0 | 1 | 1 | 1.1465 | 13.33% | 11.54% | -15.38% | 0.8669 |
| 1 | 1 | 1 | 1 | 0 | 0 | 1.2310 | 13.64% | 10.91% | -12.99% | 1.0500 |
| 1 | 1 | 1 | 1 | 0 | 1 | 1.2655 | 13.48% | 10.47% | -12.99% | 1.0378 |
| 1 | 1 | 1 | 1 | 1 | 0 | 1.1227 | 13.12% | 11.63% | -13.18% | 0.9955 |
| 1 | 1 | 1 | 1 | 1 | 1 | **1.1658** | 13.15% | 11.18% | **-12.97%** | **1.0137** |

(all-OFF = `000000` faithful AAA; all-ON = `111111` production CPM -- both bold.)

## Full 64-cell grid -- EXT (mooex, 10 bps/side)

Config column order: C,U,R,S,W,P.

| C | U | R | S | W | P | Sharpe | CAGR | Vol | MaxDD | Calmar |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 0 | 0 | 0 | 0 | 0 | **0.8696** | 8.41% | 9.84% | **-23.21%** | **0.3624** |
| 0 | 0 | 0 | 0 | 0 | 1 | 0.8696 | 8.41% | 9.84% | -23.21% | 0.3624 |
| 0 | 0 | 0 | 0 | 1 | 0 | 0.9607 | 10.33% | 10.85% | -22.88% | 0.4515 |
| 0 | 0 | 0 | 0 | 1 | 1 | 0.9607 | 10.33% | 10.85% | -22.88% | 0.4515 |
| 0 | 0 | 0 | 1 | 0 | 0 | 0.8183 | 8.45% | 10.60% | -25.99% | 0.3252 |
| 0 | 0 | 0 | 1 | 0 | 1 | 0.9179 | 8.78% | 9.68% | -14.30% | 0.6142 |
| 0 | 0 | 0 | 1 | 1 | 0 | 0.8736 | 9.86% | 11.52% | -24.13% | 0.4085 |
| 0 | 0 | 0 | 1 | 1 | 1 | 0.9794 | 10.30% | 10.59% | -17.03% | 0.6052 |
| 0 | 0 | 1 | 0 | 0 | 0 | 0.9350 | 8.53% | 9.21% | -23.54% | 0.3623 |
| 0 | 0 | 1 | 0 | 0 | 1 | 0.9579 | 8.70% | 9.15% | -23.54% | 0.3698 |
| 0 | 0 | 1 | 0 | 1 | 0 | 0.9940 | 10.24% | 10.34% | -20.85% | 0.4910 |
| 0 | 0 | 1 | 0 | 1 | 1 | 1.0141 | 10.41% | 10.29% | -20.85% | 0.4995 |
| 0 | 0 | 1 | 1 | 0 | 0 | 0.8841 | 8.46% | 9.72% | -30.07% | 0.2813 |
| 0 | 0 | 1 | 1 | 0 | 1 | 0.9984 | 8.69% | 8.73% | -15.16% | 0.5731 |
| 0 | 0 | 1 | 1 | 1 | 0 | 0.9307 | 9.90% | 10.77% | -27.14% | 0.3648 |
| 0 | 0 | 1 | 1 | 1 | 1 | 1.0432 | 10.21% | 9.78% | -13.83% | 0.7383 |
| 0 | 1 | 0 | 0 | 0 | 0 | 0.9326 | 10.83% | 11.77% | -34.55% | 0.3135 |
| 0 | 1 | 0 | 0 | 0 | 1 | 0.9326 | 10.83% | 11.77% | -34.55% | 0.3135 |
| 0 | 1 | 0 | 0 | 1 | 0 | 0.9819 | 12.51% | 12.84% | -33.03% | 0.3786 |
| 0 | 1 | 0 | 0 | 1 | 1 | 0.9819 | 12.51% | 12.84% | -33.03% | 0.3786 |
| 0 | 1 | 0 | 1 | 0 | 0 | 0.8068 | 9.71% | 12.45% | -32.71% | 0.2968 |
| 0 | 1 | 0 | 1 | 0 | 1 | 0.9027 | 10.05% | 11.32% | -28.93% | 0.3474 |
| 0 | 1 | 0 | 1 | 1 | 0 | 0.9071 | 11.83% | 13.30% | -29.06% | 0.4070 |
| 0 | 1 | 0 | 1 | 1 | 1 | 1.0046 | 12.20% | 12.20% | -22.92% | 0.5321 |
| 0 | 1 | 1 | 0 | 0 | 0 | 1.0243 | 11.55% | 11.30% | -24.81% | 0.4656 |
| 0 | 1 | 1 | 0 | 0 | 1 | 1.0424 | 11.73% | 11.25% | -24.81% | 0.4729 |
| 0 | 1 | 1 | 0 | 1 | 0 | 1.0131 | 12.50% | 12.38% | -29.69% | 0.4210 |
| 0 | 1 | 1 | 0 | 1 | 1 | 1.0292 | 12.68% | 12.34% | -29.69% | 0.4271 |
| 0 | 1 | 1 | 1 | 0 | 0 | 0.9989 | 11.77% | 11.84% | -28.88% | 0.4075 |
| 0 | 1 | 1 | 1 | 0 | 1 | 1.1221 | 12.02% | 10.62% | -15.42% | 0.7798 |
| 0 | 1 | 1 | 1 | 1 | 0 | 1.0154 | 12.72% | 12.57% | -25.24% | 0.5039 |
| 0 | 1 | 1 | 1 | 1 | 1 | 1.1519 | 13.24% | 11.35% | -15.73% | 0.8416 |
| 1 | 0 | 0 | 0 | 0 | 0 | 0.9092 | 8.55% | 9.53% | -14.05% | 0.6087 |
| 1 | 0 | 0 | 0 | 0 | 1 | 0.9092 | 8.55% | 9.53% | -14.05% | 0.6087 |
| 1 | 0 | 0 | 0 | 1 | 0 | 1.0290 | 10.70% | 10.40% | -17.03% | 0.6282 |
| 1 | 0 | 0 | 0 | 1 | 1 | 1.0290 | 10.70% | 10.40% | -17.03% | 0.6282 |
| 1 | 0 | 0 | 1 | 0 | 0 | 0.9281 | 9.00% | 9.81% | -16.08% | 0.5601 |
| 1 | 0 | 0 | 1 | 0 | 1 | 0.9400 | 8.81% | 9.46% | -14.10% | 0.6248 |
| 1 | 0 | 0 | 1 | 1 | 0 | 0.9998 | 10.63% | 10.68% | -18.92% | 0.5619 |
| 1 | 0 | 0 | 1 | 1 | 1 | 1.0210 | 10.53% | 10.33% | -17.03% | 0.6182 |
| 1 | 0 | 1 | 0 | 0 | 0 | 1.0153 | 8.87% | 8.75% | -13.90% | 0.6381 |
| 1 | 0 | 1 | 0 | 0 | 1 | 1.0403 | 9.05% | 8.69% | -13.90% | 0.6507 |
| 1 | 0 | 1 | 0 | 1 | 0 | 1.0800 | 10.57% | 9.75% | -14.88% | 0.7105 |
| 1 | 0 | 1 | 0 | 1 | 1 | 1.1022 | 10.75% | 9.69% | -14.88% | 0.7224 |
| 1 | 0 | 1 | 1 | 0 | 0 | 1.0059 | 8.90% | 8.86% | -14.96% | 0.5948 |
| 1 | 0 | 1 | 1 | 0 | 1 | 1.0199 | 8.71% | 8.55% | -13.90% | 0.6265 |
| 1 | 0 | 1 | 1 | 1 | 0 | 1.0695 | 10.62% | 9.90% | -16.03% | 0.6625 |
| 1 | 0 | 1 | 1 | 1 | 1 | 1.0941 | 10.52% | 9.56% | -13.86% | 0.7592 |
| 1 | 1 | 0 | 0 | 0 | 0 | 0.9679 | 10.69% | 11.14% | -26.84% | 0.3982 |
| 1 | 1 | 0 | 0 | 0 | 1 | 0.9679 | 10.69% | 11.14% | -26.84% | 0.3982 |
| 1 | 1 | 0 | 0 | 1 | 0 | 1.1155 | 13.49% | 11.99% | -20.32% | 0.6640 |
| 1 | 1 | 0 | 0 | 1 | 1 | 1.1155 | 13.49% | 11.99% | -20.32% | 0.6640 |
| 1 | 1 | 0 | 1 | 0 | 0 | 0.8810 | 9.85% | 11.41% | -36.25% | 0.2718 |
| 1 | 1 | 0 | 1 | 0 | 1 | 0.9335 | 10.12% | 10.97% | -28.66% | 0.3531 |
| 1 | 1 | 0 | 1 | 1 | 0 | 1.0242 | 12.48% | 12.21% | -28.20% | 0.4424 |
| 1 | 1 | 0 | 1 | 1 | 1 | 1.0664 | 12.63% | 11.80% | -20.05% | 0.6296 |
| 1 | 1 | 1 | 0 | 0 | 0 | 1.0950 | 11.63% | 10.56% | -17.52% | 0.6635 |
| 1 | 1 | 1 | 0 | 0 | 1 | 1.1150 | 11.81% | 10.51% | -17.52% | 0.6738 |
| 1 | 1 | 1 | 0 | 1 | 0 | 1.1428 | 13.14% | 11.37% | -16.02% | 0.8198 |
| 1 | 1 | 1 | 0 | 1 | 1 | 1.1613 | 13.32% | 11.32% | -16.02% | 0.8311 |
| 1 | 1 | 1 | 1 | 0 | 0 | 1.1384 | 12.28% | 10.68% | -15.42% | 0.7964 |
| 1 | 1 | 1 | 1 | 0 | 1 | 1.1540 | 12.05% | 10.32% | -15.42% | 0.7816 |
| 1 | 1 | 1 | 1 | 1 | 0 | 1.1699 | 13.53% | 11.41% | -15.73% | 0.8604 |
| 1 | 1 | 1 | 1 | 1 | 1 | **1.2004** | 13.48% | 11.05% | **-15.73%** | **0.8571** |

(all-OFF = `000000` faithful AAA; all-ON = `111111` production CPM -- both bold.)

## Main effects (background-averaged, coded +-1; effect = mean|on - mean|off)

Sign-flip flag = factor's on-minus-off delta changes sign across backgrounds (direction not robust).

### CLEAN

| factor | dSharpe | flip | dCalmar | flip |
|---|---:|---|---:|---|
| **R** | +0.2041 | | +0.2326 | SIGN-FLIP |
| **C** | +0.1130 | | +0.2100 | SIGN-FLIP |
| **P** | +0.0481 | | +0.0876 | SIGN-FLIP |
| **U** | +0.0857 | SIGN-FLIP | +0.0615 | SIGN-FLIP |
| **S** | -0.0238 | SIGN-FLIP | +0.0469 | SIGN-FLIP |
| **W** | -0.0159 | SIGN-FLIP | +0.0343 | SIGN-FLIP |

### EXT

| factor | dSharpe | flip | dCalmar | flip |
|---|---:|---|---:|---|
| **C** | +0.0808 | | +0.1800 | SIGN-FLIP |
| **R** | +0.1007 | | +0.1387 | SIGN-FLIP |
| **W** | +0.0696 | SIGN-FLIP | +0.0957 | SIGN-FLIP |
| **P** | +0.0394 | | +0.0816 | SIGN-FLIP |
| **S** | -0.0092 | SIGN-FLIP | +0.0374 | SIGN-FLIP |
| **U** | +0.0593 | SIGN-FLIP | -0.0023 | SIGN-FLIP |

## Two-way interactions

Calmar (both windows), sorted by |CLEAN|:

| interaction | CLEAN | EXT |
|---|---:|---:|
| UxR | +0.1320 | +0.0997 |
| SxP | +0.0876 | +0.0769 |
| CxR | +0.0784 | +0.0480 |
| RxS | +0.0585 | +0.0382 |
| CxP | -0.0521 | -0.0475 |
| CxS | -0.0427 | -0.0567 |
| UxS | +0.0363 | +0.0141 |
| RxP | +0.0226 | +0.0159 |
| RxW | -0.0219 | -0.0099 |
| UxW | +0.0161 | +0.0246 |
| SxW | -0.0159 | +0.0017 |
| CxW | +0.0139 | +0.0174 |
| CxU | +0.0120 | -0.0039 |
| WxP | -0.0036 | +0.0064 |
| UxP | +0.0017 | -0.0084 |

### Key requested interactions

| interaction | meaning | CLEAN Calmar | EXT Calmar | CLEAN Sharpe | EXT Sharpe |
|---|---|---:|---:|---:|---:|
| RxW | ranker vs weighting | -0.0219 | -0.0099 | -0.0399 | -0.0281 |
| SxP | positive screen vs partial-safe (P bites only when S thins breadth < 4) | +0.0876 | +0.0769 | +0.0481 | +0.0292 |
| SxW | screen vs weighting (min-var vs inverse-vol on a thinned set) | -0.0159 | +0.0017 | -0.0051 | -0.0008 |
| RxS | ranker vs screen | +0.0585 | +0.0382 | +0.0167 | +0.0238 |
| UxR | universe vs ranker | +0.1320 | +0.0997 | +0.0743 | +0.0276 |
| CxS | screen vs canary (overlapping risk-off) | -0.0427 | -0.0567 | +0.0004 | -0.0001 |
| WxP | weighting vs partial-safe | -0.0036 | +0.0064 | -0.0012 | +0.0011 |

## Contribution ladder (dependency-respecting cumulative path)

Ordering = factors by CLEAN Calmar main effect, largest first, with P forced AFTER S (P is inert until S thins breadth below 4): **R -> C -> U -> S -> P -> W**.

### CLEAN cumulative path

| step | config (C,U,R,S,W,P) | Sharpe | Calmar | MaxDD |
|---|---|---:|---:|---:|
| all-OFF (faithful AAA) | `000000` | 0.7869 | 0.3188 | -23.21% |
| + R | `001000` | 0.9128 | 0.3637 | -23.54% |
| + C | `101000` | 1.0527 | 0.7203 | -12.96% |
| + U | `111000` | 1.2062 | 0.7491 | -17.52% |
| + S | `111100` | 1.2310 | 1.0500 | -12.99% |
| + P | `111101` | 1.2655 | 1.0378 | -12.99% |
| + W = all-ON (production) | `111111` | 1.1658 | 1.0137 | -12.97% |

CLEAN: Calmar is NOT monotone along this ladder (at least one step reduces Calmar) -- reported honestly; see the step deltas above.

### EXT cumulative path

| step | config (C,U,R,S,W,P) | Sharpe | Calmar | MaxDD |
|---|---|---:|---:|---:|
| all-OFF (faithful AAA) | `000000` | 0.8696 | 0.3624 | -23.21% |
| + R | `001000` | 0.9350 | 0.3623 | -23.54% |
| + C | `101000` | 1.0153 | 0.6381 | -13.90% |
| + U | `111000` | 1.0950 | 0.6635 | -17.52% |
| + S | `111100` | 1.1384 | 0.7964 | -15.42% |
| + P | `111101` | 1.1540 | 0.7816 | -15.42% |
| + W = all-ON (production) | `111111` | 1.2004 | 0.8571 | -15.73% |

EXT: Calmar is NOT monotone along this ladder (at least one step reduces Calmar) -- reported honestly; see the step deltas above.

## Caveats / confidence

- all-OFF cell reproduces the faithful AAA baseline (raw 6m momentum, top-4/8, weighted-cov min-variance, monthly, no canary/screen/partial-safe) and all-ON reproduces production `cpm_live.compute_target_weights` exactly (param==prod). Confidence high subject to the data constraint below.
- DATA CONSTRAINT: the faithful AAA universe is 10 assets but the panel lacks EWJ and RWX, so the all-OFF baseline and all U=OFF cells use the best-buildable 8-of-10 universe `['SPY', 'EFA', 'EEM', 'VNQ', 'IEF', 'TLT', 'DBC', 'GLD']`. The faithful-AAA anchor itself was computed under the same 8-of-10 constraint, so the gate is apples-to-apples.
- P (partial-safe) is defined coherently with S: with S OFF breadth == 4 so P is inert (risky_fraction == 1); with S ON the emptied slots route to safe at risky_fraction = min(breadth,4)/4. The P main effect is diluted because P is inert across the entire S-OFF half of the cube -- read it together with the S x P interaction and the ladder, where P is placed after S.
- W=OFF uses long-only SLSQP min-variance on the AAA weighted covariance (126d corr / 20d vol). Optimizer non-convergence falls back to equal-weight (rare); this matches the audit implementation.
- Grid internally consistent: shared harness, single EXT run sliced per window, identical cost/execution across all 64 cells.
- All numbers mooex / T+1 MOO exact / 10 bps/side / no vol gate (CPM has none). EXT 27y is partly proxy-backed pre-2006 for the trend universe; CLEAN 18y has full real-open coverage and is the decisive lens. CLEAN-only monotonicity vs any EXT non-monotonicity is reported honestly in the ladder section.
