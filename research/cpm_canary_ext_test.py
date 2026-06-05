# -*- coding: utf-8 -*-
"""Canary value test in the EXTENDED (crisis-rich) window on the NEW min-var prod base.

QUESTION: in the ext window (dot-com 2000-02 + GFC 2008 in-sample), does the
CANARY earn its keep on the min-var 3-of-4 production config? Specifically, does
TIP-only canary significantly beat NO-canary (path-independent: dSharpe/dSortino/
dCVaR, paired block bootstrap)? And does HYG add anything over TIP-only?

Three configs (all on NEW min-var prod base; vary ONLY the canary):
  - NO canary    : always risk-on (no gate).
  - TIP-only     : risk-off unless TIP 13612U > 0.
  - HYG-or-TIP   : current prod (any-positive over HYG/TIP). HYG<-VWEHX pre-2007;
                   TIP<-VIPSX ~2000+.

Windows: EXT (1999+) is the DECISION lens; clean (2008+) reported for contrast.
Bootstrap: paired block B=2000 block=21 seed=42 on ext (TIP-only vs no-canary,
and HYG-or-TIP vs TIP-only).

Research-only. Does NOT modify prod/memo/cpm_live. No commit.
"""
from __future__ import annotations

import json
import numpy as np
import pandas as pd

import research.cpm_harness as H
from research.cpm_bootstrap_multimetric import paired_block_bootstrap_mm

import cpm_live
from cpm_live import (
    compute_target_weights,
    sig_13612U,
    best_safe,
    faber_sma_xs,
    inv_vol_weights,
    _min_var_subset,
    RISKY_UNIVERSE,
    SAFE_POOL,
    TOP_K_CANDIDATES,
    CORR_LOOKBACK_DAYS,
)
import numpy as _np  # noqa


# ---------- weight functions (vary ONLY the canary) ----------

def wf_hyg_or_tip(panel, sig_d):
    """Current prod: HYG-or-TIP any-positive canary."""
    return compute_target_weights(panel, sig_d)  # default canary_assets=["HYG","TIP"]


def wf_tip_only(panel, sig_d):
    """TIP-only canary: risk-on iff TIP 13612U>0 (single-asset any_positive)."""
    return compute_target_weights(panel, sig_d, canary_assets=["TIP"])


def wf_no_canary(panel, sig_d):
    """NO canary: always risk-on. Replicates prod min-var selection EXACTLY
    minus the canary gate. (Mirrors cpm_live.compute_target_weights body.)"""
    universe = RISKY_UNIVERSE
    safe_pool = SAFE_POOL
    monthly = panel.loc[:sig_d].resample("ME").last()
    safe = best_safe(monthly, sig_d, safe_pool)

    # --- NO canary gate here (always proceed to selection) ---

    faber = faber_sma_xs(monthly)
    avail = [t for t in universe
             if t in faber.index and pd.notna(faber[t])
             and pd.notna(panel.loc[sig_d].get(t, np.nan) if sig_d in panel.index else np.nan)]
    if not avail:
        return {safe: 1.0}, None, "DEFENSIVE", safe

    daily_rets = panel[avail].ffill().pct_change()
    scores = {}
    for t in avail:
        v = daily_rets[t].loc[:sig_d].tail(252).std() * np.sqrt(252)
        if pd.isna(v) or v < 1e-9:
            v = 1.0
        scores[t] = float(faber[t]) / v
    sa = pd.Series(scores)
    ranked = sa.sort_values(ascending=False)
    top_k = max(2, min(TOP_K_CANDIDATES, len(ranked)))
    top = ranked.iloc[:top_k]
    positive = top[top.index.map(lambda t: faber.get(t, -np.inf) > 0)]

    if len(positive) == 0:
        return {safe: 1.0}, None, "DEFENSIVE", safe

    positive_picks = list(positive.index)
    n_pos = len(positive_picks)
    if n_pos == 4:
        picks = _min_var_subset(panel, sig_d, positive_picks, CORR_LOOKBACK_DAYS, 3)
    else:
        picks = positive_picks

    risky_fraction = min(n_pos, 4) / 4.0
    safe_fraction = 1.0 - risky_fraction
    csub = panel.loc[:sig_d]
    risky_w = inv_vol_weights(csub, picks, CORR_LOOKBACK_DAYS)
    out = {t: w * risky_fraction for t, w in risky_w.items()}
    if safe_fraction > 0:
        out[safe] = out.get(safe, 0.0) + safe_fraction
    return out, tuple(picks), "RISK_ON", safe


CONFIGS = {
    "no_canary": wf_no_canary,
    "tip_only": wf_tip_only,
    "hyg_or_tip": wf_hyg_or_tip,
}


# ---------- per-crisis drawdown ----------

CRISES = {
    "Dot-com (2000-02)": ("2000-03-01", "2002-12-31"),
    "GFC (2008)":        ("2007-10-01", "2009-06-30"),
    "COVID (2020)":      ("2020-02-01", "2020-06-30"),
    "2022":              ("2022-01-01", "2022-12-31"),
    "2025":              ("2025-01-01", "2026-05-22"),
}


def equity_from_returns(r: pd.Series) -> pd.Series:
    return (1.0 + r.fillna(0.0)).cumprod()


def crisis_dd(r: pd.Series, lo: str, hi: str) -> float | None:
    """Worst drawdown whose trough lies in [lo,hi]; running max from curve start."""
    eq = equity_from_returns(r).dropna()
    rm = eq.cummax()
    dd = eq / rm - 1.0
    w = dd.loc[lo:hi]
    if len(w) == 0 or not np.isfinite(w.min()):
        return None
    return float(w.min())


def descriptors(r: pd.Series, cash: pd.Series) -> dict:
    m = cpm_live.perf_metrics(r, cash)
    return {
        "Sharpe": m.get("sharpe"),
        "Sortino": _sortino_full(r),
        "CVaR_ratio": _cvar_full(r),
        "Calmar": m.get("calmar"),
        "Martin": m.get("martin"),
        "MaxDD": m.get("max_drawdown"),
        "CAGR": m.get("cagr"),
        "vol": m.get("vol"),
    }


def _sortino_full(r):
    x = r.dropna().values.astype(float)
    if x.size == 0:
        return float("nan")
    neg = np.minimum(x, 0.0)
    dd = np.sqrt(np.mean(neg ** 2))
    if dd <= 0:
        return float("nan")
    return (x.mean() * 252.0) / (dd * np.sqrt(252.0))


def _cvar_full(r, q=0.05):
    x = r.dropna().values.astype(float)
    n = x.size
    if n == 0:
        return float("nan")
    k = max(1, int(np.floor(q * n)))
    worst = np.sort(x)[:k]
    es = np.mean(worst)
    if es >= 0:
        return float("nan")
    return (x.mean() * 252.0) / abs(es)


def main():
    d = H.load_data()
    print("Verifying anchor...")
    H.verify_anchor(data=d)
    print("ANCHOR OK\n")

    results = {"clean": {}, "ext": {}}
    series = {"clean": {}, "ext": {}}

    for win in ("clean", "ext"):
        for name, wf in CONFIGS.items():
            r = H.run_strategy(wf, window=win, data=d)
            series[win][name] = r
            desc = descriptors(r, d.cash)
            cd = {c: crisis_dd(r, lo, hi) for c, (lo, hi) in CRISES.items()}
            results[win][name] = {"desc": desc, "crisis_dd": cd,
                                  "start": str(r.index[0].date()),
                                  "end": str(r.index[-1].date()),
                                  "n": int(len(r))}

    # ---------- bootstrap on EXT ----------
    print("Bootstrapping (ext, B=2000 block=21 seed=42)...")
    boot = {}
    # TIP-only vs no-canary (key question)
    boot["tip_only_vs_no_canary"] = paired_block_bootstrap_mm(
        series["ext"]["tip_only"], series["ext"]["no_canary"], d.cash,
        B=2000, block=21, seed=42)
    # HYG-or-TIP vs TIP-only (does HYG add anything)
    boot["hyg_or_tip_vs_tip_only"] = paired_block_bootstrap_mm(
        series["ext"]["hyg_or_tip"], series["ext"]["tip_only"], d.cash,
        B=2000, block=21, seed=42)

    out = {"results": results, "bootstrap_ext": boot,
           "anchor": H.ANCHOR, "crises": CRISES}
    with open("research/cpm_canary_ext_test.json", "w") as f:
        json.dump(out, f, indent=2, default=float)

    # ---------- print tables ----------
    def fmt(v, pct=False):
        if v is None or (isinstance(v, float) and not np.isfinite(v)):
            return "  n/a"
        return f"{v*100:7.2f}%" if pct else f"{v:8.4f}"

    for win in ("ext", "clean"):
        print("\n" + "=" * 92)
        print(f"WINDOW = {win.upper()}  ({results[win]['no_canary']['start']} .. "
              f"{results[win]['no_canary']['end']})")
        print("=" * 92)
        hdr = f"{'config':<14}{'Sharpe':>9}{'Sortino':>9}{'CVaRr':>9}{'Calmar':>9}{'Martin':>9}{'MaxDD':>9}{'CAGR':>9}{'vol':>9}"
        print(hdr)
        for name in CONFIGS:
            de = results[win][name]["desc"]
            print(f"{name:<14}{fmt(de['Sharpe'])}{fmt(de['Sortino'])}{fmt(de['CVaR_ratio'])}"
                  f"{fmt(de['Calmar'])}{fmt(de['Martin'])}{fmt(de['MaxDD'],1)}"
                  f"{fmt(de['CAGR'],1)}{fmt(de['vol'],1)}")
        print("\nPer-crisis drawdown (trough in window):")
        print(f"{'config':<14}" + "".join(f"{c[:14]:>16}" for c in CRISES))
        for name in CONFIGS:
            cd = results[win][name]["crisis_dd"]
            print(f"{name:<14}" + "".join(f"{fmt(cd[c],1):>16}" for c in CRISES))

    print("\n" + "=" * 92)
    print("BOOTSTRAP (EXT) -- path-independent classification metrics")
    print("=" * 92)
    for cmp_name, b in boot.items():
        print(f"\n{cmp_name}:")
        for met in ("dSharpe", "dSortino", "dCVaR"):
            s = b[met]
            sig = "SIGNIFICANT" if (s["ci_lo"] > 0 or s["ci_hi"] < 0) else "NOISE"
            print(f"  {met:<9} mean={s['mean']:+.4f} CI[{s['ci_lo']:+.4f},{s['ci_hi']:+.4f}] "
                  f"p>0={s['p_gt0']:.3f}  -> {sig}")
        print("  context (path-dependent, soft CIs):")
        for met in ("dCalmar", "dMartin", "dMaxDD"):
            s = b[met]
            print(f"  {met:<9} mean={s['mean']:+.4f} CI[{s['ci_lo']:+.4f},{s['ci_hi']:+.4f}]")

    print("\nDONE. JSON -> research/cpm_canary_ext_test.json")


if __name__ == "__main__":
    main()
