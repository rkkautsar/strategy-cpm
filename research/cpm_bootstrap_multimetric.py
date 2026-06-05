# -*- coding: utf-8 -*-
"""Multi-metric paired block bootstrap (research-only helper).

Byte-identical resampling to research.cpm_weighting_corr.paired_block_bootstrap
(B=2000, block=21, seed=42) -- same rng seed, same block-index construction --
so dSharpe matches that helper exactly. ADDS path-INDEPENDENT downside metrics
that bootstrap as cleanly as Sharpe:

  dSORTINO : (mean(r)*252) / (downside_dev*sqrt(252))
             downside_dev = sqrt(mean( min(r,0)^2 ))  [threshold 0]
  dCVAR    : (mean(r)*252) / |mean(worst 5% of r)|     (Expected-Shortfall ratio)

WHY NOT bootstrap Calmar/Martin for classification: both are PATH-DEPENDENT
(running-max drawdown / Ulcer). Block resampling shuffles the drawdown path, so
their CIs are soft/unreliable. Sortino and CVaR are distributional /
order-invariant -> stable CIs. Calmar/Martin are reported as POINT-ESTIMATE
context only (computed on the full clean series, not classified on these CIs).

Does NOT modify any production or shared script.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import cpm_live


def _sortino_ann(x, cash_vals):
    """Annualized Sortino. Numerator = annualized mean total return; denom =
    annualized downside deviation (threshold 0). Order-invariant."""
    x = np.asarray(x, dtype=float)
    if x.size == 0:
        return float("nan")
    neg = np.minimum(x, 0.0)
    dd = np.sqrt(np.mean(neg ** 2))
    if dd <= 0:
        return float("nan")
    return (x.mean() * 252.0) / (dd * np.sqrt(252.0))


def _cvar_ratio_ann(x, q=0.05):
    """Annualized Expected-Shortfall ratio: annualized mean return divided by
    |mean of worst q-tail returns|. Order-invariant."""
    x = np.asarray(x, dtype=float)
    n = x.size
    if n == 0:
        return float("nan")
    k = max(1, int(np.floor(q * n)))
    worst = np.sort(x)[:k]
    es = np.mean(worst)
    if es >= 0:
        return float("nan")
    return (x.mean() * 252.0) / abs(es)


def _summ(arr):
    arr = np.asarray(arr, dtype=float)
    finite = arr[np.isfinite(arr)]
    return {
        "mean": float(finite.mean()) if finite.size else float("nan"),
        "ci_lo": float(np.percentile(finite, 2.5)) if finite.size else float("nan"),
        "ci_hi": float(np.percentile(finite, 97.5)) if finite.size else float("nan"),
        "p_gt0": float((finite > 0).mean()) if finite.size else float("nan"),
        "n_finite": int(finite.size),
    }


def paired_block_bootstrap_mm(ra, rb, cash, B=2000, block=21, seed=42):
    """Return classification blocks (dSharpe / dSortino / dCVaR) plus
    path-dependent context blocks (dCalmar / dMartin / dMaxDD).

    Resampling identical to cpm_weighting_corr.paired_block_bootstrap. Only
    dSharpe/dSortino/dCVaR should drive SIGNIFICANT/MARGINAL/NOISE calls;
    dCalmar/dMartin are reported for transparency but their CIs are soft.
    """
    common = ra.index.intersection(rb.index)
    a = ra.loc[common].values
    b = rb.loc[common].values
    cash_vals = (cash.reindex(common).fillna(0.0).values
                 if cash is not None else np.zeros(len(common)))
    n = len(a)
    rng = np.random.default_rng(seed)
    nb = int(np.ceil(n / block))

    def path_stats(x):
        s = pd.Series(x, index=common)
        m = cpm_live.perf_metrics(s, cash)
        return m.get("sharpe"), m.get("calmar"), m.get("martin"), m.get("max_drawdown")

    dS, dSor, dCv = [], [], []
    dC, dM, dD = [], [], []
    for _ in range(B):
        starts = rng.integers(0, n, size=nb)
        idx = np.concatenate([np.arange(s, s + block) % n for s in starts])[:n]
        xa, xb = a[idx], b[idx]
        ca = cash_vals[idx]
        # path-independent (classification)
        dSor.append(_sortino_ann(xa, ca) - _sortino_ann(xb, ca))
        dCv.append(_cvar_ratio_ann(xa) - _cvar_ratio_ann(xb))
        # path-dependent (context only)
        sA, cA, mA, dA = path_stats(xa)
        sB, cB, mB, dB = path_stats(xb)
        dS.append(sA - sB)
        dC.append(cA - cB)
        dM.append(mA - mB)
        dD.append(dA - dB)

    return {
        # classification metrics (clean CIs)
        "dSharpe": _summ(dS),
        "dSortino": _summ(dSor),
        "dCVaR": _summ(dCv),
        # path-dependent context (soft CIs -- do NOT classify)
        "dCalmar": _summ(dC),
        "dMartin": _summ(dM),
        "dMaxDD": _summ(dD),
    }
