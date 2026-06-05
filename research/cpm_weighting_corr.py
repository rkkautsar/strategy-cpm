"""Isolate the WEIGHTING lever: does correlation/covariance-aware weighting
(ERC / HRP) beat CPM production inverse-vol weighting, net of cost + OOS?

Throwaway research. Read-only re production. No production files changed; no commit.

Production CPM (cpm_live.compute_target_weights, verified):
  rank by vol-adjusted Faber (faber / vol_252) -> top-4 -> positive-faber filter
  -> inv_vol_weights (252d cov DIAGONAL only) -> strict-4 partial-safe fallback.
  Correlation enters NOWHERE in prod. This script swaps ONLY the risky-block
  weighting; selection/canary/safe/fallback held byte-identical to prod.

Weighting variants (same prod-selected picks):
  - invvol : production inverse-vol (cpm_live.inv_vol_weights, sample diag).
  - erc    : equal-risk-contribution (full cov, SLSQP).
  - hrp    : Hierarchical Risk Parity (Lopez de Prado).
Cov estimate for erc/hrp: Ledoit-Wolf shrinkage (default) and sample (robustness).
Cov lookback: 252 (prod) and 504.

Sharp 2x2 + HRP: selection {rank-select=PROD, min-var-subset=NEW} x weighting
{invvol=PROD, ERC}; plus HRP over prod selection. min-var subset is a NEW
exploratory variant (never adopted), NOT prod.
"""

from __future__ import annotations

import json
import math
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import linkage
from scipy.spatial.distance import squareform
from scipy.optimize import minimize
from sklearn.covariance import LedoitWolf

from research import cpm_harness as H
import cpm_live
from cpm_live import (
    faber_sma_xs, best_safe, sig_13612U, inv_vol_weights,
    RISKY_UNIVERSE, SAFE_POOL, CANARY_ASSETS, CANARY_RULE,
    TOP_K_CANDIDATES, DEFAULT_CASH,
)

OUT = Path(__file__).resolve().parent / "cpm_weighting_corr_findings.json"


# ---------------- covariance estimators ----------------
def _ret_window(close, picks, lookback):
    """Trailing return matrix, mirrors cpm_live.inv_vol_weights window exactly."""
    rets = close[picks].ffill().pct_change().dropna(how="all").tail(lookback)
    return rets


def _cov(rets, method):
    """Return (n,n) covariance array. method in {sample, lw}."""
    if method == "sample":
        return rets.cov().values
    # Ledoit-Wolf on complete rows
    X = rets.dropna().values
    if X.shape[0] < 3:
        return rets.cov().values
    return LedoitWolf().fit(X).covariance_


# ---------------- weighting schemes ----------------
def _erc(cov):
    n = cov.shape[0]
    sig = np.sqrt(np.clip(np.diag(cov), 1e-18, None))
    iv = 1.0 / sig
    iv = iv / iv.sum()
    if n == 1:
        return np.array([1.0])

    def obj(w):
        rc = w * (cov @ w)
        d = rc[:, None] - rc[None, :]
        return float((d * d).sum())

    cons = ({"type": "eq", "fun": lambda w: np.sum(w) - 1.0},)
    bnds = tuple((1e-9, 1.0) for _ in range(n))
    r = minimize(obj, iv, method="SLSQP", bounds=bnds, constraints=cons,
                 options={"maxiter": 1000, "ftol": 1e-14})
    if not r.success:
        return iv
    w = np.clip(r.x, 0.0, None)
    s = w.sum()
    return w / s if s > 0 else iv


def _hrp(cov):
    """Hierarchical Risk Parity (Lopez de Prado 2016)."""
    n = cov.shape[0]
    if n == 1:
        return np.array([1.0])
    std = np.sqrt(np.clip(np.diag(cov), 1e-18, None))
    corr = cov / np.outer(std, std)
    corr = np.clip(corr, -1.0, 1.0)
    if n == 2:
        iv = 1.0 / np.clip(std, 1e-18, None)
        return iv / iv.sum()
    # distance + linkage
    dist = np.sqrt(np.clip((1.0 - corr) / 2.0, 0.0, None))
    np.fill_diagonal(dist, 0.0)
    condensed = squareform(dist, checks=False)
    link = linkage(condensed, method="single")
    # quasi-diagonalization
    link = link.astype(int)
    sort_ix = pd.Series([link[-1, 0], link[-1, 1]])
    num_items = link[-1, 3]
    while sort_ix.max() >= num_items:
        sort_ix.index = range(0, sort_ix.shape[0] * 2, 2)
        df0 = sort_ix[sort_ix >= num_items]
        i = df0.index
        j = df0.values - num_items
        sort_ix[i] = link[j, 0]
        df1 = pd.Series(link[j, 1], index=i + 1)
        sort_ix = pd.concat([sort_ix, df1]).sort_index()
        sort_ix.index = range(sort_ix.shape[0])
    sort_ix = sort_ix.tolist()
    # recursive bisection
    w = pd.Series(1.0, index=sort_ix)
    clusters = [sort_ix]
    while clusters:
        clusters = [c[j:k] for c in clusters
                    for j, k in ((0, len(c) // 2), (len(c) // 2, len(c)))
                    if len(c) > 1]
        for i in range(0, len(clusters), 2):
            c0 = clusters[i]
            c1 = clusters[i + 1]
            v0 = _cluster_var(cov, c0)
            v1 = _cluster_var(cov, c1)
            alpha = 1.0 - v0 / (v0 + v1)
            w[c0] *= alpha
            w[c1] *= 1.0 - alpha
    return w.reindex(range(n)).values


def _cluster_var(cov, items):
    sub = cov[np.ix_(items, items)]
    iv = 1.0 / np.clip(np.diag(sub), 1e-18, None)
    iv = iv / iv.sum()
    return float(iv @ sub @ iv)


def _risky_weights(close, sig_d, picks, weighting, cov_method, lookback):
    """Weight the risky block (sums to 1 over picks). invvol delegates to prod."""
    if len(picks) == 1:
        return {picks[0]: 1.0}
    csub = close.loc[:sig_d]
    if weighting == "invvol" and cov_method == "sample" and lookback == cpm_live.CORR_LOOKBACK_DAYS:
        # byte-identical to production
        return inv_vol_weights(csub, picks, lookback)
    rets = _ret_window(csub, picks, lookback)
    if len(rets) < lookback or rets.shape[1] < len(picks):
        return {t: 1.0 / len(picks) for t in picks}
    cols = list(rets.columns)
    cov = _cov(rets, cov_method)
    if not np.all(np.isfinite(cov)):
        return {t: 1.0 / len(picks) for t in picks}
    if weighting == "invvol":
        sig = np.sqrt(np.clip(np.diag(cov), 1e-18, None))
        wv = 1.0 / sig
        wv = wv / wv.sum()
    elif weighting == "erc":
        wv = _erc(cov)
    elif weighting == "hrp":
        wv = _hrp(cov)
    else:
        raise ValueError(weighting)
    return {cols[i]: float(wv[i]) for i in range(len(cols))}


# ---------------- min-var subset (NEW exploratory selection) ----------------
def _min_var_subset(close, sig_d, candidates, lookback, m):
    if len(candidates) <= m:
        return list(candidates)
    rets = _ret_window(close.loc[:sig_d], candidates, lookback)
    if len(rets) < lookback:
        return list(candidates)
    cov = rets.cov()
    if cov.isna().any().any():
        return list(candidates)
    w = 1.0 / m
    best, best_v = None, np.inf
    for combo in combinations(candidates, m):
        sub = cov.loc[list(combo), list(combo)].values
        v = float(w * w * sub.sum())
        if v < best_v:
            best_v, best = v, combo
    return list(best) if best else list(candidates)


# ---------------- full prod-faithful weight fn with swappable weighting ----------------
def make_weight_fn(weighting="invvol", cov_method="sample", lookback=None,
                   selection="rank", subset_m=3):
    """Return weight_fn(panel, sig_d) replicating prod selection + partial-safe,
    swapping ONLY the risky-block weighting (and optionally min-var subset)."""
    lb = lookback or cpm_live.CORR_LOOKBACK_DAYS

    def wf(close_panel, sig_d):
        universe = RISKY_UNIVERSE
        monthly = close_panel.loc[:sig_d].resample("ME").last()
        safe = best_safe(monthly, sig_d, SAFE_POOL)

        cscores = []
        for c in CANARY_ASSETS:
            if c not in monthly.columns:
                continue
            s = sig_13612U(monthly[c])
            if pd.notna(s):
                cscores.append(s)
        if not cscores:
            return {safe: 1.0}
        n_pos = sum(1 for s in cscores if s > 0)
        if CANARY_RULE == "any_positive":
            if n_pos == 0:
                return {safe: 1.0}
        elif CANARY_RULE == "all_positive":
            if n_pos < len(cscores):
                return {safe: 1.0}
        else:
            if n_pos <= len(cscores) // 2:
                return {safe: 1.0}

        faber = faber_sma_xs(monthly)
        avail = [t for t in universe
                 if t in faber.index and pd.notna(faber[t])
                 and (sig_d in close_panel.index and pd.notna(close_panel.loc[sig_d].get(t, np.nan)))]
        if not avail:
            return {safe: 1.0}
        dr = close_panel[avail].ffill().pct_change()
        scores = {}
        for t in avail:
            v = dr[t].loc[:sig_d].tail(252).std() * np.sqrt(252)
            if pd.isna(v) or v < 1e-9:
                v = 1.0
            scores[t] = float(faber[t]) / v
        ranked = pd.Series(scores).sort_values(ascending=False)
        top_k = max(2, min(TOP_K_CANDIDATES, len(ranked)))
        top = ranked.iloc[:top_k]
        positive = [t for t in top.index if faber.get(t, -np.inf) > 0]
        if len(positive) == 0:
            return {safe: 1.0}

        picks = positive
        if selection == "minvar" and len(picks) > subset_m:
            picks = _min_var_subset(close_panel, sig_d, picks, lb, subset_m)

        n_picks = len(picks)
        # partial-safe fraction uses ORIGINAL n positives (prod semantics: strict-4)
        risky_fraction = min(len(positive), 4) / 4.0
        safe_fraction = 1.0 - risky_fraction

        rw = _risky_weights(close_panel, sig_d, picks, weighting, cov_method, lb)
        out = {t: w * risky_fraction for t, w in rw.items()}
        if safe_fraction > 0:
            out[safe] = out.get(safe, 0.0) + safe_fraction
        return out

    return wf


# ---------------- metrics / crises / turnover ----------------
CRISES = {
    "GFC_2007_10__2009_06": ("2007-10-01", "2009-06-30"),
    "COVID_2020_02__2020_06": ("2020-02-01", "2020-06-30"),
    "Y2022_full": ("2022-01-01", "2022-12-31"),
    "Y2025_tariff_02_19__06_12": ("2025-02-19", "2025-06-12"),
}


def _sub_metrics(returns, cash, a, b):
    r = returns.loc[(returns.index >= pd.Timestamp(a)) & (returns.index <= pd.Timestamp(b))]
    if len(r) < 5:
        return None
    m = cpm_live.perf_metrics(r, cash)
    return {
        "Sharpe": m.get("sharpe"), "Calmar": m.get("calmar"),
        "Martin": m.get("martin"), "MaxDD": m.get("max_drawdown"),
        "CAGR": m.get("cagr"),
    }


def annualized_turnover(weight_fn, data):
    """One-way annualized turnover from monthly target weights (sum|dw|/2 per
    rebalance, *12). Uses signal dates = month-end resample, matching engine."""
    panel = data.panel
    sig_dates = panel.resample("ME").last().index
    sig_dates = [d for d in sig_dates if d >= data.clean_start and d <= data.end]
    prev = {}
    tot = 0.0
    n = 0
    for d in sig_dates:
        # nearest available trading day <= d
        idx = panel.index[panel.index <= d]
        if len(idx) == 0:
            continue
        sd = idx[-1]
        w = weight_fn(panel, sd)
        keys = set(w) | set(prev)
        dv = sum(abs(w.get(k, 0.0) - prev.get(k, 0.0)) for k in keys)
        tot += dv / 2.0
        n += 1
        prev = w
    if n == 0:
        return float("nan")
    return tot / n * 12.0


def run_cell(weight_fn, data, label):
    out = {}
    for win in ("clean", "ext"):
        r = H.run_strategy(weight_fn, window=win, data=data)
        out[win] = H.metrics(r, data=data)
        out[win + "_returns"] = r  # keep for bootstrap (not serialized)
    # per-crisis on ext curve
    rext = out["ext_returns"]
    out["crises"] = {}
    for name, (a, b) in CRISES.items():
        out["crises"][name] = _sub_metrics(rext, data.cash, a, b)
    out["turnover_ann"] = annualized_turnover(weight_fn, data)
    out["label"] = label
    return out


# ---------------- paired block bootstrap ----------------
def paired_block_bootstrap(ra, rb, cash, B=2000, block=21, seed=42):
    common = ra.index.intersection(rb.index)
    a = ra.loc[common].values
    b = rb.loc[common].values
    n = len(a)
    rng = np.random.default_rng(seed)
    nb = int(np.ceil(n / block))

    def stats(x):
        s = pd.Series(x, index=common)
        m = cpm_live.perf_metrics(s, cash)
        return m.get("sharpe"), m.get("calmar"), m.get("max_drawdown")

    dS, dC, dD = [], [], []
    for _ in range(B):
        starts = rng.integers(0, n, size=nb)
        idx = np.concatenate([np.arange(s, s + block) % n for s in starts])[:n]
        sA, cA, dA = stats(a[idx])
        sB, cB, dB = stats(b[idx])
        dS.append(sA - sB); dC.append(cA - cB); dD.append(dA - dB)
    def summ(arr):
        arr = np.array(arr)
        return {
            "mean": float(arr.mean()),
            "ci_lo": float(np.percentile(arr, 2.5)),
            "ci_hi": float(np.percentile(arr, 97.5)),
            "p_gt0": float((arr > 0).mean()),
        }
    return {"dSharpe": summ(dS), "dCalmar": summ(dC), "dMaxDD": summ(dD)}


# ---------------- sequential / walk-forward OOS ----------------
def walk_forward_oos(weight_fn_base, weight_fn_var, data, splits=None):
    """Sequential OOS: split clean window into expanding-ish thirds; report
    var-vs-base Sharpe/Calmar per segment (single in-sample param, so this is a
    stability check, not a tuning CV)."""
    rb = H.run_strategy(weight_fn_base, window="clean", data=data)
    rv = H.run_strategy(weight_fn_var, window="clean", data=data)
    common = rb.index.intersection(rv.index)
    rb = rb.loc[common]; rv = rv.loc[common]
    if splits is None:
        # 3 sequential segments
        n = len(common)
        bounds = [0, n // 3, 2 * n // 3, n]
        splits = [(bounds[i], bounds[i + 1]) for i in range(3)]
    segs = []
    for (lo, hi) in splits:
        bb = rb.iloc[lo:hi]; vv = rv.iloc[lo:hi]
        mb = cpm_live.perf_metrics(bb, data.cash)
        mv = cpm_live.perf_metrics(vv, data.cash)
        segs.append({
            "start": str(common[lo].date()), "end": str(common[hi - 1].date()),
            "base_Sharpe": mb.get("sharpe"), "var_Sharpe": mv.get("sharpe"),
            "base_Calmar": mb.get("calmar"), "var_Calmar": mv.get("calmar"),
            "dSharpe": mv.get("sharpe") - mb.get("sharpe"),
            "dCalmar": mv.get("calmar") - mb.get("calmar"),
        })
    return segs


def main():
    data = H.load_data()
    anchor = H.verify_anchor(data=data)
    print("ANCHOR OK:", {k: round(float(v), 4) for k, v in anchor.items() if k in ("Sharpe", "MaxDD", "Calmar")})

    results = {"anchor": {k: float(v) for k, v in anchor.items()}}

    # ---- PRIMARY: weighting-only A/B on prod rank-select picks ----
    # cov sensitivity grid: lookback {252,504} x cov {sample,lw}
    cells = {}
    # baseline (prod): invvol sample 252
    base_wf = make_weight_fn("invvol", "sample", 252, "rank")
    cells["PROD_invvol_s252"] = run_cell(base_wf, data, "PROD invvol sample 252")

    grid = []
    for w in ("erc", "hrp"):
        for cm in ("lw", "sample"):
            for lb in (252, 504):
                grid.append((w, cm, lb))
    # also invvol at 504 (lookback robustness of prod weighting)
    grid.append(("invvol", "sample", 504))

    for (w, cm, lb) in grid:
        key = f"{w}_{cm[0]}{lb}"
        wf = make_weight_fn(w, cm, lb, "rank")
        cells[key] = run_cell(wf, data, f"{w} {cm} {lb}")
        print("done", key)

    # ---- Sharp 2x2 + HRP: selection x weighting (default lw 252 for corr) ----
    twox2 = {}
    twox2["rank_invvol"] = cells["PROD_invvol_s252"]  # prod top-left
    twox2["rank_erc"] = cells["erc_l252"]
    # min-var subset (NEW) x {invvol, erc}; use lw 252 for erc, sample for invvol-weight
    mv_iv = make_weight_fn("invvol", "sample", 252, "minvar", subset_m=3)
    mv_erc = make_weight_fn("erc", "lw", 252, "minvar", subset_m=3)
    twox2["minvar_invvol"] = run_cell(mv_iv, data, "minvar-subset3 + invvol")
    twox2["minvar_erc"] = run_cell(mv_erc, data, "minvar-subset3 + erc")
    twox2["rank_hrp"] = cells["hrp_l252"]

    # ---- serialize cells (strip returns) ----
    def strip(cell):
        c = {k: v for k, v in cell.items() if not k.endswith("_returns")}
        return c
    results["cells"] = {k: strip(v) for k, v in cells.items()}
    results["twox2"] = {k: strip(v) for k, v in twox2.items()}

    # ---- bootstrap + walk-forward for any cell beating baseline on Sharpe AND Calmar (clean) ----
    base_clean = cells["PROD_invvol_s252"]["clean"]
    base_ret = cells["PROD_invvol_s252"]["clean_returns"]
    bSh, bCa = base_clean["Sharpe"], base_clean["Calmar"]
    candidates = {}
    pool = dict(cells)
    pool.update(twox2)
    for key, cell in pool.items():
        if key == "PROD_invvol_s252":
            continue
        cl = cell["clean"]
        if cl["Sharpe"] > bSh and cl["Calmar"] > bCa:
            candidates[key] = cell
    results["beats_baseline_both"] = list(candidates.keys())
    print("candidates beating baseline (Sharpe&Calmar, clean):", list(candidates.keys()))

    results["bootstrap"] = {}
    results["walk_forward"] = {}
    for key, cell in candidates.items():
        bs = paired_block_bootstrap(cell["clean_returns"], base_ret, data.cash)
        results["bootstrap"][key] = bs
        # reconstruct var wf for walk-forward
        # all candidate wfs are in pool with known config; rebuild from label
        # simplest: rerun via stored returns split
        wf_var_returns = cell["clean_returns"]
        # walk-forward via returns directly
        common = base_ret.index.intersection(wf_var_returns.index)
        bR = base_ret.loc[common]; vR = wf_var_returns.loc[common]
        n = len(common); bounds = [0, n // 3, 2 * n // 3, n]
        segs = []
        for i in range(3):
            lo, hi = bounds[i], bounds[i + 1]
            mb = cpm_live.perf_metrics(bR.iloc[lo:hi], data.cash)
            mv = cpm_live.perf_metrics(vR.iloc[lo:hi], data.cash)
            segs.append({
                "start": str(common[lo].date()), "end": str(common[hi - 1].date()),
                "base_Sharpe": mb.get("sharpe"), "var_Sharpe": mv.get("sharpe"),
                "dSharpe": mv.get("sharpe") - mb.get("sharpe"),
                "base_Calmar": mb.get("calmar"), "var_Calmar": mv.get("calmar"),
                "dCalmar": mv.get("calmar") - mb.get("calmar"),
            })
        results["walk_forward"][key] = segs
        print("bootstrap+wf done", key)

    with open(OUT, "w") as f:
        json.dump(results, f, indent=2, default=lambda o: None)
    print("wrote", OUT)
    return results


if __name__ == "__main__":
    main()
