"""
FCP + AAA-with-canary vs SOTA peers using extended TAA-favorable metrics.

Tests:
  A. AAA K=5 + canary on multiple universes (HAA-9, FCP-15, AAA-10) with extended metrics
  B. FCP production (vol-target on AND off) vs SOTA peers on UPI/Calmar/Pain/Avg36mDD/SWR
  C. Bootstrap Sharpe diff: FCP vs each peer

Metrics: Sharpe, Sortino, Calmar, MaxDD, UPI/Martin, Pain, Avg rolling 36m DD,
         SWR, AnnTO, 95% CI Sharpe.
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
COST_BPS_SIDE = 10
HAA9 = ["SPY", "QQQ", "IWM", "VEA", "VWO", "VNQ", "DBC", "GLD", "TLT"]
AAA10 = ["SPY", "EFA", "EEM", "VNQ", "IEF", "TLT", "DBC", "GLD", "VEA", "VWO"]
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


def canary_pass(panel, sig_d, canary_assets=None):
    monthly = panel.loc[:sig_d].resample("ME").last()
    canary_assets = canary_assets or CANARY_ASSETS
    scs = []
    for c in canary_assets:
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


# ============================================================
# Strategies
# ============================================================
def aaa_canonical(panel, sig_d, universe=HAA9, K=5, apply_canary=False):
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


# ============================================================
# Simulator + metrics
# ============================================================
def simulate(panel, start, end, target_fn, cost_bps=COST_BPS_SIDE):
    eom = get_eom_dates(panel, start, end)
    target_at = {}
    for d in eom:
        try:
            w = target_fn(panel, d)
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
            eq *= (1 - to * cost_bps / 10000.0)
            holdings = new_w
        nav.append((d, eq))
    df = pd.DataFrame(nav, columns=["date","equity"]).set_index("date")
    df["daily_ret"] = df["equity"].pct_change()
    return df, np.array(turnovers)


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


def rolling_36m_dd(eq_s):
    window_days = 36 * 21
    if len(eq_s) < window_days: return np.nan
    rolling_max = eq_s.rolling(window_days, min_periods=1).max()
    rolling_dd = (eq_s / rolling_max - 1) * 100
    worst_in_window = rolling_dd.rolling(window_days).min()
    return float(worst_in_window.mean())


def safe_withdrawal_rate(eq_s):
    daily_returns = eq_s.pct_change().dropna()
    n_years = int(len(daily_returns) / 252)
    if n_years < 5: return np.nan
    annual_returns = []
    for y in range(n_years):
        chunk = daily_returns.iloc[y*252:(y+1)*252]
        if len(chunk) > 0:
            annual_returns.append((1 + chunk).prod() - 1)
    annual_returns = np.array(annual_returns)
    survivors = []
    for w_rate in np.arange(0.02, 0.15, 0.0025):
        capital = 1.0
        survived = True
        for r in annual_returns:
            capital = capital * (1 + r) - 1.0 * w_rate
            if capital <= 0:
                survived = False
                break
        if survived: survivors.append(w_rate)
    return max(survivors) * 100 if survivors else 0.0


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
                upi=upi_martin(eq_s), pain=pain_index(eq_s),
                avg_36m_dd=rolling_36m_dd(eq_s),
                swr=safe_withdrawal_rate(eq_s))


def block_bootstrap_ci(daily, B=3000, block=21, seed=42):
    r = daily.dropna().values
    n = len(r)
    if n < block * 2: return (np.nan, np.nan)
    rng = np.random.default_rng(seed)
    n_blocks = n // block + 1
    starts = rng.integers(0, n - block + 1, size=(B, n_blocks))
    offsets = np.arange(block)
    idx = (starts[:, :, None] + offsets[None, None, :]).reshape(B, -1)[:, :n]
    samples = r[idx]
    m = samples.mean(axis=1) * 252
    s = samples.std(axis=1) * np.sqrt(252)
    sharpes = np.where(s > 0, m / s, 0.0)
    return float(np.percentile(sharpes, 2.5)), float(np.percentile(sharpes, 97.5))


def bootstrap_diff(daily_a, daily_b, B=3000, block=21, seed=42):
    df = pd.concat([daily_a.rename("a"), daily_b.rename("b")], axis=1).dropna()
    a = df["a"].values; b = df["b"].values
    n = len(a)
    if n < block * 2: return (np.nan, np.nan, np.nan, np.nan)
    rng = np.random.default_rng(seed)
    n_blocks = n // block + 1
    starts = rng.integers(0, n - block + 1, size=(B, n_blocks))
    offsets = np.arange(block)
    idx = (starts[:, :, None] + offsets[None, None, :]).reshape(B, -1)[:, :n]
    sa, sb = a[idx], b[idx]
    ma = sa.mean(axis=1)*252; sda = sa.std(axis=1)*np.sqrt(252) + 1e-9
    mb = sb.mean(axis=1)*252; sdb = sb.std(axis=1)*np.sqrt(252) + 1e-9
    diffs = (ma/sda) - (mb/sdb)
    pt_a = (a.mean()*252)/(a.std()*np.sqrt(252))
    pt_b = (b.mean()*252)/(b.std()*np.sqrt(252))
    return pt_a - pt_b, float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5)), float((diffs > 0).mean())


def fmt(label, m, to):
    ann_to = to.mean()*12*100 if len(to) > 1 else 0
    return (f"  {label:<48s}  Sh {m['sharpe']:+.2f}  Cal {m['calmar']:+.2f}  "
            f"UPI {m['upi']:+5.2f}  Pain {m['pain']:+5.2f}%  Avg36m {m['avg_36m_dd']:+6.2f}%  "
            f"SWR {m['swr']:5.2f}%  CAGR {m['cagr']*100:+5.2f}%  DD {m['maxdd']*100:+6.2f}%  TO {ann_to:>4.0f}%")


def run_fcp_baseline(panel, start, end, vol_target=False):
    daily_ret, _ = run_fcp_backtest(panel, start, end, apply_vol_target=vol_target)
    eq = (1 + daily_ret).cumprod()
    return pd.DataFrame({"equity": eq, "daily_ret": daily_ret})


def main():
    panel = load_panel(start=pd.Timestamp("1995-01-01"))
    end = panel.index.max()
    hybrid_start = pd.Timestamp("1997-08-31")
    live_start = pd.Timestamp("2008-09-30")

    # ============================================================
    # PART A: AAA K=5 + canary cross-test on multiple universes
    # ============================================================
    print("=" * 175)
    print("PART A: AAA K=5 (canonical 126d corr x 20d vol cov) WITH SPY+TIP CANARY -- on multiple universes")
    print("Extended metrics on extended 28.7y AND live-only 18y")
    print("=" * 175)

    for win_label, start in [("Extended 28.7y", hybrid_start), ("Live-only 18y", live_start)]:
        print(f"\n>>> {win_label}")
        print("-" * 175)
        for uni_label, uni in [("HAA-9", HAA9), ("FCP-15", FCP15), ("AAA-10", AAA10)]:
            for canary in [False, True]:
                clabel = "+canary" if canary else "no canary"
                eq, to = simulate(panel, start, end, lambda p, d, u=uni, c=canary: aaa_canonical(p, d, u, K=5, apply_canary=c))
                m = all_metrics(eq)
                print(fmt(f"AAA K=5 {clabel} on {uni_label}", m, to))

    # ============================================================
    # PART B: FCP production vs SOTA peers on extended metrics
    # ============================================================
    print()
    print("=" * 175)
    print("PART B: FCP production (vol-target ON and OFF) vs SOTA peers -- extended metrics")
    print("=" * 175)

    for win_label, start in [("Extended 28.7y", hybrid_start), ("Live-only 18y", live_start)]:
        print(f"\n>>> {win_label}")
        print("-" * 175)

        # FCP production
        eq_fcp_vt = run_fcp_baseline(panel, start, end, vol_target=True)
        eq_fcp_novt = run_fcp_baseline(panel, start, end, vol_target=False)
        m_fcp_vt = all_metrics(eq_fcp_vt)
        m_fcp_novt = all_metrics(eq_fcp_novt)
        print(fmt("FCP production (vol-target ON)", m_fcp_vt, np.array([0])))
        print(fmt("FCP production (vol-target OFF)", m_fcp_novt, np.array([0])))

        # Best AAA variant
        eq_aaa_haa9, to_aaa = simulate(panel, start, end, lambda p, d: aaa_canonical(p, d, HAA9, K=5, apply_canary=False))
        m_aaa_haa9 = all_metrics(eq_aaa_haa9)
        print(fmt("AAA K=5 canonical (HAA-9)", m_aaa_haa9, to_aaa))

        eq_aaa_fcp_can, to_aaa_can = simulate(panel, start, end, lambda p, d: aaa_canonical(p, d, FCP15, K=5, apply_canary=True))
        m_aaa_fcp_can = all_metrics(eq_aaa_fcp_can)
        print(fmt("AAA K=5 +canary on FCP-15", m_aaa_fcp_can, to_aaa_can))

        # SOTA peers
        for label, fn in [
            ("Keller HAA-Balanced", haa_balanced),
            ("Faber GTAA-5", faber_gtaa5),
            ("60/40 SPY/IEF", static_60_40),
            ("PP-IEF static", static_pp_ief),
            ("SPY buy-hold", buyhold_spy),
        ]:
            eq, to = simulate(panel, start, end, fn)
            m = all_metrics(eq)
            print(fmt(label, m, to))

    # ============================================================
    # PART C: Bootstrap Sharpe diff: FCP vs each peer (extended 28.7y)
    # ============================================================
    print()
    print("=" * 175)
    print("PART C: Bootstrap Sharpe diff: FCP production (vol-target OFF) vs each peer (extended 28.7y)")
    print("=" * 175)

    fcp_eq = run_fcp_baseline(panel, hybrid_start, end, vol_target=False)
    peers = {
        "AAA K=5 canonical (HAA-9)": simulate(panel, hybrid_start, end, lambda p, d: aaa_canonical(p, d, HAA9, K=5, apply_canary=False))[0],
        "AAA K=5 +canary on FCP-15": simulate(panel, hybrid_start, end, lambda p, d: aaa_canonical(p, d, FCP15, K=5, apply_canary=True))[0],
        "Keller HAA-Balanced":        simulate(panel, hybrid_start, end, haa_balanced)[0],
        "Faber GTAA-5":               simulate(panel, hybrid_start, end, faber_gtaa5)[0],
        "60/40 SPY/IEF":              simulate(panel, hybrid_start, end, static_60_40)[0],
        "PP-IEF static":              simulate(panel, hybrid_start, end, static_pp_ief)[0],
        "SPY buy-hold":               simulate(panel, hybrid_start, end, buyhold_spy)[0],
    }

    print(f"\n  {'Comparison (FCP - peer)':<48s}  point Sharpe diff   95% CI               P(>0)  Sig?")
    print("  " + "-" * 100)
    for label, eq in peers.items():
        pt, lo, hi, p = bootstrap_diff(fcp_eq["daily_ret"], eq["daily_ret"])
        sig = " *" if (lo > 0 or hi < 0) else ""
        print(f"  FCP - {label:<42s}  {pt:>+.3f}        [{lo:>+.3f}, {hi:>+.3f}]  {p*100:>5.0f}%  {sig}")


if __name__ == "__main__":
    main()
