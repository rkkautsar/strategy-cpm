"""
Two execution refinements:
  A) T-1 signal / T MOC: compute signal using prior day's close, execute same day MOC.
     Compare vs:
       - 0d (signal at close = full insight)
       - 1d (signal close, execute next day)
       - T-1/T MOC (signal computed on prior close, execute today MOC = our common retail flow)

  B) Tranching: split monthly rebal into N tranches on business days W of month.
     Each tranche holds 1/N of portfolio with its own pair selection.
     Tests:
       - 1 tranche (default) on business day 22 (~ month-end)
       - 3 tranches on biz days 18, 20, 22 (the user's request)
       - 4 tranches on biz days 14, 17, 20, 22 (more spread)

All on cherry config: buffer=3.0, corr_lookback=378.
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

CASH = "SHV"
SAFE_DEFAULT = ["SHV", "IEF"]
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


def compute_pair_at(monthly_panel, close_panel, signal_date, exec_date, prev_pair, universe, buffer=BUFFER, corr_lookback=CORR_LOOKBACK):
    """Compute pair selection using monthly data UP TO signal_date,
       and lowest-corr lookback ending at signal_date.
       Returns weights dict + new prev_pair."""
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


def daily_returns_from_weights(close, daily_weights):
    """daily_weights: DataFrame indexed by date, columns = assets, values = weight.
       Returns daily portfolio return series.
    """
    daily_ret = close.ffill().pct_change()
    common = daily_weights.index.intersection(daily_ret.index)
    weighted = (daily_weights.loc[common] * daily_ret.loc[common, daily_weights.columns]).sum(axis=1, min_count=1)
    return weighted.fillna(0.0)


# ============================================================
# Setup
# ============================================================
end = panel.index[-1]
start = pd.Timestamp("2001-08-30")
cols = list(dict.fromkeys(UNIVERSE + SAFE_DEFAULT + CANARY_ASSETS + [CASH]))
cols = [c for c in cols if c in panel.columns]
close = panel[cols]
monthly = close.resample("ME").last()


# ============================================================
# A) Signal/exec timing
# ============================================================
print("="*80)
print("A) Signal / Execution timing (cherry config, monthly rebal)")
print("="*80)

def run_with_timing(timing):
    """timing: 'T0_signal_close', 'T0_T1_open', 'T1_signal_T_MOC' """
    # Get month-end signal dates
    monthly_idx = pd.DataFrame({"x":1}, index=close.index).groupby(pd.Grouper(freq="ME")).tail(1)
    signal_dates = monthly_idx.index[(monthly_idx.index >= start) & (monthly_idx.index <= end)].tolist()
    
    # Build per-day weights series
    weights_per_day = []
    prev_pair = None
    for i, sig_d in enumerate(signal_dates):
        if timing == "T0_signal_close":
            # signal on close of sig_d, executed instantly (lookahead-free if we apply weight from sig_d+1 next day)
            exec_d = sig_d
            apply_from = close.index[close.index > sig_d][0] if (close.index > sig_d).any() else sig_d
        elif timing == "T0_T1_open":
            # signal on close of sig_d, executed at next day's open. Weight applies from sig_d+2 (skip sig_d+1 which is the execution day's intra-day return)
            exec_d_arr = close.index[close.index > sig_d]
            if len(exec_d_arr) < 2: continue
            exec_d = exec_d_arr[0]  # next day = exec
            apply_from = exec_d_arr[1]  # weight applies from day after exec
        elif timing == "T1_signal_T_MOC":
            # signal computed using close of T-1 (previous trading day), executed at MOC of sig_d
            sig_for_calc = close.index[close.index < sig_d][-1] if (close.index < sig_d).any() else sig_d
            exec_d = sig_d
            apply_from = close.index[close.index > sig_d][0] if (close.index > sig_d).any() else sig_d
            sig_d_calc = sig_for_calc  # use this for signal calc
        
        if timing == "T1_signal_T_MOC":
            w, new_pair = compute_pair_at(monthly, close, sig_d_calc, exec_d, prev_pair, UNIVERSE)
        else:
            w, new_pair = compute_pair_at(monthly, close, sig_d, exec_d, prev_pair, UNIVERSE)
        prev_pair = new_pair
        # apply weights from apply_from until next signal's exec/apply window
        next_sig_d = signal_dates[i+1] if i+1 < len(signal_dates) else end
        # weight active range: [apply_from, next_apply_from - 1d]
        # we'll just store anchor and resolve later
        weights_per_day.append((apply_from, w))
    
    # build per-day weights df
    all_assets = sorted({a for _, w in weights_per_day for a in w})
    df = pd.DataFrame(0.0, index=close.index, columns=all_assets)
    for i, (apply_from, w) in enumerate(weights_per_day):
        end_apply = weights_per_day[i+1][0] if i+1 < len(weights_per_day) else end
        mask = (close.index >= apply_from) & (close.index < end_apply) if end_apply != end else (close.index >= apply_from) & (close.index <= end_apply)
        for a, ww in w.items():
            if a in df.columns:
                df.loc[mask, a] = ww
    
    daily_ret = close.ffill().pct_change()
    common_assets = [a for a in df.columns if a in daily_ret.columns]
    portfolio = (df[common_assets] * daily_ret[common_assets]).sum(axis=1, min_count=1).fillna(0.0)
    portfolio = portfolio.loc[(portfolio.index >= start) & (portfolio.index <= end)]
    return portfolio

timing_rows = []
for timing in ["T0_signal_close", "T0_T1_open", "T1_signal_T_MOC"]:
    daily = run_with_timing(timing)
    eq = (1.0+daily).cumprod()*100_000.0
    m = perf(daily, eq); m["timing"] = timing
    timing_rows.append(m)
print(pd.DataFrame(timing_rows)[["timing","cagr","vol","sharpe","max_drawdown"]].to_string(index=False, float_format=lambda x: f"{x:.4f}"))


# ============================================================
# B) Tranching
# ============================================================
print("\n" + "="*80)
print("B) Tranching: split monthly rebal across N business days within month")
print("="*80)

def tranching_dates_for_month(month_end_date, target_biz_days, all_trading_days):
    """For a given month, find the trading day closest to each target business-day-of-month."""
    # Get trading days in this month
    month_start = pd.Timestamp(year=month_end_date.year, month=month_end_date.month, day=1)
    next_month = month_start + pd.DateOffset(months=1)
    trading_days_this_month = all_trading_days[(all_trading_days >= month_start) & (all_trading_days < next_month)]
    if len(trading_days_this_month) == 0:
        return []
    # Map target business day to actual trading day
    actual = []
    for target_bd in target_biz_days:
        if target_bd <= len(trading_days_this_month):
            actual.append(trading_days_this_month[target_bd - 1])
        else:
            actual.append(trading_days_this_month[-1])
    return actual

def run_tranches(target_biz_days):
    """Each tranche holds 1/N of portfolio with independent pair selection on its trade day."""
    n = len(target_biz_days)
    # For each tranche, identify monthly trade dates
    trade_calendars = [[] for _ in range(n)]
    monthly_idx = pd.DataFrame({"x":1}, index=close.index).groupby(pd.Grouper(freq="ME")).tail(1)
    month_ends = monthly_idx.index[(monthly_idx.index >= start) & (monthly_idx.index <= end)].tolist()
    for me in month_ends:
        # Need monthly data ending at month before for signal (since trade happens mid-month)
        # Actually signal computed at the trade date's monthly bar
        biz_days = tranching_dates_for_month(me, target_biz_days, close.index)
        for i, d in enumerate(biz_days):
            if d >= start and d <= end:
                trade_calendars[i].append(d)
    
    # For each tranche, build its weight time series independently
    all_assets = set()
    tranche_weights = []  # list of (anchor_date, weight_dict)
    
    for ti, cal in enumerate(trade_calendars):
        prev_pair = None
        tranche_history = []  # (apply_from, end_apply, weights)
        for i, trade_d in enumerate(cal):
            # Use signal_d = previous trading day (T-1 signal, T MOC execution model)
            sig_d_arr = close.index[close.index < trade_d]
            if len(sig_d_arr) == 0: continue
            sig_d = sig_d_arr[-1]
            # Resample monthly using sig_d as cutoff
            monthly_for_signal = close.loc[:sig_d].resample("ME").last()
            w, new_pair = compute_pair_at(monthly_for_signal, close, sig_d, trade_d, prev_pair, UNIVERSE)
            prev_pair = new_pair
            apply_from_arr = close.index[close.index > trade_d]
            if len(apply_from_arr) == 0: continue
            apply_from = apply_from_arr[0]
            next_trade_d = cal[i+1] if i+1 < len(cal) else end
            tranche_history.append((apply_from, next_trade_d, w))
            for a in w: all_assets.add(a)
        tranche_weights.append(tranche_history)
    
    # Build per-day per-tranche DataFrames, sum, divide by n
    all_assets = sorted(all_assets)
    portfolio_daily = pd.Series(0.0, index=close.index)
    for tranche_history in tranche_weights:
        df = pd.DataFrame(0.0, index=close.index, columns=all_assets)
        for apply_from, end_apply, w in tranche_history:
            mask = (close.index >= apply_from) & (close.index < end_apply)
            for a, ww in w.items():
                if a in df.columns:
                    df.loc[mask, a] = ww
        daily_ret = close.ffill().pct_change()
        common = [a for a in df.columns if a in daily_ret.columns]
        tranche_port = (df[common] * daily_ret[common]).sum(axis=1, min_count=1).fillna(0.0)
        portfolio_daily += tranche_port / n
    portfolio_daily = portfolio_daily.loc[(portfolio_daily.index >= start) & (portfolio_daily.index <= end)]
    return portfolio_daily

tranche_rows = []
for name, biz_days in [
    ("1tranche_BD22",         [22]),
    ("3tranches_BD18_20_22",  [18, 20, 22]),
    ("4tranches_BD14_17_20_22", [14, 17, 20, 22]),
    ("5tranches_BD13_16_19_22_25", [13, 16, 19, 22, 25]),
]:
    print(f"  Running {name}...")
    daily = run_tranches(biz_days)
    eq = (1.0+daily).cumprod()*100_000.0
    m = perf(daily, eq); m["tranching"] = name
    tranche_rows.append(m)
print()
print(pd.DataFrame(tranche_rows)[["tranching","cagr","vol","sharpe","max_drawdown"]].to_string(index=False, float_format=lambda x: f"{x:.4f}"))

pd.DataFrame(timing_rows).to_csv("/tmp/exec_A_timing.csv", index=False)
pd.DataFrame(tranche_rows).to_csv("/tmp/exec_B_tranching.csv", index=False)
