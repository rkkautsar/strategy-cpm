from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd
import pytest

from research.window_cache import CACHE_DIR_RESEARCH, get_sleeve_window
from research.window_cache_adapters import get_window_adapter
from sleeve_cache import _atomic_write_series, _read_cached_series, _series_equal

EXT_START = pd.Timestamp("1999-03-10")
CLEAN_START = pd.Timestamp("2008-05-30")
TAIL_SEED_END = pd.Timestamp("2024-12-31")
END = pd.Timestamp("2026-04-30")
SUB_START = pd.Timestamp("2015-01-02")


class CountingSegmentFn:
    def __init__(self, fn: Callable[[pd.Timestamp, pd.Timestamp], pd.Series]):
        self.fn = fn
        self.calls = 0
        self.last_meta: dict = {}

    def __call__(self, seg_start: pd.Timestamp, seg_end: pd.Timestamp) -> pd.Series:
        self.calls += 1
        out = self.fn(seg_start, seg_end)
        raw = getattr(self.fn, "last_meta", {})
        self.last_meta = dict(raw) if isinstance(raw, dict) else {}
        return out


def _clear_window_cache() -> None:
    shutil.rmtree(CACHE_DIR_RESEARCH, ignore_errors=True)


def _window_call(
    adapter,
    start: pd.Timestamp,
    end: pd.Timestamp,
    *,
    segment_compute_fn=None,
    verify: bool = False,
    source_files: list[Path] | tuple[Path, ...] | None = None,
    data_identity: dict[str, str] | None = None,
) -> pd.Series:
    return get_sleeve_window(
        adapter.sleeve,
        start,
        end,
        segment_compute_fn=segment_compute_fn or adapter.segment_compute_fn,
        max_lookback=adapter.max_lookback,
        version=adapter.version,
        params=adapter.params,
        source_files=source_files or adapter.source_files,
        data_identity=data_identity or adapter.data_identity,
        atol=adapter.atol,
        enable=True,
        verify=verify,
    )


def _full_slice(adapter, start: pd.Timestamp, end: pd.Timestamp) -> pd.Series:
    s = adapter.segment_compute_fn(start, end)
    s = s.copy()
    s.index = pd.to_datetime(s.index)
    s = s.sort_index()
    return s.loc[(s.index >= start) & (s.index <= end)]


def _assert_parity(adapter, left: pd.Series, right: pd.Series) -> None:
    assert left.index.equals(right.index)

    lv = left.to_numpy()
    rv = right.to_numpy()
    if adapter.sleeve == "ndx":
        assert _series_equal(left, right)

        exact = np.isclose(lv, rv, rtol=0.0, atol=0.0, equal_nan=True)
        diff_idx = np.flatnonzero(~exact)
        assert len(diff_idx) <= 25
        if len(diff_idx):
            max_abs = float(np.nanmax(np.abs(lv[diff_idx] - rv[diff_idx])))
            assert max_abs < 1e-15
        return

    assert np.array_equal(lv, rv, equal_nan=True)


def _make_toy_segment_fn(scale_fn: Callable[[], float] | None = None):
    sf = scale_fn or (lambda: 1.0)

    def compute(seg_start: pd.Timestamp, seg_end: pd.Timestamp) -> pd.Series:
        seg_start = pd.Timestamp(seg_start).normalize()
        seg_end = pd.Timestamp(seg_end).normalize()
        warmup_start = seg_start - pd.DateOffset(months=15)
        idx = pd.bdate_range(warmup_start, seg_end)
        base = np.arange(len(idx), dtype=float)

        panel = pd.DataFrame({"x": base * float(sf())}, index=idx)
        compute.last_meta = {
            "panel": panel,
            "run_start": seg_start,
            "warmup_start": warmup_start,
        }
        return pd.Series(base, index=idx, name="ret")

    compute.last_meta = {}
    return compute


def _toy_call(
    fn,
    start: pd.Timestamp,
    end: pd.Timestamp,
    source_files: list[Path],
    data_identity: dict[str, str],
    *,
    verify: bool = False,
) -> pd.Series:
    return get_sleeve_window(
        "toy",
        start,
        end,
        segment_compute_fn=fn,
        max_lookback=pd.DateOffset(months=15),
        version="toy-1",
        params={"mode": "toy"},
        source_files=source_files,
        data_identity=data_identity,
        atol=0.0,
        enable=True,
        verify=verify,
    )


def test_g1_g2_composition_parity_ext() -> None:
    for sleeve in ("cpm", "rpv", "val", "ndx"):
        _clear_window_cache()
        adapter = get_window_adapter(sleeve)

        _window_call(adapter, CLEAN_START, END)
        composed_ext = _window_call(adapter, EXT_START, END)
        fresh_ext = _full_slice(adapter, EXT_START, END)

        _assert_parity(adapter, composed_ext, fresh_ext)
        assert composed_ext.index.is_monotonic_increasing
        assert not composed_ext.index.has_duplicates


def test_g3_pure_slice_zero_compute() -> None:
    for sleeve in ("val", "ndx"):
        _clear_window_cache()
        adapter = get_window_adapter(sleeve)

        ext_fresh = _full_slice(adapter, EXT_START, END)
        _window_call(adapter, EXT_START, END)

        counted = CountingSegmentFn(adapter.segment_compute_fn)
        sliced = _window_call(adapter, SUB_START, END, segment_compute_fn=counted)
        fresh_slice = ext_fresh.loc[(ext_fresh.index >= SUB_START) & (ext_fresh.index <= END)]

        assert counted.calls == 0
        _assert_parity(adapter, sliced, fresh_slice)


def test_g4_tail_extend_parity() -> None:
    for sleeve in ("cpm", "rpv", "val", "ndx"):
        _clear_window_cache()
        adapter = get_window_adapter(sleeve)

        _window_call(adapter, CLEAN_START, TAIL_SEED_END)
        composed = _window_call(adapter, CLEAN_START, END)
        fresh = _full_slice(adapter, CLEAN_START, END)

        _assert_parity(adapter, composed, fresh)


def test_g5_warmup_miss_and_audit_quarantine(tmp_path: Path) -> None:
    _clear_window_cache()

    source = tmp_path / "toy_source.txt"
    source.write_text("v1", encoding="utf-8")
    data_identity = {"toy": "1"}

    fn = _make_toy_segment_fn()

    _toy_call(fn, pd.Timestamp("2009-01-02"), pd.Timestamp("2010-12-31"), [source], data_identity)

    counted = CountingSegmentFn(fn)
    out = _toy_call(counted, pd.Timestamp("2008-06-02"), pd.Timestamp("2010-12-31"), [source], data_identity)
    assert counted.calls >= 1
    assert out.index.min() <= pd.Timestamp("2008-06-02")

    sidecars = sorted(CACHE_DIR_RESEARCH.glob("toy_*.json"))
    assert sidecars
    sidecar_path = sidecars[0]
    payload = json.loads(sidecar_path.read_text(encoding="utf-8"))
    payload["warmup_start"] = "2010-01-04"
    sidecar_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")

    counted2 = CountingSegmentFn(fn)
    out2 = _toy_call(counted2, pd.Timestamp("2008-06-02"), pd.Timestamp("2010-12-31"), [source], data_identity)
    assert counted2.calls >= 1
    assert out2.index.min() <= pd.Timestamp("2008-06-02")


def test_g6_source_guard_coarse_and_overlap_guard_fine(tmp_path: Path) -> None:
    _clear_window_cache()

    source = tmp_path / "toy_source.txt"
    source.write_text("coarse-v1", encoding="utf-8")
    data_identity = {"toy": "2"}

    fn = _make_toy_segment_fn()
    _toy_call(fn, pd.Timestamp("2009-01-02"), pd.Timestamp("2010-12-31"), [source], data_identity)

    counted_hit = CountingSegmentFn(fn)
    _toy_call(counted_hit, pd.Timestamp("2009-01-02"), pd.Timestamp("2010-12-31"), [source], data_identity)
    assert counted_hit.calls == 0

    source.write_text("coarse-v2", encoding="utf-8")
    counted_miss = CountingSegmentFn(fn)
    _toy_call(counted_miss, pd.Timestamp("2009-01-02"), pd.Timestamp("2010-12-31"), [source], data_identity)
    assert counted_miss.calls >= 1

    _clear_window_cache()
    source.write_text("fine-stable", encoding="utf-8")

    scale = {"v": 1.0}
    fn_fine = _make_toy_segment_fn(lambda: scale["v"])
    _toy_call(fn_fine, pd.Timestamp("2009-01-02"), pd.Timestamp("2010-12-31"), [source], {"toy": "3"})

    scale["v"] = 2.0
    counted_fine = CountingSegmentFn(fn_fine)
    _toy_call(counted_fine, pd.Timestamp("2008-06-02"), pd.Timestamp("2010-12-31"), [source], {"toy": "3"})
    assert counted_fine.calls >= 2


def test_g7_idempotence_and_order_independence() -> None:
    for sleeve in ("cpm", "rpv", "val", "ndx"):
        _clear_window_cache()
        adapter = get_window_adapter(sleeve)

        ext_first = _window_call(adapter, EXT_START, END)
        counted = CountingSegmentFn(adapter.segment_compute_fn)
        ext_second = _window_call(adapter, EXT_START, END, segment_compute_fn=counted)

        assert counted.calls == 0
        _assert_parity(adapter, ext_first, ext_second)

        clean_from_ext = _window_call(adapter, CLEAN_START, END)

        _clear_window_cache()
        adapter_fresh = get_window_adapter(sleeve)
        clean_first = _window_call(adapter_fresh, CLEAN_START, END)

        _assert_parity(adapter_fresh, clean_from_ext, clean_first)


def test_g9_verify_mode_smoke_ndx() -> None:
    _clear_window_cache()
    adapter = get_window_adapter("ndx")

    start = pd.Timestamp("2012-01-03")
    end = pd.Timestamp("2016-12-30")

    seeded = _window_call(adapter, start, end)
    hit_start = pd.Timestamp(seeded.index.min())
    hit_end = pd.Timestamp(seeded.index.max())

    verified = _window_call(adapter, hit_start, hit_end, verify=True)
    _assert_parity(adapter, seeded.loc[hit_start:hit_end], verified)

    cache_files = sorted(CACHE_DIR_RESEARCH.glob("ndx_*.parquet"))
    assert cache_files

    corrupted = _read_cached_series(cache_files[0])
    corrupt_idx = corrupted.index.min()
    corrupted.loc[corrupt_idx] = float(corrupted.loc[corrupt_idx]) + 1e-3
    _atomic_write_series(cache_files[0], corrupted)

    with pytest.raises(AssertionError, match="WINDOW_CACHE_VERIFY mismatch"):
        _window_call(adapter, hit_start, hit_end, verify=True)
