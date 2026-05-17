"""Stitch real TIPS history: VIPSX (2000-06+) -> TIP (2003-12+)."""
import pandas as pd
import yfinance as yf

print("Downloading TIP...")
tip = yf.download("TIP", start="2003-01-01", end="2026-05-14", auto_adjust=True, progress=False, threads=False)
if isinstance(tip.columns, pd.MultiIndex):
    tip = tip["Close"]
tip = tip["Close"] if "Close" in tip.columns else tip.iloc[:, 0]
tip = tip.dropna(); tip.name = "TIP"

print("Downloading VIPSX (Vanguard Inflation-Protected Securities Fund)...")
vipsx = yf.download("VIPSX", start="2000-01-01", end="2026-05-14", auto_adjust=True, progress=False, threads=False)
if isinstance(vipsx.columns, pd.MultiIndex):
    vipsx = vipsx["Close"]
vipsx = vipsx["Close"] if "Close" in vipsx.columns else vipsx.iloc[:, 0]
vipsx = vipsx.dropna(); vipsx.name = "VIPSX"

print(f"TIP:   {tip.index[0].date()} -> {tip.index[-1].date()}")
print(f"VIPSX: {vipsx.index[0].date()} -> {vipsx.index[-1].date()}")

splice = tip.index[0]
vipsx_anchor_date = vipsx.index[vipsx.index <= splice][-1]
scale = tip.loc[splice] / vipsx.loc[vipsx_anchor_date]
print(f"Splice {splice.date()}: scale {scale:.6f}")

vipsx_scaled = vipsx.loc[vipsx.index < splice] * scale
stitched = pd.concat([vipsx_scaled, tip]).sort_index()
stitched = stitched[~stitched.index.duplicated(keep="last")]
stitched.name = "TIP_stitched"
print(f"Stitched: {stitched.index[0].date()} -> {stitched.index[-1].date()}, rows {len(stitched)}")
stitched.to_csv("/tmp/tip_stitched_daily.csv", header=True)
