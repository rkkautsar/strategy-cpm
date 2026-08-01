import csv
import io
import math
import os
from pathlib import Path

from lxml import html as lxml_html

import pandas as pd

import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

ROOT = Path(__file__).parent.resolve()
DATA_DIR = ROOT / "data"

FRED_IDS = ["DGS10", "DGS3MO", "DBAA", "SP500", "BAA", "DAAA", "AAA", "CPIAUCSL", "SAHMREALTIME"]
MULTPL_EARNINGS_URL = "https://www.multpl.com/s-p-500-earnings/table/by-month"
MULTPL_USER_AGENT = "strategy-cpm-data-refresh/1.0 (contact: research@example.com)"
REQUIRED_EARNINGS_COLUMNS = {"Date", "SP500", "Earnings"}
MULTPL_ANCHOR_VALIDATION_MONTHS = 12
MULTPL_ANCHOR_MAX_RELATIVE_ERROR = 0.05

def _build_retrying_session() -> requests.Session:
    retry = Retry(
        total=4,
        connect=4,
        read=4,
        status=4,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods={"GET"},
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def _fetch_bytes(session: requests.Session, url: str) -> bytes:
    response = session.get(url, timeout=15.0)
    response.raise_for_status()
    return response.content


def _fred_api_key_from_env() -> str | None:
    api_key = os.environ.get("FRED_API_KEY", "").strip()
    return api_key or None


def _fred_observations_json_to_csv_bytes(payload: dict, id_: str) -> bytes:
    observations = payload.get("observations") if isinstance(payload, dict) else None
    if not isinstance(observations, list) or not observations:
        raise ValueError(f"Invalid FRED API payload for {id_}: missing observations")

    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["DATE", id_])
    for row in observations:
        if not isinstance(row, dict):
            continue
        date = row.get("date")
        value = row.get("value")
        if date is None or value is None:
            continue
        writer.writerow([date, value])

    content = out.getvalue().encode("utf-8")
    if b"DATE" not in content.upper() or len(content) <= len(f"DATE,{id_}\r\n"):
        raise ValueError(f"Invalid converted CSV payload for {id_}")
    return content


def _fetch_fred_series_csv_bytes(session: requests.Session, id_: str, api_key: str | None) -> bytes:
    if api_key:
        response = session.get(
            "https://api.stlouisfed.org/fred/series/observations",
            params={"series_id": id_, "api_key": api_key, "file_type": "json"},
            timeout=15.0,
        )
        response.raise_for_status()
        return _fred_observations_json_to_csv_bytes(response.json(), id_)

    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={id_}"
    return _fetch_bytes(session, url)


def _read_monthly_cpi(path: Path) -> pd.Series:
    frame = pd.read_csv(path)
    date_col = next((c for c in frame.columns if c.upper() == "DATE"), None)
    value_col = "CPIAUCSL" if "CPIAUCSL" in frame.columns else next(
        (c for c in frame.columns if c.upper() == "VALUE"), None
    )
    if date_col is None or value_col is None:
        raise ValueError("CPIAUCSL cache is missing DATE/CPIAUCSL columns")
    dates = pd.to_datetime(frame[date_col], errors="coerce").dt.to_period("M")
    if dates.isna().any() or dates.duplicated().any():
        raise ValueError("CPIAUCSL cache has invalid or duplicated monthly dates")
    values = pd.to_numeric(frame[value_col], errors="coerce")
    cpi = pd.Series(values.to_numpy(), index=dates).sort_index()
    if cpi.empty:
        raise ValueError("CPIAUCSL cache has no monthly observations")
    expected = pd.period_range(cpi.index.min(), cpi.index.max(), freq="M")
    cpi = cpi.reindex(expected)
    missing = cpi.isna() | ~cpi.map(lambda value: math.isfinite(value) if pd.notna(value) else False)
    if missing.iloc[0] or missing.iloc[-1]:
        raise ValueError("CPIAUCSL has a leading or trailing missing month")
    missing_periods = cpi.index[missing]
    if len(missing_periods):
        runs = (missing_periods.to_timestamp().to_series().diff().dt.days > 40).cumsum()
        for _, run in missing_periods.to_series().groupby(runs.to_numpy()):
            if len(run) != 1:
                raise ValueError("CPIAUCSL has a multi-month internal gap")
            month = run.iloc[0]
            before, after = cpi.loc[month - 1], cpi.loc[month + 1]
            if not (
                pd.notna(before) and pd.notna(after)
                and math.isfinite(before) and math.isfinite(after)
                and before > 0 and after > 0
            ):
                raise ValueError("CPIAUCSL internal gap is not bracketed by positive values")
            cpi.loc[month] = (before + after) / 2
    cpi = cpi[(cpi > 0) & cpi.map(math.isfinite)]
    if cpi.empty:
        raise ValueError("CPIAUCSL cache has no positive monthly observations")
    return cpi


def _parse_multpl_earnings(content: bytes) -> pd.DataFrame:
    root = lxml_html.fromstring(content)
    candidates = []
    for element in root.xpath("//table"):
        attrs = {key.lower(): value.lower() for key, value in element.attrib.items()}
        context = " ".join(element.xpath("./preceding::*[self::h1 or self::h2 or self::h3 or self::caption][1]//text()"))
        marker = " ".join([attrs.get("id", ""), attrs.get("name", ""), attrs.get("class", ""), context]).lower()
        score = (3 if attrs.get("id") == "datatable" else 0) + (2 if "earning" in marker else 0) + (1 if "s&p 500" in marker or "sp500" in marker else 0)
        if score:
            candidates.append((score, lxml_html.tostring(element, encoding="unicode")))
    for _, table_html in sorted(candidates, key=lambda candidate: candidate[0], reverse=True):
        table = pd.read_html(io.StringIO(table_html), flavor="lxml")[0]
        normalized = {str(column).strip().lower(): column for column in table.columns}
        date_col = normalized.get("date")
        value_col = normalized.get("value")
        if date_col is None or value_col is None:
            continue
        result = table[[date_col, value_col]].rename(columns={date_col: "Date", value_col: "MultplEarnings"})
        result["Date"] = pd.to_datetime(result["Date"], errors="coerce").dt.to_period("M")
        result["MultplEarnings"] = pd.to_numeric(result["MultplEarnings"].astype(str).str.replace(",", "", regex=False), errors="coerce")
        result = result.dropna(subset=["Date", "MultplEarnings"])
        result = result[(result["MultplEarnings"] > 0) & result["MultplEarnings"].map(math.isfinite)]
        if not result.empty:
            return result.drop_duplicates("Date", keep="last").set_index("Date").sort_index()
    raise ValueError("Multpl earnings payload has no identified Date/Value earnings table")


def _refresh_sp500_earnings(session: requests.Session, earn_path: Path, cpi_path: Path) -> None:
    """Fill only the canonical file's post-last-positive earnings tail."""
    original = earn_path.read_bytes()
    historical = pd.read_csv(io.BytesIO(original))
    if not REQUIRED_EARNINGS_COLUMNS.issubset(historical.columns):
        raise ValueError("canonical earnings cache is missing required columns")
    historical["Date"] = pd.to_datetime(historical["Date"], errors="coerce").dt.to_period("M")
    if historical["Date"].isna().any() or historical["Date"].duplicated().any():
        raise ValueError("canonical earnings dates are invalid or duplicated")
    historical["Earnings"] = pd.to_numeric(historical["Earnings"], errors="coerce")
    positive_mask = (historical["Earnings"] > 0) & historical["Earnings"].map(math.isfinite)
    positive = historical.loc[positive_mask, "Date"]
    if positive.empty:
        raise ValueError("canonical earnings cache has no positive historical month")
    last_positive = positive.max()

    cpi = _read_monthly_cpi(cpi_path)
    multpl_response = session.get(
        MULTPL_EARNINGS_URL, headers={"User-Agent": MULTPL_USER_AGENT}, timeout=15.0
    )
    multpl_response.raise_for_status()
    multpl = _parse_multpl_earnings(multpl_response.content)
    overlap = sorted(set(positive) & set(multpl.index) & set(cpi.index))
    if not overlap:
        raise ValueError("no positive historical earnings/Multpl/CPI month overlap")
    anchor = overlap[-1]
    canonical_anchor = float(historical.loc[historical["Date"] == anchor, "Earnings"].iloc[-1])
    multpl_anchor = float(multpl.loc[anchor, "MultplEarnings"])
    cpi_anchor = float(cpi.loc[anchor])
    cpi_ref = cpi_anchor * multpl_anchor / canonical_anchor
    if not all(
        math.isfinite(value) and value > 0
        for value in (canonical_anchor, multpl_anchor, cpi_anchor, cpi_ref)
    ):
        raise ValueError("invalid positive finite earnings/CPI anchor")
    recent_overlap = overlap[-MULTPL_ANCHOR_VALIDATION_MONTHS:]
    for month in recent_overlap:
        canonical_value = float(historical.loc[historical["Date"] == month, "Earnings"].iloc[-1])
        reconstructed_value = float(multpl.loc[month, "MultplEarnings"] * cpi.loc[month] / cpi_ref)
        if not (
            math.isfinite(canonical_value)
            and canonical_value > 0
            and math.isfinite(reconstructed_value)
            and reconstructed_value > 0
        ):
            raise ValueError(f"invalid positive earnings overlap at {month}")
        relative_error = abs(reconstructed_value - canonical_value) / canonical_value
        if relative_error > MULTPL_ANCHOR_MAX_RELATIVE_ERROR:
            raise ValueError(
                f"Multpl earnings splice mismatch at {month}: "
                f"relative error {relative_error:.2%} exceeds "
                f"{MULTPL_ANCHOR_MAX_RELATIVE_ERROR:.2%}"
            )
    tail = multpl.loc[multpl.index > last_positive].copy()
    if tail.empty:
        raise ValueError("Multpl has no valid post-tail earnings months")
    if not set(tail.index).issubset(cpi.index) or cpi.loc[tail.index].isna().any():
        raise ValueError("CPIAUCSL is missing one or more Multpl tail months")
    tail["Earnings"] = tail["MultplEarnings"] * cpi.loc[tail.index].to_numpy() / cpi_ref
    if not (
        (tail["Earnings"] > 0) & tail["Earnings"].map(math.isfinite)
    ).all():
        raise ValueError("Multpl tail conversion produced nonpositive or nonfinite earnings")

    updated = historical.set_index("Date").astype({"Earnings": "float64"})
    for month, row in tail.iterrows():
        if month in updated.index:
            updated.loc[month, "Earnings"] = float(row["Earnings"])
        else:
            new_row = {column: pd.NA for column in updated.columns}
            new_row["Earnings"] = float(row["Earnings"])
            updated.loc[month] = new_row
    updated = updated.sort_index().reset_index()
    updated["Date"] = updated["Date"].astype(str)
    output = io.StringIO()
    updated.to_csv(output, index=False, lineterminator="\n")
    earn_path.write_text(output.getvalue(), encoding="utf-8")


def refresh_fred():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    api_key = _fred_api_key_from_env()
    with _build_retrying_session() as session:
        for id_ in FRED_IDS:
            dest_path = DATA_DIR / f"fred_{id_}.csv"
            print(f"Fetching {id_} from FRED...")
            try:
                content = _fetch_fred_series_csv_bytes(session, id_, api_key)
                if len(content) > 100 and b"DATE" in content.upper():
                    with open(dest_path, "wb") as f:
                        f.write(content)
                    print(f"Successfully updated {dest_path}")
                else:
                    print(f"Warning: Invalid content for {id_}, keeping existing.")
            except Exception:
                print(f"Error fetching {id_}. Keeping existing CSV.")

        # Preserve the canonical history and fill only its stale monthly tail.
        earn_path = DATA_DIR / "sp500_earnings.csv"
        print("Refreshing stale S&P 500 earnings tail from Multpl...")
        try:
            _refresh_sp500_earnings(session, earn_path, DATA_DIR / "fred_CPIAUCSL.csv")
            print(f"Successfully refreshed {earn_path} tail")
        except Exception as e:
            print(f"Warning: S&P 500 earnings refresh failed ({e}); keeping existing CSV.")

if __name__ == "__main__":
    refresh_fred()
