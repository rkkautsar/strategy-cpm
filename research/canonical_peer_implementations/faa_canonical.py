"""
Flexible Asset Allocation (FAA) — Keller & van Putten (2012).
SSRN: https://ssrn.com/abstract=2193735

Canonical Rules:
  - Default Universe: SPY, VEA, VWO, SHY, LQD, IBB, VNQ (7 assets)
  - Safe Asset: SHY (or cash equivalent)
  - Lookback: 4 months (84 trading days)
  - Scoring: Rank Return (desc) + 0.5 * Rank Vol (asc) + 0.5 * Rank Corr (asc)
  - Gating: Cash Fraction = n_negative / N (fraction of assets with mom <= 0)
  - Selection: Top K=3 assets with positive momentum (Score-selected)
  - Weighting: Equal-weighted active, scaled by (1 - Cash_Fraction)
"""
import numpy as np
import pandas as pd

FAA_UNIVERSE = ["SPY", "VEA", "VWO", "SHY", "LQD", "IBB", "VNQ"]
FAA_SAFE = "SHY"


def compute_faa_weights(panel: pd.DataFrame, sig_d: pd.Timestamp,
                        universe: list | None = None,
                        safe_asset: str | None = None,
                        K: int = 3,
                        lookback_months: int = 4) -> dict[str, float]:
    """Calculate FAA weights at sig_d close (T+1 MOO honest)."""
    if universe is None:
        universe = FAA_UNIVERSE
    if safe_asset is None:
        safe_asset = FAA_SAFE

    # resample to monthly and slice up to sig_d
    monthly = panel.loc[:sig_d].resample("ME").last()
    daily = panel.loc[:sig_d]

    # Warmup check: need lookback_months + 1 monthly bars
    if len(monthly) < lookback_months + 1:
        return {safe_asset: 1.0}

    # 1. Trailing 4-month total returns
    m_start = monthly.index[-(lookback_months + 1)]
    m_end = monthly.index[-1]
    
    # Map lookback to daily trading days (approx 21 days/month)
    daily_lookback_days = lookback_months * 21
    daily_sub = daily.tail(daily_lookback_days + 1)
    if len(daily_sub) < daily_lookback_days:
        return {safe_asset: 1.0}

    avail = [t for t in universe if t in monthly.columns and t in daily.columns]
    if not avail:
        return {safe_asset: 1.0}

    # 2. Compute ranking factors
    # A. 4-month return (relative momentum)
    returns = {}
    for t in avail:
        p_now = monthly[t].iloc[-1]
        p_prev = monthly[t].iloc[-(lookback_months + 1)]
        returns[t] = p_now / p_prev - 1.0 if p_prev > 0 else -1.0

    # Count negative absolute momentum assets for cash fraction
    n_negative = sum(1 for t in avail if returns.get(t, -1.0) <= 0)
    cash_fraction = n_negative / len(avail) if avail else 1.0

    # B. 4-month daily volatility
    vols = {}
    for t in avail:
        v = daily_sub[t].pct_change().std() * np.sqrt(252)
        vols[t] = v if pd.notna(v) else 999.0

    # C. 4-month daily correlation to equal-weighted basket
    ew_ret = daily_sub[avail].pct_change().mean(axis=1)
    corrs = {}
    for t in avail:
        c = daily_sub[t].pct_change().corr(ew_ret)
        corrs[t] = c if pd.notna(c) else 0.0

    # 3. Ordinal ranking (1 is best)
    r_series = pd.Series(returns)
    v_series = pd.Series(vols)
    c_series = pd.Series(corrs)

    # Return: rank descending (highest return = rank 1)
    r_rank = r_series.rank(ascending=False, method="min")
    # Volatility: rank ascending (lowest vol = rank 1)
    v_rank = v_series.rank(ascending=True, method="min")
    # Correlation: rank ascending (lowest corr = rank 1)
    c_rank = c_series.rank(ascending=True, method="min")

    # Composite Score: R_rank + 0.5 * V_rank + 0.5 * C_rank
    score = r_rank + 0.5 * v_rank + 0.5 * c_rank

    # Filter out assets with negative 4-month returns (absolute momentum filter)
    active_score = score[score.index.map(lambda t: returns.get(t, -1.0) > 0)]
    
    # Select top-K assets
    picks = active_score.sort_values(ascending=True).index[:K].tolist()
    n_picks = len(picks)

    # 4. Portfolio Weighting
    if n_picks == 0 or cash_fraction >= 0.999:
        return {safe_asset: 1.0}

    # Split the active risky fraction (1 - cash_fraction) equally among picks
    risky_fraction = 1.0 - cash_fraction
    w_active = risky_fraction / n_picks
    weights = {t: w_active for t in picks}
    
    # Remainder goes to safe asset (cash)
    weights[safe_asset] = weights.get(safe_asset, 0.0) + cash_fraction
    return weights
