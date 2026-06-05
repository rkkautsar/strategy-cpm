# -*- coding: utf-8 -*-
"""DSR (Deflated Sharpe Ratio) + PBO (Probability of Backtest Overfitting via
CSCV) for the CPM de-risk config FAMILY.

PURPOSE
-------
The selected CPM de-risk winner (continuous EW scale-to-cash vol-target; the
parameter-free EXPANDING-60/40 anchor ~= VT-10) beats baseline by only ~+0.015
blend Sharpe. With ~8-10 trials this could be selection noise. This script is
the honest multiple-testing / overfitting guard:

  (1) DSR  -- Bailey & Lopez de Prado (2014). Deflate the winner's Sharpe for
      (a) the number of trials N and (b) return non-normality (skew/kurtosis).
      Reported on ABSOLUTE Sharpe (as requested) AND on the INCREMENT spread
      (winner minus baseline) -- the latter is the decision-relevant quantity.
  (2) PBO  -- Bailey, Borwein, Lopez de Prado, Zhu (2017) CSCV. Over the family
      of de-risk configs, estimate how often the in-sample-best config lands
      below the OOS median (logit <= 0).

TRIAL FAMILY (de-risk configs; baseline is the null reference, not a trial):
  baseline (no de-risk)               [null reference]
  drop-to-safe (n_pos=4 3x25%+safe)
  VT-10% fixed (252d)
  VT-12% fixed (252d)
  VT-10% (60d window)
  VT-6040-trailing
  VT-6040-expand   <- WINNER
  cov re-weight V1 (min-var-weight)
  cov re-weight V2 (target-vol tilt)
  (VT-SPY anchors were dropped a-priori: SPY ~16-18% >> CPM ~10% => near no-op.
   Not run; not counted as a trial.)

Honest trial count: 8 distinct de-risk configs were actually backtested.
DSR N-sensitivity reported at N = 6, 8, 10.

CAVEATS baked into the report:
  - These configs are MINOR variants of ONE baseline (same selection/canary/
    ranker; only the final risky weights are scaled/re-weighted). They are HIGHLY
    correlated => effective N << raw N, and the "edge" is ONE mechanism, not 8
    independent bets. Reported: mean pairwise corr + an effective-N estimate.
  - DSR on ABSOLUTE Sharpe mostly certifies the (robust) base CPM strategy, NOT
    the marginal de-risk tweak. The INCREMENT PSR/DSR and the PBO are the honest
    guards for the SELECTION question.
  - PIT/cached-data: frozen cached dataset; trailing/expanding targets and rv_CPM
    are lagged to sig_d (PIT-clean per the source run scripts).

RESEARCH-ONLY. No prod/memo/doc edits; no commit. Reuses the EXACT config
builders from the four source run scripts and build_dashboard.build_artifacts.

Run: .venv/bin/python -m research.cpm_voltarget_dsr_pbo_harness
"""
from __future__ import annotations

import json
from itertools import combinations
from pathlib import Path
import sys

import numpy as np
import pandas as pd
from scipy.stats import norm

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import cpm_live
from cpm_live import compute_target_weights
from research import cpm_harness as H

# ---- exact config builders from the four source run scripts ----
from research.cpm_npos4_droptosafe_run import (
    baseline_weight_fn,
    variant_weight_fn as droptosafe_weight_fn,
    variant_compute_target_weights as droptosafe_ctw,
)
from research.cpm_voltarget_paramfree_run import (
    bench_6040_returns,
    make_fixed_target,
    make_trailing_target,
    make_expanding_target,
    make_vt_weight_fn,   # callable-target version (window arg)
    make_vt_ctw,
)
from research.cpm_voltarget_reweight_run import (
    v1_weight_fn, v2_weight_fn, v1_ctw, v2_ctw,
)

OUT_JSON = Path(__file__).resolve().parent / "cpm_voltarget_dsr_pbo_findings.json"
EULER = 0.5772156649015329


# ============================ stats helpers ============================
def monthly_returns(daily: pd.Series) -> pd.Series:
    return (1.0 + daily.dropna()).resample("ME").prod() - 1.0


def stream_stats(monthly: pd.Series) -> dict:
    x = monthly.dropna().values
    T = len(x)
    mu = x.mean()
    sd = x.std(ddof=1)
    sr_m = mu / sd if sd > 0 else float("nan")
    sk = float(pd.Series(x).skew())
    ku_excess = float(pd.Series(x).kurt())
    return {
        "T": T, "sr_month": float(sr_m), "sr_ann": float(sr_m * np.sqrt(12.0)),
        "skew": sk, "kurt_excess": ku_excess, "kurt_full": ku_excess + 3.0,
        "mu_month": float(mu), "sd_month": float(sd),
    }


def psr(sr_hat_m: float, sr0_m: float, T: int, skew: float, kurt_full: float) -> dict:
    """PSR / DSR core. SR in per-period (monthly). DSR = PSR(sr0=expected_max)."""
    denom = np.sqrt(max(1e-18,
                        1.0 - skew * sr_hat_m + (kurt_full - 1.0) / 4.0 * sr_hat_m ** 2))
    z = (sr_hat_m - sr0_m) * np.sqrt(max(T - 1, 1)) / denom
    return {"prob": float(norm.cdf(z)), "z": float(z), "denom": float(denom)}


def expected_max_sr(var_trials_m: float, N: int) -> float:
    """E[max of N iid N(0,var)] (Bailey-LdP). var in per-month SR^2. Returns
    per-month SR0."""
    if N < 2 or var_trials_m <= 0:
        return 0.0
    sigma = np.sqrt(var_trials_m)
    a = norm.ppf(1.0 - 1.0 / N)
    b = norm.ppf(1.0 - 1.0 / (N * np.e))
    return float(sigma * ((1.0 - EULER) * a + EULER * b))


def effective_n(corr: np.ndarray) -> dict:
    """Participation-ratio effective N from eigenvalues of the corr matrix."""
    eig = np.linalg.eigvalsh(corr)
    eig = eig[eig > 0]
    n_eff = float((eig.sum() ** 2) / (eig ** 2).sum())
    iu = np.triu_indices_from(corr, k=1)
    mean_corr = float(corr[iu].mean())
    return {"n_eff_pr": n_eff, "mean_pairwise_corr": mean_corr,
            "raw_n": int(corr.shape[0])}


# ============================ PBO / CSCV ============================
def sharpe_cols(M: np.ndarray) -> np.ndarray:
    """Per-column (config) per-period Sharpe of a returns matrix (rows=periods)."""
    mu = M.mean(axis=0)
    sd = M.std(axis=0, ddof=1)
    out = np.divide(mu, sd, out=np.zeros_like(mu), where=sd > 0)
    return out


def pbo_cscv(M: pd.DataFrame, S: int = 12) -> dict:
    """CSCV PBO over returns matrix M (rows=periods, cols=configs).

    Split T rows into S equal contiguous blocks; for each of C(S, S/2)
    train/test partitions: IS-best config -> its OOS Sharpe rank -> relative
    rank w in (0,1) -> logit. PBO = P(logit <= 0) = fraction of partitions where
    the IS-best is at/below the OOS median.
    """
    A = M.values
    T, Ncfg = A.shape
    rows_per = T // S
    usable = rows_per * S
    A = A[:usable]
    blocks = [A[i * rows_per:(i + 1) * rows_per] for i in range(S)]
    half = S // 2
    logits, below = [], 0
    n_comb = 0
    is_best_counts = np.zeros(Ncfg, dtype=int)
    for combo in combinations(range(S), half):
        cset = set(combo)
        is_blocks = [blocks[i] for i in combo]
        oos_blocks = [blocks[i] for i in range(S) if i not in cset]
        IS = np.vstack(is_blocks)
        OOS = np.vstack(oos_blocks)
        sr_is = sharpe_cols(IS)
        sr_oos = sharpe_cols(OOS)
        n_star = int(np.argmax(sr_is))
        is_best_counts[n_star] += 1
        # relative OOS rank of the IS-best (1 = best OOS, 0 = worst OOS)
        order = np.argsort(sr_oos)            # ascending
        ranks = np.empty(Ncfg, dtype=float)
        ranks[order] = np.arange(1, Ncfg + 1)  # 1..Ncfg, higher = better OOS
        w = ranks[n_star] / (Ncfg + 1.0)       # in (0,1)
        lam = float(np.log(w / (1.0 - w)))
        logits.append(lam)
        if w <= 0.5:
            below += 1
        n_comb += 1
    logits = np.array(logits)
    return {
        "S": S, "n_partitions": n_comb, "n_configs": Ncfg, "T_used": usable,
        "pbo": float(below / n_comb),
        "logit_mean": float(logits.mean()),
        "logit_median": float(np.median(logits)),
        "logit_p05": float(np.percentile(logits, 5)),
        "logit_p95": float(np.percentile(logits, 95)),
        "frac_logit_le0": float((logits <= 0).mean()),
        "is_best_distribution": {int(i): int(c) for i, c in enumerate(is_best_counts)},
    }


# ============================ build all config streams ============================
def build_streams(data):
    """Return dict level -> {config_name: daily returns Series} for sleeve+blend."""
    close = data.panel
    print("Computing baseline CPM sleeve returns (ext) for rv_CPM proxy ...")
    baseline_ret_ext = H.run_strategy(compute_target_weights, window="ext", data=data)
    b6040 = bench_6040_returns(close)

    # ---- de-risk config -> (sleeve weight_fn, blend ctw) ----
    vt10_t = make_fixed_target(0.10)
    vt12_t = make_fixed_target(0.12)
    tr_t = make_trailing_target(b6040, 252)
    ex_t = make_expanding_target(b6040)

    SLEEVE_FN = {
        "baseline":        baseline_weight_fn,
        "drop-to-safe":    droptosafe_weight_fn,
        "VT-10 (252d)":    make_vt_weight_fn(baseline_ret_ext, vt10_t, 252),
        "VT-12 (252d)":    make_vt_weight_fn(baseline_ret_ext, vt12_t, 252),
        "VT-10 (60d)":     make_vt_weight_fn(baseline_ret_ext, vt10_t, 60),
        "VT-6040-trail":   make_vt_weight_fn(baseline_ret_ext, tr_t, 252),
        "VT-6040-expand":  make_vt_weight_fn(baseline_ret_ext, ex_t, 252),
        "cov-V1-minvar":   v1_weight_fn,
        "cov-V2-tilt":     v2_weight_fn,
    }
    BLEND_CTW = {
        "baseline":        None,  # no patch
        "drop-to-safe":    droptosafe_ctw,
        "VT-10 (252d)":    make_vt_ctw(baseline_ret_ext, vt10_t, 252),
        "VT-12 (252d)":    make_vt_ctw(baseline_ret_ext, vt12_t, 252),
        "VT-10 (60d)":     make_vt_ctw(baseline_ret_ext, vt10_t, 60),
        "VT-6040-trail":   make_vt_ctw(baseline_ret_ext, tr_t, 252),
        "VT-6040-expand":  make_vt_ctw(baseline_ret_ext, ex_t, 252),
        "cov-V1-minvar":   v1_ctw,
        "cov-V2-tilt":     v2_ctw,
    }

    # ---- SLEEVE (clean window) ----
    sleeve = {}
    for name, fn in SLEEVE_FN.items():
        print(f"  sleeve: {name}")
        sleeve[name] = H.run_strategy(fn, window="clean", data=data)

    # ---- BLEND (build_dashboard 60/20/20, clean window) ----
    import build_dashboard as BD
    from cpm_live import load_panel
    print("Loading blend panel + NDX ...")
    bpanel = load_panel(start=pd.Timestamp("1995-01-01"), end=data.end, live=True)
    bend = min(data.end, bpanel.index[-1])
    try:
        from ndx_sleeve_live import load_ndx_panel
        ndx_panel = load_ndx_panel()
    except Exception as e:
        print(f"  NDX panel unavailable ({e}); blend uses CPM+BULL only.")
        ndx_panel = None
    bstart = data.clean_start

    blend = {}
    _orig = cpm_live.compute_target_weights
    for name, ctw in BLEND_CTW.items():
        print(f"  blend: {name}")
        if ctw is None:
            blend[name] = BD.build_artifacts(bpanel, ndx_panel, bstart, bend,
                                             include_records=False).blend
        else:
            cpm_live.compute_target_weights = ctw
            try:
                blend[name] = BD.build_artifacts(bpanel, ndx_panel, bstart, bend,
                                                 include_records=False).blend
            finally:
                cpm_live.compute_target_weights = _orig
    return {"sleeve": sleeve, "blend": blend}


# ============================ analysis ============================
DERISK = ["drop-to-safe", "VT-10 (252d)", "VT-12 (252d)", "VT-10 (60d)",
          "VT-6040-trail", "VT-6040-expand", "cov-V1-minvar", "cov-V2-tilt"]
WINNER = "VT-6040-expand"
XCHECK = "VT-10 (252d)"


def analyze_level(level: str, streams: dict) -> dict:
    # aligned monthly matrix (all configs incl baseline)
    monthly = {k: monthly_returns(v) for k, v in streams.items()}
    Mdf = pd.DataFrame(monthly).dropna()
    cfg_all = list(Mdf.columns)
    stats = {k: stream_stats(Mdf[k]) for k in cfg_all}

    # --- trial SR variance (monthly units) over the 8 de-risk configs ---
    sr_derisk = np.array([stats[k]["sr_month"] for k in DERISK if k in stats])
    var_trials_m = float(np.var(sr_derisk, ddof=1))

    # --- DSR on ABSOLUTE Sharpe for winner + cross-check, N = 6,8,10 ---
    dsr_abs = {}
    for cand in (WINNER, XCHECK):
        s = stats[cand]
        rows = []
        for N in (6, 8, 10):
            sr0 = expected_max_sr(var_trials_m, N)
            d = psr(s["sr_month"], sr0, s["T"], s["skew"], s["kurt_full"])
            rows.append({"N": N, "sr0_month": sr0, "sr0_ann": sr0 * np.sqrt(12),
                         "dsr": d["prob"], "z": d["z"]})
        # PSR vs 0 (no deflation) for reference
        p0 = psr(s["sr_month"], 0.0, s["T"], s["skew"], s["kurt_full"])
        dsr_abs[cand] = {"sr_ann": s["sr_ann"], "T": s["T"], "skew": s["skew"],
                         "kurt_excess": s["kurt_excess"], "psr_vs0": p0["prob"],
                         "N_sens": rows}

    # --- INCREMENT spread: winner/xcheck MINUS baseline (the honest quantity) ---
    incr = {}
    base_m = Mdf["baseline"]
    for cand in (WINNER, XCHECK):
        spread = Mdf[cand] - base_m
        ss = stream_stats(spread)
        p0 = psr(ss["sr_month"], 0.0, ss["T"], ss["skew"], ss["kurt_full"])
        # deflate the increment too (N=8): SR0 from var of the 8 increment SRs
        incr_srs = np.array([stream_stats(Mdf[k] - base_m)["sr_month"]
                             for k in DERISK if k in stats])
        var_incr = float(np.var(incr_srs, ddof=1))
        defl = {}
        for N in (6, 8, 10):
            sr0 = expected_max_sr(var_incr, N)
            d = psr(ss["sr_month"], sr0, ss["T"], ss["skew"], ss["kurt_full"])
            defl[N] = {"sr0_ann": sr0 * np.sqrt(12), "dsr": d["prob"], "z": d["z"]}
        incr[cand] = {
            "spread_sr_ann": ss["sr_ann"], "spread_mu_month_bps": ss["mu_month"] * 1e4,
            "T": ss["T"], "skew": ss["skew"], "kurt_excess": ss["kurt_excess"],
            "psr_vs0": p0["prob"], "z_vs0": p0["z"],
            "deflated": defl, "var_incr_month": var_incr,
        }

    # --- correlation / effective N (de-risk configs only) ---
    corr = Mdf[[k for k in DERISK if k in stats]].corr().values
    eff = effective_n(corr)
    corr_all = Mdf[cfg_all].corr().values
    eff_all = effective_n(corr_all)

    # --- PBO over full menu (baseline + 8) and de-risk-only (8) ---
    pbo_full = {S: pbo_cscv(Mdf[cfg_all], S=S) for S in (10, 12)}
    pbo_derisk = {S: pbo_cscv(Mdf[[k for k in DERISK if k in stats]], S=S)
                  for S in (10, 12)}

    return {
        "T_months": int(Mdf.shape[0]),
        "window": f"{Mdf.index[0].date()}..{Mdf.index[-1].date()}",
        "config_sr_ann": {k: stats[k]["sr_ann"] for k in cfg_all},
        "var_trials_month_derisk": var_trials_m,
        "dsr_absolute": dsr_abs,
        "increment": incr,
        "effective_n_derisk": eff,
        "effective_n_all": eff_all,
        "pbo_full_menu": pbo_full,
        "pbo_derisk_only": pbo_derisk,
        "config_index": {i: k for i, k in enumerate(cfg_all)},
        "derisk_index": {i: k for i, k in enumerate([x for x in DERISK if x in stats])},
    }


def main():
    print("Loading harness data ...")
    data = H.load_data()
    anc = H.verify_anchor(data=data)
    print(f"[ok] anchor Sharpe={anc['Sharpe']:.6f} MaxDD={anc['MaxDD']:.6f} "
          f"Calmar={anc['Calmar']:.6f}")

    streams = build_streams(data)
    results = {"anchor": {k: float(v) for k, v in anc.items()
                          if k in ("Sharpe", "MaxDD", "Calmar")}}
    for level in ("sleeve", "blend"):
        print(f"\n=== analyzing {level} ===")
        results[level] = analyze_level(level, streams[level])

    with open(OUT_JSON, "w") as f:
        json.dump(results, f, indent=2, default=lambda o: None)
    print(f"\n[written] {OUT_JSON}")

    # ---- compact console summary ----
    for level in ("blend", "sleeve"):
        r = results[level]
        print(f"\n##### {level.upper()}  (T={r['T_months']} months, {r['window']})")
        print("config Sharpe(ann):")
        for k, v in r["config_sr_ann"].items():
            print(f"   {k:18s} {v:7.4f}")
        print(f"var_trials(month, 8 de-risk) = {r['var_trials_month_derisk']:.3e}")
        print(f"effective N (de-risk 8): n_eff={r['effective_n_derisk']['n_eff_pr']:.2f} "
              f"mean_corr={r['effective_n_derisk']['mean_pairwise_corr']:.3f}")
        for cand in (WINNER, XCHECK):
            a = r["dsr_absolute"][cand]
            print(f"  DSR-ABS {cand}: SR_ann={a['sr_ann']:.3f} PSRvs0={a['psr_vs0']:.3f} "
                  f"skew={a['skew']:.2f} kurtX={a['kurt_excess']:.2f}")
            for row in a["N_sens"]:
                print(f"     N={row['N']:2d} SR0_ann={row['sr0_ann']:.3f} "
                      f"DSR={row['dsr']:.4f} z={row['z']:.2f}")
            inc = r["increment"][cand]
            print(f"  INCR {cand}-baseline: spreadSR={inc['spread_sr_ann']:.3f} "
                  f"mu={inc['spread_mu_month_bps']:.1f}bps/mo PSRvs0={inc['psr_vs0']:.3f} "
                  f"z={inc['z_vs0']:.2f}")
            for N in (6, 8, 10):
                d = inc["deflated"][N]
                print(f"     defl N={N}: DSR={d['dsr']:.4f} z={d['z']:.2f}")
        for tag, pdct in (("full-menu", r["pbo_full_menu"]),
                          ("de-risk-only", r["pbo_derisk_only"])):
            for S, p in pdct.items():
                print(f"  PBO {tag} S={S}: PBO={p['pbo']:.3f} "
                      f"logit(mean={p['logit_mean']:.2f} med={p['logit_median']:.2f} "
                      f"p05={p['logit_p05']:.2f} p95={p['logit_p95']:.2f}) "
                      f"nparts={p['n_partitions']}")

    return results


if __name__ == "__main__":
    main()
