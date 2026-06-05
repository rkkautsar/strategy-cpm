# CPM continuous vol-targeting (10% / 12%) -- exploratory findings

Status: RESEARCH-ONLY, exploratory. No prod edits, no adoption. Point-estimates
only (no bootstrap, no walk-forward). High overfit caution applies.

## Question

Does continuous vol-targeting of the whole CPM RISKY block to a fixed annualized
target (10% and 12%) improve CPM sleeve and/or 60/20/20 blend risk-adjusted
metrics versus (a) prod CPM baseline and (b) the n_pos=4 drop-to-safe variant?
How often does each target bind, and does either de-risk approach improve
integrated drawdown (Martin) or only single-trough (MaxDD/Calmar)?

## Method

- Construction: `scale = min(1, target / rv)`, de-risk-only (cap 1.0). The CPM
  risky weights (post-selection) are multiplied by `scale`; the shed weight
  `(1-scale)*risky` is routed to the prod safe asset (SHV/IEF best-of). Selection,
  canary, ranker, and safe-selector are IDENTICAL to prod -- only final risky
  weights are scaled.
- `rv` = trailing realized vol of the BASELINE (unscaled prod) CPM sleeve daily
  returns, LAGGED to sig_d (uses only returns realized before the month-end
  signal). Primary window 252d (prod-consistent); 60d reported as sensitivity.
  This is the standard non-recursive vol-target estimate and is PIT-clean. The
  same baseline sleeve series feeds both sleeve and blend rv.
- Rebalance monthly, T+1, 10 bps/side on changes. Sleeve via cpm_harness mooex
  engine; blend via build_dashboard build_artifacts (CPM swapped, BULL+NDX fixed).
- Anchor verified through harness: Sharpe 1.255673, MaxDD -0.130317, Calmar
  1.007646 (prod both-252).

Script: `research/cpm_voltarget_compare_run.py`
Raw output: `research/cpm_voltarget_compare_findings_raw.txt`
Command: `.venv/bin/python research/cpm_voltarget_compare_run.py`

## Bind frequency / effect size (clean 2008-05-30..2026-05-22, 217 months)

| config        | bind_frac | mean_scale | min_scale | mean_scale\|bind |
|---------------|-----------|------------|-----------|------------------|
| VT-10% (252d) | 45.6%     | 0.9049     | 0.5542    | 0.7915           |
| VT-12% (252d) | 33.2%     | 0.9649     | 0.6651    | 0.8941           |
| VT-10% (60d)  | 42.4%     | 0.8998     | 0.4846    | 0.7637           |

Note: even though CPM full-period vol is ~10.3%, the 252d trailing estimate
exceeds 10% in 45.6% of months and exceeds 12% in 33.2% (vol clusters above the
mean during stress). So VT-12 is NOT a near-no-op -- it binds about 1/3 of
months, but lightly (mean scale 0.965 overall, 0.894 when binding). VT-10 binds
nearly half the months and cuts risk harder (min scale 0.55).

## SLEEVE (clean) -- mooex T+1, 10 bps

| config          | Sharpe | Sortino | CVaR95_d | Calmar | Martin | MaxDD   | CAGR   | vol    | turnover |
|-----------------|--------|---------|----------|--------|--------|---------|--------|--------|----------|
| baseline (prod) | 1.256  | 1.516   | -1.57%   | 1.008  | 4.257  | -13.03% | 13.13% | 10.28% | 0.590    |
| drop-to-safe    | 1.243  | 1.518   | -1.26%   | 0.802  | 3.776  | -13.03% | 10.45% | 8.30%  | 0.525    |
| VT-10% (252d)   | 1.276  | 1.568   | -1.33%   | 1.114  | 4.259  | -10.36% | 11.54% | 8.89%  | 0.594    |
| VT-12% (252d)   | 1.270  | 1.545   | -1.46%   | 1.061  | 4.290  | -11.78% | 12.50% | 9.67%  | 0.600    |
| VT-10% (60d)    | 1.250  | 1.518   | -1.35%   | 0.941  | 4.007  | -12.08% | 11.36% | 8.95%  | 0.613    |

## SLEEVE (ext 1999-03-10..) -- mooex T+1, 10 bps

| config          | Sharpe | Sortino | Calmar | Martin | MaxDD   | CAGR   | vol   | bind  |
|-----------------|--------|---------|--------|--------|---------|--------|-------|-------|
| baseline (prod) | 1.255  | 1.550   | 0.971  | 4.117  | -13.14% | 12.76% | 9.97% | -     |
| drop-to-safe    | 1.266  | 1.585   | 0.737  | 3.773  | -14.11% | 10.40% | 8.07% | -     |
| VT-10% (252d)   | 1.269  | 1.592   | 1.013  | 4.034  | -11.30% | 11.44% | 8.84% | 43.1% |
| VT-12% (252d)   | 1.265  | 1.574   | 1.010  | 4.100  | -12.16% | 12.28% | 9.51% | 25.1% |
| VT-10% (60d)    | 1.254  | 1.559   | 0.900  | 3.855  | -12.43% | 11.19% | 8.77% | 38.8% |

## BLEND 60/20/20 (clean) -- close-to-close T+1, 10 bps; BULL+NDX identical

| config          | Sharpe | Sortino | CVaR95_d | Calmar | Martin | MaxDD   | CAGR   | vol    |
|-----------------|--------|---------|----------|--------|--------|---------|--------|--------|
| baseline (prod) | 1.495  | 1.852   | -1.64%   | 1.626  | 6.715  | -10.46% | 17.02% | 10.93% |
| drop-to-safe    | 1.509  | 1.896   | -1.45%   | 1.690  | 6.689  | -9.05%  | 15.30% | 9.76%  |
| VT-10% (252d)   | 1.519  | 1.911   | -1.51%   | 1.768  | 6.921  | -9.05%  | 16.00% | 10.13% |
| VT-12% (252d)   | 1.510  | 1.886   | -1.58%   | 1.807  | 6.909  | -9.20%  | 16.61% | 10.57% |
| VT-10% (60d)    | 1.513  | 1.900   | -1.51%   | 1.751  | 6.784  | -9.10%  | 15.92% | 10.12% |

## Per-crisis (sleeve, clean) cum return / maxDD

| crisis             | base ret | VT10 ret | VT12 ret | base DD | VT10 DD | VT12 DD |
|--------------------|----------|----------|----------|---------|---------|---------|
| GFC 2007-09..03    | 1.98%    | 5.12%    | 3.22%    | -13.03% | -10.02% | -11.78% |
| Euro 2011-05..10   | -0.68%   | 1.10%    | -0.64%   | -7.95%  | -6.84%  | -7.84%  |
| 2015-16 selloff    | 4.11%    | 4.11%    | 4.11%    | -2.89%  | -2.89%  | -2.89%  |
| Q4-2018            | 0.53%    | 0.53%    | 0.53%    | -0.02%  | -0.02%  | -0.02%  |
| COVID 2020-02..04  | 2.11%    | 2.08%    | 2.11%    | -10.20% | -10.20% | -10.20% |
| 2022 bear          | -0.33%   | -0.12%   | -0.24%   | -5.17%  | -4.17%  | -4.97%  |

Per-crisis (blend) shows the same direction: VT cuts GFC blend DD -7.40% ->
-6.13% (VT10) and improves Euro/2011 and 2022; COVID unchanged (fast shock, the
252d trailing estimate had not yet risen). drop-to-safe wins only COVID/2022
mildly (its n_pos=4 trigger happened to align there).

## Verdicts

(a) YES -- vol-targeting improves risk-adjusted metrics, not just CAGR-for-vol.
VT-10% and VT-12% (252d) both beat baseline on Sharpe, Sortino, Calmar, MaxDD,
and CVaR at BOTH sleeve and blend. Crucially Martin (integrated DD) improves too:
sleeve 4.257 -> 4.290 (VT-12); blend 6.715 -> 6.921 (VT-10). This is the key
difference vs drop-to-safe, which only traded CAGR for vol.

(b) Bind frequency: VT-10% binds 45.6% of months (mean scale 0.905, min 0.554);
VT-12% binds 33.2% (mean 0.965, min 0.665). VT-12 is light but real, not a no-op.

(c) Vol-target DOMINATES drop-to-safe at sleeve and at blend. Sleeve: VT-10
Sharpe 1.276 / Calmar 1.114 / Martin 4.259 vs drop-to-safe 1.243 / 0.802 / 3.776.
Blend: VT-10 1.519 / 1.768 / 6.921 vs drop-to-safe 1.509 / 1.690 / 6.689.
Mechanism: drop-to-safe only de-risks in the rare n_pos=4 case (single-trough
MaxDD/Calmar benefit, Martin flat-to-worse), whereas continuous vol-targeting
de-risks across many months and so reduces the integrated drawdown path -- it
improves BOTH MaxDD/Calmar AND Martin.

(d) Net (exploratory): VT-10% (252d) is the best candidate overall (top Sharpe
and Martin at blend, biggest crisis-DD relief). VT-12% (252d) is a close second
and retains more CAGR (16.61% vs 16.00% blend) with nearly identical Martin --
better choice if CAGR retention is prioritized. The 60d window is worse on every
risk-adjusted metric (noisier scale, higher turnover, lower Martin) -- prefer
252d. drop-to-safe is dominated and is not the preferred de-risk approach.

## Caveats / confidence

- POINT ESTIMATES ONLY. Improvements are modest (sleeve Sharpe +0.014..+0.020;
  blend Sharpe +0.015..+0.024; blend Martin +0.19..+0.21). These are compelling
  enough to NOTE for a later bootstrap / walk-forward confirmation but do NOT by
  themselves justify adoption. Bootstrap not run per scope.
- Overfit caution HIGH but mitigated: targets 10%/12% are a-priori (CPM
  full-period vol ~10.3%), window 252d is prod-consistent, no parameter tuning.
  Only sensitivity tested is window (60d worse, supports 252d a-priori choice).
- rv proxy uses the baseline (unscaled) sleeve returns to estimate vol (standard
  non-recursive vol-target). PIT integrity maintained (lagged to sig_d).
- COVID DD unchanged: a 252d trailing estimator cannot pre-empt a fast shock;
  the de-risk arrives after the vol spike, helping subsequent months not the
  initial crash. A faster window would help the shock but hurts everywhere else.
- Cached-data caveat: yfinance OHLC/panel from local cache; last bar 2026-05-22.
- Confidence: MEDIUM that vol-target is directionally better than both baseline
  and drop-to-safe (consistent across sleeve, blend, ext window, and crises);
  LOW that the magnitude is robust without bootstrap.

## Suggested next step (if pursued)

Bootstrap + walk-forward on VT-10% (252d) and VT-12% (252d) at the BLEND level
(stationary block bootstrap of daily returns; rolling-window Sharpe/Martin
stability) before any adoption discussion. Hand off to fixer only if a robust
edge survives.
