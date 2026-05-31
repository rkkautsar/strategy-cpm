# -*- coding: utf-8 -*-
"""Throwaway research (READ-ONLY re: production): CPM full-factorial INTERACTION grid.

Deepens the OFAT param sweep (cpm_robust_param_sweep.py) into a full Cartesian
grid to expose interaction effects OFAT cannot see.

Convention: mooex (T+1 MOO exact), 10 bps/side, monthly month-end signal.
Clean window 2008-05-30..2026-05-22 (18y); ext 1999-03-10..2026-05-22 (cheap, included).

ANCHOR GATE (must reproduce before analysis):
  cell {K=4, mom=faber_voladj, lookback=504, weighting=invvol}
  => CPM clean Sharpe 1.1910 / MaxDD -12.67% / Calmar 1.0615.

GRID (full Cartesian = 4 x 5 x 2 x 2 = 80 cells):
  Top-K        : {3, 4, 5, 6}
  Momentum fn  : {faber_voladj, 13612U, 12m, 6m, 3m}
  cov/vol lkbk : {252, 504}
  Weighting    : {invvol, equal}
All other knobs held at production (canary HYG-OR-TIP, safe SHV/IEF,
strict-K partial-safe, vol cap, positive-trend screen) -- inherited from
cpm_weights_param / run_series in the sweep harness.

NOTE: under weighting=equal the cov/vol lookback is unused (only inv_vol uses
it), so the two lookback cells are numerically identical there. Kept for a
complete 80-cell Cartesian; flagged in analysis.

Writes research/cpm_grid_interaction_findings.{md,json}. No production files touched.
"""
from __future__ import annotations
import sys, json, itertools
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

import exec_lag_moo_validation_2026_05_30 as H
from cpm_live import load_panel, RISKY_UNIVERSE, SAFE_POOL, CANARY_ASSETS, DEFAULT_CASH
# reuse the parametrized engine + helpers from the OFAT harness
from cpm_robust_param_sweep import (
    run_series, metr, CS, EXT, END, ANCHOR, COST_BASE,
)

KS = [3, 4, 5, 6]
MOMS = ["faber_voladj", "13612U", "12m", "6m", "3m"]
LBS = [252, 504]
WGTS = ["invvol", "equal"]

BASELINE_KEY = ("faber_voladj", 4, 504, "invvol")  # (mom, K, lb, wgt)
ANCHOR_TOL = dict(sharpe=0.01, maxdd=0.01, calmar=0.02)


def pct(arr, q):
    return float(np.percentile(np.asarray(arr, float), q))


def _jsonable(o):
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    raise TypeError(repr(o))


def main():
    panel = load_panel(start=EXT, end=END)
    open_df, close_yf = H.load_open_close()
    intraday = (close_yf / open_df - 1.0).reindex(panel.index)
    overnight = (open_df / close_yf.shift(1) - 1.0).reindex(panel.index)
    cash = panel["SHV"].ffill().pct_change()

    cells = []
    print("Running %d cells (4 K x 5 mom x 2 lb x 2 wgt)...\n" % (len(KS)*len(MOMS)*len(LBS)*len(WGTS)))
    for k, mom, lb, wgt in itertools.product(KS, MOMS, LBS, WGTS):
        s, fb = run_series(panel, intraday, overnight, cost=COST_BASE,
                           top_k=k, lookback=lb, mom=mom, weighting=wgt)
        clean = metr(s, cash, CS, END)
        ext = metr(s, cash, EXT, END)
        cell = {
            "K": k, "mom": mom, "lookback": lb, "weighting": wgt,
            "clean": clean, "ext": ext,
            "label": "K%d/%s/%d/%s" % (k, mom, lb, wgt),
        }
        cells.append(cell)
        print("%-30s clean S=%.4f C=%.4f DD=%.4f | ext S=%.4f"
              % (cell["label"], clean["sharpe"], clean["calmar"], clean["maxdd"], ext["sharpe"]))

    # ---- Anchor gate ----
    base = next(c for c in cells if (c["mom"], c["K"], c["lookback"], c["weighting"]) == BASELINE_KEY)
    bs, bc, bd = base["clean"]["sharpe"], base["clean"]["calmar"], base["clean"]["maxdd"]
    gate_ok = bool(abs(bs - ANCHOR["sharpe"]) <= ANCHOR_TOL["sharpe"]
                   and abs(bd - ANCHOR["maxdd"]) <= ANCHOR_TOL["maxdd"]
                   and abs(bc - ANCHOR["calmar"]) <= ANCHOR_TOL["calmar"])
    print("\nANCHOR GATE baseline K4/faber_voladj/504/invvol: S=%.4f DD=%.4f C=%.4f  expect %.4f/%.4f/%.4f  => %s"
          % (bs, bd, bc, ANCHOR["sharpe"], ANCHOR["maxdd"], ANCHOR["calmar"], "PASS" if gate_ok else "FAIL"))
    if not gate_ok:
        raise SystemExit("ANCHOR GATE FAILED -- aborting analysis (numbers do not reproduce).")

    # ---- Joint distribution ----
    sharpes = [c["clean"]["sharpe"] for c in cells]
    calmars = [c["clean"]["calmar"] for c in cells]
    dds = [c["clean"]["maxdd"] for c in cells]
    n = len(cells)

    def dist(vals):
        a = np.asarray(vals, float)
        return {"median": float(np.median(a)), "iqr": [pct(a, 25), pct(a, 75)],
                "min": float(a.min()), "max": float(a.max()),
                "mean": float(a.mean()), "std": float(a.std(ddof=0))}

    s_dist = dist(sharpes)
    c_dist = dist(calmars)
    s_gt10 = sum(1 for x in sharpes if x > 1.0)
    s_gt11 = sum(1 for x in sharpes if x > 1.1)
    c_gt10 = sum(1 for x in calmars if x > 1.0)
    c_gt11 = sum(1 for x in calmars if x > 1.1)

    # ---- Extremes ----
    by_sharpe = sorted(cells, key=lambda c: c["clean"]["sharpe"])
    by_calmar = sorted(cells, key=lambda c: c["clean"]["calmar"])
    lo_s, hi_s = by_sharpe[0], by_sharpe[-1]
    lo_c, hi_c = by_calmar[0], by_calmar[-1]

    # ---- Baseline placement / selection-on-peak ----
    rank_better = sum(1 for x in sharpes if x > bs)  # how many cells beat baseline
    pctile = 100.0 * (1.0 - rank_better / n)  # baseline's percentile (higher=better)
    is_max = (rank_better == 0)
    # plateau: count cells within 0.02 Sharpe of baseline
    near = [c for c in cells if abs(c["clean"]["sharpe"] - bs) <= 0.02]
    sel_on_peak_med = bs - s_dist["median"]
    sel_on_peak_max = bs - s_dist["max"]

    # ---- Marginal means (main effects) for interaction context ----
    def grp_mean(key):
        out = {}
        for lvl in sorted(set(c[key] for c in cells), key=str):
            vals = [c["clean"]["sharpe"] for c in cells if c[key] == lvl]
            out[str(lvl)] = {"mean": float(np.mean(vals)), "min": float(np.min(vals)),
                             "max": float(np.max(vals)), "n": len(vals)}
        return out
    marg = {k: grp_mean(k) for k in ["K", "mom", "lookback", "weighting"]}

    # ---- Interaction cross-tabs: mom x weighting and K x mom (mean Sharpe) ----
    def crosstab(rk, ck):
        rows = sorted(set(c[rk] for c in cells), key=str)
        colz = sorted(set(c[ck] for c in cells), key=str)
        tab = {}
        for r in rows:
            tab[str(r)] = {}
            for cc in colz:
                vals = [x["clean"]["sharpe"] for x in cells if x[rk] == r and x[ck] == cc]
                tab[str(r)][str(cc)] = float(np.mean(vals)) if vals else None
        return tab
    xtab_mom_wgt = crosstab("mom", "weighting")
    xtab_K_mom = crosstab("K", "mom")

    results = {
        "convention": "mooex", "cost_bps_side": COST_BASE,
        "clean_window": [str(CS.date()), str(END.date())],
        "ext_window": [str(EXT.date()), str(END.date())],
        "anchor": ANCHOR, "anchor_gate_pass": gate_ok,
        "n_cells": n,
        "baseline": {"label": base["label"], "clean": base["clean"], "ext": base["ext"],
                     "percentile": pctile, "is_literal_max": is_max,
                     "n_within_0.02_sharpe": len(near),
                     "n_cells_beating_baseline": rank_better,
                     "selection_on_peak_vs_median": sel_on_peak_med,
                     "selection_on_peak_vs_max": sel_on_peak_max},
        "sharpe_dist": s_dist, "calmar_dist": c_dist,
        "frac_sharpe_gt_1.0": s_gt10 / n, "n_sharpe_gt_1.0": s_gt10,
        "frac_sharpe_gt_1.1": s_gt11 / n, "n_sharpe_gt_1.1": s_gt11,
        "frac_calmar_gt_1.0": c_gt10 / n, "n_calmar_gt_1.0": c_gt10,
        "frac_calmar_gt_1.1": c_gt11 / n, "n_calmar_gt_1.1": c_gt11,
        "extremes": {
            "lowest_sharpe": {"label": lo_s["label"], "sharpe": lo_s["clean"]["sharpe"], "calmar": lo_s["clean"]["calmar"], "maxdd": lo_s["clean"]["maxdd"]},
            "highest_sharpe": {"label": hi_s["label"], "sharpe": hi_s["clean"]["sharpe"], "calmar": hi_s["clean"]["calmar"], "maxdd": hi_s["clean"]["maxdd"]},
            "lowest_calmar": {"label": lo_c["label"], "calmar": lo_c["clean"]["calmar"], "sharpe": lo_c["clean"]["sharpe"], "maxdd": lo_c["clean"]["maxdd"]},
            "highest_calmar": {"label": hi_c["label"], "calmar": hi_c["clean"]["calmar"], "sharpe": hi_c["clean"]["sharpe"], "maxdd": hi_c["clean"]["maxdd"]},
        },
        "marginals_sharpe": marg,
        "crosstab_mom_x_weighting_sharpe": xtab_mom_wgt,
        "crosstab_K_x_mom_sharpe": xtab_K_mom,
        "grid": cells,
    }

    out_json = HERE / "cpm_grid_interaction_findings.json"
    out_json.write_text(json.dumps(results, indent=2, default=_jsonable))
    print("\nWROTE", out_json)

    # quick console summary
    print("\n=== JOINT DIST (clean Sharpe) ===")
    print("median=%.4f IQR=[%.4f,%.4f] min=%.4f max=%.4f" %
          (s_dist["median"], s_dist["iqr"][0], s_dist["iqr"][1], s_dist["min"], s_dist["max"]))
    print("Sharpe>1.0: %d/%d (%.0f%%)  Sharpe>1.1: %d/%d (%.0f%%)" %
          (s_gt10, n, 100*s_gt10/n, s_gt11, n, 100*s_gt11/n))
    print("Calmar>1.0: %d/%d  Calmar>1.1: %d/%d" % (c_gt10, n, c_gt11, n))
    print("BASELINE pctile=%.1f is_max=%s within0.02=%d sel-on-peak(vs med)=%+.4f (vs max)=%+.4f" %
          (pctile, is_max, len(near), sel_on_peak_med, sel_on_peak_max))
    print("LOW S:", lo_s["label"], "%.4f" % lo_s["clean"]["sharpe"], " HIGH S:", hi_s["label"], "%.4f" % hi_s["clean"]["sharpe"])
    print("LOW C:", lo_c["label"], "%.4f" % lo_c["clean"]["calmar"], " HIGH C:", hi_c["label"], "%.4f" % hi_c["clean"]["calmar"])
    return results


if __name__ == "__main__":
    main()
