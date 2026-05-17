import yfinance as yf
import pandas as pd

# Candidates for long-history gold proxy
candidates = [
    "GLD",      # iShares gold, 2004
    "IAU",      # iShares COMEX gold, 2005
    "GC=F",     # COMEX gold futures continuous
    "^XAU",     # Philadelphia Gold/Silver Index
    "VGPMX",    # Vanguard Precious Metals & Mining (miners, but long)
    "FGDAX",    # Fidelity Gold (mutual fund, miners-tilt)
    "FSAGX",    # Fidelity Select Gold
    "FKRCX",    # Franklin Gold and Precious Metals
    "INIVX",    # Van Eck International Gold
    "USAGX",    # USAA Precious Metals
    "OPGSX",    # Oppenheimer Gold & Special Minerals
    "GOLD",     # ticker varies
]

for t in candidates:
    try:
        d = yf.download(t, start="1990-01-01", end="2026-05-14", auto_adjust=True, progress=False, threads=False)
        if d is None or d.empty:
            print(f"{t:8s} NO DATA")
            continue
        if isinstance(d.columns, pd.MultiIndex):
            close = d["Close"]
        else:
            close = d["Close"] if "Close" in d.columns else d.iloc[:, 0]
        close = close.dropna()
        print(f"{t:8s} {close.index[0].date()} -> {close.index[-1].date()}  rows={len(close)}")
    except Exception as e:
        print(f"{t:8s} err {e}")
