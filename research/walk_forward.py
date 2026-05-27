"""
Walk-forward / OOS validation for buffer x corr_lookback hyperparameter pair.

Two tests:
  A) Single split: 2001-2014 IS / 2014-2026 OOS
       - Pick best (buffer, corr_lookback) by IS Sharpe
       - Evaluate that config on OOS unseen
       - Compare to: default (1.0, 252), cherry-picked (3.0, 378)
  B) Expanding walk-forward (3y OOS slices)
       - Train on 2001-Y, test on Y+1..Y+3 (rolling)
       - Track which config wins IS, what its OOS Sharpe is
       - Aggregate across slices

Goal: do (3.0, 378) survive OOS, or was it in-sample fit?
"""
import sys
sys.path.insert(0, "/Users/rkautsar/personal/scripts/strategy_cpm")

import numpy as np
import pandas as pd
from itertools import combinations

PANEL_PATH = "/Users/rkautsar/personal/scripts/strategy_cpm/data/proxy_adjusted_close_daily.csv"
panel = pd.read_csv(PANEL_PATH, parse_dates=["Date"], index_col="Date").sort_index()
gld = pd.read_csv("/Users/rkautsar/personal/scripts/strategy_cpm/data/gld_stitched_daily_clean.csv", parse_dates=[0], index_col=0); gld.columns=["GLD"]
kmlm = pd.read_csv("/Users/rkautsar/personal/scripts/strategy_cpm/data/kmlm_stitched_daily.csv", parse_dates=[0], index_col=0); kmlm.columns=["KMLM_stitched"]
agg = pd.read_csv("/Users/rkautsar/personal/scripts/strategy_cpm/data/agg_stitched_daily.csv", parse_dates=[0], index_col=0); agg.columns=["AGG_stitched"]
tip_clean = pd.read_csv("/Users/rkautsar/personal/scripts/strategy_cpm/data/tip_stitched_daily.csv", parse_dates=[0], index_col=0); tip_clean.columns=["TIP_clean"]
panel = panel.join(gld, how="outer").join(kmlm, how="outer").join(agg, how="outer").join(tip_clean, how="outer").sort_index()
panel["TIP"] = panel["TIP_clean"]

CASH = "SHV"
SAFE_POOL = ["SHV", "IEF"]
AGGR_ALL = ["QQQ","IGM","SPMO","XLE","XRT","SMH","COWZ","AVUV","MOO","RWJ","SPHQ","XMMO","XMHQ"]
UNIVERSE = AGGR_ALL + ["GLD", "KMLM_stitched"]
CANARY_ASSETS = ["SPY", "TIP"]


def faber_sma_xs(monthly):
    if len(monthly) < 10: return pd.Series(np.nan, index=monthly.columns)
    sma = monthly.rolling(10).mean().iloc[-1]
    return (monthly.iloc[-1] - sma) / sma

def sig_13612W(p):
    p = p.dropna()
    if len(p) < 13: return np.nan
    last = p.iloc[-1]
    return (12*(last/p.iloc[-2]-1) + 4*(last/p.iloc[-4]-1) + 2*(last/p.iloc[-7]-1) + (last/p.iloc[-13]-1))/19.0

def lowest_corr_pair(daily, candidates, lookback):
    if len(candidates) < 2: return None
    rets = daily[candidates].iloc[-lookback:].pct_change().dropna(how="all")
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
    if pd.isna(sd) or sd == 0: return pd.Series(0.0, index=s.index)
    return (s - s.mean())/sd

def month_end_dates(idx, start, end):
    sub = idx[(idx>=start)&(idx<=end)]
    return pd.DataFrame({"x":1}, index=sub).groupby(pd.Grouper(freq="ME")).tail(1).index.to_list()

def best_safe(monthly, d):
    m = monthly.loc[:d]
    av = [s for s in SAFE_POOL if s in m.columns and m[s].first_valid_index() is not None]
    if not av: return CASH
    if len(m) < 10: return av[0]
    sma = m[av].rolling(10).mean().iloc[-1]; last = m[av].iloc[-1]
    dist = ((last-sma)/sma).dropna()
    return dist.idxmax() if not dist.empty else av[0]

def build_weights(close, monthly, dates, universe, buffer, corr_lookback):
    weights_map = {}
    prev_pair = None
    for d in dates:
        m = monthly.loc[:d]
        on = True
        for c in CANARY_ASSETS:
            if c in m.columns:
                s = sig_13612W(m[c])
                if pd.isna(s) or s <= 0: on = False; break
        safe = best_safe(monthly, d) or CASH
        if not on:
            weights_map[d] = {safe: 1.0}; prev_pair = None; continue
        score = faber_sma_xs(m)
        avail = [t for t in universe if t in score.index and pd.notna(score[t]) and pd.notna(close.loc[d].get(t, np.nan))]
        if not avail:
            weights_map[d] = {safe: 1.0}; prev_pair = None; continue
        sa = score.loc[avail]; za = zscore(sa)
        ranked = sa.sort_values(ascending=False)
        positive = ranked.iloc[:max(2,(len(ranked)+1)//2)][lambda s: s>0]
        if len(positive) < 2:
            if len(positive) == 1:
                weights_map[d] = {positive.index[0]: 0.5, safe: 0.5}
            else:
                weights_map[d] = {safe: 1.0}
            prev_pair = None; continue
        candidates = list(positive.index)
        new_pick = lowest_corr_pair(close.loc[:d, candidates], candidates, corr_lookback)
        if new_pick is None:
            weights_map[d] = {candidates[0]: 1.0}; prev_pair = None; continue
        if prev_pair is not None and buffer > 1e-9:
            new_set = list(new_pick)
            for prior in prev_pair:
                if prior in new_set or prior not in avail: continue
                if sa.get(prior, -np.inf) <= 0: continue
                z_prior = za.get(prior, np.nan)
                if pd.isna(z_prior): continue
                swap_cands = [x for x in new_set if x not in prev_pair]
                if not swap_cands: continue
                swap = min(swap_cands, key=lambda x: za.get(x, np.inf))
                z_swap = za.get(swap, np.nan)
                if pd.isna(z_swap): continue
                if z_swap - z_prior < buffer:
                    new_set.remove(swap); new_set.append(prior)
            new_pick = tuple(new_set[:2])
        weights_map[d] = {new_pick[0]: 0.5, new_pick[1]: 0.5}
        prev_pair = new_pick
    return weights_map

def segment_returns(close, weights_map, dates, end):
    daily = close.ffill().pct_change()
    period_idx = close.index[(close.index>=dates[0])&(close.index<=end)]
    out = pd.Series(0.0, index=period_idx)
    for i, d in enumerate(dates):
        nxt = dates[i+1] if i+1<len(dates) else end
        seg = period_idx[(period_idx>d)&(period_idx<=nxt)]
        if len(seg)==0: continue
        w = weights_map.get(d, {})
        if not w: continue
        cols = [c for c in w if c in daily.columns]
        if not cols: continue
        out.loc[seg] = daily.loc[seg, cols].mul(pd.Series({k:w[k] for k in cols}), axis=1).sum(axis=1, min_count=1).fillna(0.0)
    return out

def perf(daily, eq):
    if daily.empty: return {}
    days = (eq.index[-1]-eq.index[0]).days; yrs = days/365.25
    cagr = (eq.iloc[-1]/eq.iloc[0])**(1/yrs)-1 if yrs>0 else float("nan")
    vol = daily.std(ddof=0)*np.sqrt(252)
    sharpe = (daily.mean()*252)/vol if vol>0 else float("nan")
    rm = eq.cummax(); mdd = (eq/rm-1).min()
    return {"cagr": cagr, "vol": vol, "sharpe": sharpe, "max_drawdown": mdd}

def run_config(close, monthly, dates, end, universe, buffer, corr_lookback):
    wmap = build_weights(close, monthly, dates, universe, buffer, corr_lookback)
    daily = segment_returns(close, wmap, dates, end)
    eq = (1.0+daily).cumprod()*100_000.0
    return perf(daily, eq), daily

# Setup
cols = list(dict.fromkeys(UNIVERSE + SAFE_POOL + CANARY_ASSETS + [CASH]))
cols = [c for c in cols if c in panel.columns]
close = panel[cols]
monthly = close.resample("ME").last()

BUFFERS = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0]
CORR_LOOKBACKS = [120, 180, 252, 378, 504]


# ============================================================
# A) SINGLE SPLIT: 2001-08-30 -> 2014-12-31 IS / 2015-01-01 -> 2026-05-13 OOS
# ============================================================
print("="*80)
print("A) Single split: 2001-2014 IS / 2015-2026 OOS")
print("="*80)
is_start = pd.Timestamp("2001-08-30")
is_end = pd.Timestamp("2014-12-31")
oos_start = pd.Timestamp("2015-01-01")
oos_end = panel.index[-1]

# Run grid on IS
is_dates = month_end_dates(close.index, is_start, is_end)
is_results = []
for b in BUFFERS:
    for c in CORR_LOOKBACKS:
        m, _ = run_config(close, monthly, is_dates, is_end, UNIVERSE, b, c)
        m["buffer"] = b; m["corr_lookback"] = c
        is_results.append(m)
is_df = pd.DataFrame(is_results)
is_pivot = is_df.pivot(index="buffer", columns="corr_lookback", values="sharpe")
print("\nIS Sharpe (2001-2014):")
print(is_pivot.to_string(float_format=lambda x: f"{x:.4f}"))

# Pick best on IS
best_row = is_df.sort_values("sharpe", ascending=False).iloc[0]
best_b, best_c = best_row["buffer"], int(best_row["corr_lookback"])
print(f"\nBest IS config: buffer={best_b}, corr_lookback={best_c} (Sharpe={best_row['sharpe']:.4f})")

# Build the FULL window weights using fixed configs (so OOS uses same monthly history continuity)
full_dates = month_end_dates(close.index, is_start, oos_end)

# Three configs to compare
test_configs = [
    ("DEFAULT_(1.0_252)",  1.0, 252),
    ("BEST_IS",            best_b, best_c),
    ("CHERRY_(3.0_378)",   3.0, 378),
    ("CHERRY_(1.0_378)",   1.0, 378),
]

print(f"\nOOS evaluation 2015-2026:")
oos_rows = []
for name, b, c in test_configs:
    m_full, daily_full = run_config(close, monthly, full_dates, oos_end, UNIVERSE, b, c)
    # Slice the OOS window only
    oos_daily = daily_full.loc[oos_start:oos_end]
    oos_eq = (1.0+oos_daily).cumprod()*100_000.0
    oos_perf = perf(oos_daily, oos_eq)
    is_daily = daily_full.loc[is_start:is_end]
    is_eq = (1.0+is_daily).cumprod()*100_000.0
    is_perf = perf(is_daily, is_eq)
    oos_rows.append({
        "config": name,
        "buffer": b, "corr_lookback": c,
        "IS_sharpe": is_perf["sharpe"], "IS_cagr": is_perf["cagr"], "IS_mdd": is_perf["max_drawdown"],
        "OOS_sharpe": oos_perf["sharpe"], "OOS_cagr": oos_perf["cagr"], "OOS_mdd": oos_perf["max_drawdown"],
    })
oos_df = pd.DataFrame(oos_rows)
print(oos_df.to_string(index=False, float_format=lambda x: f"{x:.4f}"))


# ============================================================
# B) Expanding walk-forward, 3-year OOS slices
# ============================================================
print("\n" + "="*80)
print("B) Expanding walk-forward (5y warmup, 3y OOS slices)")
print("="*80)
years = list(range(2009, 2024, 3))  # OOS-start years: 2009,2012,2015,2018,2021
slice_results = []
for yr in years:
    is_end_dt = pd.Timestamp(f"{yr}-01-01") - pd.Timedelta(days=1)
    oos_start_dt = pd.Timestamp(f"{yr}-01-01")
    oos_end_dt = min(pd.Timestamp(f"{yr+3}-01-01") - pd.Timedelta(days=1), panel.index[-1])
    if oos_end_dt <= oos_start_dt: continue
    
    # IS sweep
    is_dates_slice = month_end_dates(close.index, is_start, is_end_dt)
    is_grid = []
    for b in BUFFERS:
        for c in CORR_LOOKBACKS:
            m, _ = run_config(close, monthly, is_dates_slice, is_end_dt, UNIVERSE, b, c)
            is_grid.append({"buffer":b, "corr_lookback":c, "sharpe":m["sharpe"]})
    is_grid_df = pd.DataFrame(is_grid)
    best = is_grid_df.sort_values("sharpe", ascending=False).iloc[0]
    
    # Run full window with each config, then slice OOS
    full_dates = month_end_dates(close.index, is_start, oos_end_dt)
    
    def oos_perf_for(b, c):
        _, daily_full = run_config(close, monthly, full_dates, oos_end_dt, UNIVERSE, b, c)
        oos_daily = daily_full.loc[oos_start_dt:oos_end_dt]
        if oos_daily.empty: return {}
        oos_eq = (1.0+oos_daily).cumprod()*100_000.0
        return perf(oos_daily, oos_eq)
    
    oos_best = oos_perf_for(best["buffer"], int(best["corr_lookback"]))
    oos_default = oos_perf_for(1.0, 252)
    oos_cherry = oos_perf_for(3.0, 378)
    
    slice_results.append({
        "OOS_window": f"{oos_start_dt.year}-{oos_end_dt.year}",
        "best_IS_buf": best["buffer"], "best_IS_lookback": int(best["corr_lookback"]),
        "best_IS_Sharpe": best["sharpe"],
        "OOS_BEST_IS_sharpe": oos_best.get("sharpe", float("nan")),
        "OOS_DEFAULT_sharpe": oos_default.get("sharpe", float("nan")),
        "OOS_CHERRY_sharpe": oos_cherry.get("sharpe", float("nan")),
    })

wf_df = pd.DataFrame(slice_results)
print()
print(wf_df.to_string(index=False, float_format=lambda x: f"{x:.4f}"))

# Aggregate
print()
print("Aggregate OOS Sharpe across slices:")
print(f"  BEST_IS  (re-pick each slice): mean={wf_df['OOS_BEST_IS_sharpe'].mean():.4f}, median={wf_df['OOS_BEST_IS_sharpe'].median():.4f}")
print(f"  DEFAULT  (1.0, 252):           mean={wf_df['OOS_DEFAULT_sharpe'].mean():.4f}, median={wf_df['OOS_DEFAULT_sharpe'].median():.4f}")
print(f"  CHERRY   (3.0, 378):           mean={wf_df['OOS_CHERRY_sharpe'].mean():.4f}, median={wf_df['OOS_CHERRY_sharpe'].median():.4f}")

oos_df.to_csv("/tmp/walk_forward_single.csv", index=False)
wf_df.to_csv("/tmp/walk_forward_expanding.csv", index=False)
