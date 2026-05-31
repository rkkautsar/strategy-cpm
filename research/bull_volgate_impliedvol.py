# -*- coding: utf-8 -*-
"""Throwaway research (analyst role; read-only re production; writes only to
research/; NO production/memo files changed; NO commit). EXPLORATION ONLY --
a POTENTIAL production BULL vol-gate improvement; user decides adoption later.

MOTIVATION
----------
Prior round (research/bull_volgate_variants_findings.md) showed downside/EWMA
REALIZED-vol gates all UNDERPERFORM the symmetric RV60<RV252 -- because the
symmetric gate's UPSIDE-sensitivity is load-bearing: it front-runs the lagging
trend filter in the 2018-Q4 and 2022 grinds. New idea: IMPLIED vol (VIX) is
naturally ASYMMETRIC -- spikes on fear, stays low in melt-ups -- so a VIX gate
might avoid the "de-risk into strength" whipsaw (the live OFF-at-SPY-highs)
WITHOUT losing protection. Also test VVIX (vol-of-vol) and implied-vs-realized
hybrids. Replace ONLY the vol-gate layer; canary (TIP 13612U>0) + trend
(SPY 13612U>0) + safe (best{SHV,IEF} by 13612U) held at production values.

NOTE: VIX term-structure (VIX vs VIX3M) was tested in bull_strengthen_macro
(REPLACE rv lowers Sharpe; ADD-to-rv helps 2020 DD only, thin evidence) -- NOT
repeated here; cited.

VARIANTS (small principled set, NOT grid-tuned)
  V0  BASELINE   : symmetric RV60 < RV252 (current production).
  V1a VIX 21/252 : risk-on when VIX 21d MA < VIX 252d MA (1m vs 12m implied).
  V1b VIX 63/252 : risk-on when VIX 63d MA < VIX 252d MA (3m vs 12m; RV60<RV252 analogue).
  V2a VIX < 20   : risk-on when VIX < 20 (classic fixed level; THRESHOLD-TUNED, flagged).
  V2b VIX<med252 : risk-on when VIX < its trailing 252d median (adaptive threshold).
  V3  VVIX<MA252 : risk-on when VVIX < its 252d MA (high vol-of-vol = tail risk -> de-risk; 2007+).
  V4a VRP-panic  : risk-OFF when VIX > 1.5 * RV20 (annualized) -- variance-risk-premium/panic sign.
  V4b CONFIRM    : risk-on when RV60<RV252 AND VIX<VIX252MA (implied confirms realized; AND-gate).

CONVENTION (canonical): T+1 MOO exact ("mooex", real auto_adjust opens),
10 bps/side, monthly month-end signal. Reuses production sleeve machinery via
exec_lag_moo_validation_2026_05_30 (H) and the parametric bull weight fn pattern
from bull_volgate_variants. ANCHOR: BULL symmetric-gate clean Sharpe ~1.1005 /
MaxDD -13.35%.

DATA: ^VIX (yfinance, 1990+), ^VVIX (yfinance/CBOE, 2007-01+), cached under
research/_macro_cache/. VVIX limits VVIX-variants to clean 18y (2008+); ext
pre-2007 VVIX runs risk-on (degraded) -- flagged.

Writes research/bull_volgate_impliedvol_findings.md (+ .json).
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

ANCHOR_BULL = {"sharpe": 1.1005, "maxdd": -13.35}
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


VIX = _cache_close("VIX.csv")    # 1990+
VVIX = _cache_close("VVIX.csv")  # 2007-01+


# ---------------- vol-gate variants ----------------
# Each gate: f(daily_spy_close_series, sig_d) -> (vol_ok: bool, diag: dict)
# diag uses keys "short"/"long" (decimal vol where applicable) so the live table
# can render generically.

def gate_symmetric(daily_spy, sig_d, fast=60, slow=252):
    sub = daily_spy.loc[:sig_d].pct_change().dropna()
    if len(sub) < slow:
        return True, {"warmup": True}
    vf = float(sub.tail(fast).std() * np.sqrt(252))
    vs = float(sub.tail(slow).std() * np.sqrt(252))
    return (vf < vs), {"short": vf, "long": vs}


def _rv(daily_spy, sig_d, window):
    sub = daily_spy.loc[:sig_d].pct_change().dropna()
    if len(sub) < window:
        return float("nan")
    return float(sub.tail(window).std() * np.sqrt(252))


def gate_vix_ma(fast, slow):
    """risk-on when VIX fast-MA < VIX slow-MA. VIX in pct points; report /100 as decimal."""
    def g(daily_spy, sig_d):
        v = VIX.loc[:sig_d]
        if len(v) < slow:
            return True, {"warmup": True}
        vf = float(v.tail(fast).mean())
        vs = float(v.tail(slow).mean())
        return (vf < vs), {"short": vf / 100.0, "long": vs / 100.0}
    return g


def gate_vix_thresh(level):
    """risk-on when latest VIX < fixed level."""
    def g(daily_spy, sig_d):
        v = VIX.loc[:sig_d]
        if len(v) == 0:
            return True, {"warmup": True}
        vv = float(v.iloc[-1])
        return (vv < level), {"short": vv / 100.0, "long": level / 100.0}
    return g


def gate_vix_median(window=252):
    """risk-on when latest VIX < its trailing-window median (adaptive threshold)."""
    def g(daily_spy, sig_d):
        v = VIX.loc[:sig_d]
        if len(v) < window:
            return True, {"warmup": True}
        vv = float(v.iloc[-1])
        med = float(v.tail(window).median())
        return (vv < med), {"short": vv / 100.0, "long": med / 100.0}
    return g


def gate_vvix_ma(slow=252):
    """risk-on when latest VVIX < its slow-MA (high vol-of-vol = de-risk)."""
    def g(daily_spy, sig_d):
        v = VVIX.loc[:sig_d]
        if len(v) < slow:
            return True, {"warmup": True}   # pre-2008 (ext): degraded -> risk-on
        vv = float(v.iloc[-1])
        ma = float(v.tail(slow).mean())
        return (vv < ma), {"short": vv / 100.0, "long": ma / 100.0}
    return g


def gate_vrp_panic(ratio=1.5, rv_win=20):
    """risk-OFF when VIX > ratio * RV(rv_win) annualized (panic / blown-out
    variance-risk-premium). risk-on otherwise."""
    def g(daily_spy, sig_d):
        v = VIX.loc[:sig_d]
        rv = _rv(daily_spy, sig_d, rv_win)
        if len(v) == 0 or not np.isfinite(rv):
            return True, {"warmup": True}
        vix = float(v.iloc[-1]) / 100.0
        thr = ratio * rv
        ok = vix <= thr
        return ok, {"short": vix, "long": thr}
    return g


def gate_confirm(fast=60, slow=252, vix_slow=252):
    """AND-gate: risk-on when RV60<RV252 AND VIX < VIX slow-MA (implied confirms realized)."""
    def g(daily_spy, sig_d):
        rv_ok, rvd = gate_symmetric(daily_spy, sig_d, fast, slow)
        v = VIX.loc[:sig_d]
        if len(v) < vix_slow:
            return rv_ok, {**rvd, "vix": float("nan")}
        vv = float(v.iloc[-1])
        ma = float(v.tail(vix_slow).mean())
        vix_ok = vv < ma
        return (rv_ok and vix_ok), {"short": vv / 100.0, "long": ma / 100.0,
                                    "rv_ok": rv_ok, "vix_ok": vix_ok}
    return g


VARIANTS = {
    "V0_symmetric_RV60_252": lambda d, s: gate_symmetric(d, s, 60, 252),
    "V1a_vix_ma_21_252":     gate_vix_ma(21, 252),
    "V1b_vix_ma_63_252":     gate_vix_ma(63, 252),
    "V2a_vix_lt_20":         gate_vix_thresh(20.0),
    "V2b_vix_lt_med252":     gate_vix_median(252),
    "V3_vvix_ma_252":        gate_vvix_ma(252),
    "V4a_vrp_panic_1p5x":    gate_vrp_panic(1.5, 20),
    "V4b_confirm_rv_and_vix": gate_confirm(60, 252, 252),
}
VLABEL = {
    "V0_symmetric_RV60_252": "V0 symmetric RV60<RV252 (PROD)",
    "V1a_vix_ma_21_252":     "V1a VIX 21d<252d MA",
    "V1b_vix_ma_63_252":     "V1b VIX 63d<252d MA",
    "V2a_vix_lt_20":         "V2a VIX < 20 (fixed)",
    "V2b_vix_lt_med252":     "V2b VIX < 252d median",
    "V3_vvix_ma_252":        "V3 VVIX < 252d MA",
    "V4a_vrp_panic_1p5x":    "V4a VRP risk-off VIX>1.5*RV20",
    "V4b_confirm_rv_and_vix": "V4b CONFIRM RV60<252 AND VIX<MA252",
}
# variants whose history is VVIX-limited (clean only is decisive)
VVIX_LIMITED = {"V3_vvix_ma_252"}


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
    n_fp = len(fp)
    up = derisk[derisk["trail63"] > 0]
    n_up = len(up)
    return {
        "n_volgate_derisk": int(n),
        "n_false_positive": int(n_fp),
        "false_positive_rate_pct": (100.0 * n_fp / n) if n else float("nan"),
        "n_true_positive": int((derisk["spy_next"] < 0).sum()),
        "n_upside_vol_derisk": int(n_up),
        "upside_vol_derisk_rate_pct": (100.0 * n_up / n) if n else float("nan"),
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
    anchor_ok = (a_ds < 0.02 and a_dd < 0.30)
    print(f"ANCHOR V0 clean: Sharpe={v0_cl['sharpe']:.4f} MaxDD={v0_cl['maxdd']*100:.2f}% "
          f"(expect ~{ANCHOR_BULL}; dS={a_ds:.4f} dDD={a_dd:.3f}) -> "
          f"{'CONFIRMED' if anchor_ok else 'FLAG'}")

    out = {"meta": {
        "conv": CONV, "cost_bps": COST,
        "clean": [str(CLEAN_START.date()), str(end.date())],
        "ext": [str(EXT_START.date()), str(end.date())],
        "variants": {vk: VLABEL[vk] for vk in VARIANTS},
        "vvix_limited": sorted(VVIX_LIMITED),
        "data": {"VIX": [str(VIX.index[0].date()), str(VIX.index[-1].date())],
                 "VVIX": [str(VVIX.index[0].date()), str(VVIX.index[-1].date())]},
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
    print("DONE -> research/bull_volgate_impliedvol_findings.md")
    return out


def write_md(o):
    L = []; A = L.append
    m = o["meta"]

    def pct(x):
        return f"{x*100:.2f}%" if x is not None and isinstance(x, (int, float)) and np.isfinite(x) else "n/a"

    A("# BULL vol-gate variants: IMPLIED vol (VIX) / VVIX / implied-vs-realized hybrids vs symmetric RV gate\n")
    A("Role: analyst (hypothesis-driven, read-only re production; writes only to research/; no "
      "production/memo files changed; no commit). EXPLORATION ONLY -- a POTENTIAL production BULL "
      "improvement; user decides adoption later (OOS-gated). Harness "
      "`research/bull_volgate_impliedvol.py`.\n")
    A("**Motivation.** Prior round (`research/bull_volgate_variants_findings.md`) showed downside/EWMA "
      "REALIZED-vol gates all UNDERPERFORM the symmetric RV60<RV252, because the symmetric gate's "
      "UPSIDE-sensitivity is load-bearing -- it front-runs the lagging trend filter in the 2018-Q4 "
      "and 2022 grinds. New idea: IMPLIED vol (VIX) is naturally ASYMMETRIC -- it spikes on fear, "
      "stays low in melt-ups -- so a VIX gate might avoid the 'de-risk into strength' whipsaw (the "
      "live OFF-at-SPY-highs) WITHOUT losing protection. Also test VVIX (vol-of-vol) and "
      "implied-vs-realized hybrids. Replace ONLY the vol-gate layer; canary (TIP 13612U>0) + trend "
      "(SPY 13612U>0) unchanged; safe = best{SHV,IEF} by 13612U.\n")
    A("**Already covered elsewhere (NOT repeated):** VIX term-structure VIX vs VIX3M -- "
      "`bull_strengthen_macro_findings.md` found REPLACE-rv lowers Sharpe; ADD-to-rv only improves "
      "2020 DD (thin: VIX3M starts 2006-07).\n")
    A("**Variants (small principled set, NOT grid-tuned).**")
    A("- **V0 symmetric** (PROD): RV60 < RV252, RV = annualized std of SPY daily returns.")
    A("- **V1a VIX 21/252**: risk-on when VIX 21d MA < VIX 252d MA (1m vs 12m implied).")
    A("- **V1b VIX 63/252**: risk-on when VIX 63d MA < VIX 252d MA (3m vs 12m; RV60<RV252 analogue).")
    A("- **V2a VIX < 20**: risk-on when latest VIX < 20 (classic fixed level; THRESHOLD-TUNED -- flagged).")
    A("- **V2b VIX < 252d median**: risk-on when latest VIX < its trailing 252d median (adaptive threshold).")
    A("- **V3 VVIX < 252d MA**: risk-on when latest VVIX < its 252d MA (high vol-of-vol = tail risk -> de-risk; VVIX 2007+).")
    A("- **V4a VRP-panic**: risk-OFF when VIX > 1.5 * RV20 (annualized) -- blown-out variance-risk-premium / panic sign.")
    A("- **V4b CONFIRM (AND)**: risk-on when RV60<RV252 AND VIX < VIX 252d MA (implied confirms realized).\n")
    A(f"**Convention (canonical).** T+1 MOO exact (`{m['conv']}`, real auto_adjust opens), "
      f"{m['cost_bps']} bps/side, monthly month-end signal. Windows: clean {m['clean'][0]}.."
      f"{m['clean'][1]} (18y, decisive lens); ext {m['ext'][0]}..{m['ext'][1]} (27y, partly "
      "proxy-backed pre-2006-08). Metrics from production `perf_metrics`.\n")
    A(f"**Data.** ^VIX (yfinance, {m['data']['VIX'][0]}..{m['data']['VIX'][1]}); "
      f"^VVIX (yfinance/CBOE, {m['data']['VVIX'][0]}..{m['data']['VVIX'][1]}). VVIX-limited "
      f"variants ({', '.join(m['vvix_limited'])}) run risk-on pre-2007 -> read CLEAN only; ext is degraded.\n")

    a = o["anchor"]; ab = a["v0_clean"]
    A("## 0. Anchor gate\n")
    A(f"BULL V0 symmetric-gate clean Sharpe **{ab['sharpe']:.4f}** / MaxDD **{pct(ab['maxdd'])}** "
      f"vs anchor ~{a['expected']['sharpe']} / {a['expected']['maxdd']}% -> "
      f"**{'CONFIRMED' if a['anchor_ok'] else 'FLAG'}**.\n")

    per = o["per_variant"]
    order = list(m["variants"].keys())

    A("## 1. BULL standalone sleeve metrics -- clean 18y\n")
    A("| Variant | CAGR | Vol | Sharpe | Excess Sharpe | MaxDD | Calmar | Martin |")
    A("|---|---:|---:|---:|---:|---:|---:|---:|")
    for vk in order:
        r = per[vk]["clean"]
        A(f"| {m['variants'][vk]} | {pct(r['cagr'])} | {pct(r['vol'])} | {r['sharpe']:.4f} | "
          f"{r['excess_sharpe']:.4f} | {pct(r['maxdd'])} | {r['calmar']:.4f} | {r['martin']:.4f} |")
    A("")
    A("### Ext 27y (partly proxy-backed; VVIX variants degraded pre-2007)\n")
    A("| Variant | CAGR | Vol | Sharpe | MaxDD | Calmar |")
    A("|---|---:|---:|---:|---:|---:|")
    for vk in order:
        r = per[vk]["ext"]
        note = " (VVIX-deg)" if vk in VVIX_LIMITED else ""
        A(f"| {m['variants'][vk]}{note} | {pct(r['cagr'])} | {pct(r['vol'])} | {r['sharpe']:.4f} | "
          f"{pct(r['maxdd'])} | {r['calmar']:.4f} |")
    A("")

    b = per[order[0]]["clean"]
    A("### Delta vs V0 (clean): Sharpe / Calmar / MaxDD / CAGR\n")
    A("| Variant | dSharpe | dCalmar | dMaxDD (pp) | dCAGR (pp) |")
    A("|---|---:|---:|---:|---:|")
    for vk in order:
        r = per[vk]["clean"]
        A(f"| {m['variants'][vk]} | {r['sharpe']-b['sharpe']:+.4f} | {r['calmar']-b['calmar']:+.4f} | "
          f"{(abs(r['maxdd'])-abs(b['maxdd']))*100:+.2f} | {(r['cagr']-b['cagr'])*100:+.2f} |")
    A("\n*dMaxDD>0 = deeper drawdown (worse). dCAGR>0 = higher return.*\n")

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
      "sleeve MaxDD / total return over the window.\n")
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
    A("Is each variant ON (risk-on, 100% SPY) or OFF (de-risked to safe) right now? Baseline V0 is "
      "OFF at SPY highs (RV60 inflated by the recovery rally) -- the de-risk-into-strength concern. "
      "vol short/long are the gate's own comparands (VIX MA / threshold / VVIX, all shown /100).\n")
    A("| Variant | signal date | canary | trend | vol_ok | risk-on | gate short | gate long | trail63 |")
    A("|---|---|:--:|:--:|:--:|:--:|---:|---:|---:|")
    for vk in order:
        lv = per[vk]["live"]
        t63 = f"{lv['trail63_pct']:+.2f}%" if lv['trail63_pct'] is not None else "n/a"
        A(f"| {m['variants'][vk]} | {lv['sig_date']} | {'Y' if lv['canary_ok'] else 'n'} | "
          f"{'Y' if lv['trend_ok'] else 'n'} | {'Y' if lv['vol_ok'] else 'n'} | "
          f"{'ON' if lv['risk_on'] else 'OFF'} | {lv['vol_short']*100:.2f} | "
          f"{lv['vol_long']*100:.2f} | {t63} |")
    A("\n*gate short/long are in vol points (VIX-style): e.g. V0 = RV60 vs RV252; V1 = VIX MA fast vs slow; "
      "V2 = VIX vs threshold/median; V3 = VVIX vs MA; V4a = VIX vs 1.5*RV20; V4b = VIX vs VIX-MA (AND rv).*\n")

    A("## 5. Annualized turnover (clean 18y, two-way, monthly state flips)\n")
    A("| Variant | Annualized turnover |")
    A("|---|---:|")
    for vk in order:
        A(f"| {m['variants'][vk]} | {per[vk]['turnover_ann']*100:.1f}% |")
    A("")

    A("## 6. VERDICT\n")
    v0 = per[order[0]]
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
            "maxdd": c["maxdd"], "cagr": c["cagr"], "fp_rate": w["false_positive_rate_pct"],
            "upside_rate": w["upside_vol_derisk_rate_pct"], "n_upside": w["n_upside_vol_derisk"],
            "keeps_crash": keeps_crash, "keeps_grind": keeps_grind,
            "live_on": per[vk]["live"]["risk_on"]})
    A("Candidate scorecard (clean 18y). Crash-protection = 2008 & 2020 DD not >2pp deeper than V0; "
      "grind-protection = 2018-Q4 & 2022 DD not >3pp deeper than V0 (the slow-bear catches the task "
      "warns not to trade away):\n")
    A("| Variant | Sharpe | Calmar | MaxDD | CAGR | false-pos | upside-derisk | keeps crash? | keeps grind? | live now |")
    A("|---|---:|---:|---:|---:|---:|---:|:--:|:--:|:--:|")
    for r in ranked:
        A(f"| {r['label']} | {r['sharpe']:.4f} | {r['calmar']:.4f} | {pct(r['maxdd'])} | "
          f"{pct(r['cagr'])} | {r['fp_rate']:.1f}% | {r['upside_rate']:.1f}% | "
          f"{'Y' if r['keeps_crash'] else 'NO'} | {'Y' if r['keeps_grind'] else 'NO'} | "
          f"{'ON' if r['live_on'] else 'OFF'} |")
    A("")

    v0_upside = v0["whipsaw"]["upside_vol_derisk_rate_pct"]
    v0_fp = v0["whipsaw"]["false_positive_rate_pct"]
    v0_sh = v0["clean"]["sharpe"]; v0_ca = v0["clean"]["calmar"]
    # primary objective: BEAT V0 on Sharpe AND Calmar while keeping crash+grind AND not raising whipsaw
    beats = [r for r in ranked if r["vk"] != order[0]
             and r["sharpe"] > v0_sh and r["calmar"] > v0_ca
             and r["keeps_crash"] and r["keeps_grind"]
             and r["fp_rate"] <= v0_fp + 1e-9 and r["upside_rate"] <= v0_upside + 1e-9]
    # secondary: any that keep crash+grind and reduce upside-derisk (the live-fix objective)
    fixers = [r for r in ranked if r["vk"] != order[0] and r["keeps_crash"] and r["keeps_grind"]
              and r["upside_rate"] <= v0_upside + 1e-9]
    if beats:
        best = max(beats, key=lambda r: (r["sharpe"], r["calmar"]))
        A(f"**WINNER: {best['label']} BEATS V0** on the full objective -- clean Sharpe {best['sharpe']:.4f} "
          f"vs V0 {v0_sh:.4f}, Calmar {best['calmar']:.4f} vs {v0_ca:.4f}, keeps crash AND grind, "
          f"and does not raise whipsaw (false-pos {best['fp_rate']:.1f}% vs {v0_fp:.1f}%, "
          f"upside-de-risk {best['upside_rate']:.1f}% vs {v0_upside:.1f}%). "
          "Adoption STILL requires OOS / walk-forward validation -- flagged below.\n")
    else:
        A(f"**NO implied-vol / VVIX / hybrid variant BEATS the symmetric V0** on the full objective "
          f"(higher Sharpe AND Calmar, keep 2008/2020 crash + 2018-Q4/2022 grind catches, not raise "
          f"whipsaw). Same conclusion as the prior realized-vol round: V0 (Sharpe {v0_sh:.4f}, Calmar "
          f"{v0_ca:.4f}) is not beaten.\n")
        if fixers:
            ff = sorted(fixers, key=lambda r: -r["sharpe"])
            names = ", ".join(f"{r['label']} (Sharpe {r['sharpe']:.4f}, upside-de-risk {r['upside_rate']:.1f}%)"
                              for r in ff[:3])
            A(f"Variants that DO cut the upside-de-risk rate while keeping both crash and grind "
              f"protection (the 'fix the live OFF-at-highs' sub-goal): {names}. But each TRAILS V0 "
              f"on Sharpe/Calmar -- the asymmetry helps the live concern yet nets negative over 18y, "
              "exactly mirroring the realized-vol round.\n")
        else:
            A("No variant even cuts the upside-de-risk rate while keeping both crash and grind "
              "protection.\n")

    # live-fix summary
    v0_live = "OFF" if not v0["live"]["risk_on"] else "ON"
    on_now = [r["label"] for r in ranked if r["vk"] != order[0] and r["live_on"]]
    A(f"**On the live de-risk-into-strength concern.** V0 is **{v0_live}** right now "
      f"(RV60 {v0['live']['vol_short']*100:.2f} vs RV252 {v0['live']['vol_long']*100:.2f}, trailing-63d "
      f"{v0['live']['trail63_pct']:+.2f}%). Variants that would be ON now: "
      f"{', '.join(on_now) if on_now else 'none'}. A live ON flip is necessary but not sufficient -- "
      "the 18y backtest decides whether re-risking into rallies pays.\n")

    A("**Overfitting / OOS caveats.** MA windows (21/63/252), the VIX<20 level, the 1.5x VRP ratio "
      "and the AND-confirm are a small principled set, NOT grid-tuned -- but ANY gate swap mined on "
      "the same 18y sample risks in-sample selection. V2a (VIX<20) is the most threshold-exposed "
      "(a round number); V2b (rolling median) is adaptive but still a level call. VVIX history "
      "starts 2007 so V3 has ~2 real crashes (2008 partial, 2020) + 2022 in the clean window -- "
      "THIN tail evidence; treat VVIX results as suggestive only. This would be a LIVE PRODUCTION "
      "CHANGE: requires OOS / walk-forward validation (freeze pre-2015, test 2015+) and a paired "
      "bootstrap on the Sharpe/Calmar deltas before adoption.\n")

    A("## Caveats\n")
    A("- EXPLORATION ONLY; no production/memo edits; no commit. Read-only re production.")
    A("- Only the vol-gate layer changes; canary (TIP 13612U>0), trend (SPY 13612U>0) and safe "
      "(best{SHV,IEF} by 13612U) held at production values, so the vol gate is the single differentiator.")
    A("- Sleeves run on T+1 MOO exact (mooex, real auto_adjust opens), 10 bps/side, via "
      "exec_lag_moo_validation_2026_05_30._segment_returns_conv.")
    A("- VIX/VVIX gates use only data up to the month-end signal date (no lookahead); VIX in pct "
      "points, reported /100 as decimal for the live table.")
    A("- VIX term-structure (VIX vs VIX3M) NOT re-tested here -- see bull_strengthen_macro_findings.md.")
    A("- Whipsaw / upside-de-risk / live state use a monthly month-grain calendar (signal -> following "
      "calendar-month SPY close-to-close return); the daily sleeve backtest uses mooex. Trailing 63d "
      "return is the rally proxy.")
    A("- VVIX (2007+) limits V3 to the clean 18y window; ext pre-2007 runs risk-on (degraded) and is "
      "flagged. Clean 18y is the decisive lens.")

    Path(ROOT / "research" / "bull_volgate_impliedvol_findings.md").write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
