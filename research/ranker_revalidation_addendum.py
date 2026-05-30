# -*- coding: utf-8 -*-
"""Throwaway research (analyst; read-only re production; no production files changed, no commit).
ADDENDUM to ranker_revalidation_final_spec.py. Two new analyses, SAME final spec
(inverse-vol, strict-3 partial-safe, cov 504d, mooex T+1 MOO exact, 10 bps):

(1) WIDER POOL for the sub-selection. C(4,3)=4 is a tiny choice set. Test K in
    {4,5,6}. For each K compare:
      A) top-K -> min-var-3-subset -> inverse-vol   (sub-select; base spec at K)
      B) top-K -> inverse-vol ALL K (IVk; no sub-selection)
    Report delta = A - B per K (clean+ext). Does the sub-selection edge GROW as
    the pool widens (C(4,3)=4, C(5,3)=10, C(6,3)=20)? (ranker = production vol-Faber)

(2) RANKER x SUB-SELECTION REDUNDANCY 2x2 at K=4:
      {vol-Faber, plain-Faber} x {min-var-3-subset, weight-all-4 (IV4)}.
    Does min-var sub-selection add MORE under plain-Faber than under vol-Faber?
    Report 4 cells (Sharpe/Calmar/MaxDD clean+ext) + the interaction.

Self-contained parametrized weight fn (subselect toggle + plain-faber branch);
base config (vol-Faber, K=4, subselect) anchor-gated to the FINAL anchor
clean 1.2667/-12.66%/1.1306, ext 1.2349/-15.18%/0.9119.

Writes research/ranker_revalidation_addendum.json.
"""
from __future__ import annotations
import sys, json
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

import exec_lag_moo_validation_2026_05_30 as H
from cpm_live import (
    load_panel, faber_sma_xs, sig_13612U, best_safe, inv_vol_weights,
    compute_target_weights, RISKY_UNIVERSE, SAFE_POOL, CANARY_ASSETS,
    DEFAULT_CASH, COST_BPS_PER_SIDE, CORR_LOOKBACK_DAYS, TOP_K_CANDIDATES,
)
import cpm_final_memo_numbers as M

CONV = "mooex"
COST = COST_BPS_PER_SIDE
LOOKBACK = CORR_LOOKBACK_DAYS
CPM_UNIV = M.CPM_UNIV
SAFE = M.SAFE
CLEAN_START = pd.Timestamp("2008-05-30")
EXT_START = pd.Timestamp("1999-03-10")
END = pd.Timestamp("2026-05-22")
ANCHOR = {"clean": (1.2667, -12.66, 1.1306), "ext": (1.2349, -15.18, 0.9119)}


def wf(close, sd, ranker, top_k, subselect, *, target_m=3, lookback=LOOKBACK):
    """Final-spec CPM weight fn with subselect toggle and target M (held names).
    Strict-M partial-safe: risky_fraction = min(n_pos, M)/M.
    subselect=True : n>M -> min-var-M-subset -> inv-vol.
    subselect=False: inv-vol over ALL positives (IVk), no min-var sub-selection.
    target_m=3 reproduces the production base spec exactly."""
    monthly = close.loc[:sd].resample("ME").last()
    safe = best_safe(monthly, sd, SAFE)
    cs = [sig_13612U(monthly[a]) for a in ["HYG", "TIP"] if a in monthly.columns]
    cs = [s for s in cs if pd.notna(s)]
    if not cs or sum(1 for s in cs if s > 0) == 0:
        return {safe: 1.0}

    present = [t for t in CPM_UNIV if t in monthly.columns]
    faber = faber_sma_xs(monthly)
    avail = [t for t in present if t in faber.index and pd.notna(faber[t])
             and (sd in close.index and pd.notna(close.loc[sd].get(t, np.nan)))]
    if not avail:
        return {safe: 1.0}

    scores, screenval = {}, {}
    if ranker == "plain12":
        for t in avail:
            s = monthly[t].dropna()
            if len(s) < 13:
                continue
            mom = float(s.iloc[-1] / s.iloc[-13] - 1.0)
            scores[t] = mom; screenval[t] = mom
    elif ranker == "faber":
        for t in avail:
            scores[t] = float(faber[t]); screenval[t] = float(faber[t])
    else:
        dr = close[avail].ffill().pct_change()
        for t in avail:
            v = dr[t].loc[:sd].tail(252).std() * np.sqrt(252)
            if pd.isna(v) or v < 1e-9:
                v = 1.0
            if ranker == "faber_vol":
                num = float(faber[t]); sv = float(faber[t])
            elif ranker == "13612u_vol":
                num = sig_13612U(monthly[t])
                if pd.isna(num):
                    continue
                num = float(num); sv = num
            else:
                raise ValueError(ranker)
            scores[t] = num / v; screenval[t] = sv
    if not scores:
        return {safe: 1.0}
    ranked = pd.Series(scores).sort_values(ascending=False)
    kk = max(2, min(top_k, len(ranked)))
    top = ranked.iloc[:kk]
    positive = [t for t in top.index if screenval.get(t, -np.inf) > 0]

    n = len(positive)
    if n == 0:
        return {safe: 1.0}
    csub = close.loc[:sd]
    risky_fraction = min(n, target_m) / float(target_m)
    if subselect and n > target_m:
        picks = M.select_subset(csub, positive, lookback, target_m, "minvar")
        if picks is None:
            picks = positive
    else:
        picks = positive
    risky_w = inv_vol_weights(csub, picks, lookback)
    out = {t: w * risky_fraction for t, w in risky_w.items()}
    if risky_fraction < 1.0:
        out[safe] = out.get(safe, 0.0) + (1.0 - risky_fraction)
    return out


def main():
    panel = load_panel(start=EXT_START, end=END)
    end = min(END, panel.index[-1])
    cash = panel["SHV"].ffill().pct_change().dropna()
    od, cy = H.load_open_close()
    intraday = (cy / od - 1.0).reindex(panel.index)
    overnight = (od / cy.shift(1) - 1.0).reindex(panel.index)
    cols = sorted(set(RISKY_UNIVERSE + SAFE_POOL + CANARY_ASSETS + [DEFAULT_CASH]) & set(panel.columns))
    close = panel[cols]
    daily = close.ffill().pct_change()

    def series(ranker, top_k, subselect, target_m=3):
        return M.run_cpm(close, daily, intraday, overnight,
                         lambda sd: wf(close, sd, ranker, top_k, subselect, target_m=target_m), end=end)

    from math import comb

    def metrics(s):
        return {wl: M.met(M.win(s, st, end), cash)
                for wl, st in [("clean", CLEAN_START), ("ext", EXT_START)]}

    out = {"meta": {"conv": CONV, "cost_bps": COST, "lookback": LOOKBACK,
                    "spec": "FINAL strict-3 partial-safe, inverse-vol",
                    "clean_start": str(CLEAN_START.date()), "ext_start": str(EXT_START.date()),
                    "end": str(end.date())}}

    # ---- ANCHOR GATE: base config (vol-Faber, K=4, subselect) ----
    base = series("faber_vol", 4, True)
    print("=== ANCHOR GATE (vol-Faber, K=4, subselect) ===")
    mb = metrics(base)
    ok_all = True
    for wl in ("clean", "ext"):
        m = mb[wl]; exp = ANCHOR[wl]
        ok = (abs(m["sharpe"] - exp[0]) < 5e-4 and abs(m["maxdd"] * 100 - exp[1]) < 0.02
              and abs(m["calmar"] - exp[2]) < 5e-4)
        ok_all &= ok
        print(f"  {wl}: {m['sharpe']:.4f}/{m['maxdd']*100:.2f}%/{m['calmar']:.4f} expect {exp} -> {'OK' if ok else 'MISMATCH'}")
    if not ok_all:
        print("ANCHOR MISMATCH -- aborting."); sys.exit(1)
    out["anchor"] = {wl: {"sharpe": mb[wl]["sharpe"], "maxdd": mb[wl]["maxdd"], "calmar": mb[wl]["calmar"]}
                     for wl in ("clean", "ext")}

    # ================= ANALYSIS (1): WIDER POOL x CHOICE-SET C(K,M) =================
    # Cells: K in {4,5,6} x M in {2,3}. Sub-select min-var-M vs weight-all-K (IVk).
    # Ranker = production vol-Faber. Tabulate edge vs choice-set size C(K,M).
    print("\n=== (1) WIDER POOL x CHOICE-SET: sub-select-min-var-M vs weight-all-K (vol-Faber) ===")
    a1 = {}
    for K in (4, 5, 6):
        for Mt in (3, 2):
            C = comb(K, Mt)
            sA = series("faber_vol", K, True, target_m=Mt)   # sub-select min-var-M
            sB = series("faber_vol", K, False, target_m=Mt)  # weight-all IVk (same strict-M partial-safe)
            mA, mB = metrics(sA), metrics(sB)
            key = f"K{K}_M{Mt}"
            a1[key] = {"K": K, "M": Mt, "choices_C_K_M": C, "subselect": mA, "weightall": mB,
                       "delta": {wl: {"sharpe": mA[wl]["sharpe"] - mB[wl]["sharpe"],
                                      "calmar": mA[wl]["calmar"] - mB[wl]["calmar"],
                                      "maxdd_pp": (mA[wl]["maxdd"] - mB[wl]["maxdd"]) * 100}
                                 for wl in ("clean", "ext")}}
            for wl in ("clean", "ext"):
                d = a1[key]["delta"][wl]
                print(f"  K={K} M={Mt} C={C:2d} [{wl}] subSel-minus-weightAll dSharpe={d['sharpe']:+.4f} "
                      f"dCalmar={d['calmar']:+.4f} dMaxDD={d['maxdd_pp']:+.2f}pp "
                      f"| A {mA[wl]['sharpe']:.4f}/{mA[wl]['maxdd']*100:.2f}% B {mB[wl]['sharpe']:.4f}/{mB[wl]['maxdd']*100:.2f}%")
    out["analysis1_wider_pool"] = a1

    # ================= ANALYSIS (2): 2x2 REDUNDANCY at K=4 =================
    print("\n=== (2) 2x2 RANKER x SUB-SELECTION at K=4 ===")
    cells = {}
    for rk in ("faber_vol", "faber"):
        for ss in (True, False):
            sname = "subselect" if ss else "weightall_IV4"
            cells[(rk, sname)] = metrics(series(rk, 4, ss))
    a2 = {}
    for (rk, sname), m in cells.items():
        a2[f"{rk}|{sname}"] = m
        for wl in ("clean", "ext"):
            mm = m[wl]
            print(f"  {rk:10s} {sname:14s} [{wl}] Sh={mm['sharpe']:.4f} Ca={mm['calmar']:.4f} DD={mm['maxdd']*100:.2f}%")
    # subselect benefit per ranker = subselect - weightall
    benefit = {}
    for rk in ("faber_vol", "faber"):
        benefit[rk] = {wl: {
            "sharpe": cells[(rk, "subselect")][wl]["sharpe"] - cells[(rk, "weightall_IV4")][wl]["sharpe"],
            "calmar": cells[(rk, "subselect")][wl]["calmar"] - cells[(rk, "weightall_IV4")][wl]["calmar"],
            "maxdd_pp": (cells[(rk, "subselect")][wl]["maxdd"] - cells[(rk, "weightall_IV4")][wl]["maxdd"]) * 100,
        } for wl in ("clean", "ext")}
    interaction = {wl: {
        "sharpe": benefit["faber"][wl]["sharpe"] - benefit["faber_vol"][wl]["sharpe"],
        "calmar": benefit["faber"][wl]["calmar"] - benefit["faber_vol"][wl]["calmar"],
        "maxdd_pp": benefit["faber"][wl]["maxdd_pp"] - benefit["faber_vol"][wl]["maxdd_pp"],
    } for wl in ("clean", "ext")}
    out["analysis2_2x2"] = {"cells": a2, "subselect_benefit": benefit, "interaction": interaction}
    print("\n  -- subselect benefit (subselect - weightall) per ranker --")
    for rk in ("faber_vol", "faber"):
        for wl in ("clean", "ext"):
            b = benefit[rk][wl]
            print(f"    {rk:10s} [{wl}] dSharpe={b['sharpe']:+.4f} dCalmar={b['calmar']:+.4f} dMaxDD={b['maxdd_pp']:+.2f}pp")
    print("  -- interaction (plain benefit - volFaber benefit) --")
    for wl in ("clean", "ext"):
        i = interaction[wl]
        print(f"    [{wl}] dSharpe={i['sharpe']:+.4f} dCalmar={i['calmar']:+.4f} dMaxDD={i['maxdd_pp']:+.2f}pp")

    (HERE / "ranker_revalidation_addendum.json").write_text(json.dumps(out, indent=2, default=float))
    print("\nDONE -> ranker_revalidation_addendum.json")
    return out


if __name__ == "__main__":
    main()
