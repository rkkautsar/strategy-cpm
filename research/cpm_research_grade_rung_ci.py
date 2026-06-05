"""ANALYST research-only (no prod/memo edits; no commit).

ITEM 3: paired block-bootstrap CIs (B=2000, block=21, seed=42) on the HAA->CPM
2^3 decomposition rung effects, so each rung delta gets a CI and an honest
significance verdict.

Effects bootstrapped (clean window, mooex, both-252, 10 bps/side; factor model
identical to research/cpm_haa_coupled_factorial_v2.py):
  - U main effect  (memo point +0.2215)
  - R main effect  (memo point +0.0647)
  - M main effect  (memo point +0.0902)
  - M corner marginal at production corner U1R1 = cell111 - cell110 (point +0.1683)
  - sequential ladder rungs (HAA->+U->+R->+M): +U = 100-000, +R = 110-100, +M = 111-110

Resampling is byte-identical to research.cpm_bootstrap_multimetric /
cpm_weighting_corr.paired_block_bootstrap (rng=default_rng(42), nb=ceil(n/21),
starts=rng.integers(0,n,nb), idx=concat(arange(s,s+21)%n)[:n]) -- common block
indices applied to ALL 8 cell series simultaneously (paired), so the effect
distribution is internally consistent.

Sharpe per draw = (mean*252)/(std*sqrt252) (order-invariant; matches
cpm_live.perf_metrics sharpe).
"""
import sys
import json
import itertools
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from cpm_live import load_panel, COST_BPS_PER_SIDE, CORR_LOOKBACK_DAYS, DEFAULT_CASH
from research import exec_lag_moo_validation_2026_05_30 as eng
from research.cpm_haa_coupled_factorial_v2 import (
    param_wf, HAA_UNIVERSE, CPM_UNIVERSE, SAFE, FACTORS,
)

CLEAN = pd.Timestamp("2008-05-30")
EXT = pd.Timestamp("1999-03-10")
END = pd.Timestamp("2026-05-22")
CONV = "mooex"
B, BLOCK, SEED = 2000, 21, 42


def sharpe(x):
    x = np.asarray(x, dtype=float)
    if x.size == 0:
        return np.nan
    sd = x.std(ddof=0)
    return (x.mean() * 252.0) / (sd * np.sqrt(252.0)) if sd > 0 else np.nan


def main_effects(cell_sharpe):
    """cell_sharpe: dict bits-tuple -> sharpe. Returns U,R,M main effects + corner + ladder."""
    keys = list(cell_sharpe.keys())
    codes = {k: tuple(2 * b - 1 for b in k) for k in keys}
    half = 2 ** (len(FACTORS) - 1)
    main = {FACTORS[i]: sum(codes[k][i] * cell_sharpe[k] for k in keys) / half for i in range(len(FACTORS))}
    out = {f"main_{FACTORS[i]}": main[FACTORS[i]] for i in range(len(FACTORS))}
    out["corner_M_U1R1"] = cell_sharpe[(1, 1, 1)] - cell_sharpe[(1, 1, 0)]
    out["ladder_U"] = cell_sharpe[(1, 0, 0)] - cell_sharpe[(0, 0, 0)]
    out["ladder_R"] = cell_sharpe[(1, 1, 0)] - cell_sharpe[(1, 0, 0)]
    out["ladder_M"] = cell_sharpe[(1, 1, 1)] - cell_sharpe[(1, 1, 0)]
    return out


def summarize(arr):
    a = np.asarray(arr, dtype=float)
    a = a[np.isfinite(a)]
    return {"mean": float(a.mean()), "ci_lo": float(np.percentile(a, 2.5)),
            "ci_hi": float(np.percentile(a, 97.5)), "p_gt0": float((a > 0).mean()),
            "half_width": float((np.percentile(a, 97.5) - np.percentile(a, 2.5)) / 2.0)}


def main():
    panel = load_panel(start=EXT, end=END, live=False)
    panel = panel.loc[panel.index <= END]
    cash = panel[DEFAULT_CASH].ffill().pct_change()

    open_df, close_df = eng.load_open_close()
    intraday = (close_df / open_df - 1.0).reindex(panel.index)
    overnight = (open_df / close_df.shift(1) - 1.0).reindex(panel.index)

    cols = sorted(set(HAA_UNIVERSE + CPM_UNIVERSE + SAFE + ["HYG", "TIP"]) & set(panel.columns))
    close = panel[cols]
    daily = close.ffill().pct_change()

    # build 8 cell daily series (clean window) under mooex
    cell_series = {}
    point_sharpe = {}
    for bits in itertools.product([0, 1], repeat=3):
        wf = lambda sd, b=bits: param_wf(close, sd, *b)
        s, _ = eng._segment_returns_conv(close, daily, wf, EXT, END, CONV,
                                         COST_BPS_PER_SIDE, intraday, overnight)
        s = s.loc[(s.index >= CLEAN) & (s.index <= END)]
        cell_series[bits] = s
        point_sharpe[bits] = sharpe(s.values)
        print(f"  cell {''.join(map(str,bits))} sharpe={point_sharpe[bits]:.4f}")

    # align all cells to common index
    common = None
    for s in cell_series.values():
        common = s.index if common is None else common.intersection(s.index)
    arrs = {bits: cell_series[bits].reindex(common).fillna(0.0).values for bits in cell_series}
    n = len(common)
    print(f"common n={n}")

    # point effects
    point_eff = main_effects(point_sharpe)
    print("point effects:", {k: round(v, 4) for k, v in point_eff.items()})

    # paired block bootstrap (common block indices across all 8 cells)
    rng = np.random.default_rng(SEED)
    nb = int(np.ceil(n / BLOCK))
    draws = {k: [] for k in point_eff}
    for _ in range(B):
        starts = rng.integers(0, n, size=nb)
        idx = np.concatenate([np.arange(s, s + BLOCK) % n for s in starts])[:n]
        cs = {bits: sharpe(arrs[bits][idx]) for bits in arrs}
        eff = main_effects(cs)
        for k in eff:
            draws[k].append(eff[k])

    ci = {k: summarize(draws[k]) for k in draws}

    HALF_LEVEL = 0.43  # level Sharpe CI half-width reference (README clean [0.954,1.823] -> ~0.43)

    verdict = {}
    for k in ("main_U", "main_R", "main_M", "corner_M_U1R1"):
        s = ci[k]
        clears_zero = s["ci_lo"] > 0
        verdict[k] = {
            "point": point_eff[k],
            "ci": [s["ci_lo"], s["ci_hi"]],
            "half_width": s["half_width"],
            "p_gt0": s["p_gt0"],
            "clears_zero": clears_zero,
            "exceeds_level_halfwidth": abs(point_eff[k]) > HALF_LEVEL,
        }

    out = {
        "meta": {"convention": CONV, "clean": f"{CLEAN.date()}..{END.date()}",
                 "both252": CORR_LOOKBACK_DAYS == 252, "cost_bps": COST_BPS_PER_SIDE,
                 "B": B, "block": BLOCK, "seed": SEED, "n_days": n,
                 "level_halfwidth_ref": HALF_LEVEL,
                 "note": ("Paired block bootstrap on the 2^3 HAA->CPM factorial. Common "
                          "block indices across all 8 cells per draw. Effects: main U/R/M, "
                          "corner M@U1R1, sequential ladder rungs.")},
        "point_cell_sharpe": {"".join(map(str, k)): point_sharpe[k] for k in point_sharpe},
        "point_effects": point_eff,
        "ci": ci,
        "verdict": verdict,
    }
    outpath = ROOT / "research" / "cpm_research_grade_rung_ci.json"
    outpath.write_text(json.dumps(out, indent=2, default=lambda x: None if (x is None or (isinstance(x, float) and pd.isna(x))) else float(x)))
    print(f"\nWROTE {outpath}")
    for k, v in verdict.items():
        print(f"{k}: point={v['point']:+.4f} CI[{v['ci'][0]:+.4f},{v['ci'][1]:+.4f}] "
              f"p>0={v['p_gt0']:.3f} clears0={v['clears_zero']}")


if __name__ == "__main__":
    main()
