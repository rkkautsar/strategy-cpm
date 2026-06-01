# -*- coding: utf-8 -*-
"""ANALYST (read-only re production; NO production files touched; NO commit).

CORRECTED HAA -> CPM 2^5 factorial with REALISTIC, COUPLED factors.

Prior harness (cpm_haa_benchmark_ladder.py) split the shared trend metric into a
RANKER factor (F2: 13612U->faber/rv, coupling metric+vol-adjust) and a separate
SCREEN factor (F4: abs 13612U>0 -> faber>0). That decoupling let the
trend-screen metric move INDEPENDENTLY of the rank metric -- a config neither
HAA nor CPM ever uses -- producing an off-diagonal artifact.

This harness fixes the coupling. Five factors:

  T  TREND METRIC  -- couples rank numerator AND absolute screen together.
                      OFF = 13612U  (rank by 13612U ; screen = 13612U > 0)   [HAA]
                      ON  = Faber 10mo-SMA distance m_faber
                            (rank numerator = m_faber ; screen = m_faber > 0) [CPM]
                      ONE factor flips BOTH the rank metric and the screen metric.
  V  VOL-ADJUST    -- its OWN factor; touches ONLY the rank denominator.
                      OFF = raw momentum rank
                      ON  = rank numerator / rv_252d (risk-adjusted)
                      Does NOT affect the screen.
  W  WEIGHTING     OFF = equal-weight ; ON = inverse-vol (cov tail 252).
  C  CANARY        OFF = TIP-only (risk-on iff TIP 13612U>0)
                   ON  = HYG-or-TIP (any-positive 13612U).
  U  UNIVERSE      OFF = HAA set [SPY,IWM,VEA,VWO,VNQ,DBC,IEF,TLT]
                   ON  = CPM set [QQQ,SPHQ,EFA,EEM,VNQ,GLD,TLT,DBC].

  Common (held FIXED, NOT factors): TOP-4 cap; partial-safe breadth scaling
  (risky_fraction = n_pass/4, remainder->safe); best-of-safe {SHV, IEF} by
  13612U; SHV=BIL ultra-short T-bill wash.

GATES (must pass):
  all-OFF (T0,V0,W0,C0,U0) == canonical HAA, weight-by-weight (Sharpe 0.8670 /
    Calmar 0.6386 / MaxDD -14.68% CLEAN).
  all-ON  (T1,V1,W1,C1,U1) == production CPM both-252, weight-by-weight
    (Sharpe 1.1658 / MaxDD -12.97% / Calmar 1.0137 CLEAN).
"""
import sys, json, itertools
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import bull_qqq_live  # noqa: F401 (harness parity)
if not hasattr(bull_qqq_live, "_vol_gate_ok"):
    bull_qqq_live._vol_gate_ok = lambda *a, **k: True
from cpm_live import (
    load_panel, perf_metrics, sig_13612U, best_safe, faber_sma_xs, inv_vol_weights,
    compute_target_weights, RISKY_UNIVERSE, SAFE_POOL, CANARY_ASSETS, DEFAULT_CASH,
    COST_BPS_PER_SIDE, CORR_LOOKBACK_DAYS, TOP_K_CANDIDATES,
)
import exec_lag_moo_validation_2026_05_30 as H

CONV = "mooex"

HAA_UNIVERSE = ["SPY", "IWM", "VEA", "VWO", "VNQ", "DBC", "IEF", "TLT"]   # U OFF
CPM_UNIVERSE = ["QQQ", "SPHQ", "EFA", "EEM", "VNQ", "GLD", "TLT", "DBC"]  # U ON
SAFE = ["SHV", "IEF"]   # best-of-safe by 13612U; BIL->SHV wash

ANCHOR_CLEAN = (1.1658, -12.97, 1.0137)
HAA_ANCHOR_CLEAN = (0.8670, -14.68, 0.6386)
TOP_K = 4

# factor order: T trend-metric, V vol-adjust, W weighting, C canary, U universe
FACTORS = ["T", "V", "W", "C", "U"]
FACTOR_LABEL = {
    "T": "trend metric (13612U -> Faber, couples rank+screen)",
    "V": "vol-adjust (raw -> /rv_252d, rank denom only)",
    "W": "weighting (equal -> inverse-vol)",
    "C": "canary (TIP-only -> HYG-or-TIP)",
    "U": "universe (HAA-set -> CPM-set)",
}


# ======================= canonical HAA (standalone cross-check) =======================
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


# ======================= coupled parametric HAA<->CPM weight fn =======================
def param_wf(close, sig_d, T, V, W, C, U):
    """all-OFF == canonical HAA ; all-ON == cpm_live.compute_target_weights.

    T trend metric couples rank-numerator AND screen (same metric).
    V vol-adjust divides ONLY the rank numerator by rv_252d (screen untouched).
    """
    universe = CPM_UNIVERSE if U else HAA_UNIVERSE
    monthly = close.loc[:sig_d].resample("ME").last()
    safe = best_safe(monthly, sig_d, SAFE)

    # --- C canary ---
    canary_assets = ["HYG", "TIP"] if C else ["TIP"]
    cs = [sig_13612U(monthly[a]) for a in canary_assets if a in monthly.columns]
    cs = [s for s in cs if pd.notna(s)]
    if not cs or sum(1 for s in cs if s > 0) == 0:
        return {safe: 1.0}

    present = [t for t in universe if t in monthly.columns]
    faber = faber_sma_xs(monthly)
    avail = [t for t in present
             if sig_d in close.index and pd.notna(close.loc[sig_d].get(t, np.nan))]
    if not avail:
        return {safe: 1.0}

    daily = close[avail].ffill().pct_change()
    rank_score, screen_val = {}, {}
    for t in avail:
        u = sig_13612U(monthly[t]) if t in monthly.columns else np.nan
        fb = float(faber[t]) if (t in faber.index and pd.notna(faber[t])) else np.nan
        # T couples the trend metric for BOTH numerator and screen
        num = fb if T else u
        if pd.isna(num):
            continue
        # V touches only the rank denominator
        if V:
            rv = daily[t].loc[:sig_d].tail(252).std() * np.sqrt(252)
            if pd.isna(rv) or rv < 1e-9:
                rv = 1.0
            rank_score[t] = num / rv
        else:
            rank_score[t] = num
        screen_val[t] = num   # screen = raw trend metric (NOT vol-adjusted)
    if not rank_score:
        return {safe: 1.0}

    ranked = pd.Series(rank_score).sort_values(ascending=False)
    top = ranked.iloc[:min(TOP_K, len(ranked))]

    picks = [t for t in top.index if pd.notna(screen_val.get(t, np.nan)) and screen_val[t] > 0]
    if len(picks) == 0:
        return {safe: 1.0}

    n_picks = len(picks)
    risky_fraction = min(n_picks, TOP_K) / float(TOP_K)
    safe_fraction = 1.0 - risky_fraction

    if W:
        base_w = inv_vol_weights(close.loc[:sig_d], picks, CORR_LOOKBACK_DAYS)
    else:
        base_w = {t: 1.0 / n_picks for t in picks}

    out = {t: w * risky_fraction for t, w in base_w.items()}
    if safe_fraction > 0:
        out[safe] = out.get(safe, 0.0) + safe_fraction
    return out


# ======================= runners =======================
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
    flips = {}
    for i in range(k):
        deltas = []
        for key in keys:
            if key[i] == 0:
                on_key = tuple(1 if t == i else key[t] for t in range(k))
                deltas.append(M[on_key] - M[key])
        signs = set(np.sign(round(d, 6)) for d in deltas if abs(d) > 1e-9)
        flips[FACTORS[i]] = (any(s > 0 for s in signs) and any(s < 0 for s in signs))
    return {"main": main, "interactions": inter, "sign_flip": flips}


def conditional_effects(cells, metric, cond_idx, cond_val):
    """Main effects of each OTHER factor within the subcube where factor
    cond_idx is fixed to cond_val. Returns per-factor avg delta + sign-flip."""
    keys = [k for k in cells if k[cond_idx] == cond_val]
    M = {key: cells[key][metric] for key in keys}
    out = {}
    for i in range(len(FACTORS)):
        if i == cond_idx:
            continue
        deltas = []
        for key in keys:
            if key[i] == 0:
                on_key = tuple(1 if t == i else key[t] for t in range(len(FACTORS)))
                if on_key in M:
                    deltas.append(M[on_key] - M[key])
        if deltas:
            signs = set(np.sign(round(d, 6)) for d in deltas if abs(d) > 1e-9)
            out[FACTORS[i]] = {
                "mean": float(np.mean(deltas)),
                "min": float(np.min(deltas)),
                "max": float(np.max(deltas)),
                "sign_flip": bool(any(s > 0 for s in signs) and any(s < 0 for s in signs)),
            }
    return out


CRISES = {
    "Dot-com": ("2000-03-01", "2002-12-31"),
    "GFC":     ("2007-10-01", "2009-06-30"),
    "COVID":   ("2020-02-01", "2020-04-30"),
    "2022":    ("2022-01-01", "2022-10-31"),
}


def crisis_dd(ser, lo, hi):
    eq = (1.0 + ser).cumprod().dropna()
    if eq.empty:
        return None
    rm = eq.cummax()
    dd = eq / rm - 1.0
    w = dd.loc[lo:hi]
    if len(w) == 0 or not np.isfinite(w.min()):
        return None
    return float(w.min())


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

    # ---- 2^5 factorial ----
    print("Running 2^5 = 32 cells (mooex)...")
    cells = {}
    series = {}
    for bits in itertools.product([0, 1], repeat=5):
        wf = lambda sd, b=bits: param_wf(close, sd, *b)
        ser = run_series(close, daily, intraday, overnight, wf, ext_start, end)
        series[bits] = ser
        cells[bits] = windowed(ser)
        print(f"  {''.join(map(str,bits))}: CLEAN sharpe={cells[bits]['CLEAN']['sharpe']:.4f} "
              f"calmar={cells[bits]['CLEAN']['calmar']:.4f} maxdd={cells[bits]['CLEAN']['maxdd']*100:.2f}%")

    alloff = cells[(0, 0, 0, 0, 0)]
    allon = cells[(1, 1, 1, 1, 1)]

    # ---- GATE A: all-OFF == standalone canonical HAA (weight-by-weight) ----
    monthly_idx = (pd.DataFrame({"x": 1}, index=close.index)
                   .groupby(pd.Grouper(freq="ME")).tail(1))
    sigs = monthly_idx.index[(monthly_idx.index >= ext_start) & (monthly_idx.index <= end)].tolist()
    haa_mismatch = 0
    for sd in sigs:
        a = {k: round(v, 8) for k, v in param_wf(close, sd, 0, 0, 0, 0, 0).items() if abs(v) > 1e-9}
        b = {k: round(v, 8) for k, v in haa_wf(close, sd).items() if abs(v) > 1e-9}
        if a != b:
            haa_mismatch += 1

    # ---- GATE B: all-ON == production compute_target_weights (weight-by-weight) ----
    cpm_mismatch = 0
    for sd in sigs:
        a = {k: round(v, 6) for k, v in param_wf(close, sd, 1, 1, 1, 1, 1).items() if abs(v) > 1e-9}
        b = {k: round(v, 6) for k, v in compute_target_weights(prod_close, sd)[0].items() if abs(v) > 1e-9}
        if a != b:
            cpm_mismatch += 1

    gate_haa = (haa_mismatch == 0)
    gate_cpm = (cpm_mismatch == 0)

    c = allon["CLEAN"]
    anchor_ok = (abs(c["sharpe"] - ANCHOR_CLEAN[0]) < 5e-4
                 and abs(c["maxdd"] * 100 - ANCHOR_CLEAN[1]) < 0.05
                 and abs(c["calmar"] - ANCHOR_CLEAN[2]) < 5e-4)
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

    # ---- universe-conditional effects ----
    U_IDX = FACTORS.index("U")
    cond = {}
    for wn in windows:
        for metric in ("sharpe", "calmar", "maxdd"):
            flat = {key: cells[key][wn] for key in cells}
            cond[f"{wn}_{metric}"] = {
                "within_HAA_universe": conditional_effects(flat, metric, U_IDX, 0),
                "within_CPM_universe": conditional_effects(flat, metric, U_IDX, 1),
            }

    # ---- sequential ladder (sensible HAA->CPM: T,V,W,C,U) ----
    ladder_order = ["T", "V", "W", "C", "U"]
    alt_order = ["U", "T", "V", "W", "C"]

    def build_ladder(order, wn):
        path = []
        state = [0, 0, 0, 0, 0]
        path.append({"step": "HAA (all-OFF)", "config": "00000", **cells[tuple(state)][wn]})
        for f in order:
            idx = FACTORS.index(f)
            state[idx] = 1
            key = tuple(state)
            label = f"+{f} {FACTOR_LABEL[f].split(' (')[0]}"
            if all(state):
                label += " = CPM (all-ON)"
            path.append({"step": label, "config": "".join(map(str, key)), **cells[key][wn]})
        return path

    ladders = {wn: build_ladder(ladder_order, wn) for wn in windows}
    alt_ladders = {wn: build_ladder(alt_order, wn) for wn in windows}

    # ---- headline: mechanism (CPM machinery on HAA universe) vs universe ----
    cfg1 = (0, 0, 0, 0, 0)   # HAA
    cfg2 = (1, 1, 1, 1, 0)   # CPM mechanics on HAA universe
    cfg3 = (1, 1, 1, 1, 1)   # CPM full
    decomp = {}
    for wn in windows:
        m1, m2, m3 = cells[cfg1][wn], cells[cfg2][wn], cells[cfg3][wn]
        decomp[wn] = {
            "cfg1_HAA": m1, "cfg2_CPMmech_HAAuniv": m2, "cfg3_CPM_full": m3,
            "mechanism_edge": {k: m2[k] - m1[k] for k in ("sharpe", "calmar", "maxdd")},
            "universe_edge": {k: m3[k] - m2[k] for k in ("sharpe", "calmar", "maxdd")},
            "total_edge": {k: m3[k] - m1[k] for k in ("sharpe", "calmar", "maxdd")},
        }

    crisis = {}
    for nm, (lo, hi) in CRISES.items():
        crisis[nm] = {
            "HAA": crisis_dd(haa_s, lo, hi),
            "CPM_full": crisis_dd(series[cfg3], lo, hi),
            "CPMmech_HAAuniv": crisis_dd(series[cfg2], lo, hi),
        }

    result = {
        "meta": {"conv": CONV, "cost_bps": COST_BPS_PER_SIDE, "lookback": CORR_LOOKBACK_DAYS,
                 "top_k": TOP_K, "factors": FACTORS, "factor_label": FACTOR_LABEL,
                 "clean": f"{clean_start.date()}..{end.date()}",
                 "ext": f"{ext_start.date()}..{end.date()}",
                 "haa_universe": HAA_UNIVERSE, "cpm_universe": CPM_UNIVERSE,
                 "safe_pool": SAFE,
                 "note": "COUPLED trend metric (rank+screen together); vol-adjust own factor"},
        "gates": {
            "allOFF_eq_canonical_HAA": {"weight_mismatches": haa_mismatch, "pass": gate_haa},
            "allON_eq_production_CPM": {"weight_mismatches": cpm_mismatch, "pass": gate_cpm},
            "allON_matches_CPM_anchor": {"target": list(ANCHOR_CLEAN),
                                         "actual": [c["sharpe"], c["maxdd"], c["calmar"]],
                                         "pass": bool(anchor_ok)},
            "allOFF_matches_HAA_anchor": {"target": list(HAA_ANCHOR_CLEAN),
                                          "actual": [o["sharpe"], o["maxdd"], o["calmar"]],
                                          "pass": bool(haa_anchor_ok)},
        },
        "benchmark": {"HAA": haa_m, "HAA_param_allOFF": alloff,
                      "CPM_param_allON": allon, "CPM_production_direct": prod_m},
        "decomposition": decomp,
        "cells": {"".join(map(str, k)): v for k, v in cells.items()},
        "effects": effects,
        "universe_conditional": cond,
        "ladder": {"order": ladder_order, "paths": ladders},
        "ladder_alt": {"order": alt_order, "paths": alt_ladders},
        "crisis": crisis,
    }
    out_json = Path(__file__).with_suffix(".json")
    out_json.write_text(json.dumps(result, indent=2, default=float))
    print("\nGATES:", json.dumps(result["gates"], indent=2, default=float))
    print("WROTE", out_json)
    return result


if __name__ == "__main__":
    main()
