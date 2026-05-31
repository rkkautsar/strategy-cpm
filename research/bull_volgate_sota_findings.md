# BULL vol-gate: SOTA-grounded constructions (correct literature signs) vs symmetric RV gate

Role: analyst (hypothesis-driven, read-only re production; writes only to research/; no production/memo files changed; no commit). EXPLORATION ONLY -- a POTENTIAL production BULL improvement; user decides adoption later (OOS-gated). Harness `research/bull_volgate_sota.py`.

**PRIMARY judging metric = CALMAR and MARTIN** (drawdown-adjusted). BULL is a capital-preservation / drawdown-control overlay, NOT a Sharpe-max sleeve. Sharpe / MaxDD / CAGR reported as secondary.

**Motivation.** Prior naive VIX/downside gates (`bull_volgate_impliedvol_findings.md`, `bull_volgate_variants_findings.md`) had the SIGN BACKWARDS vs the literature -- e.g. V4a de-risked when VIX > 1.5*RV20 (HIGH variance-risk-premium), but Bollerslev-Tauchen-Zhou says HIGH VRP predicts HIGH future returns -> stay invested; you de-risk when VRP is LOW. This round tests SOTA-grounded gates with the CORRECT signs. Replace ONLY the vol-gate layer; canary (TIP 13612U>0) + trend (SPY 13612U>0) + safe (best{SHV,IEF} by 13612U) unchanged.

**Gates (correct literature sign), each as REPLACE (R) and ADD (A).** ADD combine = risk-on requires RV-gate AND new-gate (de-risk if EITHER fires) -- the conservative drawdown-overlay combine.

- **G1 VRP-correct (Bollerslev-Tauchen-Zhou)**: VRP = VIX^2 - RV22^2 (variance points). de-risk when VRP <= 0 (realized caught/exceeded implied) OR below rolling-252d 10th pct; stay invested when VRP positive/high. OPPOSITE of the old VIX>1.5*RV sign.
- **G2 SKEW-complacency (Bevilacqua-Tunaru / volatility paradox)**: LOW CBOE SKEW = complacency = crash 6-12mo ahead. de-risk when SKEW < rolling-252d 10th/20th pct; invested otherwise. Most drawdown-aligned candidate; THRESHOLD/lookback TUNING RISK flagged.
- **G3 Semivariance-divergence (Patton-Sheppard)**: RS-/RS+ over trailing 22d signed daily returns. de-risk when RS-/RS+ ELEVATED (>=252d 80th pct, bad-vol expanding) AND VIX LOW (< 252d median, options complacent); invested otherwise.
- **G4 term-structure confirm (ADD only)**: RV AND VIX<VIX3M (contango). VIX vs VIX3M already tested in bull_strengthen_macro (REPLACE lowers Sharpe; ADD helps 2020 DD only); VIX3M starts 2006-07 -> pre-2006 degraded. Included only as ADD confirm.

**Convention (canonical).** T+1 MOO exact (`mooex`, real auto_adjust opens), 10 bps/side, monthly month-end signal. Windows: clean 2008-05-30..2026-05-22 (18y, decisive lens); ext 1999-03-10..2026-05-22 (27y, partly proxy-backed pre-2006-08). Metrics from production `perf_metrics`.

**Data.** ^VIX (1990-01-02..2026-05-29); ^SKEW (1990-01-02..2026-05-29); ^VIX3M (2006-07-17..2026-05-29). VIX3M-limited variant (G4A_termstruct) runs RV-only pre-2006 -> read CLEAN only; ext degraded. VRP/SKEW have FULL ext history (1990+).

## 0. Anchor gate

BULL V0 symmetric-gate clean Sharpe **1.1005** / Calmar **0.8189** / Martin **3.0714** / MaxDD **-13.35%** vs anchor ~1.1005 / 0.8189 / -13.35% -> **CONFIRMED**. (Martin established as baseline.)

## 1. BULL standalone sleeve metrics -- clean 18y (PRIMARY = Calmar, Martin)

| Variant | Calmar | Martin | Sharpe | MaxDD | CAGR | Vol |
|---|---:|---:|---:|---:|---:|---:|
| V0 symmetric RV60<RV252 (PROD) | 0.8189 | 3.0714 | 1.1005 | -13.35% | 10.93% | 9.90% |
| G1R VRP>0 (REPLACE) | 0.4547 | 1.8493 | 0.8358 | -20.41% | 9.28% | 11.44% |
| G1R VRP>r252-p10 (REPLACE) | 0.7052 | 2.4458 | 0.9250 | -14.54% | 10.26% | 11.28% |
| G1A RV AND VRP>0 (ADD) | 0.7574 | 2.6756 | 1.0383 | -13.35% | 10.11% | 9.77% |
| G2R SKEW>=r252-p20 (REPLACE) | 0.3211 | 1.1580 | 0.8462 | -29.17% | 9.37% | 11.39% |
| G2R SKEW>=r252-p10 (REPLACE) | 0.3400 | 1.2427 | 0.8833 | -29.17% | 9.92% | 11.49% |
| G2A RV AND SKEW>=p20 (ADD) | 0.7211 | 2.4649 | 1.0015 | -13.35% | 9.62% | 9.67% |
| G3R semivar-divergence (REPLACE) | 0.7647 | 2.8904 | 0.9711 | -14.47% | 11.07% | 11.53% |
| G3A RV AND not-semivar-div (ADD) | 0.7827 | 3.0714 | 1.1052 | -13.35% | 10.45% | 9.42% |
| G4A RV AND VIX<VIX3M (ADD) | 0.8646 | 3.0690 | 1.0826 | -12.09% | 10.45% | 9.64% |

### Ext 27y (partly proxy-backed; G4 degraded pre-2006)

| Variant | Calmar | Martin | Sharpe | MaxDD | CAGR |
|---|---:|---:|---:|---:|---:|
| V0 symmetric RV60<RV252 (PROD) | 0.7101 | 2.5820 | 1.0207 | -13.35% | 9.48% |
| G1R VRP>0 (REPLACE) | 0.4506 | 2.0647 | 0.8724 | -20.41% | 9.20% |
| G1R VRP>r252-p10 (REPLACE) | 0.6330 | 2.2709 | 0.8878 | -14.54% | 9.21% |
| G1A RV AND VRP>0 (ADD) | 0.6700 | 2.3451 | 0.9769 | -13.35% | 8.94% |
| G2R SKEW>=r252-p20 (REPLACE) | 0.3238 | 1.4094 | 0.9277 | -29.17% | 9.45% |
| G2R SKEW>=r252-p10 (REPLACE) | 0.3243 | 1.4079 | 0.9044 | -29.17% | 9.46% |
| G2A RV AND SKEW>=p20 (ADD) | 0.6365 | 2.2574 | 0.9567 | -13.35% | 8.50% |
| G3R semivar-divergence (REPLACE) | 0.7023 | 2.7267 | 0.9540 | -14.47% | 10.16% |
| G3A RV AND not-semivar-div (ADD) | 0.6716 | 2.2806 | 1.0133 | -13.35% | 8.96% |
| G4A RV AND VIX<VIX3M (ADD) (deg) | 0.7582 | 2.5648 | 1.0078 | -12.09% | 9.17% |

### Delta vs V0 (clean): Calmar / Martin / Sharpe / MaxDD

| Variant | dCalmar | dMartin | dSharpe | dMaxDD (pp) | dCAGR (pp) |
|---|---:|---:|---:|---:|---:|
| V0 symmetric RV60<RV252 (PROD) | +0.0000 | +0.0000 | +0.0000 | +0.00 | +0.00 |
| G1R VRP>0 (REPLACE) | -0.3641 | -1.2221 | -0.2648 | +7.06 | -1.65 |
| G1R VRP>r252-p10 (REPLACE) | -0.1137 | -0.6256 | -0.1756 | +1.20 | -0.67 |
| G1A RV AND VRP>0 (ADD) | -0.0614 | -0.3959 | -0.0623 | -0.00 | -0.82 |
| G2R SKEW>=r252-p20 (REPLACE) | -0.4978 | -1.9134 | -0.2543 | +15.83 | -1.56 |
| G2R SKEW>=r252-p10 (REPLACE) | -0.4788 | -1.8288 | -0.2173 | +15.83 | -1.01 |
| G2A RV AND SKEW>=p20 (ADD) | -0.0978 | -0.6065 | -0.0990 | -0.00 | -1.31 |
| G3R semivar-divergence (REPLACE) | -0.0542 | -0.1810 | -0.1295 | +1.13 | +0.14 |
| G3A RV AND not-semivar-div (ADD) | -0.0362 | -0.0000 | +0.0047 | -0.00 | -0.48 |
| G4A RV AND VIX<VIX3M (ADD) | +0.0457 | -0.0024 | -0.0179 | -1.26 | -0.48 |

*dCalmar/dMartin/dSharpe>0 = better. dMaxDD>0 = deeper drawdown (worse). dCAGR>0 = higher return.*

## 2. Whipsaw + upside-vol-de-risk (clean 18y monthly signals)

Vol-gate de-risk month = canary_ok AND trend_ok AND NOT vol_ok (vol gate is the SOLE binding leg). False de-risk = governed next-month SPY return > 0. Upside-vol-de-risk = de-risk while trailing 63d SPY return is POSITIVE (the de-risk-into-strength failure mode).

| Variant | de-risk months | false-pos | false-pos rate | upside-derisk | upside rate | mean SPY next | mean trail63 |
|---|---:|---:|---:|---:|---:|---:|---:|
| V0 symmetric RV60<RV252 (PROD) | 32 | 19 | 59.4% | 22 | 68.8% | +0.50% | +2.38% |
| G1R VRP>0 (REPLACE) | 13 | 9 | 69.2% | 11 | 84.6% | +1.66% | +1.97% |
| G1R VRP>r252-p10 (REPLACE) | 15 | 10 | 66.7% | 13 | 86.7% | +0.83% | +4.00% |
| G1A RV AND VRP>0 (ADD) | 38 | 22 | 57.9% | 28 | 73.7% | +0.47% | +2.69% |
| G2R SKEW>=r252-p20 (REPLACE) | 16 | 12 | 75.0% | 12 | 75.0% | +1.77% | +4.74% |
| G2R SKEW>=r252-p10 (REPLACE) | 12 | 10 | 83.3% | 9 | 75.0% | +2.19% | +5.03% |
| G2A RV AND SKEW>=p20 (ADD) | 41 | 26 | 63.4% | 30 | 73.2% | +0.69% | +3.15% |
| G3R semivar-divergence (REPLACE) | 11 | 7 | 63.6% | 11 | 100.0% | +0.84% | +3.25% |
| G3A RV AND not-semivar-div (ADD) | 43 | 26 | 60.5% | 33 | 76.7% | +0.59% | +2.60% |
| G4A RV AND VIX<VIX3M (ADD) | 36 | 22 | 61.1% | 25 | 69.4% | +0.82% | +2.47% |

*Lower false-pos rate and FEWER upside-vol-de-risks = the variant punishes upside vol less.*

## 3. Per-crisis protection (BULL sleeve MaxDD / total return in window)

Crash protection (2008, 2020) and grind catches (2018-Q4, 2022) must be KEPT. Each cell = sleeve MaxDD / total return over the window. V0: 2018 Q4 -2.14% / 2022 -0.30% grind catches.

| Variant | 2008 GFC DD/Ret | 2018 Q4 DD/Ret | 2020 COVID DD/Ret | 2022 bear DD/Ret |
|---|---|---|---|---|
| V0 symmetric RV60<RV252 (PROD) | -12.09% / 6.57% | -2.14% / 15.33% | -13.35% / -3.82% | -0.30% / 0.94% |
| G1R VRP>0 (REPLACE) | -12.09% / 6.57% | -10.10% / 10.42% | -13.35% / -2.29% | -10.11% / -0.33% |
| G1R VRP>r252-p10 (REPLACE) | -12.09% / 6.57% | -10.10% / 10.44% | -13.35% / 4.02% | -4.94% / 5.27% |
| G1A RV AND VRP>0 (ADD) | -12.09% / 6.57% | -2.14% / 15.33% | -13.35% / -3.82% | -0.30% / 0.94% |
| G2R SKEW>=r252-p20 (REPLACE) | -12.09% / 6.57% | -3.00% / 14.43% | -13.35% / 4.02% | -10.11% / -0.33% |
| G2R SKEW>=r252-p10 (REPLACE) | -12.09% / 6.57% | -3.00% / 14.43% | -13.35% / 4.02% | -10.11% / -0.33% |
| G2A RV AND SKEW>=p20 (ADD) | -12.09% / 6.57% | -2.14% / 15.33% | -13.35% / -3.82% | -0.30% / 0.94% |
| G3R semivar-divergence (REPLACE) | -12.09% / 6.57% | -10.10% / 10.42% | -13.35% / 4.02% | -10.11% / -0.33% |
| G3A RV AND not-semivar-div (ADD) | -12.09% / 6.57% | -2.14% / 15.33% | -13.35% / -3.82% | -0.30% / 0.94% |
| G4A RV AND VIX<VIX3M (ADD) | -12.09% / 6.57% | -2.14% / 15.33% | -4.68% / 8.03% | -0.30% / 0.94% |

*Windows: 2008 GFC 2008-05-30..2009-06-30; 2018 Q4 2018-01-01..2018-12-31; 2020 COVID 2020-01-01..2020-06-30; 2022 bear 2022-01-01..2022-12-31.*

## 4. Live current state (latest signal month)

Is each variant ON (risk-on, 100% SPY) or OFF (de-risked) right now? Baseline V0 is OFF at SPY highs (RV60 inflated by the recovery rally) -- the de-risk-into-strength concern; does any SOTA gate FIX this? gate short/long = the gate's own comparands (see footnote).

| Variant | signal date | canary | trend | vol_ok | risk-on | gate short | gate long | trail63 |
|---|---|:--:|:--:|:--:|:--:|---:|---:|---:|
| V0 symmetric RV60<RV252 (PROD) | 2026-05-22 | Y | Y | n | OFF | 14.59 | 12.43 | +6.83% |
| G1R VRP>0 (REPLACE) | 2026-05-22 | Y | Y | Y | ON | 16.70 | 10.08 | +6.83% |
| G1R VRP>r252-p10 (REPLACE) | 2026-05-22 | Y | Y | Y | ON | 23616.74 | 4935.17 | +6.83% |
| G1A RV AND VRP>0 (ADD) | 2026-05-22 | Y | Y | n | OFF | 16.70 | 10.08 | +6.83% |
| G2R SKEW>=r252-p20 (REPLACE) | 2026-05-22 | Y | Y | n | OFF | 137.39 | 140.89 | +6.83% |
| G2R SKEW>=r252-p10 (REPLACE) | 2026-05-22 | Y | Y | n | OFF | 137.39 | 139.08 | +6.83% |
| G2A RV AND SKEW>=p20 (ADD) | 2026-05-22 | Y | Y | n | OFF | 137.39 | 140.89 | +6.83% |
| G3R semivar-divergence (REPLACE) | 2026-05-22 | Y | Y | Y | ON | 10.26 | 138.60 | +6.83% |
| G3A RV AND not-semivar-div (ADD) | 2026-05-22 | Y | Y | n | OFF | 10.26 | 138.60 | +6.83% |
| G4A RV AND VIX<VIX3M (ADD) | 2026-05-22 | Y | Y | n | OFF | 16.70 | 20.03 | +6.83% |

*gate short/long (x100): V0 RV60 vs RV252; G1R-pos VIX vs RV22; G1R-p10 VRP vs p10-thr (variance pts, x100); G2 SKEW vs pct-thr; G3 RS-/RS+ ratio vs p80-thr; G4 VIX vs VIX3M.*

## 5. Annualized turnover (clean 18y, two-way, monthly state flips)

| Variant | Annualized turnover |
|---|---:|
| V0 symmetric RV60<RV252 (PROD) | 378.3% |
| G1R VRP>0 (REPLACE) | 500.6% |
| G1R VRP>r252-p10 (REPLACE) | 522.9% |
| G1A RV AND VRP>0 (ADD) | 422.8% |
| G2R SKEW>=r252-p20 (REPLACE) | 511.8% |
| G2R SKEW>=r252-p10 (REPLACE) | 489.5% |
| G2A RV AND SKEW>=p20 (ADD) | 445.0% |
| G3R semivar-divergence (REPLACE) | 545.1% |
| G3A RV AND not-semivar-div (ADD) | 489.5% |
| G4A RV AND VIX<VIX3M (ADD) | 445.0% |

## 6. VERDICT (PRIMARY = Calmar / Martin)

Scorecard ranked by CALMAR (primary). Crash-protection = 2008 & 2020 DD not >2pp deeper than V0; grind-protection = 2018-Q4 & 2022 DD not >3pp deeper than V0:

| Rank | Variant | Calmar | Martin | Sharpe | MaxDD | CAGR | keeps crash? | keeps grind? | live now |
|---:|---|---:|---:|---:|---:|---:|:--:|:--:|:--:|
| 1 | G4A RV AND VIX<VIX3M (ADD) | 0.8646 | 3.0690 | 1.0826 | -12.09% | 10.45% | Y | Y | OFF |
| 2 | V0 symmetric RV60<RV252 (PROD) | 0.8189 | 3.0714 | 1.1005 | -13.35% | 10.93% | Y | Y | OFF |
| 3 | G3A RV AND not-semivar-div (ADD) | 0.7827 | 3.0714 | 1.1052 | -13.35% | 10.45% | Y | Y | OFF |
| 4 | G3R semivar-divergence (REPLACE) | 0.7647 | 2.8904 | 0.9711 | -14.47% | 11.07% | Y | NO | ON |
| 5 | G1A RV AND VRP>0 (ADD) | 0.7574 | 2.6756 | 1.0383 | -13.35% | 10.11% | Y | Y | OFF |
| 6 | G2A RV AND SKEW>=p20 (ADD) | 0.7211 | 2.4649 | 1.0015 | -13.35% | 9.62% | Y | Y | OFF |
| 7 | G1R VRP>r252-p10 (REPLACE) | 0.7052 | 2.4458 | 0.9250 | -14.54% | 10.26% | Y | NO | ON |
| 8 | G1R VRP>0 (REPLACE) | 0.4547 | 1.8493 | 0.8358 | -20.41% | 9.28% | Y | NO | ON |
| 9 | G2R SKEW>=r252-p10 (REPLACE) | 0.3400 | 1.2427 | 0.8833 | -29.17% | 9.92% | Y | NO | OFF |
| 10 | G2R SKEW>=r252-p20 (REPLACE) | 0.3211 | 1.1580 | 0.8462 | -29.17% | 9.37% | Y | NO | OFF |

**NO SOTA-grounded gate BEATS the symmetric V0 on the PRIMARY drawdown objective** (higher Calmar AND Martin, keep 2008/2020 crash + 2018-Q4/2022 grind). V0 (Calmar 0.8189, Martin 3.0714, Sharpe 1.1005) is not beaten on drawdown-adjusted terms. Correct-sign constructions move the right direction relative to the backwards naive gates, but do not clear V0.

**Best-ranked-by-Calmar (keeps crash+grind): G4A RV AND VIX<VIX3M (ADD)** -- Calmar 0.8646 (+0.0457 vs V0), Martin 3.0690 (-0.0024 vs V0), MaxDD -12.09%, Sharpe 1.0826. It IMPROVES Calmar and shrinks MaxDD while keeping every grind+crash catch, but Martin is a statistical TIE (not strictly higher), so it does not clear the dual Calmar-AND-Martin bar. This is an ADD-mode term-structure confirm (VIX<VIX3M), data-limited to 2006+ and already partly covered in bull_strengthen_macro -- the marginal Calmar lift comes almost entirely from cutting the 2020-COVID DD; treat as a thin, single-episode improvement, not a robust edge.

**SKEW-complacency verdict (the a-priori most drawdown-aligned candidate): it FAILS.** In REPLACE mode SKEW gates are the WORST in the whole set (Calmar ~0.32-0.34, MaxDD -29.17% -- a 16pp DEEPER drawdown than V0): a low-SKEW de-risk timer misses the actual crash drawdowns because complacency is a 6-12mo lead, not a precise timer, so it sits de-risked through rallies and still invested into the drop. In ADD mode (G2A) it merely drags V0 down (Calmar 0.7211 < 0.8189). The literature sign is correct but the signal is too imprecise for a monthly drawdown overlay on this sleeve.

**OBJECTIVE MISMATCH flag.** Return-premium signal(s) lift Sharpe but NOT Calmar/Martin: G3A RV AND not-semivar-div (ADD) (Sharpe 1.1052, Calmar 0.7827, Martin 3.0714). Higher Sharpe with equal/worse drawdown-adjusted ratios = the VRP return-premium tilt buys average return at the cost of (or with no help to) drawdown control -- wrong axis for a capital-preservation overlay.

**On the live de-risk-into-strength concern.** V0 is **OFF** right now (RV60 14.59 vs RV252 12.43, trailing-63d +6.83%). Variants ON now: G1R VRP>0 (REPLACE), G1R VRP>r252-p10 (REPLACE), G3R semivar-divergence (REPLACE). A live ON flip fixes the OFF-at-highs symptom but is necessary-not-sufficient -- the 18y drawdown-adjusted backtest decides whether re-risking into rallies pays.

**Overfitting / OOS caveats.** The 252d lookback, the VRP 10th-pct and SKEW 10th/20th-pct thresholds, the semivar 80th-pct / VIX-median cut are a small principled set, NOT grid-tuned -- but ANY gate mined on the same 18y sample risks in-sample selection. The SKEW-complacency gate is the MOST threshold/lookback-exposed (the percentile choice directly sets de-risk frequency) and SKEW's crash-lead is a 6-12mo statistical tendency, NOT a precise timer -- treat SKEW results as suggestive. SKEW/VRP have full 1990+ history (better than VVIX's 2007+); VIX3M (G4) limits to 2006+. This would be a LIVE PRODUCTION CHANGE: requires OOS / walk-forward validation (freeze pre-2015, test 2015+) and a paired bootstrap on the Calmar/Martin deltas before adoption.

## Caveats

- EXPLORATION ONLY; no production/memo edits; no commit. Read-only re production.
- Only the vol-gate layer changes; canary (TIP 13612U>0), trend (SPY 13612U>0) and safe (best{SHV,IEF} by 13612U) held at production values, so the vol gate is the single differentiator.
- Sleeves run on T+1 MOO exact (mooex, real auto_adjust opens), 10 bps/side, via exec_lag_moo_validation_2026_05_30._segment_returns_conv.
- All gates use only data up to the month-end signal date (no lookahead); VIX/SKEW/VIX3M in pct points, reported /100 as decimal in tables where applicable.
- VRP = VIX^2 - RV22^2 in variance points; RV22 = 22d annualized SPY realized vol (pct pts).
- SKEW gate de-risks when SKEW is LOW vs rolling percentile (complacency = crash-ahead sign).
- Semivar gate de-risks when RS-/RS+ >= 252d 80th pct AND VIX < 252d median (both-fire).
- ADD combine = risk-on requires RV-gate AND new-gate (de-risk if either fires).
- Whipsaw / upside-de-risk / live state use a monthly month-grain calendar (signal -> following calendar-month SPY close-to-close return); the daily sleeve backtest uses mooex. Trailing 63d return is the rally proxy.
- VIX3M (2006-07+) limits G4 to clean 18y; ext pre-2006 runs RV-only (degraded) and is flagged.
