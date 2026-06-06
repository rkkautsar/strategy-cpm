from __future__ import annotations
from types import SimpleNamespace
from dashboard.tables import alpha_beta_table_html

def render(ctx: SimpleNamespace) -> str:
    return f"""<details>
<summary><strong>Alpha / Beta / Correlation vs canonical benchmarks</strong> (daily OLS regression)</summary>
<div class='card'>
<p style='font-size:0.9em;color:#555'>Per-sleeve comparators: <code>CPM vs AAA+TIP canary</code>, <code>NDX vs HAA-Simple QQQ</code>, <code>VAL vs HAA-Simple SPY</code>, <code>RPV vs SACEVS value rotation</code> (secondary peer: <code>EW RPV universe</code>). Blend benchmark: <code>60% AAA+TIP + 15% HAA-Simple QQQ + 15% HAA-Simple SPY + 10% PP</code>. SPY/QQQ buy-hold rows show market-correlation diagnostics (low beta + low corr = portfolio diversifier, not levered equity).</p>
{alpha_beta_table_html(ctx.alpha_beta_rows)}
</div>
</details>"""
