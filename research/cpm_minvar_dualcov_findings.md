# CPM min-var dual-window covariance (reviewer rec #2) -- findings

Analyst, 2026-06-02. Exploratory. CPM prod UNCHANGED. No commit; research only.

## Question / hypothesis

Reviewer recommendation #2: blend a faster 60d covariance into CPM's min-var
3-of-4 subset selector (current uses 252d = `CORR_LOOKBACK_DAYS`). Hypothesis:
the faster covariance helps the selector eject assets undergoing sudden
correlation spikes during regime shifts (e.g. 2022), improving drawdown there.

A-priori expectation (stated before running): WITHIN-NOISE. Min-var is already a
within-noise contributor in CPM (significant only at the (U1,R1) corner) and
operates over only 4 candidates -> C(4,3)=4 triplets, a coarse decision surface;
a prior vol-window test found 60d noisier.

## Method

- Script: `research/cpm_minvar_dualcov_2026_06_02.py` (+ `.json`).
- Mechanism reused byte-identical from `research/cpm_mech_2swap_univ_2026_06_02.cpm_mech_wf`
  (CPM R1 M1: vol-adj Faber ranker + min-var 3-of-4 at n_pos=4, TIP-only canary,
  top-4, EW, breadth-scaled partial-safe, best-of {SHV,IEF} safe). ONLY the
  covariance estimate fed to the min-var triplet choice changes.
- Engine: `exec_lag_moo_validation_2026_05_30._segment_returns_conv`, mooex T+1
  MOO exact, 10 bps/side, both-252 baseline guard. CLEAN 2008-05-30..2026-05-22,
  EXT 1999-03-10..2026-05-22.
- Configs: (1) CURRENT 252d; (2) BLEND-ALWAYS 0.5*Cov252 + 0.5*Cov60 every month;
  (3) STRESS-COND 0.5/0.5 blend iff stress high else 252d (reviewer's exact
  proposal); (4) FAST 60d-only (bracket).
- Stress definition (exact): SPY trailing 20d realized vol (annualized) above its
  trailing 756d (~3y) 80th percentile, PIT (expanding min_periods=60). A-priori
  60d/80th-pct, no tuning. Stress fires 19.3% of CLEAN days (872 days).
- Point-estimates only (bootstrap skipped per scope).

## Gate

CURRENT 252d reproduces full CPM-8: **1.25567327** vs target 1.255673
(|d|<5e-4). PASS.

## Metrics table (CLEAN, vs CURRENT)

| Config | Sharpe | Calmar | Martin | MaxDD | CAGR | Vol | Turnover | dSharpe |
|---|---|---|---|---|---|---|---|---|
| CURRENT 252d        | 1.2557 | 1.0076 | 4.257 | -13.03% | 13.13% | 10.28% | 7.08 | -- |
| BLEND-always 50/50  | 1.2249 | 0.9798 | 3.573 | -13.03% | -- | -- | 7.16 | -0.0308 |
| STRESS-cond blend   | 1.2557 | 1.0076 | 4.257 | -13.03% | 13.13% | 10.28% | 7.08 | 0.0000 |
| FAST 60d-only       | 1.1479 | 0.9167 | 3.356 | -13.03% | -- | -- | 7.68 | -0.1078 |

EXT dSharpe vs current: BLEND +0.0137, STRESS 0.0000, 60d -0.0595.
MaxDD identical (-13.03% CLEAN) across all configs -- the cov change never moved
the worst drawdown.

## Selection divergence (only meaningful at n_pos==4; 143 of 217 CLEAN rebals)

| Config | diverged | % of n_pos4 | stress rebals | diverged within stress |
|---|---|---|---|---|
| BLEND-always | 16 | 11.2% | 14 | **0** |
| STRESS-cond  | **0** | **0.0%** | 14 | **0** |
| FAST 60d     | 42 | 29.4% | 14 | **0** |

## Per-crisis (Sharpe / MaxDD / total return)

| Crisis | CURRENT | BLEND-always | STRESS-cond | 60d |
|---|---|---|---|---|
| COVID 2020 | 0.18 / -10.20% / +0.32% | identical | identical | identical |
| BEAR 2022  | 0.10 / -5.17% / +0.39% | **-0.65 / -11.73% / -5.04%** | identical | -0.65 / -11.73% / -5.04% |
| GFC 2008-09| 0.88 / -6.53% / +6.22% | identical | identical | identical |

COVID and GFC: zero min-var divergence -> faster cov changed nothing in either.

## Answers

(a) Material change? No. STRESS-conditional = exact no-op (all deltas 0.0).
BLEND-always is worse (Sharpe -0.031, Calmar -0.028, Martin -0.68; EXT +0.014,
within-noise/mixed). 60d-only clearly worse (Sharpe -0.108). MaxDD unchanged
everywhere.

(b) Does it change selections, and help 2022/COVID? The stress-conditional
proposal NEVER changes a selection: the 14 stress-flagged n_pos4 rebals produced
ZERO divergence -- precisely when the thesis says the faster cov should act, it
does not. BLEND/60d DO diverge (11-29%) but ALL divergences land in CALM months
(stress=False), none in stress. The thesis is falsified on its own terms.
Worse, the faster cov HURT 2022: the 2021-12-31 rebal (governing Jan-2022
holdings) flipped the min-var triplet from [DBC,SPHQ,VNQ] to [QQQ,SPHQ,VNQ] --
ejecting DBC (commodities, the 2022 winner) for QQQ (the 2022 loser). That single
swap drove BEAR_2022 from Sharpe 0.10 / -5.17% DD to -0.65 / -11.73% DD. COVID
and GFC saw no divergence at all.

(c) Verdict: **REJECT / within-noise-to-worse.** Do not adopt. Stress-conditional
is a literal no-op; blend/60d hurt headline metrics and specifically worsen 2022
(the exact regime the thesis targeted) by ejecting the protective asset. The
faster covariance reacts to short-window noise in calm months, not to the
correlation spikes during shifts. Matches the a-priori within-noise expectation
and the prior "60d noisier" vol-window result.

## Caveats / confidence

- Single in-sample window; point-estimates only (bootstrap skipped per scope).
- Adds a stress-threshold + window DoF; held a-priori (60d / 80th-pct / 20d-rv /
  756d-pctl), no tuning -- but the no-op/worse result means tuning could only be
  curve-fitting.
- PIT / cached-data; SPY used as the cross-asset stress proxy.
- Confidence: HIGH that this is not an improvement (stress-cond identical to
  current; blend/60d strictly worse on headline + 2022). CPM prod unchanged.

## Reproduce

```
.venv/bin/python research/cpm_minvar_dualcov_2026_06_02.py
```
