# -*- coding: utf-8 -*-
"""Search-aware multiple-testing-corrected Sharpe lens (PSR + DSR) for the
min-var COHERENT-EW candidate vs no-minvar top-4 and COHERENT-IV.

Bailey & Lopez de Prado (2014): Probabilistic Sharpe Ratio (PSR) and Deflated
Sharpe Ratio (DSR). Read-only research. No prod/memo/cpm_live edits; no commit.

Configs (research.cpm_minvar_coherence.make_weight_fn):
  COHERENT-EW  = make_weight_fn("minvar_ewobj","ew")   (candidate; clean ~1.2711)
  NO-MINVAR    = make_weight_fn("rank","invvol")        (do-nothing top-4; clean ~1.1658, OLD anchor)
  COHERENT-IV  = make_weight_fn("minvar_ivobj","invvol")(challenger; clean ~1.2501)
  NO-MINVAR-EW = make_weight_fn("rank","ew")            (secondary no-minvar; clean ~1.1317)

Decision lens = CLEAN window, MONTHLY frame.

Run: .venv/bin/python -m research.cpm_deflated_sharpe_challenge
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

from research import cpm_harness as H
from research.cpm_minvar_coherence import make_weight_fn

OUT_JSON = Path(__file__).resolve().parent / "cpm_deflated_sharpe_challenge_findings.json"

EULER = 0.5772156649015329


# ---------------- monthly stream stats ----------------
def monthly_returns(daily: pd.Series) -> pd.Series:
    """Compound daily net returns within calendar month."""
    return (1.0 + daily).resample("ME").prod() - 1.0


def stream_stats(daily: pd.Series) -> dict:
    m = monthly_returns(daily).dropna()
    x = m.values
    T = len(x)
    mu = x.mean()
    sd = x.std(ddof=1)
    sr_m = mu / sd                       # per-month Sharpe
    sr_ann = sr_m * np.sqrt(12.0)
    # Bailey-LdP moments: skewness (gamma3), kurtosis NON-excess (gamma4)
    sk = float(pd.Series(x).skew())      # sample skew
    ku_excess = float(pd.Series(x).kurt())  # Fisher (excess)
    ku_full = ku_excess + 3.0
    return {
        "T": T, "sr_month": float(sr_m), "sr_ann": float(sr_ann),
        "skew": sk, "kurt_excess": ku_excess, "kurt_full": ku_full,
        "mu_month": float(mu), "sd_month": float(sd),
    }


# ---------------- PSR ----------------
def psr(sr_hat_m: float, sr0_m: float, T: int, skew: float, kurt_full: float) -> dict:
    """Probabilistic Sharpe Ratio. All SR in per-PERIOD (monthly) units.
    PSR(sr0) = Phi( (sr_hat - sr0)*sqrt(T-1) / sqrt(1 - skew*sr_hat + (kurt_full-1)/4 * sr_hat^2) )
    """
    denom = np.sqrt(max(1e-18, 1.0 - skew * sr_hat_m + (kurt_full - 1.0) / 4.0 * sr_hat_m ** 2))
    z = (sr_hat_m - sr0_m) * np.sqrt(T - 1) / denom
    return {"psr": float(norm.cdf(z)), "z": float(z), "denom": float(denom)}


# ---------------- expected max SR (deflation benchmark) ----------------
def expected_max_sr(var_trials_m: float, N: int) -> float:
    """E[max of N ~ N(0, var)] approximation (Bailey-LdP).
    SR0 = sqrt(V) * [ (1-gamma)*Z^-1(1 - 1/N) + gamma*Z^-1(1 - 1/(N*e)) ]
    var_trials_m in per-MONTH SR^2 units. Returns per-month SR0."""
    sigma = np.sqrt(var_trials_m)
    a = norm.ppf(1.0 - 1.0 / N)
    b = norm.ppf(1.0 - 1.0 / (N * np.e))
    return float(sigma * ((1.0 - EULER) * a + EULER * b))


# ---------------- trial Sharpe universe (clean, net 10 bps, annualized) ----------------
# Transparent list assembled from this session's selection/sizing/objective studies.
# Source files in research/*.json. Annualized clean net-10bps Sharpes.
TRIAL_SHARPES_ANN = {
    # --- minvar coherence 2x2 + references (cpm_minvar_coherence_findings.json) ---
    "PROD_rank_IV (no-minvar top4)": 1.1658,
    "PROD_rank_EW (no-minvar top4 EW)": 1.1317,
    "COHERENT_EW (ewobj+EW)": 1.2711,
    "MINVAR_IV (ewobj+IV)": 1.2622,
    "COHERENT_IV (ivobj+IV)": 1.2501,
    "ivobj+EW mismatch": 1.2509,
    # --- simple-corr selection sweep (cpm_simple_corr_selection_findings.json) ---
    "RANK3_IV (top-3 IV)": 0.9566,
    "RANK3_EW (top-3 EW)": 0.9477,
    "DROP1_IV": 1.1791,
    "DROP1_EW": 1.1580,
    # MINCORR == DROP1 (duplicate) -> excluded to avoid near-dup inflation
    # --- weighting head-to-head / consolidated (net_10bps clean) ---
    "CONT (continuous minvar)": 1.2935,
    "IV4": 1.1491,
    "IV3": 1.2453,
    "IV2": 1.2630,
    "EW2": 1.2424,
    "EW4": 1.0875,
    "ERC": 1.1723,
    # --- weighting/selection sensitivity (objective sweep, INVVOL) ---
    "MINVOL_IV": 1.1926,
    "MINCORR_IV (obj)": 1.2027,
    "MAXSHARPE_IV": 1.1501,
    "MAXCALMAR_IV": 1.1958,
    "MINDD_IV": 1.2166,
    "MINVAR_ERC": 1.2693,
    "MINVAR_EW (sens)": 1.2229,
    # --- cardinality / poolsize sweep (selection cardinality) ---
    "EW1 (single)": 0.9673,
    "EW3": 1.2229,
    "4of5_minvar_IV": 1.1466,
    "4of5_minvar_EW": 1.1187,
    "3of4_minvar_IV": 1.2414,
    "3of4_minvar_EW": 1.2375,
    "5of6_minvar_IV": 1.0313,
    "5of6_minvar_EW": 0.9926,
    "5of6_rank_IV": 1.0531,
    "2of4_minvar_IV_fullrisk": 1.1012,
    "2of4_minvar_EW_fullrisk": 1.0677,
    # --- 504 lookback variants (cpm_simple_corr cells_504) ---
    "PROD_504": 1.1910,
    "DROP1_504": 1.2440,
    "MINVAR_504": 1.2923,
}

# Economically-distinct families for N point estimate (see findings .md):
# signal family x horizon x filter x universe x sizing x selection-rule.


def main():
    data = H.load_data()
    anchor = H.verify_anchor(data=data)
    print("ANCHOR OK:", {k: round(float(v), 4) for k, v in anchor.items() if k in ("Sharpe", "MaxDD", "Calmar")})

    configs = {
        "COHERENT_EW": make_weight_fn("minvar_ewobj", "ew"),
        "NO_MINVAR": make_weight_fn("rank", "invvol"),
        "COHERENT_IV": make_weight_fn("minvar_ivobj", "invvol"),
        "NO_MINVAR_EW": make_weight_fn("rank", "ew"),
    }
    streams, stats = {}, {}
    for k, wf in configs.items():
        daily = H.run_strategy(wf, window="clean", data=data)
        streams[k] = daily
        stats[k] = stream_stats(daily)
        print(f"{k}: clean ann Sharpe {stats[k]['sr_ann']:.4f}, T={stats[k]['T']}, "
              f"skew={stats[k]['skew']:.3f}, kurt_excess={stats[k]['kurt_excess']:.3f}")

    # ---- PSR for each config: vs 0 and vs no-minvar benchmark ----
    nm = stats["NO_MINVAR"]
    sr0_nm_month = nm["sr_month"]  # per-month no-minvar SR benchmark
    psr_results = {}
    for k, s in stats.items():
        p0 = psr(s["sr_month"], 0.0, s["T"], s["skew"], s["kurt_full"])
        pbench = psr(s["sr_month"], sr0_nm_month, s["T"], s["skew"], s["kurt_full"])
        psr_results[k] = {
            "vs_0": p0,
            "vs_no_minvar": pbench,
            "sr_ann": s["sr_ann"],
        }
        print(f"PSR {k}: vs0={p0['psr']:.4f} (z={p0['z']:.2f}), "
              f"vsNM={pbench['psr']:.4f} (z={pbench['z']:.2f})")

    # ---- trial SR variance (monthly units) ----
    trials_ann = np.array(list(TRIAL_SHARPES_ANN.values()))
    trials_month = trials_ann / np.sqrt(12.0)
    var_trials_m = float(np.var(trials_month, ddof=1))
    var_trials_ann = float(np.var(trials_ann, ddof=1))
    std_trials_ann = float(np.std(trials_ann, ddof=1))
    print(f"Trials: n={len(trials_ann)}, std_ann={std_trials_ann:.4f}, "
          f"var_month={var_trials_m:.6e}")

    # ---- DSR for candidate (and IV) across N sensitivity ----
    Ns = [5, 10, 20, 50]
    dsr_table = {}
    for cand in ("COHERENT_EW", "COHERENT_IV"):
        s = stats[cand]
        rows = []
        for N in Ns:
            sr0_m = expected_max_sr(var_trials_m, N)
            d = psr(s["sr_month"], sr0_m, s["T"], s["skew"], s["kurt_full"])
            rows.append({
                "N": N,
                "sr0_month": sr0_m,
                "sr0_ann": sr0_m * np.sqrt(12.0),
                "dsr": d["psr"],
                "z": d["z"],
            })
            print(f"DSR {cand} N={N}: SR0_ann={sr0_m*np.sqrt(12):.4f}, DSR={d['psr']:.4f}, z={d['z']:.2f}")
        dsr_table[cand] = rows

    # ---- find N at which DSR drops below 0.95 for COHERENT_EW (fine grid) ----
    s = stats["COHERENT_EW"]
    cross = None
    for N in range(2, 5001):
        sr0_m = expected_max_sr(var_trials_m, N)
        d = psr(s["sr_month"], sr0_m, s["T"], s["skew"], s["kurt_full"])
        if d["psr"] < 0.95:
            cross = N
            break
    print(f"COHERENT_EW DSR<0.95 first at N={cross}")

    results = {
        "anchor": {k: float(v) for k, v in anchor.items()},
        "stats": stats,
        "psr": psr_results,
        "no_minvar_benchmark_sr_ann": nm["sr_ann"],
        "trials": {
            "list_ann": TRIAL_SHARPES_ANN,
            "n": len(trials_ann),
            "std_ann": std_trials_ann,
            "var_ann": var_trials_ann,
            "var_month": var_trials_m,
        },
        "dsr": dsr_table,
        "dsr_cross_below_0p95_coherent_ew": cross,
    }
    with open(OUT_JSON, "w") as f:
        json.dump(results, f, indent=2, default=lambda o: None)
    print("wrote", OUT_JSON)
    return results


if __name__ == "__main__":
    main()
