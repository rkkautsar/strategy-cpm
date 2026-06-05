"""Does a SIMPLE, parameter-free corr-aware SELECTION ("drop the most-redundant
asset so the rest is more diverse") capture the min-var-SUBSET OOS edge WITHOUT
the optimizer complexity?

Throwaway research. Read-only re production. No production files changed; no commit.

Context
-------
Prior study (research/cpm_weighting_corr*) found correlation pays via SELECTION,
not weighting: a MIN-VAR SUBSET(3) selection beats prod on both windows + both
metrics + all 3 sequential OOS segments (P97 bootstrap on Sharpe). But min-var
selection was previously REMOVED from prod for PARSIMONY (single-stage top-4
inverse-vol; complexity not worth the marginal gain). The user wants a SIMPLER,
parameter-free corr-aware selection.

Production CPM (cpm_live.compute_target_weights, verified lines 425-465):
  rank by vol-adjusted Faber (faber / vol_252) -> top-4 -> positive-faber filter
  -> inverse-vol weight (252d cov DIAGONAL only) -> strict-4 partial-safe.
  Correlation enters NOWHERE in prod.

Selection variants (all keep prod rank -> top-4 -> positive filter, then apply
the rule, then INVERSE-VOL weight; everything else byte-identical to prod:
universe / canary / trend / safe / both-252 / mooex T+1 / 10 bps):

  1. PROD            : keep all positive picks (baseline; reproduces anchor).
  2. DROP-REDUNDANT-1: when 4 positive picks, compute each asset's AVG pairwise
                       252d corr to the other 3; DROP the highest (most redundant);
                       inverse-vol weight the remaining 3 at FULL risk budget
                       (renormalize over 3, stay 100% risky -- no safe inject).
                       When <=3 positive picks: unchanged (= prod). PRIMARY.
  3. MIN-CORR-TRIO   : when 4 picks, keep the 3-of-4 with the LOWEST avg pairwise
                       corr; inverse-vol weight; <=3 unchanged. (Near-equivalent
                       to #2; report whether they pick the same trio.)
  4. MIN-VAR-SUBSET  : the complex benchmark that survived OOS (reuse from
                       cpm_weighting_corr.make_weight_fn selection="minvar").

NOTE on full-risk semantics: prod is already 100% risky whenever n_pos == 4
(risky_fraction = min(4,4)/4 = 1.0). The selection rules only act on n_pos == 4
months, so dropping 4->3 at FULL risk is the apples-to-apples comparison (both
prod and challengers are 100% risky there; only the held names differ). This
isolates DIVERSIFICATION from DE-RISKING. The min-var benchmark in
cpm_weighting_corr uses identical full-risk-on-4 semantics, so edge-capture is
like-for-like. Robustness: a partial-safe-on-drop alt (3/4 risky + 1/4 safe) is
also run and its directional effect reported.

Run: .venv/bin/python -m research.cpm_simple_corr_selection
Out: research/cpm_simple_corr_selection_findings.json
"""

from __future__ import annotations

import json
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

from research import cpm_harness as H
import cpm_live
from cpm_live import (
    faber_sma_xs, best_safe, sig_13612U, inv_vol_weights,
    RISKY_UNIVERSE, SAFE_POOL, CANARY_ASSETS, CANARY_RULE, TOP_K_CANDIDATES,
)
from research.cpm_weighting_corr import (
    _ret_window, _risky_weights, _min_var_subset,
    CRISES, _sub_metrics, annualized_turnover, paired_block_bootstrap, run_cell,
    make_weight_fn as make_weight_fn_corr,
)

OUT = Path(__file__).resolve().parent / "cpm_simple_corr_selection_findings.json"


# ---------------- simple corr-aware subset rules ----------------
def _corr_window(close, sig_d, picks, lookback):
    rets = _ret_window(close.loc[:sig_d], picks, lookback)
    if len(rets) < lookback or rets.shape[1] < len(picks):
        return None
    c = rets.corr()
    if c.isna().any().any():
        return None
    return c


def _drop_redundant_1(close, sig_d, picks, lookback, m=3):
    """DROP-REDUNDANT-1: drop the asset with the highest AVG pairwise corr to the
    others. Parameter-free. Leaves a trio when picks==4."""
    if len(picks) <= m:
        return list(picks)
    c = _corr_window(close, sig_d, picks, lookback)
    if c is None:
        return list(picks)
    avg = {}
    for t in picks:
        others = [o for o in picks if o != t]
        avg[t] = float(c.loc[t, others].mean())
    drop = max(avg, key=lambda k: avg[k])
    return [t for t in picks if t != drop]


def _min_corr_trio(close, sig_d, picks, lookback, m=3):
    """MIN-CORR-TRIO: keep the m-subset with the lowest avg pairwise correlation."""
    if len(picks) <= m:
        return list(picks)
    c = _corr_window(close, sig_d, picks, lookback)
    if c is None:
        return list(picks)
    best, best_v = None, np.inf
    for combo in combinations(picks, m):
        sub = c.loc[list(combo), list(combo)].values
        iu = np.triu_indices(m, k=1)
        v = float(sub[iu].mean())
        if v < best_v:
            best_v, best = v, combo
    return list(best) if best else list(picks)


def _top3_by_rank(close, sig_d, picks, lookback, m=3):
    """CONCENTRATION CONTROL: keep the m highest-RANKED (vol-adj Faber) picks,
    dropping the lowest-ranked. `picks` arrives in rank order (descending). No
    correlation used -- isolates the pure 3-vs-4 concentration effect."""
    return list(picks)[:m]


_SUBSET_FN = {
    "rank3": _top3_by_rank,
    "drop1": _drop_redundant_1,
    "mincorr_trio": _min_corr_trio,
    "minvar": _min_var_subset,
}


# ---------------- prod-faithful weight fn with swappable SELECTION ----------------
def make_weight_fn(selection="rank", lookback=None, subset_m=3,
                   partial_safe_on_drop=False, sizing="invvol"):
    """Replicate prod selection + partial-safe, swapping ONLY the subset rule.

    selection: rank (prod, no drop) | drop1 | mincorr_trio | minvar.
    sizing: invvol (cov diagonal, prod) | ew (plain equal-weight, no cov at all).
      EW = 1/n over the kept names, then scaled by risky_fraction.
    partial_safe_on_drop: if True and a drop happens, use strict-4 partial-safe
      (risky_fraction = len(reduced)/4 = 3/4, inject 1/4 safe). Default False =
      full-risk renormalize over the kept trio (PRIMARY).
    """
    lb = lookback or cpm_live.CORR_LOOKBACK_DAYS

    def wf(close_panel, sig_d):
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
        n_pos_canary = sum(1 for s in cscores if s > 0)
        if CANARY_RULE == "any_positive":
            if n_pos_canary == 0:
                return {safe: 1.0}
        elif CANARY_RULE == "all_positive":
            if n_pos_canary < len(cscores):
                return {safe: 1.0}
        else:
            if n_pos_canary <= len(cscores) // 2:
                return {safe: 1.0}

        faber = faber_sma_xs(monthly)
        avail = [t for t in RISKY_UNIVERSE
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

        picks = list(positive)
        dropped = False
        if selection in _SUBSET_FN and len(picks) > subset_m:
            picks = _SUBSET_FN[selection](close_panel, sig_d, picks, lb, subset_m)
            dropped = len(picks) < len(positive)

        # risky fraction: strict-4 semantics on ORIGINAL n positives.
        # PRIMARY: full-risk renormalize over the kept trio when a drop happens
        # (i.e. n_pos==4 -> risky_fraction stays 1.0). partial_safe_on_drop flips
        # this to 3/4 risky + 1/4 safe to test the de-risking alternative.
        if dropped and partial_safe_on_drop:
            risky_fraction = len(picks) / 4.0
        else:
            risky_fraction = min(len(positive), 4) / 4.0
        safe_fraction = 1.0 - risky_fraction

        if sizing == "ew":
            rw = {t: 1.0 / len(picks) for t in picks}
        else:
            rw = _risky_weights(close_panel, sig_d, picks, "invvol", "sample", lb)
        out = {t: w * risky_fraction for t, w in rw.items()}
        if safe_fraction > 0:
            out[safe] = out.get(safe, 0.0) + safe_fraction
        return out

    return wf


# ---------------- subset-agreement diagnostics ----------------
def subset_agreement(data, lb=252, subset_m=3):
    """On selection-active months (n_pos==4), compare which trio drop1 /
    mincorr_trio / minvar each keep. Jaccard + same-subset rates vs each other."""
    panel = data.panel
    sig_dates = panel.resample("ME").last().index
    sig_dates = [d for d in sig_dates if d >= data.clean_start and d <= data.end]
    rows = []
    for d in sig_dates:
        idx = panel.index[panel.index <= d]
        if len(idx) == 0:
            continue
        sd = idx[-1]
        monthly = panel.loc[:sd].resample("ME").last()
        # canary gate
        cscores = []
        for c in CANARY_ASSETS:
            if c in monthly.columns:
                s = sig_13612U(monthly[c])
                if pd.notna(s):
                    cscores.append(s)
        if not cscores or sum(1 for s in cscores if s > 0) == 0:
            continue
        faber = faber_sma_xs(monthly)
        avail = [t for t in RISKY_UNIVERSE
                 if t in faber.index and pd.notna(faber[t])
                 and pd.notna(panel.loc[sd].get(t, np.nan))]
        if not avail:
            continue
        dr = panel[avail].ffill().pct_change()
        scores = {}
        for t in avail:
            v = dr[t].loc[:sd].tail(252).std() * np.sqrt(252)
            if pd.isna(v) or v < 1e-9:
                v = 1.0
            scores[t] = float(faber[t]) / v
        ranked = pd.Series(scores).sort_values(ascending=False)
        top = ranked.iloc[:max(2, min(TOP_K_CANDIDATES, len(ranked)))]
        positive = [t for t in top.index if faber.get(t, -np.inf) > 0]
        if len(positive) != 4:
            continue
        s_d1 = set(_drop_redundant_1(panel, sd, positive, lb, subset_m))
        s_mc = set(_min_corr_trio(panel, sd, positive, lb, subset_m))
        s_mv = set(_min_var_subset(panel, sd, positive, lb, subset_m))
        rows.append((s_d1, s_mc, s_mv))
    n = len(rows)
    if n == 0:
        return {"active_months": 0}

    def cmp(a_key, b_key):
        ai = {"d1": 0, "mc": 1, "mv": 2}[a_key]
        bi = {"d1": 0, "mc": 1, "mv": 2}[b_key]
        same = sum(1 for r in rows if r[ai] == r[bi])
        jac = np.mean([len(r[ai] & r[bi]) / len(r[ai] | r[bi]) for r in rows])
        return {"same": same, "pct_same": same / n, "avg_jaccard": float(jac)}

    return {
        "active_months": n,
        "drop1_vs_mincorr": cmp("d1", "mc"),
        "drop1_vs_minvar": cmp("d1", "mv"),
        "mincorr_vs_minvar": cmp("mc", "mv"),
    }


def walk_forward(base_ret, var_ret, cash):
    common = base_ret.index.intersection(var_ret.index)
    bR = base_ret.loc[common]
    vR = var_ret.loc[common]
    n = len(common)
    bounds = [0, n // 3, 2 * n // 3, n]
    segs = []
    for i in range(3):
        lo, hi = bounds[i], bounds[i + 1]
        mb = cpm_live.perf_metrics(bR.iloc[lo:hi], cash)
        mv = cpm_live.perf_metrics(vR.iloc[lo:hi], cash)
        segs.append({
            "start": str(common[lo].date()), "end": str(common[hi - 1].date()),
            "base_Sharpe": mb.get("sharpe"), "var_Sharpe": mv.get("sharpe"),
            "dSharpe": mv.get("sharpe") - mb.get("sharpe"),
            "base_Calmar": mb.get("calmar"), "var_Calmar": mv.get("calmar"),
            "dCalmar": mv.get("calmar") - mb.get("calmar"),
        })
    return segs


def main():
    data = H.load_data()
    anchor = H.verify_anchor(data=data)
    print("ANCHOR OK:", {k: round(float(v), 4) for k, v in anchor.items() if k in ("Sharpe", "MaxDD", "Calmar")})

    results = {"anchor": {k: float(v) for k, v in anchor.items()}}

    # ---- variant cells (primary: cov lookback 252, full-risk-on-drop) ----
    # PROD stays inv-vol top-4. Each trio-selection rule run with BOTH inv-vol
    # sizing and plain EQUAL-WEIGHT (EW = 1/3, no cov at all).
    variants = {
        "PROD": make_weight_fn("rank", 252, sizing="invvol"),
        "RANK3_IV": make_weight_fn("rank3", 252, sizing="invvol"),
        "RANK3_EW": make_weight_fn("rank3", 252, sizing="ew"),
        "DROP1_IV": make_weight_fn("drop1", 252, sizing="invvol"),
        "DROP1_EW": make_weight_fn("drop1", 252, sizing="ew"),
        "MINCORR_IV": make_weight_fn("mincorr_trio", 252, sizing="invvol"),
        "MINCORR_EW": make_weight_fn("mincorr_trio", 252, sizing="ew"),
        "MINVAR_IV": make_weight_fn("minvar", 252, sizing="invvol"),
        "MINVAR_EW": make_weight_fn("minvar", 252, sizing="ew"),
    }
    cells = {}
    for key, wf in variants.items():
        cells[key] = run_cell(wf, data, key)
        print("done", key, "clean Sharpe", round(cells[key]["clean"]["Sharpe"], 4))

    # ---- robustness: cov lookback 504 (cheap note) ----
    cells504 = {}
    for key, sel in (("PROD", "rank"), ("DROP1", "drop1"), ("MINVAR", "minvar")):
        wf = make_weight_fn(sel, 504)
        cells504[key] = run_cell(wf, data, key + "_504")
        print("done 504", key, "clean Sharpe", round(cells504[key]["clean"]["Sharpe"], 4))

    # ---- robustness: DROP1 partial-safe-on-drop (3/4 risky + 1/4 safe) ----
    drop1_ps = make_weight_fn("drop1", 252, partial_safe_on_drop=True)
    cells_ps = {"DROP1_partialsafe": run_cell(drop1_ps, data, "DROP1_partialsafe")}
    print("done DROP1 partial-safe, clean Sharpe", round(cells_ps["DROP1_partialsafe"]["clean"]["Sharpe"], 4))

    # ---- subset agreement (drop1 vs mincorr_trio vs minvar) ----
    results["subset_agreement_252"] = subset_agreement(data, lb=252)
    print("subset agreement:", results["subset_agreement_252"])

    # ---- bootstrap + walk-forward vs PROD for each challenger ----
    base_clean_ret = cells["PROD"]["clean_returns"]
    results["bootstrap"] = {}
    results["walk_forward"] = {}
    for key in ("RANK3_IV", "RANK3_EW", "DROP1_IV", "DROP1_EW",
                "MINCORR_IV", "MINCORR_EW", "MINVAR_IV", "MINVAR_EW"):
        var_ret = cells[key]["clean_returns"]
        results["bootstrap"][key] = paired_block_bootstrap(var_ret, base_clean_ret, data.cash)
        results["walk_forward"][key] = walk_forward(base_clean_ret, var_ret, data.cash)
        print("bootstrap+wf done", key)

    # ---- CORR-vs-CONCENTRATION: each corr-trio MINUS top-3-by-rank ----
    # decisive test: does correlation add anything beyond pure 3-vs-4 concentration?
    results["corr_vs_concentration"] = {}
    for sizing, r3key in (("IV", "RANK3_IV"), ("EW", "RANK3_EW")):
        base = cells[r3key]["clean_returns"]
        for trio in ("DROP1", "MINCORR", "MINVAR"):
            vk = f"{trio}_{sizing}"
            var_ret = cells[vk]["clean_returns"]
            results["corr_vs_concentration"][f"{vk}_vs_{r3key}"] = {
                "bootstrap": paired_block_bootstrap(var_ret, base, data.cash),
                "walk_forward": walk_forward(base, var_ret, data.cash),
            }
        print("corr-vs-concentration done", sizing)
    # also bootstrap partial-safe drop1
    results["bootstrap"]["DROP1_partialsafe"] = paired_block_bootstrap(
        cells_ps["DROP1_partialsafe"]["clean_returns"], base_clean_ret, data.cash)
    results["walk_forward"]["DROP1_partialsafe"] = walk_forward(
        base_clean_ret, cells_ps["DROP1_partialsafe"]["clean_returns"], data.cash)

    def strip(cell):
        return {k: v for k, v in cell.items() if not k.endswith("_returns")}

    results["cells"] = {k: strip(v) for k, v in cells.items()}
    results["cells_504"] = {k: strip(v) for k, v in cells504.items()}
    results["cells_partialsafe"] = {k: strip(v) for k, v in cells_ps.items()}

    with open(OUT, "w") as f:
        json.dump(results, f, indent=2, default=lambda o: None)
    print("wrote", OUT)
    return results


if __name__ == "__main__":
    main()
