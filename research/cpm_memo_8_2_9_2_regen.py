"""Regenerate cpm_memo.md tables 8.2 (DSR) and 9.2 (vol-window) for CURRENT prod CPM.

Research-only. No production / memo edits, no commit.

Methodology is COPIED from the memo's own generating scripts so only the inputs
(the CPM return series) swap to current prod CPM:

  8.2 DSR  -> mirrors research/_rebaseline_dsr_both252.py EXACTLY
              (Gumbel expected-max SR0, PSR/DSR z with skew+kurt denom,
               V_trials carried = 2.094e-5, N grid 40..2000, daily + monthly).
              Only swap: CPM series now = cpm_live.compute_target_weights via
              research/cpm_harness.py (anchor 1.255673), not the old sleeve.

  9.2 vol-window -> three configs run through the SAME current-prod engine,
              parametrizing the TWO vol windows that exist in current prod:
                rank-vol lookback (cpm_live line ~464, hardcoded .tail(252))
                min-var covariance lookback (CORR_LOOKBACK_DAYS, line ~485)
              Current prod = both-252. Split = rank252/cov504 (mirrors old prod
              rank252/wt504 split). Both-504 = rank504/cov504.
              Paired stationary block bootstrap (B=2000, block=21, seed=42) to
              match the memo's declared bootstrap convention (5.3).
"""
from __future__ import annotations

import json
import sys
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from scipy.stats import norm

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import cpm_live
from cpm_live import (
    RISKY_UNIVERSE, SAFE_POOL, CANARY_ASSETS, CANARY_RULE, TOP_K_CANDIDATES,
    faber_sma_xs, sig_13612U, best_safe, perf_metrics,
)
import cpm_harness as HN

EULER = 0.5772156649015329  # Euler-Mascheroni gamma
V_TRIALS_DAY = 2.094e-5      # memo 8.2 stated measured value (grid SR variance, per-day)
N_GRID = (40, 80, 200, 500, 1000, 2000)
BOOT_B, BOOT_BLOCK, BOOT_SEED = 2000, 21, 42


# ---------------------------------------------------------------------------
# Parametrized current-prod weight fn: identical to cpm_live.compute_target_weights
# except the two vol windows (rank_lb, cov_lb) are injectable.
# ---------------------------------------------------------------------------
def _min_var_subset_lb(close, sig_d, candidates, lookback, m):
    if len(candidates) <= m:
        return list(candidates)
    rets = close.loc[:sig_d][candidates].ffill().pct_change().dropna(how="all").tail(lookback)
    if len(rets) < lookback:
        return list(candidates)
    cov = rets.cov()
    if cov.isna().any().any():
        return list(candidates)
    w = 1.0 / m
    best, best_v = None, np.inf
    for combo in combinations(candidates, m):
        sub = cov.loc[list(combo), list(combo)].values
        v = float(w * w * sub.sum())
        if v < best_v:
            best_v, best = v, combo
    return list(best) if best else list(candidates)


def make_weight_fn(rank_lb: int, cov_lb: int):
    def wf(close_panel, sig_d):
        universe = RISKY_UNIVERSE
        safe_pool = SAFE_POOL
        canary_assets = CANARY_ASSETS
        monthly = close_panel.loc[:sig_d].resample("ME").last()
        safe = best_safe(monthly, sig_d, safe_pool)

        canary_scores = []
        for c in canary_assets:
            if c not in monthly.columns:
                continue
            s = sig_13612U(monthly[c])
            if pd.notna(s):
                canary_scores.append(s)
        if not canary_scores:
            return {safe: 1.0}
        n_canary_pos = sum(1 for s in canary_scores if s > 0)
        if CANARY_RULE == "any_positive":
            if n_canary_pos == 0:
                return {safe: 1.0}
        elif CANARY_RULE == "all_positive":
            if n_canary_pos < len(canary_scores):
                return {safe: 1.0}
        else:
            if n_canary_pos <= len(canary_scores) // 2:
                return {safe: 1.0}

        faber = faber_sma_xs(monthly)
        avail = [t for t in universe
                 if t in faber.index and pd.notna(faber[t])
                 and pd.notna(close_panel.loc[sig_d].get(t, np.nan) if sig_d in close_panel.index else np.nan)]
        if not avail:
            return {safe: 1.0}

        daily_rets = close_panel[avail].ffill().pct_change()
        scores = {}
        for t in avail:
            v = daily_rets[t].loc[:sig_d].tail(rank_lb).std() * np.sqrt(252)
            if pd.isna(v) or v < 1e-9:
                v = 1.0
            scores[t] = float(faber[t]) / v
        sa = pd.Series(scores)
        ranked = sa.sort_values(ascending=False)
        top_k = max(2, min(TOP_K_CANDIDATES, len(ranked)))
        top = ranked.iloc[:top_k]
        positive = top[top.index.map(lambda t: faber.get(t, -np.inf) > 0)]
        if len(positive) == 0:
            return {safe: 1.0}

        positive_picks = list(positive.index)
        n_pos = len(positive_picks)
        if n_pos == 4:
            picks = _min_var_subset_lb(close_panel, sig_d, positive_picks, cov_lb, 3)
        else:
            picks = positive_picks

        risky_fraction = min(n_pos, 4) / 4.0
        safe_fraction = 1.0 - risky_fraction
        risky_w = {t: 1.0 / len(picks) for t in picks}
        out = {t: w * risky_fraction for t, w in risky_w.items()}
        if safe_fraction > 0:
            out[safe] = out.get(safe, 0.0) + safe_fraction
        return out
    return wf


# ---------------------------------------------------------------------------
# 8.2 DSR machinery (verbatim from _rebaseline_dsr_both252.py)
# ---------------------------------------------------------------------------
def sr0_ann(N, V_day):
    z1 = norm.ppf(1 - 1.0 / N)
    z2 = norm.ppf(1 - 1.0 / (N * np.e))
    sr0_day = np.sqrt(V_day) * ((1 - EULER) * z1 + EULER * z2)
    return sr0_day, sr0_day * np.sqrt(252)


def dsr_daily(N, sr_day, skew, ex_kurt, n):
    sr0_day, sr0_a = sr0_ann(N, V_TRIALS_DAY)
    denom = np.sqrt(1 - skew * sr_day + ((ex_kurt + 3 - 1) / 4.0) * sr_day ** 2)
    z = (sr_day - sr0_day) * np.sqrt(n - 1) / denom
    return sr0_a, float(norm.cdf(z)), float(z)


def run_82(clean: pd.Series) -> dict:
    r = clean.values
    n = len(r)
    sr_day = r.mean() / r.std(ddof=1)
    sr_ann = sr_day * np.sqrt(252)
    skew = float(stats.skew(r))
    ex_kurt = float(stats.kurtosis(r, fisher=True))

    out = {"config": "current-prod both-252", "SR_hat_day": float(sr_day),
           "SR_ann": float(sr_ann), "n_daily": n, "skew": skew,
           "excess_kurtosis": ex_kurt, "V_trials_day": V_TRIALS_DAY, "by_N": {}}
    for N in N_GRID:
        sr0_a, dsr, z = dsr_daily(N, sr_day, skew, ex_kurt, n)
        out["by_N"][N] = {"sr0_ann": float(sr0_a), "dsr": dsr, "z": z}

    # monthly frame
    m = clean.resample("ME").apply(lambda x: (1 + x).prod() - 1).dropna()
    mr = m.values
    sr_m = mr.mean() / mr.std(ddof=1)
    nm = len(mr)
    skew_m = float(stats.skew(mr))
    kurt_m = float(stats.kurtosis(mr, fisher=True))
    V_m = V_TRIALS_DAY * 21
    zs = []
    for N in N_GRID:
        z1 = norm.ppf(1 - 1.0 / N); z2 = norm.ppf(1 - 1.0 / (N * np.e))
        sr0_m = np.sqrt(V_m) * ((1 - EULER) * z1 + EULER * z2)
        denom = np.sqrt(1 - skew_m * sr_m + ((kurt_m + 3 - 1) / 4.0) * sr_m ** 2)
        z = (sr_m - sr0_m) * np.sqrt(nm - 1) / denom
        zs.append(float(z))
    out["monthly"] = {"n": nm, "sr_m": float(sr_m), "skew": skew_m,
                      "excess_kurtosis": kurt_m, "z_range": [min(zs), max(zs)]}
    zd = [v["z"] for v in out["by_N"].values()]
    out["daily_z_range"] = [min(zd), max(zd)]
    return out


# ---------------------------------------------------------------------------
# 9.2 vol-window: three configs + paired block bootstrap
# ---------------------------------------------------------------------------
CFGS = {
    "both-252 (rank252/cov252)": (252, 252),  # current prod
    "split (rank252/cov504)":    (252, 504),
    "both-504 (rank504/cov504)": (504, 504),
}


def _metrics(daily: pd.Series, cash: pd.Series) -> dict:
    m = perf_metrics(daily, cash)
    return {"sharpe": m.get("sharpe"), "maxdd": m.get("max_drawdown"),
            "calmar": m.get("calmar"), "martin": m.get("martin"),
            "cagr": m.get("cagr"), "vol": m.get("vol")}


def _metrics_arr(r, n_years):
    vol = r.std(ddof=0) * np.sqrt(252)
    sharpe = (r.mean() * 252) / vol if vol > 0 else np.nan
    eq = np.cumprod(1.0 + r)
    cagr = eq[-1] ** (1.0 / n_years) - 1.0 if n_years > 0 else np.nan
    rm = np.maximum.accumulate(eq)
    dd = eq / rm - 1.0
    mdd = dd.min()
    calmar = cagr / abs(mdd) if mdd != 0 else np.nan
    ulcer = float(np.sqrt(np.mean(dd ** 2)))
    martin = cagr / ulcer if ulcer > 0 else np.nan
    return sharpe, calmar, martin


def _block_index(n, block, rng):
    n_blocks = (n // block) + 1
    parts = []
    for _ in range(n_blocks):
        s = int(rng.integers(0, n))
        e = s + block
        if e <= n:
            parts.append(np.arange(s, e))
        else:
            parts.append(np.concatenate([np.arange(s, n), np.arange(0, e - n)]))
    return np.concatenate(parts)[:n]


def _summ(a):
    a = np.asarray(a)
    lo, hi = float(np.percentile(a, 2.5)), float(np.percentile(a, 97.5))
    return {"mean": float(a.mean()), "ci_lo": lo, "ci_hi": hi,
            "includes_zero": bool(lo <= 0.0 <= hi), "p_gt0": float(np.mean(a > 0))}


def paired_bootstrap(series_by_cfg, n_years, pairs):
    names = list(series_by_cfg)
    n = len(series_by_cfg[names[0]])
    rng = np.random.default_rng(BOOT_SEED)
    draws = {nm: {"sharpe": [], "calmar": [], "martin": []} for nm in names}
    for _ in range(BOOT_B):
        idx = _block_index(n, BOOT_BLOCK, rng)
        for nm in names:
            s, c, m = _metrics_arr(series_by_cfg[nm][idx], n_years)
            draws[nm]["sharpe"].append(s)
            draws[nm]["calmar"].append(c)
            draws[nm]["martin"].append(m)
    out = {}
    for (A, Bn) in pairs:
        lbl = f"{A} - {Bn}"
        out[lbl] = {}
        for mk in ("sharpe", "calmar", "martin"):
            d = np.asarray(draws[A][mk]) - np.asarray(draws[Bn][mk])
            out[lbl][mk] = _summ(d)
    return out


def main():
    hd = HN.load_data()
    HN.verify_anchor(data=hd)  # asserts current prod anchor 1.255673
    print("[anchor] current prod both-252 verified (Sharpe 1.255673)")

    # ----- run three vol-window configs (clean window) -----
    series = {}
    comp = {}
    for name, (rl, cl) in CFGS.items():
        s = HN.run_strategy(make_weight_fn(rl, cl), window="clean", data=hd)
        series[name] = s.dropna()
        comp[name] = _metrics(series[name], hd.cash)
        m = comp[name]
        print(f"[{name}] Sharpe={m['sharpe']:.4f} MaxDD={m['maxdd']*100:.2f}% "
              f"Calmar={m['calmar']:.4f} Martin={m['martin']:.4f}")

    # sanity: both-252 must match prod anchor 1.2557
    b252 = comp["both-252 (rank252/cov252)"]["sharpe"]
    assert abs(b252 - 1.255673) < 2e-3, f"both-252 reproduction off: {b252}"

    # ----- 8.2 DSR on the current-prod (both-252) clean series -----
    dsr = run_82(series["both-252 (rank252/cov252)"])
    print(f"\n[8.2] SR_ann={dsr['SR_ann']:.4f} n={dsr['n_daily']} "
          f"skew={dsr['skew']:.4f} exkurt={dsr['excess_kurtosis']:.4f}")
    for N in N_GRID:
        v = dsr["by_N"][N]
        print(f"   N={N:5d} SR0={v['sr0_ann']:.3f} DSR={v['dsr']:.4f} z={v['z']:.2f}")
    print(f"   daily z range {dsr['daily_z_range']}  monthly z range {dsr['monthly']['z_range']}")

    # ----- 9.2 paired bootstrap (both-252 minus alternatives) -----
    short = {"both-252 (rank252/cov252)": "both-252",
             "split (rank252/cov504)": "split",
             "both-504 (rank504/cov504)": "both-504"}
    common = None
    for s in series.values():
        common = s.index if common is None else common.intersection(s.index)
    arrs = {short[k]: v.reindex(common).values for k, v in series.items()}
    n_years = (common[-1] - common[0]).days / 365.25
    pairs = [("both-252", "split"), ("both-252", "both-504")]
    boot = {"meta": {"B": BOOT_B, "block": BOOT_BLOCK, "seed": BOOT_SEED,
                     "n": int(len(common)), "n_years": float(n_years)}}
    boot["clean"] = paired_bootstrap(arrs, n_years, pairs)
    print(f"\n[9.2] paired bootstrap clean n={len(common)} B={BOOT_B} block={BOOT_BLOCK} seed={BOOT_SEED}")
    for lbl, mm in boot["clean"].items():
        for mk in ("sharpe", "calmar", "martin"):
            ss = mm[mk]
            flag = "includes 0" if ss["includes_zero"] else "EXCLUDES 0"
            print(f"   {lbl:20s} {mk:7s} d={ss['mean']:+.4f} "
                  f"CI[{ss['ci_lo']:+.4f},{ss['ci_hi']:+.4f}] {flag}")

    out = {"t82_dsr": dsr,
           "t92_comparison": comp,
           "t92_bootstrap": boot,
           "cfgs": {k: {"rank_lb": v[0], "cov_lb": v[1]} for k, v in CFGS.items()}}
    outp = Path(__file__).with_suffix(".json")
    outp.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nWrote {outp}")
    return out


if __name__ == "__main__":
    main()
