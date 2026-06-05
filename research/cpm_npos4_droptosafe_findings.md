# CPM n_pos=4 "drop-to-safe" vs renormalize -- exploratory findings

Status: EXPLORATORY ("try only"). No prod change, no adoption, no commit.
Date: 2026-06-02. Author role: analyst.

## Hypothesis / question

At n_pos=4 (exactly 4 candidates with positive momentum), prod min-var drops
1-of-4, then renormalizes the 3 survivors to 100% equal-weight (33.3% each,
ZERO safe) because `risky_fraction = min(n_pos,4)/4 = 1.0`. The min-var drop
thus only CONCENTRATES; it does not de-risk.

VARIANT ("drop-to-safe"): send the min-var-dropped 4th slot to SAFE instead of
renormalizing it away -> 3 risk @ 25% + 25% safe (`risky_fraction =
len(picks)/4 = 0.75`). ONLY the n_pos=4 case changes. n_pos in {1,2,3} are
already partial-safe and are left untouched. Selection (min-var 3-of-4),
canary, ranker, and safe-selector are IDENTICAL between configs.

Questions:
(a) Sleeve: does drop-to-safe improve risk-adjusted metrics, or only trade
    CAGR for drawdown/vol?
(b) How often does n_pos=4 actually occur (effect size)?
(c) Blend (CPM 60%): does the variant move blend Sharpe/Calmar/Martin/MaxDD/
    CAGR materially?
(d) Net verdict + exploratory recommendation.

## Method / inputs

- Script: `research/cpm_npos4_droptosafe_run.py` (`.venv/bin/python`).
- Run: `cd strategy_cpm && .venv/bin/python research/cpm_npos4_droptosafe_run.py`
- Sleeve metrics: `research/cpm_harness.py` (mooex T+1 MOO exact, 10 bps/side).
  Anchor verified through harness: Sharpe 1.255673, MaxDD -0.130317,
  Calmar 1.007646 (matches `ANCHOR`).
- Blend metrics: `build_dashboard.build_artifacts` 60/20/20 (CPM close-to-close
  T+1, 10 bps/side). Variant injected by monkeypatching
  `cpm_live.compute_target_weights` so `run_cpm_backtest` picks it up; BULL+NDX
  identical across configs; patch restored after run.
- Variant logic is a faithful copy of `compute_target_weights` with the single
  n_pos=4 risky_fraction change. Self-check: baseline replica reproduces prod
  weights at every clean-window signal date (max weight diff 0.00e+00).
- Point-estimates only (bootstrap + walk-forward skipped per scope cut).
- Data: cached panel + open-cache (cached-data caveat applies).

## (b) Effect size: n_pos=4 is the DOMINANT case, not rare

| window | total mo | risk-on mo | n_pos {1,2,3,4} | n_pos=4 | % of risk-on | % of all |
|--------|---------:|-----------:|-----------------|--------:|-------------:|---------:|
| clean (2008-05-30..2026-05-22) | 217 | 160 | {1,5,11,143} | 143 | 89.4% | 65.9% |
| ext (1999-03-10..2026-05-22)   | 327 | 237 | {1,8,22,206} | 206 | 86.9% | 63.0% |

n_pos=4 fires in ~89% of risk-on months / ~66% of all months. This is the
default risk-on state, so the change is NOT marginal -- it reshapes the bulk of
the risk-on book (every typical risk-on month goes from 100% risky to 75%
risky + 25% safe).

## (a) Sleeve level (mooex T+1, 10 bps)

clean (2008-05-30..2026-05-22):

| config | Sharpe | Sortino | CVaR95/d | Calmar | Martin | MaxDD | CAGR | vol | turnover |
|--------|------:|------:|------:|------:|------:|------:|------:|------:|------:|
| baseline (renorm)  | 1.256 | 1.516 | -1.57% | 1.008 | 4.257 | -13.03% | 13.13% | 10.28% | 0.590 |
| drop-to-safe (var) | 1.243 | 1.518 | -1.26% | 0.802 | 3.776 | -13.03% | 10.45% |  8.30% | 0.525 |

ext (1999-03-10..2026-05-22):

| config | Sharpe | Sortino | CVaR95/d | Calmar | Martin | MaxDD | CAGR | vol | turnover |
|--------|------:|------:|------:|------:|------:|------:|------:|------:|------:|
| baseline (renorm)  | 1.255 | 1.550 | -1.51% | 0.971 | 4.117 | -13.14% | 12.76% | 9.97% | 0.567 |
| drop-to-safe (var) | 1.266 | 1.585 | -1.21% | 0.737 | 3.773 | -14.11% | 10.40% | 8.07% | 0.508 |

Sleeve read: drop-to-safe lowers CAGR ~2.7pp (clean) / ~2.4pp (ext) and lowers
vol ~2pp; Sharpe ~flat (slightly down clean, slightly up ext); Sortino ~flat;
CVaR95 improves (tail less negative). But Calmar and Martin get WORSE in both
windows, and MaxDD does NOT improve (identical -13.03% clean; actually worse
-14.11% ext). Reason: the worst drawdowns occur in/around DEFENSIVE and
low-n_pos transitions, which the variant does not touch -- so DD is unchanged
while CAGR (the Calmar/Martin numerator) drops. At the sleeve level the variant
is essentially "trade CAGR for vol/CVaR" with no DD payoff -> net mildly
NEGATIVE on Calmar/Martin.

### Per-crisis (sleeve, clean) -- cum return / maxDD

| crisis | base ret | var ret | base DD | var DD |
|--------|------:|------:|------:|------:|
| GFC 2007-09..2009-03 | 1.98% | 1.83% | -13.03% | -13.03% |
| Euro/2011 2011-05..10 | -0.68% | 1.14% | -7.95% | -7.95% |
| 2015-16 selloff | 4.11% | 4.11% | -2.89% | -2.89% |
| Q4-2018 | 0.53% | 0.54% | -0.02% | -0.02% |
| COVID 2020-02..04 | 2.11% | 3.00% | -10.20% | -10.20% |
| 2022 bear | -0.33% | 0.24% | -5.17% | -4.88% |

Crisis DDs are near-identical; small return improvements in Euro/2011, COVID,
2022 (variant holds 25% safe into those stress legs). The headline crisis DDs
(GFC, COVID) are unchanged -> those troughs are driven by non-n_pos=4 months.

## (c) Blend level 60/20/20 (clean, CPM close-to-close T+1, 10 bps)

| config | Sharpe | Sortino | CVaR95/d | Calmar | Martin | MaxDD | CAGR | vol |
|--------|------:|------:|------:|------:|------:|------:|------:|------:|
| baseline (renorm)  | 1.495 | 1.852 | -1.64% | 1.626 | 6.715 | -10.46% | 17.02% | 10.93% |
| drop-to-safe (var) | 1.509 | 1.896 | -1.45% | 1.690 | 6.689 |  -9.05% | 15.30% |  9.76% |

### Per-crisis (blend, clean)

| crisis | base ret | var ret | base DD | var DD |
|--------|------:|------:|------:|------:|
| GFC 2007-09..2009-03 | 7.98% | 7.93% | -7.40% | -7.40% |
| Euro/2011 2011-05..10 | -0.44% | 0.66% | -5.61% | -5.45% |
| 2015-16 selloff | 4.56% | 4.56% | -2.89% | -2.89% |
| Q4-2018 | 0.36% | 0.39% | -0.02% | -0.02% |
| COVID 2020-02..04 | 2.28% | 2.90% | -7.96% | -7.66% |
| 2022 bear | 0.21% | 0.51% | -5.09% | -4.34% |

Blend read: unlike the sleeve, at blend level the variant improves Sharpe
(+0.014), Sortino (+0.044), CVaR95 (-1.64% -> -1.45%), Calmar (+0.064), and
MaxDD (-10.46% -> -9.05%, ~1.4pp shallower). Martin is essentially flat
(6.715 -> 6.689). Cost is CAGR -1.7pp (17.02% -> 15.30%) and vol -1.2pp.
The DD/Calmar improvement that was ABSENT at the sleeve level APPEARS at the
blend level: the lower-vol CPM sleeve diversifies better against BULL+NDX, so
the blend's worst drawdown shrinks even though the CPM sleeve's own MaxDD did
not. 2022 bear blend DD improves most (-5.09% -> -4.34%).

## (d) Net verdict

- Effect size is LARGE in frequency (n_pos=4 ~= 66% of all months), so this is
  not a corner-case tweak; it materially de-risks the typical risk-on book.
- SLEEVE: wash-to-slightly-NEGATIVE on risk-adjusted quality. Sharpe/Sortino
  ~flat, CVaR better, but Calmar and Martin worse and MaxDD not improved -- it
  mostly trades CAGR for vol with no drawdown payoff at the sleeve.
- BLEND (the decision surface, CPM = 60%): mildly POSITIVE. Sharpe, Sortino,
  Calmar, CVaR95, and MaxDD all improve; Martin flat. The price is ~1.7pp CAGR.
  The improvement is a diversification effect (lower-vol CPM combines better
  with BULL+NDX), not a sleeve-intrinsic gain.

Recommendation (exploratory, NOT an adoption call): drop-to-safe is a
CAGR-for-safety trade. It is a WASH-to-mild-improvement at the blend level
(better Sharpe/Calmar/MaxDD, flat Martin, ~1.7pp lower CAGR) and a mild
NEGATIVE at the sleeve level (worse Calmar/Martin). Whether it is "better"
depends on the objective: prefer it if the goal is lower blend drawdown/vol and
higher Sharpe/Calmar; reject it if CAGR or sleeve-level Martin is the target.
The deltas are small relative to plausible noise, so this is NOT a clear win.

The blend-level Sharpe/Calmar/MaxDD improvement is the only result compelling
enough to be worth a bootstrap + walk-forward confirmation BEFORE any adoption
consideration (not run here per scope cut). Treat the point estimates as
suggestive only.

## Caveats / confidence

- Confidence: MEDIUM-LOW. Single a-priori variant, no tuning (good for overfit
  hygiene), but deltas are small and point-estimates only (no CI / no
  walk-forward). HIGH overfit caution still warranted.
- PIT integrity preserved: variant reuses prod selection/canary/ranker/safe
  and lagged T+1 execution; only the n_pos=4 weight split changes.
- Cached-data caveat: results computed off cached panel/open-cache.
- Sleeve uses mooex exact (anchor 1.2557); blend uses close-to-close T+1 via
  `run_cpm_backtest` -- the two execution models are not directly comparable to
  each other, but baseline vs variant WITHIN each model is apples-to-apples.
- turnover reported sleeve-only (avg two-way monthly, first month dropped);
  variant turnover is slightly lower (less reshuffling among 3 vs renormalized
  100% block). Blend turnover not decomposed.

## Artifacts

- `research/cpm_npos4_droptosafe_run.py` -- runnable backtest (self-verifying
  anchor + baseline-replica check).
- `research/cpm_npos4_droptosafe_findings_raw.txt` -- raw console tables.
- `research/cpm_npos4_droptosafe_findings.md` -- this report.
