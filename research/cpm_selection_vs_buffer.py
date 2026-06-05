"""SELECTION vs PERMANENT SAFE BUFFER decomposition.

Throwaway research. Read-only re production. No production files changed; no commit.

Decomposes two levers prior min-var variants conflated:
  (1) min-var SELECTION  -- which 3 names (min-var 3-of-4 vs prod top-4 rank).
  (2) PERMANENT SAFE BUFFER b -- a Permanent-Portfolio-style floor allocation to
      the timed safe (best-of SHV/IEF by 13612U), held EVEN at full breadth,
      ON TOP of prod's existing strict-4 breadth scaling.

Buffer composition (stated exactly)
-----------------------------------
prod_risky_fraction = min(n_pos, 4) / 4   (strict-4 breadth scaling; n_pos = count
  of positive-faber names within the top-4 rank pool -- byte-identical to prod).
effective_risky    = (1 - b) * prod_risky_fraction
safe_fraction      = 1 - effective_risky
risky block (selected names, inv-vol sample 252) is scaled by effective_risky;
the permanent + breadth safe goes entirely to the timed best_safe (SHV/IEF).

At full breadth (n_pos>=4 -> prod_risky=1.0): effective_risky=(1-b), safe=b. EXACT
PP-style permanent floor. Below full breadth prod's strict-4 de-risk compounds
multiplicatively with the buffer.

GATE: rank selection (top-4) with b=0 -> effective_risky=prod_risky_fraction,
inv-vol over positives -> reproduces production anchor (Sharpe 1.1658).

Everything else byte-identical to prod: universe, canary HYG-or-TIP any_positive,
vol-adj Faber rank, both-252, inv-vol sizing, mooex T+1, 10 bps/side.

Run: .venv/bin/python -m research.cpm_selection_vs_buffer
Out: research/cpm_selection_vs_buffer_findings.json
"""

from __future__ import annotations

import json
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
    _risky_weights, _min_var_subset, CRISES, _sub_metrics, annualized_turnover,
)

OUT = Path(__file__).resolve().parent / "cpm_selection_vs_buffer_findings.json"


# ---------------- buffer-aware, selection-aware weight fn ----------------
def make_wf(selection="rank", buffer_b=0.0, hold_n=3, lookback=None):
    """selection in {rank, minvar}. buffer_b = permanent safe floor.
    rank  -> hold all positive top-4 (prod). minvar -> hold min-var hold_n subset.
    """
    lb = lookback or cpm_live.CORR_LOOKBACK_DAYS
    b = float(buffer_b)

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

        n_pos = len(positive)  # strict-4 breadth counter (prod semantics)
        prod_risky = min(n_pos, 4) / 4.0

        # selection: which names to hold
        if selection == "rank":
            picks = list(positive)
        elif selection == "minvar":
            if n_pos > hold_n:
                picks = _min_var_subset(close_panel, sig_d, list(positive), lb, hold_n)
            else:
                picks = list(positive)
        else:
            raise ValueError(selection)

        # permanent buffer composes multiplicatively on top of breadth scaling
        effective_risky = (1.0 - b) * prod_risky
        safe_fraction = 1.0 - effective_risky

        rw = _risky_weights(close_panel, sig_d, picks, "invvol", "sample", lb)
        out = {t: w * effective_risky for t, w in rw.items()}
        if safe_fraction > 0:
            out[safe] = out.get(safe, 0.0) + safe_fraction
        return out

    return wf


# ---------------- metrics incl Sortino (path-independent) ----------------
def _sortino(returns, mar=0.0):
    r = returns.dropna()
    if len(r) < 5:
        return float("nan")
    downside = r[r < mar] - mar
    dd = np.sqrt((downside ** 2).sum() / len(r)) * np.sqrt(252)
    if dd <= 0:
        return float("nan")
    return float((r.mean() - mar) * 252 / dd)


def full_metrics(returns, cash):
    m = cpm_live.perf_metrics(returns, cash)
    return {
        "Sharpe": m.get("sharpe"),
        "Sortino": _sortino(returns),
        "Calmar": m.get("calmar"),
        "Martin": m.get("martin"),
        "MaxDD": m.get("max_drawdown"),
        "CAGR": m.get("cagr"),
        "vol": m.get("vol"),
    }


def run_cell(weight_fn, data, label):
    out = {}
    for win in ("clean", "ext"):
        r = H.run_strategy(weight_fn, window=win, data=data)
        out[win] = full_metrics(r, data.cash)
        out[win + "_returns"] = r
    rext = out["ext_returns"]
    out["crises"] = {}
    for name, (a, b) in CRISES.items():
        sm = _sub_metrics(rext, data.cash, a, b)
        if sm is not None:
            sub = rext.loc[(rext.index >= pd.Timestamp(a)) & (rext.index <= pd.Timestamp(b))]
            sm["Sortino"] = _sortino(sub)
            sm["vol"] = sub.std(ddof=0) * np.sqrt(252)
        out["crises"][name] = sm
    out["turnover_ann"] = annualized_turnover(weight_fn, data)
    out["label"] = label
    return out


# ---------------- paired block bootstrap with Sharpe AND Sortino ----------------
def paired_block_bootstrap_ss(ra, rb, cash, B=2000, block=21, seed=42):
    """Mirror cpm_weighting_corr.paired_block_bootstrap (same B/block/seed/resampling)
    but report dSharpe AND dSortino. ra - rb (variant - base)."""
    common = ra.index.intersection(rb.index)
    a = ra.loc[common].values
    b = rb.loc[common].values
    n = len(a)
    rng = np.random.default_rng(seed)
    nb = int(np.ceil(n / block))

    def stats(x):
        s = pd.Series(x, index=common)
        m = cpm_live.perf_metrics(s, cash)
        return m.get("sharpe"), _sortino(s)

    dS, dSo = [], []
    for _ in range(B):
        starts = rng.integers(0, n, size=nb)
        idx = np.concatenate([np.arange(s, s + block) % n for s in starts])[:n]
        sA, soA = stats(a[idx])
        sB, soB = stats(b[idx])
        dS.append(sA - sB)
        dSo.append(soA - soB)

    def summ(arr):
        arr = np.array(arr, dtype=float)
        arr = arr[np.isfinite(arr)]
        return {
            "mean": float(arr.mean()),
            "ci_lo": float(np.percentile(arr, 2.5)),
            "ci_hi": float(np.percentile(arr, 97.5)),
            "p_gt0": float((arr > 0).mean()),
        }
    return {"dSharpe": summ(dS), "dSortino": summ(dSo)}


def main():
    data = H.load_data()
    anchor = H.verify_anchor(data=data)
    print("ANCHOR OK:", {k: round(float(v), 4) for k, v in anchor.items() if k in ("Sharpe", "MaxDD", "Calmar")})
    results = {"anchor": {k: float(v) for k, v in anchor.items()}}

    # ---- 2x2: selection {rank(prod), minvar 3of4} x buffer {0, 0.25} ----
    cells = {}
    cfgs = [
        ("prod_b0",        "rank",   0.00),  # PROD anchor gate
        ("prod_b25",       "rank",   0.25),  # BUFFER lever isolated
        ("minvar_b0",      "minvar", 0.00),  # variant A: SELECTION lever isolated
        ("minvar_b25",     "minvar", 0.25),  # variant B: both levers
    ]
    # ---- buffer sweep on prod selection ----
    for bb in (0.00, 0.10, 0.25, 0.40):
        key = f"prod_b{int(round(bb*100)):02d}"
        if key not in dict((c[0], None) for c in cfgs):
            cfgs.append((key, "rank", bb))
    # dedupe preserving order
    seen = set()
    cfgs2 = []
    for c in cfgs:
        if c[0] in seen:
            continue
        seen.add(c[0])
        cfgs2.append(c)
    cfgs = cfgs2

    for key, sel, bb in cfgs:
        wf = make_wf(selection=sel, buffer_b=bb, hold_n=3)
        cells[key] = run_cell(wf, data, key)
        print(f"done {key:14s} clean Sh {cells[key]['clean']['Sharpe']:.4f} "
              f"So {cells[key]['clean']['Sortino']:.4f} "
              f"CAGR {cells[key]['clean']['CAGR']:.4f} vol {cells[key]['clean']['vol']:.4f} "
              f"MaxDD {cells[key]['clean']['MaxDD']:.4f} turn {cells[key]['turnover_ann']:.3f}")

    # GATE check: prod_b0 must reproduce anchor
    g = cells["prod_b0"]["clean"]
    assert abs(g["Sharpe"] - 1.1658) < 5e-4, f"GATE FAIL prod_b0 Sharpe={g['Sharpe']}"
    print("GATE OK: prod_b0 Sharpe", round(g["Sharpe"], 4))

    # ---- bootstrap: SELECTION main effect (prod -> minvar at b=0) ----
    #      and BUFFER main effect (b=0 -> b=0.25 at prod selection) ----
    base = cells["prod_b0"]["clean_returns"]
    results["bootstrap"] = {}
    results["bootstrap"]["selection_main_effect_b0"] = paired_block_bootstrap_ss(
        cells["minvar_b0"]["clean_returns"], base, data.cash)
    results["bootstrap"]["buffer_main_effect_prodsel"] = paired_block_bootstrap_ss(
        cells["prod_b25"]["clean_returns"], base, data.cash)
    # interaction helpers: buffer on minvar; selection at b=0.25
    results["bootstrap"]["buffer_on_minvar"] = paired_block_bootstrap_ss(
        cells["minvar_b25"]["clean_returns"], cells["minvar_b0"]["clean_returns"], data.cash)
    results["bootstrap"]["selection_at_b25"] = paired_block_bootstrap_ss(
        cells["minvar_b25"]["clean_returns"], cells["prod_b25"]["clean_returns"], data.cash)
    results["bootstrap"]["both_vs_prod"] = paired_block_bootstrap_ss(
        cells["minvar_b25"]["clean_returns"], base, data.cash)
    print("bootstrap done")

    def strip(cell):
        return {k: v for k, v in cell.items() if not k.endswith("_returns")}
    results["cells"] = {k: strip(v) for k, v in cells.items()}

    with open(OUT, "w") as f:
        json.dump(results, f, indent=2, default=lambda o: None)
    print("wrote", OUT)
    return results


if __name__ == "__main__":
    main()
