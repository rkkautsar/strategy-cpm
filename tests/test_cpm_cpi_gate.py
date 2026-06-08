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
