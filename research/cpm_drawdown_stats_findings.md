# CPM drawdown-control edge: significance + GFC/canary independence

Scope: read-only research. Tests whether the memo's NEW lead claim -- "drawdown /
tail-control is CPM's significant edge" -- holds up under the same statistical
treatment the Sharpe claim got, and whether it is independent of the
canary-GFC-insurance leg.

Convention: mooex (T+1 MOO exact), 10 bps/side, monthly month-end signal, clean
18y window (2008-05-30 -> 2026-05-22). Same `_segment_returns_conv` harness and
benchmark builders as `cpm_benchmarks_proper.py` (byte-identical cost / window /
execution across CPM and every benchmark).

Anchor reproduced exactly: CPM clean Sharpe 1.1910 / MaxDD -12.67% / Calmar
1.0615 / Martin 3.9646.

Artifacts: `research/cpm_drawdown_stats.py`, `research/cpm_drawdown_stats.json`.

## Clean 18y metrics

| series | Sharpe | CAGR | MaxDD | Calmar | Martin | Ulcer |
|---|---|---|---|---|---|---|
| CPM | 1.1910 | 13.45% | -12.67% | 1.0615 | 3.9646 | 3.39% |
| CPM_no_canary | 1.1278 | 13.11% | -15.01% | 0.8736 | 3.1531 | 4.16% |
| Canonical_AAA | 0.9435 | 9.23% | -21.76% | 0.4241 | 1.6230 | 5.69% |
| 60/40 | 0.7946 | 8.75% | -29.82% | 0.2936 | 1.4023 | 6.24% |
| Naive_12m | 0.6493 | 8.14% | -26.59% | 0.3061 | 1.0193 | 7.98% |
| BuyHold_InvVol | 0.6860 | 8.15% | -34.92% | 0.2333 | 1.1067 | 7.36% |

## 1. Paired difference-CIs on Calmar / Martin / MaxDD (B=2000, block=21)

Paired block bootstrap, CPM minus each benchmark (positive = CPM better).
Significant = 95% CI excludes the no-difference point (zero).

MaxDD difference (positive = CPM shallower DD):

| vs benchmark | point | CI_lo | CI_hi | significant? |
|---|---|---|---|---|
| Canonical_AAA | 0.0910 | -0.0586 | 0.1354 | NO |
| 60/40 | 0.1716 | -0.0300 | 0.2371 | NO |
| Naive_12m | 0.1392 | 0.0152 | 0.3109 | YES |
| BuyHold_InvVol | 0.2225 | 0.0006 | 0.3021 | YES |

Calmar difference:

| vs benchmark | point | CI_lo | CI_hi | significant? |
|---|---|---|---|---|
| Canonical_AAA | 0.6399 | -0.1162 | 0.9142 | NO |
| 60/40 | 0.7713 | -0.0213 | 1.1070 | NO |
| Naive_12m | 0.7579 | 0.1548 | 1.1379 | YES |
| BuyHold_InvVol | 0.8313 | 0.1109 | 1.1800 | YES |

Martin difference:

| vs benchmark | point | CI_lo | CI_hi | significant? |
|---|---|---|---|---|
| Canonical_AAA | 2.3504 | -0.1371 | 3.8059 | NO |
| 60/40 | 2.5738 | -0.3145 | 4.5695 | NO |
| Naive_12m | 2.9550 | 0.7683 | 4.7088 | YES |
| BuyHold_InvVol | 2.8682 | 0.4540 | 4.7908 | YES |

Key result: the drawdown/tail metrics reproduce the EXACT SAME significance
pattern as the raw Sharpe. CPM clears the bar against the two weak benchmarks
(Naive_12m, BuyHold_InvVol) on all three metrics, but the CI INCLUDES zero
against the two strongest benchmarks (Canonical_AAA and 60/40) on all three
metrics. The structurally large MaxDD point gaps (-12.67% vs -21.76% / -29.82%)
do NOT survive the bootstrap vs canonical AAA and 60/40 -- MaxDD is a single-path
extremum with large sampling variance, so a big point gap is within noise.

So the brief's expectation ("MaxDD difference is structurally large; confirm it
survives bootstrap") is only partly met: it survives vs the weak peers, NOT vs
the strong defensive peers.

## 2. GFC independence / breadth of the drawdown edge

Worst peak-to-trough drawdown per crisis episode (running-high based), plus where
each series' overall MaxDD trough actually lands:

| series | GFC | COVID | 2022 | overall MaxDD | trough date |
|---|---|---|---|---|---|
| CPM | -9.83% | -10.06% | -7.64% | -12.67% | 2025-04-08 |
| CPM_no_canary | -13.33% | -10.06% | -8.74% | -15.01% | 2016-01-20 |
| Canonical_AAA | -11.74% | -7.88% | -21.76% | -21.76% | 2022-10-20 |
| 60/40 | -29.82% | -19.13% | -21.02% | -29.82% | 2009-03-09 |
| Naive_12m | -22.96% | -23.23% | -23.74% | -26.59% | 2023-03-15 |
| BuyHold_InvVol | -34.92% | -21.33% | -21.27% | -34.92% | 2008-11-20 |

Critical: CPM's own worst drawdown is NOT in the GFC. CPM's MaxDD trough is
2025-04-08 (recent tariff/equity selloff); its GFC episode DD is only -9.83%.
CPM's tail control is therefore not a GFC artifact -- the strategy's deepest hole
is a non-GFC event and is still shallow (-12.67%).

MaxDD/Calmar EXCLUDING the GFC window (GFC excised + remainder stitched):

| series | MaxDD ex-GFC | Calmar ex-GFC | Martin ex-GFC |
|---|---|---|---|
| CPM | -12.67% | 1.1388 | 4.5366 |
| CPM_no_canary | -15.01% | 0.9415 | 3.5696 |
| Canonical_AAA | -21.76% | 0.4765 | 1.8222 |
| 60/40 | -21.02% | 0.4986 | 2.2773 |
| Naive_12m | -26.59% | 0.3480 | 1.1874 |
| BuyHold_InvVol | -21.33% | 0.4748 | 2.1217 |

MaxDD gap decomposition (CPM minus bench): how much of the point gap is GFC-driven:

| vs benchmark | full gap | ex-GFC gap | GFC-attributable |
|---|---|---|---|
| Canonical_AAA | 9.10% | 9.10% | 0.0% |
| 60/40 | 17.16% | 8.35% | 51.3% |
| Naive_12m | 13.92% | 13.92% | -0.0% |
| BuyHold_InvVol | 22.25% | 8.67% | 61.1% |

Reading: the drawdown advantage vs Canonical_AAA and Naive_12m is entirely
NON-GFC (0% GFC-attributable -- those benchmarks' own MaxDDs are in 2022/2023).
The advantage vs 60/40 and BuyHold_InvVol is ~half-to-most GFC-driven (51% / 61%)
because those benchmarks took their worst hits in 2008-09. But even after
excising GFC, CPM still dominates every benchmark on point MaxDD (-12.67% vs
-21.02% to -26.59%). So on the point-estimate / breadth dimension the edge is
BROAD, not GFC-only.

## 3. Canary independence

CPM-no-canary = identical ranker / Faber screen / vol-adjusted selection /
inverse-vol weighting / strict-4 partial-safe fallback, with ONLY the HYG|TIP
canary gate disabled.

- CPM MaxDD -12.67% vs CPM-no-canary MaxDD -15.01%. The canary contributes only
  2.35 pts of drawdown reduction.
- CPM-no-canary is STILL shallower than every benchmark on point MaxDD
  (-15.01% vs -21.76% / -29.82% / -26.59% / -34.92%).
- GFC episode: canary helps where expected -- CPM -9.83% vs no-canary -13.33%
  (canary saves ~3.5 pts inside GFC). But CPM's overall MaxDD is not in GFC
  anyway, so the canary's GFC insurance does not set the headline tail number.
- CPM-no-canary difference-CIs vs benchmarks keep the same significance pattern:
  significant vs Naive_12m (all three metrics) and vs BuyHold_InvVol on
  Calmar/Martin (MaxDD marginal, CI just touches 0); not significant vs
  Canonical_AAA or 60/40.

Conclusion on overlap: the drawdown-control leg is LARGELY INDEPENDENT of the
canary-insurance leg. Most of CPM's drawdown advantage comes from the
trend/screen/universe/inverse-vol stack, not the canary. The critique's worry
that "Calmar dominance" and "canary = GFC-only insurance" are the same claim is
NOT supported -- they are distinct contributors (canary ~2.35 pts of MaxDD;
~3.5 pts localized to GFC).

## Verdict

(a) Statistically significant on Calmar/Martin/MaxDD difference-CIs?
PARTIAL -- and identical to the Sharpe result. CPM is significant vs the weak
benchmarks (Naive_12m, BuyHold_InvVol) on all three tail metrics, but the CI
INCLUDES zero vs the two strongest defensive benchmarks (Canonical_AAA, 60/40)
on all three. The large MaxDD point gaps are within bootstrap noise against the
best-matched peers. Promoting drawdown control to "the memo's significant edge"
overstates: it carries the same statistical weakness as the Sharpe claim.

(b) Broad, not solely GFC/canary-driven?
YES. CPM's own worst drawdown is a 2025 (non-GFC) event; the edge vs AAA/Naive
is 0% GFC-attributable; CPM dominates all benchmarks on point MaxDD even after
GFC is excised; and removing the canary leaves CPM shallower than every benchmark
(canary worth only ~2.35 pts). The drawdown-control leg is independent of the
canary-GFC-insurance leg, not the same claim.

Bottom line: the drawdown edge is BROAD and INDEPENDENT of the canary (good news
for the memo's narrative that it is a distinct, structural property), but it is
NOT statistically stronger than the Sharpe edge -- it fails the same difference-CI
test against canonical AAA and 60/40. Recommend the memo frame tail control as a
broad, structurally-distinct property with large point gaps, while explicitly
flagging that, like Sharpe, the gap is within bootstrap noise versus the two
strongest defensive benchmarks (n ~ 18y single path; MaxDD is a high-variance
extremum). Do not assert it as a statistically significant lead edge over all
benchmarks.

## Caveats / confidence

- Single 18y clean path; MaxDD/Calmar/Martin are path-extremum statistics with
  high sampling variance -- the wide bootstrap CIs reflect that, not a coding
  artifact. Block bootstrap (block=21 ~ 1 trading month) preserves short-horizon
  autocorrelation; results are stable at B=2000.
- Ex-GFC recompute excises the GFC window and stitches the remainder; the splice
  introduces one artificial return junction (minor, does not affect the
  conclusion since CPM's MaxDD is outside GFC).
- Episode windows are fixed calendar ranges (GFC 2008-05-30..2009-06-30, COVID
  2020-02..2020-04, 2022 full year); a benchmark whose true trough sits just
  outside a window is attributed to "overall" not the episode.
- CPM-no-canary isolates ONLY the canary gate; all other stack components
  (ranker, screen, inverse-vol, partial-safe) are unchanged.
- Confidence: HIGH on the qualitative verdict (significance pattern, breadth,
  canary independence all robust and internally consistent with the prior Sharpe
  finding). MEDIUM on exact CI bounds (resample-noise at the 2nd decimal).

## Handoff

oracle: decision on how the memo should frame the drawdown-control claim given it
is broad + canary-independent but NOT significant vs canonical AAA / 60/40.
fixer: any memo wording edits (out of analyst scope; no prod/memo edits made).
