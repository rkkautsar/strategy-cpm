# IV vs EW sizing on the min-var 3-of-4 trio: path-independent significance

Throwaway research. Read-only re production; no prod/memo/cpm_live edits; no commit.

Anchor (clean, via research/cpm_harness.py): Sharpe 1.2622, MaxDD -0.1135, Calmar 1.2196 -- verified first, reproduced exactly by MINVAR_IV.

## Question

Does inverse-vol (IV) weighting add SIGNIFICANT value over equal-weight (EW) when selection is min-var (ewobj) 3-of-4, on PATH-INDEPENDENT downside metrics (Sharpe / Sortino / CVaR)? Prior work bootstrapped Sharpe only (within-noise, p~0.71). Sortino and CVaR were never bootstrapped for this IV-vs-EW sizing contrast; Calmar / Martin / MaxDD are path-dependent point-estimates only. This settles it.

## Method

- Engine: research/cpm_harness.py (mooex T+1 MOO, both-252, 10 bps/side). `verify_anchor()` run first.
- Two cells, IDENTICAL ewobj min-var selection (canonical `_min_var_subset`, EW-variance objective), differ ONLY in sizing:
  - MINVAR_IV = ewobj selection + inverse-vol sizing = CURRENT PROD.
  - COHERENT_EW = ewobj selection + equal-weight sizing.
- Cells built via `research.cpm_minvar_coherence.make_weight_fn("minvar_ewobj", {"invvol","ew"})`. Full-risk-on-drop renormalize over the kept trio; everything else byte-identical to prod.
- Significance: paired block bootstrap of the SIZING contrast d = IV - EW on the DECISION (clean) window, B=2000, seed=42, via `research.cpm_bootstrap_multimetric.paired_block_bootstrap_mm` (byte-identical resampling to the other studies). Path-independent metrics ONLY: dSharpe, dSortino, dCVaR. Robustness: block=21 and block=42.
- Path-dependent metrics (Calmar / Martin / MaxDD) reported as POINT-ESTIMATE context only (block resampling shuffles the drawdown path, so their CIs are soft/unreliable; NOT classified).

Direction note: d = IV - EW. On Sharpe IV is the lower cell, so a negative dSharpe is expected; the live question is whether Sortino/CVaR exclude 0 in IV's favor (would require POSITIVE d).

## Point-estimate context (path-dependent; NOT significance)

| cell | window | Sharpe | Calmar | Martin | MaxDD | CAGR |
|---|---|---|---|---|---|---|
| MINVAR_IV (prod) | clean | 1.2622 | 1.2196 | 3.9522 | -0.1135 | 0.1384 |
| COHERENT_EW | clean | 1.2711 | 1.0883 | 4.1685 | -0.1303 | 0.1418 |
| MINVAR_IV (prod) | ext | 1.2624 | 0.9135 | 3.8170 | -0.1492 | 0.1363 |
| COHERENT_EW | ext | 1.2969 | 0.9458 | 4.0211 | -0.1522 | 0.1439 |

Read of the point estimates (soft CIs, do NOT classify):
- IV's drawdown "edge" is NOT consistent. IV wins on clean Calmar (1.2196 vs 1.0883) and clean MaxDD (-0.1135 vs -0.1303), but EW wins Martin in BOTH windows (4.17 vs 3.95 clean; 4.02 vs 3.82 ext), and on ext Calmar EW leads (0.9458 vs 0.9135) with ext MaxDD a near-wash (-0.1492 vs -0.1522). The IV advantage is essentially a single-window (clean Calmar/MaxDD) point artifact, reversed by Martin and by the ext window.
- EW wins Sharpe and CAGR in both windows.

## Significance: paired block bootstrap, d = IV - EW (clean / DECISION window)

block = 21:

| metric | mean | 95% CI | p(IV>EW) | CI excludes 0? |
|---|---|---|---|---|
| dSharpe | -0.0088 | [-0.0651, +0.0469] | 0.372 | no |
| dSortino | -0.0143 | [-0.1009, +0.0714] | 0.364 | no |
| dCVaR | -0.0541 | [-0.4603, +0.3601] | 0.392 | no |

block = 42 (robustness):

| metric | mean | 95% CI | p(IV>EW) | CI excludes 0? |
|---|---|---|---|---|
| dSharpe | -0.0087 | [-0.0637, +0.0474] | 0.364 | no |
| dSortino | -0.0142 | [-0.1003, +0.0742] | 0.363 | no |
| dCVaR | -0.0535 | [-0.4563, +0.3713] | 0.384 | no |

All six CIs (3 metrics x 2 block sizes) span 0. Point-estimate means are all NEGATIVE (favor EW, the opposite of IV adding value), p(IV>0) ~0.36-0.39 throughout. block=42 is essentially identical to block=21.

## Verdict (blunt; no recommendation)

IV adds NO statistically-supported value over EW on the min-var 3-of-4 trio, on ANY path-independent metric. All three classification metrics (Sharpe, Sortino, CVaR) have 95% CIs that span 0 at both block=21 and block=42, and every point-estimate mean of d=IV-EW is NEGATIVE -- i.e., the distributional/downside metrics that bootstrap cleanly slightly favor EW, within noise, not IV.

IV's apparent drawdown advantage (clean Calmar 1.2196 vs 1.0883, clean MaxDD -11.35% vs -13.03%) does NOT show up as significant downside outperformance: order-invariant downside (Sortino, CVaR) is flat-to-EW-favoring, and the path-dependent gap is itself fragile (Martin favors EW in both windows; ext Calmar/MaxDD favor EW or wash). The clean-window Calmar/MaxDD gap is a path/sequencing point-estimate, not a real distributional downside edge -- it is not significant.

Bottom line: on min-var selection, the IV-vs-EW sizing choice is within-noise on all path-independent metrics; IV's drawdown/Calmar point-estimate gap is not statistically supported.

## Caveats

- Single in-sample test (clean window is the decision metric; ext shown for context). No OOS holdout.
- Path-dependent metrics (Calmar / Martin / MaxDD) are point-estimates with soft CIs; block resampling shuffles drawdown paths, so they are NOT used for significance classification -- reported for transparency only.
- Bootstrap CIs are wide (low ceiling); differences within the band are within-noise.
- Scope: IV-vs-EW sizing on the ewobj min-var trio only. Canary/HYG out of scope. Selection-objective and prod-top4 contrasts are covered in research/cpm_minvar_coherence_findings.md, not re-run here.

## Reproduce

```
.venv/bin/python -m research.cpm_iv_vs_ew_minvar_significance
```
Outputs: research/cpm_iv_vs_ew_minvar_significance.json (+ this findings md).
