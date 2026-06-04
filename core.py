"""Neutral shared utilities and persistent cache/checkpoint layer."""
from __future__ import annotations

import hashlib
import os
import pickle
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

# ===========================================================================
# 1. Neutral Math & Performance Metrics Utilities
# ===========================================================================

def sig_13612U(p: pd.Series) -> float:
    """Simple unweighted average of 1/3/6/12-month total returns."""
    p = p.dropna()
    if len(p) < 13:
        return np.nan
    last = p.iloc[-1]
    r1 = last / p.iloc[-2] - 1
    r3 = last / p.iloc[-4] - 1
    r6 = last / p.iloc[-7] - 1
    r12 = last / p.iloc[-13] - 1
    return (r1 + r3 + r6 + r12) / 4.0


def perf_metrics(daily: pd.Series, cash_daily: pd.Series = None) -> dict:
    """Compute CAGR, Vol, Sharpe, Max Drawdown, Ulcer index, and Calmar/Martin ratios."""
    if daily.empty:
        return {}
    eq = (1.0 + daily).cumprod() * 100_000.0
    days = (eq.index[-1] - eq.index[0]).days
    yrs = days / 365.25
    cagr = (eq.iloc[-1] / eq.iloc[0]) ** (1 / yrs) - 1 if yrs > 0 else float("nan")
    vol = daily.std(ddof=0) * np.sqrt(252)
    sharpe = (daily.mean() * 252) / vol if vol > 0 else float("nan")
    cash_aligned = cash_daily.reindex_like(daily).fillna(0.0) if cash_daily is not None else pd.Series(0.0, index=daily.index)
    excess_daily = daily - cash_aligned
    excess_vol = excess_daily.std(ddof=0) * np.sqrt(252)
    excess_sharpe = (excess_daily.mean() * 252) / excess_vol if excess_vol > 0 else float("nan")
    rm = eq.cummax()
    dd_series = eq / rm - 1
    mdd = dd_series.min()
    ulcer = float(np.sqrt(np.mean(dd_series ** 2)))
    calmar = cagr / abs(mdd) if mdd != 0 and not pd.isna(mdd) else float("nan")
    martin = cagr / ulcer if ulcer > 0 else float("nan")
    return {
        "total_return": eq.iloc[-1] / eq.iloc[0] - 1,
        "cagr": cagr, "vol": vol, "sharpe": sharpe, "excess_sharpe": excess_sharpe, "max_drawdown": mdd,
        "ulcer": ulcer, "calmar": calmar, "martin": martin
    }


# ===========================================================================
# 2. Central Checkpoint & Cache Persistence Layer (Parity-Critical)
# ===========================================================================

_HASH_CACHE = {}
_SLEEVE_CACHE_MEM = {}


def _get_panel_hash(df: pd.DataFrame) -> str:
    df_id = id(df)
    if df_id not in _HASH_CACHE:
        _HASH_CACHE[df_id] = hashlib.md5(pd.util.hash_pandas_object(df, index=True).values).hexdigest()[:16]
    return _HASH_CACHE[df_id]


def get_cached_sleeve_weight(sleeve: str, panel: pd.DataFrame, sig_d: pd.Timestamp, compute_fn, *args, **kwargs):
    """Retrieve weights from a persistent dictionary cache in /tmp, keyed by panel hash + end date."""
    end_date = panel.index.max()
    phash = _get_panel_hash(panel)
    end_str = end_date.strftime("%Y-%m-%d")
    checkpoint_path = Path(tempfile.gettempdir()) / f"{sleeve}_weights_{phash}_{end_str}.pkl"

    mem_key = (sleeve, phash, end_str)
    if mem_key not in _SLEEVE_CACHE_MEM:
        if checkpoint_path.exists():
            try:
                with checkpoint_path.open("rb") as fh:
                    _SLEEVE_CACHE_MEM[mem_key] = pickle.load(fh)
            except Exception:
                _SLEEVE_CACHE_MEM[mem_key] = {}
        else:
            _SLEEVE_CACHE_MEM[mem_key] = {}

    cache_dict = _SLEEVE_CACHE_MEM[mem_key]

    sig_str = sig_d.strftime("%Y-%m-%d")
    if sig_str not in cache_dict:
        result = compute_fn(*args, **kwargs)
        cache_dict[sig_str] = result

        try:
            checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = checkpoint_path.with_suffix(f".tmp.{os.getpid()}")
            with tmp_path.open("wb") as fh:
                pickle.dump(cache_dict, fh, protocol=pickle.HIGHEST_PROTOCOL)
            os.replace(tmp_path, checkpoint_path)
        except Exception:
            pass

    return cache_dict[sig_str]


def _val_backtest_checkpoint_path(
    start: pd.Timestamp,
    end: pd.Timestamp,
    cost_bps: float,
    checkpoint_dir: str | Path | None = None,
) -> Path:
    start_ts = pd.Timestamp(start).normalize()
    end_ts = pd.Timestamp(end).normalize()
    base_dir = Path(checkpoint_dir) if checkpoint_dir is not None else Path(tempfile.gettempdir())
    return base_dir / f"val_backtest_{start_ts.date()}_{end_ts.date()}_{cost_bps:g}.pkl"


def cached_value_backtest(
    cpm_panel: pd.DataFrame,
    ndx_panel: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
    cost_bps: float = 10,
    cache_dir: str = "data/valuein",
    checkpoint_dir: str | Path | None = None,
) -> tuple[pd.Series, list[dict]]:
    """Run VAL backtest once per (start, end, cost) and reuse checkpoint from /tmp."""
    checkpoint_path = _val_backtest_checkpoint_path(start, end, cost_bps, checkpoint_dir=checkpoint_dir)
    if checkpoint_path.exists():
        try:
            with checkpoint_path.open("rb") as fh:
                cached = pickle.load(fh)
            if isinstance(cached, tuple) and len(cached) == 2:
                return cached
        except Exception:
            try:
                checkpoint_path.unlink()
            except OSError:
                pass

    # Dynamic import to prevent circular import chain with value_sleeve_live
    from value_sleeve_live import run_value_backtest
    result = run_value_backtest(cpm_panel, ndx_panel, start, end, cost_bps=cost_bps, cache_dir=cache_dir)

    try:
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = checkpoint_path.with_suffix(f".tmp.{os.getpid()}")
        with tmp_path.open("wb") as fh:
            pickle.dump(result, fh, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(tmp_path, checkpoint_path)
    except Exception:
        pass

    return result
