# BULL TIP-only recompute -- canonical number set under NEW production

Role: analyst (hypothesis-driven, read-only re production; writes only to research/; no production/memo files changed; no commit). Harness `research/bull_tiponly_recompute.py`. Production BULL canary was changed to TIP-ONLY (`bull_qqq_live.CANARY_ASSETS=["TIP"]`); CPM is UNCHANGED (HYG-OR-TIP). This file is the FRESH number set that REPLACES the old 60/40 headline 1.2485 / -10.68% / 1.1928 (which assumed BULL HYG-OR-TIP).

**Sleeves from production modules** via canonical harness `exec_lag_moo_validation_2026_05_30`: CPM = `cpm_live.compute_target_weights` (HYG-OR-TIP, unchanged); BULL = `bull_qqq_live.compute_bull_qqq_weights` reading production `CANARY_ASSETS=['TIP']` (TIP-only) + slow vol gate rv_60d<rv_252d; NDX = production sleeve (PROD 60/20/20 only).

**Conventions (canonical):** T+1 MOO exact (`mooex`, real auto_adjust opens), post-cost 10 bps/side. Metrics from production `perf_metrics`: CAGR, Vol, raw Sharpe (rf=0), Excess Sharpe vs SHV, MaxDD, Calmar (=CAGR/|MaxDD|), Martin, 2022 cal return. Windows: clean 2008-05-30..2026-05-22 (18y); ext/stress 1999-03-10..2026-05-22 (27y).

**NDX leg caveat (PROD 60/20/20 only):** runs on the production path under T+1 MOO offset=1 (close-to-close; exact-open engine unsupported for per-stock PIT NDX universe + delisting). The exact-open (`mooex`) engine cannot run the per-stock PIT NDX universe with delisting haircuts, so the NDX 20% leg uses close-to-close T+1 MOO while CPM 60% and BULL 20% legs use exact-open T+1 MOO. CPM and BULL legs are byte-identical between the two-sleeve and PROD rows.

## 0. Anchor gate (gate-first)

| Gate | Sharpe | MaxDD | Calmar | Expected | Match |
|---|---:|---:|---:|---|---|
| CPM-solo (clean, UNCHANGED) | 1.1910 | -12.67% | 1.0615 | 1.1910 / -12.67% / 1.0615 | CONFIRMED |
| BULL TIP-only (clean) | 1.1005 | -13.35% | 0.8189 | ~1.1005 / -13.35% | CONFIRMED |

CPM anchor reproduces exactly (unchanged); BULL TIP-only reproduces ~1.1005 / -13.35% from the canary-test mooex run. Rest of file trusted on that basis.

## 1. BULL sleeve (TIP-only) standalone

| Window | CAGR | Vol | Raw Sharpe | Excess Sharpe vs SHV | MaxDD | Calmar |
|---|---:|---:|---:|---:|---:|---:|
| Clean 18y | 10.93% | 9.90% | 1.1005 | 0.9661 | -13.35% | 0.8189 |
| Ext 27y | 9.48% | 9.30% | 1.0207 | 0.7737 | -13.35% | 0.7101 |

## 2. NEW memo headline -- 60/40 blend (CPM HYG-OR-TIP + BULL TIP-only)

Replaces the old 1.2485 / -10.68% / 1.1928. Clean (18y) + ext (27y); 2022 return on clean. 50/50 split and PROD 60/20/20 (3-sleeve, live NDX) re-cited.

| Portfolio | Window | CAGR | Vol | Raw Sharpe | Excess Sharpe vs SHV | MaxDD | Calmar | 2022 Return |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| **CPM/BULL 60/40** | Clean | 12.55% | 9.65% | 1.2777 | 1.1401 | -10.68% | 1.1746 | **0.12%** |
| | Ext | 12.13% | 9.26% | 1.2817 | 1.0358 | -10.68% | 1.1349 | |
| **CPM/BULL 50/50** | Clean | 12.30% | 9.47% | 1.2773 | 1.1370 | -11.12% | 1.1059 | **0.27%** |
| | Ext | 11.71% | 9.01% | 1.2734 | 1.0210 | -11.12% | 1.0524 | |
| *PROD 60/20/20* | Clean | 16.28% | 11.26% | 1.4008 | 1.2827 | -12.16% | 1.3382 | **0.12%** |
| | Ext | 14.59% | 10.44% | 1.3572 | 1.1386 | -12.16% | 1.1996 | |

## 3. Weight-insensitivity sweep (80/20 -> 30/70)

| CPM Weight | BULL Weight | Clean Sharpe | Clean MaxDD | Stress Sharpe | Stress MaxDD |
|---|---|---:|---:|---:|---:|
| 80% | 20% | 1.2480 | -10.09% | 1.2629 | -12.85% |
| 70% | 30% | 1.2674 | -10.25% | 1.2774 | -11.27% |
| 60% | 40% | 1.2777 | -10.68% | 1.2817 | -10.68% |
| 50% | 50% | 1.2773 | -11.12% | 1.2734 | -11.12% |
| 40% | 60% | 1.2646 | -11.56% | 1.2504 | -11.56% |
| 30% | 70% | 1.2395 | -12.01% | 1.2120 | -12.01% |

- **Clean Sharpe band:** 0.0383 (low 1.2395 at 30/70, high 1.2777 at 60/40).
- **Stress Sharpe band:** 0.0698 (low 1.2120 at 30/70, high 1.2817 at 60/40).
- **Verdict:** FLAT (not weight-fitted) -- max Sharpe range 0.0698 across the full 80/20..30/70 sweep.

## 4. CPM-BULL correlation (daily returns)

- **Clean:** 0.6156
- **Stress/ext:** 0.5603

### Side-by-side standalone vs blends (clean window)

| Metric | CPM | BULL (TIP-only) | NDX | 60/40 | 50/50 | PROD 60/20/20 |
| --- | --- | --- | --- | --- | --- | --- |
| **CAGR** | 13.44% | 10.93% | 28.77% | 12.55% | 12.30% | 16.28% |
| **Vol** | 11.16% | 9.90% | 23.32% | 9.65% | 9.47% | 11.26% |
| **Raw Sharpe** | 1.1910 | 1.1005 | 1.2035 | 1.2777 | 1.2773 | 1.4008 |
| **Excess Sharpe** | 1.0719 | 0.9661 | 1.1462 | 1.1401 | 1.1370 | 1.2827 |
| **MaxDD** | -12.67% | -13.35% | -35.92% | -10.68% | -11.12% | -12.16% |
| **Calmar** | 1.0615 | 0.8189 | 0.8009 | 1.1746 | 1.1059 | 1.3382 |
| **2022 Return** | -0.50% | 0.94% | 0.94% | 0.12% | 0.27% | 0.12% |

## 5. Crisis windows + bootstrap CI -- NEW 60/40 blend (clean)

### Crisis-window returns (60/40, mooex)

| Regime | Total Return | CAGR | MaxDD | Sharpe | N days |
|---|---:|---:|---:|---:|---:|
| Dot-com (2000-03..2002-12) | 25.54% | 7.93% | -5.13% | 1.3665 | 716 |
| GFC (2007-10..2009-06) | 11.68% | 6.48% | -9.90% | 0.6506 | 441 |
| COVID (2020-02..2020-06) | 3.22% | 6.73% | -10.68% | 0.6783 | 104 |
| 2022 bear (2022-01..2022-12) | 0.12% | 0.20% | -3.86% | 0.0511 | 251 |

*Note: pre-2008 regimes (Dot-com, GFC start) sit in the proxy-backed extended window; clean 18y starts 2008-05-30 so GFC partially covered.*

### Bootstrap 95% CI (stationary block bootstrap, B=2000, block=21d, seed=42; clean window)

| Metric | p2.5 | p50 (median) | p97.5 | mean |
|---|---:|---:|---:|---:|
| Sharpe | 0.8710 | 1.2775 | 1.6929 | 1.2810 |
| CAGR | 8.34% | 12.55% | 16.95% | 12.61% |
| Vol | 9.01% | 9.66% | 10.35% | 9.66% |
| MaxDD | -21.55% | -13.19% | -9.21% | -13.81% |
| Calmar | 0.4539 | 0.9405 | 1.6935 | 0.9750 |

## 6. BULL decomposition vs HAA-Simple -- the vol-gate (V) effect

Since BULL canary is now TIP-only (shared with HAA-Simple), the canary is no longer a BULL differentiator. BULL = HAA-Simple + vol gate. Holding canary=TIP-only and safe=SHV/IEF fixed at production, the vol gate V is the SINGLE differentiator. Both legs run through the same mooex harness (local `bull_wf`, K=0/S=1; identical logic to the archived factorial decomposition cell).

| Variant | Window | CAGR | Vol | Sharpe | MaxDD | Calmar |
|---|---|---:|---:|---:|---:|---:|
| HAA-Simple (TIP+SPY) | Clean | 11.60% | 11.92% | 0.9840 | -20.41% | 0.5685 |
| HAA-Simple (TIP+SPY) | Ext | 10.73% | 11.11% | 0.9735 | -20.41% | 0.5259 |
| BULL-TIP-only (TIP+SPY+vol) | Clean | 10.93% | 9.90% | 1.1005 | -13.35% | 0.8189 |
| BULL-TIP-only (TIP+SPY+vol) | Ext | 9.48% | 9.30% | 1.0207 | -13.35% | 0.7101 |

**V main effect (vol gate ON minus OFF), clean:** dSharpe +0.1165, dCalmar +0.2504, dMaxDD -7.06pp, dCAGR -0.67pp.

**V main effect, ext:** dSharpe +0.0471, dCalmar +0.1842, dMaxDD -7.06pp, dCAGR -1.26pp.

*Cross-check: bull_wf(K=0,V=1,S=1) clean Sharpe 1.1005 vs production BULL sleeve 1.1005 (|diff|=0.0000) -> MATCH.*

## 7. PROD 60/20/20 (CPM-BULL-NDX) under new BULL TIP-only -- dashboard headline

| Metric | Value (clean 18y) |
|---|---:|
| Raw Sharpe | 1.4008 |
| Excess Sharpe vs SHV | 1.2827 |
| CAGR | 16.28% |
| Vol | 11.26% |
| MaxDD | -12.16% |
| Calmar | 1.3382 |
| 2022 Return | 0.12% |

NDX leg convention: T+1 MOO offset=1 (close-to-close; exact-open engine unsupported for per-stock PIT NDX universe + delisting) (only the 20% NDX leg; CPM 60% and BULL 20% legs are exact-open mooex).

## Caveats

- CPM sleeve UNCHANGED (HYG-OR-TIP); CPM-solo numbers and concentration are NOT recomputed here, only the unchanged anchor is re-cited (Sharpe 1.1910 / MaxDD -12.67% / Calmar 1.0615).
- BULL sleeve now TIP-only canary (production change); all BULL-derived rows reflect that.
- CPM & BULL legs: production weight fns run on T+1 MOO exact (mooex, real auto_adjust opens), 10 bps/side post-cost, BULL slow gate rv_60d<rv_252d.
- NDX leg (PROD 60/20/20 + NDX standalone): production NDX sleeve under T+1 MOO offset=1 close-to-close (exact-open engine unsupported for per-stock PIT universe + delisting).
- Ext/stress window (1999-03-10..) is partially proxy-backed pre-2006-2008; clean 18y has full real-open coverage and is the decisive lens. NDX constituent data does not span the full stress window, so PROD ext-row NDX leg is near-cash pre-data.
- V-effect (section 6) holds canary=TIP-only and safe=SHV/IEF at production; only the vol gate toggles. HAA-Simple here uses SHV/IEF safe (not the BIL/AGG supplied-spec variant) to isolate V apples-to-apples vs production BULL.
- Bootstrap: stationary block bootstrap, B=2000, block=21d, seed=42; resampled on the 60/40 clean-window daily series.
