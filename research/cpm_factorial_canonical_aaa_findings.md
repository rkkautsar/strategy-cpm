# CPM 2^4 factorial -- RE-ANCHORED at canonical AAA (no canary)

Date: 2026-05-30. Role: analyst (read-only re production, no production change, no commit).
Script: `research/cpm_factorial_canonical_aaa.py` -> `research/cpm_factorial_canonical_aaa.json`
(console log `research/cpm_factorial_canonical_aaa.log`).

> SUPERSEDES the AAA+TIP-anchored CPM 2^4 factorial in
> `research/factorial_decomposition_2026_05_30.py` /
> `research/factorial_decomposition_findings.md` (CPM side, entirely).
> Canonical AAA (no canary) is the sole CPM benchmark and the all-OFF anchor.
> AAA+TIP and every TIP-inclusive hybrid are dropped from the CPM grid.
> The BULL (HAA-simple-anchored 2^3) factorial is unchanged and not re-run here.

## Factor definitions (off = canonical AAA setting / on = CPM production setting)

| factor | OFF (canonical AAA) | ON (CPM production) |
|---|---|---|
| **U** universe | SPY-set `["SPY","EFA","EEM","VNQ","GLD","TLT","DBC"]` | QQQ/quality-set `["QQQ","SPHQ","EFA","EEM","VNQ","GLD","TLT","DBC"]` |
| **R** ranker | 13612U momentum | vol-adjusted Faber (10m-SMA-distance / RV_252d) |
| **P** pair weighting | continuous min-variance over survivors (SLSQP) | equal-weight 50/50 minimum-variance pair |
| **C** canary | **NONE (no risk-off gate)** | HYG-OR-TIP any-positive 13612U gate |

Key re-anchoring: **C OFF is now NO canary** (canonical AAA), not the prior
TIP-only baseline. Common fixed-on settings (NOT factors): top-half K cap
(ceil(n/2), =4 either universe), positive-momentum/positive-trend screen,
SHV/IEF best-of-safe, cov lookback tail(504). all-OFF (U=R=P=C=0) reproduces
canonical AAA; all-ON (1,1,1,1) reproduces CPM production.

## Execution convention (every table below)

Realistic T+1 MOO exact (`mooex`), post-cost 10 bps/side, via the shared
`_segment_returns_conv` harness so cost/window/execution are byte-identical
across all 16 cells. CPM sleeve has NO vol gate, so no vol gate is applied.
Windows: CLEAN 18y (2008-05-30 .. 2026-05-22), EXT 27y (1999-03-10 .. 2026-05-22).
Full panel runs once over EXT and is sliced to each window.

## Anchor checks (CLEAN 18y, mooex) -- BOTH PASS

| anchor | Sharpe | Calmar | MaxDD | expected | status |
|---|---|---|---|---|---|
| all-OFF `0000` (canonical AAA) | 0.970 | 0.556 | -20.65% | 0.970 / 0.556 / -20.65% | EXACT |
| all-ON `1111` (CPM production) | 1.242 | 0.870 | -16.35% | 1.242 / 0.870 / -16.35% | EXACT |

Both endpoints reproduce to the reported precision. Grid proceeds.

## Full 16-cell grid -- CLEAN 18y (2008-05-30 .., mooex, 10 bps/side)

Config column order: U,R,P,C.

| U | R | P | C | Sharpe | CAGR | Vol | MaxDD | Calmar |
|---|---|---|---|---|---|---|---|---|
| 0 | 0 | 0 | 0 | 0.970 | 11.48% | 12.00% | -20.65% | 0.556 |
| 0 | 0 | 0 | 1 | 1.070 | 11.90% | 11.14% | -20.82% | 0.572 |
| 0 | 0 | 1 | 0 | 0.873 | 10.47% | 12.33% | -23.74% | 0.441 |
| 0 | 0 | 1 | 1 | 0.994 | 11.20% | 11.40% | -17.68% | 0.634 |
| 0 | 1 | 0 | 0 | 1.002 | 12.08% | 12.17% | -20.66% | 0.585 |
| 0 | 1 | 0 | 1 | 1.197 | 13.39% | 11.06% | -16.17% | 0.828 |
| 0 | 1 | 1 | 0 | 0.802 |  9.83% | 12.78% | -36.09% | 0.272 |
| 0 | 1 | 1 | 1 | 1.068 | 11.97% | 11.23% | -17.42% | 0.687 |
| 1 | 0 | 0 | 0 | 1.100 | 13.66% | 12.39% | -20.22% | 0.676 |
| 1 | 0 | 0 | 1 | 1.218 | 14.10% | 11.41% | -20.40% | 0.691 |
| 1 | 0 | 1 | 0 | 1.064 | 13.74% | 12.94% | -22.76% | 0.604 |
| 1 | 0 | 1 | 1 | 1.210 | 14.55% | 11.86% | -17.21% | 0.846 |
| 1 | 1 | 0 | 0 | 1.170 | 14.12% | 11.94% | -18.32% | 0.771 |
| 1 | 1 | 0 | 1 | **1.294** | 14.57% | 11.03% | **-15.15%** | **0.962** |
| 1 | 1 | 1 | 0 | 1.022 | 12.85% | 12.67% | -35.27% | 0.364 |
| 1 | 1 | 1 | 1 | 1.242 | 14.23% | 11.27% | -16.35% | 0.870 |

Best CLEAN cell = `1101` (U,R,C on; P off = continuous min-var):
Sharpe 1.294 / Calmar 0.962 / MaxDD -15.15% -- it dominates all-ON CPM `1111`
on all three metrics.

## Full 16-cell grid -- EXT 27y (1999-03-10 .., mooex, 10 bps/side)

Config column order: U,R,P,C.

| U | R | P | C | Sharpe | CAGR | Vol | MaxDD | Calmar |
|---|---|---|---|---|---|---|---|---|
| 0 | 0 | 0 | 0 | 1.032 | 11.91% | 11.55% | -20.65% | 0.577 |
| 0 | 0 | 0 | 1 | 1.096 | 12.05% | 10.92% | -20.82% | 0.578 |
| 0 | 0 | 1 | 0 | 0.928 | 11.44% | 12.52% | -24.54% | 0.466 |
| 0 | 0 | 1 | 1 | 0.982 | 11.56% | 11.86% | -18.54% | 0.624 |
| 0 | 1 | 0 | 0 | 1.026 | 11.70% | 11.42% | -20.66% | 0.566 |
| 0 | 1 | 0 | 1 | 1.151 | 12.38% | 10.63% | -16.17% | 0.766 |
| 0 | 1 | 1 | 0 | 0.929 | 11.41% | 12.48% | -36.76% | 0.310 |
| 0 | 1 | 1 | 1 | 1.091 | 12.52% | 11.41% | -18.28% | 0.685 |
| 1 | 0 | 0 | 0 | 1.166 | 14.19% | 12.00% | -20.22% | 0.702 |
| 1 | 0 | 0 | 1 | **1.249** | 14.39% | 11.28% | -20.40% | 0.706 |
| 1 | 0 | 1 | 0 | 1.146 | 16.47% | 14.18% | -23.13% | 0.712 |
| 1 | 0 | 1 | 1 | 1.222 | 16.72% | 13.38% | -17.96% | **0.931** |
| 1 | 1 | 0 | 0 | 1.140 | 13.17% | 11.43% | -18.32% | 0.719 |
| 1 | 1 | 0 | 1 | 1.209 | 13.27% | 10.79% | -15.15% | 0.876 |
| 1 | 1 | 1 | 0 | 1.047 | 13.36% | 12.75% | -35.59% | 0.375 |
| 1 | 1 | 1 | 1 | 1.164 | 13.95% | 11.82% | -16.76% | 0.832 |

Best EXT cells: Calmar `1011` (U,P,C on; R off) 0.931; Sharpe `1001` (U,C on)
1.249. all-ON CPM `1111` (0.832 / 1.164) is again not the EXT grid optimum.

## Main effects (background-averaged, coded +-1; effect = mean|on - mean|off)

Sign-flip flag = factor's on-minus-off delta changes sign across backgrounds
(effect direction not robust).

### CLEAN 18y

| factor | dSharpe | flip | dCalmar | flip |
|---|---|---|---|---|
| **C** canary | +0.1612 |  | **+0.2277** |  |
| **U** universe | **+0.1683** |  | +0.1512 |  |
| **P** pairing | -0.0931 |  | -0.1152 | SIGN-FLIP |
| **R** ranker | +0.0370 | SIGN-FLIP | +0.0402 | SIGN-FLIP |

### EXT 27y

| factor | dSharpe | flip | dCalmar | flip |
|---|---|---|---|---|
| **U** universe | **+0.1385** |  | +0.1601 |  |
| **C** canary | +0.0938 |  | **+0.1963** |  |
| **P** pairing | -0.0701 |  | -0.0692 | SIGN-FLIP |
| **R** ranker | -0.0078 | SIGN-FLIP | -0.0206 | SIGN-FLIP |

Reading:
- **U and C are the two robust value-adders** (no sign-flips, top-2 on both
  metrics/windows). U is the largest Sharpe driver; C is the largest Calmar driver.
- **P (50/50 pairing) has a NEGATIVE main effect** on both metrics/windows --
  on average it subtracts value vs continuous min-variance. Calmar flag is a
  sign-flip: P helps in some backgrounds, hurts in others (see RxP below).
- **R (vol-Faber ranker) is the weakest factor**, near zero and sign-flipping on
  both metrics/windows; on EXT its mean effect is slightly negative.

## Largest 2-way interactions (Calmar, both windows)

| interaction | CLEAN | EXT | reading |
|---|---|---|---|
| **R x P** | -0.1226 | -0.1118 | strongest: ranker and pairing are SUBSTITUTES (want one, not both) |
| **P x C** | +0.1112 | +0.1058 | canary unlocks pairing value (pair only safe behind a risk-off gate) |
| **R x C** | +0.1112 | +0.1006 | canary unlocks ranker value too |
| U x R | -0.0025 | -0.0413 | mild |
| U x P | +0.0113 | +0.0313 | mild |
| U x C | +0.0110 | +0.0130 | mild |

The R x P substitution explains P's negative main effect and sign-flip: with the
vol-Faber ranker ON, adding the 50/50 pair hurts (e.g. CLEAN `1101` Calmar 0.962
-> `1111` 0.870); with R OFF, the pair helps (CLEAN `1001` 0.691 -> `1011` 0.846).
Both R and P reduce concentration risk; stacking them over-diversifies. P x C and
R x C show why pairing/ranker carry negative or flat main effects when averaged
over canary-OFF backgrounds: without a risk-off gate they ride equity drawdowns
(see `0110`/`1110` MaxDD ~ -35%); the canary is what makes them safe to deploy.

## Derived ladder ordering + cumulative path

Ordering = value-adding factors first by |Calmar main effect|, value-subtracting
factor last, respecting the R/P structural coupling: **C -> U -> R -> P**.
(C largest Calmar effect; U next and robust; R the marginal ranker; P last
because its main effect is negative and it is a substitute for R.)

### CLEAN 18y cumulative path

| step | config (U,R,P,C) | Sharpe | Calmar | MaxDD |
|---|---|---|---|---|
| all-OFF (canonical AAA) | `0000` | 0.970 | 0.556 | -20.65% |
| + C (canary) | `0001` | 1.070 | 0.572 | -20.82% |
| + U (universe) | `1001` | 1.218 | 0.691 | -20.40% |
| + R (ranker) | `1101` | **1.294** | **0.962** | **-15.15%** |
| + P (pairing) = all-ON CPM | `1111` | 1.242 | 0.870 | -16.35% |

### EXT 27y cumulative path

| step | config (U,R,P,C) | Sharpe | Calmar | MaxDD |
|---|---|---|---|---|
| all-OFF (canonical AAA) | `0000` | 1.032 | 0.577 | -20.65% |
| + C (canary) | `0001` | 1.096 | 0.578 | -20.82% |
| + U (universe) | `1001` | 1.249 | 0.706 | -20.40% |
| + R (ranker) | `1101` | 1.209 | 0.876 | -15.15% |
| + P (pairing) = all-ON CPM | `1111` | 1.164 | 0.832 | -16.76% |

The ladder rises monotonically through C, U, R, then the final step (+P) is
NEGATIVE in both windows: all-ON CPM `1111` is dominated by `1101` (U,R,C on,
continuous min-var). The 50/50 pair is the one value-subtracting CPM component
on the canonical-AAA-anchored grid; CPM production carries it for governance/
robustness reasons, not raw backtest Calmar.

## Canary: re-anchoring effect (none -> HYG-OR-TIP) is far larger than the prior swap

Re-anchoring C from TIP-only to NONE makes the canary one of the two dominant CPM
components, where under the old anchor it was the smallest.

| framing | dSharpe (CLEAN) | dCalmar (CLEAN) |
|---|---|---|
| OLD C main effect (TIP-only -> HYG-OR-TIP swap, AAA+TIP anchor) | +0.0266 | +0.0523 |
| NEW C main effect (none -> HYG-OR-TIP, canonical-AAA anchor) | +0.1612 | +0.2277 |

C jumps from rank-4 (smallest) under the old anchor to rank-1 on Calmar / rank-2
on Sharpe under the new anchor. Most of the canary's value is the EXISTENCE of a
risk-off gate at all, not which inputs feed it.

### Universe-dependence confirmed (canary large only on equity-heavy universe)

Production-structure canary contrast (U,R,P all ON; C none `1110` -> HYG-OR-TIP
`1111`), reconciling against `research/cpm_vs_canonical_aaa_findings.md`:

| window | dSharpe | dCalmar | dMaxDD | scoped finding |
|---|---|---|---|---|
| CLEAN | +0.2205 | +0.5061 | +18.92pp | matches +0.220 / +0.506 / +18.92pp EXACT |
| EXT | +0.1170 | +0.4568 | +18.83pp | matches +0.117 / +0.457 / +18.83pp EXACT |

On the QQQ/quality (equity-heavy) universe with no canary, MaxDD blows out to
~-35% (`1110` -35.27% CLEAN, `0110` -36.09%); the HYG-OR-TIP gate cuts that to
~-16%. On the diversified AAA cross-asset universe the same canary is nearly inert
for drawdown (~0.2pp, per the scoped findings: canonical AAA -20.65% vs AAA+TIP
-20.82%): the AAA universe self-defends via bond/cash momentum, so the canary
adds little there. The averaged main effect (CLEAN dCalmar +0.2277) sits below
the production-structure single contrast (+0.5061) precisely because it averages
the large equity-universe gain with the near-zero AAA-universe gain -- i.e. the
canary's value is universe-dependent, as the scoped work found. HYG-only remains
the dominant single canary input per the scoped decomposition (CLEAN 1.328 /
1.116 / -13.12%); HYG-OR-TIP trades a hair of raw performance for breadth/
governance robustness.

## Caveats / confidence

- Both anchors reproduce EXACTLY (`0000` = canonical AAA 0.970/0.556/-20.65%;
  `1111` = CPM 1.242/0.870/-16.35%); production-structure canary contrast
  reproduces the scoped findings exactly in both windows. Confidence high.
- Grid internally consistent: shared harness, single EXT run sliced per window,
  identical cost/execution across all 16 cells.
- Main-effect averaging hides the universe-dependence of C and the R/P
  substitution; read main effects together with the interaction table and the
  ladder, not in isolation.
- All numbers mooex / T+1 MOO exact / 10 bps/side / no vol gate (CPM has none).
  No same-day/MOC numbers. No codenames.
- The grid shows `1101` (drop the 50/50 pair) dominates all-ON CPM on backtest
  Sharpe/Calmar/MaxDD in both windows. This is an observation about the factorial,
  not a production recommendation; pairing's governance/robustness rationale is
  out of scope here.

## Key numbers

- all-OFF canonical AAA anchor: CLEAN 0.970 / 0.556 / -20.65%; EXT 1.032 / 0.577 / -20.65%.
- all-ON CPM anchor: CLEAN 1.242 / 0.870 / -16.35%; EXT 1.164 / 0.832 / -16.76%.
- Robust value-adders: U (Sharpe lead) and C (Calmar lead), no sign-flips.
- P (50/50 pair) negative main effect both windows; R (vol-Faber) weakest, sign-flips.
- Dominant interaction R x P -0.12 (substitutes); P x C and R x C +0.11 (canary unlocks both).
- New canary main effect (none -> HYG-OR-TIP): CLEAN dSharpe +0.1612 / dCalmar +0.2277,
  vs old TIP-swap +0.0266 / +0.0523. Universe-dependent (large on QQQ/quality, inert on AAA).
- Grid optimum: CLEAN `1101` 1.294 / 0.962 / -15.15%; EXT `1011` Calmar 0.931.
