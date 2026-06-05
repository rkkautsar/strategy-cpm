# -*- coding: utf-8 -*-
"""NDX sleeve TOP-5 DISCRETE drop-lowest-momentum slot-replacement vol-target:
EXPANDING-WINDOW EXTERNAL PARENT-INDEX (QQQ) target estimator.

This is the SYNTHESIS of the two best prior ideas (see qqq_harness for context):
  * EXTERNAL / below-basket-vol : QQQ parent-index vol (~0.18-0.25) sits
    structurally BELOW the concentrated top-5 basket vol (~0.45). An external
    target below basket vol is the only family that ever de-risked
    (FIXED-0.25 worked; all self-referential targets failed).
  * EXPANDING / contamination-free : a single crash year (2020) barely moves a
    ~20yr expanding mean, so the target does NOT stay inflated through 2021 the
    way any trailing-252d measure does. Trailing-252d QQQ (QQQ_LEVEL) FAILED to
    protect 2021 precisely because 2020 inflated its 252d window all through 2021.

MODE QQQ_EXPAND:
  qexp = EXPANDING-window MEAN of completed-month QQQ realized vol, inception->t-1
  target = mult * qexp
  scale  = min(1, target / basket_RV_short)
  -> de-risk the basket toward (mult x) the parent index's LONG-RUN average vol.

  mult is an a-priori risk dial mapping the conditional-vs-chronic-drag frontier:
    m=1.0  target ~ qexp ~0.20 << basket 0.45  -> RISK: chronic drag (always on)
    m=1.25 fills the gap between 1.0 drag and 1.5
    m=1.5  target ~0.30
    m=2.0  target ~0.40 ~ basket 0.45          -> conditional (fires only on
           genuine dispersion blowout above the normal concentration premium)

  HYPOTHESIS: expanding-QQQ avoids the trailing-252d contamination that sank
  QQQ_LEVEL, and with mult it can be simultaneously BELOW basket vol (de-risks),
  CONTAMINATION-FREE (expanding), and CONDITIONAL (mult tunes the trigger) -- the
  first parameter-light candidate that could satisfy all three required
  properties that only a fixed constant satisfied before.

ENGINE: gate / safe rotation / T+1 MOO / 10bps / delist / PIT membership via the
UNMODIFIED ndx_sleeve_live.run_ndx_backtest. Only the TARGET feeding scale
differs. Reuses qqq_harness for the proven modes (NONE/FIXED/ADAPT/EXPAND/
QQQ_LEVEL/QQQ_RATIO) and adds QQQ_EXPAND here.

QQQ DATA: cpm_panel["QQQ"] -- actual ETF adj close 1999-03+, NDX index-level
proxy pre-1999. Cached frozen dataset; absolute levels may differ marginally
from a prod refresh -- apples-to-apples across configs.

Analyst role. Read-only re production. Writes only research/cpm_ndx_voltarget_*.
No commit. mult A-PRIORI {1.0,1.25,1.5,2.0}, NOT optimized; single in-sample.
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
from research.cpm_ndx_voltarget_qqq_harness import (
    _scale, _basket_expanding_rv_mean, K, SAFE_SET, MIN_MONTH_DAYS,
)

SPY = ndx.SPY_TICKER


def _index_expanding_vol(cpm_panel, sig_d):
    """EXPANDING-window long-run mean realized vol of QQQ (parent index) =
    MEAN of ALL completed-month QQQ RV observations from inception to t-1.
    Contamination-resistant: a single crash month barely moves a multi-decade
    mean. None until >= 4 completed monthly obs exist. Falls back to SPY only if
    QQQ entirely absent."""
    for tk in ("QQQ", SPY):
        if tk not in cpm_panel.columns:
            continue
        s = cpm_panel[tk].loc[:sig_d].ffill().pct_change().dropna()
        if s.empty:
            continue
        cur_m = pd.Timestamp(sig_d).to_period("M")
        vals = []
        for m, grp in s.groupby(s.index.to_period("M")):
            if m >= cur_m or len(grp) < MIN_MONTH_DAYS:
                continue
            v = float(grp.std() * np.sqrt(252))
            if np.isfinite(v) and v > 0:
                vals.append(v)
        if len(vals) >= 4:
            return float(np.mean(vals))
    return None


def make_compute(mode, short_win, fixed_target, mult, log):
    """Drop-in for compute_ndx_weights. mode here is QQQ_EXPAND (others handled
    by qqq_harness.make_compute)."""

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

        rv_short = _basket_vol(ndx_panel, sel, sig_d, short_win)
        qexp = _index_expanding_vol(cpm_panel, sig_d)
        target = (mult * qexp) if qexp is not None else None
        scale = _scale(rv_short, target)

        n = int(np.clip(int(np.round(scale * K)), 0, k_avail))
        kept = sel[:n]
        out = {t: 1.0 / K for t in kept}
        eq = n / K
        safe_w = 1.0 - eq
        if safe_w > 1e-9:
            out[safe] = out.get(safe, 0.0) + safe_w
        log.append({"sig_d": str(sig_d.date()), "rv_short": rv_short,
                    "rv_long": qexp, "qqq_rv252": None, "qqq_rv_short": None,
                    "qqq_expand": qexp, "target": target, "scale": scale,
                    "n_risky": n, "equity_exposure": eq})
        return (out, f"NDX_{mode}", {"selected": kept})

    return compute


def run_cell(cpm_panel, ndx_panel, short_win=60, mult=1.0):
    log = []
    orig = ndx.compute_ndx_weights
    ndx.compute_ndx_weights = make_compute("QQQ_EXPAND", short_win, None, mult, log)
    try:
        r, hist = ndx.run_ndx_backtest(cpm_panel, ndx_panel, EXT_START,
                                       min(END, cpm_panel.index[-1]))
    finally:
        ndx.compute_ndx_weights = orig
    return r, hist, log
