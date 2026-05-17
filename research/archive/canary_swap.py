"""
Replace current SPY+TIP 13612W canary with two alternatives:
  A) CAM 4-rule: SPY/TIP/EFA/EEM avg136 -> 4 regimes (Rule 1 risk-on, Rule 4 mid 60/40-style)
  B) SPY-CAP 3-regime: SPY/TIP/EFA/EEM 13612U -> RISK-ON / DEFENSIVE / CAUTION (60/40)

For each, integrate as "regime selector" feeding the existing engine:
  - RISK-ON: full pair selection from PROD universe
  - DEFENSIVE: 100% best safe
  - CAUTION/MID: 60% pair + 40% best safe (or 60/40 PROD/safe if engine returns full risky)

Compare to current PROD canary (SPY+TIP both 13612W>0 -> binary on/off).

Universe: AGGR+GLD+TLT (current PROD).
All other components fixed: cherry config, partial-safe, vol-target, 10bps cost.
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

def sig_13612U(p):
    """Unweighted average of r1, r3, r6, r12."""
    p = p.dropna()
    if len(p) < 13: return np.nan
    last = p.iloc[-1]
    return ((last/p.iloc[-2]-1) + (last/p.iloc[-4]-1) + (last/p.iloc[-7]-1) + (last/p.iloc[-13]-1))/4.0

def sig_avg136(p):
    """avg(r1, r3, r6) = CAM signal."""
    p = p.dropna()
    if len(p) < 7: return np.nan
    last = p.iloc[-1]
    return ((last/p.iloc[-2]-1) + (last/p.iloc[-4]-1) + (last/p.iloc[-7]-1))/3.0

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


# ==========================================================
# Regime classifiers — each returns "RISK_ON" | "DEFENSIVE" | "CAUTION"
# ==========================================================

def regime_PROD(monthly_panel, sig_d):
    """Current PROD: SPY+TIP both 13612W > 0 -> RISK_ON, else DEFENSIVE."""
    m = monthly_panel.loc[:sig_d]
    for c in ["SPY", "TIP"]:
        if c not in m.columns: return "RISK_ON"
        s = sig_13612W(m[c])
        if pd.isna(s): return "RISK_ON"
        if s <= 0: return "DEFENSIVE"
    return "RISK_ON"

def regime_CAM(monthly_panel, sig_d):
    """CAM 4-rule with avg136 signal:
       Rule 1: TIP up AND SPY up AND g_down==0  -> RISK_ON (100% AGGR)
       Rule 2: TIP down AND g_down==2          -> CAUTION_HEAVY (50% MR-KMLM, 50% safe; we treat as DEFENSIVE since no MR-KMLM here)
       Rule 3: SPY down OR (TIP down AND g_down==1) -> DEFENSIVE (100% safe)
       Rule 4: otherwise                        -> CAUTION (mid 60/20/20-ish; we treat as 60% pair + 40% safe)
    """
    m = monthly_panel.loc[:sig_d]
    sigs = {}
    for c in ["SPY", "TIP", "EFA", "EEM"]:
        if c not in m.columns:
            return "RISK_ON"  # missing canary, default risky
        s = sig_avg136(m[c])
        if pd.isna(s): return "RISK_ON"
        sigs[c] = s
    spy_up = sigs["SPY"] > 0
    tip_up = sigs["TIP"] > 0
    efa_down = sigs["EFA"] < 0
    eem_down = sigs["EEM"] < 0
    g_down = int(efa_down) + int(eem_down)
    
    # Rule 1
    if tip_up and spy_up and g_down == 0:
        return "RISK_ON"
    # Rule 2
    if (not tip_up) and g_down == 2:
        return "DEFENSIVE"  # no MR-KMLM in this test
    # Rule 3
    if (not spy_up) or ((not tip_up) and g_down == 1):
        return "DEFENSIVE"
    # Rule 4 default
    return "CAUTION"

def regime_SPY_CAP(monthly_panel, sig_d):
    """SPY-CAP: 3 regimes via 13612U.
       Rule 1: SPY up AND TIP up                 -> RISK_ON
       Rule 2: SPY down                          -> DEFENSIVE
       Rule 3: TIP down AND EFA down AND EEM down -> DEFENSIVE
       otherwise                                  -> CAUTION (60/40)
    """
    m = monthly_panel.loc[:sig_d]
    sigs = {}
    for c in ["SPY", "TIP", "EFA", "EEM"]:
        if c not in m.columns:
            return "RISK_ON"
        s = sig_13612U(m[c])
        if pd.isna(s): return "RISK_ON"
        sigs[c] = s
    spy_up = sigs["SPY"] > 0
    tip_up = sigs["TIP"] > 0
    efa_down = sigs["EFA"] < 0
    eem_down = sigs["EEM"] < 0
    
    if spy_up and tip_up:
        return "RISK_ON"
    if not spy_up:
        return "DEFENSIVE"
    if (not tip_up) and efa_down and eem_down:
        return "DEFENSIVE"
    return "CAUTION"


def compute_pair(monthly_panel, close_panel, sig_d, prev_pair, base_universe):
    """Pair selection (no canary applied here)."""
    m = monthly_panel.loc[:sig_d]
    score = faber_sma_xs(m)
    avail = [t for t in base_universe if t in score.index and pd.notna(score[t]) and pd.notna(close_panel.loc[sig_d].get(t, np.nan) if sig_d in close_panel.index else np.nan)]
    if not avail: return None, None
    sa = score.loc[avail]; za = zscore(sa)
    ranked = sa.sort_values(ascending=False)
    positive = ranked.iloc[:max(2,(len(ranked)+1)//2)][lambda s: s>0]
    if len(positive) < 2:
        if len(positive) == 1:
            return ([(positive.index[0], 0.5)], None)  # partial; consumer will add safe
        return None, None
    candidates = list(positive.index)
    new_pick = lowest_corr_pair(close_panel.loc[:sig_d, candidates], candidates, CORR_LOOKBACK)
    if new_pick is None:
        return ([(candidates[0], 1.0)], None)
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
    return [(new_pick[0], 0.5), (new_pick[1], 0.5)], new_pick


def compute_signal(monthly_panel, close_panel, sig_d, prev_pair, base_universe, regime_fn, caution_risk_pct=0.6):
    """
    Use regime_fn to decide regime, then build weights.
    
    RISK_ON: 100% pair (or partial-safe if <2 positive)
    DEFENSIVE: 100% best safe
    CAUTION: caution_risk_pct% pair + (1-caution_risk_pct)% safe
    """
    safe = best_safe(monthly_panel, sig_d, SAFE_POOL) or CASH
    regime = regime_fn(monthly_panel, sig_d)
    
    if regime == "DEFENSIVE":
        return {safe: 1.0}, None, regime
    
    pair_result, new_pair = compute_pair(monthly_panel, close_panel, sig_d, prev_pair, base_universe)
    if pair_result is None:
        return {safe: 1.0}, None, regime
    pair_dict = dict(pair_result)
    pair_total = sum(pair_dict.values())  # may be 1.0 (full pair) or 0.5 (partial)
    
    if regime == "RISK_ON":
        # Use pair as-is. Top up with safe if partial.
        if pair_total < 0.99:
            pair_dict[safe] = pair_dict.get(safe, 0.0) + (1.0 - pair_total)
        return pair_dict, new_pair, regime
    
    if regime == "CAUTION":
        # Scale pair to caution_risk_pct of capital, rest to safe
        scaled = {k: v * (caution_risk_pct / pair_total) for k, v in pair_dict.items()} if pair_total > 0 else {}
        scaled[safe] = scaled.get(safe, 0.0) + (1.0 - caution_risk_pct)
        return scaled, new_pair, regime
    
    return {safe: 1.0}, None, regime


def run_strategy(start, end, base_universe, regime_fn, caution_risk_pct=0.6, apply_vt=True, cost_bps=COST_BPS):
    cols = list(dict.fromkeys(base_universe + SAFE_POOL + ["SPY","TIP","EFA","EEM"] + [CASH]))
    cols = [c for c in cols if c in panel.columns]
    close = panel[cols]
    monthly_idx = pd.DataFrame({"x":1}, index=close.index).groupby(pd.Grouper(freq="ME")).tail(1)
    signal_dates = monthly_idx.index[(monthly_idx.index >= start) & (monthly_idx.index <= end)].tolist()
    weights_history = []; prev_pair = None
    regime_counts = {"RISK_ON": 0, "DEFENSIVE": 0, "CAUTION": 0}
    for i, sig_d in enumerate(signal_dates):
        monthly_for_signal = close.loc[:sig_d].resample("ME").last()
        w, new_pair, regime = compute_signal(monthly_for_signal, close, sig_d, prev_pair, base_universe, regime_fn, caution_risk_pct)
        regime_counts[regime] = regime_counts.get(regime, 0) + 1
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
    return daily.loc[(daily.index >= start) & (daily.index <= end)], regime_counts


# ==========================================================
end = panel.index[-1]
start = pd.Timestamp("2001-08-30")

print("="*80)
print("Canary system swap: SPY+TIP-13612W (current) vs CAM 4-rule vs SPY-CAP 3-regime")
print(f"Window: {start.date()} -> {end.date()}, universe: AGGR+GLD+TLT")
print("="*80)

variants = [
    ("PROD_canary (SPY+TIP 13612W)",       regime_PROD,    0.6),
    ("CAM 4-rule (caution=60% pair)",      regime_CAM,     0.6),
    ("CAM 4-rule (caution=80% pair)",      regime_CAM,     0.8),
    ("CAM 4-rule (caution=50% pair)",      regime_CAM,     0.5),
    ("SPY_CAP 3-regime (caution=60% pair)", regime_SPY_CAP, 0.6),
    ("SPY_CAP 3-regime (caution=80% pair)", regime_SPY_CAP, 0.8),
    ("SPY_CAP 3-regime (caution=50% pair)", regime_SPY_CAP, 0.5),
]

rows = []
for name, fn, cau in variants:
    daily, regimes = run_strategy(start, end, PROD_UNIVERSE, fn, caution_risk_pct=cau)
    if daily.empty: continue
    eq = (1.0+daily).cumprod()*100_000.0
    m = perf(daily, eq); m["variant"] = name
    total = sum(regimes.values()) or 1
    m["risk_on"] = round(100*regimes.get("RISK_ON",0)/total, 1)
    m["caution"] = round(100*regimes.get("CAUTION",0)/total, 1)
    m["defensive"] = round(100*regimes.get("DEFENSIVE",0)/total, 1)
    rows.append(m)
df = pd.DataFrame(rows)[["variant","risk_on","caution","defensive","cagr","vol","sharpe","max_drawdown"]]
df = df.sort_values("sharpe", ascending=False).reset_index(drop=True)
print(df.to_string(index=False, float_format=lambda x: f"{x:.4f}"))

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
    for vname, fn, cau in variants:
        if vname == name:
            daily, _ = run_strategy(start, end, PROD_UNIVERSE, fn, caution_risk_pct=cau)
            common = daily.index.intersection(pp.index)
            blended = 0.7 * daily.reindex(common).fillna(0.0) + 0.3 * pp.reindex(common).fillna(0.0)
            m = perf(blended); m["variant"] = f"70%[{name}]+30%PP"
            ens_rows.append(m)
            break
print(pd.DataFrame(ens_rows)[["variant","cagr","vol","sharpe","max_drawdown"]].to_string(index=False, float_format=lambda x: f"{x:.4f}"))
df.to_csv("/tmp/canary_swap.csv", index=False)
