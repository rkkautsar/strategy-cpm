"""
MR-filtered KMLM as overlay (not as universe candidate).

Interpretation: KMLM has long-term mean reversion. When 6m-1 < 0 AND 12m < 10%,
the bet is that it bounces back. The engine's own momentum filter would never select
KMLM in this state, so we override with a fixed sleeve.

Implementation:
  - Run normal PROD on AGGR+GLD+TLT (no KMLM)
  - When MR conditions met that month, allocate X% of capital to KMLM, rest scaled down
  - X = 10%, 20%, 30% (sweep)

Also test: maybe the right MR signal is rougher (just 6m-1<0).
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

CASH = "SHV"; SAFE_POOL = ["BIL", "SHV", "SHY", "IEF"]
AGGR_ALL = ["QQQ","IGM","SPMO","XLE","XRT","SMH","COWZ","AVUV","MOO","RWJ","SPHQ","XMMO","XMHQ"]
PROD_UNIVERSE = AGGR_ALL + ["GLD", "TLT"]
CANARY_ASSETS = ["SPY", "TIP"]
BUFFER = 3.0; CORR_LOOKBACK = 378
TARGET_VOL = 0.10; VOL_LOOKBACK = 63; MAX_LEV = 1.5
COST_BPS = 10
MR_TICKER = "KMLM_stitched"


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
    if eq is None: eq = (1.0+daily).cumprod()*100_000.0
    days = (eq.index[-1]-eq.index[0]).days; yrs = days/365.25
    cagr = (eq.iloc[-1]/eq.iloc[0])**(1/yrs)-1 if yrs>0 else float("nan")
    vol = daily.std(ddof=0)*np.sqrt(252)
    sharpe = (daily.mean()*252)/vol if vol>0 else float("nan")
    rm = eq.cummax(); mdd = (eq/rm-1).min()
    return {"cagr": cagr, "vol": vol, "sharpe": sharpe, "max_drawdown": mdd}


def mr_signal(monthly_panel, sig_d, mode="mr_and_cap"):
    """Returns True if MR allocation should fire."""
    if MR_TICKER not in monthly_panel.columns: return False
    p = monthly_panel.loc[:sig_d, MR_TICKER].dropna()
    if len(p) < 14: return False
    r6_1 = p.iloc[-2] / p.iloc[-8] - 1
    r12 = p.iloc[-1] / p.iloc[-13] - 1
    if mode == "mr_only":     return r6_1 < 0
    if mode == "cap_only":    return r12 < 0.10
    if mode == "mr_and_cap":  return (r6_1 < 0) and (r12 < 0.10)
    if mode == "deep_mr":     return r6_1 < -0.05  # need >=5% drawdown over 6m-1
    return False


def compute_signal(monthly_panel, close_panel, sig_d, prev_pair, base_universe):
    m = monthly_panel.loc[:sig_d]
    on = True
    for c in CANARY_ASSETS:
        if c in m.columns:
            s = sig_13612W(m[c])
            if pd.isna(s) or s <= 0: on = False; break
    safe = best_safe(monthly_panel, sig_d, SAFE_POOL) or CASH
    if not on: return {safe: 1.0}, None, on
    score = faber_sma_xs(m)
    avail = [t for t in base_universe if t in score.index and pd.notna(score[t]) and pd.notna(close_panel.loc[sig_d].get(t, np.nan) if sig_d in close_panel.index else np.nan)]
    if not avail: return {safe: 1.0}, None, on
    sa = score.loc[avail]; za = zscore(sa)
    ranked = sa.sort_values(ascending=False)
    positive = ranked.iloc[:max(2,(len(ranked)+1)//2)][lambda s: s>0]
    if len(positive) < 2:
        if len(positive) == 1:
            return {positive.index[0]: 0.5, safe: 0.5}, None, on
        return {safe: 1.0}, None, on
    candidates = list(positive.index)
    new_pick = lowest_corr_pair(close_panel.loc[:sig_d, candidates], candidates, CORR_LOOKBACK)
    if new_pick is None: return {candidates[0]: 1.0}, None, on
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
    return {new_pick[0]: 0.5, new_pick[1]: 0.5}, new_pick, on


def run_with_mr_overlay(start, end, base_universe, mr_alloc_pct, mr_mode, apply_vt=True, cost_bps=COST_BPS):
    """
    mr_alloc_pct: fraction of capital reserved for KMLM when MR fires (e.g. 0.10, 0.20, 0.30).
    When MR fires this month, weights = (1-mr_alloc_pct)*pair + mr_alloc_pct*KMLM.
    When MR doesn't fire, weights = pair as usual.
    """
    cols = list(dict.fromkeys(base_universe + [MR_TICKER] + SAFE_POOL + CANARY_ASSETS + [CASH]))
    cols = [c for c in cols if c in panel.columns]
    close = panel[cols]
    monthly_idx = pd.DataFrame({"x":1}, index=close.index).groupby(pd.Grouper(freq="ME")).tail(1)
    signal_dates = monthly_idx.index[(monthly_idx.index >= start) & (monthly_idx.index <= end)].tolist()
    weights_history = []; prev_pair = None
    n_mr_fired = 0
    for i, sig_d in enumerate(signal_dates):
        monthly_for_signal = close.loc[:sig_d].resample("ME").last()
        w, new_pair, canary_on = compute_signal(monthly_for_signal, close, sig_d, prev_pair, base_universe)
        prev_pair = new_pair
        # Apply MR overlay (only when canary is on AND MR fires)
        mr_fires = canary_on and mr_alloc_pct > 0 and mr_signal(monthly_for_signal, sig_d, mr_mode) and MR_TICKER in close.columns and pd.notna(close.loc[sig_d].get(MR_TICKER, np.nan))
        if mr_fires:
            n_mr_fired += 1
            scale = 1.0 - mr_alloc_pct
            w_scaled = {k: v * scale for k, v in w.items()}
            w_scaled[MR_TICKER] = w_scaled.get(MR_TICKER, 0.0) + mr_alloc_pct
            w = w_scaled
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
    return daily.loc[(daily.index >= start) & (daily.index <= end)], n_mr_fired, len(signal_dates)


end = panel.index[-1]
start = pd.Timestamp("2001-08-30")

print("="*80)
print("Mean-reversion KMLM OVERLAY on PROD (AGGR+GLD+TLT)")
print(f"Window: {start.date()} -> {end.date()}")
print("="*80)

variants = []
# Baseline (no overlay)
variants.append(("Baseline (no MR overlay)", 0.0, "mr_and_cap"))

# Sweep alloc % x mode
for mode in ["mr_only", "cap_only", "mr_and_cap", "deep_mr"]:
    for alloc in [0.10, 0.20, 0.30]:
        variants.append((f"{int(alloc*100)}%KMLM-MR ({mode})", alloc, mode))

rows = []
for name, alloc, mode in variants:
    daily, fired, total = run_with_mr_overlay(start, end, PROD_UNIVERSE, alloc, mode)
    if daily.empty: continue
    eq = (1.0+daily).cumprod()*100_000.0
    m = perf(daily, eq); m["variant"] = name
    m["mr_fired_pct"] = round(100*fired/total, 1) if total else 0
    rows.append(m)
df = pd.DataFrame(rows)[["variant","mr_fired_pct","cagr","vol","sharpe","max_drawdown"]]
df = df.sort_values("sharpe", ascending=False).reset_index(drop=True)
print(df.to_string(index=False, float_format=lambda x: f"{x:.4f}"))

# Test best ones with PP 30% ensemble
print()
print("="*80)
print("Best 3 + ensemble with PP (70/30)")
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
top3 = df.head(3)
ens_rows = []
for _, row in top3.iterrows():
    name = row["variant"]
    # find original alloc/mode
    for vname, valloc, vmode in variants:
        if vname == name:
            daily, _, _ = run_with_mr_overlay(start, end, PROD_UNIVERSE, valloc, vmode)
            common = daily.index.intersection(pp.index)
            blended = 0.7 * daily.reindex(common).fillna(0.0) + 0.3 * pp.reindex(common).fillna(0.0)
            m = perf(blended); m["variant"] = f"70%[{name}]+30%PP"
            ens_rows.append(m)
            break
print(pd.DataFrame(ens_rows)[["variant","cagr","vol","sharpe","max_drawdown"]].to_string(index=False, float_format=lambda x: f"{x:.4f}"))
df.to_csv("/tmp/mf_mr_overlay.csv", index=False)
