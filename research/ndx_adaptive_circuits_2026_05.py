"""
NDX adaptive intramonth canaries (no fixed % DD trigger).

All variants use honest t+1 MOO execution.

Adaptive trigger families:
  A. DD-in-vol-units (k-sigma drawdown):
     trigger when sleeve DD from rolling N-day peak < -K * sigma_N
     Adapts to regime: high-vol periods get wider threshold, low-vol periods tighter.

  B. DD-percentile (regime-relative):
     trigger when current DD is in worst P% of rolling lookback DDs
     E.g., trigger when DD < 5th percentile of past 252d sleeve DDs.

  C. Returns z-score (downside burst detection):
     trigger when (rolling 21d cumulative return) - mean / std < -K
     where mean/std use rolling 252d window.

  D. Vol expansion (GARCH-style alert):
     trigger when realized N-day vol > K * realized 252d vol (vol spike).
     Adapts: triggers when current vol jumps relative to recent history.

  E. Combined: DD-in-vol-units AND vol-expansion (both must fire).

Sanity gate: +1-day lag on top candidates.
"""
import sys, socket
socket.setdefaulttimeout(15)
sys.path.insert(0, "/Users/rkautsar/personal/scripts/strategy_cpm")

import pandas as pd
import numpy as np
from cpm_live import load_panel, perf_metrics
from ndx_sleeve_live import load_ndx_panel, run_ndx_backtest


def apply_t_plus_1(sleeve_returns, trigger, sig_dates):
    daily_idx = sleeve_returns.index
    trigger_d = trigger.reindex(daily_idx).fillna(False)
    sig_set = set(sig_dates)
    scale = pd.Series(1.0, index=daily_idx)
    state = 1.0
    trips = 0
    for i, day in enumerate(daily_idx):
        if day in sig_set:
            state = 1.0
        scale.iloc[i] = state
        if bool(trigger_d.iloc[i]):
            if state == 1.0:
                trips += 1
            state = 0.0
    return scale * sleeve_returns, scale, trips


def trigger_dd_vol_units(sleeve_returns, K, peak_window=63, vol_window=63):
    """A. DD-in-vol-units: trigger when DD from rolling peak < -K * annualized sigma."""
    eq = (1.0 + sleeve_returns).cumprod()
    rp = eq.rolling(peak_window, min_periods=1).max()
    dd = eq / rp - 1.0
    sigma_daily = sleeve_returns.rolling(vol_window).std()
    sigma_ann = sigma_daily * np.sqrt(252)
    # DD in units of annualized vol: e.g., if vol=25%, K=2 means DD < -50%
    # That's too loose. Use daily vol scaled by sqrt(window) for window-relative threshold.
    # Better interpretation: DD threshold = K * sigma_daily * sqrt(peak_window) (window-scaled vol).
    sigma_window = sigma_daily * np.sqrt(peak_window)
    threshold = -K * sigma_window
    return dd < threshold


def trigger_dd_percentile(sleeve_returns, P, peak_window=63, lookback=252):
    """B. DD-percentile: trigger when DD < Pth percentile of rolling DD history."""
    eq = (1.0 + sleeve_returns).cumprod()
    rp = eq.rolling(peak_window, min_periods=1).max()
    dd = eq / rp - 1.0
    pctile = dd.rolling(lookback).quantile(P / 100.0)
    return dd < pctile


def trigger_return_zscore(sleeve_returns, K, return_window=21, lookback=252):
    """C. Returns z-score: trigger when (rolling return) z-score vs lookback < -K."""
    rolling_ret = sleeve_returns.rolling(return_window).sum()
    mu = rolling_ret.rolling(lookback).mean()
    sd = rolling_ret.rolling(lookback).std()
    z = (rolling_ret - mu) / sd
    return z < -K


def trigger_vol_expansion(sleeve_returns, K, short_window=21, long_window=252):
    """D. Vol expansion: trigger when realized short-vol > K * realized long-vol."""
    short_vol = sleeve_returns.rolling(short_window).std()
    long_vol = sleeve_returns.rolling(long_window).std()
    return short_vol > K * long_vol


def trigger_drawdown_speed(sleeve_returns, K, peak_window=63, speed_window=10):
    """F. Drawdown speed: trigger when DD has dropped > K standard deviations in N days."""
    eq = (1.0 + sleeve_returns).cumprod()
    rp = eq.rolling(peak_window, min_periods=1).max()
    dd = eq / rp - 1.0
    dd_change = dd - dd.shift(speed_window)
    sigma_change = dd_change.rolling(252).std()
    return dd_change < -K * sigma_change


# === Crossover-family triggers (asset-price or sleeve-equity based) ===

def trigger_sma_crossover(series, fast, slow):
    """G. SMA crossover: trigger when fast SMA < slow SMA (downside cross)."""
    return series.rolling(fast).mean() < series.rolling(slow).mean()


def trigger_ema_crossover(series, fast, slow):
    """H. EMA crossover: trigger when fast EMA < slow EMA (downside cross)."""
    return series.ewm(span=fast, adjust=False).mean() < series.ewm(span=slow, adjust=False).mean()


# === 13612W variants ===

def trigger_13612W_daily(series, threshold=0.0):
    """I. Daily 13612W (Keller BAA weighted momentum) on a daily-compounded series.
    Weights 12/4/2/1 for 1mo/3mo/6mo/12mo returns (~22/64/127/253 trading days)."""
    r1 = series.pct_change(22)
    r3 = series.pct_change(64)
    r6 = series.pct_change(127)
    r12 = series.pct_change(253)
    score = (12 * r1 + 4 * r3 + 2 * r6 + r12) / 19
    return score < threshold


def trigger_13612U_daily(series, threshold=0.0):
    """J. Daily 13612U (Keller HAA unweighted) on a daily-compounded series."""
    r1 = series.pct_change(22)
    r3 = series.pct_change(64)
    r6 = series.pct_change(127)
    r12 = series.pct_change(253)
    score = (r1 + r3 + r6 + r12) / 4
    return score < threshold


def metrics_row(label, ret, trips):
    m = perf_metrics(ret)
    cal = m["cagr"] / abs(m["max_drawdown"]) if m["max_drawdown"] != 0 else float("nan")
    return (label, m["sharpe"], m["cagr"] * 100, m["vol"] * 100,
             m["max_drawdown"] * 100, trips, cal)


def print_table(rows, title):
    print("\n" + "=" * 115)
    print(title)
    print("=" * 115)
    print(f"{'Variant':<60} {'Sharpe':>7} {'CAGR':>7} {'Vol':>7} {'MaxDD':>9} {'Trips':>6} {'Calmar':>7}")
    print("-" * 115)
    for r in rows:
        if r[0] == "---":
            print("-" * 115); continue
        print(f"{r[0]:<60} {r[1]:>7.3f} {r[2]:>6.2f}% {r[3]:>6.2f}% {r[4]:>8.2f}% {r[5]:>6d} {r[6]:>7.2f}")
    print("=" * 115)


if __name__ == "__main__":
    panel = load_panel(start=pd.Timestamp("1993-01-01"))
    ndx_panel = load_ndx_panel()
    start, end = pd.Timestamp("2008-04-30"), pd.Timestamp("2026-05-22")
    ndx_raw, _ = run_ndx_backtest(panel, ndx_panel, start, end)
    common = ndx_raw.index[(ndx_raw.index >= start) & (ndx_raw.index <= end)]
    ndx_raw = ndx_raw.reindex(common).fillna(0.0)
    sigs = (pd.DataFrame({"x": 1}, index=common).groupby(pd.Grouper(freq="ME")).tail(1).index.tolist())

    rows = []
    rows.append(metrics_row("NDX raw (no circuit, reference)", ndx_raw, 0))
    # Current fixed -10%/63d benchmark
    from vol_cap import compute_dd_circuit_scale, DD_CIRCUIT_SCALE
    curr_scale = compute_dd_circuit_scale(ndx_raw, sigs, -0.10, DD_CIRCUIT_SCALE)
    rows.append(metrics_row("[FIXED] DD -10%/63d (current production)", curr_scale * ndx_raw,
                              int((curr_scale.diff() < 0).sum())))
    # Better fixed -12.5%/63d for reference
    fix125 = compute_dd_circuit_scale(ndx_raw, sigs, -0.125, DD_CIRCUIT_SCALE)
    rows.append(metrics_row("[FIXED] DD -12.5%/63d (proposed)", fix125 * ndx_raw,
                              int((fix125.diff() < 0).sum())))
    rows.append(("---", 0, 0, 0, 0, 0, 0))

    # A. DD-in-vol-units sweep
    for K in [1.0, 1.25, 1.5, 1.75, 2.0, 2.5]:
        trig = trigger_dd_vol_units(ndx_raw, K, peak_window=63, vol_window=63)
        out, _, trips = apply_t_plus_1(ndx_raw, trig, sigs)
        rows.append(metrics_row(f"[A] DD < -{K:.2f}sigma * sqrt(63), 63d peak (vol_units)", out, trips))
    rows.append(("---", 0, 0, 0, 0, 0, 0))

    # B. DD-percentile sweep
    for P in [1, 2.5, 5, 10]:
        trig = trigger_dd_percentile(ndx_raw, P, peak_window=63, lookback=252)
        out, _, trips = apply_t_plus_1(ndx_raw, trig, sigs)
        rows.append(metrics_row(f"[B] DD < {P}th-pctile of 252d DDs, 63d peak", out, trips))
    rows.append(("---", 0, 0, 0, 0, 0, 0))

    # C. Returns z-score sweep
    for K in [1.5, 2.0, 2.5, 3.0]:
        trig = trigger_return_zscore(ndx_raw, K, return_window=21, lookback=252)
        out, _, trips = apply_t_plus_1(ndx_raw, trig, sigs)
        rows.append(metrics_row(f"[C] 21d-return z-score < -{K:.1f} vs 252d", out, trips))
    rows.append(("---", 0, 0, 0, 0, 0, 0))

    # D. Vol expansion sweep
    for K in [1.25, 1.5, 1.75, 2.0]:
        trig = trigger_vol_expansion(ndx_raw, K, short_window=21, long_window=252)
        out, _, trips = apply_t_plus_1(ndx_raw, trig, sigs)
        rows.append(metrics_row(f"[D] 21d vol > {K:.2f}x 252d vol (vol_expansion)", out, trips))
    rows.append(("---", 0, 0, 0, 0, 0, 0))

    # F. Drawdown speed
    for K in [1.5, 2.0, 2.5, 3.0]:
        trig = trigger_drawdown_speed(ndx_raw, K, peak_window=63, speed_window=10)
        out, _, trips = apply_t_plus_1(ndx_raw, trig, sigs)
        rows.append(metrics_row(f"[F] 10d DD-change z-score < -{K:.1f}", out, trips))
    rows.append(("---", 0, 0, 0, 0, 0, 0))

    # E. Combos: DD-vol-units AND vol-expansion
    for K_dd, K_vol in [(1.5, 1.5), (1.5, 1.25), (2.0, 1.5), (1.75, 1.5)]:
        t_dd = trigger_dd_vol_units(ndx_raw, K_dd, 63, 63)
        t_ve = trigger_vol_expansion(ndx_raw, K_vol, 21, 252)
        combo = t_dd & t_ve
        out, _, trips = apply_t_plus_1(ndx_raw, combo, sigs)
        rows.append(metrics_row(f"[E] [A K={K_dd}] AND [D K={K_vol}]", out, trips))
    rows.append(("---", 0, 0, 0, 0, 0, 0))

    # G. SMA crossovers on QQQ
    qqq_close = panel["QQQ"].ffill().reindex(common).ffill()
    sleeve_eq = (1.0 + ndx_raw).cumprod()
    for fast, slow in [(10, 20), (10, 50), (20, 50), (20, 100), (50, 200)]:
        # QQQ-based
        trig_qqq = trigger_sma_crossover(qqq_close, fast, slow)
        out, _, trips = apply_t_plus_1(ndx_raw, trig_qqq, sigs)
        rows.append(metrics_row(f"[G-QQQ] SMA{fast} < SMA{slow}", out, trips))
        # Sleeve-equity based
        trig_eq = trigger_sma_crossover(sleeve_eq, fast, slow)
        out, _, trips = apply_t_plus_1(ndx_raw, trig_eq, sigs)
        rows.append(metrics_row(f"[G-NDX] SMA{fast} < SMA{slow} on sleeve eq", out, trips))
    rows.append(("---", 0, 0, 0, 0, 0, 0))

    # H. EMA crossovers
    for fast, slow in [(12, 26), (20, 50), (20, 100), (50, 200)]:
        trig_qqq = trigger_ema_crossover(qqq_close, fast, slow)
        out, _, trips = apply_t_plus_1(ndx_raw, trig_qqq, sigs)
        rows.append(metrics_row(f"[H-QQQ] EMA{fast} < EMA{slow} (MACD-like)", out, trips))
        trig_eq = trigger_ema_crossover(sleeve_eq, fast, slow)
        out, _, trips = apply_t_plus_1(ndx_raw, trig_eq, sigs)
        rows.append(metrics_row(f"[H-NDX] EMA{fast} < EMA{slow} on sleeve eq", out, trips))
    rows.append(("---", 0, 0, 0, 0, 0, 0))

    # I. 13612W daily on QQQ and on NDX sleeve equity
    for ser_label, ser in [("QQQ", qqq_close), ("NDX-sleeve", sleeve_eq)]:
        trig = trigger_13612W_daily(ser, threshold=0.0)
        out, _, trips = apply_t_plus_1(ndx_raw, trig, sigs)
        rows.append(metrics_row(f"[I] 13612W daily on {ser_label} < 0 (BAA-fast)", out, trips))

    # J. 13612U daily on QQQ and on NDX sleeve
    for ser_label, ser in [("QQQ", qqq_close), ("NDX-sleeve", sleeve_eq)]:
        trig = trigger_13612U_daily(ser, threshold=0.0)
        out, _, trips = apply_t_plus_1(ndx_raw, trig, sigs)
        rows.append(metrics_row(f"[J] 13612U daily on {ser_label} < 0 (HAA-canonical)", out, trips))
    rows.append(("---", 0, 0, 0, 0, 0, 0))

    # K. Combos: best adaptive + 13612W or crossover
    for K_dd in [1.5, 2.0]:
        for partner_label, partner_trig in [
            ("13612W-QQQ<0", trigger_13612W_daily(qqq_close, 0.0)),
            ("13612W-NDXeq<0", trigger_13612W_daily(sleeve_eq, 0.0)),
            ("SMA50<SMA200 QQQ", trigger_sma_crossover(qqq_close, 50, 200)),
            ("EMA20<EMA50 QQQ", trigger_ema_crossover(qqq_close, 20, 50)),
        ]:
            t_dd = trigger_dd_vol_units(ndx_raw, K_dd, 63, 63)
            combo = t_dd & partner_trig
            out, _, trips = apply_t_plus_1(ndx_raw, combo, sigs)
            rows.append(metrics_row(f"[K] [A K={K_dd}] AND [{partner_label}]", out, trips))

    # Sort core results (excluding dividers)
    core_rows = [r for r in rows if r[0] != "---"]
    core_rows.sort(key=lambda r: -r[1])
    print_table(core_rows,
                 "NDX adaptive intramonth canary sweep (HONEST t+1 MOO, 2008-04 to 2026-05, 10bps)\nSorted by Sharpe. [FIXED] rows are anchors for comparison.")

    # SANITY GATE: top 5 with +1d extra lag
    print("\n--- SANITY GATE: top 5 with +1-day extra lag (delta > 0.10 = suspect) ---")
    top5_labels = [r[0] for r in core_rows[:8] if not r[0].startswith("[FIXED]") and r[0] != "NDX raw (no circuit, reference)"][:5]
    sanity_rows = []
    for label in top5_labels:
        # Re-derive the trigger and apply +1d lag
        if label.startswith("[A]"):
            import re
            m = re.search(r"-(\d+\.?\d*)sigma", label)
            K = float(m.group(1))
            trig = trigger_dd_vol_units(ndx_raw, K, 63, 63).shift(1).fillna(False)
        elif label.startswith("[B]"):
            m = re.search(r"(\d+\.?\d*)th-pctile", label)
            P = float(m.group(1))
            trig = trigger_dd_percentile(ndx_raw, P, 63, 252).shift(1).fillna(False)
        elif label.startswith("[C]"):
            m = re.search(r"< -(\d+\.?\d*)", label)
            K = float(m.group(1))
            trig = trigger_return_zscore(ndx_raw, K, 21, 252).shift(1).fillna(False)
        elif label.startswith("[D]"):
            m = re.search(r"> (\d+\.?\d*)x", label)
            K = float(m.group(1))
            trig = trigger_vol_expansion(ndx_raw, K, 21, 252).shift(1).fillna(False)
        elif label.startswith("[F]"):
            m = re.search(r"< -(\d+\.?\d*)", label)
            K = float(m.group(1))
            trig = trigger_drawdown_speed(ndx_raw, K, 63, 10).shift(1).fillna(False)
        elif label.startswith("[E]"):
            continue  # skip combos for brevity
        else:
            continue
        out, _, trips = apply_t_plus_1(ndx_raw, trig, sigs)
        sanity_rows.append(metrics_row(f"  +1d lag: {label}", out, trips))
    print_table(sanity_rows, "Top candidates with +1d extra lag")
