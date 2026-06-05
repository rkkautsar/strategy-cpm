from __future__ import annotations

import hashlib
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import numpy as np
import pandas as pd

from sleeve_cache import (
    _atomic_write_series,
    _quarantine_file,
    _read_cached_series,
    _series_equal,
    df_digest,
    source_guard_digest,
)

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR_RESEARCH = ROOT / ".cache" / "sleeve_windows"


@dataclass
class _SegmentResult:
    full: pd.Series
    usable: pd.Series
    run_start: pd.Timestamp
    warmup_start: pd.Timestamp
    usable_start: pd.Timestamp
    panel: pd.DataFrame | None


def get_sleeve_window(
    sleeve: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
    *,
    segment_compute_fn: Callable[[pd.Timestamp, pd.Timestamp], pd.Series],
    max_lookback: pd.DateOffset,
    version: str,
    params: Mapping[str, Any],
    source_files: Sequence[str | Path],
    data_identity: Mapping[str, str],
    atol: float = 0.0,
    enable: bool | None = None,
    verify: bool = False,
) -> pd.Series:
    req_start = _normalize_day(start)
    req_end = _normalize_day(end)
    if req_start > req_end:
        raise ValueError(f"invalid window: start {req_start.date()} > end {req_end.date()}")

    _assert_lookback_not_beyond_15m(max_lookback)
    sleeve_norm = str(sleeve).strip().lower()
    atol_class = _atol_class(atol)

    if sleeve_norm == "ndx":
        if float(atol) == 0.0:
            raise ValueError("NDX requires atol=1e-12 for window composition")
        if not np.isclose(float(atol), 1e-12, rtol=0.0, atol=0.0):
            raise ValueError(f"NDX requires atol=1e-12, got {atol!r}")

    enabled = enable if enable is not None else os.environ.get("WINDOW_CACHE", "0") == "1"
    if not enabled:
        fresh = _normalize_series(segment_compute_fn(req_start, req_end))
        return _slice_window(fresh, req_start, req_end)

    source_guard = source_guard_digest(source_files)
    built = _build_window_key(
        sleeve=sleeve_norm,
        version=version,
        params=params,
        atol_class=atol_class,
        data_identity=data_identity,
        source_guard=source_guard,
    )
    if built is None:
        fresh = _normalize_series(segment_compute_fn(req_start, req_end))
        return _slice_window(fresh, req_start, req_end)

    key_obj, key_hash = built
    cache_path = CACHE_DIR_RESEARCH / f"{sleeve_norm}_{key_hash}.parquet"
    sidecar_path = CACHE_DIR_RESEARCH / f"{sleeve_norm}_{key_hash}.json"

    def recompute_full() -> pd.Series:
        return _recompute_and_store(
            req_start=req_start,
            req_end=req_end,
            segment_compute_fn=segment_compute_fn,
            max_lookback=max_lookback,
            cache_path=cache_path,
            sidecar_path=sidecar_path,
            key_obj=key_obj,
            source_guard=source_guard,
            atol_class=atol_class,
        )

    cached, sidecar = _read_cache_entry(cache_path, sidecar_path)
    if cached is None or sidecar is None:
        return recompute_full()

    if source_guard is None or sidecar.get("source_guard") != source_guard:
        return recompute_full()

    if not _audit_sidecar(cached, sidecar, max_lookback):
        _quarantine_file(cache_path)
        _quarantine_file(sidecar_path)
        return recompute_full()

    usable_start = _normalize_day(cached.index.min())
    end_computed = _normalize_day(cached.index.max())

    need_head = req_start < usable_start
    need_tail = req_end > end_computed

    # Conservative safety for sleeves with endpoint/start sensitivity in research path.
    # Prefer correctness over reuse for tail requests or interior sub-slices.
    if sleeve_norm in {"cpm", "rpv"} and (need_tail or req_start > usable_start):
        return recompute_full()

    if not need_head and not need_tail:
        out = _slice_window(cached, req_start, req_end)
        _verify_if_needed(
            verify=verify,
            sleeve=sleeve_norm,
            key_hash=key_hash,
            cached_slice=out,
            req_start=req_start,
            req_end=req_end,
            segment_compute_fn=segment_compute_fn,
            max_lookback=max_lookback,
            atol=atol,
            cache_path=cache_path,
            sidecar_path=sidecar_path,
        )
        return out

    composed = cached.copy()
    write_run_start = _normalize_day(sidecar.get("run_start"))
    write_warmup_start = _normalize_day(sidecar.get("warmup_start"))
    write_boundary_digest = _sidecar_boundary_digest(sidecar)

    if need_head:
        boundary = usable_start
        head_seg = _compute_segment(
            segment_compute_fn=segment_compute_fn,
            seg_start=req_start,
            seg_end=boundary - pd.Timedelta(days=1),
            max_lookback=max_lookback,
        )

        if head_seg.usable.empty or _normalize_day(head_seg.usable.index.min()) > req_start:
            return recompute_full()

        cached_overlap_digest = _sidecar_boundary_digest(sidecar)
        head_overlap_digest = _compute_overlap_digest(head_seg, boundary, max_lookback)
        if cached_overlap_digest is None or head_overlap_digest is None or cached_overlap_digest != head_overlap_digest:
            _quarantine_file(cache_path)
            _quarantine_file(sidecar_path)
            return recompute_full()

        head_only = head_seg.usable.loc[head_seg.usable.index < boundary]
        composed = _merge_prefer_right(head_only, composed)
        if not composed.index.equals(head_only.index.union(cached.index)):
            _quarantine_file(cache_path)
            _quarantine_file(sidecar_path)
            return recompute_full()

        write_run_start = min(write_run_start, head_seg.run_start)
        write_warmup_start = min(write_warmup_start, head_seg.warmup_start)
        write_boundary_digest = _compute_overlap_digest(head_seg, _normalize_day(composed.index.min()), max_lookback)

    if need_tail:
        # Conservative tail strategy: compute tail against full request start to avoid
        # endpoint-sensitive drift in stateful sleeve internals.
        tail_seg = _compute_segment(
            segment_compute_fn=segment_compute_fn,
            seg_start=req_start,
            seg_end=req_end,
            max_lookback=max_lookback,
        )
        if tail_seg.usable.empty or _normalize_day(tail_seg.usable.index.max()) < req_end:
            return recompute_full()

        before = composed
        tail_only = tail_seg.usable.loc[tail_seg.usable.index > end_computed]
        composed = _merge_prefer_left(before, tail_only)
        if not composed.index.equals(before.index.union(tail_only.index)):
            _quarantine_file(cache_path)
            _quarantine_file(sidecar_path)
            return recompute_full()

        write_run_start = min(write_run_start, tail_seg.run_start)
        write_warmup_start = min(write_warmup_start, tail_seg.warmup_start)

    if not _series_structurally_valid(composed):
        _quarantine_file(cache_path)
        _quarantine_file(sidecar_path)
        return recompute_full()

    if _normalize_day(composed.index.min()) > req_start or _normalize_day(composed.index.max()) < req_end:
        return recompute_full()

    _write_cache_entry(
        cache_path=cache_path,
        sidecar_path=sidecar_path,
        key_obj=key_obj,
        source_guard=source_guard,
        atol_class=atol_class,
        max_lookback=max_lookback,
        series=composed,
        run_start=write_run_start,
        warmup_start=write_warmup_start,
        panel_overlap_digest=write_boundary_digest,
    )

    out = _slice_window(composed, req_start, req_end)
    _verify_if_needed(
        verify=verify,
        sleeve=sleeve_norm,
        key_hash=key_hash,
        cached_slice=out,
        req_start=req_start,
        req_end=req_end,
        segment_compute_fn=segment_compute_fn,
        max_lookback=max_lookback,
        atol=atol,
        cache_path=cache_path,
        sidecar_path=sidecar_path,
    )
    return out


def _recompute_and_store(
    *,
    req_start: pd.Timestamp,
    req_end: pd.Timestamp,
    segment_compute_fn: Callable[[pd.Timestamp, pd.Timestamp], pd.Series],
    max_lookback: pd.DateOffset,
    cache_path: Path,
    sidecar_path: Path,
    key_obj: Mapping[str, Any],
    source_guard: str | None,
    atol_class: str,
) -> pd.Series:
    seg = _compute_segment(
        segment_compute_fn=segment_compute_fn,
        seg_start=req_start,
        seg_end=req_end,
        max_lookback=max_lookback,
    )
    if not seg.usable.empty:
        _write_cache_entry(
            cache_path=cache_path,
            sidecar_path=sidecar_path,
            key_obj=key_obj,
            source_guard=source_guard,
            atol_class=atol_class,
            max_lookback=max_lookback,
            series=seg.usable,
            run_start=seg.run_start,
            warmup_start=seg.warmup_start,
            panel_overlap_digest=_compute_overlap_digest(seg, seg.usable_start, max_lookback),
        )
    return _slice_window(seg.usable, req_start, req_end)


def _compute_segment(
    *,
    segment_compute_fn: Callable[[pd.Timestamp, pd.Timestamp], pd.Series],
    seg_start: pd.Timestamp,
    seg_end: pd.Timestamp,
    max_lookback: pd.DateOffset,
) -> _SegmentResult:
    full = _normalize_series(segment_compute_fn(_normalize_day(seg_start), _normalize_day(seg_end)))

    meta = getattr(segment_compute_fn, "last_meta", None)
    if not isinstance(meta, Mapping):
        meta = {}

    panel = meta.get("panel")
    if not isinstance(panel, pd.DataFrame):
        panel = None

    if full.empty:
        run_start = _normalize_day(meta.get("run_start", seg_start))
        warmup_start = _normalize_day(meta.get("warmup_start", run_start))
        usable_start = max(run_start, _normalize_day(warmup_start + max_lookback))
        return _SegmentResult(
            full=full,
            usable=full,
            run_start=run_start,
            warmup_start=warmup_start,
            usable_start=usable_start,
            panel=panel,
        )

    run_start = _normalize_day(meta.get("run_start", full.index.min()))
    warmup_start = _normalize_day(meta.get("warmup_start", run_start))
    usable_start = max(run_start, _normalize_day(warmup_start + max_lookback))

    usable = full.loc[full.index >= usable_start].copy()
    return _SegmentResult(
        full=full,
        usable=usable,
        run_start=run_start,
        warmup_start=warmup_start,
        usable_start=usable_start,
        panel=panel,
    )


def _compute_overlap_digest(segment: _SegmentResult, boundary: pd.Timestamp, max_lookback: pd.DateOffset) -> str | None:
    if segment.panel is None or segment.panel.empty:
        return None
    b = _normalize_day(boundary)
    lo = _normalize_day(b - max_lookback)
    band = segment.panel.loc[(segment.panel.index >= lo) & (segment.panel.index <= b)]
    if band.empty:
        return None
    return df_digest(band.sort_index())


def _build_window_key(
    *,
    sleeve: str,
    version: str,
    params: Mapping[str, Any],
    atol_class: str,
    data_identity: Mapping[str, str],
    source_guard: str | None,
) -> tuple[dict[str, Any], str] | None:
    if not version or not source_guard:
        return None

    params_obj = dict(params or {})
    data_obj = dict(data_identity or {})
    if _contains_none(params_obj) or _contains_none(data_obj):
        return None

    key_obj: dict[str, Any] = {
        "sleeve": str(sleeve),
        "logic_version": str(version),
        "params": params_obj,
        "atol_class": atol_class,
        "data": data_obj,
        "source_guard": str(source_guard),
        "env": {
            "pandas": pd.__version__,
            "numpy": np.__version__,
            "py": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        },
    }

    try:
        canonical_json = json.dumps(key_obj, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError):
        return None

    key_hash = hashlib.sha256(canonical_json.encode()).hexdigest()[:16]
    return key_obj, key_hash


def _write_cache_entry(
    *,
    cache_path: Path,
    sidecar_path: Path,
    key_obj: Mapping[str, Any],
    source_guard: str | None,
    atol_class: str,
    max_lookback: pd.DateOffset,
    series: pd.Series,
    run_start: pd.Timestamp,
    warmup_start: pd.Timestamp,
    panel_overlap_digest: str | None,
) -> None:
    if series.empty:
        return

    payload = {
        "key": dict(key_obj),
        "usable_start": _normalize_day(series.index.min()).date().isoformat(),
        "end_computed": _normalize_day(series.index.max()).date().isoformat(),
        "warmup_start": _normalize_day(warmup_start).date().isoformat(),
        "run_start": _normalize_day(run_start).date().isoformat(),
        "max_lookback": _lookback_str(max_lookback),
        "atol_class": atol_class,
        "source_guard": source_guard,
        "segments": [
            {
                "start": _normalize_day(series.index.min()).date().isoformat(),
                "end": _normalize_day(series.index.max()).date().isoformat(),
                "warmup_start": _normalize_day(warmup_start).date().isoformat(),
                "panel_overlap_digest": panel_overlap_digest,
            }
        ],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "series_name": series.name,
    }

    try:
        _atomic_write_series(cache_path, series)
        _atomic_write_json(sidecar_path, payload)
    except Exception:
        pass


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = Path(f"{path}.tmp.{os.getpid()}")
    with tmp_path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, sort_keys=True, default=str)
    os.replace(tmp_path, path)


def _read_cache_entry(cache_path: Path, sidecar_path: Path) -> tuple[pd.Series | None, dict[str, Any] | None]:
    if not cache_path.exists():
        return None, None

    try:
        cached = _normalize_series(_read_cached_series(cache_path))
    except Exception:
        _quarantine_file(cache_path)
        _quarantine_file(sidecar_path)
        return None, None

    if not _series_structurally_valid(cached):
        _quarantine_file(cache_path)
        _quarantine_file(sidecar_path)
        return None, None

    sidecar = _read_sidecar(sidecar_path)
    if sidecar is None:
        _quarantine_file(cache_path)
        _quarantine_file(sidecar_path)
        return None, None

    cached.name = sidecar.get("series_name", cached.name)
    return cached, sidecar


def _read_sidecar(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _audit_sidecar(cached: pd.Series, sidecar: Mapping[str, Any], max_lookback: pd.DateOffset) -> bool:
    if cached.empty:
        return False
    try:
        run_start = _normalize_day(sidecar.get("run_start"))
        warmup_start = _normalize_day(sidecar.get("warmup_start"))
    except Exception:
        return False

    expected_usable = max(run_start, _normalize_day(warmup_start + max_lookback))
    observed = _normalize_day(cached.index.min())
    if observed < expected_usable:
        return False
    # Return series can validly start a few trading days after expected_usable
    # (e.g. pct_change-based builders). Treat large drifts as structural anomalies.
    if observed > expected_usable + pd.Timedelta(days=7):
        return False

    if sidecar.get("max_lookback") and str(sidecar.get("max_lookback")) != _lookback_str(max_lookback):
        return False

    usable_start_sidecar = sidecar.get("usable_start")
    if usable_start_sidecar and _normalize_day(usable_start_sidecar) != observed:
        return False

    end_sidecar = sidecar.get("end_computed")
    if end_sidecar and _normalize_day(end_sidecar) != _normalize_day(cached.index.max()):
        return False

    return True


def _verify_if_needed(
    *,
    verify: bool,
    sleeve: str,
    key_hash: str,
    cached_slice: pd.Series,
    req_start: pd.Timestamp,
    req_end: pd.Timestamp,
    segment_compute_fn: Callable[[pd.Timestamp, pd.Timestamp], pd.Series],
    max_lookback: pd.DateOffset,
    atol: float,
    cache_path: Path,
    sidecar_path: Path,
) -> None:
    if not verify:
        return

    fresh_seg = _compute_segment(
        segment_compute_fn=segment_compute_fn,
        seg_start=req_start,
        seg_end=req_end,
        max_lookback=max_lookback,
    )
    fresh_slice = _slice_window(fresh_seg.usable, req_start, req_end)

    if not _series_equal_for_atol(cached_slice, fresh_slice, atol):
        _quarantine_file(cache_path)
        _quarantine_file(sidecar_path)
        raise AssertionError(f"WINDOW_CACHE_VERIFY mismatch for {sleeve} key={key_hash}")


def _series_equal_for_atol(left: pd.Series, right: pd.Series, atol: float) -> bool:
    if not left.index.equals(right.index):
        return False

    lv = left.to_numpy()
    rv = right.to_numpy()
    if np.array_equal(lv, rv, equal_nan=True):
        return True

    if float(atol) == 0.0:
        return False
    if np.isclose(float(atol), 1e-12, rtol=0.0, atol=0.0):
        return _series_equal(left, right)
    return bool(np.allclose(lv, rv, rtol=0.0, atol=float(atol), equal_nan=True))


def _merge_prefer_right(left: pd.Series, right: pd.Series) -> pd.Series:
    merged = pd.concat([left, right]).sort_index()
    if merged.index.has_duplicates:
        merged = merged[~merged.index.duplicated(keep="last")]
    return merged


def _merge_prefer_left(left: pd.Series, right: pd.Series) -> pd.Series:
    merged = pd.concat([left, right]).sort_index()
    if merged.index.has_duplicates:
        merged = merged[~merged.index.duplicated(keep="first")]
    return merged


def _series_structurally_valid(s: pd.Series) -> bool:
    if not isinstance(s, pd.Series):
        return False
    if s.empty:
        return False
    if not s.index.is_monotonic_increasing:
        return False
    if s.index.has_duplicates:
        return False
    if not np.issubdtype(s.dtype, np.number):
        return False
    return True


def _slice_window(s: pd.Series, start: pd.Timestamp, end: pd.Timestamp) -> pd.Series:
    if s.empty:
        return s.copy()
    return s.loc[(s.index >= start) & (s.index <= end)].copy()


def _normalize_series(s: pd.Series) -> pd.Series:
    if not isinstance(s, pd.Series):
        raise TypeError(f"segment_compute_fn must return pd.Series, got {type(s).__name__}")
    out = s.copy()
    out.index = pd.to_datetime(out.index)
    out = out.sort_index()
    if out.index.has_duplicates:
        raise ValueError("segment series index has duplicates")
    return out


def _sidecar_boundary_digest(sidecar: Mapping[str, Any]) -> str | None:
    segs = sidecar.get("segments")
    if not isinstance(segs, list) or not segs:
        return None
    first = segs[0]
    if not isinstance(first, Mapping):
        return None
    digest = first.get("panel_overlap_digest")
    if digest is None:
        return None
    return str(digest)


def _normalize_day(ts: Any) -> pd.Timestamp:
    return pd.Timestamp(ts).normalize()


def _atol_class(atol: float) -> str:
    return "strict" if float(atol) == 0.0 else f"tol:{float(atol):g}"


def _lookback_str(offset: pd.DateOffset) -> str:
    months = int(getattr(offset, "months", 0) or 0)
    if months:
        return f"{months}M"
    days = int(getattr(offset, "days", 0) or 0)
    if days:
        return f"{days}D"
    return str(offset)


def _contains_none(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, Mapping):
        return any(_contains_none(v) for v in value.values())
    if isinstance(value, (list, tuple, set)):
        return any(_contains_none(v) for v in value)
    return False


def _assert_lookback_not_beyond_15m(max_lookback: pd.DateOffset) -> None:
    probe = pd.Timestamp("2020-01-31")
    if _normalize_day(probe + max_lookback) > _normalize_day(probe + pd.DateOffset(months=15)):
        raise ValueError(f"max_lookback {max_lookback} exceeds load_panel 15-month warmup")
