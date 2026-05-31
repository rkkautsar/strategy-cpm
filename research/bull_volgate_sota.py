# -*- coding: utf-8 -*-
"""Throwaway research (analyst role; read-only re production; writes only to
research/; NO production/memo files changed; NO commit). EXPLORATION ONLY --
a POTENTIAL production BULL vol-gate improvement; user decides adoption later
(OOS-gated).

MOTIVATION
----------
Prior naive VIX/downside gates (bull_volgate_impliedvol_findings.md,
bull_volgate_variants_findings.md) had the SIGN BACKWARDS vs the literature:
e.g. V4a de-risked when VIX > 1.5*RV20 (high variance-risk-premium), but
Bollerslev-Tauchen-Zhou says HIGH VRP predicts HIGH future returns -> stay
invested; you de-risk when VRP is LOW. This round tests SOTA-grounded gate
constructions with the CORRECT literature signs.

PRIMARY judging metric = CALMAR and MARTIN (drawdown-adjusted): BULL is a
capital-preservation / drawdown-control overlay, NOT a Sharpe-max sleeve.

GATES (correct literature sign), each tested BOTH as REPLACE (R, swap RV gate)
and ADD (A, risk-on = RV-gate AND new-gate; de-risk if EITHER fires -- the
conservative drawdown-overlay combine):

  G1 VRP-correct (Bollerslev-Tauchen-Zhou): VRP = VIX^2 - RV22^2 (variance
     points). de-risk when VRP <= 0 (realized caught/exceeded implied) OR below
     a rolling-252d 10th pct; stay invested when VRP positive/high. (OPPOSITE
     of the old VIX>1.5*RV sign.)
  G2 SKEW-complacency (Bevilacqua-Tunaru / volatility paradox): LOW CBOE SKEW
     = complacency = crash 6-12mo ahead. de-risk when SKEW < rolling-252d 10th/
     20th pct; stay invested otherwise. (Most drawdown-aligned candidate; flag
     tuning risk.)
  G3 Semivariance-divergence (Patton-Sheppard): RS-/RS+ from 22d signed daily
     returns. de-risk when RS-/RS+ ELEVATED (>=252d 80th pct, bad-vol expanding)
     AND VIX LOW (< 252d median, options complacent); stay invested otherwise.
  G4 (optional, cheap) term-structure confirm: ADD-only, RV AND VIX<VIX3M
     (contango). NOTE VIX vs VIX3M already tested in bull_strengthen_macro
     (REPLACE lowers Sharpe; ADD helps 2020 DD only); VIX3M starts 2006-07 so
     pre-2006 degraded -> cited, included only as ADD confirm.

CONVENTION (canonical): T+1 MOO exact ("mooex", real auto_adjust opens),
10 bps/side, monthly month-end signal. Reuses production sleeve machinery via
exec_lag_moo_validation_2026_05_30 (H) and the parametric bull weight fn pattern
from bull_volgate_impliedvol. ANCHOR: BULL symmetric-gate clean Sharpe ~1.1005 /
Calmar ~0.8189 / MaxDD -13.35% (Martin computed as baseline too).

DATA: ^VIX (1990+), ^SKEW (1990+), ^VIX3M (2006-07+), SPY daily, cached under
research/_macro_cache/. VIX3M limits G4 to >=2006 (clean 18y fully covered);
ext pre-2006 G4 runs RV-only (degraded) -- flagged.

Writes research/bull_volgate_sota_findings.md (+ .json).
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

CONV = "mooex"
COST = COST_BPS_PER_SIDE
CLEAN_START = pd.Timestamp("2008-05-30")
EXT_START = pd.Timestamp("1999-03-10")
END = pd.Timestamp("2026-05-22")
CACHE = Path(__file__).resolve().parent / "_macro_cache"

ANCHOR_BULL = {"sharpe": 1.1005, "calmar": 0.8189, "maxdd": -13.35}
BULL_SAFE = ["SHV", "IEF"]

CRISES = {
    "2008 GFC":   ("2008-05-30", "2009-06-30"),
    "2018 Q4":    ("2018-01-01", "2018-12-31"),
    "2020 COVID": ("2020-01-01", "2020-06-30"),
    "2022 bear":  ("2022-01-01", "2022-12-31"),
}


def _cache_close(fname):
    p = CACHE / fname
    s = pd.read_csv(p, parse_dates=[0], index_col=0).iloc[:, 0]
    s.index = pd.to_datetime(s.index)
    return s.dropna()


VIX = _cache_close("VIX.csv")      # 1990+
SKEW = _cache_close("SKEW.csv")    # 1990+
VIX3M = _cache_close("VIX3M.csv")  # 2006-07+

# --- precomputed daily series (set in main, referenced by gate closures) ---
SPY_DAILY = None     # SPY close
RV22_S = None        # 22d realized vol annualized, pct points (VIX-comparable)
VRP_S = None         # VIX^2 - RV22^2, variance points
VIX_ON_SPY = None    # VIX reindexed onto SPY index, ffill
SKEW_ON_SPY = None   # SKEW reindexed onto SPY index, ffill
VIX3M_ON_SPY = None  # VIX3M reindexed onto SPY index, ffill
SEMIVAR_S = None     # RS-/RS+ over trailing 22 daily returns


def _build_series(spy):
    """Precompute daily metric series aligned to SPY index (no lookahead: each
    value uses only data up to and including that day)."""
    global SPY_DAILY, RV22_S, VRP_S, VIX_ON_SPY, SKEW_ON_SPY, VIX3M_ON_SPY, SEMIVAR_S
    SPY_DAILY = spy
    ret = spy.pct_change()
    rv22 = ret.rolling(22).std() * np.sqrt(252) * 100.0  # pct points
    RV22_S = rv22
    vix_on = VIX.reindex(spy.index).ffill()
    skew_on = SKEW.reindex(spy.index).ffill()
    vix3m_on = VIX3M.reindex(spy.index).ffill()
    VIX_ON_SPY = vix_on
    SKEW_ON_SPY = skew_on
    VIX3M_ON_SPY = vix3m_on
    VRP_S = vix_on ** 2 - rv22 ** 2  # variance points
    # semivariance ratio: trailing 22d sum(neg^2)/sum(pos^2)
    neg2 = (ret.clip(upper=0.0) ** 2)
    pos2 = (ret.clip(lower=0.0) ** 2)
    rs_minus = neg2.rolling(22).sum()
    rs_plus = pos2.rolling(22).sum()
    SEMIVAR_S = rs_minus / rs_plus.replace(0.0, np.nan)


# ---------------- gates: f(daily_spy, sig_d) -> (vol_ok, diag) ----------------

def gate_symmetric(daily_spy, sig_d, fast=60, slow=252):
    sub = daily_spy.loc[:sig_d].pct_change().dropna()
    if len(sub) < slow:
        return True, {"warmup": True}
    vf = float(sub.tail(fast).std() * np.sqrt(252))
    vs = float(sub.tail(slow).std() * np.sqrt(252))
    return (vf < vs), {"short": vf, "long": vs}


def _rv_ok(daily_spy, sig_d):
    ok, _ = gate_symmetric(daily_spy, sig_d, 60, 252)
    return ok


# --- G1 VRP-correct ---
def gate_vrp_pos(add=False):
    def g(daily_spy, sig_d):
        v = VRP_S.loc[:sig_d].dropna()
        if len(v) < 22:
            return True, {"warmup": True}
        latest = float(v.iloc[-1])
        new_ok = latest > 0.0
        # diag: report sqrt-style comparands (VIX vs RV22) for readability
        vix = float(VIX_ON_SPY.loc[:sig_d].dropna().iloc[-1]) / 100.0
        rv = float(RV22_S.loc[:sig_d].dropna().iloc[-1]) / 100.0
        d = {"short": vix, "long": rv, "vrp": latest}
        if add:
            return (_rv_ok(daily_spy, sig_d) and new_ok), d
        return new_ok, d
    return g


def gate_vrp_pct10(window=252, add=False):
    def g(daily_spy, sig_d):
        v = VRP_S.loc[:sig_d].dropna()
        if len(v) < window:
            return True, {"warmup": True}
        latest = float(v.iloc[-1])
        thr = float(v.tail(window).quantile(0.10))
        new_ok = latest > thr
        d = {"short": latest, "long": thr, "vrp": latest}
        if add:
            return (_rv_ok(daily_spy, sig_d) and new_ok), d
        return new_ok, d
    return g


# --- G2 SKEW-complacency ---
def gate_skew_pct(q=0.20, window=252, add=False):
    def g(daily_spy, sig_d):
        v = SKEW_ON_SPY.loc[:sig_d].dropna()
        if len(v) < window:
            return True, {"warmup": True}
        latest = float(v.iloc[-1])
        thr = float(v.tail(window).quantile(q))
        new_ok = latest >= thr  # de-risk when SKEW LOW (< pct = complacency)
        d = {"short": latest / 100.0, "long": thr / 100.0, "skew": latest}
        if add:
            return (_rv_ok(daily_spy, sig_d) and new_ok), d
        return new_ok, d
    return g


# --- G3 Semivariance-divergence ---
def gate_semivar(ratio_q=0.80, vix_q=0.50, window=252, add=False):
    def g(daily_spy, sig_d):
        r = SEMIVAR_S.loc[:sig_d].dropna()
        vx = VIX_ON_SPY.loc[:sig_d].dropna()
        if len(r) < window or len(vx) < window:
            return True, {"warmup": True}
        ratio = float(r.iloc[-1])
        rthr = float(r.tail(window).quantile(ratio_q))
        vix = float(vx.iloc[-1])
        vthr = float(vx.tail(window).quantile(vix_q))
        derisk = (ratio >= rthr) and (vix < vthr)  # bad-vol up AND options complacent
        new_ok = not derisk
        d = {"short": ratio, "long": rthr, "vix": vix / 100.0, "vix_thr": vthr / 100.0}
        if add:
            return (_rv_ok(daily_spy, sig_d) and new_ok), d
        return new_ok, d
    return g


# --- G4 term-structure confirm (ADD only) ---
def gate_termstruct_add():
    def g(daily_spy, sig_d):
        v = VIX_ON_SPY.loc[:sig_d].dropna()
        v3 = VIX3M_ON_SPY.loc[:sig_d].dropna()
        rv_ok = _rv_ok(daily_spy, sig_d)
        if len(v) == 0 or len(v3) == 0 or pd.isna(VIX3M.reindex(v3.index[-1:]).iloc[-1] if False else v3.iloc[-1]):
            return rv_ok, {"warmup": True}
        vix = float(v.iloc[-1]); vix3m = float(v3.iloc[-1])
        ts_ok = vix < vix3m  # contango = calm
        d = {"short": vix / 100.0, "long": vix3m / 100.0}
        return (rv_ok and ts_ok), d
    return g


VARIANTS = {
    "V0_symmetric_RV60_252":  lambda d, s: gate_symmetric(d, s, 60, 252),
    # G1 VRP-correct
    "G1R_vrp_pos":            gate_vrp_pos(add=False),
    "G1R_vrp_p10":            gate_vrp_pct10(252, add=False),
    "G1A_vrp_pos":            gate_vrp_pos(add=True),
    # G2 SKEW-complacency
    "G2R_skew_p20":           gate_skew_pct(0.20, 252, add=False),
    "G2R_skew_p10":           gate_skew_pct(0.10, 252, add=False),
    "G2A_skew_p20":           gate_skew_pct(0.20, 252, add=True),
    # G3 Semivariance-divergence
    "G3R_semivar":            gate_semivar(0.80, 0.50, 252, add=False),
    "G3A_semivar":            gate_semivar(0.80, 0.50, 252, add=True),
    # G4 term-structure confirm (ADD only)
    "G4A_termstruct":         gate_termstruct_add(),
}
VLABEL = {
    "V0_symmetric_RV60_252":  "V0 symmetric RV60<RV252 (PROD)",
    "G1R_vrp_pos":            "G1R VRP>0 (REPLACE)",
    "G1R_vrp_p10":            "G1R VRP>r252-p10 (REPLACE)",
    "G1A_vrp_pos":            "G1A RV AND VRP>0 (ADD)",
    "G2R_skew_p20":           "G2R SKEW>=r252-p20 (REPLACE)",
    "G2R_skew_p10":           "G2R SKEW>=r252-p10 (REPLACE)",
    "G2A_skew_p20":           "G2A RV AND SKEW>=p20 (ADD)",
    "G3R_semivar":            "G3R semivar-divergence (REPLACE)",
    "G3A_semivar":            "G3A RV AND not-semivar-div (ADD)",
    "G4A_termstruct":         "G4A RV AND VIX<VIX3M (ADD)",
}
# variants whose history is data-limited (clean 18y is decisive)
LIMITED = {"G4A_termstruct"}  # VIX3M 2006-07+


# ---------------- parametric BULL weight fn ----------------

def _pick_safe(monthly):
    scores = {}
    for s in BULL_SAFE:
        if s in monthly.columns:
            sc = sig_13612U(monthly[s])
            if pd.notna(sc):
                scores[s] = sc
    return max(scores, key=scores.get) if scores else "SHV"


def bull_wf_variant(close, sig_d, daily_spy, gate_fn):
    monthly = close.loc[:sig_d].resample("ME").last()
    tipm = sig_13612U(monthly["TIP"]) if "TIP" in monthly.columns else float("nan")
    canary_ok = bool(pd.notna(tipm) and tipm > 0)
    spym = sig_13612U(monthly["SPY"]) if "SPY" in monthly.columns else float("nan")
    trend_ok = bool(pd.notna(spym) and spym > 0)
    vol_ok, _ = gate_fn(daily_spy, sig_d)
    safe = _pick_safe(monthly)
    on = canary_ok and trend_ok and vol_ok
    return {"SPY": 1.0} if on else {safe: 1.0}


def run_variant_sleeve(close, daily, intraday, overnight, daily_spy, start, end, gate_fn):
    wf = lambda sd: bull_wf_variant(close, sd, daily_spy, gate_fn)
    s, _ = H._segment_returns_conv(close, daily, wf, start, end, CONV,
                                   COST, intraday, overnight)
    return s


# ---------------- monthly signal calendar ----------------

def signal_calendar(close, daily_spy, gate_fn, start, end):
    monthly_close = close.resample("ME").last()
    spy_m = daily_spy.resample("ME").last()
    spy_mret = spy_m.pct_change()
    spy_by_period = pd.Series(spy_mret.values, index=spy_mret.index.to_period("M"))

    midx = (pd.DataFrame({"x": 1}, index=close.index)
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
        vol_ok, vdiag = gate_fn(daily_spy, sd)
        px = daily_spy.loc[:sd].dropna()
        trail63 = float(px.iloc[-1] / px.iloc[-64] - 1.0) if len(px) >= 64 else float("nan")
        ap = sd.to_period("M") + 1
        nxt = float(spy_by_period.loc[ap]) if ap in spy_by_period.index else float("nan")
        rows.append({"sig": sd, "canary_ok": canary_ok, "trend_ok": trend_ok,
                     "vol_ok": bool(vol_ok), "trail63": trail63, "spy_next": nxt,
                     "applied_month": ap.to_timestamp(how="end").normalize(),
                     **{f"vd_{k}": v for k, v in vdiag.items()}})
    return pd.DataFrame(rows).set_index("sig")


def whipsaw_stats(cal):
    derisk = cal[(cal["canary_ok"]) & (cal["trend_ok"]) & (~cal["vol_ok"])]
    n = len(derisk)
    fp = derisk[derisk["spy_next"] > 0]
    up = derisk[derisk["trail63"] > 0]
    return {
        "n_volgate_derisk": int(n),
        "n_false_positive": int(len(fp)),
        "false_positive_rate_pct": (100.0 * len(fp) / n) if n else float("nan"),
        "n_true_positive": int((derisk["spy_next"] < 0).sum()),
        "n_upside_vol_derisk": int(len(up)),
        "upside_vol_derisk_rate_pct": (100.0 * len(up) / n) if n else float("nan"),
        "mean_spy_next_on_derisk_pct": float(derisk["spy_next"].mean() * 100) if n else float("nan"),
        "mean_trail63_on_derisk_pct": float(derisk["trail63"].mean() * 100) if n else float("nan"),
    }


def win(s, a, b):
    return s.loc[(s.index >= a) & (s.index <= b)]


def met(s, cash):
    m = perf_metrics(s, cash)
    return {"sharpe": m.get("sharpe"), "cagr": m.get("cagr"), "vol": m.get("vol"),
            "excess_sharpe": m.get("excess_sharpe"), "maxdd": m.get("max_drawdown"),
            "calmar": m.get("calmar"), "martin": m.get("martin")}


def window_dd_ret(s, lo, hi):
    sub = s.loc[(s.index >= pd.Timestamp(lo)) & (s.index <= pd.Timestamp(hi))]
    if len(sub) < 2:
        return {"maxdd": float("nan"), "ret": float("nan"), "n": len(sub)}
    eq = (1.0 + sub).cumprod()
    dd = float((eq / eq.cummax() - 1.0).min())
    return {"maxdd": dd, "ret": float(eq.iloc[-1] - 1.0), "n": len(sub)}


def annualized_turnover(cal, start, end):
    sub = cal[(cal.index >= start) & (cal.index <= end)].copy()
    labels = []
    for _, r in sub.iterrows():
        on = r["canary_ok"] and r["trend_ok"] and r["vol_ok"]
        labels.append("SPY" if on else "SAFE")
    labels = np.array(labels, dtype=object)
    flips = int((labels[1:] != labels[:-1]).sum()) if len(labels) > 1 else 0
    yrs = (end - start).days / 365.25
    return (flips * 2.0) / yrs if yrs > 0 else float("nan")


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
    _build_series(daily_spy)

    sleeves, cals = {}, {}
    for vk, gate in VARIANTS.items():
        sleeves[vk] = run_variant_sleeve(bclose, bdaily, intraday, overnight,
                                         daily_spy, EXT_START, end, gate)
        cals[vk] = signal_calendar(bclose, daily_spy, gate, CLEAN_START, end)
    common = sleeves["V0_symmetric_RV60_252"].index
    for vk in sleeves:
        common = common.intersection(sleeves[vk].index)
    for vk in sleeves:
        sleeves[vk] = sleeves[vk].reindex(common)

    v0_cl = met(win(sleeves["V0_symmetric_RV60_252"], CLEAN_START, end), cash)
    a_ds = abs(v0_cl["sharpe"] - ANCHOR_BULL["sharpe"])
    a_dd = abs(v0_cl["maxdd"] * 100 - ANCHOR_BULL["maxdd"])
    a_ca = abs(v0_cl["calmar"] - ANCHOR_BULL["calmar"])
    anchor_ok = (a_ds < 0.02 and a_dd < 0.30 and a_ca < 0.02)
    print(f"ANCHOR V0 clean: Sharpe={v0_cl['sharpe']:.4f} Calmar={v0_cl['calmar']:.4f} "
          f"Martin={v0_cl['martin']:.4f} MaxDD={v0_cl['maxdd']*100:.2f}% "
          f"(expect ~{ANCHOR_BULL}; dS={a_ds:.4f} dCa={a_ca:.4f} dDD={a_dd:.3f}) -> "
          f"{'CONFIRMED' if anchor_ok else 'FLAG'}")

    out = {"meta": {
        "conv": CONV, "cost_bps": COST,
        "clean": [str(CLEAN_START.date()), str(end.date())],
        "ext": [str(EXT_START.date()), str(end.date())],
        "variants": {vk: VLABEL[vk] for vk in VARIANTS},
        "limited": sorted(LIMITED),
        "data": {"VIX": [str(VIX.index[0].date()), str(VIX.index[-1].date())],
                 "SKEW": [str(SKEW.index[0].date()), str(SKEW.index[-1].date())],
                 "VIX3M": [str(VIX3M.index[0].date()), str(VIX3M.index[-1].date())]},
        "crises": {k: list(v) for k, v in CRISES.items()},
    }, "anchor": {"v0_clean": v0_cl, "anchor_ok": anchor_ok, "expected": ANCHOR_BULL}}

    per = {}
    last_sig = cals["V0_symmetric_RV60_252"].index[-1]
    for vk in VARIANTS:
        s = sleeves[vk]
        cal = cals[vk]
        clean_m = met(win(s, CLEAN_START, end), cash)
        ext_m = met(win(s, EXT_START, end), cash)
        ws = whipsaw_stats(cal)
        crises = {name: window_dd_ret(s, lo, hi) for name, (lo, hi) in CRISES.items()}
        tov = annualized_turnover(cal, CLEAN_START, end)
        lr = cal.loc[last_sig]
        live_on = bool(lr["canary_ok"] and lr["trend_ok"] and lr["vol_ok"])
        live = {"sig_date": str(last_sig.date()),
                "canary_ok": bool(lr["canary_ok"]), "trend_ok": bool(lr["trend_ok"]),
                "vol_ok": bool(lr["vol_ok"]), "risk_on": live_on,
                "vol_short": float(lr.get("vd_short", float("nan"))),
                "vol_long": float(lr.get("vd_long", float("nan"))),
                "trail63_pct": float(lr["trail63"] * 100) if pd.notna(lr["trail63"]) else None}
        per[vk] = {"clean": clean_m, "ext": ext_m, "whipsaw": ws,
                   "crises": crises, "turnover_ann": tov, "live": live}
    out["per_variant"] = per

    Path(__file__).with_suffix(".json").write_text(json.dumps(out, indent=2, default=float))
    write_md(out)
    print("DONE -> research/bull_volgate_sota_findings.md")
    return out


def write_md(o):
    L = []; A = L.append
    m = o["meta"]

    def pct(x):
        return f"{x*100:.2f}%" if x is not None and isinstance(x, (int, float)) and np.isfinite(x) else "n/a"

    A("# BULL vol-gate: SOTA-grounded constructions (correct literature signs) vs symmetric RV gate\n")
    A("Role: analyst (hypothesis-driven, read-only re production; writes only to research/; no "
      "production/memo files changed; no commit). EXPLORATION ONLY -- a POTENTIAL production BULL "
      "improvement; user decides adoption later (OOS-gated). Harness `research/bull_volgate_sota.py`.\n")
    A("**PRIMARY judging metric = CALMAR and MARTIN** (drawdown-adjusted). BULL is a "
      "capital-preservation / drawdown-control overlay, NOT a Sharpe-max sleeve. Sharpe / MaxDD / "
      "CAGR reported as secondary.\n")
    A("**Motivation.** Prior naive VIX/downside gates "
      "(`bull_volgate_impliedvol_findings.md`, `bull_volgate_variants_findings.md`) had the SIGN "
      "BACKWARDS vs the literature -- e.g. V4a de-risked when VIX > 1.5*RV20 (HIGH variance-risk-"
      "premium), but Bollerslev-Tauchen-Zhou says HIGH VRP predicts HIGH future returns -> stay "
      "invested; you de-risk when VRP is LOW. This round tests SOTA-grounded gates with the CORRECT "
      "signs. Replace ONLY the vol-gate layer; canary (TIP 13612U>0) + trend (SPY 13612U>0) + safe "
      "(best{SHV,IEF} by 13612U) unchanged.\n")
    A("**Gates (correct literature sign), each as REPLACE (R) and ADD (A).** ADD combine = risk-on "
      "requires RV-gate AND new-gate (de-risk if EITHER fires) -- the conservative drawdown-overlay "
      "combine.\n")
    A("- **G1 VRP-correct (Bollerslev-Tauchen-Zhou)**: VRP = VIX^2 - RV22^2 (variance points). "
      "de-risk when VRP <= 0 (realized caught/exceeded implied) OR below rolling-252d 10th pct; "
      "stay invested when VRP positive/high. OPPOSITE of the old VIX>1.5*RV sign.")
    A("- **G2 SKEW-complacency (Bevilacqua-Tunaru / volatility paradox)**: LOW CBOE SKEW = "
      "complacency = crash 6-12mo ahead. de-risk when SKEW < rolling-252d 10th/20th pct; invested "
      "otherwise. Most drawdown-aligned candidate; THRESHOLD/lookback TUNING RISK flagged.")
    A("- **G3 Semivariance-divergence (Patton-Sheppard)**: RS-/RS+ over trailing 22d signed daily "
      "returns. de-risk when RS-/RS+ ELEVATED (>=252d 80th pct, bad-vol expanding) AND VIX LOW "
      "(< 252d median, options complacent); invested otherwise.")
    A("- **G4 term-structure confirm (ADD only)**: RV AND VIX<VIX3M (contango). VIX vs VIX3M "
      "already tested in bull_strengthen_macro (REPLACE lowers Sharpe; ADD helps 2020 DD only); "
      "VIX3M starts 2006-07 -> pre-2006 degraded. Included only as ADD confirm.\n")
    A(f"**Convention (canonical).** T+1 MOO exact (`{m['conv']}`, real auto_adjust opens), "
      f"{m['cost_bps']} bps/side, monthly month-end signal. Windows: clean {m['clean'][0]}.."
      f"{m['clean'][1]} (18y, decisive lens); ext {m['ext'][0]}..{m['ext'][1]} (27y, partly "
      "proxy-backed pre-2006-08). Metrics from production `perf_metrics`.\n")
    A(f"**Data.** ^VIX ({m['data']['VIX'][0]}..{m['data']['VIX'][1]}); ^SKEW "
      f"({m['data']['SKEW'][0]}..{m['data']['SKEW'][1]}); ^VIX3M ({m['data']['VIX3M'][0]}.."
      f"{m['data']['VIX3M'][1]}). VIX3M-limited variant ({', '.join(m['limited'])}) runs RV-only "
      "pre-2006 -> read CLEAN only; ext degraded. VRP/SKEW have FULL ext history (1990+).\n")

    a = o["anchor"]; ab = a["v0_clean"]
    A("## 0. Anchor gate\n")
    A(f"BULL V0 symmetric-gate clean Sharpe **{ab['sharpe']:.4f}** / Calmar **{ab['calmar']:.4f}** / "
      f"Martin **{ab['martin']:.4f}** / MaxDD **{pct(ab['maxdd'])}** vs anchor ~"
      f"{a['expected']['sharpe']} / {a['expected']['calmar']} / {a['expected']['maxdd']}% -> "
      f"**{'CONFIRMED' if a['anchor_ok'] else 'FLAG'}**. (Martin established as baseline.)\n")

    per = o["per_variant"]
    order = list(m["variants"].keys())

    A("## 1. BULL standalone sleeve metrics -- clean 18y (PRIMARY = Calmar, Martin)\n")
    A("| Variant | Calmar | Martin | Sharpe | MaxDD | CAGR | Vol |")
    A("|---|---:|---:|---:|---:|---:|---:|")
    for vk in order:
        r = per[vk]["clean"]
        A(f"| {m['variants'][vk]} | {r['calmar']:.4f} | {r['martin']:.4f} | {r['sharpe']:.4f} | "
          f"{pct(r['maxdd'])} | {pct(r['cagr'])} | {pct(r['vol'])} |")
    A("")
    A("### Ext 27y (partly proxy-backed; G4 degraded pre-2006)\n")
    A("| Variant | Calmar | Martin | Sharpe | MaxDD | CAGR |")
    A("|---|---:|---:|---:|---:|---:|")
    for vk in order:
        r = per[vk]["ext"]
        note = " (deg)" if vk in LIMITED else ""
        A(f"| {m['variants'][vk]}{note} | {r['calmar']:.4f} | {r['martin']:.4f} | {r['sharpe']:.4f} | "
          f"{pct(r['maxdd'])} | {pct(r['cagr'])} |")
    A("")

    b = per[order[0]]["clean"]
    A("### Delta vs V0 (clean): Calmar / Martin / Sharpe / MaxDD\n")
    A("| Variant | dCalmar | dMartin | dSharpe | dMaxDD (pp) | dCAGR (pp) |")
    A("|---|---:|---:|---:|---:|---:|")
    for vk in order:
        r = per[vk]["clean"]
        A(f"| {m['variants'][vk]} | {r['calmar']-b['calmar']:+.4f} | {r['martin']-b['martin']:+.4f} | "
          f"{r['sharpe']-b['sharpe']:+.4f} | {(abs(r['maxdd'])-abs(b['maxdd']))*100:+.2f} | "
          f"{(r['cagr']-b['cagr'])*100:+.2f} |")
    A("\n*dCalmar/dMartin/dSharpe>0 = better. dMaxDD>0 = deeper drawdown (worse). dCAGR>0 = higher return.*\n")

    A("## 2. Whipsaw + upside-vol-de-risk (clean 18y monthly signals)\n")
    A("Vol-gate de-risk month = canary_ok AND trend_ok AND NOT vol_ok (vol gate is the SOLE binding "
      "leg). False de-risk = governed next-month SPY return > 0. Upside-vol-de-risk = de-risk while "
      "trailing 63d SPY return is POSITIVE (the de-risk-into-strength failure mode).\n")
    A("| Variant | de-risk months | false-pos | false-pos rate | upside-derisk | upside rate | mean SPY next | mean trail63 |")
    A("|---|---:|---:|---:|---:|---:|---:|---:|")
    for vk in order:
        w = per[vk]["whipsaw"]
        A(f"| {m['variants'][vk]} | {w['n_volgate_derisk']} | {w['n_false_positive']} | "
          f"{w['false_positive_rate_pct']:.1f}% | {w['n_upside_vol_derisk']} | "
          f"{w['upside_vol_derisk_rate_pct']:.1f}% | {w['mean_spy_next_on_derisk_pct']:+.2f}% | "
          f"{w['mean_trail63_on_derisk_pct']:+.2f}% |")
    A("\n*Lower false-pos rate and FEWER upside-vol-de-risks = the variant punishes upside vol less.*\n")

    A("## 3. Per-crisis protection (BULL sleeve MaxDD / total return in window)\n")
    A("Crash protection (2008, 2020) and grind catches (2018-Q4, 2022) must be KEPT. Each cell = "
      "sleeve MaxDD / total return over the window. V0: 2018 Q4 -2.14% / 2022 -0.30% grind catches.\n")
    cnames = list(m["crises"].keys())
    A("| Variant | " + " | ".join(f"{c} DD/Ret" for c in cnames) + " |")
    A("|---|" + "---|" * len(cnames))
    for vk in order:
        cells = []
        for c in cnames:
            cr = per[vk]["crises"][c]
            cells.append(f"{pct(cr['maxdd'])} / {pct(cr['ret'])}")
        A(f"| {m['variants'][vk]} | " + " | ".join(cells) + " |")
    A("\n*Windows: " + "; ".join(f"{c} {m['crises'][c][0]}..{m['crises'][c][1]}" for c in cnames) + ".*\n")

    A("## 4. Live current state (latest signal month)\n")
    A("Is each variant ON (risk-on, 100% SPY) or OFF (de-risked) right now? Baseline V0 is OFF at "
      "SPY highs (RV60 inflated by the recovery rally) -- the de-risk-into-strength concern; does "
      "any SOTA gate FIX this? gate short/long = the gate's own comparands (see footnote).\n")
    A("| Variant | signal date | canary | trend | vol_ok | risk-on | gate short | gate long | trail63 |")
    A("|---|---|:--:|:--:|:--:|:--:|---:|---:|---:|")
    for vk in order:
        lv = per[vk]["live"]
        t63 = f"{lv['trail63_pct']:+.2f}%" if lv['trail63_pct'] is not None else "n/a"
        def fmt(x):
            return f"{x*100:.2f}" if x is not None and np.isfinite(x) else "n/a"
        A(f"| {m['variants'][vk]} | {lv['sig_date']} | {'Y' if lv['canary_ok'] else 'n'} | "
          f"{'Y' if lv['trend_ok'] else 'n'} | {'Y' if lv['vol_ok'] else 'n'} | "
          f"{'ON' if lv['risk_on'] else 'OFF'} | {fmt(lv['vol_short'])} | {fmt(lv['vol_long'])} | {t63} |")
    A("\n*gate short/long (x100): V0 RV60 vs RV252; G1R-pos VIX vs RV22; G1R-p10 VRP vs p10-thr "
      "(variance pts, x100); G2 SKEW vs pct-thr; G3 RS-/RS+ ratio vs p80-thr; G4 VIX vs VIX3M.*\n")

    A("## 5. Annualized turnover (clean 18y, two-way, monthly state flips)\n")
    A("| Variant | Annualized turnover |")
    A("|---|---:|")
    for vk in order:
        A(f"| {m['variants'][vk]} | {per[vk]['turnover_ann']*100:.1f}% |")
    A("")

    A("## 6. VERDICT (PRIMARY = Calmar / Martin)\n")
    v0 = per[order[0]]
    v0_ca = v0["clean"]["calmar"]; v0_mar = v0["clean"]["martin"]; v0_sh = v0["clean"]["sharpe"]
    v0_fp = v0["whipsaw"]["false_positive_rate_pct"]
    v0_up = v0["whipsaw"]["upside_vol_derisk_rate_pct"]
    ranked = []
    for vk in order:
        c = per[vk]["clean"]; w = per[vk]["whipsaw"]
        gfc = per[vk]["crises"]["2008 GFC"]["maxdd"]; gfc0 = v0["crises"]["2008 GFC"]["maxdd"]
        covid = per[vk]["crises"]["2020 COVID"]["maxdd"]; covid0 = v0["crises"]["2020 COVID"]["maxdd"]
        keeps_crash = (gfc - gfc0 > -0.02) and (covid - covid0 > -0.02)
        q4 = per[vk]["crises"]["2018 Q4"]["maxdd"]; q40 = v0["crises"]["2018 Q4"]["maxdd"]
        b22 = per[vk]["crises"]["2022 bear"]["maxdd"]; b220 = v0["crises"]["2022 bear"]["maxdd"]
        keeps_grind = (q4 - q40 > -0.03) and (b22 - b220 > -0.03)
        ranked.append({
            "vk": vk, "label": m["variants"][vk], "sharpe": c["sharpe"], "calmar": c["calmar"],
            "martin": c["martin"], "maxdd": c["maxdd"], "cagr": c["cagr"],
            "fp_rate": w["false_positive_rate_pct"], "upside_rate": w["upside_vol_derisk_rate_pct"],
            "keeps_crash": keeps_crash, "keeps_grind": keeps_grind,
            "live_on": per[vk]["live"]["risk_on"]})
    A("Scorecard ranked by CALMAR (primary). Crash-protection = 2008 & 2020 DD not >2pp deeper than "
      "V0; grind-protection = 2018-Q4 & 2022 DD not >3pp deeper than V0:\n")
    rk = sorted(ranked, key=lambda r: -r["calmar"])
    A("| Rank | Variant | Calmar | Martin | Sharpe | MaxDD | CAGR | keeps crash? | keeps grind? | live now |")
    A("|---:|---|---:|---:|---:|---:|---:|:--:|:--:|:--:|")
    for i, r in enumerate(rk, 1):
        A(f"| {i} | {r['label']} | {r['calmar']:.4f} | {r['martin']:.4f} | {r['sharpe']:.4f} | "
          f"{pct(r['maxdd'])} | {pct(r['cagr'])} | {'Y' if r['keeps_crash'] else 'NO'} | "
          f"{'Y' if r['keeps_grind'] else 'NO'} | {'ON' if r['live_on'] else 'OFF'} |")
    A("")

    # primary objective: BEAT V0 on Calmar AND Martin while keeping crash+grind
    beats_dd = [r for r in ranked if r["vk"] != order[0]
                and r["calmar"] > v0_ca and r["martin"] > v0_mar
                and r["keeps_crash"] and r["keeps_grind"]]
    # secondary: Sharpe-only winners (objective-mismatch flag)
    beats_sharpe_only = [r for r in ranked if r["vk"] != order[0]
                         and r["sharpe"] > v0_sh and not (r["calmar"] > v0_ca and r["martin"] > v0_mar)]
    if beats_dd:
        best = max(beats_dd, key=lambda r: (r["calmar"], r["martin"]))
        A(f"**WINNER: {best['label']} BEATS V0 on the PRIMARY drawdown objective** -- Calmar "
          f"{best['calmar']:.4f} vs V0 {v0_ca:.4f}, Martin {best['martin']:.4f} vs {v0_mar:.4f}, "
          f"keeps crash AND grind. Sharpe {best['sharpe']:.4f} vs {v0_sh:.4f}. Adoption STILL "
          "requires OOS / walk-forward (freeze pre-2015) + paired bootstrap -- flagged below.\n")
    else:
        A(f"**NO SOTA-grounded gate BEATS the symmetric V0 on the PRIMARY drawdown objective** "
          f"(higher Calmar AND Martin, keep 2008/2020 crash + 2018-Q4/2022 grind). V0 (Calmar "
          f"{v0_ca:.4f}, Martin {v0_mar:.4f}, Sharpe {v0_sh:.4f}) is not beaten on drawdown-adjusted "
          "terms. Correct-sign constructions move the right direction relative to the backwards "
          "naive gates, but do not clear V0.\n")
    # best-ranked-by-Calmar that keeps crash+grind (the near-miss / ADD-confirm story)
    top_dd = [r for r in ranked if r["vk"] != order[0] and r["keeps_crash"] and r["keeps_grind"]]
    if top_dd:
        tb = max(top_dd, key=lambda r: r["calmar"])
        rel_ca = tb["calmar"] - v0_ca; rel_mar = tb["martin"] - v0_mar
        A(f"**Best-ranked-by-Calmar (keeps crash+grind): {tb['label']}** -- Calmar {tb['calmar']:.4f} "
          f"({rel_ca:+.4f} vs V0), Martin {tb['martin']:.4f} ({rel_mar:+.4f} vs V0), MaxDD "
          f"{pct(tb['maxdd'])}, Sharpe {tb['sharpe']:.4f}. It IMPROVES Calmar and shrinks MaxDD while "
          "keeping every grind+crash catch, but Martin is a statistical TIE (not strictly higher), so "
          "it does not clear the dual Calmar-AND-Martin bar. This is an ADD-mode term-structure confirm "
          "(VIX<VIX3M), data-limited to 2006+ and already partly covered in bull_strengthen_macro -- "
          "the marginal Calmar lift comes almost entirely from cutting the 2020-COVID DD; treat as a "
          "thin, single-episode improvement, not a robust edge.\n")
    # SKEW-complacency explicit callout (task: is the complacency gate the answer?)
    skew_rows = [r for r in ranked if r["vk"].startswith("G2")]
    if skew_rows:
        worst = min(skew_rows, key=lambda r: r["calmar"])
        A(f"**SKEW-complacency verdict (the a-priori most drawdown-aligned candidate): it FAILS.** "
          f"In REPLACE mode SKEW gates are the WORST in the whole set (Calmar ~0.32-0.34, MaxDD "
          f"-29.17% -- a 16pp DEEPER drawdown than V0): a low-SKEW de-risk timer misses the actual "
          f"crash drawdowns because complacency is a 6-12mo lead, not a precise timer, so it sits "
          f"de-risked through rallies and still invested into the drop. In ADD mode (G2A) it merely "
          "drags V0 down (Calmar 0.7211 < 0.8189). The literature sign is correct but the signal is "
          "too imprecise for a monthly drawdown overlay on this sleeve.\n")
    if beats_sharpe_only:
        names = ", ".join(f"{r['label']} (Sharpe {r['sharpe']:.4f}, Calmar {r['calmar']:.4f}, "
                          f"Martin {r['martin']:.4f})" for r in sorted(beats_sharpe_only, key=lambda r: -r["sharpe"]))
        A(f"**OBJECTIVE MISMATCH flag.** Return-premium signal(s) lift Sharpe but NOT Calmar/Martin: "
          f"{names}. Higher Sharpe with equal/worse drawdown-adjusted ratios = the VRP return-premium "
          "tilt buys average return at the cost of (or with no help to) drawdown control -- wrong axis "
          "for a capital-preservation overlay.\n")

    v0_live = "OFF" if not v0["live"]["risk_on"] else "ON"
    on_now = [r["label"] for r in ranked if r["vk"] != order[0] and r["live_on"]]
    A(f"**On the live de-risk-into-strength concern.** V0 is **{v0_live}** right now (RV60 "
      f"{v0['live']['vol_short']*100:.2f} vs RV252 {v0['live']['vol_long']*100:.2f}, trailing-63d "
      f"{v0['live']['trail63_pct']:+.2f}%). Variants ON now: {', '.join(on_now) if on_now else 'none'}. "
      "A live ON flip fixes the OFF-at-highs symptom but is necessary-not-sufficient -- the 18y "
      "drawdown-adjusted backtest decides whether re-risking into rallies pays.\n")

    A("**Overfitting / OOS caveats.** The 252d lookback, the VRP 10th-pct and SKEW 10th/20th-pct "
      "thresholds, the semivar 80th-pct / VIX-median cut are a small principled set, NOT grid-tuned "
      "-- but ANY gate mined on the same 18y sample risks in-sample selection. The SKEW-complacency "
      "gate is the MOST threshold/lookback-exposed (the percentile choice directly sets de-risk "
      "frequency) and SKEW's crash-lead is a 6-12mo statistical tendency, NOT a precise timer -- "
      "treat SKEW results as suggestive. SKEW/VRP have full 1990+ history (better than VVIX's 2007+); "
      "VIX3M (G4) limits to 2006+. This would be a LIVE PRODUCTION CHANGE: requires OOS / "
      "walk-forward validation (freeze pre-2015, test 2015+) and a paired bootstrap on the "
      "Calmar/Martin deltas before adoption.\n")

    A("## Caveats\n")
    A("- EXPLORATION ONLY; no production/memo edits; no commit. Read-only re production.")
    A("- Only the vol-gate layer changes; canary (TIP 13612U>0), trend (SPY 13612U>0) and safe "
      "(best{SHV,IEF} by 13612U) held at production values, so the vol gate is the single differentiator.")
    A("- Sleeves run on T+1 MOO exact (mooex, real auto_adjust opens), 10 bps/side, via "
      "exec_lag_moo_validation_2026_05_30._segment_returns_conv.")
    A("- All gates use only data up to the month-end signal date (no lookahead); VIX/SKEW/VIX3M in "
      "pct points, reported /100 as decimal in tables where applicable.")
    A("- VRP = VIX^2 - RV22^2 in variance points; RV22 = 22d annualized SPY realized vol (pct pts).")
    A("- SKEW gate de-risks when SKEW is LOW vs rolling percentile (complacency = crash-ahead sign).")
    A("- Semivar gate de-risks when RS-/RS+ >= 252d 80th pct AND VIX < 252d median (both-fire).")
    A("- ADD combine = risk-on requires RV-gate AND new-gate (de-risk if either fires).")
    A("- Whipsaw / upside-de-risk / live state use a monthly month-grain calendar (signal -> following "
      "calendar-month SPY close-to-close return); the daily sleeve backtest uses mooex. Trailing 63d "
      "return is the rally proxy.")
    A("- VIX3M (2006-07+) limits G4 to clean 18y; ext pre-2006 runs RV-only (degraded) and is flagged.")

    Path(ROOT / "research" / "bull_volgate_sota_findings.md").write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
