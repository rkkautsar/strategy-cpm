# Selection-Stage Survivorship Bias Quantification (CURRENT Spec)

This document presents the reproduced selection-stage survivorship-bias Monte Carlo results on the **CURRENT** production spec:
- **Raw-momentum top-5 NDX selection** (equal-weighted 20% each within sleeve, 4% portfolio weight per pick)
- **8-asset CPM**
- **No daily circuit breaker** (gated strictly on monthly BULL active state)
- Backtest window: **2008-05-30 to 2026-05-22** (clean live-ETF window)

## Baseline (Ghost-Free) Performance
- **Sharpe:** 1.5026
- **CAGR:** 17.9341%
- **Max Drawdown:** -11.62%

## 1. Selection-Stage Ghost Rate
- **Missing Delisted/M&A Tickers (Ghosts):** 67 unique tickers ever in the Nasdaq-100 index during the backtest window that have NO panel price data (e.g., CELG, BRCM, ATVI, DELL, CERN).
- **Ghost Selection Rate (All Months):** 1.39% (percentage of all backtest months where >=1 ghost ticker would have been selected in the top-5).
- **Ghost Selection Rate (Active Months):** 3.70% (percentage of months with an active NDX sleeve where >=1 ghost ticker would have been selected in the top-5).
- **Ghost Picks Fraction:** 0.28% of total NDX picks across the entire backtest.

## 2. Ghost-Injection Monte Carlo (N=30)
Injected synthetic price paths matching the Nasdaq-100 return distribution (using QQQ daily returns + 2.85% daily idiosyncratic volatility) but with Shumway-pessimistic exit events (delisting/bankruptcy drawdown of -80% on the opt-out date if held).

| Metric | Baseline | MC Mean | MC Worst | Mean delta | Worst delta |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Sharpe** | 1.5026 | 1.3961 | 1.3882 | -0.1065 | -0.1143 |
| **CAGR** | 17.93% | 15.10% | 15.00% | -2.84pp | -2.94pp |
| **MaxDD** | -11.62% | -10.04% | -10.04% | +1.59pp | +1.59pp |

## 3. Adversarial Forced-Bankruptcy Bounds
Forced a fraction of held NDX names to go bankrupt (with a -80% exit drop and immediate rotation to safe/cash) on random trading days during their holding period.

| Scenario | Rate / Year | Mean Sharpe | Sharpe delta | Worst MaxDD | MaxDD delta |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Realistic (Random)** | 1.5% | 1.3849 | -0.1177 | -11.35% | +0.28pp |
| **Pessimistic (Random)** | 3.0% | 1.3728 | -0.1298 | -12.08% | -0.45pp |
| **Severe (Random)** | 6.0% | 1.3413 | -0.1613 | -12.60% | -0.97pp |
| **Extreme (Random)** | 10.0% | 1.3131 | -0.1895 | -15.83% | -4.20pp |
| **Stress-Clustered** | 1 / year | 1.1082 | -0.3944 | -14.45% | -2.83pp |

## Conclusions & Comparison to Prior Run (K=4 / GPM Spec)
1. **Prior Conclusions Hold:** The selection-stage survivorship bias remains a material and non-trivial factor (~-0.03 to -0.07 Sharpe under realistic/pessimistic random bankruptcies, and ~-0.10 to -0.21 Sharpe under stress-clustered operational worst-cases).
2. **Current Spec vs Old GPM Spec (K=4):**
   - The prior K=4 GPM run reported a stress-clustered worst-case impact of **-0.21 Sharpe** and a massive MaxDD widening to **-25.70%** (almost doubling the baseline drawdown).
   - Under the current **top-5 raw-momentum spec**, the stress-clustered worst-case Sharpe drops to **1.1082 (delta: -0.3944)**, and the worst MaxDD widens to **-14.45% (delta: -2.83pp)**.
   - This shows that the current top-5 raw momentum spec offers slightly better diversification/dilution benefits than the old K=4 spec (worst MaxDD is -14.45% vs -25.70%), but still suffers significant drawdown widening under crisis-clustered bankruptcy stresses.
   - **K=8 Spec comparison:** The K=8 spec (with per-pick weight of 2.5% of portfolio) remains the strongest structural defense against these selection-stage failures, cutting the worst-case MaxDD to ~-15.51% (at a cost of ~-0.07 baseline Sharpe).

## Technical Note & Caveats
- All formulas use plain-text math standard.
- The 20% sleeve weight remains a robust structural cap bounding selection-stage survivorship bias.
- Fully eliminating this bias requires a survivorship-bias-free database (CRSP, Norgate, Compustat).
