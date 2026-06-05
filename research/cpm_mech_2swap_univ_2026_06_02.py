# -*- coding: utf-8 -*-
"""ANALYST (read-only re production; NO prod/memo/docs touched; NO commit).

QUESTION: Run the FULL CPM mechanism (R1 M1: vol-adjusted Faber ranker +
min-var 3-of-4 at n_pos=4) on the HAA universe with ONLY the two best swaps
applied (IEF->GLD, IWM->SPHQ). How much of full CPM (1.2557 CLEAN Sharpe) does
the partially-upgraded universe + CPM mechanism recover, vs the full CPM-8
universe? Do the remaining swaps (SPY->QQQ, VEA->EFA, VWO->EEM) still add?

MECHANISM = CPM (R=1, M=1) held FIXED. Only the universe varies. The weight
function below is the universe-parametric generalization of param_wf(U,R,M)
from research/cpm_haa_coupled_factorial_v2.py: byte-identical logic with
R=1,M=1 hardwired, universe passed explicitly.

Universes:
  HAA-8     = SPY, IWM, VEA, VWO, VNQ, DBC, IEF, TLT
  2-swap    = SPY, SPHQ, VEA, VWO, VNQ, DBC, GLD, TLT  (IEF->GLD & IWM->SPHQ)
  CPM-8     = QQQ, SPHQ, EFA, EEM, VNQ, GLD, TLT, DBC

GATES (must pass; CLEAN window, mooex/T+1 MOO, both-252, 10bps):
  CPM mech on HAA-8  (config U0 R1 M1) = 0.9399  (+/-5e-4)
  full CPM-8         (config U1 R1 M1) = 1.255673(+/-5e-4)

DISCIPLINE: point-estimates only (bootstrap skipped per scope); HIGH overfit
caution -- GLD & SPHQ were SELECTED as the top-2 single drivers in a prior
in-sample attribution, so the in-sample 2-swap lift is selection-biased;
PIT/cached-data; single in-sample window.
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
    load_panel, perf_metrics, sig_13612U, best_safe, faber_sma_xs,
    _min_var_subset, DEFAULT_CASH, COST_BPS_PER_SIDE, CORR_LOOKBACK_DAYS,
)
import exec_lag_moo_validation_2026_05_30 as H  # noqa: E402
from research.cpm_bootstrap_multimetric import (  # noqa: E402
    _sortino_ann, _cvar_ratio_ann,
)

CONV = "mooex"
SAFE = ["SHV", "IEF"]
TOP_K = 4

HAA_UNIVERSE = ["SPY", "IWM", "VEA", "VWO", "VNQ", "DBC", "IEF", "TLT"]
CPM_UNIVERSE = ["QQQ", "SPHQ", "EFA", "EEM", "VNQ", "GLD", "TLT", "DBC"]
TWOSWAP_UNIVERSE = [("GLD" if t == "IEF" else "SPHQ" if t == "IWM" else t)
                    for t in HAA_UNIVERSE]  # SPY,SPHQ,VEA,VWO,VNQ,DBC,GLD,TLT

# CLEAN anchors
CPM_ON_HAA_R1M1_ANCHOR = 0.9399    # config 011
FULL_CPM_ANCHOR = 1.255673         # config 111
HAA_BASELINE = 0.8670              # HAA mech baseline (context)


def cpm_mech_wf(close, sig_d, universe):
    """CPM mechanism (R=1 vol-adj Faber ranker, M=1 min-var 3-of-4 at n_pos=4)
    on an arbitrary universe. Byte-identical to param_wf(.,.,U=*,R=1,M=1) with
    universe passed explicitly. Canary TIP-only, top-4, equal-weight,
    best-of {SHV,IEF} safe, strict-4 breadth.
    """
    monthly = close.loc[:sig_d].resample("ME").last()
    safe = best_safe(monthly, sig_d, SAFE)

    # canary TIP-only
    tip = sig_13612U(monthly["TIP"]) if "TIP" in monthly.columns else np.nan
    if pd.isna(tip) or tip <= 0:
        return {safe: 1.0}

    present = [t for t in universe if t in monthly.columns]
    faber = faber_sma_xs(monthly)
    avail = [t for t in present
             if t in faber.index and pd.notna(faber[t])
             and (sig_d in close.index and pd.notna(close.loc[sig_d].get(t, np.nan)))]
    if not avail:
        return {safe: 1.0}

    rank_score, screen_val = {}, {}
    daily_rets = close[avail].ffill().pct_change()
    for t in avail:
        v = daily_rets[t].loc[:sig_d].tail(252).std() * np.sqrt(252)
        if pd.isna(v) or v < 1e-9:
            v = 1.0
        rank_score[t] = float(faber[t]) / v
        screen_val[t] = float(faber[t])
    if not rank_score:
        return {safe: 1.0}

    ranked = pd.Series(rank_score).sort_values(ascending=False)
    top_k = max(2, min(TOP_K, len(ranked)))
    top = ranked.iloc[:top_k]

    positive = top[top.index.map(lambda t: screen_val.get(t, -np.inf) > 0)]
    if len(positive) == 0:
        return {safe: 1.0}

    positive_picks = list(positive.index)
    n_pos = len(positive_picks)

    # M=1 min-var 3-of-4 at n_pos=4
    if n_pos == 4:
        picks = _min_var_subset(close, sig_d, positive_picks, CORR_LOOKBACK_DAYS, 3)
    else:
        picks = positive_picks

    risky_fraction = min(n_pos, 4) / 4.0
    safe_fraction = 1.0 - risky_fraction

    base_w = {t: 1.0 / len(picks) for t in picks}
    out = {t: w * risky_fraction for t, w in base_w.items()}
    if safe_fraction > 0:
        out[safe] = out.get(safe, 0.0) + safe_fraction
    return out


def full_met(daily, cash):
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
    monthly_idx = (pd.DataFrame({"x": 1}, index=close.index)
                   .groupby(pd.Grouper(freq="ME")).tail(1))
    sigs = monthly_idx.index[(monthly_idx.index >= start)
                             & (monthly_idx.index <= end)].tolist()
    prev_w, tos = {}, []
    for sd in sigs:
        w = cpm_mech_wf(close, sd, universe)
        keys = set(w) | set(prev_w)
        tos.append(sum(abs(w.get(k, 0.0) - prev_w.get(k, 0.0)) for k in keys))
        prev_w = w
    if len(tos) <= 1:
        return float("nan")
    return float(np.mean(tos[1:]) * 12.0)


def run_series(close, daily, intraday, overnight, universe, start, end):
    wf = lambda sd: cpm_mech_wf(close, sd, universe)
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

    cols = sorted(set(HAA_UNIVERSE + CPM_UNIVERSE + TWOSWAP_UNIVERSE + SAFE + ["TIP"])
                  & set(panel.columns))
    close = panel[cols]
    daily = close.ffill().pct_change()
    for a in ("GLD", "SPHQ"):
        if a not in close.columns:
            raise SystemExit(f"FATAL: {a} not in panel")

    windows = {"CLEAN": (clean_start, end), "EXT": (ext_start, end)}

    configs = {
        "CPMmech_HAA8": list(HAA_UNIVERSE),       # gate -> 0.9399
        "CPMmech_2swap": list(TWOSWAP_UNIVERSE),  # NEW
        "CPMmech_CPM8": list(CPM_UNIVERSE),       # gate -> 1.255673
    }

    metrics, turnover = {}, {}
    for name, uni in configs.items():
        metrics[name], turnover[name] = {}, {}
        full_ser = run_series(close, daily, intraday, overnight, uni, ext_start, end)
        for wn, (ws, we) in windows.items():
            seg = full_ser.loc[(full_ser.index >= ws) & (full_ser.index <= we)]
            metrics[name][wn] = full_met(seg, cash)
            turnover[name][wn] = ann_turnover(close, uni, ws, we)
        c = metrics[name]["CLEAN"]
        print(f"  {name:16s} CLEAN sharpe={c['sharpe']:.4f} sortino={c['sortino']:.4f} "
              f"calmar={c['calmar']:.4f} maxdd={c['maxdd']*100:.2f}%")

    haa8_sh = metrics["CPMmech_HAA8"]["CLEAN"]["sharpe"]
    cpm8_sh = metrics["CPMmech_CPM8"]["CLEAN"]["sharpe"]
    twoswap_sh = metrics["CPMmech_2swap"]["CLEAN"]["sharpe"]

    gate_haa = abs(haa8_sh - CPM_ON_HAA_R1M1_ANCHOR) < 5e-4
    gate_cpm = abs(cpm8_sh - FULL_CPM_ANCHOR) < 5e-4

    # recovery vs full-CPM-vs-HAA gap (HAA mech baseline 0.8670 -> full CPM 1.2557)
    full_gap = FULL_CPM_ANCHOR - HAA_BASELINE          # 0.3887
    twoswap_lift = twoswap_sh - HAA_BASELINE
    recovery_pct_of_full_gap = 100.0 * twoswap_lift / full_gap

    # how much of full CPM does 2-swap reach (vs CPM-mech-on-HAA8 floor)
    cpmmech_gap = cpm8_sh - haa8_sh                     # remaining universe edge under CPM mech
    twoswap_vs_floor = twoswap_sh - haa8_sh
    pct_of_cpmmech_universe_edge = 100.0 * twoswap_vs_floor / cpmmech_gap if cpmmech_gap else float("nan")

    # remaining swaps' marginal contribution under CPM mech
    remaining_swaps_lift = cpm8_sh - twoswap_sh

    out = {
        "meta": {
            "conv": CONV, "cost_bps": COST_BPS_PER_SIDE, "top_k": TOP_K,
            "lookback": CORR_LOOKBACK_DAYS,
            "mechanism": "CPM FIXED R1 M1 (vol-adj Faber rank + raw-Faber screen, min-var 3-of-4 at n_pos=4, TIP-only canary, top-4, equal-weight, best-of{SHV,IEF} safe, strict-4 breadth)",
            "clean": f"{clean_start.date()}..{end.date()}",
            "ext": f"{ext_start.date()}..{end.date()}",
            "haa_universe": HAA_UNIVERSE,
            "twoswap_universe": TWOSWAP_UNIVERSE,
            "cpm_universe": CPM_UNIVERSE,
            "swaps_applied": ["IEF->GLD", "IWM->SPHQ"],
            "swaps_omitted": ["SPY->QQQ", "VEA->EFA", "VWO->EEM"],
            "anchors": {"HAA_baseline_HAAmech": HAA_BASELINE,
                        "CPMmech_on_HAA8": CPM_ON_HAA_R1M1_ANCHOR,
                        "HAAmech_2swap": 1.028,
                        "full_CPM8": FULL_CPM_ANCHOR},
            "caveat": "GLD+SPHQ SELECTED as top-2 single drivers in prior in-sample attribution -> selection bias inflates the 2-swap in-sample lift. Point-estimates only; PIT/cached-data; single in-sample window. Bootstrap skipped per scope.",
        },
        "gates": {
            "CPMmech_HAA8_reproduces_011": {"actual": haa8_sh, "target": CPM_ON_HAA_R1M1_ANCHOR, "pass": bool(gate_haa)},
            "CPMmech_CPM8_reproduces_111": {"actual": cpm8_sh, "target": FULL_CPM_ANCHOR, "pass": bool(gate_cpm)},
        },
        "metrics": metrics,
        "turnover": turnover,
        "analysis": {
            "twoswap_CLEAN_sharpe": twoswap_sh,
            "twoswap_EXT_sharpe": metrics["CPMmech_2swap"]["EXT"]["sharpe"],
            "full_CPM_CLEAN_sharpe": cpm8_sh,
            "gap_twoswap_to_full_CPM": cpm8_sh - twoswap_sh,
            "full_gap_HAAmech_to_fullCPM": full_gap,
            "twoswap_lift_vs_HAAmech_baseline": twoswap_lift,
            "recovery_pct_of_full_CPM_gap": recovery_pct_of_full_gap,
            "cpmmech_universe_edge_HAA8_to_CPM8": cpmmech_gap,
            "twoswap_vs_CPMmech_HAA8_floor": twoswap_vs_floor,
            "pct_of_cpmmech_universe_edge_captured": pct_of_cpmmech_universe_edge,
            "remaining_swaps_marginal_lift": remaining_swaps_lift,
            "haamech_2swap_anchor": 1.028,
            "cpm_mech_amplification_vs_haa_mech_on_2swap": twoswap_sh - 1.028,
        },
    }
    out_json = Path(__file__).with_suffix(".json")
    out_json.write_text(json.dumps(out, indent=2, default=float))
    print("\nGATES:", json.dumps(out["gates"], indent=2, default=float))
    print("\nANALYSIS:", json.dumps(out["analysis"], indent=2, default=float))
    print("WROTE", out_json)
    return out


if __name__ == "__main__":
    main()
