from __future__ import annotations
from types import SimpleNamespace
from dashboard.tables import perf_table_html

def render(ctx: SimpleNamespace) -> str:
    return f"""<details>
<summary><strong>Sleeve breakdown</strong></summary>
<div class='card'>
{perf_table_html(ctx.sleeve_rows)}
</div>
</details>"""
