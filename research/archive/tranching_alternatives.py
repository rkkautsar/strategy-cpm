"""
Cheaper alternatives to 5-tranche execution:

1. Single tranche on different days of month (find best fixed day)
2. 2 tranches (one early-mid, one late-month)
3. 5-tranche but with shared signal (split execution only, single signal calc)
4. Random-day rebalance (sanity check)
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
UNIVERSE = AGGR_ALL + ["GLD", "KMLM_stitched"]; CANARY_ASSETS = ["SPY", "TIP"]
BUFFER = 3.0; CORR_LOOKBACK = 378


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

def compute_pair_at(monthly_panel, close_panel, signal_date, exec_date, prev_pair, universe, buffer=BUFFER, corr_lookback=CORR_LOOKBACK):
    m = monthly_panel.loc[:signal_date]
    on = True
    for c in CANARY_ASSETS:
        if c in m.columns:
            s = sig_13612W(m[c])
            if pd.isna(s) or s <= 0: on = False; break
    safe = best_safe(monthly_panel, signal_date, SAFE_DEFAULT) or CASH
    if not on:
        return {safe: 1.0}, None
    score = faber_sma_xs(m)
    avail = [t for t in universe if t in score.index and pd.notna(score[t]) and pd.notna(close_panel.loc[exec_date].get(t, np.nan) if exec_date in close_panel.index else np.nan)]
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
    new_pick = lowest_corr_pair(close_panel.loc[:signal_date, candidates], candidates, corr_lookback)
    if new_pick is None:
        return {candidates[0]: 1.0}, None
    if prev_pair is not None and buffer > 1e-9:
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
            if z_swap - z_prior < buffer:
                new_set.remove(swap); new_set.append(prior)
        new_pick = tuple(new_set[:2])
    return {new_pick[0]: 0.5, new_pick[1]: 0.5}, new_pick


end = panel.index[-1]
start = pd.Timestamp("2001-08-30")
cols = list(dict.fromkeys(UNIVERSE + SAFE_DEFAULT + CANARY_ASSETS + [CASH]))
cols = [c for c in cols if c in panel.columns]
close = panel[cols]


def tranching_dates_for_month(month_end_date, target_biz_days, all_trading_days):
    month_start = pd.Timestamp(year=month_end_date.year, month=month_end_date.month, day=1)
    next_month = month_start + pd.DateOffset(months=1)
    trading_days_this_month = all_trading_days[(all_trading_days >= month_start) & (all_trading_days < next_month)]
    if len(trading_days_this_month) == 0: return []
    actual = []
    for target_bd in target_biz_days:
        if target_bd <= len(trading_days_this_month):
            actual.append(trading_days_this_month[target_bd - 1])
        else:
            actual.append(trading_days_this_month[-1])
    return actual


def run_tranches_independent_signals(target_biz_days):
    """Each tranche has its OWN signal calc + selection (full independence)."""
    n = len(target_biz_days)
    trade_calendars = [[] for _ in range(n)]
    monthly_idx = pd.DataFrame({"x":1}, index=close.index).groupby(pd.Grouper(freq="ME")).tail(1)
    month_ends = monthly_idx.index[(monthly_idx.index >= start) & (monthly_idx.index <= end)].tolist()
    for me in month_ends:
        biz_days = tranching_dates_for_month(me, target_biz_days, close.index)
        for i, d in enumerate(biz_days):
            if d >= start and d <= end:
                trade_calendars[i].append(d)
    
    all_assets = set()
    tranche_weights = []
    for cal in trade_calendars:
        prev_pair = None
        history = []
        for i, trade_d in enumerate(cal):
            sig_d_arr = close.index[close.index < trade_d]
            if len(sig_d_arr) == 0: continue
            sig_d = sig_d_arr[-1]
            monthly_for_signal = close.loc[:sig_d].resample("ME").last()
            w, new_pair = compute_pair_at(monthly_for_signal, close, sig_d, trade_d, prev_pair, UNIVERSE)
            prev_pair = new_pair
            apply_from_arr = close.index[close.index > trade_d]
            if len(apply_from_arr) == 0: continue
            apply_from = apply_from_arr[0]
            next_trade_d = cal[i+1] if i+1 < len(cal) else end
            history.append((apply_from, next_trade_d, w))
            for a in w: all_assets.add(a)
        tranche_weights.append(history)
    
    all_assets = sorted(all_assets)
    portfolio_daily = pd.Series(0.0, index=close.index)
    for h in tranche_weights:
        df = pd.DataFrame(0.0, index=close.index, columns=all_assets)
        for apply_from, end_apply, w in h:
            mask = (close.index >= apply_from) & (close.index < end_apply)
            for a, ww in w.items():
                if a in df.columns: df.loc[mask, a] = ww
        daily_ret = close.ffill().pct_change()
        common = [a for a in df.columns if a in daily_ret.columns]
        portfolio_daily += (df[common] * daily_ret[common]).sum(axis=1, min_count=1).fillna(0.0) / n
    return portfolio_daily.loc[(portfolio_daily.index >= start) & (portfolio_daily.index <= end)]


def run_tranches_shared_signal(target_biz_days, signal_biz_day=22):
    """Single signal at signal_biz_day, weights split across N tranches at target_biz_days.
       Each tranche just executes with the SAME monthly weight — only execution day differs."""
    n = len(target_biz_days)
    monthly_idx = pd.DataFrame({"x":1}, index=close.index).groupby(pd.Grouper(freq="ME")).tail(1)
    month_ends = monthly_idx.index[(monthly_idx.index >= start) & (monthly_idx.index <= end)].tolist()
    
    # Single signal per month at signal_biz_day
    signal_dates = []
    trade_dates_per_month = []  # each list = trade days for this month
    for me in month_ends:
        sig_d = tranching_dates_for_month(me, [signal_biz_day], close.index)
        if not sig_d: continue
        signal_dates.append(sig_d[0])
        trades = tranching_dates_for_month(me, target_biz_days, close.index)
        trade_dates_per_month.append(trades)
    
    prev_pair = None
    weights_history = []  # (signal_d, weight_dict)
    for sig_d in signal_dates:
        sig_calc = close.index[close.index < sig_d][-1] if (close.index < sig_d).any() else sig_d
        monthly_for_signal = close.loc[:sig_calc].resample("ME").last()
        w, new_pair = compute_pair_at(monthly_for_signal, close, sig_calc, sig_d, prev_pair, UNIVERSE)
        prev_pair = new_pair
        weights_history.append(w)
    
    all_assets = sorted({a for w in weights_history for a in w})
    # Build tranched weight series
    portfolio_daily = pd.Series(0.0, index=close.index)
    for ti in range(n):
        df = pd.DataFrame(0.0, index=close.index, columns=all_assets)
        for mi, w in enumerate(weights_history):
            trades = trade_dates_per_month[mi]
            if ti >= len(trades): continue
            trade_d = trades[ti]
            apply_from_arr = close.index[close.index > trade_d]
            if len(apply_from_arr) == 0: continue
            apply_from = apply_from_arr[0]
            # apply until next month's same-tranche-trade
            if mi+1 < len(weights_history) and ti < len(trade_dates_per_month[mi+1]):
                end_apply = trade_dates_per_month[mi+1][ti]
            else:
                end_apply = end
            mask = (close.index >= apply_from) & (close.index < end_apply)
            for a, ww in w.items():
                if a in df.columns: df.loc[mask, a] = ww
        daily_ret = close.ffill().pct_change()
        common = [a for a in df.columns if a in daily_ret.columns]
        portfolio_daily += (df[common] * daily_ret[common]).sum(axis=1, min_count=1).fillna(0.0) / n
    return portfolio_daily.loc[(portfolio_daily.index >= start) & (portfolio_daily.index <= end)]


def run_single_tranche_at_day(biz_day):
    """Single rebal at given business day each month (T-1/T MOC realistic timing)."""
    monthly_idx = pd.DataFrame({"x":1}, index=close.index).groupby(pd.Grouper(freq="ME")).tail(1)
    month_ends = monthly_idx.index[(monthly_idx.index >= start) & (monthly_idx.index <= end)].tolist()
    trade_dates = []
    for me in month_ends:
        td = tranching_dates_for_month(me, [biz_day], close.index)
        if td and td[0] >= start and td[0] <= end:
            trade_dates.append(td[0])
    
    prev_pair = None
    weights_per_apply = []
    for i, trade_d in enumerate(trade_dates):
        sig_d = close.index[close.index < trade_d][-1] if (close.index < trade_d).any() else trade_d
        monthly_for_signal = close.loc[:sig_d].resample("ME").last()
        w, new_pair = compute_pair_at(monthly_for_signal, close, sig_d, trade_d, prev_pair, UNIVERSE)
        prev_pair = new_pair
        apply_from_arr = close.index[close.index > trade_d]
        if len(apply_from_arr) == 0: continue
        apply_from = apply_from_arr[0]
        next_trade = trade_dates[i+1] if i+1 < len(trade_dates) else end
        weights_per_apply.append((apply_from, next_trade, w))
    
    all_assets = sorted({a for _, _, w in weights_per_apply for a in w})
    df = pd.DataFrame(0.0, index=close.index, columns=all_assets)
    for apply_from, end_apply, w in weights_per_apply:
        mask = (close.index >= apply_from) & (close.index < end_apply)
        for a, ww in w.items():
            if a in df.columns: df.loc[mask, a] = ww
    daily_ret = close.ffill().pct_change()
    common = [a for a in df.columns if a in daily_ret.columns]
    portfolio = (df[common] * daily_ret[common]).sum(axis=1, min_count=1).fillna(0.0)
    return portfolio.loc[(portfolio.index >= start) & (portfolio.index <= end)]


# ============================================================
print("="*80)
print("Single tranche on different days of month (find best fixed day)")
print("="*80)
single_rows = []
for bd in [5, 10, 13, 15, 18, 20, 22, 25, -1]:  # -1 = month-end (last)
    label = "month_end" if bd == -1 else f"BD{bd}"
    daily = run_single_tranche_at_day(99 if bd == -1 else bd)  # 99 forces last
    eq = (1.0+daily).cumprod()*100_000.0
    m = perf(daily, eq); m["day"] = label
    single_rows.append(m)
print(pd.DataFrame(single_rows)[["day","cagr","vol","sharpe","max_drawdown"]].to_string(index=False, float_format=lambda x: f"{x:.4f}"))

print()
print("="*80)
print("2-tranche options (each has independent signal, T-1/T MOC realistic)")
print("="*80)
two_rows = []
for name, bds in [
    ("BD15_BD25", [15, 25]),
    ("BD10_BD22", [10, 22]),
    ("BD18_BD22", [18, 22]),
]:
    daily = run_tranches_independent_signals(bds)
    eq = (1.0+daily).cumprod()*100_000.0
    m = perf(daily, eq); m["config"] = name
    two_rows.append(m)
print(pd.DataFrame(two_rows)[["config","cagr","vol","sharpe","max_drawdown"]].to_string(index=False, float_format=lambda x: f"{x:.4f}"))

print()
print("="*80)
print("Shared signal + tranched execution (1 calc, N execution days)")
print("="*80)
shared_rows = []
for name, bds in [
    ("shared_sig_BD22__exec_BD18_20_22",   [18, 20, 22]),
    ("shared_sig_BD22__exec_BD13_22",      [13, 22]),
    ("shared_sig_BD22__exec_BD10_15_20_25",[10, 15, 20, 25]),
]:
    daily = run_tranches_shared_signal(bds, signal_biz_day=22)
    eq = (1.0+daily).cumprod()*100_000.0
    m = perf(daily, eq); m["config"] = name
    shared_rows.append(m)
print(pd.DataFrame(shared_rows)[["config","cagr","vol","sharpe","max_drawdown"]].to_string(index=False, float_format=lambda x: f"{x:.4f}"))

# Reference: 5-tranche from prior
print()
print("="*80)
print("Reference 5-tranche (independent signals)")
print("="*80)
daily_5t = run_tranches_independent_signals([13, 16, 19, 22, 25])
eq = (1.0+daily_5t).cumprod()*100_000.0
m = perf(daily_5t, eq); m["config"] = "5tranche_indep_BD13-25"
print(pd.DataFrame([m])[["config","cagr","vol","sharpe","max_drawdown"]].to_string(index=False, float_format=lambda x: f"{x:.4f}"))
