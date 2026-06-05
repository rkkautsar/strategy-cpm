# -*- coding: utf-8 -*-
"""HAA->CPM 2^5 coupled factorial STATISTICAL-SIGNIFICANCE audit (both-252).

Role: analyst (read-only re production; writes only research/ artifacts; no
commit). Question: are the ADOPTED HAA->CPM production factors (T,V,W,C,U)
individually significant or marginal -- under the SAME lens applied to the
min-var 3-of-4 selection (clean window, B=2000 paired block bootstrap, dSharpe
CI + p(>0))? If the adopted factors are also marginal, "marginal" is not a fair
disqualifier for min-var 3-of-4.

Reuses the COUPLED HAA<->CPM factorial machinery from
research/cpm_haa_coupled_factorial.py (param_wf): all-OFF == canonical HAA
(0.8670 clean), all-ON == production CPM both-252 (1.1658 clean). This script
is ALREADY both-252 (W uses CORR_LOOKBACK_DAYS=252) -- no window fix needed.

GATES (all must pass before analysis):
  G0 cpm_harness.verify_anchor() -> production both-252 1.1658 (engine sanity).
  G1 all-OFF (00000) clean Sharpe == HAA 0.8670.
  G2 all-ON  (11111) clean Sharpe == prod 1.1658 (NOT 504d's 1.1910).

Bootstrap: research.cpm_weighting_corr.paired_block_bootstrap
(B=2000, block=21, seed=42) -- byte-identical to the min-var studies.
Clean window (2008-05-30..end) is the decision lens. Single in-sample.

Run: .venv/bin/python research/cpm_haa_factorial_significance_audit.py
Out: research/cpm_haa_factorial_significance_audit.json
     (findings .md written by the analyst)
"""
from __future__ import annotations

import sys
import json
import itertools
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import cpm_live
from cpm_live import perf_metrics, load_panel
from research import cpm_harness as HARNESS
from research.cpm_weighting_corr import paired_block_bootstrap, make_weight_fn
from research.cpm_bootstrap_multimetric import paired_block_bootstrap_mm

# the coupled HAA<->CPM machinery (gated to HAA 0.8670 / CPM 1.1658)
from research.cpm_haa_coupled_factorial import (
    param_wf, run_series, FACTORS, FACTOR_LABEL,
    HAA_UNIVERSE, CPM_UNIVERSE, SAFE,
    ANCHOR_CLEAN, HAA_ANCHOR_CLEAN,
)
import exec_lag_moo_validation_2026_05_30 as H

OUT = Path(__file__).resolve().parent / "cpm_haa_factorial_significance_audit.json"

PROD_ANCHOR_SHARPE = 1.1658   # all-ON, both-252
HAA_ANCHOR_SHARPE = 0.8670    # all-OFF
IS_504_SHARPE = 1.1910        # tripwire: if all-ON hits this, harness is 504d

# ladder order matching memo 5.9: trend -> vol-adj -> weighting -> canary -> universe
LADDER_ORDER = ["T", "V", "W", "C", "U"]

# min-var 3-of-4 reference (prior min-var studies, same lens).
MINVAR_3OF4 = {
    "label": "min-var 3-of-4 (vs prod)",
    "dSharpe_mean": 0.106,
    "ci_lo": 0.002,
    "ci_hi": 0.213,
    "p_gt0": 0.977,
}


def classify(boot):
    """SIG / MARGINAL / NOISE from a paired-bootstrap dSharpe block."""
    lo, hi, p = boot["ci_lo"], boot["ci_hi"], boot["p_gt0"]
    if lo > 0 or hi < 0:
        return "SIGNIFICANT"
    if p >= 0.85 or p <= 0.15:
        return "MARGINAL"
    return "NOISE"


def bh_fdr(pvals, alpha=0.05):
    """Benjamini-Hochberg on one-sided p = P(effect <= 0) = 1 - p_gt0."""
    items = sorted(pvals.items(), key=lambda kv: kv[1])
    m = len(items)
    kmax = 0
    for i, (name, p) in enumerate(items, start=1):
        if p <= alpha * i / m:
            kmax = i
    survive = {name: (i <= kmax) for i, (name, p) in enumerate(items, start=1)}
    return {"alpha": alpha, "ordered": items, "survive": survive,
            "n_survive": sum(survive.values())}


def walk_forward_3seg(base_ret, var_ret, cash):
    """var - base dSharpe/dCalmar over 3 sequential clean segments."""
    common = base_ret.index.intersection(var_ret.index)
    b = base_ret.loc[common]
    v = var_ret.loc[common]
    n = len(common)
    bounds = [0, n // 3, 2 * n // 3, n]
    segs = []
    for i in range(3):
        lo, hi = bounds[i], bounds[i + 1]
        mb = perf_metrics(b.iloc[lo:hi], cash)
        mv = perf_metrics(v.iloc[lo:hi], cash)
        segs.append({
            "start": str(common[lo].date()), "end": str(common[hi - 1].date()),
            "dSharpe": mv.get("sharpe") - mb.get("sharpe"),
            "dCalmar": mv.get("calmar") - mb.get("calmar"),
        })
    return segs


def main():
    end = pd.Timestamp("2026-05-22")
    ext_start = pd.Timestamp("1999-03-10")
    clean_start = pd.Timestamp("2008-05-30")

    # ---- GATE 0: engine anchor through canonical harness ----
    hdata = HARNESS.load_data()
    anchor = HARNESS.verify_anchor(data=hdata)
    print("G0 verify_anchor OK:",
          {k: round(float(anchor[k]), 4) for k in ("Sharpe", "MaxDD", "Calmar")})
    assert abs(float(anchor["Sharpe"]) - PROD_ANCHOR_SHARPE) < 5e-4, "verify_anchor sharpe drift"
    assert cpm_live.CORR_LOOKBACK_DAYS == 252, "NOT both-252"

    # ---- load panel + OHLC (same path as cpm_haa_coupled_factorial.main) ----
    panel = load_panel(start=ext_start, end=end)
    end = min(end, panel.index[-1])
    cash = panel["SHV"].ffill().pct_change().dropna()

    open_df, close_yf = H.load_open_close()
    intraday = (close_yf / open_df - 1.0).reindex(panel.index)
    overnight = (open_df / close_yf.shift(1) - 1.0).reindex(panel.index)

    cols = sorted(set(HAA_UNIVERSE + CPM_UNIVERSE + SAFE + ["HYG", "TIP"]) & set(panel.columns))
    close = panel[cols]
    daily = close.ffill().pct_change()

    # ---- run all 32 cells; keep CLEAN-window return series ----
    cells = {}
    for cfg in itertools.product([0, 1], repeat=5):
        wf = lambda sd, b=cfg: param_wf(close, sd, *b)
        ser = run_series(close, daily, intraday, overnight, wf, ext_start, end)
        rclean = ser.loc[(ser.index >= clean_start) & (ser.index <= end)]
        m = perf_metrics(rclean, cash)
        cells[cfg] = {"ret": rclean, "sharpe": m.get("sharpe"),
                      "calmar": m.get("calmar"), "martin": m.get("martin"),
                      "maxdd": m.get("max_drawdown")}
    print(f"ran {len(cells)} cells")

    alloff = (0, 0, 0, 0, 0)
    allon = (1, 1, 1, 1, 1)
    off_sh = cells[alloff]["sharpe"]
    on_sh = cells[allon]["sharpe"]

    # ---- GATE 1/2 ----
    gate_off = abs(off_sh - HAA_ANCHOR_SHARPE) < 5e-3
    gate_on = abs(on_sh - PROD_ANCHOR_SHARPE) < 5e-3
    is_504 = abs(on_sh - IS_504_SHARPE) < 5e-3
    print(f"G1 all-OFF sharpe={off_sh:.4f} (target {HAA_ANCHOR_SHARPE}) -> {gate_off}")
    print(f"G2 all-ON  sharpe={on_sh:.4f} (target {PROD_ANCHOR_SHARPE}) -> {gate_on}"
          + ("  [STILL 504d!]" if is_504 else ""))
    if is_504:
        raise SystemExit("ABORT: all-ON == 1.1910 -> harness 504d. Should not happen.")
    if not (gate_off and gate_on):
        raise SystemExit("ABORT: anchor gate failed.")

    prod_ret = cells[allon]["ret"]
    haa_ret = cells[alloff]["ret"]

    # ===== Per-factor LEAVE-ONE-OUT at production corner (single-swap vs prod) =====
    # var = production (all-ON); base = production with ONE factor OFF.
    # dSharpe = Sharpe(prod) - Sharpe(prod\X): marginal contribution of X AT prod.
    # Single change vs prod -> directly comparable to min-var 3-of-4.
    loo = {}
    for i, fn in enumerate(FACTORS):
        base_cfg = tuple(0 if j == i else 1 for j in range(5))
        base_ret = cells[base_cfg]["ret"]
        # multi-metric paired block bootstrap (same B/block/seed); classify on
        # path-INDEPENDENT Sharpe + Sortino (+CVaR). Calmar/Martin = point context.
        boot = paired_block_bootstrap_mm(prod_ret, base_ret, cash)  # var=prod, base=prod\X
        wf = walk_forward_3seg(base_ret, prod_ret, cash)
        cbm = {
            "Sharpe": classify(boot["dSharpe"]),
            "Sortino": classify(boot["dSortino"]),
            "CVaR": classify(boot["dCVaR"]),
        }
        loo[fn] = {
            "label": FACTOR_LABEL[fn],
            "base_cfg": "".join(map(str, base_cfg)),
            "point_dSharpe": cells[allon]["sharpe"] - cells[base_cfg]["sharpe"],
            "point_dCalmar": cells[allon]["calmar"] - cells[base_cfg]["calmar"],
            "point_dMartin": cells[allon]["martin"] - cells[base_cfg]["martin"],
            "boot": boot,
            "walk_forward": wf,
            "wf_sign_positive": sum(1 for s in wf if s["dSharpe"] > 0),
            "class_by_metric": cbm,
            "classification": cbm["Sharpe"],
        }
        print(f"LOO {fn}: dS={loo[fn]['point_dSharpe']:+.4f} "
              f"Sh={cbm['Sharpe'][:4]}/So[{boot['dSortino']['ci_lo']:+.3f},"
              f"{boot['dSortino']['ci_hi']:+.3f}]p={boot['dSortino']['p_gt0']:.2f}={cbm['Sortino'][:4]}/"
              f"CV={cbm['CVaR'][:4]} wf+={loo[fn]['wf_sign_positive']}/3")

    # ===== Background-averaged main effects =====
    # point estimate (grid): avg over 16 backgrounds of (Sharpe_on - Sharpe_off).
    # CI: paired bootstrap on the averaged-ON vs averaged-OFF return series.
    main_eff = {}
    half = 2 ** 4
    for i, fn in enumerate(FACTORS):
        dS = sum((1 if cfg[i] else -1) * cells[cfg]["sharpe"] for cfg in cells) / half
        dC = sum((1 if cfg[i] else -1) * cells[cfg]["calmar"] for cfg in cells) / half
        on_cells = [cfg for cfg in cells if cfg[i] == 1]
        off_cells = [cfg for cfg in cells if cfg[i] == 0]
        idx = prod_ret.index
        avg_on = sum(cells[c]["ret"].reindex(idx).fillna(0.0) for c in on_cells) / len(on_cells)
        avg_off = sum(cells[c]["ret"].reindex(idx).fillna(0.0) for c in off_cells) / len(off_cells)
        boot = paired_block_bootstrap(avg_on, avg_off, cash)
        main_eff[fn] = {
            "grid_dSharpe": dS, "grid_dCalmar": dC,
            "retspace_dSharpe": perf_metrics(avg_on, cash).get("sharpe")
                                - perf_metrics(avg_off, cash).get("sharpe"),
            "boot": boot,
            "classification": classify(boot["dSharpe"]),
        }
        print(f"MAIN {fn}: grid_dS={dS:+.4f} retspace_dS={main_eff[fn]['retspace_dSharpe']:+.4f} "
              f"CI[{boot['dSharpe']['ci_lo']:+.4f},{boot['dSharpe']['ci_hi']:+.4f}] "
              f"p={boot['dSharpe']['p_gt0']:.3f} {main_eff[fn]['classification']}")

    # ===== Sequential ladder (cumulative add-in, memo 5.9 order), marginal-step CIs =====
    ladder = []
    state = {f: 0 for f in FACTORS}
    prev_cfg = tuple(state[f] for f in FACTORS)
    for f in LADDER_ORDER:
        state[f] = 1
        cfg = tuple(state[x] for x in FACTORS)
        boot = paired_block_bootstrap(cells[cfg]["ret"], cells[prev_cfg]["ret"], cash)
        ladder.append({
            "step": f"+{f}",
            "from_cfg": "".join(map(str, prev_cfg)),
            "to_cfg": "".join(map(str, cfg)),
            "cum_sharpe": cells[cfg]["sharpe"],
            "cum_calmar": cells[cfg]["calmar"],
            "step_dSharpe": cells[cfg]["sharpe"] - cells[prev_cfg]["sharpe"],
            "step_dCalmar": cells[cfg]["calmar"] - cells[prev_cfg]["calmar"],
            "boot": boot,
            "classification": classify(boot["dSharpe"]),
        })
        print(f"LADDER +{f}: cum_sh={cells[cfg]['sharpe']:.4f} "
              f"stepdS CI[{boot['dSharpe']['ci_lo']:+.4f},{boot['dSharpe']['ci_hi']:+.4f}] "
              f"p={boot['dSharpe']['p_gt0']:.3f} {ladder[-1]['classification']}")
        prev_cfg = cfg

    # ===== Cumulative whole-stack: all-ON vs all-OFF =====
    cum_boot = paired_block_bootstrap(prod_ret, haa_ret, cash)
    cum_wf = walk_forward_3seg(haa_ret, prod_ret, cash)
    print(f"CUMULATIVE all-ON vs all-OFF: dS={on_sh-off_sh:+.4f} "
          f"CI[{cum_boot['dSharpe']['ci_lo']:+.4f},{cum_boot['dSharpe']['ci_hi']:+.4f}] "
          f"p={cum_boot['dSharpe']['p_gt0']:.3f}")

    # ===== BH-FDR across the 5 LOO factor p-values (one-sided 1-p_gt0) =====
    pvals = {fn: 1.0 - loo[fn]["boot"]["dSharpe"]["p_gt0"] for fn in FACTORS}
    fdr = bh_fdr(pvals, alpha=0.05)

    # ===== classification counts (LOO) =====
    counts = {"SIGNIFICANT": 0, "MARGINAL": 0, "NOISE": 0}
    for fn in FACTORS:
        counts[loo[fn]["classification"]] += 1

    # ===== ranking incl min-var 3-of-4 (by p_gt0) =====
    rank_rows = []
    for fn in FACTORS:
        b = loo[fn]["boot"]["dSharpe"]
        rank_rows.append({
            "name": f"factor {fn}", "dSharpe": b["mean"], "ci_lo": b["ci_lo"],
            "ci_hi": b["ci_hi"], "p_gt0": b["p_gt0"],
            "classification": loo[fn]["classification"],
        })
    rank_rows.append({
        "name": MINVAR_3OF4["label"], "dSharpe": MINVAR_3OF4["dSharpe_mean"],
        "ci_lo": MINVAR_3OF4["ci_lo"], "ci_hi": MINVAR_3OF4["ci_hi"],
        "p_gt0": MINVAR_3OF4["p_gt0"],
        "classification": ("SIGNIFICANT" if MINVAR_3OF4["ci_lo"] > 0 else "MARGINAL"),
    })
    rank_rows.sort(key=lambda r: -r["p_gt0"])

    # ===== MULTI-METRIC: min-var 3-of-4 recomputed on Sortino/CVaR (+Calmar/Martin pt) =====
    # min-var is an ENGINE-level selection swap on canonical CPM (reproduces anchor),
    # not HAA/AAA-specific. Bootstrap vs prod with the SAME params for comparability.
    prod_wf = make_weight_fn("invvol", "sample", 252, "rank")
    mv_wf = make_weight_fn("invvol", "sample", 252, "minvar", subset_m=3)
    mv_prod = HARNESS.run_strategy(prod_wf, window="clean", data=hdata)
    mv_ret = HARNESS.run_strategy(mv_wf, window="clean", data=hdata)
    mv_boot = paired_block_bootstrap_mm(mv_ret, mv_prod, cash)
    mp = perf_metrics(mv_prod, cash); mm = perf_metrics(mv_ret, cash)
    minvar_mm = {
        "engine_prod_sharpe": mp.get("sharpe"),
        "minvar_sharpe": mm.get("sharpe"),
        "point_dSharpe": mm.get("sharpe") - mp.get("sharpe"),
        "point_dCalmar": mm.get("calmar") - mp.get("calmar"),
        "point_dMartin": mm.get("martin") - mp.get("martin"),
        "point_dMaxDD": mm.get("max_drawdown") - mp.get("max_drawdown"),
        "boot": mv_boot,
        "class_by_metric": {
            "Sharpe": classify(mv_boot["dSharpe"]),
            "Sortino": classify(mv_boot["dSortino"]),
            "CVaR": classify(mv_boot["dCVaR"]),
        },
    }
    print("MINVAR mm: dSh", minvar_mm["class_by_metric"]["Sharpe"],
          "dSo", minvar_mm["class_by_metric"]["Sortino"],
          "dCV", minvar_mm["class_by_metric"]["CVaR"])

    # factor x metric significance matrix (Sharpe/Sortino/CVaR classification)
    sig_matrix = []
    for fn in FACTORS:
        b = loo[fn]["boot"]; cbm = loo[fn]["class_by_metric"]
        sig_matrix.append({
            "factor": fn, "label": FACTOR_LABEL[fn],
            "Sharpe": cbm["Sharpe"], "Sortino": cbm["Sortino"], "CVaR": cbm["CVaR"],
            "dSharpe": b["dSharpe"], "dSortino": b["dSortino"], "dCVaR": b["dCVaR"],
            "point_dCalmar": loo[fn]["point_dCalmar"],
            "point_dMartin": loo[fn]["point_dMartin"],
        })

    # per-metric ranking incl min-var (by p_gt0) for Sharpe + Sortino
    def _rank(metric_key):
        rows = [{"name": f"factor {fn}", **loo[fn]["boot"][metric_key],
                 "class": loo[fn]["class_by_metric"][metric_key.replace("d", "", 1)]}
                for fn in FACTORS]
        rows.append({"name": MINVAR_3OF4["label"], **mv_boot[metric_key],
                     "class": minvar_mm["class_by_metric"][metric_key.replace("d", "", 1)]})
        rows.sort(key=lambda r: -r["p_gt0"])
        return rows
    ranking_per_metric = {m: _rank("d" + m) for m in ("Sharpe", "Sortino", "CVaR")}

    result = {
        "meta": {
            "lens": "clean window, B=2000 paired block bootstrap (block=21, seed=42)",
            "both_252": cpm_live.CORR_LOOKBACK_DAYS == 252,
            "corr_lookback_days": cpm_live.CORR_LOOKBACK_DAYS,
            "haa_universe": HAA_UNIVERSE, "cpm_universe": CPM_UNIVERSE,
            "safe_pool": SAFE,
            "factor_order": ",".join(FACTORS),
            "factor_label": FACTOR_LABEL,
            "ladder_order": LADDER_ORDER,
            "clean": f"{clean_start.date()}..{end.date()}",
        },
        "anchor": {k: float(anchor[k]) for k in anchor},
        "gate": {"all_off_sharpe": off_sh, "all_on_sharpe": on_sh,
                 "all_off_target": HAA_ANCHOR_SHARPE, "all_on_target": PROD_ANCHOR_SHARPE,
                 "gate_off": gate_off, "gate_on": gate_on, "is_504": is_504},
        "loo_main_effects": loo,
        "background_main_effects": main_eff,
        "ladder": {"order": LADDER_ORDER, "steps": ladder},
        "cumulative": {
            "dSharpe_point": on_sh - off_sh,
            "boot": cum_boot, "walk_forward": cum_wf,
            "classification": classify(cum_boot["dSharpe"]),
        },
        "bh_fdr": fdr,
        "classification_counts": counts,
        "ranking_with_minvar": rank_rows,
        "minvar_3of4": MINVAR_3OF4,
        "significance_matrix": sig_matrix,
        "minvar_multimetric": minvar_mm,
        "ranking_per_metric": ranking_per_metric,
        "metric_notes": {
            "classification_metrics": ["Sharpe", "Sortino", "CVaR"],
            "path_independent": True,
            "context_only": ["Calmar", "Martin", "MaxDD"],
            "caveat": "Calmar/Martin path-dependent (running-max DD / Ulcer); "
                      "block bootstrap shuffles the DD path -> soft CIs, reported "
                      "as POINT estimates only. Sortino/CVaR order-invariant -> "
                      "clean CIs, used for SIGNIFICANT/MARGINAL/NOISE.",
        },
    }

    def _strip(o):
        return None

    with open(OUT, "w") as f:
        json.dump(result, f, indent=2, default=_strip)
    print("wrote", OUT)
    return result


if __name__ == "__main__":
    main()
