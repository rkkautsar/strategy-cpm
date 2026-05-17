"""Stitch AGG long history: VBMFX (1986+) -> AGG (2003-09+)."""
import pandas as pd
import yfinance as yf

print("Downloading AGG...")
agg = yf.download("AGG", start="2003-01-01", end="2026-05-14", auto_adjust=True, progress=False, threads=False)
if isinstance(agg.columns, pd.MultiIndex):
    agg = agg["Close"]
agg = agg["Close"] if "Close" in agg.columns else agg.iloc[:, 0]
agg = agg.dropna(); agg.name = "AGG"

print("Downloading VBMFX...")
vbmfx = yf.download("VBMFX", start="1986-01-01", end="2026-05-14", auto_adjust=True, progress=False, threads=False)
if isinstance(vbmfx.columns, pd.MultiIndex):
    vbmfx = vbmfx["Close"]
vbmfx = vbmfx["Close"] if "Close" in vbmfx.columns else vbmfx.iloc[:, 0]
vbmfx = vbmfx.dropna(); vbmfx.name = "VBMFX"

print(f"AGG:   {agg.index[0].date()} -> {agg.index[-1].date()}")
print(f"VBMFX: {vbmfx.index[0].date()} -> {vbmfx.index[-1].date()}")

splice = agg.index[0]
vbmfx_anchor_date = vbmfx.index[vbmfx.index <= splice][-1]
scale = agg.loc[splice] / vbmfx.loc[vbmfx_anchor_date]
print(f"Splice {splice.date()}: scale {scale:.6f}")

vbmfx_scaled = vbmfx.loc[vbmfx.index < splice] * scale
stitched = pd.concat([vbmfx_scaled, agg]).sort_index()
stitched = stitched[~stitched.index.duplicated(keep="last")]
stitched.name = "AGG_stitched"
print(f"Stitched: {stitched.index[0].date()} -> {stitched.index[-1].date()}, rows {len(stitched)}")
stitched.to_csv("/tmp/agg_stitched_daily.csv", header=True)
print("Wrote /tmp/agg_stitched_daily.csv")
