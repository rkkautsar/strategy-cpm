from __future__ import annotations
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from types import SimpleNamespace
from dashboard.helpers import fig_to_html, _legend_below
from dashboard.charts_core import chart_correlations

def chart_sleeve_contribution(cpm_rets: pd.Series, rpv_rets: pd.Series, ndx_rets: pd.Series, val_rets: pd.Series,
                              w_cpm: float, w_rpv: float, w_ndx: float, w_val: float):
    """Yearly stacked bars showing each sleeve's contribution to blend annual return."""
    common = cpm_rets.index.intersection(rpv_rets.index).intersection(ndx_rets.index).intersection(val_rets.index)
    cpm_c = cpm_rets.loc[common] * w_cpm
    ndx_c = ndx_rets.loc[common] * w_ndx
    val_c = val_rets.loc[common] * w_val
    rpv_c = rpv_rets.loc[common] * w_rpv

    def yearly_contribution(daily):
        return daily.groupby(daily.index.year).sum()

    cpm_y = yearly_contribution(cpm_c)
    ndx_y = yearly_contribution(ndx_c)
    val_y = yearly_contribution(val_c)
    rpv_y = yearly_contribution(rpv_c)
    years = cpm_y.index

    fig, ax = plt.subplots(figsize=(12, 4.5), constrained_layout=True)

    width = 0.7
    ax.bar(years, cpm_y * 100, width, label=f'CPM ({int(w_cpm*100)}%)', color='#2e86c1', edgecolor='#1b4f72')
    ax.bar(years, ndx_y * 100, width, bottom=cpm_y * 100, label=f'NDX ({int(w_ndx*100)}%)', color='#c0392b', edgecolor='#641e16')
    ax.bar(years, val_y * 100, width, bottom=(cpm_y + ndx_y) * 100, label=f'VAL ({int(w_val*100)}%)', color='#7f3fbf', edgecolor='#4a235a')
    ax.bar(years, rpv_y * 100, width, bottom=(cpm_y + ndx_y + val_y) * 100, label=f'RPV ({int(w_rpv*100)}%)', color='#f39c12', edgecolor='#7e5109')

    totals = (cpm_y + ndx_y + val_y + rpv_y) * 100
    ax.plot(years, totals, color='black', marker='D', markersize=6, linestyle='', label='Blend total')

    ax.axhline(0, color='black', lw=0.5)
    ax.set_ylabel('Annual contribution to blend return (%)')
    ax.set_title('Per-sleeve contribution to blend (yearly, daily-sum approximation)')
    ax.set_xticks(years)
    ax.set_xticklabels(years, rotation=45)
    ax.grid(axis='y', alpha=0.3)
    _legend_below(ax, ncol=5)
    return fig


def table_worst_drawdowns(cpm_rets: pd.Series, rpv_rets: pd.Series, ndx_rets: pd.Series, val_rets: pd.Series,
                          w_cpm: float, w_rpv: float, w_ndx: float, w_val: float, top_n: int = 10) -> str:
    """Identify top-N drawdown periods of the blend and decompose by sleeve contribution."""
    common = cpm_rets.index.intersection(rpv_rets.index).intersection(ndx_rets.index).intersection(val_rets.index)
    blend = (
        w_cpm * cpm_rets.loc[common]
        + w_ndx * ndx_rets.loc[common]
        + w_val * val_rets.loc[common]
        + w_rpv * rpv_rets.loc[common]
    )
    eq = (1 + blend).cumprod()
    peak = eq.cummax()
    dd = eq / peak - 1

    in_dd = False
    periods = []
    start_d = None
    for date, val in dd.items():
        if not in_dd and val < -0.001:
            in_dd = True
            start_d = date
        elif in_dd and val >= -0.0001:
            trough_d = dd.loc[start_d:date].idxmin()
            trough_v = dd.loc[trough_d]
            periods.append({'start': start_d, 'trough': trough_d, 'recovery': date, 'depth': trough_v})
            in_dd = False
    if in_dd:
        trough_d = dd.loc[start_d:].idxmin()
        trough_v = dd.loc[trough_d]
        periods.append({'start': start_d, 'trough': trough_d, 'recovery': None, 'depth': trough_v})

    periods.sort(key=lambda p: p['depth'])
    top = periods[:top_n]

    rows_html = ""
    for p in top:
        s, t, r, d = p['start'], p['trough'], p['recovery'], p['depth']
        ptd_cpm = cpm_rets.loc[s:t].sum() * w_cpm
        ptd_ndx = ndx_rets.loc[s:t].sum() * w_ndx
        ptd_val = val_rets.loc[s:t].sum() * w_val
        ptd_rpv = rpv_rets.loc[s:t].sum() * w_rpv
        days_to_trough = (t - s).days
        days_to_recover = (r - t).days if r else None
        rec_str = f"{days_to_recover}d" if r else "<em>ongoing</em>"
        rows_html += (f"<tr>"
                      f"<td>{s.strftime('%Y-%m-%d')}</td>"
                      f"<td>{t.strftime('%Y-%m-%d')}</td>"
                      f"<td>{r.strftime('%Y-%m-%d') if r else '-'}</td>"
                      f"<td style='text-align:right'>{d*100:+.2f}%</td>"
                      f"<td style='text-align:right'>{days_to_trough}d</td>"
                      f"<td style='text-align:right'>{rec_str}</td>"
                      f"<td style='text-align:right; color:{'#c0392b' if ptd_cpm < 0 else '#27ae60'}'>{ptd_cpm*100:+.2f}%</td>"
                      f"<td style='text-align:right; color:{'#c0392b' if ptd_ndx < 0 else '#27ae60'}'>{ptd_ndx*100:+.2f}%</td>"
                      f"<td style='text-align:right; color:{'#c0392b' if ptd_val < 0 else '#27ae60'}'>{ptd_val*100:+.2f}%</td>"
                      f"<td style='text-align:right; color:{'#c0392b' if ptd_rpv < 0 else '#27ae60'}'>{ptd_rpv*100:+.2f}%</td>"
                      f"</tr>")

    return f"""<div class='table-scroll'><table class='metric-table'><thead><tr>
<th>Peak date</th><th>Trough date</th><th>Recovery date</th>
<th>Depth</th><th>To trough</th><th>To recover</th>
<th>CPM contrib (peak->trough)</th><th>NDX contrib (peak->trough)</th><th>VAL contrib (peak->trough)</th><th>RPV contrib (peak->trough)</th>
</tr></thead><tbody>{rows_html}</tbody></table></div>"""


def chart_monthly_return_distributions(cpm_rets: pd.Series, rpv_rets: pd.Series, ndx_rets: pd.Series,
                                         w_cpm: float, w_rpv: float, w_ndx: float):
    def monthly(daily):
        return (1 + daily).resample('ME').apply(lambda x: x.prod() - 1)
    m_cpm = monthly(cpm_rets).dropna() * 100
    m_rpv = monthly(rpv_rets).dropna() * 100
    m_ndx = monthly(ndx_rets).dropna() * 100
    common = cpm_rets.index.intersection(rpv_rets.index).intersection(ndx_rets.index)
    blend = w_cpm * cpm_rets.loc[common] + w_rpv * rpv_rets.loc[common] + w_ndx * ndx_rets.loc[common]
    m_blend = monthly(blend).dropna() * 100

    fig, axes = plt.subplots(2, 2, figsize=(12, 7), constrained_layout=True)
    for ax, (name, ser, color) in zip(
        axes.flat,
        [(f'CPM ({int(w_cpm*100)}%)', m_cpm, '#2e86c1'),
         (f'RPV ({int(w_rpv*100)}%)', m_rpv, '#f39c12'),
         (f'NDX ({int(w_ndx*100)}%)', m_ndx, '#c0392b'),
         (f'Blend {int(w_cpm*100)}/{int(w_rpv*100)}/{int(w_ndx*100)}', m_blend, '#27ae60')]
    ):
        ax.hist(ser, bins=40, color=color, alpha=0.7, edgecolor='black', linewidth=0.5)
        ax.axvline(ser.mean(), color='black', ls='--', lw=1, label=f'Mean {ser.mean():.2f}%')
        ax.axvline(ser.median(), color='red', ls=':', lw=1, label=f'Median {ser.median():.2f}%')
        ax.axvline(0, color='gray', lw=0.5)
        skew = ((ser - ser.mean()) ** 3).mean() / ser.std() ** 3
        kurt = ((ser - ser.mean()) ** 4).mean() / ser.std() ** 4 - 3
        ax.set_title(f'{name}: skew {skew:+.2f}, ex.kurt {kurt:+.2f}')
        ax.set_xlabel('Monthly return (%)')
        ax.set_ylabel('Count')
        ax.legend(fontsize=8, loc='upper right')
        ax.grid(alpha=0.3)
    return fig


def chart_rolling_sleeve_correlation(cpm_rets: pd.Series, rpv_rets: pd.Series, ndx_rets: pd.Series, window: int = 252):
    common = cpm_rets.index.intersection(rpv_rets.index).intersection(ndx_rets.index)
    roll_cb = cpm_rets.loc[common].rolling(window).corr(rpv_rets.loc[common])
    roll_cn = cpm_rets.loc[common].rolling(window).corr(ndx_rets.loc[common])
    roll_bn = rpv_rets.loc[common].rolling(window).corr(ndx_rets.loc[common])

    fig, ax = plt.subplots(figsize=(12, 4.5), constrained_layout=True)
    ax.plot(roll_cb.index, roll_cb, color='#2e86c1', lw=1.5, label='CPM vs RPV')
    ax.plot(roll_cn.index, roll_cn, color='#f39c12', lw=1.5, label='CPM vs NDX')
    ax.plot(roll_bn.index, roll_bn, color='#c0392b', lw=1.5, label='RPV vs NDX')
    ax.axhline(0, color='gray', lw=0.5)
    ax.axhline(0.5, color='gray', ls=':', lw=0.5)
    ax.set_ylabel('1y rolling correlation')
    ax.set_title('Rolling 252-day correlations between sleeves')
    ax.legend(loc='lower right')
    ax.grid(alpha=0.3)
    ax.xaxis.set_major_locator(mdates.YearLocator(2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
    return fig

def render(ctx: SimpleNamespace) -> str:
    fig_sleeve_contrib = chart_sleeve_contribution(ctx.art.cpm, ctx.art.rpv, ctx.art.ndx, ctx.art.val, ctx.cpm_w, ctx.rpv_w, ctx.ndx_w, ctx.val_w)
    drawdowns_html = table_worst_drawdowns(ctx.art.cpm, ctx.art.rpv, ctx.art.ndx, ctx.art.val, ctx.cpm_w, ctx.rpv_w, ctx.ndx_w, ctx.val_w, top_n=10)
    fig_distributions = chart_monthly_return_distributions(ctx.art.cpm, ctx.art.rpv, ctx.art.ndx, ctx.cpm_w, ctx.rpv_w, ctx.ndx_w)
    fig_sleeve_corr = chart_rolling_sleeve_correlation(ctx.art.cpm, ctx.art.rpv, ctx.art.ndx)
    fig_corr = chart_correlations({k: v for k, v in ctx.strategies.items() if k in (ctx.prod_label, "CPM", "RPV sleeve", "VAL sleeve", "NDX sleeve", "BB4 lit blend (60 AAA+TIP / 20 HAA-S SPY / 20 QQQ-trend)", "Static 80% PP + 20% QQQ", "QQQ buy-hold")} )

    return f"""<h3>Attribution & distributions</h3>
<div class='card'>
{fig_to_html(fig_sleeve_contrib)}
{drawdowns_html}
{fig_to_html(fig_distributions)}
{fig_to_html(fig_corr)}
</div>"""
