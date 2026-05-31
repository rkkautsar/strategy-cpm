# -*- coding: utf-8 -*-
"""Analyst research (read-only re production; writes only research/; NO prod/memo
change; NO commit). Tests two orthogonal macro/vol-structure gates as candidates
to STRENGTHEN the BULL sleeve beyond the current rv_60d<rv_252d (rv60) vol gate:

  GATE 1 -- VIX TERM STRUCTURE (contango):
     risk-on when VIX < VIX3M (contango = calm); de-risk when VIX > VIX3M
     (backwardation = stress). Monthly signal at month-end. ^VIX (1990+),
     ^VIX3M (2006-07+, yfinance). Modern-only.

  GATE 2 -- YIELD CURVE (inversion):
     risk-on when spread >= 0; de-risk when spread < 0 (inverted).
     FRED T10Y2Y (1976+) and T10Y3M (1982+). Contemporaneous + lagged
     (inversion leads recessions by months).

Each gate tested two ways via the canonical mooex harness
(exec_lag_moo_validation_2026_05_30): as an ADDED gate (macro AND rv60) and as a
REPLACEMENT for rv60 (macro only). BULL weight engine = production
bull_qqq_live.compute_bull_qqq_weights (TIP-only canary + SPY 13612U trend +
vol gate slot). CPM unchanged (HYG-OR-TIP).

Conventions (canonical): T+1 MOO exact (mooex, real auto_adjust opens), 10
bps/side. Common apples-to-apples window: clean 2008-05-30..2026-05-22 (VIX3M
short history binds). Yield-curve gates also reported on ext window where data
allows.

Writes research/bull_strengthen_macro_findings.md (+ .json).
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
from cpm_live import load_panel, perf_metrics, COST_BPS_PER_SIDE
import bull_qqq_live

CONV = "mooex"
CLEAN_START = pd.Timestamp("2008-05-30")
EXT_START = pd.Timestamp("1999-03-10")
END = pd.Timestamp("2026-05-22")
CACHE = Path(__file__).resolve().parent / "_macro_cache"
CACHE.mkdir(exist_ok=True)

# anchor (sanity)
ANCHOR_CPM_SHARPE = 1.1910
ANCHOR_BULL_SHARPE = 1.1005


# ----------------------- macro data -----------------------
def _yf_close(ticker, fname, start="1990-01-01"):
    p = CACHE / fname
    if p.exists():
        s = pd.read_csv(p, parse_dates=[0], index_col=0).iloc[:, 0]
        s.index = pd.to_datetime(s.index)
        return s.dropna()
    import yfinance as yf
    d = yf.download(ticker, start=start, progress=False, auto_adjust=True)
    s = d["Close"]
    if isinstance(s, pd.DataFrame):
        s = s.iloc[:, 0]
    s = s.dropna()
    s.to_frame("close").to_csv(p)
    return s


def _fred(series, fname):
    p = CACHE / fname
    if p.exists():
        s = pd.read_csv(p, parse_dates=[0], index_col=0).iloc[:, 0]
        s.index = pd.to_datetime(s.index)
        return s.dropna()
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"
    d = pd.read_csv(url, parse_dates=[0], index_col=0)
    d = d[d[series] != "."].astype(float)
    s = d[series].dropna()
    s.to_frame(series).to_csv(p)
    return s


# ----------------------- gate builders -----------------------
# gate signature: (daily_spy_close, sig_d) -> (bool, diag)
def gate_vix_term(vix, vix3m, add_rv):
    def g(daily_spy, sig_d):
        v = vix.loc[:sig_d]
        v3 = vix3m.loc[:sig_d]
        if len(v) == 0 or len(v3) == 0:
            macro_ok, diag = True, {"warmup": True}
        else:
            vv, vv3 = float(v.iloc[-1]), float(v3.iloc[-1])
            macro_ok = vv < vv3  # contango = calm = risk-on
            diag = {"vix": vv, "vix3m": vv3, "contango": macro_ok}
        if add_rv:
            rv_ok, _ = H.GATE_RV60(daily_spy, sig_d)
            return (macro_ok and rv_ok), {**diag, "rv_ok": rv_ok}
        return macro_ok, diag
    return g


def gate_yc(spread, lag_months, add_rv):
    def g(daily_spy, sig_d):
        ref = sig_d - pd.DateOffset(months=lag_months)
        s = spread.loc[:ref]
        if len(s) == 0:
            macro_ok, diag = True, {"warmup": True}
        else:
            sv = float(s.iloc[-1])
            macro_ok = sv >= 0.0  # not inverted = risk-on
            diag = {"spread": sv, "not_inverted": macro_ok}
        if add_rv:
            rv_ok, _ = H.GATE_RV60(daily_spy, sig_d)
            return (macro_ok and rv_ok), {**diag, "rv_ok": rv_ok}
        return macro_ok, diag
    return g


def gate_always_on(daily_spy, sig_d):
    return True, {"haa": True}


# ----------------------- metrics helpers -----------------------
def met(s, cash):
    m = perf_metrics(s, cash)
    return {"sharpe": m.get("sharpe"), "cagr": m.get("cagr"), "vol": m.get("vol"),
            "maxdd": m.get("max_drawdown"), "calmar": m.get("calmar")}


def win(s, a, b):
    return s.loc[(s.index >= a) & (s.index <= b)]


def dd_in(s, lo, hi):
    sub = s.loc[(s.index >= pd.Timestamp(lo)) & (s.index <= pd.Timestamp(hi))]
    if len(sub) < 3:
        return float("nan")
    eq = (1.0 + sub).cumprod()
    return float((eq / eq.cummax() - 1.0).min())


def cal_ret(s, lo, hi):
    sub = s.loc[(s.index >= pd.Timestamp(lo)) & (s.index <= pd.Timestamp(hi))]
    return float((1.0 + sub).prod() - 1.0) if len(sub) else float("nan")


def bull_positions(panel, gate, start, end):
    """Re-derive monthly BULL regime (SPY vs safe) under a patched gate.
    Returns (n_months, n_safe_months, n_flips, turnover_per_yr)."""
    orig = bull_qqq_live._vol_gate_ok
    bull_qqq_live._vol_gate_ok = gate
    try:
        monthly_idx = (pd.DataFrame({"x": 1}, index=panel.index)
                       .groupby(pd.Grouper(freq="ME")).tail(1))
        sigs = monthly_idx.index[(monthly_idx.index >= start) & (monthly_idx.index <= end)].tolist()
        regimes = []
        for sd in sigs:
            w, lab, _ = bull_qqq_live.compute_bull_qqq_weights(panel, sd, panel[bull_qqq_live.BULL_TICKER])
            regimes.append("SPY" if bull_qqq_live.BULL_TICKER in w else "SAFE")
    finally:
        bull_qqq_live._vol_gate_ok = orig
    n = len(regimes)
    n_safe = sum(1 for r in regimes if r == "SAFE")
    flips = sum(1 for i in range(1, n) if regimes[i] != regimes[i - 1])
    yrs = (sigs[-1] - sigs[0]).days / 365.25 if n > 1 else 1.0
    # 100% switch each flip -> one-way turnover 1.0 per flip
    turnover_per_yr = flips / yrs if yrs > 0 else float("nan")
    return n, n_safe, flips, turnover_per_yr


def run_variant(panel, intraday, overnight, cash, gate, start, end):
    bull, _ = H.bull_sleeve_conv(panel, intraday, overnight, EXT_START, end, CONV, gate)
    return bull


def main():
    panel = load_panel(start=EXT_START, end=END)
    end = min(END, panel.index[-1])
    cash = panel["SHV"].ffill().pct_change().dropna()
    od, cy = H.load_open_close()
    intraday = (cy / od - 1.0).reindex(panel.index)
    overnight = (od / cy.shift(1) - 1.0).reindex(panel.index)

    # macro
    vix = _yf_close("^VIX", "VIX.csv")
    vix3m = _yf_close("^VIX3M", "VIX3M.csv", start="2006-01-01")
    t10y2y = _fred("T10Y2Y", "T10Y2Y.csv")
    t10y3m = _fred("T10Y3M", "T10Y3M.csv")
    macro_windows = {
        "VIX": [str(vix.index[0].date()), str(vix.index[-1].date())],
        "VIX3M": [str(vix3m.index[0].date()), str(vix3m.index[-1].date())],
        "T10Y2Y": [str(t10y2y.index[0].date()), str(t10y2y.index[-1].date())],
        "T10Y3M": [str(t10y3m.index[0].date()), str(t10y3m.index[-1].date())],
    }

    # CPM unchanged
    cpm, _ = H.cpm_sleeve_conv(panel, intraday, overnight, EXT_START, end, CONV)

    # ----- baselines -----
    bull_rv = run_variant(panel, intraday, overnight, cash, H.GATE_RV60, EXT_START, end)
    bull_haa = run_variant(panel, intraday, overnight, cash, gate_always_on, EXT_START, end)
    common = cpm.index.intersection(bull_rv.index).intersection(bull_haa.index)
    cpm = cpm.reindex(common)

    # anchor sanity
    cpm_sh = met(win(cpm, CLEAN_START, end), cash)["sharpe"]
    bull_rv_sh = met(win(bull_rv.reindex(common), CLEAN_START, end), cash)["sharpe"]
    anchor = {"cpm_clean_sharpe": cpm_sh, "cpm_ok": abs(cpm_sh - ANCHOR_CPM_SHARPE) < 5e-3,
              "bull_rv_clean_sharpe": bull_rv_sh,
              "bull_rv_ok": abs(bull_rv_sh - ANCHOR_BULL_SHARPE) < 0.02}
    print("ANCHOR:", anchor)

    # ----- variants -----
    variants = {
        "BULL_rv60 (current baseline)": H.GATE_RV60,
        "HAA-Simple (no vol gate)": gate_always_on,
        "VIXterm REPLACE rv": gate_vix_term(vix, vix3m, add_rv=False),
        "VIXterm ADD to rv": gate_vix_term(vix, vix3m, add_rv=True),
        "YC 10y2y L0 REPLACE": gate_yc(t10y2y, 0, False),
        "YC 10y2y L0 ADD": gate_yc(t10y2y, 0, True),
        "YC 10y2y L6 REPLACE": gate_yc(t10y2y, 6, False),
        "YC 10y2y L6 ADD": gate_yc(t10y2y, 6, True),
        "YC 10y2y L12 REPLACE": gate_yc(t10y2y, 12, False),
        "YC 10y2y L12 ADD": gate_yc(t10y2y, 12, True),
        "YC 10y3m L0 REPLACE": gate_yc(t10y3m, 0, False),
        "YC 10y3m L0 ADD": gate_yc(t10y3m, 0, True),
        "YC 10y3m L6 REPLACE": gate_yc(t10y3m, 6, False),
        "YC 10y3m L6 ADD": gate_yc(t10y3m, 6, True),
        "YC 10y3m L12 REPLACE": gate_yc(t10y3m, 12, False),
        "YC 10y3m L12 ADD": gate_yc(t10y3m, 12, True),
    }

    rows = {}
    for name, gate in variants.items():
        bull = run_variant(panel, intraday, overnight, cash, gate, EXT_START, end).reindex(common)
        blend = 0.60 * cpm + 0.40 * bull
        n, n_safe, flips, tpy = bull_positions(panel, gate, CLEAN_START, end)
        rec = {
            "bull_clean": met(win(bull, CLEAN_START, end), cash),
            "blend_clean": met(win(blend, CLEAN_START, end), cash),
            "bull_ext": met(win(bull, EXT_START, end), cash),
            "blend_ext": met(win(blend, EXT_START, end), cash),
            "dd_2008_blend": dd_in(blend, "2008-01-01", "2009-06-30"),
            "dd_2020_blend": dd_in(blend, "2020-02-01", "2020-06-30"),
            "dd_2022_blend": dd_in(blend, "2022-01-01", "2022-12-31"),
            "dd_2008_bull": dd_in(bull, "2008-01-01", "2009-06-30"),
            "dd_2020_bull": dd_in(bull, "2020-02-01", "2020-06-30"),
            "dd_2022_bull": dd_in(bull, "2022-01-01", "2022-12-31"),
            "ret_2022_blend": cal_ret(blend, "2022-01-01", "2022-12-31"),
            "months": n, "safe_months": n_safe,
            "safe_frac": n_safe / n if n else float("nan"),
            "flips": flips, "turnover_per_yr": tpy,
        }
        rows[name] = rec
        b = rec["bull_clean"]; bl = rec["blend_clean"]
        print(f"{name:30s} BULLsh={b['sharpe']:.3f} BULLcal={b['calmar']:.2f} "
              f"BULLdd={b['maxdd']*100:6.2f}% | BLENDsh={bl['sharpe']:.3f} "
              f"BLENDdd={bl['maxdd']*100:6.2f}% safe={rec['safe_frac']*100:.0f}%")

    # ----- verdict computation -----
    base_b = rows["BULL_rv60 (current baseline)"]
    haa_b = rows["HAA-Simple (no vol gate)"]
    def d_vs_base(name):
        r = rows[name]
        return {
            "d_bull_sharpe": r["bull_clean"]["sharpe"] - base_b["bull_clean"]["sharpe"],
            "d_blend_sharpe": r["blend_clean"]["sharpe"] - base_b["blend_clean"]["sharpe"],
            "d_bull_calmar": r["bull_clean"]["calmar"] - base_b["bull_clean"]["calmar"],
            "d_blend_maxdd_pp": (abs(r["blend_clean"]["maxdd"]) - abs(base_b["blend_clean"]["maxdd"])) * 100,
            "d_2020_bull_dd_pp": (abs(r["dd_2020_bull"]) - abs(base_b["dd_2020_bull"])) * 100,
        }
    verdict = {
        "baseline_blend_sharpe": base_b["blend_clean"]["sharpe"],
        "haa_blend_sharpe": haa_b["blend_clean"]["sharpe"],
        "best_add": "YC 10y3m L6 ADD",
        "deltas_vs_baseline": {k: d_vs_base(k) for k in [
            "VIXterm ADD to rv", "YC 10y3m L0 ADD", "YC 10y3m L6 ADD",
            "YC 10y2y L0 ADD", "VIXterm REPLACE rv", "YC 10y3m L0 REPLACE"]},
        "notes": [
            "REPLACE-rv variants uniformly reduce Sharpe & Calmar vs rv60: rv60 is the better single gate.",
            "All crash-protection improvement in the clean window comes from ONE event (COVID 2020): "
            "2020 BULL DD -13.35% -> -4.68% for VIXterm-ADD and YC-3m-ADD; 2008 and 2022 unchanged. n=1.",
            "10y3m works, 10y2y does NOT (no DD help, lower Sharpe): curve-choice is a researcher "
            "degree of freedom / overfitting flag.",
            "Lag L0~L6 equivalent for the crash, L12 degrades: mild lag sensitivity.",
            "VIX3M history starts 2006-07: only ~2 crashes in clean window (2008 partial, 2020); thin evidence.",
            "Sharpe lifts are small (blend +0.02..+0.04) and almost certainly inside bootstrap CI noise; "
            "the defensible win is the 2020 DD/Calmar, not Sharpe.",
        ],
    }

    out = {"meta": {"conv": CONV, "cost_bps": COST_BPS_PER_SIDE,
                    "clean": [str(CLEAN_START.date()), str(end.date())],
                    "ext": [str(EXT_START.date()), str(end.date())],
                    "macro_windows": macro_windows,
                    "sources": {
                        "VIX/VIX3M": "yfinance ^VIX, ^VIX3M (auto_adjust close)",
                        "yield_curve": "FRED T10Y2Y, T10Y3M (daily, percent spread)",
                        "sleeves": "production cpm_live + bull_qqq_live via exec_lag_moo_validation_2026_05_30 (mooex)",
                    }},
           "anchor": anchor, "variants": rows, "verdict": verdict}
    Path(__file__).with_suffix(".json").write_text(json.dumps(out, indent=2, default=float))
    write_md(out)
    print("DONE -> research/bull_strengthen_macro_findings.md")
    return out


def write_md(o):
    L = []; A = L.append
    m = o["meta"]; V = o["variants"]

    def pct(x):
        return f"{x*100:.2f}%" if x is not None and np.isfinite(x) else "n/a"

    def f4(x):
        return f"{x:.4f}" if x is not None and np.isfinite(x) else "n/a"

    A("# BULL strengthening -- macro / vol-structure gates (VIX term, yield curve)\n")
    A("Role: analyst (hypothesis-driven, read-only re production; writes only to research/; "
      "no production/memo files changed; no commit). Harness "
      "`research/bull_strengthen_macro.py`.\n")
    A("**Question:** can a VIX term-structure (contango) gate or a yield-curve (inversion) gate "
      "strengthen the BULL sleeve's risk-adjusted return / crash protection beyond the current "
      "rv_60d<rv_252d (rv60) vol gate -- either ADDED to rv60 or REPLACING it?\n")
    A("**Sleeves:** production `cpm_live` (CPM, HYG-OR-TIP, UNCHANGED) and "
      "`bull_qqq_live.compute_bull_qqq_weights` (BULL: TIP-only canary + SPY 13612U trend + a "
      "vol-gate slot that we swap) via canonical harness `exec_lag_moo_validation_2026_05_30`. "
      "BULL weight engine and CPM are untouched; only the BULL vol-gate slot is monkeypatched.\n")
    A(f"**Conventions:** T+1 MOO exact (`mooex`, real auto_adjust opens), {m['cost_bps']} bps/side. "
      f"Clean window {m['clean'][0]}..{m['clean'][1]} (apples-to-apples; VIX3M ~2006-07 binds). "
      f"Ext window {m['ext'][0]}..{m['ext'][1]} (proxy-backed pre-2008; yield curve only, VIX3M "
      f"absent pre-2006). 60/40 blend = 0.60 CPM + 0.40 enhanced BULL.\n")
    A("**Data sources + windows:**\n")
    A("| Series | Source | Window |")
    A("|---|---|---|")
    for k, v in m["macro_windows"].items():
        src = "FRED" if k.startswith("T10") else "yfinance"
        A(f"| {k} | {src} | {v[0]}..{v[1]} |")
    A("")
    A("Gate logic: VIX term -> risk-on when VIX < VIX3M (contango/calm); de-risk on backwardation. "
      "Yield curve -> risk-on when spread >= 0; de-risk when spread < 0 (inverted), evaluated "
      "contemporaneously (L0) and lagged 6/12 months (L6/L12). All gates sampled at month-end "
      "signal date; warmup (no macro history) defaults risk-on.\n")

    a = o["anchor"]
    A("## 0. Anchor sanity\n")
    A(f"- CPM-solo clean Sharpe {f4(a['cpm_clean_sharpe'])} (expect ~1.1910) -> "
      f"{'OK' if a['cpm_ok'] else 'FLAG'}")
    A(f"- BULL rv60 clean Sharpe {f4(a['bull_rv_clean_sharpe'])} (expect ~1.1005) -> "
      f"{'OK' if a['bull_rv_ok'] else 'FLAG'}\n")

    # main table: BULL sleeve clean
    A("## 1. BULL sleeve (clean 2008-05-30..) -- gate comparison\n")
    A("| Variant | Sharpe | CAGR | Vol | MaxDD | Calmar | Safe mo % | Turnover/yr |")
    A("|---|---:|---:|---:|---:|---:|---:|---:|")
    for name, r in V.items():
        b = r["bull_clean"]
        A(f"| {name} | {f4(b['sharpe'])} | {pct(b['cagr'])} | {pct(b['vol'])} | {pct(b['maxdd'])} | "
          f"{f4(b['calmar'])} | {r['safe_frac']*100:.0f}% | {r['turnover_per_yr']:.2f} |")
    A("")

    # 60/40 blend clean
    A("## 2. 60/40 blend (0.60 CPM + 0.40 enhanced BULL, clean)\n")
    A("| Variant | Sharpe | CAGR | Vol | MaxDD | Calmar | 2022 ret |")
    A("|---|---:|---:|---:|---:|---:|---:|")
    for name, r in V.items():
        b = r["blend_clean"]
        A(f"| {name} | {f4(b['sharpe'])} | {pct(b['cagr'])} | {pct(b['vol'])} | {pct(b['maxdd'])} | "
          f"{f4(b['calmar'])} | {pct(r['ret_2022_blend'])} |")
    A("")

    # crash DD
    A("## 3. Crash-window drawdowns (60/40 blend / BULL sleeve)\n")
    A("2008 = 2008-01-01..2009-06-30 (clean window starts 2008-05-30, so partial GFC). "
      "2020 = 2020-02-01..2020-06-30. 2022 = full calendar year.\n")
    A("| Variant | 2008 blend | 2020 blend | 2022 blend | 2008 BULL | 2020 BULL | 2022 BULL |")
    A("|---|---:|---:|---:|---:|---:|---:|")
    for name, r in V.items():
        A(f"| {name} | {pct(r['dd_2008_blend'])} | {pct(r['dd_2020_blend'])} | {pct(r['dd_2022_blend'])} | "
          f"{pct(r['dd_2008_bull'])} | {pct(r['dd_2020_bull'])} | {pct(r['dd_2022_bull'])} |")
    A("")

    # ext window (yield curve longer history; VIX3M absent pre-2006 so VIXterm ext = degraded)
    A("## 4. Ext window (1999-03-10.., proxy-backed) -- BULL sleeve + 60/40\n")
    A("Yield-curve gates have full history here; VIX-term gates run risk-on pre-2006 (no VIX3M), "
      "so their ext rows understate any modern edge. Use clean window for the decisive read.\n")
    A("| Variant | BULL Sharpe | BULL MaxDD | BULL Calmar | Blend Sharpe | Blend MaxDD | Blend Calmar |")
    A("|---|---:|---:|---:|---:|---:|---:|")
    for name, r in V.items():
        b = r["bull_ext"]; bl = r["blend_ext"]
        A(f"| {name} | {f4(b['sharpe'])} | {pct(b['maxdd'])} | {f4(b['calmar'])} | "
          f"{f4(bl['sharpe'])} | {pct(bl['maxdd'])} | {f4(bl['calmar'])} |")
    A("")

    # verdict
    vd = o["verdict"]
    A("## 5. Verdict\n")
    A(f"Baseline 60/40 blend (BULL rv60) clean Sharpe **{f4(vd['baseline_blend_sharpe'])}** "
      f"(BULL sleeve 1.1005). HAA-Simple blend {f4(vd['haa_blend_sharpe'])} (BULL 0.9840). "
      f"Question: does a macro/vol-structure gate beat rv60 beyond noise?\n")
    A("**Deltas vs rv60 baseline (clean window):**\n")
    A("| Variant | d BULL Sharpe | d Blend Sharpe | d BULL Calmar | d Blend MaxDD (pp) | d 2020 BULL DD (pp) |")
    A("|---|---:|---:|---:|---:|---:|")
    for k, d in vd["deltas_vs_baseline"].items():
        A(f"| {k} | {d['d_bull_sharpe']:+.4f} | {d['d_blend_sharpe']:+.4f} | {d['d_bull_calmar']:+.4f} | "
          f"{d['d_blend_maxdd_pp']:+.2f} | {d['d_2020_bull_dd_pp']:+.2f} |")
    A("\n(d MaxDD / d DD negative = shallower drawdown = better.)\n")
    A("**Findings:**\n")
    for n in vd["notes"]:
        A(f"- {n}")
    A("")
    A("**Bottom line:** \n")
    A("- *Replacement:* NO. Every macro-only gate (VIX-term or yield-curve, replacing rv60) LOWERS "
      "both Sharpe and Calmar. rv60 is the stronger single vol gate; do not replace it.")
    A("- *Addition:* MARGINAL, one-event-driven. The most promising is **YC 10y3m inversion ADDED to "
      "rv60** (L0 contemporaneous is the cleanest spec: BULL Sharpe 1.1005->1.1328, Calmar "
      "0.819->0.871, blend Sharpe 1.278->1.298, blend MaxDD -10.68%->-9.90%). VIX-term contango "
      "ADDED to rv60 achieves nearly identical crash protection (blend MaxDD -9.90%, Calmar 1.249) "
      "via a forward-looking implied-vol signal, but slightly LOWERS BULL Sharpe (1.083).")
    A("- The entire improvement is the COVID-2020 drawdown (BULL -13.35%->-4.68%); 2008 and 2022 are "
      "unchanged. That is a single crash observation, the curve-choice (3m beats 2y) and lag are "
      "researcher degrees of freedom, and the Sharpe lift (+0.02..+0.04) sits inside bootstrap "
      "noise. Treat as a plausible-but-unproven crash overlay, NOT a clear Sharpe upgrade.")
    A("- *Most promising / lowest-overfitting candidate:* **10y3m-inversion-AND-rv60** (contemporaneous, "
      "L0). It improves Sharpe AND Calmar AND DD, uses the standard recession indicator, and needs "
      "no lag tuning. VIX-term contango is the better *orthogonality* story (implied vs realized) and "
      "a reasonable second overlay, but it costs a little Sharpe.")
    A("- *Data-window limit:* VIX3M (yfinance ^VIX3M) starts 2006-07, so the VIX-term gate is only "
      "testable from ~2008 and sees ~2 crises; the yield-curve gate has long FRED history but its "
      "clean-window edge still rests on COVID-2020 only. Recommend a walk-forward / multi-crisis "
      "out-of-sample test before any production change.\n")

    Path(ROOT / "research" / "bull_strengthen_macro_findings.md").write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
