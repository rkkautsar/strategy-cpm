"""Portfolio-level vol cap: VIX-based latched binary 50%.

Trigger form:
  threshold = rolling 5y P95 of VIX close
  trigger if VIX > threshold

Once triggered:
  - Scale all sleeves by 0.5 (half to cash)
  - Hold scale until next monthly signal date (latched)
  - At signal date, re-evaluate: lift if VIX < threshold, else stay

Rationale:
  - VIX is externally calibrated; not tuned to own backtest data
  - Rolling 5y P95 adapts to the prevailing vol-of-vol regime
  - Industry-standard signal; VIX > 30 is widely recognized as panic
  - Threshold today ~30; current VIX ~16-18 in normal regimes

Empirical results (CLEAN 18.1y, post-cost):
  Variant                       Sh    MaxDD    r12mean-DD  r24mean-DD  trades/yr
  Baseline (no vol cap)         1.51  -12.00%  -7.28%      -8.31%      0
  VIX P95 rolling 5y (PROD)     1.53  -11.46%  -6.63%      -7.40%      1.8

  The VIX cap improves rolling 12mo / 24mo mean drawdown and the single
  worst-case MaxDD at a small CAGR cost (-1.1pp) and modest ops (~1.8
  trades/yr). Sharpe shift +0.02 is within the blend bootstrap CI
  [1.08, 1.94] width — treat as noise; the cap is for tail-DD compression,
  not Sharpe enhancement.

Form supported by practitioner literature:
  - VIX-percentile regime classification (standard practitioner approach)
  - Rolling 5y window matches institutional risk-management norms
  - Signal-confirmation + cooldown (Moreira-Muir 2017 bounded variant)
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd

VIX_PCT = 0.95             # 95th percentile of trailing VIX distribution
VIX_LB_YEARS = 5           # rolling 5-year window
VIX_LB_DAYS = VIX_LB_YEARS * 252  # ~1260 trading days
VOL_CAP_SCALE = 0.5        # binary scale-down (half to cash) when triggered

ROOT = Path(__file__).resolve().parent
VIX_CACHE = ROOT / "data" / "vix_cache.parquet"


def load_vix(start: pd.Timestamp | None = None,
              end: pd.Timestamp | None = None,
              refresh: bool = False) -> pd.Series:
    """Load VIX close series. Uses local parquet cache; refreshes via yfinance
    when stale or refresh=True. Returns daily close timeseries (UTC-naive)."""
    import yfinance as yf
    cached: pd.Series | None = None
    if VIX_CACHE.exists() and not refresh:
        try:
            df = pd.read_parquet(VIX_CACHE)
            cached = df["close"].copy()
            cached.index = pd.to_datetime(cached.index).tz_localize(None)
        except Exception:
            cached = None
    today = pd.Timestamp.utcnow().tz_localize(None).normalize()
    need_refresh = (
        refresh
        or cached is None
        or len(cached) == 0
        or (today - cached.index[-1]).days > 1
    )
    if need_refresh:
        fetch_start = "1990-01-01"
        fetch_end = today + pd.Timedelta(days=2)
        v = yf.Ticker("^VIX").history(start=fetch_start, end=fetch_end,
                                        auto_adjust=True)
        if v is None or v.empty:
            if cached is None:
                raise RuntimeError("VIX fetch failed and no cache available")
            v_series = cached
        else:
            v_series = v["Close"].copy()
            v_series.index = pd.to_datetime(v_series.index).tz_localize(None)
            v_series = v_series.dropna()
            VIX_CACHE.parent.mkdir(parents=True, exist_ok=True)
            v_series.to_frame(name="close").to_parquet(VIX_CACHE)
    else:
        v_series = cached  # type: ignore[assignment]
    if start is not None:
        v_series = v_series.loc[v_series.index >= start]
    if end is not None:
        v_series = v_series.loc[v_series.index <= end]
    return v_series


def _vix_threshold_series(vix: pd.Series,
                            pct: float = VIX_PCT,
                            lb_days: int = VIX_LB_DAYS) -> pd.Series:
    """Rolling P95 of VIX close over lb_days, lagged 1d to avoid look-ahead."""
    return vix.rolling(lb_days, min_periods=lb_days).quantile(pct).shift(1)


def compute_latched_scale(blend_returns: pd.Series,
                           signal_dates: list[pd.Timestamp],
                           vix: pd.Series | None = None,
                           pct: float = VIX_PCT,
                           lb_days: int = VIX_LB_DAYS,
                           latched_scale: float = VOL_CAP_SCALE,
                           ) -> tuple[pd.Series, list[dict]]:
    """Compute daily vol-cap scale: latched binary 50% on VIX > rolling P95.

    blend_returns: only used for index alignment + as the natural ops boundary.
    vix: VIX close series (loaded automatically if None).
    """
    if vix is None:
        vix = load_vix(start=blend_returns.index[0] - pd.Timedelta(days=365 * VIX_LB_YEARS + 60),
                        end=blend_returns.index[-1] + pd.Timedelta(days=2))
    vix_aligned = vix.reindex(blend_returns.index).ffill()
    threshold_series = _vix_threshold_series(vix_aligned, pct=pct, lb_days=lb_days)
    triggered_today = (vix_aligned.shift(1) > threshold_series)

    scale = pd.Series(1.0, index=blend_returns.index)
    events: list[dict] = []
    current = 1.0
    sig_sorted = sorted(signal_dates)
    end = blend_returns.index[-1]

    for i in range(len(sig_sorted)):
        sd = sig_sorted[i]
        nxt = sig_sorted[i + 1] if i + 1 < len(sig_sorted) else end
        trig_sd = bool(triggered_today.loc[:sd].iloc[-1]) if len(triggered_today.loc[:sd]) else False
        vix_at_sd = float(vix_aligned.loc[:sd].iloc[-1]) if len(vix_aligned.loc[:sd]) else float("nan")
        thr_at_sd = float(threshold_series.loc[:sd].iloc[-1]) if len(threshold_series.loc[:sd]) else float("nan")
        if trig_sd:
            if current >= 1.0:
                events.append(dict(date=sd, action="trigger@signal", scale=latched_scale,
                                    vix=vix_at_sd, threshold=thr_at_sd))
            current = latched_scale
        else:
            if current < 1.0:
                events.append(dict(date=sd, action="lift@signal", scale=1.0,
                                    vix=vix_at_sd, threshold=thr_at_sd))
            current = 1.0

        in_period = blend_returns.index[(blend_returns.index > sd)
                                         & (blend_returns.index <= nxt)]
        for day in in_period:
            trig = bool(triggered_today.loc[day]) if day in triggered_today.index else False
            if current >= 1.0 and trig:
                events.append(dict(date=day, action="trigger@daily", scale=latched_scale,
                                    vix=float(vix_aligned.loc[day]) if day in vix_aligned.index else float("nan"),
                                    threshold=float(threshold_series.loc[day]) if day in threshold_series.index else float("nan")))
                current = latched_scale
            scale.loc[day] = current

    return scale, events


def apply_vol_cap(blend_returns: pd.Series,
                   signal_dates: list[pd.Timestamp],
                   **kwargs) -> pd.Series:
    """Convenience: return scaled blend returns directly."""
    scale, _ = compute_latched_scale(blend_returns, signal_dates, **kwargs)
    return scale * blend_returns


def current_threshold(vix: pd.Series | None = None,
                       pct: float = VIX_PCT,
                       lb_days: int = VIX_LB_DAYS) -> dict:
    """Return current VIX, threshold, and triggered state."""
    if vix is None:
        vix = load_vix()
    vix = vix.dropna()
    if len(vix) < lb_days:
        return dict(vix=float(vix.iloc[-1]) if len(vix) else float("nan"),
                    threshold=float("nan"), triggered=False,
                    pct=pct, lb_days=lb_days)
    thr = float(vix.iloc[:-1].tail(lb_days).quantile(pct))
    last_vix = float(vix.iloc[-1])
    return dict(vix=last_vix, threshold=thr, triggered=(last_vix > thr),
                pct=pct, lb_days=lb_days, asof=str(vix.index[-1].date()))


def current_scale_state(blend_returns: pd.Series,
                         signal_dates: list[pd.Timestamp],
                         **kwargs) -> dict:
    scale, events = compute_latched_scale(blend_returns, signal_dates, **kwargs)
    last_scale = float(scale.iloc[-1])
    breakdown = current_threshold()
    return dict(
        scale=last_scale,
        regime="CAP_ENGAGED" if last_scale < 1.0 else "NORMAL",
        vix=breakdown["vix"],
        threshold=breakdown["threshold"],
        pct=breakdown["pct"],
        lb_years=VIX_LB_YEARS,
        last_event=events[-1] if events else None,
        n_events_total=len(events),
    )
