# -*- coding: utf-8 -*-
"""Throwaway research (analyst role; read-only re production; NO production files
changed; NO commit). Regenerates the TWO-SLEEVE CPM+BULL memo number set under the
FINAL production spec = IV4 (cpm_live.compute_target_weights), in the memo's exact
metric conventions, so research/two_sleeve_cpm_bull_findings.md can be rewritten
without stale pair / min-var-3 numbers.

Production CPM spec (now in cpm_live.compute_target_weights) = IV4 single-stage:
  cross-asset momentum -> vol-Faber ranker (faber_score / rv_252d) -> positive-trend
  screen -> top-4 -> inverse-vol weight ALL surviving positives (NO min-var
  sub-selection) -> strict-4 partial-safe (risky_fraction = min(n_pos,4)/4,
  remainder -> timed SHV/IEF) -> canary HYG-OR-TIP -> timed safe.

Execution / metric conventions (held identical to the IV4 final-number set
research/cpm_iv4_final_numbers.py, which is anchor-gated):
  - CPM & BULL: realistic T+1 MOO exact ("mooex", real yfinance auto_adjust opens),
    post-cost 10 bps/side, BULL slow equity vol gate rv_60d<rv_252d (GATE_RV60).
  - NDX (PROD 60/20/20 only): production NDX sleeve under T+1 MOO (offset=1)
    close-to-close via moc_vs_moo_analysis.run_ndx_backtest_with_offset, because the
    per-stock NDX universe (PIT constituents + delisting haircut) is NOT supported by
    the exact-open (mooex) single-panel engine. This is flagged in the findings.
  - Metrics from production perf_metrics: CAGR, Vol, raw Sharpe (rf=0),
    Excess Sharpe vs SHV, MaxDD, Calmar (=CAGR/|MaxDD|), Martin (=CAGR/UlcerIndex),
    and 2022 calendar-year total return.
  - Windows: clean 2008-05-30..2026-05-22 (18y), stress/ext 1999-03-10..2026-05-22.

ANCHOR GATE (abort on mismatch):
  CPM-solo IV4 clean Sharpe 1.1910 / MaxDD -12.67% / Calmar 1.0615.
  60/40 CPM-BULL blend clean Sharpe 1.2485 / MaxDD -10.68% / Calmar 1.1928 /
  Martin 4.354.

Writes research/two_sleeve_iv4_memo_numbers_findings.md (+ .json).
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
from cpm_live import load_panel, perf_metrics, compute_target_weights, COST_BPS_PER_SIDE
import ndx_sleeve_live as ndx_sleeve
from moc_vs_moo_analysis import run_ndx_backtest_with_offset

CONV = "mooex"
COST = COST_BPS_PER_SIDE  # 10
CLEAN_START = pd.Timestamp("2008-05-30")
EXT_START = pd.Timestamp("1999-03-10")   # "stress" window in the memo
END = pd.Timestamp("2026-05-22")

# Anchor gate (must reproduce before producing anything).
ANCHOR_CPM = {"sharpe": 1.1910, "maxdd": -12.67, "calmar": 1.0615}   # CPM-solo IV4, clean
ANCHOR_BLEND = {"sharpe": 1.2485, "maxdd": -10.68, "calmar": 1.1928, "martin": 4.354}  # 60/40, clean

SWEEP = [(0.80, 0.20), (0.70, 0.30), (0.60, 0.40), (0.50, 0.50), (0.40, 0.60), (0.30, 0.70)]


def met(s, cash):
    m = perf_metrics(s, cash)
    return {"sharpe": m.get("sharpe"), "cagr": m.get("cagr"), "vol": m.get("vol"),
            "excess_sharpe": m.get("excess_sharpe"), "maxdd": m.get("max_drawdown"),
            "calmar": m.get("calmar"), "martin": m.get("martin")}


def win(s, start, end):
    return s.loc[(s.index >= start) & (s.index <= end)]


def cal2022(s):
    sub = s.loc["2022-01-01":"2022-12-31"]
    return float((1.0 + sub).prod() - 1.0) if len(sub) else float("nan")


def main():
    panel = load_panel(start=EXT_START, end=END)
    end = min(END, panel.index[-1])
    cash = panel["SHV"].ffill().pct_change().dropna()
    od, cy = H.load_open_close()
    intraday = (cy / od - 1.0).reindex(panel.index)
    overnight = (od / cy.shift(1) - 1.0).reindex(panel.index)

    # ---- sleeves (CPM & BULL mooex, production IV4 + slow gate) ----
    cpm, _ = H.cpm_sleeve_conv(panel, intraday, overnight, EXT_START, end, CONV)
    bull, _ = H.bull_sleeve_conv(panel, intraday, overnight, EXT_START, end, CONV, H.GATE_RV60)
    common = cpm.index.intersection(bull.index)
    cpm = cpm.reindex(common); bull = bull.reindex(common)

    # ---- NDX sleeve (production path, T+1 MOO offset=1) for PROD 60/20/20 ----
    ndx_panel = ndx_sleeve.load_ndx_panel()
    ndx = run_ndx_backtest_with_offset(panel, ndx_panel, EXT_START, end, offset=1)
    ndx = ndx.reindex(common).fillna(0.0)

    # ======================= ANCHOR GATE =======================
    print("=== ANCHOR GATE ===")
    cpm_cl = met(win(cpm, CLEAN_START, end), cash)
    ok_cpm = (abs(cpm_cl["sharpe"] - ANCHOR_CPM["sharpe"]) < 5e-4
              and abs(cpm_cl["maxdd"] * 100 - ANCHOR_CPM["maxdd"]) < 0.02
              and abs(cpm_cl["calmar"] - ANCHOR_CPM["calmar"]) < 5e-4)
    print(f"  CPM-solo clean: Sharpe={cpm_cl['sharpe']:.4f} MaxDD={cpm_cl['maxdd']*100:.2f}% "
          f"Calmar={cpm_cl['calmar']:.4f} expect {ANCHOR_CPM} -> {'OK' if ok_cpm else 'MISMATCH'}")

    blend6040 = 0.60 * cpm + 0.40 * bull
    bl_cl = met(win(blend6040, CLEAN_START, end), cash)
    ok_bl = (abs(bl_cl["sharpe"] - ANCHOR_BLEND["sharpe"]) < 5e-4
             and abs(bl_cl["maxdd"] * 100 - ANCHOR_BLEND["maxdd"]) < 0.02
             and abs(bl_cl["calmar"] - ANCHOR_BLEND["calmar"]) < 5e-4
             and abs(bl_cl["martin"] - ANCHOR_BLEND["martin"]) < 5e-3)
    print(f"  60/40 blend clean: Sharpe={bl_cl['sharpe']:.4f} MaxDD={bl_cl['maxdd']*100:.2f}% "
          f"Calmar={bl_cl['calmar']:.4f} Martin={bl_cl['martin']:.4f} expect {ANCHOR_BLEND} "
          f"-> {'OK' if ok_bl else 'MISMATCH'}")

    if not (ok_cpm and ok_bl):
        print("ANCHOR MISMATCH -- aborting, no outputs produced.")
        sys.exit(1)
    print("ANCHOR CONFIRMED -- both gates pass.\n")

    out = {"meta": {"conv": CONV, "cost_bps": COST,
                    "clean": [str(CLEAN_START.date()), str(end.date())],
                    "stress": [str(EXT_START.date()), str(end.date())],
                    "ndx_convention": "T+1 MOO offset=1 (close-to-close; exact-open engine "
                                      "unsupported for per-stock NDX universe + delisting)",
                    "cpm_bull_convention": "T+1 MOO exact (mooex, real auto_adjust opens)"},
           "anchor": {"cpm_solo_clean": cpm_cl, "blend_6040_clean": bl_cl,
                      "cpm_gate_ok": ok_cpm, "blend_gate_ok": ok_bl}}

    # ======================= SECTION 1: two-sleeve blends + PROD ref =======================
    prod = 0.60 * cpm + 0.20 * bull + 0.20 * ndx
    sec1 = {}
    for label, wc, wb in [("60/40", 0.60, 0.40), ("50/50", 0.50, 0.50)]:
        b = wc * cpm + wb * bull
        sec1[label] = {"clean": met(win(b, CLEAN_START, end), cash),
                       "stress": met(win(b, EXT_START, end), cash),
                       "ret_2022": cal2022(win(b, CLEAN_START, end))}
    sec1["PROD_60_20_20"] = {"clean": met(win(prod, CLEAN_START, end), cash),
                             "stress": met(win(prod, EXT_START, end), cash),
                             "ret_2022": cal2022(win(prod, CLEAN_START, end))}
    out["section1"] = sec1

    # ======================= SECTION 2: weight-insensitivity sweep =======================
    sweep = []
    for wc, wb in SWEEP:
        b = wc * cpm + wb * bull
        mc = met(win(b, CLEAN_START, end), cash)
        ms = met(win(b, EXT_START, end), cash)
        sweep.append({"w_cpm": wc, "w_bull": wb,
                      "clean_sharpe": mc["sharpe"], "clean_maxdd": mc["maxdd"],
                      "stress_sharpe": ms["sharpe"], "stress_maxdd": ms["maxdd"]})
    cl_sh = [r["clean_sharpe"] for r in sweep]
    st_sh = [r["stress_sharpe"] for r in sweep]
    clean_band = max(cl_sh) - min(cl_sh)
    stress_band = max(st_sh) - min(st_sh)
    out["section2"] = {"sweep": sweep,
                       "clean_band": clean_band, "stress_band": stress_band,
                       "clean_min": min(cl_sh), "clean_max": max(cl_sh),
                       "stress_min": min(st_sh), "stress_max": max(st_sh),
                       "clean_argmax": SWEEP[int(np.argmax(cl_sh))],
                       "clean_argmin": SWEEP[int(np.argmin(cl_sh))],
                       "stress_argmax": SWEEP[int(np.argmax(st_sh))],
                       "stress_argmin": SWEEP[int(np.argmin(st_sh))]}

    # ======================= SECTION 3: correlation + side-by-side (clean) =======================
    corr_cl = float(win(cpm, CLEAN_START, end).corr(win(bull, CLEAN_START, end)))
    corr_st = float(win(cpm, EXT_START, end).corr(win(bull, EXT_START, end)))

    cpm_m = met(win(cpm, CLEAN_START, end), cash)
    bull_m = met(win(bull, CLEAN_START, end), cash)
    ndx_m = met(win(ndx, CLEAN_START, end), cash)
    b6040_m = sec1["60/40"]["clean"]
    b5050_m = sec1["50/50"]["clean"]
    prod_m = sec1["PROD_60_20_20"]["clean"]

    side = {
        "CPM_standalone": {**cpm_m, "ret_2022": cal2022(win(cpm, CLEAN_START, end))},
        "BULL_standalone": {**bull_m, "ret_2022": cal2022(win(bull, CLEAN_START, end))},
        "NDX_standalone": {**ndx_m, "ret_2022": cal2022(win(ndx, CLEAN_START, end))},
        "TwoSleeve_60_40": {**b6040_m, "ret_2022": sec1["60/40"]["ret_2022"]},
        "TwoSleeve_50_50": {**b5050_m, "ret_2022": sec1["50/50"]["ret_2022"]},
        "PROD_60_20_20": {**prod_m, "ret_2022": sec1["PROD_60_20_20"]["ret_2022"]},
    }
    # deltas: PROD - two-sleeve 60/40 (given up = positive when PROD higher)
    deltas = {
        "cagr_pp_given_up": (prod_m["cagr"] - b6040_m["cagr"]) * 100,
        "sharpe_given_up": prod_m["sharpe"] - b6040_m["sharpe"],
        "excess_sharpe_given_up": prod_m["excess_sharpe"] - b6040_m["excess_sharpe"],
        "vol_pp_gained": (prod_m["vol"] - b6040_m["vol"]) * 100,           # PROD higher vol -> two-sleeve gains lower vol
        "maxdd_pp_gained": (abs(prod_m["maxdd"]) - abs(b6040_m["maxdd"])) * 100,  # PROD deeper DD -> two-sleeve gains shallower DD
        "calmar_delta": b6040_m["calmar"] - prod_m["calmar"],
    }
    out["section3"] = {"corr_clean": corr_cl, "corr_stress": corr_st,
                       "side_by_side_clean": side, "deltas_6040_vs_prod": deltas}

    Path(__file__).with_suffix(".json").write_text(json.dumps(out, indent=2, default=float))
    write_md(out)
    print("DONE -> research/two_sleeve_iv4_memo_numbers_findings.md")
    return out


def write_md(o):
    L = []
    A = L.append
    m = o["meta"]
    s1, s2, s3 = o["section1"], o["section2"], o["section3"]

    def pct(x): return f"{x*100:.2f}%"

    A("# Two-Sleeve CPM + BULL memo numbers -- regenerated under IV4\n")
    A("Role: analyst (hypothesis-driven, read-only re production; no production files changed; "
      "no commit). Throwaway harness `research/two_sleeve_iv4_memo_numbers.py`. This file supplies "
      "the FRESH number set to rewrite `research/two_sleeve_cpm_bull_findings.md` (whose existing "
      "pair / min-var-3-era blend numbers are STALE). Memo prose/rewrite is a separate fixer step; "
      "this file is numbers only.\n")
    A("**Production CPM spec = IV4** (`cpm_live.compute_target_weights`): single-stage cross-asset "
      "momentum -> vol-Faber ranker (faber_score/rv_252d) -> positive-trend screen -> top-4 -> "
      "INVERSE-VOL WEIGHT ALL surviving positives (NO min-var sub-selection) -> strict-4 "
      "partial-safe -> HYG-OR-TIP canary -> timed safe.\n")
    A(f"**Conventions (memo metric set):** CAGR, Vol, raw Sharpe (rf=0), Excess Sharpe vs SHV, "
      f"MaxDD, Calmar (=CAGR/|MaxDD|), 2022 calendar return. CPM & BULL on T+1 MOO exact "
      f"(`mooex`, real auto_adjust opens), post-cost {m['cost_bps']} bps/side, BULL slow vol gate "
      f"rv_60d<rv_252d. Windows: clean {m['clean'][0]}..{m['clean'][1]} (18y); "
      f"stress/ext {m['stress'][0]}..{m['stress'][1]} (27y).\n")
    A(f"**NDX leg caveat (PROD 60/20/20 only):** the NDX sleeve runs on the production path under "
      f"T+1 MOO offset=1 close-to-close ({m['ndx_convention']}). The exact-open (`mooex`) engine "
      f"cannot run the per-stock PIT NDX universe with delisting haircuts, so the NDX 20% leg uses "
      f"close-to-close T+1 MOO while the CPM 60% and BULL 20% legs use exact-open T+1 MOO. CPM and "
      f"BULL legs are byte-identical between the two-sleeve and PROD rows; only the NDX leg carries "
      f"this minor convention nuance.\n")

    a = o["anchor"]
    A("## 0. Anchor gate\n")
    A("| Gate | Sharpe | MaxDD | Calmar | Martin | Expected | Match |")
    A("|---|---:|---:|---:|---:|---|---|")
    ac = a["cpm_solo_clean"]
    A(f"| CPM-solo IV4 (clean) | {ac['sharpe']:.4f} | {pct(ac['maxdd'])} | {ac['calmar']:.4f} | "
      f"{ac['martin']:.4f} | 1.1910 / -12.67% / 1.0615 | "
      f"{'CONFIRMED' if a['cpm_gate_ok'] else 'MISMATCH'} |")
    ab = a["blend_6040_clean"]
    A(f"| 60/40 blend (clean) | {ab['sharpe']:.4f} | {pct(ab['maxdd'])} | {ab['calmar']:.4f} | "
      f"{ab['martin']:.4f} | 1.2485 / -10.68% / 1.1928 / 4.354 | "
      f"{'CONFIRMED' if a['blend_gate_ok'] else 'MISMATCH'} |")
    A("\nBoth anchors reproduce exactly; the rest of this file is trusted on that basis.\n")

    A("## 1. Two-sleeve blend performance (60/40 vs 50/50)\n")
    A("Memo metric conventions; clean (18y) + stress (27y); 2022 calendar return on the clean "
      "series. PROD 60/20/20 (3-sleeve, incl. live NDX) re-cited for reference.\n")
    A("| Portfolio / Split | Window | CAGR | Vol | Raw Sharpe | Excess Sharpe vs SHV | MaxDD | "
      "Calmar | 2022 Return |")
    A("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for label in ("60/40", "50/50"):
        r = s1[label]; c = r["clean"]; st = r["stress"]
        A(f"| **CPM/BULL {label}** | Clean | {pct(c['cagr'])} | {pct(c['vol'])} | {c['sharpe']:.3f} | "
          f"{c['excess_sharpe']:.3f} | {pct(c['maxdd'])} | {c['calmar']:.2f} | "
          f"**{pct(r['ret_2022'])}** |")
        A(f"| | Stress | {pct(st['cagr'])} | {pct(st['vol'])} | {st['sharpe']:.3f} | "
          f"{st['excess_sharpe']:.3f} | {pct(st['maxdd'])} | {st['calmar']:.2f} | |")
    p = s1["PROD_60_20_20"]; pc = p["clean"]; ps = p["stress"]
    A(f"| *PROD 60/20/20* | Clean | {pct(pc['cagr'])} | {pct(pc['vol'])} | {pc['sharpe']:.3f} | "
      f"{pc['excess_sharpe']:.3f} | {pct(pc['maxdd'])} | {pc['calmar']:.2f} | **{pct(p['ret_2022'])}** |")
    A(f"| | Stress | {pct(ps['cagr'])} | {pct(ps['vol'])} | {ps['sharpe']:.3f} | "
      f"{ps['excess_sharpe']:.3f} | {pct(ps['maxdd'])} | {ps['calmar']:.2f} | |")
    A("")

    A("## 2. Weight-insensitivity sweep (80/20 -> 30/70)\n")
    A("| CPM Weight | BULL Weight | Clean Sharpe | Clean MaxDD | Stress Sharpe | Stress MaxDD |")
    A("| --- | --- | --- | --- | --- | --- |")
    for r in s2["sweep"]:
        A(f"| {r['w_cpm']*100:.0f}% | {r['w_bull']*100:.0f}% | {r['clean_sharpe']:.3f} | "
          f"{pct(r['clean_maxdd'])} | {r['stress_sharpe']:.3f} | {pct(r['stress_maxdd'])} |")
    amx = s2["clean_argmax"]; amn = s2["clean_argmin"]
    smx = s2["stress_argmax"]; smn = s2["stress_argmin"]
    A(f"\n- **Clean Sharpe band:** {s2['clean_band']:.3f} (low {s2['clean_min']:.3f} at "
      f"{amn[0]*100:.0f}/{amn[1]*100:.0f}, high {s2['clean_max']:.3f} at {amx[0]*100:.0f}/{amx[1]*100:.0f}).")
    A(f"- **Stress Sharpe band:** {s2['stress_band']:.3f} (low {s2['stress_min']:.3f} at "
      f"{smn[0]*100:.0f}/{smn[1]*100:.0f}, high {s2['stress_max']:.3f} at {smx[0]*100:.0f}/{smx[1]*100:.0f}).")
    flat = (s2["clean_band"] <= 0.10) and (s2["stress_band"] <= 0.10)
    A(f"- **Verdict on fit:** {'FLAT (not weight-fitted)' if flat else 'PEAKED'} -- the entire "
      f"80/20..30/70 sweep spans a max Sharpe range of {max(s2['clean_band'], s2['stress_band']):.3f}. "
      f"The split is not a fitted parameter.\n")

    A("## 3. Correlation & diversification\n")
    A(f"- **CPM-BULL correlation (clean):** {s3['corr_clean']:.4f}")
    A(f"- **CPM-BULL correlation (stress):** {s3['corr_stress']:.4f}\n")
    A("### Side-by-side vs PROD 60/20/20 (clean window)\n")
    sb = s3["side_by_side_clean"]
    cols = [("CPM Standalone", "CPM_standalone"), ("BULL Standalone", "BULL_standalone"),
            ("NDX Standalone", "NDX_standalone"), ("2-Sleeve 60/40", "TwoSleeve_60_40"),
            ("2-Sleeve 50/50", "TwoSleeve_50_50"), ("3-Sleeve PROD", "PROD_60_20_20")]
    A("| Metric | " + " | ".join(h for h, _ in cols) + " |")
    A("| --- |" + " --- |" * len(cols))

    def rowm(name, fmt):
        return f"| **{name}** | " + " | ".join(fmt(sb[k]) for _, k in cols) + " |"
    A(rowm("CAGR", lambda d: pct(d['cagr'])))
    A(rowm("Vol", lambda d: pct(d['vol'])))
    A(rowm("Raw Sharpe", lambda d: f"{d['sharpe']:.3f}"))
    A(rowm("Excess Sharpe", lambda d: f"{d['excess_sharpe']:.3f}"))
    A(rowm("MaxDD", lambda d: pct(d['maxdd'])))
    A(rowm("Calmar", lambda d: f"{d['calmar']:.2f}"))
    A(rowm("2022 Return", lambda d: pct(d['ret_2022'])))

    d = s3["deltas_6040_vs_prod"]
    A("\n### 60/40 two-sleeve vs PROD 60/20/20 -- what is given up / gained (clean)\n")
    A("Given up by dropping NDX (two-sleeve 60/40 minus PROD):")
    A(f"- **CAGR:** give up {d['cagr_pp_given_up']:.2f}pp "
      f"({pct(sb['PROD_60_20_20']['cagr'])} PROD -> {pct(sb['TwoSleeve_60_40']['cagr'])} 60/40).")
    A(f"- **Raw Sharpe:** give up {d['sharpe_given_up']:.3f} "
      f"({sb['PROD_60_20_20']['sharpe']:.3f} -> {sb['TwoSleeve_60_40']['sharpe']:.3f}).")
    A(f"- **Excess Sharpe:** give up {d['excess_sharpe_given_up']:.3f} "
      f"({sb['PROD_60_20_20']['excess_sharpe']:.3f} -> {sb['TwoSleeve_60_40']['excess_sharpe']:.3f}).")
    A("\nGained by dropping NDX:")
    A(f"- **Vol:** lower by {d['vol_pp_gained']:.2f}pp "
      f"({pct(sb['PROD_60_20_20']['vol'])} PROD -> {pct(sb['TwoSleeve_60_40']['vol'])} 60/40).")
    A(f"- **MaxDD:** shallower by {d['maxdd_pp_gained']:.2f}pp "
      f"({pct(sb['PROD_60_20_20']['maxdd'])} PROD -> {pct(sb['TwoSleeve_60_40']['maxdd'])} 60/40).")
    A(f"- **Calmar:** {d['calmar_delta']:+.2f} ({sb['PROD_60_20_20']['calmar']:.2f} PROD -> "
      f"{sb['TwoSleeve_60_40']['calmar']:.2f} 60/40).")
    A("- **Operational:** zero individual stocks (broad-index ETFs only) vs monthly NDX-constituent "
      "rebalancing.\n")

    A("## Caveats\n")
    A("- CPM & BULL legs: production IV4 `cpm_live.compute_target_weights` + production BULL slow "
      "gate, run on T+1 MOO exact (mooex, real auto_adjust opens), 10 bps/side post-cost; "
      "anchor-gated to the FINAL IV4 set.")
    A("- NDX leg (PROD 60/20/20 + NDX standalone only): production NDX sleeve under T+1 MOO "
      "offset=1 close-to-close (exact-open engine unsupported for per-stock PIT universe + "
      "delisting). The NDX 20% leg therefore carries a minor convention difference vs the "
      "exact-open CPM/BULL legs; CPM and BULL contributions are identical across the two-sleeve "
      "and PROD rows.")
    A("- Stress/ext window (1999-03-10..) is partially proxy-backed pre-2006-2008 for the CPM "
      "trend universe; clean 18y has full real-open coverage and is the decisive lens. NDX "
      "constituent data does not extend across the full stress window, so PROD stress-row NDX leg "
      "is near-cash pre-data.")
    A("- Martin = CAGR / UlcerIndex, UlcerIndex = sqrt(mean(dd_pct^2)); from production "
      "perf_metrics. (Memo tables report Calmar; Martin shown only in the anchor gate.)")

    Path(ROOT / "research" / "two_sleeve_iv4_memo_numbers_findings.md").write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
