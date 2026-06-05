# -*- coding: utf-8 -*-
"""ANALYST (read-only re production; NO prod/memo/docs touched; NO commit).

Test the COMBINED GLD + SPHQ swap on the HAA universe vs plain HAA baseline.

Hypothesis: the two biggest single-asset drivers of CPM's universe edge
(IEF->GLD +0.073, IWM->SPHQ +0.051; combined ~+0.124 near-additive) form a
robust "gold + quality" universe upgrade over plain HAA-8. Is the combined lift
statistically significant (paired block bootstrap), or within-noise?

Mechanism FIXED = HAA config R0 M0 (13612U dual momentum, TIP-only canary,
top-4, equal-weight, best-of {SHV,IEF} safe; NO vol-adj ranker, NO min-var).
ONLY the universe varies. uni_wf reused byte-identical from
research/cpm_haa_asset_swap_2026_06_02.py.

Configs:
  baseline_HAA8  = SPY, IWM, VEA, VWO, VNQ, DBC, IEF, TLT   (anchor 0.8669910)
  HAA_GLD_SPHQ   = SPY, SPHQ, VEA, VWO, VNQ, DBC, GLD, TLT  (IEF->GLD & IWM->SPHQ)

Metrics (FULL): Sharpe, Sortino, CVaR(95) ratio, Calmar, Martin, MaxDD, CAGR,
ann.vol, turnover -- baseline vs GLD+SPHQ, CLEAN + EXT.
Bootstrap: paired block bootstrap B=2000 block=21 seed=42, GLD+SPHQ MINUS
baseline (same return path) -> dSharpe/dSortino/dCVaR/dCalmar/dMartin + 95% CI
+ p(variant>baseline). CLEAN window (decision).

HIGH overfit caution: GLD and SPHQ were SELECTED as the top-2 single drivers in
a prior in-sample attribution -> selection bias inflates the combined in-sample
lift. The honest test is whether the lift survives the bootstrap despite that
selection. PIT/cached-data caveat; single in-sample window.
"""
import sys
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from cpm_live import (  # noqa: E402
    load_panel, perf_metrics, best_safe, sig_13612U,
    DEFAULT_CASH, COST_BPS_PER_SIDE,
)
import exec_lag_moo_validation_2026_05_30 as H  # noqa: E402
# reuse the EXACT mechanism + universe-parametric weight fn (gate-verified)
from cpm_haa_asset_swap_2026_06_02 import (  # noqa: E402
    uni_wf, HAA_UNIVERSE, HAA_ANCHOR, SAFE, CONV,
)
from research.cpm_bootstrap_multimetric import (  # noqa: E402
    paired_block_bootstrap_mm, _sortino_ann, _cvar_ratio_ann,
)


def full_met(daily, cash):
    """FULL metric set on a daily return series."""
    m = perf_metrics(daily, cash)
    x = daily.values
    return {
        "sharpe": m.get("sharpe"),
        "sortino": _sortino_ann(x, None),
        "cvar95_ratio": _cvar_ratio_ann(x, q=0.05),
        "calmar": m.get("calmar"),
        "martin": m.get("martin"),
        "maxdd": m.get("max_drawdown"),
        "cagr": m.get("cagr"),
        "vol": m.get("vol"),
    }


def ann_turnover(close, universe, start, end):
    """Average annual one-way turnover for uni_wf over signal dates in window."""
    monthly_idx = (pd.DataFrame({"x": 1}, index=close.index)
                   .groupby(pd.Grouper(freq="ME")).tail(1))
    sigs = monthly_idx.index[(monthly_idx.index >= start)
                             & (monthly_idx.index <= end)].tolist()
    prev_w, tos = {}, []
    for sd in sigs:
        w = uni_wf(close, sd, universe)
        keys = set(w) | set(prev_w)
        tos.append(sum(abs(w.get(k, 0.0) - prev_w.get(k, 0.0)) for k in keys))
        prev_w = w
    if len(tos) <= 1:
        return float("nan")
    # drop first (initial build); annualize monthly turnover *12
    return float(np.mean(tos[1:]) * 12.0)


def run_series(close, daily, intraday, overnight, universe, start, end):
    wf = lambda sd: uni_wf(close, sd, universe)
    s, _ = H._segment_returns_conv(close, daily, wf, start, end, CONV,
                                   COST_BPS_PER_SIDE, intraday, overnight)
    return s


def main():
    end = pd.Timestamp("2026-05-22")
    ext_start = pd.Timestamp("1999-03-10")
    clean_start = pd.Timestamp("2008-05-30")

    panel = load_panel(start=ext_start, end=end)
    end = min(end, panel.index[-1])
    cash = panel[DEFAULT_CASH].ffill().pct_change().dropna()

    open_df, close_yf = H.load_open_close()
    intraday = (close_yf / open_df - 1.0).reindex(panel.index)
    overnight = (open_df / close_yf.shift(1) - 1.0).reindex(panel.index)

    GLD_SPHQ = [("GLD" if t == "IEF" else "SPHQ" if t == "IWM" else t)
                for t in HAA_UNIVERSE]

    needed = sorted(set(HAA_UNIVERSE + GLD_SPHQ + SAFE + ["TIP"]) & set(panel.columns))
    close = panel[needed]
    daily = close.ffill().pct_change()

    for a in ("GLD", "SPHQ"):
        if a not in close.columns:
            raise SystemExit(f"FATAL: {a} not in panel -> cannot run combined swap")

    windows = {"CLEAN": (clean_start, end), "EXT": (ext_start, end)}

    configs = {"baseline_HAA8": list(HAA_UNIVERSE), "HAA_GLD_SPHQ": GLD_SPHQ}

    # ---- full-return series per window per config ----
    series = {}  # name -> window -> series
    metrics = {}  # name -> window -> full_met
    turnover = {}  # name -> window -> ann turnover
    for name, uni in configs.items():
        series[name], metrics[name], turnover[name] = {}, {}, {}
        full_ser = run_series(close, daily, intraday, overnight, uni, ext_start, end)
        for wn, (ws, we) in windows.items():
            seg = full_ser.loc[(full_ser.index >= ws) & (full_ser.index <= we)]
            series[name][wn] = seg
            metrics[name][wn] = full_met(seg, cash)
            turnover[name][wn] = ann_turnover(close, uni, ws, we)

    base_sh = metrics["baseline_HAA8"]["CLEAN"]["sharpe"]
    gate_haa = abs(base_sh - HAA_ANCHOR) < 5e-4
    var_sh = metrics["HAA_GLD_SPHQ"]["CLEAN"]["sharpe"]

    print(f"GATE baseline HAA-8 CLEAN sharpe = {base_sh:.7f} "
          f"(anchor {HAA_ANCHOR:.7f}) pass={gate_haa}")
    print(f"HAA+GLD+SPHQ CLEAN sharpe = {var_sh:.7f} "
          f"dSharpe = {var_sh - base_sh:+.4f}")

    if not gate_haa:
        raise SystemExit("GATE FAILED: baseline does not reproduce HAA anchor")

    # ---- paired block bootstrap (CLEAN, decision window) ----
    ra = series["HAA_GLD_SPHQ"]["CLEAN"]  # variant
    rb = series["baseline_HAA8"]["CLEAN"]  # baseline
    boot_clean = paired_block_bootstrap_mm(ra, rb, cash, B=2000, block=21, seed=42)
    # EXT bootstrap for robustness context
    boot_ext = paired_block_bootstrap_mm(
        series["HAA_GLD_SPHQ"]["EXT"], series["baseline_HAA8"]["EXT"],
        cash, B=2000, block=21, seed=42)

    out = {
        "meta": {
            "conv": CONV, "cost_bps": COST_BPS_PER_SIDE,
            "mechanism": "HAA fixed R0 M0 (13612U dual momentum, TIP-only canary, top-4, equal-weight, no vol-adj, no min-var)",
            "clean": f"{clean_start.date()}..{end.date()}",
            "ext": f"{ext_start.date()}..{end.date()}",
            "baseline_universe": HAA_UNIVERSE,
            "variant_universe": GLD_SPHQ,
            "swaps": ["IEF->GLD", "IWM->SPHQ"],
            "anchor_HAA8": HAA_ANCHOR,
            "bootstrap": "paired block B=2000 block=21 seed=42, variant MINUS baseline (same path)",
            "caveat": "GLD+SPHQ SELECTED as top-2 single drivers in prior in-sample attribution -> selection bias inflates the in-sample combined lift. Bootstrap is the honest test. PIT/cached-data; single in-sample.",
        },
        "gate_baseline_reproduces_HAA": {"actual": base_sh, "target": HAA_ANCHOR, "pass": bool(gate_haa)},
        "metrics": metrics,
        "turnover": turnover,
        "dSharpe_point": {"CLEAN": var_sh - base_sh,
                          "EXT": metrics["HAA_GLD_SPHQ"]["EXT"]["sharpe"] - metrics["baseline_HAA8"]["EXT"]["sharpe"]},
        "bootstrap_CLEAN": boot_clean,
        "bootstrap_EXT": boot_ext,
    }
    out_json = Path(__file__).with_suffix(".json")
    out_json.write_text(json.dumps(out, indent=2, default=float))
    print("\nBOOTSTRAP CLEAN (variant - baseline):")
    for k in ("dSharpe", "dSortino", "dCVaR", "dCalmar", "dMartin"):
        s = boot_clean[k]
        print(f"  {k:9s} mean={s['mean']:+.4f} CI=[{s['ci_lo']:+.4f},{s['ci_hi']:+.4f}] p_gt0={s['p_gt0']:.3f}")
    print("WROTE", out_json)
    return out


if __name__ == "__main__":
    main()
