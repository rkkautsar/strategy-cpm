# -*- coding: utf-8 -*-
"""ANALYST (read-only re production; NO prod/memo/docs touched; NO commit).

REVIEWER RECOMMENDATION #2: dual-window covariance for CPM's min-var 3-of-4
subset selector. Current min-var uses a 252d covariance (CORR_LOOKBACK_DAYS).
Hypothesis: blending in a faster 60d covariance helps the selector eject assets
undergoing sudden correlation spikes during regime shifts (e.g. 2022).

A-PRIORI EXPECTATION (stated up front): likely WITHIN-NOISE. Min-var is already
a within-noise contributor in CPM (significant only at the (U1,R1) corner) and
operates over only 4 candidates -> C(4,3)=4 triplets, a coarse decision surface.
A prior vol-window test found 60d noisier. Tested anyway to put it on record.

CONFIGS (full CPM mechanism R1 M1; ONLY the min-var covariance lookback changes;
selection trigger n_pos=4, EW weights, canary, ranker, breadth, safe UNCHANGED):
  1. CURRENT      : min-var cov = 252d                         (gate = 1.255673)
  2. BLEND-ALWAYS : min-var cov = 0.5*Cov_252d + 0.5*Cov_60d   (every month)
  3. STRESS-COND  : min-var cov = 0.5*Cov_252d + 0.5*Cov_60d   IFF stress high,
                    else 252d. Stress = SPY trailing 20d realized vol (annualized)
                    above its trailing 80th percentile (756d / expanding window,
                    PIT). Reviewer's exact proposal; a-priori 60d/80th-pct, no tuning.
  4. 60D-ONLY     : min-var cov = 60d (bracket).

GATE (CLEAN, mooex/T+1 MOO, both-252 baseline guard, 10bps):
  full CPM-8 CURRENT = 1.255673 (+/-5e-4).

MECHANISM reused byte-identical from research.cpm_mech_2swap_univ_2026_06_02
(cpm_mech_wf, CPM R1 M1, universe-parametric); ONLY the min-var covariance fed
to the 3-of-4 subset choice is swapped. With cov_mode="252" the min-var step is
byte-identical to cpm_live._min_var_subset -> reproduces 1.2557.

DISCIPLINE: point-estimates only (bootstrap skipped per scope); HIGH overfit
caution (adds a stress threshold + window DoF; a-priori 60d/80th-pct, no tuning);
PIT/cached-data; single in-sample window; CPM prod UNCHANGED (exploratory).
"""
import sys
import json
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from cpm_live import (  # noqa: E402
    load_panel, perf_metrics, sig_13612U, best_safe, faber_sma_xs,
    _ret_window, DEFAULT_CASH, COST_BPS_PER_SIDE, CORR_LOOKBACK_DAYS,
)
import exec_lag_moo_validation_2026_05_30 as H  # noqa: E402
from research.cpm_bootstrap_multimetric import _sortino_ann, _cvar_ratio_ann  # noqa: E402

CONV = "mooex"
SAFE = ["SHV", "IEF"]
TOP_K = 4
FAST_LOOKBACK = 60
STRESS_PCTL = 0.80
STRESS_RV_WIN = 20      # SPY realized-vol short window (trading days)
STRESS_PCTL_WIN = 756   # trailing window for the 80th-pct threshold (~3y), PIT
CPM_UNIVERSE = ["QQQ", "SPHQ", "EFA", "EEM", "VNQ", "GLD", "TLT", "DBC"]
FULL_CPM_ANCHOR = 1.255673


def build_stress_series(close, rv_win=STRESS_RV_WIN, pctl=STRESS_PCTL,
                        pctl_win=STRESS_PCTL_WIN):
    """Per-day boolean: SPY trailing rv_win realized vol > trailing-window 80th
    pctl of that same rv series. PIT: threshold uses only data up to each day."""
    spy = close["SPY"].ffill().pct_change()
    rv = spy.rolling(rv_win).std() * np.sqrt(252)
    # trailing percentile (min_periods modest so it activates early)
    thr = rv.rolling(pctl_win, min_periods=rv_win * 3).quantile(pctl)
    stress = (rv > thr) & thr.notna()
    return stress.fillna(False)


def min_var_subset_cov(close, sig_d, candidates, m, cov_mode, stress_high):
    """Min equal-weight portfolio variance over m-of-candidates, with a
    configurable covariance estimate. cov_mode in {252,blend,stress,60}.
    cov_mode='252' is byte-identical to cpm_live._min_var_subset(.,252,m)."""
    if len(candidates) <= m:
        return list(candidates)
    rets252 = _ret_window(close.loc[:sig_d], candidates, CORR_LOOKBACK_DAYS)
    if len(rets252) < CORR_LOOKBACK_DAYS:
        return list(candidates)
    cov252 = rets252.cov()
    if cov252.isna().any().any():
        return list(candidates)

    if cov_mode == "252":
        cov = cov252
    else:
        rets60 = _ret_window(close.loc[:sig_d], candidates, FAST_LOOKBACK)
        cov60 = rets60.cov() if len(rets60) >= FAST_LOOKBACK else None
        if cov60 is None or cov60.isna().any().any():
            cov = cov252  # degrade safely to 252d if fast window unusable
        elif cov_mode == "60":
            cov = cov60
        elif cov_mode == "blend":
            cov = 0.5 * cov252 + 0.5 * cov60
        elif cov_mode == "stress":
            cov = (0.5 * cov252 + 0.5 * cov60) if stress_high else cov252
        else:
            raise ValueError(cov_mode)

    w = 1.0 / m
    best, best_v = None, np.inf
    for combo in combinations(candidates, m):
        sub = cov.loc[list(combo), list(combo)].values
        v = float(w * w * sub.sum())
        if v < best_v:
            best_v, best = v, combo
    return list(best) if best else list(candidates)


def cpm_mech_wf_cov(close, sig_d, universe, cov_mode, stress_ser):
    """CPM mechanism (R1 M1) with dual-window cov in the min-var step ONLY.
    Mirrors research.cpm_mech_2swap_univ_2026_06_02.cpm_mech_wf exactly except
    _min_var_subset -> min_var_subset_cov(cov_mode)."""
    monthly = close.loc[:sig_d].resample("ME").last()
    safe = best_safe(monthly, sig_d, SAFE)

    tip = sig_13612U(monthly["TIP"]) if "TIP" in monthly.columns else np.nan
    if pd.isna(tip) or tip <= 0:
        return {safe: 1.0}, None

    present = [t for t in universe if t in monthly.columns]
    faber = faber_sma_xs(monthly)
    avail = [t for t in present
             if t in faber.index and pd.notna(faber[t])
             and (sig_d in close.index and pd.notna(close.loc[sig_d].get(t, np.nan)))]
    if not avail:
        return {safe: 1.0}, None

    rank_score, screen_val = {}, {}
    daily_rets = close[avail].ffill().pct_change()
    for t in avail:
        v = daily_rets[t].loc[:sig_d].tail(252).std() * np.sqrt(252)
        if pd.isna(v) or v < 1e-9:
            v = 1.0
        rank_score[t] = float(faber[t]) / v
        screen_val[t] = float(faber[t])
    if not rank_score:
        return {safe: 1.0}, None

    ranked = pd.Series(rank_score).sort_values(ascending=False)
    top_k = max(2, min(TOP_K, len(ranked)))
    top = ranked.iloc[:top_k]
    positive = top[top.index.map(lambda t: screen_val.get(t, -np.inf) > 0)]
    if len(positive) == 0:
        return {safe: 1.0}, None

    positive_picks = list(positive.index)
    n_pos = len(positive_picks)

    minvar_info = None
    if n_pos == 4:
        stress_high = bool(stress_ser.reindex([sig_d], method="ffill").iloc[0]) \
            if stress_ser is not None else False
        picks = min_var_subset_cov(close, sig_d, positive_picks, 3, cov_mode, stress_high)
        minvar_info = {"candidates": sorted(positive_picks),
                       "picks": sorted(picks), "stress_high": stress_high}
    else:
        picks = positive_picks

    risky_fraction = min(n_pos, 4) / 4.0
    safe_fraction = 1.0 - risky_fraction
    base_w = {t: 1.0 / len(picks) for t in picks}
    out = {t: w * risky_fraction for t, w in base_w.items()}
    if safe_fraction > 0:
        out[safe] = out.get(safe, 0.0) + safe_fraction
    return out, minvar_info


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


def ann_turnover(close, universe, cov_mode, stress_ser, start, end):
    sigs = monthly_sigs(close, start, end)
    prev_w, tos = {}, []
    for sd in sigs:
        w, _ = cpm_mech_wf_cov(close, sd, universe, cov_mode, stress_ser)
        keys = set(w) | set(prev_w)
        tos.append(sum(abs(w.get(k, 0.0) - prev_w.get(k, 0.0)) for k in keys))
        prev_w = w
    if len(tos) <= 1:
        return float("nan")
    return float(np.mean(tos[1:]) * 12.0)


def monthly_sigs(close, start, end):
    midx = (pd.DataFrame({"x": 1}, index=close.index)
            .groupby(pd.Grouper(freq="ME")).tail(1))
    return midx.index[(midx.index >= start) & (midx.index <= end)].tolist()


def run_series(close, daily, intraday, overnight, universe, cov_mode, stress_ser,
               start, end):
    wf = lambda sd: cpm_mech_wf_cov(close, sd, universe, cov_mode, stress_ser)[0]
    s, _ = H._segment_returns_conv(close, daily, wf, start, end, CONV,
                                   COST_BPS_PER_SIDE, intraday, overnight)
    return s


def selection_divergence(close, stress_ser, cov_mode, start, end):
    """At each n_pos==4 monthly rebal, compare min-var triplet under cov_mode vs
    252d. Report divergence rate (only meaningful at n_pos==4)."""
    sigs = monthly_sigs(close, start, end)
    n_eval = n_n4 = n_diff = n_stress = n_diff_in_stress = 0
    diff_dates = []
    for sd in sigs:
        n_eval += 1
        _, base = cpm_mech_wf_cov(close, sd, CPM_UNIVERSE, "252", stress_ser)
        _, alt = cpm_mech_wf_cov(close, sd, CPM_UNIVERSE, cov_mode, stress_ser)
        if base is None or alt is None:
            continue
        n_n4 += 1
        stressed = alt.get("stress_high", False)
        n_stress += int(stressed)
        if base["picks"] != alt["picks"]:
            n_diff += 1
            diff_dates.append({"date": str(sd.date()),
                               "base_picks": base["picks"],
                               "alt_picks": alt["picks"],
                               "stress_high": stressed})
            if stressed:
                n_diff_in_stress += 1
    return {
        "n_rebals": n_eval,
        "n_npos4_rebals": n_n4,
        "n_diverged": n_diff,
        "divergence_pct_of_npos4": 100.0 * n_diff / n_n4 if n_n4 else float("nan"),
        "n_stress_rebals": n_stress,
        "n_diverged_within_stress": n_diff_in_stress,
        "diff_dates": diff_dates,
    }


def crisis_segment(full_ser, cash, lo, hi):
    seg = full_ser.loc[(full_ser.index >= lo) & (full_ser.index <= hi)]
    if len(seg) < 5:
        return None
    m = perf_metrics(seg, cash)
    return {"sharpe": m.get("sharpe"), "maxdd": m.get("max_drawdown"),
            "cagr": m.get("cagr"), "vol": m.get("vol"),
            "total_ret": float((1 + seg).prod() - 1), "n_days": int(len(seg))}


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

    cols = sorted(set(CPM_UNIVERSE + SAFE + ["TIP", "SPY"]) & set(panel.columns))
    close = panel[cols]
    daily = close.ffill().pct_change()
    if "SPY" not in close.columns:
        raise SystemExit("FATAL: SPY needed for stress signal")

    stress_ser = build_stress_series(close)

    windows = {"CLEAN": (clean_start, end), "EXT": (ext_start, end)}
    configs = {
        "CURRENT_252d": "252",
        "BLEND_always_50_50": "blend",
        "STRESS_cond_blend": "stress",
        "FAST_60d_only": "60",
    }
    crises = {
        "COVID_2020": (pd.Timestamp("2020-02-19"), pd.Timestamp("2020-04-30")),
        "BEAR_2022": (pd.Timestamp("2022-01-01"), pd.Timestamp("2022-12-31")),
        "GFC_2008_09": (pd.Timestamp("2008-09-01"), pd.Timestamp("2009-03-31")),
    }

    metrics, turnover, crisis_metrics = {}, {}, {}
    full_series = {}
    for name, cmode in configs.items():
        metrics[name], turnover[name], crisis_metrics[name] = {}, {}, {}
        fs = run_series(close, daily, intraday, overnight, CPM_UNIVERSE,
                        cmode, stress_ser, ext_start, end)
        full_series[name] = fs
        for wn, (ws, we) in windows.items():
            seg = fs.loc[(fs.index >= ws) & (fs.index <= we)]
            metrics[name][wn] = full_met(seg, cash)
            turnover[name][wn] = ann_turnover(close, CPM_UNIVERSE, cmode,
                                              stress_ser, ws, we)
        for cn, (lo, hi) in crises.items():
            crisis_metrics[name][cn] = crisis_segment(fs, cash, lo, hi)
        c = metrics[name]["CLEAN"]
        print(f"  {name:20s} CLEAN sharpe={c['sharpe']:.4f} calmar={c['calmar']:.4f} "
              f"martin={c['martin']:.4f} maxdd={c['maxdd']*100:.2f}% to={turnover[name]['CLEAN']:.2f}")

    cur_sh = metrics["CURRENT_252d"]["CLEAN"]["sharpe"]
    gate = abs(cur_sh - FULL_CPM_ANCHOR) < 5e-4

    seldiv = {}
    for name, cmode in configs.items():
        if cmode == "252":
            continue
        seldiv[name] = {wn: selection_divergence(close, stress_ser, cmode, ws, we)
                        for wn, (ws, we) in windows.items()}

    # stress-signal coverage diagnostics (EXT)
    s_clean = stress_ser.loc[(stress_ser.index >= clean_start) & (stress_ser.index <= end)]
    stress_diag = {"pct_days_stress_CLEAN": float(100.0 * s_clean.mean()),
                   "n_stress_days_CLEAN": int(s_clean.sum())}

    out = {
        "meta": {
            "conv": CONV, "cost_bps": COST_BPS_PER_SIDE, "top_k": TOP_K,
            "baseline_lookback": CORR_LOOKBACK_DAYS, "fast_lookback": FAST_LOOKBACK,
            "stress_def": (f"SPY trailing {STRESS_RV_WIN}d realized vol (annualized) "
                           f"> trailing {STRESS_PCTL_WIN}d {int(STRESS_PCTL*100)}th "
                           f"pctl of that rv series (PIT, expanding min_periods)"),
            "mechanism": "CPM FIXED R1 M1; ONLY min-var 3-of-4 covariance estimate varies",
            "clean": f"{clean_start.date()}..{end.date()}",
            "ext": f"{ext_start.date()}..{end.date()}",
            "cpm_universe": CPM_UNIVERSE,
            "anchor_full_CPM8": FULL_CPM_ANCHOR,
            "a_priori_expectation": "WITHIN-NOISE (min-var already within-noise; 4 candidates / C(4,3)=4 triplets; 60d found noisier in prior vol-window test)",
            "caveat": "Single in-sample window; adds stress-threshold + window DoF (a-priori 60d/80th-pct, no tuning); point-estimates only, bootstrap skipped per scope; PIT/cached-data; CPM prod UNCHANGED (exploratory).",
        },
        "gate_current_reproduces_full_CPM8": {
            "actual": cur_sh, "target": FULL_CPM_ANCHOR, "pass": bool(gate)},
        "metrics": metrics,
        "turnover": turnover,
        "crisis_metrics": crisis_metrics,
        "selection_divergence": seldiv,
        "stress_diag": stress_diag,
        "summary_vs_current": {
            name: {
                "d_sharpe_CLEAN": metrics[name]["CLEAN"]["sharpe"] - cur_sh,
                "d_calmar_CLEAN": metrics[name]["CLEAN"]["calmar"] - metrics["CURRENT_252d"]["CLEAN"]["calmar"],
                "d_martin_CLEAN": metrics[name]["CLEAN"]["martin"] - metrics["CURRENT_252d"]["CLEAN"]["martin"],
                "d_maxdd_CLEAN": metrics[name]["CLEAN"]["maxdd"] - metrics["CURRENT_252d"]["CLEAN"]["maxdd"],
                "d_sharpe_EXT": metrics[name]["EXT"]["sharpe"] - metrics["CURRENT_252d"]["EXT"]["sharpe"],
            } for name in configs if name != "CURRENT_252d"
        },
    }
    out_json = Path(__file__).with_suffix(".json")
    out_json.write_text(json.dumps(out, indent=2, default=float))
    print("\nGATE:", json.dumps(out["gate_current_reproduces_full_CPM8"], indent=2, default=float))
    print("STRESS_DIAG:", json.dumps(stress_diag, indent=2, default=float))
    for name in seldiv:
        print(f"SELDIV {name} CLEAN:",
              json.dumps({k: v for k, v in seldiv[name]["CLEAN"].items() if k != "diff_dates"},
                         default=float))
    print("SUMMARY:", json.dumps(out["summary_vs_current"], indent=2, default=float))
    print("WROTE", out_json)
    return out


if __name__ == "__main__":
    main()
