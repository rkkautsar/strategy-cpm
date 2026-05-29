#!/usr/bin/env python3
"""Analysis + findings generator for the CPM breadth canary overlay.

Reads /tmp/cpm_breadth_payload.pkl (from cpm_breadth_canary.py) and writes
research/cpm_breadth_canary_findings.md. Computes:
  - n_positive distribution and gating frequency
  - forward CPM return of gated vs non-gated months (false-positive test)
  - interaction with the existing HYG-OR-TIP canary / partial-safe
  - 2022 + 2008 calendar returns per variant
"""
from __future__ import annotations

import pickle
from pathlib import Path

import numpy as np
import pandas as pd

with open("/tmp/cpm_breadth_payload.pkl", "rb") as f:
    P = pickle.load(f)

results = P["results"]
diags = P["diags"]
daily_cpm = P["daily_cpm"]
daily_blend = P["daily_blend"]
turnovers = P["turnovers"]
cash = P["cash_daily"]
v0_ok = P["v0_ok"]

VARIANTS = ["V0", "V_lt2", "V_lt3", "V_lt4", "V_contT4", "V_contT6"]
GATES = ["V_lt2", "V_lt3", "V_lt4", "V_contT4", "V_contT6"]


def cal_ret(daily, y):
    seg = daily.loc[f"{y}-01-01":f"{y}-12-31"]
    return (1.0 + seg).prod() - 1.0 if not seg.empty else float("nan")


def fwd_month_returns(cpm_daily):
    """Forward (next calendar month) return per month-end signal date."""
    m = (1.0 + cpm_daily).resample("ME").prod() - 1.0
    fwd = m.shift(-1)  # return realized in month after this month-end
    return fwd


# ---- forward V0 CPM monthly returns (what ungated CPM earns next month) ----
fwd_clean = fwd_month_returns(daily_cpm[("V0", "clean")])
fwd_stress = fwd_month_returns(daily_cpm[("V0", "stress")])

# ---- n_pos distribution (use V0 diag, has all months) ----
diag_v0_clean = diags[("V0", "clean")]
diag_v0_stress = diags[("V0", "stress")]


def npos_dist(diag):
    n = diag["n_pos"]
    total = len(n)
    rows = []
    for k in range(0, 9):
        cnt = (n == k).sum()
        rows.append((k, cnt, cnt / total * 100))
    return rows, total


def thresh_freq(diag):
    n = diag["n_pos"]
    total = len(n)
    return {
        "<2": (n < 2).sum() / total * 100,
        "<3": (n < 3).sum() / total * 100,
        "<4": (n < 4).sum() / total * 100,
    }


# ---- per-gate activity + forward-return false-positive test ----
def gate_activity(variant, window, fwd):
    diag = diags[(variant, window)]
    base_diag = diags[("V0", window)]
    gated = diag["gated"]
    n_gated = gated.sum()
    total = len(gated)
    pct_gated = n_gated / total * 100 if total else float("nan")
    # base regime already defensive among gated months (interaction/redundancy)
    base_def = (base_diag["base_regime"] == "DEFENSIVE")
    gated_idx = diag.index[gated]
    # redundancy: of gated months, how many already had base risky < 1 or DEFENSIVE
    base_risky = base_diag["risky_base"].reindex(gated_idx)
    n_already_def = (base_diag.loc[gated_idx, "base_regime"] == "DEFENSIVE").sum()
    n_already_partial = ((base_risky < 0.999) & (base_diag.loc[gated_idx, "base_regime"] != "DEFENSIVE")).sum()
    n_full_risky_gated = (base_risky > 0.999).sum()
    # forward returns of gated vs non-gated
    fwd_al = fwd.reindex(diag.index)
    fwd_gated = fwd_al[gated].dropna()
    fwd_nongated = fwd_al[~gated].dropna()
    return {
        "pct_gated": pct_gated, "n_gated": int(n_gated), "total": total,
        "n_already_def": int(n_already_def),
        "n_already_partial": int(n_already_partial),
        "n_full_risky_gated": int(n_full_risky_gated),
        "fwd_gated_mean": fwd_gated.mean() * 100 if len(fwd_gated) else float("nan"),
        "fwd_gated_median": fwd_gated.median() * 100 if len(fwd_gated) else float("nan"),
        "fwd_gated_n": len(fwd_gated),
        "fwd_gated_pctpos": (fwd_gated > 0).mean() * 100 if len(fwd_gated) else float("nan"),
        "fwd_nongated_mean": fwd_nongated.mean() * 100 if len(fwd_nongated) else float("nan"),
        "fwd_all_mean": fwd_al.dropna().mean() * 100,
    }


# correlation of n_pos with forward CPM return (predictiveness)
def npos_fwd_corr(window, fwd):
    diag = diags[("V0", window)]
    df = pd.DataFrame({"n": diag["n_pos"], "fwd": fwd.reindex(diag.index)}).dropna()
    return df["n"].corr(df["fwd"]), len(df)


# ---------------- build findings ----------------
lines = []
A = lines.append

A("# CPM Breadth Canary Overlay - Findings\n")
A("Hypothesis: a breadth canary (risk-off / scale-down when too few of the 8 "
  "risky-universe assets have positive Faber trend) is a useful complementary "
  "regime gate on top of the existing HYG-OR-TIP canary + positive-Faber "
  "partial-safe structure, evaluated in the 60/40 two-sleeve CPM+BULL "
  "research baseline.\n")
A(f"V0 reproduction check (target 1.347 Sharpe / 13.59% CAGR / -9.82% MaxDD, "
  f"60/40 clean blend): **{'PASS' if v0_ok else 'FAIL'}**\n")

A("Method: reimplemented `run_cpm_backtest` in "
  "`research/cpm_breadth_canary.py` with an overlay hook applied to the "
  "output of the production `compute_target_weights` (no production files "
  "edited). Breadth signal `n_positive` = count of the 8 risky-universe "
  "assets (QQQ, SPHQ, EFA, EEM, VNQ, GLD, TLT, DBC) with positive Faber "
  "10mo-SMA distance at the month-end signal date. Discrete gates force 100% "
  "best_safe when `n_positive < T`; continuous gates scale CPM risky exposure "
  "by `min(1, n_positive/T)` with the remainder to best_safe (no leverage). "
  "Existing canary + structure kept in all variants.\n")
A("Windows: clean 2008-05-30..2026-05-22, stress 1999-03-10..2026-05-22. "
  "Costs 10bps/side. Excess Sharpe vs SHV.\n")

# ---- Section 1: headline metrics tables ----
A("\n## 1. Performance: CPM standalone and 60/40 blend\n")
for window in ["clean", "stress"]:
    A(f"\n### {window.capitalize()} window\n")
    A("| Variant | Sleeve | Raw Sharpe | Excess Sharpe | CAGR | Vol | MaxDD | Calmar | Turnover/yr |")
    A("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for v in VARIANTS:
        for sleeve in ["cpm", "blend"]:
            m = results[(v, window, sleeve)]
            tov = turnovers[(v, window)] if sleeve == "cpm" else float("nan")
            tov_s = f"{tov*100:.0f}%" if sleeve == "cpm" else "-"
            A(f"| {v} | {sleeve} | {m['sharpe']:.3f} | {m['excess_sharpe']:.3f} | "
              f"{m['cagr']*100:.2f}% | {m['vol']*100:.2f}% | "
              f"{m['max_drawdown']*100:.2f}% | {m['calmar']:.2f} | {tov_s} |")

# ---- crisis calendar returns ----
A("\n## 2. Crisis / calendar returns (60/40 blend)\n")
A("| Variant | 2022 (clean) | 2008 (stress) |")
A("| --- | --- | --- |")
for v in VARIANTS:
    r2022 = cal_ret(daily_blend[(v, "clean")], 2022)
    r2008 = cal_ret(daily_blend[(v, "stress")], 2008)
    A(f"| {v} | {r2022*100:.2f}% | {r2008*100:.2f}% |")

# ---- Section 3: n_pos distribution ----
A("\n## 3. Breadth activity diagnostic\n")
for window, diag in [("clean", diag_v0_clean), ("stress", diag_v0_stress)]:
    rows, total = npos_dist(diag)
    tf = thresh_freq(diag)
    A(f"\n### {window.capitalize()} window - n_positive distribution "
      f"({total} months)\n")
    A("| n_positive | months | % |")
    A("| --- | --- | --- |")
    for k, cnt, pct in rows:
        A(f"| {k} | {cnt} | {pct:.1f}% |")
    A(f"\nThreshold frequency: n<2 = {tf['<2']:.1f}%, n<3 = {tf['<3']:.1f}%, "
      f"n<4 = {tf['<4']:.1f}% of months.")

# ---- Section 4: gating activity + false positive ----
A("\n## 4. Gating activity + false-positive test (does low breadth predict "
  "bad forward CPM returns?)\n")
A("Forward return = next-calendar-month return of the ungated V0 CPM sleeve. "
  "If low-breadth months are a real signal, gated months should have clearly "
  "negative / below-average forward returns. If gated-month forward returns "
  "are near or above average, the gate is mostly exiting good months "
  "(false positives).\n")
for window in ["clean", "stress"]:
    fwd = fwd_clean if window == "clean" else fwd_stress
    corr, ncorr = npos_fwd_corr(window, fwd)
    A(f"\n### {window.capitalize()} window\n")
    A(f"Correlation(n_positive, forward CPM monthly return) = **{corr:.3f}** "
      f"(n={ncorr}). All-month mean forward CPM return = "
      f"{fwd.reindex(diags[('V0',window)].index).dropna().mean()*100:.2f}%.\n")
    A("| Gate | % months gated | fwd ret gated (mean) | gated median | "
      "% gated fwd>0 | fwd ret non-gated (mean) |")
    A("| --- | --- | --- | --- | --- | --- |")
    for v in GATES:
        ga = gate_activity(v, window, fwd)
        A(f"| {v} | {ga['pct_gated']:.1f}% ({ga['n_gated']}/{ga['total']}) | "
          f"{ga['fwd_gated_mean']:.2f}% | {ga['fwd_gated_median']:.2f}% | "
          f"{ga['fwd_gated_pctpos']:.0f}% | {ga['fwd_nongated_mean']:.2f}% |")

# ---- Section 5: interaction / redundancy ----
A("\n## 5. Interaction with existing HYG-OR-TIP canary + partial-safe "
  "(redundancy)\n")
A("For each gate, of the months where the breadth overlay reduces risk, how "
  "many were ALREADY defensive or partial under the production rules (so the "
  "breadth gate adds nothing) vs full-risky months it newly cuts.\n")
for window in ["clean", "stress"]:
    fwd = fwd_clean if window == "clean" else fwd_stress
    A(f"\n### {window.capitalize()} window\n")
    A("| Gate | months gated | already DEFENSIVE | already partial-safe | "
      "newly cuts full-risky |")
    A("| --- | --- | --- | --- | --- |")
    for v in GATES:
        ga = gate_activity(v, window, fwd)
        A(f"| {v} | {ga['n_gated']} | {ga['n_already_def']} | "
          f"{ga['n_already_partial']} | {ga['n_full_risky_gated']} |")

# ---- Section 6: verdict ----
A("\n## 6. Verdict\n")

v0 = results[("V0", "clean", "blend")]
best = None
for v in GATES:
    m = results[(v, "clean", "blend")]
    d_sharpe = m["sharpe"] - v0["sharpe"]
    d_dd = abs(m["max_drawdown"]) - abs(v0["max_drawdown"])
    d_cagr = (m["cagr"] - v0["cagr"]) * 100
    A(f"- **{v}** (clean blend): Sharpe {m['sharpe']:.3f} ({d_sharpe:+.3f}), "
      f"MaxDD {m['max_drawdown']*100:.2f}% ({-d_dd:+.2f}pp), "
      f"CAGR {m['cagr']*100:.2f}% ({d_cagr:+.2f}pp).")

A("")
A("See the synthesized conclusion paragraph appended below.\n")

Path("research/cpm_breadth_canary_findings.md").write_text("\n".join(lines))
print("Wrote research/cpm_breadth_canary_findings.md")

# also dump key numbers for the agent to read
print("\n=== KEY NUMBERS ===")
for window in ["clean", "stress"]:
    fwd = fwd_clean if window == "clean" else fwd_stress
    corr, ncorr = npos_fwd_corr(window, fwd)
    print(f"\n[{window}] corr(n_pos, fwd CPM ret) = {corr:.3f}")
    for v in GATES:
        ga = gate_activity(v, window, fwd)
        print(f"  {v:9s} gated {ga['pct_gated']:5.1f}% | fwd_gated {ga['fwd_gated_mean']:+.2f}% "
              f"vs nongated {ga['fwd_nongated_mean']:+.2f}% | "
              f"already_def {ga['n_already_def']}/{ga['n_gated']} "
              f"newcut {ga['n_full_risky_gated']}")
