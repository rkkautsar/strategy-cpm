"""Runner: CPM-8 vs OPT3-universe x {minvar,MCA} x top-K{4,5,6}, sleeve only.

Outputs a common-window comparison table, CPM-8 full-window context, per-crisis
+ bull-window block, and effective-universe / window / dropped-tickers report.
Point estimates only. ASCII only.
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

from research import cpm_opt3_universe_harness as H


def fmt_row(name, m):
    return (f"{name:<26}{m['Sharpe']:>7.3f}{m['Sortino']:>8.3f}{m['Calmar']:>7.3f}"
            f"{m['Martin']:>7.2f}{m['MaxDD']*100:>8.2f}%{m['CVaR95']*100:>7.2f}%"
            f"{m['CAGR']*100:>7.2f}%{m['Vol']*100:>6.2f}%"
            + (f"{m.get('TurnAnn', float('nan')):>7.2f}" if 'TurnAnn' in m else "       "))


HDR = (f"{'config':<26}{'Sharpe':>7}{'Sortino':>8}{'Calmar':>7}{'Martin':>7}"
       f"{'MaxDD':>9}{'CVaR':>7}{'CAGR':>7}{'Vol':>6}{'Turn':>7}")


def main():
    panel, intra, on = H.load_extended()
    cash = panel["SHV"].ffill().pct_change()

    # effective universe report
    print("=" * 96)
    print("EFFECTIVE UNIVERSE / DATA REALITY")
    print("=" * 96)
    incept = {}
    for t in H.OPT3:
        col = panel[t].dropna()
        incept[t] = col.index[0].date() if len(col) else None
    new_incept = {t: incept[t] for t in H.NEW_TICKERS if t in panel.columns}
    print(f"Panel: {panel.index[0].date()} -> {panel.index[-1].date()}")
    print(f"OPT3 universe ({len(H.OPT3)}): {H.OPT3}")
    print(f"Newly fetched (no proxy stitch, cached yfinance): {H.NEW_TICKERS}")
    print("Inceptions (panel-effective first non-NaN):")
    for t in H.OPT3:
        flag = "  <- NEW/short-hist" if t in H.NEW_TICKERS else ""
        print(f"   {t:<5} {incept[t]}{flag}")
    binding = max((v for v in new_incept.values()))
    print(f"Binding new-ticker inception: {binding} (SCZ). All-rankable common start: {H.COMMON_START.date()}")
    print(f"Dropped tickers: NONE (all 15 resolvable). EM=EEM, intl-REIT=RWX, commodities=DBC.")
    print(f"Dual-role kept (faithful to Optimum3): IEF/TLT/TIP are momentum candidates;")
    print(f"  TIP also canary, SHV/IEF also safe pool.")
    print()

    # ---- CPM-8 full prod clean window (context) ----
    print("=" * 96)
    print(f"CONTEXT: CPM-8 baseline on FULL prod clean window {H.PROD_CLEAN.date()}..{H.END.date()}")
    print("=" * 96)
    print(HDR)
    wf8 = H.make_weight_fn(panel, H.PROD8, top_k=4, method="minvar")
    s8full, _ = H.run(wf8, panel, intra, on, H.PROD_CLEAN, H.END)
    m8full = H.metrics(s8full, cash, wf8, panel, H.PROD_CLEAN, H.END)
    print(fmt_row("CPM-8 minvar k4 (prod)", m8full))
    print()

    # ---- COMMON window comparison ----
    cs, ce = H.COMMON_START, H.END
    print("=" * 96)
    print(f"COMMON WINDOW {cs.date()}..{ce.date()} (all 15 OPT3 assets rankable) -- apples-to-apples")
    print("=" * 96)
    print(HDR)

    configs = [("CPM-8 minvar k4", H.PROD8, 4, "minvar", "topk")]
    for k in (4, 5, 6):
        configs.append((f"OPT3 minvar k{k}", H.OPT3, k, "minvar", "topk"))
    for k in (4, 5, 6):
        configs.append((f"OPT3 MCA k{k}", H.OPT3, k, "mca", "topk"))
    # Optimum3-faithful: top-half pool -> final 3 (EW 1/3)
    configs.append(("OPT3 half->3 minvar", H.OPT3, 0, "minvar", "half3"))
    configs.append(("OPT3 half->3 MCA", H.OPT3, 0, "mca", "half3"))

    series_store = {}
    rows = {}
    for name, univ, k, meth, sel in configs:
        wf = H.make_weight_fn(panel, univ, top_k=k, method=meth, select=sel)
        s, _ = H.run(wf, panel, intra, on, cs, ce)
        m = H.metrics(s, cash, wf, panel, cs, ce)
        series_store[name] = (s, wf, univ, k, meth, sel)
        rows[name] = m
        print(fmt_row(name, m))
    print()

    # ---- per-crisis + bull (Sharpe / total return) ----
    print("=" * 96)
    print("PER-CRISIS + BULL-WINDOW (total return %, common-window configs)")
    print("=" * 96)
    cw = H.crisis_windows()
    names = list(series_store.keys())
    hdr = f"{'window':<26}" + "".join(f"{n.replace('OPT3 ','O3-').replace('CPM-8 ','C8-'):>13}" for n in names)
    print(hdr)
    for label, (a, b) in cw.items():
        a, b = pd.Timestamp(a), pd.Timestamp(b)
        if b < cs:
            continue
        line = f"{label:<26}"
        for n in names:
            s = series_store[n][0]
            seg = s.loc[(s.index >= a) & (s.index <= b)]
            tr = (1 + seg).prod() - 1 if len(seg) else float("nan")
            line += f"{tr*100:>12.2f}%"
        print(line)
    print()

    # save json
    out = {"common_window": [str(cs.date()), str(ce.date())],
           "cpm8_full": m8full, "common": rows,
           "inceptions": {t: str(incept[t]) for t in H.OPT3}}
    p = ROOT / "research" / "cpm_opt3_universe_results.json"
    p.write_text(json.dumps(out, indent=2, default=float))
    print(f"Saved {p}")


if __name__ == "__main__":
    main()
