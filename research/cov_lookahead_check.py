"""Throwaway research: covariance-lookahead / cov-timing test for the CPM sleeve
weighting step. 50/50 min-var PAIR (production) vs continuous min-var.

Hypothesis: continuous min-var uses the covariance VALUES to set weights, so it
amplifies any covariance estimate timing/leakage edge. The 50/50 pair uses the
covariance only for SELECTION (rank by pair-variance, pick 2 lowest), so it is
sensitive only to the RANK ORDER, not magnitudes -> structurally rank-robust.

Experiment: lag ONLY the covariance window endpoint back by k monthly rebalances
(cov window ends at the prior rebalance date sigs[i-k] instead of sig_d), keeping
everything else identical (universe, canary, ranker, safe pick, survivor set
`positive` all still computed AS-OF sig_d). This provably prevents the covariance
from peeking into the current holding period. If continuous's edge over the pair
ERODES under lagged cov while the pair is ~unchanged, that edge was a cov-timing
artifact the pair avoids by construction.

lag=0 == baseline (must reproduce anchors): cov window ends at sig_d.
lag=1 == cov window ends at PRIOR rebalance (provably no peek into holding bar).
lag=2,3 == deliberately stale cov (degradation map).

Reuses cpm_wf_lb structure from pair_vs_continuous_minvar.py + the mooex T+1 MOO
segment harness. No production files touched.

Headline convention: T+1 MOO exact (mooex), 10 bps/side, CLEAN 18y + EXT 27y.
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


def cpm_wf_lag(close, daily, sig_d, P, cov_d, lookback=CORR_LOOKBACK_DAYS):
    """CPM production weight fn (U=R=C=1), weighting scheme P, but the covariance
    window ends at cov_d (<= sig_d) instead of sig_d. Everything else (canary,
    ranker, safe, survivor set) is computed AS-OF sig_d. P=1 -> 50/50 min-var
    pair; P=0 -> continuous min-var.

    cov_d == sig_d reproduces the baseline (pair_vs_continuous_minvar.cpm_wf_lb).
    """
    universe = CPM_PROD_UNIVERSE
    monthly = close.loc[:sig_d].resample("ME").last()
    safe = best_safe(monthly, sig_d, CPM_SAFE)

    # canary: HYG-OR-TIP any-positive (C=1) -- AS-OF sig_d
    cscores = [sig_13612U(monthly[a]) for a in ["HYG", "TIP"] if a in monthly.columns]
    cscores = [s for s in cscores if pd.notna(s)]
    if not cscores:
        return {safe: 1.0}
    if sum(1 for s in cscores if s > 0) == 0:
        return {safe: 1.0}

    # ranker: vol-adjusted Faber (R=1), top-half=4, positive screen -- AS-OF sig_d
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

    # ---- COVARIANCE STEP: window ends at cov_d (lagged), not sig_d ----
    if P:  # 50/50 min-var pair: cov used only for SELECTION (rank order)
        pick = min_vol_pair(close.loc[:cov_d, positive], positive, lookback)
        if pick is None:
            return {positive[0]: 1.0}
        return {pick[0]: 0.5, pick[1]: 0.5}
    else:  # continuous min-var: cov VALUES set weights
        cov = daily.loc[:cov_d].tail(lookback)[positive].cov() * 252
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


def build_cov_date_map(sigs_all, lag):
    """For each sig_d in sigs_all, cov_d = sigs_all[idx-lag] (clamped to first).
    Guarantees cov_d <= sig_d (strictly trailing). lag=0 -> identity."""
    m = {}
    for i, sd in enumerate(sigs_all):
        j = max(0, i - lag)
        m[sd] = sigs_all[j]
    return m


def returns_for(close, daily, intraday, overnight, start, end, P, cost_bps, cov_map):
    wf = lambda sd: cpm_wf_lag(close, daily, sd, P, cov_map.get(sd, sd))
    s, _ = H._segment_returns_conv(close, daily, wf, start, end, CONV,
                                   cost_bps, intraday, overnight)
    return s


def met(daily, cash):
    m = perf_metrics(daily, cash)
    return {"sharpe": round(float(m.get("sharpe")), 4),
            "cagr": round(float(m.get("cagr")), 4),
            "maxdd": round(float(m.get("max_drawdown")), 4),
            "calmar": round(float(m.get("calmar")), 4),
            "vol": round(float(m.get("vol")), 4)}


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
    lags = [0, 1, 2, 3]

    # cov-date maps keyed off the FULL ext sig list so lag is well-defined
    sigs_ext = sig_dates(close, ext_start, end)
    cov_maps = {lag: build_cov_date_map(sigs_ext, lag) for lag in lags}

    out = {"meta": {"conv": CONV, "lookback": CORR_LOOKBACK_DAYS,
                    "cost_bps": COST_BPS_PER_SIDE,
                    "clean_start": str(clean_start.date()), "ext_start": str(ext_start.date()),
                    "end": str(end.date()), "lags": lags},
           "results": {}}

    # full-ext return series per (scheme, lag), sliced to windows. 10 bps.
    print("Computing return series per (scheme, lag) at 10 bps...")
    ret_cache = {}
    for P in (1, 0):
        for lag in lags:
            ret_cache[(P, lag)] = returns_for(close, daily, intraday, overnight,
                                              ext_start, end, P, COST_BPS_PER_SIDE,
                                              cov_maps[lag])
        print(f"  scheme P={P} done")

    for wn, (ws_, we_) in windows.items():
        wd = {}
        for lag in lags:
            row = {}
            for P, label in [(1, "pair_5050"), (0, "continuous_minvar")]:
                s = ret_cache[(P, lag)]
                sw = s.loc[(s.index >= ws_) & (s.index <= we_)]
                row[label] = met(sw, cash)
            # edge = continuous - pair
            c, p = row["continuous_minvar"], row["pair_5050"]
            row["edge_cont_minus_pair"] = {
                "d_sharpe": round(c["sharpe"] - p["sharpe"], 4),
                "d_maxdd_pp": round((c["maxdd"] - p["maxdd"]) * 100, 2),
                "d_calmar": round(c["calmar"] - p["calmar"], 4),
            }
            wd[f"lag{lag}"] = row
        out["results"][wn] = wd

    Path(__file__).with_suffix(".json").write_text(json.dumps(out, indent=2, default=float))

    # ---- console: verify anchors (lag0) + edge table ----
    print("\n=== ANCHOR VERIFY (CLEAN, lag0, 10 bps) ===")
    a = out["results"]["CLEAN"]["lag0"]
    print(f"  pair_5050        : sharpe={a['pair_5050']['sharpe']:.4f} "
          f"calmar={a['pair_5050']['calmar']:.4f} maxdd={a['pair_5050']['maxdd']*100:.2f}%"
          f"  (expect 1.2424/0.8704/-16.35%)")
    print(f"  continuous_minvar: sharpe={a['continuous_minvar']['sharpe']:.4f} "
          f"calmar={a['continuous_minvar']['calmar']:.4f} maxdd={a['continuous_minvar']['maxdd']*100:.2f}%"
          f"  (expect 1.2935/0.9618/-15.15%)")

    for wn in ("CLEAN", "EXT"):
        print(f"\n=== {wn}: edge (continuous - pair) vs cov lag ===")
        print("  lag  pair_Sh  cont_Sh  dSh    pair_DD%  cont_DD%  dDD_pp  dCalmar")
        for lag in lags:
            r = out["results"][wn][f"lag{lag}"]
            p, c, e = r["pair_5050"], r["continuous_minvar"], r["edge_cont_minus_pair"]
            print(f"  {lag}   {p['sharpe']:.4f}  {c['sharpe']:.4f}  {e['d_sharpe']:+.4f}  "
                  f"{p['maxdd']*100:7.2f}  {c['maxdd']*100:7.2f}  {e['d_maxdd_pp']:+6.2f}  {e['d_calmar']:+.4f}")
    print("\nDONE -> json written")
    return out


if __name__ == "__main__":
    main()
