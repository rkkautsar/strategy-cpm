from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

import data_loader
import refresh_fred
import rpv_live


@pytest.mark.parametrize("module", [data_loader, rpv_live])
def test_fetch_fred_uses_api_when_key_present(monkeypatch, tmp_path, module) -> None:
    monkeypatch.setenv("REFRESH_FRED", "1")
    monkeypatch.setenv("FRED_API_KEY", "top-secret-key")

    calls: list[tuple[str, str, float]] = []

    def _fake_api(id_: str, api_key: str, timeout_s: float = 15.0) -> pd.DataFrame:
        calls.append((id_, api_key, timeout_s))
        return pd.DataFrame(
            {
                "date": ["2024-01-01", "2024-01-02"],
                id_: ["1.0", "2.0"],
            }
        )

    def _fail_csv(*args, **kwargs):
        raise AssertionError("CSV endpoint should not be called when FRED_API_KEY is present")

    monkeypatch.setattr(module, "_read_fred_api_observations_timeout", _fake_api)
    monkeypatch.setattr(module, "_read_csv_url_timeout", _fail_csv)

    series = module._fetch_fred_series("DGS10", fallback_paths=[tmp_path / "missing.csv"])

    assert calls == [("DGS10", "top-secret-key", 15.0)]
    assert list(series.index) == [pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-02")]
    assert list(series.values) == [1.0, 2.0]


@pytest.mark.parametrize("module", [data_loader, rpv_live])
def test_fetch_fred_uses_csv_when_key_absent(monkeypatch, tmp_path, module) -> None:
    monkeypatch.setenv("REFRESH_FRED", "1")
    monkeypatch.delenv("FRED_API_KEY", raising=False)

    calls: list[tuple[str, float]] = []

    def _fake_csv(url: str, timeout_s: float = 15.0) -> pd.DataFrame:
        calls.append((url, timeout_s))
        return pd.DataFrame({"DATE": ["2024-01-01"], "VALUE": ["4.5"]})

    def _fail_api(*args, **kwargs):
        raise AssertionError("FRED API path should not be called when FRED_API_KEY is absent")

    monkeypatch.setattr(module, "_read_csv_url_timeout", _fake_csv)
    monkeypatch.setattr(module, "_read_fred_api_observations_timeout", _fail_api)

    series = module._fetch_fred_series("DGS3MO", fallback_paths=[tmp_path / "missing.csv"])

    assert len(calls) == 1
    assert calls[0][0] == "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS3MO"
    assert list(series.index) == [pd.Timestamp("2024-01-01")]
    assert list(series.values) == [4.5]


def test_fetch_fred_local_fallback_preserved_when_remote_fails(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("REFRESH_FRED", "1")
    monkeypatch.setenv("FRED_API_KEY", "top-secret-key")

    def _fail_remote(*args, **kwargs):
        raise RuntimeError("remote failed")

    monkeypatch.setattr(data_loader, "_read_fred_api_observations_timeout", _fail_remote)

    fallback = tmp_path / "fred_DGS10.csv"
    fallback.write_text("DATE,DGS10\n2025-01-01,3.25\n", encoding="utf-8")

    series = data_loader._fetch_fred_series("DGS10", fallback_paths=[fallback])

    assert list(series.index) == [pd.Timestamp("2025-01-01")]
    assert list(series.values) == [3.25]


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class _FakeSession:
    def __init__(self, payload: dict) -> None:
        self._payload = payload
        self.calls: list[dict] = []

    def get(self, url: str, params: dict | None = None, timeout: float | None = None):
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        return _FakeResponse(self._payload)


def test_refresh_fetch_uses_api_params_when_key_present() -> None:
    payload = {
        "observations": [
            {"date": "2024-01-01", "value": "1.1"},
            {"date": "2024-01-02", "value": "1.2"},
        ]
    }
    session = _FakeSession(payload)

    content = refresh_fred._fetch_fred_series_csv_bytes(session, "DGS10", api_key="api-secret")

    assert len(session.calls) == 1
    call = session.calls[0]
    assert call["url"] == "https://api.stlouisfed.org/fred/series/observations"
    assert call["params"] == {
        "series_id": "DGS10",
        "api_key": "api-secret",
        "file_type": "json",
    }
    assert b"DATE,DGS10" in content
    assert b"2024-01-01,1.1" in content


def test_refresh_fetch_uses_csv_graph_when_key_absent(monkeypatch) -> None:
    calls: list[str] = []

    def _fake_fetch_bytes(session, url: str) -> bytes:
        calls.append(url)
        return b"DATE,DGS10\n2024-01-01,1.0\n"

    monkeypatch.setattr(refresh_fred, "_fetch_bytes", _fake_fetch_bytes)

    content = refresh_fred._fetch_fred_series_csv_bytes(object(), "DGS10", api_key=None)

    assert calls == ["https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10"]
    assert content == b"DATE,DGS10\n2024-01-01,1.0\n"


def test_refresh_fred_does_not_print_api_key_on_fetch_error(monkeypatch, tmp_path, capsys) -> None:
    secret = "ultra-secret-key"
    monkeypatch.setenv("FRED_API_KEY", secret)
    monkeypatch.setattr(refresh_fred, "FRED_IDS", ["DGS10"])
    monkeypatch.setattr(refresh_fred, "DATA_DIR", tmp_path)

    class _CtxSession:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(refresh_fred, "_build_retrying_session", lambda: _CtxSession())

    def _fail_fetch(session, id_: str, api_key: str | None) -> bytes:
        raise RuntimeError(f"boom {api_key}")

    monkeypatch.setattr(refresh_fred, "_fetch_fred_series_csv_bytes", _fail_fetch)
    monkeypatch.setattr(
        refresh_fred,
        "_fetch_bytes",
        lambda session, url: (
            "Date,SP500,Dividend,Earnings,Consumer Price Index,Long Interest Rate,Real Price,Real Dividend,Real Earnings,PE10\n"
            "2024-01-01,1,0,1,1,1,1,1,1,1\n"
        ).encode("utf-8"),
    )

    refresh_fred.refresh_fred()

    output = capsys.readouterr().out
    assert secret not in output
