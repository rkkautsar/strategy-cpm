from __future__ import annotations
from types import SimpleNamespace

def render_summary(ctx: SimpleNamespace) -> str:
    return f"""<details>
<summary><strong>Strategy spec (sleeves)</strong></summary>
<div class='card'>
<ul>
<li><strong>Cross-asset Parity Momentum (CPM) ({int(ctx.cpm_w*100)}%):</strong> 8-asset risky universe (QQQ, SPHQ, EFA, EEM, VNQ, GLD, TLT, DBC), EAA-style Vol-Adj (Faber/Vol) ranker, positive-trend screen, top-4. CPM risky fraction uses breadth cliff + HYG 13612U credit momentum: breadth gives risky fraction 100% when positive picks = 4, 50% when positive picks = 3, and 0% (100% safe) when positive picks &lt;= 2; HYG 13612U &lt; 0 forces risk-off (0% risky). If positive picks = 4, min-var 3-of-4 selection is used for the risky block; if positive picks = 3, the 3 positive picks are held equal-weighted; the safe fraction is routed to HAA best-of-safe (SHV / IEF) by 13612U.</li>
<li><strong>NDX ({int(ctx.ndx_w*100)}%):</strong> Top-{ctx.ndx_select_k} PIT Nasdaq-100 by raw 13612U momentum (positive only), equal-weight {100/ctx.ndx_select_k:.1f}% each, activated only when TIP 13612U &gt; 0, SPY 13612U &gt; 0, and SPY RV_20d &lt; RV_252d all pass.</li>
<li><strong>VAL ({int(ctx.val_w*100)}%):</strong> PIT Nasdaq-100 fundamental value+quality stock-picking sleeve. Monthly signal, top-half by QUALITY then cheapest by VALUE, stateful trend band (ENTER &gt; 1.05*SMA10m, HOLD &gt;= 1.00*SMA10m), equal-weight top-5, activated by the same TIP-canary + SPY-trend + SPY-volatility gate as NDX, trade T+1 OPEN (MOO), and route to HAA best-of-safe when gate is off.</li>
<li><strong>RPV ({int(ctx.rpv_w*100)}%) -- 5-premia sequential:</strong> Universe SPY, TLT, LQD, HYG, TIP + SHV cash. Monthly 120-month z-scores (term, IG spread, HY spread, equity, real yield), keep only z &gt; 0 and above-200d-SMA assets, fully-invested, z-weighted across survivors (no per-asset cap); 100% SHV only when no premium qualifies.</li>
</ul>
</div>
</details>"""

def render_details(ctx: SimpleNamespace) -> str:
    RISKY_UNIVERSE = ["QQQ", "SPHQ", "EFA", "EEM", "VNQ", "GLD", "TLT", "DBC"]
    SAFE_POOL = ["SHV", "IEF"]
    return f"""<details>
<summary><strong>Strategy spec details</strong> (full sleeve mechanics)</summary>
<div class='card'>
<details>
<summary>Cross-asset Parity Momentum (CPM) Sleeve ({int(ctx.cpm_w*100)}%)</summary>
<ul>
<li><strong>Universe ({len(RISKY_UNIVERSE)} assets):</strong> 8-asset risky universe (QQQ, SPHQ, EFA, EEM, VNQ, GLD, TLT, DBC).
  <br><code>{', '.join(RISKY_UNIVERSE)}</code></li>
<li><strong>Safe pool:</strong> <code>{', '.join(SAFE_POOL)}</code> (HAA-style best-of-safe by 13612U momentum)</li>
<li><strong>Gate:</strong> breadth cliff + HYG 13612U credit-momentum gate (HYG 13612U &lt; 0 forces risk-off).</li>
<li><strong>Ranker:</strong> EAA-style Volatility-Adjusted Faber score: <code>score = faber / vol_252d</code> where <code>faber = (price - SMA10) / SMA10</code>. Penalizes high-volatility "junk momentum".</li>
<li><strong>Top-K candidates:</strong> top 4 by volatility-adjusted Faber score, drop assets with raw Faber &le; 0</li>
<li><strong>Risky-block weights:</strong> equal-weight across surviving positives; when positive picks = 4 use min-var 3-of-4 selection before equal-weight allocation</li>
<li><strong>breadth-cliff partial-safe:</strong> risky fraction = 1.0 (when positive picks = 4), 0.5 (when positive picks = 3), or 0.0 (when positive picks &le; 2); safe fraction = 1 - risky fraction</li>
<li><strong>Cost:</strong> 10 bps/side</li>
<li><strong>Execution (T+1 MOO):</strong> month-end signal (T = last trading day of month, close), T+1 OPEN trade (next trading day MOO)</li>
</ul>
</details>
<details>
<summary>RPV Sleeve ({int(ctx.rpv_w*100)}%) -- Risk Premia Value (5-Premia Sequential)</summary>
<ul>
<li><strong>Universe:</strong> <code>SPY</code>, <code>TLT</code>, <code>LQD</code>, <code>HYG</code>, <code>TIP</code> plus <code>SHV</code> cash.</li>
<li><strong>Value (120-month z-scores):</strong> Monthly trailing 10-year z-score of each premium vs its own history (higher z = cheaper):
  <ol>
    <li><strong>Term:</strong> <code>DGS10 - DGS3MO</code> -&gt; <code>TLT</code></li>
    <li><strong>IG credit spread:</strong> <code>DBAA - DGS10</code> -&gt; <code>LQD</code></li>
    <li><strong>HY credit spread:</strong> <code>BAA - AAA</code> proxy -&gt; <code>HYG</code></li>
    <li><strong>Equity:</strong> S&amp;P earnings yield minus <code>DGS10</code> -&gt; <code>SPY</code></li>
    <li><strong>Real yield:</strong> <code>DGS10 - CPI YoY</code> -&gt; <code>TIP</code></li>
  </ol>
</li>
<li><strong>Selection (sequential filter):</strong> Keep premia with <code>z &gt; 0</code> and asset price above its 200-day SMA. Keep sleeve fully-invested, z-weighted across survivors (no per-asset cap); hold 100% <code>SHV</code> only when no premium qualifies.</li>
<li><strong>Execution:</strong> Monthly signal, trade T+1 OPEN (MOO).</li>
<li><strong>Sleeve ({ctx.yrs_full:.1f}y, post-cost):</strong> Sharpe <strong>{ctx.rpv_metrics['sharpe']:.2f}</strong>, CAGR <strong>{ctx.rpv_metrics['cagr']*100:.2f}%</strong>, MaxDD <strong>{ctx.rpv_metrics['max_drawdown']*100:.2f}%</strong>, Ulcer <strong>{ctx.rpv_metrics['ulcer']*100:.2f}%</strong>, Martin <strong>{ctx.rpv_metrics['martin']:.2f}</strong>.</li>
</ul>
</details>

<details>
<summary>NDX Sleeve ({int(ctx.ndx_w*100)}%) -- concentrated Nasdaq-100 momentum</summary>
<ul>
<li><strong>Universe:</strong> PIT Nasdaq-100 constituents (via <code>index-constitution</code> library, coverage 2006-01+).</li>
<li><strong>Signal:</strong> Raw 13612U momentum (no correlation penalty).</li>
<li><strong>Selection:</strong> top {ctx.ndx_select_k} positive momentum names, equal-weighted {100/ctx.ndx_select_k:.1f}% each.</li>
<li><strong>Gate:</strong> Activated only when TIP 13612U &gt; 0 canary, SPY 13612U &gt; 0 trend, and SPY RV_20d &lt; RV_252d all pass at the signal date.</li>
<li><strong>Best-of-safe:</strong> HAA best-of-safe (SHV/IEF by 13612U) when any gate leg is off. Partial-fill cash (when &lt;K positive candidates) also uses best-of-safe.</li>
<li><strong>Sleeve ({ctx.yrs_full:.1f}y, post-cost):</strong> Sharpe <strong>{ctx.ndx_metrics['sharpe']:.2f}</strong>, CAGR <strong>{ctx.ndx_metrics['cagr']*100:.2f}%</strong>, MaxDD <strong>{ctx.ndx_metrics['max_drawdown']*100:.2f}%</strong>, Ulcer <strong>{ctx.ndx_metrics['ulcer']*100:.2f}%</strong>, Martin <strong>{ctx.ndx_metrics['martin']:.2f}</strong>.</li>
<li><strong>Tradeoff:</strong> High beta, high vol, deeper DD than other sleeves on its own. Diluted by {int(ctx.ndx_w*100)}% blend weight, contributing meaningful CAGR uplift without dominating the blend's risk.</li>
</ul>
</details>

<details>
<summary>VAL Sleeve ({int(ctx.val_w*100)}%) -- PIT Nasdaq-100 value+quality stock selection</summary>
<ul>
<li><strong>Universe:</strong> PIT Nasdaq-100 constituents (via <code>index-constitution</code>) intersected with PIT fundamentals coverage and at least 260 trading days of NDX-panel price history.</li>
<li><strong>PIT fundamentals (as-of signal date):</strong> <code>accepted_at &lt;= sig_d</code> value_as_filed facts only (no look-ahead).</li>
<li><strong>Composites:</strong> VALUE = EW z-score of earnings yield, book/price, sales yield, and FCF yield; QUALITY = EW z-score of gross profitability, ROE, negative leverage, and accrual flag.</li>
<li><strong>Selection:</strong> Keep top-half by QUALITY, then choose cheapest by VALUE.</li>
<li><strong>State gating:</strong> Stateful trend band per candidate (ENTER when price &gt; 1.05*SMA10m, HOLD while price &gt;= 1.00*SMA10m).</li>
<li><strong>Sizing / gate-off routing:</strong> Equal-weight top-5 (20% each); residual and gate-off allocation routes to HAA best-of-safe (SHV/IEF by 13612U).</li>
<li><strong>Execution:</strong> Monthly signal, T+1 OPEN (MOO), 10 bps/side transaction cost assumption.</li>
<li><strong>Sleeve ({ctx.yrs_full:.1f}y, post-cost):</strong> Sharpe <strong>{ctx.val_metrics['sharpe']:.2f}</strong>, CAGR <strong>{ctx.val_metrics['cagr']*100:.2f}%</strong>, MaxDD <strong>{ctx.val_metrics['max_drawdown']*100:.2f}%</strong>, Ulcer <strong>{ctx.val_metrics['ulcer']*100:.2f}%</strong>, Martin <strong>{ctx.val_metrics['martin']:.2f}</strong>.</li>
</ul>
</details>
</div>

</details>"""
