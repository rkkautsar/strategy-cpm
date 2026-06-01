#!/usr/bin/env python3
"""
CPM safe-rule isolation study.

Question: does CPM/BULL's best_safe timing (argmax 13612U over [SHV, IEF])
earn its keep vs simpler fixed safe rules, in the 60/40 two-sleeve CPM+BULL
baseline? Safe asset is SHARED by CPM and BULL, so the safe rule is varied
on BOTH sleeves consistently.

Variants (vary ONLY the safe-selection rule, everything else fixed):
  S0 (PROD): best of SHV/IEF by 13612U momentum.
  S1: SHV only.
  S2: IEF only.
  S3: 50/50 SHV+IEF (no timing).
  S4: best of SHV/IEF by 3-month return.
  S5: best of SHV/IEF by 12-month return.

Mechanism: monkeypatch cpm_live.best_safe and bull_spy_live._pick_safe with a
rule-specific selector. The 50/50 variant uses a synthetic daily-rebalanced
SHV+IEF blend column injected into the panel.

Windows: clean 2008-05-30..2026-05-22, stress 1999-03-10..2026-05-22.
Verify: S0 reproduces 60/40 baseline 1.347 / 13.59% / -9.82%.

Measurement only. No production files edited. Writes incremental findings.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cpm_live
import bull_spy_live
from cpm_live import load_panel, run_cpm_backtest, perf_metrics
from bull_spy_live import run_bull_spy_backtest, compute_bull_spy_weights

try:
    from ndx_sleeve_live import load_ndx_panel, run_ndx_backtest
    HAVE_NDX = True
except Exception:
    HAVE_NDX = False

CLEAN_START = pd.Timestamp("2008-05-30")
STRESS_START = pd.Timestamp("1999-03-10")
END = pd.Timestamp("2026-05-22")

W_CPM, W_BULL = 0.60, 0.40

FINDINGS = Path(__file__).resolve().parent / "cpm_safe_isolation_findings.md"

# Saved production callables (restored when running PROD-as-shipped path).
_PROD_BEST_SAFE = cpm_live.best_safe
_PROD_PICK_SAFE = bull_spy_live._pick_safe


# ---------- Safe-rule selectors ----------

def _safe_by(monthly: pd.DataFrame, kind: str) -> str:
    """Pick safe ticker for a monthly price frame sliced up to sig_d."""
    if kind == "SHV":
        return "SHV"
    if kind == "IEF":
        return "IEF"
    if kind == "BLEND5050":
        return "BLEND5050"
    pool = ["SHV", "IEF"]
    avail = [t for t in pool if t in monthly.columns
             and monthly[t].dropna().shape[0] >= 13]
    if not avail:
        return "SHV"
    best_t, best_m = avail[0], -np.inf
    for t in avail:
        s = monthly[t].dropna()
        last = s.iloc[-1]
        if kind == "13612":
            r1 = last / s.iloc[-2] - 1
            r3 = last / s.iloc[-4] - 1
            r6 = last / s.iloc[-7] - 1
            r12 = last / s.iloc[-13] - 1
            m = (r1 + r3 + r6 + r12) / 4.0
        elif kind == "3m":
            m = last / s.iloc[-4] - 1
        elif kind == "12m":
            m = last / s.iloc[-13] - 1
        else:
            raise ValueError(kind)
        if m > best_m:
            best_m, best_t = m, t
    return best_t


def patch_rule(kind: str):
    """Monkeypatch both sleeves' safe selection with the given rule."""
    cpm_live.best_safe = lambda monthly, sig_d, safe_pool, _k=kind: _safe_by(monthly, _k)
    bull_spy_live._pick_safe = lambda monthly, _k=kind: _safe_by(monthly, _k)


def restore_prod():
    cpm_live.best_safe = _PROD_BEST_SAFE
    bull_spy_live._pick_safe = _PROD_PICK_SAFE


# ---------- Turnover ----------

def blend_turnover(panel, start, end, w_cpm, w_bull):
    """Annual one-way turnover of the 60/40 blend, combining shared tickers
    (e.g. SHV/IEF held by both sleeves net out)."""
    cols = sorted(set(cpm_live.RISKY_UNIVERSE + cpm_live.SAFE_POOL
                      + cpm_live.CANARY_ASSETS + [cpm_live.DEFAULT_CASH])
                  & set(panel.columns))
    close = panel[cols]
    midx = pd.DataFrame({"x": 1}, index=close.index).groupby(pd.Grouper(freq="ME")).tail(1)
    sigs = midx.index[(midx.index >= start) & (midx.index <= end)].tolist()
    combined = []
    for sig_d in sigs:
        cw, _, _, _ = cpm_live.compute_target_weights(close, sig_d)
        bw, _, _ = compute_bull_spy_weights(panel, sig_d, panel["SPY"])
        cmb = {}
        for t, x in cw.items():
            cmb[t] = cmb.get(t, 0.0) + w_cpm * x
        for t, x in bw.items():
            cmb[t] = cmb.get(t, 0.0) + w_bull * x
        combined.append(cmb)
    if len(combined) < 2:
        return float("nan")
    tos = []
    for i in range(1, len(combined)):
        prev, curr = combined[i - 1], combined[i]
        keys = set(prev) | set(curr)
        to = 0.5 * sum(abs(curr.get(k, 0.0) - prev.get(k, 0.0)) for k in keys)
        tos.append(to)
    yrs = (sigs[-1] - sigs[0]).days / 365.25
    return float(np.sum(tos) / yrs) if yrs > 0 else float("nan")


# ---------- Metrics for a window ----------

def cal_year_return(daily, year):
    seg = daily.loc[f"{year}-01-01":f"{year}-12-31"]
    if seg.empty:
        return float("nan")
    return float((1.0 + seg).prod() - 1.0)


def run_window(panel, kind, start, end, cash_daily, w_cpm, w_bull, prod_path=False):
    _saved_pool = (cpm_live.SAFE_POOL, bull_spy_live.SAFE_POOL)
    if prod_path:
        restore_prod()
        # Use the real production pool (exclude synthetic BLEND5050) so the
        # baseline reproduction is bit-clean.
        cpm_live.SAFE_POOL = ["SHV", "IEF"]
        bull_spy_live.SAFE_POOL = ["SHV", "IEF"]
    else:
        patch_rule(kind)
    cpm, _ = run_cpm_backtest(panel, start, end)
    bull = run_bull_spy_backtest(panel, start, end)
    common = cpm.index.intersection(bull.index)
    cpm = cpm.reindex(common)
    bull = bull.reindex(common)
    blend = w_cpm * cpm + w_bull * bull
    mb = perf_metrics(blend, cash_daily)
    mc = perf_metrics(cpm, cash_daily)
    to = blend_turnover(panel, start, end, w_cpm, w_bull)
    if prod_path:
        cpm_live.SAFE_POOL, bull_spy_live.SAFE_POOL = _saved_pool
    return {
        "blend": mb, "cpm": mc, "blend_daily": blend, "cpm_daily": cpm,
        "turnover": to,
        "ret_2022": cal_year_return(blend, 2022),
        "ret_2008": cal_year_return(blend, 2008),
        "cpm_ret_2022": cal_year_return(cpm, 2022),
        "cpm_ret_2008": cal_year_return(cpm, 2008),
    }


# ---------- S0 timing diagnostic ----------

def s0_timing_diagnostic(panel, start, end):
    """For S0 (13612U timing), at each month-end determine each sleeve's safe
    pick when defensive, and the realized forward 1-month IEF-vs-SHV gap."""
    patch_rule("13612")
    cols = sorted(set(cpm_live.RISKY_UNIVERSE + cpm_live.SAFE_POOL
                      + cpm_live.CANARY_ASSETS + [cpm_live.DEFAULT_CASH])
                  & set(panel.columns))
    close = panel[cols]
    midx = pd.DataFrame({"x": 1}, index=close.index).groupby(pd.Grouper(freq="ME")).tail(1)
    sigs = midx.index[(midx.index >= start) & (midx.index <= end)].tolist()
    daily = panel.ffill().pct_change()

    recs = []
    for i, sig_d in enumerate(sigs):
        cw, _, cregime, csafe = cpm_live.compute_target_weights(close, sig_d)
        bw, bregime, _ = compute_bull_spy_weights(panel, sig_d, panel["SPY"])
        # CPM defensive if any safe-pool ticker in weights
        cpm_safe_w = sum(v for t, v in cw.items() if t in ("SHV", "IEF"))
        cpm_safe_pick = next((t for t in cw if t in ("SHV", "IEF")), None)
        bull_safe_w = sum(v for t, v in bw.items() if t in ("SHV", "IEF"))
        bull_safe_pick = next((t for t in bw if t in ("SHV", "IEF")), None)
        # forward 1-month realized SHV/IEF returns (apply_from -> next month-end+1)
        future = close.index[close.index > sig_d]
        if len(future) < 1:
            continue
        af = future[0]
        if i + 1 < len(sigs):
            nf = close.index[close.index > sigs[i + 1]]
            ea = nf[0] if len(nf) >= 1 else end
        else:
            ea = end
        seg = (daily.index >= af) & (daily.index < ea)
        shv_r = float((1.0 + daily.loc[seg, "SHV"].fillna(0.0)).prod() - 1.0)
        ief_r = float((1.0 + daily.loc[seg, "IEF"].fillna(0.0)).prod() - 1.0)
        recs.append({
            "sig_d": sig_d,
            "cpm_safe_w": cpm_safe_w, "cpm_safe_pick": cpm_safe_pick,
            "bull_safe_w": bull_safe_w, "bull_safe_pick": bull_safe_pick,
            "shv_fwd": shv_r, "ief_fwd": ief_r, "gap_ief_minus_shv": ief_r - shv_r,
        })
    return pd.DataFrame(recs)


# ---------- Main ----------

def main():
    print("Loading panel ...")
    panel = load_panel(start=pd.Timestamp("1995-01-01"), end=END)

    # Inject synthetic 50/50 SHV+IEF daily-rebalanced blend.
    shv = panel["SHV"].ffill()
    ief = panel["IEF"].ffill()
    ret = (0.5 * shv.pct_change() + 0.5 * ief.pct_change()).fillna(0.0)
    panel["BLEND5050"] = (1.0 + ret).cumprod() * 100.0

    # Ensure synthetic blend visible to cols filters in both sleeves.
    cpm_live.SAFE_POOL = ["SHV", "IEF", "BLEND5050"]
    bull_spy_live.SAFE_POOL = ["SHV", "IEF", "BLEND5050"]

    cash_daily = panel["SHV"].ffill().pct_change().dropna()

    print("Panel:", panel.index[0].date(), "->", panel.index[-1].date(),
          len(panel.columns), "cols")

    # ---- Verify S0 reproduces 60/40 baseline (production path, unpatched) ----
    print("Verifying S0 baseline (production path) ...")
    v0_prod = run_window(panel, "13612", CLEAN_START, END, cash_daily,
                         W_CPM, W_BULL, prod_path=True)
    s, c, d = v0_prod["blend"]["sharpe"], v0_prod["blend"]["cagr"], v0_prod["blend"]["max_drawdown"]
    print(f"  S0 PROD: Sharpe={s:.3f} CAGR={c*100:.2f}% MaxDD={d*100:.2f}%")
    ok = abs(s - 1.347) <= 0.01 and abs(c * 100 - 13.59) <= 0.1 and abs(d * 100 + 9.82) <= 0.15
    print("  baseline match:", ok)

    # Confirm patched 13612 rule == production path numerically.
    v0_patched = run_window(panel, "13612", CLEAN_START, END, cash_daily, W_CPM, W_BULL)
    match_patch = (abs(v0_patched["blend"]["sharpe"] - s) < 1e-9
                   and abs(v0_patched["blend"]["cagr"] - c) < 1e-9)
    print("  patched-13612 == prod:", match_patch)

    variants = [
        ("S0", "13612", "best of SHV/IEF by 13612U (PROD)"),
        ("S1", "SHV", "SHV only"),
        ("S2", "IEF", "IEF only"),
        ("S3", "BLEND5050", "50/50 SHV+IEF (no timing)"),
        ("S4", "3m", "best of SHV/IEF by 3-month return"),
        ("S5", "12m", "best of SHV/IEF by 12-month return"),
    ]

    results = {}
    for sid, kind, desc in variants:
        print(f"Running {sid} ({desc}) ...")
        rc = run_window(panel, kind, CLEAN_START, END, cash_daily, W_CPM, W_BULL)
        rs = run_window(panel, kind, STRESS_START, END, cash_daily, W_CPM, W_BULL)
        results[sid] = {"kind": kind, "desc": desc, "clean": rc, "stress": rs}

    print("Running S0 timing diagnostic ...")
    diag_clean = s0_timing_diagnostic(panel, CLEAN_START, END)
    diag_stress = s0_timing_diagnostic(panel, STRESS_START, END)

    write_findings(results, v0_prod, ok, match_patch, diag_clean, diag_stress)
    print("Wrote", FINDINGS)


def _row(sid, desc, win, r):
    m = r[win]["blend"]
    return (f"| {sid} ({desc}) | {win} | {m['cagr']*100:.2f}% | {m['vol']*100:.2f}% "
            f"| {m['sharpe']:.3f} | {m['excess_sharpe']:.3f} | {m['max_drawdown']*100:.2f}% "
            f"| {m['calmar']:.2f} | {r[win]['turnover']:.2f} "
            f"| {r[win]['ret_2022']*100:.2f}% | {r[win]['ret_2008']*100 if not np.isnan(r[win]['ret_2008']) else float('nan'):.2f}% |")


def write_findings(results, v0_prod, ok, match_patch, diag_clean, diag_stress):
    L = []
    A = L.append
    A("# CPM best_safe Timing Isolation (60/40 CPM+BULL two-sleeve)\n")
    A("Question: does CPM/BULL's `best_safe` timing (argmax 13612U over "
      "[SHV, IEF]) earn its keep vs simpler fixed safe rules? Safe asset is "
      "shared by CPM and BULL; the safe rule is varied on BOTH sleeves "
      "consistently.\n")
    A("Method: monkeypatch `cpm_live.best_safe` and `bull_spy_live._pick_safe` "
      "(measurement only, no production files edited). 50/50 uses a synthetic "
      "daily-rebalanced SHV+IEF blend column. Blend = 0.60*CPM + 0.40*BULL. "
      "Excess Sharpe vs SHV cash. Turnover = annual one-way, combined "
      "(shared SHV/IEF net out).\n")
    A(f"Windows: clean {CLEAN_START.date()}..{END.date()}, "
      f"stress {STRESS_START.date()}..{END.date()}.\n")
    s = v0_prod['blend']
    A("## Verification\n")
    A(f"S0 production path (60/40 clean): Sharpe **{s['sharpe']:.3f}** / "
      f"CAGR **{s['cagr']*100:.2f}%** / MaxDD **{s['max_drawdown']*100:.2f}%**. "
      f"Target 1.347 / 13.59% / -9.82%. Match: **{ok}**.\n")
    A(f"Patched 13612 rule reproduces production path exactly: **{match_patch}**.\n")

    A("## 1. 60/40 Blend Metrics (all variants)\n")
    A("| Variant | Window | CAGR | Vol | Raw Sharpe | Excess Sharpe | MaxDD | Calmar | Turnover (ann 1-way) | 2022 | 2008 |")
    A("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for sid in ["S0", "S1", "S2", "S3", "S4", "S5"]:
        r = results[sid]
        A(_row(sid, r["desc"], "clean", r))
        A(_row(sid, r["desc"], "stress", r))
    A("")
    A("Notes: 2008 calendar return only meaningful in stress window (clean "
      "window starts 2008-05-30, so 2008 figure is partial-year May-Dec). "
      "Turnover differs slightly across windows due to start date.\n")

    A("## 1b. CPM standalone (where it differs from blend)\n")
    A("| Variant | Window | CAGR | Vol | Raw Sharpe | Excess Sharpe | MaxDD | Calmar |")
    A("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for sid in ["S0", "S1", "S2", "S3", "S4", "S5"]:
        r = results[sid]
        for win in ["clean", "stress"]:
            m = r[win]["cpm"]
            A(f"| {sid} | {win} | {m['cagr']*100:.2f}% | {m['vol']*100:.2f}% "
              f"| {m['sharpe']:.3f} | {m['excess_sharpe']:.3f} "
              f"| {m['max_drawdown']*100:.2f}% | {m['calmar']:.2f} |")
    A("")

    # ---- Diagnostic ----
    A("## 2. S0 13612U Timing Diagnostic\n")
    for label, d in [("clean", diag_clean), ("stress", diag_stress)]:
        A(f"### {label} window\n")
        n = len(d)
        # CPM defensive months
        cpm_def = d[d["cpm_safe_w"] > 0]
        bull_def = d[d["bull_safe_w"] > 0]
        cpm_ief = cpm_def[cpm_def["cpm_safe_pick"] == "IEF"]
        bull_ief = bull_def[bull_def["bull_safe_pick"] == "IEF"]
        # any-sleeve-defensive months where pick is IEF
        any_def = d[(d["cpm_safe_w"] > 0) | (d["bull_safe_w"] > 0)]
        # IEF picked by either sleeve
        ief_picked = any_def[(any_def["cpm_safe_pick"] == "IEF")
                             | (any_def["bull_safe_pick"] == "IEF")]
        A(f"- Total month-ends: {n}.")
        A(f"- CPM defensive months (holds safe leg): {len(cpm_def)} "
          f"({len(cpm_def)/n*100:.1f}% of months). Of these IEF picked: "
          f"{len(cpm_ief)} ({(len(cpm_ief)/len(cpm_def)*100) if len(cpm_def) else float('nan'):.1f}%), "
          f"SHV picked: {len(cpm_def)-len(cpm_ief)}.")
        A(f"- BULL cash months (holds safe leg): {len(bull_def)} "
          f"({len(bull_def)/n*100:.1f}% of months). Of these IEF picked: "
          f"{len(bull_ief)} ({(len(bull_ief)/len(bull_def)*100) if len(bull_def) else float('nan'):.1f}%), "
          f"SHV picked: {len(bull_def)-len(bull_ief)}.")
        A(f"- Any-sleeve-defensive months: {len(any_def)}; of those at least one "
          f"sleeve picked IEF: {len(ief_picked)} "
          f"({(len(ief_picked)/len(any_def)*100) if len(any_def) else float('nan'):.1f}%). "
          f"(How often the SHV-vs-IEF choice could matter.)")
        # realized gap in IEF-picked defensive months
        if len(cpm_ief):
            g = cpm_ief["gap_ief_minus_shv"]
            A(f"- CPM IEF-picked months realized fwd gap (IEF-SHV): "
              f"mean {g.mean()*100:+.2f}%, median {g.median()*100:+.2f}%, "
              f"IEF beat SHV {int((g>0).sum())}/{len(g)} ({(g>0).mean()*100:.0f}%).")
        if len(cpm_def):
            # what if IEF months had been SHV instead: sum of gap captured
            g_all = cpm_def.apply(lambda r: r["gap_ief_minus_shv"] if r["cpm_safe_pick"] == "IEF" else 0.0, axis=1)
            A(f"- CPM: cumulative realized timing edge from picking IEF over SHV "
              f"in defensive months (sum of captured gaps): {g_all.sum()*100:+.2f}% "
              f"over {len(cpm_def)} defensive months.")
        if len(bull_ief):
            g = bull_ief["gap_ief_minus_shv"]
            A(f"- BULL IEF-picked months realized fwd gap (IEF-SHV): "
              f"mean {g.mean()*100:+.2f}%, IEF beat SHV {int((g>0).sum())}/{len(g)} "
              f"({(g>0).mean()*100:.0f}%).")
        A("")

    # ---- Verdict ----
    A("## 3. Verdict\n")
    c = {sid: results[sid]["clean"]["blend"] for sid in results}
    st = {sid: results[sid]["stress"]["blend"] for sid in results}
    A("Comparison anchors (clean window, 60/40 blend):\n")
    A(f"- S0 (timing): Sharpe {c['S0']['sharpe']:.3f}, ExSharpe "
      f"{c['S0']['excess_sharpe']:.3f}, CAGR {c['S0']['cagr']*100:.2f}%, "
      f"MaxDD {c['S0']['max_drawdown']*100:.2f}%, Calmar {c['S0']['calmar']:.2f}, "
      f"2022 {results['S0']['clean']['ret_2022']*100:.2f}%.")
    A(f"- S1 (SHV): Sharpe {c['S1']['sharpe']:.3f}, ExSharpe "
      f"{c['S1']['excess_sharpe']:.3f}, CAGR {c['S1']['cagr']*100:.2f}%, "
      f"MaxDD {c['S1']['max_drawdown']*100:.2f}%, Calmar {c['S1']['calmar']:.2f}, "
      f"2022 {results['S1']['clean']['ret_2022']*100:.2f}%.")
    A(f"- S3 (50/50): Sharpe {c['S3']['sharpe']:.3f}, ExSharpe "
      f"{c['S3']['excess_sharpe']:.3f}, CAGR {c['S3']['cagr']*100:.2f}%, "
      f"MaxDD {c['S3']['max_drawdown']*100:.2f}%, Calmar {c['S3']['calmar']:.2f}, "
      f"2022 {results['S3']['clean']['ret_2022']*100:.2f}%.")
    A("")
    A("Decisive periods:\n")
    A(f"- 2022 (rate-hike, IEF duration hurts) clean 60/40 returns: "
      f"S0 {results['S0']['clean']['ret_2022']*100:+.2f}%, "
      f"S1 {results['S1']['clean']['ret_2022']*100:+.2f}%, "
      f"S2 {results['S2']['clean']['ret_2022']*100:+.2f}%, "
      f"S3 {results['S3']['clean']['ret_2022']*100:+.2f}%.")
    A(f"- 2008 (flight-to-quality, IEF duration helps) stress 60/40 returns: "
      f"S0 {results['S0']['stress']['ret_2008']*100:+.2f}%, "
      f"S1 {results['S1']['stress']['ret_2008']*100:+.2f}%, "
      f"S2 {results['S2']['stress']['ret_2008']*100:+.2f}%, "
      f"S3 {results['S3']['stress']['ret_2008']*100:+.2f}%.")
    A("")
    A("(Auto-generated metrics above; narrative verdict appended after review.)\n")

    FINDINGS.write_text("\n".join(L))


if __name__ == "__main__":
    main()
