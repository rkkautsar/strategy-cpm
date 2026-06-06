from __future__ import annotations
from types import SimpleNamespace
from dashboard.tables import perf_table_html

def render(ctx: SimpleNamespace) -> str:
    return f"""<details>
<summary><strong>Sleeve breakdown</strong> (individual components and two-sleeve research blend)</summary>
<div class='card'>
<p style='margin:0 0 10px 0;font-size:0.86rem;color:#555'>Performance profiles of the individual tactical sleeves and the simplified two-sleeve blend (60% CPM + 40% RPV) for baseline reference.</p>
{perf_table_html(ctx.sleeve_rows)}
</div>
</details>"""
