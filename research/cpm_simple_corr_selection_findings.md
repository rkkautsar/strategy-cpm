# CPM simple corr-aware SELECTION: does "drop the most-redundant asset" capture the min-var-subset OOS edge cheaply?

Role: analyst (hypothesis-driven, read-only re production). No production files changed; no commit. Throwaway harness in `research/`.

## Question

Prior study (`research/cpm_weighting_corr*`) found correlation pays via SELECTION, not weighting: a MIN-VAR SUBSET(3) selection beats prod on both windows, both metrics, and all 3 sequential OOS segments (P97 bootstrap on Sharpe). But min-var selection was previously REMOVED from prod for PARSIMONY (single-stage top-4 inverse-vol; the marginal gain was judged not worth the optimizer complexity). The user wants a SIMPLER, parameter-free corr-aware selection -- "remove one asset so the rest is more diverse" -- and asks:

- (a) Does DROP-REDUNDANT-1 beat prod net of cost + OOS (both windows, both metrics, all 3 OOS segments)?
- (b) Does it CAPTURE MOST of the min-var-subset edge?
- (c) Parsimony verdict: is the simple rule simple ENOUGH and good ENOUGH to adopt where min-var was not?

Plus a critical CONFOUND CONTROL the user added: all trio rules reduce 4 picks to 3 at full risk budget, so the gain might be pure CONCENTRATION (3 vs 4), not correlation. A naive TOP-3-BY-RANK trio isolates that. And EQUAL-WEIGHT sizing variants test whether selection does all the work and sizing can be trivial.

## Method / reproduction

- Harness: `research/cpm_simple_corr_selection.py`, built on `research/cpm_harness.py` (mooex T+1 MOO exact, both-252 baseline, 10 bps/side net) and reusing `research/cpm_weighting_corr.py` machinery (`run_cell`, `paired_block_bootstrap`, `annualized_turnover`, `_min_var_subset`, per-crisis). Selection/canary/trend/safe/partial-safe blocks are byte-identical to prod; ONLY the subset rule and sizing are swapped.
- Run: `.venv/bin/python -m research.cpm_simple_corr_selection`
- Output: `research/cpm_simple_corr_selection_findings.json`.
- Anchor verified first: `H.verify_anchor` reproduces the prod clean both-252 anchor EXACT (Sharpe 1.1658 / MaxDD -12.97% / Calmar 1.0137). PROD cell delegates to `cpm_live.inv_vol_weights`, so the baseline IS production.

Selection rules (all keep prod rank -> top-4 -> positive filter, act only when there are 4 positive picks, reduce 4 -> 3 at FULL risk budget; <=3 picks unchanged = prod):

- PROD: keep all positive picks (top-4), inverse-vol. Baseline.
- TOP-3-BY-RANK (concentration control): drop the lowest vol-adj-Faber-RANKED pick. No correlation.
- DROP-REDUNDANT-1 (primary, parameter-free): drop the asset with the highest AVG pairwise 252d correlation to the other three.
- MIN-CORR-TRIO: keep the 3-of-4 with the lowest avg pairwise correlation.
- MIN-VAR-SUBSET(3) (benchmark): the complex incumbent challenger that survived OOS; minimizes equal-weight portfolio variance w'Sigma w.

Sizing for each trio rule: INVERSE-VOL (IV, cov diagonal, prod) and plain EQUAL-WEIGHT (EW = 1/3, no covariance at all).

Why full-risk-on-drop is the right comparison: prod is already 100% risky whenever n_pos == 4 (risky_fraction = min(4,4)/4 = 1.0). All trio rules act only on n_pos == 4 months, so dropping 4 -> 3 at full risk keeps both prod and challengers 100% risky there -- only the held names differ. This isolates DIVERSIFICATION from DE-RISKING. The min-var benchmark uses identical full-risk-on-4 semantics, so edge-capture is like-for-like. A partial-safe-on-drop alternative (3/4 risky + 1/4 safe) is run as a robustness note.

## 1. Headline (net 10 bps/side, cov lookback 252)

| cell | clean Sharpe | clean Calmar | clean MaxDD | ext Sharpe | ext Calmar | ext MaxDD | turnover (1-way ann) |
|---|---:|---:|---:|---:|---:|---:|---:|
| PROD (top-4 inv-vol) | 1.1658 | 1.0137 | -12.97% | 1.2004 | 0.8571 | -15.73% | 258% |
| TOP-3-BY-RANK + IV | 0.9566 | 0.8757 | -12.87% | 1.0501 | 0.7848 | -15.93% | 331% |
| TOP-3-BY-RANK + EW | 0.9477 | 0.8564 | -13.40% | 1.0533 | 0.7951 | -16.65% | 317% |
| DROP-1 + IV | 1.1791 | 1.1565 | -11.54% | 1.1942 | 0.8346 | -16.08% | 351% |
| DROP-1 + EW | 1.1580 | 1.0351 | -13.03% | 1.1932 | 0.8478 | -16.78% | 340% |
| MIN-CORR-TRIO + IV | 1.1791 | 1.1565 | -11.54% | 1.1942 | 0.8346 | -16.08% | 351% |
| MIN-CORR-TRIO + EW | 1.1580 | 1.0351 | -13.03% | 1.1932 | 0.8478 | -16.78% | 340% |
| MIN-VAR(3) + IV | 1.2622 | 1.2196 | -11.35% | 1.2624 | 0.9135 | -14.92% | 299% |
| MIN-VAR(3) + EW | 1.2711 | 1.0883 | -13.03% | 1.2969 | 0.9458 | -15.22% | 296% |

Three facts jump out immediately:

1. DROP-1 and MIN-CORR-TRIO are IDENTICAL -- byte-for-byte the same curve, same turnover, same crises. They pick the same trio on 168/168 selection-active months (Jaccard 1.0). This is not a coincidence: for exactly 4 assets, dropping the one with the highest average pairwise correlation is mathematically equivalent to keeping the trio with the lowest average pairwise correlation. The user's parameter-free "drop-redundant" rule IS min-corr-trio. From here they are reported as one rule (DROP-1).

2. TOP-3-BY-RANK is much WORSE than prod (clean Sharpe 0.96 vs 1.17). Pure 3-vs-4 concentration, choosing which to drop by momentum rank, destroys value. So dropping an asset is NOT free -- the concentration penalty is real and large, and you only come out ahead if you drop the RIGHT asset.

3. MIN-VAR is the strongest variant on both windows (clean 1.2622 IV / 1.2711 EW; ext 1.2624 / 1.2969), and is the only rule whose drawdown also improves materially in the EXTENDED window (ext MaxDD -14.9% / -15.2% vs prod -15.7%).

## 2. The decisive confound test: CORRELATION vs CONCENTRATION

Each corr-trio MINUS top-3-by-rank (same sizing), paired block bootstrap B=2000 + 3-segment walk-forward, clean window:

| comparison | dSharpe mean [95% CI] P | dCalmar P | walk-forward dSharpe (3 seg) |
|---|---|---:|---|
| DROP-1 IV - TOP3RANK IV | +0.2245 [+0.059, +0.397] 100% | 97% | +0.164 / +0.314 / +0.226 |
| MIN-VAR IV - TOP3RANK IV | +0.3068 [+0.155, +0.464] 100% | 100% | +0.326 / +0.282 / +0.311 |
| DROP-1 EW - TOP3RANK EW | +0.2111 [+0.045, +0.380] 99% | 97% | +0.091 / +0.325 / +0.272 |
| MIN-VAR EW - TOP3RANK EW | +0.3243 [+0.163, +0.492] 100% | 100% | +0.294 / +0.307 / +0.379 |

This is unambiguous and is the cleanest result in the study. Correlation EARNS ITS KEEP. Given that you are going to hold 3 of the 4 picks, choosing the 3 by correlation (drop-1 or min-var) beats choosing them by momentum rank with P99-100% bootstrap confidence (CIs exclude 0) and positive walk-forward in all three segments. The lever is decisively "WHICH 3", not "3 vs 4". A naive concentration (top-3-by-rank) is strictly the worst thing in the study; correlation-awareness is what rescues it.

But note the framing flips when the baseline is prod rather than top-3-by-rank (next section): correlation beats naive concentration handily, yet the corr-trio barely beats prod's full top-4, because prod never threw the 4th asset away in the first place.

## 3. (a) Does DROP-1 beat PROD? Within noise.

Paired block bootstrap vs PROD (clean, B=2000, block=21, seed=42); P = P(variant > prod):

| cell | dSharpe mean [95% CI] P | dCalmar mean [95% CI] P | dMaxDD mean P |
|---|---|---|---|
| TOP-3-BY-RANK IV | -0.2099 [-0.347, -0.077] 0% | -0.235 [-0.554, -0.005] 2% | -3.39pp 9% |
| TOP-3-BY-RANK EW | -0.2186 [-0.353, -0.088] 0% | -0.238 [-0.549, -0.003] 2% | -3.91pp 6% |
| DROP-1 IV | +0.0146 [-0.092, +0.126] 60% | +0.044 [-0.193, +0.285] 67% | +0.66pp 65% |
| DROP-1 EW | -0.0075 [-0.120, +0.105] 45% | +0.029 [-0.238, +0.282] 62% | +0.24pp 56% |
| MIN-VAR IV | +0.0969 [-0.005, +0.196] 97% | +0.112 [-0.084, +0.334] 89% | +1.28pp 83% |
| MIN-VAR EW | +0.1057 [+0.002, +0.213] 98% | +0.133 [-0.091, +0.398] 89% | +1.25pp 78% |

Walk-forward vs PROD (3 sequential ~6y clean segments, variant minus prod):

| cell | 2008-2014 | 2014-2020 | 2020-2026 |
|---|---:|---:|---:|
| DROP-1 IV | dSh -0.036 | dSh +0.095 | dSh +0.007 |
| DROP-1 EW | dSh -0.096 | dSh +0.100 | dSh +0.023 |
| MIN-VAR IV | dSh +0.126 | dSh +0.063 | dSh +0.091 |
| MIN-VAR EW | dSh +0.107 | dSh +0.082 | dSh +0.130 |

Reading:

- DROP-1 IV beats prod on clean Sharpe by a hair (+0.013) and trims clean MaxDD (-11.54% vs -12.97%), but the bootstrap is squarely within noise: dSharpe +0.015 with CI [-0.092, +0.126], P only 60%. On the EXTENDED window DROP-1 is flat-to-slightly-worse (ext Sharpe 1.1942 vs 1.2004; ext Calmar 0.835 vs 0.857; ext MaxDD deeper -16.08% vs -15.73%). Walk-forward is NEGATIVE in the first segment. It does NOT satisfy "beats prod on both windows, both metrics, all 3 OOS segments."
- DROP-1 EW is even weaker (clean dSharpe -0.008, P45% -- below prod).
- DROP-1 also costs ~90pp more annualized turnover (351% vs 258%): dropping/re-adding the 4th name churns the book, and the net-of-10bps numbers already reflect that drag.
- MIN-VAR, by contrast, clears the bar: P97-98% on Sharpe (EW CI EXCLUDES 0), positive in all 3 walk-forward segments, better on BOTH windows, and lower turnover than DROP-1 (299% -- the optimizer-picked trio is more stable month-to-month than the corr-only trio).

Answer to (a): NO. DROP-1 does not beat prod net of cost and OOS; it is within noise on clean and flat-to-worse on ext.

## 4. (b) Does DROP-1 CAPTURE the min-var edge? Mostly not (on Sharpe).

Edge over PROD, side-by-side (clean window, IV sizing), and DROP-1's capture fraction of the MIN-VAR edge:

| metric | PROD | DROP-1 | MIN-VAR | DROP-1 edge | MIN-VAR edge | DROP-1 capture |
|---|---:|---:|---:|---:|---:|---:|
| clean Sharpe | 1.1658 | 1.1791 | 1.2622 | +0.0133 | +0.0964 | ~14% |
| clean Calmar | 1.0137 | 1.1565 | 1.2196 | +0.1428 | +0.2059 | ~69% |
| clean MaxDD | -12.97% | -11.54% | -11.35% | +1.43pp | +1.62pp | ~88% |
| ext Sharpe | 1.2004 | 1.1942 | 1.2624 | -0.0062 | +0.0620 | negative |
| bootstrap dSharpe P | -- | P60% | P97% | within noise | significant | does not reproduce |

DROP-1 captures the DRAWDOWN direction of the min-var edge (clean MaxDD +1.43pp of +1.62pp, ~88%; Calmar ~69%) -- consistent with the idea that dropping a redundant name reduces concentration risk in a selloff. But it captures almost none of the SHARPE edge (~14% clean, NEGATIVE on ext), and crucially it does not reproduce the statistical signal: min-var is P97-98% over prod, DROP-1 is P60% (a coin flip). The bootstrap dMaxDD for DROP-1 (+0.66pp, P65%) is also within noise -- the clean-window point improvement is not robust to resampling.

Why the gap? DROP-1 / min-corr use correlation ONLY; min-var uses correlation AND vol levels (it minimizes w'Sigma w). They pick a DIFFERENT trio 67% of the time (drop-1 vs min-var: same on only 55/168 active months, Jaccard 0.66). This is the same lesson as the prior `selection_mincorr_vs_minvar` study: discarding vol information costs you -- min-var's joint vol+corr objective is what delivers the durable Sharpe edge, and the pure-correlation shortcut does not reach it.

Answer to (b): NO on Sharpe (captures ~14% clean, negative ext, signal not reproduced). PARTIALLY on drawdown/Calmar (captures most of the DD improvement, but not bootstrap-significant).

## 5. Equal-weight vs inverse-vol sizing

Does plain EW (no covariance at all) match or beat inverse-vol on the diversified trio?

| selection | IV clean Sharpe | EW clean Sharpe | IV clean Calmar | EW clean Calmar | IV clean MaxDD | EW clean MaxDD |
|---|---:|---:|---:|---:|---:|---:|
| DROP-1 | 1.1791 | 1.1580 | 1.1565 | 1.0351 | -11.54% | -13.03% |
| MIN-VAR | 1.2622 | 1.2711 | 1.2196 | 1.0883 | -11.35% | -13.03% |

- For DROP-1, EW is slightly WORSE than IV on every metric. No parsimony win there.
- For MIN-VAR, EW BEATS IV on Sharpe (clean 1.2711 vs 1.2622; ext 1.2969 vs 1.2624) and is the single strongest Sharpe cell in the study, with the only bootstrap CI that excludes 0 (dSharpe +0.106, P98%). This matches the prior expectation that EW is more robust OOS once assets are pre-diversified by selection. BUT EW gives up the drawdown protection: clean MaxDD -13.03% vs IV -11.35%, Calmar 1.0883 vs 1.2196. Inverse-vol's vol-targeting is doing the tail-trimming work that EW cannot.
- Net: EW is a Sharpe-competitive, maximally-parsimonious sizing on a min-var trio, but it trades away drawdown/Calmar. It is not a clean dominant win -- the choice is a Sharpe-vs-drawdown preference, and prod's inv-vol already optimizes the drawdown side.

## 6. Per-crisis (EXT curve; Sharpe / MaxDD)

| cell | GFC | COVID | 2022 | 2025 |
|---|---|---|---|---|
| PROD | 0.54 / -11.9% | 1.19 / -10.5% | -0.30 / -8.0% | 0.24 / -13.0% |
| TOP-3-BY-RANK IV | 0.68 / -10.2% | 1.75 / -10.1% | -0.62 / -11.4% | 0.30 / -11.8% |
| DROP-1 IV | 0.48 / -10.3% | 1.49 / -10.1% | -0.35 / -7.7% | 0.38 / -11.5% |
| MIN-VAR IV | 0.74 / -10.3% | 1.25 / -10.1% | -0.11 / -6.2% | 0.24 / -11.3% |
| MIN-VAR EW | 0.82 / -13.1% | 1.11 / -10.2% | +0.10 / -5.2% | 0.36 / -10.7% |

Min-var is the only rule with a consistent cross-crisis drawdown improvement and the best GFC/2022 risk-adjusted return. DROP-1 helps modestly in COVID and 2025 but is mixed in GFC (0.48 vs prod 0.54). Top-3-by-rank trims GFC/COVID drawdown but is much worse in 2022 -- the unguided concentration is regime-fragile.

## 7. Robustness notes

- Cov lookback 504 (vs 252 primary): every variant shifts up (the known lookback confound from `cpm_weighting_corr`). PROD 1.1910, DROP-1 1.2440 (+0.053 vs prod -- a wider but still single-window gap), MIN-VAR 1.2923. The relative ordering is preserved (min-var > drop-1 > prod); the absolute drop-1-vs-prod gap is larger at 504 but this is partly the lookback effect prod itself captures when its own lookback is lengthened. The both-252 prod baseline is the decision lens.
- Partial-safe-on-drop alternative (3/4 risky + 1/4 safe instead of full-risk renormalize): DROP-1 clean Sharpe 1.1897 (vs full-risk 1.1791), MaxDD shallower -10.23% (vs -11.54%), bootstrap dMaxDD +3.38pp P97% vs prod. As expected, injecting 1/4 safe on the drop month trims drawdown materially -- but that is DE-RISKING, not diversification, and it conflates the two levers. Sharpe is still within noise vs prod (P65%). If the goal were drawdown reduction, holding more safe is a more direct (and orthogonal) lever than corr selection.

## 8. Verdict (DOCUMENT / parsimony wins)

- (a) Does DROP-1 beat prod net cost + OOS? NO. Within noise on clean (dSharpe +0.015, P60%, CI straddles 0), flat-to-worse on ext, negative in the first walk-forward segment, EW version below prod, and ~90pp more turnover. Fails "both windows, both metrics, all 3 OOS segments."
- (b) Does DROP-1 capture the min-var edge? NO on Sharpe (~14% of the clean edge, negative on ext, P60% vs min-var's P97%). PARTIALLY on drawdown (captures most of the clean MaxDD improvement, but not bootstrap-significant). The cheap correlation-only rule does not reach the min-var Sharpe edge because it discards vol information; min-var's joint vol+corr objective is load-bearing.
- (c) Parsimony verdict: DROP-1 is simple ENOUGH (parameter-free, one line) but NOT good ENOUGH. It is within noise of prod and misses most of the min-var edge. Min-var is good enough but was dropped for parsimony; the simple rule does not rescue that edge cheaply. RECOMMENDATION: DOCUMENT / REJECT as a prod change. Parsimony wins, exactly as the low-ceiling prior (selection is not load-bearing; min-var only barely cleared the bar) predicted.

The one genuinely positive and robust result is the confound control: correlation-aware trio selection beats naive top-3-by-rank concentration with P99-100% confidence. The lever, if you ever take 3 of 4, is decisively WHICH 3 (and the best "which" is min-var's vol+corr objective, not pure correlation). But prod does not take 3 of 4 -- it holds all 4 -- so against prod the simple corr rule is within noise. Correlation matters for HOW you concentrate; it does not justify concentrating in the first place over prod's top-4.

## Caveats / confidence

- Single in-sample full-window evaluation; selection rules act only on n_pos == 4 months (168 of ~217 clean rebalances), so the curves are diluted by the many identical n_pos < 4 months -- magnitudes are small by construction (low ceiling held strictly, all CIs reported).
- All post-cost (10 bps/side), T+1 MOO exact opens; cov/corr windows strictly trailing (`tail(lookback)` up to sig_d), monthly resample on `loc[:sig_d]`; no look-ahead. Turnover reported (corr trios churn ~90pp/yr more one-way than prod top-4).
- DROP-1 == MIN-CORR-TRIO is exact (Jaccard 1.0) and is a structural identity for the 4 -> 3 case, not a data artifact.
- EXT pre-2008 leans on stitched proxies (lower confidence on absolute ext levels; directional cross-cell comparison is sound). Clean 18y is the decision lens.
- Confidence HIGH that DROP-1 does not beat prod net OOS (P60%, fails ext + first walk-forward segment). HIGH that correlation beats naive concentration (P99-100%). HIGH that DROP-1 does not capture the min-var Sharpe edge. MEDIUM-HIGH that EW matches IV on Sharpe for a min-var trio but loses drawdown.

## Knowledge candidate

A simple parameter-free "drop the most-redundant asset" CPM selection (drop highest-avg-pairwise-corr of 4; provably identical to min-corr-trio for 4 -> 3) does NOT beat prod top-4 net of cost + OOS (clean dSharpe +0.015 P60%, flat-to-worse ext, mixed walk-forward) and does NOT capture the min-var-subset Sharpe edge (~14% clean, negative ext; min-var stays P97-98%) -- because it discards vol information that min-var's joint vol+corr objective uses. Parsimony wins: document/reject. The robust positive is the confound control -- correlation-aware trios beat naive top-3-by-rank concentration P99-100%, so the lever is WHICH 3, not 3-vs-4; but prod holds all 4, so against prod the cheap corr rule is within noise. Equal-weight on a min-var trio matches inverse-vol on Sharpe (EW the only CI to exclude 0) but gives up drawdown/Calmar.
