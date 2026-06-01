# -*- coding: utf-8 -*-
"""Read-only re production. BULL 2^2 factorial with a FAITHFUL HAA-Simple
baseline (all-OFF). Two factors only:

  C  canary : OFF = TIP-only 13612U ; ON = (HYG OR TIP) 13612U
  V  vol    : OFF = none            ; ON = rv_60d(SPY) < rv_252d(SPY)

Safe pool held at production {SHV, IEF} (best-of by 13612U) across ALL cells.
SPY 13612U trend gate is common to every cell (NOT a factor).

  all-OFF  == faithful HAA-Simple  (anchor: clean Sharpe ~0.9840)
  all-ON   == production BULL      (anchor: clean Sharpe ~1.081)

Plus a one-off SAFE-POOL immateriality check: {IEF, BIL} (paper) vs {SHV, IEF}
(production), expected ~0. Harness: mooex T+1 MOO exact, 10 bps/side, CLEAN+EXT.
NO factorial axis for the safe pool (SHV/BIL are near-identical T-bill cash).
NO production files touched, NO commit."""
import sys, json
from pathlib import Path
from itertools import product
import numpy as np
import pandas as pd

REPO = Path("/Users/rkautsar/personal/scripts/strategy_cpm")
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "research"))

from cpm_live import (load_panel, perf_metrics, sig_13612U, COST_BPS_PER_SIDE,
                      _fetch_cached_adjusted_close)
import exec_lag_moo_validation_2026_05_30 as H
import bull_spy_live as BULL

CONV = "mooex"
PROD_SAFE = ["SHV", "IEF"]   # production safe pool, held across all factorial cells


# ---------- parametric weight function ----------

def make_wf(close, daily, canary_on, vol_on, safe_pool=PROD_SAFE):
    """Return weight_fn(sig_d) -> dict. Faithful-HAA <-> production BULL via flags.

    Risk-on iff:  canary AND SPY-13612U-trend AND vol
      canary OFF -> TIP 13612U > 0
      canary ON  -> (HYG OR TIP) 13612U > 0
      vol OFF    -> always True
      vol ON     -> rv_60d(SPY) < rv_252d(SPY)  (annualized daily-return std)
    Risk-on -> 100% SPY ; else best-of(safe_pool) by 13612U."""
    spy_close = close["SPY"]

    def wf(sig_d):
        monthly = close.loc[:sig_d].resample("ME").last()

        def s13(t):
            return sig_13612U(monthly[t]) if t in monthly.columns else np.nan

        spym = s13("SPY")
        tipm = s13("TIP")
        hygm = s13("HYG")
        # canary
        if canary_on:
            canary_ok = ((pd.notna(hygm) and hygm > 0) or (pd.notna(tipm) and tipm > 0))
        else:
            canary_ok = (pd.notna(tipm) and tipm > 0)
        # common SPY trend
        spy_trend_ok = pd.notna(spym) and spym > 0
        # vol gate (mirror bull_spy_live._vol_gate_ok on SPY prices)
        if vol_on:
            sub = spy_close.loc[:sig_d].pct_change().dropna()
            if len(sub) < 252:
                vol_ok = True
            else:
                rv60 = float(sub.tail(60).std() * np.sqrt(252))
                rv252 = float(sub.tail(252).std() * np.sqrt(252))
                vol_ok = rv60 < rv252
        else:
            vol_ok = True

        if canary_ok and spy_trend_ok and vol_ok:
            return {"SPY": 1.0}
        # best-of safe pool by 13612U
        scores = {s: s13(s) for s in safe_pool if pd.notna(s13(s))}
        if not scores:
            return {"SHV": 1.0}
        return {max(scores, key=scores.get): 1.0}

    return wf


def met(daily, cash):
    m = perf_metrics(daily, cash)
    return {"sharpe": m.get("sharpe"), "cagr": m.get("cagr"), "vol": m.get("vol"),
            "max_drawdown": m.get("max_drawdown"), "calmar": m.get("calmar")}


def main():
    end = pd.Timestamp("2026-05-22")
    ext_start = pd.Timestamp("1999-03-10")
    clean_start = pd.Timestamp("2008-05-30")
    panel = load_panel(start=ext_start, end=end)
    end = min(end, panel.index[-1])
    cash = panel["SHV"].ffill().pct_change().dropna()

    open_df, close_yf = H.load_open_close()
    intraday = (close_yf / open_df - 1.0).reindex(panel.index)
    overnight = (open_df / close_yf.shift(1) - 1.0).reindex(panel.index)

    cols = sorted({"SPY", "IEF", "SHV", "TIP", "HYG"} & set(panel.columns))
    close = panel[cols]
    daily = close.ffill().pct_change()

    windows = {"CLEAN": (clean_start, end), "EXT": (ext_start, end)}

    def run(wf):
        ser, _ = H._segment_returns_conv(close, daily, wf, ext_start, end, CONV,
                                         COST_BPS_PER_SIDE, intraday, overnight)
        out = {}
        for wn, (ws, we) in windows.items():
            sw = ser.loc[(ser.index >= ws) & (ser.index <= we)]
            out[wn] = met(sw, cash)
        return ser, out

    # ---- 4-cell factorial: C (canary), V (vol) ----
    cells = {}
    series = {}
    for c_on, v_on in product([False, True], [False, True]):
        wf = make_wf(close, daily, c_on, v_on)
        ser, out = run(wf)
        key = (("C" if c_on else "c"), ("V" if v_on else "v"))
        cells["".join(key)] = out
        series["".join(key)] = ser

    # ---- GATE 1: all-ON cell == production BULL (logic equality, weight-by-weight) ----
    monthly_idx = (pd.DataFrame({"x": 1}, index=close.index)
                   .groupby(pd.Grouper(freq="ME")).tail(1))
    sigs = monthly_idx.index[(monthly_idx.index >= ext_start) & (monthly_idx.index <= end)].tolist()
    wf_on = make_wf(close, daily, True, True)
    mismatches = 0
    for sd in sigs:
        mine = wf_on(sd)
        prod, _, _ = BULL.compute_bull_spy_weights(panel, sd, panel["SPY"])
        # normalize keys/values
        mk = {k: round(v, 6) for k, v in mine.items() if v != 0}
        pk = {k: round(v, 6) for k, v in prod.items() if v != 0}
        if mk != pk:
            mismatches += 1
    gate_allon = (mismatches == 0)

    # ---- GATE 2: production BULL native engine clean Sharpe (~1.081 target) ----
    bull_native = BULL.run_bull_spy_backtest(panel, clean_start, end, cost_bps=COST_BPS_PER_SIDE)
    bn = met(bull_native.loc[(bull_native.index >= clean_start) & (bull_native.index <= end)], cash)

    # ---- SAFE-POOL immateriality check: {IEF,BIL} vs {SHV,IEF} ----
    # BIL not in stitched panel (no long history). Fetch real BIL where it exists.
    safe_check = {"note": ""}
    try:
        bil = _fetch_cached_adjusted_close("BIL", pd.Timestamp("2007-01-01"), end, "/tmp/cpm_cache")
    except Exception as e:
        bil = pd.Series(dtype=float)
        safe_check["fetch_error"] = str(e)
    if not bil.empty:
        bil = bil.reindex(panel.index).ffill()
        bil_first = bil.first_valid_index()
        close2 = close.copy()
        close2["BIL"] = bil
        daily2 = close2.ffill().pct_change()
        intraday2 = intraday.copy(); overnight2 = overnight.copy()
        # immateriality measured on the window where BIL is live (clean window ok: 2008+)
        def run2(wf, cl, dl):
            ser, _ = H._segment_returns_conv(cl, dl, wf, ext_start, end, CONV,
                                             COST_BPS_PER_SIDE, intraday2, overnight2)
            o = {}
            for wn, (ws, we) in windows.items():
                sw = ser.loc[(ser.index >= ws) & (ser.index <= we)]
                o[wn] = met(sw, cash)
            return o
        # all-OFF baseline with paper {IEF,BIL} vs production {SHV,IEF}
        wf_paper = make_wf(close2, daily2, False, False, safe_pool=["IEF", "BIL"])
        wf_prod = make_wf(close2, daily2, False, False, safe_pool=["SHV", "IEF"])
        out_paper = run2(wf_paper, close2, daily2)
        out_prod = run2(wf_prod, close2, daily2)
        # correlation of SHV vs BIL daily returns over overlap
        shv_r = close2["SHV"].pct_change()
        bil_r = close2["BIL"].pct_change()
        ov = pd.concat([shv_r, bil_r], axis=1).dropna()
        ov = ov[(ov.index >= bil_first)]
        corr = float(ov.iloc[:, 0].corr(ov.iloc[:, 1])) if len(ov) > 10 else float("nan")
        safe_check.update({
            "bil_first_valid": str(bil_first.date()) if bil_first is not None else None,
            "shv_bil_daily_corr": corr,
            "paper_IEF_BIL": out_paper,
            "prod_SHV_IEF": out_prod,
            "delta_clean_sharpe": out_prod["CLEAN"]["sharpe"] - out_paper["CLEAN"]["sharpe"],
            "delta_clean_calmar": out_prod["CLEAN"]["calmar"] - out_paper["CLEAN"]["calmar"],
            "delta_ext_sharpe": out_prod["EXT"]["sharpe"] - out_paper["EXT"]["sharpe"],
            "delta_ext_calmar": out_prod["EXT"]["calmar"] - out_paper["EXT"]["calmar"],
            "note": ("BIL has no long stitched history (inception ~2007); SHV is "
                     "stitched from VFISX back to 1991, so SHV is required for the "
                     "extended (1999+) window. Delta measured where BIL is live."),
        })
    else:
        safe_check["note"] = ("BIL unavailable from data source; SHV used as the "
                              "ultra-short T-bill cash proxy. SHV is stitched from "
                              "VFISX to 1991 for the extended window; BIL inception "
                              "~2007 with no stitch -> SHV preferred structurally.")

    # ---- effects + interaction (cv, Cv, cV, CV) ----
    def get(cell, win, metric):
        return cells[cell][win][metric]

    effects = {}
    for win in ("CLEAN", "EXT"):
        for metric in ("sharpe", "calmar"):
            # main effect = avg(ON) - avg(OFF)
            cV = get("cV", win, metric); CV = get("CV", win, metric)
            cv = get("cv", win, metric); Cv = get("Cv", win, metric)
            C_eff = 0.5 * ((Cv + CV) - (cv + cV))   # canary ON - OFF
            V_eff = 0.5 * ((cV + CV) - (cv + Cv))   # vol ON - OFF
            CxV = 0.5 * ((CV - cV) - (Cv - cv))     # interaction
            effects[f"{win}_{metric}"] = {
                "C_main": C_eff, "V_main": V_eff, "CxV_interaction": CxV,
            }

    result = {
        "harness": "mooex T+1 MOO-exact, 10 bps/side",
        "windows": {"CLEAN": "2008-05-30..2026-05-22", "EXT": "1999-03-10..2026-05-22"},
        "factors": {
            "C_canary": "OFF=TIP-only 13612U ; ON=(HYG OR TIP) 13612U",
            "V_vol": "OFF=none ; ON=rv_60d(SPY)<rv_252d(SPY)",
            "common": "SPY 13612U trend gate (all cells)",
            "safe_pool_fixed": "{SHV, IEF} best-of by 13612U (all cells)",
        },
        "cells": cells,
        "gate_allOFF_anchor": {"target_clean_sharpe": 0.9840, "actual": cells["cv"]["CLEAN"]},
        "gate_allON_logic_equals_production": {"weight_mismatches": mismatches, "pass": gate_allon},
        "gate_allON_anchor_native_bull": {"target_clean_sharpe_approx": 1.081, "native": bn,
                                          "mooex_allon": cells["CV"]["CLEAN"]},
        "effects": effects,
        "safe_pool_immateriality": safe_check,
    }

    out_json = REPO / "research" / "bull_factorial_faithful_haa_findings.json"
    out_json.write_text(json.dumps(result, indent=2, default=float))
    print("WROTE", out_json)
    print(json.dumps(result, indent=2, default=float))


if __name__ == "__main__":
    main()
