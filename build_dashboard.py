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

import cpm_live as cpm_module
from cpm_live import (
    RISKY_UNIVERSE, SAFE_POOL,
    CANARY_ASSETS, DEFAULT_CASH,
    TARGET_VOL, HOLD_BUFFER, CORR_LOOKBACK_DAYS, COST_BPS_PER_SIDE,
    TOP_K_CANDIDATES,
    load_panel, run_cpm_backtest,
    perf_metrics, compute_target_weights, sig_13612U,
)
from bull_qqq_live import (
    run_bull_qqq_backtest, compute_bull_qqq_weights,
    BULL_TICKER, CASH_TICKER,
)

# Production blend: 60% CPM + 20% BULL-QQQ + 20% NDX
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
            if len(future) < 1: continue
            next_sd = sig_dates[sig_dates > sd]
            if len(next_sd) > 0 and len(common[common > next_sd[0]]) > 0:
                end_apply = common[common > next_sd[0]][0]
            else:
                end_apply = common[-1]
            # T+1 OPEN execution (next-day MOO)
            mask = (common >= future[0]) & (common < end_apply)
            asset_per_day.loc[mask] = "QQQ"
    trend_rets = pd.Series(0.0, index=common)
    trend_rets[asset_per_day == "QQQ"] = daily_qqq.reindex(common).fillna(0)[asset_per_day == "QQQ"]
    trend_rets[asset_per_day == "SHV"] = daily_shv.reindex(common).fillna(0)[asset_per_day == "SHV"]
    import numpy as _np
    flips = (asset_per_day.values[1:] != asset_per_day.values[:-1])
    for i in _np.where(flips)[0]:
        trend_rets.iloc[i+1] -= 2.0 * cost_bps / 10000.0
    return trend_rets


def naive_60_40_pp_qqq_trend(panel, start, end):
    """Naive 60/40: 60% Permanent Portfolio + 40% QQQ trend-follow.
    Apples-to-apples benchmark for CPM-BULL-NDX PROD (60/20/20 = 60% defensive
    + 40% growth-leveraged)."""
    from cpm_live import run_pp_backtest
    pp = run_pp_backtest(panel, start, end)
    qt = qqq_trend_follow(panel, start, end)
    common = pp.index.intersection(qt.index)
    if len(common) == 0:
        return pd.Series(dtype=float)
    return (0.6 * pp.reindex(common).fillna(0) + 0.4 * qt.reindex(common).fillna(0))


def cpm_signal_records(panel: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp | None = None) -> list[dict]:
    """Production-equivalent monthly CPM signal path for dashboard diagnostics.

    Mirrors run_cpm_backtest breadth-majority hold-buffer reset so charts/tables
    do not drift from the live strategy path.
    """
    cols = sorted(set(RISKY_UNIVERSE + SAFE_POOL + CANARY_ASSETS + [DEFAULT_CASH]) & set(panel.columns))
    close = panel[cols]
    monthly_idx = pd.DataFrame({"x": 1}, index=close.index).groupby(pd.Grouper(freq="ME")).tail(1)
    mask = monthly_idx.index >= start
    if end is not None:
        mask &= monthly_idx.index <= end
    sig_dates = monthly_idx.index[mask].tolist()

    records = []
    prev_pair = None
    prev_risk_state = None
    for sig_d in sig_dates:
        monthly = close.loc[:sig_d].resample("ME").last()
        n_pos = cpm_module.canary_positive_count(monthly, CANARY_ASSETS)
        risk_state = cpm_module.canary_risk_state(n_pos)
        if (
            prev_pair is not None
            and risk_state is not None
            and prev_risk_state is not None
            and risk_state != prev_risk_state
        ):
            prev_pair = None

        weights, new_pair, regime, safe = compute_target_weights(close, sig_d, prev_pair=prev_pair)
        records.append({
            "sig_d": sig_d,
            "weights": weights,
            "pair": new_pair,
            "regime": regime,
            "safe": safe,
            "canary_positive_count": n_pos,
            "risk_state": risk_state,
        })
        prev_pair = new_pair
        prev_risk_state = risk_state
    return records


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
    "NDX sleeve":           dict(color="#cc2266", lw=1.6, ls="-",  alpha=0.85, zorder=7),
    # Tier 3: 2 benchmarks (apples-to-apples + raw target)
    "Naive 60/40 PP/QQQ-trend": dict(color="#9966aa", lw=1.6, ls="--", alpha=0.85, zorder=4),
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
    "NDX sleeve",
    "QQQ buy-hold", "Naive 60/40 PP/QQQ-trend",  # core 2 benchmarks
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
    ax.bar(x,         yr_n.values, width, label="Naive 60/40 PP/QQQ-trend", color="#9966aa")
    ax.bar(x + width, yr_b.values, width, label="CPM-BULL-NDX (PROD)", color="#0040d0")
    ax.set_xticks(x)
    ax.set_xticklabels(years, rotation=45, fontsize=8)
    ax.set_ylabel("Annual return (%)")
    ax.set_title("Annual Returns: PROD vs Naive 60/40 vs QQQ buy-hold")
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
    ax.plot(blend_dd.index, blend_dd.values, label="CPM-BULL-NDX (PROD)", color="#0040d0", lw=2.0)
    ax.plot(naive_dd.index, naive_dd.values, label="Naive 60/40 PP/QQQ-trend", color="#9966aa", lw=1.4, ls="--", alpha=0.85)

    if max_fcp is not None:
        max_fcp_dd = rolling_intra_dd(max_fcp.reindex(idx))
        ax.plot(max_fcp_dd.index, max_fcp_dd.values, label="BULL-QQQ standalone",
                color="#ff8800", lw=1.6, ls="-", alpha=0.85)
    ax.axhline(0, color="#444", lw=0.6)
    ax.set_ylabel("Worst DD in window (%)")
    ax.set_title(f"Rolling {window_days//21}-Month Max Drawdown")
    ax.xaxis.set_major_locator(mdates.YearLocator(2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    _legend_below(ax, ncol=4)
    return fig

def chart_rolling_excess(fcp_only: pd.Series, blended: pd.Series, naive: pd.Series,
                          max_fcp: pd.Series = None, window_days=252):
    """Rolling N-month annualized excess CAGR vs Naive 60/40 benchmark.
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
            label="CPM standalone vs Naive 60/40", color="#1a9a1a", lw=1.6)
    ax.plot(excess_blend.index, excess_blend.values,
            label="PROD vs Naive 60/40", color="#0040d0", lw=2.0)
    if max_fcp is not None:
        max_fcp_cagr = rolling_cagr(max_fcp.reindex(idx))
        excess_max = (max_fcp_cagr - naive_cagr) * 100
        ax.plot(excess_max.index, excess_max.values,
                label="BULL-QQQ standalone vs Naive 60/40", color="#ff8800", lw=1.4, ls="--", alpha=0.85)
    ax.axhline(0, color="#444", lw=0.6)
    ax.set_ylabel("Excess CAGR (pp, ann.)")
    ax.set_title(f"Rolling {window_days//21}-Month Excess vs Naive 60/40")
    ax.xaxis.set_major_locator(mdates.YearLocator(2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    _legend_below(ax, ncol=3)
    return fig

def chart_rolling_sharpe(blended: pd.Series, naive: pd.Series, window_days=252):
    # Rolling Sharpe vs Naive 60/40 (apples-to-apples architecture)
    fig, ax = plt.subplots(figsize=(8, 3.6))
    bench = naive.reindex(blended.index)
    bench_sr = (bench.rolling(window_days).mean() * 252) / (bench.rolling(window_days).std() * np.sqrt(252))
    fcp_sr = (blended.rolling(window_days).mean() * 252) / (blended.rolling(window_days).std() * np.sqrt(252))
    ax.plot(bench_sr.index, bench_sr.values, label="Naive 60/40 PP/QQQ-trend", color="#9966aa", lw=1.4, ls="--", alpha=0.85)
    ax.plot(fcp_sr.index, fcp_sr.values, label="CPM-BULL-NDX (PROD)", color="#0040d0", lw=2.0)
    ax.axhline(0, color="#888", lw=0.6, ls="--", alpha=0.5)
    ax.axhline(1, color="#0040d0", lw=0.6, ls=":", alpha=0.4)
    ax.set_ylabel("Sharpe")
    ax.set_title(f"Rolling {window_days//21}-Month Sharpe (vs Naive 60/40)")
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
        BULL 2-asset canary + macro: 4x4 grid (rows=HYG/TIP, cols=curve/vol)."""
        state_ser = compute_states(canary_assets, include_macro=include_macro)
        state_per_day = attribute(daily_returns, state_ser)
        n_assets = len(canary_assets)
        if not include_macro and n_assets == 3:
            # CPM: rows = HYG (first canary), cols = TIP x GLD
            row_order = [(True,), (False,)]
            col_order = [(True, True), (True, False), (False, True), (False, False)]
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
    bull_grid = build_grid(bull_rets, bull_canary, include_macro=True)

    cpm_col_labels = [f"TIP{a}\nGLD{b}" for a, b in [('+','+'),('+','-'),('-','+'),('-','-')]]
    cpm_row_labels = ['HYG+', 'HYG-']
    bull_col_labels = [f"curve{a}\nvol{b}" for a, b in [('+','+'),('+','-'),('-','+'),('-','-')]]
    bull_row_labels = [f"HYG{a}\nTIP{b}" for a, b in [('+','+'),('+','-'),('-','+'),('-','-')]]

    fig, axes = plt.subplots(2, 1, figsize=(11, 11), constrained_layout=True,
                              gridspec_kw={'height_ratios':[1, 2]})
    im = plot_sub(axes[0], cpm_grid, cpm_row_labels, cpm_col_labels,
                   'CPM sleeve - performance by canary state', fontsize=9)
    plot_sub(axes[1], bull_grid, bull_row_labels, bull_col_labels,
              'BULL-QQQ sleeve - performance by canary AND macro composite state', fontsize=8)
    fig.colorbar(im, ax=axes, shrink=0.7, label='Sharpe', orientation='vertical', pad=0.02)
    return fig


def chart_canary_timeline(panel: pd.DataFrame, start: pd.Timestamp) -> tuple:
    """Run signal dates and collect (sig_d, cpm_regime, bull_regime, pair, safe).
    Plot two stacked rows: CPM canary (HYG/TIP/GLD) + BULL canary (HYG/TIP).
    Returns (fig, regime_counts dict, picks Counter, pair_counter Counter)."""
    from collections import Counter
    records = cpm_signal_records(panel, start)

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

    # Row 2: BULL-QQQ canary (HYG/TIP any-positive + curve/vol OR + asset mom)
    bull_colors = []
    for r in bull_regimes:
        if r.startswith("BULL_QQQ"): bull_colors.append("#00a040")
        else: bull_colors.append("#808080")
    axes[1].bar(dates, [1] * len(dates), color=bull_colors, width=25, alpha=0.85, edgecolor="none")
    axes[1].set_yticks([])
    axes[1].set_ylim(0, 1)
    axes[1].set_title("BULL canary (HYG/TIP any-positive 13612U)", fontsize=9)
    axes[1].legend(
        handles=[
            Patch(facecolor="#00a040", label="BULL_QQQ"),
            Patch(facecolor="#808080", label="CASH (SHV)"),
        ],
        loc="upper right", bbox_to_anchor=(1.0, 1.4), ncol=2, fontsize=7,
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


def chart_asset_when_picked(panel: pd.DataFrame, start: pd.Timestamp):
    """Per-asset conditional performance when held in a CPM pair.

    Bars: Sharpe, AnnRet, CumRet per asset. Sorted by Sharpe.
    """
    from collections import defaultdict
    end = panel.index[-1]
    records = cpm_signal_records(panel, start)
    sig_dates = [r["sig_d"] for r in records]

    asset_returns = defaultdict(list)
    asset_picks = defaultdict(int)
    for i, rec in enumerate(records):
        sig_d = rec["sig_d"]
        weights = rec["weights"]
        sidx = panel.index.searchsorted(sig_d) + 2
        eidx = panel.index.searchsorted(sig_dates[i+1]) + 2 if i+1 < len(sig_dates) else len(panel.index)
        if sidx >= len(panel.index):
            continue
        window = panel.index[sidx:eidx]
        for asset in weights.keys():
            asset_picks[asset] += 1
            if asset not in panel.columns:
                continue
            rs = []
            for d in window:
                dpos = panel.index.searchsorted(d)
                if dpos == 0:
                    continue
                p0 = panel[asset].iloc[dpos - 1]
                p1 = panel[asset].loc[d]
                if pd.notna(p0) and pd.notna(p1) and p0 > 0:
                    rs.append((d, p1/p0 - 1))
            if rs:
                asset_returns[asset].append(pd.Series([r for _, r in rs], index=[d for d, _ in rs]))

    rows = []
    for a, sers in asset_returns.items():
        full = pd.concat(sers).sort_index().dropna()
        if len(full) < 3:
            continue
        eq = (1 + full).cumprod()
        vol = full.std(ddof=0) * np.sqrt(252)
        ann_ret = full.mean() * 252
        sh = ann_ret / vol if vol > 0 else float('nan')
        cum = eq.iloc[-1] - 1
        rows.append({'asset': a, 'picks': asset_picks[a], 'sh': sh, 'ann_ret': ann_ret, 'cum': cum})
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


def asset_when_picked_note_html(rows):
    """Render current conditional-pick interpretation without hardcoded stale metrics."""
    if not rows:
        return "<p>For each asset, performance is measured only during days it was held in a CPM pair. No conditional rows were available.</p>"

    def fmt_pct(v):
        return f"{v * 100:+.1f}%"

    neg = [r for r in rows if r['sh'] < 0]
    neg_sorted = sorted(neg, key=lambda r: r['sh'])
    neg_txt = ", ".join(
        f"{r['asset']} (Sh {r['sh']:+.2f}, AnnRet {fmt_pct(r['ann_ret'])}, CumRet {fmt_pct(r['cum'])}, n={r['picks']})"
        for r in neg_sorted
    ) or "none"
    low = min(rows, key=lambda r: r['sh'])
    only_negative_txt = (
        f" Currently, {neg_sorted[0]['asset']} is the only negative conditional-Sharpe asset."
        if len(neg_sorted) == 1 else ""
    )
    return f"""
<p>For each asset, performance is measured only during days it was held in a CPM pair. <strong>Current negative conditional Sharpe assets:</strong> {neg_txt}. Lowest conditional Sharpe is <strong>{low['asset']}</strong> (Sh {low['sh']:+.2f}).{only_negative_txt} SHV defensive cash can show high Sharpe because of very low volatility, so read it with AnnRet/CumRet.</p>
<p><strong>Interpretation:</strong> this chart is descriptive pick attribution, not a standalone asset-veto rule. TLT can show negative standalone when-picked returns while still serving a positive portfolio role through low/negative correlation and drawdown control.</p>
"""


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
    ax.bar(years, bull_y * 100, width, bottom=cpm_y * 100, label=f'BULL-QQQ ({int(w_bull*100)}%)', color='#f39c12', edgecolor='#7e5109')
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

    return f"""<table class='metric-table'><thead><tr>
<th>Peak date</th><th>Trough date</th><th>Recovery date</th>
<th>Depth</th><th>To trough</th><th>To recover</th>
<th>CPM contrib (peak->trough)</th><th>BULL contrib (peak->trough)</th><th>NDX contrib (peak->trough)</th>
</tr></thead><tbody>{rows_html}</tbody></table>"""


def chart_rolling_defensive_pct(panel: pd.DataFrame, start: pd.Timestamp):
    """Rolling 12-month % of months the CPM canary was defensive."""
    records = cpm_signal_records(panel, start)
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
    ax.set_ylabel('% of last 12 months in defensive (SHV cash)')
    ax.set_ylim(0, 100)
    ax.set_title('CPM Rolling Defensive Activation (12-month window)')
    ax.legend(loc='upper right')
    ax.grid(alpha=0.3)
    ax.xaxis.set_major_locator(mdates.YearLocator(2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
    return fig


def chart_pair_pick_timeline(panel: pd.DataFrame, start: pd.Timestamp):
    """Gantt-style pair-pick timeline colored by realized 1mo return."""
    records = cpm_signal_records(panel, start)
    sig_dates = [r["sig_d"] for r in records]
    timeline = []
    for i, rec in enumerate(records):
        sig_d = rec["sig_d"]
        weights = rec["weights"]
        new_pair = rec["pair"]
        regime = rec["regime"]
        sidx = panel.index.searchsorted(sig_d) + 2
        eidx = panel.index.searchsorted(sig_dates[i+1]) + 2 if i+1 < len(sig_dates) else len(panel.index)
        if sidx >= len(panel.index):
            continue
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
    ax.plot(roll_cb.index, roll_cb, color='#2e86c1', lw=1.5, label='CPM vs BULL-QQQ')
    ax.plot(roll_cn.index, roll_cn, color='#f39c12', lw=1.5, label='CPM vs NDX')
    ax.plot(roll_bn.index, roll_bn, color='#c0392b', lw=1.5, label='BULL-QQQ vs NDX')
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
         (f'BULL-QQQ ({int(w_bull*100)}%)', m_bull, '#f39c12'),
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


# ---------- Tables ----------

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
                       "Naive 60/40": yr_n.reindex(yr_b.index).values * 100,
                       "QQQ": yr_q.reindex(yr_b.index).values * 100})
    df["Excess vs Naive"] = df["PROD"] - df["Naive 60/40"]
    df["Excess vs QQQ"] = df["PROD"] - df["QQQ"]
    body = ""
    for _, r in df.iterrows():
        ex_n = r["Excess vs Naive"]
        ex_q = r["Excess vs QQQ"]
        exn_class = "pos" if ex_n > 0 else "neg"
        exq_class = "pos" if ex_q > 0 else "neg"
        body += f"<tr><td>{int(r['Year'])}</td>"
        for col in ["PROD", "CPM", "BULL-QQQ", "Naive 60/40", "QQQ"]:
            v = r[col]
            cls = "pos" if v > 0 else "neg"
            body += f"<td style='text-align:right' class='{cls}'>{v:+.2f}%</td>"
        body += f"<td style='text-align:right' class='{exn_class}'>{ex_n:+.2f}pp</td>"
        body += f"<td style='text-align:right' class='{exq_class}'>{ex_q:+.2f}pp</td></tr>\n"
    return f"""<div class='table-scroll'><table class='yearly'>
<thead><tr><th>Year</th><th>PROD<br>(60/20/20)</th><th>CPM only</th><th>BULL-QQQ only</th><th>Naive 60/40</th><th>QQQ</th><th>Ex vs Naive</th><th>Ex vs QQQ</th></tr></thead>
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


def current_alloc_html(panel: pd.DataFrame, sig_d: pd.Timestamp) -> str:
    records = cpm_signal_records(panel, pd.Timestamp("1900-01-01"), sig_d)
    rec = records[-1] if records else {"weights": {}, "pair": None, "regime": "DEFENSIVE", "safe": DEFAULT_CASH}
    weights = rec["weights"]
    pair = rec["pair"]
    regime = rec["regime"]
    safe = rec["safe"]

    # CPM sleeve (60%)
    fcp_html = "".join(f"<tr><td>{t}</td><td style='text-align:right'>{w*100:.1f}%</td></tr>"
                        for t, w in sorted(weights.items(), key=lambda x: -x[1]))
    pair_str = f"{pair[0]} + {pair[1]}" if pair else "-"

    # BULL-QQQ sleeve (20%)
    bq_w, bq_regime, bq_diag = compute_bull_qqq_weights(panel, sig_d)
    bq_html = "".join(f"<tr><td>{t}</td><td style='text-align:right'>{w*100:.1f}%</td></tr>"
                        for t, w in sorted(bq_w.items(), key=lambda x: -x[1]))
    cstate = bq_diag.get("state", "---")
    n_pos = bq_diag.get("composite_n_pos", 0)
    n_eval = bq_diag.get("composite_n_eval", 0)
    def _pillar_str(name, val):
        if val is None: return f"{name}=?"
        return f"{name}={'+' if val else '-'}"
    pillar_str = " ".join([
        _pillar_str("curve",  bq_diag.get("pillar_curve")),
        _pillar_str("vol",    bq_diag.get("pillar_vol")),
    ])
    comp_str = f"composite {n_pos}/{n_eval} [{pillar_str}]"
    if bq_regime.startswith("BULL_"):
        bq_state = f"{bq_regime} (canary {cstate}, {comp_str})"
    else:
        bq_state = f"CASH ({bq_diag.get('reason','-')}; canary {cstate}, {comp_str})"

    # NDX sleeve (20%) -- gated by BULL-QQQ regime
    try:
        from ndx_sleeve_live import compute_ndx_weights, load_ndx_panel, SELECT_K as NDX_SELECT_K
        ndx_panel_data = load_ndx_panel()
        ndx_w, ndx_regime, ndx_diag = compute_ndx_weights(panel, ndx_panel_data, sig_d)
        ndx_html = "".join(f"<tr><td>{t}</td><td style='text-align:right'>{w*100:.1f}%</td></tr>"
                            for t, w in sorted(ndx_w.items(), key=lambda x: -x[1]))
        if ndx_regime == "NDX_ACTIVE":
            sel = ndx_diag.get('selected', [])
            sector_summary = _ndx_sector_summary(sel)
            ndx_state = (f"NDX_ACTIVE · top-{NDX_SELECT_K} by 13612U: "
                          f"{', '.join(sel)}<br>Sector mix: {sector_summary}")
        else:
            ndx_state = f"{ndx_regime} -- {ndx_diag.get('reason', '100% cash')}"
    except (FileNotFoundError, ImportError) as e:
        ndx_w = {CASH_TICKER: 1.0}
        ndx_html = "<tr><td colspan='2'>(NDX panel not available)</td></tr>"
        ndx_state = f"NDX panel data unavailable ({e})"

    # Combined 60% CPM + 20% BULL-QQQ + 20% NDX  (UNSCALED)
    combined_uncapped = {}
    for t, w in weights.items():
        combined_uncapped[t] = combined_uncapped.get(t, 0.0) + w * CPM_WEIGHT
    for t, w in bq_w.items():
        combined_uncapped[t] = combined_uncapped.get(t, 0.0) + w * BULL_WEIGHT
    for t, w in ndx_w.items():
        combined_uncapped[t] = combined_uncapped.get(t, 0.0) + w * NDX_WEIGHT

    # Load vol-cap state (from vol_cap_state.json, persisted by daily vol-check)
    try:
        import json
        from vol_cap import VIX_PCT, VIX_LB_YEARS, VOL_CAP_SCALE
        state_file = ROOT / "vol_cap_state.json"
        if state_file.exists():
            vc_state = json.loads(state_file.read_text())
            vc_scale = float(vc_state.get("scale", 1.0))
            vc_regime = vc_state.get("regime", "NORMAL")
            vc_vix = vc_state.get("vix", None)
            vc_threshold = vc_state.get("vix_threshold", None)
            vc_as_of = vc_state.get("as_of_date", "never")
            vc_vix_asof = vc_state.get("vix_asof_date", "n/a")
            vc_last_event = vc_state.get("last_change_event")
            vc_lifetime = vc_state.get("lifetime_events", 0)
        else:
            vc_scale = 1.0
            vc_regime = "NORMAL"
            vc_vix = None
            vc_threshold = None
            vc_as_of = "never (vol_cap_state.json missing)"
            vc_vix_asof = "n/a"
            vc_last_event = None
            vc_lifetime = 0
    except Exception as e:
        vc_scale = 1.0
        vc_regime = "ERROR"
        vc_vix = None
        vc_threshold = None
        vc_as_of = f"error: {e}"
        vc_vix_asof = "n/a"
        vc_last_event = None
        vc_lifetime = 0

    # Apply scale: combined = vc_scale * uncapped; (1 - vc_scale) -> cash
    combined = {t: w * vc_scale for t, w in combined_uncapped.items()}
    if vc_scale < 1.0:
        cash_extra = 1.0 - vc_scale
        combined[CASH_TICKER] = combined.get(CASH_TICKER, 0.0) + cash_extra
    combined_html = "".join(f"<tr><td>{t}</td><td style='text-align:right'>{w*100:.1f}%</td></tr>"
                             for t, w in sorted(combined.items(), key=lambda x: -x[1])
                             if abs(w) > 1e-6)

    # Vol-cap status block
    vix_str = f"{vc_vix:.2f}" if vc_vix is not None else "n/a"
    thresh_str = f"{vc_threshold:.2f}" if vc_threshold is not None else "n/a"
    if vc_regime == "CAP_ENGAGED":
        vc_color = "#e74c3c"
        vc_status = (f"⚠️ <strong>CAP ENGAGED</strong> at {int(vc_scale*100)}% scale "
                      f"(half to cash). VIX: {vix_str} &gt; threshold {thresh_str}. "
                      f"Latched until next monthly signal.")
    elif vc_regime == "NORMAL":
        vc_color = "#27ae60"
        vc_status = (f"✓ NORMAL: scale 100%. VIX: {vix_str} &lt; threshold {thresh_str}.")
    else:
        vc_color = "#666"
        vc_status = f"State: {vc_regime}. As-of: {vc_as_of}."
    last_event_str = ""
    if vc_last_event:
        last_event_str = (f" Last state change: {vc_last_event.get('at_date')} "
                           f"({vc_last_event.get('kind')}, "
                           f"VIX={vc_last_event.get('vix_at_change')}, "
                           f"threshold={vc_last_event.get('threshold_at_change')}).")
    vol_cap_html = (
        f"<div style='grid-column: 1 / -1; background:#fef9e7; "
        f"border-left: 4px solid {vc_color}; padding:10px 14px; border-radius:4px; "
        f"margin: 8px 0;'>"
        f"<strong>Portfolio vol cap</strong> (latched binary {int(VOL_CAP_SCALE*100)}%; "
        f"VIX-based trigger: VIX &gt; P{int(VIX_PCT*100)} of rolling {VIX_LB_YEARS}y VIX): {vc_status} "
        f"<br><span style='font-size:0.9em;color:#555'>Threshold today = {thresh_str} "
        f"(P{int(VIX_PCT*100)} of last {VIX_LB_YEARS} years of VIX closes).{last_event_str}"
        f" VIX as-of {vc_vix_asof}. State as-of {vc_as_of}. Lifetime events: {vc_lifetime}.</span>"
        f"</div>"
    )

    # Build prior-vs-target trade-delta table (compare to PREVIOUS signal date if available)
    prev_combined = {}
    if len(records) >= 2:
        prev_rec = records[-2]
        prev_weights = prev_rec.get("weights", {})
        try:
            prev_sd = prev_rec.get("sig_d", None)
            prev_bq_w, _, _ = compute_bull_qqq_weights(panel, prev_sd) if prev_sd is not None else ({}, None, {})
            prev_ndx_w, _, _ = compute_ndx_weights(panel, ndx_panel_data, prev_sd) if prev_sd is not None else ({}, None, {})
        except Exception:
            prev_bq_w, prev_ndx_w = {}, {}
        for t, w in prev_weights.items():
            prev_combined[t] = prev_combined.get(t, 0.0) + w * CPM_WEIGHT * vc_scale
        for t, w in prev_bq_w.items():
            prev_combined[t] = prev_combined.get(t, 0.0) + w * BULL_WEIGHT * vc_scale
        for t, w in prev_ndx_w.items():
            prev_combined[t] = prev_combined.get(t, 0.0) + w * NDX_WEIGHT * vc_scale
        if vc_scale < 1.0:
            prev_combined[CASH_TICKER] = prev_combined.get(CASH_TICKER, 0.0) + (1.0 - vc_scale)
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

    # Vol-cap one-line summary for top-of-card
    if vc_regime == "CAP_ENGAGED":
        vc_summary = f"⚠️ Vol cap engaged ({int(vc_scale*100)}% scale, half to cash) — VIX {vix_str} &gt; {thresh_str} threshold"
    elif vc_regime == "NORMAL":
        vc_summary = f"✓ Vol cap normal (100% scale) — VIX {vix_str} &lt; {thresh_str} threshold"
    else:
        vc_summary = f"Vol cap state: {vc_regime} (as-of {vc_as_of})"

    # Bull-QQQ + NDX picks one-liner (for top summary)
    bull_pick = next(iter(bq_w), CASH_TICKER) if bq_w else CASH_TICKER
    ndx_picks_str = ", ".join(ndx_diag.get("selected", [])) if ndx_diag.get("selected") else "(cash)"
    sector_str = _ndx_sector_summary(ndx_diag.get("selected", [])) if ndx_diag.get("selected") else ""

    return f"""
<div class='alloc-grid'>
<div style='grid-column: 1 / -1'>
  <h4 style='background:#fff4d6;padding:8px 12px;border-radius:4px;margin:0 0 8px 0'>Final portfolio target {int(CPM_WEIGHT*100)}/{int(BULL_WEIGHT*100)}/{int(NDX_WEIGHT*100)} {('× ' + str(vc_scale)) if vc_scale < 1.0 else ''}</h4>
  <p style='font-size:0.78rem;color:#666;margin:2px 0 6px 0'>{vc_summary}</p>
  <div class='table-scroll'><table class='alloc'>{combined_target_html}</table></div>
</div>
<div style='grid-column: 1 / -1'>
  <h4 style='background:#e8f4fd;padding:8px 12px;border-radius:4px;margin:0 0 8px 0'>Rebalance trade (vs prior signal)</h4>
  <div class='table-scroll'>{trade_html}</div>
</div>
<div style='grid-column: 1 / -1'>
  <details>
    <summary style='font-weight:600;cursor:pointer'>Signal diagnostics (sleeves, vol-cap state, selection details)</summary>
    <div style='margin-top:10px'>
    <p style='font-size:0.85rem;margin:6px 0'><strong>CPM</strong> ({int(CPM_WEIGHT*100)}% of capital, regime <strong>{regime}</strong>): pair = <strong>{pair_str}</strong>, safe = {safe}</p>
    <p style='font-size:0.85rem;margin:6px 0'><strong>BULL-QQQ</strong> ({int(BULL_WEIGHT*100)}% of capital, state <strong>{bq_state}</strong>): holding <strong>{bull_pick}</strong></p>
    <p style='font-size:0.85rem;margin:6px 0'><strong>NDX</strong> ({int(NDX_WEIGHT*100)}% of capital, state <strong>{ndx_regime}</strong>): top-{NDX_SELECT_K} = {ndx_picks_str}{(' · sectors: ' + sector_str) if sector_str else ''}</p>
    {vol_cap_html}
    <h4 style='margin-top:14px'>Sleeve-internal weights (sum to 100% of each sleeve)</h4>
    <div style='display:grid;grid-template-columns:repeat(auto-fit, minmax(220px, 1fr));gap:14px'>
      <div><strong>CPM</strong><div class='table-scroll'><table class='alloc'>{fcp_html}</table></div></div>
      <div><strong>BULL-QQQ</strong><div class='table-scroll'><table class='alloc'>{bq_html}</table></div></div>
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
    
    # Load with sufficient warmup so CPM signals + BULL-QQQ 12mo TR momentum are stable
    panel_start = min(start - pd.DateOffset(years=20), pd.Timestamp("1995-01-01"))
    print(f"Loading panel from {panel_start.date()} (warmup for EMA200 canary) ...")
    panel = load_panel(start=panel_start, end=end)
    print(f"Panel: {panel.index[0].date()} -> {panel.index[-1].date()}, {len(panel.columns)} assets")
    
    print(f"Running CPM backtest ...")
    cpm, _ = run_cpm_backtest(panel, start, end)

    print("Computing BULL-QQQ sleeve ...")
    bull_qqq_rets = run_bull_qqq_backtest(panel, start, end)

    print("Computing NDX sleeve ...")
    from ndx_sleeve_live import run_ndx_backtest, load_ndx_panel, SELECT_K as NDX_SELECT_K
    try:
        ndx_panel = load_ndx_panel()
        ndx_rets, _ = run_ndx_backtest(panel, ndx_panel, start, end)
    except FileNotFoundError:
        print("  NDX panel data not found; skipping NDX sleeve.")
        ndx_rets = pd.Series(0.0, index=bull_qqq_rets.index)

    # Production blend: 60% CPM + 20% BULL-QQQ + 20% NDX
    common = cpm.index.intersection(bull_qqq_rets.index).intersection(ndx_rets.index)
    cpm = cpm.reindex(common)
    bull_qqq_rets = bull_qqq_rets.reindex(common)
    ndx_rets = ndx_rets.reindex(common).fillna(0.0)
    blended_uncapped = CPM_W * cpm + BULL_W * bull_qqq_rets + NDX_W * ndx_rets
    # Apply portfolio-level vol cap (latched binary 50%; trigger when
    # VIX > rolling 5y P95 of VIX)
    from vol_cap import compute_latched_scale, load_vix
    blend_sig_dates = (pd.date_range(blended_uncapped.index[0], blended_uncapped.index[-1],
                                       freq="ME")
                       .intersection(blended_uncapped.index).tolist())
    vix_series = load_vix(
        start=blended_uncapped.index[0] - pd.Timedelta(days=365 * 6),
        end=blended_uncapped.index[-1] + pd.Timedelta(days=2),
    )
    vol_scale, vol_events = compute_latched_scale(
        blended_uncapped, blend_sig_dates, vix=vix_series
    )
    blended = vol_scale * blended_uncapped
    prod_label = f"CPM-BULL-NDX ({int(CPM_W*100)}/{int(BULL_W*100)}/{int(NDX_W*100)}) + VIX cap"

    print(f"Running peer strategies ...")
    spy = panel["SPY"].ffill().pct_change().loc[start:end].fillna(0.0) if "SPY" in panel.columns else pd.Series(dtype=float)
    qqq = panel["QQQ"].ffill().pct_change().loc[start:end].fillna(0.0) if "QQQ" in panel.columns else pd.Series(dtype=float)
    six40 = sixty_forty(panel, start, end)
    # Core 2 benchmarks for clean comparison
    naive_pp_qt = naive_60_40_pp_qqq_trend(panel, start, end)

    strategies = {
        prod_label: blended,
        "CPM standalone": cpm,
        "BULL-QQQ sleeve": bull_qqq_rets,
        "NDX sleeve": ndx_rets,
        "Naive 60/40 PP/QQQ-trend": naive_pp_qt,
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
    CORE_CHARTS = (prod_label, "CPM standalone", "BULL-QQQ sleeve", "NDX sleeve",
                   "Naive 60/40 PP/QQQ-trend", "QQQ buy-hold")
    fig_equity = chart_equity({k: v for k, v in strategies.items() if k in CORE_CHARTS},
                              prod_label=prod_label)
    fig_dd = chart_drawdown({k: v for k, v in strategies.items() if k in CORE_CHARTS},
                            prod_label=prod_label)
    fig_yearly = chart_yearly_bars(blended, qqq, strategies["Naive 60/40 PP/QQQ-trend"])
    fig_monthly_heatmap = chart_monthly_heatmap(blended, title="PROD 60/20/20 Monthly Returns Heatmap")
    fig_rolling = chart_rolling_sharpe(blended, strategies["Naive 60/40 PP/QQQ-trend"])
    fig_excess = chart_rolling_excess(cpm, blended, strategies["Naive 60/40 PP/QQQ-trend"], bull_qqq_rets)
    fig_roll_dd = chart_rolling_dd(cpm, blended, strategies["Naive 60/40 PP/QQQ-trend"], bull_qqq_rets)
    fig_canary, regime_counts, picks, pair_counter = chart_canary_timeline(panel, start)
    fig_canary_heatmap = chart_canary_state_heatmap(panel, cpm, bull_qqq_rets, start)
    fig_asset_picked, asset_picked_rows = chart_asset_when_picked(panel, start)
    fig_sleeve_contrib = chart_sleeve_contribution(cpm, bull_qqq_rets, ndx_rets, CPM_W, BULL_W, NDX_W)
    drawdowns_html = table_worst_drawdowns(cpm, bull_qqq_rets, ndx_rets, CPM_W, BULL_W, NDX_W, top_n=10)
    fig_def_pct = chart_rolling_defensive_pct(panel, start)
    fig_pair_timeline = chart_pair_pick_timeline(panel, start)
    fig_sleeve_corr = chart_rolling_sleeve_correlation(cpm, bull_qqq_rets, ndx_rets)
    fig_distributions = chart_monthly_return_distributions(cpm, bull_qqq_rets, ndx_rets, CPM_W, BULL_W, NDX_W)
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
    
    # Per-sleeve breakdown of the PROD blend
    common_idx = cpm.index.intersection(bull_qqq_rets.index).intersection(ndx_rets.index)
    fcp_c = cpm.loc[common_idx]; mt2_c = bull_qqq_rets.loc[common_idx]
    ndx_c = ndx_rets.loc[common_idx].fillna(0.0)
    blend_60_20_20 = CPM_W * fcp_c + BULL_W * mt2_c + NDX_W * ndx_c

    sleeve_rows = [
        {"strategy": "CPM-BULL-NDX 60/20/20 (PRODUCTION)", **perf_metrics(blend_60_20_20)},
        {"strategy": "CPM standalone (60% sleeve)",        **perf_metrics(cpm)},
        {"strategy": "BULL-QQQ standalone (20% sleeve)",   **perf_metrics(bull_qqq_rets)},
        {"strategy": "NDX standalone (20% sleeve)",         **perf_metrics(ndx_c)},
    ]

    # ========================================================
    # EXTENDED ~27y backtest (1999-03 -> present)
    # QQQ actual inception: 1999-03-10. Earlier dates would require
    # synthetic QQQ proxies for the BULL sleeve.
    # Constraints by sleeve:
    #   - CPM: HYG_stitched (1980+), TIP (2000-06+, nan pre-2000 -> canary
    #     uses HYG only). GLD (2000-08+). DBC live 2006-02 (stitched pre).
    #     VBR live 2004-01 (stitched pre). Pre-2004 universe selection is
    #     proxy-heavy (universe-selection contamination concern).
    #   - BULL: QQQ live 1999-03. HYG+TIP canary -- pre-2000 TIP stitched via VIPSX.
    #     pre-2000 TIP nan, falls back to HYG-only canary.
    #   - NDX: PIT data 2006-01+. Pre-2006 the NDX sleeve mirrors BULL-QQQ
    #     (i.e., extra BULL exposure) instead of sitting in cash.
    # Includes 2000-02 dot-com bust, 2008 GFC, 2020 COVID, 2022 stress.
    # ========================================================
    ext_start = pd.Timestamp("1999-03-10")
    print(f"Running EXT backtest {ext_start.date()} ...")
    ext_fcp, _ = run_cpm_backtest(panel, ext_start, end)
    ext_bull = run_bull_qqq_backtest(panel, ext_start, end)
    try:
        ext_ndx, _ = run_ndx_backtest(panel, ndx_panel, ext_start, end)
    except Exception:
        ext_ndx = pd.Series(0.0, index=ext_bull.index)
    ext_common = ext_fcp.index.intersection(ext_bull.index).intersection(ext_ndx.index)
    ext_fcp_c = ext_fcp.reindex(ext_common)
    ext_bull_c = ext_bull.reindex(ext_common)
    ext_ndx_c = ext_ndx.reindex(ext_common).fillna(0.0)
    ext_blended = CPM_W * ext_fcp_c + BULL_W * ext_bull_c + NDX_W * ext_ndx_c
    ext_qqq = panel["QQQ"].ffill().pct_change().loc[ext_start:end].fillna(0.0) if "QQQ" in panel.columns else pd.Series(dtype=float)
    ext_naive = naive_60_40_pp_qqq_trend(panel, ext_start, end)

    ext_strategies = {
        prod_label: ext_blended,
        "CPM standalone": ext_fcp_c,
        "BULL-QQQ sleeve": ext_bull_c,
        "NDX sleeve": ext_ndx_c,
        "Naive 60/40 PP/QQQ-trend": ext_naive,
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
    yrs_full = (end - start).days / 365.25
    prod_metrics = perf_metrics(blended)
    bull_metrics = perf_metrics(bull_qqq_rets)
    ndx_metrics = perf_metrics(ndx_rets) if ndx_rets is not None and not ndx_rets.empty else {'sharpe': float('nan'), 'cagr': float('nan'), 'max_drawdown': float('nan'), 'ulcer': float('nan'), 'martin': float('nan')}
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
<p style='margin:6px 0;font-size:0.92rem'>Backtest <strong>{yrs_full:.1f}y</strong> (post-cost): Sharpe <strong>{prod_metrics['sharpe']:.2f}</strong> · CAGR <strong>{prod_metrics['cagr']*100:.2f}%</strong> · MaxDD <strong>{prod_metrics['max_drawdown']*100:.2f}%</strong>. Forward base-case Sh 1.00–1.30, CAGR 11–15% pre-tax (5–9% after).</p>
{perf_table_html(perf_rows, compact=True)}
<details>
  <summary style='font-size:0.85rem;color:#666;cursor:pointer'>Full metrics (Ulcer / Calmar / Martin)</summary>
  {perf_table_html(perf_rows)}
</details>
</div>

<details>
<summary><strong>Strategy spec (sleeves)</strong></summary>
<div class='card'>
<ul>
<li><strong>CPM ({int(CPM_W*100)}%):</strong> 9-asset universe (US factor + intl + diversifier), HYG+TIP+GLD any-positive 13612U canary, Faber SMA10 ranker top-{cpm_module.TOP_K_CANDIDATES}, min-vol pair selection ({cpm_module.CORR_LOOKBACK_DAYS}d cov), hold buffer {cpm_module.HOLD_BUFFER:.1f}z, vol cap {cpm_module.TARGET_VOL*100:.0f}% (de-risk only). SHV cash fallback.</li>
<li><strong>BULL-QQQ ({int(BULL_W*100)}%):</strong> 100% QQQ when all three gates pass: HYG OR TIP 13612U &gt; 0 (Keller/HAA canary) AND curve OR vol macro composite AND QQQ 12mo TR absolute momentum &gt; 0 (Antonacci GEM). Fallback: HAA best-of-safe (SHV / IEF) by 13612U.</li>
<li><strong>NDX ({int(NDX_W*100)}%):</strong> Top-{NDX_SELECT_K} PIT Nasdaq-100 by 13612U momentum, equal-weight {100/NDX_SELECT_K:.1f}% each, gated by BULL_QQQ regime.</li>
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
{yearly_table_html(blended, qqq, cpm, bull_qqq_rets, naive_pp_qt)}
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
{asset_when_picked_note_html(asset_picked_rows)}
</div>

<h3>Attribution & distributions</h3>
<div class='card'>
{fig_to_html(fig_sleeve_contrib)}
{drawdowns_html}
{fig_to_html(fig_distributions)}
{fig_to_html(fig_corr)}
</div>

<h3>Extended backtest (~27y, {ext_start.date()} -> {end.date()})</h3>
<p class='footnote'>NDX sleeve mirrors BULL-QQQ pre-2006 (no PIT data). Pre-2010 uses stitched ETF proxies.</p>
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
<summary>CPM Sleeve ({int(CPM_W*100)}%)</summary>
<ul>
<li><strong>Universe ({len(RISKY_UNIVERSE)}):</strong> US factor + international + diversifier.
  <br><code>{', '.join(RISKY_UNIVERSE)}</code></li>
<li><strong>Safe pool:</strong> <code>{', '.join(SAFE_POOL)}</code> (ultra-short Treasury cash, ~0.3y duration)</li>
<li><strong>Canary:</strong> {' + '.join(CANARY_ASSETS)} -- ANY positive 13612U momentum -&gt; risk-on; all negative -&gt; 100% SHV. HYG_stitched = VWEHX pre-2007-04 + live HYG.</li>
<li><strong>Ranker:</strong> Faber 10-month SMA distance: <code>(price - SMA10) / SMA10</code></li>
<li><strong>Top-K candidates:</strong> top {TOP_K_CANDIDATES} by ranker (= ceil({len(RISKY_UNIVERSE)}/2), top-half rule), drop negative momentum</li>
<li><strong>Pair selection:</strong> minimum-variance 50/50 pair ({CORR_LOOKBACK_DAYS}d covariance lookback, ~{CORR_LOOKBACK_DAYS/252:.1f}y)</li>
<li><strong>Hold buffer:</strong> {HOLD_BUFFER:.1f} z-units (keep prior pair member unless new candidate exceeds by this margin in cross-sectional z-score). Buffer memory resets when canary breadth crosses majority (HYG/TIP/GLD positive count moves between <2 and >=2), so stale pair memory does not bridge narrow-risk-on vs broad-risk-on regimes.</li>
<li><strong>Partial-safe fill:</strong> 1 positive momentum &rarr; 50% asset + 50% SHV; 0 positive &rarr; 100% SHV</li>
<li><strong>Vol cap:</strong> {TARGET_VOL*100:.0f}% annualized target, 63d realized vol, <strong>max 1.0x (de-risk only, no leverage)</strong>. Fires only in crisis regimes (~17% of days).</li>
<li><strong>Cost:</strong> {COST_BPS_PER_SIDE} bps/side</li>
<li><strong>Execution:</strong> month-end signal (T = last trading day of month, close), T+1 OPEN trade (next trading day MOO)</li>
</ul>
</details>
<details>
<summary>BULL-QQQ Sleeve ({int(BULL_BLEND*100)}%) -- 3-layer regime gate (Keller/HAA canary + custom curve/vol composite + TSMOM trend filter)</summary>
<ul>
<li><strong>Bull asset:</strong> 100% <code>{BULL_TICKER}</code> (Nasdaq-100). No state-conditional rotation.</li>
<li><strong>Canary gate:</strong> HYG OR TIP 13612U &gt; 0. Two-asset credit (HYG = high-yield) + inflation (TIP) regime check.</li>
<li><strong>Macro composite gate:</strong> curve OR vol pillar positive: (curve) IEF 63d ret &gt; TLT 63d ret = yield-curve steepening; (vol) SPY 63d vol &lt; 252d avg of 63d rolling vol = low-vol regime. Both pillars use natural midpoint cutoffs. Pair ablation showed curve+vol are the only two structurally orthogonal macro signals worth keeping; trend (SPY 200d MA) and credit (HYG 200d MA) pillars were dropped as redundant with asset_mom and canary respectively.</li>
<li><strong>Asset momentum gate:</strong> <code>{BULL_TICKER}</code> 12-month TR absolute momentum &gt; 0 (Antonacci GEM 2014, no skip-month). Direct observation of the risky asset itself.</li>
<li><strong>Fallback:</strong> HAA best-of-safe by 13612U momentum: <code>argmax(SHV, IEF)</code>. IEF in falling-rate regimes captures bond rally returns; SHV otherwise. May carry duration risk during IEF holding periods, so this sleeve is equity-or-defensive, not equity-or-cash.</li>
<li><strong>Standalone ({yrs_full:.1f}y, post-cost):</strong> Sharpe <strong>{bull_metrics['sharpe']:.2f}</strong>, CAGR <strong>{bull_metrics['cagr']*100:.2f}%</strong>, MaxDD <strong>{bull_metrics['max_drawdown']*100:.2f}%</strong>, Ulcer <strong>{bull_metrics['ulcer']*100:.2f}%</strong>, Martin <strong>{bull_metrics['martin']:.2f}</strong>.</li>

</ul>
</details>

<details>
<summary>NDX Sleeve ({int(NDX_W*100)}%) -- concentrated Nasdaq-100 momentum</summary>
<ul>
<li><strong>Universe:</strong> PIT Nasdaq-100 constituents (via <code>index-constitution</code> library, coverage 2006-01+).</li>
<li><strong>Signal:</strong> 13612U momentum per stock (same formula as CPM canary, canonical HAA unweighted).</li>
<li><strong>Selection:</strong> top 8 by momentum (positive only), equal-weighted 12.5% each.</li>
<li><strong>Gate:</strong> only allocates when BULL-QQQ regime is <code>BULL_QQQ</code> (equity-friendly); cash otherwise.</li>
<li><strong>Fallback:</strong> 100% <code>{CASH_TICKER}</code> when gate off or fewer than 4 positive-momentum candidates.</li>
<li><strong>Standalone ({yrs_full:.1f}y, post-cost):</strong> Sharpe <strong>{ndx_metrics['sharpe']:.2f}</strong>, CAGR <strong>{ndx_metrics['cagr']*100:.2f}%</strong>, MaxDD <strong>{ndx_metrics['max_drawdown']*100:.2f}%</strong>, Ulcer <strong>{ndx_metrics['ulcer']*100:.2f}%</strong>, Martin <strong>{ndx_metrics['martin']:.2f}</strong>.</li>
<li><strong>Tradeoff:</strong> High beta, high vol, deeper DD than other sleeves as standalone. Diluted by 10% blend weight, contributing meaningful CAGR uplift without dominating the blend's risk.</li>
</ul>
</details>
</div>

</details>

<details>
<summary><strong>Honest caveats</strong> (in-sample bias, NDX survivorship, regime risks; click to expand)</summary>
<div class='card'>
<ul style='line-height:1.5'>
<li><strong>In-sample bias.</strong> Tuned on this window. Forward Sharpe ~30-40% below backtest; blend 1.00-1.30, CPM standalone 0.80-1.10.</li>
<li><strong>NDX survivorship.</strong> Holding-stage MC bounded &lt;0.01 Sh. Selection-stage MC v2 (177 missing delisted tickers): adversarial stress-clustered impact -0.11 Sh / -1.40pp CAGR / MaxDD -15.51% at K=8. CRSP/Norgate validation pending.</li>
<li><strong>NDX 30y caveat.</strong> Pre-2006 sleeve mirrors BULL-QQQ (no PIT data). 30y window does NOT stress-test live stock-selection sleeve through dotcom.</li>
<li><strong>V-shape recovery lag.</strong> 13612U + 12mo TR momentum use trailing 12mo → re-entry delayed 1-3 months after deep selloffs. Lagged SPY ~5-10pp in 2009/2020-Q2/2022-Q4 snap-backs.</li>
<li><strong>Crisis-concentrated alpha.</strong> CPM defensive edge concentrated in 2008/2002/2020/2022. Non-crisis years lag SPY by design.</li>
<li><strong>Bull underperformance is structural.</strong> No leverage; gives up bull upside for crisis alpha.</li>
<li><strong>2020+ regime favors NDX.</strong> Mega-cap concentration regime massively rewarded top-K. Forward regime may revert.</li>
<li><strong>Not live-traded.</strong> Bootstrap CI on Sharpe is wide [1.08, 1.94].</li>
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
