# -*- coding: utf-8 -*-
"""
BULL daily intramonth trend-exit overlay (Faber daily 200d SMA convention).

Question: does a conventional daily 200-day SMA intramonth crash exit on the
BULL sleeve reduce the LIVE 3-sleeve 60/20/20 blend drawdown - and at what cost?

NO tuned percentage. Pure Faber daily SMA cross (SPY close < SPY 200d SMA).

Variants:
  V0  monthly-only (prod baseline)
  V1  daily 200d, NO intramonth re-entry, BULL only (NDX monthly as prod)
  V2  daily 200d, WITH intramonth re-entry (reclaim 200d), BULL only
  V3  daily 200d, NO re-entry, cascade exit to NDX intramonth
  V4  daily 200d, WITH re-entry, cascade exit to NDX intramonth
  V5  daily 210d (10-month SMA, secondary Faber signal), NO re-entry, BULL only

Execution: exit observed at close[d] -> position effective day d+1 (T+1), same
convention as the monthly gate. Safe leg = best-of-safe (SHV/IEF) at sig_d, same
as the monthly fallback.
"""
import sys
from pathlib import Path
import pandas as pd
import numpy as np

ROOT = Path('/Users/rkautsar/personal/scripts/strategy_cpm')
sys.path.insert(0, str(ROOT))

import cpm_live as cpm
from cpm_live import load_panel, run_cpm_backtest, perf_metrics
import bull_qqq_live as bull_mod
from bull_qqq_live import (
    run_bull_qqq_backtest, compute_bull_qqq_weights, _pick_safe,
    BULL_TICKER, COST_BPS_PER_SIDE,
)
from ndx_sleeve_live import run_ndx_backtest, load_ndx_panel

CPM_W, BULL_W, NDX_W = 0.60, 0.20, 0.20


def monthly_sig_dates(panel, start, end):
    midx = pd.DataFrame({"x": 1}, index=panel.index).groupby(pd.Grouper(freq="ME")).tail(1)
    return midx.index[(midx.index >= start) & (midx.index <= end)].tolist()


def build_bull_overlay(panel, start, end, sma_window, reentry, cost_bps=COST_BPS_PER_SIDE,
                       daily_overlay=True):
    """Reimplements run_bull_qqq_backtest with a daily SMA intramonth exit.

    Returns (daily_returns, exit_active_mask, events).
      exit_active_mask: bool Series, True on days the overlay is holding safe
                        instead of SPY *within a bull-active month* (for cascade).
      events: list of dicts describing each intramonth exit episode.
    """
    daily_rets = panel.ffill().pct_change()
    common = panel.index[(panel.index >= start) & (panel.index <= end)]
    sigs = monthly_sig_dates(panel, start, end)

    spy = panel[BULL_TICKER].ffill()
    sma = spy.rolling(sma_window).mean()

    # position weight series
    all_safe = set(["SHV", "IEF"])
    w_spy = pd.Series(0.0, index=common)
    w_safe = {s: pd.Series(0.0, index=common) for s in all_safe}
    label = pd.Series("", index=common, dtype=object)
    exit_active = pd.Series(False, index=common)
    events = []

    for i, sig_d in enumerate(sigs):
        mw, regime, diag = compute_bull_qqq_weights(panel, sig_d, panel[BULL_TICKER])
        monthly = panel.loc[:sig_d].resample("ME").last()
        safe = _pick_safe(monthly)

        future = common[common > sig_d]
        if len(future) < 1:
            continue
        apply_from = future[0]
        if i + 1 < len(sigs):
            nf = common[common > sigs[i + 1]]
            end_apply = nf[0] if len(nf) >= 1 else common[-1] + pd.Timedelta(days=1)
        else:
            end_apply = common[-1] + pd.Timedelta(days=1)
        period = common[(common >= apply_from) & (common < end_apply)]
        if len(period) == 0:
            continue

        bull_active = (BULL_TICKER in mw and mw[BULL_TICKER] > 0)
        if bull_active and not daily_overlay:
            # V0 path: hold SPY entire period, no intramonth check
            w_spy.loc[period] = 1.0
            label.loc[period] = f"{BULL_TICKER}:1.00"
            continue
        if not bull_active:
            # monthly defensive: hold the monthly safe leg, no overlay
            for s, wv in mw.items():
                if s in w_safe:
                    w_safe[s].loc[period] = wv
                else:
                    w_safe.setdefault(s, pd.Series(0.0, index=common)).loc[period] = wv
            label.loc[period] = "+".join(f"{t}:{v:.2f}" for t, v in sorted(mw.items()))
            continue

        # bull-active month: apply daily SMA overlay with T+1 execution.
        # initialize state from the close just before apply_from (= sig_d region)
        prev_idx = common[common < apply_from]
        if len(prev_idx) > 0 and pd.notna(sma.loc[prev_idx[-1]]):
            in_spy = bool(spy.loc[prev_idx[-1]] >= sma.loc[prev_idx[-1]])
        else:
            in_spy = True

        exited_this_month = False
        exit_day = None
        for d in period:
            if in_spy:
                w_spy.loc[d] = 1.0
                label.loc[d] = f"{BULL_TICKER}:1.00"
            else:
                w_safe[safe].loc[d] = 1.0 if safe in w_safe else 1.0
                w_safe.setdefault(safe, pd.Series(0.0, index=common)).loc[d] = 1.0
                label.loc[d] = f"{safe}:1.00"
                exit_active.loc[d] = True
            # update state from close[d] for next day
            s_d, m_d = spy.loc[d], sma.loc[d]
            if pd.isna(m_d):
                continue
            if in_spy and s_d < m_d:
                in_spy = False
                if not exited_this_month:
                    exited_this_month = True
                    exit_day = d
            elif (not in_spy) and reentry and s_d >= m_d:
                in_spy = True

        if exit_day is not None:
            # forward SPY return from exit execution day to period end
            exec_loc = common.get_loc(exit_day)
            exec_day = common[exec_loc + 1] if exec_loc + 1 < len(common) else exit_day
            p_end = period[-1]
            if exec_day <= p_end and exec_day in spy.index:
                fwd = float(spy.loc[p_end] / spy.loc[exec_day] - 1)
            else:
                fwd = 0.0
            events.append({"sig_d": sig_d, "exit_day": exit_day,
                           "fwd_spy_to_monthend": fwd})

    port = pd.Series(0.0, index=common)
    port = port + daily_rets[BULL_TICKER].reindex(common).fillna(0.0) * w_spy
    for s, ws in w_safe.items():
        if s in daily_rets.columns:
            port = port + daily_rets[s].reindex(common).fillna(0.0) * ws

    arr = label.values
    flip_idx = np.where(arr[1:] != arr[:-1])[0] + 1
    n_flips = len(flip_idx)
    if cost_bps > 0:
        for f in flip_idx:
            port.iloc[f] -= 2.0 * cost_bps / 10000.0

    return port, exit_active, events, n_flips


def apply_cascade_to_ndx(panel, ndx_panel, start, end, exit_active, cost_bps=COST_BPS_PER_SIDE):
    """Cascade the daily BULL exit to NDX: on exit-active days, NDX -> best-safe.

    Approximation: recompute the prod NDX series, then on exit-active days
    replace the NDX daily return with the best-safe (SHV/IEF) daily return,
    charging a round-trip cost at each cascade on/off transition.
    """
    ndx_base, _ = run_ndx_backtest(panel, ndx_panel, start, end)
    daily_rets = panel.ffill().pct_change()
    common = ndx_base.index
    ea = exit_active.reindex(common).fillna(False)

    # choose best-safe per day from the monthly gate (use SHV as conservative
    # default for the cascade safe leg; matches BULL overlay exit target mix)
    sigs = monthly_sig_dates(panel, start, end)
    safe_per_day = pd.Series("SHV", index=common, dtype=object)
    for i, sig_d in enumerate(sigs):
        monthly = panel.loc[:sig_d].resample("ME").last()
        safe = _pick_safe(monthly)
        future = common[common > sig_d]
        if len(future) < 1:
            continue
        af = future[0]
        if i + 1 < len(sigs):
            nf = common[common > sigs[i + 1]]
            ea_end = nf[0] if len(nf) >= 1 else common[-1] + pd.Timedelta(days=1)
        else:
            ea_end = common[-1] + pd.Timedelta(days=1)
        safe_per_day.loc[(common >= af) & (common < ea_end)] = safe

    out = ndx_base.copy()
    safe_ret = pd.Series(0.0, index=common)
    for s in ["SHV", "IEF"]:
        if s in daily_rets.columns:
            mask = (safe_per_day == s) & ea.values
            safe_ret.loc[mask] = daily_rets[s].reindex(common).fillna(0.0).loc[mask]
    out.loc[ea.values] = safe_ret.loc[ea.values]

    if cost_bps > 0:
        ea_arr = ea.values.astype(int)
        trans = np.where(ea_arr[1:] != ea_arr[:-1])[0] + 1
        for t in trans:
            out.iloc[t] -= 2.0 * cost_bps / 10000.0
    return out


def metrics_row(label, daily):
    common = daily.index
    cash = pd.Series(0.0, index=common)
    m = perf_metrics(daily, cash)
    return {
        "variant": label,
        "raw_sharpe": m["sharpe"],
        "excess_sharpe": m["excess_sharpe"],
        "cagr": m["cagr"],
        "vol": m["vol"],
        "maxdd": m["max_drawdown"],
        "calmar": m["calmar"],
    }


def window_maxdd(daily, w_start, w_end):
    sub = daily.loc[(daily.index >= w_start) & (daily.index <= w_end)]
    if len(sub) == 0:
        return float("nan"), float("nan")
    eq = (1 + sub).cumprod()
    dd = (eq / eq.cummax() - 1).min()
    ret = eq.iloc[-1] / eq.iloc[0] - 1
    return float(dd), float(ret)


def turnover_per_year(daily_label_flips, years):
    return daily_label_flips / years if years > 0 else float("nan")


if __name__ == "__main__":
    pass
