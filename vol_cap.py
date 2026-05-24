"""Portfolio-level vol cap: latched binary 50% trigger.

When blend trailing 21d realized vol > VOL_CAP_TARGET (22%):
  - Scale all sleeves by 0.5 (half to cash)
  - Hold scale until next monthly signal date (latched)
  - At signal date, re-evaluate: lift scale back to 1.0 if vol normalized

Rationale (see /tmp/vol_cap_*.py for empirical justification):
  - Best Sharpe across in-sample halves vs MM continuous, VIX-percentile,
    smooth bounded alternatives (latched 1.554 vs MM 1.535 vs VIX 1.490
    on CLEAN 18.1y).
  - Tail compression Max realized vol 31.5% -> 23.4% on CLEAN, 33.1% -> 24.9%
    on 30y extended including dotcom.
  - ~0.9 trades/yr (basically zero ops overhead at zero-commission brokers).
  - 22% threshold robust across out-of-window splits (first half +0.042 Sh,
    second half +0.032 Sh); LB=21d robust vs 10d/42d/63d.

Reference: Moreira & Muir 2017 "Volatility-Managed Portfolios" JoF; this
form is a practitioner-engineered latched binary variant of that approach.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

VOL_CAP_TARGET = 0.22  # 22% annualized realized vol trigger
VOL_CAP_LOOKBACK = 21  # trailing-vol window in trading days
VOL_CAP_SCALE = 0.5    # binary scale-down (half to cash) when triggered


def compute_latched_scale(blend_returns: pd.Series,
                           signal_dates: list[pd.Timestamp],
                           target: float = VOL_CAP_TARGET,
                           lookback: int = VOL_CAP_LOOKBACK,
                           latched_scale: float = VOL_CAP_SCALE,
                           ) -> tuple[pd.Series, list[dict]]:
    """Compute daily vol-cap scale series with monthly-latched binary trigger.

    Parameters
    ----------
    blend_returns : pd.Series
        Daily returns of the unscaled blend (CPM*0.60 + BULL*0.20 + NDX*0.20).
    signal_dates : list[pd.Timestamp]
        Monthly signal dates where the scale can be lifted back to 1.0.
    target : float
        Realized-vol trigger threshold (annualized, e.g. 0.22 = 22%).
    lookback : int
        Trailing-vol window (trading days, e.g. 21).
    latched_scale : float
        Scale to apply when triggered (e.g. 0.5 = half).

    Returns
    -------
    scale : pd.Series
        Daily scale series (1.0 or `latched_scale`).
    events : list[dict]
        Log of each trigger / lift event for audit.
    """
    rv = blend_returns.rolling(lookback).std() * np.sqrt(252)
    rv_lag = rv.shift(1)
    scale = pd.Series(1.0, index=blend_returns.index)
    events: list[dict] = []
    current = 1.0
    sig_sorted = sorted(signal_dates)
    end = blend_returns.index[-1]

    for i in range(len(sig_sorted)):
        sd = sig_sorted[i]
        nxt = sig_sorted[i + 1] if i + 1 < len(sig_sorted) else end
        # At signal date: reset (lift or maintain trigger based on current vol)
        rv_at_sd = (rv_lag.loc[:sd].iloc[-1]
                     if len(rv_lag.loc[:sd]) else float("nan"))
        if pd.notna(rv_at_sd) and rv_at_sd > target:
            if current >= 1.0:
                events.append(dict(
                    date=sd, action="trigger@signal", scale=latched_scale,
                    realized_vol=float(rv_at_sd)))
            current = latched_scale
        else:
            if current < 1.0:
                events.append(dict(
                    date=sd, action="lift@signal", scale=1.0,
                    realized_vol=float(rv_at_sd) if pd.notna(rv_at_sd) else None))
            current = 1.0
        # Walk forward through the month
        in_period = blend_returns.index[(blend_returns.index > sd)
                                         & (blend_returns.index <= nxt)]
        for day in in_period:
            rv_today = (rv_lag.loc[day] if day in rv_lag.index else float("nan"))
            if current >= 1.0 and pd.notna(rv_today) and rv_today > target:
                events.append(dict(
                    date=day, action="trigger@daily", scale=latched_scale,
                    realized_vol=float(rv_today)))
                current = latched_scale
            scale.loc[day] = current

    return scale, events


def apply_vol_cap(blend_returns: pd.Series,
                   signal_dates: list[pd.Timestamp],
                   **kwargs) -> pd.Series:
    """Convenience: return the scaled blend returns directly."""
    scale, _ = compute_latched_scale(blend_returns, signal_dates, **kwargs)
    return scale * blend_returns


def current_scale_state(blend_returns: pd.Series,
                         signal_dates: list[pd.Timestamp],
                         **kwargs) -> dict:
    """Returns the current vol-cap state for the live dashboard.

    Output keys: scale (float), regime ("NORMAL"|"CAP_ENGAGED"),
    realized_vol (current value), trigger_threshold, last_event (dict|None).
    """
    scale, events = compute_latched_scale(blend_returns, signal_dates, **kwargs)
    last_scale = float(scale.iloc[-1])
    rv = blend_returns.rolling(kwargs.get("lookback", VOL_CAP_LOOKBACK)).std() * np.sqrt(252)
    last_rv = float(rv.iloc[-1]) if len(rv) and pd.notna(rv.iloc[-1]) else None
    return dict(
        scale=last_scale,
        regime="CAP_ENGAGED" if last_scale < 1.0 else "NORMAL",
        realized_vol_21d=last_rv,
        trigger_threshold=kwargs.get("target", VOL_CAP_TARGET),
        last_event=events[-1] if events else None,
        n_events_total=len(events),
    )
