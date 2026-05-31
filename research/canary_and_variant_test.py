#!/usr/bin/env python3
"""
STRICTER AND-canary extension of research/canary_variant_test.py.

Adds HYG-AND-TIP (both 13612U > 0 to be risk-on) alongside the three existing
variants and re-runs both sleeves, clean + ext, at sleeve and 60/40 blend level.

Variants tested (canary toggled ONLY; everything else held at production):
  - tip        : TIP-only           (TIP 13612U > 0)
  - hygortip   : HYG-OR-TIP          (any positive; PRODUCTION)
  - hygandtip  : HYG-AND-TIP         (BOTH positive; NEW, stricter)
  - none       : no canary gate      (always risk-on)

Faithful execution = mooex (same framework producing the production anchor:
  CPM clean Sharpe 1.1910, BULL 1.0813, 60/40 blend 1.2485).

Reuses helpers from canary_variant_test.py (build_synthetic_tip, run_cpm,
run_bull, metrics, win, period_*, block_bootstrap_sharpe_diff, canary_signal_table).

Read-only re production. Writes to research/ only. No production/memo edits, no commit.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import cpm_live
import bull_qqq_live
import research.exec_lag_moo_validation_2026_05_30 as H
import research.canary_variant_test as cvt
from cpm_live import load_panel, perf_metrics, sig_13612U

CLEAN = cvt.CLEAN
EXT = cvt.EXT
END = cvt.END
CONV = cvt.CONV
ANCHOR = cvt.ANCHOR

MODES = ["tip", "hygortip", "hygandtip", "none"]
TIP_MODES = ["tip", "hygortip", "hygandtip"]  # canary uses TIP -> synthetic-TIP variant relevant


# ---------------------------------------------------------------------------
# Canary setters that ALSO drive CANARY_RULE (any_positive vs all_positive).
# ---------------------------------------------------------------------------
def set_cpm(mode):
    if mode == "none":
        H.compute_target_weights = cvt.cpm_compute_nocanary
        return
    H.compute_target_weights = cvt._PROD_CPM
    if mode == "tip":
        cpm_live.CANARY_ASSETS = ["TIP"]; cpm_live.CANARY_RULE = "any_positive"
    elif mode == "hygortip":
        cpm_live.CANARY_ASSETS = ["HYG", "TIP"]; cpm_live.CANARY_RULE = "any_positive"
    elif mode == "hygandtip":
        cpm_live.CANARY_ASSETS = ["HYG", "TIP"]; cpm_live.CANARY_RULE = "all_positive"


def set_bull(mode):
    if mode == "none":
        bull_qqq_live._macro_gate = cvt._bull_macro_always_on
        return
    bull_qqq_live._macro_gate = cvt._PROD_MACRO
    if mode == "tip":
        bull_qqq_live.CANARY_ASSETS = ["TIP"]; bull_qqq_live.CANARY_RULE = "any_positive"
    elif mode == "hygortip":
        bull_qqq_live.CANARY_ASSETS = ["HYG", "TIP"]; bull_qqq_live.CANARY_RULE = "any_positive"
    elif mode == "hygandtip":
        bull_qqq_live.CANARY_ASSETS = ["HYG", "TIP"]; bull_qqq_live.CANARY_RULE = "all_positive"


def reset():
    cvt.reset_cpm_canary(); cvt.reset_bull_canary()
    cpm_live.CANARY_RULE = "any_positive"
    bull_qqq_live.CANARY_RULE = "any_positive"


# ---------------------------------------------------------------------------
# Canary-gate defensive-month accounting (pure signal-driven; trend/vol common).
# ---------------------------------------------------------------------------
def defensive_counts(sig_tbl, start, end):
    """For each variant, count months the CANARY forces defensive within window.
    Also report disagreement sets vs HYG-OR-TIP and TIP-only."""
    rows = [me for me in sig_tbl.index
            if start <= me <= end
            and pd.notna(sig_tbl.loc[me, "hyg"]) and pd.notna(sig_tbl.loc[me, "tip"])]
    n = len(rows)

    def defs(predicate):
        return [me for me in rows if predicate(sig_tbl.loc[me, "hyg"], sig_tbl.loc[me, "tip"])]

    d_tip = defs(lambda h, t: t <= 0)
    d_or = defs(lambda h, t: (h <= 0) and (t <= 0))
    d_and = defs(lambda h, t: (h <= 0) or (t <= 0))
    # disagreement sets
    and_minus_or = [me for me in d_and if me not in set(d_or)]   # exactly one positive
    and_minus_tip = [me for me in d_and if me not in set(d_tip)]  # tip>0 & hyg<=0
    return {
        "n_months": n,
        "defensive_months": {
            "tip": len(d_tip), "hygortip": len(d_or), "hygandtip": len(d_and),
        },
        "extra_defensive_AND_vs_OR": len(and_minus_or),
        "extra_defensive_AND_vs_TIP": len(and_minus_tip),
        "AND_extra_vs_OR_months": [str(me.date()) for me in and_minus_or],
        "AND_extra_vs_TIP_months": [str(me.date()) for me in and_minus_tip],
    }


def fwd_spy_in_months(spy_daily, months):
    """Realized next-~21-trading-day SPY return for each month-end in list."""
    out = []
    for me in months:
        seg = spy_daily.loc[spy_daily.index > me].iloc[:21]
        if len(seg):
            out.append(float((1.0 + seg).prod() - 1.0))
    if not out:
        return {"n": 0}
    arr = np.array(out)
    return {"n": len(arr),
            "mean_pct": round(float(arr.mean()) * 100, 3),
            "median_pct": round(float(np.median(arr)) * 100, 3),
            "vol_pct": round(float(arr.std(ddof=0)) * 100, 3),
            "pct_negative": round(float((arr < 0).mean()) * 100, 1)}


# ===========================================================================
def main():
    print("Loading panel ...")
    panel = load_panel(start=pd.Timestamp("1995-01-01"), end=END)
    end = min(END, panel.index[-1])
    cash = panel["SHV"].ffill().pct_change().dropna()
    od, cy = H.load_open_close()
    intr = (cy / od - 1.0).reindex(panel.index)
    on = (od / cy.shift(1) - 1.0).reindex(panel.index)
    spy_daily = panel["SPY"].ffill().pct_change()

    out = {"windows": {"clean": [str(CLEAN.date()), str(end.date())],
                       "ext": [str(EXT.date()), str(end.date())]},
           "conv": CONV, "anchor": ANCHOR, "variants": MODES,
           "variant_defs": {
               "tip": "TIP 13612U > 0",
               "hygortip": "HYG OR TIP positive (production)",
               "hygandtip": "HYG AND TIP both positive (NEW, stricter)",
               "none": "no canary gate (always risk-on)"}}

    # ---- synthetic TIP (ext de-bias; canary-only) ----
    print("Building CPI-aware synthetic TIP ...")
    syn_daily, syn_price_m, cpi_infl = cvt.build_synthetic_tip(panel)
    out["synthetic_tip"] = {
        "construction": "monthly syn TIPS total return = IEF nominal total return + realized monthly CPI(CPIAUCSL) inflation; cumulated to price index; canary-only use",
        "validation": cvt.validate_synthetic(panel, syn_price_m),
    }
    panel_syn = panel.copy()
    panel_syn["TIP"] = syn_daily

    # ---- ANCHOR GATE ----
    print("Anchor gate ...")
    reset()
    cpm_p = cvt.run_cpm(panel, intr, on, EXT, end)
    bull_p = cvt.run_bull(panel, intr, on, EXT, end)
    common = cpm_p.index.intersection(bull_p.index)
    cpm_p = cpm_p.reindex(common); bull_p = bull_p.reindex(common)
    blend_p = 0.6 * cpm_p + 0.4 * bull_p
    a_cpm = cvt.metrics(cvt.win(cpm_p, CLEAN, end), cash)["sharpe"]
    a_bull = cvt.metrics(cvt.win(bull_p, CLEAN, end), cash)["sharpe"]
    a_blend = cvt.metrics(cvt.win(blend_p, CLEAN, end), cash)["sharpe"]
    anchor_ok = (abs(a_cpm - ANCHOR["cpm"]) < 5e-4 and abs(a_bull - ANCHOR["bull"]) < 5e-4
                 and abs(a_blend - ANCHOR["blend"]) < 5e-4)
    out["anchor_check"] = {"cpm": a_cpm, "bull": a_bull, "blend": a_blend, "ok": anchor_ok}
    print(f"  anchor cpm={a_cpm} bull={a_bull} blend={a_blend} OK={anchor_ok}")
    assert anchor_ok, "ANCHOR MISMATCH - aborting"

    # ---- CPM sleeve variants ----
    print("CPM sleeve variants ...")
    cpm_series = {}
    out["cpm_sleeve"] = {}
    for mode in MODES:
        set_cpm(mode); cvt.reset_bull_canary(); bull_qqq_live.CANARY_RULE = "any_positive"
        s = cvt.run_cpm(panel, intr, on, EXT, end)
        cpm_series[(mode, "real")] = s
        rec = {"clean": cvt.metrics(cvt.win(s, CLEAN, end), cash),
               "ext_prodTIP": cvt.metrics(cvt.win(s, EXT, end), cash)}
        if mode in TIP_MODES:
            s_syn = cvt.run_cpm(panel_syn, intr, on, EXT, end)
            cpm_series[(mode, "syn")] = s_syn
            rec["ext_synTIP"] = cvt.metrics(cvt.win(s_syn, EXT, end), cash)
        out["cpm_sleeve"][mode] = rec
    reset()

    # ---- BULL sleeve variants ----
    print("BULL sleeve variants ...")
    bull_series = {}
    out["bull_sleeve"] = {}
    for mode in MODES:
        cvt.reset_cpm_canary(); cpm_live.CANARY_RULE = "any_positive"; set_bull(mode)
        s = cvt.run_bull(panel, intr, on, EXT, end)
        bull_series[(mode, "real")] = s
        rec = {"clean": cvt.metrics(cvt.win(s, CLEAN, end), cash),
               "ext_prodTIP": cvt.metrics(cvt.win(s, EXT, end), cash)}
        if mode in TIP_MODES:
            s_syn = cvt.run_bull(panel_syn, intr, on, EXT, end)
            bull_series[(mode, "syn")] = s_syn
            rec["ext_synTIP"] = cvt.metrics(cvt.win(s_syn, EXT, end), cash)
        out["bull_sleeve"][mode] = rec
    reset()

    # ---- 60/40 blend variants ----
    print("60/40 blend variants ...")
    out["blend_6040"] = {}
    # joint (both sleeves same canary), real TIP
    for mode in MODES:
        c = cpm_series[(mode, "real")]; b = bull_series[(mode, "real")]
        ci = c.index.intersection(b.index)
        bl = 0.6 * c.reindex(ci) + 0.4 * b.reindex(ci)
        out["blend_6040"][f"joint_{mode}"] = {
            "clean": cvt.metrics(cvt.win(bl, CLEAN, end), cash),
            "ext_prodTIP": cvt.metrics(cvt.win(bl, EXT, end), cash)}
    # asymmetric: every CPM x BULL combo, clean window (find best asymmetric)
    out["blend_asymmetric"] = {}
    best = None
    for cm in MODES:
        for bm in MODES:
            c = cpm_series[(cm, "real")]; b = bull_series[(bm, "real")]
            ci = c.index.intersection(b.index)
            bl = 0.6 * c.reindex(ci) + 0.4 * b.reindex(ci)
            mc = cvt.metrics(cvt.win(bl, CLEAN, end), cash)
            key = f"cpm_{cm}__bull_{bm}"
            out["blend_asymmetric"][key] = mc
            if best is None or mc["sharpe"] > best[1]["sharpe"]:
                best = (key, mc)
    out["blend_asymmetric_best_by_sharpe"] = {"combo": best[0], "metrics": best[1]}
    # also best by calmar
    best_cal = max(out["blend_asymmetric"].items(), key=lambda kv: kv[1]["calmar"])
    out["blend_asymmetric_best_by_calmar"] = {"combo": best_cal[0], "metrics": best_cal[1]}

    # ---- defensive-month accounting (canary-gate level) ----
    print("Defensive-month accounting ...")
    sig_real = cvt.canary_signal_table(panel, "TIP")
    sig_syn = cvt.canary_signal_table(panel_syn, "TIP")
    out["defensive_accounting"] = {
        "definition": "canary-forced defensive months: tip(t<=0); hygortip(h<=0 & t<=0); hygandtip(h<=0 | t<=0). trend/vol gates common across variants.",
        "clean_realTIP": defensive_counts(sig_real, CLEAN, end),
        "ext_realTIP": defensive_counts(sig_real, EXT, end),
        "ext_synTIP": defensive_counts(sig_syn, EXT, end),
    }
    # SPY forward return in the AND-extra months (whipsaw vs protection)
    dc = out["defensive_accounting"]["clean_realTIP"]
    and_vs_or_months = [pd.Timestamp(d) for d in dc["AND_extra_vs_OR_months"]]
    and_vs_tip_months = [pd.Timestamp(d) for d in dc["AND_extra_vs_TIP_months"]]
    out["defensive_accounting"]["AND_extra_months_spy_fwd_clean"] = {
        "AND_vs_OR (HYG-AND-TIP sits out, HYG-OR-TIP risk-on)": fwd_spy_in_months(spy_daily, and_vs_or_months),
        "AND_vs_TIP (HYG-AND-TIP sits out, TIP-only risk-on)": fwd_spy_in_months(spy_daily, and_vs_tip_months),
        "note": "mean<0 / high pct_negative => AND avoided losses (protection); mean>0 => AND gave up gains (whipsaw)",
    }

    # ---- stagflation episodes (real-data, clean window) ----
    print("Stagflation episodes ...")
    episodes = {
        "2022_full": ("2022-01-01", "2022-12-31"),
        "2022H1_worst": ("2022-01-01", "2022-06-30"),
        "2021H2_runup": ("2021-07-01", "2021-12-31"),
        "rate_stress_2022_2023": ("2022-01-01", "2023-10-31"),
    }
    stag = {}
    for ename, (s0, s1) in episodes.items():
        s0t, s1t = pd.Timestamp(s0), pd.Timestamp(s1)
        rec = {}
        for sname, smap in [("cpm", cpm_series), ("bull", bull_series)]:
            for mode in TIP_MODES:
                ser = smap[(mode, "real")]
                rec[f"{sname}_{mode}"] = {
                    "ret_pct": round(cvt.period_total_return(ser, s0t, s1t) * 100, 2),
                    "maxdd_pct": round(cvt.period_maxdd(ser, s0t, s1t) * 100, 2)}
        for mode in TIP_MODES:
            bl = 0.6 * cpm_series[(mode, "real")] + 0.4 * bull_series[(mode, "real")]
            rec[f"blend_{mode}"] = {
                "ret_pct": round(cvt.period_total_return(bl, s0t, s1t) * 100, 2),
                "maxdd_pct": round(cvt.period_maxdd(bl, s0t, s1t) * 100, 2)}
        signs = [{"month": str(me.date()),
                  "hyg": round(float(sig_real.loc[me, "hyg"]), 4),
                  "tip": round(float(sig_real.loc[me, "tip"]), 4)}
                 for me in sig_real.index if s0t <= me <= s1t
                 and pd.notna(sig_real.loc[me, "hyg"]) and pd.notna(sig_real.loc[me, "tip"])]
        rec["canary_signs"] = signs
        stag[ename] = rec
    out["stagflation"] = stag

    # ---- bootstrap noise (clean) ----
    print("Bootstrap noise ...")
    bb = cvt.block_bootstrap_sharpe_diff
    out["bootstrap_clean"] = {}
    for sname, smap in [("cpm", cpm_series), ("bull", bull_series)]:
        out["bootstrap_clean"][f"{sname}_AND_vs_OR"] = bb(
            cvt.win(smap[("hygandtip", "real")], CLEAN, end),
            cvt.win(smap[("hygortip", "real")], CLEAN, end))
        out["bootstrap_clean"][f"{sname}_AND_vs_TIP"] = bb(
            cvt.win(smap[("hygandtip", "real")], CLEAN, end),
            cvt.win(smap[("tip", "real")], CLEAN, end))
    blA = 0.6 * cpm_series[("hygandtip", "real")] + 0.4 * bull_series[("hygandtip", "real")]
    blO = 0.6 * cpm_series[("hygortip", "real")] + 0.4 * bull_series[("hygortip", "real")]
    blT = 0.6 * cpm_series[("tip", "real")] + 0.4 * bull_series[("tip", "real")]
    out["bootstrap_clean"]["blend_AND_vs_OR"] = bb(cvt.win(blA, CLEAN, end), cvt.win(blO, CLEAN, end))
    out["bootstrap_clean"]["blend_AND_vs_TIP"] = bb(cvt.win(blA, CLEAN, end), cvt.win(blT, CLEAN, end))

    # ---- write JSON ----
    def _ser(o):
        if isinstance(o, (np.bool_,)):
            return bool(o)
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, (np.floating,)):
            return float(o)
        raise TypeError(str(type(o)))
    OUT_JSON = ROOT / "research" / "canary_and_variant_findings.json"
    OUT_JSON.write_text(json.dumps(out, indent=2, default=_ser))
    print(f"Wrote {OUT_JSON}")
    return out


if __name__ == "__main__":
    main()
