"""Fetch NDX constituent OPEN prices to mirror the close panel 1:1.

Mirrors data/ndx_constituents/prices.parquet (auto_adjust=True closes) by
downloading auto_adjust=True OHLC for the SAME ticker universe over the SAME
span, persisting adjusted Open + Close to research/ndx_opens_cache.parquet.

Adjustment alignment: prices.parquet closes are yfinance auto_adjust=True. We
fetch with auto_adjust=True so Open is back-adjusted by the identical split/div
factor as Close -> adjusted_open is on the same basis as the existing adjusted
closes. intraday = Close/Open-1 is scale-invariant (drift-free). We persist the
fetched adjusted Open AND Close so the overnight leg uses yfinance-internal
close shift, mirroring the macro open-cache loader (load_open_close) convention.
"""
from pathlib import Path
import sys
import time

import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PRICES_FILE = ROOT / "data" / "ndx_constituents" / "prices.parquet"
OUT_FILE = ROOT / "research" / "ndx_opens_cache.parquet"


def main():
    closes = pd.read_parquet(PRICES_FILE)
    tickers = sorted(closes.columns)
    start = closes.index.min().strftime("%Y-%m-%d")
    end = (closes.index.max() + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    print(f"universe={len(tickers)} span={start}..{end}")

    opens, ycloses = {}, {}
    chunks = [tickers[i:i + 25] for i in range(0, len(tickers), 25)]
    for ci, chunk in enumerate(chunks):
        for attempt in range(3):
            try:
                df = yf.download(chunk, start=start, end=end, auto_adjust=True,
                                 progress=False, threads=True, group_by="ticker",
                                 timeout=60)
                break
            except Exception as e:
                print(f"  chunk {ci} attempt {attempt} err {e}", file=sys.stderr)
                time.sleep(3)
        else:
            print(f"  chunk {ci} FAILED", file=sys.stderr)
            continue
        if isinstance(df.columns, pd.MultiIndex):
            for t in chunk:
                if t in df.columns.get_level_values(0):
                    sub = df[t]
                    if "Open" in sub and sub["Open"].notna().any():
                        opens[t] = sub["Open"]
                        ycloses[t] = sub["Close"]
        else:
            if "Open" in df:
                opens[chunk[0]] = df["Open"]
                ycloses[chunk[0]] = df["Close"]
        got = sum(1 for t in chunk if t in opens)
        print(f"  chunk {ci+1}/{len(chunks)} got {got}/{len(chunk)}")

    open_df = pd.DataFrame(opens).sort_index()
    yclose_df = pd.DataFrame(ycloses).sort_index()
    open_df = open_df.reindex(columns=tickers)
    yclose_df = yclose_df.reindex(columns=tickers)

    out = pd.concat({"Open": open_df, "Close": yclose_df}, axis=1)
    out.to_parquet(OUT_FILE)
    fetched = int(open_df.notna().any().sum())
    print(f"\nfetched opens for {fetched}/{len(tickers)} tickers")
    print(f"saved {OUT_FILE}  shape={out.shape}")


if __name__ == "__main__":
    main()
