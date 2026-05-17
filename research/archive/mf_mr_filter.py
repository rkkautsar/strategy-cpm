"""
Mean-reversion-filtered KMLM as universe candidate.

Filter: include KMLM only when both:
  - 6m-1 momentum (skip-1) < 0
  - 12m momentum < +10%

Implementation: at signal time, mask KMLM out of universe when filter fails.
The pair-engine treats it as if not in universe (won't pick it).

Test:
  A) AGGR+GLD+TLT (current PROD)
  B) AGGR+GLD+TLT+KMLM (always in)
  C) AGGR+GLD+TLT+KMLM(MR-filter)
  D) AGGR+GLD+TLT+KMLM(MR-only)  — just 6m-1<0 alone, no 12m cap
  E) AGGR+GLD+TLT+KMLM(12m<10% only)
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
tip_clean = pd.read_csv("/tmp/tip_stitched_daily.csv", parse_dates=[0], index_col=0); tip_clean.columns=["TIP_clean"]
panel = panel.join(gld, how="outer").join(kmlm, how="outer").join(tip_clean, how="outer").sort_index()
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
MR_FILTER_TICKER = "KMLM_stitched"


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

def perf(daily, eq=None):
    if daily.empty: return {}
    if eq is None:
        eq = (1.0+daily).cumprod()*100_000.0
    days = (eq.index[-1]-eq.index[0]).days; yrs = days/365.25
    cagr = (eq.iloc[-1]/eq.iloc[0])**(1/yrs)-1 if yrs>0 else float("nan")
    vol = daily.std(ddof=0)*np.sqrt(252)
    sharpe = (daily.mean()*252)/vol if vol>0 else float("nan")
    rm = eq.cummax(); mdd = (eq/rm-1).min()
    return {"cagr": cagr, "vol": vol, "sharpe": sharpe, "max_drawdown": mdd}


def mr_filter_kmlm(monthly_panel, sig_d, mode):
    """Returns True if KMLM should be included this month."""
    if mode == "always": return True
    if mode == "never":  return False
    if MR_FILTER_TICKER not in monthly_panel.columns: return True
    p = monthly_panel.loc[:sig_d, MR_FILTER_TICKER].dropna()
    if len(p) < 14: return True  # not enough history -> default include
    # 6m-1 momentum: price[t-1] / price[t-7] - 1
    r6_1 = p.iloc[-2] / p.iloc[-8] - 1
    # 12m momentum: price[t] / price[t-13] - 1
    r12 = p.iloc[-1] / p.iloc[-13] - 1
    if mode == "mr_only":         # 6m-1 < 0 only
        return r6_1 < 0
    if mode == "cap_only":        # 12m < 10% only
        return r12 < 0.10
    if mode == "mr_and_cap":      # both
        return (r6_1 < 0) and (r12 < 0.10)
    raise ValueError(mode)


def compute_signal(monthly_panel, close_panel, sig_d, prev_pair, base_universe, mr_mode):
    m = monthly_panel.loc[:sig_d]
    on = True
    for c in CANARY_ASSETS:
        if c in m.columns:
            s = sig_13612W(m[c])
            if pd.isna(s) or s <= 0: on = False; break
    safe = best_safe(monthly_panel, sig_d, SAFE_POOL) or CASH
    if not on: return {safe: 1.0}, None
    
    # Apply MR filter to dynamically build universe
    universe = list(base_universe)
    if MR_FILTER_TICKER in universe and not mr_filter_kmlm(monthly_panel, sig_d, mr_mode):
        universe.remove(MR_FILTER_TICKER)
    
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


def run_production(start, end, universe, mr_mode="always", apply_vt=True, cost_bps=COST_BPS):
    cols = list(dict.fromkeys(universe + SAFE_POOL + CANARY_ASSETS + [CASH]))
    cols = [c for c in cols if c in panel.columns]
    close = panel[cols]
    monthly_idx = pd.DataFrame({"x":1}, index=close.index).groupby(pd.Grouper(freq="ME")).tail(1)
    signal_dates = monthly_idx.index[(monthly_idx.index >= start) & (monthly_idx.index <= end)].tolist()
    weights_history = []; prev_pair = None
    n_kmlm_eligible = 0; n_kmlm_picked = 0
    for i, sig_d in enumerate(signal_dates):
        monthly_for_signal = close.loc[:sig_d].resample("ME").last()
        # diagnostics: MR filter outcome
        if MR_FILTER_TICKER in universe:
            if mr_filter_kmlm(monthly_for_signal, sig_d, mr_mode):
                n_kmlm_eligible += 1
        w, new_pair = compute_signal(monthly_for_signal, close, sig_d, prev_pair, universe, mr_mode)
        prev_pair = new_pair
        if MR_FILTER_TICKER in w:
            n_kmlm_picked += 1
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
    daily = daily.loc[(daily.index >= start) & (daily.index <= end)]
    return daily, n_kmlm_eligible, n_kmlm_picked, len(signal_dates)


end = panel.index[-1]
start = pd.Timestamp("2001-08-30")

variants = [
    ("AGGR+GLD+TLT (no KMLM)",          AGGR_ALL + ["GLD", "TLT"],                "always"),
    ("AGGR+GLD+TLT+KMLM (always)",      AGGR_ALL + ["GLD", "TLT", "KMLM_stitched"], "always"),
    ("AGGR+GLD+TLT+KMLM (MR 6m-1<0)",   AGGR_ALL + ["GLD", "TLT", "KMLM_stitched"], "mr_only"),
    ("AGGR+GLD+TLT+KMLM (cap 12m<10%)", AGGR_ALL + ["GLD", "TLT", "KMLM_stitched"], "cap_only"),
    ("AGGR+GLD+TLT+KMLM (MR + cap)",    AGGR_ALL + ["GLD", "TLT", "KMLM_stitched"], "mr_and_cap"),
]

print("="*80)
print("Mean-reversion filter on KMLM in PROD universe")
print(f"Window: {start.date()} -> {end.date()}")
print("="*80)
rows = []
for name, univ, mode in variants:
    print(f"  Running {name}...")
    daily, elig, picked, total = run_production(start, end, univ, mr_mode=mode)
    if daily.empty: continue
    eq = (1.0+daily).cumprod()*100_000.0
    m = perf(daily, eq); m["variant"] = name
    m["KMLM_eligible_pct"] = round(100*elig/total, 1) if "KMLM" in str(univ) and total else 0
    m["KMLM_picked_pct"] = round(100*picked/total, 1) if total else 0
    rows.append(m)
df = pd.DataFrame(rows)[["variant","KMLM_eligible_pct","KMLM_picked_pct","cagr","vol","sharpe","max_drawdown"]]
print()
print(df.to_string(index=False, float_format=lambda x: f"{x:.4f}"))
df.to_csv("/tmp/mf_mr_filter.csv", index=False)

# Also test with PP ensemble
print()
print("="*80)
print("With PP 30% ensemble (PROD 70 / PP 30)")
print("="*80)
def pp_daily(start, end):
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

pp = pp_daily(start, end)
ens_rows = []
for name, univ, mode in variants:
    daily, _, _, _ = run_production(start, end, univ, mr_mode=mode)
    common = daily.index.intersection(pp.index)
    blended = 0.7 * daily.reindex(common).fillna(0.0) + 0.3 * pp.reindex(common).fillna(0.0)
    eq = (1.0+blended).cumprod()*100_000.0
    m = perf(blended, eq); m["variant"] = f"70%[{name}]+30%PP"
    ens_rows.append(m)
print(pd.DataFrame(ens_rows)[["variant","cagr","vol","sharpe","max_drawdown"]].to_string(index=False, float_format=lambda x: f"{x:.4f}"))
