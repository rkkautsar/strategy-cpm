# CPM sleeve: Varadi MCA (min-correlation) 3-of-4 vs production min-variance 3-of-4

## Question

Does replacing CPM's MIN-VARIANCE 3-of-4 subset selection with a VARADI MCA
(MINIMUM-CORRELATION) 3-of-4 selection -- at the same trigger (n_pos=4), with
everything else byte-identical -- improve the CPM sleeve?

Hypothesis (from Optimum3): min-variance favors low-vol assets (bonds/gold), so
it can de-tilt CPM away from equities in bull markets; min-correlation optimizes
pairwise dependence regardless of vol, so it should keep high-momentum winners
while still diversifying -> better bull participation / CAGR / Sharpe. Risk =
more turnover (correlation reshuffling), per Optimum3's poor tax profile.

Scope trimmed to the CPM SLEEVE only (blend skipped). Point-estimates only.

## Method

- Harness: `research/cpm_harness.py` (mooex T+1 MOO exact, 10 bps/side, both-252
  lookback). Baseline = production `cpm_live.compute_target_weights` unchanged.
- Variant: monkeypatch `cpm_live._min_var_subset` -> `min_corr_subset`, which
  picks the 3-of-4 subset with the LOWEST AVERAGE PAIRWISE CORRELATION (mean of
  the 3 pairwise corrs) over the SAME `CORR_LOOKBACK_DAYS` (252). Fallback
  conditions byte-identical to production; only the objective (avg pairwise corr)
  and the matrix (corr vs cov) differ. Selector fires ONLY at n_pos=4 in both.
- Diagnostics: weight-sequence turnover (one-way annualized), n_pos=4 frequency,
  and selection divergence captured via an instrumented selector that computes
  both triplets on the identical candidate pool each rebalance.
- Run: `research/cpm_mca_vs_minvar_run.py`
  (`.venv/bin/python research/cpm_mca_vs_minvar_run.py`).
  Full numbers: `research/cpm_mca_vs_minvar_findings.json`.

## Anchor gate

Baseline reproduces the production both-252 anchor EXACTLY through the harness:
Sharpe 1.255673, MaxDD -13.03%, Calmar 1.007646. MCA numbers are trusted
relative to this.

## Headline -- CPM sleeve, net 10 bps/side

Clean (2008-05-30 .. 2026-05-22):

| Selection            | Sharpe | Sortino | CVaR-ratio | Calmar | Martin | MaxDD   | CAGR   | vol    | turnover/yr |
|----------------------|-------:|--------:|-----------:|-------:|-------:|--------:|-------:|-------:|------------:|
| MIN-VAR (production)  | 1.2557 | 1.8058  | 8.2295     | 1.0076 | 4.2571 | -13.03% | 13.13% | 10.28% | 3.55        |
| MCA (min-corr)        | 1.1408 | 1.6445  | 7.4346     | 0.9516 | 3.7953 | -13.03% | 12.40% | 10.79% | 3.95        |

Extended (1999-03-10 .. 2026-05-22):

| Selection            | Sharpe | Sortino | CVaR-ratio | Calmar | Martin | MaxDD   | CAGR   | vol    | turnover/yr |
|----------------------|-------:|--------:|-----------:|-------:|-------:|--------:|-------:|-------:|------------:|
| MIN-VAR (production)  | 1.2549 | 1.8114  | 8.2770     | 0.9712 | 4.1168 | -13.14% | 12.76% |  9.97% | 3.41        |
| MCA (min-corr)        | 1.1774 | 1.7047  | 7.7746     | 0.9135 | 3.9205 | -13.70% | 12.52% | 10.48% | 3.66        |

MCA is WORSE on every risk-adjusted metric in both windows (Sharpe, Sortino,
CVaR-ratio, Calmar, Martin), with LOWER CAGR, HIGHER vol, and (ext) deeper MaxDD.

## Selection effect size (clean / ext)

| Window | rebalances | n_pos=4 fires | n_pos=4 freq | MCA != MIN-VAR triplet | divergence rate | avg Jaccard |
|--------|-----------:|--------------:|-------------:|-----------------------:|----------------:|------------:|
| clean  | 217        | 143           | 65.9%        | 92                     | 64.3%           | 0.678       |
| ext    | 327        | 206           | 63.0%        | 136                    | 66.0%           | 0.670       |

The swap is HIGHLY active: the selector fires ~64% of rebalances and MCA picks a
DIFFERENT triplet ~65% of the time it fires (Jaccard ~0.67, i.e. typically swaps
one of the three names). So the negative net result is not a "no-op that rarely
bites" -- it is a real, frequent, and consistently slightly-worse choice.

## Bull-window participation (clean) -- hypothesis test

| Window           | sel    | Sharpe | CAGR   | vol    | MaxDD   |
|------------------|--------|-------:|-------:|-------:|--------:|
| 2013-2019        | MIN-VAR| 1.2355 | 9.08%  | 7.30%  | -9.66%  |
| 2013-2019        | MCA    | 1.1008 | 8.25%  | 7.54%  | -10.67% |
| 2023-2025        | MIN-VAR| 1.0480 | 10.15% | 9.73%  | -10.71% |
| 2023-2025        | MCA    | 1.0435 | 10.49% | 10.11% | -11.00% |

Hypothesis NOT supported. In 2013-2019 MCA LOWERS bull participation (CAGR
9.08% -> 8.25%, Sharpe 1.24 -> 1.10, deeper DD). In 2023-2025 MCA nudges CAGR up
(+0.34pp) but with higher vol and deeper DD, so Sharpe is flat-to-worse. There is
no clean "keep the momentum winners" bull benefit; the de-tilt premise does not
translate into better equity participation here.

## Per-crisis (ext)

| Crisis           | sel    | Sharpe | Sortino | MaxDD   | CAGR    |
|------------------|--------|-------:|--------:|--------:|--------:|
| dotcom 2000-2002 | MIN-VAR| 0.965  | 1.382   | -8.66%  | 5.99%   |
| dotcom 2000-2002 | MCA    | 1.273  | 1.873   | -5.68%  | 8.24%   |
| GFC 2007-2009    | MIN-VAR| 0.815  | 1.198   | -13.14% | 11.06%  |
| GFC 2007-2009    | MCA    | 0.416  | 0.600   | -13.14% | 5.17%   |
| COVID 2020       | MIN-VAR| 0.177  | 0.237   | -10.20% | -0.31%  |
| COVID 2020       | MCA    | 0.188  | 0.252   | -10.20% | -0.80%  |
| Y2022            | MIN-VAR| 0.096  | 0.130   | -5.17%  | 0.78%   |
| Y2022            | MCA    | -0.180 | -0.241  | -7.01%  | -1.06%  |
| Y2025            | MIN-VAR| 0.800  | 1.187   | -10.70% | 9.93%   |
| Y2025            | MCA    | 0.957  | 1.426   | -11.00% | 12.37%  |

Mixed and offsetting: MCA helps in dotcom and Y2025 but hurts materially in GFC
(Sharpe 0.82 -> 0.42) and Y2022 (turns positive into negative). No consistent
crisis edge; the GFC degradation is the largest single move.

## Answers

- (a) CAGR / Sharpe / bull participation: NO. MCA lowers Sharpe (1.2557 ->
  1.1408 clean; 1.2549 -> 1.1774 ext), lowers CAGR, and does not improve bull
  participation (2013-2019 worse; 2023-2025 a wash). Hypothesis rejected at the
  sleeve level.
- (b) Turnover cost: YES, modestly higher. Annualized one-way turnover 3.55 ->
  3.95 (clean, +11%) and 3.41 -> 3.66 (ext, +7%). Consistent with Optimum3's
  correlation-reshuffling tax direction, though small in absolute terms.
- (c) Different assets: YES, frequently. Selector fires ~64% of rebalances and
  diverges ~65% of those (avg Jaccard ~0.67). The effect is real and active, not
  a rare edge case.
- (d) Risk profile: MCA runs HIGHER vol (10.28% -> 10.79% clean) and slightly
  deeper/equal MaxDD, with worse Calmar / Martin / CVaR-ratio. The "keep
  higher-vol momentum winners" mechanism shows up as more vol WITHOUT the
  hoped-for return compensation.
- (e) Net: MCA is WORSE than min-variance for the CPM sleeve -- a consistent
  modest degradation in risk-adjusted terms, slightly more turnover, no bull
  benefit. Recommendation: DO NOT adopt; keep production min-variance 3-of-4.

## Caveats and confidence

- Single a-priori swap, no tuning -> low overfit risk on the variant itself; the
  negative verdict is therefore credible (we did not search for a flattering MCA
  variant). Confidence MEDIUM-HIGH that MCA is not an improvement; the gap is
  consistent in sign across clean, ext, bull, and most crises.
- Point-estimates only. The clean Sharpe gap (~0.115) is economically meaningful
  but a paired block bootstrap was NOT run (scope: skip unless compelling). Prior
  related work (`research/selection_mincorr_vs_minvar.py`, older STRICT-3 /
  inv-vol / 504d config) found min-corr a smaller wash-to-slightly-worse with CIs
  that did not exclude zero; under the CURRENT prod config (STRICT-4 / EW / 252d)
  the gap is LARGER and same-signed. If a confirmatory significance test is later
  wanted, a paired block bootstrap of dSharpe is the natural next step.
- Correlation estimated on a 4-asset candidate set, but selection is only
  4-choose-3 = 4 subsets, so the choice is numerically stable (estimation error
  small). PIT integrity preserved: corr matrix uses data up to sig_d only, T+1
  MOO execution, lagged matrix.
- Cached frozen dataset (load_panel + open-cache); results are dataset-conditional.

## Artifacts

- Harness/run: `research/cpm_mca_vs_minvar_run.py`
- Numbers: `research/cpm_mca_vs_minvar_findings.json`
