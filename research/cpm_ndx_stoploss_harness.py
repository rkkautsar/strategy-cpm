"""Monthly-SET, INTRAMONTH-TRIGGERED vol-based stop-loss on the NDX sleeve.

Intramonth complement to monthly vol-targeting: catches mid-month single-stock
crashes that monthly exposure-scaling cannot see.

MECHANISM
  - Keep PROD selection: 13612U momentum top-5 EW, gating, best-of-safe, T+1 MOO.
  - At each monthly rebalance, set a per-stock STOP LEVEL from lagged vol (+ mu).
    * sigma_monthly = trailing daily return std (window W, up to sig_d, lagged)
      * sqrt(21).  No look-ahead: uses only data through the signal date.
    * mu_monthly    = trailing daily mean (window W, up to sig_d) * 21.
  - Walk DAILY through the holding month.  Track each held stock's CUMULATIVE
    intramonth return from the rebalance reference price (close at sig_d).
  - If a held stock's cumulative return breaches its stop on close day t, EXIT
    that stock to the period's best-of-safe asset, effective from t+1 (prod's
    T+1 MOO convention: the breach day's move is still borne by the stock; safe
    applies from the next close).  No re-entry until the next rebalance.
  - 10bps/side on each stop rotation (sell stock + buy safe).

STOP VARIANTS
  - Vol-multiple:  exit if cum_ret < -k * sigma_monthly        (k in 1.5,2,3)
  - Expected-band: exit if cum_ret < (mu_monthly - z * sigma)  (z in 1,2)

EXECUTION / FILL
  Conservative.  Breach detected at CLOSE t (no intraday/look-ahead).  The stock
  is liquidated at t+1 close-to-close (T+1 MOO, identical to prod rebalance
  convention).  Fill is therefore at/under the trigger close -- i.e. we DO NOT
  assume a clean fill at the stop level, and we DO bear the breach-day move +
  any next-day gap.  This is the conservative end of the fill spectrum; a
  fill-at-stop-level model would be strictly more favourable to the stop.

CAVEATS (stated up front; see findings .md):
  - Daily panel data/ndx_constituents/prices.parquet is auto-adjusted Close
    only.  No intraday => cannot model true intra-day stop fills; we use T+1
    close as conservative proxy.
  - PIT NDX membership via index_constitution (>=2006); pre-2006 the sleeve
    falls back to SPY proxy, so per-crisis dot-com is CONTEXT only.
  - Path-dependent design (k/z/level/W DoF) -> high overfit risk; we report
    defaults + sensitivity, single in-sample, bootstrap + walk-forward.
  - PROD and EVERY stop variant run on the IDENTICAL dataset (apples-to-apples
    directional comparison), per scope relaxation.
"""
from __future__ import annotations
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "/Users/rkautsar/personal/scripts/strategy_cpm")

from cpm_live import load_panel, perf_metrics
from ndx_sleeve_live import (
    load_ndx_panel, compute_ndx_weights, SAFE_POOL, CASH_TICKER,
    COST_BPS_PER_SIDE, SELECT_K, _pick_safe,
)

VOL_WINDOW = 63  # trailing daily window for lagged sigma/mu


def get_monthly_history(cpm_panel, ndx_panel, start, end):
    """Recompute monthly picks; return list of period dicts + full_panel.

    Each period: sig_d, apply_from (T+1), end_apply (next apply_from), target
    weights, safe pick, list of selected stocks.
    """
    full_panel = cpm_panel.join(ndx_panel, how="outer", rsuffix="_dup")
    full_panel = full_panel.loc[:, ~full_panel.columns.str.endswith("_dup")]
    monthly_idx = pd.DataFrame({"x": 1}, index=full_panel.index).groupby(
        pd.Grouper(freq="ME")).tail(1).index
    sig_dates = monthly_idx[(monthly_idx >= start) & (monthly_idx <= end)]
    history = []
    for sd in sig_dates:
        target, regime, diag = compute_ndx_weights(cpm_panel, ndx_panel, sd)
        next_loc = full_panel.index.get_indexer([sd], method="bfill")[0] + 1
        if next_loc >= len(full_panel.index):
            continue
        apply_from = full_panel.index[next_loc]
        stocks = [t for t in target if t in ndx_panel.columns]
        safes = [t for t in target if t in SAFE_POOL or t == CASH_TICKER]
        if safes:
            safe = safes[0]
        else:
            cpm_monthly = cpm_panel.loc[:sd].resample("ME").last()
            safe = _pick_safe(cpm_monthly)
        history.append({
            "sig_d": sd, "apply_from": apply_from, "target": dict(target),
            "safe": safe, "stocks": stocks, "regime": regime,
        })
    # fill end_apply
    for i, h in enumerate(history):
        h["end_apply"] = history[i + 1]["apply_from"] if i + 1 < len(history) else None
    return history, full_panel


def _stop_thresholds(ndx_panel, stock, sig_d, kind, k=None, z=None, W=VOL_WINDOW):
    """Lagged per-stock stop threshold on CUMULATIVE intramonth return.
    Uses only daily data up to and including sig_d (no look-ahead)."""
    s = ndx_panel[stock].loc[:sig_d].dropna()
    if len(s) < W + 2:
        return None
    r = s.pct_change().dropna().tail(W)
    if len(r) < W // 2:
        return None
    sigma_d = float(r.std(ddof=0))
    mu_d = float(r.mean())
    sigma_m = sigma_d * np.sqrt(21.0)
    mu_m = mu_d * 21.0
    if sigma_m <= 0:
        return None
    if kind == "vol_mult":
        return -k * sigma_m
    if kind == "exp_band":
        return mu_m - z * sigma_m
    raise ValueError(kind)


def run_with_stops(history, full_panel, ndx_panel, start, end,
                   kind=None, k=None, z=None, W=VOL_WINDOW,
                   cost_bps=COST_BPS_PER_SIDE):
    """Run NDX sleeve with monthly-set intramonth cumulative-return stops.

    Returns (daily_rets, stats) where stats has stop counts / whipsaw / turnover.
    kind=None => PROD reference (no stops).
    """
    idx = full_panel.loc[start:end].index
    daily_rets = pd.Series(0.0, index=idx)
    history_by_apply = {h["apply_from"]: h for h in history}
    apply_set = set(history_by_apply.keys())

    cur_w = {CASH_TICKER: 1.0}
    cur_stocks = []
    cur_safe = CASH_TICKER
    entry_ref = {}      # stock -> reference close at sig_d
    stop_level = {}     # stock -> threshold on cum return
    stopped_out = set()
    exit_info = {}      # stock -> (exit_cum_ret, exit_ts) for whipsaw eval
    cur_sig_d = None
    cur_end_apply = None

    total_turnover = 0.0
    n_stops = 0
    whipsaw_hits = 0
    whipsaw_total = 0
    # collect per-period stop bookkeeping to evaluate rebound at end of period
    pending_whipsaw = []  # list of (stock, exit_ref_price, end_apply)

    for ts in idx:
        # ---- monthly rebalance ----
        if ts in apply_set:
            # before reset, evaluate whipsaw for prior period's stops at this rebal
            h = history_by_apply[ts]
            new_w = dict(h["target"])
            tovr = sum(abs(cur_w.get(a, 0) - new_w.get(a, 0))
                       for a in set(cur_w) | set(new_w))
            total_turnover += tovr
            daily_rets.loc[ts] -= tovr * cost_bps / 10000.0
            cur_w = new_w
            cur_stocks = list(h["stocks"])
            cur_safe = h["safe"]
            cur_sig_d = h["sig_d"]
            cur_end_apply = h["end_apply"]
            stopped_out = set()
            entry_ref = {}
            stop_level = {}
            for stk in cur_stocks:
                ser = ndx_panel[stk].loc[:cur_sig_d].dropna()
                if ser.empty:
                    continue
                entry_ref[stk] = float(ser.iloc[-1])
                if kind is not None:
                    thr = _stop_thresholds(ndx_panel, stk, cur_sig_d, kind, k=k, z=z, W=W)
                    if thr is not None:
                        stop_level[stk] = thr

        # ---- compute today's return ----
        loc = full_panel.index.get_loc(ts)
        if loc == 0:
            continue
        prev_d = full_panel.index[loc - 1]
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
            elif pd.notna(yest) and yest > 0 and pd.isna(today):
                port_r += w * (-0.10)
                delisted_w += w
                del cur_w[asset]
        if delisted_w > 0:
            cur_w[cur_safe] = cur_w.get(cur_safe, 0.0) + delisted_w
        daily_rets.loc[ts] += port_r

        # ---- intramonth stop check (after today's return; exit from t+1) ----
        if kind is not None and cur_stocks:
            for stk in list(cur_stocks):
                if stk in stopped_out or stk not in stop_level or stk not in entry_ref:
                    continue
                px = full_panel.loc[ts, stk] if stk in full_panel.columns else np.nan
                if pd.isna(px):
                    continue
                cum_ret = px / entry_ref[stk] - 1.0
                if cum_ret < stop_level[stk]:
                    slot_w = cur_w.pop(stk, 0.0)
                    cur_w[cur_safe] = cur_w.get(cur_safe, 0.0) + slot_w
                    total_turnover += 2.0 * slot_w
                    daily_rets.loc[ts] -= 2.0 * slot_w * cost_bps / 10000.0
                    stopped_out.add(stk)
                    n_stops += 1
                    pending_whipsaw.append((stk, float(px), cur_end_apply))

    # ---- whipsaw evaluation: did stopped stock rebound above exit price by
    # the next rebalance (end_apply) close? ----
    for stk, exit_px, end_apply in pending_whipsaw:
        whipsaw_total += 1
        if end_apply is None or stk not in ndx_panel.columns:
            continue
        ser = ndx_panel[stk].loc[:end_apply].dropna()
        if ser.empty:
            continue
        end_px = float(ser.iloc[-1])
        if end_px > exit_px:
            whipsaw_hits += 1

    yrs = (idx[-1] - idx[0]).days / 365.25
    stats = {
        "ann_turnover": total_turnover / yrs if yrs > 0 else float("nan"),
        "n_stops": n_stops,
        "stops_per_yr": n_stops / yrs if yrs > 0 else float("nan"),
        "whipsaw_pct": 100.0 * whipsaw_hits / whipsaw_total if whipsaw_total else float("nan"),
        "whipsaw_n": whipsaw_total,
    }
    return daily_rets, stats


# ---------------- metrics helpers ----------------

def _sortino(x):
    x = np.asarray(x, float)
    neg = np.minimum(x, 0.0)
    dd = np.sqrt(np.mean(neg ** 2))
    return (x.mean() * 252.0) / (dd * np.sqrt(252.0)) if dd > 0 else float("nan")


def _cvar_ratio(x, q=0.05):
    x = np.asarray(x, float)
    n = x.size
    if n == 0:
        return float("nan")
    kk = max(1, int(np.floor(q * n)))
    worst = np.sort(x)[:kk]
    es = worst.mean()
    return (x.mean() * 252.0) / abs(es) if es < 0 else float("nan")


def full_metrics(ret):
    m = perf_metrics(ret)
    out = {
        "sharpe": m.get("sharpe"), "sortino": _sortino(ret.values),
        "cvar": _cvar_ratio(ret.values), "cagr": m.get("cagr"),
        "vol": m.get("vol"), "maxdd": m.get("max_drawdown"),
        "calmar": m.get("calmar"), "martin": m.get("martin"),
    }
    return out
