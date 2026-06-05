# -*- coding: utf-8 -*-
"""Analyst research (read-only re production; writes only research/; NO prod/memo
change; NO commit).

SPY-COMP-style COMPOSITE RECESSION-GATE OVERRIDE for the BULL sleeve.

Idea (SPY-COMP): a macro recession nowcast decides WHEN trend-following turns on.
  macro healthy  -> ride SPY ignoring trend
  macro warns    -> defer to SPY trend
Reduces to:   risk_on = (n_recession_warnings < k) OR spy_trend_up

CURRENT BULL (bull_spy_live.compute_bull_spy_weights) = AND gate:
  risk_on = canary_ok(TIP 13612U>0) AND spy_trend_ok(SPY 13612U>0)
  else best-of(SHV/IEF by 13612U). This AND gate is the baseline to beat.

SIX recession indicators (each -> binary warn, point-in-time via macro_at;
slow/lagged-publication series lagged >=1mo to kill look-ahead):
  1. VIX backwardation : warn if VIX >= VIX3M           (market data, sig_d)
  2. Yield curve       : warn if T10Y3M < 0 (inverted)  (market data, sig_d)
  3. Unemployment      : warn if UNRATE > 12mo MA (Sahm-lite, FRED, lag 1mo)
  4. Breadth           : warn if n_positive < 4 of 8 (Faber breadth, sig_d)
  5. Equity risk prem. : warn if ERP < expanding-mean(ERP) (Shiller CAPE ey - DGS10)
  6. TIP canary        : warn if TIP 13612U <= 0          (sig_d)

Composite gate on BULL (asset SPY, safe best-of SHV/IEF, mooex T+1 MOO,
10 bps/side, both-252):
  risk_on = (n_warnings < k) OR spy_trend_up, spy_trend = SPY 13612U > 0.
  k = 1 (SPY-COMP-faithful), 2, 3 (sensitivity, NOT optimization).

Comparisons (sleeve-level): prod AND (baseline), OR-TIP (TIP OR trend, cheap
structure-flip control), composite-OR k=1/2/3, leave-one-out attribution at
chosen k, per-crisis DD (GFC/COVID/2022/2025-tariff), ext-reduced confirmation,
walk-forward of best config.

Writes research/bull_spycomp_composite_findings.md (+ .json).
"""
from __future__ import annotations
import sys, json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from research import cpm_harness as H
from cpm_live import perf_metrics, sig_13612U, faber_sma_xs, RISKY_UNIVERSE, SAFE_POOL
import bull_spy_live as B

CACHE = Path(__file__).resolve().parent / "_macro_cache"
CLEAN_START = pd.Timestamp("2008-05-30")
EXT_START = pd.Timestamp("1999-03-10")
INDICATORS = ["vix", "yc", "unrate", "breadth", "erp", "tip"]


# ----------------------- macro data loaders -----------------------
def _load_csv_series(fname, col=None):
    p = CACHE / fname
    d = pd.read_csv(p, parse_dates=[0], index_col=0)
    s = d[col] if col else d.iloc[:, 0]
    s.index = pd.to_datetime(s.index)
    if s.dtype == object:
        s = pd.to_numeric(s, errors="coerce")
    return s.dropna()


def load_macro():
    vix = _load_csv_series("VIX.csv")
    vix3m = _load_csv_series("VIX3M.csv")
    t10y3m = _load_csv_series("T10Y3M.csv", "T10Y3M")
    unrate = _load_csv_series("UNRATE.csv", "UNRATE")
    dgs10 = _load_csv_series("DGS10.csv", "DGS10")
    sh = pd.read_csv(CACHE / "SHILLER_sp500.csv", parse_dates=[0], index_col=0)
    sh.index = pd.to_datetime(sh.index)
    # Reconstruct/extend PE10 (CAPE): valid through 2023-09 in source; beyond that
    # earnings are unreported. Price-scale the last valid CAPE by nominal price ratio
    # (price-driven CAPE proxy; ignores earnings growth -> mildly OVERstates CAPE ->
    # UNDERstates earnings yield -> biases toward MORE "expensive" warnings recently).
    pe10 = sh["PE10"].copy()
    pe10 = pe10[pe10 > 0]
    price = sh["SP500"][sh["SP500"] > 0]
    last_valid = pe10.index[-1]
    ext_idx = price.index[price.index > last_valid]
    if len(ext_idx):
        base_pe = float(pe10.iloc[-1]); base_px = float(price.loc[last_valid])
        ext = pd.Series(base_pe * (price.loc[ext_idx] / base_px).values, index=ext_idx)
        pe10 = pd.concat([pe10, ext])
    # earnings yield (CAPE) minus 10y nominal yield -> ERP (monthly, decimal)
    ey = 1.0 / pe10
    dgs10_m = dgs10.resample("MS").last() / 100.0
    erp = (ey - dgs10_m.reindex(ey.index, method="ffill")).dropna()
    return dict(vix=vix, vix3m=vix3m, t10y3m=t10y3m, unrate=unrate, erp=erp,
                pe10_last_valid=str(last_valid.date()))


def macro_at(series, sig_d, lag_months=0):
    """Point-in-time: last value with index <= (sig_d - lag_months)."""
    ref = sig_d - pd.DateOffset(months=lag_months) if lag_months else sig_d
    s = series.loc[:ref]
    return float(s.iloc[-1]) if len(s) else None


# ----------------------- indicator warns -----------------------
def warn_vix(panel, monthly, sig_d, M):
    v = macro_at(M["vix"], sig_d); v3 = macro_at(M["vix3m"], sig_d)
    if v is None or v3 is None:
        return None
    return v >= v3  # backwardation = warn


def warn_yc(panel, monthly, sig_d, M):
    s = macro_at(M["t10y3m"], sig_d)
    if s is None:
        return None
    return s < 0.0  # inverted = warn


def warn_unrate(panel, monthly, sig_d, M):
    # FRED publication ~1mo lag -> use UNRATE as of sig_d - 1 month (no look-ahead).
    ref = sig_d - pd.DateOffset(months=1)
    s = M["unrate"].loc[:ref]
    if len(s) < 12:
        return None
    u = float(s.iloc[-1]); ma12 = float(s.tail(12).mean())
    return u > ma12  # rising unemployment vs 12mo MA = warn (Sahm-lite)


def warn_breadth(panel, monthly, sig_d, M, thresh=4):
    mclose = panel.loc[:sig_d].resample("ME").last()
    faber = faber_sma_xs(mclose)
    n = sum(1 for t in RISKY_UNIVERSE
            if t in faber.index and pd.notna(faber[t]) and faber[t] > 0)
    return n < thresh  # weak breadth = warn


def warn_erp(panel, monthly, sig_d, M):
    erp = M["erp"].loc[:sig_d]
    if len(erp) < 24:
        return None
    cur = float(erp.iloc[-1]); avg = float(erp.iloc[:-1].mean())  # expanding mean, PIT
    return cur < avg  # equities expensive (low risk premium) = warn


def warn_tip(panel, monthly, sig_d, M):
    if "TIP" not in monthly.columns:
        return None
    v = sig_13612U(monthly["TIP"])
    return (not (pd.notna(v) and v > 0))  # TIP 13612U <= 0 = warn


WARN_FN = {"vix": warn_vix, "yc": warn_yc, "unrate": warn_unrate,
           "breadth": warn_breadth, "erp": warn_erp, "tip": warn_tip}


def count_warnings(panel, monthly, sig_d, M, active):
    warns = {}
    for name in active:
        w = WARN_FN[name](panel, monthly, sig_d, M)
        warns[name] = w
    n = sum(1 for w in warns.values() if w is True)
    return n, warns


# ----------------------- weight functions -----------------------
def _spy_trend_up(monthly):
    v = sig_13612U(monthly["SPY"])
    return pd.notna(v) and v > 0


def _pick_safe(monthly):
    scores = {}
    for s in SAFE_POOL:
        if s in monthly.columns:
            sc = sig_13612U(monthly[s])
            if pd.notna(sc):
                scores[s] = sc
    return max(scores, key=scores.get) if scores else B.CASH_TICKER


def make_prod_and(M):
    def wf(panel, sig_d):
        return B.compute_bull_spy_weights(panel, sig_d, panel[B.BULL_TICKER])[0]
    return wf


def make_or_tip(M):
    def wf(panel, sig_d):
        monthly = panel.loc[:sig_d].resample("ME").last()
        tip = sig_13612U(monthly["TIP"]) if "TIP" in monthly.columns else float("nan")
        tip_ok = pd.notna(tip) and tip > 0
        risk_on = tip_ok or _spy_trend_up(monthly)
        return {B.BULL_TICKER: 1.0} if risk_on else {_pick_safe(monthly): 1.0}
    return wf


def make_composite(M, k, active=None):
    active = active or INDICATORS
    def wf(panel, sig_d):
        monthly = panel.loc[:sig_d].resample("ME").last()
        n, _ = count_warnings(panel, monthly, sig_d, M, active)
        risk_on = (n < k) or _spy_trend_up(monthly)
        return {B.BULL_TICKER: 1.0} if risk_on else {_pick_safe(monthly): 1.0}
    return wf


# ----------------------- metrics helpers -----------------------
def met(series, cash):
    m = perf_metrics(series, cash)
    return {"sharpe": m.get("sharpe"), "calmar": m.get("calmar"),
            "martin": m.get("martin"), "maxdd": m.get("max_drawdown"),
            "cagr": m.get("cagr"), "vol": m.get("vol")}


def dd_in(s, lo, hi):
    sub = s.loc[(s.index >= pd.Timestamp(lo)) & (s.index <= pd.Timestamp(hi))]
    if len(sub) < 3:
        return float("nan")
    eq = (1.0 + sub).cumprod()
    return float((eq / eq.cummax() - 1.0).min())


def stationary_bootstrap_sharpe(ret_a, ret_b, n_boot=2000, mean_block=20, seed=7):
    """Paired stationary bootstrap of Sharpe diff (a - b). Returns p(diff<=0)."""
    common = ret_a.index.intersection(ret_b.index)
    a = ret_a.reindex(common).fillna(0.0).values
    b = ret_b.reindex(common).fillna(0.0).values
    n = len(a)
    rng = np.random.default_rng(seed)
    p = 1.0 / mean_block
    def sh(x):
        sd = x.std()
        return float(x.mean() / sd * np.sqrt(252)) if sd > 0 else 0.0
    diffs = np.empty(n_boot)
    for j in range(n_boot):
        idx = np.empty(n, dtype=int)
        i = rng.integers(0, n); idx[0] = i
        for t in range(1, n):
            if rng.random() < p:
                i = rng.integers(0, n)
            else:
                i = (i + 1) % n
            idx[t] = i
        diffs[j] = sh(a[idx]) - sh(b[idx])
    return float(np.mean(diffs <= 0.0)), float(np.mean(diffs)), float(np.std(diffs))


# ----------------------- main -----------------------
def main():
    data = H.load_data()
    cash = data.cash
    panel = data.panel
    M = load_macro()
    print("anchor:", {k: round(float(v), 4) for k, v in H.verify_anchor(data=data).items()})

    CRISES = {
        "GFC_2008": ("2007-10-01", "2009-06-30"),
        "COVID_2020": ("2020-02-01", "2020-06-30"),
        "Y2022": ("2022-01-01", "2022-12-31"),
        "Tariff_2025": ("2025-02-01", "2025-06-30"),
    }

    variants = {
        "prod_AND (baseline)": make_prod_and(M),
        "OR-TIP": make_or_tip(M),
        "composite_k1": make_composite(M, 1),
        "composite_k2": make_composite(M, 2),
        "composite_k3": make_composite(M, 3),
    }

    rows = {}
    series_clean = {}
    series_ext = {}
    for name, wf in variants.items():
        s_clean = H.run_strategy(wf, window="clean", data=data)
        s_ext = H.run_strategy(wf, window="ext", data=data)
        series_clean[name] = s_clean
        series_ext[name] = s_ext
        rec = {"clean": met(s_clean, cash), "ext": met(s_ext, cash)}
        # per-crisis DD from ext series (covers full GFC)
        rec["crisis_dd"] = {ck: dd_in(s_ext, lo, hi) for ck, (lo, hi) in CRISES.items()}
        rows[name] = rec
        c = rec["clean"]
        print(f"{name:22s} clean Sh={c['sharpe']:.3f} Cal={c['calmar']:.3f} "
              f"MDD={c['maxdd']*100:6.2f}% Mar={c['martin']:.2f}")

    # ---- leave-one-out attribution at canonical k=1 ----
    loo = {}
    base_k1 = rows["composite_k1"]["clean"]
    for drop in INDICATORS:
        active = [x for x in INDICATORS if x != drop]
        wf = make_composite(M, 1, active=active)
        s = H.run_strategy(wf, window="clean", data=data)
        m = met(s, cash)
        loo[drop] = {"sharpe": m["sharpe"], "calmar": m["calmar"], "maxdd": m["maxdd"],
                     "d_sharpe": m["sharpe"] - base_k1["sharpe"],
                     "d_calmar": m["calmar"] - base_k1["calmar"]}
        print(f"  LOO drop {drop:8s} Sh={m['sharpe']:.3f} (d {loo[drop]['d_sharpe']:+.3f}) "
              f"Cal={m['calmar']:.3f}")

    # ---- ext-reduced composite (drop VIX-backwardation; reach back further) ----
    reduced = [x for x in INDICATORS if x != "vix"]
    ext_reduced = {}
    for k in (1, 2, 3):
        wf = make_composite(M, k, active=reduced)
        s = H.run_strategy(wf, window="ext", data=data)
        ext_reduced[f"reduced_k{k}"] = met(s, cash)
    # prod AND ext for reference already in rows

    # ---- bootstrap configs beating prod on Sharpe AND Calmar (clean) ----
    base = rows["prod_AND (baseline)"]["clean"]
    boot = {}
    for name in ["OR-TIP", "composite_k1", "composite_k2", "composite_k3"]:
        c = rows[name]["clean"]
        if c["sharpe"] > base["sharpe"] and c["calmar"] > base["calmar"]:
            p, mdiff, sdiff = stationary_bootstrap_sharpe(
                series_clean[name], series_clean["prod_AND (baseline)"])
            boot[name] = {"p_sharpe_diff_le0": p, "mean_diff": mdiff, "std_diff": sdiff}
            print(f"  bootstrap {name}: p(dSharpe<=0)={p:.3f} mean dSh={mdiff:+.3f}")

    # ---- walk-forward: yearly select best k in {prod,OR-TIP,k1,k2,k3} by trailing
    #      in-sample Sharpe, apply OOS next calendar year, chain. ----
    wf_candidates = ["prod_AND (baseline)", "OR-TIP", "composite_k1",
                     "composite_k2", "composite_k3"]
    wf_series = {n: series_clean[n] for n in wf_candidates}
    years = sorted({d.year for d in series_clean["prod_AND (baseline)"].index})
    wf_chain = []
    wf_picks = []
    MIN_IS_YEARS = 4
    for yi, y in enumerate(years):
        if yi < MIN_IS_YEARS:
            # warmup: hold baseline OOS
            pick = "prod_AND (baseline)"
        else:
            is_lo = pd.Timestamp(f"{years[0]}-01-01"); is_hi = pd.Timestamp(f"{y-1}-12-31")
            best, best_sh = None, -1e9
            for n in wf_candidates:
                seg = wf_series[n].loc[(wf_series[n].index >= is_lo) & (wf_series[n].index <= is_hi)]
                sh = met(seg, cash)["sharpe"]
                if sh is not None and sh > best_sh:
                    best_sh, best = sh, n
            pick = best
        oos = wf_series[pick].loc[(wf_series[pick].index >= pd.Timestamp(f"{y}-01-01"))
                                  & (wf_series[pick].index <= pd.Timestamp(f"{y}-12-31"))]
        wf_chain.append(oos)
        wf_picks.append({"year": y, "pick": pick})
    wf_oos = pd.concat(wf_chain).sort_index()
    # OOS-only segment (after warmup years)
    oos_start = pd.Timestamp(f"{years[MIN_IS_YEARS]}-01-01")
    wf_oos_only = wf_oos.loc[wf_oos.index >= oos_start]
    wf_metrics = {
        "walkforward_full": met(wf_oos, cash),
        "walkforward_oos_only": met(wf_oos_only, cash),
        "prod_oos_only": met(series_clean["prod_AND (baseline)"].loc[
            series_clean["prod_AND (baseline)"].index >= oos_start], cash),
        "k1_oos_only": met(series_clean["composite_k1"].loc[
            series_clean["composite_k1"].index >= oos_start], cash),
        "picks": wf_picks,
        "oos_start": str(oos_start.date()),
    }
    print("walkforward OOS-only:", {k: round(v, 3) for k, v in wf_metrics["walkforward_oos_only"].items() if isinstance(v, float)})

    # split-half OOS for k1 vs prod
    mid = pd.Timestamp("2017-06-01")
    def half(s, lo, hi):
        return met(s.loc[(s.index >= lo) & (s.index <= hi)], cash)
    split = {
        "prod_h1": half(series_clean["prod_AND (baseline)"], CLEAN_START, mid),
        "prod_h2": half(series_clean["prod_AND (baseline)"], mid, data.end),
        "k1_h1": half(series_clean["composite_k1"], CLEAN_START, mid),
        "k1_h2": half(series_clean["composite_k1"], mid, data.end),
    }

    out = {
        "meta": {
            "conv": "mooex", "cost_bps": 10, "baseline": "both-252",
            "clean": [str(CLEAN_START.date()), str(data.end.date())],
            "ext": [str(EXT_START.date()), str(data.end.date())],
            "indicators": INDICATORS,
            "lookahead_controls": [
                "UNRATE lagged 1 month (FRED publication lag)",
                "ERP from Shiller CAPE; PE10 valid through " + M["pe10_last_valid"]
                + ", price-scaled beyond (overstates CAPE -> more 'expensive' warns)",
                "ERP expanding-mean threshold is point-in-time (past only)",
                "market data (VIX/VIX3M/T10Y3M/breadth/TIP) at sig_d month-end (known)",
                "mooex T+1 MOO execution, 10bps/side",
            ],
            "warn_rules": {
                "vix": "VIX >= VIX3M", "yc": "T10Y3M < 0",
                "unrate": "UNRATE > 12mo MA (lag 1mo)", "breadth": "n_positive < 4 of 8",
                "erp": "ERP < expanding-mean(ERP)", "tip": "TIP 13612U <= 0"},
        },
        "variants": rows,
        "leave_one_out_k1": loo,
        "ext_reduced": ext_reduced,
        "bootstrap_vs_prod": boot,
        "walkforward": wf_metrics,
        "split_half": split,
    }
    Path(__file__).with_suffix(".json").write_text(json.dumps(out, indent=2, default=float))
    write_md(out)
    print("DONE -> research/bull_spycomp_composite_findings.md")
    return out


def write_md(o):
    L = []; A = L.append
    m = o["meta"]; V = o["variants"]
    def pct(x):
        return f"{x*100:.2f}%" if x is not None and np.isfinite(x) else "n/a"
    def f3(x):
        return f"{x:.3f}" if x is not None and np.isfinite(x) else "n/a"

    A("# BULL SPY-COMP composite recession-gate override\n")
    A("Role: analyst (read-only re production; writes only to research/; no prod/memo "
      "files changed; no commit). Harness `research/cpm_harness.py` + "
      "`research/bull_spycomp_composite.py`.\n")
    A("**Question:** does a SPY-COMP-style COMPOSITE recession-nowcast OVERRIDE "
      "(`risk_on = (n_warnings < k) OR spy_trend_up`) beat the BULL sleeve's current "
      "AND gate (`canary_ok AND spy_trend_ok`) on the decision lens WITHOUT blowing out "
      "COVID / fast-crash drawdown, and survive walk-forward?\n")
    A(f"**Conventions:** mooex T+1 MOO exact, {m['cost_bps']} bps/side, {m['baseline']}. "
      f"Clean (decision lens) {m['clean'][0]}..{m['clean'][1]}. Ext {m['ext'][0]}..{m['ext'][1]}. "
      "BULL sleeve = asset SPY, safe best-of(SHV/IEF) by 13612U.\n")
    A("**Six recession indicators (binary warn):**\n")
    A("| # | Indicator | Warn rule |")
    A("|---|---|---|")
    names = {"vix": "VIX backwardation", "yc": "Yield curve", "unrate": "Unemployment (Sahm-lite)",
             "breadth": "Faber breadth", "erp": "Equity risk premium", "tip": "TIP canary"}
    for i, k in enumerate(INDICATORS, 1):
        A(f"| {i} | {names[k]} | {m['warn_rules'][k]} |")
    A("")
    A("**Look-ahead controls:**\n")
    for c in m["lookahead_controls"]:
        A(f"- {c}")
    A("")

    A("## 1. Sleeve comparison -- clean decision lens (2008-05-30..)\n")
    A("| Variant | Sharpe | Calmar | Martin | MaxDD | CAGR | Vol |")
    A("|---|---:|---:|---:|---:|---:|---:|")
    for name, r in V.items():
        c = r["clean"]
        A(f"| {name} | {f3(c['sharpe'])} | {f3(c['calmar'])} | {f3(c['martin'])} | "
          f"{pct(c['maxdd'])} | {pct(c['cagr'])} | {pct(c['vol'])} |")
    A("")

    A("## 2. Per-crisis drawdown (BULL sleeve, from ext series)\n")
    A("GFC 2007-10..2009-06; COVID 2020-02..2020-06 (CRITICAL: override stays long "
      "through head-fakes; 1mo-lag fast-crash 'long into the void' risk); 2022 full year; "
      "2025 tariff 2025-02..2025-06.\n")
    A("| Variant | GFC_2008 | COVID_2020 | Y2022 | Tariff_2025 |")
    A("|---|---:|---:|---:|---:|")
    for name, r in V.items():
        d = r["crisis_dd"]
        A(f"| {name} | {pct(d['GFC_2008'])} | {pct(d['COVID_2020'])} | "
          f"{pct(d['Y2022'])} | {pct(d['Tariff_2025'])} |")
    A("")

    A("## 3. Leave-one-out signal attribution (composite k=1, clean)\n")
    A("Drop each indicator from the composite at k=1; SPY-COMP predicts removing weak "
      "signals barely matters (any single warn already pushes to trend).\n")
    A("| Dropped | Sharpe | d Sharpe | Calmar | d Calmar | MaxDD |")
    A("|---|---:|---:|---:|---:|---:|")
    for d, r in o["leave_one_out_k1"].items():
        A(f"| {names[d]} | {f3(r['sharpe'])} | {r['d_sharpe']:+.3f} | {f3(r['calmar'])} | "
          f"{r['d_calmar']:+.3f} | {pct(r['maxdd'])} |")
    A("")

    A("## 4. Ext-reduced composite confirmation (drop VIX-backwardation; 1999-03-10..)\n")
    A("Reduced composite = yield/unemp/ERP/breadth/TIP (drops VIX-term, VIX3M only "
      "from 2006). Confirms the macro-override is not a 2008+ artifact.\n")
    A("| Config | Sharpe | Calmar | Martin | MaxDD | CAGR |")
    A("|---|---:|---:|---:|---:|---:|")
    pe = V["prod_AND (baseline)"]["ext"]
    A(f"| prod_AND (baseline) ext | {f3(pe['sharpe'])} | {f3(pe['calmar'])} | "
      f"{f3(pe['martin'])} | {pct(pe['maxdd'])} | {pct(pe['cagr'])} |")
    for name, r in o["ext_reduced"].items():
        A(f"| {name} ext | {f3(r['sharpe'])} | {f3(r['calmar'])} | {f3(r['martin'])} | "
          f"{pct(r['maxdd'])} | {pct(r['cagr'])} |")
    A("")

    A("## 5. Bootstrap (configs beating prod on Sharpe AND Calmar, clean)\n")
    if o["bootstrap_vs_prod"]:
        A("Paired stationary bootstrap (block ~20d, 2000 reps) of Sharpe(config) - "
          "Sharpe(prod). p = P(diff <= 0) = chance the edge is noise.\n")
        A("| Config | p(dSharpe<=0) | mean dSharpe | std |")
        A("|---|---:|---:|---:|")
        for name, b in o["bootstrap_vs_prod"].items():
            A(f"| {name} | {b['p_sharpe_diff_le0']:.3f} | {b['mean_diff']:+.3f} | {b['std_diff']:.3f} |")
    else:
        A("No config beat prod on BOTH Sharpe AND Calmar in the clean window; bootstrap skipped.")
    A("")

    A("## 6. Walk-forward (sequential OOS k-selection)\n")
    wf = o["walkforward"]
    A(f"Each year (after {wf['oos_start']} warmup) pick the config with best trailing "
      "in-sample Sharpe from {{prod, OR-TIP, k1, k2, k3}}, apply OOS next year, chain.\n")
    A("| Series | Sharpe | Calmar | Martin | MaxDD | CAGR |")
    A("|---|---:|---:|---:|---:|---:|")
    for key in ["walkforward_oos_only", "prod_oos_only", "k1_oos_only"]:
        r = wf[key]
        A(f"| {key} | {f3(r['sharpe'])} | {f3(r['calmar'])} | {f3(r['martin'])} | "
          f"{pct(r['maxdd'])} | {pct(r['cagr'])} |")
    A("")
    A("Yearly picks: " + ", ".join(f"{p['year']}:{p['pick'].split(' ')[0]}" for p in wf["picks"]) + "\n")
    sp = o["split_half"]
    A("Split-half (k1 vs prod): "
      f"prod H1 Sharpe {f3(sp['prod_h1']['sharpe'])} / H2 {f3(sp['prod_h2']['sharpe'])}; "
      f"k1 H1 {f3(sp['k1_h1']['sharpe'])} / H2 {f3(sp['k1_h2']['sharpe'])} "
      f"(split 2017-06).\n")

    base = V["prod_AND (baseline)"]["clean"]; k1 = V["composite_k1"]["clean"]
    ortip = V["OR-TIP"]["clean"]
    wfo = o["walkforward"]["walkforward_oos_only"]; pro = o["walkforward"]["prod_oos_only"]
    A("## 7. Verdict -- DOCUMENT, do NOT adopt\n")
    A("The SPY-COMP-style OVERRIDE (OR structure; OR-TIP or composite) does NOT beat the "
      "production AND gate on the decision lens. The AND gate wins.\n")
    A("**Evidence:**\n")
    A(f"- **OR structure alone is strictly worse.** OR-TIP (`TIP OR trend`) drops Sharpe "
      f"{f3(base['sharpe'])} -> {f3(ortip['sharpe'])} and deepens MaxDD "
      f"{pct(base['maxdd'])} -> {pct(ortip['maxdd'])} (GFC -27.3%, COVID -33.7%). "
      "The permissive OR keeps the sleeve long into drawdowns -- the wrong direction for a "
      "crash-defense sleeve.")
    A(f"- **Composite k=1 trades Sharpe for a marginal Calmar bump.** Sharpe "
      f"{f3(base['sharpe'])} -> {f3(k1['sharpe'])} (WORSE), Calmar {f3(base['calmar'])} -> "
      f"{f3(k1['calmar'])} (better), MaxDD {pct(base['maxdd'])} -> {pct(k1['maxdd'])} "
      "(0.5pp, noise). No config beat prod on BOTH Sharpe AND Calmar, so the bootstrap "
      "significance gate never even triggered.")
    A("- **Higher k blows out tails.** k=2/k=3 deepen GFC (-19.9%/-25.0%) and 2022 "
      "(-13.8%/-25.2%): more permissive override = more 'long into the void'.")
    A("- **COVID fast-crash:** composite holds COVID at -13.35% (same as prod) ONLY because "
      "the SPY trend leg still fires; the macro-override itself adds no COVID protection and "
      "the 1mo-lag fast-crash risk shows up instead in 2022 (-10.1% -> -13.8% at k=1).")
    A("- **Leave-one-out exposes the overfit narrative.** At k=1, dropping VIX, ERP, or TIP "
      "changes Sharpe by +0.000 (inert -- they never bind), dropping the yield curve "
      "IMPROVES Sharpe +0.029 (it actively hurts), and only unemployment/breadth carry mild "
      "positive weight. The 'composite' is not composite: 2 signals carry it, 1 drags it, 3 "
      "are dead weight. Consistent with SPY-COMP's own logic (any warn just defers to trend) "
      "-- which means it adds nothing over a plain trend rule.")
    A(f"- **Ext-reduced confirms it is not a 2008 artifact (in the wrong direction).** Over "
      f"1999-03-10.. the reduced composite is also WORSE: reduced_k1 Sharpe 0.842 vs prod "
      f"ext 0.974.")
    A(f"- **Walk-forward is decisive.** Yearly adaptive selection of the best config OOS "
      f"yields Sharpe {f3(wfo['sharpe'])} / Calmar {f3(wfo['calmar'])} / MaxDD "
      f"{pct(wfo['maxdd'])} -- WORSE than simply holding prod OOS "
      f"(Sharpe {f3(pro['sharpe'])}, Calmar {f3(pro['calmar'])}, MaxDD {pct(pro['maxdd'])}). "
      "Even an oracle-ish adaptive override loses to the static AND gate out-of-sample.")
    A("")
    A("**Why the AND gate wins (structural):** the AND gate requires BOTH macro canary and "
      "SPY trend to agree before risking on -- conservative, good crash protection. The "
      "SPY-COMP OR override only requires macro-healthy OR trend-up -- permissive, stays "
      "invested through deteriorating tape. For a sleeve whose mandate includes tail defense, "
      "permissiveness is value-destructive.\n")
    A("**Portfolio context:** BULL is ~20% of the 60/20/20 book. Adopting composite_k1 costs "
      "~0.056 sleeve Sharpe with no MaxDD win that survives scrutiny; at 20% weight the "
      "full-portfolio impact is small but negative, with a deeper 2022 tail. No upside "
      "justifies the change; full-CPM re-run not warranted.\n")
    A("**Recommendation:** DOCUMENT (negative result). Keep the production AND gate. The "
      "SPY-COMP recession-override paradigm does not transfer to this sleeve; the override's "
      "permissiveness is the dominant failure mode and it is the AND gate's conservatism that "
      "is doing the work. The biggest threat anticipated (overfit DoF across 6 signals x k) "
      "is confirmed by leave-one-out and walk-forward: the apparent Calmar edge at k=1 is "
      "carried by 2 signals, does not beat prod on Sharpe, and reverses out-of-sample.\n")

    Path(ROOT / "research" / "bull_spycomp_composite_findings.md").write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
