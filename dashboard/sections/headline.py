from __future__ import annotations
from types import SimpleNamespace
from dashboard.helpers import fig_to_html
from dashboard.tables import perf_table_html
from dashboard.charts_core import chart_equity_dd_combined

def render(ctx: SimpleNamespace) -> str:
    # Render headline comparison
    headline_strats = {ctx.prod_label: ctx.art.blend}
    if ctx.blend_bench is not None and not ctx.blend_bench.empty:
        headline_strats["Literature blend"] = ctx.blend_bench
    fig_eq_dd_headline = chart_equity_dd_combined(headline_strats, prod_label=ctx.prod_label)
    calmar = ctx.prod_metrics['cagr'] / abs(ctx.prod_metrics['max_drawdown'])

    return f"""<h2>Headline performance</h2>
<div class='card'>
<p style='margin:0 0 8px 0;font-size:0.92rem;color:var(--muted)'>Backtest window of <strong>{ctx.yrs_full:.1f}y</strong> (post-cost) comparing the production portfolio against core asset classes and reference benchmarks:</p>

<div class='hero-cards'>
  <div class='stat-card'>
    <div class='stat-label'>Raw Sharpe</div>
    <div class='stat-value'>{ctx.prod_metrics['sharpe']:.2f}</div>
  </div>
  <div class='stat-card'>
    <div class='stat-label'>CAGR</div>
    <div class='stat-value'>{ctx.prod_metrics['cagr']*100:.2f}%</div>
  </div>
  <div class='stat-card'>
    <div class='stat-label'>Max Drawdown</div>
    <div class='stat-value' style='color:var(--neg)'>{ctx.prod_metrics['max_drawdown']*100:.2f}%</div>
  </div>
  <div class='stat-card'>
    <div class='stat-label'>Calmar Ratio</div>
    <div class='stat-value'>{calmar:.2f}</div>
  </div>
</div>

{perf_table_html(ctx.perf_rows)}

{fig_to_html(fig_eq_dd_headline)}
</div>"""
