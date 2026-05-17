"""
Risk-off rescue: when canary (SPY+TIP) fails, evaluate short-term momentum + trend
to decide between (a) full safe, (b) keep one strong risky, (c) pair fallback.

Variants:
  none         — canary fails -> 100% best safe (baseline from prior turn)
  aggr_style   — replicate AGGR's apply_riskoff_trend_following:
                   pick best_risky by safe_switch_mom = z(r6 + 4*r2_1)
                   pick best_safe  by mom_short       = z(r2)
                   switch to safe if (best_safe's switch_mom > best_risky's switch_mom)
                                  OR (best_risky's SMA(5) < SMA(100))
                                  OR (best_risky's switch_mom < 0)
                   else hold 100% best_risky
  simple_gtt   — pick best_risky and best_safe by 2m momentum (mom_short)
                   hold best_risky if (best_risky_mom > best_safe_mom) AND (best_risky_mom > 0)
                   else 100% best safe
  half_rescue  — same as simple_gtt but if rescue passes use 50% best_risky + 50% best_safe
"""
import sys
sys.path.insert(0, "/Users/rkautsar/personal/scripts/strategy_cam")

import numpy as np
import pandas as pd
from itertools import combinations

PANEL_PATH = "/Users/rkautsar/personal/scripts/artifacts/cpa-1997-exact-core-proxy-research/proxy_adjusted_close_daily.csv"
panel = pd.read_csv(PANEL_PATH, parse_dates=["Date"], index_col="Date").sort_index()
gld_stitched = pd.read_csv("/tmp/gld_stitched_daily_clean.csv", parse_dates=[0], index_col=0)
gld_stitched.columns = ["GLD"]
panel = panel.join(gld_stitched, how="outer").sort_index()

CASH = "SHV"
SAFE_POOL = ["SHV", "IEF"]
CORR_LOOKBACK_DAYS = 252
HOLD_BUFFER = 1.0
SHORT_MA = 5
LONG_MA = 100
AGGR_ALL = ["QQQ","IGM","SPMO","XLE","XRT","SMH","COWZ","AVUV","MOO","RWJ","SPHQ","XMMO","XMHQ"]
UNIVERSES = {
    "AGGR+GLD":      AGGR_ALL + ["GLD"],
    "AGGR+GLD+KMLM": AGGR_ALL + ["GLD", "KMLM_stitched"],
}
CANARY_ASSETS = ["SPY", "TIP"]
CANARY_MODE = "up"

# Load KMLM stitched
kmlm = pd.read_csv("/tmp/kmlm_stitched_daily.csv", parse_dates=[0], index_col=0)
kmlm.columns = ["KMLM_stitched"]
panel = panel.join(kmlm, how="outer").sort_index()
print(f"Panel after KMLM: {len(panel.columns)} cols")


# ---- helpers ----
def faber_sma(monthly):
    if len(monthly) < 10: return pd.Series(np.nan, index=monthly.columns)
    sma = monthly.rolling(10).mean().iloc[-1]
    return (monthly.iloc[-1] - sma) / sma

def keller_13612W_single(p):
    p = p.dropna()
    if len(p) < 13: return np.nan
    last = p.iloc[-1]
    return (12*(last/p.iloc[-2]-1) + 4*(last/p.iloc[-4]-1) + 2*(last/p.iloc[-7]-1) + (last/p.iloc[-13]-1))/19.0

def mom_short_xs(monthly):
    """z(r2) cross-section."""
    if len(monthly) < 3: return pd.Series(np.nan, index=monthly.columns)
    r2 = monthly.iloc[-1] / monthly.iloc[-3] - 1.0
    sd = r2.std()
    if pd.isna(sd) or sd == 0: return pd.Series(0.0, index=monthly.columns)
    return (r2 - r2.mean()) / sd

def safe_switch_mom_xs(monthly):
    """z(r6 + 4*r(2,1)) cross-section. Lag 1 on the 2m return."""
    if len(monthly) < 7: return pd.Series(np.nan, index=monthly.columns)
    r6 = monthly.iloc[-1] / monthly.iloc[-7] - 1.0
    r2_1 = monthly.iloc[-2] / monthly.iloc[-4] - 1.0
    s = r6 + 4*r2_1
    sd = s.std()
    if pd.isna(sd) or sd == 0: return pd.Series(0.0, index=monthly.columns)
    return (s - s.mean()) / sd

def lowest_corr_pair(daily_close, candidates, lookback_days=CORR_LOOKBACK_DAYS):
    if len(candidates) < 2: return None
    rets = daily_close[candidates].iloc[-lookback_days:].pct_change().dropna(how="all")
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
    return (s - s.mean()) / sd

def month_end_dates(idx, start, end):
    sub = idx[(idx >= start) & (idx <= end)]
    if len(sub) == 0: return []
    return pd.DataFrame({"x":1}, index=sub).groupby(pd.Grouper(freq="ME")).tail(1).index.to_list()

def segment_returns(close, weights_map, dates, end):
    ffill = close.ffill()
    daily = ffill.pct_change()
    period_idx = close.index[(close.index >= dates[0]) & (close.index <= end)]
    out = pd.Series(0.0, index=period_idx, dtype=float)
    for i, d in enumerate(dates):
        nxt = dates[i+1] if i+1 < len(dates) else end
        seg = period_idx[(period_idx > d) & (period_idx <= nxt)]
        if len(seg) == 0: continue
        w = weights_map.get(d, {})
        if not w: continue
        cols = [c for c in w if c in daily.columns]
        if not cols: continue
        sub = daily.loc[seg, cols].mul(pd.Series({k: w[k] for k in cols}), axis=1)
        out.loc[seg] = sub.sum(axis=1, min_count=1).fillna(0.0)
    return out

def perf(daily, eq):
    if daily.empty: return {}
    days = (eq.index[-1]-eq.index[0]).days
    yrs = days/365.25
    cagr = (eq.iloc[-1]/eq.iloc[0])**(1/yrs)-1 if yrs>0 else float("nan")
    vol = daily.std(ddof=0)*np.sqrt(252)
    sharpe = (daily.mean()*252)/vol if vol>0 else float("nan")
    rm = eq.cummax()
    mdd = (eq/rm-1).min()
    return {"total_return": eq.iloc[-1]/eq.iloc[0]-1, "cagr": cagr, "vol": vol, "sharpe": sharpe, "max_drawdown": mdd}

def best_safe(monthly_panel, d):
    m = monthly_panel.loc[:d]
    available = [s for s in SAFE_POOL if s in m.columns and m[s].first_valid_index() is not None]
    if not available:
        return CASH if CASH in m.columns else None
    if len(m) < 10:
        return available[0]
    sma = m[available].rolling(10).mean().iloc[-1]
    last = m[available].iloc[-1]
    dist = ((last - sma) / sma).dropna()
    if dist.empty:
        return available[0]
    return dist.idxmax()

def canary_active(monthly_panel, d):
    m = monthly_panel.loc[:d]
    for c in CANARY_ASSETS:
        if c not in m.columns: return True
        s = keller_13612W_single(m[c])
        if pd.isna(s): return True
        if s <= 0: return False
    return True


# ---- rescue branches ----
def rescue_aggr_style(close, monthly, daily_close, d, universe, safe):
    """AGGR's apply_riskoff_trend_following adapted."""
    m = monthly.loc[:d]
    switch_mom = safe_switch_mom_xs(m)
    short_mom = mom_short_xs(m)
    risky_avail = [t for t in universe if t in switch_mom.index and pd.notna(switch_mom[t]) and pd.notna(close.loc[d].get(t, np.nan))]
    if not risky_avail:
        return {safe: 1.0}
    best_risky = switch_mom.reindex(risky_avail).idxmax()
    safe_avail = [s for s in SAFE_POOL if s in short_mom.index and pd.notna(short_mom[s])]
    best_safe_short = short_mom.reindex(safe_avail).idxmax() if safe_avail else None
    if best_safe_short is None:
        best_safe_short = safe

    # Compare via switch_mom
    risky_switch = switch_mom.get(best_risky, np.nan)
    safe_switch = switch_mom.get(best_safe_short, np.nan) if best_safe_short else np.nan
    if pd.notna(safe_switch) and pd.notna(risky_switch) and risky_switch < safe_switch:
        return {best_safe_short: 1.0}

    # MA cross check (5d vs 100d daily)
    sub_daily = daily_close.loc[:d, [best_risky]].dropna()
    if len(sub_daily) >= LONG_MA:
        sma5 = sub_daily.rolling(SHORT_MA).mean().iloc[-1, 0]
        sma100 = sub_daily.rolling(LONG_MA).mean().iloc[-1, 0]
        if pd.notna(sma5) and pd.notna(sma100) and sma5 < sma100:
            return {best_safe_short: 1.0}

    # Switch_mom < 0 check
    if pd.notna(risky_switch) and risky_switch < 0:
        return {best_safe_short: 1.0}

    # Otherwise rescue: hold best risky
    return {best_risky: 1.0}


def rescue_simple_gtt(close, monthly, d, universe, safe):
    """Hold best risky if its 2m mom > best safe's 2m mom AND > 0."""
    m = monthly.loc[:d]
    short_mom = mom_short_xs(m)
    risky_avail = [t for t in universe if t in short_mom.index and pd.notna(short_mom[t]) and pd.notna(close.loc[d].get(t, np.nan))]
    if not risky_avail:
        return {safe: 1.0}
    best_risky = short_mom.reindex(risky_avail).idxmax()
    safe_avail = [s for s in SAFE_POOL if s in short_mom.index and pd.notna(short_mom[s])]
    best_safe_short = short_mom.reindex(safe_avail).idxmax() if safe_avail else safe
    risky_m = short_mom.get(best_risky, np.nan)
    safe_m = short_mom.get(best_safe_short, np.nan)
    if pd.notna(risky_m) and pd.notna(safe_m) and risky_m > safe_m and risky_m > 0:
        return {best_risky: 1.0}
    return {best_safe_short: 1.0}


def rescue_half(close, monthly, d, universe, safe):
    """Same gating as simple_gtt; if pass -> 50/50 best risky + best safe."""
    m = monthly.loc[:d]
    short_mom = mom_short_xs(m)
    risky_avail = [t for t in universe if t in short_mom.index and pd.notna(short_mom[t]) and pd.notna(close.loc[d].get(t, np.nan))]
    if not risky_avail:
        return {safe: 1.0}
    best_risky = short_mom.reindex(risky_avail).idxmax()
    safe_avail = [s for s in SAFE_POOL if s in short_mom.index and pd.notna(short_mom[s])]
    best_safe_short = short_mom.reindex(safe_avail).idxmax() if safe_avail else safe
    risky_m = short_mom.get(best_risky, np.nan)
    safe_m = short_mom.get(best_safe_short, np.nan)
    if pd.notna(risky_m) and pd.notna(safe_m) and risky_m > safe_m and risky_m > 0:
        return {best_risky: 0.5, best_safe_short: 0.5}
    return {best_safe_short: 1.0}


# ---- main ----
def run(rescue_mode, universe, start, end):
    cols = list(dict.fromkeys(universe + SAFE_POOL + CANARY_ASSETS + [CASH]))
    cols = [c for c in cols if c in panel.columns]
    close = panel[cols]
    monthly = close.resample("ME").last()
    dates = month_end_dates(close.index, start, end)
    weights_map = {}
    prev_pair = None
    n_riskon = 0
    n_rescue_kept = 0  # for risk-off branch: how often did rescue keep risky asset
    n_riskoff = 0

    for d in dates:
        risky_on = canary_active(monthly, d)
        safe = best_safe(monthly, d) or CASH

        if not risky_on:
            n_riskoff += 1
            if rescue_mode == "none":
                weights_map[d] = {safe: 1.0}
            elif rescue_mode == "aggr_style":
                w = rescue_aggr_style(close, monthly, close, d, universe, safe)
                if any(t in universe for t in w):
                    n_rescue_kept += 1
                weights_map[d] = w
            elif rescue_mode == "simple_gtt":
                w = rescue_simple_gtt(close, monthly, d, universe, safe)
                if any(t in universe for t in w):
                    n_rescue_kept += 1
                weights_map[d] = w
            elif rescue_mode == "half_rescue":
                w = rescue_half(close, monthly, d, universe, safe)
                if any(t in universe for t in w):
                    n_rescue_kept += 1
                weights_map[d] = w
            prev_pair = None
            continue

        n_riskon += 1
        m = monthly.loc[:d]
        score = faber_sma(m)
        avail = [t for t in universe if t in score.index and pd.notna(score[t]) and pd.notna(close.loc[d].get(t, np.nan))]
        if not avail:
            weights_map[d] = {safe:1.0}
            prev_pair = None
            continue
        score_avail = score.loc[avail]
        z_avail = zscore(score_avail)
        ranked = score_avail.sort_values(ascending=False)
        half_n = max(2, (len(ranked)+1)//2)
        positive = ranked.iloc[:half_n][lambda s: s>0]
        if len(positive) < 2:
            if len(positive) == 1:
                weights_map[d] = {positive.index[0]: 0.5, safe: 0.5}
            else:
                weights_map[d] = {safe: 1.0}
            prev_pair = None
            continue
        candidates = list(positive.index)
        new_pair = lowest_corr_pair(close.loc[:d, candidates], candidates)
        if new_pair is None:
            weights_map[d] = {candidates[0]:1.0}
            prev_pair = None
            continue
        if prev_pair is not None and HOLD_BUFFER > 1e-9:
            new_set = list(new_pair)
            for prior in prev_pair:
                if prior in new_set or prior not in avail: continue
                if score_avail.get(prior, -np.inf) <= 0: continue
                z_prior = z_avail.get(prior, np.nan)
                if pd.isna(z_prior): continue
                swap_candidates = [x for x in new_set if x not in prev_pair]
                if not swap_candidates: continue
                swap_target = min(swap_candidates, key=lambda x: z_avail.get(x, np.inf))
                z_swap = z_avail.get(swap_target, np.nan)
                if pd.isna(z_swap): continue
                if z_swap - z_prior < HOLD_BUFFER:
                    new_set.remove(swap_target)
                    new_set.append(prior)
            new_pair = tuple(new_set[:2])
        weights_map[d] = {new_pair[0]:0.5, new_pair[1]:0.5}
        prev_pair = new_pair

    daily = segment_returns(close, weights_map, dates, end)
    return daily, n_riskon, n_riskoff, n_rescue_kept, weights_map


end = panel.index[-1]
start = pd.Timestamp("2001-08-30")  # GC=F-clean GLD start

results = {}
diags = {}
for uname, univ in UNIVERSES.items():
    for mode in ["none", "aggr_style", "simple_gtt", "half_rescue"]:
        label = f"{uname}_{mode}"
        daily, riskon, riskoff, rescue_kept, _ = run(mode, univ, start, end)
        results[label] = daily
        diags[label] = (riskon, riskoff, rescue_kept)
        print(f"{label}: risk-on {riskon}, risk-off {riskoff}, rescue kept risky in {rescue_kept}/{riskoff} risk-off months")

rows = []
for label, daily in results.items():
    if daily.empty: continue
    eq = (1.0+daily).cumprod()*100_000.0
    m = perf(daily, eq)
    m["strategy"] = label
    riskon, riskoff, rescue_kept = diags[label]
    m["riskon"] = riskon
    m["rescue_kept"] = rescue_kept
    m["years"] = round((daily.index[-1]-daily.index[0]).days/365.25, 1)
    rows.append(m)
df = pd.DataFrame(rows)[["strategy","years","riskon","rescue_kept","total_return","cagr","vol","sharpe","max_drawdown"]]
df = df.sort_values("sharpe", ascending=False).reset_index(drop=True)
print()
print(df.to_string(index=False, float_format=lambda x: f"{x:.4f}"))
df.to_csv("/tmp/risk_off_rescue_summary.csv", index=False)
