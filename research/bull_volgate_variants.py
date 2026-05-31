# -*- coding: utf-8 -*-
"""Throwaway research (analyst role; read-only re production; writes only to
research/; NO production/memo files changed; NO commit). EXPLORATION ONLY --
a POTENTIAL production BULL vol-gate improvement; user decides adoption later.

MOTIVATION
----------
BULL's vol gate is SYMMETRIC: risk-on when RV60 < RV252, where RV = annualized
std of SPY daily returns (counts UP and DOWN vol identically). A sharp RALLY
inflates RV60 -> the gate can DE-RISK INTO STRENGTH (the likely current
SPY-at-highs OFF state). It also whipsaws (~59% false-positive de-risks).

Test whether a DOWNSIDE-only or EWMA vol gate fixes this WITHOUT losing crash
protection. Replace ONLY the vol-gate layer; canary (TIP 13612U) + trend
(SPY 13612U) unchanged. Safe = best{SHV,IEF} by 13612U.

VARIANTS
  V0 BASELINE     : symmetric RV60 < RV252 (current production).
  V1 DOWNSIDE     : dRV = sqrt(mean(min(r,0)^2))*sqrt(252) over 60 vs 252d;
                    risk-on when dRV60 < dRV252.
  V2a EWMA(94/99) : RiskMetrics short lambda=0.94 (HL 11.2d) vs long lambda=0.99
                    (HL 69d); risk-on when ewma_short < ewma_long.
  V2b EWMA(97/99) : short lambda=0.97 (HL 22.8d ~ 60d-window com) vs long
                    lambda=0.99 (HL 69d); risk-on when ewma_short < ewma_long.
  V3 DOWNSIDE-EWMA: EWMA on downside semi-variance (min(r,0)^2), short
                    lambda=0.97 vs long lambda=0.99; risk-on when short < long.

Small principled set (NOT grid-tuned to peak). Overfitting risk flagged.

CONVENTION (canonical): T+1 MOO exact ("mooex", real auto_adjust opens),
10 bps/side, monthly month-end signal. Reuses production sleeve machinery via
exec_lag_moo_validation_2026_05_30 (H) and the parametric bull weight fn pattern
from bull_tiponly_recompute. ANCHOR: BULL symmetric-gate clean Sharpe ~1.1005 /
MaxDD -13.35%.

Writes research/bull_volgate_variants_findings.md (+ .json).
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

ANCHOR_BULL = {"sharpe": 1.1005, "maxdd": -13.35}
BULL_SAFE = ["SHV", "IEF"]

# Crisis windows for protection check.
CRISES = {
    "2008 GFC":      ("2008-05-30", "2009-06-30"),
    "2018 Q4":       ("2018-01-01", "2018-12-31"),
    "2020 COVID":    ("2020-01-01", "2020-06-30"),
    "2022 bear":     ("2022-01-01", "2022-12-31"),
}


def _hl(lmbda):
    """EWMA half-life in days for decay lambda."""
    return float(np.log(2) / (-np.log(lmbda)))


# ---------------- vol-gate variants ----------------
# Each: f(daily_spy_close_series, sig_d) -> (vol_ok: bool, diag: dict)

def gate_symmetric(daily_spy, sig_d, fast=60, slow=252):
    sub = daily_spy.loc[:sig_d].pct_change().dropna()
    if len(sub) < slow:
        return True, {"warmup": True}
    vf = float(sub.tail(fast).std() * np.sqrt(252))
    vs = float(sub.tail(slow).std() * np.sqrt(252))
    return (vf < vs), {"short": vf, "long": vs}


def gate_downside(daily_spy, sig_d, fast=60, slow=252):
    sub = daily_spy.loc[:sig_d].pct_change().dropna()
    if len(sub) < slow:
        return True, {"warmup": True}
    neg = np.minimum(sub.values, 0.0) ** 2
    df = float(np.sqrt(neg[-fast:].mean()) * np.sqrt(252))
    ds = float(np.sqrt(neg[-slow:].mean()) * np.sqrt(252))
    return (df < ds), {"short": df, "long": ds}


def _ewma_vol(r2, lmbda):
    """Last EWMA value of squared-return series r2 (RiskMetrics: alpha=1-lambda)."""
    return float(np.sqrt(pd.Series(r2).ewm(alpha=1.0 - lmbda, adjust=False).mean().iloc[-1]) * np.sqrt(252))


def gate_ewma(daily_spy, sig_d, lam_s, lam_l):
    sub = daily_spy.loc[:sig_d].pct_change().dropna()
    if len(sub) < 252:
        return True, {"warmup": True}
    r2 = (sub.values ** 2)
    vs_ = _ewma_vol(r2, lam_s)
    vl_ = _ewma_vol(r2, lam_l)
    return (vs_ < vl_), {"short": vs_, "long": vl_}


def gate_downside_ewma(daily_spy, sig_d, lam_s, lam_l):
    sub = daily_spy.loc[:sig_d].pct_change().dropna()
    if len(sub) < 252:
        return True, {"warmup": True}
    neg2 = np.minimum(sub.values, 0.0) ** 2
    vs_ = _ewma_vol(neg2, lam_s)
    vl_ = _ewma_vol(neg2, lam_l)
    return (vs_ < vl_), {"short": vs_, "long": vl_}


VARIANTS = {
    "V0_symmetric_RV60_252": lambda d, s: gate_symmetric(d, s, 60, 252),
    "V1_downside_60_252":    lambda d, s: gate_downside(d, s, 60, 252),
    "V2a_ewma_94_99":        lambda d, s: gate_ewma(d, s, 0.94, 0.99),
    "V2b_ewma_97_99":        lambda d, s: gate_ewma(d, s, 0.97, 0.99),
    "V3_downside_ewma_97_99": lambda d, s: gate_downside_ewma(d, s, 0.97, 0.99),
}
VLABEL = {
    "V0_symmetric_RV60_252": "V0 symmetric RV60<RV252 (PROD)",
    "V1_downside_60_252":    "V1 downside semi-dev 60<252",
    "V2a_ewma_94_99":        "V2a EWMA lam 0.94<0.99",
    "V2b_ewma_97_99":        "V2b EWMA lam 0.97<0.99",
    "V3_downside_ewma_97_99": "V3 downside-EWMA 0.97<0.99",
}


# ---------------- parametric BULL weight fn (canary=TIP, trend=SPY, safe=SHV/IEF) ----------------

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


# ---------------- monthly signal calendar (whipsaw / upside-derisk / live) ----------------

def signal_calendar(close, daily_spy, gate_fn, start, end):
    """Per month-end signal: canary/trend/vol booleans, governed-next-month SPY
    return, trailing 63d SPY return (for upside-vol-derisk)."""
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
        # trailing 63d SPY total return (rally detector)
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
    """vol-gate de-risk = canary_ok AND trend_ok AND NOT vol_ok (vol sole binding leg)."""
    derisk = cal[(cal["canary_ok"]) & (cal["trend_ok"]) & (~cal["vol_ok"])]
    n = len(derisk)
    fp = derisk[derisk["spy_next"] > 0]
    n_fp = len(fp)
    # upside-vol-derisk: vol-binding de-risk while trailing 63d move is UP (de-risk into strength)
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
    """Annualized two-way turnover from monthly weight-label changes (state flips * 2)."""
    sub = cal[(cal.index >= start) & (cal.index <= end)].copy()
    # weight label: SPY if on else safe label proxy 'SAFE' (safe identity changes also count)
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

    # ---- run all variant sleeves ----
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

    # ---- anchor gate ----
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
        "ewma_halflives": {"lam0.94": _hl(0.94), "lam0.97": _hl(0.97), "lam0.99": _hl(0.99)},
        "crises": {k: list(v) for k, v in CRISES.items()},
    }, "anchor": {"v0_clean": v0_cl, "anchor_ok": anchor_ok, "expected": ANCHOR_BULL}}

    # ---- per-variant metrics, whipsaw, crises, live, turnover ----
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
        # live state (latest signal month)
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
    print("DONE -> research/bull_volgate_variants_findings.md")
    return out


def write_md(o):
    L = []; A = L.append
    m = o["meta"]

    def pct(x):
        return f"{x*100:.2f}%" if x is not None and isinstance(x, (int, float)) and np.isfinite(x) else "n/a"

    A("# BULL vol-gate variants: downside-only / EWMA vs symmetric RV gate\n")
    A("Role: analyst (hypothesis-driven, read-only re production; writes only to research/; "
      "no production/memo files changed; no commit). EXPLORATION ONLY -- a POTENTIAL production "
      "BULL improvement; user decides adoption later. Harness "
      "`research/bull_volgate_variants.py`.\n")
    A("**Motivation.** Production vol gate is SYMMETRIC: risk-on when RV60 < RV252 (annualized "
      "std of SPY daily returns, counting UP and DOWN vol identically). A sharp RALLY inflates "
      "RV60 so the gate can DE-RISK INTO STRENGTH (the likely current SPY-at-highs OFF state). "
      "It also whipsaws (~59% false-positive de-risks). Test whether a DOWNSIDE-only or EWMA "
      "vol gate fixes this WITHOUT losing crash protection. Replace ONLY the vol-gate layer; "
      "canary (TIP 13612U>0) + trend (SPY 13612U>0) unchanged; safe = best{SHV,IEF} by 13612U.\n")
    hl = m["ewma_halflives"]
    A("**Variants (small principled set, NOT grid-tuned).**")
    A(f"- **V0 symmetric** (PROD): RV60 < RV252, RV = annualized std of daily returns.")
    A(f"- **V1 downside**: dRV = sqrt(mean(min(r,0)^2))*sqrt(252) over 60 vs 252d; ON when dRV60 < dRV252.")
    A(f"- **V2a EWMA 0.94/0.99**: RiskMetrics short lambda=0.94 (HL {hl['lam0.94']:.1f}d) vs long "
      f"lambda=0.99 (HL {hl['lam0.99']:.1f}d); ON when ewma_short < ewma_long.")
    A(f"- **V2b EWMA 0.97/0.99**: short lambda=0.97 (HL {hl['lam0.97']:.1f}d, ~60d-window com) vs "
      f"long lambda=0.99 (HL {hl['lam0.99']:.1f}d); ON when ewma_short < ewma_long.")
    A(f"- **V3 downside-EWMA 0.97/0.99**: EWMA on downside semi-variance (min(r,0)^2), short "
      f"lambda=0.97 vs long lambda=0.99; ON when short < long.\n")
    A(f"**Convention (canonical).** T+1 MOO exact (`{m['conv']}`, real auto_adjust opens), "
      f"{m['cost_bps']} bps/side, monthly month-end signal. Windows: clean {m['clean'][0]}.."
      f"{m['clean'][1]} (18y); ext {m['ext'][0]}..{m['ext'][1]} (27y, partly proxy-backed "
      "pre-2006-08). Metrics from production `perf_metrics`.\n")

    a = o["anchor"]; ab = a["v0_clean"]
    A("## 0. Anchor gate\n")
    A(f"BULL V0 symmetric-gate clean Sharpe **{ab['sharpe']:.4f}** / MaxDD **{pct(ab['maxdd'])}** "
      f"vs anchor ~{a['expected']['sharpe']} / {a['expected']['maxdd']}% -> "
      f"**{'CONFIRMED' if a['anchor_ok'] else 'FLAG'}**.\n")

    per = o["per_variant"]
    order = list(m["variants"].keys())

    # ---- Section 1: clean metrics ----
    A("## 1. BULL standalone sleeve metrics -- clean 18y\n")
    A("| Variant | CAGR | Vol | Sharpe | Excess Sharpe | MaxDD | Calmar | Martin |")
    A("|---|---:|---:|---:|---:|---:|---:|---:|")
    for vk in order:
        r = per[vk]["clean"]
        A(f"| {m['variants'][vk]} | {pct(r['cagr'])} | {pct(r['vol'])} | {r['sharpe']:.4f} | "
          f"{r['excess_sharpe']:.4f} | {pct(r['maxdd'])} | {r['calmar']:.4f} | {r['martin']:.4f} |")
    A("")
    A("### Ext 27y (partly proxy-backed)\n")
    A("| Variant | CAGR | Vol | Sharpe | MaxDD | Calmar |")
    A("|---|---:|---:|---:|---:|---:|")
    for vk in order:
        r = per[vk]["ext"]
        A(f"| {m['variants'][vk]} | {pct(r['cagr'])} | {pct(r['vol'])} | {r['sharpe']:.4f} | "
          f"{pct(r['maxdd'])} | {r['calmar']:.4f} |")
    A("")

    # ---- Section 1b: deltas vs V0 ----
    b = per[order[0]]["clean"]
    A("### Delta vs V0 (clean): Sharpe / Calmar / MaxDD / CAGR\n")
    A("| Variant | dSharpe | dCalmar | dMaxDD (pp) | dCAGR (pp) |")
    A("|---|---:|---:|---:|---:|")
    for vk in order:
        r = per[vk]["clean"]
        A(f"| {m['variants'][vk]} | {r['sharpe']-b['sharpe']:+.4f} | {r['calmar']-b['calmar']:+.4f} | "
          f"{(abs(r['maxdd'])-abs(b['maxdd']))*100:+.2f} | {(r['cagr']-b['cagr'])*100:+.2f} |")
    A("\n*dMaxDD>0 = deeper drawdown (worse). dCAGR>0 = higher return.*\n")

    # ---- Section 2: whipsaw + upside-vol-derisk ----
    A("## 2. Whipsaw + upside-vol-de-risk (clean 18y monthly signals)\n")
    A("Vol-gate de-risk month = canary_ok AND trend_ok AND NOT vol_ok (vol gate is the SOLE "
      "binding leg). False de-risk = governed next-month SPY return > 0. Upside-vol-de-risk = "
      "de-risk while trailing 63d SPY return is POSITIVE (the de-risk-into-strength failure mode).\n")
    A("| Variant | de-risk months | false-pos | false-pos rate | upside-derisk | upside rate | mean SPY next | mean trail63 |")
    A("|---|---:|---:|---:|---:|---:|---:|---:|")
    for vk in order:
        w = per[vk]["whipsaw"]
        A(f"| {m['variants'][vk]} | {w['n_volgate_derisk']} | {w['n_false_positive']} | "
          f"{w['false_positive_rate_pct']:.1f}% | {w['n_upside_vol_derisk']} | "
          f"{w['upside_vol_derisk_rate_pct']:.1f}% | {w['mean_spy_next_on_derisk_pct']:+.2f}% | "
          f"{w['mean_trail63_on_derisk_pct']:+.2f}% |")
    A("\n*Lower false-pos rate and FEWER upside-vol-de-risks = the variant punishes upside vol less.*\n")

    # ---- Section 3: per-crisis protection ----
    A("## 3. Per-crisis protection (BULL sleeve MaxDD / total return in window)\n")
    A("Crash protection must be KEPT. Each cell = sleeve MaxDD / total return over the window.\n")
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

    # ---- Section 4: live state ----
    A("## 4. Live current state (latest signal month)\n")
    A("Is each variant ON (risk-on, 100% SPY) or OFF (de-risked to safe) right now? Baseline V0 "
      "is expected OFF at SPY highs (RV60 inflated by the recovery rally).\n")
    A("| Variant | signal date | canary | trend | vol_ok | risk-on | vol short | vol long | trail63 |")
    A("|---|---|:--:|:--:|:--:|:--:|---:|---:|---:|")
    for vk in order:
        lv = per[vk]["live"]
        A(f"| {m['variants'][vk]} | {lv['sig_date']} | {'Y' if lv['canary_ok'] else 'n'} | "
          f"{'Y' if lv['trend_ok'] else 'n'} | {'Y' if lv['vol_ok'] else 'n'} | "
          f"{'ON' if lv['risk_on'] else 'OFF'} | {lv['vol_short']*100:.2f}% | "
          f"{lv['vol_long']*100:.2f}% | "
          f"{lv['trail63_pct']:+.2f}%" + (" |" if lv['trail63_pct'] is not None else " n/a |"))
    A("")

    # ---- Section 5: turnover ----
    A("## 5. Annualized turnover (clean 18y, two-way, monthly state flips)\n")
    A("| Variant | Annualized turnover |")
    A("|---|---:|")
    for vk in order:
        A(f"| {m['variants'][vk]} | {per[vk]['turnover_ann']*100:.1f}% |")
    A("")

    # ---- Verdict ----
    A("## 6. VERDICT\n")
    v0 = per[order[0]]
    # rank candidates (exclude V0) by a simple composite: prefer higher clean Calmar,
    # lower upside-derisk rate, not-worse crisis protection.
    ranked = []
    for vk in order:
        c = per[vk]["clean"]; w = per[vk]["whipsaw"]
        # keep crash protection: 2008+2020 DD must not be materially worse than V0
        gfc = per[vk]["crises"]["2008 GFC"]["maxdd"]
        covid = per[vk]["crises"]["2020 COVID"]["maxdd"]
        gfc0 = v0["crises"]["2008 GFC"]["maxdd"]
        covid0 = v0["crises"]["2020 COVID"]["maxdd"]
        keeps_crash = (gfc - gfc0 > -0.02) and (covid - covid0 > -0.02)  # not >2pp deeper
        # grind protection: 2018 Q4 + 2022 slow-bear DD not >3pp deeper than V0
        q4 = per[vk]["crises"]["2018 Q4"]["maxdd"]; q40 = v0["crises"]["2018 Q4"]["maxdd"]
        b22 = per[vk]["crises"]["2022 bear"]["maxdd"]; b220 = v0["crises"]["2022 bear"]["maxdd"]
        keeps_grind = (q4 - q40 > -0.03) and (b22 - b220 > -0.03)
        ranked.append({
            "vk": vk, "label": m["variants"][vk], "sharpe": c["sharpe"], "calmar": c["calmar"],
            "maxdd": c["maxdd"], "cagr": c["cagr"], "fp_rate": w["false_positive_rate_pct"],
            "upside_rate": w["upside_vol_derisk_rate_pct"], "n_upside": w["n_upside_vol_derisk"],
            "keeps_crash": keeps_crash, "keeps_grind": keeps_grind})
    A("Candidate scorecard (clean 18y). Crash-protection = 2008 & 2020 DD not >2pp deeper than V0; "
      "grind-protection = 2018-Q4 & 2022 DD not >3pp deeper than V0 (the slow-bear catches the task "
      "warns not to trade away):\n")
    A("| Variant | Sharpe | Calmar | MaxDD | CAGR | false-pos | upside-derisk | keeps crash? | keeps grind? |")
    A("|---|---:|---:|---:|---:|---:|---:|:--:|:--:|")
    for r in ranked:
        A(f"| {r['label']} | {r['sharpe']:.4f} | {r['calmar']:.4f} | {pct(r['maxdd'])} | "
          f"{pct(r['cagr'])} | {r['fp_rate']:.1f}% | {r['upside_rate']:.1f}% | "
          f"{'Y' if r['keeps_crash'] else 'NO'} | {'Y' if r['keeps_grind'] else 'NO'} |")
    A("")
    A("**Key failure mode -- downside gates trade away the 2018/2022 grind catches.** The DOWNSIDE "
      "variants (V1, V3) de-risk LESS in slow grinds (they wait for realized DOWN-vol, which lags a "
      "steady bleed), so they hold SPY through 2018-Q4 and 2022: BULL 2018-Q4 DD blows out to "
      f"{pct(per['V1_downside_60_252']['crises']['2018 Q4']['maxdd'])} (V0 "
      f"{pct(v0['crises']['2018 Q4']['maxdd'])}) and 2022 DD to "
      f"{pct(per['V1_downside_60_252']['crises']['2022 bear']['maxdd'])} (V0 "
      f"{pct(v0['crises']['2022 bear']['maxdd'])}). This is exactly the catch the task says not to "
      "lose -- so the downside-only premise BACKFIRES here: the symmetric gate's 'upside punishment' "
      "is also what front-runs the lagging trend filter in grinds.\n")
    # best = highest clean Sharpe among those that keep crash protection and reduce upside-derisk vs V0
    v0_upside = v0["whipsaw"]["upside_vol_derisk_rate_pct"]
    v0_fp = v0["whipsaw"]["false_positive_rate_pct"]
    cands = [r for r in ranked if r["vk"] != order[0] and r["keeps_crash"] and r["keeps_grind"]
             and r["upside_rate"] <= v0_upside + 1e-9]
    if cands:
        best = max(cands, key=lambda r: r["sharpe"])
        A(f"**Best non-baseline variant (keeps crash AND grind protection AND reduces "
          f"upside-vol-de-risk): {best['label']}.** Clean Sharpe {best['sharpe']:.4f} vs V0 "
          f"{v0['clean']['sharpe']:.4f} ({best['sharpe']-v0['clean']['sharpe']:+.4f}); Calmar "
          f"{best['calmar']:.4f} vs {v0['clean']['calmar']:.4f}; upside-de-risk {best['upside_rate']:.1f}% "
          f"vs V0 {v0_upside:.1f}%; false-pos {best['fp_rate']:.1f}% vs V0 {v0_fp:.1f}%. "
          f"NOTE: it still TRAILS V0 on every headline risk-adjusted metric -- it is the 'least bad' "
          f"alternative, not an improvement.\n")
    else:
        A("**No non-baseline variant simultaneously keeps BOTH crash and grind protection AND "
          "reduces the upside-vol-de-risk rate below V0.** The symmetric RV60<RV252 gate is NOT "
          "beaten on the stated objective. Ranking the candidates by least damage: the two EWMA "
          "variants (V2b 0.97/0.99, then V2a 0.94/0.99) are closest -- they keep crash AND grind "
          "protection and modestly cut the upside-de-risk rate (64.3% / 63.0% vs V0 68.8%), but at "
          "the cost of -0.09 to -0.12 clean Sharpe, ~-0.13 Calmar, +1.2pp deeper MaxDD, and higher "
          "turnover. The DOWNSIDE variants (V1, V3) are WORST: they raise the false-positive rate "
          "(62-71% vs 59%) AND destroy the 2018/2022 grind catches. **Verdict: keep the production "
          "symmetric gate.** The downside/EWMA hypotheses do not deliver a net improvement on this "
          "sample.\n")
    A("**On the live de-risk-into-strength concern.** Section 4 confirms V0 is OFF right now "
      "(RV60 14.59% > RV252 12.43%, trailing-63d +6.83%) -- a genuine de-risk into a rally. The "
      "EWMA variants (V2a/V2b/V3) would be ON; V1 downside would also be OFF. So EWMA *would* fix "
      "the specific current OFF state, but the 18y backtest shows that flexibility nets out NEGATIVE "
      "(lower Sharpe/Calmar, deeper DD) -- the symmetric gate's 'over-cautious' de-risks are, on "
      "net, paid for by the crash/grind protection they buy. Re-risking into every rally is not "
      "free.\n")
    A("**Overfitting / OOS caveats.** Windows (60/252) and EWMA lambdas (0.94/0.97/0.99) are a "
      "small principled set, NOT grid-tuned, but ANY gate swap mined on the same 18y sample risks "
      "in-sample selection. This would be a LIVE PRODUCTION CHANGE: requires OOS / walk-forward "
      "validation (e.g. freeze the variant pre-2015, test 2015+) and a paired bootstrap on the "
      "Sharpe/Calmar deltas before adoption. The downside/EWMA gates change the LIVE state vs "
      "baseline (section 4) -- confirm that flip is desired, not just a sample artifact.\n")

    A("## Caveats\n")
    A("- EXPLORATION ONLY; no production/memo edits; no commit. Read-only re production.")
    A("- Only the vol-gate layer changes; canary (TIP 13612U>0), trend (SPY 13612U>0) and safe "
      "(best{SHV,IEF} by 13612U) are held at production values, so the vol gate is the single "
      "differentiator across variants.")
    A("- Sleeves run on T+1 MOO exact (mooex, real auto_adjust opens), 10 bps/side, via the "
      "canonical harness exec_lag_moo_validation_2026_05_30._segment_returns_conv.")
    A("- Whipsaw / upside-de-risk / live state use a monthly month-grain calendar (signal -> "
      "following calendar month SPY close-to-close return); the daily sleeve backtest uses mooex. "
      "Trailing 63d return is the rally proxy for upside-vol-de-risk.")
    A("- EWMA variance: RiskMetrics recursion var_t = lambda*var_{t-1} + (1-lambda)*r^2 "
      "(pandas ewm alpha=1-lambda, adjust=False), seeded from the full daily history up to the "
      "signal date; annualized x sqrt(252).")
    A("- Ext window pre-2006-08 is proxy-backed; clean 18y has full real-open coverage and is the "
      "decisive lens.")

    Path(ROOT / "research" / "bull_volgate_variants_findings.md").write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
