#!/usr/bin/env python3
"""
CPM Robust Pair-Selection Engine: parameter-free regime-robust covariance vs
production 504d sample-covariance min-variance pair.

Hypothesis: a PARAMETER-FREE robust covariance estimator in CPM pair selection
(folding the "re-pick a still-diversified pair" idea into the optimizer with NO
threshold and NO safe-gating) beats the static 504d sample-cov min-var pair on
risk-adjusted terms, in the 60/40 two-sleeve CPM+BULL baseline.

Variants (vary ONLY the covariance / pair-selection estimator; canary +
positive-Faber filter + EAA rank + K=4 + 50/50 pair FIXED):
  E0 (PROD): 504d SAMPLE covariance, min-variance 50/50 pair.
  E1: Ledoit-Wolf shrinkage covariance (analytic intensity), min-variance pair.
  E2: min-correlation pair (lowest 504d pairwise corr) = re-pick-diversified.
  E3 (ref): constant-correlation-target LW shrinkage (analytic), min-var pair.

Measurement only. Production files untouched: we monkeypatch cpm_live.min_vol_pair.

Usage: .venv/bin/python research/cpm_robust_pair_engine.py
"""
from __future__ import annotations

import sys
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cpm_live
from cpm_live import (
    load_panel, run_cpm_backtest, perf_metrics,
    RISKY_UNIVERSE, SAFE_POOL, CANARY_ASSETS, DEFAULT_CASH, CORR_LOOKBACK_DAYS,
)
from bull_spy_live import run_bull_spy_backtest
from sklearn.covariance import LedoitWolf

PROD_MIN_VOL_PAIR = cpm_live.min_vol_pair  # save to restore

# Windows
START_CL = pd.Timestamp("2008-05-30")
END_CL = pd.Timestamp("2026-05-22")
START_ST = pd.Timestamp("1999-03-10")
END_ST = pd.Timestamp("2026-05-22")

FINDINGS = Path("research/cpm_robust_pair_engine_findings.md")
LOG = []


def log(s=""):
    print(s)
    LOG.append(str(s))


# ---------- Pair-selection estimator variants ----------
# Signature must match cpm_live.min_vol_pair:
#   (daily, candidates, lookback, momenta=None, var_weight=None) -> (a, b) | None

def _clean_returns(daily, candidates, lookback):
    """Replicate prod return-window construction; return (rets_raw, rets_dropna)."""
    rets = daily[candidates].pct_change().dropna(how="all").tail(lookback)
    if len(rets) < lookback:
        return None, None
    return rets, rets.dropna()


def _pick_min_var(cov, candidates):
    best, best_v = None, np.inf
    for a, b in combinations(candidates, 2):
        try:
            v = 0.25 * cov.loc[a, a] + 0.25 * cov.loc[b, b] + 0.5 * cov.loc[a, b]
        except KeyError:
            continue
        if pd.notna(v) and v < best_v:
            best_v, best = v, (a, b)
    return best


def pair_E0(daily, candidates, lookback, momenta=None, var_weight=None):
    """PROD: 504d sample covariance, min-variance pair."""
    if len(candidates) < 2:
        return None
    rets, _ = _clean_returns(daily, candidates, lookback)
    if rets is None:
        return None
    cov = rets.cov()
    if cov.isna().any().any():
        return None
    return _pick_min_var(cov, candidates)


def pair_E1(daily, candidates, lookback, momenta=None, var_weight=None):
    """Ledoit-Wolf shrinkage covariance (analytic intensity), min-variance pair."""
    if len(candidates) < 2:
        return None
    rets, rclean = _clean_returns(daily, candidates, lookback)
    if rets is None or rclean is None or len(rclean) < 2:
        return None
    X = rclean[candidates].values
    if np.isnan(X).any():
        return None
    try:
        lw = LedoitWolf(assume_centered=False).fit(X)
    except Exception:
        return None
    cov = pd.DataFrame(lw.covariance_, index=candidates, columns=candidates)
    return _pick_min_var(cov, candidates)


def pair_E2(daily, candidates, lookback, momenta=None, var_weight=None):
    """Min-correlation pair: lowest 504d pairwise sample correlation (50/50)."""
    if len(candidates) < 2:
        return None
    rets, _ = _clean_returns(daily, candidates, lookback)
    if rets is None:
        return None
    corr = rets.corr()
    if corr.isna().any().any():
        return None
    best, best_c = None, np.inf
    for a, b in combinations(candidates, 2):
        try:
            c = corr.loc[a, b]
        except KeyError:
            continue
        if pd.notna(c) and c < best_c:
            best_c, best = c, (a, b)
    return best


def _cc_shrinkage(rclean, candidates):
    """Constant-correlation-target Ledoit-Wolf shrinkage (analytic intensity).
    Ledoit & Wolf (2003) 'Honey, I Shrunk the Sample Covariance Matrix'.
    Returns shrunk covariance DataFrame, or None on failure."""
    X = rclean[candidates].values
    t, n = X.shape
    if t < 2 or n < 2 or np.isnan(X).any():
        return None
    xm = X - X.mean(axis=0)
    sample = (xm.T @ xm) / t  # MLE sample cov (1/T)
    var = np.diag(sample)
    std = np.sqrt(var)
    outer_std = np.outer(std, std)
    if (outer_std == 0).any():
        return None
    corr = sample / outer_std
    rbar = (corr.sum() - n) / (n * (n - 1))  # mean off-diag corr
    # Constant-correlation target F
    F = rbar * outer_std
    np.fill_diagonal(F, var)
    # pi: sum of asymptotic variances of sample cov entries
    y = xm ** 2
    pi_mat = (y.T @ y) / t - sample ** 2
    pi = pi_mat.sum()
    # rho: estimate of cov between sample cov and shrinkage target
    term = ((xm ** 3).T @ xm) / t - var[:, None] * sample
    np.fill_diagonal(term, 0.0)
    theta_mat = term
    rho_diag = np.diag(pi_mat).sum()
    ratio = outer_std / outer_std.T  # std_i/std_j
    rho_off = (rbar / 2.0) * (
        (ratio * theta_mat) + (ratio.T * theta_mat.T)
    ).sum()
    rho = rho_diag + rho_off
    # gamma: misfit of target
    gamma = np.linalg.norm(sample - F, "fro") ** 2
    if gamma <= 0:
        return None
    kappa = (pi - rho) / gamma
    delta = max(0.0, min(1.0, kappa / t))
    shrunk = delta * F + (1.0 - delta) * sample
    return pd.DataFrame(shrunk, index=candidates, columns=candidates)


def pair_E3(daily, candidates, lookback, momenta=None, var_weight=None):
    """Constant-correlation-target shrinkage (analytic), min-variance pair."""
    if len(candidates) < 2:
        return None
    rets, rclean = _clean_returns(daily, candidates, lookback)
    if rets is None or rclean is None or len(rclean) < 2:
        return None
    cov = _cc_shrinkage(rclean, candidates)
    if cov is None or cov.isna().any().any():
        return None
    return _pick_min_var(cov, candidates)


VARIANTS = {
    "E0_PROD_sample": pair_E0,
    "E1_LedoitWolf": pair_E1,
    "E2_min_corr": pair_E2,
    "E3_const_corr": pair_E3,
}


# ---------- Helpers ----------

def turnover_annual(weights_history):
    if not weights_history:
        return float("nan")
    tos = []
    for i in range(len(weights_history)):
        prev = weights_history[i - 1]["weights"] if i > 0 else {}
        curr = weights_history[i]["weights"]
        keys = set(curr) | set(prev)
        to = 0.5 * sum(abs(curr.get(k, 0.0) - prev.get(k, 0.0)) for k in keys)
        tos.append(to)
    return float(np.mean(tos) * 12.0)


def cal_metrics(daily, cash_daily, year):
    seg = daily.loc[f"{year}-01-01":f"{year}-12-31"]
    if seg.empty:
        return None
    cret = (1.0 + seg).prod() - 1.0
    m = perf_metrics(seg, cash_daily)
    return {"ret": cret, "sharpe": m.get("sharpe"), "maxdd": m.get("max_drawdown")}


def derive_pick(weights_history):
    """Map sig_d -> chosen risky pair (tuple) or None for defensive months."""
    out = {}
    for h in weights_history:
        if h.get("regime") != "RISK_ON":
            out[h["sig_d"]] = None
            continue
        risky = [k for k, v in h["weights"].items()
                 if abs(v - 0.5) < 1e-9 and k not in SAFE_POOL and k != DEFAULT_CASH]
        out[h["sig_d"]] = tuple(sorted(risky)) if len(risky) == 2 else None
    return out


def run_variant(panel, fn, start, end, cost_bps=10):
    cpm_live.min_vol_pair = fn
    try:
        rets, wh = run_cpm_backtest(panel, start, end, cost_bps=cost_bps)
    finally:
        cpm_live.min_vol_pair = PROD_MIN_VOL_PAIR
    return rets, wh


def fmt_metrics_row(name, scope, m, turnover=None):
    to = f"{turnover*100:.0f}%" if turnover is not None and pd.notna(turnover) else "-"
    return (f"| {name} | {scope} | {m['sharpe']:.3f} | {m['excess_sharpe']:.3f} | "
            f"{m['cagr']*100:.2f}% | {m['vol']*100:.2f}% | {m['max_drawdown']*100:.2f}% | "
            f"{m['calmar']:.2f} | {to} |")


def main():
    log("Loading panel ...")
    panel = load_panel(start=pd.Timestamp("1995-01-01"))
    cash_daily = panel[DEFAULT_CASH].ffill().pct_change().dropna()
    log(f"Panel: {panel.index[0].date()} -> {panel.index[-1].date()}")

    # BULL sleeve (constant across variants) for both windows
    log("Computing BULL sleeve (constant across variants) ...")
    bull_cl = run_bull_spy_backtest(panel, START_CL, END_CL)
    bull_st = run_bull_spy_backtest(panel, START_ST, END_ST)

    # ---- E0 reproduction check ----
    log("\n=== E0 reproduction check ===")
    cpm0_cl, wh0_cl = run_variant(panel, pair_E0, START_CL, END_CL)
    m0_cl = perf_metrics(cpm0_cl, cash_daily)
    common_cl = cpm0_cl.index.intersection(bull_cl.index)
    blend0_cl = 0.60 * cpm0_cl.reindex(common_cl) + 0.40 * bull_cl.reindex(common_cl)
    bm0_cl = perf_metrics(blend0_cl, cash_daily)
    log(f"E0 CPM     : Sharpe {m0_cl['sharpe']:.3f} (target 1.263), CAGR {m0_cl['cagr']*100:.2f}% (target 14.58%), MaxDD {m0_cl['max_drawdown']*100:.2f}% (target -15.41%)")
    log(f"E0 60/40   : Sharpe {bm0_cl['sharpe']:.3f} (target 1.347), CAGR {bm0_cl['cagr']*100:.2f}% (target 13.59%), MaxDD {bm0_cl['max_drawdown']*100:.2f}% (target -9.82%)")

    repro_ok = (abs(m0_cl['sharpe'] - 1.263) < 0.01 and abs(m0_cl['cagr'] * 100 - 14.58) < 0.1
                and abs(bm0_cl['sharpe'] - 1.347) < 0.01 and abs(bm0_cl['max_drawdown'] * 100 + 9.82) < 0.1)
    log(f"E0 reproduction: {'PASS' if repro_ok else 'FAIL'}")

    # ---- Run all variants both windows; collect metrics + picks ----
    results = {}   # variant -> dict
    picks = {}     # variant -> {window: {sig_d: pair}}
    for name, fn in VARIANTS.items():
        log(f"\nRunning {name} ...")
        cpm_cl, wh_cl = run_variant(panel, fn, START_CL, END_CL)
        cpm_st, wh_st = run_variant(panel, fn, START_ST, END_ST)
        cc = cpm_cl.index.intersection(bull_cl.index)
        cs = cpm_st.index.intersection(bull_st.index)
        blend_cl = 0.60 * cpm_cl.reindex(cc) + 0.40 * bull_cl.reindex(cc)
        blend_st = 0.60 * cpm_st.reindex(cs) + 0.40 * bull_st.reindex(cs)
        results[name] = {
            "cpm_cl": cpm_cl, "cpm_st": cpm_st,
            "blend_cl": blend_cl, "blend_st": blend_st,
            "m_cpm_cl": perf_metrics(cpm_cl, cash_daily),
            "m_cpm_st": perf_metrics(cpm_st, cash_daily),
            "m_blend_cl": perf_metrics(blend_cl, cash_daily),
            "m_blend_st": perf_metrics(blend_st, cash_daily),
            "to_cl": turnover_annual(wh_cl),
            "to_st": turnover_annual(wh_st),
            "cpm_2022": cal_metrics(cpm_cl, cash_daily, 2022),
            "cpm_2008": cal_metrics(cpm_st, cash_daily, 2008),
            "blend_2022": cal_metrics(blend_cl, cash_daily, 2022),
            "blend_2008": cal_metrics(blend_st, cash_daily, 2008),
        }
        picks[name] = {"cl": derive_pick(wh_cl), "st": derive_pick(wh_st)}

    # ---- Re-pick diagnostic (item 2) ----
    log("\n=== Re-pick diagnostic ===")
    diag = repick_diagnostic(panel, picks, cash_daily)

    # ---- Walk-forward stability (item 3) ----
    log("\n=== Walk-forward / sub-period stability ===")
    wf = walk_forward(results, cash_daily)

    write_findings(results, diag, wf, repro_ok, m0_cl, bm0_cl)
    log(f"\nWrote {FINDINGS}")


def _fwd_window_returns(panel, sig_d, horizon=21):
    """Forward per-asset cumulative returns over the next `horizon` trading days."""
    daily = panel.ffill().pct_change()
    future = daily.index[daily.index > sig_d][:horizon]
    if len(future) == 0:
        return None, None
    seg = daily.loc[future]
    cum = (1.0 + seg).prod() - 1.0
    return seg, cum


def _trailing_corr(panel, sig_d, a, b, lookback=CORR_LOOKBACK_DAYS):
    daily = panel.ffill().pct_change()
    sub = daily.loc[:sig_d, [a, b]].dropna().tail(lookback)
    if len(sub) < 30:
        return np.nan
    return sub[a].corr(sub[b])


def _fwd_corr(panel, sig_d, a, b, horizon=21):
    daily = panel.ffill().pct_change()
    future = daily.index[daily.index > sig_d][:horizon]
    if len(future) < 5:
        return np.nan
    sub = daily.loc[future, [a, b]].dropna()
    if len(sub) < 5:
        return np.nan
    return sub[a].corr(sub[b])


def repick_diagnostic(panel, picks, cash_daily):
    """For months where E0's chosen pair had a POOR forward outcome, did E1/E2/E3
    pick a DIFFERENT pair, and was that pair's forward outcome better?"""
    daily = panel.ffill().pct_change()

    def pair_fwd_5050(sig_d, pair, horizon=21):
        if pair is None:
            return np.nan
        future = daily.index[daily.index > sig_d][:horizon]
        if len(future) == 0:
            return np.nan
        legs = []
        for leg in pair:
            if leg not in daily.columns:
                return np.nan
            r = (1.0 + daily.loc[future, leg]).prod() - 1.0
            legs.append(r)
        return 0.5 * legs[0] + 0.5 * legs[1]

    e0 = picks["E0_PROD_sample"]["cl"]
    rows = {}
    for cand in ["E1_LedoitWolf", "E2_min_corr", "E3_const_corr"]:
        ev = picks[cand]["cl"]
        n_months = 0
        n_diverge = 0
        n_poor = 0           # E0 risk-on months with poor forward outcome
        n_poor_diverge = 0   # of those, where cand picked a different pair
        n_poor_div_better = 0  # of those, cand pair forward >= E0 pair forward
        div_fwd_delta = []   # cand_fwd - e0_fwd across ALL divergence months
        poor_div_delta = []  # cand_fwd - e0_fwd in poor-and-diverge months
        for sig_d, e0pair in e0.items():
            if e0pair is None:
                continue
            n_months += 1
            cpair = ev.get(sig_d)
            diverged = cpair is not None and cpair != e0pair
            if diverged:
                n_diverge += 1
            e0_fwd = pair_fwd_5050(sig_d, e0pair)
            # poor outcome: both legs down OR forward corr >> trailing corr
            both_down = False
            future = daily.index[daily.index > sig_d][:21]
            if len(future) > 0 and all(l in daily.columns for l in e0pair):
                leg_rets = [(1.0 + daily.loc[future, l]).prod() - 1.0 for l in e0pair]
                both_down = all(r < 0 for r in leg_rets)
            tcorr = _trailing_corr(panel, sig_d, e0pair[0], e0pair[1])
            fcorr = _fwd_corr(panel, sig_d, e0pair[0], e0pair[1])
            corr_break = (pd.notna(tcorr) and pd.notna(fcorr) and (fcorr - tcorr) > 0.30)
            poor = both_down or corr_break
            if diverged and pd.notna(e0_fwd):
                cfwd = pair_fwd_5050(sig_d, cpair)
                if pd.notna(cfwd):
                    div_fwd_delta.append(cfwd - e0_fwd)
            if poor:
                n_poor += 1
                if diverged:
                    n_poor_diverge += 1
                    cfwd = pair_fwd_5050(sig_d, cpair)
                    if pd.notna(cfwd) and pd.notna(e0_fwd):
                        poor_div_delta.append(cfwd - e0_fwd)
                        if cfwd >= e0_fwd:
                            n_poor_div_better += 1
        rows[cand] = {
            "n_months": n_months,
            "n_diverge": n_diverge,
            "diverge_pct": n_diverge / n_months if n_months else float("nan"),
            "mean_div_fwd_delta_bps": (np.mean(div_fwd_delta) * 1e4) if div_fwd_delta else float("nan"),
            "n_poor": n_poor,
            "n_poor_diverge": n_poor_diverge,
            "n_poor_div_better": n_poor_div_better,
            "mean_poor_div_delta_bps": (np.mean(poor_div_delta) * 1e4) if poor_div_delta else float("nan"),
        }
        log(f"{cand}: diverge {n_diverge}/{n_months} ({rows[cand]['diverge_pct']*100:.1f}%); "
            f"E0 poor months {n_poor}; of those diverged {n_poor_diverge}, "
            f"better {n_poor_div_better}; mean poor-div fwd delta {rows[cand]['mean_poor_div_delta_bps']:.1f}bps")
    return rows


def walk_forward(results, cash_daily):
    """Rolling sub-period Sharpe stability + ex-crisis recompute."""
    out = {}
    e0_cl = results["E0_PROD_sample"]["blend_cl"]
    # 3-year (756d) rolling Sharpe on blend; count windows where cand > E0
    def roll_sharpe(s, win=756):
        return (s.rolling(win).mean() * 252) / (s.rolling(win).std() * np.sqrt(252))
    rs_e0 = roll_sharpe(e0_cl)
    for cand in ["E1_LedoitWolf", "E2_min_corr", "E3_const_corr"]:
        cl = results[cand]["blend_cl"]
        rs = roll_sharpe(cl)
        common = rs_e0.dropna().index.intersection(rs.dropna().index)
        diff = (rs.reindex(common) - rs_e0.reindex(common)).dropna()
        win_frac = float((diff > 0).mean()) if len(diff) else float("nan")
        # ex-crisis: exclude calendar 2008 and 2020 from blend daily, recompute Sharpe
        def ex_crisis(s):
            mask = ~s.index.year.isin([2008, 2020])
            return perf_metrics(s[mask], cash_daily)
        m_full = results[cand]["m_blend_cl"]
        m_ex = ex_crisis(cl)
        m_e0_full = results["E0_PROD_sample"]["m_blend_cl"]
        m_e0_ex = ex_crisis(e0_cl)
        out[cand] = {
            "roll_win_frac": win_frac,
            "roll_mean_diff": float(diff.mean()) if len(diff) else float("nan"),
            "roll_min_diff": float(diff.min()) if len(diff) else float("nan"),
            "roll_max_diff": float(diff.max()) if len(diff) else float("nan"),
            "sharpe_full_delta": m_full["sharpe"] - m_e0_full["sharpe"],
            "sharpe_excrisis_delta": m_ex["sharpe"] - m_e0_ex["sharpe"],
            "sharpe_excrisis": m_ex["sharpe"],
            "sharpe_e0_excrisis": m_e0_ex["sharpe"],
        }
        log(f"{cand}: rolling-3y blend Sharpe > E0 in {win_frac*100:.0f}% of windows; "
            f"full delta {out[cand]['sharpe_full_delta']:+.3f}, ex-2008/2020 delta {out[cand]['sharpe_excrisis_delta']:+.3f}")
    return out


def write_findings(results, diag, wf, repro_ok, m0_cl, bm0_cl):
    L = []
    L.append("# CPM Robust Pair-Selection Engine: Parameter-Free Covariance vs PROD Min-Var\n")
    L.append("Tests whether a **parameter-free regime-robust covariance** in CPM pair selection "
             "beats the static 504d sample-covariance min-variance pair, folding the SIG-B "
             "\"re-pick a still-diversified pair\" idea into the optimizer with **no threshold "
             "and no safe-gating**. Evaluated in the 60/40 two-sleeve CPM+BULL baseline.\n")
    L.append("Fixed: canary (HYG OR TIP), positive-Faber filter, EAA vol-adjusted rank, K=4 "
             "candidates, 50/50 pair sizing. Varied: ONLY the covariance / pair-selection estimator.\n")
    L.append("Variants:")
    L.append("- **E0 (PROD)**: 504d sample covariance, min-variance 50/50 pair.")
    L.append("- **E1**: Ledoit-Wolf shrinkage covariance (analytic intensity), min-variance pair.")
    L.append("- **E2**: min-correlation pair (lowest 504d pairwise corr) -- re-pick-diversified directly.")
    L.append("- **E3 (ref)**: constant-correlation-target LW shrinkage (analytic), min-variance pair.\n")

    L.append(f"**E0 reproduction:** {'PASS' if repro_ok else 'FAIL'} "
             f"(CPM Sharpe {m0_cl['sharpe']:.3f}/14.58% CAGR target; "
             f"60/40 blend Sharpe {bm0_cl['sharpe']:.3f}/{bm0_cl['max_drawdown']*100:.2f}% MaxDD).\n")

    # Table 1: CPM standalone
    L.append("\n## 1. CPM standalone (clean + stress windows)\n")
    L.append("| Variant | Window | Raw Sharpe | Excess Sharpe | CAGR | Vol | MaxDD | Calmar | Turnover |")
    L.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for name in VARIANTS:
        r = results[name]
        L.append(fmt_metrics_row(name, "Clean", r["m_cpm_cl"], r["to_cl"]))
        L.append(fmt_metrics_row(name, "Stress", r["m_cpm_st"], r["to_st"]))

    # Table 2: 60/40 blend
    L.append("\n## 2. 60/40 CPM+BULL blend (clean + stress windows)\n")
    L.append("| Variant | Window | Raw Sharpe | Excess Sharpe | CAGR | Vol | MaxDD | Calmar |")
    L.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for name in VARIANTS:
        r = results[name]
        for scope, key in [("Clean", "m_blend_cl"), ("Stress", "m_blend_st")]:
            m = r[key]
            L.append(f"| {name} | {scope} | {m['sharpe']:.3f} | {m['excess_sharpe']:.3f} | "
                     f"{m['cagr']*100:.2f}% | {m['vol']*100:.2f}% | {m['max_drawdown']*100:.2f}% | {m['calmar']:.2f} |")

    # Table 3: crisis-year sub-periods
    L.append("\n## 3. Crisis sub-periods (2022 calendar, 2008 calendar)\n")
    L.append("| Variant | Cell | 2022 Return | 2022 Sharpe | 2022 MaxDD | 2008 Return | 2008 Sharpe | 2008 MaxDD |")
    L.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for name in VARIANTS:
        r = results[name]
        for cell, c22, c08 in [("CPM", r["cpm_2022"], r["cpm_2008"]),
                                ("Blend", r["blend_2022"], r["blend_2008"])]:
            def g(d, k):
                if d is None or d.get(k) is None or pd.isna(d.get(k)):
                    return "-"
                return f"{d[k]*100:.2f}%" if k != "sharpe" else f"{d[k]:.3f}"
            L.append(f"| {name} | {cell} | {g(c22,'ret')} | {g(c22,'sharpe')} | {g(c22,'maxdd')} | "
                     f"{g(c08,'ret')} | {g(c08,'sharpe')} | {g(c08,'maxdd')} |")

    # Section 4: re-pick diagnostic
    L.append("\n## 4. Re-pick diagnostic (does divergence from E0 help?)\n")
    L.append("Clean window, CPM risk-on months only. \"E0 poor\" = E0 pair had both legs down "
             "over the forward 21d holding period OR forward-21d pair correlation exceeded its "
             "trailing-504d correlation by >0.30 (diversification break). Forward delta = "
             "candidate pair 50/50 forward-21d return minus E0 pair forward-21d return.\n")
    L.append("| Variant | Diverge from E0 | Mean fwd delta (all diverge) | E0 poor months | of those diverged | of diverged: cand better | Mean fwd delta (poor & diverge) |")
    L.append("| --- | --- | --- | --- | --- | --- | --- |")
    for cand, d in diag.items():
        L.append(f"| {cand} | {d['n_diverge']}/{d['n_months']} ({d['diverge_pct']*100:.1f}%) | "
                 f"{d['mean_div_fwd_delta_bps']:.1f}bps | {d['n_poor']} | {d['n_poor_diverge']} | "
                 f"{d['n_poor_div_better']} | {d['mean_poor_div_delta_bps']:.1f}bps |")

    # Section 5: walk-forward
    L.append("\n## 5. Walk-forward / sub-period stability (is any edge broad?)\n")
    L.append("Rolling 3-year (756d) blend Sharpe vs E0; fraction of windows where candidate beats E0. "
             "Ex-crisis = clean-window blend Sharpe excluding calendar 2008 and 2020.\n")
    L.append("| Variant | Roll-3y win-frac vs E0 | Roll mean diff | Roll [min, max] diff | Full-window Sharpe delta | Ex-2008/2020 Sharpe delta |")
    L.append("| --- | --- | --- | --- | --- | --- |")
    for cand, w in wf.items():
        L.append(f"| {cand} | {w['roll_win_frac']*100:.0f}% | {w['roll_mean_diff']:+.3f} | "
                 f"[{w['roll_min_diff']:+.3f}, {w['roll_max_diff']:+.3f}] | "
                 f"{w['sharpe_full_delta']:+.3f} | {w['sharpe_excrisis_delta']:+.3f} |")

    # Section 6: verdict
    L.append("\n## 6. Verdict\n")
    e0b = results["E0_PROD_sample"]["m_blend_cl"]
    e0b_st = results["E0_PROD_sample"]["m_blend_st"]
    verdict_lines = []
    for cand in ["E1_LedoitWolf", "E2_min_corr", "E3_const_corr"]:
        cb = results[cand]["m_blend_cl"]
        cb_st = results[cand]["m_blend_st"]
        ds = cb["sharpe"] - e0b["sharpe"]
        dss = cb_st["sharpe"] - e0b_st["sharpe"]
        dcalmar = cb["calmar"] - e0b["calmar"]
        dmdd = (cb["max_drawdown"] - e0b["max_drawdown"]) * 100
        broad = wf[cand]["sharpe_excrisis_delta"] > 0 and wf[cand]["roll_win_frac"] > 0.5
        verdict_lines.append(
            f"- **{cand}**: clean blend Sharpe {ds:+.3f}, stress {dss:+.3f}, Calmar {dcalmar:+.2f}, "
            f"MaxDD {dmdd:+.2f}pp vs E0. Ex-crisis Sharpe delta {wf[cand]['sharpe_excrisis_delta']:+.3f}, "
            f"rolling-3y win-frac {wf[cand]['roll_win_frac']*100:.0f}%. "
            f"Edge {'BROAD' if broad else 'NOT broad (crisis-concentrated or absent)'}.")
    L.extend(verdict_lines)

    FINDINGS.parent.mkdir(parents=True, exist_ok=True)
    FINDINGS.write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
