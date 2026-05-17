"""
Refinement tests on OUR_STACK (cherry: buffer=3.0, corr_lookback=378):
  #5 Rebalance frequency (monthly default, bi-weekly, quarterly)
  #6 Execution lag (signal-day vs +1d, +1w)
  #7 Vol-targeting overlay (target 10%, 12%, 15%)
  #8 Best-safe pool expansion (add BIL, SHY)
"""
import sys
sys.path.insert(0, "/Users/rkautsar/personal/scripts/strategy_cam")

import numpy as np
import pandas as pd
import yfinance as yf
from itertools import combinations

PANEL_PATH = "/Users/rkautsar/personal/scripts/artifacts/cpa-1997-exact-core-proxy-research/proxy_adjusted_close_daily.csv"
panel = pd.read_csv(PANEL_PATH, parse_dates=["Date"], index_col="Date").sort_index()
gld = pd.read_csv("/tmp/gld_stitched_daily_clean.csv", parse_dates=[0], index_col=0); gld.columns=["GLD"]
kmlm = pd.read_csv("/tmp/kmlm_stitched_daily.csv", parse_dates=[0], index_col=0); kmlm.columns=["KMLM_stitched"]
agg = pd.read_csv("/tmp/agg_stitched_daily.csv", parse_dates=[0], index_col=0); agg.columns=["AGG_stitched"]
tip_clean = pd.read_csv("/tmp/tip_stitched_daily.csv", parse_dates=[0], index_col=0); tip_clean.columns=["TIP_clean"]
panel = panel.join(gld, how="outer").join(kmlm, how="outer").join(agg, how="outer").join(tip_clean, how="outer").sort_index()
panel["TIP"] = panel["TIP_clean"]

# Fetch BIL and SHY for #8
print("Fetching BIL, SHY for safe-pool expansion...")
for t in ["BIL","SHY"]:
    if t not in panel.columns:
        try:
            d = yf.download(t, start="2000-01-01", end="2026-05-14", auto_adjust=True, progress=False, threads=False)
            if isinstance(d.columns, pd.MultiIndex):
                d = d["Close"]
            c = d["Close"] if "Close" in d.columns else d.iloc[:, 0]
            c = c.dropna(); c.name = t
            panel = panel.join(c.to_frame(), how="outer").sort_index()
            print(f"  {t}: {c.index[0].date()} -> {c.index[-1].date()}")
        except Exception as e:
            print(f"  {t} err: {e}")

CASH = "SHV"
SAFE_DEFAULT = ["SHV", "IEF"]
SAFE_EXPANDED = ["BIL", "SHV", "SHY", "IEF"]
AGGR_ALL = ["QQQ","IGM","SPMO","XLE","XRT","SMH","COWZ","AVUV","MOO","RWJ","SPHQ","XMMO","XMHQ"]
UNIVERSE = AGGR_ALL + ["GLD", "KMLM_stitched"]
CANARY_ASSETS = ["SPY", "TIP"]

# Cherry config defaults
BUFFER = 3.0
CORR_LOOKBACK = 378


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

def best_safe(monthly_or_daily, d, safe_pool, mode="monthly"):
    """Pick best safe by Faber distance (10mo if monthly, 200d if daily)."""
    sub = monthly_or_daily.loc[:d]
    av = [s for s in safe_pool if s in sub.columns and sub[s].first_valid_index() is not None]
    if not av: return CASH if CASH in sub.columns else (av[0] if av else None)
    win = 10 if mode == "monthly" else 200
    if len(sub) < win: return av[0]
    sma = sub[av].rolling(win).mean().iloc[-1]; last = sub[av].iloc[-1]
    dist = ((last - sma) / sma).dropna()
    return dist.idxmax() if not dist.empty else av[0]


def rebal_dates(idx, start, end, freq):
    """Generate rebalance dates by frequency.
       freq: 'M'=month-end, 'BW'=bi-weekly (every 2 weeks), 'Q'=quarter-end
    """
    sub = idx[(idx >= start) & (idx <= end)]
    if len(sub) == 0: return []
    if freq == "M":
        groups = pd.DataFrame({"x":1}, index=sub).groupby(pd.Grouper(freq="ME")).tail(1)
    elif freq == "Q":
        groups = pd.DataFrame({"x":1}, index=sub).groupby(pd.Grouper(freq="QE")).tail(1)
    elif freq == "BW":
        # bi-weekly = every 14 days, find nearest trading day for each fortnight
        bw_targets = pd.date_range(start=sub[0], end=sub[-1], freq="14D")
        idx_arr = sub.values
        actual_dates = []
        for t in bw_targets:
            avail = sub[sub <= t]
            if len(avail) > 0:
                actual_dates.append(avail[-1])
        return list(dict.fromkeys(actual_dates))
    else:
        raise ValueError(f"Unknown freq {freq}")
    return groups.index.tolist()


def build_weights(close, monthly, dates, universe, safe_pool, buffer=BUFFER, corr_lookback=CORR_LOOKBACK):
    weights_map = {}
    prev_pair = None
    for d in dates:
        m = monthly.loc[:d]
        on = True
        for c in CANARY_ASSETS:
            if c in m.columns:
                s = sig_13612W(m[c])
                if pd.isna(s) or s <= 0: on = False; break
        safe = best_safe(monthly, d, safe_pool, mode="monthly") or CASH
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


def segment_returns(close, weights_map, dates, end, lag_days=0):
    """Apply weights with optional execution lag (signal computed on d, executed d+lag)."""
    daily = close.ffill().pct_change()
    period_idx = close.index[(close.index >= dates[0]) & (close.index <= end)]
    out = pd.Series(0.0, index=period_idx)
    for i, d in enumerate(dates):
        nxt = dates[i+1] if i+1 < len(dates) else end
        seg = period_idx[(period_idx > d) & (period_idx <= nxt)]
        if len(seg) == 0: continue
        if lag_days > 0:
            seg = seg[lag_days:] if len(seg) > lag_days else pd.DatetimeIndex([])
        if len(seg) == 0: continue
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


def vol_target_overlay(daily, target_vol_ann=0.12, lookback_d=63, max_lev=1.5):
    """Scale daily returns to target annualized vol using rolling realized vol.
       max_lev caps leverage; returns scaled daily series.
       Realized vol uses prior `lookback_d` days; applies forward (no look-ahead).
    """
    realized = daily.rolling(lookback_d).std() * np.sqrt(252)
    scale = (target_vol_ann / realized).clip(upper=max_lev).shift(1)  # shift to avoid lookahead
    scale = scale.fillna(1.0)
    return daily * scale


# Setup
end = panel.index[-1]
start = pd.Timestamp("2001-08-30")

cols = list(dict.fromkeys(UNIVERSE + SAFE_DEFAULT + SAFE_EXPANDED + CANARY_ASSETS + [CASH]))
cols = [c for c in cols if c in panel.columns]
close = panel[cols]
monthly = close.resample("ME").last()


# ============================================================
# #5 REBALANCE FREQUENCY
# ============================================================
print("\n" + "="*80)
print("#5 Rebalance frequency (cherry config)")
print("="*80)
freq_rows = []
for freq_name, freq in [("monthly", "M"), ("bi-weekly", "BW"), ("quarterly", "Q")]:
    dates = rebal_dates(close.index, start, end, freq)
    wmap = build_weights(close, monthly, dates, UNIVERSE, SAFE_DEFAULT)
    daily = segment_returns(close, wmap, dates, end)
    eq = (1.0+daily).cumprod()*100_000.0
    m = perf(daily, eq); m["frequency"] = freq_name
    m["n_rebalances"] = len(dates)
    m["per_yr"] = round(len(dates) / ((end - dates[0]).days/365.25), 1)
    freq_rows.append(m)
freq_df = pd.DataFrame(freq_rows)[["frequency","n_rebalances","per_yr","cagr","vol","sharpe","max_drawdown"]]
print(freq_df.to_string(index=False, float_format=lambda x: f"{x:.4f}"))


# ============================================================
# #6 EXECUTION LAG
# ============================================================
print("\n" + "="*80)
print("#6 Execution lag (monthly rebal, cherry)")
print("="*80)
lag_rows = []
dates = rebal_dates(close.index, start, end, "M")
wmap = build_weights(close, monthly, dates, UNIVERSE, SAFE_DEFAULT)
for lag_name, lag_d in [("0d_signal_close", 0), ("1d_next_open", 1), ("3d_settle_buffer", 3), ("5d_one_week", 5)]:
    daily = segment_returns(close, wmap, dates, end, lag_days=lag_d)
    eq = (1.0+daily).cumprod()*100_000.0
    m = perf(daily, eq); m["lag"] = lag_name
    lag_rows.append(m)
lag_df = pd.DataFrame(lag_rows)[["lag","cagr","vol","sharpe","max_drawdown"]]
print(lag_df.to_string(index=False, float_format=lambda x: f"{x:.4f}"))


# ============================================================
# #7 VOL TARGETING OVERLAY
# ============================================================
print("\n" + "="*80)
print("#7 Vol targeting overlay (target N% annualized, max 1.5x lev)")
print("="*80)
dates = rebal_dates(close.index, start, end, "M")
wmap = build_weights(close, monthly, dates, UNIVERSE, SAFE_DEFAULT)
base_daily = segment_returns(close, wmap, dates, end)
vt_rows = []
# baseline (no targeting)
eq = (1.0+base_daily).cumprod()*100_000.0
m = perf(base_daily, eq); m["target_vol"] = "none"
vt_rows.append(m)
for tv in [0.08, 0.10, 0.12, 0.15]:
    scaled = vol_target_overlay(base_daily, target_vol_ann=tv, lookback_d=63, max_lev=1.5)
    eq = (1.0+scaled).cumprod()*100_000.0
    m = perf(scaled, eq); m["target_vol"] = f"{int(tv*100)}%"
    vt_rows.append(m)
# also try with longer lookback
for tv in [0.10, 0.12]:
    scaled = vol_target_overlay(base_daily, target_vol_ann=tv, lookback_d=126, max_lev=1.5)
    eq = (1.0+scaled).cumprod()*100_000.0
    m = perf(scaled, eq); m["target_vol"] = f"{int(tv*100)}%_lb126d"
    vt_rows.append(m)
vt_df = pd.DataFrame(vt_rows)[["target_vol","cagr","vol","sharpe","max_drawdown"]]
print(vt_df.to_string(index=False, float_format=lambda x: f"{x:.4f}"))


# ============================================================
# #8 BEST-SAFE POOL EXPANSION
# ============================================================
print("\n" + "="*80)
print("#8 Best-safe pool expansion")
print("="*80)
safe_rows = []
for name, pool in [
    ("SHV_only",         ["SHV"]),
    ("default_SHV+IEF",  ["SHV","IEF"]),
    ("BIL+SHV",          ["BIL","SHV"]),
    ("SHV+SHY+IEF",      ["SHV","SHY","IEF"]),
    ("expanded_BIL+SHV+SHY+IEF", ["BIL","SHV","SHY","IEF"]),
]:
    pool = [p for p in pool if p in panel.columns]
    if not pool:
        print(f"  {name}: SKIP (no tickers available)"); continue
    dates = rebal_dates(close.index, start, end, "M")
    wmap = build_weights(close, monthly, dates, UNIVERSE, pool)
    daily = segment_returns(close, wmap, dates, end)
    eq = (1.0+daily).cumprod()*100_000.0
    m = perf(daily, eq); m["safe_pool"] = name; m["pool_assets"] = ",".join(pool)
    safe_rows.append(m)
safe_df = pd.DataFrame(safe_rows)[["safe_pool","pool_assets","cagr","vol","sharpe","max_drawdown"]]
print(safe_df.to_string(index=False, float_format=lambda x: f"{x:.4f}"))

freq_df.to_csv("/tmp/refine5_freq.csv", index=False)
lag_df.to_csv("/tmp/refine6_lag.csv", index=False)
vt_df.to_csv("/tmp/refine7_voltarget.csv", index=False)
safe_df.to_csv("/tmp/refine8_safe.csv", index=False)
