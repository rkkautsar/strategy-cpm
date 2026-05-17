"""Universe pruning v2: drop low-liquidity / short-history names.

Concerns:
  - XRT and XMMO: 0% picked in 18y (zombie assets)
  - COWZ: 2016-12 inception, uses SPY proxy for 8y in 'live-18y' window
  - SPMO: 2015-10 inception, uses SPY proxy for 7y in 'live-18y' window
  - XLE / VBR / VEA: low pick % but liquid

Test variants:
  FCP-15 (current): full
  FCP-13a (no XRT, XMMO): drop zombies, all live-2008+
  FCP-13b (no COWZ, SPMO): drop proxy-heavy
  FCP-11 (no XRT, XMMO, COWZ, SPMO): drop both
  FCP-9 (also no XLE, VBR): aggressive prune
  FCP-7 (only top-picked: QQQ, IGM, SPHQ, XMHQ, XLV, GLD, TLT, VWO, VEA): defensive prune

For each, also report: earliest fully-live date.
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import fcp_live as fcp
from fcp_live import load_panel, run_fcp_backtest, perf_metrics


# Inception dates (live ETF launch)
INCEPTIONS = {
    "QQQ": "1999-03-10", "IGM": "2001-03-13", "SPMO": "2015-10-09",
    "XLE": "1998-12-22", "XRT": "2006-06-22", "COWZ": "2016-12-19",
    "VBR": "2004-01-30", "SPHQ": "2005-12-09", "XMMO": "2005-03-10",
    "XMHQ": "2005-12-09", "XLV": "1998-12-22", "VEA": "2007-07-20",
    "VWO": "2005-03-04", "GLD": "2004-11-18", "TLT": "2002-07-22",
    # Longer-history factor alternatives
    "PDP": "2007-03-01", "MTUM": "2013-04-18", "DLN": "2006-06-16",
    "VYM": "2006-11-16", "VTV": "2004-01-30", "IWD": "2000-05-26",
    "IWF": "2000-05-26", "RSP": "2003-05-01",
    # Schwab broad factors (popular, low-cost)
    "SCHG": "2009-12-11", "SCHD": "2011-10-20",
}

FCP11_BASE = ["QQQ","IGM","XLE","VBR","SPHQ","XMHQ","XLV","VEA","VWO","GLD","TLT"]

FCP11_BASE = ["QQQ","IGM","XLE","VBR","SPHQ","XMHQ","XLV","VEA","VWO","GLD","TLT"]

VARIANTS = [
    ("FCP-15 (current)", ["QQQ","IGM","SPMO","XLE","XRT","COWZ","VBR","SPHQ",
                          "XMMO","XMHQ","XLV","VEA","VWO","GLD","TLT"]),
    ("FCP-11 baseline", FCP11_BASE),
    # Schwab simple growth+value adds
    ("FCP-12 +SCHG", FCP11_BASE + ["SCHG"]),
    ("FCP-12 +SCHD", FCP11_BASE + ["SCHD"]),
    ("FCP-13 +SCHG +SCHD", FCP11_BASE + ["SCHG", "SCHD"]),
    # Simplified universe: keep only essentials, drop redundant factors
    ("FCP-simple9 SCHG+SCHD core",
     ["QQQ", "SCHG", "SCHD", "XLV", "VEA", "VWO", "GLD", "TLT", "SPHQ"]),
    ("FCP-simple7 ultra-clean",
     ["SCHG", "SCHD", "XLV", "VEA", "VWO", "GLD", "TLT"]),
    # Long-history factor replacements
    ("FCP-12 +PDP (DWA mom 2007)", FCP11_BASE + ["PDP"]),
    ("FCP-13 +PDP +DLN", FCP11_BASE + ["PDP", "DLN"]),
    ("FCP-13 +MTUM +DLN", FCP11_BASE + ["MTUM", "DLN"]),
    ("FCP-13 +PDP +SCHD", FCP11_BASE + ["PDP", "SCHD"]),
    ("FCP-14 +SCHG +SCHD +PDP", FCP11_BASE + ["SCHG", "SCHD", "PDP"]),
]


def run_variant(panel, start, end, universe):
    orig = fcp.RISKY_UNIVERSE
    fcp.RISKY_UNIVERSE = universe
    try:
        rets, _ = run_fcp_backtest(panel, start, end)
        m = perf_metrics(rets)
    finally:
        fcp.RISKY_UNIVERSE = orig
    return m


def earliest_all_live(universe):
    incept_dates = [pd.Timestamp(INCEPTIONS[u]) for u in universe if u in INCEPTIONS]
    return max(incept_dates).date()


def main():
    out = Path(__file__).parent / "universe_prune_v2.log"
    log_lines = []
    def log(s=""): log_lines.append(s); print(s)

    log("=" * 110)
    log("UNIVERSE PRUNING SWEEP")
    log("Test: drop low-liquidity / short-history names to get cleaner live-only window")
    log("=" * 110)

    panel = load_panel(start=pd.Timestamp("1999-01-01"))
    end = panel.index[-1]

    # Live-only 18y window
    start_live = pd.Timestamp("2008-09-30")
    # Full 28y window
    start_full = pd.Timestamp("1997-08-30")

    log("")
    log(f"  {'Variant':<35s}  Earliest    LIVE-18y                    FULL-28y")
    log(f"  {'':<35s}  all-live    Sh    CAGR     DD              Sh    CAGR     DD")
    log("  " + "-" * 105)

    for label, universe in VARIANTS:
        all_live = earliest_all_live(universe)
        m_live = run_variant(panel, start_live, end, universe)
        m_full = run_variant(panel, start_full, end, universe)
        log(f"  {label:<35s}  {str(all_live):<10s}  "
            f"{m_live['sharpe']:+.3f}  {m_live['cagr']*100:+5.2f}%  "
            f"{m_live['max_drawdown']*100:+6.2f}%      "
            f"{m_full['sharpe']:+.3f}  {m_full['cagr']*100:+5.2f}%  "
            f"{m_full['max_drawdown']*100:+6.2f}%")

    # Now run TRULY all-live window for each variant (start from earliest-all-live + 1y warmup)
    log("")
    log("=" * 110)
    log("TRULY ALL-LIVE WINDOW per variant (start = max inception + 12mo warmup)")
    log("=" * 110)
    log("")
    log(f"  {'Variant':<35s}  Window               Years  Sh      CAGR     DD")
    log("  " + "-" * 90)
    for label, universe in VARIANTS:
        all_live = earliest_all_live(universe)
        clean_start = pd.Timestamp(all_live) + pd.DateOffset(years=1)
        if clean_start >= end:
            log(f"  {label:<35s}  TOO SHORT")
            continue
        m = run_variant(panel, clean_start, end, universe)
        years = (end - clean_start).days / 365.25
        log(f"  {label:<35s}  {clean_start.date()} -> {end.date()}  {years:4.1f}y  "
            f"{m['sharpe']:+.3f}  {m['cagr']*100:+5.2f}%  {m['max_drawdown']*100:+6.2f}%")

    log("")
    log("=" * 110)
    with open(out, "w") as f: f.write("\n".join(log_lines))
    print(f"\nLog: {out}")


if __name__ == "__main__":
    main()
