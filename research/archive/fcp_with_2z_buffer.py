"""
FCP with HOLD_BUFFER=2z (robust setting, not overfit to 2008-2014).
Re-run PSR and SOTA peer comparison to see if edge survives.
"""
from __future__ import annotations
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm
from scipy.optimize import minimize
from itertools import combinations

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import strategy_fcp.fcp_live as fcp
from strategy_fcp.fcp_live import (
    load_panel, sig_13612W, RISKY_UNIVERSE as FCP15, run_fcp_backtest, CANARY_ASSETS,
    DEFAULT_CASH,
)

LB = 252
COST_BPS_SIDE = 10
HAA9 = ["SPY", "QQQ", "IWM", "VEA", "VWO", "VNQ", "DBC", "GLD", "TLT"]
SAFE_POOL_AAA = ["SHV", "IEF"]


def run_fcp_buf(panel, start, end, buf, vt=True, cost_bps=10):
    saved = fcp.HOLD_BUFFER
    fcp.HOLD_BUFFER = buf
    try:
        daily, _ = run_fcp_backtest(panel, start, end, apply_vol_target=vt, cost_bps=cost_bps)
        eq = (1 + daily).cumprod()
        return pd.DataFrame({"equity": eq, "daily_ret": daily})
    finally:
        fcp.HOLD_BUFFER = saved


def get_eom_dates(panel, start, end):
    idx = panel.loc[start:end].index
    return list(pd.Series(idx).groupby(idx.to_period("M")).last())


def best_safe_aaa(monthly):
    avail = [s for s in SAFE_POOL_AAA if s in monthly.columns and pd.notna(monthly[s].iloc[-1])]
    if not avail: return DEFAULT_CASH
    sc = {s: sig_13612W(monthly[s]) for s in avail}
    sc = {k: v for k, v in sc.items() if pd.notna(v)}
    return max(sc, key=sc.get) if sc else avail[0]


def dynamic_avail(panel, sig_d, universe, daily_lb=252):
    monthly = panel.loc[:sig_d].resample("ME").last()
    out = []
    for u in universe:
        if u not in panel.columns: continue
        m = monthly[u].dropna() if u in monthly.columns else pd.Series(dtype=float)
        d = panel[u].loc[:sig_d].dropna()
        if len(m) < 13 or len(d) < daily_lb: continue
        out.append(u)
    return out


def mom_6mo(panel, sig_d, asset):
    p = panel[asset].loc[:sig_d].dropna()
    if len(p) < 127: return np.nan
    return p.iloc[-1] / p.iloc[-127] - 1


def aaa_canonical(panel, sig_d, universe=HAA9, K=5):
    monthly = panel.loc[:sig_d].resample("ME").last()
    bs = best_safe_aaa(monthly)
    avail = dynamic_avail(panel, sig_d, universe, daily_lb=126)
    moms = {u: mom_6mo(panel, sig_d, u) for u in avail}
    moms = {k: v for k, v in moms.items() if pd.notna(v) and v > 0}
    if len(moms) < 2: return {bs: 1.0}
    ranked = sorted(moms.items(), key=lambda kv: kv[1], reverse=True)[:K]
    selected = [u for u, _ in ranked]
    if len(selected) < 2: return {bs: 1.0}
    rets_corr = panel.loc[:sig_d, selected].iloc[-126:].pct_change().dropna()
    rets_vol = panel.loc[:sig_d, selected].iloc[-20:].pct_change().dropna()
    if len(rets_corr) < 63 or len(rets_vol) < 10: return {bs: 1.0}
    corr = rets_corr.corr().values
    vols = rets_vol.std().values
    cov = corr * np.outer(vols, vols)
    n = len(selected)
    cons = ({"type": "eq", "fun": lambda w: w.sum() - 1.0},)
    bnds = [(0.0, 1.0)] * n
    x0 = np.ones(n) / n
    res = minimize(lambda w: w @ cov @ w, x0, method="SLSQP", bounds=bnds,
                   constraints=cons, options={"maxiter": 200, "ftol": 1e-9})
    w = res.x if res.success else x0
    return {selected[i]: float(w[i]) for i in range(n) if w[i] > 1e-4}


def haa_balanced(panel, sig_d):
    monthly = panel.loc[:sig_d].resample("ME").last()
    bs = best_safe_aaa(monthly)
    if "TIP" in monthly.columns and pd.notna(monthly["TIP"].iloc[-1]):
        tip_s = sig_13612W(monthly["TIP"])
        if pd.isna(tip_s) or tip_s <= 0: return {bs: 1.0}
    avail = dynamic_avail(panel, sig_d, ["SPY","IWM","VEA","VWO","VNQ","DBC","GLD","TLT"])
    scs = {u: sig_13612W(monthly[u]) for u in avail}
    scs = {k: v for k, v in scs.items() if pd.notna(v)}
    if not scs: return {bs: 1.0}
    ranked = sorted(scs.items(), key=lambda kv: kv[1], reverse=True)[:4]
    n = len(ranked)
    w = {}
    for t, sc in ranked:
        if sc > 0: w[t] = w.get(t, 0) + 1.0/n
        else: w[bs] = w.get(bs, 0) + 1.0/n
    return w


def faber_gtaa5(panel, sig_d):
    monthly = panel.loc[:sig_d].resample("ME").last()
    weights = {}
    for asset in ["SPY","EFA","IEF","VNQ","DBC"]:
        if asset not in monthly.columns: continue
        p = monthly[asset].dropna()
        if len(p) < 11: continue
        sma = p.iloc[-11:-1].mean()
        if p.iloc[-1] > sma: weights[asset] = 0.20
    cash_share = 1.0 - sum(weights.values())
    if cash_share > 0.001: weights["SHV"] = cash_share
    return weights or {"SHV": 1.0}


def static_60_40(p, d): return {"SPY": 0.6, "IEF": 0.4}
def static_pp_ief(p, d): return {"SPY": 0.25, "IEF": 0.25, "GLD": 0.25, "SHV": 0.25}
def buyhold_spy(p, d): return {"SPY": 1.0}


def simulate(panel, start, end, target_fn, cost_bps=COST_BPS_SIDE):
    eom = get_eom_dates(panel, start, end)
    target_at = {}
    for d in eom:
        try: w = target_fn(panel, d)
        except Exception: continue
        future = panel.loc[d:].index
        if len(future) >= 2: target_at[future[1]] = w
    daily_ret = panel.pct_change()
    eq = 1.0
    holdings = {}
    nav = []
    for d in panel.loc[start:end].index:
        if holdings:
            r = sum(w*daily_ret.loc[d,t] for t,w in holdings.items()
                    if t in daily_ret.columns and pd.notna(daily_ret.loc[d,t]))
            eq *= (1 + r)
        if d in target_at:
            new_w = target_at[d]
            old_w = holdings.copy()
            all_t = set(old_w.keys()) | set(new_w.keys())
            to = sum(abs(new_w.get(t,0) - old_w.get(t,0)) for t in all_t)
            eq *= (1 - to * cost_bps / 10000.0)
            holdings = new_w
        nav.append((d, eq))
    df = pd.DataFrame(nav, columns=["date","equity"]).set_index("date")
    df["daily_ret"] = df["equity"].pct_change()
    return df


def deflated_sharpe(point_sh_annual, n_obs_daily, n_trials):
    sr = point_sh_annual / np.sqrt(252)
    var_sr = (1 + sr ** 2 / 2) / (n_obs_daily - 1)  # sk=0, kt=3 -> simplified
    sr_std = np.sqrt(var_sr)
    e_gamma = 0.5772
    if n_trials < 2: e_max_std = 0.0
    else:
        e_max_std = (np.sqrt(2*np.log(n_trials)) - (e_gamma + np.log(np.log(n_trials)))/np.sqrt(2*np.log(n_trials)))
    sr_threshold = e_max_std * sr_std
    z = (sr - sr_threshold) / sr_std
    return float(norm.cdf(z))


def ulcer_index(eq_s):
    cummax = eq_s.cummax()
    dd = (eq_s / cummax - 1) * 100
    return float(np.sqrt((dd ** 2).mean()))


def upi_martin(eq_s):
    n_y = len(eq_s.pct_change().dropna()) / 252.0
    cagr = (eq_s.iloc[-1] / eq_s.iloc[0]) ** (1/n_y) - 1
    ulcer = ulcer_index(eq_s)
    return (cagr * 100) / ulcer if ulcer > 0 else np.nan


def pain_index(eq_s):
    cummax = eq_s.cummax()
    dd = (eq_s / cummax - 1) * 100
    return float(-dd.mean())


def all_metrics(eq):
    r = eq["daily_ret"].dropna()
    if r.empty: return {}
    eq_s = eq["equity"]
    n_y = len(r) / 252.0
    cagr = eq_s.iloc[-1] ** (1/n_y) - 1
    vol = r.std() * np.sqrt(252)
    sh = (r.mean()*252) / vol if vol > 0 else np.nan
    dd = (eq_s / eq_s.cummax() - 1).min()
    sortino_dn = r[r < 0].std() * np.sqrt(252) if len(r[r<0]) > 1 else np.nan
    sortino = (r.mean()*252) / sortino_dn if sortino_dn and sortino_dn > 0 else np.nan
    calmar = cagr / abs(dd) if dd < 0 else np.nan
    return dict(years=round(n_y,1), cagr=cagr, vol=vol, sharpe=sh,
                sortino=sortino, calmar=calmar, maxdd=dd,
                upi=upi_martin(eq_s), pain=pain_index(eq_s))


def main():
    panel = load_panel(start=pd.Timestamp("1995-01-01"))
    end = panel.index.max()
    hybrid_start = pd.Timestamp("1997-08-31")
    live_start = pd.Timestamp("2008-09-30")

    print("=" * 165)
    print("FCP with HOLD_BUFFER=2z (robust) -- updated PSR + SOTA comparison")
    print("=" * 165)

    # PSR
    print("\n[PSR with HOLD_BUFFER=2z]")
    print("-" * 165)
    for win_label, start in [("Extended 28.7y", hybrid_start), ("Live-only 18y", live_start)]:
        for vt in [True, False]:
            eq = run_fcp_buf(panel, start, end, buf=2.0, vt=vt)
            r = eq["daily_ret"].dropna()
            n_obs = len(r)
            sh = (r.mean() * 252) / (r.std() * np.sqrt(252))
            tag = "VT" if vt else "noVT"
            print(f"  {win_label} FCP-{tag} (buf=2z): Sh={sh:.3f}, n_obs={n_obs}")
            for nt in [50, 100, 250, 500]:
                psr = deflated_sharpe(sh, n_obs, nt)
                survives = "YES" if psr >= 0.95 else "no"
                print(f"    N={nt:>4d}: PSR={psr*100:.1f}% ({survives})")

    # SOTA peer extended metrics (live-only 18y)
    print("\n[SOTA peer comparison with FCP buf=2z (live-only 18y)]")
    print("-" * 165)
    print(f"  {'Strategy':<48s}  {'Sh':>5s}  {'UPI':>5s}  {'Pain':>6s}  {'CAGR':>6s}  {'DD':>7s}  {'Cal':>5s}")
    print("  " + "-" * 100)

    eq_fcp_2z_vt = run_fcp_buf(panel, live_start, end, buf=2.0, vt=True)
    eq_fcp_2z_novt = run_fcp_buf(panel, live_start, end, buf=2.0, vt=False)
    eq_fcp_3z_vt = run_fcp_buf(panel, live_start, end, buf=3.0, vt=True)  # production reference

    for label, eq in [
        ("FCP (buf=3z, VT) PRODUCTION REFERENCE", eq_fcp_3z_vt),
        ("FCP (buf=2z, VT) ROBUST", eq_fcp_2z_vt),
        ("FCP (buf=2z, no VT) ROBUST + simple", eq_fcp_2z_novt),
    ]:
        m = all_metrics(eq)
        print(f"  {label:<48s}  {m['sharpe']:>+.2f}  {m['upi']:>+5.2f}  {m['pain']:>+5.2f}%  "
              f"{m['cagr']*100:>+5.2f}%  {m['maxdd']*100:>+6.2f}%  {m['calmar']:>+5.2f}")

    for label, fn in [
        ("AAA K=5 canonical (HAA-9)", lambda p,d: aaa_canonical(p, d, HAA9, K=5)),
        ("Keller HAA-Balanced", haa_balanced),
        ("Faber GTAA-5", faber_gtaa5),
        ("60/40 SPY/IEF", static_60_40),
        ("PP-IEF static", static_pp_ief),
        ("SPY buy-hold", buyhold_spy),
    ]:
        eq = simulate(panel, live_start, end, fn)
        m = all_metrics(eq)
        print(f"  {label:<48s}  {m['sharpe']:>+.2f}  {m['upi']:>+5.2f}  {m['pain']:>+5.2f}%  "
              f"{m['cagr']*100:>+5.2f}%  {m['maxdd']*100:>+6.2f}%  {m['calmar']:>+5.2f}")

    # Cost stress (live-only 18y, FCP-2z VT vs FCP-3z VT vs PP-IEF)
    print("\n[Cost stress: FCP buf=2z VT vs production buf=3z VT (live-only 18y)]")
    print("-" * 165)
    print(f"  {'Cost RT':>8s} | {'FCP-2z VT':>10s}  {'FCP-3z VT':>10s}  {'PP-IEF':>8s}  {'60/40':>8s}  {'AAA-K5':>8s}")
    for c in [5, 10, 20, 40, 60]:
        eq_2z = run_fcp_buf(panel, live_start, end, buf=2.0, vt=True, cost_bps=c)
        eq_3z = run_fcp_buf(panel, live_start, end, buf=3.0, vt=True, cost_bps=c)
        eq_pp = simulate(panel, live_start, end, static_pp_ief, cost_bps=c)
        eq_60 = simulate(panel, live_start, end, static_60_40, cost_bps=c)
        eq_aaa = simulate(panel, live_start, end, lambda p,d: aaa_canonical(p, d, HAA9, K=5), cost_bps=c)
        sh = lambda eq: (eq['daily_ret'].dropna().mean()*252)/(eq['daily_ret'].dropna().std()*np.sqrt(252))
        print(f"  {c*2:>5d}bps | {sh(eq_2z):>+9.2f}  {sh(eq_3z):>+9.2f}  {sh(eq_pp):>+7.2f}  "
              f"{sh(eq_60):>+7.2f}  {sh(eq_aaa):>+7.2f}")


if __name__ == "__main__":
    main()
