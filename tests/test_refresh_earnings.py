from pathlib import Path

import pandas as pd
import pytest

import refresh_fred


class _Response:
    def __init__(self, content: bytes):
        self.content = content

    def raise_for_status(self):
        return None


class _Session:
    def __init__(self, content: bytes):
        self.content = content
        self.headers = None

    def get(self, url, headers=None, timeout=None):
        self.headers = headers
        return _Response(self.content)


def _write_inputs(tmp_path: Path, earnings: str, cpi: str) -> Path:
    earn_path = tmp_path / "sp500_earnings.csv"
    earn_path.write_text(earnings, encoding="utf-8")
    (tmp_path / "fred_CPIAUCSL.csv").write_text(cpi, encoding="utf-8")
    return earn_path


def test_multpl_real_eps_converts_and_fills_only_tail(tmp_path):
    earn_path = _write_inputs(
        tmp_path,
        "Date,SP500,Earnings\n2020-01-15,100,5\n2020-02-20,101,6\n2020-03-31,102,7\n2020-04-30,103,0\n2020-05-31,104,0\n",
        "DATE,CPIAUCSL\n2020-01-01,100\n2020-02-01,101\n2020-03-01,102\n2020-04-01,103\n2020-05-01,104\n",
    )
    html = b"<table id='datatable'><tr><th>Date</th><th>Value</th></tr><tr><td>Mar 2020</td><td>14</td></tr><tr><td>Apr 2020</td><td>10</td></tr><tr><td>May 2020</td><td>20</td></tr></table>"

    refresh_fred._refresh_sp500_earnings(
        _Session(html), earn_path, tmp_path / "fred_CPIAUCSL.csv"
    )

    result = pd.read_csv(earn_path)
    assert result["Date"].tolist() == ["2020-01", "2020-02", "2020-03", "2020-04", "2020-05"]
    assert result.loc[:2, "Earnings"].tolist() == [5, 6, 7]
    # Anchor is Mar: cpi_ref = 102 * 14 / 7 = 204, not CPI at the last month.
    assert result.loc[2, "Earnings"] == pytest.approx(14 * 102 / 204)
    assert result.loc[3, "Earnings"] == pytest.approx(10 * 103 / 204)
    assert result.loc[4, "Earnings"] == pytest.approx(20 * 104 / 204)
    assert result.loc[3, "Earnings"] / 10 == pytest.approx(103 / 204)
    assert result.loc[3:, "SP500"].tolist() == [103, 104]


def test_recent_overlap_mismatch_leaves_old_data_untouched(tmp_path):
    months = pd.period_range("2020-01", periods=12, freq="M")
    original = "Date,SP500,Earnings\n" + "".join(
        f"{month},100,10\n" for month in months
    )
    earn_path = _write_inputs(
        tmp_path,
        original,
        "DATE,CPIAUCSL\n"
        + "".join(f"{month}-01,100\n" for month in months)
        + "2021-01-01,100\n",
    )
    rows = "".join(
        f"<tr><td>{month.strftime('%b %Y')}</td><td>{20 if month == months[5] else 10}</td></tr>"
        for month in months
    )
    html = (
        b"<table id='datatable'><tr><th>Date</th><th>Value</th></tr>"
        + rows.encode()
        + b"<tr><td>Jan 2021</td><td>12</td></tr></table>"
    )

    with pytest.raises(ValueError, match="relative error"):
        refresh_fred._refresh_sp500_earnings(
            _Session(html), earn_path, tmp_path / "fred_CPIAUCSL.csv"
        )

    assert earn_path.read_text(encoding="utf-8") == original


def test_malformed_multpl_payload_leaves_old_data_untouched(tmp_path):
    original = "Date,SP500,Earnings\n2020-01-01,100,5\n2020-02-01,101,0\n"
    earn_path = _write_inputs(tmp_path, original, "DATE,CPIAUCSL\n2020-01-01,100\n2020-02-01,101\n")

    with pytest.raises(ValueError):
        refresh_fred._refresh_sp500_earnings(
            _Session(b"<html>not the table</html>"),
            earn_path,
            tmp_path / "fred_CPIAUCSL.csv",
        )

    assert earn_path.read_text(encoding="utf-8") == original


def test_multpl_value_header_uses_identified_table_not_decoy():
    html = b"""
    <h2>Unrelated table</h2><table><tr><th>Date</th><th>Value</th></tr>
    <tr><td>Jan 2020</td><td>999</td></tr></table>
    <h2>S&amp;P 500 Earnings by Month</h2>
    <table id="datatable"><tr><th>Date</th><th>Value</th></tr>
    <tr><td>Jan 2020</td><td>12</td></tr></table>
    """
    result = refresh_fred._parse_multpl_earnings(html)
    assert result.loc[pd.Period("2020-01", freq="M"), "MultplEarnings"] == 12


def test_cpi_single_internal_gap_is_interpolated(tmp_path):
    path = tmp_path / "fred_CPIAUCSL.csv"
    path.write_text("DATE,CPIAUCSL\n2025-09-01,324\n2025-10-01,.\n2025-11-01,326\n", encoding="utf-8")
    result = refresh_fred._read_monthly_cpi(path)
    assert result.loc[pd.Period("2025-10", freq="M")] == pytest.approx(325)


@pytest.mark.parametrize(
    "cpi",
    [
        "DATE,CPIAUCSL\n2025-10-01,.\n2025-11-01,326\n",
        "DATE,CPIAUCSL\n2025-09-01,324\n2025-10-01,.\n",
        "DATE,CPIAUCSL\n2025-09-01,324\n2025-10-01,.\n2025-11-01,.\n2025-12-01,327\n",
    ],
)
def test_cpi_rejects_unbounded_or_multi_month_gaps(tmp_path, cpi):
    path = tmp_path / "fred_CPIAUCSL.csv"
    path.write_text(cpi, encoding="utf-8")
    with pytest.raises(ValueError, match="CPIAUCSL"):
        refresh_fred._read_monthly_cpi(path)


def test_missing_overlap_fails_without_overwriting(tmp_path):
    original = "Date,SP500,Earnings\n2020-01-01,100,5\n2020-02-01,101,0\n"
    earn_path = _write_inputs(tmp_path, original, "DATE,CPIAUCSL\n2019-01-01,100\n")
    html = b"<table id='datatable'><tr><th>Date</th><th>Value</th></tr><tr><td>Feb 2020</td><td>10</td></tr></table>"

    with pytest.raises(ValueError, match="overlap"):
        refresh_fred._refresh_sp500_earnings(
            _Session(html), earn_path, tmp_path / "fred_CPIAUCSL.csv"
        )

    assert earn_path.read_text(encoding="utf-8") == original
