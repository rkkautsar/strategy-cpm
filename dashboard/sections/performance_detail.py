from __future__ import annotations
import pandas as pd
import numpy as np
from types import SimpleNamespace
from dashboard.helpers import fig_to_html
from dashboard.charts_core import chart_risk_return_scatter

def topN_drawdowns_html(daily: pd.Series, n: int = 10) -> str:
    """Top-N worst drawdowns with start, trough, recovery, depth, duration."""
    r = daily.dropna()
    eq = (1 + r).cumprod()
    peak = eq.cummax()
    dd = (eq / peak - 1)
    # Identify distinct drawdown periods: peak-to-trough-to-recovery
    periods = []
    in_dd = False
    start_idx = None
    peak_value = None
    trough_idx = None
    trough_value = 0
    for i, (date, e) in enumerate(eq.items()):
        if not in_dd:
            if dd.iloc[i] < -0.001:  # 0.1% threshold to start
                in_dd = True
                start_idx = date
                peak_value = peak.iloc[i]
                trough_idx = date
                trough_value = dd.iloc[i]
        else:
            if dd.iloc[i] < trough_value:
                trough_value = dd.iloc[i]
                trough_idx = date
            if e >= peak_value:  # recovered
                periods.append({
                    "start": start_idx, "trough": trough_idx, "recovery": date,
                    "depth": trough_value * 100,
                    "days": (date - start_idx).days,
                    "to_trough": (trough_idx - start_idx).days,
                    "recovery_days": (date - trough_idx).days,
                })
                in_dd = False
    # If still in drawdown at end, record as ongoing
    if in_dd:
        periods.append({
            "start": start_idx, "trough": trough_idx, "recovery": None,
            "depth": trough_value * 100,
            "days": (eq.index[-1] - start_idx).days,
            "to_trough": (trough_idx - start_idx).days,
            "recovery_days": None,
        })
    top = sorted(periods, key=lambda x: x["depth"])[:n]
    rows = []
    for p in top:
        rec = str(p["recovery"].date()) if p["recovery"] else "<i>ongoing</i>"
        rec_d = f"{p['recovery_days']}d" if p["recovery_days"] is not None else "-"
        rows.append(
            f"<tr><td>{p['start'].date()}</td><td>{p['trough'].date()}</td>"
            f"<td>{rec}</td><td style='text-align:right'><b>{p['depth']:.2f}%</b></td>"
            f"<td style='text-align:right'>{p['to_trough']}d</td>"
            f"<td style='text-align:right'>{rec_d}</td>"
            f"<td style='text-align:right'>{p['days']}d</td></tr>"
        )
    return (
        "<div class='table-scroll'><table><thead><tr>"
        "<th>Peak start</th><th>Trough</th><th>Recovery</th>"
        "<th style='text-align:right'>Depth</th>"
        "<th style='text-align:right'>Peak->trough</th>"
        "<th style='text-align:right'>Trough->recovery</th>"
        "<th style='text-align:right'>Total duration</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>"
    )

def period_summary_html(daily: pd.Series, end_date: pd.Timestamp = None) -> str:
    """Period-over-period summary table: 1y/3y/5y/10y/since-inception."""
    r = daily.dropna()
    if end_date is None:
        end_date = r.index[-1]
    inception = r.index[0]
    periods = [
        ("1Y", end_date - pd.DateOffset(years=1)),
        ("3Y", end_date - pd.DateOffset(years=3)),
        ("5Y", end_date - pd.DateOffset(years=5)),
        ("10Y", end_date - pd.DateOffset(years=10)),
        ("Since inception", inception),
    ]
    rows = []
    for label, start in periods:
        if start < inception:
            if label == "Since inception":
                start = inception
            else:
                rows.append(f"<tr><td>{label}</td><td colspan=4 style='color:#888;text-align:center'>insufficient history</td></tr>")
                continue
        sub = r.loc[start:end_date].dropna()
        if len(sub) < 20:
            rows.append(f"<tr><td>{label}</td><td colspan=4 style='color:#888;text-align:center'>n/a</td></tr>")
            continue
        eq = (1 + sub).cumprod()
        yrs = (sub.index[-1] - sub.index[0]).days / 365.25
        cagr = float(eq.iloc[-1] ** (1/yrs) - 1) * 100 if yrs > 0 else 0
        sh = float(sub.mean() / sub.std() * (252 ** 0.5)) if sub.std() else 0
        dd = float((eq / eq.cummax() - 1).min()) * 100
        calmar = cagr / abs(dd) if dd != 0 else 0
        rows.append(
            f"<tr><td><b>{label}</b></td>"
            f"<td style='text-align:right'>{sh:.2f}</td>"
            f"<td style='text-align:right'>{cagr:+.2f}%</td>"
            f"<td style='text-align:right'>{dd:.2f}%</td>"
            f"<td style='text-align:right'>{calmar:.2f}</td></tr>"
        )
    return (
        "<div class='table-scroll'><table><thead><tr>"
        "<th>Period</th><th style='text-align:right'>Sharpe</th>"
        "<th style='text-align:right'>CAGR</th>"
        "<th style='text-align:right'>MaxDD</th>"
        "<th style='text-align:right'>Calmar</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>"
    )

def render(ctx: SimpleNamespace) -> str:
    CORE_CHARTS = (ctx.prod_label, "CPM", "RPV sleeve", "VAL sleeve", "NDX sleeve",
                   "Literature blend (60% AAA+TIP / 15% HAA-Simple QQQ / 15% HAA-Simple SPY / 10% PP)",
                   "Static 80% PP + 20% QQQ", "QQQ buy-hold")
    fig_riskret = chart_risk_return_scatter({k: v for k, v in ctx.strategies.items() if k in CORE_CHARTS}, prod_label=ctx.prod_label)
    
    return f"""<details>
<summary><strong>Performance detail</strong> (period summary, risk-return scatter, top-10 drawdowns; click to expand)</summary>

<h3>Period-over-period</h3>
<div class='card'>
{period_summary_html(ctx.art.blend)}
</div>

<h3>Risk vs Return (yearly snapshots)</h3>
<div class='card'>
{fig_to_html(fig_riskret)}
</div>

<h3>Top 10 worst drawdowns</h3>
<div class='card'>
{topN_drawdowns_html(ctx.art.blend, n=10)}
</div>

</details>"""
