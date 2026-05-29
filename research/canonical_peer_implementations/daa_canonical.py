"""
Defensive Asset Allocation (DAA) — Keller & Keuning (2018).
SSRN: https://ssrn.com/abstract=3212862

Canonical Rules:
  - Default Universe: SPY, IWM, QQQ, VGK, EWJ, EEM, VNQ, DBC, GLD, TLT, HYG, LQD (12 assets)
  - Canary Universe: VWO, BND (or AGG)
  - Safe Asset: IEF (or SHV)
  - Momentum Score (13612W): 12*r1 + 4*r3 + 2*r6 + r12
  - Gating: Cash Fraction = 0% (0 bad), 50% (1 bad), 100% (2 bad)
  - Selection: Top K=6 assets by 13612W score (positive only)
  - Weighting: Equal-weighted active, scaled by (1 - Cash_Fraction)
"""
import numpy as np
import pandas as pd

DAA_UNIVERSE = ["SPY", "IWM", "QQQ", "VGK", "EWJ", "EEM", "VNQ", "DBC", "GLD", "TLT", "HYG", "LQD"]
DAA_CANARY = ["VWO", "AGG"]  # AGG proxies BND
DAA_SAFE = "IEF"


def mom_13612W(monthly_series: pd.Series) -> float:
    """Calculate Keller's 13612W score from monthly series."""
    p = monthly_series.dropna()
    if len(p) < 13:
        return np.nan
    last = p.iloc[-1]
    r1  = last / p.iloc[-2] - 1.0
    r3  = last / p.iloc[-4] - 1.0
    r6  = last / p.iloc[-7] - 1.0
    r12 = last / p.iloc[-13] - 1.0
    return 12.0 * r1 + 4.0 * r3 + 2.0 * r6 + r12


def compute_daa_weights(panel: pd.DataFrame, sig_d: pd.Timestamp,
                        universe: list | None = None,
                        canary_universe: list | None = None,
                        safe_asset: str | None = None,
                        K: int = 6) -> dict[str, float]:
    """Calculate DAA weights at sig_d close (T+1 MOO honest)."""
    if universe is None:
        universe = DAA_UNIVERSE
    if canary_universe is None:
        canary_universe = DAA_CANARY
    if safe_asset is None:
        safe_asset = DAA_SAFE

    monthly = panel.loc[:sig_d].resample("ME").last()

    # Warmup check
    if len(monthly) < 13:
        return {safe_asset: 1.0}

    # 1. Evaluate Canary Universe for cash fraction
    n_bad_canaries = 0
    for c in canary_universe:
        if c not in monthly.columns:
            continue
        score = mom_13612W(monthly[c])
        if pd.isna(score) or score <= 0:
            n_bad_canaries += 1

    # Tiered cash fraction: 0 bad -> 0% cash, 1 bad -> 50% cash, 2 bad -> 100% cash
    if n_bad_canaries == 0:
        cash_fraction = 0.0
    elif n_bad_canaries == 1:
        cash_fraction = 0.5
    else:
        cash_fraction = 1.0

    if cash_fraction >= 0.999:
        return {safe_asset: 1.0}

    # 2. Score offensive universe
    avail = [t for t in universe if t in monthly.columns]
    scores = {}
    for t in avail:
        score = mom_13612W(monthly[t])
        if pd.isna(score) or score <= 0:
            continue
        scores[t] = score

    # Select top-K assets
    sorted_picks = sorted(scores.items(), key=lambda x: -x[1])
    picks = [t for t, s in sorted_picks[:K] if s > 0]
    n_picks = len(picks)

    if n_picks == 0:
        return {safe_asset: 1.0}

    # 3. Weighting (equal-weighted active, scaled by active fraction)
    risky_fraction = 1.0 - cash_fraction
    w_active = risky_fraction / n_picks
    weights = {t: w_active for t in picks}
    
    weights[safe_asset] = weights.get(safe_asset, 0.0) + cash_fraction
    return weights
