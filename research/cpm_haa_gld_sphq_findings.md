# HAA + GLD + SPHQ ("gold + quality") vs plain HAA: full metrics + bootstrap

Analyst, 2026-06-02. Research only; no prod/memo/docs edits; no commit.

## Question

The CPM universe edge (HAA-8 -> CPM-8, +0.1519 clean Sharpe under the HAA
mechanism) was attributed to single-asset swaps. The top-2 drivers were
IEF->GLD (+0.0730) and IWM->SPHQ (+0.0508), sum-of-singles +0.1238. This study
tests the COMBINED two-asset swap as a candidate universe upgrade:

(a) Full metrics: HAA+GLD+SPHQ vs HAA baseline across all risk-adjusted
    measures (clean + ext). Broad improvement, or narrow?
(b) Bootstrap: is dSharpe (and dSortino/dCVaR/dCalmar/dMartin) significant
    (95% CI excludes zero), or within-noise?
(c) Net: is "HAA + gold + quality" a statistically robust universe upgrade, or
    a within-noise point-estimate?

## Method

HAA mechanism held FIXED at config R0 M0 (13612U dual momentum, TIP-only canary,
top-4, equal-weight, best-of {SHV,IEF} safe; NO vol-adj ranker, NO min-var).
Only the universe varies (2 assets swapped). `uni_wf` reused byte-identical
from `research/cpm_haa_asset_swap_2026_06_02.py` (gate-verified vs the factorial
000/100 cells). Bootstrap helper `paired_block_bootstrap_mm` from
`research/cpm_bootstrap_multimetric.py` (B=2000, block=21, seed=42).

- Script: `research/cpm_haa_gld_sphq_run.py`
  (run: `.venv/bin/python research/cpm_haa_gld_sphq_run.py`)
- Output: `research/cpm_haa_gld_sphq_run.json`
- Exec: T+1 MOO (mooex), both-252, 10 bps/side. CLEAN = decision window.
- Windows: CLEAN 2008-05-30..2026-05-22; EXT 1999-03-10..2026-05-22.

Baseline HAA-8 = SPY, IWM, VEA, VWO, VNQ, DBC, IEF, TLT.
Variant       = SPY, SPHQ, VEA, VWO, VNQ, DBC, GLD, TLT  (IEF->GLD & IWM->SPHQ).

## Gate (PASS, exact)

Baseline HAA-8 CLEAN Sharpe = 0.8669910 == anchor 0.8669910 (PASS). Harness and
weight fn exactly match the verified factorial 000 cell.

## (a) Full metrics: baseline vs HAA+GLD+SPHQ

CLEAN (2008-05-30..2026-05-22):

| Metric        | HAA-8 baseline | HAA+GLD+SPHQ | delta    |
|---------------|----------------|--------------|----------|
| Sharpe        | 0.8670         | 1.0282       | +0.1613  |
| Sortino       | 1.2296         | 1.4692       | +0.2396  |
| CVaR(95) ratio| 5.5254         | 6.6112       | +1.0858  |
| Calmar        | 0.6386         | 0.8522       | +0.2136  |
| Martin        | 2.2156         | 2.9423       | +0.7267  |
| MaxDD         | -14.68%        | -13.13%      | +1.55 pp |
| CAGR          | 9.37%          | 11.19%       | +1.82 pp |
| Ann. vol      | 11.08%         | 10.94%       | -0.14 pp |
| Turnover (ann)| 680.6%         | 661.1%       | -19.5 pp |

EXT (1999-03-10..2026-05-22):

| Metric        | HAA-8 baseline | HAA+GLD+SPHQ | delta    |
|---------------|----------------|--------------|----------|
| Sharpe        | 1.0307         | 1.1574       | +0.1266  |
| Sortino       | 1.4716         | 1.6610       | +0.1894  |
| CVaR(95) ratio| 6.6243         | 7.4816       | +0.8573  |
| Calmar        | 0.7527         | 0.9482       | +0.1955  |
| Martin        | 2.8608         | 3.6607       | +0.7999  |
| MaxDD         | -14.68%        | -13.17%      | +1.51 pp |
| CAGR          | 11.05%         | 12.49%       | +1.44 pp |
| Ann. vol      | 10.73%         | 10.66%       | -0.07 pp |
| Turnover (ann)| 598.2%         | 596.3%       | -1.9 pp  |

The improvement is BROAD, not narrow: every risk-adjusted measure improves
(Sharpe, Sortino, CVaR, Calmar, Martin), tail risk improves (MaxDD -14.68% ->
-13.13% clean), CAGR rises ~1.8 pp, vol is flat-to-lower, and turnover is
slightly lower. No metric trades off against another. Same sign in CLEAN and
EXT, which adds robustness.

Supra-additivity note: the combined CLEAN dSharpe is +0.1613, MORE than the
sum-of-singles +0.1238 (IEF->GLD +0.0730 + IWM->SPHQ +0.0508). Positive
interaction ~ +0.0375. The combined lift is NOT the ~+0.124 / Sharpe ~0.99 the
brief expected; it is +0.161 / Sharpe 1.028. Gold + quality together are
complementary (gold defensive, quality offensive), so the pair beats the linear
sum -- but see the selection-bias caveat below.

## (b) Bootstrap (paired block B=2000 block=21 seed=42, variant MINUS baseline)

CLEAN (decision window):

| Delta    | mean    | 95% CI               | p(var>base) | excl 0? |
|----------|---------|----------------------|-------------|---------|
| dSharpe  | +0.1617 | [+0.0004, +0.3220]   | 0.975       | YES (bare)|
| dSortino | +0.2402 | [-0.0060, +0.4764]   | 0.971       | no (bare) |
| dCVaR    | +1.0886 | [-0.0014, +2.1542]   | 0.974       | no (bare) |
| dCalmar* | +0.1556 | [-0.0725, +0.4307]   | 0.916       | no        |
| dMartin* | +0.7319 | [-0.1217, +1.8341]   | 0.954       | no        |

EXT (robustness context):

| Delta    | mean    | 95% CI               | p(var>base) | excl 0? |
|----------|---------|----------------------|-------------|---------|
| dSharpe  | +0.1267 | [+0.0094, +0.2516]   | 0.984       | YES     |
| dSortino | +0.1894 | [+0.0075, +0.3809]   | 0.981       | YES     |
| dCVaR    | +0.8569 | [+0.0358, +1.7207]   | 0.980       | YES     |
| dCalmar* | +0.1193 | [-0.0861, +0.3584]   | 0.884       | no      |
| dMartin* | +0.6308 | [-0.1007, +1.5745]   | 0.952       | no      |

*dCalmar / dMartin are PATH-DEPENDENT; block resampling shuffles the drawdown
path so their CIs are soft and must NOT be used to classify significance. They
are point-estimate context only. The classification metrics are
dSharpe / dSortino / dCVaR (order-invariant, clean CIs).

Reading:
- CLEAN is BORDERLINE. dSharpe just clears zero (CI lo = +0.0004, p = 0.975);
  dSortino (lo -0.006) and dCVaR (lo -0.0014) just MISS, sitting right on the
  zero boundary. All three classification metrics cluster at the edge -> the
  CLEAN evidence is marginal, not clean.
- EXT is robustly SIGNIFICANT. All three classification metrics (dSharpe,
  dSortino, dCVaR) clear zero with p ~ 0.98. The longer window tightens the CIs
  and pulls them off the boundary.

## (c) Verdict

Net: HAA + gold + quality is a MARGINALLY-to-MODERATELY robust universe upgrade,
not a clean slam-dunk and not pure noise.

- The point estimate is broad and consistent (every metric up, both windows),
  and supra-additive (+0.161 clean, beyond the +0.124 sum of singles).
- The CLEAN (decision-window) bootstrap is BORDERLINE: dSharpe barely clears
  zero, dSortino and dCVaR sit on the boundary. The 18-year clean sample is not
  long enough to put clear daylight between the variant and baseline.
- The EXT (27-year) bootstrap is clearly significant on all classification
  metrics. So the edge IS real over the long sample, but the clean-window CI is
  too tight-to-zero to call it decisively significant on its own.

Compared to the full HAA-8 -> CPM-8 universe swap (+0.22, CI [+0.029, +0.402],
clearly significant), this two-asset subset is the BORDERLINE case the brief
anticipated: it captures most of the universe edge (gold + quality = ~81% of the
full gap in the prior attribution) but with a clean-window CI that only just
clears (Sharpe) or just misses (Sortino/CVaR) zero.

## Caveats / confidence

- SELECTION BIAS (the headline caveat). GLD and SPHQ were chosen because they
  were the top-2 single-asset drivers in a PRIOR in-sample attribution on this
  same data. Picking the best 2 of 5 candidates and then re-testing them on the
  same sample inflates the in-sample combined lift. The honest test is the
  bootstrap, and the bootstrap is only borderline on the CLEAN window -- exactly
  the pattern you expect when a selected-best subset is re-confirmed on its own
  data. Treat the CLEAN +0.161 as an optimistic upper bound; the true
  out-of-sample lift is likely smaller. The EXT-window significance is more
  trustworthy because the selection used metrics dominated by the CLEAN window.
- Path-dependent metrics (Calmar, Martin) bootstrap with soft CIs and are NOT
  used to classify; point estimates only.
- PIT/cached-data caveat: cached `load_panel` + cached open/close for MOO exec
  lag; same data basis as the verified anchors, internally consistent.
- Single in-sample window; no walk-forward / out-of-sample holdout. No
  multiple-testing correction beyond reporting all metrics.
- Conditional on the HAA mechanism (R0 M0). Under the full CPM mechanism
  (vol-adj ranker + min-var) the marginals would differ.

## Handoff

None required. A genuine out-of-sample confirmation (walk-forward, or holding
out the window not used for selection) would be the next step to defeat the
selection-bias concern; that is a follow-up analyst run.
