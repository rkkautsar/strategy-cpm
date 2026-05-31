"""Throwaway research harness: CPM universe-substitution robustness.

Role: analyst (read-only re production; NO production/memo edits; NO commit).

Holds the FULL CPM pipeline fixed (vol-adj Faber rank, positive screen, top-4,
inverse-vol, strict-4 partial-safe, HYG-OR-TIP canary, SHV/IEF safe, cov 504d,
10 bps/side, monthly month-end signal, mooex T+1 MOO exact) and only swaps the
risky universe. Reuses the validated mooex builder from
exec_lag_moo_validation_2026_05_30 (V.cpm_sleeve_conv).

Universe is injected by monkeypatching cpm_live.RISKY_UNIVERSE and the name
V.RISKY_UNIVERSE (both used: the former by compute_target_weights default, the
latter by V.cpm_sleeve_conv's column filter). TOP_K stays 4 (production pipeline).
"""
import sys
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import cpm_live
from cpm_live import load_panel, perf_metrics
import exec_lag_moo_validation_2026_05_30 as V

CLEAN_START = pd.Timestamp("2008-05-30")
EXT_START = pd.Timestamp("1999-03-10")

PROD = ["QQQ", "SPHQ", "EFA", "EEM", "VNQ", "GLD", "TLT", "DBC"]

UNIVERSES = {
    "PROD_8 (QQQ,SPHQ,EFA,EEM,VNQ,GLD,TLT,DBC)": PROD,
    "SPYswap_7 (SPY,EFA,EEM,VNQ,GLD,TLT,DBC)": ["SPY", "EFA", "EEM", "VNQ", "GLD", "TLT", "DBC"],
    "AAA_8 (SPY,EFA,EEM,VNQ,IEF,TLT,DBC,GLD)": ["SPY", "EFA", "EEM", "VNQ", "IEF", "TLT", "DBC", "GLD"],
    "FaberGTAA5 (SPY,EFA,IEF,VNQ,DBC)": ["SPY", "EFA", "IEF", "VNQ", "DBC"],
    "KellerGTAA10 (SPY,EFA,EEM,IEF,GLD,DBC,VNQ,TLT,LQD,HYG)":
        ["SPY", "EFA", "EEM", "IEF", "GLD", "DBC", "VNQ", "TLT", "LQD", "HYG"],
}


def run_universe(uni, panel, intraday, overnight, end, cash_daily):
    # Patch both global references the pipeline reads.
    cpm_live.RISKY_UNIVERSE = list(uni)
    V.RISKY_UNIVERSE = list(uni)
    cpm_full, fb = V.cpm_sleeve_conv(panel, intraday, overnight, EXT_START, end, "mooex")
    clean = cpm_full.loc[(cpm_full.index >= CLEAN_START) & (cpm_full.index <= end)]
    ext = cpm_full.loc[(cpm_full.index >= EXT_START) & (cpm_full.index <= end)]
    mc = perf_metrics(clean, cash_daily)
    me = perf_metrics(ext, cash_daily)
    return mc, me, fb


def main():
    end = pd.Timestamp("2026-05-30")
    # Need LQD/HYG/SPY/IEF in panel: all present in proxy_adjusted_close_daily.csv.
    panel = load_panel(start=EXT_START, end=end)
    end = min(end, panel.index[-1])
    cash_daily = panel["SHV"].ffill().pct_change().dropna()

    open_df, close_yf = V.load_open_close()
    intraday = (close_yf / open_df - 1.0).reindex(panel.index)
    overnight = (open_df / close_yf.shift(1) - 1.0).reindex(panel.index)

    missing_ohlc = {}
    for name, uni in UNIVERSES.items():
        miss = [t for t in uni if t not in open_df.columns]
        if miss:
            missing_ohlc[name] = miss

    rows = []
    results = {}
    for name, uni in UNIVERSES.items():
        present = [t for t in uni if t in panel.columns]
        absent = [t for t in uni if t not in panel.columns]
        mc, me, fb = run_universe(uni, panel, intraday, overnight, end, cash_daily)
        results[name] = {
            "universe": uni,
            "panel_absent": absent,
            "ohlc_missing_mooex_fallback": [t for t in uni if t not in open_df.columns],
            "mooex_coverage_real_fallback": list(fb),
            "clean": {k: mc.get(k) for k in ["sharpe", "cagr", "vol", "max_drawdown", "calmar", "excess_sharpe"]},
            "ext": {k: me.get(k) for k in ["sharpe", "cagr", "vol", "max_drawdown", "calmar", "excess_sharpe"]},
        }
        rows.append((name, mc, me))
        print(f"\n=== {name} ===")
        print(f"  panel_absent={absent}  ohlc_missing(fallback)={[t for t in uni if t not in open_df.columns]}  "
              f"mooex real/fallback={fb}")
        print(f"  CLEAN: Sharpe={mc['sharpe']:.4f} CAGR={mc['cagr']*100:.2f}% Vol={mc['vol']*100:.2f}% "
              f"MaxDD={mc['max_drawdown']*100:.2f}% Calmar={mc['calmar']:.4f}")
        print(f"  EXT:   Sharpe={me['sharpe']:.4f} CAGR={me['cagr']*100:.2f}% Vol={me['vol']*100:.2f}% "
              f"MaxDD={me['max_drawdown']*100:.2f}% Calmar={me['calmar']:.4f}")

    # Anchor gate on PROD.
    p = results[list(UNIVERSES.keys())[0]]["clean"]
    anchor_ok = (abs(p["sharpe"] - 1.1910) < 0.0015 and
                 abs(p["max_drawdown"] * 100 + 12.67) < 0.06 and
                 abs(p["calmar"] - 1.0615) < 0.006)
    print(f"\nANCHOR (PROD clean) match 1.1910/-12.67%/1.0615: {anchor_ok}")

    out = {
        "convention": "mooex T+1 MOO exact, 10 bps/side, monthly month-end signal; full CPM pipeline held fixed (top-4, vol-Faber, positive screen, inverse-vol, strict-4 partial-safe, HYG-OR-TIP canary, SHV/IEF safe, cov 504d)",
        "windows": {"clean": ["2008-05-30", str(end.date())], "ext": ["1999-03-10", str(end.date())]},
        "anchor_prod_clean_ok": bool(anchor_ok),
        "results": results,
    }
    out_path = Path(__file__).resolve().parent / "cpm_robust_universe.json"
    out_path.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
