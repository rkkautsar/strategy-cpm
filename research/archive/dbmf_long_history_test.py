"""Final config with synthetic DBMF backfill (1999-2026, ~26y), vs KMLM stitched."""
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
dbmf_stitched = pd.read_csv("/tmp/dbmf_stitched_daily.csv", parse_dates=[0], index_col=0); dbmf_stitched.columns=["DBMF_stitched"]
panel = panel.join(gld, how="outer").join(kmlm, how="outer").join(agg, how="outer").join(tip_clean, how="outer").join(dbmf_stitched, how="outer").sort_index()
panel["TIP"] = panel["TIP_clean"]

for t in ["BIL", "SHY"]:
    if t not in panel.columns:
        d = yf.download(t, start="2000-01-01", end="2026-05-14", auto_adjust=True, progress=False, threads=False)
        if isinstance(d.columns, pd.MultiIndex): d = d["Close"]
        c = d["Close"] if "Close" in d.columns else d.iloc[:, 0]
        c = c.dropna(); c.name = t
        panel = panel.join(c.to_frame(), how="outer").sort_index()

CASH = "SHV"
SAFE_POOL = ["BIL", "SHV", "SHY", "IEF"]
AGGR_ALL = ["QQQ","IGM","SPMO","XLE","XRT","SMH","COWZ","AVUV","MOO","RWJ","SPHQ","XMMO","XMHQ"]
CANARY_ASSETS = ["SPY", "TIP"]
BUFFER = 3.0; CORR_LOOKBACK = 378
TARGET_VOL = 0.10; VOL_LOOKBACK = 63; MAX_LEV = 1.5
COST_BPS = 10


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

def best_safe(monthly, d, safe_pool):
    sub = monthly.loc[:d]
    av = [s for s in safe_pool if s in sub.columns and sub[s].first_valid_index() is not None]
    if not av: return CASH if CASH in sub.columns else None
    if len(sub) < 10: return av[0]
    sma = sub[av].rolling(10).mean().iloc[-1]; last = sub[av].iloc[-1]
    dist = ((last - sma) / sma).dropna()
    return dist.idxmax() if not dist.empty else av[0]

def perf(daily, eq):
    if daily.empty: return {}
    days = (eq.index[-1]-eq.index[0]).days; yrs = days/365.25
    cagr = (eq.iloc[-1]/eq.iloc[0])**(1/yrs)-1 if yrs>0 else float("nan")
    vol = daily.std(ddof=0)*np.sqrt(252)
    sharpe = (daily.mean()*252)/vol if vol>0 else float("nan")
    rm = eq.cummax(); mdd = (eq/rm-1).min()
    return {"cagr": cagr, "vol": vol, "sharpe": sharpe, "max_drawdown": mdd}


def compute_signal(monthly_panel, close_panel, sig_d, prev_pair, universe):
    m = monthly_panel.loc[:sig_d]
    on = True
    for c in CANARY_ASSETS:
        if c in m.columns:
            s = sig_13612W(m[c])
            if pd.isna(s) or s <= 0: on = False; break
    safe = best_safe(monthly_panel, sig_d, SAFE_POOL) or CASH
    if not on: return {safe: 1.0}, None
    score = faber_sma_xs(m)
    avail = [t for t in universe if t in score.index and pd.notna(score[t]) and pd.notna(close_panel.loc[sig_d].get(t, np.nan) if sig_d in close_panel.index else np.nan)]
    if not avail: return {safe: 1.0}, None
    sa = score.loc[avail]; za = zscore(sa)
    ranked = sa.sort_values(ascending=False)
    positive = ranked.iloc[:max(2,(len(ranked)+1)//2)][lambda s: s>0]
    if len(positive) < 2:
        if len(positive) == 1:
            return {positive.index[0]: 0.5, safe: 0.5}, None
        return {safe: 1.0}, None
    candidates = list(positive.index)
    new_pick = lowest_corr_pair(close_panel.loc[:sig_d, candidates], candidates, CORR_LOOKBACK)
    if new_pick is None: return {candidates[0]: 1.0}, None
    if prev_pair is not None and BUFFER > 1e-9:
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
            if z_swap - z_prior < BUFFER:
                new_set.remove(swap); new_set.append(prior)
        new_pick = tuple(new_set[:2])
    return {new_pick[0]: 0.5, new_pick[1]: 0.5}, new_pick


def run_production(start, end, universe, apply_vt=True, cost_bps=COST_BPS):
    cols = list(dict.fromkeys(universe + SAFE_POOL + CANARY_ASSETS + [CASH]))
    cols = [c for c in cols if c in panel.columns]
    close = panel[cols]
    monthly_idx = pd.DataFrame({"x":1}, index=close.index).groupby(pd.Grouper(freq="ME")).tail(1)
    signal_dates = monthly_idx.index[(monthly_idx.index >= start) & (monthly_idx.index <= end)].tolist()
    weights_history = []; prev_pair = None
    for i, sig_d in enumerate(signal_dates):
        monthly_for_signal = close.loc[:sig_d].resample("ME").last()
        w, new_pair = compute_signal(monthly_for_signal, close, sig_d, prev_pair, universe)
        prev_pair = new_pair
        future = close.index[close.index > sig_d]
        if len(future) < 2: continue
        apply_from = future[1]
        if i+1 < len(signal_dates):
            next_sig = signal_dates[i+1]
            next_future = close.index[close.index > next_sig]
            end_apply = next_future[1] if len(next_future) >= 2 else end
        else:
            end_apply = end
        weights_history.append((apply_from, end_apply, w))
    all_assets = sorted({a for _, _, w in weights_history for a in w})
    df = pd.DataFrame(0.0, index=close.index, columns=all_assets)
    for apply_from, end_apply, w in weights_history:
        mask = (close.index >= apply_from) & (close.index < end_apply)
        for a, ww in w.items():
            if a in df.columns: df.loc[mask, a] = ww
    daily_ret = close.ffill().pct_change()
    common = [a for a in df.columns if a in daily_ret.columns]
    pre_cost = (df[common] * daily_ret[common]).sum(axis=1, min_count=1).fillna(0.0)
    for i in range(len(weights_history)):
        prev_w = weights_history[i-1][2] if i > 0 else {}
        curr_w = weights_history[i][2]
        keys = set(curr_w) | set(prev_w)
        turnover = sum(abs(curr_w.get(k, 0.0) - prev_w.get(k, 0.0)) for k in keys)
        cost = turnover * cost_bps / 10000.0
        apply_from = weights_history[i][0]
        if apply_from in pre_cost.index:
            pre_cost.loc[apply_from] -= cost
    daily = pre_cost
    if apply_vt:
        realized = daily.rolling(VOL_LOOKBACK).std() * np.sqrt(252)
        scale = (TARGET_VOL / realized).clip(upper=MAX_LEV).shift(1).fillna(1.0)
        daily = daily * scale
    return daily.loc[(daily.index >= start) & (daily.index <= end)]


end = panel.index[-1]
start_long = pd.Timestamp("2001-08-30")  # cleanest GLD start

variants = [
    ("AGGR+GLD",                          AGGR_ALL + ["GLD"]),
    ("AGGR+GLD+KMLM",                     AGGR_ALL + ["GLD", "KMLM_stitched"]),
    ("AGGR+GLD+TLT",                      AGGR_ALL + ["GLD", "TLT"]),
    ("AGGR+GLD+KMLM+TLT",                 AGGR_ALL + ["GLD", "KMLM_stitched", "TLT"]),
    ("AGGR+GLD+DBMF_stitched",            AGGR_ALL + ["GLD", "DBMF_stitched"]),
    ("AGGR+GLD+DBMF_stitched+TLT",        AGGR_ALL + ["GLD", "DBMF_stitched", "TLT"]),
    ("AGGR+GLD+KMLM+DBMF_stitched",       AGGR_ALL + ["GLD", "KMLM_stitched", "DBMF_stitched"]),
    ("AGGR+GLD+KMLM+DBMF_stitched+TLT",   AGGR_ALL + ["GLD", "KMLM_stitched", "DBMF_stitched", "TLT"]),
]

print("="*80)
print(f"Production config (cherry + 10bps + 10% VT) on different diversifier universes")
print(f"Long-history window: {start_long.date()} -> {end.date()}")
print("="*80)
rows = []
for name, univ in variants:
    print(f"  Running {name}...")
    daily = run_production(start_long, end, univ)
    if daily.empty: continue
    eq = (1.0+daily).cumprod()*100_000.0
    m = perf(daily, eq); m["universe"] = name
    rows.append(m)
df = pd.DataFrame(rows)[["universe","cagr","vol","sharpe","max_drawdown"]]
df = df.sort_values("sharpe", ascending=False).reset_index(drop=True)
print(df.to_string(index=False, float_format=lambda x: f"{x:.4f}"))


# Year-by-year compare top 4
print()
print("="*80)
print("Year-by-year: KMLM vs +TLT vs +KMLM+TLT")
print("="*80)
daily_kmlm = run_production(start_long, end, AGGR_ALL + ["GLD", "KMLM_stitched"])
daily_tlt = run_production(start_long, end, AGGR_ALL + ["GLD", "TLT"])
daily_kmlm_tlt = run_production(start_long, end, AGGR_ALL + ["GLD", "KMLM_stitched", "TLT"])
spy = panel["SPY"].ffill().pct_change().loc[start_long:end].fillna(0.0)
yr_kmlm = (1.0+daily_kmlm).resample("YE").prod() - 1
yr_tlt = (1.0+daily_tlt).resample("YE").prod() - 1
yr_kt = (1.0+daily_kmlm_tlt).resample("YE").prod() - 1
yr_spy = (1.0+spy).resample("YE").prod() - 1
yr = pd.DataFrame({"SPY": yr_spy, "KMLM": yr_kmlm, "TLT": yr_tlt, "KMLM+TLT": yr_kt})
yr.index = yr.index.year
print(yr.to_string(float_format=lambda x: f"{x*100:+6.2f}%"))
df.to_csv("/tmp/tlt_kmlm_test.csv", index=False)
yr.to_csv("/tmp/tlt_kmlm_yearly.csv")

# Pick frequency for the KMLM+TLT variant
print()
print("="*80)
print("Pick frequency for AGGR+GLD+KMLM+TLT (which assets get used?)")
print("="*80)
# Re-build weights map manually to count picks
cols = list(dict.fromkeys((AGGR_ALL + ["GLD", "KMLM_stitched", "TLT"]) + SAFE_POOL + CANARY_ASSETS + [CASH]))
cols = [c for c in cols if c in panel.columns]
close_x = panel[cols]
monthly_idx = pd.DataFrame({"x":1}, index=close_x.index).groupby(pd.Grouper(freq="ME")).tail(1)
signal_dates = monthly_idx.index[(monthly_idx.index >= start_long) & (monthly_idx.index <= end)].tolist()
counts = {}
prev_pair = None
for sig_d in signal_dates:
    monthly_for_signal = close_x.loc[:sig_d].resample("ME").last()
    w, new_pair = compute_signal(monthly_for_signal, close_x, sig_d, prev_pair, AGGR_ALL + ["GLD", "KMLM_stitched", "TLT"])
    prev_pair = new_pair
    for t in w:
        counts[t] = counts.get(t, 0) + 1
total = len(signal_dates)
freq = sorted(counts.items(), key=lambda x: x[1], reverse=True)
print(f"Total months: {total}")
for t, c in freq:
    pct = c/total*100
    print(f"  {t:14s} {c:4d} months ({pct:5.1f}%)  {'#'*int(pct/2)}")
