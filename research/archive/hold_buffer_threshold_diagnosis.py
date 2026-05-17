"""
Diagnose why HOLD_BUFFER 2z -> 3z gives a 0.20 Sharpe jump (live-only 18y).

Hypothesis: a small number of months drive the difference. Identify them.

Tests:
  - Run FCP with HOLD_BUFFER = 2.5, 2.75, 3.0, 3.25, 3.5 to confirm the threshold shape
  - Compare holdings month-by-month between buf=2 and buf=3
  - Identify which months differ (different pair selection) and their P&L impact
  - Test on multiple sub-windows to see if the threshold persists
"""
from __future__ import annotations
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import strategy_fcp.fcp_live as fcp
from strategy_fcp.fcp_live import (
    load_panel, run_fcp_backtest, compute_target_weights,
)


def metrics_from_daily(daily_ret):
    eq = (1 + daily_ret).cumprod()
    r = daily_ret.dropna()
    if r.empty: return {}
    n_y = len(r) / 252.0
    cagr = eq.iloc[-1] ** (1/n_y) - 1
    vol = r.std() * np.sqrt(252)
    sh = (r.mean()*252) / vol if vol > 0 else np.nan
    dd = (eq / eq.cummax() - 1).min()
    return dict(cagr=cagr, vol=vol, sharpe=sh, maxdd=dd, eq=eq, ret=daily_ret)


def run_with_buffer(panel, start, end, buf, vt=True):
    saved_buf = fcp.HOLD_BUFFER
    fcp.HOLD_BUFFER = buf
    try:
        daily, _ = run_fcp_backtest(panel, start, end, apply_vol_target=vt)
        return metrics_from_daily(daily)
    finally:
        fcp.HOLD_BUFFER = saved_buf


def get_holdings(panel, start, end, buf):
    """Replay FCP and return monthly holdings dict per signal date."""
    saved_buf = fcp.HOLD_BUFFER
    fcp.HOLD_BUFFER = buf
    try:
        idx = panel.loc[start:end].index
        eom = list(pd.Series(idx).groupby(idx.to_period("M")).last())
        holdings = {}
        prev_pair = None
        for d in eom:
            try:
                w, new_pair, regime, _ = compute_target_weights(panel, d, prev_pair)
                holdings[d] = (w, new_pair, regime)
                prev_pair = new_pair
            except Exception:
                holdings[d] = ({}, None, "ERR")
        return holdings
    finally:
        fcp.HOLD_BUFFER = saved_buf


def main():
    panel = load_panel(start=pd.Timestamp("1995-01-01"))
    end = panel.index.max()
    live_start = pd.Timestamp("2008-09-30")
    hybrid_start = pd.Timestamp("1997-08-31")

    print("=" * 145)
    print("HOLD_BUFFER threshold diagnosis: WHY does 2z -> 3z give big Sharpe jump?")
    print("=" * 145)

    # 1. Fine-grained sweep around the threshold
    print("\n[Fine-grained HOLD_BUFFER sweep]")
    print("-" * 145)
    print(f"  Extended 28.7y:")
    for buf in [0.0, 0.5, 1.0, 1.5, 2.0, 2.25, 2.5, 2.75, 3.0, 3.25, 3.5, 4.0, 5.0, 10.0]:
        m = run_with_buffer(panel, hybrid_start, end, buf)
        print(f"    HOLD_BUFFER = {buf:>5.2f}z   Sh {m['sharpe']:+.3f}  CAGR {m['cagr']*100:+5.2f}%  DD {m['maxdd']*100:+6.2f}%")

    print(f"\n  Live-only 18y:")
    for buf in [0.0, 0.5, 1.0, 1.5, 2.0, 2.25, 2.5, 2.75, 3.0, 3.25, 3.5, 4.0, 5.0, 10.0]:
        m = run_with_buffer(panel, live_start, end, buf)
        print(f"    HOLD_BUFFER = {buf:>5.2f}z   Sh {m['sharpe']:+.3f}  CAGR {m['cagr']*100:+5.2f}%  DD {m['maxdd']*100:+6.2f}%")

    # 2. Compare holdings between 2z and 3z
    print("\n[Holdings diff: HOLD_BUFFER=2z vs 3z, live-only 18y]")
    print("-" * 145)
    h2 = get_holdings(panel, live_start, end, 2.0)
    h3 = get_holdings(panel, live_start, end, 3.0)

    diff_months = []
    for d in sorted(set(h2.keys()) | set(h3.keys())):
        w2 = h2.get(d, ({}, None, ""))[0]
        w3 = h3.get(d, ({}, None, ""))[0]
        # Compare pair selection (sets of tickers)
        s2 = set(w2.keys())
        s3 = set(w3.keys())
        if s2 != s3:
            diff_months.append((d, w2, w3))

    print(f"  Months where 2z and 3z chose different pairs: {len(diff_months)} / {len(h2)}")
    print(f"\n  Showing first 20 differences:")
    for d, w2, w3 in diff_months[:20]:
        s2 = set(w2.keys())
        s3 = set(w3.keys())
        print(f"    {d.date()}: buf=2z {sorted(s2)}  -->  buf=3z {sorted(s3)}")

    # 3. Compute monthly returns for each variant and identify the months that drive the gap
    print("\n[Monthly P&L impact of holdings differences (buf=3z - buf=2z)]")
    print("-" * 145)
    m2 = run_with_buffer(panel, live_start, end, 2.0)
    m3 = run_with_buffer(panel, live_start, end, 3.0)
    # Compute monthly compounded returns for each
    monthly_2 = (1 + m2["ret"]).resample("ME").apply(lambda x: x.prod() - 1)
    monthly_3 = (1 + m3["ret"]).resample("ME").apply(lambda x: x.prod() - 1)
    diff = monthly_3 - monthly_2
    diff_sorted = diff.sort_values(ascending=False)
    print(f"\n  Top 15 months where 3z beat 2z most:")
    for d, val in diff_sorted.head(15).items():
        print(f"    {d.date()}: 2z={monthly_2[d]*100:+.2f}%  3z={monthly_3[d]*100:+.2f}%  diff={val*100:+.2f}%")
    print(f"\n  Top 15 months where 3z LOST to 2z most:")
    for d, val in diff_sorted.tail(15).items():
        print(f"    {d.date()}: 2z={monthly_2[d]*100:+.2f}%  3z={monthly_3[d]*100:+.2f}%  diff={val*100:+.2f}%")

    # Cumulative diff
    cum_diff_3_minus_2 = (1 + diff.fillna(0)).cumprod()
    print(f"\n  Total cumulative outperformance of 3z over 2z (live-only 18y): {(cum_diff_3_minus_2.iloc[-1] - 1)*100:+.2f}%")
    print(f"  Number of months where diff > 1%: {(diff.abs() > 0.01).sum()}")
    print(f"  Number of months where diff > 3%: {(diff.abs() > 0.03).sum()}")
    print(f"  Mean monthly absolute diff: {diff.abs().mean()*100:.3f}%")

    # 4. Test threshold persistence on subwindows
    print("\n[Subwindow stability of HOLD_BUFFER 2z vs 3z gap]")
    print("-" * 145)
    subwindows = [
        ("2008-09 to 2014-12", "2008-09-30", "2014-12-31"),
        ("2015-01 to 2019-12", "2015-01-01", "2019-12-31"),
        ("2020-01 to 2026-05", "2020-01-01", "2026-05-15"),
    ]
    for label, s, e in subwindows:
        m_2z = run_with_buffer(panel, pd.Timestamp(s), pd.Timestamp(e), 2.0)
        m_3z = run_with_buffer(panel, pd.Timestamp(s), pd.Timestamp(e), 3.0)
        gap = m_3z['sharpe'] - m_2z['sharpe']
        print(f"  {label}:  buf=2z Sh {m_2z['sharpe']:+.3f}, buf=3z Sh {m_3z['sharpe']:+.3f}, gap {gap:+.3f}")


if __name__ == "__main__":
    main()
