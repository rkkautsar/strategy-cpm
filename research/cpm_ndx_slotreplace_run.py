# -*- coding: utf-8 -*-
"""Run the slot-replacement vs continuous-dial experiment (matched exposure).

Writes research/cpm_ndx_slotreplace_findings.json. See harness for design.
Drop rules: R1 = drop lowest-momentum (SLOT_*), R2 = drop highest-vol (SLOT_*_VOL).
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

from cpm_live import load_panel
import ndx_sleeve_live as ndx
from research.cpm_bootstrap_multimetric import paired_block_bootstrap_mm
from research.cpm_ndx_minvar_cvar import (
    full_metrics, crisis_metrics, annual_turnover, walk_forward, win,
    EXT_START, CLEAN_START, END,
)
from research.cpm_ndx_slotreplace_harness import (
    run_config, exposure_stats, slot_changes_per_year, TARGET_BASKET, WIN_PRIMARY,
)

# 2021 growth-unwind window (the sleeve-wide risk-on co-movement event of interest)
UNWIND_2021 = ("2021-02-12", "2021-05-13")


def unwind_metrics(ret, a=UNWIND_2021[0], b=UNWIND_2021[1]):
    from cpm_live import perf_metrics
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

    configs = ["PROD", "CONT",
               "SLOT_ROUND", "SLOT_FLOOR", "SLOT_CEIL",
               "SLOT_ROUND_VOL", "SLOT_FLOOR_VOL", "SLOT_CEIL_VOL"]

    series_clean, series_ext, results = {}, {}, {}
    for name in configs:
        print(f"running {name} ...", file=sys.stderr)
        r, hist, log = run_config(panel, ndx_panel, name,
                                  target=TARGET_BASKET, window=WIN_PRIMARY)
        sc = win(r, CLEAN_START, end)
        se = win(r, EXT_START, end)
        series_clean[name] = sc
        series_ext[name] = se
        results[name] = {
            "clean": full_metrics(sc, cash),
            "ext": full_metrics(se, cash),
            "crisis": crisis_metrics(se),
            "unwind_2021": unwind_metrics(se),
            "turnover_ann": annual_turnover(hist, CLEAN_START),
            "exposure": exposure_stats(log, CLEAN_START),
            "slot_changes_per_yr": slot_changes_per_year(log, CLEAN_START),
        }
        m = results[name]["clean"]
        ex = results[name]["exposure"]
        uw = results[name]["unwind_2021"]
        print(f"  {name}: Sharpe={m['Sharpe']:.4f} Sortino={m['Sortino']:.4f} "
              f"CVaR={m['CVaR_ratio']:.3f} MaxDD={m['MaxDD']:.4f} CAGR={m['CAGR']:.4f} "
              f"vol={m['vol']:.4f} TO={results[name]['turnover_ann']:.2f} "
              f"meanExp={ex['mean_equity_exposure']:.3f} keptRV={ex['avg_kept_rv']:.3f} "
              f"2021DD={uw['MaxDD']:.4f}", file=sys.stderr)

    # --------------------------- bootstraps ---------------------------
    # each SLOT/CONT vs PROD; each SLOT vs CONT; and R1 vs R2 at matched mapping.
    boot = {}

    def bb(a, b):
        return paired_block_bootstrap_mm(series_clean[a], series_clean[b], cash,
                                         B=2000, block=21, seed=42)

    for name in configs:
        if name == "PROD":
            continue
        print(f"bootstrap {name} vs PROD ...", file=sys.stderr)
        boot[f"{name}_vs_PROD"] = bb(name, "PROD")
    for name in ["SLOT_ROUND", "SLOT_FLOOR", "SLOT_CEIL",
                 "SLOT_ROUND_VOL", "SLOT_FLOOR_VOL", "SLOT_CEIL_VOL"]:
        print(f"bootstrap {name} vs CONT ...", file=sys.stderr)
        boot[f"{name}_vs_CONT"] = bb(name, "CONT")
    for mode in ["ROUND", "FLOOR", "CEIL"]:
        a, b = f"SLOT_{mode}_VOL", f"SLOT_{mode}"
        print(f"bootstrap {a} vs {b} (R2 vs R1) ...", file=sys.stderr)
        boot[f"{a}_vs_{b}"] = bb(a, b)

    # --------------------------- walk-forward ---------------------------
    wf = {}
    for name in configs:
        wf[name] = walk_forward(series_clean[name], cash, 3)

    out = {
        "anchor_note": ("PROD reproduces clean Sharpe ~1.28, MaxDD ~-31.4%. Engine "
                        "identical across configs; CONT and SLOT_* share the SAME "
                        "basket-vol scale signal so average equity exposure is "
                        "~matched. SLOT_* isolate concentration (drop-weakest) vs "
                        "CONT shrink-all. R1=drop lowest-momentum, R2=drop "
                        "highest-trailing-vol."),
        "spec": {"target_basket": TARGET_BASKET, "window": WIN_PRIMARY, "cap": 1.0,
                 "K": 5},
        "window": {"clean": [str(CLEAN_START.date()), str(end.date())],
                   "ext": [str(EXT_START.date()), str(end.date())],
                   "unwind_2021": list(UNWIND_2021)},
        "results": results,
        "bootstrap": boot,
        "walk_forward": wf,
    }
    op = ROOT / "research" / "cpm_ndx_slotreplace_findings.json"
    op.write_text(json.dumps(out, indent=2, default=float))
    print("WROTE", op, file=sys.stderr)
    return out


if __name__ == "__main__":
    main()
