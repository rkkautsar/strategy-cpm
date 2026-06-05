from __future__ import annotations
from types import SimpleNamespace

def render(ctx: SimpleNamespace) -> str:
    return f"""<details>
<summary><strong>Honest caveats</strong> (click to expand)</summary>
<div class='card'>
<ul style='line-height:1.5'>
<li><strong>Backtest only.</strong> Strategy is not live-traded.</li>
<li><strong>Data dependency.</strong> NDX results depend on PIT membership and available price history.</li>
<li><strong>Regime dependency.</strong> Defensive alpha depends on breadth/gates, trend, and diversifier behavior.</li>
<li><strong>Recovery lag.</strong> Monthly momentum signals can re-enter late after fast recoveries.</li>
<li><strong>Bootstrap labels.</strong> Single-strategy PROD confidence intervals use B={ctx.bootstrap_single_b}; difference tests vs BB4/benchmarks use B={ctx.bootstrap_paired_b}.</li>
<li><strong>Forward expectations.</strong> {ctx.forward_sharpe_guidance}</li>
<li><strong>Concentration.</strong> Risk-on regimes can concentrate in growth and Nasdaq exposure.</li>
</ul>
</div>

</details>"""
