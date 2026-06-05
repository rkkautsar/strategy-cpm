# CPM limit-breadth-to-3 vs current renormalize / drop-to-safe

Exploratory design comparison. CPM prod UNCHANGED. Research only, single in-sample,
point-estimates (no bootstrap). HIGH overfit caution. Sleeve-level focus.

- Script: `research/cpm_limit3_breadth_2026_06_02.py`
- Raw output: `research/cpm_limit3_breadth_2026_06_02_raw.txt`
- Run: `.venv/bin/python research/cpm_limit3_breadth_2026_06_02.py`
- Engine: mooex T+1 MOO, 10 bps/side. Clean 2008-05-30.., Ext 1999-03-10..2026-05-22.

## Question

Does limiting CPM breadth to 3 slots (denom 3, with/without min-var) remove the
`n_pos=3->4` exposure discontinuity while preserving performance, vs current
renormalize (A) and drop-to-safe (B)?

## The discontinuity

Current rule: `risky_fraction = min(n_pos,4)/4`, min-var 3-of-4 at `n_pos=4`.
- `n_pos=3` -> 3 names @ 25% = 75% risky.
- `n_pos=4` -> min-var picks 3 names, renormalized to 33.3% each = 100% risky.

Same ~3 names held, exposure jumps 75% -> 100%. The 4th positive signal flips the
book from 75% to fully invested WITHOUT adding a 4th name. That step is the cliff.

## Configs

| | pool | selection | denom | n_pos=4 |
|---|---|---|---|---|
| A current (gate) | top-4 | min-var 3-of-4 @ n=4 | 4 | 3 names @ 100% |
| B drop-to-safe | top-4 | min-var 3-of-4 @ n=4 | 4 | 3 names @ 75% + 25% safe |
| C limit3+min-var | top-4 | min-var 3-of-4 @ n=4 | 3 | 3 names @ 100% |
| D limit3 plain | top-3 | top-3 momentum (no min-var) | 3 | 3 names @ 100% |

Gate PASS: A replica matches prod weights exactly (max diff 0.00e+00); sleeve
Sharpe = 1.255673 (target 1.255673), MaxDD -13.03%, Calmar 1.008.

## (i) Risky-exposure by n_pos -- consistency / cliff check

```
n_pos      A current     B drop-safe    C/D limit3
1         25.0% / 1nm    25.0% / 1nm    33.3% / 1nm
2         50.0% / 2nm    50.0% / 2nm    66.7% / 2nm
3         75.0% / 3nm    75.0% / 3nm   100.0% / 3nm
4        100.0% / 3nm    75.0% / 3nm   100.0% / 3nm
```

CLIFF check `n_pos 3->4` (same ~3 names):
**A 75%->100% JUMP** | **B 75%->75% flat** | **C/D 100%->100% flat**.

Both B and C/D remove the `3->4` discontinuity, but in OPPOSITE directions:
- B removes it DOWNWARD: drops n_pos=4 to 75% (de-risk the dropped slot).
- C/D remove it UPWARD: raise n_pos=3 to 100% (denom 3 makes 3 names fully invested).

Critical structural fact: at `n_pos=4`, **A and C are IDENTICAL** (both min-var 3-of-4,
both 100%). C therefore differs from A ONLY at `n_pos in {1,2,3}`, where C runs hotter
(33/67/100 vs 25/50/75). C's true effect is purely the LOW-breadth aggression, not the
n_pos=4 behavior.

## (ii) n_pos distribution (selection-stage breadth)

```
clean: total=217 risk-on=160 defensive=57
  n_pos counts {1,2,3,4} = {1, 5, 11, 143}
  share of risk-on: n=1 0.6%, n=2 3.1%, n=3 6.9%, n=4 89.4%
ext:   total=327 risk-on=237 defensive=90
  n_pos counts {1,2,3,4} = {1, 8, 22, 206}
  share of risk-on: n=1 0.4%, n=2 3.4%, n=3 9.3%, n=4 86.9%
```

`n_pos=4` dominates (~89% of risk-on months). Low breadth (`n_pos<=2`) is only 3.8%.
The `n_pos=3` bucket (6.9% clean) is where C's biggest change lands (75%->100%).

## A/B/C/D sleeve metrics

SLEEVE (clean) -- mooex T+1, 10bps/side
```
config             Sharpe  exSharpe  Sortino  CVaR95_d  Calmar  Martin   MaxDD    CAGR     vol  turnover
A current(denom4)   1.256    1.126    1.516    -1.57%   1.008   4.257  -13.03%  13.13%  10.28%   0.590
B drop-to-safe      1.243    1.083    1.518    -1.26%   0.802   3.776  -13.03%  10.45%   8.30%   0.525
C limit3+minvar     1.208    1.083    1.442    -1.64%   0.776   3.551  -16.86%  13.08%  10.67%   0.586
D limit3 plain      0.870    0.759    1.032    -1.89%   0.602   2.105  -16.86%  10.15%  12.00%   0.614
```

SLEEVE (ext) -- mooex T+1, 10bps/side
```
config             Sharpe  exSharpe  Sortino  CVaR95_d  Calmar  Martin   MaxDD    CAGR     vol  turnover
A current(denom4)   1.255    1.026    1.550    -1.51%   0.971   4.117  -13.14%  12.76%   9.97%   0.567
B drop-to-safe      1.266    0.990    1.585    -1.21%   0.737   3.773  -14.11%  10.40%   8.07%   0.508
C limit3+minvar     1.216    0.994    1.487    -1.57%   0.722   3.541  -17.68%  12.76%  10.32%   0.562
D limit3 plain      0.992    0.792    1.201    -1.81%   0.683   2.646  -16.86%  11.51%  11.67%   0.554
```

## Verdicts

### (a) C (limit-3 + min-var) vs A (current): removes cliff but DEGRADES performance.
C strips the `3->4` jump but is worse on the headline:
- Sharpe -0.048 clean (1.208 vs 1.256), -0.039 ext.
- MaxDD +3.83pp WORSE clean (-16.86% vs -13.03%), +4.54pp ext.
- Calmar 0.776 vs 1.008, Martin 3.551 vs 4.257; CVaR95 worse.
Since A == C at n_pos=4 (89% of months), the entire deficit comes from C running
HOTTER at n_pos in {1,2,3}. Low breadth = fewer trending assets = riskier regime;
C leans IN (100% at n_pos=3) where A de-risks (75%). The drawdown gets deeper.
The cliff is NOT free to remove upward; at equal vol (10.67% vs 10.28%) C earns less.

### (b) C vs D: min-var clearly earns its keep at 3 slots.
C (1.208) >> D (0.870) clean; 1.216 vs 0.992 ext. Same breadth scaling, only
difference is min-var 3-of-4 vs top-3 momentum. Dropping min-var costs ~0.34 Sharpe
clean, raises vol (12.00% vs 10.67%) and worsens Sortino/Martin. Min-var variance
selection is doing heavy lifting -- it remains essential at 3 slots.

### (c) C vs B: B is the BETTER consistent rule.
B dominates C on both Sharpe and MaxDD, both windows:
- Sharpe: B 1.243/1.266 vs C 1.208/1.216.
- MaxDD: B -13.03%/-14.11% vs C -16.86%/-17.68% (B materially shallower).
- Sortino: B 1.518/1.585 vs C 1.442/1.487. CVaR95: B best of all four.
B removes the cliff while KEEPING the "more breadth needed for full risk" instinct
(caps n_pos>=3 at 75%). C removes the cliff by abandoning that instinct, buying tail
risk for a lower Sharpe. As a consistent design, B wins.

### (d) Net: best consistent design = B (drop-to-safe); honest tradeoff vs A.
- If the goal is a CONSISTENT rule with no `n_pos=3->4` cliff, **B (drop-to-safe)** is
  the pick: highest Sharpe among the consistent candidates, shallowest MaxDD, best
  CVaR95, and it preserves the breadth->risk monotonicity.
- C/D remove the cliff in the wrong direction (more aggression at low breadth) and
  pay for it with deeper drawdowns and lower Sharpe. C is mediocre; D is poor.
- HONEST CAVEAT: A (the cliff) is NOT dominated. A has the best clean Sharpe (1.256),
  best Calmar (1.008) and highest CAGR (13.13%). The cliff is a RETURN ENHANCER:
  going fully invested at n_pos=4 (89% of months) captures upside. Both consistent
  rules trade CAGR/Calmar for smoothness -- B gives up ~2.7pp CAGR (10.45% vs 13.13%)
  and ~0.21 Calmar. "Consistency" here is a real return sacrifice, not a free lunch.

## Bottom line

- Limit-3 (C) DOES remove the `3->4` discontinuity but does NOT preserve performance;
  it is more aggressive exactly when breadth is thin, deepening drawdowns (-16.86%) for
  a lower Sharpe (1.208). Not recommended.
- min-var still earns its keep at 3 slots (C 1.208 vs D 0.870).
- Among consistent rules, drop-to-safe (B) beats limit-3 (C) on Sharpe AND MaxDD; B is
  the better way to remove the cliff (downward de-risk, not upward over-risk).
- The current cliff (A) remains the highest-return/Calmar sleeve. Removing it is a
  deliberate return-for-consistency trade, best executed via B if pursued.

## Caveats / confidence

- Single in-sample backtest, point estimates, NO bootstrap/significance test. The
  ~0.04-0.05 Sharpe gaps and Calmar/MaxDD deltas are NOT significance-tested; treat as
  directional. MaxDD differences are single-path and fragile.
- HIGH overfit caution: this is a design comparison on one history; relative ordering
  (B>C, C>>D, A best Calmar) is more trustworthy than absolute numbers.
- Sleeve-only (blend skipped per scope: no candidate is clearly best enough to warrant
  blend-level evaluation; A is not dominated).
- CPM prod is unchanged. Confidence: MEDIUM on rankings, LOW on absolute magnitudes.
