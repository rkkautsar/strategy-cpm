import csv
import io
import os
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

ROOT = Path(__file__).parent.resolve()
DATA_DIR = ROOT / "data"

FRED_IDS = ["DGS10", "DGS3MO", "DBAA", "SP500", "BAA", "DAAA", "AAA", "CPIAUCSL", "SAHMREALTIME"]

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

        # Also refresh S&P 500 earnings
        earn_url = "https://raw.githubusercontent.com/datasets/s-and-p-500/main/data/data.csv"
        earn_path = DATA_DIR / "sp500_earnings.csv"
        print("Fetching S&P 500 earnings...")
        try:
            content = _fetch_bytes(session, earn_url)
            if len(content) > 100 and b"Earnings" in content:
                with open(earn_path, "wb") as f:
                    f.write(content)
                print(f"Successfully updated {earn_path}")
            else:
                print("Warning: Invalid content for sp500_earnings, keeping existing.")
        except Exception as e:
            print(f"Error fetching earnings: {e}. Keeping existing CSV.")

if __name__ == "__main__":
    refresh_fred()
