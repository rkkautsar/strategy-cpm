"""Throwaway research (analyst, read-only re production): map CONTINUOUS
minimum-variance weighting robustness across a 2D grid of K (candidate pool
size) x covariance lookback.

We are considering continuous min-variance as the production CPM weighting (no
incumbent yet). The original K=4 and 504d were chosen under the equal-weight
PAIR regime; this re-examines whether they remain right under CONTINUOUS
weighting (which can optimize weights over more assets, so it may prefer a
larger K and/or a different cov lookback).

Setup: CPM sleeve, U=R=C on (production universe/ranker/canary), weighting =
CONTINUOUS min-variance over the top-K trend-qualified candidates (NOT the
pair). Execution = realistic T+1 MOO exact (mooex), 10 bps/side. Reuses the
pair_vs_continuous_minvar / pair_vs_continuous_by_covlookback harness; only K
(top-K momentum pool) and cov lookback are parametrized, selection logic
identical otherwise.

Grid: K in {2,3,4,5,6} x cov lookback in {126,252,504,756,1008,1260}.
Windows: CLEAN 18y (2008-05-30..), EXT 27y (1999-03-10..).

Anchor: K=4 / 504d continuous must reproduce CLEAN 1.2935 / -15.15% / 0.9618.

No production files touched. Writes findings md + json next to this file.
"""
import sys, math, json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.optimize import minimize

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from cpm_live import (
    load_panel, perf_metrics, sig_13612U, best_safe, faber_sma_xs,
    COST_BPS_PER_SIDE,
)
import exec_lag_moo_validation_2026_05_30 as H
from sleeve_vs_benchmark_2026_05_30 import stitch_bil, stitch_agg

CONV = "mooex"
CPM_PROD_UNIVERSE = ["QQQ", "SPHQ", "EFA", "EEM", "VNQ", "GLD", "TLT", "DBC"]
CPM_SAFE = ["SHV", "IEF"]

KS = [2, 3, 4, 5, 6]
LOOKBACKS = [126, 252, 504, 756, 1008, 1260]
PROD_K = 4
PROD_LB = 504


def cpm_wf_K(close, daily, sig_d, K, lookback):
    """CPM production weight fn (U=R=C=1), CONTINUOUS min-var over the top-K
    trend-qualified candidates with cov `lookback`. K replaces the production
    top-half (=4). Selection/canary/safe/fallback logic otherwise identical to
    pair_vs_continuous_minvar.cpm_wf_lb (P=0 branch)."""
    universe = CPM_PROD_UNIVERSE
    monthly = close.loc[:sig_d].resample("ME").last()
    safe = best_safe(monthly, sig_d, CPM_SAFE)

    # canary: HYG-OR-TIP any-positive (C=1)
    cscores = [sig_13612U(monthly[a]) for a in ["HYG", "TIP"] if a in monthly.columns]
    cscores = [s for s in cscores if pd.notna(s)]
    if not cscores:
        return {safe: 1.0}
    if sum(1 for s in cscores if s > 0) == 0:
        return {safe: 1.0}

    # ranker: vol-adjusted Faber (R=1), top-K, positive screen
    present = [t for t in universe if t in monthly.columns]
    faber = faber_sma_xs(monthly)
    avail = [t for t in present if t in faber.index and pd.notna(faber[t])
             and (sig_d in close.index and pd.notna(close.loc[sig_d].get(t, np.nan)))]
    if not avail:
        return {safe: 1.0}
    dr = close[avail].ffill().pct_change()
    score = {}
    for t in avail:
        v = dr[t].loc[:sig_d].tail(252).std() * np.sqrt(252)
        if pd.isna(v) or v < 1e-9:
            v = 1.0
        score[t] = float(faber[t]) / v
    ranked = pd.Series(score).sort_values(ascending=False)
    top_k = max(2, min(K, len(ranked)))
    top = ranked.iloc[:top_k]
    positive = [t for t in top.index if faber.get(t, -np.inf) > 0]

    if len(positive) == 0:
        return {safe: 1.0}
    if len(positive) == 1:
        return {positive[0]: 0.5, safe: 0.5}

    # continuous min-var over survivors
    cov = daily.loc[:sig_d].tail(lookback)[positive].cov() * 252
    n = len(positive)
    def obj(w, Cv=cov.values):
        return float(np.dot(w, np.dot(Cv, w)))
    cons = ({"type": "eq", "fun": lambda w: np.sum(w) - 1.0},)
    bnds = tuple((0.0, 1.0) for _ in range(n))
    r = minimize(obj, np.ones(n) / n, method="SLSQP", bounds=bnds, constraints=cons)
    return {positive[i]: float(r.x[i]) for i in range(n)} if r.success else \
           {t: 1.0 / n for t in positive}


def sig_dates(close, start, end):
    monthly_idx = (pd.DataFrame({"x": 1}, index=close.index)
                   .groupby(pd.Grouper(freq="ME")).tail(1))
    return monthly_idx.index[(monthly_idx.index >= start) & (monthly_idx.index <= end)].tolist()


def weight_series(close, daily, sigs, K, lookback):
    return [(sd, cpm_wf_K(close, daily, sd, K, lookback)) for sd in sigs]


def basket(w, thr=1e-6):
    return frozenset(k for k, v in w.items() if abs(v) > thr)


def is_risk_on(w):
    return any(k not in CPM_SAFE for k in basket(w))


def concentration(w):
    vals = [v for v in w.values() if v > 1e-9]
    hhi = sum(v * v for v in vals)
    return max(vals) if vals else 0.0, (1.0 / hhi if hhi > 0 else float("nan"))


def analyze_weights(ws):
    weights = [w for _, w in ws]
    conc_ron = [concentration(w) for w in weights if is_risk_on(w)]
    conc_all = [concentration(w) for w in weights]
    return {
        "n_risk_on": len(conc_ron),
        "avg_max_weight_riskon": float(np.mean([c[0] for c in conc_ron])) if conc_ron else float("nan"),
        "avg_eff_n_riskon": float(np.mean([c[1] for c in conc_ron])) if conc_ron else float("nan"),
        "max_single_weight_riskon": float(max(c[0] for c in conc_ron)) if conc_ron else float("nan"),
        "avg_max_weight_all": float(np.mean([c[0] for c in conc_all])),
        "max_single_weight": float(max(c[0] for c in conc_all)),
    }


def returns_for(close, daily, intraday, overnight, start, end, K, lb, cost_bps):
    wf = lambda sd: cpm_wf_K(close, daily, sd, K, lb)
    s, _ = H._segment_returns_conv(close, daily, wf, start, end, CONV,
                                   cost_bps, intraday, overnight)
    return s


def met(daily, cash):
    m = perf_metrics(daily, cash)
    return {"sharpe": float(m.get("sharpe")), "cagr": float(m.get("cagr")),
            "maxdd": float(m.get("max_drawdown")), "calmar": float(m.get("calmar")),
            "vol": float(m.get("vol"))}


def main():
    end = pd.Timestamp("2026-05-22")
    ext_start = pd.Timestamp("1999-03-10")
    clean_start = pd.Timestamp("2008-05-30")

    panel = load_panel(start=ext_start, end=end)
    end = min(end, panel.index[-1])
    cash = panel["SHV"].ffill().pct_change().dropna()
    panel["BIL"] = stitch_bil(panel)
    panel["AGG"] = stitch_agg(panel)

    open_df, close_yf = H.load_open_close()
    intraday = (close_yf / open_df - 1.0).reindex(panel.index)
    overnight = (open_df / close_yf.shift(1) - 1.0).reindex(panel.index)

    cpm_cols = sorted(set(CPM_PROD_UNIVERSE + CPM_SAFE + ["HYG", "TIP"]) & set(panel.columns))
    close = panel[cpm_cols]
    daily = close.ffill().pct_change()

    windows = {"CLEAN": (clean_start, end), "EXT": (ext_start, end)}

    out = {"meta": {"conv": CONV, "cost_bps_prod": COST_BPS_PER_SIDE,
                    "weighting": "continuous_minvar", "U_R_C": "1/1/1",
                    "Ks": KS, "lookbacks": LOOKBACKS, "prod_K": PROD_K, "prod_lb": PROD_LB,
                    "clean_start": str(clean_start.date()),
                    "ext_start": str(ext_start.date()), "end": str(end.date())},
           "grid": {}, "concentration": {}}

    # Compute full-ext return series once per (K, lb) at 10 bps, slice to windows.
    print("Computing return series per (K, lookback) @10bps...")
    ret_cache = {}
    for K in KS:
        for lb in LOOKBACKS:
            ret_cache[(K, lb)] = returns_for(close, daily, intraday, overnight,
                                             ext_start, end, K, lb, 10)
            print(f"  K={K} lb={lb} done")

    for wn, (ws_, we_) in windows.items():
        grid = {}
        for K in KS:
            for lb in LOOKBACKS:
                s = ret_cache[(K, lb)]
                sw = s.loc[(s.index >= ws_) & (s.index <= we_)]
                grid[f"{K}|{lb}"] = met(sw, cash)
        out["grid"][wn] = grid

    # Concentration cross-check per (K, lookback) on each window's signal set.
    print("Concentration cross-check per (K, lookback)...")
    for wn, (ws_, we_) in windows.items():
        sigs = sig_dates(close, ws_, we_)
        cc = {}
        for K in KS:
            for lb in LOOKBACKS:
                ws = weight_series(close, daily, sigs, K, lb)
                cc[f"{K}|{lb}"] = analyze_weights(ws)
        out["concentration"][wn] = cc

    Path(__file__).with_suffix(".json").write_text(json.dumps(out, indent=2, default=float))

    # ---- verify anchor at K=4/504d CLEAN 10bps ----
    print("\n=== VERIFY anchor (CLEAN, K=4, 504d, 10 bps) ===")
    a = out["grid"]["CLEAN"]["4|504"]
    print(f"  continuous: sharpe={a['sharpe']:.4f} maxdd={a['maxdd']*100:.2f}% "
          f"calmar={a['calmar']:.4f}  (expect 1.2935/-15.15%/0.9618)")
    print("\nDONE -> json written")
    return out


if __name__ == "__main__":
    main()
