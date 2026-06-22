#!/usr/bin/env python3
"""
Regime-B Stress Blend Experiment
=================================
Tests using a MARKET-BASED regime signal (Regime B) instead of the Sahm recession
indicator as the blend weight shift trigger.

Variants:
  1. Baseline        - no overlay, always BASE_BLEND_WEIGHTS
  2. Sahm stress     - shift to STRESS weights when SahmREALTIME >= 0.50
  3. Regime B stress - shift to STRESS weights when SPY 12m ret <= 0 OR vol top tercile
  4. Hybrid          - shift to STRESS weights when Regime B OR Sahm fires
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import BASE_BLEND_WEIGHTS, SAHM_STRESS_BLEND_WEIGHTS

DATA_DIR = ROOT / "data"
GM_DIR = ROOT / "tests" / "test_golden_master"
PROXY_PATH = DATA_DIR / "proxy_adjusted_close_daily.csv"
SAHM_PATH = DATA_DIR / "fred_SAHMREALTIME.csv"

SLEEVE_FILES = {
    "cpm": GM_DIR / "test_numeric_csv_stream_cpm_mooex_csv_.csv",
    "ndx": GM_DIR / "test_numeric_csv_stream_ndx_mooex_csv_.csv",
    "val": GM_DIR / "test_numeric_csv_stream_val_mooex_csv_.csv",
    "rpv": GM_DIR / "test_numeric_csv_stream_rpv_mooex_csv_.csv",
}

STRESS_WEIGHTS = SAHM_STRESS_BLEND_WEIGHTS
NORMAL_WEIGHTS = BASE_BLEND_WEIGHTS
COST_BPS_PER_SIDE = 10.0

SAHM_LAG_MONTHS = 1
SAHM_LAG_DAYS = 7
SAHM_THRESHOLD = 0.50


def load_sleeve_returns(name: str) -> pd.Series:
    df = pd.read_csv(SLEEVE_FILES[name], index_col=0, parse_dates=True)
    return df.iloc[:, 0]


def load_all_sleeves() -> pd.DataFrame:
    df = pd.DataFrame({name: load_sleeve_returns(name)
                       for name in ["cpm", "ndx", "val", "rpv"]})
    df.index = pd.to_datetime(df.index)
    df = df.sort_index()
    return df


def load_spy_prices() -> pd.Series:
    df = pd.read_csv(PROXY_PATH, index_col=0, parse_dates=True)
    spy = df["SPY"].dropna().sort_index()
    return spy[spy > 0]


def load_sahm() -> pd.Series:
    df = pd.read_csv(SAHM_PATH, index_col=0, parse_dates=True)
    return df.squeeze().sort_index()


def is_sahm_stress(sig_d: pd.Timestamp, sahm: pd.Series) -> bool:
    if sahm.empty:
        return False
    avail = sahm.copy()
    avail.index = avail.index + pd.DateOffset(months=SAHM_LAG_MONTHS, days=SAHM_LAG_DAYS)
    avail = avail.sort_index()
    known = avail.loc[avail.index <= sig_d]
    if known.empty:
        return False
    value = known.iloc[-1]
    return bool(pd.notna(value) and float(value) >= SAHM_THRESHOLD)


def compute_regime_b_signals(
    sig_dates: list[pd.Timestamp],
    spy_close: pd.Series,
    n_vol_window: int = 63,
) -> pd.Series:
    """Regime B = SPY 12m return <= 0 OR SPY 63d realized vol in top tercile."""
    spy_daily = spy_close.ffill().pct_change()
    rv = spy_daily.rolling(n_vol_window).std() * np.sqrt(252)
    rv_me = rv.resample("ME").last()
    m_close = spy_close.resample("ME").last()
    trend12 = m_close / m_close.shift(12) - 1.0

    rv_eval = rv_me.loc[rv_me.index >= sig_dates[0] - pd.DateOffset(months=13)].dropna()
    q2 = rv_eval.quantile(2 / 3)

    signals = {}
    for sig_d in sig_dates:
        prior = sig_d - pd.offsets.MonthEnd(1)
        v = rv_me.get(prior, np.nan)
        t = trend12.get(prior, np.nan)
        if pd.isna(v) or pd.isna(t):
            signals[sig_d] = False
            continue
        high_vol = v > q2
        down_trend = t <= 0
        signals[sig_d] = bool(down_trend or high_vol)
    return pd.Series(signals)


def compute_sahm_signals(sig_dates: list[pd.Timestamp], sahm: pd.Series) -> pd.Series:
    return pd.Series({sd: is_sahm_stress(sd, sahm) for sd in sig_dates})


def compute_variant_returns(
    sleeve_df: pd.DataFrame,
    sig_dates: list[pd.Timestamp],
    stress_signal: pd.Series,
    with_cost: bool = True,
) -> tuple[pd.Series, pd.DataFrame, list]:
    idx = sleeve_df.index
    weight_df = pd.DataFrame(0.0, index=idx, columns=list(NORMAL_WEIGHTS.keys()))
    prev_weights = dict(NORMAL_WEIGHTS)
    turnover_events = []

    for i, sig_d in enumerate(sig_dates):
        active = dict(STRESS_WEIGHTS) if stress_signal.get(sig_d, False) else dict(NORMAL_WEIGHTS)
        future = idx[idx > sig_d]
        if len(future) < 1:
            continue
        apply_from = future[0]
        if i + 1 < len(sig_dates):
            next_sig = sig_dates[i + 1]
            next_future = idx[idx > next_sig]
            end_apply = next_future[0] if len(next_future) >= 1 else (idx[-1] + pd.Timedelta(days=1))
        else:
            end_apply = idx[-1] + pd.Timedelta(days=1)
        mask = (idx >= apply_from) & (idx < end_apply)
        for sleeve in NORMAL_WEIGHTS:
            weight_df.loc[mask, sleeve] = active.get(sleeve, 0.0)
        all_keys = set(prev_weights) | set(active)
        turnover = sum(abs(active.get(k, 0.0) - prev_weights.get(k, 0.0)) for k in all_keys)
        turnover_events.append((apply_from, turnover))
        prev_weights = active

    daily_returns = pd.Series(0.0, index=idx, dtype=float)
    for sleeve in NORMAL_WEIGHTS:
        daily_returns += sleeve_df[sleeve] * weight_df[sleeve]

    if with_cost:
        for apply_from, turnover in turnover_events:
            if apply_from in daily_returns.index:
                daily_returns.loc[apply_from] -= turnover * COST_BPS_PER_SIDE / 10000.0
    return daily_returns, weight_df, turnover_events


def compute_metrics(returns: pd.Series, rf_annual: float = 0.05) -> dict:
    cum = (1 + returns).cumprod()
    n_years = len(returns) / 252
    cagr = cum.iloc[-1] ** (1 / n_years) - 1 if n_years > 0 else 0.0
    vol = returns.std(ddof=1) * np.sqrt(252) if len(returns) > 1 else 0.0
    excess = returns - rf_annual / 252
    sharpe = (excess.mean() / returns.std(ddof=1) * np.sqrt(252)
              if returns.std(ddof=1) > 0 else 0.0)
    cum_series = (1 + returns).cumprod()
    rolling_max = cum_series.cummax()
    drawdown = cum_series / rolling_max - 1.0
    max_dd = drawdown.min()
    calmar = cagr / abs(max_dd) if max_dd != 0 else 0.0
    return {"CAGR": cagr, "Vol": vol, "Sharpe": sharpe,
            "MaxDD": max_dd, "Calmar": calmar}


def count_stress_days(weight_df: pd.DataFrame) -> int:
    col = weight_df.get("rpv", pd.Series(0.0, index=weight_df.index))
    return int((col == STRESS_WEIGHTS["rpv"]).sum())


def annual_returns(returns: pd.Series) -> pd.Series:
    return (1 + returns).resample("YE").prod() - 1.0


def fmt_pct(x):
    if pd.isna(x):
        return "     N/A"
    return f"{x:>7.2%}"

def fmt_sharpe(x):
    if pd.isna(x):
        return "    N/A"
    return f"{x:>6.4f}"


def main():
    print("=" * 72)
    print("REGIME-B STRESS BLEND EXPERIMENT")
    print("=" * 72)

    print("\n[1] Loading data...")
    sleeves = load_all_sleeves()
    print(f"  Sleeve returns: {sleeves.index[0].date()} to {sleeves.index[-1].date()} ({len(sleeves)} days)")

    spy_close = load_spy_prices()
    print(f"  SPY prices: {spy_close.index[0].date()} to {spy_close.index[-1].date()}")

    sahm = load_sahm()
    print(f"  Sahm data: {sahm.index[0].date()} to {sahm.index[-1].date()}")

    cov_start = sleeves.index[0] + pd.DateOffset(days=1)
    sig_candidates = sleeves.loc[cov_start:].index
    sig_dates = pd.Series(index=sig_candidates).resample("ME").last().index.tolist()
    sig_dates = [d for d in sig_dates
                 if d >= spy_close.index[0] + pd.DateOffset(years=1)]
    print(f"  Signal dates: {len(sig_dates)} ({sig_dates[0].date()} to {sig_dates[-1].date()})")

    print("\n[2] Computing stress signals...")
    sahm_signal = compute_sahm_signals(sig_dates, sahm)
    regime_b_signal = compute_regime_b_signals(sig_dates, spy_close)
    hybrid_signal = sahm_signal | regime_b_signal

    n_sahm = int(sahm_signal.sum())
    n_reg = int(regime_b_signal.sum())
    n_hyb = int(hybrid_signal.sum())
    total = len(sig_dates)
    print(f"  Sahm stress:     {n_sahm}/{total} ({n_sahm/total*100:.1f}%)")
    print(f"  Regime B stress: {n_reg}/{total} ({n_reg/total*100:.1f}%)")
    print(f"  Hybrid:          {n_hyb}/{total} ({n_hyb/total*100:.1f}%)")

    sahm_dates = sorted([d for d, v in sahm_signal.items() if v])
    reg_dates = sorted([d for d, v in regime_b_signal.items() if v])
    overlap = sorted(set(sahm_dates) & set(reg_dates))

    print(f"\n  Sahm stress dates ({len(sahm_dates)}):")
    for d in sahm_dates:
        print(f"    {d.date()}")
    print(f"\n  Regime B dates ({len(reg_dates)}):")
    for d in reg_dates:
        print(f"    {d.date()}")
    if overlap:
        print(f"\n  Overlap ({len(overlap)}):")
        for d in overlap:
            print(f"    {d.date()}")

    print("\n[3] Computing blended returns...")
    variants = [
        ("1. Baseline", pd.Series({sd: False for sd in sig_dates})),
        ("2. Sahm stress", sahm_signal),
        ("3. Regime B stress", regime_b_signal),
        ("4. Hybrid", hybrid_signal),
    ]

    results = {}
    weight_dfs = {}
    turnovers = {}
    for name, signal in variants:
        ret, wdf, te = compute_variant_returns(sleeves, sig_dates, signal)
        results[name] = ret
        weight_dfs[name] = wdf
        turnovers[name] = te
        sd = count_stress_days(wdf)
        print(f"  {name}: {len(ret)} days, {sd} stress days")

    print("\n" + "=" * 72)
    print("OVERALL METRICS  (2009-05 to 2026-04, 17y)")
    print("=" * 72)

    all_metrics = {}
    for name, _ in variants:
        m = compute_metrics(results[name])
        all_metrics[name] = m

    item_fmt = "{:<28s}  CAGR={:>7.2%}  Vol={:>6.2%}  Sharpe={:>6.4f}  MaxDD={:>7.2%}  Calmar={:>5.2f}  stress={:>4d}d"
    for name, _ in variants:
        m = all_metrics[name]
        sd = count_stress_days(weight_dfs[name])
        print(item_fmt.format(name, m["CAGR"], m["Vol"], m["Sharpe"], m["MaxDD"], m["Calmar"], sd))

    # GM reference
    gm = pd.read_csv(GM_DIR / "test_numeric_csv_stream_blend_csv_.csv",
                     index_col=0, parse_dates=True).iloc[:, 0]
    gm_m = compute_metrics(gm)
    print(f"\n  {'Golden Master (prod blend)':<28s}  CAGR={gm_m['CAGR']:>7.2%}  "
          f"Vol={gm_m['Vol']:>6.2%}  Sharpe={gm_m['Sharpe']:>6.4f}  "
          f"MaxDD={gm_m['MaxDD']:>7.2%}  Calmar={gm_m['Calmar']:>5.2f}")

    print("\n" + "=" * 72)
    print("ANNUAL RETURNS (focus years)")
    print("=" * 72)
    focus_years = [2018, 2020, 2022, 2025]
    line = f"{'Variant':<30s}"
    for y in focus_years:
        line += f" {y:>8d}"
    print(line)
    print("-" * (30 + 9 * len(focus_years)))
    for name, _ in variants:
        ann = annual_returns(results[name])
        line = f"{name:<30s}"
        for y in focus_years:
            vals = ann[ann.index.year == y]
            v = vals.iloc[0] if len(vals) > 0 else float("nan")
            line += f" {v:>8.2%}" if pd.notna(v) else f" {'N/A':>8s}"
        print(line)

    print("\n" + "=" * 72)
    print("STRESS WINDOW RETURNS")
    print("=" * 72)
    windows = [
        ("Oct 2018", "2018-10-01", "2018-10-31"),
        ("Mar 2020", "2020-03-01", "2020-03-31"),
        ("Jan-Oct 2022", "2022-01-01", "2022-10-31"),
    ]
    if results["1. Baseline"].index.max() >= pd.Timestamp("2025-04-01"):
        windows.append(("Apr 2025", "2025-04-01", "2025-04-30"))

    for label, s, e in windows:
        print(f"\n  {label}:")
        for name, _ in variants:
            mask = (results[name].index >= s) & (results[name].index <= e)
            if mask.any():
                r = (1 + results[name][mask]).prod() - 1
                print(f"    {name:<28s}: {r:>8.2%}")

    print("\n" + "=" * 72)
    print("MONTH-LEVEL DIFFERENCES vs BASELINE")
    print("=" * 72)
    monthly_rets = {}
    for name, _ in variants:
        monthly_rets[name] = (1 + results[name]).resample("ME").prod() - 1
    base_m = monthly_rets["1. Baseline"]
    for vn in ["2. Sahm stress", "3. Regime B stress", "4. Hybrid"]:
        diff = monthly_rets[vn] - base_m
        n_diff = (diff != 0).sum()
        print(f"\n  {vn}:")
        print(f"    Different months: {n_diff}/{len(diff.dropna())}")
        if n_diff > 0:
            print(f"    Mean diff: {diff[diff != 0].mean():+.6f}")
            print(f"    Std diff:  {diff[diff != 0].std():.6f}")
            print(f"    Max up:    {diff.max():+.6f}")
            print(f"    Max down:  {diff.min():+.6f}")

    print("\n" + "=" * 72)
    print("TURNOVER")
    print("=" * 72)
    for name, _ in variants:
        te = turnovers[name]
        total_turn = sum(t for _, t in te)
        n_rebal = len(te)
        ann_turn = total_turn / (len(results[name]) / 252)
        print(f"  {name:<28s}: {n_rebal:>3d} rebalances, total turn={total_turn:.3f}, ann={ann_turn:.3f}")

    print("\nDone.")


if __name__ == "__main__":
    main()
