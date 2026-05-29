"""
Protected Adaptive Asset Allocation (PAAA) — Bellu & Conversano (2020).
SSRN / DOI: https://doi.org/10.1016/j.frl.2019.01.007

Canonical Rules:
  - Default Universe: SPY, EFA, EEM, VNQ, DBC, GLD, TLT, IEF, LQD, HYG (10 assets)
  - Safe Asset: SHY (or cash equivalent)
  - Lookback: 6 months (126 trading days) for relative momentum
  - Gating: BF = max(0, min(1, (10 - n)/5))  [where n is count of assets with r_6 > 0]
  - Selection: Top K=5 assets with positive 6-month return
  - Weighting: Minimum Variance Optimization (MVO) over 20-day volatility and
               126-day daily covariance, scaled by (1 - Cash_Fraction)
"""
import numpy as np
import pandas as pd
from scipy.optimize import minimize

PAAA_UNIVERSE = ["SPY", "EFA", "EEM", "VNQ", "DBC", "GLD", "TLT", "IEF", "LQD", "HYG"]
PAAA_SAFE = "SHY"


def compute_paaa_weights(panel: pd.DataFrame, sig_d: pd.Timestamp,
                         universe: list | None = None,
                         safe_asset: str | None = None,
                         K: int = 5,
                         lookback_months: int = 6,
                         cov_lookback: int = 20) -> dict[str, float]:
    """Calculate PAAA weights at sig_d close (T+1 MOO honest)."""
    if universe is None:
        universe = PAAA_UNIVERSE
    if safe_asset is None:
        safe_asset = PAAA_SAFE

    monthly = panel.loc[:sig_d].resample("ME").last()
    daily = panel.loc[:sig_d]

    # Warmup check
    if len(monthly) < lookback_months + 1:
        return {safe_asset: 1.0}

    daily_lookback_days = lookback_months * 21
    daily_sub = daily.tail(daily_lookback_days + 1)
    if len(daily_sub) < daily_lookback_days:
        return {safe_asset: 1.0}

    avail = [t for t in universe if t in monthly.columns and t in daily.columns]
    if not avail:
        return {safe_asset: 1.0}

    # 1. Trailing 6-month returns
    returns = {}
    for t in avail:
        p_now = monthly[t].iloc[-1]
        p_prev = monthly[t].iloc[-(lookback_months + 1)]
        returns[t] = p_now / p_prev - 1.0 if p_prev > 0 else -1.0

    # PAA-style protection level (top-half threshold): BF = max(0, min(1, (N - n) / (N / 2)))
    n_positive = sum(1 for t in avail if returns.get(t, -1.0) > 0)
    N = len(avail)
    denom = N / 2.0
    cash_fraction = max(0.0, min(1.0, (N - n_positive) / denom)) if denom > 0 else 1.0

    # If 100% cash
    if cash_fraction >= 0.999:
        return {safe_asset: 1.0}

    # 2. Select top-K assets with positive momentum
    sorted_moms = sorted(returns.items(), key=lambda x: -x[1])
    picks = [t for t, r in sorted_moms[:K] if r > 0]
    n_picks = len(picks)

    if n_picks == 0:
        return {safe_asset: 1.0}

    # If only 1 pick, allocate all risky weight to it
    if n_picks == 1:
        risky_fraction = 1.0 - cash_fraction
        return {picks[0]: risky_fraction, safe_asset: cash_fraction}

    # 3. Minimum Variance Optimization (MVO) over cov_lookback
    rets_daily = daily[picks].pct_change().dropna(how="all").tail(cov_lookback)
    if len(rets_daily) < min(15, cov_lookback):
        # fallback to equal weight
        w_active = (1.0 - cash_fraction) / n_picks
        weights = {t: w_active for t in picks}
        weights[safe_asset] = weights.get(safe_asset, 0.0) + cash_fraction
        return weights

    # Covariance matrix (annualized)
    cov_mat = rets_daily.cov().values * 252
    
    # Quadratic solver: min w^T Σ w
    cons = [{"type": "eq", "fun": lambda w: w.sum() - 1.0}]
    bounds = [(0.0, 1.0)] * n_picks
    x0 = np.ones(n_picks) / n_picks
    
    res = minimize(lambda w: w @ cov_mat @ w, x0, method="SLSQP", bounds=bounds, constraints=cons)
    w_opt = res.x if res.success else x0

    # Scale optimal weights by the active fraction (1 - cash_fraction)
    risky_fraction = 1.0 - cash_fraction
    weights = {}
    for i, t in enumerate(picks):
        weights[t] = risky_fraction * float(w_opt[i])

    weights[safe_asset] = weights.get(safe_asset, 0.0) + cash_fraction
    return weights
