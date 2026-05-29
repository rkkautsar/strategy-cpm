"""Throwaway research: FACTORIAL decomposition benchmark -> production sleeve.

  CPM  sleeve : AAA+TIP benchmark  -> CPM (4 factors, 2^4 = 16 cells)
  BULL sleeve : HAA-simple SPY     -> BULL (3 factors, 2^3 = 8 cells)

Each factor binary: off = benchmark setting, on = production setting.
all-OFF must reproduce the published benchmark; all-ON the production sleeve.

Execution identical to the headline convention everywhere:
  realistic T+1 MOO exact (mooex), post-cost 10 bps/side, production slow vol
  gate where the gate factor is ON (RV_60d < RV_252d). Both benchmark and
  production endpoints (and every interior cell) run through the SAME
  _segment_returns_conv harness => byte-identical cost/window/execution.

Windows: CLEAN 18y 2008-05-30.. ; EXT 27y 1999-03-10..

Reads code from cpm_live.py, bull_qqq_live.py, build_dashboard.py to define
factors. Writes JSON next to this file. No production files touched.
"""
import sys, math, json, itertools
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.optimize import minimize

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import bull_qqq_live
from cpm_live import (
    load_panel, perf_metrics, sig_13612U, best_safe, faber_sma_xs, min_vol_pair,
    COST_BPS_PER_SIDE, CORR_LOOKBACK_DAYS, TOP_K_CANDIDATES,
)
import exec_lag_moo_validation_2026_05_30 as H
from sleeve_vs_benchmark_2026_05_30 import stitch_bil, stitch_agg

CONV = "mooex"

# ---- universes / pools ----
CPM_SPY_UNIVERSE = ["SPY", "EFA", "EEM", "VNQ", "GLD", "TLT", "DBC"]          # benchmark (AAA)
CPM_PROD_UNIVERSE = ["QQQ", "SPHQ", "EFA", "EEM", "VNQ", "GLD", "TLT", "DBC"]  # production
CPM_SAFE = ["SHV", "IEF"]   # common to both ends (NOT a factor)
BULL_BENCH_SAFE = ["BIL", "AGG"]   # HAA-simple supplied spec
BULL_PROD_SAFE = ["SHV", "IEF"]    # production


# ======================= CPM parametric weight fn =======================
# Factors (off=benchmark / on=production):
#   U  universe : SPY-set (off)            vs QQQ/SPHQ-set (on)
#   R  ranker   : 13612U (off)             vs vol-adjusted Faber (on)
#   P  weighting: continuous min-var (off) vs 50/50 min-var PAIR (on)
#   C  canary   : TIP-only (off)           vs HYG-OR-TIP any-positive (on)
# Common to both ends (fixed-on, NOT factors): top-half K cap (=4 either side),
# positive-trend screen, SHV/IEF best-of-safe.

def cpm_wf(close, daily, sig_d, U, R, P, C):
    universe = CPM_PROD_UNIVERSE if U else CPM_SPY_UNIVERSE
    monthly = close.loc[:sig_d].resample("ME").last()
    safe = best_safe(monthly, sig_d, CPM_SAFE)

    # --- canary ---
    canary_assets = ["HYG", "TIP"] if C else ["TIP"]
    cscores = [sig_13612U(monthly[a]) for a in canary_assets if a in monthly.columns]
    cscores = [s for s in cscores if pd.notna(s)]
    if not cscores:
        return {safe: 1.0}
    n_pos = sum(1 for s in cscores if s > 0)
    if n_pos == 0:                       # any-positive (C on) and TIP-only (C off) coincide here
        return {safe: 1.0}

    # --- ranker + top-half + positive screen ---
    top_half = max(2, math.ceil(len(universe) / 2))   # 7->4, 8->4
    present = [t for t in universe if t in monthly.columns]
    if R:  # vol-adjusted Faber (production)
        faber = faber_sma_xs(monthly)
        avail = [t for t in present if t in faber.index and pd.notna(faber[t])
                 and (sig_d in close.index and pd.notna(close.loc[sig_d].get(t, np.nan)))]
        if not avail:
            return {safe: 1.0}
        dr = close[avail].ffill().pct_change()
        score = {}
        for t in avail:
            v = dr[t].loc[:sig_d].tail(252).std() * np.sqrt(252)
            if pd.isna(v) or v < 1e-9:
                v = 1.0
            score[t] = float(faber[t]) / v
        ranked = pd.Series(score).sort_values(ascending=False)
        top_k = max(2, min(top_half, len(ranked)))
        top = ranked.iloc[:top_k]
        positive = [t for t in top.index if faber.get(t, -np.inf) > 0]
    else:  # 13612U (benchmark)
        scores = {t: sig_13612U(monthly[t]) for t in present}
        scores = {t: s for t, s in scores.items() if pd.notna(s)}
        ranked = sorted(scores.items(), key=lambda x: -x[1])
        top = ranked[:top_half]
        positive = [t for t, s in top if s > 0]

    # --- weighting ---
    if len(positive) == 0:
        return {safe: 1.0}
    if len(positive) == 1:
        return {positive[0]: 0.5, safe: 0.5}

    if P:  # 50/50 min-var pair (production)
        pick = min_vol_pair(close.loc[:sig_d, positive], positive, CORR_LOOKBACK_DAYS)
        if pick is None:
            return {positive[0]: 1.0}
        return {pick[0]: 0.5, pick[1]: 0.5}
    else:  # continuous min-var over survivors (benchmark)
        cov = daily.loc[:sig_d].tail(CORR_LOOKBACK_DAYS)[positive].cov() * 252
        n = len(positive)
        def obj(w, Cv=cov.values):
            return float(np.dot(w, np.dot(Cv, w)))
        cons = ({"type": "eq", "fun": lambda w: np.sum(w) - 1.0},)
        bnds = tuple((0.0, 1.0) for _ in range(n))
        r = minimize(obj, np.ones(n) / n, method="SLSQP", bounds=bnds, constraints=cons)
        return {positive[i]: float(r.x[i]) for i in range(n)} if r.success else \
               {t: 1.0 / n for t in positive}


# ======================= BULL parametric weight fn =======================
# Factors (off=benchmark / on=production):
#   K  canary  : TIP-only (off)        vs HYG-OR-TIP any-positive (on)
#   V  vol gate: none (off)            vs RV_60d<RV_252d (on)
#   S  safe    : {BIL,AGG} (off)       vs {SHV,IEF} (on)
# Common to both ends (fixed-on, NOT a factor): SPY 13612U>0 trend gate.

def _pick_safe_pool(monthly, pool):
    """Production bull_qqq_live._pick_safe generalized to an explicit pool:
    max 13612U over pool members, fallback SHV."""
    scores = {}
    for s in pool:
        if s in monthly.columns:
            sc = sig_13612U(monthly[s])
            if pd.notna(sc):
                scores[s] = sc
    return max(scores, key=scores.get) if scores else "SHV"


def bull_wf(close, sig_d, daily_spy, K, V, S):
    monthly = close.loc[:sig_d].resample("ME").last()
    safe_pool = BULL_PROD_SAFE if S else BULL_BENCH_SAFE
    safe = _pick_safe_pool(monthly, safe_pool)

    if K:
        cs = [sig_13612U(monthly[a]) for a in ["HYG", "TIP"] if a in monthly.columns]
        cs = [s for s in cs if pd.notna(s)]
        canary_ok = any(s > 0 for s in cs) if cs else False
    else:
        tipm = sig_13612U(monthly["TIP"]) if "TIP" in monthly.columns else float("nan")
        canary_ok = pd.notna(tipm) and tipm > 0

    spym = sig_13612U(monthly["SPY"]) if "SPY" in monthly.columns else float("nan")
    trend_ok = pd.notna(spym) and spym > 0

    if V:
        sub = daily_spy.loc[:sig_d].pct_change().dropna()
        if len(sub) < 252:
            vol_ok = True
        else:
            vol_ok = float(sub.tail(60).std()) < float(sub.tail(252).std())
    else:
        vol_ok = True

    if canary_ok and trend_ok and vol_ok:
        return {"SPY": 1.0}
    return {safe: 1.0}


# ======================= runners =======================

def met(daily, cash):
    m = perf_metrics(daily, cash)
    return {"sharpe": m.get("sharpe"), "cagr": m.get("cagr"),
            "maxdd": m.get("max_drawdown"), "calmar": m.get("calmar"), "vol": m.get("vol")}


def run_cpm_cell(close, daily, intraday, overnight, start, end, U, R, P, C):
    wf = lambda sd: cpm_wf(close, daily, sd, U, R, P, C)
    s, _ = H._segment_returns_conv(close, daily, wf, start, end, CONV,
                                   COST_BPS_PER_SIDE, intraday, overnight)
    return s


def run_bull_cell(close, daily, intraday, overnight, daily_spy, start, end, K, V, S):
    wf = lambda sd: bull_wf(close, sd, daily_spy, K, V, S)
    s, _ = H._segment_returns_conv(close, daily, wf, start, end, CONV,
                                   COST_BPS_PER_SIDE, intraday, overnight)
    return s


def factorial_effects(cells, factor_names, metric):
    """cells: dict tuple(code 0/1...) -> metrics dict. Return main effects +
    2-way interactions for `metric`. Coded +-1; effect = mean(M|f=1)-mean(M|f=0)."""
    keys = list(cells.keys())
    k = len(factor_names)
    M = {key: cells[key][metric] for key in keys}
    codes = {key: tuple(2 * b - 1 for b in key) for key in keys}  # 0/1 -> -1/+1
    half = 2 ** (k - 1)
    main = {}
    for i, fn in enumerate(factor_names):
        main[fn] = sum(codes[key][i] * M[key] for key in keys) / half
    inter = {}
    for i, j in itertools.combinations(range(k), 2):
        name = f"{factor_names[i]}x{factor_names[j]}"
        inter[name] = sum(codes[key][i] * codes[key][j] * M[key] for key in keys) / half
    # sign-flip detection: does toggling factor i change sign of metric delta across backgrounds?
    flips = {}
    for i, fn in enumerate(factor_names):
        deltas = []
        for key in keys:
            if key[i] == 0:
                on_key = tuple(1 if t == i else key[t] for t in range(k))
                deltas.append(M[on_key] - M[key])
        signs = set(np.sign(round(d, 6)) for d in deltas if abs(d) > 1e-9)
        flips[fn] = (len([s for s in signs if s > 0]) > 0 and len([s for s in signs if s < 0]) > 0)
    return {"main": main, "interactions": inter, "sign_flip": flips}


def main():
    end = pd.Timestamp("2026-05-22")
    ext_start = pd.Timestamp("1999-03-10")
    clean_start = pd.Timestamp("2008-05-30")

    panel = load_panel(start=ext_start, end=end)
    end = min(end, panel.index[-1])
    cash = panel["SHV"].ffill().pct_change().dropna()
    panel["BIL"] = stitch_bil(panel)
    panel["AGG"] = stitch_agg(panel)

    open_df, close_yf = H.load_open_close()
    intraday = (close_yf / open_df - 1.0).reindex(panel.index)
    overnight = (open_df / close_yf.shift(1) - 1.0).reindex(panel.index)

    # ---- CPM panel/daily ----
    cpm_cols = sorted(set(CPM_SPY_UNIVERSE + CPM_PROD_UNIVERSE + CPM_SAFE
                          + ["HYG", "TIP"]) & set(panel.columns))
    cpm_close = panel[cpm_cols]
    cpm_daily = cpm_close.ffill().pct_change()

    # ---- BULL panel/daily ----
    bull_cols = sorted(set(["SPY", "HYG", "TIP"] + BULL_BENCH_SAFE + BULL_PROD_SAFE)
                       & set(panel.columns))
    bull_close = panel[bull_cols]
    bull_daily = bull_close.ffill().pct_change()
    daily_spy = panel["SPY"]

    windows = {"CLEAN": (clean_start, end), "EXT": (ext_start, end)}

    # ===== CPM 2^4 =====
    cpm_factors = ["U", "R", "P", "C"]
    cpm_cells = {}  # (U,R,P,C) -> {window: metrics}
    print("Running CPM 2^4 = 16 cells (mooex, ext window then slice)...")
    for U, R, P, C in itertools.product([0, 1], repeat=4):
        s = run_cpm_cell(cpm_close, cpm_daily, intraday, overnight, ext_start, end, U, R, P, C)
        wm = {}
        for wn, (ws, we) in windows.items():
            sw = s.loc[(s.index >= ws) & (s.index <= we)]
            wm[wn] = met(sw, cash)
        cpm_cells[(U, R, P, C)] = wm
        if (U, R, P, C) in [(0, 0, 0, 0), (1, 1, 1, 1)]:
            print(f"  CPM {U}{R}{P}{C}: CLEAN sharpe={wm['CLEAN']['sharpe']:.3f} "
                  f"calmar={wm['CLEAN']['calmar']:.3f} maxdd={wm['CLEAN']['maxdd']*100:.2f}%")

    # ===== BULL 2^3 =====
    bull_factors = ["K", "V", "S"]
    bull_cells = {}
    print("Running BULL 2^3 = 8 cells...")
    for K, V, S in itertools.product([0, 1], repeat=3):
        s = run_bull_cell(bull_close, bull_daily, intraday, overnight, daily_spy,
                          ext_start, end, K, V, S)
        wm = {}
        for wn, (ws, we) in windows.items():
            sw = s.loc[(s.index >= ws) & (s.index <= we)]
            wm[wn] = met(sw, cash)
        bull_cells[(K, V, S)] = wm
        if (K, V, S) in [(0, 0, 0), (1, 1, 1)]:
            print(f"  BULL {K}{V}{S}: CLEAN sharpe={wm['CLEAN']['sharpe']:.3f} "
                  f"calmar={wm['CLEAN']['calmar']:.3f} maxdd={wm['CLEAN']['maxdd']*100:.2f}%")

    # ===== effects =====
    out = {"cpm": {"factors": cpm_factors, "cells": {}, "effects": {}},
           "bull": {"factors": bull_factors, "cells": {}, "effects": {}}}
    for key, wm in cpm_cells.items():
        out["cpm"]["cells"]["".join(map(str, key))] = wm
    for key, wm in bull_cells.items():
        out["bull"]["cells"]["".join(map(str, key))] = wm

    for wn in windows:
        for metric in ["sharpe", "calmar"]:
            cpm_flat = {key: cpm_cells[key][wn] for key in cpm_cells}
            bull_flat = {key: bull_cells[key][wn] for key in bull_cells}
            out["cpm"]["effects"][f"{wn}_{metric}"] = factorial_effects(cpm_flat, cpm_factors, metric)
            out["bull"]["effects"][f"{wn}_{metric}"] = factorial_effects(bull_flat, bull_factors, metric)

    Path(__file__).with_suffix(".json").write_text(json.dumps(out, indent=2, default=float))

    # ===== console report =====
    def anchor_line(cells, key, label):
        c = cells[key]["CLEAN"]
        print(f"  {label}: sharpe={c['sharpe']:.3f} cagr={c['cagr']*100:.2f}% "
              f"maxdd={c['maxdd']*100:.2f}% calmar={c['calmar']:.3f}")

    print("\n=== CPM ENDPOINT ANCHORS (CLEAN 18y, mooex) ===")
    anchor_line(cpm_cells, (0, 0, 0, 0), "all-OFF (expect AAA+TIP ~Sharpe1.041 Calmar0.527)")
    anchor_line(cpm_cells, (1, 1, 1, 1), "all-ON  (expect CPM     ~Sharpe1.242 Calmar0.870)")
    print("\n=== BULL ENDPOINT ANCHORS (CLEAN 18y, mooex) ===")
    anchor_line(bull_cells, (0, 0, 0), "all-OFF (expect HAA-S   ~Sharpe0.960 Calmar0.561)")
    anchor_line(bull_cells, (1, 1, 1), "all-ON  (expect BULL    ~Sharpe1.081 Calmar0.857)")

    def eff_report(name, cells, factors, effects):
        print(f"\n===== {name} MAIN EFFECTS =====")
        for wn in windows:
            for metric in ["sharpe", "calmar"]:
                e = effects[f"{wn}_{metric}"]
                print(f"\n  {wn} d{metric}:")
                for fn, v in sorted(e["main"].items(), key=lambda x: -abs(x[1])):
                    fl = " [SIGN-FLIP]" if e["sign_flip"][fn] else ""
                    print(f"    {fn}: {v:+.4f}{fl}")
                top_int = sorted(e["interactions"].items(), key=lambda x: -abs(x[1]))[:3]
                print(f"    top 2-way: " + ", ".join(f"{k}={v:+.4f}" for k, v in top_int))

    eff_report("CPM", cpm_cells, cpm_factors, out["cpm"]["effects"])
    eff_report("BULL", bull_cells, bull_factors, out["bull"]["effects"])
    print("\nDONE -> json written")


if __name__ == "__main__":
    main()
