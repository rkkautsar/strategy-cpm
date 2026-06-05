"""ADOPTION-GATE CONFIRM: paired block bootstrap + 3-segment walk-forward for the
CPM continuous vol-target with the PARAMETER-FREE EXPANDING-60/40 anchor
(VT-6040-expand) vs the prod baseline.

WHY
---
Point estimates (blend, clean) showed only MODEST gains for VT-6040-expand vs
baseline (Sharpe +0.015, Calmar +0.14, Martin +0.12, MaxDD -1.4pp). All small
and plausibly inside noise. Before any adoption talk we must decide whether the
edge is (a) STATISTICALLY ROBUST (bootstrap CI / p) and (b) OOS-STABLE
(beat-or-tie across contiguous walk-forward segments, not one-segment luck), and
(c) whether expanding-60/40 tracks fixed VT-10 (parameter-free equivalence).

CANDIDATE MECHANISM (settled, implementable -- monthly / lagged / T+1 / 10bps):
  CPM de-risk = EW risky block, continuous de-risk-only scale = min(1, target/rv_CPM),
  shed -> safe. SELECTION unchanged (prod compute_target_weights).
  rv_CPM = trailing 252d baseline CPM sleeve vol (lagged, PIT-clean).
  TARGET (VT-6040-expand) = expanding-window mean of completed-month realized vol
  of a 60/40 portfolio (0.6*SPY + 0.4*IEF). Empirically pins ~9.8-10% == the
  parameter-free equivalent of fixed VT-10.
  Cross-check config = fixed VT-10%.

METHOD
------
1. PAIRED BLOCK BOOTSTRAP (B=2000, block=21, seed=42) via
   research.cpm_bootstrap_multimetric.paired_block_bootstrap_mm. VT MINUS
   baseline, paired on the SAME return path. Classification metrics with clean
   CIs: dSharpe, dSortino, dCVaR. Path-dependent context (SOFT CIs, do not
   classify): dCalmar, dMartin, dMaxDD. Run at SLEEVE and BLEND. Both
   VT-6040-expand and fixed VT-10 vs baseline.
2. 3-SEGMENT WALK-FORWARD: split the CLEAN window (2008-05-30..end) into 3
   contiguous equal-calendar segments. Per segment report Sharpe / Martin /
   MaxDD / CAGR for baseline, VT-6040-expand, VT-10 (sleeve + blend). Tests
   whether VT beats-or-ties baseline in ALL segments vs one-segment edge.

RESEARCH-ONLY. Reuses cpm_harness sleeve engine, paramfree helpers, and
build_dashboard build_artifacts for the blend (monkeypatched compute_target_weights).
Cached frozen dataset; deltas are apples-to-apples, paired on identical paths.
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
from research.cpm_npos4_droptosafe_run import baseline_weight_fn
from research.cpm_voltarget_paramfree_run import (
    bench_6040_returns,
    make_fixed_target,
    make_expanding_target,
    make_vt_weight_fn,
    make_vt_ctw,
    bind_stats,
)
from research.cpm_bootstrap_multimetric import paired_block_bootstrap_mm

B = 2000
BLOCK = 21
SEED = 42


# --------------------------------------------------------------------------
# Metric helpers
# --------------------------------------------------------------------------
def seg_metrics(ret: pd.Series, cash: pd.Series) -> dict:
    m = cpm_live.perf_metrics(ret, cash)
    return {
        "Sharpe": m.get("sharpe", float("nan")),
        "Martin": m.get("martin", float("nan")),
        "MaxDD": m.get("max_drawdown", float("nan")),
        "CAGR": m.get("cagr", float("nan")),
        "n": len(ret),
    }


def fmt_boot_block(title, res: dict) -> list[str]:
    out = [f"\n## {title}"]
    out.append("```")
    hdr = ("metric".ljust(10) + "delta".rjust(10) + "ci_lo".rjust(10)
           + "ci_hi".rjust(10) + "p(VT>base)".rjust(12) + "  note")
    out.append(hdr)
    out.append("-" * len(hdr))
    rows = [
        ("Sharpe", "dSharpe", "CLEAN CI -> classify"),
        ("Sortino", "dSortino", "CLEAN CI -> classify"),
        ("CVaR95", "dCVaR", "CLEAN CI -> classify"),
        ("Calmar", "dCalmar", "SOFT CI (path-dep)"),
        ("Martin", "dMartin", "SOFT CI (path-dep)"),
        ("MaxDD", "dMaxDD", "SOFT CI (path-dep)"),
    ]
    for label, key, note in rows:
        s = res[key]
        out.append(label.ljust(10)
                   + f"{s['mean']:+.4f}".rjust(10)
                   + f"{s['ci_lo']:+.4f}".rjust(10)
                   + f"{s['ci_hi']:+.4f}".rjust(10)
                   + f"{s['p_gt0']*100:.1f}%".rjust(12)
                   + "  " + note)
    out.append("```")
    out.append("(p(VT>base) = bootstrap fraction of delta>0. For MaxDD, delta>0 "
               "means VT LESS-NEGATIVE = shallower DD = better.)")
    return out


def wf_table(seg_bounds, series_by_name, names, cash, level) -> list[str]:
    out = [f"\n## 3-segment walk-forward -- {level}"]
    for si, (lo, hi) in enumerate(seg_bounds, 1):
        out.append(f"\n### Segment {si}: {lo.date()}..{hi.date()}")
        out.append("```")
        hdr = ("config".ljust(20) + "Sharpe".rjust(9) + "Martin".rjust(9)
               + "MaxDD".rjust(9) + "CAGR".rjust(9) + "ndays".rjust(8))
        out.append(hdr)
        out.append("-" * len(hdr))
        base_m = None
        for nm in names:
            s = series_by_name[nm]
            seg = s.loc[(s.index >= lo) & (s.index <= hi)]
            mm = seg_metrics(seg, cash)
            if nm == names[0]:
                base_m = mm
            tag = ""
            if base_m is not None and nm != names[0]:
                d_sh = mm["Sharpe"] - base_m["Sharpe"]
                d_mt = mm["Martin"] - base_m["Martin"]
                sh_ok = d_sh >= -0.02
                mt_ok = d_mt >= -0.05
                tag = "  [Sh " + ("ok" if sh_ok else "WORSE") + \
                      " | Mt " + ("ok" if mt_ok else "WORSE") + "]"
            out.append(nm.ljust(20)
                       + f"{mm['Sharpe']:.3f}".rjust(9)
                       + f"{mm['Martin']:.3f}".rjust(9)
                       + f"{mm['MaxDD']*100:.2f}%".rjust(9)
                       + f"{mm['CAGR']*100:.2f}%".rjust(9)
                       + f"{mm['n']}".rjust(8)
                       + tag)
        out.append("```")
    out.append("([Sh ok] = VT Sharpe within 0.02 of (or above) baseline; "
               "[Mt ok] = VT Martin within 0.05. WORSE = VT loses materially "
               "in that segment.)")
    return out


def main():
    print("Loading harness data ...")
    data = H.load_data()
    cash = data.cash
    close = data.panel

    anc = H.verify_anchor(data=data)
    print(f"[ok] anchor Sharpe={anc['Sharpe']:.6f} MaxDD={anc['MaxDD']:.6f} "
          f"Calmar={anc['Calmar']:.6f}")

    print("Computing baseline CPM sleeve returns (ext) for rv_CPM ...")
    baseline_ret_ext = H.run_strategy(compute_target_weights, window="ext", data=data)

    b6040 = bench_6040_returns(close)
    print(f"60/40 bench: {b6040.index[0].date()}..{b6040.index[-1].date()} "
          f"({len(b6040)}d), full-period vol "
          f"{b6040.std(ddof=0)*np.sqrt(252)*100:.2f}%")

    CFG = {
        "VT-6040-expand": make_expanding_target(b6040),
        "VT-10% (fixed)": make_fixed_target(0.10),
    }
    vt_fns = {nm: make_vt_weight_fn(baseline_ret_ext, tf, 252)
              for nm, tf in CFG.items()}

    out = []
    out.append("# CPM expanding-60/40 vol-target: ADOPTION-GATE CONFIRM")
    out.append(f"\nbootstrap: PAIRED BLOCK B={B} block={BLOCK} seed={SEED}; "
               "VT MINUS baseline, paired on identical path.")
    out.append("mechanism: scale=min(1,target/rv_CPM) de-risk-only shed->safe, "
               "monthly/lagged/T+1/10bps; SELECTION = prod (unchanged).")
    out.append("rv_CPM = trailing 252d baseline CPM sleeve vol. "
               "VT-6040-expand target = expanding-mean completed-month 60/40 RV. "
               "VT-10 = fixed cross-check.")

    # ---- SLEEVE returns (clean) ----
    print("Building sleeve returns (clean) ...")
    base_sleeve = H.run_strategy(baseline_weight_fn, window="clean", data=data)
    vt_sleeve = {nm: H.run_strategy(fn, window="clean", data=data)
                 for nm, fn in vt_fns.items()}

    # bind diagnostics (clean months)
    midx = (pd.DataFrame({"x": 1}, index=close.index)
            .groupby(pd.Grouper(freq="ME")).tail(1).index)
    sigs_clean = midx[(midx >= data.clean_start) & (midx <= data.end)]
    out.append(f"\n## Bind diagnostics (clean {data.clean_start.date()}.."
               f"{data.end.date()}, {len(sigs_clean)} months)")
    out.append("```")
    bh = "config".ljust(20) + "bind_frac".rjust(11) + "mean_scl".rjust(10) + "meanTgt".rjust(10)
    out.append(bh)
    out.append("-" * len(bh))
    for nm, tf in CFG.items():
        b = bind_stats(baseline_ret_ext, sigs_clean, tf, 252)
        out.append(nm.ljust(20)
                   + f"{b['bind_frac']*100:.1f}%".rjust(11)
                   + f"{b['mean_scale']:.4f}".rjust(10)
                   + f"{b['mean_target']*100:.2f}%".rjust(10))
    out.append("```")

    # ---- SLEEVE bootstrap ----
    out.append("\n# BOOTSTRAP (a)")
    for nm in CFG:
        print(f"Bootstrap SLEEVE {nm} vs baseline ...")
        res = paired_block_bootstrap_mm(vt_sleeve[nm], base_sleeve, cash,
                                        B=B, block=BLOCK, seed=SEED)
        out += fmt_boot_block(f"SLEEVE bootstrap: {nm} - baseline", res)

    # ---- BLEND artifacts (clean) ----
    print("Building blend artifacts (clean) ...")
    import build_dashboard as BD
    from cpm_live import load_panel
    bpanel = load_panel(start=pd.Timestamp("1995-01-01"), end=data.end, live=True)
    bend = min(data.end, bpanel.index[-1])
    bcash = bpanel["SHV"].ffill().pct_change().dropna()
    try:
        from ndx_sleeve_live import load_ndx_panel
        ndx_panel = load_ndx_panel()
    except Exception as e:
        print(f"  NDX panel unavailable ({e}); blend = CPM+BULL only.")
        ndx_panel = None
    bstart = data.clean_start

    art_base = BD.build_artifacts(bpanel, ndx_panel, bstart, bend, include_records=False)
    _orig = cpm_live.compute_target_weights
    blend_series = {"baseline (prod)": art_base.blend}
    for nm, tf in CFG.items():
        print(f"Building blend {nm} ...")
        cpm_live.compute_target_weights = make_vt_ctw(baseline_ret_ext, tf, 252)
        try:
            art = BD.build_artifacts(bpanel, ndx_panel, bstart, bend,
                                     include_records=False)
        finally:
            cpm_live.compute_target_weights = _orig
        blend_series[nm] = art.blend

    # ---- BLEND bootstrap (DECISION LEVEL) ----
    out.append("\n# BOOTSTRAP -- BLEND (DECISION LEVEL)")
    for nm in CFG:
        print(f"Bootstrap BLEND {nm} vs baseline ...")
        res = paired_block_bootstrap_mm(blend_series[nm],
                                        blend_series["baseline (prod)"], bcash,
                                        B=B, block=BLOCK, seed=SEED)
        out += fmt_boot_block(f"BLEND bootstrap: {nm} - baseline", res)

    # ---- 3-SEGMENT WALK-FORWARD (b)/(c) ----
    out.append("\n# WALK-FORWARD (b)/(c) -- 3 contiguous equal-calendar segments")
    # segment boundaries on the clean span (use sleeve baseline index span)
    span_lo = base_sleeve.index[0]
    span_hi = base_sleeve.index[-1]
    total_days = (span_hi - span_lo).days
    b1 = span_lo + pd.Timedelta(days=total_days // 3)
    b2 = span_lo + pd.Timedelta(days=2 * total_days // 3)
    seg_bounds = [
        (span_lo, b1),
        (b1 + pd.Timedelta(days=1), b2),
        (b2 + pd.Timedelta(days=1), span_hi),
    ]
    out.append(f"\nclean span {span_lo.date()}..{span_hi.date()} "
               f"({total_days} days) split into thirds:")
    for i, (lo, hi) in enumerate(seg_bounds, 1):
        out.append(f"  seg{i}: {lo.date()}..{hi.date()}")

    sleeve_names = ["baseline", "VT-6040-expand", "VT-10% (fixed)"]
    sleeve_by_name = {"baseline": base_sleeve,
                      "VT-6040-expand": vt_sleeve["VT-6040-expand"],
                      "VT-10% (fixed)": vt_sleeve["VT-10% (fixed)"]}
    out += wf_table(seg_bounds, sleeve_by_name, sleeve_names, cash, "SLEEVE")

    blend_names = ["baseline (prod)", "VT-6040-expand", "VT-10% (fixed)"]
    out += wf_table(seg_bounds, blend_series, blend_names, bcash, "BLEND")

    report = "\n".join(out)
    print("\n" + report)
    rp = ROOT / "research" / "cpm_voltarget_expand6040_confirm_findings_raw.txt"
    rp.write_text(report)
    print(f"\n[written] {rp}")


if __name__ == "__main__":
    main()
