
import pandas as pd
import numpy as np
from pathlib import Path
from cpm_live import load_panel, run_cpm_backtest, perf_metrics, sig_13612U
from bull_spy_live import run_bull_spy_backtest, compute_bull_spy_weights, CASH_TICKER, SAFE_POOL, _pick_safe
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
        bull_weights, _, _ = compute_bull_spy_weights(panel, sig_d)
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

    sleeve_rets = pd.Series(0.0, index=common)
    cur_w = {CASH_TICKER: 1.0}
    
    for ts in common:
        new_w = {t: weights_per_day[t].loc[ts] for t in all_tickers if weights_per_day[t].loc[ts] > 0}
        if not new_w:
            new_w = {CASH_TICKER: 1.0}
        if cur_w != new_w:
            tovr = sum(abs(cur_w.get(a, 0) - new_w.get(a, 0)) for a in set(cur_w) | set(new_w))
            sleeve_rets.loc[ts] -= tovr * cost_bps / 10000.0
        cur_w = new_w
        
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

def run_ndx_backtest_with_haircuts(
    cpm_panel, ndx_panel, start, end,
    cost_bps=10.0,
    dropped_haircut=0.0,
    blanket_annual_drag=0.0
):
    full_panel = cpm_panel.join(ndx_panel, how='outer', rsuffix='_dup')
    full_panel = full_panel.loc[:, ~full_panel.columns.str.endswith('_dup')]

    monthly_idx = pd.DataFrame({'x': 1}, index=full_panel.index).groupby(
        pd.Grouper(freq='ME')).tail(1).index
    sig_dates = monthly_idx[(monthly_idx >= start) & (monthly_idx <= end)]

    daily_rets = pd.Series(0.0, index=full_panel.loc[start:end].index)
    weights_for_date = {}

    from ndx_sleeve_live import compute_ndx_weights
    for sd in sig_dates:
        target, _, _ = compute_ndx_weights(cpm_panel, ndx_panel, sd)
        next_loc = full_panel.index.get_indexer([sd], method='bfill')[0] + 1
        if next_loc < len(full_panel.index):
            weights_for_date[full_panel.index[next_loc]] = target

    exec_dates = sorted(weights_for_date.keys())
    cur_w = {CASH_TICKER: 1.0}
    cur_w_idx = 0
    safe_tickers = {CASH_TICKER, 'SHV', 'IEF'}

    for ts in full_panel.loc[start:end].index:
        # Check rebalance
        rebalanced = False
        if cur_w_idx < len(exec_dates) and exec_dates[cur_w_idx] <= ts:
            new_w = weights_for_date[exec_dates[cur_w_idx]]
            rebalanced = True
            
            # 1. Rebalance transaction cost (tovr)
            if cur_w != new_w:
                tovr = sum(abs(cur_w.get(a, 0) - new_w.get(a, 0)) for a in set(cur_w) | set(new_w))
                daily_rets.loc[ts] -= tovr * cost_bps / 10000.0

                # 2. Dropped/reduced single-stock haircut
                if dropped_haircut > 0.0:
                    for asset, w_old in cur_w.items():
                        if asset not in safe_tickers:
                            w_new = new_w.get(asset, 0.0)
                            if w_old > w_new:
                                reduction = w_old - w_new
                                daily_rets.loc[ts] -= reduction * dropped_haircut

            cur_w = new_w
            cur_w_idx += 1

        prev_loc = full_panel.index.get_loc(ts)
        if prev_loc == 0:
            continue
        prev_d = full_panel.index[prev_loc - 1]
        market_open = full_panel.loc[ts].notna().sum() > full_panel.loc[ts].isna().sum()
        port_r = 0.0
        delisted_w = 0.0
        
        for asset, w in list(cur_w.items()):
            if asset not in full_panel.columns:
                delisted_w += w
                del cur_w[asset]
                continue
            today = full_panel.loc[ts, asset]
            yest = full_panel.loc[prev_d, asset]
            if pd.notna(today) and pd.notna(yest) and yest > 0:
                port_r += w * (today / yest - 1)
            elif market_open and pd.notna(yest) and yest > 0 and pd.isna(today):
                # Standard delisting haircut
                port_r += w * ndx_sleeve_live.DELISTING_HAIRCUT
                delisted_w += w
                del cur_w[asset]

        if delisted_w > 0:
            existing_safe = next((s for s in SAFE_POOL if s in cur_w), CASH_TICKER)
            cur_w[existing_safe] = cur_w.get(existing_safe, 0.0) + delisted_w
            if existing_safe in full_panel.columns:
                t_cash = full_panel.loc[ts, existing_safe]
                y_cash = full_panel.loc[prev_d, existing_safe]
                if pd.notna(t_cash) and pd.notna(y_cash) and y_cash > 0:
                    port_r += delisted_w * (t_cash / y_cash - 1)

        # Apply blanket annual drag if active
        if blanket_annual_drag > 0.0:
            # daily drag = (1 + blanket_annual_drag) ** (1/252) - 1
            daily_drag = (1.0 + blanket_annual_drag) ** (1.0/252.0) - 1.0
            # Apply to portion of portfolio in stocks (not in safe cash assets)
            stock_w = sum(w for a, w in cur_w.items() if a not in safe_tickers)
            port_r -= stock_w * daily_drag

        daily_rets.loc[ts] += port_r

    return daily_rets

print('Advanced backtest helper loaded successfully.')

import pandas as pd
import numpy as np

def run_sweeps():
    start_clean = pd.Timestamp('2008-05-30')
    start_stress = pd.Timestamp('1999-03-10')
    end = pd.Timestamp('2026-05-22')

    panel_start = min(start_stress - pd.DateOffset(years=20), pd.Timestamp('1995-01-01'))
    print(f'Loading panel from {panel_start.date()} to {end.date()}...')
    panel = load_panel(start=panel_start, end=end)
    ndx_panel = load_ndx_panel()

    cash_daily = panel['SHV'].ffill().pct_change().dropna()

    for w_name, start in [('CLEAN WINDOW (2008-05-30 to 2026-05-22)', start_clean), 
                           ('STRESS WINDOW (1999-03-10 to 2026-05-22)', start_stress)]:
        print(f'\n================================================================================')
        print(f'=== Sweeps for {w_name} ===')
        print(f'================================================================================')

        # 1. Base component runs
        cpm, _ = run_cpm_backtest(panel, start, end)
        bull_raw = run_bull_spy_backtest(panel, start, end)
        qqq_gated_raw = run_bull_gated_qqq_backtest(panel, start, end)

        # Reindex base components to common
        common = cpm.index.intersection(bull_raw.index).intersection(qqq_gated_raw.index)
        cpm = cpm.reindex(common)
        bull_raw = bull_raw.reindex(common)
        qqq_gated_raw = qqq_gated_raw.reindex(common).fillna(0.0)

        # Base Alt Blend (B) - always uses 10bps cost for QQQ
        blend_b = 0.60 * cpm + 0.20 * bull_raw + 0.20 * qqq_gated_raw
        m_b = perf_metrics(blend_b, cash_daily)

        print(f'Base Alt Blend (B) CAGR: {m_b["cagr"]*100:.2f}%, Sharpe: {m_b["sharpe"]:.3f}, ExSharpe: {m_b["excess_sharpe"]:.3f}, MaxDD: {m_b["max_drawdown"]*100:.2f}%')

        # --- Sweep 1: Extra Slippage on NDX ---
        print(f'\n--- Sweep 1: Extra Slippage on NDX (QQQ remains at base 10bps) ---')
        print(f'| Extra Bps | Total Bps/side | CAGR | Vol | Raw Sharpe | Excess Sharpe | MaxDD | CAGR Gap (A-B) | Sharpe Gap (A-B) |')
        print(f'|---|---|---|---|---|---|---|---|---|')
        
        # Base is 10bps (extra = 0)
        for extra in [0, 25, 50, 100]:
            total_bps = 10.0 + extra
            ndx_raw = run_ndx_backtest_with_haircuts(panel, ndx_panel, start, end, cost_bps=total_bps)
            common_a = common.intersection(ndx_raw.index)
            
            cpm_s = cpm.reindex(common_a)
            bull_s = bull_raw.reindex(common_a)
            ndx_s = ndx_raw.reindex(common_a).fillna(0.0)
            
            blend_a = 0.60 * cpm_s + 0.20 * bull_s + 0.20 * ndx_s
            m_a = perf_metrics(blend_a, cash_daily)
            
            cagr_gap = m_a['cagr'] - m_b['cagr']
            sharpe_gap = m_a['sharpe'] - m_b['sharpe']
            
            print(f'| {extra:+d} bps | {total_bps:.1f} bps | {m_a["cagr"]*100:.2f}% | {m_a["vol"]*100:.2f}% | {m_a["sharpe"]:.3f} | {m_a["excess_sharpe"]:.3f} | {m_a["max_drawdown"]*100:.2f}% | {cagr_gap*100:+.2f}% | {sharpe_gap:+.3f} |')

        # --- Sweep 2: Dropped/Reduced Name Haircut ---
        print(f'\n--- Sweep 2: Dropped/Reduced Name Haircut (on top of base 10bps) ---')
        print(f'| Haircut % | CAGR | Vol | Raw Sharpe | Excess Sharpe | MaxDD | CAGR Gap (A-B) | Sharpe Gap (A-B) |')
        print(f'|---|---|---|---|---|---|---|---|')
        
        for hc in [0.0, 0.01, 0.025, 0.05, 0.10]:
            ndx_raw = run_ndx_backtest_with_haircuts(panel, ndx_panel, start, end, cost_bps=10.0, dropped_haircut=hc)
            common_a = common.intersection(ndx_raw.index)
            
            cpm_s = cpm.reindex(common_a)
            bull_s = bull_raw.reindex(common_a)
            ndx_s = ndx_raw.reindex(common_a).fillna(0.0)
            
            blend_a = 0.60 * cpm_s + 0.20 * bull_s + 0.20 * ndx_s
            m_a = perf_metrics(blend_a, cash_daily)
            
            cagr_gap = m_a['cagr'] - m_b['cagr']
            sharpe_gap = m_a['sharpe'] - m_b['sharpe']
            
            print(f'| {hc*100:.1f}% | {m_a["cagr"]*100:.2f}% | {m_a["vol"]*100:.2f}% | {m_a["sharpe"]:.3f} | {m_a["excess_sharpe"]:.3f} | {m_a["max_drawdown"]*100:.2f}% | {cagr_gap*100:+.2f}% | {sharpe_gap:+.3f} |')

        # --- Sweep 3: Blanket Annual Drag on NDX ---
        print(f'\n--- Sweep 3: Blanket Annual Drag on NDX Sleeve (on top of base 10bps) ---')
        print(f'| Annual Drag % | CAGR | Vol | Raw Sharpe | Excess Sharpe | MaxDD | CAGR Gap (A-B) | Sharpe Gap (A-B) |')
        print(f'|---|---|---|---|---|---|---|---|')
        
        for drag in [0.0, 0.005, 0.01, 0.02, 0.03]:
            ndx_raw = run_ndx_backtest_with_haircuts(panel, ndx_panel, start, end, cost_bps=10.0, blanket_annual_drag=drag)
            common_a = common.intersection(ndx_raw.index)
            
            cpm_s = cpm.reindex(common_a)
            bull_s = bull_raw.reindex(common_a)
            ndx_s = ndx_raw.reindex(common_a).fillna(0.0)
            
            blend_a = 0.60 * cpm_s + 0.20 * bull_s + 0.20 * ndx_s
            m_a = perf_metrics(blend_a, cash_daily)
            
            cagr_gap = m_a['cagr'] - m_b['cagr']
            sharpe_gap = m_a['sharpe'] - m_b['sharpe']
            
            print(f'| {drag*100:.1f}% | {m_a["cagr"]*100:.2f}% | {m_a["vol"]*100:.2f}% | {m_a["sharpe"]:.3f} | {m_a["excess_sharpe"]:.3f} | {m_a["max_drawdown"]*100:.2f}% | {cagr_gap*100:+.2f}% | {sharpe_gap:+.3f} |')

if __name__ == '__main__':
    run_sweeps()
