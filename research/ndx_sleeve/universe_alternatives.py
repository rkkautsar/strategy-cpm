"""Test alternative universes for the momentum sleeve (cached).

Variants:
  - NDX top-K (current)
  - SP500 top-K  (3x larger universe, broader sector mix)
  - DOW30 top-K  (concentrated mega-caps across all sectors)
  - SP500 top-decile (50 names, classic momentum factor)

All gated by BULL-QQQ regime (same as NDX), equal-weight, 13612U momentum,
monthly rebalance, 10bps cost.

Each config is cached to research/ndx_sleeve/cache/ for fast re-runs.
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

from cpm_live import load_panel, perf_metrics, sig_13612U
from bull_spy_live import compute_bull_spy_weights, CASH_TICKER
from ndx_sleeve_live import load_ndx_panel  # reuse NDX panel for tickers

CACHE_DIR = Path(__file__).resolve().parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)


def _cache_key(**params):
    blob = json.dumps(params, sort_keys=True, default=str)
    h = hashlib.sha1(blob.encode()).hexdigest()[:12]
    return CACHE_DIR / f"univ_{h}.parquet"


def _ensure_prices(tickers: list[str], existing_panel: pd.DataFrame) -> pd.DataFrame:
    """Download any tickers missing from existing_panel, append to it."""
    missing = sorted(set(tickers) - set(existing_panel.columns))
    if not missing:
        return existing_panel
    print(f"  Fetching {len(missing)} missing tickers...")
    import yfinance as yf
    chunks = [missing[i:i + 30] for i in range(0, len(missing), 30)]
    new_dfs = []
    for chunk in chunks:
        try:
            df = yf.download(chunk, start="1995-01-01", auto_adjust=True,
                             progress=False, threads=True, group_by="ticker",
                             timeout=60)
            if isinstance(df.columns, pd.MultiIndex):
                close = df.xs("Close", axis=1, level=1)
            else:
                close = df[["Close"]].rename(columns={"Close": chunk[0]})
            new_dfs.append(close)
        except Exception as e:
            print(f"    WARN chunk {chunk[:3]}: {e}", file=sys.stderr)
        time.sleep(1)
    new_panel = pd.concat(new_dfs, axis=1)
    new_panel = new_panel.loc[:, ~new_panel.columns.duplicated()]
    combined = existing_panel.join(new_panel, how="outer", rsuffix="_dup")
    combined = combined.loc[:, ~combined.columns.str.endswith("_dup")]
    # Save back
    combined.to_parquet(Path(__file__).resolve().parents[2] / "data" / "ndx_constituents" / "prices.parquet")
    return combined


def _identify_corrupted_tickers(panel: pd.DataFrame, max_daily_threshold: float = 1.0) -> set[str]:
    """Find tickers with implausible single-day returns -- yfinance data errors.
    >100% daily return for a real stock is essentially impossible (would need a
    perfectly-timed reverse split + reporting issue). Filter these out."""
    rets = panel.pct_change()
    max_daily = rets.max()
    return set(max_daily[max_daily > max_daily_threshold].index.tolist())


def _run_universe_sleeve(start, end_, index_name, select_k, cost_bps=10):
    """Universe-agnostic momentum sleeve, gated by BULL-QQQ regime."""
    panel = load_panel(start=pd.Timestamp("1993-01-01"))
    ndx_panel = load_ndx_panel()

    # Determine universe tickers ever appearing in this index
    h = ic.history(index_name)
    all_tickers = sorted(h["symbol"].unique())

    # Ensure we have price data for all of them
    ndx_panel = _ensure_prices(all_tickers, ndx_panel)

    # Filter out tickers with corrupted data (yfinance returns bad data for
    # some delisted M&A casualties: CBE +33999x, TIE +8107x, CFC +4498x, etc.)
    bad = _identify_corrupted_tickers(ndx_panel[[t for t in all_tickers if t in ndx_panel.columns]])
    if bad:
        print(f"  Filtering {len(bad)} corrupted tickers: {sorted(bad)[:10]}...")
        all_tickers = [t for t in all_tickers if t not in bad]
    full_panel = panel.join(ndx_panel, how="outer", rsuffix="_dup")
    full_panel = full_panel.loc[:, ~full_panel.columns.str.endswith("_dup")]

    sig_dates = full_panel.resample("ME").last().index
    sig_dates = sig_dates[(sig_dates >= start) & (sig_dates <= end_)]

    weights_for_date = {}
    for sd in sig_dates:
        # Gate by BULL-QQQ regime
        bq_w, bq_regime, _ = compute_bull_spy_weights(panel, sd)
        if not bq_regime.startswith("BULL_QQQ"):
            target = {CASH_TICKER: 1.0}
        else:
            # PIT membership in chosen index
            pit = ic.constituents_at(index_name, sd.strftime("%Y-%m-%d"))
            pit_tickers = set(pit["symbol"].tolist())
            available = [t for t in pit_tickers if t in ndx_panel.columns and t not in bad]
            monthly = ndx_panel.loc[:sd].resample("ME").last()
            momenta = {}
            for t in available:
                s = monthly[t].dropna()
                if len(s) < 13: continue
                m = sig_13612U(s)
                if pd.notna(m) and m > 0:
                    momenta[t] = m
            top = sorted(momenta.items(), key=lambda x: -x[1])[:select_k]
            if len(top) < select_k:
                target = {CASH_TICKER: 1.0}
            else:
                target = {t: 1.0/select_k for t, _ in top}

        next_loc = full_panel.index.get_indexer([sd], method="bfill")[0] + 1
        if next_loc < len(full_panel.index):
            weights_for_date[full_panel.index[next_loc]] = target

    daily_rets = pd.Series(0.0, index=full_panel.loc[start:end_].index)
    exec_dates = sorted(weights_for_date.keys())
    cur_w = {CASH_TICKER: 1.0}
    cur_w_idx = 0
    for ts in full_panel.loc[start:end_].index:
        while cur_w_idx < len(exec_dates) and exec_dates[cur_w_idx] <= ts:
            new_w = weights_for_date[exec_dates[cur_w_idx]]
            if cur_w != new_w:
                tovr = sum(abs(cur_w.get(a, 0) - new_w.get(a, 0))
                           for a in set(cur_w) | set(new_w))
                daily_rets.loc[ts] -= tovr * cost_bps / 10000 / 2
            cur_w = new_w
            cur_w_idx += 1
        prev_loc = full_panel.index.get_loc(ts)
        if prev_loc == 0: continue
        prev_d = full_panel.index[prev_loc - 1]
        port_r = 0.0
        for asset, w in cur_w.items():
            if asset not in full_panel.columns: continue
            today = full_panel.loc[ts, asset]
            yest = full_panel.loc[prev_d, asset]
            if pd.notna(today) and pd.notna(yest) and yest > 0:
                port_r += w * (today/yest - 1)
        daily_rets.loc[ts] += port_r
    return daily_rets


def cached_universe(start, end_, index_name, select_k):
    path = _cache_key(start=start, end=end_, index=index_name, k=select_k)
    if path.exists():
        return pd.read_parquet(path)["r"]
    r = _run_universe_sleeve(start, end_, index_name, select_k)
    pd.DataFrame({"r": r}).to_parquet(path)
    return r


def fmt(label, r):
    m = perf_metrics(r)
    return (f"  {label:<35}  Sh {m['sharpe']:>5.3f}  CAGR {m['cagr']*100:>5.2f}%  "
            f"Vol {m['vol']*100:>5.2f}%  MaxDD {m['max_drawdown']*100:>7.2f}%")


def main():
    start = pd.Timestamp("2007-02-28")
    end = pd.Timestamp("2026-05-19")

    print("## Universe alternatives for momentum sleeve (CAN 2007-02 -> 2026)")
    print("All gated by BULL-QQQ regime, equal-weight top-K by 13612U momentum")
    print()

    variants = [
        ("NDX top-4 (current)",  "nasdaq100", 4),
        ("NDX top-6",            "nasdaq100", 6),
        ("SP500 top-4",          "sp500", 4),
        ("SP500 top-6",          "sp500", 6),
        ("SP500 top-10",         "sp500", 10),
        ("SP500 top-25 (decile-ish)", "sp500", 25),
        ("SP500 top-50 (decile)", "sp500", 50),
        ("Dow30 top-4",          "dow30", 4),
        ("Dow30 top-6",          "dow30", 6),
        ("Dow30 top-10",         "dow30", 10),
    ]

    results = {}
    for label, idx, k in variants:
        t0 = time.time()
        r = cached_universe(start, end, idx, k)
        elapsed = time.time() - t0
        cache_note = "" if elapsed < 1 else f"  ({elapsed:.0f}s)"
        print(fmt(label, r) + cache_note)
        results[label] = r

    # Now compare as 10% sleeve in 60/30/10 blend
    print()
    print("## As 10% sleeve in 60/30 CPM/BULL + 10% [variant]")
    from cpm_live import run_cpm_backtest
    from bull_spy_live import run_bull_spy_backtest
    panel = load_panel(start=pd.Timestamp("1993-01-01"))
    cpm_r, _ = run_cpm_backtest(panel, start, end)
    bull_r = run_bull_spy_backtest(panel, start, end)

    base_df = pd.concat([cpm_r.rename("c"), bull_r.rename("b")], axis=1).dropna()
    base_blend = base_df["c"]*0.7 + base_df["b"]*0.3
    print(fmt("BASELINE 70/30 CPM-BULL (no sleeve)", base_blend))
    print()

    for label in results:
        r = results[label]
        df = pd.concat([cpm_r.rename("c"), bull_r.rename("b"), r.rename("n")], axis=1).dropna()
        blend = df["c"]*0.6 + df["b"]*0.3 + df["n"]*0.1
        print(fmt(f"60/30/10 with {label}", blend))


if __name__ == "__main__":
    main()
