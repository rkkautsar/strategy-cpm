# -*- coding: utf-8 -*-
"""Read-only analyst research. Fetch + cache rigorous proxy series to extend
AAA / HAA-Simple / 60-40 components back to (or toward) the Keller paper window.

Caches monthly-close CSVs under research/_macro_cache/. yfinance auto_adjust=True
=> total-return (dividends reinvested) for ETFs and mutual funds. FRED series via
fredgraph CSV (no key). Each series documented in the build step. NO prod edits.
"""
import sys, time
from pathlib import Path
import pandas as pd
import yfinance as yf
import requests

MACRO = Path(__file__).resolve().parent / "_macro_cache"
MACRO.mkdir(exist_ok=True)

# yfinance tickers -> cache filename stem. auto_adjust=True => TR.
YF = {
    "^SP500TR": "SP500TR_tr",      # S&P 500 total return index, 1988+
    "SPY": "SPY_tr", "IEF": "IEF_tr", "TLT": "TLT_tr", "GLD": "GLD_tr",
    "DBC": "DBC_tr", "EEM": "EEM_tr", "EZU": "EZU_tr", "IYR": "IYR_tr",
    "EWJ": "EWJ_tr", "RWX": "RWX_tr", "TIP": "TIP_tr",
    "VFITX": "VFITX_tr",   # Vanguard Interm-Term Treasury, 1991+  (IEF proxy)
    "VUSTX": "VUSTX_tr",   # Vanguard Long-Term Treasury, 1986+    (TLT proxy)
    "VGTSX": "VGTSX_tr",   # Vanguard Total Intl Stock, 1996+      (EZU/dev-exUS proxy)
    "VEIEX": "VEIEX_tr",   # Vanguard Emerging Mkts, 1994+         (EEM proxy)
    "VGSIX": "VGSIX_tr",   # Vanguard REIT Index, 1996+            (IYR proxy)
    "VIPSX": "VIPSX_tr",   # Vanguard Inflation-Protected, 2000+   (real TIPS fund)
    "^SPGSCI": "SPGSCI_idx",  # S&P GSCI commodity index, 1984+    (DBC proxy)
    "GC=F": "GCF_fut",        # gold front future, 2000+           (GLD proxy)
    "XRFIX": "XRFIX_tr",      # intl REIT mutual fund, 1998-11+     (RWX proxy)
}

# Shiller S&P 500 monthly (price + annual dividend + CPI), 1871+, for pre-1988
# S&P 500 TOTAL RETURN reconstruction. Mirror of Robert Shiller's ie_data.
SHILLER_URL = ("https://raw.githubusercontent.com/datasets/s-and-p-500/main/"
               "data/data.csv")

FRED = {
    "GOLDAMGBD228NLBM": "GOLD_LBMA",  # London AM gold fix USD/oz, 1968+ (GLD deep proxy)
    "DGS20": "DGS20",                 # 20y CMT yield (has gaps) - optional
}


def fetch_yf(tk, stem):
    out = MACRO / f"{stem}.csv"
    if out.exists():
        print(f"  cached {stem}")
        return
    for attempt in range(3):
        try:
            df = yf.download(tk, start="1970-01-01", end="2026-05-23",
                             progress=False, auto_adjust=True)
            if len(df):
                s = df["Close"]
                if isinstance(s, pd.DataFrame):
                    s = s.iloc[:, 0]
                s.name = "Close"
                s.to_csv(out)
                print(f"  fetched {stem:12} {len(s):6d} {s.index[0].date()}->{s.index[-1].date()}")
                return
        except Exception as e:
            print(f"  retry {stem} ({e})")
            time.sleep(2)
    print(f"  !! FAILED {stem} ({tk})")


def fetch_fred(sid, stem):
    out = MACRO / f"{stem}.csv"
    if out.exists():
        print(f"  cached {stem}")
        return
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
    try:
        r = requests.get(url, timeout=60)
        r.raise_for_status()
        out.write_text(r.text)
        df = pd.read_csv(out)
        print(f"  fetched {stem:12} {len(df):6d} ({sid})")
    except Exception as e:
        print(f"  !! FAILED FRED {stem} ({e})")


if __name__ == "__main__":
    print("YFINANCE:")
    for tk, stem in YF.items():
        fetch_yf(tk, stem)
    print("FRED:")
    for sid, stem in FRED.items():
        fetch_fred(sid, stem)
    print("SHILLER:")
    out = MACRO / "SHILLER_sp500.csv"
    if out.exists():
        print("  cached SHILLER_sp500")
    else:
        try:
            r = requests.get(SHILLER_URL, timeout=60); r.raise_for_status()
            out.write_text(r.text); print("  fetched SHILLER_sp500")
        except Exception as e:
            print(f"  !! FAILED shiller ({e})")
    print("DONE")
