# CPM Risky-Block Allocation: Downside-Risk Objectives (CVaR / CDaR) vs Variance / Naive + GMV Reference

Date: 2026-06-02
Author: analyst (research-only; no prod/memo/cpm_live edits; no commit)

## Question

Does a downside-risk allocation objective for the CPM risky block -- Min-CVaR or
Min-CDaR, which (unlike variance) do NOT penalize upside -- beat variance / naive
weighting net of turnover cost and out-of-sample (OOS), or does it wash out at 4
assets (DeMiguel 1/N; our prior 2x2 nulls)?

Sub-questions:
- (b) GMV ("global min-variance weights", the "min-var weights" the user asked
  why we do not use): do they help, or are they unstable (high turnover,
  concentrated max-weight, no OOS edge)?
- (c) Per-crisis: does the drawdown objective (CDaR) actually cut crisis
  drawdowns more than inv-vol?

## Method

- Engine / anchor: `research/cpm_harness.py` (`run_strategy`, `verify_anchor`).
  Anchor verified FIRST through the harness: Sharpe 1.262209, MaxDD -0.113463,
  Calmar 1.219599 (prod min-var anchor 1.2622 / -11.35% / 1.2196). PASS.
- Design: hold the entire pipeline FIXED (universe / canary / rank / safe /
  partial-safe / both-252 / mooex T+1 / 10 bps) and vary ONLY the within-risky-
  block allocation. Risky block = top-4 POSITIVE momentum picks, so the
  allocation objective is the sole varying factor. Partial-safe scaling
  (`risky_fraction = min(n_pos,4)/4`) identical across all configs.
  Selection replicated from `cpm_live.compute_target_weights` lines 425-465.
- PROD config keeps the production logic exactly (min-var-subset(3)+inv-vol in
  the n_pos=4 case) and reproduces the anchor as a control. All other configs
  apply their objective to the full top-4 block.
- Optimizers (no cvxpy/riskfolio in venv -> implemented directly):
  - GMV: long-only min-variance QP `min w'Sigma w, w>=0, sum w=1` via
    `scipy.optimize.minimize` (SLSQP); 252d sample covariance.
  - MIN-CVaR: Rockafellar-Uryasev LP, beta=0.95, loss = -portfolio return, via
    `scipy.optimize.linprog` (HiGHS).
  - MIN-CDaR: Chekhlov-Uryasev drawdown LP, beta=0.95, on the uncompounded
    cumulative path, via `linprog` (HiGHS). Path-dependent objective.
  - HRP: Lopez de Prado (corr->dist, single-linkage, quasi-diag, recursive
    bisection inverse-variance) via `scipy.cluster.hierarchy`.
  - Each falls back to inv-vol if covariance is degenerate / solver fails.
- All optimizers use the SAME 252d trailing window as `cpm_live.inv_vol_weights`
  (`close[picks].ffill().pct_change().dropna(how='all').tail(252)`).
- Metrics: Sharpe + Sortino + CVaR-ratio (path-independent) + Calmar / Martin /
  MaxDD / CAGR / vol; annualized one-way risky-block turnover (net 10 bps);
  per-crisis (GFC/COVID/2022/2025); concentration (risky-block max weight).
- Significance: paired block bootstrap (`research/cpm_bootstrap_multimetric.py`,
  B=2000, block=21, seed=42) of the key contrasts vs INV-VOL on the
  path-independent metrics dSharpe / dSortino / dCVaR. 3-segment walk-forward.

Inputs: `cpm_live.load_panel` + open/close cache via harness. Both-252.
Script: `research/cpm_cvar_cdar_objective.py`. Output JSON:
`research/cpm_cvar_cdar_objective.json`.

## Results

### Config table -- CLEAN (DECISION window, 2008-05-30..)

| config   | Sharpe | Sortino | CVaR | Calmar | Martin | MaxDD   | CAGR   | vol    | TO/yr | mxW(4) |
|----------|--------|---------|------|--------|--------|---------|--------|--------|-------|--------|
| PROD     | 1.2622 | 1.8036  | 8.39 | 1.2196 | 3.952  | -0.1135 | 0.1384 | 0.1076 | 2.36  | n/a    |
| EW       | 1.1317 | 1.6152  | 7.41 | 1.0147 | 3.741  | -0.1305 | 0.1324 | 0.1163 | 1.90  | 0.25   |
| INV-VOL  | 1.1658 | 1.6629  | 7.65 | 1.0137 | 3.691  | -0.1297 | 0.1315 | 0.1118 | 2.04  | 0.44   |
| GMV      | 1.2570 | 1.7846  | 8.32 | 1.0623 | 3.436  | -0.1270 | 0.1349 | 0.1055 | 2.66  | 1.00   |
| MIN-CVaR | 1.1896 | 1.6858  | 7.83 | 0.9121 | 2.836  | -0.1399 | 0.1276 | 0.1061 | 2.81  | 1.00   |
| MIN-CDaR | 1.1754 | 1.6595  | 7.63 | 1.0998 | 3.360  | -0.1213 | 0.1334 | 0.1123 | 3.16  | 1.00   |
| HRP      | 1.1975 | 1.7020  | 7.86 | 1.0454 | 3.557  | -0.1269 | 0.1326 | 0.1095 | 2.39  | 0.74   |

`mxW(4)` = max risky-block weight on 4-asset blocks. PROD never has a 4-asset
block (it always trims to a 3-of-4 min-var subset), so n/a.

### Config table -- EXT (1999-03-10..)

| config   | Sharpe | Sortino | CVaR | MaxDD   | CAGR   |
|----------|--------|---------|------|---------|--------|
| PROD     | 1.2624 | 1.8093  | 8.45 | -0.1492 | 0.1363 |
| EW       | 1.1868 | 1.7021  | 7.88 | -0.1621 | 0.1413 |
| INV-VOL  | 1.2004 | 1.7161  | 7.94 | -0.1573 | 0.1348 |
| GMV      | 1.1992 | 1.7041  | 7.97 | -0.1444 | 0.1259 |
| MIN-CVaR | 1.1544 | 1.6398  | 7.66 | -0.1399 | 0.1213 |
| MIN-CDaR | 1.1816 | 1.6793  | 7.80 | -0.1375 | 0.1329 |
| HRP      | 1.1631 | 1.6536  | 7.66 | -0.1544 | 0.1267 |

### GMV instability demo (concentration + turnover) -- the "min-var weights" answer

| config   | eq4_avg maxW | eq4_max maxW | ge2_avg | ge2_max | TO/yr |
|----------|--------------|--------------|---------|---------|-------|
| EW       | 0.250        | 0.250        | 0.269   | 0.500   | 1.90  |
| INV-VOL  | 0.319        | 0.441        | 0.340   | 0.657   | 2.04  |
| HRP      | 0.413        | 0.739        | 0.432   | 0.739   | 2.39  |
| GMV      | 0.583        | 1.000        | 0.588   | 1.000   | 2.66  |
| MIN-CVaR | 0.596        | 1.000        | 0.599   | 1.000   | 2.81  |
| MIN-CDaR | 0.618        | 1.000        | 0.619   | 1.000   | 3.16  |

GMV / Min-CVaR / Min-CDaR all pile up to a 100% single-asset corner on 4-asset
blocks (average top weight ~0.58-0.62), versus 0.25 (EW) / 0.32-0.44 (inv-vol) /
0.41-0.74 (HRP). They also churn 30-55% more turnover than inv-vol. This is the
textbook error-maximization signature: the optimizer treats noisy 252d sample
covariance / tail estimates as signal, concentrates into one estimated "best"
asset, and the position flips as estimates drift -> high turnover. This is the
empirical reason raw min-var (GMV) weights are NOT used at the block level.

### Per-crisis MaxDD (ext series)

| config   | GFC     | COVID   | 2022    | 2025    |
|----------|---------|---------|---------|---------|
| PROD     | -0.1033 | -0.1011 | -0.0619 | -0.1135 |
| EW       | -0.1573 | -0.1121 | -0.0744 | -0.1275 |
| INV-VOL  | -0.1188 | -0.1050 | -0.0796 | -0.1297 |
| GMV      | -0.1052 | -0.1050 | -0.0722 | -0.1270 |
| MIN-CVaR | -0.1069 | -0.1175 | -0.0791 | -0.1062 |
| MIN-CDaR | -0.1152 | -0.1194 | -0.0664 | -0.0936 |
| HRP      | -0.0912 | -0.1014 | -0.0799 | -0.1269 |

Per-crisis Sortino / CVaR-ratio (ext): MIN-CDaR best in 2022 (Sortino -0.22,
least-negative) and 2025 (2.07 / 9.92, best of all configs incl PROD) but WORST
in COVID (Sortino 0.08, CVaR 0.37 vs inv-vol -0.14 / -0.65 -- mixed). The drawdown
objective helped the slow-grind drawdowns (2022, 2025) but not the fast COVID
crash, because the trailing-window path it optimizes did not contain a comparable
shock. PROD (min-var subset) is the most consistent across crises.

### Bootstrap vs INV-VOL (clean; paired block, B=2000, block=21, seed=42)

| contrast            | dSharpe mean [95% CI] p>0          | dSortino mean [95% CI] p>0         | dCVaR mean [95% CI] p>0            |
|---------------------|------------------------------------|------------------------------------|------------------------------------|
| MIN-CVaR vs INV-VOL | +0.026 [-0.166,+0.221] 0.60        | +0.027 [-0.274,+0.329] 0.57        | +0.198 [-1.197,+1.591] 0.61        |
| MIN-CDaR vs INV-VOL | +0.012 [-0.200,+0.224] 0.55        | -0.001 [-0.325,+0.325] 0.50        | -0.009 [-1.503,+1.499] 0.50        |
| GMV vs INV-VOL      | +0.093 [-0.088,+0.281] 0.85        | +0.125 [-0.147,+0.421] 0.82        | +0.679 [-0.583,+2.038] 0.85        |

Every CI straddles 0 on every path-independent metric. None significant.
MIN-CDaR is dead-on zero. GMV has the strongest point estimates (p>0 ~0.82-0.85)
but still NOT significant -- and that in-sample tilt does not survive OOS (see ext
table: GMV 1.1992 vs INV-VOL 1.2004) or turnover/concentration.

### 3-segment walk-forward (clean)

| config   | 2008-2014 Sharpe | 2014-2020 | 2020-2026 |
|----------|------------------|-----------|-----------|
| PROD     | 1.104            | 1.168     | 1.542     |
| GMV      | 1.181            | 1.018     | 1.540     |
| MIN-CVaR | 1.142            | 0.989     | 1.414     |
| MIN-CDaR | 1.176            | 0.981     | 1.345     |
| HRP      | 1.081            | 1.093     | 1.433     |

GMV / CVaR / CDaR all sag in the middle segment (2014-2020, the low-vol bull where
estimation noise dominates) -- 0.98-1.02 vs PROD 1.17. The downside / GMV edge is
regime-fragile and not a free lunch; PROD (min-var subset) is the most stable
across segments.

## Verdict

(a) No. Downside-risk objectives (Min-CVaR, Min-CDaR) do NOT beat variance /
inv-vol on the path-independent downside metrics (Sortino, CVaR) net of turnover
and OOS at 4 assets. The contrasts WASH OUT: all bootstrap CIs straddle 0
(MIN-CDaR exactly zero; MIN-CVaR p>0 ~0.57-0.61, not significant), they churn
30-55% more turnover, and they degrade OOS (ext) and in the 2014-2020 walk-forward
segment. This confirms the DeMiguel 1/N expectation and our prior 2x2 nulls: at 4
assets, estimation error swamps the objective's theoretical advantage.

(b) GMV (the raw "min-var weights") are unstable. In-sample they LOOK strong
(clean Sharpe 1.2570, near PROD's 1.2622, best non-PROD point estimate vs inv-vol)
but this is error-maximization: 100% single-asset corner solutions (avg top
weight 0.58 vs inv-vol 0.34), +30% turnover, no significance (CI crosses 0), no
OOS edge (ext 1.1992 == INV-VOL 1.2004), and a mid-sample walk-forward sag (1.02).
This is the concrete demonstration of why raw min-var weights are not used.

(c) Mixed. MIN-CDaR cut the slow-grind drawdowns (2022 -6.6%, 2025 -9.4%, both
better than inv-vol's -8.0% / -13.0%) but was WORSE in COVID (-11.9% vs -10.5%).
The drawdown objective does not reliably cut crisis drawdowns more than inv-vol;
it only helps when the trailing window resembles the coming drawdown.

Structural note (the real lever): PROD's edge over inv-vol (1.2622 vs 1.1658,
+0.10 Sharpe) comes almost entirely from the min-var SUBSET (drop the worst 1 of 4
assets, cardinality reduction), NOT from any within-block weighting objective. The
spread across ALL allocation objectives on the full 4 (EW 1.13 .. GMV 1.26) is
dominated by that single selection choice. Reweighting 4 noisy assets is a wash;
dropping one is where the signal is. Recommendation: keep PROD (min-var-subset(3)
+ inv-vol). Do not adopt CVaR / CDaR / GMV block weighting.

## Caveats and confidence

- 4-asset block -> estimation error dominates; all conclusions are consistent with
  DeMiguel and our priors. High confidence on the wash-out / GMV-instability calls.
- Single in-sample backtest; bootstrap + 3-seg walk-forward are the only OOS
  proxies. Per-crisis stats are few-observation and path-dependent (context only,
  not used for significance).
- CDaR/CVaR LPs and GMV QP fall back to inv-vol on degenerate covariance; the
  optimizers solved cleanly in the vast majority of 4-asset months (n_eq4=251).
- HRP included as SOTA-robust reference: clean Sharpe 1.1975, also below PROD,
  also wash vs inv-vol -- consistent with the 4-asset estimation-error story.
- Turnover is risky-block one-way annualized; net-of-cost effects already in
  Sharpe via the 10 bps engine costs (extra-churn configs still did not win).

## Reproduce

```
cd /Users/rkautsar/personal/scripts/strategy_cpm
.venv/bin/python research/cpm_cvar_cdar_objective.py
```

Outputs: console tables + `research/cpm_cvar_cdar_objective.json`.
Anchor self-checked at start (asserts 1.2622 within 5e-4).
