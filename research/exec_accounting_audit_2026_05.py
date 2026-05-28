"""
True MOO T+1 backtest. Splits T+1 day into:
  OLD weights * (open[T+1]/close[T_eom] - 1)         # overnight gap
  NEW weights * (close[T+1]/open[T+1] - 1)           # T+1 intraday
NEW weights compound close-to-close from T+2 onward.

Compares to BUGGY (close-to-close on T+1 all to NEW) and FIXED (=MOC T+1,
all of T+1 day to OLD; NEW from T+2 close-to-close).
"""
import sys, socket, os
socket.setdefaulttimeout(60)
sys.path.insert(0, "/Users/rkautsar/personal/scripts/strategy_cpm")

import pandas as pd
import numpy as np
from itertools import combinations
import yfinance as yf
from cpm_live import load_panel, perf_metrics, sig_13612U

CLEAN7_UNIVERSE = ["SPY", "EFA", "EEM", "VNQ", "GLD", "TLT", "DBC"]
SAFE_POOL = ["SHV", "IEF"]
CANARY = ["TIP"]
ALL_TICKERS = CLEAN7_UNIVERSE + SAFE_POOL + CANARY
DEFAULT_CASH = "SHV"

OPEN_CACHE = "/tmp/cpm_open_prices_yf.csv"
CLOSE_CACHE = "/tmp/cpm_close_prices_yf.csv"


def fetch_open_close(start="2006-01-01", end="2026-05-31"):
    """Fetch BOTH Open and Close from yfinance with consistent adjustment basis.
    Critical: opens and closes must come from the same adjustment scheme. Mixing
    yfinance opens with our stitched panel closes gives 4-15x scale mismatches
    on split days, which explodes overnight returns.
    """
    if os.path.exists(OPEN_CACHE) and os.path.exists(CLOSE_CACHE):
        opens = pd.read_csv(OPEN_CACHE, index_col=0, parse_dates=True)
        closes = pd.read_csv(CLOSE_CACHE, index_col=0, parse_dates=True)
        if all(t in opens.columns for t in ALL_TICKERS) and all(t in closes.columns for t in ALL_TICKERS):
            print(f"Loaded cached opens+closes (yfinance)")
            return opens[ALL_TICKERS], closes[ALL_TICKERS]
    print(f"Downloading Open+Close via yfinance for {len(ALL_TICKERS)} tickers...")
    data = yf.download(
        ALL_TICKERS, start=start, end=end,
        auto_adjust=True, progress=False, threads=True,
    )
    opens = data["Open"][ALL_TICKERS]
    closes = data["Close"][ALL_TICKERS]
    opens.to_csv(OPEN_CACHE)
    closes.to_csv(CLOSE_CACHE)
    print(f"Saved cache: opens+closes")
    return opens, closes


def pick_safe_haa(monthly, sig_d):
    sub = monthly.loc[:sig_d]
    scores = {t: sig_13612U(sub[t]) if t in sub.columns else -999.0 for t in ["IEF", "SHV"]}
    return max(scores, key=scores.get)


def compute_weights(close, daily_rets_full, sig_d, prev_pair, prev_state):
    mon_full = close.loc[:sig_d].resample("ME").last()
    tip_mom = sig_13612U(mon_full["TIP"]) if "TIP" in mon_full.columns else -999.0
    canary_ok = bool(pd.notna(tip_mom) and tip_mom > 0)
    risk_state = "ON" if canary_ok else "OFF"
    if prev_state is not None and prev_pair is not None and risk_state != prev_state:
        prev_pair = None
    safe = pick_safe_haa(mon_full, sig_d)
    if not canary_ok:
        return {safe: 1.0}, None, risk_state
    daily_rets_lookback = daily_rets_full.loc[:sig_d].tail(260)
    ew_ret = daily_rets_lookback[CLEAN7_UNIVERSE].mean(axis=1)
    scores, candidates = {}, []
    for t in CLEAN7_UNIVERSE:
        if t in mon_full.columns and len(mon_full[t]) >= 10:
            sma10 = mon_full[t].rolling(10).mean().iloc[-1]
            f_score = (mon_full[t].iloc[-1] - sma10) / sma10
            if pd.notna(f_score) and f_score > 0:
                corr = daily_rets_lookback[t].corr(ew_ret)
                if pd.isna(corr): corr = 0.0
                scores[t] = f_score * (1.0 - corr)
                candidates.append(t)
    top_k = sorted(candidates, key=lambda x: scores[x], reverse=True)[:4]
    if not top_k:
        return {safe: 1.0}, None, risk_state
    if len(top_k) == 1:
        return {top_k[0]: 0.5, safe: 0.5}, None, risk_state
    cov_matrix = daily_rets_full.loc[:sig_d].tail(504)[top_k].cov() * 252
    best_pair, min_var = None, 1e9
    for p in combinations(top_k, 2):
        var = 0.25 * cov_matrix.loc[p[0], p[0]] + 0.25 * cov_matrix.loc[p[1], p[1]] + 0.5 * cov_matrix.loc[p[0], p[1]]
        if var < min_var:
            min_var, best_pair = var, p
    return {best_pair[0]: 0.5, best_pair[1]: 0.5}, best_pair, risk_state


def run_moo_true(opens_yf, closes_yf, start, end, cost_bps=10.0):
    """True MOO T+1 using yfinance opens+closes (consistent adjustment basis)."""
    cols = ALL_TICKERS
    close = closes_yf[cols].ffill()
    panel = closes_yf  # alias
    opens_aligned = opens_yf[cols].reindex(close.index).ffill()
    daily_rets_full = close.pct_change()

    # Per-day overnight return: open[t]/close[t-1] - 1 (both from yfinance, same basis)
    overnight_ret = opens_aligned / close.shift(1) - 1.0
    # Per-day intraday return: close[t]/open[t] - 1
    intraday_ret = close / opens_aligned - 1.0
    # Sanity: overnight + intraday + cross = full daily close-to-close
    # (1+overnight)*(1+intraday) - 1 = close[t]/close[t-1] - 1; this is exact

    monthly_idx = pd.DataFrame({"x": 1}, index=close.index).groupby(pd.Grouper(freq="ME")).tail(1)
    signal_dates = monthly_idx.index[(monthly_idx.index >= start) & (monthly_idx.index <= end)].tolist()

    weights_history = []
    prev_pair, prev_state = None, None
    for sig_d in signal_dates:
        w, new_pair, risk_state = compute_weights(close, daily_rets_full, sig_d, prev_pair, prev_state)
        weights_history.append((sig_d, w, risk_state))
        prev_pair, prev_state = new_pair, risk_state

    common = panel.index[(panel.index >= start) & (panel.index <= end)]
    port = pd.Series(0.0, index=common)
    rebalance_days = set()

    for i, (sig_d, w, _risk) in enumerate(weights_history):
        future = common[common > sig_d]
        if len(future) < 1:
            continue
        t1 = future[0]  # T+1 trading day (MOO trade day)
        rebalance_days.add(t1)

        if i + 1 < len(weights_history):
            next_sig = weights_history[i + 1][0]
            next_future = common[common > next_sig]
            t1_next = next_future[0] if len(next_future) >= 1 else common[-1] + pd.Timedelta(days=1)
        else:
            t1_next = end + pd.Timedelta(days=1)

        # NEW weights compound close-to-close from t1+1 trading day onward
        post_mask = (common > t1) & (common < t1_next)
        for t_asset, weight in w.items():
            if t_asset in daily_rets_full.columns:
                port.loc[post_mask] += daily_rets_full[t_asset].reindex(common).fillna(0.0).loc[post_mask] * weight

        # NEW weights also earn T+1 intraday (open->close)
        if t1 in intraday_ret.index:
            for t_asset, weight in w.items():
                if t_asset in intraday_ret.columns:
                    v = intraday_ret.at[t1, t_asset]
                    if pd.notna(v):
                        port.at[t1] += v * weight

        # OLD weights earn T+1 overnight (close[T_eom] -> open[t1])
        if i > 0:
            prev_w = weights_history[i - 1][1]
            if t1 in overnight_ret.index:
                for t_asset, weight in prev_w.items():
                    if t_asset in overnight_ret.columns:
                        v = overnight_ret.at[t1, t_asset]
                        if pd.notna(v):
                            port.at[t1] += v * weight
        # i == 0: no prior weights, so overnight = 0 (cash). Tiny edge effect on day 1 only.

    # Costs: charge full turnover on the trade day t1
    for i in range(len(weights_history)):
        prev_w = weights_history[i - 1][1] if i > 0 else {}
        curr_w = weights_history[i][1]
        keys = set(curr_w) | set(prev_w)
        turnover = sum(abs(curr_w.get(k, 0.0) - prev_w.get(k, 0.0)) for k in keys)
        cost = turnover * cost_bps / 10000.0
        future = common[common > weights_history[i][0]]
        if len(future) >= 1:
            t1 = future[0]
            if t1 in port.index:
                port.at[t1] -= cost

    return port


def run_close_to_close(closes_yf, start, end, mode, cost_bps=10.0):
    """BUGGY (offset=1) and FIXED=MOC T+1 (offset=2) on yfinance closes."""
    cols = ALL_TICKERS
    close = closes_yf[cols].ffill()
    panel = closes_yf  # alias so common = panel.index... works
    daily_rets_full = close.pct_change()
    monthly_idx = pd.DataFrame({"x": 1}, index=close.index).groupby(pd.Grouper(freq="ME")).tail(1)
    signal_dates = monthly_idx.index[(monthly_idx.index >= start) & (monthly_idx.index <= end)].tolist()
    weights_history = []
    prev_pair, prev_state = None, None
    for sig_d in signal_dates:
        w, new_pair, risk_state = compute_weights(close, daily_rets_full, sig_d, prev_pair, prev_state)
        weights_history.append((sig_d, w, risk_state))
        prev_pair, prev_state = new_pair, risk_state
    common = panel.index[(panel.index >= start) & (panel.index <= end)]
    port = pd.Series(0.0, index=common)
    state_per_day = pd.Series("", index=common, dtype=object)
    offset = 1 if mode == "buggy" else 2
    for i, (sig_d, w, _risk) in enumerate(weights_history):
        future = common[common > sig_d]
        if len(future) < offset:
            continue
        apply_from = future[offset - 1]
        if i + 1 < len(weights_history):
            next_sig = weights_history[i + 1][0]
            next_future = common[common > next_sig]
            end_apply = next_future[offset - 1] if len(next_future) >= offset else common[-1] + pd.Timedelta(days=1)
        else:
            end_apply = end + pd.Timedelta(days=1)
        mask = (common >= apply_from) & (common < end_apply)
        for t, weight in w.items():
            if t in daily_rets_full.columns:
                port.loc[mask] += daily_rets_full[t].reindex(common).fillna(0.0).loc[mask] * weight
        state_per_day.loc[mask] = "+".join(f"{t}:{weight:.2f}" for t, weight in w.items())
    if cost_bps > 0:
        label_arr = state_per_day.values
        if len(label_arr) > 1:
            flips = np.where(label_arr[1:] != label_arr[:-1])[0] + 1
            for f in flips:
                port.iloc[f] -= 2.0 * cost_bps / 10000.0
    return port


if __name__ == "__main__":
    start = pd.Timestamp("2008-04-30")
    end = pd.Timestamp("2026-05-22")
    opens_yf, closes_yf = fetch_open_close()
    print(f"yfinance closes shape: {closes_yf.shape} | range {closes_yf.index.min().date()} to {closes_yf.index.max().date()}")

    # Sanity check: overnight return distribution should be sane (median |ret| < 1%)
    sanity = (opens_yf / closes_yf.shift(1) - 1.0).abs().median()
    print("Overnight |ret| median per ticker:")
    for t in ALL_TICKERS:
        print(f"  {t}: {sanity[t]*100:.3f}%")

    print("Running BUGGY (close-to-close T+1 all to NEW)...")
    p_buggy = run_close_to_close(closes_yf, start, end, mode="buggy"); m_buggy = perf_metrics(p_buggy)
    print("Running FIXED = MOC T+1 (close-to-close T+1 all to OLD)...")
    p_fixed = run_close_to_close(closes_yf, start, end, mode="fixed"); m_fixed = perf_metrics(p_fixed)
    print("Running TRUE MOO T+1 (split T+1: OLD overnight + NEW intraday)...")
    p_moo = run_moo_true(opens_yf, closes_yf, start, end); m_moo = perf_metrics(p_moo)

    print("\n" + "=" * 95)
    print("EXECUTION ACCOUNTING: BUGGY vs FIXED(MOC T+1) vs TRUE MOO T+1")
    print("(CLEAN-7, Faber*(1-corr), 504d cov, 10bps, no HB, 2008-04-30 to 2026-05-22)")
    print("=" * 95)
    print(f"{'Variant':<60} {'Sharpe':>8} {'CAGR':>8} {'Vol':>8} {'MaxDD':>8}")
    print("-" * 95)
    rows = [
        ("BUGGY  close[T+1]/close[T_eom] all to NEW (overnight bias)", m_buggy),
        ("FIXED  MOC T+1: full T+1 day to OLD, NEW from close[T+1]",   m_fixed),
        ("TRUE   MOO T+1: OLD = overnight gap; NEW = T+1 intraday on",  m_moo),
    ]
    for label, m in rows:
        print(f"{label:<60} {m['sharpe']:>8.3f} {m['cagr']*100:>7.2f}% "
              f"{m['vol']*100:>7.2f}% {m['max_drawdown']*100:>7.2f}%")
    print("-" * 95)
    print(f"{'Delta TRUE MOO - BUGGY':<60} "
          f"{m_moo['sharpe']-m_buggy['sharpe']:>+8.3f} "
          f"{(m_moo['cagr']-m_buggy['cagr'])*100:>+7.2f}%        "
          f"{(m_moo['max_drawdown']-m_buggy['max_drawdown'])*100:>+7.2f}%")
    print(f"{'Delta TRUE MOO - FIXED(MOC T+1)':<60} "
          f"{m_moo['sharpe']-m_fixed['sharpe']:>+8.3f} "
          f"{(m_moo['cagr']-m_fixed['cagr'])*100:>+7.2f}%        "
          f"{(m_moo['max_drawdown']-m_fixed['max_drawdown'])*100:>+7.2f}%")
    print("=" * 95)
    print("Critic's reproduction: Sharpe 0.90 | CAGR 9.12% | MaxDD -14.50%")
