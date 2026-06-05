# -*- coding: utf-8 -*-
"""ANALYST (read-only re production; NO production files touched; NO commit).

CORRECTED HAA -> CPM coupled factorial, re-anchored to CURRENT PROD CPM
(cpm_live.py @ commit 24c1207: EQUAL-WEIGHT risky block, TIP-ONLY canary,
MIN-VAR 3-of-4 selection at n_pos=4).

Why this supersedes research/cpm_haa_coupled_factorial.py
---------------------------------------------------------
The old coupled factorial used factor set {T trend, V vol-adj, W weighting,
C canary, U universe} and an all-ON endpoint of 1.1658 (an OLD CPM:
inverse-vol weighting + HYG-or-TIP canary + NO min-var selection). Current
prod CPM has changed:
  - canary  : HYG-or-TIP  ->  TIP-only   (== HAA canary)        -> NO LONGER a diff
  - weights : inverse-vol ->  equal-weight (== HAA weighting)   -> NO LONGER a diff
  - selection: hold-all-4 ->  min-var 3-of-4 at n_pos=4 (NEW)   -> NEW HAA->CPM diff

A factorial is HAA -> CPM, so factors must be exactly what CURRENTLY differs
between the HAA baseline and current prod CPM. Therefore:
  DROP   C (canary)     : both ends TIP-only.
  DROP   W (weighting)  : both ends equal-weight.
  ADD    M (min-var 3-of-4 selection at n_pos=4): CPM-only.
  KEEP   U (universe)   : HAA-8 -> CPM cross-asset-8.
  KEEP   R (ranker)     : 13612U rank+screen -> vol-adjusted Faber rank +
                          raw-Faber screen (one coupled "ranker" factor; this
                          bundles the old T metric switch AND the old V
                          vol-adjust, since prod's vol-adjust exists only in
                          the Faber path).

CONFIRMED no-ops (verified empirically below, hence NOT factors):
  - SAFE selector : HAA baseline and CPM both use best-of {SHV, IEF} by 13612U,
                    universe-independent. Identical month-by-month.
  - BREADTH / partial-safe (strict-4): both use risky_fraction = min(n_pos,4)/4
                    with remainder -> safe. Identical mechanism; the only
                    n_pos=4 difference is min-var, isolated as factor M.

CORRECTED FACTOR SET (3 genuine factors -> 2^3 = 8 cells):
  U  UNIVERSE  OFF = HAA-8 [SPY,IWM,VEA,VWO,VNQ,DBC,IEF,TLT]
               ON  = CPM-8 [QQQ,SPHQ,EFA,EEM,VNQ,GLD,TLT,DBC]
  R  RANKER    OFF = 13612U (rank by 13612U ; screen = 13612U > 0)          [HAA]
               ON  = vol-adjusted Faber (rank = faber/rv_252 ; screen=faber>0) [CPM]
  M  MIN-VAR   OFF = at n_pos=4 hold all 4 equal-weight                      [HAA]
               ON  = at n_pos=4 pick min-var 3-of-4 (equal-weight var obj)   [CPM]

  Held FIXED (== HAA == current CPM, NOT factors):
    canary = TIP-only (13612U>0) ; weighting = equal-weight ;
    safe = best-of {SHV,IEF} by 13612U ; top-4 cap ;
    partial-safe breadth (risky_fraction = min(n_pos,4)/4, remainder->safe).

GATES (must pass):
  all-OFF (U0,R0,M0) == canonical HAA baseline, weight-by-weight
    (CLEAN Sharpe 0.8670 / MaxDD -14.68% / Calmar 0.6386).
  all-ON  (U1,R1,M1) == production CPM compute_target_weights, weight-by-weight
    (CLEAN Sharpe 1.255673 / MaxDD -13.0317% / Calmar 1.007646).

NO-OP DEMONSTRATION (separate, not part of the cube):
  all-ON + canary flipped to HYG-or-TIP  -> shows canary is a live lever in
    general, but current prod chose the HAA value (TIP-only), so it is constant
    along HAA->CPM and contributes nothing.
  all-ON + weighting flipped to inverse-vol -> same argument for weighting.
"""
import sys
import json
import itertools
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from cpm_live import (  # noqa: E402
    load_panel, perf_metrics, sig_13612U, best_safe, faber_sma_xs,
    inv_vol_weights, _min_var_subset, compute_target_weights,
    RISKY_UNIVERSE, SAFE_POOL, CANARY_ASSETS, DEFAULT_CASH,
    COST_BPS_PER_SIDE, CORR_LOOKBACK_DAYS, TOP_K_CANDIDATES,
)
import exec_lag_moo_validation_2026_05_30 as H  # noqa: E402

CONV = "mooex"

HAA_UNIVERSE = ["SPY", "IWM", "VEA", "VWO", "VNQ", "DBC", "IEF", "TLT"]   # U OFF
CPM_UNIVERSE = ["QQQ", "SPHQ", "EFA", "EEM", "VNQ", "GLD", "TLT", "DBC"]  # U ON
SAFE = ["SHV", "IEF"]   # best-of-safe by 13612U; shared HAA == CPM
TOP_K = 4

# anchors (CLEAN window): (sharpe, maxdd_pct, calmar)
HAA_ANCHOR_CLEAN = (0.8670, -14.68, 0.6386)
CPM_ANCHOR_CLEAN = (1.255673, -13.0317, 1.007646)

FACTORS = ["U", "R", "M"]
FACTOR_LABEL = {
    "U": "universe (HAA-8 -> CPM cross-asset-8)",
    "R": "ranker (13612U -> vol-adjusted Faber, couples rank+screen)",
    "M": "min-var 3-of-4 selection at n_pos=4 (hold-all -> min-var subset)",
}


# ============================= canonical HAA (standalone) =============================
def haa_wf(close, sig_d):
    monthly = close.loc[:sig_d].resample("ME").last()
    safe = best_safe(monthly, sig_d, SAFE)
    tip = sig_13612U(monthly["TIP"]) if "TIP" in monthly.columns else np.nan
    if pd.isna(tip) or tip <= 0:
        return {safe: 1.0}
    present = [t for t in HAA_UNIVERSE if t in monthly.columns]
    mom = {}
    for t in present:
        m = sig_13612U(monthly[t])
        if pd.notna(m) and (sig_d in close.index and pd.notna(close.loc[sig_d].get(t, np.nan))):
            mom[t] = float(m)
    if not mom:
        return {safe: 1.0}
    ranked = pd.Series(mom).sort_values(ascending=False)
    top = ranked.iloc[:min(TOP_K, len(ranked))]
    out = {}
    for t in top.index:
        if top[t] > 0:
            out[t] = out.get(t, 0.0) + 0.25
        else:
            out[safe] = out.get(safe, 0.0) + 0.25
    missing_slots = TOP_K - len(top)
    if missing_slots > 0:
        out[safe] = out.get(safe, 0.0) + 0.25 * missing_slots
    return out


# ===================== coupled parametric HAA<->CPM weight fn =====================
def param_wf(close, sig_d, U, R, M, C=0, W=0):
    """all-OFF (U0,R0,M0,C0,W0) == canonical HAA ;
       all-ON  (U1,R1,M1,C0,W0) == cpm_live.compute_target_weights.

    C and W are NOT cube factors -- defaults reproduce both HAA and CPM
    (TIP-only canary, equal-weight). They are exposed ONLY for the no-op
    demonstration runs (flip to HYG-or-TIP / inverse-vol).
    """
    universe = CPM_UNIVERSE if U else HAA_UNIVERSE
    monthly = close.loc[:sig_d].resample("ME").last()
    safe = best_safe(monthly, sig_d, SAFE)

    # --- canary (FIXED TIP-only unless C demo flips to HYG-or-TIP) ---
    canary_assets = ["HYG", "TIP"] if C else ["TIP"]
    cs = [sig_13612U(monthly[a]) for a in canary_assets if a in monthly.columns]
    cs = [s for s in cs if pd.notna(s)]
    if not cs or sum(1 for s in cs if s > 0) == 0:
        return {safe: 1.0}

    present = [t for t in universe if t in monthly.columns]
    faber = faber_sma_xs(monthly)

    if R:
        avail = [t for t in present
                 if t in faber.index and pd.notna(faber[t])
                 and (sig_d in close.index and pd.notna(close.loc[sig_d].get(t, np.nan)))]
    else:
        avail = [t for t in present
                 if (sig_d in close.index and pd.notna(close.loc[sig_d].get(t, np.nan)))
                 and pd.notna(sig_13612U(monthly[t]))]
    if not avail:
        return {safe: 1.0}

    rank_score, screen_val = {}, {}
    if R:
        daily_rets = close[avail].ffill().pct_change()
        for t in avail:
            v = daily_rets[t].loc[:sig_d].tail(252).std() * np.sqrt(252)
            if pd.isna(v) or v < 1e-9:
                v = 1.0
            rank_score[t] = float(faber[t]) / v
            screen_val[t] = float(faber[t])
    else:
        for t in avail:
            m = sig_13612U(monthly[t])
            if pd.isna(m):
                continue
            rank_score[t] = float(m)
            screen_val[t] = float(m)
    if not rank_score:
        return {safe: 1.0}

    ranked = pd.Series(rank_score).sort_values(ascending=False)
    top_k = max(2, min(TOP_K, len(ranked)))
    top = ranked.iloc[:top_k]

    positive = top[top.index.map(lambda t: screen_val.get(t, -np.inf) > 0)]
    if len(positive) == 0:
        return {safe: 1.0}

    positive_picks = list(positive.index)
    n_pos = len(positive_picks)

    # --- M min-var 3-of-4 selection at n_pos=4 (CPM-only) ---
    if M and n_pos == 4:
        picks = _min_var_subset(close, sig_d, positive_picks, CORR_LOOKBACK_DAYS, 3)
    else:
        picks = positive_picks

    risky_fraction = min(n_pos, 4) / 4.0
    safe_fraction = 1.0 - risky_fraction

    # --- weighting (FIXED equal unless W demo flips to inverse-vol) ---
    if W:
        base_w = inv_vol_weights(close.loc[:sig_d], picks, CORR_LOOKBACK_DAYS)
    else:
        base_w = {t: 1.0 / len(picks) for t in picks}

    out = {t: w * risky_fraction for t, w in base_w.items()}
    if safe_fraction > 0:
        out[safe] = out.get(safe, 0.0) + safe_fraction
    return out


# ================================== runners ==================================
def met(daily, cash):
    m = perf_metrics(daily, cash)
    return {"sharpe": m.get("sharpe"), "cagr": m.get("cagr"), "vol": m.get("vol"),
            "maxdd": m.get("max_drawdown"), "calmar": m.get("calmar"), "martin": m.get("martin")}


def run_series(close, daily, intraday, overnight, wf, start, end):
    s, _ = H._segment_returns_conv(close, daily, wf, start, end, CONV,
                                   COST_BPS_PER_SIDE, intraday, overnight)
    return s


def factorial_effects(cells, metric):
    keys = list(cells.keys())
    k = len(FACTORS)
    M = {key: cells[key][metric] for key in keys}
    codes = {key: tuple(2 * b - 1 for b in key) for key in keys}
    half = 2 ** (k - 1)
    main = {FACTORS[i]: sum(codes[key][i] * M[key] for key in keys) / half for i in range(k)}
    inter = {}
    for i, j in itertools.combinations(range(k), 2):
        inter[f"{FACTORS[i]}x{FACTORS[j]}"] = sum(
            codes[key][i] * codes[key][j] * M[key] for key in keys) / half
    triple = sum(codes[key][0] * codes[key][1] * codes[key][2] * M[key] for key in keys) / half
    inter["UxRxM"] = triple
    flips = {}
    for i in range(k):
        deltas = []
        for key in keys:
            if key[i] == 0:
                on_key = tuple(1 if t == i else key[t] for t in range(k))
                deltas.append(M[on_key] - M[key])
        signs = set(np.sign(round(d, 6)) for d in deltas if abs(d) > 1e-9)
        flips[FACTORS[i]] = bool(any(s > 0 for s in signs) and any(s < 0 for s in signs))
    return {"main": main, "interactions": inter, "sign_flip": flips}


def main():
    end = pd.Timestamp("2026-05-22")
    ext_start = pd.Timestamp("1999-03-10")
    clean_start = pd.Timestamp("2008-05-30")

    panel = load_panel(start=ext_start, end=end)
    end = min(end, panel.index[-1])
    cash = panel[DEFAULT_CASH].ffill().pct_change().dropna()

    open_df, close_yf = H.load_open_close()
    intraday = (close_yf / open_df - 1.0).reindex(panel.index)
    overnight = (open_df / close_yf.shift(1) - 1.0).reindex(panel.index)

    cols = sorted(set(HAA_UNIVERSE + CPM_UNIVERSE + SAFE + ["HYG", "TIP"]) & set(panel.columns))
    close = panel[cols]
    daily = close.ffill().pct_change()
    print("panel cols:", cols)
    missing_haa = [t for t in HAA_UNIVERSE if t not in cols]
    if missing_haa:
        print("WARN missing HAA tickers:", missing_haa)

    windows = {"CLEAN": (clean_start, end), "EXT": (ext_start, end)}

    def windowed(ser):
        return {wn: met(ser.loc[(ser.index >= ws) & (ser.index <= we)], cash)
                for wn, (ws, we) in windows.items()}

    # ---- production-direct CPM anchor ----
    prod_cols = sorted(set(RISKY_UNIVERSE + SAFE_POOL + CANARY_ASSETS + [DEFAULT_CASH]) & set(panel.columns))
    prod_close = panel[prod_cols]
    prod_daily = prod_close.ffill().pct_change()
    prod_s = run_series(prod_close, prod_daily, intraday, overnight,
                        lambda sd: compute_target_weights(prod_close, sd)[0], ext_start, end)
    prod_m = windowed(prod_s)

    # ---- standalone canonical HAA ----
    haa_s = run_series(close, daily, intraday, overnight,
                       lambda sd: haa_wf(close, sd), ext_start, end)
    haa_m = windowed(haa_s)

    # ---- 2^3 factorial (U, R, M) ----
    print("Running 2^3 = 8 cells (mooex)...")
    cells = {}
    series = {}
    for bits in itertools.product([0, 1], repeat=3):
        wf = lambda sd, b=bits: param_wf(close, sd, *b)
        ser = run_series(close, daily, intraday, overnight, wf, ext_start, end)
        series[bits] = ser
        cells[bits] = windowed(ser)
        print(f"  {''.join(map(str,bits))}: CLEAN sharpe={cells[bits]['CLEAN']['sharpe']:.4f} "
              f"calmar={cells[bits]['CLEAN']['calmar']:.4f} maxdd={cells[bits]['CLEAN']['maxdd']*100:.2f}%")

    alloff = cells[(0, 0, 0)]
    allon = cells[(1, 1, 1)]

    # ---- monthly signal dates ----
    monthly_idx = (pd.DataFrame({"x": 1}, index=close.index)
                   .groupby(pd.Grouper(freq="ME")).tail(1))
    sigs = monthly_idx.index[(monthly_idx.index >= ext_start) & (monthly_idx.index <= end)].tolist()

    # ---- GATE A: all-OFF == canonical HAA (weight-by-weight) ----
    haa_mismatch = 0
    for sd in sigs:
        a = {k: round(v, 8) for k, v in param_wf(close, sd, 0, 0, 0).items() if abs(v) > 1e-9}
        b = {k: round(v, 8) for k, v in haa_wf(close, sd).items() if abs(v) > 1e-9}
        if a != b:
            haa_mismatch += 1

    # ---- GATE B: all-ON == production compute_target_weights (weight-by-weight) ----
    cpm_mismatch = 0
    for sd in sigs:
        a = {k: round(v, 6) for k, v in param_wf(close, sd, 1, 1, 1).items() if abs(v) > 1e-9}
        b = {k: round(v, 6) for k, v in compute_target_weights(prod_close, sd)[0].items() if abs(v) > 1e-9}
        if a != b:
            cpm_mismatch += 1

    gate_haa = (haa_mismatch == 0)
    gate_cpm = (cpm_mismatch == 0)

    c = allon["CLEAN"]
    anchor_ok = (abs(c["sharpe"] - CPM_ANCHOR_CLEAN[0]) < 5e-4
                 and abs(c["maxdd"] * 100 - CPM_ANCHOR_CLEAN[1]) < 0.05
                 and abs(c["calmar"] - CPM_ANCHOR_CLEAN[2]) < 5e-4)
    o = alloff["CLEAN"]
    haa_anchor_ok = (abs(o["sharpe"] - HAA_ANCHOR_CLEAN[0]) < 5e-4
                     and abs(o["maxdd"] * 100 - HAA_ANCHOR_CLEAN[1]) < 0.05
                     and abs(o["calmar"] - HAA_ANCHOR_CLEAN[2]) < 5e-4)

    # ---- effects ----
    effects = {}
    for wn in windows:
        for metric in ("sharpe", "calmar", "maxdd"):
            flat = {key: cells[key][wn] for key in cells}
            effects[f"{wn}_{metric}"] = factorial_effects(flat, metric)

    # ---- sequential ladder (HAA -> +U -> +R -> +M = CPM) ----
    def build_ladder(order, wn):
        path = []
        state = [0, 0, 0]
        path.append({"step": "HAA baseline (all-OFF)", "config": "000", **cells[tuple(state)][wn]})
        for f in order:
            idx = FACTORS.index(f)
            state[idx] = 1
            key = tuple(state)
            label = f"+{f} {FACTOR_LABEL[f].split(' (')[0]}"
            if all(state):
                label += " = CPM (all-ON)"
            path.append({"step": label, "config": "".join(map(str, key)), **cells[key][wn]})
        return path

    ladder_order = ["U", "R", "M"]
    ladders = {wn: build_ladder(ladder_order, wn) for wn in windows}
    # alternate orders to show order-(in)dependence
    alt_orders = {"R_U_M": ["R", "U", "M"], "M_R_U": ["M", "R", "U"]}
    alt_ladders = {nm: {wn: build_ladder(order, wn) for wn in windows}
                   for nm, order in alt_orders.items()}

    # ---- min-var (M) marginal at each (U,R) corner, CLEAN ----
    minvar_marginal = {}
    for U in (0, 1):
        for R in (0, 1):
            off = cells[(U, R, 0)]["CLEAN"]
            on = cells[(U, R, 1)]["CLEAN"]
            minvar_marginal[f"U{U}R{R}"] = {
                "sharpe_off": off["sharpe"], "sharpe_on": on["sharpe"],
                "d_sharpe": on["sharpe"] - off["sharpe"],
                "d_maxdd_pct": (on["maxdd"] - off["maxdd"]) * 100,
                "d_calmar": on["calmar"] - off["calmar"],
            }

    # ---- NO-OP demonstration: canary & weighting on the all-ON CPM config ----
    cpm_canary_flip = run_series(close, daily, intraday, overnight,
                                 lambda sd: param_wf(close, sd, 1, 1, 1, C=1, W=0), ext_start, end)
    cpm_weight_flip = run_series(close, daily, intraday, overnight,
                                 lambda sd: param_wf(close, sd, 1, 1, 1, C=0, W=1), ext_start, end)
    # weight-identity check: does flipping canary/weighting change any monthly weight?
    canary_wt_changes = 0
    weight_wt_changes = 0
    for sd in sigs:
        base = {k: round(v, 6) for k, v in param_wf(close, sd, 1, 1, 1).items() if abs(v) > 1e-9}
        cflip = {k: round(v, 6) for k, v in param_wf(close, sd, 1, 1, 1, C=1).items() if abs(v) > 1e-9}
        wflip = {k: round(v, 6) for k, v in param_wf(close, sd, 1, 1, 1, W=1).items() if abs(v) > 1e-9}
        if base != cflip:
            canary_wt_changes += 1
        if base != wflip:
            weight_wt_changes += 1
    noop = {
        "rationale": ("Current prod CPM and the HAA baseline BOTH use TIP-only canary "
                      "and equal-weight, so along HAA->CPM these never flip. The flips "
                      "below move AWAY from current prod toward the OLD CPM config."),
        "canary_flip_HYGorTIP": {
            "CLEAN": windowed(cpm_canary_flip)["CLEAN"],
            "monthly_weight_changes_vs_prod": canary_wt_changes,
            "of_total_months": len(sigs),
        },
        "weighting_flip_invvol": {
            "CLEAN": windowed(cpm_weight_flip)["CLEAN"],
            "monthly_weight_changes_vs_prod": weight_wt_changes,
            "of_total_months": len(sigs),
        },
    }

    # ---- SAFE & BREADTH no-op verification ----
    # safe selector identical month-by-month regardless of universe/ranker.
    safe_haa_ctx = []
    safe_cpm_ctx = []
    for sd in sigs:
        m_haa = close.loc[:sd].resample("ME").last()
        m_cpm = prod_close.loc[:sd].resample("ME").last()
        safe_haa_ctx.append(best_safe(m_haa, sd, SAFE))
        safe_cpm_ctx.append(best_safe(m_cpm, sd, SAFE_POOL))
    safe_mismatch = sum(1 for a, b in zip(safe_haa_ctx, safe_cpm_ctx) if a != b)
    structure_noops = {
        "safe_pool_haa": SAFE, "safe_pool_cpm": SAFE_POOL,
        "safe_selector_monthly_mismatch": safe_mismatch, "of_total_months": len(sigs),
        "breadth_rule": "both use risky_fraction = min(n_pos,4)/4, remainder->safe (strict-4)",
        "note": ("SAFE selector and BREADTH/partial-safe are identical between HAA "
                 "baseline and CPM; not factors. The only n_pos=4 breadth difference "
                 "is min-var, isolated as factor M."),
    }

    result = {
        "meta": {"conv": CONV, "cost_bps": COST_BPS_PER_SIDE, "lookback": CORR_LOOKBACK_DAYS,
                 "top_k": TOP_K, "factors": FACTORS, "factor_label": FACTOR_LABEL,
                 "clean": f"{clean_start.date()}..{end.date()}",
                 "ext": f"{ext_start.date()}..{end.date()}",
                 "haa_universe": HAA_UNIVERSE, "cpm_universe": CPM_UNIVERSE,
                 "safe_pool": SAFE,
                 "prod_commit": "24c1207",
                 "note": ("Corrected HAA->CPM factorial: dropped canary+weighting (now "
                          "==HAA), added min-var selection; kept universe+ranker. "
                          "Endpoint = current prod CPM.")},
        "gates": {
            "allOFF_eq_canonical_HAA": {"weight_mismatches": haa_mismatch, "pass": gate_haa},
            "allON_eq_production_CPM": {"weight_mismatches": cpm_mismatch, "pass": gate_cpm},
            "allON_matches_CPM_anchor": {"target": list(CPM_ANCHOR_CLEAN),
                                         "actual": [c["sharpe"], c["maxdd"] * 100, c["calmar"]],
                                         "pass": bool(anchor_ok)},
            "allOFF_matches_HAA_anchor": {"target": list(HAA_ANCHOR_CLEAN),
                                          "actual": [o["sharpe"], o["maxdd"] * 100, o["calmar"]],
                                          "pass": bool(haa_anchor_ok)},
        },
        "benchmark": {"HAA": haa_m, "HAA_param_allOFF": alloff,
                      "CPM_param_allON": allon, "CPM_production_direct": prod_m},
        "cells": {"".join(map(str, k)): v for k, v in cells.items()},
        "effects": effects,
        "ladder": {"order": ladder_order, "paths": ladders},
        "ladder_alt": alt_ladders,
        "minvar_marginal": minvar_marginal,
        "noop_demonstration": noop,
        "structure_noops": structure_noops,
    }
    out_json = Path(__file__).with_suffix(".json")
    out_json.write_text(json.dumps(result, indent=2, default=float))
    print("\nGATES:", json.dumps(result["gates"], indent=2, default=float))
    print("benchmark CPM prod-direct CLEAN sharpe:", prod_m["CLEAN"]["sharpe"])
    print("WROTE", out_json)
    return result


if __name__ == "__main__":
    main()
