#!/usr/bin/env python
"""One-time offline generator script to build the static split calendar and completeness manifest.
This script MUST NEVER be run in backtest or live trading execution paths.
"""
import json
import time
from pathlib import Path


# 184 verified-covered tickers (from val_2b_coverage.json)
COVERED_TICKERS = [
    "AAL", "AAPL", "ABNB", "ADBE", "ADI", "ADP", "ADSK", "AEP", "AKAM", "ALGN",
    "ALNY", "AMAT", "AMD", "AMGN", "AMZN", "APP", "ARM", "ASML", "AVGO", "AXON",
    "AZN", "BATRA", "BATRK", "BIDU", "BIIB", "BKNG", "BKR", "BMRN", "CCEP", "CDNS",
    "CDW", "CEG", "CHKP", "CHRW", "CHTR", "CMCSA", "COST", "CPRT", "CRWD", "CSCO",
    "CSGP", "CSX", "CTAS", "CTSH", "DASH", "DDOG", "DLTR", "DOCU", "DXCM", "EA",
    "EBAY", "ENPH", "EQIX", "ERIC", "EXC", "EXPD", "EXPE", "FANG", "FAST", "FER",
    "FFIV", "FISV", "FLEX", "FOSL", "FOX", "FOXA", "FSLR", "FTNT", "GEHC", "GFS",
    "GILD", "GOOG", "GOOGL", "GRMN", "HAS", "HON", "HSIC", "IDXX", "ILMN", "INCY",
    "INFY", "INSM", "INTC", "INTU", "ISRG", "JBHT", "JD", "KDP", "KHC", "KLAC",
    "LAMR", "LBTYA", "LBTYK", "LCID", "LILA", "LILAK", "LIN", "LOGI", "LRCX", "LULU",
    "MAR", "MAT", "MCHP", "MDB", "MDLZ", "MELI", "META", "MNST", "MPWR", "MRNA",
    "MRVL", "MSFT", "MSTR", "MTCH", "MU", "NCLH", "NFLX", "NTAP", "NTES", "NVDA",
    "NWSA", "NXPI", "ODFL", "OKTA", "ON", "ORCL", "ORLY", "PANW", "PAYX", "PCAR",
    "PDD", "PEP", "PLTR", "PRGO", "PTEN", "PTON", "PYPL", "QCOM", "QGEN", "REGN",
    "RIVN", "ROP", "ROST", "RYAAY", "SBAC", "SBUX", "SHOP", "SIRI", "SMCI", "SNDK",
    "SNPS", "SOLS", "STLD", "STX", "SWKS", "TCOM", "TEAM", "TEVA", "TMUS", "TRI",
    "TRIP", "TSCO", "TSLA", "TTD", "TTWO", "TXN", "UAL", "ULTA", "URBN", "VOD",
    "VRSK", "VRSN", "VRTX", "VSNT", "WBD", "WDAY", "WDC", "WMT", "WTW", "WYNN",
    "XEL", "XRAY", "ZM", "ZS"
]

TMP_SPLITS_PATH = Path("/tmp/val_2b_splits.json")


def _from_cached_tmp() -> dict | None:
    if not TMP_SPLITS_PATH.exists():
        return None
    try:
        with open(TMP_SPLITS_PATH, "r") as f:
            raw = json.load(f)
    except Exception:
        return None

    covered = sorted(list(set(COVERED_TICKERS)))
    if any(t not in raw for t in covered):
        return None

    calendar = {}
    for t in covered:
        events = []
        for item in raw.get(t, []):
            try:
                d, fac = item
                events.append([str(d), float(fac)])
            except Exception:
                pass
        calendar[t] = events
    return calendar


def main():
    data_dir = Path("data")
    data_dir.mkdir(parents=True, exist_ok=True)

    # 1. Write Covered Manifest
    manifest_path = data_dir / "splits_covered_manifest.json"
    with open(manifest_path, "w") as f:
        json.dump({"covered": sorted(list(set(COVERED_TICKERS)))}, f, indent=2)
    print(f"Wrote manifest: {manifest_path}")

    # 2. Fetch splits and assemble calendar
    # We query all covered tickers to fetch their complete split histories
    calendar = _from_cached_tmp()
    if calendar is not None:
        print(f"Loaded cached split history from {TMP_SPLITS_PATH}")
    else:
        import yfinance as yf

        calendar = {}
        print(f"Fetching splits for {len(COVERED_TICKERS)} tickers...")
        for i, t in enumerate(COVERED_TICKERS):
            try:
                s = yf.Ticker(t).splits
                events = []
                for dt, f in s.items():
                    try:
                        events.append([dt.strftime("%Y-%m-%d"), float(f)])
                    except Exception:
                        pass
                calendar[t] = events
            except Exception as e:
                print(f"Error fetching splits for {t}: {e}")
                calendar[t] = []

            if (i + 1) % 20 == 0:
                print(f"  {i+1}/{len(COVERED_TICKERS)} processed")
                time.sleep(0.3)

    calendar_path = data_dir / "splits_calendar.json"
    with open(calendar_path, "w") as f:
        json.dump(calendar, f, indent=2)
    print(f"Wrote calendar: {calendar_path}")


if __name__ == "__main__":
    main()
