#!/usr/bin/env python3
"""
CPM - Factor, Canary, Basket
Production allocation runner + backtest.

Usage:
    python cpm_live.py allocate                          # show this month's target weights
    python cpm_live.py allocate --signal-date 2026-04-30
    python cpm_live.py backtest                          # full backtest with all components
    python cpm_live.py backtest --start 2010-01-01 --out /tmp/fcp_out
    python cpm_live.py backtest --no-vol-target --no-cost
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
# Proxy panel (extends history pre-ETF-live via mutual fund proxies for some assets).
# In-repo path first (CI environments), fall back to external research artifacts dir (local dev).
LOCAL_PROXY = ROOT / "data" / "proxy_adjusted_close_daily.csv"
ARTIFACTS_PROXY = ROOT.parent / "artifacts" / "cpa-1997-exact-core-proxy-research" / "proxy_adjusted_close_daily.csv"
PROXY_PATH = LOCAL_PROXY if LOCAL_PROXY.exists() else ARTIFACTS_PROXY

# ---------- Configuration ----------
# CPM risky universe (8 risky ETFs): US factor + international + diversifiers.
# Universe binding: DBC (live 2006-02-03). Canonical backtest 2007-02-28
# (DBC live + 12mo signal warmup, 19.3y).
# HYG canary uses VWEHX mutual fund pre-2007-04 + live HYG post.
#
# CPM risky universe (8 assets, all live since 2006-02; DBC inception is the
# binding constraint).
#   US factor (2):     QQQ, SPHQ
#   International (2): EFA, EEM
#   Real estate (1):   VNQ
#   Diversifiers (3):  GLD, TLT, DBC
# Top-K candidates = ceil(N/2) = 4.
US_EQUITY = []
US_FACTOR = ["QQQ", "SPHQ"]
INTERNATIONAL = ["EFA", "EEM"]
REAL_ESTATE = ["VNQ"]
DIVERSIFIERS = ["GLD", "TLT", "DBC"]
RISKY_UNIVERSE = (US_EQUITY + US_FACTOR + INTERNATIONAL + REAL_ESTATE
                   + DIVERSIFIERS)
SAFE_POOL = ["SHV", "IEF"]      # HAA-style best-of-safe by 13612U momentum.

# CPM canary: HYG OR TIP (any positive, dual confirmation).
# Dual confirmation canary reduces false risk-on signals.
CANARY_ASSETS = ["HYG", "TIP"]
CANARY_RULE = "any_positive"  # "any_positive" or "all_positive"

DEFAULT_CASH = "SHV"

# Engine parameters
TOP_K_CANDIDATES = 4        # top-half of 8-asset universe (ceil(8/2))
CORR_LOOKBACK_DAYS = 252    # rolling covariance lookback for inverse-vol weights (~1y)
COST_BPS_PER_SIDE = 10
# Pinned research/backtest evaluation cutoff for reproducibility (memo clean-window end).
EVAL_END = pd.Timestamp("2026-05-22")

# Benchmark-only constants for Naive 60/40 PP/SPY-trend in build_dashboard.py.
# PRODUCTION strategy is 60% CPM + 20% BULL-SPY + 20% NDX.
PP_ASSETS = ["SPY", "IEF", "GLD", "SHV"]
PP_WEIGHTS = {"SPY": 0.25, "IEF": 0.25, "GLD": 0.25, "SHV": 0.25}


# ---------- Data loading ----------

def _download_adjusted_close(ticker: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.Series:
    """Download adjusted close series (same convention as stitched history)."""
    d = yf.download(
        ticker,
        start=start.strftime("%Y-%m-%d"),
        end=end.strftime("%Y-%m-%d"),
        auto_adjust=True,
        progress=False,
        threads=False,
    )
    if d is None or d.empty:
        return pd.Series(dtype=float, name=ticker)
    if isinstance(d.columns, pd.MultiIndex):
        if "Close" in d.columns.get_level_values(-1):
            c = d.xs("Close", axis=1, level=-1)
            if isinstance(c, pd.DataFrame):
                c = c.iloc[:, 0]
        else:
            c = d.iloc[:, 0]
    else:
        c = d["Close"] if "Close" in d.columns else d.iloc[:, 0]
    c = c.dropna()
    c.name = ticker
    return c


def _fetch_cached_adjusted_close(
    ticker: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
    cache_dir: str,
) -> pd.Series:
    """Range-cached adjusted close series keyed by ticker + date range."""
    start_ts = pd.Timestamp(start).normalize()
    end_ts = pd.Timestamp(end).normalize()
    if end_ts < start_ts:
        return pd.Series(dtype=float, name=ticker)

    cache_path = Path(cache_dir) / f"{ticker}_{start_ts.strftime('%Y-%m-%d')}_{end_ts.strftime('%Y-%m-%d')}.csv"
    if cache_path.exists():
        try:
            s = pd.read_csv(cache_path, parse_dates=[0], index_col=0).iloc[:, 0]
            s.name = ticker
            return s.dropna()
        except Exception:
            pass

    s = _download_adjusted_close(ticker, start_ts, end_ts)
    if not s.empty:  # never cache empty/failed pulls (avoids day-stable empty-cache poisoning)
        s.to_csv(cache_path, header=True)
    return s


def load_panel(start: pd.Timestamp = None, end: pd.Timestamp = None,
               cache_dir: str = "/tmp/cpm_cache", live: bool = False) -> pd.DataFrame:
    """Build the daily price panel from all sources.

    live=False: frozen in-repo data only (plus fully-missing columns, as before).
    live=True: append fresh per-ticker deltas after each column's last non-NaN date.
    """
    os.makedirs(cache_dir, exist_ok=True)

    # Long-history proxy panel (1995+)
    if PROXY_PATH.exists():
        panel = pd.read_csv(PROXY_PATH, parse_dates=["Date"], index_col="Date").sort_index()
    else:
        panel = pd.DataFrame()

    # Stitched series from data/ (overwrites same-named column in proxy panel).
    # HYG = VWEHX mutual fund pre-2007-04 + live HYG post.
    # GLD/TIP: clean stitches for canary usage pre-live-ETF.
    # Audited stitches (each replaces same-named column from proxy file):
    # - HYG <- VWEHX (Vanguard HY mutual fund), 1980-01+, auditable
    # - TIP <- VIPSX (Vanguard TIPS), 2000-06+, auditable
    # - SHV <- VFISX (Vanguard Short-Term Treasury), 1991-10+, auditable
    # - IEF <- VFITX (Vanguard Intermediate-Term Treasury), 1991-10+, auditable
    # - TLT <- VUSTX (Vanguard Long-Term Treasury), 1986-05+, auditable
    # - GLD <- partly documented stitch (2000-08+), pre-2000 still gap
    for fname, col in [
        ("gld_stitched_extended_daily.csv", "GLD"),  # World Bank monthly pre-2000-08
        ("tip_stitched_daily.csv", "TIP"),
        ("hyg_stitched_daily.csv", "HYG"),
        ("shv_stitched_daily.csv", "SHV"),
        ("ief_stitched_daily.csv", "IEF"),
        ("tlt_stitched_daily.csv", "TLT"),
        ("qqq_stitched_daily.csv", "QQQ"),  # NDX index proxy 1985-10 to 1999-03
    ]:
        fpath = DATA_DIR / fname
        if fpath.exists():
            s = pd.read_csv(fpath, parse_dates=[0], index_col=0)
            s.columns = [col]
            if panel.empty:
                panel = s.copy()
            elif col in panel.columns:
                # Overwrite existing column with stitched data
                panel = panel.drop(columns=[col]).join(s, how="outer").sort_index()
            else:
                panel = panel.join(s, how="outer").sort_index()

    needed = sorted(set(RISKY_UNIVERSE + SAFE_POOL + CANARY_ASSETS + PP_ASSETS + [DEFAULT_CASH]))
    present = set(panel.columns)
    missing = [t for t in needed if t not in present]

    pull_start = (start - pd.DateOffset(years=2)) if start else pd.Timestamp("1995-01-01")
    pull_end = end if end else pd.Timestamp.today() + pd.Timedelta(days=1)

    # Always backfill fully missing assets exactly as before.
    fetched_missing = {}
    for t in missing:
        try:
            s = _fetch_cached_adjusted_close(t, pull_start, pull_end, cache_dir)
            if not s.empty:
                fetched_missing[t] = s
        except Exception as e:
            print(f"WARN: could not fetch {t}: {e}", file=sys.stderr)

    if fetched_missing:
        extras = pd.DataFrame(fetched_missing)
        panel = panel.join(extras, how="outer").sort_index() if not panel.empty else extras

    # Live mode: refresh stale tails for assets that already exist in panel.
    if live and not panel.empty:
        for t in [x for x in needed if x in panel.columns]:
            col = panel[t]
            last_valid = col.last_valid_index()
            delta_start = pull_start if last_valid is None else last_valid
            if delta_start > pull_end:
                continue
            try:
                delta = _fetch_cached_adjusted_close(t, delta_start, pull_end, cache_dir)
                if delta.empty:
                    continue

                if last_valid is None:
                    panel = panel.reindex(panel.index.union(delta.index))
                    panel.loc[delta.index, t] = delta.values
                    continue

                ratio_date = None
                if last_valid in delta.index and pd.notna(delta.loc[last_valid]) and delta.loc[last_valid] != 0:
                    ratio_date = last_valid
                else:
                    overlap = col.dropna().index.intersection(delta.index)
                    for d in overlap:
                        if pd.notna(col.loc[d]) and pd.notna(delta.loc[d]) and delta.loc[d] != 0:
                            ratio_date = d
                            break

                if ratio_date is not None:
                    ratio = col.loc[ratio_date] / delta.loc[ratio_date]
                    delta = delta * ratio
                else:
                    print(f"WARN: no overlap to rescale live refresh for {t}; appending raw scale", file=sys.stderr)

                new_idx = delta.index[delta.index > last_valid]
                if len(new_idx) == 0:
                    continue

                prev_val = col.loc[last_valid]
                first_new_val = delta.loc[new_idx[0]]
                if pd.notna(prev_val) and prev_val != 0 and pd.notna(first_new_val):
                    first_ret = first_new_val / prev_val - 1.0
                    if abs(first_ret) > 0.50:
                        print(
                            f"WARN: rejected live refresh for {t}; first appended return {first_ret:+.2%} exceeds 50% guard",
                            file=sys.stderr,
                        )
                        continue

                panel = panel.reindex(panel.index.union(new_idx))
                panel.loc[new_idx, t] = delta.loc[new_idx].values
            except Exception as e:
                print(f"WARN: could not refresh {t}: {e}", file=sys.stderr)

    if start:
        panel = panel[panel.index >= start - pd.DateOffset(months=15)]  # keep warmup
    if end is not None:
        panel = panel[panel.index <= end]
    elif not live:
        panel = panel.loc[:EVAL_END]
    return panel.sort_index()


# ---------- Signals ----------

def faber_sma_xs(monthly: pd.DataFrame) -> pd.Series:
    """Cross-sectional Faber 10-month SMA distance: (price - SMA10) / SMA10."""
    if len(monthly) < 10:
        return pd.Series(np.nan, index=monthly.columns)
    sma = monthly.rolling(10).mean().iloc[-1]
    return (monthly.iloc[-1] - sma) / sma


def sig_13612U(p: pd.Series) -> float:
    """Canonical Keller HAA 13612U momentum: simple unweighted average of
    1/3/6/12-month total returns. Matches Keller & Keuning HAA paper (2022)."""
    p = p.dropna()
    if len(p) < 13:
        return np.nan
    last = p.iloc[-1]
    r1 = last / p.iloc[-2] - 1
    r3 = last / p.iloc[-4] - 1
    r6 = last / p.iloc[-7] - 1
    r12 = last / p.iloc[-13] - 1
    return (r1 + r3 + r6 + r12) / 4.0


def canary_positive_count(monthly: pd.DataFrame, canary_assets: list = None) -> int | None:
    """Number of canary assets with positive 13612U momentum.

    Used by canary_risk_state to map breadth into a 3-level regime state
    (OFF/WEAK/ON). Hold-buffer memory is reset across any regime transition
    so stale basket memory does not bridge a regime change.
    """
    canary_assets = canary_assets or CANARY_ASSETS
    scores = []
    for asset in canary_assets:
        if asset not in monthly.columns:
            continue
        score = sig_13612U(monthly[asset])
        if pd.notna(score):
            scores.append(score)
    if not scores:
        return None
    return sum(1 for score in scores if score > 0)


assert len(CANARY_ASSETS) >= 1, "CANARY_ASSETS must be non-empty"


def canary_risk_state(n_pos: int | None) -> str | None:
    """Map canary positive count -> risk state.

    Binary: ON (n_canary_pos >= 1) or OFF (n_canary_pos == 0). Generalizes cleanly to
    multi-canary configs; any state change in n_canary_pos can be used to invalidate
    memory in callers that track prior risk regime.
    """
    if n_pos is None:
        return None
    if n_pos == 0:
        return "OFF"
    return "ON"


def inv_vol_weights(close: pd.DataFrame, picks: list, lookback: int) -> dict:
    """Inverse-vol weights over `picks` using sigma_i from 252d covariance diag.

    Uses the same backward-only NaN handling as ranking-vol path:
      sigma_i = sqrt(diag(close[picks].ffill().pct_change().dropna(how='all').tail(lookback).cov()))
    Falls back to equal-weight if covariance/sigma is unavailable or degenerate.
    """
    if not picks:
        return {}
    rets = close[picks].ffill().pct_change().dropna(how="all").tail(lookback)
    if len(rets) < lookback:
        return {t: 1.0 / len(picks) for t in picks}
    cov = rets.cov()
    if cov.isna().any().any():
        return {t: 1.0 / len(picks) for t in picks}
    sigma = pd.Series(np.sqrt(np.diag(cov.values)), index=cov.index)
    inv = {}
    for t in picks:
        s = float(sigma.get(t, np.nan))
        if not np.isfinite(s) or s < 1e-12:
            return {tt: 1.0 / len(picks) for tt in picks}
        inv[t] = 1.0 / s
    z = float(sum(inv.values()))
    if not np.isfinite(z) or z <= 0:
        return {t: 1.0 / len(picks) for t in picks}
    return {t: inv[t] / z for t in picks}


def zscore(s: pd.Series) -> pd.Series:
    sd = s.std()
    if pd.isna(sd) or sd == 0:
        return pd.Series(0.0, index=s.index)
    return (s - s.mean()) / sd


def best_safe(monthly: pd.DataFrame, sig_d: pd.Timestamp, safe_pool: list) -> str:
    """Pick the best safe asset by 13612U momentum (HAA canonical, matches BULL).

    13612U = average of 1, 3, 6, 12-month total returns. Robustly identifies
    short-duration vs intermediate-duration regime preference for the safe leg.
    """
    sub = monthly.loc[:sig_d]
    available = [s for s in safe_pool if s in sub.columns and sub[s].first_valid_index() is not None]
    if not available:
        return DEFAULT_CASH
    if len(sub) < 13:
        return available[0]
    best_t, best_m = available[0], -np.inf
    for t in available:
        s = sub[t].dropna()
        if len(s) < 13:
            continue
        r1 = float(s.iloc[-1] / s.iloc[-2] - 1)
        r3 = float(s.iloc[-1] / s.iloc[-4] - 1)
        r6 = float(s.iloc[-1] / s.iloc[-7] - 1)
        r12 = float(s.iloc[-1] / s.iloc[-13] - 1)
        m = (r1 + r3 + r6 + r12) / 4
        if m > best_m:
            best_m, best_t = m, t
    return best_t


# ---------- Allocation logic ----------

def compute_target_weights(
    close_panel: pd.DataFrame,
    sig_d: pd.Timestamp,
    universe: list = None,
    safe_pool: list = None,
    canary_assets: list = None,
) -> tuple[dict, tuple, str, str]:
    """
    Returns: (weights, basket, regime, safe_ticker)
      regime: 'RISK_ON' | 'DEFENSIVE'
      weights: dict mapping ticker -> weight
    """
    universe = universe or RISKY_UNIVERSE
    safe_pool = safe_pool or SAFE_POOL
    canary_assets = canary_assets or CANARY_ASSETS
    
    monthly = close_panel.loc[:sig_d].resample("ME").last()
    safe = best_safe(monthly, sig_d, safe_pool)
    
    # Canary check: apply CANARY_RULE to canary 13612U states.
    canary_scores = []
    for c in canary_assets:
        if c not in monthly.columns:
            continue
        s = sig_13612U(monthly[c])
        if pd.notna(s):
            canary_scores.append(s)
    if not canary_scores:
        return {safe: 1.0}, None, "DEFENSIVE", safe
    n_canary_pos = sum(1 for s in canary_scores if s > 0)
    if CANARY_RULE == "any_positive":
        if n_canary_pos == 0:
            return {safe: 1.0}, None, "DEFENSIVE", safe  # defensive only when both HYG and TIP fail
    elif CANARY_RULE == "all_positive":
        if n_canary_pos < len(canary_scores):
            return {safe: 1.0}, None, "DEFENSIVE", safe
    else:  # "majority"
        if n_canary_pos <= len(canary_scores) // 2:
            return {safe: 1.0}, None, "DEFENSIVE", safe
    
    # Volatility-adjusted Faber ranker (EAA adoption):
    #   score(A) = faber_score(A) / vol_252d(A)
    # Penalizes high-volatility "junk momentum" to select stable trend leaders.
    # Volatility computed over trailing 252 trading days.
    faber = faber_sma_xs(monthly)
    avail = [t for t in universe
             if t in faber.index and pd.notna(faber[t])
             and pd.notna(close_panel.loc[sig_d].get(t, np.nan) if sig_d in close_panel.index else np.nan)]
    if not avail:
        return {safe: 1.0}, None, "DEFENSIVE", safe
    
    daily_rets = close_panel[avail].ffill().pct_change()
    scores = {}
    for t in avail:
        v = daily_rets[t].loc[:sig_d].tail(252).std() * np.sqrt(252)
        if pd.isna(v) or v < 1e-9:
            v = 1.0
        scores[t] = float(faber[t]) / v
    sa = pd.Series(scores)  # Vol-adjusted Faber score used for ranking
    ranked = sa.sort_values(ascending=False)
    top_k = max(2, min(TOP_K_CANDIDATES, len(ranked)))  # See TOP_K_CANDIDATES at top of file.
    top = ranked.iloc[:top_k]
    # Positive-momentum filter on raw faber score (not volatility-adjusted).
    positive = top[top.index.map(lambda t: faber.get(t, -np.inf) > 0)]
    
    # Strict-4 partial-safe fallback:
    #   risky fraction = min(n_picks, 4) / 4, safe fraction = 1 - risky fraction
    #   n_picks in {1,2,3}: hold all positives, inverse-vol weighted, then scale risky block
    #   n_picks=4: fully risky, inverse-vol across all 4 positives
    if len(positive) == 0:
        return {safe: 1.0}, None, "DEFENSIVE", safe

    picks = list(positive.index)
    n_picks = len(picks)
    risky_fraction = min(n_picks, 4) / 4.0
    safe_fraction = 1.0 - risky_fraction

    csub = close_panel.loc[:sig_d]
    risky_w = inv_vol_weights(csub, picks, CORR_LOOKBACK_DAYS)
    out = {t: w * risky_fraction for t, w in risky_w.items()}
    if safe_fraction > 0:
        out[safe] = out.get(safe, 0.0) + safe_fraction

    return out, tuple(picks), "RISK_ON", safe


# ---------- Backtest ----------


def compute_live_weights(
    panel: pd.DataFrame,
    sig_d: pd.Timestamp,
) -> tuple[dict, tuple, str, str]:
    """Production-correct allocation at sig_d.

    Returns (weights, basket, regime, safe). Used by `cpm_live allocate` and
    `format_message.py` to publish the live signal.
    """
    cols = sorted(set(RISKY_UNIVERSE + SAFE_POOL + CANARY_ASSETS + [DEFAULT_CASH]) & set(panel.columns))
    close = panel[cols]
    return compute_target_weights(close, sig_d)


def perf_metrics(daily: pd.Series, cash_daily: pd.Series = None) -> dict:
    if daily.empty:
        return {}
    eq = (1.0 + daily).cumprod() * 100_000.0
    days = (eq.index[-1] - eq.index[0]).days
    yrs = days / 365.25
    cagr = (eq.iloc[-1] / eq.iloc[0]) ** (1 / yrs) - 1 if yrs > 0 else float("nan")
    vol = daily.std(ddof=0) * np.sqrt(252)
    sharpe = (daily.mean() * 252) / vol if vol > 0 else float("nan")
    cash_aligned = cash_daily.reindex_like(daily).fillna(0.0) if cash_daily is not None else pd.Series(0.0, index=daily.index)
    excess_daily = daily - cash_aligned
    excess_vol = excess_daily.std(ddof=0) * np.sqrt(252)
    excess_sharpe = (excess_daily.mean() * 252) / excess_vol if excess_vol > 0 else float("nan")
    rm = eq.cummax()
    dd_series = eq / rm - 1
    mdd = dd_series.min()
    ulcer = float(np.sqrt(np.mean(dd_series ** 2)))
    calmar = cagr / abs(mdd) if mdd != 0 and not pd.isna(mdd) else float("nan")
    martin = cagr / ulcer if ulcer > 0 else float("nan")
    return {"total_return": eq.iloc[-1] / eq.iloc[0] - 1,
            "cagr": cagr, "vol": vol, "sharpe": sharpe, "excess_sharpe": excess_sharpe, "max_drawdown": mdd,
            "ulcer": ulcer, "calmar": calmar, "martin": martin}


def run_cpm_backtest(
    panel: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
    cost_bps: float = COST_BPS_PER_SIDE,
) -> tuple[pd.Series, list]:
    """Run CPM (no PP blend). Returns daily returns + diagnostics list.

    Execution model: signal at month-end close T (last trading day of month),
    rebalance executed at MOO of next trading day T+1 OPEN. Backtest uses
    close-to-close accounting on the apply_from day (close[T+1] / close[T] - 1),
    which assigns the T_eom -> T+1 overnight gap to the NEW weight vector.
    """
    cols = sorted(set(RISKY_UNIVERSE + SAFE_POOL + CANARY_ASSETS + [DEFAULT_CASH]) & set(panel.columns))
    close = panel[cols]
    
    monthly_idx = pd.DataFrame({"x": 1}, index=close.index).groupby(pd.Grouper(freq="ME")).tail(1)
    signal_dates = monthly_idx.index[(monthly_idx.index >= start) & (monthly_idx.index <= end)].tolist()
    
    weights_history = []
    canary_state = {}

    for i, sig_d in enumerate(signal_dates):
        w, new_basket, regime, safe = compute_target_weights(close, sig_d)
        canary_state[sig_d] = (regime == "RISK_ON")
        future = close.index[close.index > sig_d]
        if len(future) < 1:
            continue
        apply_from = future[0]  # T+1 OPEN (next trading day MOO)
        if i + 1 < len(signal_dates):
            next_sig = signal_dates[i + 1]
            next_future = close.index[close.index > next_sig]
            end_apply = next_future[0] if len(next_future) >= 1 else end
        else:
            end_apply = end
        weights_history.append({
            "apply_from": apply_from, "end_apply": end_apply,
            "weights": w, "sig_d": sig_d, "regime": regime, "safe": safe,
        })
    
    # Build daily return series
    all_assets = sorted({a for h in weights_history for a in h["weights"]})
    df_w = pd.DataFrame(0.0, index=close.index, columns=[a for a in all_assets if a in close.columns])
    sig_d_per_day = pd.Series(index=close.index, dtype=object)
    safe_per_day = pd.Series(index=close.index, dtype=object)
    
    for h in weights_history:
        mask = (close.index >= h["apply_from"]) & (close.index < h["end_apply"])
        for a, ww in h["weights"].items():
            if a in df_w.columns:
                df_w.loc[mask, a] = ww
        sig_d_per_day.loc[mask] = h["sig_d"]
        safe_per_day.loc[mask] = h["safe"]
    
    daily_ret = close.ffill().pct_change()
    common = [a for a in df_w.columns if a in daily_ret.columns]
    raw_returns = (df_w[common] * daily_ret[common]).sum(axis=1, min_count=1).fillna(0.0)
    
    # Apply trade costs
    for i in range(len(weights_history)):
        prev_w = weights_history[i - 1]["weights"] if i > 0 else {}
        curr_w = weights_history[i]["weights"]
        keys = set(curr_w) | set(prev_w)
        turnover = sum(abs(curr_w.get(k, 0.0) - prev_w.get(k, 0.0)) for k in keys)
        cost = turnover * cost_bps / 10000.0
        af = weights_history[i]["apply_from"]
        if af in raw_returns.index:
            raw_returns.loc[af] -= cost
    
    return raw_returns.loc[(raw_returns.index >= start) & (raw_returns.index <= end)], weights_history


def run_pp_backtest(panel: pd.DataFrame, start, end) -> pd.Series:
    """Static buffer: PP-IEF 25/25/25/25 SPY/IEF/GLD/SHV. Monthly rebalanced.

    Execution: T+1 OPEN (next-day MOO). Weights apply from future[0] of each
    signal date (first trading day after signal).
    """
    cols = [a for a in PP_ASSETS if a in panel.columns]
    if not cols:
        return pd.Series(dtype=float)
    close = panel[cols]
    monthly_idx = pd.DataFrame({"x": 1}, index=close.index).groupby(pd.Grouper(freq="ME")).tail(1)
    dates = monthly_idx.index[(monthly_idx.index >= start) & (monthly_idx.index <= end)].tolist()
    daily_ret = close.ffill().pct_change()
    out = pd.Series(0.0, index=close.index)
    # Renormalize PP_WEIGHTS over available cols (handles missing tickers gracefully)
    raw_w = {a: PP_WEIGHTS[a] for a in cols}
    total = sum(raw_w.values())
    w = pd.Series({a: v / total for a, v in raw_w.items()})
    for i, d in enumerate(dates):
        # T+1 OPEN: weights apply from future[0] of d (first trading day after signal)
        future_d = close.index[close.index > d]
        if len(future_d) < 1:
            continue
        seg_start = future_d[0]
        if i + 1 < len(dates):
            nxt = dates[i + 1]
            future_nxt = close.index[close.index > nxt]
            seg_end = future_nxt[0] if len(future_nxt) >= 1 else end
        else:
            seg_end = end
        seg = close.index[(close.index >= seg_start) & (close.index < seg_end)]
        out.loc[seg] = daily_ret.loc[seg, cols].mul(w, axis=1).sum(axis=1).fillna(0.0)
    return out.loc[(out.index >= start) & (out.index <= end)]


# ---------- CLI commands ----------

def cmd_allocate(args):
    """Print this month's target allocation."""
    sig_d = pd.Timestamp(args.signal_date) if args.signal_date else None
    panel = load_panel(end=sig_d, live=True)
    if sig_d is None:
        # Use most recent COMPLETED month-end as signal date.
        # (e.g. on May 14, signal date = April 30 close, trade for May)
        today = panel.index[-1]
        # Last day of prior month
        prior_month_end = (today.replace(day=1) - pd.Timedelta(days=1))
        # Find actual last trading day of that month in panel
        candidates = panel.index[panel.index <= prior_month_end]
        if len(candidates) == 0:
            sig_d = today  # fallback
        else:
            sig_d = candidates[-1]
        # Validate signal date has data for canary assets
        for c in CANARY_ASSETS:
            if c in panel.columns and pd.isna(panel.loc[sig_d, c]):
                # Walk back to last non-NaN date for canary
                valid = panel[c].loc[:sig_d].dropna()
                if len(valid) > 0:
                    sig_d = min(sig_d, valid.index[-1])
    print(f"CPM Allocation @ {sig_d.date()} (signal date)")
    print("=" * 60)
    
    # CPM weights (walk-forward with hold-buffer; matches backtest path)
    weights, basket, regime, safe = compute_live_weights(panel, sig_d)
    print(f"\n[CPM sleeve — 60% of PROD]")
    print(f"  Regime: {regime}")
    print(f"  Best safe: {safe}")
    if basket:
        print(f"  Selected risky basket: {' + '.join(basket)}")
    print(f"  Weights:")
    for t, w in sorted(weights.items(), key=lambda x: -x[1]):
        print(f"    {t:8s} {w*100:5.1f}%")

    # NOTE: This shows the CPM sleeve only (60% of PROD). For full
    # PROD allocation, use deploy/cf-pages/format_message.py or dashboard.
    print(f"\n[CPM sleeve only -- this is 60% of PROD]")
    print(f"  Full PROD allocation: see format_message.py or dashboard.")


def cmd_backtest(args):
    start = pd.Timestamp(args.start)
    end = pd.Timestamp(args.end) if args.end else None
    print(f"Loading panel ...")
    panel = load_panel(start=start, end=end)
    bt_end = end if end is not None else panel.index[-1]
    print(f"Panel: {panel.index[0].date()} -> {panel.index[-1].date()}, {len(panel.columns)} assets")
    
    print(f"\nRunning CPM-only backtest from {start.date()} to {bt_end.date()} ...")
    print(f"Execution model: T+1 OPEN (next-day MOO after month-end signal at T)")
    print(f"NOTE: This is CPM sleeve only (60% of PROD). For full PROD blend")
    print(f"      (60% CPM + 20% BULL-SPY + 20% NDX) use build_dashboard.py.")
    
    cost_bps = 0 if args.no_cost else COST_BPS_PER_SIDE
    cpm, _ = run_cpm_backtest(panel, start, bt_end, cost_bps=cost_bps)
    
    print(f"\n{'Strategy':25s} {'CAGR':>8s} {'Vol':>7s} {'Sharpe':>7s} {'MaxDD':>8s}")
    print("-" * 60)
    m = perf_metrics(cpm)
    print(f"{'CPM':25s} {m['cagr']*100:7.2f}% {m['vol']*100:6.2f}% {m['sharpe']:7.3f} {m['max_drawdown']*100:7.2f}%")

    # SPY benchmark
    if "SPY" in panel.columns:
        spy = panel["SPY"].ffill().pct_change().loc[start:bt_end].fillna(0.0)
        common = cpm.index.intersection(spy.index)
        spy_eq = spy.reindex(common)
        m = perf_metrics(spy_eq)
        print(f"{'SPY buy-hold':25s} {m['cagr']*100:7.2f}% {m['vol']*100:6.2f}% {m['sharpe']:7.3f} {m['max_drawdown']*100:7.2f}%")

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        df = pd.DataFrame({"CPM": cpm})
        df.to_csv(f"{out_path}_daily.csv")
        print(f"\nSaved daily returns: {out_path}_daily.csv")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    
    pa = sub.add_parser("allocate", help="Show target allocation for a given signal date")
    pa.add_argument("--signal-date", default=None, help="YYYY-MM-DD month-end (default: latest available)")
    pa.set_defaults(func=cmd_allocate)
    
    pb = sub.add_parser("backtest", help="Run full backtest")
    pb.add_argument("--start", default="2001-08-30")
    pb.add_argument("--end", default=None)
    pb.add_argument("--out", default=None, help="Output prefix (saves _daily.csv)")
    pb.add_argument("--no-vol-target", action="store_true")
    pb.add_argument("--no-cost", action="store_true")
    pb.set_defaults(func=cmd_backtest)
    
    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
