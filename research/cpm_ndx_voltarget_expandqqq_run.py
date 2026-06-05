# -*- coding: utf-8 -*-
"""Run the EXPANDING-WINDOW QQQ vol-target study + COMPREHENSIVE risk-adjusted
table across ALL finalist target specs. POINT-ESTIMATES ONLY (no bootstrap, no
walk-forward -- scope-reduced for speed; flag any compelling cell for a later
bootstrap/WF confirm).

Writes research/cpm_ndx_voltarget_expandqqq_findings.json (+ stderr tables).

CONFIGS (all TOP-5 SLOT discrete drop-lowest-momentum; identical engine):
  NONE             prod top-5 EW, no de-risk                       (baseline)
  FIXED t0.25 w60  incumbent external-absolute winner             (anchor)
  FIXED t0.30 w60  incumbent                                      (anchor)
  ADAPT  w60       target = RV252 MEAN basket vol (self-ref FAIL) (reference)
  EXPAND w60       expanding-window mean basket RV  (self-ref FAIL)(reference)
  QQQ_LEVEL m1.0 w60  target = m*QQQ_RV252  (trailing-252d, chronic drag)(ref)
  QQQ_RATIO w60    scale=min(1,QQQ_RV252/QQQ_RV_short)            (regime form)
  QQQ_EXPAND m{1.0,1.25,1.5,2.0} w60 (+ w20)  target=m*qqq_expand_vol  (NEW)

METRIC DEFINITIONS (all annualized unless noted):
  Sharpe  = perf_metrics annualized excess-of-cash Sharpe
  Sortino = mean*252 / (downside_dev*sqrt(252)), downside_dev=sqrt(mean(min(r,0)^2))
  CVaR_ratio = mean*252 / |mean(worst 5% daily returns)|  (Expected-Shortfall ratio)
  Calmar  = CAGR / |MaxDD|
  Martin  = CAGR / Ulcer, Ulcer = sqrt(mean(drawdown^2)) over the daily DD path
  MaxDD   = peak-to-trough worst drawdown (path-dependent)
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
from research.cpm_ndx_minvar_cvar import (
    full_metrics, crisis_metrics, win, CLEAN_START, END,
)
from research.cpm_ndx_voltarget_spec_harness import (
    turnover_events, slot_changes_per_year, exposure_stats, exposure_series,
)
from research.cpm_ndx_voltarget_qqq_harness import run_cell as run_qqq
from research.cpm_ndx_voltarget_expandqqq_harness import run_cell as run_expand, EXT_START

UNWIND_2021 = ("2021-02-12", "2021-05-13")
Y2021 = ("2021-01-01", "2021-12-31")
COVID = ("2020-02-19", "2020-04-30")

# (key, kind, mode, short_win, fixed_target, mult)
#   kind: "qqq" -> qqq_harness.run_cell ; "exp" -> expandqqq_harness.run_cell
CONFIGS = [
    ("NONE",            "qqq", "NONE",      60, None, 1.0),
    ("FIXED_t25_w60",   "qqq", "FIXED",     60, 0.25, 1.0),
    ("FIXED_t30_w60",   "qqq", "FIXED",     60, 0.30, 1.0),
    ("ADAPT_w60",       "qqq", "ADAPT",     60, None, 1.0),
    ("EXPAND_w60",      "qqq", "EXPAND",    60, None, 1.0),
    ("QQQL_m10_w60",    "qqq", "QQQ_LEVEL", 60, None, 1.0),
    ("QQQR_w60",        "qqq", "QQQ_RATIO", 60, None, 1.0),
    ("QEXP_m100_w60",   "exp", "QQQ_EXPAND",60, None, 1.0),
    ("QEXP_m125_w60",   "exp", "QQQ_EXPAND",60, None, 1.25),
    ("QEXP_m150_w60",   "exp", "QQQ_EXPAND",60, None, 1.5),
    ("QEXP_m200_w60",   "exp", "QQQ_EXPAND",60, None, 2.0),
    ("QEXP_m100_w20",   "exp", "QQQ_EXPAND",20, None, 1.0),
    ("QEXP_m125_w20",   "exp", "QQQ_EXPAND",20, None, 1.25),
    ("QEXP_m150_w20",   "exp", "QQQ_EXPAND",20, None, 1.5),
    ("QEXP_m200_w20",   "exp", "QQQ_EXPAND",20, None, 2.0),
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
                        "qexp": e.get("qqq_expand"), "qqq252": e.get("qqq_rv252"),
                        "tgt": e.get("target"), "scale": e.get("scale"),
                        "n": e.get("n_risky"), "exp": e.get("equity_exposure")})
    return out


def main():
    panel = load_panel(start=EXT_START, end=END)
    end = min(END, panel.index[-1])
    ndx_panel = ndx.load_ndx_panel()
    cash = panel["SHV"].ffill().pct_change().dropna()

    series_clean, results, logs = {}, {}, {}
    for key, kind, mode, sw, tgt, mult in CONFIGS:
        print(f"running {key} ...", file=sys.stderr)
        if kind == "exp":
            r, hist, log = run_expand(panel, ndx_panel, short_win=sw, mult=mult)
        else:
            r, hist, log = run_qqq(panel, ndx_panel, mode, short_win=sw,
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
            "slot_changes_per_yr": slot_changes_per_year(log, CLEAN_START),
            "exposure": exposure_stats(log, CLEAN_START),
        }
        m = results[key]["clean"]
        ex = results[key]["exposure"]
        u = results[key]["unwind_2021"] or {}
        y = results[key]["year_2021"] or {}
        print(f"  {key}: Sh={m['Sharpe']:.3f} Sort={m['Sortino']:.3f} "
              f"CVaR={m['CVaR_ratio']:.3f} Cal={m['Calmar']:.3f} "
              f"Mar={m['Martin']:.3f} MaxDD={m['MaxDD']:.3f} CAGR={m['CAGR']:.3f} "
              f"vol={m['vol']:.3f} TO={te['turnover_ann']:.2f} "
              f"slotEv={results[key]['slot_changes_per_yr']:.2f} "
              f"meanExp={ex['mean_equity_exposure']:.3f} "
              f"u2021DD={u.get('MaxDD')} y2021DD={y.get('MaxDD')}", file=sys.stderr)

    # 2021 path (decisive episode) for expand-QQQ + references
    path21 = {k: path_2021(logs[k]) for k in
              ("FIXED_t25_w60", "QQQL_m10_w60",
               "QEXP_m100_w60", "QEXP_m125_w60", "QEXP_m150_w60", "QEXP_m200_w60")}

    expser = {}
    for k in ("QEXP_m100_w60", "QEXP_m125_w60", "QEXP_m150_w60", "QEXP_m200_w60"):
        es = exposure_series(logs[k], CLEAN_START)
        expser[k] = [e for e in es if "2020" <= e["d"][:4] <= "2022"]

    out = {
        "anchor_note": ("NONE = prod top-5 EW. All de-risk configs share the IDENTICAL "
                        "TOP-5 SLOT discrete drop-lowest-momentum mechanism "
                        "(n=round(scale*5)); only the TARGET feeding scale differs. "
                        "QQQ_EXPAND target=mult*qqq_expanding_vol (expanding-window MEAN of "
                        "completed-month QQQ RV, inception->t-1), scale=min(1,target/"
                        "basket_RV_short). FIXED is the incumbent external-absolute winner; "
                        "ADAPT/EXPAND/QQQ_LEVEL/QQQ_RATIO are reference families. "
                        "POINT-ESTIMATES ONLY -- bootstrap + walk-forward SKIPPED for speed; "
                        "flag compelling cells for later confirm. mult/windows A-PRIORI "
                        "{1.0,1.25,1.5,2.0}, short 20/60d, NOT optimized; single in-sample."),
        "metric_defs": {
            "Sharpe": "annualized excess-of-cash Sharpe (perf_metrics)",
            "Sortino": "mean*252 / (downside_dev*sqrt(252)); downside_dev=sqrt(mean(min(r,0)^2))",
            "CVaR_ratio": "mean*252 / |mean(worst 5% daily returns)| (annualized ES ratio)",
            "Calmar": "CAGR / |MaxDD|",
            "Martin": "CAGR / Ulcer; Ulcer=sqrt(mean(drawdown^2)) over daily DD path",
            "MaxDD": "peak-to-trough worst drawdown (path-dependent)",
        },
        "spec": {"K": 5, "cap": 1.0, "drop_rule": "lowest_momentum",
                 "qqq_source": "cpm_panel[QQQ] stitched (ETF 1999-03+, NDX proxy pre-1999)",
                 "configs": [{"key": c[0], "mode": c[2], "short_win": c[3],
                              "fixed_target": c[4], "mult": c[5]} for c in CONFIGS]},
        "window": {"clean": [str(CLEAN_START.date()), str(end.date())],
                   "ext": [str(EXT_START.date()), str(end.date())],
                   "unwind_2021": list(UNWIND_2021), "year_2021": list(Y2021),
                   "covid_2020": list(COVID)},
        "results": results,
        "path_2021": path21,
        "exposure_series_2020_2022": expser,
    }
    op = ROOT / "research" / "cpm_ndx_voltarget_expandqqq_findings.json"
    op.write_text(json.dumps(out, indent=2, default=float))
    print("\nWROTE", op, file=sys.stderr)
    return out


if __name__ == "__main__":
    main()
