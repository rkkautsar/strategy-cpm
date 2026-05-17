"""3-tier rule test: defensive / normal / aggressive.

Base rule (already in production):
  HYG- AND TIP-           -> DEFENSIVE (100% best safe)
  HYG+ OR TIP+ (else)     -> NORMAL (FCP-15 pair selection)

Adds AGGRESSIVE tier on top of NORMAL when extra strict conditions met:
  HYG+ AND TIP+ AND <X>   -> AGGRESSIVE (swap part of FCP for QQQ/QLD)

Tests strict <X> rules:
  X1: TLT-              (rates rising)
  X2: EEM+              (EM risk-on)
  X3: SPY+              (equity momentum confirms)
  X4: TLT- AND EEM+     (strictest, 4-condition)

Aggressive deployment options:
  swap 25% FCP -> QQQ (no leverage, no decay)
  swap 50% FCP -> QQQ
  swap 25% FCP -> QLD (2x leveraged QQQ, no margin)
  swap 50% FCP -> QLD
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import fcp_live as fcp  # type: ignore
from fcp_live import load_panel, run_fcp_backtest, perf_metrics, sig_13612W

ALIASES = {"AGG": "AGG_stitched", "HYG": "HYG_stitched"}


def fetch_qld(panel):
    s = yf.Ticker("QLD").history(period="max", auto_adjust=True)["Close"]
    s.index = pd.DatetimeIndex(s.index).tz_localize(None)
    return s.reindex(panel.index, method="ffill")


def get_canary_state(monthly, sig_d, canaries):
    state = {}
    for c in canaries:
        col = ALIASES.get(c, c)
        if col not in monthly.columns:
            return None
        v = sig_13612W(monthly[col].loc[:sig_d])
        if pd.isna(v):
            return None
        state[c] = bool(v > 0)
    return state


def make_aggr_rule(extra_rule_fn):
    """Aggressive fires iff HYG+ AND TIP+ AND extra_rule_fn(state)."""
    def f(state):
        if not (state.get("HYG", False) and state.get("TIP", False)):
            return False
        return extra_rule_fn(state)
    return f


def compute_swap_rets(panel, base_rets, sigs, aggr_triggers, swap_pct, swap_asset_price):
    """Daily returns with FCP swapped out for swap_asset by swap_pct on aggressive months."""
    swap_ret = swap_asset_price.pct_change().fillna(0).reindex(base_rets.index, fill_value=0.0)
    firing = pd.Series(0.0, index=base_rets.index)
    for i, sig_d in enumerate(sigs):
        if not aggr_triggers.get(sig_d, False):
            continue
        future = panel.index[panel.index > sig_d]
        if len(future) < 2:
            continue
        apply_from = future[1]
        if i + 1 < len(sigs):
            next_sig = sigs[i + 1]
            next_future = panel.index[panel.index > next_sig]
            end_apply = next_future[1] if len(next_future) >= 2 else panel.index[-1]
        else:
            end_apply = panel.index[-1]
        mask = (base_rets.index >= apply_from) & (base_rets.index < end_apply)
        firing.loc[mask] = swap_pct
    # During firing: (1-swap)*base + swap*overlay
    return base_rets * (1 - firing) + firing * swap_ret


def main():
    out_path = Path(__file__).parent / "aggressive_tier_test.log"
    log_lines = []
    def log(s=""):
        log_lines.append(s); print(s)

    log("=" * 110)
    log("3-TIER RULE TEST: defensive / normal / AGGRESSIVE")
    log("Base canary (production): HYG- AND TIP- -> DEF, else NORMAL")
    log("Aggressive trigger: HYG+ AND TIP+ AND <strict extra condition>")
    log("=" * 110)

    panel = load_panel(start=pd.Timestamp("1999-01-01"))
    log(f"Panel: {panel.index[0].date()} -> {panel.index[-1].date()}")

    start = pd.Timestamp("2008-09-30")
    end = panel.index[-1]

    base_rets, _ = run_fcp_backtest(panel, start, end)
    base_m = perf_metrics(base_rets)
    log(f"BASE (production):  Sh={base_m['sharpe']:+.3f}  CAGR={base_m['cagr']*100:+.2f}%  "
        f"DD={base_m['max_drawdown']*100:+.2f}%")
    log("")

    qqq = panel["QQQ"]
    qld = fetch_qld(panel)
    spy = panel["SPY"]

    extra_rules = [
        ("X1: + TLT-",                  lambda s: not s.get("TLT", True)),
        ("X2: + EEM+",                  lambda s: s.get("EEM", False)),
        ("X3: + SPY+",                  lambda s: s.get("SPY", False)),
        ("X4: + TLT- AND EEM+",         lambda s: (not s.get("TLT", True)) and s.get("EEM", False)),
        ("X5: + TLT- AND SPY+",         lambda s: (not s.get("TLT", True)) and s.get("SPY", False)),
        ("X6: + EEM+ AND SPY+",         lambda s: s.get("EEM", False) and s.get("SPY", False)),
        ("X7: + TLT- AND EEM+ AND SPY+", lambda s: (not s.get("TLT", True)) and s.get("EEM", False) and s.get("SPY", False)),
    ]
    all_extras = sorted({"TLT","EEM","SPY","HYG","TIP"})

    monthly_idx = pd.DataFrame({"x":1}, index=panel.index).groupby(pd.Grouper(freq="ME")).tail(1)
    sigs = monthly_idx.index[(monthly_idx.index >= start) & (monthly_idx.index <= end)].tolist()

    swap_assets = [("QLD (2x)", qld)]
    swap_pcts = [0.10, 0.15, 0.20, 0.25, 0.30, 0.40]

    for label, extra_fn in extra_rules:
        log(f"--- AGGRESSIVE TRIGGER: HYG+ AND TIP+ AND {label} ---")
        aggr_rule = make_aggr_rule(extra_fn)
        triggers = {}
        for sd in sigs:
            mon = panel.loc[:sd].resample("ME").last()
            state = get_canary_state(mon, sd, all_extras)
            triggers[sd] = (state is not None) and aggr_rule(state)
        n_fire = sum(1 for v in triggers.values() if v)
        log(f"  Fires {n_fire}/{len(sigs)} ({n_fire/len(sigs)*100:.1f}%)  (base 100% FCP otherwise)")

        for asset_label, asset_px in swap_assets:
            if asset_px.dropna().empty:
                continue
            for swap_pct in swap_pcts:
                combined = compute_swap_rets(panel, base_rets, sigs, triggers, swap_pct, asset_px)
                m = perf_metrics(combined)
                log(f"    swap {int(swap_pct*100):2d}% -> {asset_label:10s}  "
                    f"Sh={m['sharpe']:+.3f}  CAGR={m['cagr']*100:+.2f}%  "
                    f"DD={m['max_drawdown']*100:+.2f}%  "
                    f"d_Sh={m['sharpe']-base_m['sharpe']:+.3f}  "
                    f"d_CAGR={(m['cagr']-base_m['cagr'])*100:+.2f}pp  "
                    f"d_DD={(m['max_drawdown']-base_m['max_drawdown'])*100:+.2f}pp")
            log("")
        log("")

    log("=" * 110)
    log("Look for: d_Sh > 0 means risk-adjusted improvement (rare for swaps).")
    log("Look for: d_CAGR > 0 with d_DD < 5pp = aggressive worth it on CAGR/DD basis.")
    log("=" * 110)
    with open(out_path, "w") as f:
        f.write("\n".join(log_lines))
    print(f"\nLog: {out_path}")


if __name__ == "__main__":
    main()
