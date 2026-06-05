# CPM parameter-free external vol-target anchors vs fixed VT-10/12

Analyst, exploratory. Research-only: no prod edit, no commit. Point-estimates
only (no bootstrap/WF). High overfit caution -- anchors chosen a-priori, no tuning.

## Question

Fixed continuous vol-target on the CPM sleeve (scale risky block by
`min(1, target/rv_CPM)`, de-risk-only, shed->safe, monthly/lagged/T+1/10bps) is
the best de-risk found for CPM, but it uses a hand-picked 10%/12% TARGET. Can a
PARAMETER-FREE external benchmark vol REPLACE that magic constant and match the
fixed VT-10/12 efficiency?

Mechanism is IDENTICAL across all configs; only the TARGET (numerator) differs.
`rv_CPM` = trailing 252d realized vol of the baseline CPM sleeve daily returns,
lagged to sig_d (UNCHANGED denominator). SPY-vol anchors were DROPPED a-priori
(SPY ~16-18% >> CPM ~10% => near no-op).

- 60/40 = 0.6*SPY + 0.4*IEF fixed-weight daily returns (full-period ann vol 11.18%).
- VT-6040-trailing: target = trailing 252d realized vol of 60/40, lagged.
- VT-6040-expand: target = expanding-window mean of completed-month 60/40
  realized vol (inception -> t-1). Parameter-free + contamination-resistant.

## Method

- `research/cpm_voltarget_paramfree_run.py` (reuses `cpm_harness` sleeve engine,
  fixed-VT mechanism helpers from `cpm_voltarget_compare_run`, and
  `build_dashboard.build_artifacts` for the blend via monkeypatch).
- Run: `.venv/bin/python research/cpm_voltarget_paramfree_run.py`
- Anchor verified: Sharpe 1.255673 / MaxDD -0.130317 / Calmar 1.007646.
- Windows: clean 2008-05-30..2026-05-22 (decision), ext 1999-03-10.. (confirm).
- PIT integrity: trailing uses returns <= sig_d; expanding uses only completed
  months strictly before sig_d's month (MIN_MONTH_DAYS=15, MIN_OBS=4).
- Raw output: `research/cpm_voltarget_paramfree_findings_raw.txt`.

## Bind freq / effect size / target level (clean, 217 months)

```
config               bind_frac  mean_scl  min_scl  scl|bind  meanTgt   minTgt   maxTgt
--------------------------------------------------------------------------------------
VT-10% (fixed)           45.6%    0.9049   0.5542    0.7915   10.00%   10.00%   10.00%
VT-12% (fixed)           33.2%    0.9649   0.6651    0.8941   12.00%   12.00%   12.00%
VT-6040-trailing         55.3%    0.8834   0.5331    0.7891   10.40%    3.77%   25.99%
VT-6040-expand           51.6%    0.9006   0.5955    0.8074    9.79%    9.10%   10.93%
```

CPM sleeve full-period vol ~10.28%. `target > rv_CPM` => scale=1 => no de-risk.

## SLEEVE (clean) -- mooex T+1, 10bps

```
config              Sharpe  Sortino  CVaR95_d  Calmar  Martin    MaxDD    CAGR     vol  turnover
-----------------------------------------------------------------------------------------------
baseline (prod)      1.256    1.516    -1.57%   1.008   4.257  -13.03%  13.13%  10.28%   0.590
VT-10% (fixed)       1.276    1.568    -1.33%   1.114   4.259  -10.36%  11.54%   8.89%   0.594
VT-12% (fixed)       1.270    1.545    -1.46%   1.061   4.290  -11.78%  12.50%   9.67%   0.600
VT-6040-trailing     1.307    1.591    -1.38%   1.191   4.763  -10.18%  12.13%   9.11%   0.574
VT-6040-expand       1.262    1.552    -1.33%   1.116   4.216  -10.20%  11.38%   8.88%   0.594
```

## BLEND 60/20/20 (clean) -- close-to-close T+1, 10bps; BULL+NDX identical

```
config              Sharpe  Sortino  CVaR95_d  Calmar  Martin    MaxDD    CAGR     vol  bind  mscl
-------------------------------------------------------------------------------------------------
baseline (prod)      1.495    1.852    -1.64%   1.626   6.715  -10.46%  17.02%  10.93%    -     -
VT-10% (fixed)       1.519    1.911    -1.51%   1.768   6.921   -9.05%  16.00%  10.13% 45.6% 0.905
VT-12% (fixed)       1.510    1.886    -1.58%   1.807   6.909   -9.20%  16.61%  10.57% 33.2% 0.965
VT-6040-trailing     1.522    1.895    -1.54%   1.748   7.305   -9.33%  16.32%  10.29% 55.3% 0.883
VT-6040-expand       1.510    1.896    -1.51%   1.763   6.835   -9.02%  15.90%  10.13% 51.6% 0.901
```

ext sleeve confirms (all VT configs Sharpe ~1.26-1.29, MaxDD ~-11.3% vs baseline
-13.1%); trailing best Sharpe/Martin in ext too. No sign flips.

## Per-crisis (blend, clean) cum return / maxDD

```
crisis                  base_ret  VT10  VT12  6040tr 6040ex | base_DD   VT10    6040tr  6040ex
---------------------------------------------------------------------------------------------
GFC 07-09..09-03          7.98%  9.54% 8.60%  9.43%  9.62% | -7.40%  -6.13%  -6.16%  -6.14%
Euro 2011                -0.44%  0.54% -0.44% 1.11%  0.22% | -5.61%  -5.01%  -4.92%  -5.26%
2015-16 selloff           4.56%  4.56% 4.56%  4.56%  4.56% | -2.89%  -2.89%  -2.89%  -2.89%
Q4-2018                   0.36%  0.36% 0.36%  0.40%  0.37% | -0.02%  -0.02%  -0.02%  -0.02%
COVID 2020                2.28%  2.25% 2.28%  2.58%  2.14% | -7.96%  -7.96%  -7.63%  -7.96%
2022 bear                 0.21%  0.21% 0.26%  0.21%  0.19% | -5.09%  -4.49%  -3.98%  -4.31%
```

All VT configs improve GFC/Euro/2022 DDs vs baseline; COVID DD unchanged (the
COVID drawdown is a fast gap the monthly/lagged scale cannot pre-empt -- it fires
the month AFTER vol spikes). Trailing edges the deepest 2022/COVID DD reductions.

## Verdict (a)-(e)

(a) YES -- a parameter-free external anchor matches the fixed VT-10/12 on the
blend. **VT-6040-expand** lands on top of VT-10 (Sharpe 1.510 vs 1.519, Calmar
1.763 vs 1.768, Martin 6.835 vs 6.921, MaxDD -9.02% vs -9.05%) -- differences are
within point-estimate noise. **VT-6040-trailing** is marginally the best raw
blend (Sharpe 1.522, Martin 7.305, best 2022 DD -3.98%) but at the cost of a
wildly swinging target (see d).

(b) YES -- **expanding 60/40 vol REDISCOVERS ~VT-10 parameter-free.** Its mean
target is 9.79% with range [9.10%, 10.93%] -- effectively a constant pinned near
10%, exactly the hand-picked VT-10 level. Bind freq 51.6% vs VT-10's 45.6%,
mean scale 0.901 vs 0.905. The 60/40 portfolio's own long-run vol IS ~10%, so
the magic "10%" was never arbitrary -- it equals a balanced portfolio's risk.
This is the same mechanism by which expanding-QQQ rediscovered NDX's constant.

(c) SPY-vol configs dropped a-priori (agreed: ~16-18% >> CPM ~10% => target
always above rv_CPM => scale=1 => no-op). Not re-tested here.

(d) Trailing-vs-expanding contamination: CONFIRMED structurally, but BENIGN here.
Trailing 60/40 target swings [3.77%, 25.99%] (regime-contaminated -- spikes in
2008/2020, collapses in calm regimes). Expanding stays tight [9.10%, 10.93%].
Because the mechanism is de-risk-ONLY, trailing's contamination is asymmetric:
high target in/after stress just means "no de-risk" (full exposure into the
recovery, which helps returns), while low target in calm regimes makes it the
MOST aggressive de-risker (lowest mean scale 0.883, highest bind 55.3%). That
combination happened to win on point estimates, but it makes behavior strongly
regime-dependent and far less predictable than the near-constant expanding anchor.
The NDX-style "trailing rises in stress -> protects less when needed" failure
mode does not bite the de-risk-only CPM construction.

(e) RECOMMENDATION: The magic 10/12 constant CAN be removed parameter-free.
**VT-6040-expand** is the principled replacement -- it rediscovers ~10% from a
balanced portfolio's long-run vol, with no tuning and full PIT integrity, and
matches fixed VT-10 on every blend metric. It is the better story if the goal is
to retire the hand-picked constant. VT-6040-trailing scores marginally higher but
its target volatility makes it a riskier (regime-dependent) bet whose edge is
likely noise. Fixed VT-10 remains the operationally simplest choice; expanding
60/40 is the parameter-free equivalent with economic justification, fixed is the
parsimony pick.

## Caveats / confidence

- Point-estimates only; blend Sharpe spreads (1.510-1.522) and Martin
  (6.835-7.305) are inside plausible noise -- do NOT rank-order without bootstrap.
- COMPELLING for later bootstrap: VT-6040-expand (parameter-free == VT-10) and
  VT-6040-trailing (best raw, but check robustness).
- Anchors chosen a-priori (60/40 == balanced-portfolio risk); no parameter
  search -> low overfit risk for the expanding anchor specifically.
- Cached frozen dataset (SHV/TLT 2026-05-22 download fail is harmless; uses
  cache); absolute levels apples-to-apples across configs.
- Monthly/lagged scale cannot pre-empt fast gap crashes (COVID DD unchanged);
  protection accrues to slower-building stress (GFC/Euro/2022).
- Confidence: HIGH on (b) (expanding 60/40 == ~VT-10, target near-constant 9.79%)
  and (d) (trailing target contamination is real but benign under de-risk-only).
  MEDIUM on (a)/(e) ranking -- needs bootstrap to separate the configs.

## Next handoff

None required. If a config is to be adopted, route to oracle (decision) +
fixer (prod edit) after a bootstrap/WF significance pass on VT-6040-expand vs
fixed VT-10.
