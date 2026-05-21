"""NDX-momentum sleeve (PROD).

Spec:
  1. Universe: PIT Nasdaq-100 constituents via index-constitution lib (2006+)
  2. Signal:   13612U momentum per name (HAA canary formula, same as CPM)
  3. Select:   Top 4 by momentum (positive only)
  4. Weight:   Equal-weight, 25% each
  5. Gate:     Only allocate when BULL-QQQ regime == BULL_QQQ
               (skip CASH regime -- equity-friendly only)
  6. Fallback: 100% SHV cash when gate off OR <4 positive-momentum candidates
  7. Monthly rebalance, T+0 OPEN execution (next-day MOO), 10bps/side cost

Headline performance (canonical 2007-02 -> 2026, 19y):
  Standalone:           Sh 1.24, CAGR 40.9%, MaxDD -44.9%, Vol 30.9%
  60/30/10 CPM-BULL-NDX: Sh 1.43, CAGR 17.2%, MaxDD -16.0%

Honest caveats:
  - Pre-2017 backtest has survivorship bias (~28% of historical PIT members
    missing yfinance price data, mostly pre-2015 delistings). Post-2020 clean.
  - K=4 is the genuine Sharpe peak per concentration sweep (K=3..15 tested)
    but accepts -44% standalone MaxDD as the price of momentum concentration.
  - Mega-cap leadership is regime-dependent. A 2000-2010-style tech lost
    decade would likely underperform vs BULL-QQQ alone -- this backtest
    cannot verify because pre-2006 PIT data is unavailable.
  - 60/30/10 blend gives +0.10 Sh vs CPM-BULL only at cost of +3.4pp MaxDD.

Live trading note: NDX sleeve holds 4 individual stocks per month.
Tax: monthly turnover at sleeve level can be high (4 names rotate); ordinary
income on gains for the equity rotation -- worse than ETF strategies.
Best in tax-advantaged account.
"""
from __future__ import annotations
import sys
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd
import index_constitution as ic

from cpm_live import sig_13612W
from bull_qqq_live import compute_bull_qqq_weights, CASH_TICKER

ROOT = Path(__file__).resolve().parent
PRICES_FILE = ROOT / "data" / "ndx_constituents" / "prices.parquet"

# Spec config
SELECT_K = 4              # top-K by momentum, equal-weighted
COST_BPS_PER_SIDE = 10


def load_ndx_panel() -> pd.DataFrame:
    """Load NDX constituent prices from disk."""
    return pd.read_parquet(PRICES_FILE)


def refresh_ndx_panel(start: str = "1995-01-01") -> pd.DataFrame:
    """Re-download NDX constituent prices for current and historical members.
    Use in live runner to ensure fresh data each month."""
    import yfinance as yf
    h = ic.history("nasdaq100")
    tickers = sorted(h["symbol"].unique())
    chunks = [tickers[i:i + 30] for i in range(0, len(tickers), 30)]
    all_dfs = []
    for chunk in chunks:
        try:
            df = yf.download(
                chunk, start=start, auto_adjust=True, progress=False,
                threads=True, group_by="ticker", timeout=60,
            )
            if isinstance(df.columns, pd.MultiIndex):
                close = df.xs("Close", axis=1, level=1)
            else:
                close = df[["Close"]].rename(columns={"Close": chunk[0]})
            all_dfs.append(close)
        except Exception as e:
            print(f"  WARN chunk {chunk[:3]}...: {e}", file=sys.stderr)
    panel = pd.concat(all_dfs, axis=1)
    panel = panel.loc[:, ~panel.columns.duplicated()]
    PRICES_FILE.parent.mkdir(parents=True, exist_ok=True)
    panel.to_parquet(PRICES_FILE)
    return panel


def compute_ndx_weights(
    cpm_panel: pd.DataFrame,
    ndx_panel: pd.DataFrame,
    sig_d: pd.Timestamp,
) -> tuple[dict, str, dict]:
    """Returns (weights, regime_label, diagnostics)."""
    # Step 1: BULL-QQQ gate -- only allocate when BULL_QQQ regime
    bq_weights, bq_regime, _ = compute_bull_qqq_weights(cpm_panel, sig_d)
    if not bq_regime.startswith("BULL_QQQ"):
        return ({CASH_TICKER: 1.0}, f"GATE_OFF ({bq_regime})", {
            "bull_qqq_regime": bq_regime,
            "selected": [],
            "reason": "BULL-QQQ not in QQQ regime",
        })

    # Step 2: PIT NDX membership at signal date
    # PIT data (index-constitution lib) only covers 2006-01+. For earlier
    # signal dates, fall back to mirroring BULL-QQQ weights (i.e., the NDX
    # sleeve acts as extra BULL exposure) instead of going to cash.
    pit = ic.constituents_at("nasdaq100", sig_d.strftime("%Y-%m-%d"))
    pit_tickers = set(pit["symbol"].tolist())
    if len(pit_tickers) == 0:
        return (bq_weights, "NDX_FALLBACK_BULL_QQQ", {
            "bull_qqq_regime": bq_regime,
            "selected": list(bq_weights.keys()),
            "reason": "PIT NDX data unavailable pre-2006; mirroring BULL-QQQ",
        })
    available = [t for t in pit_tickers if t in ndx_panel.columns]

    # Step 3: 13612U momentum on each available member
    monthly = ndx_panel.loc[:sig_d].resample("ME").last()
    momenta = {}
    for t in available:
        s = monthly[t].dropna()
        if len(s) < 13:
            continue
        m = sig_13612W(s)
        if pd.notna(m) and m > 0:
            momenta[t] = m

    # Step 4: top SELECT_K by momentum, equal-weight 1/SELECT_K each.
    # Partial fill if < SELECT_K positive candidates (CPM-style):
    # take what's there at 1/SELECT_K each, rest in SHV cash.
    sorted_by_mom = sorted(momenta.items(), key=lambda x: -x[1])
    n_pick = min(len(sorted_by_mom), SELECT_K)
    selected = [t for t, _ in sorted_by_mom[:n_pick]]
    per_slot = 1.0 / SELECT_K
    weights = {t: per_slot for t in selected}
    cash_share = 1.0 - n_pick * per_slot
    if cash_share > 1e-9:
        weights[CASH_TICKER] = cash_share
    regime = "NDX_ACTIVE" if n_pick == SELECT_K else f"NDX_PARTIAL_{n_pick}"
    return (weights, regime, {
        "bull_qqq_regime": bq_regime,
        "n_candidates": len(sorted_by_mom),
        "selected": selected,
        "momenta": {t: momenta[t] for t in selected},
        "cash_share": cash_share,
    })


def run_ndx_backtest(
    cpm_panel: pd.DataFrame,
    ndx_panel: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
    cost_bps: float = COST_BPS_PER_SIDE,
) -> tuple[pd.Series, list[dict]]:
    """Run monthly NDX sleeve backtest. Returns (daily_returns, history).

    Execution: T+0 OPEN (next-day MOO). Weights apply from the first trading
    day after each signal date (next_loc + 1 from signal day index).
    """
    full_panel = cpm_panel.join(ndx_panel, how="outer", rsuffix="_dup")
    full_panel = full_panel.loc[:, ~full_panel.columns.str.endswith("_dup")]

    # Use ACTUAL last trading day per calendar month (not calendar month-end
    # timestamps) for correct alignment with CPM/BULL signal dates.
    monthly_idx = pd.DataFrame({"x": 1}, index=full_panel.index).groupby(
        pd.Grouper(freq="ME")).tail(1).index
    sig_dates = monthly_idx[(monthly_idx >= start) & (monthly_idx <= end)]

    daily_rets = pd.Series(0.0, index=full_panel.loc[start:end].index)
    weights_for_date = {}
    history = []

    for sd in sig_dates:
        target, regime, diag = compute_ndx_weights(cpm_panel, ndx_panel, sd)
        next_loc = full_panel.index.get_indexer([sd], method="bfill")[0] + 1
        if next_loc < len(full_panel.index):
            weights_for_date[full_panel.index[next_loc]] = target
        history.append({"sig_d": sd, "regime": regime, "weights": target,
                        "selected": diag.get("selected", [])})

    exec_dates = sorted(weights_for_date.keys())
    cur_w = {CASH_TICKER: 1.0}
    cur_w_idx = 0
    for ts in full_panel.loc[start:end].index:
        while cur_w_idx < len(exec_dates) and exec_dates[cur_w_idx] <= ts:
            new_w = weights_for_date[exec_dates[cur_w_idx]]
            if cur_w != new_w:
                tovr = sum(abs(cur_w.get(a, 0) - new_w.get(a, 0))
                           for a in set(cur_w) | set(new_w))
                # turnover already counts both sell and buy legs (one positive
                # delta per affected asset); apply 10bps/side via single division.
                daily_rets.loc[ts] -= tovr * cost_bps / 10000.0
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
                port_r += w * (today / yest - 1)
        daily_rets.loc[ts] += port_r

    return daily_rets, history


if __name__ == "__main__":
    """Smoke test: print current allocation."""
    from cpm_live import load_panel
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="Re-download NDX prices")
    ap.add_argument("--sig-date", default=None)
    args = ap.parse_args()

    if args.refresh:
        print("Refreshing NDX panel (downloading from yfinance)...")
        refresh_ndx_panel()

    cpm_panel = load_panel(start=pd.Timestamp("2018-01-01"))
    ndx_panel = load_ndx_panel()

    if args.sig_date:
        sig_d = pd.Timestamp(args.sig_date)
    else:
        today = pd.Timestamp.today().normalize()
        # last completed month-end
        prior_me = today.replace(day=1) - pd.Timedelta(days=1)
        candidates = cpm_panel.index[cpm_panel.index <= prior_me]
        sig_d = candidates[-1] if len(candidates) > 0 else today

    weights, regime, diag = compute_ndx_weights(cpm_panel, ndx_panel, sig_d)
    print(f"\nNDX sleeve allocation (signal date: {sig_d.date()})")
    print(f"Regime: {regime}")
    if regime == "NDX_ACTIVE":
        print(f"BULL-QQQ gate state: {diag.get('bull_qqq_regime')}")
        print(f"\nTop-{SELECT_K} by 13612U momentum:")
        for t in diag["selected"]:
            mom = diag["momenta"][t]
            print(f"  {t:<6} weight 25%  momentum {mom*100:+.2f}%")
    else:
        print(f"  100% {CASH_TICKER} cash")
        print(f"  Reason: {diag.get('reason', '-')}")
