"""Canonical CPM research harness (mooex, both-252, 10 bps/side).

Conventions
-----------
- Execution: mooex T+1 MOO exact via `exec_lag_moo_validation_2026_05_30._segment_returns_conv`.
  Rebalance day return = old basket overnight close[T]->open[t+1] plus new basket
  intraday open[t+1]->close[t+1], compounded.
- Costs: 10 bps per side at each rebalance apply date.
- Windows:
  - clean: 2008-05-30..end
  - ext:   1999-03-10..end
- Data: `cpm_live.load_panel` plus open-cache OHLC from
  `exec_lag_moo_validation_2026_05_30.load_open_close()`.
- Guard: `cpm_live.CORR_LOOKBACK_DAYS` must be 252 (both-252 baseline).

This module wraps existing engine/math. It does not reimplement backtest logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Callable

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import cpm_live
from cpm_live import (
    load_panel,
    perf_metrics,
    compute_target_weights,
    COST_BPS_PER_SIDE,
    DEFAULT_CASH,
)

try:
    from research import exec_lag_moo_validation_2026_05_30 as _engine
except ImportError:  # pragma: no cover - script-style fallback
    import exec_lag_moo_validation_2026_05_30 as _engine


CLEAN_START = pd.Timestamp("2008-05-30")
EXT_START = pd.Timestamp("1999-03-10")
DEFAULT_END = pd.Timestamp("2026-05-22")
CONVENTION = "mooex"

ANCHOR = {
    "Sharpe": 1.2622,
    "MaxDD": -0.1135,
    "Calmar": 1.2196,
}
ANCHOR_TOL = {
    "Sharpe": 5e-4,
    "MaxDD": 5e-4,
    "Calmar": 5e-4,
}


@dataclass(frozen=True)
class HarnessData:
    """Loaded canonical inputs for research runs."""

    panel: pd.DataFrame
    open_df: pd.DataFrame
    close_yf: pd.DataFrame
    intraday: pd.DataFrame
    overnight: pd.DataFrame
    cash: pd.Series
    clean_start: pd.Timestamp
    ext_start: pd.Timestamp
    end: pd.Timestamp


def _assert_both_252() -> None:
    if cpm_live.CORR_LOOKBACK_DAYS != 252:
        raise ValueError(
            "Harness requires both-252 baseline: "
            f"cpm_live.CORR_LOOKBACK_DAYS={cpm_live.CORR_LOOKBACK_DAYS}, expected 252."
        )


def _as_weights(raw: object) -> dict[str, float]:
    if isinstance(raw, tuple):
        raw = raw[0] if raw else {}
    if not isinstance(raw, dict):
        raise TypeError(
            "weight_fn must return dict[str, float] or tuple with dict at position 0."
        )
    out = {}
    for k, v in raw.items():
        if pd.isna(v):
            continue
        fv = float(v)
        if abs(fv) <= 0:
            continue
        out[str(k)] = fv
    return out


def _call_weight_fn(
    weight_fn: Callable[..., object], panel: pd.DataFrame, sig_d: pd.Timestamp
) -> dict[str, float]:
    try:
        raw = weight_fn(panel, sig_d)
    except TypeError:
        raw = weight_fn(sig_d)
    return _as_weights(raw)


def load_data(
    *,
    end: pd.Timestamp | str = DEFAULT_END,
    clean_start: pd.Timestamp | str = CLEAN_START,
    ext_start: pd.Timestamp | str = EXT_START,
) -> HarnessData:
    """Load canonical panel + open cache with standard clean/ext windows.

    Returns `HarnessData` including panel prices, yfinance open/close cache,
    derived intraday and overnight legs, cash series, and window bounds.
    """
    _assert_both_252()

    end_ts = pd.Timestamp(end)
    clean_ts = pd.Timestamp(clean_start)
    ext_ts = pd.Timestamp(ext_start)

    panel = load_panel(start=ext_ts, end=end_ts)
    if panel.empty:
        raise ValueError("load_panel returned empty panel.")
    end_ts = min(end_ts, panel.index[-1])
    panel = panel.loc[panel.index <= end_ts].copy()

    open_df, close_yf = _engine.load_open_close()
    intraday = (close_yf / open_df - 1.0).reindex(panel.index)
    overnight = (open_df / close_yf.shift(1) - 1.0).reindex(panel.index)
    cash = panel[DEFAULT_CASH].ffill().pct_change()

    return HarnessData(
        panel=panel,
        open_df=open_df,
        close_yf=close_yf,
        intraday=intraday,
        overnight=overnight,
        cash=cash,
        clean_start=clean_ts,
        ext_start=ext_ts,
        end=end_ts,
    )


def run_strategy(
    weight_fn: Callable[..., object], *, window: str = "clean", data: HarnessData | None = None
) -> pd.Series:
    """Run strategy through canonical mooex engine.

    Parameters
    ----------
    weight_fn:
        Callable with signature `(panel, sig_d) -> dict` (or tuple with dict at [0]).
        A one-arg form `(sig_d) -> dict` is also accepted.
    window:
        "clean" (2008-05-30..) or "ext" (1999-03-10..).
    data:
        Optional preloaded `HarnessData` from `load_data()`.

    Returns
    -------
    pandas.Series
        Daily net returns after 10 bps/side turnover costs.
    """
    d = data or load_data()
    daily_ret = d.panel.ffill().pct_change()

    wf = lambda sig_d: _call_weight_fn(weight_fn, d.panel, sig_d)
    series, _ = _engine._segment_returns_conv(
        d.panel,
        daily_ret,
        wf,
        d.ext_start,
        d.end,
        CONVENTION,
        COST_BPS_PER_SIDE,
        d.intraday,
        d.overnight,
    )

    if window == "clean":
        return series.loc[(series.index >= d.clean_start) & (series.index <= d.end)]
    if window == "ext":
        return series.loc[(series.index >= d.ext_start) & (series.index <= d.end)]
    raise ValueError("window must be 'clean' or 'ext'.")


def metrics(returns: pd.Series, *, data: HarnessData | None = None) -> dict[str, float]:
    """Compute canonical performance metrics for a returns series."""
    d = data or load_data()
    m = perf_metrics(returns, d.cash)
    return {
        "Sharpe": m.get("sharpe"),
        "Calmar": m.get("calmar"),
        "Martin": m.get("martin"),
        "MaxDD": m.get("max_drawdown"),
        "CAGR": m.get("cagr"),
        "vol": m.get("vol"),
    }


def verify_anchor(*, data: HarnessData | None = None) -> dict[str, float]:
    """Assert production CPM both-252 anchor through this harness.

    Uses `cpm_live.compute_target_weights` as-is. Raises AssertionError with
    detailed expected vs actual metrics when anchor deviates.
    """
    d = data or load_data()
    prod_returns = run_strategy(compute_target_weights, window="clean", data=d)
    got = metrics(prod_returns, data=d)

    failures = []
    for key in ("Sharpe", "MaxDD", "Calmar"):
        target = ANCHOR[key]
        tol = ANCHOR_TOL[key]
        val = got[key]
        if pd.isna(val) or abs(val - target) > tol:
            failures.append(
                f"{key}: got {val:.6f}, expected {target:.6f}, tol {tol:.6f}"
            )
    if failures:
        raise AssertionError(
            "CPM both-252 anchor mismatch through research/cpm_harness.py. "
            + " | ".join(failures)
        )
    return got


__all__ = [
    "ANCHOR",
    "ANCHOR_TOL",
    "CLEAN_START",
    "EXT_START",
    "HarnessData",
    "load_data",
    "run_strategy",
    "metrics",
    "verify_anchor",
]
