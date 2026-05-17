"""
Universe sweep using long-history MUTUAL FUND PROXIES (1995+) + stitched KMLM (1988+).

Pair_MSMAdist_50_50 + hold_buffer=1.0.

Trimmed AGGR universe = drop tickers w/ inception > 2007:
  Original AGGR_orig: QQQ, IGM, SPMO, XLE, XRT, SMH, COWZ, AVUV, MOO, RWJ, SPHQ, XMMO, XMHQ
  Inception:         1999, 2001, 2015, 1998, 2006, 2000, 2016, 2019, 2007, 2008, 2005, 2005, 2006
  Long-history (pre-2007): QQQ, IGM, XLE, XRT, SMH, SPHQ, XMMO, XMHQ
  But proxies extend ALL of them back to 1995!

So with proxy panel we can run all 13 tickers from 1996+. KMLM stitched gets us trend-follower coverage from 1988+.

Universes tested:
  AGGR_orig                  — all 13 AGGR ETFs (proxy-extended)
  AGGR_trim_long             — only ETFs with real inception <= 2008 (no proxy hack): QQQ, IGM, XLE, XRT, SMH, MOO, RWJ, SPHQ, XMMO, XMHQ
  AGGR_trim_picked           — only ETFs that were actually picked >5% of months: QQQ, SMH, XLE, XRT, XMHQ, RWJ, MOO
  AGGR_orig_+GLD             — proxy + GLD
  AGGR_orig_+GLD_+KMLM       — proxy + GLD + stitched KMLM
  AGGR_trim_picked_+GLD_+KMLM
  AGGR_trim_picked_+GLD_+KMLM_+TLT
  Keller_DAA_G12_proxy
  Faber_IVY_5_proxy
  Faber_IVY_13_proxy
"""
import sys
sys.path.insert(0, "/Users/rkautsar/personal/scripts/strategy_cam")

import numpy as np
import pandas as pd
from itertools import combinations

# ---- load proxy panel ----
PANEL_PATH = "/Users/rkautsar/personal/scripts/artifacts/cpa-1997-exact-core-proxy-research/proxy_adjusted_close_daily.csv"
panel = pd.read_csv(PANEL_PATH, parse_dates=["Date"], index_col="Date").sort_index()
print(f"Proxy panel: {panel.index[0].date()} -> {panel.index[-1].date()}, {len(panel.columns)} assets")

# ---- merge stitched KMLM ----
kmlm_stitched = pd.read_csv("/tmp/kmlm_stitched_daily.csv", parse_dates=["Date"] if "Date" in open("/tmp/kmlm_stitched_daily.csv").readline() else [0], index_col=0)
kmlm_stitched.columns = ["KMLM_stitched"]
panel = panel.join(kmlm_stitched, how="outer").sort_index()
print(f"After KMLM stitch: {panel.index[0].date()} -> {panel.index[-1].date()}, {len(panel.columns)} assets")

# ---- pull stitched GLD (FSAGX 1990->GC=F 2000->GLD 2004) ----
gld_stitched = pd.read_csv("/tmp/gld_stitched_daily_clean.csv", parse_dates=[0], index_col=0)
gld_stitched.columns = ["GLD"]
panel = panel.join(gld_stitched, how="outer").sort_index()
print(f"After clean GLD (GC=F+GLD only): {len(panel.columns)} assets, GLD coverage {gld_stitched.index[0].date()} -> {gld_stitched.index[-1].date()}")

# ---- map AGGR universe to proxy panel column names (KMLM_stitched used in place of WTMF/KMLM live) ----
AGGR_ALL = ["QQQ","IGM","SPMO","XLE","XRT","SMH","COWZ","AVUV","MOO","RWJ","SPHQ","XMMO","XMHQ"]
# Long-history = real ETF inception <= 2008-12-31
AGGR_LONG = ["QQQ","IGM","XLE","XRT","SMH","MOO","RWJ","SPHQ","XMMO","XMHQ"]
# Picked = appeared >5% of months in 2020+ pick-frequency analysis
AGGR_PICKED = ["QQQ","SMH","XLE","XRT","XMHQ","RWJ","MOO"]

UNIVERSES = {
    "AGGR_orig_proxy":             AGGR_ALL,
    "AGGR_long_proxy":             AGGR_LONG,
    "AGGR_picked_proxy":           AGGR_PICKED,
    "AGGR_orig_+GLD":              AGGR_ALL + ["GLD"],
    "AGGR_orig_+GLD_+KMLM":        AGGR_ALL + ["GLD","KMLM_stitched"],
    "AGGR_picked_+GLD":            AGGR_PICKED + ["GLD"],
    "AGGR_picked_+GLD_+KMLM":      AGGR_PICKED + ["GLD","KMLM_stitched"],
    "AGGR_picked_+GLD_+KMLM_+TLT": AGGR_PICKED + ["GLD","KMLM_stitched","TLT"],
    "AGGR_long_+GLD_+KMLM":        AGGR_LONG + ["GLD","KMLM_stitched"],
    "Keller_DAA_G12_proxy":        ["SPY","IWM","QQQ","EFA","EEM","VNQ","DBC","GLD","TLT","IEF","SHV"],  # VGK, EWJ, HYG, LQD missing
    "Faber_IVY_5_proxy":           ["SPY","EFA","IEF","VNQ","DBC"],
    "Faber_IVY_13_proxy":          ["SPY","IWM","EFA","EEM","VNQ","DBC","GLD","IEF","TLT","XLE","KMLM_stitched"],
}

CASH = "SHV"
CORR_LOOKBACK_DAYS = 252
HOLD_BUFFER = 1.0

# ---- engine ----
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

def month_end_dates(idx, start, end):
    sub = idx[(idx >= start) & (idx <= end)]
    if len(sub) == 0: return []
    return pd.DataFrame({"x":1}, index=sub).groupby(pd.Grouper(freq="ME")).tail(1).index.to_list()

def segment_returns(close, weights_map, dates, end):
    ffill = close.ffill()
    daily = ffill.pct_change()
    period_idx = close.index[(close.index >= dates[0]) & (close.index <= end)]
    out = pd.Series(0.0, index=period_idx, dtype=float)
    for i, d in enumerate(dates):
        nxt = dates[i+1] if i+1 < len(dates) else end
        seg = period_idx[(period_idx > d) & (period_idx <= nxt)]
        if len(seg) == 0: continue
        w = weights_map.get(d, {})
        if not w: continue
        cols = [c for c in w if c in daily.columns]
        if not cols: continue
        sub = daily.loc[seg, cols].mul(pd.Series({k: w[k] for k in cols}), axis=1)
        out.loc[seg] = sub.sum(axis=1, min_count=1).fillna(0.0)
    return out

def perf(daily, eq):
    if daily.empty: return {}
    days = (eq.index[-1] - eq.index[0]).days
    yrs = days/365.25
    cagr = (eq.iloc[-1]/eq.iloc[0])**(1/yrs)-1 if yrs>0 else float("nan")
    vol = daily.std(ddof=0)*np.sqrt(252)
    sharpe = (daily.mean()*252)/vol if vol>0 else float("nan")
    rm = eq.cummax()
    mdd = (eq/rm-1).min()
    return {"total_return": eq.iloc[-1]/eq.iloc[0]-1, "cagr": cagr, "vol": vol, "sharpe": sharpe, "max_drawdown": mdd}

def run_pair(close_panel, universe, start, end, buffer=HOLD_BUFFER):
    cols = [c for c in universe if c in close_panel.columns] + [CASH]
    cols = list(dict.fromkeys(cols))
    close = close_panel[cols]
    dates = month_end_dates(close.index, start, end)
    monthly = close.resample("ME").last()
    weights_map = {}
    prev_pair = None
    for d in dates:
        m = monthly.loc[:d]
        score = faber_sma(m)
        avail = [t for t in universe if t in score.index and pd.notna(score[t]) and pd.notna(close.loc[d].get(t, np.nan))]
        if not avail:
            weights_map[d] = {CASH: 1.0} if CASH in close.columns and pd.notna(close.loc[d].get(CASH, np.nan)) else {}
            prev_pair = None
            continue
        score_avail = score.loc[avail]
        z_avail = zscore(score_avail)
        ranked = score_avail.sort_values(ascending=False)
        half_n = max(2, (len(ranked)+1)//2)
        positive = ranked.iloc[:half_n][lambda s: s>0]
        if len(positive) < 2:
            if len(positive)==1:
                weights_map[d] = {positive.index[0]:1.0}
            else:
                weights_map[d] = {CASH:1.0} if CASH in close.columns and pd.notna(close.loc[d].get(CASH, np.nan)) else {}
            prev_pair = None
            continue
        candidates = list(positive.index)
        new_pair = lowest_corr_pair(close.loc[:d, candidates], candidates)
        if new_pair is None:
            weights_map[d] = {candidates[0]:1.0}
            prev_pair = None
            continue
        if prev_pair is not None and buffer > 1e-9:
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
                if z_swap - z_prior < buffer:
                    new_set.remove(swap_target)
                    new_set.append(prior)
            new_pair = tuple(new_set[:2])
        weights_map[d] = {new_pair[0]:0.5, new_pair[1]:0.5}
        prev_pair = new_pair
    daily = segment_returns(close, weights_map, dates, end)
    return daily, weights_map

def first_full_history(panel, universe):
    sub = panel[[t for t in universe if t in panel.columns]]
    fv = sub.apply(lambda c: c.first_valid_index())
    return fv.max() + pd.DateOffset(months=12)

# ---- run ----
common_start = pd.Timestamp("1997-01-01")
end = panel.index[-1]
results = {}
weights_history = {}
print()
print("="*80)
print(f"Running each universe from earliest valid start (max with universe + 12mo warmup)")
print("="*80)
for name, univ in UNIVERSES.items():
    missing = [t for t in univ if t not in panel.columns]
    if missing:
        print(f"  {name}: SKIP missing {missing}")
        continue
    start_use = max(common_start, first_full_history(panel, univ))
    if start_use >= end:
        print(f"  {name}: SKIP no window")
        continue
    daily, wmap = run_pair(panel, univ, start_use, end)
    results[name] = daily
    weights_history[name] = wmap
    print(f"  {name}: {start_use.date()} -> {end.date()}  ({(end-start_use).days/365.25:.1f}y)")

# Per-universe summary (own start)
rows = []
for name, daily in results.items():
    if daily.empty: continue
    eq = (1.0+daily).cumprod()*100_000.0
    m = perf(daily, eq)
    m["strategy"] = name
    m["start"] = daily.index[0].date().isoformat()
    m["years"] = (daily.index[-1]-daily.index[0]).days/365.25
    rows.append(m)
summary = pd.DataFrame(rows)[["strategy","start","years","total_return","cagr","vol","sharpe","max_drawdown"]]
summary = summary.sort_values("sharpe", ascending=False).reset_index(drop=True)
print()
print("Per-universe own-start summary:")
print(summary.to_string(index=False, float_format=lambda x: f"{x:.4f}"))
summary.to_csv("/tmp/universe_sweep_v2_summary.csv", index=False)

# Apples-to-apples
common = max(d.index[0] for d in results.values())
print()
print(f"Apples-to-apples aligned start: {common.date()}")
rows2 = []
for name, daily in results.items():
    sub = daily.loc[daily.index >= common]
    if sub.empty: continue
    eq = (1.0+sub).cumprod()*100_000.0
    m = perf(sub, eq)
    m["strategy"] = name
    rows2.append(m)
aligned = pd.DataFrame(rows2)[["strategy","total_return","cagr","vol","sharpe","max_drawdown"]]
aligned = aligned.sort_values("sharpe", ascending=False).reset_index(drop=True)
print(aligned.to_string(index=False, float_format=lambda x: f"{x:.4f}"))
aligned.to_csv("/tmp/universe_sweep_v2_aligned.csv", index=False)

# Pick freq for top universes
print()
print("="*80)
print("Pick frequency (own start; %% of months):")
print("="*80)
for name, wmap in weights_history.items():
    total = len(wmap)
    if total == 0: continue
    counts = {}
    for d, w in wmap.items():
        for t in w: counts[t] = counts.get(t,0)+1
    freq = pd.Series({t: counts[t]/total*100 for t in counts}).sort_values(ascending=False)
    print(f"\n{name} ({total} months):")
    for t, p in freq.items():
        print(f"  {t:14s} {p:5.1f}%  {'#'*int(p/3)}")
