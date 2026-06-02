# CPM 3-subset selection: MIN-AVG-PAIRWISE-CORRELATION vs MIN-VARIANCE

Is **MINCORR** (pure-diversification, correlation-based, Choueifaty-flavored) a better 3-subset SELECTION objective than the production **MINVAR** for the CPM (Cross-asset Parity Momentum) sleeve? **MINVOL** (3 lowest individual-vol assets) is a reference. All three are inverse-vol weighted with a STRICT-3 partial-safe fallback; only the 3-subset selection rule changes.

**Selection rules (pick 3 of the top-K=4 positive-trend candidates):**

| Rule | Objective |
|---|---|
| MINVAR (production) | minimize equal-weight portfolio variance w'Sigma w |
| MINCORR | minimize the average of the 3 pairwise correlations (most diversified trio) |
| MINVOL (ref) | the 3 lowest individual-vol assets (ignores correlation) |

**Both MINVAR and MINCORR are risk-based selectors** (use only the trailing risk estimate, not realized performance) -> neither is overfit-prone in the way a performance-based selector would be.

**Config (every table):** weighting = inverse-vol; fallback = STRICT-3 partial-safe (risky_fraction = min(n_pos,3)/3, remainder to timed SHV/IEF safe); cov lookback 504d; K=4; vol-adjusted Faber ranker; HYG-or-TIP canary. Execution = T+1 MOO exact (`mooex`, real auto_adjust opens); post-cost 10 bps/side. Clean window 2008-05-30..2026-05-22 (18y); extended 1999-03-10..2026-05-22 (27y).

**The selection rule only differentiates months where n_pos >= 4** (choose 3 of 4). When n_pos == 3 there is a single 3-subset; when n_pos in {1,2} the STRICT-3 partial-safe inverse-vol weights ALL positives (selection-agnostic).

Source harness: `research/selection_mincorr_vs_minvar.py` (read-only; no production files touched). MINVAR delegates to `cpm_live.min_var_subset` for byte-identical anchor reproduction.

## 0. Anchor check (MINVAR reproduces the STRICT-3 CPM-solo anchor)

| Window | Sharpe | MaxDD | Calmar | Expected | Match |
|---|---:|---:|---:|---|---|
| clean | 1.2667 | -12.66% | 1.1306 | 1.2667/-12.66%/1.1306 | CONFIRMED |
| ext | 1.2349 | -15.18% | 0.9119 | 1.2349/-15.18%/0.9119 | CONFIRMED |

MINVAR reproduces the STRICT-3 anchor exactly; MINCORR/MINVOL are trusted relative to it.

## 1. Headline -- CPM-solo, net 10 bps/side

**Clean (18y):**

| Selection | Sharpe | CAGR | Vol | MaxDD | Calmar |
|---|---:|---:|---:|---:|---:|
| MINVAR (production) | 1.2667 | 14.31% | 11.08% | -12.66% | 1.1306 |
| MINCORR (diversification) | 1.2218 | 14.30% | 11.52% | -12.66% | 1.1301 |
| MINVOL (3 lowest-vol, ref) | 1.2131 | 13.62% | 11.09% | -12.66% | 1.0762 |

**Extended (27y):**

| Selection | Sharpe | CAGR | Vol | MaxDD | Calmar |
|---|---:|---:|---:|---:|---:|
| MINVAR (production) | 1.2349 | 13.84% | 10.99% | -15.18% | 0.9119 |
| MINCORR (diversification) | 1.1933 | 13.87% | 11.43% | -16.31% | 0.8504 |
| MINVOL (3 lowest-vol, ref) | 1.2044 | 13.52% | 11.04% | -17.24% | 0.7844 |

## 2. Paired block bootstrap -- MINCORR vs MINVAR (B=2000, block=21, seed=42)

Same block draws applied to both rules (paired). Difference = MINCORR minus MINVAR. Positive => MINCORR wins (for MaxDD, positive = less negative = shallower). 'Significant' if the 95% CI excludes 0.

### Clean (18y) (daily corr MINCORR vs MINVAR = 0.9753)

| Metric (MINCORR-MINVAR) | mean | 95% CI | P(MINCORR>MINVAR) | excludes 0? |
|---|---:|---|---:|---:|
| dSharpe | -0.0448 | [-0.1457, +0.0567] | 20.0% | no |
| dMaxDD | -0.62pp | [-3.82, +2.34]pp | 34.0% | no |
| dCalmar | -0.0345 | [-0.2669, +0.1638] | 35.8% | no |

### Extended (27y) (daily corr MINCORR vs MINVAR = 0.9657)

| Metric (MINCORR-MINVAR) | mean | 95% CI | P(MINCORR>MINVAR) | excludes 0? |
|---|---:|---|---:|---:|
| dSharpe | -0.0430 | [-0.1382, +0.0571] | 18.4% | no |
| dMaxDD | -0.81pp | [-4.82, +2.62]pp | 33.1% | no |
| dCalmar | -0.0306 | [-0.2232, +0.1452] | 36.4% | no |

## 3. Subset overlap -- how often MINCORR picks a DIFFERENT 3-subset than MINVAR

Restricted to **selection-active** rebalances (n_pos >= 4, where a 3-of-4 choice actually exists). Jaccard = |intersection|/|union| of the two 3-subsets.

| Window | rebal total | selection-active (n_pos>=4) | same subset | different | % different | avg Jaccard |
|---|---:|---:|---:|---:|---:|---:|
| Clean (18y) | 217 | 168 | 64 | 104 | 61.9% | 0.690 |
| Extended (27y) | 327 | 243 | 84 | 159 | 65.4% | 0.673 |

**When they differ -- who wins the forward month?** (invvol portfolio close->close return over the applied month, on the differing rebalances):

| Window | differing months | MINCORR wins fwd | avg fwd MINCORR | avg fwd MINVAR |
|---|---:|---:|---:|---:|
| Clean (18y) | 104 | 48 | +1.433% | +1.429% |
| Extended (27y) | 159 | 76 | +1.411% | +1.395% |

## 4. Diversification / concentration of the held 3-subset (n_pos>=3 months)

avg pairwise corr = mean of the 3 trailing 504d pairwise correlations of the held trio; effN = 1/HHI of the inverse-vol weights (max 3.0 = perfectly balanced).

**Clean (18y):**

| Selection | months | avg pairwise corr | avg effN |
|---|---:|---:|---:|
| MINVAR (production) | 182 | 0.3518 | 2.933 |
| MINCORR (diversification) | 182 | 0.3246 | 2.899 |
| MINVOL (3 lowest-vol, ref) | 182 | 0.3662 | 2.935 |

**Extended (27y):**

| Selection | months | avg pairwise corr | avg effN |
|---|---:|---:|---:|
| MINVAR (production) | 269 | 0.2987 | 2.909 |
| MINCORR (diversification) | 269 | 0.2668 | 2.855 |
| MINVOL (3 lowest-vol, ref) | 269 | 0.3210 | 2.914 |

## 5. Verdict

Filled from the computed numbers (clean window decisive):

- **CPM-solo clean:** MINCORR Sharpe 1.2218 / CAGR 14.30% / MaxDD -12.66% / Calmar 1.1301; MINVAR Sharpe 1.2667 / CAGR 14.31% / MaxDD -12.66% / Calmar 1.1306.
- **CPM-solo ext:** MINCORR Sharpe 1.1933 / MaxDD -16.31% / Calmar 0.8504; MINVAR Sharpe 1.2349 / MaxDD -15.18% / Calmar 0.9119.
- **Paired clean (MINCORR-MINVAR):** dSharpe -0.0448 CI[-0.1457,+0.0567] (P 20%); dMaxDD -0.62pp CI[-3.82,+2.34]pp; dCalmar -0.0345 CI[-0.2669,+0.1638].
- **Subset overlap (clean):** MINCORR differs from MINVAR on 104/168 selection-active months (61.9%), avg Jaccard 0.690.

**MINCORR does what it claims, but it is not a better selection objective than MINVAR -- it is comparable-to-worse, and it does NOT win drawdown.**

1. **MINCORR genuinely maximizes diversification.** It delivers the lowest average pairwise correlation of the held trio in both windows (clean 0.3246 vs MINVAR 0.3518; ext 0.2668 vs 0.2987). The objective behaves as designed -- it really does pick the most mutually-decorrelated trio. Yet effN is essentially flat across rules (clean ~2.93 vs 2.90; ext ~2.91 vs 2.86), so the lower correlation does not translate into a more balanced weight distribution, because inverse-vol weighting (applied afterward) dominates the concentration profile.

2. **MINVAR wins risk-adjusted return, directionally in both windows.** Clean Sharpe 1.2667 vs 1.2218; ext 1.2349 vs 1.1933. The paired bootstrap puts the difference inside noise -- dSharpe -0.0448 (clean) / -0.0430 (ext), both 95% CIs straddle 0, and P(MINCORR beats MINVAR) is only 20% / 18% -- but the directional read consistently favors MINVAR. MINCORR also runs ~0.4pp higher vol for no CAGR benefit (CAGR is a dead heat: 14.30% vs 14.31% clean, 13.87% vs 13.84% ext), which is exactly why its Sharpe is lower: ignoring vol levels in selection lets it admit a more volatile (if less correlated) trio.

3. **MINCORR does NOT win drawdown -- it loses it in the extended window.** This is the decisive disqualifier given the spec ("keep min-var unless min-corr clearly wins DD"). Clean MaxDD is identical (-12.66% for all three) because the worst clean-window drawdown is driven by low-breadth partial-safe / safe-asset months, which are selection-agnostic. In the extended window MINCORR is materially WORSE: MaxDD -16.31% vs MINVAR -15.18% (+1.13pp deeper) and Calmar 0.8504 vs 0.9119. The paired bootstrap dMaxDD is -0.62pp (clean) / -0.81pp (ext) with P(MINCORR shallower) only 34% / 33% -- not significant, but again pointing the wrong way for the challenger. MINCORR never produces a shallower drawdown than MINVAR in either window.

4. **They disagree often but it barely matters.** MINCORR picks a different 3-subset on 62% (clean) / 65% (ext) of selection-active months (avg Jaccard ~0.68 -- they typically share 2 of 3 names). But on the months where they differ the forward-month outcome is a coin flip: MINCORR wins 48/104 (clean) and 76/159 (ext), and the average forward return is a dead heat (+1.433% vs +1.429% clean; +1.411% vs +1.395% ext). Frequent disagreement, no edge from it.

**Recommendation: keep MIN-VARIANCE (the incumbent).** Both selectors are risk-based and neither is overfit-prone, so this is a clean, honest comparison. MINCORR is the more aggressively diversified objective and is comparable on Sharpe within noise, but it is directionally worse on Sharpe in both windows, runs higher vol for no CAGR, and -- critically -- fails the only condition under which it would have been worth switching: it does not win drawdown (identical clean, clearly worse ext DD and Calmar). MINVAR already implicitly captures correlation (it minimizes full-covariance portfolio variance, which rewards low correlation AND low vol jointly), so the pure-correlation objective discards the useful vol information without buying any tail protection. No reason to switch; min-var is simpler, incumbent, and weakly dominant.

## Caveats

- All post-cost (10 bps/side), T+1 MOO exact with real yfinance auto_adjust opens. CPM-solo (no equity vol gate; that gate only affects BULL/blend, out of scope here).
- The selection rule only acts on n_pos>=4 rebalances; differences are diluted across the full curve by the many n_pos<4 (identical) months. Magnitudes are therefore small by construction.
- Ext 27y is partially proxy-backed for the CPM trend universe pre-2006; clean 18y has full real-open coverage and is the decisive lens.
- Forward-month win attribution in Section 3 uses simple close->close invvol portfolio return over the applied window (gross, no cost) -- a directional attribution, not the post-cost curve metric.
- MINCORR ignores vol levels in selection but is still inverse-vol weighted afterward, so vol does re-enter at the weighting step.
