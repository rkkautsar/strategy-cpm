#!/usr/bin/env python3
"""
CPM - Factor, C1 Cliff Breadth, Basket
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
from itertools import combinations
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
# TIP canary uses VIPSX mutual fund stitch pre-live ETF period.
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

# CPM canary: DISABLED (de-canary C1, 2026-06-05). CPM now self-de-risks via the
# C1 cliff in risky_fraction (breadth of its own top-K picks), removing the single
# TIP signal that previously gated ~90% of the blend. CANARY_ASSETS kept only so
# compute_live_weights still includes TIP in the panel columns (harmless, not a gate).
CANARY_ASSETS = ["TIP"]
CANARY_RULE = "disabled"  # de-canary: gate moved into the risky_fraction C1 cliff
# C1 cliff: top-K positive-faber breadth -> risky fraction; <=2 positives -> 100% safe.
CPM_RISKY_FRACTION_CURVE = {1: 0.0, 2: 0.0, 3: 0.5, 4: 1.0}

DEFAULT_CASH = "SHV"

# Engine parameters
TOP_K_CANDIDATES = 4        # top-half of 8-asset universe (ceil(8/2))
CORR_LOOKBACK_DAYS = 252    # rolling covariance lookback (~1y)
COST_BPS_PER_SIDE = 10
# Pinned research/backtest evaluation cutoff for reproducibility (memo clean-window end).
# Invariant: EVAL_END must be a trading day present in all RISKY_UNIVERSE +
# SAFE_POOL + CANARY_ASSETS feeds; frozen-path freshness guard asserts
# last-valid >= EVAL_END for every required asset.
EVAL_END = pd.Timestamp("2026-04-30")

# Production blend weights.
from config import CPM_WEIGHT, NDX_WEIGHT, VAL_WEIGHT, RPV_WEIGHT

# Benchmark-only constants for Naive 60/40 PP/SPY-trend in build_dashboard.py.
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
        timeout=30,
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


def _live_freshness_floor(reference_date: pd.Timestamp) -> pd.Timestamp:
    """Freshness floor for live-panel publish checks.

    If reference_date is a business month-end signal date, require freshness to that
    exact day. Otherwise require freshness to the latest completed business month-end.
    """
    ref = pd.Timestamp(reference_date).normalize()
    bme = pd.offsets.BMonthEnd()
    if bme.is_on_offset(ref):
        return ref
    return ref - pd.offsets.BMonthEnd(1)


def _assert_live_panel_fresh(
    panel: pd.DataFrame,
    reference_date: pd.Timestamp,
    required_assets: list[str],
) -> None:
    """Fail loud when live panel cannot support current publish signal timing."""
    freshness_floor = _live_freshness_floor(reference_date)
    stale_assets = []
    for asset in required_assets:
        if asset not in panel.columns:
            stale_assets.append((asset, None))
            continue
        last_valid = panel[asset].last_valid_index()
        if last_valid is None or last_valid < freshness_floor:
            stale_assets.append((asset, last_valid))
    if stale_assets:
        stale_msg = ", ".join(
            f"{asset}={(lv.date().isoformat() if lv is not None else 'missing')}"
            for asset, lv in stale_assets
        )
        raise ValueError(
            "Live panel stale for publish path; "
            f"expected last-valid >= {freshness_floor.date().isoformat()} "
            "for all required assets (RISKY_UNIVERSE+SAFE_POOL+CANARY_ASSETS). "
            f"reference_date={pd.Timestamp(reference_date).date().isoformat()}. "
            f"{stale_msg}"
        )


from data_loader import load_panel


# ---------- Signals ----------

def faber_sma_xs(monthly: pd.DataFrame) -> pd.Series:
    """Cross-sectional Faber 10-month SMA distance: (price - SMA10) / SMA10."""
    if len(monthly) < 10:
        return pd.Series(np.nan, index=monthly.columns)
    sma = monthly.rolling(10).mean().iloc[-1]
    return (monthly.iloc[-1] - sma) / sma


from core import sig_13612U


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


def _ret_window(close, picks, lookback):
    """Trailing return matrix, mirrors cpm_live.inv_vol_weights window exactly."""
    rets = close[picks].ffill().pct_change().dropna(how="all").tail(lookback)
    return rets


def _min_var_subset(close, sig_d, candidates, lookback, m):
    """Minimize equal-weight portfolio variance over m-of-candidates."""
    if len(candidates) <= m:
        return list(candidates)
    rets = _ret_window(close.loc[:sig_d], candidates, lookback)
    if len(rets) < lookback:
        return list(candidates)
    cov = rets.cov()
    if cov.isna().any().any():
        return list(candidates)
    w = 1.0 / m
    best, best_v = None, np.inf
    for combo in combinations(candidates, m):
        sub = cov.loc[list(combo), list(combo)].values
        v = float(w * w * sub.sum())
        if v < best_v:
            best_v, best = v, combo
    return list(best) if best else list(candidates)


def zscore(s: pd.Series) -> pd.Series:
    sd = s.std()
    if pd.isna(sd) or sd == 0:
        return pd.Series(0.0, index=s.index)
    return (s - s.mean()) / sd


def best_safe(monthly: pd.DataFrame, sig_d: pd.Timestamp, safe_pool: list) -> str:
    """Pick the best safe asset by 13612U momentum (HAA canonical, matches RPV).

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
    
    # De-canary (C1): no external canary gate. CPM self-de-risks via the C1 cliff
    # in risky_fraction below (breadth of its own top-K picks; <=2 positive -> safe).

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
    #   risky fraction = min(n_pos, 4) / 4, safe fraction = 1 - risky fraction
    #   n_pos in {1,2,3}: hold all positives, equal-weighted, then scale risky block
    #   full breadth + full risk: min-var 3-of-4 (equal-weight variance objective)
    if len(positive) == 0:
        return {safe: 1.0}, None, "DEFENSIVE", safe

    positive_picks = list(positive.index)
    n_pos = len(positive_picks)
    # C1 cliff de-risk (replaces TIP canary): <=2 positive top-K picks -> 100% safe.
    risky_fraction = CPM_RISKY_FRACTION_CURVE.get(min(n_pos, 4), 0.0)
    if risky_fraction <= 1e-12:
        return {safe: 1.0}, None, "DEFENSIVE", safe
    if n_pos == TOP_K_CANDIDATES and risky_fraction == 1.0:
        # min-variance / vol-covariance excision gated by full breadth (n_pos==top_k) + full risk (risky_fraction==1.0)
        picks = _min_var_subset(close_panel, sig_d, positive_picks, CORR_LOOKBACK_DAYS, 3)
    else:
        picks = positive_picks

    safe_fraction = 1.0 - risky_fraction

    risky_w = {t: 1.0 / len(picks) for t in picks}
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


from core import perf_metrics


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
    from ndx_sleeve_live import compute_ndx_weights, load_ndx_panel
    from rpv_live import compute_rpv_weights
    from core import cached_value_backtest

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

    ndx_panel = load_ndx_panel()

    # Sleeve weights
    from sleeves import compute_live_blend
    combined, res = compute_live_blend(panel, ndx_panel, sig_d)
    cpm_res, ndx_res, val_res, rpv_res = res["cpm"], res["ndx"], res["val"], res["rpv"]
    cpm_w, basket, cpm_regime, safe = cpm_res.weights, cpm_res.extra["basket"], cpm_res.regime, cpm_res.extra["safe"]
    ndx_w, ndx_regime, ndx_diag = ndx_res.weights, ndx_res.regime, ndx_res.extra["diag"]
    rpv_w, rpv_regime, rpv_diag = rpv_res.weights, rpv_res.regime, rpv_res.extra["diag"]
    val_w, val_regime, val_picks = val_res.weights, val_res.regime, val_res.picks

    print(f"CPM-NDX-VAL-RPV Allocation @ {sig_d.date()} (signal date)")
    print("=" * 60)

    print(f"\n[CPM sleeve — {int(CPM_WEIGHT*100)}%]")
    print(f"  Regime: {cpm_regime}")
    print(f"  Best safe: {safe}")
    if basket:
        print(f"  Selected risky basket: {' + '.join(basket)}")
    for t, w in sorted(cpm_w.items(), key=lambda x: -x[1]):
        print(f"    {t:8s} {w*100:5.1f}%")

    print(f"\n[NDX sleeve — {int(NDX_WEIGHT*100)}%]")
    print(f"  Regime: {ndx_regime}")
    if ndx_diag.get("selected"):
        print(f"  Picks: {', '.join(ndx_diag['selected'])}")
    for t, w in sorted(ndx_w.items(), key=lambda x: -x[1]):
        print(f"    {t:8s} {w*100:5.1f}%")

    print(f"\n[VAL sleeve — {int(VAL_WEIGHT*100)}%]")
    print(f"  Regime: {val_regime}")
    if val_picks:
        print(f"  Picks: {', '.join(val_picks)}")
    for t, w in sorted(val_w.items(), key=lambda x: -x[1]):
        print(f"    {t:8s} {w*100:5.1f}%")

    print(f"\n[RPV sleeve — {int(RPV_WEIGHT*100)}%]")
    print(f"  Regime: {rpv_regime}")
    if rpv_diag.get("eligible"):
        print(f"  Picks: {', '.join(rpv_diag['eligible'])}")
    for t, w in sorted(rpv_w.items(), key=lambda x: -x[1]):
        print(f"    {t:8s} {w*100:5.1f}%")

    print("\n[Combined target — 100%]")
    for t, w in sorted(combined.items(), key=lambda x: -x[1]):
        print(f"    {t:8s} {w*100:5.1f}%")
    print(f"\n  Weight sum: {sum(combined.values()):.6f}")


def cmd_backtest(args):
    from ndx_sleeve_live import load_ndx_panel, run_ndx_backtest
    from rpv_live import run_rpv_backtest
    from core import cached_value_backtest

    start = pd.Timestamp(args.start)
    end = pd.Timestamp(args.end) if args.end else None
    print(f"Loading panel ...")
    panel = load_panel(start=start, end=end)
    bt_end = end if end is not None else panel.index[-1]
    print(f"Panel: {panel.index[0].date()} -> {panel.index[-1].date()}, {len(panel.columns)} assets")

    print(f"\nRunning CPM-NDX-VAL-RPV backtest from {start.date()} to {bt_end.date()} ...")
    print(f"Execution model: T+1 OPEN (next-day MOO after month-end signal at T)")

    cost_bps = 0 if args.no_cost else COST_BPS_PER_SIDE
    cpm, _ = run_cpm_backtest(panel, start, bt_end, cost_bps=cost_bps)
    ndx_panel = load_ndx_panel()
    ndx, _ = run_ndx_backtest(panel, ndx_panel, start, bt_end, cost_bps=cost_bps)
    rpv = run_rpv_backtest(panel, start, bt_end, cost_bps=cost_bps)
    val, _ = cached_value_backtest(panel, ndx_panel, start, bt_end, cost_bps=cost_bps)

    common = cpm.index.intersection(ndx.index).intersection(rpv.index).intersection(val.index)
    cpm = cpm.reindex(common).fillna(0.0)
    ndx = ndx.reindex(common).fillna(0.0)
    rpv = rpv.reindex(common).fillna(0.0)
    val = val.reindex(common).fillna(0.0)
    blend = CPM_WEIGHT * cpm + NDX_WEIGHT * ndx + VAL_WEIGHT * val + RPV_WEIGHT * rpv

    print(f"\n{'Strategy':25s} {'CAGR':>8s} {'Vol':>7s} {'Sharpe':>7s} {'MaxDD':>8s}")
    print("-" * 60)
    for name, series in [
        (f"PROD {int(CPM_WEIGHT*100)}/{int(NDX_WEIGHT*100)}/{int(VAL_WEIGHT*100)}/{int(RPV_WEIGHT*100)}", blend),
        ("CPM sleeve", cpm),
        ("NDX sleeve", ndx),
        ("VAL sleeve", val),
        ("RPV sleeve", rpv),
    ]:
        m = perf_metrics(series)
        print(f"{name:25s} {m['cagr']*100:7.2f}% {m['vol']*100:6.2f}% {m['sharpe']:7.3f} {m['max_drawdown']*100:7.2f}%")

    if "SPY" in panel.columns:
        spy = panel["SPY"].ffill().pct_change().loc[start:bt_end].fillna(0.0)
        common_spy = blend.index.intersection(spy.index)
        spy_eq = spy.reindex(common_spy)
        m = perf_metrics(spy_eq)
        print(f"{'SPY buy-hold':25s} {m['cagr']*100:7.2f}% {m['vol']*100:6.2f}% {m['sharpe']:7.3f} {m['max_drawdown']*100:7.2f}%")

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        df = pd.DataFrame({
            "PROD": blend,
            "CPM": cpm,
            "NDX": ndx,
            "VAL": val,
            "RPV": rpv,
        })
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
