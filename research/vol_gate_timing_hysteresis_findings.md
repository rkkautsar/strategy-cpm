# Vol-Gate Timing / Hysteresis Tuning -- 1970s + Modern

Analyst role; READ-ONLY re production. No production or memo files changed; no
commit. This is a test-only sensitivity study of the BULL-sleeve realized-vol
gate (`rv_60d < rv_252d`). Reuses existing 1970s harnesses
(`stagflation_1970s_bull_stack` / `trend_vol` / `tip_canary`) and the modern
anchor-gated engine (`exec_lag_moo_validation_2026_05_30`, mooex T+1, 10 bps/side).

Script: `research/vol_gate_timing_hysteresis.py` -> `*_findings.json`.

Anchor reproduced before reporting: modern 60d BULL clean Sharpe = **1.0813**,
60/40 CPM-BULL blend clean Sharpe = **1.2485** (exact). Abort-on-mismatch gate
passed.

---

## PART A -- 1970s BULL-stack full-period MaxDD diagnosis

Full BULL stack = canary (synthetic-TIP 13612U) AND trend (S&P 13612U) AND vol
(`rv_60d < rv_252d`); risk-on -> 100% S&P TR, else best-of {cash, IEF}. Eval
1968-01 .. 1985-12.

**Exact full-period MaxDD window:**

| metric | value |
|---|---|
| peak | **1981-04** |
| trough | **1982-01** |
| depth | **-12.40%** |
| recovered | 1982-09 |

This is the **1977-82 stagflation grind, NOT the 1973-74 crash.** Confirmation:

| window | BULL-stack MaxDD |
|---|---|
| 1973-74 crash | -6.85% |
| 1977-82 grind | -12.40% (= full-period MaxDD) |
| buy & hold (full) | -39.16% |

The gate **does** protect the 1973-74 crash (window DD only -6.85% vs buy & hold
-39.16%). The binding drawdown is the slow 1981-82 grind.

**Vol-gate state month-by-month through the MaxDD window (peak 1981-04 -> trough
1982-01):** 10 months; risk-on **7 of 10**; **2 vol flips**.

| applied month | rv_60 | rv_252 | ratio | vol_on | trend_on | risk_on | S&P ret |
|---|---|---|---|---|---|---|---|
| 1981-04 | 0.146 | 0.154 | 0.95 | ON | ON | risk-on | +1.30% |
| 1981-05 | 0.127 | 0.148 | 0.86 | ON | ON | risk-on | -1.61% |
| 1981-06 | 0.124 | 0.147 | 0.84 | ON | ON | risk-on | +0.86% |
| 1981-07 | 0.106 | 0.146 | 0.73 | ON | ON | risk-on | -2.01% |
| 1981-08 | 0.108 | 0.145 | 0.74 | ON | ON | risk-on | +0.81% |
| 1981-09 | 0.123 | 0.145 | 0.85 | ON | ON | risk-on | **-8.30%** |
| 1981-10 | 0.148 | 0.146 | 1.01 | OFF | OFF | defensive | +1.73% |
| 1981-11 | 0.164 | 0.146 | 1.12 | OFF | OFF | defensive | +3.05% |
| 1981-12 | 0.158 | 0.140 | 1.13 | OFF | OFF | defensive | +1.18% |
| 1982-01 | 0.130 | 0.135 | 0.96 | ON | ON | risk-on | **-4.80%** |

**Why the gate failed here.** Through the entire decline into the September-1981
plunge, realized vol was *low and falling* (rv_60 ratio 0.73-0.95, well below
rv_252). The market ground lower on calm tape, so the vol gate stayed risk-on
for all six months April-September 1981 and ate the -8.30% September drop. It only
flipped defensive in October 1981 -- after the damage -- when rv finally crossed
up, and by then it sat in cash through a +1.73/+3.05/+1.18% rebound (whipsaw),
then flipped *back* risk-on at the January-1982 trough just in time to absorb
another -4.80%.

This is the structural distinction:

- **Slow low-vol grind (1981-82):** decline arrives *without* a vol expansion;
  rv_60 never exceeds rv_252 until after the fact. The vol gate is the wrong tool
  -- it is blind to grinds. (The trend gate is the relevant defense and it also
  lagged, flipping only in October.)
- **Sharp vol-spike crash (1973-74):** decline arrives *with* a vol expansion;
  rv_60 crosses above rv_252 in time, so the gate de-risks and cuts the window DD
  to -6.85% vs -39.16% buy & hold. This is the gate's whole value.

---

## PART B -- slower / smoother / hysteresis variants

Variants (vol leg only; everything else held at production):

| name | spec |
|---|---|
| prod_60 | rv_60 < rv_252 (production) |
| sw_90 | rv_90 < rv_252 |
| sw_120 | rv_120 < rv_252 |
| hyst_sym2 | rv_60 < rv_252, require 2 consecutive months both directions |
| hyst_asym | rv_60 < rv_252, 1 month to-defensive (fast out), 2 months to-risk-on (slow in) |
| k_105 | rv_60 < 1.05 * rv_252 |
| k_110 | rv_60 < 1.10 * rv_252 |

### B.1 -- 1970s (full BULL stack)

| variant | full Sharpe | full MaxDD | 1973-74 DD | 1977-82 DD | 1977-82 ret | 1977-82 Sharpe | vol flips | whipsaw (77-82) |
|---|---|---|---|---|---|---|---|---|
| prod_60 | 0.361 | -12.40% | -6.85% | -12.40% | +69.98% | -0.083 | 41 | 29 |
| sw_90 | **0.437** | -10.36% | -6.85% | -10.36% | +77.34% | +0.011 | 32 | 31 |
| sw_120 | 0.332 | -9.67% | **-1.48%** | -9.67% | +55.73% | -0.293 | 26 | 34 |
| hyst_sym2 | 0.317 | -10.36% | -6.85% | -10.36% | +47.73% | -0.376 | 28 | 32 |
| hyst_asym | 0.309 | -10.36% | -6.85% | -10.36% | +52.56% | -0.335 | 31 | 33 |
| k_105 | 0.363 | -12.40% | -6.85% | -12.40% | +68.88% | -0.073 | 36 | 27 |
| k_110 | 0.426 | -12.40% | -6.85% | -12.40% | +73.77% | -0.014 | 38 | 24 |

1970s read:

- **1973-74 crash catch is preserved by every variant** (DD -6.85% throughout;
  sw_120 even tightens to -1.48%). Slowing the gate does not lose the crash in
  this era.
- The 1981-82 grind MaxDD shrinks a little under longer windows / hysteresis
  (-12.40% -> -9.67/-10.36%), but this is *not* the gate catching the grind --
  it is fewer/later flips reducing whipsaw cost, plus a slightly different path.
- On full-period Sharpe, **sw_90 (0.437) and k_110 (0.426)** look best; the
  **hysteresis variants are the worst** (0.309-0.317) because slow re-entry gives
  up too much of the +70% 1977-82 recovery.

### B.2 -- Modern (anchor-gated; clean 2008-05-30.., ext 1999-03-10..)

BULL sleeve:

| variant | clean Sharpe | clean Calmar | clean MaxDD | clean CAGR | ext Sharpe | ext MaxDD | turnover/yr | regime flips | fully-safe mo |
|---|---|---|---|---|---|---|---|---|---|
| prod_60 | **1.0813** | 0.857 | -13.35% | 11.44% | 0.9196 | -13.96% | 5.62 | 59 | 151 |
| sw_90 | 0.888 | 0.556 | -17.31% | 9.62% | 0.8235 | -17.31% | 5.62 | 55 | 162 |
| sw_120 | 1.0275 | 0.603 | -17.43% | 10.51% | 0.9982 | -17.43% | 5.17 | 49 | 164 |
| hyst_sym2 | 0.8865 | 0.559 | -17.31% | 9.68% | 0.8481 | -17.31% | 4.95 | 47 | 153 |
| hyst_asym | 0.9392 | 0.644 | -14.80% | 9.53% | 0.8562 | -14.80% | 5.39 | 52 | 172 |
| k_105 | 1.0780 | **0.882** | -13.35% | **11.77%** | **0.9325** | -13.35% | 5.32 | 57 | 141 |
| k_110 | 0.9508 | 0.625 | -17.31% | 10.81% | 0.8835 | -17.31% | 4.73 | 51 | 129 |

60/40 CPM-BULL blend:

| variant | clean Sharpe | clean Calmar | clean MaxDD | clean CAGR | ext Sharpe | ext MaxDD |
|---|---|---|---|---|---|---|
| prod_60 | **1.2485** | 1.193 | -10.68% | 12.74% | 1.2192 | -11.31% |
| sw_90 | 1.1700 | 1.124 | -10.68% | 12.01% | 1.1806 | -11.31% |
| sw_120 | 1.2330 | 1.113 | -11.12% | 12.37% | 1.2549 | -11.31% |
| hyst_sym2 | 1.1698 | 1.127 | -10.68% | 12.04% | 1.1909 | -12.66% |
| hyst_asym | 1.1940 | 1.120 | -10.68% | 11.97% | 1.2032 | -11.31% |
| k_105 | 1.2368 | 1.205 | -10.68% | 12.87% | 1.2129 | -11.31% |
| k_110 | 1.1862 | 1.124 | -11.12% | 12.49% | 1.1895 | -12.66% |

Crash behavior (BULL-sleeve drawdown in window / fully-safe months in window):

| variant | GFC 2008 | covid 2020 | bear 2022 |
|---|---|---|---|
| prod_60 | -12.09% (20 safe) | -13.35% (3 safe) | -0.30% (12 safe) |
| sw_90 | -12.09% | -13.35% | -0.30% |
| sw_120 | -12.09% | -4.68% | -9.73% |
| hyst_sym2 | -12.09% | -13.35% | -0.30% |
| hyst_asym | -12.09% | -13.35% | -0.30% |
| k_105 | -12.09% | -13.35% | -0.30% |
| k_110 | -12.09% | -13.35% | **-9.73%** |

Modern read:

- **Every slower/hysteresis variant degrades clean BULL Sharpe** (1.0813 -> 0.89
  to 1.03) **and worsens clean MaxDD from -13.35% to ~-17.3%.** The worse MaxDD is
  the **August-2011 US-debt-downgrade vol spike** (peak 2011-04 -> trough
  2011-08): the production 60d gate exits in time and cushions to -13.35%, while
  the 90d/120d/hysteresis gates lag the exit and eat the full -17.31%. This is the
  fast-crash catch that is the gate's entire value, lost by slowing it.
- The covid-2020 and 2022 catches are unchanged by mild slowing but **break under
  the loosest settings**: k_110 lets the 2022 decline ride to -9.73% (vs -0.30%),
  and sw_120 worsens 2022 to -9.73% (while accidentally improving covid). Looser
  threshold trades one crash for another.
- **k_105 is the only variant within noise of production**: BULL clean 1.0780 vs
  1.0813 (-0.003), blend 1.2368 vs 1.2485, identical crash DDs, marginally higher
  CAGR/Calmar. It is a near-no-op (a 5% threshold cushion barely changes flip
  timing) and does **not** reduce the modern drawdown.

---

## VERDICT

**No slower or hysteresis vol-gate setting delivers a robust win. Slowing the
gate sacrifices the fast crash catch that is its whole value.**

1. **The 1970s binding MaxDD (1981-82, -12.40%) is not a vol event.** It is a
   slow low-vol grind; the vol gate is structurally blind to it regardless of
   window (rv_60 never exceeds rv_252 until after the drop). Slowing the gate
   trims whipsaw and nudges that grind DD to ~-10%, but it does not *catch* the
   grind -- the trend gate is the relevant (and also-lagging) defense there.

2. **The 1970s and modern eras disagree on the "best" slow setting.** sw_90 and
   k_110 look attractive in the 1970s (higher full Sharpe, smaller grind DD, 73-74
   crash intact) but are clearly *worse* in modern data (lower Sharpe, -17.3%
   MaxDD, and k_110 loses the 2022 catch). Picking a slow window to fix the
   1970s grind is overfitting to one proxy episode.

3. **Modern: slowing the gate costs the 2011 (and risks the 2020/2022) crash
   catches** and lowers risk-adjusted return across the board. The only neutral
   tweak (k_105) is a near-no-op that does not reduce drawdown.

4. **Keep production `rv_60d < rv_252d`.** The grind MaxDD is a known structural
   gap of any vol crossover; the right lever for grinds is the trend leg / sleeve
   diversification (the 60/40 blend already cuts clean MaxDD to -10.68%), not a
   slower vol gate.

### Within-noise flag

All modern BULL Sharpe differences sit inside the memo's bootstrap Sharpe 95% CI
(~[0.635, 1.553]); even the largest gap (prod 1.0813 vs hyst_sym2 0.8865) is well
under one sigma. k_105 vs prod (0.003 Sharpe, identical DDs) is indistinguishable
from noise. Treat the modern degradations from slow windows/hysteresis as a
consistent *directional* signal (they all point the same way and break a
specific, datable crash catch), not as individually significant point estimates.
The 1970s numbers are proxy-based (synthetic TIP, monthly-average S&P trend price
vs daily-close vol series, duration-only bond TR) and should be read as
directional, not precise.

## Caveats

- 1970s: synthetic TIP canary is effectively always-on this era; TREND uses
  Shiller monthly-average S&P price while VOL uses Yahoo ^GSPC daily close
  (documented series mismatch); IEF analog is a 5y CMT duration TR (convexity
  omitted); warmup months default each gate to risk-on (no lookahead).
- Modern: mooex T+1 MOO exact, 10 bps/side, real yfinance auto_adjust OHLC from
  `/tmp/cpm_open_cache`; hysteresis applied on month-end raw rv signals with
  state depending only on past months (no lookahead).
