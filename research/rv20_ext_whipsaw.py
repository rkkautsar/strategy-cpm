# -*- coding: utf-8 -*-
"""Analyst research (read-only re production; writes ONLY research/; NO prod/memo
change; NO commit). OWN harness -- does NOT edit other analysts' files.

QUESTION (user recollection to verify, honestly, could be right or wrong)
------------------------------------------------------------------------
"RV20 was a bit overfit to the clean period; on the EXTENDED window it whipsaws."
The prior verdict (research/rv20_window_validation_findings.md) ADOPTED RV20<RV252
for the NDX sleeve on clean-18y + post-2017 walk-forward. That validation did NOT
test the EXTENDED/older window, and the in-sample bootstrap CI already INCLUDED 0
(RV20-minus-V0 Calmar P=85%). A faster window is structurally more whipsaw-prone,
so the EXTENDED period is the key missing test.

V0 = RV60<RV252 (SPY); candidate = RV20<RV252 (SPY). Gate underlying is SPY for
BOTH the BULL and NDX sleeves, so the SPY-gate whipsaw behavior over the extended
window IS the NDX-relevant test (the gate is identical).

DESIGN
------
PART A -- 1970s stagflation OOS (genuine older regime). Monthly S&P sleeve,
  vol-gate-ONLY (risk-on iff rv_fast<rv_252 on ^GSPC daily; else 3m T-bill).
  Variants: no-gate (buyhold), RV60, RV20. Reuses stagflation_1970s_trend_vol
  loaders verbatim (vol_gate_monthly(win_fast=...)).

PART B1 -- EXTENDED SPY-gate on the BULL daily sleeve. Reuses
  bull_10y3m_extended_1982.build_extended_panel/run_bull/gate factory. Gates:
  no-gate (HAA-simple), RV60 (prod V0), RV20 (candidate). Windows: full 1982-2026,
  ext-1995 (~31y), clean 2008+ (continuity / anchor reproduction).

PART B2 -- EXTENDED high-beta NDX PROXY (QQQ). NDX sleeve returns are
  survivorship-unreliable pre-2017, so we proxy high-beta ext returns with the
  repo QQQ series (proxy from 1988) gated by the SAME SPY-based vol gate, monthly,
  vol-gate-ONLY. EXPLICIT CAVEAT: QQQ proxy != survivorship-clean NDX-100 sleeve.

Every part reports: WHIPSAW (flip count) + FALSE-POSITIVE rate (defensive month
where the asset ROSE next period) for RV20 vs RV60; Calmar/Martin/MaxDD/Sharpe;
and whether RV20 keeps the crisis catches. KEY: does RV20's edge over RV60
SURVIVE the extended/older window or does it whipsaw away (confirming the user)?

HONESTY: t+1 (monthly lag part A; close-to-close T+1 part B1; monthly lag B2),
point-in-time gate, NDX pre-2017 survivorship (B2 is a QQQ proxy, flagged),
single samples. Anchor reproduced before deltas (CLEAN rv60 0.9936/0.7305).

Writes research/rv20_ext_whipsaw_findings.md (+ .json).
"""
from __future__ import annotations
import sys, json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from cpm_live import load_panel, perf_metrics, COST_BPS_PER_SIDE

OUT_JSON = Path(__file__).with_suffix(".json")
OUT_MD = ROOT / "research" / "rv20_ext_whipsaw_findings.md"

FAST_V0 = 60
FAST_CAND = 20
SLOW = 252


# ============================ metric helpers ============================
def monthly_metrics(r: pd.Series, rf: pd.Series) -> dict:
    """CAGR/Vol/Sharpe/MaxDD/Calmar/Martin on a MONTHLY return series."""
    r = r.dropna()
    if r.empty:
        return {}
    n = len(r)
    growth = float((1.0 + r).prod())
    cagr = growth ** (12.0 / n) - 1.0
    vol = float(r.std(ddof=0) * np.sqrt(12))
    rf_a = rf.reindex(r.index).fillna(0.0)
    ex = r - rf_a
    ex_vol = float(ex.std(ddof=0) * np.sqrt(12))
    sharpe = float(ex.mean() * 12 / ex_vol) if ex_vol > 0 else float("nan")
    eq = (1.0 + r).cumprod()
    dd = eq / eq.cummax() - 1.0
    maxdd = float(dd.min())
    ulcer = float(np.sqrt((dd ** 2).mean()))
    calmar = cagr / abs(maxdd) if maxdd != 0 else float("nan")
    martin = cagr / ulcer if ulcer > 0 else float("nan")
    return {"n": n, "cagr": cagr, "vol": vol, "sharpe": sharpe,
            "maxdd": maxdd, "calmar": calmar, "martin": martin,
            "total_ret": growth - 1.0}


def whipsaw_stats(risk_on: pd.Series, asset_ret: pd.Series):
    """Given a monthly risk_on boolean series (decision applied to that month) and
    the asset's monthly return, count flips, defensive months, false positives
    (defensive month where asset ROSE), FP rate, and down-month capture
    (fraction of down months that were defensive)."""
    ro = risk_on.dropna().astype(bool)
    ar = asset_ret.reindex(ro.index)
    flips = int((ro.astype(int).diff().abs() > 0).sum())
    defensive = ~ro
    n_def = int(defensive.sum())
    fp = int(((defensive) & (ar > 0)).sum())           # defensive but asset up
    fp_rate = fp / n_def if n_def else float("nan")
    down = ar < 0
    n_down = int(down.sum())
    caught = int((defensive & down).sum())
    down_capture = caught / n_down if n_down else float("nan")
    yrs = len(ro) / 12.0
    return {"flips": flips, "flips_per_yr": flips / yrs if yrs else float("nan"),
            "n_def": n_def, "def_frac": n_def / len(ro) if len(ro) else float("nan"),
            "fp": fp, "fp_rate": fp_rate, "down_capture": down_capture,
            "n_months": len(ro)}


def window_dd(r: pd.Series, lo, hi) -> float:
    sub = r.loc[(r.index >= lo) & (r.index <= hi)].dropna()
    if len(sub) < 2:
        return float("nan")
    eq = (1.0 + sub).cumprod()
    return float((eq / eq.cummax() - 1.0).min())


def window_ret(r: pd.Series, lo, hi) -> float:
    sub = r.loc[(r.index >= lo) & (r.index <= hi)].dropna()
    return float((1.0 + sub).prod() - 1.0) if len(sub) else float("nan")


# ============================ PART A: 1970s stagflation ============================
def part_a_stagflation():
    import stagflation_1970s_trend_vol as SV
    from stagflation_1970s_tip_canary import (
        EVAL_START, EVAL_END, load_inputs, sp500_total_return, cum_index,
    )
    d = load_inputs()
    tr_sp = sp500_total_return(d["sp_p"], d["sp_d"])   # monthly S&P TR
    rf = d["tb3"] / 12.0
    daily = SV.load_daily_sp()

    vg60 = SV.vol_gate_monthly(daily, win_fast=FAST_V0, win_slow=SLOW)
    vg20 = SV.vol_gate_monthly(daily, win_fast=FAST_CAND, win_slow=SLOW)

    eval_months = pd.period_range(EVAL_START, EVAL_END, freq="M")
    variants = {"nogate": None, "rv60": vg60, "rv20": vg20}
    strat_ret = {v: {} for v in variants}
    risk_on = {v: {} for v in variants}
    for t in eval_months:
        prev = t - 1
        sp = tr_sp.get(t, np.nan)
        cash = rf.get(t, np.nan)
        if pd.isna(sp):
            continue
        for v, vg in variants.items():
            if vg is None:
                on = True
            else:
                sval = vg.loc[prev, "vol_on"] if prev in vg.index else np.nan
                on = bool(sval) if pd.notna(sval) else True   # warmup risk-on
            risk_on[v][t] = on
            strat_ret[v][t] = sp if on else cash

    strat_ret = {v: pd.Series(s).sort_index() for v, s in strat_ret.items()}
    risk_on = {v: pd.Series(s).sort_index() for v, s in risk_on.items()}
    sp_m = tr_sp.reindex(strat_ret["rv60"].index)

    res = {"window": [str(EVAL_START), str(EVAL_END)], "variants": {}}
    crisis = {"1973_74_bear": (pd.Period("1973-01"), pd.Period("1974-12")),
              "1977_82_stag": (pd.Period("1977-01"), pd.Period("1982-12"))}
    for v in variants:
        m = monthly_metrics(strat_ret[v], rf)
        w = whipsaw_stats(risk_on[v], sp_m) if v != "nogate" else \
            {"flips": 0, "flips_per_yr": 0.0, "n_def": 0, "def_frac": 0.0,
             "fp": 0, "fp_rate": float("nan"), "down_capture": 0.0,
             "n_months": len(risk_on[v])}
        cz = {}
        for cn, (a, b) in crisis.items():
            cz[cn] = {"dd": window_dd(strat_ret[v], a, b),
                      "ret": window_ret(strat_ret[v], a, b)}
        res["variants"][v] = {"metrics": m, "whipsaw": w, "crisis": cz}
    return res


# ============================ PART B1: ext BULL daily sleeve ============================
def make_gate_rvN(fast):
    import numpy as _np
    def g(daily_spy, sig_d):
        sub = daily_spy.loc[:sig_d].pct_change().dropna()
        if len(sub) < SLOW:
            return True, {"warmup": True}
        rvf = float(sub.tail(fast).std() * _np.sqrt(252))
        rvs = float(sub.tail(SLOW).std() * _np.sqrt(252))
        return (rvf < rvs), {"rvf": rvf, "rvs": rvs}
    return g


def part_b1_ext_bull():
    import bull_10y3m_extended_1982 as E
    import bull_spy_live
    panel, _t10y3m, prov = E.build_extended_panel()
    end = min(E.END, panel.index[-1])
    cash = panel["SHV"].ffill().pct_change().dropna()

    EXT95_START = pd.Timestamp("1995-01-31")
    windows = {"full_1982": (E.FULL_START, end),
               "ext_1995": (EXT95_START, end),
               "clean_2008": (E.CLEAN_START, end)}
    gates = {"nogate": E.gate_always_on,
             "rv60": make_gate_rvN(FAST_V0),
             "rv20": make_gate_rvN(FAST_CAND)}

    EPISODES = [
        ("1990 recession",   "1990-06-01", "1991-03-31"),
        ("2000-02 dot-com",  "2000-03-01", "2002-10-31"),
        ("2008-09 GFC",      "2007-10-01", "2009-06-30"),
        ("2011 euro/dgrade", "2011-05-01", "2011-12-31"),
        ("2018-Q4",          "2018-10-01", "2018-12-31"),
        ("2020-COVID",       "2020-02-01", "2020-06-30"),
        ("2022 grind",       "2022-01-01", "2022-12-31"),
    ]

    # SPY monthly returns for whipsaw FP (decision applies to month t+1)
    spy_m = panel["SPY"].resample("ME").last().pct_change()

    def regime_series(gate, start, end):
        """monthly risk_on (decision made end of month t, applies month t+1)."""
        orig = bull_spy_live._vol_gate_ok
        bull_spy_live._vol_gate_ok = gate
        out = {}
        try:
            midx = (pd.DataFrame({"x": 1}, index=panel.index)
                    .groupby(pd.Grouper(freq="ME")).tail(1))
            sigs = midx.index[(midx.index >= start) & (midx.index <= end)].tolist()
            for sd in sigs:
                w, lab, _ = bull_spy_live.compute_bull_spy_weights(panel, sd, panel["SPY"])
                out[sd] = ("SPY" in w)
        finally:
            bull_spy_live._vol_gate_ok = orig
        return pd.Series(out).sort_index()

    res = {"anchor_clean_rv60": None, "windows": {}}
    series_cache = {}
    for gname, gate in gates.items():
        series_cache[gname] = E.run_bull(panel, gate, E.FULL_START, end)

    # anchor check
    am = E.met(series_cache["rv60"].loc[E.CLEAN_START:end], cash)
    am["martin"] = perf_metrics(series_cache["rv60"].loc[E.CLEAN_START:end], cash).get("martin")
    res["anchor_clean_rv60"] = am

    for wname, (ws, we) in windows.items():
        res["windows"][wname] = {}
        for gname, gate in gates.items():
            s = series_cache[gname].loc[ws:we]
            pm = perf_metrics(s, cash)
            m = {"sharpe": pm.get("sharpe"), "calmar": pm.get("calmar"),
                 "martin": pm.get("martin"), "maxdd": pm.get("max_drawdown"),
                 "cagr": pm.get("cagr"), "vol": pm.get("vol")}
            # whipsaw: regime decision month t -> apply to spy_m month t+1
            ro = regime_series(gate, ws, we)
            ro.index = ro.index.to_period("M")
            ro_next = ro.copy()
            ro_next.index = ro_next.index + 1            # decision applies next month
            spy_p = spy_m.copy(); spy_p.index = spy_p.index.to_period("M")
            common = ro_next.index.intersection(spy_p.index)
            w = whipsaw_stats(ro_next.reindex(common), spy_p.reindex(common)) if gname != "nogate" \
                else {"flips": 0, "flips_per_yr": 0.0, "n_def": 0, "def_frac": 0.0,
                      "fp": 0, "fp_rate": float("nan"), "down_capture": 0.0,
                      "n_months": len(common)}
            eps = {}
            for lbl, lo, hi in EPISODES:
                lo_t, hi_t = pd.Timestamp(lo), pd.Timestamp(hi)
                if hi_t < ws or lo_t > we:
                    continue
                ss = series_cache[gname]
                eps[lbl] = {"dd": window_dd(ss, lo_t, hi_t),
                            "ret": window_ret(ss, lo_t, hi_t)}
            res["windows"][wname][gname] = {"metrics": m, "whipsaw": w, "episodes": eps}
    res["prov"] = prov
    return res


# ============================ PART B2: ext high-beta QQQ proxy ============================
def part_b2_ext_qqq():
    """vol-gate-ONLY on QQQ monthly returns, gate underlying = SPY daily.
    QQQ proxy from repo (1988+). CAVEAT: QQQ proxy != survivorship-clean NDX-100."""
    panel = load_panel(start=pd.Timestamp("1990-01-01"))
    spy = panel["SPY"].dropna()
    qqq = panel["QQQ"].dropna()
    # gate underlying must have >=252 history; SPY proxy starts 1995
    spy_ret = spy.pct_change().dropna()
    qqq_m = qqq.resample("ME").last().pct_change()
    # cash proxy: SHV monthly
    cash_m = panel["SHV"].resample("ME").last().pct_change()

    def vol_gate_monthly_spy(fast):
        midx = spy.resample("ME").last().index
        rows = {}
        for me in midx:
            sub = spy_ret.loc[:me]
            if len(sub) < SLOW:
                rows[me] = np.nan
                continue
            rvf = float(sub.tail(fast).std() * np.sqrt(252))
            rvs = float(sub.tail(SLOW).std() * np.sqrt(252))
            rows[me] = bool(rvf < rvs)
        return pd.Series(rows).sort_index()

    g60 = vol_gate_monthly_spy(FAST_V0)
    g20 = vol_gate_monthly_spy(FAST_CAND)

    # decision end of month t applies to month t+1
    EXT95 = pd.Timestamp("1995-01-31")
    eval_idx = qqq_m.index[(qqq_m.index >= EXT95)]
    variants = {"nogate": None, "rv60": g60, "rv20": g20}
    res = {"window": [str(eval_idx[0].date()), str(eval_idx[-1].date())], "variants": {}}
    for v, g in variants.items():
        strat = {}
        ro = {}
        for me in eval_idx:
            prev = (me.to_period("M") - 1)
            # find gate value as of prior month-end
            if g is None:
                on = True
            else:
                gp = g[g.index.to_period("M") == prev]
                on = bool(gp.iloc[-1]) if (len(gp) and pd.notna(gp.iloc[-1])) else True
            ro[me] = on
            qr = qqq_m.get(me, np.nan)
            cr = cash_m.get(me, np.nan)
            if pd.isna(qr):
                continue
            strat[me] = qr if on else (cr if pd.notna(cr) else 0.0)
        sret = pd.Series(strat).sort_index()
        roS = pd.Series(ro).sort_index().reindex(sret.index)
        m = monthly_metrics(sret, cash_m)
        w = whipsaw_stats(roS, qqq_m.reindex(sret.index)) if v != "nogate" else \
            {"flips": 0, "flips_per_yr": 0.0, "n_def": 0, "def_frac": 0.0,
             "fp": 0, "fp_rate": float("nan"), "down_capture": 0.0, "n_months": len(sret)}
        # crisis catches (NDX-relevant)
        cz = {}
        for cn, lo, hi in [("2000-02 dotcom", "2000-03-01", "2002-10-31"),
                           ("2008 GFC", "2007-10-01", "2009-06-30"),
                           ("2018-Q4", "2018-10-01", "2018-12-31"),
                           ("2020 COVID", "2020-02-01", "2020-06-30"),
                           ("2022 bear", "2022-01-01", "2022-12-31")]:
            cz[cn] = {"dd": window_dd(sret, pd.Timestamp(lo), pd.Timestamp(hi)),
                      "ret": window_ret(sret, pd.Timestamp(lo), pd.Timestamp(hi))}
        res["variants"][v] = {"metrics": m, "whipsaw": w, "crisis": cz}
    res["qqq_first"] = str(qqq.index[0].date())
    res["spy_first"] = str(spy.index[0].date())
    return res


# ============================ MD writer ============================
def f4(x):
    return f"{x:.4f}" if x is not None and isinstance(x, (int, float)) and np.isfinite(x) else "n/a"


def pct(x):
    return f"{x*100:.2f}%" if x is not None and isinstance(x, (int, float)) and np.isfinite(x) else "n/a"


def write_md(A, B1, B2):
    L = []; W = L.append
    W("# RV20 vs RV60 on the EXTENDED / 1970s windows -- whipsaw + crisis-catch test\n")
    W("Role: analyst (read-only re production; writes only research/; no prod/memo edits; no "
      "commit). Own harness `research/rv20_ext_whipsaw.py`. Does NOT edit other analysts' files.\n")
    W("**Recollection under test:** \"RV20 was a bit overfit to the clean period; on the EXTENDED "
      "window it whipsaws.\" The prior verdict adopted RV20<RV252 for NDX on clean-18y + post-2017 "
      "walk-forward, but never tested the EXTENDED/older window, and the in-sample bootstrap CI "
      "already INCLUDED 0 (RV20-V0 Calmar P=85%). This study supplies the missing ext / 1970s test.\n")
    W("**V0** = RV60<RV252 (SPY); **candidate** = RV20<RV252 (SPY). The gate underlying is SPY for "
      "BOTH the BULL and NDX sleeves, so SPY-gate whipsaw over the extended window IS the "
      "NDX-relevant test.\n")
    W("**Anchor reproduced before deltas:** ext-harness CLEAN(2008+) BULL rv60 close-to-close "
      f"Sharpe {f4(B1['anchor_clean_rv60']['sharpe'])} / Calmar {f4(B1['anchor_clean_rv60']['calmar'])} "
      f"/ MaxDD {pct(B1['anchor_clean_rv60']['maxdd'])} (expect 0.9936/0.7305/-13.60%).\n")

    # ---------------- PART A ----------------
    W("\n## PART A -- 1970s stagflation OOS (genuine older regime)\n")
    W(f"Monthly S&P sleeve, vol-gate-ONLY (risk-on iff rv_fast<rv_252 on ^GSPC daily, else 3m "
      f"T-bill), t+1 monthly lag. Window {A['window'][0]}..{A['window'][1]}. Reuses "
      "stagflation_1970s_trend_vol loaders verbatim.\n")
    W("| Variant | CAGR | MaxDD | Sharpe | Calmar | Martin | Flips | FlipsYr | Def% | FP rate | DownCap |")
    W("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for v in ["nogate", "rv60", "rv20"]:
        m = A["variants"][v]["metrics"]; w = A["variants"][v]["whipsaw"]
        W(f"| {v} | {pct(m['cagr'])} | {pct(m['maxdd'])} | {f4(m['sharpe'])} | {f4(m['calmar'])} | "
          f"{f4(m['martin'])} | {w['flips']} | {f4(w['flips_per_yr'])} | {pct(w['def_frac'])} | "
          f"{pct(w['fp_rate'])} | {pct(w['down_capture'])} |")
    W("")
    W("Crisis catches (DD / total return within window):\n")
    W("| Variant | 1973-74 bear | 1977-82 stagflation |")
    W("|---|---|---|")
    for v in ["nogate", "rv60", "rv20"]:
        c = A["variants"][v]["crisis"]
        W(f"| {v} | {pct(c['1973_74_bear']['dd'])} / {pct(c['1973_74_bear']['ret'])} | "
          f"{pct(c['1977_82_stag']['dd'])} / {pct(c['1977_82_stag']['ret'])} |")
    aw60, aw20 = A["variants"]["rv60"]["whipsaw"], A["variants"]["rv20"]["whipsaw"]
    W(f"\n**Whipsaw delta RV20 vs RV60 (1970s):** flips {aw20['flips']} vs {aw60['flips']} "
      f"({aw20['flips']-aw60['flips']:+d}); FP rate {pct(aw20['fp_rate'])} vs {pct(aw60['fp_rate'])}; "
      f"defensive {pct(aw20['def_frac'])} vs {pct(aw60['def_frac'])}.\n")

    # ---------------- PART B1 ----------------
    W("\n## PART B1 -- EXTENDED SPY-gate on the BULL daily sleeve (1982/1995-2026)\n")
    W("Reuses bull_10y3m_extended_1982 (production close-to-close T+1, 10 bps/side, gates "
      "monkeypatched). Gates: no-gate (HAA-simple), RV60 (prod V0), RV20 (candidate).\n")
    for wname in ["full_1982", "ext_1995", "clean_2008"]:
        W(f"### {wname}\n")
        W("| Gate | Sharpe | Calmar | Martin | MaxDD | CAGR | Flips | FlipsYr | Def% | FP rate | DownCap |")
        W("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
        for g in ["nogate", "rv60", "rv20"]:
            m = B1["windows"][wname][g]["metrics"]; w = B1["windows"][wname][g]["whipsaw"]
            W(f"| {g} | {f4(m['sharpe'])} | {f4(m['calmar'])} | {f4(m['martin'])} | {pct(m['maxdd'])} | "
              f"{pct(m['cagr'])} | {w['flips']} | {f4(w['flips_per_yr'])} | {pct(w['def_frac'])} | "
              f"{pct(w['fp_rate'])} | {pct(w['down_capture'])} |")
        b60 = B1["windows"][wname]["rv60"]; b20 = B1["windows"][wname]["rv20"]
        dC = b20["metrics"]["calmar"] - b60["metrics"]["calmar"]
        dM = b20["metrics"]["martin"] - b60["metrics"]["martin"]
        dfl = b20["whipsaw"]["flips"] - b60["whipsaw"]["flips"]
        W(f"\nRV20-RV60 deltas ({wname}): Calmar {dC:+.4f}, Martin {dM:+.4f}, flips {dfl:+d} "
          f"({b20['whipsaw']['flips']} vs {b60['whipsaw']['flips']}), FP rate "
          f"{pct(b20['whipsaw']['fp_rate'])} vs {pct(b60['whipsaw']['fp_rate'])}.\n")
    # episode DD table (full window)
    W("### Per-episode MaxDD (full 1982 window, BULL sleeve)\n")
    eplabels = list(B1["windows"]["full_1982"]["rv60"]["episodes"].keys())
    W("| Episode | nogate | rv60 | rv20 |")
    W("|---|---:|---:|---:|")
    for lbl in eplabels:
        row = [lbl]
        for g in ["nogate", "rv60", "rv20"]:
            e = B1["windows"]["full_1982"][g]["episodes"].get(lbl, {})
            row.append(pct(e.get("dd")))
        W("| " + " | ".join(row) + " |")

    # ---------------- PART B2 ----------------
    W("\n## PART B2 -- EXTENDED high-beta NDX PROXY (QQQ), vol-gate-only\n")
    W(f"QQQ monthly returns (repo proxy from {B2['qqq_first']}) gated by the SAME SPY-based vol "
      f"gate (SPY from {B2['spy_first']}), monthly t+1. Window {B2['window'][0]}..{B2['window'][1]}. "
      "**CAVEAT: QQQ proxy != survivorship-clean NDX-100 sleeve; directional high-beta proxy only.**\n")
    W("| Variant | CAGR | MaxDD | Sharpe | Calmar | Martin | Flips | FlipsYr | Def% | FP rate | DownCap |")
    W("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for v in ["nogate", "rv60", "rv20"]:
        m = B2["variants"][v]["metrics"]; w = B2["variants"][v]["whipsaw"]
        W(f"| {v} | {pct(m['cagr'])} | {pct(m['maxdd'])} | {f4(m['sharpe'])} | {f4(m['calmar'])} | "
          f"{f4(m['martin'])} | {w['flips']} | {f4(w['flips_per_yr'])} | {pct(w['def_frac'])} | "
          f"{pct(w['fp_rate'])} | {pct(w['down_capture'])} |")
    W("")
    W("Crisis catches (DD / total return, QQQ proxy):\n")
    cks = list(B2["variants"]["rv60"]["crisis"].keys())
    W("| Variant | " + " | ".join(cks) + " |")
    W("|---" * (len(cks) + 1) + "|")
    for v in ["nogate", "rv60", "rv20"]:
        c = B2["variants"][v]["crisis"]
        row = [v] + [f"{pct(c[k]['dd'])} / {pct(c[k]['ret'])}" for k in cks]
        W("| " + " | ".join(row) + " |")
    q60, q20 = B2["variants"]["rv60"]["whipsaw"], B2["variants"]["rv20"]["whipsaw"]
    qm60, qm20 = B2["variants"]["rv60"]["metrics"], B2["variants"]["rv20"]["metrics"]
    W(f"\n**RV20-RV60 deltas (QQQ ext proxy):** Calmar {qm20['calmar']-qm60['calmar']:+.4f}, "
      f"Martin {qm20['martin']-qm60['martin']:+.4f}, flips {q20['flips']-q60['flips']:+d} "
      f"({q20['flips']} vs {q60['flips']}), FP rate {pct(q20['fp_rate'])} vs {pct(q60['fp_rate'])}.\n")

    OUT_MD.write_text("\n".join(L))


def main():
    print("PART A: 1970s stagflation ..."); A = part_a_stagflation()
    print("PART B1: ext BULL ..."); B1 = part_b1_ext_bull()
    print("PART B2: ext QQQ proxy ..."); B2 = part_b2_ext_qqq()
    OUT_JSON.write_text(json.dumps({"A": A, "B1": B1, "B2": B2}, indent=2, default=float))
    write_md(A, B1, B2)
    # console summary
    print("\n=== 1970s flips RV20/RV60:",
          A["variants"]["rv20"]["whipsaw"]["flips"], "/", A["variants"]["rv60"]["whipsaw"]["flips"])
    for wn in ["full_1982", "ext_1995", "clean_2008"]:
        b60 = B1["windows"][wn]["rv60"]["metrics"]; b20 = B1["windows"][wn]["rv20"]["metrics"]
        f60 = B1["windows"][wn]["rv60"]["whipsaw"]["flips"]; f20 = B1["windows"][wn]["rv20"]["whipsaw"]["flips"]
        print(f"{wn}: RV20 Calmar {b20['calmar']:.4f} vs RV60 {b60['calmar']:.4f} | flips {f20}/{f60}")
    q60 = B2["variants"]["rv60"]["metrics"]; q20 = B2["variants"]["rv20"]["metrics"]
    print(f"QQQ ext: RV20 Calmar {q20['calmar']:.4f} vs RV60 {q60['calmar']:.4f} | "
          f"flips {B2['variants']['rv20']['whipsaw']['flips']}/{B2['variants']['rv60']['whipsaw']['flips']}")
    print("DONE ->", OUT_MD)


if __name__ == "__main__":
    main()
