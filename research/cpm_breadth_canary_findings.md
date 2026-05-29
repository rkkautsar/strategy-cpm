# CPM Breadth Canary Overlay - Findings

Hypothesis: a breadth canary (risk-off / scale-down when too few of the 8 risky-universe assets have positive Faber trend) is a useful complementary regime gate on top of the existing HYG-OR-TIP canary + positive-Faber partial-safe structure, evaluated in the 60/40 two-sleeve CPM+BULL research baseline.

V0 reproduction check (target 1.347 Sharpe / 13.59% CAGR / -9.82% MaxDD, 60/40 clean blend): **PASS**

Method: reimplemented `run_cpm_backtest` in `research/cpm_breadth_canary.py` with an overlay hook applied to the output of the production `compute_target_weights` (no production files edited). Breadth signal `n_positive` = count of the 8 risky-universe assets (QQQ, SPHQ, EFA, EEM, VNQ, GLD, TLT, DBC) with positive Faber 10mo-SMA distance at the month-end signal date. Discrete gates force 100% best_safe when `n_positive < T`; continuous gates scale CPM risky exposure by `min(1, n_positive/T)` with the remainder to best_safe (no leverage). Existing canary + structure kept in all variants.

Windows: clean 2008-05-30..2026-05-22, stress 1999-03-10..2026-05-22. Costs 10bps/side. Excess Sharpe vs SHV.


## 1. Performance: CPM standalone and 60/40 blend


### Clean window

| Variant | Sleeve | Raw Sharpe | Excess Sharpe | CAGR | Vol | MaxDD | Calmar | Turnover/yr |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| V0 | cpm | 1.263 | 1.145 | 14.58% | 11.30% | -15.41% | 0.95 | 311% |
| V0 | blend | 1.347 | 1.212 | 13.59% | 9.84% | -9.82% | 1.38 | - |
| V_lt2 | cpm | 1.263 | 1.145 | 14.58% | 11.30% | -15.41% | 0.95 | 311% |
| V_lt2 | blend | 1.347 | 1.212 | 13.59% | 9.84% | -9.82% | 1.38 | - |
| V_lt3 | cpm | 1.261 | 1.139 | 14.03% | 10.91% | -15.41% | 0.91 | 303% |
| V_lt3 | blend | 1.338 | 1.201 | 13.26% | 9.67% | -9.82% | 1.35 | - |
| V_lt4 | cpm | 1.323 | 1.196 | 14.08% | 10.38% | -11.49% | 1.23 | 333% |
| V_lt4 | blend | 1.371 | 1.231 | 13.27% | 9.43% | -10.27% | 1.29 | - |
| V_contT4 | cpm | 1.299 | 1.177 | 14.34% | 10.78% | -12.42% | 1.15 | 315% |
| V_contT4 | blend | 1.362 | 1.224 | 13.44% | 9.61% | -9.22% | 1.46 | - |
| V_contT6 | cpm | 1.313 | 1.181 | 13.43% | 9.99% | -9.88% | 1.36 | 349% |
| V_contT6 | blend | 1.367 | 1.223 | 12.88% | 9.19% | -9.22% | 1.40 | - |

### Stress window

| Variant | Sleeve | Raw Sharpe | Excess Sharpe | CAGR | Vol | MaxDD | Calmar | Turnover/yr |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| V0 | cpm | 1.218 | 1.014 | 13.99% | 11.28% | -15.91% | 0.88 | 324% |
| V0 | blend | 1.291 | 1.056 | 12.65% | 9.58% | -11.79% | 1.07 | - |
| V_lt2 | cpm | 1.218 | 1.014 | 13.99% | 11.28% | -15.91% | 0.88 | 324% |
| V_lt2 | blend | 1.291 | 1.056 | 12.65% | 9.58% | -11.79% | 1.07 | - |
| V_lt3 | cpm | 1.201 | 0.994 | 13.45% | 11.01% | -15.91% | 0.85 | 329% |
| V_lt3 | blend | 1.274 | 1.037 | 12.32% | 9.47% | -11.79% | 1.04 | - |
| V_lt4 | cpm | 1.242 | 1.029 | 13.40% | 10.57% | -15.87% | 0.84 | 344% |
| V_lt4 | blend | 1.294 | 1.053 | 12.27% | 9.28% | -11.79% | 1.04 | - |
| V_contT4 | cpm | 1.238 | 1.028 | 13.73% | 10.87% | -15.87% | 0.87 | 330% |
| V_contT4 | blend | 1.297 | 1.058 | 12.48% | 9.41% | -11.79% | 1.06 | - |
| V_contT6 | cpm | 1.243 | 1.021 | 12.92% | 10.19% | -15.87% | 0.81 | 363% |
| V_contT6 | blend | 1.295 | 1.049 | 11.98% | 9.05% | -11.44% | 1.05 | - |

## 2. Crisis / calendar returns (60/40 blend)

| Variant | 2022 (clean) | 2008 (stress) |
| --- | --- | --- |
| V0 | 4.95% | 15.17% |
| V_lt2 | 4.95% | 15.17% |
| V_lt3 | 1.85% | 15.17% |
| V_lt4 | 1.85% | 18.98% |
| V_contT4 | 3.44% | 16.15% |
| V_contT6 | 2.90% | 16.85% |

## 3. Breadth activity diagnostic


### Clean window - n_positive distribution (217 months)

| n_positive | months | % |
| --- | --- | --- |
| 0 | 4 | 1.8% |
| 1 | 8 | 3.7% |
| 2 | 13 | 6.0% |
| 3 | 21 | 9.7% |
| 4 | 26 | 12.0% |
| 5 | 27 | 12.4% |
| 6 | 36 | 16.6% |
| 7 | 54 | 24.9% |
| 8 | 28 | 12.9% |

Threshold frequency: n<2 = 5.5%, n<3 = 11.5%, n<4 = 21.2% of months.

### Stress window - n_positive distribution (327 months)

| n_positive | months | % |
| --- | --- | --- |
| 0 | 4 | 1.2% |
| 1 | 8 | 2.4% |
| 2 | 20 | 6.1% |
| 3 | 37 | 11.3% |
| 4 | 37 | 11.3% |
| 5 | 37 | 11.3% |
| 6 | 56 | 17.1% |
| 7 | 84 | 25.7% |
| 8 | 44 | 13.5% |

Threshold frequency: n<2 = 3.7%, n<3 = 9.8%, n<4 = 21.1% of months.

## 4. Gating activity + false-positive test (does low breadth predict bad forward CPM returns?)

Forward return = next-calendar-month return of the ungated V0 CPM sleeve. If low-breadth months are a real signal, gated months should have clearly negative / below-average forward returns. If gated-month forward returns are near or above average, the gate is mostly exiting good months (false positives).


### Clean window

Correlation(n_positive, forward CPM monthly return) = **0.059** (n=150). All-month mean forward CPM return = 1.17%.

| Gate | % months gated | fwd ret gated (mean) | gated median | % gated fwd>0 | fwd ret non-gated (mean) |
| --- | --- | --- | --- | --- | --- |
| V_lt2 | 0.0% (0/217) | nan% | nan% | nan% | 1.17% |
| V_lt3 | 2.3% (5/217) | 0.16% | 0.94% | 60% | 1.20% |
| V_lt4 | 8.8% (19/217) | 0.40% | 0.67% | 57% | 1.25% |
| V_contT4 | 8.8% (19/217) | 0.40% | 0.67% | 57% | 1.25% |
| V_contT6 | 32.7% (71/217) | 1.39% | 1.79% | 69% | 1.07% |

### Stress window

Correlation(n_positive, forward CPM monthly return) = **0.018** (n=231). All-month mean forward CPM return = 1.10%.

| Gate | % months gated | fwd ret gated (mean) | gated median | % gated fwd>0 | fwd ret non-gated (mean) |
| --- | --- | --- | --- | --- | --- |
| V_lt2 | 0.0% (0/327) | nan% | nan% | nan% | 1.10% |
| V_lt3 | 3.7% (12/327) | 0.40% | 0.94% | 64% | 1.13% |
| V_lt4 | 11.9% (39/327) | 0.48% | 0.40% | 59% | 1.19% |
| V_contT4 | 11.9% (39/327) | 0.48% | 0.40% | 59% | 1.19% |
| V_contT6 | 33.9% (111/327) | 1.23% | 1.43% | 70% | 1.03% |

## 5. Interaction with existing HYG-OR-TIP canary + partial-safe (redundancy)

For each gate, of the months where the breadth overlay reduces risk, how many were ALREADY defensive or partial under the production rules (so the breadth gate adds nothing) vs full-risky months it newly cuts.


### Clean window

| Gate | months gated | already DEFENSIVE | already partial-safe | newly cuts full-risky |
| --- | --- | --- | --- | --- |
| V_lt2 | 0 | 0 | 0 | 0 |
| V_lt3 | 5 | 0 | 0 | 5 |
| V_lt4 | 19 | 0 | 0 | 19 |
| V_contT4 | 19 | 0 | 0 | 19 |
| V_contT6 | 71 | 0 | 0 | 71 |

### Stress window

| Gate | months gated | already DEFENSIVE | already partial-safe | newly cuts full-risky |
| --- | --- | --- | --- | --- |
| V_lt2 | 0 | 0 | 0 | 0 |
| V_lt3 | 12 | 0 | 0 | 12 |
| V_lt4 | 39 | 0 | 0 | 39 |
| V_contT4 | 39 | 0 | 0 | 39 |
| V_contT6 | 111 | 0 | 0 | 111 |

## 6. Verdict

- **V_lt2** (clean blend): Sharpe 1.347 (+0.000), MaxDD -9.82% (-0.00pp), CAGR 13.59% (+0.00pp).
- **V_lt3** (clean blend): Sharpe 1.338 (-0.009), MaxDD -9.82% (-0.00pp), CAGR 13.26% (-0.33pp).
- **V_lt4** (clean blend): Sharpe 1.371 (+0.024), MaxDD -10.27% (-0.00pp), CAGR 13.27% (-0.32pp).
- **V_contT4** (clean blend): Sharpe 1.362 (+0.015), MaxDD -9.22% (+0.01pp), CAGR 13.44% (-0.15pp).
- **V_contT6** (clean blend): Sharpe 1.367 (+0.020), MaxDD -9.22% (+0.01pp), CAGR 12.88% (-0.71pp).

See the synthesized conclusion paragraph appended below.
