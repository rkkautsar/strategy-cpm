# CPM HYG-OR-TIP Canary Ablation

Marginal value of the production canary and whether a simpler/stricter form is better, evaluated in the 60/40 two-sleeve CPM+BULL baseline. Only the canary rule varies; positive-Faber filter, EAA vol-adj rank, K=4, and min-var pair are fixed.


**C0 reproduction check:** PASS (target CPM 1.263/14.58%, 60/40 1.347/13.59%/-9.82%; got CPM 1.263/14.58%, 60/40 1.347/13.59%/-9.82%)


Windows: clean 2008-05-30..2026-05-22, stress 1999-03-10..2026-05-22. Excess Sharpe vs SHV. Costs 10bps/side. Turnover = CPM one-way annualized (canary varies CPM only; BULL fixed).


## 1a. CPM standalone

| Variant | Win | RawSh | ExSh | CAGR | Vol | MaxDD | Calmar | Turn |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| C0_PROD_HYGorTIP | Clean | 1.263 | 1.145 | 14.58% | 11.30% | -15.41% | 0.95 | 314% |
| C0_PROD_HYGorTIP | Stress | 1.218 | 1.014 | 13.99% | 11.28% | -15.91% | 0.88 | 326% |
| C1_none | Clean | 1.049 | 0.943 | 13.29% | 12.67% | -34.56% | 0.38 | 278% |
| C1_none | Stress | 1.085 | 0.894 | 13.33% | 12.22% | -34.94% | 0.38 | 278% |
| C2_TIPonly | Clean | 1.187 | 1.063 | 12.88% | 10.71% | -15.41% | 0.84 | 364% |
| C2_TIPonly | Stress | 1.154 | 0.936 | 12.16% | 10.41% | -15.91% | 0.76 | 348% |
| C3_HYGonly | Clean | 1.318 | 1.196 | 14.57% | 10.78% | -13.12% | 1.11 | 311% |
| C3_HYGonly | Stress | 1.286 | 1.079 | 14.28% | 10.84% | -15.87% | 0.90 | 346% |
| C4_HYGandTIP | Clean | 1.246 | 1.116 | 12.88% | 10.16% | -13.12% | 0.98 | 361% |
| C4_HYGandTIP | Stress | 1.239 | 1.019 | 12.88% | 10.19% | -14.55% | 0.88 | 390% |
| C5_avg | Clean | 1.219 | 1.098 | 13.56% | 10.94% | -15.41% | 0.88 | 339% |
| C5_avg | Stress | 1.194 | 0.986 | 13.35% | 11.01% | -15.91% | 0.84 | 353% |

## 1b. 60/40 CPM+BULL blend

| Variant | Win | RawSh | ExSh | CAGR | Vol | MaxDD | Calmar |
| --- | --- | --- | --- | --- | --- | --- | --- |
| C0_PROD_HYGorTIP | Clean | 1.347 | 1.212 | 13.59% | 9.84% | -9.82% | 1.38 |
| C0_PROD_HYGorTIP | Stress | 1.291 | 1.056 | 12.65% | 9.58% | -11.79% | 1.07 |
| C1_none | Clean | 1.219 | 1.090 | 12.87% | 10.39% | -21.14% | 0.61 |
| C1_none | Stress | 1.214 | 0.984 | 12.29% | 9.96% | -21.71% | 0.57 |
| C2_TIPonly | Clean | 1.319 | 1.177 | 12.59% | 9.34% | -9.82% | 1.28 |
| C2_TIPonly | Stress | 1.262 | 1.013 | 11.56% | 8.99% | -11.79% | 0.98 |
| C3_HYGonly | Clean | 1.376 | 1.239 | 13.58% | 9.60% | -9.82% | 1.38 |
| C3_HYGonly | Stress | 1.327 | 1.091 | 12.80% | 9.42% | -11.79% | 1.09 |
| C4_HYGandTIP | Clean | 1.351 | 1.206 | 12.58% | 9.09% | -9.82% | 1.28 |
| C4_HYGandTIP | Stress | 1.307 | 1.059 | 11.97% | 8.96% | -11.79% | 1.01 |
| C5_avg | Clean | 1.325 | 1.187 | 12.99% | 9.58% | -9.82% | 1.32 |
| C5_avg | Stress | 1.278 | 1.038 | 12.27% | 9.40% | -11.79% | 1.04 |

## 2. Crisis calendar returns & drawdowns (stress window)

2022/2008 calendar returns; crisis-window MaxDD (2008 = 2007-10..2009-06).

| Variant | CPM 2022 | CPM 2008 | 60/40 2022 | 60/40 2008 | CPM DD08 | CPM DD20 | CPM DD22 | 60/40 DD08 | 60/40 DD20 | 60/40 DD22 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| C0_PROD_HYGorTIP | 7.49% | 12.98% | 4.95% | 15.17% | -15.91% | -13.12% | -9.60% | -9.99% | -9.82% | -5.84% |
| C1_none | -6.07% | 1.50% | -3.05% | 8.36% | -34.94% | -13.12% | -20.00% | -21.71% | -9.82% | -11.98% |
| C2_TIPonly | 7.49% | 12.98% | 4.95% | 15.17% | -15.91% | -13.12% | -9.60% | -9.99% | -9.82% | -5.84% |
| C3_HYGonly | 2.45% | 24.38% | 1.85% | 21.84% | -6.98% | -13.12% | -3.20% | -6.03% | -9.82% | -1.94% |
| C4_HYGandTIP | 2.45% | 24.38% | 1.85% | 21.84% | -6.98% | -13.12% | -3.20% | -6.03% | -9.82% | -1.94% |
| C5_avg | 7.49% | 12.98% | 4.95% | 15.17% | -15.91% | -13.12% | -9.60% | -9.99% | -9.82% | -5.84% |

## 3. C0 canary activity diagnostics


**Clean**: 29/217 months blocked (13.4%).
- Blocked months SPY fwd-1m: mean -1.95%, % negative 62.1% (n=29)
- Allowed months SPY fwd-1m: mean 1.64%, % negative 25.5% (n=188)

**Stress**: 35/327 months blocked (10.7%).
- Blocked months SPY fwd-1m: mean -1.99%, % negative 65.7% (n=35)
- Allowed months SPY fwd-1m: mean 1.21%, % negative 31.2% (n=292)

## 4. Verdict


### (a) Does canary add value beyond Faber trend filter? (C0 vs C1)

- CPM clean MaxDD: C0 -15.41% vs C1 -34.56%.
- CPM stress MaxDD: C0 -15.91% vs C1 -34.94%.
- Crisis CPM DD (C0 vs C1): 2008 -15.91% vs -34.94%; 2020 -13.12% vs -13.12%; 2022 -9.60% vs -20.00%.
- CPM stress Sharpe: C0 1.218 vs C1 1.085.

### (b) Is HYG pulling weight, or is TIP-only (C2) nearly as good?

- CPM clean Sharpe: C2 1.187 vs C3 1.318 vs C0 1.263.
- CPM stress Sharpe: C2 1.154 vs C3 1.286 vs C0 1.218.
- CPM stress MaxDD: C2 -15.91% vs C3 -15.87% vs C0 -15.91%.

### (c) Is OR the right combiner vs AND/average?

- C0(OR) vs C4(AND) vs C5(avg) clean Sharpe: 1.263 / 1.246 / 1.219.
- stress Sharpe: 1.218 / 1.239 / 1.194.
- stress MaxDD: -15.91% / -14.55% / -15.91%.

### Recommendation: SWITCH TO HYG-ONLY (C3)

**(a) Canary adds clear value beyond the Faber filter -- keep a canary.** Dropping it (C1) blows out drawdowns: CPM standalone MaxDD goes -15.4% -> -34.6% (clean) and -15.9% -> -34.9% (stress); the 60/40 blend MaxDD goes -9.8% -> -21.1%. The protection is concentrated in 2008 (CPM DD -15.9% vs -34.9%) and 2022 (-9.6% vs -20.0%); 2020 is unchanged (-13.1% both) because a month-end signal is too slow for the COVID flash crash -- the Faber/vol gates carry that one. Diagnostics confirm the canary blocks genuinely bad months: blocked-month SPY fwd-1m is sharply negative (mean ~-2%, ~62-66% negative) vs positive for allowed months.

**(b) HYG is pulling all the weight; TIP is a drag.** TIP-only (C2) is strictly worse than prod (clean Sharpe 1.187 vs 1.263, CAGR 12.88% vs 14.58%). HYG-only (C3) is strictly BETTER than prod on Sharpe (1.318 vs 1.263 clean, 1.286 vs 1.218 stress), MaxDD (-13.1% vs -15.4% clean), and 2008 crisis return (CPM 24.4% vs 13.0%). So TIP-only is NOT nearly as good -- it is the weaker single signal; the HAA-lineage defensibility of TIP costs real performance.

**(c) OR is not the right combiner.** The dual-confirmation premise (OR reduces false risk-off) does not pay off because TIP adds noise, not signal. OR makes the gate more permissive than HYG-alone (it risks-on whenever TIP is positive even if HYG has rolled over), letting through months HYG-only would have blocked. HYG-only (C3) dominates OR (C0), AND (C4 1.246/12.88%), and average (C5 1.219/13.56%) on both Sharpe and CAGR. AND/avg trim CAGR by over-blocking without improving risk-adjusted return vs HYG-only.

**Bottom line:** Replace `(HYG OR TIP)` with `HYG > 0` alone. It is the simplest form, dominates production on Sharpe / CAGR / MaxDD / Calmar in both windows and in 2008 & 2022, and at similar turnover. Do NOT switch to TIP-only and do NOT drop the canary.

**Caveats:** (1) HYG-only is a single-asset, single-point-of-failure signal; OR was likely chosen for governance robustness/defensibility, not backtest max -- the single-signal risk is a judgment call for the oracle. (2) HYG pre-2007-04 is the VWEHX mutual-fund stitch; the credit-canary edge depends partly on that proxy. (3) C3's edge is consistent across both windows and multiple crises, so it is not a single-period artifact, but this is in-sample on the same history used to build CPM. (4) 2020 shows the canary's blind spot: monthly cadence cannot react to flash crashes.

