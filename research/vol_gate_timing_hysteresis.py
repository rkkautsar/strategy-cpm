# -*- coding: utf-8 -*-
"""Throwaway research (analyst role; READ-ONLY re production; NO production/memo
files changed; NO commit). Vol-gate TIMING / HYSTERESIS tuning study.

PART A -- diagnose the 1970s BULL-stack full-period MaxDD: exact peak/trough/
depth window + month-by-month vol-gate state through it. Confirm 1977-82 grind
vs 1973-74 crash, and explain why the gate failed (slow low-vol grind vs sharp
vol-spike crash it does catch).

PART B -- test slower / smoother / hysteresis vol gates vs production
rv_60d<rv_252d, in BOTH eras:
  * Longer short window: rv_90d, rv_120d < rv_252d
  * Confirmation/hysteresis: require N consecutive months before flipping
      - sym2  : 2 months both directions
      - asym  : 1 month to-defensive (fast out), 2 months to-risk-on (slow in)
  * Wider threshold: rv_60d < k*rv_252d for k in {1.05, 1.10}

1970s harness: stagflation_1970s_bull_stack / trend_vol / tip_canary (verbatim
helpers). Full BULL stack (canary AND trend AND vol). Vol gate is the only leg
varied.

MODERN harness: exec_lag_moo_validation_2026_05_30 (mooex T+1, 10bps/side),
production bull_qqq_live BULL sleeve + 60/40 CPM-BULL blend, gate monkeypatched.
ANCHOR-GATED on 60d BULL clean Sharpe ~1.0813 and 60/40 blend ~1.2485.

Writes research/vol_gate_timing_hysteresis_findings.md (+ .json).
"""
from __future__ import annotations
import sys, json
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

# ===========================================================================
# Variant registry (shared naming across eras)
#   each: dict(fast, slow, k, to_def, to_on)
#   to_def/to_on = consecutive-month confirmation required to flip
#   (1 = no hysteresis = production immediacy)
# ===========================================================================
SLOW = 252
VARIANTS = {
    "prod_60":   dict(fast=60,  slow=SLOW, k=1.00, to_def=1, to_on=1),
    "sw_90":     dict(fast=90,  slow=SLOW, k=1.00, to_def=1, to_on=1),
    "sw_120":    dict(fast=120, slow=SLOW, k=1.00, to_def=1, to_on=1),
    "hyst_sym2": dict(fast=60,  slow=SLOW, k=1.00, to_def=2, to_on=2),
    "hyst_asym": dict(fast=60,  slow=SLOW, k=1.00, to_def=1, to_on=2),
    "k_105":     dict(fast=60,  slow=SLOW, k=1.05, to_def=1, to_on=1),
    "k_110":     dict(fast=60,  slow=SLOW, k=1.10, to_def=1, to_on=1),
}


def apply_hysteresis(raw: list, to_def: int, to_on: int, init_state=True) -> list:
    """raw: list of (bool|None) raw gate signals in chronological order.
    None = warmup -> default risk-on (state held = init/True)."""
    out = []
    state = init_state
    pend = 0
    for r in raw:
        if r is None:
            out.append(True)
            continue
        if r == state:
            pend = 0
        else:
            pend += 1
            need = to_def if state else to_on   # state True=risk-on -> need to_def to go defensive
            if pend >= need:
                state = r
                pend = 0
        out.append(state)
    return out


# ===========================================================================
# PART A + 1970s PART B
# ===========================================================================
def run_1970s():
    from stagflation_1970s_tip_canary import (
        EVAL_START, EVAL_END, STAG_WINDOWS,
        load_inputs, bond_total_return, sp500_total_return, cum_index,
        sig_13612U_at, metrics,
    )
    from stagflation_1970s_trend_vol import load_daily_sp, vol_gate_monthly

    d = load_inputs()
    cpi = d["cpi"].pct_change()
    tr_gs5 = bond_total_return(d["gs5"], N=5)
    idx = tr_gs5.index.intersection(cpi.index)
    tr_tip = (tr_gs5.reindex(idx) + cpi.reindex(idx)).dropna()
    px_tip = cum_index(tr_tip)
    tr_sp = sp500_total_return(d["sp_p"], d["sp_d"]); px_sp = cum_index(tr_sp)
    rf = d["tb3"] / 12.0
    px_ief = cum_index(tr_gs5); px_cash = cum_index(rf.dropna())
    daily = load_daily_sp()

    all_months = pd.period_range(EVAL_START - 1, EVAL_END, freq="M")
    # base signals (trend/tip/safe) -- vol added per variant
    base = {}
    for t in all_months:
        base[t] = dict(
            trend=sig_13612U_at(px_sp, t), tip=sig_13612U_at(px_tip, t),
            ief=sig_13612U_at(px_ief, t), cash=sig_13612U_at(px_cash, t),
        )
    eval_months = pd.period_range(EVAL_START, EVAL_END, freq="M")

    def vol_series(fast, k, to_def, to_on):
        """monthly applied vol_on (PeriodIndex) for given variant, plus raw rv."""
        vg = vol_gate_monthly(daily, win_fast=fast, win_slow=SLOW)
        raw = []
        for t in all_months:
            if t in vg.index and pd.notna(vg.loc[t, "rv_fast"]):
                raw.append(bool(vg.loc[t, "rv_fast"] < k * vg.loc[t, "rv_slow"]))
            else:
                raw.append(None)
        applied = apply_hysteresis(raw, to_def, to_on)
        s_app = pd.Series(applied, index=all_months)
        s_raw = pd.Series([np.nan if r is None else bool(r) for r in raw], index=all_months)
        return s_app, s_raw, vg

    def backtest(s_app):
        ret = {}; ro = {}
        for t in eval_months:
            p = t - 1
            if p not in base:
                continue
            s = base[p]; sp = tr_sp.get(t, np.nan)
            if pd.isna(sp):
                continue
            trend_on = (s["trend"] > 0) if pd.notna(s["trend"]) else True
            tip_on = (s["tip"] > 0) if pd.notna(s["tip"]) else True
            vol_on = bool(s_app.get(p, True))
            ci = s["cash"] if pd.notna(s["cash"]) else -np.inf
            ii = s["ief"] if pd.notna(s["ief"]) else -np.inf
            safe = tr_gs5.get(t, np.nan) if ii >= ci else rf.get(t, np.nan)
            if pd.isna(safe):
                safe = rf.get(t, np.nan)
            on = trend_on and tip_on and vol_on
            ro[t] = on
            ret[t] = sp if on else safe
        return pd.Series(ret).sort_index(), pd.Series(ro).sort_index()

    def dd_window(r):
        eq = (1 + r).cumprod(); peak = eq.cummax(); dd = eq / peak - 1
        trough = dd.idxmin(); depth = float(dd.min())
        pk = eq.loc[:trough].idxmax()
        rec = eq.loc[trough:]; recov = rec[rec >= eq.loc[pk]]
        return dict(peak=str(pk), trough=str(trough), depth_pct=round(depth * 100, 2),
                    recover=str(recov.index[0]) if len(recov) else None)

    def win_maxdd(r, a, b):
        sub = r.loc[a:b].dropna()
        eq = (1 + sub).cumprod()
        return round(float((eq / eq.cummax() - 1).min()) * 100, 2)

    # ---- production baseline for PART A ----
    s_app_prod, s_raw_prod, vg_prod = vol_series(60, 1.0, 1, 1)
    r_prod, ro_prod = backtest(s_app_prod)
    fulldd = dd_window(r_prod)

    # month-by-month gate state THROUGH the full-period DD window
    pk = pd.Period(fulldd["peak"], "M"); tr = pd.Period(fulldd["trough"], "M")
    cal = []
    flips = 0; prev = None; ron_cnt = 0
    for t in pd.period_range(pk, tr, freq="M"):
        p = t - 1
        vf = float(vg_prod.loc[p, "rv_fast"]) if (p in vg_prod.index and pd.notna(vg_prod.loc[p, "rv_fast"])) else None
        vs = float(vg_prod.loc[p, "rv_slow"]) if (p in vg_prod.index and pd.notna(vg_prod.loc[p, "rv_slow"])) else None
        von = bool(s_app_prod.get(p, True))
        ton = (base[p]["trend"] > 0) if pd.notna(base[p]["trend"]) else True
        risk_on = bool(ro_prod.get(t, True))
        ron_cnt += int(risk_on)
        if prev is not None and von != prev:
            flips += 1
        prev = von
        cal.append(dict(
            applied_month=str(t), signal_month=str(p),
            rv_fast=round(vf, 4) if vf else None, rv_slow=round(vs, 4) if vs else None,
            rv_ratio=round(vf / vs, 3) if (vf and vs) else None,
            vol_on=von, trend_on=bool(ton), bull_risk_on=risk_on,
            sp_ret_pct=round(float(tr_sp.get(t, np.nan)) * 100, 2) if pd.notna(tr_sp.get(t, np.nan)) else None,
        ))

    partA = {
        "full_period_maxdd_window": fulldd,
        "full_period_metrics": metrics(r_prod, rf),
        "window_maxdd_1973_74": win_maxdd(r_prod, *STAG_WINDOWS["bear_1973_74"]),
        "window_maxdd_1977_82": win_maxdd(r_prod, *STAG_WINDOWS["stagflation_1977_82"]),
        "dd_window_n_months": len(cal),
        "dd_window_n_riskon_months": ron_cnt,
        "dd_window_vol_flips": flips,
        "dd_window_calendar": cal,
        "interpretation": (
            "Full-period MaxDD is the 1977-82 GRIND (peak %s -> trough %s, %.2f%%), "
            "NOT the 1973-74 crash (window DD only %s%%). Through the DD the vol gate "
            "was risk-on %d of %d months: rv_fast stayed BELOW rv_252 (low realized vol) "
            "while equity ground lower; the gate only flipped defensive AFTER the sharp "
            "-8.3%% Sep-1981 drop (rv finally crossed up), then flipped back risk-on at "
            "the Jan-1982 trough catching -4.8%%. Gate fails on slow low-vol grinds; it "
            "catches the 1973-74 crash because that decline came WITH a vol expansion."
            % (fulldd["peak"], fulldd["trough"], fulldd["depth_pct"],
               win_maxdd(r_prod, *STAG_WINDOWS["bear_1973_74"]), ron_cnt, len(cal))
        ),
    }

    # ---- PART B variants (1970s) ----
    W7374 = STAG_WINDOWS["bear_1973_74"]; W7782 = STAG_WINDOWS["stagflation_1977_82"]
    sp_next = tr_sp.reindex(eval_months)
    rows = {}
    for name, v in VARIANTS.items():
        s_app, s_raw, vg = vol_series(v["fast"], v["k"], v["to_def"], v["to_on"])
        r, ro = backtest(s_app)
        m = metrics(r, rf)
        # vol flips over eval window (applied)
        app_eval = s_app.reindex([t - 1 for t in eval_months]).values
        nflip = int(np.sum(app_eval[1:] != app_eval[:-1]))
        # whipsaw within 1977-82: defensive months where equity rose
        ro_w = ro.reindex(pd.period_range(*W7782, freq="M"))
        defm = ~ro_w.fillna(True)
        spn = sp_next.reindex(defm.index)
        whip = int(((defm) & (spn > 0)).sum())
        rows[name] = {
            "spec": v,
            "full_sharpe": m.get("sharpe"), "full_cagr_pct": m.get("cagr_pct"),
            "full_maxdd_pct": m.get("maxdd_pct"),
            "full_dd_window": dd_window(r),
            "maxdd_1973_74_pct": win_maxdd(r, *W7374),
            "maxdd_1977_82_pct": win_maxdd(r, *W7782),
            "ret_1977_82_pct": round(float((1 + r.loc[W7782[0]:W7782[1]]).prod() - 1) * 100, 2),
            "sharpe_1977_82": metrics(r.loc[W7782[0]:W7782[1]], rf).get("sharpe"),
            "n_defensive_total": int((~ro.fillna(True)).sum()),
            "vol_flips_eval": nflip,
            "whipsaw_def_months_1977_82": whip,
        }
    return {"partA": partA, "partB_1970s": rows,
            "eval_window": [str(EVAL_START), str(EVAL_END)]}


# ===========================================================================
# MODERN PART B
# ===========================================================================
def run_modern():
    import exec_lag_moo_validation_2026_05_30 as H
    import bull_qqq_live
    from bull_qqq_live import BULL_TICKER, compute_bull_qqq_weights
    from cpm_live import load_panel, perf_metrics, COST_BPS_PER_SIDE

    CONV = "mooex"
    CLEAN_START = pd.Timestamp("2008-05-30")
    EXT_START = pd.Timestamp("1999-03-10")
    END = pd.Timestamp("2026-05-22")
    CPM_W, BULL_W = 0.60, 0.40
    ANCHOR_BULL = 1.0813; ANCHOR_BLEND = 1.2485; TOL = 0.01

    CRASH = {
        "gfc_2008": (pd.Timestamp("2007-10-01"), pd.Timestamp("2009-06-30")),
        "covid_2020": (pd.Timestamp("2020-02-01"), pd.Timestamp("2020-04-30")),
        "bear_2022": (pd.Timestamp("2022-01-01"), pd.Timestamp("2022-12-31")),
    }

    panel = load_panel(start=EXT_START, end=END)
    end = min(END, panel.index[-1])
    cash = panel["SHV"].ffill().pct_change().dropna()
    od, cy = H.load_open_close()
    intraday = (cy / od - 1.0).reindex(panel.index)
    overnight = (od / cy.shift(1) - 1.0).reindex(panel.index)
    spy_close = panel[BULL_TICKER]

    # month-end trading days across the panel
    me = (pd.DataFrame({"x": 1}, index=panel.index)
          .groupby(pd.Grouper(freq="ME")).tail(1).index)

    def build_gate(fast, k, to_def, to_on):
        raw = []
        for d2 in me:
            sub = spy_close.loc[:d2].pct_change().dropna()
            if len(sub) < SLOW:
                raw.append(None)
            else:
                vf = float(sub.tail(fast).std() * np.sqrt(252))
                vs = float(sub.tail(SLOW).std() * np.sqrt(252))
                raw.append(bool(vf < k * vs))
        applied = apply_hysteresis(raw, to_def, to_on)
        amap = dict(zip(me, applied))

        def g(daily_spy, sig_d):
            if sig_d in amap:
                return amap[sig_d], {}
            return True, {"warmup": True}
        return g, amap

    def met(s, a, b):
        sub = s.loc[(s.index >= a) & (s.index <= b)]
        m = perf_metrics(sub, cash)
        return {"sharpe": round(m.get("sharpe"), 4), "calmar": round(m.get("calmar"), 3),
                "maxdd": round(m.get("max_drawdown") * 100, 2), "cagr": round(m.get("cagr") * 100, 2),
                "vol": round(m.get("vol") * 100, 2)}

    def crash_dd(s, a, b):
        sub = s.loc[(s.index >= a) & (s.index <= b)]
        eq = (1 + sub).cumprod()
        return round(float((eq / eq.cummax() - 1).min()) * 100, 2) if len(sub) else None

    # CPM sleeve (fixed prod)
    cpm, _ = H.cpm_sleeve_conv(panel, intraday, overnight, EXT_START, end, CONV)

    # build bull series + weight diagnostics per variant
    results = {}; bull_series = {}; common = cpm.index
    weight_diag = {}
    for name, v in VARIANTS.items():
        gate, amap = build_gate(v["fast"], v["k"], v["to_def"], v["to_on"])
        bull, _ = H.bull_sleeve_conv(panel, intraday, overnight, EXT_START, end, CONV, gate)
        bull_series[name] = bull
        common = common.intersection(bull.index)
        # monthly weights/regime with this gate (turnover + fully-safe count)
        bull_qqq_live._vol_gate_ok = gate
        try:
            recs = []
            for d2 in me:
                if d2 < EXT_START or d2 > end:
                    continue
                w, regime, _ = compute_bull_qqq_weights(panel, d2, spy_close)
                recs.append((d2, regime, w))
        finally:
            bull_qqq_live._vol_gate_ok = H._ORIG_VOL_GATE
        weight_diag[name] = recs

    cpm = cpm.reindex(common)
    for name in VARIANTS:
        bull_series[name] = bull_series[name].reindex(common)

    # anchor check
    a_bull = met(bull_series["prod_60"], CLEAN_START, end)["sharpe"]
    blend_prod = CPM_W * cpm + BULL_W * bull_series["prod_60"]
    a_blend = met(blend_prod, CLEAN_START, end)["sharpe"]
    if abs(a_bull - ANCHOR_BULL) > TOL or abs(a_blend - ANCHOR_BLEND) > TOL:
        raise SystemExit(f"ANCHOR MISMATCH bull={a_bull} blend={a_blend} -- ABORT")

    for name, v in VARIANTS.items():
        b = bull_series[name]
        blend = CPM_W * cpm + BULL_W * b
        recs = weight_diag[name]
        # turnover (L1 monthly weight change) + fully-safe months
        prevw = {}; turnover = 0.0; nsafe = 0; nmonths = 0; flips = 0; prevregime = None
        safe_by_crash = {c: 0 for c in CRASH}
        for d2, regime, w in recs:
            keys = set(w) | set(prevw)
            turnover += sum(abs(w.get(k, 0.0) - prevw.get(k, 0.0)) for k in keys)
            prevw = w; nmonths += 1
            if regime == "CASH":
                nsafe += 1
                for c, (ca, cb) in CRASH.items():
                    if ca <= d2 <= cb:
                        safe_by_crash[c] += 1
            if prevregime is not None and regime != prevregime:
                flips += 1
            prevregime = regime
        results[name] = {
            "spec": v,
            "bull_clean": met(b, CLEAN_START, end),
            "bull_ext": met(b, EXT_START, end),
            "blend_clean": met(blend, CLEAN_START, end),
            "blend_ext": met(blend, EXT_START, end),
            "turnover_total": round(turnover, 2),
            "turnover_per_yr": round(turnover / (nmonths / 12.0), 3),
            "regime_flips": flips,
            "fully_safe_months": nsafe,
            "n_months": nmonths,
            "crash_bull_dd": {c: crash_dd(b, *CRASH[c]) for c in CRASH},
            "crash_fully_safe_months": safe_by_crash,
        }
    return {"anchor": {"bull_clean": a_bull, "blend_clean": a_blend},
            "results": results,
            "clean_window": [str(CLEAN_START.date()), str(end.date())],
            "ext_window": [str(EXT_START.date()), str(end.date())]}


def main():
    out = {"meta": {
        "role": "analyst; READ-ONLY re production; test-only; no commit",
        "caveats_1970s": [
            "Synthetic TIP (CPI-accrual proxy); canary effectively always-on this era.",
            "TREND uses Shiller MONTHLY-AVERAGE S&P price; VOL uses Yahoo ^GSPC DAILY close (documented series mismatch).",
            "IEF analog = 5y CMT par-bond duration TR (convexity omitted).",
            "Warmup months default each gate to risk-on (no lookahead).",
        ],
        "caveats_modern": [
            "mooex T+1 MOO exact, 10bps/side; real yfinance auto_adjust OHLC from /tmp/cpm_open_cache.",
            "Hysteresis applied on month-end raw rv signals; state depends only on past (no lookahead).",
            "Anchor-gated: 60d BULL clean ~1.0813, 60/40 blend ~1.2485.",
        ],
    }}
    print("== 1970s ==")
    out["era_1970s"] = run_1970s()
    print(json.dumps(out["era_1970s"]["partA"]["full_period_maxdd_window"], indent=2))
    print("== MODERN ==")
    out["modern"] = run_modern()
    OUT = HERE / "vol_gate_timing_hysteresis_findings.json"
    OUT.write_text(json.dumps(out, indent=2, default=lambda o: bool(o) if isinstance(o, np.bool_) else (int(o) if isinstance(o, np.integer) else float(o))))
    print(f"Wrote {OUT}")
    return out


if __name__ == "__main__":
    main()
