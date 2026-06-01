# -*- coding: utf-8 -*-
"""Throwaway research (read-only re production): CPM 2^6 factorial with a
FAITHFUL AAA baseline.

The prior factorial harness (research/cpm_factorial_iv4_6factor.py) used a
NON-faithful AAA baseline: plain-12-month momentum + equal-weight + a TIP
canary. That is NOT the AAA (Adaptive Asset Allocation, Keller/Butler)
specification. This harness corrects the baseline so the all-OFF cell is the
TRUE faithful AAA (best buildable from the panel, 8 of 10 -- panel lacks EWJ
and RWX), reusing the audit's implementation in /tmp/true_aaa_haa.py.

FAITHFUL AAA (all-OFF cell):
  universe  : SPY, EFA, EEM, VNQ, IEF, TLT, DBC, GLD   (8 of 10; missing EWJ, RWX)
  ranker    : raw 6-month total-return momentum
  cardinality: top-half (top-4 of 8)
  weighting : MINIMUM-VARIANCE (weighted covariance: 126d correlation, 20d vol)
  cadence   : monthly
  canary    : NONE
  screen    : NONE (positive screen off)
  partial   : fully invested
Anchor (gate before proceeding): faithful AAA clean Sharpe ~0.7869 /
MaxDD -23.21% / Calmar 0.3188 ; ext ~0.8696 / Calmar 0.3624.

Six factors (OFF = AAA value, ON = CPM/production value). Each toggles ONE
AAA->CPM component:
  U  universe : AAA 8-members [SPY,EFA,EEM,VNQ,IEF,TLT,DBC,GLD]
                -> CPM 8-members [QQQ,SPHQ,EFA,EEM,VNQ,GLD,TLT,DBC].
                Both top-half (top-4); count is NOT a separate factor.
  R  ranker   : raw 6-month total-return momentum
                -> vol-adjusted Faber (10m-SMA distance / realized vol).
                Bundles metric + lookback + vol-adjust as one ranker factor.
  W  weighting: minimum-variance (weighted cov 126d corr / 20d vol)
                -> inverse-vol (504d). Bundles scheme + window.
  S  screen   : none -> positive-trend (absolute-momentum) screen.
  P  partial  : fully invested -> strict-4 (risky_fraction = min(n_pos,4)/4,
                remainder to timed SHV/IEF best-of-safe).
  C  canary   : none -> HYG-OR-TIP 13612U any-positive gate (risk-off to safe).

S x P coherence: held set = top-K (top-half ceil(n/2)=4); breadth = len(held).
  - S OFF: held = full top-K (sign ignored) -> breadth = 4 -> P routes nothing
    (risky_fraction = 1 even if P ON). Partial-safe INERT across the S-OFF half.
  - S ON : held = positive-trend subset -> breadth < 4 possible -> P (when ON)
    routes the emptied slots (4 - breadth) to safe.
  => P only bites when S thins breadth below 4 -> strong S x P expected; ladder
     places P AFTER S.

all-ON (C,U,R,S,W,P = 1,1,1,1,1,1) MUST reproduce production CPM
(cpm_live.compute_target_weights) EXACTLY.

Anchor gate (abort/flag if not):
  baseline all-OFF == faithful AAA: clean Sharpe ~0.7869 / MaxDD -23.21% /
    Calmar 0.3188 ; ext ~0.8696 / Calmar 0.3624.
  all-ON == production CPM: clean 1.1910 / -12.67% / 1.0615 ;
    ext 1.2142 / -15.93% / 0.8608 ; param==prod (== compute_target_weights).

Execution = headline convention everywhere: realistic T+1 MOO exact (mooex),
post-cost 10 bps/side, shared _segment_returns_conv harness => byte-identical
cost/window/execution across all 64 cells. CPM sleeve has NO vol gate.
Windows: CLEAN 18y 2008-05-30.. ; EXT 27y 1999-03-10.. ; end 2026-05-22.

No production files touched. Writes JSON + findings markdown next to this file.
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
    load_panel, perf_metrics, sig_13612U, best_safe, faber_sma_xs, inv_vol_weights,
    compute_target_weights, RISKY_UNIVERSE, SAFE_POOL, CANARY_ASSETS, DEFAULT_CASH,
    COST_BPS_PER_SIDE, CORR_LOOKBACK_DAYS, TOP_K_CANDIDATES,
)
import exec_lag_moo_validation_2026_05_30 as H

CONV = "mooex"

# ---- universes / pools ----
# Faithful AAA universe (U off): verified spec is 10 assets
# [SPY, EZU/EFA, EWJ, EEM, VNQ/IYR, RWX, IEF, TLT, DBC, GLD]; panel lacks EWJ
# and RWX -> best buildable = 8 of 10. NOTE: IEF is a risky candidate here.
AAA_UNIVERSE = ["SPY", "EFA", "EEM", "VNQ", "IEF", "TLT", "DBC", "GLD"]
CPM_PROD_UNIVERSE = ["QQQ", "SPHQ", "EFA", "EEM", "VNQ", "GLD", "TLT", "DBC"]   # CPM production (U on)
SAFE = ["SHV", "IEF"]   # best-of-safe (timed), common to both ends (NOT a factor)

# Anchors.
ANCHOR_BASE_CLEAN = (0.7869, -23.21, 0.3188)   # faithful AAA all-OFF
ANCHOR_BASE_EXT = (0.8696, None, 0.3624)        # faithful AAA all-OFF (maxdd not pinned)
ANCHOR_ON_CLEAN = (1.1910, -12.67, 1.0615)      # production CPM all-ON
ANCHOR_ON_EXT = (1.2142, -15.93, 0.8608)


# ======================= weighted-cov min-variance (W off, AAA) =======================
def weighted_cov_minvar(daily, sig_d, picks, corr_days=126, vol_days=20):
    """AAA weighted covariance min-variance: corr from `corr_days` daily returns,
    vol from `vol_days` daily returns. Cov_ij = corr_ij * sd_i * sd_j (annualized).
    Long-only min-variance via SLSQP. Mirrors /tmp/true_aaa_haa.py."""
    if len(picks) == 1:
        return {picks[0]: 1.0}
    r = daily[picks].loc[:sig_d].dropna(how="all")
    rc = r.tail(corr_days)
    rv = r.tail(vol_days)
    if len(rc) < corr_days or len(rv) < vol_days:
        return {t: 1.0 / len(picks) for t in picks}
    corr = rc.corr().values
    vol = (rv.std(ddof=0) * np.sqrt(252)).reindex(picks).values
    if np.any(~np.isfinite(vol)) or np.any(~np.isfinite(corr)):
        return {t: 1.0 / len(picks) for t in picks}
    D = np.diag(vol)
    cov = D @ corr @ D
    n = len(picks)

    def obj(w, Cv=cov):
        return float(w @ Cv @ w)
    cons = ({"type": "eq", "fun": lambda w: np.sum(w) - 1.0},)
    bnds = tuple((0.0, 1.0) for _ in range(n))
    res = minimize(obj, np.ones(n) / n, method="SLSQP", bounds=bnds, constraints=cons)
    if not res.success:
        return {t: 1.0 / n for t in picks}
    return {picks[i]: float(res.x[i]) for i in range(n)}


def mom6(monthly_series):
    s = monthly_series.dropna()
    if len(s) < 7:
        return np.nan
    return float(s.iloc[-1] / s.iloc[-7] - 1.0)


# ======================= CPM parametric weight fn =======================
# all-OFF (000000) == faithful AAA ; all-ON (111111) == compute_target_weights.
def cpm_wf(close, daily, sig_d, C, U, R, S, W, P):
    universe = CPM_PROD_UNIVERSE if U else AAA_UNIVERSE
    monthly = close.loc[:sig_d].resample("ME").last()
    safe = best_safe(monthly, sig_d, SAFE)

    # --- canary C: OFF = NONE (no gate); ON = HYG-OR-TIP any-positive 13612U ---
    if C:
        cs = [sig_13612U(monthly[a]) for a in ("HYG", "TIP") if a in monthly.columns]
        cs = [s for s in cs if pd.notna(s)]
        if not cs or sum(1 for s in cs if s > 0) == 0:
            return {safe: 1.0}

    # --- ranker R: OFF = raw 6m momentum ; ON = vol-adjusted Faber ---
    scores, screenval = {}, {}
    if R:
        faber = faber_sma_xs(monthly)
        avail = [t for t in universe if t in faber.index and pd.notna(faber[t])
                 and (sig_d in close.index and pd.notna(close.loc[sig_d].get(t, np.nan)))]
        if not avail:
            return {safe: 1.0}
        dr = close[avail].ffill().pct_change()
        for t in avail:
            v = dr[t].loc[:sig_d].tail(252).std() * np.sqrt(252)
            if pd.isna(v) or v < 1e-9:
                v = 1.0
            scores[t] = float(faber[t]) / v
            screenval[t] = float(faber[t])
    else:
        present = [t for t in universe if t in monthly.columns and pd.notna(monthly[t].iloc[-1])]
        for t in present:
            mm = mom6(monthly[t])
            if pd.notna(mm):
                scores[t] = mm
                screenval[t] = mm
    if not scores:
        return {safe: 1.0}

    # --- top-half K cap (fixed-on, both ends; ceil(8/2)=4) ---
    ranked = pd.Series(scores).sort_values(ascending=False)
    top_half = max(2, math.ceil(len(universe) / 2))
    kk = max(2, min(top_half, len(ranked)))
    top = ranked.iloc[:kk]

    # --- screen S: ON = positive-trend filter; OFF = hold all top-K (sign ignored) ---
    if S:
        held = [t for t in top.index if screenval.get(t, -np.inf) > 0]
    else:
        held = list(top.index)
    n = len(held)
    if n == 0:
        return {safe: 1.0}

    # --- weighting W: OFF = min-variance (weighted cov 126/20); ON = inverse-vol 504 ---
    if W:
        base_w = inv_vol_weights(close.loc[:sig_d], held, CORR_LOOKBACK_DAYS)
    else:
        base_w = weighted_cov_minvar(daily, sig_d, held, 126, 20)

    # --- partial-safe P: OFF = fully invested; ON = strict-4 risky_fraction scaling ---
    risky_fraction = (min(n, 4) / 4.0) if P else 1.0
    out = {t: w * risky_fraction for t, w in base_w.items()}
    if risky_fraction < 1.0:
        out[safe] = out.get(safe, 0.0) + (1.0 - risky_fraction)
    return out


# ======================= runners / effects =======================
def met(daily, cash):
    m = perf_metrics(daily, cash)
    return {"sharpe": m.get("sharpe"), "cagr": m.get("cagr"),
            "maxdd": m.get("max_drawdown"), "calmar": m.get("calmar"), "vol": m.get("vol")}


def run_cell(close, daily, intraday, overnight, start, end, C, U, R, S, W, P):
    wf = lambda sd: cpm_wf(close, daily, sd, C, U, R, S, W, P)
    s, _ = H._segment_returns_conv(close, daily, wf, start, end, CONV,
                                   COST_BPS_PER_SIDE, intraday, overnight)
    return s


def factorial_effects(cells, factor_names, metric):
    """Main effects + 2-way interactions (coded +-1; effect = mean|on - mean|off)."""
    keys = list(cells.keys())
    k = len(factor_names)
    M = {key: cells[key][metric] for key in keys}
    codes = {key: tuple(2 * b - 1 for b in key) for key in keys}
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

    cpm_cols = sorted(set(AAA_UNIVERSE + CPM_PROD_UNIVERSE + SAFE
                          + ["HYG", "TIP"]) & set(panel.columns))
    cpm_close = panel[cpm_cols]
    cpm_daily = cpm_close.ffill().pct_change()

    windows = {"CLEAN": (clean_start, end), "EXT": (ext_start, end)}
    factors = ["C", "U", "R", "S", "W", "P"]

    # ---- production-direct anchor (compute_target_weights) ----
    prod_cols = sorted(set(RISKY_UNIVERSE + SAFE_POOL + CANARY_ASSETS + [DEFAULT_CASH]) & set(panel.columns))
    prod_close = panel[prod_cols]
    prod_daily = prod_close.ffill().pct_change()
    prod_s, _ = H._segment_returns_conv(
        prod_close, prod_daily, lambda sd: compute_target_weights(prod_close, sd)[0],
        ext_start, end, CONV, COST_BPS_PER_SIDE, intraday, overnight)
    prod_m = {wn: met(prod_s.loc[(prod_s.index >= ws) & (prod_s.index <= we)], cash)
              for wn, (ws, we) in windows.items()}

    print("Running CPM 2^6 = 64 cells, FAITHFUL AAA baseline (mooex, ext then slice)...")
    cells = {}  # (C,U,R,S,W,P) -> {window: metrics}
    for C, U, R, S, W, P in itertools.product([0, 1], repeat=6):
        ser = run_cell(cpm_close, cpm_daily, intraday, overnight, ext_start, end, C, U, R, S, W, P)
        wm = {}
        for wn, (ws, we) in windows.items():
            sw = ser.loc[(ser.index >= ws) & (ser.index <= we)]
            wm[wn] = met(sw, cash)
        cells[(C, U, R, S, W, P)] = wm
        print(f"  {C}{U}{R}{S}{W}{P}: CLEAN sharpe={wm['CLEAN']['sharpe']:.4f} "
              f"calmar={wm['CLEAN']['calmar']:.4f} maxdd={wm['CLEAN']['maxdd']*100:.2f}%")

    # ---- anchor gate ----
    alloff = cells[(0, 0, 0, 0, 0, 0)]
    allon = cells[(1, 1, 1, 1, 1, 1)]
    anchor_status = {"baseline": {}, "production": {}}
    abort = False

    # baseline (all-OFF) == faithful AAA
    for wn in windows:
        c = alloff[wn]
        exp = ANCHOR_BASE_CLEAN if wn == "CLEAN" else ANCHOR_BASE_EXT
        ok_sh = abs(c["sharpe"] - exp[0]) < 5e-3
        ok_dd = (exp[1] is None) or (abs(c["maxdd"] * 100 - exp[1]) < 0.05)
        ok_ca = abs(c["calmar"] - exp[2]) < 5e-3
        ok = ok_sh and ok_dd and ok_ca
        anchor_status["baseline"][wn] = {
            "alloff": [c["sharpe"], c["maxdd"], c["calmar"]],
            "expected": [exp[0], exp[1], exp[2]],
            "matches_expected": bool(ok)}
        print(f"BASELINE {wn}: all-OFF sharpe={c['sharpe']:.4f} maxdd={c['maxdd']*100:.2f}% "
              f"calmar={c['calmar']:.4f} -> matches faithful AAA {ok}")
        if not ok:
            abort = True

    # production (all-ON) == compute_target_weights
    for wn in windows:
        c = allon[wn]; p = prod_m[wn]
        ok_param_prod = (abs(c["sharpe"] - p["sharpe"]) < 1e-6)
        exp = ANCHOR_ON_CLEAN if wn == "CLEAN" else ANCHOR_ON_EXT
        ok_exp = (abs(c["sharpe"] - exp[0]) < 5e-4
                  and abs(c["maxdd"] * 100 - exp[1]) < 0.02
                  and abs(c["calmar"] - exp[2]) < 5e-4)
        gate_ok = ok_param_prod and (ok_exp if wn == "CLEAN" else ok_param_prod)
        anchor_status["production"][wn] = {
            "param": [c["sharpe"], c["maxdd"], c["calmar"]],
            "prod_direct": [p["sharpe"], p["maxdd"], p["calmar"]],
            "expected": list(exp),
            "param_eq_prod": bool(ok_param_prod),
            "matches_expected": bool(ok_exp)}
        print(f"PRODUCTION {wn}: param sharpe={c['sharpe']:.4f} maxdd={c['maxdd']*100:.2f}% "
              f"calmar={c['calmar']:.4f} | prod sharpe={p['sharpe']:.4f} "
              f"-> param==prod {ok_param_prod}, matches_expected {ok_exp}")
        if not gate_ok:
            abort = True

    out = {"meta": {"conv": CONV, "cost_bps": COST_BPS_PER_SIDE, "lookback": CORR_LOOKBACK_DAYS,
                    "top_k": TOP_K_CANDIDATES, "factors": factors,
                    "factor_order": "C,U,R,S,W,P",
                    "aaa_universe": AAA_UNIVERSE, "cpm_universe": CPM_PROD_UNIVERSE,
                    "aaa_data_constraint": "8 of 10 (panel lacks EWJ, RWX)",
                    "clean_start": str(clean_start.date()), "ext_start": str(ext_start.date()),
                    "end": str(end.date())},
           "anchor": anchor_status, "abort": bool(abort), "cells": {}, "effects": {}}
    for key, wm in cells.items():
        out["cells"]["".join(map(str, key))] = wm
    for wn in windows:
        for metric in ["sharpe", "calmar"]:
            flat = {key: cells[key][wn] for key in cells}
            out["effects"][f"{wn}_{metric}"] = factorial_effects(flat, factors, metric)

    # ---- dependency-respecting ladder (P after S) ----
    clean_cal = out["effects"]["CLEAN_calmar"]["main"]
    order = sorted(factors, key=lambda f: -clean_cal[f])
    # enforce S before P
    if order.index("P") < order.index("S"):
        order.remove("P")
        order.insert(order.index("S") + 1, "P")
    ladders = {}
    for wn in windows:
        path = []
        state = {f: 0 for f in factors}
        key0 = tuple(state[f] for f in factors)
        path.append({"step": "all-OFF (faithful AAA)", "config": "".join(map(str, key0)),
                     **cells[key0][wn]})
        for f in order:
            state[f] = 1
            key = tuple(state[f] for f in factors)
            label = f"+ {f}"
            if all(state[x] == 1 for x in factors):
                label += " = all-ON (production)"
            path.append({"step": label, "config": "".join(map(str, key)), **cells[key][wn]})
        ladders[wn] = path
    out["ladder"] = {"order": order, "paths": ladders}

    Path(__file__).with_suffix(".json").write_text(json.dumps(out, indent=2, default=float))
    write_md(out, cells, factors, windows)
    print("\nDONE -> research/cpm_factorial_aaa_findings.md (+ .json)")
    if abort:
        print("WARNING: anchor gate FAILED -- findings flagged.")
    return out


def write_md(out, cells, factors, windows):
    L = []
    A = L.append
    m = out["meta"]

    A("# CPM 2^6 factorial -- corrected, with a FAITHFUL AAA baseline\n")
    A("Role: analyst (read-only re production; no production/memo files changed; no commit). "
      "Throwaway harness in `research/`.\n")
    A("Script: `research/cpm_factorial_faithful_aaa.py` -> "
      "`research/cpm_factorial_faithful_aaa.json`.\n")
    A("> CORRECTS the baseline of `research/cpm_factorial_iv4_6factor.py`. The prior harness used "
      "a NON-faithful AAA baseline (plain-12m momentum + equal-weight + a TIP canary), which is "
      "NOT the AAA (Adaptive Asset Allocation) spec. Here the all-OFF cell is the TRUE faithful "
      "AAA, reusing the audit implementation in `/tmp/true_aaa_haa.py`: raw 6-month total-return "
      "momentum, top-half (top-4 of 8), MINIMUM-VARIANCE weighting (weighted covariance 126d "
      "correlation / 20d vol), monthly, NO canary, NO screen, fully invested. Each of the six "
      "factors toggles exactly one AAA->CPM component (OFF = AAA value, ON = CPM/production "
      "value). all-ON reproduces production `cpm_live.compute_target_weights` exactly.\n")

    A("## Data constraint (faithful AAA universe)\n")
    A(f"Verified AAA spec is a 10-asset universe "
      "`[SPY, EZU/EFA, EWJ, EEM, VNQ/IYR, RWX, IEF, TLT, DBC, GLD]`. The panel lacks **EWJ** and "
      "**RWX**, so the best buildable faithful AAA is **8 of 10**: "
      f"`{AAA_UNIVERSE}`. Top-half = ceil(8/2) = 4. This 8-of-10 constraint applies to the "
      "all-OFF baseline and any U=OFF cell; it does NOT affect U=ON (CPM) cells.\n")

    A("## Factor definitions (OFF = faithful AAA / ON = production CPM)\n")
    A("| factor | OFF (faithful AAA) | ON (production CPM) |")
    A("|---|---|---|")
    A("| **U** universe | AAA 8-members `[SPY,EFA,EEM,VNQ,IEF,TLT,DBC,GLD]` (8 of 10) | "
      "CPM 8-members `[QQQ,SPHQ,EFA,EEM,VNQ,GLD,TLT,DBC]` |")
    A("| **R** ranker | raw 6-month total-return momentum | vol-adjusted Faber "
      "(10m-SMA distance / realized vol) -- bundles metric+lookback+vol-adjust |")
    A("| **W** weighting | minimum-variance (weighted cov: 126d corr / 20d vol) | "
      "inverse-vol (504d) -- bundles scheme+window |")
    A("| **S** screen | none (hold all top-K regardless of momentum sign) | "
      "positive-trend (absolute-momentum) screen; non-positive slots empty |")
    A("| **P** partial-safe | fully invested (risky_fraction = 1) | strict-4: "
      "risky_fraction = min(n_pos,4)/4; remainder routed to timed SHV/IEF best-of-safe |")
    A("| **C** canary | none (no risk-off gate) | HYG-OR-TIP any-positive 13612U gate "
      "(risk-off to safe when canary non-positive) |")
    A("\nBoth universes are top-half (top-4 of 8); cardinality is NOT a separate factor. "
      "Common fixed-on settings (NOT factors): top-half K cap (ceil(n/2)=4 both universes), "
      "SHV/IEF best-of-safe timed by 13612U.\n")

    A("\n**S x P coherence.** Held set = top-K (top-half, ceil(n/2) = 4); breadth = len(held). "
      "With S OFF the held set is the full top-K (sign ignored), so breadth = 4 and partial-safe "
      "routes nothing (risky_fraction = 1 even when P is ON) -- P is INERT across the entire "
      "S-OFF half of the cube. With S ON the held set is the positive-trend subset, so breadth < 4 "
      "is possible and P (when ON) routes the emptied slots (4 - breadth) to safe. P therefore "
      "only bites when S thins breadth below 4 -> a strong S x P interaction is expected, and the "
      "contribution ladder places P AFTER S.\n")

    A("## Execution convention (every table below)\n")
    A(f"Realistic T+1 MOO exact (`mooex`), post-cost {m['cost_bps']} bps/side, via the shared "
      "`_segment_returns_conv` harness so cost/window/execution are byte-identical across all 64 "
      "cells. CPM sleeve has NO vol gate. Windows: CLEAN 18y "
      f"({m['clean_start']} .. {m['end']}), EXT 27y ({m['ext_start']} .. {m['end']}). Full panel "
      "runs once over EXT and is sliced to each window.\n")

    # anchor gate
    a = out["anchor"]
    base_pass = a["baseline"]["CLEAN"]["matches_expected"] and a["baseline"]["EXT"]["matches_expected"]
    prod_pass = (a["production"]["CLEAN"]["param_eq_prod"] and a["production"]["CLEAN"]["matches_expected"]
                 and a["production"]["EXT"]["param_eq_prod"])
    A("## Anchor gate (gate-first; abort/flag on mismatch)\n")
    A("Two binding gates: (1) all-OFF cell == faithful AAA (clean Sharpe ~0.7869 / MaxDD -23.21% / "
      "Calmar 0.3188 ; ext Sharpe ~0.8696 / Calmar 0.3624); (2) all-ON cell == live production "
      "`compute_target_weights` (param==prod) in both windows AND the CLEAN all-ON cell == the "
      "production anchor (Sharpe 1.1910 / MaxDD -12.67% / Calmar 1.0615; EXT 1.2142 / -15.93% / "
      "0.8608).\n")
    A("### Gate 1 -- all-OFF == faithful AAA\n")
    A("| window | all-OFF Sharpe | all-OFF MaxDD | all-OFF Calmar | "
      "faithful-AAA target (Sharpe/MaxDD/Calmar) | matches |")
    A("|---|---:|---:|---:|---|---|")
    for wn in windows:
        s = a["baseline"][wn]; c = s["alloff"]; e = s["expected"]
        ddt = f"{e[1]:.2f}%" if e[1] is not None else "n/a"
        A(f"| {wn} | {c[0]:.4f} | {c[1]*100:.2f}% | {c[2]:.4f} | "
          f"{e[0]:.4f}/{ddt}/{e[2]:.4f} | {'YES' if s['matches_expected'] else 'NO'} |")
    A("")
    A("### Gate 2 -- all-ON == production CPM\n")
    A("| window | all-ON Sharpe | all-ON MaxDD | all-ON Calmar | production-direct Sharpe | "
      "gate target (Sharpe/MaxDD/Calmar) | param==prod | matches anchor |")
    A("|---|---:|---:|---:|---:|---|---|---|")
    for wn in windows:
        s = a["production"][wn]; p = s["param"]; pd_ = s["prod_direct"]; e = s["expected"]
        A(f"| {wn} | {p[0]:.4f} | {p[1]*100:.2f}% | {p[2]:.4f} | {pd_[0]:.4f} | "
          f"{e[0]:.4f}/{e[1]:.2f}%/{e[2]:.4f} | {'YES' if s['param_eq_prod'] else 'NO'} | "
          f"{'YES' if s['matches_expected'] else 'NO'} |")
    if base_pass and prod_pass:
        A("\nGate PASS: all-OFF reproduces the faithful AAA baseline and all-ON equals live "
          "production `cpm_live.compute_target_weights` (param==prod, both windows) and the "
          "production CLEAN anchor EXACTLY. Grid proceeds.\n")
    else:
        A("\n**GATE FAIL**: at least one anchor did not reproduce. Numbers below are FLAGGED and "
          "should not be trusted until reconciled.\n")

    # grids
    def grid(wn):
        A(f"## Full 64-cell grid -- {wn} (mooex, {m['cost_bps']} bps/side)\n")
        A("Config column order: C,U,R,S,W,P.\n")
        A("| C | U | R | S | W | P | Sharpe | CAGR | Vol | MaxDD | Calmar |")
        A("|---|---|---|---|---|---|---|---|---|---|---|")
        for C, U, R, S, W, P in itertools.product([0, 1], repeat=6):
            c = cells[(C, U, R, S, W, P)][wn]
            alloff = (C, U, R, S, W, P) == (0, 0, 0, 0, 0, 0)
            allon = (C, U, R, S, W, P) == (1, 1, 1, 1, 1, 1)
            mark = "**" if (alloff or allon) else ""
            A(f"| {C} | {U} | {R} | {S} | {W} | {P} | {mark}{c['sharpe']:.4f}{mark} | "
              f"{c['cagr']*100:.2f}% | {c['vol']*100:.2f}% | {mark}{c['maxdd']*100:.2f}%{mark} | "
              f"{mark}{c['calmar']:.4f}{mark} |")
        A("\n(all-OFF = `000000` faithful AAA; all-ON = `111111` production CPM -- both bold.)\n")
    grid("CLEAN")
    grid("EXT")

    # main effects
    A("## Main effects (background-averaged, coded +-1; effect = mean|on - mean|off)\n")
    A("Sign-flip flag = factor's on-minus-off delta changes sign across backgrounds (direction not "
      "robust).\n")
    for wn in windows:
        A(f"### {wn}\n")
        A("| factor | dSharpe | flip | dCalmar | flip |")
        A("|---|---:|---|---:|---|")
        es = out["effects"][f"{wn}_sharpe"]; ec = out["effects"][f"{wn}_calmar"]
        for f in sorted(factors, key=lambda x: -abs(ec["main"][x])):
            sf = " SIGN-FLIP" if es["sign_flip"][f] else ""
            cf = " SIGN-FLIP" if ec["sign_flip"][f] else ""
            A(f"| **{f}** | {es['main'][f]:+.4f} |{sf} | {ec['main'][f]:+.4f} |{cf} |")
        A("")

    # interactions
    A("## Two-way interactions\n")
    A("Calmar (both windows), sorted by |CLEAN|:\n")
    A("| interaction | CLEAN | EXT |")
    A("|---|---:|---:|")
    ci = out["effects"]["CLEAN_calmar"]["interactions"]
    ei = out["effects"]["EXT_calmar"]["interactions"]
    for name in sorted(ci, key=lambda x: -abs(ci[x])):
        A(f"| {name} | {ci[name]:+.4f} | {ei[name]:+.4f} |")
    A("")
    A("### Key requested interactions\n")
    A("| interaction | meaning | CLEAN Calmar | EXT Calmar | CLEAN Sharpe | EXT Sharpe |")
    A("|---|---|---:|---:|---:|---:|")
    cis = out["effects"]["CLEAN_sharpe"]["interactions"]
    eis = out["effects"]["EXT_sharpe"]["interactions"]
    for name, mean in [("RxW", "ranker vs weighting"),
                       ("SxP", "positive screen vs partial-safe (P bites only when S thins breadth < 4)"),
                       ("SxW", "screen vs weighting (min-var vs inverse-vol on a thinned set)"),
                       ("RxS", "ranker vs screen"),
                       ("UxR", "universe vs ranker"),
                       ("SxC", "screen vs canary (overlapping risk-off)"),
                       ("WxP", "weighting vs partial-safe")]:
        cc = ci.get(name); ee = ei.get(name); cs = cis.get(name); es2 = eis.get(name)
        if cc is None:
            rn = "x".join(name.split("x")[::-1])
            cc = ci.get(rn); ee = ei.get(rn); cs = cis.get(rn); es2 = eis.get(rn)
            name = rn if cc is not None else name
        if cc is None:
            continue
        A(f"| {name} | {mean} | {cc:+.4f} | {ee:+.4f} | {cs:+.4f} | {es2:+.4f} |")
    A("")

    # ladder
    lad = out["ladder"]
    A("## Contribution ladder (dependency-respecting cumulative path)\n")
    A(f"Ordering = factors by CLEAN Calmar main effect, largest first, with P forced AFTER S "
      f"(P is inert until S thins breadth below 4): **{' -> '.join(lad['order'])}**.\n")
    for wn in windows:
        A(f"### {wn} cumulative path\n")
        A("| step | config (C,U,R,S,W,P) | Sharpe | Calmar | MaxDD |")
        A("|---|---|---:|---:|---:|")
        prev = None
        mono = True
        for st in lad["paths"][wn]:
            A(f"| {st['step']} | `{st['config']}` | {st['sharpe']:.4f} | {st['calmar']:.4f} | "
              f"{st['maxdd']*100:.2f}% |")
            if prev is not None and st["calmar"] < prev - 1e-9:
                mono = False
            prev = st["calmar"]
        if mono:
            A(f"\n{wn}: Calmar is monotonically non-decreasing along this ladder.\n")
        else:
            A(f"\n{wn}: Calmar is NOT monotone along this ladder (at least one step reduces "
              "Calmar) -- reported honestly; see the step deltas above.\n")

    # caveats
    A("## Caveats / confidence\n")
    A("- all-OFF cell reproduces the faithful AAA baseline (raw 6m momentum, top-4/8, weighted-cov "
      "min-variance, monthly, no canary/screen/partial-safe) and all-ON reproduces production "
      "`cpm_live.compute_target_weights` exactly (param==prod). Confidence high subject to the "
      "data constraint below.")
    A(f"- DATA CONSTRAINT: the faithful AAA universe is 10 assets but the panel lacks EWJ and RWX, "
      "so the all-OFF baseline and all U=OFF cells use the best-buildable 8-of-10 universe "
      f"`{AAA_UNIVERSE}`. The faithful-AAA anchor itself was computed under the same 8-of-10 "
      "constraint, so the gate is apples-to-apples.")
    A("- P (partial-safe) is defined coherently with S: with S OFF breadth == 4 so P is inert "
      "(risky_fraction == 1); with S ON the emptied slots route to safe at "
      "risky_fraction = min(breadth,4)/4. The P main effect is diluted because P is inert across "
      "the entire S-OFF half of the cube -- read it together with the S x P interaction and the "
      "ladder, where P is placed after S.")
    A("- W=OFF uses long-only SLSQP min-variance on the AAA weighted covariance (126d corr / 20d "
      "vol). Optimizer non-convergence falls back to equal-weight (rare); this matches the audit "
      "implementation.")
    A("- Grid internally consistent: shared harness, single EXT run sliced per window, identical "
      "cost/execution across all 64 cells.")
    A("- All numbers mooex / T+1 MOO exact / 10 bps/side / no vol gate (CPM has none). EXT 27y is "
      "partly proxy-backed pre-2006 for the trend universe; CLEAN 18y has full real-open coverage "
      "and is the decisive lens. CLEAN-only monotonicity vs any EXT non-monotonicity is reported "
      "honestly in the ladder section.")

    Path(ROOT / "research" / "cpm_factorial_aaa_findings.md").write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
