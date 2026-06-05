from __future__ import annotations
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from types import SimpleNamespace
import cpm_live as cpm_module
from ndx_sleeve_live import load_ndx_panel
from rpv_live import compute_rpv_signals
from build_dashboard import (
    cpm_signal_records,
    rpv_signal_records,
    ndx_signal_records,
    RISKY_UNIVERSE,
    SAFE_POOL,
    TOP_K_CANDIDATES,
    CASH_TICKER,
    CPM_W,
    NDX_W,
    VAL_W,
    RPV_W,
)
from dashboard.helpers import fig_to_html

def chart_canary_timeline(panel: pd.DataFrame, start: pd.Timestamp,
                            records: list | None = None,
                            rpv_records: list | None = None,
                            ndx_records: list | None = None,
                            val_records: list | None = None) -> tuple:
    """Plot aggregate portfolio defensive (risk-off) exposure over time.
    Returns (fig, regime_counts dict, picks Counter)."""
    from collections import Counter
    records = records if records is not None else cpm_signal_records(panel, start)
    _br = rpv_records if rpv_records is not None else rpv_signal_records(panel, start)
    _nr = ndx_records if ndx_records is not None else ndx_signal_records(panel, load_ndx_panel(), start)
    _vr = val_records if val_records is not None else []

    _rpv_by_date = {r["sig_d"]: r for r in _br}
    _ndx_by_date = {r["sig_d"]: r for r in _nr}
    _val_by_date = {r["sig_d"]: r for r in _vr}

    cpm_per_date = []
    rpv_per_date = []
    picks = Counter()
    dates = []
    cpm_def_pcts = []
    rpv_def_pcts = []
    ndx_def_pcts = []
    val_def_pcts = []

    for rec in records:
        sd = rec["sig_d"]
        weights = rec["weights"]
        basket = rec["basket"]
        regime = rec["regime"]
        safe = rec["safe"]
        cpm_per_date.append((sd, regime, basket, safe))
        for asset, w in weights.items():
            if w > 0:
                picks[asset] += 1

        # Calculate exact defensive exposure per sleeve
        # 1. CPM defensive share (weight of the safe asset)
        cpm_def = weights.get(safe, 0.0)
        if regime == "DEFENSIVE":
            cpm_def = 1.0

        # 2. RPV defensive share
        rpv_rec = _rpv_by_date.get(sd, {})
        rpv_regime = rpv_rec.get("regime", "CASH")
        rpv_def = 1.0 if rpv_regime == "CASH" else 0.0

        # 3. NDX defensive share
        n_rec = _ndx_by_date.get(sd, {})
        n_weights = n_rec.get("weights", {})
        n_reg = n_rec.get("regime", "GATE_OFF (QQQ_mom <= 0)")
        if n_reg.startswith("GATE_OFF") or n_reg == "NDX_DEFENSIVE":
            ndx_def = 1.0
        else:
            ndx_def = n_weights.get(safe, 0.0)

        # 4. VAL defensive share
        v_rec = _val_by_date.get(sd, {})
        v_weights = v_rec.get("weights", {})
        safe_assets = set(SAFE_POOL + [CASH_TICKER])
        val_def = float(sum(v_weights.get(a, 0.0) for a in safe_assets))

        # Portfolio contributions in % of total blend
        cpm_def_pcts.append(CPM_W * cpm_def * 100.0)
        rpv_def_pcts.append(RPV_W * rpv_def * 100.0)
        ndx_def_pcts.append(NDX_W * ndx_def * 100.0)
        val_def_pcts.append(VAL_W * val_def * 100.0)
        dates.append(sd)

    for sd, _, _, _ in cpm_per_date:
        rpv_rec_reg = _rpv_by_date.get(sd, {})
        rpv_per_date.append((sd, rpv_rec_reg.get("regime", "CASH")))

    cpm_regimes = [r for _, r, _, _ in cpm_per_date]
    rpv_regimes = [r for _, r in rpv_per_date]
    regime_counts = {
        "RISK_ON": cpm_regimes.count("RISK_ON"),
        "DEFENSIVE": cpm_regimes.count("DEFENSIVE"),
        "RPV_ACTIVE": sum(1 for r in rpv_regimes if r != "CASH"),
        "RPV_CASH": sum(1 for r in rpv_regimes if r == "CASH"),
    }

    fig, ax = plt.subplots(figsize=(11, 3.2), constrained_layout=True)
    cpm_arr = np.array(cpm_def_pcts)
    rpv_arr = np.array(rpv_def_pcts)
    ndx_arr = np.array(ndx_def_pcts)
    val_arr = np.array(val_def_pcts)

    ax.bar(dates, cpm_arr, width=25, label=f"CPM ({int(CPM_W*100)}% wt)", color="#9e2a2b", alpha=0.85, edgecolor="none")
    ax.bar(dates, ndx_arr, width=25, bottom=cpm_arr, label=f"NDX ({int(NDX_W*100)}% wt)", color="#ffb703", alpha=0.85, edgecolor="none")
    ax.bar(dates, val_arr, width=25, bottom=cpm_arr + ndx_arr, label=f"VAL ({int(VAL_W*100)}% wt)", color="#7f3fbf", alpha=0.85, edgecolor="none")
    ax.bar(dates, rpv_arr, width=25, bottom=cpm_arr + ndx_arr + val_arr, label=f"RPV ({int(RPV_W*100)}% wt)", color="#3f51b5", alpha=0.85, edgecolor="none")

    ax.set_ylabel("Defensive Weight (%)", fontsize=9, fontweight="bold")
    ax.set_ylim(0, 100)
    ax.set_title(f"Aggregate Portfolio Defensive Exposure (Monthly Signal, {int(CPM_W*100)}/{int(NDX_W*100)}/{int(VAL_W*100)}/{int(RPV_W*100)})", fontsize=11, fontweight="bold")
    ax.xaxis.set_major_locator(mdates.YearLocator(2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.tick_params(axis='both', which='both', labelsize=8)
    ax.legend(loc="upper right", frameon=False, fontsize=8)
    return fig, regime_counts, picks

def chart_canary_state_heatmap(panel: pd.DataFrame, cpm_rets: pd.Series, rpv_rets: pd.Series, start: pd.Timestamp):
    """Truth-table heatmap of CPM and RPV sleeve performance by state.

    CPM: C1 breadth-state split (<=2, 3, 4 positive top-K picks).
    RPV: 2x2 split by Equity z-score sign and SPY 200d SMA trend state.
    Cell: Sharpe (color) + AnnRet + MaxDD + n_months.
    """
    end = panel.index[-1]

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

    def compute_rpv_grid(daily_returns):
        z_scores = compute_rpv_signals()
        spy = panel["SPY"].ffill() if "SPY" in panel.columns else pd.Series(dtype=float)
        spy_sma200 = spy.rolling(200).mean()
        states = {}
        for sig_d in z_scores.index:
            if sig_d < start or sig_d > end:
                continue
            zrow = z_scores.loc[sig_d]
            if pd.isna(zrow.get("equity")):
                continue
            spy_hist = spy.loc[:sig_d]
            sma_hist = spy_sma200.loc[:sig_d]
            if spy_hist.empty or sma_hist.empty:
                continue
            spy_close = spy_hist.iloc[-1]
            spy_sma = sma_hist.iloc[-1]
            if pd.isna(spy_close) or pd.isna(spy_sma):
                continue
            equity_z_pos = bool(zrow["equity"] > 0)
            spy_above_sma = bool(spy_close > spy_sma)
            states[sig_d] = (equity_z_pos, spy_above_sma)

        state_ser = pd.Series(states).sort_index()
        state_per_day = attribute(daily_returns, state_ser)
        row_order = [(True,), (False,)]
        col_order = [(True,), (False,)]
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

    def compute_cpm_n_pos_states():
        monthly = panel.loc[:end].resample("ME").last()
        faber = cpm_module.faber_sma_xs(monthly)
        states = {}
        for sig_d in monthly.index:
            if sig_d < start:
                continue
            avail = [t for t in RISKY_UNIVERSE
                     if t in faber.index and pd.notna(faber[t])
                     and pd.notna(panel.loc[sig_d].get(t, np.nan) if sig_d in panel.index else np.nan)]
            if not avail:
                continue
            daily_rets = panel[avail].ffill().pct_change()
            scores = {}
            for t in avail:
                v = daily_rets[t].loc[:sig_d].tail(252).std() * np.sqrt(252)
                if pd.isna(v) or v < 1e-9:
                    v = 1.0
                scores[t] = float(faber[t]) / v
            sa = pd.Series(scores)
            ranked = sa.sort_values(ascending=False)
            top_k = max(2, min(TOP_K_CANDIDATES, len(ranked)))
            top = ranked.iloc[:top_k]
            positive = top[top.index.map(lambda t: faber.get(t, -np.inf) > 0)]
            n_pos = len(positive)

            if n_pos <= 2:
                states[sig_d] = '<=2'
            elif n_pos == 3:
                states[sig_d] = '3'
            else:
                states[sig_d] = '4'
        return pd.Series(states).sort_index()

    def build_cpm_breadth_grid(daily_returns):
        state_ser = compute_cpm_n_pos_states()
        state_per_day = attribute(daily_returns, state_ser)
        row_order = ['<=2', '3', '4']
        grid = []
        for r in row_order:
            mask = state_per_day == r
            n_months = int((state_ser == r).sum())
            d = daily_returns[mask]
            s = cell_stats(d)
            grid.append([{'state': (r,), 'n_months': n_months, 'stats': s}])
        return grid

    cpm_grid = build_cpm_breadth_grid(cpm_rets)
    rpv_grid = compute_rpv_grid(rpv_rets)

    cpm_col_labels = ['C1 Breadth']
    cpm_row_labels = ['<=2 Positives', '3 Positives', '4 Positives']
    rpv_col_labels = ['SPY > SMA200', 'SPY <= SMA200']
    rpv_row_labels = ['Equity Z > 0', 'Equity Z <= 0']

    fig, axes = plt.subplots(2, 1, figsize=(11, 8.5), constrained_layout=True,
                              gridspec_kw={'height_ratios':[1, 1]})
    im = plot_sub(axes[0], cpm_grid, cpm_row_labels, cpm_col_labels,
                   'CPM sleeve - performance by C1 breadth state', fontsize=9)
    plot_sub(axes[1], rpv_grid, rpv_row_labels, rpv_col_labels,
              'RPV sleeve - performance by Value (Equity Z) and Trend (SPY SMA) state', fontsize=9)
    fig.colorbar(im, ax=axes, shrink=0.7, label='Sharpe', orientation='vertical', pad=0.02)
    return fig

def render(ctx: SimpleNamespace) -> str:
    # Build charts
    fig_canary, regime_counts, picks = chart_canary_timeline(
        ctx.panel, ctx.start,
        records=ctx.art.cpm_records,
        rpv_records=ctx.art.rpv_records,
        ndx_records=ctx.art.ndx_records,
        val_records=ctx.art.val_records,
    )
    fig_canary_heatmap = chart_canary_state_heatmap(ctx.panel, ctx.art.cpm, ctx.art.rpv, ctx.start)
    
    return f"""<h3>Regime & breadth history</h3>
<div class='card'>
{fig_to_html(fig_canary)}
{fig_to_html(fig_canary_heatmap)}
</div>"""
