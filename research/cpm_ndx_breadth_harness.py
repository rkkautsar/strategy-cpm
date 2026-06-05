# -*- coding: utf-8 -*-
"""NDX sleeve: BREADTH (top-N in {5,8,10}) x DE-RISK METHOD ({NONE, CONT, SLOT})
sweep. Headline metric = TURNOVER/YEAR and #POSITION-CHANGE-EVENTS/YEAR per cell.

Analyst role. Read-only re production (ndx_sleeve_live.py / prod / memo NOT
edited). Writes only research/cpm_ndx_breadth_findings.* . No commit.

EXTENDS research/cpm_ndx_slotreplace_harness.py to parametrize breadth N. Reuses
the SAME engine (monkeypatch ndx_sleeve_live.compute_ndx_weights -> UNMODIFIED
run_ndx_backtest: gate TIP+SPY-trend+SPY-RV, safe rotation, T+1 MOO, 10bps/side,
delisting haircut, PIT membership). Reuses the SAME basket-vol scale signal
(target 0.30, 60d lagged, cap 1.0) for CONT and SLOT so exposure is matched
WITHIN each N.

CONFIGS (9 cells = N{5,8,10} x method{NONE, CONT, SLOT}):
  NONE  top-N EW, no de-risk (scale=1 always)            [breadth-only effect]
  CONT  top-N EW * scale, freed weight -> safe (continuous dial)
  SLOT  discrete drop-lowest-momentum: n=round(scale*N) keep top-n EW each at 1/N,
        drop (N-n) lowest-momentum names to safe.
All share the IDENTICAL scale signal so exposure matched within each N.
NONE@N=5 reproduces the PROD top-5 EW anchor exactly (same gate/selection).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ndx_sleeve_live as ndx
from bull_spy_live import SAFE_POOL, CASH_TICKER
from research.cpm_ndx_minvar_cvar import (
    _gate_and_candidates,
    _partial_safe_pack,
    EXT_START,
    CLEAN_START,
    END,
)
from research.cpm_ndx_voltarget import _basket_vol

SPY = ndx.SPY_TICKER
TARGET_BASKET = 0.30   # a-priori annualized basket-vol target (same as voltarget/slot)
WIN_PRIMARY = 60       # trailing daily-return window for realized vol
SAFE_SET = set(SAFE_POOL) | {CASH_TICKER}   # SHV/IEF/cash -> excluded from risky-name events


def _scale(rv, target):
    """De-risk-only vol-target scale = clip(target/rv, 0, 1)."""
    if rv is None or not np.isfinite(rv) or rv <= 0:
        return 1.0
    return float(np.clip(target / rv, 0.0, 1.0))


def make_compute(method, N, target, window, log):
    """Drop-in replacement for ndx_sleeve_live.compute_ndx_weights.

    Selection = momentum top-N (PROD gate/PIT). NONE: EW, scale=1. CONT: shrink
    all N uniformly by the basket-vol scale, freed weight -> safe. SLOT: keep the
    top-n=round(scale*N) momentum names EW at 1/N each, drop the rest to safe.
    `log` collects per-ON-month (sig_d, rv, scale, n_risky, equity_exposure)."""

    def compute(cpm_panel, ndx_panel, sig_d):
        status, safe, cands = _gate_and_candidates(cpm_panel, ndx_panel, sig_d)
        if status == "OFF":
            return ({safe: 1.0}, "GATE_OFF", {"selected": []})
        if status == "PROXY":
            return ({SPY: 1.0}, "NDX_FALLBACK_SPY", {"selected": [SPY]})
        if not cands:
            return ({safe: 1.0}, "NDX_NO_POS", {"selected": []})

        names = [t for t, _ in cands]
        sel = names[:N]                       # momentum top-N
        k_avail = len(sel)
        rw = {t: 1.0 / k_avail for t in sel}
        base = _partial_safe_pack(rw, k_avail, safe, K=N)   # each name 1/N, rest safe
        risky_fraction = min(k_avail, N) / N

        if method == "NONE":
            log.append({"sig_d": str(sig_d.date()), "rv": None, "scale": 1.0,
                        "n_risky": k_avail, "equity_exposure": risky_fraction})
            return (base, f"NDX_NONE_N{N}", {"selected": sel})

        rv = _basket_vol(ndx_panel, sel, sig_d, window)
        scale = _scale(rv, target)

        if method == "CONT":
            out = {t: base[t] * scale for t in sel}
            freed = risky_fraction * (1.0 - scale)
            safe_w = base.get(safe, 0.0) + freed
            if abs(safe_w) > 1e-9:
                out[safe] = out.get(safe, 0.0) + safe_w
            eq = risky_fraction * scale
            log.append({"sig_d": str(sig_d.date()), "rv": rv, "scale": scale,
                        "n_risky": None, "equity_exposure": eq})
            return (out, f"NDX_CONT_N{N}", {"selected": sel})

        if method == "SLOT":
            n = int(np.clip(int(np.round(scale * N)), 0, k_avail))
            kept = sel[:n]                    # keep top-n momentum (drop lowest mom)
            out = {t: 1.0 / N for t in kept}  # each kept name = 1/N of book
            eq = n / N
            safe_w = 1.0 - eq
            if safe_w > 1e-9:
                out[safe] = out.get(safe, 0.0) + safe_w
            log.append({"sig_d": str(sig_d.date()), "rv": rv, "scale": scale,
                        "n_risky": n, "equity_exposure": eq})
            return (out, f"NDX_SLOT_N{N}", {"selected": kept})

        raise ValueError(method)

    return compute


def run_cell(cpm_panel, ndx_panel, method, N, target=TARGET_BASKET, window=WIN_PRIMARY):
    log = []
    orig = ndx.compute_ndx_weights
    ndx.compute_ndx_weights = make_compute(method, N, target, window, log)
    try:
        r, hist = ndx.run_ndx_backtest(cpm_panel, ndx_panel, EXT_START,
                                       min(END, cpm_panel.index[-1]))
    finally:
        ndx.compute_ndx_weights = orig
    return r, hist, log


# ----------------------------- execution-cost metrics -----------------------
def turnover_events(hist, clean_start, eps=1e-6):
    """From the monthly target-weight history (clean window), compute:
      turnover_ann            : one-way annualized turnover (sum|dw|/2 * 12)
      pos_change_events_yr    : #assets with |dw|>eps per month, annualized (incl safe)
                                -> the practical execution-leg count (CONT re-trims
                                   every held name monthly; SLOT/NONE only on flips)
      name_flip_events_yr     : #risky names that ENTER or EXIT the held set per
                                month, annualized (whole-name buys+sells)
    All computed over consecutive transitions (initial from-empty excluded) so the
    contrast is apples-to-apples across cells.
    """
    h = [e for e in hist if e["sig_d"] >= clean_start]
    if len(h) < 2:
        return {"turnover_ann": float("nan"), "pos_change_events_yr": float("nan"),
                "name_flip_events_yr": float("nan"), "n_months": 0}
    prev = h[0]["weights"]
    to_tot, ev_tot, flip_tot, n = 0.0, 0, 0, 0
    for e in h[1:]:
        w = e["weights"]
        keys = set(w) | set(prev)
        to_tot += 0.5 * sum(abs(w.get(k, 0.0) - prev.get(k, 0.0)) for k in keys)
        ev_tot += sum(1 for k in keys if abs(w.get(k, 0.0) - prev.get(k, 0.0)) > eps)
        for k in keys:
            if k in SAFE_SET:
                continue
            held_now = w.get(k, 0.0) > eps
            held_prev = prev.get(k, 0.0) > eps
            if held_now != held_prev:
                flip_tot += 1
        n += 1
        prev = w
    return {
        "turnover_ann": to_tot / n * 12.0,
        "pos_change_events_yr": ev_tot / n * 12.0,
        "name_flip_events_yr": flip_tot / n * 12.0,
        "n_months": n,
    }


def slot_changes_per_year(log, clean_start):
    """Average #n_risky transitions per year (SLOT only; n_risky not None)."""
    cs = pd.Timestamp(clean_start)
    on = [e for e in log if e.get("n_risky") is not None
          and pd.Timestamp(e["sig_d"]) >= cs]
    if len(on) < 2:
        return float("nan")
    changes = sum(1 for a, b in zip(on[:-1], on[1:]) if a["n_risky"] != b["n_risky"])
    span_years = (pd.Timestamp(on[-1]["sig_d"]) - pd.Timestamp(on[0]["sig_d"])).days / 365.25
    return changes / span_years if span_years > 0 else float("nan")


def exposure_stats(log, clean_start):
    """Mean equity exposure + de-risk frequency (clean ON-months only)."""
    cs = pd.Timestamp(clean_start)
    on = [e for e in log if e["rv"] is not None and pd.Timestamp(e["sig_d"]) >= cs]
    if not on:
        return {"n_on": 0, "mean_equity_exposure": float("nan"),
                "frac_derisk": float("nan"), "avg_rv": float("nan"),
                "avg_scale": float("nan")}
    eq = np.array([e["equity_exposure"] for e in on])
    sc = np.array([e["scale"] for e in on])
    rv = np.array([e["rv"] for e in on])
    return {
        "n_on": len(on),
        "mean_equity_exposure": float(eq.mean()),
        "frac_derisk": float((sc < 0.999).mean()),
        "avg_rv": float(rv.mean()),
        "avg_scale": float(sc.mean()),
    }
