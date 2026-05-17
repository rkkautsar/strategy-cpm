"""
FINAL PRODUCTION CONFIG benchmark.

Stack:
  Universe: AGGR_orig (13) + GLD (clean stitch) + KMLM (stitched)
  Engine: Pair_MSMAdist_50_50 + lowest 12m corr + hold buffer 3.0z + 378d corr lookback
  Canary: SPY+TIP both 13612W > 0
  Best-safe pool: SHV + IEF (only IEF/SHV materially used)
  Partial-safe: 1 positive momentum -> 50/50 with best safe; 0 positive -> 100% best safe
  Timing: month-end close signal, T+1 MOC execution
  Vol target: 10% annualized, 63d lookback, max 1.5x lev
  Cost: 10bps per side per turnover

Output: full-period perf, year-by-year, vs benchmarks.
"""
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

CASH = "SHV"; SAFE_POOL = ["SHV", "IEF"]
AGGR_ALL = ["QQQ","IGM","SPMO","XLE","XRT","SMH","COWZ","AVUV","MOO","RWJ","SPHQ","XMMO","XMHQ"]
UNIVERSE = AGGR_ALL + ["GLD", "KMLM_stitched"]
CANARY_ASSETS = ["SPY", "TIP"]
BUFFER = 3.0
CORR_LOOKBACK = 378
TARGET_VOL = 0.10
VOL_LOOKBACK = 63
MAX_LEV = 1.5
COST_BPS_PER_SIDE = 10  # 10 bps each side


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


def compute_signal(monthly_panel, close_panel, sig_d, prev_pair):
    """Standard pair-signal at sig_d (month-end close, frozen)."""
    m = monthly_panel.loc[:sig_d]
    on = True
    for c in CANARY_ASSETS:
        if c in m.columns:
            s = sig_13612W(m[c])
            if pd.isna(s) or s <= 0: on = False; break
    safe = best_safe(monthly_panel, sig_d, SAFE_POOL) or CASH
    if not on: return {safe: 1.0}, None
    score = faber_sma_xs(m)
    avail = [t for t in UNIVERSE if t in score.index and pd.notna(score[t]) and pd.notna(close_panel.loc[sig_d].get(t, np.nan) if sig_d in close_panel.index else np.nan)]
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


def run_production(start, end, apply_vol_target=True, cost_bps=COST_BPS_PER_SIDE):
    """Full production stack: frozen EOM signal + T+1 MOC + cost + vol target."""
    cols = list(dict.fromkeys(UNIVERSE + SAFE_POOL + CANARY_ASSETS + [CASH]))
    cols = [c for c in cols if c in panel.columns]
    close = panel[cols]
    
    # Month-end signal dates
    monthly_idx = pd.DataFrame({"x":1}, index=close.index).groupby(pd.Grouper(freq="ME")).tail(1)
    signal_dates = monthly_idx.index[(monthly_idx.index >= start) & (monthly_idx.index <= end)].tolist()
    
    # Generate weights with T+1 MOC execution
    weights_history = []  # (apply_from, end_apply, weights)
    prev_pair = None
    for i, sig_d in enumerate(signal_dates):
        monthly_for_signal = close.loc[:sig_d].resample("ME").last()
        w, new_pair = compute_signal(monthly_for_signal, close, sig_d, prev_pair)
        prev_pair = new_pair
        # T+1 execution
        future = close.index[close.index > sig_d]
        if len(future) < 2: continue
        exec_d = future[0]
        apply_from = future[1]
        if i+1 < len(signal_dates):
            next_sig = signal_dates[i+1]
            next_future = close.index[close.index > next_sig]
            if len(next_future) < 2:
                end_apply = end
            else:
                end_apply = next_future[1]
        else:
            end_apply = end
        weights_history.append((apply_from, end_apply, w))
    
    # Build per-day weights df + compute pre-cost daily
    all_assets = sorted({a for _, _, w in weights_history for a in w})
    df = pd.DataFrame(0.0, index=close.index, columns=all_assets)
    for apply_from, end_apply, w in weights_history:
        mask = (close.index >= apply_from) & (close.index < end_apply)
        for a, ww in w.items():
            if a in df.columns: df.loc[mask, a] = ww
    daily_ret = close.ffill().pct_change()
    common = [a for a in df.columns if a in daily_ret.columns]
    pre_cost_daily = (df[common] * daily_ret[common]).sum(axis=1, min_count=1).fillna(0.0)
    
    # Apply cost on each rebalance day
    turnovers = []
    for i in range(len(weights_history)):
        prev_w = weights_history[i-1][2] if i > 0 else {}
        curr_w = weights_history[i][2]
        keys = set(curr_w) | set(prev_w)
        turnover = sum(abs(curr_w.get(k, 0.0) - prev_w.get(k, 0.0)) for k in keys)
        turnovers.append(turnover)
        cost = turnover * cost_bps / 10000.0
        # apply cost on apply_from (first day of new weights = day after exec)
        apply_from = weights_history[i][0]
        if apply_from in pre_cost_daily.index:
            pre_cost_daily.loc[apply_from] -= cost
    
    daily = pre_cost_daily
    
    # Vol target overlay
    vt_daily = daily
    if apply_vol_target:
        realized = daily.rolling(VOL_LOOKBACK).std() * np.sqrt(252)
        scale = (TARGET_VOL / realized).clip(upper=MAX_LEV).shift(1).fillna(1.0)
        vt_daily = daily * scale
    
    daily_out = vt_daily.loc[(vt_daily.index >= start) & (vt_daily.index <= end)]
    return daily_out, turnovers


# ============================================================
# RUN
# ============================================================
end = panel.index[-1]
start = pd.Timestamp("2001-08-30")

print("="*80)
print("PRODUCTION STACK PERFORMANCE")
print("="*80)

variants = [
    ("Pre-cost, no vol-target",    {"apply_vol_target": False, "cost_bps": 0}),
    ("Pre-cost, 10% vol-target",   {"apply_vol_target": True,  "cost_bps": 0}),
    ("10bps cost, no vol-target",  {"apply_vol_target": False, "cost_bps": 10}),
    ("PRODUCTION (10bps + 10% VT)",{"apply_vol_target": True,  "cost_bps": 10}),
]

results = {}
for name, kwargs in variants:
    daily, turnovers = run_production(start, end, **kwargs)
    results[name] = daily
    eq = (1.0+daily).cumprod()*100_000.0
    m = perf(daily, eq); m["config"] = name
    m["mean_turnover"] = np.mean(turnovers)
    print(f"\n{name}:")
    print(f"  CAGR: {m['cagr']*100:.2f}%  Vol: {m['vol']*100:.1f}%  Sharpe: {m['sharpe']:.3f}  MaxDD: {m['max_drawdown']*100:.1f}%")
    print(f"  Mean monthly turnover: {m['mean_turnover']:.3f}")

# Year-by-year for production
print("\n" + "="*80)
print("YEAR-BY-YEAR — PRODUCTION CONFIG vs SPY")
print("="*80)
prod_daily = results["PRODUCTION (10bps + 10% VT)"]
spy_daily = panel["SPY"].ffill().pct_change().loc[start:end].fillna(0.0)
both = pd.concat([prod_daily.rename("PROD"), spy_daily.rename("SPY")], axis=1).dropna()
yr_prod = (1.0 + both["PROD"]).resample("YE").prod() - 1.0
yr_spy = (1.0 + both["SPY"]).resample("YE").prod() - 1.0
yr = pd.DataFrame({"SPY": yr_spy, "PROD": yr_prod})
yr["excess"] = yr["PROD"] - yr["SPY"]
yr.index = yr.index.year
print(yr.to_string(float_format=lambda x: f"{x*100:+6.2f}%"))
print()
print(f"Years PROD > SPY: {(yr['excess'] > 0).sum()}/{len(yr)}")
print(f"Mean excess: {yr['excess'].mean()*100:+.2f}%/yr")
print(f"Down-SPY years excess: {yr.loc[yr['SPY']<0, 'excess'].mean()*100:+.2f}%/yr ({(yr['SPY']<0).sum()} years)")
print(f"Up-SPY years excess:   {yr.loc[yr['SPY']>=0, 'excess'].mean()*100:+.2f}%/yr ({(yr['SPY']>=0).sum()} years)")

# Drawdown profile
prod_eq = (1.0+prod_daily).cumprod()*100_000.0
spy_eq = (1.0+spy_daily.loc[prod_daily.index]).cumprod()*100_000.0
prod_dd = prod_eq / prod_eq.cummax() - 1
spy_dd = spy_eq / spy_eq.cummax() - 1
print(f"\nDrawdown summary (24.7y):")
print(f"  PROD MaxDD: {prod_dd.min()*100:.1f}% on {prod_dd.idxmin().date()}")
print(f"  SPY  MaxDD: {spy_dd.min()*100:.1f}% on {spy_dd.idxmin().date()}")
print(f"  PROD time underwater: {(prod_dd < -0.05).sum()} days w/ DD < -5%, {(prod_dd < -0.10).sum()} days w/ DD < -10%")

# Final summary
results["PRODUCTION (10bps + 10% VT)"].rename("daily_return").to_frame().to_csv("/tmp/production_daily.csv")
yr.to_csv("/tmp/production_yearly.csv")
