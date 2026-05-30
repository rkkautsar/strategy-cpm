# -*- coding: utf-8 -*-
"""Throwaway research (read-only re: production): is MIN-AVERAGE-PAIRWISE-CORRELATION
a better 3-subset SELECTION objective than the production MIN-VARIANCE for the CPM
(Cross-asset Parity Momentum) sleeve?

CPM core: from the top-K=4 positive-trend candidate pool, select a 3-subset, then
inverse-vol weight it. Low-breadth handling = STRICT-3 partial-safe fallback
(variant A of fallback_partialsafe_vs_none.py): risky_fraction = min(n_pos,3)/3,
remainder to the timed SHV/IEF safe. n_pos in {1,2} therefore inverse-vol weights
ALL positives (no 3-subset choice needed) -> the SELECTION rule only differentiates
months where n_pos >= 4 (choose 3 of 4); n_pos==3 has a single 3-subset.

Selection rules compared (all inverse-vol weighted, STRICT-3 partial-safe fallback):
  MINVAR  (production): 3-subset minimizing equal-weight portfolio variance w'Sigma w.
  MINCORR             : 3-subset minimizing the average of the 3 pairwise correlations
                        (most mutually-diversified trio; ignores vol levels).
  MINVOL  (reference) : the 3 lowest individual-vol assets (ignores correlation).

Everything else IDENTICAL to production (variant A): vol-adjusted Faber ranker,
K=4, HYG-or-TIP canary, timed SHV/IEF safe, cov lookback 504d, T+1 MOO exact
("mooex", real auto_adjust opens), 10 bps/side post-cost. Clean 18y / ext 27y.

VERIFY before trusting variants: MINVAR (production) reproduces the STRICT-3 CPM-solo
anchor CLEAN 1.2667 / -12.66% / 1.1306. (Also ext 1.2349 / -15.18% / 0.9119.)

No production files touched. Writes research/selection_mincorr_vs_minvar_findings.md (+ json).
"""
from __future__ import annotations
import sys, json
from itertools import combinations
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
COST = COST_BPS_PER_SIDE  # 10
CPM_UNIV = ["QQQ", "SPHQ", "EFA", "EEM", "VNQ", "GLD", "TLT", "DBC"]
SAFE = ["SHV", "IEF"]
LOOKBACK = CORR_LOOKBACK_DAYS  # 504
K = TOP_K_CANDIDATES           # 4
M = 3

CLEAN_START = pd.Timestamp("2008-05-30")
EXT_START = pd.Timestamp("1999-03-10")
END = pd.Timestamp("2026-05-22")

B, BLOCK, SEED = 2000, 21, 42

ANCHOR = {"clean": (1.2667, -12.66, 1.1306), "ext": (1.2349, -15.18, 0.9119)}

RULES = ["MINVAR", "MINCORR", "MINVOL"]
RLABEL = {"MINVAR": "MINVAR (production)", "MINCORR": "MINCORR (diversification)",
          "MINVOL": "MINVOL (3 lowest-vol, ref)"}


# ---------------------------------------------------------------------------
# Selection.  Cov window mirrors cpm_live.min_var_subset / inv_vol_weights
# EXACTLY (rets = close[cand].pct_change().dropna(how='all').tail(lookback);
# require >= lookback rows; reject if cov has NaN). Returns None -> caller
# inverse-vol weights all candidates (degenerate guard, matches production).
# ---------------------------------------------------------------------------
def _window(close, candidates, lookback):
    rets = close[candidates].pct_change().dropna(how="all").tail(lookback)
    if len(rets) < lookback:
        return None, None
    cov = rets.cov()
    if cov.isna().any().any():
        return None, None
    return rets, cov


def select_subset(close, candidates, lookback, m, rule):
    """Pick m-subset of candidates under `rule`. None on degenerate window."""
    if len(candidates) < m:
        return None
    if rule == "MINVAR":
        # delegate to production primitive for byte-identical anchor reproduction
        return min_var_subset(close, candidates, lookback, m)
    rets, cov = _window(close, candidates, lookback)
    if cov is None:
        return None
    if rule == "MINVOL":
        sigma = pd.Series(np.sqrt(np.diag(cov.values)), index=cov.index)
        return list(sigma.sort_values().index[:m])
    if rule == "MINCORR":
        corr = rets.corr()
        if corr.isna().any().any():
            return None
        iu = np.triu_indices(m, k=1)
        best, best_c = None, np.inf
        for combo in combinations(candidates, m):
            cl = list(combo)
            sub = corr.loc[cl, cl].values
            avg_c = float(sub[iu].mean())
            if avg_c < best_c:
                best_c, best = avg_c, combo
        return list(best) if best is not None else None
    raise ValueError(rule)


# ---------------------------------------------------------------------------
def _select(close, sd):
    """Production candidate selection -> (safe, positives list, faber)."""
    monthly = close.loc[:sd].resample("ME").last()
    safe = best_safe(monthly, sd, SAFE)
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


def cpm_wf(close, sd, rule):
    """STRICT-3 partial-safe CPM weight fn; SELECTION rule swaps the 3-subset pick."""
    safe, positive, _ = _select(close, sd)
    n = len(positive)
    if n == 0:
        return {safe: 1.0}
    csub = close.loc[:sd]
    if n >= 3:
        pick = select_subset(csub, positive, LOOKBACK, M, rule)
        if pick is None:
            pick = positive
        return inv_vol_weights(csub, pick, LOOKBACK)
    # n_pos in {1,2}: STRICT-3 partial-safe (selection-agnostic; identical across rules)
    risky_fraction = n / 3.0
    rw = inv_vol_weights(csub, positive, LOOKBACK)
    out = {t: w * risky_fraction for t, w in rw.items()}
    out[safe] = out.get(safe, 0.0) + (1.0 - risky_fraction)
    return out


# ---------------------------------------------------------------------------
def met(s, cash):
    m = perf_metrics(s, cash)
    return {"sharpe": m.get("sharpe"), "cagr": m.get("cagr"), "vol": m.get("vol"),
            "maxdd": m.get("max_drawdown"), "calmar": m.get("calmar")}


def win(s, start, end):
    return s.loc[(s.index >= start) & (s.index <= end)]


def run_cpm(close, daily, intraday, overnight, rule, cost=COST):
    wf = lambda sd: cpm_wf(close, sd, rule)
    s, _ = H._segment_returns_conv(close, daily, wf, EXT_START, END, CONV,
                                   cost, intraday, overnight)
    return s


def sig_dates(close, start, end):
    mi = (pd.DataFrame({"x": 1}, index=close.index)
          .groupby(pd.Grouper(freq="ME")).tail(1))
    return mi.index[(mi.index >= start) & (mi.index <= end)].tolist()


# ---------- bootstrap helpers (PBC semantics) ----------
def metrics_from_array(r, n_years):
    vol = r.std(ddof=0) * np.sqrt(252)
    sharpe = (r.mean() * 252) / vol if vol > 0 else np.nan
    eq = np.cumprod(1.0 + r)
    cagr = eq[-1] ** (1.0 / n_years) - 1.0 if n_years > 0 else np.nan
    rm = np.maximum.accumulate(eq)
    mdd = (eq / rm - 1.0).min()
    calmar = cagr / abs(mdd) if mdd != 0 else np.nan
    return sharpe, mdd, calmar


def block_index(n, block, rng):
    nb = (n // block) + 1
    parts = []
    for _ in range(nb):
        s = int(rng.integers(0, n))
        e = s + block
        if e <= n:
            parts.append(np.arange(s, e))
        else:
            parts.append(np.concatenate([np.arange(s, n), np.arange(0, e - n)]))
    return np.concatenate(parts)[:n]


def paired_boot(a_r, b_r, n_years):
    """(b - a) paired block bootstrap. b = challenger (MINCORR), a = MINVAR.
    Positive sharpe/maxdd/calmar => b (MINCORR) wins (maxdd less negative = shallower)."""
    n = len(a_r)
    rng = np.random.default_rng(SEED)
    ds, dm, dc = [], [], []
    for _ in range(B):
        idx = block_index(n, BLOCK, rng)
        as_, am, ac = metrics_from_array(a_r[idx], n_years)
        bs, bm, bc = metrics_from_array(b_r[idx], n_years)
        ds.append(bs - as_); dm.append(bm - am); dc.append(bc - ac)

    def summ(arr):
        x = np.asarray(arr, dtype=float)
        x = x[np.isfinite(x)]
        lo, hi = np.percentile(x, 2.5), np.percentile(x, 97.5)
        return {"p_b_wins": float(np.mean(x > 0)), "mean": float(x.mean()),
                "ci_lo": float(lo), "ci_hi": float(hi),
                "excludes_zero": bool(lo > 0 or hi < 0)}
    return {"sharpe": summ(ds), "maxdd": summ(dm), "calmar": summ(dc)}


# ---------- diversification / overlap diagnostics ----------
def subset_metrics(close, picks, lookback):
    """avg pairwise corr + effN (1/HHI of inverse-vol weights) of held subset."""
    rets, cov = _window(close, picks, lookback)
    if cov is None:
        return float("nan"), float("nan")
    corr = rets.corr()
    m = len(picks)
    iu = np.triu_indices(m, k=1)
    avg_c = float(corr.loc[picks, picks].values[iu].mean()) if m >= 2 else float("nan")
    w = inv_vol_weights(close, picks, lookback)
    vals = [v for v in w.values() if v > 1e-9]
    hhi = sum(v * v for v in vals)
    effn = (1.0 / hhi) if hhi > 0 else float("nan")
    return avg_c, effn


def overlap_analysis(close, start, end):
    """Per selection-active rebal (n_pos>=4): picks under each rule, Jaccard
    MINCORR vs MINVAR, and forward-month invvol portfolio return per rule for
    the months where they differ (to see who wins)."""
    sds = sig_dates(close, start, end)
    rows = []
    for i, sd in enumerate(sds):
        safe, positive, _ = _select(close, sd)
        n = len(positive)
        if n < 4:
            continue  # selection only differentiates when choosing 3-of->=4
        csub = close.loc[:sd]
        picks = {r: select_subset(csub, positive, LOOKBACK, M, r) for r in RULES}
        if any(picks[r] is None for r in RULES):
            continue
        # forward simple month return (close->close over applied window) per rule, invvol
        fut = close.index[close.index > sd]
        if len(fut) == 0:
            continue
        af = fut[0]
        nxt = sds[i + 1] if i + 1 < len(sds) else None
        if nxt is not None:
            nf = close.index[close.index > nxt]
            ea = nf[0] if len(nf) else end
        else:
            ea = end
        seg = close.loc[(close.index >= af) & (close.index <= ea)]
        fr = {}
        for r in RULES:
            w = inv_vol_weights(csub, picks[r], LOOKBACK)
            if len(seg) < 2:
                fr[r] = float("nan")
                continue
            sub = seg[list(w.keys())].ffill()
            ret = (sub.iloc[-1] / sub.iloc[0] - 1.0)
            fr[r] = float(sum(w[t] * ret.get(t, 0.0) for t in w))
        rows.append({"sd": sd, "n_pos": n,
                     "picks": {r: sorted(picks[r]) for r in RULES},
                     "fwd": fr})
    return rows


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

    rets = {r: run_cpm(close, daily, intraday, overnight, r) for r in RULES}

    out = {"meta": {"conv": CONV, "cost_bps": COST, "lookback": LOOKBACK, "K": K,
                    "M": M, "weighting": "INVVOL-3", "fallback": "STRICT-3 partial-safe",
                    "B": B, "block": BLOCK, "seed": SEED,
                    "clean_start": str(CLEAN_START.date()), "ext_start": str(EXT_START.date()),
                    "end": str(end.date())}}

    # ---- ANCHOR CHECK (MINVAR production) ----
    print("=== ANCHOR CHECK (MINVAR production, STRICT-3) ===")
    anc = {}
    for wl, st in [("clean", CLEAN_START), ("ext", EXT_START)]:
        m = met(win(rets["MINVAR"], st, end), cash)
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

    # ---- ITEM 1: HEADLINE (CPM-solo, net 10bps) ----
    headline = {}
    for r in RULES:
        headline[r] = {wl: met(win(rets[r], st, end), cash)
                       for wl, st in [("clean", CLEAN_START), ("ext", EXT_START)]}
    out["headline"] = headline

    # ---- ITEM 2: PAIRED BOOTSTRAP MINCORR (b) vs MINVAR (a) ----
    pboot = {}
    for wl, st in [("clean", CLEAN_START), ("ext", EXT_START)]:
        a = win(rets["MINVAR"], st, end)
        b = win(rets["MINCORR"], st, end)
        common = a.index.intersection(b.index)
        a, b = a.reindex(common).fillna(0.0), b.reindex(common).fillna(0.0)
        ny = (common[-1] - common[0]).days / 365.25
        pboot[wl] = {"n_days": len(common), "n_years": ny,
                     "corr": float(np.corrcoef(a.values, b.values)[0, 1]),
                     "diff_mincorr_minus_minvar": paired_boot(a.values, b.values, ny)}
        d = pboot[wl]["diff_mincorr_minus_minvar"]
        print(f"paired boot {wl}: dSharpe {d['sharpe']['mean']:+.3f} "
              f"CI[{d['sharpe']['ci_lo']:+.3f},{d['sharpe']['ci_hi']:+.3f}] "
              f"P(mincorr>minvar)={d['sharpe']['p_b_wins']*100:.1f}%")
    out["paired_bootstrap"] = pboot

    # ---- ITEM 3: SUBSET OVERLAP (selection-active months n_pos>=4) ----
    overlap = {}
    for wl, st in [("clean", CLEAN_START), ("ext", EXT_START)]:
        rows = overlap_analysis(close, st, end)
        n_active = len(rows)
        same = sum(1 for r in rows if set(r["picks"]["MINCORR"]) == set(r["picks"]["MINVAR"]))
        diff = n_active - same
        jacc = [len(set(r["picks"]["MINCORR"]) & set(r["picks"]["MINVAR"])) /
                len(set(r["picks"]["MINCORR"]) | set(r["picks"]["MINVAR"])) for r in rows]
        # when they differ: forward return comparison
        diff_rows = [r for r in rows if set(r["picks"]["MINCORR"]) != set(r["picks"]["MINVAR"])]
        mc_wins = sum(1 for r in diff_rows
                      if np.isfinite(r["fwd"]["MINCORR"]) and np.isfinite(r["fwd"]["MINVAR"])
                      and r["fwd"]["MINCORR"] > r["fwd"]["MINVAR"])
        mc_fwd = [r["fwd"]["MINCORR"] for r in diff_rows if np.isfinite(r["fwd"]["MINCORR"])]
        mv_fwd = [r["fwd"]["MINVAR"] for r in diff_rows if np.isfinite(r["fwd"]["MINVAR"])]
        overlap[wl] = {
            "n_rebal_total": len(sig_dates(close, st, end)),
            "n_selection_active": n_active,
            "n_same_subset": same, "n_diff_subset": diff,
            "pct_diff": (diff / n_active) if n_active else float("nan"),
            "avg_jaccard": float(np.mean(jacc)) if jacc else float("nan"),
            "diff_months_mincorr_wins_fwd": mc_wins,
            "diff_months_total": len(diff_rows),
            "avg_fwd_mincorr_on_diff": float(np.mean(mc_fwd)) if mc_fwd else float("nan"),
            "avg_fwd_minvar_on_diff": float(np.mean(mv_fwd)) if mv_fwd else float("nan"),
        }
    out["overlap"] = overlap

    # ---- ITEM 4: CONCENTRATION / DIVERSIFICATION of held subsets ----
    diversif = {}
    for wl, st in [("clean", CLEAN_START), ("ext", EXT_START)]:
        diversif[wl] = {}
        for r in RULES:
            corrs, effns = [], []
            for sd in sig_dates(close, st, end):
                safe, positive, _ = _select(close, sd)
                n = len(positive)
                if n < 3:
                    continue  # held subset = all positives (partial-safe); skip selection-irrelevant
                csub = close.loc[:sd]
                pick = select_subset(csub, positive, LOOKBACK, M, r)
                if pick is None:
                    continue
                ac, en = subset_metrics(csub, pick, LOOKBACK)
                if np.isfinite(ac):
                    corrs.append(ac)
                if np.isfinite(en):
                    effns.append(en)
            diversif[wl][r] = {"n_months": len(corrs),
                               "avg_pairwise_corr": float(np.mean(corrs)) if corrs else float("nan"),
                               "avg_eff_n": float(np.mean(effns)) if effns else float("nan")}
    out["diversification"] = diversif

    (Path(__file__).with_suffix(".json")).write_text(json.dumps(out, indent=2, default=float))
    write_md(out)
    print("\nDONE -> research/selection_mincorr_vs_minvar_findings.md")
    return out


# ---------------------------------------------------------------------------
def write_md(o):
    L = []
    A = L.append
    m = o["meta"]

    def r5(mm):
        return (f"{mm['sharpe']:.4f} | {mm['cagr']*100:.2f}% | {mm['vol']*100:.2f}% "
                f"| {mm['maxdd']*100:.2f}% | {mm['calmar']:.4f}")

    A("# CPM 3-subset selection: MIN-AVG-PAIRWISE-CORRELATION vs MIN-VARIANCE\n")
    A("Is **MINCORR** (pure-diversification, correlation-based, Choueifaty-flavored) a "
      "better 3-subset SELECTION objective than the production **MINVAR** for the CPM "
      "(Cross-asset Parity Momentum) sleeve? **MINVOL** (3 lowest individual-vol assets) "
      "is a reference. All three are inverse-vol weighted with a STRICT-3 partial-safe "
      "fallback; only the 3-subset selection rule changes.\n")
    A("**Selection rules (pick 3 of the top-K=4 positive-trend candidates):**\n")
    A("| Rule | Objective |")
    A("|---|---|")
    A("| MINVAR (production) | minimize equal-weight portfolio variance w'Sigma w |")
    A("| MINCORR | minimize the average of the 3 pairwise correlations (most diversified trio) |")
    A("| MINVOL (ref) | the 3 lowest individual-vol assets (ignores correlation) |")
    A("")
    A("**Both MINVAR and MINCORR are risk-based selectors** (use only the trailing risk "
      "estimate, not realized performance) -> neither is overfit-prone in the way a "
      "performance-based selector would be.\n")
    A(f"**Config (every table):** weighting = inverse-vol; fallback = STRICT-3 partial-safe "
      f"(risky_fraction = min(n_pos,3)/3, remainder to timed SHV/IEF safe); cov lookback "
      f"{m['lookback']}d; K={m['K']}; vol-adjusted Faber ranker; HYG-or-TIP canary. "
      f"Execution = T+1 MOO exact (`mooex`, real auto_adjust opens); post-cost "
      f"{m['cost_bps']} bps/side. Clean window {m['clean_start']}..{m['end']} (18y); "
      f"extended {m['ext_start']}..{m['end']} (27y).\n")
    A("**The selection rule only differentiates months where n_pos >= 4** (choose 3 of 4). "
      "When n_pos == 3 there is a single 3-subset; when n_pos in {1,2} the STRICT-3 "
      "partial-safe inverse-vol weights ALL positives (selection-agnostic).\n")
    A("Source harness: `research/selection_mincorr_vs_minvar.py` (read-only; no production "
      "files touched). MINVAR delegates to `cpm_live.min_var_subset` for byte-identical "
      "anchor reproduction.\n")

    a = o["anchor"]
    A("## 0. Anchor check (MINVAR reproduces the STRICT-3 CPM-solo anchor)\n")
    A("| Window | Sharpe | MaxDD | Calmar | Expected | Match |")
    A("|---|---:|---:|---:|---|---|")
    for wl in ("clean", "ext"):
        e = a[wl]["expect"]
        A(f"| {wl} | {a[wl]['sharpe']:.4f} | {a[wl]['maxdd']*100:.2f}% | {a[wl]['calmar']:.4f} "
          f"| {e[0]}/{e[1]}%/{e[2]} | {'CONFIRMED' if a[wl]['ok'] else 'MISMATCH'} |")
    A("\nMINVAR reproduces the STRICT-3 anchor exactly; MINCORR/MINVOL are trusted relative to it.\n")

    h = o["headline"]
    A("## 1. Headline -- CPM-solo, net 10 bps/side\n")
    for wl, wt in [("clean", "Clean (18y)"), ("ext", "Extended (27y)")]:
        A(f"**{wt}:**\n")
        A("| Selection | Sharpe | CAGR | Vol | MaxDD | Calmar |")
        A("|---|---:|---:|---:|---:|---:|")
        for r in RULES:
            A(f"| {RLABEL[r]} | {r5(h[r][wl])} |")
        A("")

    p = o["paired_bootstrap"]
    A(f"## 2. Paired block bootstrap -- MINCORR vs MINVAR (B={m['B']}, block={m['block']}, seed={m['seed']})\n")
    A("Same block draws applied to both rules (paired). Difference = MINCORR minus MINVAR. "
      "Positive => MINCORR wins (for MaxDD, positive = less negative = shallower). "
      "'Significant' if the 95% CI excludes 0.\n")
    for wl, wt in [("clean", "Clean (18y)"), ("ext", "Extended (27y)")]:
        d = p[wl]["diff_mincorr_minus_minvar"]
        A(f"### {wt} (daily corr MINCORR vs MINVAR = {p[wl]['corr']:.4f})\n")
        A("| Metric (MINCORR-MINVAR) | mean | 95% CI | P(MINCORR>MINVAR) | excludes 0? |")
        A("|---|---:|---|---:|---:|")
        for k, lab in [("sharpe", "dSharpe"), ("maxdd", "dMaxDD"), ("calmar", "dCalmar")]:
            dd = d[k]
            if k == "maxdd":
                A(f"| {lab} | {dd['mean']*100:+.2f}pp | [{dd['ci_lo']*100:+.2f}, "
                  f"{dd['ci_hi']*100:+.2f}]pp | {dd['p_b_wins']*100:.1f}% | "
                  f"{'YES' if dd['excludes_zero'] else 'no'} |")
            else:
                A(f"| {lab} | {dd['mean']:+.4f} | [{dd['ci_lo']:+.4f}, {dd['ci_hi']:+.4f}] "
                  f"| {dd['p_b_wins']*100:.1f}% | {'YES' if dd['excludes_zero'] else 'no'} |")
        A("")

    ov = o["overlap"]
    A("## 3. Subset overlap -- how often MINCORR picks a DIFFERENT 3-subset than MINVAR\n")
    A("Restricted to **selection-active** rebalances (n_pos >= 4, where a 3-of-4 choice "
      "actually exists). Jaccard = |intersection|/|union| of the two 3-subsets.\n")
    A("| Window | rebal total | selection-active (n_pos>=4) | same subset | different | % different | avg Jaccard |")
    A("|---|---:|---:|---:|---:|---:|---:|")
    for wl, wt in [("clean", "Clean (18y)"), ("ext", "Extended (27y)")]:
        d = ov[wl]
        A(f"| {wt} | {d['n_rebal_total']} | {d['n_selection_active']} | {d['n_same_subset']} "
          f"| {d['n_diff_subset']} | {d['pct_diff']*100:.1f}% | {d['avg_jaccard']:.3f} |")
    A("")
    A("**When they differ -- who wins the forward month?** (invvol portfolio close->close "
      "return over the applied month, on the differing rebalances):\n")
    A("| Window | differing months | MINCORR wins fwd | avg fwd MINCORR | avg fwd MINVAR |")
    A("|---|---:|---:|---:|---:|")
    for wl, wt in [("clean", "Clean (18y)"), ("ext", "Extended (27y)")]:
        d = ov[wl]
        A(f"| {wt} | {d['diff_months_total']} | {d['diff_months_mincorr_wins_fwd']} "
          f"| {d['avg_fwd_mincorr_on_diff']*100:+.3f}% | {d['avg_fwd_minvar_on_diff']*100:+.3f}% |")
    A("")

    dv = o["diversification"]
    A("## 4. Diversification / concentration of the held 3-subset (n_pos>=3 months)\n")
    A("avg pairwise corr = mean of the 3 trailing 504d pairwise correlations of the held trio; "
      "effN = 1/HHI of the inverse-vol weights (max 3.0 = perfectly balanced).\n")
    for wl, wt in [("clean", "Clean (18y)"), ("ext", "Extended (27y)")]:
        A(f"**{wt}:**\n")
        A("| Selection | months | avg pairwise corr | avg effN |")
        A("|---|---:|---:|---:|")
        for r in RULES:
            d = dv[wl][r]
            A(f"| {RLABEL[r]} | {d['n_months']} | {d['avg_pairwise_corr']:.4f} | {d['avg_eff_n']:.3f} |")
        A("")

    A("## 5. Verdict\n")
    _verdict(A, o)

    A("## Caveats\n")
    A("- All post-cost (10 bps/side), T+1 MOO exact with real yfinance auto_adjust opens. "
      "CPM-solo (no equity vol gate; that gate only affects BULL/blend, out of scope here).")
    A("- The selection rule only acts on n_pos>=4 rebalances; differences are diluted across "
      "the full curve by the many n_pos<4 (identical) months. Magnitudes are therefore small "
      "by construction.")
    A("- Ext 27y is partially proxy-backed for the CPM trend universe pre-2006; clean 18y has "
      "full real-open coverage and is the decisive lens.")
    A("- Forward-month win attribution in Section 3 uses simple close->close invvol portfolio "
      "return over the applied window (gross, no cost) -- a directional attribution, not the "
      "post-cost curve metric.")
    A("- MINCORR ignores vol levels in selection but is still inverse-vol weighted afterward, "
      "so vol does re-enter at the weighting step.")

    Path(ROOT / "research" / "selection_mincorr_vs_minvar_findings.md").write_text("\n".join(L) + "\n")


def _verdict(A, o):
    h = o["headline"]; pb = o["paired_bootstrap"]; ov = o["overlap"]
    cc, mv = h["MINCORR"]["clean"], h["MINVAR"]["clean"]
    ec, ev = h["MINCORR"]["ext"], h["MINVAR"]["ext"]
    db = pb["clean"]["diff_mincorr_minus_minvar"]
    A("Filled from the computed numbers (clean window decisive):\n")
    A(f"- **CPM-solo clean:** MINCORR Sharpe {cc['sharpe']:.4f} / CAGR {cc['cagr']*100:.2f}% / "
      f"MaxDD {cc['maxdd']*100:.2f}% / Calmar {cc['calmar']:.4f}; "
      f"MINVAR Sharpe {mv['sharpe']:.4f} / CAGR {mv['cagr']*100:.2f}% / MaxDD {mv['maxdd']*100:.2f}% "
      f"/ Calmar {mv['calmar']:.4f}.")
    A(f"- **CPM-solo ext:** MINCORR Sharpe {ec['sharpe']:.4f} / MaxDD {ec['maxdd']*100:.2f}% / "
      f"Calmar {ec['calmar']:.4f}; MINVAR Sharpe {ev['sharpe']:.4f} / MaxDD {ev['maxdd']*100:.2f}% "
      f"/ Calmar {ev['calmar']:.4f}.")
    A(f"- **Paired clean (MINCORR-MINVAR):** dSharpe {db['sharpe']['mean']:+.4f} "
      f"CI[{db['sharpe']['ci_lo']:+.4f},{db['sharpe']['ci_hi']:+.4f}] "
      f"(P {db['sharpe']['p_b_wins']*100:.0f}%); "
      f"dMaxDD {db['maxdd']['mean']*100:+.2f}pp "
      f"CI[{db['maxdd']['ci_lo']*100:+.2f},{db['maxdd']['ci_hi']*100:+.2f}]pp; "
      f"dCalmar {db['calmar']['mean']:+.4f} "
      f"CI[{db['calmar']['ci_lo']:+.4f},{db['calmar']['ci_hi']:+.4f}].")
    A(f"- **Subset overlap (clean):** MINCORR differs from MINVAR on "
      f"{ov['clean']['n_diff_subset']}/{ov['clean']['n_selection_active']} selection-active "
      f"months ({ov['clean']['pct_diff']*100:.1f}%), avg Jaccard {ov['clean']['avg_jaccard']:.3f}.")
    A("\n(Prose verdict appended manually after inspecting numbers.)\n")


if __name__ == "__main__":
    main()
