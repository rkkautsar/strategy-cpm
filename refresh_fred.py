import os
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
DATA_DIR = ROOT / "data"

FRED_IDS = ["DGS10", "DGS3MO", "DBAA", "SP500", "BAA", "DAAA", "AAA", "CPIAUCSL"]

def refresh_fred():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for id_ in FRED_IDS:
        url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={id_}"
        dest_path = DATA_DIR / f"fred_{id_}.csv"
        print(f"Fetching {id_} from FRED...")
        try:
            with urllib.request.urlopen(url, timeout=15.0) as response:
                content = response.read()
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
        with urllib.request.urlopen(earn_url, timeout=15.0) as response:
            content = response.read()
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
