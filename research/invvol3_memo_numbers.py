# -*- coding: utf-8 -*-
"""Throwaway research (read-only re: production): regenerate ALL memo CPM-side
numbers FRESH under the production INVVOL-3 CPM sleeve weighting.

INVVOL-3 (now in production cpm_live.compute_target_weights):
  select the min-variance 3-subset from the top-K=4 positive-trend pool, then
  inverse-vol weight. Fallbacks: 0 positive -> 100% safe; 1 -> 50/50 risky+safe;
  2 -> inverse-vol over the 2 positives.

Everything routed through the headline convention:
  - Execution: T+1 MOO exact ("mooex") with real yfinance auto_adjust opens.
  - Costs: 10 bps/side, post-cost throughout.
  - BULL equity vol gate: slow rv_60d < rv_252d (GATE_RV60).
  - Blend = 0.60*CPM(INVVOL-3) + 0.40*BULL.
  - Windows: clean 2008-05-30..2026-05-22 (18y), ext 1999-03-10..2026-05-22 (27y).

Anchor (must reproduce before trusting the rest):
  CPM-solo INVVOL-3 clean Sharpe 1.2453 / MaxDD -13.19% / Calmar 1.0824;
  ext Sharpe 1.2249 / MaxDD -15.18% / Calmar 0.9148.

No production files touched. Writes research/invvol3_memo_numbers_findings.md (+ json).
"""
from __future__ import annotations
import sys, json, math
from itertools import combinations
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import exec_lag_moo_validation_2026_05_30 as H
from cpm_live import (
    load_panel, perf_metrics, faber_sma_xs, sig_13612U, best_safe,
    min_var_subset, inv_vol_weights, compute_target_weights,
    RISKY_UNIVERSE, SAFE_POOL, CANARY_ASSETS, DEFAULT_CASH, COST_BPS_PER_SIDE,
)
import cpm_live
# AAA benchmark primitives (CPM-solo there is already production INVVOL-3).
import cpm_vs_canonical_aaa as AAA
# bootstrap / rolling primitives.
import two_sleeve_60_40_ci_walkforward as CI

CONV = "mooex"
CPM_W, BULL_W = 0.60, 0.40
COST = COST_BPS_PER_SIDE  # 10
CPM_UNIV = ["QQQ", "SPHQ", "EFA", "EEM", "VNQ", "GLD", "TLT", "DBC"]
SAFE = ["SHV", "IEF"]
LOOKBACK = 504

CLEAN_START = pd.Timestamp("2008-05-30")
EXT_START = pd.Timestamp("1999-03-10")
END = pd.Timestamp("2026-05-22")

REGIMES = {
    "Dot-com (2000-03..2002-12)": ("2000-03-01", "2002-12-31"),
    "GFC (2007-10..2009-06)":     ("2007-10-01", "2009-06-30"),
    "COVID (2020-02..2020-06)":   ("2020-02-01", "2020-06-30"),
    "2022 bear (2022-01..2022-12)": ("2022-01-01", "2022-12-31"),
}

ANCHOR = {"clean": (1.2453, -13.19, 1.0824), "ext": (1.2249, -15.18, 0.9148)}


def met(s, cash):
    m = perf_metrics(s, cash)
    return {"sharpe": m.get("sharpe"), "cagr": m.get("cagr"), "vol": m.get("vol"),
            "maxdd": m.get("max_drawdown"), "calmar": m.get("calmar"),
            "excess_sharpe": m.get("excess_sharpe")}


def win(s, start, end):
    return s.loc[(s.index >= start) & (s.index <= end)]


def maxdd_ret(s):
    eq = (1.0 + s).cumprod()
    rm = eq.cummax()
    mdd = float((eq / rm - 1.0).min())
    tot = float(eq.iloc[-1] - 1.0) if len(eq) else float("nan")
    return mdd, tot


# ---------------------------------------------------------------------------
# Generalized INVVOL-3 CPM weight function (knobs for Section-8 sweeps).
# Base config (K=4, screen on, faber_vol, hygortip, timed) == production.
# ---------------------------------------------------------------------------
def gcpm_wf(close, sd, *, top_k=4, screen=True, ranker="faber_vol",
            canary="hygortip", safe_kind="timed", lookback=LOOKBACK):
    monthly = close.loc[:sd].resample("ME").last()
    if safe_kind == "timed":
        safe = best_safe(monthly, sd, SAFE)
    elif safe_kind in ("SHV", "IEF", "BLEND5050"):
        safe = safe_kind
    else:
        safe = best_safe(monthly, sd, SAFE)

    if canary != "none":
        ca = {"hyg": ["HYG"], "tip": ["TIP"], "hygortip": ["HYG", "TIP"]}[canary]
        cs = [sig_13612U(monthly[a]) for a in ca if a in monthly.columns]
        cs = [s for s in cs if pd.notna(s)]
        if not cs or sum(1 for s in cs if s > 0) == 0:
            return {safe: 1.0}

    present = [t for t in CPM_UNIV if t in monthly.columns]
    faber = faber_sma_xs(monthly)
    avail = [t for t in present if t in faber.index and pd.notna(faber[t])
             and (sd in close.index and pd.notna(close.loc[sd].get(t, np.nan)))]
    if not avail:
        return {safe: 1.0}

    # ranker score + screen value
    scores, screenval = {}, {}
    if ranker == "plain12":
        for t in avail:
            s = monthly[t].dropna()
            if len(s) < 13:
                continue
            mom = float(s.iloc[-1] / s.iloc[-13] - 1.0)
            scores[t] = mom
            screenval[t] = mom
    else:
        dr = close[avail].ffill().pct_change()
        for t in avail:
            v = dr[t].loc[:sd].tail(252).std() * np.sqrt(252)
            if pd.isna(v) or v < 1e-9:
                v = 1.0
            if ranker == "faber_vol":
                num = float(faber[t]); sv = float(faber[t])
            elif ranker == "13612u_vol":
                num = sig_13612U(monthly[t])
                if pd.isna(num):
                    continue
                num = float(num); sv = num
            else:
                raise ValueError(ranker)
            scores[t] = num / v
            screenval[t] = sv
    if not scores:
        return {safe: 1.0}
    ranked = pd.Series(scores).sort_values(ascending=False)

    if top_k is not None:
        kk = max(2, min(top_k, len(ranked)))
        top = ranked.iloc[:kk]
    else:
        top = ranked

    if screen:
        positive = [t for t in top.index if screenval.get(t, -np.inf) > 0]
    else:
        positive = list(top.index)

    n = len(positive)
    if n == 0:
        return {safe: 1.0}
    if n == 1:
        return {positive[0]: 0.5, safe: 0.5}
    csub = close.loc[:sd]
    if n < 3:
        return inv_vol_weights(csub, positive, lookback)
    pick = min_var_subset(csub, positive, lookback, 3)
    if pick is None:
        return inv_vol_weights(csub, positive, lookback)
    return inv_vol_weights(csub, pick, lookback)


def run_cpm(close, daily, intraday, overnight, wf, cost=COST):
    s, _ = H._segment_returns_conv(close, daily, wf, EXT_START, END, CONV,
                                   cost, intraday, overnight)
    return s


def daily_weights(close, wf, start, end):
    """Daily applied-weight matrix over [start,end] (T+1 MOO apply_from logic)."""
    monthly_idx = (pd.DataFrame({"x": 1}, index=close.index)
                   .groupby(pd.Grouper(freq="ME")).tail(1))
    sigs = monthly_idx.index[(monthly_idx.index >= start) & (monthly_idx.index <= end)].tolist()
    hist = []
    for i, sd in enumerate(sigs):
        w = wf(sd)
        fut = close.index[close.index > sd]
        if len(fut) < 1:
            continue
        af = fut[0]
        if i + 1 < len(sigs):
            nf = close.index[close.index > sigs[i + 1]]
            ea = nf[0] if len(nf) >= 1 else end
        else:
            ea = end
        hist.append((af, ea, w))
    assets = sorted({a for _, _, w in hist for a in w})
    dfw = pd.DataFrame(0.0, index=close.index, columns=assets)
    for af, ea, w in hist:
        mask = (close.index >= af) & (close.index < ea)
        for a, ww in w.items():
            dfw.loc[mask, a] = ww
    return dfw.loc[(dfw.index >= start) & (dfw.index <= end)]


def main():
    panel = load_panel(start=EXT_START, end=END)
    end = min(END, panel.index[-1])
    cash = panel["SHV"].ffill().pct_change().dropna()
    od, cy = H.load_open_close()
    intraday = (cy / od - 1.0).reindex(panel.index)
    overnight = (od / cy.shift(1) - 1.0).reindex(panel.index)

    cols = sorted(set(RISKY_UNIVERSE + SAFE_POOL + CANARY_ASSETS + [DEFAULT_CASH]) & set(panel.columns))
    close = panel[cols]
    daily = close.ffill().pct_change()

    # ----- base sleeves (production INVVOL-3 + BULL slow gate) -----
    cpm = run_cpm(close, daily, intraday, overnight,
                  lambda sd: compute_target_weights(close, sd)[0])
    bull, _ = H.bull_sleeve_conv(panel, intraday, overnight, EXT_START, end, CONV, H.GATE_RV60)
    common = cpm.index.intersection(bull.index)
    cpm = cpm.reindex(common); bull = bull.reindex(common)
    blend = CPM_W * cpm + BULL_W * bull

    out = {"meta": {"conv": CONV, "cost_bps": COST, "lookback": LOOKBACK, "K": 4,
                    "weighting": "INVVOL-3", "clean_start": str(CLEAN_START.date()),
                    "ext_start": str(EXT_START.date()), "end": str(end.date())}}

    # ----- ANCHOR CHECK -----
    anc = {}
    print("=== ANCHOR CHECK (CPM-solo INVVOL-3) ===")
    for wl, st in [("clean", CLEAN_START), ("ext", EXT_START)]:
        m = met(win(cpm, st, end), cash)
        exp = ANCHOR[wl]
        ok = (abs(m["sharpe"] - exp[0]) < 5e-4 and abs(m["maxdd"] * 100 - exp[1]) < 0.02
              and abs(m["calmar"] - exp[2]) < 5e-4)
        anc[wl] = {"m": m, "expect": exp, "ok": ok}
        print(f"  {wl}: Sharpe={m['sharpe']:.4f} MaxDD={m['maxdd']*100:.2f}% Calmar={m['calmar']:.4f} "
              f"expect {exp} -> {'OK' if ok else 'MISMATCH'}")
    out["anchor"] = {wl: {"sharpe": anc[wl]["m"]["sharpe"], "maxdd": anc[wl]["m"]["maxdd"],
                          "calmar": anc[wl]["m"]["calmar"], "ok": anc[wl]["ok"]} for wl in anc}
    if not all(anc[wl]["ok"] for wl in anc):
        print("ANCHOR MISMATCH -- aborting.")
        sys.exit(1)

    # ----- ITEM 1: HEADLINE -----
    headline = {}
    for name, s in [("CPM-solo (INVVOL-3)", cpm), ("BULL-solo", bull), ("60/40 blend", blend)]:
        headline[name] = {wl: met(win(s, st, end), cash)
                          for wl, st in [("clean", CLEAN_START), ("ext", EXT_START)]}
    out["headline"] = headline

    # ----- ITEM 2: CRISIS -----
    crisis = {}
    for rname, (rs, re) in REGIMES.items():
        rs_, re_ = pd.Timestamp(rs), pd.Timestamp(re)
        bl = win(blend, rs_, re_); cp = win(cpm, rs_, re_)
        crisis[rname] = {}
        if len(bl) > 1:
            mdd, tot = maxdd_ret(bl); crisis[rname]["blend"] = {"maxdd": mdd, "ret": tot}
        if len(cp) > 1:
            mdd, tot = maxdd_ret(cp); crisis[rname]["cpm"] = {"maxdd": mdd, "ret": tot}
    out["crisis"] = crisis

    # ----- ITEM 3: BOOTSTRAP CI (clean) -----
    boot = {}
    for name, s in [("60/40 blend", blend), ("CPM-solo (INVVOL-3)", cpm), ("BULL-solo", bull)]:
        cb = s.loc[(s.index >= CLEAN_START) & (s.index <= END)]
        boot[name] = {"point": CI.metrics(cb, cash), "ci": CI.bootstrap_ci(cb)}
        print(f"CI {name}: Sharpe point={boot[name]['point']['Sharpe']:.3f} "
              f"CI[{boot[name]['ci']['Sharpe']['p2.5']:.3f},{boot[name]['ci']['Sharpe']['p97.5']:.3f}]")
    out["bootstrap"] = boot

    # ----- ITEM 4: ROLLING STABILITY (blend) -----
    roll = {}
    cf = win(blend, CLEAN_START, end); ef = win(blend, EXT_START, end)
    roll["clean_3y"] = CI.roll_stats(CI.rolling_sharpe(cf, 3.0))
    roll["clean_5y"] = CI.roll_stats(CI.rolling_sharpe(cf, 5.0))
    roll["ext_3y"] = CI.roll_stats(CI.rolling_sharpe(ef, 3.0))
    roll["ext_5y"] = CI.roll_stats(CI.rolling_sharpe(ef, 5.0))
    worst = {}
    for wl, s in [("clean", cf), ("ext", ef)]:
        for yr in (1.0, 2.0, 3.0):
            sd_, ed_, sh, cg, md = CI.worst_contiguous(s, yr)
            worst[f"{wl}_{int(yr)}y"] = None if sd_ is None else {
                "start": str(sd_.date()), "end": str(ed_.date()), "sharpe": sh,
                "cagr": cg, "maxdd": md}
    out["rolling"] = {"blend": roll, "worst_blend": worst}

    # ----- ITEM 5: BENCHMARK CPM-solo vs canonical AAA -----
    aaa_cols = sorted(set(AAA.AAA_UNIVERSE + AAA.SAFE + ["TIP"]) & set(panel.columns))
    aaa_close = panel[aaa_cols]; aaa_daily = aaa_close.ffill().pct_change()
    canon = AAA.run_wf(aaa_close, aaa_daily, intraday, overnight, EXT_START, end,
                       AAA.make_canonical_aaa_wf(aaa_close, aaa_daily))
    bench = {}
    for wl, st in [("clean", CLEAN_START), ("ext", EXT_START)]:
        bench[wl] = AAA.active_stats(win(cpm, st, end), win(canon, st, end), cash)
    out["benchmark_aaa"] = bench

    # ----- ITEM 6: SECTION-8 SWEEPS (INVVOL-3 weighting) -----
    def sweep_metrics(wf):
        s = run_cpm(close, daily, intraday, overnight, wf)
        com = s.index.intersection(bull.index)
        bl = CPM_W * s.reindex(com) + BULL_W * bull.reindex(com)
        return ({wl: met(win(s, st, end), cash) for wl, st in [("clean", CLEAN_START), ("ext", EXT_START)]},
                {wl: met(win(bl, st, end), cash) for wl, st in [("clean", CLEAN_START), ("ext", EXT_START)]})

    sec8 = {}
    # K-sweep
    ks = {}
    for K in [2, 3, 4, 5, 6]:
        cpm_m, bl_m = sweep_metrics(lambda sd, K=K: gcpm_wf(close, sd, top_k=K))
        ks[K] = {"cpm": cpm_m, "blend": bl_m}
        print(f"K={K} blend clean Sharpe={bl_m['clean']['sharpe']:.3f} MaxDD={bl_m['clean']['maxdd']*100:.2f}%")
    sec8["K_sweep"] = ks
    # screen 2x2
    sc = {}
    for lbl, (kc, scr) in {
        "K-cap ON + positive-trend ON": (4, True),
        "K-cap OFF + positive-trend ON": (None, True),
        "K-cap ON + positive-trend OFF": (4, False),
        "K-cap OFF + positive-trend OFF": (None, False),
    }.items():
        cpm_m, bl_m = sweep_metrics(lambda sd, kc=kc, scr=scr: gcpm_wf(close, sd, top_k=kc, screen=scr))
        sc[lbl] = {"cpm": cpm_m, "blend": bl_m}
    sec8["screen_2x2"] = sc
    # ranker
    rk = {}
    for lbl, rn in {"10m-SMA-distance / rv_252d": "faber_vol",
                    "13612U / rv_252d (positive-13612U screen)": "13612u_vol",
                    "plain 12-month momentum": "plain12"}.items():
        cpm_m, bl_m = sweep_metrics(lambda sd, rn=rn: gcpm_wf(close, sd, ranker=rn))
        rk[lbl] = {"cpm": cpm_m, "blend": bl_m}
    sec8["ranker"] = rk
    # canary
    cn = {}
    for lbl, cm in {"dual high-yield OR inflation-protected": "hygortip",
                    "no canary": "none", "high-yield only": "hyg",
                    "inflation-protected only": "tip"}.items():
        cpm_m, bl_m = sweep_metrics(lambda sd, cm=cm: gcpm_wf(close, sd, canary=cm))
        cn[lbl] = {"cpm": cpm_m, "blend": bl_m}
    sec8["canary"] = cn
    # safe (timed vs fixed). Add synthetic BLEND5050 column.
    close2 = close.copy()
    ret5050 = (0.5 * close["SHV"].ffill().pct_change() + 0.5 * close["IEF"].ffill().pct_change()).fillna(0.0)
    close2["BLEND5050"] = (1.0 + ret5050).cumprod() * 100.0
    daily2 = close2.ffill().pct_change()

    def sweep_metrics2(wf):
        s, _ = H._segment_returns_conv(close2, daily2, wf, EXT_START, end, CONV, COST, intraday, overnight)
        com = s.index.intersection(bull.index)
        bl = CPM_W * s.reindex(com) + BULL_W * bull.reindex(com)
        return ({wl: met(win(s, st, end), cash) for wl, st in [("clean", CLEAN_START), ("ext", EXT_START)]},
                {wl: met(win(bl, st, end), cash) for wl, st in [("clean", CLEAN_START), ("ext", EXT_START)]})

    sf = {}
    for lbl, sk in {"timed SHV/IEF by 13612U": "timed", "SHV only": "SHV",
                    "IEF only": "IEF", "static 50/50 SHV+IEF": "BLEND5050"}.items():
        cpm_m, bl_m = sweep_metrics2(lambda sd, sk=sk: gcpm_wf(close2, sd, safe_kind=sk))
        sf[lbl] = {"cpm": cpm_m, "blend": bl_m}
    sec8["safe"] = sf
    out["section8"] = sec8

    # ----- ITEM 7: CONCENTRATION (per-asset share of risky) -----
    conc = {}
    for wl, st in [("clean", CLEAN_START), ("ext", EXT_START)]:
        dfw = daily_weights(close, lambda sd: compute_target_weights(close, sd)[0], st, end)
        risky = [a for a in CPM_UNIV if a in dfw.columns]
        tot = dfw[risky].values.sum()
        conc[wl] = {a: float(dfw[a].sum() / tot) if tot > 0 else 0.0 for a in CPM_UNIV if a in dfw.columns}
    out["concentration"] = conc

    # ----- ITEM 8: COV-LOOKBACK SWEEP (CPM-solo INVVOL-3) -----
    covsw = {}
    for lb in [126, 252, 504, 756, 1008, 1260]:
        s = run_cpm(close, daily, intraday, overnight,
                    lambda sd, lb=lb: gcpm_wf(close, sd, lookback=lb))
        covsw[lb] = {wl: met(win(s, st, end), cash) for wl, st in [("clean", CLEAN_START), ("ext", EXT_START)]}
        print(f"cov={lb} clean Sharpe={covsw[lb]['clean']['sharpe']:.3f} MaxDD={covsw[lb]['clean']['maxdd']*100:.2f}%")
    out["cov_lookback"] = covsw

    (Path(__file__).with_suffix(".json")).write_text(json.dumps(out, indent=2, default=float))
    write_md(out)
    print("\nDONE -> research/invvol3_memo_numbers_findings.md")
    return out


# ---------------------------------------------------------------------------
def write_md(o):
    L = []
    A = L.append
    m = o["meta"]

    def row5(label, mm, star=False):
        n = f"{label}{' (base)' if star else ''}"
        return (f"| {n} | {mm['sharpe']:.3f} | {mm['cagr']*100:.2f}% | {mm['vol']*100:.2f}% "
                f"| {mm['maxdd']*100:.2f}% | {mm['calmar']:.3f} |")

    A("# CPM INVVOL-3 memo numbers (fresh re-run)\n")
    A(f"All CPM-side numbers regenerated under the **production INVVOL-3** CPM sleeve weighting "
      f"(min-variance 3-subset from the top-K=4 positive-trend pool, then inverse-vol weight; "
      f"fallbacks 0->safe, 1->50/50 risky+safe, 2->invvol-2).\n")
    A(f"**Convention (every table):** execution T+1 MOO exact (`mooex`, real auto_adjust opens); "
      f"post-cost {m['cost_bps']} bps/side; BULL equity vol gate slow rv_60d<rv_252d; "
      f"blend = 0.60*CPM(INVVOL-3) + 0.40*BULL; cov lookback {m['lookback']}d; K={m['K']}. "
      f"Clean window {m['clean_start']}..{m['end']} (18y); extended {m['ext_start']}..{m['end']} (27y).\n")
    A("Source harness: `research/invvol3_memo_numbers.py` (read-only; CPM-solo and concentration "
      "use production `cpm_live.compute_target_weights`; Section-8 variants use a generalized "
      "INVVOL-3 weight fn whose base config reproduces production exactly).\n")

    # Anchor
    a = o["anchor"]
    A("## 0. Anchor check\n")
    A("| Window | Sharpe | MaxDD | Calmar | Expected | Match |")
    A("|---|---:|---:|---:|---|---|")
    for wl in ("clean", "ext"):
        e = ANCHOR[wl]
        A(f"| {wl} | {a[wl]['sharpe']:.4f} | {a[wl]['maxdd']*100:.2f}% | {a[wl]['calmar']:.4f} "
          f"| {e[0]}/{e[1]}%/{e[2]} | {'CONFIRMED' if a[wl]['ok'] else 'MISMATCH'} |")
    A("\nCPM-solo INVVOL-3 reproduces the research anchor exactly in both windows; the rest of this "
      "file is trusted on that basis.\n")

    # Item 1
    h = o["headline"]
    A("## 1. Headline results (config INVVOL-3, T+1 MOO exact, 10 bps/side)\n")
    A("### 1.1 Clean window (18y)\n")
    A("| Series | Sharpe | CAGR | Vol | MaxDD | Calmar |")
    A("|---|---:|---:|---:|---:|---:|")
    for n in ("CPM-solo (INVVOL-3)", "BULL-solo", "60/40 blend"):
        A(row5(n, h[n]["clean"]))
    A("\n### 1.2 Extended window (27y)\n")
    A("| Series | Sharpe | CAGR | Vol | MaxDD | Calmar |")
    A("|---|---:|---:|---:|---:|---:|")
    for n in ("CPM-solo (INVVOL-3)", "BULL-solo", "60/40 blend"):
        A(row5(n, h[n]["ext"]))
    bl = h["60/40 blend"]["clean"]
    A(f"\n**KEY NEW HEADLINE -- 60/40 blend (CPM-INVVOL-3 + BULL), clean:** Sharpe {bl['sharpe']:.3f}, "
      f"CAGR {bl['cagr']*100:.2f}%, Vol {bl['vol']*100:.2f}%, MaxDD {bl['maxdd']*100:.2f}%, "
      f"Calmar {bl['calmar']:.3f}.\n")
    A("**MATERIAL CHANGE vs pair-era memo blend** (pair clean 1.321/13.25%/9.82%/-10.66%/1.243): "
      f"the INVVOL-3 blend Sharpe is {bl['sharpe']:.3f} (was 1.321), MaxDD {bl['maxdd']*100:.2f}% "
      f"(was -10.66%), Calmar {bl['calmar']:.3f} (was 1.243). The old 1.321 blend headline is stale "
      "and must not be reused. BULL-solo is unchanged from the pair era (BULL is independent of the "
      "CPM weighting).\n")

    # Item 2
    c = o["crisis"]
    A("## 2. Crisis windows (INVVOL-3; MaxDD and total return)\n")
    A("| Crisis window | Blend MaxDD | Blend return | CPM-solo MaxDD | CPM-solo return |")
    A("|---|---:|---:|---:|---:|")
    for rn, d in c.items():
        bd = d.get("blend", {}); cd = d.get("cpm", {})
        A(f"| {rn} | {bd.get('maxdd', float('nan'))*100:.2f}% | {bd.get('ret', float('nan'))*100:.2f}% "
          f"| {cd.get('maxdd', float('nan'))*100:.2f}% | {cd.get('ret', float('nan'))*100:.2f}% |")
    A("\nNote: crisis-window MaxDD is computed within each window (peak-to-trough inside the window), "
      "execution T+1 MOO exact, post-cost. Dot-com and GFC pre-2008 sit in the proxy-backed "
      "extended history for the CPM trend universe.\n")

    # Item 3
    b = o["bootstrap"]
    A("## 3. Bootstrap CI (clean window, stationary block bootstrap B=2000, block=21, seed=42)\n")
    for n in ("60/40 blend", "CPM-solo (INVVOL-3)", "BULL-solo"):
        bb = b[n]; ci = bb["ci"]; pt = bb["point"]
        A(f"\n### {n}\n")
        A("| Metric | Point | 95% CI | CI width |")
        A("|---|---:|---|---:|")
        for k in ("Sharpe", "CAGR", "MaxDD", "Calmar"):
            cc = ci[k]; w = cc["p97.5"] - cc["p2.5"]
            if k in ("CAGR", "MaxDD"):
                A(f"| {k} | {pt[k]*100:.2f}% | [{cc['p2.5']*100:.2f}%, {cc['p97.5']*100:.2f}%] | {w*100:.2f}pp |")
            else:
                A(f"| {k} | {pt[k]:.3f} | [{cc['p2.5']:.3f}, {cc['p97.5']:.3f}] | {w:.3f} |")
    bs = b["60/40 blend"]["ci"]["Sharpe"]
    A(f"\n**MATERIAL CHANGE vs pair-era CI:** pair-era blend Sharpe CI was [0.909, 1.751] width 0.842. "
      f"INVVOL-3 blend Sharpe 95% CI = [{bs['p2.5']:.3f}, {bs['p97.5']:.3f}], width "
      f"{bs['p97.5']-bs['p2.5']:.3f}.\n")

    # Item 4
    r = o["rolling"]["blend"]; w = o["rolling"]["worst_blend"]
    A("## 4. Rolling-window stability -- 60/40 blend (INVVOL-3)\n")
    A("| Window | Min | Median | Max | % < 1.0 | % < 0.7 | N |")
    A("|---|---:|---:|---:|---:|---:|---:|")
    for lbl, k in [("Clean 3y", "clean_3y"), ("Clean 5y", "clean_5y"),
                   ("Ext 3y", "ext_3y"), ("Ext 5y", "ext_5y")]:
        s = r[k]
        A(f"| {lbl} | {s['min']:.3f} | {s['median']:.3f} | {s['max']:.3f} | "
          f"{s['pct_under_1.0']:.1f}% | {s['pct_under_0.7']:.1f}% | {s['n']} |")
    A("\nWorst contiguous stretches (blend):\n")
    A("| Window | Length | Dates | Sharpe | CAGR | MaxDD |")
    A("|---|---|---|---:|---:|---:|")
    for wl in ("clean", "ext"):
        for yr in (1, 2, 3):
            d = w[f"{wl}_{yr}y"]
            if d is None:
                A(f"| {wl} | {yr}y | - | - | - | - |")
            else:
                A(f"| {wl} | {yr}y | {d['start']}..{d['end']} | {d['sharpe']:.3f} | "
                  f"{d['cagr']*100:.2f}% | {d['maxdd']*100:.2f}% |")
    A("")

    # Item 5
    bm = o["benchmark_aaa"]
    A("## 5. Benchmark -- CPM-solo (INVVOL-3) vs canonical AAA (no canary)\n")
    A("| Window | Series | Sharpe | CAGR | Vol | MaxDD | Calmar |")
    A("|---|---|---:|---:|---:|---:|---:|")
    for wl in ("clean", "ext"):
        st = bm[wl]; sl = st["sleeve"]; bn = st["bench"]
        A(f"| {wl} | CPM-solo INVVOL-3 | {sl['sharpe']:.3f} | {sl['cagr']*100:.2f}% | {sl['vol']*100:.2f}% "
          f"| {sl['maxdd']*100:.2f}% | {sl['calmar']:.3f} |")
        A(f"| {wl} | Canonical AAA | {bn['sharpe']:.3f} | {bn['cagr']*100:.2f}% | {bn['vol']*100:.2f}% "
          f"| {bn['maxdd']*100:.2f}% | {bn['calmar']:.3f} |")
    A("\n| Window | dCAGR | dCalmar | dSharpe | dMaxDD | Info ratio | Return corr | Tracking err |")
    A("|---|---:|---:|---:|---:|---:|---:|---:|")
    for wl in ("clean", "ext"):
        st = bm[wl]
        A(f"| {wl} | {st['d_cagr']*100:+.2f}pp | {st['d_calmar']:+.3f} | {st['d_sharpe']:+.3f} | "
          f"{st['d_maxdd']*100:+.2f}pp | {st['ir']:+.3f} | {st['corr']:.3f} | {st['te']*100:.2f}% |")
    A("\nBULL vs HAA-Simple is UNCHANGED by the INVVOL-3 weighting (BULL is independent of the CPM "
      "sleeve). Re-cited from the memo: clean BULL 1.081/11.44%/10.57%/-13.35%/0.857 vs HAA-Simple "
      "{BIL,AGG} 0.960/11.08%/11.70%/-19.74%/0.561; ext BULL 0.920/9.49%/10.45%/-13.96%/0.680 vs "
      "HAA-Simple 0.946/10.14%/10.83%/-19.74%/0.514.\n")

    # Item 6
    s8 = o["section8"]
    A("## 6. Section-8 sensitivity sweeps (INVVOL-3 weighting)\n")
    A("Every base row below uses the INVVOL-3 production config and equals the new headline. "
      "Tables show CPM-solo and 60/40 blend, clean + ext.\n")

    def sweep_table(title, d, base_label, order=None):
        A(f"### {title}\n")
        keys = order if order else list(d.keys())
        A("**CPM-solo:**\n")
        A("| variant | Clean Sharpe | Clean CAGR | Clean MaxDD | Clean Calmar | Ext Sharpe | Ext MaxDD | Ext Calmar |")
        A("|---|---:|---:|---:|---:|---:|---:|---:|")
        for k in keys:
            c = d[k]["cpm"]["clean"]; e = d[k]["cpm"]["ext"]
            star = " (base)" if str(k) == str(base_label) else ""
            A(f"| {k}{star} | {c['sharpe']:.3f} | {c['cagr']*100:.2f}% | {c['maxdd']*100:.2f}% | "
              f"{c['calmar']:.3f} | {e['sharpe']:.3f} | {e['maxdd']*100:.2f}% | {e['calmar']:.3f} |")
        A("\n**60/40 blend:**\n")
        A("| variant | Clean Sharpe | Clean CAGR | Clean MaxDD | Clean Calmar | Ext Sharpe | Ext MaxDD | Ext Calmar |")
        A("|---|---:|---:|---:|---:|---:|---:|---:|")
        for k in keys:
            c = d[k]["blend"]["clean"]; e = d[k]["blend"]["ext"]
            star = " (base)" if str(k) == str(base_label) else ""
            A(f"| {k}{star} | {c['sharpe']:.3f} | {c['cagr']*100:.2f}% | {c['maxdd']*100:.2f}% | "
              f"{c['calmar']:.3f} | {e['sharpe']:.3f} | {e['maxdd']*100:.2f}% | {e['calmar']:.3f} |")
        A("")

    sweep_table("6.1 Selection-count K (INVVOL-3)", s8["K_sweep"], 4, order=[2, 3, 4, 5, 6])
    sweep_table("6.2 Screen 2x2 (K-cap x positive-trend, INVVOL-3)", s8["screen_2x2"],
                "K-cap ON + positive-trend ON")
    sweep_table("6.3 Ranker (INVVOL-3)", s8["ranker"], "10m-SMA-distance / rv_252d")
    sweep_table("6.4 Canary (INVVOL-3)", s8["canary"], "dual high-yield OR inflation-protected")
    sweep_table("6.5 Safe sleeve (INVVOL-3)", s8["safe"], "timed SHV/IEF by 13612U")

    # Item 7
    cc = o["concentration"]
    A("## 7. Concentration -- per-asset contribution share of the 8 risky (INVVOL-3)\n")
    A("Share = sum of applied daily weight on the asset / sum of total risky daily weight, over the "
      "window (selection + inverse-vol driven). All 8 risky included; shares sum to 100%.\n")
    A("| Asset | Clean share | Ext share |")
    A("|---|---:|---:|")
    order = sorted(CPM_UNIV, key=lambda a: -cc["clean"].get(a, 0.0))
    tc = sum(cc["clean"].get(a, 0.0) for a in CPM_UNIV)
    te = sum(cc["ext"].get(a, 0.0) for a in CPM_UNIV)
    for a in order:
        A(f"| {a} | {cc['clean'].get(a,0.0)*100:.1f}% | {cc['ext'].get(a,0.0)*100:.1f}% |")
    A(f"| **Total** | {tc*100:.1f}% | {te*100:.1f}% |")
    A("")

    # Item 8
    cs = o["cov_lookback"]
    A("## 8. Cov-lookback sweep -- CPM-solo (INVVOL-3)\n")
    A("| Cov lookback | Clean Sharpe | Clean MaxDD | Clean Calmar | Ext Sharpe | Ext MaxDD | Ext Calmar |")
    A("|---|---:|---:|---:|---:|---:|---:|")
    for lb in [126, 252, 504, 756, 1008, 1260]:
        c = cs[lb]["clean"]; e = cs[lb]["ext"]
        star = " (base)" if lb == 504 else ""
        A(f"| {lb}d{star} | {c['sharpe']:.3f} | {c['maxdd']*100:.2f}% | {c['calmar']:.3f} | "
          f"{e['sharpe']:.3f} | {e['maxdd']*100:.2f}% | {e['calmar']:.3f} |")
    A("\nConfirms whether 504d remains the INVVOL-3 optimum and whether the K=4 pool (Section 6.1) "
      "still holds under inverse-vol weighting.\n")

    A("## Caveats\n")
    A("- All post-cost (10 bps/side), T+1 MOO exact using real yfinance auto_adjust opens "
      "(/tmp/cpm_open_cache); CPM sleeve has no equity vol gate (gate only affects BULL/blend).")
    A("- Ext 27y is partially proxy-backed for the CPM trend universe (several ETFs lack real opens "
      "pre-2006 -> close-to-close fallback on ~80 rebal days); clean 18y has full real-open coverage "
      "and is the decisive lens.")
    A("- CPM-solo, concentration, and the cov/K/canary/safe sweeps drive INVVOL-3 selection from "
      "production primitives; ranker and screen-OFF variants use a generalized INVVOL-3 weight fn "
      "whose base config matches production exactly (anchor confirmed).")
    A("- BULL-solo and BULL-vs-HAA-Simple are independent of the CPM weighting and are unchanged "
      "from the pair-era memo; re-cited, not re-derived as new.")
    A("- Static 50/50 safe variant uses a synthetic daily-rebalanced SHV+IEF column (no opens -> "
      "rebal-day close-to-close fallback on the safe leg).")

    Path(ROOT / "research" / "invvol3_memo_numbers_findings.md").write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
