"""
Unified rank-buffer comparison across FCP and AAA on FCP-15 universe.

Buffer mechanisms tested:
  - z-score buffer (FCP current): keep prior member if z(prior) - z(boundary) > -BUFFER_Z
  - rank buffer (MVP-style): keep prior pair/subset if still in top-half by variance
  - rank buffer at asset level: keep prior K members if still in top-(K+slack)
  - no buffer (baseline)

Goal: find which buffer mechanism generalizes best.

Strategies:
  - FCP K=2 pair selection (with various buffers)
  - AAA K=5 and K=7 continuous min-vol (with various buffers)
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
    load_panel, sig_13612W, RISKY_UNIVERSE, SAFE_POOL, CANARY_ASSETS,
    DEFAULT_CASH, faber_sma_xs, min_vol_pair, best_safe as fcp_best_safe,
    run_fcp_backtest, TOP_K_CANDIDATES, CORR_LOOKBACK_DAYS,
)

LB = 252
COST_BPS_SIDE = 10
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


# ============================================================
# FCP variants with different buffer mechanisms
# ============================================================
def make_fcp_buffer(buffer_kind="zscore_3"):
    """FCP K=2 pair selection with various buffer mechanisms.
    All use canary + Faber-z + pair-min-vol from the original FCP design.
    buffer_kind:
      'none': no buffer
      'zscore_3': original 3z buffer (FCP production)
      'zscore_1': 1z (lighter)
      'rank_pair_half': MVP-style top-half pair rank buffer
      'rank_asset_K+3': keep prior K members if in top-K+3 by z-score
    """
    state = {"prev_pair": None}

    def strat(panel, sig_d):
        monthly = panel.loc[:sig_d].resample("ME").last()
        safe = fcp_best_safe(monthly, sig_d, SAFE_POOL)
        if not canary_pass(panel, sig_d):
            state["prev_pair"] = None
            return {safe: 1.0}

        sma_z = faber_sma_xs(monthly[[u for u in RISKY_UNIVERSE if u in monthly.columns]])
        z_panel = sma_z.dropna()
        if z_panel.empty:
            return {safe: 1.0}
        positive = z_panel[z_panel > 0].sort_values(ascending=False)
        if len(positive) < 2:
            return {safe: 1.0}

        top_k = positive.head(TOP_K_CANDIDATES).index.tolist()

        # Apply asset-level z-score buffer: bring back prior pair members if their z is within buffer of cutoff
        if buffer_kind.startswith("zscore"):
            buf_z = float(buffer_kind.split("_")[1])
            prev = state["prev_pair"]
            if prev:
                cutoff_z = positive.iloc[TOP_K_CANDIDATES - 1] if len(positive) >= TOP_K_CANDIDATES else -np.inf
                kept = [p for p in prev if p in z_panel and z_panel[p] >= cutoff_z - buf_z]
                cands = list(set(top_k) | set(kept))
            else:
                cands = top_k
        elif buffer_kind == "rank_asset_K+3":
            # Keep prior members if still in top-K+3
            extended = positive.head(TOP_K_CANDIDATES + 3).index.tolist()
            prev = state["prev_pair"]
            if prev:
                kept = [p for p in prev if p in extended]
                cands = list(set(top_k) | set(kept))
            else:
                cands = top_k
        else:
            cands = top_k

        if len(cands) < 2:
            return {safe: 1.0}

        ranked_pairs = rank_pairs(panel, sig_d, cands, CORR_LOOKBACK_DAYS)
        if not ranked_pairs:
            return {safe: 1.0}

        chosen = ranked_pairs[0][0]

        # Apply pair-level rank buffer: keep prior pair if still in top-half
        if buffer_kind == "rank_pair_half":
            prev = state["prev_pair"]
            if prev is not None and all(m in cands for m in prev):
                n = len(ranked_pairs)
                buf_k = max(1, ceil(n / 2))
                if frozenset(prev) in {p for p, _ in ranked_pairs[:buf_k]}:
                    chosen = frozenset(prev)

        a, b = list(chosen)
        state["prev_pair"] = (a, b)
        return {a: 0.5, b: 0.5}

    return strat


# ============================================================
# AAA variants with different buffer mechanisms
# ============================================================
def make_aaa_buffer(K=7, buffer_kind="none", apply_canary=False, signal_kind="6mo"):
    """AAA K=K with optional buffer mechanism + optional canary.
    buffer_kind:
      'none'
      'rank_asset_K+3': keep prior K members if still in top-K+3 by momentum
    """
    state = {"prev_top_k": None}

    def strat(panel, sig_d):
        monthly = panel.loc[:sig_d].resample("ME").last()
        bs = best_safe_aaa(monthly)

        if apply_canary and not canary_pass(panel, sig_d):
            state["prev_top_k"] = None
            return {bs: 1.0}

        avail = dynamic_avail(panel, sig_d, RISKY_UNIVERSE, daily_lb=126)
        if signal_kind == "6mo":
            moms = {u: mom_6mo(panel, sig_d, u) for u in avail}
        else:
            moms = {u: sig_13612W(monthly[u]) for u in avail}
        moms = {k: v for k, v in moms.items() if pd.notna(v) and v > 0}
        if len(moms) < 2:
            state["prev_top_k"] = None
            return {bs: 1.0}

        ranked = sorted(moms.items(), key=lambda kv: kv[1], reverse=True)

        if buffer_kind == "rank_asset_K+3" and state["prev_top_k"]:
            # Build top-K, then check if prior K members are in top-(K+3)
            top_k_candidates = [u for u, _ in ranked[:K]]
            extended = [u for u, _ in ranked[:K+3]]
            kept_priors = [p for p in state["prev_top_k"] if p in extended and p not in top_k_candidates]
            # Add kept priors in place of weakest top_k members
            for kept in kept_priors:
                # Remove weakest non-prior asset to make room
                for i in range(len(top_k_candidates) - 1, -1, -1):
                    if top_k_candidates[i] not in state["prev_top_k"]:
                        top_k_candidates[i] = kept
                        break
            selected = list(dict.fromkeys(top_k_candidates))[:K]
        else:
            selected = [u for u, _ in ranked[:K]]

        if len(selected) < 2:
            state["prev_top_k"] = None
            return {bs: 1.0}

        # Min-vol QP weights
        rets_corr = panel.loc[:sig_d, selected].iloc[-126:].pct_change().dropna()
        rets_vol = panel.loc[:sig_d, selected].iloc[-20:].pct_change().dropna()
        if len(rets_corr) < 63 or len(rets_vol) < 10:
            return {bs: 1.0}
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
        weights = {selected[i]: float(w[i]) for i in range(n) if w[i] > 1e-4}
        state["prev_top_k"] = set(selected)
        return weights

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
    print("UNIFIED RANK BUFFER COMPARISON across FCP-K2 and AAA on FCP-15 universe")
    print("=" * 165)

    for win_label, start in [
        ("Extended 28.7y", hybrid_start),
        ("Live-only 18y", live_start),
    ]:
        print()
        print("=" * 165)
        print(f">>> {win_label}")
        print("=" * 165)

        # Baseline: FCP production
        print("\n[FCP K=2 + canary, buffer mechanism sweep]")
        print("-" * 165)
        # Production (3z buffer)
        daily_ret_prod, _ = run_fcp_backtest(panel, start, end, apply_vol_target=False)
        eq_prod = (1 + daily_ret_prod).cumprod()
        df_prod = pd.DataFrame({"equity": eq_prod, "daily_ret": daily_ret_prod})
        print(fmt("FCP production (3z hold buffer)", metrics(df_prod), np.array([0])))

        for bk in ["none", "zscore_1", "zscore_3", "rank_pair_half", "rank_asset_K+3"]:
            eq, to = simulate(panel, start, end, make_fcp_buffer(buffer_kind=bk))
            m = metrics(eq)
            print(fmt(f"FCP K=2 + {bk:>20s} buffer", m, to))

        print("\n[AAA K=7, buffer mechanism sweep]")
        print("-" * 165)
        for bk in ["none", "rank_asset_K+3"]:
            for canary in [False, True]:
                cl = "+canary" if canary else "no canary"
                eq, to = simulate(panel, start, end, make_aaa_buffer(K=7, buffer_kind=bk, apply_canary=canary))
                m = metrics(eq)
                print(fmt(f"AAA K=7 {cl}, {bk:>16s} buffer", m, to))

        print("\n[AAA K=5, buffer mechanism sweep]")
        print("-" * 165)
        for bk in ["none", "rank_asset_K+3"]:
            for canary in [False, True]:
                cl = "+canary" if canary else "no canary"
                eq, to = simulate(panel, start, end, make_aaa_buffer(K=5, buffer_kind=bk, apply_canary=canary))
                m = metrics(eq)
                print(fmt(f"AAA K=5 {cl}, {bk:>16s} buffer", m, to))


if __name__ == "__main__":
    main()
