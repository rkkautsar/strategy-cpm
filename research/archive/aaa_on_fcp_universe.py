"""
Apply AAA engine (top-K by momentum + min-vol QP) to FCP-15 universe.

FCP-15 universe (from strategy_fcp/fcp_live.py):
  AGGR_FACTORS: QQQ, IGM, SPMO, XLE, XRT, COWZ, AVUV, VBR, SPHQ, XMMO, XMHQ
  INTERNATIONAL: VEA, VWO
  DIVERSIFIERS: GLD, TLT

Total: 15 assets. Heavy US factor tilt vs HAA-9's broad asset-class set.

Tests:
  A. AAA K = 3, 5, 7, 10 with canonical (126d corr * 20d vol) cov
  B. Same Ks with naive 20d cov
  C. 6mo vs 13612W momentum signal
  D. With and without best-safe defensive fallback (when fewer than K positive)
  E. Compare to FCP standalone (current production baseline)
  F. Compare to AAA-K=5 on HAA-9 reference

Cost: 20bps RT.
Window: 1997-08 to 2026-05 (28.7y, with proxies pre-2008).
"""
from __future__ import annotations
import sys
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from strategy_fcp.fcp_live import (
    load_panel, sig_13612W, RISKY_UNIVERSE, AGGR_FACTORS, INTERNATIONAL,
    DIVERSIFIERS, SAFE_POOL, DEFAULT_CASH,
)

LB = 252
COST_BPS_SIDE = 10
HAA9 = ["SPY", "QQQ", "IWM", "VEA", "VWO", "VNQ", "DBC", "GLD", "TLT"]
SAFE_POOL_AAA = ["SHV", "IEF"]

INCEPTION = {
    "SPY": "1993-01-29", "QQQ": "1999-03-10", "IWM": "2000-05-22",
    "VEA": "2007-07-20", "VWO": "2005-03-04", "VNQ": "2004-09-23",
    "DBC": "2006-02-03", "GLD": "2004-11-18", "TLT": "2002-07-22",
    "SHV": "2007-01-05", "IEF": "2002-07-22",
    # FCP-specific
    "IGM": "2001-03-13", "SPMO": "2015-10-09", "XLE": "1998-12-22",
    "XRT": "2006-06-22", "COWZ": "2016-12-19", "AVUV": "2019-09-25",
    "VBR": "2004-01-30", "SPHQ": "2005-12-09", "XMMO": "2005-03-10",
    "XMHQ": "2005-12-09",
}


def get_eom_dates(panel, start, end):
    idx = panel.loc[start:end].index
    return list(pd.Series(idx).groupby(idx.to_period("M")).last())


def best_safe(monthly, safe_pool=SAFE_POOL_AAA):
    avail = [s for s in safe_pool if s in monthly.columns and pd.notna(monthly[s].iloc[-1])]
    if not avail: return DEFAULT_CASH
    sc = {s: sig_13612W(monthly[s]) for s in avail}
    sc = {k: v for k, v in sc.items() if pd.notna(v)}
    return max(sc, key=sc.get) if sc else avail[0]


def dynamic_avail(panel, sig_d, universe, daily_lb=252, live_only=False):
    monthly = panel.loc[:sig_d].resample("ME").last()
    out = []
    for u in universe:
        if u not in panel.columns:
            continue
        m = monthly[u].dropna() if u in monthly.columns else pd.Series(dtype=float)
        d = panel[u].loc[:sig_d].dropna()
        if len(m) < 13 or len(d) < daily_lb:
            continue
        if live_only and u in INCEPTION:
            if sig_d < pd.Timestamp(INCEPTION[u]):
                continue
        out.append(u)
    return out


def mom_6mo(panel, sig_d, asset):
    p = panel[asset].loc[:sig_d].dropna()
    if len(p) < 127:
        return np.nan
    return p.iloc[-1] / p.iloc[-127] - 1


def aaa_target(panel, sig_d, universe, K=5, signal_kind="6mo",
               cov_method="canonical", corr_lookback=126, vol_lookback=20,
               defensive=True, safe_pool=SAFE_POOL_AAA, live_only=False):
    """AAA engine on arbitrary universe.

    cov_method: 'canonical' (corr_lookback corr x vol_lookback vol) or 'naive' (pure vol_lookback cov)
    defensive: if True and fewer than K positive momentum, fill with best-safe; otherwise use whatever positive
    """
    monthly = panel.loc[:sig_d].resample("ME").last()
    bs = best_safe(monthly, safe_pool)
    daily_lb = max(252, corr_lookback if cov_method == "canonical" else vol_lookback)
    avail = dynamic_avail(panel, sig_d, universe, daily_lb=daily_lb, live_only=live_only)
    if signal_kind == "6mo":
        moms = {u: mom_6mo(panel, sig_d, u) for u in avail}
    else:
        moms = {u: sig_13612W(monthly[u]) for u in avail}
    moms = {k: v for k, v in moms.items() if pd.notna(v)}
    if not moms:
        return {bs: 1.0}

    if defensive:
        # Filter positive momentum first
        positive = {k: v for k, v in moms.items() if v > 0}
        if len(positive) < 2:
            return {bs: 1.0}
        ranked = sorted(positive.items(), key=lambda kv: kv[1], reverse=True)[:K]
    else:
        # Just take top-K regardless of sign
        ranked = sorted(moms.items(), key=lambda kv: kv[1], reverse=True)[:K]
    selected = [u for u, _ in ranked]
    if len(selected) < 2:
        return {bs: 1.0}

    # Build cov matrix
    if cov_method == "canonical":
        rets_corr = panel.loc[:sig_d, selected].iloc[-corr_lookback:].pct_change().dropna()
        rets_vol = panel.loc[:sig_d, selected].iloc[-vol_lookback:].pct_change().dropna()
        if len(rets_corr) < corr_lookback // 2 or len(rets_vol) < vol_lookback // 2:
            return {bs: 1.0}
        corr = rets_corr.corr().values
        vols = rets_vol.std().values
        cov = corr * np.outer(vols, vols)
    else:  # naive pure vol_lookback cov
        sub = panel.loc[:sig_d, selected].iloc[-vol_lookback:].pct_change().dropna()
        if len(sub) < vol_lookback // 2:
            return {bs: 1.0}
        cov = sub.cov().values

    # Long-only constrained min-variance
    n = len(selected)
    cons = ({"type": "eq", "fun": lambda w: w.sum() - 1.0},)
    bnds = [(0.0, 1.0)] * n
    x0 = np.ones(n) / n
    res = minimize(lambda w: w @ cov @ w, x0, method="SLSQP", bounds=bnds,
                   constraints=cons, options={"maxiter": 200, "ftol": 1e-9})
    w = res.x if res.success else x0
    return {selected[i]: float(w[i]) for i in range(n) if w[i] > 1e-4}


# ============================================================
# FCP standalone reference (run separately, not via wrapper)
# ============================================================
def run_fcp_reference(panel, start, end):
    """Use the production run_fcp_backtest directly. Returns same df shape as simulate()."""
    from strategy_fcp.fcp_live import run_fcp_backtest
    daily_ret, _diag = run_fcp_backtest(panel, start, end, apply_vol_target=False)  # disable vol-target for fair comparison
    eq = (1 + daily_ret).cumprod()
    df = pd.DataFrame({"equity": eq, "daily_ret": daily_ret})
    return df


def simulate(panel, start, end, target_fn, cost_bps=COST_BPS_SIDE):
    eom = get_eom_dates(panel, start, end)
    target_at = {}
    for d in eom:
        try:
            w = target_fn(panel, d)
        except Exception as e:
            print(f"  ERR at {d.date()}: {e}")
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
    cagr = eq["equity"].iloc[-1] ** (1 / n_y) - 1
    vol = r.std() * np.sqrt(252)
    sh = (r.mean() * 252) / vol if vol > 0 else np.nan
    dd = (eq["equity"] / eq["equity"].cummax() - 1).min()
    sortino_dn = r[r < 0].std() * np.sqrt(252) if len(r[r < 0]) > 1 else np.nan
    sortino = (r.mean() * 252) / sortino_dn if sortino_dn and sortino_dn > 0 else np.nan
    calmar = cagr / abs(dd) if dd < 0 else np.nan
    return dict(years=round(n_y, 1), cagr=cagr, vol=vol, sharpe=sh,
                sortino=sortino, calmar=calmar, maxdd=dd)


def fmt(label, m, to):
    ann_to = to.mean() * 12 * 100 if len(to) else 0
    return (f"  {label:<54s}  Sh {m['sharpe']:+.3f}  CAGR {m['cagr']*100:+5.2f}%  "
            f"DD {m['maxdd']*100:+6.2f}%  Vol {m['vol']*100:5.2f}%  AnnTO {ann_to:>5.0f}%")


def main():
    panel = load_panel(start=pd.Timestamp("1995-01-01"))
    end = panel.index.max()
    hybrid_start = pd.Timestamp("1997-08-31")
    live_start = pd.Timestamp("2008-09-30")

    print("=" * 165)
    print("AAA ENGINE on FCP-15 universe (US factor + intl + diversifiers)")
    print(f"FCP-15 = {RISKY_UNIVERSE}")
    print("=" * 165)

    # Reference points
    print()
    print(">>> REFERENCE: AAA K=5 canonical on HAA-9 (cleanest AAA from prior work)")
    print("-" * 165)
    eq, to = simulate(panel, hybrid_start, end, lambda p, d: aaa_target(p, d, HAA9, K=5, signal_kind="6mo", cov_method="canonical", corr_lookback=126, vol_lookback=20))
    m = metrics(eq)
    print(fmt("AAA K=5 canonical, HAA-9 (REFERENCE)", m, to))

    print()
    print(">>> REFERENCE: FCP standalone (current production, no vol-target)")
    print("-" * 165)
    eq = run_fcp_reference(panel, hybrid_start, end)
    m_fcp = metrics(eq)
    print(fmt("FCP standalone (production)", m_fcp, np.array([0])))

    # ============= Extended 28.7y AAA on FCP-15 =============
    print()
    print("=" * 165)
    print(">>> Extended 28.7y -- AAA engine on FCP-15 universe")
    print("=" * 165)

    print("\n[A] CANONICAL cov (126d corr x 20d vol), 6mo signal")
    for K in [3, 5, 7, 10, 15]:
        eq, to = simulate(panel, hybrid_start, end, lambda p, d, K=K: aaa_target(p, d, RISKY_UNIVERSE, K=K, signal_kind="6mo", cov_method="canonical"))
        m = metrics(eq)
        print(fmt(f"AAA K={K}, 6mo, canonical cov", m, to))

    print("\n[B] CANONICAL cov, 13612W signal")
    for K in [3, 5, 7, 10, 15]:
        eq, to = simulate(panel, hybrid_start, end, lambda p, d, K=K: aaa_target(p, d, RISKY_UNIVERSE, K=K, signal_kind="13612W", cov_method="canonical"))
        m = metrics(eq)
        print(fmt(f"AAA K={K}, 13612W, canonical cov", m, to))

    print("\n[C] NAIVE 20d cov, 6mo signal")
    for K in [3, 5, 7, 10, 15]:
        eq, to = simulate(panel, hybrid_start, end, lambda p, d, K=K: aaa_target(p, d, RISKY_UNIVERSE, K=K, signal_kind="6mo", cov_method="naive", vol_lookback=20))
        m = metrics(eq)
        print(fmt(f"AAA K={K}, 6mo, naive 20d cov", m, to))

    print("\n[D] CANONICAL cov, longer vol lookback (60d)")
    for K in [5, 7, 10]:
        eq, to = simulate(panel, hybrid_start, end, lambda p, d, K=K: aaa_target(p, d, RISKY_UNIVERSE, K=K, signal_kind="6mo", cov_method="canonical", vol_lookback=60))
        m = metrics(eq)
        print(fmt(f"AAA K={K}, 6mo, canonical cov + 60d vol", m, to))

    # ============= Live-only 18y =============
    print()
    print("=" * 165)
    print(">>> Live-only 18y -- AAA engine on FCP-15 universe (post-2008-09)")
    print("=" * 165)

    print("\n[A] CANONICAL cov, 6mo signal")
    for K in [3, 5, 7, 10, 15]:
        eq, to = simulate(panel, live_start, end, lambda p, d, K=K: aaa_target(p, d, RISKY_UNIVERSE, K=K, signal_kind="6mo", cov_method="canonical", live_only=True))
        m = metrics(eq)
        print(fmt(f"AAA K={K}, 6mo, canonical cov", m, to))

    print("\n[B] CANONICAL cov, 13612W signal")
    for K in [3, 5, 7, 10, 15]:
        eq, to = simulate(panel, live_start, end, lambda p, d, K=K: aaa_target(p, d, RISKY_UNIVERSE, K=K, signal_kind="13612W", cov_method="canonical", live_only=True))
        m = metrics(eq)
        print(fmt(f"AAA K={K}, 13612W, canonical cov", m, to))

    # FCP reference for live-only
    eq = run_fcp_reference(panel, live_start, end)
    m_fcp_live = metrics(eq)
    print(fmt("FCP standalone (production) [REFERENCE]", m_fcp_live, np.array([0])))

    # AAA-K=5 HAA-9 reference live
    eq, to = simulate(panel, live_start, end, lambda p, d: aaa_target(p, d, HAA9, K=5, signal_kind="6mo", cov_method="canonical", live_only=True))
    m_aaa_haa9_live = metrics(eq)
    print(fmt("AAA K=5 canonical, HAA-9 [REFERENCE]", m_aaa_haa9_live, to))


if __name__ == "__main__":
    main()
