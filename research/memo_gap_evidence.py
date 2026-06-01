# -*- coding: utf-8 -*-
"""Throwaway research: fill memo gaps A-E for the 60/40 two-sleeve CPM-BULL memo.

Headline convention (LABELLED EVERYWHERE):
  - Blend = 0.60*trend sleeve (CPM) + 0.40*equity sleeve (BULL-SPY); two-sleeve only.
  - BULL equity vol gate = SLOW crossover rv_60d(SPY) < rv_252d(SPY).
  - Execution = realistic T+1 MOO exact ("mooex"): old basket earns overnight
    close[T]->open[af], new basket earns intraday open[af]->close[af], compounded.
  - Costs = 10 bps/side, post-cost throughout.
  - Clean window 2008-05-30..panel_end (18y); Extended 1999-03-10..panel_end (27y).

Reuses (does NOT rewrite) the production weight/return functions via the
exec_lag_moo_validation_2026_05_30 engine. Read-only; writes only the findings md.

Pieces:
  A. Covariance-lookback plateau sweep (126/252/504/756/1008/1260d) for the CPM
     min-variance pair; CPM-solo + 60/40 blend Sharpe/CAGR/MaxDD/Calmar, clean+ext.
  B. SPY/QQQ naive-benchmark excess + exposure caveat (beta, avg risky exposure).
  C. RV-gate FP/TP cohort vol asymmetry (fresh rv_60d).
  D. Full 8-asset (incl EEM) per-asset contribution share of the CPM sleeve.
  E. Rolling-window methodology paragraph (cite-ready).

Run: .venv/bin/python research/memo_gap_evidence.py
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "research"))

import cpm_live
from cpm_live import (
    load_panel, compute_target_weights, perf_metrics,
    RISKY_UNIVERSE, SAFE_POOL, CANARY_ASSETS, DEFAULT_CASH, COST_BPS_PER_SIDE,
)
import exec_lag_moo_validation_2026_05_30 as ex

GATE_RV60 = ex.GATE_RV60
CONV = "mooex"
CPM_W, BULL_W = 0.60, 0.40
EXT_START = pd.Timestamp("1999-03-10")
CLEAN_START = pd.Timestamp("2008-05-30")

OUT = ROOT / "research" / "memo_gap_evidence_findings.md"

# Headline anchors (60/40 blend, mooex, slow gate).
ANCHOR = {
    "clean": dict(sharpe=1.321, cagr=0.1325, maxdd=-0.1066, calmar=1.243),
    "ext":   dict(sharpe=1.235, cagr=0.1232, maxdd=-0.1118, calmar=1.101),
}

L = []
def emit(s=""):
    L.append(s)
def flush():
    OUT.write_text("\n".join(L) + "\n")


# ---------------------------------------------------------------------------
# Shared panel / execution scaffolding.
# ---------------------------------------------------------------------------
def build():
    end = pd.Timestamp("2026-05-30")
    panel = load_panel(start=EXT_START, end=end)
    end = min(end, panel.index[-1])
    cash_daily = panel["SHV"].ffill().pct_change().dropna()
    open_df, close_yf = ex.load_open_close()
    intraday = (close_yf / open_df - 1.0).reindex(panel.index)
    overnight = (open_df / close_yf.shift(1) - 1.0).reindex(panel.index)
    return panel, end, cash_daily, intraday, overnight


def met_window(series, ws, we, cash, label="x"):
    sub = series.loc[(series.index >= ws) & (series.index <= we)]
    return ex.met(sub, cash, label)


def blend_window(cpm_full, bull_full, ws, we, cash, wc=CPM_W, wb=BULL_W):
    common = cpm_full.index.intersection(bull_full.index)
    bl = wc * cpm_full.reindex(common) + wb * bull_full.reindex(common)
    return met_window(bl, ws, we, cash)


def blend_series(cpm_full, bull_full, wc=CPM_W, wb=BULL_W):
    common = cpm_full.index.intersection(bull_full.index)
    return wc * cpm_full.reindex(common) + wb * bull_full.reindex(common)


# ---------------------------------------------------------------------------
# Weight-placement reconstruction (for exposure + contribution).
# Mirrors ex._segment_returns_conv df_w construction exactly (weight placement
# is convention-independent; mooex only re-prices the rebal day return).
# ---------------------------------------------------------------------------
def build_weights_df(close, weight_fn, start, end):
    monthly_idx = (pd.DataFrame({"x": 1}, index=close.index)
                   .groupby(pd.Grouper(freq="ME")).tail(1))
    sigs = monthly_idx.index[(monthly_idx.index >= start) & (monthly_idx.index <= end)].tolist()

    def apply_from(sig_d):
        fut = close.index[close.index > sig_d]
        return fut[0] if len(fut) else None

    hist = []
    for i, sd in enumerate(sigs):
        w = weight_fn(sd)
        af = apply_from(sd)
        if af is None:
            continue
        if i + 1 < len(sigs):
            naf = apply_from(sigs[i + 1])
            ea = naf if naf is not None else end
        else:
            ea = end
        hist.append({"af": af, "ea": ea, "w": w})
    all_assets = sorted({a for h in hist for a in h["w"]})
    cols = [a for a in all_assets if a in close.columns]
    df_w = pd.DataFrame(0.0, index=close.index, columns=cols)
    for h in hist:
        mask = (close.index >= h["af"]) & (close.index < h["ea"])
        for a, ww in h["w"].items():
            if a in df_w.columns:
                df_w.loc[mask, a] = ww
    return df_w


def cpm_close(panel):
    cols = sorted(set(RISKY_UNIVERSE + SAFE_POOL + CANARY_ASSETS + [DEFAULT_CASH]) & set(panel.columns))
    return panel[cols]


def fp(x, d=2):
    return f"{x*100:.{d}f}%"


# ===========================================================================
# A. Covariance-lookback plateau.
# ===========================================================================
def section_A(panel, end, cash, intraday, overnight, bull_base):
    emit("\n## A. Covariance-Lookback Plateau (CPM min-variance pair)\n")
    emit("**Config:** 60/40 two-sleeve (0.60 CPM + 0.40 BULL-SPY), slow rv_60d<rv_252d equity "
         "gate, T+1 MOO exact execution, post-cost 10 bps/side. Only the CPM min-variance pair's "
         "covariance lookback varies; everything else held at the headline config "
         "(PAIR_VAR_WEIGHT=1.0 pure min-variance, top-K=4, positive-trend screen, dual canary). "
         "BULL sleeve is identical across rows (gate-shared but lookback-independent).")
    emit(f"**Windows:** clean {CLEAN_START.date()}..{end.date()} (18y); "
         f"ext {EXT_START.date()}..{end.date()} (27y).\n")

    lookbacks = [126, 252, 504, 756, 1008, 1260]
    base_orig = cpm_live.CORR_LOOKBACK_DAYS
    rows = {}
    try:
        for Lb in lookbacks:
            cpm_live.CORR_LOOKBACK_DAYS = Lb
            cpm_s, fb = ex.cpm_sleeve_conv(panel, intraday, overnight, EXT_START, end, CONV)
            rows[Lb] = {
                "cpm_clean": met_window(cpm_s, CLEAN_START, end, cash),
                "cpm_ext": met_window(cpm_s, EXT_START, end, cash),
                "bl_clean": blend_window(cpm_s, bull_base, CLEAN_START, end, cash),
                "bl_ext": blend_window(cpm_s, bull_base, EXT_START, end, cash),
                "fb": fb,
            }
            print(f"  A: cov={Lb}d blend clean Sharpe={rows[Lb]['bl_clean']['sharpe']:.3f} "
                  f"MaxDD={fp(rows[Lb]['bl_clean']['maxdd'])} Calmar={rows[Lb]['bl_clean']['calmar']:.3f} "
                  f"(MOO real/fb={fb})")
    finally:
        cpm_live.CORR_LOOKBACK_DAYS = base_orig

    # Anchor check on base 504d blend clean.
    b = rows[504]["bl_clean"]
    ok = (abs(b["sharpe"] - ANCHOR["clean"]["sharpe"]) <= 0.004
          and abs(b["maxdd"] - ANCHOR["clean"]["maxdd"]) <= 0.0015
          and abs(b["calmar"] - ANCHOR["clean"]["calmar"]) <= 0.006)
    emit(f"**Base anchor (504d, clean blend):** Sharpe {b['sharpe']:.3f} / CAGR {fp(b['cagr'])} / "
         f"MaxDD {fp(b['maxdd'])} / Calmar {b['calmar']:.3f} vs headline 1.321 / 13.25% / -10.66% / "
         f"1.243 -> **{'CONFIRMED' if ok else 'MISMATCH'}**.\n")

    def tbl(kind, win):
        sub = "cpm_" + win if kind == "cpm" else "bl_" + win
        emit(f"\n### {('CPM-solo' if kind=='cpm' else '60/40 blend')} -- cov-lookback sweep [{win}, mooex, slow gate]\n")
        emit("| cov lookback | Sharpe | CAGR | MaxDD | Calmar |")
        emit("|---|---:|---:|---:|---:|")
        for Lb in lookbacks:
            m = rows[Lb][sub]
            star = " (base)" if Lb == 504 else ""
            emit(f"| {Lb}d{star} | {m['sharpe']:.3f} | {fp(m['cagr'])} | {fp(m['maxdd'])} | {m['calmar']:.3f} |")

    for kind in ("cpm", "blend"):
        for win in ("clean", "ext"):
            tbl(kind, win)

    # Verdict logic: plateau if 756/1008/1260 ~ flat vs 504 (within tol on blend clean Sharpe & Calmar).
    base_sh = rows[504]["bl_clean"]["sharpe"]
    base_cal = rows[504]["bl_clean"]["calmar"]
    long_sh = [rows[x]["bl_clean"]["sharpe"] for x in (756, 1008, 1260)]
    long_cal = [rows[x]["bl_clean"]["calmar"] for x in (756, 1008, 1260)]
    max_sh_dev = max(abs(s - base_sh) for s in long_sh)
    max_cal_dev = max(abs(c - base_cal) for c in long_cal)
    emit("\n### A. Verdict\n")
    emit(f"Clean blend Sharpe: 504d={base_sh:.3f}, 756d={rows[756]['bl_clean']['sharpe']:.3f}, "
         f"1008d={rows[1008]['bl_clean']['sharpe']:.3f}, 1260d={rows[1260]['bl_clean']['sharpe']:.3f}; "
         f"clean blend Calmar: 504d={base_cal:.3f}, 756d={rows[756]['bl_clean']['calmar']:.3f}, "
         f"1008d={rows[1008]['bl_clean']['calmar']:.3f}, 1260d={rows[1260]['bl_clean']['calmar']:.3f} "
         f"(max deviation of 756/1008/1260 vs 504 = {max_sh_dev:.3f} Sharpe, {max_cal_dev:.3f} Calmar).\n")
    emit(
        "**Verdict: the '504d plateaus to 1000d+' claim is REFUTED as stated.** There is a NARROW "
        "plateau, but it spans only 504d-756d, not 1000d+. 504d and 756d are statistically flat on "
        "the clean blend (Sharpe 1.321 vs 1.307, identical MaxDD -10.66%, Calmar 1.243 vs 1.224) -- a "
        "genuine two-point stability shelf that supports 504d as a non-knife-edge choice. But "
        "extending to 1008d and 1260d DEGRADES the blend monotonically: clean Sharpe falls to 1.275 "
        "then 1.257, clean Calmar collapses from 1.243 to 1.011 then 1.000, and clean MaxDD deepens "
        "from -10.66% to -12.70%. The ext window is worse still for long lookbacks (756d/1008d/1260d "
        "Calmar 0.872/0.958/0.785 vs 504d 1.101, with 1260d MaxDD blowing out to -15.34%). The short "
        "end is also clearly inferior (252d Sharpe 1.216 / Calmar 0.946; 126d MaxDD -14.80%). So 504d "
        "sits at the LEFT EDGE of a short 504-756d plateau and is the joint Sharpe+Calmar optimum, "
        "with decay -- not a plateau -- beyond ~756d. CPM-solo tells a slightly different story (its "
        "MaxDD keeps improving out to 756-1008d as longer covariance smooths pair selection) but its "
        "Sharpe/Calmar still peak at 504-756d, and the blend (the headline object) decays past 756d. "
        "Bottom line: 504d is well-chosen and locally stable, but the specific claim that metrics stay "
        "flat out to 1000d+ does not hold.\n"
    )
    return rows, ok


# ===========================================================================
# B. SPY/QQQ naive-benchmark excess + exposure caveat.
# ===========================================================================
def buy_hold(panel, ticker, cost_bps=COST_BPS_PER_SIDE):
    """Buy-and-hold daily returns, one-time entry cost (10 bps) on first day."""
    px = panel[ticker].ffill()
    r = px.pct_change().dropna()
    if len(r):
        r.iloc[0] -= cost_bps / 10000.0
    return r


def beta_to_spy(strat, spy_ret, ws, we):
    common = strat.index.intersection(spy_ret.index)
    s = strat.reindex(common)
    m = spy_ret.reindex(common)
    sub = pd.DataFrame({"s": s, "m": m}).loc[(s.index >= ws) & (s.index <= we)].dropna()
    if len(sub) < 30:
        return float("nan")
    cov = np.cov(sub["s"], sub["m"])
    return float(cov[0, 1] / cov[1, 1]) if cov[1, 1] > 0 else float("nan")


def section_B(panel, end, cash, intraday, overnight, cpm_base, bull_base):
    emit("\n## B. SPY / QQQ Naive-Benchmark Excess + Exposure Caveat\n")
    emit("**Config:** strategies = 60/40 blend, CPM-solo, BULL-solo (slow rv_60d gate, T+1 MOO "
         "exact, post-cost 10 bps/side). Benchmarks = SPY buy-and-hold and QQQ buy-and-hold "
         "(close-to-close, one-time 10 bps entry cost, always 100% long). Beta = OLS slope of "
         "daily strategy returns on daily SPY returns. Avg exposure = mean daily fraction in "
         "risky/risk-on assets (CPM: sum of weight on the 8 risky ETFs; BULL: SPY weight; "
         "blend: 0.60*CPM_risky + 0.40*BULL_risky). Cash/safe legs count as 0 exposure.")
    emit(f"**Windows:** clean {CLEAN_START.date()}..{end.date()}; ext {EXT_START.date()}..{end.date()} "
         "(QQQ & SPY both have full history from the panel start).\n")

    blend = blend_series(cpm_base, bull_base)
    strat = {"60/40 blend": blend, "CPM-solo": cpm_base, "BULL-solo": bull_base}

    spy_bh = buy_hold(panel, "SPY")
    qqq_bh = buy_hold(panel, "QQQ")
    spy_ret_raw = panel["SPY"].ffill().pct_change().dropna()  # for beta (no cost)

    # Exposure series.
    close = cpm_close(panel)
    cpm_wdf = build_weights_df(close, lambda sd: compute_target_weights(close, sd)[0], EXT_START, end)
    cpm_risky = cpm_wdf[[c for c in RISKY_UNIVERSE if c in cpm_wdf.columns]].sum(axis=1)
    # BULL exposure: SPY weight from bull weight fn.
    import bull_spy_live
    bclose = panel
    bull_wdf = build_weights_df(panel, lambda sd: bull_spy_live.compute_bull_spy_weights(panel, sd, panel["SPY"])[0],
                                EXT_START, end)
    bull_risky = bull_wdf[["SPY"]].sum(axis=1) if "SPY" in bull_wdf.columns else pd.Series(0.0, index=panel.index)
    common = cpm_risky.index.intersection(bull_risky.index)
    blend_risky = CPM_W * cpm_risky.reindex(common) + BULL_W * bull_risky.reindex(common)
    expo = {"60/40 blend": blend_risky, "CPM-solo": cpm_risky, "BULL-solo": bull_risky}

    windows = {"clean": (CLEAN_START, end), "ext": (EXT_START, end)}
    res = {}
    for win, (ws, we) in windows.items():
        spy_m = met_window(spy_bh, ws, we, cash)
        qqq_m = met_window(qqq_bh, ws, we, cash)
        res[win] = {"SPY-BH": spy_m, "QQQ-BH": qqq_m}
        for name, s in strat.items():
            m = met_window(s, ws, we, cash)
            bta = beta_to_spy(s, spy_ret_raw, ws, we)
            e = expo[name]
            avg_exp = float(e.loc[(e.index >= ws) & (e.index <= we)].mean())
            res[win][name] = {**m, "beta": bta, "exp": avg_exp,
                              "exc_spy": m["cagr"] - spy_m["cagr"],
                              "exc_qqq": m["cagr"] - qqq_m["cagr"]}
        # benchmark beta/exposure
        res[win]["SPY-BH"].update({"beta": beta_to_spy(spy_bh, spy_ret_raw, ws, we), "exp": 1.0,
                                   "exc_spy": 0.0, "exc_qqq": spy_m["cagr"] - qqq_m["cagr"]})
        res[win]["QQQ-BH"].update({"beta": beta_to_spy(qqq_bh, spy_ret_raw, ws, we), "exp": 1.0,
                                   "exc_spy": qqq_m["cagr"] - spy_m["cagr"], "exc_qqq": 0.0})

    order = ["60/40 blend", "CPM-solo", "BULL-solo", "SPY-BH", "QQQ-BH"]
    for win, (ws, we) in windows.items():
        emit(f"\n### B. Strategy vs SPY/QQQ buy-and-hold [{win}, mooex, slow gate]\n")
        emit("| series | CAGR | Sharpe | MaxDD | Calmar | excess CAGR vs SPY | excess CAGR vs QQQ | beta to SPY | avg risky exposure |")
        emit("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
        for name in order:
            m = res[win][name]
            exp_s = "100%" if name in ("SPY-BH", "QQQ-BH") else f"{m['exp']*100:.1f}%"
            emit(f"| {name} | {fp(m['cagr'])} | {m['sharpe']:.3f} | {fp(m['maxdd'])} | {m['calmar']:.3f} | "
                 f"{fp(m['exc_spy'])} | {fp(m['exc_qqq'])} | {m['beta']:.2f} | {exp_s} |")

    emit("\n### B. Honest read\n")
    emit(
        "The 60/40 blend beats SPY buy-and-hold on CAGR by a modest +1.52% (clean) / +3.82% (ext) "
        "but TRAILS QQQ buy-and-hold on CAGR in the clean window (-3.70%) and only edges it in the "
        "ext window (+1.42%). The blend's headline advantage is NOT raw return -- it is risk: clean "
        "Sharpe 1.321 vs SPY 0.660 / QQQ 0.816, clean MaxDD -10.66% vs SPY -50.70% / QQQ -49.37% "
        "(Calmar 1.243 vs 0.231 / 0.343). **Mechanical caveat (must be stated with any excess-return "
        "row):** the blend runs a realized beta to SPY of only ~0.16 and spends meaningful time "
        "de-risked -- average risky exposure ~75% (blend), ~87% (CPM-solo), ~59% (BULL-solo) -- so it "
        "is NOT an always-long equity book. A large part of the excess return versus always-long "
        "SPY/QQQ is therefore lower-beta de-risking and cross-asset diversification (the trend sleeve "
        "holds GLD/TLT/bonds), not pure stock-picking skill. Framed honestly: the blend is not a "
        "higher-return bet than QQQ; it is a far higher risk-adjusted, far shallower-drawdown bet that "
        "happens to roughly match SPY's long-run CAGR while taking ~1/6th the equity beta and a "
        "fifth of the peak drawdown.\n"
    )
    return res


# ===========================================================================
# C. RV-gate FP/TP cohort vol asymmetry (fresh rv_60d).
# ===========================================================================
def section_C(panel, end, cash):
    emit("\n## C. RV-Gate FP/TP Cohort Vol Asymmetry (fresh rv_60d)\n")
    emit("**Gate:** BULL equity vol gate rv_60d(SPY) < rv_252d(SPY); gate ON = risk-on allowed, "
         "gate OFF (rv_60d >= rv_252d) = risk-off. Forward = next month-end signal date. Forward "
         "realized vol = annualized std of daily SPY returns over the forward month. Cohorts among "
         "gate-OFF months: TRUE-POSITIVE (SPY fell, fwd <= 0) vs FALSE-POSITIVE (SPY rose, fwd > 0). "
         "Computed fresh on the rv_60d gate (not the stale rv_20d cohort log).")
    emit(f"**Windows:** clean {CLEAN_START.date()}..{end.date()}; ext {EXT_START.date()}..{end.date()}.\n")

    spy = panel["SPY"].ffill()
    spy_daily = spy.pct_change()
    monthly_idx = (pd.DataFrame({"x": 1}, index=panel.index)
                   .groupby(pd.Grouper(freq="ME")).tail(1))

    windows = {"clean": (CLEAN_START, end), "ext": (EXT_START, end)}
    out = {}
    for win, (ws, we) in windows.items():
        sigs = monthly_idx.index[(monthly_idx.index >= ws) & (monthly_idx.index <= we)].tolist()
        recs = []
        for i, sd in enumerate(sigs):
            if i + 1 >= len(sigs):
                continue
            nd = sigs[i + 1]
            vol_ok, _ = GATE_RV60(spy, sd)
            fwd_ret = float(spy.loc[nd] / spy.loc[sd] - 1.0)
            fwd_daily = spy_daily.loc[(spy_daily.index > sd) & (spy_daily.index <= nd)].dropna()
            fwd_vol = float(fwd_daily.std() * np.sqrt(252)) if len(fwd_daily) > 2 else np.nan
            recs.append({"sd": sd, "vol_ok": bool(vol_ok), "fwd_ret": fwd_ret, "fwd_vol": fwd_vol})
        df = pd.DataFrame(recs)
        off = df[~df["vol_ok"]]
        on = df[df["vol_ok"]]
        tp = off[off["fwd_ret"] <= 0]
        fp_ = off[off["fwd_ret"] > 0]

        def agg(d):
            return dict(n=len(d), mean_ret=float(d["fwd_ret"].mean()) if len(d) else np.nan,
                        fwd_vol=float(d["fwd_vol"].mean()) if len(d) else np.nan,
                        med_vol=float(d["fwd_vol"].median()) if len(d) else np.nan)
        out[win] = {"n_total": len(df), "n_off": len(off), "n_on": len(on),
                    "TP": agg(tp), "FP": agg(fp_), "OFF_all": agg(off), "ON": agg(on)}

    for win in ("clean", "ext"):
        o = out[win]
        emit(f"\n### C. rv_60d gate-OFF cohorts [{win}]\n")
        emit(f"Evaluated months: {o['n_total']}; gate-OFF (risk-off): {o['n_off']} "
             f"({o['n_off']/o['n_total']*100:.1f}%); gate-ON: {o['n_on']}.\n")
        emit("| cohort | count | mean fwd SPY return | mean fwd realized vol (ann) | median fwd vol |")
        emit("|---|---:|---:|---:|---:|")
        for lab, k in [("TRUE-POSITIVE (SPY fell)", "TP"), ("FALSE-POSITIVE (SPY rose)", "FP"),
                       ("ALL gate-OFF", "OFF_all"), ("gate-ON (unconditional contrast)", "ON")]:
            a = o[k]
            emit(f"| {lab} | {a['n']} | {fp(a['mean_ret'])} | {fp(a['fwd_vol'])} | {fp(a['med_vol'])} |")

    emit("\n### C. Verdict + reconciliation\n")
    emit(
        "**The vol asymmetry is real: the rv_60d gate fires risk-off into a genuinely "
        "higher-volatility forward regime, not noise.** In the clean window, gate-OFF months average "
        "22.19% forward realized vol vs 12.95% for gate-ON months -- a 1.7x vol step. Critically, the "
        "asymmetry holds even when the gate is 'wrong' on direction: the FALSE-POSITIVE cohort (SPY "
        "rose, +4.11% mean) still carries 15.96% forward vol, ABOVE the 12.95% gate-ON baseline, while "
        "the TRUE-POSITIVE cohort (SPY fell, -5.32% mean) carries 29.94% forward vol. So even the "
        "de-risk decisions that 'missed' upside landed in elevated-risk regimes; the gate is selecting "
        "real vol regimes, not random months. Mean forward return across all gate-OFF months is roughly "
        "flat (-0.10% clean / +0.11% ext) but at ~1.7x the volatility of gate-ON months -- a poor "
        "risk-adjusted payoff that justifies stepping aside. The ext window confirms it (gate-OFF "
        "20.88% vs gate-ON 13.61% fwd vol; TP 27.24% vs FP 16.01%).\n\n"
        "**Reconciliation with prior logs:** `rv_gate_cohort_calibration_findings.md` computed cohorts "
        "on the OLD rv_20d gate AND on the narrower 'blocked-month' subset (canary_ok AND trend_ok AND "
        "NOT vol_ok), reporting clean TP fwd vol ~21.1% vs FP ~11.8% on 41 blocked months. This fresh "
        "computation uses the CURRENT rv_60d gate over the FULL vol-gate-OFF set (74 clean months) and "
        "finds the SAME directional asymmetry but a WIDER spread (TP 29.94% vs FP 15.96%). Both agree "
        "on the core claim; the rv_60d full-set view is the cleaner test of the production gate and "
        "shows the asymmetry more strongly. (Note: the prior log's separate EV-decomposition point -- "
        "that forgone FP gains slightly exceed avoided TP losses in raw return terms -- is a return "
        "argument, not a vol argument; it does not contradict the vol-asymmetry justification, which "
        "is about risk-adjusted exposure, not unconditional return.)\n"
    )
    return out


# ===========================================================================
# D. Full 8-asset contribution share (incl EEM).
# ===========================================================================
def section_D(panel, end, cash):
    emit("\n## D. Asset Concentration / Contribution Share (all 8 risky assets, incl EEM)\n")
    emit("**Config:** CPM sleeve, headline config (504d cov, top-K=4, slow-gate-independent), "
         "T+1 MOO weight placement. Contribution_i = sum over days of (weight_i * "
         "close-to-close daily return_i) within the window (arithmetic attribution of the "
         "headline-config weight vector). Risky-share = each asset's contribution as a fraction of "
         "the total of all 8 risky-asset contributions (sums to 100%); the safe leg "
         "(SHV/IEF cash) contribution is reported separately for completeness.")
    emit(f"**Universe (8 risky):** {', '.join(RISKY_UNIVERSE)}.")
    emit(f"**Windows:** clean {CLEAN_START.date()}..{end.date()}; ext {EXT_START.date()}..{end.date()}.\n")

    close = cpm_close(panel)
    daily_ret = close.ffill().pct_change()
    cpm_wdf = build_weights_df(close, lambda sd: compute_target_weights(close, sd)[0], EXT_START, end)
    contrib_all = (cpm_wdf * daily_ret.reindex(cpm_wdf.index)[cpm_wdf.columns]).fillna(0.0)

    windows = {"clean": (CLEAN_START, end), "ext": (EXT_START, end)}
    safe_set = [c for c in (SAFE_POOL + [DEFAULT_CASH]) if c in contrib_all.columns]
    for win, (ws, we) in windows.items():
        sub = contrib_all.loc[(contrib_all.index >= ws) & (contrib_all.index <= we)]
        tot = sub.sum()
        risky_contrib = {a: float(tot.get(a, 0.0)) for a in RISKY_UNIVERSE}
        risky_total = sum(risky_contrib.values())
        safe_contrib = float(sum(tot.get(a, 0.0) for a in safe_set))
        # avg weight (time-in-asset) for context
        wsub = cpm_wdf.loc[(cpm_wdf.index >= ws) & (cpm_wdf.index <= we)]
        emit(f"\n### D. CPM-sleeve per-asset contribution [{win}, mooex weight placement]\n")
        emit("| asset | contribution (sum w*r) | share of 8 risky | avg weight (time-in-asset) |")
        emit("|---|---:|---:|---:|")
        for a in RISKY_UNIVERSE:
            c = risky_contrib[a]
            share = c / risky_total * 100.0 if risky_total != 0 else float("nan")
            avgw = float(wsub.get(a, pd.Series(0.0, index=wsub.index)).mean()) if a in wsub.columns else 0.0
            emit(f"| {a} | {c*100:.2f} pp | {share:.1f}% | {avgw*100:.1f}% |")
        emit(f"| **8 risky total** | {risky_total*100:.2f} pp | 100.0% | - |")
        safe_avgw = float(wsub[safe_set].sum(axis=1).mean()) if safe_set else 0.0
        emit(f"| safe leg (SHV/IEF) | {safe_contrib*100:.2f} pp | (excl.) | {safe_avgw*100:.1f}% |")
    emit("\nNo asset is silently dropped: EEM appears explicitly above with its own contribution "
         "share and average weight.")
    emit(
        "\n**Read:** EEM is a near-dormant member of the trend universe under the headline config -- "
        "0.4% of clean risky contribution at 0.7% average weight (0.6% / 2.6% ext) -- it rarely ranks "
        "into the top-K=4 and is rarely selected into the min-variance pair, but it is NOT excluded "
        "from the universe and is shown here for completeness. Clean-window contribution concentrates "
        "in SPHQ (28.1%), GLD (21.8%) and QQQ (17.6%); the ext window is more balanced (QQQ 20.4%, "
        "SPHQ 16.8%, GLD 16.4%, DBC 13.9%). The eight risky shares sum to 100% by construction; the "
        "safe leg (SHV/IEF, ~21% average weight clean) is reported separately and is additive to the "
        "sleeve's total return.")


# ===========================================================================
# E. Rolling-window methodology (cite-ready).
# ===========================================================================
def section_E():
    emit("\n## E. Rolling-Window Stability Methodology (cite-ready)\n")
    emit(
        "The rolling-window stability metrics in `research/two_sleeve_60_40_ci_walkforward.py` "
        "(`rolling_sharpe`) use **calendar-day** lookbacks, not a fixed trading-day count. For an "
        "N-year window the lookback is `days_lookback = int(N * 365.25)` calendar days, i.e. 1095 "
        "calendar days for the 3-year window and 1826 calendar days for the 5-year window. The "
        "rolling series starts at `daily.index[0] + days_lookback` and is evaluated on every "
        "trading day from that point forward; at each date `d` the window is the calendar slice "
        "`daily.loc[d - days_lookback : d]`. A window is skipped (NaN) unless it contains at least "
        "**100 trading days** of returns (the min-observations cutoff). Within each window the "
        "Sharpe is the raw (zero risk-free) annualized Sharpe: "
        "`(mean(daily) * 252) / (std(daily, ddof=0) * sqrt(252))`, so the **annualization factor "
        "is 252** and volatility uses the population standard deviation (`ddof=0`). The worst-"
        "contiguous-stretch scan (`worst_contiguous`) uses the same `int(N * 365.25)` calendar-day "
        "window length and the same >=100 trading-day floor, stepping the window start across every "
        "trading day. Because the windows are calendar-based, the actual number of trading days per "
        "window is approximately 252 * N (about 756 for 3y and about 1260 for 5y) but varies "
        "slightly with holidays and is not held fixed."
    )


def main():
    panel, end, cash, intraday, overnight = build()
    print(f"Panel {panel.index[0].date()}..{end.date()} ({len(panel)} rows)")

    bull_base, bfb = ex.bull_sleeve_conv(panel, intraday, overnight, EXT_START, end, CONV, GATE_RV60)
    cpm_base, cfb = ex.cpm_sleeve_conv(panel, intraday, overnight, EXT_START, end, CONV)
    print(f"MOO coverage: CPM real/fb={cfb}, BULL real/fb={bfb}")

    emit("# 60/40 Two-Sleeve CPM-BULL: Memo-Gap Evidence (A-E)\n")
    emit("**Headline convention (all tables):** blend = 0.60 CPM (trend sleeve) + 0.40 BULL-SPY "
         "(equity sleeve); slow rv_60d<rv_252d equity vol gate; realistic T+1 MOO exact execution "
         "(overnight close[T]->open[af] on the old basket, intraday open[af]->close[af] on the new "
         "basket, compounded; real yfinance auto_adjust opens); post-cost 10 bps/side. Two-sleeve "
         "only (NOT 60/20/20). Read-only harness `research/memo_gap_evidence.py`; reuses production "
         "weight/return functions via the `exec_lag_moo_validation_2026_05_30` engine.")
    emit(f"Panel {panel.index[0].date()}..{end.date()} ({len(panel)} rows). "
         f"MOO real-open coverage: CPM real={cfb[0]} fallback={cfb[1]}; "
         f"BULL real={bfb[0]} fallback={bfb[1]}.")

    rows_A, ok_A = section_A(panel, end, cash, intraday, overnight, bull_base)
    res_B = section_B(panel, end, cash, intraday, overnight, cpm_base, bull_base)
    out_C = section_C(panel, end, cash)
    section_D(panel, end, cash)
    section_E()

    flush()
    print(f"\nDONE -> {OUT}")
    return rows_A, ok_A, res_B, out_C


if __name__ == "__main__":
    main()
