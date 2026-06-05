# -*- coding: utf-8 -*-
"""NDX sleeve TOP-5 DISCRETE drop-lowest-momentum slot-replacement vol-target:
ADAPTIVE-MEDIAN target estimator.

  target = PERCENTILE (default median, 50th) of the trailing N MONTHLY realized-
           vol observations (one RV per calendar month, robust over last N months)
  scale  = min(1, target / RV_short)          (de-risk-only, cap 1.0)
  n_risky= round(scale * 5) clipped to [0, k_avail]
  drop the (5 - n) LOWEST-momentum names to safe; keep top-n EW each at 1/5.

HYPOTHESIS: prior ADAPT-RV252 (target = trailing 252d MEAN basket vol) gave ZERO
DD protection because by 2021 the trailing 1yr was already high-vol (2020
contamination) so RV252~RV20, ratio~1, never de-risks. MEDIAN is ROBUST to a
handful of elevated recent months -> reference stays LOWER -> target/RV_short
smaller -> de-risks more readily. Test whether the robust estimator recovers
FIXED's 2021 floor while staying parameter-free, or whether the trailing-relative
contamination still kills it (delayed, once the high-vol regime persists).

Analyst role. Read-only re production (ndx_sleeve_live.py / prod / voltarget /
memo NOT edited). Writes only research/cpm_ndx_voltarget_median_*. No commit.

ENGINE REUSE: monkeypatch ndx_sleeve_live.compute_ndx_weights; call the
UNMODIFIED ndx_sleeve_live.run_ndx_backtest (gate TIP+SPY-trend+SPY RV20<RV252,
safe rotation, T+1 MOO, 10bps/side, delisting haircut, PIT membership). Reuses
_gate_and_candidates / _partial_safe_pack / _basket_vol and the cost/exposure
helpers + bootstrap from the spec harness so references are byte-identical.
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
from research.cpm_ndx_voltarget import _basket_vol

SPY = ndx.SPY_TICKER
K = 5
SAFE_SET = set(SAFE_POOL) | {CASH_TICKER}
MIN_MONTH_DAYS = 15            # min trading days for a month's RV to count


def _scale(rv_short, target):
    if (rv_short is None or not np.isfinite(rv_short) or rv_short <= 0
            or target is None or not np.isfinite(target) or target <= 0):
        return 1.0
    return float(np.clip(target / rv_short, 0.0, 1.0))


def _basket_monthly_rv_pct(ndx_panel, sel, sig_d, n_months, pct=50.0):
    """PERCENTILE of the trailing `n_months` MONTHLY realized-vol observations.

    One RV per completed calendar month = annualized std of that month's daily
    EW-basket returns (>= MIN_MONTH_DAYS days). Only months strictly BEFORE the
    sig_d month are used (lagged/implementable). Returns None if < ~half the
    requested months are available.
    """
    px = ndx_panel[sel].loc[:sig_d].ffill()
    rets = px.pct_change().dropna(how="all")
    basket = rets.mean(axis=1).dropna()
    if basket.empty:
        return None
    cur_m = pd.Timestamp(sig_d).to_period("M")
    by_m = basket.groupby(basket.index.to_period("M"))
    obs = []
    for m, grp in by_m:
        if m >= cur_m:                         # exclude current (partial) month
            continue
        if len(grp) < MIN_MONTH_DAYS:
            continue
        v = float(grp.std() * np.sqrt(252))
        if np.isfinite(v) and v > 0:
            obs.append((m, v))
    if len(obs) < max(4, n_months // 2):
        return None
    obs.sort(key=lambda t: t[0])
    vals = [v for _, v in obs[-n_months:]]
    return float(np.percentile(vals, pct))


def _basket_expanding_rv_mean(ndx_panel, sel, sig_d):
    """EXPANDING-window long-run average realized vol = MEAN of ALL completed
    monthly RV observations from inception up to t-1 (lookback expands each
    month, never resets). Academic parameter-free anchor (Bongaerts-Kang-van
    Dijk 2020). None until >= 4 monthly observations exist.
    """
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


def make_compute(mode, short_win, fixed_target, n_months, pct, log):
    """Drop-in for compute_ndx_weights. Modes:
      NONE   scale=1
      FIXED  target=fixed_target (absolute)
      ADAPT  target=RV252 (trailing-252d MEAN basket vol) -- prior failure ref
      MEDIAN target=percentile(trailing n_months monthly RV), pct=pct
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
                        "target": None, "scale": 1.0, "n_risky": k_avail,
                        "equity_exposure": risky_fraction})
            return (base, "NDX_NONE", {"selected": sel})

        rv_short = _basket_vol(ndx_panel, sel, sig_d, short_win)
        if mode == "FIXED":
            target, rv_long = fixed_target, None
        elif mode == "ADAPT":
            rv_long = _basket_vol(ndx_panel, sel, sig_d, 252)
            target = rv_long
        elif mode == "MEDIAN":
            rv_long = _basket_monthly_rv_pct(ndx_panel, sel, sig_d, n_months, pct)
            target = rv_long
        elif mode == "EXPAND":
            rv_long = _basket_expanding_rv_mean(ndx_panel, sel, sig_d)
            target = rv_long
        else:
            raise ValueError(mode)

        scale = _scale(rv_short, target)
        n = int(np.clip(int(np.round(scale * K)), 0, k_avail))
        kept = sel[:n]
        out = {t: 1.0 / K for t in kept}
        eq = n / K
        safe_w = 1.0 - eq
        if safe_w > 1e-9:
            out[safe] = out.get(safe, 0.0) + safe_w
        log.append({"sig_d": str(sig_d.date()), "rv_short": rv_short, "rv_long": rv_long,
                    "target": target, "scale": scale, "n_risky": n,
                    "equity_exposure": eq})
        return (out, f"NDX_{mode}", {"selected": kept})

    return compute


def run_cell(cpm_panel, ndx_panel, mode, short_win=60, fixed_target=0.30,
             n_months=12, pct=50.0):
    log = []
    orig = ndx.compute_ndx_weights
    ndx.compute_ndx_weights = make_compute(mode, short_win, fixed_target,
                                           n_months, pct, log)
    try:
        r, hist = ndx.run_ndx_backtest(cpm_panel, ndx_panel, EXT_START,
                                       min(END, cpm_panel.index[-1]))
    finally:
        ndx.compute_ndx_weights = orig
    return r, hist, log
