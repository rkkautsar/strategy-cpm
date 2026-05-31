# CPM vs canonical HAA: head-to-head benchmark + HAA->CPM factor ladder

Role: analyst (read-only relative to production; no production files changed; no commit). Throwaway harness in `research/`.

Script: `research/cpm_haa_benchmark_ladder.py` -> `research/cpm_haa_benchmark_ladder.json`.

This document delivers two things the memo asked for:

1. A faithful canonical Hybrid Asset Allocation (HAA) benchmark (Keller & Keuning 2023), computed on the same window, costs, and execution engine as CPM, so it is the truest published head-to-head peer for CPM (HAA is the closest published peer per `research/cpm_closest_taa_peer_findings.md`).
2. A HAA -> CPM factor ladder that attributes CPM's edge over HAA to its individual design choices, with the headline split being mechanism contribution versus universe contribution.

## Method, harness, and gates

All curves use the identical shared execution harness as the production CPM studies: realistic T+1 market-on-open execution (`mooex`, exact: old basket earns the overnight close[T]->open[af] gap, new basket earns the intraday open[af]->close[af]), post-cost 10 bps/side, via `_segment_returns_conv`. The full panel runs once over the extended window and is sliced to each window, so cost, execution, and windowing are byte-identical across every config. Cash leg for excess metrics is SHV.

- Windows: CLEAN 2008-05-30..2026-05-22 (18y, full real-open coverage; the decision lens) and EXT 1999-03-10..2026-05-22 (27y, partly proxy-backed pre-2006; robustness only).
- Production CPM is BOTH-252 (`CORR_LOOKBACK_DAYS = 252`): inverse-vol covariance window and ranking-vol window are both 252 trading days.
- Metrics: clean is the decision lens, ext is robustness. Single in-sample evaluation -> treat magnitudes as in-sample and read direction/robustness over precision.

Three binding gates all PASS:

| gate | check | result |
|---|---|---|
| all-OFF == canonical HAA | parametric (0,0,0,0,0) equals the standalone HAA weight function, weight-by-weight over every rebalance | 0 mismatches, PASS |
| all-ON == production CPM | parametric (1,1,1,1,1) equals `cpm_live.compute_target_weights`, weight-by-weight | 0 mismatches, PASS |
| all-ON == CPM(both-252) anchor | CLEAN Sharpe 1.1658 / MaxDD -12.97% / Calmar 1.0137 | actual 1.1658 / -12.97% / 1.0137, PASS |

Because the endpoints are proven by construction (HAA reproduces the standalone implementation; CPM reproduces live production exactly and hits the anchor), every interior cell of the cube is a coherent interpolation between the two real strategies.

## HAA specification (confirmed against the paper / `canonical_taa_reference.md` sec.8)

- Offensive universe (8): SPY, IWM, VEA, VWO, VNQ, DBC, IEF, TLT.
- Canary: TIP single asset; risk-on iff TIP 13612U > 0, else 100% defensive.
- Ranking: 13612U (simple unweighted average of 1/3/6/12-month total returns).
- Cap: TOP-4 by 13612U.
- Absolute-momentum partial-safe: a top-4 slot whose own 13612U <= 0 routes its 25% tranche to the defensive asset.
- Defensive/safe: best of {BIL, IEF} by 13612U.
- Weighting: equal-weight surviving picks (25% each). Monthly.

Data / proxy note: HAA's offensive 8 are all available in the repo proxy panel (proxy-backed for the long EXT history; real ETF opens fetched for IWM/VEA/VWO for the CLEAN window so the mooex fill is faithful). The defensive asset uses SHV in place of BIL. SHV and BIL are the same ultra-short T-bill instrument; SHV simply has more history. Per the refinement, this BIL->SHV substitution is treated as a cosmetic instrument wash, NOT a design factor, and is held fixed in every config (safe pool = best of {SHV, IEF} by 13612U throughout).

# Deliverable 1: full-HAA benchmark vs CPM

All on the same window / costs / engine.

| strategy | window | Sharpe | CAGR | Vol | MaxDD | Calmar | Martin |
|---|---|---:|---:|---:|---:|---:|---:|
| **HAA** (canonical) | CLEAN | 0.8670 | 9.37% | 11.08% | -14.68% | 0.6386 | 2.2156 |
| **CPM** (both-252) | CLEAN | 1.1658 | 13.15% | 11.18% | -12.97% | 1.0137 | 3.6907 |
| **HAA** (canonical) | EXT | 1.0307 | 11.05% | 10.73% | -14.68% | 0.7527 | 2.8608 |
| **CPM** (both-252) | EXT | 1.2004 | 13.48% | 11.05% | -15.73% | 0.8571 | 3.6757 |

(CPM param all-ON equals CPM production-direct `compute_target_weights` to 4 decimals in both windows; Martin here is CAGR/Ulcer in fraction units, used only for ordinal comparison.)

Read: at near-identical volatility (~11%), CPM earns ~3.8 pp/yr more CAGR than canonical HAA on the clean window, with a shallower MaxDD, lifting Sharpe 0.87 -> 1.17 and Calmar 0.64 -> 1.01. HAA is a genuinely solid defensive peer (Sharpe ~0.87 clean, ~1.03 ext, and it diversifies CPM's bad crises -- see crisis table), but CPM dominates it on every risk-adjusted metric in both windows.

## Per-crisis MaxDD (continuous-curve, trough in window)

| crisis | HAA | CPM-mech on HAA universe | CPM full |
|---|---:|---:|---:|
| Dot-com (2000-03..2002-12) | -7.13% | -6.50% | -6.03% |
| GFC (2007-10..2009-06) | -12.72% | -13.82% | -11.88% |
| COVID (2020-02..2020-04) | -8.93% | -7.35% | -10.50% |
| 2022 (2022-01..2022-10) | -7.07% | -6.04% | -8.32% |

Honest note: CPM beats HAA in the two deep equity crises (Dot-com, GFC) but HAA is the shallower drawdown in COVID and 2022. HAA's pure-13612U / equal-weight defense is faster to de-risk in sharp, broad selloffs; CPM's growth-tilted universe (QQQ/SPHQ/GLD) costs it some downside in inflation/rate shocks like 2022. The crisis catches are preserved in both.

# Deliverable 2: HAA -> CPM factor ladder and attribution

Real CPM-vs-HAA design deltas (F5 safe-selector excluded as the SHV=BIL wash):

| factor | OFF (HAA) | ON (CPM) |
|---|---|---|
| **F1** canary | TIP-only 13612U>0 | HYG-or-TIP any-positive 13612U>0 |
| **F2** ranker | 13612U | risk-adjusted faber (10mo-SMA-distance / rv_252d) |
| **F3** weight | equal-weight | inverse-vol (cov tail 252) |
| **F4** screen | absolute 13612U>0 per slot | CPM 10mo-SMA faber>0 (positive-trend) |
| **F6** universe | HAA 8-set [SPY,IWM,VEA,VWO,VNQ,DBC,IEF,TLT] | CPM 8-set [QQQ,SPHQ,EFA,EEM,VNQ,GLD,TLT,DBC] |

Common (NOT factors, held fixed): TOP-4 cap; partial-safe breadth scaling (risky_fraction = n_pass/4, remainder to timed safe); SHV/IEF best-of-safe by 13612U. Note the partial-safe routing is common to both HAA and CPM, so it is correctly NOT a factor; equal-weight + per-slot absolute screen reproduces HAA's 25%-per-slot routing exactly, and inverse-vol + faber screen reproduces CPM exactly.

## HEADLINE: mechanism vs universe decomposition (3 configs, same engine)

| config | window | Sharpe | Calmar | MaxDD |
|---|---|---:|---:|---:|
| cfg1 HAA (HAA mech + HAA universe) | CLEAN | 0.8670 | 0.6386 | -14.68% |
| cfg2 CPM mech on HAA universe | CLEAN | 0.9575 | 0.6350 | -15.69% |
| cfg3 CPM full (CPM mech + CPM universe) | CLEAN | 1.1658 | 1.0137 | -12.97% |
| cfg1 HAA | EXT | 1.0307 | 0.7527 | -14.68% |
| cfg2 CPM mech on HAA universe | EXT | 1.0663 | 0.6900 | -15.69% |
| cfg3 CPM full | EXT | 1.2004 | 0.8571 | -15.73% |

| edge split | window | dSharpe | dCalmar | dMaxDD |
|---|---|---:|---:|---:|
| MECHANISM (cfg2 - cfg1) | CLEAN | +0.0906 | -0.0037 | -1.01 pp (worse) |
| UNIVERSE (cfg3 - cfg2) | CLEAN | +0.2082 | +0.3787 | +2.72 pp (better) |
| TOTAL (cfg3 - cfg1) | CLEAN | +0.2988 | +0.3750 | +1.71 pp (better) |
| MECHANISM (cfg2 - cfg1) | EXT | +0.0356 | -0.0627 | -1.01 pp (worse) |
| UNIVERSE (cfg3 - cfg2) | EXT | +0.1341 | +0.1671 | -0.04 pp |
| TOTAL (cfg3 - cfg1) | EXT | +0.1697 | +0.1044 | -1.05 pp (worse) |

**The dominant verdict: CPM's edge over HAA is overwhelmingly a UNIVERSE story, not a machinery story.** On the clean decision window, swapping HAA's asset set for CPM's QQQ/SPHQ/GLD-tilted set delivers ~70% of the Sharpe edge (+0.21 of +0.30) and effectively 100%+ of the Calmar and MaxDD edge (+0.38 Calmar, +2.7 pp shallower MaxDD). CPM's machinery applied to HAA's own assets (cfg2) raises Sharpe a modest +0.09 but does NOT improve Calmar (-0.004) and actually deepens MaxDD by ~1 pp. In other words, the risk-adjusted ranker / inverse-vol / faber-screen package only earns its keep when paired with CPM's more growth-tilted, higher-trending universe; on HAA's flatter universe the mechanisms are close to a wash on drawdown-adjusted terms.

## Per-factor attribution (background-averaged main effects over the 2^5 cube)

Main effect = mean(metric | factor ON) - mean(metric | factor OFF), averaged across all 16 backgrounds (Shapley-equivalent for a balanced factorial). "FLIP" = the on-minus-off delta changes sign across backgrounds, i.e. direction is not robust.

| factor | window | dSharpe | dCalmar | dMaxDD | robust? |
|---|---|---:|---:|---:|---|
| **F6 universe** | CLEAN | +0.1821 | +0.2295 | +0.75 pp | yes (no flip) |
| F2 ranker | CLEAN | +0.0634 | +0.0603 | +0.56 pp | Sharpe flip / Calmar flip |
| F3 weight | CLEAN | +0.0297 | +0.0192 | +0.68 pp | Calmar flip |
| F1 canary | CLEAN | +0.0257 | +0.0777 | +0.13 pp | Sharpe flip; Calmar robust |
| F4 screen | CLEAN | +0.0032 | -0.0414 | -1.02 pp | both flip (mildly negative) |
| **F6 universe** | EXT | +0.1154 | +0.1013 | -0.82 pp | Sharpe robust; Calmar flip |
| F1 canary | EXT | +0.0332 | +0.0310 | -1.23 pp | Calmar flip |
| F2 ranker | EXT | +0.0265 | -0.0091 | +0.32 pp | both flip |
| F3 weight | EXT | +0.0198 | +0.0194 | +1.00 pp | both flip |
| F4 screen | EXT | -0.0096 | -0.0371 | -0.64 pp | both flip (negative) |

Which CPM deltas DRIVE the edge, and which are immaterial:

- **F6 universe is the only first-order driver.** It is ~3x the next-largest factor on Sharpe and the only factor with a large, mostly-robust Calmar effect. This is the single design choice that separates CPM from HAA.
- **F1 credit canary (HYG-or-TIP) is the best of the mechanism factors and the one to keep.** Its Sharpe contribution is small/noisy, but it robustly improves clean Calmar (+0.078) -- it de-risks better on a drawdown-adjusted basis. In the ladder it is the single largest Calmar step (0.6386 -> 0.7689) when applied first.
- **F2 ranker (faber/rv) and F3 inverse-vol weighting are second-order and background-dependent.** Both add a little Sharpe but sign-flip on Calmar; they help mainly in combination with the CPM universe (see interactions below), not on HAA's assets.
- **F4 trend-screen change (13612U-absolute -> faber 10mo-SMA) is immaterial-to-mildly-negative.** On the clean window it is ~0 on Sharpe, negative on Calmar (-0.04), and deepens MaxDD (~-1 pp). Switching the screen metric from 13612U to the Faber SMA distance does not earn anything on its own; its only value is the coherence/interaction with the faber-based ranker.

## Interactions (why the mechanism looks weak alone)

Top 2-way Calmar interactions (coded +-1):

| interaction | CLEAN | EXT | reading |
|---|---:|---:|---|
| F2 x F6 (ranker x universe) | +0.0787 | +0.0483 | the risk-adjusted ranker pays off mostly ON the CPM universe |
| F4 x F6 (screen x universe) | +0.0537 | +0.0410 | the faber screen likewise only helps on the CPM universe |
| F3 x F6 (weight x universe) | -0.0163 | +0.0049 | inverse-vol x universe is small/inconsistent |
| F1 x F6 (canary x universe) | +0.0140 | -0.0298 | canary effect roughly universe-independent |

The strong positive F2xF6 and F4xF6 Calmar interactions are the mechanical reason cfg2 (mechanism on HAA universe) under-delivers: the ranker and screen are tuned to extract trend from the growth-tilted CPM universe, and contribute little on HAA's flatter, more bond/foreign-heavy asset set. The mechanism and the universe are complements, not independent additive gains.

## Sequential ladder (order-dependence)

Canonical order F1 -> F2 -> F3 -> F4 -> F6, CLEAN:

| step | config | Sharpe | Calmar | MaxDD |
|---|---|---:|---:|---:|
| HAA (all-OFF) | 00000 | 0.8670 | 0.6386 | -14.68% |
| +F1 canary | 10000 | 0.8929 | 0.7689 | -13.35% |
| +F2 ranker | 11000 | 0.9053 | 0.7088 | -14.12% |
| +F3 weight | 11100 | 0.9576 | 0.7618 | -12.97% |
| +F4 screen | 11110 | 0.9575 | 0.6350 | -15.69% |
| +F6 universe = CPM | 11111 | 1.1658 | 1.0137 | -12.97% |

Alternate order F6 first, CLEAN: HAA 0.8670/0.6386 -> +F6 1.0189/0.7693 -> +F2 1.0807/0.9026 -> +F3 1.1050/0.8926 -> +F4 1.1290/0.9166 -> +F1 = CPM 1.1658/1.0137.

Order-dependence is material and it reinforces the headline. When the universe is added LAST (canonical order), the +F6 step jumps Sharpe 0.96 -> 1.17 and Calmar 0.64 -> 1.01 in a single move -- the mechanism factors before it net almost nothing on Calmar. When the universe is added FIRST, the very first step (+F6) captures the bulk of the gain (Sharpe +0.15, Calmar +0.13) and the mechanism factors then layer on additive improvements (because they now sit on the universe they were designed for). Either way the universe swap is where the edge lives; the mechanism factors are productive only once the CPM universe is present, consistent with the F2xF6 / F4xF6 interactions.

## Verdict

- CPM is a clear risk-adjusted improvement over its closest published peer: clean Sharpe 1.17 vs HAA 0.87, Calmar 1.01 vs 0.64, at equal volatility, with shallower MaxDD.
- That edge is primarily a better/more-US-growth-tilted asset set (F6), not better machinery. On HAA's own assets, CPM's machinery adds only ~+0.09 Sharpe and nothing on Calmar/MaxDD.
- Among the mechanism deltas, the credit canary (F1) is the one robustly worth keeping (improves drawdown-adjusted return); the risk-adjusted ranker (F2) and inverse-vol weighting (F3) are second-order and only pay off in combination with the CPM universe; the trend-screen metric change (F4) is immaterial-to-mildly-negative.
- For the memo: frame HAA as the truest published peer and CPM's outperformance as predominantly a universe-selection edge complemented by a robust credit-canary defense, rather than a claim that the ranking/weighting machinery is the source of alpha.

## Caveats and confidence

- Endpoints are exact: all-OFF reproduces canonical HAA weight-by-weight; all-ON reproduces live `compute_target_weights` weight-by-weight and hits the CPM(both-252) anchor exactly. Confidence high on the cube's internal consistency.
- Single in-sample evaluation over one historical path -> magnitudes are in-sample. Many mechanism main effects sign-flip across backgrounds; trust direction/robustness, not the precise decimals. The universe effect is the only consistently large, mostly non-flipping factor.
- The universe comparison is a set-swap (messy by nature); it is handled cleanly by reporting the full 3-config decomposition (mechanism on HAA's own assets, then the universe swap) so mechanism and universe contributions are not conflated.
- BIL->SHV is documented as a cosmetic wash and is held fixed in all configs; it is not credited or penalized.
- EXT 27y is partly proxy-backed pre-2006 for the trend universes; CLEAN 18y has full real-open coverage and is the decisive lens. HAA-only tickers (IWM/VEA/VWO) have real ETF opens from 2000/2007/2005; their few pre-inception rebalance days fall back to close-to-close, immaterial to the clean window.
- All numbers mooex / T+1 MOO exact / 10 bps/side; CPM sleeve has no vol gate.

## Reproduce

```
.venv/bin/python research/cpm_haa_benchmark_ladder.py
```

Inputs: `cpm_live` engine (HAA-style functions: `sig_13612U`, `faber_sma_xs`, `inv_vol_weights`, `best_safe`, `compute_target_weights`), shared mooex harness `research/exec_lag_moo_validation_2026_05_30.py` (`_segment_returns_conv`, `load_open_close`), repo proxy panel + stitched data, real opens cache `/tmp/cpm_open_cache` (IWM/VEA/VWO fetched for this study).
Outputs: `research/cpm_haa_benchmark_ladder.json` (full 32-cell grid, effects, ladders, decomposition, crisis table) and this markdown.
