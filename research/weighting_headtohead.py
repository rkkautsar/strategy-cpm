"""Throwaway research: WEIGHTING method head-to-head for the CPM sleeve top-K=4.

Question: is a full quadratic min-variance solver (CONTINUOUS min-var, SLSQP)
needed for CPM weighting, or does a simpler scheme match/beat it -- especially
on the DD-aware objective (Calmar / MaxDD)?

Selection is IDENTICAL across all schemes (U=R=C=1, K=4 top-half, cov 504d,
mooex T+1 MOO exact, 10 bps/side). Only the WEIGHTING of the top-K=4
trend-qualified (positive-Faber) candidates changes:

  CONT  : continuous min-variance, FULL covariance (SLSQP quadratic). Optimizer.
  IV4   : inverse-vol (w_i prop 1/sigma_i; diagonal only, NO correlations).
          == naive risk parity. Reuses inverse_vol_weighting IV4 (== weight all
          positive top-K by 1/sigma).
  ERC   : equal-risk-contribution risk parity, FULL covariance (each asset
          contributes equal risk). More robust than min-var, needs cov.
  EW4   : equal-weight 1/N over the top-K positives (reference).

CONT and IV4 are delegated to inverse_vol_weighting.cpm_wf for EXACT
reproduction of the prior anchors (CONT clean 1.2935/-15.15%/0.9618 ;
IV4 = INVVOL-4 clean 1.1491/0.1344.../-12.665%/1.0614 @10bps).

ERC and EW4 replicate the IDENTICAL selection block then swap the weighting.

Computes per scheme x window (CLEAN 18y 2008-05-30.., EXT 27y 1999-03-10..):
  - net (10 bps) and gross (0 bps) Sharpe/CAGR/Vol/MaxDD/Calmar.
  - estimation sensitivity: cov lookback 504 -> 480/528, mean/max L1 weight drift.
  - which schemes need the FULL covariance vs only vols.

No production files touched. Writes findings md + json next to this file.
"""
import sys, math, json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.optimize import minimize

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

from cpm_live import (
    load_panel, perf_metrics, sig_13612U, best_safe, faber_sma_xs,
    COST_BPS_PER_SIDE, CORR_LOOKBACK_DAYS,
)
import exec_lag_moo_validation_2026_05_30 as H
from sleeve_vs_benchmark_2026_05_30 import stitch_bil, stitch_agg
import inverse_vol_weighting as IVW

CONV = "mooex"
CPM_PROD_UNIVERSE = IVW.CPM_PROD_UNIVERSE
CPM_SAFE = IVW.CPM_SAFE


# ---------- ERC (equal risk contribution) over a covariance ----------
def erc_weights(cov_values, x0=None):
    """Equal-risk-contribution weights via SLSQP minimizing pairwise squared
    risk-contribution differences. cov_values: (n,n) annualized cov array.
    Long-only, fully invested. Falls back to inverse-vol on failure."""
    n = cov_values.shape[0]
    sig = np.sqrt(np.clip(np.diag(cov_values), 1e-18, None))
    iv = (1.0 / sig)
    iv = iv / iv.sum()
    if x0 is None:
        x0 = iv

    def obj(w):
        rc = w * (cov_values @ w)          # risk contributions
        d = rc[:, None] - rc[None, :]
        return float((d * d).sum())

    cons = ({"type": "eq", "fun": lambda w: np.sum(w) - 1.0},)
    bnds = tuple((1e-9, 1.0) for _ in range(n))
    r = minimize(obj, x0, method="SLSQP", bounds=bnds, constraints=cons,
                 options={"maxiter": 1000, "ftol": 1e-14})
    if not r.success:
        return iv
    w = np.clip(r.x, 0.0, None)
    s = w.sum()
    return w / s if s > 0 else iv


def _selection(close, daily, sig_d, lookback):
    """Reproduce the IDENTICAL CPM selection (U=R=C=1, K=4 top-half). Returns
    (positive, safe) where positive is the list of trend-qualified top-K tickers.
    Mirrors inverse_vol_weighting.cpm_wf selection block exactly."""
    universe = CPM_PROD_UNIVERSE
    monthly = close.loc[:sig_d].resample("ME").last()
    safe = best_safe(monthly, sig_d, CPM_SAFE)

    cscores = [sig_13612U(monthly[a]) for a in ["HYG", "TIP"] if a in monthly.columns]
    cscores = [s for s in cscores if pd.notna(s)]
    if not cscores or sum(1 for s in cscores if s > 0) == 0:
        return None, safe

    top_half = max(2, math.ceil(len(universe) / 2))
    present = [t for t in universe if t in monthly.columns]
    faber = faber_sma_xs(monthly)
    avail = [t for t in present if t in faber.index and pd.notna(faber[t])
             and (sig_d in close.index and pd.notna(close.loc[sig_d].get(t, np.nan)))]
    if not avail:
        return None, safe
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
    return positive, safe


def cpm_wf(close, daily, sig_d, scheme, lookback):
    """scheme in {CONT, IV4, ERC, EW4}. CONT/IV4 delegate to IVW for exact
    reproduction; ERC/EW4 use identical selection then swap weighting."""
    if scheme in ("CONT", "IV4"):
        return IVW.cpm_wf(close, daily, sig_d, scheme, lookback)

    positive, safe = _selection(close, daily, sig_d, lookback)
    if positive is None or len(positive) == 0:
        return {safe: 1.0}
    if len(positive) == 1:
        return {positive[0]: 0.5, safe: 0.5}

    cov = daily.loc[:sig_d].tail(lookback)[positive].cov() * 252
    if cov.isna().any().any():
        n = len(positive)
        return {t: 1.0 / n for t in positive}

    if scheme == "EW4":
        n = len(positive)
        return {t: 1.0 / n for t in positive}
    if scheme == "ERC":
        w = erc_weights(cov.values)
        return {positive[i]: float(w[i]) for i in range(len(positive))}
    raise ValueError(scheme)


# ---------- reuse IVW helpers (selection-agnostic) ----------
sig_dates = IVW.sig_dates
l1 = IVW.l1


def weight_series(close, daily, sigs, scheme, lookback=CORR_LOOKBACK_DAYS):
    return [(sd, cpm_wf(close, daily, sd, scheme, lookback)) for sd in sigs]


def returns_for(close, daily, intraday, overnight, start, end, scheme, cost_bps):
    wf = lambda sd: cpm_wf(close, daily, sd, scheme, CORR_LOOKBACK_DAYS)
    s, _ = H._segment_returns_conv(close, daily, wf, start, end, CONV,
                                   cost_bps, intraday, overnight)
    return s


def met(daily, cash):
    m = perf_metrics(daily, cash)
    return {"sharpe": m.get("sharpe"), "cagr": m.get("cagr"),
            "maxdd": m.get("max_drawdown"), "calmar": m.get("calmar"), "vol": m.get("vol")}


def concentration(w):
    vals = [v for v in w.values() if v > 1e-9]
    hhi = sum(v * v for v in vals)
    return (max(vals) if vals else 0.0), (1.0 / hhi if hhi > 0 else float("nan"))


SCHEMES = [("CONT", "continuous min-var (full cov)"),
           ("IV4", "inverse-vol top-4 (vols only)"),
           ("ERC", "ERC risk-parity (full cov)"),
           ("EW4", "1/N top-4 (reference)")]
NEEDS_FULL_COV = {"CONT": True, "IV4": False, "ERC": True, "EW4": False}


# ---------- paired block bootstrap (reuse PBC primitives) ----------
import paired_bootstrap_pair_vs_continuous as PBC
B, BLOCK, SEED = PBC.B, PBC.BLOCK, PBC.SEED


def paired_boot(a_r, b_r, n_years):
    """P(b beats a) and diff CIs for sharpe / maxdd / calmar via PAIRED block
    bootstrap (same block index both series). Returns (b - a) diff stats:
    sharpe>0 => b higher Sharpe; maxdd>0 => b shallower DD; calmar>0 => b higher."""
    n = len(a_r)
    rng = np.random.default_rng(SEED)
    ds, dm, dc = [], [], []
    for _ in range(B):
        idx = PBC.block_index(n, BLOCK, rng)
        as_, am, ac = PBC.metrics_from_array(a_r[idx], n_years)
        bs, bm, bc = PBC.metrics_from_array(b_r[idx], n_years)
        ds.append(bs - as_); dm.append(bm - am); dc.append(bc - ac)

    def summ(arr):
        x = np.asarray(arr)
        lo, hi = np.percentile(x, 2.5), np.percentile(x, 97.5)
        return {"p_b_wins": float(np.mean(x > 0)), "mean": float(x.mean()),
                "ci_lo": float(lo), "ci_hi": float(hi),
                "excludes_zero": bool(lo > 0 or hi < 0)}
    return {"sharpe": summ(ds), "maxdd": summ(dm), "calmar": summ(dc)}


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

    out = {"meta": {"conv": CONV, "lookback": CORR_LOOKBACK_DAYS,
                    "cost_bps_prod": COST_BPS_PER_SIDE, "K_top_half": 4,
                    "B": B, "block": BLOCK, "seed": SEED,
                    "clean_start": str(clean_start.date()),
                    "ext_start": str(ext_start.date()), "end": str(end.date())},
           "needs_full_cov": NEEDS_FULL_COV, "windows": {}}

    print("Computing return series (ext, all schemes, 0 & 10 bps)...")
    ret_cache = {}
    for scheme, _ in SCHEMES:
        for cb in (0, 10):
            ret_cache[(scheme, cb)] = returns_for(close, daily, intraday, overnight,
                                                  ext_start, end, scheme, cb)
        print(f"  scheme {scheme} done")

    # ---- metrics tables + concentration ----
    for wn, (ws_, we_) in windows.items():
        n_years = (we_ - ws_).days / 365.25
        sigs = sig_dates(close, ws_, we_)
        wd = {"n_years": round(n_years, 4), "schemes": {}}
        for scheme, label in SCHEMES:
            ws = [w for _, w in weight_series(close, daily, sigs, scheme)]
            conc = [concentration(w) for w in ws]
            perf = {}
            for cb in (0, 10):
                s = ret_cache[(scheme, cb)]
                sw = s.loc[(s.index >= ws_) & (s.index <= we_)]
                perf[cb] = met(sw, cash)
            wd["schemes"][scheme] = {
                "label": label, "needs_full_cov": NEEDS_FULL_COV[scheme],
                "gross_0bps": perf[0], "net_10bps": perf[10],
                "avg_max_weight": float(np.mean([c[0] for c in conc])),
                "avg_eff_n": float(np.mean([c[1] for c in conc])),
            }
        out["windows"][wn] = wd

    # ---- paired bootstrap: CONT vs IV4 and CONT vs ERC (a=CONT baseline) ----
    print("Paired block bootstrap (CONT vs IV4, CONT vs ERC)...")
    boot = {}
    for wn, (ws_, we_) in windows.items():
        cont = ret_cache[("CONT", 10)]
        iv4 = ret_cache[("IV4", 10)]
        erc = ret_cache[("ERC", 10)]
        sl = lambda s: s.loc[(s.index >= ws_) & (s.index <= we_)]
        c, i, e = sl(cont), sl(iv4), sl(erc)
        common = c.index.intersection(i.index).intersection(e.index)
        c, i, e = c.reindex(common), i.reindex(common), e.reindex(common)
        n_years = (common[-1] - common[0]).days / 365.25
        # diff = (continuous - alt) so positive => continuous wins
        boot[wn] = {
            "n_days": len(common), "n_years": n_years,
            "cont_vs_iv4": _flip(paired_boot(i.values, c.values, n_years)),
            "cont_vs_erc": _flip(paired_boot(e.values, c.values, n_years)),
            "corr_cont_iv4": float(np.corrcoef(c.values, i.values)[0, 1]),
            "corr_cont_erc": float(np.corrcoef(c.values, e.values)[0, 1]),
        }
    out["paired_bootstrap"] = boot

    # ---- estimation sensitivity: lookback 504 -> 480/528 (ext sigs) ----
    print("Estimation sensitivity (cov lookback perturbation)...")
    sens = {}
    sigs_ext = sig_dates(close, ext_start, end)
    for scheme, label in SCHEMES:
        base = {sd: w for sd, w in weight_series(close, daily, sigs_ext, scheme, 504)}
        moves = {}
        for lb in (480, 528):
            pert = {sd: w for sd, w in weight_series(close, daily, sigs_ext, scheme, lb)}
            ds = [l1(base[sd], pert[sd]) for sd in sigs_ext]
            moves[lb] = {"mean_l1": float(np.mean(ds)), "max_l1": float(np.max(ds))}
        avg_mean = float(np.mean([moves[lb]["mean_l1"] for lb in (480, 528)]))
        sens[scheme] = {"label": label, "needs_full_cov": NEEDS_FULL_COV[scheme],
                        "480": moves[480], "528": moves[528], "avg_mean_l1": avg_mean}
    out["estimation_sensitivity"] = sens

    (HERE / "weighting_headtohead.json").write_text(json.dumps(out, indent=2, default=float))

    # ---- console verify ----
    print("\n=== VERIFY anchors (CLEAN, 10 bps) ===")
    c = out["windows"]["CLEAN"]["schemes"]["CONT"]["net_10bps"]
    iv = out["windows"]["CLEAN"]["schemes"]["IV4"]["net_10bps"]
    print(f"  CONT : sharpe={c['sharpe']:.4f} maxdd={c['maxdd']*100:.2f}% calmar={c['calmar']:.4f}"
          f"   (expect 1.2935/-15.15%/0.9618)")
    print(f"  IV4  : sharpe={iv['sharpe']:.4f} maxdd={iv['maxdd']*100:.2f}% calmar={iv['calmar']:.4f}"
          f"   (expect 1.1491/-12.67%/1.0614)")
    print("\n=== HEAD-TO-HEAD (net 10 bps) ===")
    for wn in ("CLEAN", "EXT"):
        print(f"\n[{wn}]  scheme                          Sharpe   CAGR    Vol     MaxDD    Calmar")
        for scheme, label in SCHEMES:
            p = out["windows"][wn]["schemes"][scheme]["net_10bps"]
            print(f"  {label:<30} {p['sharpe']:.4f}  {p['cagr']*100:5.2f}%  "
                  f"{p['vol']*100:5.2f}%  {p['maxdd']*100:6.2f}%  {p['calmar']:.4f}")
    print("\nDONE -> json written")
    return out


def _flip(d):
    """Input diffs are (continuous - alt). Relabel p_b_wins -> p_cont_wins."""
    out = {}
    for k, v in d.items():
        out[k] = {"p_cont_wins": v["p_b_wins"], "mean_cont_minus_alt": v["mean"],
                  "ci_lo": v["ci_lo"], "ci_hi": v["ci_hi"],
                  "excludes_zero": v["excludes_zero"]}
    return out


if __name__ == "__main__":
    main()
