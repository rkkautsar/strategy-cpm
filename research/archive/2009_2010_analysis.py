"""
Compare OUR_STACK (cherry config) vs other momentum strategies during 2009-2010
to see if the 'recovery whipsaw' problem is universal or our-engine-specific.
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
SAFE_POOL = ["SHV", "IEF"]
AGGR_ALL = ["QQQ","IGM","SPMO","XLE","XRT","SMH","COWZ","AVUV","MOO","RWJ","SPHQ","XMMO","XMHQ"]
UNIVERSE = AGGR_ALL + ["GLD", "KMLM_stitched"]
CANARY_ASSETS = ["SPY", "TIP"]


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

def month_end_dates(idx, start, end):
    sub = idx[(idx>=start)&(idx<=end)]
    return pd.DataFrame({"x":1}, index=sub).groupby(pd.Grouper(freq="ME")).tail(1).index.to_list()

def best_safe(monthly, d):
    m = monthly.loc[:d]
    av = [s for s in SAFE_POOL if s in m.columns and m[s].first_valid_index() is not None]
    if not av: return CASH
    if len(m) < 10: return av[0]
    sma = m[av].rolling(10).mean().iloc[-1]; last = m[av].iloc[-1]
    dist = ((last-sma)/sma).dropna()
    return dist.idxmax() if not dist.empty else av[0]

def segment_returns(close, weights_map, dates, end):
    daily = close.ffill().pct_change()
    period_idx = close.index[(close.index>=dates[0])&(close.index<=end)]
    out = pd.Series(0.0, index=period_idx)
    for i, d in enumerate(dates):
        nxt = dates[i+1] if i+1<len(dates) else end
        seg = period_idx[(period_idx>d)&(period_idx<=nxt)]
        if len(seg)==0: continue
        w = weights_map.get(d, {})
        if not w: continue
        cols = [c for c in w if c in daily.columns]
        if not cols: continue
        out.loc[seg] = daily.loc[seg, cols].mul(pd.Series({k:w[k] for k in cols}), axis=1).sum(axis=1, min_count=1).fillna(0.0)
    return out

def perf(daily, eq):
    if daily.empty: return {}
    days = (eq.index[-1]-eq.index[0]).days; yrs = days/365.25
    cagr = (eq.iloc[-1]/eq.iloc[0])**(1/yrs)-1 if yrs>0 else float("nan")
    vol = daily.std(ddof=0)*np.sqrt(252)
    sharpe = (daily.mean()*252)/vol if vol>0 else float("nan")
    rm = eq.cummax(); mdd = (eq/rm-1).min()
    return {"cagr": cagr, "vol": vol, "sharpe": sharpe, "max_drawdown": mdd}


# OUR STACK (CHERRY config: buffer=3.0, corr_lookback=378)
def our_stack_cherry(start, end):
    cols = list(dict.fromkeys(UNIVERSE + SAFE_POOL + CANARY_ASSETS + [CASH]))
    cols = [c for c in cols if c in panel.columns]
    close = panel[cols]; monthly = close.resample("ME").last()
    dates = month_end_dates(close.index, start, end)
    weights_map = {}; prev_pair = None
    BUFFER = 3.0; LOOKBACK = 378
    for d in dates:
        m = monthly.loc[:d]
        on = True
        for c in CANARY_ASSETS:
            if c in m.columns:
                s = sig_13612W(m[c])
                if pd.isna(s) or s <= 0: on = False; break
        safe = best_safe(monthly, d) or CASH
        if not on:
            weights_map[d] = {safe: 1.0}; prev_pair = None; continue
        score = faber_sma_xs(m)
        avail = [t for t in UNIVERSE if t in score.index and pd.notna(score[t]) and pd.notna(close.loc[d].get(t, np.nan))]
        if not avail: weights_map[d] = {safe: 1.0}; prev_pair = None; continue
        sa = score.loc[avail]; za = zscore(sa)
        ranked = sa.sort_values(ascending=False)
        positive = ranked.iloc[:max(2,(len(ranked)+1)//2)][lambda s: s>0]
        if len(positive) < 2:
            if len(positive) == 1:
                weights_map[d] = {positive.index[0]: 0.5, safe: 0.5}
            else:
                weights_map[d] = {safe: 1.0}
            prev_pair = None; continue
        candidates = list(positive.index)
        new_pick = lowest_corr_pair(close.loc[:d, candidates], candidates, LOOKBACK)
        if new_pick is None:
            weights_map[d] = {candidates[0]: 1.0}; prev_pair = None; continue
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
        weights_map[d] = {new_pick[0]: 0.5, new_pick[1]: 0.5}
        prev_pair = new_pick
    return segment_returns(close, weights_map, dates, end)


def faber_gtaa5(start, end):
    universe = ["SPY","EFA","IEF","VNQ","DBC"]
    close = panel[universe + [CASH]]; monthly = close.resample("ME").last()
    dates = month_end_dates(close.index, start, end)
    weights_map = {}
    for d in dates:
        m = monthly.loc[:d]; sma = m.rolling(10).mean().iloc[-1]; last = m.iloc[-1]
        in_uptrend = [a for a in universe if a in last.index and pd.notna(sma.get(a)) and pd.notna(last[a]) and last[a] > sma[a]]
        w = {a: 0.20 for a in in_uptrend}
        if 5 - len(in_uptrend) > 0:
            w[CASH] = 0.20 * (5 - len(in_uptrend))
        weights_map[d] = w if w else {CASH: 1.0}
    return segment_returns(close, weights_map, dates, end)


def antonacci_gem(start, end):
    universe = ["SPY","EFA","SHV","AGG_stitched"]
    cols = [c for c in universe if c in panel.columns]
    close = panel[cols]; monthly = close.resample("ME").last()
    dates = month_end_dates(close.index, start, end)
    weights_map = {}
    for d in dates:
        m = monthly.loc[:d]
        if len(m) < 13: weights_map[d] = {CASH:1.0}; continue
        spy_12 = m["SPY"].iloc[-1]/m["SPY"].iloc[-13]-1
        cash_12 = m["SHV"].iloc[-1]/m["SHV"].iloc[-13]-1 if "SHV" in m.columns else 0.0
        if spy_12 <= cash_12:
            weights_map[d] = {"AGG_stitched": 1.0}
        else:
            efa_12 = m["EFA"].iloc[-1]/m["EFA"].iloc[-13]-1 if "EFA" in m.columns else -np.inf
            weights_map[d] = {"SPY": 1.0} if spy_12 >= efa_12 else {"EFA": 1.0}
    return segment_returns(close, weights_map, dates, end)


def keller_vaa_g4(start, end):
    offensive = ["SPY","EFA","EEM","AGG_stitched"]
    defensive = ["SHV","IEF"]
    cols = list(dict.fromkeys(offensive + defensive))
    cols = [c for c in cols if c in panel.columns]
    close = panel[cols]; monthly = close.resample("ME").last()
    dates = month_end_dates(close.index, start, end)
    weights_map = {}
    for d in dates:
        m = monthly.loc[:d]
        scores_off = {a: sig_13612W(m[a]) for a in offensive if a in m.columns}
        if any(pd.isna(v) for v in scores_off.values()):
            weights_map[d] = {CASH:1.0}; continue
        if all(v > 0 for v in scores_off.values()):
            best = max(scores_off, key=scores_off.get)
            weights_map[d] = {best: 1.0}
        else:
            scores_def = {a: sig_13612W(m[a]) for a in defensive if a in m.columns}
            valid = {k:v for k,v in scores_def.items() if pd.notna(v)}
            best = max(valid, key=valid.get) if valid else CASH
            weights_map[d] = {best: 1.0}
    return segment_returns(close, weights_map, dates, end)


def keller_haa_balanced(start, end):
    canary = ["TIP", "AGG_stitched"]
    offensive = ["SPY","IWM","VEA","VWO","VNQ","DBC","IEF","TLT"]
    defensive = ["SHV","IEF"]
    cols = list(dict.fromkeys(canary + offensive + defensive))
    cols = [c for c in cols if c in panel.columns]
    close = panel[cols]; monthly = close.resample("ME").last()
    dates = month_end_dates(close.index, start, end)
    weights_map = {}
    for d in dates:
        m = monthly.loc[:d]
        canary_scores = {a: sig_13612W(m[a]) for a in canary if a in m.columns}
        if any(pd.isna(v) for v in canary_scores.values()):
            weights_map[d] = {CASH:1.0}; continue
        if all(v > 0 for v in canary_scores.values()):
            off_scores = {a: sig_13612W(m[a]) for a in offensive if a in m.columns}
            valid_pos = sorted([a for a, v in off_scores.items() if pd.notna(v) and v > 0],
                               key=lambda a: off_scores[a], reverse=True)[:4]
            if not valid_pos: weights_map[d] = {CASH:1.0}; continue
            w = 1.0/len(valid_pos)
            weights_map[d] = {a: w for a in valid_pos}
        else:
            def_scores = {a: sig_13612W(m[a]) for a in defensive if a in m.columns}
            valid = {k:v for k,v in def_scores.items() if pd.notna(v)}
            if not valid: weights_map[d] = {CASH:1.0}; continue
            best = max(valid, key=valid.get)
            weights_map[d] = {best: 1.0}
    return segment_returns(close, weights_map, dates, end)


def dual_mom_sectors(start, end):
    universe = ["XLK","XLE","XLF","XLV","XLI","XLY","XLP","XLB","XLU"]
    universe = [u for u in universe if u in panel.columns]
    cols = universe + [CASH]
    close = panel[cols]; monthly = close.resample("ME").last()
    dates = month_end_dates(close.index, start, end)
    weights_map = {}
    for d in dates:
        m = monthly.loc[:d]
        if len(m) < 13: weights_map[d] = {CASH:1.0}; continue
        scores = {a: m[a].iloc[-1]/m[a].iloc[-13]-1 for a in universe if pd.notna(m[a].iloc[-13])}
        positive = sorted([(a, s) for a, s in scores.items() if pd.notna(s) and s > 0], key=lambda x: x[1], reverse=True)[:2]
        if not positive: weights_map[d] = {CASH:1.0}; continue
        w = 1.0/len(positive)
        weights_map[d] = {a: w for a, _ in positive}
    return segment_returns(close, weights_map, dates, end)


def spy_bh(start, end):
    px = panel["SPY"].ffill().loc[start:end].dropna()
    return px.pct_change().fillna(0.0)


# ============================================================
# RUN
# ============================================================
# Need 13mo warmup for 13612W
warmup_start = pd.Timestamp("2007-12-01")  # 13mo before 2009-01
window_start = pd.Timestamp("2009-01-01")
window_end = pd.Timestamp("2010-12-31")

strategies = {
    "OUR_STACK_cherry": our_stack_cherry,
    "Faber_GTAA5":     faber_gtaa5,
    "Antonacci_GEM":   antonacci_gem,
    "Keller_VAA_G4":   keller_vaa_g4,
    "Keller_HAA_bal":  keller_haa_balanced,
    "DualMom_Sectors": dual_mom_sectors,
    "SPY_BH":          spy_bh,
}

results = {}
for name, fn in strategies.items():
    print(f"Running {name}...")
    daily = fn(warmup_start, window_end)
    sub = daily.loc[window_start:window_end]
    results[name] = sub

# 2009-2010 perf
print()
print("="*80)
print("2009-2010 (post-GFC recovery) performance")
print("="*80)
rows = []
for name, daily in results.items():
    if daily.empty: continue
    eq = (1.0+daily).cumprod()*100_000.0
    m = perf(daily, eq); m["strategy"] = name
    rows.append(m)
df = pd.DataFrame(rows)[["strategy","cagr","vol","sharpe","max_drawdown"]]
df = df.sort_values("cagr", ascending=False).reset_index(drop=True)
print(df.to_string(index=False, float_format=lambda x: f"{x:.4f}"))

# Year-by-year breakdown 2009 vs 2010
print()
print("="*80)
print("Yearly returns 2009 vs 2010 vs SPY")
print("="*80)
yearly_rows = []
for name, daily in results.items():
    if daily.empty: continue
    yr = (1.0+daily).resample("YE").prod() - 1.0
    yearly_rows.append({"strategy": name, "2009": yr.iloc[0] if len(yr)>0 else np.nan, "2010": yr.iloc[1] if len(yr)>1 else np.nan})
y_df = pd.DataFrame(yearly_rows).set_index("strategy")
y_df["2009_vs_SPY"] = y_df["2009"] - y_df.loc["SPY_BH","2009"]
y_df["2010_vs_SPY"] = y_df["2010"] - y_df.loc["SPY_BH","2010"]
print(y_df.to_string(float_format=lambda x: f"{x*100:+6.2f}%"))

# Quarterly granularity for OUR_STACK
print()
print("="*80)
print("Quarterly returns OUR_STACK_cherry vs SPY (2009-2010)")
print("="*80)
ours = results["OUR_STACK_cherry"]
spy = results["SPY_BH"]
qtr_ours = (1.0+ours).resample("QE").prod() - 1.0
qtr_spy = (1.0+spy).resample("QE").prod() - 1.0
qq = pd.DataFrame({"SPY": qtr_spy, "OUR": qtr_ours})
qq["excess"] = qq["OUR"] - qq["SPY"]
print(qq.to_string(float_format=lambda x: f"{x*100:+6.2f}%"))
