"""
Drawdown circuit-breaker: force-defensive if portfolio drawdown breaches threshold,
regardless of canary state. Re-enter when drawdown recovers above re-entry threshold.

Variants:
  - Hard: trip at -10%, re-enter at -5%
  - Medium: trip at -12%, re-enter at -7%
  - Loose: trip at -15%, re-enter at -10%
  - Trail-only: trip at -8%, re-enter when canary turns risk-on
  - Trail+EMA: trip at -10%, re-enter when 20d EMA of equity > 30d EMA
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
    if not on: return {safe: 1.0}, None, False  # canary off
    score = faber_sma_xs(m)
    avail = [t for t in base_universe if t in score.index and pd.notna(score[t]) and pd.notna(close_panel.loc[sig_d].get(t, np.nan) if sig_d in close_panel.index else np.nan)]
    if not avail: return {safe: 1.0}, None, True  # canary on but no avail
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


def run_with_circuit_breaker(start, end, base_universe,
                             cb_trip=None, cb_reenter=None, cb_mode="threshold",
                             apply_vt=True, cost_bps=COST_BPS):
    """
    cb_trip: drawdown level that trips the breaker (e.g., -0.10 = trip at -10% DD). None=disabled.
    cb_reenter: drawdown recovery level for re-entry (e.g., -0.05 = re-enter when DD recovers to -5%).
    cb_mode: 
      'threshold'   - trip on cb_trip, re-enter on cb_reenter
      'canary_only' - trip on cb_trip, re-enter only when canary turns on
      'ema'         - trip on cb_trip, re-enter when 20d EMA > 30d EMA
    
    The breaker is applied DAILY based on running portfolio equity.
    When tripped, weights = 100% best-safe (overrides whatever monthly signal said).
    """
    cols = list(dict.fromkeys(base_universe + SAFE_POOL + CANARY_ASSETS + [CASH]))
    cols = [c for c in cols if c in panel.columns]
    close = panel[cols]
    monthly_idx = pd.DataFrame({"x":1}, index=close.index).groupby(pd.Grouper(freq="ME")).tail(1)
    signal_dates = monthly_idx.index[(monthly_idx.index >= start) & (monthly_idx.index <= end)].tolist()
    
    # Pre-compute monthly weights (canary-aware, no breaker yet)
    monthly_weights = {}  # apply_from -> weights
    weights_history = []
    prev_pair = None
    canary_state_per_signal = {}  # sig_d -> canary on/off
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
    
    all_assets = sorted({a for _, _, w, _ in weights_history for a in w} | set(SAFE_POOL))
    all_assets = [a for a in all_assets if a in close.columns]
    daily_ret = close.ffill().pct_change()
    
    # Walk daily, applying breaker on running equity
    period_idx = close.index[(close.index >= weights_history[0][0]) & (close.index <= end)]
    portfolio_ret = pd.Series(0.0, index=period_idx)
    breaker_tripped = False
    n_trip_days = 0
    n_total_days = 0
    
    # Build a sig_lookup by date
    # Pre-build per-day signal map (avoids inner loop over intervals)
    sig_d_per_day = pd.Series(index=close.index, dtype=object)
    weights_per_day_idx = {}  # date -> weights dict
    monthly_resampled = close.resample("ME").last()
    safe_per_sig = {}  # sig_d -> safe ticker (precomputed)
    for apply_from, end_apply, w, sig_d in weights_history:
        if sig_d not in safe_per_sig:
            safe_per_sig[sig_d] = best_safe(monthly_resampled, sig_d, SAFE_POOL) or CASH
        mask = (close.index >= apply_from) & (close.index < end_apply)
        for d in close.index[mask]:
            sig_d_per_day.loc[d] = sig_d
            weights_per_day_idx[d] = w
    
    # Track equity for breaker decisions
    equity = 1.0
    peak = 1.0
    
    # Pre-extract daily returns as numpy for speed
    rets_np = daily_ret.fillna(0.0)
    
    for d in period_idx:
        if d not in weights_per_day_idx:
            continue
        current_w = weights_per_day_idx[d]
        current_sig_d = sig_d_per_day.loc[d]
        
        n_total_days += 1
        canary_says_on = canary_state_per_signal.get(current_sig_d, True)
        safe_today = safe_per_sig.get(current_sig_d, CASH)
        
        if cb_trip is not None:
            dd = equity / peak - 1
            if not breaker_tripped:
                if dd <= cb_trip:
                    breaker_tripped = True
            else:
                if cb_mode == "threshold":
                    if dd >= cb_reenter:
                        breaker_tripped = False
                elif cb_mode == "canary_only":
                    if canary_says_on:
                        breaker_tripped = False
        
        if breaker_tripped:
            n_trip_days += 1
            use_w = {safe_today: 1.0}
        else:
            use_w = current_w
        
        # Vectorized return
        if d in rets_np.index:
            r = 0.0
            for c, ww in use_w.items():
                if c in rets_np.columns:
                    r += ww * rets_np.loc[d, c]
            portfolio_ret.loc[d] = r
            equity = equity * (1 + r)
            if equity > peak:
                peak = equity
    
    # Apply rebal cost (rough approx using monthly weights as before)
    for i in range(len(weights_history)):
        prev_w = weights_history[i-1][2] if i > 0 else {}
        curr_w = weights_history[i][2]
        keys = set(curr_w) | set(prev_w)
        turnover = sum(abs(curr_w.get(k, 0.0) - prev_w.get(k, 0.0)) for k in keys)
        cost = turnover * cost_bps / 10000.0
        apply_from = weights_history[i][0]
        if apply_from in portfolio_ret.index:
            portfolio_ret.loc[apply_from] -= cost
    
    daily = portfolio_ret
    if apply_vt:
        realized = daily.rolling(VOL_LOOKBACK).std() * np.sqrt(252)
        scale = (TARGET_VOL / realized).clip(upper=MAX_LEV).shift(1).fillna(1.0)
        daily = daily * scale
    
    daily = daily.loc[(daily.index >= start) & (daily.index <= end)]
    return daily, n_trip_days, n_total_days


end = panel.index[-1]
start = pd.Timestamp("2001-08-30")

print("="*80)
print("DRAWDOWN CIRCUIT-BREAKER tests on PROD (AG")
print(f"Window: {start.date()} -> {end.date()}")
print("="*80)

variants = [
    ("Baseline (no breaker)", None, None, "threshold"),
    ("Trip -10%, re-enter -5%",   -0.10, -0.05, "threshold"),
    ("Trip -12%, re-enter -7%",   -0.12, -0.07, "threshold"),
    ("Trip -15%, re-enter -10%",  -0.15, -0.10, "threshold"),
    ("Trip -8%,  re-enter -3%",   -0.08, -0.03, "threshold"),
    ("Trip -5%,  re-enter -2%",   -0.05, -0.02, "threshold"),
    ("Trip -10%, canary-only re-entry", -0.10, None, "canary_only"),
    ("Trip -8%,  canary-only re-entry", -0.08, None, "canary_only"),
    ("Trip -12%, canary-only re-entry", -0.12, None, "canary_only"),
]

rows = []
for name, trip, reenter, mode in variants:
    daily, n_trip, n_total = run_with_circuit_breaker(start, end, PROD_UNIVERSE, trip, reenter, mode)
    if daily.empty: continue
    eq = (1.0+daily).cumprod()*100_000.0
    m = perf(daily, eq); m["variant"] = name
    m["trip_days_pct"] = round(100*n_trip/n_total, 1) if n_total else 0
    rows.append(m)
df = pd.DataFrame(rows)[["variant","trip_days_pct","cagr","vol","sharpe","max_drawdown"]]
df = df.sort_values("sharpe", ascending=False).reset_index(drop=True)
print(df.to_string(index=False, float_format=lambda x: f"{x:.4f}"))
print()
print("(trip_days_pct: % of trading days the circuit breaker was actively suppressing risk)")

# Top 3 + PP ensemble
print()
print("="*80)
print("Top 3 + PP 30% ensemble")
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
    for vname, trip, reenter, mode in variants:
        if vname == name:
            daily, _, _ = run_with_circuit_breaker(start, end, PROD_UNIVERSE, trip, reenter, mode)
            common = daily.index.intersection(pp.index)
            blended = 0.7 * daily.reindex(common).fillna(0.0) + 0.3 * pp.reindex(common).fillna(0.0)
            m = perf(blended); m["variant"] = f"70%[{name}]+30%PP"
            ens_rows.append(m)
            break
print(pd.DataFrame(ens_rows)[["variant","cagr","vol","sharpe","max_drawdown"]].to_string(index=False, float_format=lambda x: f"{x:.4f}"))
df.to_csv("/tmp/dd_circuit_breaker.csv", index=False)
