# -*- coding: utf-8 -*-
"""Run the NDX breadth x de-risk-method sweep. Writes
research/cpm_ndx_breadth_findings.json (+ a turnover table printed to stderr).

9 cells = N{5,8,10} x method{NONE, CONT, SLOT(drop-low-mom round)}.
Headline = turnover/yr + #position-change-events/yr per cell. See harness.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cpm_live import load_panel, perf_metrics
import ndx_sleeve_live as ndx
from research.cpm_bootstrap_multimetric import paired_block_bootstrap_mm
from research.cpm_ndx_minvar_cvar import (
    full_metrics, crisis_metrics, walk_forward, win,
    EXT_START, CLEAN_START, END,
)
from research.cpm_ndx_breadth_harness import (
    run_cell, turnover_events, slot_changes_per_year, exposure_stats,
    TARGET_BASKET, WIN_PRIMARY,
)

UNWIND_2021 = ("2021-02-12", "2021-05-13")
COVID = ("2020-02-19", "2020-04-30")
NS = [5, 8, 10]
METHODS = ["NONE", "CONT", "SLOT"]


def window_metrics(ret, a, b):
    w = ret.loc[(ret.index >= pd.Timestamp(a)) & (ret.index <= pd.Timestamp(b))]
    if len(w) < 5:
        return None
    m = perf_metrics(w, None)
    cum = float((1.0 + w).prod() - 1.0)
    return {"MaxDD": m.get("max_drawdown"), "cum_return": cum, "n_days": len(w)}


def main():
    panel = load_panel(start=EXT_START, end=END)
    end = min(END, panel.index[-1])
    ndx_panel = ndx.load_ndx_panel()
    cash = panel["SHV"].ffill().pct_change().dropna()

    series_clean, series_ext, results = {}, {}, {}
    for N in NS:
        for method in METHODS:
            key = f"{method}_N{N}"
            print(f"running {key} ...", file=sys.stderr)
            r, hist, log = run_cell(panel, ndx_panel, method, N,
                                    target=TARGET_BASKET, window=WIN_PRIMARY)
            sc = win(r, CLEAN_START, end)
            se = win(r, EXT_START, end)
            series_clean[key] = sc
            series_ext[key] = se
            te = turnover_events(hist, CLEAN_START)
            results[key] = {
                "N": N, "method": method,
                "clean": full_metrics(sc, cash),
                "ext": full_metrics(se, cash),
                "crisis": crisis_metrics(se),
                "unwind_2021": window_metrics(se, *UNWIND_2021),
                "covid_2020": window_metrics(se, *COVID),
                "turnover_ann": te["turnover_ann"],
                "pos_change_events_yr": te["pos_change_events_yr"],
                "name_flip_events_yr": te["name_flip_events_yr"],
                "slot_changes_per_yr": slot_changes_per_year(log, CLEAN_START),
                "exposure": exposure_stats(log, CLEAN_START),
            }
            m = results[key]["clean"]
            ex = results[key]["exposure"]
            print(f"  {key}: Sharpe={m['Sharpe']:.3f} Sortino={m['Sortino']:.3f} "
                  f"CVaR={m['CVaR_ratio']:.3f} MaxDD={m['MaxDD']:.3f} CAGR={m['CAGR']:.3f} "
                  f"vol={m['vol']:.3f} TO={te['turnover_ann']:.2f} "
                  f"posEv={te['pos_change_events_yr']:.1f} flips={te['name_flip_events_yr']:.1f} "
                  f"meanExp={ex['mean_equity_exposure']:.3f}", file=sys.stderr)

    # --------------------------- turnover table (headline) ----------------------
    def cell(metric):
        rows = []
        for N in NS:
            row = {"N": N}
            for method in METHODS:
                row[method] = results[f"{method}_N{N}"][metric]
            rows.append(row)
        return rows

    tables = {
        "turnover_ann": cell("turnover_ann"),
        "pos_change_events_yr": cell("pos_change_events_yr"),
        "name_flip_events_yr": cell("name_flip_events_yr"),
        "Sharpe": [{"N": N, **{m: results[f"{m}_N{N}"]["clean"]["Sharpe"] for m in METHODS}} for N in NS],
        "MaxDD": [{"N": N, **{m: results[f"{m}_N{N}"]["clean"]["MaxDD"] for m in METHODS}} for N in NS],
        "CAGR": [{"N": N, **{m: results[f"{m}_N{N}"]["clean"]["CAGR"] for m in METHODS}} for N in NS],
    }

    # --------------------------- bootstraps ---------------------------
    boot = {}

    def bb(a, b):
        return paired_block_bootstrap_mm(series_clean[a], series_clean[b], cash,
                                         B=2000, block=21, seed=42)

    # (1) within each N: SLOT vs CONT (granularity / convergence)
    for N in NS:
        print(f"bootstrap SLOT_N{N} vs CONT_N{N} ...", file=sys.stderr)
        boot[f"SLOT_N{N}_vs_CONT_N{N}"] = bb(f"SLOT_N{N}", f"CONT_N{N}")
    # (2) breadth effect (no vol-target): NONE_N{8,10} vs NONE_N5 (== PROD anchor)
    for N in [8, 10]:
        print(f"bootstrap NONE_N{N} vs NONE_N5 ...", file=sys.stderr)
        boot[f"NONE_N{N}_vs_NONE_N5"] = bb(f"NONE_N{N}", "NONE_N5")
    # (3) breadth effect WITH vol-target: CONT/SLOT_N{8,10} vs same method N5
    for method in ["CONT", "SLOT"]:
        for N in [8, 10]:
            print(f"bootstrap {method}_N{N} vs {method}_N5 ...", file=sys.stderr)
            boot[f"{method}_N{N}_vs_{method}_N5"] = bb(f"{method}_N{N}", f"{method}_N5")
    # (4) de-risk vs none within each N (does vol-target help at this breadth)
    for N in NS:
        for method in ["CONT", "SLOT"]:
            print(f"bootstrap {method}_N{N} vs NONE_N{N} ...", file=sys.stderr)
            boot[f"{method}_N{N}_vs_NONE_N{N}"] = bb(f"{method}_N{N}", f"NONE_N{N}")

    # --------------------------- walk-forward (all cells) ---------------------------
    wf = {key: walk_forward(series_clean[key], cash, 3) for key in series_clean}

    out = {
        "anchor_note": ("NONE_N5 reproduces the PROD top-5 EW anchor (same gate/"
                        "selection, scale=1). Engine identical across cells; CONT "
                        "and SLOT share the SAME basket-vol scale signal so exposure "
                        "is matched WITHIN each N. SLOT = discrete drop-lowest-"
                        "momentum, n=round(scale*N). Cached dataset; absolute levels "
                        "may differ slightly from prod refresh -- apples-to-apples "
                        "across cells via identical engine."),
        "spec": {"target_basket": TARGET_BASKET, "window": WIN_PRIMARY, "cap": 1.0,
                 "Ns": NS, "methods": METHODS},
        "window": {"clean": [str(CLEAN_START.date()), str(end.date())],
                   "ext": [str(EXT_START.date()), str(end.date())],
                   "unwind_2021": list(UNWIND_2021), "covid_2020": list(COVID)},
        "results": results,
        "tables": tables,
        "bootstrap": boot,
        "walk_forward": wf,
    }
    op = ROOT / "research" / "cpm_ndx_breadth_findings.json"
    op.write_text(json.dumps(out, indent=2, default=float))

    # pretty turnover table to stderr
    print("\n=== TURNOVER/YR (rows N, cols method) ===", file=sys.stderr)
    for row in tables["turnover_ann"]:
        print(f"  N={row['N']:>2}  NONE={row['NONE']:.2f}  CONT={row['CONT']:.2f}  SLOT={row['SLOT']:.2f}", file=sys.stderr)
    print("=== POSITION-CHANGE EVENTS/YR ===", file=sys.stderr)
    for row in tables["pos_change_events_yr"]:
        print(f"  N={row['N']:>2}  NONE={row['NONE']:.1f}  CONT={row['CONT']:.1f}  SLOT={row['SLOT']:.1f}", file=sys.stderr)
    print("WROTE", op, file=sys.stderr)
    return out


if __name__ == "__main__":
    main()
