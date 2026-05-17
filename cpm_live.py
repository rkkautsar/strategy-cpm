#!/usr/bin/env python3
"""
CPM - Factor, Canary, Pair
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
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
ARTIFACTS_PROXY = ROOT.parent / "artifacts" / "cpa-1997-exact-core-proxy-research" / "proxy_adjusted_close_daily.csv"

# ---------- Configuration ----------
# US factor universe: 7 names selected for clean live-data history and
# positive selection rate in min-var pair audit. All ETFs live since 2005 or
# earlier (no SPY-proxy contamination in backtest).
US_FACTORS = [
    "QQQ", "IGM", "XLE", "VBR", "SPHQ", "XMHQ", "XLV",
]

# International: regime hedge for periods when US factor leadership wanes.
INTERNATIONAL = ["VEA", "VWO"]

DIVERSIFIERS = ["GLD", "TLT"]
RISKY_UNIVERSE = US_FACTORS + INTERNATIONAL + DIVERSIFIERS  # 11 risky
SAFE_POOL = ["SHV"]            # Single-asset cash mode (unified with BULL-QQQ).
                                # Best-of-4 rotation (was [BIL,SHV,SHY,IEF])
                                # captured ~0.03 Sh of bootstrap-noise alpha;
                                # dropped for spec simplicity + oracle-v4
                                # "zero-duration defensive" narrative.
# HYG_stitched = VWEHX pre-2007-04 + live HYG post (high-yield credit signal).
# 3-asset canary: HYG (credit), TIP (inflation), GLD (real-asset/tail).
# GLD added based on 2026 review showing -3% 2023 return when canary off forced
# CPM into TLT-defensive pair during rate-rising regime. With GLD in canary:
#   2023: -3.10% -> +6.23%, 2008: +2.38% -> +4.73%, 2022: -2.65% -> -1.21%
# Bond/credit-based canary chosen because SPY momentum is already gated by
# the universe's positive-momentum filter (adding SPY to canary is redundant).
# Note: GLD addition is HARMFUL for BULL-QQQ canary (lone-GLD-positive states
# have -2.29% mean fwd QQQ) but HELPFUL for CPM because CPM has multi-asset
# universe and can pick GLD itself or vol-targeted equity pair when canary on.
# See research/canary_rule_variants_v2.log + research/canary_state_rotation_notes.md
CANARY_ASSETS = ["HYG_stitched", "TIP", "GLD"]
CANARY_RULE = "any_positive"  # alternatives: "all_positive", "majority"
DEFAULT_CASH = "SHV"

# Engine parameters
TOP_K_CANDIDATES = 6        # Cap on momentum-ranked candidates passed to pair selection.
#                              = ceil(len(RISKY_UNIVERSE) / 2) = top half of 11 candidates.
HOLD_BUFFER = 2.5           # z-score units. Keep prior pair member unless new
#                              candidate exceeds prior z-score by this margin.
#                              See research/hold_buffer_threshold_diagnosis.log.
CORR_LOOKBACK_DAYS = 756    # ~3y (oracle-v3 sensitivity: 756d marginally beats 378d, more stable covariance)
TARGET_VOL = 0.10           # annualized
VOL_LOOKBACK_DAYS = 63
MAX_LEVERAGE = 1.0          # de-risk only, no borrowing
COST_BPS_PER_SIDE = 10
PP_BLEND = 0.30             # 30% buffer sleeve (default; sweep shows 0.4-0.7 CPM weight roughly tied)

# Buffer sleeve: PP-IEF (Browne 1981 Permanent Portfolio with IEF in place
# of TLT to reduce duration risk; TLT had -31% drawdown in 2022).
# 25% each: SPY (equity) / IEF (intermediate treasuries) / GLD (gold) / SHV (cash).
PP_ASSETS = ["SPY", "IEF", "GLD", "SHV"]
PP_WEIGHTS = {"SPY": 0.25, "IEF": 0.25, "GLD": 0.25, "SHV": 0.25}


# ---------- Data loading ----------

def load_panel(start: pd.Timestamp = None, end: pd.Timestamp = None,
               cache_dir: str = "/tmp/cpm_cache") -> pd.DataFrame:
    """Build the daily price panel from all sources."""
    os.makedirs(cache_dir, exist_ok=True)
    
    # Long-history proxy panel (1995+)
    if ARTIFACTS_PROXY.exists():
        panel = pd.read_csv(ARTIFACTS_PROXY, parse_dates=["Date"], index_col="Date").sort_index()
    else:
        panel = pd.DataFrame()
    
    # Stitched series from data/ (overwrites any same-named column in proxy panel).
    # KMLM stitched = KFA-MLM Index pre-2020-12 + live KMLM ETF post.
    # Used as buffer sleeve component (managed futures crisis-alpha).
    for fname, col in [
        ("gld_stitched_daily_clean.csv", "GLD"),
        ("tip_stitched_daily.csv", "TIP"),
        ("agg_stitched_daily.csv", "AGG_stitched"),
        ("kmlm_stitched_daily.csv", "KMLM"),
        ("hyg_stitched_daily.csv", "HYG_stitched"),  # VWEHX pre-2007-04 + live HYG
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
    
    # Live yfinance pulls for ETFs not in proxy panel
    needed = set(RISKY_UNIVERSE + SAFE_POOL + CANARY_ASSETS + PP_ASSETS + [DEFAULT_CASH])
    missing = sorted(needed - set(panel.columns))
    
    pull_start = (start - pd.DateOffset(years=2)) if start else pd.Timestamp("1995-01-01")
    pull_end = end if end else pd.Timestamp.today() + pd.Timedelta(days=1)
    
    fetched = {}
    for t in missing:
        cache_path = Path(cache_dir) / f"{t}.csv"
        if cache_path.exists():
            try:
                s = pd.read_csv(cache_path, parse_dates=[0], index_col=0).iloc[:, 0]
                s.name = t
                fetched[t] = s
                continue
            except Exception:
                pass
        try:
            d = yf.download(t, start=pull_start.strftime("%Y-%m-%d"),
                            end=pull_end.strftime("%Y-%m-%d"),
                            auto_adjust=True, progress=False, threads=False)
            if isinstance(d.columns, pd.MultiIndex):
                d = d["Close"]
            c = d["Close"] if "Close" in d.columns else d.iloc[:, 0]
            c = c.dropna(); c.name = t
            c.to_csv(cache_path, header=True)
            fetched[t] = c
        except Exception as e:
            print(f"WARN: could not fetch {t}: {e}", file=sys.stderr)
    
    if fetched:
        extras = pd.DataFrame(fetched)
        panel = panel.join(extras, how="outer").sort_index() if not panel.empty else extras
    
    if start: panel = panel[panel.index >= start - pd.DateOffset(months=15)]  # keep warmup
    if end:   panel = panel[panel.index <= end]
    return panel.sort_index()


# ---------- Signals ----------

def faber_sma_xs(monthly: pd.DataFrame) -> pd.Series:
    """Cross-sectional Faber 10-month SMA distance: (price - SMA10) / SMA10."""
    if len(monthly) < 10:
        return pd.Series(np.nan, index=monthly.columns)
    sma = monthly.rolling(10).mean().iloc[-1]
    return (monthly.iloc[-1] - sma) / sma


def sig_13612W(p: pd.Series) -> float:
    """Canonical HAA 13612U momentum: simple average of 1/3/6/12-month returns.
    Per Keller & Keuning HAA paper (2022) and AllocateSmartly reproduction.
    Earlier version used Keller-family 13612W weighted form (12r1+4r3+2r6+r12)/19;
    oracle-v6 test showed 13612U canonical is both better-performing (+0.08 Sh
    on 70/30 blend) and matches the actual HAA paper formula.
    Function name kept as sig_13612W for back-compat with diagnostic outputs."""
    p = p.dropna()
    if len(p) < 13:
        return np.nan
    last = p.iloc[-1]
    r1 = last / p.iloc[-2] - 1
    r3 = last / p.iloc[-4] - 1
    r6 = last / p.iloc[-7] - 1
    r12 = last / p.iloc[-13] - 1
    return (r1 + r3 + r6 + r12) / 4.0

# Canonical alias: 13612U (unweighted average per actual HAA paper).
# Prefer this name in new code; sig_13612W kept for back-compat with
# ~150 references in research/ scripts and diagnostic outputs.
sig_13612U = sig_13612W
mom_canary = sig_13612W






def lowest_corr_pair(daily: pd.DataFrame, candidates: list, lookback: int) -> tuple:
    """Return the pair with lowest 12-month correlation. Kept for reference;
    superseded by min_vol_pair below."""
    if len(candidates) < 2:
        return None
    rets = daily[candidates].iloc[-lookback:].pct_change().dropna(how="all")
    if len(rets) < 30:
        return None
    corr = rets.corr()
    best = None
    best_val = float("inf")
    for a, b in combinations(candidates, 2):
        c = corr.loc[a, b]
        if pd.notna(c) and c < best_val:
            best_val = c
            best = (a, b)
    return best


def min_vol_pair(daily: pd.DataFrame, candidates: list, lookback: int) -> tuple:
    """Return the pair with lowest 50/50 portfolio variance over lookback.

    Uses full covariance (correlation x volatility) rather than correlation
    only. Empirically more stable: variance estimation is robust where mean
    estimation (Sharpe/Sortino selection) is noisy. Compared to
    `lowest_corr_pair`, picks pairs that are both diversified AND
    individually low-vol.

    Research (strategy_mvp/RESEARCH_NOTE.md sec 10/10c):
      - Sharpe lift over lowest_corr_pair: +0.07 (0.82 -> 0.89)
      - Lower portfolio vol via covariance optimization
      - Top-half momentum pre-filter retained (positive momentum required)
    """
    if len(candidates) < 2:
        return None
    rets = daily[candidates].iloc[-lookback:].pct_change().dropna(how="all")
    if len(rets) < 30:
        return None
    cov = rets.cov()
    best = None
    best_var = float("inf")
    for a, b in combinations(candidates, 2):
        v = 0.25 * cov.loc[a, a] + 0.25 * cov.loc[b, b] + 0.5 * cov.loc[a, b]
        if pd.notna(v) and v < best_var:
            best_var = v
            best = (a, b)
    return best


def zscore(s: pd.Series) -> pd.Series:
    sd = s.std()
    if pd.isna(sd) or sd == 0:
        return pd.Series(0.0, index=s.index)
    return (s - s.mean()) / sd


def best_safe(monthly: pd.DataFrame, sig_d: pd.Timestamp, safe_pool: list) -> str:
    """Pick the best safe asset by Faber 10m SMA distance."""
    sub = monthly.loc[:sig_d]
    available = [s for s in safe_pool if s in sub.columns and sub[s].first_valid_index() is not None]
    if not available:
        return DEFAULT_CASH
    if len(sub) < 10:
        return available[0]
    sma = sub[available].rolling(10).mean().iloc[-1]
    last = sub[available].iloc[-1]
    dist = ((last - sma) / sma).dropna()
    return dist.idxmax() if not dist.empty else available[0]


# ---------- Allocation logic ----------

def compute_target_weights(
    close_panel: pd.DataFrame,
    sig_d: pd.Timestamp,
    prev_pair: tuple = None,
    universe: list = None,
    safe_pool: list = None,
    canary_assets: list = None,
) -> tuple[dict, tuple, str, str]:
    """
    Returns: (weights, new_pair, regime, safe_ticker)
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
        s = sig_13612W(monthly[c])
        if pd.notna(s):
            canary_scores.append(s)
    if not canary_scores:
        return {safe: 1.0}, None, "DEFENSIVE", safe
    n_pos = sum(1 for s in canary_scores if s > 0)
    if CANARY_RULE == "any_positive":
        if n_pos == 0:
            return {safe: 1.0}, None, "DEFENSIVE", safe
    elif CANARY_RULE == "all_positive":
        if n_pos < len(canary_scores):
            return {safe: 1.0}, None, "DEFENSIVE", safe
    else:  # "majority"
        if n_pos <= len(canary_scores) // 2:
            return {safe: 1.0}, None, "DEFENSIVE", safe
    
    # Faber SMA10m ranker on universe
    score = faber_sma_xs(monthly)
    avail = [t for t in universe
             if t in score.index and pd.notna(score[t])
             and pd.notna(close_panel.loc[sig_d].get(t, np.nan) if sig_d in close_panel.index else np.nan)]
    if not avail:
        return {safe: 1.0}, None, "DEFENSIVE", safe
    
    sa = score.loc[avail]
    za = zscore(sa)
    ranked = sa.sort_values(ascending=False)
    top_k = max(2, min(TOP_K_CANDIDATES, len(ranked)))  # See TOP_K_CANDIDATES at top of file.
    positive = ranked.iloc[:top_k][lambda s: s > 0]
    
    # Partial-safe fill if <2 positive
    if len(positive) < 2:
        if len(positive) == 1:
            return {positive.index[0]: 0.5, safe: 0.5}, None, "RISK_ON", safe
        return {safe: 1.0}, None, "DEFENSIVE", safe
    
    candidates = list(positive.index)
    new_pick = min_vol_pair(close_panel.loc[:sig_d, candidates], candidates, CORR_LOOKBACK_DAYS)
    if new_pick is None:
        return {candidates[0]: 1.0}, None, "RISK_ON", safe
    
    # Hold buffer
    # Small-sample rule: DISABLED if fewer than 3 positive candidates -- cross-
    # sectional z-score is unstable with n<3, so the buffer cannot reliably
    # judge whether prior is "close enough" to swap candidate. Default to
    # the new pick when sample is sparse.
    if prev_pair is not None and HOLD_BUFFER > 1e-9 and len(candidates) >= 3:
        new_set = list(new_pick)
        for prior in prev_pair:
            if prior in new_set or prior not in avail:
                continue
            if sa.get(prior, -np.inf) <= 0:
                continue
            z_prior = za.get(prior, np.nan)
            if pd.isna(z_prior):
                continue
            swap_cands = [x for x in new_set if x not in prev_pair]
            if not swap_cands:
                continue
            swap = min(swap_cands, key=lambda x: za.get(x, np.inf))
            z_swap = za.get(swap, np.nan)
            if pd.isna(z_swap):
                continue
            if z_swap - z_prior < HOLD_BUFFER:
                new_set.remove(swap)
                new_set.append(prior)
        new_pick = tuple(new_set[:2])
    
    return {new_pick[0]: 0.5, new_pick[1]: 0.5}, new_pick, "RISK_ON", safe


# ---------- Backtest ----------

def perf_metrics(daily: pd.Series) -> dict:
    if daily.empty:
        return {}
    eq = (1.0 + daily).cumprod() * 100_000.0
    days = (eq.index[-1] - eq.index[0]).days
    yrs = days / 365.25
    cagr = (eq.iloc[-1] / eq.iloc[0]) ** (1 / yrs) - 1 if yrs > 0 else float("nan")
    vol = daily.std(ddof=0) * np.sqrt(252)
    sharpe = (daily.mean() * 252) / vol if vol > 0 else float("nan")
    rm = eq.cummax()
    mdd = (eq / rm - 1).min()
    return {"total_return": eq.iloc[-1] / eq.iloc[0] - 1,
            "cagr": cagr, "vol": vol, "sharpe": sharpe, "max_drawdown": mdd}


def run_cpm_backtest(
    panel: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
    apply_vol_target: bool = True,
    cost_bps: float = COST_BPS_PER_SIDE,
) -> tuple[pd.Series, list]:
    """Run CPM standalone (no PP blend). Returns daily returns + diagnostics list."""
    cols = sorted(set(RISKY_UNIVERSE + SAFE_POOL + CANARY_ASSETS + [DEFAULT_CASH]) & set(panel.columns))
    close = panel[cols]
    
    monthly_idx = pd.DataFrame({"x": 1}, index=close.index).groupby(pd.Grouper(freq="ME")).tail(1)
    signal_dates = monthly_idx.index[(monthly_idx.index >= start) & (monthly_idx.index <= end)].tolist()
    
    weights_history = []
    canary_state = {}
    prev_pair = None
    
    for i, sig_d in enumerate(signal_dates):
        w, new_pair, regime, safe = compute_target_weights(close, sig_d, prev_pair)
        canary_state[sig_d] = (regime == "RISK_ON")
        prev_pair = new_pair
        future = close.index[close.index > sig_d]
        if len(future) < 2:
            continue
        apply_from = future[1]  # T+1 MOC execution
        if i + 1 < len(signal_dates):
            next_sig = signal_dates[i + 1]
            next_future = close.index[close.index > next_sig]
            end_apply = next_future[1] if len(next_future) >= 2 else end
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
    
    # Vol target overlay
    if apply_vol_target:
        realized = raw_returns.rolling(VOL_LOOKBACK_DAYS).std() * np.sqrt(252)
        scale = (TARGET_VOL / realized).clip(upper=MAX_LEVERAGE).shift(1).fillna(1.0)
        raw_returns = raw_returns * scale
    
    return raw_returns.loc[(raw_returns.index >= start) & (raw_returns.index <= end)], weights_history


def run_pp_backtest(panel: pd.DataFrame, start, end) -> pd.Series:
    """Static buffer: PP-IEF 25/25/25/25 SPY/IEF/GLD/SHV. Monthly rebalanced."""
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
        nxt = dates[i + 1] if i + 1 < len(dates) else end
        seg = close.index[(close.index > d) & (close.index <= nxt)]
        out.loc[seg] = daily_ret.loc[seg, cols].mul(w, axis=1).sum(axis=1).fillna(0.0)
    return out.loc[(out.index >= start) & (out.index <= end)]


def run_fcp_pp_blend(panel, start, end, blend_pct=PP_BLEND, **kwargs) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Returns (blended, cpm, pp)."""
    fcp_daily, _ = run_cpm_backtest(panel, start, end, **kwargs)
    pp_daily = run_pp_backtest(panel, start, end)
    common = fcp_daily.index.intersection(pp_daily.index)
    blended = (1 - blend_pct) * fcp_daily.reindex(common).fillna(0.0) + blend_pct * pp_daily.reindex(common).fillna(0.0)
    return blended, fcp_daily.reindex(common), pp_daily.reindex(common)


# ---------- CLI commands ----------

def cmd_allocate(args):
    """Print this month's target allocation."""
    sig_d = pd.Timestamp(args.signal_date) if args.signal_date else None
    panel = load_panel(end=sig_d)
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
    
    # CPM weights
    weights, pair, regime, safe = compute_target_weights(panel, sig_d)
    print(f"\n[CPM sleeve, 70% of capital]")
    print(f"  Regime: {regime}")
    print(f"  Best safe: {safe}")
    if pair:
        print(f"  Selected pair: {pair[0]} + {pair[1]}")
    print(f"  Weights:")
    for t, w in sorted(weights.items(), key=lambda x: -x[1]):
        print(f"    {t:8s} {w*100:5.1f}%")
    
    # PP weights
    print(f"\n[Buffer sleeve, 30% of capital]")
    for a in PP_ASSETS:
        print(f"    {a:8s} {PP_WEIGHTS[a]*100:5.1f}%")
    
    # Combined (% of total portfolio)
    print(f"\n[Combined target, 100% of capital]")
    fcp_share = 1 - PP_BLEND
    combined = {}
    for t, w in weights.items():
        combined[t] = combined.get(t, 0.0) + w * fcp_share
    for a in PP_ASSETS:
        combined[a] = combined.get(a, 0.0) + PP_WEIGHTS[a] * PP_BLEND
    for t, w in sorted(combined.items(), key=lambda x: -x[1]):
        print(f"    {t:8s} {w*100:5.1f}%")


def cmd_backtest(args):
    start = pd.Timestamp(args.start)
    end = pd.Timestamp(args.end) if args.end else pd.Timestamp.today().normalize()
    print(f"Loading panel ...")
    panel = load_panel(start=start, end=end)
    print(f"Panel: {panel.index[0].date()} -> {panel.index[-1].date()}, {len(panel.columns)} assets")
    
    print(f"\nRunning CPM backtest from {start.date()} to {end.date()} ...")
    
    kwargs = dict(
        apply_vol_target=not args.no_vol_target,
        cost_bps=0 if args.no_cost else COST_BPS_PER_SIDE,
    )
    
    blended, cpm, pp = run_fcp_pp_blend(panel, start, end, **kwargs)
    
    print(f"\n{'Strategy':25s} {'CAGR':>8s} {'Vol':>7s} {'Sharpe':>7s} {'MaxDD':>8s}")
    print("-" * 60)
    for label, daily in [("CPM standalone", cpm),
                         ("Permanent Portfolio", pp),
                         ("CPM-PP (70/30)", blended)]:
        m = perf_metrics(daily)
        print(f"{label:25s} {m['cagr']*100:7.2f}% {m['vol']*100:6.2f}% {m['sharpe']:7.3f} {m['max_drawdown']*100:7.2f}%")
    
    # SPY benchmark
    if "SPY" in panel.columns:
        spy = panel["SPY"].ffill().pct_change().loc[start:end].fillna(0.0)
        common = blended.index.intersection(spy.index)
        spy_eq = spy.reindex(common)
        m = perf_metrics(spy_eq)
        print(f"{'SPY buy-hold':25s} {m['cagr']*100:7.2f}% {m['vol']*100:6.2f}% {m['sharpe']:7.3f} {m['max_drawdown']*100:7.2f}%")
    
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        df = pd.DataFrame({"CPM": cpm, "PP": pp, "FCP_PP_blend": blended})
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
