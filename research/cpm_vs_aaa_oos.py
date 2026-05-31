"""Analyst research (read-only re prod/memo; writes research/ only; NO commit).

QUESTION: How does an AAA-style benchmark fare vs CPM in AAA's POST-PAPER
out-of-sample period? AAA (Adaptive Asset Allocation, Butler/Philbrick/Gordillo/
Varadi, SSRN 2328254) paper in-sample window = 1995-2015. So 2016-01..2026-05 is
AAA's genuine OOS. Compute CPM vs Canonical-AAA over that window on the SAME
engine, apples-to-apples.

PRIMARY ENGINE (CPM vs AAA OOS + full clean): mooex T+1 MOO exact, 10 bps/side,
monthly month-end signal. Reuses research/cpm_benchmarks_proper.py building
blocks byte-identically across CPM and Canonical_AAA. Canonical AAA = 10-asset
[SPY,EZU,EWJ,EEM,IYR,RWX,IEF,TLT,DBC,GLD], top-half by 6m momentum, SLSQP
min-var weights, no canary. (mooex AAA starts ~2008 due to RWX inception + real
opens; the 2016-2026 OOS slice is fully covered.)

DEGRADATION ENGINE (AAA in-sample 1995-2015 vs OOS 2016-2026): the mooex engine
cannot reach 1995 (no real intraday opens / RWX inception 2006). AAA in-sample
and OOS are therefore taken from the monthly-close engine already computed in
research/cpm_class_significance_sanity.json (monthly TR, month-end signal, hold
next month, 10 bps/side, dynamic AAA universe with proxy splices back to 1995).
Both windows from ONE engine -> internally consistent degradation read.

Anchor sanity: CPM clean (2008-05-30..end) Sharpe == 1.1910.
"""
import sys, json
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

import cpm_benchmarks_proper as B
from cpm_live import perf_metrics, COST_BPS_PER_SIDE, RISKY_UNIVERSE

CONV = B.CONV
SEED = 20260531


def met(daily, cash, start, end):
    s = daily.loc[(daily.index >= start) & (daily.index <= end)]
    m = perf_metrics(s, cash)
    return {"sharpe": m.get("sharpe"), "cagr": m.get("cagr"), "vol": m.get("vol"),
            "maxdd": m.get("max_drawdown"), "calmar": m.get("calmar"),
            "martin": m.get("martin"), "ulcer": m.get("ulcer"),
            "n_days": int(len(s)), "start": str(s.index[0].date()) if len(s) else None,
            "end": str(s.index[-1].date()) if len(s) else None}


def main():
    end = pd.Timestamp("2026-05-22")
    ext_start = pd.Timestamp("1999-03-10")
    clean_start = pd.Timestamp("2008-05-30")
    oos_start = pd.Timestamp("2016-01-01")  # AAA post-paper OOS

    panel, intraday, overnight, end = B.build_data(ext_start, end)
    cash = panel["SHV"].ffill().pct_change().dropna()

    # CPM sleeve (mooex)
    cpm, _ = B.H.cpm_sleeve_conv(panel, intraday, overnight, ext_start, end, CONV)

    # Canonical AAA (mooex)
    aaa_cols = [t for t in B.AAA_UNIVERSE if t in panel.columns] + ["SHV", "IEF"]
    aaa_close = panel[sorted(set(aaa_cols))]
    aaa_daily = aaa_close.ffill().pct_change()
    rwx_fv = panel["RWX"].first_valid_index()
    aaa_ext_start = max(ext_start, (rwx_fv + pd.DateOffset(months=13)) if rwx_fv is not None else ext_start)
    aaa, _ = B.run_wf(aaa_close, aaa_daily, intraday, overnight, aaa_ext_start, end,
                      B.make_canonical_aaa_wf(aaa_close, aaa_daily))

    # 60/40 for context
    bm_cols = sorted(set(RISKY_UNIVERSE + ["SPY", "IEF", "SHV"]) & set(panel.columns))
    bm_close = panel[bm_cols]
    bm_daily = bm_close.ffill().pct_change()
    sixty, _ = B.run_wf(bm_close, bm_daily, intraday, overnight, ext_start, end, B.make_6040_wf(bm_close))

    out = {"meta": {
        "primary_engine": "mooex T+1 MOO, 10bps/side, monthly ME signal (cpm_benchmarks_proper)",
        "degradation_engine": "monthly-close TR, 10bps/side (cpm_class_significance_sanity.json)",
        "panel_end": str(end.date()), "aaa_universe": B.AAA_UNIVERSE,
        "aaa_mooex_start": str(aaa_ext_start.date()),
        "rwx_first_valid": str(rwx_fv.date()) if rwx_fv is not None else None,
        "windows": {"clean": [str(clean_start.date()), str(end.date())],
                    "aaa_oos": [str(oos_start.date()), str(end.date())]}}}

    # anchor
    out["anchor"] = {"cpm_clean": met(cpm, cash, clean_start, end)}

    # PRIMARY: mooex CPM vs AAA over OOS and clean
    out["mooex"] = {}
    for win, st in [("clean", clean_start), ("aaa_oos", oos_start)]:
        out["mooex"][win] = {
            "CPM": met(cpm, cash, st, end),
            "Canonical_AAA": met(aaa, cash, st, end),
            "60/40": met(sixty, cash, st, end)}
        c = out["mooex"][win]["CPM"]; a = out["mooex"][win]["Canonical_AAA"]
        out["mooex"][win]["CPM_minus_AAA"] = {
            "dSharpe": c["sharpe"] - a["sharpe"],
            "dCAGR": c["cagr"] - a["cagr"],
            "dCalmar": c["calmar"] - a["calmar"],
            "dMartin": c["martin"] - a["martin"]}

    # paired bootstrap CPM-minus-AAA Sharpe over OOS (daily, block=21)
    cw = cpm.loc[(cpm.index >= oos_start) & (cpm.index <= end)]
    aw = aaa.loc[(aaa.index >= oos_start) & (aaa.index <= end)]
    out["mooex"]["aaa_oos"]["boot_dSharpe_CPM_minus_AAA"] = B.paired_block_bootstrap(
        cw, aw, block=21, B=3000, seed=SEED)

    # DEGRADATION: AAA in-sample vs OOS from monthly-close engine json
    sig = json.loads((HERE / "cpm_class_significance_sanity.json").read_text())
    # locate AAA per-window metrics in that json
    out["aaa_degradation_monthlyclose"] = _extract_aaa_degradation(sig)

    (HERE / "cpm_vs_aaa_oos.json").write_text(json.dumps(out, indent=2, default=float))

    # ---- console ----
    print(f"Panel end {end.date()}  AAA mooex start {aaa_ext_start.date()} (RWX {rwx_fv.date()})")
    a = out["anchor"]["cpm_clean"]
    print(f"\nANCHOR CPM clean Sharpe={a['sharpe']:.4f} (expect 1.1910) MaxDD={a['maxdd']*100:.2f}% Calmar={a['calmar']:.4f}\n")

    for win, label in [("clean", "FULL CLEAN 2008-05 -> end"),
                       ("aaa_oos", "AAA POST-PAPER OOS 2016-01 -> end")]:
        d = out["mooex"][win]
        print("=" * 78)
        print(f"{label}  [mooex T+1 MOO]")
        print("=" * 78)
        print(f"{'series':<16}{'Sharpe':>8}{'CAGR':>8}{'Vol':>7}{'MaxDD':>9}{'Calmar':>8}{'Martin':>8}{'n_d':>6}")
        for nm in ["CPM", "Canonical_AAA", "60/40"]:
            m = d[nm]
            print(f"{nm:<16}{m['sharpe']:>8.4f}{m['cagr']*100:>7.2f}%{m['vol']*100:>6.2f}%"
                  f"{m['maxdd']*100:>8.2f}%{m['calmar']:>8.4f}{m['martin']:>8.4f}{m['n_days']:>6}")
        dm = d["CPM_minus_AAA"]
        print(f"  CPM - AAA: dSharpe={dm['dSharpe']:+.4f}  dCAGR={dm['dCAGR']*100:+.2f}%  "
              f"dCalmar={dm['dCalmar']:+.4f}  dMartin={dm['dMartin']:+.4f}")
        if "boot_dSharpe_CPM_minus_AAA" in d:
            b = d["boot_dSharpe_CPM_minus_AAA"]
            print(f"  boot dSharpe point={b['point']:+.4f} 95%CI=[{b['lo']:+.4f},{b['hi']:+.4f}] "
                  f"incl0={b['includes_zero']} (n={b['n']})")
        print()

    print("=" * 78)
    print("AAA DEGRADATION (monthly-close engine; AAA's own paper windows)")
    print("=" * 78)
    deg = out["aaa_degradation_monthlyclose"]
    for k in ["in_sample", "paper_oos"]:
        w = deg[k]
        print(f"{k:<12} {w['range']:<24} Sharpe={w['sharpe']:.4f}  Calmar={w['calmar']:.4f}  MaxDD={w['maxdd']*100:.2f}%")
    print(f"DELTA OOS - in-sample: dSharpe={deg['delta']['dSharpe']:+.4f}  dCalmar={deg['delta']['dCalmar']:+.4f}")
    print("\nDONE -> cpm_vs_aaa_oos.json")


def _extract_aaa_degradation(sig):
    """AAA in-sample (1995-2015) vs paper-oos (2016-2026) from the class-sig json
    standalone.AAA blocks (monthly-close engine, proxy splices to 1995)."""
    a = sig["standalone"]["AAA"]
    def grab(key):
        b = a[key]["strategy"]
        rng = " .. ".join(a[key]["window"])
        return {"range": rng, "sharpe": b["sharpe"], "calmar": b["calmar"],
                "maxdd": b["maxdd"], "cagr": b["cagr"], "n_months": b.get("n_months")}
    res = {"source": "cpm_class_significance_sanity.json standalone.AAA",
           "note": "monthly-close engine, dynamic AAA universe, proxy splices to 1995",
           "in_sample": grab("in_sample"), "paper_oos": grab("paper_oos"),
           "common18y": grab("common18y")}
    res["delta"] = {"dSharpe": res["paper_oos"]["sharpe"] - res["in_sample"]["sharpe"],
                    "dCalmar": res["paper_oos"]["calmar"] - res["in_sample"]["calmar"]}
    return res


if __name__ == "__main__":
    main()
