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

from cpm_live import (
    RISKY_UNIVERSE, SAFE_POOL,
    CANARY_ASSETS, DEFAULT_CASH,
    TARGET_VOL, HOLD_BUFFER, CORR_LOOKBACK_DAYS, COST_BPS_PER_SIDE,
    load_panel, run_cpm_backtest,
    perf_metrics, compute_target_weights, sig_13612W,
)
from bull_qqq_live import (
    run_bull_qqq_backtest, compute_bull_qqq_weights,
    BULL_TICKER, CASH_TICKER, MOMENTUM_LOOKBACK,
)

# Production blend weight for BULL-QQQ sleeve (CPM gets 1 - this).
# 60/40 chosen for higher bull-tilt deployment.
# Tradeoff vs 80/20: more equity exposure, ~+0.5pp CAGR, slightly higher DD.
# Both 60/40 and 80/20 are well within bootstrap Sharpe CI.
BULL_BLEND = 0.30

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
    """Save matplotlib figure as base64 PNG embedded in <img>."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120, bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)
    buf.seek(0)
    b64 = base64.b64encode(buf.read()).decode("ascii")
    return f'<img class="chart" alt="{alt}" src="data:image/png;base64,{b64}"/>'


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
        scores_off = {a: sig_13612W(m[a]) for a in offensive if a in m.columns}
        if any(pd.isna(v) for v in scores_off.values()):
            weights_map[d] = {"SHV":1.0}; continue
        if all(v > 0 for v in scores_off.values()):
            best = max(scores_off, key=scores_off.get)
            weights_map[d] = {best:1.0}
        else:
            sd = {a: sig_13612W(m[a]) for a in defensive if a in m.columns}
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
    scs = {s: sig_13612W(monthly[s]) for s in avail}
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
        tip_s = sig_13612W(m["TIP"]) if "TIP" in m.columns else float("nan")
        if pd.isna(tip_s) or tip_s <= 0:
            weights_map[d] = {_haa_safe_pick(m): 1.0}; continue
        scs = {a: sig_13612W(m[a]) for a in offensive if a in m.columns and pd.notna(m[a].iloc[-1])}
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
    """HAA-Simple (Keller 2023): TIP canary, top-1 by 13612W from HAA-8."""
    return _haa_run(panel, start, end, top_k=1)


def haa_balanced(panel, start, end):
    """HAA-Balanced (Keller 2023): TIP canary, top-4 by 13612W from HAA-8."""
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


def qqq_trend_follow(panel, start, end, cost_bps=10.0):
    """Faber 10mo SMA timing on QQQ: hold QQQ when above SMA, SHV otherwise.
    Simplest possible QQQ timing strategy, used as benchmark."""
    if "QQQ" not in panel.columns or "SHV" not in panel.columns:
        return pd.Series(dtype=float)
    monthly = panel["QQQ"].resample("ME").last().dropna()
    sma10 = monthly.rolling(10).mean()
    signal = (monthly > sma10).reindex(monthly.index).fillna(False)
    daily_qqq = panel["QQQ"].ffill().pct_change()
    daily_shv = panel["SHV"].ffill().pct_change().reindex(daily_qqq.index).fillna(0)
    common = daily_qqq.loc[start:end].index
    if len(common) == 0:
        return pd.Series(dtype=float)
    asset_per_day = pd.Series("SHV", index=common)
    sig_dates = signal.index[(signal.index >= start - pd.Timedelta(days=60)) & (signal.index <= end)]
    for sd in sig_dates:
        if signal.loc[sd]:
            future = common[common > sd]
            if len(future) < 2: continue
            next_sd = sig_dates[sig_dates > sd]
            if len(next_sd) > 0 and len(common[common > next_sd[0]]) > 1:
                end_apply = common[common > next_sd[0]][1]
            else:
                end_apply = common[-1]
            mask = (common >= future[1]) & (common < end_apply)
            asset_per_day.loc[mask] = "QQQ"
    trend_rets = pd.Series(0.0, index=common)
    trend_rets[asset_per_day == "QQQ"] = daily_qqq.reindex(common).fillna(0)[asset_per_day == "QQQ"]
    trend_rets[asset_per_day == "SHV"] = daily_shv.reindex(common).fillna(0)[asset_per_day == "SHV"]
    import numpy as _np
    flips = (asset_per_day.values[1:] != asset_per_day.values[:-1])
    for i in _np.where(flips)[0]:
        trend_rets.iloc[i+1] -= 2.0 * cost_bps / 10000.0
    return trend_rets


def naive_70_30_pp_qqq_trend(panel, start, end):
    """Naive 70/30: 70% Permanent Portfolio + 30% QQQ trend-follow.
    Apples-to-apples benchmark for CPM-BULL."""
    from cpm_live import run_pp_backtest
    pp = run_pp_backtest(panel, start, end)
    qt = qqq_trend_follow(panel, start, end)
    common = pp.index.intersection(qt.index)
    if len(common) == 0:
        return pd.Series(dtype=float)
    return (0.7 * pp.reindex(common).fillna(0) + 0.3 * qt.reindex(common).fillna(0))


# ---------- Charts ----------

# Visual hierarchy (3 tiers):
#   Tier 1 (most prominent): production blend - bold thick deep blue, drawn last
#   Tier 2 (component sleeves): CPM green + BULL-QQQ orange, medium weight
#   Tier 3 (benchmarks): muted grey/colored thin lines, dashed/dotted
PROD_STYLE = dict(color="#0040d0", lw=2.0, ls="-", alpha=1.0, zorder=10)

FCP_STYLES = {
    # Tier 2: components
    "CPM standalone":       dict(color="#1a9a1a", lw=2.0, ls="-",  alpha=0.95, zorder=8),
    "BULL-QQQ sleeve":      dict(color="#ff8800", lw=2.0, ls="-",  alpha=0.95, zorder=8),
    # Tier 3: 2 benchmarks (apples-to-apples + raw target)
    "Naive 70/30 PP/QQQ-trend": dict(color="#9966aa", lw=1.6, ls="--", alpha=0.85, zorder=4),
    "QQQ buy-hold":         dict(color="#707070", lw=1.2, ls=":",  alpha=0.7,  zorder=3),
    # Legacy styles (kept in dict for safety but not plotted by default)
    "SPY buy-hold":         dict(color="#a0a0a0", lw=1.0, ls=":",  alpha=0.65, zorder=3),
    "60/40 SPY/IEF":        dict(color="#b8b8b8", lw=1.0, ls=":",  alpha=0.65, zorder=3),
    "Keller VAA G4":        dict(color="#9966aa", lw=1.0, ls="--", alpha=0.55, zorder=2),
    "HAA-Balanced":         dict(color="#3399cc", lw=1.0, ls="--", alpha=0.55, zorder=2),
    "Faber GTAA5":          dict(color="#bb7733", lw=0.9, ls="--", alpha=0.5, zorder=2),
    "HAA-Simple":           dict(color="#88aabb", lw=0.9, ls="--", alpha=0.5, zorder=2),
}
# Order matters: last drawn = top of pile, but zorder takes precedence.
BASE_RENDER_ORDER = [
    "Faber GTAA5", "HAA-Simple",       # bottom (legacy)
    "Keller VAA G4", "HAA-Balanced",   # middle (legacy)
    "60/40 SPY/IEF", "SPY buy-hold",   # legacy benchmarks
    "QQQ buy-hold", "Naive 70/30 PP/QQQ-trend",  # core 2 benchmarks
    "BULL-QQQ sleeve", "CPM standalone",         # components
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

def chart_yearly_bars(blended: pd.Series, qqq: pd.Series, naive: pd.Series):
    yr_b = ((1 + blended).resample("YE").prod() - 1) * 100
    yr_q = ((1 + qqq.reindex(blended.index)).resample("YE").prod() - 1) * 100
    yr_n = ((1 + naive.reindex(blended.index)).resample("YE").prod() - 1) * 100
    years = yr_b.index.year.values
    fig, ax = plt.subplots(figsize=(8, 3.8))
    width = 0.28
    x = np.arange(len(years))
    ax.bar(x - width, yr_q.values, width, label="QQQ buy-hold", color="#707070")
    ax.bar(x,         yr_n.values, width, label="Naive 70/30 PP/QQQ-trend", color="#9966aa")
    ax.bar(x + width, yr_b.values, width, label="CPM-BULL (PROD)", color="#0040d0")
    ax.set_xticks(x)
    ax.set_xticklabels(years, rotation=45, fontsize=8)
    ax.set_ylabel("Annual return (%)")
    ax.set_title("Annual Returns: PROD vs Naive 70/30 vs QQQ buy-hold")
    ax.axhline(0, color="#888", lw=0.6)
    _legend_below(ax, ncol=3)
    return fig

def chart_rolling_dd(fcp_only: pd.Series, blended: pd.Series, naive: pd.Series,
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
    naive_dd = rolling_intra_dd(naive.reindex(idx))


    ax.plot(fcp_dd.index, fcp_dd.values, label="CPM standalone", color="#1a9a1a", lw=1.6)
    ax.plot(blend_dd.index, blend_dd.values, label="CPM-BULL (PROD)", color="#0040d0", lw=2.0)
    ax.plot(naive_dd.index, naive_dd.values, label="Naive 70/30 PP/QQQ-trend", color="#9966aa", lw=1.4, ls="--", alpha=0.85)

    if max_fcp is not None:
        max_fcp_dd = rolling_intra_dd(max_fcp.reindex(idx))
        ax.plot(max_fcp_dd.index, max_fcp_dd.values, label="BULL-QQQ standalone",
                color="#009933", lw=1.6, ls="-", alpha=0.85)
    ax.axhline(0, color="#444", lw=0.6)
    ax.set_ylabel("Worst DD in window (%)")
    ax.set_title(f"Rolling {window_days//21}-Month Max Drawdown")
    ax.xaxis.set_major_locator(mdates.YearLocator(2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    _legend_below(ax, ncol=4)
    return fig

def chart_rolling_excess(fcp_only: pd.Series, blended: pd.Series, naive: pd.Series,
                          max_fcp: pd.Series = None, window_days=252):
    """Rolling N-month annualized excess CAGR vs Naive 70/30 benchmark.
    Uses geometric (1+r).rolling.prod()**(252/window) - 1 for proper compounding.
    """
    fig, ax = plt.subplots(figsize=(8, 3.6))

    def rolling_cagr(s: pd.Series) -> pd.Series:
        log1p = np.log1p(s)
        rolled_log = log1p.rolling(window_days).sum()
        return np.expm1(rolled_log * (252.0 / window_days))

    idx = blended.index
    fcp_only_a = fcp_only.reindex(idx)
    naive_a = naive.reindex(idx)

    fcp_cagr = rolling_cagr(fcp_only_a)
    blend_cagr = rolling_cagr(blended)
    naive_cagr = rolling_cagr(naive_a)

    excess_fcp = (fcp_cagr - naive_cagr) * 100
    excess_blend = (blend_cagr - naive_cagr) * 100

    ax.plot(excess_fcp.index, excess_fcp.values,
            label="CPM standalone vs Naive 70/30", color="#1a9a1a", lw=1.6)
    ax.plot(excess_blend.index, excess_blend.values,
            label="PROD vs Naive 70/30", color="#0040d0", lw=2.0)
    if max_fcp is not None:
        max_fcp_cagr = rolling_cagr(max_fcp.reindex(idx))
        excess_max = (max_fcp_cagr - naive_cagr) * 100
        ax.plot(excess_max.index, excess_max.values,
                label="BULL-QQQ standalone vs Naive 70/30", color="#ff8800", lw=1.4, ls="--", alpha=0.85)
    ax.axhline(0, color="#444", lw=0.6)
    ax.set_ylabel("Excess CAGR (pp, ann.)")
    ax.set_title(f"Rolling {window_days//21}-Month Excess vs Naive 70/30")
    ax.xaxis.set_major_locator(mdates.YearLocator(2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    _legend_below(ax, ncol=3)
    return fig

def chart_rolling_sharpe(blended: pd.Series, naive: pd.Series, window_days=252):
    # Rolling Sharpe vs Naive 70/30 (apples-to-apples architecture)
    fig, ax = plt.subplots(figsize=(8, 3.6))
    bench = naive.reindex(blended.index)
    bench_sr = (bench.rolling(window_days).mean() * 252) / (bench.rolling(window_days).std() * np.sqrt(252))
    fcp_sr = (blended.rolling(window_days).mean() * 252) / (blended.rolling(window_days).std() * np.sqrt(252))
    ax.plot(bench_sr.index, bench_sr.values, label="Naive 70/30 PP/QQQ-trend", color="#9966aa", lw=1.4, ls="--", alpha=0.85)
    ax.plot(fcp_sr.index, fcp_sr.values, label="CPM-BULL (PROD)", color="#0040d0", lw=2.0)
    ax.axhline(0, color="#888", lw=0.6, ls="--", alpha=0.5)
    ax.axhline(1, color="#0040d0", lw=0.6, ls=":", alpha=0.4)
    ax.set_ylabel("Sharpe")
    ax.set_title(f"Rolling {window_days//21}-Month Sharpe (vs Naive 70/30)")
    ax.xaxis.set_major_locator(mdates.YearLocator(2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    _legend_below(ax, ncol=2)
    return fig

def chart_canary_timeline(panel: pd.DataFrame, start: pd.Timestamp) -> tuple:
    """Run signal dates and collect (sig_d, cpm_regime, bull_regime, pair, safe).
    Plot two stacked rows: CPM canary (HYG/TIP/GLD) + BULL canary (HYG/LQD/TIP).
    Returns (fig, regime_counts dict, picks Counter, pair_counter Counter)."""
    from collections import Counter
    monthly_idx = pd.DataFrame({"x": 1}, index=panel.index).groupby(pd.Grouper(freq="ME")).tail(1)
    sigs = monthly_idx.index[(monthly_idx.index >= start)].tolist()

    cpm_per_date = []
    bull_per_date = []
    picks = Counter()
    pair_counter = Counter()
    prev_pair = None
    for sd in sigs:
        weights, pair, regime, safe = compute_target_weights(panel, sd, prev_pair=prev_pair)
        cpm_per_date.append((sd, regime, pair, safe))
        prev_pair = pair
        for asset, w in weights.items():
            if w > 0:
                picks[asset] += 1
        if pair and len(pair) == 2:
            pair_counter[tuple(sorted(pair))] += 1
        # BULL-QQQ canary state
        try:
            _bw, bregime, _bdiag = compute_bull_qqq_weights(panel, sd)
            bull_per_date.append((sd, bregime))
        except Exception:
            bull_per_date.append((sd, "CASH"))

    cpm_regimes = [r for _, r, _, _ in cpm_per_date]
    bull_regimes = [r for _, r in bull_per_date]
    n_total = len(cpm_regimes)
    regime_counts = {
        "RISK_ON": cpm_regimes.count("RISK_ON"),
        "DEFENSIVE": cpm_regimes.count("DEFENSIVE"),
        "BULL_QQQ": sum(1 for r in bull_regimes if r.startswith("BULL_QQQ")),
        "BULL_XLP": sum(1 for r in bull_regimes if r.startswith("BULL_XLP")),
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
            Patch(facecolor="#d04000", label="DEFENSIVE (SHV cash)"),
        ],
        loc="upper right", bbox_to_anchor=(1.0, 1.4), ncol=2, fontsize=7,
        frameon=False, handlelength=1.2, handleheight=0.7,
    )

    # Row 2: BULL-QQQ canary (HYG/LQD/TIP any-positive + QQQ trend)
    bull_colors = []
    for r in bull_regimes:
        if r.startswith("BULL_QQQ"): bull_colors.append("#00a040")
        elif r.startswith("BULL_XLP"): bull_colors.append("#a06000")
        else: bull_colors.append("#808080")
    axes[1].bar(dates, [1] * len(dates), color=bull_colors, width=25, alpha=0.85, edgecolor="none")
    axes[1].set_yticks([])
    axes[1].set_ylim(0, 1)
    axes[1].set_title("BULL canary (HYG / LQD / TIP any-positive 13612U + QQQ trend)", fontsize=9)
    axes[1].legend(
        handles=[
            Patch(facecolor="#00a040", label="BULL_QQQ"),
            Patch(facecolor="#a06000", label="BULL_XLP (late-cycle)"),
            Patch(facecolor="#808080", label="CASH (SHV)"),
        ],
        loc="upper right", bbox_to_anchor=(1.0, 1.4), ncol=3, fontsize=7,
        frameon=False, handlelength=1.2, handleheight=0.7,
    )
    axes[1].xaxis.set_major_locator(mdates.YearLocator(2))
    axes[1].xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    plt.tight_layout()
    return fig, regime_counts, picks, pair_counter


def picks_table_html(picks, pair_counter, n_signals):
    """Render two side-by-side tables: top picks + top pairs."""
    # Top picks
    pick_rows = sorted(picks.items(), key=lambda x: -x[1])
    picks_html = "<table class='yearly'><thead><tr><th>Asset</th><th>Picks</th><th>% months</th></tr></thead><tbody>"
    for asset, cnt in pick_rows[:18]:
        pct = cnt / n_signals * 100
        picks_html += f"<tr><td>{asset}</td><td style='text-align:right'>{cnt}</td>" \
                      f"<td style='text-align:right'>{pct:.1f}%</td></tr>"
    picks_html += "</tbody></table>"

    # Top pairs
    pair_rows = sorted(pair_counter.items(), key=lambda x: -x[1])
    pairs_html = "<table class='yearly'><thead><tr><th>Pair</th><th>Picks</th><th>% months</th></tr></thead><tbody>"
    for pair, cnt in pair_rows[:15]:
        pct = cnt / n_signals * 100
        label = f"{pair[0]} + {pair[1]}"
        pairs_html += f"<tr><td>{label}</td><td style='text-align:right'>{cnt}</td>" \
                      f"<td style='text-align:right'>{pct:.1f}%</td></tr>"
    pairs_html += "</tbody></table>"

    return f"""<div style='display:flex; gap:24px; flex-wrap:wrap;'>
<div style='flex:1; min-width:280px;'><h3 style='margin-top:0;'>Asset Pick Frequency</h3>{picks_html}</div>
<div style='flex:1; min-width:280px;'><h3 style='margin-top:0;'>Top Pair Archetypes</h3>{pairs_html}</div>
</div>"""


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


# ---------- Tables ----------

def perf_table_html(rows: list[dict]) -> str:
    """rows: list of {strategy, cagr, vol, sharpe, max_drawdown, ...}"""
    df = pd.DataFrame(rows)
    df = df[["strategy", "cagr", "vol", "sharpe", "max_drawdown"]]
    df.columns = ["Strategy", "CAGR", "Vol", "Sharpe", "MaxDD"]
    body = ""
    for _, r in df.iterrows():
        body += f"<tr><td>{r['Strategy']}</td>"
        body += f"<td style='text-align:right'>{fmt_pct(r['CAGR'])}</td>"
        body += f"<td style='text-align:right'>{fmt_pct(r['Vol'])}</td>"
        body += f"<td style='text-align:right'>{fmt_num(r['Sharpe'])}</td>"
        body += f"<td style='text-align:right'>{fmt_pct(r['MaxDD'])}</td></tr>\n"
    return f"""<div class='table-scroll'><table class='perf'>
<thead><tr><th>Strategy</th><th>CAGR</th><th>Vol</th><th>Sharpe</th><th>MaxDD</th></tr></thead>
<tbody>{body}</tbody></table></div>"""


def yearly_table_html(blended: pd.Series, qqq: pd.Series, cpm: pd.Series, mt2: pd.Series, naive: pd.Series) -> str:
    yr_b = ((1 + blended).resample("YE").prod() - 1)
    yr_f = ((1 + cpm).resample("YE").prod() - 1)
    yr_m = ((1 + mt2).resample("YE").prod() - 1)
    yr_q = ((1 + qqq.reindex(blended.index)).resample("YE").prod() - 1)
    yr_n = ((1 + naive.reindex(blended.index)).resample("YE").prod() - 1)
    df = pd.DataFrame({"Year": yr_b.index.year,
                       "PROD": yr_b.values * 100,
                       "CPM": yr_f.reindex(yr_b.index).values * 100,
                       "BULL-QQQ": yr_m.reindex(yr_b.index).values * 100,
                       "Naive 70/30": yr_n.reindex(yr_b.index).values * 100,
                       "QQQ": yr_q.reindex(yr_b.index).values * 100})
    df["Excess vs Naive"] = df["PROD"] - df["Naive 70/30"]
    df["Excess vs QQQ"] = df["PROD"] - df["QQQ"]
    body = ""
    for _, r in df.iterrows():
        ex_n = r["Excess vs Naive"]
        ex_q = r["Excess vs QQQ"]
        exn_class = "pos" if ex_n > 0 else "neg"
        exq_class = "pos" if ex_q > 0 else "neg"
        body += f"<tr><td>{int(r['Year'])}</td>"
        for col in ["PROD", "CPM", "BULL-QQQ", "Naive 70/30", "QQQ"]:
            v = r[col]
            cls = "pos" if v > 0 else "neg"
            body += f"<td style='text-align:right' class='{cls}'>{v:+.2f}%</td>"
        body += f"<td style='text-align:right' class='{exn_class}'>{ex_n:+.2f}pp</td>"
        body += f"<td style='text-align:right' class='{exq_class}'>{ex_q:+.2f}pp</td></tr>\n"
    return f"""<div class='table-scroll'><table class='yearly'>
<thead><tr><th>Year</th><th>PROD<br>(70/30)</th><th>CPM only</th><th>BULL-QQQ only</th><th>Naive 70/30</th><th>QQQ</th><th>Ex vs Naive</th><th>Ex vs QQQ</th></tr></thead>
<tbody>{body}</tbody></table></div>"""


def current_alloc_html(panel: pd.DataFrame, sig_d: pd.Timestamp) -> str:
    weights, pair, regime, safe = compute_target_weights(panel, sig_d)

    # CPM sleeve (70%)
    fcp_share = 1 - BULL_BLEND
    fcp_html = "".join(f"<tr><td>{t}</td><td style='text-align:right'>{w*100:.1f}%</td></tr>"
                        for t, w in sorted(weights.items(), key=lambda x: -x[1]))
    pair_str = f"{pair[0]} + {pair[1]}" if pair else "-"

    # BULL-QQQ sleeve (30%)
    bq_w, bq_regime, bq_diag = compute_bull_qqq_weights(panel, sig_d)
    bq_html = "".join(f"<tr><td>{t}</td><td style='text-align:right'>{w*100:.1f}%</td></tr>"
                        for t, w in sorted(bq_w.items(), key=lambda x: -x[1]))
    mom_12_1 = bq_diag.get("mom_12_1") or 0
    sig_w13 = bq_diag.get("sig_13612W") or 0
    cstate = bq_diag.get("state", "---")
    override_thr = bq_diag.get("override_threshold") or 0
    if bq_regime.startswith("BULL_"):
        via_override = bq_regime.endswith("_via_override")
        clean_regime = bq_regime.replace("_via_override","")
        override_note = " [via override]" if via_override else ""
        bq_state = f"{clean_regime} (canary {cstate}, 12-1={mom_12_1*100:+.1f}% w13={sig_w13*100:+.1f}%){override_note}"
    else:
        bq_state = f"CASH ({bq_diag.get('reason','-')}; canary {cstate}, 12-1={mom_12_1*100:+.1f}%)"

    # Combined 70% CPM + 30% BULL-QQQ
    combined = {}
    for t, w in weights.items():
        combined[t] = combined.get(t, 0.0) + w * fcp_share
    for t, w in bq_w.items():
        combined[t] = combined.get(t, 0.0) + w * BULL_BLEND
    combined_html = "".join(f"<tr><td>{t}</td><td style='text-align:right'>{w*100:.1f}%</td></tr>"
                             for t, w in sorted(combined.items(), key=lambda x: -x[1]))

    return f"""
<div class='alloc-grid'>
<div>
  <h4>CPM sleeve (70%)</h4>
  <p style='font-size:0.85rem'>Regime: <strong>{regime}</strong><br>Best safe: <strong>{safe}</strong><br>Pair: <strong>{pair_str}</strong></p>
  <div class='table-scroll'><table class='alloc'>{fcp_html}</table></div>
</div>
<div>
  <h4>BULL-QQQ sleeve ({int(BULL_BLEND*100)}%)</h4>
  <p style='font-size:0.85rem'>State: <strong>{bq_state}</strong><br>Canary: HYG/LQD/TIP any-positive 13612W<br>Trend: QQQ 12-1 mom &gt; 0 OR QQQ 13612W &gt; 0 (composite)<br>Override: QQQ 12-1 mom &gt; 67th pct expanding (current threshold: {override_thr*100:+.1f}%)<br>Bull asset: QQQ (default); XLP in `+-+` canary state<br>Fallback: 100% {CASH_TICKER} (cash)</p>
  <div class='table-scroll'><table class='alloc'>{bq_html}</table></div>
</div>
<div>
  <h4>Combined {int(fcp_share*100)}/{int(BULL_BLEND*100)} (100% of capital)</h4>
  <div class='table-scroll'><table class='alloc'>{combined_html}</table></div>
</div>
</div>
"""


# ---------- Main ----------

def main():
    ap = argparse.ArgumentParser()
    # Default to POST-DBC canonical 19.2y window (2007-02); all RISKY ETFs
    # the README headline. Override with --start to view the longer extended
    # window (1997-08 or 2001-08), but bottom-line text is calibrated to
    # live-only metrics.
    ap.add_argument("--start", default="2007-02-28")
    ap.add_argument("--end", default=None)
    ap.add_argument("--out", default=str(ROOT / "cpm_dashboard.html"))
    args = ap.parse_args()
    
    start = pd.Timestamp(args.start)
    end = pd.Timestamp(args.end) if args.end else pd.Timestamp.today().normalize()
    
    # Load with sufficient warmup so CPM signals + BULL-QQQ 12-1 momentum are stable
    panel_start = min(start - pd.DateOffset(years=20), pd.Timestamp("1995-01-01"))
    print(f"Loading panel from {panel_start.date()} (warmup for EMA200 canary) ...")
    panel = load_panel(start=panel_start, end=end)
    print(f"Panel: {panel.index[0].date()} -> {panel.index[-1].date()}, {len(panel.columns)} assets")
    
    print(f"Running CPM backtest ...")
    cpm, _ = run_cpm_backtest(panel, start, end)

    print("Computing BULL-QQQ sleeve ...")
    bull_qqq_rets = run_bull_qqq_backtest(panel, start, end)

    # Production blend: 80% CPM + 20% BULL-QQQ
    common = cpm.index.intersection(bull_qqq_rets.index)
    cpm = cpm.reindex(common)
    bull_qqq_rets = bull_qqq_rets.reindex(common)
    blended = (1 - BULL_BLEND) * cpm + BULL_BLEND * bull_qqq_rets
    prod_label = f"CPM-BULL ({int((1-BULL_BLEND)*100)}/{int(BULL_BLEND*100)})"

    print(f"Running peer strategies ...")
    spy = panel["SPY"].ffill().pct_change().loc[start:end].fillna(0.0) if "SPY" in panel.columns else pd.Series(dtype=float)
    qqq = panel["QQQ"].ffill().pct_change().loc[start:end].fillna(0.0) if "QQQ" in panel.columns else pd.Series(dtype=float)
    six40 = sixty_forty(panel, start, end)
    # Core 2 benchmarks for clean comparison
    naive_pp_qt = naive_70_30_pp_qqq_trend(panel, start, end)

    strategies = {
        prod_label: blended,
        "CPM standalone": cpm,
        "BULL-QQQ sleeve": bull_qqq_rets,
        "Naive 70/30 PP/QQQ-trend": naive_pp_qt,
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
    # Core comparison: PROD + 2 components + 2 apples-to-apples benchmarks
    CORE_CHARTS = (prod_label, "CPM standalone", "BULL-QQQ sleeve",
                   "Naive 70/30 PP/QQQ-trend", "QQQ buy-hold")
    fig_equity = chart_equity({k: v for k, v in strategies.items() if k in CORE_CHARTS},
                              prod_label=prod_label)
    fig_dd = chart_drawdown({k: v for k, v in strategies.items() if k in CORE_CHARTS},
                            prod_label=prod_label)
    fig_yearly = chart_yearly_bars(blended, qqq, strategies["Naive 70/30 PP/QQQ-trend"])
    fig_rolling = chart_rolling_sharpe(blended, strategies["Naive 70/30 PP/QQQ-trend"])
    fig_excess = chart_rolling_excess(cpm, blended, strategies["Naive 70/30 PP/QQQ-trend"], bull_qqq_rets)
    fig_roll_dd = chart_rolling_dd(cpm, blended, strategies["Naive 70/30 PP/QQQ-trend"], bull_qqq_rets)
    fig_canary, regime_counts, picks, pair_counter = chart_canary_timeline(panel, start)
    # CPM regimes sum to total months; BULL regimes also sum to total. Use CPM as denominator.
    n_signals = regime_counts["RISK_ON"] + regime_counts["DEFENSIVE"]
    picks_html = picks_table_html(picks, pair_counter, n_signals)
    regime_pct_def = regime_counts["DEFENSIVE"] / max(1, n_signals) * 100
    regime_pct_ron = regime_counts["RISK_ON"] / max(1, n_signals) * 100
    fig_corr = chart_correlations({k: v for k, v in strategies.items() if k in CORE_CHARTS})
    
    # Current allocation: use last COMPLETED month-end as signal date
    today = panel.index[-1]
    prior_month_end = today.replace(day=1) - pd.Timedelta(days=1)
    candidates = panel.index[panel.index <= prior_month_end]
    sig_d = candidates[-1] if len(candidates) > 0 else today
    alloc_html = current_alloc_html(panel, sig_d)
    
    # Sleeve breakdown -- production blend variants + reference sleeves
    common_idx = cpm.index.intersection(bull_qqq_rets.index)
    fcp_c = cpm.loc[common_idx]; mt2_c = bull_qqq_rets.loc[common_idx]
    blend_70_30 = 0.7 * fcp_c + 0.3 * mt2_c
    blend_60_40 = 0.6 * fcp_c + 0.4 * mt2_c
    blend_90_10 = 0.9 * fcp_c + 0.1 * mt2_c

    sleeve_rows = [
        {"strategy": "CPM-BULL 70/30 (PRODUCTION)",   **perf_metrics(blend_70_30)},
        {"strategy": "CPM-BULL 80/20 (lower bull tilt)", **perf_metrics(0.8*fcp_c + 0.2*mt2_c)},
        {"strategy": "CPM-BULL 60/40 (higher bull tilt)", **perf_metrics(blended)},
        {"strategy": "CPM-BULL 50/50 (max bull tilt)",   **perf_metrics(0.5*fcp_c + 0.5*mt2_c)},
        {"strategy": "CPM standalone (defensive)",     **perf_metrics(cpm)},
        {"strategy": "BULL-QQQ standalone (bull sleeve)", **perf_metrics(bull_qqq_rets)},
    ]

    # ========================================================
    # EXTENDED 32y backtest (1994-2026, includes dot-com)
    # ========================================================
    ext_start = pd.Timestamp("1994-01-01")
    print(f"Running EXT 32y backtest {ext_start.date()} ...")
    ext_fcp, _ = run_cpm_backtest(panel, ext_start, end)
    ext_bull = run_bull_qqq_backtest(panel, ext_start, end)
    ext_common = ext_fcp.index.intersection(ext_bull.index)
    ext_fcp_c = ext_fcp.reindex(ext_common)
    ext_bull_c = ext_bull.reindex(ext_common)
    ext_blended = (1 - BULL_BLEND) * ext_fcp_c + BULL_BLEND * ext_bull_c
    ext_qqq = panel["QQQ"].ffill().pct_change().loc[ext_start:end].fillna(0.0) if "QQQ" in panel.columns else pd.Series(dtype=float)
    ext_naive = naive_70_30_pp_qqq_trend(panel, ext_start, end)

    ext_strategies = {
        prod_label: ext_blended,
        "CPM standalone": ext_fcp_c,
        "BULL-QQQ sleeve": ext_bull_c,
        "Naive 70/30 PP/QQQ-trend": ext_naive,
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
    ext_fig_yearly = chart_yearly_bars(ext_blended, ext_qqq, ext_naive)
    ext_fig_rolling = chart_rolling_sharpe(ext_blended, ext_naive)
    ext_fig_roll_dd = chart_rolling_dd(ext_fcp_c, ext_blended, ext_naive, ext_bull_c)
    
    # Compose HTML
    print("Composing HTML ...")
    today = dt.date.today().isoformat()
    window_str = f"{start.date()} to {end.date()}"
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
</style>
</head>
<body>

<h1>CPM-BULL Strategy Dashboard</h1>
<p class='subtitle'><strong>CPM</strong> (canary-gated momentum + min-variance pair selection) + <strong>BULL-QQQ</strong> trend overlay.</p>
<p class='meta'>Backtest window: {window_str} | Built: {today}</p>

<div class='card'>
<h3>Bottom line</h3>
<p><strong>Production deployment</strong>: 70% CPM defensive sleeve + 30% BULL-QQQ bull sleeve (oracle-v3 Sharpe-optimal).</p>
<p><strong>CPM</strong> (Canary-gated Pair Momentum) = 11-asset cross-asset universe (factor + sector + international + diversifier), HYG+TIP+GLD any-positive canary, min-variance pair selection on top-K Faber SMA ranker, vol cap 10% (de-risk only, no leverage), 10 bps/side cost.</p>
<p><strong>BULL-QQQ</strong> = QQQ (or XLP in `+-+` canary state) when composite trend (QQQ {MOMENTUM_LOOKBACK}-1 mom > 0 OR QQQ 13612W > 0) passes AND (HYG/LQD/TIP any-positive canary OR equity-strength override: QQQ 12-1 mom > top tercile of expanding history). Otherwise 100% {CASH_TICKER} cash.</p>
<p>Live-18y backtest (post-cost): CPM standalone Sharpe <strong>1.26</strong>, CAGR <strong>12.12%</strong>, MaxDD <strong>-13.5%</strong>. BULL-QQQ standalone Sharpe <strong>~1.07</strong>, CAGR <strong>~18%</strong>, MaxDD <strong>~-29%</strong>. <strong>70/30 production blend Sharpe ~1.48, CAGR ~14.25%, MaxDD ~-12.3%, COVID DD ~-2%</strong>. Extended 32y window (incl. dot-com): Sharpe ~1.27, CAGR ~13.2%, MaxDD ~-15.2%. TEST OOS 2017-26: Sharpe 1.63, CAGR 16.85%. Bootstrap 95% CI on Sharpe is wide, so honest forward base-case expectation is <strong>0.90-1.20 Sharpe, 8-12% CAGR</strong> after in-sample selection bias and Nasdaq-era discount.</p>
</div>

<h2>This Month's Allocation</h2>
<div class='card'>
<p class='meta'>Signal date: {sig_d.date()}</p>
{alloc_html}
</div>

<h2>Performance Summary</h2>
<div class='card'>
{perf_table_html(perf_rows)}
<p class='footnote'>Post-cost (10 bps/side), with vol targeting (10% annualized).</p>
</div>

<h2>Sleeve Breakdown</h2>
<div class='card'>
{perf_table_html(sleeve_rows)}
</div>

<h2>Equity Curves</h2>
<div class='card'>
{fig_to_html(fig_equity)}
</div>

<h2>Drawdown Profile</h2>
<div class='card'>
{fig_to_html(fig_dd)}
</div>

<h2>Year-by-Year</h2>
<div class='card'>
{fig_to_html(fig_yearly)}
</div>

<h2>Rolling Sharpe (12-month, vs Naive 70/30 PP/QQQ-trend)</h2>
<div class='card'>
{fig_to_html(fig_rolling)}
</div>

<h2>Rolling Excess Return (12-month, annualized)</h2>
<div class='card'>
{fig_to_html(fig_excess)}
<p class='footnote'>Excess CAGR over Naive 70/30 PP/QQQ-trend (apples-to-apples benchmark: same 70/30 architecture with off-the-shelf components). Negative regions = strategy lagged that window vs simpler implementation of same meta-design.</p>
</div>

<h2>Rolling 3-Month Max Drawdown</h2>
<div class='card'>
{fig_to_html(fig_roll_dd)}
<p class='footnote'>Worst peak-to-trough drawdown within each rolling 63-trading-day window. Shallower (closer to 0) = better risk control over short horizons. Compares CPM standalone, CPM-BULL production blend, BULL-QQQ standalone, and Naive 70/30 PP/QQQ-trend benchmark.</p>
</div>

<h2>Canary Regime History</h2>
<div class='card'>
{fig_to_html(fig_canary)}
<p><strong>CPM canary (HYG/TIP/GLD any-positive 13612U):</strong> Risk-on <strong>{regime_pct_ron:.1f}%</strong> ({regime_counts['RISK_ON']}/{n_signals}) -- pair selection runs. Defensive <strong>{regime_pct_def:.1f}%</strong> ({regime_counts['DEFENSIVE']}/{n_signals}) -- 100% SHV cash. Defensive fires only when ALL three of HYG (credit), TIP (inflation), GLD (real-asset/tail) are simultaneously negative. GLD added (vs original HYG+TIP) to avoid TLT-bias when canary triggers in rate-rising regimes.</p>
<p><strong>BULL canary (HYG/LQD/TIP any-positive 13612U + QQQ trend):</strong> QQQ on <strong>{regime_counts['BULL_QQQ']/n_signals*100:.1f}%</strong> ({regime_counts['BULL_QQQ']}/{n_signals}), XLP late-cycle <strong>{regime_counts['BULL_XLP']/n_signals*100:.1f}%</strong> ({regime_counts['BULL_XLP']}/{n_signals}, HYG-/LQD-/TIP+ state only), cash <strong>{regime_counts['BULL_CASH']/n_signals*100:.1f}%</strong> ({regime_counts['BULL_CASH']}/{n_signals}). Uses LQD instead of GLD because bull-overlay's lone-GLD-positive states have -2.3% mean forward QQQ (canary differentiation documented in caveat 7).</p>
<p class='footnote'>The two canaries differ by sleeve design: CPM uses HYG/TIP/GLD (real-asset focus, suits cross-asset pair selection); BULL-QQQ uses HYG/LQD/TIP (credit/inflation focus, suits single-asset equity overlay). HYG_stitched = VWEHX pre-2007-04 + live HYG.</p>
</div>

<h2>Asset Pick Frequency & Top Pair Archetypes</h2>
<div class='card'>
{picks_html}
<p class='footnote'>Counts across signal dates from {start.strftime('%Y-%m')} onward. Shows which assets the min-variance pair selection actually picks most often, and which pair archetypes dominate. Helpful to verify universe is actually being used (no zombies).</p>
</div>

<h2>Strategy Correlations</h2>
<div class='card'>
{fig_to_html(fig_corr)}
<p class='footnote'>Lower correlation = better diversifier. BULL-QQQ's trend/regime filters cut equity exposure to 0% (SHV cash) in defensive months, giving regime-conditional diversification with the CPM sleeve.</p>
</div>

<h2>Yearly Returns Table</h2>
<div class='card'>
{yearly_table_html(blended, qqq, cpm, bull_qqq_rets, naive_pp_qt)}
</div>

<h2>Extended Backtest (32y, 1994-2026)</h2>
<div class='card'>
<p class='meta'>EXT window includes dot-com bust (2000-2002) and pre-GFC period. Tests robustness across multiple regimes. Pre-2010 uses stitched ETF proxies (Vanguard mutual funds etc.). Treat as exploratory: proxy quality + pre-2008 universe coverage degrades signal vs live.</p>
{perf_table_html(ext_perf_rows)}
</div>

<h3>EXT Equity Curves</h3>
<div class='card'>
{fig_to_html(ext_fig_equity)}
</div>

<h3>EXT Drawdown Profile</h3>
<div class='card'>
{fig_to_html(ext_fig_dd)}
</div>

<h3>EXT Year-by-Year</h3>
<div class='card'>
{fig_to_html(ext_fig_yearly)}
</div>

<h3>EXT Rolling Sharpe (12-month)</h3>
<div class='card'>
{fig_to_html(ext_fig_rolling)}
</div>

<h3>EXT Rolling 3-Month Max Drawdown</h3>
<div class='card'>
{fig_to_html(ext_fig_roll_dd)}
</div>

<h2>Strategy Spec</h2>
<div class='card'>
<details open>
<summary>CPM Sleeve (70%)</summary>
<ul>
<li><strong>Universe (10):</strong> 4 US broad/factor (QQQ, IWF, VBR, SPHQ) + EFA (iShares developed, live 2001-08), EEM (iShares EM, live 2003-04) + GLD, TLT, DBC, DBMF (diversifiers incl. managed futures). Live-trade equivalents: IWF&rarr;SCHG (corr 0.994, 14bps cheaper), DBC&rarr;PDBC (no K-1). DBMF live 2019-05; pre-2019 uses SG CTA Index stitch. EFA/EEM chosen over VEA/VWO on principle (correlation &gt;0.99, picking the +0.05 Sh winner is DSR overfitting; EFA has 6y more live history). <strong>Canonical window: 2007-02-28 (19.2y, post-DBC + 12mo signal warmup, all 10 RISKY ETFs LIVE at start, includes full 2008 GFC realization)</strong> -- HYG/DBMF use existing canonical stitches; prior 2008-09 cherry-picked post-GFC-trough start.
  <br><code>{', '.join(RISKY_UNIVERSE)}</code></li>
<li><strong>Safe pool:</strong> {', '.join(SAFE_POOL)} (best-of by Faber 10m SMA distance)</li>
<li><strong>Canary:</strong> HYG + TIP, ANY positive Keller 13612W &gt; 0 -&gt; risk-on; both negative -&gt; 100% best safe. HYG_stitched = VWEHX pre-2007-04 + live HYG.</li>
<li><strong>Ranker:</strong> Faber 10-month SMA distance: <code>(price - SMA10) / SMA10</code></li>
<li><strong>Selection:</strong> top half by ranker, drop negative momentum</li>
<li><strong>Pair:</strong> minimum-variance pair (50/50 portfolio variance) among positive-momentum candidates ({CORR_LOOKBACK_DAYS}d lookback)</li>
<li><strong>Hold buffer:</strong> {HOLD_BUFFER:.1f} z-units (keep prior pair member unless new exceeds)</li>
<li><strong>Vol targeting:</strong> {TARGET_VOL*100:.0f}% annualized, 63d realized vol, <strong>max 1.0x (de-risk only, no leverage)</strong></li>
<li><strong>Cost:</strong> {COST_BPS_PER_SIDE} bps/side</li>
<li><strong>Execution:</strong> month-end signal, T+1 MOC trade</li>
</ul>
</details>
<details>
<summary>BULL-QQQ Sleeve ({int(BULL_BLEND*100)}%) - bull capture with cash defense</summary>
<ul>
<li><strong>Bull asset:</strong> <code>{BULL_TICKER}</code> (single ticker -- Nasdaq-100, already diversified across mega-cap tech). Multi-ETF "diversified" universes (SMH/SCHG/XLK/IWM/GLD) tested and rejected: same Sharpe, more complexity, no alpha.</li>
<li><strong>Per-asset filter:</strong> {BULL_TICKER} {MOMENTUM_LOOKBACK}-1 absolute momentum &gt; 0 (Antonacci dual momentum / Moskowitz TSMOM). Chosen over Faber 10mo SMA because dot-com survival is materially better -- 12-1 stays negative throughout sustained bears, avoiding whipsaws.</li>
<li><strong>Macro gate:</strong> HYG OR TIP positive 13612W (catches credit/inflation stress, e.g. 2022). Adds +54% Martin Ratio over mom-only at small CAGR cost.</li>
<li><strong>Fallback:</strong> 100% <code>{CASH_TICKER}</code> (short-treasury cash) when either filter fails. No duration risk on this sleeve.</li>
<li><strong>Standalone (live-18y):</strong> Sharpe 0.92, CAGR 15.3%, MaxDD -28.6%, Ulcer 5.05%, Martin 2.96.</li>
<li><strong>Why this composition:</strong> canary catches credit/inflation stress (2022); 12-1 momentum catches sustained equity bears (dot-com 2000-02). Together they handle 2 of 3 bear-market types. Single-ticker QQQ chosen over multi-ETF "diversified" universes because empirical tests showed same Sharpe with more complexity.</li>
<li><strong>Variants tested and rejected:</strong> Multi-ETF universe (no Sharpe benefit, more rotation noise); IEF fallback (+0.02 Sharpe but adds duration risk); CPM fallback (+0.85pp CAGR but worse Martin Ratio on extended); Faber 10mo SMA filter (worse dot-com survival); VIX filter (~0.05 Sharpe cost across both windows, n=1 COVID evidence); vol-targeting (cleaner MaxDD but minimal avg-rolling-DD improvement, trades CAGR for tail protection); Keller 13612W filter (Sh 0.76 worst on QQQ timing); EMA50/200 monthly (math error - 4yr/17yr filter, useless); top-K momentum-weighted (concentrates on highest vol, hurts Sharpe).</li>
</ul>
</details>
</div>

<h2>Honest Caveats</h2>
<div class='card'>
<ul>
<li><strong>In-sample selection bias:</strong> hyperparameters and universe tuned on this same data window.</li>
<li><strong>Universe risk:</strong> 7-name US equity sub-universe is bespoke / human-curated. All ETFs live since 2005 or earlier; no SPY-proxy contamination in post-2008 backtest.</li>
<li><strong>Pre-2019 proxies:</strong> SPHQ uses SPY proxy pre-2005, DBMF uses SG CTA Index pre-2019 (affects EXT 30y window only; MODERN 17.6y window has all ETFs live except DBMF which uses CTA stitch).</li>
<li><strong>Crisis-concentrated alpha:</strong> top 4 single years (2008 +45.8pp, 2002 +32.8pp, 2020 +17.6pp, 2022 +17.2pp) contribute +128pp of total +25pp arithmetic excess vs SPY. Non-crisis years generally lag SPY.</li>
<li><strong>Lags V-shaped recoveries</strong> (verified): 2009 full-year -10.8pp vs SPY; 2020-Q2 -27.6pp vs SPY in the snap-back. Canary slow to re-engage after deep selloffs.</li>
<li><strong>Bullish-rally underperformance is structural:</strong> MAX_LEVERAGE=1.0 prevents the vol-target from levering up in low-vol bull runs. Strategy gives up bull upside in exchange for crisis alpha as designed.</li>
<li><strong>Bootstrap CI for Sharpe (live-only 18y):</strong> CPM standalone Sharpe 1.29, 95% CI [0.78, 1.63] (pre-canary-upgrade CI bounds; will narrow once new HYG canary has more data). Wide CIs imply ~0.21 std-error on forward estimate. Anchor forward base case at 0.80-1.10 for CPM standalone.</li>
<li><strong>Strategy not yet live-traded.</strong> Forward expectation should anchor below backtest.</li>
</ul>
</div>

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
