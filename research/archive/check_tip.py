import pandas as pd
src = pd.read_csv("/Users/rkautsar/personal/scripts/artifacts/cpa-1997-exact-core-proxy-research/proxy_source_by_asset_day.csv", parse_dates=["Date"], index_col="Date")
tip_src = src["TIP_source"].dropna()
print("TIP proxy segments:")
changes = tip_src.ne(tip_src.shift())
for d, val in tip_src[changes].items():
    print(f"  {d.date()}: {val}")
