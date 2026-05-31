"""Throwaway research: CPM turn-of-month (TOM) TEMPORAL DECAY + already-discounted check.

Read-only analyst harness. Reuses production SIGNAL/WEIGHT fns from cpm_live.py
UNCHANGED and the cpm_execution_cliff.py timing harness UNCHANGED. Varies only
the WINDOW over which the day-since-rebalance attribution is measured. Does NOT
edit prod or memo; does NOT commit.

Question
--------
Prior work (research/cpm_execution_cliff_findings.md) found ~0.10-0.20 of the
~1.19-1.21 headline Sharpe is a turn-of-month (TOM) effect: EOM config earns
~14.9 bp on trading-day-1 of the month vs ~4.9 bp rest-of-month (full window).
That day-1 attribution is EMPIRICAL on the full window. Two open questions:

1. TEMPORAL DECAY: is the day-1 / TOM premium DECAYING over subperiods
   (consistent with crowding/arbitrage), STABLE, or NOISY? Measure day-1 bp,
   rest-of-month bp, day-1 standalone Sharpe, and day-1 standalone P&L
   contribution per subperiod.
2. ALREADY-DISCOUNTED: split into 2008-16 vs 2017-26 halves. The recent half
   shows Sharpe ~1.38. How much of each half-Sharpe is TOM (day-1) driven? If
   TOM is already small post-2015, the strong recent Sharpe is NOT TOM-driven
   and the microstructure concern is partly already discounted in the clean
   number.

Convention: identical to cpm_execution_cliff.py (close-to-close, exec_lag=0,
10 bps/side). EOM config (eom, 0). Anchor: EOM clean Sharpe ~1.206 cc / 1.191
t1_moo. We compute returns + day-since-rebalance ONCE over the full clean
window, then slice by date subperiod for attribution -- so the rebalance basket
sequence is identical to the headline backtest; only the measurement window
varies.
"""
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cpm_live import (
    load_panel, perf_metrics,
    RISKY_UNIVERSE, SAFE_POOL, CANARY_ASSETS, DEFAULT_CASH, COST_BPS_PER_SIDE,
)
from research.cpm_execution_cliff import cpm_cc_returns, sharpe_of

CLEAN_START = pd.Timestamp("2008-05-30")
EXT_START = pd.Timestamp("1999-03-10")
EVAL_END = pd.Timestamp("2026-05-22")


def slice_attr(ret, dsr, cash, lo, hi):
    """Day-since-rebalance attribution on the date slice [lo, hi].

    Returns day-1 bp, rest-of-month bp, multiple, day-1 standalone Sharpe,
    day-1 share of arithmetic P&L, plus full Sharpe of the slice and the
    'exclude day-1' counterfactual Sharpe (the TOM contribution to Sharpe).
    """
    sel = (ret.index >= lo) & (ret.index <= hi)
    r = ret[sel]
    d = dsr[sel]
    valid = d.notna()
    rv = r[valid]
    dv = d[valid].astype(int)

    day1 = rv[dv == 1]
    rest = rv[dv > 1]
    total = float(rv.sum())

    full_sharpe = sharpe_of(r, cash)            # full slice (incl flat/cash days)
    excl1_sharpe = sharpe_of(r[~((d == 1))], cash)  # drop day-1 rows, keep rest+flat

    return {
        "window": f"{lo.date()}..{hi.date()}",
        "n_days_total": int(sel.sum()),
        "n_day1": int(len(day1)),
        "n_rest": int(len(rest)),
        "day1_bp": float(day1.mean() * 1e4) if len(day1) else None,
        "rest_bp": float(rest.mean() * 1e4) if len(rest) else None,
        "multiple_day1_over_rest": (float(day1.mean() / rest.mean())
                                    if len(day1) and len(rest) and rest.mean() != 0 else None),
        "day1_standalone_sharpe": sharpe_of(day1, cash),
        "rest_standalone_sharpe": sharpe_of(rest, cash),
        "day1_share_of_arith_pnl": float(day1.sum() / total) if total != 0 else None,
        "day1_arith_sum": float(day1.sum()),
        "total_arith_sum": total,
        "full_sharpe": full_sharpe,
        "sharpe_excl_day1": excl1_sharpe,
        "sharpe_drop_from_day1": (float(full_sharpe - excl1_sharpe)
                                  if full_sharpe is not None and excl1_sharpe is not None else None),
    }


def main():
    panel = load_panel(start=EXT_START, end=EVAL_END)
    end = min(EVAL_END, panel.index[-1])
    cash_daily = panel["SHV"].ffill().pct_change().dropna()

    cols = sorted(set(RISKY_UNIVERSE + SAFE_POOL + CANARY_ASSETS + [DEFAULT_CASH]) & set(panel.columns))
    close = panel[cols]
    daily_ret = close.ffill().pct_change()

    # Returns + day-since-rebalance over full clean window (EOM config), ONCE.
    ret, dsr = cpm_cc_returns(close, daily_ret, CLEAN_START, end, ("eom", 0))

    results = {"meta": {
        "panel_start": str(panel.index[0].date()),
        "panel_end": str(panel.index[-1].date()),
        "clean_start": str(CLEAN_START.date()),
        "eval_end": str(end.date()),
        "cost_bps_per_side": COST_BPS_PER_SIDE,
        "config": "eom (eom,0), close-to-close, exec_lag=0",
        "anchor_full_clean_sharpe": sharpe_of(ret, cash_daily),
        "note": "returns+dsr computed once on full clean window; subperiods are date slices",
    }}

    # ---- PART 1: TEMPORAL DECAY by subperiod ----
    subperiods = [
        ("2008-12", pd.Timestamp("2008-05-30"), pd.Timestamp("2012-12-31")),
        ("2013-17", pd.Timestamp("2013-01-01"), pd.Timestamp("2017-12-31")),
        ("2018-22", pd.Timestamp("2018-01-01"), pd.Timestamp("2022-12-31")),
        ("2023-26", pd.Timestamp("2023-01-01"), end),
    ]
    part1 = {}
    for name, lo, hi in subperiods:
        part1[name] = slice_attr(ret, dsr, cash_daily, lo, hi)
    results["part1_subperiod_decay"] = part1

    # ---- PART 2: ALREADY-DISCOUNTED halves (2008-16 vs 2017-26) ----
    halves = [
        ("2008-16", pd.Timestamp("2008-05-30"), pd.Timestamp("2016-12-31")),
        ("2017-26", pd.Timestamp("2017-01-01"), end),
    ]
    part2 = {}
    for name, lo, hi in halves:
        part2[name] = slice_attr(ret, dsr, cash_daily, lo, hi)
    results["part2_halves_already_discounted"] = part2

    # ---- PART 3: rolling 5y day-1 bp + standalone Sharpe (decay curve) ----
    valid = dsr.notna()
    rv_all = ret[valid]
    dv_all = dsr[valid].astype(int)
    day1_series = rv_all[dv_all == 1]
    roll = {}
    # year-anchored rolling 5y windows
    for y0 in range(2008, 2023):
        lo = pd.Timestamp(f"{y0}-01-01")
        hi = pd.Timestamp(f"{y0+4}-12-31")
        seg = day1_series[(day1_series.index >= lo) & (day1_series.index <= hi)]
        if len(seg) >= 12:
            roll[f"{y0}-{y0+4}"] = {
                "day1_bp": float(seg.mean() * 1e4),
                "day1_standalone_sharpe": sharpe_of(seg, cash_daily),
                "n_day1": int(len(seg)),
            }
    results["part3_rolling5y_day1"] = roll

    print(json.dumps(results, indent=2, default=lambda x: None if x is None else float(x)))
    out = ROOT / "research" / "cpm_tom_decay_findings.json"
    with open(out, "w") as f:
        json.dump(results, f, indent=2, default=lambda x: None if x is None else float(x))
    print(f"\nSaved {out}")


if __name__ == "__main__":
    main()
