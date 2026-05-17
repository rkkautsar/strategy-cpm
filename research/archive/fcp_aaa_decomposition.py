"""
FCP vs AAA on FCP-15 universe -- component decomposition.

Goal: explain WHY FCP standalone Sharpe 1.15 beats AAA-K=7 Sharpe 0.76
(hybrid) and AAA-K=7 Sharpe 0.97 (live) on the same FCP-15 universe.

FCP components (production):
  1. Universe: FCP-15 (factor-heavy)
  2. Canary: SPY+TIP majority must be 13612W positive
  3. Filter: top-K=7 by Faber 10mo SMA z-score
  4. Hold buffer: keep prior pair if new candidate doesn't beat by 3z
  5. Pair selection: lowest 50/50 portfolio variance from top-K
  6. Weights: equal 50/50

AAA components (canonical):
  1. Universe: AAA-10 (broad asset classes)
  2. No canary
  3. Filter: top-K=5 by 6mo total return
  4. No hold buffer
  5. Selection: continuous min-vol QP weights on top-K
  6. Weights: continuous

DECOMPOSITION TESTS (all on FCP-15 universe):
  D1. FCP full (production baseline)
  D2. FCP - canary (drop SPY+TIP gate, keep pair+buffer+factor)
  D3. FCP - hold buffer (drop 3z stickiness)
  D4. FCP - canary - hold buffer (just pair+factor on FCP-15)
  D5. AAA-K=7 + FCP canary (cross-pollination: AAA engine + FCP risk gate)
  D6. AAA-K=7 + hold buffer at asset level
  D7. AAA-K=7 + canary + hold buffer
  D8. MVP-style (K=2 pair + 50/50 + rank buffer) on FCP-15 (NO canary, NO Faber-z)
  D9. MVP-style + canary on FCP-15

These should isolate which component contributes how much Sharpe.
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
    DEFAULT_CASH, faber_sma_xs, lowest_corr_pair, min_vol_pair, zscore,
    best_safe as fcp_best_safe, compute_target_weights, run_fcp_backtest,
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
    "IGM": "2001-03-13", "SPMO": "2015-10-09", "XLE": "1998-12-22",
    "XRT": "2006-06-22", "COWZ": "2016-12-19", "AVUV": "2019-09-25",
    "VBR": "2004-01-30", "SPHQ": "2005-12-09", "XMMO": "2005-03-10",
    "XMHQ": "2005-12-09",
}


def get_eom_dates(panel, start, end):
    idx = panel.loc[start:end].index
    return list(pd.Series(idx).groupby(idx.to_period("M")).last())


def best_safe_aaa(monthly):
    avail = [s for s in SAFE_POOL_AAA if s in monthly.columns and pd.notna(monthly[s].iloc[-1])]
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


def canary_pass(panel, sig_d, canary_assets=None):
    """SPY+TIP majority must be 13612W positive (FCP convention)."""
    monthly = panel.loc[:sig_d].resample("ME").last()
    canary_assets = canary_assets or CANARY_ASSETS
    scs = []
    for c in canary_assets:
        if c not in monthly.columns: continue
        s = sig_13612W(monthly[c])
        if pd.notna(s):
            scs.append(s)
    if not scs: return False
    n_pos = sum(1 for s in scs if s > 0)
    return n_pos > len(scs) // 2  # majority


def mom_6mo(panel, sig_d, asset):
    p = panel[asset].loc[:sig_d].dropna()
    if len(p) < 127: return np.nan
    return p.iloc[-1] / p.iloc[-127] - 1


# ============================================================
# AAA engine
# ============================================================
def aaa_target(panel, sig_d, universe, K=7, signal_kind="6mo",
               vol_lookback=20, corr_lookback=126, live_only=False,
               apply_canary=False, hold_buffer_z=0.0, prev_top_k=None,
               safe_pool=SAFE_POOL_AAA):
    """AAA-style: top-K by momentum + min-vol QP weights.
    Optional: canary check (drop to safe if canary fails)
    Optional: hold buffer at asset level (z-score on momentum, prev_top_k state)
    """
    monthly = panel.loc[:sig_d].resample("ME").last()
    bs = best_safe_aaa(monthly)

    if apply_canary and not canary_pass(panel, sig_d):
        return {bs: 1.0}, set()

    avail = dynamic_avail(panel, sig_d, universe,
                          daily_lb=max(252, corr_lookback), live_only=live_only)
    if signal_kind == "6mo":
        moms = {u: mom_6mo(panel, sig_d, u) for u in avail}
    else:
        moms = {u: sig_13612W(monthly[u]) for u in avail}
    moms = {k: v for k, v in moms.items() if pd.notna(v) and v > 0}
    if len(moms) < 2:
        return {bs: 1.0}, set()

    # Apply hold buffer at asset level
    ranked = sorted(moms.items(), key=lambda kv: kv[1], reverse=True)
    if hold_buffer_z > 0 and prev_top_k:
        # Compute z-scores
        scores = np.array([s for _, s in ranked])
        if scores.std() > 1e-9:
            zs = (scores - scores.mean()) / scores.std()
            # Build new top-K honoring buffer: prior members stay if their z is within buffer of #K
            new_top = []
            for asset, sc in ranked[:K]:
                new_top.append(asset)
            # For each prior member NOT in new_top but still positive, check if z(member) - z(new[K-1]) > -buffer
            cutoff_idx = K - 1 if K <= len(ranked) else len(ranked) - 1
            cutoff_z = zs[cutoff_idx] if cutoff_idx < len(zs) else -np.inf
            for prior in prev_top_k:
                if prior in moms and prior not in new_top:
                    prior_idx = next((i for i, (a, _) in enumerate(ranked) if a == prior), None)
                    if prior_idx is not None and zs[prior_idx] - cutoff_z > -hold_buffer_z:
                        # Keep prior; bump weakest non-prior out
                        for i in range(len(new_top) - 1, -1, -1):
                            if new_top[i] not in prev_top_k:
                                del new_top[i]
                                break
                        new_top.append(prior)
            ranked = [(a, moms[a]) for a in new_top[:K]]

    selected = [u for u, _ in ranked[:K]]
    if len(selected) < 2:
        return {bs: 1.0}, set()

    rets_corr = panel.loc[:sig_d, selected].iloc[-corr_lookback:].pct_change().dropna()
    rets_vol = panel.loc[:sig_d, selected].iloc[-vol_lookback:].pct_change().dropna()
    if len(rets_corr) < corr_lookback // 2 or len(rets_vol) < vol_lookback // 2:
        return {bs: 1.0}, set()

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
    return weights, set(selected)


def make_aaa_strat(K=7, signal_kind="6mo", apply_canary=False,
                   hold_buffer_z=0.0, live_only=False, universe=None):
    """Stateful AAA strategy with optional canary + hold buffer."""
    universe = universe or RISKY_UNIVERSE
    state = {"prev_top_k": None}

    def strat(panel, sig_d):
        weights, top_k = aaa_target(panel, sig_d, universe, K=K, signal_kind=signal_kind,
                                    apply_canary=apply_canary, hold_buffer_z=hold_buffer_z,
                                    prev_top_k=state["prev_top_k"], live_only=live_only)
        if top_k:
            state["prev_top_k"] = top_k
        else:
            state["prev_top_k"] = None
        return weights
    return strat


# ============================================================
# FCP variants (production-derived)
# ============================================================
def make_fcp_via_compute_target(disable_canary=False, hold_buffer_z=None,
                                custom_weight_fn=None):
    """Wrapper around production compute_target_weights with optional component disable.
    For now, use the production directly (vol-target off via run_fcp_backtest flag).
    To disable canary or change hold_buffer, must edit the function -- but we can monkey-patch.
    """
    # For "FCP - canary" we override CANARY_ASSETS to empty so canary check always passes
    state = {"prev_pair": None}

    def strat(panel, sig_d):
        if disable_canary:
            # Bypass canary by passing canary_assets=[] (returns no scores -> defensive)
            # Actually that returns defensive. To DISABLE canary, we need to pass a "always positive" set.
            # Easiest: temporarily monkey-patch CANARY_ASSETS via custom call.
            # We'll inline a copy of compute_target_weights without the canary block.
            return _fcp_no_canary(panel, sig_d, state)
        weights, new_pair, regime, safe = compute_target_weights(
            panel, sig_d, prev_pair=state["prev_pair"]
        )
        state["prev_pair"] = new_pair
        return weights

    return strat


def _fcp_no_canary(close_panel, sig_d, state):
    """Production FCP minus canary check. Faithful inline copy of compute_target_weights
    skipping the canary block."""
    from strategy_fcp.fcp_live import (
        TOP_K_CANDIDATES, CORR_LOOKBACK_DAYS, HOLD_BUFFER, faber_sma_xs,
        min_vol_pair, zscore,
    )
    monthly = close_panel.loc[:sig_d].resample("ME").last()
    safe = fcp_best_safe(monthly, sig_d, SAFE_POOL)

    # Skip canary check.

    # Faber SMA10 ranker
    sma_z = faber_sma_xs(monthly[[u for u in RISKY_UNIVERSE if u in monthly.columns]])
    if sma_z.dropna().empty:
        return {safe: 1.0}
    z_panel = sma_z.dropna()
    # Keep positive z only
    positive = z_panel[z_panel > 0].sort_values(ascending=False)
    if positive.empty:
        return {safe: 1.0}
    top_k = positive.head(TOP_K_CANDIDATES).index.tolist()
    if len(top_k) < 2:
        return {safe: 1.0}
    # Hold buffer: keep prior pair if both still in top_k+buffer
    prev_pair = state.get("prev_pair")
    if prev_pair and HOLD_BUFFER > 0:
        # If prior pair members both still have z >= z(top_k[-1]) - HOLD_BUFFER, keep them in cands
        cutoff_z = positive.iloc[-1] if len(positive) >= TOP_K_CANDIDATES else -np.inf
        all_z_dict = z_panel.to_dict()
        kept_priors = [p for p in prev_pair if p in all_z_dict and all_z_dict[p] >= cutoff_z - HOLD_BUFFER]
        cands = list(set(top_k) | set(kept_priors))
    else:
        cands = top_k
    if len(cands) < 2:
        return {safe: 1.0}
    # Min-vol pair
    daily = close_panel.loc[:sig_d, cands]
    pair = min_vol_pair(daily, cands, CORR_LOOKBACK_DAYS)
    if pair is None:
        return {safe: 1.0}
    state["prev_pair"] = pair
    return {pair[0]: 0.5, pair[1]: 0.5}


def fcp_no_buffer_target(panel, sig_d, state):
    """FCP minus hold buffer (canary still on)."""
    from strategy_fcp.fcp_live import (
        TOP_K_CANDIDATES, CORR_LOOKBACK_DAYS, faber_sma_xs, min_vol_pair,
    )
    monthly = panel.loc[:sig_d].resample("ME").last()
    safe = fcp_best_safe(monthly, sig_d, SAFE_POOL)
    if not canary_pass(panel, sig_d):
        return {safe: 1.0}
    sma_z = faber_sma_xs(monthly[[u for u in RISKY_UNIVERSE if u in monthly.columns]])
    if sma_z.dropna().empty:
        return {safe: 1.0}
    positive = sma_z.dropna()[sma_z.dropna() > 0].sort_values(ascending=False)
    if positive.empty or len(positive) < 2:
        return {safe: 1.0}
    cands = positive.head(TOP_K_CANDIDATES).index.tolist()
    daily = panel.loc[:sig_d, cands]
    pair = min_vol_pair(daily, cands, CORR_LOOKBACK_DAYS)
    if pair is None:
        return {safe: 1.0}
    return {pair[0]: 0.5, pair[1]: 0.5}


def make_fcp_no_buffer():
    state = {}
    def strat(panel, sig_d):
        return fcp_no_buffer_target(panel, sig_d, state)
    return strat


def make_fcp_no_canary_no_buffer():
    state = {"prev_pair": None}
    def strat(panel, sig_d):
        return _fcp_no_canary(panel, sig_d, state)
    return strat


# ============================================================
# MVP-style (K=2 + 50/50 + rank buffer) on FCP-15
# ============================================================
def rank_pairs_by_variance(panel, sig_d, candidates, lookback=LB):
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


def make_mvp_on_fcp(apply_canary=False, live_only=False):
    state = {"prev_pair": None}
    def strat(panel, sig_d):
        monthly = panel.loc[:sig_d].resample("ME").last()
        bs = best_safe_aaa(monthly)
        if apply_canary and not canary_pass(panel, sig_d):
            state["prev_pair"] = None
            return {bs: 1.0}
        avail = dynamic_avail(panel, sig_d, RISKY_UNIVERSE, live_only=live_only)
        scs = {u: sig_13612W(monthly[u]) for u in avail}
        cands = [u for u, s in scs.items() if pd.notna(s) and s > 0]
        if len(cands) < 2:
            state["prev_pair"] = None
            return {bs: 1.0}
        ranked = rank_pairs_by_variance(panel, sig_d, cands, LB)
        if not ranked:
            state["prev_pair"] = None
            return {bs: 1.0}
        chosen = ranked[0][0]
        if state["prev_pair"] is not None and all(m in cands for m in state["prev_pair"]):
            n = len(ranked)
            buf_k = max(1, ceil(n / 2))
            if state["prev_pair"] in {p for p, _ in ranked[:buf_k]}:
                chosen = state["prev_pair"]
        state["prev_pair"] = chosen
        a, b = list(chosen)
        return {a: 0.5, b: 0.5}
    return strat


# ============================================================
# Simulation
# ============================================================
def simulate(panel, start, end, target_fn, cost_bps=COST_BPS_SIDE):
    eom = get_eom_dates(panel, start, end)
    target_at = {}
    for d in eom:
        try:
            w = target_fn(panel, d)
        except Exception as e:
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
    df = pd.DataFrame(nav, columns=["date","equity"]).set_index("date")
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
    return dict(cagr=cagr, vol=vol, sharpe=sh, maxdd=dd)


def fmt(label, m, to):
    ann_to = to.mean() * 12 * 100 if len(to) else 0
    return (f"  {label:<48s}  Sh {m['sharpe']:+.3f}  CAGR {m['cagr']*100:+5.2f}%  "
            f"DD {m['maxdd']*100:+6.2f}%  Vol {m['vol']*100:5.2f}%  AnnTO {ann_to:>5.0f}%")


def run_fcp_baseline(panel, start, end):
    """Production FCP, no vol target."""
    daily_ret, _ = run_fcp_backtest(panel, start, end, apply_vol_target=False)
    eq = (1 + daily_ret).cumprod()
    return pd.DataFrame({"equity": eq, "daily_ret": daily_ret})


def main():
    panel = load_panel(start=pd.Timestamp("1995-01-01"))
    end = panel.index.max()
    hybrid_start = pd.Timestamp("1997-08-31")
    live_start = pd.Timestamp("2008-09-30")

    print("=" * 165)
    print("FCP vs AAA on FCP-15 universe -- COMPONENT DECOMPOSITION")
    print("=" * 165)

    for win_label, start, live_only in [
        ("Extended 28.7y", hybrid_start, False),
        ("Live-only 18y", live_start, True),
    ]:
        print()
        print("=" * 165)
        print(f">>> {win_label}")
        print("=" * 165)

        # FCP family
        print("\n[FCP family on FCP-15]")
        eq_fcp = run_fcp_baseline(panel, start, end)
        print(fmt("FCP full (canary + buffer + pair, production)", metrics(eq_fcp), np.array([0])))

        eq, to = simulate(panel, start, end, make_fcp_no_buffer())
        print(fmt("FCP - hold buffer (canary + pair)", metrics(eq), to))

        eq, to = simulate(panel, start, end, make_fcp_via_compute_target(disable_canary=True))
        print(fmt("FCP - canary (buffer + pair)", metrics(eq), to))

        eq, to = simulate(panel, start, end, make_fcp_no_canary_no_buffer())
        print(fmt("FCP - canary - buffer (just pair selection)", metrics(eq), to))

        # MVP-style on FCP-15
        print("\n[MVP-style (K=2 min-vol pair + 50/50 + rank buffer) on FCP-15]")
        eq, to = simulate(panel, start, end, make_mvp_on_fcp(apply_canary=False, live_only=live_only))
        print(fmt("MVP-style on FCP-15 (NO canary)", metrics(eq), to))
        eq, to = simulate(panel, start, end, make_mvp_on_fcp(apply_canary=True, live_only=live_only))
        print(fmt("MVP-style on FCP-15 + FCP canary", metrics(eq), to))

        # AAA on FCP-15 (best K from prior sweep)
        print("\n[AAA family on FCP-15]")
        eq, to = simulate(panel, start, end, make_aaa_strat(K=7, signal_kind="6mo", live_only=live_only))
        print(fmt("AAA K=7, 6mo, no canary, no buffer (baseline)", metrics(eq), to))
        eq, to = simulate(panel, start, end, make_aaa_strat(K=7, signal_kind="6mo", apply_canary=True, live_only=live_only))
        print(fmt("AAA K=7 + FCP canary", metrics(eq), to))
        eq, to = simulate(panel, start, end, make_aaa_strat(K=7, signal_kind="6mo", hold_buffer_z=1.0, live_only=live_only))
        print(fmt("AAA K=7 + hold buffer 1.0z", metrics(eq), to))
        eq, to = simulate(panel, start, end, make_aaa_strat(K=7, signal_kind="6mo", apply_canary=True, hold_buffer_z=1.0, live_only=live_only))
        print(fmt("AAA K=7 + canary + hold buffer 1.0z", metrics(eq), to))


if __name__ == "__main__":
    main()
