from types import SimpleNamespace

import pandas as pd
import pytest

import cpm_live


def _args(signal_date=None):
    return SimpleNamespace(signal_date=signal_date)


def test_cmd_allocate_rejects_missing_canary_at_current_signal_date(monkeypatch):
    sig_d = pd.Timestamp("2026-05-29")
    panel = pd.DataFrame({"TIP": [100.0], "HYG": [float("nan")]}, index=[sig_d])
    monkeypatch.setattr(cpm_live, "load_panel", lambda **kwargs: panel)

    with pytest.raises(ValueError, match=r"HYG.*2026-05-29"):
        cpm_live.cmd_allocate(_args())


def test_canary_validation_accepts_populated_signal_date():
    sig_d = pd.Timestamp("2026-05-29")
    panel = pd.DataFrame({"TIP": [100.0], "HYG": [101.0]}, index=[sig_d])

    cpm_live._validate_canary_data(panel, sig_d)
