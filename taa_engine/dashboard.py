from __future__ import annotations

from datetime import datetime, timezone
from html import escape
import json
from pathlib import Path

import numpy as np
import pandas as pd


def _pct(value: float) -> str:
    return f"{value:.1%}"


def build_dashboard(
    *,
    prices: pd.DataFrame,
    strategy_targets: dict[str, pd.DataFrame],
    portfolios: dict,
    metrics: pd.DataFrame,
    output_path: Path,
    fee_bps: float,
    rebalance_dates: list[pd.Timestamp],
) -> Path:
    """Write a mobile-friendly static dashboard without publishing price bars."""
    as_of = prices.index[-1]
    built_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    performance_rows = []
    for name in metrics.index:
        row = metrics.loc[name]
        performance_rows.append(
            f"<tr><th>{escape(str(name))}</th>"
            f"<td>{_pct(float(row['Total return']))}</td>"
            f"<td>{_pct(float(row['CAGR']))}</td>"
            f"<td>{_pct(float(row['Volatility']))}</td>"
            f"<td>{float(row['Sharpe']):.2f}</td>"
            f"<td>{_pct(float(row['Max drawdown']))}</td></tr>"
        )

    chart_data = []
    colors = {
        "CPM": "#147d8b", "HAA-Simple": "#8b67b4", "HAA-Balanced": "#3399cc",
        "BAA-G12": "#c28725", "AAA": "#778397", "VAA-G12": "#cb5973", "NDX": "#d45b42", "RPV": "#34875b", "VAL": "#bd6e35", "SPY B&H": "#a6afbd",
        "60/40 Annual": "#5476d2",
    }
    for name, portfolio in portfolios.items():
        value = portfolio.value() if hasattr(portfolio, "value") else portfolio
        if isinstance(value, pd.DataFrame):
            value = value.iloc[:, 0]
        value = value.dropna()
        chart_data.append({
            "name": str(name),
            "color": colors.get(str(name), "#7a8797"),
            "dates": [timestamp.strftime("%Y-%m-%d") for timestamp in value.index],
            "values": [float(item) for item in value.to_numpy()],
        })
    chart_data_json = json.dumps(chart_data, separators=(",", ":"))
    blendable_names = [name for name in ("CPM", "HAA-Simple", "HAA-Balanced", "BAA-G12", "AAA", "VAA-G12", "NDX", "RPV", "VAL") if name in portfolios]
    blend_controls = "".join(
        f'<label class="blend-leg"><input type="checkbox" class="blend-enabled" data-strategy="{escape(name)}">'
        f'<span>{escape(name)}</span><input type="number" class="blend-weight" data-strategy="{escape(name)}" '
        f'min="0" max="100" step="1" value="0" disabled aria-label="{escape(name)} target percent">'
        f'<span>%</span></label>'
        for name in blendable_names
    )
    rebalance_dates_json = json.dumps([pd.Timestamp(date).strftime("%Y-%m-%d") for date in rebalance_dates])
    blend_target_state = {}
    for name in blendable_names:
        events = strategy_targets[name].dropna(how="all")
        if events.empty:
            continue
        current_targets = events.iloc[-1].fillna(0.0)
        previous_targets = events.iloc[-2].fillna(0.0) if len(events) > 1 else pd.Series(0.0, index=events.columns)
        blend_target_state[name] = {
            "current_date": events.index[-1].strftime("%Y-%m-%d"),
            "previous_date": events.index[-2].strftime("%Y-%m-%d") if len(events) > 1 else None,
            "current": {str(ticker): float(weight) for ticker, weight in current_targets.items() if abs(float(weight)) > 1e-8},
            "previous": {str(ticker): float(weight) for ticker, weight in previous_targets.items() if abs(float(weight)) > 1e-8},
        }
    blend_target_state_json = json.dumps(blend_target_state, separators=(",", ":"))

    performance_data = {
        "all": [
            {
                "name": str(name),
                "total_return": float(row["Total return"]),
                "cagr": float(row["CAGR"]),
                "volatility": float(row["Volatility"]),
                "sharpe": float(row["Sharpe"]),
                "max_drawdown": float(row["Max drawdown"]),
            }
            for name, row in metrics.iterrows()
        ]
    }
    end_date = as_of
    for years in (10, 5, 3, 1):
        cutoff = end_date - pd.DateOffset(years=years)
        rows = []
        for name, portfolio in portfolios.items():
            value = portfolio.value() if hasattr(portfolio, "value") else portfolio
            if isinstance(value, pd.DataFrame):
                value = value.iloc[:, 0]
            value = value.dropna()
            period = value.loc[value.index >= cutoff]
            if len(period) < 2:
                continue
            daily_returns = period.pct_change().dropna()
            elapsed_years = max((period.index[-1] - period.index[0]).days / 365.25, 1 / 365.25)
            total_return = float(period.iloc[-1] / period.iloc[0] - 1)
            volatility = float(daily_returns.std(ddof=1) * np.sqrt(252)) if len(daily_returns) > 1 else 0.0
            sharpe = (
                float(daily_returns.mean() / daily_returns.std(ddof=1) * np.sqrt(252))
                if len(daily_returns) > 1 and daily_returns.std(ddof=1) > 0 else 0.0
            )
            drawdown = period / period.cummax() - 1
            rows.append({
                "name": str(name),
                "total_return": total_return,
                "cagr": float((period.iloc[-1] / period.iloc[0]) ** (1 / elapsed_years) - 1),
                "volatility": volatility,
                "sharpe": sharpe,
                "max_drawdown": float(drawdown.min()),
            })
        performance_data[str(years)] = rows
    performance_data_json = json.dumps(performance_data, separators=(",", ":"))
    strategies_json = json.dumps(blendable_names, separators=(",", ":"))

    html = r'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="theme-color" content="#f4f7fb">
    <title>TAA Dashboard</title>
  <style>
    :root { color-scheme: light; --ink:#17263c; --muted:#68778b; --line:#e5ebf1; --panel:#fff; --bg:#f4f7fb; --accent:#147d8b; }
    * { box-sizing:border-box; }
    body { margin:0; background:var(--bg); color:var(--ink); font:15px/1.5 Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif; }
    main { max-width:1120px; padding:28px 22px 44px; margin:0 auto; }
    header { display:flex; justify-content:space-between; align-items:flex-end; gap:16px; margin:4px 0 22px; }
    .eyebrow { color:var(--accent); font-weight:750; font-size:11px; letter-spacing:.12em; text-transform:uppercase; }
    h1 { margin:4px 0 2px; font-size:clamp(26px,4vw,36px); line-height:1.15; letter-spacing:-.04em; }
    .subtitle,.muted { color:var(--muted); }
    .updated { text-align:right; color:var(--muted); font-size:12px; white-space:nowrap; }
    .grid { display:grid; gap:16px; }
    .metrics { grid-template-columns:repeat(4,minmax(0,1fr)); margin-bottom:16px; }
    .portfolio-panel { margin-bottom:18px; border-color:#d8e5eb; background:linear-gradient(135deg,#fff 0%,#f2f8fa 100%); }
    .portfolio-mode { display:inline-flex; gap:4px; padding:4px; background:#eaf0f3; border-radius:11px; }
    .mode-button { border:0; border-radius:8px; padding:9px 14px; background:transparent; color:var(--muted); font:inherit; font-size:13px; font-weight:700; cursor:pointer; }
    .mode-button[aria-pressed="true"] { background:#fff; color:var(--ink); box-shadow:0 1px 4px rgba(25,48,78,.12); }
    .portfolio-controls { margin-top:14px; }
    .blend-summary { display:flex; align-items:center; flex-wrap:wrap; gap:10px; }
    .blend-summary-copy { flex:1 1 240px; min-width:0; }
    .blend-summary-title { display:block; font-size:13px; font-weight:750; }
    .blend-summary-value { display:block; color:var(--muted); font-size:12px; margin-top:2px; }
    .blend-editor { margin-top:14px; padding-top:14px; border-top:1px solid var(--line); }
    .blend-editor[hidden],.blend-summary[hidden],.portfolio-controls[hidden],#portfolio-results[hidden] { display:none; }
    .blend-editor-title { margin:0 0 4px; font-size:15px; }
    .strategy-picker { display:flex; align-items:center; gap:10px; }
    .strategy-picker label { color:var(--muted); font-size:12px; font-weight:650; }
    .strategy-picker select { min-width:190px; border:1px solid var(--line); border-radius:9px; background:#fff; color:var(--ink); padding:9px 11px; font:inherit; }
    .strategy-name { color:var(--accent); font-weight:750; }
    .two-col { grid-template-columns:minmax(0,1.05fr) minmax(0,.95fr); }
    .card,.metric { background:var(--panel); border:1px solid var(--line); border-radius:16px; box-shadow:0 5px 20px rgba(25,48,78,.035); }
    .metric { padding:16px 18px; }
    .metric span { color:var(--muted); display:block; font-size:12px; }
    .metric strong { display:block; margin-top:4px; font-size:23px; letter-spacing:-.025em; }
    .card { padding:20px; min-width:0; }
    .card h2 { margin:0 0 4px; font-size:17px; letter-spacing:-.02em; }
    .card-intro { margin:0 0 16px; color:var(--muted); font-size:12px; }
    .position-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:9px; }
    .position { display:flex; align-items:center; justify-content:space-between; padding:12px 13px; background:#f4f8fa; border-radius:11px; }
    .position span { font-size:13px; font-weight:650; }
    .position strong { font-size:15px; }
    .table-wrap { width:100%; overflow-x:auto; }
    table { width:100%; border-collapse:collapse; font-size:12px; text-align:right; }
    th,td { padding:10px 8px; border-bottom:1px solid var(--line); white-space:nowrap; }
    th:first-child,td:first-child { text-align:left; }
    thead th { color:var(--muted); font-weight:600; font-size:11px; }
    tbody tr:last-child td,tbody tr:last-child th { border-bottom:0; }
    .action { display:inline-block; margin-right:5px; padding:2px 6px; border-radius:6px; font-size:10px; font-weight:750; }
    .buy { color:#13744d; background:#e8f6ef; }
    .sell { color:#a94a4a; background:#fbefef; }
    .delta.buy { color:#13744d; } .delta.sell { color:#a94a4a; }
    .chart-card { margin-top:16px; padding:18px 12px 8px; }
    .chart-head { display:flex; align-items:flex-start; justify-content:space-between; gap:12px; padding:0 6px; }
    .range-select { flex:0 0 auto; border:1px solid var(--line); border-radius:9px; background:#fff; color:var(--ink); padding:8px 10px; font:inherit; font-size:12px; }
    .echart { width:100%; height:390px; }
    #drawdown-chart { height:300px; }
    .footnote { padding:12px 4px 0; font-size:11px; color:var(--muted); }
    .performance { margin-top:16px; }
    .blend-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(190px,1fr)); gap:9px; }
    .blend-leg { display:grid; grid-template-columns:20px minmax(0,1fr) 68px 12px; align-items:center; gap:8px; padding:10px 11px; border:1px solid var(--line); border-radius:10px; font-size:13px; }
    .blend-leg input[type=checkbox] { width:17px; height:17px; accent-color:var(--accent); }
    .blend-weight { width:68px; border:1px solid var(--line); border-radius:7px; padding:6px; text-align:right; font:inherit; }
    .blend-actions { display:flex; flex-wrap:wrap; align-items:center; gap:9px; margin-top:12px; }
    .primary-button,.secondary-button { border:0; border-radius:8px; padding:9px 13px; font:inherit; font-size:12px; font-weight:700; cursor:pointer; }
    .primary-button { background:var(--accent); color:#fff; }
    .secondary-button { background:#eef3f6; color:var(--ink); }
    .blend-message { min-height:1.5em; margin:9px 0 0; font-size:12px; }
    .blend-holdings { margin-top:18px; padding-top:16px; border-top:1px solid var(--line); }
    .blend-holdings h3 { margin:0 0 4px; font-size:14px; }
    @media (max-width:760px) {
      main { padding:20px 13px 32px; }
      header { align-items:flex-start; flex-direction:column; margin-bottom:16px; }
      .updated { text-align:left; white-space:normal; }
      .portfolio-mode { display:grid; grid-template-columns:1fr 1fr; width:100%; }
      .mode-button { padding:10px 8px; }
      .strategy-picker { align-items:stretch; flex-direction:column; gap:6px; }
      .strategy-picker select { min-width:0; width:100%; }
      .blend-grid { grid-template-columns:1fr; }
      .blend-actions .primary-button { order:-1; width:100%; }
      .metrics { grid-template-columns:repeat(2,minmax(0,1fr)); gap:9px; }
      .metric { padding:13px 14px; border-radius:13px; }
      .metric strong { font-size:21px; }
      .two-col { grid-template-columns:1fr; gap:12px; }
      .card { padding:16px 14px; border-radius:14px; }
      .chart-card { padding:14px 6px 8px; }
      .chart-head { padding:0 5px; align-items:center; }
      .range-select { max-width:112px; }
    }
    @media (max-width:380px) {
      .position-grid { grid-template-columns:1fr; }
      table { font-size:11px; }
      th,td { padding:9px 6px; }
    }
  </style>
</head>
<body>
<main>
  <header>
    <div><div class="eyebrow">Tactical asset allocation · Monthly</div><h1>TAA Dashboard</h1>
      <div class="subtitle">Inspect strategy performance, current targets, and monthly target changes.</div></div>
    <div class="updated">Prices through __AS_OF__<br>Dashboard built __BUILT_AT__</div>
  </header>
  <section class="card portfolio-panel" aria-label="Portfolio selection and blend editor">
    <div class="portfolio-mode" role="group" aria-label="Choose portfolio type">
      <button id="mode-single" class="mode-button" type="button" aria-pressed="true">Single strategy</button>
      <button id="mode-blend" class="mode-button" type="button" aria-pressed="false">My blend</button>
    </div>
    <div id="single-controls" class="portfolio-controls">
      <div class="strategy-picker"><label for="strategy-select">Inspect strategy</label><select id="strategy-select"><option value="CPM">CPM</option><option value="HAA-Simple">HAA-Simple</option><option value="HAA-Balanced">HAA-Balanced</option><option value="BAA-G12">BAA-G12</option><option value="AAA">AAA</option><option value="VAA-G12">VAA-G12</option><option value="NDX">NDX</option><option value="RPV">RPV</option><option value="VAL">VAL</option></select></div>
    </div>
    <div id="blend-controls-panel" class="portfolio-controls" hidden>
      <div id="blend-summary" class="blend-summary" hidden><div class="blend-summary-copy"><span class="blend-summary-title">Saved blend</span><span id="blend-summary-value" class="blend-summary-value"></span></div><button id="edit-blend" type="button" class="secondary-button">Edit</button></div>
      <div id="blend-editor" class="blend-editor">
        <h2 class="blend-editor-title">Compose your portfolio</h2>
        <p class="card-intro">Choose strategy sleeves and target weights totaling 100%. The portfolio rebalances monthly using daily strategy returns.</p>
        <div class="blend-grid">__BLEND_CONTROLS__</div>
        <div class="blend-actions"><button id="equal-weight" type="button" class="secondary-button">Equal weight selected</button>
          <button id="apply-blend" type="button" class="primary-button">Apply blend</button>
          <button id="clear-blend" type="button" class="secondary-button">Clear blend</button>
          <span id="blend-total" class="muted" aria-live="polite">Selected: 0%</span></div>
        <p class="footnote">Strategy trading fees are included; transfers between strategy sleeves have no added cost.</p>
        <p id="blend-message" class="blend-message muted" aria-live="polite">Select strategies and set targets that total 100%.</p>
      </div>
    </div>
  </section>
  <div id="portfolio-results">
  <div id="selected-strategy" class="strategy-name">CPM</div>
  <section id="headline-metrics" class="grid metrics"></section>
  <section class="grid two-col">
    <article class="card"><h2>Latest target allocation</h2>
      <p id="target-date-label" class="card-intro"></p><div id="target-positions" class="position-grid"></div></article>
    <article class="card"><h2>Target changes vs. prior month</h2>
      <p id="target-change-label" class="card-intro"></p>
      <div class="table-wrap"><table><thead><tr><th>Action / asset</th><th>Prior</th><th>Target</th><th>Change</th></tr></thead>
      <tbody id="target-trades"></tbody></table></div>
      <p class="footnote">Changes are percentage points of portfolio target weight, not share quantities.</p>
    </article>
  </section>
  <section class="card chart-card">
    <div class="chart-head"><div><h2>Cumulative return</h2><p class="card-intro">TAA strategies compared with SPY and annually rebalanced 60/40</p></div>
      <label class="muted" for="timeframe">Range&nbsp; <select class="range-select" id="timeframe"><option value="all">All</option><option value="10">10 years</option><option value="5">5 years</option><option value="3">3 years</option><option value="1">1 year</option></select></label>
    </div>
    <div id="equity-chart" class="echart" role="img" aria-label="Cumulative return chart"></div>
  </section>
  <section class="card chart-card">
    <div class="chart-head"><div><h2>Rolling 3-month maximum drawdown</h2><p class="card-intro">Worst peak-to-trough decline over the trailing 63 trading days</p></div></div>
    <div id="drawdown-chart" class="echart" role="img" aria-label="Drawdown chart"></div>
  </section>
  <section class="card performance">
    <div class="chart-head"><div><h2>Performance summary</h2><p class="card-intro">Same selected period and transaction-cost assumption for all portfolios</p></div>
      <label class="muted" for="performance-timeframe">Range&nbsp; <select class="range-select" id="performance-timeframe"><option value="all">All</option><option value="10">10 years</option><option value="5">5 years</option><option value="3">3 years</option><option value="1">1 year</option></select></label>
    </div>
    <div class="table-wrap"><table><thead><tr><th>Portfolio</th><th>Total return</th><th>CAGR</th><th>Volatility</th><th>Sharpe</th><th>Max drawdown</th></tr></thead><tbody id="performance-rows">__PERFORMANCE_ROWS__</tbody></table></div>
  </section>
  <p class="footnote">__PERIOD__ · __FEE__ bps per side · Source prices are not included in this dashboard.</p>
  </div>
</main>
<script src="https://cdn.jsdelivr.net/npm/echarts@6.1.0/dist/echarts.min.js"></script>
<script>
  const selectors = [document.getElementById('timeframe'), document.getElementById('performance-timeframe')];
  const basePortfolioSeries = __CHART_DATA__;
  let portfolioSeries = basePortfolioSeries.slice();
  const performanceByRange = __PERFORMANCE_DATA__;
  const strategyTargetState = __BLEND_TARGET_STATE__;
  const strategyNames = __STRATEGIES__;
  const rebalanceDates = new Set(__REBALANCE_DATES__);
  const blendFeeBps = Number(__FEE__);
  let firstDate = 0;
  let lastDate = 0;
  let selectedStrategy = 'CPM';
  let activeBlendTargetState = null;
  function updateBounds() {
    const starts = portfolioSeries.map(item => Date.parse(item.dates[0] + 'T00:00:00Z'));
    const ends = portfolioSeries.map(item => Date.parse(item.dates[item.dates.length - 1] + 'T00:00:00Z'));
    firstDate = Math.min(...starts);
    lastDate = Math.max(...ends);
  }
  updateBounds();
  const equityChart = echarts.init(document.getElementById('equity-chart'), null, {useCoarsePointer: true, pointerSize: 44});
  const drawdownChart = echarts.init(document.getElementById('drawdown-chart'), null, {useCoarsePointer: true, pointerSize: 44});
  equityChart.group = 'cpm-performance';
  drawdownChart.group = 'cpm-performance';
  echarts.connect('cpm-performance');

  function rebaseSeries(start, end, drawdown) {
    return portfolioSeries.map(item => {
      const dates = item.dates.map(date => Date.parse(date + 'T00:00:00Z'));
      let firstVisible = dates.findIndex(date => date >= start);
      if (firstVisible < 0) firstVisible = dates.length - 1;
      const base = item.values[firstVisible];
      let peak = Number.NEGATIVE_INFINITY;
      const rollingDrawdown = drawdown ? item.values.map((value, index) => {
        const windowStart = Math.max(0, index - 62);
        let windowPeak = Number.NEGATIVE_INFINITY;
        let worst = 0;
        for (let cursor = windowStart; cursor <= index; cursor += 1) {
          windowPeak = Math.max(windowPeak, item.values[cursor]);
          worst = Math.min(worst, item.values[cursor] / windowPeak - 1);
        }
        return worst * 100;
      }) : null;
      return {
        id: item.name,
        name: item.name,
        type: 'line',
        showSymbol: false,
        connectNulls: false,
        data: dates.map((date, index) => {
          const value = item.values[index];
          if (date < start || date > end) return [date, null];
          if (!drawdown) return [date, value / base];
          peak = Math.max(peak, value);
          return [date, rollingDrawdown[index]];
        }),
        lineStyle: {color: item.color, width: item.name === selectedStrategy ? 3.2 : 1.7, opacity: item.name === selectedStrategy ? 1 : 0.82},
        itemStyle: {color: item.color, opacity: item.name === selectedStrategy ? 1 : 0.82},
        emphasis: {focus: 'series'}
      };
    });
  }

  function equityYAxis(start, end) {
    let minMultiple = 1;
    let maxMultiple = 1;
    portfolioSeries.forEach(item => {
      const dates = item.dates.map(date => Date.parse(date + 'T00:00:00Z'));
      const firstVisible = dates.findIndex(date => date >= start && date <= end);
      if (firstVisible < 0) return;
      const base = item.values[firstVisible];
      item.values.forEach((value, index) => {
        if (dates[index] < start || dates[index] > end) return;
        const multiple = value / base;
        minMultiple = Math.min(minMultiple, multiple);
        maxMultiple = Math.max(maxMultiple, multiple);
      });
    });
    const minExponent = Math.min(0, Math.log10(minMultiple));
    const maxExponent = Math.max(0, Math.log10(maxMultiple));
    const padding = Math.max(0.06, (maxExponent - minExponent) * 0.08);
    return {
      type: 'log',
      logBase: 10,
      min: Math.pow(10, minExponent - padding),
      max: Math.pow(10, maxExponent + padding),
      axisLabel: {formatter: value => {
        const percent = (Number(value) - 1) * 100;
        return `${percent > 0 ? '+' : ''}${percent.toFixed(0)}%`;
      }},
      splitLine: {lineStyle: {color: '#e8edf2'}}
    };
  }

  const baseOption = {
    animation: false,
    color: portfolioSeries.map(item => item.color),
    grid: {left: 54, right: 18, top: 44, bottom: 66},
    legend: {top: 4, left: 8, itemWidth: 16, itemHeight: 3, textStyle: {fontSize: 12}},
    tooltip: {trigger: 'axis', axisPointer: {type: 'cross'}, confine: true},
    xAxis: {type: 'time', boundaryGap: false, axisLabel: {hideOverlap: true}, splitLine: {show: false}},
    dataZoom: [
      {id: 'shared-inside', type: 'inside', xAxisIndex: 0, filterMode: 'none', zoomOnMouseWheel: false, moveOnMouseMove: false, moveOnMouseWheel: false},
      {id: 'shared-slider', type: 'slider', xAxisIndex: 0, filterMode: 'none', show: false}
    ]
  };
  const equityOption = {
    ...baseOption,
    tooltip: {...baseOption.tooltip, valueFormatter: value => `${((Number(value) - 1) * 100).toFixed(2)}%`},
    yAxis: equityYAxis(firstDate, lastDate),
    series: rebaseSeries(firstDate, lastDate, false)
  };
  const drawdownOption = {
    ...baseOption,
    tooltip: {...baseOption.tooltip, valueFormatter: value => `${Number(value).toFixed(2)}%`},
    dataZoom: [
      {id: 'shared-inside', type: 'inside', xAxisIndex: 0, filterMode: 'none', zoomOnMouseWheel: false, moveOnMouseMove: false, moveOnMouseWheel: false},
      {id: 'shared-slider', type: 'slider', xAxisIndex: 0, filterMode: 'none', show: false}
    ],
    legend: {show: false},
    grid: {left: 54, right: 18, top: 14, bottom: 40},
    yAxis: {type: 'value', scale: true, axisLabel: {formatter: value => `${Number(value).toFixed(0)}%`}, splitLine: {lineStyle: {color: '#e8edf2'}}},
    series: rebaseSeries(firstDate, lastDate, true)
  };
  equityChart.setOption(equityOption);
  drawdownChart.setOption(drawdownOption);

  function updateRange(start, end) {
    equityChart.setOption({yAxis: equityYAxis(start, end), series: rebaseSeries(start, end, false)}, {replaceMerge: ['series']});
    drawdownChart.setOption({series: rebaseSeries(start, end, true)}, {replaceMerge: ['series']});
  }
  let activeBlend = null;
  let portfolioMode = 'single';
  let lastSingleStrategy = 'CPM';
  let blendEditing = false;
  let savedBlendDefinition = [];
  function renderPerformance(range) {
    const tbody = document.getElementById('performance-rows');
    const rows = [...(performanceByRange[range] ?? performanceByRange.all)];
    if (activeBlend) {
      const dates = activeBlend.dates.map(date => Date.parse(date + 'T00:00:00Z'));
      const cutoff = range === 'all' ? dates[0] : (() => {
        const date = new Date(lastDate);
        date.setUTCFullYear(date.getUTCFullYear() - Number(range));
        return date.getTime();
      })();
      let startIndex = dates.findIndex(date => date >= cutoff);
      if (startIndex < 0) startIndex = dates.length - 1;
      const values = activeBlend.values.slice(startIndex);
      const periodDates = dates.slice(startIndex);
      if (values.length > 1) {
        const returns = values.slice(1).map((value, index) => value / values[index] - 1);
        const mean = returns.reduce((sum, value) => sum + value, 0) / returns.length;
        const variance = returns.reduce((sum, value) => sum + (value - mean) ** 2, 0) / (returns.length - 1);
        const volatility = Math.sqrt(variance * 252);
        const years = Math.max((periodDates[periodDates.length - 1] - periodDates[0]) / (365.25 * 86400000), 1 / 365.25);
        let peak = values[0];
        let maxDrawdown = 0;
        values.forEach(value => { peak = Math.max(peak, value); maxDrawdown = Math.min(maxDrawdown, value / peak - 1); });
        rows.push({
          name: activeBlend.name,
          total_return: values[values.length - 1] / values[0] - 1,
          cagr: (values[values.length - 1] / values[0]) ** (1 / years) - 1,
          volatility,
          sharpe: variance > 0 ? mean / Math.sqrt(variance) * Math.sqrt(252) : 0,
          max_drawdown: maxDrawdown,
        });
      }
    }
    tbody.replaceChildren(...rows.map(row => {
      const tr = document.createElement('tr');
      const values = [row.name, `${(row.total_return * 100).toFixed(1)}%`, `${(row.cagr * 100).toFixed(1)}%`, `${(row.volatility * 100).toFixed(1)}%`, row.sharpe.toFixed(2), `${(row.max_drawdown * 100).toFixed(1)}%`];
      values.forEach((value, index) => {
        const cell = document.createElement(index === 0 ? 'th' : 'td');
        cell.textContent = value;
        tr.appendChild(cell);
      });
      return tr;
    }));
    renderHeadline(selectedStrategy, range);
  }

  function percent(value) { return `${(Number(value) * 100).toFixed(1)}%`; }
  function renderPositionsAndChanges(state, strategyName) {
    const positions = document.getElementById('target-positions');
    const current = state?.current ?? {};
    const previous = state?.previous ?? {};
    const positionRows = Object.entries(current).filter(([, weight]) => weight > 1e-8).sort((a,b) => b[1] - a[1]).map(([ticker, weight]) => {
      const row = document.createElement('div'); row.className = 'position';
      const label = document.createElement('span'); label.textContent = ticker;
      const value = document.createElement('strong'); value.textContent = percent(weight);
      row.append(label, value); return row;
    });
    if (!positionRows.length) {
      const empty = document.createElement('p'); empty.className = 'muted'; empty.textContent = 'No active target weights.'; positionRows.push(empty);
    }
    positions.replaceChildren(...positionRows);
    const changes = [...new Set([...Object.keys(current), ...Object.keys(previous)])].map(ticker => ({
      ticker, before: previous[ticker] || 0, after: current[ticker] || 0,
      delta: (current[ticker] || 0) - (previous[ticker] || 0),
    })).filter(item => Math.abs(item.delta) > 1e-6).sort((a,b) => Math.abs(b.delta) - Math.abs(a.delta));
    const tbody = document.getElementById('target-trades');
    if (!changes.length) {
      const row = document.createElement('tr'); const cell = document.createElement('td');
      cell.colSpan = 4; cell.className = 'muted'; cell.textContent = 'No target-weight changes from the prior month.';
      row.append(cell); tbody.replaceChildren(row);
    } else tbody.replaceChildren(...changes.map(item => {
      const row = document.createElement('tr'); const actionCell = document.createElement('td');
      const action = item.before <= 1e-8 ? 'Buy' : item.after <= 1e-8 ? 'Exit' : item.delta > 0 ? 'Increase' : 'Reduce';
      const badge = document.createElement('span'); badge.className = `action ${item.delta > 0 ? 'buy' : 'sell'}`; badge.textContent = action;
      actionCell.append(badge, document.createTextNode(` ${item.ticker}`));
      const priorCell = document.createElement('td'); priorCell.textContent = percent(item.before);
      const targetCell = document.createElement('td'); targetCell.textContent = percent(item.after);
      const deltaCell = document.createElement('td'); deltaCell.className = `delta ${item.delta > 0 ? 'buy' : 'sell'}`; deltaCell.textContent = `${item.delta > 0 ? '+' : ''}${percent(item.delta)}`;
      row.append(actionCell, priorCell, targetCell, deltaCell); return row;
    }));
    document.getElementById('target-date-label').textContent = `Latest ${strategyName} targets · ${state?.current_date ?? 'unavailable'}.`;
    document.getElementById('target-change-label').textContent = `Target changes since ${state?.previous_date ?? 'the prior signal'} · ${state?.current_date ?? 'unavailable'}.`;
  }

  function blendMetrics(range) {
    if (!activeBlend) return null;
    const dates = activeBlend.dates.map(date => Date.parse(date + 'T00:00:00Z'));
    const cutoff = range === 'all' ? dates[0] : (() => { const date = new Date(lastDate); date.setUTCFullYear(date.getUTCFullYear() - Number(range)); return date.getTime(); })();
    let startIndex = dates.findIndex(date => date >= cutoff); if (startIndex < 0) startIndex = dates.length - 1;
    const values = activeBlend.values.slice(startIndex); const periodDates = dates.slice(startIndex);
    if (values.length < 2) return null;
    const returns = values.slice(1).map((value, index) => value / values[index] - 1);
    const mean = returns.reduce((sum, value) => sum + value, 0) / returns.length;
    const variance = returns.length > 1 ? returns.reduce((sum, value) => sum + (value - mean) ** 2, 0) / (returns.length - 1) : 0;
    const volatility = Math.sqrt(variance * 252);
    const years = Math.max((periodDates.at(-1) - periodDates[0]) / (365.25 * 86400000), 1 / 365.25);
    let peak = values[0]; let maxDrawdown = 0;
    values.forEach(value => { peak = Math.max(peak, value); maxDrawdown = Math.min(maxDrawdown, value / peak - 1); });
    return {name: 'My blend', total_return: values.at(-1) / values[0] - 1,
      cagr: (values.at(-1) / values[0]) ** (1 / years) - 1, volatility,
      sharpe: variance > 0 ? mean / Math.sqrt(variance) * Math.sqrt(252) : 0, max_drawdown: maxDrawdown};
  }

  function renderHeadline(name, range) {
    const row = name === 'My blend' ? blendMetrics(range) : (performanceByRange[range] ?? performanceByRange.all).find(item => item.name === name);
    document.getElementById('selected-strategy').textContent = name;
    const cards = row ? [['CAGR', percent(row.cagr)], ['Total return', percent(row.total_return)], ['Max drawdown', percent(row.max_drawdown)], ['Sharpe', Number(row.sharpe).toFixed(2)]] : [];
    document.getElementById('headline-metrics').replaceChildren(...cards.map(([label, value]) => {
      const card = document.createElement('div'); card.className = 'metric';
      const title = document.createElement('span'); title.textContent = `${label} · ${range === 'all' ? 'All time' : `Last ${range}y`}`;
      const metric = document.createElement('strong'); metric.textContent = value; card.append(title, metric); return card;
    }));
    const state = name === 'My blend' ? activeBlendTargetState : strategyTargetState[name];
    renderPositionsAndChanges(state, name);
  }

  const strategySelect = document.getElementById('strategy-select');
  let rememberedStrategy = null;
  let rememberedMode = 'single';
  try {
    rememberedStrategy = localStorage.getItem('taa-selected-strategy');
    rememberedMode = localStorage.getItem('taa-portfolio-mode') || 'single';
    const parsedBlend = JSON.parse(localStorage.getItem('taa-blend-targets') || '[]');
    savedBlendDefinition = Array.isArray(parsedBlend) ? parsedBlend : [];
  } catch (_) { savedBlendDefinition = []; }
  if (strategyNames.includes(rememberedStrategy)) strategySelect.value = rememberedStrategy;
  lastSingleStrategy = strategySelect.value;
  selectedStrategy = lastSingleStrategy;
  if (Array.isArray(savedBlendDefinition)) savedBlendDefinition.forEach(leg => {
    const checkbox = document.querySelector(`.blend-enabled[data-strategy="${leg.name}"]`);
    const input = document.querySelector(`.blend-weight[data-strategy="${leg.name}"]`);
    if (checkbox && input && Number.isFinite(Number(leg.weight))) {
      checkbox.checked = true; input.disabled = false; input.value = String(Math.round(Number(leg.weight) * 100));
    }
  });
  function refreshPortfolioPanel() {
    const isBlend = portfolioMode === 'blend';
    document.getElementById('single-controls').hidden = isBlend;
    document.getElementById('blend-controls-panel').hidden = !isBlend;
    document.getElementById('mode-single').setAttribute('aria-pressed', String(!isBlend));
    document.getElementById('mode-blend').setAttribute('aria-pressed', String(isBlend));
    const hasBlend = Boolean(activeBlend);
    document.getElementById('blend-summary').hidden = !isBlend || !hasBlend || blendEditing;
    document.getElementById('blend-editor').hidden = !isBlend || (hasBlend && !blendEditing);
    document.getElementById('portfolio-results').hidden = isBlend && !hasBlend;
    selectedStrategy = isBlend ? 'My blend' : lastSingleStrategy;
    if (hasBlend) document.getElementById('blend-summary-value').textContent = savedBlendDefinition.map(leg => `${leg.name} ${Math.round(leg.weight * 100)}%`).join(' · ');
  }
  function setPortfolioMode(mode) {
    portfolioMode = mode;
    blendEditing = false;
    try { localStorage.setItem('taa-portfolio-mode', mode); } catch (_) {}
    refreshPortfolioPanel();
    if (!(mode === 'blend' && !activeBlend)) {
      updateRange(firstDate, lastDate);
      renderHeadline(selectedStrategy, document.getElementById('performance-timeframe').value);
      equityChart.resize(); drawdownChart.resize();
    }
  }
  document.getElementById('mode-single').addEventListener('click', () => setPortfolioMode('single'));
  document.getElementById('mode-blend').addEventListener('click', () => setPortfolioMode('blend'));
  strategySelect.addEventListener('change', () => {
    lastSingleStrategy = strategySelect.value;
    selectedStrategy = lastSingleStrategy;
    try { localStorage.setItem('taa-selected-strategy', lastSingleStrategy); } catch (_) {}
    updateRange(firstDate, lastDate);
    renderHeadline(selectedStrategy, document.getElementById('performance-timeframe').value);
  });
  document.getElementById('edit-blend').addEventListener('click', () => {
    blendEditing = true;
    refreshPortfolioPanel();
  });

  function applyBlend(restoring = false) {
    const chosen = [...document.querySelectorAll('.blend-enabled:checked')].map(checkbox => {
      const weightInput = document.querySelector(`.blend-weight[data-strategy="${checkbox.dataset.strategy}"]`);
      return {name: checkbox.dataset.strategy, weight: Number(weightInput.value) / 100};
    });
    const total = chosen.reduce((sum, item) => sum + item.weight, 0);
    const message = document.getElementById('blend-message');
    if (!chosen.length || chosen.some(item => !Number.isFinite(item.weight) || item.weight < 0) || Math.abs(total - 1) > 0.0001) {
      message.textContent = 'Select one or more strategies and set their targets to exactly 100%.';
      message.style.color = '#a94a4a';
      return;
    }
    const legs = chosen.map(item => ({
      ...item,
      series: basePortfolioSeries.find(series => series.name === item.name),
    }));
    const maps = legs.map(leg => new Map(leg.series.dates.map((date, index) => [date, leg.series.values[index]])));
    const firstDateByLeg = legs.map(leg => Date.parse(leg.series.dates[0] + 'T00:00:00Z'));
    const lastDateByLeg = legs.map(leg => Date.parse(leg.series.dates[leg.series.dates.length - 1] + 'T00:00:00Z'));
    const commonStart = Math.max(...firstDateByLeg);
    const commonEnd = Math.min(...lastDateByLeg);
    const dates = legs[0].series.dates.filter(date => {
      const timestamp = Date.parse(date + 'T00:00:00Z');
      return timestamp >= commonStart && timestamp <= commonEnd && maps.every(map => map.has(date));
    });
    if (dates.length < 2) {
      message.textContent = 'The selected strategies do not have enough shared history to blend.';
      message.style.color = '#a94a4a';
      return;
    }
    let sleeveValues = legs.map(leg => 100000 * leg.weight);
    const values = [100000];
    for (let index = 1; index < dates.length; index += 1) {
      const priorDate = dates[index - 1];
      const date = dates[index];
      legs.forEach((leg, legIndex) => {
        const prior = maps[legIndex].get(priorDate);
        const current = maps[legIndex].get(date);
        sleeveValues[legIndex] *= current / prior;
      });
      const totalValue = sleeveValues.reduce((sum, value) => sum + value, 0);
      if (rebalanceDates.has(date)) {
        sleeveValues = legs.map(leg => totalValue * leg.weight);
      }
      values.push(totalValue);
    }
    activeBlend = {name: 'My blend', color: '#d24f78', dates, values};
    savedBlendDefinition = chosen.map(leg => ({name: leg.name, weight: leg.weight}));
    if (!restoring) {
      portfolioMode = 'blend';
      try {
        localStorage.setItem('taa-blend-targets', JSON.stringify(savedBlendDefinition));
        localStorage.setItem('taa-portfolio-mode', 'blend');
      } catch (_) {}
    }
    blendEditing = false;
    refreshPortfolioPanel();
    selectedStrategy = portfolioMode === 'blend' ? 'My blend' : lastSingleStrategy;
    renderBlendHoldings(chosen);
    portfolioSeries = [...basePortfolioSeries, activeBlend];
    updateBounds();
    const selectedRange = document.getElementById('timeframe').value;
    if (selectedRange === 'all') updateRange(firstDate, lastDate);
    else {
      const start = new Date(lastDate);
      start.setUTCFullYear(start.getUTCFullYear() - Number(selectedRange));
      updateRange(start.getTime(), lastDate);
    }
    renderPerformance(document.getElementById('performance-timeframe').value);
    message.textContent = `Blend applied over ${dates[0]} to ${dates[dates.length - 1]}. Strategy-level fees are included; sleeve transfers have no added cost.`;
    message.style.color = 'var(--muted)';
  }

  function refreshBlendTotal() {
    const total = [...document.querySelectorAll('.blend-enabled:checked')].reduce((sum, checkbox) => {
      const input = document.querySelector(`.blend-weight[data-strategy="${checkbox.dataset.strategy}"]`);
      return sum + (Number(input.value) || 0);
    }, 0);
    document.getElementById('blend-total').textContent = `Selected: ${total.toFixed(0)}%`;
  }
  function renderBlendHoldings(chosen) {
    const current = {};
    const previous = {};
    const currentDates = [];
    const previousDates = [];
    chosen.forEach(leg => {
      const state = strategyTargetState[leg.name];
      if (!state) return;
      currentDates.push(state.current_date);
      if (state.previous_date) previousDates.push(state.previous_date);
      Object.entries(state.current).forEach(([ticker, weight]) => { current[ticker] = (current[ticker] || 0) + leg.weight * weight; });
      Object.entries(state.previous).forEach(([ticker, weight]) => { previous[ticker] = (previous[ticker] || 0) + leg.weight * weight; });
    });
    const currentDate = currentDates.sort().at(-1) || 'unavailable';
    const previousDate = previousDates.sort().at(-1) || 'unavailable';
    activeBlendTargetState = {current, previous, current_date: currentDate, previous_date: previousDate};
  }
  document.querySelectorAll('.blend-enabled').forEach(checkbox => checkbox.addEventListener('change', () => {
    document.querySelector(`.blend-weight[data-strategy="${checkbox.dataset.strategy}"]`).disabled = !checkbox.checked;
    refreshBlendTotal();
  }));
  document.querySelectorAll('.blend-weight').forEach(input => input.addEventListener('input', refreshBlendTotal));
  document.getElementById('equal-weight').addEventListener('click', () => {
    let selected = [...document.querySelectorAll('.blend-enabled:checked')];
    if (!selected.length) {
      document.querySelectorAll('.blend-enabled').forEach(checkbox => { checkbox.checked = true; });
      selected = [...document.querySelectorAll('.blend-enabled:checked')];
    }
    const baseWeight = Math.floor(100 / selected.length);
    const remainder = 100 - baseWeight * selected.length;
    selected.forEach((checkbox, index) => {
      const input = document.querySelector(`.blend-weight[data-strategy="${checkbox.dataset.strategy}"]`);
      input.disabled = false;
      input.value = baseWeight + (index < remainder ? 1 : 0);
    });
    refreshBlendTotal();
  });
  document.getElementById('apply-blend').addEventListener('click', () => applyBlend(false));
  document.getElementById('clear-blend').addEventListener('click', () => {
    activeBlend = null;
    activeBlendTargetState = null;
    savedBlendDefinition = [];
    blendEditing = false;
    portfolioMode = 'single';
    selectedStrategy = lastSingleStrategy;
    document.querySelectorAll('.blend-enabled').forEach(checkbox => { checkbox.checked = false; });
    document.querySelectorAll('.blend-weight').forEach(input => { input.value = '0'; input.disabled = true; });
    try { localStorage.removeItem('taa-blend-targets'); localStorage.setItem('taa-portfolio-mode', 'single'); } catch (_) {}
    refreshPortfolioPanel();
    portfolioSeries = basePortfolioSeries.slice();
    updateBounds();
    const range = document.getElementById('timeframe').value;
    if (range === 'all') updateRange(firstDate, lastDate);
    else {
      const start = new Date(lastDate);
      start.setUTCFullYear(start.getUTCFullYear() - Number(range));
      updateRange(start.getTime(), lastDate);
    }
    renderPerformance(document.getElementById('performance-timeframe').value);
    document.getElementById('blend-message').textContent = 'Blend cleared. Select strategies and set targets that total 100%.';
    document.getElementById('blend-message').style.color = 'var(--muted)';
  });

  function applyTimeframe(range) {
    selectors.forEach(select => { select.value = range; });
    renderPerformance(range);
    if (range === 'all') {
      equityChart.dispatchAction({type: 'dataZoom', dataZoomId: 'shared-slider', start: 0, end: 100});
      drawdownChart.dispatchAction({type: 'dataZoom', dataZoomId: 'shared-slider', start: 0, end: 100});
      updateRange(firstDate, lastDate);
      return;
    }
    const start = new Date(lastDate);
    start.setUTCFullYear(start.getUTCFullYear() - Number(range));
    const startValue = start.getTime();
    equityChart.dispatchAction({type: 'dataZoom', dataZoomId: 'shared-slider', startValue, endValue: lastDate});
    drawdownChart.dispatchAction({type: 'dataZoom', dataZoomId: 'shared-slider', startValue, endValue: lastDate});
    updateRange(startValue, lastDate);
  }
  selectors.forEach(select => select.addEventListener('change', () => applyTimeframe(select.value)));
  portfolioMode = rememberedMode === 'blend' ? 'blend' : 'single';
  refreshPortfolioPanel();
  if (savedBlendDefinition.length) {
    refreshBlendTotal();
    applyBlend(true);
  } else {
    updateRange(firstDate, lastDate);
    renderPerformance(document.getElementById('performance-timeframe').value);
  }
  window.addEventListener('resize', () => { equityChart.resize(); drawdownChart.resize(); });
</script>
</body>
</html>'''
    replacements = {
        "__AS_OF__": escape(as_of.strftime("%d %b %Y")),
        "__BUILT_AT__": escape(built_at),
        "__BLEND_CONTROLS__": blend_controls,
        "__BLEND_TARGET_STATE__": blend_target_state_json,
        "__CHART_DATA__": chart_data_json,
        "__REBALANCE_DATES__": rebalance_dates_json,
        "__PERFORMANCE_DATA__": performance_data_json,
        "__STRATEGIES__": strategies_json,
        "__PERFORMANCE_ROWS__": "".join(performance_rows),
        "__PERIOD__": escape(f'{metrics.attrs.get("start", "")} {metrics.attrs.get("end", "")}'.strip())
        if metrics.attrs.get("start") else escape(f"{prices.index[0]:%d %b %Y} – {as_of:%d %b %Y}"),
        "__FEE__": f"{fee_bps:g}",
    }
    for key, value in replacements.items():
        html = html.replace(key, value)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    return output_path
