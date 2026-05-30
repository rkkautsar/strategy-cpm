"""Throwaway research: 50/50 min-var PAIR (production) vs continuous min-var
weighting (alternative) for the CPM sleeve.

Reuses the factorial harness (factorial_decomposition_2026_05_30.cpm_wf,
exec_lag_moo_validation_2026_05_30._segment_returns_conv). The P factor toggles
weighting: P=1 = 50/50 pair (production); P=0 = continuous min-var.

Both schemes held at U=1,R=1,C=1 (production universe/ranker/canary), so the
ONLY difference is the weighting step. Execution = realistic T+1 MOO exact
(mooex), production slow vol gate context baked into the CPM weight fn (CPM is
gate-independent). Windows: CLEAN 18y (2008-05-30..), EXT 27y (1999-03-10..).

Computes, per scheme x window:
  1. Turnover (annualized sum|dw| round-trip & one-way) + cost drag @10/25/50 bps.
  2. Pre-cost (0 bps) vs post-cost (10 bps) Sharpe/CAGR; cost sweep -> break-even
     bps where pair overtakes continuous on net Sharpe.
  3. Concentration: avg/max single-asset weight, effective N = 1/HHI.
  4. Holding/signal stability: basket-change frequency, fraction of months with
     any weight change, mean month-to-month L1 weight move.
  5. Estimation sensitivity: perturb cov lookback 504 -> 480/528 d, mean L1
     weight move.

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
    load_panel, perf_metrics, sig_13612U, best_safe, faber_sma_xs, min_vol_pair,
    COST_BPS_PER_SIDE, CORR_LOOKBACK_DAYS,
)
import exec_lag_moo_validation_2026_05_30 as H
from sleeve_vs_benchmark_2026_05_30 import stitch_bil, stitch_agg

CONV = "mooex"
CPM_PROD_UNIVERSE = ["QQQ", "SPHQ", "EFA", "EEM", "VNQ", "GLD", "TLT", "DBC"]
CPM_SAFE = ["SHV", "IEF"]


def cpm_wf_lb(close, daily, sig_d, P, lookback):
    """CPM production weight fn (U=R=C=1) parametrized by weighting scheme P and
    cov lookback. Mirrors factorial_decomposition_2026_05_30.cpm_wf for U=R=C=1.
    P=1 -> 50/50 min-var pair; P=0 -> continuous min-var."""
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

    # ranker: vol-adjusted Faber (R=1), top-half=4, positive screen
    top_half = max(2, math.ceil(len(universe) / 2))
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
    top_k = max(2, min(top_half, len(ranked)))
    top = ranked.iloc[:top_k]
    positive = [t for t in top.index if faber.get(t, -np.inf) > 0]

    if len(positive) == 0:
        return {safe: 1.0}
    if len(positive) == 1:
        return {positive[0]: 0.5, safe: 0.5}

    if P:  # 50/50 min-var pair
        pick = min_vol_pair(close.loc[:sig_d, positive], positive, lookback)
        if pick is None:
            return {positive[0]: 1.0}
        return {pick[0]: 0.5, pick[1]: 0.5}
    else:  # continuous min-var over survivors
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


def weight_series(close, daily, sigs, P, lookback=CORR_LOOKBACK_DAYS):
    """Return list of (sig_d, weights dict) for each rebalance."""
    return [(sd, cpm_wf_lb(close, daily, sd, P, lookback)) for sd in sigs]


def l1(wa, wb):
    keys = set(wa) | set(wb)
    return sum(abs(wa.get(k, 0.0) - wb.get(k, 0.0)) for k in keys)


def basket(w, thr=1e-6):
    return frozenset(k for k, v in w.items() if abs(v) > thr)


def is_risk_on(w):
    """Risk-on = holds at least one non-safe asset."""
    return any(k not in CPM_SAFE for k in basket(w))


def concentration(w):
    vals = [v for v in w.values() if v > 1e-9]
    hhi = sum(v * v for v in vals)
    return max(vals) if vals else 0.0, (1.0 / hhi if hhi > 0 else float("nan"))


def analyze_weights(ws, n_years):
    """ws: list of (sig_d, weights). Returns turnover/concentration/stability."""
    weights = [w for _, w in ws]
    # turnover (round-trip sum|dw|) per rebalance, skip first (no prior)
    dws = [l1(weights[i], weights[i - 1]) for i in range(1, len(weights))]
    total_rt = sum(dws)
    ann_rt = total_rt / n_years
    ann_ow = ann_rt / 2.0
    # stability
    baskets = [basket(w) for w in weights]
    basket_changes = sum(1 for i in range(1, len(baskets)) if baskets[i] != baskets[i - 1])
    any_change = sum(1 for d in dws if d > 1e-6)
    n_trans = len(dws)
    # concentration (all months + risk-on subset)
    conc_all = [concentration(w) for w in weights]
    conc_ron = [concentration(w) for w in weights if is_risk_on(w)]
    maxw_all = np.mean([c[0] for c in conc_all])
    effn_all = np.mean([c[1] for c in conc_all])
    maxw_ron = np.mean([c[0] for c in conc_ron]) if conc_ron else float("nan")
    effn_ron = np.mean([c[1] for c in conc_ron]) if conc_ron else float("nan")
    max_single = max(c[0] for c in conc_all)
    return {
        "n_rebal": len(weights), "n_trans": n_trans, "n_risk_on": len(conc_ron),
        "ann_turnover_roundtrip": ann_rt, "ann_turnover_oneway": ann_ow,
        "mean_l1_move": float(np.mean(dws)) if dws else 0.0,
        "basket_change_freq": basket_changes / n_trans if n_trans else 0.0,
        "frac_months_changed": any_change / n_trans if n_trans else 0.0,
        "avg_max_weight_all": float(maxw_all), "avg_eff_n_all": float(effn_all),
        "avg_max_weight_riskon": float(maxw_ron), "avg_eff_n_riskon": float(effn_ron),
        "max_single_weight": float(max_single),
    }


def returns_for(close, daily, intraday, overnight, start, end, P, cost_bps):
    wf = lambda sd: cpm_wf_lb(close, daily, sd, P, CORR_LOOKBACK_DAYS)
    s, _ = H._segment_returns_conv(close, daily, wf, start, end, CONV,
                                   cost_bps, intraday, overnight)
    return s


def met(daily, cash):
    m = perf_metrics(daily, cash)
    return {"sharpe": m.get("sharpe"), "cagr": m.get("cagr"),
            "maxdd": m.get("max_drawdown"), "calmar": m.get("calmar"), "vol": m.get("vol")}


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
    cost_grid = [0, 5, 10, 15, 20, 25, 30, 40, 50, 75, 100]

    out = {"meta": {"conv": CONV, "lookback": CORR_LOOKBACK_DAYS,
                    "cost_bps_prod": COST_BPS_PER_SIDE,
                    "clean_start": str(clean_start.date()), "ext_start": str(ext_start.date()),
                    "end": str(end.date())},
           "windows": {}}

    # full-ext returns per scheme per cost, sliced to windows
    print("Computing return series (ext, both schemes, cost grid)...")
    ret_cache = {}  # (P, cost) -> series
    for P in (1, 0):
        for cb in cost_grid:
            ret_cache[(P, cb)] = returns_for(close, daily, intraday, overnight,
                                             ext_start, end, P, cb)
        print(f"  scheme P={P} done")

    for wn, (ws_, we_) in windows.items():
        n_years = (we_ - ws_).days / 365.25
        sigs = sig_dates(close, ws_, we_)
        wd = {"n_years": round(n_years, 3), "schemes": {}, "cost_sweep": {}}

        for P, label in [(1, "pair_5050"), (0, "continuous_minvar")]:
            ws = weight_series(close, daily, sigs, P)
            wa = analyze_weights(ws, n_years)
            # perf at 0 and 10 bps
            perf = {}
            for cb in (0, 10):
                s = ret_cache[(P, cb)]
                sw = s.loc[(s.index >= ws_) & (s.index <= we_)]
                perf[cb] = met(sw, cash)
            wa["perf_0bps"] = perf[0]
            wa["perf_10bps"] = perf[10]
            wa["cost_drag_bps"] = {b: wa["ann_turnover_roundtrip"] * b / 10000.0
                                   for b in (10, 25, 50)}
            wd["schemes"][label] = wa

        # cost sweep net Sharpe & CAGR for break-even
        for cb in cost_grid:
            row = {}
            for P, label in [(1, "pair_5050"), (0, "continuous_minvar")]:
                s = ret_cache[(P, cb)]
                sw = s.loc[(s.index >= ws_) & (s.index <= we_)]
                m = met(sw, cash)
                row[label] = {"sharpe": m["sharpe"], "cagr": m["cagr"], "calmar": m["calmar"]}
            wd["cost_sweep"][cb] = row
        out["windows"][wn] = wd

    # estimation sensitivity: lookback 504 -> 480/528, mean L1 weight move (clean+ext sigs union=ext)
    print("Estimation sensitivity (lookback perturbation)...")
    sens = {}
    sigs_ext = sig_dates(close, ext_start, end)
    for P, label in [(1, "pair_5050"), (0, "continuous_minvar")]:
        base = {sd: w for sd, w in weight_series(close, daily, sigs_ext, P, 504)}
        moves = {}
        for lb in (480, 528):
            pert = {sd: w for sd, w in weight_series(close, daily, sigs_ext, P, lb)}
            ds = [l1(base[sd], pert[sd]) for sd in sigs_ext]
            moves[lb] = {"mean_l1": float(np.mean(ds)), "max_l1": float(np.max(ds)),
                         "frac_changed": float(np.mean([1 for d in ds if d > 1e-6]))}
        sens[label] = moves
    out["estimation_sensitivity"] = sens

    Path(__file__).with_suffix(".json").write_text(json.dumps(out, indent=2, default=float))

    # ---- console verify ----
    print("\n=== VERIFY anchors (CLEAN, 10 bps) ===")
    p1 = out["windows"]["CLEAN"]["schemes"]["pair_5050"]["perf_10bps"]
    p0 = out["windows"]["CLEAN"]["schemes"]["continuous_minvar"]["perf_10bps"]
    print(f"  pair_5050        : sharpe={p1['sharpe']:.4f} calmar={p1['calmar']:.4f} "
          f"maxdd={p1['maxdd']*100:.2f}%  (expect 1.2424/0.8704/-16.35%)")
    print(f"  continuous_minvar: sharpe={p0['sharpe']:.4f} calmar={p0['calmar']:.4f} "
          f"maxdd={p0['maxdd']*100:.2f}%  (expect 1.2935/0.9618/-15.15%)")
    print("\nDONE -> json written")
    return out


if __name__ == "__main__":
    main()
