"""POOL-SIZE SWEEP: decouple DIVERSIFICATION (pool width) from CONCENTRATION
(holding count). "Widen the candidate pool, drop the redundant one, KEEP the
holding count."

Throwaway research. Read-only re production. No production files changed; no commit.

Context
-------
Prior 3-of-4 study found: (1) 3-vs-4 CONCENTRATION ALONE HURTS (top-3-by-rank
0.96 << prod top-4 1.17); the lever is WHICH assets, not how many. (2) corr-ONLY
selection (drop-1 == min-corr) is within-noise of prod; only MIN-VAR (vol+corr)
selection beats prod (clean ~1.26, P97-98, both windows, all 3 OOS, lower
turnover). (3) min-var historically dropped for PARSIMONY.

This study tests the "widen pool, drop redundant one, keep holding count" idea.
Prod = top-4 of the 8-asset universe (TOP_K_CANDIDATES=4), rank by vol-adj Faber.

Configs (everything else byte-identical to prod: universe / canary / trend / safe
/ both-252 / mooex T+1 / 10 bps; positive-faber filter still applies). Each cell
parameterized by (pool_k = rank pool width, hold_n = names held, selection,
sizing).

  - PROD          : pool=4, hold=4, rank, inv-vol      (baseline, reproduces anchor)
  - 4of5_minvar   : pool=5, hold=4, MIN-VAR subset     (PRIMARY: pure diversification)
  - 4of5_drop1    : pool=5, hold=4, corr-only drop-1   (corr-only comparison)
  - 4of5_rank     : pool=5, hold=4, top-4-by-rank      (CONTROL: wider pool alone)
  - 3of4_minvar   : pool=4, hold=3, MIN-VAR subset     (= prior winner, more concentrated)
  - 3of4_rank     : pool=4, hold=3, top-3-by-rank      (CONTROL: concentration alone)
  - 5of6_minvar   : pool=6, hold=5, MIN-VAR subset     (less concentrated)
  - 5of6_rank     : pool=6, hold=5, top-5-by-rank      (CONTROL)

Each non-prod config run with BOTH inv-vol and equal-weight (EW) sizing.

RISKY-FRACTION (partial-safe) SEMANTICS -- stated clearly
---------------------------------------------------------
PRIMARY = FULL-RISK RENORMALIZE: when the rank pool yields >= hold_n positives,
hold exactly hold_n names and run them at FULL risk (risky_fraction = 1.0,
weights renormalized over the held names). When positives < hold_n (rare
transition months), hold all positives and fall back to prod strict-4 partial-
safe (risky_fraction = min(n_pos, 4)/4, inject safe).

This makes PROD identical to the production anchor (4 positives -> risky 1.0;
<4 -> prod partial-safe) AND makes 3of4_minvar identical to the prior 3-of-4
min-var winner (full-risk-on-drop). It isolates DIVERSIFICATION (which names)
from DE-RISKING (how much risk) everywhere.

ALTERNATIVE (noted, run for 3of4/4of5/5of6 minvar) = PARTIAL-SAFE:
risky_fraction = min(hold_n, 4)/4 always. For 3-of-4 -> 0.75 risky + 0.25 safe;
for 4-of-5 / 5-of-6 -> 1.0 (same as primary in the common case).

Run: .venv/bin/python -m research.cpm_poolsize_sweep
Out: research/cpm_poolsize_sweep_findings.json
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from research import cpm_harness as H
import cpm_live
from cpm_live import (
    faber_sma_xs, best_safe, sig_13612U,
    RISKY_UNIVERSE, SAFE_POOL, CANARY_ASSETS, CANARY_RULE,
)
from research.cpm_weighting_corr import (
    _risky_weights, _min_var_subset,
    CRISES, paired_block_bootstrap, run_cell,
)
from research.cpm_simple_corr_selection import (
    _drop_redundant_1, _min_corr_trio,
)

OUT = Path(__file__).resolve().parent / "cpm_poolsize_sweep_findings.json"


# ---------------- selection rules (all return a subset of `picks` of size hold_n) ----------------
def _select(close, sig_d, picks, lookback, hold_n, rule):
    """picks arrives in rank order (descending vol-adj Faber)."""
    if len(picks) <= hold_n:
        return list(picks)
    if rule == "rank":
        return list(picks)[:hold_n]
    if rule == "minvar":
        return _min_var_subset(close, sig_d, picks, lookback, hold_n)
    if rule == "drop1":
        # corr-only: iteratively drop the single most-redundant until hold_n left
        cur = list(picks)
        while len(cur) > hold_n:
            nxt = _drop_redundant_1(close, sig_d, cur, lookback, len(cur) - 1)
            if len(nxt) >= len(cur):
                break
            cur = nxt
        return cur
    if rule == "mincorr":
        return _min_corr_trio(close, sig_d, picks, lookback, hold_n)
    raise ValueError(rule)


def make_pool_weight_fn(pool_k, hold_n, rule="rank", sizing="invvol",
                        lookback=None, partial_safe=False):
    """Prod-faithful weight fn with parameterized pool width + holding count.

    pool_k : rank pool width (top-K candidates).
    hold_n : names to hold after the selection rule.
    rule   : rank | minvar | drop1 | mincorr.
    sizing : invvol (prod, cov diagonal) | ew (1/hold_n).
    partial_safe : False = PRIMARY full-risk renormalize (risky 1.0 when pool has
      >= hold_n positives); True = ALTERNATIVE risky_fraction = min(hold_n,4)/4.
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
        top_k = max(2, min(pool_k, len(ranked)))
        top = ranked.iloc[:top_k]
        positive = [t for t in top.index if faber.get(t, -np.inf) > 0]
        if len(positive) == 0:
            return {safe: 1.0}

        n_pos = len(positive)
        if n_pos >= hold_n:
            picks = _select(close_panel, sig_d, list(positive), lb, hold_n, rule)
            if partial_safe:
                risky_fraction = min(hold_n, 4) / 4.0
            else:
                risky_fraction = 1.0  # full-risk renormalize over held names
        else:
            # transition month: fewer positives than target hold -> prod partial-safe
            picks = list(positive)
            risky_fraction = min(n_pos, 4) / 4.0
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

    # ---- config table ----
    # (key, pool_k, hold_n, rule, sizing, partial_safe)
    cfgs = [
        ("PROD",          4, 4, "rank",   "invvol", False),
        ("4of5_minvar_IV", 5, 4, "minvar", "invvol", False),
        ("4of5_minvar_EW", 5, 4, "minvar", "ew",     False),
        ("4of5_drop1_IV",  5, 4, "drop1",  "invvol", False),
        ("4of5_drop1_EW",  5, 4, "drop1",  "ew",     False),
        ("4of5_rank_IV",   5, 4, "rank",   "invvol", False),
        ("4of5_rank_EW",   5, 4, "rank",   "ew",     False),
        ("3of4_minvar_IV", 4, 3, "minvar", "invvol", False),
        ("3of4_minvar_EW", 4, 3, "minvar", "ew",     False),
        ("3of4_rank_IV",   4, 3, "rank",   "invvol", False),
        ("3of4_rank_EW",   4, 3, "rank",   "ew",     False),
        ("5of6_minvar_IV", 6, 5, "minvar", "invvol", False),
        ("5of6_minvar_EW", 6, 5, "minvar", "ew",     False),
        ("5of6_rank_IV",   6, 5, "rank",   "invvol", False),
        ("5of6_rank_EW",   6, 5, "rank",   "ew",     False),
        # partial-safe alternatives (noted)
        ("3of4_minvar_IV_psafe", 4, 3, "minvar", "invvol", True),
        ("4of5_minvar_IV_psafe", 5, 4, "minvar", "invvol", True),
        ("5of6_minvar_IV_psafe", 6, 5, "minvar", "invvol", True),
    ]

    cells = {}
    for key, pk, hn, rule, sizing, psafe in cfgs:
        wf = make_pool_weight_fn(pk, hn, rule, sizing, partial_safe=psafe)
        cells[key] = run_cell(wf, data, key)
        print("done", key, "clean Sharpe", round(cells[key]["clean"]["Sharpe"], 4),
              "ext Sharpe", round(cells[key]["ext"]["Sharpe"], 4),
              "turn", round(cells[key]["turnover_ann"], 3))

    # ---- bootstrap + walk-forward vs PROD for each challenger ----
    base_ret = cells["PROD"]["clean_returns"]
    results["bootstrap_vs_prod"] = {}
    results["walk_forward_vs_prod"] = {}
    for key in cells:
        if key == "PROD":
            continue
        var_ret = cells[key]["clean_returns"]
        results["bootstrap_vs_prod"][key] = paired_block_bootstrap(var_ret, base_ret, data.cash)
        results["walk_forward_vs_prod"][key] = walk_forward(base_ret, var_ret, data.cash)
        print("bs+wf vs prod done", key)

    # ---- KEY: 4of5_minvar vs 3of4_minvar (does keeping 4 preserve the edge?) ----
    results["bootstrap_4of5_vs_3of4"] = {}
    results["walk_forward_4of5_vs_3of4"] = {}
    for sizing in ("IV", "EW"):
        a = cells[f"4of5_minvar_{sizing}"]["clean_returns"]
        b = cells[f"3of4_minvar_{sizing}"]["clean_returns"]
        results["bootstrap_4of5_vs_3of4"][sizing] = paired_block_bootstrap(a, b, data.cash)
        results["walk_forward_4of5_vs_3of4"][sizing] = walk_forward(b, a, data.cash)
        print("4of5 vs 3of4 done", sizing)

    # ---- minvar vs corr-only drop1 at the wider pool (question d) ----
    results["bootstrap_minvar_vs_drop1_4of5"] = {}
    for sizing in ("IV", "EW"):
        a = cells[f"4of5_minvar_{sizing}"]["clean_returns"]
        b = cells[f"4of5_drop1_{sizing}"]["clean_returns"]
        results["bootstrap_minvar_vs_drop1_4of5"][sizing] = paired_block_bootstrap(a, b, data.cash)
        print("minvar vs drop1 done", sizing)

    def strip(cell):
        return {k: v for k, v in cell.items() if not k.endswith("_returns")}

    results["cells"] = {k: strip(v) for k, v in cells.items()}

    with open(OUT, "w") as f:
        json.dump(results, f, indent=2, default=lambda o: None)
    print("wrote", OUT)
    return results


if __name__ == "__main__":
    main()
