#!/usr/bin/env python3
"""
BULL-QQQ - Regime-gated QQQ overlay with SHV cash fallback.

30% sleeve in the 60/30/10 CPM-BULL-NDX production blend.

Spec:
  Risk-on when BOTH:
    1. Macro:    HYG OR LQD OR TIP 13612U > 0  (credit/inflation canary)
    2. Trend:    QQQ 12-1 absolute momentum > 0 (Antonacci GEM)

  Risk-on  -> 100% QQQ
  Else     -> 100% SHV (ultra-short Treasury cash)

Usage:
    python bull_qqq_live.py allocate                  # show this month's target
    python bull_qqq_live.py allocate --signal-date 2026-04-30
    python bull_qqq_live.py backtest                  # standalone backtest
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

BULL_TICKER = "QQQ"
CASH_TICKER = "SHV"

MOMENTUM_LOOKBACK = 12       # months for 12-1 absolute momentum

# Macro canary: HYG OR LQD OR TIP 13612U > 0 (Keller HAA-family).
# State matrix evidence (canonical window): lone-positive HYG/LQD/TIP states
# all have positive forward QQQ; all-negative state has negative fwd QQQ.
# GLD or BND as additional OR is harmful (flight-to-safety bias).
CANARY_ASSETS = ["HYG_stitched", "LQD", "TIP"]
CANARY_RULE = "any_positive"

PROD_BULL_WEIGHT = 0.30      # BULL weight in 60/30/10 PROD blend

COST_BPS_PER_SIDE = 10


# ---------- Signal helpers ----------

def _absolute_momentum(s: pd.Series, sig_d: pd.Timestamp,
                       n: int = MOMENTUM_LOOKBACK) -> float:
    """N-month absolute total return (Antonacci 12-1 / Moskowitz TSMOM).
    SLOW anchor signal -- stays negative throughout sustained bears,
    avoiding whipsaws. `s` should be MONTHLY resampled prices."""
    sd = s.loc[:sig_d].dropna()
    if len(sd) < n + 1:
        return float("nan")
    return float(sd.iloc[-1] / sd.iloc[-n - 1] - 1)


def _trend_signal(monthly_qqq: pd.Series, sig_d: pd.Timestamp) -> tuple[bool, dict]:
    """Trend filter: QQQ 12-1 absolute momentum > 0 (Antonacci GEM standard).

    Returns (signal_on, diagnostics):
      signal_on = True if 12-1 absolute momentum is positive.
      12-1: slow anchor (anti-whipsaw, GEM standard)
    """
    mom_12_1 = _absolute_momentum(monthly_qqq, sig_d)
    mom_ok = pd.notna(mom_12_1) and mom_12_1 > 0
    return (mom_ok, dict(
        mom_12_1=mom_12_1, sig_13612U=float("nan"),
        mom_ok=mom_ok, w13_ok=False,
    ))


def _macro_gate(monthly: pd.DataFrame, sig_d: pd.Timestamp) -> tuple[bool, dict]:
    """Macro risk-on gate: HYG/LQD/TIP "any positive" 13612U canary."""
    sigs = {}
    for asset in CANARY_ASSETS:
        sigs[asset] = sig_13612U(monthly[asset].loc[:sig_d]) if asset in monthly.columns else float("nan")
    positives = [(pd.notna(v) and v > 0) for v in sigs.values()]
    if CANARY_RULE == "all_positive":
        canary_ok = all(positives)
    else:
        canary_ok = any(positives)
    diag = dict(
        hyg_sig=sigs.get("HYG_stitched", float("nan")),
        lqd_sig=sigs.get("LQD", float("nan")),
        tip_sig=sigs.get("TIP", float("nan")),
        canary_ok=canary_ok,
    )
    return (canary_ok, diag)


def _qqq_trend_ok(monthly: pd.DataFrame, sig_d: pd.Timestamp) -> tuple[bool, dict]:
    """QQQ trend filter: 12-1 absolute momentum > 0."""
    if BULL_TICKER not in monthly.columns:
        return (False, dict(mom_12_1=float("nan"), sig_13612U=float("nan"),
                             mom_ok=False, w13_ok=False))
    return _trend_signal(monthly[BULL_TICKER], sig_d)


# ---------- Allocation ----------

def _canary_state(monthly: pd.DataFrame, sig_d: pd.Timestamp) -> str | None:
    """Returns canary state string '+-+' etc. based on HYG/LQD/TIP 13612U signs."""
    chars = []
    for asset in CANARY_ASSETS:
        if asset not in monthly.columns:
            return None
        v = sig_13612U(monthly[asset].loc[:sig_d])
        if pd.isna(v):
            return None
        chars.append("+" if v > 0 else "-")
    return "".join(chars)


def compute_bull_qqq_weights(close_panel: pd.DataFrame, sig_d: pd.Timestamp
                              ) -> tuple[dict, str, dict]:
    """Returns (weights, regime_label, diagnostics).
    regime: 'BULL_QQQ' or 'CASH'."""
    monthly = close_panel.loc[:sig_d].resample("ME").last()
    gate_open, mdiag = _macro_gate(monthly, sig_d)
    state = _canary_state(monthly, sig_d)
    trend_ok, tdiag = _qqq_trend_ok(monthly, sig_d)
    if not trend_ok:
        return ({CASH_TICKER: 1.0}, "CASH",
                {**mdiag, **tdiag, "state": state,
                 "reason": "qqq_trend_off (12-1 mom <= 0)"})
    if not gate_open:
        return ({CASH_TICKER: 1.0}, "CASH",
                {**mdiag, **tdiag, "state": state,
                 "reason": "macro_gate_off (all of HYG/LQD/TIP <= 0)"})
    # Bull state: 100% QQQ (no state rotation in current spec).
    weights = {BULL_TICKER: 1.0}
    regime_label = f"BULL_{BULL_TICKER}"
    return (weights, regime_label,
            {**mdiag, **tdiag, "state": state, "bull_asset": BULL_TICKER,
             "bull_weights": weights, "gate_natural": gate_open})


# ---------- Backtest ----------

def run_bull_qqq_backtest(panel: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp,
                           cost_bps: float = COST_BPS_PER_SIDE) -> pd.Series:
    """Run BULL-QQQ standalone backtest.

    For each signal date (month-end):
      - If macro gate passes AND QQQ 12-1 momentum > 0: hold 100% QQQ
      - Else: hold 100% SHV cash
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
    all_tickers = {BULL_TICKER, CASH_TICKER}
    weights_per_day = {t: pd.Series(0.0, index=common) for t in all_tickers}
    state_per_day = pd.Series("", index=common, dtype=object)  # for cost calc

    for i, sig_d in enumerate(sigs):
        mon = panel.loc[:sig_d].resample("ME").last()
        gate_open, _ = _macro_gate(mon, sig_d)
        trend_ok, tdiag = _qqq_trend_ok(mon, sig_d)
        if trend_ok and gate_open:
            month_weights = {BULL_TICKER: 1.0}
        else:
            month_weights = {CASH_TICKER: 1.0}

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

    # Switching costs on any weight change (label change captures basket switches too)
    if cost_bps > 0:
        label_arr = state_per_day.values
        if len(label_arr) > 1:
            flips = np.where(label_arr[1:] != label_arr[:-1])[0] + 1
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

    print(f"BULL-QQQ Allocation @ {sig_d.date()} (signal date)")
    print("=" * 60)
    print(f"Bull asset:  {BULL_TICKER}  (100% when macro AND trend both pass)")
    print(f"Fallback:    {CASH_TICKER}  (100% cash when either filter fails)")
    print(f"Macro gate:  HYG/LQD/TIP any-positive 13612U")
    print(f"Trend filter: QQQ {MOMENTUM_LOOKBACK}-1 absolute momentum > 0 (Antonacci GEM)")
    print()

    weights, regime, diag = compute_bull_qqq_weights(panel, sig_d)

    print(f"Macro gate diagnostics:")
    print(f"  HYG 13612U = {diag['hyg_sig']:+.4f} ({'+' if diag['hyg_sig']>0 else '-'})")
    print(f"  LQD 13612U = {diag['lqd_sig']:+.4f} ({'+' if diag['lqd_sig']>0 else '-'})")
    print(f"  TIP 13612U = {diag['tip_sig']:+.4f} ({'+' if diag['tip_sig']>0 else '-'})")
    print(f"  Canary any-positive: {'YES' if diag['canary_ok'] else 'NO'}")
    if pd.notna(diag.get('mom_12_1', float('nan'))):
        print(f"\nTrend filter diagnostics:")
        print(f"  QQQ 12-1 mom = {diag['mom_12_1']*100:+7.2f}%  "
              f"(> 0: {'YES' if diag['mom_ok'] else 'NO'})    [slow anchor]")
        print(f"  QQQ 13612U   = {diag['sig_13612U']*100:+7.2f}%  "   # 13612U canonical HAA
              f"(> 0: {'YES' if diag['w13_ok'] else 'NO'})    [fast Keller-style]")
        print(f"  Trend OK (either positive): {'YES' if (diag['mom_ok'] or diag['w13_ok']) else 'NO'}")
    print()

    state = diag.get("state")
    if regime.startswith("BULL_"):
        print(f"Regime: {regime} (trend pass)")
    else:
        print(f"Regime: CASH ({diag.get('reason','unknown')}; canary state {state})")

    print(f"\n[BULL-QQQ sleeve target weights]")
    for t, w in sorted(weights.items(), key=lambda x: -x[1]):
        print(f"  {t:8s} {w*100:5.1f}%")


def cmd_backtest(args):
    start = pd.Timestamp(args.start)
    end = pd.Timestamp(args.end) if args.end else pd.Timestamp.today().normalize()
    panel_start = min(start - pd.DateOffset(years=3), pd.Timestamp("1995-01-01"))
    print(f"Loading panel from {panel_start.date()} ...")
    panel = load_panel(start=panel_start, end=end)
    print(f"Panel: {panel.index[0].date()} -> {panel.index[-1].date()}, {len(panel.columns)} assets")

    print(f"\nRunning BULL-QQQ backtest {start.date()} -> {end.date()} ...")
    cost_bps = 0 if args.no_cost else COST_BPS_PER_SIDE

    bull_qqq = run_bull_qqq_backtest(panel, start, end, cost_bps=cost_bps)
    fcp_rets, _ = run_cpm_backtest(panel, start, end, cost_bps=cost_bps)
    qqq = panel["QQQ"].ffill().pct_change().fillna(0).loc[start:end]
    spy = panel["SPY"].ffill().pct_change().fillna(0).loc[start:end]

    common = fcp_rets.index.intersection(bull_qqq.index)
    w_b = PROD_BULL_WEIGHT
    w_f = 1 - w_b
    blend = w_f * fcp_rets.loc[common] + w_b * bull_qqq.loc[common]
    prod_label = f"{int(w_f*100)}% CPM + {int(w_b*100)}% BULL-QQQ (2-sleeve historical)"
    print("Note: actual PROD is 60/30/10 CPM-BULL-NDX (see build_dashboard.py); this CLI prints 2-sleeve comparison.")

    strategies = [
        (prod_label, blend),
        ("BULL-QQQ standalone", bull_qqq),
        ("CPM-9 standalone", fcp_rets),
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
