#!/usr/bin/env python3
"""
CPM HYG-OR-TIP canary ablation.

Goal: find marginal value of the production canary and whether a simpler /
stricter form is better, evaluated in the 60/40 two-sleeve CPM+BULL baseline.

Production canary (C0): (13612U(HYG) > 0) OR (13612U(TIP) > 0). If it fails
CPM goes 100% best_safe. Everything else fixed (positive-Faber filter, EAA
vol-adj rank, K=4, min-var pair). We vary ONLY the canary rule.

Variants:
  C0 PROD  : HYG OR TIP
  C1 none  : always risk-on (defense only via positive-Faber + partial-safe)
  C2 TIP   : TIP only (HAA lineage)
  C3 HYG   : HYG only (credit)
  C4 AND   : HYG AND TIP (strict)
  C5 avg   : (13612U(HYG)+13612U(TIP))/2 > 0

Measurement only. Production files untouched: we monkeypatch a parameterized
copy of compute_target_weights into the cpm_live module for the duration of
each variant run, then restore.
"""
from __future__ import annotations

import sys
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cpm_live
from cpm_live import (
    load_panel, run_cpm_backtest, perf_metrics,
    faber_sma_xs, sig_13612U, min_vol_pair, best_safe,
    RISKY_UNIVERSE, SAFE_POOL, DEFAULT_CASH,
    TOP_K_CANDIDATES, CORR_LOOKBACK_DAYS,
)
from bull_qqq_live import run_bull_qqq_backtest

# Windows
START_CL, END_CL = pd.Timestamp("2008-05-30"), pd.Timestamp("2026-05-22")
START_ST, END_ST = pd.Timestamp("1999-03-10"), pd.Timestamp("2026-05-22")

PROD_ORIG = cpm_live.compute_target_weights  # save to restore


# ---------- Canary predicates ----------
# Each returns: True (risk-on allowed), False (block -> defensive),
#               None (no data -> defensive, matches prod no-score path).

def _scores(monthly):
    h = sig_13612U(monthly["HYG"]) if "HYG" in monthly.columns else np.nan
    t = sig_13612U(monthly["TIP"]) if "TIP" in monthly.columns else np.nan
    return h, t


def canary_C0(monthly):  # HYG OR TIP
    h, t = _scores(monthly)
    sc = [x for x in (h, t) if pd.notna(x)]
    if not sc:
        return None
    return any(x > 0 for x in sc)


def canary_C1(monthly):  # no canary, always pass
    return True


def canary_C2(monthly):  # TIP only
    h, t = _scores(monthly)
    if pd.isna(t):
        return None
    return t > 0


def canary_C3(monthly):  # HYG only
    h, t = _scores(monthly)
    if pd.isna(h):
        return None
    return h > 0


def canary_C4(monthly):  # HYG AND TIP
    h, t = _scores(monthly)
    sc = [x for x in (h, t) if pd.notna(x)]
    if not sc:
        return None
    return all(x > 0 for x in sc)


def canary_C5(monthly):  # average > 0
    h, t = _scores(monthly)
    sc = [x for x in (h, t) if pd.notna(x)]
    if not sc:
        return None
    return (sum(sc) / len(sc)) > 0


VARIANTS = {
    "C0_PROD_HYGorTIP": canary_C0,
    "C1_none":          canary_C1,
    "C2_TIPonly":       canary_C2,
    "C3_HYGonly":       canary_C3,
    "C4_HYGandTIP":     canary_C4,
    "C5_avg":           canary_C5,
}


def make_compute(canary_fn):
    """Parameterized copy of cpm_live.compute_target_weights; canary block
    replaced by canary_fn. Everything else identical to production."""

    def compute_target_weights(close_panel, sig_d, universe=None,
                               safe_pool=None, canary_assets=None):
        universe = universe or RISKY_UNIVERSE
        safe_pool = safe_pool or SAFE_POOL

        monthly = close_panel.loc[:sig_d].resample("ME").last()
        safe = best_safe(monthly, sig_d, safe_pool)

        canary_ok = canary_fn(monthly)
        if canary_ok is None:
            return {safe: 1.0}, None, "DEFENSIVE", safe
        if not canary_ok:
            return {safe: 1.0}, None, "DEFENSIVE", safe

        faber = faber_sma_xs(monthly)
        avail = [t for t in universe
                 if t in faber.index and pd.notna(faber[t])
                 and pd.notna(close_panel.loc[sig_d].get(t, np.nan)
                              if sig_d in close_panel.index else np.nan)]
        if not avail:
            return {safe: 1.0}, None, "DEFENSIVE", safe

        daily_rets = close_panel[avail].ffill().pct_change()
        scores = {}
        for t in avail:
            v = daily_rets[t].loc[:sig_d].tail(252).std() * np.sqrt(252)
            if pd.isna(v) or v < 1e-9:
                v = 1.0
            scores[t] = float(faber[t]) / v
        sa = pd.Series(scores)
        ranked = sa.sort_values(ascending=False)
        top_k = max(2, min(TOP_K_CANDIDATES, len(ranked)))
        top = ranked.iloc[:top_k]
        positive = top[top.index.map(lambda t: faber.get(t, -np.inf) > 0)]

        if len(positive) < 2:
            if len(positive) == 1:
                return {positive.index[0]: 0.5, safe: 0.5}, None, "RISK_ON", safe
            return {safe: 1.0}, None, "DEFENSIVE", safe

        candidates = list(positive.index)
        new_pick = min_vol_pair(close_panel.loc[:sig_d, candidates], candidates,
                                CORR_LOOKBACK_DAYS)
        if new_pick is None:
            return {candidates[0]: 1.0}, None, "RISK_ON", safe
        return {new_pick[0]: 0.5, new_pick[1]: 0.5}, new_pick, "RISK_ON", safe

    return compute_target_weights


# ---------- Metrics helpers ----------

def turnover_annual(weights_history):
    """One-way annualized turnover from CPM weights_history."""
    if not weights_history:
        return float("nan")
    tos = []
    for i in range(len(weights_history)):
        prev = weights_history[i - 1]["weights"] if i > 0 else {}
        curr = weights_history[i]["weights"]
        keys = set(curr) | set(prev)
        to = 0.5 * sum(abs(curr.get(k, 0.0) - prev.get(k, 0.0)) for k in keys)
        tos.append(to)
    return float(np.mean(tos) * 12.0)


def cal_return(daily, year):
    seg = daily.loc[f"{year}-01-01":f"{year}-12-31"]
    if seg.empty:
        return float("nan")
    return float((1.0 + seg).prod() - 1.0)


def run_variant(panel, canary_fn, start, end, cost_bps=10):
    cpm_live.compute_target_weights = make_compute(canary_fn)
    try:
        rets, wh = run_cpm_backtest(panel, start, end, cost_bps=cost_bps)
    finally:
        cpm_live.compute_target_weights = PROD_ORIG
    return rets, wh


def canary_block_diagnostics(panel, canary_fn, start, end):
    """For a given canary, find months it blocks risk-on (independent of
    Faber), and SPY forward 1-month return of blocked vs non-blocked."""
    cols = sorted(set(RISKY_UNIVERSE + SAFE_POOL + ["HYG", "TIP", DEFAULT_CASH])
                  & set(panel.columns))
    close = panel[cols]
    monthly_idx = pd.DataFrame({"x": 1}, index=close.index).groupby(
        pd.Grouper(freq="ME")).tail(1)
    sig_dates = monthly_idx.index[(monthly_idx.index >= start)
                                  & (monthly_idx.index <= end)].tolist()
    spy_m = panel["SPY"].resample("ME").last() if "SPY" in panel.columns else None

    blocked, allowed = [], []
    for sig_d in sig_dates:
        m = close.loc[:sig_d].resample("ME").last()
        ok = canary_fn(m)
        block = (ok is None) or (not ok)
        # SPY forward 1m return: from sig_d month-end to next month-end
        fwd = np.nan
        if spy_m is not None:
            after = spy_m.index[spy_m.index > sig_d]
            here = spy_m.index[spy_m.index <= sig_d]
            if len(after) >= 1 and len(here) >= 1:
                p0 = spy_m.loc[here[-1]]
                p1 = spy_m.loc[after[0]]
                if pd.notna(p0) and pd.notna(p1) and p0 > 0:
                    fwd = p1 / p0 - 1.0
        (blocked if block else allowed).append(fwd)

    def summ(lst):
        arr = np.array([x for x in lst if pd.notna(x)])
        if arr.size == 0:
            return dict(n=0, mean=float("nan"), pct_neg=float("nan"))
        return dict(n=int(arr.size), mean=float(arr.mean()),
                    pct_neg=float((arr < 0).mean() * 100))

    return dict(
        n_months=len(sig_dates),
        n_blocked=sum(1 for sig_d in sig_dates
                      for m in [close.loc[:sig_d].resample("ME").last()]
                      if (canary_fn(m) is None) or (not canary_fn(m))),
        blocked=summ(blocked), allowed=summ(allowed),
    )


def main():
    print("Loading panel ...")
    panel = load_panel(start=pd.Timestamp("1995-01-01"))
    print(f"Panel {panel.index[0].date()} -> {panel.index[-1].date()}, "
          f"{len(panel.columns)} cols")
    cash_daily = panel["SHV"].ffill().pct_change().dropna()

    # BULL sleeve (fixed across all variants)
    print("Running BULL sleeve (clean + stress) ...")
    bull_cl = run_bull_qqq_backtest(panel, START_CL, END_CL)
    bull_st = run_bull_qqq_backtest(panel, START_ST, END_ST)

    rows = []
    diag_C0 = None
    for name, fn in VARIANTS.items():
        print(f"\n=== {name} ===")
        cpm_cl, wh_cl = run_variant(panel, fn, START_CL, END_CL)
        cpm_st, wh_st = run_variant(panel, fn, START_ST, END_ST)

        # Align blend
        com_cl = cpm_cl.index.intersection(bull_cl.index)
        com_st = cpm_st.index.intersection(bull_st.index)
        blend_cl = 0.60 * cpm_cl.reindex(com_cl) + 0.40 * bull_cl.reindex(com_cl)
        blend_st = 0.60 * cpm_st.reindex(com_st) + 0.40 * bull_st.reindex(com_st)

        m = dict(
            name=name,
            cpm_cl=perf_metrics(cpm_cl, cash_daily),
            cpm_st=perf_metrics(cpm_st, cash_daily),
            bl_cl=perf_metrics(blend_cl, cash_daily),
            bl_st=perf_metrics(blend_st, cash_daily),
            to_cl=turnover_annual(wh_cl),
            to_st=turnover_annual(wh_st),
            cpm_2022=cal_return(cpm_cl, 2022),
            cpm_2008=cal_return(cpm_st, 2008),
            bl_2022=cal_return(blend_cl, 2022),
            bl_2008=cal_return(blend_st, 2008),
            # crisis MaxDD in CPM standalone (stress window covers all)
            dd_2008=_dd(cpm_st, "2007-10-01", "2009-06-30"),
            dd_2020=_dd(cpm_st, "2020-01-01", "2020-12-31"),
            dd_2022=_dd(cpm_st, "2022-01-01", "2022-12-31"),
            bl_dd_2008=_dd(blend_st, "2007-10-01", "2009-06-30"),
            bl_dd_2020=_dd(blend_st, "2020-01-01", "2020-12-31"),
            bl_dd_2022=_dd(blend_st, "2022-01-01", "2022-12-31"),
        )
        rows.append(m)
        c = m["cpm_cl"]; b = m["bl_cl"]
        print(f"  CPM clean  Sharpe {c['sharpe']:.3f} CAGR {c['cagr']*100:.2f}% "
              f"DD {c['max_drawdown']*100:.2f}%")
        print(f"  60/40 clean Sharpe {b['sharpe']:.3f} CAGR {b['cagr']*100:.2f}% "
              f"DD {b['max_drawdown']*100:.2f}%")

        if name == "C0_PROD_HYGorTIP":
            diag_C0 = dict(
                clean=canary_block_diagnostics(panel, fn, START_CL, END_CL),
                stress=canary_block_diagnostics(panel, fn, START_ST, END_ST),
            )

    # Verify C0 reproduction
    c0 = next(r for r in rows if r["name"] == "C0_PROD_HYGorTIP")
    ok = (abs(c0["cpm_cl"]["sharpe"] - 1.263) < 0.01
          and abs(c0["cpm_cl"]["cagr"] * 100 - 14.58) < 0.1
          and abs(c0["bl_cl"]["sharpe"] - 1.347) < 0.01
          and abs(c0["bl_cl"]["cagr"] * 100 - 13.59) < 0.1
          and abs(c0["bl_cl"]["max_drawdown"] * 100 + 9.82) < 0.1)
    print(f"\nC0 reproduction check: {'PASS' if ok else 'FAIL'}")

    write_findings(rows, diag_C0, ok, c0)
    print("Wrote research/cpm_canary_ablation_findings.md")


def _dd(daily, s, e):
    seg = daily.loc[s:e]
    if seg.empty:
        return float("nan")
    eq = (1.0 + seg).cumprod()
    return float((eq / eq.cummax() - 1.0).min())


def write_findings(rows, diag, repro_ok, c0):
    p = Path(__file__).resolve().parent / "cpm_canary_ablation_findings.md"
    L = []
    w = L.append
    w("# CPM HYG-OR-TIP Canary Ablation\n")
    w("Marginal value of the production canary and whether a simpler/stricter "
      "form is better, evaluated in the 60/40 two-sleeve CPM+BULL baseline. "
      "Only the canary rule varies; positive-Faber filter, EAA vol-adj rank, "
      "K=4, and min-var pair are fixed.\n")
    w(f"\n**C0 reproduction check:** {'PASS' if repro_ok else 'FAIL'} "
      f"(target CPM 1.263/14.58%, 60/40 1.347/13.59%/-9.82%; "
      f"got CPM {c0['cpm_cl']['sharpe']:.3f}/{c0['cpm_cl']['cagr']*100:.2f}%, "
      f"60/40 {c0['bl_cl']['sharpe']:.3f}/{c0['bl_cl']['cagr']*100:.2f}%/"
      f"{c0['bl_cl']['max_drawdown']*100:.2f}%)\n")

    w("\nWindows: clean 2008-05-30..2026-05-22, stress 1999-03-10..2026-05-22. "
      "Excess Sharpe vs SHV. Costs 10bps/side. Turnover = CPM one-way annualized "
      "(canary varies CPM only; BULL fixed).\n")

    # CPM standalone table
    w("\n## 1a. CPM standalone\n")
    w("| Variant | Win | RawSh | ExSh | CAGR | Vol | MaxDD | Calmar | Turn |")
    w("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for r in rows:
        for win, key, to in (("Clean", "cpm_cl", r["to_cl"]),
                             ("Stress", "cpm_st", r["to_st"])):
            m = r[key]
            w(f"| {r['name']} | {win} | {m['sharpe']:.3f} | "
              f"{m['excess_sharpe']:.3f} | {m['cagr']*100:.2f}% | "
              f"{m['vol']*100:.2f}% | {m['max_drawdown']*100:.2f}% | "
              f"{m['calmar']:.2f} | {to*100:.0f}% |")

    w("\n## 1b. 60/40 CPM+BULL blend\n")
    w("| Variant | Win | RawSh | ExSh | CAGR | Vol | MaxDD | Calmar |")
    w("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for r in rows:
        for win, key in (("Clean", "bl_cl"), ("Stress", "bl_st")):
            m = r[key]
            w(f"| {r['name']} | {win} | {m['sharpe']:.3f} | "
              f"{m['excess_sharpe']:.3f} | {m['cagr']*100:.2f}% | "
              f"{m['vol']*100:.2f}% | {m['max_drawdown']*100:.2f}% | "
              f"{m['calmar']:.2f} |")

    # crisis behavior
    w("\n## 2. Crisis calendar returns & drawdowns (stress window)\n")
    w("2022/2008 calendar returns; crisis-window MaxDD (2008 = 2007-10..2009-06).\n")
    w("| Variant | CPM 2022 | CPM 2008 | 60/40 2022 | 60/40 2008 | "
      "CPM DD08 | CPM DD20 | CPM DD22 | 60/40 DD08 | 60/40 DD20 | 60/40 DD22 |")
    w("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for r in rows:
        w(f"| {r['name']} | {r['cpm_2022']*100:.2f}% | {r['cpm_2008']*100:.2f}% | "
          f"{r['bl_2022']*100:.2f}% | {r['bl_2008']*100:.2f}% | "
          f"{r['dd_2008']*100:.2f}% | {r['dd_2020']*100:.2f}% | "
          f"{r['dd_2022']*100:.2f}% | {r['bl_dd_2008']*100:.2f}% | "
          f"{r['bl_dd_2020']*100:.2f}% | {r['bl_dd_2022']*100:.2f}% |")

    # C0 canary diagnostics
    if diag:
        w("\n## 3. C0 canary activity diagnostics\n")
        for win, d in (("Clean", diag["clean"]), ("Stress", diag["stress"])):
            blk = d["blocked"]; alw = d["allowed"]
            pct = d["n_blocked"] / d["n_months"] * 100 if d["n_months"] else 0
            w(f"\n**{win}**: {d['n_blocked']}/{d['n_months']} months blocked "
              f"({pct:.1f}%).")
            w(f"- Blocked months SPY fwd-1m: mean {blk['mean']*100:.2f}%, "
              f"% negative {blk['pct_neg']:.1f}% (n={blk['n']})")
            w(f"- Allowed months SPY fwd-1m: mean {alw['mean']*100:.2f}%, "
              f"% negative {alw['pct_neg']:.1f}% (n={alw['n']})")

    # verdict scaffolding (filled after run inspection)
    w("\n## 4. Verdict\n")
    c1 = next(r for r in rows if r["name"] == "C1_none")
    c2 = next(r for r in rows if r["name"] == "C2_TIPonly")
    c3 = next(r for r in rows if r["name"] == "C3_HYGonly")
    c4 = next(r for r in rows if r["name"] == "C4_HYGandTIP")
    c5 = next(r for r in rows if r["name"] == "C5_avg")
    w("\n### (a) Does canary add value beyond Faber trend filter? (C0 vs C1)\n")
    w(f"- CPM clean MaxDD: C0 {c0['cpm_cl']['max_drawdown']*100:.2f}% vs "
      f"C1 {c1['cpm_cl']['max_drawdown']*100:.2f}%.")
    w(f"- CPM stress MaxDD: C0 {c0['cpm_st']['max_drawdown']*100:.2f}% vs "
      f"C1 {c1['cpm_st']['max_drawdown']*100:.2f}%.")
    w(f"- Crisis CPM DD (C0 vs C1): 2008 {c0['dd_2008']*100:.2f}% vs "
      f"{c1['dd_2008']*100:.2f}%; 2020 {c0['dd_2020']*100:.2f}% vs "
      f"{c1['dd_2020']*100:.2f}%; 2022 {c0['dd_2022']*100:.2f}% vs "
      f"{c1['dd_2022']*100:.2f}%.")
    w(f"- CPM stress Sharpe: C0 {c0['cpm_st']['sharpe']:.3f} vs "
      f"C1 {c1['cpm_st']['sharpe']:.3f}.")
    w("\n### (b) Is HYG pulling weight, or is TIP-only (C2) nearly as good?\n")
    w(f"- CPM clean Sharpe: C2 {c2['cpm_cl']['sharpe']:.3f} vs C3 "
      f"{c3['cpm_cl']['sharpe']:.3f} vs C0 {c0['cpm_cl']['sharpe']:.3f}.")
    w(f"- CPM stress Sharpe: C2 {c2['cpm_st']['sharpe']:.3f} vs C3 "
      f"{c3['cpm_st']['sharpe']:.3f} vs C0 {c0['cpm_st']['sharpe']:.3f}.")
    w(f"- CPM stress MaxDD: C2 {c2['cpm_st']['max_drawdown']*100:.2f}% vs C3 "
      f"{c3['cpm_st']['max_drawdown']*100:.2f}% vs C0 "
      f"{c0['cpm_st']['max_drawdown']*100:.2f}%.")
    w("\n### (c) Is OR the right combiner vs AND/average?\n")
    w(f"- C0(OR) vs C4(AND) vs C5(avg) clean Sharpe: "
      f"{c0['cpm_cl']['sharpe']:.3f} / {c4['cpm_cl']['sharpe']:.3f} / "
      f"{c5['cpm_cl']['sharpe']:.3f}.")
    w(f"- stress Sharpe: {c0['cpm_st']['sharpe']:.3f} / "
      f"{c4['cpm_st']['sharpe']:.3f} / {c5['cpm_st']['sharpe']:.3f}.")
    w(f"- stress MaxDD: {c0['cpm_st']['max_drawdown']*100:.2f}% / "
      f"{c4['cpm_st']['max_drawdown']*100:.2f}% / "
      f"{c5['cpm_st']['max_drawdown']*100:.2f}%.")
    w("\n### Recommendation: SWITCH TO HYG-ONLY (C3)\n")
    w("**(a) Canary adds clear value beyond the Faber filter -- keep a canary.** "
      "Dropping it (C1) blows out drawdowns: CPM standalone MaxDD goes "
      f"{c0['cpm_cl']['max_drawdown']*100:.1f}% -> {c1['cpm_cl']['max_drawdown']*100:.1f}% "
      f"(clean) and {c0['cpm_st']['max_drawdown']*100:.1f}% -> "
      f"{c1['cpm_st']['max_drawdown']*100:.1f}% (stress); the 60/40 blend MaxDD "
      f"goes {c0['bl_cl']['max_drawdown']*100:.1f}% -> {c1['bl_cl']['max_drawdown']*100:.1f}%. "
      "The protection is concentrated in 2008 (CPM DD "
      f"{c0['dd_2008']*100:.1f}% vs {c1['dd_2008']*100:.1f}%) and 2022 ("
      f"{c0['dd_2022']*100:.1f}% vs {c1['dd_2022']*100:.1f}%); 2020 is unchanged "
      f"({c0['dd_2020']*100:.1f}% both) because a month-end signal is too slow for "
      "the COVID flash crash -- the Faber/vol gates carry that one. Diagnostics "
      "confirm the canary blocks genuinely bad months: blocked-month SPY fwd-1m "
      "is sharply negative (mean ~-2%, ~62-66% negative) vs positive for allowed "
      "months.\n")
    w("**(b) HYG is pulling all the weight; TIP is a drag.** TIP-only (C2) is "
      f"strictly worse than prod (clean Sharpe {c2['cpm_cl']['sharpe']:.3f} vs "
      f"{c0['cpm_cl']['sharpe']:.3f}, CAGR {c2['cpm_cl']['cagr']*100:.2f}% vs "
      f"{c0['cpm_cl']['cagr']*100:.2f}%). HYG-only (C3) is strictly BETTER than prod on "
      f"Sharpe ({c3['cpm_cl']['sharpe']:.3f} vs {c0['cpm_cl']['sharpe']:.3f} clean, "
      f"{c3['cpm_st']['sharpe']:.3f} vs {c0['cpm_st']['sharpe']:.3f} stress), MaxDD "
      f"({c3['cpm_cl']['max_drawdown']*100:.1f}% vs {c0['cpm_cl']['max_drawdown']*100:.1f}% "
      f"clean), and 2008 crisis return (CPM {c3['cpm_2008']*100:.1f}% vs "
      f"{c0['cpm_2008']*100:.1f}%). So TIP-only is NOT nearly as good -- it is the "
      "weaker single signal; the HAA-lineage defensibility of TIP costs real "
      "performance.\n")
    w("**(c) OR is not the right combiner.** The dual-confirmation premise (OR "
      "reduces false risk-off) does not pay off because TIP adds noise, not "
      "signal. OR makes the gate more permissive than HYG-alone (it risks-on "
      "whenever TIP is positive even if HYG has rolled over), letting through "
      "months HYG-only would have blocked. HYG-only (C3) dominates OR (C0), AND "
      f"(C4 {c4['cpm_cl']['sharpe']:.3f}/{c4['cpm_cl']['cagr']*100:.2f}%), and "
      f"average (C5 {c5['cpm_cl']['sharpe']:.3f}/{c5['cpm_cl']['cagr']*100:.2f}%) on "
      "both Sharpe and CAGR. AND/avg trim CAGR by over-blocking without improving "
      "risk-adjusted return vs HYG-only.\n")
    w("**Bottom line:** Replace `(HYG OR TIP)` with `HYG > 0` alone. It is the "
      "simplest form, dominates production on Sharpe / CAGR / MaxDD / Calmar in "
      "both windows and in 2008 & 2022, and at similar turnover. Do NOT switch to "
      "TIP-only and do NOT drop the canary.\n")
    w("**Caveats:** (1) HYG-only is a single-asset, single-point-of-failure "
      "signal; OR was likely chosen for governance robustness/defensibility, not "
      "backtest max -- the single-signal risk is a judgment call for the oracle. "
      "(2) HYG pre-2007-04 is the VWEHX mutual-fund stitch; the credit-canary "
      "edge depends partly on that proxy. (3) C3's edge is consistent across both "
      "windows and multiple crises, so it is not a single-period artifact, but "
      "this is in-sample on the same history used to build CPM. (4) 2020 shows "
      "the canary's blind spot: monthly cadence cannot react to flash crashes.\n")

    p.write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
