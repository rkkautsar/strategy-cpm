import sys
sys.path.insert(0, "/Users/rkautsar/personal/scripts/strategy_cam")

import pandas as pd
import numpy as np
from aggr_core import (
    AGGRESSIVE_TICKERS, SAFE_ASSETS, download_prices,
    month_end_rebalance_dates, perf_metrics,
)
from aggr_benchmark import run_xs_momentum, run_tsmom, run_spy_bh, align_curves, compute_summary, _segment_returns

AGGR_UNIV = AGGRESSIVE_TICKERS
SECTOR_UNIV = ["XLK","XLE","XLF","XLV","XLI","XLY","XLP","XLB","XLU"]

start = pd.Timestamp("2008-01-01")
end = pd.Timestamp.today().normalize()
extra = ["SPY","SHV","IEF"]
tickers = sorted(set(AGGR_UNIV + SECTOR_UNIV + extra))
download_start = start - pd.DateOffset(years=5)
print(f"Downloading {len(tickers)} tickers...")
close = download_prices(tickers=tickers, start=download_start, end=end, cache_path="/tmp/yfinance_aggr_cache")

results = {}
print("AGGR univ TSMOM..."); results["TSMOM_AGGR"] = run_tsmom(close, start, end, AGGR_UNIV)["daily"]
print("AGGR univ XSMom..."); results["XSMom_AGGR"] = run_xs_momentum(close, start, end, AGGR_UNIV, top_n=2)["daily"]
print("Sector univ TSMOM..."); results["TSMOM_Sector"] = run_tsmom(close, start, end, SECTOR_UNIV)["daily"]
print("Sector univ XSMom..."); results["XSMom_Sector"] = run_xs_momentum(close, start, end, SECTOR_UNIV, top_n=2)["daily"]
print("SPY BH..."); results["SPY_BH"] = run_spy_bh(close, start, end)["daily"]

def ew_buyhold(close, start, end, univ):
    dates = month_end_rebalance_dates(close.index, start, end)
    weights_map = {}
    for d in dates:
        avail = [t for t in univ if pd.notna(close.loc[d].get(t, np.nan))]
        if not avail:
            weights_map[d] = {}
        else:
            w = 1.0/len(avail)
            weights_map[d] = {t: w for t in avail}
    return _segment_returns(close, weights_map, dates, end)

print("EW AGGR univ..."); results["EW_AGGR_univ"] = ew_buyhold(close, start, end, AGGR_UNIV)
print("EW Sector univ..."); results["EW_Sector_univ"] = ew_buyhold(close, start, end, SECTOR_UNIV)

aligned, equity = align_curves(results, 100_000.0)
summary = compute_summary(aligned, equity)
print()
print(f"Window: {aligned.index[0].date()} -> {aligned.index[-1].date()}")
print(summary.to_string(index=False, float_format=lambda x: f"{x:.4f}"))
summary.to_csv("/tmp/universe_test_summary.csv", index=False)
