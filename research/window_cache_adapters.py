from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

import pandas as pd

import dashboard_engine as de
from cpm_live import CANARY_ASSETS, DEFAULT_CASH, RISKY_UNIVERSE, SAFE_POOL, load_panel
from ndx_sleeve_live import load_ndx_panel
from sleeve_cache import file_digest
from value_sleeve_live import (
    COST_BPS_PER_SIDE as VAL_COST_BPS_PER_SIDE,
    DEFAULT_CACHE_DIR as VAL_CACHE_DIR,
    DELISTING_HAIRCUT as VAL_DELISTING_HAIRCUT,
    SELECT_K as VAL_SELECT_K,
    run_value_backtest,
)

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"

MAX_LOOKBACK_15M = pd.DateOffset(months=15)


def _assert_lookback_contract(offset: pd.DateOffset) -> None:
    probe = pd.Timestamp("2020-01-31")
    if (probe + offset).normalize() > (probe + pd.DateOffset(months=15)).normalize():
        raise ValueError(f"max_lookback {offset} exceeds load_panel 15-month contract")


_assert_lookback_contract(MAX_LOOKBACK_15M)


@dataclass(frozen=True)
class WindowAdapter:
    sleeve: str
    version: str
    params: Mapping[str, Any]
    source_files: tuple[Path, ...]
    data_identity: Mapping[str, str]
    max_lookback: pd.DateOffset
    atol: float
    segment_compute_fn: Callable[[pd.Timestamp, pd.Timestamp], pd.Series]


def get_window_adapter(sleeve: str) -> WindowAdapter:
    s = str(sleeve).strip().lower()
    if s == "cpm":
        return _build_cpm_adapter()
    if s == "rpv":
        return _build_rpv_adapter()
    if s == "ndx":
        return _build_ndx_adapter()
    if s == "val":
        return _build_val_adapter()
    raise ValueError(f"unknown sleeve: {sleeve}")


def all_window_adapters() -> dict[str, WindowAdapter]:
    return {name: get_window_adapter(name) for name in ("cpm", "rpv", "ndx", "val")}


def _build_cpm_adapter() -> WindowAdapter:
    return WindowAdapter(
        sleeve="cpm",
        version="cpm-window-cache-2026-06-06.1",
        params={
            "COST_BPS_PER_SIDE": float(de.COST_BPS_PER_SIDE),
            "CORR_LOOKBACK_DAYS": float(de.CORR_LOOKBACK_DAYS),
            "TOP_K_CANDIDATES": float(de.TOP_K_CANDIDATES),
        },
        source_files=_existing_paths(
            [
                ROOT / "cpm_live.py",
                ROOT / "dashboard_engine.py",
                ROOT / "engine.py",
                ROOT / "core.py",
                ROOT / "data_loader.py",
                *_panel_history_files(),
                *_macro_open_files(),
            ]
        ),
        data_identity={
            "panel_bundle": _bundle_digest(_panel_history_files()),
            "macro_opens_bundle": _bundle_digest(_macro_open_files()),
            "pit_lib": _str_or_missing(de._pit_lib_version()),
        },
        max_lookback=MAX_LOOKBACK_15M,
        atol=0.0,
        segment_compute_fn=_make_cpm_segment_compute_fn(),
    )


def _build_rpv_adapter() -> WindowAdapter:
    fred_files = [
        DATA_DIR / "fred_BAA.csv",
        DATA_DIR / "fred_DAAA.csv",
        DATA_DIR / "fred_AAA.csv",
        DATA_DIR / "fred_CPIAUCSL.csv",
    ]
    return WindowAdapter(
        sleeve="rpv",
        version="rpv-window-cache-2026-06-06.1",
        params={
            "COST_BPS_PER_SIDE": float(de.RPV_COST_BPS_PER_SIDE),
            "EQUITY_TICKER": de.RPV_EQUITY_TICKER,
        },
        source_files=_existing_paths(
            [
                ROOT / "rpv_live.py",
                ROOT / "dashboard_engine.py",
                ROOT / "engine.py",
                ROOT / "core.py",
                ROOT / "data_loader.py",
                *fred_files,
                *_panel_history_files(),
                *_macro_open_files(),
            ]
        ),
        data_identity={
            "fred_bundle": _bundle_digest(fred_files),
            "panel_bundle": _bundle_digest(_panel_history_files()),
        },
        max_lookback=MAX_LOOKBACK_15M,
        atol=0.0,
        segment_compute_fn=_make_rpv_segment_compute_fn(),
    )


def _build_ndx_adapter() -> WindowAdapter:
    ndx_files = [
        DATA_DIR / "ndx_constituents" / "prices.parquet",
        DATA_DIR / "ndx_constituents" / "opens.parquet",
    ]
    return WindowAdapter(
        sleeve="ndx",
        version=de.NDX_SLEEVE_VERSION,
        params=de._ndx_cache_params(de.NDX_COST_BPS_PER_SIDE),
        source_files=_existing_paths(
            [
                ROOT / "ndx_sleeve_live.py",
                ROOT / "dashboard_engine.py",
                ROOT / "engine.py",
                ROOT / "core.py",
                ROOT / "data_loader.py",
                *ndx_files,
                *_panel_history_files(),
                *_macro_open_files(),
            ]
        ),
        data_identity={
            "pit_lib": _str_or_missing(de._pit_lib_version()),
            "ndx_bundle": _bundle_digest(ndx_files),
        },
        max_lookback=MAX_LOOKBACK_15M,
        atol=1e-12,
        segment_compute_fn=_make_ndx_segment_compute_fn(),
    )


def _build_val_adapter() -> WindowAdapter:
    valuein_files = [
        DATA_DIR / "valuein" / "fact.parquet",
        DATA_DIR / "valuein" / "filing.parquet",
        DATA_DIR / "valuein" / "index_membership.parquet",
        DATA_DIR / "valuein" / "security.parquet",
    ]
    ndx_files = [
        DATA_DIR / "ndx_constituents" / "prices.parquet",
    ]
    return WindowAdapter(
        sleeve="val",
        version="val-window-cache-2026-06-06.1",
        params={
            "COST_BPS_PER_SIDE": float(VAL_COST_BPS_PER_SIDE),
            "SELECT_K": float(VAL_SELECT_K),
            "DELISTING_HAIRCUT": float(VAL_DELISTING_HAIRCUT),
        },
        source_files=_existing_paths(
            [
                ROOT / "value_sleeve_live.py",
                ROOT / "ndx_sleeve_live.py",
                ROOT / "dashboard_engine.py",
                ROOT / "engine.py",
                ROOT / "core.py",
                ROOT / "data_loader.py",
                *valuein_files,
                *ndx_files,
                *_panel_history_files(),
            ]
        ),
        data_identity={
            "pit_lib": _str_or_missing(de._pit_lib_version()),
            "valuein_bundle": _bundle_digest(valuein_files),
            "ndx_prices": _digest_or_missing(DATA_DIR / "ndx_constituents" / "prices.parquet"),
        },
        max_lookback=MAX_LOOKBACK_15M,
        atol=0.0,
        segment_compute_fn=_make_val_segment_compute_fn(),
    )


def _make_cpm_segment_compute_fn() -> Callable[[pd.Timestamp, pd.Timestamp], pd.Series]:
    def compute(seg_start: pd.Timestamp, seg_end: pd.Timestamp) -> pd.Series:
        panel = load_panel(start=seg_start, end=seg_end, live=False)
        run_start = max(de.EXT_START, panel.index.min())

        moo_engine, macro_intraday, macro_overnight = de._load_macro_mooex_legs(panel.index)
        cpm_cols = sorted(set(RISKY_UNIVERSE + SAFE_POOL + CANARY_ASSETS + [DEFAULT_CASH]) & set(panel.columns))
        cpm_close = panel[cpm_cols]
        cpm_daily = cpm_close.ffill().pct_change()

        from core import get_cached_sleeve_weight

        cpm_wf = lambda sd: get_cached_sleeve_weight(
            "cpm", cpm_close, sd, de.compute_target_weights, cpm_close, sd
        )[0]
        cpm_full, _ = moo_engine._segment_returns_conv(
            cpm_close,
            cpm_daily,
            cpm_wf,
            run_start,
            seg_end,
            "mooex",
            de.COST_BPS_PER_SIDE,
            macro_intraday,
            macro_overnight,
        )
        compute.last_meta = {
            "panel": panel,
            "run_start": run_start,
            "warmup_start": panel.index.min(),
        }
        return cpm_full

    compute.last_meta = {}
    return compute


def _make_rpv_segment_compute_fn() -> Callable[[pd.Timestamp, pd.Timestamp], pd.Series]:
    def compute(seg_start: pd.Timestamp, seg_end: pd.Timestamp) -> pd.Series:
        panel = load_panel(start=seg_start, end=seg_end, live=False)
        run_start = max(de.EXT_START, panel.index.min())

        moo_engine, macro_intraday, macro_overnight = de._load_macro_mooex_legs(panel.index)
        rpv_cols = sorted(set([de.RPV_EQUITY_TICKER, "TLT", "LQD", de.CASH_TICKER]) & set(panel.columns))
        rpv_close = panel[rpv_cols]
        rpv_daily = panel.ffill().pct_change()

        from core import get_cached_sleeve_weight

        rpv_wf = lambda sd: get_cached_sleeve_weight(
            "rpv", panel, sd, de.compute_rpv_weights, panel, sd
        )[0]
        rpv_raw_full, _ = moo_engine._segment_returns_conv(
            rpv_close,
            rpv_daily,
            rpv_wf,
            run_start,
            seg_end,
            "mooex",
            de.RPV_COST_BPS_PER_SIDE,
            macro_intraday,
            macro_overnight,
        )
        compute.last_meta = {
            "panel": panel,
            "run_start": run_start,
            "warmup_start": panel.index.min(),
        }
        return rpv_raw_full

    compute.last_meta = {}
    return compute


def _make_ndx_segment_compute_fn() -> Callable[[pd.Timestamp, pd.Timestamp], pd.Series]:
    def compute(seg_start: pd.Timestamp, seg_end: pd.Timestamp) -> pd.Series:
        panel = load_panel(start=seg_start, end=seg_end, live=False)
        ndx_panel = load_ndx_panel().loc[:seg_end]
        run_start = max(de.EXT_START, panel.index.min())

        ndx_raw_full = de.compute_ndx_sleeve_series(
            panel,
            ndx_panel,
            run_start,
            seg_end,
            de.NDX_COST_BPS_PER_SIDE,
        )

        full_panel = panel.join(ndx_panel, how="outer", rsuffix="_dup")
        full_panel = full_panel.loc[:, ~full_panel.columns.str.endswith("_dup")]
        full_panel = full_panel.loc[full_panel.index <= seg_end]

        compute.last_meta = {
            "panel": full_panel,
            "run_start": run_start,
            "warmup_start": panel.index.min(),
        }
        return ndx_raw_full

    compute.last_meta = {}
    return compute


def _make_val_segment_compute_fn() -> Callable[[pd.Timestamp, pd.Timestamp], pd.Series]:
    def compute(seg_start: pd.Timestamp, seg_end: pd.Timestamp) -> pd.Series:
        panel = load_panel(start=seg_start, end=seg_end, live=False)
        ndx_panel = load_ndx_panel().loc[:seg_end]
        run_start = max(de.EXT_START, panel.index.min())

        val_raw_full, _ = run_value_backtest(
            panel,
            ndx_panel,
            run_start,
            seg_end,
            cost_bps=VAL_COST_BPS_PER_SIDE,
            cache_dir=VAL_CACHE_DIR,
        )

        full_panel = panel.join(ndx_panel, how="outer", rsuffix="_dup")
        full_panel = full_panel.loc[:, ~full_panel.columns.str.endswith("_dup")]
        full_panel = full_panel.loc[full_panel.index <= seg_end]

        compute.last_meta = {
            "panel": full_panel,
            "run_start": run_start,
            "warmup_start": panel.index.min(),
        }
        return val_raw_full

    compute.last_meta = {}
    return compute


def _panel_history_files() -> list[Path]:
    return [
        DATA_DIR / "proxy_adjusted_close_daily.csv",
        DATA_DIR / "gld_stitched_extended_daily.csv",
        DATA_DIR / "tip_stitched_daily.csv",
        DATA_DIR / "hyg_stitched_daily.csv",
        DATA_DIR / "lqd_stitched_daily.csv",
        DATA_DIR / "shv_stitched_daily.csv",
        DATA_DIR / "ief_stitched_daily.csv",
        DATA_DIR / "tlt_stitched_daily.csv",
        DATA_DIR / "qqq_stitched_daily.csv",
    ]


def _macro_open_files() -> list[Path]:
    return sorted((DATA_DIR / "macro_opens").glob("*.csv"))


def _existing_paths(paths: list[Path]) -> tuple[Path, ...]:
    out: list[Path] = []
    seen: set[Path] = set()
    for raw in paths:
        p = Path(raw)
        if not p.exists():
            continue
        rp = p.resolve()
        if rp in seen:
            continue
        seen.add(rp)
        out.append(rp)
    return tuple(out)


def _digest_or_missing(path: Path) -> str:
    digest = file_digest(path)
    return digest if digest is not None else "missing"


def _bundle_digest(paths: list[Path]) -> str:
    entries: list[str] = []
    for p in paths:
        pp = Path(p)
        if not pp.exists():
            continue
        entries.append(f"{pp.resolve()}:{_digest_or_missing(pp)}")
    if not entries:
        return "missing"
    payload = "|".join(sorted(entries))
    return hashlib.sha256(payload.encode()).hexdigest()[:24]


def _str_or_missing(value: Any) -> str:
    if value is None:
        return "missing"
    return str(value)
