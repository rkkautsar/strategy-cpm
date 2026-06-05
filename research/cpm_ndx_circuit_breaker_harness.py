"""SLEEVE-LEVEL (whole-basket) DAILY-OVERLAY circuit breakers on the NDX sleeve.

This is the correct shape for the NDX failure mode: the ~-31% MaxDD is a
SLEEVE-WIDE, multi-week, cross-rebalance momentum unwind (Feb 12 -> Mar 29 2021
growth de-rate), NOT an idiosyncratic single-name intramonth crash. The prior
per-STOCK intramonth stop (research/cpm_ndx_stoploss_*) structurally could not
catch it (reference resets monthly, single-name risk already capped ~4%). Here
the trigger is evaluated on the WHOLE risky basket and rotates the ENTIRE sleeve
to safe (long-only de-risk; no shorting) for the remainder of the month.

MECHANISM
  - Keep PROD selection: 13612U momentum top-5 EW, gating, best-of-safe, T+1 MOO.
  - Walk DAILY through each holding month. Evaluate a SLEEVE-LEVEL breaker on
    lagged daily data (decision at close t, fill from t+1 -- prod T+1 convention).
  - On trigger, rotate ALL risky stock weight -> period best-of-safe for the rest
    of the month. NO intramonth re-entry; re-enter at the next monthly rebalance.
  - 10bps/side on the de-risk rotation (sell stocks + buy safe = 2 sides).

BREAKER FAMILIES
  - voltarget : MONTHLY dial reference (not daily). Scale risky exposure at
    rebalance by clip(target/realized_basket_vol, 0, 1). Replicates the prior
    vol-target DERISK config on THIS dataset for apples-to-apples comparison.
  - volbrk    : ADAPTIVE vol-breakdown. De-risk when trailing SHORT-window basket
    realized vol breaches k * LONG-window vol (or an absolute annualized level).
  - trend     : ADAPTIVE trend. De-risk when QQQ (or the basket) closes below a
    fast moving average (MA20 / MA50) intramonth.
  - traildd   : FIXED-% trailing drawdown (completeness). De-risk when the basket
    drops X% from its trailing INTRAMONTH peak.

EXECUTION / FILL
  Conservative. Signal computed at CLOSE t from data through t (no intraday /
  look-ahead). Sleeve rotated to safe from t+1 close-to-close. The trigger-day
  move + next-day gap are borne by the sleeve. A fill-at-level model would be
  strictly more favourable to the breaker.

CAVEATS (stated up front; see findings .md):
  - Daily panel data/ndx_constituents/prices.parquet is auto-adjusted Close only.
    No intraday => T+1 close is the conservative proxy.
  - PIT NDX membership via index_constitution (>=2006); pre-2006 SPY proxy, so
    pre-2006 per-crisis (dot-com) is CONTEXT only.
  - Path-dependent design (k / level / MA / X / window DoF) -> high overfit risk;
    sensible a-priori defaults + sensitivity, single in-sample, bootstrap + WF.
  - PROD and EVERY breaker variant run on the IDENTICAL dataset (apples-to-apples
    directional comparison), per scope relaxation.
"""
from __future__ import annotations
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "/Users/rkautsar/personal/scripts/strategy_cpm")

from cpm_live import perf_metrics
from ndx_sleeve_live import (
    compute_ndx_weights, SAFE_POOL, CASH_TICKER, COST_BPS_PER_SIDE, _pick_safe,
)

# reuse the monthly-history builder verbatim
from research.cpm_ndx_stoploss_harness import get_monthly_history, full_metrics


# ----------------------------- signal precompute -----------------------------
def basket_ret_series(ndx_panel, stocks):
    """EW daily return series of `stocks` over the full panel (ffilled)."""
    if not stocks:
        return pd.Series(dtype=float)
    px = ndx_panel[stocks].ffill()
    return px.pct_change().mean(axis=1)


def annualized_rollvol(ret, window):
    return ret.rolling(window).std() * np.sqrt(252.0)


def ma_series(px, window):
    return px.rolling(window).mean()


# ------------------------------- main runner -------------------------------
def run_with_breaker(history, full_panel, ndx_panel, cpm_panel, start, end,
                     kind=None, params=None, cost_bps=COST_BPS_PER_SIDE):
    """Run NDX sleeve with a SLEEVE-LEVEL daily circuit breaker.

    kind=None  -> PROD reference (no breaker).
    kind='voltarget' -> monthly exposure dial (no daily path).
    kind in {'volbrk','trend','traildd'} -> daily sleeve-level breaker.

    params (dict) keys by kind:
      voltarget: target, vol_window
      volbrk:    short, long, k, abs_level (use ratio if k set else abs_level)
      trend:     ma   (QQQ closes below MA(ma))
      traildd:   x    (fractional drawdown, e.g. 0.15)

    Returns (daily_rets, stats).
    """
    params = params or {}
    idx = full_panel.loc[start:end].index
    daily_rets = pd.Series(0.0, index=idx)
    history_by_apply = {h["apply_from"]: h for h in history}
    apply_set = set(history_by_apply.keys())

    # global QQQ trend signals (lagged use inside loop)
    qqq_px = cpm_panel["QQQ"].reindex(full_panel.index).ffill() if "QQQ" in cpm_panel.columns else None
    qqq_ma = None
    if kind == "trend" and qqq_px is not None:
        qqq_ma = ma_series(qqq_px, params["ma"])

    cur_w = {CASH_TICKER: 1.0}
    cur_stocks = []
    cur_safe = CASH_TICKER
    derisked = False
    # period basket bookkeeping
    basket_rv_short = basket_rv_long = None      # pd.Series indexed by date
    basket_idx_val = 1.0                          # intramonth basket index
    basket_peak = 1.0
    exit_basket_val = None
    cur_end_apply = None

    total_turnover = 0.0
    n_trig = 0
    whip_hits = 0
    whip_total = 0
    pending_whip = []   # (exit_val, end_apply, period_basket_end_val_ref)
    period_records = [] # to evaluate whipsaw at end: (exit_val, end_val)

    # for whipsaw we need basket index value at end_apply for the period in which
    # the trigger fired -> track via a per-period basket index series
    period_basket_end = {}

    for ts in idx:
        # ---------------- monthly rebalance ----------------
        if ts in apply_set:
            h = history_by_apply[ts]
            new_w = dict(h["target"])
            cur_stocks = list(h["stocks"])
            cur_safe = h["safe"]
            cur_end_apply = h["end_apply"]
            sig_d = h["sig_d"]

            # voltarget: scale risky exposure at rebalance (monthly dial)
            if kind == "voltarget" and cur_stocks:
                bret = basket_ret_series(ndx_panel, cur_stocks).loc[:sig_d].dropna()
                w = params.get("vol_window", 60)
                tail = bret.tail(w)
                if len(tail) >= max(10, w // 2):
                    rv = float(tail.std() * np.sqrt(252.0))
                    if rv > 0:
                        exp = float(np.clip(params.get("target", 0.30) / rv, 0.0, 1.0))
                        risky = {t: new_w.get(t, 0.0) for t in cur_stocks}
                        freed = sum(risky.values()) * (1.0 - exp)
                        for t in cur_stocks:
                            new_w[t] = new_w.get(t, 0.0) * exp
                        new_w[cur_safe] = new_w.get(cur_safe, 0.0) + freed

            tovr = sum(abs(cur_w.get(a, 0) - new_w.get(a, 0))
                       for a in set(cur_w) | set(new_w))
            total_turnover += tovr
            daily_rets.loc[ts] -= tovr * cost_bps / 10000.0
            cur_w = new_w

            # reset breaker state + precompute period signals
            derisked = False
            basket_idx_val = 1.0
            basket_peak = 1.0
            exit_basket_val = None
            if kind == "volbrk" and cur_stocks:
                bret_full = basket_ret_series(ndx_panel, cur_stocks).reindex(full_panel.index)
                basket_rv_short = annualized_rollvol(bret_full, params["short"])
                basket_rv_long = annualized_rollvol(bret_full, params["long"])

        # ---------------- today's portfolio return ----------------
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

        # ---------------- update intramonth basket index ----------------
        if kind in ("volbrk", "trend", "traildd") and cur_stocks and not derisked:
            # basket daily return today (EW of held stocks)
            br = 0.0
            cnt = 0
            for stk in cur_stocks:
                if stk in full_panel.columns:
                    t1 = full_panel.loc[ts, stk]
                    t0 = full_panel.loc[prev_d, stk]
                    if pd.notna(t1) and pd.notna(t0) and t0 > 0:
                        br += t1 / t0 - 1.0
                        cnt += 1
            if cnt:
                br /= cnt
                basket_idx_val *= (1.0 + br)
                basket_peak = max(basket_peak, basket_idx_val)

        # ---------------- sleeve-level breaker check (act t+1) ----------------
        if kind in ("volbrk", "trend", "traildd") and cur_stocks and not derisked:
            trig = False
            if kind == "volbrk":
                rs = basket_rv_short.get(ts, np.nan) if basket_rv_short is not None else np.nan
                rl = basket_rv_long.get(ts, np.nan) if basket_rv_long is not None else np.nan
                if params.get("k") is not None:
                    if np.isfinite(rs) and np.isfinite(rl) and rl > 0 and rs > params["k"] * rl:
                        trig = True
                elif params.get("abs_level") is not None:
                    if np.isfinite(rs) and rs > params["abs_level"]:
                        trig = True
            elif kind == "trend":
                if qqq_px is not None and qqq_ma is not None:
                    px_t = qqq_px.get(ts, np.nan)
                    ma_t = qqq_ma.get(ts, np.nan)
                    if np.isfinite(px_t) and np.isfinite(ma_t) and px_t < ma_t:
                        trig = True
            elif kind == "traildd":
                if basket_peak > 0:
                    dd = basket_idx_val / basket_peak - 1.0
                    if dd < -params["x"]:
                        trig = True

            if trig:
                risky_w = sum(cur_w.get(s, 0.0) for s in cur_stocks)
                for s in cur_stocks:
                    cur_w.pop(s, None)
                cur_w[cur_safe] = cur_w.get(cur_safe, 0.0) + risky_w
                total_turnover += 2.0 * risky_w
                daily_rets.loc[ts] -= 2.0 * risky_w * cost_bps / 10000.0
                derisked = True
                n_trig += 1
                exit_basket_val = basket_idx_val
                period_records.append([exit_basket_val, cur_end_apply, cur_stocks[:], 1.0])

    # ---------------- whipsaw evaluation ----------------
    # For each trigger, did the basket (held names) recover above exit value by
    # the period's next rebalance close?
    for rec in period_records:
        exit_val, end_apply, stocks, _ = rec
        whip_total += 1
        if end_apply is None or not stocks:
            continue
        # recompute basket index from period start to end_apply
        # (reconstruct: exit_val already relative to period start=1.0)
        # need basket value at end_apply relative to same start
        # find the period's apply_from from history_by_apply mapping end_apply
        # simpler: recompute basket index over the period using ndx_panel
        # locate period by end_apply
        per = None
        for h in history:
            if h["end_apply"] == end_apply and set(h["stocks"]) == set(stocks):
                per = h
                break
        if per is None:
            continue
        af = per["apply_from"]
        seg = ndx_panel[stocks].loc[af:end_apply].ffill()
        if seg.empty:
            continue
        rr = seg.pct_change().mean(axis=1).fillna(0.0)
        endval = float((1.0 + rr).prod())
        if endval > exit_val:
            whip_hits += 1

    yrs = (idx[-1] - idx[0]).days / 365.25
    stats = {
        "ann_turnover": total_turnover / yrs if yrs > 0 else float("nan"),
        "n_trig": n_trig,
        "trig_per_yr": n_trig / yrs if yrs > 0 else float("nan"),
        "whipsaw_pct": 100.0 * whip_hits / whip_total if whip_total else float("nan"),
        "whipsaw_n": whip_total,
    }
    return daily_rets, stats
