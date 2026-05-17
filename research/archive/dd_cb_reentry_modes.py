"""
Drawdown circuit-breaker re-entry timing variants:

A) canary_immediate: re-enter the moment canary turns on (current implementation; effectively waits for next month boundary because canary only updates monthly)
B) next_month: re-enter only at next monthly rebalance regardless of intra-month state
C) recovery_X: re-enter when DD recovers to -X% (mid-month allowed)
D) recovery_AND_canary: re-enter when DD recovers AND canary on
E) min_holding_period: trip + force minimum 1-month hold before any re-entry
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
tip_clean = pd.read_csv("/tmp/tip_stitched_daily.csv", parse_dates=[0], index_col=0); tip_clean.columns=["TIP_clean"]
panel = panel.join(gld, how="outer").join(tip_clean, how="outer").sort_index()
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
TRIP_THRESHOLD = -0.08


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


def compute_signal(monthly_panel, close_panel, sig_d, prev_pair, base_universe):
    m = monthly_panel.loc[:sig_d]
    on = True
    for c in CANARY_ASSETS:
        if c in m.columns:
            s = sig_13612W(m[c])
            if pd.isna(s) or s <= 0: on = False; break
    safe = best_safe(monthly_panel, sig_d, SAFE_POOL) or CASH
    if not on: return {safe: 1.0}, None, False
    score = faber_sma_xs(m)
    avail = [t for t in base_universe if t in score.index and pd.notna(score[t]) and pd.notna(close_panel.loc[sig_d].get(t, np.nan) if sig_d in close_panel.index else np.nan)]
    if not avail: return {safe: 1.0}, None, True
    sa = score.loc[avail]; za = zscore(sa)
    ranked = sa.sort_values(ascending=False)
    positive = ranked.iloc[:max(2,(len(ranked)+1)//2)][lambda s: s>0]
    if len(positive) < 2:
        if len(positive) == 1:
            return {positive.index[0]: 0.5, safe: 0.5}, None, True
        return {safe: 1.0}, None, True
    candidates = list(positive.index)
    new_pick = lowest_corr_pair(close_panel.loc[:sig_d, candidates], candidates, CORR_LOOKBACK)
    if new_pick is None: return {candidates[0]: 1.0}, None, True
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
    return {new_pick[0]: 0.5, new_pick[1]: 0.5}, new_pick, True


def run_with_breaker(start, end, base_universe, reentry_mode, recovery_thresh=None,
                     min_hold_days=0, apply_vt=True, cost_bps=COST_BPS):
    cols = list(dict.fromkeys(base_universe + SAFE_POOL + CANARY_ASSETS + [CASH]))
    cols = [c for c in cols if c in panel.columns]
    close = panel[cols]
    monthly_idx = pd.DataFrame({"x":1}, index=close.index).groupby(pd.Grouper(freq="ME")).tail(1)
    signal_dates = monthly_idx.index[(monthly_idx.index >= start) & (monthly_idx.index <= end)].tolist()
    
    weights_history = []
    prev_pair = None
    canary_state_per_signal = {}
    for i, sig_d in enumerate(signal_dates):
        monthly_for_signal = close.loc[:sig_d].resample("ME").last()
        w, new_pair, canary_on = compute_signal(monthly_for_signal, close, sig_d, prev_pair, base_universe)
        canary_state_per_signal[sig_d] = canary_on
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
        weights_history.append((apply_from, end_apply, w, sig_d))
    
    daily_ret = close.ffill().pct_change()
    period_idx = close.index[(close.index >= weights_history[0][0]) & (close.index <= end)]
    portfolio_ret = pd.Series(0.0, index=period_idx)
    
    # Pre-build per-day signal map
    sig_d_per_day = pd.Series(index=close.index, dtype=object)
    weights_per_day_idx = {}
    monthly_resampled = close.resample("ME").last()
    safe_per_sig = {}
    next_month_boundary = {}  # sig_d -> next month boundary
    for j, (apply_from, end_apply, w, sig_d) in enumerate(weights_history):
        if sig_d not in safe_per_sig:
            safe_per_sig[sig_d] = best_safe(monthly_resampled, sig_d, SAFE_POOL) or CASH
        for d in close.index[(close.index >= apply_from) & (close.index < end_apply)]:
            sig_d_per_day.loc[d] = sig_d
            weights_per_day_idx[d] = w
        # next month boundary = end_apply (start of next monthly weight period)
        next_month_boundary[sig_d] = end_apply
    
    breaker_tripped = False
    trip_date = None
    n_trip_days = 0; n_total_days = 0
    equity = 1.0; peak = 1.0
    rets_np = daily_ret.fillna(0.0)
    
    for d in period_idx:
        if d not in weights_per_day_idx:
            continue
        current_w = weights_per_day_idx[d]
        current_sig_d = sig_d_per_day.loc[d]
        
        n_total_days += 1
        canary_says_on = canary_state_per_signal.get(current_sig_d, True)
        safe_today = safe_per_sig.get(current_sig_d, CASH)
        dd = equity / peak - 1
        
        # Trip condition
        if not breaker_tripped and dd <= TRIP_THRESHOLD:
            breaker_tripped = True
            trip_date = d
        # Re-entry condition
        elif breaker_tripped:
            release = False
            if reentry_mode == "canary_immediate":
                if canary_says_on: release = True
            elif reentry_mode == "next_month":
                # only check at first day of new monthly weight regime
                if current_sig_d != sig_d_per_day.loc[trip_date]:
                    if canary_says_on: release = True  # also require canary on
            elif reentry_mode == "recovery":
                if dd >= recovery_thresh: release = True
            elif reentry_mode == "recovery_AND_canary":
                if dd >= recovery_thresh and canary_says_on: release = True
            elif reentry_mode == "min_hold":
                # require min_hold_days elapsed AND canary on
                days_held = (d - trip_date).days
                if days_held >= min_hold_days and canary_says_on:
                    release = True
            if release:
                breaker_tripped = False
                trip_date = None
        
        if breaker_tripped:
            n_trip_days += 1
            use_w = {safe_today: 1.0}
        else:
            use_w = current_w
        
        if d in rets_np.index:
            r = 0.0
            for c, ww in use_w.items():
                if c in rets_np.columns:
                    r += ww * rets_np.loc[d, c]
            portfolio_ret.loc[d] = r
            equity = equity * (1 + r)
            if equity > peak: peak = equity
    
    for j in range(len(weights_history)):
        prev_w = weights_history[j-1][2] if j > 0 else {}
        curr_w = weights_history[j][2]
        keys = set(curr_w) | set(prev_w)
        turnover = sum(abs(curr_w.get(k, 0.0) - prev_w.get(k, 0.0)) for k in keys)
        cost = turnover * cost_bps / 10000.0
        apply_from = weights_history[j][0]
        if apply_from in portfolio_ret.index:
            portfolio_ret.loc[apply_from] -= cost
    
    daily = portfolio_ret
    if apply_vt:
        realized = daily.rolling(VOL_LOOKBACK).std() * np.sqrt(252)
        scale = (TARGET_VOL / realized).clip(upper=MAX_LEV).shift(1).fillna(1.0)
        daily = daily * scale
    return daily.loc[(daily.index >= start) & (daily.index <= end)], n_trip_days, n_total_days


end = panel.index[-1]
start = pd.Timestamp("2001-08-30")

print("="*80)
print(f"DD CIRCUIT BREAKER re-entry mode comparison (trip = {TRIP_THRESHOLD*100:.0f}%)")
print(f"Window: {start.date()} -> {end.date()}")
print("="*80)

variants = [
    ("(no breaker)",                   None,                None, 0),
    ("canary_immediate (current)",     "canary_immediate",  None, 0),
    ("next_month (canary on then)",    "next_month",        None, 0),
    ("recovery -3% any time",          "recovery",          -0.03, 0),
    ("recovery -2% any time",          "recovery",          -0.02, 0),
    ("recovery -3% AND canary on",     "recovery_AND_canary", -0.03, 0),
    ("recovery -5% AND canary on",     "recovery_AND_canary", -0.05, 0),
    ("min_hold 21d + canary",          "min_hold",          None, 21),
    ("min_hold 42d + canary",          "min_hold",          None, 42),
    ("min_hold 63d + canary",          "min_hold",          None, 63),
]

rows = []
for name, mode, rec, hold in variants:
    if mode is None:
        # baseline: no breaker
        cols = list(dict.fromkeys(PROD_UNIVERSE + SAFE_POOL + CANARY_ASSETS + [CASH]))
        cols = [c for c in cols if c in panel.columns]
        close = panel[cols]
        monthly_idx = pd.DataFrame({"x":1}, index=close.index).groupby(pd.Grouper(freq="ME")).tail(1)
        signal_dates = monthly_idx.index[(monthly_idx.index >= start) & (monthly_idx.index <= end)].tolist()
        weights_history = []; prev_pair = None
        for i, sig_d in enumerate(signal_dates):
            monthly_for_signal = close.loc[:sig_d].resample("ME").last()
            w, new_pair, _ = compute_signal(monthly_for_signal, close, sig_d, prev_pair, PROD_UNIVERSE)
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
        df_w = pd.DataFrame(0.0, index=close.index, columns=[a for a in all_assets if a in close.columns])
        for apply_from, end_apply, w in weights_history:
            mask = (close.index >= apply_from) & (close.index < end_apply)
            for a, ww in w.items():
                if a in df_w.columns: df_w.loc[mask, a] = ww
        daily_ret = close.ffill().pct_change()
        common = [a for a in df_w.columns if a in daily_ret.columns]
        pre = (df_w[common] * daily_ret[common]).sum(axis=1, min_count=1).fillna(0.0)
        for j in range(len(weights_history)):
            prev_w = weights_history[j-1][2] if j > 0 else {}
            curr_w = weights_history[j][2]
            keys = set(curr_w) | set(prev_w)
            turnover = sum(abs(curr_w.get(k, 0.0) - prev_w.get(k, 0.0)) for k in keys)
            cost = turnover * COST_BPS / 10000.0
            apply_from = weights_history[j][0]
            if apply_from in pre.index:
                pre.loc[apply_from] -= cost
        realized = pre.rolling(VOL_LOOKBACK).std() * np.sqrt(252)
        scale = (TARGET_VOL / realized).clip(upper=MAX_LEV).shift(1).fillna(1.0)
        daily = (pre * scale).loc[(pre.index >= start) & (pre.index <= end)]
        n_trip = 0; n_total = (daily.index <= end).sum()
    else:
        daily, n_trip, n_total = run_with_breaker(start, end, PROD_UNIVERSE, mode, recovery_thresh=rec, min_hold_days=hold)
    if daily.empty: continue
    eq = (1.0+daily).cumprod()*100_000.0
    m = perf(daily, eq); m["variant"] = name
    m["trip_days_pct"] = round(100*n_trip/n_total, 1) if n_total else 0
    rows.append(m)
df = pd.DataFrame(rows)[["variant","trip_days_pct","cagr","vol","sharpe","max_drawdown"]]
df = df.sort_values("sharpe", ascending=False).reset_index(drop=True)
print(df.to_string(index=False, float_format=lambda x: f"{x:.4f}"))
df.to_csv("/tmp/dd_cb_reentry.csv", index=False)
