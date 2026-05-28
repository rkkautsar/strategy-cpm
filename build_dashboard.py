#!/usr/bin/env python3
"""
Build a single-file mobile-friendly static HTML dashboard for CPM strategy.

Recomputes both sleeves + benchmarks and bakes
matplotlib charts + tables into one HTML file.

Usage:
    python build_dashboard.py
    python build_dashboard.py --start 2010-01-01 --out /tmp/cpm_dashboard.html
"""
from __future__ import annotations

import argparse
import re
import datetime as dt
import sys
from itertools import combinations
from pathlib import Path

import base64
import io

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import cpm_live as cpm_module
from cpm_live import (
    RISKY_UNIVERSE, SAFE_POOL,
    CANARY_ASSETS, DEFAULT_CASH,
    CORR_LOOKBACK_DAYS, COST_BPS_PER_SIDE,
    TOP_K_CANDIDATES,
    load_panel, run_cpm_backtest,
    perf_metrics, compute_target_weights, sig_13612U,
)
from bull_qqq_live import (
    run_bull_qqq_backtest, compute_bull_qqq_weights,
    BULL_TICKER, CASH_TICKER,
)

# Production blend: 60% CPM + 20% BULL-SPY + 20% NDX
CPM_W = 0.60
BULL_W = 0.20
NDX_W = 0.20
BULL_BLEND = BULL_W  # alias used by chart helpers below

# matplotlib styling
plt.rcParams.update({
    "figure.facecolor": "white",
    "axes.facecolor": "white",
    "axes.edgecolor": "#cccccc",
    "axes.labelcolor": "#444",
    "axes.grid": True,
    "grid.color": "#eeeeee",
    "grid.linewidth": 0.6,
    "xtick.color": "#666",
    "ytick.color": "#666",
    "font.family": "sans-serif",
    "font.size": 10,
    "legend.frameon": False,
    "legend.fontsize": 9,
    "axes.titlesize": 11,
    "axes.titleweight": "600",
    "axes.spines.top": False,
    "axes.spines.right": False,
})


# ---------- Helpers ----------

def fmt_pct(v, decimals=2, signed=False):
    if pd.isna(v): return "--"
    sign = "+" if signed and v > 0 else ""
    return f"{sign}{v*100:.{decimals}f}%"

def fmt_num(v, decimals=2, signed=False):
    if pd.isna(v): return "--"
    sign = "+" if signed and v > 0 else ""
    return f"{sign}{v:.{decimals}f}"

def fig_to_html(fig, alt="chart"):
    """Save matplotlib figure as inline SVG (vector, crisp at any resolution).
    Strips XML/DOCTYPE/width/height so CSS can scale responsively via viewBox."""
    import re
    buf = io.StringIO()
    fig.savefig(buf, format="svg", bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)
    svg = buf.getvalue()
    if svg.startswith("<?xml"):
        svg = svg[svg.find("?>") + 2:].lstrip()
    if svg.startswith("<!DOCTYPE"):
        svg = svg[svg.find(">") + 1:].lstrip()
    # Strip explicit width="..." and height="..." from <svg> tag so CSS
    # `width:100%` + the existing viewBox attribute drive responsive scaling.
    svg = re.sub(r'(<svg[^>]*?)\s+width="[^"]*"', r'\1', svg, count=1)
    svg = re.sub(r'(<svg[^>]*?)\s+height="[^"]*"', r'\1', svg, count=1)
    return f'<div class="chart" role="img" aria-label="{alt}">{svg}</div>'


# ---------- Peer benchmarks ----------

def faber_gtaa5(panel, start, end):
    universe = ["SPY", "EFA", "IEF", "VNQ", "DBC"]
    cols = [c for c in universe if c in panel.columns]
    if "SHV" not in panel.columns: return pd.Series(dtype=float)
    cols += ["SHV"]
    close = panel[cols]; monthly = close.resample("ME").last()
    monthly_idx = pd.DataFrame({"x":1}, index=close.index).groupby(pd.Grouper(freq="ME")).tail(1)
    dates = monthly_idx.index[(monthly_idx.index>=start)&(monthly_idx.index<=end)].tolist()
    weights_map = {}
    for d in dates:
        m = monthly.loc[:d]
        if len(m) < 11: weights_map[d] = {"SHV": 1.0}; continue
        sma = m.rolling(10).mean().iloc[-1]; last = m.iloc[-1]
        in_u = [a for a in universe if a in last.index and pd.notna(sma.get(a)) and pd.notna(last[a]) and last[a] > sma[a]]
        w = {a: 0.20 for a in in_u}
        if 5 - len(in_u) > 0: w["SHV"] = 0.20*(5-len(in_u))
        weights_map[d] = w if w else {"SHV": 1.0}
    daily_ret = close.ffill().pct_change()
    out = pd.Series(0.0, index=close.index)
    for i, d in enumerate(dates):
        nxt = dates[i+1] if i+1 < len(dates) else end
        seg = close.index[(close.index > d) & (close.index <= nxt)]
        w = weights_map.get(d, {})
        if not w: continue
        cs = [c for c in w if c in daily_ret.columns]
        if not cs: continue
        out.loc[seg] = daily_ret.loc[seg, cs].mul(pd.Series({k: w[k] for k in cs}), axis=1).sum(axis=1, min_count=1).fillna(0.0)
    return out.loc[(out.index>=start)&(out.index<=end)]

def keller_vaa_g4(panel, start, end):
    offensive = ["SPY","EFA","EEM","AGG_stitched"]
    defensive = ["SHV","IEF"]
    cols = list(dict.fromkeys(offensive + defensive))
    cols = [c for c in cols if c in panel.columns]
    close = panel[cols]; monthly = close.resample("ME").last()
    monthly_idx = pd.DataFrame({"x":1}, index=close.index).groupby(pd.Grouper(freq="ME")).tail(1)
    dates = monthly_idx.index[(monthly_idx.index>=start)&(monthly_idx.index<=end)].tolist()
    weights_map = {}
    for d in dates:
        m = monthly.loc[:d]
        scores_off = {a: sig_13612U(m[a]) for a in offensive if a in m.columns}
        if any(pd.isna(v) for v in scores_off.values()):
            weights_map[d] = {"SHV":1.0}; continue
        if all(v > 0 for v in scores_off.values()):
            best = max(scores_off, key=scores_off.get)
            weights_map[d] = {best:1.0}
        else:
            sd = {a: sig_13612U(m[a]) for a in defensive if a in m.columns}
            valid = {k:v for k,v in sd.items() if pd.notna(v)}
            best = max(valid, key=valid.get) if valid else "SHV"
            weights_map[d] = {best:1.0}
    daily_ret = close.ffill().pct_change()
    out = pd.Series(0.0, index=close.index)
    for i, d in enumerate(dates):
        nxt = dates[i+1] if i+1 < len(dates) else end
        seg = close.index[(close.index > d) & (close.index <= nxt)]
        w = weights_map.get(d, {})
        if not w: continue
        cs = [c for c in w if c in daily_ret.columns]
        if not cs: continue
        out.loc[seg] = daily_ret.loc[seg, cs].mul(pd.Series({k: w[k] for k in cs}), axis=1).sum(axis=1, min_count=1).fillna(0.0)
    return out.loc[(out.index>=start)&(out.index<=end)]


def _haa_safe_pick(monthly, defensive=("BIL", "IEF", "SHV")):
    avail = [s for s in defensive if s in monthly.columns]
    if not avail: return "SHV"
    scs = {s: sig_13612U(monthly[s]) for s in avail}
    scs = {k: v for k, v in scs.items() if pd.notna(v)}
    if not scs: return avail[0]
    return max(scs, key=scs.get)


def _haa_run(panel, start, end, top_k):
    offensive = ["SPY","IWM","VEA","VWO","VNQ","DBC","GLD","TLT"]
    cols = list(dict.fromkeys(offensive + ["TIP","BIL","IEF","SHV"]))
    cols = [c for c in cols if c in panel.columns]
    if "TIP" not in cols or "SHV" not in cols: return pd.Series(dtype=float)
    close = panel[cols]; monthly = close.resample("ME").last()
    monthly_idx = pd.DataFrame({"x":1}, index=close.index).groupby(pd.Grouper(freq="ME")).tail(1)
    dates = monthly_idx.index[(monthly_idx.index>=start)&(monthly_idx.index<=end)].tolist()
    weights_map = {}
    for d in dates:
        m = monthly.loc[:d]
        if len(m) < 13: weights_map[d] = {"SHV": 1.0}; continue
        tip_s = sig_13612U(m["TIP"]) if "TIP" in m.columns else float("nan")
        if pd.isna(tip_s) or tip_s <= 0:
            weights_map[d] = {_haa_safe_pick(m): 1.0}; continue
        scs = {a: sig_13612U(m[a]) for a in offensive if a in m.columns and pd.notna(m[a].iloc[-1])}
        scs = {k: v for k, v in scs.items() if pd.notna(v)}
        if not scs:
            weights_map[d] = {_haa_safe_pick(m): 1.0}; continue
        ranked = sorted(scs.items(), key=lambda kv: kv[1], reverse=True)[:top_k]
        safe = _haa_safe_pick(m); n = len(ranked); w = {}
        for ticker, sc in ranked:
            if sc > 0: w[ticker] = w.get(ticker, 0) + 1.0/n
            else: w[safe] = w.get(safe, 0) + 1.0/n
        weights_map[d] = w
    daily_ret = close.ffill().pct_change()
    out = pd.Series(0.0, index=close.index)
    for i, d in enumerate(dates):
        nxt = dates[i+1] if i+1 < len(dates) else end
        seg = close.index[(close.index > d) & (close.index <= nxt)]
        w = weights_map.get(d, {})
        if not w: continue
        cs = [c for c in w if c in daily_ret.columns]
        if not cs: continue
        out.loc[seg] = daily_ret.loc[seg, cs].mul(pd.Series({k: w[k] for k in cs}), axis=1).sum(axis=1, min_count=1).fillna(0.0)
    return out.loc[(out.index>=start)&(out.index<=end)]


def haa_simple(panel, start, end):
    """HAA-Simple (Keller 2023): TIP canary, top-1 by 13612U from HAA-8."""
    return _haa_run(panel, start, end, top_k=1)


def haa_balanced(panel, start, end):
    """HAA-Balanced (Keller 2023): TIP canary, top-4 by 13612U from HAA-8."""
    return _haa_run(panel, start, end, top_k=4)


def sixty_forty(panel, start, end):
    cols = ["SPY", "IEF"]
    cols = [c for c in cols if c in panel.columns]
    if len(cols) < 2: return pd.Series(dtype=float)
    close = panel[cols]
    monthly_idx = pd.DataFrame({"x":1}, index=close.index).groupby(pd.Grouper(freq="ME")).tail(1)
    dates = monthly_idx.index[(monthly_idx.index>=start)&(monthly_idx.index<=end)].tolist()
    daily_ret = close.ffill().pct_change()
    out = pd.Series(0.0, index=close.index)
    for i, d in enumerate(dates):
        nxt = dates[i+1] if i+1 < len(dates) else end
        seg = close.index[(close.index > d) & (close.index <= nxt)]
        out.loc[seg] = daily_ret.loc[seg, ["SPY","IEF"]].mul(pd.Series({"SPY":0.6,"IEF":0.4}), axis=1).sum(axis=1).fillna(0.0)
    return out.loc[(out.index>=start)&(out.index<=end)]


def qqq_trend_follow(panel, start, end, cost_bps=10.0, ticker="SPY"):
    """Faber 10mo SMA timing on `ticker`: hold ticker when above SMA, SHV otherwise.
    Simplest possible single-asset timing strategy, used as TAA peer benchmark.
    Default SPY matches the BULL sleeve ticker for apples-to-apples comparison.
    Uses SPY by default for apples-to-apples comparison with BULL-SPY."""
    if ticker not in panel.columns or "SHV" not in panel.columns:
        return pd.Series(dtype=float)
    monthly = panel[ticker].resample("ME").last().dropna()
    sma10 = monthly.rolling(10).mean()
    signal = (monthly > sma10).reindex(monthly.index).fillna(False)
    daily_tkr = panel[ticker].ffill().pct_change()
    daily_shv = panel["SHV"].ffill().pct_change().reindex(daily_tkr.index).fillna(0)
    common = daily_tkr.loc[start:end].index
    if len(common) == 0:
        return pd.Series(dtype=float)
    asset_per_day = pd.Series("SHV", index=common)
    sig_dates = signal.index[(signal.index >= start - pd.Timedelta(days=60)) & (signal.index <= end)]
    for sd in sig_dates:
        if signal.loc[sd]:
            future = common[common > sd]
            if len(future) < 1: continue
            next_sd = sig_dates[sig_dates > sd]
            if len(next_sd) > 0 and len(common[common > next_sd[0]]) > 0:
                end_apply = common[common > next_sd[0]][0]
            else:
                end_apply = common[-1]
            # T+1 OPEN execution (next-day MOO)
            mask = (common >= future[0]) & (common < end_apply)
            asset_per_day.loc[mask] = ticker
    trend_rets = pd.Series(0.0, index=common)
    trend_rets[asset_per_day == ticker] = daily_tkr.reindex(common).fillna(0)[asset_per_day == ticker]
    trend_rets[asset_per_day == "SHV"] = daily_shv.reindex(common).fillna(0)[asset_per_day == "SHV"]
    import numpy as _np
    flips = (asset_per_day.values[1:] != asset_per_day.values[:-1])
    for i in _np.where(flips)[0]:
        trend_rets.iloc[i+1] -= 2.0 * cost_bps / 10000.0
    return trend_rets


# ============================================================================
# Literature benchmarks (apples-to-apples vs PROD 60/20/20).
#
# Naming follows research/benchmark_comparison_2026_05.py:
#   B2: AAA + TIP canary on CLEAN-7 (Butler-Philbrick 2012 + Keller TIP veto)
#   B3: HAA-Simple SPY (Keller 2022; AllocateSmartly canonical N=1 form)
#   B5: QQQ 12mo trend (Antonacci 2014 GEM single-asset form)
#   BB4 = 60% B2 + 20% B3 + 20% B5 (best literature 60/20/20 blend tested)
#
# BB4 is the canonical apples-to-apples benchmark for PROD: same 60/20/20
# weighting, all three sleeves backed by published TAA papers, and it was the
# strongest literature blend across all multi-sleeve combinations tested.
# Per-sleeve alpha decomposition uses:
#   CPM-ext     vs B2 (AAA + TIP)
#   BULL-ext    vs B3 (HAA-Simple SPY)
#   NDX sleeve  vs B5 (QQQ 12mo trend) or QQQ buy-hold for raw equity proxy
# ============================================================================

CLEAN7_UNIVERSE = ["SPY", "EFA", "EEM", "VNQ", "GLD", "TLT", "DBC"]
_BENCH_SAFE = ["SHV", "IEF"]


def _b_monthly_signal_dates(close, start, end):
    monthly_idx = pd.DataFrame({"x": 1}, index=close.index).groupby(
        pd.Grouper(freq="ME")).tail(1).index
    return monthly_idx[(monthly_idx >= start) & (monthly_idx <= end)].tolist()


def _b_build_port(close, weights_history, start, end, cost_bps=10.0):
    common = close.index[(close.index >= start) & (close.index <= end)]
    daily = close.ffill().pct_change()
    port = pd.Series(0.0, index=common)
    state = pd.Series("", index=common, dtype=object)
    for i, (sd, w) in enumerate(weights_history):
        fut = common[common > sd]
        if len(fut) < 1: continue
        af = fut[0]
        if i + 1 < len(weights_history):
            nf = common[common > weights_history[i + 1][0]]
            ea = nf[0] if len(nf) >= 1 else common[-1] + pd.Timedelta(days=1)
        else:
            ea = end + pd.Timedelta(days=1)
        mask = (common >= af) & (common < ea)
        for t, ww in w.items():
            if t in daily.columns:
                port.loc[mask] += daily[t].reindex(common).fillna(0.0).loc[mask] * ww
        state.loc[mask] = "|".join(f"{t}:{ww:.2f}" for t, ww in sorted(w.items()))
    if cost_bps > 0:
        arr = state.values
        if len(arr) > 1:
            flips = np.where(arr[1:] != arr[:-1])[0] + 1
            for f in flips:
                port.iloc[f] -= 2.0 * cost_bps / 10000.0
    return port


def bench_aaa_tip(panel, start, end, cost_bps=10.0):
    """B2: AAA standard with TIP canary on CLEAN-7.
    Top-half ranking by mom_13612U; min-var continuous weights via SLSQP;
    TIP canary (mom_13612U > 0) gates risk-on/off; HAA best-of-safe (SHV/IEF).
    """
    from cpm_live import sig_13612U, best_safe as _best_safe
    from scipy.optimize import minimize
    import math
    cols = sorted(set(CLEAN7_UNIVERSE + _BENCH_SAFE + ["TIP"]) & set(panel.columns))
    close = panel[cols]
    daily = close.ffill().pct_change()
    sig_dates = _b_monthly_signal_dates(close, start, end)
    wh = []
    for sd in sig_dates:
        monthly = close.loc[:sd].resample("ME").last()
        safe = _best_safe(monthly, sd, _BENCH_SAFE)
        tipm = sig_13612U(monthly["TIP"]) if "TIP" in monthly.columns else float("nan")
        if not (pd.notna(tipm) and tipm > 0):
            wh.append((sd, {safe: 1.0})); continue
        scores = {t: sig_13612U(monthly[t]) for t in CLEAN7_UNIVERSE if t in monthly.columns}
        scores = {t: s for t, s in scores.items() if pd.notna(s)}
        ranked = sorted(scores.items(), key=lambda x: -x[1])
        top_half = max(2, math.ceil(len(CLEAN7_UNIVERSE) / 2))
        top = [t for t, s in ranked[:top_half] if s > 0]
        if len(top) == 0:
            wh.append((sd, {safe: 1.0})); continue
        if len(top) == 1:
            wh.append((sd, {top[0]: 0.5, safe: 0.5})); continue
        cov = daily.loc[:sd].tail(504)[top].cov() * 252
        n = len(top)
        def obj(w, C=cov.values): return float(np.dot(w, np.dot(C, w)))
        cons = ({"type": "eq", "fun": lambda w: np.sum(w) - 1.0},)
        bnds = tuple((0.0, 1.0) for _ in range(n))
        w0 = np.ones(n) / n
        r = minimize(obj, w0, method="SLSQP", bounds=bnds, constraints=cons)
        weights = {top[i]: float(r.x[i]) for i in range(n)} if r.success else {t: 1.0/n for t in top}
        wh.append((sd, weights))
    return _b_build_port(close, wh, start, end, cost_bps)


def bench_haa_simple(panel, start, end, asset="SPY", cost_bps=10.0):
    """B3/B4: HAA-Simple N=1 specialization. Hold `asset` when TIP canary AND
    asset's own mom_13612U both positive; else HAA best-of-safe."""
    from cpm_live import sig_13612U, best_safe as _best_safe
    cols = sorted(set([asset] + _BENCH_SAFE + ["TIP"]) & set(panel.columns))
    close = panel[cols]
    sig_dates = _b_monthly_signal_dates(close, start, end)
    wh = []
    for sd in sig_dates:
        monthly = close.loc[:sd].resample("ME").last()
        safe = _best_safe(monthly, sd, _BENCH_SAFE)
        tipm = sig_13612U(monthly["TIP"]) if "TIP" in monthly.columns else float("nan")
        c_ok = pd.notna(tipm) and tipm > 0
        amom = sig_13612U(monthly[asset]) if asset in monthly.columns else float("nan")
        a_ok = pd.notna(amom) and amom > 0
        wh.append((sd, {asset: 1.0} if (c_ok and a_ok) else {safe: 1.0}))
    return _b_build_port(close, wh, start, end, cost_bps)


def bench_qqq_12mo_trend(panel, start, end, cost_bps=10.0):
    """B5: Antonacci 2014 GEM single-asset on QQQ. Hold QQQ when r12 > 0,
    else HAA best-of-safe."""
    from cpm_live import best_safe as _best_safe
    cols = sorted(set(["QQQ"] + _BENCH_SAFE) & set(panel.columns))
    close = panel[cols]
    sig_dates = _b_monthly_signal_dates(close, start, end)
    wh = []
    for sd in sig_dates:
        monthly = close.loc[:sd].resample("ME").last()
        safe = _best_safe(monthly, sd, _BENCH_SAFE)
        if "QQQ" in monthly.columns and len(monthly["QQQ"]) >= 13:
            r12 = monthly["QQQ"].iloc[-1] / monthly["QQQ"].iloc[-13] - 1
            if pd.notna(r12) and r12 > 0:
                wh.append((sd, {"QQQ": 1.0})); continue
        wh.append((sd, {safe: 1.0}))
    return _b_build_port(close, wh, start, end, cost_bps)


def bench_static_pp_qqq(panel, start, end, pp_weight=0.80, growth_ticker="QQQ"):
    """Static portfolio benchmark: 80% Permanent Portfolio + 20% QQQ buy-hold,
    monthly rebal between sleeves. PP itself is 25% each of SPY/IEF/GLD/SHV
    rebalanced monthly. So the effective static mix is:
      20% SPY  (from PP)
      20% IEF  (from PP)
      20% GLD  (from PP)
      20% SHV  (from PP)
      20% QQQ  (growth sleeve)
    Total ~40% equity (SPY + QQQ), 40% defensive (IEF + SHV), 20% gold.
    Chosen for closest Vol match to PROD 60/20/20 (PROD Vol ~8.9%, this ~9.1%).
    Acts as a 'what if you didn't time anything' static baseline alongside the
    BB4 active-TAA peer benchmark.
    """
    from cpm_live import run_pp_backtest
    pp = run_pp_backtest(panel, start, end)
    if growth_ticker not in panel.columns:
        return pd.Series(dtype=float)
    growth = panel[growth_ticker].ffill().pct_change()
    common = pp.index.intersection(growth.index)
    if len(common) == 0:
        return pd.Series(dtype=float)
    return (pp_weight * pp.reindex(common).fillna(0)
            + (1 - pp_weight) * growth.reindex(common).fillna(0))


def bench_bb4_blend(panel, start, end):
    """BB4 literature blend: 60% B2 (AAA+TIP) + 20% B3 (HAA-Simple SPY) +
    20% B5 (QQQ 12mo trend). Apples-to-apples 60/20/20 vs PROD."""
    b2 = bench_aaa_tip(panel, start, end)
    b3 = bench_haa_simple(panel, start, end, asset="SPY")
    b5 = bench_qqq_12mo_trend(panel, start, end)
    common = b2.index.intersection(b3.index).intersection(b5.index)
    if len(common) == 0:
        return pd.Series(dtype=float)
    return (0.60 * b2.reindex(common).fillna(0)
            + 0.20 * b3.reindex(common).fillna(0)
            + 0.20 * b5.reindex(common).fillna(0))


def alpha_beta_corr(strat: pd.Series, bench: pd.Series) -> dict:
    """OLS daily-return regression r_strat = alpha + beta * r_bench + eps.
    Returns dict with annualized alpha (%/yr), beta, and Pearson correlation.
    """
    common = strat.index.intersection(bench.index)
    if len(common) < 30:
        return {"alpha_ann_pct": float("nan"), "beta": float("nan"), "corr": float("nan")}
    s = strat.reindex(common).fillna(0.0).values
    b = bench.reindex(common).fillna(0.0).values
    if np.std(b) < 1e-12:
        return {"alpha_ann_pct": float("nan"), "beta": float("nan"), "corr": float("nan")}
    cov = np.cov(s, b, ddof=1)
    beta = cov[0, 1] / cov[1, 1]
    alpha_daily = float(np.mean(s) - beta * np.mean(b))
    return {
        "alpha_ann_pct": alpha_daily * 252 * 100,
        "beta": float(beta),
        "corr": float(np.corrcoef(s, b)[0, 1]),
    }


# Module-level cache for cpm_signal_records. Several dashboard diagnostics
# (canary timeline, asset picks, pair archetypes, rolling defensive %, pair
# timeline) all call cpm_signal_records with the same (start, end). Without
# caching, this runs the full monthly signal loop 5+ times per build; with
# caching, it runs once. Keyed by (id(panel), start, end) since panel is
# unhashable but is the same object across calls within one build_dashboard
# invocation.
_CPM_RECORDS_CACHE: dict = {}


def cpm_signal_records(panel: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp | None = None) -> list[dict]:
    """Production-equivalent monthly CPM signal path for dashboard diagnostics.

    Mirrors run_cpm_backtest breadth-majority hold-buffer reset so charts/tables
    do not drift from the live strategy path. Memoized per (panel, start, end)
    to avoid recomputation across the 5+ diagnostic call sites.
    """
    cache_key = (id(panel), pd.Timestamp(start), pd.Timestamp(end) if end is not None else None)
    if cache_key in _CPM_RECORDS_CACHE:
        return _CPM_RECORDS_CACHE[cache_key]
    records = _compute_cpm_signal_records(panel, start, end)
    _CPM_RECORDS_CACHE[cache_key] = records
    return records


def _compute_cpm_signal_records(panel: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp | None = None) -> list[dict]:
    """Actual signal-record computation (cache miss path).

    Excludes the current in-progress calendar month: pd.Grouper(freq='ME')
    picks 'last trading day per month bucket', which for the current month is
    just today (or the latest panel day), NOT the actual month-end signal
    date. PROD doesn't execute on mid-month signals, so including them creates
    phantom records in the pair table / records list (e.g. a 'signal' on
    2026-05-22 when the actual May signal would be computed on 2026-05-29).
    """
    cols = sorted(set(RISKY_UNIVERSE + SAFE_POOL + CANARY_ASSETS + [DEFAULT_CASH]) & set(panel.columns))
    close = panel[cols]
    monthly_idx = pd.DataFrame({"x": 1}, index=close.index).groupby(pd.Grouper(freq="ME")).tail(1)
    mask = monthly_idx.index >= start
    if end is not None:
        mask &= monthly_idx.index <= end
    # Drop in-progress current calendar month: signal is only real once its
    # month-end has actually arrived.
    this_month_start = pd.Timestamp.today().normalize().replace(day=1)
    mask &= monthly_idx.index < this_month_start
    sig_dates = monthly_idx.index[mask].tolist()

    records = []
    for sig_d in sig_dates:
        monthly = close.loc[:sig_d].resample("ME").last()
        n_pos = cpm_module.canary_positive_count(monthly, CANARY_ASSETS)
        risk_state = cpm_module.canary_risk_state(n_pos)
        weights, new_pair, regime, safe = compute_target_weights(close, sig_d)
        records.append({
            "sig_d": sig_d,
            "weights": weights,
            "pair": new_pair,
            "regime": regime,
            "safe": safe,
            "canary_positive_count": n_pos,
            "risk_state": risk_state,
        })
    return records


# ============================================================================
# Per-signal-date records for BULL and NDX sleeves. Precompute once and memoize
# so diagnostics reuse one consistent signal path.
# ============================================================================
_BULL_RECORDS_CACHE: dict = {}
_NDX_RECORDS_CACHE: dict = {}


def bull_signal_records(panel: pd.DataFrame, start: pd.Timestamp,
                          end: pd.Timestamp | None = None) -> list[dict]:
    """BULL sleeve weights at each monthly signal date. Memoized.
    Excludes in-progress current calendar month (see cpm_signal_records).
    """
    key = (id(panel), pd.Timestamp(start), pd.Timestamp(end) if end else None)
    if key in _BULL_RECORDS_CACHE:
        return _BULL_RECORDS_CACHE[key]
    monthly_idx = pd.DataFrame({"x": 1}, index=panel.index).groupby(pd.Grouper(freq="ME")).tail(1)
    mask = monthly_idx.index >= start
    if end is not None:
        mask &= monthly_idx.index <= end
    this_month_start = pd.Timestamp.today().normalize().replace(day=1)
    mask &= monthly_idx.index < this_month_start
    sig_dates = monthly_idx.index[mask].tolist()
    records = []
    for sd in sig_dates:
        w, regime, diag = compute_bull_qqq_weights(panel, sd)
        records.append({"sig_d": sd, "weights": w, "regime": regime, "diag": diag})
    _BULL_RECORDS_CACHE[key] = records
    return records


def ndx_signal_records(panel: pd.DataFrame, ndx_panel: pd.DataFrame,
                        start: pd.Timestamp, end: pd.Timestamp | None = None) -> list[dict]:
    """NDX sleeve weights at each monthly signal date. Memoized.
    Excludes in-progress current calendar month (see cpm_signal_records).
    """
    from ndx_sleeve_live import compute_ndx_weights
    key = (id(panel), id(ndx_panel), pd.Timestamp(start), pd.Timestamp(end) if end else None)
    if key in _NDX_RECORDS_CACHE:
        return _NDX_RECORDS_CACHE[key]
    monthly_idx = pd.DataFrame({"x": 1}, index=panel.index).groupby(pd.Grouper(freq="ME")).tail(1)
    mask = monthly_idx.index >= start
    if end is not None:
        mask &= monthly_idx.index <= end
    this_month_start = pd.Timestamp.today().normalize().replace(day=1)
    mask &= monthly_idx.index < this_month_start
    sig_dates = monthly_idx.index[mask].tolist()
    records = []
    for sd in sig_dates:
        w, regime, diag = compute_ndx_weights(panel, ndx_panel, sd)
        records.append({"sig_d": sd, "weights": w, "regime": regime, "diag": diag})
    _NDX_RECORDS_CACHE[key] = records
    return records


# ============================================================================
# build_artifacts: single source of truth for all dashboard inputs.
# Computes once at start of main(), passed (or available via memoization) to
# every chart/table function. Keeps compute_*_weights() and run_*_backtest()
# calls consistent across views.
# ============================================================================
from types import SimpleNamespace


def build_artifacts(panel: pd.DataFrame, ndx_panel: pd.DataFrame | None,
                     start: pd.Timestamp, end: pd.Timestamp,
                     include_records: bool = True) -> SimpleNamespace:
    """Compute every per-build artifact ONCE.

    Returns SimpleNamespace with:
      panel, ndx_panel, start, end
      cpm, bull_raw, ndx_raw          - daily return Series (pre-DD-circuit)
      bull, ndx                        - daily return Series (post-DD-circuit)
      bull_dd_scale, ndx_dd_scale      - daily DD-scale Series
      vol_scale, vol_events            - portfolio overlay scale/events (identity)
      blend_uncapped, blend            - portfolio daily returns
      sigs                             - signal dates list
      cpm_records, bull_records, ndx_records  - per-signal-date weights/regime
                                                (only populated when include_records=True;
                                                EXT 30y window skips these for speed)
    """
    from circuit_breaker import (compute_lqd_ief_circuit_scale,
                                   LQD_IEF_EMA_SPAN)
    cpm, _ = run_cpm_backtest(panel, start, end)
    bull_raw = run_bull_qqq_backtest(panel, start, end)
    if ndx_panel is not None:
        from ndx_sleeve_live import run_ndx_backtest
        ndx_raw, _ = run_ndx_backtest(panel, ndx_panel, start, end)
    else:
        ndx_raw = pd.Series(0.0, index=bull_raw.index)
    common = cpm.index.intersection(bull_raw.index).intersection(ndx_raw.index)
    cpm = cpm.reindex(common)
    bull_raw = bull_raw.reindex(common)
    ndx_raw = ndx_raw.reindex(common).fillna(0.0)
    sigs = (pd.DataFrame({"x": 1}, index=cpm.index)
             .groupby(pd.Grouper(freq="ME")).tail(1).index.tolist())
    # Intramonth circuits (BULL has none; NDX uses LQD/IEF credit-spread proxy).
    # BULL: no circuit (2026-05-27 audit found DD-10%/63d net Sharpe-negative
    #   under honest t+1 MOO execution; sleeve raw 1.023 > circuit 0.983).
    # NDX: LQD/IEF < EMA50 daily circuit. LQD/IEF ratio is the
    #   duration-cancelled credit spread proxy; falling below EMA50 = IG corporate bonds
    #   underperforming Treasuries = credit-spread widening = risk-off signal.
    #   PROD blend Sharpe 1.384 (DD-10%) -> 1.410 (LQD/IEF). Best Calmar 1.30
    #   (vs 1.28) and shallowest MaxDD -10.17% (vs -10.89%). Sanity-gate
    #   robust to +1d lag (+0.075 delta = signal improves with lag).
    bull = bull_raw
    bull_dd_scale = pd.Series(1.0, index=bull_raw.index)  # passthrough
    lqd_price = panel["LQD"]
    ief_price = panel["IEF"]
    ndx_dd_scale = compute_lqd_ief_circuit_scale(lqd_price, ief_price, common, sigs,
                                                    ema_span=LQD_IEF_EMA_SPAN)
    ndx = ndx_dd_scale * ndx_raw
    blend_uncapped = CPM_W * cpm + BULL_W * bull + NDX_W * ndx
    # No additional portfolio-level cap overlay.
    vol_scale = pd.Series(1.0, index=blend_uncapped.index)
    vol_events: list[dict] = []
    blend = blend_uncapped
    if include_records:
        cpm_records = cpm_signal_records(panel, start, end)
        bull_records = bull_signal_records(panel, start, end)
        ndx_records = (ndx_signal_records(panel, ndx_panel, start, end)
                        if ndx_panel is not None else [])
    else:
        cpm_records = bull_records = ndx_records = []
    return SimpleNamespace(
        panel=panel, ndx_panel=ndx_panel, start=start, end=end,
        cpm=cpm, bull_raw=bull_raw, ndx_raw=ndx_raw,
        bull=bull, ndx=ndx,
        bull_dd_scale=bull_dd_scale, ndx_dd_scale=ndx_dd_scale,
        vol_scale=vol_scale, vol_events=vol_events,
        blend_uncapped=blend_uncapped, blend=blend,
        sigs=sigs,
        cpm_records=cpm_records,
        bull_records=bull_records,
        ndx_records=ndx_records,
    )


# ---------- Charts ----------

# Visual hierarchy (3 tiers):
#   Tier 1 (most prominent): production blend - bold thick deep blue, drawn last
#   Tier 2 (component sleeves): CPM green + BULL-SPY orange, medium weight
#   Tier 3 (benchmarks): muted grey/colored thin lines, dashed/dotted
PROD_STYLE = dict(color="#0040d0", lw=2.0, ls="-", alpha=1.0, zorder=10)

FCP_STYLES = {
    # Tier 2: components
    "CPM standalone":       dict(color="#1a9a1a", lw=2.0, ls="-",  alpha=0.95, zorder=8),
    "BULL-SPY sleeve":      dict(color="#ff8800", lw=2.0, ls="-",  alpha=0.95, zorder=8),
    "NDX sleeve":           dict(color="#cc2266", lw=1.6, ls="-",  alpha=0.85, zorder=7),
    # Tier 3: benchmarks
    "BB4 lit blend (60 AAA+TIP / 20 HAA-S SPY / 20 QQQ-trend)": dict(color="#9966aa", lw=1.6, ls="--", alpha=0.85, zorder=4),
    "Static 80% PP + 20% QQQ": dict(color="#2d8659", lw=1.4, ls="-.", alpha=0.85, zorder=4),
    "QQQ buy-hold":         dict(color="#707070", lw=1.2, ls=":",  alpha=0.7,  zorder=3),
    # Additional benchmark styles
    "SPY buy-hold":         dict(color="#a0a0a0", lw=1.0, ls=":",  alpha=0.65, zorder=3),
    "60/40 SPY/IEF":        dict(color="#b8b8b8", lw=1.0, ls=":",  alpha=0.65, zorder=3),
    "Keller VAA G4":        dict(color="#9966aa", lw=1.0, ls="--", alpha=0.55, zorder=2),
    "HAA-Balanced":         dict(color="#3399cc", lw=1.0, ls="--", alpha=0.55, zorder=2),
    "Faber GTAA5":          dict(color="#bb7733", lw=0.9, ls="--", alpha=0.5, zorder=2),
    "HAA-Simple":           dict(color="#88aabb", lw=0.9, ls="--", alpha=0.5, zorder=2),
}
# Order matters: last drawn = top of pile, but zorder takes precedence.
BASE_RENDER_ORDER = [
    "Faber GTAA5", "HAA-Simple",
    "Keller VAA G4", "HAA-Balanced",
    "60/40 SPY/IEF", "SPY buy-hold",
    "NDX sleeve",
    "QQQ buy-hold", "Static 80% PP + 20% QQQ", "BB4 lit blend (60 AAA+TIP / 20 HAA-S SPY / 20 QQQ-trend)",
    "BULL-SPY sleeve", "CPM standalone",
]


def _ordered(strategies: dict) -> list:
    # Production label is whichever key starts with "CPM-BULL"; render last (top).
    prod_keys = [k for k in strategies if k.startswith("CPM-BULL")]
    render_order = BASE_RENDER_ORDER + prod_keys
    out = []
    for name in render_order:
        if name in strategies and not strategies[name].empty:
            out.append((name, strategies[name]))
    for name, daily in strategies.items():
        if name not in render_order and not daily.empty:
            out.insert(0, (name, daily))
    return out


def _legend_below(ax, ncol=3, prod_label: str | None = None):
    leg = ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.18),
                    ncol=ncol, frameon=False, fontsize=8.5)
    # Bold the production label in legend
    if prod_label:
        for text in leg.get_texts():
            if text.get_text() == prod_label:
                text.set_fontweight("bold")
                text.set_fontsize(9.5)


def chart_equity(strategies: dict, initial_capital: float = 100_000, prod_label: str | None = None):
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for name, daily in _ordered(strategies):
        eq = (1.0 + daily).cumprod() * initial_capital
        sty = PROD_STYLE if (prod_label and name == prod_label) else FCP_STYLES.get(name, dict(lw=1.0, zorder=1))
        ax.plot(eq.index, eq.values, label=name, **sty)
    ax.set_yscale("log")
    ax.set_ylabel("Portfolio Value ($)")
    ax.set_title("Equity Curves (log scale)")
    ax.xaxis.set_major_locator(mdates.YearLocator(2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    _legend_below(ax, ncol=3, prod_label=prod_label)
    return fig

def chart_drawdown(strategies: dict, prod_label: str | None = None):
    fig, ax = plt.subplots(figsize=(8, 3.6))
    for name, daily in _ordered(strategies):
        eq = (1.0 + daily).cumprod()
        dd = (eq / eq.cummax() - 1) * 100
        if prod_label and name == prod_label:
            sty = dict(color="#0040d0", lw=1.8, ls="-", alpha=1.0, zorder=10)
        else:
            sty = dict(FCP_STYLES.get(name, dict(lw=1.0, zorder=1)))
            # Bump benchmarks/components to be visible against PROD fill
            sty["lw"] = max(sty.get("lw", 1.0), 1.4)
            sty["alpha"] = max(sty.get("alpha", 0.7), 0.85)
        ax.plot(dd.index, dd.values, label=name, **sty)
        if prod_label and name == prod_label:
            ax.fill_between(dd.index, dd.values, 0, color="#0040d0", alpha=0.08, zorder=9)
    ax.set_ylabel("Drawdown (%)")
    ax.set_title("Drawdown over time")
    ax.axhline(0, color="#888", lw=0.6)
    ax.xaxis.set_major_locator(mdates.YearLocator(2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    _legend_below(ax, ncol=3, prod_label=prod_label)
    return fig

def chart_monthly_heatmap(daily: pd.Series, title: str = "Monthly Returns"):
    """Heatmap of monthly returns: year x month grid."""
    monthly = ((1 + daily).resample("ME").prod() - 1) * 100
    # Build year x month matrix
    df = monthly.to_frame("ret")
    df["year"] = df.index.year
    df["month"] = df.index.month
    grid = df.pivot(index="year", columns="month", values="ret")
    # Add year total column
    yearly = ((1 + daily).resample("YE").prod() - 1) * 100
    yearly.index = yearly.index.year
    grid["YTD"] = yearly

    fig, ax = plt.subplots(figsize=(8, max(3.5, 0.32 * len(grid))))
    vmax = max(abs(grid.values[~pd.isna(grid.values)].max()),
               abs(grid.values[~pd.isna(grid.values)].min())) if grid.notna().any().any() else 10
    vmax = min(vmax, 20)  # cap colors at +/-20%
    im = ax.imshow(grid.values, cmap="RdYlGn", aspect="auto", vmin=-vmax, vmax=vmax)
    month_labels = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "YTD"]
    ax.set_xticks(range(len(month_labels)))
    ax.set_xticklabels(month_labels, fontsize=8)
    ax.set_yticks(range(len(grid.index)))
    ax.set_yticklabels(grid.index, fontsize=7)
    ax.set_title(title)
    # Annotate cells
    for i in range(len(grid.index)):
        for j in range(len(grid.columns)):
            val = grid.values[i, j]
            if pd.notna(val):
                color = "white" if abs(val) > vmax * 0.6 else "black"
                ax.text(j, i, f"{val:+.1f}", ha="center", va="center",
                        fontsize=6, color=color)
    # Vertical separator between Dec and YTD
    ax.axvline(11.5, color="black", lw=1.2)
    fig.colorbar(im, ax=ax, label="Return (%)", shrink=0.7)
    return fig


def chart_yearly_bars(blended: pd.Series, qqq: pd.Series, naive: pd.Series):
    yr_b = ((1 + blended).resample("YE").prod() - 1) * 100
    yr_q = ((1 + qqq.reindex(blended.index)).resample("YE").prod() - 1) * 100
    yr_n = ((1 + naive.reindex(blended.index)).resample("YE").prod() - 1) * 100
    years = yr_b.index.year.values
    fig, ax = plt.subplots(figsize=(8, 3.8))
    width = 0.28
    x = np.arange(len(years))
    ax.bar(x - width, yr_q.values, width, label="QQQ buy-hold", color="#707070")
    ax.bar(x,         yr_n.values, width, label="BB4 lit blend", color="#9966aa")
    ax.bar(x + width, yr_b.values, width, label="CPM-BULL-NDX (PROD)", color="#0040d0")
    ax.set_xticks(x)
    ax.set_xticklabels(years, rotation=45, fontsize=8)
    ax.set_ylabel("Annual return (%)")
    ax.set_title("Annual Returns: PROD vs BB4 lit blend vs QQQ buy-hold")
    ax.axhline(0, color="#888", lw=0.6)
    _legend_below(ax, ncol=3)
    return fig

def chart_rolling_dd(fcp_only: pd.Series, blended: pd.Series, bb4: pd.Series,
                      max_fcp: pd.Series = None, window_days=63):
    """Rolling N-day max drawdown within window (peak-to-trough inside window)."""
    fig, ax = plt.subplots(figsize=(8, 3.6))

    def rolling_intra_dd(s: pd.Series) -> pd.Series:
        # Compounded equity over rolling window, then worst DD inside that window
        eq = (1 + s.fillna(0)).cumprod()
        # rolling max of equity over window
        roll_max = eq.rolling(window_days).max()
        # current drawdown from rolling-window peak
        dd_from_peak = (eq / roll_max - 1.0)
        # rolling MIN of dd_from_peak gives worst DD experienced in last window
        return dd_from_peak.rolling(window_days).min() * 100

    idx = blended.index
    fcp_dd = rolling_intra_dd(fcp_only.reindex(idx))
    blend_dd = rolling_intra_dd(blended)
    bb4_dd = rolling_intra_dd(bb4.reindex(idx))


    ax.plot(fcp_dd.index, fcp_dd.values, label="CPM standalone", color="#1a9a1a", lw=1.6)
    ax.plot(blend_dd.index, blend_dd.values, label="CPM-BULL-NDX (PROD)", color="#0040d0", lw=2.0)
    ax.plot(bb4_dd.index, bb4_dd.values, label="BB4 lit blend", color="#9966aa", lw=1.4, ls="--", alpha=0.85)

    if max_fcp is not None:
        max_fcp_dd = rolling_intra_dd(max_fcp.reindex(idx))
        ax.plot(max_fcp_dd.index, max_fcp_dd.values, label="BULL-SPY standalone",
                color="#ff8800", lw=1.6, ls="-", alpha=0.85)
    ax.axhline(0, color="#444", lw=0.6)
    ax.set_ylabel("Worst DD in window (%)")
    ax.set_title(f"Rolling {window_days//21}-Month Max Drawdown")
    ax.xaxis.set_major_locator(mdates.YearLocator(2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    _legend_below(ax, ncol=4)
    return fig

def chart_rolling_excess(fcp_only: pd.Series, blended: pd.Series, bb4: pd.Series,
                          max_fcp: pd.Series = None, window_days=252):
    """Rolling N-month annualized excess CAGR vs BB4 lit benchmark.
    Uses geometric (1+r).rolling.prod()**(252/window) - 1 for proper compounding.
    """
    fig, ax = plt.subplots(figsize=(8, 3.6))

    def rolling_cagr(s: pd.Series) -> pd.Series:
        log1p = np.log1p(s)
        rolled_log = log1p.rolling(window_days).sum()
        return np.expm1(rolled_log * (252.0 / window_days))

    idx = blended.index
    fcp_only_a = fcp_only.reindex(idx)
    bb4_a = bb4.reindex(idx)

    fcp_cagr = rolling_cagr(fcp_only_a)
    blend_cagr = rolling_cagr(blended)
    bb4_cagr = rolling_cagr(bb4_a)

    excess_fcp = (fcp_cagr - bb4_cagr) * 100
    excess_blend = (blend_cagr - bb4_cagr) * 100

    ax.plot(excess_fcp.index, excess_fcp.values,
            label="CPM standalone vs BB4", color="#1a9a1a", lw=1.6)
    ax.plot(excess_blend.index, excess_blend.values,
            label="PROD vs BB4", color="#0040d0", lw=2.0)
    if max_fcp is not None:
        max_fcp_cagr = rolling_cagr(max_fcp.reindex(idx))
        excess_max = (max_fcp_cagr - bb4_cagr) * 100
        ax.plot(excess_max.index, excess_max.values,
                label="BULL-SPY standalone vs BB4", color="#ff8800", lw=1.4, ls="--", alpha=0.85)
    ax.axhline(0, color="#444", lw=0.6)
    ax.set_ylabel("Excess CAGR (pp, ann.)")
    ax.set_title(f"Rolling {window_days//21}-Month Excess vs BB4 lit blend")
    ax.xaxis.set_major_locator(mdates.YearLocator(2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    _legend_below(ax, ncol=3)
    return fig

def chart_rolling_sharpe(blended: pd.Series, bb4: pd.Series, window_days=252):
    # Rolling Sharpe vs BB4 lit blend (apples-to-apples architecture)
    fig, ax = plt.subplots(figsize=(8, 3.6))
    bench = bb4.reindex(blended.index)
    bench_sr = (bench.rolling(window_days).mean() * 252) / (bench.rolling(window_days).std() * np.sqrt(252))
    fcp_sr = (blended.rolling(window_days).mean() * 252) / (blended.rolling(window_days).std() * np.sqrt(252))
    ax.plot(bench_sr.index, bench_sr.values, label="BB4 lit blend", color="#9966aa", lw=1.4, ls="--", alpha=0.85)
    ax.plot(fcp_sr.index, fcp_sr.values, label="CPM-BULL-NDX (PROD)", color="#0040d0", lw=2.0)
    ax.axhline(0, color="#888", lw=0.6, ls="--", alpha=0.5)
    ax.axhline(1, color="#0040d0", lw=0.6, ls=":", alpha=0.4)
    ax.set_ylabel("Sharpe")
    ax.set_title(f"Rolling {window_days//21}-Month Sharpe: PROD vs BB4 lit blend")
    ax.xaxis.set_major_locator(mdates.YearLocator(2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    _legend_below(ax, ncol=2)
    return fig

def chart_canary_state_heatmap(panel: pd.DataFrame, cpm_rets: pd.Series, bull_rets: pd.Series, start: pd.Timestamp):
    """Truth-table heatmap of CPM and BULL sleeve performance by state.

    CPM (2x4): rows = HYG canary bit; cols = TIP/GLD combinations.
    BULL (4x4): rows = HYG/TIP canary combinations; cols = curve/vol macro combinations.
    Cell: Sharpe (color) + AnnRet + MaxDD + n_months.
    """
    end = panel.index[-1]

    def _pillar_curve(panel, sig_d):
        ief = panel['IEF'].loc[:sig_d].pct_change().tail(63).sum() if 'IEF' in panel.columns else float('nan')
        tlt = panel['TLT'].loc[:sig_d].pct_change().tail(63).sum() if 'TLT' in panel.columns else float('nan')
        if pd.isna(ief) or pd.isna(tlt):
            return None
        return bool(ief > tlt)

    def _pillar_vol(panel, sig_d):
        if 'SPY' not in panel.columns:
            return None
        rets = panel['SPY'].loc[:sig_d].pct_change().dropna()
        if len(rets) < 252:
            return None
        v63 = rets.tail(63).std() * np.sqrt(252)
        v252_avg = (rets.tail(252).rolling(63).std().dropna() * np.sqrt(252)).mean()
        if pd.isna(v63) or pd.isna(v252_avg):
            return None
        return bool(v63 < v252_avg)

    def compute_states(canary_assets, include_macro=False):
        """Returns Series of state tuples per signal date.
        If include_macro=True, appends (curve_bit, vol_bit) to each tuple."""
        monthly = panel.loc[:end].resample("ME").last()
        states = {}
        for sig_d in monthly.index:
            if sig_d < start:
                continue
            bits = []
            ok = True
            for c in canary_assets:
                if c not in monthly.columns:
                    ok = False; break
                s = sig_13612U(monthly[c].loc[:sig_d])
                if pd.isna(s):
                    ok = False; break
                bits.append(bool(s > 0))
            if not ok:
                continue
            if include_macro:
                cv = _pillar_curve(panel, sig_d)
                vl = _pillar_vol(panel, sig_d)
                if cv is None or vl is None:
                    continue
                bits.extend([cv, vl])
            states[sig_d] = tuple(bits)
        return pd.Series(states).sort_index()

    def attribute(daily_returns, state_ser):
        sig_dates = state_ser.index
        state_per_day = pd.Series(index=daily_returns.index, dtype=object)
        for i, sig_d in enumerate(sig_dates):
            sidx = panel.index.searchsorted(sig_d) + 2
            eidx = panel.index.searchsorted(sig_dates[i+1]) + 1 if i+1 < len(sig_dates) else len(panel.index)
            if sidx >= len(panel.index):
                continue
            window = panel.index[sidx:eidx]
            common = daily_returns.index.intersection(window)
            state_per_day.loc[common] = [state_ser.iloc[i]] * len(common)
        return state_per_day

    def cell_stats(d):
        d = d.dropna()
        if len(d) < 5:
            return None
        eq = (1 + d).cumprod()
        vol = d.std(ddof=0) * np.sqrt(252)
        ann_ret = d.mean() * 252
        mdd = (eq / eq.cummax() - 1).min()
        sh = ann_ret / vol if vol > 0 else float('nan')
        return {'sh': sh, 'ann_ret': ann_ret, 'mdd': mdd}

    def build_grid(daily_returns, canary_assets, include_macro=False):
        """CPM 3-asset canary: 2x4 grid (rows=HYG, cols=last two canary bits).
        BULL 2-asset canary: 2x2 grid (rows=HYG, cols=TIP)."""
        state_ser = compute_states(canary_assets, include_macro=include_macro)
        state_per_day = attribute(daily_returns, state_ser)
        n_assets = len(canary_assets)
        if not include_macro and n_assets == 3:
            # CPM: rows = HYG (first canary), cols = TIP x GLD
            row_order = [(True,), (False,)]
            col_order = [(True, True), (True, False), (False, True), (False, False)]
        elif not include_macro and n_assets == 2:
            # BULL: rows = HYG, cols = TIP
            row_order = [(True,), (False,)]
            col_order = [(True,), (False,)]
        elif include_macro and n_assets == 2:
            # BULL: rows = HYG x TIP, cols = curve x vol
            row_order = [(True, True), (True, False), (False, True), (False, False)]
            col_order = [(True, True), (True, False), (False, True), (False, False)]
        else:
            raise ValueError(f'Unsupported config: n_assets={n_assets}, include_macro={include_macro}')
        grid = []
        for r in row_order:
            row_cells = []
            for c in col_order:
                st = r + c
                mask = state_per_day == st
                n_months = int((state_ser == st).sum())
                d = daily_returns[mask]
                s = cell_stats(d)
                row_cells.append({'state': st, 'n_months': n_months, 'stats': s})
            grid.append(row_cells)
        return grid

    def plot_sub(ax, grid, row_labels_text, col_labels_text, title, fontsize=9):
        nrows = len(grid)
        ncols = len(grid[0])
        sh_grid = np.full((nrows, ncols), np.nan)
        for ri, row in enumerate(grid):
            for ci, cell in enumerate(row):
                if cell['stats']:
                    sh_grid[ri, ci] = cell['stats']['sh']
        im = ax.imshow(sh_grid, cmap=plt.cm.RdYlGn, vmin=-1.5, vmax=2.5, aspect='auto')
        for ri, row in enumerate(grid):
            for ci, cell in enumerate(row):
                s = cell['stats']
                if s is None:
                    text = f"(no data)\nn={cell['n_months']}mo"
                    color = 'gray'
                else:
                    text = (f"Sh {s['sh']:+.2f}\n"
                            f"Ret {s['ann_ret']*100:+5.1f}%/y\n"
                            f"DD {s['mdd']*100:5.1f}%\n"
                            f"n={cell['n_months']}mo")
                    color = 'white' if s['sh'] < -0.3 or s['sh'] > 1.6 else 'black'
                ax.text(ci, ri, text, ha='center', va='center', fontsize=fontsize,
                        color=color, fontfamily='monospace',
                        fontweight='bold' if s and s['sh'] > 1.0 else 'normal')
        ax.set_xticks(range(ncols))
        ax.set_xticklabels(col_labels_text, fontsize=fontsize, fontweight='bold')
        ax.xaxis.tick_top()
        ax.set_yticks(range(nrows))
        ax.set_yticklabels(row_labels_text, fontsize=fontsize+1, fontweight='bold')
        ax.tick_params(axis='both', which='both', length=0)
        ax.set_title(title, fontsize=11, fontweight='bold', pad=36)
        return im

    cpm_canary = ['HYG_stitched', 'TIP', 'GLD']
    bull_canary = ['HYG_stitched', 'TIP']

    cpm_grid = build_grid(cpm_rets, cpm_canary, include_macro=False)
    bull_grid = build_grid(bull_rets, bull_canary, include_macro=False)

    cpm_col_labels = [f"TIP{a}\nGLD{b}" for a, b in [('+','+'),('+','-'),('-','+'),('-','-')]]
    cpm_row_labels = ['HYG+', 'HYG-']
    bull_col_labels = ['TIP+', 'TIP-']
    bull_row_labels = ['HYG+', 'HYG-']

    fig, axes = plt.subplots(2, 1, figsize=(11, 8.5), constrained_layout=True,
                              gridspec_kw={'height_ratios':[1, 1]})
    im = plot_sub(axes[0], cpm_grid, cpm_row_labels, cpm_col_labels,
                   'CPM sleeve - performance by canary state', fontsize=9)
    plot_sub(axes[1], bull_grid, bull_row_labels, bull_col_labels,
              'BULL-SPY sleeve - performance by canary state', fontsize=9)
    fig.colorbar(im, ax=axes, shrink=0.7, label='Sharpe', orientation='vertical', pad=0.02)
    return fig


def chart_canary_timeline(panel: pd.DataFrame, start: pd.Timestamp,
                            records: list | None = None,
                            bull_records: list | None = None) -> tuple:
    """Run signal dates and collect (sig_d, cpm_regime, bull_regime, pair, safe).
    Plot two stacked rows: CPM canary (HYG/TIP/GLD) + BULL canary (HYG/TIP).
    Returns (fig, regime_counts dict, picks Counter, pair_counter Counter)."""
    from collections import Counter
    records = records if records is not None else cpm_signal_records(panel, start)

    cpm_per_date = []
    bull_per_date = []
    picks = Counter()
    pair_counter = Counter()
    for rec in records:
        sd = rec["sig_d"]
        weights = rec["weights"]
        pair = rec["pair"]
        regime = rec["regime"]
        safe = rec["safe"]
        cpm_per_date.append((sd, regime, pair, safe))
        for asset, w in weights.items():
            if w > 0:
                picks[asset] += 1
        if pair and len(pair) == 2:
            pair_counter[tuple(sorted(pair))] += 1
    # BULL-SPY canary state: pull from precomputed bull_records (memoized) so
    # we don't recompute compute_bull_qqq_weights for every signal date
    # (~218 redundant calls each containing a full monthly resample).
    _br = bull_records if bull_records is not None else bull_signal_records(panel, start)
    _bull_by_date = {r["sig_d"]: r["regime"] for r in _br}
    for sd, _, _, _ in cpm_per_date:
        bull_per_date.append((sd, _bull_by_date.get(sd, "CASH")))

    cpm_regimes = [r for _, r, _, _ in cpm_per_date]
    bull_regimes = [r for _, r in bull_per_date]
    n_total = len(cpm_regimes)
    regime_counts = {
        "RISK_ON": cpm_regimes.count("RISK_ON"),
        "DEFENSIVE": cpm_regimes.count("DEFENSIVE"),
        "BULL_SPY": sum(1 for r in bull_regimes if r.startswith("BULL_")),
        "BULL_CASH": sum(1 for r in bull_regimes if r == "CASH"),
    }

    from matplotlib.patches import Patch
    fig, axes = plt.subplots(2, 1, figsize=(8, 3.2), sharex=True,
                             gridspec_kw={"hspace": 0.55})
    dates = [d for d, _, _, _ in cpm_per_date]

    # Row 1: CPM canary (HYG/TIP/GLD any-positive)
    cpm_colors = ["#d04000" if r == "DEFENSIVE" else "#0040d0" for r in cpm_regimes]
    axes[0].bar(dates, [1] * len(dates), color=cpm_colors, width=25, alpha=0.85, edgecolor="none")
    axes[0].set_yticks([])
    axes[0].set_ylim(0, 1)
    axes[0].set_title("CPM canary (HYG / TIP / GLD any-positive 13612U)", fontsize=9)
    axes[0].legend(
        handles=[
            Patch(facecolor="#0040d0", label="RISK_ON (pair)"),
            Patch(facecolor="#d04000", label="DEFENSIVE (best-of-safe SHV/IEF)"),
        ],
        loc="upper right", bbox_to_anchor=(1.0, 1.4), ncol=2, fontsize=7,
        frameon=False, handlelength=1.2, handleheight=0.7,
    )

    # Row 2: BULL-SPY canary (HYG/TIP any-positive + asset mom)
    bull_colors = []
    for r in bull_regimes:
        if r.startswith("BULL_"): bull_colors.append("#00a040")
        else: bull_colors.append("#808080")
    axes[1].bar(dates, [1] * len(dates), color=bull_colors, width=25, alpha=0.85, edgecolor="none")
    axes[1].set_yticks([])
    axes[1].set_ylim(0, 1)
    axes[1].set_title("BULL canary (HYG/TIP any-positive 13612U)", fontsize=9)
    axes[1].legend(
        handles=[
            Patch(facecolor="#00a040", label="BULL_SPY"),
            Patch(facecolor="#808080", label="CASH (best-of-safe SHV/IEF)"),
        ],
        loc="upper right", bbox_to_anchor=(1.0, 1.4), ncol=2, fontsize=7,
        frameon=False, handlelength=1.2, handleheight=0.7,
    )
    axes[1].xaxis.set_major_locator(mdates.YearLocator(2))
    axes[1].xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    plt.tight_layout()
    return fig, regime_counts, picks, pair_counter


def _period_stats(rets: pd.Series) -> dict:
    """Sharpe / AnnRet / MaxDD from concatenated daily-return Series."""
    rets = rets.dropna()
    if len(rets) < 3:
        return {'sh': float('nan'), 'ann': float('nan'), 'mdd': float('nan')}
    eq = (1 + rets).cumprod()
    vol = rets.std(ddof=0) * np.sqrt(252)
    ann = rets.mean() * 252
    sh = ann / vol if vol > 0 else float('nan')
    mdd = (eq / eq.cummax() - 1).min()
    return {'sh': sh, 'ann': ann, 'mdd': mdd}


def compute_pick_pair_stats(records: list, panel: pd.DataFrame) -> tuple:
    """Realized per-asset and per-pair stats from CPM signal records.

    Returns (asset_stats, pair_stats) where each is dict keyed by asset/pair tuple
    mapping to {picks, sh, ann, mdd} measured over days the asset/pair was held
    at its actual pair weight.
    """
    from collections import defaultdict
    sig_dates = [r["sig_d"] for r in records]
    asset_rets = defaultdict(list)
    pair_rets = defaultdict(list)
    asset_picks = defaultdict(int)
    pair_picks = defaultdict(int)
    pair_dates = defaultdict(list)  # diagnostic: per-pair signal dates
    pair_diag = defaultdict(list)   # diagnostic: per-pair (sig_d, len_rets_df, reason)
    for i, rec in enumerate(records):
        sig_d = rec["sig_d"]
        weights = {a: w for a, w in rec["weights"].items() if w > 0}
        pair = rec["pair"]
        # Count picks/pairs unconditionally so counts match chart_canary_timeline's
        # picks Counter (which has no sidx skip). Returns computation skips when
        # there's no future window, but counts still increment.
        for asset in weights:
            asset_picks[asset] += 1
        if pair and len(pair) == 2:
            pkey = tuple(sorted(pair))
            pair_picks[pkey] += 1
            pair_dates[pkey].append(sig_d)
        sidx = panel.index.searchsorted(sig_d) + 2
        eidx = (panel.index.searchsorted(sig_dates[i+1]) + 2
                 if i+1 < len(sig_dates) else len(panel.index))
        if sidx >= len(panel.index):
            continue
        window = panel.index[sidx:eidx]
        # Per-asset returns (skip if no data column)
        for asset, w in weights.items():
            if asset not in panel.columns: continue
            ser = panel[asset].reindex(window).pct_change().dropna()
            if len(ser): asset_rets[asset].append(ser)
        # Per-pair returns (use intersection of valid days for BOTH members).
        # Pair counter already incremented above; this only computes returns.
        if pair and len(pair) == 2:
            pkey = tuple(sorted(pair))
            pair_members = [a for a in weights.keys() if a in panel.columns]
            if len(pair_members) < 2:
                pair_diag[pkey].append((sig_d, 0, f"only {len(pair_members)} members in panel"))
            else:
                rets_df = pd.concat(
                    [panel[a].reindex(window).pct_change().rename(a) for a in pair_members],
                    axis=1).dropna()  # only days where ALL members have valid returns
                if len(rets_df) < 3:
                    # Diagnose which member had data gaps
                    per_member = {a: panel[a].reindex(window).pct_change().dropna().shape[0]
                                   for a in pair_members}
                    pair_diag[pkey].append((sig_d, len(rets_df),
                                             f"joint <3 days; window={len(window)}d; "
                                             f"per_member_valid={per_member}"))
                else:
                    period_ret = sum(rets_df[a] * weights[a] for a in pair_members)
                    pair_rets[pkey].append(period_ret)
    asset_stats = {}
    for a, sers in asset_rets.items():
        merged = pd.concat(sers).groupby(level=0).sum().dropna()
        s = _period_stats(merged)
        asset_stats[a] = {'picks': asset_picks[a], **s}
    # Add zero-return assets (picked but no data) so table count matches
    for a, n in asset_picks.items():
        if a not in asset_stats:
            asset_stats[a] = {'picks': n, 'sh': float('nan'), 'ann': float('nan'),
                                'mdd': float('nan')}
    pair_stats = {}
    for p, sers in pair_rets.items():
        merged = pd.concat(sers)
        s = _period_stats(merged)
        pair_stats[p] = {'picks': pair_picks[p], 'dates': pair_dates[p],
                          'diag': pair_diag.get(p, []), **s}
    # Add pairs with no valid return data so the count still shows
    for p, n in pair_picks.items():
        if p not in pair_stats:
            pair_stats[p] = {'picks': n, 'dates': pair_dates[p],
                              'diag': pair_diag.get(p, []),
                              'sh': float('nan'), 'ann': float('nan'), 'mdd': float('nan')}
    return asset_stats, pair_stats


def _fmt_cell(v, suffix='', neg_class='neg', pos_class='pos'):
    if pd.isna(v): return "<td style='text-align:right; color:#999'>--</td>"
    cls = neg_class if v < 0 else pos_class
    if suffix == '%':
        return f"<td style='text-align:right' class='{cls}'>{v*100:+.1f}%</td>"
    return f"<td style='text-align:right' class='{cls}'>{v:+.2f}</td>"


def picks_table_html(picks, pair_counter, n_signals, records=None, panel=None):
    """Render two side-by-side tables: top picks + top pairs.

    When records + panel given, augments tables with realized Sharpe / AnnRet
    / MaxDD for the periods the asset/pair was held (weighted by pair share).
    """
    asset_stats = pair_stats = None
    if records is not None and panel is not None:
        asset_stats, pair_stats = compute_pick_pair_stats(records, panel)

    # Top picks
    pick_rows = sorted(picks.items(), key=lambda x: -x[1])
    if asset_stats is not None:
        picks_html = ("<div class='table-scroll'><table class='yearly'><thead><tr>"
                      "<th>Asset</th><th>Picks</th><th>% mo</th>"
                      "<th>Sharpe</th><th>AnnRet</th><th>MaxDD</th></tr></thead><tbody>")
    else:
        picks_html = "<div class='table-scroll'><table class='yearly'><thead><tr><th>Asset</th><th>Picks</th><th>% months</th></tr></thead><tbody>"
    for asset, cnt in pick_rows[:18]:
        pct = cnt / n_signals * 100
        picks_html += f"<tr><td>{asset}</td><td style='text-align:right'>{cnt}</td>" \
                      f"<td style='text-align:right'>{pct:.1f}%</td>"
        if asset_stats is not None:
            st = asset_stats.get(asset, {'sh': float('nan'), 'ann': float('nan'), 'mdd': float('nan')})
            picks_html += _fmt_cell(st['sh']) + _fmt_cell(st['ann'], '%') + _fmt_cell(st['mdd'], '%')
        picks_html += "</tr>"
    picks_html += "</tbody></table></div>"

    # Top pairs
    pair_rows = sorted(pair_counter.items(), key=lambda x: -x[1])
    if pair_stats is not None:
        pairs_html = ("<div class='table-scroll'><table class='yearly'><thead><tr>"
                      "<th>Pair</th><th>Picks</th><th>% mo</th>"
                      "<th>Sharpe</th><th>AnnRet</th><th>MaxDD</th></tr></thead><tbody>")
    else:
        pairs_html = "<div class='table-scroll'><table class='yearly'><thead><tr><th>Pair</th><th>Picks</th><th>% months</th></tr></thead><tbody>"
    for pair, cnt in pair_rows[:15]:
        pct = cnt / n_signals * 100
        label = f"{pair[0]} + {pair[1]}"
        # Build tooltip with signal dates + NaN diagnostics so the user can
        # hover any pair row to see when it was picked and why stats are NaN.
        tooltip = ""
        if pair_stats is not None:
            st = pair_stats.get(pair, {'sh': float('nan'), 'ann': float('nan'), 'mdd': float('nan'),
                                          'dates': [], 'diag': []})
            dates = st.get('dates', [])
            diag = st.get('diag', [])
            parts = []
            if dates:
                parts.append('Picks: ' + ', '.join(d.strftime('%Y-%m-%d') for d in dates))
            if diag:
                parts.append('NaN: ' + '; '.join(f'{d.strftime("%Y-%m-%d")} {r}' for d, _, r in diag))
            tooltip = ' | '.join(parts)
        tr_attr = f' title="{tooltip}"' if tooltip else ''
        pairs_html += f"<tr{tr_attr}><td>{label}</td><td style='text-align:right'>{cnt}</td>" \
                      f"<td style='text-align:right'>{pct:.1f}%</td>"
        if pair_stats is not None:
            pairs_html += _fmt_cell(st['sh']) + _fmt_cell(st['ann'], '%') + _fmt_cell(st['mdd'], '%')
        pairs_html += "</tr>"
    pairs_html += "</tbody></table></div>"

    return f"""<div style='display:flex; gap:24px; flex-wrap:wrap;'>
<div style='flex:1; min-width:280px;'><h3 style='margin-top:0;'>Asset Pick Frequency</h3>{picks_html}</div>
<div style='flex:1; min-width:280px;'><h3 style='margin-top:0;'>Top Pair Archetypes</h3>{pairs_html}</div>
</div>"""


def chart_asset_when_picked(panel: pd.DataFrame, start: pd.Timestamp,
                              records: list | None = None):
    """Per-asset conditional performance when held in a CPM pair.

    Bars: Sharpe, AnnRet, CumRet per asset. Sorted by Sharpe. Uses the same
    `compute_pick_pair_stats` source as the Asset Pick Frequency table so the
    counts and metrics MUST match the table (single source of truth).
    """
    records = records if records is not None else cpm_signal_records(panel, start)
    asset_stats, _pair_stats = compute_pick_pair_stats(records, panel)

    rows = []
    for a, st in asset_stats.items():
        # Skip assets with insufficient data for meaningful stats
        if pd.isna(st.get('sh')):
            continue
        # Cumulative return: recompute from records the same way (raw, unweighted)
        rows.append({'asset': a, 'picks': st['picks'], 'sh': st['sh'],
                      'ann_ret': st['ann'], 'cum': st.get('mdd', float('nan'))})
    # Cum return is informational; recompute properly by concatenating held-period raw returns
    from collections import defaultdict
    cum_by_asset = defaultdict(list)
    sig_dates = [r["sig_d"] for r in records]
    for i, rec in enumerate(records):
        sig_d = rec["sig_d"]
        weights = {a: w for a, w in rec["weights"].items() if w > 0}
        sidx = panel.index.searchsorted(sig_d) + 2
        eidx = (panel.index.searchsorted(sig_dates[i+1]) + 2
                 if i+1 < len(sig_dates) else len(panel.index))
        if sidx >= len(panel.index): continue
        window = panel.index[sidx:eidx]
        for a in weights.keys():
            if a not in panel.columns: continue
            ser = panel[a].reindex(window).pct_change().dropna()
            if len(ser): cum_by_asset[a].append(ser)
    for r in rows:
        sers = cum_by_asset.get(r['asset'], [])
        if sers:
            full = pd.concat(sers).groupby(level=0).first().dropna()
            eq = (1 + full).cumprod()
            r['cum'] = eq.iloc[-1] - 1 if len(eq) else float('nan')
        else:
            r['cum'] = float('nan')
    rows.sort(key=lambda r: -r['sh'])

    assets = [r['asset'] for r in rows]
    sharpes = [r['sh'] for r in rows]
    ann_rets = [r['ann_ret'] * 100 for r in rows]
    cums = [r['cum'] * 100 for r in rows]
    picks_n = [r['picks'] for r in rows]

    fig, axes = plt.subplots(1, 3, figsize=(13, 4.5), constrained_layout=True)
    colors = ['#ec5b56' if s < 0 else '#73c373' if s > 1 else '#c4d76f' for s in sharpes]

    axes[0].barh(assets, sharpes, color=colors, edgecolor='#333')
    axes[0].axvline(0, color='black', lw=0.8)
    axes[0].set_xlabel('Sharpe (when held)')
    axes[0].set_title('Sharpe (when picked)')
    axes[0].invert_yaxis()
    for i, (s, n) in enumerate(zip(sharpes, picks_n)):
        axes[0].text(s + (0.05 if s >= 0 else -0.05), i, f"{s:+.2f}\n(n={n})",
                     va='center', ha='left' if s >= 0 else 'right', fontsize=8)

    axes[1].barh(assets, ann_rets, color=colors, edgecolor='#333')
    axes[1].axvline(0, color='black', lw=0.8)
    axes[1].set_xlabel('Annualized Return % (when held)')
    axes[1].set_title('Ann.Return (when picked)')
    axes[1].invert_yaxis()
    for i, v in enumerate(ann_rets):
        axes[1].text(v + (0.5 if v >= 0 else -0.5), i, f"{v:+.1f}%",
                     va='center', ha='left' if v >= 0 else 'right', fontsize=8)

    axes[2].barh(assets, cums, color=colors, edgecolor='#333')
    axes[2].axvline(0, color='black', lw=0.8)
    axes[2].set_xlabel('Cumulative Return % (over all held days)')
    axes[2].set_title('Cum.Return (when picked)')
    axes[2].invert_yaxis()
    for i, v in enumerate(cums):
        axes[2].text(v + (2 if v >= 0 else -2), i, f"{v:+.1f}%",
                     va='center', ha='left' if v >= 0 else 'right', fontsize=8)

    return fig, rows





def chart_sleeve_contribution(cpm_rets: pd.Series, bull_rets: pd.Series, ndx_rets: pd.Series,
                              w_cpm: float, w_bull: float, w_ndx: float):
    """Yearly stacked bars showing each sleeve's contribution to blend annual return."""
    common = cpm_rets.index.intersection(bull_rets.index).intersection(ndx_rets.index)
    cpm_c = cpm_rets.loc[common] * w_cpm
    bull_c = bull_rets.loc[common] * w_bull
    ndx_c = ndx_rets.loc[common] * w_ndx

    def yearly_contribution(daily):
        # Annualized contribution: sum of daily contributions per year
        # Approximation: sum_d (w * r_d) = w * sum_d r_d ~= w * annual_ret
        # More accurate: re-compound annual
        return daily.groupby(daily.index.year).sum()

    cpm_y = yearly_contribution(cpm_c)
    bull_y = yearly_contribution(bull_c)
    ndx_y = yearly_contribution(ndx_c)
    years = cpm_y.index

    fig, ax = plt.subplots(figsize=(12, 4.5), constrained_layout=True)

    # Stacked bars
    width = 0.7
    ax.bar(years, cpm_y * 100, width, label=f'CPM ({int(w_cpm*100)}%)', color='#2e86c1', edgecolor='#1b4f72')
    ax.bar(years, bull_y * 100, width, bottom=cpm_y * 100, label=f'BULL-SPY ({int(w_bull*100)}%)', color='#f39c12', edgecolor='#7e5109')
    ax.bar(years, ndx_y * 100, width, bottom=(cpm_y + bull_y) * 100, label=f'NDX ({int(w_ndx*100)}%)', color='#c0392b', edgecolor='#641e16')

    # Total line marker
    totals = (cpm_y + bull_y + ndx_y) * 100
    ax.plot(years, totals, color='black', marker='D', markersize=6, linestyle='', label='Blend total')

    ax.axhline(0, color='black', lw=0.5)
    ax.set_ylabel('Annual contribution to blend return (%)')
    ax.set_title('Per-sleeve contribution to blend (yearly, daily-sum approximation)')
    ax.set_xticks(years)
    ax.set_xticklabels(years, rotation=45)
    ax.grid(axis='y', alpha=0.3)
    _legend_below(ax, ncol=4)
    return fig


def table_worst_drawdowns(cpm_rets: pd.Series, bull_rets: pd.Series, ndx_rets: pd.Series,
                          w_cpm: float, w_bull: float, w_ndx: float, top_n: int = 10) -> str:
    """Identify top-N drawdown periods of the blend and decompose by sleeve contribution."""
    common = cpm_rets.index.intersection(bull_rets.index).intersection(ndx_rets.index)
    blend = w_cpm * cpm_rets.loc[common] + w_bull * bull_rets.loc[common] + w_ndx * ndx_rets.loc[common]
    eq = (1 + blend).cumprod()
    peak = eq.cummax()
    dd = eq / peak - 1

    # Identify drawdown periods: peak -> trough -> recovery (or end)
    in_dd = False
    periods = []
    start_d = None
    for date, val in dd.items():
        if not in_dd and val < -0.001:
            in_dd = True
            start_d = date
        elif in_dd and val >= -0.0001:
            trough_d = dd.loc[start_d:date].idxmin()
            trough_v = dd.loc[trough_d]
            periods.append({'start': start_d, 'trough': trough_d, 'recovery': date, 'depth': trough_v})
            in_dd = False
    if in_dd:
        trough_d = dd.loc[start_d:].idxmin()
        trough_v = dd.loc[trough_d]
        periods.append({'start': start_d, 'trough': trough_d, 'recovery': None, 'depth': trough_v})

    periods.sort(key=lambda p: p['depth'])
    top = periods[:top_n]

    rows_html = ""
    for p in top:
        s, t, r, d = p['start'], p['trough'], p['recovery'], p['depth']
        end_d = r if r else cpm_rets.index[-1]
        sub_cpm = cpm_rets.loc[s:end_d].sum() * w_cpm
        sub_bull = bull_rets.loc[s:end_d].sum() * w_bull
        sub_ndx = ndx_rets.loc[s:end_d].sum() * w_ndx
        # Compute the actual blend drawdown contribution per sleeve over peak-to-trough
        ptd_cpm = cpm_rets.loc[s:t].sum() * w_cpm
        ptd_bull = bull_rets.loc[s:t].sum() * w_bull
        ptd_ndx = ndx_rets.loc[s:t].sum() * w_ndx
        days_to_trough = (t - s).days
        days_to_recover = (r - t).days if r else None
        rec_str = f"{days_to_recover}d" if r else "<em>ongoing</em>"
        rows_html += (f"<tr>"
                      f"<td>{s.strftime('%Y-%m-%d')}</td>"
                      f"<td>{t.strftime('%Y-%m-%d')}</td>"
                      f"<td>{r.strftime('%Y-%m-%d') if r else '-'}</td>"
                      f"<td style='text-align:right'>{d*100:+.2f}%</td>"
                      f"<td style='text-align:right'>{days_to_trough}d</td>"
                      f"<td style='text-align:right'>{rec_str}</td>"
                      f"<td style='text-align:right; color:{'#c0392b' if ptd_cpm < 0 else '#27ae60'}'>{ptd_cpm*100:+.2f}%</td>"
                      f"<td style='text-align:right; color:{'#c0392b' if ptd_bull < 0 else '#27ae60'}'>{ptd_bull*100:+.2f}%</td>"
                      f"<td style='text-align:right; color:{'#c0392b' if ptd_ndx < 0 else '#27ae60'}'>{ptd_ndx*100:+.2f}%</td>"
                      f"</tr>")

    return f"""<div class='table-scroll'><table class='metric-table'><thead><tr>
<th>Peak date</th><th>Trough date</th><th>Recovery date</th>
<th>Depth</th><th>To trough</th><th>To recover</th>
<th>CPM contrib (peak->trough)</th><th>BULL contrib (peak->trough)</th><th>NDX contrib (peak->trough)</th>
</tr></thead><tbody>{rows_html}</tbody></table></div>"""


def chart_rolling_defensive_pct(panel: pd.DataFrame, start: pd.Timestamp,
                                  records: list | None = None):
    """Rolling 12-month % of months the CPM canary was defensive."""
    records = records if records is not None else cpm_signal_records(panel, start)
    defensive_per_month = []
    for rec in records:
        is_def = 1.0 if rec["regime"] == "DEFENSIVE" else (0.5 if rec["pair"] is None else 0.0)
        defensive_per_month.append((rec["sig_d"], is_def))
    df_def = pd.DataFrame(defensive_per_month, columns=['date', 'def']).set_index('date')
    rolling_def = df_def['def'].rolling(12, min_periods=6).mean() * 100

    fig, ax = plt.subplots(figsize=(12, 4), constrained_layout=True)
    ax.fill_between(rolling_def.index, 0, rolling_def.values, color='#e74c3c', alpha=0.4, label='CPM defensive %')
    ax.plot(rolling_def.index, rolling_def.values, color='#c0392b', lw=1.5)
    ax.axhline(rolling_def.mean(), color='black', ls='--', lw=0.8, label=f'Mean {rolling_def.mean():.1f}%')
    ax.set_ylabel('% of last 12 months in defensive (best-of-safe SHV/IEF)')
    ax.set_ylim(0, 100)
    ax.set_title('CPM Rolling Defensive Activation (12-month window)')
    ax.legend(loc='upper right')
    ax.grid(alpha=0.3)
    ax.xaxis.set_major_locator(mdates.YearLocator(2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
    return fig


def chart_pair_pick_timeline(panel: pd.DataFrame, start: pd.Timestamp,
                                records: list | None = None):
    """Gantt-style pair-pick timeline colored by realized 1mo return."""
    records = records if records is not None else cpm_signal_records(panel, start)
    sig_dates = [r["sig_d"] for r in records]
    timeline = []
    for i, rec in enumerate(records):
        sig_d = rec["sig_d"]
        weights = rec["weights"]
        new_pair = rec["pair"]
        regime = rec["regime"]
        sidx = panel.index.searchsorted(sig_d) + 2
        eidx = panel.index.searchsorted(sig_dates[i+1]) + 2 if i+1 < len(sig_dates) else len(panel.index)
        # Compute realized 1mo return when a future window exists; otherwise
        # this is the most-recent pick with no held period yet -- still show it
        # in the timeline (so VBR / latest-month picks are not silently omitted).
        port_ret = float('nan')
        if sidx < len(panel.index):
            port_ret = 0.0
            for a, w in weights.items():
                if a in panel.columns:
                    p0 = panel[a].iloc[sidx - 1]
                    p1 = panel[a].iloc[eidx - 1] if eidx - 1 < len(panel.index) else None
                    if p1 is not None and pd.notna(p0) and pd.notna(p1) and p0 > 0:
                        port_ret += w * (p1 / p0 - 1)
        label = ' + '.join(sorted(new_pair)) if new_pair else ('DEFENSIVE' if regime == 'DEFENSIVE' else 'PARTIAL')
        timeline.append({'date': sig_d, 'label': label, 'ret': port_ret})
    df_tl = pd.DataFrame(timeline)
    label_counts = df_tl['label'].value_counts()
    labels_sorted = label_counts.index.tolist()
    label_to_y = {l: i for i, l in enumerate(labels_sorted)}
    df_tl['y'] = df_tl['label'].map(label_to_y)

    fig, ax = plt.subplots(figsize=(13, 7), constrained_layout=True)
    vmin, vmax = -0.08, 0.08
    scatter = ax.scatter(df_tl['date'], df_tl['y'], c=df_tl['ret'].clip(vmin, vmax),
                         cmap=plt.cm.RdYlGn, vmin=vmin, vmax=vmax, s=50, marker='s',
                         edgecolor='black', linewidth=0.3)
    ax.set_yticks(range(len(labels_sorted)))
    ax.set_yticklabels([f"{l} (n={label_counts[l]})" for l in labels_sorted], fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel('Signal date')
    ax.set_title('CPM Pair-Pick Timeline (color = realized 1mo return of held weights)')
    ax.xaxis.set_major_locator(mdates.YearLocator(2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
    ax.grid(alpha=0.2)
    cbar = fig.colorbar(scatter, ax=ax)
    cbar.set_label('1mo realized return (clipped at -8%/+8%)')
    return fig


def chart_rolling_sleeve_correlation(cpm_rets: pd.Series, bull_rets: pd.Series, ndx_rets: pd.Series, window: int = 252):
    common = cpm_rets.index.intersection(bull_rets.index).intersection(ndx_rets.index)
    roll_cb = cpm_rets.loc[common].rolling(window).corr(bull_rets.loc[common])
    roll_cn = cpm_rets.loc[common].rolling(window).corr(ndx_rets.loc[common])
    roll_bn = bull_rets.loc[common].rolling(window).corr(ndx_rets.loc[common])

    fig, ax = plt.subplots(figsize=(12, 4.5), constrained_layout=True)
    ax.plot(roll_cb.index, roll_cb, color='#2e86c1', lw=1.5, label='CPM vs BULL-SPY')
    ax.plot(roll_cn.index, roll_cn, color='#f39c12', lw=1.5, label='CPM vs NDX')
    ax.plot(roll_bn.index, roll_bn, color='#c0392b', lw=1.5, label='BULL-SPY vs NDX')
    ax.axhline(0, color='gray', lw=0.5)
    ax.axhline(0.5, color='gray', ls=':', lw=0.5)
    ax.set_ylabel('1y rolling correlation')
    ax.set_title('Rolling 252-day correlations between sleeves')
    ax.legend(loc='lower right')
    ax.grid(alpha=0.3)
    ax.xaxis.set_major_locator(mdates.YearLocator(2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
    return fig


def chart_monthly_return_distributions(cpm_rets: pd.Series, bull_rets: pd.Series, ndx_rets: pd.Series,
                                         w_cpm: float, w_bull: float, w_ndx: float):
    def monthly(daily):
        return (1 + daily).resample('ME').apply(lambda x: x.prod() - 1)
    m_cpm = monthly(cpm_rets).dropna() * 100
    m_bull = monthly(bull_rets).dropna() * 100
    m_ndx = monthly(ndx_rets).dropna() * 100
    common = cpm_rets.index.intersection(bull_rets.index).intersection(ndx_rets.index)
    blend = w_cpm * cpm_rets.loc[common] + w_bull * bull_rets.loc[common] + w_ndx * ndx_rets.loc[common]
    m_blend = monthly(blend).dropna() * 100

    fig, axes = plt.subplots(2, 2, figsize=(12, 7), constrained_layout=True)
    for ax, (name, ser, color) in zip(
        axes.flat,
        [(f'CPM ({int(w_cpm*100)}%)', m_cpm, '#2e86c1'),
         (f'BULL-SPY ({int(w_bull*100)}%)', m_bull, '#f39c12'),
         (f'NDX ({int(w_ndx*100)}%)', m_ndx, '#c0392b'),
         (f'Blend {int(w_cpm*100)}/{int(w_bull*100)}/{int(w_ndx*100)}', m_blend, '#27ae60')]
    ):
        ax.hist(ser, bins=40, color=color, alpha=0.7, edgecolor='black', linewidth=0.5)
        ax.axvline(ser.mean(), color='black', ls='--', lw=1, label=f'Mean {ser.mean():.2f}%')
        ax.axvline(ser.median(), color='red', ls=':', lw=1, label=f'Median {ser.median():.2f}%')
        ax.axvline(0, color='gray', lw=0.5)
        skew = ((ser - ser.mean()) ** 3).mean() / ser.std() ** 3
        kurt = ((ser - ser.mean()) ** 4).mean() / ser.std() ** 4 - 3
        ax.set_title(f'{name}: skew {skew:+.2f}, ex.kurt {kurt:+.2f}')
        ax.set_xlabel('Monthly return (%)')
        ax.set_ylabel('Count')
        ax.legend(fontsize=8, loc='upper right')
        ax.grid(alpha=0.3)
    return fig


def chart_correlations(strategies: dict):
    df = pd.DataFrame({k: v for k, v in strategies.items() if not v.empty})
    common = df.dropna()
    corr = common.corr()
    n = len(corr)
    fig, ax = plt.subplots(figsize=(7, 6))
    im = ax.imshow(corr.values, cmap="RdBu_r", vmin=-1, vmax=1, aspect="auto")
    ax.set_xticks(range(n)); ax.set_yticks(range(n))
    ax.set_xticklabels(corr.columns, rotation=40, ha="right", fontsize=9)
    ax.set_yticklabels(corr.columns, fontsize=9)
    for i in range(n):
        for j in range(n):
            v = corr.values[i, j]
            color = "white" if abs(v) > 0.5 else "#222"
            ax.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=8.5, color=color)
    ax.set_title("Strategy Daily-Return Correlations")
    ax.grid(False)
    cbar = plt.colorbar(im, ax=ax, fraction=0.04, pad=0.02)
    cbar.ax.tick_params(labelsize=8)
    cbar.set_label("correlation", fontsize=9)
    return fig


def chart_equity_dd_combined(strategies: dict, prod_label: str | None = None,
                                initial_capital: float = 1000):
    """TT-style integrated equity + drawdown chart.
    Top panel: log-scale equity curves. Bottom panel: drawdown filled.
    Shared x-axis.
    """
    fig, (ax_eq, ax_dd) = plt.subplots(2, 1, figsize=(9, 6),
                                          gridspec_kw={"height_ratios": [3, 1.5],
                                                        "hspace": 0.06},
                                          sharex=True)
    for name, daily in _ordered(strategies):
        eq = (1.0 + daily).cumprod() * initial_capital
        dd = (eq / eq.cummax() - 1) * 100
        sty = PROD_STYLE if (prod_label and name == prod_label) else FCP_STYLES.get(name, dict(lw=1.0, zorder=1))
        color = sty.get("color", "#888")
        if prod_label and name == prod_label:
            ax_eq.fill_between(eq.index, initial_capital, eq.values,
                                 color=color, alpha=0.85, zorder=3)
            ax_eq.plot(eq.index, eq.values, color=color, lw=1.5, zorder=4, label=name)
            ax_dd.fill_between(dd.index, dd.values, 0, color=color, alpha=0.85, zorder=3)
        else:
            ax_eq.plot(eq.index, eq.values, label=name, **sty)
            ax_dd.plot(dd.index, dd.values, color=color, lw=sty.get("lw", 1.0),
                        alpha=sty.get("alpha", 0.7), zorder=sty.get("zorder", 1))
    ax_eq.set_yscale("log")
    ax_eq.set_ylabel("Portfolio Value ($)")
    ax_eq.grid(True, alpha=0.3, which="both")
    ax_dd.set_ylabel("Drawdown (%)")
    ax_dd.axhline(0, color="#888", lw=0.6)
    ax_dd.grid(True, alpha=0.3)
    ax_dd.xaxis.set_major_locator(mdates.YearLocator(2))
    ax_dd.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    _legend_below(ax_dd, ncol=3, prod_label=prod_label)
    ax_eq.set_title("Equity & Drawdown", fontsize=11)
    return fig


def chart_risk_return_scatter(strategies: dict, prod_label: str | None = None):
    """TT-style risk-return scatter: Ulcer Index (X) vs Avg Return (Y).
    One dot per calendar year per strategy. Shows cloud of yearly snapshots:
    high return + low Ulcer = top-left quadrant.
    """
    fig, ax = plt.subplots(figsize=(9, 5.5))
    for name, daily in strategies.items():
        r = daily.dropna()
        if len(r) < 252:
            continue
        is_prod = (prod_label and name == prod_label)
        sty = PROD_STYLE if is_prod else FCP_STYLES.get(name, dict(color="#888"))
        color = sty.get("color", "#888")
        # Group by calendar year
        years = sorted(set(r.index.year))
        xs = []; ys = []
        for y in years:
            sub = r[r.index.year == y]
            if len(sub) < 100: continue
            eq = (1 + sub).cumprod()
            avg_ret = float(eq.iloc[-1] - 1) * 100  # year's total return (~CAGR for 1y)
            # Ulcer Index: sqrt(mean(DD^2)) over year
            dd = (eq / eq.cummax() - 1) * 100
            ulcer = float((dd ** 2).mean() ** 0.5)
            xs.append(ulcer); ys.append(avg_ret)
        if not xs: continue
        size = 80 if is_prod else 50
        alpha = 0.85 if is_prod else 0.55
        edge = "#000" if is_prod else "none"
        ax.scatter(xs, ys, s=size, c=color, alpha=alpha,
                    edgecolors=edge, linewidths=0.8 if is_prod else 0,
                    label=name, zorder=10 if is_prod else 3)
    ax.axhline(0, color="#444", lw=0.6)
    ax.set_xlabel("Risk: Ulcer Index (%)")
    ax.set_ylabel("Reward: Annual Return (%)")
    ax.set_title("Risk vs Return (per calendar year)")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper right", fontsize=8.5, framealpha=0.9)
    return fig


def topN_drawdowns_html(daily: pd.Series, n: int = 10) -> str:
    """Top-N worst drawdowns with start, trough, recovery, depth, duration."""
    r = daily.dropna()
    eq = (1 + r).cumprod()
    peak = eq.cummax()
    dd = (eq / peak - 1)
    # Identify distinct drawdown periods: peak-to-trough-to-recovery
    periods = []
    in_dd = False
    start_idx = None
    peak_value = None
    trough_idx = None
    trough_value = 0
    for i, (date, e) in enumerate(eq.items()):
        if not in_dd:
            if dd.iloc[i] < -0.001:  # 0.1% threshold to start
                in_dd = True
                start_idx = date
                peak_value = peak.iloc[i]
                trough_idx = date
                trough_value = dd.iloc[i]
        else:
            if dd.iloc[i] < trough_value:
                trough_value = dd.iloc[i]
                trough_idx = date
            if e >= peak_value:  # recovered
                periods.append({
                    "start": start_idx, "trough": trough_idx, "recovery": date,
                    "depth": trough_value * 100,
                    "days": (date - start_idx).days,
                    "to_trough": (trough_idx - start_idx).days,
                    "recovery_days": (date - trough_idx).days,
                })
                in_dd = False
    # If still in drawdown at end, record as ongoing
    if in_dd:
        periods.append({
            "start": start_idx, "trough": trough_idx, "recovery": None,
            "depth": trough_value * 100,
            "days": (eq.index[-1] - start_idx).days,
            "to_trough": (trough_idx - start_idx).days,
            "recovery_days": None,
        })
    top = sorted(periods, key=lambda x: x["depth"])[:n]
    rows = []
    for p in top:
        rec = str(p["recovery"].date()) if p["recovery"] else "<i>ongoing</i>"
        rec_d = f"{p['recovery_days']}d" if p["recovery_days"] is not None else "-"
        rows.append(
            f"<tr><td>{p['start'].date()}</td><td>{p['trough'].date()}</td>"
            f"<td>{rec}</td><td style='text-align:right'><b>{p['depth']:.2f}%</b></td>"
            f"<td style='text-align:right'>{p['to_trough']}d</td>"
            f"<td style='text-align:right'>{rec_d}</td>"
            f"<td style='text-align:right'>{p['days']}d</td></tr>"
        )
    return (
        "<div class='table-scroll'><table><thead><tr>"
        "<th>Peak start</th><th>Trough</th><th>Recovery</th>"
        "<th style='text-align:right'>Depth</th>"
        "<th style='text-align:right'>Peak→trough</th>"
        "<th style='text-align:right'>Trough→recovery</th>"
        "<th style='text-align:right'>Total duration</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>"
    )


def period_summary_html(daily: pd.Series, end_date: pd.Timestamp = None) -> str:
    """Period-over-period summary table: 1y/3y/5y/10y/since-inception."""
    r = daily.dropna()
    if end_date is None:
        end_date = r.index[-1]
    inception = r.index[0]
    periods = [
        ("1Y", end_date - pd.DateOffset(years=1)),
        ("3Y", end_date - pd.DateOffset(years=3)),
        ("5Y", end_date - pd.DateOffset(years=5)),
        ("10Y", end_date - pd.DateOffset(years=10)),
        ("Since inception", inception),
    ]
    rows = []
    for label, start in periods:
        if start < inception:
            if label == "Since inception":
                start = inception
            else:
                rows.append(f"<tr><td>{label}</td><td colspan=4 style='color:#888;text-align:center'>insufficient history</td></tr>")
                continue
        sub = r.loc[start:end_date].dropna()
        if len(sub) < 20:
            rows.append(f"<tr><td>{label}</td><td colspan=4 style='color:#888;text-align:center'>n/a</td></tr>")
            continue
        eq = (1 + sub).cumprod()
        yrs = (sub.index[-1] - sub.index[0]).days / 365.25
        cagr = float(eq.iloc[-1] ** (1/yrs) - 1) * 100 if yrs > 0 else 0
        sh = float(sub.mean() / sub.std() * (252 ** 0.5)) if sub.std() else 0
        dd = float((eq / eq.cummax() - 1).min()) * 100
        calmar = cagr / abs(dd) if dd != 0 else 0
        rows.append(
            f"<tr><td><b>{label}</b></td>"
            f"<td style='text-align:right'>{sh:.2f}</td>"
            f"<td style='text-align:right'>{cagr:+.2f}%</td>"
            f"<td style='text-align:right'>{dd:.2f}%</td>"
            f"<td style='text-align:right'>{calmar:.2f}</td></tr>"
        )
    return (
        "<div class='table-scroll'><table><thead><tr>"
        "<th>Period</th><th style='text-align:right'>Sharpe</th>"
        "<th style='text-align:right'>CAGR</th>"
        "<th style='text-align:right'>MaxDD</th>"
        "<th style='text-align:right'>Calmar</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>"
    )


# ---------- Tables ----------

def alpha_beta_table_html(rows: list[dict]) -> str:
    """rows: list of {strategy, benchmark, alpha_ann_pct, beta, corr}."""
    body = ""
    for r in rows:
        body += ("<tr>"
                  f"<td>{r['strategy']}</td>"
                  f"<td>{r['benchmark']}</td>"
                  f"<td style='text-align:right'>{r['alpha_ann_pct']:+.2f}%</td>"
                  f"<td style='text-align:right'>{r['beta']:.3f}</td>"
                  f"<td style='text-align:right'>{r['corr']:.3f}</td>"
                  "</tr>\n")
    return f"""<div class='table-scroll'><table class='perf'>
<thead><tr><th>Strategy</th><th>Benchmark</th><th>Alpha (%/yr)</th><th>Beta</th><th>Corr</th></tr></thead>
<tbody>{body}</tbody></table></div>"""


def perf_table_html(rows: list[dict], compact: bool = False) -> str:
    """rows: list of {strategy, cagr, vol, sharpe, max_drawdown, ulcer, calmar, martin, ...}.
    compact=True drops Ulcer/Calmar/Martin (keep them for collapsed details view)."""
    df = pd.DataFrame(rows)
    if compact:
        cols = ["strategy", "sharpe", "cagr", "vol", "max_drawdown"]
    else:
        cols = ["strategy", "cagr", "vol", "sharpe", "max_drawdown", "ulcer", "calmar", "martin"]
    cols = [c for c in cols if c in df.columns]
    df = df[cols]
    rename = {"strategy": "Strategy", "cagr": "CAGR", "vol": "Vol", "sharpe": "Sharpe",
              "max_drawdown": "MaxDD", "ulcer": "Ulcer", "calmar": "Calmar", "martin": "Martin"}
    df.columns = [rename[c] for c in cols]
    body = ""
    pct_cols = {"CAGR", "Vol", "MaxDD", "Ulcer"}
    for _, r in df.iterrows():
        body += f"<tr><td>{r['Strategy']}</td>"
        for c in df.columns[1:]:
            val = r[c]
            cell = fmt_pct(val) if c in pct_cols else fmt_num(val)
            body += f"<td style='text-align:right'>{cell}</td>"
        body += "</tr>\n"
    header = "".join(f"<th>{c}</th>" for c in df.columns)
    return f"""<div class='table-scroll'><table class='perf'>
<thead><tr>{header}</tr></thead>
<tbody>{body}</tbody></table></div>"""


def yearly_table_html(blended: pd.Series, qqq: pd.Series, cpm: pd.Series,
                       bull: pd.Series, ndx: pd.Series, naive: pd.Series) -> str:
    yr_b = ((1 + blended).resample("YE").prod() - 1)
    yr_f = ((1 + cpm).resample("YE").prod() - 1)
    yr_bu = ((1 + bull).resample("YE").prod() - 1)
    yr_nd = ((1 + ndx).resample("YE").prod() - 1)
    yr_q = ((1 + qqq.reindex(blended.index)).resample("YE").prod() - 1)
    yr_n = ((1 + naive.reindex(blended.index)).resample("YE").prod() - 1)
    df = pd.DataFrame({"Year": yr_b.index.year,
                       "PROD": yr_b.values * 100,
                       "CPM": yr_f.reindex(yr_b.index).values * 100,
                       "BULL-SPY": yr_bu.reindex(yr_b.index).values * 100,
                       "NDX": yr_nd.reindex(yr_b.index).values * 100,
                       "BB4 lit": yr_n.reindex(yr_b.index).values * 100,
                       "QQQ": yr_q.reindex(yr_b.index).values * 100})
    df["Excess vs BB4"] = df["PROD"] - df["BB4 lit"]
    df["Excess vs QQQ"] = df["PROD"] - df["QQQ"]
    body = ""
    for _, r in df.iterrows():
        ex_n = r["Excess vs BB4"]
        ex_q = r["Excess vs QQQ"]
        exn_class = "pos" if ex_n > 0 else "neg"
        exq_class = "pos" if ex_q > 0 else "neg"
        body += f"<tr><td>{int(r['Year'])}</td>"
        for col in ["PROD", "CPM", "BULL-SPY", "NDX", "BB4 lit", "QQQ"]:
            v = r[col]
            cls = "pos" if v > 0 else "neg"
            body += f"<td style='text-align:right' class='{cls}'>{v:+.2f}%</td>"
        body += f"<td style='text-align:right' class='{exn_class}'>{ex_n:+.2f}pp</td>"
        body += f"<td style='text-align:right' class='{exq_class}'>{ex_q:+.2f}pp</td></tr>\n"
    return f"""<div class='table-scroll'><table class='yearly'>
<thead><tr><th>Year</th><th>PROD<br>(60/20/20)</th><th>CPM only</th><th>BULL-SPY only</th><th>NDX only</th><th>BB4 lit blend</th><th>QQQ</th><th>Ex vs BB4</th><th>Ex vs QQQ</th></tr></thead>
<tbody>{body}</tbody></table></div>"""


# Production blend weights
CPM_WEIGHT = 0.6
BULL_WEIGHT = 0.2
NDX_WEIGHT = 0.2


# NDX-100 sector map (manual, covers most current/historical mega-caps).
# Used only for the dashboard concentration display.
NDX_SECTORS = {
    # Semis
    "NVDA":"Semis", "AVGO":"Semis", "AMD":"Semis", "INTC":"Semis",
    "QCOM":"Semis", "AMAT":"Semis", "MU":"Semis", "LRCX":"Semis",
    "KLAC":"Semis", "MCHP":"Semis", "MRVL":"Semis", "NXPI":"Semis",
    "ASML":"Semis", "ARM":"Semis", "ADI":"Semis", "ON":"Semis",
    "TXN":"Semis",
    # Mega-cap software / platforms
    "MSFT":"Software", "GOOGL":"Internet", "GOOG":"Internet",
    "META":"Internet", "AAPL":"Hardware/Software", "AMZN":"Internet/Retail",
    "NFLX":"Streaming", "ADBE":"Software", "CRM":"Software",
    "INTU":"Software", "ORCL":"Software", "NOW":"Software",
    "SNPS":"Software/EDA", "CDNS":"Software/EDA", "WDAY":"Software",
    "CTSH":"Software", "FTNT":"Cybersec", "PANW":"Cybersec",
    "CRWD":"Cybersec", "ZS":"Cybersec", "CSCO":"Networking",
    # Storage / hardware
    "WDC":"Storage", "STX":"Storage", "SNDK":"Storage",
    # Consumer
    "TSLA":"Auto/EV", "COST":"Retail", "PEP":"Consumer Staples",
    "MDLZ":"Consumer Staples", "MAR":"Hospitality", "BKNG":"Travel",
    "ABNB":"Travel", "DASH":"Internet", "LULU":"Apparel",
    "SBUX":"Restaurants", "MNST":"Beverages", "KDP":"Beverages",
    # Healthcare/biotech
    "AMGN":"Biotech", "GILD":"Biotech", "VRTX":"Biotech",
    "REGN":"Biotech", "ISRG":"MedTech", "DXCM":"MedTech",
    "IDXX":"MedTech", "MRNA":"Biotech", "BIIB":"Biotech",
    # Other
    "TMUS":"Telecom", "CMCSA":"Media/Cable", "CHTR":"Media/Cable",
    "PYPL":"Fintech", "PDD":"Internet/Retail", "MELI":"Internet/Retail",
    "PCAR":"Trucks", "FAST":"Industrials", "CSX":"Rail",
    "ODFL":"Trucks", "EXC":"Utilities", "AEP":"Utilities",
    "XEL":"Utilities", "CTAS":"Services", "ROST":"Retail",
    "ORLY":"Auto Parts", "AZN":"Pharma",
    # Current NDX-100 additions (2026-05)
    "ADP":"Services", "PAYX":"Services",
    "ADSK":"Software", "EA":"Gaming", "TTWO":"Gaming",
    "DDOG":"Software", "PLTR":"Software", "SHOP":"Internet/Retail",
    "APP":"AdTech", "MSTR":"Software", "CSGP":"Data/RE",
    "VRSK":"Data/Analytics", "TRI":"Media/Data",
    "ALNY":"Biotech", "INSM":"Biotech", "ENDP":"Pharma",
    "GEHC":"MedTech",
    "MPWR":"Semis",
    "AXON":"Defense", "HON":"Industrials", "ROP":"Industrials",
    "CPRT":"Auto Services", "FER":"Auto",
    "BKR":"Energy", "FANG":"Energy", "CEG":"Utilities",
    "LIN":"Materials",
    "CCEP":"Beverages", "KHC":"Consumer Staples", "WMT":"Retail",
    "WBD":"Media", "NWSA":"Media", "WLTW":"Insurance/Consulting",
}

def _ndx_sector_summary(picks: list) -> str:
    if not picks:
        return "(no active picks)"
    counts = {}
    for t in picks:
        s = NDX_SECTORS.get(t, "Unknown/?")
        counts[s] = counts.get(s, 0) + 1
    parts = [f"{c} {s}" for s, c in sorted(counts.items(), key=lambda x: -x[1])]
    return " · ".join(parts)


def current_alloc_html(panel: pd.DataFrame, sig_d: pd.Timestamp,
                         bull_qqq_rets: pd.Series | None = None,
                         ndx_rets: pd.Series | None = None,
                         art = None) -> str:
    # Pull current allocation from precomputed records (no recomputation).
    if art is not None:
        records = [r for r in art.cpm_records if r["sig_d"] <= sig_d]
        bull_records_subset = [r for r in art.bull_records if r["sig_d"] <= sig_d]
        ndx_records_subset = [r for r in art.ndx_records if r["sig_d"] <= sig_d] if art.ndx_records else []
        cpm_rec = records[-1] if records else {"weights": {}, "pair": None, "regime": "DEFENSIVE", "safe": DEFAULT_CASH}
        bull_rec = bull_records_subset[-1] if bull_records_subset else {"weights": {}, "regime": "CASH", "diag": {}}
        ndx_rec = ndx_records_subset[-1] if ndx_records_subset else None
    else:
        # Fallback when art is not provided.
        records = cpm_signal_records(panel, pd.Timestamp("1900-01-01"), sig_d)
        cpm_rec = records[-1] if records else {"weights": {}, "pair": None, "regime": "DEFENSIVE", "safe": DEFAULT_CASH}
        bull_rec = ndx_rec = None
    weights = cpm_rec["weights"]
    pair = cpm_rec["pair"]
    regime = cpm_rec["regime"]
    safe = cpm_rec["safe"]

    # CPM sleeve (60%)
    fcp_html = "".join(f"<tr><td>{t}</td><td style='text-align:right'>{w*100:.1f}%</td></tr>"
                        for t, w in sorted(weights.items(), key=lambda x: -x[1]))
    pair_str = f"{pair[0]} + {pair[1]}" if pair else "-"

    # BULL-SPY sleeve (20%) -- from precomputed record if available
    if bull_rec is not None:
        bq_w, bq_regime, bq_diag = bull_rec["weights"], bull_rec["regime"], bull_rec["diag"]
    else:
        bq_w, bq_regime, bq_diag = compute_bull_qqq_weights(panel, sig_d)
    bq_html = "".join(f"<tr><td>{t}</td><td style='text-align:right'>{w*100:.1f}%</td></tr>"
                        for t, w in sorted(bq_w.items(), key=lambda x: -x[1]))
    cstate = bq_diag.get("state", "---")
    if bq_regime.startswith("BULL_"):
        bq_state = f"{bq_regime} (canary {cstate})"
    else:
        bq_state = f"CASH ({bq_diag.get('reason','-')}; canary {cstate})"

    # NDX sleeve (20%) -- gated by BULL-SPY regime
    try:
        from ndx_sleeve_live import compute_ndx_weights, load_ndx_panel, SELECT_K as NDX_SELECT_K
        if ndx_rec is not None:
            ndx_w, ndx_regime, ndx_diag = ndx_rec["weights"], ndx_rec["regime"], ndx_rec["diag"]
        else:
            ndx_panel_data = load_ndx_panel()
            ndx_w, ndx_regime, ndx_diag = compute_ndx_weights(panel, ndx_panel_data, sig_d)
        ndx_html = "".join(f"<tr><td>{t}</td><td style='text-align:right'>{w*100:.1f}%</td></tr>"
                            for t, w in sorted(ndx_w.items(), key=lambda x: -x[1]))
        if ndx_regime == "NDX_ACTIVE" or ndx_regime.startswith("NDX_PARTIAL"):
            sel = ndx_diag.get('selected', [])
            sector_summary = _ndx_sector_summary(sel)
            mode = f"{ndx_regime} · top-{NDX_SELECT_K} by GPM"
            ndx_state = (f"{mode}: {', '.join(sel)}<br>Sector mix: {sector_summary}")
        else:
            ndx_state = f"{ndx_regime} -- {ndx_diag.get('reason', '100% cash')}"
    except (FileNotFoundError, ImportError) as e:
        ndx_w = {CASH_TICKER: 1.0}
        ndx_html = "<tr><td colspan='2'>(NDX panel not available)</td></tr>"
        ndx_state = f"NDX panel data unavailable ({e})"

    # Combined 60% CPM + 20% BULL-SPY + 20% NDX  (UNSCALED)
    combined_uncapped = {}
    for t, w in weights.items():
        combined_uncapped[t] = combined_uncapped.get(t, 0.0) + w * CPM_WEIGHT
    for t, w in bq_w.items():
        combined_uncapped[t] = combined_uncapped.get(t, 0.0) + w * BULL_WEIGHT
    for t, w in ndx_w.items():
        combined_uncapped[t] = combined_uncapped.get(t, 0.0) + w * NDX_WEIGHT

    # Combined target weights (no extra portfolio cap overlay)
    combined = combined_uncapped
    combined_html = "".join(f"<tr><td>{t}</td><td style='text-align:right'>{w*100:.1f}%</td></tr>"
                             for t, w in sorted(combined.items(), key=lambda x: -x[1])
                             if abs(w) > 1e-6)

    # LQD/IEF credit-spread circuit state for NDX sleeve
    from circuit_breaker import current_circuit_state, LQD_IEF_EMA_SPAN
    try:
        st = current_circuit_state(panel["LQD"], panel["IEF"])
        triggered = st["triggered"]
        color = "#e74c3c" if triggered else "#2ecc71"
        status = "⚠️ CIRCUIT TRIGGERED" if triggered else "✓ Normal"
        dist_pct = st["distance_pct"]
        dd_status_html = (
            f"<div style='grid-column: 1 / -1; background:#fafafa;border-left:4px solid {color};"
            f"padding:8px 12px;margin:8px 0;border-radius:4px;font-size:0.88rem;'>"
            f"<strong>NDX LQD/IEF circuit</strong>: {status} "
            f"&middot; ratio <strong>{st['ratio']:.4f}</strong> "
            f"(EMA{LQD_IEF_EMA_SPAN} {st['ema']:.4f}, {dist_pct:+.2f}%) "
            f"&middot; as of {st['as_of_date'].date() if st.get('as_of_date') else 'n/a'}"
            f"</div>"
        )
    except Exception as _e:
        dd_status_html = f"<p style='color:#999'>NDX circuit state unavailable: {_e}</p>"

    # Build prior-vs-target trade-delta table (compare to PREVIOUS signal date if available)
    prev_combined = {}
    if len(records) >= 2:
        prev_rec = records[-2]
        prev_weights = prev_rec.get("weights", {})
        try:
            prev_sd = prev_rec.get("sig_d", None)
            # Prefer precomputed bull/ndx records (no recomputation)
            if art is not None and prev_sd is not None:
                prev_bull_rec = next((r for r in reversed(art.bull_records) if r["sig_d"] == prev_sd), None)
                prev_ndx_rec = next((r for r in reversed(art.ndx_records) if r["sig_d"] == prev_sd), None) if art.ndx_records else None
                prev_bq_w = prev_bull_rec["weights"] if prev_bull_rec else {}
                prev_ndx_w = prev_ndx_rec["weights"] if prev_ndx_rec else {}
            else:
                prev_bq_w, _, _ = compute_bull_qqq_weights(panel, prev_sd) if prev_sd is not None else ({}, None, {})
                prev_ndx_w, _, _ = compute_ndx_weights(panel, ndx_panel_data, prev_sd) if prev_sd is not None else ({}, None, {})
        except Exception:
            prev_bq_w, prev_ndx_w = {}, {}
        for t, w in prev_weights.items():
            prev_combined[t] = prev_combined.get(t, 0.0) + w * CPM_WEIGHT
        for t, w in prev_bq_w.items():
            prev_combined[t] = prev_combined.get(t, 0.0) + w * BULL_WEIGHT
        for t, w in prev_ndx_w.items():
            prev_combined[t] = prev_combined.get(t, 0.0) + w * NDX_WEIGHT
    all_keys = set(combined) | set(prev_combined)
    trade_rows = []
    hold_count = 0
    for t in sorted(all_keys, key=lambda k: -abs((combined.get(k, 0.0) - prev_combined.get(k, 0.0)))):
        prev_w = prev_combined.get(t, 0.0)
        new_w = combined.get(t, 0.0)
        delta = new_w - prev_w
        if abs(prev_w) < 1e-6 and abs(new_w) < 1e-6: continue
        if abs(delta) < 1e-4:
            hold_count += 1
            continue
        sign = "BUY " if delta > 0 else "SELL"
        color = "#1d8348" if delta > 0 else "#c0392b"
        trade_rows.append(
            f"<tr><td>{t}</td><td style='text-align:right'>{prev_w*100:.1f}%</td>"
            f"<td style='text-align:right'>{new_w*100:.1f}%</td>"
            f"<td style='text-align:right;color:{color};font-weight:600'>{sign} {abs(delta)*100:.1f}pp</td></tr>"
        )
    if trade_rows:
        hold_note = f"<p style='font-size:0.75rem;color:#888;margin:4px 0 0 0'>({hold_count} unchanged positions hidden)</p>" if hold_count else ""
        trade_html = ("<table class='alloc'><thead><tr><th>Ticker</th>"
                      "<th style='text-align:right'>Prior</th>"
                      "<th style='text-align:right'>Target</th>"
                      "<th style='text-align:right'>Trade</th></tr></thead><tbody>"
                      + "".join(trade_rows) + "</tbody></table>" + hold_note)
    else:
        trade_html = "<p style='font-size:0.85rem;color:#666'>(no rebalance trades needed; all positions unchanged from prior signal)</p>"

    # Combined target weights table
    combined_target_html = "".join(
        f"<tr><td>{t}</td><td style='text-align:right;font-weight:600'>{w*100:.1f}%</td></tr>"
        for t, w in sorted(combined.items(), key=lambda x: -x[1])
        if abs(w) > 1e-6
    )

    # Bull-QQQ + NDX picks one-liner (for top summary)
    bull_pick = next(iter(bq_w), CASH_TICKER) if bq_w else CASH_TICKER
    ndx_picks_str = ", ".join(ndx_diag.get("selected", [])) if ndx_diag.get("selected") else "(cash)"
    sector_str = _ndx_sector_summary(ndx_diag.get("selected", [])) if ndx_diag.get("selected") else ""

    return f"""
<div class='alloc-grid'>
<div class='alloc-row' style='grid-column: 1 / -1; display: grid; grid-template-columns: 1fr; gap: 14px;'>
  <style>@media (min-width: 900px) {{ .alloc-row {{ grid-template-columns: minmax(0, 1fr) minmax(0, 1.2fr) !important; }} }}</style>
  <div>
    <h4 style='background:#fff4d6;padding:8px 12px;border-radius:4px;margin:0 0 8px 0'>Final portfolio target {int(CPM_WEIGHT*100)}/{int(BULL_WEIGHT*100)}/{int(NDX_WEIGHT*100)}</h4>
    <div class='table-scroll'><table class='alloc'>{combined_target_html}</table></div>
  </div>
  <div>
    <h4 style='background:#e8f4fd;padding:8px 12px;border-radius:4px;margin:0 0 8px 0'>Rebalance trade (vs prior signal)</h4>
    <div class='table-scroll'>{trade_html}</div>
  </div>
</div>
<div style='grid-column: 1 / -1'>
  <details>
    <summary style='font-weight:600;cursor:pointer'>Signal diagnostics (sleeves, selection details)</summary>
    <div style='margin-top:10px'>
    <p style='font-size:0.85rem;margin:6px 0'><strong>CPM</strong> ({int(CPM_WEIGHT*100)}% of capital, regime <strong>{regime}</strong>): pair = <strong>{pair_str}</strong>, safe = {safe}</p>
    <p style='font-size:0.85rem;margin:6px 0'><strong>BULL-SPY</strong> ({int(BULL_WEIGHT*100)}% of capital, state <strong>{bq_state}</strong>): holding <strong>{bull_pick}</strong></p>
    <p style='font-size:0.85rem;margin:6px 0'><strong>NDX</strong> ({int(NDX_WEIGHT*100)}% of capital, state <strong>{ndx_regime}</strong>): top-{NDX_SELECT_K} = {ndx_picks_str}{(' · sectors: ' + sector_str) if sector_str else ''}</p>
    {dd_status_html}
    <h4 style='margin-top:14px'>Sleeve-internal weights (sum to 100% of each sleeve)</h4>
    <div style='display:grid;grid-template-columns:repeat(auto-fit, minmax(220px, 1fr));gap:14px'>
      <div><strong>CPM</strong><div class='table-scroll'><table class='alloc'>{fcp_html}</table></div></div>
      <div><strong>BULL-SPY</strong><div class='table-scroll'><table class='alloc'>{bq_html}</table></div></div>
      <div><strong>NDX</strong><div class='table-scroll'><table class='alloc'>{ndx_html}</table></div></div>
    </div>
    </div>
  </details>
</div>
</div>
"""


# ---------- Main ----------

def main():
    ap = argparse.ArgumentParser()
    # Default to strict live-ETF CLEAN window 18.1y (2008-04-30).
    # Matches README CLEAN headline.
    ap.add_argument("--start", default="2008-04-30")
    ap.add_argument("--end", default=None)
    ap.add_argument("--out", default=str(ROOT / "cpm_dashboard.html"))
    args = ap.parse_args()
    
    start = pd.Timestamp(args.start)
    end = pd.Timestamp(args.end) if args.end else pd.Timestamp.today().normalize()
    
    # Load with sufficient warmup so CPM signals + BULL-SPY 12mo TR momentum are stable
    panel_start = min(start - pd.DateOffset(years=20), pd.Timestamp("1995-01-01"))
    print(f"Loading panel from {panel_start.date()} (warmup for EMA200 canary) ...")
    panel = load_panel(start=panel_start, end=end)
    print(f"Panel: {panel.index[0].date()} -> {panel.index[-1].date()}, {len(panel.columns)} assets")
    
    # Compute all sleeves, overlays, and per-signal records ONCE.
    # Every downstream chart/table pulls from `art` (no more drift between
    # diagnostic and backtest paths). See `build_artifacts()` definition.
    print("Computing sleeves + overlays + signal records (single pass) ...")
    from ndx_sleeve_live import load_ndx_panel, SELECT_K as NDX_SELECT_K
    try:
        ndx_panel = load_ndx_panel()
    except FileNotFoundError:
        print("  NDX panel data not found; skipping NDX sleeve.")
        ndx_panel = None
    art = build_artifacts(panel, ndx_panel, start, end)
    prod_label = f"CPM-BULL-NDX ({int(CPM_W*100)}/{int(BULL_W*100)}/{int(NDX_W*100)}) + NDX LQD/IEF circuit"

    print(f"Running peer strategies ...")
    spy = panel["SPY"].ffill().pct_change().loc[start:end].fillna(0.0) if "SPY" in panel.columns else pd.Series(dtype=float)
    qqq = panel["QQQ"].ffill().pct_change().loc[start:end].fillna(0.0) if "QQQ" in panel.columns else pd.Series(dtype=float)
    six40 = sixty_forty(panel, start, end)
    bb4_blend = bench_bb4_blend(panel, start, end)
    static_pp_qqq = bench_static_pp_qqq(panel, start, end, pp_weight=0.80, growth_ticker="QQQ")

    strategies = {
        prod_label: art.blend,
        "CPM standalone": art.cpm,
        "BULL-SPY sleeve": art.bull,
        "NDX sleeve": art.ndx,
        "BB4 lit blend (60 AAA+TIP / 20 HAA-S SPY / 20 QQQ-trend)": bb4_blend,
        "Static 80% PP + 20% QQQ": static_pp_qqq,
        "QQQ buy-hold": qqq,
    }
    
    # Build perf table
    perf_rows = []
    for name, daily in strategies.items():
        if daily.empty: continue
        m = perf_metrics(daily)
        m["strategy"] = name
        perf_rows.append(m)
    perf_rows = sorted(perf_rows, key=lambda r: -r.get("sharpe", -99))
    
    # Build charts
    print("Building charts ...")
    # Core comparison: PROD + 3 sleeves + 2 active TAA benchmarks + 1 static + QQQ
    CORE_CHARTS = (prod_label, "CPM standalone", "BULL-SPY sleeve", "NDX sleeve",
                   "BB4 lit blend (60 AAA+TIP / 20 HAA-S SPY / 20 QQQ-trend)",
                   "Static 80% PP + 20% QQQ", "QQQ buy-hold")
    fig_equity = chart_equity({k: v for k, v in strategies.items() if k in CORE_CHARTS},
                              prod_label=prod_label)
    fig_dd = chart_drawdown({k: v for k, v in strategies.items() if k in CORE_CHARTS},
                            prod_label=prod_label)
    fig_yearly = chart_yearly_bars(art.blend, qqq, strategies["BB4 lit blend (60 AAA+TIP / 20 HAA-S SPY / 20 QQQ-trend)"])
    fig_monthly_heatmap = chart_monthly_heatmap(art.blend, title="PROD 60/20/20 Monthly Returns Heatmap")
    fig_rolling = chart_rolling_sharpe(art.blend, strategies["BB4 lit blend (60 AAA+TIP / 20 HAA-S SPY / 20 QQQ-trend)"])
    fig_excess = chart_rolling_excess(art.cpm, art.blend, strategies["BB4 lit blend (60 AAA+TIP / 20 HAA-S SPY / 20 QQQ-trend)"], art.bull)
    fig_roll_dd = chart_rolling_dd(art.cpm, art.blend, strategies["BB4 lit blend (60 AAA+TIP / 20 HAA-S SPY / 20 QQQ-trend)"], art.bull)
    fig_canary, regime_counts, picks, pair_counter = chart_canary_timeline(
        panel, start, records=art.cpm_records, bull_records=art.bull_records)
    fig_canary_heatmap = chart_canary_state_heatmap(panel, art.cpm, art.bull, start)
    fig_asset_picked, asset_picked_rows = chart_asset_when_picked(panel, start, records=art.cpm_records)
    fig_sleeve_contrib = chart_sleeve_contribution(art.cpm, art.bull, art.ndx, CPM_W, BULL_W, NDX_W)
    drawdowns_html = table_worst_drawdowns(art.cpm, art.bull, art.ndx, CPM_W, BULL_W, NDX_W, top_n=10)
    fig_def_pct = chart_rolling_defensive_pct(panel, start, records=art.cpm_records)
    fig_pair_timeline = chart_pair_pick_timeline(panel, start, records=art.cpm_records)
    fig_sleeve_corr = chart_rolling_sleeve_correlation(art.cpm, art.bull, art.ndx)
    fig_distributions = chart_monthly_return_distributions(art.cpm, art.bull, art.ndx, CPM_W, BULL_W, NDX_W)
    n_signals = regime_counts["RISK_ON"] + regime_counts["DEFENSIVE"]
    # picks_table reads from precomputed cpm_records (memoized, so 'free' call).
    picks_html = picks_table_html(picks, pair_counter, n_signals,
                                    records=art.cpm_records, panel=panel)
    regime_pct_def = regime_counts["DEFENSIVE"] / max(1, n_signals) * 100
    regime_pct_ron = regime_counts["RISK_ON"] / max(1, n_signals) * 100
    fig_corr = chart_correlations({k: v for k, v in strategies.items() if k in CORE_CHARTS})
    fig_riskret = chart_risk_return_scatter(
        {k: v for k, v in strategies.items() if k in CORE_CHARTS},
        prod_label=prod_label,
    )
    # TT-style integrated equity + drawdown chart for headline.
    # PROD vs closest benchmark (BB4 lit blend).
    bb4_for_headline = strategies.get("BB4 lit blend (60 AAA+TIP / 20 HAA-S SPY / 20 QQQ-trend)")
    headline_strats = {prod_label: art.blend}
    if bb4_for_headline is not None and not bb4_for_headline.empty:
        headline_strats["BB4 lit blend (60 AAA+TIP / 20 HAA-S SPY / 20 QQQ-trend)"] = bb4_for_headline
    fig_eq_dd_headline = chart_equity_dd_combined(headline_strats,
                                                    prod_label=prod_label)
    top_dd_html = topN_drawdowns_html(art.blend, n=10)
    period_summary = period_summary_html(art.blend)

    # Current allocation: use last COMPLETED month-end as signal date
    today = panel.index[-1]
    prior_month_end = today.replace(day=1) - pd.Timedelta(days=1)
    candidates = panel.index[panel.index <= prior_month_end]
    sig_d = candidates[-1] if len(candidates) > 0 else today
    alloc_html = current_alloc_html(panel, sig_d,
                                       bull_qqq_rets=art.bull,
                                       ndx_rets=art.ndx,
                                       art=art)

    # Audit-block values
    import subprocess
    try:
        git_sha = subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
            text=True, timeout=2).strip()
    except Exception:
        git_sha = "unknown"
    panel_index_last = panel.index[-1].date()
    try:
        from ndx_sleeve_live import load_ndx_panel
        _np = load_ndx_panel()
        ndx_snapshot_date = _np.index[-1].date()
    except Exception:
        ndx_snapshot_date = "unknown"

    # Trade due date = first trading day AFTER signal date (T+1 OPEN)
    next_idx_pos = panel.index.searchsorted(sig_d) + 1
    trade_due_date = panel.index[next_idx_pos].date() if next_idx_pos < len(panel.index) else "future"
    age_days = (pd.Timestamp.today().normalize() - pd.Timestamp(sig_d)).days
    if age_days <= 7:
        age_status = "<span style='color:#1d8348;font-weight:600'>CURRENT</span>"
    elif age_days <= 35:
        age_status = "<span style='color:#6f4e00'>recent</span>"
    else:
        age_status = f"<span style='color:#c0392b;font-weight:600'>STALE (next signal end of month)</span>"
    
    # Per-sleeve breakdown of the PROD blend.
    sleeve_rows = [
        {"strategy": "CPM-BULL-NDX 60/20/20 (PRODUCTION)",            **perf_metrics(art.blend)},
        {"strategy": "CPM standalone (60% weight)",                   **perf_metrics(art.cpm)},
        {"strategy": "BULL-SPY standalone (20% weight)",              **perf_metrics(art.bull)},
        {"strategy": "NDX standalone (20% weight)",                   **perf_metrics(art.ndx)},
    ]

    # Alpha/beta/corr decomposition vs canonical benchmarks (BB4 blend +
    # per-sleeve literature counterparts). Daily-return OLS regression.
    print("Computing alpha/beta/corr vs canonical benchmarks ...")
    bench_b2 = bench_aaa_tip(panel, start, end)   # AAA+TIP canary CLEAN-7 (sleeve canonical for CPM)
    bench_b3 = bench_haa_simple(panel, start, end, asset="SPY")  # HAA-Simple SPY (BULL canonical)
    bench_b5 = bench_qqq_12mo_trend(panel, start, end)  # QQQ 12mo trend (NDX-equity peer)
    alpha_beta_rows = []
    spy_d = panel["SPY"].ffill().pct_change().loc[start:end].fillna(0.0) if "SPY" in panel.columns else pd.Series(dtype=float)
    qqq_d = panel["QQQ"].ffill().pct_change().loc[start:end].fillna(0.0) if "QQQ" in panel.columns else pd.Series(dtype=float)
    for label, strat, bench, bench_label in [
        ("PROD 60/20/20",  art.blend, bb4_blend,      "BB4 lit blend (60 AAA+TIP / 20 HAA-S SPY / 20 QQQ-trend)"),
        ("PROD 60/20/20",  art.blend, static_pp_qqq,  "Static 80% PP + 20% QQQ (vol-matched)"),
        ("PROD 60/20/20",  art.blend, spy_d,          "SPY buy-hold"),
        ("PROD 60/20/20",  art.blend, qqq_d,          "QQQ buy-hold"),
        ("CPM-ext sleeve", art.cpm,   bench_b2,  "B2 AAA + TIP canary (CLEAN-7)"),
        ("CPM-ext sleeve", art.cpm,   spy_d,     "SPY buy-hold"),
        ("BULL-ext sleeve",art.bull,  bench_b3,  "B3 HAA-Simple SPY"),
        ("BULL-ext sleeve",art.bull,  spy_d,     "SPY buy-hold"),
        ("NDX sleeve",     art.ndx,   bench_b5,  "B5 QQQ 12mo trend (Antonacci GEM)"),
        ("NDX sleeve",     art.ndx,   qqq_d,     "QQQ buy-hold"),
    ]:
        m = alpha_beta_corr(strat, bench)
        alpha_beta_rows.append({
            "strategy": label, "benchmark": bench_label,
            "alpha_ann_pct": m["alpha_ann_pct"],
            "beta": m["beta"], "corr": m["corr"],
        })

    # ========================================================
    # Extended backtest from QQQ inception.
    # ========================================================
    ext_start = pd.Timestamp("1999-03-10")
    print(f"Running EXT backtest {ext_start.date()} ...")
    # EXT window uses the same single-pass artifacts builder.
    # EXT charts use the raw blend.
    # EXT only needs daily returns for yearly bars / rolling Sharpe charts;
    # skip records to save ~7s on the deep history pass.
    ext_art = build_artifacts(panel, ndx_panel, ext_start, end, include_records=False)
    ext_qqq = panel["QQQ"].ffill().pct_change().loc[ext_start:end].fillna(0.0) if "QQQ" in panel.columns else pd.Series(dtype=float)
    ext_bb4 = bench_bb4_blend(panel, ext_start, end)

    ext_static_pp_qqq = bench_static_pp_qqq(panel, ext_start, end, pp_weight=0.80, growth_ticker="QQQ")
    ext_strategies = {
        prod_label: ext_art.blend,
        "CPM standalone": ext_art.cpm,
        "BULL-SPY sleeve": ext_art.bull,
        "NDX sleeve": ext_art.ndx,
        "BB4 lit blend (60 AAA+TIP / 20 HAA-S SPY / 20 QQQ-trend)": ext_bb4,
        "Static 80% PP + 20% QQQ": ext_static_pp_qqq,
        "QQQ buy-hold": ext_qqq,
    }
    ext_perf_rows = []
    for name, daily in ext_strategies.items():
        if daily.empty: continue
        m = perf_metrics(daily)
        m["strategy"] = name
        ext_perf_rows.append(m)
    ext_perf_rows = sorted(ext_perf_rows, key=lambda r: -r.get("sharpe", -99))

    print("Building EXT charts ...")
    ext_fig_equity = chart_equity(ext_strategies, prod_label=prod_label)
    ext_fig_dd = chart_drawdown(ext_strategies, prod_label=prod_label)
    ext_fig_yearly = chart_yearly_bars(ext_art.blend, ext_qqq, ext_bb4)
    ext_fig_rolling = chart_rolling_sharpe(ext_art.blend, ext_bb4)
    ext_fig_roll_dd = chart_rolling_dd(ext_art.cpm, ext_art.blend, ext_bb4, ext_art.bull)
    
    # Compose HTML
    print("Composing HTML ...")
    today = dt.date.today().isoformat()
    window_str = f"{start.date()} to {end.date()}"
    yrs_full = (end - start).days / 365.25
    prod_metrics = perf_metrics(art.blend)
    bull_metrics = perf_metrics(art.bull)
    ndx_metrics = perf_metrics(art.ndx) if art.ndx is not None and not art.ndx.empty else {'sharpe': float('nan'), 'cagr': float('nan'), 'max_drawdown': float('nan'), 'ulcer': float('nan'), 'martin': float('nan')}
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>CPM Strategy Dashboard</title>

<style>
  :root {{ --bg:#fafafa; --card:#fff; --border:#e8e8e8; --text:#222; --muted:#666; --pos:#1a8a1a; --neg:#cc3333; }}
  * {{ box-sizing: border-box; }}
  html, body {{ overflow-x:hidden; max-width:100vw; }}
  body {{ font-family:-apple-system,BlinkMacSystemFont,'SF Pro',Segoe UI,Roboto,sans-serif;
         background:var(--bg); color:var(--text); margin:0; padding:8px; line-height:1.45; font-size:14px; }}
  h1 {{ font-size:1.4rem; margin:0 0 0.3rem; }}
  h2 {{ font-size:1.1rem; margin:1.2rem 0 0.4rem; padding-bottom:0.3rem; border-bottom:1px solid var(--border); }}
  h3 {{ font-size:1rem; margin:0.8rem 0 0.4rem; }}
  h4 {{ font-size:0.92rem; margin:0.5rem 0 0.3rem; color:var(--muted); }}
  p {{ margin:0.4rem 0; }}
  .meta {{ color:var(--muted); font-size:0.82rem; }}
  .card {{ background:var(--card); border:1px solid var(--border); border-radius:8px;
           padding:8px; margin:8px 0; overflow:hidden; }}
  .table-scroll {{ overflow-x:auto; -webkit-overflow-scrolling:touch; margin:0 -4px; }}
  table {{ border-collapse: collapse; width:100%; font-size:0.85rem; min-width:fit-content; }}
  th, td {{ padding:5px 8px; border-bottom:1px solid var(--border); white-space:nowrap; }}
  th {{ background:#f3f3f3; font-weight:600; text-align:left; position:sticky; top:0; }}
  td.pos, .pos {{ color:var(--pos); }}
  td.neg, .neg {{ color:var(--neg); }}
  .perf tr:nth-child(odd), .yearly tr:nth-child(odd) {{ background:#fcfcfc; }}
  .alloc {{ font-size:0.92rem; width:100%; max-width:none; }}
  .alloc td:first-child {{ font-weight:600; }}
  .alloc-grid {{ display:grid; grid-template-columns: 1fr; gap:10px; }}
  ul {{ margin:0.4rem 0 0.4rem 1.2rem; padding:0; }}
  ul li {{ margin:0.15rem 0; word-wrap:break-word; }}
  code {{ background:#f0f0f0; padding:1px 4px; border-radius:3px; font-size:0.82rem;
          word-break:break-all; }}
  .footnote {{ font-size:0.78rem; color:var(--muted); margin-top:0.6rem; }}
  details summary {{ cursor:pointer; font-weight:600; padding:5px 0; }}
  img.chart {{ display:block; width:100%; height:auto; max-width:100%; }}
  div.chart {{ width:100%; max-width:100%; overflow-x:auto; }}
  div.chart svg {{ display:block; width:100%; height:auto; max-width:100%; }}
  /* Tablet+ */
  @media (min-width: 720px) {{
    body {{ padding:14px; font-size:14px; }}
    h1 {{ font-size:1.5rem; }}
    h2 {{ font-size:1.2rem; }}
    .card {{ padding:14px; margin:10px 0; }}
    th, td {{ padding:6px 10px; }}
    .alloc-grid {{ grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap:14px; }}
  }}
  /* Desktop */
  @media (min-width: 1024px) {{
    body {{ max-width:1200px; margin:0 auto; padding:20px; }}
  }}
  /* Print / PDF export */
  @media print {{
    body {{ max-width: 1100px; }}
    .card, .chart-card, table {{
      break-inside: avoid;
      page-break-inside: avoid;
    }}
    .alloc-grid > div {{
      break-inside: avoid;
      page-break-inside: avoid;
    }}
    table {{ font-size: 11px; }}
    h1, h2, h3, h4 {{
      break-after: avoid;
      page-break-after: avoid;
    }}
    .warning-banner {{ break-inside: avoid; }}
  }}
  .warning-banner {{
    color: #888;
    font-size: 0.78rem;
    margin: 4px 0 8px 0;
  }}
  .audit-block {{
    background: #f0f4f8;
    border: 1px solid #c8d4e0;
    padding: 8px 12px;
    border-radius: 4px;
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 0.78rem;
    color: #333;
    margin: 6px 0;
  }}
</style>
</head>
<body>

<p class='warning-banner'>Backtest only, not live-traded. IRA / 401k / Roth only.</p>

<h1>CPM-BULL-NDX Strategy Dashboard</h1>
<p class='meta'>{int(CPM_W*100)}/{int(BULL_W*100)}/{int(NDX_W*100)} CPM-BULL-NDX · monthly rebalance · T+1 OPEN · 10 bps/side · backtest {window_str} · built {today}</p>

<h2>→ This month's allocation</h2>
<div class='card'>
<div class='audit-block'>
Signal: <strong>{sig_d.date()}</strong> (last biz day of month) · Trade: <strong>T+1 OPEN</strong> ({trade_due_date}) · Age: {age_days}d · Status: {age_status}<br>
<span style='color:#888'>Data through {panel_index_last} · NDX snapshot {ndx_snapshot_date} · commit {git_sha} · built {today}</span>
</div>
{alloc_html}
</div>

<h2>Headline performance</h2>
<div class='card'>
<p style='margin:6px 0;font-size:0.92rem'>Backtest <strong>{yrs_full:.1f}y</strong> (post-cost): Sharpe <strong>{prod_metrics['sharpe']:.2f}</strong> · CAGR <strong>{prod_metrics['cagr']*100:.2f}%</strong> · MaxDD <strong>{prod_metrics['max_drawdown']*100:.2f}%</strong>.</p>
{perf_table_html(perf_rows, compact=True)}
{fig_to_html(fig_eq_dd_headline)}
<details>
  <summary style='font-size:0.85rem;color:#666;cursor:pointer'>Full metrics (Ulcer / Calmar / Martin)</summary>
  {perf_table_html(perf_rows)}
</details>
</div>

<details>
<summary><strong>Performance detail</strong> (period summary, risk-return scatter, top-10 drawdowns; click to expand)</summary>

<h3>Period-over-period</h3>
<div class='card'>
{period_summary}
</div>

<h3>Risk vs Return (yearly snapshots)</h3>
<div class='card'>
{fig_to_html(fig_riskret)}
</div>

<h3>Top 10 worst drawdowns</h3>
<div class='card'>
{top_dd_html}
</div>

</details>

<details>
<summary><strong>Strategy spec (sleeves)</strong></summary>
<div class='card'>
<ul>
<li><strong>CPM ({int(CPM_W*100)}%) -- AAA Pair-EW Extension:</strong> 9-asset risky universe (SPY, QQQ, SPHQ, EFA, EEM, VNQ, GLD, TLT, DBC), TIP 13612U canary (HAA canonical), GPM-penalized ranker (13612U * (1 - corr_260d)), top-{cpm_module.TOP_K_CANDIDATES} candidates (top-half), min-variance pair selection ({cpm_module.CORR_LOOKBACK_DAYS}d cov), 50/50 pair weight. HAA best-of-safe (SHV / IEF) by 13612U on defensive.</li>
<li><strong>BULL-SPY ({int(BULL_W*100)}%) -- HAA-Simple Extension:</strong> 100% SPY when both gates pass: (HYG_stitched OR TIP) 13612U &gt; 0 AND SPY 13612U &gt; 0. Else 100% HAA best-of-safe (SHV / IEF) by 13612U.</li>
<li><strong>NDX ({int(NDX_W*100)}%):</strong> Top-{NDX_SELECT_K} PIT Nasdaq-100 by GPM score (13612U momentum penalized by 260d correlation), equal-weight {100/NDX_SELECT_K:.1f}% each, gated strictly on TIP 13612U canary. When TIP canary is off, allocate 100% best-of-safe SHV/IEF. Daily LQD/IEF&lt;EMA50 intramonth circuit (duration-cancelled credit-spread proxy) latches defensive intramonth on credit-spread widening; releases at next monthly signal.</li>
</ul>
</div>
</details>

<details>
<summary><strong>Sleeve breakdown</strong></summary>
<div class='card'>
{perf_table_html(sleeve_rows)}
</div>
</details>

<details>
<summary><strong>Alpha / Beta / Correlation vs canonical benchmarks</strong> (daily OLS regression)</summary>
<div class='card'>
<p style='font-size:0.9em;color:#555'>Per-sleeve canonical: <code>CPM-ext vs B2 (AAA + TIP canary CLEAN-7)</code>, <code>BULL-ext vs B3 (HAA-Simple SPY)</code>, <code>NDX vs B5 (QQQ 12mo trend, Antonacci GEM)</code>. Blend canonical: <code>BB4 = 60% B2 + 20% B3 + 20% B5</code>. SPY/QQQ buy-hold rows show market-correlation diagnostics (low beta + low corr = portfolio diversifier, not levered equity).</p>
{alpha_beta_table_html(alpha_beta_rows)}
</div>
</details>

<details>
<summary><strong>Charts & analysis</strong> (equity curves, regime history, attribution, distributions; click to expand)</summary>

<h3>Equity & drawdown</h3>
<div class='card'>
{fig_to_html(fig_equity)}
{fig_to_html(fig_dd)}
{fig_to_html(fig_roll_dd)}
</div>

<h3>Returns by period</h3>
<div class='card'>
{fig_to_html(fig_yearly)}
{fig_to_html(fig_monthly_heatmap)}
{yearly_table_html(art.blend, qqq, art.cpm, art.bull, art.ndx, bb4_blend)}
</div>

<h3>Rolling metrics (12-month)</h3>
<div class='card'>
{fig_to_html(fig_rolling)}
{fig_to_html(fig_excess)}
{fig_to_html(fig_sleeve_corr)}
</div>

<h3>Regime & gate history</h3>
<div class='card'>
{fig_to_html(fig_canary)}
{fig_to_html(fig_def_pct)}
{fig_to_html(fig_canary_heatmap)}
</div>

<h3>Pair selection</h3>
<div class='card'>
{picks_html}
{fig_to_html(fig_pair_timeline)}
{fig_to_html(fig_asset_picked)}
</div>

<h3>Attribution & distributions</h3>
<div class='card'>
{fig_to_html(fig_sleeve_contrib)}
{drawdowns_html}
{fig_to_html(fig_distributions)}
{fig_to_html(fig_corr)}
</div>

<h3>Extended backtest ({ext_start.date()} -> {end.date()})</h3>
<div class='card'>
{perf_table_html(ext_perf_rows)}
{fig_to_html(ext_fig_equity)}
{fig_to_html(ext_fig_dd)}
{fig_to_html(ext_fig_yearly)}
{fig_to_html(ext_fig_rolling)}
</div>

<h3>EXT Rolling 3-Month Max Drawdown</h3>
<div class='card'>
{fig_to_html(ext_fig_roll_dd)}
</div>

</details>

<details>
<summary><strong>Strategy spec details</strong> (full sleeve mechanics)</summary>
<div class='card'>
<details>
<summary>CPM Sleeve ({int(CPM_W*100)}%) -- AAA Pair-EW Extension (CLEAN-7)</summary>
<ul>
<li><strong>Universe ({len(RISKY_UNIVERSE)}, CLEAN-7):</strong> US equity + international + real estate + diversifiers (canonical AAA cross-asset pool).
  <br><code>{', '.join(RISKY_UNIVERSE)}</code></li>
<li><strong>Safe pool:</strong> <code>{', '.join(SAFE_POOL)}</code> (HAA-style best-of-safe by 13612U momentum)</li>
<li><strong>Canary:</strong> TIP only -- 13612U &gt; 0 -&gt; risk-on; negative -&gt; 100% best-of-safe (HAA canonical TIP veto).</li>
<li><strong>Ranker:</strong> Faber * (1 - corr_260d) GPM-penalized score. <code>faber = (price - SMA10) / SMA10</code>; <code>corr_260d</code> = daily Pearson correlation of asset's returns over last 260d to equal-weighted basket return of the universe. Positive-momentum filter applies to raw Faber, not the penalized score.</li>
<li><strong>Top-K candidates:</strong> top {TOP_K_CANDIDATES} by GPM-penalized score (= ceil({len(RISKY_UNIVERSE)}/2), top-half rule), drop assets with raw Faber &le; 0</li>
<li><strong>Pair selection:</strong> minimum-variance 50/50 pair ({CORR_LOOKBACK_DAYS}d simple daily covariance lookback)</li>
<li><strong>Hold buffer:</strong> DISABLED (HB = 0). Was an overlay on the prior 9-asset spec; the AAA Pair-EW Extension does not use it.</li>
<li><strong>Partial-safe fill:</strong> 1 positive momentum &rarr; 50% asset + 50% best-of-safe; 0 positive &rarr; 100% best-of-safe</li>
<li><strong>Vol cap:</strong> DISABLED. Was an overlay on the prior 9-asset spec; the AAA Pair-EW Extension already delivers shallow MaxDD without it.</li>
<li><strong>Cost:</strong> {COST_BPS_PER_SIDE} bps/side</li>
<li><strong>Execution:</strong> month-end signal (T = last trading day of month, close), T+1 OPEN trade (next trading day MOO)</li>
</ul>
</details>
<details>
<summary>BULL-SPY Sleeve ({int(BULL_BLEND*100)}%) -- 2-layer regime gate (Keller/HAA canary + TSMOM trend filter)</summary>
<ul>
<li><strong>Bull asset:</strong> 100% <code>{BULL_TICKER}</code> (S&P 500 broad market). No state-conditional rotation.</li>
<li><strong>Canary gate:</strong> (HYG_stitched OR TIP) 13612U &gt; 0 (HAA-simple TIP canary plus credit breadth extension).</li>
<li><strong>Asset momentum gate:</strong> <code>{BULL_TICKER}</code> 13612U momentum &gt; 0 (HAA canonical). Fast and responsive (no slow 12mo lag).</li>
<li><strong>Daily overlay:</strong> -10% daily drawdown circuit breaker from 63d rolling-peak. Scale to cash (0.0) on breach, resets monthly.</li>
<li><strong>Fallback:</strong> HAA best-of-safe by 13612U momentum: <code>argmax(SHV, IEF)</code>. IEF in falling-rate regimes captures bond rally returns; SHV otherwise. May carry duration risk during IEF holding periods, so this sleeve is equity-or-defensive, not equity-or-cash.</li>
<li><strong>Standalone ({yrs_full:.1f}y, post-cost):</strong> Sharpe <strong>{bull_metrics['sharpe']:.2f}</strong>, CAGR <strong>{bull_metrics['cagr']*100:.2f}%</strong>, MaxDD <strong>{bull_metrics['max_drawdown']*100:.2f}%</strong>, Ulcer <strong>{bull_metrics['ulcer']*100:.2f}%</strong>, Martin <strong>{bull_metrics['martin']:.2f}</strong>.</li>

</ul>
</details>

<details>
<summary>NDX Sleeve ({int(NDX_W*100)}%) -- concentrated Nasdaq-100 momentum</summary>
<ul>
<li><strong>Universe:</strong> PIT Nasdaq-100 constituents (via <code>index-constitution</code> library, coverage 2006-01+).</li>
<li><strong>Signal:</strong> GPM score = 13612U momentum penalized by 260d correlation to equal-weighted NDX basket.</li>
<li><strong>Selection:</strong> top {NDX_SELECT_K} by GPM score (positive only), equal-weighted {100/NDX_SELECT_K:.1f}% each.</li>
<li><strong>Gate:</strong> Gated strictly on decoupled TIP 13612U canary &gt; 0 (no SPY trend filter check, allowing stock-level momentum to run undisturbed).</li>
<li><strong>Daily overlay:</strong> -10% daily drawdown circuit breaker from 63d rolling-peak. Scale to cash (0.0) on breach, resets monthly.</li>
<li><strong>Best-of-safe:</strong> HAA best-of-safe (SHV/IEF by 13612U) when gate is off. Partial-fill cash (when &lt;K positive candidates) also uses best-of-safe.</li>
<li><strong>Standalone ({yrs_full:.1f}y, post-cost):</strong> Sharpe <strong>{ndx_metrics['sharpe']:.2f}</strong>, CAGR <strong>{ndx_metrics['cagr']*100:.2f}%</strong>, MaxDD <strong>{ndx_metrics['max_drawdown']*100:.2f}%</strong>, Ulcer <strong>{ndx_metrics['ulcer']*100:.2f}%</strong>, Martin <strong>{ndx_metrics['martin']:.2f}</strong>.</li>
<li><strong>Tradeoff:</strong> High beta, high vol, deeper DD than other sleeves as standalone. Diluted by {int(NDX_W*100)}% blend weight, contributing meaningful CAGR uplift without dominating the blend's risk.</li>
</ul>
</details>
</div>

</details>

<details>
<summary><strong>Honest caveats</strong> (click to expand)</summary>
<div class='card'>
<ul style='line-height:1.5'>
<li><strong>Backtest only.</strong> Strategy is not live-traded.</li>
<li><strong>Data dependency.</strong> NDX results depend on PIT membership and available price history.</li>
<li><strong>Regime dependency.</strong> Defensive alpha depends on canary, trend, and diversifier behavior.</li>
<li><strong>Recovery lag.</strong> Monthly momentum signals can re-enter late after fast recoveries.</li>
<li><strong>Concentration.</strong> Risk-on regimes can concentrate in growth and Nasdaq exposure.</li>
</ul>
</div>

</details>

<p class='footnote' style='margin-top:30px'>Generated by <code>strategy_cpm/build_dashboard.py</code> on {today}.</p>

</body>
</html>
"""
    
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        f.write(html)
    print(f"\nDashboard written: {out_path}")
    print(f"File size: {out_path.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    main()
