"""
Test ADDING a SECOND asset to FCP-15 (post-XLV).
Hypothesis: maybe XLV unlocks more universe additions that previously hurt.
Also test specific combos to find the best 16/17 universe.
"""
from __future__ import annotations
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import strategy_fcp.fcp_live as fcp
from strategy_fcp.fcp_live import load_panel, run_fcp_backtest


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


def run_universe(panel, risky, start, end):
    saved = (fcp.RISKY_UNIVERSE, fcp.AGGR_FACTORS, fcp.INTERNATIONAL, fcp.DIVERSIFIERS, fcp.HOLD_BUFFER)
    fcp.RISKY_UNIVERSE = risky
    intl = [t for t in risky if t in ('VEA','VWO','EFA','EEM','SCZ')]
    div = [t for t in risky if t in ('GLD','TLT','IAU','KMLM','LQD','HYG','BND','IEF')]
    fcp.AGGR_FACTORS = [t for t in risky if t not in intl + div]
    fcp.INTERNATIONAL = intl
    fcp.DIVERSIFIERS = div
    fcp.HOLD_BUFFER = 2.5
    try:
        daily, _ = run_fcp_backtest(panel, start, end, apply_vol_target=True)
        return metrics(daily)
    finally:
        fcp.RISKY_UNIVERSE, fcp.AGGR_FACTORS, fcp.INTERNATIONAL, fcp.DIVERSIFIERS, fcp.HOLD_BUFFER = saved


def main():
    panel = load_panel(start=pd.Timestamp('1995-01-01'))
    end = panel.index.max()
    hybrid_start = pd.Timestamp('1997-08-31')
    live_start = pd.Timestamp('2008-09-30')

    BASE = list(fcp.RISKY_UNIVERSE)  # FCP-15 with XLV
    print(f'Baseline FCP-15 (with XLV): {BASE}')
    print()

    # Single additions on top of FCP-15
    additions = {
        'XLP (Cons Staples)':     'XLP',
        'XLU (Utilities)':        'XLU',
        'XLK (Tech Sector)':      'XLK',
        'XLY (Cons Discr)':       'XLY',
        'XLF (Financials)':       'XLF',
        'XLI (Industrials)':      'XLI',
        'VNQ (US REIT)':          'VNQ',
        'IWM (Russell 2k)':       'IWM',
        'EFA (Dev Intl)':         'EFA',
        'EEM (EM)':               'EEM',
        'IAU (Gold trust)':       'IAU',
        'HYG (High Yield)':       'HYG',
        'KMLM (Managed Fut)':     'KMLM',
        'DBC (Commodities)':      'DBC',
        'TIP (TIPS)':             'TIP',
        'PRF (Fundamental val)':  'PRF',
        'MTUM (Momentum)':        'MTUM',
        'SLYV (Small Val 600)':   'SLYV',
    }

    base_h = run_universe(panel, BASE, hybrid_start, end)
    base_l = run_universe(panel, BASE, live_start, end)
    print(f'  baseline: hybrid Sh={base_h["sharpe"]:.3f}  live Sh={base_l["sharpe"]:.3f}  CAGR={base_l["cagr"]*100:+.2f}%  DD={base_l["maxdd"]*100:+.2f}%')
    print()

    print('=' * 130)
    print('SINGLE ADDITION on top of FCP-15')
    print('=' * 130)
    print(f'  {"Addition":<28s}  {"hybrid Sh":>10s}  {"hybrid Δ":>9s}  {"live Sh":>9s}  {"live Δ":>9s}  {"live CAGR":>10s}  {"live DD":>9s}')

    rows = []
    for label, asset in additions.items():
        if asset not in panel.columns or panel[asset].dropna().empty:
            print(f'  {label:<28s}  -- MISSING --')
            continue
        new = BASE + [asset]
        m_h = run_universe(panel, new, hybrid_start, end)
        m_l = run_universe(panel, new, live_start, end)
        dh = m_h['sharpe'] - base_h['sharpe']
        dl = m_l['sharpe'] - base_l['sharpe']
        rows.append((label, asset, dh, dl, m_h, m_l))
        print(f'  {label:<28s}  {m_h["sharpe"]:>+9.3f}  {dh:>+8.3f}  {m_l["sharpe"]:>+8.3f}  {dl:>+8.3f}  {m_l["cagr"]*100:>+8.2f}%  {m_l["maxdd"]*100:>+7.2f}%')

    rows.sort(key=lambda r: -r[3])
    print()
    print('=' * 130)
    print('TOP 5 ADDITIONS to test in COMBINATION')
    print('=' * 130)
    top5 = [r[1] for r in rows[:5]]
    print(f'  Top-5: {top5}')

    # Test pairs of top-5 additions
    print()
    from itertools import combinations
    print('=' * 130)
    print('PAIRS of top-5 additions to FCP-15 (yields 17-asset universe)')
    print('=' * 130)
    for a, b in combinations(top5, 2):
        new = BASE + [a, b]
        m_h = run_universe(panel, new, hybrid_start, end)
        m_l = run_universe(panel, new, live_start, end)
        dh = m_h['sharpe'] - base_h['sharpe']
        dl = m_l['sharpe'] - base_l['sharpe']
        print(f'  +{a:5s}+{b:<5s}  hybrid {m_h["sharpe"]:.3f} (Δ{dh:+.3f})  live {m_l["sharpe"]:.3f} (Δ{dl:+.3f})  CAGR {m_l["cagr"]*100:+.2f}%  DD {m_l["maxdd"]*100:+.2f}%')

    # Test top-3 combination
    if len(top5) >= 3:
        print()
        print('=' * 130)
        print('TOP-3 + top-4 + top-5 combinations (build up universe)')
        print('=' * 130)
        for k in [3, 4, 5]:
            new = BASE + top5[:k]
            m_h = run_universe(panel, new, hybrid_start, end)
            m_l = run_universe(panel, new, live_start, end)
            dh = m_h['sharpe'] - base_h['sharpe']
            dl = m_l['sharpe'] - base_l['sharpe']
            print(f'  +{",".join(top5[:k]):<28s}  hybrid {m_h["sharpe"]:.3f} (Δ{dh:+.3f})  live {m_l["sharpe"]:.3f} (Δ{dl:+.3f})  CAGR {m_l["cagr"]*100:+.2f}%  DD {m_l["maxdd"]*100:+.2f}%')


if __name__ == '__main__':
    main()
