#!/usr/bin/env python3
"""
CPM Canary Variant Comparison
==============================
Compare three canary gate implementations on the CPM sleeve:

  C0 / C1 (current prod): HYG-only credit momentum gate
  C2 (HYG-OR-TIP):        either HYG or TIP positive -> risk-on
  C3 (no gate):            no canary; risky_fraction = breadth_frac only

Metrics: Sharpe, CAGR, Vol, MaxDD, Calmar + year-by-year + crisis windows.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Ensure project root is importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from cpm_live import (
    CANARY_ASSETS,
    CORR_LOOKBACK_DAYS,
    COST_BPS_PER_SIDE,
    CPM_RISKY_FRACTION_CURVE,
    DEFAULT_CASH,
    EVAL_END,
    RISKY_UNIVERSE,
    SAFE_POOL,
    TOP_K_CANDIDATES,
    best_safe,
    faber_sma_xs,
    inv_vol_weights,
)
from core import perf_metrics, sig_13612U
from data_loader import load_panel

# ---------- Crisis windows ----------
CRISIS_WINDOWS = {
    "GFC":   (pd.Timestamp("2007-10-01"), pd.Timestamp("2009-06-30")),
    "COVID": (pd.Timestamp("2020-02-01"), pd.Timestamp("2020-04-30")),
    "2022":  (pd.Timestamp("2022-01-01"), pd.Timestamp("2022-10-31")),
}

CRISIS_YEARS = [2008, 2020, 2022]


def _min_var_subset_local(close, sig_d, candidates, lookback, m):
    """Minimize equal-weight portfolio variance over m-of-candidates."""
    from itertools import combinations
    if len(candidates) <= m:
        return list(candidates)
    rets = close[candidates].ffill().pct_change().dropna(how="all").loc[:sig_d].tail(lookback)
    if len(rets) < lookback:
        return list(candidates)
    cov = rets.cov()
    if cov.isna().any().any():
        return list(candidates)
    w = 1.0 / m
    best, best_v = None, np.inf
    for combo in combinations(candidates, m):
        sub = cov.loc[list(combo), list(combo)].values
        v = float(w * w * sub.sum())
        if v < best_v:
            best_v, best = v, combo
    return list(best) if best else list(candidates)


# ---------- Variant weight computation ----------

def compute_target_weights_variant(
    close_panel: pd.DataFrame,
    sig_d: pd.Timestamp,
    variant: str = "C0",
    universe: list = None,
    safe_pool: list = None,
) -> tuple[dict, tuple, str, str]:
    """
    Compute CPM target weights with a specific canary variant.

    Variants:
      C0 (prod):   risky_fraction = min(breadth_frac, hyg_frac)  [current code]
      C1:          same as C0 (HYG-only, explicit)
      C2:          risky_fraction = min(breadth_frac, max(hyg_frac, tip_frac))
      C3:          risky_fraction = breadth_frac (no canary gate)
    """
    universe = universe or RISKY_UNIVERSE
    safe_pool = safe_pool or SAFE_POOL

    monthly = close_panel.loc[:sig_d].resample("ME").last()
    safe = best_safe(monthly, sig_d, safe_pool)

    # Volatility-adjusted Faber ranker
    faber = faber_sma_xs(monthly)
    avail = [t for t in universe
             if t in faber.index and pd.notna(faber[t])
             and pd.notna(close_panel.loc[sig_d].get(t, np.nan) if sig_d in close_panel.index else np.nan)]
    if not avail:
        return {safe: 1.0}, None, "DEFENSIVE", safe

    daily_rets = close_panel[avail].ffill().pct_change()
    scores = {}
    for t in avail:
        v = daily_rets[t].loc[:sig_d].tail(252).std() * np.sqrt(252)
        if pd.isna(v) or v < 1e-9:
            v = 1.0
        scores[t] = float(faber[t]) / v
    sa = pd.Series(scores)
    ranked = sa.sort_values(ascending=False)
    top_k = max(2, min(TOP_K_CANDIDATES, len(ranked)))
    top = ranked.iloc[:top_k]
    positive = top[top.index.map(lambda t: faber.get(t, -np.inf) > 0)]

    if len(positive) == 0:
        return {safe: 1.0}, None, "DEFENSIVE", safe

    positive_picks = list(positive.index)
    n_pos = len(positive_picks)

    # --- Canary gate logic (variant-dependent) ---
    hyg_mom = sig_13612U(monthly["HYG"]) if "HYG" in monthly.columns else float("nan")
    hyg_frac = 0.0 if pd.notna(hyg_mom) and hyg_mom < 0.0 else 1.0

    if variant in ("C0", "C1"):
        # Current production: HYG-only gate
        risky_fraction = min(CPM_RISKY_FRACTION_CURVE.get(min(n_pos, 4), 0.0), hyg_frac)
    elif variant == "C2":
        # HYG-OR-TIP: either positive -> risk-on
        tip_mom = sig_13612U(monthly["TIP"]) if "TIP" in monthly.columns else float("nan")
        tip_frac = 0.0 if pd.notna(tip_mom) and tip_mom < 0.0 else 1.0
        gate_frac = max(hyg_frac, tip_frac)
        risky_fraction = min(CPM_RISKY_FRACTION_CURVE.get(min(n_pos, 4), 0.0), gate_frac)
    elif variant == "C3":
        # No canary: breadth-only
        risky_fraction = CPM_RISKY_FRACTION_CURVE.get(min(n_pos, 4), 0.0)
    else:
        raise ValueError(f"Unknown variant: {variant}")

    if risky_fraction <= 1e-12:
        return {safe: 1.0}, None, "DEFENSIVE", safe

    if n_pos == TOP_K_CANDIDATES and risky_fraction == 1.0:
        picks = _min_var_subset_local(close_panel, sig_d, positive_picks, CORR_LOOKBACK_DAYS, 3)
    else:
        picks = positive_picks

    safe_fraction = 1.0 - risky_fraction
    risky_w = {t: 1.0 / len(picks) for t in picks}
    out = {t: w * risky_fraction for t, w in risky_w.items()}
    if safe_fraction > 0:
        out[safe] = out.get(safe, 0.0) + safe_fraction
    return out, tuple(picks), "RISK_ON", safe


def run_cpm_backtest_variant(
    panel: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
    variant: str = "C0",
    cost_bps: float = COST_BPS_PER_SIDE,
) -> tuple[pd.Series, list]:
    """Run CPM backtest with a specific canary variant."""
    cols = sorted(set(RISKY_UNIVERSE + SAFE_POOL + CANARY_ASSETS + [DEFAULT_CASH]) & set(panel.columns))
    close = panel[cols]

    monthly_idx = pd.DataFrame({"x": 1}, index=close.index).groupby(pd.Grouper(freq="ME")).tail(1)
    signal_dates = monthly_idx.index[(monthly_idx.index >= start) & (monthly_idx.index <= end)].tolist()

    weights_history = []

    for i, sig_d in enumerate(signal_dates):
        w, new_basket, regime, safe = compute_target_weights_variant(close, sig_d, variant=variant)
        future = close.index[close.index > sig_d]
        if len(future) < 1:
            continue
        apply_from = future[0]
        if i + 1 < len(signal_dates):
            next_sig = signal_dates[i + 1]
            next_future = close.index[close.index > next_sig]
            end_apply = next_future[0] if len(next_future) >= 1 else end
        else:
            end_apply = end
        weights_history.append({
            "apply_from": apply_from, "end_apply": end_apply,
            "weights": w, "sig_d": sig_d, "regime": regime, "safe": safe,
        })

    # Build daily return series
    all_assets = sorted({a for h in weights_history for a in h["weights"]})
    df_w = pd.DataFrame(0.0, index=close.index, columns=[a for a in all_assets if a in close.columns])

    for h in weights_history:
        mask = (close.index >= h["apply_from"]) & (close.index < h["end_apply"])
        for a, ww in h["weights"].items():
            if a in df_w.columns:
                df_w.loc[mask, a] = ww

    daily_ret = close.ffill().pct_change()
    common = [a for a in df_w.columns if a in daily_ret.columns]
    raw_returns = (df_w[common] * daily_ret[common]).sum(axis=1, min_count=1).fillna(0.0)

    # Apply trade costs
    for i in range(len(weights_history)):
        prev_w = weights_history[i - 1]["weights"] if i > 0 else {}
        curr_w = weights_history[i]["weights"]
        keys = set(curr_w) | set(prev_w)
        turnover = sum(abs(curr_w.get(k, 0.0) - prev_w.get(k, 0.0)) for k in keys)
        cost = turnover * cost_bps / 10000.0
        af = weights_history[i]["apply_from"]
        if af in raw_returns.index:
            raw_returns.loc[af] -= cost

    return raw_returns.loc[(raw_returns.index >= start) & (raw_returns.index <= end)], weights_history


# ---------- Metrics helpers ----------

def year_returns(daily: pd.Series) -> dict:
    """Annual returns by calendar year."""
    out = {}
    for yr, grp in daily.groupby(daily.index.year):
        cum = (1 + grp).prod() - 1
        out[yr] = float(cum)
    return out


def window_return(daily: pd.Series, start: pd.Timestamp, end: pd.Timestamp) -> float:
    """Cumulative return over [start, end]."""
    sub = daily.loc[(daily.index >= start) & (daily.index <= end)]
    if sub.empty:
        return float("nan")
    return float((1 + sub).prod() - 1)


def window_maxdd(daily: pd.Series, start: pd.Timestamp, end: pd.Timestamp) -> float:
    """Max drawdown over [start, end]."""
    sub = daily.loc[(daily.index >= start) & (daily.index <= end)]
    if sub.empty:
        return float("nan")
    eq = (1 + sub).cumprod()
    rm = eq.cummax()
    dd = eq / rm - 1
    return float(dd.min())


# ---------- Main ----------

def main():
    START = pd.Timestamp("2008-05-30")
    END = pd.Timestamp("2026-04-30")

    print("Loading panel ...")
    panel = load_panel(start=START, end=END)
    print(f"Panel: {panel.index[0].date()} -> {panel.index[-1].date()}, {len(panel.columns)} assets\n")

    variants = ["C0", "C1", "C2", "C3"]
    variant_labels = {
        "C0": "C0: Current prod (HYG-only)",
        "C1": "C1: HYG-only (explicit)",
        "C2": "C2: HYG-OR-TIP",
        "C3": "C3: No gate (breadth only)",
    }

    results = {}

    for v in variants:
        print(f"Running {variant_labels[v]} ...")
        daily, wh = run_cpm_backtest_variant(panel, START, END, variant=v)
        m = perf_metrics(daily)
        yr = year_returns(daily)
        crisis = {}
        for name, (ws, we) in CRISIS_WINDOWS.items():
            crisis[name] = {
                "return": window_return(daily, ws, we),
                "maxdd": window_maxdd(daily, ws, we),
            }
        crisis_year_rets = {yr_val: yr_ret for yr_val, yr_ret in yr.items() if yr_val in CRISIS_YEARS}

        results[v] = {
            "label": variant_labels[v],
            "full_window": {
                "cagr": m["cagr"],
                "vol": m["vol"],
                "sharpe": m["sharpe"],
                "max_drawdown": m["max_drawdown"],
                "calmar": m["calmar"],
                "total_return": m["total_return"],
            },
            "year_returns": yr,
            "crisis_returns": crisis,
            "crisis_year_rets": crisis_year_rets,
        }

    # Print comparison table
    print("\n" + "=" * 90)
    print("FULL WINDOW (2008-05-30 to 2026-04-30)")
    print("=" * 90)
    print(f"{'Variant':30s} {'CAGR':>8s} {'Vol':>7s} {'Sharpe':>7s} {'MaxDD':>8s} {'Calmar':>8s}")
    print("-" * 90)
    for v in variants:
        r = results[v]["full_window"]
        print(f"{variant_labels[v]:30s} {r['cagr']*100:7.2f}% {r['vol']*100:6.2f}% {r['sharpe']:7.3f} {r['max_drawdown']*100:7.2f}% {r['calmar']:8.3f}")

    print("\n" + "=" * 90)
    print("CRISIS WINDOWS")
    print("=" * 90)
    for crisis_name in CRISIS_WINDOWS:
        print(f"\n  {crisis_name}:")
        print(f"  {'Variant':30s} {'Return':>10s} {'MaxDD':>10s}")
        for v in variants:
            c = results[v]["crisis_returns"][crisis_name]
            print(f"  {variant_labels[v]:30s} {c['return']*100:9.2f}% {c['maxdd']*100:9.2f}%")

    print("\n" + "=" * 90)
    print("YEAR-BY-YEAR RETURNS")
    print("=" * 90)
    all_years = sorted(set().union(*(set(results[v]["year_returns"]) for v in variants)))
    print(f"{'Year':6s}", end="")
    for v in variants:
        print(f" {v:>10s}", end="")
    print()
    print("-" * 56)
    for yr_val in all_years:
        print(f"{yr_val:6d}", end="")
        for v in variants:
            val = results[v]["year_returns"].get(yr_val, float("nan"))
            print(f" {val*100:9.2f}%", end="")
        print()

    # Delta table: C2 and C3 vs C0
    print("\n" + "=" * 90)
    print("DELTA vs C0 (current prod)")
    print("=" * 90)
    base = results["C0"]["full_window"]
    print(f"{'Variant':30s} {'dCAGR':>8s} {'dVol':>7s} {'dSharpe':>8s} {'dMaxDD':>8s}")
    print("-" * 65)
    for v in ["C2", "C3"]:
        r = results[v]["full_window"]
        print(f"{variant_labels[v]:30s} {(r['cagr']-base['cagr'])*100:+7.2f}% {(r['vol']-base['vol'])*100:+6.2f}% {r['sharpe']-base['sharpe']:+8.3f} {(r['max_drawdown']-base['max_drawdown'])*100:+7.2f}%")

    # Save JSON
    out_path = Path(__file__).parent / "cpm_canary_hyg_only.json"
    # Convert numpy types for JSON serialization
    def to_native(obj):
        if isinstance(obj, (np.integer,)): return int(obj)
        if isinstance(obj, (np.floating,)): return float(obj)
        if isinstance(obj, np.ndarray): return obj.tolist()
        if isinstance(obj, pd.Timestamp): return obj.isoformat()
        return obj

    json_out = {}
    for v, data in results.items():
        json_out[v] = {
            "label": data["label"],
            "full_window": {k: to_native(val) for k, val in data["full_window"].items()},
            "year_returns": {str(k): to_native(val) for k, val in data["year_returns"].items()},
            "crisis_returns": {
                k: {kk: to_native(vv) for kk, vv in val.items()}
                for k, val in data["crisis_returns"].items()
            },
        }

    with open(out_path, "w") as f:
        json.dump(json_out, f, indent=2, default=str)
    print(f"\nSaved JSON: {out_path}")


if __name__ == "__main__":
    main()
