# -*- coding: utf-8 -*-
"""Regenerate stale CPM CI/bootstrap tables in cpm_memo.md for CURRENT prod CPM.

Read-only research. No production/memo files edited. No commit.

Targets:
  (5.3) single-series clean Sharpe stationary block bootstrap CI.
  (5.5) paired block-bootstrap dSharpe CIs: CPM-minus-each-benchmark.
  (8.2) DSR appendix series stats (skew, excess kurtosis, n) sanity for current CPM.

Bootstrap convention (memo 5.3 stated): stationary block bootstrap,
B=2000, block=21 trading days, seed=42. Resampling matches
research/cpm_bootstrap_multimetric.py (circular wrap, rng.integers(0,n)).
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import cpm_live
from cpm_live import perf_metrics, compute_target_weights

import cpm_harness as HN
from cpm_bootstrap_multimetric import paired_block_bootstrap_mm
import cpm_benchmarks_proper as BP

B = 2000
BLOCK = 21
SEED = 42
CLEAN_START = pd.Timestamp("2008-05-30")
END = pd.Timestamp("2026-05-22")


def sharpe_pm(x, index, cash):
    return perf_metrics(pd.Series(np.asarray(x, float), index=index), cash).get("sharpe")


def single_series_block_boot(r, cash, B=B, block=BLOCK, seed=SEED):
    """Circular stationary block bootstrap of a single series' Sharpe.
    Resampling identical to cpm_bootstrap_multimetric (rng.integers + %n wrap)."""
    idxc = r.index
    a = r.values
    n = len(a)
    rng = np.random.default_rng(seed)
    nb = int(np.ceil(n / block))
    point = sharpe_pm(a, idxc, cash)
    draws = np.empty(B)
    for i in range(B):
        starts = rng.integers(0, n, size=nb)
        idx = np.concatenate([np.arange(s, s + block) % n for s in starts])[:n]
        draws[i] = sharpe_pm(a[idx], idxc, cash)
    fin = draws[np.isfinite(draws)]
    return {
        "point": float(point),
        "p2.5": float(np.percentile(fin, 2.5)),
        "p50": float(np.percentile(fin, 50)),
        "p97.5": float(np.percentile(fin, 97.5)),
        "mean": float(fin.mean()),
        "n_obs": int(n),
        "B": B, "block": block, "seed": seed,
    }


def main():
    # --- current prod CPM clean series via canonical harness (anchored) ---
    hd = HN.load_data(end=END)
    HN.verify_anchor(data=hd)  # asserts Sharpe 1.255673 etc.
    cpm = HN.run_strategy(compute_target_weights, window="clean", data=hd)
    cash = hd.cash
    cpm_c = cpm.loc[(cpm.index >= CLEAN_START) & (cpm.index <= END)]
    print(f"CPM clean: {cpm_c.index[0].date()}..{cpm_c.index[-1].date()} n={len(cpm_c)}")
    print(f"CPM clean Sharpe (perf_metrics) = {perf_metrics(cpm_c, cash).get('sharpe'):.6f}")

    out = {"meta": {"B": B, "block": BLOCK, "seed": SEED,
                    "window": "clean 2008-05-30..2026-05-22",
                    "convention": "mooex T+1 MOO, 10bps/side, both-252",
                    "cpm_source": "cpm_live.compute_target_weights via cpm_harness"}}

    # --- (5.3) single-series clean Sharpe CI ---
    out["s53_single_sharpe_ci"] = single_series_block_boot(cpm_c, cash)
    print("\n[5.3] single-series clean Sharpe CI:", json.dumps(out["s53_single_sharpe_ci"]))

    # --- benchmark series via cpm_benchmarks_proper (UNCHANGED benches) ---
    ext_start = pd.Timestamp("1999-03-10")
    panel, intraday, overnight, bend = BP.build_data(ext_start, END)
    bcash = panel["SHV"].ffill().pct_change()

    aaa_cols = sorted(set([t for t in BP.AAA_UNIVERSE if t in panel.columns] + ["SHV", "IEF"]))
    aaa_close = panel[aaa_cols]
    aaa_daily = aaa_close.ffill().pct_change()
    rwx_fv = panel["RWX"].first_valid_index()
    aaa_ext_start = max(ext_start, (rwx_fv + pd.DateOffset(months=13)) if rwx_fv is not None else ext_start)
    aaa, _ = BP.run_wf(aaa_close, aaa_daily, intraday, overnight, aaa_ext_start, bend,
                       BP.make_canonical_aaa_wf(aaa_close, aaa_daily))

    bm_cols = sorted(set(BP.RISKY_UNIVERSE + ["SPY", "IEF", "SHV"]) & set(panel.columns))
    bm_close = panel[bm_cols]
    bm_daily = bm_close.ffill().pct_change()
    sixty, _ = BP.run_wf(bm_close, bm_daily, intraday, overnight, ext_start, bend, BP.make_6040_wf(bm_close))
    naive, _ = BP.run_wf(bm_close, bm_daily, intraday, overnight, ext_start, bend, BP.make_naive12_wf(bm_close))
    bhiv, _ = BP.run_wf(bm_close, bm_daily, intraday, overnight, ext_start, bend, BP.make_buyhold_invvol_wf(bm_close))

    benches = {
        "Canonical_AAA": aaa,
        "60/40": sixty,
        "Naive_12m": naive,
        "BuyHold_InvVol": bhiv,
    }

    # --- (5.5) paired dSharpe CIs: CPM(current) minus each benchmark ---
    out["s55_dsharpe_ci"] = {}
    print("\n[5.5] paired dSharpe CI (CPM_current - bench), B=2000 block=21 seed=42:")
    for name, s in benches.items():
        bw = s.loc[(s.index >= CLEAN_START) & (s.index <= END)]
        res = paired_block_bootstrap_mm(cpm_c, bw, cash, B=B, block=BLOCK, seed=SEED)
        ds = res["dSharpe"]
        rec = {
            "dSharpe_point": float(perf_metrics(cpm_c, cash).get("sharpe")
                                   - perf_metrics(bw.reindex(cpm_c.index.intersection(bw.index)), cash).get("sharpe")),
            "ci_lo": ds["ci_lo"], "ci_hi": ds["ci_hi"],
            "boot_mean_dSharpe": ds["mean"],
            "includes_zero": bool(ds["ci_lo"] <= 0.0 <= ds["ci_hi"]),
            "p_gt0": ds["p_gt0"],
            "n_common": int(len(cpm_c.index.intersection(bw.index))),
        }
        out["s55_dsharpe_ci"][name] = rec
        print(f"  {name:<16} dS={rec['dSharpe_point']:+.4f} CI[{rec['ci_lo']:+.3f},{rec['ci_hi']:+.3f}] "
              f"incl0={rec['includes_zero']}")

    # --- (8.2) DSR series-stat sanity for current CPM ---
    r = cpm_c.values
    rr = r[np.isfinite(r)]
    mean = rr.mean(); sd = rr.std(ddof=0)
    skew = float(np.mean(((rr - mean) / sd) ** 3))
    exk = float(np.mean(((rr - mean) / sd) ** 4) - 3.0)
    out["s82_dsr_inputs"] = {
        "SR_hat_per_day": float(mean / sd),
        "SR_ann": float((mean / sd) * np.sqrt(252)),
        "n_daily": int(len(rr)),
        "skew": skew,
        "excess_kurtosis": exk,
    }
    print("\n[8.2] DSR inputs (current CPM):", json.dumps(out["s82_dsr_inputs"]))

    Path(__file__).with_suffix(".json").write_text(json.dumps(out, indent=2, default=float))
    print("\nDONE -> cpm_memo_ci_regen.json")


if __name__ == "__main__":
    main()
