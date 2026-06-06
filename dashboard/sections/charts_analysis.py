from __future__ import annotations
from types import SimpleNamespace
from dashboard.helpers import fig_to_html
from dashboard.tables import yearly_table_html, perf_table_html
from dashboard.charts_core import (
    chart_equity, chart_drawdown, chart_rolling_dd, chart_rolling_sharpe,
    chart_rolling_excess, chart_yearly_bars, chart_monthly_heatmap,
)
from dashboard.sections import regime, cpm_diagnostics, attribution

def render(ctx: SimpleNamespace) -> str:
    CORE_CHARTS = (ctx.prod_label, "CPM", "RPV sleeve", "VAL sleeve", "NDX sleeve",
                   "Literature blend",
                   "Static 80% PP + 20% QQQ", "QQQ buy-hold")
    fig_equity = chart_equity({k: v for k, v in ctx.strategies.items() if k in CORE_CHARTS}, prod_label=ctx.prod_label)
    fig_dd = chart_drawdown({k: v for k, v in ctx.strategies.items() if k in CORE_CHARTS}, prod_label=ctx.prod_label)
    fig_roll_dd = chart_rolling_dd(ctx.art.cpm, ctx.art.blend, ctx.blend_bench, ctx.art.rpv)
    fig_yearly = chart_yearly_bars(ctx.art.blend, ctx.qqq, ctx.blend_bench)
    fig_monthly_heatmap = chart_monthly_heatmap(ctx.art.blend, title="PROD 60/15/15/10 Monthly Returns Heatmap")
    fig_rolling = chart_rolling_sharpe(ctx.art.blend, ctx.blend_bench)
    fig_excess = chart_rolling_excess(ctx.art.cpm, ctx.art.blend, ctx.blend_bench, ctx.art.rpv)
    fig_sleeve_corr = attribution.chart_rolling_sleeve_correlation(ctx.art.cpm, ctx.art.rpv, ctx.art.ndx, ctx.art.val)

    # Extended charts
    ext_fig_equity = chart_equity(ctx.ext_strategies, prod_label=ctx.prod_label)
    ext_fig_dd = chart_drawdown(ctx.ext_strategies, prod_label=ctx.prod_label)
    ext_fig_yearly = chart_yearly_bars(ctx.ext_art.blend, ctx.ext_qqq, ctx.ext_blend_bench)
    ext_fig_rolling = chart_rolling_sharpe(ctx.ext_art.blend, ctx.ext_blend_bench)
    ext_fig_roll_dd = chart_rolling_dd(ctx.ext_art.cpm, ctx.ext_art.blend, ctx.ext_blend_bench, ctx.ext_art.rpv)

    regime_html = regime.render(ctx)
    cpm_diagnostics_html = cpm_diagnostics.render(ctx)
    attribution_html = attribution.render(ctx)

    return f"""<details>
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
{yearly_table_html(ctx.art.blend, ctx.qqq, ctx.art.cpm, ctx.art.rpv, ctx.art.ndx, ctx.blend_bench)}
</div>

<h3>Rolling metrics (12-month)</h3>
<div class='card'>
{fig_to_html(fig_rolling)}
{fig_to_html(fig_excess)}
{fig_to_html(fig_sleeve_corr)}
</div>

{regime_html}

{cpm_diagnostics_html}

{attribution_html}

<h3>Extended backtest ({ctx.ext_start.date()} -> {ctx.end.date()})</h3>
<div class='card'>
<p style='margin:0 0 10px 0;font-size:0.86rem;color:#555'>The same 8 strategies from the canonical headline table evaluated over the extended 1999-2026 backtest window (includes dot-com bubble and pre-2008 market data for long-term stress-testing).</p>
{perf_table_html(ctx.ext_perf_rows)}
{fig_to_html(ext_fig_equity)}
{fig_to_html(ext_fig_dd)}
{fig_to_html(ext_fig_yearly)}
{fig_to_html(ext_fig_rolling)}
</div>

<h3>EXT Rolling 3-Month Max Drawdown</h3>
<div class='card'>
{fig_to_html(ext_fig_roll_dd)}
</div>

</details>"""
