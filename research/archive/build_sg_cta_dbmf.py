"""
Build long-history DBMF proxy by stitching:
  SG CTA Trend Index daily returns (NEIXCTAT, 2000-01-03 to 2023-05-09) from pastebin
  + Live DBMF (2019-05-08+) from yfinance

The SG CTA Trend index is what DBMF replicates. Pastebin label says "SG CTA Index" but
the dates and behavior match NEIXCTAT (trend sub-index). We treat as DBMF proxy.
"""
import pandas as pd
import numpy as np
import urllib.request

RAW_PATH = "/tmp/sg_cta_raw.csv"
print(f"Loading SG CTA daily returns from {RAW_PATH}...")
with open(RAW_PATH) as f:
    text = f.read()

rows = []
for line in text.strip().split("\n"):
    line = line.strip()
    if not line or "," not in line: continue
    try:
        d, ret = line.split(",")
        rows.append((pd.Timestamp(d.strip()), float(ret.strip())))
    except Exception:
        continue
sgcta_returns = pd.Series({d: r for d, r in rows}).sort_index()
print(f"SG CTA: {sgcta_returns.index[0].date()} -> {sgcta_returns.index[-1].date()}, {len(sgcta_returns)} obs")

# Build synthetic price series from returns
sgcta_price = (1.0 + sgcta_returns).cumprod() * 100.0

# Pull live DBMF from yfinance (workdir cache)
import yfinance as yf
print("Fetching live DBMF...")
dbmf = yf.download("DBMF", start="2019-01-01", end="2026-05-14", auto_adjust=True, progress=False, threads=False)
if isinstance(dbmf.columns, pd.MultiIndex):
    dbmf = dbmf["Close"]
dbmf = dbmf["Close"] if "Close" in dbmf.columns else dbmf.iloc[:, 0]
dbmf = dbmf.dropna(); dbmf.name = "DBMF"
print(f"DBMF: {dbmf.index[0].date()} -> {dbmf.index[-1].date()}, rows {len(dbmf)}")

# Splice: scale SG CTA segment to live DBMF at first DBMF date
splice = dbmf.index[0]
sg_anchor_arr = sgcta_price.index[sgcta_price.index <= splice]
if len(sg_anchor_arr) == 0:
    raise RuntimeError("No SG CTA data before DBMF start")
sg_anchor = sg_anchor_arr[-1]
scale = dbmf.loc[splice] / sgcta_price.loc[sg_anchor]
print(f"Splice {splice.date()}: SG anchor {sg_anchor.date()} scale {scale:.6f}")

sg_scaled = sgcta_price.loc[sgcta_price.index < splice] * scale
stitched = pd.concat([sg_scaled, dbmf]).sort_index()
stitched = stitched[~stitched.index.duplicated(keep="last")]
stitched.name = "DBMF_stitched"
print(f"Stitched DBMF: {stitched.index[0].date()} -> {stitched.index[-1].date()}, rows {len(stitched)}")
stitched.to_csv("/tmp/dbmf_stitched_daily.csv", header=True)

# Sanity check: yearly returns
yr = stitched.resample("YE").last().pct_change().dropna()
print("\nYearly returns:")
for y, v in yr.items():
    flag = "  (live)" if y >= splice else ""
    print(f"  {y.year}: {v*100:+6.2f}%{flag}")
