"""Exploratory backtest: PARAMETER-FREE external vol-target anchors for the CPM
sleeve, vs the fixed VT-10 / VT-12 winners.

HYPOTHESIS
----------
The fixed continuous vol-target (scale CPM risky block by min(1, target/rv_CPM),
de-risk-only, shed -> safe, monthly / lagged / T+1 / 10bps) is the best de-risk
found for CPM, but it relies on a hand-picked 10% / 12% TARGET. Can a
PARAMETER-FREE external benchmark vol REPLACE that magic constant?

The de-risk MECHANISM is IDENTICAL to research/cpm_voltarget_compare_run.py:
    scale  = min(1, target / rv_CPM)
    rv_CPM = trailing 252d realized vol of the BASELINE CPM sleeve daily returns,
             lagged to sig_d (PIT-clean). DENOMINATOR UNCHANGED across all configs.
ONLY the TARGET (numerator) differs:
  * VT-10% / VT-12%  : fixed constant (reference winners).
  * VT-6040-trailing : trailing 252d realized vol of a 60/40 portfolio
                       (0.6*SPY + 0.4*IEF fixed-weight daily returns), lagged.
  * VT-6040-expand   : EXPANDING-window mean of completed-month 60/40 realized
                       vol (inception -> t-1). Parameter-free + contamination
                       resistant. KEY TEST: does this rediscover ~VT-10?

60/40 long-run vol ~9-10% ~= CPM's own ~10.3%, so a 60/40 anchor should bind
similarly to fixed VT-10. SPY-vol anchors were DROPPED (SPY ~16-18% >> CPM ~10%
=> near no-op; agreed a-priori).

For each anchor we report MEAN TARGET LEVEL (annualized, vs CPM ~10.3%) and
BIND FREQUENCY (fraction of months scale<1) to explain behavior.

RESEARCH-ONLY. Does not edit prod. Reuses cpm_harness sleeve engine + the
fixed-VT mechanism helpers from cpm_voltarget_compare_run, and build_dashboard
build_artifacts for the blend (monkeypatched compute_target_weights).

PIT integrity: trailing target uses only returns <= sig_d; expanding target uses
only COMPLETED months strictly before sig_d's month. rv_CPM uses the baseline
(unscaled) prod sleeve returns <= sig_d (standard non-recursive VT construction).
Cached frozen dataset; absolute levels apples-to-apples across configs.
"""

from __future__ import annotations

from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import cpm_live
from cpm_live import compute_target_weights
from research import cpm_harness as H
from research.cpm_npos4_droptosafe_run import (
    baseline_weight_fn,
    extra_metrics,
    turnover_avg,
)
from research.cpm_voltarget_compare_run import _vt_apply, fmt_table, crisis_multi

MIN_MONTH_DAYS = 15  # match cpm_ndx_voltarget_qqq_harness expanding estimator
MIN_EXPAND_OBS = 4


# --------------------------------------------------------------------------
# External benchmark daily returns (60/40 = 0.6*SPY + 0.4*IEF fixed-weight).
# --------------------------------------------------------------------------
def bench_6040_returns(panel: pd.DataFrame) -> pd.Series:
    spy = panel["SPY"].ffill().pct_change()
    ief = panel["IEF"].ffill().pct_change()
    r = 0.6 * spy + 0.4 * ief
    return r.dropna()


# --------------------------------------------------------------------------
# Target estimators (PIT-clean, lagged to sig_d).
# --------------------------------------------------------------------------
def make_fixed_target(level: float):
    return lambda sig_d: float(level)


def make_trailing_target(bench_ret: pd.Series, window: int = 252):
    def fn(sig_d):
        hist = bench_ret.loc[bench_ret.index <= sig_d]
        if len(hist) < window:
            return None
        rv = float(hist.tail(window).std(ddof=0) * np.sqrt(252))
        return rv if np.isfinite(rv) and rv > 0 else None
    return fn


def make_expanding_target(bench_ret: pd.Series):
    """Expanding mean of completed-month realized vol, inception -> t-1."""
    def fn(sig_d):
        s = bench_ret.loc[bench_ret.index <= sig_d]
        cur_m = pd.Timestamp(sig_d).to_period("M")
        vals = []
        for m, grp in s.groupby(s.index.to_period("M")):
            if m >= cur_m or len(grp) < MIN_MONTH_DAYS:
                continue
            v = float(grp.std(ddof=0) * np.sqrt(252))
            if np.isfinite(v) and v > 0:
                vals.append(v)
        if len(vals) < MIN_EXPAND_OBS:
            return None
        return float(np.mean(vals))
    return fn


# --------------------------------------------------------------------------
# Vol-target core: scale prod risky block by min(1, target/rv_CPM).
# rv_CPM = trailing 252d vol of baseline CPM sleeve daily returns, lagged.
# --------------------------------------------------------------------------
def _vt_scale(baseline_ret: pd.Series, sig_d: pd.Timestamp,
              target_fn, window: int = 252) -> float:
    hist = baseline_ret.loc[baseline_ret.index <= sig_d]
    if len(hist) < window:
        return 1.0
    rv = hist.tail(window).std(ddof=0) * np.sqrt(252)
    if not np.isfinite(rv) or rv <= 0:
        return 1.0
    target = target_fn(sig_d)
    if target is None or not np.isfinite(target) or target <= 0:
        return 1.0
    return float(min(1.0, target / rv))


def make_vt_weight_fn(baseline_ret, target_fn, window=252):
    def fn(close_panel, sig_d):
        out, _basket, _regime, safe = compute_target_weights(close_panel, sig_d)
        scale = _vt_scale(baseline_ret, sig_d, target_fn, window)
        return _vt_apply(out, safe, scale)
    return fn


def make_vt_ctw(baseline_ret, target_fn, window=252):
    def ctw(close_panel, sig_d, universe=None, safe_pool=None, canary_assets=None):
        out, basket, regime, safe = compute_target_weights(close_panel, sig_d)
        scale = _vt_scale(baseline_ret, sig_d, target_fn, window)
        return _vt_apply(out, safe, scale), basket, regime, safe
    return ctw


# --------------------------------------------------------------------------
# Diagnostics: bind freq, mean scale, mean target level (annualized).
# --------------------------------------------------------------------------
def bind_stats(baseline_ret, sigs, target_fn, window=252) -> dict:
    scales, targets = [], []
    for d in sigs:
        scales.append(_vt_scale(baseline_ret, d, target_fn, window))
        t = target_fn(d)
        if t is not None and np.isfinite(t):
            targets.append(t)
    s = np.array(scales)
    bind = s < 1.0 - 1e-9
    tg = np.array(targets)
    return {
        "n_months": len(s),
        "bind_frac": float(bind.mean()) if len(s) else float("nan"),
        "mean_scale": float(s.mean()) if len(s) else float("nan"),
        "min_scale": float(s.min()) if len(s) else float("nan"),
        "mean_scale_when_bind": float(s[bind].mean()) if bind.any() else float("nan"),
        "mean_target": float(tg.mean()) if len(tg) else float("nan"),
        "min_target": float(tg.min()) if len(tg) else float("nan"),
        "max_target": float(tg.max()) if len(tg) else float("nan"),
    }


def full_metrics(returns, cash, close, sigs, weight_fn, bind=None) -> dict:
    m = cpm_live.perf_metrics(returns, cash)
    em = extra_metrics(returns, cash)
    to = turnover_avg(weight_fn, close, sigs) if weight_fn is not None else float("nan")
    row = {
        "Sharpe": m["sharpe"], "Sortino": em["Sortino"],
        "CVaR95_d": em["CVaR95_daily"], "Calmar": m["calmar"],
        "Martin": m["martin"], "MaxDD": m["max_drawdown"],
        "CAGR": m["cagr"], "vol": m["vol"], "turnover": to,
        "bindfrac": float("nan"), "meanscale": float("nan"),
    }
    if bind is not None:
        row["bindfrac"] = bind["bind_frac"]
        row["meanscale"] = bind["mean_scale"]
    return row


def main():
    print("Loading harness data ...")
    data = H.load_data()
    cash = data.cash
    close = data.panel

    anc = H.verify_anchor(data=data)
    print(f"[ok] anchor Sharpe={anc['Sharpe']:.6f} MaxDD={anc['MaxDD']:.6f} "
          f"Calmar={anc['Calmar']:.6f}")

    print("Computing baseline CPM sleeve returns (ext) for rv_CPM proxy ...")
    baseline_ret_ext = H.run_strategy(compute_target_weights, window="ext", data=data)

    b6040 = bench_6040_returns(close)
    print(f"60/40 bench returns: {b6040.index[0].date()}..{b6040.index[-1].date()} "
          f"({len(b6040)} days), full-period ann vol "
          f"{b6040.std(ddof=0)*np.sqrt(252)*100:.2f}%")

    # config -> (target_fn, label)
    CFG = {
        "VT-10% (fixed)":     make_fixed_target(0.10),
        "VT-12% (fixed)":     make_fixed_target(0.12),
        "VT-6040-trailing":   make_trailing_target(b6040, 252),
        "VT-6040-expand":     make_expanding_target(b6040),
    }
    vt_fns = {name: make_vt_weight_fn(baseline_ret_ext, tf, 252)
              for name, tf in CFG.items()}

    out = []
    out.append("# CPM parameter-free external vol-target anchors vs fixed VT-10/12\n")
    out.append("Mechanism IDENTICAL to fixed VT: scale=min(1, target/rv_CPM), "
               "de-risk-only, shed->safe, monthly/lagged/T+1/10bps. "
               "rv_CPM = trailing 252d baseline CPM sleeve vol (UNCHANGED). "
               "ONLY target differs. 60/40 = 0.6*SPY+0.4*IEF fixed-weight daily.")

    # ---- bind freq / effect size / mean target (clean) ----
    midx = (pd.DataFrame({"x": 1}, index=close.index)
            .groupby(pd.Grouper(freq="ME")).tail(1).index)
    sigs_clean = midx[(midx >= data.clean_start) & (midx <= data.end)]
    binds = {name: bind_stats(baseline_ret_ext, sigs_clean, tf, 252)
             for name, tf in CFG.items()}
    out.append(f"\n## Bind freq / effect size / target level (clean "
               f"{data.clean_start.date()}..{data.end.date()}, "
               f"{len(sigs_clean)} months)")
    out.append("```")
    bh = ("config".ljust(20) + "bind_frac".rjust(10) + "mean_scl".rjust(10)
          + "min_scl".rjust(9) + "scl|bind".rjust(10)
          + "meanTgt".rjust(9) + "minTgt".rjust(9) + "maxTgt".rjust(9))
    out.append(bh)
    out.append("-" * len(bh))
    for name in CFG:
        b = binds[name]
        out.append(name.ljust(20)
                   + f"{b['bind_frac']*100:.1f}%".rjust(10)
                   + f"{b['mean_scale']:.4f}".rjust(10)
                   + f"{b['min_scale']:.4f}".rjust(9)
                   + f"{b['mean_scale_when_bind']:.4f}".rjust(10)
                   + f"{b['mean_target']*100:.2f}%".rjust(9)
                   + f"{b['min_target']*100:.2f}%".rjust(9)
                   + f"{b['max_target']*100:.2f}%".rjust(9))
    out.append("```")
    out.append("(CPM sleeve full-period vol ~10.3%; target>rv_CPM => scale=1 => "
               "no de-risk. mean target shows where the anchor sits.)")

    # ---- SLEEVE level (mooex), clean + ext ----
    order = ["baseline (prod)", "VT-10% (fixed)", "VT-12% (fixed)",
             "VT-6040-trailing", "VT-6040-expand"]
    sleeve_series = {}
    for win in ("clean", "ext"):
        start = data.clean_start if win == "clean" else data.ext_start
        sigs = midx[(midx >= start) & (midx <= data.end)]
        base_ret = H.run_strategy(baseline_weight_fn, window=win, data=data)
        vt_ret = {name: H.run_strategy(fn, window=win, data=data)
                  for name, fn in vt_fns.items()}
        rows = {"baseline (prod)": full_metrics(base_ret, cash, close, sigs,
                                                baseline_weight_fn)}
        for name, tf in CFG.items():
            rows[name] = full_metrics(vt_ret[name], cash, close, sigs, vt_fns[name],
                                      bind=bind_stats(baseline_ret_ext, sigs, tf, 252))
        out.append(f"\n## SLEEVE ({win}) -- mooex T+1, 10bps")
        out.append("```")
        out.append(fmt_table(rows, order))
        out.append("```")
        if win == "clean":
            sleeve_series = {
                "baseline": base_ret,
                "VT10": vt_ret["VT-10% (fixed)"],
                "VT12": vt_ret["VT-12% (fixed)"],
                "6040tr": vt_ret["VT-6040-trailing"],
                "6040ex": vt_ret["VT-6040-expand"],
            }

    out.append("\n### Per-crisis (sleeve, clean) cum return + maxDD")
    out.append("```")
    out.append(crisis_multi(sleeve_series,
                            ["baseline", "VT10", "VT12", "6040tr", "6040ex"]))
    out.append("```")

    # ---- BLEND level (build_dashboard 60/20/20) ----
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

    def blend_metrics(art, bind=None):
        m = cpm_live.perf_metrics(art.blend, bcash)
        em = extra_metrics(art.blend, bcash)
        row = {
            "Sharpe": m["sharpe"], "Sortino": em["Sortino"],
            "CVaR95_d": em["CVaR95_daily"], "Calmar": m["calmar"],
            "Martin": m["martin"], "MaxDD": m["max_drawdown"],
            "CAGR": m["cagr"], "vol": m["vol"], "turnover": float("nan"),
            "bindfrac": float("nan"), "meanscale": float("nan"),
        }
        if bind is not None:
            row["bindfrac"] = bind["bind_frac"]
            row["meanscale"] = bind["mean_scale"]
        return row

    print("Building baseline blend ...")
    art_base = BD.build_artifacts(bpanel, ndx_panel, bstart, bend, include_records=False)

    _orig = cpm_live.compute_target_weights
    art_vt = {}
    for name, tf in CFG.items():
        print(f"Building blend {name} ...")
        cpm_live.compute_target_weights = make_vt_ctw(baseline_ret_ext, tf, 252)
        try:
            art_vt[name] = BD.build_artifacts(bpanel, ndx_panel, bstart, bend,
                                              include_records=False)
        finally:
            cpm_live.compute_target_weights = _orig

    brows = {"baseline (prod)": blend_metrics(art_base)}
    for name, tf in CFG.items():
        brows[name] = blend_metrics(art_vt[name],
                                    bind=bind_stats(baseline_ret_ext, sigs_clean, tf, 252))
    out.append(f"\n## BLEND 60/20/20 (clean {bstart.date()}..{bend.date()}) "
               "-- close-to-close T+1, 10bps; BULL+NDX identical")
    out.append("```")
    out.append(fmt_table(brows, order))
    out.append("```")
    out.append("\n### Per-crisis (blend, clean)")
    out.append("```")
    out.append(crisis_multi(
        {"baseline": art_base.blend,
         "VT10": art_vt["VT-10% (fixed)"].blend,
         "VT12": art_vt["VT-12% (fixed)"].blend,
         "6040tr": art_vt["VT-6040-trailing"].blend,
         "6040ex": art_vt["VT-6040-expand"].blend},
        ["baseline", "VT10", "VT12", "6040tr", "6040ex"]))
    out.append("```")

    report = "\n".join(out)
    print("\n" + report)
    rp = ROOT / "research" / "cpm_voltarget_paramfree_findings_raw.txt"
    rp.write_text(report)
    print(f"\n[written] {rp}")


if __name__ == "__main__":
    main()
