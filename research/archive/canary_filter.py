"""
HAA-style canary filter overlay on Pair_MSMAdist_50_50 + hold_buffer=1.0.

Base universe: AGGR_orig (proxy) + clean GLD.
Canary signal: Keller's 13612W = (12*r1 + 4*r3 + 2*r6 + r12) / 19.
Defensive: 100% SHV.

Variants:
  None        — no filter (baseline)
  TIP_up      — risky only when TIP_13612W > 0
  TIP_down    — risky only when TIP_13612W < 0  (anti-canary sanity)
  SPY_up      — risky only when SPY_13612W > 0
  SPY_down    — risky only when SPY_13612W < 0
  SPY+TIP_up  — risky only when BOTH SPY and TIP > 0
  SPY+TIP_down— risky only when BOTH SPY and TIP < 0
  SPY+TIP+EEM_up   — all three > 0
  SPY+TIP+EEM_down — all three < 0
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

# Need SPY, TIP, EEM as canaries (already in panel)
print(f"Panel: {panel.index[0].date()} -> {panel.index[-1].date()}, cols: {list(panel.columns)}")
for c in ["SPY","TIP","EEM"]:
    if c not in panel.columns:
        print(f"WARN: {c} missing")
    else:
        fv = panel[c].first_valid_index()
        print(f"  Canary {c}: first valid {fv.date() if fv else 'NONE'}")

CASH = "SHV"
SAFE_POOL = ["SHV", "IEF"]   # BIL not in proxy panel; SHV+IEF cover short + int-term treasuries
CORR_LOOKBACK_DAYS = 252
HOLD_BUFFER = 1.0
AGGR_ALL = ["QQQ","IGM","SPMO","XLE","XRT","SMH","COWZ","AVUV","MOO","RWJ","SPHQ","XMMO","XMHQ"]
UNIVERSE = AGGR_ALL + ["GLD"]


def best_safe(monthly_panel, d):
    """Pick best safe asset by Faber_SMA distance."""
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

# ---- engine ----
def faber_sma(monthly):
    if len(monthly) < 10:
        return pd.Series(np.nan, index=monthly.columns)
    sma = monthly.rolling(10).mean().iloc[-1]
    return (monthly.iloc[-1] - sma) / sma

def keller_13612W_single(monthly_series: pd.Series) -> float:
    """Keller's 13612W momentum for a single asset's monthly price series."""
    if len(monthly_series) < 13: return np.nan
    p = monthly_series.dropna()
    if len(p) < 13: return np.nan
    last = p.iloc[-1]
    r1 = last/p.iloc[-2]-1
    r3 = last/p.iloc[-4]-1
    r6 = last/p.iloc[-7]-1
    r12 = last/p.iloc[-13]-1
    return (12*r1 + 4*r3 + 2*r6 + r12) / 19.0

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
    if pd.isna(sd) or sd == 0:
        return pd.Series(0.0, index=s.index)
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

def evaluate_canary(monthly_panel, canary_assets, mode, d):
    """Return True if risk-on signal active.
       mode='up'   -> risky only when ALL canaries' 13612W > 0 (defensive otherwise)
       mode='down' -> defensive only when ALL canaries' 13612W < 0 (risky otherwise)
       mode=None   -> always risky
    """
    if mode is None:
        return True
    m = monthly_panel.loc[:d]
    scores = {}
    for c in canary_assets:
        if c not in m.columns:
            return True  # no data, default risky
        s = keller_13612W_single(m[c])
        if pd.isna(s):
            return True
        scores[c] = s
    if mode == "up":
        return all(v > 0 for v in scores.values())
    if mode == "down":
        # defensive only if ALL canaries < 0; risky otherwise
        return not all(v < 0 for v in scores.values())
    return True


def run_pair_with_canary(close_panel, universe, canary_assets, mode, start, end, buffer=HOLD_BUFFER):
    cols = list(dict.fromkeys([c for c in universe if c in close_panel.columns] + [CASH] + [c for c in canary_assets if c in close_panel.columns]))
    close = close_panel[cols]
    monthly = close.resample("ME").last()
    dates = month_end_dates(close.index, start, end)
    weights_map = {}
    prev_pair = None
    n_riskon = 0
    n_total = 0
    for d in dates:
        n_total += 1
        risky_on = evaluate_canary(monthly, canary_assets, mode, d)
        safe = best_safe(monthly, d) or CASH
        if not risky_on:
            weights_map[d] = {safe: 1.0} if safe in close.columns and pd.notna(close.loc[d].get(safe, np.nan)) else {}
            prev_pair = None  # break hold buffer when defensive
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
                # Half risky + half best safe (absolute momentum partial fill)
                weights_map[d] = {positive.index[0]: 0.5, safe: 0.5}
            else:
                # All zero/negative momentum -> full defensive
                weights_map[d] = {safe: 1.0}
            prev_pair = None
            continue
        candidates = list(positive.index)
        new_pair = lowest_corr_pair(close.loc[:d, candidates], candidates)
        if new_pair is None:
            weights_map[d] = {candidates[0]:1.0}
            prev_pair = None
            continue
        if prev_pair is not None and buffer > 1e-9:
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
                if z_swap - z_prior < buffer:
                    new_set.remove(swap_target)
                    new_set.append(prior)
            new_pair = tuple(new_set[:2])
        weights_map[d] = {new_pair[0]:0.5, new_pair[1]:0.5}
        prev_pair = new_pair
    daily = segment_returns(close, weights_map, dates, end)
    return daily, weights_map, n_riskon, n_total


# ---- run ----
FILTERS = [
    ("None",            [],                 None),
    ("TIP_up",          ["TIP"],            "up"),
    ("TIP_down",        ["TIP"],            "down"),
    ("SPY_up",          ["SPY"],            "up"),
    ("SPY_down",        ["SPY"],            "down"),
    ("SPY+TIP_up",      ["SPY","TIP"],      "up"),
    ("SPY+TIP_down",    ["SPY","TIP"],      "down"),
    ("SPY+TIP+EEM_up",  ["SPY","TIP","EEM"],"up"),
    ("SPY+TIP+EEM_down",["SPY","TIP","EEM"],"down"),
]

def first_valid(panel, universe, canary):
    sub = panel[[t for t in (list(universe)+list(canary)) if t in panel.columns]]
    fv = sub.apply(lambda c: c.first_valid_index())
    return fv.max() + pd.DateOffset(months=13)  # 13mo for keller_13612W

end = panel.index[-1]
results = {}
diags = {}
for name, canary, mode in FILTERS:
    earliest = first_valid(panel, UNIVERSE, canary)
    start = max(pd.Timestamp("2001-08-30"), earliest)
    daily, wmap, riskon, total = run_pair_with_canary(panel, UNIVERSE, canary, mode, start, end)
    results[name] = daily
    diags[name] = (riskon, total, start)

rows = []
for name, daily in results.items():
    if daily.empty: continue
    eq = (1.0+daily).cumprod()*100_000.0
    m = perf(daily, eq)
    m["filter"] = name
    m["start"] = daily.index[0].date().isoformat()
    m["years"] = round((daily.index[-1]-daily.index[0]).days/365.25, 1)
    riskon, total, _ = diags[name]
    m["riskon_pct"] = round(100.0*riskon/total, 1) if total else 0
    rows.append(m)
df = pd.DataFrame(rows)[["filter","start","years","riskon_pct","total_return","cagr","vol","sharpe","max_drawdown"]]
df = df.sort_values("sharpe", ascending=False).reset_index(drop=True)
print()
print(df.to_string(index=False, float_format=lambda x: f"{x:.4f}"))
df.to_csv("/tmp/canary_filter_summary.csv", index=False)
