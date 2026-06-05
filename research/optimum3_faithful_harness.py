"""FAITHFUL standalone OPTIMUM3 -- research harness (NOT a CPM variant).

Implements Optimum3's PUBLIC rules as a pure dual-momentum + Varadi-MCA strategy,
backtests on our data, validates direction/ballpark vs AllocateSmartly's published
track record, and compares to CPM-8 + cheap benchmarks on the SAME common window.

PUBLIC RULES IMPLEMENTED (Todd Tresidder / FinancialMentor; tracked by Allocate
Smartly; their backtest is since 1987, net of costs, rules undisclosed/black-box):
  - UNIVERSE: 15 global ETFs
      SPY QQQ VNQ REM IEF TLT TIP VGK EWJ SCZ EEM RWX BWX DBC GLD.
  - DUAL MOMENTUM:
      (i) RELATIVE: rank all 15 by momentum, take ~top HALF (round(15/2)=8).
      (ii) ABSOLUTE gate: within that top-half, keep only momentum > 0 (trend
           filter). The eligible pool = (in top-half) AND (positive).
  - SELECTION (Varadi MCA / MinCorr): from the eligible pool, pick the 3-asset
    subset with the LOWEST AVERAGE PAIRWISE CORRELATION (exhaustive C(pool,3),
    252d corr).
  - WEIGHTING: equal-weight, 1/3 each.
  - DEFENSIVE (NO external canary): if <3 names pass the absolute gate, hold those
    that pass at 1/3 each and route the remainder to cash; if 0 pass, 100% cash.
  - REBALANCE: monthly (single month-end rebalance = CORE; 3-tranche = optional
    sensitivity).

ASSUMPTIONS STATED (all are choices; the strategy is partly a black box):
  - LOOKBACK is UNDISCLOSED. Primary proxy = 13612U (Keller multi-horizon avg of
    1/3/6/12m total returns, the repo's canonical convention). Sensitivity tests
    6m and 12m total return. We CANNOT know the true lookback ("daily fast-tactical"
    per the vendor) -> the repro carries irreducible lookback uncertainty.
  - CASH asset = SHV (Optimum3 says BIL/SHV; SHV is in our panel).
  - top-half cardinality = 8 of 15 (round(15/2)); 7 tested as a sensitivity.
  - Execution: signals lagged, T+1 MOO-exact (mooex), 10 bps/side, monthly. Same
    engine + conventions as CPM so comparison is apples-to-apples.
  - NO vol-adjusted ranker, NO vol-targeting, NO TIP-canary, NO breadth /4 scaling
    (those are CPM-specific). This is PURE dual-momentum + MCA-3 + EW + cash.

CAVEATS (PROMINENT):
  - UNDISCLOSED LOOKBACK: biggest source of repro error; see sensitivity table.
  - NON-PIT / SHORT HISTORY / SURVIVORSHIP: 6 of 15 ETFs are freshly fetched cached
    yfinance pulls with NO proxy stitch and NO point-in-time guarantee
    (REM 2007-05, VGK 2005-03, EWJ 2003-01, SCZ 2007-12 BINDING, RWX 2006-12,
    BWX 2007-10). Common all-rankable window starts ~2009-01.
  - CANNOT MATCH 1987: AllocateSmartly backtests since 1987 on longer/cleaner data;
    our 15-ETF universe only exists ~2009+. We validate DIRECTION/BALLPARK on the
    recent overlap only, never the full 1987 record.
  - Point estimates only (no bootstrap/WF per scope). Not tuned toward any target.

Reuses the data loader / universe resolution from cpm_opt3_universe_harness and the
backtest engine + momentum helpers from cpm_live, but the Optimum3 LOGIC here is
implemented fresh and faithfully (the prior opt3 run used the CPM mechanism).
"""

from __future__ import annotations

from itertools import combinations
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cpm_live import sig_13612U, perf_metrics, COST_BPS_PER_SIDE
from research import cpm_opt3_universe_harness as H

# Optimum3 faithful universe (15 global ETFs) -- reuse resolution from H.
OPT3 = H.OPT3
CASH = "SHV"
CORR_LOOKBACK = 252           # 252d pairwise correlation window for MCA
COMMON_START = H.COMMON_START  # 2009-01-31 (all 15 rankable)
END = H.END


# ---------- momentum score (configurable, undisclosed-lookback proxy) ----------
def _score(monthly_series: pd.Series, lookback: str) -> float:
    s = monthly_series.dropna()
    if lookback == "13612U":
        return sig_13612U(s)              # needs >=13 monthly points
    if len(s) < 13:                       # keep warmup uniform across lookbacks
        return np.nan
    last = s.iloc[-1]
    if lookback == "12m":
        return last / s.iloc[-13] - 1.0
    if lookback == "6m":
        return last / s.iloc[-7] - 1.0
    if lookback == "3m":
        return last / s.iloc[-4] - 1.0
    raise ValueError(f"unknown lookback {lookback}")


def _mca3(close: pd.DataFrame, sig_d, pool: list) -> list:
    """3-asset subset of pool with LOWEST average pairwise correlation (Varadi MCA).

    Exhaustive over C(pool,3). Falls back to the top-3 of pool (caller order) when
    the 252d correlation matrix is unavailable.
    """
    if len(pool) <= 3:
        return list(pool)
    rets = H._ret_window(close.loc[:sig_d], pool, CORR_LOOKBACK)
    if len(rets) < CORR_LOOKBACK:
        return list(pool[:3])
    corr = rets.corr()
    if corr.isna().any().any():
        return list(pool[:3])
    best, best_v = None, np.inf
    for combo in combinations(pool, 3):
        cl = list(combo)
        sub = corr.loc[cl, cl].values
        avg = (sub.sum() - 3) / 6.0       # avg of 3 off-diagonal pairwise corrs
        if avg < best_v:
            best_v, best = avg, combo
    return list(best) if best else list(pool[:3])


# ---------- faithful Optimum3 weight function ----------
def make_opt3_weight_fn(close: pd.DataFrame, universe=OPT3, lookback="13612U",
                        top_half=8, cash=CASH, select="mca"):
    """weight_fn(sig_d)->dict implementing faithful standalone Optimum3.

    select="mca"  -> 3-of-pool by lowest avg pairwise correlation (faithful).
    select="topmom" -> top-3 of pool by momentum (ablation: no MCA).
    """
    def weight_fn(sig_d):
        monthly = close.loc[:sig_d].resample("ME").last()
        scores = {}
        for t in universe:
            if t not in monthly.columns:
                continue
            sc = _score(monthly[t], lookback)
            if pd.notna(sc):
                scores[t] = float(sc)
        if not scores:
            return {cash: 1.0}
        ranked = pd.Series(scores).sort_values(ascending=False)
        k = min(top_half, len(ranked))
        top = ranked.iloc[:k]
        # dual momentum: in top-half AND positive (absolute gate)
        pool = [t for t in top.index if top[t] > 0.0]
        if len(pool) == 0:
            return {cash: 1.0}
        if len(pool) < 3:
            w = {t: 1.0 / 3.0 for t in pool}
            w[cash] = w.get(cash, 0.0) + (3 - len(pool)) / 3.0
            return w
        picks = _mca3(close, sig_d, pool) if select == "mca" else list(pool[:3])
        return {t: 1.0 / 3.0 for t in picks}

    return weight_fn


# ---------- constant-weight benchmark weight fns ----------
def const_weight_fn(weights: dict):
    def wf(sig_d):
        return dict(weights)
    return wf


# ---------- run via repo mooex engine (T+1, 10bps/side) ----------
def run(weight_fn, panel, intraday, overnight, start, end):
    return H.run(weight_fn, panel, intraday, overnight, start, end)


def metrics(daily, cash_series, weight_fn=None, panel=None, start=None, end=None):
    return H.metrics(daily, cash_series, weight_fn, panel, start, end)


# ---------- optional: 3-tranche execution sensitivity (proxy) -----------------
def _trading_day_of_month(close_index, offset):
    """Return, per calendar month, the trading day at position `offset` (0-based)
    within that month (clamped to last available)."""
    df = pd.DataFrame({"d": close_index}, index=close_index)
    grp = df.groupby(pd.Grouper(freq="MS"))
    days = []
    for _, sub in grp:
        idx = sub.index
        if len(idx) == 0:
            continue
        days.append(idx[min(offset, len(idx) - 1)])
    return pd.DatetimeIndex(days)


def run_tranche3(weight_fn, panel, start, end, offsets=(1, 8, 15),
                 cost_bps=COST_BPS_PER_SIDE):
    """3-tranche proxy: 3 equal sleeves, each rebalanced monthly on a DIFFERENT
    trading-day-of-month (offsets ~ days 2/9/16, 0-based 1/8/15), averaged.

    Execution model is a SIMPLER T+1 close-to-close (not mooex) -- this is a
    smoothing sensitivity, not the primary result. Signals lagged 1 trading day.
    """
    daily_ret = panel.ffill().pct_change()
    series_list = []
    for off in offsets:
        sig_days = _trading_day_of_month(panel.index, off)
        sig_days = sig_days[(sig_days >= start) & (sig_days <= end)]
        s = _segment_t1_cc(panel, daily_ret, weight_fn, list(sig_days), end, cost_bps)
        series_list.append(s)
    aligned = pd.concat(series_list, axis=1).fillna(0.0)
    return aligned.mean(axis=1)


def _segment_t1_cc(close, daily_ret, weight_fn, sig_days, end, cost_bps):
    """Minimal T+1 close-to-close executor for explicit signal dates."""
    hist, prev_w = [], {}
    for i, sd in enumerate(sig_days):
        fut = close.index[close.index > sd]
        if len(fut) == 0:
            continue
        af = fut[0]
        if i + 1 < len(sig_days):
            nf = close.index[close.index > sig_days[i + 1]]
            ea = nf[0] if len(nf) else end
        else:
            ea = end
        hist.append({"af": af, "ea": ea, "w": weight_fn(sd), "pw": prev_w})
        prev_w = hist[-1]["w"]
    cols = sorted({a for h in hist for a in h["w"]} & set(daily_ret.columns))
    df_w = pd.DataFrame(0.0, index=close.index, columns=cols)
    for h in hist:
        mask = (close.index >= h["af"]) & (close.index < h["ea"])
        for a, ww in h["w"].items():
            if a in df_w.columns:
                df_w.loc[mask, a] = ww
    ret = (df_w[cols] * daily_ret[cols]).sum(axis=1, min_count=1).fillna(0.0)
    for i, h in enumerate(hist):
        pw = hist[i - 1]["w"] if i > 0 else {}
        keys = set(h["w"]) | set(pw)
        to = sum(abs(h["w"].get(k, 0.0) - pw.get(k, 0.0)) for k in keys)
        if h["af"] in ret.index:
            ret.loc[h["af"]] -= to * cost_bps / 10000.0
    return ret.loc[(ret.index >= sig_days[0]) & (ret.index <= end)] if sig_days else ret


def crisis_windows():
    cw = dict(H.crisis_windows())
    cw["Tariff 2025 2025-02..2025-04"] = ("2025-02-15", "2025-04-30")
    return cw
