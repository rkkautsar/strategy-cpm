# CPM Overbought / Stretch Filter Evaluation

Tests an overbought screen applied AFTER the positive-trend (Faber) filter in CPM. A candidate must be positive-trend AND not-overbought to enter EAA rank -> K=4 -> min-var pair. Partial-safe fallback (<2 eligible) preserved. **Measurement only; no production files edited.**

- Clean window: 2008-05-30 .. 2026-05-22
- Stress window: 1999-03-10 .. 2026-05-22
- Costs 10bps/side, T+1 OPEN execution (production engine, monkeypatched CTW).
- Blend = 60% CPM + 40% BULL-SPY (two-sleeve baseline).

## 0. V0 baseline verification

60/40 clean: Sharpe **1.347** / CAGR **13.59%** / MaxDD **-9.82%** (target 1.347 / 13.59% / -9.82%) -> MATCH

## 1. KEY DIAGNOSTIC: do overbought asset-months mean-revert or continue?

Universe-wide, point-in-time. For every risky asset at every month-end in the clean window we compute positive-trend (faber>0) and each overbought flag, then the FORWARD 1-month return (month-end to month-end). We compare overbought vs non-overbought *within the positive-trend set* (the only set the screen can act on).

Forward 1m mean return: overbought (OB) vs non-overbought (non-OB), within positive-trend asset-months. **REVERT** (OB worse) supports the filter; **CONTINUE** (OB better) means the filter forfeits winners.

| Group | Measure | N(OB) | OB fwd | N(nonOB) | nonOB fwd | OB - nonOB |
| --- | --- | --- | --- | --- | --- | --- |
| ALL positive | rsi70 | 310 | 0.92% | 837 | 0.80% | +0.12pp CONTINUE |
| ALL positive | rsi80 | 55 | -0.16% | 1092 | 0.89% | -1.05pp REVERT |
| ALL positive | z15 | 260 | 0.86% | 887 | 0.83% | +0.03pp CONTINUE |
| ALL positive | z20 | 117 | 0.60% | 1030 | 0.86% | -0.27pp REVERT |
| ALL positive | pct90 | 156 | 0.99% | 991 | 0.81% | +0.18pp CONTINUE |
| ALL positive | pct95 | 74 | 0.86% | 1073 | 0.83% | +0.03pp CONTINUE |
| equity | rsi70 | 229 | 0.82% | 546 | 1.00% | -0.18pp REVERT |
| equity | rsi80 | 33 | -1.10% | 742 | 1.04% | -2.14pp REVERT |
| equity | z15 | 176 | 0.75% | 599 | 1.01% | -0.26pp REVERT |
| equity | z20 | 75 | 0.29% | 700 | 1.02% | -0.73pp REVERT |
| equity | pct90 | 75 | 1.20% | 700 | 0.92% | +0.28pp CONTINUE |
| equity | pct95 | 30 | 1.43% | 745 | 0.93% | +0.50pp CONTINUE |
| commodity | rsi70 | 17 | 1.92% | 94 | 0.09% | +1.82pp CONTINUE |
| commodity | rsi80 | 6 | 0.84% | 105 | 0.35% | +0.50pp CONTINUE |
| commodity | z15 | 18 | 1.79% | 93 | 0.10% | +1.69pp CONTINUE |
| commodity | z20 | 13 | 2.82% | 98 | 0.05% | +2.77pp CONTINUE |
| commodity | pct90 | 21 | 2.14% | 90 | -0.04% | +2.18pp CONTINUE |
| commodity | pct95 | 11 | 1.69% | 100 | 0.23% | +1.47pp CONTINUE |
| gold | rsi70 | 44 | 1.58% | 99 | 0.64% | +0.94pp CONTINUE |
| gold | rsi80 | 15 | 2.36% | 128 | 0.76% | +1.59pp CONTINUE |
| gold | z15 | 43 | 1.23% | 100 | 0.80% | +0.43pp CONTINUE |
| gold | z20 | 16 | 0.11% | 127 | 1.03% | -0.92pp REVERT |
| gold | pct90 | 33 | 0.53% | 110 | 1.05% | -0.51pp REVERT |
| gold | pct95 | 16 | 0.11% | 127 | 1.03% | -0.92pp REVERT |
| bond | rsi70 | 20 | -0.21% | 98 | 0.54% | -0.75pp REVERT |
| bond | rsi80 | 1 | -13.07% | 117 | 0.53% | -13.60pp REVERT |
| bond | z15 | 23 | 0.28% | 95 | 0.44% | -0.16pp REVERT |
| bond | z20 | 13 | 0.74% | 105 | 0.37% | +0.36pp CONTINUE |
| bond | pct90 | 27 | 0.10% | 91 | 0.51% | -0.40pp REVERT |
| bond | pct95 | 17 | 0.03% | 101 | 0.48% | -0.45pp REVERT |
| diversifier(C+G+B) | rsi70 | 81 | 1.21% | 291 | 0.43% | +0.78pp CONTINUE |
| diversifier(C+G+B) | rsi80 | 22 | 1.24% | 350 | 0.56% | +0.68pp CONTINUE |
| diversifier(C+G+B) | z15 | 84 | 1.09% | 288 | 0.46% | +0.63pp CONTINUE |
| diversifier(C+G+B) | z20 | 42 | 1.14% | 330 | 0.53% | +0.61pp CONTINUE |
| diversifier(C+G+B) | pct90 | 81 | 0.81% | 291 | 0.54% | +0.26pp CONTINUE |
| diversifier(C+G+B) | pct95 | 44 | 0.47% | 328 | 0.62% | -0.14pp REVERT |

## 2. CPM standalone + 60/40 blend metrics

### Clean window -- CPM standalone

| Variant | Raw Sharpe | Excess Sharpe | CAGR | Vol | MaxDD | Calmar | 2022 | 2008 | Turnover |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| V0 (no filter) | 1.263 | 1.145 | 14.58% | 11.30% | -15.41% | 0.95 | 7.49% | -0.08% | 6.28 |
| OB-RSI>70 | 1.166 | 1.047 | 13.14% | 11.13% | -18.48% | 0.71 | 5.11% | 0.71% | 9.89 |
| OB-RSI>80 | 1.285 | 1.167 | 14.72% | 11.19% | -13.12% | 1.12 | 7.49% | 1.40% | 7.33 |
| OB-z>1.5 | 1.318 | 1.196 | 14.75% | 10.91% | -15.40% | 0.96 | 5.11% | -0.13% | 10.39 |
| OB-z>2.0 | 1.301 | 1.183 | 15.03% | 11.27% | -15.13% | 0.99 | 7.49% | 1.40% | 8.83 |
| OB-pct>90 | 1.282 | 1.165 | 14.88% | 11.34% | -15.13% | 0.98 | 2.96% | 1.40% | 10.00 |
| OB-pct>95 | 1.322 | 1.206 | 15.53% | 11.43% | -15.13% | 1.03 | 7.49% | 1.40% | 8.17 |

### Clean window -- 60/40 blend (CPM+BULL)

| Variant | Raw Sharpe | Excess Sharpe | CAGR | Vol | MaxDD | Calmar | 2022 | 2008 | Turnover |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| V0 (no filter) | 1.347 | 1.212 | 13.59% | 9.84% | -9.82% | 1.38 | 4.95% | 6.11% | - |
| OB-RSI>70 | 1.303 | 1.164 | 12.75% | 9.58% | -11.34% | 1.12 | 3.44% | 6.58% | - |
| OB-RSI>80 | 1.352 | 1.217 | 13.66% | 9.85% | -9.82% | 1.39 | 4.95% | 7.03% | - |
| OB-z>1.5 | 1.446 | 1.302 | 13.73% | 9.21% | -9.40% | 1.46 | 3.44% | 6.05% | - |
| OB-z>2.0 | 1.412 | 1.273 | 13.89% | 9.55% | -9.22% | 1.51 | 4.95% | 7.03% | - |
| OB-pct>90 | 1.400 | 1.261 | 13.80% | 9.58% | -9.22% | 1.50 | 2.17% | 7.03% | - |
| OB-pct>95 | 1.418 | 1.281 | 14.18% | 9.70% | -9.22% | 1.54 | 4.95% | 7.03% | - |

### Stress window -- CPM standalone

| Variant | Raw Sharpe | Excess Sharpe | CAGR | Vol | MaxDD | Calmar | 2022 | 2008 | Turnover |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| V0 (no filter) | 1.218 | 1.014 | 13.99% | 11.28% | -15.91% | 0.88 | 7.49% | 12.98% | 6.52 |
| OB-RSI>70 | 1.239 | 1.022 | 13.68% | 10.82% | -18.48% | 0.74 | 5.11% | 2.50% | 10.42 |
| OB-RSI>80 | 1.180 | 0.978 | 13.62% | 11.37% | -17.17% | 0.79 | 7.49% | 6.66% | 7.66 |
| OB-z>1.5 | 1.372 | 1.156 | 15.43% | 10.90% | -17.12% | 0.90 | 5.11% | -4.02% | 10.45 |
| OB-z>2.0 | 1.404 | 1.198 | 16.33% | 11.22% | -15.91% | 1.03 | 7.49% | -2.96% | 9.46 |
| OB-pct>90 | 1.249 | 1.045 | 14.40% | 11.28% | -17.24% | 0.84 | 2.96% | -3.48% | 10.23 |
| OB-pct>95 | 1.297 | 1.094 | 15.20% | 11.41% | -18.25% | 0.83 | 7.49% | -4.30% | 8.58 |

### Stress window -- 60/40 blend (CPM+BULL)

| Variant | Raw Sharpe | Excess Sharpe | CAGR | Vol | MaxDD | Calmar | 2022 | 2008 | Turnover |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| V0 (no filter) | 1.291 | 1.056 | 12.65% | 9.58% | -11.79% | 1.07 | 4.95% | 15.17% | - |
| OB-RSI>70 | 1.320 | 1.072 | 12.46% | 9.22% | -11.59% | 1.08 | 3.44% | 8.51% | - |
| OB-RSI>80 | 1.254 | 1.021 | 12.42% | 9.71% | -12.04% | 1.03 | 4.95% | 11.20% | - |
| OB-z>1.5 | 1.434 | 1.183 | 13.52% | 9.14% | -11.86% | 1.14 | 3.44% | 4.37% | - |
| OB-z>2.0 | 1.444 | 1.204 | 14.04% | 9.40% | -11.71% | 1.20 | 4.95% | 5.07% | - |
| OB-pct>90 | 1.331 | 1.092 | 12.90% | 9.45% | -12.04% | 1.07 | 2.17% | 4.73% | - |
| OB-pct>95 | 1.355 | 1.119 | 13.37% | 9.60% | -11.57% | 1.16 | 4.95% | 4.21% | - |

## 3. Targeted check: DBC/GLD blow-off-top reversal episodes

Did the screen ever flag the diversifier blow-off-tops, and what was the realized forward 1m return at those flagged month-ends?

| Episode window | Asset | Month-end | faber | RSI | z | flags-on | fwd 1m |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2008 H2 commodity | DBC | 2008-04-30 | 21.9% | 84 | 2.93 | rsi70,rsi80,z15,z20,pct90,pct95 | +6.91% |
| 2008 H2 commodity | DBC | 2008-05-31 | 24.3% | 87 | 3.15 | rsi70,rsi80,z15,z20,pct90,pct95 | +10.43% |
| 2008 H2 commodity | DBC | 2008-06-30 | 29.4% | 89 | 3.63 | rsi70,rsi80,z15,z20,pct90,pct95 | -9.78% |
| 2008 H2 commodity | DBC | 2008-07-31 | 12.6% | 73 | 1.56 | rsi70,z15 | -6.53% |
| 2008 H2 commodity | GLD | 2008-01-31 | 24.8% | 84 | 3.68 | rsi70,rsi80,z15,z20,pct90,pct95 | +5.23% |
| 2008 H2 commodity | GLD | 2008-02-29 | 26.3% | 86 | 3.65 | rsi70,rsi80,z15,z20,pct90,pct95 | -6.00% |
| 2008 H2 commodity | GLD | 2008-03-31 | 15.0% | 75 | 2.06 | rsi70,z15,z20,pct90 | -4.16% |
| 2008 H2 commodity | GLD | 2008-06-30 | 6.9% | 72 | 0.95 | rsi70 | -1.44% |
| 2011 gold peak | GLD | 2011-07-31 | 11.4% | 73 | 1.62 | rsi70,z15 | +12.27% |
| 2011 gold peak | GLD | 2011-08-31 | 21.3% | 79 | 2.92 | rsi70,z15,z20,pct90,pct95 | -11.06% |

## 4. Attribution: equity-only vs diversifier-only screen

The whole-universe z-screen improves clean Sharpe, but Section 1 says diversifier (commodity/gold) overbought CONTINUES while equity overbought mildly REVERTS. This ablation applies the screen to ONLY one class to attribute the Sharpe change. 60/40 blend, both windows.

| Variant | Window | Raw Sharpe | Excess Sharpe | CAGR | MaxDD | Calmar | 2008 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| V0 (no filter) | Clean | 1.347 | 1.212 | 13.59% | -9.82% | 1.38 | 6.11% |
| V0 (no filter) | Stress | 1.291 | 1.056 | 12.65% | -11.79% | 1.07 | 15.17% |
| OB-z>1.5 equity-only | Clean | 1.389 | 1.250 | 13.53% | -9.87% | 1.37 | 6.11% |
| OB-z>1.5 equity-only | Stress | 1.386 | 1.146 | 13.24% | -11.25% | 1.18 | 15.17% |
| OB-z>1.5 diversifier-only | Clean | 1.359 | 1.227 | 14.03% | -9.40% | 1.49 | 6.05% |
| OB-z>1.5 diversifier-only | Stress | 1.285 | 1.050 | 13.00% | -11.86% | 1.10 | 4.44% |
| OB-z>2.0 equity-only | Clean | 1.402 | 1.266 | 14.05% | -9.82% | 1.43 | 6.11% |
| OB-z>2.0 equity-only | Stress | 1.406 | 1.170 | 13.77% | -11.71% | 1.18 | 15.17% |
| OB-z>2.0 diversifier-only | Clean | 1.329 | 1.194 | 13.40% | -9.22% | 1.45 | 7.03% |
| OB-z>2.0 diversifier-only | Stress | 1.270 | 1.034 | 12.57% | -11.79% | 1.07 | 5.07% |

## 5. Verdict

Baseline V0 60/40 clean Sharpe **1.347**, MaxDD **-9.82%**, Calmar **1.38**, full-2008 (stress) **15.17%**.

Highest-Sharpe whole-universe variant: **OB-z>1.5** -> clean Sharpe 1.446 (delta +0.099), MaxDD -9.40%, Calmar 1.46.

### Recommendation: REJECT as a diversifier blow-off-top filter.

Reasoning (the headline Sharpe bump is real but for the WRONG reason):

1. **Premise falsified by the diagnostic (Section 1).** Within positive-trend asset-months, diversifier overbought months CONTINUE, not revert: commodity z>2.0 OB fwd +2.82% vs +0.05% (+2.77pp), gold rsi>80 +2.36% vs +0.76% (+1.59pp), diversifier(C+G+B) z>1.5 +1.09% vs +0.46% (+0.63pp). This is textbook momentum-continuation: excluding overbought DBC/GLD on average forfeits next-month gains.
2. **The Sharpe gain is an EQUITY short-term-reversal artifact, not the diversifier thesis (Section 4).** Equity-only z-screen captures almost all of the whole-universe clean Sharpe improvement, while diversifier-only screening adds little-to-negative value and damages the crisis year. The filter 'works' by trimming overbought equity (which mildly reverts: equity z>2.0 -0.73pp), which is a different, known effect unrelated to catching DBC/GLD tops.
3. **It does the OPPOSITE of its design goal in the crisis.** Full-year 2008 (stress window) collapses from V0 +15.17% to roughly +4-5% (z) / +4.2% (pct95) at the blend level, because the H1-2008 commodity & gold safe-haven momentum run -- the very diversifier trend that carried CPM through the crisis -- is overbought and gets excluded. Section 3 shows the mixed reality: it catches DBC 2008-06-30 (fwd -9.78%) and GLD 2011-08-31 (-11.06%) but forfeits DBC 2008-04/05 (+6.91%, +10.43%) and GLD 2011-07-31 (+12.27%).
4. **Threshold-fragile.** RSI variants are inconsistent (RSI>70 HURTS clean blend Sharpe to 1.303; RSI>80 is roughly neutral 1.352). The z/pct gains depend on threshold choice. A robust structural edge would not flip sign across nearby thresholds.

### Constructive next step (different experiment)

If an overbought screen is pursued, scope it to **equity candidates only** and NEVER to diversifiers (commodity/gold/bond), per the attribution in Section 4. That isolates the genuine equity short-term-reversal effect while preserving the diversifier crisis-momentum run. That is a distinct hypothesis and should be validated on its own (incl. cost/turnover and 2008 behavior) before any adoption. As specified here -- a universe-wide screen sold as a DBC/GLD blow-off filter -- the classic momentum prior holds and the filter is REJECTED.

