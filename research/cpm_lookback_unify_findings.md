# CPM lookback unification (R4) -- can 13612U replace the 10mo trend screen + 252d vol ranker?

Role: analyst (hypothesis-driven, read-only re production; no production files changed; no commit). Throwaway harness `research/cpm_lookback_unify_harness.py`.

**Question (external review -- "lookback sprawl / degrees of freedom"):** production CPM mixes distinct horizons -- 10-month SMA (absolute TREND screen), 252d daily vol (risk-adjusted RANK denominator, faber/rv_252d), 504d daily vol (inverse-vol WEIGHT), and 13612U (1/3/6/12m, canary + safe selectors). Can a normalized 13612U replace BOTH the 10mo SMA trend screen AND the 252d vol ranker, collapsing 10mo + 252d into the 13612U family? (A1 already showed 252/504 vol windows are a robust plateau; this is the TREND + RANK metric unification, not vol windows.)

**Convention (all rows):** strict-4 partial-safe CPM-solo (`cpm_live.compute_target_weights` spec); HYG-OR-TIP 13612U any-positive canary; timed SHV/IEF safe; top-K=4 candidate pool; inverse-vol weight (504d prod); T+1 MOO exact (`mooex`, real auto_adjust opens); post-cost 10 bps/side. Windows: clean 2008-05-30..2026-05-22 (decisive 18y, full real-open coverage); extended 1995-01-31..2026-05-22 (~31y, proxy-informed robustness only).

## 0. Anchor gate + self-check

| Window | Sharpe | MaxDD | Calmar | Martin | Expected | Match |
|---|---:|---:|---:|---:|---|---|
| clean | 1.1910 | -12.67% | 1.0615 | 3.9646 | 1.191/-12.67%/1.0615 | CONFIRMED |
| ext | 1.2643 | -15.93% | 0.8791 | 3.9767 | 1.2643/-15.93%/0.8791 | CONFIRMED |

Production engine reproduces the clean anchor exactly (Sharpe 1.1910 / MaxDD -12.67% / Calmar 1.0615). Parametric base-config self-check vs production: clean Sharpe 1.190980, max|daily-return diff| = 0.00e+00 (matches production = True). All variant rows below toggle only the rank and/or screen metric off this byte-identical base.

## 1. Unification variants -- clean window (decisive, 18y)

| Variant | Sharpe | CAGR | Vol | MaxDD | Calmar | Martin | dSharpe vs PROD | dCalmar vs PROD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| PROD (faber rank, faber screen, 504 vw) | 1.1910 | 13.44% | 11.16% | -12.67% | 1.0615 | 3.9646 |  |  |
| (a) trend->13612U screen (faber rank, 504 vw) | 1.1728 | 13.18% | 11.14% | -12.67% | 1.0410 | 3.8532 | -0.0182 | -0.0205 |
| (b) rank->13612U/vol (faber screen, 504 vw) | 1.1965 | 13.64% | 11.27% | -12.67% | 1.0765 | 3.9295 | +0.0055 | +0.0149 |
| (c) FULL unify 13612U rank+screen (504 vw) | 1.1725 | 13.37% | 11.30% | -12.67% | 1.0558 | 3.7339 | -0.0185 | -0.0058 |
| (c2) FULL unify + 252 vw | 1.1540 | 13.15% | 11.31% | -13.32% | 0.9876 | 3.5434 | -0.0370 | -0.0740 |

## 2. Unification variants -- extended window (proxy-informed robustness only, ~31y)

| Variant | Sharpe | CAGR | Vol | MaxDD | Calmar | Martin | dSharpe vs PROD |
|---|---:|---:|---:|---:|---:|---:|---:|
| PROD (faber rank, faber screen, 504 vw) | 1.2643 | 14.00% | 10.78% | -15.93% | 0.8791 | 3.9767 |  |
| (a) trend->13612U screen (faber rank, 504 vw) | 1.2500 | 13.80% | 10.76% | -15.93% | 0.8667 | 3.8837 | -0.0143 |
| (b) rank->13612U/vol (faber screen, 504 vw) | 1.2432 | 13.88% | 10.88% | -18.86% | 0.7356 | 3.8001 | -0.0211 |
| (c) FULL unify 13612U rank+screen (504 vw) | 1.2372 | 13.84% | 10.91% | -18.86% | 0.7339 | 3.7377 | -0.0270 |
| (c2) FULL unify + 252 vw | 1.2344 | 13.73% | 10.86% | -18.72% | 0.7335 | 3.6937 | -0.0299 |

## 3. Read

- **(a) trend screen 10mo->13612U:** clean Sharpe 1.1728 (dSharpe -0.0182), Calmar 1.0410 (-0.0205), MaxDD -12.67%.
- **(b) rank 10mo-dist/vol -> 13612U/vol:** clean Sharpe 1.1965 (dSharpe +0.0055), Calmar 1.0765 (+0.0149), MaxDD -12.67%.
- **(c) FULL unify (review proposal):** clean Sharpe 1.1725 (dSharpe -0.0185), Calmar 1.0558 (-0.0058), MaxDD -12.67%.
- **(c2) FULL unify + 252 vw:** clean Sharpe 1.1540 (dSharpe -0.0370), Calmar 0.9876, MaxDD -13.32%.

**Tail-control nuance (the decisive observation):** clean MaxDD is identical (-12.67%) across PROD/(a)/(b)/(c) because the clean-window worst drawdown is dominated by the single 2025-04-08 event that all variants share. The differentiation surfaces in the extended (~31y) lens: swapping the ranker to 13612U/vol (variants b, c) DEEPENS extended MaxDD from -15.93% (PROD) to -18.86%, collapsing extended Calmar from 0.8791 to 0.7339 (-0.1452). The 10mo-SMA-distance / 252d-vol ranker is therefore mildly load-bearing on the tail-control axis even though its clean-window Sharpe contribution is noise-level.

## 4. Verdict

**KEEP the multi-horizon design. Unification is at best a clean-window wash and a measurable extended-window tail-control LOSS; it does not earn the parsimony win.**

- The clean-window dSharpe of every unification variant is within a few hundredths (-0.018 to +0.006), comfortably inside the memo's bootstrap CI on the Sharpe level ([0.79, 1.60]); on clean Sharpe alone the choice is statistically unresolved.
- Rank-only unification (b) is the only variant that does not lose on clean (Sharpe 1.1965 +0.0055, Calmar 1.0765), but it costs ~3pp of extended MaxDD (-15.93% -> -18.86%) and ~0.14 of extended Calmar -- a real robustness give-up for no clean-window gain.
- Trend-screen unification (a) and full unification (c) both lose on clean Sharpe (-0.018) AND on extended Calmar. Collapsing the 504d vol weight too (c2) is the worst cell (clean Sharpe -0.037, clean Calmar < 1.0) -- consistent with A1's finding that the vol windows are load-bearing.
- The horizons are each literature-canonical (Faber 10mo SMA trend, AAA/EAA 252d vol-adjusted rank, Keller HAA 13612U). Because unifying does NOT improve clean performance and demonstrably degrades extended-window drawdown control, the multi-horizon stack earns its complexity on the tail axis; "lookback sprawl" is not free degrees of freedom here. Recommend: keep 10mo trend screen + 252d vol ranker as-is; do not unify onto 13612U.
- Honesty flag: single in-sample run, point estimates, no OOS split; clean deltas are noise-level. The case to KEEP rests on "no upside + real extended-window tail cost", not on a statistically significant clean-window edge. There is likewise no evidence to ADOPT a unified config.

## Caveats

- Post-cost (10 bps/side), T+1 MOO exact using real yfinance auto_adjust opens; CPM sleeve only (no equity vol gate; gate is a BULL/blend concern).
- Single in-sample run, point estimates only -- no bootstrap CI or OOS split in this harness. Clean-window CPM Sharpe difference CIs are structurally wide (memo bootstrap CI on the level is [0.79, 1.60]); deltas of order a few hundredths of Sharpe are inside noise.
- Extended window is partially proxy-backed pre-2006 for the CPM trend universe (close-to-close fallback on a minority of rebal days); clean 18y is the decisive lens.
- These horizons are each literature-canonical (Faber 10mo SMA; AAA/EAA 252d vol-adjusted rank; Keller HAA 13612U). A wash favors simplification (fewer degrees of freedom, less non-stationarity risk); a loss means the pedigree'd multi-horizon stack earns its complexity. Do not over-claim a unified config beats a literature-grounded one on one in-sample slice.
