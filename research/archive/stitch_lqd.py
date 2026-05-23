"""Stitch real IG corporate bond history: VFICX (1993-11+) -> LQD (2002-07+).

VFICX = Vanguard Intermediate-Term IG Corporate Bond Fund (inception 1993-11).
LQD   = iShares iBoxx $ Investment Grade Corporate Bond ETF (inception 2002-07).

VFICX intermediate maturity ~5-10y is the closest mutual-fund proxy for LQD's
~10-12y duration. Use VFICX returns scaled to LQD price at splice date so the
stitched series is continuous and tradeable-in-spirit.
"""
import pandas as pd
import yfinance as yf

print("Downloading LQD...")
lqd = yf.download("LQD", start="2002-01-01", end="2026-05-14",
                   auto_adjust=True, progress=False, threads=False)
if isinstance(lqd.columns, pd.MultiIndex):
    lqd = lqd["Close"]
lqd = lqd["Close"] if "Close" in lqd.columns else lqd.iloc[:, 0]
lqd = lqd.dropna(); lqd.name = "LQD"

print("Downloading VFICX (Vanguard Intermediate-Term IG Bond Fund)...")
vficx = yf.download("VFICX", start="1993-01-01", end="2026-05-14",
                     auto_adjust=True, progress=False, threads=False)
if isinstance(vficx.columns, pd.MultiIndex):
    vficx = vficx["Close"]
vficx = vficx["Close"] if "Close" in vficx.columns else vficx.iloc[:, 0]
vficx = vficx.dropna(); vficx.name = "VFICX"

print(f"LQD:   {lqd.index[0].date()} -> {lqd.index[-1].date()}")
print(f"VFICX: {vficx.index[0].date()} -> {vficx.index[-1].date()}")

splice = lqd.index[0]
vficx_anchor_date = vficx.index[vficx.index <= splice][-1]
scale = lqd.loc[splice] / vficx.loc[vficx_anchor_date]
print(f"Splice {splice.date()}: scale {scale:.6f}")

vficx_scaled = vficx.loc[vficx.index < splice] * scale
stitched = pd.concat([vficx_scaled, lqd]).sort_index()
stitched = stitched[~stitched.index.duplicated(keep="last")]
stitched.name = "LQD_stitched"
print(f"Stitched: {stitched.index[0].date()} -> {stitched.index[-1].date()}, rows {len(stitched)}")
stitched.to_csv("../../data/lqd_stitched_daily.csv", header=True)
print("Wrote ../../data/lqd_stitched_daily.csv")
