# -*- coding: utf-8 -*-
"""Run the NDX TOP-5 SLOT vol-target EXTERNAL PARENT-INDEX (QQQ) target study.
Writes research/cpm_ndx_voltarget_qqq_findings.json (+ stderr tables).

CONFIGS (all TOP-5 SLOT discrete drop-lowest-momentum; identical engine):
  NONE             prod top-5 EW, no de-risk                       (baseline)
  FIXED t0.25 w60  incumbent winner                                (anchor)
  FIXED t0.30 w60  incumbent                                       (anchor)
  ADAPT  w20 / w60 target=RV252 MEAN basket vol (self-ref FAILURE) (reference)
  EXPAND w20 / w60 expanding-window mean basket RV (self-ref FAIL) (reference)
  QQQ_LEVEL m1.0/1.5/2.0 w20 + w60   target = m*QQQ_RV252          (HYPOTHESIS,dial)
  QQQ_RATIO w20 / w60   scale=min(1,QQQ_RV252/QQQ_RV_short)        (regime form)
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
from research.cpm_ndx_voltarget_qqq_harness import run_cell, EXT_START

UNWIND_2021 = ("2021-02-12", "2021-05-13")
Y2021 = ("2021-01-01", "2021-12-31")
COVID = ("2020-02-19", "2020-04-30")

# (key, mode, short_win, fixed_target, mult)
CONFIGS = [
    ("NONE",            "NONE",      60, None, 1.0),
    ("FIXED_t25_w60",   "FIXED",     60, 0.25, 1.0),
    ("FIXED_t30_w60",   "FIXED",     60, 0.30, 1.0),
    ("ADAPT_w20",       "ADAPT",     20, None, 1.0),
    ("ADAPT_w60",       "ADAPT",     60, None, 1.0),
    ("EXPAND_w20",      "EXPAND",    20, None, 1.0),
    ("EXPAND_w60",      "EXPAND",    60, None, 1.0),
    ("QQQL_m10_w20",    "QQQ_LEVEL", 20, None, 1.0),
    ("QQQL_m10_w60",    "QQQ_LEVEL", 60, None, 1.0),
    ("QQQL_m15_w20",    "QQQ_LEVEL", 20, None, 1.5),
    ("QQQL_m15_w60",    "QQQ_LEVEL", 60, None, 1.5),
    ("QQQL_m20_w20",    "QQQ_LEVEL", 20, None, 2.0),
    ("QQQL_m20_w60",    "QQQ_LEVEL", 60, None, 2.0),
    ("QQQR_w20",        "QQQ_RATIO", 20, None, 1.0),
    ("QQQR_w60",        "QQQ_RATIO", 60, None, 1.0),
]


def window_metrics(ret, a, b):
    w = ret.loc[(ret.index >= pd.Timestamp(a)) & (ret.index <= pd.Timestamp(b))]
    if len(w) < 5:
        return None
    m = perf_metrics(w, None)
    cum = float((1.0 + w).prod() - 1.0)
    return {"MaxDD": m.get("max_drawdown"), "cum_return": cum, "n_days": len(w)}


def path_2021(log):
    """Monthly path 2020-07..2021-12 to show the de-risk signal vs basket vol."""
    out = []
    for e in log:
        d = e["sig_d"]
        if "2020-07" <= d[:7] <= "2021-12":
            out.append({"d": d, "rv_s": e.get("rv_short"),
                        "qqq252": e.get("qqq_rv252"), "qqq_s": e.get("qqq_rv_short"),
                        "tgt": e.get("target"), "scale": e.get("scale"),
                        "n": e.get("n_risky"), "exp": e.get("equity_exposure")})
    return out


def main():
    panel = load_panel(start=EXT_START, end=END)
    end = min(END, panel.index[-1])
    ndx_panel = ndx.load_ndx_panel()
    cash = panel["SHV"].ffill().pct_change().dropna()

    series_clean, results, logs = {}, {}, {}
    for key, mode, sw, tgt, mult in CONFIGS:
        print(f"running {key} ...", file=sys.stderr)
        r, hist, log = run_cell(panel, ndx_panel, mode, short_win=sw,
                                fixed_target=tgt, mult=mult)
        sc = win(r, CLEAN_START, end)
        se = win(r, EXT_START, end)
        series_clean[key] = sc
        logs[key] = log
        te = turnover_events(hist, CLEAN_START)
        results[key] = {
            "mode": mode, "short_win": sw, "fixed_target": tgt, "mult": mult,
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

    # QQQ-LEVEL (each m) vs the fixed winner, vs self-ref failure, vs prod
    for k in ("QQQL_m10_w60", "QQQL_m15_w60", "QQQL_m20_w60",
              "QQQL_m10_w20", "QQQL_m15_w20", "QQQL_m20_w20"):
        boot[f"{k}_vs_FIXED_t25_w60"] = bb(k, "FIXED_t25_w60")
        boot[f"{k}_vs_NONE"] = bb(k, "NONE")
    boot["QQQL_m10_w60_vs_ADAPT_w60"] = bb("QQQL_m10_w60", "ADAPT_w60")
    boot["QQQL_m15_w60_vs_ADAPT_w60"] = bb("QQQL_m15_w60", "ADAPT_w60")
    # QQQ-RATIO form
    boot["QQQR_w60_vs_FIXED_t25_w60"] = bb("QQQR_w60", "FIXED_t25_w60")
    boot["QQQR_w20_vs_FIXED_t25_w60"] = bb("QQQR_w20", "FIXED_t25_w60")
    boot["QQQR_w60_vs_NONE"] = bb("QQQR_w60", "NONE")
    boot["QQQR_w60_vs_ADAPT_w60"] = bb("QQQR_w60", "ADAPT_w60")

    # --------------------------- walk-forward (all cells) ---------------------------
    wf = {key: walk_forward(series_clean[key], cash, 3) for key in series_clean}

    # --------------------------- 2021 path (decisive episode) -----------------
    path21 = {k: path_2021(logs[k]) for k in
              ("FIXED_t30_w60", "ADAPT_w60", "EXPAND_w60",
               "QQQL_m10_w60", "QQQL_m15_w60", "QQQL_m20_w60",
               "QQQR_w60")}

    expser = {}
    for k in ("FIXED_t30_w60", "ADAPT_w60",
              "QQQL_m10_w60", "QQQL_m15_w60", "QQQL_m20_w60", "QQQR_w60"):
        es = exposure_series(logs[k], CLEAN_START)
        expser[k] = [e for e in es if "2020" <= e["d"][:4] <= "2022"]

    out = {
        "anchor_note": ("NONE = prod top-5 EW. All de-risk configs share the IDENTICAL "
                        "TOP-5 SLOT discrete drop-lowest-momentum mechanism "
                        "(n=round(scale*5)); only the TARGET feeding scale differs. "
                        "QQQ_LEVEL target=mult*QQQ_RV252, scale=min(1,target/basket_RV_short); "
                        "QQQ_RATIO scale=min(1,QQQ_RV252/QQQ_RV_short). ADAPT/EXPAND are the "
                        "proven self-referential FAILURES (reference, expect zero 2021 "
                        "protection). FIXED is the incumbent external-absolute winner. "
                        "QQQ from cpm_panel (data/qqq_stitched_daily.csv): actual ETF adj "
                        "close 1999-03+, NDX index-level proxy 1985-10..1999-03 (equivalent "
                        "for vol). Cached frozen dataset; absolute levels may differ "
                        "marginally from a prod refresh -- apples-to-apples across configs. "
                        "mult/windows A-PRIORI (m in {1.0,1.5,2.0}, short 20/60d), NOT "
                        "optimized; single in-sample pass."),
        "spec": {"K": 5, "cap": 1.0, "drop_rule": "lowest_momentum",
                 "qqq_source": "cpm_panel[QQQ] stitched (ETF 1999-03+, NDX proxy pre-1999)",
                 "configs": [{"key": c[0], "mode": c[1], "short_win": c[2],
                              "fixed_target": c[3], "mult": c[4]} for c in CONFIGS]},
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
    op = ROOT / "research" / "cpm_ndx_voltarget_qqq_findings.json"
    op.write_text(json.dumps(out, indent=2, default=float))
    print("\nWROTE", op, file=sys.stderr)
    return out


if __name__ == "__main__":
    main()
