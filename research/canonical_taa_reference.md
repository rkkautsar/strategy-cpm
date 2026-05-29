# Canonical Tactical Asset Allocation (TAA) Reference Sheet

This reference document outlines the exact canonical rules, asset universes, momentum formulas, risk-gating breadth metrics, and portfolio optimization mathematics for ten (10) major Tactical Asset Allocation (TAA) strategies.

All formulas, lookbacks, and parameters represent the primary specifications from the original academic publications or foundational whitepapers.

---

## 1. Protected Adaptive Asset Allocation (PAAA)
**Authors:** Bellu, Mirko & Conversano, Claudio (2020)  
**Publication:** *Protected Adaptive Asset Allocation*, Finance Research Letters, Volume 32, January 2020.  
**SSRN / DOI:** [https://doi.org/10.1016/j.frl.2019.01.007](https://doi.org/10.1016/j.frl.2019.01.007)

### A. Canonical Universe
* **Risky Assets ($N=10$):** `SPY` (US Large Cap), `VGK` (Europe Equities), `EWJ` (Japan Equities), `EEM` (Emerging Markets), `VNQ` (US Real Estate), `RWX` (International Real Estate), `DBC` (Commodities), `GLD` (Gold), `IEF` (Intermediate-Term Treasuries), `TLT` (Long-Term Treasuries).
* **Safe Asset:** `SHY` (Short-Term Treasuries) or cash-equivalents (e.g. `BIL` / 3-month T-Bills).

### B. Momentum Scoring & Lookback Window
* **Lookback Window:** Trailing 6 months ($L = 6$, approximately 126 trading days).
* **Momentum Metric ($R_{6,i}$):** Simple total return over the past 6 months:
  $$R_{6,i} = rac{p_{0,i}}{p_{126,i}} - 1$$
  where $p_{0,i}$ is the current price and $p_{126,i}$ is the price 126 trading days ago.

### C. Risk Gating & Canary Breadth Rules
PAAA introduces PAA-style multi-market breadth protection to the traditional Adaptive Asset Allocation (AAA) model.
* **Positive Momentum Count ($n$):** Count the number of risky assets with $R_{6,i} > 0$.
* **Bond/Cash Fraction ($BF$):** Calculated using the Protective Asset Allocation (PAA) formula:
  $$BF = rac{N - n}{N - n_1}$$
  where $n_1$ is the protection level threshold. Under the default high protection setting ($pf = 2$, $N = 10 \implies n_1 = 5$):
  $$BF = \max\left(0, \min\left(1, rac{10 - n}{5}ight)ight)$$
  * If $n \ge 10 \implies BF = 0\%$ (100% risk-on).
  * If $n = 9 \implies BF = 20\%$.
  * If $n = 8 \implies BF = 40\%$.
  * If $n = 7 \implies BF = 60\%$.
  * If $n = 6 \implies BF = 80\%$.
  * If $n \le 5 \implies BF = 100\%$ (100% risk-off, fully defensive).

### D. Weighting & Portfolio Optimization Mathematics
* **Risky Allocation ($1 - BF$):** Invested in the top $K = 5$ risky assets with the highest positive momentum score ($R_{6,i} > 0$).
* **Weighting Mechanics:** Rather than equal weighting, the weights of the $K$ selected assets are computed using **Minimum Variance Optimization (MVO)**:
  $$\min_{w} w^T \Sigma w$$
  subject to:
  $$\sum_{i=1}^K w_i = 1, \quad w_i \ge 0$$
  where $\Sigma$ is the rolling covariance matrix of the daily returns of the $K$ selected assets, typically estimated over a trailing window of 126 trading days (for correlation) and 20 trading days (for volatility).
* **Final Weights:** The optimal weights $w_i^*$ from MVO are scaled by the risky fraction:
  $$w_{	ext{final}, i} = (1 - BF) 	imes w_i^*$$
  The defensive asset receives the cash fraction $BF$.

---

## 2. Flexible Asset Allocation (FAA)
**Authors:** Keller, Wouter J. & van Putten, Hugo (2012)  
**Publication:** *Generalized Momentum and Flexible Asset Allocation (FAA): An Heuristic Approach*, SSRN Working Paper, December 24, 2012.  
**SSRN / DOI:** [https://ssrn.com/abstract=2193735](https://ssrn.com/abstract=2193735)

### A. Canonical Universe
* **Risky Assets ($N=7$):**
  1. US Equities (`VTSMX` or ETF proxy `SPY`)
  2. Developed Market Equities (`FDIVX` or ETF proxy `EFA`)
  3. Emerging Market Equities (`VEIEX` or ETF proxy `EEM`)
  4. US Intermediate-Term Bonds (`VBMFX` or ETF proxy `AGG`)
  5. US Short-Term Treasuries (`VFISX` or ETF proxy `SHY`) — acts as cash proxy and defensive asset.
  6. Commodities (`QRAAX` or ETF proxy `DBC`)
  7. Real Estate / REITs (`VGSIX` or ETF proxy `VNQ`)

### B. Momentum Scoring & Lookback Window
FAA scores and ranks assets based on "generalized momentum" across three factors (Return, Volatility, and Correlation) over a **4-month** lookback window ($L = 4$, or approximately 84 trading days).
* **Relative Momentum ($R_i$):** Trailing 4-month total return:
  $$R_i = rac{p_{0,i}}{p_{84,i}} - 1$$
* **Volatility ($V_i$):** Standard deviation of daily returns over the trailing 4 months (annualized).
* **Correlation ($C_i$):** Average Pearson correlation coefficient of daily returns between asset $i$ and the other 6 assets over the trailing 4 months.

### C. Risk Gating & Canary Breadth Rules
FAA does not use a separate canary asset. It applies an absolute momentum trend filter directly to the selected assets (dual momentum).
* **Absolute Momentum Filter:** For each of the top selected assets, if its 4-month return is positive ($R_i > 0$), it is eligible for investment. If $R_i \le 0$, the capital portion for that asset is allocated to the cash proxy (`VFISX` / `SHY`).

### D. Weighting & Portfolio Optimization Mathematics
* **Nested Ranking Score ($MVC_i$):**
  For each of the $N=7$ assets, calculate its ordinal rank (1 to 7) for each factor:
  * $MR_i$: Rank of Momentum $R_i$ (ascending; 1 is highest return, 7 is lowest).
  * $VR_i$: Rank of Volatility $V_i$ (ascending; 1 is lowest volatility, 7 is highest).
  * $CR_i$: Rank of Correlation $C_i$ (ascending; 1 is lowest correlation, 7 is highest).
  The combined ranking score is a weighted linear combination of these ordinal ranks:
  $$MVC_i = w_R 	imes MR_i + w_V 	imes VR_i + w_C 	imes CR_i$$
  where the canonical weights are:
  $$w_R = 1.0, \quad w_V = 0.5, \quad w_C = 0.5$$
* **Selection:** Sort assets in ascending order of $MVC_i$ (lower score is better). Select the top $K = 3$ assets.
* **Weighting Mechanics:** Each of the top 3 chosen tranches is allocated $1/3 pprox 33.3\%$ of the portfolio.
  * If a selected asset has $R_i > 0 \implies$ invest $33.3\%$ in that asset.
  * If a selected asset has $R_i \le 0 \implies$ invest $33.3\%$ in the cash proxy.

---

## 3. Elastic Asset Allocation (EAA)
**Authors:** Keller, Wouter J. & Butler, Adam (2014)  
**Publication:** *A Century of Generalized Momentum; From Flexible Asset Allocations (FAA) to Elastic Asset Allocation (EAA)*, SSRN Working Paper, December 30, 2014.  
**SSRN / DOI:** [https://ssrn.com/abstract=2543979](https://ssrn.com/abstract=2543979)

### A. Canonical Universe
* **Risky Assets ($N=10$):** `SPY`, `EFA`, `EEM`, `VNQ`, `DBC`, `GLD` (Gold), `TLT` (Long-Term Treasuries), `IEF` (Intermediate-Term Treasuries), `LQD` (Investment-Grade Corporates), `HYG` (High-Yield Bonds).
* **Safe Asset:** `BIL` (1-3 Month T-Bills) or cash.

### B. Momentum Scoring & Lookback Window
EAA generalizes FAA by replacing ordinal ranking with cardinal "elasticity-weighted" scores. All estimates use a **12-month** lookback window ($L = 12$).
* **Return ($r_i$):** Unweighted average of trailing 1, 3, 6, and 12-month returns:
  $$r_i = rac{R_1 + R_3 + R_6 + R_{12}}{4}$$
* **Volatility ($v_i$):** Annualized standard deviation of daily returns over the past 12 months.
* **Correlation ($c_i$):** Pairwise correlation coefficient of daily returns between asset $i$ and the equal-weighted index of all 10 assets over the past 12 months.

### C. Risk Gating & Canary Breadth Rules
EAA utilizes an "elastic cash" mechanism where the defensive allocation scales dynamically with the number of assets in distress.
* **Eligible Assets ($n$):** Count the number of assets with positive returns ($r_i > 0$).
* **Cash/Defensive Fraction ($CF$):** 
  $$CF = 1 - rac{n}{N}$$
  where $N = 10$. This fraction $CF$ is allocated to `BIL`.

### D. Weighting & Portfolio Optimization Mathematics
* **Scoring Formula ($z_i$):** For each asset, if $r_i > 0$, compute its exponential score:
  $$z_i = \left( rac{r_i^{w_R} \cdot (1 - c_i)^{w_C}}{v_i^{w_V}} ight)^{w_S}$$
  If $r_i \le 0 \implies z_i = 0$.  
  The default elasticities (weights) optimized in the paper are:
  $$w_R = 1.0, \quad w_V = 0.0, \quad w_C = 1.0, \quad w_S = 2.0$$
  Under these parameters, volatility is ignored ($w_V = 0$), and the score simplifies to:
  $$z_i = \left( r_i \cdot (1 - c_i) ight)^2 \quad 	ext{for } r_i > 0$$
* **Selection:** Select the top $K = 3$ assets with the highest score $z_i$.
* **Weighting Mechanics (Score-Proportional):** The remaining risky fraction $(1 - CF)$ is allocated among the selected assets proportionally to their scores $z_i$:
  $$w_i = (1 - CF) 	imes rac{z_i}{\sum_{j \in 	ext{selected}} z_j}$$

---

## 4. Generalized Protective Momentum (GPM)
**Authors:** Keuning, Jan Willem & Keller, Wouter J. (2016)  
**Publication:** *Generalized Protective Momentum*, SSRN Working Paper, 2016.  
**SSRN / DOI:** [https://ssrn.com/abstract=2759734](https://ssrn.com/abstract=2759734) (derived from PAA research)

### A. Canonical Universe
* **Risky Assets ($N=12$):** `SPY`, `QQQ` (Nasdaq 100), `IWM` (Russell 2000), `EEM` (Emerging Markets), `VGK` (Europe), `EWJ` (Japan), `VNQ` (US Real Estate), `DBC` (Commodities), `GLD` (Gold), `TLT` (Long-Term Treasuries), `HYG` (High Yield), `LQD` (Investment-Grade Corporates).
* **Crash Protection (CP) Assets:** Rotates between `SHY` and `IEF` (best of 2).

### B. Momentum Scoring & Lookback Window
GPM uses unweighted average returns and rolling correlations over a **12-month** lookback window.
* **Return ($r_i$):** Unweighted average of trailing 1, 3, 6, and 12-month returns:
  $$r_i = rac{R_1 + R_3 + R_6 + R_{12}}{4}$$
* **Correlation ($c_i$):** Trailing 12-month Pearson correlation of daily returns between asset $i$ and the equal-weighted portfolio of the 12 risky assets.
* **Scoring Options:** GPM defines three momentum score variations:
  1. **GPMxR (Raw Return):** $score_i = r_i$ (unhedged)
  2. **GPMxM (Correlation Multiplied):** $score_i = r_i 	imes (1 - c_i)$ (EAA style)
  3. **GPMxF (Correlation Fractioned):** $score_i = rac{r_i}{1 + c_i}$ (fractional hedge)

### C. Risk Gating & Canary Breadth Rules
Uses PAA's breadth-based crash protection routine.
* **Positive Momentum Count ($n$):** Count the number of risky assets with $r_i > 0$.
* **Bond/Cash Fraction ($BF$):**
  $$BF = rac{N - n}{N - n_1}$$
  clamped to $[0, 1]$, where $n_1 = pf 	imes N / 4$. Under the standard high protection level ($pf = 2$, $N = 12 \implies n_1 = 6$):
  $$BF = \max\left(0, \min\left(1, rac{12 - n}{6}ight)ight)$$
  * If $n \le 6 \implies BF = 100\%$ (100% defensive).
  * If $n \ge 12 \implies BF = 0\%$ (100% risky).

### D. Weighting & Portfolio Optimization Mathematics
* **Selection:** Select the top $K = 3$ risky assets with the highest score ($score_i$).
* **Weighting Mechanics:** 
  * The risky portion $(1 - BF)$ is allocated equally ($1/3$ each) to the top 3 selected assets:
    $$w_i = rac{1 - BF}{3}$$
  * The defensive portion $BF$ is allocated entirely to the CP asset (`SHY` or `IEF`) with the highest score.

---

## 5. Protective Asset Allocation (PAA)
**Authors:** Keller, Wouter J. & Keuning, Jan Willem (2016)  
**Publication:** *Protective Asset Allocation (PAA): A Simple Momentum-Based Alternative for Term Deposits*, SSRN Working Paper, April 5, 2016.  
**SSRN / DOI:** [https://ssrn.com/abstract=2759734](https://ssrn.com/abstract=2759734)

### A. Canonical Universe
* **Risky Assets ($N=12$):** `SPY`, `IWM`, `QQQ`, `VGK`, `EWJ`, `EEM` (or `VWO`), `VNQ`, `DBC` (or `GSG`), `GLD`, `TLT`, `HYG`, `LQD`.
* **Crash Protection (CP) Asset:** `IEF` (and/or rotated with `SHY` based on 13-month SMA momentum in PAA-CPR).

### B. Momentum Scoring & Lookback Window
* **Lookback Window ($L = 12$):** Trailing 12 months, using 13 monthly closing prices ($p_0, p_1, \dots, p_{12}$).
* **Momentum Score ($MOM_i$):** SMA distance formula:
  $$MOM_i = rac{p_{0,i}}{	ext{SMA}_{13}(p_{0..12, i})} - 1 = rac{p_{0,i}}{rac{1}{13} \sum_{j=0}^{12} p_{j,i}} - 1$$

### C. Risk Gating & Canary Breadth Rules
PAA applies a linear breadth protection scaling algorithm.
* **Positive Momentum Count ($n$):** Count the number of risky assets with $MOM_i > 0$.
* **Bond/Cash Fraction ($BF$):**
  $$BF = rac{N - n}{N - n_1}$$
  clamped to $[0, 1]$, where $n_1 = pf 	imes N / 4$. Under the default high protection level ($pf = 2$, $N = 12 \implies n_1 = 6$):
  $$BF = \max\left(0, \min\left(1, rac{12 - n}{6}ight)ight)$$
  This yields a step-wise risk gating function:
  * $n \le 6 \implies BF = 100\%$
  * $n = 7 \implies BF = 83.3\%$
  * $n = 8 \implies BF = 66.7\%$
  * $n = 9 \implies BF = 50.0\%$
  * $n = 10 \implies BF = 33.3\%$
  * $n = 11 \implies BF = 16.7\%$
  * $n = 12 \implies BF = 0\%$

### D. Weighting & Portfolio Optimization Mathematics
* **Selection:** Select the top $K = 6$ risky assets with the highest $MOM_i$.
* **Weighting Mechanics:** Equal-weighting of the selected risky assets:
  * The risky portion $(1 - BF)$ is divided equally among the top 6 assets (each receiving $(1 - BF)/6$).
  * The defensive portion $BF$ is invested in the CP asset (`IEF` or cash).
  * Note: Because $BF = 100\%$ when $n \le 6$, the risky allocation is only active when $n \ge 7$.

---

## 6. Vigilant Asset Allocation (VAA)
**Authors:** Keller, Wouter J. & Keuning, Jan Willem (2017)  
**Publication:** *Breadth Momentum and Vigilant Asset Allocation (VAA): Winning More by Losing Less*, SSRN Working Paper, July 14, 2017.  
**SSRN / DOI:** [https://ssrn.com/abstract=3002624](https://ssrn.com/abstract=3002624)

### A. Canonical Universe
* **Offensive Universe ($N=4$, VAA-G4):** `SPY` (US Stocks), `VEA` or `EFA` (Developed Foreign), `EEM` (Emerging Markets), `AGG` (US Aggregate Bonds).
* **Defensive Universe ($M=3$):** `LQD` (Corporate Bonds), `IEF` (Intermediate Treasuries), `SHY` (Short-Term Treasuries).

### B. Momentum Scoring & Lookback Window
* **Momentum Metric ($13612W$):** Weighted sum of 1, 3, 6, and 12-month returns:
  $$13612W = 12 	imes R_1 + 4 	imes R_3 + 2 	imes R_6 + 1 	imes R_{12}$$
  where $R_k = rac{p_0}{p_k} - 1$ is the total return over the past $k$ months.
  *(This weighted average heavily emphasizes recent momentum: the 1-month return represents $12/19 pprox 63\%$ of the total score).*

### C. Risk Gating & Canary Breadth Rules
VAA uses a highly vigilant "any-negative" breadth filter in its aggressive version ($B=1$).
* **Positive Momentum Count ($n$):** Count the number of offensive assets with $13612W > 0$.
* **Bond Fraction ($BF$):**
  * If $n = 4 \implies BF = 0\%$ (all 4 offensive assets are positive $\implies$ 100% risk-on).
  * If $n < 4 \implies BF = 100\%$ (if even a single offensive asset turns negative $\implies$ 100% risk-off).

### D. Weighting & Portfolio Optimization Mathematics
* **Offensive (Risk-On):** 100% of the portfolio is invested in the single offensive asset ($T = 1$) with the highest positive $13612W$ score.
* **Defensive (Risk-Off):** 100% of the portfolio is invested in the single defensive asset ($M = 3$) with the highest $13612W$ score.

---

## 7. Defensive Asset Allocation (DAA)
**Authors:** Keller, Wouter J. & Keuning, Jan Willem (2018)  
**Publication:** *Breadth Momentum and the Canary Universe: Defensive Asset Allocation (DAA)*, SSRN Working Paper, July 12, 2018.  
**SSRN / DOI:** [https://ssrn.com/abstract=3212862](https://ssrn.com/abstract=3212862)

### A. Canonical Universe
* **Offensive Universe ($N=12$, G12):** `SPY`, `IWM`, `QQQ`, `VGK`, `EWJ`, `VWO` (Emerging Markets), `VNQ`, `GSG` (or `DBC`), `GLD`, `TLT`, `HYG`, `LQD`.
* **Canary Universe ($B=2$):** `VWO` (Emerging Markets) and `BND` (Total US Bond Market).
* **Defensive Universe ($M=3$):** `SHY`, `IEF`, `LQD`.

### B. Momentum Scoring & Lookback Window
* **Momentum Metric ($13612W$):** Weighted sum of 1, 3, 6, and 12-month returns:
  $$13612W = 12 	imes R_1 + 4 	imes R_3 + 2 	imes R_6 + 1 	imes R_{12}$$

### C. Risk Gating & Canary Breadth Rules
DAA improves upon VAA by separating the crash protection signal from the offensive universe, using a narrow two-asset "canary" universe.
* **Canary Breadth Check ($b$):** Count the number of canary assets with $13612W \le 0$ (out of $B = 2$).
* **Bond Fraction ($BF$):**
  $$BF = rac{b}{B}$$
  This yields three discrete cash fraction tiers:
  * $b = 0 \implies BF = 0\%$ (Both canaries positive $\implies$ 100% risk-on).
  * $b = 1 \implies BF = 50\%$ (One canary negative $\implies$ 50% risk-on, 50% risk-off).
  * $b = 2 \implies BF = 100\%$ (Both canaries negative $\implies$ 100% risk-off).

### D. Weighting & Portfolio Optimization Mathematics
* **Offensive Allocation ($1 - BF$):** Invested equally among the top $K = 6$ offensive assets with the highest positive $13612W$ scores.
  * If fewer than 6 offensive assets have positive scores, the unallocated portion is transferred to defensive assets.
* **Defensive Allocation ($BF$):** Invested 100% in the single defensive asset ($M = 3$) with the highest $13612W$ score.

---

## 8. Hybrid Asset Allocation (HAA)
**Authors:** Keller, Wouter J. & Keuning, Jan Willem (2023)  
**Publication:** *Dual and Canary Momentum with Rising Yields/Inflation: Hybrid Asset Allocation (HAA)*, SSRN Working Paper, February 3, 2023.  
**SSRN / DOI:** [https://ssrn.com/abstract=4346906](https://ssrn.com/abstract=4346906)

### A. Canonical Universe
* **Offensive Universe ($N=8$ / $N=9$ with QQQ):** `SPY`, `IWM`, `VEA` (or `EFA`), `VWO` (or `EEM`), `VNQ`, `DBC` (or `PDBC`), `IEF`, `TLT`. *(Standard HAA with QQQ adds `QQQ` as the 9th asset)*.
* **Canary Asset:** `TIP` (US Treasury Inflation-Protected Securities).
* **Defensive Universe:** `BIL` (US T-Bills) and `IEF` (Intermediate Treasuries).

### B. Momentum Scoring & Lookback Window
HAA uses unweighted momentum to capture longer-term trends cleanly.
* **Momentum Metric ($13612U$):** Simple average of trailing 1, 3, 6, and 12-month returns:
  $$13612U = rac{R_1 + R_3 + R_6 + R_{12}}{4}$$

### C. Risk Gating & Canary Breadth Rules
Uses `TIP` as a single canary to signal whether the financial system is under yield-driven or inflationary stress.
* **Canary Check:** Measure $13612U_{	ext{TIP}}$.
  * If $13612U_{	ext{TIP}} > 0 \implies$ Risk-On.
  * If $13612U_{	ext{TIP}} \le 0 \implies$ Risk-Off (100% defensive).

### D. Weighting & Portfolio Optimization Mathematics
* **Risk-On Weighting (Dual Momentum):**
  * Rank offensive assets by $13612U$, and select the top $K = 4$ assets.
  * For each of the top 4 assets:
    * If its $13612U > 0$, allocate $25\%$ to that asset.
    * If its $13612U \le 0$, allocate that $25\%$ tranche to the best defensive asset.
* **Risk-Off Weighting:**
  * Allocate 100% of the portfolio to the single defensive asset (`BIL` or `IEF`) with the highest $13612U$ score.

---

## 9. Faber Global Tactical Asset Allocation (GTAA 5/13)
**Author:** Faber, Mebane T. (2007)  
**Publication:** *A Quantitative Approach to Tactical Asset Allocation*, The Journal of Wealth Management, Spring 2007 (updated in 2009, 2013).  
**SSRN / DOI:** [https://ssrn.com/abstract=962461](https://ssrn.com/abstract=962461)

### A. Canonical Universe
* **GTAA-5 Universe:** `SPY` (US Equities), `EFA` (Foreign Developed), `VNQ` (US Real Estate), `IEF` (Intermediate Treasuries), `DBC` (Commodities).
* **GTAA-13 Universe:** Adds `IWD` (US Value), `IWN` (US Small Value), `EEM` (Emerging Markets), `MTUM` (Momentum Factor), `LQD` (Corporate Bonds), `TLT` (Long Treasuries), `BWX` (International Bonds), `GLD` (Gold).
* **Cash/Defensive Asset:** `BIL` or cash.

### B. Momentum Scoring & Lookback Window
* **Timing Filter:** Trailing 10-month Simple Moving Average (SMA), calculated using monthly closing prices:
  $$	ext{SMA}_{10} = rac{1}{10} \sum_{j=0}^9 p_j$$
  where $p_0$ is the current month-end price.

### C. Risk Gating & Canary Breadth Rules
Faber's model applies the trend filter strictly at the individual asset class level. There are no separate canaries or portfolio-level breadth-scaling parameters.

### D. Weighting & Portfolio Optimization Mathematics
* **GTAA-5 (Standard Equal-Weight):**
  * Portfolio is split into 5 equal tranches of $20\%$ each.
  * For each asset $i$:
    * If $p_{0,i} > 	ext{SMA}_{10, i} \implies$ invest $20\%$ in asset $i$.
    * If $p_{0,i} \le 	ext{SMA}_{10, i} \implies$ invest $20\%$ in the cash proxy (`BIL`).
* **GTAA-13 (Ivy Portfolio Equal-Weight):**
  * Portfolio is split into 13 equal tranches of $7.69\%$ each.
  * Same binary SMA trend filter is applied to each tranche.
* **GTAA-AGG (Aggressive Top 3 / Top 6):**
  * Rank the 13 assets by their trailing returns (typically average of 1, 3, 6, 12-month returns).
  * Select the top $K = 3$ (or $K = 6$) assets.
  * For each selected asset, if its current price is above its 10-month SMA, invest $1/K$ in the asset; otherwise, invest that portion in cash/BIL.

---

## 10. Antonacci Composite / Dual Momentum
**Author:** Antonacci, Gary (2014)  
**Publication:** *Dual Momentum Investing: An Innovative Strategy for Higher Returns with Lower Risk*, McGraw-Hill, 2014.  
**SSRN / DOI:** [https://ssrn.com/abstract=2042750](https://ssrn.com/abstract=2042750)

### A. Canonical Universe
* **Global Equities Momentum (GEM):**
  * Offensive Assets: `SPY` (US Stocks) vs. `VEU` or `EFA` (International Stocks).
  * Defensive Asset: `AGG` (US Aggregate Bonds) or `BND`.
  * Risk-Free Benchmark: `BIL` (3-month T-Bills) or cash.
* **Composite Dual Momentum (CDM):**
  * Divided into 4 equal-weighted modules (25% each):
    1. **Equities:** `SPY` vs. `EFA`
    2. **Credit:** `LQD` vs. `HYG`
    3. **Real Estate:** `VNQ` vs. `REM` (Mortgage REITs)
    4. **Stress:** `GLD` vs. `TLT`
  * Risk-Free Benchmark / Cash: `BIL` or cash.

### B. Momentum Scoring & Lookback Window
* **Lookback Window:** Trailing 12 months.
* **Momentum Metric ($R_{12}$):** Simple 12-month total return:
  $$R_{12, i} = rac{p_{0, i}}{p_{12, i}} - 1$$

### C. Risk Gating & Canary Breadth Rules (Absolute Momentum)
An asset must exhibit positive momentum relative to the risk-free rate to be eligible for investment.
* **GEM Absolute Filter:** Check if $R_{12, 	ext{SPY}} > R_{12, 	ext{BIL}}$.
  * If No $\implies$ 100% Defensive (Bonds).
* **CDM Absolute Filter:** For each module, check if the winner's 12-month return is greater than $R_{12, 	ext{BIL}}$.
  * If No $\implies$ That 25% tranche is allocated to cash (`BIL`).

### D. Weighting & Portfolio Optimization Mathematics
* **GEM Weighting:**
  * If Absolute Momentum is positive: Compare $R_{12, 	ext{SPY}}$ vs. $R_{12, 	ext{VEU}}$ (Relative Momentum). Allocate 100% of the portfolio to the higher-performing asset.
  * If Absolute Momentum is negative: Allocate 100% to bonds (`AGG`).
  * *GEM is always concentrated 100% in a single ETF.*
* **CDM Weighting:**
  * Each of the 4 modules is allocated $25\%$.
  * Within each module:
    * Select the asset with the higher 12-month return (Relative Momentum).
    * If its return exceeds $R_{12, 	ext{BIL}}$ (Absolute Momentum), invest $25\%$ in that asset; otherwise, invest $25\%$ in cash (`BIL`).
