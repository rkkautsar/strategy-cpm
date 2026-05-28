"""LQD/IEF credit-spread intramonth circuit breaker for the NDX sleeve."""
from __future__ import annotations

import pandas as pd

# ============================================================================
# LQD/IEF credit-spread intramonth circuit (NDX sleeve).
#
# Rule: latch defensive when LQD/IEF ratio < its rolling 50-day EMA.
#   LQD = iShares iBoxx $ Investment Grade Corporate Bonds (duration ~8y)
#   IEF = iShares 7-10 Year Treasury Bond ETF (duration ~7y)
# Both have similar duration so the ratio cancels rate-direction moves,
# leaving an approximate credit-spread proxy. Falling ratio = IG corporates
# underperforming Treasuries = credit-spread widening = risk-off.
#
# Window: 50-day EMA. Reset: scale = 1.0 at each monthly signal date.
# Execution: t+1 MOO honest (scale[t] set BEFORE today's trigger evaluation).
#
# Method lineage:
#   - LQD/IEF as credit-spread proxy: duration-cancelled ratio is standard
#     macro practitioner research (HYG/IEF and LQD/IEF spread variants).
#   - EMA50 crossover: practitioner exponential-moving-average filter family
#     (Faber 2007 SSRN TAA uses 10mo SMA on equity; EMA is the same family
#     with recency-weighted smoothing).
LQD_IEF_EMA_SPAN = 50    # EMA span for LQD/IEF ratio (trading days)
DEFENSIVE_SCALE = 0.0    # scale when latched defensive (0.0 = full cash)


def compute_lqd_ief_circuit_scale(lqd_price: pd.Series,
                                     ief_price: pd.Series,
                                     sleeve_index: pd.DatetimeIndex,
                                     sig_dates: list,
                                     ema_span: int = LQD_IEF_EMA_SPAN,
                                     recovery_scale: float = DEFENSIVE_SCALE,
                                     ) -> pd.Series:
    """Daily LQD/IEF < EMA intramonth circuit for a single sleeve.

    Latches defensive when ratio = LQD / IEF < ratio.ewm(span=EMA_SPAN).mean().
    Releases to 1.0 at each monthly signal date.

    Args:
        lqd_price: daily close of LQD ETF
        ief_price: daily close of IEF ETF
        sleeve_index: daily index over which to produce scale
        sig_dates: monthly signal dates where the latch resets
        ema_span: EMA span in trading days (default 50)
        recovery_scale: scale when latched defensive (default 0.0)

    Returns:
        scale: pd.Series of daily scale [0, 1] indexed by sleeve_index
    """
    if len(sleeve_index) == 0:
        return pd.Series(dtype=float)
    lqd = lqd_price.reindex(sleeve_index).ffill()
    ief = ief_price.reindex(sleeve_index).ffill()
    ratio = lqd / ief
    ema = ratio.ewm(span=ema_span, adjust=False).mean()
    trigger = (ratio < ema) & ratio.notna() & ema.notna()
    scale = pd.Series(1.0, index=sleeve_index)
    sig_set = set(sig_dates)
    state = 1.0
    # T+1 MOO honest execution: set scale[t] FIRST, then check trigger to
    # update state for t+1. Trigger evaluated at day-t close fires defensive
    # starting day t+1.
    for i, day in enumerate(sleeve_index):
        if day in sig_set:
            state = 1.0
        scale.iloc[i] = state
        if bool(trigger.iloc[i]):
            state = recovery_scale
    return scale


def current_circuit_state(lqd_price: pd.Series,
                            ief_price: pd.Series,
                            ema_span: int = LQD_IEF_EMA_SPAN) -> dict:
    """Get current LQD/IEF circuit state as of latest available data.

    Returns dict with: ratio, ema, distance_pct, triggered, regime,
    as_of_date.
    """
    common = lqd_price.dropna().index.intersection(ief_price.dropna().index)
    if len(common) < ema_span:
        return dict(triggered=False, regime="NO_DATA", as_of_date=None)
    lqd = lqd_price.reindex(common).ffill()
    ief = ief_price.reindex(common).ffill()
    ratio = lqd / ief
    ema = ratio.ewm(span=ema_span, adjust=False).mean()
    last_ratio = float(ratio.iloc[-1])
    last_ema = float(ema.iloc[-1])
    distance_pct = (last_ratio / last_ema - 1.0) * 100.0
    triggered = last_ratio < last_ema
    return dict(
        ratio=last_ratio,
        ema=last_ema,
        distance_pct=distance_pct,
        triggered=triggered,
        ema_span=ema_span,
        regime="CIRCUIT_TRIGGERED" if triggered else "NORMAL",
        as_of_date=common[-1],
    )
