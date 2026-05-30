"""Throwaway research: INVERSE-VOLATILITY weighting for the CPM sleeve, the
missing cell of the weighting grid between equal-weight (EW-M) and continuous
min-variance (CONT).

Inverse-vol uses ONLY the individual realized vols sigma_i (the diagonal of the
cov matrix), not the full covariance => far less estimation-prone than
continuous min-var, more nuanced than equal-weight. Within a selected M-subset
the weights are w_i proportional to 1/sigma_i, renormalized to sum 1.

SELECTION is IDENTICAL to cardinality_sweep.min_var_subset (the equal-weight
m-subset with lowest portfolio variance; for m=2 this reproduces the production
min_vol_pair). Only the WEIGHTING within the selected set changes. This keeps
the comparison clean: EW-M vs INVVOL-M differ ONLY in the weighting step.

sigma_i = realized vol over the 504d cov window: sqrt of the diagonal of
close[cand].pct_change().dropna(how='all').tail(504).cov() -- the SAME vol used
in the min-var selection (annualization constant cancels in renormalization).

Variants (U=R=C=1, cov lookback 504d, mooex T+1 MOO exact, K=4 top-half):
  INVVOL-2 : min-var 2-subset, inverse-vol weighted.
  INVVOL-3 : min-var 3-subset, inverse-vol weighted.
  INVVOL-4 : min-var 4-subset (= all 4 trend-qualified when >=4 positive),
             inverse-vol weighted.

Partial-safe fallback (matches production cpm_wf, identical to cardinality_sweep):
  - 0 positive-trend candidates  -> 100% safe.
  - 1 positive-trend candidate   -> {pos:0.5, safe:0.5} (partial-safe).
  - 2..M-1 positive candidates   -> inverse-vol weight ALL that qualify.
  - >= M positive candidates     -> min-var M-subset, inverse-vol weighted.

Reference anchors recomputed for trust (CLEAN 18y, 10 bps):
  EW-2  = 1.2424/0.8704/-16.35% ; CONT = 1.2935/0.9618/-15.15%.
Also recomputes EW-2/EW-3/CONT here so the inverse-vol cells sit on one grid.
No production files touched.
"""
import sys, math, json
from itertools import combinations
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.optimize import minimize

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from cpm_live import (
    load_panel, perf_metrics, sig_13612U, best_safe, faber_sma_xs,
    COST_BPS_PER_SIDE, CORR_LOOKBACK_DAYS,
)
import exec_lag_moo_validation_2026_05_30 as H
from sleeve_vs_benchmark_2026_05_30 import stitch_bil, stitch_agg

CONV = "mooex"
CPM_PROD_UNIVERSE = ["QQQ", "SPHQ", "EFA", "EEM", "VNQ", "GLD", "TLT", "DBC"]
CPM_SAFE = ["SHV", "IEF"]


def _cov_window(close, candidates, lookback):
    """Return (cov DataFrame, sigma Series) over the lookback window, matching
    cpm_live.min_vol_pair covariance handling. sigma_i = sqrt(diag(cov))."""
    rets = close[candidates].pct_change().dropna(how="all").tail(lookback)
    if len(rets) < lookback:
        return None, None
    cov = rets.cov()
    if cov.isna().any().any():
        return None, None
    sigma = pd.Series(np.sqrt(np.diag(cov.values)), index=cov.index)
    return cov, sigma


def min_var_subset(close, candidates, lookback, m):
    """Equal-weight m-subset with lowest portfolio variance (selection only).
    Identical to cardinality_sweep.min_var_subset; for m=2 reproduces the
    production min-var pair."""
    if len(candidates) < m:
        return None
    cov, _ = _cov_window(close, candidates, lookback)
    if cov is None:
        return None
    w = 1.0 / m
    best, best_v = None, np.inf
    for combo in combinations(candidates, m):
        sub = cov.loc[list(combo), list(combo)].values
        v = float(w * w * sub.sum())
        if v < best_v:
            best_v, best = v, combo
    return list(best) if best is not None else None


def inv_vol_weights(close, picks, lookback):
    """Inverse-vol weights over `picks` using sigma over the lookback window.
    Falls back to equal-weight if sigma unavailable / degenerate."""
    _, sigma = _cov_window(close, picks, lookback)
    if sigma is None:
        return {t: 1.0 / len(picks) for t in picks}
    inv = {}
    for t in picks:
        s = float(sigma.get(t, np.nan))
        if not np.isfinite(s) or s < 1e-12:
            return {t: 1.0 / len(picks) for t in picks}
        inv[t] = 1.0 / s
    z = sum(inv.values())
    return {t: inv[t] / z for t in picks}


def cpm_wf(close, daily, sig_d, scheme, lookback):
    """CPM production weight fn (U=R=C=1) parametrized by `scheme`:
      'EW2'/'EW3'        -> equal-weight min-var m-subset (anchors).
      'IV2'/'IV3'/'IV4'  -> inverse-vol weighted min-var m-subset.
      'CONT'             -> continuous min-var over all positives.
    """
    universe = CPM_PROD_UNIVERSE
    monthly = close.loc[:sig_d].resample("ME").last()
    safe = best_safe(monthly, sig_d, CPM_SAFE)

    cscores = [sig_13612U(monthly[a]) for a in ["HYG", "TIP"] if a in monthly.columns]
    cscores = [s for s in cscores if pd.notna(s)]
    if not cscores:
        return {safe: 1.0}
    if sum(1 for s in cscores if s > 0) == 0:
        return {safe: 1.0}

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

    # shared 0/1 fallback (matches production cpm_wf)
    if len(positive) == 0:
        return {safe: 1.0}
    if len(positive) == 1:
        return {positive[0]: 0.5, safe: 0.5}

    if scheme == "CONT":
        cov = daily.loc[:sig_d].tail(lookback)[positive].cov() * 252
        n = len(positive)
        def obj(w, Cv=cov.values):
            return float(np.dot(w, np.dot(Cv, w)))
        cons = ({"type": "eq", "fun": lambda w: np.sum(w) - 1.0},)
        bnds = tuple((0.0, 1.0) for _ in range(n))
        r = minimize(obj, np.ones(n) / n, method="SLSQP", bounds=bnds, constraints=cons)
        return {positive[i]: float(r.x[i]) for i in range(n)} if r.success else \
               {t: 1.0 / n for t in positive}

    csub = close.loc[:sig_d]
    if scheme in ("EW2", "EW3"):
        m = {"EW2": 2, "EW3": 3}[scheme]
        n_pos = len(positive)
        if n_pos < m:
            return {t: 1.0 / n_pos for t in positive}
        pick = min_var_subset(csub, positive, lookback, m)
        if pick is None:
            return {t: 1.0 / n_pos for t in positive}
        return {t: 1.0 / m for t in pick}

    # inverse-vol schemes
    m = {"IV2": 2, "IV3": 3, "IV4": 4}[scheme]
    n_pos = len(positive)
    if n_pos < m:
        # fewer positives than target M -> inverse-vol weight ALL that qualify
        return inv_vol_weights(csub, positive, lookback)
    pick = min_var_subset(csub, positive, lookback, m)
    if pick is None:
        return inv_vol_weights(csub, positive, lookback)
    return inv_vol_weights(csub, pick, lookback)


def sig_dates(close, start, end):
    monthly_idx = (pd.DataFrame({"x": 1}, index=close.index)
                   .groupby(pd.Grouper(freq="ME")).tail(1))
    return monthly_idx.index[(monthly_idx.index >= start) & (monthly_idx.index <= end)].tolist()


def weight_series(close, daily, sigs, scheme, lookback=CORR_LOOKBACK_DAYS):
    return [(sd, cpm_wf(close, daily, sd, scheme, lookback)) for sd in sigs]


def l1(wa, wb):
    keys = set(wa) | set(wb)
    return sum(abs(wa.get(k, 0.0) - wb.get(k, 0.0)) for k in keys)


def basket(w, thr=1e-6):
    return frozenset(k for k, v in w.items() if abs(v) > thr)


def is_risk_on(w):
    return any(k not in CPM_SAFE for k in basket(w))


def concentration(w):
    vals = [v for v in w.values() if v > 1e-9]
    hhi = sum(v * v for v in vals)
    return max(vals) if vals else 0.0, (1.0 / hhi if hhi > 0 else float("nan"))


def analyze_weights(ws, n_years):
    weights = [w for _, w in ws]
    dws = [l1(weights[i], weights[i - 1]) for i in range(1, len(weights))]
    total_rt = sum(dws)
    ann_rt = total_rt / n_years
    baskets = [basket(w) for w in weights]
    basket_changes = sum(1 for i in range(1, len(baskets)) if baskets[i] != baskets[i - 1])
    any_change = sum(1 for d in dws if d > 1e-6)
    n_trans = len(dws)
    conc_all = [concentration(w) for w in weights]
    conc_ron = [concentration(w) for w in weights if is_risk_on(w)]
    return {
        "n_rebal": len(weights), "n_trans": n_trans, "n_risk_on": len(conc_ron),
        "ann_turnover_roundtrip": ann_rt, "ann_turnover_oneway": ann_rt / 2.0,
        "mean_l1_move": float(np.mean(dws)) if dws else 0.0,
        "basket_change_freq": basket_changes / n_trans if n_trans else 0.0,
        "frac_months_changed": any_change / n_trans if n_trans else 0.0,
        "avg_max_weight_all": float(np.mean([c[0] for c in conc_all])),
        "avg_eff_n_all": float(np.mean([c[1] for c in conc_all])),
        "avg_max_weight_riskon": float(np.mean([c[0] for c in conc_ron])) if conc_ron else float("nan"),
        "avg_eff_n_riskon": float(np.mean([c[1] for c in conc_ron])) if conc_ron else float("nan"),
        "max_single_weight": float(max(c[0] for c in conc_all)),
    }


def returns_for(close, daily, intraday, overnight, start, end, scheme, cost_bps):
    wf = lambda sd: cpm_wf(close, daily, sd, scheme, CORR_LOOKBACK_DAYS)
    s, _ = H._segment_returns_conv(close, daily, wf, start, end, CONV,
                                   cost_bps, intraday, overnight)
    return s


def met(daily, cash):
    m = perf_metrics(daily, cash)
    return {"sharpe": m.get("sharpe"), "cagr": m.get("cagr"),
            "maxdd": m.get("max_drawdown"), "calmar": m.get("calmar"), "vol": m.get("vol")}


SCHEMES = [("EW2", "EW-2 pair (prod)"), ("EW3", "EW-3 triplet"),
           ("IV2", "INVVOL-2"), ("IV3", "INVVOL-3"), ("IV4", "INVVOL-4"),
           ("CONT", "continuous min-var")]


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
    cost_grid = [0, 10, 25, 50]

    out = {"meta": {"conv": CONV, "lookback": CORR_LOOKBACK_DAYS,
                    "cost_bps_prod": COST_BPS_PER_SIDE, "K_top_half": 4,
                    "clean_start": str(clean_start.date()), "ext_start": str(ext_start.date()),
                    "end": str(end.date())},
           "windows": {}}

    print("Computing return series (ext, all schemes, cost grid)...")
    ret_cache = {}
    for scheme, _ in SCHEMES:
        for cb in cost_grid:
            ret_cache[(scheme, cb)] = returns_for(close, daily, intraday, overnight,
                                                  ext_start, end, scheme, cb)
        print(f"  scheme {scheme} done")

    for wn, (ws_, we_) in windows.items():
        n_years = (we_ - ws_).days / 365.25
        sigs = sig_dates(close, ws_, we_)
        wd = {"n_years": round(n_years, 3), "schemes": {}}
        for scheme, label in SCHEMES:
            ws = weight_series(close, daily, sigs, scheme)
            wa = analyze_weights(ws, n_years)
            wa["label"] = label
            perf = {}
            for cb in cost_grid:
                s = ret_cache[(scheme, cb)]
                sw = s.loc[(s.index >= ws_) & (s.index <= we_)]
                perf[cb] = met(sw, cash)
            wa["perf"] = perf
            wd["schemes"][scheme] = wa
        out["windows"][wn] = wd

    # estimation sensitivity: lookback 504 -> 480/528, mean L1 weight move (ext sigs)
    print("Estimation sensitivity (lookback perturbation)...")
    sens = {}
    sigs_ext = sig_dates(close, ext_start, end)
    for scheme, label in SCHEMES:
        base = {sd: w for sd, w in weight_series(close, daily, sigs_ext, scheme, 504)}
        moves = {}
        for lb in (480, 528):
            pert = {sd: w for sd, w in weight_series(close, daily, sigs_ext, scheme, lb)}
            ds = [l1(base[sd], pert[sd]) for sd in sigs_ext]
            moves[lb] = {"mean_l1": float(np.mean(ds)), "max_l1": float(np.max(ds)),
                         "frac_changed": float(np.mean([1 for d in ds if d > 1e-6]))}
        sens[label] = moves
    out["estimation_sensitivity"] = sens

    Path(__file__).with_suffix(".json").write_text(json.dumps(out, indent=2, default=float))

    print("\n=== VERIFY anchors (CLEAN, 10 bps) ===")
    e2 = out["windows"]["CLEAN"]["schemes"]["EW2"]["perf"][10]
    e3 = out["windows"]["CLEAN"]["schemes"]["EW3"]["perf"][10]
    c0 = out["windows"]["CLEAN"]["schemes"]["CONT"]["perf"][10]
    print(f"  EW-2 : sharpe={e2['sharpe']:.4f} calmar={e2['calmar']:.4f} "
          f"maxdd={e2['maxdd']*100:.2f}%  (expect 1.2424/0.8704/-16.35%)")
    print(f"  EW-3 : sharpe={e3['sharpe']:.4f} calmar={e3['calmar']:.4f} "
          f"maxdd={e3['maxdd']*100:.2f}%  (expect 1.2229/0.8536/-16.86%)")
    print(f"  CONT : sharpe={c0['sharpe']:.4f} calmar={c0['calmar']:.4f} "
          f"maxdd={c0['maxdd']*100:.2f}%  (expect 1.2935/0.9618/-15.15%)")

    print("\n=== INVERSE-VOL GRID (net 10 bps) ===")
    for wn in ("CLEAN", "EXT"):
        print(f"\n[{wn}]  scheme              Sharpe   CAGR    Vol     MaxDD    Calmar")
        for scheme, label in SCHEMES:
            p = out["windows"][wn]["schemes"][scheme]["perf"][10]
            print(f"  {label:<20} {p['sharpe']:.4f}  {p['cagr']*100:5.2f}%  "
                  f"{p['vol']*100:5.2f}%  {p['maxdd']*100:6.2f}%  {p['calmar']:.4f}")
    print("\nDONE -> json written")
    return out


if __name__ == "__main__":
    main()
