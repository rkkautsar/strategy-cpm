# CPM-BULL-NDX Blend: Validation Detail

**Companion to `README.md` and `bull_qqq_handout.md`.**
This handout holds the long-form validation tables, NDX survivor-bias Monte
Carlo, complexity ablation, hold-buffer sensitivity, and references that the
README defers. CPM and NDX sleeves are described inline below.

**Windows used here:**

- **CLEAN 18.1y**: 2008-04-30 → 2026-05-15 (all required ETFs live + 12mo warmup).
- **Extended 30y**: 1996-01-04 → 2026-05-15 (uses Vanguard mutual fund stitches
  pre-live; HYG-only canary pre-2001-06; NDX mirrors BULL pre-2006 PIT).
- **Alternative 19.3y window**: 2007-01-01 → 2026 (pre-PROD ablation runs;
  prefix tables labelled "alt weights" use 60/30/10, not current 60/20/20).

---

## 1. NDX sleeve: survivor-bias caveats

The NDX 20% sleeve has documented backtest biases. Standalone NDX numbers
(Sharpe 1.26 / CAGR 36% in CLEAN raw) appear inflated by survivor bias, though
the bias direction for large-cap NDX-100 is non-obvious (acquired-at-premium
dominates bankruptcies). Quantified via Monte Carlo: impact on the PROD blend
is small (~0.01 Sharpe, ~0.01pp CAGR). At 20% blend weight the bias impact is
structurally bounded.

### Bias sources

- **Yearly PIT membership**: `index_constitution` library snapshots NDX-100
  constituents at year boundaries, so mid-year additions (e.g. TSLA on
  2020-07-21) appear as members from Jan 1 of that year onward. Small
  look-ahead bias on additions.
- **Missing delisted-ticker data**: 24% of historical NDX-100 members have
  no usable price data in the panel (yfinance silently drops delisted
  acquired-out names like CELG, ATVI, BRCM, YHOO). Selection pool tilts toward
  survivors. Dominant remaining bias source.
- **NaN-in-holding handling**: when a held NDX ticker delists mid-period (NaN
  price on a market-open day), the backtest applies a -10% haircut to the
  position (conservative blended estimate of acquisition vs bankruptcy
  outcomes) and converts the position to SHV cash for the remainder of the
  holding period. Market-holiday detection prevents false triggers on days
  when all panel tickers are NaN.
- **Pre-2006 fallback**: PIT data starts 2006-01; the sleeve mirrors BULL-SPY
  weights before then, so 1996-2005 NDX is not a real selection.

### Survivor-bias Monte Carlo stress (CLEAN 18.1y, 1000 sims)

24% of unique selected tickers randomly delist with realistic event impacts.

| Event distribution | Mean event impact | PROD Sharpe | PROD CAGR | PROD MaxDD |
|---|---:|---:|---:|---:|
| Raw (no MC injection) | n/a | 1.579 | 19.33% | -12.93% |
| Realistic NDX-100 (70% acq-premium +20%, 15% merger, 10% weak -20%, 5% bankrupt -80%) | +8.0% | 1.599 | 19.62% | -12.92% |
| **Shumway-pessimistic (55% acq, 15% merger, 20% weak -30%, 10% bankrupt -55% per Shumway-Warther 1999)** | **-0.5%** | **1.574** | **19.31%** | **-12.99%** |
| Worst case (40% acq, 15% merger, 20% weak -30%, 25% bankrupt -80%) | -20.0% | 1.508 | 18.42% | -13.20% |

The Shumway-pessimistic distribution uses the academic-standard -55% imputation
for performance-related Nasdaq delistings (Shumway 1997, Shumway-Warther 1999),
which is the convention used in CRSP's preprocessed data. Under this
distribution, PROD CAGR shifts by -0.02pp from raw — effectively noise. Even
worst-case stress leaves PROD Sharpe 1.51 (vs CPM standalone 1.28) and CAGR
18.42%. The 20% NDX weight bounds bias impact to ~0.07 Sharpe / ~0.9pp CAGR
even in implausibly severe scenarios.

Reproducibility: MC analysis scripts at `/tmp/cpm_ndx_delisting_mc_v2.py` and
`/tmp/cpm_ndx_mc_pessimistic.py` (1000 iterations each, seed=42).

---

## 2. Block bootstrap CI

B = 2000, 21-day blocks, alternative 19.3y window.

| Strategy | Sharpe | Bootstrap mean | 95% CI | P(Sh > 1.0) |
|---|---:|---:|---:|---:|
| CPM standalone | 1.113 | 1.120 | [0.708, 1.528] | 73.2% |
| BULL standalone | 1.011 | 1.011 | [0.578, 1.444] | 52.6% |
| NDX standalone | 1.131 | 1.117 | [0.669, 1.564] | 69.1% |
| **60/30/10 CPM-BULL-NDX (alt weights)** | **1.364** | **1.362** | **[0.946, 1.796]** | **95.1%** |

The bootstrap Sharpe lower bound (0.946) is roughly at the forward-expectation
floor (0.95), so the strategy is supported by the tested data but not
comfortably above the floor.

---

## 3. Deflated Sharpe Ratio

Bailey & Lopez de Prado 2012. P[true Sh > 0] after N-trial haircut.

| Strategy | N=50 | N=100 | N=500 | N=1000 |
|---|---:|---:|---:|---:|
| CPM standalone | 99.6% | 99.1% | 96.8% | 95.1% |
| BULL standalone | 98.6% | 97.3% | 92.2% | 88.9% |
| NDX standalone | 99.7% | 99.4% | 97.5% | 96.1% |
| **60/30/10 CPM-BULL-NDX (alt weights)** | **99.99%** | **99.97%** | **99.84%** | **99.70%** |

DSR depends heavily on the assumed effective trial count. True hyperparameter
search space (9-asset universe, top-K=5, 504d EWMA cov, HOLD_BUFFER 2.0z, 15%
vol cap, 63d realized lookback, 12mo TR trend, 13612U canary, NDX K=4, 60/30/10
vs 60/20/20 blend, etc.) is plausibly larger than N=1000 even at conservative
count. These results reduce the probability that the historical result is pure
noise; they do not eliminate model-selection bias, regime risk, data-quality
risk, or implementation drift.

---

## 4. Complexity-layer ablation

Alternative 19.3y window. Each added complexity layer should justify itself
versus simpler adjacent strategies after cost.

| Strategy | Sharpe | CAGR | Vol | MaxDD | Δ Sharpe vs prior |
|---|---:|---:|---:|---:|---:|
| SPY buy-hold | 0.62 | 10.89% | 19.69% | -55.19% | (baseline) |
| QQQ buy-hold | 0.80 | 16.47% | 22.22% | -53.40% | +0.18 (beta switch) |
| QQQ 12mo TR timing only | 0.87 | 15.76% | 18.83% | -28.72% | +0.07 (trend filter) |
| 60% CPM + 40% SHV (defensive) | 1.27 | 9.17% | 7.09% | -8.53% | +0.41 (CPM engine) |
| 100% CPM standalone | 1.19 | 14.21% | 11.80% | -14.74% | (alt: CPM full size) |
| **70/30 CPM-BULL (no NDX)** | **1.34** | **15.66%** | **11.36%** | **-12.59%** | +0.15 (BULL adds) |
| **60/30/10 CPM-BULL-NDX (alt weights)** | **1.41** | **18.35%** | **12.51%** | **-15.43%** | +0.07 (NDX adds, at +3pp DD cost) |

Each layer adds Sharpe. NDX is the smallest marginal gain (+0.07 Sh) at the
steepest DD cost (+3pp); justified by the +2.7pp CAGR contribution.

---

## 5. Hold-buffer sensitivity

CPM uses a 2.0z cross-sectional hold buffer to reduce pair-rotation churn
(keep prior pair member if its z-score is within 2.0z of the worst new pick).

| Variant | CPM Sh | CPM CAGR | CPM Vol | CPM MaxDD | Blend Sh | Blend MaxDD |
|---|---:|---:|---:|---:|---:|---:|
| **HB=2.0z (PROD)** | **1.19** | **14.21%** | 11.80% | **-14.74%** | **1.41** | **-15.43%** |
| HB=0 (no buffer) | 1.16 | 13.18% | 11.24% | -18.42% | 1.35 | -20.01% |

Removing the buffer deepens MaxDD by 3.7pp (CPM) and 4.6pp (blend) for a
marginal Sharpe loss. Buffer fires retain in ~38% of pair-selection months;
it is actively reducing churn into worse-DD positions, not dead code. Within
the validated 2-5z plateau, exact value is not sensitive.

---

## 6. 30y extended window notes

1996-01-04 → 2026-05-15. Includes dot-com bust (2000-02), GFC (2008), COVID
(2020), 2022 inflation spike.

- Pre-2006 the NDX sleeve mirrors BULL-SPY (PIT constituent data unavailable).
- Pre-2001-06 the BULL canary reduces to HYG-only (VIPSX/TIP 12-month warm-up
  not complete).
- SHV/IEF/TLT pre-live use VFISX/VFITX/VUSTX Vanguard mutual fund stitches.
- GLD pre-2004-11 uses World Bank monthly gold forward-filled to daily.
- Asset momentum circuit breaker (Antonacci 12mo TR) is the primary defense in
  macro-confusion regimes like dotcom.

Pre-2007 is least reliable in exactly the periods that matter most (dotcom,
GFC) because they use proxy-stitched data. Treat pre-2007 as directional only,
not as confirmation.

---

## 7. References

- Shumway, T. (1997). The Delisting Bias in CRSP Data. *Journal of Finance*
  52(1), 327-340.
- Shumway, T. & Warther, V. (1999). The Delisting Bias in CRSP's Nasdaq Data
  and Its Implications for the Size Effect. *Journal of Finance* 54(6),
  2361-2379.
- Bailey, D. & Lopez de Prado, M. (2012). The Deflated Sharpe Ratio.
- Antonacci, G. (2014). *Dual Momentum Investing.*
- Moskowitz, T., Ooi, Y., & Pedersen, L. (2012). Time series momentum.
  *Journal of Financial Economics* 104, 228-250.
- Keller, W. & Keuning, J.W. (2022). Hybrid Asset Allocation (HAA).
- Faber, M. (2007). A Quantitative Approach to Tactical Asset Allocation. SSRN.
- Jegadeesh, N. & Titman, S. (1993). Returns to Buying Winners and Selling
  Losers. *Journal of Finance* 48(1), 65-91.
- Markowitz, H. (1952). Portfolio Selection. *Journal of Finance* 7(1), 77-91.
- JPMorgan (1996). *RiskMetrics — Technical Document*, 4th ed.

---

## 8. Current 60/20/20 validation archive

This section preserves validation detail removed from the README cleanup so the
README can stay spec-only.

### Live-window headline and bias checks

Clean live-ETF window: 2008-04-30 -> 2026-05-22, 18.1y, post-cost.

| Metric | Value |
|---|---:|
| PROD Sharpe | 1.700 |
| PROD CAGR | 17.24% |
| PROD Vol | 9.84% |
| PROD MaxDD | -8.25% |
| PROD Ulcer | 2.40% |

NDX standalone: Sharpe 1.24, CAGR 29.25%, Vol 23.66%, MaxDD -31.52%.

### PROD 60/20/20 K=8 block bootstrap

B=5000, paired 21-trading-day blocks, 2008-04-30 -> 2026-05-22.

| Metric | Value |
|---|---:|
| PROD point Sharpe | 1.700 |
| PROD bootstrap mean | 1.696 |
| PROD Sharpe 95% CI | [1.292, 2.120] |
| Naive 60/40 PP/SPY-trend point Sharpe | 0.993 |
| Benchmark bootstrap mean | 0.991 |
| Benchmark Sharpe 95% CI | [0.552, 1.434] |
| Sharpe difference mean | +0.706 |
| Sharpe difference 95% CI | [+0.336, +1.075] |
| P(PROD Sharpe > benchmark Sharpe) | 100.0% |
| P(PROD Sharpe > 1.0) | 100.0% |
| P(PROD Sharpe > 1.05) | 99.98% |

### Excess Sharpe over SHV

| Strategy | CLEAN raw Sh | CLEAN excess Sh | 30y raw Sh | 30y excess Sh |
|---|---:|---:|---:|---:|
| PROD | 1.700 | 1.563 (-0.14) | 1.538 | 1.304 (-0.23) |
| CPM solo | 1.324 | 1.200 | 1.254 | 1.039 |
| BULL solo | 1.197 | 1.075 | 1.040 | 0.833 |
| NDX solo | 1.289 | 1.233 | 1.167 | 1.056 |
| SPY buy-hold | 0.660 | 0.591 | 0.532 | 0.406 |
| QQQ buy-hold | 0.824 | 0.763 | 0.528 | 0.437 |

T-bill CAGR: 1.34% on CLEAN window, about 2.7% on 30y.

### Bootstrap robustness across block lengths

| Window | Block | Mean Sh | 95% CI |
|---|---:|---:|---:|
| CLEAN 18.1y | 21d | 1.697 | [1.292, 2.136] |
| CLEAN 18.1y | 63d | 1.676 | [1.320, 2.034] |
| CLEAN 18.1y | 126d | 1.691 | [1.371, 1.990] |
| Extended 30y | 21d | 1.543 | [1.198, 1.894] |
| Extended 30y | 63d | 1.525 | [1.243, 1.801] |
| Extended 30y | 126d | 1.521 | [1.248, 1.782] |

### Regime-block bootstrap

| Window | Regime split | Mean Sh | 95% CI |
|---|---|---:|---:|
| CLEAN 18.1y | 79% bull / 21% bear | 1.704 | [1.218, 2.186] |
| Extended 30y | 72% bull / 28% bear | 1.539 | [1.157, 1.917] |

### BULL composite gate DSR

BULL standalone Sharpe 1.182, daily skew -0.374, kurt 3.74.

| Effective trial count N | PSR (P[true Sh > 0]) |
|---:|---:|
| 20 | 99.88% |
| 50 | 99.61% |
| 100 | 99.20% |

### Full research-path DSR

| N trials | CLEAN PSR | 30y PSR |
|---:|---:|---:|
| 20 | 100.00% | 100.00% |
| 100 | 99.98% | 99.97% |
| 200 | 99.95% | 99.93% |
| 500 | 99.87% | 99.81% |
| 1000 | 99.75% | 99.65% |
| 2000 | 99.56% | 99.39% |

### Blend-weight sensitivity

| Weights | Sharpe | CAGR | MaxDD | Max-rv 63d | Ulcer |
|---|---:|---:|---:|---:|---:|
| 60/40/0 | 1.487 | 14.06% | -8.74% | 15.72% | 2.62% |
| 60/30/10 | 1.618 | 15.66% | -8.27% | 15.76% | 2.52% |
| 60/25/15 | 1.665 | 16.45% | -8.07% | 16.57% | 2.50% |
| 60/20/20 PROD | 1.700 | 17.24% | -8.25% | 17.48% | 2.50% |
| 60/15/25 | 1.723 | 18.04% | -8.43% | 18.54% | 2.52% |
| 60/10/30 | 1.736 | 18.82% | -8.62% | 19.66% | 2.56% |
| 60/0/40 | 1.738 | 20.40% | -9.01% | 22.08% | 2.70% |

### NDX DD circuit sensitivity

| Threshold | Sharpe | CAGR | MaxDD | NDX DD-days |
|---:|---:|---:|---:|---:|
| -7.5% | 1.756 | 17.17% | -7.85% | 1115 |
| -10.0% PROD | 1.700 | 17.24% | -8.25% | 701 |
| -12.5% | 1.724 | 18.10% | -8.82% | 461 |
| -15.0% | 1.685 | 18.04% | -8.71% | 304 |
| -20.0% | 1.634 | 17.71% | -10.44% | 166 |

### Cost sensitivity

| Cost/side | Blend Sh | CAGR | MaxDD |
|---:|---:|---:|---:|
| 0 bps | 1.740 | 17.68% | -8.20% |
| 5 bps | 1.720 | 17.46% | -8.23% |
| 10 bps PROD | 1.700 | 17.24% | -8.25% |
| 15 bps | 1.681 | 17.02% | -8.27% |
| 20 bps | 1.661 | 16.80% | -8.29% |
| 25 bps | 1.474 | 15.93% | -11.67% |
| 50 bps | 1.382 | 14.86% | -12.02% |
| 75 bps | 1.289 | 13.80% | -12.81% |
| 100 bps | 1.195 | 12.75% | -15.52% |
