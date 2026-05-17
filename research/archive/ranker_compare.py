"""
Pair_50_50 with different momentum ranker functions on AGGR universe.

Rankers:
  - Faber_avg:    avg(r3, r6, r12)               [Faber 2007 ETF Rotation]
  - Faber_SMA:    distance above 10-month SMA    [Faber 2007 trend filter]
  - Keller_13612W: (12*r1 + 4*r3 + 2*r6 + r12)/19 [Keller VAA/DAA, equal-monthly weight]
  - Keller_13612U: avg(r1, r3, r6, r12)          [Keller unweighted variant]
  - AGG_MOM:      z( r12_1 + 2*r2_1 - r1_12 )    [user's formula]
  - M12, M12_1, M6: simple baselines
"""
import sys
sys.path.insert(0, "/Users/rkautsar/personal/scripts/strategy_cam")

import numpy as np
import pandas as pd
from itertools import combinations
from aggr_core import AGGRESSIVE_TICKERS, SAFE_ASSETS, download_prices, month_end_rebalance_dates, r as agg_r, z as agg_z
from aggr_benchmark import _segment_returns, align_curves, compute_summary, run_spy_bh, run_tsmom

UNIVERSE = AGGRESSIVE_TICKERS
CASH = "SHV"
CORR_LOOKBACK_DAYS = 252

start = pd.Timestamp("2008-01-01")
end = pd.Timestamp.today().normalize()
tickers = sorted(set(UNIVERSE + SAFE_ASSETS + ["SPY"]))
download_start = start - pd.DateOffset(years=5)
print(f"Downloading {len(tickers)} tickers...")
close = download_prices(tickers=tickers, start=download_start, end=end, cache_path="/tmp/yfinance_aggr_cache")


# ---- ranker functions ----
def _ret(monthly, periods, lag=0):
    if len(monthly) < periods + lag + 1:
        return pd.Series(np.nan, index=monthly.columns)
    return monthly.iloc[-1 - lag] / monthly.iloc[-periods - 1 - lag] - 1.0

def faber_avg(monthly):
    if len(monthly) < 13: return pd.Series(np.nan, index=monthly.columns)
    r3 = _ret(monthly, 3); r6 = _ret(monthly, 6); r12 = _ret(monthly, 12)
    return (r3 + r6 + r12) / 3.0

def faber_sma(monthly):
    if len(monthly) < 10: return pd.Series(np.nan, index=monthly.columns)
    sma = monthly.rolling(10).mean().iloc[-1]
    return (monthly.iloc[-1] - sma) / sma

def keller_13612W(monthly):
    """Keller's VAA/DAA momentum: weighted by 12/N to give equal monthly weight.
       Score = (12*r1 + 4*r3 + 2*r6 + 1*r12) / 19  (often expressed unnormalized)
    """
    if len(monthly) < 13: return pd.Series(np.nan, index=monthly.columns)
    r1 = _ret(monthly, 1); r3 = _ret(monthly, 3)
    r6 = _ret(monthly, 6); r12 = _ret(monthly, 12)
    return (12.0 * r1 + 4.0 * r3 + 2.0 * r6 + 1.0 * r12) / 19.0

def keller_13612U(monthly):
    """Unweighted average of 1/3/6/12m returns."""
    if len(monthly) < 13: return pd.Series(np.nan, index=monthly.columns)
    r1 = _ret(monthly, 1); r3 = _ret(monthly, 3)
    r6 = _ret(monthly, 6); r12 = _ret(monthly, 12)
    return (r1 + r3 + r6 + r12) / 4.0

def agg_mom_user(monthly):
    """User's AGG_MOM: z( r(12,1) + 2*r(2,1) - r(1,12) )."""
    if len(monthly) < 14: return pd.Series(np.nan, index=monthly.columns)
    try:
        return agg_z(agg_r(monthly, 12, 1) + 2 * agg_r(monthly, 2, 1) - agg_r(monthly, 1, 12))
    except Exception:
        return pd.Series(np.nan, index=monthly.columns)

def m12(monthly):
    return _ret(monthly, 12)

def m12_1(monthly):
    if len(monthly) < 14: return pd.Series(np.nan, index=monthly.columns)
    return _ret(monthly, 12, lag=1)

def m6(monthly):
    return _ret(monthly, 6)


RANKERS = {
    "Faber_avg":     faber_avg,
    "Faber_SMA":     faber_sma,
    "Keller_13612W": keller_13612W,
    "Keller_13612U": keller_13612U,
    "AGG_MOM_user":  agg_mom_user,
    "M12":           m12,
    "M12_1":         m12_1,
    "M6":            m6,
}


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


def run_pair_50_50(close, ranker, universe):
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
        weights_map[d] = {pair[0]: 0.5, pair[1]: 0.5}
    return _segment_returns(close, weights_map, dates, end)


results = {}
for name, fn in RANKERS.items():
    label = f"Pair5050_{name}"
    print(f"Running {label}...")
    results[label] = run_pair_50_50(close, fn, UNIVERSE)

print("Running TSMOM_12m..."); results["TSMOM_12m"] = run_tsmom(close, start, end, UNIVERSE)["daily"]
print("Running SPY_BH..."); results["SPY_BH"] = run_spy_bh(close, start, end)["daily"]

aligned, equity = align_curves(results, 100_000.0)
summary = compute_summary(aligned, equity)
print()
print(f"Window: {aligned.index[0].date()} -> {aligned.index[-1].date()}")
print(summary.to_string(index=False, float_format=lambda x: f"{x:.4f}"))
summary.to_csv("/tmp/ranker_compare_summary.csv", index=False)
equity.to_csv("/tmp/ranker_compare_equity.csv")
