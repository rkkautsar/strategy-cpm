# -*- coding: utf-8 -*-
"""NDX sleeve TOP-5 DISCRETE drop-lowest-momentum slot-replacement vol-target:
EXTERNAL PARENT-INDEX (QQQ) target estimator.

PRIOR CONTEXT (experiments c07cecde, 826b3765): EVERY self-referential target
fails to protect the 2021 unwind (ADAPT-RV252 / MED-12/24/36 / EXPAND all gave
-31.4%, identical to no-de-risk). ROOT CAUSE: a concentrated top-5 momentum
basket has structurally HIGH own-vol (~45%), so any target derived from the
basket's own history sits at ~45% >= current basket vol -> scale~1 -> never
de-risks. Only an EXTERNAL absolute target set BELOW basket structural vol works
(FIXED-0.25: MaxDD -22.4%, 2021 -19.6%).

HYPOTHESIS: QQQ RV252 (parent NDX-100 index ETF, ~18-25% vol) is EXTERNAL +
structurally BELOW basket vol + ADAPTIVE/parameter-free + tracks the broad-market
regime -> it has the two proven-required properties (external + sub-basket-vol).

MODES (all share the engine: gate / safe rotation / T+1 MOO / 10bps / delist /
PIT membership via UNMODIFIED ndx_sleeve_live.run_ndx_backtest; only the TARGET
feeding scale differs):
  NONE        scale=1                                            (prod baseline)
  FIXED       target = fixed_target (absolute)                   (incumbent ref)
  ADAPT       target = RV252 trailing-252d MEAN basket vol       (self-ref FAIL ref)
  EXPAND      target = expanding-window mean of monthly basket RV (self-ref FAIL ref)
  QQQ_LEVEL   target = mult * QQQ_RV252;  scale=min(1, target/basket_RV_short)
              -> scale basket DOWN to (mult x) the parent index's vol LEVEL.
              mult is an interpretable risk dial: "run the sleeve at mult x the
              parent-index vol". mult>1 lifts target toward the basket's natural
              vol so it only de-risks when basket vol exceeds mult*QQQ (i.e. when
              concentration/dispersion blows out beyond the normal premium =
              CONDITIONAL crash response, not a permanent ~0.5x drag).
  QQQ_RATIO   scale=min(1, QQQ_RV252 / QQQ_RV_short)
              -> de-risk the basket when the BROAD MARKET regime is high-vol
              (QQQ short vol > QQQ long vol). Pure parameter-free market-regime
              signal. Distinct from QQQ_LEVEL: level scales to QQQ's vol LEVEL,
              ratio scales by QQQ's own vol REGIME.

QQQ DATA: cpm_panel["QQQ"] (data/qqq_stitched_daily.csv). Actual QQQ ETF adjusted
close from 1999-03; stitched NDX index-level proxy 1985-10..1999-03. Equivalent
for realized-vol purposes. PIT caveat: cached frozen dataset; absolute levels may
differ marginally from a prod refresh -- apples-to-apples across configs.

Analyst role. Read-only re production (ndx_sleeve_live.py / prod / voltarget /
memo NOT edited). Writes only research/cpm_ndx_voltarget_qqq_*. No commit.
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
    _gate_and_candidates, _partial_safe_pack, EXT_START, END,
)
from research.cpm_ndx_voltarget import _basket_vol, _index_vol

SPY = ndx.SPY_TICKER
K = 5
SAFE_SET = set(SAFE_POOL) | {CASH_TICKER}
MIN_MONTH_DAYS = 15


def _scale(rv_short, target):
    if (rv_short is None or not np.isfinite(rv_short) or rv_short <= 0
            or target is None or not np.isfinite(target) or target <= 0):
        return 1.0
    return float(np.clip(target / rv_short, 0.0, 1.0))


def _basket_expanding_rv_mean(ndx_panel, sel, sig_d):
    """EXPANDING-window long-run average realized vol = MEAN of ALL completed
    monthly RV observations from inception up to t-1 (academic parameter-free
    anchor, Bongaerts-Kang-van Dijk 2020). None until >= 4 monthly obs exist."""
    px = ndx_panel[sel].loc[:sig_d].ffill()
    rets = px.pct_change().dropna(how="all")
    basket = rets.mean(axis=1).dropna()
    if basket.empty:
        return None
    cur_m = pd.Timestamp(sig_d).to_period("M")
    vals = []
    for m, grp in basket.groupby(basket.index.to_period("M")):
        if m >= cur_m or len(grp) < MIN_MONTH_DAYS:
            continue
        v = float(grp.std() * np.sqrt(252))
        if np.isfinite(v) and v > 0:
            vals.append(v)
    if len(vals) < 4:
        return None
    return float(np.mean(vals))


def make_compute(mode, short_win, fixed_target, mult, log):
    """Drop-in for compute_ndx_weights.

    mode: NONE / FIXED / ADAPT / EXPAND / QQQ_LEVEL / QQQ_RATIO
    short_win: trailing daily window for the SHORT realized vol (20 or 60)
    fixed_target: absolute target (FIXED only)
    mult: multiplier on QQQ_RV252 (QQQ_LEVEL only); the risk dial.
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
        sel = names[:K]
        k_avail = len(sel)
        rw = {t: 1.0 / k_avail for t in sel}
        base = _partial_safe_pack(rw, k_avail, safe, K)
        risky_fraction = min(k_avail, K) / K

        if mode == "NONE":
            log.append({"sig_d": str(sig_d.date()), "rv_short": None, "rv_long": None,
                        "qqq_rv252": None, "qqq_rv_short": None,
                        "target": None, "scale": 1.0, "n_risky": k_avail,
                        "equity_exposure": risky_fraction})
            return (base, "NDX_NONE", {"selected": sel})

        rv_short = _basket_vol(ndx_panel, sel, sig_d, short_win)  # basket short vol
        qqq_rv252 = None
        qqq_rv_short = None

        if mode == "FIXED":
            target, rv_long = fixed_target, None
        elif mode == "ADAPT":
            rv_long = _basket_vol(ndx_panel, sel, sig_d, 252)
            target = rv_long
        elif mode == "EXPAND":
            rv_long = _basket_expanding_rv_mean(ndx_panel, sel, sig_d)
            target = rv_long
        elif mode == "QQQ_LEVEL":
            qqq_rv252 = _index_vol(cpm_panel, sig_d, 252)
            rv_long = qqq_rv252
            target = (mult * qqq_rv252) if qqq_rv252 is not None else None
        elif mode == "QQQ_RATIO":
            qqq_rv252 = _index_vol(cpm_panel, sig_d, 252)
            qqq_rv_short = _index_vol(cpm_panel, sig_d, short_win)
            rv_long = qqq_rv252
            # scale = min(1, QQQ_RV252 / QQQ_RV_short): de-risk when broad-market
            # short vol > long vol. Computed directly on QQQ (not basket).
            target = None
        else:
            raise ValueError(mode)

        if mode == "QQQ_RATIO":
            scale = _scale(qqq_rv_short, qqq_rv252)   # min(1, long/short) on QQQ
        else:
            scale = _scale(rv_short, target)

        n = int(np.clip(int(np.round(scale * K)), 0, k_avail))
        kept = sel[:n]
        out = {t: 1.0 / K for t in kept}
        eq = n / K
        safe_w = 1.0 - eq
        if safe_w > 1e-9:
            out[safe] = out.get(safe, 0.0) + safe_w
        log.append({"sig_d": str(sig_d.date()), "rv_short": rv_short, "rv_long": rv_long,
                    "qqq_rv252": qqq_rv252, "qqq_rv_short": qqq_rv_short,
                    "target": target, "scale": scale, "n_risky": n,
                    "equity_exposure": eq})
        return (out, f"NDX_{mode}", {"selected": kept})

    return compute


def run_cell(cpm_panel, ndx_panel, mode, short_win=60, fixed_target=0.30, mult=1.0):
    log = []
    orig = ndx.compute_ndx_weights
    ndx.compute_ndx_weights = make_compute(mode, short_win, fixed_target, mult, log)
    try:
        r, hist = ndx.run_ndx_backtest(cpm_panel, ndx_panel, EXT_START,
                                       min(END, cpm_panel.index[-1]))
    finally:
        ndx.compute_ndx_weights = orig
    return r, hist, log
