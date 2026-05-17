"""
Test ADDING assets to FCP-14 risky universe.
Hypothesis: TOP_K=7 selection benefits from larger candidate pool (combinatorial diversity).
Adding assets that fill gaps (defensives, sectors not represented, alternatives) may help.
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
    # Reclassify: anything not intl/diversifier goes to AGGR
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

    BASE = list(fcp.RISKY_UNIVERSE)  # 14 risky (post-AVUV-drop)
    print(f'Baseline FCP-14: {BASE}')
    print()

    # Single-asset additions to test
    additions = {
        # Sectors not represented
        'XLV (Healthcare)':      'XLV',
        'XLU (Utilities)':       'XLU',
        'XLP (Cons Staples)':    'XLP',
        'XLF (Financials)':      'XLF',
        'XLI (Industrials)':     'XLI',
        'XLK (Tech Sector)':     'XLK',
        'XLY (Cons Discr)':      'XLY',
        # Real estate / additional sectors
        'VNQ (US REIT)':         'VNQ',
        # Bonds (different duration)
        'IEF (Interm Treasury)': 'IEF',
        'TIP (TIPS)':            'TIP',
        'HYG (High Yield)':      'HYG',
        'LQD (Inv Grade Corp)':  'LQD',
        # Broad market
        'IWM (Russell 2k)':      'IWM',
        # Alternatives
        'KMLM (Managed Fut)':    'KMLM',
        'DBC (Commodities)':     'DBC',
        # International
        'EFA (Dev Intl)':        'EFA',
        'EEM (EM)':              'EEM',
    }

    # Multi-additions to test
    multi = {
        'add VNQ + XLV':            ['VNQ', 'XLV'],
        'add VNQ + IEF':            ['VNQ', 'IEF'],
        'add IEF + KMLM':           ['IEF', 'KMLM'],
        'add VNQ + IEF + KMLM':     ['VNQ', 'IEF', 'KMLM'],
        'add 4 sectors (XLV/U/P/I)': ['XLV', 'XLU', 'XLP', 'XLI'],
        'add 7 sectors (all SPDR)':  ['XLV','XLU','XLP','XLF','XLI','XLK','XLY'],
    }

    print('=' * 130)
    print('SINGLE ADDITIONS to FCP-14 (baseline + 1 new asset = 15 risky)')
    print('=' * 130)
    base_m_h = run_universe(panel, BASE, hybrid_start, end)
    base_m_l = run_universe(panel, BASE, live_start, end)
    print(f'  baseline FCP-14: hybrid Sh={base_m_h['sharpe']:.3f} CAGR={base_m_h['cagr']*100:+.2f}% DD={base_m_h['maxdd']*100:+.2f}%')
    print(f'  baseline FCP-14: live18  Sh={base_m_l['sharpe']:.3f} CAGR={base_m_l['cagr']*100:+.2f}% DD={base_m_l['maxdd']*100:+.2f}%')
    print()
    print(f'  {'Addition':<28s}  {'hybrid Sh':>9s}  {'hybrid Δ':>9s}  {'live Sh':>9s}  {'live Δ':>9s}  {'live CAGR':>10s}  {'live DD':>9s}')
    rows = []
    for label, asset in additions.items():
        if asset not in panel.columns or panel[asset].dropna().empty:
            print(f'  {label:<28s}  -- NOT IN PANEL --')
            continue
        new = BASE + [asset]
        try:
            m_h = run_universe(panel, new, hybrid_start, end)
            m_l = run_universe(panel, new, live_start, end)
            dh = m_h['sharpe'] - base_m_h['sharpe']
            dl = m_l['sharpe'] - base_m_l['sharpe']
            print(f'  {label:<28s}  {m_h['sharpe']:>+8.3f}  {dh:>+8.3f}  {m_l['sharpe']:>+8.3f}  {dl:>+8.3f}  {m_l['cagr']*100:>+8.2f}%  {m_l['maxdd']*100:>+7.2f}%')
            rows.append((label, asset, dh, dl, m_l))
        except Exception as e:
            print(f'  {label:<28s}  ERR {e}')

    print()
    print('=' * 130)
    print('MULTI-ASSET ADDITIONS')
    print('=' * 130)
    for label, assets in multi.items():
        avail = [a for a in assets if a in panel.columns and not panel[a].dropna().empty]
        if len(avail) != len(assets): print(f'  {label:<28s}  some missing'); continue
        new = BASE + avail
        try:
            m_h = run_universe(panel, new, hybrid_start, end)
            m_l = run_universe(panel, new, live_start, end)
            dh = m_h['sharpe'] - base_m_h['sharpe']
            dl = m_l['sharpe'] - base_m_l['sharpe']
            print(f'  {label:<28s}  hybrid {m_h['sharpe']:.3f} (Δ{dh:+.3f})  live {m_l['sharpe']:.3f} (Δ{dl:+.3f})  CAGR {m_l['cagr']*100:+.2f}%  DD {m_l['maxdd']*100:+.2f}%')
        except Exception as e:
            print(f'  {label:<28s}  ERR {e}')

    print()
    print('=' * 130)
    print('TOP IMPROVEMENTS (by live18 Δ Sharpe)')
    print('=' * 130)
    rows.sort(key=lambda r: -r[3])
    for label, asset, dh, dl, m_l in rows[:8]:
        print(f'  {label:<28s}  live Δ {dl:+.3f}  live Sh {m_l['sharpe']:.3f}')


if __name__ == '__main__':
    main()
