"""
Pair-momentum strategy:
  1. Rank universe by momentum
  2. Take top half
  3. Drop negative-momentum names
  4. From survivors, pick pair with lowest 12m return correlation
  5. Weight pair 70/30, 60/40, 50/50 (heavy on higher momentum)

Sweep momentum-ranker function. Compare to AGGR + best TSMOM.
"""
import sys
sys.path.insert(0, "/Users/rkautsar/personal/scripts/strategy_cam")

import numpy as np
import pandas as pd
from itertools import combinations
from aggr_core import AGGRESSIVE_TICKERS, SAFE_ASSETS, download_prices, month_end_rebalance_dates
from aggr_benchmark import _segment_returns, align_curves, compute_summary, run_spy_bh, run_tsmom

UNIVERSE = AGGRESSIVE_TICKERS
CASH = "SHV"
CORR_LOOKBACK_DAYS = 252  # 12m

start = pd.Timestamp("2008-01-01")
end = pd.Timestamp.today().normalize()
tickers = sorted(set(UNIVERSE + SAFE_ASSETS + ["SPY"]))
download_start = start - pd.DateOffset(years=5)
print(f"Downloading {len(tickers)} tickers...")
close = download_prices(tickers=tickers, start=download_start, end=end, cache_path="/tmp/yfinance_aggr_cache")


# ---- momentum rankers (return Series scoring each asset; higher = better) ----
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
    """Distance above 10-month SMA, normalized (% above SMA). Higher = stronger trend."""
    if len(monthly) < 10: return pd.Series(np.nan, index=monthly.columns)
    sma = monthly.rolling(10).mean().iloc[-1]
    return (monthly.iloc[-1] - sma) / sma

def mom_multi_avg(monthly):
    """Average of 3/6/12m returns."""
    if len(monthly) < 13: return pd.Series(np.nan, index=monthly.columns)
    r3 = monthly.iloc[-1] / monthly.iloc[-4] - 1.0
    r6 = monthly.iloc[-1] / monthly.iloc[-7] - 1.0
    r12 = monthly.iloc[-1] / monthly.iloc[-13] - 1.0
    return (r3 + r6 + r12) / 3.0

RANKERS = {
    "M12_1":    mom_12_1,
    "M12":      mom_12m,
    "M6":       mom_6m,
    "MSMAdist": mom_sma10m_dist,
    "MMulti":   mom_multi_avg,
}

WEIGHT_SCHEMES = [(0.50, 0.50), (0.60, 0.40), (0.70, 0.30)]
TRIPLET_WEIGHT_SCHEMES = [
    (1/3, 1/3, 1/3),  # equal
    (0.50, 0.30, 0.20),
    (0.40, 0.35, 0.25),
    (0.60, 0.25, 0.15),
]


def lowest_corr_pair(daily_close: pd.DataFrame, candidates: list[str], lookback_days: int = CORR_LOOKBACK_DAYS) -> tuple[str, str] | None:
    if len(candidates) < 2:
        return None
    sub = daily_close[candidates].iloc[-lookback_days:]
    rets = sub.pct_change().dropna(how="all")
    if len(rets) < 30:
        return None
    corr = rets.corr()
    best_pair = None
    best_val = float("inf")
    for a, b in combinations(candidates, 2):
        c = corr.loc[a, b]
        if pd.notna(c) and c < best_val:
            best_val = c
            best_pair = (a, b)
    return best_pair


def lowest_corr_triplet(daily_close: pd.DataFrame, candidates: list[str], lookback_days: int = CORR_LOOKBACK_DAYS) -> tuple[str, str, str] | None:
    """Pick triplet with lowest average pairwise correlation."""
    if len(candidates) < 3:
        return None
    sub = daily_close[candidates].iloc[-lookback_days:]
    rets = sub.pct_change().dropna(how="all")
    if len(rets) < 30:
        return None
    corr = rets.corr()
    best_trip = None
    best_val = float("inf")
    for a, b, c in combinations(candidates, 3):
        avg_corr = (corr.loc[a, b] + corr.loc[a, c] + corr.loc[b, c]) / 3.0
        if pd.notna(avg_corr) and avg_corr < best_val:
            best_val = avg_corr
            best_trip = (a, b, c)
    return best_trip


def run_pair_strategy(close: pd.DataFrame, ranker, w_high: float, w_low: float, universe: list[str]) -> pd.Series:
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
        # Top half (round up so small universes still work)
        half_n = max(2, (len(ranked) + 1) // 2)
        top_half = ranked.iloc[:half_n]
        # Drop negative momentum
        positive = top_half[top_half > 0]
        if len(positive) < 2:
            # Fall back to cash if can't form pair
            if len(positive) == 1:
                weights_map[d] = {positive.index[0]: 1.0}
            else:
                weights_map[d] = {CASH: 1.0} if pd.notna(close.loc[d].get(CASH, np.nan)) else {}
            continue
        candidates = list(positive.index)
        # Pick pair with lowest 12m return correlation
        daily_window = close.loc[:d, candidates]
        pair = lowest_corr_pair(daily_window, candidates, lookback_days=CORR_LOOKBACK_DAYS)
        if pair is None:
            weights_map[d] = {candidates[0]: 1.0}
            continue
        # Sort pair so higher momentum gets w_high
        a, b = pair
        if positive[a] >= positive[b]:
            high, low = a, b
        else:
            high, low = b, a
        weights_map[d] = {high: w_high, low: w_low}
    return _segment_returns(close, weights_map, dates, end)


def run_triplet_strategy(close: pd.DataFrame, ranker, w1: float, w2: float, w3: float, universe: list[str]) -> pd.Series:
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
        top_half = ranked.iloc[:half_n]
        positive = top_half[top_half > 0]
        if len(positive) < 3:
            # fallback: use whatever positive names exist (1 or 2 holdings, equal weight)
            if len(positive) == 0:
                weights_map[d] = {CASH: 1.0} if pd.notna(close.loc[d].get(CASH, np.nan)) else {}
            else:
                w = 1.0 / len(positive)
                weights_map[d] = {t: w for t in positive.index}
            continue
        candidates = list(positive.index)
        daily_window = close.loc[:d, candidates]
        trip = lowest_corr_triplet(daily_window, candidates, lookback_days=CORR_LOOKBACK_DAYS)
        if trip is None:
            w = 1.0 / len(candidates[:3])
            weights_map[d] = {t: w for t in candidates[:3]}
            continue
        # Sort triplet by momentum desc, assign w1>=w2>=w3
        trip_sorted = sorted(trip, key=lambda t: positive[t], reverse=True)
        weights_map[d] = {trip_sorted[0]: w1, trip_sorted[1]: w2, trip_sorted[2]: w3}
    return _segment_returns(close, weights_map, dates, end)


results = {}
for ranker_name, ranker_fn in RANKERS.items():
    for w_high, w_low in WEIGHT_SCHEMES:
        label = f"Pair_{ranker_name}_{int(w_high*100)}_{int(w_low*100)}"
        print(f"Running {label}...")
        results[label] = run_pair_strategy(close, ranker_fn, w_high, w_low, UNIVERSE)
    for w1, w2, w3 in TRIPLET_WEIGHT_SCHEMES:
        label = f"Trip_{ranker_name}_{int(round(w1*100))}_{int(round(w2*100))}_{int(round(w3*100))}"
        print(f"Running {label}...")
        results[label] = run_triplet_strategy(close, ranker_fn, w1, w2, w3, UNIVERSE)

# benchmarks
print("Running TSMOM_12m...")
results["TSMOM_12m"] = run_tsmom(close, start, end, UNIVERSE)["daily"]
print("Running SPY_BH...")
results["SPY_BH"] = run_spy_bh(close, start, end)["daily"]

aligned, equity = align_curves(results, 100_000.0)
summary = compute_summary(aligned, equity)
print()
print(f"Window: {aligned.index[0].date()} -> {aligned.index[-1].date()}")
print(summary.to_string(index=False, float_format=lambda x: f"{x:.4f}"))
summary.to_csv("/tmp/lowcorr_pair_summary.csv", index=False)
equity.to_csv("/tmp/lowcorr_pair_equity.csv")

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(12, 7))
    # plot top 5 by sharpe + benchmarks
    top_curves = summary.head(5)["strategy"].tolist() + ["TSMOM_12m", "SPY_BH"]
    for col in equity.columns:
        if col in top_curves:
            lw = 1.5 if col not in ("TSMOM_12m", "SPY_BH") else 1.0
            ls = "-" if col not in ("TSMOM_12m", "SPY_BH") else "--"
            ax.plot(equity.index, equity[col], label=col, linewidth=lw, linestyle=ls)
    ax.set_yscale("log")
    ax.set_title(f"Pair-momentum + low-corr filter ({equity.index[0].date()}–{equity.index[-1].date()})")
    ax.legend(fontsize=9, loc="upper left")
    ax.grid(True, which="both", alpha=0.3)
    fig.tight_layout()
    fig.savefig("/tmp/lowcorr_pair_equity.png", dpi=120)
    print("Wrote /tmp/lowcorr_pair_equity.png")
except Exception as e:
    print(f"Plot skipped: {e}")
