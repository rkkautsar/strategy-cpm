# CPM C8 (full-invest from n_pos>=3) -- exploratory backtest findings

Date: 2026-06-02
Status: RESEARCH-ONLY (CPM prod unchanged; no commit). Single in-sample point
estimates; HIGH overfit caution.

## Question / hypothesis

The oracle's top consistency fix C8 removes the n_pos=3 -> n_pos=4 exposure
cliff by LIFTING n_pos=3 to 100% invest (instead of de-risking n_pos=4):

    risky_fraction = 1.0 if n_pos >= 3 else n_pos / 4.0   # C8
    risky_fraction = min(n_pos, 4) / 4.0                  # A (prod)

Selection is identical (n_pos<=3 hold all positives EW; n_pos==4 min-var 3-of-4).
The ONLY change vs prod A is the n_pos=3 row: 75% (with 25% safe buffer) -> 100%.
Hypothesis: this is a "free" consistency fix that preserves CPM return/risk.

## Method

- Script: research/cpm_c8_fullinvest3_2026_06_02.py (template adapted from
  cpm_npos4_droptosafe_run.py). Reuses canonical harness research/cpm_harness.py
  (mooex T+1 MOO, both-252, 10 bps/side) and build_dashboard.build_artifacts for
  the 60/20/20 blend (BULL + NDX held fixed).
- Run: .venv/bin/python research/cpm_c8_fullinvest3_2026_06_02.py
- Anchor gate reproduced exactly: Sharpe=1.255673 (target 1.2557),
  MaxDD=-13.0317%, Calmar=1.007646. Baseline replica matches prod (max weight
  diff 0.00e+00).
- Blend monkeypatch FIX: build_dashboard.py:41 imports compute_target_weights
  into its own namespace, so patching cpm_live.compute_target_weights alone is a
  no-op for the blend path. The script patches BD.compute_target_weights (the
  bound reference). The droptosafe template carried this latent bug.

## CRITICAL GATE -- A vs C8 bit-identical except n_pos=3 (clean)

- n_pos=4 months bit-IDENTICAL to A: 143 (worst weight diff 0.00e+00). PASS.
- n_pos in {1,2} bit-identical to A: 6. PASS.
- n_pos=3 months CHANGED (expected): 11.
- max weight diff across ALL non-n_pos3 months: 0.00e+00.

Confirmed: C8 changes ONLY the n_pos=3 state. n_pos=4 output is exactly prod A.

## n_pos distribution (the n_pos=3 frequency)

Clean (2008-05-30..2026-05-22): 217 months, 160 risk-on.
RISK_ON n_pos counts {1,2,3,4} = {1, 5, 11, 143}.
n_pos=3 = 11 months = 6.9% of risk-on, 5.1% of all months.

Ext (1999-03-10..2026-05-22): 327 months, 237 risk-on.
RISK_ON n_pos counts = {1, 8, 22, 206}.
n_pos=3 = 22 = 9.3% of risk-on, 6.7% of all months.

n_pos=3 months (clean) -- the buffer-loss exposure dates:
  2008-06  2008-07  2008-08  2009-04  2010-06  2011-08  2011-11  2011-12
  2020-02  2020-04  2025-04

KEY: n_pos=3 is NOT a random/benign state. It clusters at crisis onset --
GFC onset (2008-06/07/08), Euro crisis (2011-08/11/12), COVID onset
(2020-02/04). Breadth collapsing from 4 to 3 positives IS the early-crisis
signal; the 25% safe buffer is doing risk work precisely there.

## SLEEVE metrics (mooex T+1, 10 bps)

clean:
config               Sharpe  Sortino  CVaR95   Calmar  Martin   MaxDD    CAGR    vol    turnover
A (prod)             1.256   1.516    -1.57%   1.008   4.257   -13.03%  13.13%  10.28%  0.590
C8 (fullinvest>=3)   1.213   1.453    -1.62%   0.774   3.621   -16.86%  13.05%  10.60%  0.586

ext:
A (prod)             1.255   1.550    -1.51%   0.971   4.117   -13.14%  12.76%   9.97%  0.567
C8 (fullinvest>=3)   1.218   1.492    -1.56%   0.719   3.586   -17.68%  12.71%  10.26%  0.569

Sleeve verdict: C8 is strictly worse on every risk metric with NO return gain.
- MaxDD: -13.03% -> -16.86% clean (+3.83pp deeper, ~29% worse); ext -13.14% ->
  -17.68% (+4.54pp). NOT near -13%.
- Calmar: 1.008 -> 0.774 clean (-23%). Martin 4.257 -> 3.621.
- CAGR: 13.13% -> 13.05% (slightly LOWER, not >= A).
- Sharpe: 1.256 -> 1.213. Sortino, CVaR also worse. Vol up ~0.3pp.

## Crisis-onset MaxDD inspection (sleeve, clean) -- the buffer-loss cost

crisis window               A_ret    C8_ret   A_DD     C8_DD
GFC 2007-09..2009-03         1.98%   -2.17%  -13.03%  -16.86%
Euro/2011 2011-05..2011-10  -0.68%   -2.34%   -7.95%   -9.73%
2015-16 selloff              4.11%    4.11%   -2.89%   -2.89%
Q4-2018                      0.53%    0.53%   -0.02%   -0.02%
COVID 2020-02..2020-04       2.11%    0.92%  -10.20%  -12.31%
2022 bear                   -0.33%   -0.33%   -5.17%   -5.17%

The entire sleeve MaxDD damage comes from the crisis-onset n_pos=3 clusters:
GFC (-13.03 -> -16.86, the global MaxDD itself), Euro (-7.95 -> -9.73), COVID
(-10.20 -> -12.31). Non-n_pos=3 crises (2015-16, Q4-2018, 2022) are untouched.
Removing the 25% safe buffer at crisis onset directly deepens the worst draws.

## BLEND 60/20/20 metrics (clean 2008-05-30..2026-05-22; BULL+NDX fixed)

config               Sharpe  Sortino  CVaR95   Calmar  Martin   MaxDD    CAGR    vol
A (prod)             1.443   1.785    -1.64%   1.557   6.161   -10.49%  16.33%  10.93%
C8 (fullinvest>=3)   1.428   1.771    -1.65%   1.524   5.927   -10.69%  16.29%  11.02%

Per-crisis (blend, clean): GFC -8.31 -> -10.69, Euro -5.72 -> -6.81, COVID
-7.97 -> -9.00. CPM is 60% of the blend so the damage is diluted, but the sign
is unchanged: C8 is worse on every metric (MaxDD +0.20pp, Calmar -0.03,
Martin -0.23, Sharpe -0.015, CAGR -0.04pp) with no upside.

## Answers

(a) Does C8 keep CPM return/risk? NO. Sleeve: CAGR is slightly BELOW A
(13.05 vs 13.13), MaxDD materially deeper (-16.86% vs -13.03%, not near -13%),
Sharpe/Calmar/Sortino/Martin all worse. Blend: directionally identical, fully
net-negative but diluted (MaxDD -10.69 vs -10.49).

(b) n_pos=3 occurs 11/160 risk-on months clean (6.9%), 22/237 ext (9.3%).
Lifting it to 100% HURTS specifically at crisis onset: the n_pos=3 months are
exactly GFC/Euro/COVID onset clusters. The buffer loss accounts for the entire
MaxDD deepening.

(c) Net: C8 is NOT a free consistency fix. The "cliff" exists because n_pos=3 is
a defensive crisis-onset state where breadth has collapsed to 3 positives; the
25% safe buffer is a deliberate feature, not a wart. C8 trades a cosmetic
exposure-monotonicity improvement for real crisis drawdown (+3.8pp sleeve MaxDD,
-23% Calmar) and a tiny CAGR loss. Recommend NOT adopting C8.

## Caveats / confidence

- Single in-sample run, point estimates only (no bootstrap per scope). HIGH
  overfit caution; do not over-read 3rd-decimal moves.
- Conclusion is robust in sign and driver: the damage is mechanistically
  attributable to removing the buffer in identified crisis-onset n_pos=3 months,
  and n_pos=4 is proven bit-identical. The direction (C8 strictly worse, no
  upside) holds on both clean and ext at sleeve and blend.
- Caveat on prior reference: the droptosafe blend numbers (~1.243) used the same
  cpm_live-only monkeypatch that is a no-op for the blend path; that script's
  BLEND section was likely measuring prod A on both rows. Sleeve numbers there
  are unaffected. Flag for the fixer/oracle if those blend figures were used.

## Artifacts

- research/cpm_c8_fullinvest3_2026_06_02.py (script)
- research/cpm_c8_fullinvest3_2026_06_02_raw.txt (raw output)
- research/cpm_c8_fullinvest3_2026_06_02_findings.md (this file)
