"""Stitch a long-history gold proxy: FSAGX (1990+) -> GC=F (2000-08+) -> GLD (2004-11+).

Each splice scales the older segment to match the newer at the splice date.
Output: daily price series 1990+ named 'GLD_stitched'.
"""
import pandas as pd
import yfinance as yf

# Pull all three
print("Downloading GLD...")
gld = yf.download("GLD", start="2004-01-01", end="2026-05-14", auto_adjust=True, progress=False, threads=False)
if isinstance(gld.columns, pd.MultiIndex):
    gld = gld["Close"]
gld = gld["Close"] if "Close" in gld.columns else gld.iloc[:, 0]
gld = gld.dropna()
gld.name = "GLD"

print("Downloading GC=F...")
gcf = yf.download("GC=F", start="2000-01-01", end="2026-05-14", auto_adjust=True, progress=False, threads=False)
if isinstance(gcf.columns, pd.MultiIndex):
    gcf = gcf["Close"]
gcf = gcf["Close"] if "Close" in gcf.columns else gcf.iloc[:, 0]
gcf = gcf.dropna()
gcf.name = "GCF"

print("Downloading FSAGX...")
fsagx = yf.download("FSAGX", start="1990-01-01", end="2026-05-14", auto_adjust=True, progress=False, threads=False)
if isinstance(fsagx.columns, pd.MultiIndex):
    fsagx = fsagx["Close"]
fsagx = fsagx["Close"] if "Close" in fsagx.columns else fsagx.iloc[:, 0]
fsagx = fsagx.dropna()
fsagx.name = "FSAGX"

print(f"GLD:   {gld.index[0].date()} -> {gld.index[-1].date()}")
print(f"GC=F:  {gcf.index[0].date()} -> {gcf.index[-1].date()}")
print(f"FSAGX: {fsagx.index[0].date()} -> {fsagx.index[-1].date()}")

# Splice 1: GC=F + GLD
splice_to_gld_date = gld.index[0]  # 2004-11-18
gcf_anchor_date = gcf.index[gcf.index <= splice_to_gld_date][-1]
scale_gcf_to_gld = gld.loc[splice_to_gld_date] / gcf.loc[gcf_anchor_date]
print(f"\nGC=F->GLD splice {splice_to_gld_date.date()}: scale {scale_gcf_to_gld:.6f}")
gcf_scaled = gcf.loc[gcf.index < splice_to_gld_date] * scale_gcf_to_gld
mid = pd.concat([gcf_scaled, gld]).sort_index()
mid = mid[~mid.index.duplicated(keep="last")]

# Splice 2: FSAGX + mid
splice_to_gcf_date = mid.index[0]  # 2000-08-30 (start of GC=F coverage)
fsagx_anchor_date = fsagx.index[fsagx.index <= splice_to_gcf_date][-1]
scale_fsagx_to_mid = mid.loc[splice_to_gcf_date] / fsagx.loc[fsagx_anchor_date]
print(f"FSAGX->mid splice {splice_to_gcf_date.date()}: scale {scale_fsagx_to_mid:.6f}")
fsagx_scaled = fsagx.loc[fsagx.index < splice_to_gcf_date] * scale_fsagx_to_mid
stitched = pd.concat([fsagx_scaled, mid]).sort_index()
stitched = stitched[~stitched.index.duplicated(keep="last")]
stitched.name = "GLD_stitched"

print(f"\nStitched GLD: {stitched.index[0].date()} -> {stitched.index[-1].date()}, rows {len(stitched)}")

# Sanity: yearly returns of stitched in pre-GLD vs FSAGX raw
yearly = stitched.resample("YE").last().pct_change().dropna()
print("\nYearly stitched returns 1991-2010 (sanity):")
for y in yearly.loc["1991":"2010"].index:
    print(f"  {y.year}: {yearly.loc[y]*100:+.1f}%")

stitched.to_csv("/tmp/gld_stitched_daily.csv", header=True)
print("\nWrote /tmp/gld_stitched_daily.csv")
