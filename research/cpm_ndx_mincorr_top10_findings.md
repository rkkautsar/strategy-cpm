# NDX sleeve: 10->5 min-corr selection and top-10 EW vs prod top-5 EW

Analyst, hypothesis-driven backtest. Research only. Production
(`ndx_sleeve_live.py` / prod / memo) NOT edited; no commit.

## Questions

- (a) Does **MINCORR_10to5** (momentum top-10 -> keep the 5 lowest-avg-pairwise-correlation names, 252d, EW) beat prod top-5 EW? Does corr-only selection at a *moderate* prune preserve momentum AND add diversification (unlike min-var, which significantly hurt)? Or is it a wash/worse?
- (b) Does **TOP10_EW** (hold all 10 momentum names EW) hit a better MaxDD/Sharpe knee than top-6 (mild) or top-15 (-8pp MaxDD but Sharpe cost)? Map the breadth curve top-5/6/10/15.
- (c) **MINCORR_10to5 vs TOP10_EW** -- does selecting 5-of-10 by correlation beat just holding all 10?

## Method

- Engine: monkeypatch `ndx_sleeve_live.compute_ndx_weights`, then call the unmodified `ndx_sleeve_live.run_ndx_backtest`. Gating (TIP canary + SPY trend + SPY vol), safe rotation, T+1 MOO close-to-close, 10 bps/side, delisting haircut, PIT Nasdaq-100 membership are all identical across configs. Only held-names selection / cardinality varies.
- Faithful reuse of the prior NDX harness: `_gate_and_candidates`, `_partial_safe_pack`, `full_metrics`, `crisis_metrics`, `annual_turnover`, `walk_forward`, `win` from `research/cpm_ndx_minvar_cvar.py`; paired block bootstrap `paired_block_bootstrap_mm` (B=2000, block=21, seed=42) from `research/cpm_bootstrap_multimetric.py`.
- Min-corr subset: brute force over C(10,5)=252 combos, keep the subset with the lowest mean upper-triangle pairwise correlation (252d sample corr). Corr-only -- never uses variance, so it cannot prefer low-vol momentum laggards the way min-var does. Falls back to top-5 momentum if the corr matrix is degenerate.
- EW breadth convention: every EW config (incl PROD) uses `_partial_safe_pack(rw, n_eff, safe, K)` -- the direct PROD generalization (1/K per held name; shortfall -> safe). `TOP15_EW_FULLINV` reproduces the prior fully-invested convention; it is **byte-identical** to `TOP15_EW`, confirming the partial-safe cap never binds during gate-ON periods (the breadth curve is convention-independent).
- Windows: clean = DECISION (2008-05-30 .. 2026-05-22), stress = ext (1999-03-10 .. 2026-05-22). Single in-sample; high overfit caution.

Run:

```
.venv/bin/python -m research.cpm_ndx_mincorr_top10
```

Outputs: `research/cpm_ndx_mincorr_top10_findings.json` (+ this md).

## Inputs / data sources

- `cpm_live.load_panel` (macro/gate/safe panel), `ndx_sleeve_live.load_ndx_panel` (PIT NDX prices), `index_constitution` (PIT membership). Same refreshed prices as the prior NDX studies.
- Anchor check: PROD reproduces clean Sharpe **1.281** / MaxDD **-31.4%** (target ~1.281 / -31.4%). Top-6 EW **1.231 / -30.4%** and top-15 EW **1.187 / -22.8%** reproduce the cited reference points exactly.

## Config table -- clean (2008+, DECISION)

| Config | Sharpe | Sortino | CVaR | Calmar | Martin | MaxDD | CAGR | Turnover |
|---|---|---|---|---|---|---|---|---|
| PROD (top-5 EW) | 1.281 | 1.962 | 8.40 | -- | -- | -31.4% | 31.4% | 5.16 |
| MINCORR_10to5 | 1.057 | 1.598 | 6.84 | -- | -- | -32.0% | 21.9% | 5.41 |
| TOP6_EW | 1.231 | 1.856 | 7.98 | -- | -- | -30.4% | 28.2% | 5.04 |
| TOP10_EW | 1.204 | 1.775 | 7.56 | -- | -- | -26.4% | 24.2% | 4.78 |
| TOP15_EW | 1.187 | 1.741 | 7.40 | -- | -- | -22.8% | 21.4% | 4.74 |

(Clean `full_metrics` reports Sharpe/Sortino/CVaR/MaxDD/CAGR; Calmar/Martin shown on the stress window below.)

## Config table -- stress (1999+, confirm)

| Config | Sharpe | Sortino | CVaR | Calmar | Martin | MaxDD | CAGR |
|---|---|---|---|---|---|---|---|
| PROD | 1.131 | 1.721 | 7.39 | 0.730 | 3.520 | -31.4% | 22.9% |
| MINCORR_10to5 | 0.964 | 1.449 | 6.21 | 0.527 | 2.155 | -32.0% | 16.9% |
| TOP6_EW | 1.098 | 1.646 | 7.12 | 0.687 | 3.326 | -30.4% | 20.9% |
| TOP10_EW | 1.100 | 1.617 | 6.99 | 0.707 | 3.377 | -26.4% | 18.7% |
| TOP15_EW | 1.094 | 1.602 | 6.93 | 0.738 | 3.472 | -22.8% | 16.8% |

Stress confirms the clean ranking. MINCORR_10to5 is the only config that materially degrades on every metric (Calmar 0.53 vs prod 0.73, Martin 2.16 vs 3.52).

## Per-crisis (ext) -- Sharpe / MaxDD

| Config | dot-com Sh/DD | GFC Sh/DD | COVID Sh/DD | 2022 Sh/DD | 2025 Sh/DD |
|---|---|---|---|---|---|
| PROD | 0.95 / -12.1% | 0.96 / -9.1% | 2.71 / -4.7% | 2.98 / -0.3% | 0.89 / -4.8% |
| MINCORR_10to5 | 0.95 / -12.1% | 0.97 / -8.9% | 2.71 / -4.7% | 2.98 / -0.3% | 2.48 / -2.9% |
| TOP6_EW | 0.95 / -12.1% | 0.92 / -9.2% | 2.71 / -4.7% | 2.98 / -0.3% | 1.27 / -3.7% |
| TOP10_EW | 0.95 / -12.1% | 0.87 / -9.2% | 2.71 / -4.7% | 2.98 / -0.3% | 1.30 / -2.9% |
| TOP15_EW | 0.95 / -12.1% | 0.95 / -8.7% | 2.71 / -4.7% | 2.98 / -0.3% | 1.36 / -2.9% |

Crisis windows are near-identical across configs because the **gate** (not breadth/selection) drives crisis behavior -- it is OFF for most of dot-com/GFC/COVID, so all configs hold safe and draw down the same. Differences appear only in Y2025 (a recent gate-ON dispersion window) where MINCORR's 2.48 is a single lucky pocket, not robust (its full-sample numbers are worst). Key implication: the breadth MaxDD reduction (top-15 -22.8% vs prod -31.4%) is a **gate-ON / normal-period single-name-dispersion effect**, NOT crisis protection.

## Bootstrap vs PROD (clean; B=2000, block=21, seed=42)

| Config | dSharpe [CI] p>0 | dSortino [CI] p>0 | dCVaR [CI] p>0 |
|---|---|---|---|
| MINCORR_10to5 | -0.220 [-0.43, -0.03] **0.011** | -0.356 [-0.71, -0.02] **0.016** | -1.528 [-3.04, -0.11] **0.017** |
| TOP6_EW | -0.049 [-0.12, 0.03] 0.089 | -0.106 [-0.23, 0.02] 0.052 | -0.424 [-0.95, 0.13] 0.064 |
| TOP10_EW | -0.075 [-0.22, 0.07] 0.147 | -0.184 [-0.44, 0.06] 0.071 | -0.836 [-1.93, 0.23] 0.061 |
| TOP15_EW | -0.093 [-0.27, 0.10] 0.152 | -0.221 [-0.53, 0.10] 0.082 | -0.997 [-2.31, 0.38] 0.069 |

- **MINCORR_10to5 is significantly WORSE than prod on all three metrics** (p<=0.017 each; CIs entirely below 0). Not a wash -- it hurts.
- The breadth EW configs (top-6/10/15) are all directionally below prod on point estimates but **not statistically significant** (every CI straddles 0; p>0 in the 0.05-0.15 range). Holding more names is a mild, insignificant Sharpe give-up in exchange for MaxDD.

## Head-to-head: MINCORR_10to5 vs TOP10_EW (clean bootstrap)

| Metric | mean [CI] | p>0 |
|---|---|---|
| dSharpe | -0.145 [-0.32, 0.03] | 0.058 |
| dSortino | -0.171 [-0.47, 0.13] | 0.134 |
| dCVaR | -0.692 [-2.02, 0.60] | 0.151 |

Corr-selecting 5-of-10 **loses to just holding all 10** (dSharpe -0.145, marginal p=0.058; all point estimates negative). If you go to a top-10 pool, hold them EW; do not corr-select down.

## Walk-forward (3 segments, clean)

| Config | seg0 2008-2014 | seg1 2014-2020 | seg2 2020-2026 |
|---|---|---|---|
| PROD | 1.179 | 1.252 | 1.471 |
| MINCORR_10to5 | 1.069 (-0.110) | 1.195 (-0.057) | 1.045 (-0.426) |

MINCORR_10to5 loses to PROD in **all three** segments (worst in the most recent: -0.43). No breadth config qualified for walk-forward (none beat prod clean Sharpe and none was significant). **No config beats PROD out-of-sample.**

## Verdict

- **(a) MINCORR_10to5 -- NO, and it is worse than the prior 6->5 corr WASH.** Corr-only selection at a *moderate* prune (10->5) does NOT preserve momentum. Significantly worse than prod on Sharpe/Sortino/CVaR (p<=0.017), -0.22 Sharpe, -9pp CAGR, and MaxDD does not even improve (-32.0% vs -31.4%). Mechanism: the 6->5 corr drop was a wash because the pool stayed tight (drop only the single most-redundant name from a high-momentum set). At 10->5 you discard half the pool, and minimizing average correlation systematically pulls in the most *idiosyncratic / off-theme* names (which tend to be momentum laggards), throwing away the correlated cluster of momentum winners that carries the premium. Same failure family as min-var, reached via the diversification objective rather than the variance objective.
- **(b) Breadth curve (clean), monotonic Sharpe-for-MaxDD trade:**

  | Pool | Sharpe | MaxDD | CAGR | marginal vs prev |
  |---|---|---|---|---|
  | top-5 (prod) | 1.281 | -31.4% | 31.4% | -- |
  | top-6 | 1.231 | -30.4% | 28.2% | -0.050 Sh / +1.0pp DD |
  | top-10 | 1.204 | -26.4% | 24.2% | -0.027 Sh / +4.0pp DD |
  | top-15 | 1.187 | -22.8% | 21.4% | -0.017 Sh / +3.6pp DD |

  More breadth monotonically lowers Sharpe/CAGR and lowers MaxDD; **none of the trades is statistically significant vs prod.** TOP10_EW is a clean midpoint knee: -5pp MaxDD (-26.4%) and -0.077 Sharpe (insignificant), while retaining ~24% CAGR. Per unit of Sharpe given up, top-15 is actually the more MaxDD-efficient point (-8.6pp DD for -0.094 Sharpe), but it cost most CAGR (-10pp). If the goal is a softer drawdown with minimal Sharpe sacrifice, top-10 is the balanced choice; if maximal drawdown reduction is the goal and CAGR can be spent, top-15. The MaxDD relief is gate-ON dispersion smoothing, not crisis protection (per-crisis DDs are flat across configs).
- **(c) MINCORR_10to5 vs TOP10_EW -- holding all 10 wins.** Corr-selecting 5-of-10 loses (dSharpe -0.145, p=0.058). Selection-by-correlation adds no value over plain breadth.

**Overall: keep prod top-5 EW.** No config beats prod out-of-sample. MINCORR_10to5 is a clear reject (significantly worse). The breadth EW configs are insignificant Sharpe give-ups that buy MaxDD; top-10 EW is the most defensible knee if a softer drawdown profile is ever desired, but it is not an edge over prod -- it is a risk-preference dial.

## Caveats and confidence

- Single in-sample backtest; bootstrap + 3-seg walk-forward used to temper overfit, but no true holdout. Confidence in the *rejections* (MINCORR_10to5 worse; corr-selection adds nothing) is HIGH -- significant on multiple metrics and consistent across clean/stress/walk-forward. Confidence that breadth is a *non-significant* Sharpe give-up is MEDIUM-HIGH (CIs straddle 0 but point estimates consistent).
- Per-crisis windows are dominated by the gate (OFF in most crises), so crisis tables understate any breadth differences in normal regimes; the full-window MaxDD is the better breadth discriminator.
- min-corr uses 252d sample correlation (no shrinkage); a shrunk corr would likely move MINCORR toward holding-all-10 but cannot rescue it above prod (top-10 EW itself does not beat prod).
- PROD/top-6/top-15 reproduce cited anchors exactly; engine integrity (PIT membership, delisting, T+1 MOO, 10 bps) inherited unchanged from `ndx_sleeve_live.run_ndx_backtest`.

## Handoff

None required. Research complete; no production change recommended. If the user wants a drawdown-softened NDX sleeve variant as a *product* option (top-10 EW), that is a fixer task -- but the evidence says it is a risk-preference dial, not an alpha improvement.
