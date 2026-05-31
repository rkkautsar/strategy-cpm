#!/usr/bin/env python3
"""
BULL-SPY - Regime-gated SPY overlay with SHV cash fallback.

20% sleeve in the 60/20/20 CPM-BULL-NDX production blend.

Spec:
  Risk-on when BOTH gates pass:
    1. Canary:    TIP 13612U > 0
    2. Asset mom: <BULL_TICKER> 12-month TR absolute momentum > 0 (Antonacci GEM)

  Risk-on  -> 100% SPY
  Else     -> 100% SHV (ultra-short Treasury cash)

Usage:
    python bull_qqq_live.py allocate                  # show this month's target
    python bull_qqq_live.py allocate --signal-date 2026-04-30
    python bull_qqq_live.py backtest                  # backtest
    python bull_qqq_live.py backtest --start 2010-01-01
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from cpm_live import (
    load_panel,
    run_cpm_backtest,
    perf_metrics,
    sig_13612U,
)


# ---------- Configuration ----------

# BULL sleeve risky ticker. SPY chosen for broad-market exposure; the NDX
# sleeve owns concentrated Nasdaq exposure.
BULL_TICKER = "SPY"
CASH_TICKER = "SHV"           # default cash if SAFE_POOL evaluation fails
SAFE_POOL = ["SHV", "IEF"]    # HAA-style best-of-safe: pick by 13612U momentum

# Macro canary: TIP 13612U momentum.
# Risk-on when canary asset has positive 13612U momentum.
CANARY_ASSETS = ["TIP"]
CANARY_RULE = "any_positive"

PROD_BULL_WEIGHT = 0.20      # BULL weight in 60/20/20 PROD blend

COST_BPS_PER_SIDE = 10

# ---------- Signal helpers ----------


def _trend_signal(monthly_spy: pd.Series, sig_d: pd.Timestamp) -> tuple[bool, dict]:
    """Trend filter: SPY 13612U momentum > 0 (HAA canonical).

    Returns (signal_on, diagnostics):
      signal_on = True if 13612U momentum is positive.
      Fast and responsive (HAA standard), no slow 12mo lag.
      Note: monthly_spy is already sliced to sig_d, do not re-slice.
    """
    spy_13612 = sig_13612U(monthly_spy)
    mom_ok = pd.notna(spy_13612) and spy_13612 > 0
    return (mom_ok, dict(
        mom_12_1=float("nan"), sig_13612U=spy_13612,
        mom_ok=mom_ok, w13_ok=mom_ok,
    ))


def _macro_gate(monthly: pd.DataFrame, sig_d: pd.Timestamp) -> tuple[bool, dict]:
    """Macro risk-on gate: TIP 13612U canary.
    Note: monthly is already sliced up to sig_d, do not re-slice with .loc[:sig_d]
    as calendar month-end index labels will drop the current month."""
    sigs = {}
    for asset in CANARY_ASSETS:
        sigs[asset] = sig_13612U(monthly[asset]) if asset in monthly.columns else float("nan")
    positives = [(pd.notna(v) and v > 0) for v in sigs.values()]
    if CANARY_RULE == "all_positive":
        canary_ok = all(positives)
    else:
        canary_ok = any(positives)
    diag = dict(
        tip_sig=sigs.get("TIP", float("nan")),
        canary_ok=canary_ok,
    )
    return (canary_ok, diag)


def _spy_trend_ok(monthly: pd.DataFrame, sig_d: pd.Timestamp) -> tuple[bool, dict]:
    """Asset trend filter: BULL_TICKER (SPY) 13612U momentum > 0.
    Active trend-following gate for BULL-SPY.
    """
    if BULL_TICKER not in monthly.columns:
        return (False, dict(mom_12_1=float("nan"), sig_13612U=float("nan"),
                             mom_ok=False, w13_ok=False))
    return _trend_signal(monthly[BULL_TICKER], sig_d)


# ---------- Allocation ----------

def _canary_state(monthly: pd.DataFrame, sig_d: pd.Timestamp) -> str | None:
    """Returns canary state string based on configured canary 13612U signs."""
    chars = []
    for asset in CANARY_ASSETS:
        if asset not in monthly.columns:
            return None
        v = sig_13612U(monthly[asset].loc[:sig_d])
        if pd.isna(v):
            return None
        chars.append("+" if v > 0 else "-")
    return "".join(chars)


def _pick_safe(monthly: pd.DataFrame) -> str:
    """HAA-style: pick the safe asset with highest 13612U momentum.
    Falls back to CASH_TICKER if no SAFE_POOL member has computable score."""
    scores = {}
    for s in SAFE_POOL:
        if s in monthly.columns:
            sc = sig_13612U(monthly[s])
            if pd.notna(sc):
                scores[s] = sc
    return max(scores, key=scores.get) if scores else CASH_TICKER


def compute_bull_qqq_weights(close_panel: pd.DataFrame, sig_d: pd.Timestamp,
                              daily_spy: pd.Series | None = None) -> tuple[dict, str, dict]:
    """Returns (weights, regime_label, diagnostics).
    regime: 'BULL_<asset>' or 'CASH'. Safe leg uses best-of(SAFE_POOL) by 13612U."""
    monthly = close_panel.loc[:sig_d].resample("ME").last()
    canary_ok, mdiag = _macro_gate(monthly, sig_d)
    state = _canary_state(monthly, sig_d)
    spy_trend_ok, tdiag = _spy_trend_ok(monthly, sig_d)

    gate_natural = canary_ok and spy_trend_ok
    all_diag = {**mdiag, **tdiag, "state": state,
                "spy_trend_ok": spy_trend_ok, "gate_natural": gate_natural}
    if not gate_natural:
        safe = _pick_safe(monthly)
        reasons = []
        if not canary_ok:
            reasons.append("macro_gate_off")
        if not spy_trend_ok:
            reasons.append(f"{BULL_TICKER}_trend_off")
        return ({safe: 1.0}, "CASH",
                {**all_diag, "reason": "; ".join(reasons), "picked_safe": safe})

    # Bull state: 100% SPY (no state rotation in current spec).
    weights = {BULL_TICKER: 1.0}
    regime_label = f"BULL_{BULL_TICKER}"
    return (weights, regime_label,
            {**all_diag, "bull_asset": BULL_TICKER, "bull_weights": weights})


# ---------- Backtest ----------

def run_bull_qqq_backtest(panel: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp,
                           cost_bps: float = COST_BPS_PER_SIDE) -> pd.Series:
    """Run BULL-SPY backtest.

    For each signal date (month-end):
      - If macro canary passes AND asset mom > 0: hold 100% SPY
      - Else: hold 100% best-of-safe (cash/IEF)
    Execution: T+1 OPEN (next trading day MOO). Weights apply from future[0] of signal
    date (first trading day after month-end). Backtest uses close-to-close on
    apply_from day (~5-10bps/yr overestimate vs strict open-to-close).
    Switching cost: 10bps/side on any state change.
    """
    if BULL_TICKER not in panel.columns:
        raise ValueError(f"{BULL_TICKER} not in panel")
    if CASH_TICKER not in panel.columns:
        raise ValueError(f"{CASH_TICKER} not in panel")

    daily_rets = panel.ffill().pct_change()
    monthly_idx = pd.DataFrame({"x": 1}, index=panel.index).groupby(pd.Grouper(freq="ME")).tail(1)
    sigs = monthly_idx.index[(monthly_idx.index >= start) & (monthly_idx.index <= end)].tolist()

    common = panel.index[(panel.index >= start) & (panel.index <= end)]
    all_tickers = {BULL_TICKER, CASH_TICKER, *SAFE_POOL}
    weights_per_day = {t: pd.Series(0.0, index=common) for t in all_tickers}
    state_per_day = pd.Series("", index=common, dtype=object)  # for cost calc

    for i, sig_d in enumerate(sigs):
        month_weights, _, _ = compute_bull_qqq_weights(panel, sig_d, panel[BULL_TICKER])

        future = common[common > sig_d]
        if len(future) < 1:
            continue
        apply_from = future[0]  # T+1 OPEN (next trading day MOO)
        if i + 1 < len(sigs):
            ns = sigs[i + 1]
            nf = common[common > ns]
            end_apply = nf[0] if len(nf) >= 1 else common[-1]
        else:
            end_apply = common[-1] + pd.Timedelta(days=1)
        mask = (common >= apply_from) & (common < end_apply)
        for t, w in month_weights.items():
            if t in weights_per_day:
                weights_per_day[t].loc[mask] = w
        # Cost-tracking label: deterministic basket string
        label = "+".join(f"{t}:{w:.2f}" for t, w in sorted(month_weights.items()))
        state_per_day.loc[mask] = label

    # Compute returns: sum across all weighted positions
    port = pd.Series(0.0, index=common)
    for t, w_s in weights_per_day.items():
        if t in daily_rets.columns:
            port = port + daily_rets[t].reindex(common).fillna(0.0) * w_s

    # Switching costs on any initialized-state change.
    # Ignore "" -> first-label transition to avoid phantom first-segment entry cost.
    if cost_bps > 0:
        label_arr = state_per_day.values
        if len(label_arr) > 1:
            flips = np.where(
                (label_arr[1:] != label_arr[:-1])
                & (label_arr[1:] != "")
                & (label_arr[:-1] != "")
            )[0] + 1
            for f in flips:
                port.iloc[f] -= 2.0 * cost_bps / 10000.0

    return port


# ---------- CLI ----------

def cmd_allocate(args):
    sig_d = pd.Timestamp(args.signal_date) if args.signal_date else None
    panel = load_panel(start=pd.Timestamp("1995-01-01"), end=sig_d)
    if sig_d is None:
        today = panel.index[-1]
        prior_month_end = today.replace(day=1) - pd.Timedelta(days=1)
        candidates = panel.index[panel.index <= prior_month_end]
        sig_d = candidates[-1] if len(candidates) > 0 else today

    print(f"BULL-SPY Allocation @ {sig_d.date()} (signal date)")
    print("=" * 60)
    print(f"Bull asset:  {BULL_TICKER}  (100% when canary AND asset momentum both pass)")
    print(f"Fallback:    best-of-safe (SHV/IEF by 13612U) when any gate fails")
    print(f"Canary:      TIP 13612U > 0")
    print(f"Asset mom:   {BULL_TICKER} 13612U momentum > 0 (HAA standard, circuit breaker)")
    print()

    weights, regime, diag = compute_bull_qqq_weights(panel, sig_d)

    print(f"Macro gate diagnostics:")
    print(f"  TIP 13612U = {diag['tip_sig']:+.4f} ({'+' if diag['tip_sig']>0 else '-'})")
    print(f"  Canary (TIP > 0): {'YES' if diag['canary_ok'] else 'NO'}")
    if pd.notna(diag.get('sig_13612U', float('nan'))):
        print(f"\nAsset mom diagnostics:")
        print(f"  {BULL_TICKER} 13612U = {diag['sig_13612U']*100:+7.2f}%  "
              f"(> 0: {'YES' if diag['mom_ok'] else 'NO'})  [circuit breaker]")
    print()

    state = diag.get("state")
    if regime.startswith("BULL_"):
        print(f"Regime: {regime} (trend pass)")
    else:
        print(f"Regime: CASH ({diag.get('reason','unknown')}; canary state {state})")

    print(f"\n[BULL sleeve target weights]")
    for t, w in sorted(weights.items(), key=lambda x: -x[1]):
        print(f"  {t:8s} {w*100:5.1f}%")


def cmd_backtest(args):
    start = pd.Timestamp(args.start)
    end = pd.Timestamp(args.end) if args.end else pd.Timestamp.today().normalize()
    panel_start = min(start - pd.DateOffset(years=3), pd.Timestamp("1995-01-01"))
    print(f"Loading panel from {panel_start.date()} ...")
    panel = load_panel(start=panel_start, end=end)
    print(f"Panel: {panel.index[0].date()} -> {panel.index[-1].date()}, {len(panel.columns)} assets")

    print(f"\nRunning BULL backtest {start.date()} -> {end.date()} ...")
    cost_bps = 0 if args.no_cost else COST_BPS_PER_SIDE

    bull_qqq = run_bull_qqq_backtest(panel, start, end, cost_bps=cost_bps)
    fcp_rets, _ = run_cpm_backtest(panel, start, end, cost_bps=cost_bps)
    qqq = panel["QQQ"].ffill().pct_change().fillna(0).loc[start:end]
    spy = panel["SPY"].ffill().pct_change().fillna(0).loc[start:end]

    common = fcp_rets.index.intersection(bull_qqq.index)
    w_b = PROD_BULL_WEIGHT
    w_f = 1 - w_b
    blend = w_f * fcp_rets.loc[common] + w_b * bull_qqq.loc[common]
    prod_label = f"{int(w_f*100)}% CPM + {int(w_b*100)}% BULL (2-sleeve)"
    print("Note: PROD blend is 60/20/20 CPM-BULL-NDX (see build_dashboard.py); this CLI prints the 2-sleeve diagnostic.")

    strategies = [
        (prod_label, blend),
        ("BULL", bull_qqq),
        ("CPM-9", fcp_rets),
        ("QQQ buy-hold", qqq),
        ("SPY buy-hold", spy),
    ]

    print(f"\n{'Strategy':40s} {'CAGR':>8s} {'Vol':>7s} {'Sharpe':>7s} {'MaxDD':>8s}")
    print("-" * 80)
    for label, daily in strategies:
        m = perf_metrics(daily)
        print(f"{label:40s} {m['cagr']*100:7.2f}% {m['vol']*100:6.2f}% "
              f"{m['sharpe']:7.3f} {m['max_drawdown']*100:7.2f}%")

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        df = pd.DataFrame({
            "PROD_blend": blend, "BULL_QQQ": bull_qqq,
            "FCP_only": fcp_rets, "QQQ": qqq, "SPY": spy,
        })
        df.to_csv(f"{out}_daily.csv")
        print(f"\nSaved daily returns: {out}_daily.csv")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    pa = sub.add_parser("allocate", help="Show target allocation for a signal date")
    pa.add_argument("--signal-date", default=None,
                    help="YYYY-MM-DD month-end (default: latest available)")
    pa.set_defaults(func=cmd_allocate)

    pb = sub.add_parser("backtest", help="Run full backtest")
    pb.add_argument("--start", default="2008-09-30")
    pb.add_argument("--end", default=None)
    pb.add_argument("--out", default=None, help="Output prefix for daily CSV")
    pb.add_argument("--no-cost", action="store_true", help="Disable transaction costs")
    pb.set_defaults(func=cmd_backtest)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
