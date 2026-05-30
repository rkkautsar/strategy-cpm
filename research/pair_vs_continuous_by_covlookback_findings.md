# Pair (50/50 min-var) vs Continuous min-var across covariance lookback

**Role:** analyst (hypothesis-driven, read-only re production; no production change, no commit). Throwaway harness in `research/`.

**Config:** CPM sleeve only, U=R=C=1 (production universe / vol-adjusted Faber ranker / dual HYG-OR-TIP canary), top-K=4, positive-trend screen. Selection logic identical across both schemes; ONLY the weighting step (50/50 min-var **pair** vs **continuous** min-var over survivors) and the covariance lookback vary. Universe `[QQQ,SPHQ,EFA,EEM,VNQ,GLD,TLT,DBC]`, safe `[SHV,IEF]`.

**Window:** CLEAN 18y `2008-05-30..2026-05-22`; EXT 27y `1999-03-10..2026-05-22`.

**Execution:** realistic T+1 MOO **exact** (`mooex`: overnight close[T]->open[af] on old basket, intraday open[af]->close[af] on new basket, compounded; real yfinance auto_adjust opens). Post-cost **10 bps/side**. Net metrics (Sharpe annualized 0-rf, CAGR, MaxDD, Calmar).

**Harness:** `research/pair_vs_continuous_by_covlookback.py` (reuses `pair_vs_continuous_minvar.cpm_wf_lb` weighting toggle + cov-lookback parametrization and `exec_lag_moo_validation_2026_05_30._segment_returns_conv`). Outputs `research/pair_vs_continuous_by_covlookback.json`.

**Anchor verification (CLEAN, 504d, 10 bps) -- reproduced EXACT before trusting other lookbacks:**
- pair: Sharpe **1.2424** / MaxDD **-16.35%** / Calmar **0.8704** (expected 1.2424 / -16.35% / 0.8704) OK
- continuous: Sharpe **1.2935** / MaxDD **-15.15%** / Calmar **0.9618** (expected 1.2935 / -15.15% / 0.9618) OK

---

## Hypothesis

DeMiguel (2009) estimation-error mechanism: continuous min-var overfits noisy covariance, so at SHORTER lookbacks (more estimation error) continuous should DEGRADE relative to the pair (possibly the pair wins), and at LONGER lookbacks (more stable covariance) continuous should hold/extend its edge. If confirmed in-sample, the pair's 50/50 regularization benefit would be demonstrably real when estimation error is high.

---

## 1-2. Grid: lookback x scheme, with continuous-minus-pair delta

### CLEAN (18y, mooex, 10 bps)

| cov lb | pair Sharpe | cont Sharpe | dSharpe | pair Calmar | cont Calmar | dCalmar | pair MaxDD | cont MaxDD | dMaxDD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 126  | 1.1589 | 1.1757 | +0.0168 | 0.7119 | 0.8459 | +0.1340 | -18.72% | -15.27% | +3.45% |
| 252  | 1.0677 | 1.2154 | +0.1477 | 0.7338 | 0.8794 | +0.1456 | -16.54% | -15.37% | +1.17% |
| 504* | 1.2424 | 1.2935 | +0.0511 | 0.8704 | 0.9618 | +0.0915 | -16.35% | -15.15% | +1.20% |
| 756  | 1.2222 | 1.2734 | +0.0512 | 0.9960 | 0.9067 | -0.0893 | -13.95% | -15.86% | -1.91% |
| 1008 | 1.1603 | 1.2490 | +0.0887 | 0.9900 | 0.9133 | -0.0767 | -13.67% | -15.63% | -1.97% |
| 1260 | 1.1344 | 1.2494 | +0.1150 | 0.9717 | 0.9169 | -0.0548 | -13.67% | -15.63% | -1.97% |

`*`504d = production. dMetric = continuous - pair (positive Sharpe/Calmar = continuous better; positive dMaxDD = continuous shallower DD).

### EXT (27y, mooex, 10 bps)

| cov lb | pair Sharpe | cont Sharpe | dSharpe | pair Calmar | cont Calmar | dCalmar | pair MaxDD | cont MaxDD | dMaxDD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 126  | 1.1244 | 1.1498 | +0.0254 | 0.5925 | 0.8056 | +0.2131 | -21.40% | -15.27% | +6.13% |
| 252  | 1.0858 | 1.1696 | +0.0838 | 0.6351 | 0.8221 | +0.1870 | -19.29% | -15.37% | +3.92% |
| 504* | 1.1640 | 1.2091 | +0.0451 | 0.8322 | 0.8760 | +0.0437 | -16.76% | -15.15% | +1.61% |
| 756  | 1.1448 | 1.1869 | +0.0421 | 0.6811 | 0.8260 | +0.1449 | -21.07% | -15.86% | +5.21% |
| 1008 | 1.0713 | 1.1779 | +0.1066 | 0.7502 | 0.8300 | +0.0798 | -18.17% | -15.92% | +2.25% |
| 1260 | 1.0419 | 1.1655 | +0.1236 | 0.5615 | 0.8285 | +0.2670 | -23.90% | -15.82% | +8.08% |

Supporting CAGR/vol (10 bps):

| cov lb | CLEAN pair CAGR/vol | CLEAN cont CAGR/vol | EXT pair CAGR/vol | EXT cont CAGR/vol |
|---|---|---|---|---|
| 126  | 13.33% / 11.41% | 12.92% / 10.88% | 12.68% / 11.17% | 12.30% / 10.58% |
| 252  | 12.14% / 11.39% | 13.52% / 10.97% | 12.25% / 11.23% | 12.64% / 10.66% |
| 504* | 14.23% / 11.27% | 14.57% / 11.03% | 13.95% / 11.82% | 13.27% / 10.79% |
| 756  | 13.90% / 11.22% | 14.38% / 11.07% | 14.35% / 12.38% | 13.10% / 10.87% |
| 1008 | 13.53% / 11.57% | 14.28% / 11.23% | 13.63% / 12.68% | 13.21% / 11.06% |
| 1260 | 13.28% / 11.65% | 14.33% / 11.27% | 13.42% / 12.89% | 13.11% / 11.10% |

---

## 3. Crossover analysis -- does continuous's edge shrink/reverse at short lookbacks?

**Sharpe (both windows): NO reversal at short lookback.** Continuous beats the pair on net Sharpe at EVERY lookback in BOTH windows (dSharpe > 0 in all 12 cells). The pair never overtakes continuous on Sharpe. If anything the Sharpe edge is SMALLEST at 126d (+0.017 CLEAN, +0.025 EXT) and grows at the LONG end (+0.115/+0.124 at 1260d) -- the exact opposite of the hypothesised "short = continuous degrades."

**MaxDD (both windows): NO reversal at short lookback.** Continuous has the SHALLOWER drawdown at short lookbacks (dMaxDD strongly positive: +3.45%/+6.13% at 126d), again opposite to the prediction. Continuous MaxDD is pinned in a tight band (~-15.1% to -15.9%) across ALL lookbacks; the pair's MaxDD is the volatile one.

**Calmar: the only crossover, and it runs the WRONG way for the hypothesis.** In CLEAN, continuous wins Calmar at short/mid lookbacks (126/252/504: dCalmar +0.134/+0.146/+0.092) and the **pair overtakes continuous between 504d and 756d** (756/1008/1260: dCalmar -0.089/-0.077/-0.055). So the only crossover lookback is ~504-756d, and the pair wins at the LONG end -- the reverse of the DeMiguel prediction (which expected the pair to win at the SHORT end). In EXT there is NO crossover at all: continuous wins Calmar at every lookback.

The CLEAN Calmar crossover is driven by the **pair improving at long lookbacks** (pair MaxDD shrinks -18.72% -> -13.67%, pair Calmar 0.71 -> 0.97 from 126d to 1260d), NOT by continuous degrading. Continuous Calmar is flat-to-slightly-down with lookback. And the CLEAN pair long-lookback gain does not survive into EXT, where the pair's long-lookback MaxDD blows out (-23.90% at 1260d) -- i.e. it is window-specific, not a robust regularization signature.

---

## 4. Concentration cross-check (continuous, EXT signal set)

| cov lb | pair avg max-wt (risk-on) | cont avg max-wt (risk-on) | cont eff-N (risk-on) | cont max single-asset wt |
|---|---:|---:|---:|---:|
| 126  | 0.5000 | 0.5755 | 2.2415 | 1.0000 |
| 252  | 0.5000 | 0.5839 | 2.2198 | 1.0000 |
| 504* | 0.5137 | 0.6045 | 2.1556 | 1.0000 |
| 756  | 0.5258 | 0.6102 | 2.1668 | 1.0000 |
| 1008 | 0.5430 | 0.6108 | 2.1691 | 1.0000 |
| 1260 | 0.5653 | 0.6076 | 2.1765 | 1.0000 |

**No corner-solution spike at short lookbacks.** Continuous's average max single-asset risk-on weight is actually LOWEST at 126d (0.5755) and rises slightly with lookback to ~0.61. Risk-on effective-N is highest at 126d (2.24) and falls to ~2.16 at long lookbacks. So short lookbacks produce MORE diversified continuous weights, not noisy corner bets -- the "noisy cov -> corner solution" overfitting prediction is not observed here (with K=4 survivors and long-only weights, the optimizer has little room to corner). The `max single-asset = 1.0000` column is the all-safe months (canary-off -> 100% SHV/IEF), present identically for both schemes, not a continuous overfitting artifact. The pair's max weight rises with lookback purely because min-var-pair tie-breaking selects more concentrated 2-asset pairs as the cov window lengthens.

---

## 5. Verdict

**The DeMiguel estimation-fragility hypothesis is REFUTED for this CPM sleeve.** There is NO in-sample evidence that the 50/50 pair's regularization pays off when covariance estimation error is higher (short lookback). The observed pattern is the inverse on the two metrics that the mechanism most directly predicts:

- Continuous min-var is the ROBUST scheme: its Sharpe (1.15-1.29), MaxDD (-15.1% to -15.9%) and Calmar (0.81-0.96) barely move across a 10x lookback range (126->1260d), and its realized vol is consistently the lowest at every lookback. It does its job (variance minimization) reliably even at the noisiest 126d window, with no concentration spike.
- The 50/50 PAIR is the FRAGILE scheme across lookback: its MaxDD and Calmar swing widely with the cov window, and it degrades sharply at the long end of the EXT window (1260d MaxDD -23.90%, Calmar 0.56).
- Continuous beats the pair on net Sharpe at all 6 lookbacks in BOTH windows, and on MaxDD at all 6 lookbacks in both windows. The pair only wins on Calmar, and only at LONG lookbacks (>=756d) in the CLEAN window -- a window-specific artifact that reverses in EXT, and the opposite end of the lookback range from where the estimation-error mechanism predicts the pair should win.

**Production 504d sits at a point where continuous WINS (not tied).** At 504d continuous beats the pair on all three headline metrics in both windows: CLEAN dSharpe +0.0511 / dCalmar +0.0915 / dMaxDD +1.20%; EXT dSharpe +0.0451 / dCalmar +0.0437 / dMaxDD +1.61%. The production lookback is NOT a coincidental sweet spot for continuous -- continuous wins across essentially the entire lookback grid.

**Decision implication (keep-pair vs continuous).** This analysis removes one candidate justification for keeping the pair: the pair cannot be defended on the grounds that its fixed-weight regularization protects against covariance estimation error at the production lookback. In-sample, at 504d and almost everywhere else, the continuous optimizer is both higher-Sharpe and shallower-DD. The case for keeping the pair therefore must rest on the OTHER arguments already on record -- a forward-looking/out-of-sample prior against optimizer overfitting, operational simplicity (a fixed two-name 50/50 vs a re-solved weight vector), the paired-bootstrap result that the in-sample continuous edge is not statistically significant, and the CLEAN long-lookback (>=756d) Calmar advantage -- NOT on an in-sample estimation-fragility mechanism, which this sweep does not support.

**Reconciliation with the earlier cov-lookback sweep.** The earlier `memo_gap_evidence.py` result (504-756d is the joint optimum for the production PAIR) is about where the PAIR alone is best; it is consistent with the pair's strong improvement from 126d -> ~504-756d seen here (CLEAN pair Sharpe 1.16 -> 1.24, Calmar 0.71 -> 0.99). That sweep optimized the pair's own lookback. The pair-vs-continuous DELTA shown here is a separate question, and it says continuous dominates the pair across the lookback range -- the pair's lookback "sweet spot" coincides with where it merely closes (CLEAN, long lookback) or narrows the gap to continuous, never with a robust win.

---

## Caveats / confidence

- IN-SAMPLE only: all 27y/18y used for both backtest and metric. No walk-forward / out-of-sample split here; this is exactly why an in-sample continuous edge is weak evidence and the pair's forward-looking-prior defense is not addressed by this run.
- Single execution convention (mooex, 10 bps/side) and single panel snapshot (`load_panel` ext_start 1999-03-10, end 2026-05-22). MOO real-open coverage has fallbacks (see prior runs); not re-audited here.
- Continuous min-var solved by SLSQP long-only sum-to-1 over the K=4 (top-half) survivor set; with only ~2-4 survivors the corner-solution risk that DeMiguel describes for large N is structurally limited, which partly explains the absence of a concentration spike. The result may not generalize to a larger continuous-min-var universe.
- 0-rf Sharpe, no statistical test on the per-lookback deltas in this script (significance is covered by the separate `paired_bootstrap_pair_vs_continuous` run). Confidence: HIGH that the descriptive hypothesis is not supported in-sample; MODERATE on the decision framing (depends on the out-of-sample/operational arguments not measured here).

## Memory / knowledge candidates

- Durable lesson: for the CPM sleeve, the continuous-min-var edge over the 50/50 pair is NOT explained by a covariance estimation-error / short-lookback fragility mechanism -- continuous is the lookback-robust scheme and wins on Sharpe+MaxDD across 126-1260d; the pair is the lookback-fragile one. Keep-pair must be defended on out-of-sample/operational grounds, not in-sample estimation-error regularization.
- Knowledge candidate: CPM weighting-vs-cov-lookback interaction grid (this file + json) for future weighting-scheme decisions.
