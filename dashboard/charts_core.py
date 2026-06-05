from __future__ import annotations
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from dashboard.helpers import _ordered, _legend_below, PROD_STYLE, FCP_STYLES, BASE_RENDER_ORDER

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
    ax.bar(x + width, yr_b.values, width, label="CPM-NDX-VAL-RPV (PROD)", color="#0040d0")
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


    ax.plot(fcp_dd.index, fcp_dd.values, label="CPM", color="#1a9a1a", lw=1.6)
    ax.plot(blend_dd.index, blend_dd.values, label="CPM-NDX-VAL-RPV (PROD)", color="#0040d0", lw=2.0)
    ax.plot(bb4_dd.index, bb4_dd.values, label="BB4 lit blend", color="#9966aa", lw=1.4, ls="--", alpha=0.85)

    if max_fcp is not None:
        max_fcp_dd = rolling_intra_dd(max_fcp.reindex(idx))
        ax.plot(max_fcp_dd.index, max_fcp_dd.values, label="RPV",
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
            label="CPM vs BB4", color="#1a9a1a", lw=1.6)
    ax.plot(excess_blend.index, excess_blend.values,
            label="PROD vs BB4", color="#0040d0", lw=2.0)
    if max_fcp is not None:
        max_fcp_cagr = rolling_cagr(max_fcp.reindex(idx))
        excess_max = (max_fcp_cagr - bb4_cagr) * 100
        ax.plot(excess_max.index, excess_max.values,
                label="RPV vs BB4", color="#ff8800", lw=1.4, ls="--", alpha=0.85)
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
    ax.plot(fcp_sr.index, fcp_sr.values, label="CPM-NDX-VAL-RPV (PROD)", color="#0040d0", lw=2.0)
    ax.axhline(0, color="#888", lw=0.6, ls="--", alpha=0.5)
    ax.axhline(1, color="#0040d0", lw=0.6, ls=":", alpha=0.4)
    ax.set_ylabel("Sharpe")
    ax.set_title(f"Rolling {window_days//21}-Month Sharpe: PROD vs BB4 lit blend")
    ax.xaxis.set_major_locator(mdates.YearLocator(2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    _legend_below(ax, ncol=2)
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
