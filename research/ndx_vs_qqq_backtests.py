
import pandas as pd
import numpy as np
from pathlib import Path
from cpm_live import load_panel, run_cpm_backtest, perf_metrics, sig_13612U
from bull_qqq_live import run_bull_qqq_backtest, compute_bull_qqq_weights, CASH_TICKER, SAFE_POOL, _pick_safe
from ndx_sleeve_live import load_ndx_panel, run_ndx_backtest
import ndx_sleeve_live

def run_bull_gated_qqq_backtest(panel, start, end, cost_bps=10.0):
    daily_rets = panel.ffill().pct_change()
    monthly_idx = pd.DataFrame({'x': 1}, index=panel.index).groupby(pd.Grouper(freq='ME')).tail(1)
    sigs = monthly_idx.index[(monthly_idx.index >= start) & (monthly_idx.index <= end)].tolist()

    common = panel.index[(panel.index >= start) & (panel.index <= end)]
    all_tickers = {'QQQ', CASH_TICKER, *SAFE_POOL}
    weights_per_day = {t: pd.Series(0.0, index=common) for t in all_tickers}

    for i, sig_d in enumerate(sigs):
        # Determine if BULL is active (holding SPY)
        bull_weights, _, _ = compute_bull_qqq_weights(panel, sig_d)
        bull_active = any(w > 0 for t, w in bull_weights.items() if t == 'SPY')
        
        if bull_active:
            month_weights = {'QQQ': 1.0}
        else:
            cpm_monthly = panel.loc[:sig_d].resample('ME').last()
            safe = _pick_safe(cpm_monthly)
            month_weights = {safe: 1.0}

        future = common[common > sig_d]
        if len(future) < 1:
            continue
        apply_from = future[0]
        if i + 1 < len(sigs):
            ns = sigs[i + 1]
            nf = common[common > ns]
            end_apply = nf[0] if len(nf) >= 1 else common[-1]
        else:
            end_apply = common[-1] + pd.Timedelta(days=1)
        
        mask = (common >= apply_from) & (common < end_apply)
        for t, w in month_weights.items():
            if t in weights_per_day:
                weights_per_day[t].loc[mask] = w

    # Calculate returns
    sleeve_rets = pd.Series(0.0, index=common)
    cur_w = {CASH_TICKER: 1.0}
    
    # Track turnover for cost calculation
    for ts in common:
        new_w = {t: weights_per_day[t].loc[ts] for t in all_tickers if weights_per_day[t].loc[ts] > 0}
        if not new_w:
            new_w = {CASH_TICKER: 1.0}
        if cur_w != new_w:
            tovr = sum(abs(cur_w.get(a, 0) - new_w.get(a, 0)) for a in set(cur_w) | set(new_w))
            sleeve_rets.loc[ts] -= tovr * cost_bps / 10000.0
        cur_w = new_w
        
        # Calculate asset return contribution
        prev_loc = panel.index.get_loc(ts)
        if prev_loc == 0:
            continue
        prev_d = panel.index[prev_loc - 1]
        port_r = 0.0
        for asset, w in cur_w.items():
            today = panel.loc[ts, asset]
            yest = panel.loc[prev_d, asset]
            if pd.notna(today) and pd.notna(yest) and yest > 0:
                port_r += w * (today / yest - 1)
        sleeve_rets.loc[ts] += port_r
        
    return sleeve_rets

print('Backtest helper loaded.')


def format_perf(metrics):
    return {
        'CAGR': f"{metrics['cagr'] * 100:.2f}%",
        'Vol': f"{metrics['vol'] * 100:.2f}%",
        'Raw Sharpe': f"{metrics['sharpe']:.3f}",
        'Excess Sharpe': f"{metrics['excess_sharpe']:.3f}",
        'MaxDD': f"{metrics['max_drawdown'] * 100:.2f}%",
        'Calmar': f"{metrics['calmar']:.3f}"
    }

def print_table(title, results):
    print(f"\n{title}")
    print("=" * len(title))
    print(f"{'_Sleeve/Blend_':<25} | {'CAGR':<8} | {'Vol':<8} | {'Raw SR':<8} | {'Ex SR':<8} | {'MaxDD':<8} | {'Calmar':<8}")
    print("-" * 85)
    for name, m in results.items():
        fmt = format_perf(m)
        print(f"{name:<25} | {fmt['CAGR']:<8} | {fmt['Vol']:<8} | {fmt['Raw Sharpe']:<8} | {fmt['Excess Sharpe']:<8} | {fmt['MaxDD']:<8} | {fmt['Calmar']:<8}")

def run_all():
    start_clean = pd.Timestamp('2008-05-30')
    start_stress = pd.Timestamp('1999-03-10')
    end = pd.Timestamp('2026-05-22')

    panel_start = min(start_stress - pd.DateOffset(years=20), pd.Timestamp('1995-01-01'))
    print(f"Loading panel from {panel_start.date()} to {end.date()}...")
    panel = load_panel(start=panel_start, end=end)
    ndx_panel = load_ndx_panel()

    for label, start in [('CLEAN WINDOW (2008-05-30 to 2026-05-22)', start_clean), 
                         ('STRESS WINDOW (1999-03-10 to 2026-05-22)', start_stress)]:
        print(f"\n=== Running {label} ===")
        
        # 1. Component backtests
        cpm, _ = run_cpm_backtest(panel, start, end)
        bull_raw = run_bull_qqq_backtest(panel, start, end)
        ndx_raw, _ = run_ndx_backtest(panel, ndx_panel, start, end)
        qqq_gated_raw = run_bull_gated_qqq_backtest(panel, start, end)

        # Reindex to common index
        common = cpm.index.intersection(bull_raw.index).intersection(ndx_raw.index).intersection(qqq_gated_raw.index)
        cpm = cpm.reindex(common)
        bull_raw = bull_raw.reindex(common)
        ndx_raw = ndx_raw.reindex(common).fillna(0.0)
        qqq_gated_raw = qqq_gated_raw.reindex(common).fillna(0.0)

        # 2. Blend backtests
        # (A) PROD: 60% CPM + 20% BULL + 20% NDX
        blend_a = 0.60 * cpm + 0.20 * bull_raw + 0.20 * ndx_raw
        
        # (B) Alt: 60% CPM + 20% BULL + 20% BULL-gated QQQ
        blend_b = 0.60 * cpm + 0.20 * bull_raw + 0.20 * qqq_gated_raw

        cash_daily = panel['SHV'].ffill().pct_change().dropna()
        
        # Calculate performance
        m_cpm = perf_metrics(cpm, cash_daily)
        m_bull = perf_metrics(bull_raw, cash_daily)
        m_ndx = perf_metrics(ndx_raw, cash_daily)
        m_qqq_gated = perf_metrics(qqq_gated_raw, cash_daily)
        m_blend_a = perf_metrics(blend_a, cash_daily)
        m_blend_b = perf_metrics(blend_b, cash_daily)

        results = {
            'CPM Standalone': m_cpm,
            'BULL-SPY Standalone': m_bull,
            'NDX Sleeve (A)': m_ndx,
            'BULL-gated QQQ Sleeve (B)': m_qqq_gated,
            'PROD Blend (A)': m_blend_a,
            'Alt Blend (B)': m_blend_b,
        }
        print_table(f"{label} Results", results)

if __name__ == '__main__':
    run_all()
