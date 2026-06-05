# -*- coding: utf-8 -*-
"""CPM SLEEVE: Varadi MCA (min-correlation) 3-of-4 selection vs production
MIN-VARIANCE 3-of-4 selection. Single a-priori swap at the n_pos=4 trigger;
everything else (EW risky block, canary/ranker/safe/breadth, STRICT-4 partial
safe fallback, T+1 MOO exec, 10 bps/side, both-252 lookback) byte-identical.

HYPOTHESIS (from Optimum3): min-variance favors LOW-VOL assets (bonds/gold) so
it can de-tilt CPM away from equities in bull markets; MIN-CORRELATION optimizes
pairwise dependence regardless of vol so it keeps high-momentum winners while
still diversifying -> better bull participation / CAGR / Sharpe. Risk = more
turnover (correlation reshuffling), per Optimum3's poor tax profile.

SLEEVE-ONLY (blend skipped per scope trim). Point-estimates only. Read-only re
production code (monkeypatch of cpm_live._min_var_subset). Writes only research/.
No commit.
"""
from __future__ import annotations

import json
import sys
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import cpm_live
from cpm_live import _ret_window, perf_metrics, compute_target_weights, CORR_LOOKBACK_DAYS

from research import cpm_harness as H
from research.cpm_ndx_minvar_cvar import (
    sortino_ann, cvar_ratio_ann, CRISES,
)

# Bull-market participation windows (a-priori, equity-led regimes).
BULL_WINDOWS = {
    "bull_2013_2019": ("2013-01-01", "2019-12-31"),
    "bull_2023_2025": ("2023-01-01", "2025-06-30"),
}

# Production min-variance subset, captured before any monkeypatch.
_PROD_MIN_VAR_SUBSET = cpm_live._min_var_subset


def min_corr_subset(close, sig_d, candidates, lookback, m):
    """Varadi MCA: p-of-candidates subset with the LOWEST AVERAGE
    PAIRWISE CORRELATION (avg of the m-choose-2 pairwise corrs) over the same
    lookback. Fallback conditions byte-identical to cpm_live._min_var_subset;
    only the objective (avg pairwise corr) and the matrix (corr vs cov) differ.
    """
    if len(candidates) <= m:
        return list(candidates)
    rets = _ret_window(close.loc[:sig_d], candidates, lookback)
    if len(rets) < lookback:
        return list(candidates)
    corr = rets.corr()
    if corr.isna().any().any():
        return list(candidates)
    iu = np.triu_indices(m, k=1)
    best, best_v = None, np.inf
    for combo in combinations(candidates, m):
        sub = corr.loc[list(combo), list(combo)].values
        avg_c = float(sub[iu].mean())
        if avg_c < best_v:
            best_v, best = avg_c, combo
    return list(best) if best else list(candidates)


# ---------- metrics ----------

def full_metrics(ret, cash):
    m = perf_metrics(ret, cash)
    x = ret.values
    return {
        "Sharpe": m.get("sharpe"), "Sortino": sortino_ann(x),
        "CVaR_ratio": cvar_ratio_ann(x), "Calmar": m.get("calmar"),
        "Martin": m.get("martin"), "MaxDD": m.get("max_drawdown"),
        "CAGR": m.get("cagr"), "vol": m.get("vol"),
    }


def window_full(ret, a, b, cash):
    w = ret.loc[(ret.index >= pd.Timestamp(a)) & (ret.index <= pd.Timestamp(b))]
    if len(w) < 5:
        return None
    return full_metrics(w, cash)


def crisis_metrics(ret):
    out = {}
    for nm, (a, b) in CRISES.items():
        w = ret.loc[(ret.index >= pd.Timestamp(a)) & (ret.index <= pd.Timestamp(b))]
        if len(w) < 5:
            out[nm] = None
            continue
        x = w.values
        m = perf_metrics(w, None)
        out[nm] = {"Sharpe": m.get("sharpe"), "Sortino": sortino_ann(x),
                   "MaxDD": m.get("max_drawdown"), "CAGR": m.get("cagr")}
    return out


# ---------- weight-sequence diagnostics ----------

def signal_dates(panel, start, end):
    midx = (pd.DataFrame({"x": 1}, index=panel.index)
            .groupby(pd.Grouper(freq="ME")).tail(1))
    return midx.index[(midx.index >= start) & (midx.index <= end)].tolist()


def weight_sequence(close, sigs):
    """Target weights at each signal date through compute_target_weights with
    whatever _min_var_subset is currently bound. Returns list of dicts."""
    seq = []
    for sd in sigs:
        w, basket, regime, safe = compute_target_weights(close, sd)
        seq.append({"sig_d": sd, "weights": w, "basket": basket, "regime": regime})
    return seq


def annual_turnover(seq):
    """One-way annualized turnover (sum|dw|/2 averaged per rebalance * 12)."""
    if len(seq) < 2:
        return float("nan")
    prev, tot, n = {}, 0.0, 0
    for e in seq:
        w = e["weights"]
        keys = set(w) | set(prev)
        tot += 0.5 * sum(abs(w.get(k, 0.0) - prev.get(k, 0.0)) for k in keys)
        n += 1
        prev = w
    return tot / n * 12.0 if n else float("nan")


def selection_divergence(close, sigs):
    """For each signal date, record candidate pool and BOTH min-var and min-corr
    triplets. The subset selector is only invoked at n_pos==4, so we replicate
    the n_pos==4 detection by checking when len(positive_picks)==4. We reuse the
    production weight path with an instrumented selector to capture candidates.
    """
    records = []

    captured = {}

    def instrumented(close_, sig_d, candidates, lookback, m):
        # n_pos==4 only path. Record candidates + both picks.
        mv = _PROD_MIN_VAR_SUBSET(close_, sig_d, candidates, lookback, m)
        mc = min_corr_subset(close_, sig_d, candidates, lookback, m)
        captured[sig_d] = {
            "candidates": list(candidates),
            "minvar": sorted(mv), "mincorr": sorted(mc),
        }
        return mv  # behave as production baseline

    orig = cpm_live._min_var_subset
    cpm_live._min_var_subset = instrumented
    try:
        for sd in sigs:
            captured.pop(sd, None)
            compute_target_weights(close, sd)
            if sd in captured:
                c = captured[sd]
                same = c["minvar"] == c["mincorr"]
                inter = len(set(c["minvar"]) & set(c["mincorr"]))
                union = len(set(c["minvar"]) | set(c["mincorr"]))
                records.append({
                    "sig_d": str(sd.date()),
                    "candidates": c["candidates"],
                    "minvar": c["minvar"], "mincorr": c["mincorr"],
                    "same": same, "jaccard": inter / union if union else 1.0,
                })
    finally:
        cpm_live._min_var_subset = orig
    return records


# ---------- run ----------

def run():
    data = H.load_data()
    cash = data.cash
    cols = sorted(set(cpm_live.RISKY_UNIVERSE + cpm_live.SAFE_POOL
                      + cpm_live.CANARY_ASSETS + [cpm_live.DEFAULT_CASH])
                  & set(data.panel.columns))
    close = data.panel[cols]

    # Anchor gate (baseline = production min-var through harness).
    anchor = H.verify_anchor(data=data)
    print(f"ANCHOR OK: Sharpe={anchor['Sharpe']:.6f} MaxDD={anchor['MaxDD']:.6f} "
          f"Calmar={anchor['Calmar']:.6f}", file=sys.stderr)

    out = {
        "anchor": anchor,
        "windows": {
            "clean": [str(data.clean_start.date()), str(data.end.date())],
            "ext": [str(data.ext_start.date()), str(data.end.date())],
            "bull": {k: list(v) for k, v in BULL_WINDOWS.items()},
            "crises": {k: list(v) for k, v in CRISES.items()},
        },
        "config": {"CORR_LOOKBACK_DAYS": CORR_LOOKBACK_DAYS, "cost_bps": cpm_live.COST_BPS_PER_SIDE},
        "sleeve": {},
        "diagnostics": {},
    }

    # --- BASELINE (production min-var) ---
    cpm_live._min_var_subset = _PROD_MIN_VAR_SUBSET
    ret_mv_clean = H.run_strategy(compute_target_weights, window="clean", data=data)
    ret_mv_ext = H.run_strategy(compute_target_weights, window="ext", data=data)

    # --- MCA (min-correlation) ---
    cpm_live._min_var_subset = min_corr_subset
    ret_mc_clean = H.run_strategy(compute_target_weights, window="clean", data=data)
    ret_mc_ext = H.run_strategy(compute_target_weights, window="ext", data=data)
    cpm_live._min_var_subset = _PROD_MIN_VAR_SUBSET

    for label, rc, re in [("minvar", ret_mv_clean, ret_mv_ext),
                          ("mca", ret_mc_clean, ret_mc_ext)]:
        out["sleeve"][label] = {
            "clean": full_metrics(rc, cash),
            "ext": full_metrics(re, cash),
            "crisis_ext": crisis_metrics(re),
            "bull_clean": {k: window_full(rc, *v, cash) for k, v in BULL_WINDOWS.items()},
        }

    # --- turnover (clean + ext) ---
    sigs_clean = signal_dates(close, data.clean_start, data.end)
    sigs_ext = signal_dates(close, data.ext_start, data.end)

    cpm_live._min_var_subset = _PROD_MIN_VAR_SUBSET
    seq_mv_clean = weight_sequence(close, sigs_clean)
    seq_mv_ext = weight_sequence(close, sigs_ext)
    cpm_live._min_var_subset = min_corr_subset
    seq_mc_clean = weight_sequence(close, sigs_clean)
    seq_mc_ext = weight_sequence(close, sigs_ext)
    cpm_live._min_var_subset = _PROD_MIN_VAR_SUBSET

    out["sleeve"]["minvar"]["turnover_ann_clean"] = annual_turnover(seq_mv_clean)
    out["sleeve"]["minvar"]["turnover_ann_ext"] = annual_turnover(seq_mv_ext)
    out["sleeve"]["mca"]["turnover_ann_clean"] = annual_turnover(seq_mc_clean)
    out["sleeve"]["mca"]["turnover_ann_ext"] = annual_turnover(seq_mc_ext)

    # --- selection divergence + n_pos=4 frequency ---
    for wlabel, sigs in [("clean", sigs_clean), ("ext", sigs_ext)]:
        recs = selection_divergence(close, sigs)
        total = len(sigs)
        active = len(recs)
        diff = sum(1 for r in recs if not r["same"])
        avg_j = float(np.mean([r["jaccard"] for r in recs])) if recs else float("nan")
        out["diagnostics"][wlabel] = {
            "total_rebalances": total,
            "npos4_active": active,
            "npos4_freq": active / total if total else float("nan"),
            "diverged": diff,
            "divergence_rate": diff / active if active else float("nan"),
            "avg_jaccard": avg_j,
            "records": recs,
        }

    return out


def main():
    out = run()
    jp = ROOT / "research" / "cpm_mca_vs_minvar_findings.json"
    jp.write_text(json.dumps(out, indent=2, default=str))

    def row(lbl, m):
        if m is None:
            return f"  {lbl:<16} n/a"
        return (f"  {lbl:<16} Sh={m['Sharpe']:.4f} Sort={m['Sortino']:.4f} "
                f"CVaR={m['CVaR_ratio']:.4f} Cal={m['Calmar']:.4f} Mar={m['Martin']:.4f} "
                f"MaxDD={m['MaxDD']:.4f} CAGR={m['CAGR']:.4f} vol={m['vol']:.4f}")

    print("\n=== CPM SLEEVE: MIN-VAR (prod) vs MCA (min-corr) ===")
    for win in ("clean", "ext"):
        print(f"\n[{win}]")
        for lbl in ("minvar", "mca"):
            print(row(f"{lbl}", out["sleeve"][lbl][win]))
        print(f"  turnover_ann minvar={out['sleeve']['minvar']['turnover_ann_'+win]:.3f} "
              f"mca={out['sleeve']['mca']['turnover_ann_'+win]:.3f}")
        d = out["diagnostics"][win]
        print(f"  n_pos=4: {d['npos4_active']}/{d['total_rebalances']} "
              f"({d['npos4_freq']*100:.1f}%) | diverged {d['diverged']}/{d['npos4_active']} "
              f"({d['divergence_rate']*100:.1f}%) | avg_jaccard {d['avg_jaccard']:.3f}")

    print("\n[bull windows, clean]")
    for lbl in ("minvar", "mca"):
        print(f" {lbl}:")
        for k in BULL_WINDOWS:
            print(row(f"  {k}", out["sleeve"][lbl]["bull_clean"][k]))

    print("\n[crisis, ext]")
    for nm in CRISES:
        print(f" {nm}:")
        for lbl in ("minvar", "mca"):
            m = out["sleeve"][lbl]["crisis_ext"][nm]
            if m is None:
                print(f"   {lbl:<8} n/a")
            else:
                print(f"   {lbl:<8} Sh={m['Sharpe']:.3f} Sort={m['Sortino']:.3f} "
                      f"MaxDD={m['MaxDD']:.4f} CAGR={m['CAGR']:.4f}")

    print(f"\nwrote {jp}")


if __name__ == "__main__":
    main()
