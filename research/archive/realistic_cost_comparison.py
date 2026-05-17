"""
Realistic-cost comparison: FCP vs AAA vs SOTA peers across cost levels.

Tests cost progression: 5bps -> 10bps -> 20bps (default) -> 40bps -> 60bps
plus optional tax-drag estimate (1.5% annual return haircut for short-term gains).

Key question: at what cost level does each strategy lose its edge?
"""
from __future__ import annotations
import sys
from itertools import combinations
from math import ceil
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from strategy_fcp.fcp_live import (
    load_panel, sig_13612W, RISKY_UNIVERSE as FCP15, SAFE_POOL, CANARY_ASSETS,
    DEFAULT_CASH, faber_sma_xs, min_vol_pair, best_safe as fcp_best_safe,
    run_fcp_backtest,
)

LB = 252
HAA9 = ["SPY", "QQQ", "IWM", "VEA", "VWO", "VNQ", "DBC", "GLD", "TLT"]
SAFE_POOL_AAA = ["SHV", "IEF"]


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


def canary_pass(panel, sig_d):
    monthly = panel.loc[:sig_d].resample("ME").last()
    scs = []
    for c in CANARY_ASSETS:
        if c not in monthly.columns: continue
        s = sig_13612W(monthly[c])
        if pd.notna(s): scs.append(s)
    if not scs: return False
    n_pos = sum(1 for s in scs if s > 0)
    return n_pos > len(scs) // 2


def mom_6mo(panel, sig_d, asset):
    p = panel[asset].loc[:sig_d].dropna()
    if len(p) < 127: return np.nan
    return p.iloc[-1] / p.iloc[-127] - 1


def aaa_canonical(panel, sig_d, universe, K=5, apply_canary=False):
    monthly = panel.loc[:sig_d].resample("ME").last()
    bs = best_safe_aaa(monthly)
    if apply_canary and not canary_pass(panel, sig_d):
        return {bs: 1.0}
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


def simulate(panel, start, end, target_fn, cost_bps_side=10):
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
    turnovers = []
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
            turnovers.append(to)
            eq *= (1 - to * cost_bps_side / 10000.0)
            holdings = new_w
        nav.append((d, eq))
    df = pd.DataFrame(nav, columns=["date","equity"]).set_index("date")
    df["daily_ret"] = df["equity"].pct_change()
    return df, np.array(turnovers)


def metrics(eq):
    r = eq["daily_ret"].dropna()
    if r.empty: return {}
    n_y = len(r) / 252.0
    cagr = eq["equity"].iloc[-1] ** (1/n_y) - 1
    vol = r.std() * np.sqrt(252)
    sh = (r.mean()*252) / vol if vol > 0 else np.nan
    dd = (eq["equity"] / eq["equity"].cummax() - 1).min()
    return dict(cagr=cagr, vol=vol, sharpe=sh, maxdd=dd)


def apply_tax_drag(eq, annual_drag=0.015):
    """Subtract annual tax drag from daily returns. Approximates short-term cap gains."""
    daily_drag = (1 + annual_drag) ** (1/252) - 1
    new_daily = eq["daily_ret"] - daily_drag
    new_eq = (1 + new_daily.fillna(0)).cumprod()
    return pd.DataFrame({"equity": new_eq, "daily_ret": new_daily})


def run_fcp_baseline(panel, start, end, vol_target=False, cost_bps_side=10):
    daily_ret, _ = run_fcp_backtest(panel, start, end, apply_vol_target=vol_target,
                                     cost_bps=cost_bps_side)
    eq = (1 + daily_ret).cumprod()
    return pd.DataFrame({"equity": eq, "daily_ret": daily_ret})


def main():
    panel = load_panel(start=pd.Timestamp("1995-01-01"))
    end = panel.index.max()
    hybrid_start = pd.Timestamp("1997-08-31")
    live_start = pd.Timestamp("2008-09-30")

    print("=" * 175)
    print("REALISTIC COST COMPARISON: how do strategies hold up at various cost levels?")
    print("Cost ranges: 5bps RT (institutional) -> 10bps -> 20bps (default) -> 40bps (retail) -> 60bps (taxable retail)")
    print("=" * 175)

    cost_levels = [2.5, 5, 10, 20, 30]  # per side; RT = 2x

    for win_label, start in [("Extended 28.7y", hybrid_start), ("Live-only 18y", live_start)]:
        print(f"\n>>> {win_label}")
        print("-" * 175)
        print(f"  {'Strategy':<48s}  | Sharpe at cost RT (bps):")
        print(f"  {'':<48s}  |  {'5':>5s}  {'10':>5s}  {'20':>5s}  {'40':>5s}  {'60':>5s}")
        print("  " + "-" * 105)

        strategies = [
            ("FCP production (vol-target ON)", lambda c: run_fcp_baseline(panel, start, end, vol_target=True, cost_bps_side=c)),
            ("FCP production (vol-target OFF)", lambda c: run_fcp_baseline(panel, start, end, vol_target=False, cost_bps_side=c)),
            ("AAA K=5 canonical (HAA-9)", lambda c: simulate(panel, start, end, lambda p, d: aaa_canonical(p, d, HAA9, K=5), cost_bps_side=c)[0]),
            ("AAA K=5 +canary (FCP-15)", lambda c: simulate(panel, start, end, lambda p, d: aaa_canonical(p, d, FCP15, K=5, apply_canary=True), cost_bps_side=c)[0]),
            ("Keller HAA-Balanced", lambda c: simulate(panel, start, end, haa_balanced, cost_bps_side=c)[0]),
            ("Faber GTAA-5", lambda c: simulate(panel, start, end, faber_gtaa5, cost_bps_side=c)[0]),
            ("60/40 SPY/IEF", lambda c: simulate(panel, start, end, static_60_40, cost_bps_side=c)[0]),
            ("PP-IEF static", lambda c: simulate(panel, start, end, static_pp_ief, cost_bps_side=c)[0]),
            ("SPY buy-hold", lambda c: simulate(panel, start, end, buyhold_spy, cost_bps_side=c)[0]),
        ]

        for label, fn in strategies:
            shs = []
            for c in cost_levels:
                eq = fn(c)
                m = metrics(eq)
                shs.append(m["sharpe"])
            print(f"  {label:<48s}  |  " + "  ".join(f"{s:>+.2f}" for s in shs))

    # ============================================================
    # Tax drag scenario (for taxable accounts)
    # ============================================================
    print()
    print("=" * 175)
    print("TAX-ADJUSTED Sharpe (live-only 18y, 20bps RT cost + 1.5% annual tax drag for high-turnover strategies)")
    print("=" * 175)
    print(f"\n  {'Strategy':<48s}  Pre-tax Sh  Post-tax Sh  Δ")
    print("  " + "-" * 90)

    for label, fn in [
        ("FCP production (vol-target ON)", lambda: run_fcp_baseline(panel, live_start, end, vol_target=True, cost_bps_side=10)),
        ("FCP production (vol-target OFF)", lambda: run_fcp_baseline(panel, live_start, end, vol_target=False, cost_bps_side=10)),
        ("AAA K=5 canonical (HAA-9)", lambda: simulate(panel, live_start, end, lambda p, d: aaa_canonical(p, d, HAA9, K=5), cost_bps_side=10)[0]),
        ("AAA K=5 +canary (FCP-15)", lambda: simulate(panel, live_start, end, lambda p, d: aaa_canonical(p, d, FCP15, K=5, apply_canary=True), cost_bps_side=10)[0]),
        ("Keller HAA-Balanced", lambda: simulate(panel, live_start, end, haa_balanced, cost_bps_side=10)[0]),
        ("60/40 SPY/IEF", lambda: simulate(panel, live_start, end, static_60_40, cost_bps_side=10)[0]),
        ("PP-IEF static", lambda: simulate(panel, live_start, end, static_pp_ief, cost_bps_side=10)[0]),
        ("SPY buy-hold (long-term cap gains, no tax drag in this model)", lambda: simulate(panel, live_start, end, buyhold_spy, cost_bps_side=10)[0]),
    ]:
        eq_pre = fn()
        m_pre = metrics(eq_pre)
        # SPY buy-hold = no tax drag (long-term capital gains, no realized turnover)
        if "SPY buy-hold" in label or "PP-IEF static" in label or "60/40" in label:
            # Static strategies have minimal realized turnover (just rebalancing); minimal tax drag
            tax = 0.003  # 0.3% drag from rebalancing
        else:
            tax = 0.015  # 1.5% drag for high-turnover TAA
        eq_post = apply_tax_drag(eq_pre, annual_drag=tax)
        m_post = metrics(eq_post)
        delta = m_post["sharpe"] - m_pre["sharpe"]
        print(f"  {label:<48s}  {m_pre['sharpe']:>+.3f}      {m_post['sharpe']:>+.3f}      {delta:>+.3f}  (tax {tax*100:.1f}%)")


if __name__ == "__main__":
    main()
