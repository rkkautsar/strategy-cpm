# CPM Regime-Conditional Forward-Sharpe Scenario Decomposition

Role: analyst (read-only research; no production/memo edits; no commit).
Script: `research/cpm_regime_scenarios.py`
JSON:   `research/cpm_regime_scenarios_findings.json`
Reuses the production engine (`cpm_robust_param_sweep.run_series`, K=4 / faber_voladj /
504 / inverse-vol) and the benchmark harness (`cpm_benchmarks_proper`).
Anchor gate: reproduced clean Sharpe **1.1910** (exact match to headline).

Convention: mooex (T+1 MOO exact, 10 bps/side, monthly signal). Clean window
2008-05-30..2026-05-22 (18y); ext 1999-03-10..2026-05-22 (more regime coverage).

## Purpose

Decompose the ~0.72 forward-Sharpe central estimate (from
`cpm_deflated_sharpe_findings.md`) across market regimes, so a reader can stress it
against their own regime priors. This is a SCENARIO DECOMPOSITION, not a prediction.

## 1. Regime classifier

Computed per calendar month, decided at the PRIOR month-end (no lookahead):

- Equity trend sign: SPY trailing 12m total return (>0 uptrend, <=0 downtrend).
- Realized-vol tercile: SPY trailing 63-trading-day annualized realized vol, terciled
  across the eval sample (clean terciles: q33=0.118, q67=0.163 annualized).

Buckets:

- (A) trending / low-vol: uptrend AND vol NOT in the top tercile.
- (B) mean-reverting / high-vol (choppy/crisis): downtrend OR vol in the top tercile.
- (C) stagflation / inflation-rotation: the modern sample has NO clean stagflation
  regime (post-1999 the US never ran a sustained 1970s-style equity-AND-bond bear with
  double-digit CPI). We therefore (i) flag the closest modern analog -- the 2021-04 to
  2022-12 inflation/Fed-hiking rotation -- as a sub-window, and (ii) import the 1970s
  cross-asset evidence (`research/stagflation_1970s_cpm_crossasset_findings.md`) as the
  qualitative bucket-C data point.

## 2. Regime-conditional performance (annualized excess Sharpe, monthly frame)

CLEAN 18y (2008-05-30..2026-05-22), N=216 months:

| Regime | n months | frac | CPM Sharpe | SPY Sharpe | 60/40 Sharpe |
|---|---|---|---|---|---|
| A trending / low-vol | 141 | 0.65 | 1.41 | 0.81 | 0.94 |
| B mean-rev / high-vol | 75 | 0.35 | 0.96 | 0.62 | 0.68 |

EXT 27y (1999-03..2026-05), N=326 months (adds dot-com bust + GFC ramp):

| Regime | n months | frac | CPM Sharpe | SPY Sharpe | 60/40 Sharpe |
|---|---|---|---|---|---|
| A trending / low-vol | 208 | 0.64 | 1.24 | 0.65 | 0.78 |
| B mean-rev / high-vol | 118 | 0.36 | 1.01 | 0.29 | 0.36 |

Key reads:

- CPM beats both benchmarks in BOTH regimes, in BOTH samples. The edge is LARGEST in
  the choppy/high-vol bucket on the ext sample (CPM 1.01 vs SPY 0.29, 60/40 0.36) --
  consistent with CPM being a drawdown-control vehicle.
- The 2017-26 subperiod (CPM Sharpe 1.40, the disclosed "trending tailwind" window) is
  almost entirely the A bucket. The headline 1.19 clean is a ~65/35 A/B blend.
- Pooled full-sample Sharpe (1.19) is BELOW the frequency-weighted regime Sharpes
  (0.65*1.41 + 0.35*0.96 = 1.25) because regime switching itself adds variance to the
  pooled denominator. This matters for reconciliation in Section 4.

Modern inflation-rotation analog (bucket-C proxy), 2021-04..2022-12, 21 months:

| Strategy | Sharpe |
|---|---|
| CPM | 1.21 |
| SPY (buy-hold) | 0.04 |
| 60/40 | -0.19 |

This is the single best modern data point for bucket C: during the only sustained
inflation/hiking rotation in the modern sample, CPM returned a 1.21 Sharpe while a
60/40 was NEGATIVE. It echoes the 1970s cross-asset result -- CPM rotates into the
inflation winners -- but is a small (21m) sample.

1970s imported (bucket C qualitative), 4-asset cross-asset CPM proxy, 1969-1985:
de-artifacted realistic read CAGR ~19-25%, MaxDD ~-9 to -13%, Sharpe **~0.8-1.0**;
CPM rotated ~90% into gold+commodities, profited through 1973-74 (+59 to +184%) and
1977-82 while buy-hold equity lost -38.6% (real ~-50%) and 60/40 -24%. Caveat: proxy
commodity series, no costs, reduced universe (see source file).

## 3. Forward scenario table (compact 3-row)

Forward scenario per regime = regime-conditional in-sample Sharpe, haircut for the
disclosed forward factors (selection de-peak, execution realism) plus a regime
non-stationarity / OOS-decay factor. Construction (multiplicative on annualized SR):
post-execution ideal level 0.83 (= 1.19 x 0.82 de-peak x 0.85 exec) scaled by the
regime ratio vs clean-full, times 0.88 OOS-decay. Bucket C uses the 1970s 0.8-1.0
midpoint with a combined de-peak/exec haircut.

| Regime | Historical CPM Sharpe | Forward scenario | Note |
|---|---|---|---|
| A trending / low-vol | 1.41 (clean) | **0.86** | Best case; 2017-26 (1.40/1.38) is mostly this bucket. Upside if trend/low-vol persists. |
| B mean-rev / high-vol (choppy/crisis) | 0.96 (clean) | **0.59** | Tail-control helps drawdowns, but raw Sharpe compresses; whipsaw + execution slippage bite hardest here. |
| C stagflation / inflation-rotation | 0.8-1.0 (1970s proxy); 1.21 (2021-22, n=21) | **0.77** | Structurally favorable IF inflation assets (GLD/DBC) stay in the live universe; no clean modern sample, costs/breadth uncertain. |

## 4. Verdict

- Regime that favors CPM MOST: **A trending / low-vol** on raw Sharpe (forward ~0.86),
  but the RELATIVE edge over benchmarks is actually LARGEST in **B choppy/high-vol** and
  in **C inflation-rotation** (where 60/40 goes negative). CPM's structural value is
  cross-asset rotation + tail control, which pays off most when the 60/40 fails.
- Regime that favors CPM LEAST (lowest absolute forward Sharpe): **B mean-reverting /
  high-vol**, forward ~0.59 -- raw Sharpe compresses under whipsaw even though drawdowns
  stay shallow.
- How ~0.72 decomposes: the three forward scenarios BRACKET the 0.72 central. B (0.59)
  is the downside, A (0.86) the upside, C (0.77) the inflation case. The historical
  regime mix (65% A / 35% B) would imply ~0.77 forward; the 0.72 central is more
  conservative, effectively pricing in either a heavier choppy-regime weighting or harder
  OOS regime decay than history delivered. A reader who believes the next decade looks
  like 2017-26 (trending) should lean toward 0.85; one who expects a choppy/crisis-heavy
  decade should lean toward 0.60.

Explicitly: this is a scenario decomposition conditioned on regime priors, NOT a
forward prediction. The point estimates are reasoned syntheses, unvalidatable until OOS
data accrues.

## 5. Caveats / confidence

- Small per-regime samples: B clean = 75 months, the 2021-22 analog = 21 months, the
  1970s bucket is a 4-asset proxy with no costs. Treat per-regime Sharpes as indicative.
- Classifier is one reasonable choice (SPY 12m trend + 63d vol tercile). Alternative
  classifiers (VIX level, drawdown state) would reshuffle a minority of months but the
  A>>benchmark / B-edge-largest ordering is stable across the clean and ext samples.
- No clean modern stagflation regime exists; bucket C leans on the 1970s reconstruction
  (proxy commodities, gold investability pre-1975, reduced universe) plus the 21-month
  2021-22 analog. The structural claim (rotate into inflation winners) is robust; the
  exact forward Sharpe is the softest cell.
- The forward haircuts (de-peak, execution, OOS-decay) are applied as independent
  multiplicative factors; if execution slippage correlates with regime stress, the B
  downside can fall below 0.59.
- Sharpes are annualized from monthly excess (over SHV cash) returns; the daily-frame
  anchor is 1.1910 (reproduced). Monthly-frame full-sample Sharpe differs slightly from
  the daily anchor by construction.

Confidence: medium-high on the regime ORDERING and the relative-edge story (stable
across clean/ext and corroborated by the 2021-22 analog + 1970s evidence); medium on
the exact forward point estimates (small samples, regime factor is the softest input).
