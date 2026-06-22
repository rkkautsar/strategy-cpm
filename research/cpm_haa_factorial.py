#!/usr/bin/env python3
"""HAA-Balanced -> CPM factorial decomposition (2^5 = 32 cells).

Runs a monthly tactical allocation backtest comparing HAA-Balanced (base)
to CPM (target). Each of the 5 factors is toggled ON/OFF independently:

    U = universe      OFF: HAA-8 [SPY,IWM,VEA,VWO,VNQ,DBC,IEF,TLT]
                      ON:  CPM-8 [QQQ,SPHQ,EFA,EEM,VNQ,GLD,TLT,DBC]

    R = ranker+screen OFF: 13612U ranker, 13612U>0 screen
                      ON:  vol-adj Faber, raw Faber>0 screen

    B = breadth+gate  OFF: linear min(n,4)/4, no HYG gate
                      ON:  C1 curve {1:0,2:0,3:0.5,4:1.0} + HYG gate

    C = canary        OFF: TIPS 13612U>0 gate
                      ON:  no TIPS gate (HYG in B handles risk-off)

    M = min-var       OFF: equal-weight picks
                      ON:  min-var 3-of-4 at full breadth

Clean window: 2008-05-30 to 2026-04-30.  Execution: T+1 MOO, 10 bps cost.

No production files touched.  Writes JSON next to this file.
"""
import sys
import json
import itertools
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Imports from project
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cpm_live
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

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
START = pd.Timestamp("2008-05-30")
END = pd.Timestamp("2026-04-30")

HAA_UNIVERSE = ["SPY", "IWM", "VEA", "VWO", "VNQ", "DBC", "IEF", "TLT"]
CPM_UNIVERSE = list(cpm_live.RISKY_UNIVERSE)  # ["QQQ","SPHQ","EFA","EEM","VNQ","GLD","TLT","DBC"]

C1_CURVE = {1: 0.0, 2: 0.0, 3: 0.5, 4: 1.0}

FACTORS = ["U", "R", "B", "C", "M"]

# Union of assets needed across all cells (plus canary gate inputs).
COMBINED_COLS = sorted(
    set(HAA_UNIVERSE + CPM_UNIVERSE + SAFE_POOL + ["HYG", "TIP"])
)


# ===================== per-cell weight computation =========================
def compute_cell_weights(panel: pd.DataFrame, sig_d: pd.Timestamp,
                         cfg: dict) -> dict:
    """Return target weights for one cell at one signal date.

    cfg keys: U, R, B, C, M (each 0 or 1).
    """
    universe = CPM_UNIVERSE if cfg["U"] else HAA_UNIVERSE
    monthly = panel.loc[:sig_d].resample("ME").last()
    safe = best_safe(monthly, sig_d, SAFE_POOL)

    # -- ranker + top-4 + positive screen --
    avail = [t for t in universe
             if t in monthly.columns and monthly[t].first_valid_index() is not None]
    if not avail:
        return {safe: 1.0}

    if cfg["R"]:                                  # vol-adj Faber ranker
        faber = faber_sma_xs(monthly)
        present = [t for t in avail
                   if t in faber.index and pd.notna(faber[t])
                   and pd.notna(panel.loc[sig_d, t] if sig_d in panel.index
                                else np.nan)]
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
    else:                                         # 13612U ranker
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

    # -- risky fraction --
    if cfg["B"]:
        breadth_frac = C1_CURVE.get(min(n_pos, 4), 0.0)
        hyg_mom = (sig_13612U(monthly["HYG"])
                   if "HYG" in monthly.columns else float("nan"))
        hyg_frac = 0.0 if pd.notna(hyg_mom) and hyg_mom < 0.0 else 1.0
        risky_fraction = min(breadth_frac, hyg_frac)
    else:
        risky_fraction = min(n_pos, 4) / 4.0

    if not cfg["C"]:                               # TIPS canary gate
        tip_mom = (sig_13612U(monthly["TIP"])
                   if "TIP" in monthly.columns else float("nan"))
        if pd.notna(tip_mom) and tip_mom < 0.0:
            risky_fraction = 0.0

    if risky_fraction <= 1e-12:
        return {safe: 1.0}

    # -- asset selection --
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


# ========================= backtest driver ================================
def run_backtest(panel: pd.DataFrame, start: pd.Timestamp,
                 end: pd.Timestamp, cfg: dict) -> tuple[pd.Series, list]:
    """Run one cell backtest.  Returns (daily_returns, weights_history)."""
    cols = sorted(set(COMBINED_COLS) & set(panel.columns))
    close = panel[cols]

    monthly_idx = (pd.DataFrame({"x": 1}, index=close.index)
                   .groupby(pd.Grouper(freq="ME")).tail(1))
    signal_dates = monthly_idx.index[
        (monthly_idx.index >= start) & (monthly_idx.index <= end)
    ].tolist()

    weights_history: list[dict] = []
    for i, sig_d in enumerate(signal_dates):
        w = compute_cell_weights(close, sig_d, cfg)
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

    # -- daily returns --
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

    return raw.loc[(raw.index >= start) & (raw.index <= end)], weights_history


# ========================= analysis helpers ===============================
def _metrics(daily: pd.Series) -> dict:
    m = perf_metrics(daily)
    return {"sharpe": m.get("sharpe"), "cagr": m.get("cagr"),
            "maxdd": m.get("max_drawdown"), "calmar": m.get("calmar"),
            "vol": m.get("vol")}


def factorial_effects(cells: dict, metric: str) -> dict:
    """Standard 2^k factorial main effects and 2-way interactions."""
    keys = list(cells.keys())
    k = len(FACTORS)
    M = {key: cells[key][metric] for key in keys}
    codes = {key: tuple(2 * b - 1 for b in key) for key in keys}
    half = 2 ** (k - 1)

    main: dict[str, float] = {}
    for i, fn in enumerate(FACTORS):
        main[fn] = sum(codes[key][i] * M[key] for key in keys) / half

    inter: dict[str, float] = {}
    for i, j in itertools.combinations(range(k), 2):
        name = f"{FACTORS[i]}x{FACTORS[j]}"
        inter[name] = sum(codes[key][i] * codes[key][j] * M[key]
                          for key in keys) / half

    flips: dict[str, bool] = {}
    for i, fn in enumerate(FACTORS):
        deltas = []
        for key in keys:
            if key[i] == 0:
                on_key = tuple(1 if t == i else key[t] for t in range(k))
                deltas.append(M[on_key] - M[key])
        signs = set(np.sign(round(d, 6)) for d in deltas if abs(d) > 1e-9)
        flips[fn] = (any(s > 0 for s in signs) and any(s < 0 for s in signs))

    return {"main": main, "interactions": inter, "sign_flip": flips}


LADDER_STEPS = [
    ("HAA-Balanced",  (0, 0, 0, 0, 0)),
    ("+U (universe)", (1, 0, 0, 0, 0)),
    ("+R (ranker)",   (1, 1, 0, 0, 0)),
    ("+B (breadth)",  (1, 1, 1, 0, 0)),
    ("+C (canary)",   (1, 1, 1, 1, 0)),
    ("+M (minvar)",   (1, 1, 1, 1, 1)),
]


def anchor_check(panel: pd.DataFrame, cells: dict,
                 cell_dailies: dict) -> list[str]:
    """Compare all-ON cell to production compute_target_weights on sample dates."""
    prod_wt = cpm_live.compute_target_weights
    sample_dates = [
        pd.Timestamp("2012-06-29"), pd.Timestamp("2015-12-31"),
        pd.Timestamp("2020-03-31"), pd.Timestamp("2024-06-28"),
    ]
    all_on = (1, 1, 1, 1, 1)
    cols = sorted(set(COMBINED_COLS) & set(panel.columns))
    close = panel[cols]
    lines: list[str] = []
    for sig_d in sample_dates:
        if sig_d not in close.index:
            continue
        prod, _, _, _ = prod_wt(close, sig_d)
        cell_w = compute_cell_weights(close, sig_d, dict(zip(FACTORS, all_on)))
        all_keys = sorted(set(prod) | set(cell_w))
        match = all(abs(prod.get(k, 0.0) - cell_w.get(k, 0.0)) < 1e-9
                    for k in all_keys)
        status = "MATCH" if match else "MISMATCH"
        lines.append(f"  {sig_d.date()}: {status}")
        if not match:
            lines.append(f"    prod: {prod}")
            lines.append(f"    cell: {cell_w}")
    return lines


# ================================= main ====================================
def main():
    print(f"HAA->CPM 2^5 factorial  |  {START.date()} .. {END.date()}")
    print("=" * 70)

    # 1. Load panel (must cover all assets across both universes + canary)
    print("Loading panel ...")
    panel = load_panel(start=START - pd.DateOffset(years=3), end=END)
    print(f"  Panel: {panel.index[0].date()} .. {panel.index[-1].date()}, "
          f"{len(panel.columns)} cols")

    # 2. Run all 32 cells
    cells: dict[tuple, dict] = {}
    cell_dailies: dict[tuple, pd.Series] = {}
    combos = list(itertools.product([0, 1], repeat=5))
    print(f"\nRunning {len(combos)} cells ...")
    for cfg_tuple in combos:
        cfg = dict(zip(FACTORS, cfg_tuple))
        label = "".join(map(str, cfg_tuple))
        daily, _ = run_backtest(panel, START, END, cfg)
        cell_dailies[cfg_tuple] = daily
        cells[cfg_tuple] = _metrics(daily)
        m = cells[cfg_tuple]
        print(f"  {label}: Sharpe={m['sharpe']:.3f}  CAGR={m['cagr']*100:.2f}%  "
              f"MaxDD={m['maxdd']*100:.2f}%  Calmar={m['calmar']:.3f}")

    # 3. 32-cell grid
    print(f"\n{'='*70}")
    print("32-CELL GRID")
    print(f"{'='*70}")
    print(f"{'Cell':>6s}  {'Sharpe':>7s}  {'CAGR':>8s}  {'MaxDD':>8s}  {'Calmar':>7s}")
    print("-" * 50)
    for cfg_tuple in combos:
        label = "".join(map(str, cfg_tuple))
        m = cells[cfg_tuple]
        print(f"{label:>6s}  {m['sharpe']:7.3f}  {m['cagr']*100:7.2f}%  "
              f"{m['maxdd']*100:7.2f}%  {m['calmar']:7.3f}")

    # 4. Main effects + interactions
    for metric in ("sharpe", "maxdd", "calmar"):
        eff = factorial_effects(cells, metric)
        print(f"\nMAIN EFFECTS (d{metric}):")
        for fn, v in sorted(eff["main"].items(), key=lambda x: -abs(x[1])):
            fl = " [SIGN-FLIP]" if eff["sign_flip"][fn] else ""
            print(f"  {fn}: {v:+.4f}{fl}")
        top2 = sorted(eff["interactions"].items(), key=lambda x: -abs(x[1]))[:5]
        print(f"  Top 2-way: " + ", ".join(f"{k}={v:+.4f}" for k, v in top2))

    # 5. Ladder
    print(f"\n{'='*70}")
    print("LADDER: U -> R -> B -> C -> M")
    print(f"{'='*70}")
    print(f"{'Step':<20s}  {'Sharpe':>7s}  {'CAGR':>8s}  {'MaxDD':>8s}  {'Calmar':>7s}")
    print("-" * 60)
    for label, cfg_tuple in LADDER_STEPS:
        m = cells[cfg_tuple]
        print(f"{label:<20s}  {m['sharpe']:7.3f}  {m['cagr']*100:7.2f}%  "
              f"{m['maxdd']*100:7.2f}%  {m['calmar']:7.3f}")

    # 6. Anchor check: all-ON vs production compute_target_weights
    print(f"\n{'='*70}")
    print("ANCHOR CHECK: all-ON vs production compute_target_weights")
    print(f"{'='*70}")
    for line in anchor_check(panel, cells, cell_dailies):
        print(line)

    # 7. Save JSON
    out_path = Path(__file__).with_suffix(".json")
    out = {
        "factors": FACTORS,
        "window": {"start": str(START.date()), "end": str(END.date())},
        "cells": {},
        "main_effects": {},
        "ladder": [],
    }
    for cfg_tuple in combos:
        label = "".join(map(str, cfg_tuple))
        out["cells"][label] = {k: (float(v) if v is not None else None)
                               for k, v in cells[cfg_tuple].items()}
    for metric in ("sharpe", "maxdd", "calmar"):
        eff = factorial_effects(cells, metric)
        out["main_effects"][metric] = {
            "main": {k: float(v) for k, v in eff["main"].items()},
            "interactions": {k: float(v) for k, v in eff["interactions"].items()},
            "sign_flip": eff["sign_flip"],
        }
    for label, cfg_tuple in LADDER_STEPS:
        m = cells[cfg_tuple]
        out["ladder"].append({
            "step": label,
            "cfg": "".join(map(str, cfg_tuple)),
            **{k: (float(v) if v is not None else None) for k, v in m.items()},
        })
    out_path.write_text(json.dumps(out, indent=2, default=float))
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
