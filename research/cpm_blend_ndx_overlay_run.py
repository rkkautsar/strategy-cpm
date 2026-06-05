# -*- coding: utf-8 -*-
"""Runner: full prod-blend NDX-overlay study. Writes JSON + prints decision
tables to stderr. See cpm_blend_ndx_overlay_harness for spec."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.cpm_blend_ndx_overlay_harness import run, CONFIGS


def fp(v, d=4):
    return f"{v:.{d}f}" if v is not None and v == v else "  --  "


def main():
    out = run()
    res = out["results"]
    keys = [k for k, _ in CONFIGS]

    print("\n=== BLEND-LEVEL RISK-ADJUSTED METRICS (CLEAN 2008-05-30+) ===",
          file=sys.stderr)
    hdr = f"{'cfg':6} {'Sharpe':>7} {'Sortino':>7} {'CVaR':>7} {'Calmar':>7} {'Martin':>7} {'MaxDD':>8} {'CAGR':>8} {'vol':>7} {'ndxTO':>7}"
    print(hdr, file=sys.stderr)
    for k in keys:
        m = res[k]["blend_clean"]
        print(f"{k:6} {fp(m['Sharpe'],3):>7} {fp(m['Sortino'],3):>7} "
              f"{fp(m['CVaR_ratio'],3):>7} {fp(m['Calmar'],3):>7} {fp(m['Martin'],3):>7} "
              f"{fp(m['MaxDD']):>8} {fp(m['CAGR']):>8} {fp(m['vol']):>7} "
              f"{fp(res[k]['ndx_turnover_ann'],2):>7}", file=sys.stderr)

    print("\n=== NDX SLEEVE STANDALONE (CLEAN) -- marginal contribution source ===",
          file=sys.stderr)
    print(f"{'cfg':6} {'CAGR':>8} {'MaxDD':>8} {'Calmar':>7} {'Sharpe':>7}", file=sys.stderr)
    for k in keys:
        m = res[k]["ndx_sleeve_clean"]
        print(f"{k:6} {fp(m['CAGR']):>8} {fp(m['MaxDD']):>8} "
              f"{fp(m['Calmar'],3):>7} {fp(m['Sharpe'],3):>7}", file=sys.stderr)

    print("\n=== PER-CRISIS BLEND MaxDD (EXT 1999+) ===", file=sys.stderr)
    crises = ["dotcom_2000_2002", "GFC_2007_2009", "COVID_2020", "Y2022", "Y2025"]
    print(f"{'cfg':6} " + " ".join(f"{c[:10]:>11}" for c in crises) +
          f" {'unwind21':>9} {'year21':>8}", file=sys.stderr)
    for k in keys:
        cr = res[k]["blend_crisis"]
        row = f"{k:6} "
        for c in crises:
            v = cr.get(c)
            row += f"{fp(v['MaxDD']) if v else '  --  ':>11} "
        u = res[k]["blend_unwind_2021"]
        y = res[k]["blend_year_2021"]
        row += f"{fp(u['MaxDD']) if u else '--':>9} {fp(y['MaxDD']) if y else '--':>8}"
        print(row, file=sys.stderr)

    print("\n=== NDX SLEEVE PER-CRISIS MaxDD (for dilution comparison) ===",
          file=sys.stderr)
    print(f"{'cfg':6} {'COVID':>9} {'Y2022':>9} {'unwind21':>9} {'year21':>9}",
          file=sys.stderr)
    for k in keys:
        cr = res[k]["ndx_sleeve_crisis"]
        u = res[k]["ndx_sleeve_unwind_2021"]
        y = res[k]["ndx_sleeve_year_2021"]
        cv = cr.get("COVID_2020")
        y22 = cr.get("Y2022")
        print(f"{k:6} {fp(cv['MaxDD']) if cv else '--':>9} "
              f"{fp(y22['MaxDD']) if y22 else '--':>9} "
              f"{fp(u['MaxDD']) if u else '--':>9} "
              f"{fp(y['MaxDD']) if y else '--':>9}", file=sys.stderr)

    op = ROOT / "research" / "cpm_blend_ndx_overlay_findings.json"
    op.write_text(json.dumps(out, indent=2, default=float))
    print("\nWROTE", op, file=sys.stderr)
    return out


if __name__ == "__main__":
    main()
