"""
Master Peer Audit: Runs all 4 canonical peer TAA strategies head-to-head on:
  - 1. Original Paper Universes (as published by the authors)
  - 2. Custom CPM 9-Asset Universe (custom universe override)

Window: 2008-05-30 to 2026-05-22 (strict live-ETF-only start date).
Cost: 10bps/side friction.
Rebalance: monthly sig_date, execution T+1 MOO.
"""
import os, sys, math
from pathlib import Path
import pandas as pd
import numpy as np
import yfinance as yf

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "research" / "canonical_peer_implementations"))

from cpm_live import load_panel, perf_metrics, RISKY_UNIVERSE, SAFE_POOL, DEFAULT_CASH
from build_dashboard import _b_monthly_signal_dates, alpha_beta_corr

# Import canonical implementations
from faa_canonical import compute_faa_weights, FAA_UNIVERSE, FAA_SAFE
from eaa_canonical import compute_eaa_weights, EAA_UNIVERSE, EAA_SAFE
from paaa_canonical import compute_paaa_weights, PAAA_UNIVERSE, PAAA_SAFE
from daa_canonical import compute_daa_weights, DAA_UNIVERSE, DAA_CANARY, DAA_SAFE


def fetch_extra_etfs(needed_tickers, start="1995-01-01"):
    """Download daily close prices with local caching."""
    px_dict = {}
    for t in needed_tickers:
        cache = Path(f"/tmp/yfc_{t}.parquet")
        if cache.exists():
            df = pd.read_parquet(cache)
            if df.index.min() <= pd.Timestamp(start):
                px_dict[t] = df.iloc[:, 0]
                continue
        print(f"  Downloading {t} via yfinance ...")
        d = yf.download(t, start=start, auto_adjust=True, progress=False)["Close"]
        if isinstance(d, pd.DataFrame):
            d = d.iloc[:, 0]
        s = pd.Series(d.values, index=d.index, name=t)
        s.to_frame().to_parquet(cache)
        px_dict[t] = s
    return px_dict


def get_monthly_rets(daily_ret_df, w_history, start, end, cost_bps=10.0):
    common = daily_ret_df.index[(daily_ret_df.index >= start) & (daily_ret_df.index <= end)]
    port = pd.Series(0.0, index=common)
    prev_w = {}
    for i, (sd, w) in enumerate(w_history):
        fut = common[common > sd]
        if len(fut) < 1: continue
        af = fut[0]
        if i + 1 < len(w_history):
            nf = common[common > w_history[i + 1][0]]
            ea = nf[0] if len(nf) >= 1 else common[-1] + pd.Timedelta(days=1)
        else:
            ea = end + pd.Timedelta(days=1)
        mask = (common >= af) & (common < ea)
        for t, ww in w.items():
            if t in daily_ret_df.columns:
                port.loc[mask] += daily_ret_df[t].reindex(common).fillna(0.0).loc[mask] * ww
        for t in set(w) | set(prev_w):
            delta = abs(w.get(t, 0.0) - prev_w.get(t, 0.0))
            if delta > 0:
                port.loc[af] -= delta * cost_bps / 10000.0
        prev_w = w
    return port


def main():
    print("Loading base proxy panel ...")
    base_panel = load_panel(start=pd.Timestamp("1996-01-01"))
    start = pd.Timestamp("2008-05-30")   # strict live-only start
    end = pd.Timestamp("2026-05-22")

    # Determine what extra ETFs we need to download to cover original universes
    all_peer_tickers = set(FAA_UNIVERSE + EAA_UNIVERSE + PAAA_UNIVERSE + DAA_UNIVERSE + DAA_CANARY + ["VWO", "AGG", "BIL", "IBB", "VEA"])
    extra_tickers = sorted(all_peer_tickers - set(base_panel.columns))
    
    print(f"Downloading {len(extra_tickers)} missing peer-universe ETFs ...")
    extra_px = fetch_extra_etfs(extra_tickers)

    # Merge into a single master daily close panel
    master_df = base_panel.copy()
    for t, s in extra_px.items():
        master_df[t] = s
    master_df = master_df.ffill().dropna(how="all")
    daily_rets = master_df.pct_change().fillna(0.0)

    # Re-calculate signal dates on aligned master panel
    close_sub = master_df[sorted(all_peer_tickers | set(RISKY_UNIVERSE) | set(SAFE_POOL) | set(["TIP", "HYG"]))]
    sig_dates = _b_monthly_signal_dates(close_sub, start, end)
    common_idx = daily_rets.loc[start:end].index

    print(f"\nAligned master panel covers: {master_df.index.min().date()} to {master_df.index.max().date()}")
    print(f"Backtest period: {start.date()} to {end.date()} ({len(common_idx)} trading days)")

    # Run list (strategy, label, weights_fn)
    runs = []

    # === I. ORIGINAL PAPER UNIVERSES ===
    # FAA Original (7 assets, SHY safe, 4mo lookback, top-2, EW)
    faa_w_orig = [ (sd, compute_faa_weights(master_df, sd, universe=FAA_UNIVERSE, safe_asset="SHY", K=2, lookback_months=4)) for sd in sig_dates ]
    runs.append(("FAA (7-asset paper universe, SHY, K=2, 4mo)", get_monthly_rets(daily_rets, faa_w_orig, start, end)))

    # EAA Original (10 assets, BIL safe, 12mo, wV=1 defensive, top-3, Score-prop)
    eaa_w_orig = [ (sd, compute_eaa_weights(master_df, sd, universe=EAA_UNIVERSE, safe_asset="BIL", K=3, lookback_months=12, wV=1.0)) for sd in sig_dates ]
    runs.append(("EAA (10-asset paper universe, BIL, K=3, 12mo)", get_monthly_rets(daily_rets, eaa_w_orig, start, end)))

    # PAAA Original (10 assets, SHY safe, 6mo, 20d cov, top-5, MVO)
    paaa_w_orig = [ (sd, compute_paaa_weights(master_df, sd, universe=PAAA_UNIVERSE, safe_asset="SHY", K=5, lookback_months=6, cov_lookback=20)) for sd in sig_dates ]
    runs.append(("PAAA (10-asset paper universe, SHY, K=5, 6mo)", get_monthly_rets(daily_rets, paaa_w_orig, start, end)))

    # DAA Original (12 assets, IEF safe, VWO/BND canaries, top-6, EW)
    daa_w_orig = [ (sd, compute_daa_weights(master_df, sd, universe=DAA_UNIVERSE, canary_universe=DAA_CANARY, safe_asset="IEF", K=6)) for sd in sig_dates ]
    runs.append(("DAA (12-asset paper universe, IEF, K=6, 13612W)", get_monthly_rets(daily_rets, daa_w_orig, start, end)))


    # === II. CUSTOM CPM 9-ASSET UNIVERSE OVERRIDES ===
    # FAA on our 9-asset universe
    faa_w_custom = [ (sd, compute_faa_weights(master_df, sd, universe=RISKY_UNIVERSE, safe_asset="SHV", K=2, lookback_months=4)) for sd in sig_dates ]
    runs.append(("FAA (Custom 9-asset CPM universe, SHV, K=2, 4mo)", get_monthly_rets(daily_rets, faa_w_custom, start, end)))

    # EAA on our 9-asset universe
    eaa_w_custom = [ (sd, compute_eaa_weights(master_df, sd, universe=RISKY_UNIVERSE, safe_asset="SHV", K=3, lookback_months=12, wV=1.0)) for sd in sig_dates ]
    runs.append(("EAA (Custom 9-asset CPM universe, SHV, K=3, 12mo)", get_monthly_rets(daily_rets, eaa_w_custom, start, end)))

    # PAAA on our 9-asset universe
    paaa_w_custom = [ (sd, compute_paaa_weights(master_df, sd, universe=RISKY_UNIVERSE, safe_asset="SHV", K=5, lookback_months=6, cov_lookback=20)) for sd in sig_dates ]
    runs.append(("PAAA (Custom 9-asset CPM universe, SHV, K=5, 6mo)", get_monthly_rets(daily_rets, paaa_w_custom, start, end)))

    # DAA on our 9-asset universe (uses custom active universe, keeps VWO/BND canaries)
    # Since DAA has 12 assets by default, we'll set K=4 (top-half rule of 9 is K=4)
    daa_w_custom = [ (sd, compute_daa_weights(master_df, sd, universe=RISKY_UNIVERSE, canary_universe=DAA_CANARY, safe_asset="SHV", K=4)) for sd in sig_dates ]
    runs.append(("DAA (Custom 9-asset CPM universe, SHV, K=4, 13612W)", get_monthly_rets(daily_rets, daa_w_custom, start, end)))


    # === III. CURRENT CPM STANDALONE REFERENCE ===
    from cpm_live import run_cpm_backtest
    ret_cpm, _ = run_cpm_backtest(base_panel, start, end)
    runs.append(("CPM Standalone (Final spec: 9-asset, Faber/Vol)", ret_cpm.reindex(common_idx).fillna(0.0)))

    # Report results
    print(f"\n{'='*140}")
    print(f"CANONICAL TAA HEAD-TO-HEAD AUDIT (2008-05-30 to 2026-05-22, 10bps/side friction)")
    print(f"{'='*140}")
    print(f"{'Strategy Variant':<60} {'Sharpe':>8} {'CAGR':>8} {'MaxDD':>9} {'Calmar':>8}")
    print("-" * 140)
    
    # 1. Print Original Universes
    print("--- Part A: Original Paper Universes (as published) ---")
    for name, r in runs[:4]:
        m = perf_metrics(r)
        cal = m["cagr"]/abs(m["max_drawdown"]) if m["max_drawdown"] else 0
        print(f"{name:<60} {m['sharpe']:>8.3f} {m['cagr']*100:>7.2f}% {m['max_drawdown']*100:>8.2f}% {cal:>8.2f}")
        
    # 2. Print Custom CPM Universe Overrides
    print("\n--- Part B: Custom CPM 9-Asset Universe Overrides ---")
    for name, r in runs[4:]:
        m = perf_metrics(r)
        cal = m["cagr"]/abs(m["max_drawdown"]) if m["max_drawdown"] else 0
        print(f"{name:<60} {m['sharpe']:>8.3f} {m['cagr']*100:>7.2f}% {m['max_drawdown']*100:>8.2f}% {cal:>8.2f}")
    print(f"====================================================================================================")


if __name__ == "__main__":
    main()
