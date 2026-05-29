"""
Elastic Asset Allocation (EAA) — Keller & Butler (2014).
SSRN: https://ssrn.com/abstract=2543979

Canonical Rules:
  - Default Universe: SPY, EFA, EEM, VNQ, DBC, GLD, TLT, IEF, LQD, HYG (10 assets)
  - Safe Asset: BIL (falls back to SHV if BIL not in panel)
  - Lookback: 12 months (252 trading days)
  - Scoring: z_i = ((r_i^wR * (1 - c_i)^wC) / v_i^wV)^wS
    Default exponents: wR=1, wC=1, wV=0 (or 1 for defensive), wS=2
  - Gating: Cash Fraction = 1 - n/N (where n is count of assets with r_12 > 0)
  - Selection: Top K=3 assets by score (positive only)
  - Weighting: Score-proportional among active picks, scaled by (1 - Cash_Fraction)
"""
import numpy as np
import pandas as pd

EAA_UNIVERSE = ["SPY", "EFA", "EEM", "VNQ", "DBC", "GLD", "TLT", "IEF", "LQD", "HYG"]
EAA_SAFE = "BIL"


def compute_eaa_weights(panel: pd.DataFrame, sig_d: pd.Timestamp,
                        universe: list | None = None,
                        safe_asset: str | None = None,
                        K: int = 3,
                        lookback_months: int = 12,
                        wR: float = 1.0,
                        wC: float = 1.0,
                        wV: float = 1.0,  # defensive form default
                        wS: float = 2.0) -> dict[str, float]:
    """Calculate EAA weights at sig_d close (T+1 MOO honest)."""
    if universe is None:
        universe = EAA_UNIVERSE
    if safe_asset is None:
        safe_asset = EAA_SAFE

    monthly = panel.loc[:sig_d].resample("ME").last()
    daily = panel.loc[:sig_d]

    # Warmup check: need 13 monthly bars
    if len(monthly) < lookback_months + 1:
        # Fallback if safe_asset is BIL but not available
        actual_safe = safe_asset if safe_asset in panel.columns else "SHV"
        return {actual_safe: 1.0}

    # Verify safe asset exists, fallback if needed
    actual_safe = safe_asset
    if safe_asset not in panel.columns and safe_asset == "BIL" and "SHV" in panel.columns:
        actual_safe = "SHV"

    daily_lookback_days = lookback_months * 21
    daily_sub = daily.tail(daily_lookback_days + 1)
    if len(daily_sub) < daily_lookback_days:
        return {actual_safe: 1.0}

    avail = [t for t in universe if t in monthly.columns and t in daily.columns]
    if not avail:
        return {actual_safe: 1.0}

    # 1. Trailing 12-month returns
    returns = {}
    for t in avail:
        p_now = monthly[t].iloc[-1]
        p_prev = monthly[t].iloc[-(lookback_months + 1)]
        returns[t] = p_now / p_prev - 1.0 if p_prev > 0 else -1.0

    # Elastic cash fraction: 1 - n_pos / N
    n_positive = sum(1 for t in avail if returns.get(t, -1.0) > 0)
    N = len(avail)
    cash_fraction = 1.0 - n_positive / N if N > 0 else 1.0

    # If 100% cash
    if cash_fraction >= 0.999:
        return {actual_safe: 1.0}

    # 2. Compute components for scores
    vols = {}
    for t in avail:
        v = daily_sub[t].pct_change().std() * np.sqrt(252)
        vols[t] = v if pd.notna(v) and v > 1e-9 else 1.0

    ew_ret = daily_sub[avail].pct_change().mean(axis=1)
    corrs = {}
    for t in avail:
        c = daily_sub[t].pct_change().corr(ew_ret)
        corrs[t] = c if pd.notna(c) else 0.0

    # 3. Calculate EAA Scores
    scores = {}
    for t in avail:
        r = returns.get(t, -1.0)
        if r <= 0:
            continue
        v = vols.get(t, 1.0)
        c = corrs.get(t, 0.0)
        
        # score = ((r^wR * (1 - c)^wC) / v^wV)^wS
        num = (r ** wR) * ((1.0 - c) ** wC)
        den = v ** wV
        score_val = (num / den) ** wS if den > 0 else 0.0
        scores[t] = score_val

    # Select top-K assets
    sorted_picks = sorted(scores.items(), key=lambda x: -x[1])
    picks = [t for t, s in sorted_picks[:K] if s > 0]
    n_picks = len(picks)

    if n_picks == 0:
        return {actual_safe: 1.0}

    # 4. Weighting (score-proportional among active picks)
    total_active_score = sum(scores[t] for t in picks)
    if total_active_score < 1e-9:
        # fallback to equal weight if scores are zero
        w_active = (1.0 - cash_fraction) / n_picks
        weights = {t: w_active for t in picks}
    else:
        risky_fraction = 1.0 - cash_fraction
        weights = {}
        for t in picks:
            weights[t] = risky_fraction * (scores[t] / total_active_score)

    weights[actual_safe] = weights.get(actual_safe, 0.0) + cash_fraction
    return weights
