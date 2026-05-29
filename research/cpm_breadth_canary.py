#!/usr/bin/env python3
"""
CPM Breadth Canary overlay evaluation.

Tests a NEW breadth-canary regime gate on top of the existing CPM structure
(HYG-OR-TIP canary + positive-Faber partial-safe). Breadth signal = n_positive,
the count of the 8 risky-universe assets with positive Faber (10mo SMA) trend
that month.

Variants (measured in the 60/40 two-sleeve CPM+BULL research baseline):
  V0    : PROD baseline, no breadth gate.
  V_lt2 : discrete risk-off (100% best_safe) if n_positive < 2
  V_lt3 : discrete risk-off if n_positive < 3
  V_lt4 : discrete risk-off if n_positive < 4
  V_contT4 : continuous scale CPM risky exposure by min(1, n_positive/4)
  V_contT6 : continuous scale CPM risky exposure by min(1, n_positive/6)

No production files are edited. This script reimplements the CPM backtest loop
with an overlay hook around the production compute_target_weights output.

Usage: .venv/bin/python research/cpm_breadth_canary.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cpm_live import (
    load_panel, perf_metrics, compute_target_weights, faber_sma_xs,
    RISKY_UNIVERSE, SAFE_POOL, CANARY_ASSETS, DEFAULT_CASH, COST_BPS_PER_SIDE,
)
from bull_qqq_live import run_bull_qqq_backtest

CLEAN_START = pd.Timestamp("2008-05-30")
STRESS_START = pd.Timestamp("1999-03-10")
END = pd.Timestamp("2026-05-22")

VARIANTS = ["V0", "V_lt2", "V_lt3", "V_lt4", "V_contT4", "V_contT6"]


def breadth_n_positive(close: pd.DataFrame, sig_d: pd.Timestamp,
                       universe: list) -> int:
    """Count of universe assets with positive Faber (price>SMA10) trend."""
    monthly = close.loc[:sig_d].resample("ME").last()
    faber = faber_sma_xs(monthly)
    n = 0
    for t in universe:
        if t in faber.index and pd.notna(faber[t]) and faber[t] > 0:
            n += 1
    return n


def apply_breadth_overlay(w: dict, safe: str, n_pos: int, variant: str) -> dict:
    """Apply breadth gate to base CPM weights. Returns new weight dict."""
    if variant == "V0":
        return w
    if variant.startswith("V_lt"):
        thresh = int(variant[len("V_lt"):])
        if n_pos < thresh:
            return {safe: 1.0}
        return w
    if variant.startswith("V_contT"):
        T = int(variant[len("V_contT"):])
        f = min(1.0, n_pos / T)
        if f >= 1.0:
            return w
        new_w: dict = {}
        leftover = 0.0
        for a, ww in w.items():
            if a in SAFE_POOL:
                new_w[a] = new_w.get(a, 0.0) + ww
            else:
                new_w[a] = new_w.get(a, 0.0) + ww * f
                leftover += ww * (1.0 - f)
        if leftover > 0:
            new_w[safe] = new_w.get(safe, 0.0) + leftover
        return new_w
    raise ValueError(f"unknown variant {variant}")


def run_cpm_breadth(panel: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp,
                    variant: str, cost_bps: float = COST_BPS_PER_SIDE):
    """CPM backtest with breadth overlay. Mirrors cpm_live.run_cpm_backtest
    but injects the breadth gate on top of base compute_target_weights output.

    Returns (daily_returns, diag_df) where diag_df has per-signal-date
    n_pos, base_regime, gated flag, and the realized factor applied.
    """
    cols = sorted(set(RISKY_UNIVERSE + SAFE_POOL + CANARY_ASSETS + [DEFAULT_CASH])
                  & set(panel.columns))
    close = panel[cols]
    monthly_idx = pd.DataFrame({"x": 1}, index=close.index).groupby(
        pd.Grouper(freq="ME")).tail(1)
    signal_dates = monthly_idx.index[(monthly_idx.index >= start)
                                     & (monthly_idx.index <= end)].tolist()

    weights_history = []
    diag_rows = []
    for i, sig_d in enumerate(signal_dates):
        w_base, new_pair, regime, safe = compute_target_weights(close, sig_d)
        n_pos = breadth_n_positive(close, sig_d, RISKY_UNIVERSE)
        w = apply_breadth_overlay(w_base, safe, n_pos, variant)
        # risky exposure (non-safe weight) before/after
        risky_base = sum(v for a, v in w_base.items() if a not in SAFE_POOL)
        risky_new = sum(v for a, v in w.items() if a not in SAFE_POOL)
        diag_rows.append({
            "sig_d": sig_d, "n_pos": n_pos, "base_regime": regime,
            "risky_base": risky_base, "risky_new": risky_new,
            "gated": risky_new < risky_base - 1e-9,
        })
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

    all_assets = sorted({a for h in weights_history for a in h["weights"]})
    df_w = pd.DataFrame(0.0, index=close.index,
                        columns=[a for a in all_assets if a in close.columns])
    for h in weights_history:
        mask = (close.index >= h["apply_from"]) & (close.index < h["end_apply"])
        for a, ww in h["weights"].items():
            if a in df_w.columns:
                df_w.loc[mask, a] = ww

    daily_ret = close.ffill().pct_change()
    common = [a for a in df_w.columns if a in daily_ret.columns]
    raw_returns = (df_w[common] * daily_ret[common]).sum(axis=1, min_count=1).fillna(0.0)

    for i in range(len(weights_history)):
        prev_w = weights_history[i - 1]["weights"] if i > 0 else {}
        curr_w = weights_history[i]["weights"]
        keys = set(curr_w) | set(prev_w)
        turnover = sum(abs(curr_w.get(k, 0.0) - prev_w.get(k, 0.0)) for k in keys)
        cost = turnover * cost_bps / 10000.0
        af = weights_history[i]["apply_from"]
        if af in raw_returns.index:
            raw_returns.loc[af] -= cost

    out = raw_returns.loc[(raw_returns.index >= start) & (raw_returns.index <= end)]
    diag = pd.DataFrame(diag_rows).set_index("sig_d")
    return out, diag, weights_history


def annual_turnover(weights_history: list) -> float:
    """One-way annualized turnover from weights history."""
    if len(weights_history) < 2:
        return float("nan")
    tot = 0.0
    for i in range(1, len(weights_history)):
        prev_w = weights_history[i - 1]["weights"]
        curr_w = weights_history[i]["weights"]
        keys = set(curr_w) | set(prev_w)
        tot += 0.5 * sum(abs(curr_w.get(k, 0.0) - prev_w.get(k, 0.0)) for k in keys)
    months = len(weights_history)
    return tot / months * 12.0


def cal_return(daily: pd.Series, y0: str, y1: str) -> float:
    seg = daily.loc[y0:y1]
    if seg.empty:
        return float("nan")
    return (1.0 + seg).prod() - 1.0


def metrics_row(daily: pd.Series, cash: pd.Series) -> dict:
    m = perf_metrics(daily, cash)
    return m


def main():
    print("Loading panel ...")
    panel = load_panel(start=pd.Timestamp("1995-01-01"), end=END)
    print(f"Panel: {panel.index[0].date()} -> {panel.index[-1].date()}, "
          f"{len(panel.columns)} cols")
    cash_daily = panel["SHV"].ffill().pct_change().dropna()

    windows = {"clean": (CLEAN_START, END), "stress": (STRESS_START, END)}

    # Precompute BULL sleeves per window (variant-independent)
    bull = {}
    for wname, (s, e) in windows.items():
        bull[wname] = run_bull_qqq_backtest(panel, s, e)

    # Run all variants both windows
    results = {}   # (variant, window) -> dict
    diags = {}     # (variant, window) -> diag df
    daily_cpm = {} # (variant, window) -> cpm daily series
    daily_blend = {}
    turnovers = {} # (variant, window) -> annual turnover

    for variant in VARIANTS:
        for wname, (s, e) in windows.items():
            cpm, diag, wh = run_cpm_breadth(panel, s, e, variant)
            b = bull[wname]
            common = cpm.index.intersection(b.index)
            cpm = cpm.reindex(common)
            b2 = b.reindex(common)
            blend = 0.60 * cpm + 0.40 * b2
            daily_cpm[(variant, wname)] = cpm
            daily_blend[(variant, wname)] = blend
            diags[(variant, wname)] = diag
            turnovers[(variant, wname)] = annual_turnover(wh)
            results[(variant, wname, "cpm")] = metrics_row(cpm, cash_daily)
            results[(variant, wname, "blend")] = metrics_row(blend, cash_daily)
            print(f"  {variant:9s} {wname:6s}  blend Sharpe="
                  f"{results[(variant, wname, 'blend')]['sharpe']:.3f} "
                  f"CAGR={results[(variant, wname, 'blend')]['cagr']*100:.2f}% "
                  f"MDD={results[(variant, wname, 'blend')]['max_drawdown']*100:.2f}%")

    # ---- V0 verification ----
    v0c = results[("V0", "clean", "blend")]
    v0_ok = (abs(v0c["sharpe"] - 1.347) < 0.01
             and abs(v0c["cagr"] * 100 - 13.59) < 0.1
             and abs(v0c["max_drawdown"] * 100 - (-9.82)) < 0.1)
    print(f"\nV0 60/40 clean blend: Sharpe={v0c['sharpe']:.3f} "
          f"CAGR={v0c['cagr']*100:.2f}% MaxDD={v0c['max_drawdown']*100:.2f}%")
    print(f"V0 reproduction check (target 1.347/13.59%/-9.82%): "
          f"{'PASS' if v0_ok else 'FAIL'}")

    payload = dict(results=results, diags=diags, daily_cpm=daily_cpm,
                   daily_blend=daily_blend, turnovers=turnovers,
                   cash_daily=cash_daily, v0_ok=v0_ok, windows=windows)
    return payload


if __name__ == "__main__":
    payload = main()
    # Persist computed objects for findings generation
    import pickle
    with open("/tmp/cpm_breadth_payload.pkl", "wb") as f:
        pickle.dump(payload, f)
    print("\nSaved payload -> /tmp/cpm_breadth_payload.pkl")
