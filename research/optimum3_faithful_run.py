"""Runner: FAITHFUL standalone Optimum3 -- backtest, lookback sensitivity, optional
3-tranche, validation vs AllocateSmartly published track record, and CPM-8 +
benchmark comparison on the SAME common window. Point estimates only. ASCII only.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research import optimum3_faithful_harness as O
from research import cpm_opt3_universe_harness as H


def fmt_row(name, m):
    return (f"{name:<30}{m['Sharpe']:>7.3f}{m['Sortino']:>8.3f}{m['Calmar']:>7.3f}"
            f"{m['Martin']:>7.2f}{m['MaxDD']*100:>8.2f}%{m['CVaR95']*100:>7.2f}%"
            f"{m['CAGR']*100:>7.2f}%{m['Vol']*100:>6.2f}%"
            + (f"{m.get('TurnAnn', float('nan')):>7.2f}" if 'TurnAnn' in m else "       "))


HDR = (f"{'config':<30}{'Sharpe':>7}{'Sortino':>8}{'Calmar':>7}{'Martin':>7}"
       f"{'MaxDD':>9}{'CVaR':>7}{'CAGR':>7}{'Vol':>6}{'Turn':>7}")


def main():
    panel, intra, on = H.load_extended()
    cash = panel["SHV"].ffill().pct_change()
    cs, ce = O.COMMON_START, O.END

    # ---- data reality ----
    print("=" * 100)
    print("EFFECTIVE UNIVERSE / DATA REALITY (faithful standalone Optimum3)")
    print("=" * 100)
    incept = {t: (panel[t].dropna().index[0].date() if t in panel and len(panel[t].dropna()) else None)
              for t in O.OPT3}
    print(f"Panel: {panel.index[0].date()} -> {panel.index[-1].date()}")
    print(f"OPT3 universe (15): {O.OPT3}")
    print(f"Freshly fetched (NO proxy stitch, NO PIT): {H.NEW_TICKERS}")
    for t in O.OPT3:
        flag = "  <- NEW/short-hist/non-PIT" if t in H.NEW_TICKERS else ""
        print(f"   {t:<5} {incept[t]}{flag}")
    print(f"Binding inception: SCZ 2007-12. Common all-rankable window: {cs.date()}..{ce.date()}")
    print(f"Cash asset: SHV. Lookback proxy primary: 13612U (UNDISCLOSED -- see sensitivity).")
    print(f"NO canary, NO vol-adj, NO vol-target, NO breadth-scale. Pure dual-mom + MCA-3 + EW.")
    print()

    store = {}

    def add(name, wf, panel_=None):
        s, _ = O.run(wf, panel, intra, on, cs, ce)
        m = O.metrics(s, cash, wf, panel, cs, ce)
        store[name] = (s, m)
        return m

    # ---- PRIMARY faithful Optimum3 ----
    print("=" * 100)
    print(f"PRIMARY: faithful Optimum3 (13612U, top-half=8, MCA-3, EW 1/3, cash=SHV)  {cs.date()}..{ce.date()}")
    print("=" * 100)
    print(HDR)
    wf_primary = O.make_opt3_weight_fn(panel, lookback="13612U", top_half=8, select="mca")
    m_primary = add("O3 13612U top8 MCA *", wf_primary)
    print(fmt_row("O3 13612U top8 MCA *", m_primary))
    print()

    # ---- LOOKBACK sensitivity (the undisclosed-lookback uncertainty) ----
    print("=" * 100)
    print("LOOKBACK SENSITIVITY (undisclosed -> how uncertain is the repro?)  [MCA-3, top-half=8]")
    print("=" * 100)
    print(HDR)
    for lb in ("6m", "12m", "13612U"):
        wf = O.make_opt3_weight_fn(panel, lookback=lb, top_half=8, select="mca")
        m = add(f"O3 {lb} top8 MCA", wf)
        print(fmt_row(f"O3 {lb} top8 MCA", m))
    print()

    # ---- structure sensitivities: top-half 7 vs 8; MCA vs top-3-momentum ----
    print("=" * 100)
    print("STRUCTURE SENSITIVITY [13612U]")
    print("=" * 100)
    print(HDR)
    for th in (7, 8):
        wf = O.make_opt3_weight_fn(panel, lookback="13612U", top_half=th, select="mca")
        m = add(f"O3 13612U top{th} MCA", wf)
        print(fmt_row(f"O3 13612U top{th} MCA", m))
    wf_tm = O.make_opt3_weight_fn(panel, lookback="13612U", top_half=8, select="topmom")
    m_tm = add("O3 13612U top8 top3mom (no MCA)", wf_tm)
    print(fmt_row("O3 13612U top8 top3mom (noMCA)", m_tm))
    print()

    # ---- optional 3-tranche execution proxy ----
    print("=" * 100)
    print("OPTIONAL: 3-tranche execution proxy (days ~2/9/16; T+1 close-to-close; primary=13612U/MCA/top8)")
    print("=" * 100)
    print(HDR)
    print("NOTE: tranche changes BOTH rebalance timing (mid-month days vs month-end) and")
    print("      execution model (ccT+1 vs mooex) -> rough SMOOTHING illustration, not a clean A/B.")
    s_tr = O.run_tranche3(wf_primary, panel, cs, ce, offsets=(1, 8, 15))
    m_tr = O.metrics(s_tr, cash)
    store["O3 3-tranche (proxy)"] = (s_tr, m_tr)
    print(fmt_row("O3 3-tranche (proxy, ccT+1)", m_tr))
    print()

    # ---- CPM-8 + cheap benchmarks on SAME window ----
    print("=" * 100)
    print(f"COMPARISON: CPM-8 sleeve + cheap benchmarks (SAME window {cs.date()}..{ce.date()})")
    print("=" * 100)
    print(HDR)
    wf8 = H.make_weight_fn(panel, H.PROD8, top_k=4, method="minvar", select="topk")
    m8 = add("CPM-8 minvar k4 (prod)", wf8)
    print(fmt_row("CPM-8 minvar k4 (prod)", m8))
    wf6040 = O.const_weight_fn({"SPY": 0.6, "IEF": 0.4})
    m6040 = add("60/40 SPY/IEF", wf6040)
    print(fmt_row("60/40 SPY/IEF", m6040))
    wfspy = O.const_weight_fn({"SPY": 1.0})
    mspy = add("SPY buy-hold", wfspy)
    print(fmt_row("SPY buy-hold", mspy))
    print()

    # ---- VALIDATION vs AllocateSmartly published ----
    print("=" * 100)
    print("VALIDATION vs AllocateSmartly published Optimum3 (direction / ballpark only)")
    print("=" * 100)
    print("AllocateSmartly (allocatesmartly.com/financial-mentors-optimum3-strategy):")
    print("  - Independent test; BACKTEST SINCE 1987; net of transaction costs; rules UNDISCLOSED.")
    print("  - Confirms our rule skeleton: 15 global asset classes; 'selects roughly the top half")
    print("    that have exhibited the strongest momentum'; 'dual momentum' (positive AND relative);")
    print("    'high momentum diversification' optimization (= the Varadi MCA min-corr step).")
    print("  - Member-derived figure (Reddit, ~last 20y): ~11.7% CAGR vs -12.9% MaxDD")
    print("    (high CAGR/MaxDD ratio ~0.9; vol roughly inline with a diversified B&H).")
    print("OUR REPRO (primary 13612U/MCA/top8, common window {}..{}):".format(cs.date(), ce.date()))
    print(f"  - CAGR {m_primary['CAGR']*100:.2f}%, MaxDD {m_primary['MaxDD']*100:.2f}%, "
          f"Sharpe {m_primary['Sharpe']:.3f}, Vol {m_primary['Vol']*100:.2f}%, "
          f"CAGR/MaxDD {abs(m_primary['CAGR']/m_primary['MaxDD']):.2f}.")
    print(f"  - Lookback span across {{6m,12m,13612U}}: CAGR "
          f"{min(store[f'O3 {lb} top8 MCA'][1]['CAGR'] for lb in ('6m','12m','13612U'))*100:.2f}%.."
          f"{max(store[f'O3 {lb} top8 MCA'][1]['CAGR'] for lb in ('6m','12m','13612U'))*100:.2f}%, "
          f"MaxDD {min(store[f'O3 {lb} top8 MCA'][1]['MaxDD'] for lb in ('6m','12m','13612U'))*100:.2f}%.."
          f"{max(store[f'O3 {lb} top8 MCA'][1]['MaxDD'] for lb in ('6m','12m','13612U'))*100:.2f}%.")
    print("  - Cannot match 1987 (our 15-ETF universe only ~2009+); recent-overlap validation only.")
    print()

    # ---- per-crisis total returns ----
    print("=" * 100)
    print("PER-CRISIS + BULL (total return %)")
    print("=" * 100)
    names = ["O3 13612U top8 MCA *", "CPM-8 minvar k4 (prod)", "60/40 SPY/IEF", "SPY buy-hold"]
    hdr = f"{'window':<28}" + "".join(f"{n.split(' (')[0][:13]:>14}" for n in names)
    print(hdr)
    for label, (a, b) in O.crisis_windows().items():
        a, b = pd.Timestamp(a), pd.Timestamp(b)
        if b < cs:
            continue
        line = f"{label:<28}"
        for n in names:
            s = store[n][0]
            seg = s.loc[(s.index >= a) & (s.index <= b)]
            tr = (1 + seg).prod() - 1 if len(seg) else float("nan")
            line += f"{tr*100:>13.2f}%"
        print(line)
    print()

    # save json
    out = {"common_window": [str(cs.date()), str(ce.date())],
           "primary": m_primary,
           "all": {k: v[1] for k, v in store.items()},
           "inceptions": {t: str(incept[t]) for t in O.OPT3}}
    p = ROOT / "research" / "optimum3_faithful_results.json"
    p.write_text(json.dumps(out, indent=2, default=float))
    print(f"Saved {p}")


if __name__ == "__main__":
    main()
