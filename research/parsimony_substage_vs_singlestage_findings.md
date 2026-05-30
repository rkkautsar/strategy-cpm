# CPM parsimony: variance sub-selection (two-stage) vs single-stage top-K momentum

Does the variance-based **sub-selection** stage -- rank top-4 by vol-adjusted Faber momentum, then pick the lowest-variance 3-subset -- earn its second tunable knob over a **single-stage** design (top-K by momentum, inverse-vol weight all, no variance sub-select)?

**Convention (every table):** execution T+1 MOO exact (`mooex`, real auto_adjust opens); post-cost 10 bps/side; inverse-vol weighting; STRICT-3 partial-safe fallback (risky_fraction = min(n_pos,3)/3, remainder to timed SHV/IEF safe); cov lookback 504d; vol-adjusted Faber ranker; HYG-or-TIP canary. Clean window 2008-05-30..2026-05-22 (18y); extended 1999-03-10..2026-05-22 (27y).

Source harness: `research/parsimony_substage_vs_singlestage.py` (read-only; no production files touched). Selection primitives shared from `cpm_live`.

**Variants:**

| Key | Design | Knobs |
|---|---|---|
| PROD | two-stage: top-4 momentum -> min-variance 3-subset -> inverse-vol | K=4 + sub-select=3 |
| SINGLE-K3 | single-stage: top-3 momentum -> inverse-vol all 3 | K=3 |
| IV4 | single-stage: top-4 momentum -> inverse-vol all 4 | K=4 |
| SINGLE-K2 | single-stage: top-2 momentum -> inverse-vol all 2 | K=2 |
| SINGLE-K5 | single-stage: top-5 momentum -> inverse-vol all 5 | K=5 |

## 0. Anchor check (PROD reproduces strict-3 anchor)

| Window | Sharpe | MaxDD | Calmar | Expected | Match |
|---|---:|---:|---:|---|---|
| clean | 1.2667 | -12.66% | 1.1306 | 1.2667/-12.66%/1.1306 | CONFIRMED |
| ext | 1.2349 | -15.18% | 0.9119 | 1.2349/-15.18%/0.9119 | CONFIRMED |

## 1. Headline -- CPM-solo net metrics

**Clean (18y):**

| Variant | Sharpe | CAGR | Vol | MaxDD | Calmar |
|---|---:|---:|---:|---:|---:|
| PROD two-stage (top4->minvar3->invvol) | 1.2667 | 14.31% | 11.08% | -12.66% | 1.1306 |
| SINGLE-stage K=3 (top3->invvol) | 0.9472 | 11.41% | 12.26% | -13.22% | 0.8629 |
| SINGLE-stage K=4 / IV4 (top4->invvol) | 1.1678 | 13.47% | 11.43% | -12.67% | 1.0639 |
| SINGLE-stage K=2 (top2->invvol) | 0.7860 | 7.32% | 9.64% | -15.63% | 0.4682 |
| SINGLE-stage K=5 (top5->invvol) | 1.0530 | 11.63% | 11.08% | -14.16% | 0.8214 |

**Extended (27y):**

| Variant | Sharpe | CAGR | Vol | MaxDD | Calmar |
|---|---:|---:|---:|---:|---:|
| PROD two-stage (top4->minvar3->invvol) | 1.2349 | 13.84% | 10.99% | -15.18% | 0.9119 |
| SINGLE-stage K=3 (top3->invvol) | 1.0316 | 12.61% | 12.24% | -16.16% | 0.7802 |
| SINGLE-stage K=4 / IV4 (top4->invvol) | 1.1966 | 13.81% | 11.35% | -15.93% | 0.8670 |
| SINGLE-stage K=2 (top2->invvol) | 0.9162 | 8.89% | 9.82% | -15.63% | 0.5688 |
| SINGLE-stage K=5 (top5->invvol) | 1.1157 | 12.34% | 10.97% | -16.90% | 0.7300 |

## 2. Paired block bootstrap -- PROD vs SINGLE-K3 (B=2000, block=21, seed=42)

Difference is **(PROD minus SINGLE-K3)**, paired (identical block draws). `P(PROD beats)` = fraction of resamples PROD exceeds SINGLE-K3; for MaxDD, (PROD-SINGLE)>0 means PROD shallower (less negative) = more defensive.

**2a. PROD vs SINGLE-K3** (collapses BOTH knobs: K 4->3 AND drop sub-select):

*Clean (18y)*

| Metric (PROD-SINGLE) | mean | 95% CI | P(PROD beats) | CI excludes 0 |
|---|---:|---|---:|---|
| dSharpe | +0.3209 | [+0.1615, +0.4845] | 100.0% | YES |
| dMaxDD | +4.88pp | [-0.64, +12.96]pp | 95.1% | no |
| dCalmar | +0.3607 | [+0.0760, +0.7615] | 99.7% | YES |

*Extended (27y)*

| Metric (PROD-SINGLE) | mean | 95% CI | P(PROD beats) | CI excludes 0 |
|---|---:|---|---:|---|
| dSharpe | +0.2048 | [+0.0734, +0.3443] | 99.9% | YES |
| dMaxDD | +3.97pp | [-1.47, +11.69]pp | 92.0% | no |
| dCalmar | +0.1903 | [-0.0323, +0.4592] | 95.6% | no |

**2b. PROD vs IV4** (isolates the PURE sub-select knob; K=4 fixed in both):

*Clean (18y)*

| Metric (PROD-IV4) | mean | 95% CI | P(PROD beats) | CI excludes 0 |
|---|---:|---|---:|---|
| dSharpe | +0.0994 | [-0.0008, +0.2028] | 97.2% | no |
| dMaxDD | +1.22pp | [-1.41, +4.99]pp | 81.4% | no |
| dCalmar | +0.1153 | [-0.0583, +0.3362] | 90.5% | no |

*Extended (27y)*

| Metric (PROD-IV4) | mean | 95% CI | P(PROD beats) | CI excludes 0 |
|---|---:|---|---:|---|
| dSharpe | +0.0389 | [-0.0469, +0.1250] | 81.0% | no |
| dMaxDD | +0.66pp | [-2.46, +4.36]pp | 66.3% | no |
| dCalmar | +0.0282 | [-0.1264, +0.2022] | 65.6% | no |

## 3. Holdings overlap -- PROD min-var-3 vs SINGLE-K3 top-3 momentum

How often do the two risky baskets differ? PROD drops the highest-variance of the top-4; SINGLE-K3 drops the 4th-momentum name (and may also differ in breadth when the 3rd-momentum is negative but the 4th positive). `forward 1-month return` = realized return of each risky basket from rebal date to next, as held (inverse-vol weights; safe sleeve excluded for the differential).

| Window | rebals | differ | % differ | PROD wins | SINGLE wins | ties | PROD avg fwd | SINGLE avg fwd | (PROD-SINGLE) avg fwd |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| clean | 216 | 124 | 57.4% | 76 | 48 | 0 | 1.35% | 0.97% | +0.38% |
| ext | 326 | 180 | 55.2% | 96 | 84 | 0 | 1.27% | 1.11% | +0.17% |

## 4. Verdict

Computed numbers (clean window decisive):

- **CPM-solo clean:** PROD Sharpe 1.2667 / MaxDD -12.66% / Calmar 1.1306; SINGLE-K3 Sharpe 0.9472 / MaxDD -13.22% / Calmar 0.8629.
- **CPM-solo ext:** PROD Sharpe 1.2349 / MaxDD -15.18% / Calmar 0.9119; SINGLE-K3 Sharpe 1.0316 / MaxDD -16.16% / Calmar 0.7802.
- **Paired clean (PROD-SINGLE):** dSharpe +0.3209 CI[+0.1615,+0.4845] P(PROD)=100.0%; dMaxDD +4.88pp P(PROD)=95.1%; dCalmar +0.3607 P(PROD)=99.7%.
- **Paired ext (PROD-SINGLE):** dSharpe +0.2048 CI[+0.0734,+0.3443] P(PROD)=99.9%; dMaxDD +3.97pp P(PROD)=92.0%; dCalmar +0.1903 P(PROD)=95.6%.

### Parsimony call

**Do NOT collapse to single-stage K=3.** The naive single-stage collapse loses
~0.32 Sharpe in clean (1.2667 -> 0.9472) and ~0.20 in ext, with worse Calmar and
slightly deeper MaxDD. The paired bootstrap is unambiguous: P(PROD beats)=100%
on Sharpe with the 95% CI excluding zero in both windows; Calmar CI also excludes
zero in clean. SINGLE-K3 is decisively worse and the simplicity is not worth it.

**But the headline gap is mostly the POOL WIDTH (K), not the variance sub-select
itself.** SINGLE-K3 conflates two changes: shrinking the candidate pool K 4->3,
and dropping the sub-selection. IV4 isolates the pure second knob (K=4 fixed,
inverse-vol all 4, no sub-select):

- **PROD vs IV4 (pure sub-select knob):** clean dSharpe +0.099 CI[-0.001,+0.203]
  P(PROD)=97% (CI just grazes zero), dCalmar +0.067, MaxDD essentially identical
  (-12.66% vs -12.67%). Ext dSharpe +0.039 CI[-0.047,+0.125] P(PROD)=81% -- within
  noise. So the variance sub-selection as an isolated knob buys a modest,
  clean-window-favorable ~0.10 Sharpe that is borderline-significant in clean and
  not robust out to 27y.

**Holdings overlap confirms the mechanism, not a fluke.** PROD's min-var-3 basket
differs from SINGLE-K3's top-3 on 55-57% of rebalances, and when they differ PROD
wins the forward month 76:48 (clean) / 96:84 (ext), averaging +0.38pp/+0.17pp per
differing month. The edge is broad-based, not one or two outliers.

**Verdict: KEEP the two-stage, but recognize the second knob is a marginal
refinement, not the load-bearing component.** The load-bearing decision is the
wide K=4 momentum pool; the variance sub-selection adds a small, free (no MaxDD
cost, slightly higher Calmar) clean-window edge that is near-but-not-robustly
significant. If strict parsimony were mandatory, **IV4 (single-stage K=4) is the
correct one-fewer-knob collapse** -- it captures ~90% of PROD's Sharpe with
identical MaxDD -- NOT SINGLE-K3. Given the sub-selection costs nothing on DD and
helps Calmar, there is no performance reason to drop it; the only argument for
IV4 is pure knob-count parsimony, and the marginal evidence (clean P=97%, ext
within noise) does not compel removal either way. Recommendation: retain PROD
two-stage; treat the sub-selection knob as low-conviction and not worth further
tuning.

## Caveats

- All post-cost (10 bps/side), T+1 MOO exact with real yfinance auto_adjust opens; CPM-solo (no equity vol gate, which only affects the BULL/blend sleeve).
- Ext 27y is partially proxy-backed for the CPM trend universe pre-2006; clean 18y has full real-open coverage and is the decisive lens.
- Paired bootstrap resamples the common daily index with stationary blocks (size 21), identical draws to PROD and SINGLE-K3 so the per-resample difference is paired; annualization uses the window's real calendar span.
- Forward-return attribution in item 3 compares the RISKY baskets only (safe sleeve excluded), as held with inverse-vol weights, over the realized hold month; it is a selection-quality diagnostic, not the net post-cost P&L (which item 1/2 capture).
