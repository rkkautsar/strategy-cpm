# CPM-BULL-NDX Robustness Ledger

**Companion to `README.md` and `bull_qqq_handout.md`.**

This document is the current validation ledger for the 60/20/20 CPM-BULL-NDX strategy. The README stays spec-only; this file records why each non-trivial rule is allowed to remain in the candidate strategy.

**Current production candidate**

- **60% CPM**: 9-asset ETF momentum/min-variance sleeve with HYG/TIP/GLD canary, best-of-safe SHV/IEF, hold buffer, and de-risk-only vol cap.
- **20% BULL-SPY**: SPY risk-on sleeve gated by HYG OR TIP canary and SPY 12-month momentum.
- **20% NDX**: PIT Nasdaq-100 top-5 GPM score (13612U momentum penalized by 260d correlation) stocks, 20% each, partial-fill to best safe, with NDX-only drawdown circuit.

**Primary windows**

- **Clean live-ETF window**: 2008-04-30 to 2026-05-22, post-cost.
- **Extended 30y window**: 1996 to 2026, using documented proxy/stitch data. Treat as directional, not confirmation.

---

## 1. Headline validation

Clean live-ETF window, 10 bps/side, no leverage.

| Strategy | Sharpe | CAGR | Vol | MaxDD | Ulcer |
|---|---:|---:|---:|---:|---:|
| **PROD 60/20/20** | **1.710** | **17.95%** | **9.99%** | **-9.35%** | **2.65%** |
| Naive 60/40 PP/SPY-trend | 0.993 | 7.70% | 7.79% | -14.41% | 4.08% |
| SPY buy-hold | 0.660 | 11.76% | 19.79% | -51.48% | -- |
| QQQ buy-hold | 0.824 | 17.23% | 22.29% | -49.37% | -- |

Sleeve standalone, same clean window:

| Sleeve | Sharpe | CAGR | Vol | MaxDD |
|---|---:|---:|---:|---:|
| CPM | 1.330 | 14.38% | 10.54% | -10.59% |
| BULL-SPY | 0.890 | 12.64% | 14.55% | -33.72% |
| NDX top-K | 1.440 | 32.23% | 20.93% | -14.40% |

---

## 2. Robustness ledger

| Rule / parameter | Rationale | Evidence artifact | Result | Verdict |
|---|---|---|---|---|
| 60/20/20 sleeve weights | Conservative middle between BULL and NDX concentration; not max-Sharpe allocation. | Section 3, blend-weight sensitivity | 60/20/20 is below peak Sharpe but keeps MaxDD/Ulcer close to best risk region. | Keep as risk-budget choice, not optimized peak. |
| CPM HYG/TIP/GLD canary | Credit, real-rate/inflation, and gold stress breadth for defensive ETF sleeve. | `research/archive/canary_audit_and_breadth_tiering.log`, `research/archive/canary_haa_simple_variants.log` | Canary variants tested; current family has better risk control than no-canary/simple trend in FCP/CPM research. | Keep, but classify as custom HAA-family extension. |
| BULL HYG OR TIP canary | HAA-simple TIP canary extended with credit breadth via HYG. | `bull_qqq_handout.md`, `research/archive/canary_haa_simple_variants.log` | Current live BULL rule uses HYG OR TIP canary; curve/vol composite remains removed. | Keep as active canary rule. |
| BULL canary + SPY 12m absolute momentum | Keep BULL gate simple and interpretable with canary breadth plus asset trend confirmation. | `bull_qqq_handout.md` | Current live BULL rule is (HYG OR TIP) canary AND SPY 12m momentum; TIP-only retained as parsimony sensitivity alternative. | Keep as active BULL gate. |
| SPY 12-month momentum in BULL | Natural absolute-momentum defense; standard GEM/TSMOM rule. | `README.md`, `bull_qqq_handout.md` | Canonical trend filter with external precedent. | Keep. |
| CPM hold buffer 2.0z | Reduces churn and avoids replacing nearly equivalent pair members. | Section 3; `research/hold_buffer_threshold_diagnosis.log`; `research/archive/fcp_sensitivity.log` | HB=0 deepens blend MaxDD materially; broad 2-5z region historically similar. | Keep, but prefer plateau framing over exact optimum. |
| CPM min-variance pair | Diversifies within top momentum candidates without forecasting returns. | `README.md`; sensitivity artifacts in `research/archive/fcp_sensitivity.log` | Corr lookbacks 126-756d remain usable; 378/504d region not isolated magic. | Keep. |
| CPM vol cap | De-risk only; no leverage. Controls realized sleeve risk. | `research/archive/fcp_sensitivity.log` | Target-vol and lookback sweeps show smooth risk/return tradeoff. | Keep as risk cap, not alpha rule. |
| NDX top-5 GPM score | Concentrated high-conviction GPM momentum sleeve, but partial-fill to safe when fewer positive names. | `research/ndx_sleeve/alternatives.py`; `research/cpm_bull_ndx_canonical_numbers.log`; Section 4 | NDX sleeve adds return but has high standalone drawdown and survivorship/data risk. | Keep only at 20% sleeve size. |
| NDX drawdown circuit | NDX-only risk throttle for concentrated stock sleeve. | Section 3 | Threshold sweep -7.5% to -20% remains strong; -10% is not the peak. | Keep as risk-control standard, not optimized peak. |
| Delisted/NaN holding handling | Avoids silently dropping failed or acquired holdings from NDX backtest. | Section 4 | Shumway-pessimistic MC has small blend impact; worst-case still leaves strategy above CPM-only reference. | Keep with caveat: research-grade data only. |
| 10 bps/side cost | Baseline implementation friction. | Section 3 | Robust through 20 bps; degrades materially beyond that. | Keep; require low-cost execution. |

---

## 3. Sensitivity and stress tables

Most tables in this section were produced under prior BULL variants and are not guaranteed current for the active HYG OR TIP plus SPY 12m rule.

| Artifact group | Status after BULL rule simplification |
|---|---|
| Block bootstrap / regime bootstrap / DSR values | Prior full-gate sensitivity evidence only. Do not treat as current active-rule validation. |
| Blend-weight, NDX DD threshold, and cost sweeps | Prior full-gate sensitivity evidence only. Re-run required before reusing headline numbers. |
| CPM hold-buffer sweeps | Directional CPM evidence still useful, but blend-level values are stale for active BULL rule. |

Current active-rule headline metrics are in Section 1. Re-run Section 3 sensitivity artifacts before using any confidence intervals or sweep tables as current evidence.

---

## 4. NDX data-bias ledger

The NDX sleeve is the least robust part of the strategy because it uses individual stocks and PIT Nasdaq-100 membership.

| Bias source | Mitigation | Remaining risk |
|---|---|---|
| Yearly PIT membership snapshots | Use `index_constitution` snapshots instead of current membership. | Mid-year changes can be pulled forward within the calendar year. |
| Missing delisted ticker prices | NaN-in-holding handler applies terminal haircut and moves to safe. | Missing tickers can still bias selection pool toward survivors. |
| Acquired-at-premium vs bankruptcy outcomes | Monte Carlo injects realistic and pessimistic delisting events. | Event model is not real CRSP event data. |
| Pre-2006 PIT unavailable | NDX sleeve mirrors BULL-SPY before PIT data exists. | Extended window is not real NDX stock selection before 2006. |

### Delisting Monte Carlo stress

Clean live-ETF window, 1000 simulations.

| Event distribution | Mean event impact | PROD Sharpe | PROD CAGR | PROD MaxDD |
|---|---:|---:|---:|---:|
| Raw | n/a | 1.579 | 19.33% | -12.93% |
| Realistic NDX-100 | +8.0% | 1.599 | 19.62% | -12.92% |
| **Shumway-pessimistic** | **-0.5%** | **1.574** | **19.31%** | **-12.99%** |
| Worst case | -20.0% | 1.508 | 18.42% | -13.20% |

The stress result supports the 20% sleeve size but does not prove live NDX stock selection will repeat the backtest edge.

---

## 5. Evidence map and open gaps

| Topic | Evidence already exists | Current enough? | Gap |
|---|---|---|---|
| CPM parameter sensitivity | `research/archive/fcp_sensitivity.log`, `research/hold_buffer_threshold_diagnosis.log` | Mostly | Some artifacts are older FCP-era and should be regenerated only if CPM rules change. |
| Walk-forward/OOS | `research/walk_forward_rule_freeze.log` | Yes for CPM-style engine | Not a full latest 60/20/20 end-to-end walk-forward. |
| Year/crisis leave-one-out | `research/archive/all_live_era_and_loo_crisis.log` | Yes for prior CPM/FCP engine | Not latest full blend. |
| Canary variants | `research/archive/canary_haa_simple_variants.log`, `research/archive/canary_audit_and_breadth_tiering.log` | Partial | Current BULL thesis is HYG OR TIP breadth plus SPY 12m momentum; TIP-only is sensitivity/parsimony fallback. |
| Blend weights | Section 3 | Yes | Need re-run only after changing sleeve definitions. |
| NDX DD threshold | Section 3 | Yes | Add newer ETF-sleeve alternatives only if NDX replacement becomes active candidate. |
| NDX survivorship/delisting | Section 4 | Research-grade | True CRSP/Polygon/Tiingo delisting data would be stronger. |
| Direct yield-curve proxy | Not in current ledger | No | Optional future replacement for IEF-vs-TLT return proxy. |
| Live-trading record | None | No | Strategy is not live-traded. |

---

## 6. References

- Antonacci, G. (2014). *Dual Momentum Investing.*
- Bailey, D. & Lopez de Prado, M. (2012). The Deflated Sharpe Ratio.
- Faber, M. (2007). A Quantitative Approach to Tactical Asset Allocation. SSRN.
- Jegadeesh, N. & Titman, S. (1993). Returns to Buying Winners and Selling Losers. *Journal of Finance* 48(1), 65-91.
- Keller, W. & Keuning, J.W. (2022). Hybrid Asset Allocation (HAA).
- Markowitz, H. (1952). Portfolio Selection. *Journal of Finance* 7(1), 77-91.
- Moskowitz, T., Ooi, Y., & Pedersen, L. (2012). Time series momentum. *Journal of Financial Economics* 104, 228-250.
- Nystrup, P. & Boyd, S. (2019). A downside risk constraint for tactical asset allocation.
- Shumway, T. (1997). The Delisting Bias in CRSP Data. *Journal of Finance* 52(1), 327-340.
- Shumway, T. & Warther, V. (1999). The Delisting Bias in CRSP's Nasdaq Data and Its Implications for the Size Effect. *Journal of Finance* 54(6), 2361-2379.
