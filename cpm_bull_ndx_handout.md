# CPM-BULL-NDX Blend: Validation Detail

**Companion to `README.md` and `bull_qqq_handout.md`.**
This handout holds the long-form validation tables, NDX survivor-bias Monte
Carlo, complexity ablation, hold-buffer sensitivity, and references that the
README defers. BULL-QQQ academic memo is `bull_qqq_handout.md` (untouched);
CPM and NDX sleeves are described inline below.

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
- **Pre-2006 fallback**: PIT data starts 2006-01; the sleeve mirrors BULL-QQQ
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
vol cap, 63d realized lookback, 12-1 trend, 13612U canary, NDX K=4, 60/30/10
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
| QQQ 12-1 timing only | 0.87 | 15.76% | 18.83% | -28.72% | +0.07 (trend filter) |
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

- Pre-2006 the NDX sleeve mirrors BULL-QQQ (PIT constituent data unavailable).
- Pre-2001-06 the BULL canary reduces to HYG-only (VIPSX/TIP 12-month warm-up
  not complete).
- SHV/IEF/TLT pre-live use VFISX/VFITX/VUSTX Vanguard mutual fund stitches.
- GLD pre-2004-11 uses World Bank monthly gold forward-filled to daily.
- Asset momentum circuit breaker (Antonacci 12-1) is the primary defense in
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
- BULL-QQQ-specific design and Jobson-Korkie/Memmel Sharpe-difference test:
  see `bull_qqq_handout.md` §3-4.
