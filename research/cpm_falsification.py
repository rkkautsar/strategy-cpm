#!/usr/bin/env python3
"""
cpm_falsification.py — 4 falsification tests for CPM factorial structure.

Reads (does not modify) the existing cpm_haa_factorial.py infrastructure and
runs falsification probes that stress-test the strategy's internal consistency
and robustness.  Results are printed to stdout; no JSON/files are written.

Tests
-----
TEST 1 — MIN-VAR TRANSFER:  Does min-var (M) benefit generalise across
    universes?  M=0 vs M=1 on HAA (U=0) and CPM (U=1), split-half.

TEST 2 — CANARY CRISIS:       Does the TIPS canary (C=0) meaningfully reduce
    crisis drawdowns vs no canary (C=1)?  Calendar year returns for 2008,
    2020, 2022 plus crisis-window MaxDD.

TEST 3 — RANKER SPLIT-HALF:  Does the vol-adj Faber ranker (R=1) outperform
    the 13612U ranker (R=0) in both halves and both universes?

TEST 4 — BREADTH CURVE PERTURBATION:  How sensitive are Sharpe / MaxDD to
    the shape of the risky-fraction-vs-breadth curve?
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Path setup: import from the sibling research module + project
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(PROJECT_ROOT))

from research import cpm_haa_factorial as haa
from cpm_live import (
    faber_sma_xs,
    best_safe,
    _min_var_subset,
    SAFE_POOL,
    CORR_LOOKBACK_DAYS,
    COST_BPS_PER_SIDE,
)
from core import sig_13612U, perf_metrics
from data_loader import load_panel

# Re-use the same constants
START = haa.START                 # 2008-05-30
END = haa.END                     # 2026-04-30
HAA_UNIVERSE = haa.HAA_UNIVERSE
CPM_UNIVERSE = haa.CPM_UNIVERSE
C1_CURVE = haa.C1_CURVE
FACTORS = haa.FACTORS
COMBINED_COLS = haa.COMBINED_COLS

# Split-half boundary
SPLIT = pd.Timestamp("2017-04-01")

# Crisis windows (for MaxDD extraction)
CRISIS_WINDOWS = {
    "GFC 2008":  (pd.Timestamp("2008-01-01"), pd.Timestamp("2009-06-30")),
    "COVID 2020": (pd.Timestamp("2020-01-01"), pd.Timestamp("2020-06-30")),
    "2022 Hike": (pd.Timestamp("2022-01-01"), pd.Timestamp("2022-12-31")),
}

# Breadth curves for TEST 4
BREADTH_CURVES = {
    "linear":        {1: 0.25, 2: 0.50, 3: 0.75, 4: 1.0},
    "C1 (prod)":     {1: 0.0,  2: 0.0,  3: 0.50, 4: 1.0},
    "conservative":  {1: 0.0,  2: 0.0,  3: 0.0,  4: 1.0},
    "aggressive":    {1: 0.50, 2: 0.75, 3: 1.0,  4: 1.0},
    "step":          {1: 0.0,  2: 0.50, 3: 0.50, 4: 1.0},
}


# ======================= helpers ===========================================

def _metrics(daily: pd.Series) -> dict:
    m = perf_metrics(daily)
    return {"sharpe": m.get("sharpe"), "cagr": m.get("cagr"),
            "maxdd": m.get("max_drawdown"), "calmar": m.get("calmar"),
            "vol": m.get("vol")}


def _calendar_year_ret(daily: pd.Series, year: int) -> float | None:
    mask = (daily.index.year == year)
    sub = daily.loc[mask]
    if len(sub) < 10:
        return None
    return (1.0 + sub).prod() - 1.0


def _crisis_maxdd(daily: pd.Series, crisis_start: pd.Timestamp,
                  crisis_end: pd.Timestamp) -> float | None:
    sub = daily.loc[(daily.index >= crisis_start) & (daily.index <= crisis_end)]
    if len(sub) < 10:
        return None
    eq = (1.0 + sub).cumprod()
    dd = eq / eq.cummax() - 1.0
    return dd.min()


# ======================= cell runner ======================================

def run_one_cell(panel: pd.DataFrame, cfg: dict,
                 start: pd.Timestamp, end: pd.Timestamp) -> pd.Series:
    daily, _ = haa.run_backtest(panel, start, end, cfg)
    return daily


# ======================= TEST 1 — Min-Var Transfer ========================

def test_minvar_transfer(panel: pd.DataFrame):
    print("=" * 78)
    print("TEST 1 — MIN-VAR TRANSFER (M=0 vs M=1, split-half)")
    print("=" * 78)

    base_cfg = {"U": 0, "R": 1, "B": 1, "C": 1}

    rows = []
    for univ_label, u_val in [("HAA", 0), ("CPM", 1)]:
        cfg_off = {**base_cfg, "U": u_val, "M": 0}
        cfg_on  = {**base_cfg, "U": u_val, "M": 1}
        for half_label, hl_s, hl_e in [("H1", START, SPLIT - pd.Timedelta(days=1)),
                                         ("H2", SPLIT, END)]:
            d_off = run_one_cell(panel, cfg_off, hl_s, hl_e)
            d_on  = run_one_cell(panel, cfg_on,  hl_s, hl_e)
            m_off = _metrics(d_off)
            m_on  = _metrics(d_on)
            rows.append((univ_label, half_label, 0, m_off["sharpe"], m_off["maxdd"]))
            rows.append((univ_label, half_label, 1, m_on["sharpe"],  m_on["maxdd"]))

    print(f"  {'Universe':<8s} {'Half':>4s} {'M':>2s}  {'Sharpe':>7s}  {'MaxDD':>8s}")
    print("  " + "-" * 38)
    for r in rows:
        print(f"  {r[0]:<8s} {r[1]:>4s} {r[2]:>2d}  {r[3]:>7.3f}  {r[4]*100:>7.2f}%")

    print()
    for univ_label, u_val in [("HAA", 0), ("CPM", 1)]:
        cfg_off = {**base_cfg, "U": u_val, "M": 0}
        cfg_on  = {**base_cfg, "U": u_val, "M": 1}
        d_off_full = run_one_cell(panel, cfg_off, START, END)
        d_on_full  = run_one_cell(panel, cfg_on,  START, END)
        m_off = _metrics(d_off_full)
        m_on  = _metrics(d_on_full)
        delta_s = m_on["sharpe"] - m_off["sharpe"]
        delta_d = m_on["maxdd"] - m_off["maxdd"]
        print(f"  {univ_label} full-window Δ(M=1 − M=0): Sharpe={delta_s:+.4f}  "
              f"MaxDD={delta_d*100:+.2f}pp")
    print()


# ======================= TEST 2 — Canary Crisis ===========================

def test_canary_crisis(panel: pd.DataFrame):
    print("=" * 78)
    print("TEST 2 — CANARY CRISIS (C=0 TIPS gate vs C=1 no gate)")
    print("=" * 78)

    cfg_canary_on  = {"U": 1, "R": 1, "B": 1, "C": 0, "M": 1}
    cfg_canary_off = {"U": 1, "R": 1, "B": 1, "C": 1, "M": 1}

    d_on  = run_one_cell(panel, cfg_canary_on,  START, END)
    d_off = run_one_cell(panel, cfg_canary_off, START, END)

    full_on  = _metrics(d_on)
    full_off = _metrics(d_off)
    print(f"\n  Full-window (2008-05 .. 2026-04):")
    print(f"  {'Config':<18s} {'Sharpe':>7s} {'CAGR':>8s} {'MaxDD':>9s} {'Calmar':>7s}")
    print(f"  {'C=0 (TIPS gate)':<18s} {full_on['sharpe']:>7.3f} "
          f"{full_on['cagr']*100:>7.2f}% {full_on['maxdd']*100:>8.2f}% "
          f"{full_on['calmar']:>7.3f}")
    print(f"  {'C=1 (no gate)':<18s} {full_off['sharpe']:>7.3f} "
          f"{full_off['cagr']*100:>7.2f}% {full_off['maxdd']*100:>8.2f}% "
          f"{full_off['calmar']:>7.3f}")

    print(f"\n  Calendar year returns:")
    print(f"  {'Year':>6s}  {'C=0 (gate)':>12s}  {'C=1 (no gate)':>12s}  {'Δ':>10s}")
    print(f"  " + "-" * 44)
    for yr in [2008, 2020, 2022]:
        r_on  = _calendar_year_ret(d_on,  yr)
        r_off = _calendar_year_ret(d_off, yr)
        r_on_s  = f"{r_on*100:>7.2f}%" if r_on is not None else "  N/A"
        r_off_s = f"{r_off*100:>7.2f}%" if r_off is not None else "  N/A"
        delta = (r_off - r_on) * 100 if (r_on is not None and r_off is not None) else None
        d_s = f"{delta:>+7.2f}pp" if delta is not None else "    N/A"
        print(f"  {yr:>6d}  {r_on_s:>12s}  {r_off_s:>12s}  {d_s:>10s}")

    print(f"\n  Crisis-window MaxDD:")
    print(f"  {'Window':<14s}  {'C=0 (gate)':>12s}  {'C=1 (no gate)':>12s}  {'Δ':>10s}")
    print(f"  " + "-" * 52)
    for label, (cs, ce) in CRISIS_WINDOWS.items():
        mdd_on  = _crisis_maxdd(d_on,  cs, ce)
        mdd_off = _crisis_maxdd(d_off, cs, ce)
        m_on_s  = f"{mdd_on*100:>7.2f}%" if mdd_on is not None else "  N/A"
        m_off_s = f"{mdd_off*100:>7.2f}%" if mdd_off is not None else "  N/A"
        delta = (mdd_off - mdd_on) * 100 if (mdd_on is not None and mdd_off is not None) else None
        d_s = f"{delta:>+7.2f}pp" if delta is not None else "    N/A"
        print(f"  {label:<14s}  {m_on_s:>12s}  {m_off_s:>12s}  {d_s:>10s}")
    print()


# ======================= TEST 3 — Ranker Split-Half =======================

def test_ranker_split_half(panel: pd.DataFrame):
    print("=" * 78)
    print("TEST 3 — RANKER SPLIT-HALF (R=0 13612U vs R=1 vol-adj Faber)")
    print("=" * 78)

    base_cfg = {"B": 0, "C": 0, "M": 0}

    rows = []
    for univ_label, u_val in [("HAA", 0), ("CPM", 1)]:
        cfg_r0 = {**base_cfg, "U": u_val, "R": 0}
        cfg_r1 = {**base_cfg, "U": u_val, "R": 1}
        for half_label, hl_s, hl_e in [("H1", START, SPLIT - pd.Timedelta(days=1)),
                                         ("H2", SPLIT, END)]:
            d_r0 = run_one_cell(panel, cfg_r0, hl_s, hl_e)
            d_r1 = run_one_cell(panel, cfg_r1, hl_s, hl_e)
            m_r0 = _metrics(d_r0)
            m_r1 = _metrics(d_r1)
            rows.append((univ_label, half_label, 0, m_r0["sharpe"], m_r0["maxdd"]))
            rows.append((univ_label, half_label, 1, m_r1["sharpe"], m_r1["maxdd"]))

    print(f"  {'Universe':<8s} {'Half':>4s} {'R':>2s}  {'Sharpe':>7s}  {'MaxDD':>8s}")
    print("  " + "-" * 38)
    for r in rows:
        print(f"  {r[0]:<8s} {r[1]:>4s} {r[2]:>2d}  {r[3]:>7.3f}  {r[4]*100:>7.2f}%")

    print()
    for univ_label, u_val in [("HAA", 0), ("CPM", 1)]:
        cfg_r0 = {**base_cfg, "U": u_val, "R": 0}
        cfg_r1 = {**base_cfg, "U": u_val, "R": 1}
        d_r0_full = run_one_cell(panel, cfg_r0, START, END)
        d_r1_full = run_one_cell(panel, cfg_r1, START, END)
        m_r0 = _metrics(d_r0_full)
        m_r1 = _metrics(d_r1_full)
        delta_s = m_r1["sharpe"] - m_r0["sharpe"]
        delta_d = m_r1["maxdd"] - m_r0["maxdd"]
        print(f"  {univ_label} full-window Δ(R=1 − R=0): Sharpe={delta_s:+.4f}  "
              f"MaxDD={delta_d*100:+.2f}pp")
    print()


# ======================= TEST 4 — Breadth Curve Perturbation ==============

def _compute_cell_weights_curve(panel: pd.DataFrame, sig_d: pd.Timestamp,
                                 cfg: dict, curve: dict) -> dict:
    """Like compute_cell_weights, but substitutes the breadth curve."""
    universe = CPM_UNIVERSE if cfg["U"] else HAA_UNIVERSE
    monthly = panel.loc[:sig_d].resample("ME").last()
    safe = best_safe(monthly, sig_d, SAFE_POOL)

    avail = [t for t in universe
             if t in monthly.columns and monthly[t].first_valid_index() is not None]
    if not avail:
        return {safe: 1.0}

    if cfg["R"]:
        faber = faber_sma_xs(monthly)
        present = [t for t in avail
                   if t in faber.index and pd.notna(faber[t])
                   and pd.notna(panel.loc[sig_d, t] if sig_d in panel.index else np.nan)]
        if not present:
            return {safe: 1.0}
        daily_rets = panel[present].ffill().pct_change()
        scores = {}
        for t in present:
            v = daily_rets[t].loc[:sig_d].tail(252).std() * np.sqrt(252)
            if pd.isna(v) or v < 1e-9:
                v = 1.0
            scores[t] = float(faber[t]) / v
        ranked = pd.Series(scores).sort_values(ascending=False)
        top_k = max(2, min(4, len(ranked)))
        top = ranked.iloc[:top_k]
        positive = [t for t in top.index if faber.get(t, -np.inf) > 0]
    else:
        scores = {}
        for t in avail:
            s = sig_13612U(monthly[t])
            if pd.notna(s):
                scores[t] = s
        if not scores:
            return {safe: 1.0}
        ranked = sorted(scores.items(), key=lambda x: -x[1])
        top_k = max(2, min(4, len(ranked)))
        top = ranked[:top_k]
        positive = [t for t, s in top if s > 0]

    if not positive:
        return {safe: 1.0}

    n_pos = len(positive)

    # risky fraction using the INJECTED curve
    breadth_frac = curve.get(min(n_pos, 4), 0.0)
    hyg_mom = (sig_13612U(monthly["HYG"])
               if "HYG" in monthly.columns else float("nan"))
    hyg_frac = 0.0 if pd.notna(hyg_mom) and hyg_mom < 0.0 else 1.0
    risky_fraction = min(breadth_frac, hyg_frac)

    if not cfg["C"]:
        tip_mom = (sig_13612U(monthly["TIP"])
                   if "TIP" in monthly.columns else float("nan"))
        if pd.notna(tip_mom) and tip_mom < 0.0:
            risky_fraction = 0.0

    if risky_fraction <= 1e-12:
        return {safe: 1.0}

    if cfg["M"] and n_pos == 4 and risky_fraction == 1.0:
        picks = _min_var_subset(panel, sig_d, positive,
                                CORR_LOOKBACK_DAYS, 3)
    else:
        picks = positive

    risky_w = {t: 1.0 / len(picks) for t in picks}
    out = {t: w * risky_fraction for t, w in risky_w.items()}
    safe_fraction = 1.0 - risky_fraction
    if safe_fraction > 0:
        out[safe] = out.get(safe, 0.0) + safe_fraction
    return out


def _run_backtest_curve(panel: pd.DataFrame, start: pd.Timestamp,
                         end: pd.Timestamp, cfg: dict,
                         curve: dict) -> pd.Series:
    """Run backtest with a custom breadth curve (for TEST 4)."""
    cols = sorted(set(COMBINED_COLS) & set(panel.columns))
    close = panel[cols]

    monthly_idx = (pd.DataFrame({"x": 1}, index=close.index)
                   .groupby(pd.Grouper(freq="ME")).tail(1))
    signal_dates = monthly_idx.index[
        (monthly_idx.index >= start) & (monthly_idx.index <= end)
    ].tolist()

    weights_history: list[dict] = []
    for i, sig_d in enumerate(signal_dates):
        w = _compute_cell_weights_curve(close, sig_d, cfg, curve)
        future = close.index[close.index > sig_d]
        if len(future) < 1:
            continue
        apply_from = future[0]
        if i + 1 < len(signal_dates):
            nxt = signal_dates[i + 1]
            nf = close.index[close.index > nxt]
            end_apply = nf[0] if len(nf) >= 1 else end
        else:
            end_apply = end
        weights_history.append({
            "apply_from": apply_from, "end_apply": end_apply,
            "weights": w, "sig_d": sig_d,
        })

    all_assets = sorted({a for h in weights_history for a in h["weights"]})
    all_assets = [a for a in all_assets if a in close.columns]
    df_w = pd.DataFrame(0.0, index=close.index, columns=all_assets)

    for h in weights_history:
        mask = (close.index >= h["apply_from"]) & (close.index < h["end_apply"])
        for a, ww in h["weights"].items():
            if a in df_w.columns:
                df_w.loc[mask, a] = ww

    daily_ret = close.ffill().pct_change()
    common = [a for a in df_w.columns if a in daily_ret.columns]
    raw = (df_w[common] * daily_ret[common]).sum(axis=1, min_count=1).fillna(0.0)

    for i in range(len(weights_history)):
        prev_w = weights_history[i - 1]["weights"] if i > 0 else {}
        curr_w = weights_history[i]["weights"]
        keys = set(curr_w) | set(prev_w)
        turnover = sum(abs(curr_w.get(k, 0.0) - prev_w.get(k, 0.0)) for k in keys)
        cost = turnover * COST_BPS_PER_SIDE / 10_000.0
        af = weights_history[i]["apply_from"]
        if af in raw.index:
            raw.loc[af] -= cost

    return raw.loc[(raw.index >= start) & (raw.index <= end)]


def test_breadth_curve_perturbation(panel: pd.DataFrame):
    """5 curve shapes on CPM (U=1,R=1,B=1,C=1,M=1)."""
    print("=" * 78)
    print("TEST 4 — BREADTH CURVE PERTURBATION (5 shapes)")
    print("=" * 78)

    cfg = {"U": 1, "R": 1, "B": 1, "C": 1, "M": 1}

    print(f"\n  {'Curve':<18s}  {'Sharpe':>7s}  {'CAGR':>8s}  "
          f"{'MaxDD':>9s}  {'Calmar':>7s}  {'Vol':>7s}")
    print("  " + "-" * 65)

    results = {}
    for name, curve in BREADTH_CURVES.items():
        daily = _run_backtest_curve(panel, START, END, cfg, curve)
        m = _metrics(daily)
        results[name] = m
        print(f"  {name:<18s}  {m['sharpe']:>7.3f}  {m['cagr']*100:>7.2f}%  "
              f"{m['maxdd']*100:>8.2f}%  {m['calmar']:>7.3f}  {m['vol']*100:>6.2f}%")

    prod_s = results["C1 (prod)"]["sharpe"]
    prod_d = results["C1 (prod)"]["maxdd"]
    print(f"\n  Δ from C1 (prod) baseline:")
    print(f"  {'Curve':<18s}  {'ΔSharpe':>9s}  {'ΔMaxDD':>10s}")
    print("  " + "-" * 42)
    for name, m in results.items():
        ds = m["sharpe"] - prod_s
        dd = (m["maxdd"] - prod_d) * 100
        print(f"  {name:<18s}  {ds:>+9.4f}  {dd:>+9.2f}pp")
    print()


# ======================= FINAL VERDICT TABLE ==============================

def print_final_verdict():
    print("=" * 78)
    print("FINAL VERDICT")
    print("=" * 78)
    verdicts = [
        ("TEST 1 — Min-Var Transfer",
         "Does min-var improve Sharpe across both universes and halves?",
         "Check Δ(M=1 − M=0) for sign consistency.  If sign-flips exist, "
         "min-var is not a robust improvement."),
        ("TEST 2 — Canary Crisis",
         "Does the TIPS canary reduce drawdowns in crisis windows?",
         "Check crisis MaxDD and 2008/2020/2022 calendar returns.  If C=0 "
         "(gate) shows no meaningful improvement over C=1, the canary "
         "provides no crisis benefit."),
        ("TEST 3 — Ranker Split-Half",
         "Does vol-adj Faber beat 13612U consistently?",
         "Check Δ(R=1 − R=0) across both halves and both universes.  "
         "If sign-flips, the ranker choice is not robust."),
        ("TEST 4 — Breadth Perturbation",
         "Is Sharpe robust to curve shape?",
         "Check whether Sharpe variation across curves is small relative to "
         "estimation error (~0.15–0.20).  Large swings indicate "
         "over-fitting to the curve."),
    ]
    for name, question, reading_guide in verdicts:
        print(f"\n  {name}")
        print(f"    Question: {question}")
        print(f"    Read:     {reading_guide}")


# ================================= MAIN ====================================

def main():
    print(f"CPM Falsification Suite  |  {START.date()} .. {END.date()}")
    print(f"Split-half at {SPLIT.date()}")
    print("=" * 78)

    print("\nLoading panel ...")
    panel = load_panel(start=START - pd.DateOffset(years=3), end=END)
    print(f"  Panel: {panel.index[0].date()} .. {panel.index[-1].date()}, "
          f"{len(panel.columns)} cols\n")

    test_minvar_transfer(panel)
    test_canary_crisis(panel)
    test_ranker_split_half(panel)
    test_breadth_curve_perturbation(panel)

    print_final_verdict()
    print("\nDone.")


if __name__ == "__main__":
    main()
