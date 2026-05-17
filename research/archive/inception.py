import yfinance as yf

tickers = ["QQQ","IGM","SPMO","XLE","XRT","SMH","COWZ","AVUV","MOO","RWJ","SPHQ","XMMO","XMHQ",
           "GLD","TLT","DBC","VNQ","EEM","EFA","SPY","IEF","SHV",
           "WTMF","KMLM","DBMF","PQTAX","AHLT","QMHRX","QMHIX",
           "VBINX","PRPFX","CMTFX","ABYIX","EQCHX","ASFYX"]
for t in tickers:
    try:
        d = yf.download(t, start="1990-01-01", end="2026-05-14", auto_adjust=True, progress=False, threads=False)
        if d is None or d.empty:
            print(f"{t:8s} NO DATA")
            continue
        print(f"{t:8s} {d.index[0].date()}  rows={len(d)}")
    except Exception as e:
        print(f"{t:8s} err {e}")
