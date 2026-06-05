# -*- coding: utf-8 -*-
"""NDX sleeve TOP-5 DISCRETE drop-lowest-momentum slot-replacement vol-target:
WHICH VOL TARGET drives the scale signal -- FIXED absolute level vs ADAPTIVE
(target = trailing 252d sleeve realized vol)?

Analyst role. Read-only re production (ndx_sleeve_live.py / prod / voltarget /
breadth-prod / memo NOT edited). Writes only research/cpm_ndx_voltarget_spec_*.
No commit.

MECHANISM (fixed across all configs -- the CHOSEN de-risk = TOP-5 SLOT discrete):
  scale     = min(1, target / RV_short)                 (de-risk-only, cap 1.0)
  n_risky   = round(scale * 5)  clipped to [0, k_avail]
  drop the (5 - n) LOWEST-momentum names to safe; keep top-n EW each at 1/5.
  Re-evaluated monthly; signals lagged through sig_d; T+1 MOO; 10bps/side.

THE VARIABLE = the TARGET spec feeding `scale`:
  NONE      no de-risk (scale=1 always)                          baseline (=prod top5 EW)
  FIXED     target = a-priori absolute level (0.20..0.40)        ABSOLUTE cap
            -> de-risks in ANY high-absolute-vol regime
  ADAPT     target = trailing RV252 of the (current top-5) sleeve basket
            -> scale = min(1, RV252/RV_short)  = RELATIVE / regime-normalized
            -> this is the GRADED CONTINUOUS GENERALIZATION of the prod gate
               (prod gate = binary SPY RV20<RV252; ADAPT(w20) grades the SAME
                RV20<RV252 comparison at the basket level into a dial)
  BINARY    target = RV252 but BINARY: n=5 if RV_short<RV252 else n=0
            -> the binary-gate analog at basket level (graded-vs-binary contrast)

RV_short window: FIXED incumbent = 60d. ADAPT tested at 20d (gate-consistent,
graded-gate) AND 60d (voltarget-consistent). RV252 = trailing 252d basket vol.

ENGINE REUSE: monkeypatch ndx_sleeve_live.compute_ndx_weights, call the
UNMODIFIED ndx_sleeve_live.run_ndx_backtest (gate TIP+SPY-trend+SPY RV20<RV252,
safe rotation, T+1 MOO, 10bps/side, delisting haircut, PIT membership). Reuses
_gate_and_candidates / _partial_safe_pack / _basket_vol and the B=2000 block=21
seed=42 paired block bootstrap. NONE@top5 reproduces the prod top-5 EW anchor.
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
K = 5
LONG_WIN = 252                                 # trailing window for ADAPT/BINARY target
SAFE_SET = set(SAFE_POOL) | {CASH_TICKER}      # excluded from risky-name flip events


def _scale(rv_short, target):
    """De-risk-only vol-target scale = clip(target/rv_short, 0, 1)."""
    if (rv_short is None or not np.isfinite(rv_short) or rv_short <= 0
            or target is None or not np.isfinite(target) or target <= 0):
        return 1.0
    return float(np.clip(target / rv_short, 0.0, 1.0))


def make_compute(mode, short_win, fixed_target, log):
    """Drop-in replacement for ndx_sleeve_live.compute_ndx_weights.

    Selection = momentum top-5 (PROD gate/PIT). All de-risk modes use the SAME
    discrete drop-lowest-momentum slot-replacement; only the TARGET feeding the
    scale signal differs:
      NONE   scale=1
      FIXED  target=fixed_target (absolute)
      ADAPT  target=RV252 (sleeve basket), graded scale=min(1,RV252/RV_short)
      BINARY target=RV252 but n=5 if RV_short<RV252 else 0 (binary gate analog)
    """

    def compute(cpm_panel, ndx_panel, sig_d):
        status, safe, cands = _gate_and_candidates(cpm_panel, ndx_panel, sig_d)
        if status == "OFF":
            return ({safe: 1.0}, "GATE_OFF", {"selected": []})
        if status == "PROXY":
            return ({SPY: 1.0}, "NDX_FALLBACK_SPY", {"selected": [SPY]})
        if not cands:
            return ({safe: 1.0}, "NDX_NO_POS", {"selected": []})

        names = [t for t, _ in cands]
        sel = names[:K]                        # momentum top-5
        k_avail = len(sel)
        rw = {t: 1.0 / k_avail for t in sel}
        base = _partial_safe_pack(rw, k_avail, safe, K)
        risky_fraction = min(k_avail, K) / K

        if mode == "NONE":
            log.append({"sig_d": str(sig_d.date()), "rv_short": None, "rv_long": None,
                        "target": None, "scale": 1.0, "n_risky": k_avail,
                        "equity_exposure": risky_fraction})
            return (base, "NDX_NONE", {"selected": sel})

        rv_short = _basket_vol(ndx_panel, sel, sig_d, short_win)
        if mode == "FIXED":
            target = fixed_target
            rv_long = None
            scale = _scale(rv_short, target)
            n = int(np.clip(int(np.round(scale * K)), 0, k_avail))
        elif mode in ("ADAPT", "BINARY"):
            rv_long = _basket_vol(ndx_panel, sel, sig_d, LONG_WIN)
            target = rv_long
            if mode == "ADAPT":
                scale = _scale(rv_short, target)
                n = int(np.clip(int(np.round(scale * K)), 0, k_avail))
            else:  # BINARY: full on if short<long else full off
                if (rv_short is None or rv_long is None
                        or not np.isfinite(rv_short) or not np.isfinite(rv_long)):
                    scale, n = 1.0, k_avail
                elif rv_short < rv_long:
                    scale, n = 1.0, k_avail
                else:
                    scale, n = 0.0, 0
        else:
            raise ValueError(mode)

        kept = sel[:n]                         # keep top-n momentum, drop lowest mom
        out = {t: 1.0 / K for t in kept}       # each kept name = 1/K of book
        eq = n / K
        safe_w = 1.0 - eq
        if safe_w > 1e-9:
            out[safe] = out.get(safe, 0.0) + safe_w
        log.append({"sig_d": str(sig_d.date()), "rv_short": rv_short, "rv_long": rv_long,
                    "target": target, "scale": scale, "n_risky": n,
                    "equity_exposure": eq})
        return (out, f"NDX_{mode}", {"selected": kept})

    return compute


def run_cell(cpm_panel, ndx_panel, mode, short_win=60, fixed_target=0.30):
    log = []
    orig = ndx.compute_ndx_weights
    ndx.compute_ndx_weights = make_compute(mode, short_win, fixed_target, log)
    try:
        r, hist = ndx.run_ndx_backtest(cpm_panel, ndx_panel, EXT_START,
                                       min(END, cpm_panel.index[-1]))
    finally:
        ndx.compute_ndx_weights = orig
    return r, hist, log


# ----------------------------- execution-cost metrics -----------------------
def turnover_events(hist, clean_start, eps=1e-6):
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
            if (w.get(k, 0.0) > eps) != (prev.get(k, 0.0) > eps):
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
    cs = pd.Timestamp(clean_start)
    on = [e for e in log if e.get("n_risky") is not None
          and pd.Timestamp(e["sig_d"]) >= cs]
    if len(on) < 2:
        return float("nan")
    changes = sum(1 for a, b in zip(on[:-1], on[1:]) if a["n_risky"] != b["n_risky"])
    span = (pd.Timestamp(on[-1]["sig_d"]) - pd.Timestamp(on[0]["sig_d"])).days / 365.25
    return changes / span if span > 0 else float("nan")


def exposure_stats(log, clean_start):
    """Mean exposure, de-risk freq, and high-absolute-vol-regime exposure split.
    `abs_vol` proxy = rv_short (the absolute realized vol the month is running).
    High-abs-vol regime = rv_short in the top tercile across clean ON-months."""
    cs = pd.Timestamp(clean_start)
    on = [e for e in log if e.get("rv_short") is not None
          and np.isfinite(e["rv_short"]) and pd.Timestamp(e["sig_d"]) >= cs]
    # NONE has rv_short=None -> fall back to equity_exposure only
    if not on:
        on_all = [e for e in log if pd.Timestamp(e["sig_d"]) >= cs
                  and e.get("equity_exposure") is not None]
        eq = np.array([e["equity_exposure"] for e in on_all]) if on_all else np.array([])
        return {"n_on": len(on_all),
                "mean_equity_exposure": float(eq.mean()) if eq.size else float("nan"),
                "frac_derisk": 0.0, "avg_rv_short": float("nan"),
                "avg_scale": 1.0, "mean_exp_hivol": float("nan"),
                "mean_exp_lovol": float("nan"), "hivol_thresh": float("nan")}
    eq = np.array([e["equity_exposure"] for e in on])
    sc = np.array([e["scale"] for e in on])
    rv = np.array([e["rv_short"] for e in on])
    thr = float(np.quantile(rv, 2.0 / 3.0))    # top-tercile abs-vol threshold
    hi = rv >= thr
    lo = ~hi
    return {
        "n_on": len(on),
        "mean_equity_exposure": float(eq.mean()),
        "frac_derisk": float((sc < 0.999).mean()),
        "avg_rv_short": float(rv.mean()),
        "avg_scale": float(sc.mean()),
        "mean_exp_hivol": float(eq[hi].mean()) if hi.any() else float("nan"),
        "mean_exp_lovol": float(eq[lo].mean()) if lo.any() else float("nan"),
        "hivol_thresh": thr,
    }


def exposure_series(log, clean_start):
    """Monthly (date, equity_exposure, rv_short, rv_long, target, scale) for
    time-series character / episode inspection (clean window)."""
    cs = pd.Timestamp(clean_start)
    out = []
    for e in log:
        if pd.Timestamp(e["sig_d"]) < cs:
            continue
        out.append({
            "d": e["sig_d"],
            "exp": e.get("equity_exposure"),
            "rv_s": e.get("rv_short"),
            "rv_l": e.get("rv_long"),
            "tgt": e.get("target"),
            "scale": e.get("scale"),
            "n": e.get("n_risky"),
        })
    return out
