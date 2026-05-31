# CPM Closest Published TAA Peer Findings

## 1. Introduction and Strategy Context

CPM (Cross-asset Parity Momentum) is a tactical asset allocation (TAA) strategy that operates on a diversified 8-asset universe (QQQ, SPHQ, EFA, EEM, VNQ, GLD, TLT, DBC) and rebalances monthly. To assess whether "AAA-style" is the most accurate headline comparator for cpm_memo.md, this document analyzes the exact mechanics of major published TAA strategies and maps them to CPM's components.

### CPM Core Components:
- **Universe:** 8 cross-asset ETFs.
- **Positive-trend Screen:** Asset-level 10-month SMA trend filter (m_faber = price / SMA_10m - 1 > 0).
- **Ranking:** Risk-adjusted momentum (m_faber / rv_252d). Volatility enters the cross-sectional ranking.
- **Breadth Cap:** Top 4 of 8.
- **Weighting:** Inverse-volatility (1 / rv_504d) across surviving positives.
- **Partial-safe Routing:** Strict-4 partial-safe (unused slots go to safe asset).
- **Canary:** HYG-or-TIP 13612U momentum (risk-on/off permission).
- **Safe Selector:** best of SHV/IEF by 13612U.


## 2. Published Strategy Analysis and Closeness Mapping

### AAA -- Adaptive Asset Allocation (Butler, Philbrick, Gordillo, Varadi 2012)
- **Selection Rule:** Rank by momentum (typically trailing 6-month or 120-day return) and select the top-N (typically top-half or top 5).
- **Ranking Factors:** Pure Return (R). Volatility and correlation do not enter the ranking phase.
- **Weighting Scheme:** Minimum Variance Optimization (MVO) or Risk Parity using trailing covariance (20-day and 126-day windows).
- **Defensive Mechanism:** Timing/absolute momentum filter on selected assets, fallback to safe asset. No separate canary asset or global breadth scaling.
- **Closeness Score per Component:**
  - *Universe:* High (highly diversified multi-asset).
  - *Trend Screen:* Medium (uses asset-level absolute momentum).
  - *Ranking:* Low (pure return-based, ignoring volatility).
  - *Weighting:* High (MVO/Risk Parity is the covariance-inclusive generalization of CPM's simplified inverse-vol weighting).
  - *Defensive:* Low-Medium (no canary, no breadth-scaled partial routing).

### FAA -- Flexible Asset Allocation (Keller & van Putten 2012)
- **Selection Rule:** Ordinal multi-factor rank on R, V, and C. Select top-3 of 7.
- **Ranking Factors:** Return (R, 4-month total return), Volatility (V, 4-month realized volatility, lower is better), Correlation (C, 4-month average correlation to equal-weighted index, lower is better).
  - Score = 1.0 * Rank_R + 0.5 * Rank_V + 0.5 * Rank_C.
- **Weighting Scheme:** Equal-weighting of top selected assets (1/3 each).
- **Defensive Mechanism:** Absolute momentum check on selected assets. If 4-month return <= 0, that asset's tranche is routed to the cash proxy (SHY).
- **Closeness Score per Component:**
  - *Universe:* High (similar 7-asset vs CPM's 8-asset).
  - *Trend Screen:* High (absolute momentum filter).
  - *Ranking:* High (explicitly penalizes volatility and correlation in ranking *before* selection, matching CPM's vol-in-rank philosophy).
  - *Weighting:* Low-Medium (Equal-weighting, but routes failed assets to cash, resembling partial-safe).
  - *Defensive:* Medium (no global canary or global breadth scaling, but uses individual asset timing to go to cash).

### EAA -- Elastic Asset Allocation (Keller & Butler 2014)
- **Selection Rule:** Rank by exponential score z_i = ( (r_i^wR * (1 - c_i)^wC) / v_i^wV )^wS. Select top-3 of 10.
- **Ranking Factors:** Return (r_i, average of 1/3/6/12m), Volatility (v_i, 12m realized vol), Correlation (c_i, 12m correlation to equal-weighted index). Under paper-default elasticities (wR=1, wV=0, wC=1, wS=2), volatility is ignored. But if wV > 0, volatility acts as a rank-penalizer.
- **Weighting Scheme:** Score-proportional weighting across the selected assets.
- **Defensive Mechanism:** Elastic cash fraction CF = 1 - n/N where n is the number of assets with positive returns (r_i > 0). CF goes to BIL.
- **Closeness Score per Component:**
  - *Universe:* High (10 assets, similar multi-asset).
  - *Trend Screen:* High.
  - *Ranking:* High (mathematically includes volatility in rank when wV > 0).
  - *Weighting:* Medium (dynamic, score-proportional instead of inverse-vol).
  - *Defensive:* High (uses global universe breadth to scale safe exposure, very similar in spirit to CPM's partial-safe routing).

### VAA -- Vigilant Asset Allocation (Keller & Keuning 2017)
- **Selection Rule:** Rank by 13612W momentum and select the top-1 offensive asset.
- **Ranking Factors:** Pure Return (13612W weighted momentum). No volatility.
- **Weighting Scheme:** Concentrated 100% in a single offensive asset (or 100% in defensive asset).
- **Defensive Mechanism:** "Any-negative" breadth filter (B=1). If any offensive asset's 13612W momentum is <= 0, the strategy rotates 100% into the best defensive asset (LQD/IEF/SHY) by 13612W.
- **Closeness Score per Component:**
  - *Universe:* Medium-Low (4 offensive, 3 defensive).
  - *Trend Screen:* High.
  - *Ranking:* Low (pure return, no vol).
  - *Weighting:* Low (100% concentration vs inverse-vol).
  - *Defensive:* Medium (breadth-based, but binary 100% or 0% risk-off, unlike CPM's partial-safe or permissive canary).

### DAA -- Defensive Asset Allocation (Keller & Keuning 2018)
- **Selection Rule:** Rank by 13612W momentum and select top-6 of G12.
- **Ranking Factors:** Pure Return (13612W weighted momentum). No volatility.
- **Weighting Scheme:** Equal weighting of selected offensive assets.
- **Defensive Mechanism:** Canary breadth check on 2 assets (VWO, BND). Cash/defensive fraction is 0%, 50%, or 100% depending on how many canary assets have negative momentum. Defensive portion goes to the single best defensive asset (SHY/IEF/LQD).
- **Closeness Score per Component:**
  - *Universe:* High (12 assets, very similar to CPM).
  - *Trend Screen:* High.
  - *Ranking:* Low (pure return, no vol).
  - *Weighting:* Low (equal weight).
  - *Defensive:* High (uses a narrow multi-asset canary universe to determine defensive scaling, similar in spirit to CPM's HYG-or-TIP gate).

### HAA -- Hybrid Asset Allocation (Keller & Keuning 2023)
- **Selection Rule:** Rank offensive assets by 13612U momentum and select top-4 of 8.
- **Ranking Factors:** Pure Return (13612U average return). No volatility in ranking.
- **Weighting Scheme:** Equal weighting of the selected 4 assets (25% each).
- **Defensive Mechanism:** Single canary asset (TIP). If TIP's 13612U momentum is <= 0, go 100% defensive into the best of BIL/IEF. If TIP is positive, go offensive: for each of the selected top 4, if its momentum is <= 0, replace its 25% allocation with the best defensive asset (BIL or IEF).
- **Closeness Score per Component:**
  - *Universe:* Very High (8 assets, shares QQQ, EFA, EEM, VNQ, DBC, IEF, TLT).
  - *Trend Screen:* High (13612U trend screen).
  - *Ranking:* Low (pure return-based, no volatility in rank).
  - *Weighting:* Medium-Low (Equal weight, but incorporates slot-level cash replacement).
  - *Defensive:* Very High (TIP canary as global risk-on/off permission, dynamic safe selector between BIL/IEF, and tranche-level cash replacement which matches CPM's partial-safe routing).

### PAA -- Protective Asset Allocation (Keller & Keuning 2016)
- **Selection Rule:** Rank by SMA(13) distance, select top-6 of 12.
- **Ranking Factors:** Pure Return (SMA distance). No volatility.
- **Weighting Scheme:** Equal weighting of selected assets.
- **Defensive Mechanism:** Linear breadth-based crash protection. Cash fraction is determined globally by BF = (N - n) / (N - n1) where n is the number of positive assets. BF goes to IEF.
- **Closeness Score per Component:**
  - *Universe:* High (12 assets).
  - *Trend Screen:* High (SMA distance).
  - *Ranking:* Low (pure return, no vol).
  - *Weighting:* Low (equal weight).
  - *Defensive:* High (global breadth-scaled cash fraction, very close in spirit to partial-safe breadth scaling).

### GTAA -- Faber Global Tactical Asset Allocation (Faber 2007)
- **Selection Rule:** Filter each asset in universe by 10-month SMA.
- **Ranking Factors:** None (no cross-sectional ranking).
- **Weighting Scheme:** Equal weighting.
- **Defensive Mechanism:** Individual asset-level timing. If an asset is below its SMA, its allocation tranche goes to cash.
- **Closeness Score per Component:**
  - *Universe:* Medium-High (5 or 13 assets).
  - *Trend Screen:* Very High (CPM's absolute trend screen m_faber > 0 is exactly Faber's 10m SMA trend filter).
  - *Ranking:* None.
  - *Weighting:* Low (equal weight).
  - *Defensive:* Medium-High (individual slot timing is the direct ancestor of CPM's partial-safe routing).


## 3. Key Comparative Analysis

### Is AAA really the closest peer?
- **Yes, for Weighting Structure:** Both strategies use a dynamic, risk-based weighting engine rather than simple equal weighting. CPM's inverse-volatility weighting is "Naive Risk Parity" (or minimum-variance under equal correlation assumptions), which is a direct, robust sub-model of AAA's covariance-inclusive Minimum Variance Optimization.
- **No, for Ranking Philosophy:** AAA selects its assets using pure return momentum. CPM, by contrast, ranks assets by return divided by realized volatility (m_faber / rv_252d), meaning volatility enters the rank itself. In this regard, FAA and EAA are much closer peers because they are the only published strategies that explicitly penalize volatility during the cross-sectional ranking phase.

### Which strategy best matches CPM's defense?
- **HAA (Hybrid Asset Allocation) is the closest defensive match:**
  - Both use a canary asset (TIP for HAA, HYG-or-TIP for CPM) as a global risk-on/off permission filter.
  - Both use a dynamic safe selector (BIL/IEF for HAA, SHV/IEF for CPM) based on momentum.
  - Both use tranche-level absolute momentum screens to route individual weak assets to safe assets, resulting in a breadth-scaled partial-safe exposure (HAA routes a selected asset's 25% tranche to BIL/IEF if its momentum is negative; CPM routes unallocated slots under its top-4 cap to SHV/IEF when fewer than 4 assets pass the positive-trend screen).


## 4. Verdict and Recommendation

CPM is a modern hybrid strategy that synthesizes elements from several classic TAA lineages. It is not purely "AAA-style" or "Keller-style," but a deliberate combination of both.

### Recommended Framing for the Memo:
1. **Acknowledge the Hybrid Nature:** Describe CPM explicitly as a synthesis of:
   - **AAA-style Portfolio Weighting:** Employs risk-adjusted weighting (inverse-volatility / naive risk parity) rather than equal weighting.
   - **FAA/EAA-style Risk-Adjusted Ranking:** Incorporates volatility into the cross-sectional ranking phase (Return divided by Volatility) to filter out high-volatility spikes, while omitting the correlation factor (C) that makes FAA/EAA prone to estimation errors.
   - **Keller-style (HAA/DAA) Canary & Breadth Defense:** Uses a permissive global canary gate (HYG-or-TIP) combined with breadth-scaled partial-safe routing and a dynamic safe selector.
2. **Retain "AAA-style" as the Weighting Benchmark:** Keep AAA as the headline weighting and performance benchmark, as it is the most well-known strategy that rejects equal weighting in favor of volatility/covariance risk weights.
3. **Add FAA/EAA and HAA to the Context:** Introduce FAA/EAA when discussing the ranking metric, and HAA when explaining the canary/partial-safe defensive design. This provides full academic rigor and positions CPM as an optimized evolution of the published literature.


## 5. Sources and Academic Literature

- **AAA:** Butler, A., Philbrick, M., Gordillo, R., & Varadi, D. (2012). *Adaptive Asset Allocation: A Primer*. SSRN: https://ssrn.com/abstract=2328254
- **FAA:** Keller, W. J., & van Putten, H. (2012). *Generalized Momentum and Flexible Asset Allocation (FAA): An Heuristic Approach*. SSRN: https://ssrn.com/abstract=2193735
- **EAA:** Keller, W. J., & Butler, A. (2014). *A Century of Generalized Momentum; From Flexible Asset Allocations (FAA) to Elastic Asset Allocation (EAA)*. SSRN: https://ssrn.com/abstract=2543979
- **VAA:** Keller, W. J., & Keuning, J. W. (2017). *Breadth Momentum and Vigilant Asset Allocation (VAA): Winning More by Losing Less*. SSRN: https://ssrn.com/abstract=3002624
- **DAA:** Keller, W. J., & Keuning, J. W. (2018). *Breadth Momentum and the Canary Universe: Defensive Asset Allocation (DAA)*. SSRN: https://ssrn.com/abstract=3212862
- **HAA:** Keller, W. J., & Keuning, J. W. (2023). *Dual and Canary Momentum with Rising Yields/Inflation: Hybrid Asset Allocation (HAA)*. SSRN: https://ssrn.com/abstract=4346906
- **PAA:** Keller, W. J., & Keuning, J. W. (2016). *Protective Asset Allocation (PAA): A Simple Momentum-Based Alternative for Term Deposits*. SSRN: https://ssrn.com/abstract=2759734
- **GTAA:** Faber, M. T. (2007). *A Quantitative Approach to Tactical Asset Allocation*. SSRN: https://ssrn.com/abstract=962461
