import yfinance as yf, pandas as pd
from pathlib import Path
cache = Path(__file__).resolve().parent / "_macro_cache"
cache.mkdir(parents=True, exist_ok=True)
for t in ["EWJ", "RWX", "EZU", "IYR"]:
    d = yf.download(t, start="1990-01-01", end="2026-05-23", auto_adjust=True,
                    progress=False, threads=False)
    if isinstance(d.columns, pd.MultiIndex):
        d.columns = d.columns.get_level_values(0)
    out = d[["Open", "Close"]].dropna()
    out.index.name = "Date"
    out.to_csv(cache / f"{t}_ohlc.csv")
    print(t, out.index[0].date(), "->", out.index[-1].date(), len(out), flush=True)
