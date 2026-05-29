# CPM Equity-Only RSI(14)>70 Overbought Screen

Textbook-standard Wilder RSI(14) > 70 (the conventional overbought default). **No threshold scanning** -- RSI>70 is the only spec that counts; RSI>80 and daily->month-end RSI appear only as single robustness points. Screen applied AFTER the positive-trend (Faber) filter and ONLY to the equity sleeve members **{QQQ, SPHQ}** (2 of 8 assets). GLD/DBC/TLT/EFA/EEM/VNQ are never screened. Partial-safe fallback preserved; everything else fixed. **Measurement only; no production files edited.**

- Clean window: 2008-05-30 .. 2026-05-22
- Stress window: 1999-03-10 .. 2026-05-22
- Costs 10bps/side, T+1 OPEN execution (production engine, monkeypatched CTW).
- Blend = 60% CPM + 40% BULL-SPY (two-sleeve baseline).
- **Caveat up front:** the equity sleeve is only 2 of 8 universe names, so the screen's reach is inherently limited.

## 0. V0 baseline verification

60/40 clean: Sharpe **1.347** / CAGR **13.59%** / MaxDD **-9.82%** (target 1.347 / 13.59% / -9.82%) -> MATCH

## 1. Metrics: V0 vs V_RSI70 (CPM standalone + 60/40 blend)

### Clean window -- CPM standalone

| Variant | Raw Sharpe | Excess Sharpe | CAGR | Vol | MaxDD | Calmar | 2022 | 2008 | Turnover |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| V0 (no screen) | 1.263 | 1.145 | 14.58% | 11.30% | -15.41% | 0.95 | 7.49% | -0.08% | 6.28 |
| V_RSI70 (equity RSI14>70, monthly) | 1.071 | 0.958 | 12.65% | 11.80% | -15.41% | 0.82 | 5.11% | -0.08% | 6.89 |
| V_RSI80 (equity RSI14>80, monthly) [robustness] | 1.219 | 1.103 | 14.16% | 11.42% | -15.41% | 0.92 | 7.49% | -0.08% | 6.89 |
| V_RSI70_daily (equity RSI14>70, daily->ME) [robustness] | 1.256 | 1.139 | 14.50% | 11.30% | -15.41% | 0.94 | 7.49% | -0.08% | 7.39 |

### Clean window -- 60/40 blend (CPM+BULL)

| Variant | Raw Sharpe | Excess Sharpe | CAGR | Vol | MaxDD | Calmar | 2022 | 2008 | Turnover |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| V0 (no screen) | 1.347 | 1.212 | 13.59% | 9.84% | -9.82% | 1.38 | 4.95% | 6.11% | - |
| V_RSI70 (equity RSI14>70, monthly) | 1.226 | 1.093 | 12.46% | 10.01% | -10.89% | 1.14 | 3.55% | 6.11% | - |
| V_RSI80 (equity RSI14>80, monthly) [robustness] | 1.318 | 1.184 | 13.35% | 9.90% | -9.82% | 1.36 | 4.95% | 6.11% | - |
| V_RSI70_daily (equity RSI14>70, daily->ME) [robustness] | 1.350 | 1.215 | 13.55% | 9.78% | -9.82% | 1.38 | 4.95% | 6.11% | - |

### Stress window -- CPM standalone

| Variant | Raw Sharpe | Excess Sharpe | CAGR | Vol | MaxDD | Calmar | 2022 | 2008 | Turnover |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| V0 (no screen) | 1.218 | 1.014 | 13.99% | 11.28% | -15.91% | 0.88 | 7.49% | 12.98% | 6.52 |
| V_RSI70 (equity RSI14>70, monthly) | 1.119 | 0.921 | 13.13% | 11.63% | -15.91% | 0.83 | 5.11% | 12.98% | 6.92 |
| V_RSI80 (equity RSI14>80, monthly) [robustness] | 1.189 | 0.986 | 13.72% | 11.36% | -15.91% | 0.86 | 7.49% | 12.98% | 6.92 |
| V_RSI70_daily (equity RSI14>70, daily->ME) [robustness] | 1.214 | 1.010 | 13.94% | 11.28% | -15.91% | 0.88 | 7.49% | 12.98% | 7.25 |

### Stress window -- 60/40 blend (CPM+BULL)

| Variant | Raw Sharpe | Excess Sharpe | CAGR | Vol | MaxDD | Calmar | 2022 | 2008 | Turnover |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| V0 (no screen) | 1.291 | 1.056 | 12.65% | 9.58% | -11.79% | 1.07 | 4.95% | 15.17% | - |
| V_RSI70 (equity RSI14>70, monthly) | 1.234 | 0.999 | 12.15% | 9.68% | -11.79% | 1.03 | 3.55% | 15.17% | - |
| V_RSI80 (equity RSI14>80, monthly) [robustness] | 1.272 | 1.036 | 12.49% | 9.62% | -11.79% | 1.06 | 4.95% | 15.17% | - |
| V_RSI70_daily (equity RSI14>70, daily->ME) [robustness] | 1.294 | 1.057 | 12.62% | 9.54% | -11.79% | 1.07 | 4.95% | 15.17% | - |

**2008 hedge check (stress, 60/40 blend full-year 2008):** V0 +15.17% vs V_RSI70 +15.17% (delta +0.00pp). The screen touches only QQQ/SPHQ, so the DBC/GLD/TLT crisis hedge is structurally untouched.

## 2. Forward-return diagnostic: do overbought equities revert?

For QQQ & SPHQ at every month-end in the clean window, restricted to positive-trend months (faber>0; the only months the screen can act on), compare forward 1-month return when RSI(14)>70 (overbought) vs not. REVERT (OB worse) justifies the screen; CONTINUE (OB better) means the screen forfeits winners.

| Group | N(OB) | OB fwd 1m | N(nonOB) | nonOB fwd 1m | OB - nonOB | Verdict |
| --- | --- | --- | --- | --- | --- | --- |
| equity RSI>70 (both) | 172 | 1.02% | 176 | 1.54% | -0.52pp | REVERT |
| equity RSI>80 (both) [robustness] | 28 | -0.51% | 320 | 1.44% | -1.96pp | REVERT |
| QQQ RSI>70 | 87 | 1.09% | 85 | 1.75% | -0.66pp | REVERT |
| SPHQ RSI>70 | 85 | 0.95% | 91 | 1.35% | -0.39pp | REVERT |

OB>70 win-rate (fwd>0): 65% (n=172); non-OB win-rate: 69% (n=176); OB median fwd +1.33% vs non-OB +1.89%.

## 3. How often does the screen actually bind?

"Binds" = the screen excludes an equity name that V0 would otherwise have **selected into the held pair**. We compare V0 vs V_RSI70 weights-history month by month.

- **Clean**: 216 signal months. Screen BINDS (drops a V0-selected equity) in **71** months (32.9%). Months where a V0-held equity was flagged RSI>70: 71.
- **Stress**: 326 signal months. Screen BINDS (drops a V0-selected equity) in **79** months (24.2%). Months where a V0-held equity was flagged RSI>70: 79.

Binding is NOT rare: despite only 2 equity names, the screen drops a V0-held equity in ~33% of clean months (~24% stress). Equities are exactly the high-momentum names that pass the Faber + EAA rank in risk-on regimes, so they are frequently in the held pair and frequently overbought at the same time. The screen therefore bites often -- but, per Sections 1 and 4, it bites in the WRONG direction (it removes winners mid-trend). High binding frequency + negative payoff = the screen is materially harmful, not negligible.

## 4. Stability: is any effect broad or concentrated?

Annual 60/40-blend return, V0 vs V_RSI70 (clean window), and the delta. A broad edge spreads the delta across many years; a few large cells = luck, not structure (post-toxic-cell skepticism).

| Year | V0 | V_RSI70 | Delta (pp) |
| --- | --- | --- | --- |
| 2008 | +6.11% | +6.11% | +0.00 |
| 2009 | +11.22% | +11.22% | +0.00 |
| 2010 | +12.58% | +12.58% | +0.00 |
| 2011 | +18.04% | +18.04% | +0.00 |
| 2012 | +5.73% | +5.44% | -0.29 |
| 2013 | +24.72% | +11.65% | -13.07 |
| 2014 | +11.71% | +9.19% | -2.52 |
| 2015 | -1.79% | -4.26% | -2.47 |
| 2016 | +10.80% | +11.48% | +0.68 |
| 2017 | +14.91% | +22.38% | +7.47 |
| 2018 | +2.58% | +1.96% | -0.62 |
| 2019 | +11.72% | +11.72% | +0.00 |
| 2020 | +23.42% | +19.63% | -3.79 |
| 2021 | +23.84% | +25.21% | +1.37 |
| 2022 | +4.95% | +3.55% | -1.40 |
| 2023 | +4.38% | +4.38% | +0.00 |
| 2024 | +20.58% | +12.90% | -7.68 |
| 2025 | +24.73% | +25.68% | +0.96 |
| 2026 | +18.54% | +19.84% | +1.30 |

Years with any delta: 13 of 19 (5 positive, 8 negative). Cumulative annual-delta sum -20.07pp. Largest single-year delta: 2013 -13.07pp.
That one year accounts for 30% of total absolute annual delta -> somewhat spread.

## 5. Verdict

60/40 clean Sharpe: V0 **1.347** -> V_RSI70 **1.226** (delta -0.121). Excess Sharpe 1.212 -> 1.093 (-0.119). MaxDD -9.82% -> -10.89% (-1.07pp).
60/40 stress Sharpe: V0 1.291 -> V_RSI70 1.234 (-0.058). 2008 hedge intact (+15.17% -> +15.17%).

### Recommendation: **REJECT.**

The textbook RSI(14)>70 equity-only screen does NOT improve risk-adjusted return -- it degrades it across every cut, with no tuning involved (this IS the conventional spec).

Reasoning:

1. **It hurts the headline metric.** 60/40 clean Sharpe falls 1.347 -> 1.226 (-0.121), Excess Sharpe -0.119, CAGR -1.13pp, and MaxDD WORSENS by 1.07pp (-9.82% -> -10.89%). Stress Sharpe also falls (1.291 -> 1.234). There is no window or metric where RSI>70 helps.

2. **The weak revert signal does not survive the selection mechanics.** Section 2 confirms the prior: overbought equities DO mildly revert in raw forward return (RSI>70 OB -0.52pp vs non-OB; RSI>80 -1.96pp). But the edge is small (OB still +1.02% fwd, 65% win-rate) and the screen does not harvest it cleanly. Excluding an overbought equity from the min-var pair forces CPM into either a partial-safe (equity + 50% cash) or a worse second-best pair, forfeiting the continuation gains in the position actually held. The -0.5pp mean revert is swamped by the opportunity cost of dropping a trend leader, plus extra turnover (6.28 -> 6.89/yr).

3. **The damage is broad AND has a toxic cell.** 8 of 13 active years are negative-delta, cumulative annual delta -20.07pp. The single worst year (2013, -13.07pp) is the classic case: strong, persistent equity uptrend where RSI sits >70 for months and the screen repeatedly ejects the winner. 2024 (-7.68pp) and 2020 (-3.79pp) repeat the pattern. Positive years (2017 +7.47pp) are fewer and smaller. This is the post-toxic-cell failure mode: an apparent statistical edge that, applied through the portfolio, mostly forfeits trending equity gains.

4. **Robustness points agree it is not real edge.** RSI>80 is roughly neutral-to-slightly-negative (clean 1.318) and daily->ME RSI>70 is ~neutral (1.350) -- i.e. the screen only does damage where it actually binds (monthly RSI>70). A genuine structural edge would not require the threshold to bind rarely to avoid harm.

5. **Materiality:** the 2-name equity subset is small, but binding frequency is high (~33% of clean months), so the effect is NOT negligible -- it is materially negative. Small universe reach did not protect it; it just concentrated the harm in trending-equity regimes.

**2008 hedge intact** (+15.17% unchanged): the screen never touches DBC/GLD/TLT, confirming it is structurally isolated to the equity sleeve as designed -- but that isolation does not rescue it.

Net: REJECT. Consistent with the prior finding that equity overbought only "mildly" reverts -- mild is not enough to overcome the cost of dropping trend-leading equities from a momentum strategy.

