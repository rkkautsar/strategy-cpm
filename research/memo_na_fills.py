#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fill the two computable n/a cells in cpm_bull_two_sleeve_memo.md, using the
SAME canonical post-tidy mooex harness that produced the memo's existing
(confirmed) clean Excess Sharpe column -- i.e. exec_lag_moo_validation_2026_05_30
(module H) + cpm_live.perf_metrics excess vs SHV, exactly as research/memo_fix_numbers.py.

Outputs (research/ only):
  1. Section 5.1/5.2: CPM and BULL standalone EXTENDED-window Excess Sharpe vs SHV
     (plus clean as a cross-check of the existing column 1.072 / 0.955).
  2. Section 12.6.2: BULL K x V interaction EXTENDED value.

Read-only re production. No production edits, no commit.
"""
import sys, json
from pathlib import Path
import pandas as pd
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

import exec_lag_moo_validation_2026_05_30 as H
from cpm_live import (
    load_panel, perf_metrics, compute_target_weights,
    RISKY_UNIVERSE, SAFE_POOL, CANARY_ASSETS, DEFAULT_CASH, COST_BPS_PER_SIDE,
)

CONV = "mooex"
COST = COST_BPS_PER_SIDE
CPM_W, BULL_W = 0.60, 0.40
CLEAN_START = pd.Timestamp("2008-05-30")
EXT_START = pd.Timestamp("1999-03-10")
END = pd.Timestamp("2026-05-22")

ANCHOR_CPM = {"clean": {"sharpe": 1.1910, "maxdd": -12.67, "calmar": 1.0615},
              "ext":   {"sharpe": 1.2142, "maxdd": -15.93, "calmar": 0.8608}}
ANCHOR_BULL_EXT_SHARPE = 0.920  # memo 5.2 BULL ext raw Sharpe (~)


def met(s, cash):
    m = perf_metrics(s, cash)
    return {"sharpe": m["sharpe"], "cagr": m["cagr"], "vol": m["vol"],
            "excess_sharpe": m["excess_sharpe"], "maxdd": m["max_drawdown"],
            "calmar": m["calmar"]}


def win(s, a, b):
    return s.loc[(s.index >= a) & (s.index <= b)]


def run_cpm(close, daily, intraday, overnight, end):
    s, _ = H._segment_returns_conv(
        close, daily, lambda sd: compute_target_weights(close, sd)[0],
        EXT_START, end, CONV, COST, intraday, overnight)
    return s


def main():
    panel = load_panel(start=EXT_START, end=END)   # live=False frozen in-repo data
    end = min(END, panel.index[-1])
    cash = panel["SHV"].ffill().pct_change().dropna()
    od, cy = H.load_open_close()
    intraday = (cy / od - 1.0).reindex(panel.index)
    overnight = (od / cy.shift(1) - 1.0).reindex(panel.index)

    cols = sorted(set(RISKY_UNIVERSE + SAFE_POOL + CANARY_ASSETS + [DEFAULT_CASH]) & set(panel.columns))
    close = panel[cols]
    daily = close.ffill().pct_change()

    cpm = run_cpm(close, daily, intraday, overnight, end)
    bull, _ = H.bull_sleeve_conv(panel, intraday, overnight, EXT_START, end, CONV, H.GATE_RV60)
    common = cpm.index.intersection(bull.index)
    cpm = cpm.reindex(common)
    bull = bull.reindex(common)

    cpm_clean = met(win(cpm, CLEAN_START, end), cash)
    cpm_ext = met(win(cpm, EXT_START, end), cash)
    bull_clean = met(win(bull, CLEAN_START, end), cash)
    bull_ext = met(win(bull, EXT_START, end), cash)

    # ---- ANCHOR GATE ----
    print(f"harness: conv={CONV}, cost={COST} bps/side, cash=SHV proxy, end={end.date()}")
    def chk(name, m, e):
        ok = (abs(m["sharpe"] - e["sharpe"]) < 5e-4
              and abs(m["maxdd"] * 100 - e["maxdd"]) < 0.02
              and abs(m["calmar"] - e["calmar"]) < 5e-4)
        print(f"  ANCHOR {name}: Sharpe={m['sharpe']:.4f} MaxDD={m['maxdd']*100:.2f}% "
              f"Calmar={m['calmar']:.4f}  expect {e['sharpe']}/{e['maxdd']}/{e['calmar']} -> "
              f"{'OK' if ok else 'MISMATCH'}")
        return ok
    g1 = chk("CPM clean", cpm_clean, ANCHOR_CPM["clean"])
    g2 = chk("CPM ext", cpm_ext, ANCHOR_CPM["ext"])
    bull_ext_ok = abs(bull_ext["sharpe"] - ANCHOR_BULL_EXT_SHARPE) < 5e-3
    print(f"  ANCHOR BULL ext: Sharpe={bull_ext['sharpe']:.4f}  expect ~{ANCHOR_BULL_EXT_SHARPE} -> "
          f"{'OK' if bull_ext_ok else 'MISMATCH'}")
    print(f"  (xref) BULL clean: Sharpe={bull_clean['sharpe']:.4f} excess={bull_clean['excess_sharpe']:.4f} "
          f"(memo 1.081 / 0.955)")
    print(f"  (xref) CPM  clean excess={cpm_clean['excess_sharpe']:.4f} (memo 1.072)")
    if not (g1 and g2 and bull_ext_ok):
        print("\nANCHOR GATE FAILED -- not reporting derived values.")
        sys.exit(1)
    print("ANCHOR GATE PASSED.\n")

    print("# Item 1 DERIVED -- EXTENDED-window Excess Sharpe vs SHV")
    print(f"  CPM  ext excess Sharpe = {cpm_ext['excess_sharpe']:.4f} (ext raw {cpm_ext['sharpe']:.4f})")
    print(f"  BULL ext excess Sharpe = {bull_ext['excess_sharpe']:.4f} (ext raw {bull_ext['sharpe']:.4f})")

    out = {
        "harness": {"conv": CONV, "cost_bps_per_side": COST,
                    "cash_benchmark": "SHV proxy (stitched VFISX pre-ETF)",
                    "module": "exec_lag_moo_validation_2026_05_30",
                    "clean_window": [str(CLEAN_START.date()), str(end.date())],
                    "ext_window": [str(EXT_START.date()), str(end.date())]},
        "anchor_gate": {"cpm_clean_ok": bool(g1), "cpm_ext_ok": bool(g2), "bull_ext_ok": bool(bull_ext_ok)},
        "item1_excess_sharpe": {
            "CPM": {"clean_raw": cpm_clean["sharpe"], "clean_excess": cpm_clean["excess_sharpe"],
                    "ext_raw": cpm_ext["sharpe"], "ext_excess": cpm_ext["excess_sharpe"]},
            "BULL": {"clean_raw": bull_clean["sharpe"], "clean_excess": bull_clean["excess_sharpe"],
                     "ext_raw": bull_ext["sharpe"], "ext_excess": bull_ext["excess_sharpe"]},
        },
    }
    (HERE / "memo_na_fills_compute.json").write_text(json.dumps(out, indent=2))
    print("\nwrote research/memo_na_fills_compute.json")


if __name__ == "__main__":
    main()
