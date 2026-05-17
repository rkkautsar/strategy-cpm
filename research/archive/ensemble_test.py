"""
Strategy-strategy correlations + ensemble blends to find the free lunch.

PROD = AGGR+GLD+TLT, full cherry config + 10bps + 10% VT.
Peers: SPY, 60/40, Permanent Portfolio, Faber GTAA5, Antonacci GEM, Keller VAA G4, Keller HAA, ARP inv-vol.

Test ensembles:
  - Equal weight (1/N)
  - Inverse-vol weight
  - Risk parity (target equal vol contribution)
  - Sharpe-weighted (oracle weights — for upper bound)

Want to find: blends that beat PROD alone on Sharpe.
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
PROD_UNIVERSE = AGGR_ALL + ["GLD", "TLT"]
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

def perf(daily):
    if daily.empty: return {}
    eq = (1.0+daily).cumprod()*100_000.0
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


def run_pair_engine(start, end, universe, apply_vt=True, cost_bps=COST_BPS):
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


# Peer strategies (same as final_benchmark)
def faber_gtaa5(start, end):
    universe = ["SPY","EFA","IEF","VNQ","DBC"]
    cols = [c for c in universe if c in panel.columns] + [CASH]
    close = panel[cols]; monthly = close.resample("ME").last()
    monthly_idx = pd.DataFrame({"x":1}, index=close.index).groupby(pd.Grouper(freq="ME")).tail(1)
    dates = monthly_idx.index[(monthly_idx.index>=start)&(monthly_idx.index<=end)].tolist()
    weights_map = {}
    for d in dates:
        m = monthly.loc[:d]; sma = m.rolling(10).mean().iloc[-1]; last = m.iloc[-1]
        in_u = [a for a in universe if a in last.index and pd.notna(sma.get(a)) and pd.notna(last[a]) and last[a] > sma[a]]
        w = {a: 0.20 for a in in_u}
        if 5 - len(in_u) > 0: w[CASH] = 0.20*(5-len(in_u))
        weights_map[d] = w if w else {CASH: 1.0}
    daily_ret = close.ffill().pct_change()
    out = pd.Series(0.0, index=close.index)
    for i, d in enumerate(dates):
        nxt = dates[i+1] if i+1 < len(dates) else end
        seg = close.index[(close.index > d) & (close.index <= nxt)]
        w = weights_map.get(d, {})
        if not w: continue
        cs = [c for c in w if c in daily_ret.columns]
        if not cs: continue
        out.loc[seg] = daily_ret.loc[seg, cs].mul(pd.Series({k: w[k] for k in cs}), axis=1).sum(axis=1, min_count=1).fillna(0.0)
    return out.loc[(out.index>=start)&(out.index<=end)]

def antonacci_gem(start, end):
    universe = ["SPY","EFA","SHV","AGG_stitched"]
    cols = [c for c in universe if c in panel.columns]
    close = panel[cols]; monthly = close.resample("ME").last()
    monthly_idx = pd.DataFrame({"x":1}, index=close.index).groupby(pd.Grouper(freq="ME")).tail(1)
    dates = monthly_idx.index[(monthly_idx.index>=start)&(monthly_idx.index<=end)].tolist()
    weights_map = {}
    for d in dates:
        m = monthly.loc[:d]
        if len(m) < 13: weights_map[d] = {CASH:1.0}; continue
        spy_12 = m["SPY"].iloc[-1]/m["SPY"].iloc[-13]-1
        cash_12 = m["SHV"].iloc[-1]/m["SHV"].iloc[-13]-1
        if spy_12 <= cash_12:
            weights_map[d] = {"AGG_stitched":1.0}
        else:
            efa_12 = m["EFA"].iloc[-1]/m["EFA"].iloc[-13]-1
            weights_map[d] = {"SPY":1.0} if spy_12 >= efa_12 else {"EFA":1.0}
    daily_ret = close.ffill().pct_change()
    out = pd.Series(0.0, index=close.index)
    for i, d in enumerate(dates):
        nxt = dates[i+1] if i+1 < len(dates) else end
        seg = close.index[(close.index > d) & (close.index <= nxt)]
        w = weights_map.get(d, {})
        if not w: continue
        cs = [c for c in w if c in daily_ret.columns]
        if not cs: continue
        out.loc[seg] = daily_ret.loc[seg, cs].mul(pd.Series({k: w[k] for k in cs}), axis=1).sum(axis=1, min_count=1).fillna(0.0)
    return out.loc[(out.index>=start)&(out.index<=end)]

def keller_vaa_g4(start, end):
    offensive = ["SPY","EFA","EEM","AGG_stitched"]
    defensive = ["SHV","IEF"]
    cols = list(dict.fromkeys(offensive + defensive))
    cols = [c for c in cols if c in panel.columns]
    close = panel[cols]; monthly = close.resample("ME").last()
    monthly_idx = pd.DataFrame({"x":1}, index=close.index).groupby(pd.Grouper(freq="ME")).tail(1)
    dates = monthly_idx.index[(monthly_idx.index>=start)&(monthly_idx.index<=end)].tolist()
    weights_map = {}
    for d in dates:
        m = monthly.loc[:d]
        scores_off = {a: sig_13612W(m[a]) for a in offensive if a in m.columns}
        if any(pd.isna(v) for v in scores_off.values()):
            weights_map[d] = {CASH:1.0}; continue
        if all(v > 0 for v in scores_off.values()):
            best = max(scores_off, key=scores_off.get)
            weights_map[d] = {best:1.0}
        else:
            sd = {a: sig_13612W(m[a]) for a in defensive if a in m.columns}
            valid = {k:v for k,v in sd.items() if pd.notna(v)}
            best = max(valid, key=valid.get) if valid else CASH
            weights_map[d] = {best:1.0}
    daily_ret = close.ffill().pct_change()
    out = pd.Series(0.0, index=close.index)
    for i, d in enumerate(dates):
        nxt = dates[i+1] if i+1 < len(dates) else end
        seg = close.index[(close.index > d) & (close.index <= nxt)]
        w = weights_map.get(d, {})
        if not w: continue
        cs = [c for c in w if c in daily_ret.columns]
        if not cs: continue
        out.loc[seg] = daily_ret.loc[seg, cs].mul(pd.Series({k: w[k] for k in cs}), axis=1).sum(axis=1, min_count=1).fillna(0.0)
    return out.loc[(out.index>=start)&(out.index<=end)]

def keller_haa_balanced(start, end):
    canary = ["TIP", "AGG_stitched"]
    offensive = ["SPY","IWM","VEA","VWO","VNQ","DBC","IEF","TLT"]
    defensive = ["SHV","IEF"]
    cols = list(dict.fromkeys(canary + offensive + defensive))
    cols = [c for c in cols if c in panel.columns]
    close = panel[cols]; monthly = close.resample("ME").last()
    monthly_idx = pd.DataFrame({"x":1}, index=close.index).groupby(pd.Grouper(freq="ME")).tail(1)
    dates = monthly_idx.index[(monthly_idx.index>=start)&(monthly_idx.index<=end)].tolist()
    weights_map = {}
    for d in dates:
        m = monthly.loc[:d]
        canary_scores = {a: sig_13612W(m[a]) for a in canary if a in m.columns}
        if any(pd.isna(v) for v in canary_scores.values()):
            weights_map[d] = {CASH:1.0}; continue
        if all(v > 0 for v in canary_scores.values()):
            off_scores = {a: sig_13612W(m[a]) for a in offensive if a in m.columns}
            valid_pos = sorted([a for a, v in off_scores.items() if pd.notna(v) and v > 0],
                               key=lambda a: off_scores[a], reverse=True)[:4]
            if not valid_pos: weights_map[d] = {CASH:1.0}; continue
            w = 1.0/len(valid_pos)
            weights_map[d] = {a: w for a in valid_pos}
        else:
            def_scores = {a: sig_13612W(m[a]) for a in defensive if a in m.columns}
            valid = {k:v for k,v in def_scores.items() if pd.notna(v)}
            if not valid: weights_map[d] = {CASH:1.0}; continue
            best = max(valid, key=valid.get)
            weights_map[d] = {best: 1.0}
    daily_ret = close.ffill().pct_change()
    out = pd.Series(0.0, index=close.index)
    for i, d in enumerate(dates):
        nxt = dates[i+1] if i+1 < len(dates) else end
        seg = close.index[(close.index > d) & (close.index <= nxt)]
        w = weights_map.get(d, {})
        if not w: continue
        cs = [c for c in w if c in daily_ret.columns]
        if not cs: continue
        out.loc[seg] = daily_ret.loc[seg, cs].mul(pd.Series({k: w[k] for k in cs}), axis=1).sum(axis=1, min_count=1).fillna(0.0)
    return out.loc[(out.index>=start)&(out.index<=end)]

def permanent_portfolio(start, end):
    cols = ["SPY","TLT","GLD","SHV"]
    cols = [c for c in cols if c in panel.columns]
    close = panel[cols]
    monthly_idx = pd.DataFrame({"x":1}, index=close.index).groupby(pd.Grouper(freq="ME")).tail(1)
    dates = monthly_idx.index[(monthly_idx.index>=start)&(monthly_idx.index<=end)].tolist()
    daily_ret = close.ffill().pct_change()
    out = pd.Series(0.0, index=close.index)
    for i, d in enumerate(dates):
        nxt = dates[i+1] if i+1 < len(dates) else end
        seg = close.index[(close.index > d) & (close.index <= nxt)]
        out.loc[seg] = daily_ret.loc[seg].mul(pd.Series({a:0.25 for a in cols}), axis=1).sum(axis=1).fillna(0.0)
    return out.loc[(out.index>=start)&(out.index<=end)]

def sixty_forty(start, end):
    cols = ["SPY", "IEF"]
    close = panel[cols]
    monthly_idx = pd.DataFrame({"x":1}, index=close.index).groupby(pd.Grouper(freq="ME")).tail(1)
    dates = monthly_idx.index[(monthly_idx.index>=start)&(monthly_idx.index<=end)].tolist()
    daily_ret = close.ffill().pct_change()
    out = pd.Series(0.0, index=close.index)
    for i, d in enumerate(dates):
        nxt = dates[i+1] if i+1 < len(dates) else end
        seg = close.index[(close.index > d) & (close.index <= nxt)]
        out.loc[seg] = daily_ret.loc[seg, ["SPY","IEF"]].mul(pd.Series({"SPY":0.6,"IEF":0.4}), axis=1).sum(axis=1).fillna(0.0)
    return out.loc[(out.index>=start)&(out.index<=end)]

def spy_bh(start, end):
    return panel["SPY"].ffill().pct_change().loc[start:end].fillna(0.0)


# ============================================================
end = panel.index[-1]
start = pd.Timestamp("2001-08-30")

print("Running PROD strategy (AGGR+GLD+TLT)...")
prod_daily = run_pair_engine(start, end, PROD_UNIVERSE)

strategies = {
    "PROD":          prod_daily,
    "Faber_GTAA5":   faber_gtaa5(start, end),
    "Antonacci_GEM": antonacci_gem(start, end),
    "Keller_VAA_G4": keller_vaa_g4(start, end),
    "Keller_HAA":    keller_haa_balanced(start, end),
    "Permanent_PP":  permanent_portfolio(start, end),
    "60/40":         sixty_forty(start, end),
    "SPY_BH":        spy_bh(start, end),
}

# Align to common index
common_idx = None
for s in strategies.values():
    common_idx = s.index if common_idx is None else common_idx.intersection(s.index)
df_strats = pd.DataFrame({k: v.reindex(common_idx).fillna(0.0) for k, v in strategies.items()})

# Per-strategy stats
print()
print("="*80); print("Per-strategy stats"); print("="*80)
rows = []
for name in df_strats.columns:
    m = perf(df_strats[name]); m["strategy"] = name; rows.append(m)
print(pd.DataFrame(rows)[["strategy","cagr","vol","sharpe","max_drawdown"]].sort_values("sharpe", ascending=False).to_string(index=False, float_format=lambda x: f"{x:.4f}"))

# Correlation matrix (daily returns)
print()
print("="*80); print("Daily-return correlation matrix"); print("="*80)
corr = df_strats.corr()
print(corr.to_string(float_format=lambda x: f"{x:.3f}"))

# Average pairwise corr to PROD
prod_corr = corr["PROD"].drop("PROD").sort_values()
print()
print("Strategies sorted by correlation TO PROD (lowest = best diversifier):")
for s, c in prod_corr.items():
    print(f"  {s:18s} {c:.3f}")


# ============================================================
# Ensembles
# ============================================================
print()
print("="*80); print("Ensemble blends (PROD + N peers)"); print("="*80)

def ensemble_perf(weights_dict, df):
    cols = list(weights_dict.keys())
    blended = (df[cols] * pd.Series(weights_dict)).sum(axis=1)
    m = perf(blended)
    return m, blended

def equal_weight(names):
    return {n: 1.0/len(names) for n in names}

def inv_vol_weight(df, names, lookback=252):
    vols = df[names].iloc[-lookback:].std() * np.sqrt(252)
    inv = 1.0/vols; w = inv/inv.sum()
    return w.to_dict()

# Test ensembles using full-period vol for inv-vol weighting (forward-looking — for upper bound)
ensembles = {
    "PROD only":                          {"PROD": 1.0},
    "PROD+PP (50/50)":                    equal_weight(["PROD","Permanent_PP"]),
    "PROD+60/40 (50/50)":                 equal_weight(["PROD","60/40"]),
    "PROD+VAA (50/50)":                   equal_weight(["PROD","Keller_VAA_G4"]),
    "PROD+HAA (50/50)":                   equal_weight(["PROD","Keller_HAA"]),
    "PROD+Faber (50/50)":                 equal_weight(["PROD","Faber_GTAA5"]),
    "PROD+VAA+HAA (1/3 each)":            equal_weight(["PROD","Keller_VAA_G4","Keller_HAA"]),
    "PROD+PP+60/40 (1/3 each)":           equal_weight(["PROD","Permanent_PP","60/40"]),
    "PROD+VAA+HAA+PP (1/4 each)":         equal_weight(["PROD","Keller_VAA_G4","Keller_HAA","Permanent_PP"]),
    "All 4 TAA (PROD+VAA+HAA+Faber)":     equal_weight(["PROD","Keller_VAA_G4","Keller_HAA","Faber_GTAA5"]),
    "70 PROD + 30 PP":                    {"PROD":0.7,"Permanent_PP":0.3},
    "70 PROD + 30 VAA":                   {"PROD":0.7,"Keller_VAA_G4":0.3},
    "70 PROD + 15 PP + 15 VAA":           {"PROD":0.7,"Permanent_PP":0.15,"Keller_VAA_G4":0.15},
    "Inv-vol PROD+PP":                    inv_vol_weight(df_strats, ["PROD","Permanent_PP"]),
    "Inv-vol PROD+VAA+HAA+PP":            inv_vol_weight(df_strats, ["PROD","Keller_VAA_G4","Keller_HAA","Permanent_PP"]),
}

rows = []
blended_series = {}
for name, w in ensembles.items():
    m, b = ensemble_perf(w, df_strats)
    m["ensemble"] = name
    rows.append(m)
    blended_series[name] = b
edf = pd.DataFrame(rows)[["ensemble","cagr","vol","sharpe","max_drawdown"]].sort_values("sharpe", ascending=False)
print(edf.to_string(index=False, float_format=lambda x: f"{x:.4f}"))

# Save
edf.to_csv("/tmp/ensemble_results.csv", index=False)
corr.to_csv("/tmp/ensemble_corr.csv")
