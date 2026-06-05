"""Runner: NDX monthly-set intramonth vol stop-loss. Produces config table
(clean+stress+per-crisis), turnover/#stops/whipsaw, paired bootstrap vs PROD,
stop-level sensitivity, 3-seg walk-forward. Research only; no prod edits."""
from __future__ import annotations
import sys, json
import numpy as np
import pandas as pd

sys.path.insert(0, "/Users/rkautsar/personal/scripts/strategy_cpm")
from cpm_live import load_panel
from ndx_sleeve_live import load_ndx_panel
import research.cpm_ndx_stoploss_harness as H
from research.cpm_bootstrap_multimetric import paired_block_bootstrap_mm

CLEAN_START = pd.Timestamp("2008-04-30")
STRESS_START = pd.Timestamp("1999-01-01")
END = pd.Timestamp("2026-05-22")

CRISES = {
    "dotcom(00-02)": ("2000-03-01", "2002-10-31"),
    "GFC(07-09)":    ("2007-10-01", "2009-03-31"),
    "COVID(20)":     ("2020-02-01", "2020-04-30"),
    "2022":          ("2022-01-01", "2022-12-31"),
    "2025":          ("2025-01-01", "2025-05-22"),
}

# (label, kind, k, z)
VARIANTS = [
    ("PROD (no stop)",        None,       None, None),
    ("VolMult k=1.5",         "vol_mult", 1.5,  None),
    ("VolMult k=2.0",         "vol_mult", 2.0,  None),
    ("VolMult k=3.0",         "vol_mult", 3.0,  None),
    ("ExpBand z=1",           "exp_band", None, 1.0),
    ("ExpBand z=2",           "exp_band", None, 2.0),
]


def slice_ret(ret, s, e):
    return ret.loc[pd.Timestamp(s):pd.Timestamp(e)]


def main():
    panel = load_panel(start=pd.Timestamp("1993-01-01"))
    ndx = load_ndx_panel()

    print("Building stress-window monthly history (covers clean too)...")
    hist, full_panel = H.get_monthly_history(panel, ndx, STRESS_START, END)
    print(f"{len(hist)} monthly periods.")

    # Run each variant once over the FULL stress window; slice for clean/crisis.
    rets = {}
    stats = {}
    for label, kind, k, z in VARIANTS:
        ret, st = H.run_with_stops(hist, full_panel, ndx, STRESS_START, END,
                                   kind=kind, k=k, z=z)
        rets[label] = ret
        stats[label] = st
        print(f"  ran {label}: stops/yr={st['stops_per_yr']:.2f} whipsaw={st['whipsaw_pct']:.0f}% turn={st['ann_turnover']:.2f}")

    # ---------- config table: clean + stress ----------
    out = {"clean": {}, "stress": {}, "crisis": {}, "bootstrap": {},
           "walkforward": {}, "stats": stats}
    for win, s in [("clean", CLEAN_START), ("stress", STRESS_START)]:
        for label, *_ in VARIANTS:
            m = H.full_metrics(slice_ret(rets[label], s, END))
            out[win][label] = m

    # ---------- per-crisis (context) ----------
    for cname, (cs, ce) in CRISES.items():
        out["crisis"][cname] = {}
        for label, *_ in VARIANTS:
            seg = slice_ret(rets[label], cs, ce)
            if len(seg) < 5:
                out["crisis"][cname][label] = None
                continue
            m = H.full_metrics(seg)
            out["crisis"][cname][label] = {"sharpe": m["sharpe"], "maxdd": m["maxdd"],
                                            "cagr": m["cagr"]}

    # ---------- paired bootstrap vs PROD (clean) ----------
    prod_clean = slice_ret(rets["PROD (no stop)"], CLEAN_START, END)
    for label, *_ in VARIANTS:
        if label == "PROD (no stop)":
            continue
        v = slice_ret(rets[label], CLEAN_START, END)
        bb = paired_block_bootstrap_mm(v, prod_clean, None, B=2000, block=21, seed=42)
        out["bootstrap"][label] = {
            "dSharpe": bb["dSharpe"], "dSortino": bb["dSortino"],
            "dCVaR": bb["dCVaR"], "dMaxDD": bb["dMaxDD"],
        }
        print(f"  bootstrap {label} vs PROD: dSharpe {bb['dSharpe']['mean']:+.3f} "
              f"[{bb['dSharpe']['ci_lo']:+.3f},{bb['dSharpe']['ci_hi']:+.3f}] p>0={bb['dSharpe']['p_gt0']:.2f}")

    # ---------- 3-seg walk-forward (clean window) ----------
    clean_idx = rets["PROD (no stop)"].loc[CLEAN_START:END].index
    seg_bounds = np.array_split(clean_idx, 3)
    out["walkforward"]["segments"] = []
    for si, seg in enumerate(seg_bounds):
        s0, s1 = seg[0], seg[-1]
        seg_res = {}
        for label, *_ in VARIANTS:
            m = H.full_metrics(slice_ret(rets[label], s0, s1))
            seg_res[label] = {"sharpe": m["sharpe"], "maxdd": m["maxdd"], "calmar": m["calmar"]}
        # winner by calmar among stop variants vs prod
        out["walkforward"]["segments"].append({
            "seg": si + 1, "start": str(s0.date()), "end": str(s1.date()),
            "metrics": seg_res,
        })

    with open("research/cpm_ndx_stoploss_results.json", "w") as f:
        json.dump(out, f, indent=2, default=str)
    print("\nWrote research/cpm_ndx_stoploss_results.json")

    # ---------- console tables ----------
    def ptable(title, win):
        print("\n" + "=" * 104)
        print(title)
        print("=" * 104)
        print(f"{'Variant':<20}{'Sharpe':>8}{'Sortino':>8}{'CVaR':>7}{'CAGR%':>8}{'Vol%':>7}"
              f"{'MaxDD%':>8}{'Calmar':>7}{'Martin':>7}{'Turn':>7}{'Stp/yr':>7}{'Whip%':>7}")
        print("-" * 104)
        for label, *_ in VARIANTS:
            m = out[win][label]; st = stats[label]
            print(f"{label:<20}{m['sharpe']:>8.3f}{m['sortino']:>8.3f}{m['cvar']:>7.2f}"
                  f"{m['cagr']*100:>8.2f}{m['vol']*100:>7.2f}{m['maxdd']*100:>8.2f}"
                  f"{m['calmar']:>7.2f}{m['martin']:>7.2f}{st['ann_turnover']:>7.2f}"
                  f"{st['stops_per_yr']:>7.2f}{st['whipsaw_pct']:>7.0f}")
    ptable("CLEAN (2008-04 -> 2026-05)", "clean")
    ptable("STRESS (1999-01 -> 2026-05)", "stress")

    print("\n" + "=" * 80)
    print("PER-CRISIS (Sharpe / MaxDD%) -- CONTEXT (path-dependent)")
    print("=" * 80)
    hdr = f"{'Crisis':<16}" + "".join(f"{lab.split('(')[0][:11]:>13}" for lab, *_ in VARIANTS)
    print(hdr)
    for cname in CRISES:
        row = f"{cname:<16}"
        for label, *_ in VARIANTS:
            c = out["crisis"][cname][label]
            row += f"{(c['maxdd']*100 if c else float('nan')):>13.1f}" if c else f"{'n/a':>13}"
        print(row + "   <- MaxDD%")
    print("\nWrote console tables. Done.")


if __name__ == "__main__":
    main()
