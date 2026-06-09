from __future__ import annotations

import numpy as np
import pandas as pd

from cpm_live import compute_target_weights


def _make_panel(sig_d: pd.Timestamp, start: str, hyg_start: float, hyg_end: float) -> pd.DataFrame:
    idx = pd.bdate_range(start, sig_d)
    panel = pd.DataFrame(index=idx, dtype=float)

    base = np.linspace(100.0, 180.0, len(idx))
    for i, ticker in enumerate(["R1", "R2", "R3", "R4"]):
        panel[ticker] = base + float(i)

    panel["SHV"] = 100.0
    panel["IEF"] = 100.0
    panel["HYG"] = np.linspace(hyg_start, hyg_end, len(idx))
    return panel


def test_hyg_gate_defensive_when_hyg_13612u_negative() -> None:
    sig_d = pd.Timestamp("2022-12-30")
    panel = _make_panel(sig_d, start="2021-01-01", hyg_start=120.0, hyg_end=80.0)

    weights, basket, regime, safe_ticker = compute_target_weights(
        panel,
        sig_d,
        universe=["R1", "R2", "R3", "R4"],
        safe_pool=["SHV", "IEF"],
    )

    assert regime == "DEFENSIVE"
    assert basket is None
    assert weights == {safe_ticker: 1.0}


def test_hyg_gate_risk_on_when_hyg_13612u_positive() -> None:
    sig_d = pd.Timestamp("2022-12-30")
    panel = _make_panel(sig_d, start="2021-01-01", hyg_start=80.0, hyg_end=120.0)

    weights, basket, regime, safe_ticker = compute_target_weights(
        panel,
        sig_d,
        universe=["R1", "R2", "R3", "R4"],
        safe_pool=["SHV", "IEF"],
    )

    assert regime == "RISK_ON"
    assert basket is not None
    assert weights.get(safe_ticker, 0.0) < 1.0
    assert any(ticker.startswith("R") for ticker in weights)


def test_hyg_gate_nan_history_is_not_forced_defensive() -> None:
    sig_d = pd.Timestamp("2020-11-30")
    panel = _make_panel(sig_d, start="2020-01-01", hyg_start=80.0, hyg_end=120.0)

    monthly = panel.loc[:sig_d].resample("ME").last()
    assert len(monthly) < 13

    weights, basket, regime, safe_ticker = compute_target_weights(
        panel,
        sig_d,
        universe=["R1", "R2", "R3", "R4"],
        safe_pool=["SHV", "IEF"],
    )

    assert regime == "RISK_ON"
    assert basket is not None
    assert weights.get(safe_ticker, 0.0) < 1.0
