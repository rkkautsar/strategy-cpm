"""
Test Optimum3 strategy + our engine on Optimum3's universe.

Optimum3 universe (15 global asset classes):
  SPY, QQQ, VNQ, REM, IEF, TLT, TIP, VGK, EWJ, SCZ, EEM, RWX, BWX, DBC, GLD
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

# Need to fetch missing Optimum3 tickers: REM, EWJ, SCZ, RWX, BWX
# QQQ, SPY, VNQ, IEF, TLT, TIP, VGK (in panel? let me check)
needed_extra = ["REM", "EWJ", "SCZ", "RWX", "BWX", "VGK"]
have = [c for c in panel.columns]
missing = [t for t in needed_extra if t not in have]
print(f"Need to fetch: {missing}")

# Fetch missing
extras = {}
for t in missing:
    try:
        d = yf.download(t, start="2000-01-01", end="2026-05-14", auto_adjust=True, progress=False, threads=False)
        if isinstance(d.columns, pd.MultiIndex):
            d = d["Close"]
        c = d["Close"] if "Close" in d.columns else d.iloc[:, 0]
        c = c.dropna()
        extras[t] = c
        print(f"  {t}: {c.index[0].date()} -> {c.index[-1].date()}")
    except Exception as e:
        print(f"  {t} err {e}")

extras_df = pd.DataFrame(extras)
panel = panel.join(extras_df, how="outer").sort_index()

OPTIMUM3_UNIVERSE = ["SPY","QQQ","VNQ","REM","IEF","TLT","TIP","VGK","EWJ","SCZ","EEM","RWX","BWX","DBC","GLD"]
have = [t for t in OPTIMUM3_UNIVERSE if t in panel.columns]
missing = [t for t in OPTIMUM3_UNIVERSE if t not in panel.columns]
print(f"\nUniverse: {len(have)}/{len(OPTIMUM3_UNIVERSE)} available, missing: {missing}")

CASH = "SHV"
SAFE_POOL = ["SHV", "IEF"]
CORR_LOOKBACK_DAYS = 252
HOLD_BUFFER = 1.0


# ---- shared helpers ----
def faber_sma_xs(monthly):
    if len(monthly) < 10: return pd.Series(np.nan, index=monthly.columns)
    sma = monthly.rolling(10).mean().iloc[-1]
    return (monthly.iloc[-1] - sma) / sma

def sig_13612W(p):
    p = p.dropna()
    if len(p) < 13: return np.nan
    last = p.iloc[-1]
    return (12*(last/p.iloc[-2]-1) + 4*(last/p.iloc[-4]-1) + 2*(last/p.iloc[-7]-1) + (last/p.iloc[-13]-1))/19.0

def sig_multi_avg(p):
    """Avg of r1, r3, r6, r12 (Optimum3-ish, since real lookback is undisclosed)."""
    p = p.dropna()
    if len(p) < 13: return np.nan
    last = p.iloc[-1]
    return ((last/p.iloc[-2]-1) + (last/p.iloc[-4]-1) + (last/p.iloc[-7]-1) + (last/p.iloc[-13]-1))/4.0

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

def lowest_avg_corr_triplet(daily, candidates, lookback=CORR_LOOKBACK_DAYS):
    """Pick triplet with lowest avg pairwise correlation (Optimum3 / Varadi MinCorr)."""
    if len(candidates) < 3: return None
    rets = daily[candidates].iloc[-lookback:].pct_change().dropna(how="all")
    if len(rets) < 30: return None
    corr = rets.corr()
    best, val = None, float("inf")
    for a, b, c in combinations(candidates, 3):
        ac = (corr.loc[a, b] + corr.loc[a, c] + corr.loc[b, c]) / 3.0
        if pd.notna(ac) and ac < val:
            val, best = ac, (a, b, c)
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


# ============================================================
# 1. LITERAL OPTIMUM3 (no canary, no harness)
#    - top half by avg-multi mom (use 13612W as best guess)
#    - drop negative
#    - lowest avg-corr triplet
#    - 33/33/33
#    - NO defensive overlay (just stays in whatever survives)
# ============================================================
def optimum3_literal(close, universe, start, end, ranker_fn=sig_13612W):
    cols = list(dict.fromkeys(universe + [CASH]))
    cols = [c for c in cols if c in close.columns]
    sub = close[cols]
    monthly = sub.resample("ME").last()
    dates = month_end_dates(sub.index, start, end)
    weights_map = {}
    for d in dates:
        m = monthly.loc[:d]
        scores = {a: ranker_fn(m[a]) for a in universe if a in m.columns}
        scores = {a: v for a, v in scores.items() if pd.notna(v) and pd.notna(sub.loc[d].get(a, np.nan))}
        if not scores:
            weights_map[d] = {CASH: 1.0}; continue
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        half_n = max(3, (len(ranked) + 1) // 2)
        top_half = ranked[:half_n]
        positive = [(a, v) for a, v in top_half if v > 0]
        if len(positive) < 3:
            if len(positive) == 0:
                weights_map[d] = {CASH: 1.0}
            else:
                w = 1.0 / len(positive)
                weights_map[d] = {a: w for a, _ in positive}
            continue
        candidates = [a for a, _ in positive]
        trip = lowest_avg_corr_triplet(sub.loc[:d, candidates], candidates)
        if trip is None:
            w = 1.0 / 3
            weights_map[d] = {a: w for a in candidates[:3]}
            continue
        weights_map[d] = {a: 1/3 for a in trip}
    return segment_returns(sub, weights_map, dates, end)


# ============================================================
# 2. OUR ENGINE on Optimum3 universe
# ============================================================
def our_engine(close_panel, universe, start, end):
    canary_assets = ["SPY", "TIP"]
    cols = list(dict.fromkeys(universe + SAFE_POOL + canary_assets + [CASH]))
    cols = [c for c in cols if c in close_panel.columns]
    sub = close_panel[cols]
    monthly = sub.resample("ME").last()
    dates = month_end_dates(sub.index, start, end)
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
        avail = [t for t in universe if t in score.index and pd.notna(score[t]) and pd.notna(sub.loc[d].get(t, np.nan))]
        if not avail: weights_map[d] = {safe:1.0}; prev_pair = None; continue
        sa = score.loc[avail]; za = zscore(sa)
        ranked = sa.sort_values(ascending=False)
        positive = ranked.iloc[:max(2,(len(ranked)+1)//2)][lambda s: s>0]
        if len(positive) < 2:
            weights_map[d] = {positive.index[0]:0.5, safe:0.5} if len(positive)==1 else {safe:1.0}
            prev_pair = None; continue
        candidates = list(positive.index)
        new_pair = lowest_corr_pair(sub.loc[:d, candidates], candidates)
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
    return segment_returns(sub, weights_map, dates, end)


# ============================================================
# 3. OUR ENGINE w/ TRIPLET (test if triplet matches Optimum3 better)
# ============================================================
def our_engine_triplet(close_panel, universe, start, end):
    canary_assets = ["SPY", "TIP"]
    cols = list(dict.fromkeys(universe + SAFE_POOL + canary_assets + [CASH]))
    cols = [c for c in cols if c in close_panel.columns]
    sub = close_panel[cols]
    monthly = sub.resample("ME").last()
    dates = month_end_dates(sub.index, start, end)
    weights_map = {}
    for d in dates:
        on = True
        m = monthly.loc[:d]
        for c in canary_assets:
            if c in m.columns:
                s = sig_13612W(m[c])
                if pd.isna(s) or s <= 0: on = False; break
        safe = best_safe(monthly, d) or CASH
        if not on:
            weights_map[d] = {safe: 1.0}; continue
        score = faber_sma_xs(m)
        avail = [t for t in universe if t in score.index and pd.notna(score[t]) and pd.notna(sub.loc[d].get(t, np.nan))]
        if not avail: weights_map[d] = {safe:1.0}; continue
        sa = score.loc[avail]
        ranked = sa.sort_values(ascending=False)
        positive = ranked.iloc[:max(3,(len(ranked)+1)//2)][lambda s: s>0]
        if len(positive) < 3:
            if len(positive) == 0:
                weights_map[d] = {safe: 1.0}
            else:
                w = 1.0 / len(positive)
                weights_map[d] = {a: w for a in positive.index}
            continue
        candidates = list(positive.index)
        trip = lowest_avg_corr_triplet(sub.loc[:d, candidates], candidates)
        if trip is None:
            weights_map[d] = {a: 1/3 for a in candidates[:3]}
            continue
        weights_map[d] = {a: 1/3 for a in trip}
    return segment_returns(sub, weights_map, dates, end)


end = panel.index[-1]
start = pd.Timestamp("2008-08-30")  # latest of Optimum3 universe inceptions w/ 12mo warmup

print(f"\nWindow: {start.date()} -> {end.date()}")
results = {}
print("Running Optimum3 LITERAL on its universe...")
results["Optimum3_literal_O3univ"] = optimum3_literal(panel, OPTIMUM3_UNIVERSE, start, end)
print("Running OUR ENGINE on Optimum3 universe...")
results["OurEngine_O3univ"] = our_engine(panel, OPTIMUM3_UNIVERSE, start, end)
print("Running OUR ENGINE TRIPLET on Optimum3 universe...")
results["OurEngineTriplet_O3univ"] = our_engine_triplet(panel, OPTIMUM3_UNIVERSE, start, end)

# Reference: our engine on AGGR+GLD+KMLM
AGGR_ALL = ["QQQ","IGM","SPMO","XLE","XRT","SMH","COWZ","AVUV","MOO","RWJ","SPHQ","XMMO","XMHQ"]
print("Running OUR ENGINE on AGGR+GLD+KMLM (reference)...")
results["OurEngine_AGGRgld+KMLM"] = our_engine(panel, AGGR_ALL + ["GLD","KMLM_stitched"], start, end)

print("Running Optimum3 LITERAL on AGGR+GLD+KMLM (cross test)...")
results["Optimum3_literal_AGGRgld+KMLM"] = optimum3_literal(panel, AGGR_ALL + ["GLD","KMLM_stitched"], start, end)

rows = []
for name, daily in results.items():
    if daily.empty: continue
    eq = (1.0+daily).cumprod()*100_000.0
    m = perf(daily, eq); m["strategy"] = name
    m["years"] = round((daily.index[-1]-daily.index[0]).days/365.25, 1)
    rows.append(m)
df = pd.DataFrame(rows)[["strategy","years","cagr","vol","sharpe","max_drawdown"]]
df = df.sort_values("sharpe", ascending=False).reset_index(drop=True)
print()
print(df.to_string(index=False, float_format=lambda x: f"{x:.4f}"))
df.to_csv("/tmp/optimum3_test.csv", index=False)
