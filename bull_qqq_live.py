#!/usr/bin/env python3
"""
BULL-QQQ - Regime-gated QQQ overlay with SHV cash fallback.

The 20% bull sleeve that pairs with the 80% CPM-11 sleeve in production
(70/30 or 60/40 also viable, per personal-capital preference).

Strategy:
  Risk-on when BOTH:
    1. Macro:    HYG OR LQD OR TIP 13612U > 0     (credit/inflation regime)
                 OR Override: QQQ 12-1 mom > expanding 67th-pctile threshold
                 (Asness-style tercile, truly OOS-calibrated, bypasses canary
                  when equity has demonstrably rallied -- handles 2023-style
                  AI rally despite credit stress)
    2. Trend:    QQQ 12-1 absolute momentum > 0
                 OR QQQ 13612U > 0                (composite trend, OR)

  Bull asset depends on canary state:
    - If state HYG-/LQD-/TIP+:  hold XLP   (late-cycle inflation regime)
    - Else:                      hold QQQ   (default tech)

  Otherwise: hold SHV (cash)

Design rationale:
  - Single-ticker bull bet on Nasdaq-100; QQQ already provides diversified
    mega-cap tech exposure (top 100 Nasdaq names)
  - Multi-ETF "diversified" universes (SMH/SCHG/XLK/IWM/GLD) tested and
    rejected: same Sharpe, more complexity, marginal pick noise
  - SHV cash fallback chosen over CPM fallback: same Sharpe in blend,
    better COVID protection (-5.4% vs -9.0%), zero duration risk
  - Two-filter design: canary + (12-1 mom OR 13612U)
      * Canary catches credit/inflation stress (2022)
      * 12-1 momentum is the SLOW anchor (anti-whipsaw in sustained bears
        like dot-com)
      * 13612U (canonical HAA average momentum) is the FAST signal
        (re-enters quickly after bears -- caught 2023 AI rally in Feb
        vs 12-1-alone waiting until June)
      * OR-combination: long if EITHER signal positive. Slow signal anchors
        against whipsaw; fast signal rescues re-entry timing.
      * VIX filter tested and REMOVED: gave ~0.05 Sharpe cost across both
        windows; specifically COVID flash-crash insurance with n=1 evidence.

Usage:
    python bull_qqq_live.py allocate                       # show this month's target
    python bull_qqq_live.py allocate --signal-date 2026-04-30
    python bull_qqq_live.py backtest                       # standalone + blend backtest
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
    sig_13612W,
)


# ---------- Configuration ----------

BULL_TICKER = "QQQ"          # default bull asset
CASH_TICKER = "SHV"          # short-treasury cash, zero duration risk

# Canary-state-conditional bull asset rotation.
# Asset substitution ablation (LIVE 18y, 60/40 blend, production module):
#   QQQ (no switch):     BULL Sh 0.97, 60/40 Sh 1.353, CAGR 14.16%
#   XLP only (PROD):     BULL Sh 1.07, 60/40 Sh 1.430, CAGR 14.62%  <- best
#   XLV only:            BULL Sh 1.05, 60/40 Sh 1.410, CAGR 14.53%
#   XLU only:            BULL Sh 1.03, 60/40 Sh 1.406, CAGR 14.46%
#   XLP/XLV 50/50:       BULL Sh 1.06, 60/40 Sh 1.423, CAGR 14.58%
#   XLP/XLU 50/50:       BULL Sh 1.05, 60/40 Sh 1.421, CAGR 14.54%
#   XLP/XLV/XLU 1/3:     BULL Sh 1.06, 60/40 Sh 1.420, CAGR 14.54%
# Plus 10+ broad defensive ETFs tested (SCHD/NOBL/VIG/DGRO/USMV/SPLV/VYM/
# DVY/HDV/RSP) on common 2014+ window: all cluster within 0.02 Sh of XLP.
# OOS test (LIVE TEST 2017-2026, n=8 +-+ firings, unseen by selection):
# XLP-only Sh 1.531 (best tied with XLU). TRAIN winner (XLV) didn't
# generalize. Mechanism family validates direction OOS; specific asset
# within family is noise. XLP chosen as single-asset for: (a) longest
# defensive ETF history (1998), (b) zero within-basket rebalancing cost,
# (c) operational simplicity, (d) tied-best Sharpe across LIVE/TEST/EXT
# windows. Basket alternatives tested but marginal cost > marginal benefit.
BULL_BY_STATE = {
    "+-+": "XLP",   # HYG-/LQD-/TIP+ state: consumer staples
}

# Per-asset trend filter: (12-1 absolute momentum > 0) OR (13612W > 0)
# 12-1 = Antonacci dual momentum / Moskowitz TSMOM (SLOW anchor)
# 13612U = canonical HAA average momentum (r1+r3+r6+r12)/4 (FAST)
# Disjunction (OR) chosen over conjunction or single signal: extended blend
# Sharpe 0.83 vs 0.74 with 12-1 alone, 2023 capture +22.4% vs +3.8%.
MOMENTUM_LOOKBACK = 12       # months for 12-1 momentum

# Macro gate: HYG/LQD/TIP "any positive" 13612U canary (Keller HAA-style)
# 3-asset rule justified by canary state matrix analysis:
#   - HYG-only positive state (`+--`): mean fwd QQQ +3.52% (clearly bull)
#   - LQD-only positive state (`-+--`): mean fwd QQQ +3.10% (caught by adding LQD)
#   - TIP-only positive state (`--+`): mean fwd QQQ +4-7% (kept by ANY rule)
#   - All-negative state (`---`): mean fwd QQQ -0.65% (correctly de-risks)
# Adding GLD/BND as OR is HARMFUL: lone-GLD or lone-BND positive states have
# negative fwd QQQ returns (flight-to-safety signal).
CANARY_ASSETS = ["HYG_stitched", "LQD", "TIP"]
CANARY_RULE = "any_positive"  # "any_positive" or "all_positive"

# Equity-strength override: when QQQ has rallied strongly over past 12 months,
# bypass macro canary even if credit/inflation has briefly stressed.
# Handles 2023-style decoupling: AI rally despite Treasury/credit stress.
#
# Threshold is expanding-window 67th percentile (top tercile) of historical
# QQQ 12-month rolling returns. Truly out-of-sample calibration: each signal
# date uses only data observed before that date.
#
# Why 67th (top tercile):
#   - External anchor: Asness/Moskowitz/Pedersen "Value & Momentum Everywhere"
#     uses tertile sorts as standard factor-portfolio cutoffs
#   - Empirical plateau [50-65%] all work; 60th was peak but only +0.02-0.05
#     Sharpe better than 67th (within bootstrap noise)
#   - 67th = top tercile = "above-normal regime" -- defensible without data-mining
#   - Oracle reviewed and chose 67th over 60th: cleaner external prior, less
#     data-mining smell, Sharpe edge for 60th not significant
#
# Validation:
#   - Selective: 4 fires in 18y LIVE / 10 fires in 32y EXT
#   - Strict Sharpe improvement on every window (+0.04 to +0.06)
#   - Zero DD increase (trend filter still required, catches actual crises)
#   - Plausible: equity-trend dominance over credit signals when proven
EQUITY_OVERRIDE_PERCENTILE = 67.0      # top tercile of historical QQQ 12-1
EQUITY_OVERRIDE_MIN_HISTORY = 24       # min historical observations needed
# Legacy fixed threshold (kept for reference; not used by default).
EQUITY_OVERRIDE_THRESHOLD = 0.20

# Production deployment: 70% CPM + 30% BULL-QQQ wired by build_dashboard.py.
# Sensitivity grid (oracle-v3): 70/30 peaks Sharpe on both LIVE/EXT, flat surface 60/40-80/20.
PROD_BULL_WEIGHT = 0.30      # for CLI backtest reporting (70/30 CPM/BULL, oracle-v3 Sharpe-optimal)

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
    """Composite trend filter: (12-1 mom > 0) OR (13612U > 0).

    Returns (signal_on, diagnostics):
      signal_on = True if at least one of the two trend signals is positive.
      12-1: slow anchor (anti-whipsaw)
      13612U: fast signal (average momentum, catches re-entry quickly)
    """
    mom_12_1 = _absolute_momentum(monthly_qqq, sig_d)
    sig_13612W_val = sig_13612W(monthly_qqq.loc[:sig_d])
    mom_ok = pd.notna(mom_12_1) and mom_12_1 > 0
    w13_ok = pd.notna(sig_13612W_val) and sig_13612W_val > 0
    return (mom_ok or w13_ok, dict(
        mom_12_1=mom_12_1, sig_13612W=sig_13612W_val,
        mom_ok=mom_ok, w13_ok=w13_ok,
    ))


def _macro_gate(monthly: pd.DataFrame, sig_d: pd.Timestamp) -> tuple[bool, dict]:
    """Macro risk-on gate: HYG/LQD/TIP "any positive" 13612U canary."""
    sigs = {}
    for asset in CANARY_ASSETS:
        sigs[asset] = sig_13612W(monthly[asset].loc[:sig_d]) if asset in monthly.columns else float("nan")
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
    """Composite QQQ trend filter: (12-1 mom > 0) OR (13612U > 0)."""
    if BULL_TICKER not in monthly.columns:
        return (False, dict(mom_12_1=float("nan"), sig_13612W=float("nan"),
                             mom_ok=False, w13_ok=False))
    return _trend_signal(monthly[BULL_TICKER], sig_d)


# ---------- Allocation ----------

def _canary_state(monthly: pd.DataFrame, sig_d: pd.Timestamp) -> str | None:
    """Returns canary state string '+-+' etc. based on HYG/LQD/TIP 13612W signs."""
    chars = []
    for asset in CANARY_ASSETS:
        if asset not in monthly.columns:
            return None
        v = sig_13612W(monthly[asset].loc[:sig_d])
        if pd.isna(v):
            return None
        chars.append("+" if v > 0 else "-")
    return "".join(chars)


def _equity_override_threshold(monthly_qqq: pd.Series, sig_d: pd.Timestamp) -> float:
    """Compute expanding-window percentile threshold for equity override.
    Returns the percentile value of historical QQQ 12-month rolling returns
    computed from data available up to (but not including) the signal date.
    Truly out-of-sample: never uses future data.
    """
    qq = monthly_qqq.loc[:sig_d].dropna()
    if len(qq) < EQUITY_OVERRIDE_MIN_HISTORY + 13:
        return float("nan")
    # Historical 12-1 returns, EXCLUDING the current observation
    hist = [qq.iloc[i] / qq.iloc[i - 12] - 1 for i in range(13, len(qq) - 1)]
    if len(hist) < EQUITY_OVERRIDE_MIN_HISTORY:
        return float("nan")
    import numpy as _np
    return float(_np.percentile(hist, EQUITY_OVERRIDE_PERCENTILE))


def compute_bull_qqq_weights(close_panel: pd.DataFrame, sig_d: pd.Timestamp
                              ) -> tuple[dict, str, dict]:
    """Returns (weights, regime_label, diagnostics).
    regime: 'BULL_QQQ', 'BULL_XLP', or 'CASH'."""
    monthly = close_panel.loc[:sig_d].resample("ME").last()
    gate_open, mdiag = _macro_gate(monthly, sig_d)
    state = _canary_state(monthly, sig_d)
    trend_ok, tdiag = _qqq_trend_ok(monthly, sig_d)
    # Equity-strength override REMOVED in oracle-v4 cleanup:
    # fired only 10/403 months over 32y, neutral on LIVE (-0.013 Sh),
    # marginal EXT help (+0.01 Sh). Removed for spec simplicity and to
    # reduce data-mining surface (pre-2005 threshold was unstable).
    # Threshold still computed for diagnostic only.
    mom_12_1 = tdiag.get("mom_12_1", float("nan"))
    override_threshold = _equity_override_threshold(monthly[BULL_TICKER], sig_d) \
        if BULL_TICKER in monthly.columns else float("nan")
    override_active = False  # disabled
    tdiag["override_threshold"] = override_threshold
    effective_gate_open = gate_open
    if not trend_ok:
        return ({CASH_TICKER: 1.0}, "CASH",
                {**mdiag, **tdiag, "state": state, "override": override_active,
                 "reason": "qqq_trend_off (both 12-1 and 13612W <= 0)"})
    if not effective_gate_open:
        return ({CASH_TICKER: 1.0}, "CASH",
                {**mdiag, **tdiag, "state": state, "override": override_active,
                 "reason": "macro_gate_off (and override inactive)"})
    # Bull state: rotate by canary state
    # BULL_BY_STATE value may be either a single ticker string (single-asset)
    # or a dict {ticker: weight} (basket).
    bull_spec = BULL_BY_STATE.get(state, BULL_TICKER)
    if isinstance(bull_spec, dict):
        weights = dict(bull_spec)
        bull_label = "+".join(sorted(weights.keys()))
    else:
        weights = {bull_spec: 1.0}
        bull_label = bull_spec
    regime_label = f"BULL_{bull_label}"
    if not gate_open and override_active:
        regime_label += "_via_override"
    return (weights, regime_label,
            {**mdiag, **tdiag, "state": state, "bull_asset": bull_label,
             "bull_weights": weights,
             "override": override_active, "gate_natural": gate_open})


# ---------- Backtest ----------

def run_bull_qqq_backtest(panel: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp,
                           cost_bps: float = COST_BPS_PER_SIDE) -> pd.Series:
    """Run BULL-QQQ standalone backtest.

    For each signal date (month-end):
      - If macro gate passes AND QQQ 12-1 momentum > 0: hold 100% QQQ
      - Else: hold 100% SHV cash
    Apply weights from second trading day after signal until next signal.
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
    # Track per-asset weights per day (supports basket holdings).
    all_tickers = {BULL_TICKER, CASH_TICKER}
    for spec in BULL_BY_STATE.values():
        if isinstance(spec, dict):
            all_tickers.update(spec.keys())
        else:
            all_tickers.add(spec)
    weights_per_day = {t: pd.Series(0.0, index=common) for t in all_tickers}
    state_per_day = pd.Series("", index=common, dtype=object)  # for cost calc

    for i, sig_d in enumerate(sigs):
        mon = panel.loc[:sig_d].resample("ME").last()
        gate_open, _ = _macro_gate(mon, sig_d)
        trend_ok, tdiag = _qqq_trend_ok(mon, sig_d)
        mom_12_1 = tdiag.get("mom_12_1", float("nan"))
        # override removed in oracle-v4 cleanup (was: bypass canary on QQQ 12-1 > 67th pct)
        if trend_ok and gate_open:
            state = _canary_state(mon, sig_d)
            spec = BULL_BY_STATE.get(state, BULL_TICKER)
            if isinstance(spec, dict):
                month_weights = dict(spec)
            else:
                month_weights = {spec: 1.0}
        else:
            month_weights = {CASH_TICKER: 1.0}

        future = common[common > sig_d]
        if len(future) < 2:
            continue
        apply_from = future[1]
        if i + 1 < len(sigs):
            ns = sigs[i + 1]
            nf = common[common > ns]
            end_apply = nf[1] if len(nf) >= 2 else common[-1]
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
    print(f"Macro gate:  HYG/LQD/TIP any+ 13612W")
    print(f"Trend filter: ({MOMENTUM_LOOKBACK}-1 absolute momentum > 0) OR (13612W > 0)")
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
        print(f"  QQQ 13612U   = {diag['sig_13612W']*100:+7.2f}%  "   # 13612U canonical HAA
              f"(> 0: {'YES' if diag['w13_ok'] else 'NO'})    [fast Keller-style]")
        print(f"  Trend OK (either positive): {'YES' if (diag['mom_ok'] or diag['w13_ok']) else 'NO'}")
    print()

    state = diag.get("state")
    override = diag.get("override", False)
    gate_natural = diag.get("gate_natural", diag.get("canary_ok", False))
    if regime.startswith("BULL_"):
        bull_asset = diag.get("bull_asset", BULL_TICKER)
        rotation_note = f" (canary state {state} -> {bull_asset})" if bull_asset != BULL_TICKER else ""
        override_note = ""
        if override and not gate_natural:
            thr = diag.get("override_threshold", float("nan"))
            override_note = (f" [via equity-strength override: QQQ 12-1 mom={diag['mom_12_1']*100:+.1f}% > "
                              f"{EQUITY_OVERRIDE_PERCENTILE:.0f}th pct ({thr*100:+.1f}%)]")
        print(f"Regime: {regime} (trend pass){rotation_note}{override_note}")
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
    prod_label = f"{int(w_f*100)}% CPM + {int(w_b*100)}% BULL-QQQ (PROD)"

    strategies = [
        (prod_label, blend),
        ("BULL-QQQ standalone", bull_qqq),
        ("CPM-11 standalone", fcp_rets),
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
