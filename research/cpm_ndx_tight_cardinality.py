# -*- coding: utf-8 -*-
"""NDX sleeve: does a TIGHT (N=K+1) min-var / drop-1 selection from a HIGH-MOMENTUM
pool, or a +/-1 breadth change, beat the momentum top-5 EW prod baseline?

Analyst role. Read-only re production (ndx_sleeve_live.py / prod / memo NOT
edited). Writes only research/cpm_ndx_tight_cardinality_findings.md (+ .json).
No commit.

CONTEXT: prior NDX experiment (research/cpm_ndx_minvar_cvar.py) found min-var /
CVaR / CDaR on a top-15 prune significantly HURT -- because pruning to 15 then
selecting 5 reaches DEEP down the momentum ranking (min-var picks low-variance
momentum LAGGARDS, killing the momentum premium). REFINEMENT: test a TIGHT
N=K+1 prune so the candidate pool stays high-momentum and min-var only drops the
single most-redundant / most-volatile name.

ENGINE REUSE: monkeypatch ndx_sleeve_live.compute_ndx_weights with a
config-specific selection fn, then call the UNMODIFIED
ndx_sleeve_live.run_ndx_backtest (gating TIP+SPY-trend+SPY-vol, safe rotation,
T+1 MOO close-to-close, 10bps/side, delisting haircut, PIT membership all
identical across configs). Only the held-names selection / cardinality varies.
Reuses the prior NDX harness helpers (_gate_and_candidates, _partial_safe_pack,
_min_var_subset_lw, _lw_cov, full_metrics, crisis_metrics, annual_turnover,
walk_forward, win) and the B=2000 block=21 seed=42 paired block bootstrap.

CONFIGS (NDX sleeve; EW sizing throughout; gating/safe/T+1/10bps/delist/PIT fixed):
  PROD            momentum top-5 EW                                        (baseline)
  MINVAR_6to5     momentum top-6 -> min-var subset of 5 -> EW  (drop worst-by-var)
  DROP1CORR_6to5  momentum top-6 -> drop highest-avg-pairwise-corr -> 5 -> EW
  MINVAR_5to4     momentum top-5 -> min-var subset of 4 -> EW    (tighter, hold 4)
  TOP6_EW         momentum top-6 EW                              (+1 breadth control)
  TOP4_EW         momentum top-4 EW                          (-1 concentration ctrl)
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
# faithful reuse of the prior NDX harness wiring (gate prefix, partial-safe pack,
# LW min-var subset, metric/turnover/walk-forward helpers, crisis windows)
from research.cpm_ndx_minvar_cvar import (
    _gate_and_candidates,
    _partial_safe_pack,
    _min_var_subset_lw,
    _lw_cov,
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


# --------------------------- drop-1 by correlation --------------------------
def _drop_by_corr(ndx_panel, pool, sig_d, target, lookback=LB):
    """Iteratively drop the name with the highest average pairwise correlation
    until `target` names remain. Sample correlation over the 252d window. Falls
    back to the top-`target` momentum names if the corr matrix is degenerate."""
    pool = list(pool)
    if len(pool) <= target:
        return pool
    rets = (ndx_panel[pool].loc[:sig_d].ffill().pct_change()
            .dropna(how="all").tail(lookback))
    corr = rets.corr()
    if corr.isna().any().any():
        return pool[:target]
    cur = list(pool)
    while len(cur) > target:
        sub = corr.loc[cur, cur]
        avg = (sub.sum(axis=1) - 1.0) / (len(cur) - 1)
        cur.remove(avg.idxmax())
    # preserve momentum order of survivors for stability
    return [t for t in pool if t in cur]


# ----------------------------- config weight fns ----------------------------
def make_compute(config):
    """Drop-in replacement for ndx_sleeve_live.compute_ndx_weights.

    Each config selects `sel` held names, then equal-weights them at 1/target_K
    via _partial_safe_pack (rest -> safe), so the partial-fill / cash semantics
    match prod exactly. target_K is the intended held count (5 for prod & the
    6->5 drop rules; 4 for the tighter 5->4 / top-4; 6 for top-6 breadth)."""

    def compute(cpm_panel, ndx_panel, sig_d):
        status, safe, cands = _gate_and_candidates(cpm_panel, ndx_panel, sig_d)
        if status == "OFF":
            return ({safe: 1.0}, "GATE_OFF", {"selected": []})
        if status == "PROXY":
            return ({SPY: 1.0}, "NDX_FALLBACK_SPY", {"selected": [SPY]})
        if not cands:
            return ({safe: 1.0}, "NDX_NO_POS", {"selected": []})

        names = [t for t, _ in cands]

        if config == "PROD":
            sel, K = names[:5], 5
        elif config == "MINVAR_6to5":
            pool = names[:6]
            sel = _min_var_subset_lw(ndx_panel, pool, sig_d, min(5, len(pool)))
            K = 5
        elif config == "DROP1CORR_6to5":
            pool = names[:6]
            sel = _drop_by_corr(ndx_panel, pool, sig_d, min(5, len(pool)))
            K = 5
        elif config == "MINVAR_5to4":
            pool = names[:5]
            sel = _min_var_subset_lw(ndx_panel, pool, sig_d, min(4, len(pool)))
            K = 4
        elif config == "TOP6_EW":
            sel, K = names[:6], 6
        elif config == "TOP4_EW":
            sel, K = names[:4], 4
        else:
            raise ValueError(config)

        if not sel:
            return ({safe: 1.0}, "NDX_NO_POS", {"selected": []})
        rw = {t: 1.0 / len(sel) for t in sel}          # EW within held block
        out = _partial_safe_pack(rw, len(sel), safe, K)  # scale to 1/K, rest cash
        return (out, f"NDX_{config}", {"selected": sel})

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

    configs = ["PROD", "MINVAR_6to5", "DROP1CORR_6to5", "MINVAR_5to4",
               "TOP6_EW", "TOP4_EW"]
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

    # direct head-to-head: 6->5 MINVAR vs 6->5 DROP1CORR (does vol+corr beat
    # corr-only at tight cardinality, mirroring the CPM finding?)
    print("bootstrap MINVAR_6to5 vs DROP1CORR_6to5 ...", file=sys.stderr)
    minvar_vs_corr = paired_block_bootstrap_mm(series_clean["MINVAR_6to5"],
                                               series_clean["DROP1CORR_6to5"],
                                               cash, B=2000, block=21, seed=42)

    # walk-forward: any config whose clean bootstrap is significant on any of
    # dSharpe/dSortino/dCVaR, OR whose clean Sharpe point estimate beats PROD
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
        "anchor_note": ("PROD reproduces clean Sharpe ~1.28, MaxDD ~-31.4% with "
                        "refreshed NDX prices. Engine identical across configs; "
                        "only held-names selection / cardinality varies."),
        "window": {"clean": [str(CLEAN_START.date()), str(end.date())],
                   "ext": [str(EXT_START.date()), str(end.date())]},
        "configs": configs,
        "results": results,
        "bootstrap_vs_PROD": boot,
        "minvar_vs_corr_6to5": minvar_vs_corr,
        "walk_forward": wf,
    }
    op = ROOT / "research" / "cpm_ndx_tight_cardinality_findings.json"
    op.write_text(json.dumps(out, indent=2, default=float))
    print("WROTE", op, file=sys.stderr)
    return out


if __name__ == "__main__":
    main()
