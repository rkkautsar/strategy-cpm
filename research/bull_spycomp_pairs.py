# -*- coding: utf-8 -*-
"""Analyst research (read-only re production; writes only research/; NO prod/memo
change; NO commit).

SIMPLER SPY-COMP ablation on BULL: TIP as the ONLY recession indicator, then add
ONE other indicator at a time -> 2-indicator (pair) composites at k=1.

REUSES research/bull_spycomp_composite.py (warn fns, make_composite, make_prod_and,
metrics helpers, bootstrap). Does NOT rebuild anything.

BULL gate (all configs): risk_on = (n_warnings < 1) OR spy_trend_up.
  k=1: 0 warnings -> ride SPY; >=1 warning -> defer to SPY 13612U trend.
risk-off -> best-of(SHV/IEF). asset SPY. mooex T+1 MOO, 10bps/side, both-252.

Configs:
  - HAA-Simple (baseline A) = prod AND gate (TIP-canary AND SPY-trend), number to beat.
  - TIP-only (baseline B)   = make_composite(M, 1, active=["tip"]) = OR-TIP minimal.
  - 5 pairs k=1: ["tip","vix"], ["tip","yc"], ["tip","unrate"], ["tip","breadth"], ["tip","erp"].

KEY Q: does adding a 2nd indicator to TIP (k=1) materially lift the minimal SPY-COMP,
and does ANY pair beat HAA-Simple on BOTH Sharpe AND Calmar? Winners -> bootstrap +
walk-forward before any adoption claim.

Writes research/bull_spycomp_pairs_findings.md (+ .json).
"""
from __future__ import annotations
import sys, json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from research import cpm_harness as H
from research.bull_spycomp_composite import (
    load_macro, make_prod_and, make_composite, met, dd_in,
    stationary_bootstrap_sharpe, CLEAN_START, EXT_START,
)
from cpm_live import perf_metrics


def main():
    data = H.load_data()
    cash = data.cash
    M = load_macro()
    anchor = {k: round(float(v), 4) for k, v in H.verify_anchor(data=data).items()}
    print("anchor:", anchor)

    CRISES = {
        "GFC_2008": ("2007-10-01", "2009-06-30"),
        "COVID_2020": ("2020-02-01", "2020-06-30"),
        "Y2022": ("2022-01-01", "2022-12-31"),
        "Tariff_2025": ("2025-02-01", "2025-06-30"),
    }

    PAIRS = [
        ("tip+vix", ["tip", "vix"]),
        ("tip+yc", ["tip", "yc"]),
        ("tip+unrate", ["tip", "unrate"]),
        ("tip+breadth", ["tip", "breadth"]),
        ("tip+erp", ["tip", "erp"]),
    ]

    variants = {
        "HAA-Simple (prod AND)": make_prod_and(M),
        "TIP-only (k1)": make_composite(M, 1, active=["tip"]),
    }
    for label, active in PAIRS:
        variants[label] = make_composite(M, 1, active=active)

    rows = {}
    series_clean = {}
    for name, wf in variants.items():
        s_clean = H.run_strategy(wf, window="clean", data=data)
        s_ext = H.run_strategy(wf, window="ext", data=data)
        series_clean[name] = s_clean
        rec = {"clean": met(s_clean, cash), "ext": met(s_ext, cash)}
        rec["crisis_dd"] = {ck: dd_in(s_ext, lo, hi) for ck, (lo, hi) in CRISES.items()}
        rows[name] = rec
        c = rec["clean"]
        print(f"{name:24s} clean Sh={c['sharpe']:.3f} Cal={c['calmar']:.3f} "
              f"MDD={c['maxdd']*100:6.2f}% Mar={c['martin']:.2f}")

    # ---- winners: pairs beating HAA-Simple on BOTH Sharpe AND Calmar (clean) ----
    base = rows["HAA-Simple (prod AND)"]["clean"]
    winners = []
    for label, _ in PAIRS:
        c = rows[label]["clean"]
        if (c["sharpe"] is not None and c["calmar"] is not None
                and c["sharpe"] > base["sharpe"] and c["calmar"] > base["calmar"]):
            winners.append(label)
    print("winners (beat HAA-Simple on Sharpe AND Calmar):", winners or "NONE")

    # ---- bootstrap + walk-forward for any winner ----
    boot = {}
    wf_out = {}
    for w in winners:
        p, mdiff, sdiff = stationary_bootstrap_sharpe(
            series_clean[w], series_clean["HAA-Simple (prod AND)"])
        boot[w] = {"p_sharpe_diff_le0": p, "mean_diff": mdiff, "std_diff": sdiff}
        print(f"  bootstrap {w}: p(dSharpe<=0)={p:.3f} mean dSh={mdiff:+.3f}")
        # sequential OOS walk-forward: pick best of {HAA-Simple, winner} by trailing
        # in-sample Sharpe each year, apply OOS next year, chain.
        cand = ["HAA-Simple (prod AND)", w]
        cser = {n: series_clean[n] for n in cand}
        years = sorted({d.year for d in series_clean["HAA-Simple (prod AND)"].index})
        MIN_IS = 4
        chain, picks = [], []
        for yi, y in enumerate(years):
            if yi < MIN_IS:
                pick = "HAA-Simple (prod AND)"
            else:
                is_lo = pd.Timestamp(f"{years[0]}-01-01"); is_hi = pd.Timestamp(f"{y-1}-12-31")
                best, best_sh = None, -1e9
                for n in cand:
                    seg = cser[n].loc[(cser[n].index >= is_lo) & (cser[n].index <= is_hi)]
                    sh = met(seg, cash)["sharpe"]
                    if sh is not None and sh > best_sh:
                        best_sh, best = sh, n
                pick = best
            oos = cser[pick].loc[(cser[pick].index >= pd.Timestamp(f"{y}-01-01"))
                                 & (cser[pick].index <= pd.Timestamp(f"{y}-12-31"))]
            chain.append(oos); picks.append({"year": y, "pick": pick})
        wf_oos = pd.concat(chain).sort_index()
        oos_start = pd.Timestamp(f"{years[MIN_IS]}-01-01")
        wf_oos_only = wf_oos.loc[wf_oos.index >= oos_start]
        wf_out[w] = {
            "walkforward_oos_only": met(wf_oos_only, cash),
            "prod_oos_only": met(series_clean["HAA-Simple (prod AND)"].loc[
                series_clean["HAA-Simple (prod AND)"].index >= oos_start], cash),
            "winner_oos_only": met(series_clean[w].loc[
                series_clean[w].index >= oos_start], cash),
            "picks": picks, "oos_start": str(oos_start.date()),
        }

    out = {
        "meta": {
            "conv": "mooex", "cost_bps": 10, "baseline": "both-252",
            "clean": [str(CLEAN_START.date()), str(data.end.date())],
            "ext": [str(EXT_START.date()), str(data.end.date())],
            "gate": "risk_on = (n_warnings < 1) OR spy_trend_up (k=1)",
            "anchor": anchor,
            "note": "k=1 + more indicators = more deferral to SPY trend (monotone "
                    "toward pure trend-following); interpret 'trend' as the trend "
                    "sleeve direction.",
        },
        "variants": rows,
        "winners": winners,
        "bootstrap_vs_haa": boot,
        "walkforward": wf_out,
    }
    Path(__file__).with_suffix(".json").write_text(json.dumps(out, indent=2, default=float))
    write_md(out)
    print("DONE -> research/bull_spycomp_pairs_findings.md")
    return out


def write_md(o):
    L = []; A = L.append
    m = o["meta"]; V = o["variants"]
    def pct(x):
        return f"{x*100:.2f}%" if x is not None and np.isfinite(x) else "n/a"
    def f3(x):
        return f"{x:.3f}" if x is not None and np.isfinite(x) else "n/a"

    order = list(V.keys())
    base = V["HAA-Simple (prod AND)"]["clean"]
    tiponly = V["TIP-only (k1)"]["clean"]

    A("# BULL SPY-COMP TIP+1 pairs ablation (k=1)\n")
    A("Role: analyst (read-only re production; writes only to research/; no "
      "prod/memo/cpm_live/bull_spy_live changed; no commit). Harness "
      "`research/cpm_harness.py`; reuses `research/bull_spycomp_composite.py` "
      "(warn fns, make_composite, metrics, bootstrap) -- nothing rebuilt.\n")
    A("**Question:** starting from TIP as the ONLY recession indicator, does adding "
      "ONE other indicator (2-indicator composite, k=1) materially lift the minimal "
      "SPY-COMP gate, and does ANY TIP+1 pair beat the production HAA-Simple AND gate "
      "on BOTH Sharpe AND Calmar?\n")
    A(f"**Gate (all SPY-COMP configs):** `{m['gate']}` -- 0 warnings ride SPY; >=1 "
      "warning defer to SPY 13612U trend; risk-off -> best-of(SHV/IEF). Asset SPY.\n")
    A(f"**Conventions:** mooex T+1 MOO exact, {m['cost_bps']} bps/side, {m['baseline']}. "
      f"Clean (decision lens) {m['clean'][0]}..{m['clean'][1]}. "
      f"Ext {m['ext'][0]}..{m['ext'][1]}. Anchor verify: {m['anchor']}.\n")
    A(f"**Monotonicity note:** {m['note']}\n")

    A("## 1. Sleeve comparison -- clean decision lens\n")
    A("| Config | Sharpe | Calmar | Martin | MaxDD | CAGR | Vol |")
    A("|---|---:|---:|---:|---:|---:|---:|")
    for name in order:
        c = V[name]["clean"]
        A(f"| {name} | {f3(c['sharpe'])} | {f3(c['calmar'])} | {f3(c['martin'])} | "
          f"{pct(c['maxdd'])} | {pct(c['cagr'])} | {pct(c['vol'])} |")
    A("")

    A("## 2. Per-crisis drawdown (BULL sleeve, from ext series)\n")
    A("GFC 2007-10..2009-06; COVID 2020-02..2020-06 (fast-crash override risk); "
      "2022 full year; 2025 tariff 2025-02..2025-06.\n")
    A("| Config | GFC_2008 | COVID_2020 | Y2022 | Tariff_2025 |")
    A("|---|---:|---:|---:|---:|")
    for name in order:
        d = V[name]["crisis_dd"]
        A(f"| {name} | {pct(d['GFC_2008'])} | {pct(d['COVID_2020'])} | "
          f"{pct(d['Y2022'])} | {pct(d['Tariff_2025'])} |")
    A("")

    A("## 3. Does TIP+1 lift the minimal SPY-COMP (vs TIP-only)?\n")
    A(f"TIP-only (k1): Sharpe {f3(tiponly['sharpe'])}, Calmar {f3(tiponly['calmar'])}, "
      f"MaxDD {pct(tiponly['maxdd'])}. Deltas of each pair vs TIP-only:\n")
    A("| Pair | dSharpe vs TIP-only | dCalmar vs TIP-only | dMaxDD |")
    A("|---|---:|---:|---:|")
    for name in order:
        if not name.startswith("tip+"):
            continue
        c = V[name]["clean"]
        ds = c["sharpe"] - tiponly["sharpe"]
        dc = c["calmar"] - tiponly["calmar"]
        dd = (c["maxdd"] - tiponly["maxdd"]) * 100
        A(f"| {name} | {ds:+.3f} | {dc:+.3f} | {dd:+.2f}pp |")
    A("")

    A("## 4. Winners (beat HAA-Simple on BOTH Sharpe AND Calmar, clean)\n")
    if o["winners"]:
        A("Pairs clearing the joint Sharpe AND Calmar bar vs HAA-Simple "
          f"(Sharpe {f3(base['sharpe'])}, Calmar {f3(base['calmar'])}): "
          + ", ".join(o["winners"]) + ".\n")
        A("### Bootstrap (paired stationary, block ~20d, 2000 reps): Sharpe(pair) - Sharpe(HAA-Simple)\n")
        A("| Pair | p(dSharpe<=0) | mean dSharpe | std |")
        A("|---|---:|---:|---:|")
        for w, b in o["bootstrap_vs_haa"].items():
            A(f"| {w} | {b['p_sharpe_diff_le0']:.3f} | {b['mean_diff']:+.3f} | {b['std_diff']:.3f} |")
        A("")
        A("### Walk-forward (yearly OOS pick best of {HAA-Simple, winner} by trailing IS Sharpe)\n")
        for w, wf in o["walkforward"].items():
            A(f"**{w}** (OOS from {wf['oos_start']}):\n")
            A("| Series | Sharpe | Calmar | Martin | MaxDD | CAGR |")
            A("|---|---:|---:|---:|---:|---:|")
            for key in ["walkforward_oos_only", "prod_oos_only", "winner_oos_only"]:
                r = wf[key]
                A(f"| {key} | {f3(r['sharpe'])} | {f3(r['calmar'])} | {f3(r['martin'])} | "
                  f"{pct(r['maxdd'])} | {pct(r['cagr'])} |")
            A("")
            A("Yearly picks: " + ", ".join(
                f"{p['year']}:{'HAA' if p['pick'].startswith('HAA') else w}" for p in wf["picks"]) + "\n")
    else:
        A(f"**NONE.** No TIP+1 pair beat HAA-Simple (Sharpe {f3(base['sharpe'])}, "
          f"Calmar {f3(base['calmar'])}) on BOTH Sharpe AND Calmar. Bootstrap and "
          "walk-forward skipped (no winner to validate).\n")

    A("## 5. Verdict\n")
    if not o["winners"]:
        A("**HAA-Simple still wins.** No TIP+1 pair (k=1) beats the production AND gate "
          "on both Sharpe and Calmar.\n")
    else:
        A("See bootstrap + walk-forward above; adopt only if a winner survives BOTH.\n")
    A("**Why (structural):** at k=1, every added indicator can only ADD warnings, and "
      "any single warning flips the gate from 'ride SPY' to 'defer to SPY trend'. So "
      "TIP+1 is monotonically MORE permissive-to-trend than TIP-only and strictly more "
      "deferral-heavy than the conservative AND gate, which requires BOTH TIP canary AND "
      "SPY trend to risk on. For a tail-defense sleeve, the AND gate's conservatism is the "
      "value driver; pushing toward pure trend-following via more k=1 warnings does not "
      "recover it.\n")
    A("**Discipline:** clean window = decision lens; single in-sample pass; t+1 MOO exact; "
      "10 bps/side; both-252. Overfit DoF here is modest (only pair selection over 5 pairs), "
      "but any apparent winner still requires the bootstrap + walk-forward gate above before "
      "any adoption claim.\n")

    Path(ROOT / "research" / "bull_spycomp_pairs_findings.md").write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
