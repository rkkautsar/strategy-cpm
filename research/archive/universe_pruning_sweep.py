"""
Test removing rarely/never-picked assets from FCP-15.

Cascade:
  1. Drop XRT + XMMO (never picked in live-only) -> 13 risky
  2. Drop XRT + XMMO + VBR + VEA + XLE (low-pick) -> 10 risky
  3. If pruning hurts, try lowering TOP_K from 7 to 5 or 4
"""
from __future__ import annotations
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import strategy_fcp.fcp_live as fcp
from strategy_fcp.fcp_live import load_panel, run_fcp_backtest, RISKY_UNIVERSE


def metrics(daily):
    eq = (1 + daily).cumprod()
    r = daily.dropna()
    if r.empty: return {}
    n_y = len(r) / 252.0
    cagr = eq.iloc[-1] ** (1/n_y) - 1
    vol = r.std() * np.sqrt(252)
    sh = (r.mean()*252) / vol if vol > 0 else np.nan
    dd = (eq / eq.cummax() - 1).min()
    return dict(cagr=cagr, vol=vol, sharpe=sh, maxdd=dd)


def run(panel, risky, start, end, top_k=None, hold_buffer=None):
    saved = (fcp.RISKY_UNIVERSE, fcp.AGGR_FACTORS, fcp.INTERNATIONAL,
             fcp.DIVERSIFIERS, fcp.HOLD_BUFFER, fcp.TOP_K_CANDIDATES)
    fcp.RISKY_UNIVERSE = risky
    intl = [t for t in risky if t in ('VEA','VWO','EFA','EEM')]
    div = [t for t in risky if t in ('GLD','TLT','IAU','KMLM')]
    fcp.AGGR_FACTORS = [t for t in risky if t not in intl + div]
    fcp.INTERNATIONAL = intl
    fcp.DIVERSIFIERS = div
    fcp.HOLD_BUFFER = hold_buffer if hold_buffer is not None else 2.5
    if top_k is not None:
        fcp.TOP_K_CANDIDATES = top_k
    try:
        daily, _ = run_fcp_backtest(panel, start, end, apply_vol_target=True)
        return metrics(daily)
    finally:
        (fcp.RISKY_UNIVERSE, fcp.AGGR_FACTORS, fcp.INTERNATIONAL,
         fcp.DIVERSIFIERS, fcp.HOLD_BUFFER, fcp.TOP_K_CANDIDATES) = saved


def fmt(label, m_h, m_l):
    return (f"  {label:<48s}  hybrid Sh={m_h['sharpe']:+.3f} CAGR={m_h['cagr']*100:+.2f}% DD={m_h['maxdd']*100:+6.2f}%   "
            f"live Sh={m_l['sharpe']:+.3f} CAGR={m_l['cagr']*100:+.2f}% DD={m_l['maxdd']*100:+6.2f}%")


def main():
    panel = load_panel(start=pd.Timestamp("1995-01-01"))
    end = panel.index.max()
    hybrid_start = pd.Timestamp("1997-08-31")
    live_start = pd.Timestamp("2008-09-30")

    BASE = list(RISKY_UNIVERSE)  # FCP-15
    print(f"Baseline FCP-{len(BASE)}: {BASE}\n")

    # 1. Drop XRT + XMMO (never picked)
    p1 = [t for t in BASE if t not in ("XRT", "XMMO")]
    # 2. Drop all low-pick: XRT + XMMO + VBR + VEA + XLE (5 assets, all <2% pick rate)
    p2 = [t for t in BASE if t not in ("XRT", "XMMO", "VBR", "VEA", "XLE")]

    variants = [
        ("baseline FCP-15 (TOP_K=7)", BASE, None),
        ("FCP-13 (drop XRT, XMMO)", p1, None),
        ("FCP-10 (drop 5 low-pick)", p2, None),
    ]

    print("=" * 145)
    print("CASCADE 1: drop never-picked / rarely-picked assets")
    print("=" * 145)
    for label, risky, tk in variants:
        m_h = run(panel, risky, hybrid_start, end, top_k=tk)
        m_l = run(panel, risky, live_start, end, top_k=tk)
        print(fmt(f"{label} ({len(risky)} risky)", m_h, m_l))

    # 3. TOP_K sweep on FCP-15 baseline
    print()
    print("=" * 145)
    print("TOP_K sweep on FCP-15 baseline (current TOP_K=7)")
    print("=" * 145)
    for tk in [3, 4, 5, 6, 7, 8, 10, 12, 15]:
        m_h = run(panel, BASE, hybrid_start, end, top_k=tk)
        m_l = run(panel, BASE, live_start, end, top_k=tk)
        print(fmt(f"TOP_K = {tk}", m_h, m_l))

    # 4. TOP_K sweep on pruned FCP-13 and FCP-10
    print()
    print("=" * 145)
    print("TOP_K sweep on FCP-13 (drop XRT, XMMO)")
    print("=" * 145)
    for tk in [3, 4, 5, 6, 7, 8, 10, 12]:
        m_h = run(panel, p1, hybrid_start, end, top_k=tk)
        m_l = run(panel, p1, live_start, end, top_k=tk)
        print(fmt(f"TOP_K = {tk}", m_h, m_l))

    print()
    print("=" * 145)
    print("TOP_K sweep on FCP-10 (drop 5 low-pick)")
    print("=" * 145)
    for tk in [3, 4, 5, 6, 7, 8, 10]:
        m_h = run(panel, p2, hybrid_start, end, top_k=tk)
        m_l = run(panel, p2, live_start, end, top_k=tk)
        print(fmt(f"TOP_K = {tk}", m_h, m_l))


if __name__ == "__main__":
    main()
