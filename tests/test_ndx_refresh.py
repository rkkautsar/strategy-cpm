from __future__ import annotations

import pandas as pd

import data_loader
import index_constitution as ic
import ndx_sleeve_live


def test_refresh_ndx_panel_preserves_recycled_prices_but_loader_filters(
    monkeypatch, tmp_path
):
    prices_file = tmp_path / "prices.parquet"
    dates = pd.date_range("2020-01-01", periods=2)
    pd.DataFrame(
        {"CA": [10.0, 11.0], "CURRENT": [20.0, 21.0]}, index=dates
    ).to_parquet(prices_file)

    monkeypatch.setattr(ndx_sleeve_live, "PRICES_FILE", prices_file)
    monkeypatch.setattr(data_loader, "NDX_PRICES_FILE", prices_file)
    monkeypatch.setattr(
        ic,
        "constituents_at",
        lambda *_args, **_kwargs: pd.DataFrame({"symbol": ["CURRENT"]}),
    )

    import yfinance as yf

    def fake_download(tickers, **_kwargs):
        index = pd.date_range("2020-01-02", periods=1)
        return pd.DataFrame({"Close": [22.0]}, index=index)

    monkeypatch.setattr(yf, "download", fake_download)

    refreshed = ndx_sleeve_live.refresh_ndx_panel()

    assert "CA" in refreshed.columns
    assert "CA" in pd.read_parquet(prices_file).columns
    assert "CA" not in data_loader.load_ndx_panel().columns
    assert "CURRENT" in data_loader.load_ndx_panel().columns
