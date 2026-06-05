# -*- coding: utf-8 -*-
"""NDX sleeve: DISCRETE SLOT-REPLACEMENT de-risk vs the CONTINUOUS vol-target dial,
at MATCHED average equity exposure -- isolating the CONCENTRATION effect.

Analyst role. Read-only re production (ndx_sleeve_live.py / prod / memo NOT
edited). Writes only research/cpm_ndx_slotreplace_findings.md (+ .json). No commit.

USER IDEA: instead of shrinking ALL 5 names uniformly (the continuous dial), DROP
THE WEAKEST-RANKED momentum SLOTS to safe. n_risky = round(scale*5), where
scale = min(1, target_vol/realized_vol) is the IDENTICAL monthly basket-vol signal
the continuous dial uses; keep the top-n momentum names EW each at 1/5 = 20% of
book; remaining (5-n)*20% -> safe (SHV/IEF best-of-safe). Re-evaluated monthly.

HYPOTHESIS: at MATCHED average exposure the only difference vs the continuous dial
is CONCENTRATION. Slot-replacement keeps full conviction in the strongest names
and sheds the marginal ones (quality tilt under stress); the continuous dial holds
all 5 smaller (diversified). Slot WINS if the weakest-ranked names crash hardest
in a sleeve-wide unwind; LOSES if it sacrifices diversification / coarse 20%
granularity causes chunky turnover.

ENGINE REUSE: identical to research/cpm_ndx_voltarget.py -- monkeypatch
ndx_sleeve_live.compute_ndx_weights, call the UNMODIFIED run_ndx_backtest (gate
TIP+SPY-trend+SPY-RV, safe rotation, T+1 MOO, 10bps/side, delisting haircut, PIT
membership all identical). The SAME basket-vol scale signal drives both the
continuous dial (CONT) and the slot-replacement (SLOT) variants, so their average
equity exposure is ~matched and the contrast isolates concentration vs shrink-all.

CONFIGS (clean 2008+, gate/safe/T+1/10bps/delist/PIT fixed; basket-vol 60d, t0.30):
  PROD         momentum top-5 EW (scale=1 always)                  (baseline)
  CONT         top-5 EW * scale, freed -> safe, cap 1.0      (incumbent dial)
  SLOT_ROUND       n=round(scale*5) keep, drop LOWEST-MOMENTUM (R1, USER IDEA)
  SLOT_FLOOR       n=floor(scale*5) R1 -- more aggressive de-risk  (sensitivity)
  SLOT_CEIL        n=ceil(scale*5)  R1 -- less aggressive de-risk   (sensitivity)
  SLOT_ROUND_VOL   n=round(scale*5) keep, drop HIGHEST-trailing-VOL (R2)
  SLOT_FLOOR_VOL   n=floor(scale*5) R2                              (sensitivity)
  SLOT_CEIL_VOL    n=ceil(scale*5)  R2                              (sensitivity)

DROP RULE (which of the 5 names go to safe at a given n_risky):
  R1 (MOM): drop the LOWEST-momentum-ranked names first (marginal selection slot).
  R2 (VOL): drop the HIGHEST-trailing-vol names first (lagged, same vol window) --
            coherent with the vol-target OBJECTIVE: sheds the biggest variance
            contributor, cutting more basket vol per slot dropped.
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
from research.cpm_ndx_minvar_cvar import (
    _gate_and_candidates,
    _partial_safe_pack,
    EXT_START,
    CLEAN_START,
    END,
)
from research.cpm_ndx_voltarget import _basket_vol

SPY = ndx.SPY_TICKER
TARGET_BASKET = 0.30   # a-priori annualized basket-vol target (same as voltarget DERISK)
WIN_PRIMARY = 60       # trailing daily-return window for realized vol
K = 5


def _name_vols(ndx_panel, sel, sig_d, window):
    """Per-name annualized trailing vol over `window` daily returns through sig_d
    (lagged, same window as the basket-vol signal). Dict name -> vol; missing/NaN
    names get +inf so they sort to the 'drop-first' end of the vol ranking."""
    px = ndx_panel[sel].loc[:sig_d].ffill()
    rets = px.pct_change().tail(window)
    out = {}
    for t in sel:
        s = rets[t].dropna()
        if len(s) < max(10, window // 2):
            out[t] = float("inf")
            continue
        v = float(s.std() * np.sqrt(252))
        out[t] = v if np.isfinite(v) and v > 0 else float("inf")
    return out


def _scale(rv, target):
    """De-risk-only vol-target scale = clip(target/rv, 0, 1)."""
    if rv is None or not np.isfinite(rv) or rv <= 0:
        return 1.0
    return float(np.clip(target / rv, 0.0, 1.0))


def _n_risky(scale, mode, k_avail):
    """Discrete number of kept momentum slots from the continuous scale."""
    raw = scale * K
    if mode == "round":
        n = int(np.round(raw))
    elif mode == "floor":
        n = int(np.floor(raw))
    elif mode == "ceil":
        n = int(np.ceil(raw))
    else:
        raise ValueError(mode)
    return int(np.clip(n, 0, k_avail))


def make_compute(config, target, window, log):
    """Drop-in replacement for ndx_sleeve_live.compute_ndx_weights.

    PROD selection (momentum top-5). CONT scales all 5 uniformly (continuous dial);
    SLOT_* keep the top-n momentum names EW each at 1/K of book and send the rest
    to safe (discrete slot-replacement). Both driven by the SAME basket-vol scale.
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
        sel = names[:K]                       # momentum top-5 (PROD selection)
        k_avail = len(sel)
        rw = {t: 1.0 / k_avail for t in sel}
        base = _partial_safe_pack(rw, k_avail, safe, K)   # risky sum = k_avail/K
        risky_fraction = min(k_avail, K) / K

        if config == "PROD":
            log.append({"sig_d": str(sig_d.date()), "rv": None, "scale": 1.0,
                        "n_risky": k_avail, "equity_exposure": risky_fraction})
            return (base, "NDX_PROD", {"selected": sel})

        rv = _basket_vol(ndx_panel, sel, sig_d, window)
        scale = _scale(rv, target)

        if config == "CONT":
            # continuous dial: shrink ALL names uniformly, freed weight -> safe
            out = {t: base[t] * scale for t in sel}
            freed = risky_fraction * (1.0 - scale)
            safe_w = base.get(safe, 0.0) + freed
            if abs(safe_w) > 1e-9:
                out[safe] = out.get(safe, 0.0) + safe_w
            eq = risky_fraction * scale
            log.append({"sig_d": str(sig_d.date()), "rv": rv, "scale": scale,
                        "n_risky": None, "equity_exposure": eq})
            return (out, "NDX_CONT", {"selected": sel})

        # SLOT_*: discrete slot-replacement -- drop weakest-ranked names to safe.
        # config = SLOT_<MODE>[_VOL]; MODE in {ROUND,FLOOR,CEIL}; suffix VOL => R2.
        parts = config.split("_")
        mode = parts[1].lower()               # ROUND/FLOOR/CEIL
        rule = "vol" if (len(parts) > 2 and parts[2].upper() == "VOL") else "mom"
        n = _n_risky(scale, mode, k_avail)
        if rule == "vol":
            # keep the n LOWEST-vol names (drop the highest-vol ones first)
            nv = _name_vols(ndx_panel, sel, sig_d, window)
            kept = sorted(sel, key=lambda t: nv[t])[:n]
        else:
            kept = sel[:n]                    # keep top-n momentum (drop lowest mom)
        out = {t: 1.0 / K for t in kept}      # each kept name = 1/K = 20% of book
        eq = n / K
        safe_w = 1.0 - eq                      # remainder to safe
        if safe_w > 1e-9:
            out[safe] = out.get(safe, 0.0) + safe_w
        # realized vol of the KEPT basket (EW) -- coherence check for R2 vs R1
        kept_rv = _basket_vol(ndx_panel, kept, sig_d, window) if kept else None
        log.append({"sig_d": str(sig_d.date()), "rv": rv, "scale": scale,
                    "n_risky": n, "equity_exposure": eq, "kept_rv": kept_rv,
                    "rule": rule})
        return (out, f"NDX_{config}", {"selected": kept})

    return compute


def run_config(cpm_panel, ndx_panel, config, target=TARGET_BASKET, window=WIN_PRIMARY):
    log = []
    orig = ndx.compute_ndx_weights
    ndx.compute_ndx_weights = make_compute(config, target, window, log)
    try:
        r, hist = ndx.run_ndx_backtest(cpm_panel, ndx_panel, EXT_START,
                                       min(END, cpm_panel.index[-1]))
    finally:
        ndx.compute_ndx_weights = orig
    return r, hist, log


def exposure_stats(log, clean_start):
    """Mean equity exposure + de-risk frequency (clean ON-months only)."""
    cs = pd.Timestamp(clean_start)
    on = [e for e in log if e["rv"] is not None and pd.Timestamp(e["sig_d"]) >= cs]
    if not on:
        return {"n_on": 0, "mean_equity_exposure": float("nan"),
                "frac_derisk": float("nan"), "avg_rv": float("nan"),
                "avg_scale": float("nan"), "avg_kept_rv": float("nan")}
    eq = np.array([e["equity_exposure"] for e in on])
    sc = np.array([e["scale"] for e in on])
    rv = np.array([e["rv"] for e in on])
    kept = np.array([e["kept_rv"] for e in on
                     if e.get("kept_rv") is not None and np.isfinite(e["kept_rv"])])
    return {
        "n_on": len(on),
        "mean_equity_exposure": float(eq.mean()),
        "frac_derisk": float((sc < 0.999).mean()),
        "avg_rv": float(rv.mean()),
        "avg_scale": float(sc.mean()),
        "avg_kept_rv": float(kept.mean()) if kept.size else float("nan"),
    }


def slot_changes_per_year(log, clean_start):
    """Average number of slot-count changes (n_risky transitions) per year.
    Only meaningful for SLOT_* configs (n_risky not None)."""
    cs = pd.Timestamp(clean_start)
    on = [e for e in log if e.get("n_risky") is not None
          and pd.Timestamp(e["sig_d"]) >= cs]
    if len(on) < 2:
        return float("nan")
    changes = sum(1 for a, b in zip(on[:-1], on[1:])
                  if a["n_risky"] != b["n_risky"])
    span_years = (pd.Timestamp(on[-1]["sig_d"]) - pd.Timestamp(on[0]["sig_d"])).days / 365.25
    return changes / span_years if span_years > 0 else float("nan")
