"""Throwaway research: CPM 2^4 factorial RE-ANCHORED at CANONICAL AAA (no canary).

SUPERSEDES the AAA+TIP-anchored CPM factorial in
research/factorial_decomposition_2026_05_30.py (CPM side). Canonical AAA is the
sole CPM benchmark and the all-OFF anchor. The TIP-only canary baseline is gone.

Factors (off = canonical AAA setting / on = CPM production setting):
  U  universe : canonical AAA SPY-set (off)   vs CPM QQQ/quality-set (on)
  R  ranker   : 13612U (off)                  vs vol-adjusted Faber (on)
  P  weighting: continuous min-var (off)      vs 50/50 min-var PAIR (on)
  C  canary   : NONE (off)                    vs HYG-OR-TIP any-positive (on)
                ^^^ KEY CHANGE: off is NO canary (canonical AAA), not TIP-only.

all-OFF must reproduce canonical AAA (clean Sharpe 0.970 / Calmar 0.556 / MaxDD -20.65%)
all-ON  must reproduce CPM             (clean Sharpe 1.242 / Calmar 0.870 / MaxDD -16.35%)

Execution = headline convention everywhere: realistic T+1 MOO exact (mooex),
post-cost 10 bps/side, shared _segment_returns_conv harness => byte-identical
cost/window/execution across all 16 cells. CPM sleeve has NO vol gate.
Windows: CLEAN 18y 2008-05-30.. ; EXT 27y 1999-03-10.. ; end 2026-05-22.

No production files touched. Writes JSON next to this file.
"""
import sys, math, json, itertools
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.optimize import minimize

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import bull_spy_live  # noqa: F401 (harness side parity)
from cpm_live import (
    load_panel, perf_metrics, sig_13612U, best_safe, faber_sma_xs, min_vol_pair,
    COST_BPS_PER_SIDE, CORR_LOOKBACK_DAYS,
)
import exec_lag_moo_validation_2026_05_30 as H

CONV = "mooex"

# ---- universes / pools ----
CPM_SPY_UNIVERSE = ["SPY", "EFA", "EEM", "VNQ", "GLD", "TLT", "DBC"]            # canonical AAA (off)
CPM_PROD_UNIVERSE = ["QQQ", "SPHQ", "EFA", "EEM", "VNQ", "GLD", "TLT", "DBC"]   # CPM production (on)
CPM_SAFE = ["SHV", "IEF"]   # best-of-safe, common to both ends (NOT a factor)


# ======================= CPM parametric weight fn =======================
# all-OFF (U=R=P=C=0) == canonical AAA (no canary, 13612U top-half, continuous
# min-var). all-ON (1,1,1,1) == CPM production. Common fixed-on (NOT factors):
# top-half K cap, positive-trend screen, SHV/IEF best-of-safe.
def cpm_wf(close, daily, sig_d, U, R, P, C):
    universe = CPM_PROD_UNIVERSE if U else CPM_SPY_UNIVERSE
    monthly = close.loc[:sig_d].resample("ME").last()
    safe = best_safe(monthly, sig_d, CPM_SAFE)

    # --- canary: C off = NONE (canonical AAA, no risk-off gate); C on = HYG-OR-TIP ---
    if C:
        cscores = [sig_13612U(monthly[a]) for a in ["HYG", "TIP"] if a in monthly.columns]
        cscores = [s for s in cscores if pd.notna(s)]
        if not cscores or sum(1 for s in cscores if s > 0) == 0:
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
    else:  # 13612U (benchmark / canonical AAA)
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
    else:  # continuous min-var over survivors (canonical AAA)
        cov = daily.loc[:sig_d].tail(CORR_LOOKBACK_DAYS)[positive].cov() * 252
        n = len(positive)
        def obj(w, Cv=cov.values):
            return float(np.dot(w, np.dot(Cv, w)))
        cons = ({"type": "eq", "fun": lambda w: np.sum(w) - 1.0},)
        bnds = tuple((0.0, 1.0) for _ in range(n))
        r = minimize(obj, np.ones(n) / n, method="SLSQP", bounds=bnds, constraints=cons)
        return {positive[i]: float(r.x[i]) for i in range(n)} if r.success else \
               {t: 1.0 / n for t in positive}


# ======================= runners / effects =======================
def met(daily, cash):
    m = perf_metrics(daily, cash)
    return {"sharpe": m.get("sharpe"), "cagr": m.get("cagr"),
            "maxdd": m.get("max_drawdown"), "calmar": m.get("calmar"), "vol": m.get("vol")}


def run_cpm_cell(close, daily, intraday, overnight, start, end, U, R, P, C):
    wf = lambda sd: cpm_wf(close, daily, sd, U, R, P, C)
    s, _ = H._segment_returns_conv(close, daily, wf, start, end, CONV,
                                   COST_BPS_PER_SIDE, intraday, overnight)
    return s


def factorial_effects(cells, factor_names, metric):
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
    flips = {}
    for i, fn in enumerate(factor_names):
        deltas = []
        for key in keys:
            if key[i] == 0:
                on_key = tuple(1 if t == i else key[t] for t in range(k))
                deltas.append(M[on_key] - M[key])
        signs = set(np.sign(round(d, 6)) for d in deltas if abs(d) > 1e-9)
        flips[fn] = (any(s > 0 for s in signs) and any(s < 0 for s in signs))
    return {"main": main, "interactions": inter, "sign_flip": flips}


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

    cpm_cols = sorted(set(CPM_SPY_UNIVERSE + CPM_PROD_UNIVERSE + CPM_SAFE
                          + ["HYG", "TIP"]) & set(panel.columns))
    cpm_close = panel[cpm_cols]
    cpm_daily = cpm_close.ffill().pct_change()

    windows = {"CLEAN": (clean_start, end), "EXT": (ext_start, end)}
    factors = ["U", "R", "P", "C"]

    cells = {}  # (U,R,P,C) -> {window: metrics}
    print("Running CPM 2^4 = 16 cells (mooex, ext window then slice)...")
    for U, R, P, C in itertools.product([0, 1], repeat=4):
        s = run_cpm_cell(cpm_close, cpm_daily, intraday, overnight, ext_start, end, U, R, P, C)
        wm = {}
        for wn, (ws, we) in windows.items():
            sw = s.loc[(s.index >= ws) & (s.index <= we)]
            wm[wn] = met(sw, cash)
        cells[(U, R, P, C)] = wm
        print(f"  {U}{R}{P}{C}: CLEAN sharpe={wm['CLEAN']['sharpe']:.3f} "
              f"calmar={wm['CLEAN']['calmar']:.3f} maxdd={wm['CLEAN']['maxdd']*100:.2f}%")

    out = {"factors": factors, "cells": {}, "effects": {}}
    for key, wm in cells.items():
        out["cells"]["".join(map(str, key))] = wm
    for wn in windows:
        for metric in ["sharpe", "calmar"]:
            flat = {key: cells[key][wn] for key in cells}
            out["effects"][f"{wn}_{metric}"] = factorial_effects(flat, factors, metric)

    Path(__file__).with_suffix(".json").write_text(json.dumps(out, indent=2, default=float))

    def anchor_line(key, label):
        c = cells[key]["CLEAN"]
        print(f"  {label}: sharpe={c['sharpe']:.3f} cagr={c['cagr']*100:.2f}% "
              f"maxdd={c['maxdd']*100:.2f}% calmar={c['calmar']:.3f}")

    print("\n=== CPM ENDPOINT ANCHORS (CLEAN 18y, mooex) ===")
    anchor_line((0, 0, 0, 0), "all-OFF (expect canonical AAA  Sharpe0.970 Calmar0.556 MaxDD-20.65%)")
    anchor_line((1, 1, 1, 1), "all-ON  (expect CPM            Sharpe1.242 Calmar0.870 MaxDD-16.35%)")

    print("\n===== CPM MAIN EFFECTS =====")
    for wn in windows:
        for metric in ["sharpe", "calmar"]:
            e = out["effects"][f"{wn}_{metric}"]
            print(f"\n  {wn} d{metric}:")
            for fn, v in sorted(e["main"].items(), key=lambda x: -abs(x[1])):
                fl = " [SIGN-FLIP]" if e["sign_flip"][fn] else ""
                print(f"    {fn}: {v:+.4f}{fl}")
            top_int = sorted(e["interactions"].items(), key=lambda x: -abs(x[1]))[:3]
            print(f"    top 2-way: " + ", ".join(f"{k}={v:+.4f}" for k, v in top_int))
    print("\nDONE -> json written")


if __name__ == "__main__":
    main()
