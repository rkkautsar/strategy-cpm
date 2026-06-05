# -*- coding: utf-8 -*-
"""Run the NDX TOP-5 SLOT vol-target ADAPTIVE-MEDIAN target-spec study.
Writes research/cpm_ndx_voltarget_median_findings.json (+ stderr tables).

CONFIGS (all TOP-5 SLOT discrete drop-lowest-momentum; identical engine):
  NONE            prod top-5 EW, no de-risk                       (baseline)
  FIXED t0.25 w60 OOS winner from prior spec study                (anchor)
  FIXED t0.30 w60 incumbent                                       (anchor)
  ADAPT w20 / w60 target=RV252 MEAN basket vol (prior FAILURE)    (reference)
  MED12 w20 / w60 target=median(trailing 12 monthly RV)           (HYPOTHESIS)
  MED24 / MED36 w60  median over 24 / 36 months                   (anchor spectrum)
  MED12 p40 w60   40th-pct of trailing 12 monthly RV              (lower-anchor)
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
    CLEAN_START, END,
)
from research.cpm_ndx_voltarget_spec_harness import (
    turnover_events, slot_changes_per_year, exposure_stats, exposure_series,
)
from research.cpm_ndx_voltarget_median_harness import run_cell, EXT_START

UNWIND_2021 = ("2021-02-12", "2021-05-13")
Y2021 = ("2021-01-01", "2021-12-31")
COVID = ("2020-02-19", "2020-04-30")

# (key, mode, short_win, fixed_target, n_months, pct)
CONFIGS = [
    ("NONE",          "NONE",   60, None, 12, 50.0),
    ("FIXED_t25_w60", "FIXED",  60, 0.25, 12, 50.0),
    ("FIXED_t30_w60", "FIXED",  60, 0.30, 12, 50.0),
    ("ADAPT_w20",     "ADAPT",  20, None, 12, 50.0),
    ("ADAPT_w60",     "ADAPT",  60, None, 12, 50.0),
    ("MED12_w20",     "MEDIAN", 20, None, 12, 50.0),
    ("MED12_w60",     "MEDIAN", 60, None, 12, 50.0),
    ("MED24_w60",     "MEDIAN", 60, None, 24, 50.0),
    ("MED36_w60",     "MEDIAN", 60, None, 36, 50.0),
    ("MED12_p40_w60", "MEDIAN", 60, None, 12, 40.0),
    ("EXPAND_w20",     "EXPAND", 20, None, 12, 50.0),
    ("EXPAND_w60",     "EXPAND", 60, None, 12, 50.0),
]


def window_metrics(ret, a, b):
    w = ret.loc[(ret.index >= pd.Timestamp(a)) & (ret.index <= pd.Timestamp(b))]
    if len(w) < 5:
        return None
    m = perf_metrics(w, None)
    cum = float((1.0 + w).prod() - 1.0)
    return {"MaxDD": m.get("max_drawdown"), "cum_return": cum, "n_days": len(w)}


def path_2021(log):
    """Monthly (date, rv_short, target, scale, n, exp) over 2020-07..2021-12 to
    show whether MEDIAN target lagged enough to keep target<RV_short (de-risk)."""
    out = []
    for e in log:
        d = e["sig_d"]
        if "2020-07" <= d[:7] <= "2021-12":
            out.append({"d": d, "rv_s": e.get("rv_short"), "tgt": e.get("target"),
                        "scale": e.get("scale"), "n": e.get("n_risky"),
                        "exp": e.get("equity_exposure")})
    return out


def main():
    panel = load_panel(start=EXT_START, end=END)
    end = min(END, panel.index[-1])
    ndx_panel = ndx.load_ndx_panel()
    cash = panel["SHV"].ffill().pct_change().dropna()

    series_clean, results, logs = {}, {}, {}
    for key, mode, sw, tgt, nm, pct in CONFIGS:
        print(f"running {key} ...", file=sys.stderr)
        r, hist, log = run_cell(panel, ndx_panel, mode, short_win=sw,
                                fixed_target=tgt, n_months=nm, pct=pct)
        sc = win(r, CLEAN_START, end)
        se = win(r, EXT_START, end)
        series_clean[key] = sc
        logs[key] = log
        te = turnover_events(hist, CLEAN_START)
        results[key] = {
            "mode": mode, "short_win": sw, "fixed_target": tgt,
            "n_months": nm, "pct": pct,
            "clean": full_metrics(sc, cash),
            "ext": full_metrics(se, cash),
            "crisis": crisis_metrics(se),
            "unwind_2021": window_metrics(se, *UNWIND_2021),
            "year_2021": window_metrics(se, *Y2021),
            "covid_2020": window_metrics(se, *COVID),
            "turnover_ann": te["turnover_ann"],
            "pos_change_events_yr": te["pos_change_events_yr"],
            "name_flip_events_yr": te["name_flip_events_yr"],
            "slot_changes_per_yr": slot_changes_per_year(log, CLEAN_START),
            "exposure": exposure_stats(log, CLEAN_START),
        }
        m = results[key]["clean"]
        ex = results[key]["exposure"]
        u = results[key]["unwind_2021"] or {}
        print(f"  {key}: Sh={m['Sharpe']:.3f} Sort={m['Sortino']:.3f} "
              f"CVaR={m['CVaR_ratio']:.3f} MaxDD={m['MaxDD']:.3f} CAGR={m['CAGR']:.3f} "
              f"vol={m['vol']:.3f} TO={te['turnover_ann']:.2f} "
              f"slotEv={results[key]['slot_changes_per_yr']:.2f} "
              f"meanExp={ex['mean_equity_exposure']:.3f} "
              f"u2021DD={u.get('MaxDD')}", file=sys.stderr)

    # --------------------------- bootstraps ---------------------------
    boot = {}

    def bb(a, b):
        return paired_block_bootstrap_mm(series_clean[a], series_clean[b], cash,
                                         B=2000, block=21, seed=42)

    boot["MED12_w20_vs_FIXED_t25_w60"] = bb("MED12_w20", "FIXED_t25_w60")
    boot["MED12_w60_vs_FIXED_t25_w60"] = bb("MED12_w60", "FIXED_t25_w60")
    boot["MED12_w20_vs_ADAPT_w20"] = bb("MED12_w20", "ADAPT_w20")
    boot["MED12_w60_vs_ADAPT_w60"] = bb("MED12_w60", "ADAPT_w60")
    boot["MED12_w20_vs_NONE"] = bb("MED12_w20", "NONE")
    boot["MED12_w60_vs_NONE"] = bb("MED12_w60", "NONE")
    boot["MED36_w60_vs_FIXED_t25_w60"] = bb("MED36_w60", "FIXED_t25_w60")
    boot["EXPAND_w60_vs_FIXED_t25_w60"] = bb("EXPAND_w60", "FIXED_t25_w60")
    boot["EXPAND_w20_vs_FIXED_t25_w60"] = bb("EXPAND_w20", "FIXED_t25_w60")
    boot["EXPAND_w60_vs_NONE"] = bb("EXPAND_w60", "NONE")

    # --------------------------- walk-forward (all cells) ---------------------------
    wf = {key: walk_forward(series_clean[key], cash, 3) for key in series_clean}

    # --------------------------- 2021 path (the decisive episode) -------------
    path21 = {k: path_2021(logs[k]) for k in
              ("FIXED_t30_w60", "ADAPT_w20", "ADAPT_w60",
               "MED12_w20", "MED12_w60", "MED24_w60", "MED36_w60",
               "EXPAND_w20", "EXPAND_w60")}

    expser = {}
    for k in ("FIXED_t30_w60", "ADAPT_w60", "MED12_w20", "MED12_w60",
              "MED36_w60", "EXPAND_w60"):
        es = exposure_series(logs[k], CLEAN_START)
        expser[k] = [e for e in es if "2020" <= e["d"][:4] <= "2022"]

    out = {
        "anchor_note": ("NONE = prod top-5 EW. All de-risk configs share the IDENTICAL "
                        "TOP-5 SLOT discrete drop-lowest-momentum mechanism "
                        "(n=round(scale*5)); only the TARGET feeding scale differs: "
                        "FIXED absolute vs ADAPT=RV252 trailing MEAN vs MEDIAN=percentile "
                        "of trailing N MONTHLY RV. References reproduce the spec-study "
                        "anchors (same engine/helpers). Cached dataset; absolute levels "
                        "may differ slightly from a prod refresh -- apples-to-apples "
                        "across configs. Lookbacks/percentiles A-PRIORI to MAP the "
                        "relative->absolute spectrum, NOT to optimize a winner."),
        "spec": {"K": 5, "cap": 1.0, "drop_rule": "lowest_momentum",
                 "min_month_days": 15,
                 "configs": [{"key": c[0], "mode": c[1], "short_win": c[2],
                              "fixed_target": c[3], "n_months": c[4], "pct": c[5]}
                             for c in CONFIGS]},
        "window": {"clean": [str(CLEAN_START.date()), str(end.date())],
                   "ext": [str(EXT_START.date()), str(end.date())],
                   "unwind_2021": list(UNWIND_2021), "year_2021": list(Y2021),
                   "covid_2020": list(COVID)},
        "results": results,
        "bootstrap": boot,
        "walk_forward": wf,
        "path_2021": path21,
        "exposure_series_2020_2022": expser,
    }
    op = ROOT / "research" / "cpm_ndx_voltarget_median_findings.json"
    op.write_text(json.dumps(out, indent=2, default=float))
    print("\nWROTE", op, file=sys.stderr)
    return out


if __name__ == "__main__":
    main()
