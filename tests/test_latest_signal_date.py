import pandas as pd
import pytest

from data_loader import latest_signal_date


def test_month_start_uses_previous_month_end():
    index = pd.DatetimeIndex(["2026-01-30", "2026-02-27", "2026-03-31"])
    assert latest_signal_date(index, today="2026-03-01") == pd.Timestamp("2026-02-27")


def test_mid_month_uses_previous_calendar_month():
    index = pd.DatetimeIndex(["2026-03-31", "2026-04-30", "2026-05-15"])
    assert latest_signal_date(index, today="2026-05-14") == pd.Timestamp("2026-04-30")


def test_month_end_does_not_use_current_month_signal():
    index = pd.DatetimeIndex(["2026-04-30", "2026-05-29", "2026-05-31"])
    assert latest_signal_date(index, today="2026-05-31") == pd.Timestamp("2026-04-30")


def test_weekend_and_year_boundary():
    index = pd.DatetimeIndex(["2025-12-31", "2026-01-02", "2026-01-30"])
    assert latest_signal_date(index, today="2026-01-03") == pd.Timestamp("2025-12-31")


def test_fallback_returns_last_panel_date_when_no_prior_month_exists():
    index = pd.DatetimeIndex(["2026-05-01", "2026-05-02"])
    assert latest_signal_date(index, today="2026-05-14") == pd.Timestamp("2026-05-02")


def test_empty_index_raises():
    with pytest.raises(ValueError, match="empty panel index"):
        latest_signal_date(pd.DatetimeIndex([]), today="2026-05-14")
