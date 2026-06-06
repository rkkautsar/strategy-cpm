"""Neutral shared utilities and persistent cache/checkpoint layer."""
from __future__ import annotations

import hashlib
import importlib
import json
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

_SLEEVE_CONFIGS = {
    "cpm": {
        "module": "cpm_live",
        "files": ["cpm_live.py", "engine.py", "core.py"],
        "params": [
            "RISKY_UNIVERSE",
            "SAFE_POOL",
            "CANARY_ASSETS",
            "CPM_RISKY_FRACTION_CURVE",
            "TOP_K_CANDIDATES",
            "CORR_LOOKBACK_DAYS",
            "COST_BPS_PER_SIDE",
        ],
    },
    "ndx": {
        "module": "ndx_sleeve_live",
        "files": ["ndx_sleeve_live.py", "engine.py", "core.py"],
        "params": ["VOL_FAST_DAYS", "VOL_SLOW_DAYS", "SELECT_K", "COST_BPS_PER_SIDE", "DELISTING_HAIRCUT"],
    },
    "rpv": {
        "module": "rpv_live",
        "files": ["rpv_live.py", "core.py"],
        "params": ["W", "ZMIN", "LAG_E", "COST_BPS_PER_SIDE", "CAP"],
    },
}

_VAL_CONFIG = {
    "module": "value_sleeve_live",
    "files": ["value_sleeve_live.py", "core.py"],
    "params": ["SELECT_K", "COST_BPS_PER_SIDE", "DELISTING_HAIRCUT"],
}


def _normalize_cache_param(value):
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        return [_normalize_cache_param(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _normalize_cache_param(v) for k, v in value.items()}
    if isinstance(value, set):
        return sorted(_normalize_cache_param(v) for v in value)
    return str(value)


def _build_bust_hash(source_guard: str | None, params: dict) -> str | None:
    if not source_guard:
        return None
    try:
        params_json = json.dumps(params, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError):
        return None
    return hashlib.sha256(f"{source_guard}{params_json}".encode()).hexdigest()[:16]


def _get_sleeve_cache_meta(sleeve: str) -> tuple[str | None, dict]:
    cfg = _SLEEVE_CONFIGS.get(sleeve)
    if cfg is None:
        return None, {}

    from sleeve_cache import source_guard_digest

    root = Path(__file__).resolve().parent
    paths = [root / rel_path for rel_path in cfg["files"]]
    source_guard = source_guard_digest(paths)
    if not source_guard:
        return None, {}

    try:
        mod = importlib.import_module(cfg["module"])
    except Exception:
        return None, {}

    params = {name: _normalize_cache_param(getattr(mod, name, None)) for name in cfg["params"]}
    return source_guard, params


def _get_val_bust_hash() -> str | None:
    from sleeve_cache import source_guard_digest

    root = Path(__file__).resolve().parent
    paths = [root / rel_path for rel_path in _VAL_CONFIG["files"]]
    source_guard = source_guard_digest(paths)
    if not source_guard:
        return None

    try:
        mod = importlib.import_module(_VAL_CONFIG["module"])
    except Exception:
        return None

    params = {name: _normalize_cache_param(getattr(mod, name, None)) for name in _VAL_CONFIG["params"]}
    return _build_bust_hash(source_guard, params)


def _get_panel_hash(df: pd.DataFrame) -> str:
    df_id = id(df)
    if df_id not in _HASH_CACHE:
        _HASH_CACHE[df_id] = hashlib.md5(pd.util.hash_pandas_object(df, index=True).values).hexdigest()[:16]
    return _HASH_CACHE[df_id]


def get_cached_sleeve_weight(sleeve: str, panel: pd.DataFrame, sig_d: pd.Timestamp, compute_fn, *args, **kwargs):
    """Retrieve sleeve weights cache keyed by panel hash + end date + source/param bust hash."""
    end_date = panel.index.max()
    phash = _get_panel_hash(panel)
    end_str = end_date.strftime("%Y-%m-%d")

    source_guard, params = _get_sleeve_cache_meta(sleeve)
    bust_hash = _build_bust_hash(source_guard, params)
    if bust_hash is None:
        return compute_fn(*args, **kwargs)

    checkpoint_path = Path(tempfile.gettempdir()) / f"{sleeve}_weights_{phash}_{end_str}_{bust_hash}.pkl"

    mem_key = (sleeve, phash, end_str, bust_hash)
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
    bust_hash: str | None = None,
) -> Path:
    start_ts = pd.Timestamp(start).normalize()
    end_ts = pd.Timestamp(end).normalize()
    base_dir = Path(checkpoint_dir) if checkpoint_dir is not None else Path(tempfile.gettempdir())
    effective_bust_hash = bust_hash if bust_hash is not None else _get_val_bust_hash()
    suffix = effective_bust_hash if effective_bust_hash is not None else "nocache"
    return base_dir / f"val_backtest_{start_ts.date()}_{end_ts.date()}_{cost_bps:g}_{suffix}.pkl"


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
    bust_hash = _get_val_bust_hash()
    checkpoint_enabled = bust_hash is not None
    checkpoint_path = _val_backtest_checkpoint_path(start, end, cost_bps, checkpoint_dir=checkpoint_dir, bust_hash=bust_hash)
    if checkpoint_enabled and checkpoint_path.exists():
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

    if checkpoint_enabled:
        try:
            checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = checkpoint_path.with_suffix(f".tmp.{os.getpid()}")
            with tmp_path.open("wb") as fh:
                pickle.dump(result, fh, protocol=pickle.HIGHEST_PROTOCOL)
            os.replace(tmp_path, checkpoint_path)
        except Exception:
            pass

    return result
