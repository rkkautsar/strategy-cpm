"""
#12 Alternative base benchmarks (extending the comparison floor)
#13 Canary pair sweep (does SPY+TIP specifically matter?)
#14 Diversifier swap on KMLM slot (DBMF, VNQ, DBC, PFF, etc.)

All against PRODUCTION config baseline.
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

# Fetch additional tickers
extra_tickers = [
    "BIL", "SHY",                           # safe pool expansion
    "DBMF", "PFF",                          # diversifiers
    "XLF", "XLK", "IWM", "MTUM",            # alternative canaries / equity proxies
]
for t in extra_tickers:
    if t not in panel.columns:
        try:
            d = yf.download(t, start="2000-01-01", end="2026-05-14", auto_adjust=True, progress=False, threads=False)
            if isinstance(d.columns, pd.MultiIndex):
                d = d["Close"]
            c = d["Close"] if "Close" in d.columns else d.iloc[:, 0]
            c = c.dropna(); c.name = t
            panel = panel.join(c.to_frame(), how="outer").sort_index()
            print(f"Fetched {t}: {c.index[0].date() if not c.empty else 'NONE'} -> {c.index[-1].date() if not c.empty else 'NONE'}")
        except Exception as e:
            print(f"  {t}: {e}")

CASH = "SHV"
SAFE_POOL = ["BIL", "SHV", "SHY", "IEF"]
AGGR_ALL = ["QQQ","IGM","SPMO","XLE","XRT","SMH","COWZ","AVUV","MOO","RWJ","SPHQ","XMMO","XMHQ"]
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


def compute_signal(monthly_panel, close_panel, sig_d, prev_pair, universe, canary_assets):
    m = monthly_panel.loc[:sig_d]
    on = True
    for c in canary_assets:
        if c in m.columns:
            s = sig_13612W(m[c])
            if pd.isna(s) or s <= 0: on = False; break
        else:
            return {CASH: 1.0}, None  # missing canary -> defensive
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


def run_production(start, end, universe, canary_assets, apply_vt=True, cost_bps=COST_BPS):
    cols = list(dict.fromkeys(universe + SAFE_POOL + canary_assets + [CASH]))
    cols = [c for c in cols if c in panel.columns]
    close = panel[cols]
    monthly_idx = pd.DataFrame({"x":1}, index=close.index).groupby(pd.Grouper(freq="ME")).tail(1)
    signal_dates = monthly_idx.index[(monthly_idx.index >= start) & (monthly_idx.index <= end)].tolist()
    weights_history = []; prev_pair = None
    for i, sig_d in enumerate(signal_dates):
        monthly_for_signal = close.loc[:sig_d].resample("ME").last()
        w, new_pair = compute_signal(monthly_for_signal, close, sig_d, prev_pair, universe, canary_assets)
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
start = pd.Timestamp("2001-08-30")

# ============================================================
# #12 Alternative base benchmarks (extending floor)
# ============================================================
print("\n" + "="*80)
print("#12 Alternative base benchmarks")
print("="*80)

def spy_bh(start, end):
    return panel["SPY"].ffill().pct_change().loc[start:end].fillna(0.0)

def sixty_forty(start, end, equity="SPY", bond="IEF", reb_freq="ME"):
    cols = [equity, bond]
    close = panel[cols]; monthly = close.resample("ME").last()
    monthly_idx = pd.DataFrame({"x":1}, index=close.index).groupby(pd.Grouper(freq=reb_freq)).tail(1)
    dates = monthly_idx.index[(monthly_idx.index>=start)&(monthly_idx.index<=end)].tolist()
    weights_map = {d: {equity: 0.6, bond: 0.4} for d in dates}
    daily_ret = close.ffill().pct_change()
    out = pd.Series(0.0, index=close.index)
    for i, d in enumerate(dates):
        nxt = dates[i+1] if i+1 < len(dates) else end
        seg = close.index[(close.index > d) & (close.index <= nxt)]
        out.loc[seg] = daily_ret.loc[seg, [equity, bond]].mul(pd.Series({equity:0.6,bond:0.4}), axis=1).sum(axis=1).fillna(0.0)
    return out.loc[(out.index>=start)&(out.index<=end)]

def permanent_portfolio(start, end):
    """Browne's Permanent Portfolio: 25% SPY, 25% TLT, 25% GLD, 25% SHV."""
    cols = ["SPY","TLT","GLD","SHV"]
    cols = [c for c in cols if c in panel.columns]
    close = panel[cols]
    monthly_idx = pd.DataFrame({"x":1}, index=close.index).groupby(pd.Grouper(freq="ME")).tail(1)
    dates = monthly_idx.index[(monthly_idx.index>=start)&(monthly_idx.index<=end)].tolist()
    weights_map = {d: {a: 0.25 for a in cols} for d in dates}
    daily_ret = close.ffill().pct_change()
    out = pd.Series(0.0, index=close.index)
    for i, d in enumerate(dates):
        nxt = dates[i+1] if i+1 < len(dates) else end
        seg = close.index[(close.index > d) & (close.index <= nxt)]
        out.loc[seg] = daily_ret.loc[seg].mul(pd.Series({a:0.25 for a in cols}), axis=1).sum(axis=1).fillna(0.0)
    return out.loc[(out.index>=start)&(out.index<=end)]

def ew_aggr_bh(start, end):
    """Equal-weight AGGR universe, monthly rebalanced."""
    universe = AGGR_ALL
    close = panel[universe]
    monthly_idx = pd.DataFrame({"x":1}, index=close.index).groupby(pd.Grouper(freq="ME")).tail(1)
    dates = monthly_idx.index[(monthly_idx.index>=start)&(monthly_idx.index<=end)].tolist()
    daily_ret = close.ffill().pct_change()
    out = pd.Series(0.0, index=close.index)
    for i, d in enumerate(dates):
        nxt = dates[i+1] if i+1 < len(dates) else end
        seg = close.index[(close.index > d) & (close.index <= nxt)]
        avail = [t for t in universe if t in close.columns and pd.notna(close.loc[d].get(t, np.nan))]
        if not avail: continue
        w = 1.0/len(avail)
        out.loc[seg] = daily_ret.loc[seg, avail].mul(w, axis=0).sum(axis=1).fillna(0.0)
    return out.loc[(out.index>=start)&(out.index<=end)]

def arp_simple(start, end):
    """Simple all-weather / risk-parity-ish: equal-vol-weighted SPY+TLT+GLD+DBC, no rebal beyond monthly."""
    universe = ["SPY","TLT","GLD","DBC"]
    universe = [u for u in universe if u in panel.columns]
    close = panel[universe]
    monthly_idx = pd.DataFrame({"x":1}, index=close.index).groupby(pd.Grouper(freq="ME")).tail(1)
    dates = monthly_idx.index[(monthly_idx.index>=start)&(monthly_idx.index<=end)].tolist()
    daily_ret = close.ffill().pct_change()
    out = pd.Series(0.0, index=close.index)
    for i, d in enumerate(dates):
        nxt = dates[i+1] if i+1 < len(dates) else end
        seg = close.index[(close.index > d) & (close.index <= nxt)]
        # inverse-vol weight on 60d realized vol
        vols = close.loc[:d, universe].pct_change().tail(60).std()
        if (vols > 0).all() and not vols.isna().any():
            inv_vol = 1.0/vols; w = inv_vol/inv_vol.sum()
            out.loc[seg] = daily_ret.loc[seg, universe].mul(w, axis=1).sum(axis=1).fillna(0.0)
    return out.loc[(out.index>=start)&(out.index<=end)]

print("Running benchmarks...")
benchmarks = {
    "SPY_BH":            spy_bh(start, end),
    "60/40_SPY_IEF":     sixty_forty(start, end, "SPY", "IEF"),
    "60/40_SPY_AGG":     sixty_forty(start, end, "SPY", "AGG_stitched"),
    "Permanent_25x4":    permanent_portfolio(start, end),
    "EW_AGGR_BH":        ew_aggr_bh(start, end),
    "ARP_invvol_4":      arp_simple(start, end),
}
# Run our PROD too
PROD_UNIVERSE = AGGR_ALL + ["GLD", "KMLM_stitched"]
PROD_CANARY = ["SPY", "TIP"]
benchmarks["PRODUCTION"] = run_production(start, end, PROD_UNIVERSE, PROD_CANARY)

rows = []
for name, daily in benchmarks.items():
    if daily.empty: continue
    eq = (1.0+daily).cumprod()*100_000.0
    m = perf(daily, eq); m["strategy"] = name
    rows.append(m)
df = pd.DataFrame(rows)[["strategy","cagr","vol","sharpe","max_drawdown"]]
df = df.sort_values("sharpe", ascending=False).reset_index(drop=True)
print(df.to_string(index=False, float_format=lambda x: f"{x:.4f}"))
df.to_csv("/tmp/div12_benchmarks.csv", index=False)


# ============================================================
# #13 Canary pair sweep
# ============================================================
print("\n" + "="*80)
print("#13 Canary pair sweep (full PROD config)")
print("="*80)

CANARY_PAIRS = [
    ("SPY+TIP",        ["SPY","TIP"]),
    ("SPY+AGG",        ["SPY","AGG_stitched"]),
    ("SPY+IEF",        ["SPY","IEF"]),
    ("SPY+TLT",        ["SPY","TLT"]),
    ("IWM+TIP",        ["IWM","TIP"]),
    ("QQQ+TIP",        ["QQQ","TIP"]),
    ("EEM+TIP",        ["EEM","TIP"]),
    ("VNQ+TIP",        ["VNQ","TIP"]),
    ("XLF+TIP",        ["XLF","TIP"]),
    ("MTUM+TIP",       ["MTUM","TIP"]),
    ("SPY_only",       ["SPY"]),
    ("TIP_only",       ["TIP"]),
    ("SPY+TIP+EEM",    ["SPY","TIP","EEM"]),
    ("SPY+TIP+VNQ",    ["SPY","TIP","VNQ"]),
]

rows = []
for name, canary in CANARY_PAIRS:
    print(f"  Running canary={name}...")
    daily = run_production(start, end, PROD_UNIVERSE, canary)
    if daily.empty: continue
    eq = (1.0+daily).cumprod()*100_000.0
    m = perf(daily, eq); m["canary"] = name
    rows.append(m)
df = pd.DataFrame(rows)[["canary","cagr","vol","sharpe","max_drawdown"]]
df = df.sort_values("sharpe", ascending=False).reset_index(drop=True)
print()
print(df.to_string(index=False, float_format=lambda x: f"{x:.4f}"))
df.to_csv("/tmp/div13_canary.csv", index=False)


# ============================================================
# #14 Diversifier swap (KMLM slot)
# ============================================================
print("\n" + "="*80)
print("#14 Diversifier swap on the KMLM slot in universe")
print("="*80)
DIVERSIFIER_OPTIONS = [
    ("AGGR+GLD_only",            AGGR_ALL + ["GLD"]),
    ("AGGR+GLD+KMLM(stitched)",  AGGR_ALL + ["GLD","KMLM_stitched"]),
    ("AGGR+GLD+DBMF",            AGGR_ALL + ["GLD","DBMF"]),
    ("AGGR+GLD+VNQ",             AGGR_ALL + ["GLD","VNQ"]),
    ("AGGR+GLD+DBC",             AGGR_ALL + ["GLD","DBC"]),
    ("AGGR+GLD+TLT",             AGGR_ALL + ["GLD","TLT"]),
    ("AGGR+GLD+PFF",             AGGR_ALL + ["GLD","PFF"]),
    ("AGGR+GLD+KMLM+DBMF",       AGGR_ALL + ["GLD","KMLM_stitched","DBMF"]),
    ("AGGR+GLD+KMLM+DBC",        AGGR_ALL + ["GLD","KMLM_stitched","DBC"]),
    ("AGGR+GLD+KMLM+TLT",        AGGR_ALL + ["GLD","KMLM_stitched","TLT"]),
]

rows = []
for name, univ in DIVERSIFIER_OPTIONS:
    print(f"  Running universe={name}...")
    # determine start based on this universe's earliest valid (12mo warmup)
    available = [t for t in univ if t in panel.columns]
    sub_panel = panel[available + PROD_CANARY + SAFE_POOL]
    fv = sub_panel.apply(lambda c: c.first_valid_index())
    earliest = fv.max() + pd.DateOffset(months=13)
    use_start = max(start, earliest)
    daily = run_production(use_start, end, univ, PROD_CANARY)
    if daily.empty: continue
    eq = (1.0+daily).cumprod()*100_000.0
    m = perf(daily, eq); m["universe"] = name
    m["start"] = daily.index[0].date().isoformat()
    m["years"] = round((daily.index[-1]-daily.index[0]).days/365.25, 1)
    rows.append(m)
df = pd.DataFrame(rows)[["universe","start","years","cagr","vol","sharpe","max_drawdown"]]
df = df.sort_values("sharpe", ascending=False).reset_index(drop=True)
print()
print(df.to_string(index=False, float_format=lambda x: f"{x:.4f}"))
df.to_csv("/tmp/div14_diversifiers.csv", index=False)
