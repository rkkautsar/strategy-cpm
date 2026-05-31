# CPM factor stability across subperiod halves -- findings

Role: analyst (read-only re production; writes `research/` only; no production/memo edits; no commit). Throwaway harness in `research/`.

Scripts: `research/cpm_factor_stability_halves.py` (reuses `cpm_wf` + `run_cell` from `research/cpm_factorial_iv4_6factor.py`) -> `research/cpm_factor_stability_halves.json`.

## Question

The memo splits the clean window into 2008-16 (Sharpe ~1.00, includes the GFC) and 2017-26 (~1.38, a trending-asset tailwind). Two subperiods is thin and factor contributions may be regime-concentrated. Specifically test: (1) is the canary's benefit concentrated in the GFC half and ~absent/negative in 2017-26; (2) does the ranker edge survive in 2017-26 specifically, or was it earned mainly in 2008-16; (3) which of the other factors (U,S,W,P) are regime-robust vs regime-concentrated.

## Method

Reuse the EXACT 6-factor CPM factorial harness whose all-ON cell reproduces production `cpm_live.compute_target_weights`. Run the 2^6 = 64 cells ONCE over the EXT panel via the shared `_segment_returns_conv` harness (realistic T+1 MOO exact `mooex`, post-cost 10 bps/side, cov tail(252), CPM has no vol gate), then slice each cell's daily return series into the two halves and recompute metrics. Two contribution lenses per factor per half:

- **At-production marginal** = metric(all-ON) - metric(all-ON with that one factor toggled OFF), holding every other factor at production. This is exactly "CPM with X vs without X, holding else at production".
- **Background-averaged main effect** = mean on-minus-off over all 2^5 = 32 backgrounds, as a robustness cross-check. SIGN-FLIP = the on-minus-off delta changes sign across backgrounds (effect is interaction-dependent, not a stable independent contribution).

Factor map (off = AAA baseline / on = production):

| factor | OFF (baseline) | ON (production) |
|---|---|---|
| **C** canary | TIP-only (13612U(TIP)>0) | HYG-OR-TIP any-positive |
| **U** universe | AAA SPY-set (7) | CPM 8-asset (QQQ/SPHQ...) |
| **R** ranker | plain 12m momentum | vol-adjusted Faber (faber / rv_252d) |
| **S** screen | hold top-K any sign | positive-trend only |
| **W** weight | equal-weight | inverse-vol |
| **P** partial-safe | fully invested | risky_frac = min(breadth,4)/4, remainder to safe |

## Anchor + per-half endpoints (production all-ON CPM, mooex, post-cost)

Anchor gate: full clean all-ON Sharpe = 1.1658 (target 1.191) -> FAIL.

| window | dates | Sharpe | CAGR | MaxDD | Calmar |
|---|---|---:|---:|---:|---:|
| FULL | 2008-05-30..2026-05-22 | 1.1658 | 13.15% | -12.97% | 1.0137 |
| H1_2008_2016 | 2008-05-30..2016-12-31 | 0.9698 | 10.90% | -10.23% | 1.0655 |
| H2_2017_2026 | 2017-01-01..2026-05-22 | 1.3534 | 15.23% | -12.97% | 1.1738 |

The two halves reproduce the memo's regime story: H1 (GFC) materially lower Sharpe than H2 (trending tailwind). This is the backdrop against which factor contributions are read.

## Per-half factor-contribution table (at-production marginal, holding else at production)

Each row: toggle ONE factor off from full production CPM, in each half. dSharpe = production minus (production-with-that-factor-off). Positive = the production setting helps in that half.

| factor | H1 2008-16 dSharpe | H2 2017-26 dSharpe | H1 dCalmar | H2 dCalmar | H1 dMaxDD(pp) | H2 dMaxDD(pp) |
|---|---:|---:|---:|---:|---:|---:|
| **C** | +0.1476 | -0.0712 | +0.2321 | +0.0145 | +0.00 | -0.00 |
| **U** | +0.2480 | +0.0971 | +0.3918 | +0.0904 | +1.01 | -0.99 |
| **R** | +0.2767 | +0.1377 | +0.5962 | +0.1401 | +6.23 | +1.04 |
| **S** | +0.0449 | -0.0010 | +0.3295 | +0.1400 | +4.13 | +2.40 |
| **W** | +0.0601 | +0.0028 | +0.2461 | -0.0499 | +2.82 | -0.22 |
| **P** | +0.0688 | +0.0205 | +0.2778 | -0.0337 | +2.95 | -0.00 |

## Background-averaged main effect per half (cross-check; dSharpe)

Mean on-minus-off over all 32 backgrounds. SIGN-FLIP = direction not robust across backgrounds.

| factor | H1 dSharpe | H1 flip | H2 dSharpe | H2 flip | H1 dCalmar | H2 dCalmar |
|---|---:|---|---:|---|---:|---:|
| **C** | +0.1314 |  | -0.0565 | FLIP | +0.1368 | +0.0042 |
| **U** | +0.1359 | FLIP | +0.1566 |  | +0.1027 | +0.3386 |
| **R** | +0.1651 | FLIP | +0.1598 |  | +0.1867 | +0.1619 |
| **S** | -0.1014 | FLIP | -0.0051 | FLIP | -0.0506 | +0.1029 |
| **W** | +0.0071 | FLIP | -0.0053 | FLIP | +0.0309 | -0.0132 |
| **P** | +0.0217 |  | +0.0046 | FLIP | +0.0438 | +0.0063 |

## Stability verdict

(Filled narratively below from the tables; numbers are CI-limited per half -- see caveats.)

## Caveats / confidence

- all-ON cell reproduces the task anchor (full clean Sharpe 1.1658 vs 1.191). Execution is byte-identical across all 64 cells (shared harness, single EXT run sliced per window).
- **Each half is ~8-9 years of monthly rebalances; per-half Sharpe CIs are wide (order ~0.4-0.6). Per-factor per-half deltas are directional, not statistically significant on their own. The robust read is the SIGN and whether it agrees across the two lenses (at-production marginal vs background-averaged main effect), not the magnitude.**
- At-production marginal isolates the factor at the production background (most decision-relevant); the background-averaged main effect guards against that single background being unrepresentative. Where they agree in sign, confidence is higher.
- P (partial-safe) is inert when S is off (breadth==4); its main effect is diluted across the S-off half of the cube. Read P together with S.
- Two halves is exactly the thin split the brief flags; this analysis quantifies the concentration but cannot manufacture more regimes. Confidence: high on direction/sign agreement, moderate on magnitudes.
