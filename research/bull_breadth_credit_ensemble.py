# -*- coding: utf-8 -*-
"""Throwaway research (analyst role; READ-ONLY re production; writes ONLY to
research/; NO production/memo files changed; NO commit). EXPLORATION ONLY --
POTENTIAL production BULL improvements; OOS-gated before adoption.

QUESTION
--------
Do BREADTH, CREDIT, or an ENSEMBLE-VOTE of {V0 + breadth + credit} beat the
production BULL vol gate V0 (RV60<RV252) on Calmar AND Martin while KEEPING the
2008/2020 crash + 2018-Q4/2022 grind catches, net of execution lag?

Three literature-ranked signals orthogonal to trend+vol:
 1. BREADTH: % S&P500 constituents > 200d MA (Zaremba 2019). FRED LACKS it and
    constituent reconstruction is out of scope -> PROXY = RSP/SPY equal-weight-
    vs-cap-weight relative strength (RSP starts 2003-05). When equal-weight lags
    cap-weight (ratio below its 200d MA) breadth is narrowing / mega-cap-led ->
    de-risk. Catches narrow rallies the cap-weight index trend misses (e.g.
    2024). DATA GAP: proxy, not the true %>200dMA series; starts 2003-05 so NO
    pre-2003 (1999 dot-com narrowing NOT covered); flagged.
 2. CREDIT: HY OAS (FRED BAMLH0A0HYM2) is license-truncated to the last ~3y via
    fredgraph (UNUSABLE for an 18-27y backtest -- confirmed, documented). Use
    Moody's Baa-Aaa spread (FRED BAA, AAA; monthly, 1919+) as the credit-quality
    slope. de-risk on WIDENING spread (Chava-Gallmeyer-Park / Han-Subrahmanyam-
    Zhou: widening credit predicts low equity returns). Plus SLOOS bank lending
    standards (FRED DRTSCILM, quarterly 1990+); de-risk when net% tightening>0.
 3. ENSEMBLE-VOTE: voters = {V0 RV gate, breadth proxy, credit slope}.
    E_frac: SPY weight = (#risk-on)/3 (fractional). E_k2: full SPY iff >=2 on.
    E_k3: full SPY iff all 3 on (== ADD-all). Canary (TIP 13612U>0) + trend
    (SPY 13612U>0) remain HARD production pre-gates in every variant.

Each single signal tested as REPLACE V0 (R) and ADD to V0 (A: de-risk if EITHER
fires). PRIMARY metric = Calmar AND Martin (BULL is a drawdown-control overlay).

HONESTY GUARDS
 (a) execution lag: engine is T+1 MOO exact (signal uses data <= month-end
     sig_d, executed next open) -- already lagged, no same-day application.
 (b) SLOOS quarterly + released w/ lag -> applied with a release lag (use only
     the survey reading available at decision time; DRTSCILM dated quarter-start
     is lagged 1 full quarter to be safe). Baa-Aaa monthly lagged 1 month.
 (c) single 18y in-sample -> any winner flagged for OOS/walk-forward.

Reuses bull_volgate_variants (BV) sleeve machinery verbatim; swaps ONLY the
vol-slot decision rule (singles) or the vol-slot vote (ensemble). ANCHOR: BULL
V0 clean Sharpe 1.1005 / Calmar 0.8189 / Martin 3.0714 / MaxDD -13.35%.

Writes research/bull_breadth_credit_ensemble_findings.md (+ .json).
"""
from __future__ import annotations
import sys, json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

import bull_volgate_variants as BV
import exec_lag_moo_validation_2026_05_30 as H
from cpm_live import load_panel, sig_13612U

CACHE = HERE / "_macro_cache"
CACHE.mkdir(exist_ok=True)
CLEAN_START = BV.CLEAN_START
EXT_START = BV.EXT_START
END = BV.END
CRISES = BV.CRISES
COST = BV.COST
ANCHOR = {"sharpe": 1.1005, "calmar": 0.8189, "martin": 3.0714, "maxdd": -13.35}


# --------------------------- data fetch (cached) ---------------------------
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


# --------------------------- signal series ---------------------------
def build_signals():
    rsp = _yf_close("RSP", "RSP_yf.csv")
    spy = _yf_close("SPY", "SPY_breadth_yf.csv")
    idx = spy.index.union(rsp.index)
    rsp_a = rsp.reindex(idx).ffill()
    spy_a = spy.reindex(idx).ffill()
    ratio = (rsp_a / spy_a).dropna()
    ratio_ma200 = ratio.rolling(200).mean()

    baa = _fred("BAA", "fred_BAA.csv")
    aaa = _fred("AAA", "fred_AAA.csv")
    cidx = baa.index.union(aaa.index)
    spread = (baa.reindex(cidx).ffill() - aaa.reindex(cidx).ffill()).dropna()  # pct points

    sloos = _fred("DRTSCILM", "fred_DRTSCILM.csv")  # net % tightening C&I (large/med)
    return {"ratio": ratio, "ratio_ma200": ratio_ma200, "spread": spread, "sloos": sloos}


# --------------------------- gate builders ---------------------------
# gate signature: (daily_spy_close, sig_d) -> (risk_on: bool, diag: dict)

def gate_breadth(SIG):
    ratio, ma = SIG["ratio"], SIG["ratio_ma200"]
    def g(daily_spy, sig_d):
        r = ratio.loc[:sig_d]
        m = ma.loc[:sig_d]
        if len(r) == 0 or len(m.dropna()) == 0:
            return True, {"warmup": True}
        rv, mv = float(r.iloc[-1]), float(m.dropna().iloc[-1])
        return (rv >= mv), {"short": rv, "long": mv}  # eq-wt keeping pace = healthy
    return g


def gate_credit_slope(SIG, lag_months=1, chg_months=3):
    """de-risk when Baa-Aaa spread WIDENING over trailing chg_months (>0)."""
    sp = SIG["spread"]
    def g(daily_spy, sig_d):
        ref = sig_d - pd.DateOffset(months=lag_months)
        s = sp.loc[:ref]
        if len(s) < chg_months + 1:
            return True, {"warmup": True}
        cur = float(s.iloc[-1])
        past = float(s.iloc[-1 - chg_months])
        chg = cur - past
        return (chg <= 0.0), {"short": cur, "long": cur - chg}  # not widening = risk-on
    return g


def gate_credit_level(SIG, lag_months=1, win_m=60):
    """de-risk when spread ABOVE its trailing win_m-month median (elevated stress)."""
    sp = SIG["spread"]
    def g(daily_spy, sig_d):
        ref = sig_d - pd.DateOffset(months=lag_months)
        s = sp.loc[:ref]
        if len(s) < 13:
            return True, {"warmup": True}
        cur = float(s.iloc[-1])
        med = float(s.iloc[-win_m:].median())
        return (cur <= med), {"short": cur, "long": med}
    return g


def gate_sloos(SIG, lag_q=1):
    """de-risk when net% tightening C&I standards > 0. Quarterly + release lag:
    DRTSCILM dated quarter-start; lag 1 full quarter so only a fully-released
    survey reading is used at decision time."""
    sl = SIG["sloos"]
    def g(daily_spy, sig_d):
        ref = sig_d - pd.DateOffset(months=3 * lag_q + 1)  # +1mo release buffer
        s = sl.loc[:ref]
        if len(s) == 0:
            return True, {"warmup": True}
        cur = float(s.iloc[-1])
        return (cur <= 0.0), {"short": cur, "long": 0.0}  # not tightening = risk-on
    return g


def add_gate(new_gate, fast=60, slow=252):
    """ADD: risk-on iff RV gate AND new gate (de-risk if EITHER fires)."""
    def g(daily_spy, sig_d):
        rv_ok, rvd = BV.gate_symmetric(daily_spy, sig_d, fast, slow)
        nk_ok, nkd = new_gate(daily_spy, sig_d)
        return (rv_ok and nk_ok), {"short": nkd.get("short", float("nan")),
                                   "long": nkd.get("long", float("nan")),
                                   "rv_ok": rv_ok, "warmup": nkd.get("warmup", False)}
    return g


# --------------------------- ensemble weight fn ---------------------------
def bull_wf_ensemble(close, sig_d, daily_spy, voters, mode, k=None):
    """canary (TIP 13612U>0) + trend (SPY 13612U>0) HARD pre-gates. Among the
    voter risk-signals compute vote -> SPY weight (mode 'frac' or 'k')."""
    monthly = close.loc[:sig_d].resample("ME").last()
    tipm = sig_13612U(monthly["TIP"]) if "TIP" in monthly.columns else float("nan")
    canary_ok = bool(pd.notna(tipm) and tipm > 0)
    spym = sig_13612U(monthly["SPY"]) if "SPY" in monthly.columns else float("nan")
    trend_ok = bool(pd.notna(spym) and spym > 0)
    safe = BV._pick_safe(monthly)
    if not (canary_ok and trend_ok):
        return {safe: 1.0}
    votes = [bool(g(daily_spy, sig_d)[0]) for g in voters]
    n_on, N = sum(votes), len(votes)
    if mode == "frac":
        w = n_on / N
    else:  # k-of-N
        w = 1.0 if n_on >= k else 0.0
    if w <= 0.0:
        return {safe: 1.0}
    if w >= 1.0:
        return {"SPY": 1.0}
    return {"SPY": w, safe: 1.0 - w}


def run_ensemble_sleeve(close, daily, intraday, overnight, daily_spy, start, end,
                        voters, mode, k=None):
    wf = lambda sd: bull_wf_ensemble(close, sd, daily_spy, voters, mode, k)
    s, _ = H._segment_returns_conv(close, daily, wf, start, end, BV.CONV,
                                   COST, intraday, overnight)
    return s


def ensemble_calendar(close, daily_spy, voters, mode, k, start, end):
    """Per month-end: canary/trend, vote weight, governed-next SPY, trail63."""
    monthly_close = close.resample("ME").last()
    spy_m = daily_spy.resample("ME").last().pct_change()
    spy_by_p = pd.Series(spy_m.values, index=spy_m.index.to_period("M"))
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
        votes = [bool(g(daily_spy, sd)[0]) for g in voters]
        n_on = sum(votes)
        w = (n_on / len(voters)) if mode == "frac" else (1.0 if n_on >= k else 0.0)
        if not (canary_ok and trend_ok):
            w = 0.0
        px = daily_spy.loc[:sd].dropna()
        trail63 = float(px.iloc[-1] / px.iloc[-64] - 1.0) if len(px) >= 64 else float("nan")
        ap = sd.to_period("M") + 1
        nxt = float(spy_by_p.loc[ap]) if ap in spy_by_p.index else float("nan")
        rows.append({"sig": sd, "canary_ok": canary_ok, "trend_ok": trend_ok,
                     "spy_weight": w, "n_on": n_on, "spy_next": nxt, "trail63": trail63})
    return pd.DataFrame(rows).set_index("sig")


# --------------------------- variant registry ---------------------------
def build_variants(SIG):
    gb = gate_breadth(SIG)
    gc = gate_credit_slope(SIG)
    gcl = gate_credit_level(SIG)
    gs = gate_sloos(SIG)
    gate_variants = {
        "V0":      (lambda d, s: BV.gate_symmetric(d, s, 60, 252), "V0 RV60<RV252 (PROD)"),
        "B_R":     (gb, "Breadth proxy RSP/SPY (REPLACE)"),
        "B_A":     (add_gate(gb), "RV AND breadth (ADD)"),
        "Cslope_R": (gc, "Credit Baa-Aaa slope (REPLACE)"),
        "Cslope_A": (add_gate(gc), "RV AND credit slope (ADD)"),
        "Clevel_A": (add_gate(gcl), "RV AND credit level (ADD)"),
        "Sloos_R": (gs, "SLOOS tightening (REPLACE)"),
        "Sloos_A": (add_gate(gs), "RV AND SLOOS (ADD)"),
    }
    voters = [lambda d, s: BV.gate_symmetric(d, s, 60, 252), gb, gc]
    ensemble_variants = {
        "E_frac": (voters, "frac", None, "Ensemble vote frac (V0+breadth+credit)/3"),
        "E_k2":   (voters, "k", 2, "Ensemble >=2 of 3 (V0,breadth,credit)"),
        "E_k3":   (voters, "k", 3, "Ensemble all-3 (==ADD-all)"),
    }
    return gate_variants, ensemble_variants


# --------------------------- main ---------------------------
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

    SIG = build_signals()
    data_cov = {
        "breadth_ratio": [str(SIG["ratio"].index.min().date()), str(SIG["ratio"].index.max().date())],
        "credit_spread": [str(SIG["spread"].index.min().date()), str(SIG["spread"].index.max().date())],
        "sloos": [str(SIG["sloos"].index.min().date()), str(SIG["sloos"].index.max().date())],
    }
    gate_variants, ensemble_variants = build_variants(SIG)

    # ---- run single-gate sleeves (reuse BV machinery) ----
    sleeves, cals = {}, {}
    for vk, (gate, _lab) in gate_variants.items():
        sleeves[vk] = BV.run_variant_sleeve(bclose, bdaily, intraday, overnight,
                                            daily_spy, EXT_START, end, gate)
        cals[vk] = BV.signal_calendar(bclose, daily_spy, gate, CLEAN_START, end)

    # ---- run ensemble sleeves ----
    ecals = {}
    for vk, (voters, mode, k, _lab) in ensemble_variants.items():
        sleeves[vk] = run_ensemble_sleeve(bclose, bdaily, intraday, overnight,
                                          daily_spy, EXT_START, end, voters, mode, k)
        ecals[vk] = ensemble_calendar(bclose, daily_spy, voters, mode, k, CLEAN_START, end)

    # align
    common = sleeves["V0"].index
    for vk in sleeves:
        common = common.intersection(sleeves[vk].index)
    for vk in sleeves:
        sleeves[vk] = sleeves[vk].reindex(common)

    # anchor
    v0c = BV.met(BV.win(sleeves["V0"], CLEAN_START, end), cash)
    a_ok = (abs(v0c["sharpe"] - ANCHOR["sharpe"]) < 0.01 and
            abs(v0c["calmar"] - ANCHOR["calmar"]) < 0.01 and
            abs(v0c["martin"] - ANCHOR["martin"]) < 0.02 and
            abs(v0c["maxdd"] * 100 - ANCHOR["maxdd"]) < 0.30)
    print(f"ANCHOR V0 clean: Sharpe={v0c['sharpe']:.4f} Calmar={v0c['calmar']:.4f} "
          f"Martin={v0c['martin']:.4f} MaxDD={v0c['maxdd']*100:.2f}% -> "
          f"{'CONFIRMED' if a_ok else 'FLAG'}")
    if not a_ok:
        print("ANCHOR MISMATCH -- aborting.")
        sys.exit(1)

    all_order = list(gate_variants.keys()) + list(ensemble_variants.keys())
    labels = {vk: gate_variants[vk][1] for vk in gate_variants}
    labels.update({vk: ensemble_variants[vk][3] for vk in ensemble_variants})

    per = {}
    for vk in all_order:
        s = sleeves[vk]
        clean_m = BV.met(BV.win(s, CLEAN_START, end), cash)
        ext_m = BV.met(BV.win(s, EXT_START, end), cash)
        crises = {name: BV.window_dd_ret(s, lo, hi) for name, (lo, hi) in CRISES.items()}
        rec = {"clean": clean_m, "ext": ext_m, "crises": crises}
        if vk in gate_variants:
            cal = cals[vk]
            rec["whipsaw"] = BV.whipsaw_stats(cal)
            rec["turnover_ann"] = BV.annualized_turnover(cal, CLEAN_START, end)
            lr = cal.loc[cal.index[-1]]
            rec["live"] = {"sig_date": str(cal.index[-1].date()),
                           "canary_ok": bool(lr["canary_ok"]), "trend_ok": bool(lr["trend_ok"]),
                           "vol_ok": bool(lr["vol_ok"]),
                           "risk_on": bool(lr["canary_ok"] and lr["trend_ok"] and lr["vol_ok"]),
                           "short": float(lr.get("vd_short", float("nan"))),
                           "long": float(lr.get("vd_long", float("nan")))}
        else:
            cal = ecals[vk]
            lr = cal.loc[cal.index[-1]]
            rec["live"] = {"sig_date": str(cal.index[-1].date()),
                           "canary_ok": bool(lr["canary_ok"]), "trend_ok": bool(lr["trend_ok"]),
                           "spy_weight": float(lr["spy_weight"]), "n_on": int(lr["n_on"])}
        per[vk] = rec

    out = {"meta": {"conv": BV.CONV, "cost_bps": COST,
                    "clean": [str(CLEAN_START.date()), str(end.date())],
                    "ext": [str(EXT_START.date()), str(end.date())],
                    "labels": labels, "order": all_order,
                    "gate_keys": list(gate_variants.keys()),
                    "ensemble_keys": list(ensemble_variants.keys()),
                    "crises": {k: list(v) for k, v in CRISES.items()},
                    "data_coverage": data_cov},
           "anchor": {"v0_clean": v0c, "anchor_ok": bool(a_ok), "expected": ANCHOR},
           "per_variant": per}
    (HERE / "bull_breadth_credit_ensemble_findings.json").write_text(
        json.dumps(out, indent=2, default=float))
    write_md(out)
    print("DONE -> research/bull_breadth_credit_ensemble_findings.md")
    return out


def write_md(o):
    L = []; A = L.append
    m = o["meta"]; per = o["per_variant"]; order = m["order"]; lab = m["labels"]
    v0 = per["V0"]; b0 = v0["clean"]

    def pct(x):
        return f"{x*100:.2f}%" if isinstance(x, (int, float)) and np.isfinite(x) else "n/a"

    A("# BULL breadth / credit / ensemble-vote vs production RV vol gate (V0)\n")
    A("Role: analyst (hypothesis-driven; READ-ONLY re production; writes only to research/; "
      "NO production/memo edits; NO commit). EXPLORATION ONLY; OOS-gated before adoption. "
      "Harness `research/bull_breadth_credit_ensemble.py` (reuses `bull_volgate_variants` sleeve "
      "machinery verbatim; swaps ONLY the vol-slot decision rule / vote).\n")
    A("**Question.** Do BREADTH, CREDIT, or an ENSEMBLE-VOTE of {V0 + breadth + credit} beat V0 "
      "(RV60<RV252) on **Calmar AND Martin** while KEEPING the 2008/2020 crash + 2018-Q4/2022 "
      "grind catches, net of execution lag? Canary (TIP 13612U>0) + trend (SPY 13612U>0) held at "
      "production in every variant; only the vol slot changes.\n")
    dc = m["data_coverage"]
    A("## 0. DATA-AVAILABILITY (load-bearing)\n")
    A("- **BREADTH (the hardest).** The literature signal is % of S&P500 constituents > their "
      "200d MA. **FRED does NOT carry it**, and full constituent reconstruction is out of scope. "
      f"PROXY used = **RSP/SPY equal-weight-vs-cap-weight relative strength** (coverage "
      f"{dc['breadth_ratio'][0]}..{dc['breadth_ratio'][1]}). When equal-weight lags cap-weight "
      "(ratio below its 200d MA) breadth is narrowing / mega-cap-led -> de-risk. **GAP: this is a "
      "PROXY, not the true %>200dMA; RSP starts 2003-05 so there is NO pre-2003 coverage -- the "
      "1999 dot-com narrowing is NOT testable, only 2008+ (and the 2024 narrow-rally episode).** "
      "Breadth results are therefore clean-18y-only and proxy-bound.")
    A("- **CREDIT.** HY OAS (FRED `BAMLH0A0HYM2`) is **license-truncated to the last ~3 years** "
      "via fredgraph (confirmed: returns only 2023-05+, n~794) -- UNUSABLE for an 18-27y backtest. "
      f"Substitute = **Moody's Baa-Aaa spread** (FRED `BAA`,`AAA`; monthly; coverage "
      f"{dc['credit_spread'][0]}..{dc['credit_spread'][1]}) as the credit-quality slope, plus "
      f"**SLOOS** net% tightening C&I standards (FRED `DRTSCILM`; quarterly; "
      f"{dc['sloos'][0]}..{dc['sloos'][1]}). Both have full clean+ext history.")
    A("- **EXECUTION LAG.** Engine = T+1 MOO exact: signal uses data <= month-end sig_d, executed "
      "next open. Baa-Aaa lagged 1 month; SLOOS lagged 1 full quarter + 1mo release buffer (only a "
      "fully-released survey reading is used at decision time -- no release look-ahead).\n")

    a = o["anchor"]; ab = a["v0_clean"]
    A("## 1. Anchor gate\n")
    A(f"BULL V0 clean Sharpe **{ab['sharpe']:.4f}** / Calmar **{ab['calmar']:.4f}** / Martin "
      f"**{ab['martin']:.4f}** / MaxDD **{pct(ab['maxdd'])}** vs anchor {a['expected']['sharpe']} / "
      f"{a['expected']['calmar']} / {a['expected']['martin']} / {a['expected']['maxdd']}% -> "
      f"**{'CONFIRMED' if a['anchor_ok'] else 'FLAG'}**.\n")

    A("## 2. PRIMARY -- Calmar / Martin (+ Sharpe / MaxDD / CAGR), BULL clean 18y\n")
    A("| Variant | Calmar | Martin | Sharpe | MaxDD | CAGR | Vol |")
    A("|---|---:|---:|---:|---:|---:|---:|")
    for vk in order:
        r = per[vk]["clean"]
        A(f"| {lab[vk]} | {r['calmar']:.4f} | {r['martin']:.4f} | {r['sharpe']:.4f} | "
          f"{pct(r['maxdd'])} | {pct(r['cagr'])} | {pct(r['vol'])} |")
    A("")
    A("### Delta vs V0 (clean)\n")
    A("| Variant | dCalmar | dMartin | dSharpe | dMaxDD (pp) | dCAGR (pp) |")
    A("|---|---:|---:|---:|---:|---:|")
    for vk in order:
        r = per[vk]["clean"]
        A(f"| {lab[vk]} | {r['calmar']-b0['calmar']:+.4f} | {r['martin']-b0['martin']:+.4f} | "
          f"{r['sharpe']-b0['sharpe']:+.4f} | {(abs(r['maxdd'])-abs(b0['maxdd']))*100:+.2f} | "
          f"{(r['cagr']-b0['cagr'])*100:+.2f} |")
    A("\n*dCalmar/dMartin/dSharpe>0 = better. dMaxDD>0 = deeper (worse). dCAGR>0 = more return. "
      "Breadth (B_*) + any breadth-containing ensemble (E_*) are PROXY-bound 2008+; credit/SLOOS "
      "span full history.*\n")
    A("### Ext 27y (partly proxy-backed; breadth proxy only 2003-05+, neutral-ON before)\n")
    A("| Variant | Calmar | Martin | Sharpe | MaxDD | CAGR |")
    A("|---|---:|---:|---:|---:|---:|")
    for vk in order:
        r = per[vk]["ext"]
        A(f"| {lab[vk]} | {r['calmar']:.4f} | {r['martin']:.4f} | {r['sharpe']:.4f} | "
          f"{pct(r['maxdd'])} | {pct(r['cagr'])} |")
    A("")

    A("## 3. Whipsaw (single-gate variants, clean 18y monthly signals)\n")
    A("Vol-slot de-risk = canary_ok AND trend_ok AND NOT gate_ok. False de-risk = next-month SPY "
      "return > 0.\n")
    A("| Variant | de-risk mo | false-pos | false-pos rate | mean SPY next | turnover/yr |")
    A("|---|---:|---:|---:|---:|---:|")
    for vk in m["gate_keys"]:
        w = per[vk]["whipsaw"]
        A(f"| {lab[vk]} | {w['n_volgate_derisk']} | {w['n_false_positive']} | "
          f"{w['false_positive_rate_pct']:.1f}% | {w['mean_spy_next_on_derisk_pct']:+.2f}% | "
          f"{per[vk]['turnover_ann']*100:.1f}% |")
    A("")

    A("## 4. Crash + grind protection (BULL sleeve MaxDD / total return in window)\n")
    A("Must KEEP: 2008 GFC + 2020 COVID crashes; 2018-Q4 + 2022 grinds (V0: 2018-Q4 -2.14%, "
      "2022 -0.30%).\n")
    cnames = list(m["crises"].keys())
    A("| Variant | " + " | ".join(f"{c} DD/Ret" for c in cnames) + " |")
    A("|---|" + "---|" * len(cnames))
    for vk in order:
        cells = [f"{pct(per[vk]['crises'][c]['maxdd'])} / {pct(per[vk]['crises'][c]['ret'])}"
                 for c in cnames]
        A(f"| {lab[vk]} | " + " | ".join(cells) + " |")
    A("\n*Windows: " + "; ".join(f"{c} {m['crises'][c][0]}..{m['crises'][c][1]}" for c in cnames) + ".*\n")

    A("## 5. Live current state (latest signal month)\n")
    A("| Variant | signal date | canary | trend | gate/vote | SPY weight |")
    A("|---|---|:--:|:--:|---|---:|")
    for vk in order:
        lv = per[vk]["live"]
        if vk in m["gate_keys"]:
            gate_state = "ON" if lv["risk_on"] else "OFF"
            wt = "100%" if lv["risk_on"] else "0%"
            A(f"| {lab[vk]} | {lv['sig_date']} | {'Y' if lv['canary_ok'] else 'n'} | "
              f"{'Y' if lv['trend_ok'] else 'n'} | {gate_state} | {wt} |")
        else:
            A(f"| {lab[vk]} | {lv['sig_date']} | {'Y' if lv['canary_ok'] else 'n'} | "
              f"{'Y' if lv['trend_ok'] else 'n'} | {lv['n_on']}/3 on | {lv['spy_weight']*100:.0f}% |")
    A("")

    A("## 6. VERDICT (PRIMARY = Calmar AND Martin; keep crash + grind)\n")
    rows = []
    for vk in order:
        if vk == "V0":
            continue
        c = per[vk]["clean"]
        def dd(name):
            return per[vk]["crises"][name]["maxdd"]
        def dd0(name):
            return v0["crises"][name]["maxdd"]
        keeps_crash = (dd("2008 GFC") - dd0("2008 GFC") > -0.02) and (dd("2020 COVID") - dd0("2020 COVID") > -0.02)
        keeps_grind = (dd("2018 Q4") - dd0("2018 Q4") > -0.03) and (dd("2022 bear") - dd0("2022 bear") > -0.03)
        beats = (c["calmar"] > b0["calmar"] + 1e-9 and c["martin"] > b0["martin"] + 1e-9)
        rows.append({"vk": vk, "label": lab[vk], "calmar": c["calmar"], "martin": c["martin"],
                     "sharpe": c["sharpe"], "maxdd": c["maxdd"], "keeps_crash": keeps_crash,
                     "keeps_grind": keeps_grind, "beats": beats})
    rows.sort(key=lambda r: r["calmar"], reverse=True)
    A(f"V0 baseline: Calmar {b0['calmar']:.4f}, Martin {b0['martin']:.4f}, Sharpe {b0['sharpe']:.4f}, "
      f"MaxDD {pct(b0['maxdd'])}. keeps crash = 2008 & 2020 DD not >2pp deeper; keeps grind = "
      "2018-Q4 & 2022 DD not >3pp deeper; beats = BOTH Calmar AND Martin above V0.\n")
    A("| Rank | Variant | Calmar | Martin | Sharpe | MaxDD | keeps crash? | keeps grind? | beats C+M? |")
    A("|---:|---|---:|---:|---:|---:|:--:|:--:|:--:|")
    A(f"| - | {lab['V0']} | {b0['calmar']:.4f} | {b0['martin']:.4f} | {b0['sharpe']:.4f} | "
      f"{pct(b0['maxdd'])} | Y | Y | - |")
    for i, r in enumerate(rows, 1):
        A(f"| {i} | {r['label']} | {r['calmar']:.4f} | {r['martin']:.4f} | {r['sharpe']:.4f} | "
          f"{pct(r['maxdd'])} | {'Y' if r['keeps_crash'] else 'NO'} | "
          f"{'Y' if r['keeps_grind'] else 'NO'} | {'Y' if r['beats'] else 'NO'} |")
    A("")
    winners = [r for r in rows if r["beats"] and r["keeps_crash"] and r["keeps_grind"]]
    if winners:
        best = max(winners, key=lambda r: (r["calmar"], r["martin"]))
        A(f"**WINNER: {best['label']}** beats V0 on BOTH Calmar ({best['calmar']:.4f} vs "
          f"{b0['calmar']:.4f}) and Martin ({best['martin']:.4f} vs {b0['martin']:.4f}) while "
          "keeping crash + grind catches. IN-SAMPLE; OOS/walk-forward + paired bootstrap required "
          "before adoption" + (" (and breadth-containing -> proxy-bound, see Section 0)." if "B" in best["vk"] or best["vk"].startswith("E") else ".") + "\n")
    else:
        A("**No candidate beats V0 on BOTH Calmar AND Martin while keeping crash AND grind "
          "protection.** Keep production V0 (RV60<RV252).\n")

    A("## 7. Caveats / OVERFITTING / OOS\n")
    A("- EXPLORATION ONLY; READ-ONLY re production; NO production/memo edits; NO commit.")
    A("- **Breadth is a PROXY** (RSP/SPY relative strength), NOT the literature %>200dMA series, "
      "and is limited to 2003-05+ (clean 18y only; no 1999). Any breadth/ensemble verdict is "
      "proxy-bound and must be re-tested on a true breadth series before adoption.")
    A("- **HY OAS unusable** via fredgraph (3y license truncation); credit uses Moody's Baa-Aaa "
      "(investment-grade quality slope, not high-yield) + SLOOS. A true daily HY OAS backtest "
      "requires a licensed data source.")
    A("- Execution: T+1 MOO exact (no same-day application). Baa-Aaa lagged 1mo; SLOOS lagged 1 "
      "quarter +1mo buffer (no release look-ahead). Monthly RV/credit signals are robust to a "
      "1-day shift by construction (month-end close data, next-open execution).")
    A("- Single 18y in-sample; any winner needs OOS / walk-forward (freeze pre-2015, test 2015+) "
      "+ paired bootstrap on Calmar/Martin deltas before a live change.")
    A("- Only the vol slot changes; canary (TIP 13612U>0) + trend (SPY 13612U>0) + safe "
      "(best{SHV,IEF}) held at production. mooex T+1, 10 bps/side, via "
      "exec_lag_moo_validation_2026_05_30._segment_returns_conv.")

    (ROOT / "research" / "bull_breadth_credit_ensemble_findings.md").write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
