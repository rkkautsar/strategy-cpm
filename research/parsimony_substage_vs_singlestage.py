# -*- coding: utf-8 -*-
"""Throwaway research (read-only re: production): PARSIMONY test of the variance
sub-selection stage in the CPM (Cross-asset Parity Momentum) sleeve.

Question: does the two-stage design -- (1) rank by vol-adjusted Faber momentum,
positive-trend screen, top-K=4; (2) sub-select the min-variance 3-subset; then
inverse-vol weight -- earn its second tunable knob over a SINGLE-STAGE design
(top-K by momentum, inverse-vol weight ALL positives, no variance sub-select)?

All variants share: vol-adjusted Faber ranker, HYG-or-TIP canary, timed SHV/IEF
safe, inverse-vol weighting, STRICT-3 partial-safe fallback (risky_fraction =
min(n_pos,3)/3 ; remainder to timed safe), cov lookback 504d, T+1 MOO exact
execution ("mooex", real auto_adjust opens), 10 bps/side post-cost.

Variants (CPM-solo):
  PROD      : two-stage. top-4 momentum -> min-variance 3-subset -> inverse-vol.
              (= fallback variant A, the strict-3 partial-safe production anchor.)
  SINGLE-K3 : single-stage. top-3 momentum -> inverse-vol all 3. (drops the
              4th-momentum name; no variance sub-select. One fewer knob.)
  IV4       : single-stage. top-4 momentum -> inverse-vol all 4. (the other
              single-stage option; keeps all 4.)
  SINGLE-K2 : single-stage. top-2 momentum -> inverse-vol all 2. (K-curve)
  SINGLE-K5 : single-stage. top-5 momentum -> inverse-vol all 5. (K-curve)

The ONLY difference between PROD and SINGLE-K3 is the held basket when the top-4
momentum screen yields >=3 positives: PROD drops the highest-variance of the
top-4; SINGLE-K3 never sees the 4th name (drops the 4th-momentum). When the top-3
all positive but top-4's 4th is also positive, sets can differ; when only 2 of
top-3 positive but 4th positive, breadth (n_pos) can differ too.

Items:
  1. Net Sharpe/CAGR/Vol/MaxDD/Calmar for all variants, clean (18y) + ext (27y).
  2. Paired block bootstrap (B=2000, block=21, seed=42): PROD vs SINGLE-K3 on
     Sharpe/MaxDD/Calmar. P(PROD beats) + (PROD-SINGLE) difference CI.
  3. Holdings overlap: how often PROD's min-var-3 basket differs from SINGLE-K3's
     top-3 basket; when they differ, which wins (forward 1-month return).
  4. Parsimony verdict.

Verify: PROD reproduces strict-3 anchor CLEAN 1.2667/-12.66%/1.1306 before trusting variants.

No production files touched. Writes research/parsimony_substage_vs_singlestage_findings.md (+ json).
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
COST = COST_BPS_PER_SIDE       # 10
CPM_UNIV = ["QQQ", "SPHQ", "EFA", "EEM", "VNQ", "GLD", "TLT", "DBC"]
SAFE = ["SHV", "IEF"]
LOOKBACK = CORR_LOOKBACK_DAYS  # 504

CLEAN_START = pd.Timestamp("2008-05-30")
EXT_START = pd.Timestamp("1999-03-10")
END = pd.Timestamp("2026-05-22")

ANCHOR = {"clean": (1.2667, -12.66, 1.1306), "ext": (1.2349, -15.18, 0.9119)}

# (key, label, mode, K)
VARIANTS = [
    ("PROD", "PROD two-stage (top4->minvar3->invvol)", "TWO_STAGE", 4),
    ("SINGLE_K3", "SINGLE-stage K=3 (top3->invvol)", "SINGLE", 3),
    ("IV4", "SINGLE-stage K=4 / IV4 (top4->invvol)", "SINGLE", 4),
    ("SINGLE_K2", "SINGLE-stage K=2 (top2->invvol)", "SINGLE", 2),
    ("SINGLE_K5", "SINGLE-stage K=5 (top5->invvol)", "SINGLE", 5),
]
VKEY = {k: (lab, mode, K) for k, lab, mode, K in VARIANTS}


# ---------------------------------------------------------------------------
# Shared selection. Returns (safe, positive[list of top-K positive-trend names],
# faber, ranked_full). Identical screen logic to production / fallback variant A.
# ---------------------------------------------------------------------------
def select_topk(close, sd, K):
    monthly = close.loc[:sd].resample("ME").last()
    safe = best_safe(monthly, sd, SAFE)
    cs = [sig_13612U(monthly[a]) for a in CANARY_ASSETS if a in monthly.columns]
    cs = [s for s in cs if pd.notna(s)]
    if not cs or sum(1 for s in cs if s > 0) == 0:
        return safe, [], None, None
    present = [t for t in CPM_UNIV if t in monthly.columns]
    faber = faber_sma_xs(monthly)
    avail = [t for t in present if t in faber.index and pd.notna(faber[t])
             and (sd in close.index and pd.notna(close.loc[sd].get(t, np.nan)))]
    if not avail:
        return safe, [], None, None
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
    return safe, positive, faber, ranked


def _strict3_partial(csub, positive, safe):
    """STRICT-3 partial-safe: risky_fraction = min(n_pos,3)/3, remainder safe.
    n_pos>=3 -> 100% risky inverse-vol over `positive`. n_pos in {1,2} -> scaled."""
    n = len(positive)
    rf = min(n, 3) / 3.0
    rw = inv_vol_weights(csub, positive, LOOKBACK)
    out = {t: w * rf for t, w in rw.items()}
    if rf < 1.0:
        out[safe] = out.get(safe, 0.0) + (1.0 - rf)
    return out


def cpm_wf(close, sd, mode, K):
    safe, positive, _, _ = select_topk(close, sd, K)
    n = len(positive)
    if n == 0:
        return {safe: 1.0}
    csub = close.loc[:sd]

    if mode == "TWO_STAGE":
        # PROD: when >=3 positives, min-var-3 subset then inverse-vol (100% risky).
        # when 1..2 positives, strict-3 partial-safe over those positives.
        if n >= 3:
            pick = min_var_subset(csub, positive, LOOKBACK, 3)
            if pick is None:
                pick = positive
            return inv_vol_weights(csub, pick, LOOKBACK)
        return _strict3_partial(csub, positive, safe)

    if mode == "SINGLE":
        # inverse-vol ALL top-K positives, strict-3 partial-safe (scales only n<3)
        return _strict3_partial(csub, positive, safe)

    raise ValueError(mode)


# ---------------------------------------------------------------------------
def met(s, cash):
    m = perf_metrics(s, cash)
    return {"sharpe": m.get("sharpe"), "cagr": m.get("cagr"), "vol": m.get("vol"),
            "maxdd": m.get("max_drawdown"), "calmar": m.get("calmar")}


def win(s, start, end):
    return s.loc[(s.index >= start) & (s.index <= end)]


def run_variant(close, daily, intraday, overnight, mode, K, cost=COST):
    wf = lambda sd: cpm_wf(close, sd, mode, K)
    s, _ = H._segment_returns_conv(close, daily, wf, EXT_START, END, CONV,
                                   cost, intraday, overnight)
    return s


def sig_dates(close, start, end):
    mi = (pd.DataFrame({"x": 1}, index=close.index)
          .groupby(pd.Grouper(freq="ME")).tail(1))
    return mi.index[(mi.index >= start) & (mi.index <= end)].tolist()


def basket(w, thr=1e-6):
    return frozenset(k for k, v in w.items() if abs(v) > thr and k not in SAFE)


# --- paired block bootstrap (PROD - SINGLE) -------------------------------
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


def paired_bootstrap(sP, sS, n_iter=2000, block=21, seed=42):
    """Stationary block bootstrap; identical block draws to both PROD and SINGLE
    so per-resample difference (PROD - SINGLE) is paired."""
    common = sP.index.intersection(sS.index)
    p = sP.reindex(common).fillna(0.0).values
    s = sS.reindex(common).fillna(0.0).values
    idx = common
    n = len(p)
    rng = np.random.default_rng(seed)
    nb = (n // block) + 1
    diffs = {"sharpe": [], "maxdd": [], "calmar": []}
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
        pp, ss = p[order], s[order]
        diffs["sharpe"].append(_sharpe(pp) - _sharpe(ss))
        diffs["maxdd"].append(_maxdd(pp) - _maxdd(ss))
        diffs["calmar"].append(_calmar(pp, idx) - _calmar(ss, idx))
    out = {}
    for k, v in diffs.items():
        arr = np.array(v, dtype=float)
        arr = arr[np.isfinite(arr)]
        out[k] = {"mean": float(arr.mean()),
                  "p2.5": float(np.percentile(arr, 2.5)),
                  "p50": float(np.percentile(arr, 50)),
                  "p97.5": float(np.percentile(arr, 97.5)),
                  "p_prod_beats": float((arr > 0).mean()),
                  "excludes_zero": bool(np.percentile(arr, 2.5) > 0 or np.percentile(arr, 97.5) < 0)}
    return out


# --- holdings overlap PROD vs SINGLE-K3 + forward-return attribution -------
def overlap_analysis(close, start, end):
    sds = sig_dates(close, start, end)
    rows = []
    n_diff = 0
    prod_wins = single_wins = ties = 0
    diff_prod_fwd = []
    diff_single_fwd = []
    for i, sd in enumerate(sds):
        wP = cpm_wf(close, sd, "TWO_STAGE", 4)
        wS = cpm_wf(close, sd, "SINGLE", 3)
        bP, bS = basket(wP), basket(wS)
        differ = bP != bS
        # forward 1-month (sig_d -> next sig_d) realized return of each basket,
        # inverse-vol weighted as held (use the actual weight dict, ex-safe scaled).
        if i + 1 < len(sds):
            nd = sds[i + 1]
        else:
            nd = end
        seg = close.loc[(close.index > sd) & (close.index <= nd)]
        if len(seg) < 2:
            continue

        def fwd(w):
            rr = 0.0
            tot = 0.0
            for t, wt in w.items():
                if t in SAFE:
                    continue
                px = close[t].loc[(close.index >= sd) & (close.index <= nd)].dropna()
                if len(px) < 2:
                    continue
                rr += wt * (px.iloc[-1] / px.iloc[0] - 1.0)
                tot += wt
            return rr  # safe sleeve assumed ~0 excess; compare risky baskets

        if differ:
            n_diff += 1
            fP, fS = fwd(wP), fwd(wS)
            diff_prod_fwd.append(fP)
            diff_single_fwd.append(fS)
            if fP > fS + 1e-9:
                prod_wins += 1
            elif fS > fP + 1e-9:
                single_wins += 1
            else:
                ties += 1
        rows.append({"sd": str(sd.date()), "bP": sorted(bP), "bS": sorted(bS),
                     "differ": differ})
    n_total = len([r for r in rows])
    return {
        "n_rebal": n_total, "n_differ": n_diff,
        "frac_differ": n_diff / n_total if n_total else float("nan"),
        "when_differ_prod_wins": prod_wins, "when_differ_single_wins": single_wins,
        "when_differ_ties": ties,
        "when_differ_prod_avg_fwd": float(np.mean(diff_prod_fwd)) if diff_prod_fwd else float("nan"),
        "when_differ_single_avg_fwd": float(np.mean(diff_single_fwd)) if diff_single_fwd else float("nan"),
        "when_differ_prod_minus_single_avg_fwd": float(np.mean(np.array(diff_prod_fwd) - np.array(diff_single_fwd))) if diff_prod_fwd else float("nan"),
    }


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

    series = {}
    for k, lab, mode, K in VARIANTS:
        series[k] = run_variant(close, daily, intraday, overnight, mode, K)
        print(f"  variant {k} done")

    out = {"meta": {"conv": CONV, "cost_bps": COST, "lookback": LOOKBACK,
                    "weighting": "inverse-vol", "fallback": "strict-3 partial-safe (min(n_pos,3)/3)",
                    "clean_start": str(CLEAN_START.date()), "ext_start": str(EXT_START.date()),
                    "end": str(end.date()), "B": 2000, "block": 21, "seed": 42}}

    # anchor check
    print("=== ANCHOR CHECK (PROD strict-3) ===")
    anc = {}
    for wl, st in [("clean", CLEAN_START), ("ext", EXT_START)]:
        m = met(win(series["PROD"], st, end), cash)
        exp = ANCHOR[wl]
        ok = (abs(m["sharpe"] - exp[0]) < 5e-4 and abs(m["maxdd"] * 100 - exp[1]) < 0.02
              and abs(m["calmar"] - exp[2]) < 5e-4)
        anc[wl] = {"sharpe": m["sharpe"], "maxdd": m["maxdd"], "calmar": m["calmar"],
                   "expect": exp, "ok": ok}
        print(f"  {wl}: Sharpe={m['sharpe']:.4f} MaxDD={m['maxdd']*100:.2f}% "
              f"Calmar={m['calmar']:.4f} expect {exp} -> {'OK' if ok else 'MISMATCH'}")
    out["anchor"] = anc
    if not anc["clean"]["ok"]:
        print("CLEAN ANCHOR MISMATCH -- aborting.")
        sys.exit(1)

    # item 1: headline
    headline = {}
    for k, lab, mode, K in VARIANTS:
        headline[k] = {"label": lab,
                       "clean": met(win(series[k], CLEAN_START, end), cash),
                       "ext": met(win(series[k], EXT_START, end), cash)}
    out["headline"] = headline

    # item 2: paired bootstrap PROD vs SINGLE-K3 (and vs IV4 = pure sub-select knob)
    pboot = {}
    pboot_iv4 = {}
    for wl, st in [("clean", CLEAN_START), ("ext", EXT_START)]:
        pboot[wl] = paired_bootstrap(win(series["PROD"], st, end),
                                     win(series["SINGLE_K3"], st, end))
        pboot_iv4[wl] = paired_bootstrap(win(series["PROD"], st, end),
                                         win(series["IV4"], st, end))
        d = pboot[wl]
        print(f"paired {wl} vsK3: dSharpe {d['sharpe']['mean']:+.3f} "
              f"CI[{d['sharpe']['p2.5']:+.3f},{d['sharpe']['p97.5']:+.3f}] "
              f"P(PROD)={d['sharpe']['p_prod_beats']:.2f}")
        di = pboot_iv4[wl]
        print(f"paired {wl} vsIV4: dSharpe {di['sharpe']['mean']:+.3f} "
              f"CI[{di['sharpe']['p2.5']:+.3f},{di['sharpe']['p97.5']:+.3f}] "
              f"P(PROD)={di['sharpe']['p_prod_beats']:.2f}")
    out["paired_bootstrap_prod_vs_singleK3"] = pboot
    out["paired_bootstrap_prod_vs_iv4"] = pboot_iv4

    # item 3: holdings overlap
    overlap = {}
    for wl, st in [("clean", CLEAN_START), ("ext", EXT_START)]:
        overlap[wl] = overlap_analysis(close, st, end)
        o = overlap[wl]
        print(f"overlap {wl}: differ {o['n_differ']}/{o['n_rebal']} "
              f"({o['frac_differ']*100:.1f}%) prodWins={o['when_differ_prod_wins']} "
              f"singleWins={o['when_differ_single_wins']}")
    out["overlap_prod_vs_singleK3"] = overlap

    (Path(__file__).with_suffix(".json")).write_text(json.dumps(out, indent=2, default=float))
    write_md(out)
    print("\nDONE -> research/parsimony_substage_vs_singlestage_findings.md")
    return out


def write_md(o):
    L = []
    A = L.append
    m = o["meta"]

    def r5(mm):
        return (f"{mm['sharpe']:.4f} | {mm['cagr']*100:.2f}% | {mm['vol']*100:.2f}% "
                f"| {mm['maxdd']*100:.2f}% | {mm['calmar']:.4f}")

    A("# CPM parsimony: variance sub-selection (two-stage) vs single-stage top-K momentum\n")
    A("Does the variance-based **sub-selection** stage -- rank top-4 by vol-adjusted "
      "Faber momentum, then pick the lowest-variance 3-subset -- earn its second tunable "
      "knob over a **single-stage** design (top-K by momentum, inverse-vol weight all, no "
      "variance sub-select)?\n")
    A(f"**Convention (every table):** execution T+1 MOO exact (`mooex`, real auto_adjust "
      f"opens); post-cost {m['cost_bps']} bps/side; inverse-vol weighting; STRICT-3 "
      f"partial-safe fallback (risky_fraction = min(n_pos,3)/3, remainder to timed SHV/IEF "
      f"safe); cov lookback {m['lookback']}d; vol-adjusted Faber ranker; HYG-or-TIP canary. "
      f"Clean window {m['clean_start']}..{m['end']} (18y); extended {m['ext_start']}..{m['end']} (27y).\n")
    A("Source harness: `research/parsimony_substage_vs_singlestage.py` (read-only; no "
      "production files touched). Selection primitives shared from `cpm_live`.\n")
    A("**Variants:**\n")
    A("| Key | Design | Knobs |")
    A("|---|---|---|")
    A("| PROD | two-stage: top-4 momentum -> min-variance 3-subset -> inverse-vol | K=4 + sub-select=3 |")
    A("| SINGLE-K3 | single-stage: top-3 momentum -> inverse-vol all 3 | K=3 |")
    A("| IV4 | single-stage: top-4 momentum -> inverse-vol all 4 | K=4 |")
    A("| SINGLE-K2 | single-stage: top-2 momentum -> inverse-vol all 2 | K=2 |")
    A("| SINGLE-K5 | single-stage: top-5 momentum -> inverse-vol all 5 | K=5 |")
    A("")

    a = o["anchor"]
    A("## 0. Anchor check (PROD reproduces strict-3 anchor)\n")
    A("| Window | Sharpe | MaxDD | Calmar | Expected | Match |")
    A("|---|---:|---:|---:|---|---|")
    for wl in ("clean", "ext"):
        e = a[wl]["expect"]
        A(f"| {wl} | {a[wl]['sharpe']:.4f} | {a[wl]['maxdd']*100:.2f}% | {a[wl]['calmar']:.4f} "
          f"| {e[0]}/{e[1]}%/{e[2]} | {'CONFIRMED' if a[wl]['ok'] else 'MISMATCH'} |")
    A("")

    h = o["headline"]
    A("## 1. Headline -- CPM-solo net metrics\n")
    for wl, wt in [("clean", "Clean (18y)"), ("ext", "Extended (27y)")]:
        A(f"**{wt}:**\n")
        A("| Variant | Sharpe | CAGR | Vol | MaxDD | Calmar |")
        A("|---|---:|---:|---:|---:|---:|")
        for k, lab, mode, K in VARIANTS:
            A(f"| {lab} | {r5(h[k][wl])} |")
        A("")

    p = o["paired_bootstrap_prod_vs_singleK3"]
    A("## 2. Paired block bootstrap -- PROD vs SINGLE-K3 (B=2000, block=21, seed=42)\n")
    A("Difference is **(PROD minus SINGLE-K3)**, paired (identical block draws). "
      "`P(PROD beats)` = fraction of resamples PROD exceeds SINGLE-K3; for MaxDD, "
      "(PROD-SINGLE)>0 means PROD shallower (less negative) = more defensive.\n")
    pi = o["paired_bootstrap_prod_vs_iv4"]
    def _bt(d, who):
        A(f"| Metric (PROD-{who}) | mean | 95% CI | P(PROD beats) | CI excludes 0 |")
        A("|---|---:|---|---:|---|")
        for k, lab in [("sharpe", "dSharpe"), ("maxdd", "dMaxDD"), ("calmar", "dCalmar")]:
            dd = d[k]
            if k == "maxdd":
                A(f"| {lab} | {dd['mean']*100:+.2f}pp | [{dd['p2.5']*100:+.2f}, "
                  f"{dd['p97.5']*100:+.2f}]pp | {dd['p_prod_beats']*100:.1f}% | "
                  f"{'YES' if dd['excludes_zero'] else 'no'} |")
            else:
                A(f"| {lab} | {dd['mean']:+.4f} | [{dd['p2.5']:+.4f}, {dd['p97.5']:+.4f}] "
                  f"| {dd['p_prod_beats']*100:.1f}% | {'YES' if dd['excludes_zero'] else 'no'} |")
        A("")
    A("**2a. PROD vs SINGLE-K3** (collapses BOTH knobs: K 4->3 AND drop sub-select):\n")
    for wl, wt in [("clean", "Clean (18y)"), ("ext", "Extended (27y)")]:
        A(f"*{wt}*\n")
        _bt(p[wl], "SINGLE")
    A("**2b. PROD vs IV4** (isolates the PURE sub-select knob; K=4 fixed in both):\n")
    for wl, wt in [("clean", "Clean (18y)"), ("ext", "Extended (27y)")]:
        A(f"*{wt}*\n")
        _bt(pi[wl], "IV4")

    ov = o["overlap_prod_vs_singleK3"]
    A("## 3. Holdings overlap -- PROD min-var-3 vs SINGLE-K3 top-3 momentum\n")
    A("How often do the two risky baskets differ? PROD drops the highest-variance of the "
      "top-4; SINGLE-K3 drops the 4th-momentum name (and may also differ in breadth when "
      "the 3rd-momentum is negative but the 4th positive). `forward 1-month return` = "
      "realized return of each risky basket from rebal date to next, as held (inverse-vol "
      "weights; safe sleeve excluded for the differential).\n")
    A("| Window | rebals | differ | % differ | PROD wins | SINGLE wins | ties | PROD avg fwd | SINGLE avg fwd | (PROD-SINGLE) avg fwd |")
    A("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for wl in ("clean", "ext"):
        d = ov[wl]
        A(f"| {wl} | {d['n_rebal']} | {d['n_differ']} | {d['frac_differ']*100:.1f}% "
          f"| {d['when_differ_prod_wins']} | {d['when_differ_single_wins']} | {d['when_differ_ties']} "
          f"| {d['when_differ_prod_avg_fwd']*100:.2f}% | {d['when_differ_single_avg_fwd']*100:.2f}% "
          f"| {d['when_differ_prod_minus_single_avg_fwd']*100:+.2f}% |")
    A("")

    A("## 4. Verdict\n")
    _verdict(A, o)

    A("## Caveats\n")
    A("- All post-cost (10 bps/side), T+1 MOO exact with real yfinance auto_adjust opens; "
      "CPM-solo (no equity vol gate, which only affects the BULL/blend sleeve).")
    A("- Ext 27y is partially proxy-backed for the CPM trend universe pre-2006; clean 18y "
      "has full real-open coverage and is the decisive lens.")
    A("- Paired bootstrap resamples the common daily index with stationary blocks (size 21), "
      "identical draws to PROD and SINGLE-K3 so the per-resample difference is paired; "
      "annualization uses the window's real calendar span.")
    A("- Forward-return attribution in item 3 compares the RISKY baskets only (safe sleeve "
      "excluded), as held with inverse-vol weights, over the realized hold month; it is a "
      "selection-quality diagnostic, not the net post-cost P&L (which item 1/2 capture).")

    Path(ROOT / "research" / "parsimony_substage_vs_singlestage_findings.md").write_text("\n".join(L) + "\n")


def _verdict(A, o):
    h = o["headline"]
    pc = o["paired_bootstrap_prod_vs_singleK3"]["clean"]
    pe = o["paired_bootstrap_prod_vs_singleK3"]["ext"]
    cP, cS = h["PROD"]["clean"], h["SINGLE_K3"]["clean"]
    eP, eS = h["PROD"]["ext"], h["SINGLE_K3"]["ext"]
    A("Computed numbers (clean window decisive):\n")
    A(f"- **CPM-solo clean:** PROD Sharpe {cP['sharpe']:.4f} / MaxDD {cP['maxdd']*100:.2f}% "
      f"/ Calmar {cP['calmar']:.4f}; SINGLE-K3 Sharpe {cS['sharpe']:.4f} / MaxDD "
      f"{cS['maxdd']*100:.2f}% / Calmar {cS['calmar']:.4f}.")
    A(f"- **CPM-solo ext:** PROD Sharpe {eP['sharpe']:.4f} / MaxDD {eP['maxdd']*100:.2f}% "
      f"/ Calmar {eP['calmar']:.4f}; SINGLE-K3 Sharpe {eS['sharpe']:.4f} / MaxDD "
      f"{eS['maxdd']*100:.2f}% / Calmar {eS['calmar']:.4f}.")
    A(f"- **Paired clean (PROD-SINGLE):** dSharpe {pc['sharpe']['mean']:+.4f} "
      f"CI[{pc['sharpe']['p2.5']:+.4f},{pc['sharpe']['p97.5']:+.4f}] P(PROD)={pc['sharpe']['p_prod_beats']*100:.1f}%; "
      f"dMaxDD {pc['maxdd']['mean']*100:+.2f}pp P(PROD)={pc['maxdd']['p_prod_beats']*100:.1f}%; "
      f"dCalmar {pc['calmar']['mean']:+.4f} P(PROD)={pc['calmar']['p_prod_beats']*100:.1f}%.")
    A(f"- **Paired ext (PROD-SINGLE):** dSharpe {pe['sharpe']['mean']:+.4f} "
      f"CI[{pe['sharpe']['p2.5']:+.4f},{pe['sharpe']['p97.5']:+.4f}] P(PROD)={pe['sharpe']['p_prod_beats']*100:.1f}%; "
      f"dMaxDD {pe['maxdd']['mean']*100:+.2f}pp P(PROD)={pe['maxdd']['p_prod_beats']*100:.1f}%; "
      f"dCalmar {pe['calmar']['mean']:+.4f} P(PROD)={pe['calmar']['p_prod_beats']*100:.1f}%.")
    A("\n(Prose parsimony verdict appended manually after inspecting numbers.)\n")


if __name__ == "__main__":
    main()
