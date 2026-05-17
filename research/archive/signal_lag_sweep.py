"""
Signal lag sweep for FCP and AAA.

Hypothesis: FCP's hold buffer works because momentum signals on the FCP-15
factor universe are sticky (factor regimes persist multi-month). A 1-2 month
signal lag might capture the same effect more cleanly: use last month's
signal to make today's allocation.

Tests:
  - lag=0: signal at sig_d, execute at sig_d+1 (production timing)
  - lag=1: signal at sig_d-1mo, execute at sig_d+1
  - lag=2: signal at sig_d-2mo
  - lag=3: signal at sig_d-3mo

Strategies:
  - MVP K=2 on FCP-15 universe
  - MVP K=2 on HAA-9 universe (control)
  - AAA K=5 on FCP-15 universe
  - AAA K=5 on HAA-9 universe (control)
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
    load_panel, sig_13612W, RISKY_UNIVERSE, SAFE_POOL,
    DEFAULT_CASH,
)

LB = 252
COST_BPS_SIDE = 10
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
        if u not in panel.columns:
            continue
        m = monthly[u].dropna() if u in monthly.columns else pd.Series(dtype=float)
        d = panel[u].loc[:sig_d].dropna()
        if len(m) < 13 or len(d) < daily_lb:
            continue
        out.append(u)
    return out


def lagged_signal_date(panel, current_eom, lag_months):
    """Return EOM date `lag_months` months before current_eom, snapped to actual trading date."""
    if lag_months == 0:
        return current_eom
    target = current_eom - pd.DateOffset(months=lag_months)
    # Find nearest EOM <= target
    idx = panel.loc[:target].index
    if len(idx) == 0:
        return None
    # Get last EOM
    last_eom = pd.Series(idx).groupby(idx.to_period("M")).last().iloc[-1]
    return last_eom


def mom_6mo(panel, sig_d, asset):
    p = panel[asset].loc[:sig_d].dropna()
    if len(p) < 127: return np.nan
    return p.iloc[-1] / p.iloc[-127] - 1


def rank_pairs(panel, sig_d, candidates, lookback=LB):
    if len(candidates) < 2: return []
    sub = panel.loc[:sig_d, candidates].iloc[-lookback:].pct_change().dropna()
    if len(sub) < lookback // 2: return []
    cov = sub.cov()
    pairs = []
    for a, b in combinations(candidates, 2):
        v = 0.25*cov.loc[a,a] + 0.25*cov.loc[b,b] + 0.5*cov.loc[a,b]
        if pd.notna(v): pairs.append((frozenset([a,b]), v))
    pairs.sort(key=lambda x: x[1])
    return pairs


def make_mvp_lag(universe=HAA9, lag_months=0, rank_buffer=False):
    """MVP K=2 + 50/50 with optional signal lag."""
    state = {"prev_pair": None}
    def strat(panel, sig_d):
        signal_d = lagged_signal_date(panel, sig_d, lag_months)
        if signal_d is None or signal_d < pd.Timestamp("1996-09-01"):
            return {DEFAULT_CASH: 1.0}

        monthly = panel.loc[:signal_d].resample("ME").last()
        bs = best_safe_aaa(monthly)
        avail = dynamic_avail(panel, signal_d, universe)
        scs = {u: sig_13612W(monthly[u]) for u in avail}
        cands = [u for u, s in scs.items() if pd.notna(s) and s > 0]
        if len(cands) < 2:
            state["prev_pair"] = None
            return {bs: 1.0}
        ranked = rank_pairs(panel, signal_d, cands, LB)
        if not ranked:
            state["prev_pair"] = None
            return {bs: 1.0}
        chosen = ranked[0][0]
        if rank_buffer and state["prev_pair"] is not None and all(m in cands for m in state["prev_pair"]):
            n = len(ranked)
            buf_k = max(1, ceil(n / 2))
            if state["prev_pair"] in {p for p, _ in ranked[:buf_k]}:
                chosen = state["prev_pair"]
        state["prev_pair"] = chosen
        a, b = list(chosen)
        return {a: 0.5, b: 0.5}
    return strat


def make_aaa_lag(universe=HAA9, K=5, lag_months=0, signal_kind="6mo"):
    def strat(panel, sig_d):
        signal_d = lagged_signal_date(panel, sig_d, lag_months)
        if signal_d is None or signal_d < pd.Timestamp("1996-09-01"):
            return {DEFAULT_CASH: 1.0}

        monthly = panel.loc[:signal_d].resample("ME").last()
        bs = best_safe_aaa(monthly)
        avail = dynamic_avail(panel, signal_d, universe, daily_lb=126)
        if signal_kind == "6mo":
            moms = {u: mom_6mo(panel, signal_d, u) for u in avail}
        else:
            moms = {u: sig_13612W(monthly[u]) for u in avail}
        moms = {k: v for k, v in moms.items() if pd.notna(v) and v > 0}
        if len(moms) < 2: return {bs: 1.0}
        ranked = sorted(moms.items(), key=lambda kv: kv[1], reverse=True)[:K]
        selected = [u for u, _ in ranked]
        if len(selected) < 2: return {bs: 1.0}
        rets_corr = panel.loc[:signal_d, selected].iloc[-126:].pct_change().dropna()
        rets_vol = panel.loc[:signal_d, selected].iloc[-20:].pct_change().dropna()
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
    return strat


def simulate(panel, start, end, target_fn, cost_bps=COST_BPS_SIDE):
    eom = get_eom_dates(panel, start, end)
    target_at = {}
    for d in eom:
        try:
            w = target_fn(panel, d)
        except Exception:
            continue
        future = panel.loc[d:].index
        if len(future) >= 2:
            target_at[future[1]] = w
    daily_ret = panel.pct_change()
    eq = 1.0
    holdings = {}
    nav = []
    turnovers = []
    for d in panel.loc[start:end].index:
        if holdings:
            r = sum(w * daily_ret.loc[d, t] for t, w in holdings.items()
                    if t in daily_ret.columns and pd.notna(daily_ret.loc[d, t]))
            eq *= (1 + r)
        if d in target_at:
            new_w = target_at[d]
            old_w = holdings.copy()
            all_t = set(old_w.keys()) | set(new_w.keys())
            to = sum(abs(new_w.get(t, 0) - old_w.get(t, 0)) for t in all_t)
            turnovers.append(to)
            eq *= (1 - to * cost_bps / 10000.0)
            holdings = new_w
        nav.append((d, eq))
    df = pd.DataFrame(nav, columns=["date", "equity"]).set_index("date")
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


def fmt(label, m, to):
    ann_to = to.mean()*12*100 if len(to) else 0
    return (f"  {label:<48s}  Sh {m['sharpe']:+.3f}  CAGR {m['cagr']*100:+5.2f}%  "
            f"DD {m['maxdd']*100:+6.2f}%  Vol {m['vol']*100:5.2f}%  AnnTO {ann_to:>5.0f}%")


def main():
    panel = load_panel(start=pd.Timestamp("1995-01-01"))
    end = panel.index.max()
    hybrid_start = pd.Timestamp("1997-08-31")
    live_start = pd.Timestamp("2008-09-30")

    print("=" * 165)
    print("SIGNAL LAG SWEEP: does using stale signals (1-3mo old) help?")
    print("Hypothesis: FCP universe has sticky momentum. Lag could substitute for hold buffer.")
    print("=" * 165)

    for win_label, start in [
        ("Extended 28.7y", hybrid_start),
        ("Live-only 18y", live_start),
    ]:
        print()
        print("=" * 165)
        print(f">>> {win_label}")
        print("=" * 165)

        # MVP K=2 on FCP-15
        print("\n[MVP K=2 (rank buffer) on FCP-15]")
        for lag in [0, 1, 2, 3]:
            eq, to = simulate(panel, start, end, make_mvp_lag(universe=RISKY_UNIVERSE, lag_months=lag, rank_buffer=True))
            m = metrics(eq)
            print(fmt(f"MVP FCP-15 lag={lag}mo", m, to))

        # MVP K=2 on HAA-9 (control)
        print("\n[MVP K=2 (rank buffer) on HAA-9 -- CONTROL]")
        for lag in [0, 1, 2, 3]:
            eq, to = simulate(panel, start, end, make_mvp_lag(universe=HAA9, lag_months=lag, rank_buffer=True))
            m = metrics(eq)
            print(fmt(f"MVP HAA-9 lag={lag}mo", m, to))

        # AAA K=5 on FCP-15
        print("\n[AAA K=5, 6mo signal on FCP-15]")
        for lag in [0, 1, 2, 3]:
            eq, to = simulate(panel, start, end, make_aaa_lag(universe=RISKY_UNIVERSE, K=5, lag_months=lag, signal_kind="6mo"))
            m = metrics(eq)
            print(fmt(f"AAA K=5 FCP-15 lag={lag}mo", m, to))

        # AAA K=5 on HAA-9 (control)
        print("\n[AAA K=5, 6mo signal on HAA-9 -- CONTROL]")
        for lag in [0, 1, 2, 3]:
            eq, to = simulate(panel, start, end, make_aaa_lag(universe=HAA9, K=5, lag_months=lag, signal_kind="6mo"))
            m = metrics(eq)
            print(fmt(f"AAA K=5 HAA-9 lag={lag}mo", m, to))

        # AAA K=7 on FCP-15
        print("\n[AAA K=7, 6mo signal on FCP-15]")
        for lag in [0, 1, 2, 3]:
            eq, to = simulate(panel, start, end, make_aaa_lag(universe=RISKY_UNIVERSE, K=7, lag_months=lag, signal_kind="6mo"))
            m = metrics(eq)
            print(fmt(f"AAA K=7 FCP-15 lag={lag}mo", m, to))


if __name__ == "__main__":
    main()
