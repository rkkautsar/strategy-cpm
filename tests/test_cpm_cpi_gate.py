from __future__ import annotations

import numpy as np
import pandas as pd

import data_loader
from cpm_live import compute_target_weights


def test_cpi_macro_gate_uses_latest_lagged_value_on_trading_day(monkeypatch) -> None:
    sig_d = pd.Timestamp("2020-03-02")  # trading day, not month-end label
    idx = pd.bdate_range("2019-01-01", sig_d)

    risky = ["R1", "R2", "R3", "R4"]
    safe = ["SHV", "IEF"]

    panel = pd.DataFrame(index=idx, dtype=float)
    base = np.linspace(100.0, 160.0, len(idx))
    for i, ticker in enumerate(risky):
        panel[ticker] = base + i
    for ticker in safe:
        panel[ticker] = 100.0

    monthly_idx = panel.loc[:sig_d].resample("ME").last().index
    assert sig_d not in monthly_idx

    # Construct CPI so lagged YoY at 2020-02-29 is in stress:
    # lagged YoY > 4 and above its 12-month MA.
    cpi_idx = pd.date_range("2018-01-31", "2020-02-29", freq="ME")
    cpi = pd.Series(
        np.where(cpi_idx >= pd.Timestamp("2020-01-31"), 106.0, 100.0),
        index=cpi_idx,
        dtype=float,
    )
    monkeypatch.setattr(data_loader, "_fetch_fred_series", lambda *args, **kwargs: cpi)

    weights, basket, regime, safe_ticker = compute_target_weights(
        panel,
        sig_d,
        universe=risky,
        safe_pool=safe,
    )

    assert regime == "DEFENSIVE"
    assert basket is None
    assert safe_ticker == "SHV"
    assert weights == {safe_ticker: 1.0}


def test_cpi_macro_gate_uses_current_monthly_bin_on_business_month_end(monkeypatch) -> None:
    sig_d = pd.Timestamp("2026-05-29")  # BME signal before calendar month-end label 2026-05-31
    idx = pd.bdate_range("2024-01-01", sig_d)

    risky = ["R1", "R2", "R3", "R4"]
    safe = ["SHV", "IEF"]

    panel = pd.DataFrame(index=idx, dtype=float)
    base = np.linspace(100.0, 180.0, len(idx))
    for i, ticker in enumerate(risky):
        panel[ticker] = base + i
    for ticker in safe:
        panel[ticker] = 100.0

    monthly_idx = panel.loc[:sig_d].resample("ME").last().index
    assert sig_d == sig_d + pd.offsets.BMonthEnd(0)
    assert monthly_idx[-1] == pd.Timestamp("2026-05-31")
    assert sig_d not in monthly_idx

    # Force March-lagged CPI to be non-stress (<4) and April-lagged CPI to be stress (>4).
    # Old behavior (asof(sig_d)) would pick 2026-04-30 -> March lagged value.
    # Fixed behavior on BME should pick 2026-05-31 -> April lagged value.
    cpi_idx = pd.date_range("2024-01-31", "2026-05-31", freq="ME")
    cpi_vals = np.full(len(cpi_idx), 100.0)
    cpi_vals[cpi_idx.year == 2026] = 102.0
    cpi_vals[(cpi_idx.year == 2026) & (cpi_idx.month == 3)] = 103.0
    cpi_vals[(cpi_idx.year == 2026) & (cpi_idx.month == 4)] = 105.0
    cpi = pd.Series(cpi_vals, index=cpi_idx, dtype=float)

    cpi_yoy = 100.0 * (cpi / cpi.shift(12) - 1.0)
    cpi_yoy_lagged = cpi_yoy.shift(1).reindex(monthly_idx).ffill()
    assert cpi_yoy_lagged.loc[pd.Timestamp("2026-04-30")] < 4.0
    assert cpi_yoy_lagged.loc[pd.Timestamp("2026-05-31")] > 4.0

    monkeypatch.setattr(data_loader, "_fetch_fred_series", lambda *args, **kwargs: cpi)

    weights, basket, regime, safe_ticker = compute_target_weights(
        panel,
        sig_d,
        universe=risky,
        safe_pool=safe,
    )

    assert regime == "DEFENSIVE"
    assert basket is None
    assert safe_ticker == "SHV"
    assert weights == {safe_ticker: 1.0}
