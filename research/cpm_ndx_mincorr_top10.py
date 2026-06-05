# -*- coding: utf-8 -*-
"""NDX sleeve: (1) does a 10->5 MIN-CORR selection (corr-only, moderate prune --
keep the 5 lowest-avg-pairwise-correlation names from the top-10 momentum pool)
beat momentum top-5 EW prod? and (2) does TOP-10 EW hit a better MaxDD/Sharpe
knee than top-6 (mild) or top-15 (-8pp MaxDD but Sharpe cost)?

Analyst role. Read-only re production (ndx_sleeve_live.py / prod / memo NOT
edited). Writes only research/cpm_ndx_mincorr_top10_findings.md (+ .json). No commit.

CONTEXT (prior NDX results, this repo):
  - min-var SELECTION significantly HURT (variance picks low-vol momentum
    LAGGARDS, kills the momentum premium).
  - corr-only DROP at tight 6->5 prune was a WASH (gentler -- removes the most
    redundant name without penalizing high-vol winners).
  - breadth: top-6 EW (Sharpe 1.231 / MaxDD -30.4%); top-15 EW (1.187 / -22.8%,
    i.e. -8pp MaxDD vs prod but a Sharpe cost).
  - PROD = momentum top-5 EW: clean Sharpe ~1.281 / MaxDD ~-31.4%.

THIS STUDY adds the two missing points the user asked for:
  MINCORR_10to5  momentum top-10 -> keep 5 lowest-avg-pairwise-corr (252d) -> EW
                 (corr-only SELECTION at a MODERATE prune: preserve momentum AND
                  add diversification, vs min-var which sig hurt).
  TOP10_EW       hold all 10 momentum names EW (fill the breadth curve knee).
Plus reproduce TOP6_EW and TOP15_EW so the breadth curve top-5/6/10/15 is mapped
on one consistent engine.

ENGINE REUSE: monkeypatch ndx_sleeve_live.compute_ndx_weights, then call the
UNMODIFIED ndx_sleeve_live.run_ndx_backtest (gating TIP+SPY-trend+SPY-vol, safe
rotation, T+1 MOO close-to-close, 10bps/side, delisting haircut, PIT membership
all identical across configs). Only held-names selection / cardinality varies.
Faithful reuse of the prior NDX harness helpers (_gate_and_candidates,
_partial_safe_pack, full_metrics, crisis_metrics, annual_turnover, walk_forward,
win) and the B=2000 block=21 seed=42 paired block bootstrap.

EW BREADTH CONVENTION: every EW config (incl PROD) uses _partial_safe_pack(rw,
n_eff, safe, K) -- the direct PROD generalization (1/K per held name; if fewer
than K positive-momentum names exist, the shortfall goes to safe). This keeps
the whole breadth curve top-5/6/10/15 on identical partial-fill semantics so the
MaxDD/Sharpe knee is comparable. (NOTE: the prior top-15 reference used a
fully-invested convention; we also reproduce that variant for reconciliation.)
"""
from __future__ import annotations

import json
import sys
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cpm_live import load_panel
import ndx_sleeve_live as ndx
from research.cpm_bootstrap_multimetric import paired_block_bootstrap_mm
# faithful reuse of the prior NDX harness wiring
from research.cpm_ndx_minvar_cvar import (
    _gate_and_candidates,
    _partial_safe_pack,
    full_metrics,
    crisis_metrics,
    annual_turnover,
    walk_forward,
    win,
    EXT_START,
    CLEAN_START,
    END,
    LB,
)

SPY = ndx.SPY_TICKER


# --------------------------- min-corr subset (corr-only SELECTION) ----------
def _min_corr_subset(ndx_panel, pool, sig_d, target, lookback=LB):
    """Keep the `target`-subset of `pool` with the LOWEST average pairwise
    correlation (252d sample corr). Corr-only -- does NOT use variance, so it
    cannot prefer low-vol momentum laggards the way min-var does. Falls back to
    the top-`target` momentum names if the corr matrix is degenerate."""
    pool = list(pool)
    if len(pool) <= target:
        return pool
    rets = (ndx_panel[pool].loc[:sig_d].ffill().pct_change()
            .dropna(how="all").tail(lookback))
    corr = rets.corr()
    if corr.isna().any().any():
        return pool[:target]
    best, best_v = None, np.inf
    iu = np.triu_indices(target, k=1)
    for combo in combinations(pool, target):
        sub = corr.loc[list(combo), list(combo)].values
        v = float(sub[iu].mean())
        if v < best_v:
            best_v, best = v, combo
    sel = best if best else tuple(pool[:target])
    # preserve momentum order of survivors for stability
    return [t for t in pool if t in sel]


# ----------------------------- config weight fns ----------------------------
# breadth-EW configs: (held_count K)
EW_BREADTH = {"PROD": 5, "TOP6_EW": 6, "TOP10_EW": 10, "TOP15_EW": 15}


def make_compute(config):
    """Drop-in replacement for ndx_sleeve_live.compute_ndx_weights."""

    def compute(cpm_panel, ndx_panel, sig_d):
        status, safe, cands = _gate_and_candidates(cpm_panel, ndx_panel, sig_d)
        if status == "OFF":
            return ({safe: 1.0}, "GATE_OFF", {"selected": []})
        if status == "PROXY":
            return ({SPY: 1.0}, "NDX_FALLBACK_SPY", {"selected": [SPY]})
        if not cands:
            return ({safe: 1.0}, "NDX_NO_POS", {"selected": []})

        names = [t for t, _ in cands]

        if config in EW_BREADTH:
            K = EW_BREADTH[config]
            sel = names[:K]
            if not sel:
                return ({safe: 1.0}, "NDX_NO_POS", {"selected": []})
            rw = {t: 1.0 / len(sel) for t in sel}
            out = _partial_safe_pack(rw, len(sel), safe, K)
            return (out, f"NDX_{config}", {"selected": sel})

        if config == "TOP15_EW_FULLINV":
            # fully-invested reconciliation variant (no partial-safe cap)
            sel = names[:15]
            n = len(sel)
            return ({t: 1.0 / n for t in sel}, "NDX_TOP15EW_FI", {"selected": sel})

        if config == "MINCORR_10to5":
            pool = names[:10]
            sel = _min_corr_subset(ndx_panel, pool, sig_d, min(5, len(pool)))
            K = 5
            if not sel:
                return ({safe: 1.0}, "NDX_NO_POS", {"selected": []})
            rw = {t: 1.0 / len(sel) for t in sel}
            out = _partial_safe_pack(rw, len(sel), safe, K)
            return (out, "NDX_MINCORR_10to5", {"selected": sel})

        raise ValueError(config)

    return compute


def run_config(cpm_panel, ndx_panel, config):
    orig = ndx.compute_ndx_weights
    ndx.compute_ndx_weights = make_compute(config)
    try:
        r, hist = ndx.run_ndx_backtest(cpm_panel, ndx_panel, EXT_START,
                                       min(END, cpm_panel.index[-1]))
    finally:
        ndx.compute_ndx_weights = orig
    return r, hist


def main():
    panel = load_panel(start=EXT_START, end=END)
    end = min(END, panel.index[-1])
    ndx_panel = ndx.load_ndx_panel()
    cash = panel["SHV"].ffill().pct_change().dropna()

    configs = ["PROD", "MINCORR_10to5", "TOP6_EW", "TOP10_EW", "TOP15_EW",
               "TOP15_EW_FULLINV"]
    series_clean, series_ext, results = {}, {}, {}
    for cfg in configs:
        print(f"running {cfg} ...", file=sys.stderr)
        r, hist = run_config(panel, ndx_panel, cfg)
        sc = win(r, CLEAN_START, end)
        se = win(r, EXT_START, end)
        series_clean[cfg] = sc
        series_ext[cfg] = se
        results[cfg] = {
            "clean": full_metrics(sc, cash),
            "ext": full_metrics(se, cash),
            "crisis": crisis_metrics(se),
            "turnover_ann": annual_turnover(hist, CLEAN_START),
        }
        m = results[cfg]["clean"]
        print(f"  {cfg}: clean Sharpe={m['Sharpe']:.4f} Sortino={m['Sortino']:.4f} "
              f"CVaR={m['CVaR_ratio']:.3f} MaxDD={m['MaxDD']:.4f} "
              f"CAGR={m['CAGR']:.4f} TO={results[cfg]['turnover_ann']:.2f}",
              file=sys.stderr)

    # bootstrap each config vs PROD on clean (dSharpe/dSortino/dCVaR)
    boot = {}
    base = series_clean["PROD"]
    for cfg in configs:
        if cfg == "PROD":
            continue
        print(f"bootstrap {cfg} vs PROD ...", file=sys.stderr)
        boot[cfg] = paired_block_bootstrap_mm(series_clean[cfg], base, cash,
                                              B=2000, block=21, seed=42)

    # head-to-head: MINCORR_10to5 vs TOP10_EW (does selecting 5-of-10 by corr
    # beat just holding all 10?)
    print("bootstrap MINCORR_10to5 vs TOP10_EW ...", file=sys.stderr)
    mincorr_vs_top10 = paired_block_bootstrap_mm(series_clean["MINCORR_10to5"],
                                                 series_clean["TOP10_EW"],
                                                 cash, B=2000, block=21, seed=42)

    # walk-forward: any config significant on dSharpe/dSortino/dCVaR OR clean
    # Sharpe point estimate beats PROD
    wf = {}
    for cfg in configs:
        if cfg == "PROD":
            continue
        bb = boot[cfg]
        sig = any(bb[m]["p_gt0"] >= 0.95 or bb[m]["p_gt0"] <= 0.05
                  for m in ("dSharpe", "dSortino", "dCVaR"))
        if sig or results[cfg]["clean"]["Sharpe"] > results["PROD"]["clean"]["Sharpe"]:
            wf[cfg] = walk_forward(series_clean[cfg], cash, 3)
    wf["PROD"] = walk_forward(base, cash, 3)

    out = {
        "anchor_note": ("PROD reproduces clean Sharpe ~1.281, MaxDD ~-31.4%. "
                        "Engine identical across configs; only held-names "
                        "selection / cardinality varies. EW breadth configs use "
                        "PROD partial-safe pack (1/K, shortfall->safe); "
                        "TOP15_EW_FULLINV is the fully-invested reconciliation."),
        "window": {"clean": [str(CLEAN_START.date()), str(end.date())],
                   "ext": [str(EXT_START.date()), str(end.date())]},
        "configs": configs,
        "results": results,
        "bootstrap_vs_PROD": boot,
        "mincorr_vs_top10": mincorr_vs_top10,
        "walk_forward": wf,
    }
    op = ROOT / "research" / "cpm_ndx_mincorr_top10_findings.json"
    op.write_text(json.dumps(out, indent=2, default=float))
    print("WROTE", op, file=sys.stderr)
    return out


if __name__ == "__main__":
    main()
