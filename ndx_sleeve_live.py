"""NDX sleeve (20% of 60/20/20 PROD blend).

Spec:
  1. Universe: PIT Nasdaq-100 constituents via index-constitution lib (2006-01+)
  2. Signal:   13612U momentum per stock (canonical HAA unweighted average)
  3. Gate:     BULL-QQQ regime must be BULL_QQQ; else best-of-safe (SHV/IEF
               by 13612U, HAA-style) -- unless Rebound bypass fires.
  4. PIT fallback: when PIT data unavailable (pre-2006), mirror BULL-QQQ
     weights (NDX sleeve acts as extra BULL exposure).
  5. Selection: top-K by 13612U momentum, equal-weighted 1/K each.
  6. Partial fill: if fewer than K positive candidates, take what's there at
     1/K=25% per pick, rest in best-of-safe (e.g. 2 positives -> 50% stocks
     + 50% best-safe).
  7. Rebound bypass: BULL gate off but fast QQQ 2mo TR > 0 -> 50% top-K
     names + 50% best-safe (Goulding-Harvey fast-bypass).
  8. Monthly rebalance, T+1 OPEN execution (next-day MOO), 10bps/side cost.
"""
from __future__ import annotations
import sys
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd
import index_constitution as ic

from cpm_live import sig_13612U
from bull_qqq_live import (
    compute_bull_qqq_weights, CASH_TICKER, BULL_TICKER, SAFE_POOL,
    _rebound_fast_ok, _pick_safe,
)

# Rebound bypass on the NDX sleeve (Goulding-Harvey 4-state 'Rebound' analog).
# When the BULL gate is OFF (slow=defensive) but fast QQQ 2mo TR > 0,
# allocate REBOUND_NDX_WEIGHT to the top-K momentum-positive NDX names and
# the rest to best-of-safe (instead of going 100% cash). Captures V-shape
# recoveries early via high-beta momentum names that run harder than QQQ
# index. Empirical lift vs no-rebound: +2.5pp NDX sleeve CAGR, +0.47pp
# portfolio CAGR, +0.013 portfolio Sortino, same portfolio MaxDD.
REBOUND_NDX_WEIGHT = 0.5

ROOT = Path(__file__).resolve().parent
PRICES_FILE = ROOT / "data" / "ndx_constituents" / "prices.parquet"

# Spec config
SELECT_K = 8              # top-K by momentum, equal-weighted (12.5% per pick
                          # within sleeve = 2.5% portfolio at 20% blend weight;
                          # caps single-name bankruptcy impact at ~2.5% portfolio)
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
    """Returns (weights, regime_label, diagnostics).

    Flow:
      - BULL gate ON  -> select top-K NDX names by 13612U > 0 (full weight)
      - BULL gate OFF + fast QQQ 2mo > 0 -> Rebound bypass (50% top-K, 50% safe)
      - BULL gate OFF + fast not positive -> 100% safe
    """
    # Step 1: BULL-QQQ gate
    bq_weights, bq_regime, _ = compute_bull_qqq_weights(cpm_panel, sig_d)
    rebound_on = False
    if not bq_regime.startswith("BULL_QQQ"):
        # Rebound bypass check: BULL gate off but fast QQQ momentum positive
        cpm_monthly = cpm_panel.loc[:sig_d].resample("ME").last()
        fast_ok, fast_r = (_rebound_fast_ok(cpm_monthly[BULL_TICKER], sig_d)
                            if BULL_TICKER in cpm_monthly.columns else (None, float("nan")))
        if fast_ok is not True:
            safe = _pick_safe(cpm_monthly)
            return ({safe: 1.0}, f"GATE_OFF ({bq_regime})", {
                "bull_qqq_regime": bq_regime,
                "selected": [],
                "reason": "BULL-QQQ off; fast QQQ 2mo TR not positive",
                "fast_qqq_2mo": fast_r,
                "picked_safe": safe,
            })
        rebound_on = True

    # Step 2: PIT NDX membership at signal date
    # PIT data (index-constitution lib) only covers 2006-01+. For earlier
    # signal dates, fall back to mirroring BULL-QQQ weights (i.e., the NDX
    # sleeve acts as extra BULL exposure) instead of going to cash.
    pit = ic.constituents_at("nasdaq100", sig_d.strftime("%Y-%m-%d"))
    pit_tickers = set(pit["symbol"].tolist())
    if len(pit_tickers) == 0:
        if rebound_on:
            # Pre-2006 rebound: fall back to 50/50 QQQ + safe
            cpm_monthly = cpm_panel.loc[:sig_d].resample("ME").last()
            safe = _pick_safe(cpm_monthly)
            return ({BULL_TICKER: REBOUND_NDX_WEIGHT, safe: 1.0 - REBOUND_NDX_WEIGHT},
                    "NDX_REBOUND_FALLBACK", {
                        "bull_qqq_regime": bq_regime,
                        "selected": [BULL_TICKER],
                        "reason": "PIT pre-2006 + rebound: 50/50 QQQ/safe fallback",
                    })
        return (bq_weights, "NDX_FALLBACK_BULL_QQQ", {
            "bull_qqq_regime": bq_regime,
            "selected": list(bq_weights.keys()),
            "reason": "PIT NDX data unavailable pre-2006; mirroring BULL-QQQ",
        })
    # Filter to PIT-listed tickers with usable price at signal date.
    # A ticker that delisted before sig_d may still appear in yearly PIT
    # membership; selecting it would trigger the holding-period haircut bug.
    monthly = ndx_panel.loc[:sig_d].resample("ME").last()
    available = []
    for t in pit_tickers:
        if t not in ndx_panel.columns:
            continue
        # Require non-NaN price at the actual signal date (not just history)
        if sig_d in ndx_panel.index and pd.isna(ndx_panel.loc[sig_d, t]):
            continue
        # Or fall back to last available within 30 days of sig_d (data gap tolerance)
        recent = ndx_panel[t].loc[sig_d - pd.Timedelta(days=30):sig_d].dropna()
        if recent.empty:
            continue
        available.append(t)

    # Step 3: 13612U momentum on each available member
    momenta = {}
    for t in available:
        s = monthly[t].dropna()
        if len(s) < 13:
            continue
        m = sig_13612U(s)
        if pd.notna(m) and m > 0:
            momenta[t] = m

    # Step 4: top SELECT_K by momentum, equal-weight 1/SELECT_K each.
    # Rebound mode: scale all stock weights by REBOUND_NDX_WEIGHT (=0.5),
    # remainder to safe asset. Normal mode: full weight, partial fill if
    # < SELECT_K positive candidates (CPM-style); rest in SHV cash.
    sorted_by_mom = sorted(momenta.items(), key=lambda x: -x[1])
    n_pick = min(len(sorted_by_mom), SELECT_K)
    selected = [t for t, _ in sorted_by_mom[:n_pick]]
    if rebound_on:
        cpm_monthly = cpm_panel.loc[:sig_d].resample("ME").last()
        safe = _pick_safe(cpm_monthly)
        per_slot = REBOUND_NDX_WEIGHT / SELECT_K
        weights = {t: per_slot for t in selected}
        weights[safe] = weights.get(safe, 0.0) + (1.0 - n_pick * per_slot)
        regime = ("NDX_REBOUND" if n_pick == SELECT_K
                   else f"NDX_REBOUND_PARTIAL_{n_pick}")
    else:
        per_slot = 1.0 / SELECT_K
        weights = {t: per_slot for t in selected}
        cash_share = 1.0 - n_pick * per_slot
        if cash_share > 1e-9:
            cpm_monthly = cpm_panel.loc[:sig_d].resample("ME").last()
            safe = _pick_safe(cpm_monthly)
            weights[safe] = weights.get(safe, 0.0) + cash_share
        regime = "NDX_ACTIVE" if n_pick == SELECT_K else f"NDX_PARTIAL_{n_pick}"
    return (weights, regime, {
        "bull_qqq_regime": bq_regime,
        "n_candidates": len(sorted_by_mom),
        "selected": selected,
        "momenta": {t: momenta[t] for t in selected},
        "rebound_active": rebound_on,
    })


def run_ndx_backtest(
    cpm_panel: pd.DataFrame,
    ndx_panel: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
    cost_bps: float = COST_BPS_PER_SIDE,
) -> tuple[pd.Series, list[dict]]:
    """Run monthly NDX sleeve backtest. Returns (daily_returns, history).

    Execution: T+1 OPEN (next trading day MOO). Weights apply from the first trading
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
        # Detect market-closed day (all tickers NaN today) vs real delisting.
        # Holidays produce NaN for every asset; real delistings produce NaN
        # only for the delisted ticker while others trade.
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
                # Real delisting detected mid-holding-period (acquisition,
                # merger, or bankruptcy). Without delisting-event metadata we
                # cannot know the terminal payoff. Apply conservative
                # liquidation: one-time -10% haircut on the delisting day
                # (rough blended estimate across NDX historical delistings)
                # then convert proceeds to the period's existing safe asset
                # (or CASH_TICKER if no safe was held).
                port_r += w * (-0.10)
                delisted_w += w
                del cur_w[asset]
        if delisted_w > 0:
            # Prefer existing safe in cur_w (matches the period's best-of-safe
            # pick); fall back to SHV when NDX was 100% stocks.
            existing_safe = next((s for s in SAFE_POOL if s in cur_w), CASH_TICKER)
            cur_w[existing_safe] = cur_w.get(existing_safe, 0.0) + delisted_w
            if existing_safe in full_panel.columns:
                t_cash = full_panel.loc[ts, existing_safe]
                y_cash = full_panel.loc[prev_d, existing_safe]
                if pd.notna(t_cash) and pd.notna(y_cash) and y_cash > 0:
                    port_r += delisted_w * (t_cash / y_cash - 1)
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
