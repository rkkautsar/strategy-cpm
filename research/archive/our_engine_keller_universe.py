"""Run OUR_STACK engine on Keller VAA G4's universe (SPY/EFA/EEM/AGG)."""
import sys
sys.path.insert(0, "/Users/rkautsar/personal/scripts/strategy_cam")

import numpy as np
import pandas as pd
from itertools import combinations

PANEL_PATH = "/Users/rkautsar/personal/scripts/artifacts/cpa-1997-exact-core-proxy-research/proxy_adjusted_close_daily.csv"
panel = pd.read_csv(PANEL_PATH, parse_dates=["Date"], index_col="Date").sort_index()
gld = pd.read_csv("/tmp/gld_stitched_daily_clean.csv", parse_dates=[0], index_col=0); gld.columns=["GLD"]
kmlm = pd.read_csv("/tmp/kmlm_stitched_daily.csv", parse_dates=[0], index_col=0); kmlm.columns=["KMLM_stitched"]
agg = pd.read_csv("/tmp/agg_stitched_daily.csv", parse_dates=[0], index_col=0); agg.columns=["AGG_stitched"]
tip_clean = pd.read_csv("/tmp/tip_stitched_daily.csv", parse_dates=[0], index_col=0); tip_clean.columns=["TIP_clean"]
panel = panel.join(gld, how="outer").join(kmlm, how="outer").join(agg, how="outer").join(tip_clean, how="outer").sort_index()
panel["TIP"] = panel["TIP_clean"]

CASH = "SHV"
SAFE_POOL = ["SHV", "IEF"]
CORR_LOOKBACK_DAYS = 252
HOLD_BUFFER = 1.0
AGGR_ALL = ["QQQ","IGM","SPMO","XLE","XRT","SMH","COWZ","AVUV","MOO","RWJ","SPHQ","XMMO","XMHQ"]

UNIVERSES = {
    "OUR_universe (AGGR+GLD+KMLM)":     AGGR_ALL + ["GLD","KMLM_stitched"],
    "Keller_VAA_G4 universe":           ["SPY","EFA","EEM","AGG_stitched"],
    "Keller_VAA_G4 + GLD":              ["SPY","EFA","EEM","AGG_stitched","GLD"],
    "Keller_VAA_G4 + GLD + KMLM":       ["SPY","EFA","EEM","AGG_stitched","GLD","KMLM_stitched"],
    "Keller_VAA_G12 universe":          ["SPY","IWM","QQQ","EEM","VNQ","DBC","GLD","TLT","IEF","AGG_stitched","EFA"],
    "Faber_IVY5 universe":              ["SPY","EFA","IEF","VNQ","DBC"],
    "Faber_IVY5 + GLD + KMLM":          ["SPY","EFA","IEF","VNQ","DBC","GLD","KMLM_stitched"],
}

def faber_sma_xs(monthly):
    if len(monthly) < 10: return pd.Series(np.nan, index=monthly.columns)
    sma = monthly.rolling(10).mean().iloc[-1]
    return (monthly.iloc[-1] - sma) / sma

def sig_13612W(p):
    p = p.dropna()
    if len(p) < 13: return np.nan
    last = p.iloc[-1]
    return (12*(last/p.iloc[-2]-1) + 4*(last/p.iloc[-4]-1) + 2*(last/p.iloc[-7]-1) + (last/p.iloc[-13]-1))/19.0

def lowest_corr_pair(daily, candidates, lookback=CORR_LOOKBACK_DAYS):
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

def best_safe(monthly, d):
    m = monthly.loc[:d]
    av = [s for s in SAFE_POOL if s in m.columns and m[s].first_valid_index() is not None]
    if not av: return CASH
    if len(m) < 10: return av[0]
    sma = m[av].rolling(10).mean().iloc[-1]; last = m[av].iloc[-1]
    dist = ((last-sma)/sma).dropna()
    return dist.idxmax() if not dist.empty else av[0]


def our_stack(universe, start, end):
    canary_assets = ["SPY", "TIP"]
    cols = list(dict.fromkeys(universe + SAFE_POOL + canary_assets + [CASH]))
    cols = [c for c in cols if c in panel.columns]
    close = panel[cols]; monthly = close.resample("ME").last()
    dates = month_end_dates(close.index, start, end)
    weights_map = {}; prev_pair = None
    for d in dates:
        on = True
        m = monthly.loc[:d]
        for c in canary_assets:
            if c in m.columns:
                s = sig_13612W(m[c])
                if pd.isna(s) or s <= 0: on = False; break
        safe = best_safe(monthly, d) or CASH
        if not on:
            weights_map[d] = {safe: 1.0}; prev_pair = None; continue
        score = faber_sma_xs(m)
        avail = [t for t in universe if t in score.index and pd.notna(score[t]) and pd.notna(close.loc[d].get(t, np.nan))]
        if not avail: weights_map[d] = {safe:1.0}; prev_pair = None; continue
        sa = score.loc[avail]; za = zscore(sa)
        ranked = sa.sort_values(ascending=False)
        positive = ranked.iloc[:max(2,(len(ranked)+1)//2)][lambda s: s>0]
        if len(positive) < 2:
            # 100% on single positive instead of 50/50 safe
            weights_map[d] = {positive.index[0]:1.0} if len(positive)==1 else {safe:1.0}
            prev_pair = None; continue
        candidates = list(positive.index)
        new_pair = lowest_corr_pair(close.loc[:d, candidates], candidates)
        if new_pair is None: weights_map[d] = {candidates[0]:1.0}; prev_pair = None; continue
        if prev_pair is not None:
            new_set = list(new_pair)
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
                if z_swap - z_prior < HOLD_BUFFER:
                    new_set.remove(swap); new_set.append(prior)
            new_pair = tuple(new_set[:2])
        weights_map[d] = {new_pair[0]:0.5, new_pair[1]:0.5}; prev_pair = new_pair
    return segment_returns(close, weights_map, dates, end)


end = panel.index[-1]
start = pd.Timestamp("2001-08-30")

results = {}
for name, univ in UNIVERSES.items():
    print(f"Running {name}...")
    daily = our_stack(univ, start, end)
    results[name] = daily

rows = []
for name, daily in results.items():
    if daily.empty: continue
    eq = (1.0+daily).cumprod()*100_000.0
    m = perf(daily, eq); m["universe"] = name
    rows.append(m)
df = pd.DataFrame(rows)[["universe","cagr","vol","sharpe","max_drawdown"]]
df = df.sort_values("sharpe", ascending=False).reset_index(drop=True)
print()
print(df.to_string(index=False, float_format=lambda x: f"{x:.4f}"))
df.to_csv("/tmp/our_engine_keller_universe.csv", index=False)
