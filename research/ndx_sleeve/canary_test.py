"""Canary architecture test — gate SPY (or IYY) by various canary specs.

Compares which canary composition best identifies risk-on for broad US equity:
  1. SPY buy-hold (no gate)
  2. HYG/TIP only (canonical HAA-Balanced canary)
  3. HYG/LQD/TIP (current BULL-QQQ canary, no trend filter)
  4. HYG/LQD/TIP + asset trend (12-1 mom OR 13612U on the asset)
  5. HYG/TIP/GLD (current CPM canary applied to single asset)
  6. HYG/TIP + asset trend
  7. (full BULL-QQQ regime gate -- only when BULL_QQQ; for reference)

Cached to research/ndx_sleeve/cache/.
"""
from __future__ import annotations
import sys
import hashlib
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import pandas as pd

from cpm_live import load_panel, perf_metrics, sig_13612U
from bull_spy_live import compute_bull_spy_weights, CASH_TICKER, _absolute_momentum

CACHE_DIR = Path(__file__).resolve().parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)


def cache_key(**params):
    blob = json.dumps(params, sort_keys=True, default=str)
    h = hashlib.sha1(blob.encode()).hexdigest()[:12]
    return CACHE_DIR / f"canary_{h}.parquet"


def gate_check(panel, sig_d, canary_tickers, trend_asset=None):
    """Return True if gate is ON (canary any-positive 13612U AND optional trend OK)."""
    # Canary: any-positive 13612U
    canary_on = False
    for c in canary_tickers:
        if c not in panel.columns:
            continue
        monthly = panel[c].loc[:sig_d].resample("ME").last().dropna()
        if len(monthly) < 13:
            continue
        m = sig_13612U(monthly)
        if pd.notna(m) and m > 0:
            canary_on = True
            break
    if not canary_on:
        return False
    if trend_asset is None:
        return True
    # Trend: 12-1 mom > 0 OR 13612U > 0
    monthly = panel[trend_asset].loc[:sig_d].resample("ME").last().dropna()
    if len(monthly) < 13:
        return False
    mom_12_1 = _absolute_momentum(monthly, sig_d)
    sig_u = sig_13612U(monthly)
    return (pd.notna(mom_12_1) and mom_12_1 > 0) or (pd.notna(sig_w13) and sig_w13 > 0)


def run_gated_asset(panel, asset, start, end_, canary_tickers, trend_filter=None,
                    use_bull_spy_regime=False, cost_bps=10):
    """Hold `asset` when gate ON, CASH_TICKER when OFF. Monthly rebalance, T+1."""
    sig_dates = panel.resample("ME").last().index
    sig_dates = sig_dates[(sig_dates >= start) & (sig_dates <= end_)]

    weights_for_date = {}
    for sd in sig_dates:
        if use_bull_spy_regime:
            _, bq_regime, _ = compute_bull_spy_weights(panel, sd)
            gate_on = bq_regime.startswith("BULL_QQQ")
        else:
            trend_a = asset if trend_filter else None
            gate_on = gate_check(panel, sd, canary_tickers, trend_a)
        target = {asset: 1.0} if gate_on else {CASH_TICKER: 1.0}
        next_loc = panel.index.get_indexer([sd], method="bfill")[0] + 1
        if next_loc < len(panel.index):
            weights_for_date[panel.index[next_loc]] = target

    daily_rets = pd.Series(0.0, index=panel.loc[start:end_].index)
    exec_dates = sorted(weights_for_date.keys())
    cur_w = {CASH_TICKER: 1.0}
    cur_w_idx = 0
    for ts in panel.loc[start:end_].index:
        while cur_w_idx < len(exec_dates) and exec_dates[cur_w_idx] <= ts:
            new_w = weights_for_date[exec_dates[cur_w_idx]]
            if cur_w != new_w:
                tovr = sum(abs(cur_w.get(a, 0) - new_w.get(a, 0))
                           for a in set(cur_w) | set(new_w))
                daily_rets.loc[ts] -= tovr * cost_bps / 10000 / 2
            cur_w = new_w
            cur_w_idx += 1
        prev_loc = panel.index.get_loc(ts)
        if prev_loc == 0: continue
        prev_d = panel.index[prev_loc - 1]
        port_r = 0.0
        for a, w in cur_w.items():
            if a not in panel.columns: continue
            today = panel.loc[ts, a]
            yest = panel.loc[prev_d, a]
            if pd.notna(today) and pd.notna(yest) and yest > 0:
                port_r += w * (today/yest - 1)
        daily_rets.loc[ts] += port_r
    return daily_rets


def cached_gated(panel, asset, start, end_, canary_tickers, trend_filter=False,
                 use_bull_spy_regime=False):
    path = cache_key(asset=asset, start=start, end=end_,
                     canary=tuple(sorted(canary_tickers)),
                     trend=trend_filter, bull_spy=use_bull_spy_regime)
    if path.exists():
        return pd.read_parquet(path)["r"]
    r = run_gated_asset(panel, asset, start, end_, canary_tickers, trend_filter,
                        use_bull_spy_regime)
    pd.DataFrame({"r": r}).to_parquet(path)
    return r


def fmt(label, r):
    m = perf_metrics(r)
    return (f"  {label:<45}  Sh {m['sharpe']:>5.3f}  CAGR {m['cagr']*100:>5.2f}%  "
            f"MaxDD {m['max_drawdown']*100:>7.2f}%")


def main():
    panel = load_panel(start=pd.Timestamp("1993-01-01"))
    end = pd.Timestamp("2026-05-19")

    # Need IYY in panel
    if "IYY" not in panel.columns:
        print("Fetching IYY...")
        import yfinance as yf
        iyy = yf.download("IYY", start="1995-01-01", auto_adjust=True, progress=False, threads=False)
        if "Close" in iyy.columns:
            panel["IYY"] = iyy["Close"]
            print(f"  IYY: {panel['IYY'].dropna().index[0].date()} -> {panel['IYY'].dropna().index[-1].date()}")

    canaries = {
        "HYG/TIP (HAA)":            ["HYG_stitched", "TIP"],
        "HYG/LQD/TIP (BULL-QQQ)":   ["HYG_stitched", "LQD", "TIP"],
        "HYG/TIP/GLD (CPM)":        ["HYG_stitched", "TIP", "GLD"],
        "HYG/LQD/TIP/GLD (combo)":  ["HYG_stitched", "LQD", "TIP", "GLD"],
    }

    print("## Canary architecture test - gate QQQ, SPY, and IYY")
    print("## Canonical 2007-02 -> 2026 (19y)")
    print()

    for asset in ["QQQ", "SPY", "IYY"]:
        if asset not in panel.columns or panel[asset].dropna().empty:
            print(f"  {asset} not in panel — skipping")
            continue
        # Find start where asset is live + 12mo warmup
        first = panel[asset].dropna().index[0]
        start = max(pd.Timestamp("2007-02-28"), first + pd.DateOffset(months=14))
        print(f"## ===== {asset} (panel from {first.date()}, gate-start {start.date()}) =====")
        # Buy-and-hold baseline
        bh = panel[asset].loc[start:end].pct_change().fillna(0)
        print(fmt(f"{asset} buy-hold (no gate)", bh))
        # Each canary, with and without trend filter
        for name, tickers in canaries.items():
            r1 = cached_gated(panel, asset, start, end, tickers, trend_filter=False)
            print(fmt(f"{asset} + {name}", r1))
            r2 = cached_gated(panel, asset, start, end, tickers, trend_filter=True)
            print(fmt(f"{asset} + {name} + trend", r2))
        # Full BULL-QQQ regime gate (for QQQ this is identical to "BULL-QQQ overlay")
        r_bq = cached_gated(panel, asset, start, end, [], use_bull_spy_regime=True)
        print(fmt(f"{asset} + full BULL-QQQ regime gate", r_bq))
        print()


if __name__ == "__main__":
    main()
