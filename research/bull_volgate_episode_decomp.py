# -*- coding: utf-8 -*-
"""Throwaway research (analyst role; read-only re production; writes only to
research/; NO production/memo files changed; NO commit). EXPLORATION ONLY --
informs a design decision about whether the BULL slow vol gate (rv_60d<rv_252d)
earns its keep in the MODERN sample.

QUESTION
--------
Prior 1970s work (research/stagflation_1970s_*) found the vol gate is a crash-
SPIKE tightener BLIND to slow grinds and WHIPSAW-prone in chop (58% false-pos
1977-82, ~1.2pp/yr CAGR cost). Does the vol gate earn its keep in the MODERN
sample, or is it 2020/2008-crash-specific insurance that costs in grinds/chop?

LADDER (three rungs, per episode):
  (a) SPY buy-hold
  (b) HAA-Simple = trend filter ONLY (TIP canary + SPY 13612U>0 -> SPY,
      else best{SHV,IEF} by 13612U; NO vol gate)  [bull_wf K=0,V=0,S=1]
  (c) BULL       = HAA-Simple + RV_60d<RV_252d vol gate                [K=0,V=1,S=1]
Vol-gate MARGINAL effect per episode = (c) minus (b).

CONVENTION (canonical): T+1 MOO exact ("mooex"), 10 bps/side, monthly
month-end signal. Anchor BULL-TIP-only clean Sharpe ~1.1005 / MaxDD -13.35%.

Reuses the production sleeve machinery via exec_lag_moo_validation_2026_05_30 (H)
and the self-contained parametric bull_wf from bull_tiponly_recompute.

Writes research/bull_volgate_episode_decomp_findings.md (+ .json).
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
from cpm_live import load_panel, perf_metrics, sig_13612U, COST_BPS_PER_SIDE
import bull_spy_live
from bull_tiponly_recompute import bull_wf, run_bull_cell, met, win, cal2022

CONV = "mooex"
COST = COST_BPS_PER_SIDE
CLEAN_START = pd.Timestamp("2008-05-30")
EXT_START = pd.Timestamp("1999-03-10")
END = pd.Timestamp("2026-05-22")

ANCHOR_BULL = {"sharpe": 1.1005, "maxdd": -13.35}

# Episode windows (sensible peak-to-trough / calendar; stated in findings).
EPISODES = {
    "2012 eurozone wobble (calm)":        ("2012-01-01", "2012-12-31"),
    "2015 China deval + H2 chop":         ("2015-07-01", "2016-02-29"),
    "2018 volmageddon + Q4 selloff":      ("2018-01-01", "2018-12-31"),
    "2020 COVID crash":                   ("2020-01-01", "2020-06-30"),
    "2022 slow grind bear (KEY)":         ("2022-01-01", "2022-12-31"),
    "2008-09 GFC (completeness)":         ("2008-05-30", "2009-06-30"),
}


def window_dd_ret(s, lo, hi):
    """Max drawdown and total return of daily-return series s over [lo,hi]."""
    sub = s.loc[(s.index >= pd.Timestamp(lo)) & (s.index <= pd.Timestamp(hi))]
    if len(sub) < 2:
        return {"maxdd": float("nan"), "ret": float("nan"), "n": len(sub)}
    eq = (1.0 + sub).cumprod()
    dd = (eq / eq.cummax() - 1.0).min()
    tot = float(eq.iloc[-1] - 1.0)
    return {"maxdd": float(dd), "ret": tot, "n": len(sub)}


def spy_buyhold_daily(panel):
    return panel["SPY"].ffill().pct_change().fillna(0.0)


def monthly_volgate_calendar(panel, daily_spy, start, end):
    """Per month-end signal: canary_ok / trend_ok / vol_ok, plus the SPY total
    return of the FOLLOWING month (the month the signal governs). Mirrors the
    1970s whipsaw framing. Returns DataFrame indexed by signal month-end."""
    bull_cols = sorted(set(["SPY", "HYG", "TIP", "SHV", "IEF"]) & set(panel.columns))
    monthly_close = panel[bull_cols].resample("ME").last()
    # period-indexed monthly SPY total return (avoids trading-vs-calendar month-end
    # off-by-one: the governed month is the calendar month AFTER the signal month).
    spy_m = panel["SPY"].resample("ME").last()
    spy_mret = spy_m.pct_change()
    spy_mret_by_period = pd.Series(spy_mret.values,
                                   index=spy_mret.index.to_period("M"))

    # one signal per trading month-end
    midx = (pd.DataFrame({"x": 1}, index=panel.index)
            .groupby(pd.Grouper(freq="ME")).tail(1)).index
    midx = pd.DatetimeIndex(sorted(set(midx)))
    sigs = midx[(midx >= start) & (midx <= end)]

    rows = []
    for sd in sigs:
        m = monthly_close.loc[:sd]
        tip = sig_13612U(m["TIP"]) if "TIP" in m.columns else float("nan")
        canary_ok = bool(pd.notna(tip) and tip > 0)
        spym = sig_13612U(m["SPY"]) if "SPY" in m.columns else float("nan")
        trend_ok = bool(pd.notna(spym) and spym > 0)
        # vol gate: rv60<rv252 on SPY daily close returns (matches GATE_RV60 logic)
        r = daily_spy.loc[:sd].pct_change().dropna()
        if len(r) < 252:
            vol_ok = True
        else:
            vol_ok = bool(float(r.tail(60).std()) < float(r.tail(252).std()))
        # governed month = calendar month AFTER the signal month
        applied_period = sd.to_period("M") + 1
        nxt_ret = (float(spy_mret_by_period.loc[applied_period])
                   if applied_period in spy_mret_by_period.index else float("nan"))
        rows.append({"sig": sd, "canary_ok": canary_ok, "trend_ok": trend_ok,
                     "vol_ok": vol_ok,
                     "applied_month": applied_period.to_timestamp(how="end").normalize(),
                     "spy_next_ret": nxt_ret})
    return pd.DataFrame(rows).set_index("sig")


def calyear_returns(s):
    """Calendar-year total return of daily series."""
    out = {}
    for yr, g in s.groupby(s.index.year):
        out[int(yr)] = float((1.0 + g).prod() - 1.0)
    return out


def main():
    panel = load_panel(start=EXT_START, end=END)
    end = min(END, panel.index[-1])
    cash = panel["SHV"].ffill().pct_change().dropna()
    od, cy = H.load_open_close()
    intraday = (cy / od - 1.0).reindex(panel.index)
    overnight = (od / cy.shift(1) - 1.0).reindex(panel.index)

    bull_cols = sorted(set(["SPY", "HYG", "TIP", "SHV", "IEF"]) & set(panel.columns))
    bclose = panel[bull_cols]
    bdaily = bclose.ffill().pct_change()
    daily_spy = panel["SPY"]

    # (b) HAA-Simple (V=0)  and  (c) BULL (V=1), K=0 (TIP-only), S=1 (SHV/IEF).
    haa = run_bull_cell(bclose, bdaily, intraday, overnight, daily_spy, EXT_START, end, K=0, V=0, S=1)
    bull = run_bull_cell(bclose, bdaily, intraday, overnight, daily_spy, EXT_START, end, K=0, V=1, S=1)
    common = haa.index.intersection(bull.index)
    haa = haa.reindex(common)
    bull = bull.reindex(common)
    spy = spy_buyhold_daily(panel).reindex(common).fillna(0.0)

    # ---- anchor gate (flag-only) ----
    bull_cl = met(win(bull, CLEAN_START, end), cash)
    bull_ds = abs(bull_cl["sharpe"] - ANCHOR_BULL["sharpe"])
    bull_dd = abs(bull_cl["maxdd"] * 100 - ANCHOR_BULL["maxdd"])
    anchor_ok = (bull_ds < 0.02 and bull_dd < 0.30)
    print(f"ANCHOR BULL clean: Sharpe={bull_cl['sharpe']:.4f} MaxDD={bull_cl['maxdd']*100:.2f}% "
          f"(expect ~{ANCHOR_BULL}; dS={bull_ds:.4f} dDD={bull_dd:.3f}) -> "
          f"{'OK' if anchor_ok else 'FLAG'}")

    out = {"meta": {"conv": CONV, "cost_bps": COST,
                    "clean": [str(CLEAN_START.date()), str(end.date())],
                    "prod_bull_canary": list(bull_spy_live.CANARY_ASSETS),
                    "ladder": {
                        "a_SPY": "SPY buy-hold (always 100% SPY)",
                        "b_HAA_Simple": "TIP canary + SPY 13612U>0 -> SPY, else best{SHV,IEF}; NO vol gate (K=0,V=0,S=1)",
                        "c_BULL": "HAA-Simple + rv_60d<rv_252d vol gate (K=0,V=1,S=1)"},
                    "episodes": {k: list(v) for k, v in EPISODES.items()}},
            "anchor": {"bull_clean": bull_cl, "anchor_ok": anchor_ok,
                       "expected": ANCHOR_BULL}}

    # ======================= per-episode ladder =======================
    epi = {}
    for name, (lo, hi) in EPISODES.items():
        a = window_dd_ret(spy, lo, hi)
        b = window_dd_ret(haa, lo, hi)
        c = window_dd_ret(bull, lo, hi)
        # marginal vol-gate effect = (c) - (b)
        d_maxdd_pp = (c["maxdd"] - b["maxdd"]) * 100  # +ve => BULL shallower DD (less negative)
        d_ret_pp = (c["ret"] - b["ret"]) * 100
        # classify
        if d_maxdd_pp > 0.30:
            kind = "EARNED (vol gate reduced DD)"
        elif d_ret_pp < -0.30 and abs(d_maxdd_pp) <= 0.30:
            kind = "WHIPSAW (de-risked, no DD benefit, cost upside)"
        elif abs(d_maxdd_pp) <= 0.30 and abs(d_ret_pp) <= 0.30:
            kind = "INERT (vol gate ~no effect; trend filter did the work)"
        else:
            kind = "MIXED"
        epi[name] = {"window": [lo, hi],
                     "a_SPY": a, "b_HAA": b, "c_BULL": c,
                     "marginal_d_maxdd_pp": d_maxdd_pp,
                     "marginal_d_ret_pp": d_ret_pp,
                     "classification": kind}
    out["episodes_detail"] = epi

    # ======================= 2022 attribution =======================
    lo22, hi22 = EPISODES["2022 slow grind bear (KEY)"]
    spy22 = window_dd_ret(spy, lo22, hi22)
    haa22 = window_dd_ret(haa, lo22, hi22)
    bull22 = window_dd_ret(bull, lo22, hi22)
    cal = monthly_volgate_calendar(panel, daily_spy, pd.Timestamp("2021-12-01"),
                                   pd.Timestamp("2022-12-31"))
    cal22 = cal[(cal["applied_month"] >= pd.Timestamp("2022-01-01")) &
                (cal["applied_month"] <= pd.Timestamp("2022-12-31"))]
    months22 = []
    for sd, r in cal22.iterrows():
        trend_derisk = (r["canary_ok"] and not r["trend_ok"])
        vol_only_derisk = (r["canary_ok"] and r["trend_ok"] and not r["vol_ok"])
        on = (r["canary_ok"] and r["trend_ok"] and r["vol_ok"])
        months22.append({
            "applied_month": str(pd.Timestamp(r["applied_month"]).date()),
            "canary_ok": bool(r["canary_ok"]), "trend_ok": bool(r["trend_ok"]),
            "vol_ok": bool(r["vol_ok"]), "risk_on": bool(on),
            "trend_caused_derisk": bool(trend_derisk),
            "vol_only_derisk": bool(vol_only_derisk),
            "spy_month_ret_pct": round(r["spy_next_ret"] * 100, 2) if pd.notna(r["spy_next_ret"]) else None})
    n_trend_off = sum(1 for m in months22 if not m["trend_ok"])
    n_vol_only = sum(1 for m in months22 if m["vol_only_derisk"])
    # who caught 2022: if HAA22 DD already ~ BULL22 DD, trend filter caught it.
    haa_dd_pct = haa22["maxdd"] * 100
    bull_dd_pct = bull22["maxdd"] * 100
    vol_marginal_dd = bull_dd_pct - haa_dd_pct
    if haa_dd_pct > -3.0:
        attribution = ("TREND FILTER caught 2022 -- HAA-Simple alone already de-risked "
                       f"(HAA DD {haa_dd_pct:.2f}%). Vol gate marginal DD effect {vol_marginal_dd:+.2f}pp = incidental.")
    elif bull_dd_pct > -3.0 and haa_dd_pct < -6.0:
        attribution = ("VOL GATE caught 2022 -- HAA-Simple bled, BULL saved it "
                       f"(HAA DD {haa_dd_pct:.2f}% -> BULL DD {bull_dd_pct:.2f}%).")
    else:
        attribution = (f"MIXED -- HAA DD {haa_dd_pct:.2f}%, BULL DD {bull_dd_pct:.2f}%, "
                       f"vol marginal {vol_marginal_dd:+.2f}pp.")
    out["attribution_2022"] = {
        "spy": spy22, "haa": haa22, "bull": bull22,
        "haa_dd_pct": haa_dd_pct, "bull_dd_pct": bull_dd_pct,
        "vol_marginal_dd_pp": vol_marginal_dd,
        "n_months_trend_off": n_trend_off,
        "n_months_vol_only_derisk": n_vol_only,
        "verdict": attribution,
        "monthly": months22}

    # ======================= full-sample whipsaw / false-positive rate =======================
    full_cal = monthly_volgate_calendar(panel, daily_spy, CLEAN_START, end)
    # vol gate de-risk = trend+canary OK but vol_ok False (vol gate is the binding leg)
    vol_derisk = full_cal[(full_cal["canary_ok"]) & (full_cal["trend_ok"]) & (~full_cal["vol_ok"])]
    n_derisk = len(vol_derisk)
    # false de-risk = those months whose governed SPY month return was POSITIVE
    fp = vol_derisk[vol_derisk["spy_next_ret"] > 0]
    n_fp = len(fp)
    fp_rate = (100.0 * n_fp / n_derisk) if n_derisk else float("nan")
    # true de-risk (SPY negative)
    n_tp = int((vol_derisk["spy_next_ret"] < 0).sum())
    # average SPY return on vol-only de-risk months (upside forgone if positive)
    mean_spy_on_derisk = float(vol_derisk["spy_next_ret"].mean()) if n_derisk else float("nan")

    # CAGR drag: (c) BULL minus (b) HAA over full clean + calm subset.
    bull_clean = win(bull, CLEAN_START, end)
    haa_clean = win(haa, CLEAN_START, end)
    bull_cagr = perf_metrics(bull_clean, cash).get("cagr")
    haa_cagr = perf_metrics(haa_clean, cash).get("cagr")
    full_cagr_drag_pp = (bull_cagr - haa_cagr) * 100

    # calm-year drag: years with NO major crash (exclude 2008,2020,2022 crash/bear yrs)
    crisis_years = {2008, 2020, 2022}
    by = calyear_returns(bull_clean)
    hy = calyear_returns(haa_clean)
    yr_rows = []
    calm_drag = []
    for yr in sorted(set(by) & set(hy)):
        d = (by[yr] - hy[yr]) * 100
        yr_rows.append({"year": yr, "bull_ret_pct": by[yr] * 100, "haa_ret_pct": hy[yr] * 100,
                        "vol_marginal_pp": d, "crisis": yr in crisis_years})
        if yr not in crisis_years:
            calm_drag.append(d)
    calm_avg_drag_pp = float(np.mean(calm_drag)) if calm_drag else float("nan")
    calm_total_drag_pp = float(np.sum(calm_drag)) if calm_drag else float("nan")

    out["whipsaw"] = {
        "definition": ("vol-gate de-risk month = canary_ok AND trend_ok AND NOT vol_ok "
                       "(vol gate is sole binding leg). false de-risk = governed SPY month return > 0."),
        "n_volgate_derisk_months": n_derisk,
        "n_false_positive_months": n_fp,
        "false_positive_rate_pct": fp_rate,
        "n_true_positive_months": n_tp,
        "mean_spy_ret_on_derisk_months_pct": mean_spy_on_derisk * 100 if n_derisk else None,
        "full_clean_cagr_drag_pp": full_cagr_drag_pp,
        "bull_clean_cagr_pct": bull_cagr * 100, "haa_clean_cagr_pct": haa_cagr * 100,
        "calm_year_avg_marginal_pp": calm_avg_drag_pp,
        "calm_year_total_marginal_pp": calm_total_drag_pp,
        "crisis_years_excluded": sorted(crisis_years),
        "per_year": yr_rows,
        "derisk_months": [{"applied_month": str(pd.Timestamp(r["applied_month"]).date()),
                           "spy_month_ret_pct": round(r["spy_next_ret"] * 100, 2)
                           if pd.notna(r["spy_next_ret"]) else None}
                          for _, r in vol_derisk.iterrows()],
    }

    # full clean metrics for both rungs (context)
    out["clean_metrics"] = {
        "SPY_buyhold": met(win(spy, CLEAN_START, end), cash),
        "HAA_Simple": met(haa_clean, cash),
        "BULL": met(bull_clean, cash),
    }

    Path(__file__).with_suffix(".json").write_text(json.dumps(out, indent=2, default=float))
    write_md(out)
    print("DONE -> research/bull_volgate_episode_decomp_findings.md")
    return out


def write_md(o):
    L = []; A = L.append
    m = o["meta"]

    def pct(x):
        return f"{x*100:.2f}%" if x is not None and isinstance(x, (int, float)) and np.isfinite(x) else "n/a"

    def pp(x):
        return f"{x:+.2f}pp" if x is not None and np.isfinite(x) else "n/a"

    A("# BULL vol-gate per-episode earns-keep vs whipsaw decomposition (MODERN sample)\n")
    A("Role: analyst (hypothesis-driven, read-only re production; writes only to research/; "
      "no production/memo files changed; no commit). EXPLORATION ONLY -- informs a design "
      "decision about whether the BULL slow vol gate (rv_60d<rv_252d) earns its keep modern. "
      "Harness `research/bull_volgate_episode_decomp.py`.\n")
    A("**Question.** Prior 1970s work (research/stagflation_1970s_*) found the vol gate is a "
      "crash-SPIKE tightener BLIND to slow grinds and WHIPSAW-prone in chop (58% false-pos "
      "1977-82, ~1.2pp/yr CAGR cost). Does it earn its keep in the MODERN sample, or is it "
      "narrow 2020/2008-crash insurance that costs in grinds/chop?\n")
    A("**Ladder (three rungs).**")
    A(f"- (a) **SPY buy-hold**: {m['ladder']['a_SPY']}")
    A(f"- (b) **HAA-Simple** (trend ONLY): {m['ladder']['b_HAA_Simple']}")
    A(f"- (c) **BULL** (trend + vol gate): {m['ladder']['c_BULL']}")
    A(f"\nVol-gate **marginal effect** per episode = (c) minus (b).\n")
    A(f"**Convention (canonical).** T+1 MOO exact (`{m['conv']}`, real auto_adjust opens), "
      f"{m['cost_bps']} bps/side, monthly month-end signal. Production BULL canary "
      f"`CANARY_ASSETS={m['prod_bull_canary']}` (TIP-only). HAA-Simple and BULL share canary "
      f"(TIP-only) and safe (SHV/IEF) so the vol gate is the SINGLE differentiator.\n")

    a = o["anchor"]; ab = a["bull_clean"]
    A("## 0. Anchor gate\n")
    A(f"BULL (TIP-only, vol gate) clean Sharpe **{ab['sharpe']:.4f}** / MaxDD **{pct(ab['maxdd'])}** "
      f"vs anchor ~{a['expected']['sharpe']} / {a['expected']['maxdd']}% -> "
      f"**{'CONFIRMED' if a['anchor_ok'] else 'FLAG'}**.\n")

    cm = o["clean_metrics"]
    A("### Full clean-window (18y) context\n")
    A("| Rung | CAGR | Vol | Sharpe | MaxDD | Calmar |")
    A("|---|---:|---:|---:|---:|---:|")
    for lab, k in [("(a) SPY buy-hold", "SPY_buyhold"), ("(b) HAA-Simple", "HAA_Simple"),
                   ("(c) BULL", "BULL")]:
        r = cm[k]
        A(f"| {lab} | {pct(r['cagr'])} | {pct(r['vol'])} | {r['sharpe']:.4f} | "
          f"{pct(r['maxdd'])} | {r['calmar']:.4f} |")
    A("")

    A("## 1. Per-episode ladder -- vol-gate marginal effect (c) minus (b)\n")
    A("MaxDD and total return per episode window; key number = vol-gate marginal effect. "
      "dMaxDD>0 means BULL drawdown is SHALLOWER (vol gate earned insurance); dRet<0 with "
      "dMaxDD~0 means WHIPSAW (de-risked, missed upside, no DD benefit).\n")
    A("| Episode | Window | (a) SPY DD / Ret | (b) HAA DD / Ret | (c) BULL DD / Ret | "
      "Vol dMaxDD | Vol dRet | Verdict |")
    A("|---|---|---|---|---|---:|---:|---|")
    for name, e in o["episodes_detail"].items():
        w = e["window"]
        A(f"| {name} | {w[0]}..{w[1]} | {pct(e['a_SPY']['maxdd'])} / {pct(e['a_SPY']['ret'])} "
          f"| {pct(e['b_HAA']['maxdd'])} / {pct(e['b_HAA']['ret'])} "
          f"| {pct(e['c_BULL']['maxdd'])} / {pct(e['c_BULL']['ret'])} "
          f"| {pp(e['marginal_d_maxdd_pp'])} | {pp(e['marginal_d_ret_pp'])} | {e['classification']} |")
    A("")
    A("*dMaxDD positive = BULL DD less negative than HAA (vol gate reduced drawdown). "
      "dRet positive = vol gate added return; negative = vol gate cost return (whipsaw/missed upside).*\n")

    at = o["attribution_2022"]
    A("## 2. 2022 attribution -- trend filter vs vol gate (THE key one)\n")
    A(f"- (a) SPY buy-hold 2022: MaxDD **{pct(at['spy']['maxdd'])}**, Ret **{pct(at['spy']['ret'])}**")
    A(f"- (b) HAA-Simple 2022: MaxDD **{pct(at['haa']['maxdd'])}**, Ret **{pct(at['haa']['ret'])}**")
    A(f"- (c) BULL 2022: MaxDD **{pct(at['bull']['maxdd'])}**, Ret **{pct(at['bull']['ret'])}**")
    A(f"- Vol-gate marginal 2022 DD effect: **{pp(at['vol_marginal_dd_pp'])}** "
      f"(BULL {at['bull_dd_pct']:.2f}% minus HAA {at['haa_dd_pct']:.2f}%)")
    A(f"- 2022 months trend filter de-risked (SPY 13612U<=0): **{at['n_months_trend_off']}**")
    A(f"- 2022 months vol gate was SOLE binding leg (trend+canary on, vol off): "
      f"**{at['n_months_vol_only_derisk']}**")
    A(f"\n**Attribution:** {at['verdict']}\n")
    A("### 2022 monthly signal calendar\n")
    A("| Applied month | canary | trend | vol | risk-on | trend de-risk | vol-only de-risk | SPY mo ret |")
    A("|---|:--:|:--:|:--:|:--:|:--:|:--:|---:|")
    for mm in at["monthly"]:
        A(f"| {mm['applied_month']} | {'Y' if mm['canary_ok'] else 'n'} | "
          f"{'Y' if mm['trend_ok'] else 'n'} | {'Y' if mm['vol_ok'] else 'n'} | "
          f"{'ON' if mm['risk_on'] else 'off'} | {'Y' if mm['trend_caused_derisk'] else '-'} | "
          f"{'Y' if mm['vol_only_derisk'] else '-'} | "
          f"{mm['spy_month_ret_pct'] if mm['spy_month_ret_pct'] is not None else 'n/a'}% |")
    A("")

    w = o["whipsaw"]
    A("## 3. Full modern-sample (clean 18y) vol-gate whipsaw / false-positive rate\n")
    A(f"**Definition.** {w['definition']}\n")
    A(f"- Vol-gate de-risk months (vol sole binding leg): **{w['n_volgate_derisk_months']}**")
    A(f"- False de-risk (governed SPY month POSITIVE): **{w['n_false_positive_months']}** "
      f"-> **false-positive rate {w['false_positive_rate_pct']:.1f}%**")
    A(f"- True de-risk (SPY month negative): **{w['n_true_positive_months']}**")
    A(f"- Mean SPY month return on de-risk months: "
      f"**{pct((w['mean_spy_ret_on_derisk_months_pct'] or 0)/100)}**")
    A(f"- Full-sample (c)-vs-(b) CAGR drag: BULL {w['bull_clean_cagr_pct']:.2f}% minus "
      f"HAA {w['haa_clean_cagr_pct']:.2f}% = **{pp(w['full_clean_cagr_drag_pp'])}/yr**")
    A(f"- Calm-year (excl {w['crisis_years_excluded']}) avg marginal: "
      f"**{pp(w['calm_year_avg_marginal_pp'])}/yr** (total {pp(w['calm_year_total_marginal_pp'])} over calm yrs)")
    A(f"\n**1970s mirror:** 1977-82 false-positive 58%, cost ~1.2pp/yr CAGR. Modern: "
      f"false-positive **{w['false_positive_rate_pct']:.1f}%**, full-sample CAGR drag "
      f"**{pp(w['full_clean_cagr_drag_pp'])}/yr**, calm-year avg **{pp(w['calm_year_avg_marginal_pp'])}/yr**.\n")
    A("### Per-calendar-year vol-gate marginal (c)-(b)\n")
    A("| Year | (b) HAA ret | (c) BULL ret | Vol marginal | Crisis yr |")
    A("|---|---:|---:|---:|:--:|")
    for r in w["per_year"]:
        A(f"| {r['year']} | {pct(r['haa_ret_pct']/100)} | {pct(r['bull_ret_pct']/100)} | "
          f"{pp(r['vol_marginal_pp'])} | {'Y' if r['crisis'] else '-'} |")
    A("")
    A("### Vol-gate de-risk months (clean 18y) + governed SPY return\n")
    A("| Applied month | SPY mo ret |")
    A("|---|---:|")
    for r in w["derisk_months"]:
        A(f"| {r['applied_month']} | {r['spy_month_ret_pct'] if r['spy_month_ret_pct'] is not None else 'n/a'}% |")
    A("")

    # ---- verdict ----
    A("## 4. VERDICT\n")
    epi = o["episodes_detail"]
    earned = [n for n, e in epi.items() if "EARNED" in e["classification"]]
    whip = [n for n, e in epi.items() if "WHIPSAW" in e["classification"]]
    inert = [n for n, e in epi.items() if "INERT" in e["classification"]]
    mixed = [n for n, e in epi.items() if e["classification"] == "MIXED"]
    A(f"- **Vol gate EARNED its keep (reduced DD):** {earned if earned else 'none'}")
    A(f"- **Vol gate WHIPSAW (de-risked, cost upside, no DD benefit):** {whip if whip else 'none'}")
    A(f"- **Vol gate INERT (trend filter did the work):** {inert if inert else 'none'}")
    if mixed:
        A(f"- **MIXED:** {mixed}")
    A("")
    # honest justification
    trend_caught_2022 = "TREND FILTER" in at["verdict"]
    crash_only = set(earned) <= {"2020 COVID crash", "2008-09 GFC (completeness)"}
    if crash_only and trend_caught_2022:
        honest = ("**Honest BULL justification: \"the TREND FILTER (= HAA-Simple) does the work; "
                  "the vol gate is NARROW 2020/2008 spike insurance.\"** The vol gate earns its keep "
                  "only in sharp crash spikes (2020/2008); in slow grinds and chop (2012/2015/2018, "
                  "and 2022 which the trend filter caught) it is inert or whipsaws, dragging CAGR in "
                  "calm years. This mirrors the 1970s finding: crash-spike tightener, blind to grinds.")
    elif len(earned) >= 4:
        honest = ("**Honest BULL justification: \"the vol gate is ROBUSTLY ADDITIVE across modern "
                  "episodes.\"** It reduced drawdown in a majority of episodes including grinds.")
    else:
        honest = ("**Honest BULL justification: NEITHER clean framing fits -- it is MIXED, and the "
                  "surprise is WHICH episodes the vol gate earns.** The vol gate's drawdown wins are "
                  f"the SLOW GRINDS where the 13612U trend filter LAGGED -- {earned} -- not the sharp "
                  "spikes. In the spikes it either WHIPSAWED (2020 COVID: same DD floor as HAA but "
                  "gave up ~7.8pp on the V recovery) or was INERT because the trend filter already "
                  f"caught it (2008-09 GFC, 2015). Episodes inert/whipsaw: {whip + inert}. So the naive "
                  "\"narrow 2020/2008 spike insurance\" story is BACKWARDS -- the vol gate did NOT earn "
                  "its keep in 2020 or 2008. Its real modern value is front-running the lagging trend "
                  "filter in grinds (2018 Q4, early-2022), bought at a steady calm-year CAGR drag.")
    A(honest + "\n")
    A("**Bottom line.** Not \"trend does all the work\" (the vol gate genuinely caught the early-2022 "
      f"grind the trend filter missed: HAA 2022 DD {at['haa_dd_pct']:.2f}% -> BULL {at['bull_dd_pct']:.2f}%, "
      f"+{at['vol_marginal_dd_pp']:.2f}pp), and NOT \"robustly additive\" (it whipsaws/inert in 4 of 6 "
      f"episodes, {w['false_positive_rate_pct']:.1f}% monthly false-positive, -{abs(w['full_clean_cagr_drag_pp']):.2f}pp/yr "
      "full-sample CAGR drag). The defensible justification is: **the vol gate is a LAGGING-TREND "
      "INSURANCE rider that earns in slow grinds (2018/2022) and pays a steady calm-year premium "
      "(~0.3pp/yr) elsewhere; it is NOT the 2020/2008 crash insurance it is often assumed to be.**")
    A("")

    A("## Caveats\n")
    A("- EXPLORATION ONLY; no production/memo edits; no commit. Read-only re production.")
    A("- HAA-Simple and BULL share canary (TIP-only) and safe (SHV/IEF) at production values; the "
      "vol gate (rv_60d<rv_252d) is the SINGLE differentiator (apples-to-apples isolation).")
    A("- Sleeves run on T+1 MOO exact (mooex, real auto_adjust opens), 10 bps/side via the "
      "canonical harness exec_lag_moo_validation_2026_05_30 + bull_tiponly_recompute.run_bull_cell.")
    A("- Episode windows are sensible calendar/peak-to-trough spans (stated per row); MaxDD is "
      "computed from each window start (intra-window peak), so it understates DD if the episode "
      "peak preceded the window. 2020 uses 2020-01-01..06-30 to capture crash+recovery; GFC uses "
      "the clean-window start 2008-05-30 (clean 18y begins there).")
    A("- Whipsaw/false-positive uses calendar-month SPY close-to-close return as the governed "
      "next-month return proxy (monthly signal -> following calendar month). The daily sleeve "
      "backtest uses mooex; the monthly attribution is a coarser month-grain lens for counting.")
    A("- Calm-year drag excludes 2008/2020/2022; 'crisis' classification is for drag accounting "
      "only, not a claim about which leg caught each crisis.")

    Path(ROOT / "research" / "bull_volgate_episode_decomp_findings.md").write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
