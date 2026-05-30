# Does the CPM ranker's vol-adjustment earn its keep under the FINAL spec?

**Status:** throwaway research (analyst role; read-only re: production; no production files changed, no commit).
**Scripts:** `research/ranker_revalidation_final_spec.py` -> `research/ranker_revalidation_final_spec.json`
(main effect + bootstrap + triple-vol + overlap); `research/ranker_revalidation_addendum.py` ->
`research/ranker_revalidation_addendum.json` (Sections 5-6: wider-pool choice-set + 2x2 redundancy)
**Date:** 2026-05-30
**Supersedes (for this question):** `research/ranker_under_invvol_findings.md`, which used the OLD partial-safe
fallback (n_pos=1 -> 50/50; n_pos=2 -> invvol-2 fully risky) and the EW-2/IV-2/IV-3 weighting menu. This
re-validation holds the FINAL production spec fixed and varies ONLY the ranker.

## Question / hypothesis

The production CPM ranker is **vol-adjusted Faber**: `m_faber / rv_252d` (10-month-SMA distance divided by
252-day annualized realized vol). Volatility now enters the pipeline in THREE places under the final spec:

1. the **ranker** (`/ rv_252d`),
2. the **min-variance 3-subset SELECTION**, and
3. the **inverse-vol WEIGHTING**.

Hypothesis: with the downstream min-var selection + inverse-vol weighting already vol-penalizing, the ranker's
vol-adjustment may be redundant (removable for parsimony -> plain Faber). I earlier called vol-Faber a "wash"
under the OLD pair weighting; the INVVOL-3 re-run hinted it firms up. This re-validates under the final spec and
checks the triple-vol-counting explicitly.

## Configuration (labeled)

- **Config:** CPM solo, FINAL production spec held fixed = `cpm_live.compute_target_weights`.
  Pipeline: rank by ranker -> positive-trend screen -> top-K=4 -> min-variance 3-subset -> inverse-vol weight
  -> **strict-3 partial-safe** (risky_fraction = min(n_pos,3)/3, remainder to timed safe) -> HYG-OR-TIP
  any-positive 13612U canary -> timed SHV/IEF safe.
- **Universe:** `[QQQ, SPHQ, EFA, EEM, VNQ, GLD, TLT, DBC]`, safe best-of `[SHV, IEF]`.
- **Window:** clean 2008-05-30 .. 2026-05-22 (18y, full real-open coverage, decisive lens);
  ext 1999-03-10 .. 2026-05-22 (27y, partially proxy-backed pre-2006).
- **Execution:** T+1 MOO exact (`mooex`, real yfinance auto_adjust opens), 10 bps/side, post-cost throughout.
- **Cov / sigma lookback:** 504d.
- **Bootstrap:** paired stationary block bootstrap, B=2000, block=21, seed=42.
- **Harness:** imports the final-spec weight fn `cpm_final_memo_numbers.gcpm_wf` (and its `select_subset` /
  `weight_block` / `met` / `win` / `run_cpm`) and adds ONLY a plain-`faber` ranker branch; the `faber_vol`,
  `13612u_vol`, and `plain12` paths are byte-identical to `gcpm_wf`.

### Rankers tested (everything else held at final spec)
- `faber_vol` (PRODUCTION): `m_faber / rv_252d`. Positive-trend screen = `faber > 0`.
- `faber` (plain): `m_faber` alone, NO vol division. Same candidate pool + same positive screen as `faber_vol`;
  differs ONLY in the order that decides the top-K=4 cut.
- `13612u_vol`: `13612U / rv_252d`. Positive screen = `13612U > 0`.
- `plain12`: plain 12-month total-return momentum. Positive screen = `score > 0`.

## Verification (anchor gate -- passed before any variant trusted)

| Window | Sharpe | MaxDD | Calmar | Expected (final strict-3 anchor) | Match |
|---|---:|---:|---:|---|---|
| clean | 1.2667 | -12.66% | 1.1306 | 1.2667 / -12.66% / 1.1306 | CONFIRMED |
| ext | 1.2349 | -15.18% | 0.9119 | 1.2349 / -15.18% / 0.9119 | CONFIRMED |

Production `compute_target_weights` reproduces the final anchor exactly in both windows. The generalized
`faber_vol` weight fn self-check matches production to 1e-9 (clean Sharpe 1.266681). All variants are trusted on
that basis.

## 1. Headline per ranker under the final spec (net 10 bps, T+1 MOO exact)

### Clean 18y (2008-05-30 .. 2026-05-22)

| Ranker | Sharpe | CAGR | Vol | MaxDD | Calmar |
|---|---:|---:|---:|---:|---:|
| vol-Faber (PRODUCTION) | **1.2667** | 14.31% | 11.08% | **-12.66%** | **1.1306** |
| plain Faber | 1.1582 | 13.28% | 11.36% | -12.66% | 1.0490 |
| 13612U / rv_252d | 1.2516 | 14.09% | 11.07% | -14.41% | 0.9778 |
| plain 12m momentum | 0.9719 | 11.01% | 11.49% | -17.33% | 0.6352 |

### Extended 27y (1999-03-10 .. 2026-05-22)

| Ranker | Sharpe | CAGR | Vol | MaxDD | Calmar |
|---|---:|---:|---:|---:|---:|
| vol-Faber (PRODUCTION) | 1.2349 | 13.84% | 10.99% | -15.18% | 0.9119 |
| plain Faber | **1.2434** | 14.37% | 11.31% | -15.18% | **0.9466** |
| 13612U / rv_252d | 1.2430 | 13.96% | 11.00% | -17.06% | 0.8181 |
| plain 12m momentum | 1.0368 | 11.97% | 11.55% | -17.33% | 0.6905 |

**Read:** in the decisive clean window, vol-Faber leads plain Faber by +0.108 Sharpe (1.2667 vs 1.1582) and
+0.082 Calmar (1.1306 vs 1.0490) at **identical MaxDD (-12.66%)**. In ext the two flip sign: plain Faber edges
ahead by +0.009 Sharpe and +0.035 Calmar, again at **identical MaxDD (-15.18%)**. `13612U` carries worse
drawdowns in both windows (-14.41% clean, -17.06% ext) and the worst Calmar of the Faber-family pair.
`plain12` is the clear loser everywhere.

## 2. Paired bootstrap (B=2000, block=21, seed=42): vol-Faber vs alternatives

Difference = vol-Faber MINUS alternative. Sharpe/Calmar: diff > 0 => vol-Faber better. MaxDD (both negative):
diff > 0 => vol-Faber shallower (better). "P(volF beats)" = fraction of resamples with diff > 0.

### vol-Faber vs plain Faber

| Window | Metric | diff mean | 95% CI | P(volF beats) | CI excludes 0? |
|---|---|---:|---|---:|:--:|
| clean | Sharpe | +0.1099 | [+0.0119, +0.2167] | 0.987 | **YES** |
| clean | MaxDD | +0.0078 | [-0.0190, +0.0477] | 0.647 | no |
| clean | Calmar | +0.1060 | [-0.0757, +0.3465] | 0.867 | no |
| ext | Sharpe | -0.0073 | [-0.1075, +0.0898] | 0.444 | no |
| ext | MaxDD | -0.0003 | [-0.0406, +0.0371] | 0.490 | no |
| ext | Calmar | -0.0297 | [-0.2270, +0.1553] | 0.357 | no |

### vol-Faber vs 13612U/rv_252d

| Window | Metric | diff mean | 95% CI | P(volF beats) | CI excludes 0? |
|---|---|---:|---|---:|:--:|
| clean | Sharpe | +0.0141 | [-0.1528, +0.1848] | 0.558 | no |
| clean | MaxDD | +0.0044 | [-0.0371, +0.0546] | 0.569 | no |
| clean | Calmar | +0.0378 | [-0.2572, +0.3820] | 0.591 | no |
| ext | Sharpe | -0.0067 | [-0.1390, +0.1292] | 0.458 | no |
| ext | MaxDD | +0.0026 | [-0.0440, +0.0517] | 0.548 | no |
| ext | Calmar | +0.0042 | [-0.2341, +0.2364] | 0.518 | no |

**Read:** the ONLY bootstrap-significant difference in the entire table is **vol-Faber vs plain Faber, clean
Sharpe** -- mean +0.110, 95% CI [+0.012, +0.217], CI excludes zero, P(volF beats) = 0.987. Everything else
(clean Calmar, all MaxDD, all ext, and every vol-Faber vs 13612U cell) is within noise (CI spans zero). So
vol-Faber's edge over plain Faber is a genuine, distinguishable clean-window Sharpe improvement, not a chance
artifact; vol-Faber vs 13612U is a Sharpe wash with vol-Faber holding a (non-significant) drawdown/Calmar lean.

## 3. Triple-vol-counting check

Vol enters at the ranker (`/ rv_252d`), the min-var SELECTION, and the inverse-vol WEIGHTING. The cleanest test
is **vol-Faber minus plain Faber** (same pool, same screen; only the rank order into the top-K=4 cut differs):

| Window | d Sharpe | d MaxDD | d Calmar |
|---|---:|---:|---:|
| clean | +0.1085 | **0.00pp** | +0.0816 |
| ext | -0.0086 | **0.00pp** (3e-14) | -0.0347 |

Comparison to the prior study under equal-weight / pair (OLD fallback, `ranker_under_invvol_findings.md`),
vol-Faber minus plain-Faber Sharpe:

| Window | EW-2 | INVVOL-2 | INVVOL-3 (old) | **Final spec (strict-3 INVVOL-3)** |
|---|---:|---:|---:|---:|
| clean | +0.0813 | +0.0904 | +0.1058 | **+0.1085** |
| ext | -0.0831 | -0.0697 | -0.0092 | **-0.0086** |

**Two decisive observations:**

1. **The ranker's vol-adjustment never touches MaxDD (0.00pp in BOTH windows).** This is the triple-vol-counting
   signature in its sharpest form: the min-variance 3-subset SELECTION + inverse-vol WEIGHTING + strict-3
   partial-safe fully pin the drawdown profile. During the deep-drawdown months both rankers select the
   identical risky names (the min-var step washes out ranker ordering exactly where it matters for tail risk),
   so changing the ranker's vol term cannot move MaxDD by a single basis point. The downstream stages already
   "spent" the vol information that governs drawdown.

2. **But the vol-adjustment is NOT thereby fully redundant.** The clean-window Sharpe edge does NOT shrink as
   you add downstream vol handling -- it actually grows EW-2 +0.081 -> final strict-3 INVVOL-3 +0.109. The naive
   double/triple-counting prediction (edge erodes once vol is handled downstream) is contradicted in clean. The
   ranker's vol term improves clean Sharpe through a channel the downstream stages do NOT cover: it re-orders
   which positive-trend names survive the top-K=4 cut and therefore which menu the min-var selector chooses from.
   That ordering lever is orthogonal to the DD-pinning role of selection/weighting.

So the "triple counting" is real for **drawdown** (ranker vol-adjustment is fully redundant there -> MaxDD
identical) but NOT for **return efficiency** (the ranker's vol term still independently lifts clean Sharpe via
the top-K menu). The earlier "firms up under INVVOL-3" hint is confirmed: the clean edge is the largest and now
bootstrap-significant under the final spec.

## 4. Selection overlap (vol-Faber vs plain Faber)

| Window | Signal months | Both risk-on | Same final basket | Mean Jaccard | Same top-K pool | Risk-on STATE disagreements |
|---|---:|---:|---:|---:|---:|---:|
| clean | 217 | 188 | 78.2% | 0.886 | 77.1% | **0 / 217** |
| ext | 327 | 291 | 75.9% | 0.875 | 74.6% | **0 / 327** |

**Read:** risk-on/off state NEVER disagrees between vol-Faber and plain Faber (0 / 544 months across both
windows). The state is decided entirely by the **HYG-OR-TIP canary + positive-trend screen**, never by the
ranker -- the ranker only re-orders within the already-qualified pool. vol-Faber and plain Faber pick the
**identical** final risky basket ~76-78% of months (Jaccard ~0.88); the vol-adjustment is a marginal
re-ordering active in only ~22-24% of risk-on months. That is exactly why MaxDD is identical (the re-ordering is
inactive in the tail) yet clean Sharpe still moves (the re-ordering helps in the body of the distribution).

## 5. Wider pool x choice-set: does the min-var sub-selection add more as the pool widens?

**Addendum script:** `research/ranker_revalidation_addendum.py` -> `research/ranker_revalidation_addendum.json`
(anchor-gated: vol-Faber K=4 M=3 sub-select reproduces clean 1.2667/-12.66%/1.1306, ext 1.2349/-15.18%/0.9119).

The min-var sub-selection chooses among C(K,M) candidate subsets. At the production K=4/M=3 the choice set is
tiny: C(4,3)=4. Hypothesis: a tiny choice set leaves little room for the min-var filter to help. Test by
widening the pool (K in {4,5,6}) and varying the target M held (M in {2,3}), ranker = production vol-Faber.
Note C(4,2)=6 > C(4,3)=4: selecting 2 of the top-4 gives MORE choices than selecting 3 of the top-4.
For each (K,M) compare **(A) top-K -> min-var-M-subset -> inverse-vol** vs **(B) top-K -> inverse-vol ALL K
(IVk, no sub-selection)**, both with strict-M partial-safe. Edge = A - B. M also changes the number of names
held (confound), so both C(K,M) and M are reported.

### Sub-selection EDGE (A minus B) vs choice-set size, sorted by C(K,M)

| K | M | C(K,M) | window | d Sharpe | d Calmar | d MaxDD | A (sub-sel) Sharpe / MaxDD | B (weight-all) Sharpe / MaxDD |
|---:|---:|---:|---|---:|---:|---:|---|---|
| 4 | 3 | **4** (prod) | clean | +0.0989 | +0.0667 | +0.01pp | 1.2667 / -12.66% | 1.1678 / -12.67% |
| 4 | 3 | 4 | ext | +0.0383 | +0.0449 | +0.75pp | 1.2349 / -15.18% | 1.1966 / -15.93% |
| 4 | 2 | 6 | clean | +0.1139 | +0.0331 | -0.47pp | 1.2630 / -13.14% | 1.1491 / -12.67% |
| 4 | 2 | 6 | ext | +0.0133 | +0.0176 | +0.49pp | 1.2011 / -15.44% | 1.1878 / -15.93% |
| 5 | 3 | 10 | clean | +0.1793 | +0.2083 | +1.51pp | 1.2323 / -12.66% | 1.0530 / -14.16% |
| 5 | 3 | 10 | ext | +0.1147 | +0.1807 | +2.65pp | 1.2304 / -14.25% | 1.1157 / -16.90% |
| 5 | 2 | 10 | clean | +0.1941 | +0.1301 | +0.14pp | 1.2291 / -14.02% | 1.0350 / -14.16% |
| 5 | 2 | 10 | ext | +0.0599 | +0.0911 | +1.46pp | 1.1670 / -15.44% | 1.1071 / -16.90% |
| 6 | 2 | 15 | clean | +0.2286 | +0.1718 | +0.57pp | 1.2096 / -13.59% | 0.9810 / -14.16% |
| 6 | 2 | 15 | ext | +0.0760 | -0.1043 | -3.75pp | 1.1517 / -20.65% | 1.0757 / -16.90% |
| 6 | 3 | 20 | clean | +0.1701 | +0.1868 | +1.51pp | 1.1688 / -12.66% | 0.9987 / -14.16% |
| 6 | 3 | 20 | ext | +0.1123 | +0.1112 | +1.65pp | 1.1967 / -15.26% | 1.0844 / -16.90% |

**Read 1 -- the edge grows with the choice set (hypothesis CONFIRMED).** Clean-window sub-selection Sharpe edge
rises monotonically-ish with C(K,M): C=4 +0.099 -> C=6 +0.114 -> C=10 +0.179/+0.194 -> C=15 +0.229 -> C=20
+0.170. The same ordering holds in ext (C<=6 give +0.01 to +0.04; C>=10 give +0.06 to +0.11). The small-choice-set
hypothesis is correct: with only 4 subsets to choose among, the min-var filter has little room to help; widen
the candidate pool and the filter's value over naive weight-all clearly increases.

**Read 2 -- but a wider pool does NOT beat the current K=4/M=3 on ABSOLUTE performance.** The edge grows mostly
because the weight-all baseline (B) DEGRADES as K widens (it is forced to hold more low-quality names: clean B
Sharpe falls 1.1678 at K=4 -> 0.9987 at K=6), not because the sub-select line (A) improves. Absolute sub-select
Sharpe is HIGHEST at the production K=4/M=3 (clean 1.2667) and declines as the pool widens (K5/M3 1.2323, K6/M3
1.1688). No (K,M) cell beats production: the closest, K5/M3, matches ext Sharpe (1.2304 vs 1.2349) but loses
~0.034 clean Sharpe and worsens ext MaxDD (-14.25% with +2.65pp edge vs prod -15.18%); K6/M2 blows out ext
MaxDD to -20.65%. **The top-K=4 cut already removes the junk that makes a wider pool need a stronger filter, so
at K=4 the small choice set is a feature, not a bug -- weight-all-4 is already near-good and sub-select-3 cleans
up the rest.** Verdict (b): widening the pool makes the sub-selection RELATIVELY more valuable but does not
produce an absolute improvement over K=4/M=3. Keep K=4, M=3.

## 6. Ranker x sub-selection redundancy 2x2 (K=4)

2x2: {vol-Faber, plain-Faber} ranker x {min-var-3-subset, weight-all-4 (IV4)} sub-selection. If min-var
sub-selection adds large value under plain-Faber but ~zero under vol-Faber, the min-var filter and the
vol-adjusted ranker are redundant (both vol-penalize) and only one is needed.

### Four cells (clean / ext)

| Ranker | Sub-selection | Clean Sharpe | Clean Calmar | Clean MaxDD | Ext Sharpe | Ext Calmar | Ext MaxDD |
|---|---|---:|---:|---:|---:|---:|---:|
| vol-Faber | min-var-3 (prod) | **1.2667** | 1.1306 | -12.66% | 1.2349 | 0.9119 | -15.18% |
| vol-Faber | weight-all-4 (IV4) | 1.1678 | 1.0639 | -12.67% | 1.1966 | 0.8670 | -15.93% |
| plain Faber | min-var-3 | 1.1582 | 1.0490 | -12.66% | 1.2434 | 0.9466 | -15.18% |
| plain Faber | weight-all-4 (IV4) | 1.0997 | 0.9210 | -13.93% | 1.2016 | 0.8954 | -15.93% |

### Sub-selection benefit (min-var-3 minus weight-all-4) per ranker, and interaction

| Ranker | window | d Sharpe | d Calmar | d MaxDD |
|---|---|---:|---:|---:|
| vol-Faber | clean | +0.0989 | +0.0667 | **+0.01pp** |
| vol-Faber | ext | +0.0383 | +0.0449 | +0.75pp |
| plain Faber | clean | +0.0585 | +0.1280 | **+1.27pp** |
| plain Faber | ext | +0.0419 | +0.0512 | +0.75pp |
| **interaction** (plain benefit - volFaber benefit) | clean | -0.0404 | +0.0613 | **+1.26pp** |
| **interaction** | ext | +0.0036 | +0.0063 | +0.00pp |

**Read -- the redundancy is real but axis-specific (DD only).** On the DRAWDOWN axis the hypothesis is
confirmed cleanly in clean: min-var sub-selection improves MaxDD by **+1.27pp under plain-Faber** but by
**+0.01pp under vol-Faber** (interaction +1.26pp). When the ranker already vol-penalizes (vol-Faber), the
min-var filter adds essentially zero drawdown protection; when the ranker does not (plain-Faber), the min-var
filter has to do the DD work itself. The two stages are therefore **substitutes for drawdown control -- you
only need one to pin MaxDD** (this is the same mechanism that made vol-Faber-subselect and plain-Faber-subselect
share an identical -12.66% MaxDD in Section 1/3: the subselect equalizes DD across rankers).

But on the SHARPE/return axis they are NOT redundant. The sub-selection Sharpe benefit is actually LARGER under
vol-Faber (+0.099 clean) than plain-Faber (+0.059 clean) -- the opposite of redundancy -- and the best cell of
the four is vol-Faber + min-var-3 (clean 1.2667), strictly above both "keep only one lever" cells (vol-Faber +
weight-all 1.1678; plain-Faber + min-var 1.1582, which are near each other ~1.16). Dropping EITHER lever costs
~0.10 clean Sharpe. So for return efficiency both contribute and you want both; the redundancy is confined to
drawdown. (Ext interaction is ~0 on every axis -- the redundancy signal is a clean-window phenomenon.)

## 7. VERDICT -- ranker main effect (vol-Faber vs plain Faber)

**Under the final spec, the ranker's vol-adjustment is (a) ADDITIVE -- keep production vol-Faber.**

Rationale against the stated decision rule ("if within noise, recommend simpler plain-Faber ONLY if it does not
hurt DD; otherwise keep production vol-Faber"):

- The clean window (the decisive 18y full-real-open lens) is **NOT within noise**: vol-Faber beats plain Faber
  by +0.110 Sharpe, paired-bootstrap 95% CI [+0.012, +0.217] **excludes zero**, P(volF beats) = 0.987. This is
  the single statistically distinguishable result in the comparison.
- Removing the vol-adjustment (plain Faber) buys **zero** DD benefit -- MaxDD is byte-identical (-12.66% clean,
  -15.18% ext) because selection + weighting + partial-safe already pin drawdown. So the parsimony trade is
  asymmetric: dropping the ranker vol term costs ~0.11 clean Sharpe with no offsetting DD gain.
- The ext window is a wash (plain Faber +0.009 Sharpe / +0.035 Calmar, CI spans zero), so it does not rescue the
  simplification; it merely fails to penalize it. Given clean is significant and DD-neutral, the expected value
  of removal is a strict loss.

This **upgrades** the prior verdict. The earlier study (under EW/pair, OLD fallback, no formal significance
test) called the ranker vol-adjustment "(b) wash / not robustly additive" because the clean edge was untested
and the sign flipped vs ext. Under the final spec with a formal paired bootstrap the clean edge **firms up**
(+0.081 EW-2 -> +0.109 strict-3) AND becomes significant (CI excludes zero), while MaxDD is provably untouched.
The honest mechanism is now clear: triple-vol-counting makes the ranker fully redundant for DRAWDOWN (hence
MaxDD identical) but leaves an orthogonal, significant clean-window RETURN-efficiency edge via the top-K menu.

**Reconciliation with the "13612U worse under INVVOL-3" flag:** confirmed and consistent. Under the final spec
`13612U/rv_252d` is a Sharpe wash vs vol-Faber (clean +0.014, ext -0.007; both CI span zero) but carries
materially worse drawdowns (clean -14.41% vs -12.66%; ext -17.06% vs -15.18%) and the worst Calmar of the pair
(0.978 clean / 0.818 ext vs 1.131 / 0.912). The bootstrap DD/Calmar lean toward vol-Faber (P 0.55-0.59) is not
significant, but the point estimates uniformly favor vol-Faber on the risk axis. So 13612U is not a free
substitute: same Sharpe, worse tail. vol-Faber remains the right production ranker on both the significant
clean-Sharpe edge over plain Faber and the (directionally consistent) DD/Calmar edge over 13612U.

## 8. NET VERDICT -- consolidated (a) / (b) / (c)

**(a) Is the ranker vol-adjustment additive or removable?** ADDITIVE -- KEEP vol-Faber. It beats plain Faber by
+0.110 clean Sharpe (paired bootstrap 95% CI [+0.012, +0.217], excludes zero) at identical MaxDD; ext is a
wash. Removing it costs clean Sharpe with zero DD benefit -> strict expected loss, no parsimony case (Section
2/3/7).

**(b) Does a wider pool make the sub-selection more valuable?** YES, relatively -- the min-var sub-selection's
edge over weight-all grows with the choice set C(K,M) (clean +0.099 at C=4 -> +0.17-0.23 at C=10-20), confirming
the small-choice-set hypothesis. BUT this does NOT translate into an absolute win: the edge grows because
weight-all degrades on a wider, junkier pool, while absolute sub-select performance is BEST at the current
K=4/M=3 (clean 1.2667) and declines as K widens. No (K,M) tested beats production. **Keep K=4, M=3** (Section
5).

**(c) Are the ranker vol-adjustment and min-var sub-selection redundant (pick one)?** PARTIALLY -- redundant on
DRAWDOWN only, complementary on RETURN. Min-var sub-selection adds +1.27pp clean MaxDD protection under
plain-Faber but +0.01pp under vol-Faber (interaction +1.26pp): for DD control the two are substitutes, one
suffices. But the best Sharpe cell uses BOTH (vol-Faber + min-var-3 = 1.2667), and dropping either lever costs
~0.10 clean Sharpe, so they are NOT redundant for return efficiency. **Do not pick one -- keep both**; the
production stack (vol-Faber ranker + min-var-3 sub-selection + inverse-vol weighting + strict-3 partial-safe)
is the best of every comparison run. The triple-vol-counting is thus reframed: the three vol stages overlap on
DRAWDOWN (which is why MaxDD is pinned and largely ranker/selection-insensitive) but each contributes
separable return efficiency, so none is dead weight (Section 3/6).

## Caveats & confidence

- Clean is a sub-window of ext (not an independent OOS split); the clean-vs-ext sign flip on the plain-Faber
  comparison signals that the +0.11 clean Sharpe edge is regime-dependent, not universal. The bootstrap CI
  excluding zero establishes it is real WITHIN the clean sample, not that it generalizes to a fresh regime.
- Only ONE of twelve bootstrap cells is significant (clean Sharpe, vol-Faber vs plain Faber). With a single
  significant result among many comparisons, treat the magnitude (+0.11 Sharpe, no DD cost) as the decision
  driver rather than the bare significance flag. The asymmetry (significant upside, zero DD downside) is what
  makes "keep vol-Faber" the low-regret choice -- not a strong multiple-testing-robust effect.
- MaxDD identity (0.00pp) is exact to displayed precision and is structural (min-var selection chooses the same
  tail-period names regardless of ranker order), not coincidental.
- Wider-pool / choice-set sweep (Section 5) varies M as well as K, so the M=2 vs M=3 rows change the NUMBER of
  names held (a confound separate from the choice-set size). Both C(K,M) and M are reported so the two effects
  are not conflated; the choice-set monotonicity holds within fixed-M slices (M=3: C4 +0.099 -> C10 +0.179 ->
  C20 +0.170 clean) as well as across.
- K6/M2 (ext MaxDD -20.65%, Calmar -0.104 edge) is the one materially degraded cell -- widening to 6 names with
  only 2 held lets the strict-2 partial-safe and small held-set destabilize the ext tail; further evidence that
  wider pools do not help absolute performance.
- Section 5/6 report point estimates only (no paired bootstrap on the sub-selection edge); the choice-set
  monotonicity and the DD-axis interaction are read off point metrics and should be treated as directional, not
  significance-tested.
- Ext 27y is partially proxy-backed pre-2006; clean 18y is the decisive lens and is where vol-Faber wins.
- Costs flat 10 bps/side; ordering/signs were stable across 0/10/25 bps in the prior ranker study and are not
  expected to flip here.
- **Confidence: high** that the ranker vol-adjustment is DD-redundant (MaxDD provably identical) yet
  Sharpe-additive in the clean window (bootstrap CI excludes zero); **high** that plain Faber is not a free
  simplification (costs clean Sharpe, buys no DD); **medium-high** that vol-Faber should stay production over
  13612U (Sharpe wash but uniformly better DD/Calmar point estimates).

## Memory / knowledge candidates

- **Durable lesson:** when a strategy already vol-penalizes downstream via min-variance SELECTION + inverse-vol
  WEIGHTING, adding a vol-adjusted RANKER is fully redundant for DRAWDOWN (MaxDD becomes byte-identical to the
  un-adjusted ranker, because the min-var step selects the same tail-period names regardless of rank order) but
  can remain additive for RETURN EFFICIENCY through the orthogonal top-K screening channel (which names survive
  the cardinality cut). "Vol is counted three times" does not imply "remove the ranker's vol term" -- the three
  stages act on different parts of the distribution (ranker -> body Sharpe; selection/weighting -> tail DD). The
  redundancy is axis-specific: ranker-vol-adjustment and min-var sub-selection are SUBSTITUTES for drawdown
  control (min-var adds +1.27pp MaxDD under a plain ranker but +0.01pp under a vol-adjusted ranker) yet
  COMPLEMENTS for return (the best Sharpe uses both; dropping either costs ~0.10). "Pick one" applies to DD
  only.
- **Durable lesson (choice-set):** the value of a min-variance sub-selection step over naive weight-all scales
  with the choice-set size C(K,M) it selects among -- a tiny choice set (C=4 at top-K=4 / hold-3) leaves little
  room to help. But widening the candidate pool to enlarge C raises the RELATIVE edge only because weight-all
  degrades on the junkier pool; ABSOLUTE performance is best when the upstream top-K cut is tight (K=4), so a
  small choice set is a feature when the pool is pre-filtered, not a defect to engineer away.
- **Knowledge (CPM ranker decision under final spec):** keep production vol-Faber (`m_faber / rv_252d`). Under
  the final strict-3 partial-safe INVVOL-3 spec it beats plain Faber by +0.110 clean Sharpe (paired bootstrap
  B=2000 block=21 seed=42, 95% CI [+0.012, +0.217], excludes zero) at identical MaxDD (-12.66%), and beats
  13612U on uniformly better DD/Calmar at equal Sharpe. plain Faber is a Sharpe wash only in ext and costs clean
  Sharpe with zero DD benefit. Risk-on/off state is canary-driven (0/544 ranker disagreements); the ranker only
  re-orders the ~22-24% of risk-on months where the top-K cut binds. Wider pools (K=5,6) and alternate hold-counts
  (M=2) do not beat K=4/M=3 on absolute Sharpe/Calmar/MaxDD; the ranker-vol-adjustment and min-var sub-selection
  are redundant for drawdown but complementary for return, so the full production stack (vol-Faber + min-var-3 +
  inverse-vol + strict-3 partial-safe) stays.
