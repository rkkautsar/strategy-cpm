import sys, socket
socket.setdefaulttimeout(15)
sys.path.insert(0, "/Users/rkautsar/personal/scripts/strategy_cpm")

import pandas as pd
import numpy as np
from cpm_live import load_panel, run_cpm_backtest, perf_metrics
from bull_qqq_live import run_bull_qqq_backtest
from ndx_sleeve_live import load_ndx_panel, run_ndx_backtest
from circuit_breaker import compute_lqd_ief_circuit_scale, LQD_IEF_EMA_SPAN
from build_dashboard import (
    bench_aaa_tip, bench_haa_simple, bench_qqq_12mo_trend,
    bench_static_pp_qqq, bench_bb4_blend
)

def compute_metrics(daily):
    if len(daily) == 0:
        return {"Sharpe": 0.0, "CAGR": 0.0, "MaxDD": 0.0}
    eq = (1.0 + daily).cumprod()
    cagr = eq.iloc[-1] ** (252.0 / len(daily)) - 1.0
    vol = daily.std(ddof=0) * np.sqrt(252)
    sharpe = (daily.mean() * 252) / (vol) if vol > 1e-9 else 0.0
    
    # MaxDD
    peaks = eq.cummax()
    dds = (eq - peaks) / peaks
    max_dd = dds.min()
    return {"Sharpe": sharpe, "CAGR": cagr, "MaxDD": max_dd}

def paired_block_bootstrap(strat_daily, bench_daily, n_iter=5000, block_size=21, seed=42):
    rng = np.random.default_rng(seed)
    n = len(strat_daily)
    n_blocks = (n // block_size) + 1
    
    strat_arr = strat_daily.values
    bench_arr = bench_daily.values
    
    diff_sharpe = []
    diff_cagr = []
    diff_maxdd = []
    
    for _ in range(n_iter):
        strat_blocks = []
        bench_blocks = []
        for _ in range(n_blocks):
            start_idx = rng.integers(0, n)
            end_idx = start_idx + block_size
            if end_idx <= n:
                strat_blocks.append(strat_arr[start_idx:end_idx])
                bench_blocks.append(bench_arr[start_idx:end_idx])
            else:
                rem = n - start_idx
                strat_blocks.append(strat_arr[start_idx:])
                bench_blocks.append(bench_arr[start_idx:])
                wrap = block_size - rem
                strat_blocks.append(strat_arr[:wrap])
                bench_blocks.append(bench_arr[:wrap])
                
        s_sampled = np.concatenate(strat_blocks)[:n]
        b_sampled = np.concatenate(bench_blocks)[:n]
        
        s_met = compute_metrics(pd.Series(s_sampled))
        b_met = compute_metrics(pd.Series(b_sampled))
        
        diff_sharpe.append(s_met["Sharpe"] - b_met["Sharpe"])
        diff_cagr.append(s_met["CAGR"] - b_met["CAGR"])
        diff_maxdd.append((s_met["MaxDD"] - b_met["MaxDD"]) * 100)
        
    return np.array(diff_sharpe), np.array(diff_cagr), np.array(diff_maxdd)

def main():
    print("Computing PROD blend and BB4 ...")
    panel = load_panel(start=pd.Timestamp("1993-01-01"))
    ndx_panel = load_ndx_panel()
    start = pd.Timestamp("2008-04-30")
    end = pd.Timestamp("2026-05-22")

    cpm, _ = run_cpm_backtest(panel, start, end)
    bull_raw = run_bull_qqq_backtest(panel, start, end)
    ndx_raw, _ = run_ndx_backtest(panel, ndx_panel, start, end)
    common = cpm.index.intersection(bull_raw.index).intersection(ndx_raw.index)
    cpm = cpm.reindex(common)
    bull_raw = bull_raw.reindex(common)
    ndx_raw = ndx_raw.reindex(common).fillna(0.0)
    sigs = (pd.DataFrame({"x": 1}, index=cpm.index).groupby(pd.Grouper(freq="ME")).tail(1).index.tolist())

    ndx_scale = compute_lqd_ief_circuit_scale(panel["LQD"], panel["IEF"],
                                                 common, sigs, ema_span=LQD_IEF_EMA_SPAN)
    ndx = ndx_scale * ndx_raw
    bull = bull_raw
    blend = 0.60 * cpm + 0.20 * bull + 0.20 * ndx

    bb4 = bench_bb4_blend(panel, start, end).reindex(common).fillna(0.0)
    static_pp = bench_static_pp_qqq(panel, start, end, pp_weight=0.80, growth_ticker="QQQ").reindex(common).fillna(0.0)
    spy = panel["SPY"].ffill().pct_change().loc[start:end].reindex(common).fillna(0.0)
    qqq = panel["QQQ"].ffill().pct_change().loc[start:end].reindex(common).fillna(0.0)

    comparisons = [
        ("PROD vs BB4 lit blend (60 AAA+TIP / 20 HAA-S SPY / 20 QQQ-trend)", bb4),
        ("PROD vs Static 80% PP + 20% QQQ", static_pp),
        ("PROD vs SPY buy-hold", spy),
        ("PROD vs QQQ buy-hold", qqq),
    ]

    for name, bench in comparisons:
        print("\n" + "="*100)
        print(name)
        print("="*100)
        
        s_met = compute_metrics(blend)
        b_met = compute_metrics(bench)
        
        print("Point estimates:")
        print(f"  PROD     Sharpe={s_met['Sharpe']:.3f}  CAGR={s_met['CAGR']*100:.2f}%  MaxDD={s_met['MaxDD']*100:.2f}%")
        print(f"  Bench    Sharpe={b_met['Sharpe']:.3f}  CAGR={b_met['CAGR']*100:.2f}%  MaxDD={b_met['MaxDD']*100:.2f}%")
        diff_sh = s_met['Sharpe'] - b_met['Sharpe']
        diff_ca = s_met['CAGR'] - b_met['CAGR']
        diff_dd = (s_met['MaxDD'] - b_met['MaxDD']) * 100
        print(f"  Diff     dSh   ={diff_sh:+.3f}  dCAGR={diff_ca*100:+.2f}%  dDD ={diff_dd:+.2f}pp (positive=shallower)")
        
        d_sh, d_ca, d_dd = paired_block_bootstrap(blend, bench, n_iter=5000, block_size=21, seed=42)
        
        print("\nBootstrap (paired block, B=5000, block=21d, seed=42):")
        print(f"  Sharpe diff:  median {np.median(d_sh):+.3f} | 95% CI [{np.percentile(d_sh, 2.5):+.3f}, {np.percentile(d_sh, 97.5):+.3f}]")
        print(f"  CAGR diff:    median {np.median(d_ca)*100:+.2f}% | 95% CI [{np.percentile(d_ca, 2.5)*100:+.2f}%, {np.percentile(d_ca, 97.5)*100:+.2f}%]")
        print(f"  MaxDD diff:   median {np.median(d_dd):+.2f}pp | 95% CI [{np.percentile(d_dd, 2.5):+.2f}pp, {np.percentile(d_dd, 97.5):+.2f}pp]")
        
        print(f"\nProbability that PROD beats {name.split(' vs ')[1]}:")
        print(f"  P(dSharpe > 0)             {np.mean(d_sh > 0)*100:.2f}%")
        print(f"  P(dSharpe > 0.05)          {np.mean(d_sh > 0.05)*100:.2f}%")
        print(f"  P(dSharpe > 0.10)          {np.mean(d_sh > 0.10)*100:.2f}%")
        print(f"  P(dSharpe > 0.20)          {np.mean(d_sh > 0.20)*100:.2f}%")
        print(f"  P(dCAGR > 0)               {np.mean(d_ca > 0)*100:.2f}%")
        print(f"  P(dCAGR > 2%)              {np.mean(d_ca > 0.02)*100:.2f}%")
        print(f"  P(dCAGR > 5%)              {np.mean(d_ca > 0.05)*100:.2f}%")
        print(f"  P(MaxDD shallower)         {np.mean(d_dd > 0)*100:.2f}%")
        print(f"  P(MaxDD shallower by 2pp)  {np.mean(d_dd > 2)*100:.2f}%")
        print(f"  P(MaxDD shallower by 5pp)  {np.mean(d_dd > 5)*100:.2f}%")

if __name__ == "__main__":
    main()
