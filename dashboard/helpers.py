from __future__ import annotations
import io
import re
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

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

def _ordered(strategies: dict) -> list:
    # Production label is whichever key starts with "CPM-NDX-VAL-RPV"; render last (top).
    prod_keys = [k for k in strategies if k.startswith("CPM-NDX-VAL-RPV")]
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

PROD_STYLE = dict(color="#0040d0", lw=2.0, ls="-", alpha=1.0, zorder=10)

FCP_STYLES = {
    "CPM":                  dict(color="#1a9a1a", lw=2.0, ls="-",  alpha=0.95, zorder=8),
    "RPV sleeve":           dict(color="#ff8800", lw=2.0, ls="-",  alpha=0.95, zorder=8),
    "VAL sleeve":           dict(color="#7f3fbf", lw=1.8, ls="-",  alpha=0.90, zorder=8),
    "NDX sleeve":           dict(color="#cc2266", lw=1.6, ls="-",  alpha=0.85, zorder=7),
    "Literature blend": dict(color="#9966aa", lw=1.6, ls="--", alpha=0.85, zorder=4),
    "Static 80% PP + 20% QQQ": dict(color="#2d8659", lw=1.4, ls="-.", alpha=0.85, zorder=4),
    "QQQ buy-hold":         dict(color="#707070", lw=1.2, ls=":",  alpha=0.7,  zorder=3),
    "SPY buy-hold":         dict(color="#a0a0a0", lw=1.0, ls=":",  alpha=0.65, zorder=3),
    "60/40 SPY/IEF":        dict(color="#b8b8b8", lw=1.0, ls=":",  alpha=0.65, zorder=3),
    "Keller VAA G4":        dict(color="#9966aa", lw=1.0, ls="--", alpha=0.55, zorder=2),
    "HAA-Balanced":         dict(color="#3399cc", lw=1.0, ls="--", alpha=0.55, zorder=2),
    "Faber GTAA5":          dict(color="#bb7733", lw=0.9, ls="--", alpha=0.5, zorder=2),
    "HAA-Simple":           dict(color="#88aabb", lw=0.9, ls="--", alpha=0.5, zorder=2),
}

BASE_RENDER_ORDER = [
    "Faber GTAA5", "HAA-Simple",
    "Keller VAA G4", "HAA-Balanced",
    "60/40 SPY/IEF", "SPY buy-hold",
    "NDX sleeve",
    "QQQ buy-hold", "Static 80% PP + 20% QQQ", "Literature blend",
    "VAL sleeve", "RPV sleeve", "CPM",
]
