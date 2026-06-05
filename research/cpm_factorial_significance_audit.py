"""Consistency audit: apply the min-var statistical lens to EVERY rung of the
COUPLED SEQUENTIAL benchmark -> production ladder.

Why self-contained: the 2026-05-30 factorial module (factorial_decomposition_2026_05_30.py)
was written against an OLDER production that used a 50/50 min-var PAIR
(cpm_live.min_vol_pair, since removed). Current production (the both-252
verify_anchor, Sharpe 1.1658) uses INVERSE-VOL weighting + STRICT-4 partial-safe.
So we rebuild the SAME ladder ordering (U -> R -> C -> weighting -> fallback) but
target CURRENT production, replicating:
  - all-OFF  == build_dashboard.bench_aaa_tip  (AAA+TIP, ~Sharpe 1.041)
  - all-ON   == cpm_live.compute_target_weights (prod, verify_anchor 1.1658)

REUSES the exact bootstrap/walk-forward machinery used on the min-var studies:
  - cpm_weighting_corr.paired_block_bootstrap (B=2000, block=21, seed=42)
  - cpm_harness.verify_anchor / load_data / run_strategy / cash

For each sequential step (step_i vs step_{i-1}) AND cumulative (step_i vs base):
dSharpe + dCalmar paired-block-bootstrap CI + p(>0), clean decision window, plus a
3-segment walk-forward marginal-dSharpe sign. Classification + BH-FDR. No prod
files touched. JSON written next to this file.
"""
import sys, json, math
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.optimize import minimize

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import research.cpm_harness as H
import cpm_live
from cpm_live import (sig_13612U, best_safe, faber_sma_xs, inv_vol_weights,
                      perf_metrics, CORR_LOOKBACK_DAYS, TOP_K_CANDIDATES)
from research.cpm_weighting_corr import paired_block_bootstrap
from sleeve_vs_benchmark_2026_05_30 import stitch_bil, stitch_agg

B = 2000
CLEAN_START = pd.Timestamp("2008-05-30")

BENCH_AAA_UNIVERSE = ["SPY", "EFA", "EEM", "VNQ", "GLD", "TLT", "DBC"]
PROD_UNIVERSE = ["QQQ", "SPHQ", "EFA", "EEM", "VNQ", "GLD", "TLT", "DBC"]
SAFE_POOL = ["SHV", "IEF"]
BULL_BENCH_SAFE = ["BIL", "AGG"]
BULL_PROD_SAFE = ["SHV", "IEF"]
DEFAULT_CASH = "SHV"


# ========================= CPM parametric weight fn =========================
# Sequential ladder factors, off = pure-AAA setting, on = production setting:
#   T trend filter : OFF none (hold top-half regardless of sign) | ON positive-momentum screen
#   C canary       : 0 none | 1 TIP-only | 2 HYG-OR-TIP any-positive
#   U universe     : SPY-set (off)             | QQQ/SPHQ-set (on)
#   R ranker       : 13612U + top-half (off)   | vol-adj Faber + top-4 (on)
#   W weighting    : continuous min-var 504cov (off) | inverse-vol 252 (on)
#   F fallback     : pure partial-safe (off, single->0.5 safe, else full) | strict-4 (on)
# Common to both ends (fixed, NOT factors): SHV/IEF best-of-safe; top cap=4.
# BASE pure-AAA = T0,C0,U0,R0,W0,F0 (no canary, no trend screen, always invested).
# all-ON (T1,C2,U1,R1,W1,F1) replicates cpm_live.compute_target_weights exactly.

def cpm_wf(close, sig_d, T, C, U, R, W, F):
    universe = PROD_UNIVERSE if U else BENCH_AAA_UNIVERSE
    monthly = close.loc[:sig_d].resample("ME").last()
    safe = best_safe(monthly, sig_d, SAFE_POOL)

    # canary gate (C=0 -> no gate)
    if C != 0:
        canary_assets = ["HYG", "TIP"] if C == 2 else ["TIP"]
        cs = [sig_13612U(monthly[a]) for a in canary_assets if a in monthly.columns]
        cs = [s for s in cs if pd.notna(s)]
        if not cs:
            return {safe: 1.0}
        if sum(1 for s in cs if s > 0) == 0:
            return {safe: 1.0}

    present = [t for t in universe if t in monthly.columns]
    top_half = max(2, math.ceil(len(universe) / 2))   # 7->4, 8->4

    if R:  # vol-adjusted Faber (production)
        faber = faber_sma_xs(monthly)
        avail = [t for t in present if t in faber.index and pd.notna(faber[t])
                 and (sig_d in close.index and pd.notna(close.loc[sig_d].get(t, np.nan)))]
        if not avail:
            return {safe: 1.0}
        dr = close[avail].ffill().pct_change()
        score = {}
        for t in avail:
            v = dr[t].loc[:sig_d].tail(252).std() * np.sqrt(252)
            if pd.isna(v) or v < 1e-9:
                v = 1.0
            score[t] = float(faber[t]) / v
        ranked = pd.Series(score).sort_values(ascending=False)
        top_k = max(2, min(TOP_K_CANDIDATES, len(ranked)))
        top = ranked.iloc[:top_k]
        positive = ([t for t in top.index if faber.get(t, -np.inf) > 0] if T
                    else list(top.index))
    else:  # 13612U (benchmark)
        scores = {t: sig_13612U(monthly[t]) for t in present}
        scores = {t: s for t, s in scores.items() if pd.notna(s)}
        ranked = sorted(scores.items(), key=lambda x: -x[1])
        top = ranked[:top_half]
        positive = ([t for t, s in top if s > 0] if T else [t for t, s in top])

    if len(positive) == 0:
        return {safe: 1.0}
    picks = list(positive)
    n = len(picks)

    # risky-block weights per W
    if W:  # inverse-vol (production)
        risky_w = inv_vol_weights(close.loc[:sig_d], picks, CORR_LOOKBACK_DAYS)
    else:  # continuous min-var, both-252 cov (CORR_LOOKBACK_DAYS, matches min-var studies)
        if n == 1:
            risky_w = {picks[0]: 1.0}
        else:
            daily = close.ffill().pct_change()
            cov = daily.loc[:sig_d].tail(CORR_LOOKBACK_DAYS)[picks].cov() * 252
            def obj(w, Cv=cov.values):
                return float(np.dot(w, np.dot(Cv, w)))
            cons = ({"type": "eq", "fun": lambda w: np.sum(w) - 1.0},)
            bnds = tuple((0.0, 1.0) for _ in range(n))
            r = minimize(obj, np.ones(n) / n, method="SLSQP", bounds=bnds, constraints=cons)
            risky_w = ({picks[i]: float(r.x[i]) for i in range(n)} if r.success
                       else {t: 1.0 / n for t in picks})

    # partial-safe per F
    if F:  # strict-4 (production)
        risky_fraction = min(n, 4) / 4.0
    else:  # benchmark: single positive -> half safe; >=2 fully invested
        risky_fraction = 0.5 if n == 1 else 1.0
    safe_fraction = 1.0 - risky_fraction
    out = {t: w * risky_fraction for t, w in risky_w.items()}
    if safe_fraction > 0:
        out[safe] = out.get(safe, 0.0) + safe_fraction
    return out


# ========================= BULL parametric weight fn =========================
# Factors (off=HAA-Simple, on=BULL): V vol gate, S safe pool, K canary.
def _pick_safe_pool(monthly, pool):
    scores = {}
    for s in pool:
        if s in monthly.columns:
            sc = sig_13612U(monthly[s])
            if pd.notna(sc):
                scores[s] = sc
    return max(scores, key=scores.get) if scores else "SHV"


def bull_wf(close, sig_d, daily_spy, K, V, S):
    monthly = close.loc[:sig_d].resample("ME").last()
    safe = _pick_safe_pool(monthly, BULL_PROD_SAFE if S else BULL_BENCH_SAFE)
    if K:
        cs = [sig_13612U(monthly[a]) for a in ["HYG", "TIP"] if a in monthly.columns]
        cs = [s for s in cs if pd.notna(s)]
        canary_ok = any(s > 0 for s in cs) if cs else False
    else:
        tipm = sig_13612U(monthly["TIP"]) if "TIP" in monthly.columns else float("nan")
        canary_ok = pd.notna(tipm) and tipm > 0
    spym = sig_13612U(monthly["SPY"]) if "SPY" in monthly.columns else float("nan")
    trend_ok = pd.notna(spym) and spym > 0
    if V:
        sub = daily_spy.loc[:sig_d].pct_change().dropna()
        vol_ok = True if len(sub) < 252 else float(sub.tail(60).std()) < float(sub.tail(252).std())
    else:
        vol_ok = True
    return {"SPY": 1.0} if (canary_ok and trend_ok and vol_ok) else {safe: 1.0}


# ========================= stats helpers =========================
def clean(s):
    return s.loc[s.index >= CLEAN_START]


def seg3(r_var, r_base, cash):
    common = r_var.index.intersection(r_base.index)
    rv, rb = r_var.loc[common], r_base.loc[common]
    n = len(common)
    bounds = [0, n // 3, 2 * n // 3, n]
    out = []
    for i in range(3):
        lo, hi = bounds[i], bounds[i + 1]
        d = perf_metrics(rv.iloc[lo:hi], cash)["sharpe"] - perf_metrics(rb.iloc[lo:hi], cash)["sharpe"]
        out.append({"start": str(common[lo].date()), "end": str(common[hi - 1].date()),
                    "dSharpe": float(d)})
    return out


def classify(stat):
    lo, hi, p = stat["ci_lo"], stat["ci_hi"], stat["p_gt0"]
    if (lo > 0 and hi > 0) or (lo < 0 and hi < 0):
        return "SIGNIFICANT"
    return "MARGINAL" if max(p, 1 - p) > 0.85 else "NOISE"


def two_sided_p(p):
    return float(2.0 * min(p, 1.0 - p))


def bh_fdr(pvals, alpha=0.05):
    m = len(pvals)
    order = sorted(range(m), key=lambda i: pvals[i])
    kmax = 0
    for rank, idx in enumerate(order, 1):
        if pvals[idx] <= alpha * rank / m:
            kmax = rank
    reject = [False] * m
    for rank, idx in enumerate(order, 1):
        if rank <= kmax:
            reject[idx] = True
    return reject


def main():
    data = H.load_data()
    anchor = H.verify_anchor(data=data)
    print("CPM ANCHOR OK:", {k: round(float(v), 4) for k, v in anchor.items()
                             if k in ("Sharpe", "MaxDD", "Calmar")})
    cash = data.cash

    panel = data.panel.copy()
    panel["BIL"] = stitch_bil(panel)
    panel["AGG"] = stitch_agg(panel)

    cpm_cols = sorted(set(BENCH_AAA_UNIVERSE + PROD_UNIVERSE + SAFE_POOL + ["HYG", "TIP"])
                      & set(panel.columns))
    cpm_close = panel[cpm_cols]
    bull_cols = sorted(set(["SPY", "HYG", "TIP"] + BULL_BENCH_SAFE + BULL_PROD_SAFE)
                       & set(panel.columns))
    bull_close = panel[bull_cols]
    daily_spy = panel["SPY"]

    # data-bound harness obj for CPM with the extra columns (HYG/TIP/BIL/AGG present in panel)
    data_cpm = data  # run_strategy uses data.panel; ensure panel has needed cols
    # patch data.panel to the augmented panel (adds BIL/AGG; superset of cols)
    data_aug = H.HarnessData(panel=panel, open_df=data.open_df, close_yf=data.close_yf,
                             intraday=data.intraday, overnight=data.overnight, cash=data.cash,
                             clean_start=data.clean_start, ext_start=data.ext_start, end=data.end)

    # ---- CPM ladder: pure-AAA -> +trend -> +TIP -> +HYG/TIP -> +universe
    #                  -> +Faber rank -> +inverse-vol -> +strict-4 PS = CPM ----
    cpm_ladder = [
        ("0. pure-AAA base",         dict(T=0, C=0, U=0, R=0, W=0, F=0)),
        ("1. + trend filter (T)",    dict(T=1, C=0, U=0, R=0, W=0, F=0)),
        ("2. + TIP canary",          dict(T=1, C=1, U=0, R=0, W=0, F=0)),
        ("3. + HYG-or-TIP canary",   dict(T=1, C=2, U=0, R=0, W=0, F=0)),
        ("4. + universe (U)",        dict(T=1, C=2, U=1, R=0, W=0, F=0)),
        ("5. + Faber rank (R)",      dict(T=1, C=2, U=1, R=1, W=0, F=0)),
        ("6. + inverse-vol (W)",     dict(T=1, C=2, U=1, R=1, W=1, F=0)),
        ("7. + strict-4 PS (F)=CPM", dict(T=1, C=2, U=1, R=1, W=1, F=1)),
    ]
    cpm_returns, cpm_labels = [], []
    for label, cfg in cpm_ladder:
        wf = (lambda c=cfg: (lambda panel_, sd: cpm_wf(cpm_close, sd, **c)))()
        r = clean(H.run_strategy(wf, window="ext", data=data_aug))
        cpm_returns.append(r); cpm_labels.append(label)
        m = perf_metrics(r, cash)
        print(f"CPM {label}: sharpe={m['sharpe']:.4f} calmar={m['calmar']:.4f} maxdd={m['max_drawdown']*100:.2f}%")

    # cross-check: all-ON ladder vs true production compute_target_weights
    prod_r = clean(H.run_strategy(cpm_live.compute_target_weights, window="ext", data=data_aug))
    mp = perf_metrics(prod_r, cash); me = perf_metrics(cpm_returns[-1], cash)
    print(f"CHECK all-ON vs compute_target_weights: ladder S={me['sharpe']:.4f} prod S={mp['sharpe']:.4f} "
          f"dS={me['sharpe']-mp['sharpe']:+.4f}")

    # ---- BULL ladder: V -> S -> K ----
    bull_ladder = [
        ("0. HAA-Simple base",     dict(K=0, V=0, S=0)),
        ("1. + vol gate (V)",      dict(K=0, V=1, S=0)),
        ("2. + safe SHV/IEF (S)",  dict(K=0, V=1, S=1)),
        ("3. + HYG-or-TIP (K)=BULL", dict(K=1, V=1, S=1)),
    ]
    bull_returns, bull_labels = [], []
    for label, cfg in bull_ladder:
        wf = (lambda c=cfg: (lambda panel_, sd: bull_wf(bull_close, sd, daily_spy, **c)))()
        r = clean(H.run_strategy(wf, window="ext", data=data_aug))
        bull_returns.append(r); bull_labels.append(label)
        m = perf_metrics(r, cash)
        print(f"BULL {label}: sharpe={m['sharpe']:.4f} calmar={m['calmar']:.4f} maxdd={m['max_drawdown']*100:.2f}%")

    def audit(name, labels, returns):
        steps = []
        base_r = returns[0]
        for i in range(1, len(returns)):
            marg = paired_block_bootstrap(returns[i], returns[i - 1], cash, B=B)
            cum = paired_block_bootstrap(returns[i], base_r, cash, B=B)
            wf = seg3(returns[i], returns[i - 1], cash)
            mS = perf_metrics(returns[i], cash)
            steps.append({
                "step": labels[i], "sharpe": float(mS["sharpe"]),
                "calmar": float(mS["calmar"]), "maxdd": float(mS["max_drawdown"]),
                "marg_dSharpe": marg["dSharpe"], "marg_dCalmar": marg["dCalmar"],
                "cum_dSharpe": cum["dSharpe"], "cum_dCalmar": cum["dCalmar"],
                "class_sharpe": classify(marg["dSharpe"]),
                "class_calmar": classify(marg["dCalmar"]),
                "p2_sharpe": two_sided_p(marg["dSharpe"]["p_gt0"]),
                "p2_calmar": two_sided_p(marg["dCalmar"]["p_gt0"]),
                "wf_seg_dSharpe": wf,
            })
            d = marg["dSharpe"]; c = marg["dCalmar"]
            print(f"\n{name} {labels[i]}")
            print(f"  marg dSharpe {d['mean']:+.4f} [{d['ci_lo']:+.4f},{d['ci_hi']:+.4f}] p>0={d['p_gt0']:.3f} -> {classify(d)}")
            print(f"  marg dCalmar {c['mean']:+.4f} [{c['ci_lo']:+.4f},{c['ci_hi']:+.4f}] p>0={c['p_gt0']:.3f} -> {classify(c)}")
            print(f"  cum  dSharpe {cum['dSharpe']['mean']:+.4f} [{cum['dSharpe']['ci_lo']:+.4f},{cum['dSharpe']['ci_hi']:+.4f}] p>0={cum['dSharpe']['p_gt0']:.3f}")
            print(f"  wf seg dSharpe: {[round(w['dSharpe'],3) for w in wf]}")
        full = paired_block_bootstrap(returns[-1], returns[0], cash, B=B)
        return {"steps": steps, "full_cumulative": {
            "dSharpe": full["dSharpe"], "dCalmar": full["dCalmar"],
            "class_sharpe": classify(full["dSharpe"]), "class_calmar": classify(full["dCalmar"])}}

    cpm_audit = audit("CPM", cpm_labels, cpm_returns)
    bull_audit = audit("BULL", bull_labels, bull_returns)

    # ---- BH-FDR across all per-step marginal dSharpe p-values ----
    fdr_items = []
    for sleeve, aud in [("CPM", cpm_audit), ("BULL", bull_audit)]:
        for st in aud["steps"]:
            fdr_items.append((f"{sleeve} {st['step']} dSharpe", st["p2_sharpe"]))
    pvals = [p for _, p in fdr_items]
    rej = bh_fdr(pvals, 0.05)
    fdr = [{"item": fdr_items[i][0], "p2": fdr_items[i][1], "bh_reject": bool(rej[i])}
           for i in range(len(fdr_items))]

    minvar_ref = {
        "label": "min-var 3-of-4 (COHERENT-EW) vs prod (cpm_minvar_coherence_findings.md)",
        "dSharpe": {"mean": 0.1057, "ci_lo": 0.0017, "ci_hi": 0.2126, "p_gt0": 0.977},
        "dCalmar": {"mean": 0.1334, "ci_lo": -0.0911, "ci_hi": 0.3982},
        "class_sharpe": "SIGNIFICANT", "p2_sharpe": two_sided_p(0.977),
    }

    out = {"anchor": {k: float(v) for k, v in anchor.items()}, "B": B,
           "cpm": cpm_audit, "bull": bull_audit, "fdr": fdr, "minvar_ref": minvar_ref,
           "ladder_endpoint_vs_prod_dSharpe": float(me["sharpe"] - mp["sharpe"])}
    Path(__file__).with_suffix(".json").write_text(json.dumps(out, indent=2, default=float))

    print("\n=== BH-FDR (alpha=0.05) across per-step marginal dSharpe (CPM+BULL) ===")
    for f in sorted(fdr, key=lambda x: x["p2"]):
        print(f"  {f['item']}: p2={f['p2']:.3f} reject={f['bh_reject']}")
    print("\nDONE -> json written")


if __name__ == "__main__":
    main()
