# NDX top-5 SLOT vol-target: FIXED absolute target vs ADAPTIVE (RV252) target

Analyst role. Read-only re production (ndx_sleeve_live.py / prod / voltarget /
breadth-prod / memo NOT edited). Research artifacts only; no commit.

Harness: `research/cpm_ndx_voltarget_spec_harness.py`
Runner:  `research/cpm_ndx_voltarget_spec_run.py`
Output:  `research/cpm_ndx_voltarget_spec_findings.json`
Run:     `.venv/bin/python -m research.cpm_ndx_voltarget_spec_run`

## Question

On the CHOSEN NDX de-risk mechanism (TOP-5, discrete drop-lowest-momentum
slot-replacement: `scale=min(1,target/RV_short)`, `n=round(scale*5)`, drop the
`5-n` lowest-momentum names to safe, kept names 1/5 each), WHAT VOL TARGET should
drive the scale signal:

- FIXED: target = a-priori absolute level (incumbent 0.30, 60d short window).
- ADAPTIVE: target = trailing RV252 of the (current top-5) sleeve basket; scale
  `= min(1, RV252/RV_short)`. This is the GRADED CONTINUOUS GENERALIZATION of the
  prod binary gate (prod gate = SPY RV20<RV252; ADAPT(w20) grades the same
  RV20<RV252 comparison at the basket level into a dial).

Decision = fixed-vs-adaptive, weighing Sharpe/DD against parsimony / robustness /
coherence-with-prod.

## Method

- Engine identical across all configs: monkeypatch
  `ndx_sleeve_live.compute_ndx_weights`, call the UNMODIFIED
  `ndx_sleeve_live.run_ndx_backtest` (gate TIP + SPY-trend + SPY RV20<RV252, safe
  rotation SHV/IEF, T+1 MOO, 10bps/side, delisting haircut, PIT membership). Only
  the TARGET feeding the scale signal changes. All signals lagged through
  `sig_d` -> no look-ahead.
- All de-risk configs share the IDENTICAL TOP-5 SLOT discrete drop-lowest-momentum
  mechanism; only the target spec differs. NONE = prod top-5 EW (anchor).
- Windows: clean = 2008-05-30..2026-05-22; ext = 1999-03-10..2026-05-22.
- Bootstrap: paired block, B=2000, block=21, seed=42
  (`cpm_bootstrap_multimetric`). Walk-forward = 3 equal segments.
- FIXED levels {0.20,0.25,0.30,0.35,0.40} and windows are A-PRIORI (sensitivity,
  not optimization).
- Caveat: cached NDX price dataset; absolute levels may drift slightly from a prod
  refresh. Contrasts are apples-to-apples via the identical engine. NONE
  reproduces the prod top-5 EW anchor (clean Sharpe 1.281, MaxDD -31.4%, CAGR
  31.4%).

## Headline table (clean 2008+)

| config        | Sharpe | Sortino | CVaR  | MaxDD  | CAGR  | vol   | turnover/yr | slot-events/yr | meanExp | hi-vol Exp | lo-vol Exp |
|---------------|--------|---------|-------|--------|-------|-------|-------------|----------------|---------|------------|------------|
| NONE (prod)   | 1.281  | 1.962   | 8.40  | -0.314 | 0.314 | 0.236 | 5.16        | 0.00           | 1.000   | n/a        | n/a        |
| FIXED t0.20   | 1.288  | 1.996   | 8.72  | -0.203 | 0.225 | 0.169 | 4.81        | 2.72           | 0.719   | 0.470      | 0.847      |
| FIXED t0.25   | 1.311  | 2.019   | 8.78  | -0.224 | 0.256 | 0.188 | 4.98        | 1.77           | 0.839   | 0.589      | 0.967      |
| FIXED t0.30   | 1.262  | 1.922   | 8.30  | -0.278 | 0.264 | 0.202 | 5.11        | 1.65           | 0.901   | 0.708      | 1.000      |
| FIXED t0.35   | 1.282  | 1.957   | 8.41  | -0.296 | 0.283 | 0.212 | 5.10        | 0.83           | 0.934   | 0.805      | 1.000      |
| FIXED t0.40   | 1.248  | 1.895   | 8.14  | -0.296 | 0.287 | 0.223 | 5.16        | 0.71           | 0.963   | 0.892      | 1.000      |
| ADAPT w20     | 1.318  | 2.035   | 8.74  | -0.314 | 0.315 | 0.228 | 5.22        | 1.42           | 0.965   | 0.924      | 0.986      |
| ADAPT w60     | 1.302  | 1.998   | 8.59  | -0.314 | 0.308 | 0.226 | 5.10        | 1.12           | 0.965   | 0.919      | 0.989      |
| BINARY w20    | 1.370  | 2.151   | 9.12  | -0.355 | 0.288 | 0.199 | 5.66        | 1.77           | 0.798   | 0.595      | 0.903      |

"hi-vol Exp" / "lo-vol Exp" = mean equity exposure in the top vs bottom tercile of
absolute basket realized vol (`RV_short`) across clean ON-months.

## 2021 unwind (the key NON-gated episode) and crises

2021 unwind = 2021-02-12..2021-05-13 (a SLOW de-rate, not a sharp spike), ext:

| config       | 2021-unwind MaxDD | 2021 cum | COVID DD | dotcom | GFC    | 2022   | 2025   |
|--------------|-------------------|----------|----------|--------|--------|--------|--------|
| NONE (prod)  | -0.314            | -0.282   | -0.047   | -0.121 | -0.091 | -0.003 | -0.048 |
| FIXED t0.20  | -0.148            | -0.130   | -0.047   | -0.121 | -0.105 | -0.003 | -0.034 |
| FIXED t0.25  | -0.196            | -0.173   | -0.047   | -0.121 | -0.105 | -0.003 | -0.044 |
| FIXED t0.30  | -0.224            | -0.186   | -0.047   | -0.121 | -0.105 | -0.003 | -0.044 |
| FIXED t0.35  | -0.261            | -0.211   | -0.047   | -0.121 | -0.095 | -0.003 | -0.044 |
| FIXED t0.40  | -0.293            | -0.260   | -0.047   | -0.121 | -0.095 | -0.003 | -0.037 |
| ADAPT w20    | -0.314            | -0.283   | -0.047   | -0.121 | -0.091 | -0.003 | -0.048 |
| ADAPT w60    | -0.314            | -0.273   | -0.047   | -0.121 | -0.091 | -0.003 | -0.043 |
| BINARY w20   | -0.355            | -0.342   | -0.047   | -0.121 | -0.091 | -0.003 | -0.048 |

Decisive result: in the 2021 unwind, FIXED floors the drawdown monotonically with
the absolute level (t0.20 -15%, t0.25 -20%, t0.30 -22%, t0.40 -29%), whereas
ADAPTIVE provides ZERO protection (-31.4%, identical to no-de-risk) and BINARY is
WORSE than no-de-risk (-35.5%, whipsaw mistiming). Crisis windows are flat because
the prod gate already covers V-shaped crises; 2021 is the one episode the gate
does not catch, and it is exactly where the target-spec choice matters.

### Why ADAPTIVE fails 2021 (monthly exposure through the grind)

| month     | FIXED t0.30 exp | ADAPT w20 exp | FIX RV60 | AD RV20 | AD RV252 |
|-----------|-----------------|---------------|----------|---------|----------|
| 2021-01   | 0.600           | 1.000         | 0.468    | 0.332   | 0.479    |
| 2021-02   | 0.800           | 1.000         | 0.404    | 0.394   | 0.420    |
| 2021-03   | 0.600           | 0.800         | 0.438    | 0.568   | 0.409    |
| 2021-04   | 0.600           | 1.000         | 0.436    | 0.281   | 0.384    |
| 2021-05   | 0.800           | 1.000         | 0.406    | 0.399   | 0.373    |

Absolute basket vol was elevated (~40-47%) the whole unwind, so FIXED (absolute
cap at 0.30) held 0.6-0.8 exposure and cushioned the loss. ADAPTIVE compares
RV20 to RV252, and because the WHOLE sleeve had drifted into a permanently higher-
vol regime, RV20 ~ RV252 -> scale ~ 1 -> full exposure -> no protection. This is
the textbook regime-risk failure of relative (regime-normalized) vol targeting.

## Bootstrap (clean, B=2000, mean dMetric, p>0; dMaxDD CI is soft -- context only)

- ADAPT w20 vs FIXED t0.30: dSharpe +0.054 (p=0.80), dSortino +0.111 (p=0.83),
  dCVaR +0.43 (p=0.80), dMaxDD -0.028 (p=0.22). -> Sharpe edge is a WASH (not
  significant), and the MaxDD point estimate favors FIXED (ADAPT -27.8 vs... note
  ADAPT full-sample MaxDD -31.4 vs FIXED -27.8; dMaxDD<0 = ADAPT worse DD).
- ADAPT w60 vs FIXED t0.30: same pattern, all insignificant; ADAPT worse DD.
- ADAPT w20 vs NONE: dSharpe +0.037 (p=0.961), dSortino +0.074 (p=0.975),
  dCVaR +0.336 (p=0.978), dMaxDD +0.011 (p=0.75). -> ADAPT SIGNIFICANTLY lifts
  risk-adjusted return vs prod-no-de-risk, but provides NO DD improvement.
- FIXED t0.30 vs NONE: dSharpe -0.017 (p=0.41, no Sharpe edge), dMaxDD +0.039
  (p=0.91, near-significant DD improvement). -> FIXED trades a hair of Sharpe for
  real, near-significant DD control.
- ADAPT w20 vs ADAPT w60: tiny, insignificant (w20 marginally higher Sharpe, no
  turnover penalty: 5.22 vs 5.10/yr, slot-events 1.42 vs 1.12). Short window is a
  wash; 20d does NOT whipsaw more.
- ADAPT w20 vs BINARY w20: binary has higher point Sharpe (1.370) but soft CIs,
  worse full-sample MaxDD (-35.5 vs -31.4) and worse 2021 (-35.5 vs -31.4).

## Coherence: ADAPT(w20) == graded prod gate (CONFIRMED)

Over 109 clean ON-months: the basket binary RV20<RV252 comparison would de-risk
in 20.18% of months; ADAPT(w20) graded de-risk fires in exactly 20.18% of months;
agreement = 100% (`agree_frac=1.0`). ADAPT(w20) de-risks precisely when basket
RV20 >= RV252, i.e. the same comparison the prod gate uses. ADAPT(w20) IS the
graded continuous form of the binary gate -- maximally coherent with prod.

Does grading the gate beat the binary gate? On DD and 2021, YES (graded -31.4 vs
binary -35.5; graded is smooth, binary whipsaws full-on/full-off and mistimes).
On raw Sharpe the binary point estimate is higher but with soft CIs and worse
tails. Grading removes the binary's whipsaw cost.

## Walk-forward (3 seg; Sharpe / MaxDD)

| config       | seg1 (08-14) | seg2 (14-20) | seg3 (20-26) |
|--------------|--------------|--------------|--------------|
| NONE         | 1.18/-0.17   | 1.25/-0.17   | 1.47/-0.31   |
| FIXED t0.20  | 1.16/-0.15   | 1.25/-0.16   | 1.44/-0.20   |
| FIXED t0.25  | 1.20/-0.17   | 1.27/-0.17   | 1.46/-0.22   |
| FIXED t0.30  | 1.18/-0.17   | 1.27/-0.17   | 1.37/-0.28   |
| FIXED t0.35  | 1.18/-0.17   | 1.25/-0.17   | 1.44/-0.30   |
| FIXED t0.40  | 1.17/-0.17   | 1.25/-0.17   | 1.38/-0.30   |
| ADAPT w20    | 1.17/-0.17   | 1.25/-0.15   | 1.55/-0.31   |
| ADAPT w60    | 1.18/-0.17   | 1.23/-0.17   | 1.52/-0.31   |
| BINARY w20   | 1.29/-0.15   | 1.20/-0.12   | 1.60/-0.35   |

FIXED-level Sharpe ranking by segment (best->worst):
- seg1: t25 > t35 ~ t30 > t40 > t20
- seg2: t30 ~ t25 > t40 ~ t35 ~ t20
- seg3: t25 > t20 ~ t35 > t40 > t30

The Sharpe-OPTIMAL fixed level is NOT robust: the ranking shuffles, the spread is
tiny (~0.10 within a segment), and t0.30 is actually WORST in seg3. So picking
t0.30 by Sharpe would be overfitting noise. BUT the DD response is monotone and
stable across ALL segments: lower target = lower DD, every segment (e.g. seg3 DD
t0.20 -0.20, t0.25 -0.22, t0.30 -0.28, t0.40 -0.30). The absolute cap's DD control
is robust OOS; the Sharpe-optimal level is not. ADAPTIVE is OOS-Sharpe-stable
(and best in seg3, 1.55) but its seg3 MaxDD is -0.31 = NO DD control OOS (the
segment that contains 2021/2022).

## Answers

(a) ADAPTIVE vs FIXED-0.30 -- materially different or a wash? On SHARPE/Sortino/
CVaR it is a statistical WASH (ADAPT +0.05 Sharpe, p=0.80). On the thing the
mechanism was CHOSEN for -- DD control -- they are NOT a wash: FIXED cuts MaxDD to
-27.8% and floors 2021 to -22%, ADAPTIVE leaves MaxDD at -31.4% and 2021 at -31.4%
(no protection). Turnover/events are near-identical. The difference is entirely in
DD, and it favors FIXED.

(b) Parsimony/overfit -- is FIXED sensitive to the level? The Sharpe-optimal level
IS noisy (ranking flips across segments; t0.30 worst in seg3), so do NOT defend
t0.30 as a Sharpe optimum. However, the DD response is MONOTONE and STABLE in the
level across every segment -- the level is a risk-appetite dial, not a fitted
constant. ADAPTIVE is more walk-forward-stable on Sharpe (its pitch holds) but
that stability buys no DD control. So: FIXED is "param-sensitive" only on the
metric where the level does not matter (Sharpe); on the metric that matters (DD)
it is robust and monotone.

(c) Regime risk -- CONFIRMED and decisive. ADAPTIVE's relative normalization
leaves it ~fully invested in a high-ABSOLUTE-vol regime when RV20~RV252 (hi-vol
exposure 0.92 vs FIXED-t0.30 0.71). The 2021 slow de-rate is exactly such a
regime: absolute vol ~40-47% but RV20~RV252 -> ADAPT never de-risks -> -31.4% DD.
FIXED de-risks on absolute vol -> -22%. This is where the choice is decided.

(d) Short window for adaptive -- 20d vs 60d is a WASH (dSharpe +0.015, p=0.77;
near-identical turnover and slot-events; 20d does not whipsaw more). Neither
catches 2021 because BOTH normalize by RV252; the failure is the relative target,
not the window length. 20d is marginally better and is the gate-consistent choice.

(e) Coherence -- CONFIRMED: ADAPT(w20) fires in exactly the same 20.2% of months
as the basket RV20<RV252 binary comparison (agree=100%); it is the graded form of
the prod gate. Grading beats the binary gate on DD/2021 and removes whipsaw, but
since the gate already owns DD for V-crises and ADAPT only de-risks 20% of months
by small amounts, the graded gate adds little DD value over the binary it
generalizes.

(f) RECOMMENDATION -- use FIXED (absolute target), NOT adaptive, for the top-5
discrete vol-target, because the mechanism's PURPOSE is drawdown control of the
non-gated 2021-type slow de-rate, and only the absolute cap delivers it. ADAPTIVE
is elegant, parsimonious, and coherent with prod, and it DOES significantly lift
Sharpe vs no-de-risk -- but it is a risk-adjusted-return tilt, NOT a DD tool, and
must not be sold as one. For the FIXED level: the incumbent 0.30 is defensible but
mid-pack; the data favor a slightly TIGHTER cap (0.25): equal-or-better Sharpe
(1.311 vs 1.262), top OOS Sharpe rank, materially better MaxDD (-22.4 vs -27.8)
and 2021 (-20 vs -22), for ~1pp CAGR give-up (25.6 vs 26.4). Choose the level as a
risk-appetite dial on the stable monotone DD/CAGR frontier, a-priori, not by
Sharpe. If parsimony/coherence is valued AND DD is delegated entirely to the gate,
ADAPT(w20) is the coherent graded-gate add-on -- but it does not replace FIXED for
DD.

## Confidence and caveats

- High confidence on the qualitative verdict (FIXED for DD, ADAPT is Sharpe-tilt-
  not-DD-tool): the 2021 mechanism is structural (relative vol cannot see an
  absolute regime shift), confirmed by exposure traces and monotone DD response.
- Moderate confidence on the exact FIXED level: Sharpe differences across levels
  are within bootstrap noise and the ranking is unstable; the DD/CAGR frontier is
  the stable, decision-relevant axis. t0.25 vs t0.30 is a risk-appetite call.
- Bootstrap dMaxDD CIs are soft (path-dependent); MaxDD claims rest on full-sample
  point estimates + per-episode windows, which agree.
- Single cached in-sample dataset; PIT/delisting integrity preserved by the
  unmodified engine. FIXED levels/windows a-priori (sensitivity, not tuned).

Next handoff: oracle, if a prod target-spec/level change is to be adjudicated
(decision = fixed vs adaptive + level), or fixer if a config change is approved.
