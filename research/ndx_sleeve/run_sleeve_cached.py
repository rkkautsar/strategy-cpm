"""Cached sleeve backtest runner. Caches by (config_hash) -> returns series.

Run with: uv run python research/ndx_sleeve/run_sleeve_cached.py [task]

Tasks:
  standalone    - just sleeve standalone numbers for all windows
  weekly        - test weekly vs monthly rebalance
  blends        - test 60/30/10, 70/20/10, etc.
  all           - everything
"""
from __future__ import annotations
import sys
import hashlib
import json
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import pandas as pd
import index_constitution as ic

from cpm_live import load_panel, run_cpm_backtest, perf_metrics, sig_13612U
from bull_qqq_live import run_bull_qqq_backtest, compute_bull_qqq_weights, CASH_TICKER
from ndx_momentum_sleeve import load_ndx_panel
import ndx_momentum_sleeve as nms

CACHE_DIR = Path(__file__).resolve().parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)


def cache_key(name: str, **params) -> Path:
    blob = name + "|" + json.dumps(params, sort_keys=True, default=str)
    h = hashlib.sha1(blob.encode()).hexdigest()[:12]
    return CACHE_DIR / f"{name}_{h}.parquet"


def cached_returns(name: str, compute_fn, force: bool = False, **params) -> pd.Series:
    path = cache_key(name, **params)
    if path.exists() and not force:
        return pd.read_parquet(path)["r"]
    s = compute_fn(**params)
    pd.DataFrame({"r": s}).to_parquet(path)
    return s


def get_cpm_r(start, end_):
    return cached_returns("cpm", lambda start, end:
        run_cpm_backtest(load_panel(start=pd.Timestamp("1993-01-01")), start, end)[0],
        start=start, end=end_)


def get_bull_r(start, end_):
    return cached_returns("bull", lambda start, end:
        run_bull_qqq_backtest(load_panel(start=pd.Timestamp("1993-01-01")), start, end),
        start=start, end=end_)


def get_ndx_r(start, end_, top_k=8, select_k=4, downside_lb=252, freq="ME"):
    """freq: ME (month-end) or W-FRI (weekly Friday)."""
    return cached_returns("ndx",
        lambda start, end, top_k, select_k, downside_lb, freq: _run_ndx(
            start, end, top_k, select_k, downside_lb, freq),
        start=start, end=end_, top_k=top_k, select_k=select_k,
        downside_lb=downside_lb, freq=freq)


def _run_ndx(start, end_, top_k, select_k, downside_lb, freq) -> pd.Series:
    """Run NDX sleeve with given config and rebalance frequency."""
    from itertools import combinations
    panel = load_panel(start=pd.Timestamp("1993-01-01"))
    ndx_panel = load_ndx_panel()
    full_panel = panel.join(ndx_panel, how="outer", rsuffix="_dup")
    full_panel = full_panel.loc[:, ~full_panel.columns.str.endswith("_dup")]

    sig_dates = full_panel.resample(freq).last().index
    sig_dates = sig_dates[(sig_dates >= start) & (sig_dates <= end_)]

    daily_rets = pd.Series(0.0, index=full_panel.loc[start:end_].index)
    weights_for_date = {}
    cost_bps = 10

    for sd in sig_dates:
        # Gate
        bq_w, bq_regime, _ = compute_bull_qqq_weights(panel, sd)
        if not bq_regime.startswith("BULL_QQQ"):
            target = {CASH_TICKER: 1.0}
        else:
            pit = ic.constituents_at("nasdaq100", sd.strftime("%Y-%m-%d"))
            pit_tickers = set(pit["symbol"].tolist())
            available = [t for t in pit_tickers if t in ndx_panel.columns]
            monthly = ndx_panel.loc[:sd].resample("ME").last()
            momenta = {}
            for t in available:
                s = monthly[t].dropna()
                if len(s) < 13:
                    continue
                m = sig_13612U(s)
                if pd.notna(m) and m > 0:
                    momenta[t] = m
            top = sorted(momenta.items(), key=lambda x: -x[1])[:top_k]
            if len(top) < select_k:
                target = {CASH_TICKER: 1.0}
            else:
                daily_rets_in = ndx_panel.loc[:sd].pct_change()
                best_score, best_combo = -np.inf, None
                for combo in combinations([t for t, _ in top], select_k):
                    avg_mom = np.mean([momenta[t] for t in combo])
                    port_ret = daily_rets_in[list(combo)].iloc[-downside_lb:].mean(axis=1)
                    r = port_ret.dropna()
                    if len(r) < 30:
                        continue
                    neg = r[r < 0]
                    if len(neg) < 5:
                        dvol = max(1e-6, r.std() * np.sqrt(252) * 0.1)
                    else:
                        dvol = neg.std() * np.sqrt(252)
                    if dvol <= 0:
                        continue
                    score = avg_mom / np.sqrt(dvol)
                    if score > best_score:
                        best_score, best_combo = score, combo
                if best_combo is None:
                    target = {CASH_TICKER: 1.0}
                else:
                    target = {t: 1.0/select_k for t in best_combo}

        next_loc = full_panel.index.get_indexer([sd], method="bfill")[0] + 1
        if next_loc < len(full_panel.index):
            exec_d = full_panel.index[next_loc]
            weights_for_date[exec_d] = target

    exec_dates = sorted(weights_for_date.keys())
    cur_w = {CASH_TICKER: 1.0}
    cur_w_idx = 0
    prev_target = None
    for ts in full_panel.loc[start:end_].index:
        while cur_w_idx < len(exec_dates) and exec_dates[cur_w_idx] <= ts:
            new_w = weights_for_date[exec_dates[cur_w_idx]]
            if cur_w != new_w:
                # Pay turnover
                tovr = sum(abs(cur_w.get(a, 0) - new_w.get(a, 0))
                           for a in set(cur_w) | set(new_w))
                daily_rets.loc[ts] -= tovr * cost_bps / 10000 / 2
            cur_w = new_w
            cur_w_idx += 1
        prev_loc = full_panel.index.get_loc(ts)
        if prev_loc == 0:
            continue
        prev_d = full_panel.index[prev_loc - 1]
        port_r = 0.0
        for asset, w in cur_w.items():
            if asset not in full_panel.columns:
                continue
            today = full_panel.loc[ts, asset]
            yest = full_panel.loc[prev_d, asset]
            if pd.notna(today) and pd.notna(yest) and yest > 0:
                port_r += w * (today/yest - 1)
        daily_rets.loc[ts] += port_r

    return daily_rets


def fmt(label, r):
    m = perf_metrics(r)
    return (f'  {label:<42}  Sh {m["sharpe"]:>5.3f}  CAGR {m["cagr"]*100:>5.2f}%  '
            f'Vol {m["vol"]*100:>5.2f}%  MaxDD {m["max_drawdown"]*100:>7.2f}%')


def main():
    task = sys.argv[1] if len(sys.argv) > 1 else "standalone"
    end = pd.Timestamp("2026-05-19")

    windows = [
        ("CAN 2007-02 (19y)",  pd.Timestamp("2007-02-28")),
        ("OOS 2017+ (9y)",     pd.Timestamp("2017-01-01")),
        ("Post-2015 PIT",      pd.Timestamp("2015-01-31")),
    ]

    if task in ("standalone", "all"):
        print("## NDX sleeve standalone (monthly, baseline top8/pick4/dv252)")
        for label, start in windows:
            t0 = time.time()
            r = get_ndx_r(start, end)
            print(fmt(label, r) + f"  ({time.time()-t0:.1f}s)")

    if task in ("weekly", "all"):
        print("\n## Monthly vs Weekly rebalance (CAN 2007-02)")
        start = pd.Timestamp("2007-02-28")
        r_m = get_ndx_r(start, end, freq="ME")
        r_w = get_ndx_r(start, end, freq="W-FRI")
        print(fmt("Monthly (ME)",       r_m))
        print(fmt("Weekly  (W-FRI)",    r_w))

    if task in ("blends", "all"):
        print("\n## 60/30/10 explicit blend")
        for label, start in windows:
            cpm_r = get_cpm_r(start, end)
            bull_r = get_bull_r(start, end)
            ndx_r = get_ndx_r(start, end)
            df = pd.concat([cpm_r.rename("c"), bull_r.rename("b"), ndx_r.rename("n")],
                           axis=1).dropna()
            cpm_bull = df["c"]*0.7 + df["b"]*0.3
            blend = df["c"]*0.6 + df["b"]*0.3 + df["n"]*0.1
            print(f"  {label}")
            print(fmt("    100% CPM-BULL (current)", cpm_bull))
            print(fmt("    60/30/10 CPM/BULL/NDX",   blend))


if __name__ == "__main__":
    main()
