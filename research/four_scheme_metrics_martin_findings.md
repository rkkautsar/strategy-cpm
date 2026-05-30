# CPM four-scheme metrics + Martin/UPI -- min-var sub-selection knob decision

Role: analyst (hypothesis-driven, read-only re production; NO production files changed; NO commit). Throwaway harness `research/four_scheme_metrics_martin.py`.

## Config / window / execution

- **CPM design (fixed across schemes):** ranker vol-Faber (10m-SMA-distance / rv_252d), positive-trend screen, top-K=4 momentum pool, canary HYG-OR-TIP (13612U), timed SHV/IEF safe, cov lookback 504d.
- **Execution:** T+1 MOO exact (`mooex`, real yfinance auto_adjust opens), post-cost 10 bps/side.
- **Windows:** clean 2008-05-30..2026-05-22 (18y); extended 1999-03-10..2026-05-22 (27y).
- **Schemes** (each its own COUNT-CONSISTENT strict partial-safe fallback, risky_fraction = min(n_pos, target)/target, remainder -> timed safe):
  1. **IV4** -- NO min-var; hold ALL top-4, inverse-vol; target=4 (strict-4 PS).
  2. **C(4,3)** = PROD -- min-var 3-subset of top-4, inverse-vol; target=3 (strict-3 PS).
  3. **C(4,2)** -- min-var 2-subset of top-4, inverse-vol; target=2 (strict-2 PS).
  4. **CONT** -- top-4 continuous min-variance (full-cov SLSQP), standard form (100% risky whenever >=1 positive; no partial-safe).
- **Ulcer Index (exact):** `UI = sqrt( mean( drawdown_pct^2 ) )` over the daily equity curve, `drawdown_pct = (equity/running_max - 1) * 100` (PERCENT units). **Martin ratio = CAGR(%) / UI(%)** (unit-consistent UPI; numerically identical to CAGR_frac/UI_frac). UI value reported in percent.

## Anchor gate

| Scheme | Window | Sharpe | MaxDD | Calmar | Expected | Match |
|---|---|---:|---:|---:|---|---|
| C(4,3) [PROD] | clean | 1.2667 | -12.66% | 1.1306 | 1.2667/-12.66%/1.1306 | CONFIRMED |

C(4,3) reproduces the production strict-3 anchor exactly. Production `compute_target_weights` clean Sharpe matches the C(4,3) scheme series = True. The other three schemes are trusted on that basis.

## Four-scheme metrics table (4 schemes x 5 metrics x {clean, ext})

Sharpe = raw daily Sharpe (0 rf). Calmar = CAGR/|MaxDD|. Martin = CAGR(%)/UI(%). UI = Ulcer Index in percent (defn above).

| Scheme | Window | Sharpe | CAGR | MaxDD | Calmar | Martin | Ulcer Index |
|---|---|---:|---:|---:|---:|---:|---:|
| IV4 (no min-var) | clean | 1.1910 | 13.44% | -12.67% | 1.0615 | 3.9646 | 3.39% |
| IV4 (no min-var) | ext | 1.2161 | 13.78% | -15.93% | 0.8654 | 3.8409 | 3.59% |
| C(4,3) [PROD] | clean | 1.2667 | 14.31% | -12.66% | 1.1306 | 3.9767 | 3.60% |
| C(4,3) [PROD] | ext | 1.2349 | 13.84% | -15.18% | 0.9119 | 3.6946 | 3.75% |
| C(4,2) | clean | 1.2630 | 14.38% | -13.14% | 1.0945 | 3.4485 | 4.17% |
| C(4,2) | ext | 1.2011 | 13.70% | -15.44% | 0.8874 | 3.2185 | 4.26% |
| CONT (continuous) | clean | 1.2935 | 14.57% | -15.15% | 0.9618 | 3.4702 | 4.20% |
| CONT (continuous) | ext | 1.2091 | 13.27% | -15.15% | 0.8760 | 3.1707 | 4.18% |

## DD-aware ranking (Calmar, Martin)

**clean:**
- Calmar rank: C(4,3) [PROD] 1.1306 > C(4,2) 1.0945 > IV4 (no min-var) 1.0615 > CONT (continuous) 0.9618
- Martin rank: C(4,3) [PROD] 3.9767 > IV4 (no min-var) 3.9646 > CONT (continuous) 3.4702 > C(4,2) 3.4485

**ext:**
- Calmar rank: C(4,3) [PROD] 0.9119 > C(4,2) 0.8874 > CONT (continuous) 0.8760 > IV4 (no min-var) 0.8654
- Martin rank: IV4 (no min-var) 3.8409 > C(4,3) [PROD] 3.6946 > C(4,2) 3.2185 > CONT (continuous) 3.1707

## Paired bootstrap IV4 vs C(4,3) -- Sharpe AND Martin

Stationary block bootstrap, B=2000, block=21, seed=42. Same block index applied to both series each draw (paired). Reported difference = **C(4,3) - IV4** (positive => C(4,3) higher; i.e. removing min-var to go IV4 hurts that metric).

| Window | Metric | mean (C43-IV4) | 95% CI | P(C43>IV4) | excludes 0 | daily corr |
|---|---|---:|---|---:|---|---:|
| clean | Sharpe | +0.0757 | [-0.0361, +0.1916] | 89.8% | no | 0.9688 |
| clean | Martin | +0.3120 | [-0.5097, +1.2390] | 77.3% | no | 0.9688 |
| ext | Sharpe | +0.0195 | [-0.0763, +0.1121] | 65.9% | no | 0.9669 |
| ext | Martin | -0.0005 | [-0.6269, +0.6398] | 50.1% | no | 0.9669 |

## Verdict

- **IV4 vs C(4,3) on DD-aware metrics (clean):** C(4,3) Calmar 1.1306 / Martin 3.9767 vs IV4 Calmar 1.0615 / Martin 3.9646. C(4,3) MaxDD -12.66% vs IV4 -12.67%.
- **Significance (paired bootstrap):** clean C(4,3)-IV4 Sharpe mean +0.0757 CI [-0.0361, +0.1916] (excludes 0 = False, P(C43>IV4)=90%); clean Martin mean +0.3120 CI [-0.5097, +1.2390] (excludes 0 = False, P=77%). Ext Sharpe mean +0.0195 (excl0=False); ext Martin mean -0.0005 (excl0=False, P=50%).
  - **Removing min-var does NOT significantly change Martin/UPI** (nor Sharpe): no IV4-vs-C(4,3) difference excludes zero in either window on either metric, and on Martin the effect is essentially nil ext (mean ~0, P~50%). The min-var sub-selection knob buys at most a marginal clean Calmar edge (1.1306 vs 1.0615) that is statistically within noise; on Martin the two are a dead heat clean (3.9767 vs 3.9646) and IV4 is actually higher ext (3.8409 vs 3.6946). **IV4 (no min-var) is NOT materially worse than C(4,3) on Martin/Calmar -- within noise.** Removing the knob is defensible.
- **C(4,2) (fewer names):** clean Sharpe 1.2630 / Calmar 1.0945 / Martin 3.4485 / MaxDD -13.14% / UI 4.17%; ext Martin 3.2185 / MaxDD -15.44%. Tightening selection to 2 names does nothing good: matched Sharpe but **worse Martin and worse (higher) Ulcer / deeper MaxDD** in both windows (concentration raises sustained drawdown). Not interesting as an improvement -- it is a DD-aware regression.
- **CONT (continuous min-var):** highest raw Sharpe (clean 1.2935, the top of the four) but **sits at/near the BOTTOM on the DD-aware metrics** -- clean Calmar 0.9618 (worst), Martin 3.4702, MaxDD -15.15% (worst), UI 4.20%; ext Martin 3.1707 (worst). Full-cov optimization concentrates into the low-vol corner, lifting Sharpe but trading away tail/DD protection -- exactly the wrong direction for a Martin/Calmar objective.
- **Net for the knob decision:** the min-var 3-subset (C(4,3)) is NOT robustly better than simply holding all top-4 inverse-vol (IV4) on any DD-aware metric; the gap is inside bootstrap noise. Going the OTHER direction (tighter C(4,2) or fully continuous CONT) both degrade Martin/Calmar. So if the goal is simplification, **removing the min-var sub-selection knob and shipping IV4 is the clean, DD-neutral simplification**; adding more selection aggressiveness is not justified.

## Caveats

- All post-cost (10 bps/side), T+1 MOO exact with real auto_adjust opens; CPM sleeve only (no BULL blend, no equity vol gate).
- Ext 27y is partially proxy-backed for the CPM trend universe pre-2006 (close-to-close fallback on a minority of rebal days); clean 18y has full real-open coverage and is the decisive lens.
- C(4,3) uses the same generalized weight fn (target=3) and is anchor-gated to production `compute_target_weights`; the cross-check confirms byte-equivalence.
- CONT uses full-covariance SLSQP (252-annualized daily cov over 504d) with inverse-vol fallback on solver failure; standard form holds 100% risky whenever >=1 top-4 positive.
- Martin/UPI uses the percent-based Ulcer Index defined above; Martin is unit-invariant so CAGR_frac/UI_frac == CAGR(%)/UI(%).
