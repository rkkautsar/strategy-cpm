"""Exploratory backtest: COVARIANCE RE-WEIGHTING the CPM risky picks to a vol
target vs the current EW uniform scale-to-cash vol-target.

HYPOTHESIS
----------
De-risk the CPM risky block TO A VOL TARGET (10%) BY COVARIANCE RE-WEIGHTING:
use the covariance matrix Sigma over the (prod-selected) picks to adjust the
risky-asset weights so portfolio ex-ante vol hits the target via diversification,
shedding to cash only the RESIDUAL that diversification cannot absorb. Compare
versus the current/reference approach (EW picks + uniform scale-to-cash).

Claim: covariance re-weighting hits the same target vol while keeping MORE
invested in risky assets (less cash drag) -> retains more CAGR at the same
realized vol -> better Sharpe/Calmar/Martin.

SELECTION IS UNCHANGED FROM PROD for every variant: vol-adj Faber rank + positive
filter + TIP-only canary + min-var 3-of-4 at n_pos=4. Only the WEIGHTING of the
selected picks (and the de-risk mechanism) changes.

VARIANTS
--------
baseline (prod EW, no VT):
    prod compute_target_weights as-is (EW picks, risky_fraction = min(n_pos,4)/4,
    remainder -> prod safe). No vol targeting.

reference EW-scale-to-cash (VT-10, the prior best de-risk):
    prod output, scaled block by min(1, target/rv_CPM), shed -> safe. rv_CPM =
    trailing 252d realized vol of the BASELINE CPM sleeve daily returns, lagged
    to sig_d. (Reproduces research/cpm_voltarget_compare VT-10% 252d.)

V1  MIN-VAR-WEIGHT + residual cash:
    w = long-only min-variance weights over picks (minimize w'Sigma w, sum w = 1,
    w_i >= 0). Sigma = annualized sample covariance of picks over the trailing
    CORR_LOOKBACK_DAYS (252d) daily returns, lagged to sig_d (same window as
    cpm_live._min_var_subset). Ex-ante risky vol v = sqrt(w'Sigma w). De-risk
    only: f = min(1, target / v); risky = w * f; cash = (1 - f) -> safe. If
    v <= target, hold w fully (no lever-up).

V2  TARGET-VOL TILT (exact formulation):
    Choose w to MAXIMIZE momentum-score-weighted exposure subject to a covariance
    vol cap:
        maximize   s . w
        s.t.       sqrt(w' Sigma w) <= target
                   w_i >= 0,  sum_i w_i <= 1
        cash       = 1 - sum_i w_i   (-> safe)
    where s_i = the prod vol-adjusted Faber score (faber[i] / vol_252[i]) of pick
    i (always > 0 because picks pass the positive-faber filter). Solved by SLSQP.
    The objective pushes total exposure toward 1 and tilts toward high-momentum
    picks; the covariance constraint caps vol via diversification; cash is the
    last-resort residual only when even a diversified full-invested book would
    breach the cap.

All de-risk inputs (Sigma, rv) are LAGGED to sig_d (PIT-clean). Monthly, T+1
MOO, 10 bps/side. Long-only weights. Sleeve via cpm_harness mooex; blend via
build_dashboard build_artifacts (CPM swapped, BULL+NDX fixed).

RESEARCH-ONLY. No prod edits, no commit.
"""

from __future__ import annotations

from pathlib import Path
import sys

import numpy as np
import pandas as pd
from scipy.optimize import minimize

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import cpm_live
from cpm_live import (
    RISKY_UNIVERSE, SAFE_POOL, CANARY_ASSETS, CANARY_RULE,
    TOP_K_CANDIDATES, CORR_LOOKBACK_DAYS,
    best_safe, sig_13612U, faber_sma_xs, _min_var_subset,
    compute_target_weights,
)
from research import cpm_harness as H
from research.cpm_npos4_droptosafe_run import (
    baseline_weight_fn, extra_metrics, turnover_avg,
)
from research.cpm_voltarget_compare_run import (
    _vt_scale, _vt_apply, make_vt_weight_fn, make_vt_ctw,
)

TARGET = 0.10            # primary vol target (annualized)
LOOKBACK = CORR_LOOKBACK_DAYS  # 252


# --------------------------------------------------------------------------
# Prod SELECTION replica -> (regime, safe, picks, scores). Selection IDENTICAL
# to compute_target_weights; only used to expose picks/scores for re-weighting.
# --------------------------------------------------------------------------
def _select(close_panel, sig_d):
    universe = RISKY_UNIVERSE
    safe_pool = SAFE_POOL
    canary_assets = CANARY_ASSETS

    monthly = close_panel.loc[:sig_d].resample("ME").last()
    safe = best_safe(monthly, sig_d, safe_pool)

    canary_scores = []
    for c in canary_assets:
        if c not in monthly.columns:
            continue
        s = sig_13612U(monthly[c])
        if pd.notna(s):
            canary_scores.append(s)
    if not canary_scores:
        return "DEFENSIVE", safe, [], {}
    n_canary_pos = sum(1 for s in canary_scores if s > 0)
    if CANARY_RULE == "any_positive":
        if n_canary_pos == 0:
            return "DEFENSIVE", safe, [], {}
    elif CANARY_RULE == "all_positive":
        if n_canary_pos < len(canary_scores):
            return "DEFENSIVE", safe, [], {}
    else:
        if n_canary_pos <= len(canary_scores) // 2:
            return "DEFENSIVE", safe, [], {}

    faber = faber_sma_xs(monthly)
    avail = [t for t in universe
             if t in faber.index and pd.notna(faber[t])
             and pd.notna(close_panel.loc[sig_d].get(t, np.nan) if sig_d in close_panel.index else np.nan)]
    if not avail:
        return "DEFENSIVE", safe, [], {}

    daily_rets = close_panel[avail].ffill().pct_change()
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
        return "DEFENSIVE", safe, [], {}

    positive_picks = list(positive.index)
    n_pos = len(positive_picks)
    if n_pos == 4:
        picks = _min_var_subset(close_panel, sig_d, positive_picks, CORR_LOOKBACK_DAYS, 3)
    else:
        picks = positive_picks

    return "RISK_ON", safe, list(picks), {t: float(scores[t]) for t in picks}


# --------------------------------------------------------------------------
# Sigma (annualized) over picks, lagged to sig_d, trailing LOOKBACK days.
# Mirrors cpm_live._min_var_subset windowing (close.loc[:sig_d], tail(lookback)).
# Returns (Sigma_ndarray in `picks` order, ok_flag).
# --------------------------------------------------------------------------
def _sigma_ann(close_panel, sig_d, picks, lookback):
    rets = (close_panel.loc[:sig_d][picks].ffill().pct_change()
            .dropna(how="all").tail(lookback))
    if len(rets) < lookback:
        return None, False
    cov = rets.cov()
    if cov.isna().any().any():
        return None, False
    Sigma = cov.loc[picks, picks].values * 252.0
    return Sigma, True


def _min_var_weights(Sigma):
    n = Sigma.shape[0]
    if n == 1:
        return np.array([1.0])
    w0 = np.ones(n) / n
    cons = [{"type": "eq", "fun": lambda w: w.sum() - 1.0}]
    bnds = [(0.0, 1.0)] * n
    res = minimize(lambda w: float(w @ Sigma @ w), w0, method="SLSQP",
                   bounds=bnds, constraints=cons,
                   options={"maxiter": 200, "ftol": 1e-12})
    w = np.clip(res.x, 0.0, None)
    s = w.sum()
    return w / s if s > 0 else np.ones(n) / n


def _tilt_weights(Sigma, scores, target):
    """maximize s.w  s.t.  w'Sigma w <= target^2,  w>=0,  sum w <= 1."""
    n = Sigma.shape[0]
    s = np.asarray(scores, dtype=float)
    if (s <= 0).all():
        s = np.ones(n)
    w0 = np.full(n, 0.5 / n)  # feasible interior start (low vol, low exposure)
    cons = [
        {"type": "ineq", "fun": lambda w: target * target - float(w @ Sigma @ w)},
        {"type": "ineq", "fun": lambda w: 1.0 - w.sum()},
    ]
    bnds = [(0.0, 1.0)] * n
    res = minimize(lambda w: -float(s @ w), w0, method="SLSQP",
                   bounds=bnds, constraints=cons,
                   options={"maxiter": 300, "ftol": 1e-12})
    w = np.clip(res.x, 0.0, None)
    # enforce constraints numerically (guard against tiny SLSQP overshoot)
    if w.sum() > 1.0:
        w = w / w.sum()
    v = np.sqrt(max(float(w @ Sigma @ w), 0.0))
    if v > target and v > 0:
        w = w * (target / v)
    return w


# --------------------------------------------------------------------------
# V1 / V2 weight functions (sleeve weight_fn signature) + ctw (blend signature).
# --------------------------------------------------------------------------
def _v1_core(close_panel, sig_d, target=TARGET, lookback=LOOKBACK):
    regime, safe, picks, _scores = _select(close_panel, sig_d)
    if regime == "DEFENSIVE" or not picks:
        return {safe: 1.0}, safe
    Sigma, ok = _sigma_ann(close_panel, sig_d, picks, lookback)
    if not ok:
        # fallback: EW, scale to target by ex-ante EW vol unavailable -> hold EW full
        w = np.ones(len(picks)) / len(picks)
        out = {picks[i]: float(w[i]) for i in range(len(picks))}
        return out, safe
    w = _min_var_weights(Sigma)
    v = float(np.sqrt(max(w @ Sigma @ w, 0.0)))
    f = min(1.0, target / v) if (np.isfinite(v) and v > 0) else 1.0
    out = {picks[i]: float(w[i] * f) for i in range(len(picks))}
    cash = 1.0 - f
    if cash > 1e-12:
        out[safe] = out.get(safe, 0.0) + cash
    return out, safe


def _v2_core(close_panel, sig_d, target=TARGET, lookback=LOOKBACK):
    regime, safe, picks, scores = _select(close_panel, sig_d)
    if regime == "DEFENSIVE" or not picks:
        return {safe: 1.0}, safe
    Sigma, ok = _sigma_ann(close_panel, sig_d, picks, lookback)
    s = np.array([scores[t] for t in picks], dtype=float)
    if not ok:
        w = np.ones(len(picks)) / len(picks)
        out = {picks[i]: float(w[i]) for i in range(len(picks))}
        return out, safe
    w = _tilt_weights(Sigma, s, target)
    out = {picks[i]: float(w[i]) for i in range(len(picks)) if w[i] > 1e-9}
    cash = 1.0 - float(sum(out.get(picks[i], 0.0) for i in range(len(picks))))
    if cash > 1e-12:
        out[safe] = out.get(safe, 0.0) + cash
    return out, safe


def v1_weight_fn(close_panel, sig_d):
    out, _ = _v1_core(close_panel, sig_d)
    return out


def v2_weight_fn(close_panel, sig_d):
    out, _ = _v2_core(close_panel, sig_d)
    return out


def v1_ctw(close_panel, sig_d, universe=None, safe_pool=None, canary_assets=None):
    out, safe = _v1_core(close_panel, sig_d)
    regime = "DEFENSIVE" if set(out) == {safe} and abs(out.get(safe, 0) - 1.0) < 1e-9 else "RISK_ON"
    basket = tuple(t for t in out if t in RISKY_UNIVERSE)
    return out, basket, regime, safe


def v2_ctw(close_panel, sig_d, universe=None, safe_pool=None, canary_assets=None):
    out, safe = _v2_core(close_panel, sig_d)
    regime = "DEFENSIVE" if set(out) == {safe} and abs(out.get(safe, 0) - 1.0) < 1e-9 else "RISK_ON"
    basket = tuple(t for t in out if t in RISKY_UNIVERSE)
    return out, basket, regime, safe


# --------------------------------------------------------------------------
# Diagnostics: mean equity (risky) exposure + ex-ante vol stats.
# --------------------------------------------------------------------------
def exposure_avg(weight_fn, close, sigs) -> float:
    """Mean (over signal months) of total weight in RISKY_UNIVERSE assets."""
    exps = []
    for sig_d in sigs:
        w = weight_fn(close, sig_d)
        exps.append(sum(v for t, v in w.items() if t in RISKY_UNIVERSE))
    return float(np.mean(exps)) if exps else float("nan")


def exante_vol_stats(core_fn, close, sigs):
    """Mean ex-ante risky vol of the (re-weighted) book at sig_d, risk-on only."""
    vs, exps = [], []
    for sig_d in sigs:
        regime, safe, picks, scores = _select(close, sig_d)
        if regime != "RISK_ON" or not picks:
            continue
        Sigma, ok = _sigma_ann(close, sig_d, picks, LOOKBACK)
        if not ok:
            continue
        out, _ = core_fn(close, sig_d)
        w = np.array([out.get(t, 0.0) for t in picks])
        vs.append(float(np.sqrt(max(w @ Sigma @ w, 0.0))))
        exps.append(float(w.sum()))
    return {
        "mean_exante_vol": float(np.mean(vs)) if vs else float("nan"),
        "mean_riskon_exposure": float(np.mean(exps)) if exps else float("nan"),
        "n_riskon": len(vs),
    }


# --------------------------------------------------------------------------
# Metrics assembly.
# --------------------------------------------------------------------------
def full_metrics(returns, cash, close, sigs, weight_fn) -> dict:
    m = cpm_live.perf_metrics(returns, cash)
    em = extra_metrics(returns, cash)
    to = turnover_avg(weight_fn, close, sigs) if weight_fn is not None else float("nan")
    exp = exposure_avg(weight_fn, close, sigs) if weight_fn is not None else float("nan")
    return {
        "Sharpe": m["sharpe"], "Sortino": em["Sortino"],
        "CVaR95_d": em["CVaR95_daily"], "Calmar": m["calmar"],
        "Martin": m["martin"], "MaxDD": m["max_drawdown"],
        "CAGR": m["cagr"], "vol": m["vol"], "turnover": to, "expo": exp,
    }


def fmt_table(rows: dict, order: list) -> str:
    cols = ["Sharpe", "Sortino", "CVaR95_d", "Calmar", "Martin", "MaxDD",
            "CAGR", "vol", "turnover", "expo"]
    head = "config".ljust(26) + "".join(c.rjust(11) for c in cols)
    lines = [head, "-" * len(head)]
    for name in order:
        m = rows[name]
        cells = []
        for c in cols:
            v = m[c]
            if isinstance(v, float) and np.isnan(v):
                cells.append("-".rjust(11))
            elif c in ("MaxDD", "CAGR", "vol", "CVaR95_d", "expo"):
                cells.append(f"{v*100:.2f}%".rjust(11))
            else:
                cells.append(f"{v:.3f}".rjust(11))
        lines.append(name.ljust(26) + "".join(cells))
    return "\n".join(lines)


def crisis_multi(series_by_name: dict, names: list) -> str:
    crises = {
        "GFC 2007-09..2009-03": ("2007-09-01", "2009-03-31"),
        "Euro 2011-05..2011-10": ("2011-05-01", "2011-10-31"),
        "2015-16 selloff": ("2015-07-01", "2016-02-29"),
        "Q4-2018": ("2018-10-01", "2018-12-31"),
        "COVID 2020-02..04": ("2020-02-01", "2020-04-30"),
        "2022 bear": ("2022-01-01", "2022-10-31"),
    }
    def cum(x):
        return (1 + x).prod() - 1
    def mdd(x):
        eq = (1 + x).cumprod()
        return (eq / eq.cummax() - 1).min()
    head = "crisis".ljust(24) + "".join(f"{n[:7]}_ret".rjust(12) for n in names) \
        + "".join(f"{n[:7]}_DD".rjust(12) for n in names)
    lines = [head, "-" * len(head)]
    for cname, (s, e) in crises.items():
        rets, dds, ok = [], [], False
        for n in names:
            w = series_by_name[n].loc[(series_by_name[n].index >= s)
                                      & (series_by_name[n].index <= e)]
            if w.empty:
                rets.append(float("nan")); dds.append(float("nan"))
            else:
                ok = True
                rets.append(cum(w)); dds.append(mdd(w))
        if not ok:
            continue
        line = cname.ljust(24)
        line += "".join((f"{r*100:.2f}%".rjust(12) if np.isfinite(r) else "-".rjust(12)) for r in rets)
        line += "".join((f"{d*100:.2f}%".rjust(12) if np.isfinite(d) else "-".rjust(12)) for d in dds)
        lines.append(line)
    return "\n".join(lines)


def walkforward(series_by_name, names, n_seg=3) -> str:
    """3-segment contiguous walk-forward: per-segment Sharpe/Martin/CAGR/vol/MaxDD."""
    idx = series_by_name[names[0]].index
    bounds = pd.date_range(idx[0], idx[-1], periods=n_seg + 1)
    lines = []
    for k in range(n_seg):
        s, e = bounds[k], bounds[k + 1]
        head = (f"seg{k+1} {s.date()}..{e.date()}").ljust(30) \
            + "Sharpe".rjust(9) + "Martin".rjust(9) + "CAGR".rjust(9) \
            + "vol".rjust(9) + "MaxDD".rjust(9)
        lines.append(head)
        lines.append("-" * len(head))
        for n in names:
            x = series_by_name[n].loc[(series_by_name[n].index >= s)
                                      & (series_by_name[n].index <= e)]
            m = cpm_live.perf_metrics(x)
            lines.append(n.ljust(30)
                         + f"{m['sharpe']:.3f}".rjust(9)
                         + f"{m['martin']:.3f}".rjust(9)
                         + f"{m['cagr']*100:.2f}%".rjust(9)
                         + f"{m['vol']*100:.2f}%".rjust(9)
                         + f"{m['max_drawdown']*100:.2f}%".rjust(9))
        lines.append("")
    return "\n".join(lines)


def main():
    print("Loading harness data ...")
    data = H.load_data()
    cash = data.cash
    close = data.panel

    anc = H.verify_anchor(data=data)
    print(f"[ok] anchor Sharpe={anc['Sharpe']:.6f} MaxDD={anc['MaxDD']:.6f} "
          f"Calmar={anc['Calmar']:.6f}")

    print("Computing baseline CPM sleeve returns (ext) for rv proxy ...")
    baseline_ret_ext = H.run_strategy(compute_target_weights, window="ext", data=data)
    ref_fn = make_vt_weight_fn(baseline_ret_ext, TARGET, 252)

    out = []
    out.append("# CPM vol-target by COVARIANCE RE-WEIGHTING vs EW scale-to-cash "
               "-- exploratory\n")
    out.append("Selection IDENTICAL to prod (vol-adj rank + positive filter + "
               "TIP canary + min-var 3-of-4 @ n_pos=4); only WEIGHTING of picks "
               "changes. Target vol = 10%. Sigma/rv lagged to sig_d (PIT-clean). "
               "Monthly, T+1, 10 bps. Long-only.\n")
    out.append("Configs: baseline (prod EW, no VT) | EW-scale-to-cash (VT-10, "
               "prior best) | V1 min-var-weight+residual cash | V2 target-vol tilt.")

    midx = (pd.DataFrame({"x": 1}, index=close.index)
            .groupby(pd.Grouper(freq="ME")).tail(1).index)

    # ---- ex-ante vol / exposure diagnostics (clean) ----
    sigs_clean = midx[(midx >= data.clean_start) & (midx <= data.end)]
    v1_ex = exante_vol_stats(_v1_core, close, sigs_clean)
    v2_ex = exante_vol_stats(_v2_core, close, sigs_clean)
    out.append(f"\n## Ex-ante diagnostics (clean, {len(sigs_clean)} months, "
               f"{v1_ex['n_riskon']} risk-on)")
    out.append("```")
    out.append("variant            mean_exante_vol   mean_riskon_exposure")
    out.append(f"V1 min-var-weight  {v1_ex['mean_exante_vol']*100:14.2f}%   "
               f"{v1_ex['mean_riskon_exposure']*100:18.2f}%")
    out.append(f"V2 target-vol tilt {v2_ex['mean_exante_vol']*100:14.2f}%   "
               f"{v2_ex['mean_riskon_exposure']*100:18.2f}%")
    out.append("```")

    # ---- SLEEVE level ----
    sleeve_series = {}
    for win in ("clean", "ext"):
        start = data.clean_start if win == "clean" else data.ext_start
        sigs = midx[(midx >= start) & (midx <= data.end)]

        base_ret = H.run_strategy(baseline_weight_fn, window=win, data=data)
        ref_ret = H.run_strategy(ref_fn, window=win, data=data)
        v1_ret = H.run_strategy(v1_weight_fn, window=win, data=data)
        v2_ret = H.run_strategy(v2_weight_fn, window=win, data=data)

        rows = {
            "baseline (prod EW)": full_metrics(base_ret, cash, close, sigs, baseline_weight_fn),
            "EW-scale-to-cash VT10": full_metrics(ref_ret, cash, close, sigs, ref_fn),
            "V1 min-var-weight": full_metrics(v1_ret, cash, close, sigs, v1_weight_fn),
            "V2 target-vol tilt": full_metrics(v2_ret, cash, close, sigs, v2_weight_fn),
        }
        order = ["baseline (prod EW)", "EW-scale-to-cash VT10",
                 "V1 min-var-weight", "V2 target-vol tilt"]
        out.append(f"\n## SLEEVE ({win}) -- mooex T+1, 10bps  "
                   "(expo = mean weight in risky universe)")
        out.append("```")
        out.append(fmt_table(rows, order))
        out.append("```")
        if win == "clean":
            sleeve_series = {
                "base": base_ret, "EWcash": ref_ret,
                "V1": v1_ret, "V2": v2_ret,
            }

    out.append("\n### Per-crisis (sleeve, clean) cum return + maxDD")
    out.append("```")
    out.append(crisis_multi(sleeve_series, ["base", "EWcash", "V1", "V2"]))
    out.append("```")

    out.append("\n### 3-segment walk-forward (sleeve, clean) -- OOS stability check")
    out.append("```")
    out.append(walkforward(sleeve_series, ["base", "EWcash", "V1", "V2"]))
    out.append("```")

    # ---- BLEND level ----
    import build_dashboard as BD
    from cpm_live import load_panel
    print("Loading blend panel + NDX ...")
    bpanel = load_panel(start=pd.Timestamp("1995-01-01"), end=data.end, live=True)
    bend = min(data.end, bpanel.index[-1])
    bcash = bpanel["SHV"].ffill().pct_change().dropna()
    try:
        from ndx_sleeve_live import load_ndx_panel
        ndx_panel = load_ndx_panel()
    except Exception as e:
        print(f"  NDX panel unavailable ({e}); blend uses CPM+BULL only.")
        ndx_panel = None
    bstart = data.clean_start

    def blend_metrics(art):
        m = cpm_live.perf_metrics(art.blend, bcash)
        em = extra_metrics(art.blend, bcash)
        return {
            "Sharpe": m["sharpe"], "Sortino": em["Sortino"],
            "CVaR95_d": em["CVaR95_daily"], "Calmar": m["calmar"],
            "Martin": m["martin"], "MaxDD": m["max_drawdown"],
            "CAGR": m["cagr"], "vol": m["vol"], "turnover": float("nan"),
            "expo": float("nan"),
        }

    print("Building baseline blend ...")
    art_base = BD.build_artifacts(bpanel, ndx_panel, bstart, bend, include_records=False)

    _orig = cpm_live.compute_target_weights
    print("Building EW-scale-to-cash blend ...")
    cpm_live.compute_target_weights = make_vt_ctw(baseline_ret_ext, TARGET, 252)
    try:
        art_ref = BD.build_artifacts(bpanel, ndx_panel, bstart, bend, include_records=False)
    finally:
        cpm_live.compute_target_weights = _orig

    print("Building V1 blend ...")
    cpm_live.compute_target_weights = v1_ctw
    try:
        art_v1 = BD.build_artifacts(bpanel, ndx_panel, bstart, bend, include_records=False)
    finally:
        cpm_live.compute_target_weights = _orig

    print("Building V2 blend ...")
    cpm_live.compute_target_weights = v2_ctw
    try:
        art_v2 = BD.build_artifacts(bpanel, ndx_panel, bstart, bend, include_records=False)
    finally:
        cpm_live.compute_target_weights = _orig

    brows = {
        "baseline (prod EW)": blend_metrics(art_base),
        "EW-scale-to-cash VT10": blend_metrics(art_ref),
        "V1 min-var-weight": blend_metrics(art_v1),
        "V2 target-vol tilt": blend_metrics(art_v2),
    }
    order = ["baseline (prod EW)", "EW-scale-to-cash VT10",
             "V1 min-var-weight", "V2 target-vol tilt"]
    out.append(f"\n## BLEND 60/20/20 (clean {bstart.date()}..{bend.date()}) "
               "-- close-to-close T+1, 10bps; BULL+NDX identical")
    out.append("```")
    out.append(fmt_table(brows, order))
    out.append("```")
    out.append("\n### Per-crisis (blend, clean)")
    out.append("```")
    out.append(crisis_multi(
        {"base": art_base.blend, "EWcash": art_ref.blend,
         "V1": art_v1.blend, "V2": art_v2.blend},
        ["base", "EWcash", "V1", "V2"]))
    out.append("```")
    out.append("\n### 3-segment walk-forward (blend, clean)")
    out.append("```")
    out.append(walkforward(
        {"base": art_base.blend, "EWcash": art_ref.blend,
         "V1": art_v1.blend, "V2": art_v2.blend},
        ["base", "EWcash", "V1", "V2"]))
    out.append("```")

    report = "\n".join(out)
    print("\n" + report)
    rp = ROOT / "research" / "cpm_voltarget_reweight_findings_raw.txt"
    rp.write_text(report)
    print(f"\n[written] {rp}")


if __name__ == "__main__":
    main()
