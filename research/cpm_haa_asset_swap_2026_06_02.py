# -*- coding: utf-8 -*-
"""ANALYST (read-only re production; NO production files touched; NO commit).

Attribute CPM's dominant "universe" edge (HAA-8 -> CPM-8, +0.15 Sharpe under
the HAA mechanism) to INDIVIDUAL single-asset swaps.

Method: KEEP THE HAA MECHANISM FIXED (config R0 M0 = 13612U dual momentum,
TIP-only canary, top-4, equal-weight, NO vol-adj ranker, NO min-var) and vary
ONLY the universe via single-asset swaps. This is exactly param_wf(..., U, R=0,
M=0) from cpm_haa_coupled_factorial_v2.py, generalized to an arbitrary universe
list.

Anchors (verified in cpm_haa_coupled_factorial_v2.json, CLEAN window):
  HAA-8 baseline (config 000)         = 0.8669910 Sharpe
  HAA-on-CPM-8   (config 100)         = 1.0189262 Sharpe   (= +0.1519 universe edge)

HAA-8 = SPY, IWM, VEA, VWO, VNQ, DBC, IEF, TLT
CPM-8 = QQQ, SPHQ, EFA, EEM, VNQ, GLD, TLT, DBC
Swaps HAA->CPM:  SPY->QQQ, IWM->SPHQ, VEA->EFA, VWO->EEM, IEF->GLD
Common (unchanged): VNQ, TLT, DBC

Configs run (all HAA mechanism R0 M0):
  baseline        : HAA-8
  IEF->GLD        : PRIMARY (user idea)
  SPY->QQQ        : single swap
  IWM->SPHQ       : single swap
  VEA->EFA        : single swap
  VWO->EEM        : single swap
  full CPM-8      : all swaps (additivity reference = config 100)

Discipline: HAA mechanism held fixed; reproduce both anchors first;
point-estimates only (no bootstrap/WF); HIGH overfit caution -> report ALL 5
swaps, no cherry-picking; PIT/cached-data caveat.
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
    load_panel, perf_metrics, sig_13612U, best_safe,
    DEFAULT_CASH, COST_BPS_PER_SIDE,
)
import exec_lag_moo_validation_2026_05_30 as H  # noqa: E402

CONV = "mooex"
SAFE = ["SHV", "IEF"]
TOP_K = 4

HAA_UNIVERSE = ["SPY", "IWM", "VEA", "VWO", "VNQ", "DBC", "IEF", "TLT"]
CPM_UNIVERSE = ["QQQ", "SPHQ", "EFA", "EEM", "VNQ", "GLD", "TLT", "DBC"]

HAA_ANCHOR = 0.8669910493845644
CPM_ON_HAAMECH_ANCHOR = 1.0189262096305145

# single-asset swaps HAA -> CPM
SWAPS = [
    ("SPY", "QQQ"),
    ("IWM", "SPHQ"),
    ("VEA", "EFA"),
    ("VWO", "EEM"),
    ("IEF", "GLD"),
]


def uni_wf(close, sig_d, universe):
    """HAA mechanism (R0 M0) on an arbitrary universe list.

    Byte-identical to param_wf(close, sig_d, U=*, R=0, M=0) except universe is
    passed explicitly instead of selected by the U flag.
    """
    monthly = close.loc[:sig_d].resample("ME").last()
    safe = best_safe(monthly, sig_d, SAFE)

    # canary TIP-only
    tip = sig_13612U(monthly["TIP"]) if "TIP" in monthly.columns else np.nan
    if pd.isna(tip) or tip <= 0:
        return {safe: 1.0}

    present = [t for t in universe if t in monthly.columns]
    avail = [t for t in present
             if (sig_d in close.index and pd.notna(close.loc[sig_d].get(t, np.nan)))
             and pd.notna(sig_13612U(monthly[t]))]
    if not avail:
        return {safe: 1.0}

    rank_score, screen_val = {}, {}
    for t in avail:
        m = sig_13612U(monthly[t])
        if pd.isna(m):
            continue
        rank_score[t] = float(m)
        screen_val[t] = float(m)
    if not rank_score:
        return {safe: 1.0}

    ranked = pd.Series(rank_score).sort_values(ascending=False)
    top_k = max(2, min(TOP_K, len(ranked)))
    top = ranked.iloc[:top_k]

    positive = top[top.index.map(lambda t: screen_val.get(t, -np.inf) > 0)]
    if len(positive) == 0:
        return {safe: 1.0}

    picks = list(positive.index)
    n_pos = len(picks)
    risky_fraction = min(n_pos, 4) / 4.0
    safe_fraction = 1.0 - risky_fraction

    base_w = {t: 1.0 / len(picks) for t in picks}
    out = {t: w * risky_fraction for t, w in base_w.items()}
    if safe_fraction > 0:
        out[safe] = out.get(safe, 0.0) + safe_fraction
    return out


def met(daily, cash):
    m = perf_metrics(daily, cash)
    return {"sharpe": m.get("sharpe"), "cagr": m.get("cagr"), "vol": m.get("vol"),
            "maxdd": m.get("max_drawdown"), "calmar": m.get("calmar")}


def run_series(close, daily, intraday, overnight, wf, start, end):
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

    cols = sorted(set(HAA_UNIVERSE + CPM_UNIVERSE + SAFE + ["TIP"]) & set(panel.columns))
    close = panel[cols]
    daily = close.ffill().pct_change()

    windows = {"CLEAN": (clean_start, end), "EXT": (ext_start, end)}

    def windowed(ser):
        return {wn: met(ser.loc[(ser.index >= ws) & (ser.index <= we)], cash)
                for wn, (ws, we) in windows.items()}

    # ---- configs: name -> universe list ----
    configs = {}
    configs["baseline_HAA8"] = list(HAA_UNIVERSE)
    # PRIMARY: IEF -> GLD
    configs["IEF->GLD"] = [("GLD" if t == "IEF" else t) for t in HAA_UNIVERSE]
    # per-asset single swaps
    for ha, cp in SWAPS:
        configs[f"{ha}->{cp}"] = [(cp if t == ha else t) for t in HAA_UNIVERSE]
    configs["full_CPM8"] = list(CPM_UNIVERSE)

    results = {}
    for name, uni in configs.items():
        wf = lambda sd, u=uni: uni_wf(close, sd, u)
        ser = run_series(close, daily, intraday, overnight, wf, ext_start, end)
        results[name] = {"universe": uni, **windowed(ser)}
        c = results[name]["CLEAN"]
        print(f"  {name:16s} CLEAN sharpe={c['sharpe']:.4f} "
              f"cagr={c['cagr']*100:.2f}% maxdd={c['maxdd']*100:.2f}% calmar={c['calmar']:.4f}")

    base_sh = results["baseline_HAA8"]["CLEAN"]["sharpe"]
    full_sh = results["full_CPM8"]["CLEAN"]["sharpe"]

    # ---- gates: reproduce anchors ----
    gate_haa = abs(base_sh - HAA_ANCHOR) < 5e-4
    gate_cpm = abs(full_sh - CPM_ON_HAAMECH_ANCHOR) < 5e-4

    # ---- per-asset attribution table ----
    attrib = []
    for ha, cp in SWAPS:
        nm = f"{ha}->{cp}"
        c = results[nm]["CLEAN"]
        attrib.append({
            "swap": nm,
            "sharpe": c["sharpe"], "d_sharpe": c["sharpe"] - base_sh,
            "cagr": c["cagr"], "maxdd": c["maxdd"], "calmar": c["calmar"],
        })
    attrib.sort(key=lambda x: x["d_sharpe"], reverse=True)

    sum_dsharpe = sum(a["d_sharpe"] for a in attrib)
    full_gap = full_sh - base_sh
    interaction = full_gap - sum_dsharpe

    out = {
        "meta": {
            "conv": CONV, "cost_bps": COST_BPS_PER_SIDE, "top_k": TOP_K,
            "mechanism": "HAA fixed R0 M0 (13612U dual momentum, TIP-only canary, top-4, equal-weight, no vol-adj, no min-var)",
            "clean": f"{clean_start.date()}..{end.date()}",
            "ext": f"{ext_start.date()}..{end.date()}",
            "haa_universe": HAA_UNIVERSE, "cpm_universe": CPM_UNIVERSE,
            "swaps": [f"{a}->{b}" for a, b in SWAPS],
            "anchors": {"HAA8": HAA_ANCHOR, "CPM8_on_HAAmech": CPM_ON_HAAMECH_ANCHOR},
            "caveat": "Point-estimates only; cached/PIT data; single-asset attribution is data-mining-prone -> all 5 swaps reported, none cherry-picked.",
        },
        "gates": {
            "baseline_reproduces_HAA": {"actual": base_sh, "target": HAA_ANCHOR, "pass": bool(gate_haa)},
            "full_reproduces_CPM_on_HAAmech": {"actual": full_sh, "target": CPM_ON_HAAMECH_ANCHOR, "pass": bool(gate_cpm)},
        },
        "baseline_sharpe": base_sh,
        "primary_IEF_to_GLD": {
            "sharpe": results["IEF->GLD"]["CLEAN"]["sharpe"],
            "d_sharpe_vs_HAA": results["IEF->GLD"]["CLEAN"]["sharpe"] - base_sh,
            "metrics_CLEAN": results["IEF->GLD"]["CLEAN"],
            "metrics_EXT": results["IEF->GLD"]["EXT"],
        },
        "attribution_ranked": attrib,
        "additivity": {
            "full_gap_HAA8_to_CPM8": full_gap,
            "sum_single_swap_dsharpe": sum_dsharpe,
            "interaction_residual": interaction,
        },
        "configs": results,
    }
    out_json = Path(__file__).with_suffix(".json")
    out_json.write_text(json.dumps(out, indent=2, default=float))
    print("\nGATES:", json.dumps(out["gates"], indent=2, default=float))
    print("WROTE", out_json)
    return out


if __name__ == "__main__":
    main()
