# iMarketSignals IM-Best Market Timing System Investigation

This report reviews the "iM-Best(SPY-SH)" and "iM-Best(SPY-Cash)" market-timing systems published by Georg Vrba (iMarketSignals) in August 2013. The systems claimed to switch between SPY (risk-on) and SH (short S&P 500) or cash (risk-off) to generate annual returns of ~27-29% with minimal drawdowns. 

---

## 1. Exact Rules and Parameter Set

The system operates on a weekly rebalancing schedule (Friday's close for Monday execution). While marketed as having "no buy rules" because it always switches to the higher-ranked ETF on weekends, it relies on a specific multi-factor ranking system and defensive overlays.

### Inputs / Indicators
1. **CBOE Volatility Index (VIX)**: Used to gauge short-term market panic.
2. **S&P 500 Risk Premium (RP)**: Calculated as:
   `RP = Current Estimated Earnings Yield of S&P 500 - US Treasury 10-Yr Note Yield`
   * Overvalued: `RP < 1%`
   * Fairly/Undervalued: `RP > 3%`
3. **S&P 500 Current Year Consensus EPS Estimate**: Represented by the Portfolio123 proprietary data series `#SPEPSCY`.
4. **SPY Price**: Adjusted for dividends.

### Strategy Rules
* **Rebalance Frequency**: Weekly (Saturday calculation, Monday market-on-close execution using `(Hi + Lo + 2 * Close) / 4` or closing price).
* **Ranking / Buy Logic**: If the system is in Cash/SH, a buy/re-entry is only permitted at least 1 week after a sell signal occurred. It selects between SPY and SH based on the ranking of their multi-factor parameters.
* **Sell / Risk-Off Logic**: 
  * Based on moving average crossovers of SPY (e.g., short-term MA crossing below long-term MA).
  * Minimum holding period of 7 weeks (or 6 weeks in some versions) specified after a SPY position is opened to avoid over-trading.
* **Stop-Loss Overlay**:
  * **Original (2013)**: Stop-loss at -12% for SPY and -16% for SH from the highest close since the position started.
  * **Revised (Late 2013/2014)**: Tightened to a strict **-8%** (or -10% for SH in some variants) from the highest close since the position started. If triggered on a weekday, the exit is executed on the following Monday.

### Claimed Backtest Statistics (Jan 3, 2000 to Aug 31, 2013)
* **iM-Best(SPY-SH)**: Claimed CAGR of **27.6% - 29.3%**, Max Drawdown (MaxDD) of **-22.75%**, vs. S&P 500 Buy-and-Hold CAGR of **2.6%**.
* **iM-Best(SPY-Cash)**: Claimed CAGR of **16.3% - 17.0%**, Max Drawdown of **-15.0%**, vs. S&P 500 Buy-and-Hold CAGR of **2.6%**. (Spent ~64% of the time in SPY).

---

## 2. Data-Mining Red Flags and Structural Vulnerabilities

The strategy suffers from multiple classical quant backtesting traps:

1. **Parameter Over-Optimization (Curve-Fitting)**: The strategy uses at least 5 highly specific thresholds (VIX level, risk premium thresholds, moving average lookbacks, minimum holding periods, and stop-loss trailing parameters). The author explicitly admitted: *"We vary the parameters' derivatives to see whether the model is robust. Obviously in the end we want to show the best return."* This is the definition of data-mining.
2. **Data Revisions / Look-Ahead Bias**: S&P 500 consensus EPS estimates (`#SPEPSCY`) are published by third parties (like Thomson Reuters/I/B/E/S) and are heavily revised retrospectively. Backtesting using refreshed data series that have been cleaned up and corrected introduces significant look-ahead bias if the original, unrevised point-in-time series is not used.
3. **Data Dependency and Model Fragility**: The strategy's performance was completely dependent on the exact formatting and definition of Portfolio123's proprietary data series. When Portfolio123 rebuilt the "Fed Model" series in late 2014 and revised `#SPEPSCY` again in late 2016, the strategy's historical backtests collapsed, and its live signals completely broke.
4. **High Transaction Friction**: Trading inverse ETFs (`SH`) weekly generates substantial slippage, tracking error, high expense ratios, and tax liabilities (short-term capital gains) which are underrepresented in backtests (often assumed at a flat 0.05% or 0.10%).

---

## 3. Out-of-Sample Performance (13-Year Decisive Check: 2013-2026)

The real-world performance of this strategy since its 2013 publication has been a catastrophic failure.

### Real-World Timeline of Failures
* **Late 2014**: The model got caught on the wrong side of the market. It switched to `SH` (short S&P 500) right before the market bottomed and remained stuck in `SH` as the market surged. It underperformed SPY by over **22%** in 2014 alone (YTD ~ -10% vs SPY's +12%). The author blamed Portfolio123 data revisions and was forced to perform a retrospective "minor revision" to the algorithm on 12/7/2014.
* **Late 2016**: Portfolio123 revised `#SPEPSCY` again, causing the unrevised algorithm to generate erratic signals. Due to R2G platform rules restricting revisions to once every 6 months, the author abandoned the public P123 R2G model and launched a private **`*.R1`** series hosted directly on the iMarketSignals website, allowing manual parameter tweaks to prevent further public embarrassment.
* **Long-Term Performance Destruction (2009-2025)**:
  According to iMarketSignals' own weekly reports (`iM-Best Reports` published in 2023, 2024, and 2025):
  * **By April 10, 2023**: A starting capital of 00,000 at inception (Jan 2, 2009) had **shrunk to 3,192** (-36.8%).
  * **By February 5, 2024**: Grew slightly to **9,745** (excluding fees/slippage).
  * **By April 1, 2025**: Grew slightly to **0,330** (excluding fees/slippage).
  * **By November 3, 2025**: Shrunk to **8,896** (including 62 cash and excluding ,818 spent on fees and slippage).
  * **Comparison**: Over this exact same period (January 2, 2009 to November 2025), a simple Buy-and-Hold of **SPY grew from 0.24 to over 70 (an increase of over 6.3x)**, transforming 00,000 into **30,000+** (before dividends). The strategy lost over 31% of nominal capital while the market was in one of its greatest bull runs in history.

---

## 4. Debunk Search & Community Criticism

* **Portfolio123 Forums**: Users complained heavily about incorrect performance statistics, erratic switches, and the "disastrous loss" in late 2014. For instance, in late 2014, users noted the strategy was stuck in `SH` while the market rocketed, and accused the author of "backdating signals" to cover up losses (which the author denied, claiming it was due to system-wide data series revisions).
* **Quant Community Critiques**: Cam Hui of *Humble Student of the Markets* explicitly critiqued Northy/Georg Vrba's recession/timing models in 2016, noting: *"Too often, backtested systems overfit data and yield stellar returns during the study period, but fail dismally when put into production... [Their studies] may be a case of data overfitting and torturing the data until it talks."*

---

## 5. Verdict and Replication Recommendation

### Verdict: Overfit & Definitively Debunked (DO NOT REPLICATE)
* **Reproducibility**: Low. The model relies on proprietary Portfolio123 database structures and specific, revised estimated earnings series (`#SPEPSCY`) that are not easily accessible in standard historical databases.
* **Overfit**: Extremely high. The model was heavily optimized on 2000-2013 data to maximize backtest performance. Once subjected to real-world, out-of-sample data, it broke repeatedly, was continuously adjusted ("R1" versions), and ultimately destroyed more than 30% of nominal capital while the benchmark went up over 500%.
* **Recommendation**: **A replication backtest is NOT worth our time.** The strategy is a textbook example of a data-mined "toy model" that relies on un-reproducible, retrospectively-revised proprietary macro data and suffers from catastrophic out-of-sample decay.

---

## Sources / References
* Original Article: https://imarketsignals.com/2013/im-best-market-timing-system/
* SPY-SH Description: https://imarketsignals.com/2013/im-bestspy-sh-market-timing-system-gains-for-up-and-down-markets/
* System Performance Archive: https://imarketsignals.com/systems/im-best-market-timing-systems/
* Final R1 Revision Post: https://imarketsignals.com/2016/model-revision-combo3-r1-replaces-combo3/
* Weekly Report (Nov 2025): https://imarketsignals.com/2025/im-best-reports-11-3-2025/
* Weekly Report (Apr 2025): https://imarketsignals.com/2025/im-best-reports-4-1-2025/
* Weekly Report (Feb 2024): https://imarketsignals.com/2024/im-best-reports-2-5-2024/
* Weekly Report (Apr 2023): https://imarketsignals.com/2023/im-best-reports-4-1-2023/
* Forum discussion on overfitting: https://community.portfolio123.com/t/how-best-to-define-buy-rule-without-overfitting/68608
* Humble Student of the Markets Critique: https://humblestudentofthemarkets.com/2016/09/18/is-a-recession-just-around-the-corner/