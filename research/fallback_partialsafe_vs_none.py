# -*- coding: utf-8 -*-
"""Throwaway research (read-only re: production): head-to-head of the two COHERENT
low-breadth fallback rules for the CPM (Cross-asset Parity Momentum) sleeve, vs
the current INCOHERENT production hybrid (reference only).

CPM core = INVVOL-3 (select min-var 3-subset from the top-K=4 positive-trend
pool, inverse-vol weight). Everything (selection / ranker / K=4 / canary
HYG-or-TIP / timed SHV-IEF safe / T+1 MOO exact execution / 10 bps/side) is
IDENTICAL across all three variants. The ONLY difference is the handling of
months with fewer than 3 positive-trend assets (n_pos in {0,1,2}).

Variants:
  (A) TRUE PARTIAL-SAFE: risky_fraction = min(n_pos,3)/3, remainder to timed safe.
      risky block = the n_pos positives (min-var-3-subset if n_pos>3), inverse-vol.
      n_pos=1 -> 1/3 risky + 2/3 safe; n_pos=2 -> 2/3 risky (invvol-2) + 1/3 safe;
      n_pos>=3 -> 100% risky invvol-3; n_pos=0 -> 100% safe.
  (B) NO PARTIAL-SAFE: hold qualifying positives FULLY invested (inverse-vol),
      go to safe only at zero breadth.
      n_pos=1 -> 100% that asset; n_pos=2 -> invvol-2 100%; n_pos>=3 -> invvol-3 100%;
      n_pos=0 -> 100% safe.
  (HYBRID-ref) current incoherent production: n_pos=1 -> 50/50 risky+safe;
      n_pos=2 -> invvol-2 FULLY risky (100%); n_pos>=3 -> invvol-3 100%; 0 -> safe.

Verification anchor (must reproduce before trusting): HYBRID-ref CPM-solo
clean (18y) Sharpe 1.2453 / MaxDD -13.19% / Calmar 1.0824 ; ext (27y)
Sharpe 1.2249 / MaxDD -15.18% / Calmar 0.9148.

Windows: clean 2008-05-30..2026-05-22 (18y), ext 1999-03-10..2026-05-22 (27y).
Execution T+1 MOO exact ("mooex", real auto_adjust opens), 10 bps/side, post-cost.
Blend = 0.60*CPM + 0.40*BULL (BULL slow rv_60d<rv_252d gate, independent of CPM).

No production files touched. Writes research/fallback_partialsafe_vs_none_findings.md (+ json).
"""
from __future__ import annotations
import sys, json, math
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import exec_lag_moo_validation_2026_05_30 as H
from cpm_live import (
    load_panel, perf_metrics, faber_sma_xs, sig_13612U, best_safe,
    min_var_subset, inv_vol_weights,
    RISKY_UNIVERSE, SAFE_POOL, CANARY_ASSETS, DEFAULT_CASH, COST_BPS_PER_SIDE,
    TOP_K_CANDIDATES, CORR_LOOKBACK_DAYS,
)

CONV = "mooex"
CPM_W, BULL_W = 0.60, 0.40
COST = COST_BPS_PER_SIDE  # 10
CPM_UNIV = ["QQQ", "SPHQ", "EFA", "EEM", "VNQ", "GLD", "TLT", "DBC"]
SAFE = ["SHV", "IEF"]
LOOKBACK = CORR_LOOKBACK_DAYS  # 504
K = TOP_K_CANDIDATES           # 4

CLEAN_START = pd.Timestamp("2008-05-30")
EXT_START = pd.Timestamp("1999-03-10")
END = pd.Timestamp("2026-05-22")

REGIMES = {
    "Dot-com (2000-03..2002-12)": ("2000-03-01", "2002-12-31"),
    "GFC (2007-10..2009-06)":     ("2007-10-01", "2009-06-30"),
    "COVID (2020-02..2020-06)":   ("2020-02-01", "2020-06-30"),
    "2022 bear (2022-01..2022-12)": ("2022-01-01", "2022-12-31"),
}

ANCHOR = {"clean": (1.2453, -13.19, 1.0824), "ext": (1.2249, -15.18, 0.9148)}

VARIANTS = ["A", "B", "HYBRID"]
VLABEL = {"A": "(A) TRUE partial-safe", "B": "(B) no partial-safe",
          "HYBRID": "hybrid (incoherent, ref)"}


# ---------------------------------------------------------------------------
# Shared selection -> positives.  Returns (safe_ticker, positive_index_list,
# faber series, close-subset).  None positives -> ([], ...) means defensive.
# ---------------------------------------------------------------------------
def _select(close, sd):
    monthly = close.loc[:sd].resample("ME").last()
    safe = best_safe(monthly, sd, SAFE)
    # canary: HYG or TIP positive 13612U
    cs = [sig_13612U(monthly[a]) for a in CANARY_ASSETS if a in monthly.columns]
    cs = [s for s in cs if pd.notna(s)]
    if not cs or sum(1 for s in cs if s > 0) == 0:
        return safe, [], None
    present = [t for t in CPM_UNIV if t in monthly.columns]
    faber = faber_sma_xs(monthly)
    avail = [t for t in present if t in faber.index and pd.notna(faber[t])
             and (sd in close.index and pd.notna(close.loc[sd].get(t, np.nan)))]
    if not avail:
        return safe, [], None
    dr = close[avail].ffill().pct_change()
    score = {}
    for t in avail:
        v = dr[t].loc[:sd].tail(252).std() * np.sqrt(252)
        if pd.isna(v) or v < 1e-9:
            v = 1.0
        score[t] = float(faber[t]) / v
    ranked = pd.Series(score).sort_values(ascending=False)
    kk = max(2, min(K, len(ranked)))
    top = ranked.iloc[:kk]
    positive = [t for t in top.index if faber.get(t, -np.inf) > 0]
    return safe, positive, faber


def cpm_wf(close, sd, variant):
    """Weight fn. Selection identical; only n_pos<3 handling differs by variant."""
    safe, positive, _ = _select(close, sd)
    n = len(positive)
    if n == 0:
        return {safe: 1.0}
    csub = close.loc[:sd]

    # n_pos >= 3 : identical across all variants -> 100% risky invvol-3 of min-var-3 subset
    if n >= 3:
        pick = min_var_subset(csub, positive, LOOKBACK, 3)
        if pick is None:
            pick = positive
        return inv_vol_weights(csub, pick, LOOKBACK)

    # n_pos in {1,2} : the differentiator
    if variant == "A":
        risky_fraction = n / 3.0
        rw = inv_vol_weights(csub, positive, LOOKBACK)
        out = {t: w * risky_fraction for t, w in rw.items()}
        out[safe] = out.get(safe, 0.0) + (1.0 - risky_fraction)
        return out
    if variant == "B":
        return inv_vol_weights(csub, positive, LOOKBACK)
    # HYBRID
    if n == 1:
        return {positive[0]: 0.5, safe: 0.5}
    # n == 2 -> invvol-2 fully risky
    return inv_vol_weights(csub, positive, LOOKBACK)


# ---------------------------------------------------------------------------
def met(s, cash):
    m = perf_metrics(s, cash)
    return {"sharpe": m.get("sharpe"), "cagr": m.get("cagr"), "vol": m.get("vol"),
            "maxdd": m.get("max_drawdown"), "calmar": m.get("calmar")}


def win(s, start, end):
    return s.loc[(s.index >= start) & (s.index <= end)]


def maxdd_ret(s):
    eq = (1.0 + s).cumprod()
    rm = eq.cummax()
    mdd = float((eq / rm - 1.0).min()) if len(eq) else float("nan")
    tot = float(eq.iloc[-1] - 1.0) if len(eq) else float("nan")
    return mdd, tot


def run_cpm(close, daily, intraday, overnight, variant, cost=COST):
    wf = lambda sd: cpm_wf(close, sd, variant)
    s, _ = H._segment_returns_conv(close, daily, wf, EXT_START, END, CONV,
                                   cost, intraday, overnight)
    return s


# --- per-month breadth / risky-exposure analysis ---------------------------
def sig_dates(close, start, end):
    mi = (pd.DataFrame({"x": 1}, index=close.index)
          .groupby(pd.Grouper(freq="ME")).tail(1))
    return mi.index[(mi.index >= start) & (mi.index <= end)].tolist()


def risky_exposure(w):
    return sum(v for k, v in w.items() if k not in SAFE)


def breadth_table(close, start, end):
    """Per-rebal n_pos bin + risky exposure under A and B."""
    rows = []
    for sd in sig_dates(close, start, end):
        safe, positive, _ = _select(close, sd)
        n = len(positive)
        wA = cpm_wf(close, sd, "A")
        wB = cpm_wf(close, sd, "B")
        rows.append({"sd": sd, "n_pos": n, "rA": risky_exposure(wA),
                     "rB": risky_exposure(wB)})
    return rows


# --- paired block bootstrap (same resample applied to A and B) -------------
def _sharpe(a):
    v = a.std(ddof=0) * np.sqrt(252)
    return float(a.mean() * 252 / v) if v > 0 else np.nan


def _maxdd(a):
    eq = np.cumprod(1.0 + a)
    rm = np.maximum.accumulate(eq)
    return float((eq / rm - 1.0).min())


def _cagr(a, idx):
    eq = np.cumprod(1.0 + a)
    yrs = (idx[-1] - idx[0]).days / 365.25
    return float(eq[-1] ** (1 / yrs) - 1.0) if yrs > 0 else np.nan


def _calmar(a, idx):
    md = _maxdd(a)
    return float(_cagr(a, idx) / abs(md)) if md < 0 else np.nan


def paired_bootstrap(sA, sB, n_iter=2000, block=21, seed=42):
    """Stationary block bootstrap on the COMMON index; same block draws applied
    to both A and B so the difference is paired. Returns dist of (A-B)."""
    common = sA.index.intersection(sB.index)
    a = sA.reindex(common).fillna(0.0).values
    b = sB.reindex(common).fillna(0.0).values
    idx = common
    n = len(a)
    rng = np.random.default_rng(seed)
    nb = (n // block) + 1
    diffs = {"sharpe": [], "maxdd": [], "calmar": [], "cagr": []}
    for _ in range(n_iter):
        starts = rng.integers(0, n, size=nb)
        sel = []
        for st in starts:
            e = st + block
            if e <= n:
                sel.append(np.arange(st, e))
            else:
                sel.append(np.concatenate([np.arange(st, n), np.arange(0, e - n)]))
        order = np.concatenate(sel)[:n]
        aa, bb = a[order], b[order]
        bidx = idx  # length preserved; use real spacing for annualization
        diffs["sharpe"].append(_sharpe(aa) - _sharpe(bb))
        diffs["maxdd"].append(_maxdd(aa) - _maxdd(bb))
        diffs["calmar"].append(_calmar(aa, bidx) - _calmar(bb, bidx))
        diffs["cagr"].append(_cagr(aa, bidx) - _cagr(bb, bidx))
    out = {}
    for k, v in diffs.items():
        arr = np.array(v, dtype=float)
        arr = arr[np.isfinite(arr)]
        p_le0 = float((arr <= 0).mean())
        out[k] = {"mean": float(arr.mean()), "p2.5": float(np.percentile(arr, 2.5)),
                  "p50": float(np.percentile(arr, 50)), "p97.5": float(np.percentile(arr, 97.5)),
                  "frac_A_minus_B_le_0": p_le0,
                  "frac_A_minus_B_gt_0": 1.0 - p_le0}
    return out


def main():
    panel = load_panel(start=EXT_START, end=END)
    end = min(END, panel.index[-1])
    cash = panel["SHV"].ffill().pct_change().dropna()
    od, cy = H.load_open_close()
    intraday = (cy / od - 1.0).reindex(panel.index)
    overnight = (od / cy.shift(1) - 1.0).reindex(panel.index)

    cols = sorted(set(RISKY_UNIVERSE + SAFE_POOL + CANARY_ASSETS + [DEFAULT_CASH]) & set(panel.columns))
    close = panel[cols]
    daily = close.ffill().pct_change()

    # base sleeves per variant
    cpm = {v: run_cpm(close, daily, intraday, overnight, v) for v in VARIANTS}
    bull, _ = H.bull_sleeve_conv(panel, intraday, overnight, EXT_START, end, CONV, H.GATE_RV60)
    blend = {}
    for v in VARIANTS:
        common = cpm[v].index.intersection(bull.index)
        blend[v] = CPM_W * cpm[v].reindex(common) + BULL_W * bull.reindex(common)

    out = {"meta": {"conv": CONV, "cost_bps": COST, "lookback": LOOKBACK, "K": K,
                    "weighting": "INVVOL-3", "blend": "0.60*CPM + 0.40*BULL(rv60 gate)",
                    "clean_start": str(CLEAN_START.date()), "ext_start": str(EXT_START.date()),
                    "end": str(end.date())}}

    # ----- ANCHOR CHECK (hybrid-ref) -----
    print("=== ANCHOR CHECK (HYBRID-ref CPM-solo) ===")
    anc = {}
    for wl, st in [("clean", CLEAN_START), ("ext", EXT_START)]:
        m = met(win(cpm["HYBRID"], st, end), cash)
        exp = ANCHOR[wl]
        ok = (abs(m["sharpe"] - exp[0]) < 5e-4 and abs(m["maxdd"] * 100 - exp[1]) < 0.02
              and abs(m["calmar"] - exp[2]) < 5e-4)
        anc[wl] = {"sharpe": m["sharpe"], "maxdd": m["maxdd"], "calmar": m["calmar"],
                   "expect": exp, "ok": ok}
        print(f"  {wl}: Sharpe={m['sharpe']:.4f} MaxDD={m['maxdd']*100:.2f}% "
              f"Calmar={m['calmar']:.4f} expect {exp} -> {'OK' if ok else 'MISMATCH'}")
    out["anchor"] = anc
    if not all(anc[wl]["ok"] for wl in anc):
        print("ANCHOR MISMATCH -- aborting.")
        sys.exit(1)

    # ----- ITEM 1: HEADLINE (solo + blend, clean + ext) -----
    headline = {"cpm": {}, "blend": {}}
    for v in VARIANTS:
        headline["cpm"][v] = {wl: met(win(cpm[v], st, end), cash)
                              for wl, st in [("clean", CLEAN_START), ("ext", EXT_START)]}
        headline["blend"][v] = {wl: met(win(blend[v], st, end), cash)
                                for wl, st in [("clean", CLEAN_START), ("ext", EXT_START)]}
    out["headline"] = headline

    # ----- ITEM 2: CRISIS MaxDD (solo + blend) -----
    crisis = {}
    for rname, (rs, re) in REGIMES.items():
        rs_, re_ = pd.Timestamp(rs), pd.Timestamp(re)
        crisis[rname] = {"cpm": {}, "blend": {}}
        for v in VARIANTS:
            cp = win(cpm[v], rs_, re_); bl = win(blend[v], rs_, re_)
            if len(cp) > 1:
                mdd, tot = maxdd_ret(cp); crisis[rname]["cpm"][v] = {"maxdd": mdd, "ret": tot}
            if len(bl) > 1:
                mdd, tot = maxdd_ret(bl); crisis[rname]["blend"][v] = {"maxdd": mdd, "ret": tot}
    out["crisis"] = crisis

    # ----- ITEM 3: LOW-BREADTH MONTH BEHAVIOR -----
    breadth = {}
    for wl, st in [("clean", CLEAN_START), ("ext", EXT_START)]:
        rows = breadth_table(close, st, end)
        bins = {0: [], 1: [], 2: [], "3+": []}
        for r in rows:
            key = r["n_pos"] if r["n_pos"] in (0, 1, 2) else "3+"
            bins[key].append(r)
        binsum = {}
        for k, rs in bins.items():
            if not rs:
                binsum[k] = {"n_months": 0}
                continue
            binsum[k] = {"n_months": len(rs),
                         "avg_riskyA": float(np.mean([r["rA"] for r in rs])),
                         "avg_riskyB": float(np.mean([r["rB"] for r in rs]))}
        # low-breadth months = n_pos in {1,2} (where A and B differ; 0 is identical)
        lb_sds = set(r["sd"] for r in rows if r["n_pos"] in (1, 2))
        # daily returns restricted to the APPLIED period of those rebal months.
        # Use month-of: returns in calendar month following each low-breadth sig.
        masks = pd.Series(False, index=cpm["A"].index)
        sdl = sorted(set(r["sd"] for r in rows))
        for i, r in enumerate(rows):
            if r["n_pos"] not in (1, 2):
                continue
            sd = r["sd"]
            fut = close.index[close.index > sd]
            if len(fut) == 0:
                continue
            af = fut[0]
            if i + 1 < len(rows):
                nf = close.index[close.index > rows[i + 1]["sd"]]
                ea = nf[0] if len(nf) else end
            else:
                ea = end
            masks.loc[(masks.index >= af) & (masks.index < ea)] = True
        lb_stats = {}
        for v in VARIANTS:
            s = win(cpm[v], st, end)
            mm = masks.reindex(s.index).fillna(False)
            sub = s[mm.values]
            if len(sub) > 1:
                lb_stats[v] = {"n_days": int(len(sub)),
                               "ann_ret": float(sub.mean() * 252),
                               "ann_vol": float(sub.std(ddof=0) * np.sqrt(252)),
                               "total_ret": float((1 + sub).prod() - 1),
                               "sharpe": _sharpe(sub.values)}
            else:
                lb_stats[v] = {"n_days": int(len(sub))}
        breadth[wl] = {"bins": binsum, "n_lowbreadth_months": len(lb_sds),
                       "lowbreadth_day_stats": lb_stats}
    out["breadth"] = breadth

    # ----- ITEM 4: PAIRED BOOTSTRAP A vs B (clean + ext) -----
    pboot = {}
    for wl, st in [("clean", CLEAN_START), ("ext", EXT_START)]:
        pboot[wl] = {
            "cpm": paired_bootstrap(win(cpm["A"], st, end), win(cpm["B"], st, end)),
            "blend": paired_bootstrap(win(blend["A"], st, end), win(blend["B"], st, end)),
        }
        d = pboot[wl]["cpm"]
        print(f"paired boot {wl} cpm: dSharpe mean={d['sharpe']['mean']:+.3f} "
              f"CI[{d['sharpe']['p2.5']:+.3f},{d['sharpe']['p97.5']:+.3f}] "
              f"dMaxDD mean={d['maxdd']['mean']*100:+.2f}pp")
    out["paired_bootstrap"] = pboot

    (Path(__file__).with_suffix(".json")).write_text(json.dumps(out, indent=2, default=float))
    write_md(out)
    print("\nDONE -> research/fallback_partialsafe_vs_none_findings.md")
    return out


# ---------------------------------------------------------------------------
def write_md(o):
    L = []
    A = L.append
    m = o["meta"]

    def r5(mm):
        return (f"{mm['sharpe']:.4f} | {mm['cagr']*100:.2f}% | {mm['vol']*100:.2f}% "
                f"| {mm['maxdd']*100:.2f}% | {mm['calmar']:.4f}")

    A("# CPM low-breadth fallback: TRUE partial-safe (A) vs no partial-safe (B)\n")
    A("Head-to-head of the two **coherent** low-breadth fallback rules for the CPM "
      "(Cross-asset Parity Momentum) sleeve, against the current **incoherent** production "
      "hybrid (reference only, being replaced).\n")
    A("**Identical across all three:** INVVOL-3 core (min-var 3-subset from top-K=4 "
      "positive-trend pool, inverse-vol weight), volatility-adjusted Faber ranker, K=4, "
      "HYG-or-TIP canary, timed SHV/IEF safe. The ONLY difference is months with fewer than "
      "3 positive-trend assets (n_pos in {1,2}; n_pos=0 -> 100% safe in all three).\n")
    A("**Fallback rules (n_pos = positive-trend count after K=4 screen):**\n")
    A("| n_pos | (A) TRUE partial-safe | (B) no partial-safe | hybrid (ref) |")
    A("|---|---|---|---|")
    A("| 0 | 100% safe | 100% safe | 100% safe |")
    A("| 1 | 1/3 risky + 2/3 safe | 100% the asset | 50% asset + 50% safe |")
    A("| 2 | 2/3 risky (invvol-2) + 1/3 safe | invvol-2 100% | invvol-2 100% |")
    A("| >=3 | invvol-3 100% | invvol-3 100% | invvol-3 100% |")
    A("")
    A(f"**Convention (every table):** execution T+1 MOO exact (`mooex`, real auto_adjust "
      f"opens); post-cost {m['cost_bps']} bps/side; cov lookback {m['lookback']}d; K={m['K']}; "
      f"blend = {m['blend']}. Clean window {m['clean_start']}..{m['end']} (18y); "
      f"extended {m['ext_start']}..{m['end']} (27y).\n")
    A("Source harness: `research/fallback_partialsafe_vs_none.py` (read-only; no production "
      "files touched). Selection primitives shared from `cpm_live`; only the n_pos<3 branch "
      "differs by variant.\n")

    # anchor
    a = o["anchor"]
    A("## 0. Anchor check (hybrid-ref reproduces prior CPM-solo anchor)\n")
    A("| Window | Sharpe | MaxDD | Calmar | Expected | Match |")
    A("|---|---:|---:|---:|---|---|")
    for wl in ("clean", "ext"):
        e = a[wl]["expect"]
        A(f"| {wl} | {a[wl]['sharpe']:.4f} | {a[wl]['maxdd']*100:.2f}% | {a[wl]['calmar']:.4f} "
          f"| {e[0]}/{e[1]}%/{e[2]} | {'CONFIRMED' if a[wl]['ok'] else 'MISMATCH'} |")
    A("\nHybrid-ref reproduces the prior anchor exactly; A and B are trusted relative to it.\n")

    # item 1
    h = o["headline"]
    A("## 1. Headline -- CPM-solo and 60/40 blend\n")
    for scope, title in [("cpm", "1.1 CPM-solo"), ("blend", "1.2 60/40 blend")]:
        A(f"### {title}\n")
        for wl, wt in [("clean", "Clean (18y)"), ("ext", "Extended (27y)")]:
            A(f"**{wt}:**\n")
            A("| Variant | Sharpe | CAGR | Vol | MaxDD | Calmar |")
            A("|---|---:|---:|---:|---:|---:|")
            for v in VARIANTS:
                A(f"| {VLABEL[v]} | {r5(h[scope][v][wl])} |")
            A("")

    # item 2
    c = o["crisis"]
    A("## 2. Crisis MaxDD and total return (peak-to-trough within window)\n")
    for scope, title in [("cpm", "2.1 CPM-solo"), ("blend", "2.2 60/40 blend")]:
        A(f"### {title}\n")
        A("| Crisis | A MaxDD | A ret | B MaxDD | B ret | hybrid MaxDD | hybrid ret | (A)-(B) MaxDD gap |")
        A("|---|---:|---:|---:|---:|---:|---:|---:|")
        for rn, d in c.items():
            dd = d[scope]
            def g(v, k):
                return dd.get(v, {}).get(k, float("nan"))
            gap = (g("A", "maxdd") - g("B", "maxdd")) * 100
            A(f"| {rn} | {g('A','maxdd')*100:.2f}% | {g('A','ret')*100:.2f}% "
              f"| {g('B','maxdd')*100:.2f}% | {g('B','ret')*100:.2f}% "
              f"| {g('HYBRID','maxdd')*100:.2f}% | {g('HYBRID','ret')*100:.2f}% "
              f"| {gap:+.2f}pp |")
        A("")
    A("Positive (A)-(B) MaxDD gap = A shallower (less negative) drawdown = more defensive.\n")

    # item 3
    b = o["breadth"]
    A("## 3. Low-breadth month behavior (the affected months)\n")
    for wl, wt in [("clean", "Clean (18y)"), ("ext", "Extended (27y)")]:
        bw = b[wl]
        A(f"### 3.{'1' if wl=='clean' else '2'} {wt}\n")
        A("Rebal-month breadth bins (n_pos) and average risky exposure under A vs B:\n")
        A("| n_pos bin | months | avg risky (A) | avg risky (B) |")
        A("|---|---:|---:|---:|")
        for k in (0, 1, 2, "3+"):
            bb = bw["bins"][k]
            if bb["n_months"] == 0:
                A(f"| {k} | 0 | - | - |")
            else:
                rA = bb.get("avg_riskyA"); rB = bb.get("avg_riskyB")
                rA_s = f"{rA*100:.1f}%" if rA is not None else "-"
                rB_s = f"{rB*100:.1f}%" if rB is not None else "-"
                A(f"| {k} | {bb['n_months']} | {rA_s} | {rB_s} |")
        A(f"\nLow-breadth months (n_pos in {{1,2}}, where A and B differ): "
          f"**{bw['n_lowbreadth_months']}**.\n")
        A("Daily-return stats restricted to the applied periods of those low-breadth months:\n")
        A("| Variant | days | ann return | ann vol | total return | Sharpe |")
        A("|---|---:|---:|---:|---:|---:|")
        for v in VARIANTS:
            ls = bw["lowbreadth_day_stats"][v]
            if ls.get("n_days", 0) > 1:
                A(f"| {VLABEL[v]} | {ls['n_days']} | {ls['ann_ret']*100:.2f}% | "
                  f"{ls['ann_vol']*100:.2f}% | {ls['total_ret']*100:.2f}% | {ls['sharpe']:.3f} |")
            else:
                A(f"| {VLABEL[v]} | {ls.get('n_days',0)} | - | - | - | - |")
        A("")

    # item 4
    p = o["paired_bootstrap"]
    A("## 4. Paired block bootstrap A vs B (B=2000, block=21, seed=42; A-B difference)\n")
    A("Same block draws applied to both A and B (paired). Distribution of (A minus B). "
      "frac>0 = fraction of resamples where A exceeds B; for MaxDD, (A-B)>0 means A shallower "
      "(less negative) = more defensive.\n")
    for wl, wt in [("clean", "Clean (18y)"), ("ext", "Extended (27y)")]:
        for scope, st in [("cpm", "CPM-solo"), ("blend", "60/40 blend")]:
            d = p[wl][scope]
            A(f"### {wt} -- {st}\n")
            A("| Metric (A-B) | mean | 95% CI | frac A>B |")
            A("|---|---:|---|---:|")
            for k, lab in [("sharpe", "dSharpe"), ("cagr", "dCAGR"),
                           ("maxdd", "dMaxDD"), ("calmar", "dCalmar")]:
                dd = d[k]
                if k in ("cagr", "maxdd"):
                    A(f"| {lab} | {dd['mean']*100:+.2f}pp | [{dd['p2.5']*100:+.2f}, "
                      f"{dd['p97.5']*100:+.2f}]pp | {dd['frac_A_minus_B_gt_0']*100:.1f}% |")
                else:
                    A(f"| {lab} | {dd['mean']:+.3f} | [{dd['p2.5']:+.3f}, {dd['p97.5']:+.3f}] "
                      f"| {dd['frac_A_minus_B_gt_0']*100:.1f}% |")
            A("")
    A("A difference is 'significant' if the 95% CI of (A-B) excludes 0 (equivalently frac A>B "
      "near 0% or 100%); otherwise within noise.\n")

    # verdict
    hc = o["headline"]["cpm"]; hb = o["headline"]["blend"]
    A("## 5. Verdict\n")
    _verdict(A, o)

    A("## Caveats\n")
    A("- All post-cost (10 bps/side), T+1 MOO exact with real yfinance auto_adjust opens; "
      "CPM sleeve has no equity vol gate (gate only affects BULL/blend).")
    A("- Ext 27y is partially proxy-backed for the CPM trend universe pre-2006 (close-to-close "
      "fallback on a minority of rebal days); clean 18y has full real-open coverage and is the "
      "decisive lens.")
    A("- Crisis-window MaxDD is peak-to-trough inside each window. Dot-com and GFC pre-2008 sit "
      "in the proxy-backed extended history.")
    A("- Paired bootstrap resamples the common daily index with stationary blocks (size 21), "
      "applying identical block draws to A and B so the per-resample difference is paired; "
      "annualization uses the real calendar span of the window.")
    A("- n_pos=0 months are identical across all three variants (100% safe) and are excluded "
      "from the low-breadth differential analysis (only n_pos in {1,2} differ).")

    Path(ROOT / "research" / "fallback_partialsafe_vs_none_findings.md").write_text("\n".join(L) + "\n")


def _verdict(A, o):
    hc = o["headline"]["cpm"]; hb = o["headline"]["blend"]
    pb = o["paired_bootstrap"]
    cc = hc["A"]["clean"]; cb = hc["B"]["clean"]
    ec = hc["A"]["ext"]; eb = hc["B"]["ext"]
    dboot = pb["clean"]["cpm"]
    A("Filled from the computed numbers below (clean window decisive):\n")
    A(f"- **CPM-solo clean:** A Sharpe {cc['sharpe']:.4f} / CAGR {cc['cagr']*100:.2f}% / "
      f"MaxDD {cc['maxdd']*100:.2f}% / Calmar {cc['calmar']:.4f}; "
      f"B Sharpe {cb['sharpe']:.4f} / CAGR {cb['cagr']*100:.2f}% / MaxDD {cb['maxdd']*100:.2f}% "
      f"/ Calmar {cb['calmar']:.4f}.")
    A(f"- **Paired clean CPM-solo (A-B):** dSharpe {dboot['sharpe']['mean']:+.3f} "
      f"CI[{dboot['sharpe']['p2.5']:+.3f},{dboot['sharpe']['p97.5']:+.3f}]; "
      f"dMaxDD {dboot['maxdd']['mean']*100:+.2f}pp "
      f"CI[{dboot['maxdd']['p2.5']*100:+.2f},{dboot['maxdd']['p97.5']*100:+.2f}]pp; "
      f"dCalmar {dboot['calmar']['mean']:+.3f} "
      f"CI[{dboot['calmar']['p2.5']:+.3f},{dboot['calmar']['p97.5']:+.3f}].")
    A("\n(Prose verdict appended manually after inspecting numbers.)\n")


if __name__ == "__main__":
    main()
