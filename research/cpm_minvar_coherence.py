"""Is the prior "min-var + EW-sizing wins" Sharpe edge a SELECTION-OBJECTIVE /
SIZING COHERENCE artifact, or a real edge that survives a matched IV objective?

Throwaway research. Read-only re production. No production files changed; no commit.

Context / insight under test
----------------------------
The current min-var SUBSET selection (research/cpm_weighting_corr._min_var_subset)
minimizes the EQUAL-WEIGHT portfolio variance:
    w = 1/m, v = w^2 * cov_sub.sum()
In the prior simple-corr study the strongest Sharpe cell was MINVAR + EW-sizing
(clean Sharpe 1.2711, the only paired bootstrap CI excluding 0). Hypothesis: that
may be an ARTIFACT of objective/sizing COHERENCE -- you select the trio that
minimizes EW-variance, then EW-weight it, so a variance-driven metric
tautologically favors the matched pair. MINVAR(EW-obj) + IV-sizing is a MISMATCH.
A fair EW-vs-IV test must pair each sizing with its OWN matched selection
objective.

Build
-----
minvar_ivobj : same subset search as _min_var_subset, but with INVERSE-VOL
  weights w_iv ~ 1/sigma_i (normalized over the subset), minimizing
  w_iv' Sigma w_iv over all m-subsets (m=3 of top-4, matching prior).
minvar_ewobj : the EXISTING _min_var_subset (= current min-var EW-objective).

Coherence 2x2 (selection objective x sizing), m=3 of top-4, everything else
byte-identical to prod (universe/canary/trend/safe/both-252/mooex T+1/10bps,
full-risk-on-3 renormalize over the kept trio as in the prior simple-corr study):

  minvar_ewobj + EW = COHERENT-EW (matched)
  minvar_ewobj + IV = MINVAR_IV    (mismatch; the prior study's MINVAR_IV)
  minvar_ivobj + IV = COHERENT-IV (matched)
  minvar_ivobj + EW = mismatch
References:
  PROD       = top-4 inverse-vol baseline (reproduces anchor)
  PROD_EW    = top-4 + EW (missing pure-sizing cell on unchanged selection)

Decisive questions:
  (a) COHERENT-EW vs COHERENT-IV head to head (clean+ext Sharpe/Calmar/MaxDD/
      turnover + paired bootstrap + 3-seg walk-forward): does EW still win once
      IV gets its OWN matched objective?
  (b) Subset overlap: how often do ewobj and ivobj pick the SAME trio (%)?
  (c) Coherence premium within each sizing: matched vs mismatched objective.
  (d) prod-top4 EW vs IV (pure sizing on unchanged selection).

Run: .venv/bin/python -m research.cpm_minvar_coherence
Out: research/cpm_minvar_coherence_findings.json
     research/cpm_minvar_coherence_findings.md
"""

from __future__ import annotations

import json
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

from research import cpm_harness as H
import cpm_live
from cpm_live import (
    faber_sma_xs, best_safe, sig_13612U,
    RISKY_UNIVERSE, SAFE_POOL, CANARY_ASSETS, CANARY_RULE, TOP_K_CANDIDATES,
)
from research.cpm_weighting_corr import (
    _ret_window, _risky_weights, _min_var_subset,
    CRISES, _sub_metrics, annualized_turnover, paired_block_bootstrap, run_cell,
)

OUT_JSON = Path(__file__).resolve().parent / "cpm_minvar_coherence_findings.json"
OUT_MD = Path(__file__).resolve().parent / "cpm_minvar_coherence_findings.md"


# ---------------- min-var subset objectives ----------------
def _min_var_subset_ewobj(close, sig_d, candidates, lookback, m=3):
    """EW-objective min-var subset == existing _min_var_subset (w=1/m)."""
    return _min_var_subset(close, sig_d, candidates, lookback, m)


def _min_var_subset_ivobj(close, sig_d, candidates, lookback, m=3):
    """IV-objective min-var subset: pick the m-subset minimizing the INVERSE-VOL
    portfolio variance w_iv' Sigma w_iv, where w_iv ~ 1/sigma_i normalized over
    the subset. sigma_i = sqrt(diag(Sigma)) on the SAME trailing window/cov as
    the EW objective, so the only difference is the objective's weight vector."""
    if len(candidates) <= m:
        return list(candidates)
    rets = _ret_window(close.loc[:sig_d], candidates, lookback)
    if len(rets) < lookback:
        return list(candidates)
    cov = rets.cov()
    if cov.isna().any().any():
        return list(candidates)
    best, best_v = None, np.inf
    for combo in combinations(candidates, m):
        sub = cov.loc[list(combo), list(combo)]
        sig = np.sqrt(np.clip(np.diag(sub.values), 1e-18, None))
        w = 1.0 / sig
        w = w / w.sum()
        v = float(w @ sub.values @ w)
        if v < best_v:
            best_v, best = v, combo
    return list(best) if best else list(candidates)


_SUBSET_FN = {
    "rank": None,  # no drop, prod selection
    "minvar_ewobj": _min_var_subset_ewobj,
    "minvar_ivobj": _min_var_subset_ivobj,
}


# ---------------- prod-faithful weight fn: swap SELECTION OBJECTIVE x SIZING ----
def make_weight_fn(selection="rank", sizing="invvol", lookback=None, subset_m=3):
    """Replicate prod selection + strict-4 partial-safe, swapping the subset
    objective and the risky-block sizing.

    selection: rank (prod, no drop) | minvar_ewobj | minvar_ivobj.
    sizing:    invvol (cov diagonal, prod) | ew (1/n over kept names).
    Full-risk-on-drop: when n_pos==4 (the only selection-active state), the kept
    trio is renormalized at FULL risk (risky_fraction stays 1.0), matching the
    prior simple-corr study. Sub-4 positive months are byte-identical to prod.
    """
    lb = lookback or cpm_live.CORR_LOOKBACK_DAYS
    fn = _SUBSET_FN[selection]

    def wf(close_panel, sig_d):
        monthly = close_panel.loc[:sig_d].resample("ME").last()
        safe = best_safe(monthly, sig_d, SAFE_POOL)

        cscores = []
        for c in CANARY_ASSETS:
            if c not in monthly.columns:
                continue
            s = sig_13612U(monthly[c])
            if pd.notna(s):
                cscores.append(s)
        if not cscores:
            return {safe: 1.0}
        n_pos_canary = sum(1 for s in cscores if s > 0)
        if CANARY_RULE == "any_positive":
            if n_pos_canary == 0:
                return {safe: 1.0}
        elif CANARY_RULE == "all_positive":
            if n_pos_canary < len(cscores):
                return {safe: 1.0}
        else:
            if n_pos_canary <= len(cscores) // 2:
                return {safe: 1.0}

        faber = faber_sma_xs(monthly)
        avail = [t for t in RISKY_UNIVERSE
                 if t in faber.index and pd.notna(faber[t])
                 and (sig_d in close_panel.index and pd.notna(close_panel.loc[sig_d].get(t, np.nan)))]
        if not avail:
            return {safe: 1.0}
        dr = close_panel[avail].ffill().pct_change()
        scores = {}
        for t in avail:
            v = dr[t].loc[:sig_d].tail(252).std() * np.sqrt(252)
            if pd.isna(v) or v < 1e-9:
                v = 1.0
            scores[t] = float(faber[t]) / v
        ranked = pd.Series(scores).sort_values(ascending=False)
        top_k = max(2, min(TOP_K_CANDIDATES, len(ranked)))
        top = ranked.iloc[:top_k]
        positive = [t for t in top.index if faber.get(t, -np.inf) > 0]
        if len(positive) == 0:
            return {safe: 1.0}

        picks = list(positive)
        if fn is not None and len(picks) > subset_m:
            picks = fn(close_panel, sig_d, picks, lb, subset_m)

        # full-risk-on-drop: risky_fraction from ORIGINAL n positives (strict-4),
        # but when n_pos==4 -> 1.0, so the kept trio stays 100% risky.
        risky_fraction = min(len(positive), 4) / 4.0
        safe_fraction = 1.0 - risky_fraction

        if sizing == "ew":
            rw = {t: 1.0 / len(picks) for t in picks}
        else:
            rw = _risky_weights(close_panel, sig_d, picks, "invvol", "sample", lb)
        out = {t: w * risky_fraction for t, w in rw.items()}
        if safe_fraction > 0:
            out[safe] = out.get(safe, 0.0) + safe_fraction
        return out

    return wf


# ---------------- subset overlap diagnostic (ewobj vs ivobj) ----------------
def subset_overlap(data, lb=252, subset_m=3):
    """On selection-active months (n_pos==4), compare which trio ewobj vs ivobj
    keep: % identical + avg Jaccard."""
    panel = data.panel
    sig_dates = panel.resample("ME").last().index
    sig_dates = [d for d in sig_dates if d >= data.clean_start and d <= data.end]
    same = 0
    jac = []
    n = 0
    diffs = []
    for d in sig_dates:
        idx = panel.index[panel.index <= d]
        if len(idx) == 0:
            continue
        sd = idx[-1]
        monthly = panel.loc[:sd].resample("ME").last()
        cscores = []
        for c in CANARY_ASSETS:
            if c in monthly.columns:
                s = sig_13612U(monthly[c])
                if pd.notna(s):
                    cscores.append(s)
        if not cscores or sum(1 for s in cscores if s > 0) == 0:
            continue
        faber = faber_sma_xs(monthly)
        avail = [t for t in RISKY_UNIVERSE
                 if t in faber.index and pd.notna(faber[t])
                 and pd.notna(panel.loc[sd].get(t, np.nan))]
        if not avail:
            continue
        dr = panel[avail].ffill().pct_change()
        scores = {}
        for t in avail:
            v = dr[t].loc[:sd].tail(252).std() * np.sqrt(252)
            if pd.isna(v) or v < 1e-9:
                v = 1.0
            scores[t] = float(faber[t]) / v
        ranked = pd.Series(scores).sort_values(ascending=False)
        top = ranked.iloc[:max(2, min(TOP_K_CANDIDATES, len(ranked)))]
        positive = [t for t in top.index if faber.get(t, -np.inf) > 0]
        if len(positive) != 4:
            continue
        s_ew = set(_min_var_subset_ewobj(panel, sd, positive, lb, subset_m))
        s_iv = set(_min_var_subset_ivobj(panel, sd, positive, lb, subset_m))
        n += 1
        if s_ew == s_iv:
            same += 1
        else:
            diffs.append((str(sd.date()), sorted(s_ew), sorted(s_iv)))
        jac.append(len(s_ew & s_iv) / len(s_ew | s_iv))
    if n == 0:
        return {"active_months": 0}
    return {
        "active_months": n,
        "same": same,
        "pct_same": same / n,
        "avg_jaccard": float(np.mean(jac)),
        "n_diff": len(diffs),
        "diff_examples": diffs[:10],
    }


def walk_forward(base_ret, var_ret, cash):
    common = base_ret.index.intersection(var_ret.index)
    bR = base_ret.loc[common]
    vR = var_ret.loc[common]
    n = len(common)
    bounds = [0, n // 3, 2 * n // 3, n]
    segs = []
    for i in range(3):
        lo, hi = bounds[i], bounds[i + 1]
        mb = cpm_live.perf_metrics(bR.iloc[lo:hi], cash)
        mv = cpm_live.perf_metrics(vR.iloc[lo:hi], cash)
        segs.append({
            "start": str(common[lo].date()), "end": str(common[hi - 1].date()),
            "base_Sharpe": mb.get("sharpe"), "var_Sharpe": mv.get("sharpe"),
            "dSharpe": mv.get("sharpe") - mb.get("sharpe"),
            "base_Calmar": mb.get("calmar"), "var_Calmar": mv.get("calmar"),
            "dCalmar": mv.get("calmar") - mb.get("calmar"),
        })
    return segs


def _fmt(x, nd=4):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "n/a"
    return f"{x:.{nd}f}"


def write_md(results):
    cells = results["cells"]
    bs = results["bootstrap"]
    wf = results["walk_forward"]
    ov = results["subset_overlap_252"]
    cp = results["coherence_premium"]

    L = []
    L.append("# Min-var coherence: is the EW-sizing edge a selection-objective/sizing artifact?\n")
    L.append("Throwaway research. Read-only re production; no prod/memo/cpm_live edits; no commit.\n")
    L.append(f"Anchor (clean, via harness): Sharpe {_fmt(results['anchor']['Sharpe'])}, "
             f"MaxDD {_fmt(results['anchor']['MaxDD'])}, Calmar {_fmt(results['anchor']['Calmar'])}.\n")

    L.append("\n## Question / hypothesis\n")
    L.append("Current min-var subset minimizes EQUAL-WEIGHT portfolio variance "
             "(`_min_var_subset`: w=1/m, v=w^2*cov_sub.sum()). Prior study found "
             "MINVAR+EW-sizing the strongest Sharpe cell (clean 1.2711, only CI "
             "excluding 0). Is that a coherence artifact (select for low EW-variance, "
             "then EW-weight) rather than a real EW sizing edge? Fair test pairs each "
             "sizing with its OWN matched selection objective: build `minvar_ivobj` "
             "(minimize INVERSE-VOL portfolio variance over m-subsets) and compare "
             "COHERENT-EW vs COHERENT-IV.\n")

    L.append("\n## Method\n")
    L.append("- Engine: research/cpm_harness.py (mooex T+1, both-252, 10 bps/side). "
             "Anchor verified first.\n")
    L.append("- 2x2 selection objective {minvar_ewobj, minvar_ivobj} x sizing {EW, IV}, "
             "m=3 of top-4, full-risk-on-drop renormalize over kept trio. Everything "
             "else byte-identical to prod (universe/canary/trend/safe).\n")
    L.append("- References: PROD (top-4 IV, anchor), PROD_EW (top-4 + EW).\n")
    L.append("- Metrics: clean (DECISION) + ext + per-crisis + annualized one-way "
             "turnover (net 10 bps). Paired block bootstrap B=2000 (block=21) vs PROD "
             "and COHERENT-EW vs COHERENT-IV directly. 3-seg sequential walk-forward.\n")

    # ---- main 2x2 + reference table ----
    L.append("\n## 2x2 + references (clean = DECISION window)\n")
    order = ["PROD", "PROD_EW", "COHERENT_EW", "MINVAR_IV", "COHERENT_IV", "MINVAR_EWOBJ_EW_MISMATCH"]
    label = {
        "PROD": "PROD (rank top-4 + IV) [anchor]",
        "PROD_EW": "PROD_EW (rank top-4 + EW)",
        "COHERENT_EW": "COHERENT-EW (ewobj + EW) [matched]",
        "MINVAR_IV": "MINVAR_IV (ewobj + IV) [mismatch]",
        "COHERENT_IV": "COHERENT-IV (ivobj + IV) [matched]",
        "MINVAR_EWOBJ_EW_MISMATCH": "ivobj + EW [mismatch]",
    }
    L.append("| cell | clean Sharpe | clean Calmar | clean MaxDD | ext Sharpe | ext Calmar | ext MaxDD | turnover/yr |")
    L.append("|---|---|---|---|---|---|---|---|")
    for k in order:
        c = cells[k]
        cl, ex = c["clean"], c["ext"]
        L.append(f"| {label[k]} | {_fmt(cl['Sharpe'])} | {_fmt(cl['Calmar'])} | {_fmt(cl['MaxDD'])} | "
                 f"{_fmt(ex['Sharpe'])} | {_fmt(ex['Calmar'])} | {_fmt(ex['MaxDD'])} | {_fmt(c['turnover_ann'],3)} |")

    # ---- per-crisis ----
    L.append("\n## Per-crisis Sharpe (ext curve)\n")
    crisis_keys = list(CRISES.keys())
    L.append("| cell | " + " | ".join(crisis_keys) + " |")
    L.append("|---|" + "|".join(["---"] * len(crisis_keys)) + "|")
    for k in order:
        cr = cells[k]["crises"]
        vals = []
        for ck in crisis_keys:
            v = cr.get(ck)
            vals.append(_fmt(v["Sharpe"]) if v else "n/a")
        L.append(f"| {label[k]} | " + " | ".join(vals) + " |")

    L.append("\n## Per-crisis MaxDD (ext curve)\n")
    L.append("| cell | " + " | ".join(crisis_keys) + " |")
    L.append("|---|" + "|".join(["---"] * len(crisis_keys)) + "|")
    for k in order:
        cr = cells[k]["crises"]
        vals = []
        for ck in crisis_keys:
            v = cr.get(ck)
            vals.append(_fmt(v["MaxDD"]) if v else "n/a")
        L.append(f"| {label[k]} | " + " | ".join(vals) + " |")

    # ---- bootstrap vs PROD ----
    L.append("\n## Paired bootstrap vs PROD (clean, B=2000, block=21)\n")
    L.append("| cell | dSharpe mean [95% CI] | p>0 | dCalmar mean [95% CI] | dMaxDD mean [95% CI] |")
    L.append("|---|---|---|---|---|")
    for k in ["PROD_EW", "COHERENT_EW", "MINVAR_IV", "COHERENT_IV", "MINVAR_EWOBJ_EW_MISMATCH"]:
        b = bs[k]
        s, c, d = b["dSharpe"], b["dCalmar"], b["dMaxDD"]
        L.append(f"| {label[k]} | {_fmt(s['mean'])} [{_fmt(s['ci_lo'])}, {_fmt(s['ci_hi'])}] | "
                 f"{_fmt(s['p_gt0'],3)} | {_fmt(c['mean'])} [{_fmt(c['ci_lo'])}, {_fmt(c['ci_hi'])}] | "
                 f"{_fmt(d['mean'])} [{_fmt(d['ci_lo'])}, {_fmt(d['ci_hi'])}] |")

    # ---- COHERENT-EW vs COHERENT-IV direct ----
    L.append("\n## (a) COHERENT-EW vs COHERENT-IV head-to-head (clean, direct paired bootstrap)\n")
    b = results["coherent_ew_vs_iv_bootstrap"]
    s, c, d = b["dSharpe"], b["dCalmar"], b["dMaxDD"]
    L.append("Positive = COHERENT-EW minus COHERENT-IV.\n")
    L.append("| metric | mean | 95% CI | p(EW>IV) |")
    L.append("|---|---|---|---|")
    L.append(f"| dSharpe | {_fmt(s['mean'])} | [{_fmt(s['ci_lo'])}, {_fmt(s['ci_hi'])}] | {_fmt(s['p_gt0'],3)} |")
    L.append(f"| dCalmar | {_fmt(c['mean'])} | [{_fmt(c['ci_lo'])}, {_fmt(c['ci_hi'])}] | {_fmt(c['p_gt0'],3)} |")
    L.append(f"| dMaxDD | {_fmt(d['mean'])} | [{_fmt(d['ci_lo'])}, {_fmt(d['ci_hi'])}] | {_fmt(d['p_gt0'],3)} |")

    L.append("\n### COHERENT-EW vs COHERENT-IV 3-seg walk-forward (clean)\n")
    L.append("Positive dSharpe = COHERENT-EW ahead.\n")
    L.append("| segment | EW Sharpe | IV Sharpe | dSharpe | EW Calmar | IV Calmar | dCalmar |")
    L.append("|---|---|---|---|---|---|---|")
    for seg in results["coherent_ew_vs_iv_wf"]:
        L.append(f"| {seg['start']}..{seg['end']} | {_fmt(seg['var_Sharpe'])} | {_fmt(seg['base_Sharpe'])} | "
                 f"{_fmt(seg['dSharpe'])} | {_fmt(seg['var_Calmar'])} | {_fmt(seg['base_Calmar'])} | {_fmt(seg['dCalmar'])} |")
    L.append("\n(base = COHERENT-IV, var = COHERENT-EW.)\n")

    # ---- (b) subset overlap ----
    L.append("\n## (b) Subset overlap: ewobj vs ivobj trio choice\n")
    L.append(f"Selection-active months (n_pos==4): {ov['active_months']}. "
             f"Same trio: {ov['same']} ({_fmt(ov['pct_same']*100,1)}%). "
             f"Avg Jaccard: {_fmt(ov['avg_jaccard'])}. Differing months: {ov['n_diff']}.\n")
    if ov.get("diff_examples"):
        L.append("\nDiffering-month examples (date, ewobj trio, ivobj trio):\n")
        for dt, ew, iv in ov["diff_examples"]:
            L.append(f"- {dt}: ew={ew} iv={iv}")

    # ---- (c) coherence premium ----
    L.append("\n## (c) Coherence premium within each sizing (clean, paired bootstrap)\n")
    L.append("Does the MATCHED objective beat the MISMATCHED one for that sizing?\n")
    L.append("| test | dSharpe mean | 95% CI | p>0 |")
    L.append("|---|---|---|---|")
    for key, desc in [
        ("iv_matched_vs_mismatch", "IV sizing: ivobj(matched) - ewobj(mismatch)"),
        ("ew_matched_vs_mismatch", "EW sizing: ewobj(matched) - ivobj(mismatch)"),
    ]:
        b = cp[key]["dSharpe"]
        L.append(f"| {desc} | {_fmt(b['mean'])} | [{_fmt(b['ci_lo'])}, {_fmt(b['ci_hi'])}] | {_fmt(b['p_gt0'],3)} |")

    # ---- (d) pure sizing A/B ----
    L.append("\n## (d) PROD top-4: EW vs IV (pure sizing on unchanged selection, clean)\n")
    b = results["prod_ew_vs_iv_bootstrap"]
    s = b["dSharpe"]; c = b["dCalmar"]; d = b["dMaxDD"]
    L.append("Positive = PROD_EW minus PROD (IV).\n")
    L.append("| metric | mean | 95% CI | p(EW>IV) |")
    L.append("|---|---|---|---|")
    L.append(f"| dSharpe | {_fmt(s['mean'])} | [{_fmt(s['ci_lo'])}, {_fmt(s['ci_hi'])}] | {_fmt(s['p_gt0'],3)} |")
    L.append(f"| dCalmar | {_fmt(c['mean'])} | [{_fmt(c['ci_lo'])}, {_fmt(c['ci_hi'])}] | {_fmt(c['p_gt0'],3)} |")
    L.append(f"| dMaxDD | {_fmt(d['mean'])} | [{_fmt(d['ci_lo'])}, {_fmt(d['ci_hi'])}] | {_fmt(d['p_gt0'],3)} |")

    L.append("\n## Verdict\n")
    L.append(results["verdict"])
    L.append("\n")

    OUT_MD.write_text("\n".join(L))


def build_verdict(results):
    cells = results["cells"]
    ew = cells["COHERENT_EW"]["clean"]["Sharpe"]
    iv = cells["COHERENT_IV"]["clean"]["Sharpe"]
    ew_ext = cells["COHERENT_EW"]["ext"]["Sharpe"]
    iv_ext = cells["COHERENT_IV"]["ext"]["Sharpe"]
    b = results["coherent_ew_vs_iv_bootstrap"]["dSharpe"]
    ov = results["subset_overlap_252"]
    ci_excl = (b["ci_lo"] > 0) or (b["ci_hi"] < 0)

    lines = []
    # artifact?
    if b["mean"] > 0 and b["p_gt0"] >= 0.95 and ci_excl:
        artifact = ("NOT a pure coherence artifact: COHERENT-EW still beats COHERENT-IV "
                    f"on clean Sharpe ({ew:.4f} vs {iv:.4f}) with the EW-vs-IV CI excluding 0 "
                    f"(p(EW>IV)={b['p_gt0']:.3f}). The EW edge survives giving IV its own "
                    "matched objective.")
    elif b["mean"] > 0 and b["p_gt0"] >= 0.80:
        artifact = ("PARTLY a coherence artifact: COHERENT-EW still leads COHERENT-IV on "
                    f"clean Sharpe ({ew:.4f} vs {iv:.4f}, p(EW>IV)={b['p_gt0']:.3f}) but the "
                    "EW-vs-IV CI includes 0, so the matched-objective edge is directional, "
                    "not significant -- much of the prior EW headline is coherence/noise.")
    else:
        artifact = ("LARGELY a coherence artifact: once IV gets its own matched objective, "
                    f"the EW edge shrinks/vanishes (clean Sharpe EW {ew:.4f} vs IV {iv:.4f}, "
                    f"EW-vs-IV mean dSharpe {b['mean']:.4f}, p(EW>IV)={b['p_gt0']:.3f}, CI "
                    "includes 0). The prior 'EW beats IV on min-var' was driven by "
                    "objective/sizing coherence, not a real sizing advantage.")
    lines.append(artifact)

    # best coherent pair
    best = "COHERENT-EW" if ew >= iv else "COHERENT-IV"
    best_ext = "COHERENT-EW" if ew_ext >= iv_ext else "COHERENT-IV"
    lines.append(f"Best coherent pair (clean Sharpe): {best} "
                 f"(EW {ew:.4f} / IV {iv:.4f}); ext: {best_ext} (EW {ew_ext:.4f} / IV {iv_ext:.4f}). "
                 f"Turnover/yr EW {cells['COHERENT_EW']['turnover_ann']:.3f} vs IV "
                 f"{cells['COHERENT_IV']['turnover_ann']:.3f} (net 10 bps already in returns).")

    # overlap
    if ov["active_months"]:
        if ov["pct_same"] >= 0.9:
            ovl = (f"Objective choice barely matters: ewobj and ivobj pick the SAME trio "
                   f"{ov['pct_same']*100:.1f}% of active months (avg Jaccard {ov['avg_jaccard']:.3f}); "
                   "sizing is effectively the only lever.")
        elif ov["pct_same"] >= 0.6:
            ovl = (f"Objective choice matters moderately: same trio {ov['pct_same']*100:.1f}% of "
                   f"active months (avg Jaccard {ov['avg_jaccard']:.3f}).")
        else:
            ovl = (f"Objective choice matters: same trio only {ov['pct_same']*100:.1f}% of active "
                   f"months (avg Jaccard {ov['avg_jaccard']:.3f}).")
        lines.append(ovl)

    lines.append("Low ceiling: all paired bootstrap CIs are wide; treat differences within "
                 "the CI band as within-noise. Decision metric is the clean window.")
    return " ".join(lines)


def main():
    data = H.load_data()
    anchor = H.verify_anchor(data=data)
    print("ANCHOR OK:", {k: round(float(v), 4) for k, v in anchor.items() if k in ("Sharpe", "MaxDD", "Calmar")})

    results = {"anchor": {k: float(v) for k, v in anchor.items()}}

    variants = {
        "PROD": make_weight_fn("rank", "invvol"),
        "PROD_EW": make_weight_fn("rank", "ew"),
        "COHERENT_EW": make_weight_fn("minvar_ewobj", "ew"),
        "MINVAR_IV": make_weight_fn("minvar_ewobj", "invvol"),
        "COHERENT_IV": make_weight_fn("minvar_ivobj", "invvol"),
        "MINVAR_EWOBJ_EW_MISMATCH": make_weight_fn("minvar_ivobj", "ew"),
    }
    cells = {}
    for key, wf in variants.items():
        cells[key] = run_cell(wf, data, key)
        print("done", key, "clean Sharpe", round(cells[key]["clean"]["Sharpe"], 4),
              "ext", round(cells[key]["ext"]["Sharpe"], 4),
              "turn", round(cells[key]["turnover_ann"], 3))

    # subset overlap
    results["subset_overlap_252"] = subset_overlap(data, lb=252)
    print("subset overlap:", {k: v for k, v in results["subset_overlap_252"].items() if k != "diff_examples"})

    cash = data.cash
    prod_ret = cells["PROD"]["clean_returns"]

    # bootstrap vs PROD
    results["bootstrap"] = {}
    results["walk_forward"] = {}
    for key in ("PROD_EW", "COHERENT_EW", "MINVAR_IV", "COHERENT_IV", "MINVAR_EWOBJ_EW_MISMATCH"):
        results["bootstrap"][key] = paired_block_bootstrap(cells[key]["clean_returns"], prod_ret, cash)
        results["walk_forward"][key] = walk_forward(prod_ret, cells[key]["clean_returns"], cash)
        print("bootstrap+wf vs PROD done", key)

    # (a) COHERENT-EW vs COHERENT-IV direct
    ew_ret = cells["COHERENT_EW"]["clean_returns"]
    iv_ret = cells["COHERENT_IV"]["clean_returns"]
    results["coherent_ew_vs_iv_bootstrap"] = paired_block_bootstrap(ew_ret, iv_ret, cash)
    results["coherent_ew_vs_iv_wf"] = walk_forward(iv_ret, ew_ret, cash)  # base=IV, var=EW
    print("coherent EW-vs-IV bootstrap+wf done")

    # (c) coherence premium within each sizing
    # IV sizing: ivobj(COHERENT_IV) matched vs ewobj(MINVAR_IV) mismatch
    # EW sizing: ewobj(COHERENT_EW) matched vs ivobj(MISMATCH) mismatch
    results["coherence_premium"] = {
        "iv_matched_vs_mismatch": paired_block_bootstrap(
            cells["COHERENT_IV"]["clean_returns"], cells["MINVAR_IV"]["clean_returns"], cash),
        "ew_matched_vs_mismatch": paired_block_bootstrap(
            cells["COHERENT_EW"]["clean_returns"], cells["MINVAR_EWOBJ_EW_MISMATCH"]["clean_returns"], cash),
    }
    print("coherence premium done")

    # (d) prod EW vs IV pure sizing
    results["prod_ew_vs_iv_bootstrap"] = paired_block_bootstrap(
        cells["PROD_EW"]["clean_returns"], prod_ret, cash)
    print("prod EW-vs-IV done")

    def strip(cell):
        return {k: v for k, v in cell.items() if not k.endswith("_returns")}

    results["cells"] = {k: strip(v) for k, v in cells.items()}
    results["verdict"] = build_verdict({**results, "cells": results["cells"]})

    with open(OUT_JSON, "w") as f:
        json.dump(results, f, indent=2, default=lambda o: None)
    print("wrote", OUT_JSON)

    write_md(results)
    print("wrote", OUT_MD)
    return results


if __name__ == "__main__":
    main()
