"""Runner: NDX SLEEVE-LEVEL daily circuit breakers. Config table (clean + stress
+ per-crisis incl 2021 unwind + COVID-V), turnover / #triggers/yr / whipsaw%,
paired bootstrap each vs PROD (Sharpe/Sortino/CVaR), adaptive-vs-fixed-DD,
vs monthly vol-target dial, 3-seg walk-forward, sensitivity. Research only."""
from __future__ import annotations
import sys, json
import numpy as np
import pandas as pd

sys.path.insert(0, "/Users/rkautsar/personal/scripts/strategy_cpm")
from cpm_live import load_panel
from ndx_sleeve_live import load_ndx_panel
import research.cpm_ndx_circuit_breaker_harness as H
from research.cpm_bootstrap_multimetric import paired_block_bootstrap_mm

CLEAN_START = pd.Timestamp("2008-04-30")
STRESS_START = pd.Timestamp("1999-01-01")
END = pd.Timestamp("2026-05-22")

CRISES = {
    "dotcom(00-02)":   ("2000-03-01", "2002-10-31"),
    "GFC(07-09)":      ("2007-10-01", "2009-03-31"),
    "COVID-V(20)":     ("2020-02-01", "2020-04-30"),
    "2021unwind":      ("2021-02-01", "2021-05-31"),
    "2022":            ("2022-01-01", "2022-12-31"),
    "2025":            ("2025-01-01", "2025-05-22"),
}

# (label, kind, params)
VARIANTS = [
    ("PROD",              None,        None),
    # ADAPTIVE: vol-breakdown
    ("VolBrk k1.5",       "volbrk",    {"short": 10, "long": 63, "k": 1.5}),
    ("VolBrk k2.0",       "volbrk",    {"short": 10, "long": 63, "k": 2.0}),
    ("VolBrk abs50",      "volbrk",    {"short": 20, "long": 63, "abs_level": 0.50}),
    # ADAPTIVE: trend
    ("Trend MA20",        "trend",     {"ma": 20}),
    ("Trend MA50",        "trend",     {"ma": 50}),
    # FIXED-%: trailing DD
    ("TrailDD 10",        "traildd",   {"x": 0.10}),
    ("TrailDD 15",        "traildd",   {"x": 0.15}),
    ("TrailDD 20",        "traildd",   {"x": 0.20}),
    # reference: monthly vol-target dial
    ("VolTarget(monthly)", "voltarget", {"target": 0.30, "vol_window": 60}),
]

SENS = [
    ("Trend MA100",  "trend",  {"ma": 100}),
    ("VolBrk k2.5",  "volbrk", {"short": 10, "long": 63, "k": 2.5}),
    ("VolBrk s20k2", "volbrk", {"short": 20, "long": 63, "k": 2.0}),
]


def sl(ret, s, e):
    return ret.loc[pd.Timestamp(s):pd.Timestamp(e)]


def main():
    panel = load_panel(start=pd.Timestamp("1997-01-01"))
    ndx = load_ndx_panel()

    print("Building stress-window monthly history...", file=sys.stderr)
    hist, full = H.get_monthly_history(panel, ndx, STRESS_START, END)
    print(f"{len(hist)} monthly periods.", file=sys.stderr)

    rets, stats = {}, {}
    for label, kind, p in VARIANTS + SENS:
        r, st = H.run_with_breaker(hist, full, ndx, panel, STRESS_START, END,
                                   kind=kind, params=p)
        rets[label] = r
        stats[label] = st
        print(f"  {label:20} trig/yr={st['trig_per_yr']:.2f} whip={st['whipsaw_pct'] if st['whipsaw_pct']==st['whipsaw_pct'] else float('nan'):.0f} "
              f"turn={st['ann_turnover']:.2f}", file=sys.stderr)

    out = {"clean": {}, "stress": {}, "crisis": {}, "bootstrap": {},
           "walkforward": {}, "stats": stats, "sensitivity": {}}

    for win, s in [("clean", CLEAN_START), ("stress", STRESS_START)]:
        for label, *_ in VARIANTS:
            out[win][label] = H.full_metrics(sl(rets[label], s, END))
    for label, *_ in SENS:
        out["sensitivity"][label] = {**H.full_metrics(sl(rets[label], CLEAN_START, END)),
                                     **stats[label]}

    for cname, (cs, ce) in CRISES.items():
        out["crisis"][cname] = {}
        for label, *_ in VARIANTS:
            seg = sl(rets[label], cs, ce)
            if len(seg) < 5:
                out["crisis"][cname][label] = None
                continue
            m = H.full_metrics(seg)
            out["crisis"][cname][label] = {"sharpe": m["sharpe"], "maxdd": m["maxdd"],
                                           "cagr": m["cagr"]}

    # paired bootstrap each vs PROD (clean)
    prod_clean = sl(rets["PROD"], CLEAN_START, END)
    for label, *_ in VARIANTS:
        if label == "PROD":
            continue
        v = sl(rets[label], CLEAN_START, END)
        bb = paired_block_bootstrap_mm(v, prod_clean, None, B=2000, block=21, seed=42)
        out["bootstrap"][label] = {
            "dSharpe": bb["dSharpe"], "dSortino": bb["dSortino"],
            "dCVaR": bb["dCVaR"], "dMaxDD": bb["dMaxDD"],
        }
        print(f"  boot {label:20} dSharpe {bb['dSharpe']['mean']:+.3f} p>0={bb['dSharpe']['p_gt0']:.2f} "
              f"| dMaxDD {bb['dMaxDD']['mean']:+.3f} p>0={bb['dMaxDD']['p_gt0']:.2f}", file=sys.stderr)

    # walk-forward (3 seg, clean)
    clean_idx = rets["PROD"].loc[CLEAN_START:END].index
    seg_bounds = np.array_split(clean_idx, 3)
    out["walkforward"]["segments"] = []
    for si, seg in enumerate(seg_bounds):
        s0, s1 = seg[0], seg[-1]
        seg_res = {}
        for label, *_ in VARIANTS:
            m = H.full_metrics(sl(rets[label], s0, s1))
            seg_res[label] = {"sharpe": m["sharpe"], "maxdd": m["maxdd"],
                              "calmar": m["calmar"], "cagr": m["cagr"]}
        out["walkforward"]["segments"].append({
            "seg": si + 1, "start": str(s0.date()), "end": str(s1.date()),
            "metrics": seg_res})

    with open("research/cpm_ndx_circuit_breaker_results.json", "w") as f:
        json.dump(out, f, indent=2, default=str)
    print("\nWrote research/cpm_ndx_circuit_breaker_results.json", file=sys.stderr)

    # ---------------- console tables ----------------
    def ptable(title, win):
        print("\n" + "=" * 116)
        print(title)
        print("=" * 116)
        print(f"{'Variant':<20}{'Sharpe':>8}{'Sortino':>8}{'CVaR':>7}{'CAGR%':>8}{'Vol%':>7}"
              f"{'MaxDD%':>8}{'Calmar':>7}{'Martin':>7}{'Turn':>7}{'Trg/yr':>7}{'Whip%':>7}")
        print("-" * 116)
        for label, *_ in VARIANTS:
            m = out[win][label]; st = stats[label]
            wp = st['whipsaw_pct']
            print(f"{label:<20}{m['sharpe']:>8.3f}{m['sortino']:>8.3f}{m['cvar']:>7.2f}"
                  f"{m['cagr']*100:>8.2f}{m['vol']*100:>7.2f}{m['maxdd']*100:>8.2f}"
                  f"{m['calmar']:>7.2f}{m['martin']:>7.2f}{st['ann_turnover']:>7.2f}"
                  f"{st['trig_per_yr']:>7.2f}{(wp if wp==wp else 0):>7.0f}")
    ptable("CLEAN (2008-04 -> 2026-05)", "clean")
    ptable("STRESS (1999-01 -> 2026-05)", "stress")

    print("\n" + "=" * 100)
    print("PER-CRISIS MaxDD% -- CONTEXT (path-dependent)")
    print("=" * 100)
    print(f"{'Crisis':<16}" + "".join(f"{lab[:11]:>12}" for lab, *_ in VARIANTS))
    for cname in CRISES:
        row = f"{cname:<16}"
        for label, *_ in VARIANTS:
            c = out["crisis"][cname][label]
            row += f"{(c['maxdd']*100 if c else float('nan')):>12.1f}" if c else f"{'n/a':>12}"
        print(row)

    print("\nBOOTSTRAP vs PROD (clean): dSharpe / dSortino / dCVaR / dMaxDD (p>0)")
    for label, *_ in VARIANTS:
        if label == "PROD":
            continue
        b = out["bootstrap"][label]
        print(f"  {label:<20} dSh {b['dSharpe']['mean']:+.3f}(p{b['dSharpe']['p_gt0']:.2f}) "
              f"dSo {b['dSortino']['mean']:+.3f}(p{b['dSortino']['p_gt0']:.2f}) "
              f"dCV {b['dCVaR']['mean']:+.3f}(p{b['dCVaR']['p_gt0']:.2f}) "
              f"dDD {b['dMaxDD']['mean']:+.3f}(p{b['dMaxDD']['p_gt0']:.2f})")

    print("\nWALK-FORWARD (3 seg clean): Sharpe / MaxDD%")
    for sg in out["walkforward"]["segments"]:
        print(f"  Seg{sg['seg']} {sg['start']}..{sg['end']}")
        for label, *_ in VARIANTS:
            mm = sg["metrics"][label]
            print(f"    {label:<20} Sh {mm['sharpe']:.3f}  DD {mm['maxdd']*100:.1f}  Cal {mm['calmar']:.2f}")
    print("\nDone.")


if __name__ == "__main__":
    main()
