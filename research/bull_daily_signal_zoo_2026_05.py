"""
BULL-ext daily intramonth canary: test standard fast-momentum signal zoo.

Each signal evaluates SPY's price series up to and including day t. Returns
True = "trigger defensive". Strategy latches defensive until next monthly
signal date (same convention as DD circuit and 13612W daily canary).

Tested:
  Baseline:
    M1.  No intramonth defense
    M2.  Sleeve-equity DD-10% / 63d (current live)

  Momentum / regression-style:
    13612W   Daily 13612W < 0 (Keller BAA weighted, prior winner)
    13612U   Daily 13612U < 0 (Keller HAA unweighted)
    ROC20    20-day ROC < 0 (simple 1-month return)
    ROC60    60-day ROC < 0 (simple 3-month return)
    ROC252   252-day ROC < 0 (Antonacci GEM 1-year, daily-evaluated)

  Moving average crossovers / SMA filters:
    SMA200   SPY < SMA200 (Faber classic, daily-evaluated)
    SMA50    SPY < SMA50
    Faber10m SPY < 10mo SMA daily (Faber TAA rule, daily eval)
    SMA50x200 SMA50 < SMA200 (golden cross / death cross)

  EMA crossovers:
    EMA20x50  EMA20 < EMA50
    MACD      EMA12 < EMA26 (MACD zero line)

  Channel / breakdown:
    DCH20    SPY < 20-day rolling low (Donchian breakdown)
    DCH60    SPY < 60-day rolling low

Window 2008-04-30 to 2026-05-22, 10bps.
"""
import sys, socket
socket.setdefaulttimeout(15)
sys.path.insert(0, "/Users/rkautsar/personal/scripts/strategy_cpm")

import pandas as pd
import numpy as np
from cpm_live import load_panel, perf_metrics
from bull_qqq_live import run_bull_qqq_backtest
from vol_cap import compute_dd_circuit_scale, DD_CIRCUIT_THRESHOLD, DD_CIRCUIT_SCALE


def make_signals(spy_close):
    """Pre-compute all daily indicator series. Returns dict label -> pd.Series of bool
    where True means 'trigger defensive'."""
    sig = {}
    sig["ROC20"] = (spy_close.pct_change(20) < 0)
    sig["ROC60"] = (spy_close.pct_change(60) < 0)
    sig["ROC252"] = (spy_close.pct_change(252) < 0)
    sig["SMA200"] = (spy_close < spy_close.rolling(200).mean())
    sig["SMA50"] = (spy_close < spy_close.rolling(50).mean())
    sig["Faber10m"] = (spy_close < spy_close.rolling(210).mean())  # ~10 months
    sig["SMA50x200"] = (spy_close.rolling(50).mean() < spy_close.rolling(200).mean())
    sig["EMA20x50"] = (spy_close.ewm(span=20, adjust=False).mean()
                       < spy_close.ewm(span=50, adjust=False).mean())
    sig["MACD"] = (spy_close.ewm(span=12, adjust=False).mean()
                   < spy_close.ewm(span=26, adjust=False).mean())
    sig["DCH20"] = (spy_close <= spy_close.rolling(20).min())
    sig["DCH60"] = (spy_close <= spy_close.rolling(60).min())

    # 13612 daily variants (compute using shift indexing to avoid python loop)
    r1 = spy_close.pct_change(22)
    r3 = spy_close.pct_change(64)
    r6 = spy_close.pct_change(127)
    r12 = spy_close.pct_change(253)
    sig["13612U"] = ((r1 + r3 + r6 + r12) / 4 < 0)
    sig["13612W"] = ((12 * r1 + 4 * r3 + 2 * r6 + r12) / 19 < 0)
    return sig


def determine_sleeve_state(panel, start, end):
    """T/F daily series for 'BULL holds SPY' (vs safe)."""
    from cpm_live import sig_13612U, best_safe
    sigs = (pd.DataFrame({"x": 1}, index=panel.loc[start:end].index)
            .groupby(pd.Grouper(freq="ME")).tail(1).index)
    sigs = sigs[(sigs >= start) & (sigs <= end)]
    state_per_sig = {}
    for sd in sigs:
        monthly = panel.loc[:sd].resample("ME").last()
        hygm = sig_13612U(monthly["HYG_stitched"]) if "HYG_stitched" in monthly.columns else -999.0
        tipm = sig_13612U(monthly["TIP"]) if "TIP" in monthly.columns else -999.0
        c_ok = (pd.notna(hygm) and hygm > 0) or (pd.notna(tipm) and tipm > 0)
        spym = sig_13612U(monthly["SPY"])
        a_ok = pd.notna(spym) and spym > 0
        state_per_sig[sd] = c_ok and a_ok
    daily_idx = panel.loc[start:end].index
    out = pd.Series(False, index=daily_idx)
    cur = False
    sig_list = sorted(state_per_sig.keys())
    for i, d in enumerate(daily_idx):
        for sd in sig_list:
            if sd < d:
                cur = state_per_sig[sd]
        out.iloc[i] = cur
    return out, list(sigs)


def apply_daily_signal_circuit(returns, holding_spy, sigs, trigger_series):
    """Apply latching daily circuit: scale to 0 when trigger fires while holding SPY,
    reset to 1 at each monthly signal date."""
    daily_idx = returns.index
    trigger = trigger_series.reindex(daily_idx).fillna(False)
    sig_set = set(sigs)
    scale = pd.Series(1.0, index=daily_idx)
    state = 1.0
    trips = 0
    for i, d in enumerate(daily_idx):
        if d in sig_set:
            state = 1.0
        else:
            if holding_spy.iloc[i] and state == 1.0 and bool(trigger.iloc[i]):
                state = 0.0
                trips += 1
        scale.iloc[i] = state
    return scale * returns, trips


if __name__ == "__main__":
    panel = load_panel(start=pd.Timestamp("1993-01-01"))
    start = pd.Timestamp("2008-04-30")
    end = pd.Timestamp("2026-05-22")

    bull_raw = run_bull_qqq_backtest(panel, start, end)
    holding_spy, sigs = determine_sleeve_state(panel, start, end)
    holding_spy = holding_spy.reindex(bull_raw.index).fillna(False)

    spy_close = panel["SPY"].ffill()
    signals = make_signals(spy_close)

    m_base = perf_metrics(bull_raw)
    rows = [("M1. No intramonth defense (baseline)",
              m_base["sharpe"], m_base["cagr"] * 100, m_base["vol"] * 100,
              m_base["max_drawdown"] * 100, 0, m_base["cagr"] / abs(m_base["max_drawdown"]))]

    # M2 sleeve-equity DD
    m2_scale = compute_dd_circuit_scale(bull_raw, sigs, DD_CIRCUIT_THRESHOLD, DD_CIRCUIT_SCALE)
    m2 = m2_scale * bull_raw
    m2_m = perf_metrics(m2)
    rows.append(("M2. Sleeve-equity DD-10% / 63d (current live)",
                 m2_m["sharpe"], m2_m["cagr"] * 100, m2_m["vol"] * 100,
                 m2_m["max_drawdown"] * 100, int((m2_scale.diff() < 0).sum()),
                 m2_m["cagr"] / abs(m2_m["max_drawdown"])))

    # Signal zoo
    for label, sig_series in signals.items():
        out, trips = apply_daily_signal_circuit(bull_raw, holding_spy, sigs, sig_series)
        m = perf_metrics(out)
        cal = m["cagr"] / abs(m["max_drawdown"]) if m["max_drawdown"] != 0 else float("nan")
        rows.append((f"daily {label}", m["sharpe"], m["cagr"] * 100, m["vol"] * 100,
                     m["max_drawdown"] * 100, trips, cal))

    # Sort by Sharpe desc
    sortable = rows[2:]
    sortable.sort(key=lambda r: -r[1])
    rows = rows[:2] + sortable

    print("\n" + "=" * 110)
    print("BULL-ext daily intramonth canary: signal zoo (2008-04 to 2026-05, 10bps)")
    print("=" * 110)
    print(f"{'Variant':<55} {'Sharpe':>8} {'CAGR':>8} {'Vol':>8} {'MaxDD':>9} {'Trips':>6} {'Calmar':>7}")
    print("-" * 110)
    for r in rows:
        print(f"{r[0]:<55} {r[1]:>8.3f} {r[2]:>7.2f}% {r[3]:>7.2f}% {r[4]:>8.2f}% {r[5]:>6d} {r[6]:>7.2f}")
    print("=" * 110)
