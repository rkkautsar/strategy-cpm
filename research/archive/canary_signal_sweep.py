"""Sweep canary signal function on SPY+TIP up filter, AGGR+GLD+KMLM universe, no rescue."""
import sys
sys.path.insert(0, "/Users/rkautsar/personal/scripts/strategy_cam")

import numpy as np
import pandas as pd
from itertools import combinations

PANEL_PATH = "/Users/rkautsar/personal/scripts/artifacts/cpa-1997-exact-core-proxy-research/proxy_adjusted_close_daily.csv"
panel = pd.read_csv(PANEL_PATH, parse_dates=["Date"], index_col="Date").sort_index()
gld = pd.read_csv("/tmp/gld_stitched_daily_clean.csv", parse_dates=[0], index_col=0); gld.columns=["GLD"]
kmlm = pd.read_csv("/tmp/kmlm_stitched_daily.csv", parse_dates=[0], index_col=0); kmlm.columns=["KMLM_stitched"]
panel = panel.join(gld, how="outer").join(kmlm, how="outer").sort_index()

CASH = "SHV"
SAFE_POOL = ["SHV", "IEF"]
CORR_LOOKBACK_DAYS = 252
HOLD_BUFFER = 1.0
AGGR_ALL = ["QQQ","IGM","SPMO","XLE","XRT","SMH","COWZ","AVUV","MOO","RWJ","SPHQ","XMMO","XMHQ"]
UNIVERSE = AGGR_ALL + ["GLD", "KMLM_stitched"]
CANARY_ASSETS = ["SPY", "TIP"]

# ---- canary signals ----
def sig_13612W(p):
    p = p.dropna()
    if len(p) < 13: return np.nan
    last = p.iloc[-1]
    return (12*(last/p.iloc[-2]-1) + 4*(last/p.iloc[-4]-1) + 2*(last/p.iloc[-7]-1) + (last/p.iloc[-13]-1))/19.0

def sig_13612U(p):
    p = p.dropna()
    if len(p) < 13: return np.nan
    last = p.iloc[-1]
    return ((last/p.iloc[-2]-1) + (last/p.iloc[-4]-1) + (last/p.iloc[-7]-1) + (last/p.iloc[-13]-1))/4.0

def sig_faber_sma10m(p):
    p = p.dropna()
    if len(p) < 10: return np.nan
    sma = p.tail(10).mean()
    return (p.iloc[-1] - sma) / sma

def sig_12m(p):
    p = p.dropna()
    if len(p) < 13: return np.nan
    return p.iloc[-1] / p.iloc[-13] - 1.0

def sig_12_1(p):
    p = p.dropna()
    if len(p) < 14: return np.nan
    return p.iloc[-2] / p.iloc[-14] - 1.0

def sig_6m(p):
    p = p.dropna()
    if len(p) < 7: return np.nan
    return p.iloc[-1] / p.iloc[-7] - 1.0

def sig_3m(p):
    p = p.dropna()
    if len(p) < 4: return np.nan
    return p.iloc[-1] / p.iloc[-4] - 1.0

def sig_sma200d(p, daily=True):
    p = p.dropna()
    if len(p) < 200: return np.nan
    sma = p.tail(200).mean()
    return (p.iloc[-1] - sma) / sma

SIGNALS = {
    "13612W":     sig_13612W,
    "13612U":     sig_13612U,
    "Faber_SMA10m": sig_faber_sma10m,
    "M12":        sig_12m,
    "M12_1":      sig_12_1,
    "M6":         sig_6m,
    "M3":         sig_3m,
}

# ---- engine helpers ----
def faber_sma_xs(monthly):
    if len(monthly) < 10: return pd.Series(np.nan, index=monthly.columns)
    sma = monthly.rolling(10).mean().iloc[-1]
    return (monthly.iloc[-1] - sma) / sma

def lowest_corr_pair(daily_close, candidates, lookback=CORR_LOOKBACK_DAYS):
    if len(candidates) < 2: return None
    rets = daily_close[candidates].iloc[-lookback:].pct_change().dropna(how="all")
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
    days = (eq.index[-1]-eq.index[0]).days; yrs = days/365.25
    cagr = (eq.iloc[-1]/eq.iloc[0])**(1/yrs)-1 if yrs>0 else float("nan")
    vol = daily.std(ddof=0)*np.sqrt(252)
    sharpe = (daily.mean()*252)/vol if vol>0 else float("nan")
    rm = eq.cummax(); mdd = (eq/rm-1).min()
    return {"total_return": eq.iloc[-1]/eq.iloc[0]-1, "cagr": cagr, "vol": vol, "sharpe": sharpe, "max_drawdown": mdd}

def best_safe(monthly_panel, d):
    m = monthly_panel.loc[:d]
    av = [s for s in SAFE_POOL if s in m.columns and m[s].first_valid_index() is not None]
    if not av: return CASH if CASH in m.columns else None
    if len(m) < 10: return av[0]
    sma = m[av].rolling(10).mean().iloc[-1]; last = m[av].iloc[-1]
    dist = ((last-sma)/sma).dropna()
    return dist.idxmax() if not dist.empty else av[0]

def canary_active(monthly_panel, sig_fn, d, daily_panel=None):
    m = monthly_panel.loc[:d]
    for c in CANARY_ASSETS:
        if c not in m.columns: return True
        s = sig_fn(m[c])
        if pd.isna(s): return True
        if s <= 0: return False
    return True

def canary_active_daily(daily_panel, d):
    """For SMA200d use daily prices."""
    sub = daily_panel.loc[:d]
    for c in CANARY_ASSETS:
        if c not in sub.columns: return True
        p = sub[c].dropna()
        if len(p) < 200: return True
        sma = p.tail(200).mean()
        if (p.iloc[-1] - sma)/sma <= 0: return False
    return True

def run(sig_fn, sig_name, start, end):
    cols = list(dict.fromkeys(UNIVERSE + SAFE_POOL + CANARY_ASSETS + [CASH]))
    cols = [c for c in cols if c in panel.columns]
    close = panel[cols]
    monthly = close.resample("ME").last()
    dates = month_end_dates(close.index, start, end)
    weights_map = {}; prev_pair = None; n_riskon = 0; n_total = 0
    for d in dates:
        n_total += 1
        if sig_name == "SMA200d":
            on = canary_active_daily(close, d)
        else:
            on = canary_active(monthly, sig_fn, d)
        safe = best_safe(monthly, d) or CASH
        if not on:
            weights_map[d] = {safe: 1.0}; prev_pair = None; continue
        n_riskon += 1
        m = monthly.loc[:d]
        score = faber_sma_xs(m)
        avail = [t for t in UNIVERSE if t in score.index and pd.notna(score[t]) and pd.notna(close.loc[d].get(t, np.nan))]
        if not avail:
            weights_map[d] = {safe:1.0}; prev_pair = None; continue
        score_avail = score.loc[avail]; z_avail = zscore(score_avail)
        ranked = score_avail.sort_values(ascending=False)
        half_n = max(2, (len(ranked)+1)//2)
        positive = ranked.iloc[:half_n][lambda s: s>0]
        if len(positive) < 2:
            if len(positive)==1:
                weights_map[d] = {positive.index[0]: 0.5, safe: 0.5}
            else:
                weights_map[d] = {safe:1.0}
            prev_pair = None; continue
        candidates = list(positive.index)
        new_pair = lowest_corr_pair(close.loc[:d, candidates], candidates)
        if new_pair is None:
            weights_map[d] = {candidates[0]:1.0}; prev_pair = None; continue
        if prev_pair is not None and HOLD_BUFFER > 1e-9:
            new_set = list(new_pair)
            for prior in prev_pair:
                if prior in new_set or prior not in avail: continue
                if score_avail.get(prior, -np.inf) <= 0: continue
                z_prior = z_avail.get(prior, np.nan)
                if pd.isna(z_prior): continue
                swap_candidates = [x for x in new_set if x not in prev_pair]
                if not swap_candidates: continue
                swap_target = min(swap_candidates, key=lambda x: z_avail.get(x, np.inf))
                z_swap = z_avail.get(swap_target, np.nan)
                if pd.isna(z_swap): continue
                if z_swap - z_prior < HOLD_BUFFER:
                    new_set.remove(swap_target); new_set.append(prior)
            new_pair = tuple(new_set[:2])
        weights_map[d] = {new_pair[0]:0.5, new_pair[1]:0.5}; prev_pair = new_pair
    return segment_returns(close, weights_map, dates, end), n_riskon, n_total

end = panel.index[-1]
start = pd.Timestamp("2001-08-30")

rows = []
for name, fn in SIGNALS.items():
    daily, riskon, total = run(fn, name, start, end)
    eq = (1.0+daily).cumprod()*100_000.0
    m = perf(daily, eq); m["canary"] = name
    m["riskon_pct"] = round(100*riskon/total, 1) if total else 0
    m["years"] = round((daily.index[-1]-daily.index[0]).days/365.25, 1)
    rows.append(m)

# Add SMA200d separately
daily, riskon, total = run(None, "SMA200d", start, end)
eq = (1.0+daily).cumprod()*100_000.0
m = perf(daily, eq); m["canary"] = "SMA200d_daily"; m["riskon_pct"] = round(100*riskon/total, 1) if total else 0
m["years"] = round((daily.index[-1]-daily.index[0]).days/365.25, 1)
rows.append(m)

# baseline none
def run_no_canary(start, end):
    cols = list(dict.fromkeys(UNIVERSE + SAFE_POOL + [CASH]))
    cols = [c for c in cols if c in panel.columns]
    close = panel[cols]; monthly = close.resample("ME").last()
    dates = month_end_dates(close.index, start, end)
    weights_map = {}; prev_pair = None
    for d in dates:
        safe = best_safe(monthly, d) or CASH
        m = monthly.loc[:d]; score = faber_sma_xs(m)
        avail = [t for t in UNIVERSE if t in score.index and pd.notna(score[t]) and pd.notna(close.loc[d].get(t, np.nan))]
        if not avail:
            weights_map[d] = {safe:1.0}; prev_pair=None; continue
        score_avail = score.loc[avail]; z_avail = zscore(score_avail)
        ranked = score_avail.sort_values(ascending=False)
        half_n = max(2, (len(ranked)+1)//2)
        positive = ranked.iloc[:half_n][lambda s: s>0]
        if len(positive)<2:
            if len(positive)==1: weights_map[d]={positive.index[0]:0.5, safe:0.5}
            else: weights_map[d]={safe:1.0}
            prev_pair=None; continue
        candidates = list(positive.index)
        new_pair = lowest_corr_pair(close.loc[:d, candidates], candidates)
        if new_pair is None:
            weights_map[d] = {candidates[0]:1.0}; prev_pair=None; continue
        if prev_pair is not None:
            new_set = list(new_pair)
            for prior in prev_pair:
                if prior in new_set or prior not in avail: continue
                if score_avail.get(prior, -np.inf) <= 0: continue
                z_prior = z_avail.get(prior, np.nan)
                if pd.isna(z_prior): continue
                swap_candidates = [x for x in new_set if x not in prev_pair]
                if not swap_candidates: continue
                swap_target = min(swap_candidates, key=lambda x: z_avail.get(x, np.inf))
                z_swap = z_avail.get(swap_target, np.nan)
                if pd.isna(z_swap): continue
                if z_swap - z_prior < HOLD_BUFFER:
                    new_set.remove(swap_target); new_set.append(prior)
            new_pair = tuple(new_set[:2])
        weights_map[d] = {new_pair[0]:0.5, new_pair[1]:0.5}; prev_pair = new_pair
    return segment_returns(close, weights_map, dates, end)

daily = run_no_canary(start, end)
eq = (1.0+daily).cumprod()*100_000.0
m = perf(daily, eq); m["canary"]="none"; m["riskon_pct"]=100.0
m["years"]=round((daily.index[-1]-daily.index[0]).days/365.25, 1)
rows.append(m)

df = pd.DataFrame(rows)[["canary","years","riskon_pct","total_return","cagr","vol","sharpe","max_drawdown"]]
df = df.sort_values("sharpe", ascending=False).reset_index(drop=True)
print()
print(df.to_string(index=False, float_format=lambda x: f"{x:.4f}"))
df.to_csv("/tmp/canary_signal_sweep.csv", index=False)
