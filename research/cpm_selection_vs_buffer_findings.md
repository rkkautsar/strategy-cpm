# CPM: min-var SELECTION vs permanent SAFE BUFFER -- lever decomposition

Status: throwaway research, read-only re production, no production files changed, no commit.

## Question / hypothesis

Prior min-var variants conflated two distinct levers. Decompose them cleanly:

1. min-var SELECTION -- which 3 names (min-var 3-of-4 vs prod top-4 rank).
2. PERMANENT SAFE BUFFER `b` -- a Permanent-Portfolio-style floor allocation to
   the timed safe (best-of SHV/IEF by 13612U), held EVEN at full breadth, ON TOP
   of prod's existing strict-4 breadth scaling.

Test whether the buffer earns an independent risk-adjusted place (PP thesis),
whether it is regime-robust (the 2022 bonds-and-equities-both-fell tell), and
whether the two levers are complementary or redundant.

## Method

- Engine: `research/cpm_harness.py` (mooex T+1 MOO, both-252, 10 bps/side).
  Anchor verified FIRST: Sharpe 1.1658, MaxDD -0.1297, Calmar 1.0137.
- Script: `research/cpm_selection_vs_buffer.py` (`.venv/bin/python -m research.cpm_selection_vs_buffer`).
- Buffer composition (exact):
  - `prod_risky_fraction = min(n_pos, 4)/4` (strict-4 breadth; n_pos = positive-faber
    names in the top-4 rank pool, byte-identical to prod).
  - `effective_risky = (1 - b) * prod_risky_fraction`; `safe_fraction = 1 - effective_risky`.
  - At full breadth (n_pos>=4): effective_risky = (1-b), safe = b -> exact PP-style floor.
  - Below full breadth, prod strict-4 de-risk compounds multiplicatively with `b`.
- GATE: rank selection (top-4) with b=0 reproduces the anchor. Confirmed: prod_b0
  Sharpe = 1.1658 (assert passed).
- Everything else byte-identical to prod: universe, canary HYG-or-TIP any_positive,
  vol-adj Faber rank, both-252, inv-vol sizing.
- Significance metrics are path-independent (Sharpe, Sortino). Sortino uses MAR=0,
  daily downside deviation annualized.
- Bootstrap: paired block, B=2000, block=21, seed=42 (mirrors
  `cpm_weighting_corr.paired_block_bootstrap` resampling exactly; extended to
  report dSharpe AND dSortino).

## 2x2 (clean window, decision; net 10 bps)

| cell | Sharpe | Sortino | Calmar | Martin | MaxDD | CAGR | vol | turn |
|---|---|---|---|---|---|---|---|---|
| prod_b0 (PROD) | 1.1658 | 1.6629 | 1.0137 | 3.69 | -0.1297 | 0.1315 | 0.1118 | 2.58 |
| prod_b25 (BUFFER) | 1.2019 | 1.7223 | 1.0861 | 3.84 | -0.0968 | 0.1051 | 0.0867 | 2.46 |
| minvar_b0 (SELECTION, var A) | 1.2622 | 1.8036 | 1.2196 | 3.95 | -0.1135 | 0.1384 | 0.1076 | 2.99 |
| minvar_b25 (BOTH, var B) | 1.2867 | 1.8474 | 1.2860 | 4.14 | -0.0856 | 0.1100 | 0.0842 | 2.76 |

Ext window (1999-03-10..) same ordering holds: prod_b0 Sh 1.2004, prod_b25 1.2505,
minvar_b0 1.2624, minvar_b25 1.3015. Selection and buffer both improve Sharpe/Sortino
in ext too; min-var remains the larger mover.

## Buffer sweep on prod selection (clean) -- PP-style frontier

| b | Sharpe | Sortino | Calmar | Martin | MaxDD | CAGR | vol |
|---|---|---|---|---|---|---|---|
| 0.00 | 1.1658 | 1.6629 | 1.0137 | 3.69 | -0.1297 | 0.1315 | 0.1118 |
| 0.10 | 1.1813 | 1.6877 | 1.0372 | 3.77 | -0.1167 | 0.1210 | 0.1015 |
| 0.25 | 1.2019 | 1.7223 | 1.0861 | 3.84 | -0.0968 | 0.1051 | 0.0867 |
| 0.40 | 1.2093 | 1.7398 | 1.0197 | 3.74 | -0.0874 | 0.0732* | 0.0732 |

(*CAGR at b=0.40 = 0.0891; vol 0.0732.)

Frontier read: vol, MaxDD, CAGR all fall monotonically with b. Sharpe and Sortino
creep UP monotonically but flatten. Calmar and Martin PEAK at b=0.25 then fall at
b=0.40 (overshooting the de-risk past the drawdown benefit). So the risk-adjusted
sweet spot by Calmar/Martin is ~b=0.25; Sharpe keeps inching but each increment of
b costs progressively more CAGR for less Sharpe.

## Per-crisis (ext curve), incl the 2022 tell

GFC 2007-10..2009-06:  prod_b0 Sh +0.54 / prod_b25 +0.68 / minvar_b0 +0.74 / minvar_b25 +0.86. MaxDD -0.119 -> -0.097 -> -0.103 -> -0.085.
COVID 2020-02..06:     prod_b0 +1.19 / prod_b25 +1.45 / minvar_b0 +1.25 / minvar_b25 +1.49.
2022 full year:        prod_b0 Sh -0.299 / prod_b25 -0.250 / minvar_b0 -0.114 / minvar_b25 -0.060. MaxDD -0.080 -> -0.060 -> -0.062 -> -0.047. vol 0.064 -> 0.048.
2025 tariff:           prod_b0 +0.240 / prod_b25 +0.233 / minvar_b0 +0.243 / minvar_b25 +0.236 (Sharpe ~flat; MaxDD -0.130 -> -0.097, vol down).

2022 regime read (the key risk): the timed safe held SHV every month of 2022
(verified: best_safe = SHV Jan..Dec 2022; it correctly avoided IEF during the
rate-rise). So the permanent buffer parked in SHV/cash, not in falling bonds. In
the one regime where a permanent bond sleeve would backfire, the buffer still
HELPED: less-negative Sharpe (-0.299 -> -0.250), smaller MaxDD (-0.080 -> -0.060),
lower vol. The buffer benefit is NOT 2008-2021 bond-bull-dependent; the SHV/IEF
timing neutralizes the 2022 regime risk. In 2025 (tariff) the buffer is Sharpe-flat
but still cuts MaxDD/vol -- a clean de-risk with no risk-adjusted cost.

## Bootstrap (paired block, B=2000, block=21, seed=42; net 10 bps)

| effect | dSharpe mean [95% CI] p>0 | dSortino mean [95% CI] p>0 |
|---|---|---|
| SELECTION main (prod -> minvar, b=0) | +0.097 [-0.005, +0.196] 0.968 | +0.142 [-0.015, +0.297] 0.961 |
| BUFFER main (b=0 -> b=0.25, prod sel) | +0.038 [-0.034, +0.108] 0.857 | +0.062 [-0.048, +0.172] 0.872 |
| buffer on minvar (b=0 -> 0.25) | +0.026 [-0.046, +0.097] 0.776 | +0.047 [-0.067, +0.158] 0.804 |
| selection at b=0.25 | +0.085 [-0.015, +0.183] 0.955 | +0.126 [-0.028, +0.276] 0.946 |
| BOTH vs prod (minvar_b25 - prod_b0) | +0.123 [-0.009, +0.252] 0.966 | +0.188 [-0.007, +0.387] 0.969 |

All 95% CIs include 0 (single in-sample, in-noise discipline). Strength ordering by
p>0: SELECTION (0.96-0.97) >> BUFFER (0.86-0.87). The joint effect is the strongest
signal (0.97).

## Answers

(a) Does the permanent buffer beat prod risk-adjusted, or is it just de-risking?
   Mostly de-risking with a small, NOT-significant risk-adjusted tilt. prod_b25
   raises Sharpe +0.036 and Sortino +0.059, but the bootstrap CI includes 0
   (p>0 ~0.86-0.87). Meanwhile CAGR drops 13.2% -> 10.5% and vol 11.2% -> 8.7%.
   Verdict: the buffer is primarily a leverage/vol-target dial, not alpha. The
   Sharpe nudge is real in direction and monotone across the sweep, but not
   statistically distinguishable from a pure de-risk.

(b) Regime-robust or bond-bull-dependent? Regime-robust. The buffer helped in ALL
   four crises including 2022, where the timed safe held SHV/cash (verified) and
   so dodged the falling-bonds trap. The PP regime risk (permanent bond sleeve in
   a rate-rise) does not materialize here because the safe sleeve is timed, not
   static bonds.

(c) Complementary or redundant? COMPLEMENTARY, approximately independent. Both
   (1.287) > selection-only (1.262) > buffer-only (1.202) > prod (1.166). Main
   effects nearly add: selection +0.097 plus buffer +0.038 = 0.135 vs joint +0.123
   (mild sub-additivity, ~-0.012, within noise). The buffer is slightly less
   additive on top of min-var (+0.026 vs +0.038 on prod) and selection slightly
   weaker with the buffer (+0.085 vs +0.097), but both remain positive -- not
   redundant.

(d) Frontier: see sweep table. vol/MaxDD/CAGR fall monotonically with b;
   Sharpe/Sortino creep up and flatten; Calmar/Martin peak at b=0.25.

## Verdict

- min-var SELECTION is the real, near-significant edge (p>0 ~0.96-0.97 on Sharpe
  AND Sortino) and improves BOTH return and risk-adjusted -- it earns its place.
- The permanent SAFE BUFFER does NOT clear the significance bar as independent
  risk-adjusted alpha (CI includes 0, p>0 ~0.86). It is a de-risking / vol-target
  dial: monotone Sharpe/Sortino nudge, big CAGR/vol/MaxDD reduction. The PP thesis
  is, at best, weakly supported -- favorable direction and genuinely regime-robust
  (incl 2022 via SHV timing), but not a statistically distinct alpha lever.
- The two are complementary and roughly additive, not redundant.

Recommended (selection, buffer) combo, honest about de-risking vs alpha:
- Maximize the edge that is statistically supported: adopt min-var selection
  (minvar_b0) -- highest CAGR (13.8%) with better Sharpe/Sortino/Calmar than prod
  and no permanent equity giveaway.
- If the mandate wants lower drawdown/vol: add a modest buffer b in [0.10, 0.25]
  on top of min-var (minvar_b25: Sharpe 1.287, Sortino 1.847, MaxDD -8.6%, vol
  8.4%, CAGR 11.0%). Calmar/Martin peak around b=0.25; do not push to b=0.40
  (Calmar regresses).
- Treat the buffer explicitly as a risk-target choice, not as alpha. b=0 if the
  objective is CAGR with the selection edge intact; b~0.25 if the objective is the
  best risk-adjusted/drawdown profile.

## Caveats / confidence

- Single in-sample fit; all bootstrap 95% CIs straddle 0 -- treat p>0 as strength,
  not proof. Selection p>0 ~0.96-0.97 is strong; buffer p>0 ~0.86 is suggestive only.
- Crisis windows are short; per-crisis Sharpe/Sortino are directional reads.
- Buffer composition is multiplicative with prod breadth scaling (stated above);
  a different composition (additive floor, or buffer only at full breadth) could
  shift magnitudes but not the qualitative selection >> buffer ordering.
- 2022 robustness hinges on the SHV-vs-IEF timing holding SHV; verified for this
  history, but it is a model-dependent guard, not a structural guarantee.

## Reproduce

```
cd /Users/rkautsar/personal/scripts/strategy_cpm
.venv/bin/python -m research.cpm_selection_vs_buffer
# -> research/cpm_selection_vs_buffer_findings.json
```
