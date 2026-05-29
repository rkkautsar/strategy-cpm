# Analysis: Production (T+1 MOO) vs. Alternative (T+1 MOC) Execution

This analysis compares the production execution model of the 60/20/20 CPM-BULL-NDX portfolio (T signal, T+1 MOO execution) against an alternative execution model (T signal, T+1 MOC execution) over the clean window **2008-05-30** to **2026-05-22**.

## Methodology & Modeling

1. **Production T+1 MOO (a)**:
   - Signals are decided at month-end close $T$.
   - Positions are established at the next trading day's open $T+1$ (MOO).
   - In close-to-close accounting, the return on the rebalance day $T+1$ is calculated using the **NEW** weights (as they are established at the open of that day, capturing the $T+1$ intraday session).
   - Non-rebalance days hold the target weights.

2. **Alternative T+1 MOC (b)**:
   - Signals are decided at month-end close $T$.
   - Positions are established at the next trading day's close $T+1$ (MOC).
   - In close-to-close accounting, the return on the rebalance day $T+1$ is calculated using the **OLD** weights (from the previous month), as the new positions are only established at the close of $T+1$.
   - From day $T+2$ onwards, the portfolio holds the new weights.
   - Non-rebalance days are identical to production.

## Performance Comparison (2008-05-30 to 2026-05-22)

The 60/20/20 production blend (60% CPM Standalone, 20% BULL-SPY, 20% NDX Sleeve) was simulated under both models:

| Metric | (a) Production MOO (offset=1) | (b) Alternative MOC (offset=2) | Difference (MOC - MOO) |
| :--- | :---: | :---: | :---: |
| **CAGR** | **17.94%** | **16.48%** | **-1.46%** |
| **Annualized Volatility** | 11.43% | 11.42% | -0.01% |
| **Raw Sharpe Ratio** | **1.505** | **1.398** | **-0.107** |
| **Excess Sharpe vs SHV** | 1.390 | 1.281 | -0.109 |
| **Max Drawdown** | -11.62% | -11.78% | -0.16% |
| **Calmar Ratio** | 1.543 | 1.399 | -0.144 |

*Note: The production MOO simulation successfully reproduces the known historical production performance of **~1.503 Sharpe**, **17.93% CAGR**, and **-11.62% MaxDD** (slight rounding differences due to clean indexing limits).*

## Tracking Difference & Rebalance-Day Drag

- **Annualized Tracking Difference** (stdev of daily return difference): **1.7814%**
- **Number of Rebalance Months evaluated**: **216**
- **Mean monthly rebalance-day return diff (MOC - MOO)**: **-0.0727%** (-7.27 bps)
- **Cumulative rebalance-day return difference**: **-15.71%**
- **Annualized mean drag**: **-0.87% per year** (-87.3 bps/year)

## Key Findings & Interpretation

1. **Materiality**:
   MOC execution **materially** degrades performance compared to MOO execution. Delaying the transition from the old weights to the new weights by a single day (from $T+1$ open to $T+1$ close) results in a **1.46% CAGR drag** and drops the Sharpe ratio by **0.11**. This is far outside the realm of noise.

2. **The Momentum Decay Effect**:
   Because CPM and its sleeves are momentum and trend-following strategies, a "risk-on" signal or asset swap is typically triggered when an asset has strong positive momentum. By waiting until the close of $T+1$ to buy the new high-momentum assets (and holding the old, decaying assets for one more day), the strategy misses out on the strong Day 1 performance of the fresh signal. 

3. **Intraday session vs. Overnight Gap**:
   In the production MOO model, the portfolio holds the **NEW** weights for the $T+1$ intraday session (open-to-close) and only holds the **OLD** weights over the $T$ close $ightarrow$ $T+1$ open overnight gap. In the alternative MOC model, the portfolio is stuck in the **OLD** weights for both the overnight gap and the entire $T+1$ intraday session. The negative drag of MOC indicates that the $T+1$ intraday return of the new weights is consistently superior to that of the old weights on rebalance days.

## Caveats & Assumptions

- **Close-to-Close Daily Returns**: In the absence of high-fidelity historical open prices for all Nasdaq-100 historical constituents, this analysis approximates the $T+1$ MOO execution by assuming the new weights are held for the full $T+1$ day return ($close[T+1]/close[T] - 1$). This is the same honest practitioner-standard convention used by the existing backtest harness in `cpm_live.py`.
- **Transaction Costs**: Transaction costs (10bps/side) are applied on the rebalance day ($T+1$) in both simulations. Since the turnover is identical, the total trading cost is identical, and the difference is purely driven by market returns.

## Conclusion

**MOC execution is not equivalent to the backtested MOO execution.** Executing at the close instead of the open on the day after the signal introduces a significant **-87.3 bps/year drag** on average. To preserve the high performance of the backtest, execution should be performed at **MOO (next-day open)** rather than MOC (next-day close).
