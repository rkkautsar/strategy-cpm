# Tactical Asset Allocation (TAA) and Volatility Targeting Literature Findings

## Strand 1: Factor / Portfolio Volatility Management Literature

The factor and portfolio volatility-management literature establishes that dynamic volatility scaling is a powerful mechanism for improving risk-adjusted returns (Sharpe ratios) and mitigating tail risk:

- **Moreira & Muir (2017) "Volatility-Managed Portfolios" (Journal of Finance)**: Formalized the strategy of scaling portfolio exposure inversely to recent realized variance (i.e., taking less risk when volatility is high). They demonstrated that this approach produces significant positive alphas and increases Sharpe ratios across the market, value, momentum, profitability, investment, and betting-against-beta factors, as well as the currency carry trade. The core mechanism is that volatility is highly persistent (clusters) while expected returns do not increase proportionally with volatility.
- **Barroso & Santa-Clara (2015) "Momentum has its moments" (Journal of Financial Economics)**: Demonstrated that volatility scaling is particularly effective for momentum. By scaling momentum exposure by the inverse of its 6-month realized volatility, they effectively eliminated "momentum crashes" (the catastrophic drawdowns that occur during sharp market turning points), doubling the Sharpe ratio of the momentum factor.
- **Harvey et al. (2018) "The Impact of Volatility Targeting" (AQR / SSRN)**: Investigated volatility targeting across a wide range of asset classes and multi-asset portfolios. They showed that volatility targeting consistently reduces drawdown and left-tail risk, noting that the benefits are concentrated during macroeconomic stress and periods of high systemic volatility.
- **The Out-of-Sample (OOS) and Transaction Cost Critique**:
  - **Cederburg et al. (2020) "On the Performance of Volatility-Managed Portfolios" (JFE)**: Discovered that the impressive in-sample gains from volatility-managed portfolios do not reliably translate out-of-sample due to parameter estimation error and structural instability in the spanning regressions. Real-time OOS implementations often underperform or fail to beat unmanaged portfolios.
  - **Barroso & Detzel (2021) / Abdi et al. (2024)**: Showed that transaction costs severely degrade the performance of volatility timing for non-market factors (e.g., size, value, investment, profitability) due to a dramatic increase in portfolio turnover (up to 15x). The only factor where volatility scaling robustly survives transaction costs and estimation error is momentum, where the avoidance of catastrophic crashes outweighs the trading costs.

---

## Strand 2: Tactical Asset Allocation (TAA) Momentum Lineage

The canonical cross-asset TAA-momentum literature typically handles risk management and drawdown reduction through structural mechanisms rather than an explicit, passive portfolio-level volatility cap:

- **Faber (GTAA, 2007)**: Achieves drawdown protection solely through binary trend-following filters (e.g., 10-month simple moving average) and safe-asset (cash/bond) routing. There is no volatility estimation or volatility targeting in the core strategy.
- **Keller Lineage (VAA, DAA, HAA, BAA, PAA, FAA, EAA)**:
  - **VAA, DAA, HAA, BAA**: Use absolute momentum and "canary" assets (e.g., TIPS, SPY, EEM, AGG) to trigger a binary or tiered switch of the entire portfolio to defensive assets (such as T-bills, intermediate treasuries, or TIPS) when market turbulence is detected.
  - **PAA (Protective Asset Allocation)**: Uses "breadth-based" crash protection. The portfolio's allocation to safe assets (bonds/cash) scales dynamically based on the fraction of risky assets with positive momentum (e.g., if only 3 out of 12 assets are in an uptrend, the remaining exposure is routed to bonds).
  - **FAA (Flexible Asset Allocation) & EAA (Elastic Asset Allocation)**: Rank assets on generalized momentum factors including return (R), volatility (V), and correlation (C). While volatility is used as a cross-sectional ranking factor (to penalize highly volatile assets during selection), these strategies do not target a constant portfolio-level volatility or employ a hard portfolio vol-cap overlay.
- **Butler, Philbrick, Gordillo, Varadi (ReSolve) "Adaptive Asset Allocation" (AAA, 2012/2013/2016)**:
  - The canonical AAA framework selects the top $K$ momentum assets and weights them using Minimum Variance Optimization (MVO) or Risk Parity (RP) based on short-term rolling covariance.
  - In their papers and book, ReSolve explicitly discusses "time diversification" (maintaining a constant portfolio risk level) and "volatility targeting" (e.g., sizing the resulting minimum variance portfolio to target an 8% or 10% annual volatility).
  - However, in canonical research implementations (and platforms like Portfolio Visualizer), the core AAA strategy is represented by the momentum selection + minimum variance optimization. A constant volatility target or vol cap is considered an optional overlay (often involving leverage or cash scaling) rather than the core asset allocation logic.

---

## Verdict

Adding a volatility-target cap to a cross-asset TAA-momentum strategy (CPM) is:

**(b) Borrowed from the factor / CTA volatility-management literature (grounded but from an adjacent field)**  
AND  
**(c) Mainly a practitioner risk-management / execution overlay not central to canonical TAA papers**

### Rationale:
- **Core TAA Protection is Structural**: Canonical TAA strategies (Faber, Keller) manage risk structurally via trend filters, canary rules, safe-asset routing, and breadth-based scaling. They do not use continuous volatility feedback loops or portfolio-level volatility caps.
- **Volatility Targeting is a Overlay/Sizing Mechanism**: Volatility targeting and caps are native to the CTA/trend-following and factor-timing literature (Moreira & Muir, Barroso & Santa-Clara). In a TAA framework like AAA, it is a secondary overlay used to adjust the overall leverage or cash buffers of an already-optimized portfolio.
- **Academic Grounding**: While highly grounded in the factor literature (especially for momentum-based strategies to avoid "momentum crashes"), its application to cross-asset TAA is an execution and risk overlay designed to control tracking error and institutional drawdown constraints rather than a core asset-selection feature of classical TAA models.

---

## Sources

1. Moreira, A., & Muir, T. (2017). "Volatility-Managed Portfolios." *The Journal of Finance*, 72(4), 1611-1644. [URL](https://doi.org/10.1111/jofi.12513)
2. Barroso, P., & Santa-Clara, P. (2015). "Momentum has its moments." *Journal of Financial Economics*, 116(1), 111-120. [URL](https://doi.org/10.1016/j.jfineco.2014.11.009)
3. Harvey, C. R., et al. (2018). "The Impact of Volatility Targeting." *SSRN*. [URL](https://ssrn.com/abstract=3089423)
4. Cederburg, S., O'Doherty, M. S., Wang, F., & Yan, X. (2020). "On the performance of volatility-managed portfolios." *Journal of Financial Economics*, 138(1), 95-117. [URL](https://doi.org/10.1016/j.jfineco.2019.05.012)
5. Butler, A., Philbrick, M., Gordillo, R., & Varadi, D. (2012). "Adaptive Asset Allocation: A Primer." *SSRN*. [URL](https://ssrn.com/abstract=2328254)
6. Keller, W. J., & Keuning, J. W. (2016). "Protective Asset Allocation (PAA): A Simple Momentum-Based Active Common-Sense Strategy." *SSRN*. [URL](https://ssrn.com/abstract=2759734)
