from __future__ import annotations
from types import SimpleNamespace
from dashboard.helpers import fig_to_html
from dashboard.tables import perf_table_html
from dashboard.charts_core import chart_equity_dd_combined

def render(ctx: SimpleNamespace) -> str:
    # Render headline comparison
    CORE_CHARTS = (ctx.prod_label, "CPM", "RPV sleeve", "VAL sleeve", "NDX sleeve",
                   "BB4 lit blend (60 AAA+TIP / 20 HAA-S SPY / 20 QQQ-trend)",
                   "Static 80% PP + 20% QQQ", "QQQ buy-hold")
    headline_strats = {ctx.prod_label: ctx.art.blend}
    if ctx.bb4_blend is not None and not ctx.bb4_blend.empty:
        headline_strats["BB4 lit blend (60 AAA+TIP / 20 HAA-S SPY / 20 QQQ-trend)"] = ctx.bb4_blend
    fig_eq_dd_headline = chart_equity_dd_combined(headline_strats, prod_label=ctx.prod_label)
    
    return f"""<h2>Headline performance</h2>
<div class='card'>
<p style='margin:6px 0;font-size:0.92rem'>Backtest <strong>{ctx.yrs_full:.1f}y</strong> (post-cost): Sharpe <strong>{ctx.prod_metrics['sharpe']:.2f}</strong> | CAGR <strong>{ctx.prod_metrics['cagr']*100:.2f}%</strong> | Vol <strong>{ctx.prod_metrics['vol']*100:.2f}%</strong> | MaxDD <strong>{ctx.prod_metrics['max_drawdown']*100:.2f}%</strong>.</p>
{perf_table_html(ctx.perf_rows, compact=True)}
<p style='margin:10px 0 6px;font-size:0.86rem;color:#555'>Production blend vs two-sleeve (no NDX) (clean window: 2008-05-30 -> 2026-04-30).</p>
{perf_table_html(ctx.research_compare_rows, compact=True)}
{fig_to_html(fig_eq_dd_headline)}
<details>
  <summary style='font-size:0.85rem;color:#666;cursor:pointer'>Full metrics (Ulcer / Calmar / Martin)</summary>
  {perf_table_html(ctx.perf_rows)}
</details>
</div>"""
