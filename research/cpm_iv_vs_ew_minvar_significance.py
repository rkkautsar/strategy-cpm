"""IV-vs-EW SIZING significance on the min-var 3-of-4 trio (single focused test).

Question: does inverse-vol (IV) weighting add SIGNIFICANT value over equal-weight
(EW) when SELECTION is min-var (ewobj) 3-of-4, on PATH-INDEPENDENT downside
metrics (Sharpe / Sortino / CVaR)? Prior work bootstrapped Sharpe only
(within-noise, p~0.71); Sortino + CVaR were never bootstrapped for this contrast.

Two cells (identical ewobj min-var selection; differ ONLY in sizing):
  MINVAR_IV    = ewobj selection + INVERSE-VOL sizing  (CURRENT PROD)
  COHERENT_EW  = ewobj selection + EQUAL-WEIGHT sizing

Contrast direction: d = IV - EW (ra=IV, rb=EW). On Sharpe IV is LOWER so expect
dSharpe<0; question is whether Sortino/CVaR CI excludes 0 in IV's favor.

Read-only re production. Writes only research/ findings. No commit.

Run: .venv/bin/python -m research.cpm_iv_vs_ew_minvar_significance
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from research import cpm_harness as H
from research.cpm_minvar_coherence import make_weight_fn
from research.cpm_bootstrap_multimetric import paired_block_bootstrap_mm

OUT_JSON = Path(__file__).resolve().parent / "cpm_iv_vs_ew_minvar_significance.json"


def main():
    data = H.load_data()
    anchor = H.verify_anchor(data=data)
    print("ANCHOR OK:", {k: round(float(v), 4) for k, v in anchor.items()
                         if k in ("Sharpe", "MaxDD", "Calmar")})

    wf_iv = make_weight_fn("minvar_ewobj", "invvol")   # MINVAR_IV (prod)
    wf_ew = make_weight_fn("minvar_ewobj", "ew")        # COHERENT_EW

    cells = {}
    streams = {}
    for key, wf in (("MINVAR_IV", wf_iv), ("COHERENT_EW", wf_ew)):
        streams[key] = {}
        cells[key] = {}
        for win in ("clean", "ext"):
            r = H.run_strategy(wf, window=win, data=data)
            streams[key][win] = r
            cells[key][win] = H.metrics(r, data=data)
        print(f"{key}: clean Sharpe {cells[key]['clean']['Sharpe']:.4f} "
              f"Calmar {cells[key]['clean']['Calmar']:.4f} "
              f"MaxDD {cells[key]['clean']['MaxDD']:.4f} | "
              f"ext Sharpe {cells[key]['ext']['Sharpe']:.4f}")

    cash = data.cash
    iv_clean = streams["MINVAR_IV"]["clean"]
    ew_clean = streams["COHERENT_EW"]["clean"]

    # SIZING contrast d = IV - EW on DECISION (clean) window
    boot = {}
    for block in (21, 42):
        boot[f"block{block}"] = paired_block_bootstrap_mm(
            iv_clean, ew_clean, cash, B=2000, block=block, seed=42)
        b = boot[f"block{block}"]
        print(f"\n-- block={block} (d = IV - EW, clean) --")
        for m in ("dSharpe", "dSortino", "dCVaR"):
            s = b[m]
            print(f"  {m}: mean {s['mean']:+.4f} CI [{s['ci_lo']:+.4f}, {s['ci_hi']:+.4f}] "
                  f"p(>0)={s['p_gt0']:.3f}")

    results = {
        "anchor": {k: float(v) for k, v in anchor.items()},
        "cells": cells,
        "bootstrap_iv_minus_ew_clean": boot,
    }
    with open(OUT_JSON, "w") as f:
        json.dump(results, f, indent=2, default=lambda o: None)
    print("\nwrote", OUT_JSON)
    return results


if __name__ == "__main__":
    main()
