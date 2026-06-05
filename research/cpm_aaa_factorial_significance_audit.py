"""AAA->CPM 2^6 factorial STATISTICAL-SIGNIFICANCE audit (both-252).

Role: analyst (read-only re production; writes only research/ artifacts; no
commit). Question: are the ADOPTED AAA->CPM production factors (U,R,W,S,P,C)
individually significant or marginal -- under the SAME lens applied to the
min-var 3-of-4 selection (clean window, B=2000 paired block bootstrap, dSharpe
CI + p(>0))? If the adopted factors are also marginal, "marginal" is not a fair
disqualifier for min-var 3-of-4.

THE FIX vs research/cpm_factorial_faithful_aaa.py:
  That script's docstring anchors the all-ON cell at 504d (Sharpe 1.1910). The
  W=ON path there calls inv_vol_weights(..., CORR_LOOKBACK_DAYS), and
  cpm_live.CORR_LOOKBACK_DAYS is now 252 (both-252 production). So reusing
  cpm_wf today already runs W=ON at 252. We GATE on it: all-OFF must == faithful
  AAA 0.7869 AND all-ON must == production both-252 1.1658 (NOT 1.1910). If
  all-ON == 1.1910 the harness is still 504d -> abort.

Engine: research.cpm_harness (mooex T+1, 10 bps/side, both-252). Bootstrap:
research.cpm_weighting_corr.paired_block_bootstrap (B=2000, block=21, seed=42)
-- byte-identical to the min-var studies. Clean window is the decision lens.

Run: .venv/bin/python -m research.cpm_aaa_factorial_significance_audit
Out: research/cpm_aaa_factorial_significance_audit.json
     (findings .md written by the analyst)
"""

from __future__ import annotations

import itertools
import json
from pathlib import Path

import numpy as np

import cpm_live
from research import cpm_harness as H
from research.cpm_weighting_corr import paired_block_bootstrap, make_weight_fn
from research.cpm_bootstrap_multimetric import paired_block_bootstrap_mm
from research.cpm_factorial_faithful_aaa import (
    cpm_wf,
    AAA_UNIVERSE,
    CPM_PROD_UNIVERSE,
    ANCHOR_BASE_CLEAN,
)

OUT = Path(__file__).resolve().parent / "cpm_aaa_factorial_significance_audit.json"

FACTORS = ["C", "U", "R", "S", "W", "P"]  # config tuple order
PROD_ANCHOR_SHARPE = 1.1658
AAA_ANCHOR_SHARPE = ANCHOR_BASE_CLEAN[0]  # 0.7869

# min-var 3-of-4 reference (from the prior min-var studies, same lens).
MINVAR_3OF4 = {
    "label": "min-var 3-of-4 (vs prod)",
    "dSharpe_mean": 0.106,
    "ci_lo": 0.002,
    "ci_hi": 0.213,
    "p_gt0": 0.977,
}


def make_wf(daily, C, U, R, S, W, P):
    return lambda panel, sig_d: cpm_wf(panel, daily, sig_d, C, U, R, S, W, P)


def cell_returns(data, daily, cfg):
    C, U, R, S, W, P = cfg
    wf = make_wf(daily, C, U, R, S, W, P)
    return H.run_strategy(wf, window="clean", data=data)


def sharpe_calmar(ret, cash):
    m = cpm_live.perf_metrics(ret, cash)
    return (m.get("sharpe"), m.get("calmar"), m.get("martin"),
            m.get("max_drawdown"))


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
        mb = cpm_live.perf_metrics(b.iloc[lo:hi], cash)
        mv = cpm_live.perf_metrics(v.iloc[lo:hi], cash)
        segs.append({
            "start": str(common[lo].date()), "end": str(common[hi - 1].date()),
            "dSharpe": mv.get("sharpe") - mb.get("sharpe"),
            "dCalmar": mv.get("calmar") - mb.get("calmar"),
        })
    return segs


def classify(boot):
    """SIG / MARGINAL / NOISE from a paired-bootstrap dSharpe block."""
    lo, hi, p = boot["ci_lo"], boot["ci_hi"], boot["p_gt0"]
    if lo > 0 or hi < 0:
        return "SIGNIFICANT"
    # CI spans 0
    if p >= 0.85 or p <= 0.15:
        return "MARGINAL"
    return "NOISE"


def bh_fdr(pvals, alpha=0.05):
    """Benjamini-Hochberg on one-sided p = P(effect <= 0) = 1 - p_gt0."""
    items = sorted(pvals.items(), key=lambda kv: kv[1])
    m = len(items)
    survive = {}
    kmax = 0
    for i, (name, p) in enumerate(items, start=1):
        thresh = alpha * i / m
        if p <= thresh:
            kmax = i
    for i, (name, p) in enumerate(items, start=1):
        survive[name] = (i <= kmax)
    return {"alpha": alpha, "ordered": items, "survive": survive,
            "n_survive": sum(survive.values())}


def main():
    data = H.load_data()
    cash = data.cash
    daily = data.panel.ffill().pct_change()

    # ---- GATE 1: production anchor through the harness (compute_target_weights) ----
    anchor = H.verify_anchor(data=data)
    print("verify_anchor OK:", {k: round(float(anchor[k]), 4)
                                 for k in ("Sharpe", "MaxDD", "Calmar")})

    # ---- run all 64 cells (clean) ----
    cells = {}
    for cfg in itertools.product([0, 1], repeat=6):
        r = cell_returns(data, daily, cfg)
        s, c, mt, dd = sharpe_calmar(r, cash)
        cells[cfg] = {"ret": r, "sharpe": s, "calmar": c, "martin": mt, "maxdd": dd}
    print(f"ran {len(cells)} cells")

    alloff = (0, 0, 0, 0, 0, 0)
    allon = (1, 1, 1, 1, 1, 1)

    # ---- GATE 2: all-OFF == faithful AAA 0.7869 ; all-ON == prod both-252 1.1658 ----
    off_sh = cells[alloff]["sharpe"]
    on_sh = cells[allon]["sharpe"]
    gate_off = abs(off_sh - AAA_ANCHOR_SHARPE) < 5e-3
    gate_on = abs(on_sh - PROD_ANCHOR_SHARPE) < 5e-3
    is_504 = abs(on_sh - 1.1910) < 5e-3
    print(f"GATE all-OFF sharpe={off_sh:.4f} (target {AAA_ANCHOR_SHARPE}) -> {gate_off}")
    print(f"GATE all-ON  sharpe={on_sh:.4f} (target {PROD_ANCHOR_SHARPE}) -> {gate_on}"
          + ("  [STILL 504d!]" if is_504 else ""))
    if is_504:
        raise SystemExit("ABORT: all-ON == 1.1910 -> harness still on 504d. Fix W to 252.")
    if not (gate_off and gate_on):
        raise SystemExit("ABORT: anchor gate failed.")

    prod_ret = cells[allon]["ret"]
    aaa_ret = cells[alloff]["ret"]

    # ===== Per-factor LEAVE-ONE-OUT at the production corner =====
    # var = production (all-ON); base = production with ONE factor turned OFF.
    # dSharpe = Sharpe(prod) - Sharpe(prod\X) = marginal contribution of factor X
    # AT the production config. Single change vs prod -> same lens as min-var.
    loo = {}
    for i, fn in enumerate(FACTORS):
        base_cfg = tuple(0 if j == i else 1 for j in range(6))  # prod minus X
        base_ret = cells[base_cfg]["ret"]
        # multi-metric paired block bootstrap (same B/block/seed); classify on
        # path-INDEPENDENT Sharpe + Sortino (+CVaR). Calmar/Martin = point context.
        boot = paired_block_bootstrap_mm(prod_ret, base_ret, cash)  # var=prod, base=prod\X
        wf = walk_forward_3seg(base_ret, prod_ret, cash)
        pt_dS = cells[allon]["sharpe"] - cells[base_cfg]["sharpe"]
        pt_dC = cells[allon]["calmar"] - cells[base_cfg]["calmar"]
        pt_dM = cells[allon]["martin"] - cells[base_cfg]["martin"]
        cbm = {
            "Sharpe": classify(boot["dSharpe"]),
            "Sortino": classify(boot["dSortino"]),
            "CVaR": classify(boot["dCVaR"]),
        }
        loo[fn] = {
            "base_cfg": "".join(map(str, base_cfg)),
            "point_dSharpe": pt_dS,
            "point_dCalmar": pt_dC,
            "point_dMartin": pt_dM,
            "boot": boot,
            "walk_forward": wf,
            "wf_sign_positive": sum(1 for s in wf if s["dSharpe"] > 0),
            "class_by_metric": cbm,
            "classification": cbm["Sharpe"],
        }
        print(f"LOO {fn}: dS={pt_dS:+.4f} Sh={cbm['Sharpe'][:4]}/"
              f"So[{boot['dSortino']['ci_lo']:+.3f},{boot['dSortino']['ci_hi']:+.3f}]"
              f"p={boot['dSortino']['p_gt0']:.2f}={cbm['Sortino'][:4]}/CV={cbm['CVaR'][:4]} "
              f"wf+={loo[fn]['wf_sign_positive']}/3")

    # ===== Background-averaged main effects (point estimates from the grid) =====
    main_eff = {}
    half = 2 ** 5
    for i, fn in enumerate(FACTORS):
        dS = sum((1 if cfg[i] else -1) * cells[cfg]["sharpe"] for cfg in cells) / half
        dC = sum((1 if cfg[i] else -1) * cells[cfg]["calmar"] for cfg in cells) / half
        main_eff[fn] = {"dSharpe": dS, "dCalmar": dC}

    # ===== Sequential ladder (cumulative add-in), marginal-step CIs =====
    # Order factors by background-averaged Calmar main effect (desc), P after S.
    order = sorted(FACTORS, key=lambda f: -main_eff[f]["dCalmar"])
    if order.index("P") < order.index("S"):
        order.remove("P")
        order.insert(order.index("S") + 1, "P")
    ladder = []
    state = {f: 0 for f in FACTORS}
    prev_cfg = tuple(state[f] for f in FACTORS)
    for f in order:
        state[f] = 1
        cfg = tuple(state[x] for x in FACTORS)
        var_ret = cells[cfg]["ret"]
        base_ret = cells[prev_cfg]["ret"]
        boot = paired_block_bootstrap(var_ret, base_ret, cash)
        ladder.append({
            "step": f"+{f}",
            "from_cfg": "".join(map(str, prev_cfg)),
            "to_cfg": "".join(map(str, cfg)),
            "cum_sharpe": cells[cfg]["sharpe"],
            "cum_calmar": cells[cfg]["calmar"],
            "step_dSharpe": cells[cfg]["sharpe"] - cells[prev_cfg]["sharpe"],
            "boot": boot,
            "classification": classify(boot["dSharpe"]),
        })
        print(f"LADDER +{f}: cum_sh={cells[cfg]['sharpe']:.4f} "
              f"stepdS CI[{boot['dSharpe']['ci_lo']:+.4f},{boot['dSharpe']['ci_hi']:+.4f}] "
              f"p={boot['dSharpe']['p_gt0']:.3f} {ladder[-1]['classification']}")
        prev_cfg = cfg

    # ===== Cumulative whole-stack: all-ON vs all-OFF =====
    cum_boot = paired_block_bootstrap(prod_ret, aaa_ret, cash)
    cum_wf = walk_forward_3seg(aaa_ret, prod_ret, cash)
    print(f"CUMULATIVE all-ON vs all-OFF: dS={on_sh-off_sh:+.4f} "
          f"CI[{cum_boot['dSharpe']['ci_lo']:+.4f},{cum_boot['dSharpe']['ci_hi']:+.4f}] "
          f"p={cum_boot['dSharpe']['p_gt0']:.3f}")

    # ===== BH-FDR across the 6 LOO factor p-values (one-sided 1-p_gt0) =====
    pvals = {fn: 1.0 - loo[fn]["boot"]["dSharpe"]["p_gt0"] for fn in FACTORS}
    fdr = bh_fdr(pvals, alpha=0.05)

    # ===== classification counts =====
    counts = {"SIGNIFICANT": 0, "MARGINAL": 0, "NOISE": 0}
    for fn in FACTORS:
        counts[loo[fn]["classification"]] += 1

    # ===== ranking incl min-var 3-of-4 =====
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
    mv_prod = H.run_strategy(prod_wf, window="clean", data=data)
    mv_ret = H.run_strategy(mv_wf, window="clean", data=data)
    mv_boot = paired_block_bootstrap_mm(mv_ret, mv_prod, cash)
    mp = cpm_live.perf_metrics(mv_prod, cash); mm = cpm_live.perf_metrics(mv_ret, cash)
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
        b = loo[fn]["boot"]; cbm2 = loo[fn]["class_by_metric"]
        sig_matrix.append({
            "factor": fn,
            "Sharpe": cbm2["Sharpe"], "Sortino": cbm2["Sortino"], "CVaR": cbm2["CVaR"],
            "dSharpe": b["dSharpe"], "dSortino": b["dSortino"], "dCVaR": b["dCVaR"],
            "point_dCalmar": loo[fn]["point_dCalmar"],
            "point_dMartin": loo[fn]["point_dMartin"],
        })

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
            "aaa_universe": AAA_UNIVERSE, "cpm_universe": CPM_PROD_UNIVERSE,
            "factor_order": "C,U,R,S,W,P",
        },
        "anchor": {k: float(anchor[k]) for k in anchor},
        "gate": {"all_off_sharpe": off_sh, "all_on_sharpe": on_sh,
                 "all_off_target": AAA_ANCHOR_SHARPE, "all_on_target": PROD_ANCHOR_SHARPE,
                 "gate_off": gate_off, "gate_on": gate_on, "is_504": is_504},
        "loo_main_effects": loo,
        "background_main_effects": main_eff,
        "ladder": {"order": order, "steps": ladder},
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

    # strip return series before serialize
    def _clean(o):
        return None

    with open(OUT, "w") as f:
        json.dump(result, f, indent=2, default=_clean)
    print("wrote", OUT)
    return result


if __name__ == "__main__":
    main()
