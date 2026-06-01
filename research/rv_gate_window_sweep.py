# -*- coding: utf-8 -*-
"""Throwaway research (analyst role; read-only re production; NO production files
changed; NO commit). Sensitivity sweep of the BULL sleeve realized-volatility
gate SHORT window.

Production BULL vol gate (bull_spy_live._vol_gate_ok / compute_bull_spy_weights):
    gate ON  <=>  rv_60d(SPY) < rv_252d(SPY)
The 60-day SHORT window is a tuned parameter with no in-memo sensitivity sweep.
This script sweeps SHORT in {20, 40, 60, 80, 120} against the SAME 252d long
window, holding everything else at production, and reports BULL-sleeve metrics
plus the 60/40 CPM-BULL blend.

Execution / metric conventions (identical to the IV4 final-number set, anchor-gated):
  - CPM & BULL: T+1 MOO exact ("mooex", real yfinance auto_adjust opens),
    post-cost 10 bps/side. CPM is fixed (production IV4); only the BULL gate
    SHORT window varies. Long window held at 252d throughout.
  - Metrics from production perf_metrics: Sharpe (rf=0), Calmar (=CAGR/|MaxDD|),
    MaxDD, CAGR, Vol.
  - Windows: clean 2008-05-30..2026-05-22 (18y), stress/ext 1999-03-10..2026-05-22.

ANCHOR GATE (abort on mismatch):
  60d BULL clean Sharpe ~1.081 (memo section 5.1).
  60/40 CPM-BULL blend clean Sharpe ~1.2485 (memo section 8.10 anchor).

Reuses production engine via research/exec_lag_moo_validation_2026_05_30.py helpers
(cpm_sleeve_conv, bull_sleeve_conv, gate_rv factory). The gate factory monkeypatches
bull_spy_live._vol_gate_ok inside bull_sleeve_conv and restores it after.

Writes research/rv_gate_window_sweep_findings.md (+ .json).
"""
from __future__ import annotations
import sys, json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import exec_lag_moo_validation_2026_05_30 as H
from cpm_live import load_panel, perf_metrics, COST_BPS_PER_SIDE

CONV = "mooex"
CLEAN_START = pd.Timestamp("2008-05-30")
EXT_START = pd.Timestamp("1999-03-10")   # "stress" window in the memo
END = pd.Timestamp("2026-05-22")

CPM_W, BULL_W = 0.60, 0.40                # 60/40 CPM-BULL two-sleeve blend
LONG_WINDOW = 252                         # held fixed
SHORT_WINDOWS = [20, 40, 60, 80, 120]     # 20 = cheap reference point
PROD_SHORT = 60

ANCHOR_BULL60_SHARPE = 1.081              # memo section 5.1
ANCHOR_BLEND_SHARPE = 1.2485             # memo section 8.10 (60/40)
ANCHOR_TOL = 0.01                          # tolerance band on anchor reproduction


def met(s, cash):
    m = perf_metrics(s, cash)
    return {"sharpe": m.get("sharpe"), "cagr": m.get("cagr"), "vol": m.get("vol"),
            "maxdd": m.get("max_drawdown"), "calmar": m.get("calmar")}


def win(s, start, end):
    return s.loc[(s.index >= start) & (s.index <= end)]


def main():
    panel = load_panel(start=EXT_START, end=END)
    end = min(END, panel.index[-1])
    cash = panel["SHV"].ffill().pct_change().dropna()
    od, cy = H.load_open_close()
    intraday = (cy / od - 1.0).reindex(panel.index)
    overnight = (od / cy.shift(1) - 1.0).reindex(panel.index)

    # ---- CPM sleeve (fixed production IV4, mooex) ----
    cpm, _ = H.cpm_sleeve_conv(panel, intraday, overnight, EXT_START, end, CONV)

    # ---- BULL sleeve per SHORT window ----
    bull_series = {}
    for sw in SHORT_WINDOWS:
        gate = H.gate_rv(sw, slow=LONG_WINDOW)
        bull, _ = H.bull_sleeve_conv(panel, intraday, overnight, EXT_START, end, CONV, gate)
        bull_series[sw] = bull

    common = cpm.index
    for sw in SHORT_WINDOWS:
        common = common.intersection(bull_series[sw].index)
    cpm = cpm.reindex(common)
    for sw in SHORT_WINDOWS:
        bull_series[sw] = bull_series[sw].reindex(common)

    # ---- Anchor gate (abort on mismatch) ----
    bull60_clean = met(win(bull_series[PROD_SHORT], CLEAN_START, end), cash)
    blend60 = CPM_W * cpm + BULL_W * bull_series[PROD_SHORT]
    blend60_clean = met(win(blend60, CLEAN_START, end), cash)
    print("=== ANCHOR GATE ===")
    print(f"60d BULL clean Sharpe   = {bull60_clean['sharpe']:.4f}  (expect ~{ANCHOR_BULL60_SHARPE})")
    print(f"60/40 blend clean Sharpe = {blend60_clean['sharpe']:.4f}  (expect ~{ANCHOR_BLEND_SHARPE})")
    ok_bull = abs(bull60_clean["sharpe"] - ANCHOR_BULL60_SHARPE) < ANCHOR_TOL
    ok_blend = abs(blend60_clean["sharpe"] - ANCHOR_BLEND_SHARPE) < ANCHOR_TOL
    if not (ok_bull and ok_blend):
        print(f"ANCHOR MISMATCH: ok_bull={ok_bull} ok_blend={ok_blend} -- ABORT")
        sys.exit(1)
    print("Anchor reproduced. Proceeding.\n")

    # ---- Sweep results ----
    rows = []
    for sw in SHORT_WINDOWS:
        b = bull_series[sw]
        blend = CPM_W * cpm + BULL_W * b
        bc = met(win(b, CLEAN_START, end), cash)
        bs = met(win(b, EXT_START, end), cash)
        kc = met(win(blend, CLEAN_START, end), cash)
        rows.append({
            "short_window": sw, "long_window": LONG_WINDOW, "is_prod": sw == PROD_SHORT,
            "bull_clean": bc, "bull_stress": bs, "blend_clean": kc,
        })

    # ---- bands ----
    bull_clean_sharpes = [r["bull_clean"]["sharpe"] for r in rows]
    bull_stress_sharpes = [r["bull_stress"]["sharpe"] for r in rows]
    blend_clean_sharpes = [r["blend_clean"]["sharpe"] for r in rows]
    core = [r for r in rows if r["short_window"] != 20]  # core sweep {40,60,80,120}
    bull_clean_core = [r["bull_clean"]["sharpe"] for r in core]
    blend_clean_core = [r["blend_clean"]["sharpe"] for r in core]
    bands = {
        "bull_clean_sharpe_band_all": max(bull_clean_sharpes) - min(bull_clean_sharpes),
        "bull_clean_sharpe_band_core_40_120": max(bull_clean_core) - min(bull_clean_core),
        "bull_stress_sharpe_band_all": max(bull_stress_sharpes) - min(bull_stress_sharpes),
        "blend_clean_sharpe_band_all": max(blend_clean_sharpes) - min(blend_clean_sharpes),
        "blend_clean_sharpe_band_core_40_120": max(blend_clean_core) - min(blend_clean_core),
    }

    best_bull_clean = max(rows, key=lambda r: r["bull_clean"]["sharpe"])
    best_blend_clean = max(rows, key=lambda r: r["blend_clean"]["sharpe"])

    result = {
        "meta": {
            "convention": CONV, "cost_bps_per_side": COST_BPS_PER_SIDE,
            "clean_window": [str(CLEAN_START.date()), str(end.date())],
            "stress_window": [str(EXT_START.date()), str(end.date())],
            "long_window": LONG_WINDOW, "short_windows": SHORT_WINDOWS,
            "prod_short": PROD_SHORT, "blend": f"{int(CPM_W*100)}/{int(BULL_W*100)} CPM-BULL",
            "anchor": {"bull60_clean_sharpe": bull60_clean["sharpe"],
                       "blend60_clean_sharpe": blend60_clean["sharpe"]},
        },
        "rows": rows, "bands": bands,
        "best_bull_clean_window": best_bull_clean["short_window"],
        "best_blend_clean_window": best_blend_clean["short_window"],
    }

    out_json = Path(__file__).resolve().parent / "rv_gate_window_sweep_findings.json"
    out_json.write_text(json.dumps(result, indent=2))
    print(f"Wrote {out_json}")

    # ---- console table ----
    print("\n=== BULL sleeve (short-window sweep, long=252) ===")
    hdr = f"{'short':>6}{'CLEAN Sharpe':>14}{'Calmar':>9}{'MaxDD':>9}{'CAGR':>9}{'Vol':>8}{'  | STRESS Sharpe':>18}{'Calmar':>9}{'MaxDD':>9}"
    print(hdr)
    for r in rows:
        bc, bs = r["bull_clean"], r["bull_stress"]
        tag = " *" if r["is_prod"] else "  "
        print(f"{r['short_window']:>4}d{tag}{bc['sharpe']:>14.4f}{bc['calmar']:>9.3f}"
              f"{bc['maxdd']*100:>8.2f}%{bc['cagr']*100:>8.2f}%{bc['vol']*100:>7.2f}%"
              f"{bs['sharpe']:>18.4f}{bs['calmar']:>9.3f}{bs['maxdd']*100:>8.2f}%")

    print("\n=== 60/40 CPM-BULL blend (clean) per BULL short window ===")
    print(f"{'short':>6}{'Sharpe':>10}{'Calmar':>9}{'MaxDD':>9}{'CAGR':>9}{'Vol':>8}")
    for r in rows:
        kc = r["blend_clean"]
        tag = " *" if r["is_prod"] else "  "
        print(f"{r['short_window']:>4}d{tag}{kc['sharpe']:>10.4f}{kc['calmar']:>9.3f}"
              f"{kc['maxdd']*100:>8.2f}%{kc['cagr']*100:>8.2f}%{kc['vol']*100:>7.2f}%")

    print("\n=== Bands ===")
    for k, v in bands.items():
        print(f"  {k}: {v:.4f}")
    print(f"\nBest BULL clean Sharpe window: {best_bull_clean['short_window']}d "
          f"({best_bull_clean['bull_clean']['sharpe']:.4f})")
    print(f"Best blend clean Sharpe window: {best_blend_clean['short_window']}d "
          f"({best_blend_clean['blend_clean']['sharpe']:.4f})")

    return result


if __name__ == "__main__":
    main()
