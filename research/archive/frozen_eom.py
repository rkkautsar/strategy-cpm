"""
Frozen end-of-month signal + delayed execution (BD1, BD2, BD3, BD5, BD7).

Practitioner-standard:
  - Compute signal on month-end close (no intramonth contamination)
  - Execute MOC of BD-N of new month (1-day delay = standard, BD3-5 = buffered)

Compare against:
  - Idealized: signal+exec at month-end close (no lag)
  - Intramonth-refresh (BD5 winner from prior test) for sanity
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

CASH = "SHV"; SAFE_DEFAULT = ["SHV", "IEF"]
AGGR_ALL = ["QQQ","IGM","SPMO","XLE","XRT","SMH","COWZ","AVUV","MOO","RWJ","SPHQ","XMMO","XMHQ"]
UNIVERSE = AGGR_ALL + ["GLD", "KMLM_stitched"]
CANARY_ASSETS = ["SPY", "TIP"]
BUFFER = 3.0
CORR_LOOKBACK = 378


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


def compute_pair_at_signal(monthly_panel, close_panel, signal_date, prev_pair, universe):
    """Use signal_date for ALL signal calc (canary, ranker, corr).
       monthly_panel must be resampled with signal_date as the cutoff."""
    m = monthly_panel  # caller already sliced to signal_date
    on = True
    for c in CANARY_ASSETS:
        if c in m.columns:
            s = sig_13612W(m[c])
            if pd.isna(s) or s <= 0: on = False; break
    safe = best_safe(monthly_panel, signal_date, SAFE_DEFAULT) or CASH
    if not on:
        return {safe: 1.0}, None
    score = faber_sma_xs(m)
    avail = [t for t in universe if t in score.index and pd.notna(score[t]) and pd.notna(close_panel.loc[signal_date].get(t, np.nan) if signal_date in close_panel.index else np.nan)]
    if not avail:
        return {safe: 1.0}, None
    sa = score.loc[avail]; za = zscore(sa)
    ranked = sa.sort_values(ascending=False)
    positive = ranked.iloc[:max(2,(len(ranked)+1)//2)][lambda s: s>0]
    if len(positive) < 2:
        if len(positive) == 1:
            return {positive.index[0]: 0.5, safe: 0.5}, None
        return {safe: 1.0}, None
    candidates = list(positive.index)
    new_pick = lowest_corr_pair(close_panel.loc[:signal_date, candidates], candidates, CORR_LOOKBACK)
    if new_pick is None:
        return {candidates[0]: 1.0}, None
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


def run_frozen_eom(exec_lag_bd):
    """Signal computed on month-end close. Execute MOC of (month-end + exec_lag_bd) trading days later.
       exec_lag_bd=0 -> idealized (same-day MOC at month-end)
       exec_lag_bd=1 -> standard practitioner convention (T+1 MOC)
       exec_lag_bd=3,5,7 -> buffered (let month-end flow settle)"""
    end = panel.index[-1]
    start = pd.Timestamp("2001-08-30")
    cols = list(dict.fromkeys(UNIVERSE + SAFE_DEFAULT + CANARY_ASSETS + [CASH]))
    cols = [c for c in cols if c in panel.columns]
    close = panel[cols]
    
    # Month-end signal dates
    monthly_idx = pd.DataFrame({"x":1}, index=close.index).groupby(pd.Grouper(freq="ME")).tail(1)
    signal_dates = monthly_idx.index[(monthly_idx.index >= start) & (monthly_idx.index <= end)].tolist()
    
    # For each signal date, find exec date = signal_date + exec_lag_bd trading days
    weights_history = []  # (apply_from, end_apply, weights)
    prev_pair = None
    for i, sig_d in enumerate(signal_dates):
        # signal: monthly bars ending at sig_d (exact month-end)
        monthly_for_signal = close.loc[:sig_d].resample("ME").last()
        w, new_pair = compute_pair_at_signal(monthly_for_signal, close, sig_d, prev_pair, UNIVERSE)
        prev_pair = new_pair
        # exec date = sig_d + exec_lag_bd trading days
        future_days = close.index[close.index > sig_d]
        if len(future_days) <= exec_lag_bd:
            continue
        exec_d = future_days[exec_lag_bd] if exec_lag_bd > 0 else sig_d
        # weights apply from day AFTER exec_d (since we filled at MOC of exec_d)
        apply_from_arr = close.index[close.index > exec_d]
        if len(apply_from_arr) == 0: continue
        apply_from = apply_from_arr[0]
        # next exec for next signal
        if i+1 < len(signal_dates):
            next_sig_d = signal_dates[i+1]
            next_future = close.index[close.index > next_sig_d]
            if len(next_future) <= exec_lag_bd:
                end_apply = end
            else:
                next_exec = next_future[exec_lag_bd] if exec_lag_bd > 0 else next_sig_d
                next_apply_arr = close.index[close.index > next_exec]
                end_apply = next_apply_arr[0] if len(next_apply_arr) > 0 else end
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
    portfolio = (df[common] * daily_ret[common]).sum(axis=1, min_count=1).fillna(0.0)
    return portfolio.loc[(portfolio.index >= start) & (portfolio.index <= end)]


print("="*80)
print("Frozen month-end signal + BD-N MOC execution lag (cherry config)")
print("="*80)
rows = []
for lag_name, lag in [
    ("EOM_signal_EOM_MOC_(idealized)", 0),
    ("EOM_signal_T+1_MOC_(standard)",  1),
    ("EOM_signal_T+2_MOC",             2),
    ("EOM_signal_T+3_MOC_(buffered)",  3),
    ("EOM_signal_T+5_MOC_(BD5_clean)", 5),
    ("EOM_signal_T+7_MOC",             7),
    ("EOM_signal_T+10_MOC",            10),
]:
    daily = run_frozen_eom(lag)
    eq = (1.0+daily).cumprod()*100_000.0
    m = perf(daily, eq); m["config"] = lag_name
    rows.append(m)
df = pd.DataFrame(rows)[["config","cagr","vol","sharpe","max_drawdown"]]
print(df.to_string(index=False, float_format=lambda x: f"{x:.4f}"))
df.to_csv("/tmp/frozen_eom.csv", index=False)
