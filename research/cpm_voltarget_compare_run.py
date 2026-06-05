"""Exploratory backtest: CONTINUOUS VOL-TARGETING of the CPM sleeve.

HYPOTHESIS
----------
Scale the CPM RISKY block continuously toward a fixed annualized vol target
(10% and 12%), de-risk-only (cap scale at 1.0), routing the shed weight to the
prod safe asset. Compare against (a) prod CPM baseline and (b) the n_pos=4
drop-to-safe variant.

    scale  = min(1, target / rv_trailing)
    rv     = trailing realized vol of the BASELINE CPM SLEEVE daily returns,
             LAGGED to prior month-end (data up to sig_d only), 252d window
             (primary; 60d reported as sensitivity).

Applied monthly, T+1, 10 bps on changes. Selection / canary / ranker /
safe-selector are IDENTICAL to prod -- only the final risky weights are scaled
and the shed weight is routed to the prod safe asset (SHV/IEF best-of).

rv proxy: we use the unscaled (baseline prod) CPM sleeve daily returns to
estimate trailing vol, then scale. This is the standard non-recursive vol-target
construction and is PIT-clean (uses only returns realized before sig_d). The
same baseline sleeve series feeds both the sleeve and blend rv estimate.

RESEARCH-ONLY. Does not edit prod. Monkeypatches cpm_live.compute_target_weights
for the blend path; passes a variant weight_fn directly to the sleeve harness.

target=10% lightly de-risks (CPM full-period vol ~10.3%); target=12% is ABOVE
full-period vol so it should bind only in the highest-vol months. Bind frequency
(fraction of months scale<1) and mean scale are reported as effect size.
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
from cpm_live import RISKY_UNIVERSE, compute_target_weights
from research import cpm_harness as H
from research.cpm_npos4_droptosafe_run import (
    baseline_weight_fn,
    variant_weight_fn as droptosafe_weight_fn,
    variant_compute_target_weights as droptosafe_ctw,
    extra_metrics,
    turnover_avg,
    crisis_breakdown,
)


# --------------------------------------------------------------------------
# Vol-target core: scale the prod risky block by min(1, target/rv).
# rv = trailing window vol of baseline CPM sleeve daily returns, lagged.
# --------------------------------------------------------------------------
def _vt_scale(baseline_ret: pd.Series, sig_d: pd.Timestamp,
              target: float, window: int) -> float:
    """De-risk-only scale at sig_d. NaN-safe; 1.0 if insufficient history."""
    hist = baseline_ret.loc[baseline_ret.index <= sig_d]
    if len(hist) < window:
        return 1.0
    rv = hist.tail(window).std(ddof=0) * np.sqrt(252)
    if not np.isfinite(rv) or rv <= 0:
        return 1.0
    return float(min(1.0, target / rv))


def _vt_apply(out: dict, safe: str, scale: float) -> dict:
    """Scale risky weights by `scale`; route shed to safe asset."""
    if scale >= 1.0:
        return dict(out)
    new = {}
    shed = 0.0
    for t, w in out.items():
        if t in RISKY_UNIVERSE:
            new[t] = w * scale
            shed += w * (1.0 - scale)
        else:
            new[t] = w
    if shed > 0:
        new[safe] = new.get(safe, 0.0) + shed
    return new


def make_vt_weight_fn(baseline_ret: pd.Series, target: float, window: int):
    """Sleeve-harness weight_fn: (close, sig_d) -> dict."""
    def fn(close_panel, sig_d):
        out, _basket, _regime, safe = compute_target_weights(close_panel, sig_d)
        scale = _vt_scale(baseline_ret, sig_d, target, window)
        return _vt_apply(out, safe, scale)
    return fn


def make_vt_ctw(baseline_ret: pd.Series, target: float, window: int):
    """Blend monkeypatch: compute_target_weights-compatible tuple return."""
    def ctw(close_panel, sig_d, universe=None, safe_pool=None, canary_assets=None):
        out, basket, regime, safe = compute_target_weights(close_panel, sig_d)
        scale = _vt_scale(baseline_ret, sig_d, target, window)
        return _vt_apply(out, safe, scale), basket, regime, safe
    return ctw


# --------------------------------------------------------------------------
# Bind-frequency / effect size diagnostics.
# --------------------------------------------------------------------------
def bind_stats(baseline_ret, sigs, target, window) -> dict:
    scales = [_vt_scale(baseline_ret, d, target, window) for d in sigs]
    s = np.array(scales)
    bind = s < 1.0 - 1e-9
    return {
        "n_months": len(s),
        "bind_frac": float(bind.mean()) if len(s) else float("nan"),
        "mean_scale": float(s.mean()) if len(s) else float("nan"),
        "min_scale": float(s.min()) if len(s) else float("nan"),
        "mean_scale_when_bind": float(s[bind].mean()) if bind.any() else float("nan"),
    }


# --------------------------------------------------------------------------
# Metrics assembly.
# --------------------------------------------------------------------------
def full_metrics(returns, cash, close, sigs, weight_fn,
                 bind=None) -> dict:
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


def fmt_table(rows: dict, order: list) -> str:
    cols = ["Sharpe", "Sortino", "CVaR95_d", "Calmar", "Martin", "MaxDD",
            "CAGR", "vol", "turnover", "bindfrac", "meanscale"]
    head = "config".ljust(24) + "".join(c.rjust(11) for c in cols)
    lines = [head, "-" * len(head)]
    for name in order:
        m = rows[name]
        cells = []
        for c in cols:
            v = m[c]
            if isinstance(v, float) and np.isnan(v):
                cells.append("-".rjust(11))
            elif c in ("MaxDD", "CAGR", "vol", "CVaR95_d", "bindfrac"):
                cells.append(f"{v*100:.2f}%".rjust(11))
            else:
                cells.append(f"{v:.3f}".rjust(11))
        lines.append(name.ljust(24) + "".join(cells))
    return "\n".join(lines)


def crisis_multi(series_by_name: dict, names: list) -> str:
    """Per-crisis cum return + maxDD for multiple configs side by side."""
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
    head = "crisis".ljust(24) + "".join(f"{n[:9]}_ret".rjust(13) for n in names) \
        + "".join(f"{n[:9]}_DD".rjust(13) for n in names)
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
        line += "".join((f"{r*100:.2f}%".rjust(13) if np.isfinite(r) else "-".rjust(13)) for r in rets)
        line += "".join((f"{d*100:.2f}%".rjust(13) if np.isfinite(d) else "-".rjust(13)) for d in dds)
        lines.append(line)
    return "\n".join(lines)


def main():
    print("Loading harness data ...")
    data = H.load_data()
    cash = data.cash
    close = data.panel

    anc = H.verify_anchor(data=data)
    print(f"[ok] anchor Sharpe={anc['Sharpe']:.6f} MaxDD={anc['MaxDD']:.6f} "
          f"Calmar={anc['Calmar']:.6f}")

    # Baseline sleeve returns over EXT window -> rv proxy (full history for trailing vol).
    print("Computing baseline CPM sleeve returns (ext) for rv proxy ...")
    baseline_ret_ext = H.run_strategy(compute_target_weights, window="ext", data=data)

    TARGETS = {"VT-10% (252d)": (0.10, 252),
               "VT-12% (252d)": (0.12, 252),
               "VT-10% (60d)":  (0.10, 60)}

    vt_fns = {name: make_vt_weight_fn(baseline_ret_ext, t, w)
              for name, (t, w) in TARGETS.items()}

    out = []
    out.append("# CPM continuous vol-targeting (10% / 12%) vs baseline & drop-to-safe\n")
    out.append("rv = trailing vol of BASELINE CPM sleeve daily returns, lagged to "
               "sig_d (PIT-clean). scale = min(1, target/rv), de-risk-only. "
               "Shed weight routed to prod safe asset (SHV/IEF best-of).")

    # ---- bind frequency / effect size (clean window) ----
    midx = (pd.DataFrame({"x": 1}, index=close.index)
            .groupby(pd.Grouper(freq="ME")).tail(1).index)
    sigs_clean = midx[(midx >= data.clean_start) & (midx <= data.end)]
    binds = {name: bind_stats(baseline_ret_ext, sigs_clean, t, w)
             for name, (t, w) in TARGETS.items()}
    out.append(f"\n## Bind frequency / effect size (clean {data.clean_start.date()}"
               f"..{data.end.date()}, {len(sigs_clean)} months)")
    out.append("```")
    bh = "config".ljust(18) + "bind_frac".rjust(11) + "mean_scale".rjust(12) \
        + "min_scale".rjust(11) + "mean|bind".rjust(11)
    out.append(bh)
    out.append("-" * len(bh))
    for name, (t, w) in TARGETS.items():
        b = binds[name]
        out.append(name.ljust(18)
                   + f"{b['bind_frac']*100:.1f}%".rjust(11)
                   + f"{b['mean_scale']:.4f}".rjust(12)
                   + f"{b['min_scale']:.4f}".rjust(11)
                   + f"{b['mean_scale_when_bind']:.4f}".rjust(11))
    out.append("```")

    # ---- SLEEVE level (mooex harness), clean + ext ----
    sleeve_series = {}
    for win in ("clean", "ext"):
        start = data.clean_start if win == "clean" else data.ext_start
        sigs = midx[(midx >= start) & (midx <= data.end)]

        base_ret = H.run_strategy(baseline_weight_fn, window=win, data=data)
        dts_ret = H.run_strategy(droptosafe_weight_fn, window=win, data=data)
        vt_ret = {name: H.run_strategy(fn, window=win, data=data)
                  for name, fn in vt_fns.items()}

        rows = {
            "baseline (prod)": full_metrics(base_ret, cash, close, sigs, baseline_weight_fn),
            "drop-to-safe": full_metrics(dts_ret, cash, close, sigs, droptosafe_weight_fn),
        }
        for name, (t, w) in TARGETS.items():
            rows[name] = full_metrics(vt_ret[name], cash, close, sigs, vt_fns[name],
                                      bind=bind_stats(baseline_ret_ext, sigs, t, w))
        order = ["baseline (prod)", "drop-to-safe",
                 "VT-10% (252d)", "VT-12% (252d)", "VT-10% (60d)"]
        out.append(f"\n## SLEEVE ({win}) -- mooex T+1, 10bps")
        out.append("```")
        out.append(fmt_table(rows, order))
        out.append("```")
        if win == "clean":
            sleeve_series = {
                "baseline": base_ret, "drop2safe": dts_ret,
                "VT10_252": vt_ret["VT-10% (252d)"],
                "VT12_252": vt_ret["VT-12% (252d)"],
            }

    out.append("\n### Per-crisis (sleeve, clean) cum return + maxDD")
    out.append("```")
    out.append(crisis_multi(sleeve_series,
                            ["baseline", "drop2safe", "VT10_252", "VT12_252"]))
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
            row["bindfrac"] = bind["bind_frac"]; row["meanscale"] = bind["mean_scale"]
        return row

    print("Building baseline blend ...")
    art_base = BD.build_artifacts(bpanel, ndx_panel, bstart, bend, include_records=False)

    print("Building drop-to-safe blend ...")
    _orig = cpm_live.compute_target_weights
    cpm_live.compute_target_weights = droptosafe_ctw
    try:
        art_dts = BD.build_artifacts(bpanel, ndx_panel, bstart, bend, include_records=False)
    finally:
        cpm_live.compute_target_weights = _orig

    art_vt = {}
    for name, (t, w) in TARGETS.items():
        print(f"Building blend {name} ...")
        cpm_live.compute_target_weights = make_vt_ctw(baseline_ret_ext, t, w)
        try:
            art_vt[name] = BD.build_artifacts(bpanel, ndx_panel, bstart, bend,
                                              include_records=False)
        finally:
            cpm_live.compute_target_weights = _orig

    brows = {
        "baseline (prod)": blend_metrics(art_base),
        "drop-to-safe": blend_metrics(art_dts),
    }
    for name, (t, w) in TARGETS.items():
        brows[name] = blend_metrics(art_vt[name],
                                    bind=bind_stats(baseline_ret_ext, sigs_clean, t, w))
    order = ["baseline (prod)", "drop-to-safe",
             "VT-10% (252d)", "VT-12% (252d)", "VT-10% (60d)"]
    out.append(f"\n## BLEND 60/20/20 (clean {bstart.date()}..{bend.date()}) "
               "-- close-to-close T+1, 10bps; BULL+NDX identical")
    out.append("```")
    out.append(fmt_table(brows, order))
    out.append("```")
    out.append("\n### Per-crisis (blend, clean)")
    out.append("```")
    out.append(crisis_multi(
        {"baseline": art_base.blend, "drop2safe": art_dts.blend,
         "VT10_252": art_vt["VT-10% (252d)"].blend,
         "VT12_252": art_vt["VT-12% (252d)"].blend},
        ["baseline", "drop2safe", "VT10_252", "VT12_252"]))
    out.append("```")

    report = "\n".join(out)
    print("\n" + report)
    rp = ROOT / "research" / "cpm_voltarget_compare_findings_raw.txt"
    rp.write_text(report)
    print(f"\n[written] {rp}")


if __name__ == "__main__":
    main()
