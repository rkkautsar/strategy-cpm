from __future__ import annotations
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from types import SimpleNamespace
from dashboard.helpers import fig_to_html
from build_dashboard import cpm_signal_records
from dashboard.sections.regime import chart_canary_timeline

def _period_stats(rets: pd.Series) -> dict:
    """Sharpe / AnnRet / MaxDD from concatenated daily-return Series."""
    rets = rets.dropna()
    if len(rets) < 3:
        return {'sh': float('nan'), 'ann': float('nan'), 'mdd': float('nan')}
    eq = (1 + rets).cumprod()
    vol = rets.std(ddof=0) * np.sqrt(252)
    ann = rets.mean() * 252
    sh = ann / vol if vol > 0 else float('nan')
    mdd = (eq / eq.cummax() - 1).min()
    return {'sh': sh, 'ann': ann, 'mdd': mdd}


def compute_pick_asset_stats(records: list, panel: pd.DataFrame) -> dict:
    """Realized per-asset stats from CPM signal records."""
    from collections import defaultdict

    sig_dates = [r["sig_d"] for r in records]
    asset_rets = defaultdict(list)
    asset_picks = defaultdict(int)
    asset_weight_sum = defaultdict(float)

    for i, rec in enumerate(records):
        sig_d = rec["sig_d"]
        weights = {a: w for a, w in rec["weights"].items() if w > 0}

        # Count picks unconditionally so counts match chart_canary_timeline's
        # picks Counter, even if no future return window exists.
        for asset in weights:
            asset_picks[asset] += 1
            asset_weight_sum[asset] += weights[asset]

        sidx = panel.index.searchsorted(sig_d) + 2
        eidx = (panel.index.searchsorted(sig_dates[i + 1]) + 2
                if i + 1 < len(sig_dates) else len(panel.index))
        if sidx >= len(panel.index):
            continue
        window = panel.index[sidx:eidx]

        for asset in weights:
            if asset not in panel.columns:
                continue
            ser = panel[asset].reindex(window).pct_change().dropna()
            if len(ser):
                asset_rets[asset].append(ser)

    asset_stats = {}
    for asset, sers in asset_rets.items():
        merged = pd.concat(sers).groupby(level=0).sum().dropna()
        s = _period_stats(merged)
        asset_stats[asset] = {
            'picks': asset_picks[asset],
            'avgw': asset_weight_sum[asset] / asset_picks[asset] if asset_picks[asset] else float('nan'),
            **s,
        }

    for asset, n in asset_picks.items():
        if asset not in asset_stats:
            asset_stats[asset] = {
                'picks': n,
                'avgw': asset_weight_sum[asset] / n if n else float('nan'),
                'sh': float('nan'),
                'ann': float('nan'),
                'mdd': float('nan'),
            }
    return asset_stats


def _fmt_cell(v, suffix='', neg_class='neg', pos_class='pos'):
    if pd.isna(v): return "<td style='text-align:right; color:#999'>--</td>"
    cls = neg_class if v < 0 else pos_class
    if suffix == '%':
        return f"<td style='text-align:right' class='{cls}'>{v*100:+.1f}%</td>"
    return f"<td style='text-align:right' class='{cls}'>{v:+.2f}</td>"


def picks_table_html(picks, n_signals, records=None, panel=None):
    """Render CPM asset pick frequency table."""
    asset_stats = None
    if records is not None and panel is not None:
        asset_stats = compute_pick_asset_stats(records, panel)

    pick_rows = sorted(picks.items(), key=lambda x: -x[1])
    if asset_stats is not None:
        picks_html = ("<div class='table-scroll'><table class='yearly'><thead><tr>"
                      "<th>Asset</th><th>Picks</th><th>% mo</th><th>AvgW</th>"
                      "<th>Sharpe</th><th>AnnRet</th><th>MaxDD</th></tr></thead><tbody>")
    else:
        picks_html = "<div class='table-scroll'><table class='yearly'><thead><tr><th>Asset</th><th>Picks</th><th>% months</th></tr></thead><tbody>"
    for asset, cnt in pick_rows[:18]:
        pct = cnt / n_signals * 100
        picks_html += f"<tr><td>{asset}</td><td style='text-align:right'>{cnt}</td>" \
                      f"<td style='text-align:right'>{pct:.1f}%</td>"
        if asset_stats is not None:
            st = asset_stats.get(asset, {'avgw': float('nan'), 'sh': float('nan'), 'ann': float('nan'), 'mdd': float('nan')})
            avgw = st['avgw']
            if pd.isna(avgw):
                picks_html += "<td style='text-align:right; color:#999'>--</td>"
            else:
                picks_html += f"<td style='text-align:right'>{avgw*100:.1f}%</td>"
            picks_html += _fmt_cell(st['sh']) + _fmt_cell(st['ann'], '%') + _fmt_cell(st['mdd'], '%')
        picks_html += "</tr>"
    picks_html += "</tbody></table></div>"

    return f"""<div style='display:flex; gap:24px; flex-wrap:wrap;'>
<div style='flex:1; min-width:280px;'><h3 style='margin-top:0;'>Asset Pick Frequency</h3>{picks_html}</div>
</div>"""


def chart_cpm_monthly_asset_weights(panel: pd.DataFrame, start: pd.Timestamp,
                                    records: list | None = None):
    """Stacked monthly CPM sleeve weights by asset."""
    records = records if records is not None else cpm_signal_records(panel, start)

    risky_assets = ["QQQ", "SPHQ", "EFA", "EEM", "VNQ", "GLD", "TLT", "DBC"]
    plot_assets = risky_assets + ["SAFE"]
    color_map = {
        "QQQ": "#4e79a7",
        "SPHQ": "#f28e2b",
        "EFA": "#e15759",
        "EEM": "#76b7b2",
        "VNQ": "#59a14f",
        "GLD": "#edc948",
        "TLT": "#b07aa1",
        "DBC": "#ff9da7",
        "SAFE": "#9aa0a6",
    }

    dates = []
    stacked = {asset: [] for asset in plot_assets}
    for rec in records:
        weights = rec.get("weights", {})
        risky_total = 0.0
        for asset in risky_assets:
            w = float(weights.get(asset, 0.0) or 0.0)
            stacked[asset].append(w)
            risky_total += w

        safe_weight = sum(
            float(w or 0.0)
            for asset, w in weights.items()
            if asset not in risky_assets and pd.notna(w) and w > 0
        )
        if safe_weight <= 0.0:
            safe_weight = max(0.0, 1.0 - risky_total)
        stacked["SAFE"].append(min(1.0, max(0.0, safe_weight)))
        dates.append(rec["sig_d"])

    fig, ax = plt.subplots(figsize=(12, 4.5), constrained_layout=True)
    if not dates:
        ax.set_title("CPM monthly asset weights")
        ax.set_ylabel("Weight")
        ax.set_ylim(0, 1)
        return fig

    stack_values = [np.array(stacked[asset], dtype=float) for asset in plot_assets]
    ax.stackplot(
        dates,
        *stack_values,
        labels=plot_assets,
        colors=[color_map[asset] for asset in plot_assets],
        alpha=0.92,
    )
    ax.set_ylim(0, 1)
    ax.set_ylabel("Weight")
    ax.set_title("CPM monthly asset weights")
    ax.xaxis.set_major_locator(mdates.YearLocator(2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.18), ncol=5, frameon=False, fontsize=8)
    ax.grid(alpha=0.25)
    return fig


def chart_asset_when_picked(panel: pd.DataFrame, start: pd.Timestamp,
                              records: list | None = None):
    """Per-asset conditional performance when held in CPM baskets.

    Bars: Sharpe, AnnRet, CumRet per asset. Sorted by Sharpe. Uses the same
    `compute_pick_asset_stats` source as the Asset Pick Frequency table so the
    counts and metrics match.
    """
    records = records if records is not None else cpm_signal_records(panel, start)
    asset_stats = compute_pick_asset_stats(records, panel)

    rows = []
    for a, st in asset_stats.items():
        # Skip assets with insufficient data for meaningful stats
        if pd.isna(st.get('sh')):
            continue
        # Cumulative return: recompute from records the same way (raw, unweighted)
        rows.append({'asset': a, 'picks': st['picks'], 'sh': st['sh'],
                      'ann_ret': st['ann'], 'cum': st.get('mdd', float('nan'))})
    # Cum return is informational; recompute properly by concatenating held-period raw returns
    from collections import defaultdict
    cum_by_asset = defaultdict(list)
    sig_dates = [r["sig_d"] for r in records]
    for i, rec in enumerate(records):
        sig_d = rec["sig_d"]
        weights = {a: w for a, w in rec["weights"].items() if w > 0}
        sidx = panel.index.searchsorted(sig_d) + 2
        eidx = (panel.index.searchsorted(sig_dates[i+1]) + 2
                 if i+1 < len(sig_dates) else len(panel.index))
        if sidx >= len(panel.index): continue
        window = panel.index[sidx:eidx]
        for a in weights.keys():
            if a not in panel.columns: continue
            ser = panel[a].reindex(window).pct_change().dropna()
            if len(ser): cum_by_asset[a].append(ser)
    for r in rows:
        sers = cum_by_asset.get(r['asset'], [])
        if sers:
            full = pd.concat(sers).groupby(level=0).first().dropna()
            eq = (1 + full).cumprod()
            r['cum'] = eq.iloc[-1] - 1 if len(eq) else float('nan')
        else:
            r['cum'] = float('nan')
    rows.sort(key=lambda r: -r['sh'])

    assets = [r['asset'] for r in rows]
    sharpes = [r['sh'] for r in rows]
    ann_rets = [r['ann_ret'] * 100 for r in rows]
    cums = [r['cum'] * 100 for r in rows]
    picks_n = [r['picks'] for r in rows]

    fig, axes = plt.subplots(1, 3, figsize=(13, 4.5), constrained_layout=True)
    colors = ['#ec5b56' if s < 0 else '#73c373' if s > 1 else '#c4d76f' for s in sharpes]

    axes[0].barh(assets, sharpes, color=colors, edgecolor='#333')
    axes[0].axvline(0, color='black', lw=0.8)
    axes[0].set_xlabel('Sharpe (when held)')
    axes[0].set_title('Sharpe (when picked)')
    axes[0].invert_yaxis()
    for i, (s, n) in enumerate(zip(sharpes, picks_n)):
        axes[0].text(s + (0.05 if s >= 0 else -0.05), i, f"{s:+.2f}\n(n={n})",
                     va='center', ha='left' if s >= 0 else 'right', fontsize=8)

    axes[1].barh(assets, ann_rets, color=colors, edgecolor='#333')
    axes[1].axvline(0, color='black', lw=0.8)
    axes[1].set_xlabel('Annualized Return % (when held)')
    axes[1].set_title('Ann.Return (when picked)')
    axes[1].invert_yaxis()
    for i, v in enumerate(ann_rets):
        axes[1].text(v + (0.5 if v >= 0 else -0.5), i, f"{v:+.1f}%",
                     va='center', ha='left' if v >= 0 else 'right', fontsize=8)

    axes[2].barh(assets, cums, color=colors, edgecolor='#333')
    axes[2].axvline(0, color='black', lw=0.8)
    axes[2].set_xlabel('Cumulative Return % (over all held days)')
    axes[2].set_title('Cum.Return (when picked)')
    axes[2].invert_yaxis()
    for i, v in enumerate(cums):
        axes[2].text(v + (2 if v >= 0 else -2), i, f"{v:+.1f}%",
                     va='center', ha='left' if v >= 0 else 'right', fontsize=8)

    return fig, rows

def render(ctx: SimpleNamespace) -> str:
    # Build timeline components
    fig_canary, regime_counts, picks = chart_canary_timeline(
        ctx.panel, ctx.start,
        records=ctx.art.cpm_records,
        rpv_records=ctx.art.rpv_records,
        ndx_records=ctx.art.ndx_records,
        val_records=ctx.art.val_records,
    )
    fig_asset_picked, asset_picked_rows = chart_asset_when_picked(ctx.panel, ctx.start, records=ctx.art.cpm_records)
    fig_cpm_monthly_weights = chart_cpm_monthly_asset_weights(ctx.panel, ctx.start, records=ctx.art.cpm_records)
    n_signals = regime_counts["RISK_ON"] + regime_counts["DEFENSIVE"]
    picks_html = picks_table_html(picks, n_signals, records=ctx.art.cpm_records, panel=ctx.panel)

    return f"""<h3>CPM selection diagnostics</h3>
<div class='card'>
{picks_html}
<h4>CPM monthly asset weights</h4>
<p class='meta'>Stacked monthly CPM sleeve allocation across risky assets and safe sleeve.</p>
{fig_to_html(fig_cpm_monthly_weights)}
{fig_to_html(fig_asset_picked)}
</div>"""
