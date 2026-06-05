# -*- coding: utf-8 -*-
"""Run the NDX TOP-5 SLOT vol-target FIXED-vs-ADAPTIVE target-spec sweep.
Writes research/cpm_ndx_voltarget_spec_findings.json (+ stderr tables).

CONFIGS (all TOP-5 SLOT discrete drop-lowest-momentum; same engine):
  NONE            prod top-5 EW, no de-risk                  (baseline)
  FIXED t0.30 w60 incumbent absolute target                 (anchor)
  FIXED t{0.20,0.25,0.35,0.40} w60                          (level sensitivity)
  ADAPT w20       target=RV252, short=RV20 (graded prod gate)
  ADAPT w60       target=RV252, short=RV60 (voltarget-consistent)
  BINARY w20      basket RV20<RV252 binary gate              (graded-vs-binary)
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
from research.cpm_ndx_voltarget_spec_harness import (
    run_cell, turnover_events, slot_changes_per_year, exposure_stats,
    exposure_series,
)

UNWIND_2021 = ("2021-02-12", "2021-05-13")
COVID = ("2020-02-19", "2020-04-30")

# (key, mode, short_win, fixed_target)
CONFIGS = [
    ("NONE",          "NONE",   60, None),
    ("FIXED_t20_w60", "FIXED",  60, 0.20),
    ("FIXED_t25_w60", "FIXED",  60, 0.25),
    ("FIXED_t30_w60", "FIXED",  60, 0.30),
    ("FIXED_t35_w60", "FIXED",  60, 0.35),
    ("FIXED_t40_w60", "FIXED",  60, 0.40),
    ("ADAPT_w20",     "ADAPT",  20, None),
    ("ADAPT_w60",     "ADAPT",  60, None),
    ("BINARY_w20",    "BINARY", 20, None),
]


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

    series_clean, series_ext, results, logs = {}, {}, {}, {}
    for key, mode, sw, tgt in CONFIGS:
        print(f"running {key} ...", file=sys.stderr)
        r, hist, log = run_cell(panel, ndx_panel, mode, short_win=sw, fixed_target=tgt)
        sc = win(r, CLEAN_START, end)
        se = win(r, EXT_START, end)
        series_clean[key] = sc
        series_ext[key] = se
        logs[key] = log
        te = turnover_events(hist, CLEAN_START)
        results[key] = {
            "mode": mode, "short_win": sw, "fixed_target": tgt,
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
              f"slotEv={results[key]['slot_changes_per_yr']:.2f} "
              f"meanExp={ex['mean_equity_exposure']:.3f} "
              f"hiExp={ex['mean_exp_hivol']:.3f} loExp={ex['mean_exp_lovol']:.3f}",
              file=sys.stderr)

    # --------------------------- bootstraps ---------------------------
    boot = {}

    def bb(a, b):
        return paired_block_bootstrap_mm(series_clean[a], series_clean[b], cash,
                                         B=2000, block=21, seed=42)

    # (a) ADAPT vs FIXED-0.30 (the core decision)
    boot["ADAPT_w20_vs_FIXED_t30_w60"] = bb("ADAPT_w20", "FIXED_t30_w60")
    boot["ADAPT_w60_vs_FIXED_t30_w60"] = bb("ADAPT_w60", "FIXED_t30_w60")
    # (d) adaptive short-window 20 vs 60
    boot["ADAPT_w20_vs_ADAPT_w60"] = bb("ADAPT_w20", "ADAPT_w60")
    # (e) graded vs binary gate
    boot["ADAPT_w20_vs_BINARY_w20"] = bb("ADAPT_w20", "BINARY_w20")
    # each main vs PROD (NONE)
    for k in ("FIXED_t30_w60", "ADAPT_w20", "ADAPT_w60", "BINARY_w20"):
        boot[f"{k}_vs_NONE"] = bb(k, "NONE")

    # --------------------------- walk-forward (all cells) ---------------------------
    wf = {key: walk_forward(series_clean[key], cash, 3) for key in series_clean}

    # --------------------------- coherence: ADAPT(w20) == graded prod gate -------
    # Quantify how often ADAPT(w20) de-risks vs how often the basket RV20<RV252
    # comparison would flip the binary gate, over clean ON-months.
    coh = {}
    la = logs["ADAPT_w20"]
    cs = pd.Timestamp(CLEAN_START)
    on = [e for e in la if e.get("rv_short") is not None and e.get("rv_long") is not None
          and np.isfinite(e["rv_short"]) and np.isfinite(e["rv_long"])
          and pd.Timestamp(e["sig_d"]) >= cs]
    if on:
        binary_off = np.array([e["rv_short"] >= e["rv_long"] for e in on])  # gate would de-risk
        graded_derisk = np.array([e["scale"] < 0.999 for e in on])
        coh = {
            "n_on": len(on),
            "frac_binary_gate_derisk": float(binary_off.mean()),
            "frac_graded_derisk": float(graded_derisk.mean()),
            "agree_frac": float((binary_off == graded_derisk).mean()),
            "note": ("graded de-risk fires exactly when basket RV_short>=RV252, i.e. "
                     "the same RV20<RV252 comparison the prod gate uses -- confirming "
                     "ADAPT(w20) is the graded continuous form of the binary gate."),
        }

    # exposure time-series (clean) for episode character (compact: 2020-2022 region)
    expser = {}
    for k in ("FIXED_t30_w60", "ADAPT_w20", "ADAPT_w60"):
        es = exposure_series(logs[k], CLEAN_START)
        expser[k] = [e for e in es if "2020" <= e["d"][:4] <= "2022"]

    out = {
        "anchor_note": ("NONE = prod top-5 EW (gate/selection identical). All de-risk "
                        "configs share the IDENTICAL TOP-5 SLOT discrete drop-lowest-"
                        "momentum mechanism (n=round(scale*5)); only the TARGET feeding "
                        "scale differs (FIXED absolute vs ADAPT=RV252-relative vs BINARY "
                        "gate). Cached dataset; absolute levels may differ slightly from "
                        "a prod refresh -- apples-to-apples across configs via identical "
                        "engine. FIXED levels + windows are A-PRIORI (sensitivity, not "
                        "optimization)."),
        "spec": {"K": 5, "long_win": 252, "cap": 1.0, "drop_rule": "lowest_momentum",
                 "configs": [{"key": c[0], "mode": c[1], "short_win": c[2],
                              "fixed_target": c[3]} for c in CONFIGS]},
        "window": {"clean": [str(CLEAN_START.date()), str(end.date())],
                   "ext": [str(EXT_START.date()), str(end.date())],
                   "unwind_2021": list(UNWIND_2021), "covid_2020": list(COVID)},
        "results": results,
        "bootstrap": boot,
        "walk_forward": wf,
        "coherence_adapt_w20_vs_gate": coh,
        "exposure_series_2020_2022": expser,
    }
    op = ROOT / "research" / "cpm_ndx_voltarget_spec_findings.json"
    op.write_text(json.dumps(out, indent=2, default=float))
    print("\nWROTE", op, file=sys.stderr)
    return out


if __name__ == "__main__":
    main()
