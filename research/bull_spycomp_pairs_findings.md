# BULL SPY-COMP TIP+1 pairs ablation (k=1)

Role: analyst (read-only re production; writes only to research/; no prod/memo/cpm_live/bull_qqq_live changed; no commit). Harness `research/cpm_harness.py`; reuses `research/bull_spycomp_composite.py` (warn fns, make_composite, metrics, bootstrap) -- nothing rebuilt.

**Question:** starting from TIP as the ONLY recession indicator, does adding ONE other indicator (2-indicator composite, k=1) materially lift the minimal SPY-COMP gate, and does ANY TIP+1 pair beat the production HAA-Simple AND gate on BOTH Sharpe AND Calmar?

**Gate (all SPY-COMP configs):** `risk_on = (n_warnings < 1) OR spy_trend_up (k=1)` -- 0 warnings ride SPY; >=1 warning defer to SPY 13612U trend; risk-off -> best-of(SHV/IEF). Asset SPY.

**Conventions:** mooex T+1 MOO exact, 10 bps/side, both-252. Clean (decision lens) 2008-05-30..2026-05-22. Ext 1999-03-10..2026-05-22. Anchor verify: {'Sharpe': 1.1658, 'Calmar': 1.0137, 'Martin': 3.6907, 'MaxDD': -0.1297, 'CAGR': 0.1315, 'vol': 0.1118}.

**Monotonicity note:** k=1 + more indicators = more deferral to SPY trend (monotone toward pure trend-following); interpret 'trend' as the trend sleeve direction.

## 1. Sleeve comparison -- clean decision lens

| Config | Sharpe | Calmar | Martin | MaxDD | CAGR | Vol |
|---|---:|---:|---:|---:|---:|---:|
| HAA-Simple (prod AND) | 0.984 | 0.569 | 2.382 | -20.41% | 11.60% | 11.92% |
| TIP-only (k1) | 0.816 | 0.385 | 1.857 | -33.72% | 12.97% | 16.71% |
| tip+vix | 0.890 | 0.595 | 1.796 | -21.39% | 12.72% | 14.71% |
| tip+yc | 0.933 | 0.690 | 2.012 | -20.03% | 13.82% | 15.15% |
| tip+unrate | 0.861 | 0.379 | 1.975 | -33.72% | 12.77% | 15.39% |
| tip+breadth | 0.912 | 0.635 | 1.958 | -19.86% | 12.60% | 14.14% |
| tip+erp | 0.828 | 0.384 | 1.858 | -33.72% | 12.93% | 16.34% |

## 2. Per-crisis drawdown (BULL sleeve, from ext series)

GFC 2007-10..2009-06; COVID 2020-02..2020-06 (fast-crash override risk); 2022 full year; 2025 tariff 2025-02..2025-06.

| Config | GFC_2008 | COVID_2020 | Y2022 | Tariff_2025 |
|---|---:|---:|---:|---:|
| HAA-Simple (prod AND) | -12.09% | -13.35% | -10.11% | -10.04% |
| TIP-only (k1) | -27.31% | -33.72% | -13.76% | -18.76% |
| tip+vix | -25.00% | -13.35% | -13.76% | -10.04% |
| tip+yc | -27.31% | -13.35% | -13.76% | -10.04% |
| tip+unrate | -12.09% | -33.72% | -13.76% | -10.04% |
| tip+breadth | -19.89% | -13.35% | -13.76% | -18.76% |
| tip+erp | -27.31% | -33.72% | -13.76% | -10.04% |

## 3. Does TIP+1 lift the minimal SPY-COMP (vs TIP-only)?

TIP-only (k1): Sharpe 0.816, Calmar 0.385, MaxDD -33.72%. Deltas of each pair vs TIP-only:

| Pair | dSharpe vs TIP-only | dCalmar vs TIP-only | dMaxDD |
|---|---:|---:|---:|
| tip+vix | +0.074 | +0.210 | +12.33pp |
| tip+yc | +0.117 | +0.305 | +13.69pp |
| tip+unrate | +0.045 | -0.006 | -0.00pp |
| tip+breadth | +0.097 | +0.250 | +13.86pp |
| tip+erp | +0.013 | -0.001 | +0.00pp |

## 4. Winners (beat HAA-Simple on BOTH Sharpe AND Calmar, clean)

**NONE.** No TIP+1 pair beat HAA-Simple (Sharpe 0.984, Calmar 0.569) on BOTH Sharpe AND Calmar. Bootstrap and walk-forward skipped (no winner to validate).

## 5. Verdict

**HAA-Simple still wins.** No TIP+1 pair (k=1) beats the production AND gate on both Sharpe and Calmar.

**Why (structural):** at k=1, every added indicator can only ADD warnings, and any single warning flips the gate from 'ride SPY' to 'defer to SPY trend'. So TIP+1 is monotonically MORE permissive-to-trend than TIP-only and strictly more deferral-heavy than the conservative AND gate, which requires BOTH TIP canary AND SPY trend to risk on. For a tail-defense sleeve, the AND gate's conservatism is the value driver; pushing toward pure trend-following via more k=1 warnings does not recover it.

**Discipline:** clean window = decision lens; single in-sample pass; t+1 MOO exact; 10 bps/side; both-252. Overfit DoF here is modest (only pair selection over 5 pairs), but any apparent winner still requires the bootstrap + walk-forward gate above before any adoption claim.

