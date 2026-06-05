#!/usr/bin/env python3
"""Rebaseline reproduction: authoritative PROD blend + sleeve metrics on the
canonical code path. Point-estimates only. No optimization.

Runs build_artifacts() (the dashboard's single source of truth) on:
  - frozen in-repo panel (live=False -> pinned to EVAL_END 2026-05-22)
  - live-refreshed panel (live=True, end=today)
for the README clean window (2008-05-30) and stress window (1999-03-10).
"""
import sys, json
from pathlib import Path
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import cpm_live as C
from cpm_live import load_panel, perf_metrics, EVAL_END
import build_dashboard as B
from ndx_sleeve_live import load_ndx_panel

CLEAN = pd.Timestamp("2008-05-30")
STRESS = pd.Timestamp("1999-03-10")

def m(daily, cash):
    if daily is None or daily.empty:
        return {}
    return perf_metrics(daily, cash)

def fmt(d):
    if not d: return "(empty)"
    return (f"Sharpe {d['sharpe']:.4f} | ExSharpe {d.get('excess_sharpe',float('nan')):.4f} | "
            f"CAGR {d['cagr']*100:.2f}% | Vol {d['vol']*100:.2f}% | "
            f"MaxDD {d['max_drawdown']*100:.2f}% | Calmar {d['calmar']:.4f} | Martin {d['martin']:.4f}")

def run_mode(live, label):
    panel_start = min(CLEAN - pd.DateOffset(years=20), pd.Timestamp("1995-01-01"))
    if live:
        end_req = pd.Timestamp.today().normalize()
        panel = load_panel(start=panel_start, end=end_req, live=True)
    else:
        panel = load_panel(start=panel_start, end=None, live=False)  # pins to EVAL_END
    panel_last = panel.index[-1]
    cash = panel["SHV"].ffill().pct_change().dropna()
    ndx_panel = load_ndx_panel()
    out = {"label": label, "panel_last": str(panel_last.date())}
    print(f"\n{'='*78}\n{label}: panel {panel.index[0].date()} -> {panel_last.date()}  (EVAL_END={EVAL_END.date()})\n{'='*78}")

    for win_name, wstart, wend in [
        ("CLEAN_README_END", CLEAN, pd.Timestamp("2026-05-22")),
        ("CLEAN_TO_PANEL_END", CLEAN, panel_last),
        ("STRESS_README_END", STRESS, pd.Timestamp("2026-05-22")),
        ("STRESS_TO_PANEL_END", STRESS, panel_last),
    ]:
        wend = min(wend, panel_last)
        art = B.build_artifacts(panel, ndx_panel, wstart, wend, include_records=False)
        blend = m(art.blend, cash)
        cpm = m(art.cpm, cash)
        bull = m(art.bull, cash)
        ndx = m(art.ndx, cash)
        # benchmarks for headline (only clean->README end matters most)
        spy = panel["SPY"].ffill().pct_change().loc[wstart:wend].fillna(0.0)
        qqq = panel["QQQ"].ffill().pct_change().loc[wstart:wend].fillna(0.0)
        bb4 = B.bench_bb4_blend(panel, wstart, wend)
        # BB1 = 60% B2 + 40% B3
        b2 = B.bench_aaa_tip(panel, wstart, wend)
        b3 = B.bench_haa_simple(panel, wstart, wend, asset="SPY")
        common = b2.index.intersection(b3.index)
        bb1 = (0.60*b2.reindex(common).fillna(0)+0.40*b3.reindex(common).fillna(0))
        print(f"\n--- {win_name}  ({wstart.date()} -> {wend.date()}, {(wend-wstart).days/365.25:.2f}y) ---")
        print(f"  PROD blend : {fmt(blend)}")
        print(f"  CPM        : {fmt(cpm)}")
        print(f"  BULL       : {fmt(bull)}")
        print(f"  NDX        : {fmt(ndx)}")
        print(f"  BB4        : {fmt(m(bb4,cash))}")
        print(f"  BB1        : {fmt(m(bb1,cash))}")
        print(f"  SPY bh     : {fmt(m(spy,cash))}")
        print(f"  QQQ bh     : {fmt(m(qqq,cash))}")
        out[win_name] = {
            "window": [str(wstart.date()), str(wend.date())],
            "PROD": blend, "CPM": cpm, "BULL": bull, "NDX": ndx,
            "BB4": m(bb4,cash), "BB1": m(bb1,cash),
            "SPY": m(spy,cash), "QQQ": m(qqq,cash),
        }
    return out

if __name__ == "__main__":
    results = {}
    results["frozen"] = run_mode(False, "FROZEN (live=False, in-repo data)")
    results["live"] = run_mode(True, "LIVE (live=True, fresh fetch)")
    with open(ROOT / "research" / "rebaseline_repro.json", "w") as f:
        json.dump(results, f, indent=2, default=str)
    print("\nWROTE research/rebaseline_repro.json")
