# -*- coding: utf-8 -*-
"""Downside-risk objectives (CVaR / CDaR) vs variance/naive for the CPM risky block.

Hypothesis: a downside-risk allocation objective (Min-CVaR, Min-CDaR) that does NOT
penalize upside (unlike variance) beats variance/inv-vol/EW weighting on
path-independent downside metrics (Sortino, CVaR) net of turnover + OOS -- OR it
washes out at 4 assets (DeMiguel 1/N; our prior 2x2 nulls).

Also includes GMV (global min-variance long-only) as the "min-var weights"
reference the user asked about, to demonstrate instability (turnover, max-weight
concentration, OOS) -- the empirical reason min-var weights aren't used.

Design: hold the ENTIRE pipeline fixed (universe / canary / rank / safe /
partial-safe / both-252 / mooex T+1 / 10bps) and vary ONLY the within-risky-block
allocation. Risky block = top-4 POSITIVE picks (so the allocation objective is the
sole varying factor). PROD config keeps min-var-subset(3)+inv-vol to reproduce the
anchor (1.2622 / -11.35% / 1.2196).

Optimizers: scipy.optimize.linprog (Rockafellar-Uryasev CVaR LP; Chekhlov-Uryasev
CDaR LP), scipy.optimize.minimize SLSQP (long-only GMV QP), scipy hierarchical
clustering (HRP). No cvxpy/riskfolio in venv.

Research-only. Does NOT modify prod/memo/cpm_live. No commit.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import linprog, minimize
from scipy.cluster.hierarchy import linkage, fcluster
from scipy.spatial.distance import squareform

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import cpm_live
from cpm_live import (
    inv_vol_weights, _min_var_subset, best_safe, sig_13612U, faber_sma_xs,
    RISKY_UNIVERSE, SAFE_POOL, CANARY_ASSETS, CANARY_RULE, TOP_K_CANDIDATES,
    CORR_LOOKBACK_DAYS, DEFAULT_CASH,
)
from research import cpm_harness as H
from research.cpm_bootstrap_multimetric import paired_block_bootstrap_mm

BETA = 0.95
LB = CORR_LOOKBACK_DAYS  # 252


# ----------------------------- trailing return window ------------------------
def _ret_window(close, picks, sig_d, lookback=LB):
    """Mirror cpm_live.inv_vol_weights window exactly."""
    rets = close[picks].loc[:sig_d].ffill().pct_change().dropna(how="all").tail(lookback)
    return rets


# ----------------------------- allocation objectives -------------------------
def alloc_ew(close, sig_d, picks):
    n = len(picks)
    return {t: 1.0 / n for t in picks}


def alloc_invvol(close, sig_d, picks):
    return inv_vol_weights(close.loc[:sig_d], picks, LB)


def alloc_gmv(close, sig_d, picks):
    """Long-only global min-variance: min w'Sigma w, w>=0, sum w=1 (SLSQP).
    The classic 'min-var weights' reference. Falls back to inv-vol if degenerate."""
    n = len(picks)
    if n == 1:
        return {picks[0]: 1.0}
    rets = _ret_window(close, picks, sig_d)
    if len(rets) < LB or rets.cov().isna().any().any():
        return inv_vol_weights(close.loc[:sig_d], picks, LB)
    cov = rets.cov().loc[picks, picks].values
    w0 = np.full(n, 1.0 / n)
    obj = lambda w: float(w @ cov @ w)
    jac = lambda w: 2.0 * cov @ w
    cons = ({"type": "eq", "fun": lambda w: w.sum() - 1.0,
             "jac": lambda w: np.ones(n)},)
    bnds = [(0.0, 1.0)] * n
    res = minimize(obj, w0, jac=jac, bounds=bnds, constraints=cons,
                   method="SLSQP", options={"maxiter": 500, "ftol": 1e-12})
    if not res.success or not np.all(np.isfinite(res.x)):
        return inv_vol_weights(close.loc[:sig_d], picks, LB)
    w = np.clip(res.x, 0.0, None)
    s = w.sum()
    if s <= 0:
        return inv_vol_weights(close.loc[:sig_d], picks, LB)
    w = w / s
    return {t: float(w[i]) for i, t in enumerate(picks)}


def alloc_mincvar(close, sig_d, picks):
    """Rockafellar-Uryasev Min-CVaR LP (beta=0.95) on trailing returns.
    Vars x=[w(n), alpha, u(T)]. min alpha + 1/((1-beta)T) sum u_t
    s.t. -r_t.w - alpha - u_t <= 0 ; u>=0 ; sum w=1 ; w in [0,1]. Loss=-return."""
    n = len(picks)
    if n == 1:
        return {picks[0]: 1.0}
    rets = _ret_window(close, picks, sig_d)
    if len(rets) < LB or rets.isna().any().any():
        return inv_vol_weights(close.loc[:sig_d], picks, LB)
    R = rets.loc[:, picks].values  # T x n
    T = R.shape[0]
    nv = n + 1 + T
    c = np.zeros(nv)
    c[n] = 1.0                       # alpha
    c[n + 1:] = 1.0 / ((1.0 - BETA) * T)  # u_t
    # A_ub: -R w - alpha - u_t <= 0
    A = np.zeros((T, nv))
    A[:, :n] = -R
    A[:, n] = -1.0
    for t in range(T):
        A[t, n + 1 + t] = -1.0
    b = np.zeros(T)
    A_eq = np.zeros((1, nv)); A_eq[0, :n] = 1.0
    b_eq = np.array([1.0])
    bounds = [(0.0, 1.0)] * n + [(None, None)] + [(0.0, None)] * T
    res = linprog(c, A_ub=A, b_ub=b, A_eq=A_eq, b_eq=b_eq, bounds=bounds,
                  method="highs")
    if not res.success or not np.all(np.isfinite(res.x[:n])):
        return inv_vol_weights(close.loc[:sig_d], picks, LB)
    w = np.clip(res.x[:n], 0.0, None)
    s = w.sum()
    if s <= 0:
        return inv_vol_weights(close.loc[:sig_d], picks, LB)
    w = w / s
    return {t: float(w[i]) for i, t in enumerate(picks)}


def alloc_mincdar(close, sig_d, picks):
    """Chekhlov-Uryasev Min-CDaR LP (beta=0.95) on trailing returns.
    Uncompounded cumulative path cum_t = sum_{s<=t} r_s.w. Drawdown dd_t = u_t - cum_t.
    Vars x=[w(n), alpha, z(T), u(T)].
      min alpha + 1/((1-beta)T) sum z_t
      z_t >= u_t - cum_t - alpha       (drawdown excess over alpha)
      u_t >= cum_t                     (running max >= cumulative)
      u_t >= u_{t-1}                   (running max non-decreasing)
      z>=0 ; sum w=1 ; w in [0,1] ; u free.
    Path-dependent objective. Falls back to inv-vol if degenerate."""
    n = len(picks)
    if n == 1:
        return {picks[0]: 1.0}
    rets = _ret_window(close, picks, sig_d)
    if len(rets) < LB or rets.isna().any().any():
        return inv_vol_weights(close.loc[:sig_d], picks, LB)
    R = rets.loc[:, picks].values  # T x n
    T = R.shape[0]
    C = np.cumsum(R, axis=0)       # cum_t coefficients in w: C[t] . w
    # var layout
    iw = 0; ia = n; iz = n + 1; iu = n + 1 + T
    nv = n + 1 + T + T
    c = np.zeros(nv)
    c[ia] = 1.0
    c[iz:iz + T] = 1.0 / ((1.0 - BETA) * T)
    rows = []; bs = []
    # z_t >= u_t - cum_t - alpha  ->  -z_t + u_t - C_t.w - alpha <= 0
    for t in range(T):
        r = np.zeros(nv)
        r[iw:iw + n] = -C[t]
        r[ia] = -1.0
        r[iz + t] = -1.0
        r[iu + t] = 1.0
        rows.append(r); bs.append(0.0)
    # u_t >= cum_t  ->  -u_t + C_t.w <= 0
    for t in range(T):
        r = np.zeros(nv)
        r[iw:iw + n] = C[t]
        r[iu + t] = -1.0
        rows.append(r); bs.append(0.0)
    # u_t >= u_{t-1}  ->  -u_t + u_{t-1} <= 0
    for t in range(1, T):
        r = np.zeros(nv)
        r[iu + t] = -1.0
        r[iu + t - 1] = 1.0
        rows.append(r); bs.append(0.0)
    A = np.array(rows); b = np.array(bs)
    A_eq = np.zeros((1, nv)); A_eq[0, iw:iw + n] = 1.0
    b_eq = np.array([1.0])
    bounds = ([(0.0, 1.0)] * n + [(None, None)] + [(0.0, None)] * T
              + [(None, None)] * T)
    res = linprog(c, A_ub=A, b_ub=b, A_eq=A_eq, b_eq=b_eq, bounds=bounds,
                  method="highs")
    if not res.success or not np.all(np.isfinite(res.x[:n])):
        return inv_vol_weights(close.loc[:sig_d], picks, LB)
    w = np.clip(res.x[:n], 0.0, None)
    s = w.sum()
    if s <= 0:
        return inv_vol_weights(close.loc[:sig_d], picks, LB)
    w = w / s
    return {t: float(w[i]) for i, t in enumerate(picks)}


def alloc_hrp(close, sig_d, picks):
    """Hierarchical Risk Parity (Lopez de Prado 2016) on trailing returns.
    corr->dist, single-linkage cluster, quasi-diag, recursive bisection
    inverse-variance. Falls back to inv-vol if degenerate."""
    n = len(picks)
    if n == 1:
        return {picks[0]: 1.0}
    if n == 2:
        return inv_vol_weights(close.loc[:sig_d], picks, LB)
    rets = _ret_window(close, picks, sig_d)
    if len(rets) < LB or rets.cov().isna().any().any():
        return inv_vol_weights(close.loc[:sig_d], picks, LB)
    cov = rets.cov().loc[picks, picks]
    corr = rets.corr().loc[picks, picks].values
    cov_v = cov.values
    dist = np.sqrt(np.clip((1.0 - corr) / 2.0, 0.0, None))
    np.fill_diagonal(dist, 0.0)
    try:
        condensed = squareform(dist, checks=False)
        link = linkage(condensed, method="single")
    except Exception:
        return inv_vol_weights(close.loc[:sig_d], picks, LB)
    # quasi-diagonalization: leaf order from dendrogram
    def get_quasi_diag(link):
        link = link.astype(int)
        sort_ix = pd.Series([link[-1, 0], link[-1, 1]])
        num_items = link[-1, 3]
        while sort_ix.max() >= num_items:
            sort_ix.index = range(0, sort_ix.shape[0] * 2, 2)
            df0 = sort_ix[sort_ix >= num_items]
            i = df0.index; j = df0.values - num_items
            sort_ix[i] = link[j, 0]
            df1 = pd.Series(link[j, 1], index=i + 1)
            sort_ix = pd.concat([sort_ix, df1]).sort_index()
            sort_ix.index = range(sort_ix.shape[0])
        return sort_ix.tolist()

    sort_ix = get_quasi_diag(link)
    ivp = lambda c: (1.0 / np.diag(c)) / (1.0 / np.diag(c)).sum()

    def cluster_var(c, items):
        sub = c[np.ix_(items, items)]
        w = ivp(sub).reshape(-1, 1)
        return float((w.T @ sub @ w)[0, 0])

    w = pd.Series(1.0, index=sort_ix)
    clusters = [sort_ix]
    while clusters:
        clusters = [c[j:k] for c in clusters
                    for j, k in ((0, len(c) // 2), (len(c) // 2, len(c)))
                    if len(c) > 1]
        for i in range(0, len(clusters), 2):
            c0, c1 = clusters[i], clusters[i + 1]
            v0 = cluster_var(cov_v, c0)
            v1 = cluster_var(cov_v, c1)
            a = 1.0 - v0 / (v0 + v1)
            w[c0] *= a
            w[c1] *= (1.0 - a)
    out = {picks[idx]: float(w[idx]) for idx in sort_ix}
    s = sum(out.values())
    return {t: v / s for t, v in out.items()}


ALLOC = {
    "EW": alloc_ew,
    "INV-VOL": alloc_invvol,
    "GMV": alloc_gmv,
    "MIN-CVaR": alloc_mincvar,
    "MIN-CDaR": alloc_mincdar,
    "HRP": alloc_hrp,
}


# ----------------------------- selection + weight fn -------------------------
def _select_positive_picks(close_panel, sig_d):
    """Replicate cpm_live.compute_target_weights selection up to positive picks.
    Returns (regime, safe, positive_picks) -- positive_picks is the full set of
    top-K positive momentum survivors (the risky block before any subset)."""
    universe, safe_pool, canary_assets = RISKY_UNIVERSE, SAFE_POOL, CANARY_ASSETS
    monthly = close_panel.loc[:sig_d].resample("ME").last()
    safe = best_safe(monthly, sig_d, safe_pool)
    canary_scores = []
    for c in canary_assets:
        if c not in monthly.columns:
            continue
        s = sig_13612U(monthly[c])
        if pd.notna(s):
            canary_scores.append(s)
    if not canary_scores:
        return "DEFENSIVE", safe, []
    n_pos = sum(1 for s in canary_scores if s > 0)
    if CANARY_RULE == "any_positive":
        if n_pos == 0:
            return "DEFENSIVE", safe, []
    elif CANARY_RULE == "all_positive":
        if n_pos < len(canary_scores):
            return "DEFENSIVE", safe, []
    else:
        if n_pos <= len(canary_scores) // 2:
            return "DEFENSIVE", safe, []
    faber = faber_sma_xs(monthly)
    avail = [t for t in universe
             if t in faber.index and pd.notna(faber[t])
             and pd.notna(close_panel.loc[sig_d].get(t, np.nan)
                          if sig_d in close_panel.index else np.nan)]
    if not avail:
        return "DEFENSIVE", safe, []
    daily_rets = close_panel[avail].ffill().pct_change()
    scores = {}
    for t in avail:
        v = daily_rets[t].loc[:sig_d].tail(252).std() * np.sqrt(252)
        if pd.isna(v) or v < 1e-9:
            v = 1.0
        scores[t] = float(faber[t]) / v
    sa = pd.Series(scores)
    ranked = sa.sort_values(ascending=False)
    top_k = max(2, min(TOP_K_CANDIDATES, len(ranked)))
    top = ranked.iloc[:top_k]
    positive = top[top.index.map(lambda t: faber.get(t, -np.inf) > 0)]
    if len(positive) == 0:
        return "DEFENSIVE", safe, []
    return "RISK_ON", safe, list(positive.index)


# turnover/concentration recorders, keyed by config name
_REC = {}


def make_weight_fn(name):
    """Build a weight_fn(panel, sig_d) -> dict for a given allocation config.
    PROD = exact prod (min-var-subset(3)+inv-vol). Others apply ALLOC[name] to the
    full top-4 positive picks. Partial-safe scaling identical across all configs."""
    _REC[name] = {}

    def wf(close_panel, sig_d):
        regime, safe, positive_picks = _select_positive_picks(close_panel, sig_d)
        if regime == "DEFENSIVE" or not positive_picks:
            return {safe: 1.0}
        n_pos = len(positive_picks)
        risky_fraction = min(n_pos, 4) / 4.0
        safe_fraction = 1.0 - risky_fraction
        if name == "PROD":
            picks = (_min_var_subset(close_panel, sig_d, positive_picks, LB, 3)
                     if n_pos == 4 else positive_picks)
            risky_w = inv_vol_weights(close_panel.loc[:sig_d], picks, LB)
        else:
            picks = positive_picks
            risky_w = ALLOC[name](close_panel, sig_d, picks)
        out = {t: w * risky_fraction for t, w in risky_w.items()}
        if safe_fraction > 0:
            out[safe] = out.get(safe, 0.0) + safe_fraction
        # record risky-block weights for turnover/concentration (risky only)
        _REC[name][pd.Timestamp(sig_d)] = dict(risky_w)
        return out

    return wf


# ----------------------------- metrics --------------------------------------
def sortino_ann(x):
    x = np.asarray(x, float)
    neg = np.minimum(x, 0.0)
    dd = np.sqrt(np.mean(neg ** 2))
    return (x.mean() * 252.0) / (dd * np.sqrt(252.0)) if dd > 0 else float("nan")


def cvar_ratio_ann(x, q=0.05):
    x = np.asarray(x, float)
    n = x.size
    if n == 0:
        return float("nan")
    k = max(1, int(np.floor(q * n)))
    worst = np.sort(x)[:k]
    es = worst.mean()
    return (x.mean() * 252.0) / abs(es) if es < 0 else float("nan")


def maxdd(x):
    eq = (1.0 + pd.Series(x)).cumprod()
    return float((eq / eq.cummax() - 1.0).min())


def full_metrics(ret, cash):
    m = cpm_live.perf_metrics(ret, cash)
    x = ret.values
    return {
        "Sharpe": m.get("sharpe"), "Sortino": sortino_ann(x),
        "CVaR_ratio": cvar_ratio_ann(x), "Calmar": m.get("calmar"),
        "Martin": m.get("martin"), "MaxDD": m.get("max_drawdown"),
        "CAGR": m.get("cagr"), "vol": m.get("vol"),
    }


def annual_turnover(rec):
    """Annualized one-way turnover of the RISKY block across rebalances.
    sum 0.5*|w_t - w_{t-1}| over union of tickers, scaled to per-year."""
    dates = sorted(rec.keys())
    if len(dates) < 2:
        return float("nan")
    tos = []
    prev = rec[dates[0]]
    for d in dates[1:]:
        cur = rec[d]
        keys = set(prev) | set(cur)
        to = 0.5 * sum(abs(cur.get(k, 0.0) - prev.get(k, 0.0)) for k in keys)
        tos.append(to)
        prev = cur
    years = (dates[-1] - dates[0]).days / 365.25
    n_rebal = len(tos)
    per_rebal = np.mean(tos)
    rebal_per_year = n_rebal / years if years > 0 else float("nan")
    return float(per_rebal * rebal_per_year)


def max_weight_stats(rec):
    """Concentration of risky-block weights. Single-asset (n_pos=1) blocks are
    trivially 1.0, so also report stats conditional on >=2 and ==4 asset blocks
    where the allocation objective actually differs."""
    mw_all = [max(w.values()) for w in rec.values() if w]
    mw_ge2 = [max(w.values()) for w in rec.values() if len(w) >= 2]
    mw_eq4 = [max(w.values()) for w in rec.values() if len(w) == 4]
    f = lambda a: (float(np.mean(a)), float(np.max(a))) if a else (float("nan"),) * 2
    a_avg, a_max = f(mw_all)
    g_avg, g_max = f(mw_ge2)
    q_avg, q_max = f(mw_eq4)
    return {"all_avg": a_avg, "all_max": a_max, "ge2_avg": g_avg, "ge2_max": g_max,
            "eq4_avg": q_avg, "eq4_max": q_max, "n_eq4": len(mw_eq4)}


CRISES = {
    "GFC": ("2007-10-01", "2009-06-30"),
    "COVID": ("2020-02-19", "2020-04-30"),
    "2022": ("2022-01-01", "2022-10-31"),
    "2025": ("2025-01-01", "2025-06-30"),
}


def crisis_metrics(ret):
    out = {}
    for nm, (lo, hi) in CRISES.items():
        w = ret.loc[(ret.index >= lo) & (ret.index <= hi)]
        if len(w) < 5:
            out[nm] = None
            continue
        x = w.values
        out[nm] = {"Sortino": sortino_ann(x), "CVaR_ratio": cvar_ratio_ann(x),
                   "MaxDD": maxdd(x), "n": int(len(w))}
    return out


# ----------------------------- walk-forward ---------------------------------
def walk_forward(series, cash, n_seg=3):
    idx = series.index
    bounds = np.linspace(0, len(idx), n_seg + 1).astype(int)
    segs = []
    for i in range(n_seg):
        s = series.iloc[bounds[i]:bounds[i + 1]]
        m = cpm_live.perf_metrics(s, cash)
        segs.append({"start": str(s.index[0].date()), "end": str(s.index[-1].date()),
                     "Sharpe": m.get("sharpe"), "Sortino": sortino_ann(s.values),
                     "CVaR_ratio": cvar_ratio_ann(s.values)})
    return segs


# ----------------------------- main -----------------------------------------
def main():
    d = H.load_data()
    print("Verifying anchor...", file=sys.stderr)
    anchor = H.verify_anchor(data=d)
    assert abs(anchor["Sharpe"] - 1.2622) < 5e-4, anchor
    print(f"ANCHOR OK Sharpe={anchor['Sharpe']:.4f} MaxDD={anchor['MaxDD']:.4f} "
          f"Calmar={anchor['Calmar']:.4f}", file=sys.stderr)

    configs = ["PROD", "EW", "INV-VOL", "GMV", "MIN-CVaR", "MIN-CDaR", "HRP"]
    results = {}
    series_clean = {}
    series_ext = {}
    for name in configs:
        print(f"Running {name}...", file=sys.stderr)
        wf = make_weight_fn(name)
        sc = H.run_strategy(wf, window="clean", data=d)
        se = H.run_strategy(wf, window="ext", data=d)
        series_clean[name] = sc
        series_ext[name] = se
        mc = full_metrics(sc, d.cash)
        me = full_metrics(se, d.cash)
        rec = _REC[name]
        to = annual_turnover(rec)
        conc = max_weight_stats(rec)
        results[name] = {
            "clean": mc, "ext": me, "turnover": to,
            "concentration": conc,
            "crisis": crisis_metrics(se),
        }
        print(f"  {name}: clean Sharpe={mc['Sharpe']:.4f} Sortino={mc['Sortino']:.4f} "
              f"CVaR={mc['CVaR_ratio']:.4f} MaxDD={mc['MaxDD']:.4f} TO={to:.3f}",
              file=sys.stderr)

    # PROD sanity: should reproduce anchor
    assert abs(results["PROD"]["clean"]["Sharpe"] - 1.2622) < 5e-4

    # Bootstrap key contrasts vs INV-VOL (baseline) on clean series
    base = series_clean["INV-VOL"]
    boot = {}
    for name in ["MIN-CVaR", "MIN-CDaR", "GMV"]:
        print(f"Bootstrap {name} vs INV-VOL...", file=sys.stderr)
        boot[name] = paired_block_bootstrap_mm(series_clean[name], base, d.cash,
                                               B=2000, block=21, seed=42)

    # Walk-forward for any config beating INV-VOL on clean Sharpe (and the downside cfgs)
    inv_sh = results["INV-VOL"]["clean"]["Sharpe"]
    wf_out = {}
    for name in ["MIN-CVaR", "MIN-CDaR", "GMV", "HRP", "PROD"]:
        if results[name]["clean"]["Sharpe"] >= inv_sh - 1e-9 or name in ("MIN-CVaR", "MIN-CDaR"):
            wf_out[name] = walk_forward(series_clean[name], d.cash, 3)

    out = {"anchor": {k: float(v) for k, v in anchor.items()},
           "results": results, "bootstrap_vs_invvol": boot,
           "walk_forward": wf_out,
           "inv_vol_clean_sharpe": float(inv_sh)}
    op = ROOT / "research" / "cpm_cvar_cdar_objective.json"
    op.write_text(json.dumps(out, indent=2, default=float))
    print(f"WROTE {op}", file=sys.stderr)

    # console table
    print("\n=== CLEAN (DECISION) ===")
    hdr = f"{'config':<10}{'Sharpe':>8}{'Sortino':>8}{'CVaR':>7}{'Calmar':>8}{'Martin':>8}{'MaxDD':>8}{'CAGR':>7}{'vol':>7}{'TO/yr':>7}{'mxW':>6}"
    print(hdr)
    for name in configs:
        r = results[name]; m = r["clean"]
        print(f"{name:<10}{m['Sharpe']:>8.4f}{m['Sortino']:>8.4f}{m['CVaR_ratio']:>7.3f}"
              f"{m['Calmar']:>8.4f}{m['Martin']:>8.3f}{m['MaxDD']:>8.4f}{m['CAGR']:>7.4f}"
              f"{m['vol']:>7.4f}{r['turnover']:>7.3f}{r['concentration']['eq4_max']:>6.2f}")
    print("\n=== EXT ===")
    for name in configs:
        m = results[name]["ext"]
        print(f"{name:<10}{m['Sharpe']:>8.4f}{m['Sortino']:>8.4f}{m['CVaR_ratio']:>7.3f}"
              f"{m['MaxDD']:>8.4f}{m['CAGR']:>7.4f}")
    print("\n=== PER-CRISIS MaxDD (ext series) ===")
    print(f"{'config':<10}" + "".join(f"{c:>12}" for c in CRISES))
    for name in configs:
        cr = results[name]["crisis"]
        cells = "".join((f"{cr[c]['MaxDD']:>12.4f}" if cr[c] else f"{'--':>12}") for c in CRISES)
        print(f"{name:<10}{cells}")
    print("\n=== CONCENTRATION (risky-block max weight; eq4 = 4-asset blocks) ===")
    print(f"{'config':<10}{'eq4_avg':>9}{'eq4_max':>9}{'ge2_avg':>9}{'ge2_max':>9}{'n_eq4':>7}")
    for name in configs:
        c = results[name]['concentration']
        print(f"{name:<10}{c['eq4_avg']:>9.3f}{c['eq4_max']:>9.3f}{c['ge2_avg']:>9.3f}"
              f"{c['ge2_max']:>9.3f}{c['n_eq4']:>7d}")
    print("\n=== BOOTSTRAP vs INV-VOL (clean; dMetric mean [95% CI] p>0) ===")
    for name, bb in boot.items():
        print(f"-- {name} vs INV-VOL")
        for met in ["dSharpe", "dSortino", "dCVaR"]:
            s = bb[met]
            print(f"   {met:<9} {s['mean']:+.4f} [{s['ci_lo']:+.4f},{s['ci_hi']:+.4f}] p>0={s['p_gt0']:.3f}")
    print("\nDONE")


if __name__ == "__main__":
    main()
