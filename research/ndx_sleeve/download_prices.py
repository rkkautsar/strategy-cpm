"""Download daily auto-adjusted close prices for all tickers ever in NDX.
Saves to data/ndx_constituents/prices.parquet (compact + fast load).
Handles delisted tickers (returns NaN, fine for PIT membership filtering)."""
from __future__ import annotations
import json
import time
from pathlib import Path
import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parents[2]
TICKERS_FILE = ROOT / "research" / "ndx_sleeve" / "ndx_all_tickers.json"
PRICES_FILE = ROOT / "data" / "ndx_constituents" / "prices.parquet"
PRICES_FILE.parent.mkdir(parents=True, exist_ok=True)

START = "1995-01-01"

def main() -> None:
    tickers = json.loads(TICKERS_FILE.read_text())
    print(f"Downloading {len(tickers)} tickers from {START} ...")

    # yfinance batch download — robust to delisted (returns NaN columns)
    # Chunk into groups of 30 to avoid timeouts
    chunks = [tickers[i:i + 30] for i in range(0, len(tickers), 30)]
    all_dfs = []
    for i, chunk in enumerate(chunks):
        print(f"  chunk {i+1}/{len(chunks)}: {chunk[:3]}...{chunk[-3:]}")
        try:
            df = yf.download(
                chunk, start=START, auto_adjust=True, progress=False,
                threads=True, group_by="ticker", timeout=60,
            )
            # Pivot to wide: index=date, columns=ticker, values=Close
            if isinstance(df.columns, pd.MultiIndex):
                close = df.xs("Close", axis=1, level=1)
            else:
                close = df[["Close"]].rename(columns={"Close": chunk[0]})
            all_dfs.append(close)
        except Exception as e:
            print(f"    ERROR: {e}")
        time.sleep(1)

    panel = pd.concat(all_dfs, axis=1)
    # Drop duplicate columns (some tickers may be in multiple chunks)
    panel = panel.loc[:, ~panel.columns.duplicated()]
    print(f"Final panel: {panel.shape[0]} dates x {panel.shape[1]} tickers")
    panel.to_parquet(PRICES_FILE)
    print(f"Saved to {PRICES_FILE} ({PRICES_FILE.stat().st_size / 1024:.1f} KB)")

    # Sanity check: print coverage
    print()
    print("Sample tickers with data:")
    has_data = (panel.notna().sum() > 100).sum()
    print(f"  Tickers with >100 rows: {has_data}/{len(panel.columns)}")
    for t in ["AAPL", "MSFT", "NVDA", "GOOG", "META", "TSLA", "AMZN"]:
        if t in panel.columns:
            s = panel[t].dropna()
            if len(s):
                print(f"  {t}: {s.index[0].date()} -> {s.index[-1].date()} ({len(s)} rows)")

if __name__ == "__main__":
    main()
