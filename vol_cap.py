"""Portfolio-level vol cap: latched binary 50% with hybrid threshold.

Threshold form:
  trigger if  realized_21d_vol > max(rolling_mean_252d(realized_21d_vol), 22%)

When triggered:
  - Scale all sleeves by 0.5 (half to cash)
  - Hold scale until next monthly signal date (latched)
  - At signal date, re-evaluate: lift scale back to 1.0 if threshold not breached

Rationale:
  - The 22% absolute floor matches the simpler fixed-22% empirical optimum in
    tested data (CLEAN 18.1y Sh 1.554, identical to fixed-22%).
  - The relative `> long_avg` arm activates ONLY if the baseline vol regime
    drifts above 22% (e.g. sustained 1970s-style high-vol regime). In that
    case the threshold adapts upward, avoiding over-triggering in genuinely
    high-vol baselines while still catching real spikes above the floor.
  - In all tested data (CLEAN 18.1y, 30y extended) the long-avg threshold
    rarely exceeded 22%, so R6 collapsed to fixed-22% in-sample. Future-proof
    against regime shifts at zero current cost.

Empirical comparison (CLEAN 18.1y):
  - Baseline (no cap):                Sh 1.515 / Max-rv 31.5%
  - Fixed 22% (prior):                Sh 1.554 / Max-rv 23.4% / 0.9 trades/yr
  - R6 max(long252, 22%):             Sh 1.554 / Max-rv 23.4% / 0.9 trades/yr
  - Pure adaptive (short > long):     Sh 1.399 (worse - triggers too often)
  - Moreira-Muir continuous @ 15%:    Sh 1.535 (worse) / 6 trades/yr

Form supported by practitioner literature:
  - Exposure floor (StockAlpha-style minimum-exposure rule)
  - Signal confirmation + cooldown (Moreira-Muir 2017 bounded variant)
  - Regime-bucket threshold (VIX-percentile / VRP-harvesting practitioners)
  - Whipsaw control via monthly latch (Lancaster RRW change-point detection)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

VOL_CAP_ABS_FLOOR = 0.22     # absolute trigger floor (matches in-sample optimum)
VOL_CAP_LB_SHORT = 21         # short trailing-vol window (trading days)
VOL_CAP_LB_LONG = 252         # long-avg baseline window (~1y)
VOL_CAP_SCALE = 0.5           # binary scale-down (half to cash) when triggered


def _threshold_at(rv_lag_history: pd.Series,
                   abs_floor: float = VOL_CAP_ABS_FLOOR,
                   long_lb: int = VOL_CAP_LB_LONG) -> float:
    """Threshold = max(rolling_mean_LB_long of short-vol series, absolute_floor)."""
    if len(rv_lag_history) < long_lb:
        return float(abs_floor)
    long_avg = float(rv_lag_history.tail(long_lb).mean())
    if not np.isfinite(long_avg):
        return float(abs_floor)
    return max(long_avg, abs_floor)


def compute_latched_scale(blend_returns: pd.Series,
                           signal_dates: list[pd.Timestamp],
                           abs_floor: float = VOL_CAP_ABS_FLOOR,
                           lb_short: int = VOL_CAP_LB_SHORT,
                           lb_long: int = VOL_CAP_LB_LONG,
                           latched_scale: float = VOL_CAP_SCALE,
                           ) -> tuple[pd.Series, list[dict]]:
    """Compute daily vol-cap scale series with monthly-latched binary trigger.

    Trigger: realized 21d vol > max(rolling mean 252d of realized 21d vol, abs_floor).
    Once triggered, hold scale = latched_scale until next signal date.
    """
    rv = blend_returns.rolling(lb_short).std() * np.sqrt(252)
    rv_lag = rv.shift(1)
    scale = pd.Series(1.0, index=blend_returns.index)
    events: list[dict] = []
    current = 1.0
    sig_sorted = sorted(signal_dates)
    end = blend_returns.index[-1]

    for i in range(len(sig_sorted)):
        sd = sig_sorted[i]
        nxt = sig_sorted[i + 1] if i + 1 < len(sig_sorted) else end
        rv_history = rv_lag.loc[:sd]
        rv_at_sd = float(rv_history.iloc[-1]) if len(rv_history) and pd.notna(rv_history.iloc[-1]) else float("nan")
        thresh_at_sd = _threshold_at(rv_history, abs_floor, lb_long)
        triggered_at_sd = pd.notna(rv_at_sd) and rv_at_sd > thresh_at_sd
        if triggered_at_sd:
            if current >= 1.0:
                events.append(dict(
                    date=sd, action="trigger@signal", scale=latched_scale,
                    realized_vol=rv_at_sd, threshold=thresh_at_sd))
            current = latched_scale
        else:
            if current < 1.0:
                events.append(dict(
                    date=sd, action="lift@signal", scale=1.0,
                    realized_vol=rv_at_sd, threshold=thresh_at_sd))
            current = 1.0

        in_period = blend_returns.index[(blend_returns.index > sd)
                                         & (blend_returns.index <= nxt)]
        for day in in_period:
            rv_today = rv_lag.loc[day] if day in rv_lag.index else float("nan")
            rv_history_today = rv_lag.loc[:day]
            thresh_today = _threshold_at(rv_history_today, abs_floor, lb_long)
            if current >= 1.0 and pd.notna(rv_today) and rv_today > thresh_today:
                events.append(dict(
                    date=day, action="trigger@daily", scale=latched_scale,
                    realized_vol=float(rv_today), threshold=thresh_today))
                current = latched_scale
            scale.loc[day] = current

    return scale, events


def apply_vol_cap(blend_returns: pd.Series,
                   signal_dates: list[pd.Timestamp],
                   **kwargs) -> pd.Series:
    """Convenience: return scaled blend returns directly."""
    scale, _ = compute_latched_scale(blend_returns, signal_dates, **kwargs)
    return scale * blend_returns


def current_threshold(blend_returns: pd.Series,
                       abs_floor: float = VOL_CAP_ABS_FLOOR,
                       lb_short: int = VOL_CAP_LB_SHORT,
                       lb_long: int = VOL_CAP_LB_LONG) -> dict:
    """Return current threshold breakdown: realized 21d vol, long avg, threshold."""
    rv = blend_returns.rolling(lb_short).std() * np.sqrt(252)
    rv_last = float(rv.iloc[-1]) if len(rv) and pd.notna(rv.iloc[-1]) else float("nan")
    long_avg = (float(rv.dropna().tail(lb_long).mean())
                 if rv.dropna().shape[0] >= lb_long else float("nan"))
    thresh = max(long_avg if pd.notna(long_avg) else 0.0, abs_floor)
    return dict(
        realized_vol_21d=rv_last,
        long_avg_252d=long_avg,
        threshold=thresh,
        abs_floor=abs_floor,
    )


def current_scale_state(blend_returns: pd.Series,
                         signal_dates: list[pd.Timestamp],
                         **kwargs) -> dict:
    """Current vol-cap state for the live dashboard / vol_check.py."""
    scale, events = compute_latched_scale(blend_returns, signal_dates, **kwargs)
    last_scale = float(scale.iloc[-1])
    breakdown = current_threshold(
        blend_returns,
        abs_floor=kwargs.get("abs_floor", VOL_CAP_ABS_FLOOR),
        lb_short=kwargs.get("lb_short", VOL_CAP_LB_SHORT),
        lb_long=kwargs.get("lb_long", VOL_CAP_LB_LONG),
    )
    return dict(
        scale=last_scale,
        regime="CAP_ENGAGED" if last_scale < 1.0 else "NORMAL",
        realized_vol_21d=breakdown["realized_vol_21d"],
        long_avg_252d=breakdown["long_avg_252d"],
        threshold=breakdown["threshold"],
        abs_floor=breakdown["abs_floor"],
        last_event=events[-1] if events else None,
        n_events_total=len(events),
    )
