"""CONCENTRATION-SWEEP COMPLETENESS: 2-of-4 min-var subset. Does MORE
concentration (hold 2 of the top-4 positive picks, minimizing EW portfolio
variance) beat prod and/or improve on the 3-of-4 min-var winner, or does it
OVER-CONCENTRATE (lose breadth/momentum, deeper crisis drawdowns)?

Throwaway research. Read-only re production. No production files changed; no
commit. Companion to cpm_simple_corr_selection / cpm_poolsize_sweep /
cpm_weighting_corr (this reuses their engine + math byte-for-byte).

Context
-------
Concentration sweep so far (prod top-4 -> 3-of-4 -> 2-of-4):
  - PROD top-4 inv-vol: anchor Sharpe 1.1658 (clean, both-252, mooex, 10bps).
  - 3-of-4 min-var is the ONLY config beating prod: clean ~1.2414 full-risk IV /
    ~1.2631 partial-safe IV, P0.91-0.92 bootstrap, 3/3 walk-forward positive,
    CI spans 0 (low ceiling -> hold the bar).
  - top-3-by-rank (concentration WITHOUT corr) cratered ~0.95 -> the lever is
    vol+corr selection, not the holding count alone.
An earlier CPM iteration actually used 2-of-4 min-var, so we test it for
completeness: does extra concentration help further or over-concentrate?

2-of-4 min-var = pick the 2 of the top-4 positive picks that minimize EW (1/2,1/2)
portfolio variance over the 252d cov window (m=2 in _min_var_subset). Crossed with:
  - sizing: inverse-vol (IV, prod cov-diagonal) AND equal-weight (EW = 50/50).
  - safe convention:
      PARTIAL-SAFE = prod strict-4 native -> n_picks=2 -> risky_fraction =
        min(2,4)/4 = 0.50 (two risky assets totalling 50% + 50% safe).
      FULL-RISK   = renormalize 100% across the two picks (risky_fraction = 1.0).
=> 4 cells: 2of4 minvar {partial-safe, full-risk} x {IV, EW}.

Everything else byte-identical to prod: universe / canary / trend / safe /
both-252 / mooex T+1 / 10 bps. Engine via research.cpm_harness.

References reproduced for head-to-head: PROD (compute_target_weights, anchor),
3-of-4 min-var IV {full-risk, partial-safe}.

Run: .venv/bin/python -m research.cpm_2of4_minvar
Out: research/cpm_2of4_minvar_findings.json (+ findings.md written by hand)
"""

from __future__ import annotations

import json
from pathlib import Path

from research import cpm_harness as H
import cpm_live
from cpm_live import compute_target_weights
from research.cpm_weighting_corr import paired_block_bootstrap, run_cell
from research.cpm_poolsize_sweep import make_pool_weight_fn

OUT = Path(__file__).resolve().parent / "cpm_2of4_minvar_findings.json"


def walk_forward(base_ret, var_ret, cash):
    """3 sequential segments; var-minus-base Sharpe/Calmar per segment."""
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
    print("ANCHOR OK:", {k: round(float(v), 4) for k, v in anchor.items()
                         if k in ("Sharpe", "MaxDD", "Calmar")})

    results = {"anchor": {k: float(v) for k, v in anchor.items()}}

    # PROD adapter: compute_target_weights returns a tuple (dict, ...); the
    # turnover helper calls the weight fn directly and needs a plain dict.
    def prod_wf(close_panel, sig_d):
        return H._call_weight_fn(compute_target_weights, close_panel, sig_d)

    # ---- reference cells ----
    refs = {
        # PROD via the real production weight fn (reproduces anchor exactly).
        "PROD": prod_wf,
        # 3-of-4 min-var IV, both safe conventions (prior concentration-sweep winner).
        "3of4_minvar_IV_fullrisk":
            make_pool_weight_fn(4, 3, "minvar", "invvol", partial_safe=False),
        "3of4_minvar_IV_partialsafe":
            make_pool_weight_fn(4, 3, "minvar", "invvol", partial_safe=True),
    }

    # ---- 2-of-4 min-var: 4 cells ----
    cells_2of4 = {
        "2of4_minvar_IV_fullrisk":
            make_pool_weight_fn(4, 2, "minvar", "invvol", partial_safe=False),
        "2of4_minvar_IV_partialsafe":
            make_pool_weight_fn(4, 2, "minvar", "invvol", partial_safe=True),
        "2of4_minvar_EW_fullrisk":
            make_pool_weight_fn(4, 2, "minvar", "ew", partial_safe=False),
        "2of4_minvar_EW_partialsafe":
            make_pool_weight_fn(4, 2, "minvar", "ew", partial_safe=True),
    }

    all_wf = dict(refs)
    all_wf.update(cells_2of4)

    cells = {}
    for key, wf in all_wf.items():
        cells[key] = run_cell(wf, data, key)
        print("done", key, "clean Sharpe", round(cells[key]["clean"]["Sharpe"], 4),
              "MaxDD", round(cells[key]["clean"]["MaxDD"], 4),
              "turnover", round(cells[key]["turnover_ann"], 3))

    prod_ret = cells["PROD"]["clean_returns"]

    # ---- bootstrap + walk-forward: each 2-of-4 cell vs PROD ----
    results["bootstrap_vs_prod"] = {}
    results["walk_forward_vs_prod"] = {}
    for key in cells_2of4:
        var_ret = cells[key]["clean_returns"]
        results["bootstrap_vs_prod"][key] = paired_block_bootstrap(
            var_ret, prod_ret, data.cash)
        results["walk_forward_vs_prod"][key] = walk_forward(
            prod_ret, var_ret, data.cash)
        print("vs PROD bootstrap+wf done", key)

    # ---- head-to-head: 2-of-4 vs 3-of-4 (matched convention+sizing) ----
    # var = 2-of-4, base = 3-of-4; positive dSharpe => extra concentration helps.
    h2h_pairs = {
        "2of4_IV_fullrisk_vs_3of4_IV_fullrisk":
            ("2of4_minvar_IV_fullrisk", "3of4_minvar_IV_fullrisk"),
        "2of4_IV_partialsafe_vs_3of4_IV_partialsafe":
            ("2of4_minvar_IV_partialsafe", "3of4_minvar_IV_partialsafe"),
        # best-2of4 (by clean Sharpe) vs best-3of4 reference is added below.
    }
    # pick best 2-of-4 and best 3-of-4 by clean Sharpe for an overall head-to-head
    best_2of4 = max(cells_2of4, key=lambda k: cells[k]["clean"]["Sharpe"])
    best_3of4 = max(
        ("3of4_minvar_IV_fullrisk", "3of4_minvar_IV_partialsafe"),
        key=lambda k: cells[k]["clean"]["Sharpe"])
    h2h_pairs[f"BEST_{best_2of4}_vs_BEST_{best_3of4}"] = (best_2of4, best_3of4)

    results["head_to_head_2of4_vs_3of4"] = {}
    for label, (vkey, bkey) in h2h_pairs.items():
        var_ret = cells[vkey]["clean_returns"]
        base_ret = cells[bkey]["clean_returns"]
        results["head_to_head_2of4_vs_3of4"][label] = {
            "var": vkey, "base": bkey,
            "bootstrap": paired_block_bootstrap(var_ret, base_ret, data.cash),
            "walk_forward": walk_forward(base_ret, var_ret, data.cash),
        }
        print("h2h done", label)

    results["best_2of4"] = best_2of4
    results["best_3of4"] = best_3of4

    def strip(cell):
        return {k: v for k, v in cell.items() if not k.endswith("_returns")}

    results["cells"] = {k: strip(v) for k, v in cells.items()}

    with open(OUT, "w") as f:
        json.dump(results, f, indent=2, default=lambda o: None)
    print("wrote", OUT)
    return results


if __name__ == "__main__":
    main()
