"""
Pair_MSMAdist_50_50 with hold buffer (AGGR-style churn dampening).

Hold-buffer logic:
  - Compute new lowest-corr pair as before.
  - For each prior holding NOT in new pair: if it still has positive momentum
    AND its z-score is within `buffer` of the new pair's lowest-z member, keep it
    (swap out that new member, swap in the prior).
  - Buffer in cross-sectional z-score units (matches AGGR convention).
  - buffer = 0.0 disables (= original strategy).

Sweep: buffer in {0.0, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0}.
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
CORR_LOOKBACK_DAYS = 252

start = pd.Timestamp("2008-01-01")
end = pd.Timestamp.today().normalize()
tickers = sorted(set(UNIVERSE + SAFE_ASSETS + ["SPY"]))
download_start = start - pd.DateOffset(years=5)
print(f"Downloading {len(tickers)} tickers...")
close = download_prices(tickers=tickers, start=download_start, end=end, cache_path="/tmp/yfinance_aggr_cache")


def faber_sma(monthly):
    if len(monthly) < 10:
        return pd.Series(np.nan, index=monthly.columns)
    sma = monthly.rolling(10).mean().iloc[-1]
    return (monthly.iloc[-1] - sma) / sma


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


def zscore(s: pd.Series) -> pd.Series:
    sd = s.std()
    if pd.isna(sd) or sd == 0:
        return pd.Series(0.0, index=s.index)
    return (s - s.mean()) / sd


def run_pair_with_buffer(close, ranker, universe, buffer: float):
    dates = month_end_rebalance_dates(close.index, start, end)
    monthly = close.resample("ME").last()
    weights_map = {}
    prev_pair: tuple[str, str] | None = None
    n_kept = 0   # diagnostics: count of months where buffer kept a prior name
    n_total = 0

    for d in dates:
        m = monthly.loc[:d]
        score = ranker(m)
        avail = [t for t in universe if t in score.index and pd.notna(score[t]) and pd.notna(close.loc[d].get(t, np.nan))]
        if not avail:
            weights_map[d] = {CASH: 1.0} if pd.notna(close.loc[d].get(CASH, np.nan)) else {}
            prev_pair = None
            continue

        score_avail = score.loc[avail]
        z_avail = zscore(score_avail)

        ranked = score_avail.sort_values(ascending=False)
        half_n = max(2, (len(ranked) + 1) // 2)
        positive = ranked.iloc[:half_n][lambda s: s > 0]

        if len(positive) < 2:
            if len(positive) == 1:
                weights_map[d] = {positive.index[0]: 1.0}
                prev_pair = None
            else:
                weights_map[d] = {CASH: 1.0} if pd.notna(close.loc[d].get(CASH, np.nan)) else {}
                prev_pair = None
            continue

        candidates = list(positive.index)
        new_pair = lowest_corr_pair(close.loc[:d, candidates], candidates)
        if new_pair is None:
            weights_map[d] = {candidates[0]: 1.0}
            prev_pair = (candidates[0], candidates[0])
            continue

        # Apply hold-buffer
        if prev_pair is not None and buffer > 1e-9:
            n_total += 1
            new_set = list(new_pair)
            # Consider each prior member that's no longer in new pair
            for prior in prev_pair:
                if prior in new_set:
                    continue
                if prior not in avail:
                    continue
                if score_avail.get(prior, -np.inf) <= 0:
                    continue
                # Find the new_pair member with the lowest z (most likely "swap target")
                # Skip if the prior is identical to other prev member
                z_prior = z_avail.get(prior, np.nan)
                if pd.isna(z_prior):
                    continue
                # find swap candidate: the one in new_set with lowest z_avail and not also a prior member
                swap_candidates = [x for x in new_set if x not in prev_pair]
                if not swap_candidates:
                    continue
                swap_target = min(swap_candidates, key=lambda x: z_avail.get(x, np.inf))
                z_swap = z_avail.get(swap_target, np.nan)
                if pd.isna(z_swap):
                    continue
                # Keep prior if new entrant doesn't exceed by `buffer` z-units
                if z_swap - z_prior < buffer:
                    new_set.remove(swap_target)
                    new_set.append(prior)
                    n_kept += 1
            new_pair = tuple(new_set[:2])

        weights_map[d] = {new_pair[0]: 0.5, new_pair[1]: 0.5}
        prev_pair = new_pair

    daily = _segment_returns(close, weights_map, dates, end)
    return daily, n_kept, n_total, weights_map


buffers = [0.0, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0]
results = {}
diags = {}
for b in buffers:
    label = f"PairMSMAd_buf{b:.2f}"
    print(f"Running {label}...")
    daily, n_kept, n_total, _ = run_pair_with_buffer(close, faber_sma, UNIVERSE, b)
    results[label] = daily
    diags[label] = (n_kept, n_total)

print("Running TSMOM_12m..."); results["TSMOM_12m"] = run_tsmom(close, start, end, UNIVERSE)["daily"]
print("Running SPY_BH..."); results["SPY_BH"] = run_spy_bh(close, start, end)["daily"]

aligned, equity = align_curves(results, 100_000.0)
summary = compute_summary(aligned, equity)
print()
print(f"Window: {aligned.index[0].date()} -> {aligned.index[-1].date()}")
print(summary.to_string(index=False, float_format=lambda x: f"{x:.4f}"))
print()
print("Diagnostics (months where buffer kept a prior name / total months with prev_pair):")
for label, (k, n) in diags.items():
    pct = 100.0 * k / n if n else 0
    print(f"  {label}: {k}/{n}  ({pct:.1f}%)")

# Turnover proxy: count of distinct holdings change per month
def turnover(daily_pair_weights_history):
    pass  # left out; diagnostics above suffice

summary.to_csv("/tmp/pair_holdbuffer_summary.csv", index=False)
equity.to_csv("/tmp/pair_holdbuffer_equity.csv")
