"""Throwaway research: two-axis sensitivity sweep of the CPM (Cross-asset Parity
Momentum) weighting flavor and subset-selection objective.

Production design held fixed (U=R=C=1, K=4 top-half positive-trend pool, canary,
safe fallback, cov lookback 504d, mooex T+1 MOO exact, 10 bps/side, select 3):
  PRODUCTION = min-variance 3-subset selection + inverse-vol weighting (INVVOL-3).

AXIS A -- WEIGHTING FLAVOR (selection FIXED = min-var 3-subset of top-4):
  INVVOL : production naive risk parity (w_i prop 1/sigma_i, diagonal only).
  ERC    : true equal-risk-contribution risk parity (full cov, SLSQP solver).
  EW     : 1/3 equal-weight reference.
  -> paired bootstrap INVVOL vs ERC (B=2000, block=21, seed=42).
  -> ERC weight-concentration / blow-up diagnostics on the vol-asymmetric menu.

AXIS B -- SUBSET SELECTION OBJECTIVE (weighting FIXED = inverse-vol; pick 3 of top-4):
  RISK-based (use only risk estimate -> robust):
    MINVAR : min equal-weight portfolio variance w'Sigma w  (PRODUCTION).
    MINVOL : 3 lowest individual-volatility assets (ignore correlation).
    MINCORR: 3-subset with lowest average pairwise correlation (diversification).
  PERFORMANCE-based (use trailing realized perf -> overfit / lookahead-prone):
    MAXSHARPE : 3-subset with highest trailing Sharpe over the cov window.
    MAXCALMAR : highest trailing Calmar over the cov window.
    MINDD     : shallowest trailing MaxDD over the cov window.
  -> for any performance-based selector that wins IN-SAMPLE, paired bootstrap
     vs MINVAR and flag as overfit-prone.

Selection blocks are byte-identical to production (delegated to
inverse_vol_weighting / weighting_headtohead selection); only the named step
changes. No production files touched. Writes md + json next to this file.

Verify: PRODUCTION (MINVAR select + inverse-vol) reproduces the CPM-solo anchor
  CLEAN 1.2453/-13.19%/1.0824 ; EXT 1.2249/-15.18%/0.9148  before trusting variants.
"""
import sys, math, json
from itertools import combinations
from pathlib import Path
import numpy as np
import pandas as pd

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
from weighting_headtohead import _selection, erc_weights
import paired_bootstrap_pair_vs_continuous as PBC

CONV = "mooex"
CPM_PROD_UNIVERSE = IVW.CPM_PROD_UNIVERSE
CPM_SAFE = IVW.CPM_SAFE
B, BLOCK, SEED = PBC.B, PBC.BLOCK, PBC.SEED
M = 3  # target cardinality (select 3 of top-4)


# ---------------------------------------------------------------------------
# Selection objectives over the cov window. All use ONLY data <= sig_d (no
# lookahead); performance-based ones use trailing REALIZED perf so they are
# overfit-prone OOS. rets/cov window matches IVW._cov_window exactly.
# ---------------------------------------------------------------------------
def _window_rets(close, candidates, lookback):
    """Cov window mirroring IVW.min_var_subset guards EXACTLY: drop all-NaN rows,
    require >=lookback rows, reject only if the (NaN-tolerant pairwise) cov has
    NaN. Newer-ETF column NaNs are kept (pandas .cov() uses pairwise complete
    obs) so selection matches production byte-for-byte."""
    rets = close[candidates].pct_change().dropna(how="all").tail(lookback)
    if len(rets) < lookback:
        return None
    return rets


def _ew_curve_metrics(rets_sub):
    """Equal-weight subset daily returns -> (sharpe, calmar, maxdd) trailing.
    Annualization constants are monotone so fine for ranking."""
    r = rets_sub.dropna().mean(axis=1).values
    vol = r.std(ddof=0)
    sharpe = r.mean() / vol if vol > 0 else -np.inf
    eq = np.cumprod(1.0 + r)
    rm = np.maximum.accumulate(eq)
    mdd = float((eq / rm - 1.0).min())
    # trailing CAGR proxy: geometric mean per-bar; calmar = mean / |mdd|
    calmar = (r.mean()) / abs(mdd) if mdd < 0 else np.inf
    return sharpe, calmar, mdd


def select_subset(close, candidates, lookback, m, objective):
    """Return the chosen m-subset of `candidates` under `objective`.
    Objectives: MINVAR, MINVOL, MINCORR (risk); MAXSHARPE, MAXCALMAR, MINDD (perf).
    Falls back to all candidates if window degenerate or fewer than m."""
    cand = list(candidates)
    if len(cand) <= m:
        return cand
    rets = _window_rets(close, cand, lookback)
    if rets is None:
        # mirror IVW: min_var_subset returns None -> caller weights all
        return cand
    cov = rets.cov()
    if cov.isna().any().any():
        return cand
    sigma = pd.Series(np.sqrt(np.diag(cov.values)), index=cov.index)

    if objective == "MINVOL":
        return list(sigma.sort_values().index[:m])

    if objective == "MINVAR":
        w = 1.0 / m
        best, best_v = None, np.inf
        for combo in combinations(cand, m):
            sub = cov.loc[list(combo), list(combo)].values
            v = float(w * w * sub.sum())
            if v < best_v:
                best_v, best = v, combo
        return list(best)

    if objective == "MINCORR":
        corr = rets.corr()
        best, best_c = None, np.inf
        for combo in combinations(cand, m):
            cl = list(combo)
            sub = corr.loc[cl, cl].values
            iu = np.triu_indices(m, k=1)
            avg_c = float(sub[iu].mean())
            if avg_c < best_c:
                best_c, best = avg_c, combo
        return list(best)

    # performance-based
    best, best_score = None, -np.inf
    for combo in combinations(cand, m):
        cl = list(combo)
        sh, ca, md = _ew_curve_metrics(rets[cl])
        if objective == "MAXSHARPE":
            score = sh
        elif objective == "MAXCALMAR":
            score = ca
        elif objective == "MINDD":
            score = md  # md is negative; larger (closer to 0) = shallower
        else:
            raise ValueError(objective)
        if score > best_score:
            best_score, best = score, combo
    return list(best)


# ---------------------------------------------------------------------------
# Weight function. flavor in {INVVOL, ERC, EW}. selector is a selection objective.
# Selection block identical to production via _selection().
# ---------------------------------------------------------------------------
def cpm_wf(close, daily, sig_d, selector, flavor, lookback):
    positive, safe = _selection(close, daily, sig_d, lookback)
    if positive is None or len(positive) == 0:
        return {safe: 1.0}
    if len(positive) == 1:
        return {positive[0]: 0.5, safe: 0.5}

    csub = close.loc[:sig_d]
    n_pos = len(positive)
    m = min(M, n_pos)
    pick = select_subset(csub, positive, lookback, m, selector)

    if flavor == "INVVOL":
        return IVW.inv_vol_weights(csub, pick, lookback)
    if flavor == "EW":
        n = len(pick)
        return {t: 1.0 / n for t in pick}
    if flavor == "ERC":
        cov = daily.loc[:sig_d].tail(lookback)[pick].cov() * 252
        if cov.isna().any().any():
            return IVW.inv_vol_weights(csub, pick, lookback)
        w = erc_weights(cov.values)
        return {pick[i]: float(w[i]) for i in range(len(pick))}
    raise ValueError(flavor)


# ---------------------------------------------------------------------------
sig_dates = IVW.sig_dates
l1 = IVW.l1


def weight_series(close, daily, sigs, selector, flavor, lookback=CORR_LOOKBACK_DAYS):
    return [(sd, cpm_wf(close, daily, sd, selector, flavor, lookback)) for sd in sigs]


def returns_for(close, daily, intraday, overnight, start, end, selector, flavor, cost_bps):
    wf = lambda sd: cpm_wf(close, daily, sd, selector, flavor, CORR_LOOKBACK_DAYS)
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


def paired_boot(a_r, b_r, n_years):
    """(b - a) paired block bootstrap. positive sharpe/maxdd/calmar => b wins."""
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


# AXIS A: weighting flavor (selection fixed = MINVAR)
AXIS_A = [("MINVAR", "INVVOL", "INVVOL (production)"),
          ("MINVAR", "ERC", "ERC true risk-parity"),
          ("MINVAR", "EW", "1/3 equal-weight (ref)")]

# AXIS B: selection objective (weighting fixed = INVVOL)
AXIS_B = [("MINVAR", "INVVOL", "MINVAR (production)", "risk"),
          ("MINVOL", "INVVOL", "MINVOL 3-lowest-vol", "risk"),
          ("MINCORR", "INVVOL", "MINCORR diversification", "risk"),
          ("MAXSHARPE", "INVVOL", "MAXSHARPE trailing", "perf"),
          ("MAXCALMAR", "INVVOL", "MAXCALMAR trailing", "perf"),
          ("MINDD", "INVVOL", "MINDD trailing", "perf")]


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

    # unique (selector, flavor) configs
    configs = {}
    for sel, fl, lab in AXIS_A:
        configs[(sel, fl)] = lab
    for sel, fl, lab, _ in AXIS_B:
        configs.setdefault((sel, fl), lab)

    out = {"meta": {"conv": CONV, "lookback": CORR_LOOKBACK_DAYS,
                    "cost_bps_prod": COST_BPS_PER_SIDE, "K_top_half": 4, "M_target": M,
                    "B": B, "block": BLOCK, "seed": SEED,
                    "clean_start": str(clean_start.date()),
                    "ext_start": str(ext_start.date()), "end": str(end.date())},
           "configs": {}, "axis_a": {}, "axis_b": {}, "paired_bootstrap": {},
           "erc_diagnostics": {}}

    print("Computing return series (ext, all configs, 0 & 10 bps)...")
    ret_cache = {}
    for (sel, fl), lab in configs.items():
        for cb in (0, 10):
            ret_cache[(sel, fl, cb)] = returns_for(close, daily, intraday, overnight,
                                                   ext_start, end, sel, fl, cb)
        print(f"  config {sel}/{fl} done")

    # per-config metrics both windows + concentration
    for (sel, fl), lab in configs.items():
        entry = {"label": lab, "windows": {}}
        for wn, (ws_, we_) in windows.items():
            sigs = sig_dates(close, ws_, we_)
            ws = [w for _, w in weight_series(close, daily, sigs, sel, fl)]
            conc = [concentration(w) for w in ws]
            perf = {}
            for cb in (0, 10):
                s = ret_cache[(sel, fl, cb)]
                sw = s.loc[(s.index >= ws_) & (s.index <= we_)]
                perf[cb] = met(sw, cash)
            entry["windows"][wn] = {
                "net_10bps": perf[10], "gross_0bps": perf[0],
                "avg_max_weight": float(np.mean([c[0] for c in conc])),
                "avg_eff_n": float(np.mean([c[1] for c in conc])),
                "max_single_weight": float(max(c[0] for c in conc)),
            }
        out["configs"][f"{sel}/{fl}"] = entry

    out["axis_a"] = [{"selector": s, "flavor": f, "label": l,
                      "key": f"{s}/{f}"} for s, f, l in AXIS_A]
    out["axis_b"] = [{"selector": s, "flavor": f, "label": l, "kind": k,
                      "key": f"{s}/{f}"} for s, f, l, k in AXIS_B]

    # ---- AXIS A paired bootstrap: INVVOL (a) vs ERC (b) ----
    print("Paired bootstrap AXIS A (INVVOL vs ERC)...")
    for wn, (ws_, we_) in windows.items():
        a = ret_cache[("MINVAR", "INVVOL", 10)]
        b = ret_cache[("MINVAR", "ERC", 10)]
        sl = lambda s: s.loc[(s.index >= ws_) & (s.index <= we_)]
        a_, b_ = sl(a), sl(b)
        common = a_.index.intersection(b_.index)
        a_, b_ = a_.reindex(common), b_.reindex(common)
        ny = (common[-1] - common[0]).days / 365.25
        out["paired_bootstrap"][f"AXISA_invvol_vs_erc_{wn}"] = {
            "a": "INVVOL", "b": "ERC", "n_days": len(common), "n_years": ny,
            "diff_b_minus_a": paired_boot(a_.values, b_.values, ny),
            "corr": float(np.corrcoef(a_.values, b_.values)[0, 1]),
        }

    # ---- ERC concentration / blow-up diagnostics vs INVVOL on the menu ----
    print("ERC vs INVVOL concentration diagnostics...")
    sigs_ext = sig_dates(close, ext_start, end)
    erc_ws = weight_series(close, daily, sigs_ext, "MINVAR", "ERC")
    iv_ws = weight_series(close, daily, sigs_ext, "MINVAR", "INVVOL")
    def conc_summary(ws):
        risk_on = [w for _, w in ws if any(k not in CPM_SAFE for k in w)]
        maxw = [concentration(w)[0] for w in risk_on]
        effn = [concentration(w)[1] for w in risk_on]
        return {"n_risk_on": len(risk_on),
                "avg_max_weight": float(np.mean(maxw)), "max_max_weight": float(np.max(maxw)),
                "avg_eff_n": float(np.mean(effn)), "min_eff_n": float(np.min(effn))}
    out["erc_diagnostics"] = {"ERC": conc_summary(erc_ws), "INVVOL": conc_summary(iv_ws),
                              "mean_l1_erc_vs_invvol": float(np.mean(
                                  [l1(e[1], i[1]) for e, i in zip(erc_ws, iv_ws)]))}

    # ---- AXIS B paired bootstrap: each PERF selector (b) vs MINVAR (a) ----
    print("Paired bootstrap AXIS B (perf selectors vs MINVAR)...")
    for sel, fl, lab, kind in AXIS_B:
        if kind != "perf":
            continue
        for wn, (ws_, we_) in windows.items():
            a = ret_cache[("MINVAR", "INVVOL", 10)]
            b = ret_cache[(sel, fl, 10)]
            sl = lambda s: s.loc[(s.index >= ws_) & (s.index <= we_)]
            a_, b_ = sl(a), sl(b)
            common = a_.index.intersection(b_.index)
            a_, b_ = a_.reindex(common), b_.reindex(common)
            ny = (common[-1] - common[0]).days / 365.25
            out["paired_bootstrap"][f"AXISB_{sel}_vs_minvar_{wn}"] = {
                "a": "MINVAR", "b": sel, "n_days": len(common), "n_years": ny,
                "diff_b_minus_a": paired_boot(a_.values, b_.values, ny),
                "corr": float(np.corrcoef(a_.values, b_.values)[0, 1]),
            }

    (HERE / "cpm_weighting_selection_sensitivity.json").write_text(
        json.dumps(out, indent=2, default=float))

    # ---- console verify production anchor ----
    prod_c = out["configs"]["MINVAR/INVVOL"]["windows"]["CLEAN"]["net_10bps"]
    prod_e = out["configs"]["MINVAR/INVVOL"]["windows"]["EXT"]["net_10bps"]
    print("\n=== VERIFY production anchor (MINVAR + INVVOL, net 10 bps) ===")
    print(f"  CLEAN: sharpe={prod_c['sharpe']:.4f} maxdd={prod_c['maxdd']*100:.2f}% "
          f"calmar={prod_c['calmar']:.4f}   (expect 1.2453/-13.19%/1.0824)")
    print(f"  EXT  : sharpe={prod_e['sharpe']:.4f} maxdd={prod_e['maxdd']*100:.2f}% "
          f"calmar={prod_e['calmar']:.4f}   (expect 1.2249/-15.18%/0.9148)")

    print("\n=== AXIS A: WEIGHTING FLAVOR (selection=MINVAR 3-subset, net 10 bps) ===")
    for wn in ("CLEAN", "EXT"):
        print(f"\n[{wn}]  flavor                      Sharpe   CAGR    Vol     MaxDD    Calmar  maxW")
        for s, f, lab in AXIS_A:
            p = out["configs"][f"{s}/{f}"]["windows"][wn]["net_10bps"]
            mw = out["configs"][f"{s}/{f}"]["windows"][wn]["avg_max_weight"]
            print(f"  {lab:<26} {p['sharpe']:.4f}  {p['cagr']*100:5.2f}%  "
                  f"{p['vol']*100:5.2f}%  {p['maxdd']*100:6.2f}%  {p['calmar']:.4f}  {mw:.3f}")

    print("\n=== AXIS B: SELECTION OBJECTIVE (weighting=INVVOL, net 10 bps) ===")
    for wn in ("CLEAN", "EXT"):
        print(f"\n[{wn}]  selector                    kind  Sharpe   CAGR    Vol     MaxDD    Calmar")
        for s, f, lab, k in AXIS_B:
            p = out["configs"][f"{s}/{f}"]["windows"][wn]["net_10bps"]
            print(f"  {lab:<26} {k:<5} {p['sharpe']:.4f}  {p['cagr']*100:5.2f}%  "
                  f"{p['vol']*100:5.2f}%  {p['maxdd']*100:6.2f}%  {p['calmar']:.4f}")

    print("\n=== ERC diagnostics (risk-on rebalances, EXT) ===")
    for k in ("INVVOL", "ERC"):
        d = out["erc_diagnostics"][k]
        print(f"  {k}: avg_maxW={d['avg_max_weight']:.3f} max_maxW={d['max_max_weight']:.3f} "
              f"avg_effN={d['avg_eff_n']:.2f} min_effN={d['min_eff_n']:.2f}")
    print(f"  mean L1(ERC,INVVOL) = {out['erc_diagnostics']['mean_l1_erc_vs_invvol']:.4f}")

    print("\nDONE -> json written")
    return out


if __name__ == "__main__":
    main()
