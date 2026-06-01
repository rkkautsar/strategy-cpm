#!/usr/bin/env python3
import sys
import os
import pandas as pd
import numpy as np
from pathlib import Path

# Insert root directory into sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cpm_live as cpm
import bull_spy_live as bull_spy
import ndx_sleeve_live as ndx_sleeve
import build_dashboard as bd

# Configuration
CPM_W = 0.60
BULL_W = 0.20
NDX_W = 0.20

# We want to run backtests with signals starting from an earlier month-end so that
# under MOC we have valid weights for the first day of our clean window.
START_SIGNALS = pd.Timestamp("2007-12-31")
CLEAN_START = pd.Timestamp("2008-05-30")
CLEAN_END = pd.Timestamp("2026-05-22")

def run_cpm_backtest_with_offset(panel, start, end, offset, cost_bps=cpm.COST_BPS_PER_SIDE):
    cols = sorted(set(cpm.RISKY_UNIVERSE + cpm.SAFE_POOL + cpm.CANARY_ASSETS + [cpm.DEFAULT_CASH]) & set(panel.columns))
    close = panel[cols]
    
    monthly_idx = pd.DataFrame({"x": 1}, index=close.index).groupby(pd.Grouper(freq="ME")).tail(1)
    signal_dates = monthly_idx.index[(monthly_idx.index >= start) & (monthly_idx.index <= end)].tolist()
    
    weights_history = []
    for i, sig_d in enumerate(signal_dates):
        w, new_pair, regime, safe = cpm.compute_target_weights(close, sig_d)
        future = close.index[close.index > sig_d]
        if len(future) < offset:
            continue
        apply_from = future[offset - 1]
        if i + 1 < len(signal_dates):
            next_sig = signal_dates[i + 1]
            next_future = close.index[close.index > next_sig]
            end_apply = next_future[offset - 1] if len(next_future) >= offset else end
        else:
            end_apply = end
        weights_history.append({
            "apply_from": apply_from, "end_apply": end_apply,
            "weights": w, "sig_d": sig_d, "regime": regime, "safe": safe,
        })
    
    all_assets = sorted({a for h in weights_history for a in h["weights"]})
    df_w = pd.DataFrame(0.0, index=close.index, columns=[a for a in all_assets if a in close.columns])
    
    for h in weights_history:
        mask = (close.index >= h["apply_from"]) & (close.index < h["end_apply"])
        for a, ww in h["weights"].items():
            if a in df_w.columns:
                df_w.loc[mask, a] = ww
                
    daily_ret = close.ffill().pct_change()
    common = [a for a in df_w.columns if a in daily_ret.columns]
    raw_returns = (df_w[common] * daily_ret[common]).sum(axis=1, min_count=1).fillna(0.0)
    
    # Apply trade costs on T+1 (execution day)
    for i in range(len(weights_history)):
        prev_w = weights_history[i - 1]["weights"] if i > 0 else {}
        curr_w = weights_history[i]["weights"]
        keys = set(curr_w) | set(prev_w)
        turnover = sum(abs(curr_w.get(k, 0.0) - prev_w.get(k, 0.0)) for k in keys)
        cost = turnover * cost_bps / 10000.0
        sig_d = weights_history[i]["sig_d"]
        future = close.index[close.index > sig_d]
        if len(future) >= 1:
            t1 = future[0]
            if t1 in raw_returns.index:
                raw_returns.loc[t1] -= cost
                
    return raw_returns, weights_history

def run_bull_spy_backtest_with_offset(panel, start, end, offset, cost_bps=bull_spy.COST_BPS_PER_SIDE):
    if bull_spy.BULL_TICKER not in panel.columns:
        raise ValueError(f"{bull_spy.BULL_TICKER} not in panel")
    if bull_spy.CASH_TICKER not in panel.columns:
        raise ValueError(f"{bull_spy.CASH_TICKER} not in panel")

    daily_rets = panel.ffill().pct_change()
    monthly_idx = pd.DataFrame({"x": 1}, index=panel.index).groupby(pd.Grouper(freq="ME")).tail(1)
    sigs = monthly_idx.index[(monthly_idx.index >= start) & (monthly_idx.index <= end)].tolist()

    common = panel.index[(panel.index >= start) & (panel.index <= end)]
    all_tickers = {bull_spy.BULL_TICKER, bull_spy.CASH_TICKER, *bull_spy.SAFE_POOL}
    weights_per_day = {t: pd.Series(0.0, index=common) for t in all_tickers}
    state_per_day = pd.Series("", index=common, dtype=object)  # for cost calc

    for i, sig_d in enumerate(sigs):
        month_weights, _, _ = bull_spy.compute_bull_spy_weights(panel, sig_d, panel[bull_spy.BULL_TICKER])

        future = common[common > sig_d]
        if len(future) < offset:
            continue
        apply_from = future[offset - 1]
        if i + 1 < len(sigs):
            ns = sigs[i + 1]
            nf = common[common > ns]
            end_apply = nf[offset - 1] if len(nf) >= offset else common[-1]
        else:
            end_apply = common[-1] + pd.Timedelta(days=1)
        mask = (common >= apply_from) & (common < end_apply)
        for t, w in month_weights.items():
            if t in weights_per_day:
                weights_per_day[t].loc[mask] = w
        # Cost-tracking label: deterministic basket string
        label = "+".join(f"{t}:{w:.2f}" for t, w in sorted(month_weights.items()))
        state_per_day.loc[mask] = label

    # Compute returns: sum across all weighted positions
    port = pd.Series(0.0, index=common)
    for t, w_s in weights_per_day.items():
        if t in daily_rets.columns:
            port = port + daily_rets[t].reindex(common).fillna(0.0) * w_s

    # Switching costs on any weight change
    if cost_bps > 0:
        label_arr = state_per_day.values
        if len(label_arr) > 1:
            flips = np.where(label_arr[1:] != label_arr[:-1])[0] + 1
            for f in flips:
                port.iloc[f] -= 2.0 * cost_bps / 10000.0

    return port

def run_ndx_backtest_with_offset(cpm_panel, ndx_panel, start, end, offset, cost_bps=ndx_sleeve.COST_BPS_PER_SIDE):
    full_panel = cpm_panel.join(ndx_panel, how="outer", rsuffix="_dup")
    full_panel = full_panel.loc[:, ~full_panel.columns.str.endswith("_dup")]

    monthly_idx = pd.DataFrame({"x": 1}, index=full_panel.index).groupby(
        pd.Grouper(freq="ME")).tail(1).index
    sig_dates = monthly_idx[(monthly_idx >= start) & (monthly_idx <= end)]

    daily_rets = pd.Series(0.0, index=full_panel.loc[start:end].index)
    weights_for_date = {}

    for sd in sig_dates:
        target, regime, diag = ndx_sleeve.compute_ndx_weights(cpm_panel, ndx_panel, sd)
        next_loc = full_panel.index.get_indexer([sd], method="bfill")[0] + offset
        if next_loc < len(full_panel.index):
            weights_for_date[full_panel.index[next_loc]] = target

    exec_dates = sorted(weights_for_date.keys())
    cur_w = {ndx_sleeve.CASH_TICKER: 1.0}
    cur_w_idx = 0
    for ts in full_panel.loc[start:end].index:
        while cur_w_idx < len(exec_dates) and exec_dates[cur_w_idx] <= ts:
            new_w = weights_for_date[exec_dates[cur_w_idx]]
            if cur_w != new_w:
                tovr = sum(abs(cur_w.get(a, 0) - new_w.get(a, 0))
                           for a in set(cur_w) | set(new_w))
                daily_rets.loc[ts] -= tovr * cost_bps / 10000.0
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
                port_r += w * ndx_sleeve.DELISTING_HAIRCUT
                delisted_w += w
                del cur_w[asset]
        if delisted_w > 0:
            existing_safe = next((s for s in ndx_sleeve.SAFE_POOL if s in cur_w), ndx_sleeve.CASH_TICKER)
            cur_w[existing_safe] = cur_w.get(existing_safe, 0.0) + delisted_w
        daily_rets.loc[ts] += port_r

    return daily_rets

def main():
    print("Loading historical price panel...")
    panel_start = min(START_SIGNALS - pd.DateOffset(years=20), pd.Timestamp("1995-01-01"))
    panel = cpm.load_panel(start=panel_start, end=CLEAN_END)
    ndx_panel = ndx_sleeve.load_ndx_panel()
    
    cash_daily = panel["SHV"].ffill().pct_change().reindex_like(panel).fillna(0.0)
    
    print("\n==================================================")
    print("RUNNING BACKTESTS FOR BOTH MOO (a) AND MOC (b)")
    print("==================================================")
    
    # ------------------ (a) PRODUCTION MOO (offset=1) ------------------
    print("Running Production (a) T+1-MOO (offset=1)...")
    cpm_moo, _ = run_cpm_backtest_with_offset(panel, START_SIGNALS, CLEAN_END, offset=1)
    bull_moo = run_bull_spy_backtest_with_offset(panel, START_SIGNALS, CLEAN_END, offset=1)
    ndx_moo = run_ndx_backtest_with_offset(panel, ndx_panel, START_SIGNALS, CLEAN_END, offset=1)
    
    common_moo = cpm_moo.index.intersection(bull_moo.index).intersection(ndx_moo.index)
    cpm_moo = cpm_moo.reindex(common_moo)
    bull_moo = bull_moo.reindex(common_moo)
    ndx_moo = ndx_moo.reindex(common_moo).fillna(0.0)
    blend_moo = CPM_W * cpm_moo + BULL_W * bull_moo + NDX_W * ndx_moo
    
    # ------------------ (b) ALTERNATIVE MOC (offset=2) ------------------
    print("Running Alternative (b) T+1-MOC (offset=2)...")
    cpm_moc, _ = run_cpm_backtest_with_offset(panel, START_SIGNALS, CLEAN_END, offset=2)
    bull_moc = run_bull_spy_backtest_with_offset(panel, START_SIGNALS, CLEAN_END, offset=2)
    ndx_moc = run_ndx_backtest_with_offset(panel, ndx_panel, START_SIGNALS, CLEAN_END, offset=2)
    
    common_moc = cpm_moc.index.intersection(bull_moc.index).intersection(ndx_moc.index)
    cpm_moc = cpm_moc.reindex(common_moc)
    bull_moc = bull_moc.reindex(common_moc)
    ndx_moc = ndx_moc.reindex(common_moc).fillna(0.0)
    blend_moc = CPM_W * cpm_moc + BULL_W * bull_moc + NDX_W * ndx_moc
    
    # ------------------ Slice to Clean Window ------------------
    moo_slice = blend_moo.loc[CLEAN_START:CLEAN_END]
    moc_slice = blend_moc.loc[CLEAN_START:CLEAN_END]
    cash_slice = cash_daily.loc[CLEAN_START:CLEAN_END]
    
    # Compute performance metrics
    metrics_moo = cpm.perf_metrics(moo_slice, cash_slice)
    metrics_moc = cpm.perf_metrics(moc_slice, cash_slice)
    
    print("\n==================================================")
    print(f"PERFORMANCE METRICS: {CLEAN_START.date()} to {CLEAN_END.date()}")
    print("==================================================")
    print(f"{'Metric':<25} | {'(a) Production MOO':<20} | {'(b) Alternative MOC':<20}")
    print("-" * 72)
    print(f"{'CAGR':<25} | {metrics_moo['cagr']*100:19.2f}% | {metrics_moc['cagr']*100:19.2f}%")
    print(f"{'Annualized Volatility':<25} | {metrics_moo['vol']*100:19.2f}% | {metrics_moc['vol']*100:19.2f}%")
    print(f"{'Raw Sharpe Ratio':<25} | {metrics_moo['sharpe']:19.3f} | {metrics_moc['sharpe']:19.3f}")
    print(f"{'Excess Sharpe vs SHV':<25} | {metrics_moo['excess_sharpe']:19.3f} | {metrics_moc['excess_sharpe']:19.3f}")
    print(f"{'Max Drawdown':<25} | {metrics_moo['max_drawdown']*100:19.2f}% | {metrics_moc['max_drawdown']*100:19.2f}%")
    print(f"{'Calmar Ratio':<25} | {metrics_moo['calmar']:19.3f} | {metrics_moc['calmar']:19.3f}")
    print("==================================================")
    
    # Sanity Check
    print("\n==================================================")
    print("SANITY CHECK & VERIFICATION")
    print("==================================================")
    target_sharpe, target_cagr, target_maxdd = 1.503, 0.1793, -0.1162
    moo_sharpe, moo_cagr, moo_maxdd = metrics_moo['sharpe'], metrics_moo['cagr'], metrics_moo['max_drawdown']
    
    sharpe_ok = abs(moo_sharpe - target_sharpe) < 0.05
    cagr_ok = abs(moo_cagr - target_cagr) < 0.01
    maxdd_ok = abs(moo_maxdd - target_maxdd) < 0.01
    
    print(f"Production Sharpe: {moo_sharpe:.3f} (target: {target_sharpe}) -> {'PASS' if sharpe_ok else 'FAIL'}")
    print(f"Production CAGR:   {moo_cagr*100:.2f}% (target: {target_cagr*100:.2f}%) -> {'PASS' if cagr_ok else 'FAIL'}")
    print(f"Production MaxDD:  {moo_maxdd*100:.2f}% (target: {target_maxdd*100:.2f}%) -> {'PASS' if maxdd_ok else 'FAIL'}")
    
    if not (sharpe_ok and cagr_ok and maxdd_ok):
        print("ERROR: Production (a) did not reproduce the known numbers! Exiting 1.")
        sys.exit(1)
    else:
        print("Production numbers successfully verified.")
        
    # ------------------ Tracking Difference & Drag ------------------
    print("\n==================================================")
    print("TRACKING DIFFERENCE & REBALANCE DAY DRAG")
    print("==================================================")
    
    daily_diff = moo_slice - moc_slice
    ann_tracking_diff = daily_diff.std() * np.sqrt(252)
    print(f"Annualized Tracking Difference: {ann_tracking_diff*100:.4f}%")
    
    monthly_idx = pd.DataFrame({"x": 1}, index=panel.index).groupby(pd.Grouper(freq="ME")).tail(1)
    sig_dates = monthly_idx.index[(monthly_idx.index >= START_SIGNALS) & (monthly_idx.index <= CLEAN_END)].tolist()
    
    rebalance_days = []
    for sig_d in sig_dates:
        future = panel.index[panel.index > sig_d]
        if len(future) >= 1:
            t1 = future[0]
            if CLEAN_START <= t1 <= CLEAN_END:
                rebalance_days.append(t1)
                
    rebalance_days = sorted(list(set(rebalance_days)))
    
    reb_returns_moo = moo_slice.reindex(rebalance_days)
    reb_returns_moc = moc_slice.reindex(rebalance_days)
    reb_diffs = reb_returns_moc - reb_returns_moo
    
    mean_monthly_drag = reb_diffs.mean()
    print(f"Number of rebalance months evaluated: {len(rebalance_days)}")
    print(f"Mean monthly rebalance-day return diff (MOC - MOO): {mean_monthly_drag*100:+.4f}%")
    print(f"Total cumulative rebalance-day return difference: {reb_diffs.sum()*100:+.2f}%")
    
    # State whether MOC execution materially changes results
    print("\n==================================================")
    print("CONCLUSION & INTERPRETATION")
    print("==================================================")
    drag_bps_year = mean_monthly_drag * 12 * 10000.0
    print(f"Annualized mean drag/gain: {mean_monthly_drag * 12 * 100:.2f}% per year ({drag_bps_year:+.1f} bps/year)")
    
    materially_different = abs(metrics_moo['sharpe'] - metrics_moc['sharpe']) >= 0.05
    if materially_different:
        print("MOC execution MATERIALLY changes results. There is a real drag/benefit.")
    else:
        print("MOC execution DOES NOT materially change results. It is within noise (~0.01 Sharpe) of the MOO backtest.")
        
    print("==================================================")
    sys.exit(0)

if __name__ == '__main__':
    main()
