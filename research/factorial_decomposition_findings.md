# Factorial Decomposition: Benchmark -> Production Sleeve -- Findings

Question: for each sleeve, decompose the transformation from its published TAA
benchmark to the production sleeve into independently-toggleable design
components, measure each component's main effect (averaged over all backgrounds,
so order-independent), detect interactions, derive a sensible ladder ordering,
and recommend whether the memo should present the full factorial or only the
derived ladder.

Two decompositions:

- AAA+TIP benchmark -> CPM sleeve (4 factors, 2^4 = 16 cells)
- HAA-Simple SPY benchmark -> BULL sleeve (3 factors, 2^3 = 8 cells)

Execution is identical for every cell, both benchmark and production endpoints:
realistic T+1 MOO exact (`mooex`), post-cost 10 bps/side, production slow vol
gate (RV_60d < RV_252d) wherever the vol-gate factor is ON. Every cell runs
through the same `_segment_returns_conv` harness from
`exec_lag_moo_validation_2026_05_30.py`, so cost model, rebalance timing, and
windows are byte-identical to the headline sleeve numbers.

- Reproduce: `.venv/bin/python research/factorial_decomposition_2026_05_30.py`
- Raw output: `research/factorial_decomposition_2026_05_30.json`
- Windows: CLEAN 18y (2008-05-30 .. 2026-05-22), EXT 27y (1999-03-10 .. 2026-05-22)
- Data: `cpm_live.load_panel` + real yfinance OHLC opens in `/tmp/cpm_open_cache/`;
  HAA defensive pool {BIL, AGG} via repo-standard stitches (BIL<-SHV pre-2007-05-30,
  AGG<-data/agg_stitched_daily.csv).

All tables are labeled config + window + execution. Codenames stripped.

---

## 1. Factor identification (diffed from code)

### CPM: AAA+TIP (build_dashboard.py:352 `bench_aaa_tip`) -> CPM (cpm_live.py `compute_target_weights`)

Four design components are distinct and independently toggleable. Each is binary;
off = benchmark setting, on = production setting.

| Factor | Off (benchmark / AAA+TIP) | On (production / CPM) |
|---|---|---|
| **U** equity universe | SPY-set: `SPY, EFA, EEM, VNQ, GLD, TLT, DBC` (7) | QQQ/SPHQ-set: `QQQ, SPHQ, EFA, EEM, VNQ, GLD, TLT, DBC` (8) |
| **R** ranker | 13612U momentum (Keller 1/3/6/12-mo avg) | vol-adjusted Faber: `faber_sma_xs / vol_252d` |
| **P** weighting | continuous min-variance over all top-half survivors (SLSQP, 504d cov) | 50/50 min-variance PAIR: pick best 2-asset min-var pair, equal-weight |
| **C** canary | TIP-only (`13612U(TIP) > 0`) | HYG OR TIP any-positive |

Components that are COMMON to both endpoints and therefore NOT factors (held
fixed-ON, flagged here so the factor set is auditable):

- **Top-half K cap.** Benchmark `max(2, ceil(7/2)) = 4`; production
  `max(2, min(4, N)) = 4`. Both cap at 4 candidates, so toggling it would be a
  no-op on these universes. Structurally coupled to U (the cap value derives from
  universe size) but evaluates to 4 on both sides; not an independent factor.
- **Positive-trend screen.** Both endpoints keep only survivors with positive
  trend (benchmark: 13612U > 0; production: raw Faber score > 0). The screen is
  always on; its positivity metric simply follows whatever ranker R is active, so
  it is bundled into R rather than separated.
- **SHV/IEF best-of-safe.** Both endpoints use `best_safe` over {SHV, IEF} by
  13612U. Identical defensive leg; not a factor.

Structural coupling flagged: **P (pairing) is meaningful only with >= 2 positive
survivors.** When fewer than 2 survive, both P settings fall back identically
(`{single: 0.5, safe: 0.5}` or `{safe: 1.0}`), so the P contrast is defined only
on risk-on months with breadth >= 2. Also expect a P x R interaction: the 50/50
pair concentrates into 2 names selected on the R-ranked, R-screened survivor set,
so the value of pairing depends on which ranker produced the survivors.

### BULL: HAA-Simple SPY -> BULL (bull_qqq_live.py `compute_bull_qqq_weights`)

Three distinct toggleable factors. Off = benchmark, on = production.

| Factor | Off (benchmark / HAA-Simple) | On (production / BULL) |
|---|---|---|
| **K** canary | TIP-only (`13612U(TIP) > 0`) | HYG OR TIP any-positive |
| **V** vol gate | none | RV_60d < RV_252d crossover |
| **S** safe pool | {BIL, AGG} best-of by 13612U | {SHV, IEF} best-of by 13612U |

Component COMMON to both endpoints, held fixed-ON, NOT a factor:

- **SPY 13612U > 0 trend gate.** Present in BOTH HAA-Simple (the "SPY held when
  ... SPY 13612U > 0" clause) and BULL (`_spy_trend_ok`). Identical on both sides,
  so toggling it is not part of the benchmark -> production transform. It is the
  shared risk-on backbone, not a CPM/BULL design choice. Listed as a candidate in
  the brief but ruled out here because it does not differ between the endpoints.

Safe-selection method note: the published HAA-Simple benchmark used `best_safe`,
while production BULL uses `_pick_safe`. These differ only in a one-month
NaN-handling edge case, not in design. To isolate the **pool** as the S factor
cleanly, the factorial holds the selection METHOD fixed at production's
`_pick_safe` and toggles only the pool. See the all-OFF anchor caveat below.

A clean factorization is achievable for both sleeves; no entanglement that forces
a stop.

---

## 2. Endpoint anchors (CLEAN 18y, mooex, post-cost)

| Sleeve | Cell | Sharpe | Calmar | MaxDD | Expected (published) | Verdict |
|---|---|---|---|---|---|---|
| CPM | all-OFF `URPC=0000` | 1.041 | 0.527 | -20.82% | AAA+TIP 1.041 / 0.527 / -20.82% | EXACT |
| CPM | all-ON `URPC=1111` | 1.242 | 0.870 | -16.35% | CPM 1.242 / 0.870 / -16.35% | EXACT |
| BULL | all-ON `KVS=111` | 1.081 | 0.857 | -13.35% | BULL 1.081 / 0.857 / -13.35% | EXACT |
| BULL | all-OFF `KVS=000` | 0.989 | 0.581 | -19.74% | HAA-Simple 0.960 / 0.561 / -19.74% | within 0.029 Sharpe |

CPM both endpoints reproduce the published numbers exactly. BULL all-ON
reproduces production exactly. BULL all-OFF differs from the previously published
HAA-Simple by +0.029 Sharpe / +0.020 Calmar; the residual is entirely the
safe-pick implementation (`_pick_safe` vs `best_safe` on a single month) and is
immaterial versus the ~0.3-0.4 bootstrap Sharpe CI. Holding the production
safe-method fixed is the correct choice so the S factor isolates only the pool.

The endpoints reproduce; proceeding with the full factorial.

---

## 3. Full factorial tables

### CPM 2^4 = 16 cells (mooex, post-cost 10 bps/side)

Config order is `URPC` (1 = production setting, 0 = benchmark setting).

| URPC | CLEAN Sharpe | CLEAN Calmar | CLEAN MaxDD | EXT Sharpe | EXT Calmar | EXT MaxDD |
|---|---|---|---|---|---|---|
| 0000 (AAA+TIP) | 1.041 | 0.527 | -20.82% | 1.065 | 0.522 | -20.82% |
| 0001 | 1.070 | 0.572 | -20.82% | 1.096 | 0.578 | -20.82% |
| 0010 | 0.980 | 0.590 | -17.68% | 1.022 | 0.588 | -18.54% |
| 0011 | 0.994 | 0.634 | -17.68% | 0.982 | 0.624 | -18.54% |
| 0100 | 1.193 | 0.843 | -15.03% | 1.138 | 0.760 | -15.03% |
| 0101 | 1.197 | 0.828 | -16.17% | 1.151 | 0.766 | -16.17% |
| 0110 | 1.110 | 0.678 | -17.42% | 1.112 | 0.635 | -18.28% |
| 0111 | 1.068 | 0.687 | -17.42% | 1.091 | 0.685 | -18.28% |
| 1000 | 1.199 | 0.642 | -20.40% | 1.193 | 0.617 | -20.40% |
| 1001 | 1.218 | 0.691 | -20.40% | 1.249 | 0.706 | -20.40% |
| 1010 | 1.142 | 0.749 | -17.21% | 1.169 | 0.740 | -17.61% |
| 1011 | 1.210 | 0.846 | -17.21% | 1.222 | 0.931 | -17.96% |
| 1100 | 1.260 | 0.883 | -15.15% | 1.167 | 0.777 | -15.15% |
| 1101 | 1.294 | 0.962 | -15.15% | 1.209 | 0.876 | -15.15% |
| 1110 | 1.155 | 0.760 | -16.35% | 1.119 | 0.700 | -16.76% |
| 1111 (CPM) | 1.242 | 0.870 | -16.35% | 1.164 | 0.832 | -16.76% |

Best CLEAN Sharpe/Calmar cell is `1101` (U+R+C, pairing OFF): 1.294 / 0.962.
Production `1111` adds pairing (P) and gives back ~0.05 Sharpe / ~0.09 Calmar in
the clean window -- pairing is a robustness/stability choice, not an in-sample
return enhancer (see ladder and caveats).

### BULL 2^3 = 8 cells (mooex, post-cost 10 bps/side)

Config order is `KVS` (1 = production, 0 = benchmark).

| KVS | CLEAN Sharpe | CLEAN Calmar | CLEAN MaxDD | EXT Sharpe | EXT Calmar | EXT MaxDD |
|---|---|---|---|---|---|---|
| 000 (HAA-Simple) | 0.989 | 0.581 | -19.74% | 0.973 | 0.530 | -19.74% |
| 001 | 0.984 | 0.569 | -20.41% | 0.974 | 0.526 | -20.41% |
| 010 | 1.107 | 0.549 | -19.17% | 1.019 | 0.468 | -19.17% |
| 011 | 1.101 | 0.819 | -13.35% | 1.021 | 0.710 | -13.35% |
| 100 | 1.020 | 0.644 | -19.74% | 0.937 | 0.578 | -19.74% |
| 101 | 1.038 | 0.643 | -20.41% | 0.953 | 0.580 | -20.41% |
| 110 | 1.067 | 0.567 | -19.17% | 0.900 | 0.464 | -19.17% |
| 111 (BULL) | 1.081 | 0.857 | -13.35% | 0.920 | 0.680 | -13.96% |

The deep-MaxDD improvement (-19.7% -> -13.4%) appears ONLY in cells where BOTH V
and S are on (`011`, `111`). Vol gate alone (`010`) or safe-pool swap alone
(`001`) does not deliver it. This is a textbook strong 2-way interaction.

---

## 4. Main effects and interactions

Main effect of a factor = mean metric delta from toggling it ON, averaged over
all 2^(k-1) backgrounds (balanced design, order-independent). Coded +-1.
`[FLIP]` marks a factor whose ON-vs-OFF delta changes sign across backgrounds
(i.e. its effect is interaction-dominated, not a stable independent contribution).

### CPM main effects

| Factor | CLEAN dSharpe | CLEAN dCalmar | EXT dSharpe | EXT dCalmar | avg |
|---|---|---|---|---|---|
| **U** universe | +0.134 | +0.130 | +0.105 | +0.128 | **+0.124** |
| **R** ranker | +0.083 | +0.158 | +0.019 [FLIP] | +0.091 [FLIP] | +0.088 |
| **C** canary | +0.027 [FLIP] | +0.052 [FLIP] | +0.023 [FLIP] | +0.082 | +0.046 |
| **P** pairing | -0.071 | -0.017 [FLIP] | -0.049 | +0.017 [FLIP] | -0.030 |

CPM largest 2-way interactions (Calmar, CLEAN): **R x P = -0.114** (by far the
biggest), U x C = +0.032, U x P = +0.028. On Sharpe (CLEAN): U x R = -0.038,
U x C = +0.025, R x P = -0.021.

Reading: **U (universe) is the single biggest, cleanest contributor** -- strongly
positive on both metrics in both windows, no sign flip. **R (ranker) is second**,
strong on Calmar, but its Sharpe effect is interaction-dependent (the R x P term
is the dominant interaction: the vol-Faber ranker and the 50/50 pair partly
substitute for each other). **C (canary) is a small net-positive** but
direction-unstable. **P (pairing) is net-negative in-sample** -- it concentrates
into 2 names and costs Sharpe/Calmar versus continuous min-var; its value is
robustness (the code documents lower pick-flip rate under price perturbation),
not headline metrics.

### BULL main effects

| Factor | CLEAN dSharpe | CLEAN dCalmar | EXT dSharpe | EXT dCalmar | avg |
|---|---|---|---|---|---|
| **S** safe pool | +0.005 [FLIP] | +0.137 [FLIP] | +0.009 | +0.114 [FLIP] | +0.066 |
| **V** vol gate | +0.081 | +0.089 [FLIP] | +0.006 [FLIP] | +0.027 [FLIP] | +0.051 |
| **K** canary | +0.006 [FLIP] | +0.048 | -0.069 | +0.017 [FLIP] | +0.000 |

BULL largest 2-way interaction: **V x S = +0.143 (CLEAN Calmar), +0.115 (EXT
Calmar)** -- dwarfs every main effect. K x V = -0.036.

Reading: BULL main effects are **interaction-dominated and pervasively
sign-flipping**. The honest story is not three independent contributions but one
dominant **V x S interaction**: the vol gate (V) sends the sleeve to safe more
often, and only the {SHV, IEF} safe pool (S) converts that into deep-drawdown
protection; {BIL, AGG} does not. Neither V nor S alone moves MaxDD; together they
cut it ~6pp. K (canary breadth) is essentially a zero net contributor and is the
least stable (negative on EXT Sharpe).

---

## 5. Derived ordering and incremental ladder

Ordering rule: descending average |main effect| across Sharpe + Calmar + both
windows, breaking ties / placing interaction-coupled and robustness factors last
so each rung is as interpretable as possible.

### CPM derived ordering: U -> R -> C -> P

(universe first as the foundational equity expression and biggest clean effect;
ranker second; canary third; pairing last as the R-coupled robustness factor that
is net-negative in-sample.)

| Rung | Config | CLEAN Sharpe | CLEAN Calmar | CLEAN MaxDD | EXT Sharpe | EXT Calmar |
|---|---|---|---|---|---|---|
| 0. AAA+TIP | 0000 | 1.041 | 0.527 | -20.82% | 1.065 | 0.522 |
| 1. + universe (U) | 1000 | 1.199 | 0.642 | -20.40% | 1.193 | 0.617 |
| 2. + ranker (R) | 1100 | 1.260 | 0.883 | -15.15% | 1.167 | 0.777 |
| 3. + canary (C) | 1101 | 1.294 | 0.962 | -15.15% | 1.209 | 0.876 |
| 4. + pairing (P) = CPM | 1111 | 1.242 | 0.870 | -16.35% | 1.164 | 0.832 |

U and R do the heavy lifting (Sharpe 1.041 -> 1.260, Calmar 0.527 -> 0.883, MaxDD
-20.8% -> -15.2% in the clean window across the first two rungs). C adds a small
top. P (pairing) gives back ~0.05 Sharpe / ~0.09 Calmar in-sample -- the rung
where production trades a little measured performance for selection robustness.

### BULL derived ordering: V -> S -> K

(vol gate first as the headline production addition with the largest standalone
Sharpe lift and the trigger for the V x S interaction; safe pool second to realize
the joint DD protection; canary last as the near-zero, least-stable factor. The
V x S interaction means the first two rungs must be read together.)

| Rung | Config | CLEAN Sharpe | CLEAN Calmar | CLEAN MaxDD | EXT Sharpe | EXT Calmar |
|---|---|---|---|---|---|---|
| 0. HAA-Simple | 000 | 0.989 | 0.581 | -19.74% | 0.973 | 0.530 |
| 1. + vol gate (V) | 010 | 1.107 | 0.549 | -19.17% | 1.019 | 0.468 |
| 2. + safe {SHV,IEF} (S) | 011 | 1.101 | 0.819 | -13.35% | 1.021 | 0.710 |
| 3. + canary (K) = BULL | 111 | 1.081 | 0.857 | -13.35% | 0.920 | 0.680 |

Rung 1 (vol gate) lifts Sharpe but NOT Calmar (DD still -19.2%, because the safe
leg is still {BIL, AGG}). Rung 2 (safe pool) is where the interaction fires: MaxDD
collapses to -13.4% and Calmar jumps 0.549 -> 0.819. Rung 3 (canary) adds a touch
of clean Calmar but costs EXT Sharpe -- consistent with K being the weakest,
sign-flipping factor.

---

## 6. Presentation recommendation

Recommendation: **the memo should lead with the derived ladders (Section 5), plus
a compact main-effects callout, and relegate the full factorial tables to an
appendix.** Treat the two sleeves slightly differently:

- **CPM: ladder-first is clean and defensible.** Factors separate well: U and R
  are large, stable, single-signed contributors; the ladder U -> R -> C -> P tells
  the whole story in four interpretable rungs, and the only material interaction
  (R x P) is exactly captured by ordering P last. Show the ladder as the narrative;
  a 4-row main-effects table is a useful supporting exhibit; the 16-cell table is
  appendix-only confirmation. Explicitly state that pairing (P) is a robustness
  choice that costs ~0.05 Sharpe in-sample, so readers do not mistake it for an
  alpha rung.

- **BULL: lead with the V x S interaction, NOT independent main effects.** BULL's
  main effects are interaction-dominated and pervasively sign-flipping, so a
  main-effects table presented as "independent contributions" would be misleading.
  The correct exhibit is the ladder V -> S -> K WITH an explicit note that rungs 1
  and 2 must be read together (the ~6pp MaxDD / +0.27 Calmar win requires both the
  vol gate and the {SHV, IEF} safe pool). The 8-cell table is small enough to
  include inline as evidence of the interaction; do not publish BULL main effects
  as standalone attributions.

In short: derived ladders are the primary memo artifact for both sleeves; the full
factorial belongs in an appendix for CPM and inline-as-interaction-evidence for
BULL. The factorial's main value here was methodological -- it proved the ladder
ordering is robust to build order (CPM) and exposed that BULL's design is a joint
interaction rather than a sum of parts (which a single sequential ablation would
have hidden depending on order).

---

## 7. Caveats and confidence

- **Per-cell and per-rung deltas are mostly within the ~0.3-0.4 bootstrap Sharpe
  CI width.** This decomposition shows direction and cumulative build, not
  statistically significant per-step alpha. Treat individual rung deltas as
  directional, the cumulative endpoint-to-endpoint moves as the robust signal.
- **Main effects are averages over backgrounds.** Factors flagged `[FLIP]`
  (CPM: C, and R/P in some cells; BULL: K, and V/S on Calmar) change sign across
  backgrounds -- their listed main effect is a background-average that masks strong
  interaction. For these, the ladder/interaction view is more honest than the
  main-effect number.
- **BULL is interaction-dominated.** The V x S interaction (+0.14 Calmar) exceeds
  every BULL main effect; BULL main effects should not be read as independent
  contributions.
- **Pairing (P) is net-negative in-sample for CPM.** Production keeps it for
  selection robustness (documented lower pick-flip rate under price perturbation),
  a property this return/DD factorial does not measure.
- **all-OFF BULL anchor** reproduces HAA-Simple within 0.029 Sharpe; the residual
  is the safe-pick method (`_pick_safe` vs `best_safe`), held fixed at production's
  method so the S factor isolates only the pool. Immaterial vs the CI.
- **Fixed-on common components** (top-half K cap, positive-trend screen, SHV/IEF
  safe for CPM; SPY 13612U trend gate for BULL) were verified identical on both
  endpoints and are not part of the factorial; their contribution is embedded in
  the shared baseline, not attributed to any rung.
- **Confidence: high** on the qualitative findings (anchors reproduce the
  headline numbers exactly for three of four endpoints and within 0.03 Sharpe for
  the fourth; ordering and interaction structure are stable across both windows).
  **Moderate** on any single rung's magnitude (CI-limited).

## Methodological lesson (generalizable)

Sequential (one-at-a-time) ablation attributes contribution in a single build
order and is order-dependent: it would have hidden the CPM R x P substitution and
the BULL V x S complementarity entirely, or assigned their joint effect to
whichever factor happened to be toggled first. A full 2^k factorial with main
effects + interactions solves the order-dependence (main effects are
background-averaged) AND surfaces the interactions that decide whether a "ladder"
is even a valid mental model. Use a factorial (not sequential ablation) whenever
strategy components might substitute for or complement each other, then derive the
ladder from the main effects rather than assuming one.
