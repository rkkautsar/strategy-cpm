"""CPM simplification candidate tests.

Evaluates several simplification variants of the production CPM strategy
without modifying cpm_live.py. Each variant is realized by monkey-patching
cpm_live.compute_target_weights with a parameterized re-implementation that
mirrors production logic exactly, then running cpm_live.run_cpm_backtest over
the Clean and Extended windows.

Run:
    python cpm_simplification_tests.py
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import cpm_live
from cpm_live import (
    load_panel,
    perf_metrics,
    best_safe,
    faber_sma_xs,
    _min_var_subset,
    RISKY_UNIVERSE,
    SAFE_POOL,
    CANARY_ASSETS,
    TOP_K_CANDIDATES,
    CORR_LOOKBACK_DAYS,
    CPM_RISKY_FRACTION_CURVE,
    COST_BPS_PER_SIDE,
    run_cpm_backtest,
)
from core import sig_13612U

CLEAN_START = pd.Timestamp("2008-05-30")
EXT_START = pd.Timestamp("1999-03-10")
EVAL_END = pd.Timestamp("2026-04-30")


def make_compute_target_weights(
    *,
    use_min_var: bool = True,
    use_vol_ranking: bool = True,
    use_hyg_gate: bool = True,
    fixed_safe: str | None = None,
):
    """Build a parameterized compute_target_weights mirroring production logic.

    Parameters toggle the four simplification axes. With all defaults this is a
    faithful reproduction of cpm_live.compute_target_weights (the baseline).
    """

    def _ctw(
        close_panel: pd.DataFrame,
        sig_d: pd.Timestamp,
        universe: list = None,
        safe_pool: list = None,
        canary_assets: list = None,
    ):
        universe = universe or RISKY_UNIVERSE
        safe_pool = safe_pool or SAFE_POOL
        canary_assets = canary_assets or CANARY_ASSETS

        monthly = close_panel.loc[:sig_d].resample("ME").last()
        if fixed_safe is not None:
            safe = fixed_safe
        else:
            safe = best_safe(monthly, sig_d, safe_pool)

        faber = faber_sma_xs(monthly)
        avail = [
            t for t in universe
            if t in faber.index and pd.notna(faber[t])
            and pd.notna(close_panel.loc[sig_d].get(t, np.nan) if sig_d in close_panel.index else np.nan)
        ]
        if not avail:
            return {safe: 1.0}, None, "DEFENSIVE", safe

        daily_rets = close_panel[avail].ffill().pct_change()
        scores = {}
        for t in avail:
            if use_vol_ranking:
                v = daily_rets[t].loc[:sig_d].tail(252).std() * np.sqrt(252)
                if pd.isna(v) or v < 1e-9:
                    v = 1.0
                scores[t] = float(faber[t]) / v
            else:
                # Raw Faber SMA distance, no volatility divisor.
                scores[t] = float(faber[t])
        sa = pd.Series(scores)
        ranked = sa.sort_values(ascending=False)
        top_k = max(2, min(TOP_K_CANDIDATES, len(ranked)))
        top = ranked.iloc[:top_k]
        positive = top[top.index.map(lambda t: faber.get(t, -np.inf) > 0)]

        if len(positive) == 0:
            return {safe: 1.0}, None, "DEFENSIVE", safe

        positive_picks = list(positive.index)
        n_pos = len(positive_picks)

        if use_hyg_gate:
            hyg_mom = sig_13612U(monthly["HYG"]) if "HYG" in monthly.columns else float("nan")
            hyg_frac = 0.0 if pd.notna(hyg_mom) and hyg_mom < 0.0 else 1.0
        else:
            hyg_frac = 1.0

        breadth_frac = CPM_RISKY_FRACTION_CURVE.get(min(n_pos, 4), 0.0)
        risky_fraction = min(breadth_frac, hyg_frac)

        if risky_fraction <= 1e-12:
            return {safe: 1.0}, None, "DEFENSIVE", safe

        if n_pos == TOP_K_CANDIDATES and risky_fraction == 1.0 and use_min_var:
            picks = _min_var_subset(close_panel, sig_d, positive_picks, CORR_LOOKBACK_DAYS, 3)
        else:
            # No min-var subset: equal-weight all positive picks (incl. all 4).
            picks = positive_picks

        safe_fraction = 1.0 - risky_fraction
        risky_w = {t: 1.0 / len(picks) for t in picks}
        out = {t: w * risky_fraction for t, w in risky_w.items()}
        if safe_fraction > 0:
            out[safe] = out.get(safe, 0.0) + safe_fraction
        return out, tuple(picks), "RISK_ON", safe

    return _ctw


def run_variant(panel, ctw, start, end):
    """Monkeypatch compute_target_weights, run backtest, restore, return metrics."""
    orig = cpm_live.compute_target_weights
    cpm_live.compute_target_weights = ctw
    try:
        ret, _ = run_cpm_backtest(panel, start, end, cost_bps=COST_BPS_PER_SIDE)
    finally:
        cpm_live.compute_target_weights = orig
    m = perf_metrics(ret)
    return {
        "sharpe": m["sharpe"],
        "cagr": m["cagr"],
        "maxdd": m["max_drawdown"],
        "calmar": m["calmar"],
    }


VARIANTS = {
    "1. Baseline": dict(),
    "2. No Min-Var Subset": dict(use_min_var=False),
    "3. No Vol-Ranking": dict(use_vol_ranking=False),
    "4. No HYG Gate": dict(use_hyg_gate=False),
    "5. Fixed Safe (SHV)": dict(fixed_safe="SHV"),
    "6. Fixed Safe (IEF)": dict(fixed_safe="IEF"),
    # Combined: filled in after we see which simplifications don't degrade Sharpe.
}


def main():
    print("Loading panel ...")
    panel = load_panel(start=EXT_START, end=EVAL_END)
    end = min(EVAL_END, panel.index[-1])
    print(f"Panel: {panel.index[0].date()} -> {panel.index[-1].date()}, {len(panel.columns)} assets\n")

    results = {}
    for name, kw in VARIANTS.items():
        ctw = make_compute_target_weights(**kw)
        clean = run_variant(panel, ctw, CLEAN_START, end)
        ext = run_variant(panel, ctw, EXT_START, end)
        results[name] = {"clean": clean, "ext": ext, "kw": kw}
        print(f"  ran {name}: clean Sharpe {clean['sharpe']:.3f}, ext Sharpe {ext['sharpe']:.3f}")

    # --- Anchor verification (Variant 1 baseline) ---
    base = results["1. Baseline"]
    print("\n=== Anchor verification (Baseline) ===")
    print(f"Clean Sharpe: {base['clean']['sharpe']:.3f} (expect ~1.28)")
    print(f"Ext   Sharpe: {base['ext']['sharpe']:.3f} (expect ~1.33)")
    ok = abs(base["clean"]["sharpe"] - 1.28) < 0.03 and abs(base["ext"]["sharpe"] - 1.33) < 0.03
    print("ANCHOR: " + ("PASS" if ok else "WARN (deviation > 0.03)"))

    # --- Combined Simplicity: pick simplifications within 0.03 Sharpe of baseline ---
    base_clean_sh = base["clean"]["sharpe"]
    combine_kw = {}
    tol = 0.03
    decisions = []
    axis_map = {
        "2. No Min-Var Subset": ("use_min_var", False),
        "3. No Vol-Ranking": ("use_vol_ranking", False),
        "4. No HYG Gate": ("use_hyg_gate", False),
    }
    for vname, (param, val) in axis_map.items():
        delta = results[vname]["clean"]["sharpe"] - base_clean_sh
        keep = delta >= -tol  # simplification does not significantly degrade Sharpe
        decisions.append((vname, delta, keep))
        if keep:
            combine_kw[param] = val
    # Safe-asset axis: choose fixed safe only if best fixed >= baseline - tol.
    shv_d = results["5. Fixed Safe (SHV)"]["clean"]["sharpe"] - base_clean_sh
    ief_d = results["6. Fixed Safe (IEF)"]["clean"]["sharpe"] - base_clean_sh
    best_fixed = "SHV" if shv_d >= ief_d else "IEF"
    best_fixed_d = max(shv_d, ief_d)
    if best_fixed_d >= -tol:
        combine_kw["fixed_safe"] = best_fixed
        decisions.append((f"Fixed Safe ({best_fixed})", best_fixed_d, True))
    else:
        decisions.append(("Dynamic safe (kept)", best_fixed_d, False))

    print("\n=== Combined-Simplicity inclusion decisions (Clean Sharpe vs baseline, tol -0.03) ===")
    for n, d, k in decisions:
        print(f"  {n:28s} dSharpe {d:+.3f}  {'INCLUDE' if k else 'exclude'}")
    print(f"  -> combined kwargs: {combine_kw}")

    ctw = make_compute_target_weights(**combine_kw)
    clean = run_variant(panel, ctw, CLEAN_START, end)
    ext = run_variant(panel, ctw, EXT_START, end)
    results["7. Combined Simplicity"] = {"clean": clean, "ext": ext, "kw": combine_kw}

    # --- Markdown table ---
    print("\n\n## CPM Simplification Comparison\n")
    print(f"Windows: Clean = {CLEAN_START.date()}..{end.date()}, "
          f"Extended = {EXT_START.date()}..{end.date()}. "
          f"Engine: run_cpm_backtest (T+1 MOO, {COST_BPS_PER_SIDE} bps/side).\n")
    hdr = ("| Variant | Sharpe (Clean) | CAGR % (Clean) | MaxDD % (Clean) "
           "| Sharpe (Ext) | CAGR % (Ext) | MaxDD % (Ext) |")
    sep = "|" + "---|" * 7
    print(hdr)
    print(sep)
    for name in list(VARIANTS.keys()) + ["7. Combined Simplicity"]:
        r = results[name]
        c, e = r["clean"], r["ext"]
        print(f"| {name} | {c['sharpe']:.3f} | {c['cagr']*100:.2f} | {c['maxdd']*100:.2f} "
              f"| {e['sharpe']:.3f} | {e['cagr']*100:.2f} | {e['maxdd']*100:.2f} |")

    # Calmar appendix
    print("\n### Calmar appendix\n")
    print("| Variant | Calmar (Clean) | Calmar (Ext) |")
    print("|---|---|---|")
    for name in list(VARIANTS.keys()) + ["7. Combined Simplicity"]:
        r = results[name]
        print(f"| {name} | {r['clean']['calmar']:.3f} | {r['ext']['calmar']:.3f} |")


if __name__ == "__main__":
    main()
