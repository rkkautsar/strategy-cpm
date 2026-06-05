"""CPM on Optimum3's 15-asset global universe -- research harness (sleeve only).

Hypothesis
----------
Universe was the dominant HAA->CPM factor (+0.2215 Sharpe in the factorial).
Does CPM's *cousin* Optimum3's richer 15-asset global universe improve CPM on a
COMMON clean window vs the prod CPM-8 universe? Test min-var vs MCA (min avg
pairwise correlation) subset selection and a top-K {4,5,6} sweep.

Faithfulness
------------
- CPM mechanism kept IDENTICAL otherwise: vol-adj Faber rank, positive-trend
  screen, TIP-only canary gate (any_positive), EW risky block, breadth-scaled
  partial-safe routing (n_pos in {1,2,3} -> hold all positives scaled; n_pos>=4
  -> select 3-of-4 subset, full risk), best-of {SHV,IEF} safe, monthly, both-252,
  10 bps/side, mooex T+1 MOO-exact execution.
- Only the RISKY UNIVERSE, the subset-selection method, and TOP_K are varied.
- compute_target_weights at top_k=4 / minvar / prod-8 reproduces anchor Sharpe
  1.2373 (verified by _verify_clone).

Optimum3 universe (faithful): bonds ARE momentum candidates (IEF/TLT/TIP enter
risky), per Optimum3. TIP stays canary; SHV/IEF stay safe pool. Dual roles kept.

Execution / data
----------------
- Base panel from cpm_live.load_panel (frozen in-repo + proxy stitches).
- New tickers (REM,VGK,EWJ,SCZ,RWX,BWX) fetched once + cached to /tmp.
- mooex intraday/overnight built from real OHLC for prod tickers (engine open
  cache) + new tickers (fetched OHLC). Missing-open days fall back gracefully
  (overnight->0, intraday->close-to-close); rare and only on rebalance days.

Caveats (PROMINENT)
-------------------
- SHORT HISTORY / SURVIVORSHIP: SCZ (2007-12), BWX (2007-10), REM (2007-05) are
  the binding inceptions. Common all-rankable window starts ~2009-01. Cached
  yfinance, point-in-time NOT guaranteed for the fetched ETFs (no proxy stitch).
- HIGH OVERFIT CAUTION: universe + K + selection = several DoF. This is an
  a-priori faithful port of Optimum3, NOT tuned. Point estimates only; no
  bootstrap/WF here (compelling configs flagged for later).
"""

from __future__ import annotations

import os
from itertools import combinations
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import cpm_live
from cpm_live import (
    load_panel,
    perf_metrics,
    faber_sma_xs,
    sig_13612U,
    best_safe,
    _min_var_subset,
    _ret_window,
    DEFAULT_CASH,
    COST_BPS_PER_SIDE,
    CORR_LOOKBACK_DAYS,
)
from research import exec_lag_moo_validation_2026_05_30 as _engine

# ---------- universe definition ----------
PROD8 = ["QQQ", "SPHQ", "EFA", "EEM", "VNQ", "GLD", "TLT", "DBC"]

# Optimum3 15-asset global universe (faithful; bonds are momentum candidates).
OPT3 = ["SPY", "QQQ", "VNQ", "REM", "IEF", "TLT", "TIP",
        "VGK", "EWJ", "SCZ", "EEM", "RWX", "BWX", "DBC", "GLD"]
# Tickers not in the prod panel/open-cache; fetched fresh (no proxy stitch).
NEW_TICKERS = ["REM", "VGK", "EWJ", "SCZ", "RWX", "BWX"]

SAFE_POOL = ["SHV", "IEF"]
CANARY = ["TIP"]
CASH = DEFAULT_CASH
CACHE = Path("/tmp/cpm_opt3_cache")
END = pd.Timestamp("2026-05-22")
EXT_START = pd.Timestamp("1999-03-10")
PROD_CLEAN = pd.Timestamp("2008-05-30")     # prod CPM-8 clean window
COMMON_START = pd.Timestamp("2009-01-31")   # all 15 OPT3 assets rankable


# ---------- data ----------
def _fetch_ohlc(ticker: str) -> pd.DataFrame:
    CACHE.mkdir(parents=True, exist_ok=True)
    p = CACHE / f"{ticker}.csv"
    if p.exists():
        return pd.read_csv(p, parse_dates=[0], index_col=0)
    d = yf.download(ticker, start="2003-01-01", end=(END + pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
                    auto_adjust=True, progress=False, threads=False)
    if isinstance(d.columns, pd.MultiIndex):
        d.columns = d.columns.get_level_values(0)
    out = d[["Open", "Close"]].dropna()
    out.to_csv(p)
    return out


def load_extended():
    """Return (panel, intraday, overnight) covering prod + OPT3 universe."""
    panel = load_panel(start=EXT_START, end=END)
    panel = panel.loc[panel.index <= END].copy()

    new_close, new_open = {}, {}
    for t in NEW_TICKERS:
        o = _fetch_ohlc(t)
        new_close[t] = o["Close"]
        new_open[t] = o["Open"]
    new_close_df = pd.DataFrame(new_close)
    # join close into panel (new columns only)
    panel = panel.join(new_close_df.reindex(panel.index), how="left")

    open_df, close_yf = _engine.load_open_close()
    new_open_df = pd.DataFrame(new_open)
    open_df = open_df.join(new_open_df, how="outer").sort_index()
    close_yf = close_yf.join(new_close_df, how="outer").sort_index()

    intraday = (close_yf / open_df - 1.0).reindex(panel.index)
    overnight = (open_df / close_yf.shift(1) - 1.0).reindex(panel.index)
    return panel, intraday, overnight


# ---------- selection methods ----------
def _mca_subset(close, sig_d, candidates, lookback, m):
    """Min avg pairwise correlation m-of-candidates (Varadi MinCorr / Optimum3)."""
    if len(candidates) <= m:
        return list(candidates)
    rets = _ret_window(close.loc[:sig_d], candidates, lookback)
    if len(rets) < lookback:
        return list(candidates)
    corr = rets.corr()
    if corr.isna().any().any():
        return list(candidates)
    best, best_v = None, np.inf
    for combo in combinations(candidates, m):
        cl = list(combo)
        sub = corr.loc[cl, cl].values
        # average off-diagonal correlation
        n = len(cl)
        avg = (sub.sum() - n) / (n * (n - 1))
        if avg < best_v:
            best_v, best = avg, combo
    return list(best) if best else list(candidates)


# ---------- parametrized CPM weight fn (faithful clone) ----------
def make_weight_fn(close, universe, top_k=4, method="minvar", select="topk"):
    """Return weight_fn(sig_d)->dict replicating compute_target_weights,
    parametrized on universe/top_k/subset-method/selection-mode.

    select="topk" (CPM-faithful):
        rank vol-adj, take top_k, positive screen; n_pos>=4 -> (n_pos-1)-of-n_pos
        subset by method (prod 3-of-4 at the boundary), breadth-scaled /4.
    select="half3" (Optimum3-faithful):
        pool = top-half of eligible by vol-adj (round(N/2)); positive screen;
        n_pos>=3 -> pick FINAL 3 from pool by method, EW 1/3, full risk;
        n_pos in {1,2} -> hold positives EW, breadth-scaled /3, safe remainder.
    method in {"minvar","mca"} = the subset/triplet selection metric.
    """
    def weight_fn(sig_d):
        monthly = close.loc[:sig_d].resample("ME").last()
        safe = best_safe(monthly, sig_d, SAFE_POOL)

        # TIP-only canary, any_positive
        cscores = []
        for c in CANARY:
            if c in monthly.columns:
                s = sig_13612U(monthly[c])
                if pd.notna(s):
                    cscores.append(s)
        if not cscores:
            return {safe: 1.0}
        if sum(1 for s in cscores if s > 0) == 0:
            return {safe: 1.0}

        faber = faber_sma_xs(monthly)
        avail = [t for t in universe
                 if t in faber.index and pd.notna(faber[t])
                 and pd.notna(close.loc[sig_d].get(t, np.nan) if sig_d in close.index else np.nan)]
        if not avail:
            return {safe: 1.0}

        daily_rets = close[avail].ffill().pct_change()
        scores = {}
        for t in avail:
            v = daily_rets[t].loc[:sig_d].tail(252).std() * np.sqrt(252)
            if pd.isna(v) or v < 1e-9:
                v = 1.0
            scores[t] = float(faber[t]) / v
        ranked = pd.Series(scores).sort_values(ascending=False)
        if select == "half3":
            k = max(3, int(round(len(ranked) / 2)))  # top-half pool
        else:
            k = max(2, min(top_k, len(ranked)))
        top = ranked.iloc[:k]
        positive = top[top.index.map(lambda t: faber.get(t, -np.inf) > 0)]
        if len(positive) == 0:
            return {safe: 1.0}

        picks_all = list(positive.index)
        n_pos = len(picks_all)

        def _subset(cands, m):
            if method == "minvar":
                return _min_var_subset(close, sig_d, cands, CORR_LOOKBACK_DAYS, m)
            return _mca_subset(close, sig_d, cands, CORR_LOOKBACK_DAYS, m)

        if select == "half3":
            # breadth base = target cardinality 3 (Optimum3-style partial-safe)
            if n_pos >= 3:
                picks = _subset(picks_all, 3)
            else:
                picks = picks_all
            risky_fraction = min(n_pos, 3) / 3.0
        else:  # topk (CPM-faithful)
            # prod trigger: n_pos==4 -> min-var 3-of-4. Generalize: positive set
            # filling top_k (>=4) -> (n_pos-1)-of-n_pos subset by method.
            if n_pos >= 4:
                picks = _subset(picks_all, n_pos - 1)
            else:
                picks = picks_all
            risky_fraction = min(n_pos, 4) / 4.0

        safe_fraction = 1.0 - risky_fraction
        out = {t: (1.0 / len(picks)) * risky_fraction for t in picks}
        if safe_fraction > 0:
            out[safe] = out.get(safe, 0.0) + safe_fraction
        return out

    return weight_fn


# ---------- run + metrics ----------
def run(weight_fn, panel, intraday, overnight, start, end):
    daily_ret = panel.ffill().pct_change()
    series, diag = _engine._segment_returns_conv(
        panel, daily_ret, weight_fn, EXT_START, end, "mooex",
        COST_BPS_PER_SIDE, intraday, overnight)
    return series.loc[(series.index >= start) & (series.index <= end)], diag


def turnover_annual(weight_fn, panel, start, end):
    """Annualized one-way turnover = mean(0.5*sum|dw|) per rebalance * 12."""
    monthly_idx = (pd.DataFrame({"x": 1}, index=panel.index)
                   .groupby(pd.Grouper(freq="ME")).tail(1))
    sigs = monthly_idx.index[(monthly_idx.index >= start) & (monthly_idx.index <= end)].tolist()
    prev, tos = {}, []
    for sd in sigs:
        w = weight_fn(sd)
        keys = set(w) | set(prev)
        tos.append(0.5 * sum(abs(w.get(k, 0.0) - prev.get(k, 0.0)) for k in keys))
        prev = w
    return float(np.mean(tos) * 12) if tos else float("nan")


def metrics(daily, cash, weight_fn=None, panel=None, start=None, end=None):
    m = perf_metrics(daily, cash)
    dn = daily[daily < 0]
    downside = dn.std(ddof=0) * np.sqrt(252) if len(dn) else np.nan
    sortino = (daily.mean() * 252) / downside if downside and downside > 0 else np.nan
    q = daily.quantile(0.05)
    cvar = daily[daily <= q].mean()
    out = {
        "Sharpe": m.get("sharpe"), "Sortino": sortino, "Calmar": m.get("calmar"),
        "Martin": m.get("martin"), "MaxDD": m.get("max_drawdown"),
        "CVaR95": cvar, "CAGR": m.get("cagr"), "Vol": m.get("vol"),
    }
    if weight_fn is not None and panel is not None:
        out["TurnAnn"] = turnover_annual(weight_fn, panel, start, end)
    return out


def crisis_windows():
    return {
        "GFC 2008-09..2009-03": ("2008-09-01", "2009-03-31"),
        "Euro 2011-05..2011-10": ("2011-05-01", "2011-10-31"),
        "Q4-2018 2018-10..2018-12": ("2018-10-01", "2018-12-31"),
        "COVID 2020-02..2020-04": ("2020-02-15", "2020-04-30"),
        "Bear 2022-01..2022-10": ("2022-01-01", "2022-10-31"),
        "Bull 2013-2017": ("2013-01-01", "2017-12-31"),
    }
