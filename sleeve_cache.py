from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
CACHE_DIR = ROOT / ".cache" / "sleeves"
QUARANTINE_DIR = CACHE_DIR / "quarantine"

_FILE_DIGEST_MEMO: dict[tuple[str, int, int], str] = {}


def df_digest(df: pd.DataFrame) -> str:
    h = hashlib.sha256()
    h.update(repr(list(map(str, df.columns))).encode())
    h.update(repr([str(t) for t in df.dtypes]).encode())
    h.update(repr(df.shape).encode())
    h.update(pd.util.hash_pandas_object(df, index=True).values.tobytes())
    return h.hexdigest()[:24]


def file_digest(path: str | Path) -> str | None:
    p = Path(path)
    try:
        st = p.stat()
    except OSError:
        return None

    key = (str(p.resolve()), int(st.st_mtime_ns), int(st.st_size))
    cached = _FILE_DIGEST_MEMO.get(key)
    if cached is not None:
        return cached

    digest = hashlib.sha256(p.read_bytes()).hexdigest()[:24]
    _FILE_DIGEST_MEMO[key] = digest
    return digest


def source_guard_digest(paths: Sequence[str | Path]) -> str | None:
    entries: list[dict[str, str]] = []
    for raw in paths:
        p = Path(raw)
        digest = file_digest(p)
        if digest is None:
            return None
        entries.append({"path": str(p.resolve()), "sha256_24": digest})

    canonical = json.dumps(entries, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:24]


def build_canonical_key(
    *,
    sleeve: str,
    logic_version: str | None,
    params: Mapping[str, Any] | None,
    cost_bps: float,
    run_start: pd.Timestamp,
    end: pd.Timestamp,
    data: Mapping[str, Any] | None,
    source_guard: str | None,
    seed: Any = None,
) -> tuple[dict[str, Any], str, str] | None:
    params_obj = dict(params or {})
    data_obj = dict(data or {})

    if not logic_version or not source_guard:
        return None
    if _contains_none(params_obj) or _contains_none(data_obj):
        return None

    key_obj = {
        "sleeve": str(sleeve),
        "logic_version": str(logic_version),
        "params": params_obj,
        "cost_bps": float(cost_bps),
        "window": {
            "run_start": pd.Timestamp(run_start).normalize().date().isoformat(),
            "end": pd.Timestamp(end).normalize().date().isoformat(),
        },
        "data": data_obj,
        "source_guard": str(source_guard),
        "env": {
            "pandas": pd.__version__,
            "numpy": np.__version__,
            "py": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        },
        "seed": seed,
    }

    try:
        canonical_json = json.dumps(key_obj, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError):
        return None

    key_hash = hashlib.sha256(canonical_json.encode()).hexdigest()[:16]
    return key_obj, canonical_json, key_hash


def get_sleeve_returns(
    sleeve_id: str,
    *,
    compute_fn: Callable[[], pd.Series],
    panel: pd.DataFrame | None = None,
    ndx_panel: pd.DataFrame | None = None,
    run_start: pd.Timestamp,
    end: pd.Timestamp,
    cost_bps: float,
    params: Mapping[str, Any] | None = None,
    version: str | None = None,
    data: Mapping[str, Any] | None = None,
    source_files: Sequence[str | Path] | None = None,
    source_guard: str | None = None,
    enable: bool | None = None,
    verify: bool = False,
    seed: Any = None,
    meta: dict[str, Any] | None = None,
) -> pd.Series:
    enabled = enable if enable is not None else os.environ.get("SLEEVE_CACHE", "1") == "1"
    if not enabled:
        return compute_fn()

    verify_on_hit = verify or os.environ.get("SLEEVE_CACHE_VERIFY", "0") == "1"

    if source_guard is None and source_files is not None:
        source_guard = source_guard_digest(source_files)

    key_data = dict(data or {})
    if not key_data:
        if panel is not None:
            key_data["panel"] = df_digest(panel)
        if ndx_panel is not None:
            key_data["ndx_panel"] = df_digest(ndx_panel)

    built = build_canonical_key(
        sleeve=sleeve_id,
        logic_version=version,
        params=params,
        cost_bps=cost_bps,
        run_start=run_start,
        end=end,
        data=key_data,
        source_guard=source_guard,
        seed=seed,
    )
    if built is None:
        return compute_fn()

    key_obj, _canonical_json, key_hash = built
    cache_path = CACHE_DIR / f"{sleeve_id}_{key_hash}.parquet"
    sidecar_path = CACHE_DIR / f"{sleeve_id}_{key_hash}.json"

    if cache_path.exists():
        try:
            cached = _read_cached_series(cache_path)
        except Exception:
            _quarantine_file(cache_path)
            _quarantine_file(sidecar_path)
            cached = None

        if cached is not None:
            sidecar_payload = _read_sidecar_payload(sidecar_path)
            cached.name = sidecar_payload.get("series_name", cached.name)
            if meta is not None:
                meta.clear()
                sidecar_meta = sidecar_payload.get("result_meta")
                if isinstance(sidecar_meta, dict):
                    meta.update(sidecar_meta)
            if verify_on_hit:
                fresh = compute_fn()
                if not _series_equal(cached, fresh):
                    _quarantine_file(cache_path)
                    _quarantine_file(sidecar_path)
                    raise AssertionError(f"SLEEVE_CACHE_VERIFY mismatch for {sleeve_id} key={key_hash}")
            return cached

    fresh = compute_fn()
    if not isinstance(fresh, pd.Series):
        raise TypeError(f"{sleeve_id} compute_fn must return pd.Series, got {type(fresh).__name__}")

    payload_meta = dict(meta) if meta is not None else None
    try:
        _atomic_write_series(cache_path, fresh)
        _atomic_write_sidecar(sidecar_path, key_obj, payload_meta, fresh.name)
    except Exception:
        pass

    return fresh


def _contains_none(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, Mapping):
        return any(_contains_none(v) for v in value.values())
    if isinstance(value, (list, tuple, set)):
        return any(_contains_none(v) for v in value)
    return False


def _atomic_write_series(path: Path, s: pd.Series) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = Path(f"{path}.tmp.{os.getpid()}")
    s.to_frame("ret").to_parquet(tmp_path)
    os.replace(tmp_path, path)


def _atomic_write_sidecar(
    path: Path,
    key_obj: Mapping[str, Any],
    meta: Mapping[str, Any] | None,
    series_name: Any,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "key": dict(key_obj),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if meta:
        payload["result_meta"] = dict(meta)
    payload["series_name"] = series_name

    tmp_path = Path(f"{path}.tmp.{os.getpid()}")
    with tmp_path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, sort_keys=True, default=str)
    os.replace(tmp_path, path)


def _read_cached_series(path: Path) -> pd.Series:
    frame = pd.read_parquet(path)
    if "ret" in frame.columns:
        s = frame["ret"]
    elif frame.shape[1] == 1:
        s = frame.iloc[:, 0]
        s.name = "ret"
    else:
        raise ValueError(f"cached parquet missing 'ret' column: {path}")
    s.index = pd.to_datetime(s.index)
    return s


def _read_sidecar_payload(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)
        if isinstance(payload, dict):
            return payload
    except Exception:
        return {}
    return {}


def _series_equal(left: pd.Series, right: pd.Series) -> bool:
    if not left.index.equals(right.index):
        return False
    lv = left.to_numpy()
    rv = right.to_numpy()
    if np.array_equal(lv, rv, equal_nan=True):
        return True
    return np.allclose(lv, rv, rtol=0.0, atol=1e-12, equal_nan=True)


def _quarantine_file(path: Path) -> None:
    if not path.exists():
        return
    try:
        QUARANTINE_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        dst = QUARANTINE_DIR / f"{path.name}.corrupt.{stamp}.{os.getpid()}"
        os.replace(path, dst)
    except Exception:
        pass
