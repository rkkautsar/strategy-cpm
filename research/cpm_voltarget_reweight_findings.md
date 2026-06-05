# CPM vol-target by COVARIANCE RE-WEIGHTING vs EW scale-to-cash -- exploratory findings

Status: RESEARCH-ONLY, exploratory. No prod edits, no adoption, no commit.
Point-estimates + per-crisis + 3-segment walk-forward (no bootstrap, per scope).
High overfit and estimation-error caution apply -- covariance weighting is the
classic fragile move, so turnover and walk-forward are weighted heavily.

## Question

De-risk the CPM risky block TO A 10% VOL TARGET BY COVARIANCE RE-WEIGHTING
(adjust risky weights via the covariance matrix Sigma so portfolio ex-ante vol
hits target through diversification, shedding to cash only the residual that
diversification cannot absorb) -- versus the current/reference EW uniform
scale-to-cash. Hypothesis: re-weighting hits the same target vol while keeping
MORE invested in risky assets (less cash drag) -> retains more CAGR at the same
realized vol -> better Sharpe/Calmar/Martin. SELECTION is unchanged from prod.

## Method

Selection IDENTICAL to prod for every config (vol-adj Faber rank + positive
filter + TIP-only canary + min-var 3-of-4 at n_pos=4). Only the WEIGHTING of the
selected picks changes. Target vol = 10% (annualized). Monthly, T+1 MOO, 10
bps/side. Long-only weights. Sigma/rv LAGGED to sig_d (PIT-clean).

- baseline (prod EW, no VT): prod `compute_target_weights` as-is.
- EW-scale-to-cash VT10 (reference, prior best de-risk): prod output scaled by
  `min(1, target/rv_CPM)`, shed -> safe. rv_CPM = trailing 252d realized vol of
  the baseline CPM sleeve daily returns, lagged. Reproduces
  `cpm_voltarget_compare` VT-10% (252d).
- V1 min-var-weight + residual cash: `w` = long-only min-variance weights over
  picks (minimize `w'Sigma w`, sum w = 1, w_i >= 0). Sigma = annualized sample
  covariance over trailing CORR_LOOKBACK_DAYS (252d), lagged (same window as
  `cpm_live._min_var_subset`). Ex-ante vol `v = sqrt(w'Sigma w)`; de-risk only:
  `f = min(1, target/v)`; risky = `w*f`, cash = `(1-f)` -> safe. If `v <= target`,
  hold `w` fully (no lever-up).
- V2 target-vol tilt (exact formulation, SLSQP):
  `maximize s.w  s.t.  sqrt(w'Sigma w) <= target,  w_i >= 0,  sum_i w_i <= 1;
  cash = 1 - sum w -> safe`, where `s_i` = the prod vol-adjusted Faber score
  (`faber[i]/vol_252[i]`) of pick i (always > 0 since picks pass the positive
  filter). Objective pushes exposure toward 1 and tilts to high-momentum picks;
  covariance constraint caps vol via diversification; cash is last-resort residual.

Anchor verified through harness: Sharpe 1.255673, MaxDD -0.130317, Calmar
1.007646 (prod both-252).

Script: `research/cpm_voltarget_reweight_run.py`
Raw output: `research/cpm_voltarget_reweight_findings_raw.txt`
Command: `.venv/bin/python research/cpm_voltarget_reweight_run.py`

## Ex-ante diagnostics (clean, 217 months, 160 risk-on)

| variant            | mean ex-ante vol | mean risk-on exposure |
|--------------------|------------------|-----------------------|
| V1 min-var-weight  | 8.86%            | 85.22%                |
| V2 target-vol tilt | 9.90%            | 81.69%                |

V1's diversified min-var book is ALREADY under the 10% target almost every month
(mean ex-ante vol 8.86%), so the residual-cash shed rarely triggers -- V1 holds
the min-var book essentially fully. V2's tilt rides the vol cap (9.90%).

## SLEEVE (clean) -- mooex T+1, 10 bps (expo = mean weight in risky universe, all months)

| config                 | Sharpe | Sortino | CVaR95_d | Calmar | Martin | MaxDD   | CAGR   | vol    | turnover | expo   |
|------------------------|--------|---------|----------|--------|--------|---------|--------|--------|----------|--------|
| baseline (prod EW)     | 1.256  | 1.516   | -1.57%   | 1.008  | 4.257  | -13.03% | 13.13% | 10.28% | 0.590    | 70.97% |
| EW-scale-to-cash VT10  | 1.276  | 1.568   | -1.33%   | 1.114  | 4.259  | -10.36% | 11.54% | 8.89%  | 0.594    | 62.73% |
| V1 min-var-weight      | 1.115  | 1.316   | -1.30%   | 0.762  | 2.536  | -12.60% | 9.60%  | 8.59%  | 0.661    | 62.84% |
| V2 target-vol tilt     | 0.731  | 0.870   | -1.58%   | 0.482  | 1.277  | -14.93% | 7.20%  | 10.30% | 0.819    | 60.23% |

## SLEEVE (ext 1999-03..) -- mooex T+1, 10 bps

| config                 | Sharpe | Sortino | Calmar | Martin | MaxDD   | CAGR   | vol    | turnover | expo   |
|------------------------|--------|---------|--------|--------|---------|--------|--------|----------|--------|
| baseline (prod EW)     | 1.255  | 1.550   | 0.971  | 4.117  | -13.14% | 12.76% | 9.97%  | 0.567    | 69.34% |
| EW-scale-to-cash VT10  | 1.269  | 1.592   | 1.013  | 4.034  | -11.30% | 11.44% | 8.84%  | 0.567    | 62.37% |
| V1 min-var-weight      | 1.075  | 1.308   | 0.701  | 2.505  | -13.16% | 9.23%  | 8.55%  | 0.642    | 64.32% |
| V2 target-vol tilt     | 0.721  | 0.870   | 0.378  | 1.242  | -19.08% | 7.22%  | 10.43% | 0.779    | 62.26% |

## BLEND 60/20/20 (clean 2008-05-30..2026-05-22) -- close-to-close T+1, 10 bps; BULL+NDX identical

| config                 | Sharpe | Sortino | CVaR95_d | Calmar | Martin | MaxDD   | CAGR   | vol    |
|------------------------|--------|---------|----------|--------|--------|---------|--------|--------|
| baseline (prod EW)     | 1.495  | 1.852   | -1.64%   | 1.626  | 6.715  | -10.46% | 17.02% | 10.93% |
| EW-scale-to-cash VT10  | 1.519  | 1.911   | -1.51%   | 1.768  | 6.921  | -9.05%  | 16.00% | 10.13% |
| V1 min-var-weight      | 1.505  | 1.923   | -1.40%   | 1.391  | 5.615  | -10.68% | 14.86% | 9.52%  |
| V2 target-vol tilt     | 1.256  | 1.583   | -1.52%   | 1.085  | 4.190  | -12.02% | 13.04% | 10.19% |

## Per-crisis (sleeve, clean) cum return / maxDD

| crisis             | base ret | EWcash ret | V1 ret | V2 ret | base DD | EWcash DD | V1 DD   | V2 DD   |
|--------------------|----------|------------|--------|--------|---------|-----------|---------|---------|
| GFC 2007-09..03    | 1.98%    | 5.12%      | 2.57%  | 2.40%  | -13.03% | -10.02%   | -9.98%  | -11.65% |
| Euro 2011-05..10   | -0.68%   | 1.10%      | 4.70%  | 1.99%  | -7.95%  | -6.84%    | -6.84%  | -11.15% |
| 2015-16 selloff    | 4.11%    | 4.11%      | 4.11%  | 4.11%  | -2.89%  | -2.89%    | -2.89%  | -2.89%  |
| Q4-2018            | 0.53%    | 0.53%      | 0.47%  | 0.57%  | -0.02%  | -0.02%    | -0.02%  | -0.02%  |
| COVID 2020-02..04  | 2.11%    | 2.08%      | 2.05%  | 6.37%  | -10.20% | -10.20%   | -12.53% | -14.30% |
| 2022 bear          | -0.33%   | -0.12%     | -1.86% | -3.14% | -5.17%  | -4.17%    | -6.95%  | -8.26%  |

V1 helps Euro/2011 (4.70% vs EWcash 1.10%) but HURTS 2022 (-1.86% vs -0.12%) and
deepens COVID DD (-12.53% vs -10.20%). V2 deepens DD nearly everywhere (Euro
-11.15%, COVID -14.30%, 2022 -8.26%). Blend per-crisis shows the same pattern.

## 3-segment walk-forward (sleeve, clean) -- OOS stability

| segment           | metric | base   | EWcash | V1     | V2     |
|-------------------|--------|--------|--------|--------|--------|
| seg1 2008..2014   | Sharpe | 0.942  | 1.029  | 0.914  | 0.527  |
|                   | Martin | 2.616  | 2.779  | 1.628  | 0.761  |
| seg2 2014..2020   | Sharpe | 1.218  | 1.216  | 1.002  | 0.445  |
|                   | Martin | 4.025  | 4.017  | 2.534  | 0.666  |
| seg3 2020..2026   | Sharpe | 1.670  | 1.582  | 1.411  | 1.264  |
|                   | Martin | 8.949  | 8.135  | 4.341  | 3.976  |

V1 underperforms EW-scale-to-cash on Sharpe AND Martin in ALL THREE segments;
V2 is worst in all three. No sub-period rescues the re-weight variants. (Blend
walk-forward: identical ordering -- EWcash >= V1 > V2 every segment.)

## Verdicts on (a)-(e)

(a) NO -- covariance re-weight does NOT hit the target with more useful equity
exposure. The hypothesis premise (large cash drag for diversification to recover)
is FALSE at the 10% target: EW-scale-to-cash VT10 already keeps ~85% risk-on
exposure (it sheds little to cash; mean scale ~0.905 from prior findings). V1's
risk-on exposure (85.22%) is IDENTICAL to EW-scale-to-cash's (~85.1% = all-month
62.73% / risk-on fraction 160/217). So there is essentially no cash drag for
diversification to recover, and V1 buys NO exposure advantage. V2 holds slightly
MORE risk-on exposure (81.7%, full-invested at the vol cap) and realizes ~target
vol (10.30%) -- but at a catastrophic return cost.

(b) NO -- retained CAGR is WORSE, not better. V1 sleeve CAGR 9.60% vs EWcash
11.54% (blend 14.86% vs 16.00%); V1 Calmar/Martin collapse (sleeve 0.762/2.536
vs 1.114/4.259; blend 1.391/5.615 vs 1.768/6.921). V1 blend Sharpe only TIES
EWcash (1.505 vs 1.519) and only because vol fell to 9.52% -- it is strictly
worse on Calmar, Martin, MaxDD, CAGR. V2 is dominated on every metric. Min-var
weighting sheds momentum return; the tilt cannot recover it.

(c) YES, the fragility flags fire. Turnover SPIKES: V1 sleeve 0.661 vs EWcash
0.594 (+11%), V2 0.819 (+39%). Walk-forward DEGRADES: V1 < EWcash in all three
segments on both Sharpe and Martin; V2 far worse. The tiny 3-4 asset pick set is
NOT stable enough to neutralize covariance estimation error -- this is exactly
the inverse-vol/EW fragility that got EW chosen in commit 24c1207, reappearing in
covariance WEIGHTING despite the small pick set.

(d) V1 (min-var) clearly beats V2 (target-vol tilt), but both lose to
EW-scale-to-cash. Min-var hurts returns MODERATELY by ignoring momentum (it tilts
to low-vol, lower-return assets), yet is reasonably stable. The score tilt (V2)
hurts CATASTROPHICALLY: maximizing score-weighted exposure under a covariance vol
cap concentrates into volatile high-score picks and churns hard (turnover 0.82),
producing the worst Sharpe (0.731 sleeve / 1.256 blend). Momentum-tilting under a
covariance cap is the worst of both worlds here.

(e) RECOMMENDATION: EW-scale-to-cash VT10 STAYS the pick. Covariance re-weighting
is NOT worth the added complexity or fragility: it provides NO equity-exposure
benefit (EW-scale-to-cash already holds ~85% risk-on; negligible cash drag to
recover), LOWER CAGR and worse Calmar/Martin/MaxDD, HIGHER turnover, and uniformly
worse walk-forward. Reject both V1 and V2. The simple EW uniform scale-to-cash
remains the superior de-risk mechanism for this strategy.

## Why the hypothesis failed (mechanism)

The hypothesis assumed scale-to-cash leaves substantial cash drag that
diversification could re-deploy. At a 10% target on a strategy whose full-period
vol is ~10.3%, scale-to-cash barely binds (mean scale ~0.90), so risk-on books
stay ~85% invested -- there is no meaningful cash to recover. Meanwhile min-var
re-weighting trades the prod EW (which keeps momentum-balanced exposure) for a
low-vol concentration that discards exactly the momentum the selection earned, so
it loses return without any offsetting exposure gain. The covariance lever only
matters when cash drag is large (a much LOWER target), and even then it imports
estimation-error turnover/OOS fragility.

## Caveats / confidence

- POINT ESTIMATES + per-crisis + 3-seg walk-forward only; no bootstrap (per
  scope). Not needed here -- the result is a clear rejection, not a marginal edge:
  V1/V2 lose to EW-scale-to-cash on the headline metrics AND in every walk-forward
  segment, so confidence in the NEGATIVE conclusion is HIGH.
- Only the 10% target was tested (primary, a-priori). A much lower target (where
  scale-to-cash WOULD leave large cash drag) was not tested; covariance re-weight
  could in principle help there, but would carry the same turnover/OOS fragility
  shown here. Out of scope and not recommended given the fragility evidence.
- PIT integrity maintained: Sigma and rv both lagged to sig_d, trailing 252d.
- Long-only weights throughout; V1/V2 never lever (f<=1, sum w<=1).
- min-var and tilt solved via SLSQP (scipy 1.17.1); 1-asset months handled as
  trivial w=[1]; insufficient-history months fall back to EW (rare, cold start).
- Cached-data caveat: yfinance OHLC/panel from local cache; last bar 2026-05-22.
- Selection is byte-for-byte prod (anchor verified); only weighting differs, so
  the comparison isolates the weighting mechanism cleanly.

## Knowledge candidate

Covariance re-weighting CPM picks to a 10% vol target (V1 min-var + residual
cash; V2 momentum-tilt under a covariance vol cap) does NOT retain more
equity/CAGR at matched vol and does NOT improve risk-adjusted metrics. At a 10%
target EW-scale-to-cash already holds ~85% risk-on exposure (negligible cash drag
to recover), so diversification buys no exposure; min-var discards momentum
return (V1 Sharpe/Martin down, CAGR down) and the tilt churns catastrophically
(V2 turnover +39%, Sharpe 0.73 sleeve). Turnover spikes and walk-forward degrades
in all 3 segments -- the same estimation-error fragility that rejected inverse-vol
for EW (commit 24c1207), even on the tiny 3-4 asset set. EW uniform scale-to-cash
VT10 stays the pick.
