#!/usr/bin/env python3
"""
BULL-QQQ - Regime-gated QQQ overlay with SHV cash fallback.

30% sleeve in the 60/30/10 CPM-BULL-NDX production blend.

Spec:
  Risk-on when ALL THREE gates pass (each using 'any positive' rule):
    1. Canary:    HYG OR TIP 13612U > 0     (Keller HAA-style credit/inflation)
    2. Macro:     curve OR vol pillar > 0   (2 orthogonal macro indicators)
         - curve:  IEF 63d ret > TLT 63d ret  (yield-curve steepening)
         - vol:    SPY 63d vol < 252d avg     (low-vol regime)
    3. Asset mom: <BULL_TICKER> 12-1 absolute momentum > 0
                  (Antonacci dual momentum on the risky asset)

  All three layers use Keller-canonical 'any positive' rule.
  Pillars are limited to factors not already covered by canary (credit)
  or asset_mom (price/trend), so curve+vol are the only two orthogonal
  macro signals worth adding. Trend (SPY 200d MA) was dropped as redundant
  with asset_mom; credit (HYG 200d MA) was dropped as redundant with canary.

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

BULL_TICKER = "SPY"
CASH_TICKER = "SHV"           # default cash if SAFE_POOL evaluation fails
SAFE_POOL = ["SHV", "IEF"]    # HAA-style best-of-safe: pick by 13612U momentum

MOMENTUM_LOOKBACK = 12       # legacy: 12-1 momentum, kept for research imports

# Macro canary: HYG OR TIP 13612U > 0 (Keller HAA-family, simplified).
# LQD removed (was HYG+LQD+TIP) because IG corporate bonds rally on rate cuts
# during equity crashes (duration effect), making "any positive" rule falsely
# permissive in dotcom-style regimes. EXT backtest (1999-2026) showed LQD
# inclusion costs ~0.20 Sharpe and pushes Bull-QQQ DD to -57% vs -27% without.
# GLD or BND as additional OR is harmful (flight-to-safety bias).
CANARY_ASSETS = ["HYG_stitched", "TIP"]
CANARY_RULE = "any_positive"

# Binary composite gate: 4 yes/no pillars, threshold count.
# Two truly orthogonal macro indicators -- the only pillars not redundant with
# the canary (credit) or asset_mom (price/trend). Pair ablation across 6
# (window x asset) combos showed curve+vol OR strictly dominates 4-pillar
# 2-of-4 on avg Sharpe and DD. Both use natural midpoint cutoffs and
# Keller-style 'any positive' rule (no tuned threshold).
COMPOSITE_VOL_ASSET = "SPY"       # interchangeable with QQQ within noise
COMPOSITE_CURVE_WINDOW = 63       # days for IEF-TLT return spread (3m)
COMPOSITE_VOL_SHORT = 63          # days for short vol estimate (3m)
COMPOSITE_VOL_LONG  = 252         # days for long vol comparison (1y)

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
    """Macro risk-on gate: HYG/TIP "any positive" 13612U canary."""
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
    """DEPRECATED: legacy QQQ 12-1 momentum filter, no longer used by gate.
    Kept for research imports / backward compat in diagnostics only."""
    if BULL_TICKER not in monthly.columns:
        return (False, dict(mom_12_1=float("nan"), sig_13612U=float("nan"),
                             mom_ok=False, w13_ok=False))
    return _trend_signal(monthly[BULL_TICKER], sig_d)


def _binary_pillars(close_panel: pd.DataFrame, sig_d: pd.Timestamp) -> dict:
    """Evaluate the 2 binary macro pillars at sig_d.
    Returns dict {name: 0|1, ...} with only pillars whose inputs are available.
    Missing pillars are omitted (not counted as negative)."""
    sub = close_panel.loc[:sig_d].ffill()
    if len(sub) < COMPOSITE_VOL_LONG:
        return {}
    pillars = {}

    # curve: IEF 63d ret > TLT 63d ret (yield-curve steepening signal)
    if "TLT" in sub.columns and "IEF" in sub.columns:
        ief_r = sub["IEF"].pct_change().tail(COMPOSITE_CURVE_WINDOW).sum()
        tlt_r = sub["TLT"].pct_change().tail(COMPOSITE_CURVE_WINDOW).sum()
        if pd.notna(ief_r) and pd.notna(tlt_r):
            pillars["curve"] = 1 if ief_r > tlt_r else 0

    # vol: SPY 63d vol < 252d avg of 63d rolling vol
    if COMPOSITE_VOL_ASSET in sub.columns:
        rets = sub[COMPOSITE_VOL_ASSET].pct_change().dropna()
        if len(rets) >= COMPOSITE_VOL_LONG:
            v_short = rets.tail(COMPOSITE_VOL_SHORT).std() * np.sqrt(252)
            v_long_avg = (rets.tail(COMPOSITE_VOL_LONG)
                          .rolling(COMPOSITE_VOL_SHORT).std().dropna()
                          * np.sqrt(252)).mean()
            if pd.notna(v_short) and pd.notna(v_long_avg):
                pillars["vol"] = 1 if v_short < v_long_avg else 0

    return pillars


def _composite_gate(close_panel: pd.DataFrame, sig_d: pd.Timestamp
                     ) -> tuple[bool, dict]:
    """Binary 2-pillar composite gate using 'any positive' (Keller-canonical) rule.
    Returns (gate_open, diag). Open when >= 1 pillar positive AND both evaluable.
    If fewer than 2 pillars evaluable (data missing), gate closes."""
    pillars = _binary_pillars(close_panel, sig_d)
    n_pos = sum(pillars.values()) if pillars else 0
    n_eval = len(pillars)
    gate_open = (n_eval >= 2) and (n_pos >= 1)
    diag = dict(
        pillar_curve=pillars.get("curve"),
        pillar_vol=pillars.get("vol"),
        composite_n_pos=n_pos,
        composite_n_eval=n_eval,
        composite_ok=gate_open,
    )
    return (gate_open, diag)


# ---------- Allocation ----------

def _canary_state(monthly: pd.DataFrame, sig_d: pd.Timestamp) -> str | None:
    """Returns canary state string '+-' etc. based on HYG/TIP 13612U signs."""
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


def compute_bull_qqq_weights(close_panel: pd.DataFrame, sig_d: pd.Timestamp
                              ) -> tuple[dict, str, dict]:
    """Returns (weights, regime_label, diagnostics).
    regime: 'BULL_<asset>' or 'CASH'. Safe leg uses best-of(SAFE_POOL) by 13612U."""
    monthly = close_panel.loc[:sig_d].resample("ME").last()
    canary_ok, mdiag = _macro_gate(monthly, sig_d)
    state = _canary_state(monthly, sig_d)
    composite_ok, cdiag = _composite_gate(close_panel, sig_d)
    asset_mom_ok, tdiag = _qqq_trend_ok(monthly, sig_d)
    all_diag = {**mdiag, **cdiag, **tdiag, "state": state}
    if not (canary_ok and composite_ok and asset_mom_ok):
        safe = _pick_safe(monthly)
        reason = ('macro_gate_off' if not canary_ok
                  else f"composite_off ({cdiag['composite_n_pos']}/2 pillars positive, need any 1)" if not composite_ok
                  else f"asset_mom_off ({BULL_TICKER} 12-1 mom <= 0; circuit breaker on risky asset)")
        return ({safe: 1.0}, "CASH",
                {**all_diag, "reason": reason, "picked_safe": safe})
    # Bull state: 100% QQQ (no state rotation in current spec).
    weights = {BULL_TICKER: 1.0}
    regime_label = f"BULL_{BULL_TICKER}"
    return (weights, regime_label,
            {**all_diag, "bull_asset": BULL_TICKER,
             "bull_weights": weights, "gate_natural": canary_ok})


# ---------- Backtest ----------

def run_bull_qqq_backtest(panel: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp,
                           cost_bps: float = COST_BPS_PER_SIDE) -> pd.Series:
    """Run BULL-QQQ standalone backtest.

    For each signal date (month-end):
      - If macro canary passes AND binary composite (>=2 of 4 pillars) passes:
        hold 100% QQQ
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
    all_tickers = {BULL_TICKER, CASH_TICKER, *SAFE_POOL}
    weights_per_day = {t: pd.Series(0.0, index=common) for t in all_tickers}
    state_per_day = pd.Series("", index=common, dtype=object)  # for cost calc

    for i, sig_d in enumerate(sigs):
        mon = panel.loc[:sig_d].resample("ME").last()
        canary_ok, _ = _macro_gate(mon, sig_d)
        composite_ok, _ = _composite_gate(panel, sig_d)
        asset_mom_ok, _ = _qqq_trend_ok(mon, sig_d)
        if canary_ok and composite_ok and asset_mom_ok:
            month_weights = {BULL_TICKER: 1.0}
        else:
            safe = _pick_safe(mon)
            month_weights = {safe: 1.0}

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
    print(f"Macro gate:  HYG/TIP any-positive 13612U")
    print(f"Composite:   any 1 of 2 macro pillars positive")
    print(f"             (IEF-TLT curve, SPY low-vol)")
    print(f"Asset mom:   {BULL_TICKER} 12-1 absolute momentum > 0 (circuit breaker)")
    print()

    weights, regime, diag = compute_bull_qqq_weights(panel, sig_d)

    print(f"Macro gate diagnostics:")
    print(f"  HYG 13612U = {diag['hyg_sig']:+.4f} ({'+' if diag['hyg_sig']>0 else '-'})")

    print(f"  TIP 13612U = {diag['tip_sig']:+.4f} ({'+' if diag['tip_sig']>0 else '-'})")
    print(f"  Canary any-positive: {'YES' if diag['canary_ok'] else 'NO'}")
    print(f"\nComposite pillar diagnostics:")
    def _show_pillar(name, val):
        if val is None:
            print(f"  {name:8s} = N/A")
        else:
            print(f"  {name:8s} = {'+' if val == 1 else '-'}")
    _show_pillar("curve",  diag.get("pillar_curve"))
    _show_pillar("vol",    diag.get("pillar_vol"))
    print(f"  Composite: {diag.get('composite_n_pos',0)}/2 positive  "
          f"(any 1 needed: {'YES' if diag.get('composite_ok') else 'NO'})")
    if pd.notna(diag.get('mom_12_1', float('nan'))):
        print(f"\nAsset mom diagnostics:")
        print(f"  {BULL_TICKER} 12-1 mom = {diag['mom_12_1']*100:+7.2f}%  "
              f"(> 0: {'YES' if diag['mom_ok'] else 'NO'})  [circuit breaker]")
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
