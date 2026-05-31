# CPM vol-window standardization: prod vs both-252 vs both-504

Research-only decision memo. Does NOT edit cpm_memo.md or production. No commit.

## Question

Production CPM uses two different volatility lookbacks: rank-vol = 252d (inside the
m_faber / rv252 ranker) and weight-vol = 504d (inside the 1/rv504 inverse-vol
weighting). The review flagged this 252/504 mismatch as an extra degree of freedom.
Should we standardize BOTH windows to a single value to reduce DoF -- both-252 or
both-504 -- holding everything else at production (canary 13612U, Faber ranker, K=4,
T+1 MOO execution)?

## Method

- Harness: `research/cpm_volwindow_standardize_harness.py` (reuses the A1
  `cpm_weights_param` parametrized vol windows + the mooex T+1 MOO segment engine).
- Execution: T+1 MOO exact (mooex), real OHLC opens, 10 bps/side.
- Windows: clean 2008-05-30..2026-05-22 (decision lens); ext 1999-03-10..2026-05-22
  (robustness).
- Run:
  ```
  .venv/bin/python research/cpm_volwindow_standardize_harness.py
  ```
- Outputs: `research/cpm_volwindow_standardize_findings.json` (full numbers).

### Anchor reproduced FIRST (both code paths)

prod rank252/wt504, clean, mooex:

- Sharpe 1.1910, MaxDD -12.67%, Calmar 1.0615  -- matches target exactly (both the
  original H `run_cpm` path and the harness's own `segment_mooex` offset=0 path).

## Results

### 1. Clean + ext (Sharpe / Calmar / Martin / MaxDD / CAGR)

Clean (2008-05-30..2026-05-22), decision lens:

| config            | Sharpe | Calmar | Martin | MaxDD   | CAGR   |
|-------------------|--------|--------|--------|---------|--------|
| prod (252/504)    | 1.1910 | 1.0615 | 3.965  | -12.67% | 13.44% |
| both-252 (252/252)| 1.1658 | 1.0137 | 3.691  | -12.97% | 13.15% |
| both-504 (504/504)| 1.2039 | 0.9877 | 4.034  | -13.73% | 13.56% |

Ext (1999-03-10..2026-05-22), robustness:

| config            | Sharpe | Calmar | Martin | MaxDD   | CAGR   |
|-------------------|--------|--------|--------|---------|--------|
| prod (252/504)    | 1.2244 | 0.8689 | 3.856  | -15.93% | 13.84% |
| both-252 (252/252)| 1.2102 | 0.8644 | 3.707  | -15.73% | 13.60% |
| both-504 (504/504)| 1.2296 | 0.8055 | 3.898  | -17.29% | 13.93% |

A1's clean numbers reproduced exactly (prod 1.1910/-12.67%/1.062; both-252
1.1658/-12.97%/1.014; both-504 1.2039/-13.73%/0.988). It is a plateau: tiny,
mixed-sign deltas.

### 2. Per-crisis MaxDD (point estimates) -- all configs KEEP the catches

| config    | GFC 2008 | COVID 2020 | 2022    |
|-----------|----------|------------|---------|
| prod      | -9.83%   | -10.06%    | -6.33%  |
| both-252  | -10.23%  | -10.50%    | -7.96%  |
| both-504  | -9.83%   | -10.06%    | -6.33%  |

- All three configs go defensive in every crisis -- none loses a catch.
- both-504 crisis DD is IDENTICAL to prod across all three crises (rank window
  change does not alter the defensive-mode weights once the canary trips).
- both-252 is marginally deeper in all three (worst in 2022: -7.96% vs -6.33%) but
  still clearly catches each crisis.

### 3. Turnover -- unchanged by standardizing

| config    | annualized one-way | per-rebal avg |
|-----------|--------------------|---------------|
| prod      | 514.6%             | 42.9%         |
| both-252  | 516.4%             | 43.0%         |
| both-504  | 514.9%             | 42.9%         |

Standardizing the vol window does not move turnover (selection cadence is unchanged).

### 4. EOM-offset stability (clean Sharpe across EOM..EOM+3)

| config    | EOM   | EOM+1 | EOM+2 | EOM+3 | std    |
|-----------|-------|-------|-------|-------|--------|
| prod      | 1.191 | 1.013 | 0.991 | 0.897 | 0.1063 |
| both-252  | 1.166 | 0.974 | 0.963 | 0.871 | 0.1071 |
| both-504  | 1.204 | 1.030 | 1.008 | 0.943 | 0.0964 |

- Standardizing does NOT meaningfully change the execution-cliff sensitivity. All
  three configs show the same EOM -> EOM+3 decay (~0.30 Sharpe), a known CPM
  turn-of-month property, not a vol-window effect.
- both-504 is marginally the most offset-stable (std 0.0964); both-252 marginally
  the least (0.1071). Differences are tiny.

### 5. Paired stationary block bootstrap (B=5000, block=21d, seed=42)

Same block index drawn for both streams each resample; metric DELTA recomputed per
resample (matches `paired_bootstrap_pair_vs_continuous.py` /
`bootstrap_ci_2026_05_28.py` methodology). 95% CI = [2.5, 97.5] pct.

Clean window (decision lens):

| delta                | metric | mean    | 95% CI               | verdict     |
|----------------------|--------|---------|----------------------|-------------|
| both-252 - prod      | Sharpe | -0.0250 | [-0.0607, +0.0093]   | includes 0  |
| both-252 - prod      | Calmar | -0.0474 | [-0.1579, +0.0231]   | includes 0  |
| both-252 - prod      | Martin | -0.2163 | [-0.5584, +0.0300]   | includes 0  |
| both-504 - prod      | Sharpe | +0.0132 | [-0.0212, +0.0519]   | includes 0  |
| both-504 - prod      | Calmar | +0.0118 | [-0.0776, +0.1140]   | includes 0  |
| both-504 - prod      | Martin | +0.0735 | [-0.1901, +0.3912]   | includes 0  |
| both-252 - both-504  | Sharpe | -0.0382 | [-0.0929, +0.0127]   | includes 0  |
| both-252 - both-504  | Calmar | -0.0592 | [-0.2101, +0.0537]   | includes 0  |
| both-252 - both-504  | Martin | -0.2898 | [-0.7703, +0.0764]   | includes 0  |

Ext window: same conclusion -- every CI includes 0 (largest |mean| is
both-252-both-504 Martin -0.134, CI [-0.530, +0.197]).

ALL nine clean deltas (and all nine ext deltas) INCLUDE 0 across Sharpe, Calmar, and
Martin. Confirms the A1 plateau: the three vol-window configs are
statistically indistinguishable. Standardizing is statistically FREE, and the
both-252-vs-both-504 choice is a parsimony / drawdown judgment, NOT a performance
one.

## What standardizing costs vs production (quantified)

Per A1, the 252/504 mismatch wins ONLY on clean drawdown. Quantified vs prod:

| move                  | clean MaxDD cost | clean Calmar cost | clean Sharpe cost |
|-----------------------|------------------|-------------------|-------------------|
| prod -> both-252      | -0.30pp (-12.97) | -0.048 (1.014)    | -0.025 (1.166)    |
| prod -> both-504      | -1.06pp (-13.73) | -0.074 (0.988)    | +0.013 (1.204)    |

All within bootstrap noise (CIs include 0). The mismatch's only real edge is the
shallowest clean MaxDD (-12.67%); giving it up costs 0.3-1.1pp of clean drawdown
and a small Calmar haircut, with no statistically real Sharpe/Martin change.

## Recommendation: both-252

For CPM's capital-preservation objective, standardize to **both-252**.

1. Parsimony + alignment (the stated preference): the ranker ALREADY uses 252d. Moving
   the weight window 504 -> 252 aligns both stages to the single window the signal
   already trusts, and is the SMALLER deviation from prod's existing logic (only the
   weight window moves; the ranker is untouched). both-504 instead changes the ranker
   window the strategy was selected on.
2. Capital preservation (CPM headline = Calmar / MaxDD): among the two standardized
   options, both-252 has the shallower clean MaxDD (-12.97% vs -13.73%) and the higher
   clean Calmar (1.014 vs 0.988). both-504's deepest drawdown + lowest Calmar is the
   wrong tradeoff for a capital-preservation mandate.
3. Statistically free: all bootstrap CIs include 0; both-252 vs both-504 is
   indistinguishable on Sharpe/Calmar/Martin. The choice is correctly made on
   parsimony + drawdown, not performance.

This is a robustness/parsimony move (one fewer free parameter), expected to cost a
little, not a performance upgrade. The cost vs production is ~0.3pp clean MaxDD and
~0.05 Calmar -- negligible and within noise.

### Honest counter-case for both-504

both-504 has the higher clean Sharpe (1.2039) and Martin (4.034), reproduces prod's
crisis drawdowns EXACTLY (all three crises), and is marginally the most
offset-stable (std 0.0964). If the objective were risk-adjusted return (Sharpe/Martin)
rather than drawdown, both-504 would be the pick. But it carries the deepest clean and
ext MaxDD (-13.73% / -17.29%) and lowest Calmar -- and the Sharpe/Martin edge is not
statistically real (CI includes 0). For capital preservation, the drawdown profile
decides, and that favors both-252.

## Caveats / confidence

- Clean = decision lens; ext = robustness context. Single in-sample path; no walk-forward.
- mooex T+1 MOO with real opens, 10 bps/side.
- Per-crisis MaxDD are point estimates over fixed calendar windows (GFC 2008-05-30..2009-06-30,
  COVID 2020-02-01..2020-06-30, 2022 full year), not bootstrapped.
- Bootstrap: stationary block, B=5000, block=21d, seed=42, paired (same blocks both streams).
- Confidence: HIGH that the three configs are statistically indistinguishable (every CI
  includes 0, two windows). MODERATE on the both-252 over both-504 call -- it rests on a
  small, non-significant clean-MaxDD/Calmar edge plus the parsimony/alignment argument, not
  on a performance difference.
