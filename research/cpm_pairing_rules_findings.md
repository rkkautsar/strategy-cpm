# CPM Pairing-Rule Comparison

**Question:** Can CPM's min-variance 50/50 pair (P0) be replaced by a simpler, more interpretable deterministic pairing rule (P1/P2/P3) without losing risk-adjusted performance? Evaluated in the 60/40 two-sleeve CPM+BULL baseline.

**Fixed:** canary gate, positive-Faber filter, EAA (faber/vol) ranker, top-K=4. Varied ONLY the pair-selection rule. Each pair 50/50.

**Method:** `research/cpm_pairing_rules.py` (measurement only; no production files edited). `min_vol_pair` replaced by injectable rule inside a faithful copy of `compute_target_weights` / `run_cpm_backtest`. Blend = 0.60*CPM + 0.40*BULL (research two-sleeve default). Excess Sharpe vs SHV daily.

**Variants:**
- P0 (PROD): min-variance pair (504d cov) among top-4 pairs.
- P1: anchor = rank-1 EAA; partner = top-4 asset (excl anchor) with LOWEST 504d corr to anchor.
- P2: min 504d pairwise correlation pair among top-4 pairs.
- P3: lowest average 252d vol of the two assets (ignores correlation).

**P0 reproduction:** OK - CPM standalone Sharpe 1.263 (target 1.263), CAGR 14.58% (target 14.58%), Vol 11.30% (target 11.30%); 60/40 blend Sharpe 1.347 (target 1.347), CAGR 13.59% (target 13.59%), Vol 9.84% (target 9.84%), MaxDD -9.82% (target -9.82%).

---

## 1. Performance by variant

Columns: CAGR | Vol | Raw Sharpe | Excess Sharpe vs SHV | MaxDD | Calmar. Plus annualized turnover (two-sided) and 2022 calendar return.

### Clean window (2008-05-30 -> 2026-05-22)

**CPM standalone**

| Variant | CAGR | Vol | Raw Sharpe | Excess Sharpe | MaxDD | Calmar | Ann.Turnover | 2022 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| P0 min-variance (PROD) | 14.58% | 11.30% | 1.263 | 1.145 | -15.41% | 0.95 | 6.29x | 7.49% |
| P1 anchor + best diversifier | 15.00% | 12.88% | 1.152 | 1.047 | -15.98% | 0.94 | 8.29x | 5.00% |
| P2 min-correlation pair | 15.16% | 12.42% | 1.200 | 1.093 | -13.21% | 1.15 | 7.40x | 4.85% |
| P3 min-avg-vol pair | 13.74% | 11.99% | 1.135 | 1.025 | -15.40% | 0.89 | 6.29x | -1.00% |

**60/40 CPM+BULL blend**

| Variant | CAGR | Vol | Raw Sharpe | Excess Sharpe | MaxDD | Calmar | 2022 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| P0 min-variance (PROD) | 13.59% | 9.84% | 1.347 | 1.212 | -9.82% | 1.38 | 4.95% |
| P1 anchor + best diversifier | 13.88% | 10.65% | 1.276 | 1.150 | -10.74% | 1.29 | 3.49% |
| P2 min-correlation pair | 13.97% | 10.37% | 1.314 | 1.186 | -9.45% | 1.48 | 3.41% |
| P3 min-avg-vol pair | 13.12% | 10.07% | 1.276 | 1.145 | -10.93% | 1.20 | -0.08% |

### Stress window (1999-03-10 -> 2026-05-22)

**CPM standalone**

| Variant | CAGR | Vol | Raw Sharpe | Excess Sharpe | MaxDD | Calmar | Ann.Turnover | 2022 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| P0 min-variance (PROD) | 13.99% | 11.28% | 1.218 | 1.014 | -15.91% | 0.88 | 6.51x | 7.49% |
| P1 anchor + best diversifier | 14.22% | 13.06% | 1.083 | 0.903 | -15.98% | 0.89 | 8.68x | 5.00% |
| P2 min-correlation pair | 15.56% | 12.50% | 1.219 | 1.031 | -13.21% | 1.18 | 8.05x | 4.85% |
| P3 min-avg-vol pair | 13.50% | 11.69% | 1.142 | 0.943 | -15.40% | 0.88 | 6.58x | -1.00% |

**60/40 CPM+BULL blend**

| Variant | CAGR | Vol | Raw Sharpe | Excess Sharpe | MaxDD | Calmar | 2022 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| P0 min-variance (PROD) | 12.65% | 9.58% | 1.291 | 1.056 | -11.79% | 1.07 | 4.95% |
| P1 anchor + best diversifier | 12.83% | 10.46% | 1.206 | 0.985 | -11.25% | 1.14 | 3.49% |
| P2 min-correlation pair | 13.61% | 10.20% | 1.302 | 1.076 | -10.55% | 1.29 | 3.41% |
| P3 min-avg-vol pair | 12.37% | 9.75% | 1.245 | 1.012 | -10.93% | 1.13 | -0.08% |

---

## 2. Selection overlap vs P0 & momentum-anchoring

% months identical pair, % months with >=1 shared asset, and mean EAA-rank of the two selected assets (1 = top momentum). P0 row is self-reference.

### Clean window

| Variant | n months | % identical to P0 | % >=1-asset overlap | Mean EAA-rank of pair |
| --- | --- | --- | --- | --- |
| P0 min-variance (PROD) | 187 | 100.0% | 100.0% | 2.30 |
| P1 anchor + best diversifier | 187 | 32.6% | 96.8% | 2.07 |
| P2 min-correlation pair | 187 | 41.2% | 95.2% | 2.45 |
| P3 min-avg-vol pair | 187 | 57.8% | 100.0% | 2.22 |

### Stress window

| Variant | n months | % identical to P0 | % >=1-asset overlap | Mean EAA-rank of pair |
| --- | --- | --- | --- | --- |
| P0 min-variance (PROD) | 290 | 100.0% | 100.0% | 2.27 |
| P1 anchor + best diversifier | 290 | 35.5% | 97.2% | 2.01 |
| P2 min-correlation pair | 290 | 43.1% | 96.9% | 2.41 |
| P3 min-avg-vol pair | 290 | 60.3% | 99.0% | 2.23 |

---

## 3. Verdict

Match criterion: blend Raw Sharpe within ~0.03 of P0 AND similar MaxDD, in BOTH windows.

| Variant | Clean blend Sharpe (dP0) | Clean blend MaxDD (dP0) | Stress blend Sharpe (dP0) | Stress blend MaxDD (dP0) |
| --- | --- | --- | --- | --- |
| P0 min-variance (PROD) | 1.347 (+0.000) | -9.82% (+0.00pp) | 1.291 (+0.000) | -11.79% (+0.00pp) |
| P1 anchor + best diversifier | 1.276 (-0.071) | -10.74% (-0.92pp) | 1.206 (-0.085) | -11.25% (+0.55pp) |
| P2 min-correlation pair | 1.314 (-0.032) | -9.45% (+0.36pp) | 1.302 (+0.011) | -10.55% (+1.25pp) |
| P3 min-avg-vol pair | 1.276 (-0.071) | -10.93% (-1.12pp) | 1.245 (-0.046) | -10.93% (+0.86pp) |

**Auto-checks (within 0.03 Sharpe both windows; MaxDD not worse than P0 by >1pp):**

- P1 anchor + best diversifier: Sharpe-match=NO, DD-match=YES
- P2 min-correlation pair: Sharpe-match=NO, DD-match=YES
- P3 min-avg-vol pair: Sharpe-match=NO, DD-match=NO

### Bottom line

1. **P1 (anchor + best diversifier) - the targeted most-interpretable rule - does NOT replace P0.** It loses ~0.07 (clean) / ~0.09 (stress) blend Raw Sharpe and ~0.10 Excess Sharpe, runs higher vol (CPM 12.9% vs 11.3%) and the highest turnover (8.3-8.7x vs 6.3-6.5x), with no DD or Calmar advantage in the clean window. Anchoring on the single top-momentum asset and forcing the least-correlated partner raises both volatility and trading churn. Reject as an equivalent simplification.

2. **P3 (min average 252d vol, ignores correlation) is the weakest.** Lowest Raw/Excess Sharpe of all variants and a negative 2022 (-0.08% blend vs +4.95% P0), confirming correlation structure - not raw single-asset vol - is what makes the pairing work. Reject.

3. **P2 (min 504d pairwise correlation) is the one genuinely competitive alternative.** Clean blend Sharpe 1.314 (-0.032, just outside the 0.03 band) but it actually BEATS P0 in the stress window (1.302 vs 1.291) and wins on drawdown and Calmar in BOTH windows (clean MaxDD -9.45% vs -9.82%, Calmar 1.48 vs 1.38; stress MaxDD -10.55% vs -11.79%, Calmar 1.29 vs 1.07). It is also reasonably interpretable ('hold the two least-correlated trend leaders'). Trade-offs: slightly higher vol and turnover than P0, and a weaker 2022 (+3.41% vs +4.95%).

**Verdict: CONFIRM P0 as default.** No deterministic rule matches P0 on raw Sharpe within ~0.03 in BOTH windows AND preserves the clean-window edge. P1 (the requested interpretable candidate) clearly underperforms, so it cannot be flagged as a simpler-equivalent. P2 (min-correlation) is the lone near-miss and is arguably superior on tail risk (MaxDD/Calmar) and stress-window Sharpe; flag it as a credible drawdown-tilted alternative worth a dedicated follow-up, but it does not strictly dominate P0 (lower clean Sharpe, higher vol/turnover). Momentum-anchoring holds for all rules: mean EAA-rank of the selected pair stays ~2.0-2.5 across variants, so none drifts away from the trend leaders.
