# Convex (KMLM managed-futures) defensive-leg study

Question: Does adding a managed-futures / trend sleeve (KMLM) to the DEFENSIVE
allocation improve the strategy by making the safe leg convex (profits in crashes
= crisis alpha), reducing blend drawdown AND adding crisis return, vs the current
SHV/IEF-only defense?

Primary evaluation surface: LIVE 3-sleeve 60/20/20 blend (CPM/BULL/NDX). Also
reported: 60/40 two-sleeve (CPM/BULL) and BULL/CPM standalone.

Status: COMPLETE. D0 reproduces both live baselines exactly.

Method: `research/bull_kmlm_convex_safe.py` (measurement only; no production file
edited). Monkeypatches the shared safe selection (`cpm_live.best_safe`,
`bull_qqq_live._pick_safe`, `ndx_sleeve_live._pick_safe`) and `SAFE_POOL` per
variant; everything else (gates, ranker, pair engine, blend weights, costs)
held fixed. Stays monthly. Run:
`PYTHONPATH=. .venv/bin/python research/bull_kmlm_convex_safe.py`

Windows: CLEAN 2008-05-30..2026-05-22, STRESS 1999-03-10..2026-05-22.
Costs 10bps/side. Crisis slices: calendar 2008, 2020, 2022.

## Variants

- D0 (PROD): best_safe = argmax 13612U over {SHV, IEF}.
- D1: best_safe = argmax 13612U over {SHV, IEF, KMLM} (KMLM competes via momentum, winner takes 100% of safe leg).
- D2: defensive safe leg = 50% best_safe(SHV/IEF) + 50% KMLM (fixed convex slice, monthly reset).
- D3: defensive safe leg = 100% KMLM.
- D4: D2-style 50/50 convex slice applied ONLY to BULL safe; CPM keeps SHV/IEF. NDX inherits BULL's safe selector, so NDX defensive also becomes convex.

## D0 reproduction (verify gate -- PASS)

| Metric | Target | Reproduced |
|---|---|---|
| 3-sleeve 60/20/20 Sharpe | 1.503 | 1.503 |
| 3-sleeve CAGR | 17.93% | 17.93% |
| 3-sleeve MaxDD | -11.62% | -11.62% |
| 60/40 CPM/BULL Sharpe | 1.347 | 1.347 |
| 60/40 CAGR | 13.59% | 13.59% |
| 60/40 MaxDD | -9.82% | -9.82% |

## 1. Full-window metrics -- LIVE 3-sleeve blend

CLEAN 2008-05-30..2026-05-22:

| Variant | Sharpe | ExSharpe | CAGR | Vol | MaxDD | Calmar | Turnover |
|---|---|---|---|---|---|---|---|
| D0 | 1.503 | -- | 17.93% | 11.43% | -11.62% | 1.54 | 374% |
| D1 | 1.400 | -- | 19.33% | 13.27% | -24.54% | 0.79 | 395% |
| D2 | 1.488 | -- | 18.80% | 12.09% | -18.52% | 1.02 | 356% |
| D3 | 1.307 | -- | 19.39% | 14.35% | -29.76% | 0.65 | 356% |
| D4 | 1.499 | -- | 18.00% | 11.50% | -12.16% | 1.48 | 362% |

STRESS 1999-03-10..2026-05-22:

| Variant | Sharpe | CAGR | Vol | MaxDD | Calmar |
|---|---|---|---|---|---|
| D0 | 1.397 | 15.54% | 10.75% | -12.69% | 1.22 |
| D1 | 1.300 | 16.42% | 12.28% | -24.54% | 0.67 |
| D2 | 1.410 | 16.50% | 11.28% | -18.52% | 0.89 |
| D3 | 1.264 | 17.21% | 13.24% | -29.76% | 0.58 |
| D4 | 1.418 | 15.92% | 10.83% | -12.69% | 1.25 |

(ExSharpe vs SHV cash collected in the JSON dump; raw Sharpe is the headline.)

## 1b. 60/40 two-sleeve (CPM/BULL) -- CLEAN

| Variant | Sharpe | CAGR | MaxDD |
|---|---|---|---|
| D0 | 1.347 | 13.59% | -9.82% |
| D1 | 1.229 | 14.93% | -23.90% |
| D2 | 1.327 | 14.43% | -17.83% |
| D3 | 1.131 | 14.99% | -29.16% |
| D4 | 1.342 | 13.65% | -12.00% |

## 1c. Standalone sleeves (CLEAN)

| Variant | CPM Sharpe | CPM CAGR | CPM MaxDD | BULL Sharpe | BULL CAGR | BULL MaxDD |
|---|---|---|---|---|---|---|
| D0 | 1.263 | 14.58% | -15.41% | 1.099 | 11.77% | -12.02% |
| D1 | 1.232 | 16.35% | -24.68% | 0.943 | 12.40% | -23.66% |
| D2 | 1.298 | 15.93% | -17.65% | 1.024 | 11.83% | -19.04% |
| D3 | 1.193 | 17.06% | -29.01% | 0.791 | 11.42% | -30.21% |
| D4 | 1.263 | 14.58% | -15.41% | 1.024 | 11.83% | -19.04% |

D4 leaves CPM standalone identical to D0 (clean isolation of the BULL/NDX-only
change). Notable: the fixed 50/50 slice (D2) is the only form that RAISES CPM
standalone Sharpe (1.263 -> 1.298 clean, 1.218 -> 1.246 stress), but it still
deepens CPM standalone MaxDD (-15.41% -> -17.65%).

## 2. Crisis-alpha check

Blend total return / intra-year MaxDD by variant (CLEAN):

| Episode | D0 TR / DD | D1 | D2 | D3 | D4 |
|---|---|---|---|---|---|
| 2008 | +6.11% / -9.33% | +7.15% / -12.73% | +17.21% / -11.40% | +27.55% / -13.94% | +8.92% / -12.00% |
| 2020 | +42.53% / -9.82% | +43.83% / -9.82% | +45.25% / -8.93% | +47.92% / -8.03% | +45.25% / -8.93% |
| 2022 | +4.95% / -5.84% | +18.84% / -17.56% | +12.31% / -8.73% | +18.84% / -17.56% | +9.76% / -7.04% |

KMLM (stitched proxy) raw calendar-year return: 2008 +40.40% (PROXY), 2020 +4.39%
(live ETF), 2022 +24.24% (live ETF).

Findings:
- Crisis RETURN is added by every KMLM variant in every episode. Strongest for
  D3 / D1 (full or momentum-concentrated KMLM). 2008 +6.1% -> D3 +27.6%, 2022
  +5.0% -> D1/D3 +18.8%.
- Crisis DRAWDOWN is reduced only in 2020 (D2 -8.93%, D3 -8.03% vs D0 -9.82%).
  In 2008 and 2022 the convex variants INCREASE intra-crisis DD, because KMLM's
  own trend whipsaws (and, for D1/D3, 100% concentration in a single volatile
  safe asset) add drawdown before the crisis trend pays off (2022 D1/D3 -17.56%
  vs D0 -5.84%).

## 3. Cost check -- calm-period drag

Monthly (variant - D0) blend delta, split crisis-months vs calm-months (CLEAN):

| Variant | Crisis cum delta | Calm cum delta | Net | Sharpe vs D0 | MaxDD vs D0 |
|---|---|---|---|---|---|
| D1 | +17.27% | +7.60% | +24.9% | -0.103 | +12.9pp worse |
| D2 | +20.03% | -5.21% | +14.8% | -0.015 | +6.9pp worse |
| D3 | +39.85% | -11.37% | +28.5% | -0.196 | +18.1pp worse |
| D4 | +9.45% | -7.99% | +1.5% | -0.004 | +0.5pp worse |

- Holding KMLM in calm defensive periods DOES drag (negative calm delta) for
  D2/D3/D4 -- managed futures bleeds/whipsaws when there is no sustained trend.
- D1 shows a POSITIVE calm delta only because momentum gating keeps it out of
  KMLM most calm months; but the months it does hold 100% KMLM it whipsaws hard,
  producing the worst full-window MaxDD (-24.54%).
- D4 calm drag (-7.99%) roughly cancels its crisis gain (+9.45%): near net-zero.

## 4. Verdict

PRIMARY GOAL (reduce blend MaxDD): NOT SUPPORTED. Every KMLM form INCREASES
full-window blend MaxDD (D0 -11.62% -> D1 -24.54%, D2 -18.52%, D3 -29.76%,
D4 -12.16%). Root cause: the existing SHV/IEF defense is already a loss-AVOIDANCE
mechanism. The canary + trend gates move the portfolio to cash/bonds BEFORE the
deep crash, so by the time the blend is defensive there is little drawdown left
for a convex asset to offset. Swapping a no-loss asset (SHV/IEF) for a volatile
trend asset (KMLM) therefore IMPORTS KMLM's own drawdowns into the blend's
worst-case rather than cancelling crash losses. The crisis profits are real but
arrive as upside, not as DD reduction.

SECONDARY GOAL (add crisis return at acceptable cost):
- D3 (pure KMLM) and D1 (momentum-competed) add the most crisis return but cost
  0.20 / 0.10 Sharpe and roughly double-to-triple the blend MaxDD. REJECT.
- D2 (full 50/50 slice) adds strong crisis return (+20pp crisis cum) at small
  Sharpe cost (1.503 -> 1.488 clean; actually +0.013 BETTER on stress) but
  +6.9pp deeper MaxDD. Acceptable only if crisis upside is prioritized over DD.
- D4 (BULL/NDX-only 50/50 slice) is the only Sharpe-neutral form: 1.499 vs
  1.503 (clean), 1.418 vs 1.397 (stress, a small IMPROVEMENT), MaxDD flat on
  stress (-12.69%) and only +0.5pp worse on clean. It adds a modest, mostly
  real-ETF crisis kicker (2022 +4.8pp, 2020 +2.7pp) with near-zero net cost.

RECOMMENDATION: Do NOT add KMLM to the shared defense as a drawdown-reduction
tool -- it fails that test in every form. If a crisis-return convexity kicker is
desired with minimal harm, D4 (apply a fixed 50/50 KMLM slice only to the BULL
and NDX safe legs, CPM unchanged) is the only acceptable form: Sharpe-neutral to
slightly positive, DD essentially unchanged, small genuine crisis uplift. Even
D4 does not reduce blend MaxDD, so the net case for adopting it is marginal and
optional, not a clear improvement. The current SHV/IEF-only defense remains the
best risk-adjusted choice.

## Data-quality caveat (KMLM proxy / stitch)

KMLM history is a STITCHED managed-futures proxy:
- 1988/1993-2020: synthetic from the KFA-MLM index MONTHLY total returns,
  interpolated piecewise-constant to daily (`research/archive/stitch_kmlm.py`).
  This UNDERSTATES daily vol and intramonth drawdown pre-2020, so the true DD of
  pre-2020 KMLM variants (the 2008 crisis and the pre-2008 portion of the stress
  window) is likely WORSE than reported here. The 2008 +40.4% crisis alpha is
  proxy-derived, not live ETF.
- 2020+: live KMLM ETF (genuine). Hence the 2020 (+4.4%) and 2022 (+24.2%)
  crisis-alpha results are real-ETF and trustworthy -- and even there the convex
  leg adds return while INCREASING full-window blend MaxDD.
- Stitched series ends 2026-05-11; ffilled to the 2026-05-22 window end.

Minor methodology note: the D2/D4 synthetic safe column rebalances the 50/50
slice monthly with within-month drift left unmodeled (daily-vs-monthly rebalance
difference is sub-1bp for these low-vol legs). Blend turnover is computed from
monthly blended sleeve target weights (annualized one-way).

Artifacts:
- Script: `research/bull_kmlm_convex_safe.py`
- Raw metrics dump: `research/bull_kmlm_convex_safe_results.json`
