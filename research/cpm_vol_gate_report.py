#!/usr/bin/env python3
"""Generate research/cpm_vol_gate_findings.md from /tmp/cpm_vol_gate_payload.pkl."""
from __future__ import annotations
import pickle
import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

VARIANTS = ["V0", "V_rvspy_bin", "V_rvspy_cont", "V_rvbook_bin", "V_rvbook_cont"]
LABEL = {
    "V0": "V0 (no gate)",
    "V_rvspy_bin": "SPY-RV binary",
    "V_rvspy_cont": "SPY-RV cont",
    "V_rvbook_bin": "book-RV binary",
    "V_rvbook_cont": "book-RV cont",
}

with open("/tmp/cpm_vol_gate_payload.pkl", "rb") as f:
    P = pickle.load(f)

results = P["results"]; diags = P["diags"]; daily_cpm = P["daily_cpm"]
daily_blend = P["daily_blend"]; turnovers = P["turnovers"]
cpm_v0 = P["cpm_v0"]; has_vix = P["has_vix"]

L = []
def w(s=""): L.append(s)

def cal_ret(daily, y0, y1):
    seg = daily.loc[y0:y1]
    return float((1.0 + seg).prod() - 1.0) if not seg.empty else float("nan")

def perf_line(variant, wname, sleeve):
    m = results[(variant, wname, sleeve)]
    to = turnovers[(variant, wname)] if sleeve == "cpm" else None
    to_s = f"{to*100:.0f}%" if to is not None else "-"
    return (f"| {LABEL[variant]} | {sleeve} | {m['sharpe']:.3f} | "
            f"{m['excess_sharpe']:.3f} | {m['cagr']*100:.2f}% | "
            f"{m['vol']*100:.2f}% | {m['max_drawdown']*100:.2f}% | "
            f"{m['calmar']:.2f} | {to_s} |")

w("# CPM Volatility-Regime Gate Overlay - Findings")
w()
w("Hypothesis: a volatility-regime gate (de-risk CPM when market or realized "
  "volatility spikes) is a useful NEW overlay on top of the existing CPM "
  "structure (HYG-OR-TIP canary + positive-Faber filter + K=4 + min-var pair), "
  "intended to catch the high-breadth-then-crash regime the breadth canary "
  "misses (notably the 2020 COVID crash). Evaluated in the 60/40 two-sleeve "
  "CPM+BULL research baseline. Mirrors the BULL sleeve's existing "
  "`_vol_gate_ok` (RV_20d < RV_252d) logic, applied to CPM, which today has NO "
  "vol gate.")
w()
v0_ok = P["v0_ok"]
w(f"V0 reproduction check (target 1.347 Sharpe / 13.59% CAGR / -9.82% MaxDD, "
  f"60/40 clean blend): **{'PASS' if v0_ok else 'FAIL'}**")
w()
w(f"VIX/VIX3M availability: **VIX NOT available** in the proxy panel "
  f"(`has_vix={has_vix}`; panel columns contain no VIX or VIX3M series). "
  f"Per task fallback, SIG-VIX (term-structure backwardation / level threshold) "
  f"could NOT be tested. All signals below use realized-vol crossovers.")
w()
w("Method: reimplemented `run_cpm_backtest` in `research/cpm_vol_gate.py` with "
  "an overlay hook applied to the output of the production "
  "`compute_target_weights` (no production files edited). Two vol signals:")
w()
w("- **SIG-RV-SPY**: SPY `RV_20d >= RV_252d` (annualized daily-return std, tail "
  "20 vs tail 252; mirrors BULL `_vol_gate_ok` exactly, fires on the inverse of "
  "`vol_ok`).")
w("- **SIG-RV-BOOK**: same crossover on the V0 (ungated) CPM **book** daily "
  "return (RV of the CPM sleeve return, 20d vs 252d).")
w()
w("Two gate actions: **binary** (100% best_safe when fired) and **continuous** "
  "(scale risky exposure by `f = min(1, RV_252/RV_20)`, remainder to best_safe; "
  "no leverage, cap 1.0). Existing canary + structure kept in all variants.")
w()
w("Windows: clean 2008-05-30..2026-05-22, stress 1999-03-10..2026-05-22. "
  "Costs 10bps/side. Excess Sharpe vs SHV.")
w()

# Section 1
w()
w("## 1. Performance: CPM standalone and 60/40 blend")
w()
for wname, title in [("clean", "Clean window"), ("stress", "Stress window")]:
    w()
    w(f"### {title}")
    w()
    w("| Variant | Sleeve | Raw Sharpe | Excess Sharpe | CAGR | Vol | MaxDD | Calmar | Turnover/yr |")
    w("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for v in VARIANTS:
        w(perf_line(v, wname, "cpm"))
        w(perf_line(v, wname, "blend"))

# Section 2 calendar
w()
w("## 2. Crisis / calendar returns (60/40 blend)")
w()
w("| Variant | 2008 (stress) | 2020 (stress) | 2022 (clean) | 2020 (clean) |")
w("| --- | --- | --- | --- | --- |")
for v in VARIANTS:
    b_clean = daily_blend[(v, "clean")]
    b_stress = daily_blend[(v, "stress")]
    r2008 = cal_ret(b_stress, "2008", "2008")
    r2020s = cal_ret(b_stress, "2020", "2020")
    r2022 = cal_ret(b_clean, "2022", "2022")
    r2020c = cal_ret(b_clean, "2020", "2020")
    w(f"| {LABEL[v]} | {r2008*100:.2f}% | {r2020s*100:.2f}% | "
      f"{r2022*100:.2f}% | {r2020c*100:.2f}% |")
w()
w("(2020 appears in both windows; clean window starts 2008 so 2020 is present "
  "in both. Shown twice as a consistency cross-check.)")

# Section 3: gating activity
w()
w("## 3. Vol-gate activity diagnostic")
w()
for wname, title in [("clean", "Clean window"), ("stress", "Stress window")]:
    w()
    w(f"### {title}")
    w()
    w("`fired` = vol signal triggered. `gated` = signal triggered AND base CPM "
      "had risky exposure to cut (so the overlay actually changed weights).")
    w()
    w("| Variant | months | fired (signal) | % fired | gated (effective) | % gated |")
    w("| --- | --- | --- | --- | --- | --- |")
    for v in VARIANTS:
        if v == "V0":
            continue
        d = diags[(v, wname)]
        nfired = int(d["fired"].sum())
        ngated = int(d["gated"].sum())
        ntot = len(d)
        w(f"| {LABEL[v]} | {ntot} | {nfired} | {nfired/ntot*100:.1f}% | "
          f"{ngated} | {ngated/ntot*100:.1f}% |")

# Section 4: COHORT study (forward 1mo CPM return + forward vol)
w()
w("## 4. COHORT diagnostic (Moreira-Muir variance-reduction test)")
w()
w("For months the vol gate fires, the forward 1-calendar-month return of the "
  "V0 (ungated) CPM book is split into **bad-forward** (fwd <= 0, gate correct / "
  "true positive) vs **good-forward** (fwd > 0, false positive), with mean + "
  "forward realized vol (annualized daily-return std within the forward month) "
  "for each cohort. Key question: is the gated cohort genuinely higher-vol "
  "(the variance-reduction value) even if direction is near-symmetric?")
w()

def forward_month_stats(cpm_daily: pd.Series, sig_d: pd.Timestamp):
    """Return (fwd_ret, fwd_vol_ann) for the calendar month after sig_d."""
    nxt_start = (sig_d + pd.offsets.MonthBegin(1))
    nxt_end = nxt_start + pd.offsets.MonthEnd(0)
    seg = cpm_daily.loc[nxt_start:nxt_end]
    if len(seg) < 2:
        return np.nan, np.nan
    fwd_ret = float((1.0 + seg).prod() - 1.0)
    fwd_vol = float(seg.std() * np.sqrt(252))
    return fwd_ret, fwd_vol

# Use the per-window signal diag for fired months; forward stats from V0 cpm book
for wname, title in [("clean", "Clean window"), ("stress", "Stress window")]:
    # the signal that defines fired months: use each gate variant. Cohort is
    # most meaningful for the SPY and book signals separately.
    for sigvar, signame in [("V_rvspy_bin", "SIG-RV-SPY"), ("V_rvbook_bin", "SIG-RV-BOOK")]:
        d = diags[(sigvar, wname)]
        cpm0 = cpm_v0[wname]
        rows = []
        all_fwd = []
        for sd in d.index:
            fr, fv = forward_month_stats(cpm0, sd)
            if np.isnan(fr):
                continue
            all_fwd.append((fr, fv))
            if bool(d.loc[sd, "fired"]):
                rows.append((sd, fr, fv))
        if not rows:
            continue
        fired = pd.DataFrame(rows, columns=["sig_d", "fwd", "fvol"])
        allf = pd.DataFrame(all_fwd, columns=["fwd", "fvol"])
        bad = fired[fired["fwd"] <= 0]
        good = fired[fired["fwd"] > 0]
        w()
        w(f"### {title} - {signame} fired-month cohorts")
        w()
        w(f"Total evaluated months: {len(allf)}. Fired months: {len(fired)} "
          f"({len(fired)/len(allf)*100:.1f}%). "
          f"Unconditional mean fwd CPM return: {allf['fwd'].mean()*100:.2f}%, "
          f"unconditional mean fwd vol: {allf['fvol'].mean()*100:.2f}%.")
        w()
        w("| Cohort | Count | % of fired | Mean fwd CPM ret | Median | Mean fwd vol (ann) | Median fwd vol |")
        w("| --- | --- | --- | --- | --- | --- | --- |")
        def coh_row(name, df):
            if len(df) == 0:
                return f"| {name} | 0 | - | - | - | - | - |"
            return (f"| {name} | {len(df)} | {len(df)/len(fired)*100:.1f}% | "
                    f"{df['fwd'].mean()*100:+.2f}% | {df['fwd'].median()*100:+.2f}% | "
                    f"{df['fvol'].mean()*100:.2f}% | {df['fvol'].median()*100:.2f}% |")
        w(coh_row("bad-forward (TP)", bad))
        w(coh_row("good-forward (FP)", good))
        w(coh_row("ALL FIRED", fired))
        w()
        # Variance-reduction verdict
        if len(fired) > 0:
            fired_vol = fired["fvol"].mean()
            uncond_vol = allf["fvol"].mean()
            w(f"Fired-cohort mean fwd vol {fired_vol*100:.2f}% vs unconditional "
              f"{uncond_vol*100:.2f}% -> "
              f"{'HIGHER (variance-reduction value present)' if fired_vol > uncond_vol else 'NOT higher (no variance-reduction value)'}.")

# Section 5: redundancy with canary
w()
w("## 5. Redundancy with existing HYG-OR-TIP canary + partial-safe")
w()
w("For each gate variant, of the months the vol SIGNAL fires, how many had the "
  "canary ALREADY off / partial under production rules (`base_regime` != "
  "RISK_ON or `risky_base` < 1 -> overlap, gate adds nothing new) vs months the "
  "canary was fully RISK_ON that the vol gate newly de-risks (NEW risk-off the "
  "canary missed). The NEW column is where a vol gate could add value beyond the "
  "canary.")
w()
for wname, title in [("clean", "Clean window"), ("stress", "Stress window")]:
    w()
    w(f"### {title}")
    w()
    w("| Variant | months fired | canary already off/partial (overlap) | canary RISK_ON, vol newly cuts (NEW) |")
    w("| --- | --- | --- | --- |")
    for v in VARIANTS:
        if v == "V0":
            continue
        d = diags[(v, wname)]
        fired = d[d["fired"]]
        overlap = int((fired["risky_base"] < 0.999).sum())
        newcut = int((fired["risky_base"] >= 0.999).sum())
        w(f"| {LABEL[v]} | {len(fired)} | {overlap} | {newcut} |")

# Section 5b: 2020 specific
w()
w("### Does the vol gate specifically help 2020 (canary blind spot)?")
w()
w("Fired months during 2020 (signal dates), with base CPM regime under "
  "production rules (DEFENSIVE = canary already off):")
w()
for v in ["V_rvspy_bin", "V_rvbook_bin"]:
    d = diags[(v, "clean")]
    d2020 = d[(d.index >= "2019-12-01") & (d.index <= "2020-12-31")]
    fired2020 = d2020[d2020["fired"]]
    w(f"- **{LABEL[v]}**: fired on "
      + (", ".join(f"{ix.date()}({d2020.loc[ix,'base_regime']})" for ix in fired2020.index)
         if len(fired2020) else "no months")
      + ".")
w()

# Section 6: verdict
w()
w("## 6. Verdict")
w()
v0c = results[("V0", "clean", "blend")]
w(f"Baseline V0 (clean blend): Sharpe {v0c['sharpe']:.3f}, CAGR "
  f"{v0c['cagr']*100:.2f}%, MaxDD {v0c['max_drawdown']*100:.2f}%, "
  f"Calmar {v0c['calmar']:.2f}.")
w()
for v in VARIANTS:
    if v == "V0":
        continue
    m = results[(v, "clean", "blend")]
    dS = m['sharpe'] - v0c['sharpe']
    dMDD = m['max_drawdown'] - v0c['max_drawdown']
    dC = m['calmar'] - v0c['calmar']
    dCAGR = m['cagr'] - v0c['cagr']
    w(f"- **{LABEL[v]}** (clean blend): Sharpe {m['sharpe']:.3f} ({dS:+.3f}), "
      f"MaxDD {m['max_drawdown']*100:.2f}% ({dMDD*100:+.2f}pp), "
      f"Calmar {m['calmar']:.2f} ({dC:+.2f}), "
      f"CAGR {m['cagr']*100:.2f}% ({dCAGR*100:+.2f}pp).")
w()
w()
w("### Synthesis")
w()
w("**1. Does a CPM vol gate improve crisis DD / Calmar beyond V0 after cost?** "
  "Only marginally, and only the continuous action. Binary risk-off is "
  "strictly bad: SPY-RV binary costs -1.59pp CAGR and -0.080 Sharpe; book-RV "
  "binary is worse (-3.70pp CAGR, -0.198 Sharpe, Calmar 0.94 << 1.38) because "
  "forcing 100% safe at every RV crossover sells the diversified CPM book at "
  "local vol peaks and buys back higher. The continuous action is roughly "
  "break-even: SPY-RV cont clean blend Sharpe 1.354 (+0.007), MaxDD -9.22% "
  "(0.60pp shallower), Calmar 1.43 (+0.05), at -0.36pp CAGR; book-RV cont is "
  "similar (Calmar 1.43, MaxDD -8.88%) but -0.90pp CAGR and -0.036 Sharpe. The "
  "DD/Calmar gains are inside noise and bought with a return give-up.")
w()
w("**2. Is the value variance-reduction (high-vol cohort) like the BULL RV "
  "gate, or redundant?** The Moreira-Muir variance-reduction thesis that "
  "justifies the BULL RV gate does NOT carry over to the SPY-RV signal on CPM. "
  "For SIG-RV-SPY the fired-month forward CPM vol (9.38% clean / 9.98% stress) "
  "is NOT higher than unconditional (9.88% / 10.07%) - SPY's vol regime does "
  "not predict the forward variance of the diversified, min-var-pair CPM book. "
  "On BULL the same gate produced a ~21% fired-cohort fwd vol vs ~12% "
  "false-positive split; on CPM that asymmetry is absent. The book-RV signal "
  "(RV of the CPM book itself) DOES select a genuinely higher-vol cohort "
  "(10.87% vs 9.88% clean; 11.45% vs 10.07% stress) - it is a real variance "
  "selector - but direction is near-symmetric (~63% false-positive, fired-month "
  "mean fwd return still +1.1%), so the binary action that would harvest the "
  "variance reduction simultaneously forfeits too much positive carry.")
w()
w("**3. Redundancy with the HYG-OR-TIP canary, and does it help 2020?** The vol "
  "gate is mostly NON-redundant in timing: most fired months occur while the "
  "canary is still RISK_ON (see section 5 NEW column), and it does fire during "
  "the 2020 canary blind spot (SPY-RV fired Jan-Apr 2020 with base RISK_ON). "
  "BUT firing in 2020 did not help the outcome: full-year 2020 blend return "
  "FALLS from 23.42% (V0) to 21.4% (cont) / 20.8% (binary), because the gate "
  "exits into the crash and misses the sharp V-recovery. So it adds new "
  "risk-off months the canary misses, but those months are not net-beneficial.")
w()
w("**4. Design-philosophy cost.** A vol gate injects a fast/daily RV crossover "
  "into a sleeve that is otherwise monthly-simple (month-end signal, monthly "
  "rebalance). It adds a second timescale, raises turnover substantially "
  "(binary ~458-625%/yr vs V0 311%; continuous ~348-402%), and couples CPM to "
  "a daily-vol estimate - all for a sub-noise Calmar bump.")
w()
w("**Verdict: REJECT.** No vol-gate variant clears the bar of a meaningful, "
  "after-cost crisis-DD/Calmar improvement over V0. The only non-negative "
  "option (SPY-RV continuous) delivers +0.007 Sharpe / +0.05 Calmar - within "
  "noise - while the BULL-style variance-reduction rationale fails to transfer "
  "to the diversified CPM book (SPY-RV fired cohort is not higher-vol). The "
  "book-RV signal is a genuine variance selector but is direction-symmetric and "
  "only usable via the return-destroying binary action. The gate does catch the "
  "2020 canary blind spot in timing, but the trade is net-negative there "
  "(misses the recovery). Recommended form if ever revisited: continuous "
  "SPY-RV scale only, but not worth the added daily-signal complexity on a "
  "monthly-simple sleeve. Keep CPM as-is (canary-only, no vol gate).")
w()

out = Path(__file__).resolve().parent / "cpm_vol_gate_findings.md"
out.write_text("\n".join(L) + "\n")
print(f"Wrote {out} ({len(L)} lines)")
