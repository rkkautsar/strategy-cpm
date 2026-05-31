# CPM Memo Review Additions

Role: analyst (read-only re production/memo; writes research/ only; no commit).
Audience: fixer, to fold the labeled sections below into `cpm_memo.md`.

Scope: the 7 additions requested by the external memo review, computed on
CPM-Core (risky universe QQQ, SPHQ, EFA, EEM, VNQ, GLD, TLT, DBC; HYG-or-TIP
canary; top-4 vol-adjusted Faber; strict-4 partial-safe; SHV/IEF selector),
post-cost (10 bps/side), T+1 MOO exact (mooex, real opens), point-in-time.

## Reproduction gate (anchor first)

Harness parity with the memo headline: same mooex T+1-MOO engine
(`research/exec_lag_moo_validation_2026_05_30._segment_returns_conv`) and the
same data build (`research/cpm_benchmarks_proper.build_data`) used for the memo's
Section 5.5 benchmark table. CPM weights come from the production engine
`cpm_live.compute_target_weights`.

Anchor reproduced byte-for-byte before any new table:

| Metric | Reproduced | Memo headline |
|---|---:|---:|
| Clean Sharpe | 1.1910 | 1.1910 |
| Clean MaxDD | -12.67% | -12.67% |
| Clean Calmar | 1.0615 | 1.0615 |

Commands:

```
.venv/bin/python research/memo_review_additions_compute.py   # items 1-4 + anchor
# items 5/6/7 are documentation-driven (see source findings cited inline)
```

Outputs: `research/memo_review_additions_compute.py`,
`research/memo_review_additions_compute.json`.

Honesty guards carried throughout: point-in-time signal (`loc[:sig_d]`) with
strictly-future fills; clean window (2008-05-30, fully live ETFs) is the decisive
lens; the extended segment is proxy-backed and descriptive only; the 1.19 clean
Sharpe is a single in-sample path (see Section 5 ladder and Section 6 DSR for the
selection / forward haircuts).

---

## ADDITION 1: Common-window EXTENDED comparison

Problem the review flagged: the memo's extended table (Section 5.5) uses
per-series start dates (CPM 1995-01-31, AAA 2008-01-19, 60/40 / naive / buy-hold
1999-03-10), so the rows are not apples-to-apples.

Fix: force a single common start. The latest common start across all five series
is driven by the AAA benchmark, whose history is bounded by RWX inception
(2006-12) plus 12-month momentum warmup -> 2008-01-19. With all five series
forced to that start, the "extended" comparison collapses to essentially the
clean ETF era (this is itself a finding: the canonical AAA benchmark cannot be
extended any earlier in this framework).

### 1A. All-5 common window, start 2008-01-19 -> 2026-05-22

| Series | Sharpe | CAGR | MaxDD | Calmar | Martin |
|---|---:|---:|---:|---:|---:|
| CPM | 1.188 | 13.41% | -12.67% | 1.059 | 3.858 |
| AAA-style available-panel | 0.930 | 9.07% | -21.76% | 0.417 | 1.603 |
| 60/40 (SPY/IEF) | 0.798 | 8.81% | -30.83% | 0.286 | 1.372 |
| Naive 12m momentum | 0.665 | 8.48% | -26.59% | 0.319 | 1.067 |
| Buy-hold inverse-vol | 0.708 | 8.51% | -35.61% | 0.239 | 1.136 |

Read: on a strict common start, CPM still leads every series on Sharpe, CAGR,
MaxDD, Calmar, and Martin. The CPM Sharpe is 1.188 here vs 1.191 in the clean
window only because the window begins ~4 months earlier and picks up early-2008.

### 1B. Genuinely-extended apples-to-apples, ex-AAA, start 1999-03-10 -> 2026-05-22

Because AAA binds the common start to near-clean, this second panel drops AAA and
forces the remaining four to the longer common start (1999-03-10, the QQQ live
inception convention anchor). This is the only way to get a multi-decade
apples-to-apples table; the 1999-2007 segment is proxy-backed (see Addition 7).

| Series | Sharpe | CAGR | MaxDD | Calmar | Martin |
|---|---:|---:|---:|---:|---:|
| CPM | 1.214 | 13.71% | -15.93% | 0.861 | 3.820 |
| 60/40 (SPY/IEF) | 0.691 | 7.31% | -31.44% | 0.232 | 1.071 |
| Naive 12m momentum | 0.816 | 10.11% | -26.59% | 0.380 | 1.428 |
| Buy-hold inverse-vol | 0.842 | 9.56% | -35.61% | 0.268 | 1.435 |

Read: over the common 1999-2026 window CPM leads on every metric; the lead is
widest on drawdown-adjusted ratios (Martin 3.82 vs 1.07-1.44). AAA is omitted
here purely because its panel cannot reach 1999.

Caveat: 1B's pre-2008 segment is proxy-backed and descriptive, not inferential.

---

## ADDITION 2: Leave-one-asset-out robustness (clean window)

Drop each risky asset one at a time; recompute the full CPM stack (same canary,
screen, top-4, inverse-vol, partial-safe) over the clean window 2008-05-30 ->
2026-05-22. Baseline = full 8-asset universe (Sharpe 1.1910 / MaxDD -12.67% /
Calmar 1.0615).

| Dropped | Sharpe | dSharpe | MaxDD | Calmar | dCalmar |
|---|---:|---:|---:|---:|---:|
| (none) baseline | 1.1910 | -- | -12.67% | 1.0615 | -- |
| ex-QQQ | 1.0140 | -0.1770 | -11.34% | 0.9285 | -0.1330 |
| ex-SPHQ | 1.0339 | -0.1570 | -12.24% | 0.9126 | -0.1489 |
| ex-EFA | 1.1799 | -0.0111 | -11.36% | 1.1102 | +0.0487 |
| ex-EEM | 1.2069 | +0.0159 | -11.06% | 1.1457 | +0.0842 |
| ex-VNQ | 1.1163 | -0.0747 | -13.73% | 0.8813 | -0.1803 |
| ex-GLD | 1.0579 | -0.1331 | -14.57% | 0.8277 | -0.2338 |
| ex-TLT | 1.0823 | -0.1087 | -13.86% | 0.9132 | -0.1483 |
| ex-DBC | 1.1248 | -0.0662 | -12.44% | 1.0155 | -0.0460 |

Read / single-asset-dependence flags:
- No single drop breaks the strategy: every ex-asset variant keeps Sharpe >= 1.01
  and MaxDD shallower than -14.6%, still better than every Section 5.5 benchmark
  MaxDD (-21.76% to -34.92%).
- Largest Sharpe sensitivity is the US equity sleeve: ex-QQQ (-0.177) and
  ex-SPHQ (-0.157). Treat the QQQ/SPHQ growth-plus-quality pair as the primary
  return engine, consistent with the asset-concentration table (Section 7.4).
- Largest Calmar / drawdown sensitivity is the diversifier sleeve: ex-GLD
  (Calmar -0.234, MaxDD deepens to -14.57%) and ex-VNQ (Calmar -0.180). Gold is
  the main drawdown-control contributor.
- ex-EEM and ex-EFA slightly IMPROVE Sharpe/Calmar -> emerging and developed-
  international add diversification breadth but are not net return drivers in the
  clean window.
- Verdict: robustness holds. The edge is broad, not propped up by any one asset;
  removing the single most-load-bearing asset (QQQ) still leaves Sharpe ~1.01,
  i.e. in the same quality band as the AAA/60/40 benchmarks.

---

## ADDITION 3: Calendar-year returns (clean window)

Annual total return and worst intra-year drawdown per year, CPM vs AAA-style vs
60/40. Window 2008-05-30 -> 2026-05-22.

Boundary-year caveat: series have different available starts (CPM 2008-05-30,
AAA 2008-01-19, 60/40 1999-03-10), so 2008 (partial for CPM/AAA) and 2026
(partial, Jan-May for all) are NOT cross-series comparable; full-year comparison
is 2009-2025.

| Year | CPM ret | CPM intraDD | AAA ret | AAA intraDD | 60/40 ret | 60/40 intraDD |
|---|---:|---:|---:|---:|---:|---:|
| 2008* | +5.08% | -9.83% | +1.66% | -11.74% | -15.57% | -26.88% |
| 2009 | +14.47% | -7.09% | +0.80% | -11.03% | +13.23% | -17.62% |
| 2010 | +16.62% | -9.15% | +15.59% | -8.38% | +13.42% | -6.95% |
| 2011 | +10.44% | -7.49% | +8.99% | -10.42% | +8.29% | -8.56% |
| 2012 | +6.72% | -4.81% | -3.53% | -10.14% | +11.26% | -4.20% |
| 2013 | +19.47% | -8.79% | +23.75% | -8.34% | +15.60% | -5.24% |
| 2014 | +15.78% | -6.07% | +9.60% | -4.29% | +11.95% | -3.39% |
| 2015 | -0.97% | -6.51% | -1.00% | -6.48% | +1.76% | -6.94% |
| 2016 | +10.36% | -9.43% | +1.71% | -8.15% | +7.80% | -3.87% |
| 2017 | +22.43% | -2.26% | +10.58% | -3.30% | +13.76% | -1.49% |
| 2018 | +1.92% | -10.13% | +0.77% | -8.94% | -1.96% | -10.83% |
| 2019 | +12.41% | -3.72% | +9.18% | -3.03% | +21.78% | -2.68% |
| 2020 | +23.43% | -10.06% | +19.80% | -7.88% | +16.90% | -19.13% |
| 2021 | +26.22% | -4.70% | +25.42% | -5.70% | +15.10% | -3.70% |
| 2022 | -0.50% | -6.33% | -14.25% | -21.76% | -16.39% | -20.67% |
| 2023 | +1.60% | -7.93% | +7.80% | -9.17% | +16.97% | -8.26% |
| 2024 | +15.08% | -7.01% | +17.87% | -6.14% | +14.23% | -4.36% |
| 2025 | +26.47% | -12.67% | +19.12% | -6.29% | +14.33% | -10.60% |
| 2026* | +20.84% | -5.99% | +21.70% | -6.07% | +4.71% | -6.00% |

`*` partial year, not cross-series comparable.

Read:
- CPM's only down years are 2015 (-0.97%), 2022 (-0.50%); never a deep annual
  loss. 60/40 had -15.57% (2008) and -16.39% (2022); AAA had -14.25% (2022).
- 2022 is the standout relative year: CPM -0.50% with intra-year DD only -6.33%,
  vs AAA -14.25% / -21.76% and 60/40 -16.39% / -20.67%. This is the inflation /
  duration-shock regime where conventional portfolios had the least defense.
- CPM intra-year DD exceeds -10% in only 3 years (2018, 2020, 2025); the 2025
  -12.67% is the worst single intra-year drawdown and equals the full-window
  MaxDD.
- 2023 is CPM's relative weak year (+1.60% vs 60/40 +16.97%): a sharp risk-on
  recovery where CPM's defensive posture lagged.

---

## ADDITION 4: Worst-interval table (clean window)

Worst rolling 1-month, 3-month, 12-month total return (month-end compounded),
and longest underwater (drawdown) duration. Window 2008-05-30 -> 2026-05-22.

| Metric | CPM | AAA-style | 60/40 |
|---|---:|---:|---:|
| Worst 1-month return | -6.00% | -7.08% | -9.77% |
| Worst 3-month return | -7.48% | -10.24% | -15.37% |
| Worst 12-month return | -5.24% | -16.86% | -16.39% |
| Longest underwater | 688 days | 903 days | 787 days |

Read:
- CPM dominates on every interval. The worst-12-month gap is the headline: CPM's
  worst rolling year is only -5.24%, vs -16.86% (AAA) and -16.39% (60/40) -- CPM
  has never had a deeply negative rolling year in the clean window.
- Shortest time-to-heal: longest underwater stretch 688 days vs 903 (AAA) and
  787 (60/40), consistent with the memo's fast-crisis-recovery claim.
- This is the strongest single-table support for the capital-preservation thesis.

Caveat: worst-interval and underwater duration are single-path statistics on one
18-year sample; like MaxDD/Calmar they are high-variance and underpowered for
formal significance (consistent with Section 5.5 difference-CI honesty).

---

## ADDITION 5: Forward-Sharpe haircut ladder

Bridge from the in-sample 1.19 to the forward central ~0.72. Selection-deflation
steps use the actual DSR numbers (Addition 6 / `cpm_deflated_sharpe_findings`);
execution and regime steps are reasoned judgmental haircuts (marked J), not
backtested forward results.

| Step | Type | Factor (central / band) | Resulting Sharpe |
|---|---|---|---:|
| 0. In-sample argmax (clean, T+1 MOO) | measured | -- | 1.19 |
| 1. Selection de-peak (expected-max SR0 over correlated search) | measured (DSR) | x 0.82 / [0.79, 0.86] | ~1.00 (0.94-1.02) |
| 2. Execution-realism haircut (month-end cliff, slippage) | judgmental (J) | x 0.85 / [0.765, 0.93] | ~0.83 (0.72-0.95) |
| 3. Regime non-stationarity haircut (OOS trend decay) | judgmental (J) | x 0.88 / [0.80, 0.95] | ~0.72 (0.62-0.85) |
| Forward central | synthesis | -- | ~0.72, range 0.62-0.85 |

Anchoring evidence for each step:
- Step 1 (measured): the selection-inflation haircut = expected-max SR0 over the
  searched family = 0.16-0.25 ann Sharpe. Two independent methods converge:
  the DSR expected-max SR0 (0.16-0.25) and the empirical peak-vs-median gaps
  (1.19 - 0.94 = 0.25 vs full-grid median; 1.19 - 1.02 = 0.17 vs Faber-family
  region median). -> selection-deflated in-sample ~1.00.
- Step 2 (judgmental): grounded in the measured execution cliff. Rebal-day
  {EOM, +1, +2, +3 bd} -> Sharpe {1.21, 1.01, 0.97, 0.91}. Factor 0.765 = full
  EOM+3 (0.91/1.19); 0.93 = disciplined T+1; central 0.85 allows occasional
  slippage. The cliff magnitudes are measured; the chosen forward factor is the
  judgmental part.
- Step 3 (judgmental): 2008-26 was a trending tailwind (subperiod Sharpe
  2008-16 = 1.00 vs 2017-26 = 1.38). Cross-asset momentum OOS-decay literature
  realizes ~0.5-0.7 of in-sample; the 0.80-0.95 factor here is deliberately
  milder than the literature because the DSR confirms a real (non-noise) core.

Honesty: the forward central is a reasoned synthesis, NOT a forward backtest; it
is unvalidatable until OOS data accrues. The 1.19 must stay labeled as the
in-sample peak. The forward haircut is driven by de-peaking + execution + regime,
NOT by failing the deflation test (CPM passes DSR decisively, Addition 6).

Source: `research/cpm_deflated_sharpe_findings.md`,
`research/cpm_execution_cliff_findings.md`.

---

## ADDITION 6: DSR appendix inputs

Surfaces the inputs behind the memo's "DSR z ~3.9-5.4 / effective search 50-300"
claim. Source: `research/cpm_deflated_sharpe_findings.md` (Bailey & Lopez de
Prado 2014 deflated Sharpe ratio), built on the 80-cell grid SR distribution in
`research/cpm_grid_interaction_findings.json` and the production engine anchor
(reproduced clean Sharpe 1.1908, matches headline 1.1910).

### 6.1 Search-space accounting (number of variants / trials)

| Axis | Documented in grid? | Choices | DoF |
|---|---|---|---:|
| Top-K | yes | {3,4,5,6} | 4 |
| Momentum fn | yes | {faber_voladj, 13612U, 12m, 6m, 3m} | 5 |
| cov/vol lookback | yes | {252, 504} | 2 (degenerate under equal-wt) |
| Weighting | yes | {invvol, equal} | 2 |
| Canary combinator | no | OR vs AND | 2 |
| Canary asset pair | no | HYG/TIP vs LQD/IEF/... | ~3-6 |
| 13612U horizon set | no | tuned {r1,r3,r6,r12} form | ~3-5 |
| strict-K partial-safe threshold | no | 4-of-8 chosen from {1..8} | ~5-8 |
| 6-factor design lattice (C,U,R,S,W,P) | partly | 2^6=64 nominal; ~6-10 explored | ~6-10 |

- Visible grid = 4 x 5 x 2 x 2 = 80 cells (40 distinct; lookback unused under
  equal-weight).
- Nominal product across ALL axes ~1e3 to ~1e4 trials.

### 6.2 Effective independent trials and correlation assumption

The nominal product massively overstates independence: the cross-config SR
dispersion across the grid (std 0.073 ann) is far BELOW the standard error of a
single config's SR (0.24 ann, Lo/Mertens). Configs share most of the same return
stream -> highly correlated, not independent draws.

- Effective independent-ish trials N ~ 50-300, central ~150.
- DSR verdict is insensitive to N across (and beyond) this band (tested to
  N=2000).

### 6.3 DSR inputs (daily frame, consistent with the 1.1910 anchor)

| Input | Value |
|---|---:|
| Observed SR_hat (per-day) | 0.07502 (ann 1.1908) |
| n (daily obs) | 4524 |
| skew | -0.3740 |
| excess kurtosis | 4.0282 |
| V_trials (grid SR variance, per-day) | 2.094e-5 (std 0.073 ann) |

### 6.4 Resulting expected-max SR0 and deflated z, by N

| N | SR0 (ann) | DSR | z |
|---|---:|---:|---:|
| 40 | 0.159 | 1.0000 | 4.29 |
| 80 | 0.178 | 1.0000 | 4.22 |
| 200 | 0.201 | 1.0000 | 4.13 |
| 500 | 0.222 | 1.0000 | 4.03 |
| 1000 | 0.236 | 1.0000 | 3.97 |
| 2000 | 0.250 | 1.0000 | 3.91 |

Monthly frame (n=217, skew +0.15, excess-kurt -0.05) gives DSR ~1.0000 with
larger z (4.82-5.39). Hence the memo's "z ~3.9-5.4" band: 3.91 (daily, N=2000
worst case) to 5.39 (monthly). "Effective search 50-300" = the N band in 6.2.

Read:
- DSR ~1.0 (z > 3.9 everywhere): the 1.19 Sharpe is statistically distinguishable
  from the expected maximum of searching this correlated family -> selection-
  from-noise alone does NOT manufacture the result; real signal is present.
- DSR answers "is skill real", not "what is forward SR". The expected-max
  benchmark SR0 (0.16-0.25 ann) is the selection-inflation haircut feeding
  Addition 5 step 1.

### 6.5 What is known vs assumed (honesty)

- KNOWN / recoverable: SR_hat, n, skew, kurtosis, and V_trials are computed
  directly from the production return stream and the committed 80-cell grid
  (`cpm_grid_interaction_findings.json`). The DSR formula and z outputs are
  reproducible from these.
- ASSUMED / judgmental: the effective independent-trials N (50-300) is an
  inference from the dispersion-vs-SE argument, not an exact count; V_trials uses
  the 80-cell grid only, so the broader undocumented DoF (canary form, horizon
  set, strict-K threshold) are not in V_trials and instead widen N. The verdict
  is robust to this because DSR is N-insensitive across the whole band.
- Frame caveat: daily n=4524 overstates independence for a monthly strategy and
  daily kurtosis is heavy (4.03); the monthly frame (n=217) is more honest and
  gives a HIGHER z. Both frames -> DSR ~1.0.

---

## ADDITION 7: Proxy-construction audit

The review flags that the canary and safe proxies behind the extended window are
undisclosed. They ARE disclosed in code and in
`research/cpm_ext_extension_feasibility_findings.md`; this section consolidates
the ACTUAL pre-ETF treatment for every component the extended window depends on.

Pipeline (code refs): `cpm_live.load_panel` loads
`data/proxy_adjusted_close_daily.csv` first (all columns floored at 1995-01-04),
then overwrites specific columns with audited stitched CSVs in `data/` (each
stitched file replaces the same-named proxy column). All series are
adjusted-close (total-return: dividends/coupons reinvested) unless noted.

### 7.1 Per-component proxy table

| Asset | Grp | Live ETF inception | Pre-inception proxy source | Proxy type | Total return? | Panel start |
|---|---|---|---|---|---|---|
| QQQ | risky | 1999-03-10 | ^NDX Nasdaq-100 index (`data/qqq_stitched_daily.csv`) | index | price-index splice (QQQ tracks NDX closely) | 1985-10-01 |
| SPHQ | risky | 2005-12-06 | synthetic (proxy-file floor; no tradeable quality fund pre-2005) | synthetic | adjusted-close synthetic | 1995-01-04 |
| EFA | risky | 2001-08-14 | EAFE-type fund series (proxy file) | index/fund | adj-close | 1996-04-30 |
| EEM | risky | 2003-04-07 | EM fund series (proxy-file floor) | index/fund | adj-close | 1995-01-04 |
| VNQ | risky | 2004-09-23 | VGSIX (Vanguard REIT index fund) | mutual fund | yes (adj-close) | 1996-05-14 |
| GLD | risky | 2004-11-18 | World Bank gold spot, monthly, pre-2000-08 (`data/gld_stitched_extended_daily.csv`) | spot price | spot (no carry) | 1995-01-02 |
| TLT | risky | 2002-07-22 | VUSTX (Vanguard Long-Term Treasury) (`data/tlt_stitched_daily.csv`) | mutual fund | yes (adj-close) | 1986-05-19 |
| DBC | risky | 2006-02-03 | synthetic commodity (proxy-file floor) | synthetic | adj-close synthetic | 1995-01-04 |
| HYG | canary | 2007-04-11 | VWEHX (Vanguard High-Yield Corp) (`data/hyg_stitched_daily.csv`) | mutual fund | yes (adj-close) | 1980-01-02 |
| TIP | canary | 2003-12-05 | IEF+CPI synthetic pre-2000-06, then VIPSX (Vanguard TIPS) (`data/tip_stitched_daily.csv`) | synthetic + mutual fund | yes (IEF TR + realized CPI; VIPSX adj-close) | 2000-06-29 |
| SHV | safe | 2007-01-11 | VFISX (Vanguard Short-Term Treasury) (`data/shv_stitched_daily.csv`) | mutual fund | yes (adj-close) | 1991-10-28 |
| IEF | safe | 2002-07-22 | VFITX (Vanguard Intermediate Treasury) (`data/ief_stitched_daily.csv`) | mutual fund | yes (adj-close) | 1991-10-28 |

Fund-inception cross-checks (yfinance auto_adjust min date): VGSIX 1996-05-13,
VWEHX 1980-01-02, VUSTX 1986-05-19, VFITX/VFISX 1991-10-28, ^NDX 1985-10-01,
VIPSX 2000-06-29.

### 7.2 Canary + safe proxy disclosure (the review's specific gap)

- HYG canary: VWEHX (Vanguard High-Yield Corporate, real mutual fund, total
  return) from 1980, spliced to live HYG from 2007-04. Auditable, good fidelity.
- TIP canary: synthetic IEF+CPI (nominal intermediate-Treasury TR plus realized
  CPI inflation) before VIPSX exists, then VIPSX (real TIPS mutual fund TR) from
  2000-06, spliced to live TIP from 2003-12. The synthetic leg is WEAK pre-1997
  (no tradeable TIPS market existed). Mitigant: the canary is HYG-OR-TIP, and HYG
  has clean 1980+ history, so the weak TIP leg rarely binds. Sensitivity tested:
  swapping the TIP-proxy construction (IEF+CPI vs plain IEF) moves HAA-Simple
  Sharpe by only -0.05 (`research/cpm_tip_proxy_compare_findings.md`).
- SHV safe: VFISX (Vanguard Short-Term Treasury, real fund TR) from 1991-10.
  Good fidelity.
- IEF safe: VFITX (Vanguard Intermediate Treasury, real fund TR) from 1991-10.
  Good fidelity.

### 7.3 Fidelity caveats (for the extended window)

- Weakest proxies: SPHQ (synthetic quality, no tradeable fund pre-2005), DBC
  (synthetic broad commodity; nearest real index S&P GSCI is energy-heavy vs
  DBC's broad basket), TIP pre-1997 (synthetic).
- Good proxies: QQQ (NDX index), EFA (EAFE), VNQ (NAREIT/VGSIX), GLD (spot gold),
  TLT/IEF/SHV (Vanguard Treasury funds), HYG (VWEHX).
- Binding data floor: VNQ 1996-05-14 (next EFA 1996-04-30). The extended
  ext_start 1999-03-10 is a CONVENTION anchor (= QQQ live inception), not a hard
  data limit; ~11 months of slack (usable ~1998-04) is left on the table.
- Pre-ETF segments use close-to-close accounting (no real opens), so the mooex
  T+1 real-open execution model only fully applies in the live ETF era (2006+).
- Interpretation: the 1995/1999-2007 extended segment is a proxy-informed
  robustness lens, descriptive only. The clean window (2008-05-30, fully live
  ETFs) remains the decisive inferential lens.

Source: `research/cpm_ext_extension_feasibility_findings.md`,
`research/cpm_tip_proxy_compare_findings.md`, `cpm_live.py:138-161`.

---

## Caveats and confidence

- Anchor reproduced exactly (1.1910 / -12.67% / 1.0615), so additions 1-4 share
  the memo's harness, cost, window, and execution conventions.
- Additions 1-4 are computed and reproducible. Addition 1B and the extended rows
  carry proxy-tail uncertainty; the clean window is decisive.
- Additions 5-6: selection-deflation numbers are measured (DSR); execution and
  regime forward haircuts are judgmental (marked J). The forward Sharpe band
  0.62-0.85 is a reasoned synthesis, not a forward backtest.
- Addition 7 is documentation of the actual pipeline, cross-checked against fund
  inception dates; no new computation.
- All single-path statistics (MaxDD, Calmar, worst-interval, underwater) are
  high-variance on one 18-year sample and underpowered for formal significance,
  consistent with the memo's Section 5.5 difference-CI honesty.
- Confidence: high on additions 1-4 (reproducible, anchor-gated); medium-high on
  6 (two methods agree on real signal + selection haircut); medium on 5 step
  factors (regime factor is the softest); high on 7 (code + fund-date verified).

## Handoff

- fixer: fold the seven labeled additions into `cpm_memo.md` (suggested homes:
  Add 1 -> Section 5.5 extended table replacement/companion; Add 2 -> Section 9
  robustness; Add 3/4 -> new Section 5 subsections; Add 5 -> Section 8 forward
  haircut ladder; Add 6 -> new Section 8 DSR appendix; Add 7 -> Section 4 data /
  new appendix). ASCII-only as written.
