"""
Pair_MSMAdist_50_50 + hold_buffer=1.0 across multiple universes.

Universes:
  1. AGGR_orig             — original 13 factor ETFs (baseline)
  2. AGGR_plus_GLD         — + GLD (gold diversifier)
  3. AGGR_plus_GLD_TLT     — + GLD + TLT (gold + long bonds)
  4. AGGR_plus_diversifiers — + GLD, DBC, TLT, VNQ, EEM (full diversifier suite)
  5. AGGR_plus_MF          — + WTMF (managed futures, post-2011)
  6. Keller_DAA_G12        — SPY, IWM, QQQ, VGK, EWJ, EEM, VNQ, DBC, GLD, TLT, HYG, LQD
  7. Keller_VAA_G4         — SPY, EFA, EEM, AGG (Antonacci/Keller GEM-style)
  8. Keller_HAA_off        — SPY, IWM, VEA, VWO, VNQ, DBC, IEF, TLT
  9. Faber_IVY_5           — SPY, EFA, IEF, VNQ, DBC
 10. Faber_IVY_13          — extended IVY universe

All use Pair_MSMAdist_50_50 + hold_buffer=1.0, same code.
Each universe runs from max(2008-01-01, latest_ticker_inception + 1y warmup).
"""
import sys
sys.path.insert(0, "/Users/rkautsar/personal/scripts/strategy_cam")

import numpy as np
import pandas as pd
from itertools import combinations
from aggr_core import AGGRESSIVE_TICKERS, SAFE_ASSETS, download_prices, month_end_rebalance_dates, perf_metrics
from aggr_benchmark import _segment_returns

CASH = "SHV"
CORR_LOOKBACK_DAYS = 252
HOLD_BUFFER = 1.0

UNIVERSES = {
    "AGGR_orig":              AGGRESSIVE_TICKERS,
    "AGGR_plus_GLD":          AGGRESSIVE_TICKERS + ["GLD"],
    "AGGR_plus_GLD_TLT":      AGGRESSIVE_TICKERS + ["GLD", "TLT"],
    "AGGR_plus_diversifiers": AGGRESSIVE_TICKERS + ["GLD", "DBC", "TLT", "VNQ", "EEM"],
    "AGGR_plus_MF":           AGGRESSIVE_TICKERS + ["WTMF"],   # WTMF inception 2011-01
    "Keller_DAA_G12":         ["SPY","IWM","QQQ","VGK","EWJ","EEM","VNQ","DBC","GLD","TLT","HYG","LQD"],
    "Keller_VAA_G4":          ["SPY","EFA","EEM","AGG"],
    "Keller_HAA_off":         ["SPY","IWM","VEA","VWO","VNQ","DBC","IEF","TLT"],
    "Faber_IVY_5":            ["SPY","EFA","IEF","VNQ","DBC"],
    "Faber_IVY_13":           ["SPY","IWM","EFA","EEM","VNQ","DBC","GLD","IEF","TLT","LQD","HYG","XLE","XLU"],
}

# Collect all unique tickers
all_tickers = set([CASH, "SPY"])
for u in UNIVERSES.values():
    all_tickers.update(u)
all_tickers = sorted(all_tickers)

end = pd.Timestamp.today().normalize()
download_start = pd.Timestamp("2003-01-01")
print(f"Downloading {len(all_tickers)} tickers: {all_tickers}")
close = download_prices(tickers=all_tickers, start=download_start, end=end, cache_path="/tmp/yfinance_aggr_cache")


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


def zscore(s):
    sd = s.std()
    if pd.isna(sd) or sd == 0:
        return pd.Series(0.0, index=s.index)
    return (s - s.mean()) / sd


def run_pair(close, universe, start, end, buffer=HOLD_BUFFER):
    dates = month_end_rebalance_dates(close.index, start, end)
    monthly = close.resample("ME").last()
    weights_map = {}
    prev_pair = None
    for d in dates:
        m = monthly.loc[:d]
        score = faber_sma(m)
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
            else:
                weights_map[d] = {CASH: 1.0} if pd.notna(close.loc[d].get(CASH, np.nan)) else {}
            prev_pair = None
            continue
        candidates = list(positive.index)
        new_pair = lowest_corr_pair(close.loc[:d, candidates], candidates)
        if new_pair is None:
            weights_map[d] = {candidates[0]: 1.0}
            prev_pair = None
            continue
        # hold buffer
        if prev_pair is not None and buffer > 1e-9:
            new_set = list(new_pair)
            for prior in prev_pair:
                if prior in new_set or prior not in avail:
                    continue
                if score_avail.get(prior, -np.inf) <= 0:
                    continue
                z_prior = z_avail.get(prior, np.nan)
                if pd.isna(z_prior):
                    continue
                swap_candidates = [x for x in new_set if x not in prev_pair]
                if not swap_candidates:
                    continue
                swap_target = min(swap_candidates, key=lambda x: z_avail.get(x, np.inf))
                z_swap = z_avail.get(swap_target, np.nan)
                if pd.isna(z_swap):
                    continue
                if z_swap - z_prior < buffer:
                    new_set.remove(swap_target)
                    new_set.append(prior)
            new_pair = tuple(new_set[:2])
        weights_map[d] = {new_pair[0]: 0.5, new_pair[1]: 0.5}
        prev_pair = new_pair
    return _segment_returns(close, weights_map, dates, end), weights_map


def first_full_history(close, universe):
    """First date all required tickers have data. Fall back to oldest available + 1y warmup."""
    sub = close[universe]
    first_valid = sub.apply(lambda c: c.first_valid_index())
    # Use the most recent first-valid date among universe members + 12-month warmup for momentum/SMA
    latest = first_valid.max()
    return latest + pd.DateOffset(months=12)


# Run all universes from common 2008-01 start, then again from per-universe earliest valid start
common_start = pd.Timestamp("2008-01-01")
print()
print("=" * 80)
print(f"Run 1: All universes from common start {common_start.date()} -> {end.date()}")
print("=" * 80)
common_results = {}
weights_history = {}  # for pick-frequency analysis
for name, univ in UNIVERSES.items():
    print(f"  {name} ({len(univ)} tickers)...", end=" ")
    try:
        missing = [t for t in univ if t not in close.columns]
        if missing:
            print(f"SKIP — missing tickers {missing}")
            continue
        earliest = first_full_history(close, univ)
        start_use = max(common_start, earliest)
        if start_use >= end:
            print("SKIP — no data window")
            continue
        daily, wmap = run_pair(close, univ, start_use, end)
        common_results[name] = daily
        weights_history[name] = wmap
        if start_use > common_start:
            print(f"OK (start {start_use.date()})")
        else:
            print("OK")
    except Exception as e:
        print(f"FAIL: {e}")

# Build summary aligning each strategy to its own equity curve
rows = []
for name, daily in common_results.items():
    if daily.empty:
        continue
    eq = (1.0 + daily).cumprod() * 100_000.0
    m = perf_metrics(daily, eq)
    m["strategy"] = name
    m["start"] = daily.index[0].date().isoformat()
    m["end"] = daily.index[-1].date().isoformat()
    m["years"] = (daily.index[-1] - daily.index[0]).days / 365.25
    rows.append(m)
summary = pd.DataFrame(rows)[["strategy","start","end","years","total_return","cagr","vol","sharpe","max_drawdown"]]
summary = summary.sort_values("sharpe", ascending=False).reset_index(drop=True)
print()
print(summary.to_string(index=False, float_format=lambda x: f"{x:.4f}"))
summary.to_csv("/tmp/universe_sweep_summary.csv", index=False)


# Apples-to-apples: align all to LATEST common start (= max of all per-universe earliest)
aligned_start = max(daily.index[0] for daily in common_results.values())
print()
print("=" * 80)
print(f"Run 2: All universes aligned to {aligned_start.date()} -> {end.date()} (apples-to-apples)")
print("=" * 80)

aligned_rows = []
aligned_dailies = {}
for name, daily in common_results.items():
    sub = daily.loc[daily.index >= aligned_start]
    if sub.empty:
        continue
    eq = (1.0 + sub).cumprod() * 100_000.0
    m = perf_metrics(sub, eq)
    m["strategy"] = name
    aligned_rows.append(m)
    aligned_dailies[name] = sub
aligned_summary = pd.DataFrame(aligned_rows)[["strategy","total_return","cagr","vol","sharpe","max_drawdown"]]
aligned_summary = aligned_summary.sort_values("sharpe", ascending=False).reset_index(drop=True)
print(aligned_summary.to_string(index=False, float_format=lambda x: f"{x:.4f}"))
aligned_summary.to_csv("/tmp/universe_sweep_aligned.csv", index=False)
print()
print(f"Aligned window: {aligned_start.date()} -> {end.date()}  ({(end-aligned_start).days/365.25:.1f}y)")


# ---- Pick-frequency analysis ----
print()
print("=" * 80)
print("Pick frequency per universe (% of months a ticker held nonzero weight)")
print("=" * 80)
all_freq_rows = []
for name, wmap in weights_history.items():
    total = len(wmap)
    if total == 0:
        continue
    counts = {}
    for d, w in wmap.items():
        for t in w:
            counts[t] = counts.get(t, 0) + 1
    freq = pd.Series({t: counts[t] / total * 100.0 for t in counts}).sort_values(ascending=False)
    print(f"\n{name} ({total} months):")
    for t, pct in freq.items():
        bar = "#" * int(pct / 2)
        print(f"  {t:6s} {pct:5.1f}%  {bar}")
    for t, pct in freq.items():
        all_freq_rows.append({"universe": name, "ticker": t, "pick_pct": pct, "months": total})

pd.DataFrame(all_freq_rows).to_csv("/tmp/universe_sweep_freq.csv", index=False)

# Highlight: rarely-picked names = candidates to drop
print()
print("=" * 80)
print("Rarely-picked (<5% of months) candidates to drop:")
print("=" * 80)
for name, wmap in weights_history.items():
    total = len(wmap)
    if total == 0:
        continue
    counts = {}
    for d, w in wmap.items():
        for t in w:
            counts[t] = counts.get(t, 0) + 1
    rarely = []
    for t in UNIVERSES[name]:
        pct = counts.get(t, 0) / total * 100.0
        if pct < 5.0:
            rarely.append((t, pct))
    if rarely:
        rarely_str = ", ".join(f"{t}({p:.1f}%)" for t, p in rarely)
        print(f"  {name}: {rarely_str}")
