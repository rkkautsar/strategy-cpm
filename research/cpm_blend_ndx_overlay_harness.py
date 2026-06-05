# -*- coding: utf-8 -*-
"""FULL PRODUCTION BLEND (60% CPM / 20% BULL-SPY / 20% NDX) with the NDX sleeve
swapped between the current top-5 EW (CAGR engine) and the settled de-risk
overlay (QQQ_EXPAND m*expanding-QQQ vol target). Tests whether the overlay
improves the WHOLE portfolio's risk-adjusted metrics or whether 20%-weight
dilution + diversification make NDX better as a pure CAGR engine.

PROD BLEND construction is REUSED verbatim from build_dashboard.build_artifacts
(CPM_W=0.60, BULL_W=0.20, NDX_W=0.20). CPM + BULL sleeves are IDENTICAL across
all configs; only the NDX sleeve varies via a monkeypatch of
ndx_sleeve_live.compute_ndx_weights (the unmodified run_ndx_backtest is reused,
so gate/safe-rotation/T+1 MOO/10bps/delist/PIT execution conventions hold).

CONFIGS (NDX sleeve only varies):
  PROD   = NDX top-5 EW, no de-risk            (anchor; reproduce blend metrics)
  m1.00  = NDX overlay QQQ_EXPAND mult=1.00    (~ fixed-0.25, full tail protect)
  m1.25  = NDX overlay QQQ_EXPAND mult=1.25    (~ fixed-0.30, lighter de-risk)
  m1.50  = NDX overlay QQQ_EXPAND mult=1.50    (frontier point)

POINT-ESTIMATES ONLY. No bootstrap / no walk-forward (standing scope cut).
mult A-PRIORI, single in-sample -> HIGH overfit caution. Cached frozen dataset.

Analyst role. Read-only re production code. Writes only research/. No commit.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cpm_live import load_panel, perf_metrics
import ndx_sleeve_live as ndx
import build_dashboard as bd

from research.cpm_ndx_minvar_cvar import (
    full_metrics, crisis_metrics, win, sortino_ann, cvar_ratio_ann,
    EXT_START, CLEAN_START, END,
)
from research.cpm_ndx_voltarget_spec_harness import turnover_events
from research.cpm_ndx_voltarget_expandqqq_harness import make_compute

UNWIND_2021 = ("2021-02-12", "2021-05-13")
Y2021 = ("2021-01-01", "2021-12-31")
COVID = ("2020-02-19", "2020-04-30")

# (key, mult or None for PROD)
CONFIGS = [
    ("PROD",  None),
    ("m1.00", 1.0),
    ("m1.25", 1.25),
    ("m1.50", 1.5),
]


def window_metrics(ret, a, b):
    w = ret.loc[(ret.index >= pd.Timestamp(a)) & (ret.index <= pd.Timestamp(b))]
    if len(w) < 5:
        return None
    m = perf_metrics(w, None)
    cum = float((1.0 + w).prod() - 1.0)
    return {"MaxDD": m.get("max_drawdown"), "cum_return": cum, "n_days": len(w)}


def build_blend(panel, ndx_panel, start, end, mult):
    """Return SimpleNamespace art from build_dashboard.build_artifacts with the
    NDX sleeve = PROD (mult None) or QQQ_EXPAND overlay (mult set). CPM + BULL
    are identical regardless. Also return the NDX hist for turnover."""
    log = []
    orig = ndx.compute_ndx_weights
    if mult is not None:
        ndx.compute_ndx_weights = make_compute("QQQ_EXPAND", 60, None, mult, log)
    try:
        art = bd.build_artifacts(panel, ndx_panel, start, end, include_records=False)
        # Separately capture NDX hist (build_artifacts discards it) for turnover.
        _, ndx_hist = ndx.run_ndx_backtest(panel, ndx_panel, start, end)
    finally:
        ndx.compute_ndx_weights = orig
    return art, ndx_hist


def run():
    # Mirror build_dashboard.main panel loading (warmup for CPM EMA200 / BULL TR).
    panel_start = min(pd.Timestamp("2008-05-30") - pd.DateOffset(years=20),
                      pd.Timestamp("1995-01-01"))
    panel = load_panel(start=panel_start, end=END, live=True)
    end = min(END, panel.index[-1])
    ndx_panel = ndx.load_ndx_panel()
    cash = panel["SHV"].ffill().pct_change().dropna()

    results = {}
    blend_clean = {}
    blend_ext = {}
    ndx_clean = {}
    for key, mult in CONFIGS:
        print(f"running {key} (mult={mult}) ...", file=sys.stderr)
        # CLEAN window blend (decision window = live ETF 2008-05-30+).
        art_c, ndx_hist = build_blend(panel, ndx_panel, CLEAN_START, end, mult)
        # EXT window blend (1999-03-10+) for dotcom/GFC crises + 2021 detail.
        art_e, _ = build_blend(panel, ndx_panel, EXT_START, end, mult)

        bc = art_c.blend
        be = art_e.blend
        ndc = art_c.ndx
        blend_clean[key] = bc
        blend_ext[key] = be
        ndx_clean[key] = ndc

        to = turnover_events(ndx_hist, CLEAN_START)
        results[key] = {
            "mult": mult,
            # blend-level
            "blend_clean": full_metrics(bc, cash),
            "blend_ext": full_metrics(be, cash),
            "blend_crisis": crisis_metrics(be),
            "blend_unwind_2021": window_metrics(be, *UNWIND_2021),
            "blend_year_2021": window_metrics(be, *Y2021),
            "blend_covid_2020": window_metrics(be, *COVID),
            # NDX sleeve standalone (clean window) for marginal-contribution
            "ndx_sleeve_clean": full_metrics(ndc, cash),
            "ndx_sleeve_crisis": crisis_metrics(art_e.ndx),
            "ndx_sleeve_unwind_2021": window_metrics(art_e.ndx, *UNWIND_2021),
            "ndx_sleeve_year_2021": window_metrics(art_e.ndx, *Y2021),
            "ndx_turnover_ann": to["turnover_ann"],
        }
        m = results[key]["blend_clean"]
        nm = results[key]["ndx_sleeve_clean"]
        print(f"  {key}: BLEND Sh={m['Sharpe']:.3f} Sort={m['Sortino']:.3f} "
              f"CVaR={m['CVaR_ratio']:.3f} Cal={m['Calmar']:.3f} Mar={m['Martin']:.3f} "
              f"MaxDD={m['MaxDD']:.4f} CAGR={m['CAGR']:.4f} vol={m['vol']:.4f} | "
              f"NDXsleeve CAGR={nm['CAGR']:.4f} MaxDD={nm['MaxDD']:.4f} "
              f"Cal={nm['Calmar']:.3f}", file=sys.stderr)

    return {
        "window": {"clean": [str(CLEAN_START.date()), str(end.date())],
                   "ext": [str(EXT_START.date()), str(end.date())],
                   "unwind_2021": list(UNWIND_2021), "year_2021": list(Y2021),
                   "covid_2020": list(COVID)},
        "weights": {"CPM": bd.CPM_W, "BULL": bd.BULL_W, "NDX": bd.NDX_W},
        "results": results,
    }
