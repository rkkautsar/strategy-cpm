from __future__ import annotations

import pandas as pd

import data_loader
from config import BASE_BLEND_WEIGHTS, SAHM_STRESS_BLEND_WEIGHTS
import sleeves
from sleeves import get_blend_weights


def _reset_sahm_cache() -> None:
    data_loader._load_sahm_realtime.cache_clear()


def test_is_sahm_stress_missing_series_fails_closed(monkeypatch) -> None:
    def _raise_missing(*args, **kwargs):
        raise FileNotFoundError("missing")

    _reset_sahm_cache()
    monkeypatch.setattr(data_loader, "_fetch_fred_series", _raise_missing)

    assert data_loader.is_sahm_stress(pd.Timestamp("2026-04-30")) is False


def test_is_sahm_stress_uses_lagged_availability_and_threshold(monkeypatch) -> None:
    sahm = pd.Series(
        [0.40, 0.55],
        index=pd.to_datetime(["2020-01-31", "2020-02-29"]),
        dtype=float,
    )

    _reset_sahm_cache()
    monkeypatch.setattr(data_loader, "_fetch_fred_series", lambda *args, **kwargs: sahm)

    # 2020-01-31 observation becomes available on 2020-03-07 -> first known value still below threshold.
    assert data_loader.is_sahm_stress(pd.Timestamp("2020-03-10")) is False
    # 2020-02-29 observation becomes available on 2020-04-07 -> now stress turns on.
    assert data_loader.is_sahm_stress(pd.Timestamp("2020-04-10")) is True


def test_get_blend_weights_switches_to_r3_half_under_sahm_stress(monkeypatch) -> None:
    sahm = pd.Series(
        [0.40, 0.55],
        index=pd.to_datetime(["2020-01-31", "2020-02-29"]),
        dtype=float,
    )

    _reset_sahm_cache()
    monkeypatch.setattr(data_loader, "_fetch_fred_series", lambda *args, **kwargs: sahm)

    assert get_blend_weights(pd.Timestamp("2020-03-10")) == BASE_BLEND_WEIGHTS
    assert get_blend_weights(pd.Timestamp("2020-04-10")) == SAHM_STRESS_BLEND_WEIGHTS


def test_build_blend_weight_schedule_applies_t_plus_one_until_window_end(monkeypatch) -> None:
    idx = pd.to_datetime(["2020-01-31", "2020-02-03", "2020-02-28", "2020-03-02"])
    sigs = [pd.Timestamp("2020-01-31"), pd.Timestamp("2020-02-28")]

    def _fake_weights(sig_d: pd.Timestamp) -> dict[str, float]:
        if pd.Timestamp(sig_d) == pd.Timestamp("2020-02-28"):
            return dict(SAHM_STRESS_BLEND_WEIGHTS)
        return dict(BASE_BLEND_WEIGHTS)

    monkeypatch.setattr(sleeves, "get_blend_weights", _fake_weights)

    weights_df, _ = sleeves.build_blend_weight_schedule(idx, sigs, idx[-1])

    # First signal (2020-01-31) applies from next trading day.
    assert weights_df.loc[pd.Timestamp("2020-02-03"), "ndx"] == BASE_BLEND_WEIGHTS["ndx"]
    # Second signal (2020-02-28) applies on 2020-03-02 and includes final day.
    assert weights_df.loc[pd.Timestamp("2020-03-02"), "ndx"] == SAHM_STRESS_BLEND_WEIGHTS["ndx"]
