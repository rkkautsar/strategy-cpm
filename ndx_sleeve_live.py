"""NDX sleeve (20% of 60/20/20 PROD blend).

Spec:
  1. Universe: PIT Nasdaq-100 constituents via index-constitution lib (2006-01+)
  2. Signal:   Raw 13612U momentum per stock (no correlation penalty)
  3. Gate:     TIP canary + SPY trend + SPY RV20<RV252; else best-of-safe (SHV/IEF)
  4. PIT fallback: when PIT data is unavailable and gate is ON, use SPY proxy.
  5. Selection: top-K by raw momentum score, equal-weighted 1/K each.
  6. Partial fill: if fewer than K positive candidates, take what's there at
     1/K=20% per pick, rest in best-of-safe (e.g. 2 positives -> 40% stocks
     + 60% best-safe).
  7. Monthly rebalance, T+1 OPEN execution (next-day MOO), 10bps/side cost.
"""
from __future__ import annotations
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import index_constitution as ic

from cpm_live import DEFAULT_CASH, SAFE_POOL
from core import sig_13612U

ROOT = Path(__file__).resolve().parent
PRICES_FILE = ROOT / "data" / "ndx_constituents" / "prices.parquet"

# Spec config
SPY_TICKER = "SPY"
VOL_FAST_DAYS = 20
VOL_SLOW_DAYS = 252
SELECT_K = 5              # top-K by raw momentum score, equal-weighted (20% per pick
                          # within sleeve = 4% portfolio at 20% blend weight;
                          # caps single-name bankruptcy impact at ~4% portfolio)
COST_BPS_PER_SIDE = 10
DELISTING_HAIRCUT = -0.10  # applied to a held position when the ticker stops
                           # quoting mid-period; rough blended estimate across
                           # NDX historical delistings (mix of acquisitions at
                           # a premium and bankruptcies near 0).
CASH_TICKER = DEFAULT_CASH


def _pick_safe(monthly: pd.DataFrame) -> str:
    """Pick safe asset with strongest 13612U score; fallback to CASH_TICKER."""
    scores = {}
    for asset in SAFE_POOL:
        if asset in monthly.columns:
            score = sig_13612U(monthly[asset])
            if pd.notna(score):
                scores[asset] = score
    return max(scores, key=scores.get) if scores else CASH_TICKER


def _ndx_vol_gate_ok(daily_spy: pd.Series, sig_d: pd.Timestamp) -> tuple[bool, dict]:
    """NDX-local volatility gate: RV20<RV252 on SPY daily returns."""
    sub = daily_spy.loc[:sig_d].pct_change().dropna()
    if len(sub) < VOL_SLOW_DAYS:
        return True, {"warmup": True, "rv_20": float("nan"), "rv_252": float("nan")}
    rv_20 = float(sub.tail(VOL_FAST_DAYS).std() * np.sqrt(252))
    rv_252 = float(sub.tail(VOL_SLOW_DAYS).std() * np.sqrt(252))
    vol_ok = rv_20 < rv_252
    return vol_ok, {"rv_20": rv_20, "rv_252": rv_252, "vol_ok": vol_ok}


from data_loader import load_ndx_panel


def refresh_ndx_panel(start: str = "1995-01-01") -> pd.DataFrame:
    """Refresh NDX constituent prices by stitching a short live tail onto committed history."""
    import yfinance as yf

    # Do not rebuild prices.parquet from empty state: fresh fetch returns only current constituents and biases history.
    try:
        base = load_ndx_panel().sort_index()
    except FileNotFoundError:
        base = pd.DataFrame()

    as_of = pd.Timestamp.today().strftime("%Y-%m-%d")
    current_df = ic.constituents_at("nasdaq100", as_of)
    current = sorted(map(str, current_df["symbol"].unique()))

    base_cols = set(map(str, base.columns)) if not base.empty else set()
    tail_tickers = [t for t in current if t in base_cols]
    full_tickers = [t for t in current if t not in base_cols]
    print(
        f"NDX tail: fetching {len(current)} current constituents "
        f"({len(tail_tickers)} tail, {len(full_tickers)} full)."
    )

    tail_start = start
    if not base.empty:
        base_last = pd.Timestamp(base.index.max())
        tail_start = (base_last - pd.Timedelta(days=5)).strftime("%Y-%m-%d")
        print(f"NDX prices tail refresh start={tail_start} (base_max={base_last.date().isoformat()})")

    def _fetch_closes(tickers: list[str], fetch_start: str) -> pd.DataFrame:
        if not tickers:
            return pd.DataFrame()
        chunks = [tickers[i:i + 30] for i in range(0, len(tickers), 30)]
        all_dfs = []
        for chunk in chunks:
            try:
                df = yf.download(
                    chunk,
                    start=fetch_start,
                    auto_adjust=True,
                    progress=False,
                    threads=True,
                    group_by="ticker",
                    timeout=60,
                )
                if isinstance(df.columns, pd.MultiIndex):
                    close = df.xs("Close", axis=1, level=1)
                else:
                    close = df[["Close"]].rename(columns={"Close": chunk[0]})
                if close.empty:
                    continue
                all_dfs.append(close)
            except Exception as e:
                print(f"  WARN chunk {chunk[:3]}...: {e}", file=sys.stderr)

        if not all_dfs:
            return pd.DataFrame()

        out = pd.concat(all_dfs, axis=1)
        out = out.loc[:, ~out.columns.duplicated()]
        return out.sort_index()

    tail = _fetch_closes(tail_tickers, tail_start)
    full = _fetch_closes(full_tickers, "1995-01-01")

    panel = base.copy() if not base.empty else pd.DataFrame()
    for fresh in (tail, full):
        if fresh.empty:
            continue
        if panel.empty and len(panel.columns) == 0:
            panel = fresh.sort_index()
            continue
        panel = panel.reindex(panel.index.union(fresh.index)).sort_index()
        for col in fresh.columns:
            if col not in panel.columns:
                panel[col] = np.nan
        panel.update(fresh)

    if panel.empty:
        raise RuntimeError("Failed to fetch NDX constituent closes and no committed snapshot is available.")

    panel = panel.loc[~panel.index.duplicated(keep="last")]
    panel = panel.loc[:, ~panel.columns.duplicated()]
    if not base.empty:
        base_order = list(base.columns)
        new_cols = sorted([c for c in panel.columns if c not in base_order])
        panel = panel.reindex(columns=base_order + new_cols)

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
      - NDX gate ON (TIP canary + SPY trend + SPY RV20<RV252) -> select top-K
      - NDX gate OFF                                           -> 100% best-of-safe
    """
    # Step 1: NDX-local activation gate (decoupled from RPV sleeve weights).
    cpm_monthly = cpm_panel.loc[:sig_d].resample("ME").last()
    safe = _pick_safe(cpm_monthly)

    tip_sig = sig_13612U(cpm_monthly["TIP"]) if "TIP" in cpm_monthly.columns else float("nan")
    canary_ok = pd.notna(tip_sig) and tip_sig > 0
    spy_sig = sig_13612U(cpm_monthly[SPY_TICKER]) if SPY_TICKER in cpm_monthly.columns else float("nan")
    trend_ok = pd.notna(spy_sig) and spy_sig > 0

    if SPY_TICKER in cpm_panel.columns:
        vol_ok, vdiag = _ndx_vol_gate_ok(cpm_panel[SPY_TICKER], sig_d)
    else:
        vol_ok, vdiag = False, {"rv_20": float("nan"), "rv_252": float("nan"), "vol_ok": False, "missing_spy": True}

    gate_on = canary_ok and trend_ok and vol_ok
    gate_diag = {
        "tip_sig": tip_sig,
        "spy_sig": spy_sig,
        "canary_ok": canary_ok,
        "trend_ok": trend_ok,
        **vdiag,
        "ndx_gate_on": gate_on,
    }

    if not gate_on:
        reasons = []
        if not canary_ok:
            reasons.append("canary_off")
        if not trend_ok:
            reasons.append("spy_trend_off")
        if not vol_ok:
            reasons.append("vol20_crossover_off")
        return ({safe: 1.0}, "GATE_OFF (NDX_defensive)", {
            **gate_diag,
            "selected": [],
            "reason": "; ".join(reasons),
            "picked_safe": safe,
        })

    # Step 2: PIT NDX membership at signal date.
    pit = ic.constituents_at("nasdaq100", sig_d.strftime("%Y-%m-%d"))
    pit_tickers = set(pit["symbol"].tolist())
    if len(pit_tickers) == 0:
        proxy_weights = {SPY_TICKER: 1.0}
        return (proxy_weights, "NDX_FALLBACK_SPY", {
            **gate_diag,
            "selected": [SPY_TICKER],
            "reason": "PIT NDX data unavailable; using SPY proxy",
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

    # Step 3: Compute raw 13612U momentum scores.
    momenta = {}
    for t in available:
        s = monthly[t].dropna()
        if len(s) < 13:
            continue
        m = sig_13612U(s)
        if pd.notna(m) and m > 0:
            momenta[t] = m

    # Step 4: top SELECT_K by raw momentum score, equal-weight 1/SELECT_K each.
    # Partial fill (CPM-style) if < SELECT_K positive candidates; rest in safe.
    sorted_by_mom = sorted(momenta.items(), key=lambda x: -x[1])
    n_pick = min(len(sorted_by_mom), SELECT_K)
    selected = [t for t, _ in sorted_by_mom[:n_pick]]
    per_slot = 1.0 / SELECT_K
    weights = {t: per_slot for t in selected}
    cash_share = 1.0 - n_pick * per_slot
    if cash_share > 1e-9:
        weights[safe] = weights.get(safe, 0.0) + cash_share

    regime = "NDX_ACTIVE" if n_pick == SELECT_K else f"NDX_PARTIAL_{n_pick}"
    return (weights, regime, {
        **gate_diag,
        "n_candidates": len(sorted_by_mom),
        "selected": selected,
        "momenta": {t: momenta[t] for t in selected},
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
    # timestamps) for correct alignment with CPM/RPV signal dates.
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
                # merger, or bankruptcy). Apply DELISTING_HAIRCUT as a one-time
                # liquidation hit, then convert proceeds to the period's
                # existing safe (or CASH_TICKER if no safe was held).
                port_r += w * DELISTING_HAIRCUT
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
    if regime == "NDX_ACTIVE" or regime.startswith("NDX_PARTIAL"):
        print("Gate state: "
              f"canary={diag.get('canary_ok')} "
              f"trend={diag.get('trend_ok')} "
              f"vol20<252={diag.get('vol_ok')}")
        print(f"\nTop-{SELECT_K} by raw 13612U momentum:")
        for t in diag["selected"]:
            score = diag["momenta"][t]
            weight_pct = weights[t] * 100
            print(f"  {t:<6} weight {weight_pct:.0f}%  momentum {score*100:+.2f}%")
    else:
        top_asset = next(iter(weights.keys()), CASH_TICKER)
        print(f"  100% {top_asset}")
        print(f"  Reason: {diag.get('reason', '-')}")
