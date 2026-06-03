#!/usr/bin/env python3
"""
RPV Sleeve (Risk Premia Value) - 10% sleeve in candidate blends.
Calculates 120-month trailing z-scores of Term, Credit, and Equity risk premia.
"""
from __future__ import annotations

import os
import io
from functools import lru_cache
from pathlib import Path
from urllib.request import urlopen
import pandas as pd
import numpy as np
import cpm_live as cpm

DATA_DIR = Path(__file__).resolve().parent / "data"

# Configuration
W = 120  # 120-month trailing window
ZMIN = 36
LAG_E = 4
COST_BPS_PER_SIDE = 10.0

ASSET_OF = {
    "term": "TLT",
    "credit": "LQD",
    "equity": "SPY"
}

def load_macro_data() -> tuple[pd.Series, pd.Series, pd.Series, pd.Series, pd.Series, pd.Series]:
    """Load macro series: term/credit yields (DGS10, DGS3MO, DBAA), S&P500 index, and
    earnings (E) / price (P). Fetch ordering differs by source on purpose:
    - FRED yields: web-first (15s timeout) -> committed data/fred_*.csv fallback, so the
      LIVE signal gets the freshest daily yields; memoized upstream so it fetches once/run.
    - Earnings/prices: committed-first (data/sp500_earnings.csv) -> web fallback, since
      earnings move slowly (quarterly) and the committed series is authoritative.
    All paths return DatetimeIndex'd series; missing/failed fetches degrade to fallbacks."""

    def read_csv_url_timeout(url: str, timeout_s: float = 15.0) -> pd.DataFrame:
        with urlopen(url, timeout=timeout_s) as response:
            text = response.read().decode("utf-8")
        return pd.read_csv(io.StringIO(text))

    # 1. FRED Series
    def fetch_fred(id_: str) -> pd.Series:
        url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={id_}"
        fpath = DATA_DIR / f"fred_{id_}.csv"
        try:
            df = read_csv_url_timeout(url, timeout_s=15.0)
            df.columns = ["date", id_]
        except Exception:
            df = pd.read_csv(fpath)
            df.columns = ["date", id_]
        df["date"] = pd.to_datetime(df["date"])
        s = pd.to_numeric(df[id_], errors="coerce")
        s.index = df["date"]
        return s.dropna()

    dgs10 = fetch_fred("DGS10")
    dgs3mo = fetch_fred("DGS3MO")
    dbaa = fetch_fred("DBAA")
    
    # S&P500 index for ratio-scaling
    try:
        sp500 = fetch_fred("SP500")
    except Exception:
        # Fall back to DGS10 index or a placeholder if SP500 FRED fails
        sp500 = pd.Series(dtype=float, index=pd.DatetimeIndex([]))

    # 2. Earnings and Prices: prefer committed local file, then live fallback
    fpath_earnings = DATA_DIR / "sp500_earnings.csv"
    try:
        df_earn = pd.read_csv(fpath_earnings)
    except Exception:
        url_earnings = "https://raw.githubusercontent.com/datasets/s-and-p-500/main/data/data.csv"
        df_earn = read_csv_url_timeout(url_earnings, timeout_s=15.0)

    df_earn["Date"] = pd.to_datetime(df_earn["Date"])
    df_earn.set_index("Date", inplace=True)
    df_earn = df_earn.sort_index()

    E = pd.to_numeric(df_earn["Earnings"], errors="coerce")
    E = E.where(E > 0, np.nan).ffill().dropna()
    P = pd.to_numeric(df_earn["SP500"], errors="coerce").dropna()
    
    return dgs10, dgs3mo, dbaa, sp500, E, P

@lru_cache(maxsize=1)
def compute_rpv_signals() -> pd.DataFrame:
    # Memoized: FRED/earnings macro data + the trailing-z signal are identical for the
    # whole process run, so compute once and reuse. Without this, build_dashboard's
    # per-signal-date loop refetches FRED hundreds of times (the CI 'Computing sleeves' stall).
    """Computes the underlying macro risk premia (Term, Credit, Equity) and their trailing z-scores."""
    dgs10, dgs3mo, dbaa, sp500, E, P = load_macro_data()
    
    me = lambda s: s.resample("ME").last()
    dgs10_m = me(dgs10)
    dgs3mo_m = me(dgs3mo)
    dbaa_m = me(dbaa)
    sp500_m = me(sp500)
    
    # Process Earnings and Prices
    E_m = E.resample("ME").last()
    # Forward fill earnings and extend range with non-regressive ceiling.
    if not E_m.empty:
        ceiling = max(
            pd.Timestamp("2026-06-30"),
            pd.Timestamp.today().normalize() + pd.offsets.MonthEnd(0),
            E_m.index.max(),
        )
        # 120-month trailing z-window: appending future months cannot change
        # any z-row dated <= 2026-06-30; this only extends forward coverage.
        E_m = E_m.reindex(pd.date_range(E_m.index.min(), ceiling, freq="ME")).ffill()
    
    P_m = P.resample("ME").last()
    if not sp500_m.empty:
        ov = P_m.index.intersection(sp500_m.index)
        if len(ov) > 0:
            k = P_m.loc[ov[-1]] / sp500_m.loc[ov[-1]]
            P_m = pd.concat([P_m, sp500_m[sp500_m.index > P_m.index.max()] * k]).sort_index().ffill()
            
    EY = (100.0 * (E_m.shift(LAG_E) / P_m)).dropna()
    
    rp = pd.DataFrame({
        "term": (dgs10_m - dgs3mo_m),
        "credit": (dbaa_m - dgs10_m),
        "equity": (EY - dgs10_m)
    }).dropna().sort_index()
    
    # 120-month rolling z-score
    def trailing_z(df: pd.DataFrame, w: int) -> pd.DataFrame:
        return df.apply(lambda s: (s - s.rolling(w).mean()) / s.rolling(w).std(ddof=0))
        
    Z = trailing_z(rp, W).dropna().iloc[ZMIN:]
    return Z

def compute_rpv_weights(close_panel: pd.DataFrame, sig_d: pd.Timestamp) -> tuple[dict, str, dict]:
    """Returns target weights, regime label, and diagnostics for a given signal date.
    Weighted scheme with 200d trend guard."""
    Z = compute_rpv_signals()
    if sig_d not in Z.index:
        # fallback to closest prior signal date
        valid_ds = Z.index[Z.index <= sig_d]
        if len(valid_ds) == 0:
            return {"SHV": 1.0}, "CASH", {}
        sig_d = valid_ds[-1]
        
    zrow = Z.loc[sig_d]
    pos = zrow.clip(lower=0.0)
    tot = pos.sum()
    
    # 1. Base weights
    if tot <= 0:
        base_w = {"SHV": 1.0}
    else:
        base_w = {}
        for kk, v in pos.items():
            if v > 0:
                asset = ASSET_OF[kk]
                base_w[asset] = base_w.get(asset, 0.0) + v / tot
                
    # 2. SMA 200 guard filter
    prices = close_panel[["SPY", "TLT", "LQD", "SHV"]].sort_index().ffill()
    sma200 = prices[["SPY", "TLT", "LQD"]].rolling(200).mean()
    above_sma = (prices[["SPY", "TLT", "LQD"]] > sma200)
    
    guarded_w = {}
    for a, wt in base_w.items():
        if a in ("SPY", "TLT", "LQD"):
            ok = above_sma[a].loc[:sig_d]
            is_above = bool(ok.iloc[-1]) if len(ok) and pd.notna(ok.iloc[-1]) else False
            if is_above:
                guarded_w[a] = guarded_w.get(a, 0.0) + wt
            else:
                guarded_w["SHV"] = guarded_w.get("SHV", 0.0) + wt
        else:
            guarded_w[a] = guarded_w.get(a, 0.0) + wt
            
    regime = "WEIGHTED_GUARDED" if "SHV" not in guarded_w or guarded_w["SHV"] < 1.0 else "CASH"
    diag = {
        "z_scores": zrow.to_dict(),
        "base_weights": base_w,
        "guarded_weights": guarded_w
    }
    return guarded_w, regime, diag

def run_rpv_backtest(panel: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp, cost_bps: float = COST_BPS_PER_SIDE) -> pd.Series:
    """Runs backtest of RPV Weighted Guarded sleeve with T+1 MOO + turnover cost."""
    prices = panel[["SPY", "TLT", "LQD", "SHV"]].sort_index().ffill()

    Z = compute_rpv_signals()
    sig_dates = Z.index[Z.index <= end]

    full_idx = prices.loc[:end].index
    trade_idx = prices.loc[start:end].index
    daily_rets = pd.Series(0.0, index=full_idx)
    weights_for_date: dict[pd.Timestamp, dict] = {}

    for sd in sig_dates:
        target, _, _ = compute_rpv_weights(panel, sd)
        future = full_idx[full_idx > sd]
        if len(future) >= 1:
            weights_for_date[future[0]] = target

    exec_dates = sorted(weights_for_date.keys())
    cur_w = {"SHV": 1.0}
    cur_w_idx = 0

    for ts in full_idx:
        while cur_w_idx < len(exec_dates) and exec_dates[cur_w_idx] <= ts:
            new_w = weights_for_date[exec_dates[cur_w_idx]]
            if cur_w != new_w and cost_bps > 0:
                tovr = sum(
                    abs(cur_w.get(a, 0.0) - new_w.get(a, 0.0))
                    for a in set(cur_w) | set(new_w)
                )
                daily_rets.loc[ts] -= tovr * cost_bps / 10000.0
            cur_w = new_w
            cur_w_idx += 1

        prev_loc = prices.index.get_loc(ts)
        if prev_loc == 0:
            continue
        prev_d = prices.index[prev_loc - 1]

        port_r = 0.0
        for asset, w in cur_w.items():
            today = prices.loc[ts, asset]
            yest = prices.loc[prev_d, asset]
            if pd.notna(today) and pd.notna(yest) and yest > 0:
                port_r += w * (today / yest - 1)
        daily_rets.loc[ts] += port_r

    return daily_rets.loc[trade_idx]
