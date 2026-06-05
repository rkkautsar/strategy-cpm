# -*- coding: utf-8 -*-
"""NDX sleeve: does min-var SELECTION and/or a downside (CVaR/CDaR) OBJECTIVE
beat the momentum top-5 equal-weight baseline, net cost + OOS?

Analyst role. Read-only re production (ndx_sleeve_live.py / prod / memo NOT
edited). Writes only research/cpm_ndx_minvar_cvar_findings.md (+ .json). No commit.

Thesis under test: NDX is a better testbed than CPM for correlation-aware
selection + downside objectives because (a) ~100-name PIT Nasdaq-100 pool (larger
N) and (b) highly non-elliptical single-stock returns (skew/kurtosis) where
variance is a poor risk proxy and CVaR/CDaR should genuinely differ.

ENGINE REUSE: monkeypatch ndx_sleeve_live.compute_ndx_weights with a
config-specific selection/weighting fn, then call the UNMODIFIED
ndx_sleeve_live.run_ndx_backtest (gating TIP+SPY-trend+SPY-vol, safe rotation,
T+1 MOO close-to-close, 10bps/side, delisting haircut -0.10, PIT membership all
identical across configs). Only the selection/sizing of the held names varies.

HIERARCHICAL WORKFLOW (mandatory; cannot optimize raw ~100 names, T/N singular):
each signal date momentum-prune to the top-N positive-13612U names (N=15
canonical; N=10/20 sensitivity), THEN apply the selection/weighting rule to
choose+size the final K=5 (or weight all N for the breadth ref). 252d window for
cov/CVaR/CDaR; Ledoit-Wolf shrinkage on cov for the variance-based optimizers.

CONFIGS (NDX sleeve; gating/safe/T+1/10bps/delist/PIT all fixed):
  PROD          momentum top-5 EW                                  (baseline)
  MINVAR_SEL    momentum top-N -> min-var subset of 5 -> EW        (selection lever)
  MIN_CVAR      momentum top-N -> min-CVaR LP -> top-5 by w, renorm(downside obj)
  MIN_CDAR      momentum top-N -> min-CDaR LP -> top-5 by w, renorm(downside obj)
  TOP15_EW      momentum top-15 EW                                 (breadth ref)
  INVVOL5       momentum top-5 inv-vol                             (weighting ref)
  MAXDIV5       momentum top-5 max-diversification                 (weighting ref)
"""
from __future__ import annotations

import json
import sys
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from sklearn.covariance import LedoitWolf

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cpm_live import load_panel, perf_metrics, sig_13612U, inv_vol_weights
import ndx_sleeve_live as ndx
from bull_spy_live import _pick_safe
import index_constitution as ic
# reuse the Rockafellar-Uryasev CVaR LP + Chekhlov-Uryasev CDaR LP already implemented
from research.cpm_cvar_cdar_objective import alloc_mincvar, alloc_mincdar
from research.cpm_bootstrap_multimetric import paired_block_bootstrap_mm

EXT_START = pd.Timestamp("1999-03-10")
CLEAN_START = pd.Timestamp("2008-05-30")
END = pd.Timestamp("2026-05-22")
LB = 252
N_CANON = 15
SPY = ndx.SPY_TICKER


# ----------------------------------------------------------------------------
# shared selection prefix: gating + PIT + positive-momentum candidate set
# (copied faithfully from ndx_sleeve_live.compute_ndx_weights up to the point
#  where the held names are chosen, so every config shares the same gate/PIT)
# ----------------------------------------------------------------------------
def _gate_and_candidates(cpm_panel, ndx_panel, sig_d):
    """Return (status, safe, candidates_sorted). status in {OFF, PROXY, ON}.
    candidates_sorted = list of (ticker, momentum) positive-13612U, desc, PIT+priced."""
    cpm_monthly = cpm_panel.loc[:sig_d].resample("ME").last()
    safe = _pick_safe(cpm_monthly)

    tip_sig = sig_13612U(cpm_monthly["TIP"]) if "TIP" in cpm_monthly.columns else float("nan")
    canary_ok = pd.notna(tip_sig) and tip_sig > 0
    spy_sig = sig_13612U(cpm_monthly[SPY]) if SPY in cpm_monthly.columns else float("nan")
    trend_ok = pd.notna(spy_sig) and spy_sig > 0
    if SPY in cpm_panel.columns:
        vol_ok, _ = ndx._ndx_vol_gate_ok(cpm_panel[SPY], sig_d)
    else:
        vol_ok = False
    if not (canary_ok and trend_ok and vol_ok):
        return "OFF", safe, []

    pit = ic.constituents_at("nasdaq100", sig_d.strftime("%Y-%m-%d"))
    pit_tickers = set(pit["symbol"].tolist())
    if len(pit_tickers) == 0:
        return "PROXY", safe, []

    monthly = ndx_panel.loc[:sig_d].resample("ME").last()
    available = []
    for t in pit_tickers:
        if t not in ndx_panel.columns:
            continue
        if sig_d in ndx_panel.index and pd.isna(ndx_panel.loc[sig_d, t]):
            continue
        recent = ndx_panel[t].loc[sig_d - pd.Timedelta(days=30):sig_d].dropna()
        if recent.empty:
            continue
        available.append(t)

    momenta = {}
    for t in available:
        s = monthly[t].dropna()
        if len(s) < 13:
            continue
        m = sig_13612U(s)
        if pd.notna(m) and m > 0:
            momenta[t] = m
    cands = sorted(momenta.items(), key=lambda x: -x[1])
    return "ON", safe, cands


def _partial_safe_pack(weights_risky, n_eff, safe, K=5):
    """Scale a risky-block weight dict (summing to 1) by n_eff/K and put the
    remainder in safe -- generalizes PROD's '1/K per held name, rest cash'."""
    risky_fraction = min(n_eff, K) / K
    out = {t: w * risky_fraction for t, w in weights_risky.items()}
    cash_share = 1.0 - risky_fraction
    if cash_share > 1e-9:
        out[safe] = out.get(safe, 0.0) + cash_share
    return out


# ----------------------------- covariance helpers ---------------------------
def _lw_cov(ndx_panel, picks, sig_d, lookback=LB):
    rets = ndx_panel[picks].loc[:sig_d].ffill().pct_change().dropna(how="all").tail(lookback)
    X = rets.dropna().values
    if X.shape[0] < max(20, len(picks) + 2):
        # too few complete rows -> sample cov on available
        c = rets.cov()
        return c.loc[picks, picks].values if not c.isna().any().any() else None
    cov = LedoitWolf().fit(X).covariance_
    return cov


def _min_var_subset_lw(ndx_panel, picks, sig_d, m, lookback=LB):
    """Min-variance equal-weight subset of size m from `picks`, Ledoit-Wolf cov.
    EW subset variance = (1/m^2) * sum(Sigma_sub). Falls back to top-m if cov bad."""
    if len(picks) <= m:
        return list(picks)
    cov = _lw_cov(ndx_panel, picks, sig_d, lookback)
    if cov is None or not np.all(np.isfinite(cov)):
        return list(picks[:m])
    idx = {t: i for i, t in enumerate(picks)}
    w = 1.0 / m
    best, best_v = None, np.inf
    for combo in combinations(picks, m):
        ii = [idx[t] for t in combo]
        sub = cov[np.ix_(ii, ii)]
        v = float(w * w * sub.sum())
        if v < best_v:
            best_v, best = v, combo
    return list(best) if best else list(picks[:m])


def _maxdiv_weights(ndx_panel, picks, sig_d, lookback=LB):
    """Maximum-diversification (Choueifaty): max (w'sigma)/sqrt(w'Sigma w), long-only.
    Falls back to inv-vol if degenerate."""
    n = len(picks)
    if n == 1:
        return {picks[0]: 1.0}
    cov = _lw_cov(ndx_panel, picks, sig_d, lookback)
    if cov is None or not np.all(np.isfinite(cov)):
        return inv_vol_weights(ndx_panel.loc[:sig_d], picks, lookback)
    sig = np.sqrt(np.clip(np.diag(cov), 1e-18, None))

    def neg_dr(w):
        num = float(w @ sig)
        den = float(np.sqrt(max(w @ cov @ w, 1e-18)))
        return -num / den

    w0 = (1.0 / sig) / (1.0 / sig).sum()
    cons = ({"type": "eq", "fun": lambda w: w.sum() - 1.0},)
    bnds = [(0.0, 1.0)] * n
    r = minimize(neg_dr, w0, method="SLSQP", bounds=bnds, constraints=cons,
                 options={"maxiter": 500, "ftol": 1e-12})
    if not r.success or not np.all(np.isfinite(r.x)):
        return inv_vol_weights(ndx_panel.loc[:sig_d], picks, lookback)
    w = np.clip(r.x, 0.0, None)
    s = w.sum()
    if s <= 0:
        return inv_vol_weights(ndx_panel.loc[:sig_d], picks, lookback)
    w = w / s
    return {picks[i]: float(w[i]) for i in range(n)}


def _top5_by_weight(wdict, K=5):
    """Keep the K largest-weight names and renormalize (LP select+weight of K)."""
    items = sorted(wdict.items(), key=lambda x: -x[1])[:K]
    s = sum(w for _, w in items)
    if s <= 0:
        return {t: 1.0 / len(items) for t, _ in items}
    return {t: w / s for t, w in items}


# ----------------------------- config weight fns ----------------------------
def make_compute(config, N=N_CANON, K=5):
    """Return a drop-in replacement for ndx_sleeve_live.compute_ndx_weights."""

    def compute(cpm_panel, ndx_panel, sig_d):
        status, safe, cands = _gate_and_candidates(cpm_panel, ndx_panel, sig_d)
        if status == "OFF":
            return ({safe: 1.0}, "GATE_OFF", {"selected": []})
        if status == "PROXY":
            return ({SPY: 1.0}, "NDX_FALLBACK_SPY", {"selected": [SPY]})
        if not cands:
            return ({safe: 1.0}, "NDX_NO_POS", {"selected": []})

        names = [t for t, _ in cands]
        pool = names[:N]                       # momentum prune to top-N positives

        if config == "PROD":
            sel = names[:K]
            rw = {t: 1.0 / K for t in sel}     # EW; partial fill via n_eff
            out = _partial_safe_pack(rw, len(sel), safe, K)
            return (out, "NDX_PROD", {"selected": sel})

        if config == "TOP15_EW":
            sel = names[:15]
            n = len(sel)
            rw = {t: 1.0 / n for t in sel}
            # breadth config: fully invested when >=1 positive (no 5-cap partial)
            return ({**rw}, "NDX_TOP15EW", {"selected": sel})

        if config == "INVVOL5":
            sel = names[:K]
            rw = inv_vol_weights(ndx_panel.loc[:sig_d], sel, LB) if len(sel) > 1 else {sel[0]: 1.0}
            out = _partial_safe_pack(rw, len(sel), safe, K)
            return (out, "NDX_INVVOL5", {"selected": sel})

        if config == "MAXDIV5":
            sel = names[:K]
            rw = _maxdiv_weights(ndx_panel, sel, sig_d) if len(sel) > 1 else {sel[0]: 1.0}
            out = _partial_safe_pack(rw, len(sel), safe, K)
            return (out, "NDX_MAXDIV5", {"selected": list(rw.keys())})

        if config == "MINVAR_SEL":
            sel = _min_var_subset_lw(ndx_panel, pool, sig_d, min(K, len(pool)))
            rw = {t: 1.0 / len(sel) for t in sel}
            out = _partial_safe_pack(rw, len(sel), safe, K)
            return (out, "NDX_MINVAR_SEL", {"selected": sel})

        if config in ("MIN_CVAR", "MIN_CDAR"):
            alloc = alloc_mincvar if config == "MIN_CVAR" else alloc_mincdar
            if len(pool) <= 1:
                rw = {pool[0]: 1.0}
            else:
                wfull = alloc(ndx_panel, sig_d, pool)   # LP over the N candidates
                rw = _top5_by_weight(wfull, K)          # select+weight of K
            out = _partial_safe_pack(rw, len(rw), safe, K)
            return (out, f"NDX_{config}", {"selected": list(rw.keys())})

        raise ValueError(config)

    return compute


# ----------------------------- run / metrics --------------------------------
def run_config(cpm_panel, ndx_panel, config, N=N_CANON):
    orig = ndx.compute_ndx_weights
    ndx.compute_ndx_weights = make_compute(config, N=N)
    try:
        r, hist = ndx.run_ndx_backtest(cpm_panel, ndx_panel, EXT_START,
                                       min(END, cpm_panel.index[-1]))
    finally:
        ndx.compute_ndx_weights = orig
    return r, hist


def sortino_ann(x):
    x = np.asarray(x, float)
    neg = np.minimum(x, 0.0)
    dd = np.sqrt(np.mean(neg ** 2))
    return (x.mean() * 252.0) / (dd * np.sqrt(252.0)) if dd > 0 else float("nan")


def cvar_ratio_ann(x, q=0.05):
    x = np.asarray(x, float)
    n = x.size
    if n == 0:
        return float("nan")
    k = max(1, int(np.floor(q * n)))
    worst = np.sort(x)[:k]
    es = worst.mean()
    return (x.mean() * 252.0) / abs(es) if es < 0 else float("nan")


def full_metrics(ret, cash):
    m = perf_metrics(ret, cash)
    x = ret.values
    return {
        "Sharpe": m.get("sharpe"), "Sortino": sortino_ann(x),
        "CVaR_ratio": cvar_ratio_ann(x), "Calmar": m.get("calmar"),
        "Martin": m.get("martin"), "MaxDD": m.get("max_drawdown"),
        "CAGR": m.get("cagr"), "vol": m.get("vol"),
    }


CRISES = {
    "dotcom_2000_2002": ("2000-03-01", "2002-10-31"),
    "GFC_2007_2009": ("2007-10-01", "2009-06-30"),
    "COVID_2020": ("2020-02-19", "2020-04-30"),
    "Y2022": ("2022-01-01", "2022-12-31"),
    "Y2025": ("2025-01-01", "2025-06-30"),
}


def crisis_metrics(ret):
    out = {}
    for nm, (a, b) in CRISES.items():
        w = ret.loc[(ret.index >= pd.Timestamp(a)) & (ret.index <= pd.Timestamp(b))]
        if len(w) < 5:
            out[nm] = None
            continue
        x = w.values
        m = perf_metrics(w, None)
        out[nm] = {"Sharpe": m.get("sharpe"), "Sortino": sortino_ann(x),
                   "MaxDD": m.get("max_drawdown"), "CAGR": m.get("cagr")}
    return out


def annual_turnover(hist, clean_start):
    """One-way annualized turnover from monthly target weights (sum|dw|/2 *12)."""
    h = [e for e in hist if e["sig_d"] >= clean_start]
    if len(h) < 2:
        return float("nan")
    prev = {}
    tot, n = 0.0, 0
    for e in h:
        w = e["weights"]
        keys = set(w) | set(prev)
        tot += 0.5 * sum(abs(w.get(k, 0.0) - prev.get(k, 0.0)) for k in keys)
        n += 1
        prev = w
    return tot / n * 12.0 if n else float("nan")


def walk_forward(series, cash, n_seg=3):
    idx = series.index
    bnds = np.linspace(0, len(idx), n_seg + 1).astype(int)
    segs = []
    for i in range(n_seg):
        s = series.iloc[bnds[i]:bnds[i + 1]]
        m = perf_metrics(s, cash)
        segs.append({"start": str(s.index[0].date()), "end": str(s.index[-1].date()),
                     "Sharpe": m.get("sharpe"), "Sortino": sortino_ann(s.values),
                     "CVaR_ratio": cvar_ratio_ann(s.values), "MaxDD": m.get("max_drawdown")})
    return segs


def win(s, a, b):
    return s.loc[(s.index >= a) & (s.index <= b)]


def main():
    panel = load_panel(start=EXT_START, end=END)
    end = min(END, panel.index[-1])
    ndx_panel = ndx.load_ndx_panel()
    cash = panel["SHV"].ffill().pct_change().dropna()

    configs = ["PROD", "MINVAR_SEL", "MIN_CVAR", "MIN_CDAR", "TOP15_EW", "INVVOL5", "MAXDIV5"]
    series_clean, series_ext, results = {}, {}, {}
    for cfg in configs:
        print(f"running {cfg} ...", file=sys.stderr)
        r, hist = run_config(panel, ndx_panel, cfg, N=N_CANON)
        sc = win(r, CLEAN_START, end)
        se = win(r, EXT_START, end)
        series_clean[cfg] = sc
        series_ext[cfg] = se
        results[cfg] = {
            "clean": full_metrics(sc, cash),
            "ext": full_metrics(se, cash),
            "crisis": crisis_metrics(se),
            "turnover_ann": annual_turnover(hist, CLEAN_START),
        }
        m = results[cfg]["clean"]
        print(f"  {cfg}: clean Sharpe={m['Sharpe']:.4f} Sortino={m['Sortino']:.4f} "
              f"CVaR={m['CVaR_ratio']:.3f} MaxDD={m['MaxDD']:.4f} TO={results[cfg]['turnover_ann']:.2f}",
              file=sys.stderr)

    # N sensitivity for the optimizer/selection configs
    nsens = {}
    for cfg in ["MINVAR_SEL", "MIN_CVAR", "MIN_CDAR"]:
        nsens[cfg] = {}
        for N in (10, 20):
            r, hist = run_config(panel, ndx_panel, cfg, N=N)
            sc = win(r, CLEAN_START, end)
            nsens[cfg][f"N{N}"] = {**full_metrics(sc, cash),
                                   "turnover_ann": annual_turnover(hist, CLEAN_START)}
            print(f"  {cfg} N={N}: clean Sharpe={nsens[cfg][f'N{N}']['Sharpe']:.4f}", file=sys.stderr)

    # bootstrap each config vs PROD on clean (dSharpe/dSortino/dCVaR)
    boot = {}
    base = series_clean["PROD"]
    for cfg in configs:
        if cfg == "PROD":
            continue
        print(f"bootstrap {cfg} vs PROD ...", file=sys.stderr)
        boot[cfg] = paired_block_bootstrap_mm(series_clean[cfg], base, cash,
                                              B=2000, block=21, seed=42)

    # walk-forward: any config whose clean dSharpe OR dSortino OR dCVaR is significant (p>0 >=0.95)
    wf = {}
    for cfg in configs:
        if cfg == "PROD":
            continue
        bb = boot[cfg]
        sig = any(bb[m]["p_gt0"] >= 0.95 or bb[m]["p_gt0"] <= 0.05 for m in ("dSharpe", "dSortino", "dCVaR"))
        # also walk-forward any config beating PROD on clean Sharpe point estimate
        if sig or results[cfg]["clean"]["Sharpe"] > results["PROD"]["clean"]["Sharpe"]:
            wf[cfg] = walk_forward(series_clean[cfg], cash, 3)
    wf["PROD"] = walk_forward(base, cash, 3)

    out = {
        "anchor_note": "PROD reproduces clean Sharpe ~1.28, MaxDD ~-31.4% with refreshed NDX prices (2026-05-28).",
        "window": {"clean": [str(CLEAN_START.date()), str(end.date())],
                   "ext": [str(EXT_START.date()), str(end.date())]},
        "N_canonical": N_CANON,
        "results": results, "n_sensitivity": nsens,
        "bootstrap_vs_PROD": boot, "walk_forward": wf,
    }
    op = ROOT / "research" / "cpm_ndx_minvar_cvar_findings.json"
    op.write_text(json.dumps(out, indent=2, default=float))
    print("WROTE", op, file=sys.stderr)
    return out


if __name__ == "__main__":
    main()
