"""
Stress/robustness tests on PRODUCTION config.

#9 Bootstrap confidence intervals on Sharpe + CAGR + MaxDD via block-bootstrap of monthly returns
#10 Crisis year deep-dive: daily/monthly behavior in 2008, 2020, 2022
#11 Live peer comparison: compare against published peers ONLY using post-publication windows
   - Antonacci GEM: published 2014; live = 2015+
   - Keller VAA: published 2017; live = 2018+
   - Faber GTAA: published 2007; live = 2008+
"""
import sys
sys.path.insert(0, "/Users/rkautsar/personal/scripts/strategy_cpm")

import numpy as np
import pandas as pd
from itertools import combinations

PANEL_PATH = "/Users/rkautsar/personal/scripts/strategy_cpm/data/proxy_adjusted_close_daily.csv"
panel = pd.read_csv(PANEL_PATH, parse_dates=["Date"], index_col="Date").sort_index()
gld = pd.read_csv("/Users/rkautsar/personal/scripts/strategy_cpm/data/gld_stitched_daily_clean.csv", parse_dates=[0], index_col=0); gld.columns=["GLD"]
kmlm = pd.read_csv("/Users/rkautsar/personal/scripts/strategy_cpm/data/kmlm_stitched_daily.csv", parse_dates=[0], index_col=0); kmlm.columns=["KMLM_stitched"]
agg = pd.read_csv("/Users/rkautsar/personal/scripts/strategy_cpm/data/agg_stitched_daily.csv", parse_dates=[0], index_col=0); agg.columns=["AGG_stitched"]
tip_clean = pd.read_csv("/Users/rkautsar/personal/scripts/strategy_cpm/data/tip_stitched_daily.csv", parse_dates=[0], index_col=0); tip_clean.columns=["TIP_clean"]
panel = panel.join(gld, how="outer").join(kmlm, how="outer").join(agg, how="outer").join(tip_clean, how="outer").sort_index()
panel["TIP"] = panel["TIP_clean"]

# Fetch BIL and SHY for expanded safe pool (#8 finding)
import yfinance as yf
for t in ["BIL", "SHY"]:
    if t not in panel.columns:
        d = yf.download(t, start="2000-01-01", end="2026-05-14", auto_adjust=True, progress=False, threads=False)
        if isinstance(d.columns, pd.MultiIndex):
            d = d["Close"]
        c = d["Close"] if "Close" in d.columns else d.iloc[:, 0]
        c = c.dropna(); c.name = t
        panel = panel.join(c.to_frame(), how="outer").sort_index()
        print(f"Fetched {t}: {c.index[0].date()} -> {c.index[-1].date()}")

CASH = "SHV"; SAFE_POOL = ["BIL", "SHV", "SHY", "IEF"]
AGGR_ALL = ["QQQ","IGM","SPMO","XLE","XRT","SMH","COWZ","AVUV","MOO","RWJ","SPHQ","XMMO","XMHQ"]
UNIVERSE = AGGR_ALL + ["GLD", "KMLM_stitched"]
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

def perf(daily, eq):
    if daily.empty: return {}
    days = (eq.index[-1]-eq.index[0]).days; yrs = days/365.25
    cagr = (eq.iloc[-1]/eq.iloc[0])**(1/yrs)-1 if yrs>0 else float("nan")
    vol = daily.std(ddof=0)*np.sqrt(252)
    sharpe = (daily.mean()*252)/vol if vol>0 else float("nan")
    rm = eq.cummax(); mdd = (eq/rm-1).min()
    return {"cagr": cagr, "vol": vol, "sharpe": sharpe, "max_drawdown": mdd}

def compute_signal(monthly_panel, close_panel, sig_d, prev_pair):
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


def run_production(start, end, apply_vol_target=True, cost_bps=COST_BPS):
    cols = list(dict.fromkeys(UNIVERSE + SAFE_POOL + CANARY_ASSETS + [CASH]))
    cols = [c for c in cols if c in panel.columns]
    close = panel[cols]
    monthly_idx = pd.DataFrame({"x":1}, index=close.index).groupby(pd.Grouper(freq="ME")).tail(1)
    signal_dates = monthly_idx.index[(monthly_idx.index >= start) & (monthly_idx.index <= end)].tolist()
    weights_history = []; prev_pair = None
    for i, sig_d in enumerate(signal_dates):
        monthly_for_signal = close.loc[:sig_d].resample("ME").last()
        w, new_pair = compute_signal(monthly_for_signal, close, sig_d, prev_pair)
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
    pre_cost_daily = (df[common] * daily_ret[common]).sum(axis=1, min_count=1).fillna(0.0)
    for i in range(len(weights_history)):
        prev_w = weights_history[i-1][2] if i > 0 else {}
        curr_w = weights_history[i][2]
        keys = set(curr_w) | set(prev_w)
        turnover = sum(abs(curr_w.get(k, 0.0) - prev_w.get(k, 0.0)) for k in keys)
        cost = turnover * cost_bps / 10000.0
        apply_from = weights_history[i][0]
        if apply_from in pre_cost_daily.index:
            pre_cost_daily.loc[apply_from] -= cost
    daily = pre_cost_daily
    if apply_vol_target:
        realized = daily.rolling(VOL_LOOKBACK).std() * np.sqrt(252)
        scale = (TARGET_VOL / realized).clip(upper=MAX_LEV).shift(1).fillna(1.0)
        daily = daily * scale
    return daily.loc[(daily.index >= start) & (daily.index <= end)]


# Build production daily series
end = panel.index[-1]
start = pd.Timestamp("2001-08-30")
print("Running PRODUCTION strategy ...")
prod_daily = run_production(start, end)


# ============================================================
# #9 BOOTSTRAP CI
# ============================================================
print("\n" + "="*80)
print("#9 Bootstrap CI on key metrics (block bootstrap, B=2000, block=21d)")
print("="*80)

def stationary_block_bootstrap(daily, n_blocks_out=None, block_size=21, rng=None):
    """Stationary block bootstrap: sample contiguous blocks of given size with replacement."""
    if rng is None: rng = np.random.default_rng()
    n = len(daily)
    if n_blocks_out is None:
        n_blocks_out = (n + block_size - 1) // block_size
    starts = rng.integers(0, n - block_size + 1, size=n_blocks_out)
    blocks = [daily.iloc[s:s+block_size].values for s in starts]
    sample = np.concatenate(blocks)[:n]
    return pd.Series(sample, index=daily.index)

def bootstrap_metrics(daily, n_iter=2000, block_size=21):
    rng = np.random.default_rng(42)
    samples = {"sharpe": [], "cagr": [], "vol": [], "max_drawdown": []}
    for _ in range(n_iter):
        bs = stationary_block_bootstrap(daily, block_size=block_size, rng=rng)
        eq = (1.0+bs).cumprod()*100_000.0
        m = perf(bs, eq)
        for k in samples:
            samples[k].append(m[k])
    out = {}
    for k, vals in samples.items():
        vals = np.array(vals)
        out[k] = {
            "mean": vals.mean(),
            "median": np.median(vals),
            "p2.5": np.percentile(vals, 2.5),
            "p97.5": np.percentile(vals, 97.5),
            "p25": np.percentile(vals, 25),
            "p75": np.percentile(vals, 75),
        }
    return out

# Get observed metrics
obs_eq = (1.0+prod_daily).cumprod()*100_000.0
observed = perf(prod_daily, obs_eq)
print(f"Observed metrics:")
for k, v in observed.items():
    if k in ("sharpe", "cagr", "vol", "max_drawdown"):
        print(f"  {k:14s} {v:.4f}")

print(f"\nBootstrap distributions (B=2000, 21-day blocks):")
boot = bootstrap_metrics(prod_daily, n_iter=2000, block_size=21)
print(f"{'metric':14s} {'observed':>10s} {'mean':>10s} {'median':>10s} {'2.5%':>10s} {'25%':>10s} {'75%':>10s} {'97.5%':>10s}")
for k in ["sharpe","cagr","vol","max_drawdown"]:
    obs = observed[k]
    b = boot[k]
    print(f"{k:14s} {obs:>10.4f} {b['mean']:>10.4f} {b['median']:>10.4f} {b['p2.5']:>10.4f} {b['p25']:>10.4f} {b['p75']:>10.4f} {b['p97.5']:>10.4f}")

# Probability Sharpe > X
sharpes = []
rng = np.random.default_rng(42)
for _ in range(2000):
    bs = stationary_block_bootstrap(prod_daily, block_size=21, rng=rng)
    eq = (1.0+bs).cumprod()*100_000.0
    sharpes.append(perf(bs, eq)["sharpe"])
sharpes = np.array(sharpes)
print(f"\nP(Sharpe > 1.0): {(sharpes>1.0).mean()*100:.1f}%")
print(f"P(Sharpe > 0.9): {(sharpes>0.9).mean()*100:.1f}%")
print(f"P(Sharpe > 0.8): {(sharpes>0.8).mean()*100:.1f}%")
print(f"P(Sharpe > 0.66 [SPY]): {(sharpes>0.66).mean()*100:.1f}%")


# ============================================================
# #10 CRISIS YEAR DEEP-DIVE
# ============================================================
print("\n" + "="*80)
print("#10 Crisis year deep-dive: 2008, 2020, 2022")
print("="*80)
spy_daily = panel["SPY"].ffill().pct_change().loc[start:end].fillna(0.0)
both = pd.concat([prod_daily.rename("PROD"), spy_daily.rename("SPY")], axis=1).dropna()

for yr_label, yr_start, yr_end in [
    ("2008 GFC", "2008-01-01", "2008-12-31"),
    ("2020 COVID", "2020-01-01", "2020-12-31"),
    ("2022 inflation/rates", "2022-01-01", "2022-12-31"),
]:
    sub = both.loc[yr_start:yr_end]
    sub_eq_prod = (1.0+sub["PROD"]).cumprod()*100_000.0
    sub_eq_spy = (1.0+sub["SPY"]).cumprod()*100_000.0
    print(f"\n--- {yr_label} ({yr_start} to {yr_end}) ---")
    # Monthly returns
    mp = (1.0+sub["PROD"]).resample("ME").prod() - 1
    ms = (1.0+sub["SPY"]).resample("ME").prod() - 1
    df = pd.DataFrame({"SPY": ms, "PROD": mp})
    df["excess"] = df["PROD"] - df["SPY"]
    df.index = df.index.strftime("%Y-%m")
    print(df.to_string(float_format=lambda x: f"{x*100:+6.2f}%"))
    # Year totals
    yt_p = (1.0+sub["PROD"]).prod() - 1
    yt_s = (1.0+sub["SPY"]).prod() - 1
    # Worst-day, worst-week
    worst_day_p = sub["PROD"].min()
    worst_week_p = sub["PROD"].rolling(5).sum().min()
    worst_day_s = sub["SPY"].min()
    worst_week_s = sub["SPY"].rolling(5).sum().min()
    # Intra-year MaxDD
    dd_p = sub_eq_prod / sub_eq_prod.cummax() - 1
    dd_s = sub_eq_spy / sub_eq_spy.cummax() - 1
    print(f"  YEAR: SPY {yt_s*100:+6.2f}% | PROD {yt_p*100:+6.2f}% | excess {(yt_p-yt_s)*100:+6.2f}pp")
    print(f"  WorstDay: SPY {worst_day_s*100:+5.2f}% | PROD {worst_day_p*100:+5.2f}%")
    print(f"  Worst5d:  SPY {worst_week_s*100:+5.2f}% | PROD {worst_week_p*100:+5.2f}%")
    print(f"  IntraYr MaxDD: SPY {dd_s.min()*100:+5.2f}% | PROD {dd_p.min()*100:+5.2f}%")


# ============================================================
# #11 LIVE PEER COMPARISON
# ============================================================
print("\n" + "="*80)
print("#11 LIVE peer comparison (post-publication windows only)")
print("="*80)

# Re-implement peer strategies (same as final_benchmark.py)
def faber_gtaa5(start, end):
    universe = ["SPY","EFA","IEF","VNQ","DBC"]
    cols = [c for c in universe if c in panel.columns] + [CASH]
    close = panel[cols]; monthly = close.resample("ME").last()
    monthly_idx = pd.DataFrame({"x":1}, index=close.index).groupby(pd.Grouper(freq="ME")).tail(1)
    dates = monthly_idx.index[(monthly_idx.index>=start)&(monthly_idx.index<=end)].tolist()
    weights_map = {}
    for d in dates:
        m = monthly.loc[:d]; sma = m.rolling(10).mean().iloc[-1]; last = m.iloc[-1]
        in_u = [a for a in universe if a in last.index and pd.notna(sma.get(a)) and pd.notna(last[a]) and last[a] > sma[a]]
        w = {a: 0.20 for a in in_u}
        if 5 - len(in_u) > 0: w[CASH] = 0.20*(5-len(in_u))
        weights_map[d] = w if w else {CASH: 1.0}
    daily_ret = close.ffill().pct_change()
    out = pd.Series(0.0, index=close.index)
    for i, d in enumerate(dates):
        nxt = dates[i+1] if i+1 < len(dates) else end
        seg = close.index[(close.index > d) & (close.index <= nxt)]
        w = weights_map.get(d, {})
        if not w: continue
        cs = [c for c in w if c in daily_ret.columns]
        if not cs: continue
        out.loc[seg] = daily_ret.loc[seg, cs].mul(pd.Series({k: w[k] for k in cs}), axis=1).sum(axis=1, min_count=1).fillna(0.0)
    return out.loc[(out.index>=start)&(out.index<=end)]

def antonacci_gem(start, end):
    universe = ["SPY","EFA","SHV","AGG_stitched"]
    cols = [c for c in universe if c in panel.columns]
    close = panel[cols]; monthly = close.resample("ME").last()
    monthly_idx = pd.DataFrame({"x":1}, index=close.index).groupby(pd.Grouper(freq="ME")).tail(1)
    dates = monthly_idx.index[(monthly_idx.index>=start)&(monthly_idx.index<=end)].tolist()
    weights_map = {}
    for d in dates:
        m = monthly.loc[:d]
        if len(m) < 13: weights_map[d] = {CASH:1.0}; continue
        spy_12 = m["SPY"].iloc[-1]/m["SPY"].iloc[-13]-1
        cash_12 = m["SHV"].iloc[-1]/m["SHV"].iloc[-13]-1
        if spy_12 <= cash_12:
            weights_map[d] = {"AGG_stitched":1.0}
        else:
            efa_12 = m["EFA"].iloc[-1]/m["EFA"].iloc[-13]-1
            weights_map[d] = {"SPY":1.0} if spy_12 >= efa_12 else {"EFA":1.0}
    daily_ret = close.ffill().pct_change()
    out = pd.Series(0.0, index=close.index)
    for i, d in enumerate(dates):
        nxt = dates[i+1] if i+1 < len(dates) else end
        seg = close.index[(close.index > d) & (close.index <= nxt)]
        w = weights_map.get(d, {})
        if not w: continue
        cs = [c for c in w if c in daily_ret.columns]
        if not cs: continue
        out.loc[seg] = daily_ret.loc[seg, cs].mul(pd.Series({k: w[k] for k in cs}), axis=1).sum(axis=1, min_count=1).fillna(0.0)
    return out.loc[(out.index>=start)&(out.index<=end)]

def keller_vaa_g4(start, end):
    offensive = ["SPY","EFA","EEM","AGG_stitched"]
    defensive = ["SHV","IEF"]
    cols = list(dict.fromkeys(offensive + defensive))
    cols = [c for c in cols if c in panel.columns]
    close = panel[cols]; monthly = close.resample("ME").last()
    monthly_idx = pd.DataFrame({"x":1}, index=close.index).groupby(pd.Grouper(freq="ME")).tail(1)
    dates = monthly_idx.index[(monthly_idx.index>=start)&(monthly_idx.index<=end)].tolist()
    weights_map = {}
    for d in dates:
        m = monthly.loc[:d]
        scores_off = {a: sig_13612W(m[a]) for a in offensive if a in m.columns}
        if any(pd.isna(v) for v in scores_off.values()):
            weights_map[d] = {CASH:1.0}; continue
        if all(v > 0 for v in scores_off.values()):
            best = max(scores_off, key=scores_off.get)
            weights_map[d] = {best:1.0}
        else:
            sd = {a: sig_13612W(m[a]) for a in defensive if a in m.columns}
            valid = {k:v for k,v in sd.items() if pd.notna(v)}
            best = max(valid, key=valid.get) if valid else CASH
            weights_map[d] = {best:1.0}
    daily_ret = close.ffill().pct_change()
    out = pd.Series(0.0, index=close.index)
    for i, d in enumerate(dates):
        nxt = dates[i+1] if i+1 < len(dates) else end
        seg = close.index[(close.index > d) & (close.index <= nxt)]
        w = weights_map.get(d, {})
        if not w: continue
        cs = [c for c in w if c in daily_ret.columns]
        if not cs: continue
        out.loc[seg] = daily_ret.loc[seg, cs].mul(pd.Series({k: w[k] for k in cs}), axis=1).sum(axis=1, min_count=1).fillna(0.0)
    return out.loc[(out.index>=start)&(out.index<=end)]

# Live windows
LIVE_WINDOWS = [
    ("Faber_GTAA5",  "2008-01-01", "2026-05-13", faber_gtaa5),
    ("Antonacci_GEM","2015-01-01", "2026-05-13", antonacci_gem),
    ("Keller_VAA_G4","2018-01-01", "2026-05-13", keller_vaa_g4),
]

# SPY benchmark for each window
def spy_in_window(s, e):
    return spy_daily.loc[s:e]

print(f"\n{'Strategy':20s} {'Live since':12s} {'Years':>6s} {'Sharpe':>8s} {'CAGR':>8s} {'MaxDD':>8s} {'vs SPY':>8s}")
print("-"*80)
for name, ws, we, fn in LIVE_WINDOWS:
    ws_ts, we_ts = pd.Timestamp(ws), pd.Timestamp(we)
    daily_p = fn(ws_ts, we_ts)
    eq = (1.0+daily_p).cumprod()*100_000.0
    m = perf(daily_p, eq)
    daily_s = spy_in_window(ws_ts, we_ts)
    eq_s = (1.0+daily_s).cumprod()*100_000.0
    ms = perf(daily_s, eq_s)
    yrs = (we_ts-ws_ts).days/365.25
    print(f"{name:20s} {ws:12s} {yrs:>6.1f} {m['sharpe']:>8.3f} {m['cagr']*100:>7.2f}% {m['max_drawdown']*100:>7.2f}% {(m['sharpe']-ms['sharpe']):>+8.3f}")

# Our strategy in same windows
print(f"\n{'PRODUCTION (this) vs same live windows:':50s}")
for name, ws, we, _ in LIVE_WINDOWS:
    ws_ts, we_ts = pd.Timestamp(ws), pd.Timestamp(we)
    sub = prod_daily.loc[ws_ts:we_ts]
    eq = (1.0+sub).cumprod()*100_000.0
    m = perf(sub, eq)
    daily_s = spy_in_window(ws_ts, we_ts)
    eq_s = (1.0+daily_s).cumprod()*100_000.0
    ms = perf(daily_s, eq_s)
    yrs = (we_ts-ws_ts).days/365.25
    print(f"  PROD vs {name:18s} window {ws}: {yrs:.1f}y  Sharpe {m['sharpe']:.3f}  CAGR {m['cagr']*100:.2f}%  MaxDD {m['max_drawdown']*100:.2f}%  excess vs SPY {m['sharpe']-ms['sharpe']:+.3f}")
