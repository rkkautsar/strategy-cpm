import shutil

import numpy as np
import pandas as pd

import dashboard_engine as de
from core import get_cached_sleeve_weight
from data_loader import load_panel
from ndx_sleeve_live import (
    COST_BPS_PER_SIDE as NDX_COST_BPS_PER_SIDE,
    compute_ndx_weights,
    load_ndx_panel,
    run_ndx_backtest,
)
from sleeve_cache import CACHE_DIR, build_canonical_key, get_sleeve_returns, source_guard_digest


def _clear_sleeve_cache() -> None:
    shutil.rmtree(CACHE_DIR, ignore_errors=True)


def _legacy_ndx_inline(
    panel: pd.DataFrame,
    ndx_panel: pd.DataFrame,
    run_start: pd.Timestamp,
    end: pd.Timestamp,
    cost_bps: float,
) -> pd.Series:
    moo_engine, macro_intraday, macro_overnight = de._load_macro_mooex_legs(panel.index)

    ndx_cc_full, _ = run_ndx_backtest(panel, ndx_panel, run_start, end, cost_bps=cost_bps)
    full_panel = panel.join(ndx_panel, how="outer", rsuffix="_dup")
    full_panel = full_panel.loc[:, ~full_panel.columns.str.endswith("_dup")]
    full_panel = full_panel.loc[full_panel.index <= end]
    ndx_daily = full_panel.ffill().pct_change()

    ndx_intraday, ndx_overnight = de._load_ndx_constituent_mooex_legs(full_panel.index)
    intraday_full = macro_intraday.reindex(full_panel.index)
    overnight_full = macro_overnight.reindex(full_panel.index)
    add_cols = [c for c in ndx_intraday.columns if c not in intraday_full.columns]
    if add_cols:
        intraday_full = intraday_full.join(ndx_intraday[add_cols], how="left")
        overnight_full = overnight_full.join(ndx_overnight[add_cols], how="left")

    ndx_wf = lambda sd: get_cached_sleeve_weight(
        "ndx", panel, sd, compute_ndx_weights, panel, ndx_panel, sd
    )[0]
    ndx_moc_full, _ = moo_engine._segment_returns_conv(
        full_panel,
        ndx_daily,
        ndx_wf,
        run_start,
        end,
        "moc",
        cost_bps,
        intraday_full,
        overnight_full,
    )
    ndx_mooex_full, _ = moo_engine._segment_returns_conv(
        full_panel,
        ndx_daily,
        ndx_wf,
        run_start,
        end,
        "mooex",
        cost_bps,
        intraday_full,
        overnight_full,
    )
    ndx_delta = (ndx_mooex_full - ndx_moc_full).reindex(ndx_cc_full.index).fillna(0.0)
    return ndx_cc_full + ndx_delta


def _ndx_key_hash(
    panel: pd.DataFrame,
    ndx_panel: pd.DataFrame,
    run_start: pd.Timestamp,
    end: pd.Timestamp,
) -> str:
    source_guard = source_guard_digest(de.NDX_SOURCE_FILES)
    built = build_canonical_key(
        sleeve="ndx",
        logic_version=de.NDX_SLEEVE_VERSION,
        params=de._ndx_cache_params(NDX_COST_BPS_PER_SIDE),
        cost_bps=NDX_COST_BPS_PER_SIDE,
        run_start=run_start,
        end=end,
        data=de._ndx_cache_data(panel, ndx_panel),
        source_guard=source_guard,
        seed=None,
    )
    assert built is not None
    return built[2]


def _cached_ndx(
    panel: pd.DataFrame,
    ndx_panel: pd.DataFrame,
    run_start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.Series:
    return get_sleeve_returns(
        "ndx",
        panel=panel,
        ndx_panel=ndx_panel,
        run_start=run_start,
        end=end,
        cost_bps=NDX_COST_BPS_PER_SIDE,
        params=de._ndx_cache_params(NDX_COST_BPS_PER_SIDE),
        version=de.NDX_SLEEVE_VERSION,
        data=de._ndx_cache_data(panel, ndx_panel),
        source_files=de.NDX_SOURCE_FILES,
        compute_fn=lambda: de.compute_ndx_sleeve_series(
            panel,
            ndx_panel,
            run_start,
            end,
            NDX_COST_BPS_PER_SIDE,
        ),
    )


def test_ndx(monkeypatch):
    monkeypatch.setenv("SLEEVE_CACHE", "1")
    monkeypatch.delenv("SLEEVE_CACHE_VERIFY", raising=False)

    _clear_sleeve_cache()

    end = pd.Timestamp("2020-12-31")
    panel = load_panel(start=pd.Timestamp("2013-01-01"), end=end)
    ndx_panel = load_ndx_panel().loc[:end]
    run_start = max(de.EXT_START, panel.index.min())

    legacy = _legacy_ndx_inline(panel, ndx_panel, run_start, end, NDX_COST_BPS_PER_SIDE)
    miss = _cached_ndx(panel, ndx_panel, run_start, end)
    hit = _cached_ndx(panel, ndx_panel, run_start, end)

    assert miss.index.equals(hit.index)
    assert np.array_equal(miss.values, hit.values, equal_nan=True)
    assert miss.index.equals(legacy.index)
    assert np.array_equal(miss.values, legacy.values, equal_nan=True)

    base_key = _ndx_key_hash(panel, ndx_panel, run_start, end)
    cache_files = sorted(CACHE_DIR.glob("ndx_*.parquet"))
    assert len(cache_files) == 1
    assert base_key in cache_files[0].name

    panel_mut = panel.copy()
    panel_mut.loc[panel_mut.index[-90:], "SPY"] = panel_mut.loc[panel_mut.index[-90:], "SPY"] * 0.50

    mut_key = _ndx_key_hash(panel_mut, ndx_panel, run_start, end)
    assert mut_key != base_key

    mut_miss = _cached_ndx(panel_mut, ndx_panel, run_start, end)
    mut_hit = _cached_ndx(panel_mut, ndx_panel, run_start, end)
    assert np.array_equal(mut_miss.values, mut_hit.values, equal_nan=True)

    cache_files = sorted(CACHE_DIR.glob("ndx_*.parquet"))
    assert len(cache_files) == 2
    assert any(mut_key in p.name for p in cache_files)
