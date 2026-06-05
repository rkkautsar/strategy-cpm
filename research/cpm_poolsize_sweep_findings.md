# CPM pool-size sweep: does widening the candidate pool (keep holding count) beat prod?

Status: throwaway research. Read-only re production. No production files changed; no commit.

## Question / hypothesis

The user's idea: "widen the candidate rank pool, drop the redundant one, but KEEP
the holding count." This decouples DIVERSIFICATION (pool width) from CONCENTRATION
(number of holdings), so any gain would be pure diversification rather than fewer
holdings.

Prod = top-4 of the 8-asset universe (TOP_K_CANDIDATES=4), rank by vol-adjusted
Faber, inverse-vol weight, strict-4 partial-safe. Correlation enters nowhere.

Primary test (4-of-5): widen the rank pool to top-5, then pick 4 by MIN-VAR subset
(vol+corr) so the holding count stays 4 (same concentration as prod, wider/more-
diverse pick). Compared against the prior 3-of-4 min-var winner, rank-only controls
at each holding count, a corr-only drop-1, and a 5-of-6 config.

## Method

- Harness: `research/cpm_harness.py` (mooex T+1 MOO exact, 10 bps/side, both-252,
  clean 2008-05-30.. / ext 1999-03-10..). `verify_anchor` PASSED first
  (Sharpe 1.1658, MaxDD -12.97%, Calmar 1.0137).
- Script: `research/cpm_poolsize_sweep.py` (reuses `cpm_weighting_corr`
  `_min_var_subset` / `_risky_weights` / `run_cell` / `paired_block_bootstrap` /
  CRISES, and `cpm_simple_corr_selection` `_drop_redundant_1` / `_min_corr_trio`).
- Everything held byte-identical to prod except (pool_k, hold_n, selection,
  sizing): universe / canary HYG,TIP any-positive / trend / SHV,IEF safe /
  both-252 cov / positive-Faber filter all unchanged.
- Bootstrap: paired block (B=2000, block=21) on clean returns. Walk-forward:
  3 sequential thirds of the clean window.

### Risky-fraction (partial-safe) semantics -- stated choice

PRIMARY = FULL-RISK RENORMALIZE: when the rank pool yields >= hold_n positive-Faber
names, hold exactly hold_n at full risk (risky_fraction = 1.0, weights renormalized
over held names). When positives < hold_n (rare transition months), hold all
positives at prod strict-4 partial-safe (risky = min(n_pos,4)/4, inject safe).

This makes PROD reproduce the anchor exactly, and makes 3of4_minvar identical to
the prior 3-of-4 min-var winner (full-risk-on-drop). It isolates DIVERSIFICATION
(which names) from DE-RISKING (how much risk). The PARTIAL-SAFE alternative
(risky = min(hold_n,4)/4 always; 3-of-4 -> 0.75 risky + 0.25 safe) is also run and
flagged `_psafe`. For 4-of-5 and 5-of-6 the two modes coincide in the common case
(hold>=4 -> risky 1.0), so only 3-of-4 differs.

## Results

### Sweep table (clean = DECISION window; ext; annualized turnover, net 10 bps)

| config | clean Sharpe | clean Calmar | clean Martin | clean MaxDD | ext Sharpe | ext Calmar | turnover |
|---|---|---|---|---|---|---|---|
| PROD (top-4/8, inv-vol) | 1.1658 | 1.014 | 3.691 | -12.97% | 1.2004 | 0.857 | 2.58 |
| 4of5 min-var inv-vol | 1.1466 | 1.028 | 3.025 | -11.86% | 1.1862 | 0.921 | 2.64 |
| 4of5 min-var EW | 1.1187 | 0.876 | 3.069 | -13.97% | 1.1839 | 0.785 | 2.57 |
| 4of5 drop-1 (corr-only) inv-vol | 1.1087 | 0.959 | 3.022 | -12.41% | 1.1591 | 0.814 | 3.18 |
| 4of5 drop-1 (corr-only) EW | 1.0619 | 0.846 | 3.107 | -13.97% | 1.1277 | 0.782 | 3.07 |
| 4of5 rank (control) inv-vol | 1.1658 | 1.014 | 3.691 | -12.97% | 1.2004 | 0.857 | 2.58 |
| 4of5 rank (control) EW | 1.1317 | 1.015 | 3.741 | -13.05% | 1.1868 | 0.872 | 2.44 |
| **3of4 min-var inv-vol** | **1.2414** | 1.053 | 3.712 | -13.18% | 1.2409 | 0.914 | 2.94 |
| 3of4 min-var EW | 1.2375 | 0.842 | 3.651 | -16.86% | 1.2650 | 0.814 | 2.89 |
| 3of4 rank (control) inv-vol | 0.9459 | 0.849 | 2.263 | -13.33% | 1.0367 | 0.785 | 3.23 |
| 3of4 rank (control) EW | 0.9295 | 0.682 | 2.260 | -16.86% | 1.0346 | 0.785 | 3.08 |
| 5of6 min-var inv-vol | 1.0313 | 0.877 | 2.870 | -12.25% | 1.1184 | 0.782 | 2.68 |
| 5of6 min-var EW | 0.9926 | 0.692 | 2.689 | -15.46% | 1.0923 | 0.653 | 2.64 |
| 5of6 rank (control) inv-vol | 1.0531 | 0.860 | 2.880 | -13.24% | 1.1214 | 0.785 | 2.57 |
| 5of6 rank (control) EW | 1.0051 | 0.732 | 2.779 | -15.46% | 1.0910 | 0.704 | 2.51 |
| **3of4 min-var inv-vol PARTIAL-SAFE** | **1.2631** | 1.079 | 3.762 | -10.23% | 1.2821 | 0.981 | 2.73 |

Notes:
- `4of5 rank == PROD` byte-for-byte. Taking the rank top-4 of the top-5 pool is
  identical to the rank top-4 of the whole universe. Widening the pool is a literal
  NO-OP unless the selection actively reaches into the wider pool. So any pool-width
  effect comes ENTIRELY through the min-var/corr selection swapping a higher-ranked
  name for a lower-ranked but more-diverse one.
- `4of5_minvar_psafe == 4of5_minvar` and `5of6_minvar_psafe == 5of6_minvar`
  (hold>=4 -> risky 1.0 in both modes). Only 3-of-4 splits.

### Paired bootstrap vs PROD (clean, B=2000)

| config | dSharpe [95% CI] | P(d>0) | dCalmar [95% CI] | P(d>0) |
|---|---|---|---|---|
| 4of5 min-var inv-vol | -0.019 [-0.124, +0.085] | 0.369 | -0.054 [-0.27, +0.15] | 0.261 |
| 4of5 min-var EW | -0.047 [-0.164, +0.074] | 0.220 | -0.077 [-0.31, +0.15] | 0.232 |
| 4of5 drop-1 inv-vol | -0.058 [-0.164, +0.052] | 0.155 | -0.088 [-0.31, +0.11] | 0.159 |
| **3of4 min-var inv-vol** | **+0.076 [-0.034, +0.185]** | **0.906** | +0.057 [-0.18, +0.29] | 0.709 |
| 3of4 min-var EW | +0.072 [-0.053, +0.199] | 0.860 | +0.057 [-0.26, +0.36] | 0.670 |
| **3of4 min-var inv-vol PARTIAL-SAFE** | **+0.099 [-0.029, +0.231]** | **0.923** | +0.065 [-0.22, +0.35] | 0.698 |
| 3of4 rank (control) | -0.221 [-0.354, -0.091] | 0.001 | -0.255 [-0.56, -0.03] | 0.013 |
| 5of6 min-var inv-vol | -0.135 [-0.258, -0.013] | 0.014 | -0.184 [-0.44, +0.02] | 0.036 |

### Head-to-head bootstraps

- 4of5 min-var vs 3of4 min-var (dSharpe = 4of5 - 3of4):
  IV -0.094 [-0.221, +0.038] P(d>0)=0.084; EW -0.119 [-0.258, +0.022] P=0.056.
  Keeping 4 holdings LOSES to dropping to 3 (directionally significant).
- min-var vs corr-only drop-1 at the wider 4of5 pool (dSharpe = minvar - drop1):
  IV +0.039 [-0.048, +0.129] P=0.802; EW +0.058 [-0.043, +0.161] P=0.871.
  vol+corr still beats corr-only, but both lose to prod.

### Walk-forward (3 sequential clean thirds), dSharpe vs PROD

| config | 2008-2014 | 2014-2020 | 2020-2026 |
|---|---|---|---|
| 4of5 min-var inv-vol | -0.006 | -0.168 | +0.100 |
| 3of4 min-var inv-vol | +0.099 | +0.024 | +0.097 |
| 3of4 min-var PARTIAL-SAFE | +0.154 | +0.071 | +0.064 |

4-of-5 is negative in 2 of 3 segments; 3-of-4 (both modes) is positive in all 3.

### Per-crisis Sharpe / MaxDD (ext curve)

| config | GFC | COVID | 2022 | 2025 |
|---|---|---|---|---|
| PROD | +0.541 / -11.9% | +1.191 / -10.5% | -0.299 / -8.0% | +0.240 / -13.0% |
| 4of5 min-var IV | +0.425 / -12.4% | +1.181 / -10.5% | -0.117 / -4.6% | +0.531 / -11.6% |
| 3of4 min-var IV | +0.720 / -13.9% | +1.015 / -12.2% | -0.114 / -6.2% | +0.516 / -11.4% |
| 3of4 min-var PARTIAL-SAFE | +0.783 / -11.2% | +1.367 / -10.1% | +0.019 / -4.7% | +0.510 / -8.4% |
| 5of6 min-var IV | +0.212 / -13.6% | +0.798 / -12.3% | -0.152 / -5.1% | +0.751 / -10.5% |

3of4 partial-safe is best or near-best in every crisis (only positive 2022 config,
shallowest GFC/COVID/2025 drawdowns).

## Answers to the key questions

(a) Does 4-of-5 (4 holdings, wider pool, min-var pick) BEAT prod?
NO. clean 1.1466 < prod 1.1658; ext 1.1862 < 1.2004; bootstrap dSharpe -0.019
[-0.124, +0.085] P(d>0)=0.369; negative in 2 of 3 walk-forward segments. PURE
diversification with concentration held fixed at 4 does NOT help -- it is a mild
(within-noise) HURT. The "widen the pool, keep the count" idea is refuted as a
prod beater.

(b) 4-of-5 vs the 3-of-4 min-var winner?
3-of-4 WINS. Head-to-head dSharpe = 4of5 - 3of4 is -0.094 (IV, P(d>0)=0.084) and
-0.119 (EW, P=0.056), directionally significant. Keeping 4 holdings (no
concentration penalty) does NOT preserve the edge -- it erases it. The
concentration to 3 is integral, NOT incidental.

(c) Parsimony sweet spot in the sweep?
3-of-4 min-var (hold 3, pool 4). Going wider (4-of-5, 5-of-6) monotonically
degrades: 5-of-6 is materially worse than prod (P(d>0)=0.014). The mechanism:
widening the rank pool only matters when the selection reaches DOWN-rank to a
weaker-momentum 5th/6th candidate for the sake of variance reduction; momentum
quality lost > variance gained. 3-of-4 stays inside prod's high-momentum top-4 and
just drops the most-redundant -- variance reduction for free, no momentum dilution.

(d) corr-only drop-1-of-5 vs min-var-4-of-5?
min-var beats corr-only (dSharpe +0.039 IV / +0.058 EW, P(d>0)~0.80-0.87), so
vol+corr still dominates corr-only at the wider pool -- consistent with the prior
study. But neither beats prod at the 4-holding (wider-pool) configuration.

## Verdict

NO keep-N-from-wider-pool config beats prod net cost + OOS. The user's "pure
diversification (widen pool, keep 4 holdings)" hypothesis is REFUTED: it is
within-noise WORSE than prod and significantly worse than the 3-of-4 min-var.

The decisive structural finding: pool-widening + rank selection is a no-op
(`4of5_rank == PROD` exactly). The only lever the wider pool offers is letting the
optimizer trade a high-momentum top-4 name for a lower-momentum, more-diverse 5th
name -- and that trade loses. The edge is "drop the redundant one from the EXISTING
top-4" (concentrate to 3), NOT "widen the candidate pool."

The 3-of-4 min-var remains the only configuration that beats prod (clean 1.2414
full-risk / 1.2631 partial-safe; P90-92 bootstrap; all 3 walk-forward segments
positive; both windows; strongest crisis profile, partial-safe variant). It is the
SIMPLER and BETTER winner than any wider-pool config.

Recommendation: DOCUMENT, do not adopt. The 3-of-4 min-var edge is real and robust
in sign but its bootstrap dSharpe 95% CI still spans 0 ([-0.034, +0.231]) -- a low
ceiling. min-var was historically dropped for parsimony; this sweep adds no reason
to revisit that, and positively rules OUT the wider-pool variants (4-of-5, 5-of-6)
as alternatives. Be honest: even the winner is within-noise on the strict paired
test; the case for it rests on directional consistency (windows + OOS + crises),
not a clean significance threshold.

## Caveats / confidence

- Single 8-asset universe, both-252 cov, monthly rebalance; bootstrap CIs are wide
  (low signal ceiling). Conclusions are about sign/direction + consistency, not
  p<0.05 significance.
- `4of5_rank == PROD` and `*_psafe == *` equalities are exact and serve as internal
  consistency checks (rank-top-4-of-5 = prod; risky 1.0 in both modes when hold>=4).
- 3-of-4 results reproduce the prior 3-of-4 study winner (partial-safe ~1.26),
  confirming harness/selection reuse is faithful.
- Confidence HIGH that 4-of-5 / wider-pool does NOT beat prod (consistent across
  metrics, windows, OOS, sizing). Confidence MODERATE that 3-of-4 min-var > prod
  (directionally robust, CI spans 0).

## Artifacts

- Script: `research/cpm_poolsize_sweep.py`
- Results JSON: `research/cpm_poolsize_sweep_findings.json`
- Run: `.venv/bin/python -m research.cpm_poolsize_sweep`
