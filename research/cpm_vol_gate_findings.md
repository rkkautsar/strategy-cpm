# CPM Volatility-Regime Gate Overlay - Findings

Hypothesis: a volatility-regime gate (de-risk CPM when market or realized volatility spikes) is a useful NEW overlay on top of the existing CPM structure (HYG-OR-TIP canary + positive-Faber filter + K=4 + min-var pair), intended to catch the high-breadth-then-crash regime the breadth canary misses (notably the 2020 COVID crash). Evaluated in the 60/40 two-sleeve CPM+BULL research baseline. Mirrors the BULL sleeve's existing `_vol_gate_ok` (RV_20d < RV_252d) logic, applied to CPM, which today has NO vol gate.

V0 reproduction check (target 1.347 Sharpe / 13.59% CAGR / -9.82% MaxDD, 60/40 clean blend): **PASS**

VIX/VIX3M availability: **VIX NOT available** in the proxy panel (`has_vix=False`; panel columns contain no VIX or VIX3M series). Per task fallback, SIG-VIX (term-structure backwardation / level threshold) could NOT be tested. All signals below use realized-vol crossovers.

Method: reimplemented `run_cpm_backtest` in `research/cpm_vol_gate.py` with an overlay hook applied to the output of the production `compute_target_weights` (no production files edited). Two vol signals:

- **SIG-RV-SPY**: SPY `RV_20d >= RV_252d` (annualized daily-return std, tail 20 vs tail 252; mirrors BULL `_vol_gate_ok` exactly, fires on the inverse of `vol_ok`).
- **SIG-RV-BOOK**: same crossover on the V0 (ungated) CPM **book** daily return (RV of the CPM sleeve return, 20d vs 252d).

Two gate actions: **binary** (100% best_safe when fired) and **continuous** (scale risky exposure by `f = min(1, RV_252/RV_20)`, remainder to best_safe; no leverage, cap 1.0). Existing canary + structure kept in all variants.

Windows: clean 2008-05-30..2026-05-22, stress 1999-03-10..2026-05-22. Costs 10bps/side. Excess Sharpe vs SHV.


## 1. Performance: CPM standalone and 60/40 blend


### Clean window

| Variant | Sleeve | Raw Sharpe | Excess Sharpe | CAGR | Vol | MaxDD | Calmar | Turnover/yr |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| V0 (no gate) | cpm | 1.263 | 1.145 | 14.58% | 11.30% | -15.41% | 0.95 | 311% |
| V0 (no gate) | blend | 1.347 | 1.212 | 13.59% | 9.84% | -9.82% | 1.38 | - |
| SPY-RV binary | cpm | 1.213 | 1.078 | 12.01% | 9.76% | -10.79% | 1.11 | 458% |
| SPY-RV binary | blend | 1.267 | 1.125 | 12.00% | 9.30% | -9.74% | 1.23 | - |
| SPY-RV cont | cpm | 1.299 | 1.173 | 14.01% | 10.54% | -15.11% | 0.93 | 348% |
| SPY-RV cont | blend | 1.354 | 1.215 | 13.23% | 9.53% | -9.22% | 1.43 | - |
| book-RV binary | cpm | 0.915 | 0.774 | 8.43% | 9.33% | -13.41% | 0.63 | 625% |
| book-RV binary | blend | 1.149 | 0.994 | 9.89% | 8.54% | -10.54% | 0.94 | - |
| book-RV cont | cpm | 1.215 | 1.090 | 13.09% | 10.60% | -14.51% | 0.90 | 402% |
| book-RV cont | blend | 1.311 | 1.171 | 12.69% | 9.47% | -8.88% | 1.43 | - |

### Stress window

| Variant | Sleeve | Raw Sharpe | Excess Sharpe | CAGR | Vol | MaxDD | Calmar | Turnover/yr |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| V0 (no gate) | cpm | 1.218 | 1.014 | 13.99% | 11.28% | -15.91% | 0.88 | 324% |
| V0 (no gate) | blend | 1.291 | 1.056 | 12.65% | 9.58% | -11.79% | 1.07 | - |
| SPY-RV binary | cpm | 1.239 | 1.006 | 12.12% | 9.61% | -11.60% | 1.05 | 475% |
| SPY-RV binary | blend | 1.248 | 1.001 | 11.48% | 9.03% | -9.74% | 1.18 | - |
| SPY-RV cont | cpm | 1.243 | 1.027 | 13.36% | 10.54% | -15.60% | 0.86 | 372% |
| SPY-RV cont | blend | 1.291 | 1.049 | 12.25% | 9.28% | -11.14% | 1.10 | - |
| book-RV binary | cpm | 0.954 | 0.698 | 8.44% | 8.91% | -13.41% | 0.63 | 615% |
| book-RV binary | blend | 1.125 | 0.852 | 9.30% | 8.20% | -10.54% | 0.88 | - |
| book-RV cont | cpm | 1.217 | 0.997 | 12.85% | 10.38% | -15.15% | 0.85 | 408% |
| book-RV cont | blend | 1.281 | 1.035 | 11.95% | 9.13% | -10.08% | 1.19 | - |

## 2. Crisis / calendar returns (60/40 blend)

| Variant | 2008 (stress) | 2020 (stress) | 2022 (clean) | 2020 (clean) |
| --- | --- | --- | --- | --- |
| V0 (no gate) | 15.17% | 23.42% | 4.95% | 23.42% |
| SPY-RV binary | 15.41% | 23.42% | 0.94% | 23.42% |
| SPY-RV cont | 13.64% | 21.40% | 3.56% | 21.40% |
| book-RV binary | 22.11% | 20.84% | 4.89% | 20.84% |
| book-RV cont | 15.18% | 21.42% | 4.94% | 21.42% |

(2020 appears in both windows; clean window starts 2008 so 2020 is present in both. Shown twice as a consistency cross-check.)

## 3. Vol-gate activity diagnostic


### Clean window

`fired` = vol signal triggered. `gated` = signal triggered AND base CPM had risky exposure to cut (so the overlay actually changed weights).

| Variant | months | fired (signal) | % fired | gated (effective) | % gated |
| --- | --- | --- | --- | --- | --- |
| SPY-RV binary | 217 | 70 | 32.3% | 52 | 24.0% |
| SPY-RV cont | 217 | 70 | 32.3% | 51 | 23.5% |
| book-RV binary | 217 | 80 | 36.9% | 75 | 34.6% |
| book-RV cont | 217 | 80 | 36.9% | 74 | 34.1% |

### Stress window

`fired` = vol signal triggered. `gated` = signal triggered AND base CPM had risky exposure to cut (so the overlay actually changed weights).

| Variant | months | fired (signal) | % fired | gated (effective) | % gated |
| --- | --- | --- | --- | --- | --- |
| SPY-RV binary | 327 | 111 | 33.9% | 89 | 27.2% |
| SPY-RV cont | 327 | 111 | 33.9% | 88 | 26.9% |
| book-RV binary | 327 | 126 | 38.5% | 120 | 36.7% |
| book-RV cont | 327 | 126 | 38.5% | 119 | 36.4% |

## 4. COHORT diagnostic (Moreira-Muir variance-reduction test)

For months the vol gate fires, the forward 1-calendar-month return of the V0 (ungated) CPM book is split into **bad-forward** (fwd <= 0, gate correct / true positive) vs **good-forward** (fwd > 0, false positive), with mean + forward realized vol (annualized daily-return std within the forward month) for each cohort. Key question: is the gated cohort genuinely higher-vol (the variance-reduction value) even if direction is near-symmetric?


### Clean window - SIG-RV-SPY fired-month cohorts

Total evaluated months: 216. Fired months: 70 (32.4%). Unconditional mean fwd CPM return: 1.18%, unconditional mean fwd vol: 9.88%.

| Cohort | Count | % of fired | Mean fwd CPM ret | Median | Mean fwd vol (ann) | Median fwd vol |
| --- | --- | --- | --- | --- | --- | --- |
| bad-forward (TP) | 26 | 37.1% | -1.54% | -1.18% | 9.92% | 9.06% |
| good-forward (FP) | 44 | 62.9% | +2.59% | +2.41% | 9.06% | 8.33% |
| ALL FIRED | 70 | 100.0% | +1.06% | +0.92% | 9.38% | 8.46% |

Fired-cohort mean fwd vol 9.38% vs unconditional 9.88% -> NOT higher (no variance-reduction value).

### Clean window - SIG-RV-BOOK fired-month cohorts

Total evaluated months: 216. Fired months: 80 (37.0%). Unconditional mean fwd CPM return: 1.18%, unconditional mean fwd vol: 9.88%.

| Cohort | Count | % of fired | Mean fwd CPM ret | Median | Mean fwd vol (ann) | Median fwd vol |
| --- | --- | --- | --- | --- | --- | --- |
| bad-forward (TP) | 30 | 37.5% | -1.77% | -1.63% | 11.09% | 11.47% |
| good-forward (FP) | 50 | 62.5% | +2.89% | +3.03% | 10.74% | 9.72% |
| ALL FIRED | 80 | 100.0% | +1.14% | +0.96% | 10.87% | 10.46% |

Fired-cohort mean fwd vol 10.87% vs unconditional 9.88% -> HIGHER (variance-reduction value present).

### Stress window - SIG-RV-SPY fired-month cohorts

Total evaluated months: 326. Fired months: 111 (34.0%). Unconditional mean fwd CPM return: 1.14%, unconditional mean fwd vol: 10.07%.

| Cohort | Count | % of fired | Mean fwd CPM ret | Median | Mean fwd vol (ann) | Median fwd vol |
| --- | --- | --- | --- | --- | --- | --- |
| bad-forward (TP) | 40 | 36.0% | -1.68% | -1.11% | 10.95% | 10.71% |
| good-forward (FP) | 71 | 64.0% | +2.35% | +2.08% | 9.44% | 8.49% |
| ALL FIRED | 111 | 100.0% | +0.90% | +0.80% | 9.98% | 9.35% |

Fired-cohort mean fwd vol 9.98% vs unconditional 10.07% -> NOT higher (no variance-reduction value).

### Stress window - SIG-RV-BOOK fired-month cohorts

Total evaluated months: 326. Fired months: 126 (38.7%). Unconditional mean fwd CPM return: 1.14%, unconditional mean fwd vol: 10.07%.

| Cohort | Count | % of fired | Mean fwd CPM ret | Median | Mean fwd vol (ann) | Median fwd vol |
| --- | --- | --- | --- | --- | --- | --- |
| bad-forward (TP) | 46 | 36.5% | -1.97% | -1.45% | 11.90% | 11.82% |
| good-forward (FP) | 80 | 63.5% | +2.86% | +2.84% | 11.19% | 10.32% |
| ALL FIRED | 126 | 100.0% | +1.09% | +0.96% | 11.45% | 10.74% |

Fired-cohort mean fwd vol 11.45% vs unconditional 10.07% -> HIGHER (variance-reduction value present).

## 5. Redundancy with existing HYG-OR-TIP canary + partial-safe

For each gate variant, of the months the vol SIGNAL fires, how many had the canary ALREADY off / partial under production rules (`base_regime` != RISK_ON or `risky_base` < 1 -> overlap, gate adds nothing new) vs months the canary was fully RISK_ON that the vol gate newly de-risks (NEW risk-off the canary missed). The NEW column is where a vol gate could add value beyond the canary.


### Clean window

| Variant | months fired | canary already off/partial (overlap) | canary RISK_ON, vol newly cuts (NEW) |
| --- | --- | --- | --- |
| SPY-RV binary | 70 | 18 | 52 |
| SPY-RV cont | 70 | 18 | 52 |
| book-RV binary | 80 | 5 | 75 |
| book-RV cont | 80 | 5 | 75 |

### Stress window

| Variant | months fired | canary already off/partial (overlap) | canary RISK_ON, vol newly cuts (NEW) |
| --- | --- | --- | --- |
| SPY-RV binary | 111 | 22 | 89 |
| SPY-RV cont | 111 | 22 | 89 |
| book-RV binary | 126 | 6 | 120 |
| book-RV cont | 126 | 6 | 120 |

### Does the vol gate specifically help 2020 (canary blind spot)?

Fired months during 2020 (signal dates), with base CPM regime under production rules (DEFENSIVE = canary already off):

- **SPY-RV binary**: fired on 2020-01-31(RISK_ON), 2020-02-28(RISK_ON), 2020-03-31(RISK_ON), 2020-04-30(RISK_ON).
- **book-RV binary**: fired on 2020-02-28(RISK_ON), 2020-03-31(RISK_ON), 2020-04-30(RISK_ON), 2020-09-30(RISK_ON).


## 6. Verdict

Baseline V0 (clean blend): Sharpe 1.347, CAGR 13.59%, MaxDD -9.82%, Calmar 1.38.

- **SPY-RV binary** (clean blend): Sharpe 1.267 (-0.080), MaxDD -9.74% (+0.08pp), Calmar 1.23 (-0.15), CAGR 12.00% (-1.59pp).
- **SPY-RV cont** (clean blend): Sharpe 1.354 (+0.007), MaxDD -9.22% (+0.60pp), Calmar 1.43 (+0.05), CAGR 13.23% (-0.36pp).
- **book-RV binary** (clean blend): Sharpe 1.149 (-0.198), MaxDD -10.54% (-0.72pp), Calmar 0.94 (-0.45), CAGR 9.89% (-3.70pp).
- **book-RV cont** (clean blend): Sharpe 1.311 (-0.036), MaxDD -8.88% (+0.94pp), Calmar 1.43 (+0.04), CAGR 12.69% (-0.90pp).


### Synthesis

**1. Does a CPM vol gate improve crisis DD / Calmar beyond V0 after cost?** Only marginally, and only the continuous action. Binary risk-off is strictly bad: SPY-RV binary costs -1.59pp CAGR and -0.080 Sharpe; book-RV binary is worse (-3.70pp CAGR, -0.198 Sharpe, Calmar 0.94 << 1.38) because forcing 100% safe at every RV crossover sells the diversified CPM book at local vol peaks and buys back higher. The continuous action is roughly break-even: SPY-RV cont clean blend Sharpe 1.354 (+0.007), MaxDD -9.22% (0.60pp shallower), Calmar 1.43 (+0.05), at -0.36pp CAGR; book-RV cont is similar (Calmar 1.43, MaxDD -8.88%) but -0.90pp CAGR and -0.036 Sharpe. The DD/Calmar gains are inside noise and bought with a return give-up.

**2. Is the value variance-reduction (high-vol cohort) like the BULL RV gate, or redundant?** The Moreira-Muir variance-reduction thesis that justifies the BULL RV gate does NOT carry over to the SPY-RV signal on CPM. For SIG-RV-SPY the fired-month forward CPM vol (9.38% clean / 9.98% stress) is NOT higher than unconditional (9.88% / 10.07%) - SPY's vol regime does not predict the forward variance of the diversified, min-var-pair CPM book. On BULL the same gate produced a ~21% fired-cohort fwd vol vs ~12% false-positive split; on CPM that asymmetry is absent. The book-RV signal (RV of the CPM book itself) DOES select a genuinely higher-vol cohort (10.87% vs 9.88% clean; 11.45% vs 10.07% stress) - it is a real variance selector - but direction is near-symmetric (~63% false-positive, fired-month mean fwd return still +1.1%), so the binary action that would harvest the variance reduction simultaneously forfeits too much positive carry.

**3. Redundancy with the HYG-OR-TIP canary, and does it help 2020?** The vol gate is mostly NON-redundant in timing: most fired months occur while the canary is still RISK_ON (see section 5 NEW column), and it does fire during the 2020 canary blind spot (SPY-RV fired Jan-Apr 2020 with base RISK_ON). BUT firing in 2020 did not help the outcome: full-year 2020 blend return FALLS from 23.42% (V0) to 21.4% (cont) / 20.8% (binary), because the gate exits into the crash and misses the sharp V-recovery. So it adds new risk-off months the canary misses, but those months are not net-beneficial.

**4. Design-philosophy cost.** A vol gate injects a fast/daily RV crossover into a sleeve that is otherwise monthly-simple (month-end signal, monthly rebalance). It adds a second timescale, raises turnover substantially (binary ~458-625%/yr vs V0 311%; continuous ~348-402%), and couples CPM to a daily-vol estimate - all for a sub-noise Calmar bump.

**Verdict: REJECT.** No vol-gate variant clears the bar of a meaningful, after-cost crisis-DD/Calmar improvement over V0. The only non-negative option (SPY-RV continuous) delivers +0.007 Sharpe / +0.05 Calmar - within noise - while the BULL-style variance-reduction rationale fails to transfer to the diversified CPM book (SPY-RV fired cohort is not higher-vol). The book-RV signal is a genuine variance selector but is direction-symmetric and only usable via the return-destroying binary action. The gate does catch the 2020 canary blind spot in timing, but the trade is net-negative there (misses the recovery). Recommended form if ever revisited: continuous SPY-RV scale only, but not worth the added daily-signal complexity on a monthly-simple sleeve. Keep CPM as-is (canary-only, no vol gate).

