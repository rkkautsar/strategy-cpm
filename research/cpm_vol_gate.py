#!/usr/bin/env python3
"""
CPM Volatility-Regime Gate overlay evaluation.

Tests a NEW volatility-regime gate on top of the existing CPM structure
(HYG-OR-TIP canary + positive-Faber partial-safe + K=4 + min-var pair). The
gate mirrors the BULL sleeve's existing RV crossover logic (_vol_gate_ok:
RV_20d < RV_252d) but is applied as an overlay on CPM, which today has NO vol
gate. Goal: catch the high-breadth-then-crash regime the breadth canary misses
(notably the 2020 COVID crash, a canary blind spot).

Vol signals tested:
  SIG-RV-SPY  : SPY RV_20d >= RV_252d  (mirror BULL gate, applied to CPM)
  SIG-RV-BOOK : RV of the V0 (ungated) CPM book daily return, 20d >= 252d
  SIG-VIX     : NOT AVAILABLE. No VIX/VIX3M series in the proxy panel
                (panel columns checked - no VIX, VIX3M). Realized-vol
                crossovers used instead, per task fallback.

Gate actions:
  binary  : when fired -> 100% best_safe
  cont    : scale risky exposure by f = min(1, RV_252/RV_20); remainder to
            best_safe (no leverage, cap 1.0)

Variants (60/40 two-sleeve CPM+BULL research baseline):
  V0            : PROD baseline, no vol gate.
  V_rvspy_bin   : SIG-RV-SPY, binary risk-off
  V_rvspy_cont  : SIG-RV-SPY, continuous scale
  V_rvbook_bin  : SIG-RV-BOOK, binary risk-off
  V_rvbook_cont : SIG-RV-BOOK, continuous scale

No production files edited. Reimplements the CPM backtest loop with an overlay
hook around the production compute_target_weights output.

Usage: .venv/bin/python research/cpm_vol_gate.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cpm_live import (
    load_panel, perf_metrics, compute_target_weights,
    RISKY_UNIVERSE, SAFE_POOL, CANARY_ASSETS, DEFAULT_CASH, COST_BPS_PER_SIDE,
)
from bull_spy_live import run_bull_spy_backtest

CLEAN_START = pd.Timestamp("2008-05-30")
STRESS_START = pd.Timestamp("1999-03-10")
END = pd.Timestamp("2026-05-22")

VARIANTS = ["V0", "V_rvspy_bin", "V_rvspy_cont", "V_rvbook_bin", "V_rvbook_cont"]


def rv_crossover(daily_ret: pd.Series, sig_d: pd.Timestamp) -> tuple[float, float]:
    """Mirror BULL _vol_gate_ok: RV_20d, RV_252d annualized from daily returns.
    Returns (v20, v252). If <252 obs, returns (0,0) -> never fires."""
    sub = daily_ret.loc[:sig_d].dropna()
    if len(sub) < 252:
        return 0.0, 0.0
    v20 = float(sub.tail(20).std() * np.sqrt(252))
    v252 = float(sub.tail(252).std() * np.sqrt(252))
    return v20, v252


def gate_state(v20: float, v252: float) -> tuple[bool, float]:
    """Return (fired, scale_factor).
    fired = RV_20 >= RV_252 (high-vol regime).
    scale_factor = min(1, v252/v20) when v20>0 else 1.0 (for continuous action)."""
    if v252 <= 0.0 and v20 <= 0.0:
        return False, 1.0
    fired = v20 >= v252
    f = min(1.0, v252 / v20) if v20 > 0 else 1.0
    return fired, f


def apply_vol_overlay(w: dict, safe: str, fired: bool, scale: float,
                      action: str) -> dict:
    """Apply vol gate to base CPM weights. action in {'bin','cont'}."""
    if action == "bin":
        if fired:
            return {safe: 1.0}
        return w
    if action == "cont":
        if not fired or scale >= 0.999:
            return w
        new_w: dict = {}
        leftover = 0.0
        for a, ww in w.items():
            if a in SAFE_POOL:
                new_w[a] = new_w.get(a, 0.0) + ww
            else:
                new_w[a] = new_w.get(a, 0.0) + ww * scale
                leftover += ww * (1.0 - scale)
        if leftover > 0:
            new_w[safe] = new_w.get(safe, 0.0) + leftover
        return new_w
    raise ValueError(f"unknown action {action}")


def variant_signal_action(variant: str) -> tuple[str, str]:
    """Map variant -> (signal, action). signal in {'spy','book'}."""
    if variant == "V0":
        return ("none", "none")
    parts = variant.split("_")  # V, rvXXX, bin/cont
    sig = "spy" if "rvspy" in variant else "book"
    action = "bin" if variant.endswith("bin") else "cont"
    return (sig, action)


def run_cpm_vol_gate(panel: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp,
                     variant: str, spy_ret: pd.Series,
                     book_signal: pd.Series | None,
                     cost_bps: float = COST_BPS_PER_SIDE):
    """CPM backtest with vol-gate overlay. book_signal (if signal=='book') is a
    per-signal-date precomputed Series mapping sig_d -> (v20, v252) tuples from
    the V0 ungated CPM book daily returns.

    Returns (daily_returns, diag_df, weights_history).
    """
    cols = sorted(set(RISKY_UNIVERSE + SAFE_POOL + CANARY_ASSETS + [DEFAULT_CASH])
                  & set(panel.columns))
    close = panel[cols]
    monthly_idx = pd.DataFrame({"x": 1}, index=close.index).groupby(
        pd.Grouper(freq="ME")).tail(1)
    signal_dates = monthly_idx.index[(monthly_idx.index >= start)
                                     & (monthly_idx.index <= end)].tolist()

    sig, action = variant_signal_action(variant)

    weights_history = []
    diag_rows = []
    for i, sig_d in enumerate(signal_dates):
        w_base, new_pair, regime, safe = compute_target_weights(close, sig_d)
        if variant == "V0":
            fired, scale = False, 1.0
            v20 = v252 = np.nan
        else:
            if sig == "spy":
                v20, v252 = rv_crossover(spy_ret, sig_d)
            else:
                v20, v252 = book_signal.get(sig_d, (0.0, 0.0))
            fired, scale = gate_state(v20, v252)
        w = apply_vol_overlay(w_base, safe, fired, scale, action) if variant != "V0" else w_base
        risky_base = sum(v for a, v in w_base.items() if a not in SAFE_POOL)
        risky_new = sum(v for a, v in w.items() if a not in SAFE_POOL)
        diag_rows.append({
            "sig_d": sig_d, "v20": v20, "v252": v252, "fired": fired,
            "scale": scale, "base_regime": regime,
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


def precompute_book_signal(cpm_v0_daily: pd.Series,
                           signal_dates: list) -> dict:
    """Per-signal-date (v20, v252) of the V0 ungated CPM book daily return."""
    out = {}
    for sd in signal_dates:
        out[sd] = rv_crossover(cpm_v0_daily, sd)
    return out


def annual_turnover(weights_history: list) -> float:
    if len(weights_history) < 2:
        return float("nan")
    tot = 0.0
    for i in range(1, len(weights_history)):
        prev_w = weights_history[i - 1]["weights"]
        curr_w = weights_history[i]["weights"]
        keys = set(curr_w) | set(prev_w)
        tot += 0.5 * sum(abs(curr_w.get(k, 0.0) - prev_w.get(k, 0.0)) for k in keys)
    return tot / len(weights_history) * 12.0


def cal_return(daily: pd.Series, y0: str, y1: str) -> float:
    seg = daily.loc[y0:y1]
    if seg.empty:
        return float("nan")
    return (1.0 + seg).prod() - 1.0


def main():
    print("Loading panel ...")
    panel = load_panel(start=pd.Timestamp("1995-01-01"), end=END)
    print(f"Panel: {panel.index[0].date()} -> {panel.index[-1].date()}, "
          f"{len(panel.columns)} cols")
    has_vix = any("VIX" in c.upper() for c in panel.columns)
    print(f"VIX in panel: {has_vix}")
    cash_daily = panel["SHV"].ffill().pct_change().dropna()
    spy_ret = panel["SPY"].ffill().pct_change()

    windows = {"clean": (CLEAN_START, END), "stress": (STRESS_START, END)}

    # BULL sleeves per window (variant-independent)
    bull = {}
    for wname, (s, e) in windows.items():
        bull[wname] = run_bull_spy_backtest(panel, s, e)

    # First pass: V0 ungated CPM book daily returns per window (for book signal
    # and for forward-return cohort study).
    cpm_v0 = {}
    for wname, (s, e) in windows.items():
        # use a wide start so RV_252 warmup exists at the window start
        cpm0, diag0, wh0 = run_cpm_vol_gate(
            panel, pd.Timestamp("1997-01-01"), e, "V0", spy_ret, None)
        cpm_v0[wname] = cpm0

    # signal dates per window
    monthly_idx = pd.DataFrame({"x": 1}, index=panel.index).groupby(
        pd.Grouper(freq="ME")).tail(1)
    book_signals = {}
    for wname, (s, e) in windows.items():
        sds = monthly_idx.index[(monthly_idx.index >= s) & (monthly_idx.index <= e)].tolist()
        book_signals[wname] = precompute_book_signal(cpm_v0[wname], sds)

    results = {}
    diags = {}
    daily_cpm = {}
    daily_blend = {}
    turnovers = {}

    for variant in VARIANTS:
        for wname, (s, e) in windows.items():
            sig, action = variant_signal_action(variant)
            bsig = book_signals[wname] if sig == "book" else None
            cpm, diag, wh = run_cpm_vol_gate(panel, s, e, variant, spy_ret, bsig)
            b = bull[wname]
            common = cpm.index.intersection(b.index)
            cpm = cpm.reindex(common)
            b2 = b.reindex(common)
            blend = 0.60 * cpm + 0.40 * b2
            daily_cpm[(variant, wname)] = cpm
            daily_blend[(variant, wname)] = blend
            diags[(variant, wname)] = diag
            turnovers[(variant, wname)] = annual_turnover(wh)
            results[(variant, wname, "cpm")] = perf_metrics(cpm, cash_daily)
            results[(variant, wname, "blend")] = perf_metrics(blend, cash_daily)
            r = results[(variant, wname, "blend")]
            print(f"  {variant:14s} {wname:6s}  blend Sharpe={r['sharpe']:.3f} "
                  f"CAGR={r['cagr']*100:.2f}% MDD={r['max_drawdown']*100:.2f}%")

    # V0 reproduction check
    v0c = results[("V0", "clean", "blend")]
    v0_ok = (abs(v0c["sharpe"] - 1.347) < 0.01
             and abs(v0c["cagr"] * 100 - 13.59) < 0.1
             and abs(v0c["max_drawdown"] * 100 - (-9.82)) < 0.1)
    print(f"\nV0 60/40 clean blend: Sharpe={v0c['sharpe']:.3f} "
          f"CAGR={v0c['cagr']*100:.2f}% MaxDD={v0c['max_drawdown']*100:.2f}%")
    print(f"V0 reproduction (target 1.347/13.59%/-9.82%): "
          f"{'PASS' if v0_ok else 'FAIL'}")

    payload = dict(results=results, diags=diags, daily_cpm=daily_cpm,
                   daily_blend=daily_blend, turnovers=turnovers,
                   cash_daily=cash_daily, v0_ok=v0_ok, windows=windows,
                   cpm_v0=cpm_v0, has_vix=has_vix)
    return payload


if __name__ == "__main__":
    payload = main()
    import pickle
    with open("/tmp/cpm_vol_gate_payload.pkl", "wb") as f:
        pickle.dump(payload, f)
    print("\nSaved payload -> /tmp/cpm_vol_gate_payload.pkl")
