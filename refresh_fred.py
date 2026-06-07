from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

ROOT = Path(__file__).parent.resolve()
DATA_DIR = ROOT / "data"

FRED_IDS = ["DGS10", "DGS3MO", "DBAA", "SP500", "BAA", "DAAA", "AAA", "CPIAUCSL"]

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


def refresh_fred():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with _build_retrying_session() as session:
        for id_ in FRED_IDS:
            url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={id_}"
            dest_path = DATA_DIR / f"fred_{id_}.csv"
            print(f"Fetching {id_} from FRED...")
            try:
                content = _fetch_bytes(session, url)
                if len(content) > 100 and b"DATE" in content.upper():
                    with open(dest_path, "wb") as f:
                        f.write(content)
                    print(f"Successfully updated {dest_path}")
                else:
                    print(f"Warning: Invalid content for {id_}, keeping existing.")
            except Exception as e:
                print(f"Error fetching {id_}: {e}. Keeping existing CSV.")

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
