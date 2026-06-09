from __future__ import annotations

import re
import datetime as dt
import sys
from importlib import metadata as importlib_metadata
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent

import cpm_live as cpm_module
from cpm_live import (
    RISKY_UNIVERSE, SAFE_POOL,
    CANARY_ASSETS, DEFAULT_CASH,
    CORR_LOOKBACK_DAYS, COST_BPS_PER_SIDE,
    TOP_K_CANDIDATES,
    load_panel,
    perf_metrics, compute_target_weights, sig_13612U,
)
from rpv_live import (
    COST_BPS_PER_SIDE as RPV_COST_BPS_PER_SIDE,
    compute_rpv_weights,
    compute_rpv_signals,
)
from ndx_sleeve_live import (
    compute_ndx_weights,
    run_ndx_backtest,
    COST_BPS_PER_SIDE as NDX_COST_BPS_PER_SIDE,
    PRICES_FILE as NDX_PRICES_FILE,
    SELECT_K as NDX_SELECT_K,
    VOL_FAST_DAYS as NDX_VOL_FAST_DAYS,
    VOL_SLOW_DAYS as NDX_VOL_SLOW_DAYS,
    DELISTING_HAIRCUT as NDX_DELISTING_HAIRCUT,
)
from core import cached_value_backtest
from sleeve_cache import df_digest, file_digest, get_sleeve_returns

from config import CROSS_SLEEVE_REALLOCATION_COST_BPS
from sleeves import apply_blend_reallocation_cost, build_blend_weight_schedule


def get_last_finalized_month_cutoff(index: pd.DatetimeIndex) -> pd.Timestamp:
    """Returns the start of the first unfinalized month based on panel index.
    A month is finalized if the panel contains its business month-end.
    """
    if len(index) == 0:
        return pd.Timestamp.today().normalize().replace(day=1)
    latest_date = index[-1]
    bme = latest_date + pd.offsets.BMonthEnd(0)
    if latest_date >= bme:
        return (latest_date + pd.offsets.MonthBegin(1)).normalize()
    else:
        return latest_date.replace(day=1).normalize()


RPV_EQUITY_TICKER = "SPY"
CASH_TICKER = "SHV"

BOOTSTRAP_SINGLE_B = 2000
BOOTSTRAP_PAIRED_B = 5000
EXT_START = pd.Timestamp("1999-03-10")
MOOEX_INTRADAY_SANITY_MAX = 0.50
NDX_OPENS_CACHE_PATH = ROOT / "data" / "ndx_constituents" / "opens.parquet"
NDX_SLEEVE_VERSION = "ndx-2026-06-05.1"
NDX_SOURCE_FILES = (
    ROOT / "ndx_sleeve_live.py",
    ROOT / "engine.py",
    ROOT / "core.py",
    ROOT / "dashboard_engine.py",
)


def faber_gtaa5(panel, start, end):
    universe = ["SPY", "EFA", "IEF", "VNQ", "DBC"]
    cols = [c for c in universe if c in panel.columns]
    if "SHV" not in panel.columns: return pd.Series(dtype=float)
    cols += ["SHV"]
    close = panel[cols]
    sig_dates = _b_monthly_signal_dates(close, start, end)
    weights_map = {}
    for sd in sig_dates:
        m = close.loc[:sd].resample("ME").last()
        if len(m) < 11: weights_map[sd] = {"SHV": 1.0}; continue
        sma = m.rolling(10).mean().iloc[-1]; last = m.iloc[-1]
        in_u = [a for a in universe if a in last.index and pd.notna(sma.get(a)) and pd.notna(last[a]) and last[a] > sma[a]]
        w = {a: 0.20 for a in in_u}
        if 5 - len(in_u) > 0: w["SHV"] = 0.20*(5-len(in_u))
        weights_map[sd] = w if w else {"SHV": 1.0}
    daily_ret = close.ffill().pct_change()
    out = pd.Series(0.0, index=close.index)
    for i, d in enumerate(sig_dates):
        nxt = sig_dates[i+1] if i+1 < len(sig_dates) else end
        seg = close.index[(close.index > d) & (close.index <= nxt)]
        w = weights_map.get(d, {})
        if not w: continue
        cs = [c for c in w if c in daily_ret.columns]
        if not cs: continue
        out.loc[seg] = daily_ret.loc[seg, cs].mul(pd.Series({k: w[k] for k in cs}), axis=1).sum(axis=1, min_count=1).fillna(0.0)
    return out.loc[(out.index>=start)&(out.index<=end)]

def keller_vaa_g4(panel, start, end):
    offensive = ["SPY","EFA","EEM","AGG_stitched"]
    defensive = ["SHV","IEF"]
    cols = list(dict.fromkeys(offensive + defensive))
    cols = [c for c in cols if c in panel.columns]
    close = panel[cols]
    sig_dates = _b_monthly_signal_dates(close, start, end)
    weights_map = {}
    for sd in sig_dates:
        m = close.loc[:sd].resample("ME").last()
        scores_off = {a: sig_13612U(m[a]) for a in offensive if a in m.columns}
        if any(pd.isna(v) for v in scores_off.values()):
            weights_map[sd] = {"SHV":1.0}; continue
        if all(v > 0 for v in scores_off.values()):
            best = max(scores_off, key=scores_off.get)
            weights_map[sd] = {best:1.0}
        else:
            sd_scores = {a: sig_13612U(m[a]) for a in defensive if a in m.columns}
            valid = {k:v for k,v in sd_scores.items() if pd.notna(v)}
            best = max(valid, key=valid.get) if valid else "SHV"
            weights_map[sd] = {best:1.0}
    daily_ret = close.ffill().pct_change()
    out = pd.Series(0.0, index=close.index)
    for i, d in enumerate(sig_dates):
        nxt = sig_dates[i+1] if i+1 < len(sig_dates) else end
        seg = close.index[(close.index > d) & (close.index <= nxt)]
        w = weights_map.get(d, {})
        if not w: continue
        cs = [c for c in w if c in daily_ret.columns]
        if not cs: continue
        out.loc[seg] = daily_ret.loc[seg, cs].mul(pd.Series({k: w[k] for k in cs}), axis=1).sum(axis=1, min_count=1).fillna(0.0)
    return out.loc[(out.index>=start)&(out.index<=end)]


def _haa_safe_pick(monthly, defensive=("BIL", "IEF", "SHV")):
    from cpm_live import best_safe as _best_safe
    safe_pool = list(defensive)
    sig_d = monthly.index[-1]
    return _best_safe(monthly, sig_d, safe_pool)


def _haa_run(panel, start, end, top_k, cost_bps=10.0):
    from cpm_live import sig_13612U, best_safe as _best_safe
    
    # Canonical HAA-8 offensive universe (replaces GLD with IEF)
    offensive = ["SPY", "IWM", "VEA", "VWO", "VNQ", "DBC", "IEF", "TLT"]
    safe_pool = ["SHV", "IEF"]
    
    cols = sorted(set(offensive + safe_pool + ["TIP"]) & set(panel.columns))
    close = panel[cols]
    
    # 1. Fix stale-signal slice bug by using the correct _b_monthly_signal_dates helper
    sig_dates = _b_monthly_signal_dates(close, start, end)
    
    wh = []
    for sd in sig_dates:
        # Slice daily first, then resample monthly to avoid stale-signal bug
        monthly = close.loc[:sd].resample("ME").last()
        safe = _best_safe(monthly, sd, safe_pool)
        
        tip_s = sig_13612U(monthly["TIP"]) if "TIP" in monthly.columns else float("nan")
        if pd.isna(tip_s) or tip_s <= 0:
            wh.append((sd, {safe: 1.0}))
            continue
            
        scs = {a: sig_13612U(monthly[a]) for a in offensive if a in monthly.columns}
        scs = {k: v for k, v in scs.items() if pd.notna(v)}
        if not scs:
            wh.append((sd, {safe: 1.0}))
            continue
            
        ranked = sorted(scs.items(), key=lambda kv: kv[1], reverse=True)[:top_k]
        
        # Absolute-momentum screen: positive 13612U per selected slot -> asset, else safe
        w = {}
        for ticker, sc in ranked:
            if sc > 0:
                w[ticker] = w.get(ticker, 0.0) + 1.0 / top_k
            else:
                w[safe] = w.get(safe, 0.0) + 1.0 / top_k
                
        # If fewer than top_k names were ranked (degenerate early history), remaining slots go to safe
        missing_slots = top_k - len(ranked)
        if missing_slots > 0:
            w[safe] = w.get(safe, 0.0) + (1.0 / top_k) * missing_slots
            
        wh.append((sd, w))
        
    # 2 & 3. Build portfolio with 10 bps transaction cost per side and mooex execution (1-day lag)
    return _b_build_port(close, wh, start, end, cost_bps)


def haa_simple(panel, start, end):
    """HAA-Simple (Keller 2023): TIP canary, top-1 by 13612U from HAA-8."""
    return _haa_run(panel, start, end, top_k=1)


def haa_balanced(panel, start, end):
    """HAA-Balanced (Keller 2023): TIP canary, top-4 by 13612U from HAA-8."""
    return _haa_run(panel, start, end, top_k=4)


def sixty_forty(panel, start, end):
    cols = ["SPY", "IEF"]
    cols = [c for c in cols if c in panel.columns]
    if len(cols) < 2: return pd.Series(dtype=float)
    close = panel[cols]
    monthly_idx = pd.DataFrame({"x":1}, index=close.index).groupby(pd.Grouper(freq="ME")).tail(1)
    dates = monthly_idx.index[(monthly_idx.index>=start)&(monthly_idx.index<=end)].tolist()
    daily_ret = close.ffill().pct_change()
    out = pd.Series(0.0, index=close.index)
    for i, d in enumerate(dates):
        nxt = dates[i+1] if i+1 < len(dates) else end
        seg = close.index[(close.index > d) & (close.index <= nxt)]
        out.loc[seg] = daily_ret.loc[seg, ["SPY","IEF"]].mul(pd.Series({"SPY":0.6,"IEF":0.4}), axis=1).sum(axis=1).fillna(0.0)
    return out.loc[(out.index>=start)&(out.index<=end)]


def qqq_trend_follow(panel, start, end, cost_bps=10.0, ticker="SPY"):
    """Faber 10mo SMA timing on `ticker`: hold ticker when above SMA, SHV otherwise.
    Simplest possible single-asset timing strategy, used as TAA peer benchmark.
    Default SPY matches the RPV sleeve equity ticker for apples-to-apples comparison.
    Uses SPY by default for apples-to-apples comparison with RPV."""
    if ticker not in panel.columns or "SHV" not in panel.columns:
        return pd.Series(dtype=float)
    monthly = panel[ticker].resample("ME").last().dropna()
    sma10 = monthly.rolling(10).mean()
    signal = (monthly > sma10).reindex(monthly.index).fillna(False)
    daily_tkr = panel[ticker].ffill().pct_change()
    daily_shv = panel["SHV"].ffill().pct_change().reindex(daily_tkr.index).fillna(0)
    common = daily_tkr.loc[start:end].index
    if len(common) == 0:
        return pd.Series(dtype=float)
    asset_per_day = pd.Series("SHV", index=common)
    sig_dates = signal.index[(signal.index >= start - pd.Timedelta(days=60)) & (signal.index <= end)]
    for sd in sig_dates:
        if signal.loc[sd]:
            future = common[common > sd]
            if len(future) < 1: continue
            next_sd = sig_dates[sig_dates > sd]
            if len(next_sd) > 0 and len(common[common > next_sd[0]]) > 0:
                end_apply = common[common > next_sd[0]][0]
            else:
                end_apply = common[-1]
            # T+1 OPEN execution (next-day MOO)
            mask = (common >= future[0]) & (common < end_apply)
            asset_per_day.loc[mask] = ticker
    trend_rets = pd.Series(0.0, index=common)
    trend_rets[asset_per_day == ticker] = daily_tkr.reindex(common).fillna(0)[asset_per_day == ticker]
    trend_rets[asset_per_day == "SHV"] = daily_shv.reindex(common).fillna(0)[asset_per_day == "SHV"]
    import numpy as _np
    flips = (asset_per_day.values[1:] != asset_per_day.values[:-1])
    for i in _np.where(flips)[0]:
        trend_rets.iloc[i+1] -= 2.0 * cost_bps / 10000.0
    return trend_rets


# ============================================================================
# Literature benchmarks (apples-to-apples vs PROD 60/20/20).
#
# Naming follows research/benchmark_comparison_2026_05.py:
#   B2: AAA + TIP canary on the canonical AAA 7-asset cross-asset pool
#       (Butler-Philbrick 2012 + Keller TIP veto)
#   B3: HAA-Simple SPY (Keller 2022; AllocateSmartly canonical N=1 form)
#   B5: QQQ 12mo trend (Antonacci 2014 GEM single-asset form)
#   BB4 = 60% B2 + 20% B3 + 20% B5 (best literature 60/20/20 blend tested)
#
# BB4 is the canonical apples-to-apples benchmark for PROD: same 60/20/20
# weighting, all three sleeves backed by published TAA papers, and it was the
# strongest literature blend across all multi-sleeve combinations tested.
# Per-sleeve alpha decomposition uses:
#   CPM         vs B2 (AAA + TIP)
#   RPV sleeve  vs B3 (HAA-Simple SPY)
#   NDX sleeve  vs B5 (QQQ 12mo trend) or QQQ buy-hold for raw equity proxy
# ============================================================================

# B2 benchmark universe: canonical AAA cross-asset pool (Butler-Philbrick 2012).
BENCH_AAA_UNIVERSE = ["SPY", "EFA", "EEM", "VNQ", "GLD", "TLT", "DBC"]
_BENCH_SAFE = ["SHV", "IEF"]


def _b_monthly_signal_dates(close, start, end):
    monthly_idx = pd.DataFrame({"x": 1}, index=close.index).groupby(
        pd.Grouper(freq="ME")).tail(1).index
    return monthly_idx[(monthly_idx >= start) & (monthly_idx <= end)].tolist()


def _b_build_port(close, weights_history, start, end, cost_bps=10.0):
    common = close.index[(close.index >= start) & (close.index <= end)]
    daily = close.ffill().pct_change()
    port = pd.Series(0.0, index=common)
    state = pd.Series("", index=common, dtype=object)
    for i, (sd, w) in enumerate(weights_history):
        fut = common[common > sd]
        if len(fut) < 1: continue
        af = fut[0]
        if i + 1 < len(weights_history):
            nf = common[common > weights_history[i + 1][0]]
            ea = nf[0] if len(nf) >= 1 else common[-1] + pd.Timedelta(days=1)
        else:
            ea = end + pd.Timedelta(days=1)
        mask = (common >= af) & (common < ea)
        for t, ww in w.items():
            if t in daily.columns:
                port.loc[mask] += daily[t].reindex(common).fillna(0.0).loc[mask] * ww
        state.loc[mask] = "|".join(f"{t}:{ww:.2f}" for t, ww in sorted(w.items()))
    if cost_bps > 0:
        arr = state.values
        if len(arr) > 1:
            flips = np.where(arr[1:] != arr[:-1])[0] + 1
            for f in flips:
                port.iloc[f] -= 2.0 * cost_bps / 10000.0
    return port


def bench_aaa_tip(panel, start, end, cost_bps=10.0):
    """B2: AAA standard with TIP canary on the canonical AAA universe.
    Top-half ranking by mom_13612U; min-var continuous weights via SLSQP;
    TIP canary (mom_13612U > 0) gates risk-on/off; HAA best-of-safe (SHV/IEF).
    """
    from cpm_live import sig_13612U, best_safe as _best_safe
    from scipy.optimize import minimize
    import math
    cols = sorted(set(BENCH_AAA_UNIVERSE + _BENCH_SAFE + ["TIP"]) & set(panel.columns))
    close = panel[cols]
    daily = close.ffill().pct_change()
    sig_dates = _b_monthly_signal_dates(close, start, end)
    wh = []
    for sd in sig_dates:
        monthly = close.loc[:sd].resample("ME").last()
        safe = _best_safe(monthly, sd, _BENCH_SAFE)
        tipm = sig_13612U(monthly["TIP"]) if "TIP" in monthly.columns else float("nan")
        if not (pd.notna(tipm) and tipm > 0):
            wh.append((sd, {safe: 1.0})); continue
        scores = {t: sig_13612U(monthly[t]) for t in BENCH_AAA_UNIVERSE if t in monthly.columns}
        scores = {t: s for t, s in scores.items() if pd.notna(s)}
        ranked = sorted(scores.items(), key=lambda x: -x[1])
        top_half = max(2, math.ceil(len(BENCH_AAA_UNIVERSE) / 2))
        top = [t for t, s in ranked[:top_half] if s > 0]
        if len(top) == 0:
            wh.append((sd, {safe: 1.0})); continue
        if len(top) == 1:
            wh.append((sd, {top[0]: 0.5, safe: 0.5})); continue
        cov = daily.loc[:sd].tail(504)[top].cov() * 252
        n = len(top)
        def obj(w, C=cov.values): return float(np.dot(w, np.dot(C, w)))
        cons = ({"type": "eq", "fun": lambda w: np.sum(w) - 1.0},)
        bnds = tuple((0.0, 1.0) for _ in range(n))
        w0 = np.ones(n) / n
        r = minimize(obj, w0, method="SLSQP", bounds=bnds, constraints=cons)
        weights = {top[i]: float(r.x[i]) for i in range(n)} if r.success else {t: 1.0/n for t in top}
        wh.append((sd, weights))
    return _b_build_port(close, wh, start, end, cost_bps)


def bench_haa_simple(panel, start, end, asset="SPY", cost_bps=10.0):
    """B3/B4: HAA-Simple N=1 specialization. Hold `asset` when TIP canary AND
    asset's own mom_13612U both positive; else HAA best-of-safe."""
    from cpm_live import sig_13612U, best_safe as _best_safe
    cols = sorted(set([asset] + _BENCH_SAFE + ["TIP"]) & set(panel.columns))
    close = panel[cols]
    sig_dates = _b_monthly_signal_dates(close, start, end)
    wh = []
    for sd in sig_dates:
        monthly = close.loc[:sd].resample("ME").last()
        safe = _best_safe(monthly, sd, _BENCH_SAFE)
        tipm = sig_13612U(monthly["TIP"]) if "TIP" in monthly.columns else float("nan")
        c_ok = pd.notna(tipm) and tipm > 0
        amom = sig_13612U(monthly[asset]) if asset in monthly.columns else float("nan")
        a_ok = pd.notna(amom) and amom > 0
        wh.append((sd, {asset: 1.0} if (c_ok and a_ok) else {safe: 1.0}))
    return _b_build_port(close, wh, start, end, cost_bps)


def bench_qqq_12mo_trend(panel, start, end, cost_bps=10.0):
    """B5: Antonacci 2014 GEM single-asset on QQQ. Hold QQQ when r12 > 0,
    else HAA best-of-safe."""
    from cpm_live import best_safe as _best_safe
    cols = sorted(set(["QQQ"] + _BENCH_SAFE) & set(panel.columns))
    close = panel[cols]
    sig_dates = _b_monthly_signal_dates(close, start, end)
    wh = []
    for sd in sig_dates:
        monthly = close.loc[:sd].resample("ME").last()
        safe = _best_safe(monthly, sd, _BENCH_SAFE)
        if "QQQ" in monthly.columns and len(monthly["QQQ"]) >= 13:
            r12 = monthly["QQQ"].iloc[-1] / monthly["QQQ"].iloc[-13] - 1
            if pd.notna(r12) and r12 > 0:
                wh.append((sd, {"QQQ": 1.0})); continue
        wh.append((sd, {safe: 1.0}))
    return _b_build_port(close, wh, start, end, cost_bps)


def bench_static_pp_qqq(panel, start, end, pp_weight=0.80, growth_ticker="QQQ"):
    """Static portfolio benchmark: 80% Permanent Portfolio + 20% QQQ buy-hold,
    monthly rebal between sleeves. PP itself is 25% each of SPY/IEF/GLD/SHV
    rebalanced monthly. So the effective static mix is:
      20% SPY  (from PP)
      20% IEF  (from PP)
      20% GLD  (from PP)
      20% SHV  (from PP)
      20% QQQ  (growth sleeve)
    Total ~40% equity (SPY + QQQ), 40% defensive (IEF + SHV), 20% gold.
    Chosen for closest Vol match to PROD 60/20/20 (PROD Vol ~8.9%, this ~9.1%).
    Acts as a 'what if you didn't time anything' static baseline alongside the
    BB4 active-TAA peer benchmark.
    """
    from cpm_live import run_pp_backtest
    pp = run_pp_backtest(panel, start, end)
    if growth_ticker not in panel.columns:
        return pd.Series(dtype=float)
    growth = panel[growth_ticker].ffill().pct_change()
    common = pp.index.intersection(growth.index)
    if len(common) == 0:
        return pd.Series(dtype=float)
    return (pp_weight * pp.reindex(common).fillna(0)
            + (1 - pp_weight) * growth.reindex(common).fillna(0))


def bench_bb4_blend(panel, start, end):
    """BB4 literature blend: 60% B2 (AAA+TIP) + 20% B3 (HAA-Simple SPY) +
    20% B5 (QQQ 12mo trend). Apples-to-apples 60/20/20 vs PROD."""
    b2 = bench_aaa_tip(panel, start, end)
    b3 = bench_haa_simple(panel, start, end, asset="SPY")
    b5 = bench_qqq_12mo_trend(panel, start, end)
    common = b2.index.intersection(b3.index).intersection(b5.index)
    if len(common) == 0:
        return pd.Series(dtype=float)
    return (0.60 * b2.reindex(common).fillna(0)
            + 0.20 * b3.reindex(common).fillna(0)
            + 0.20 * b5.reindex(common).fillna(0))


def bench_blend_4leg(panel, start, end):
    """Literature blend benchmark: 60% AAA+TIP + 15% HAA-Simple QQQ +
    15% HAA-Simple SPY + 10% PP."""
    from cpm_live import run_pp_backtest

    aaa_tip = bench_aaa_tip(panel, start, end)
    haa_qqq = bench_haa_simple(panel, start, end, asset="QQQ")
    haa_spy = bench_haa_simple(panel, start, end, asset="SPY")
    pp = run_pp_backtest(panel, start, end)
    common = aaa_tip.index.intersection(haa_qqq.index).intersection(haa_spy.index).intersection(pp.index)
    if len(common) == 0:
        return pd.Series(dtype=float)
    return (0.60 * aaa_tip.reindex(common).fillna(0)
            + 0.15 * haa_qqq.reindex(common).fillna(0)
            + 0.15 * haa_spy.reindex(common).fillna(0)
            + 0.10 * pp.reindex(common).fillna(0))


def bench_ew_rpv(panel, start, end):
    """Equal-weight benchmark over RPV risky universe (TLT/LQD/SPY/TIP/HYG)."""
    risky = ["TLT", "LQD", "SPY", "TIP", "HYG"]
    cols = [c for c in risky if c in panel.columns]
    if len(cols) == 0:
        return pd.Series(dtype=float)
    close = panel[cols]
    monthly_idx = pd.DataFrame({"x": 1}, index=close.index).groupby(pd.Grouper(freq="ME")).tail(1)
    dates = monthly_idx.index[(monthly_idx.index >= start) & (monthly_idx.index <= end)].tolist()
    daily_ret = close.ffill().pct_change()
    out = pd.Series(0.0, index=close.index)
    w = pd.Series({c: 1.0 / len(cols) for c in cols})
    for i, d in enumerate(dates):
        nxt = dates[i + 1] if i + 1 < len(dates) else end
        seg = close.index[(close.index > d) & (close.index <= nxt)]
        out.loc[seg] = daily_ret.loc[seg, cols].mul(w, axis=1).sum(axis=1).fillna(0.0)
    return out.loc[(out.index >= start) & (out.index <= end)]


def bench_sacevs_value_rotation(panel, start, end):
    """SACEVS-style 3-premia value rotation (term/credit/equity), no trend gate."""
    import rpv_live

    required_premia = ["term", "igcredit", "equity"]
    original_sma_check = rpv_live._sma_above
    original_compute_signals = rpv_live.compute_rpv_signals
    full_signals = original_compute_signals()
    if not set(required_premia).issubset(set(full_signals.columns)):
        return pd.Series(dtype=float)
    sacevs_signals = full_signals[required_premia].copy()

    rpv_live._sma_above = lambda *args, **kwargs: True
    rpv_live.compute_rpv_signals = lambda: sacevs_signals
    try:
        return rpv_live.run_rpv_backtest(panel, start, end, cost_bps=RPV_COST_BPS_PER_SIDE)
    finally:
        rpv_live._sma_above = original_sma_check
        rpv_live.compute_rpv_signals = original_compute_signals


def alpha_beta_corr(strat: pd.Series, bench: pd.Series) -> dict:
    """OLS daily-return regression r_strat = alpha + beta * r_bench + eps.
    Returns dict with annualized alpha (%/yr), beta, and Pearson correlation.
    """
    common = strat.index.intersection(bench.index)
    if len(common) < 30:
        return {"alpha_ann_pct": float("nan"), "beta": float("nan"), "corr": float("nan")}
    s = strat.reindex(common).fillna(0.0).values
    b = bench.reindex(common).fillna(0.0).values
    if np.std(b) < 1e-12:
        return {"alpha_ann_pct": float("nan"), "beta": float("nan"), "corr": float("nan")}
    cov = np.cov(s, b, ddof=1)
    beta = cov[0, 1] / cov[1, 1]
    alpha_daily = float(np.mean(s) - beta * np.mean(b))
    return {
        "alpha_ann_pct": alpha_daily * 252 * 100,
        "beta": float(beta),
        "corr": float(np.corrcoef(s, b)[0, 1]),
    }


# Module-level cache for cpm_signal_records. Several dashboard diagnostics
# (canary timeline, asset picks, basket archetypes, rolling defensive %, basket
# timeline) all call cpm_signal_records with the same (start, end). Without
# caching, this runs the full monthly signal loop 5+ times per build; with
# caching, it runs once. Keyed by (id(panel), start, end) since panel is
# unhashable but is the same object across calls within one build_dashboard
# invocation.
_CPM_RECORDS_CACHE: dict = {}


def cpm_signal_records(panel: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp | None = None) -> list[dict]:
    """Production-equivalent monthly CPM signal path for dashboard diagnostics.

    Mirrors run_cpm_backtest breadth-majority hold-buffer reset so charts/tables
    do not drift from the live strategy path. Memoized per (panel, start, end)
    to avoid recomputation across the 5+ diagnostic call sites.
    """
    cache_key = (id(panel), pd.Timestamp(start), pd.Timestamp(end) if end is not None else None)
    if cache_key in _CPM_RECORDS_CACHE:
        return _CPM_RECORDS_CACHE[cache_key]
    records = _compute_cpm_signal_records(panel, start, end)
    _CPM_RECORDS_CACHE[cache_key] = records
    return records


def _compute_cpm_signal_records(panel: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp | None = None) -> list[dict]:
    """Actual signal-record computation (cache miss path).

    Excludes the current in-progress calendar month: pd.Grouper(freq='ME')
    picks 'last trading day per month bucket', which for the current month is
    just today (or the latest panel day), NOT the actual month-end signal
    date. PROD doesn't execute on mid-month signals, so including them creates
    phantom records in the basket table / records list (e.g. a 'signal' on
    2026-05-22 when the actual May signal would be computed on 2026-05-29).
    """
    cols = sorted(set(RISKY_UNIVERSE + SAFE_POOL + CANARY_ASSETS + [DEFAULT_CASH]) & set(panel.columns))
    close = panel[cols]
    monthly_idx = pd.DataFrame({"x": 1}, index=close.index).groupby(pd.Grouper(freq="ME")).tail(1)
    mask = monthly_idx.index >= start
    if end is not None:
        mask &= monthly_idx.index <= end
    # Drop in-progress current calendar month: signal is only real once its
    # month-end has actually arrived.
    this_month_start = get_last_finalized_month_cutoff(panel.index)
    mask &= monthly_idx.index < this_month_start
    sig_dates = monthly_idx.index[mask].tolist()

    records = []
    for sig_d in sig_dates:
        monthly = close.loc[:sig_d].resample("ME").last()
        hyg_mom = sig_13612U(monthly["HYG"]) if "HYG" in monthly.columns else float("nan")
        hyg_gate_on = not (pd.notna(hyg_mom) and hyg_mom < 0.0)
        n_pos = 1 if hyg_gate_on else 0
        risk_state = "ON" if hyg_gate_on else "OFF"
        weights, new_basket, regime, safe = compute_target_weights(close, sig_d)
        records.append({
            "sig_d": sig_d,
            "weights": weights,
            "basket": new_basket,
            "regime": regime,
            "safe": safe,
            "canary_positive_count": n_pos,
            "risk_state": risk_state,
        })
    return records


# ============================================================================
# Per-signal-date records for RPV and NDX sleeves. Precompute once and memoize
# so diagnostics reuse one consistent signal path.
# ============================================================================
_RPV_RECORDS_CACHE: dict = {}
_NDX_RECORDS_CACHE: dict = {}


def _load_macro_mooex_legs(panel_index: pd.DatetimeIndex) -> tuple[object, pd.DataFrame, pd.DataFrame]:
    """Load macro-asset overnight/intraday legs used by mooex attribution."""
    import engine as moo_engine
    open_df, close_yf = moo_engine.load_open_close()
    intraday = (close_yf / open_df - 1.0).reindex(panel_index)
    overnight = (open_df / close_yf.shift(1) - 1.0).reindex(panel_index)
    return moo_engine, intraday, overnight


def _rebuild_ndx_constituent_opens_cache() -> None:
    """Build adjusted Open/Close cache for NDX constituents from the refreshed close panel."""
    if not NDX_PRICES_FILE.exists():
        raise FileNotFoundError(
            f"NDX constituent close panel missing at {NDX_PRICES_FILE}; cannot rebuild opens cache."
        )

    closes = pd.read_parquet(NDX_PRICES_FILE)
    if closes.empty or len(closes.columns) == 0:
        raise ValueError(f"NDX constituent close panel empty at {NDX_PRICES_FILE}; cannot rebuild opens cache.")

    tickers = sorted(map(str, closes.columns))
    closes_max = pd.Timestamp(closes.index.max())
    fetch_start_ts = pd.Timestamp(closes.index.min())
    base_cache = pd.DataFrame()

    if NDX_OPENS_CACHE_PATH.exists():
        base_cache = pd.read_parquet(NDX_OPENS_CACHE_PATH)
        if not isinstance(base_cache.columns, pd.MultiIndex) or {"Open", "Close"} - set(
            base_cache.columns.get_level_values(0)
        ):
            raise ValueError(
                f"Unexpected NDX opens cache schema at {NDX_OPENS_CACHE_PATH}; expected MultiIndex with Open/Close."
            )
        base_cache = base_cache.sort_index()
        if not base_cache.empty:
            fetch_start_ts = pd.Timestamp(base_cache.index.max())
            print(
                f"NDX opens tail refresh start={fetch_start_ts.date().isoformat()} "
                f"(base_max={fetch_start_ts.date().isoformat()}, closes_max={closes_max.date().isoformat()})"
            )

    if not base_cache.empty and fetch_start_ts > closes_max:
        out = base_cache
        fetched = 0
    else:
        start = fetch_start_ts.strftime("%Y-%m-%d")
        end = (closes_max + pd.Timedelta(days=1)).strftime("%Y-%m-%d")

        import yfinance as yf

        source = NDX_OPENS_CACHE_PATH if not base_cache.empty else NDX_PRICES_FILE
        print(
            f"NDX opens cache refresh at {NDX_OPENS_CACHE_PATH} from {source} "
            f"for {len(tickers)} tickers ({start}..{end})."
        )

        opens: dict[str, pd.Series] = {}
        ycloses: dict[str, pd.Series] = {}
        chunks = [tickers[i:i + 25] for i in range(0, len(tickers), 25)]

        for ci, chunk in enumerate(chunks, start=1):
            chunk_df = None
            for attempt in range(1, 4):
                try:
                    chunk_df = yf.download(
                        chunk,
                        start=start,
                        end=end,
                        auto_adjust=True,
                        progress=False,
                        threads=True,
                        group_by="ticker",
                        timeout=60,
                    )
                    break
                except Exception as exc:
                    print(f"  NDX opens chunk {ci}/{len(chunks)} attempt {attempt}/3 failed: {exc}")

            if chunk_df is None:
                continue

            if isinstance(chunk_df.columns, pd.MultiIndex):
                lvl0 = chunk_df.columns.get_level_values(0)
                for t in chunk:
                    if t not in lvl0:
                        continue
                    sub = chunk_df[t]
                    if "Open" in sub and sub["Open"].notna().any():
                        opens[t] = sub["Open"]
                        ycloses[t] = sub["Close"]
            else:
                t = chunk[0]
                if "Open" in chunk_df and chunk_df["Open"].notna().any():
                    opens[t] = chunk_df["Open"]
                    ycloses[t] = chunk_df["Close"]

            got = sum(1 for t in chunk if t in opens)
            print(f"  NDX opens chunk {ci}/{len(chunks)} got {got}/{len(chunk)}")

        fetched = int(sum(1 for s in opens.values() if s.notna().any()))
        tail_out = None
        if opens:
            open_df = pd.DataFrame(opens).sort_index().reindex(columns=tickers)
            yclose_df = pd.DataFrame(ycloses).sort_index().reindex(columns=tickers)
            tail_out = pd.concat({"Open": open_df, "Close": yclose_df}, axis=1)

        if tail_out is not None and not tail_out.empty:
            if not base_cache.empty:
                out = pd.concat([base_cache[base_cache.index < tail_out.index.min()], tail_out], axis=0).sort_index()
                out = out.loc[~out.index.duplicated(keep="last")]
            else:
                out = tail_out.sort_index()
        elif not base_cache.empty:
            out = base_cache
        else:
            raise RuntimeError("Failed to fetch any NDX constituent opens from yfinance.")

    NDX_OPENS_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(NDX_OPENS_CACHE_PATH)
    print(f"NDX opens cache rebuilt: {NDX_OPENS_CACHE_PATH} ({fetched}/{len(tickers)} tickers fetched).")


def _tail_refresh_ndx_opens_cache(cache: pd.DataFrame, panel_index: pd.DatetimeIndex) -> pd.DataFrame:
    """Refresh cached NDX opens with a timed tail fetch; fall back to base cache on failures."""
    if cache.empty:
        return cache

    panel_end = pd.Timestamp(panel_index.max())
    base_max = pd.Timestamp(cache.index.max())
    if base_max > panel_end:
        return cache

    fetch_start_ts = base_max - pd.Timedelta(days=5)
    start = fetch_start_ts.strftime("%Y-%m-%d")
    end = (panel_end + pd.Timedelta(days=1)).strftime("%Y-%m-%d")

    import index_constitution as ic
    import yfinance as yf

    as_of = pd.Timestamp.today().strftime("%Y-%m-%d")
    current_df = ic.constituents_at("nasdaq100", as_of)
    current = sorted(map(str, current_df["symbol"].unique()))

    cache_tickers = sorted(map(str, cache["Open"].columns))
    cache_set = set(cache_tickers)
    tail_tickers = [t for t in current if t in cache_set]
    full_tickers = [t for t in current if t not in cache_set]
    print(
        f"NDX opens tail: fetching {len(current)} current constituents "
        f"({len(tail_tickers)} tail, {len(full_tickers)} full)."
    )

    def _fetch_open_close(tickers: list[str], fetch_start: str) -> pd.DataFrame:
        if not tickers:
            return pd.DataFrame()

        opens: dict[str, pd.Series] = {}
        ycloses: dict[str, pd.Series] = {}
        chunks = [tickers[i:i + 25] for i in range(0, len(tickers), 25)]

        for chunk in chunks:
            try:
                chunk_df = yf.download(
                    chunk,
                    start=fetch_start,
                    end=end,
                    auto_adjust=True,
                    progress=False,
                    threads=True,
                    group_by="ticker",
                    timeout=30,
                )
            except Exception:
                continue

            if chunk_df is None or chunk_df.empty:
                continue

            if isinstance(chunk_df.columns, pd.MultiIndex):
                lvl0 = chunk_df.columns.get_level_values(0)
                for t in chunk:
                    if t not in lvl0:
                        continue
                    sub = chunk_df[t]
                    if "Open" in sub and "Close" in sub and sub["Open"].notna().any():
                        opens[t] = sub["Open"]
                        ycloses[t] = sub["Close"]
            else:
                t = chunk[0]
                if "Open" in chunk_df and "Close" in chunk_df and chunk_df["Open"].notna().any():
                    opens[t] = chunk_df["Open"]
                    ycloses[t] = chunk_df["Close"]

        if not opens:
            return pd.DataFrame()

        out_open = pd.DataFrame(opens).sort_index().reindex(columns=tickers)
        out_close = pd.DataFrame(ycloses).sort_index().reindex(columns=tickers)
        return pd.concat({"Open": out_open, "Close": out_close}, axis=1).dropna(how="all")

    tail = _fetch_open_close(tail_tickers, start)
    full = _fetch_open_close(full_tickers, "1995-01-01")

    out = cache.copy()
    base_order = list(cache.columns)
    for fresh in (tail, full):
        if fresh.empty:
            continue
        out = out.reindex(out.index.union(fresh.index)).sort_index()
        for col in fresh.columns:
            if col not in out.columns:
                out[col] = np.nan
        out.update(fresh)

    out = out.loc[~out.index.duplicated(keep="last")]
    out = out.loc[:, ~out.columns.duplicated()]
    extra_cols = [c for c in out.columns if c not in base_order]
    if extra_cols:
        out = out.reindex(columns=base_order + sorted(extra_cols, key=lambda c: (c[0], c[1])))
    return out


def _load_ndx_constituent_mooex_legs(panel_index: pd.DatetimeIndex) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load NDX constituent overnight/intraday legs from cached adjusted opens."""
    if not NDX_OPENS_CACHE_PATH.exists():
        _rebuild_ndx_constituent_opens_cache()

    cache = pd.read_parquet(NDX_OPENS_CACHE_PATH)
    if not isinstance(cache.columns, pd.MultiIndex) or {"Open", "Close"} - set(cache.columns.get_level_values(0)):
        raise ValueError(
            f"Unexpected NDX opens cache schema at {NDX_OPENS_CACHE_PATH}; expected MultiIndex with Open/Close."
        )

    cache = cache.sort_index()

    c_open = cache["Open"]
    c_close = cache["Close"]
    intraday = (c_close / c_open - 1.0)
    overnight = (c_open / c_close.shift(1) - 1.0)
    bad = intraday.abs() > MOOEX_INTRADAY_SANITY_MAX
    intraday = intraday.mask(bad).reindex(panel_index)
    overnight = overnight.mask(bad).reindex(panel_index)
    return intraday, overnight


def rpv_signal_records(panel: pd.DataFrame, start: pd.Timestamp,
                          end: pd.Timestamp | None = None) -> list[dict]:
    """RPV sleeve weights at each monthly signal date. Memoized.
    Excludes in-progress current calendar month (see cpm_signal_records).
    """
    key = (id(panel), pd.Timestamp(start), pd.Timestamp(end) if end else None)
    if key in _RPV_RECORDS_CACHE:
        return _RPV_RECORDS_CACHE[key]
    monthly_idx = pd.DataFrame({"x": 1}, index=panel.index).groupby(pd.Grouper(freq="ME")).tail(1)
    mask = monthly_idx.index >= start
    if end is not None:
        mask &= monthly_idx.index <= end
    this_month_start = get_last_finalized_month_cutoff(panel.index)
    mask &= monthly_idx.index < this_month_start
    sig_dates = monthly_idx.index[mask].tolist()
    records = []
    for sd in sig_dates:
        w, regime, diag = compute_rpv_weights(panel, sd)
        records.append({"sig_d": sd, "weights": w, "regime": regime, "diag": diag})
    _RPV_RECORDS_CACHE[key] = records
    return records


def ndx_signal_records(panel: pd.DataFrame, ndx_panel: pd.DataFrame,
                        start: pd.Timestamp, end: pd.Timestamp | None = None) -> list[dict]:
    """NDX sleeve weights at each monthly signal date. Memoized.
    Excludes in-progress current calendar month (see cpm_signal_records).
    """
    from ndx_sleeve_live import compute_ndx_weights
    key = (id(panel), id(ndx_panel), pd.Timestamp(start), pd.Timestamp(end) if end else None)
    if key in _NDX_RECORDS_CACHE:
        return _NDX_RECORDS_CACHE[key]
    monthly_idx = pd.DataFrame({"x": 1}, index=panel.index).groupby(pd.Grouper(freq="ME")).tail(1)
    mask = monthly_idx.index >= start
    if end is not None:
        mask &= monthly_idx.index <= end
    this_month_start = get_last_finalized_month_cutoff(panel.index)
    mask &= monthly_idx.index < this_month_start
    sig_dates = monthly_idx.index[mask].tolist()
    records = []
    for sd in sig_dates:
        w, regime, diag = compute_ndx_weights(panel, ndx_panel, sd)
        records.append({"sig_d": sd, "weights": w, "regime": regime, "diag": diag})
    _NDX_RECORDS_CACHE[key] = records
    return records


# ============================================================================
# build_artifacts: single source of truth for all dashboard inputs.
# Computes once at start of main(), passed (or available via memoization) to
# every chart/table function. Keeps compute_*_weights() and run_*_backtest()
# calls consistent across views.
# ============================================================================
from types import SimpleNamespace


def _pit_lib_version() -> str | None:
    try:
        return f"index_constitution=={importlib_metadata.version('index_constitution')}"
    except Exception:
        return None


def _ndx_cache_params(cost_bps: float) -> dict[str, float]:
    return {
        "SELECT_K": float(NDX_SELECT_K),
        "VOL_FAST_DAYS": float(NDX_VOL_FAST_DAYS),
        "VOL_SLOW_DAYS": float(NDX_VOL_SLOW_DAYS),
        "COST_BPS_PER_SIDE": float(cost_bps),
        "DELISTING_HAIRCUT": float(NDX_DELISTING_HAIRCUT),
    }


def _ndx_gate_panel(panel: pd.DataFrame) -> pd.DataFrame:
    gate_cols = sorted(set(["SPY", "TIP", *SAFE_POOL]) & set(panel.columns))
    return panel[gate_cols]


def _ndx_cache_data(panel: pd.DataFrame, ndx_panel: pd.DataFrame) -> dict[str, str | None]:
    return {
        "gate_panel": df_digest(_ndx_gate_panel(panel)),
        "ndx_panel": df_digest(ndx_panel),
        "pit_lib": _pit_lib_version(),
        "ndx_opens": file_digest(NDX_OPENS_CACHE_PATH),
    }


def _compute_ndx_sleeve_series_with_fb(
    panel: pd.DataFrame,
    ndx_panel: pd.DataFrame,
    run_start: pd.Timestamp,
    end: pd.Timestamp,
    cost_bps: float,
    moo_engine,
    macro_intraday: pd.DataFrame,
    macro_overnight: pd.DataFrame,
) -> tuple[pd.Series, tuple[int, int]]:
    ndx_cc_full, _ = run_ndx_backtest(panel, ndx_panel, run_start, end, cost_bps=cost_bps)
    full_panel = panel.join(ndx_panel, how="outer", rsuffix="_dup")
    full_panel = full_panel.loc[:, ~full_panel.columns.str.endswith("_dup")]
    full_panel = full_panel.loc[full_panel.index <= end]
    ndx_daily = full_panel.ffill().pct_change()

    ndx_intraday, ndx_overnight = _load_ndx_constituent_mooex_legs(full_panel.index)
    intraday_full = macro_intraday.reindex(full_panel.index)
    overnight_full = macro_overnight.reindex(full_panel.index)
    add_cols = [c for c in ndx_intraday.columns if c not in intraday_full.columns]
    if add_cols:
        intraday_full = intraday_full.join(ndx_intraday[add_cols], how="left")
        overnight_full = overnight_full.join(ndx_overnight[add_cols], how="left")

    from core import get_cached_sleeve_weight

    ndx_wf = lambda sd: get_cached_sleeve_weight(
        "ndx", panel, sd, compute_ndx_weights, panel, ndx_panel, sd
    )[0]
    ndx_moc_full, _ = moo_engine._segment_returns_conv(
        full_panel,
        ndx_daily,
        ndx_wf,
        run_start,
        end,
        "moc",
        cost_bps,
        intraday_full,
        overnight_full,
    )
    ndx_mooex_full, ndx_fb = moo_engine._segment_returns_conv(
        full_panel,
        ndx_daily,
        ndx_wf,
        run_start,
        end,
        "mooex",
        cost_bps,
        intraday_full,
        overnight_full,
    )
    ndx_delta = (ndx_mooex_full - ndx_moc_full).reindex(ndx_cc_full.index).fillna(0.0)
    return ndx_cc_full + ndx_delta, ndx_fb


def compute_ndx_sleeve_series(
    panel: pd.DataFrame,
    ndx_panel: pd.DataFrame,
    run_start: pd.Timestamp,
    end: pd.Timestamp,
    cost_bps: float,
) -> pd.Series:
    moo_engine, macro_intraday, macro_overnight = _load_macro_mooex_legs(panel.index)
    ndx_raw_full, ndx_fb = _compute_ndx_sleeve_series_with_fb(
        panel,
        ndx_panel,
        run_start,
        end,
        cost_bps,
        moo_engine,
        macro_intraday,
        macro_overnight,
    )
    compute_ndx_sleeve_series.last_fb = (int(ndx_fb[0]), int(ndx_fb[1]))
    return ndx_raw_full


compute_ndx_sleeve_series.last_fb = (0, 0)


def build_artifacts(panel: pd.DataFrame, ndx_panel: pd.DataFrame | None,
                     start: pd.Timestamp, end: pd.Timestamp,
                     include_records: bool = True) -> SimpleNamespace:
    """Compute every per-build artifact ONCE.

    Returns SimpleNamespace with:
      panel, ndx_panel, start, end
      cpm, rpv_raw, ndx_raw, val_raw  - daily return Series
      rpv, ndx, val                   - daily return Series
      rpv_dd_scale, ndx_dd_scale      - daily scale Series (identity)
      vol_scale, vol_events           - portfolio overlay scale/events (identity)
      blend_uncapped, blend           - portfolio daily returns
      sigs                            - signal dates list
      cpm_records, rpv_records, ndx_records, val_records - per-signal-date weights/regime
                                                           (only populated when include_records=True;
                                                           EXT 30y window skips these for speed)
    """
    run_start = max(EXT_START, panel.index.min())
    moo_engine, macro_intraday, macro_overnight = _load_macro_mooex_legs(panel.index)

    # CPM sleeve (canonical mooex T+1 exact).
    cpm_cols = sorted(set(RISKY_UNIVERSE + SAFE_POOL + CANARY_ASSETS + [DEFAULT_CASH]) & set(panel.columns))
    cpm_close = panel[cpm_cols]
    cpm_daily = cpm_close.ffill().pct_change()
    from core import get_cached_sleeve_weight
    cpm_wf = lambda sd: get_cached_sleeve_weight(
        "cpm", cpm_close, sd, compute_target_weights, cpm_close, sd
    )[0]
    cpm_full, cpm_fb = moo_engine._segment_returns_conv(
        cpm_close,
        cpm_daily,
        cpm_wf,
        run_start,
        end,
        "mooex",
        COST_BPS_PER_SIDE,
        macro_intraday,
        macro_overnight,
    )
    # RPV sleeve (production logic, mooex execution attribution).
    rpv_cols = sorted(set([RPV_EQUITY_TICKER, "TLT", "LQD", CASH_TICKER]) & set(panel.columns))
    rpv_close = panel[rpv_cols]
    rpv_daily = panel.ffill().pct_change()
    from core import get_cached_sleeve_weight
    rpv_wf = lambda sd: get_cached_sleeve_weight(
        "rpv", panel, sd, compute_rpv_weights, panel, sd
    )[0]
    rpv_raw_full, rpv_fb = moo_engine._segment_returns_conv(
        rpv_close,
        rpv_daily,
        rpv_wf,
        run_start,
        end,
        "mooex",
        RPV_COST_BPS_PER_SIDE,
        macro_intraday,
        macro_overnight,
    )
    # NDX sleeve (production engine plus mooex delta overlay with constituent opens).
    if ndx_panel is not None:
        ndx_meta: dict[str, list[int]] = {}

        def _compute_ndx() -> pd.Series:
            ndx_raw = compute_ndx_sleeve_series(
                panel,
                ndx_panel,
                run_start,
                end,
                NDX_COST_BPS_PER_SIDE,
            )
            ndx_fb_local = getattr(compute_ndx_sleeve_series, "last_fb", (0, 0))
            ndx_meta["ndx_fb"] = [int(ndx_fb_local[0]), int(ndx_fb_local[1])]
            return ndx_raw

        ndx_raw_full = get_sleeve_returns(
            "ndx",
            panel=panel,
            ndx_panel=ndx_panel,
            run_start=run_start,
            end=end,
            cost_bps=NDX_COST_BPS_PER_SIDE,
            params=_ndx_cache_params(NDX_COST_BPS_PER_SIDE),
            version=NDX_SLEEVE_VERSION,
            data=_ndx_cache_data(panel, ndx_panel),
            source_files=NDX_SOURCE_FILES,
            compute_fn=_compute_ndx,
            meta=ndx_meta,
        )
        ndx_fb_raw = ndx_meta.get("ndx_fb", [0, 0])
        ndx_fb = (int(ndx_fb_raw[0]), int(ndx_fb_raw[1]))
        val_raw_full, val_history = cached_value_backtest(panel, ndx_panel, run_start, end)
    else:
        rpv_idx = rpv_raw_full.index
        ndx_raw_full = pd.Series(0.0, index=rpv_idx)
        ndx_fb = (0, 0)
        val_raw_full = pd.Series(0.0, index=rpv_idx)
        val_history = []

    cpm = cpm_full.loc[(cpm_full.index >= start) & (cpm_full.index <= end)]
    rpv_raw = rpv_raw_full.loc[(rpv_raw_full.index >= start) & (rpv_raw_full.index <= end)]
    ndx_raw = ndx_raw_full.loc[(ndx_raw_full.index >= start) & (ndx_raw_full.index <= end)]
    val_raw = val_raw_full.loc[(val_raw_full.index >= start) & (val_raw_full.index <= end)]

    common = cpm.index.intersection(rpv_raw.index).intersection(ndx_raw.index).intersection(val_raw.index)
    cpm = cpm.reindex(common)
    rpv_raw = rpv_raw.reindex(common)
    ndx_raw = ndx_raw.reindex(common).fillna(0.0)
    val_raw = val_raw.reindex(common).fillna(0.0)

    sigs = (pd.DataFrame({"x": 1}, index=cpm.index)
             .groupby(pd.Grouper(freq="ME")).tail(1).index.tolist())
    # Monthly sleeve gates only.
    # RPV, NDX, and VAL are monthly-gated sleeves only.
    rpv = rpv_raw
    ndx = ndx_raw
    val = val_raw
    rpv_dd_scale = pd.Series(1.0, index=rpv_raw.index)
    ndx_dd_scale = pd.Series(1.0, index=ndx_raw.index)

    blend_weights, blend_turnover = build_blend_weight_schedule(common, sigs, end)
    blend_uncapped = (
        blend_weights["cpm"] * cpm
        + blend_weights["ndx"] * ndx
        + blend_weights["val"] * val
        + blend_weights["rpv"] * rpv
    )
    blend_uncapped = apply_blend_reallocation_cost(
        blend_uncapped,
        blend_turnover,
        CROSS_SLEEVE_REALLOCATION_COST_BPS,
    )
    # No additional portfolio-level cap overlay.
    vol_scale = pd.Series(1.0, index=blend_uncapped.index)
    vol_events: list[dict] = []
    blend = blend_uncapped
    if include_records:
        cpm_records = cpm_signal_records(panel, start, end)
        rpv_records = rpv_signal_records(panel, start, end)
        ndx_records = (ndx_signal_records(panel, ndx_panel, start, end)
                        if ndx_panel is not None else [])
        this_month_start = get_last_finalized_month_cutoff(panel.index)
        val_records = []
        for r in val_history:
            sd = r.get("sig_d")
            if sd is None:
                continue
            if start <= sd <= end and sd < this_month_start:
                val_records.append(r)
    else:
        cpm_records = rpv_records = ndx_records = val_records = []

    mooex_coverage = {
        "cpm_real": int(cpm_fb[0]),
        "cpm_fallback": int(cpm_fb[1]),
        "rpv_real": int(rpv_fb[0]),
        "rpv_fallback": int(rpv_fb[1]),
        "ndx_real": int(ndx_fb[0]),
        "ndx_fallback": int(ndx_fb[1]),
    }

    return SimpleNamespace(
        panel=panel, ndx_panel=ndx_panel, start=start, end=end,
        cpm=cpm, rpv_raw=rpv_raw, ndx_raw=ndx_raw, val_raw=val_raw,
        rpv=rpv, ndx=ndx, val=val,
        rpv_dd_scale=rpv_dd_scale, ndx_dd_scale=ndx_dd_scale,
        vol_scale=vol_scale, vol_events=vol_events,
        blend_uncapped=blend_uncapped, blend=blend,
        sigs=sigs,
        cpm_records=cpm_records,
        rpv_records=rpv_records,
        ndx_records=ndx_records,
        val_records=val_records,
        mooex_coverage=mooex_coverage,
    )
