from __future__ import annotations

import hashlib
import json

import pandas as pd
import pytest

import core
import value_sleeve_live


def _expected_bust_hash(source_guard: str, params: dict) -> str:
    params_json = json.dumps(params, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(f"{source_guard}{params_json}".encode()).hexdigest()[:16]


@pytest.mark.parametrize("target", ["cpm", "ndx", "rpv", "val"])
def test_cache_invalidation_invariant_all_sleeves(monkeypatch: pytest.MonkeyPatch, tmp_path, target: str) -> None:
    """Durable invariant: any source or params change must invalidate that sleeve checkpoint."""
    panel = pd.DataFrame({"SPY": [100.0, 101.0]}, index=[pd.Timestamp("2026-06-04"), pd.Timestamp("2026-06-05")])
    sig_d = panel.index[-1]
    monkeypatch.setattr(core.tempfile, "gettempdir", lambda: str(tmp_path))

    if target in {"cpm", "ndx", "rpv"}:
        core._SLEEVE_CACHE_MEM.clear()
        phash = core._get_panel_hash(panel)
        end_str = panel.index.max().strftime("%Y-%m-%d")

        digest_v1 = "digest_v1"
        params_v1 = {"alpha": 1}
        bust_v1 = _expected_bust_hash(digest_v1, params_v1)
        monkeypatch.setattr(core, "_get_sleeve_cache_meta", lambda sleeve: (digest_v1, params_v1))

        calls = {"n": 0}

        def _compute_v1(*_args, **_kwargs):
            calls["n"] += 1
            return ({"SPY": 1.0}, "REGIME", {}, [])

        core.get_cached_sleeve_weight(target, panel, sig_d, _compute_v1)
        assert calls["n"] == 1

        path_v1 = tmp_path / f"{target}_weights_{phash}_{end_str}_{bust_v1}.pkl"
        assert path_v1.exists()
        assert bust_v1 in path_v1.name
        assert (target, phash, end_str, bust_v1) in core._SLEEVE_CACHE_MEM

        core.get_cached_sleeve_weight(target, panel, sig_d, _compute_v1)
        assert calls["n"] == 1

        digest_v2 = "digest_v2"
        bust_v2 = _expected_bust_hash(digest_v2, params_v1)
        monkeypatch.setattr(core, "_get_sleeve_cache_meta", lambda sleeve: (digest_v2, params_v1))
        core.get_cached_sleeve_weight(target, panel, sig_d, _compute_v1)
        assert calls["n"] == 2
        assert bust_v2 != bust_v1
        assert (tmp_path / f"{target}_weights_{phash}_{end_str}_{bust_v2}.pkl").exists()

        params_v2 = {"alpha": 2}
        bust_v3 = _expected_bust_hash(digest_v1, params_v2)
        monkeypatch.setattr(core, "_get_sleeve_cache_meta", lambda sleeve: (digest_v1, params_v2))
        core.get_cached_sleeve_weight(target, panel, sig_d, _compute_v1)
        assert calls["n"] == 3
        assert bust_v3 != bust_v1
        assert (tmp_path / f"{target}_weights_{phash}_{end_str}_{bust_v3}.pkl").exists()
        return

    calls = {"n": 0}

    def _fake_run_value_backtest(*_args, **_kwargs):
        calls["n"] += 1
        rets = pd.Series([0.01], index=[pd.Timestamp("2026-06-05")], name="val")
        hist = [{"sig_d": pd.Timestamp("2026-06-05"), "weights": {"SHV": 1.0}}]
        return rets, hist

    monkeypatch.setattr(value_sleeve_live, "run_value_backtest", _fake_run_value_backtest)

    start = pd.Timestamp("2026-06-01")
    end = pd.Timestamp("2026-06-05")

    monkeypatch.setattr(core, "_get_val_bust_hash", lambda: "valhashv1")
    path_v1 = core._val_backtest_checkpoint_path(start, end, 10.0, checkpoint_dir=tmp_path)
    assert "valhashv1" in path_v1.name

    core.cached_value_backtest(panel, panel, start, end, cost_bps=10.0, checkpoint_dir=tmp_path)
    assert calls["n"] == 1
    core.cached_value_backtest(panel, panel, start, end, cost_bps=10.0, checkpoint_dir=tmp_path)
    assert calls["n"] == 1

    monkeypatch.setattr(core, "_get_val_bust_hash", lambda: "valhashv2")
    path_v2 = core._val_backtest_checkpoint_path(start, end, 10.0, checkpoint_dir=tmp_path)
    assert "valhashv2" in path_v2.name
    assert path_v2 != path_v1
    core.cached_value_backtest(panel, panel, start, end, cost_bps=10.0, checkpoint_dir=tmp_path)
    assert calls["n"] == 2

    monkeypatch.setattr(core, "_get_val_bust_hash", lambda: "valhashv3")
    path_v3 = core._val_backtest_checkpoint_path(start, end, 10.0, checkpoint_dir=tmp_path)
    assert "valhashv3" in path_v3.name
    assert path_v3 != path_v2
    core.cached_value_backtest(panel, panel, start, end, cost_bps=10.0, checkpoint_dir=tmp_path)
    assert calls["n"] == 3
