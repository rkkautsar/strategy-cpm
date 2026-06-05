# -*- coding: utf-8 -*-
"""ANALYST (read-only re production; NO prod/memo/docs touched; NO commit).

QUESTION: User dislikes IWM (small-cap: adds vol, weak size premium). Test
making SPY the SOLE US equity. IEF->GLD ALWAYS (IEF is a bond; it belongs in
the SAFE pool only, not the risky momentum universe -- consistent with CPM-8
which excludes IEF from risky and keeps it safe). Safe selector unchanged =
best of {SHV, IEF}.

  G1  IEF->GLD, KEEP IWM (8 risky): {SPY, IWM, VEA, VWO, VNQ, GLD, DBC, TLT}
      HAA mechanism (R0 M0) AND CPM mechanism (R1 M1).

  G2  IEF->GLD, DROP IWM = SPY sole US equity (7 risky) [USER TARGET]:
      {SPY, VEA, VWO, VNQ, GLD, DBC, TLT}. HAA mech AND CPM mech.
      top-4 of 7 then min-var 3-of-4 under CPM mech.

Compare G1 vs G2 to isolate the IWM-drop effect (GLD already in, IEF already
out). How does the clean SPY+GLD risky universe (no IEF, no small-cap, no
QQQ/SPHQ tilt) compare to full CPM?

GATES (CLEAN, mooex/T+1 MOO, both-252, 10bps):
  HAA mech on HAA-8  = 0.8670     (uni_wf gate)
  CPM mech on CPM-8  = 1.255673   (cpm_mech_wf gate)

ANCHORS for comparison:
  HAA-8 HAA-mech              0.8670
  CPM-mech-on-HAA-8          0.9399
  HAA-mech+GLD+SPHQ          1.028   (HAAmech 2-swap)
  CPM-mech+GLD+SPHQ 2-swap   1.200
  full CPM-8                 1.2557

MECHANISM wf functions are byte-identical to the verified harnesses:
  uni_wf       <- cpm_haa_asset_swap_2026_06_02.py (HAA R0 M0)
  cpm_mech_wf  <- cpm_mech_2swap_univ_2026_06_02.py (CPM R1 M1)

DISCIPLINE: reproduce anchors first (gate); point-estimates only (bootstrap
skipped per scope); HIGH overfit caution -- exploratory universe-design, single
in-sample window, PIT/cached data; CPM prod unchanged.
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
# G1: IEF->GLD, KEEP IWM (8 risky); IEF stays safe-pool only
G1_UNIVERSE = ["SPY", "IWM", "VEA", "VWO", "VNQ", "GLD", "DBC", "TLT"]
# G2: IEF->GLD, DROP IWM -> SPY sole US equity (7 risky) [USER TARGET]
G2_UNIVERSE = ["SPY", "VEA", "VWO", "VNQ", "GLD", "DBC", "TLT"]

# anchors
HAA_ANCHOR = 0.8670
CPM8_ANCHOR = 1.255673
CPMmech_HAA8_ANCHOR = 0.9399
HAAmech_2swap_ANCHOR = 1.028
CPMmech_2swap_ANCHOR = 1.200


# ----------------------- mechanism weight functions -----------------------
def uni_wf(close, sig_d, universe):
    """HAA mechanism (R0 M0): 13612U dual momentum, TIP-only canary, top-4,
    equal-weight, no vol-adj ranker, no min-var. Byte-identical to
    cpm_haa_asset_swap_2026_06_02.uni_wf."""
    monthly = close.loc[:sig_d].resample("ME").last()
    safe = best_safe(monthly, sig_d, SAFE)
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


def cpm_mech_wf(close, sig_d, universe):
    """CPM mechanism (R1 M1): vol-adj Faber ranker + raw-Faber screen, min-var
    3-of-4 at n_pos=4, TIP-only canary, top-4, equal-weight, best-of{SHV,IEF}
    safe, strict-4 breadth. Byte-identical to
    cpm_mech_2swap_univ_2026_06_02.cpm_mech_wf."""
    monthly = close.loc[:sig_d].resample("ME").last()
    safe = best_safe(monthly, sig_d, SAFE)
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


# ----------------------------- metrics -----------------------------------
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


def ann_turnover(close, wf, start, end):
    monthly_idx = (pd.DataFrame({"x": 1}, index=close.index)
                   .groupby(pd.Grouper(freq="ME")).tail(1))
    sigs = monthly_idx.index[(monthly_idx.index >= start)
                             & (monthly_idx.index <= end)].tolist()
    prev_w, tos = {}, []
    for sd in sigs:
        w = wf(sd)
        keys = set(w) | set(prev_w)
        tos.append(sum(abs(w.get(k, 0.0) - prev_w.get(k, 0.0)) for k in keys))
        prev_w = w
    if len(tos) <= 1:
        return float("nan")
    return float(np.mean(tos[1:]) * 12.0)


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

    allu = set(HAA_UNIVERSE + CPM_UNIVERSE + G1_UNIVERSE
               + G2_UNIVERSE + SAFE + ["TIP"])
    cols = sorted(allu & set(panel.columns))
    close = panel[cols]
    daily = close.ffill().pct_change()
    for a in ("GLD",):
        if a not in close.columns:
            raise SystemExit(f"FATAL: {a} not in panel")

    windows = {"CLEAN": (clean_start, end), "EXT": (ext_start, end)}

    # name -> (mechanism_fn, universe)
    configs = {
        # gates
        "GATE_HAAmech_HAA8": (uni_wf, list(HAA_UNIVERSE)),       # -> 0.8670
        "GATE_CPMmech_CPM8": (cpm_mech_wf, list(CPM_UNIVERSE)),  # -> 1.255673
        # experiments: G1 (keep IWM) vs G2 (drop IWM), each x {HAA, CPM} mech
        "G1_HAAmech_keepIWM": (uni_wf, list(G1_UNIVERSE)),
        "G1_CPMmech_keepIWM": (cpm_mech_wf, list(G1_UNIVERSE)),
        "G2_HAAmech_dropIWM": (uni_wf, list(G2_UNIVERSE)),
        "G2_CPMmech_dropIWM": (cpm_mech_wf, list(G2_UNIVERSE)),
    }

    metrics, turnover = {}, {}
    for name, (mech, uni) in configs.items():
        wf = lambda sd, m=mech, u=uni: m(close, sd, u)
        metrics[name], turnover[name] = {}, {}
        full_ser = run_series(close, daily, intraday, overnight, wf, ext_start, end)
        for wn, (ws, we) in windows.items():
            seg = full_ser.loc[(full_ser.index >= ws) & (full_ser.index <= we)]
            metrics[name][wn] = full_met(seg, cash)
            wf_w = lambda sd, m=mech, u=uni: m(close, sd, u)
            turnover[name][wn] = ann_turnover(close, wf_w, ws, we)
        c = metrics[name]["CLEAN"]
        print(f"  {name:22s} CLEAN sh={c['sharpe']:.4f} sortino={c['sortino']:.4f} "
              f"calmar={c['calmar']:.4f} mdd={c['maxdd']*100:.2f}% cagr={c['cagr']*100:.2f}%")

    haa_gate = metrics["GATE_HAAmech_HAA8"]["CLEAN"]["sharpe"]
    cpm_gate = metrics["GATE_CPMmech_CPM8"]["CLEAN"]["sharpe"]
    gate_haa_ok = abs(haa_gate - HAA_ANCHOR) < 5e-4
    gate_cpm_ok = abs(cpm_gate - CPM8_ANCHOR) < 5e-4

    g1h = metrics["G1_HAAmech_keepIWM"]["CLEAN"]["sharpe"]
    g1c = metrics["G1_CPMmech_keepIWM"]["CLEAN"]["sharpe"]
    g2h = metrics["G2_HAAmech_dropIWM"]["CLEAN"]["sharpe"]
    g2c = metrics["G2_CPMmech_dropIWM"]["CLEAN"]["sharpe"]

    out = {
        "meta": {
            "conv": CONV, "cost_bps": COST_BPS_PER_SIDE, "top_k": TOP_K,
            "lookback": CORR_LOOKBACK_DAYS,
            "clean": f"{clean_start.date()}..{end.date()}",
            "ext": f"{ext_start.date()}..{end.date()}",
            "universes": {
                "HAA8": HAA_UNIVERSE, "CPM8": CPM_UNIVERSE,
                "G1_keepIWM_8risky": G1_UNIVERSE,
                "G2_dropIWM_7risky": G2_UNIVERSE,
                "note": "IEF->GLD in G1/G2; IEF safe-pool only",
            },
            "anchors": {
                "HAA8_HAAmech": HAA_ANCHOR, "CPMmech_HAA8": CPMmech_HAA8_ANCHOR,
                "HAAmech_2swap": HAAmech_2swap_ANCHOR,
                "CPMmech_2swap": CPMmech_2swap_ANCHOR, "full_CPM8": CPM8_ANCHOR,
            },
            "caveat": "Exploratory universe-design. Point-estimates only (bootstrap skipped). HIGH overfit caution; single in-sample window; PIT/cached data. CPM prod unchanged.",
        },
        "gates": {
            "HAAmech_HAA8_reproduces_0.8670": {"actual": haa_gate, "target": HAA_ANCHOR, "pass": bool(gate_haa_ok)},
            "CPMmech_CPM8_reproduces_1.2557": {"actual": cpm_gate, "target": CPM8_ANCHOR, "pass": bool(gate_cpm_ok)},
        },
        "metrics": metrics,
        "turnover": turnover,
        "analysis": {
            "G1_HAAmech_CLEAN_sharpe": g1h,
            "G1_CPMmech_CLEAN_sharpe": g1c,
            "G2_HAAmech_CLEAN_sharpe": g2h,
            "G2_CPMmech_CLEAN_sharpe": g2c,
            "IWM_drop_effect_HAAmech_G2_minus_G1": g2h - g1h,
            "IWM_drop_effect_CPMmech_G2_minus_G1": g2c - g1c,
            "G1_HAAmech_vs_HAA8_anchor": g1h - HAA_ANCHOR,
            "G1_CPMmech_vs_CPMmech_HAA8_anchor": g1c - CPMmech_HAA8_ANCHOR,
            "G2_CPMmech_vs_CPMmech_2swap": g2c - CPMmech_2swap_ANCHOR,
            "G2_CPMmech_vs_full_CPM8": g2c - CPM8_ANCHOR,
            "cost_of_dropping_SPHQ_QQQ_tilts_G2_vs_fullCPM": CPM8_ANCHOR - g2c,
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
