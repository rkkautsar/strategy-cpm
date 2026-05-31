# BULL strengthening -- macro / vol-structure gates (VIX term, yield curve)

Role: analyst (hypothesis-driven, read-only re production; writes only to research/; no production/memo files changed; no commit). Harness `research/bull_strengthen_macro.py`.

**Question:** can a VIX term-structure (contango) gate or a yield-curve (inversion) gate strengthen the BULL sleeve's risk-adjusted return / crash protection beyond the current rv_60d<rv_252d (rv60) vol gate -- either ADDED to rv60 or REPLACING it?

**Sleeves:** production `cpm_live` (CPM, HYG-OR-TIP, UNCHANGED) and `bull_qqq_live.compute_bull_qqq_weights` (BULL: TIP-only canary + SPY 13612U trend + a vol-gate slot that we swap) via canonical harness `exec_lag_moo_validation_2026_05_30`. BULL weight engine and CPM are untouched; only the BULL vol-gate slot is monkeypatched.

**Conventions:** T+1 MOO exact (`mooex`, real auto_adjust opens), 10 bps/side. Clean window 2008-05-30..2026-05-22 (apples-to-apples; VIX3M ~2006-07 binds). Ext window 1999-03-10..2026-05-22 (proxy-backed pre-2008; yield curve only, VIX3M absent pre-2006). 60/40 blend = 0.60 CPM + 0.40 enhanced BULL.

**Data sources + windows:**

| Series | Source | Window |
|---|---|---|
| VIX | yfinance | 1990-01-02..2026-05-29 |
| VIX3M | yfinance | 2006-07-17..2026-05-29 |
| T10Y2Y | FRED | 1976-06-01..2026-05-29 |
| T10Y3M | FRED | 1982-01-04..2026-05-29 |

Gate logic: VIX term -> risk-on when VIX < VIX3M (contango/calm); de-risk on backwardation. Yield curve -> risk-on when spread >= 0; de-risk when spread < 0 (inverted), evaluated contemporaneously (L0) and lagged 6/12 months (L6/L12). All gates sampled at month-end signal date; warmup (no macro history) defaults risk-on.

## 0. Anchor sanity

- CPM-solo clean Sharpe 1.1910 (expect ~1.1910) -> OK
- BULL rv60 clean Sharpe 1.1005 (expect ~1.1005) -> OK

## 1. BULL sleeve (clean 2008-05-30..) -- gate comparison

| Variant | Sharpe | CAGR | Vol | MaxDD | Calmar | Safe mo % | Turnover/yr |
|---|---:|---:|---:|---:|---:|---:|---:|
| BULL_rv60 (current baseline) | 1.1005 | 10.93% | 9.90% | -13.35% | 0.8189 | 50% | 2.11 |
| HAA-Simple (no vol gate) | 0.9840 | 11.60% | 11.92% | -20.41% | 0.5685 | 35% | 2.39 |
| VIXterm REPLACE rv | 1.0619 | 11.71% | 11.03% | -14.54% | 0.8050 | 38% | 2.73 |
| VIXterm ADD to rv | 1.0826 | 10.45% | 9.64% | -12.09% | 0.8646 | 52% | 2.45 |
| YC 10y2y L0 REPLACE | 0.9214 | 10.56% | 11.67% | -20.41% | 0.5173 | 39% | 2.17 |
| YC 10y2y L0 ADD | 1.0348 | 9.92% | 9.62% | -13.35% | 0.7429 | 54% | 1.78 |
| YC 10y2y L6 REPLACE | 0.8841 | 9.98% | 11.55% | -20.41% | 0.4890 | 41% | 2.06 |
| YC 10y2y L6 ADD | 1.0411 | 9.94% | 9.57% | -13.35% | 0.7446 | 55% | 1.67 |
| YC 10y2y L12 REPLACE | 0.8708 | 9.68% | 11.40% | -20.41% | 0.4743 | 43% | 2.06 |
| YC 10y2y L12 ADD | 1.0453 | 9.99% | 9.58% | -13.35% | 0.7485 | 54% | 1.78 |
| YC 10y3m L0 REPLACE | 0.9539 | 10.51% | 11.17% | -20.41% | 0.5149 | 45% | 2.17 |
| YC 10y3m L0 ADD | 1.1328 | 10.53% | 9.24% | -12.09% | 0.8707 | 58% | 1.67 |
| YC 10y3m L6 REPLACE | 0.9387 | 10.12% | 10.95% | -20.41% | 0.4959 | 47% | 2.39 |
| YC 10y3m L6 ADD | 1.1386 | 10.34% | 9.03% | -12.09% | 0.8552 | 59% | 2.11 |
| YC 10y3m L12 REPLACE | 0.7568 | 7.79% | 10.71% | -20.41% | 0.3815 | 49% | 2.39 |
| YC 10y3m L12 ADD | 0.9483 | 8.41% | 8.97% | -13.35% | 0.6300 | 59% | 1.89 |

## 2. 60/40 blend (0.60 CPM + 0.40 enhanced BULL, clean)

| Variant | Sharpe | CAGR | Vol | MaxDD | Calmar | 2022 ret |
|---|---:|---:|---:|---:|---:|---:|
| BULL_rv60 (current baseline) | 1.2777 | 12.55% | 9.65% | -10.68% | 1.1746 | 0.12% |
| HAA-Simple (no vol gate) | 1.2314 | 12.85% | 10.28% | -11.32% | 1.1350 | -0.31% |
| VIXterm REPLACE rv | 1.2554 | 12.87% | 10.08% | -11.12% | 1.1576 | -2.03% |
| VIXterm ADD to rv | 1.2739 | 12.36% | 9.54% | -9.90% | 1.2486 | 0.12% |
| YC 10y2y L0 REPLACE | 1.2146 | 12.43% | 10.11% | -11.32% | 1.0983 | -0.31% |
| YC 10y2y L0 ADD | 1.2632 | 12.14% | 9.46% | -10.68% | 1.1367 | 0.12% |
| YC 10y2y L6 REPLACE | 1.2008 | 12.20% | 10.04% | -11.32% | 1.0776 | -0.31% |
| YC 10y2y L6 ADD | 1.2671 | 12.15% | 9.44% | -10.68% | 1.1376 | 0.12% |
| YC 10y2y L12 REPLACE | 1.1955 | 12.07% | 9.99% | -11.32% | 1.0666 | -0.31% |
| YC 10y2y L12 ADD | 1.2676 | 12.17% | 9.45% | -10.68% | 1.1395 | 0.12% |
| YC 10y3m L0 REPLACE | 1.2308 | 12.41% | 9.94% | -11.32% | 1.0959 | -0.31% |
| YC 10y3m L0 ADD | 1.2982 | 12.39% | 9.37% | -9.90% | 1.2517 | 0.12% |
| YC 10y3m L6 REPLACE | 1.2407 | 12.26% | 9.74% | -11.32% | 1.0829 | -0.31% |
| YC 10y3m L6 ADD | 1.3164 | 12.32% | 9.18% | -9.90% | 1.2451 | 0.12% |
| YC 10y3m L12 REPLACE | 1.1637 | 11.30% | 9.64% | -11.32% | 0.9983 | -0.31% |
| YC 10y3m L12 ADD | 1.2457 | 11.53% | 9.13% | -10.68% | 1.0796 | 0.12% |

## 3. Crash-window drawdowns (60/40 blend / BULL sleeve)

2008 = 2008-01-01..2009-06-30 (clean window starts 2008-05-30, so partial GFC). 2020 = 2020-02-01..2020-06-30. 2022 = full calendar year.

| Variant | 2008 blend | 2020 blend | 2022 blend | 2008 BULL | 2020 BULL | 2022 BULL |
|---|---:|---:|---:|---:|---:|---:|
| BULL_rv60 (current baseline) | -9.90% | -10.68% | -3.86% | -12.09% | -13.35% | -0.30% |
| HAA-Simple (no vol gate) | -9.90% | -10.68% | -7.69% | -12.09% | -13.35% | -10.11% |
| VIXterm REPLACE rv | -9.90% | -7.89% | -7.69% | -12.09% | -6.99% | -9.73% |
| VIXterm ADD to rv | -9.90% | -7.89% | -3.86% | -12.09% | -4.68% | -0.30% |
| YC 10y2y L0 REPLACE | -9.90% | -10.68% | -7.69% | -12.09% | -13.35% | -10.11% |
| YC 10y2y L0 ADD | -9.90% | -10.68% | -3.86% | -12.09% | -13.35% | -0.30% |
| YC 10y2y L6 REPLACE | -9.90% | -10.68% | -7.69% | -12.09% | -13.35% | -10.11% |
| YC 10y2y L6 ADD | -9.90% | -10.68% | -3.86% | -12.09% | -13.35% | -0.30% |
| YC 10y2y L12 REPLACE | -9.90% | -10.68% | -7.69% | -12.09% | -13.35% | -10.11% |
| YC 10y2y L12 ADD | -9.90% | -10.68% | -3.86% | -12.09% | -13.35% | -0.30% |
| YC 10y3m L0 REPLACE | -9.90% | -7.89% | -7.69% | -12.09% | -6.99% | -10.11% |
| YC 10y3m L0 ADD | -9.90% | -7.89% | -3.86% | -12.09% | -4.68% | -0.30% |
| YC 10y3m L6 REPLACE | -9.90% | -7.89% | -7.69% | -12.09% | -6.99% | -10.11% |
| YC 10y3m L6 ADD | -9.90% | -7.89% | -3.86% | -12.09% | -4.68% | -0.30% |
| YC 10y3m L12 REPLACE | -9.90% | -10.68% | -7.69% | -12.09% | -13.35% | -10.11% |
| YC 10y3m L12 ADD | -9.90% | -10.68% | -3.86% | -12.09% | -13.35% | -0.30% |

## 4. Ext window (1999-03-10.., proxy-backed) -- BULL sleeve + 60/40

Yield-curve gates have full history here; VIX-term gates run risk-on pre-2006 (no VIX3M), so their ext rows understate any modern edge. Use clean window for the decisive read.

| Variant | BULL Sharpe | BULL MaxDD | BULL Calmar | Blend Sharpe | Blend MaxDD | Blend Calmar |
|---|---:|---:|---:|---:|---:|---:|
| BULL_rv60 (current baseline) | 1.0207 | -13.35% | 0.7101 | 1.2817 | -10.68% | 1.1349 |
| HAA-Simple (no vol gate) | 0.9735 | -20.41% | 0.5259 | 1.2462 | -11.32% | 1.1171 |
| VIXterm REPLACE rv | 0.9981 | -14.54% | 0.7087 | 1.2558 | -11.12% | 1.1209 |
| VIXterm ADD to rv | 1.0078 | -12.09% | 0.7582 | 1.2796 | -10.26% | 1.1693 |
| YC 10y2y L0 REPLACE | 0.9082 | -20.41% | 0.4732 | 1.2337 | -11.32% | 1.0792 |
| YC 10y2y L0 ADD | 0.9738 | -13.35% | 0.6503 | 1.2798 | -10.68% | 1.1051 |
| YC 10y2y L6 REPLACE | 0.8653 | -20.41% | 0.4411 | 1.2205 | -11.32% | 1.0556 |
| YC 10y2y L6 ADD | 0.9793 | -13.35% | 0.6593 | 1.2776 | -10.68% | 1.1095 |
| YC 10y2y L12 REPLACE | 0.9318 | -20.41% | 0.4749 | 1.2491 | -11.32% | 1.0805 |
| YC 10y2y L12 ADD | 1.0022 | -13.35% | 0.6761 | 1.2861 | -10.68% | 1.1181 |
| YC 10y3m L0 REPLACE | 0.9020 | -20.41% | 0.4528 | 1.2342 | -11.32% | 1.0638 |
| YC 10y3m L0 ADD | 1.0352 | -12.09% | 0.7507 | 1.2975 | -10.26% | 1.1659 |
| YC 10y3m L6 REPLACE | 0.9805 | -20.41% | 0.4806 | 1.2920 | -11.32% | 1.0856 |
| YC 10y3m L6 ADD | 1.0805 | -12.09% | 0.7726 | 1.3277 | -10.26% | 1.1772 |
| YC 10y3m L12 REPLACE | 0.8489 | -20.41% | 0.4074 | 1.2286 | -11.32% | 1.0308 |
| YC 10y3m L12 ADD | 0.9146 | -13.35% | 0.5865 | 1.2619 | -10.68% | 1.0723 |

## 5. Verdict

Baseline 60/40 blend (BULL rv60) clean Sharpe **1.2777** (BULL sleeve 1.1005). HAA-Simple blend 1.2314 (BULL 0.9840). Question: does a macro/vol-structure gate beat rv60 beyond noise?

**Deltas vs rv60 baseline (clean window):**

| Variant | d BULL Sharpe | d Blend Sharpe | d BULL Calmar | d Blend MaxDD (pp) | d 2020 BULL DD (pp) |
|---|---:|---:|---:|---:|---:|
| VIXterm ADD to rv | -0.0179 | -0.0038 | +0.0457 | -0.79 | -8.67 |
| YC 10y3m L0 ADD | +0.0323 | +0.0204 | +0.0519 | -0.79 | -8.67 |
| YC 10y3m L6 ADD | +0.0381 | +0.0386 | +0.0363 | -0.79 | -8.67 |
| YC 10y2y L0 ADD | -0.0657 | -0.0146 | -0.0760 | +0.00 | +0.00 |
| VIXterm REPLACE rv | -0.0387 | -0.0223 | -0.0139 | +0.43 | -6.36 |
| YC 10y3m L0 REPLACE | -0.1466 | -0.0469 | -0.3039 | +0.64 | -6.36 |

(d MaxDD / d DD negative = shallower drawdown = better.)

**Findings:**

- REPLACE-rv variants uniformly reduce Sharpe & Calmar vs rv60: rv60 is the better single gate.
- All crash-protection improvement in the clean window comes from ONE event (COVID 2020): 2020 BULL DD -13.35% -> -4.68% for VIXterm-ADD and YC-3m-ADD; 2008 and 2022 unchanged. n=1.
- 10y3m works, 10y2y does NOT (no DD help, lower Sharpe): curve-choice is a researcher degree of freedom / overfitting flag.
- Lag L0~L6 equivalent for the crash, L12 degrades: mild lag sensitivity.
- VIX3M history starts 2006-07: only ~2 crashes in clean window (2008 partial, 2020); thin evidence.
- Sharpe lifts are small (blend +0.02..+0.04) and almost certainly inside bootstrap CI noise; the defensible win is the 2020 DD/Calmar, not Sharpe.

**Bottom line:** 

- *Replacement:* NO. Every macro-only gate (VIX-term or yield-curve, replacing rv60) LOWERS both Sharpe and Calmar. rv60 is the stronger single vol gate; do not replace it.
- *Addition:* MARGINAL, one-event-driven. The most promising is **YC 10y3m inversion ADDED to rv60** (L0 contemporaneous is the cleanest spec: BULL Sharpe 1.1005->1.1328, Calmar 0.819->0.871, blend Sharpe 1.278->1.298, blend MaxDD -10.68%->-9.90%). VIX-term contango ADDED to rv60 achieves nearly identical crash protection (blend MaxDD -9.90%, Calmar 1.249) via a forward-looking implied-vol signal, but slightly LOWERS BULL Sharpe (1.083).
- The entire improvement is the COVID-2020 drawdown (BULL -13.35%->-4.68%); 2008 and 2022 are unchanged. That is a single crash observation, the curve-choice (3m beats 2y) and lag are researcher degrees of freedom, and the Sharpe lift (+0.02..+0.04) sits inside bootstrap noise. Treat as a plausible-but-unproven crash overlay, NOT a clear Sharpe upgrade.
- *Most promising / lowest-overfitting candidate:* **10y3m-inversion-AND-rv60** (contemporaneous, L0). It improves Sharpe AND Calmar AND DD, uses the standard recession indicator, and needs no lag tuning. VIX-term contango is the better *orthogonality* story (implied vs realized) and a reasonable second overlay, but it costs a little Sharpe.
- *Data-window limit:* VIX3M (yfinance ^VIX3M) starts 2006-07, so the VIX-term gate is only testable from ~2008 and sees ~2 crises; the yield-curve gate has long FRED history but its clean-window edge still rests on COVID-2020 only. Recommend a walk-forward / multi-crisis out-of-sample test before any production change.

