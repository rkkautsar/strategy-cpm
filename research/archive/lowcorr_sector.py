"""Pair/triplet low-corr strategy on generic SPDR sector universe."""
import sys
sys.path.insert(0, "/Users/rkautsar/personal/scripts/strategy_cam")

import numpy as np
import pandas as pd
from itertools import combinations
from aggr_core import AGGRESSIVE_TICKERS, SAFE_ASSETS, download_prices, month_end_rebalance_dates
from aggr_benchmark import _segment_returns, align_curves, compute_summary, run_spy_bh, run_tsmom

# Generic sectors that exist 2008-01
SECTOR_UNIV = ["XLK","XLE","XLF","XLV","XLI","XLY","XLP","XLB","XLU"]
CASH = "SHV"
CORR_LOOKBACK_DAYS = 252

start = pd.Timestamp("2008-01-01")
end = pd.Timestamp.today().normalize()
tickers = sorted(set(SECTOR_UNIV + SAFE_ASSETS + AGGRESSIVE_TICKERS + ["SPY"]))
download_start = start - pd.DateOffset(years=5)
print(f"Downloading {len(tickers)} tickers...")
close = download_prices(tickers=tickers, start=download_start, end=end, cache_path="/tmp/yfinance_aggr_cache")


def mom_12_1(monthly):
    if len(monthly) < 14: return pd.Series(np.nan, index=monthly.columns)
    return monthly.iloc[-2] / monthly.iloc[-14] - 1.0
def mom_12m(monthly):
    if len(monthly) < 13: return pd.Series(np.nan, index=monthly.columns)
    return monthly.iloc[-1] / monthly.iloc[-13] - 1.0
def mom_6m(monthly):
    if len(monthly) < 7: return pd.Series(np.nan, index=monthly.columns)
    return monthly.iloc[-1] / monthly.iloc[-7] - 1.0
def mom_sma10m_dist(monthly):
    if len(monthly) < 10: return pd.Series(np.nan, index=monthly.columns)
    sma = monthly.rolling(10).mean().iloc[-1]
    return (monthly.iloc[-1] - sma) / sma
def mom_multi_avg(monthly):
    if len(monthly) < 13: return pd.Series(np.nan, index=monthly.columns)
    r3 = monthly.iloc[-1] / monthly.iloc[-4] - 1.0
    r6 = monthly.iloc[-1] / monthly.iloc[-7] - 1.0
    r12 = monthly.iloc[-1] / monthly.iloc[-13] - 1.0
    return (r3 + r6 + r12) / 3.0

RANKERS = {"M12_1": mom_12_1, "M12": mom_12m, "M6": mom_6m, "MSMAdist": mom_sma10m_dist, "MMulti": mom_multi_avg}
WEIGHT_SCHEMES = [(0.50, 0.50), (0.60, 0.40), (0.70, 0.30)]
TRIPLET_WEIGHT_SCHEMES = [(1/3, 1/3, 1/3), (0.50, 0.30, 0.20), (0.40, 0.35, 0.25), (0.60, 0.25, 0.15)]


def lowest_corr_pair(daily_close, candidates, lookback_days=CORR_LOOKBACK_DAYS):
    if len(candidates) < 2: return None
    rets = daily_close[candidates].iloc[-lookback_days:].pct_change().dropna(how="all")
    if len(rets) < 30: return None
    corr = rets.corr()
    best, val = None, float("inf")
    for a, b in combinations(candidates, 2):
        c = corr.loc[a, b]
        if pd.notna(c) and c < val:
            val, best = c, (a, b)
    return best

def lowest_corr_triplet(daily_close, candidates, lookback_days=CORR_LOOKBACK_DAYS):
    if len(candidates) < 3: return None
    rets = daily_close[candidates].iloc[-lookback_days:].pct_change().dropna(how="all")
    if len(rets) < 30: return None
    corr = rets.corr()
    best, val = None, float("inf")
    for a, b, c in combinations(candidates, 3):
        ac = (corr.loc[a, b] + corr.loc[a, c] + corr.loc[b, c]) / 3.0
        if pd.notna(ac) and ac < val:
            val, best = ac, (a, b, c)
    return best


def run_pair(close, ranker, w_high, w_low, universe):
    dates = month_end_rebalance_dates(close.index, start, end)
    monthly = close.resample("ME").last()
    weights_map = {}
    for d in dates:
        m = monthly.loc[:d]
        score = ranker(m)
        avail = [t for t in universe if t in score.index and pd.notna(score[t]) and pd.notna(close.loc[d].get(t, np.nan))]
        if not avail:
            weights_map[d] = {CASH: 1.0} if pd.notna(close.loc[d].get(CASH, np.nan)) else {}
            continue
        ranked = score.loc[avail].sort_values(ascending=False)
        half_n = max(2, (len(ranked) + 1) // 2)
        positive = ranked.iloc[:half_n][lambda s: s > 0]
        if len(positive) < 2:
            if len(positive) == 1:
                weights_map[d] = {positive.index[0]: 1.0}
            else:
                weights_map[d] = {CASH: 1.0} if pd.notna(close.loc[d].get(CASH, np.nan)) else {}
            continue
        candidates = list(positive.index)
        pair = lowest_corr_pair(close.loc[:d, candidates], candidates)
        if pair is None:
            weights_map[d] = {candidates[0]: 1.0}
            continue
        a, b = pair
        high, low = (a, b) if positive[a] >= positive[b] else (b, a)
        weights_map[d] = {high: w_high, low: w_low}
    return _segment_returns(close, weights_map, dates, end)


def run_triplet(close, ranker, w1, w2, w3, universe):
    dates = month_end_rebalance_dates(close.index, start, end)
    monthly = close.resample("ME").last()
    weights_map = {}
    for d in dates:
        m = monthly.loc[:d]
        score = ranker(m)
        avail = [t for t in universe if t in score.index and pd.notna(score[t]) and pd.notna(close.loc[d].get(t, np.nan))]
        if not avail:
            weights_map[d] = {CASH: 1.0} if pd.notna(close.loc[d].get(CASH, np.nan)) else {}
            continue
        ranked = score.loc[avail].sort_values(ascending=False)
        half_n = max(3, (len(ranked) + 1) // 2)
        positive = ranked.iloc[:half_n][lambda s: s > 0]
        if len(positive) < 3:
            if len(positive) == 0:
                weights_map[d] = {CASH: 1.0} if pd.notna(close.loc[d].get(CASH, np.nan)) else {}
            else:
                w = 1.0 / len(positive)
                weights_map[d] = {t: w for t in positive.index}
            continue
        candidates = list(positive.index)
        trip = lowest_corr_triplet(close.loc[:d, candidates], candidates)
        if trip is None:
            w = 1.0 / 3
            weights_map[d] = {t: w for t in candidates[:3]}
            continue
        srt = sorted(trip, key=lambda t: positive[t], reverse=True)
        weights_map[d] = {srt[0]: w1, srt[1]: w2, srt[2]: w3}
    return _segment_returns(close, weights_map, dates, end)


results = {}
for ranker_name, ranker_fn in RANKERS.items():
    for w_high, w_low in WEIGHT_SCHEMES:
        label = f"Pair_{ranker_name}_{int(w_high*100)}_{int(w_low*100)}"
        print(f"Running {label}...")
        results[label] = run_pair(close, ranker_fn, w_high, w_low, SECTOR_UNIV)
    for w1, w2, w3 in TRIPLET_WEIGHT_SCHEMES:
        label = f"Trip_{ranker_name}_{int(round(w1*100))}_{int(round(w2*100))}_{int(round(w3*100))}"
        print(f"Running {label}...")
        results[label] = run_triplet(close, ranker_fn, w1, w2, w3, SECTOR_UNIV)

print("Running TSMOM_12m_Sector...")
results["TSMOM_12m_Sector"] = run_tsmom(close, start, end, SECTOR_UNIV)["daily"]
print("Running SPY_BH...")
results["SPY_BH"] = run_spy_bh(close, start, end)["daily"]

aligned, equity = align_curves(results, 100_000.0)
summary = compute_summary(aligned, equity)
print()
print(f"Window: {aligned.index[0].date()} -> {aligned.index[-1].date()}")
print(summary.to_string(index=False, float_format=lambda x: f"{x:.4f}"))
summary.to_csv("/tmp/lowcorr_sector_summary.csv", index=False)
equity.to_csv("/tmp/lowcorr_sector_equity.csv")
