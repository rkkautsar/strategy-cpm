# PROD 60/20/20 (CPM-BULL-NDX) -- full surface regenerated under current production spec

Role: analyst (hypothesis-driven, READ-ONLY re production; no production files changed; no commit). Throwaway harness `research/prod_60_20_20_iv4_surface.py`. Supplies the FRESH number set to correct the STALE README headline surface (README PROD clean was ~1.503 / 17.93% / -11.62% / 1.54, built on the OLD CPM and a different NDX execution convention).

**Production spec:** 60% CPM (`cpm_live.compute_target_weights`, IV4 single-stage inverse-vol top-4) + 20% BULL (`bull_qqq_live`, HAA-Simple Ext SPY, RV_60d<RV_252d vol gate + first-segment entry-cost fix) + 20% NDX (`ndx_sleeve_live`, top-5 PIT NDX raw 13612U, monthly BULL-gated). Monthly rebalance, 10 bps/side.

**Execution convention:** CPM & BULL on T+1 MOO exact-open (mooex, real auto_adjust opens); NDX on T+1 MOO offset=1 close-to-close (exact-open engine unsupported for per-stock PIT NDX universe + delisting). The exact-open engine reproduces the anchor gate exactly; NDX uses close-to-close T+1 MOO because the per-stock PIT NDX universe (constituents + delisting haircut) is unsupported by the exact-open single-panel engine. CPM and BULL legs are byte-identical to the two-sleeve memo run; only the NDX leg carries this minor convention nuance.

**Metric conventions (README):** raw Sharpe (rf=0), excess Sharpe vs SHV, CAGR, Vol, MaxDD, Calmar (=CAGR/|MaxDD|). Windows: clean 2008-05-30..2026-05-22 (18y); extended/stress 1999-03-10..2026-05-22 (27y). Bootstrap: B_ci=2000, B_pwin=5000, block=21d, seed=42.

## 0. Anchor gate

| Gate | Sharpe | MaxDD | Calmar | Expected | Match |
|---|---:|---:|---:|---|---|
| CPM (clean) | 1.1910 | -12.67% | 1.0615 | 1.1910 / -12.67% / 1.0615 | CONFIRMED |
| CPM-BULL 60/40 (clean) | 1.2485 | -10.68% | 1.1928 | 1.2485 / -10.68% / 1.1928 | CONFIRMED |

Both anchors reproduce exactly; the rest of this file is trusted on that basis.

## 1. PROD 60/20/20 headline

| Window | Raw Sharpe (0rf) | Excess Sharpe (vs SHV) | CAGR | Vol | MaxDD | Calmar |
|---|---:|---:|---:|---:|---:|---:|
| **Clean (18y)** | **1.370** | **1.257** | **16.64%** | **11.78%** | **-12.16%** | **1.37** |
| **Extended (27y)** | **1.298** | **1.091** | **14.73%** | **11.06%** | **-12.63%** | **1.17** |

## 2. Sleeve table

### Clean window (18y)

| Sleeve | Raw Sharpe (0rf) | Excess Sharpe (vs SHV) | CAGR | Vol | MaxDD | Calmar |
|---|---:|---:|---:|---:|---:|---:|
| Cross-asset Parity Momentum (CPM) | 1.191 | 1.072 | 13.44% | 11.16% | -12.67% | 1.06 |
| BULL-SPY | 1.081 | 0.955 | 11.44% | 10.57% | -13.35% | 0.86 |
| NDX (monthly BULL-gated) | 1.186 | 1.132 | 30.01% | 24.77% | -35.92% | 0.84 |
| PROD 60/20/20 | 1.370 | 1.257 | 16.64% | 11.78% | -12.16% | 1.37 |

### Extended window (27y)

| Sleeve | Raw Sharpe (0rf) | Excess Sharpe (vs SHV) | CAGR | Vol | MaxDD | Calmar |
|---|---:|---:|---:|---:|---:|---:|
| Cross-asset Parity Momentum (CPM) | 1.214 | 1.006 | 13.71% | 11.09% | -15.93% | 0.86 |
| BULL-SPY | 0.920 | 0.700 | 9.49% | 10.45% | -13.96% | 0.68 |
| NDX (monthly BULL-gated) | 1.014 | 0.905 | 21.48% | 21.46% | -35.92% | 0.60 |
| PROD 60/20/20 | 1.298 | 1.091 | 14.73% | 11.06% | -12.63% | 1.17 |

*NDX extended-window leg is near-cash before NDX-constituent data begins (~2008); the clean 18y window is the decisive lens for the NDX leg.*

## 3. NDX-blend comparison (raw-momentum checkpoints)

| Window | NDX Sharpe | NDX CAGR | NDX MaxDD | Blend Sharpe | Blend CAGR | Blend MaxDD |
|---|---:|---:|---:|---:|---:|---:|
| Clean | 1.186 | 30.01% | -35.92% | 1.370 | 16.64% | -12.16% |
| Stress | 1.014 | 21.48% | -35.92% | 1.298 | 14.73% | -12.63% |

## 4. Bootstrap CI -- PROD 60/20/20 (stationary block bootstrap)

Method/B per `research/bootstrap_ci_2026_05_28*`: block bootstrap, B=2000, block=21d, seed=42; percentile CI.

### Clean (18y)

| Metric | Point | p2.5 | p25 | p50 | p75 | p97.5 |
|---|---:|---:|---:|---:|---:|---:|
| Sharpe | 1.370 | 0.954 | 1.224 | 1.372 | 1.521 | 1.823 |
| CAGR | 16.69% | 11.25% | 14.81% | 16.66% | 18.68% | 22.61% |
| Vol | 11.78% | 11.01% | 11.50% | 11.78% | 12.07% | 12.64% |
| MaxDD | -12.16% | -24.58% | -18.18% | -15.56% | -13.52% | -10.85% |
| Calmar | 1.372 | 0.525 | 0.843 | 1.069 | 1.314 | 1.901 |

**Sharpe point 1.370, 95% CI [0.954, 1.823].**

### Extended (27y)

| Metric | Point | p2.5 | p25 | p50 | p75 | p97.5 |
|---|---:|---:|---:|---:|---:|---:|
| Sharpe | 1.298 | 0.952 | 1.180 | 1.291 | 1.408 | 1.640 |
| CAGR | 14.73% | 10.60% | 13.25% | 14.65% | 16.04% | 18.95% |
| Vol | 11.06% | 10.40% | 10.82% | 11.04% | 11.28% | 11.68% |
| MaxDD | -12.63% | -27.17% | -19.51% | -16.87% | -14.90% | -12.22% |
| Calmar | 1.166 | 0.452 | 0.703 | 0.861 | 1.028 | 1.403 |

**Sharpe point 1.298, 95% CI [0.952, 1.640].**

## 5. Alpha / beta / R^2 decomposition (clean window)

OLS daily-return regression `r_strat = alpha + beta * r_bench`; alpha annualized (alpha_daily * 252).

| Strategy | Benchmark | Alpha (%/yr) | Beta | Corr | R^2 |
|---|---|---:|---:|---:|---:|
| Cross-asset Parity Momentum (CPM) | B2: AAA + TIP canary (same universe) | +4.75 | 0.834 | 0.791 | 0.625 |
| BULL | B3: HAA-Simple SPY | +4.48 | 0.589 | 0.668 | 0.446 |
| NDX (monthly BULL-gated) | QQQ buy-hold | +22.09 | 0.400 | 0.360 | 0.130 |
| PROD 60/20/20 | BB4 (best lit 60/20/20) | +4.85 | 0.947 | 0.800 | 0.640 |
| PROD 60/20/20 | BB1 (60% AAA+TIP + 40% HAA-S SPY) | +6.01 | 0.933 | 0.764 | 0.583 |
| PROD 60/20/20 | SPY buy-hold | +13.12 | 0.230 | 0.388 | 0.150 |
| PROD 60/20/20 | QQQ buy-hold | +11.73 | 0.242 | 0.458 | 0.210 |

Buy-hold equity alpha is mechanically inflated by time in cash/safe (low realized beta) and is not analytically meaningful; the peer-blend alpha (vs BB4 / BB1) is the real claim.

## 6. Win-probability -- PROD vs BB4 (paired block bootstrap)

Paired difference block bootstrap (B=5000, block=21d, seed=42). BB4 = best literature 60/20/20 blend (60 AAA+TIP / 20 HAA-Simple SPY / 20 QQQ-12mo-trend).

| Comparison | PROD Sharpe | Bench Sharpe | dSharpe median [95% CI] | P(dSharpe>0) | P(dSharpe>0.10) |
|---|---:|---:|---|---:|---:|
| PROD vs BB4 (clean) | 1.370 | 1.198 | +0.175 [-0.124, +0.465] | 87.92% | 69.02% |
| PROD vs BB4 (extended) | 1.298 | 1.142 | +0.154 [-0.085, +0.390] | 90.60% | 68.08% |
| PROD vs B4 HAA-Simple QQQ (clean) | 1.370 | 0.862 | +0.500 [+0.097, +0.883] | 99.40% | 97.38% |

*Naming note: the task parenthetical labels BB4 as the 'HAA-Simple QQQ benchmark'; the established README/harness BB4 is the three-sleeve literature blend (60 B2 + 20 B3 + 20 B5). Both are reported above -- the primary BB4 rows use the three-sleeve blend; the last row uses the single HAA-Simple QQQ (README B4) for completeness.*

## Caveats & confidence

- Anchor-gated: CPM-solo and CPM-BULL 60/40 clean reproduce the locked anchors to <5e-4 on Sharpe/Calmar and <0.02pp on MaxDD before any number is emitted.
- NDX leg uses close-to-close T+1 MOO (offset=1); CPM/BULL use exact-open T+1 MOO. This is the decisive convention difference vs the README's prior headline path, which ran the production `run_cpm_backtest`/`run_ndx_backtest` close-to-close engine on the OLD CPM and produced the stale 1.503. Under the current spec with this honest exact-open CPM/BULL convention, PROD clean Sharpe is materially lower.
- Extended/stress window (1999-03-10..) is partially proxy-backed pre-2006-2008 for the CPM trend universe and near-cash for NDX before constituent data begins; the clean 18y window is the decisive lens.
- Benchmark series (B2/B3/B5/BB4/BB1) are computed via `build_dashboard` literature-benchmark helpers (their own monthly close-to-close convention); alpha/beta/win-prob compare the exact-open PROD/sleeves against those series, a minor cross-convention nuance that does not affect the qualitative conclusion.
