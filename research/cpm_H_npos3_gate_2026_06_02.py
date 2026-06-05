"""Exploratory backtest: CPM low-breadth gate refinements focused on n_pos=3.

RESEARCH-ONLY. Does not edit prod. Reuses canonical harness (mooex T+1,
both-252, 10 bps/side). Reproduces the 1.255673 anchor gate.

Configs (only n_pos in {1,2,3} ever change; n_pos=4 = min-var-3-of-4 @ 33.3%,
n_pos=0 / canary-off = 100% safe, BIT-IDENTICAL across all configs):

  curve = risky_fraction by n_pos in {1,2,3,4}; n3_mode = selection at n_pos=3
    holdall  -> 3 positives equal-weight, split risky_fraction over 3
    minvar2  -> min-var 2-of-3 (C(3,2)=3 equal-weight pairs), split over 2

  A  (anchor):  holdall  curve 25/50/75/100   -> MUST reproduce 1.255673
  F  (ref):     holdall  curve  0/ 0/50/100
  H1:           holdall  curve  0/ 0/75/100   (== A at n_pos=3; differs n_pos<=2)
  H2:           minvar2  curve 25/50/75/100   (== A except n_pos=3 selection)
  H3:           minvar2  curve  0/ 0/75/100

BLEND fix: patch build_dashboard.compute_target_weights (BD imports the symbol
into its OWN namespace; patching cpm_live.* alone silently measures prod A on
the blend rows). Patch both for safety.
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
from cpm_live import (
    RISKY_UNIVERSE, SAFE_POOL, CANARY_ASSETS, CANARY_RULE,
    TOP_K_CANDIDATES, CORR_LOOKBACK_DAYS,
    best_safe, sig_13612U, faber_sma_xs, _min_var_subset,
    compute_target_weights,
)
from research import cpm_harness as H


# config -> (curve dict, n3_mode)
CONFIGS = {
    "A":  ({1: 0.25, 2: 0.50, 3: 0.75, 4: 1.0}, "holdall"),
    "F":  ({1: 0.00, 2: 0.00, 3: 0.50, 4: 1.0}, "holdall"),
    "H1": ({1: 0.00, 2: 0.00, 3: 0.75, 4: 1.0}, "holdall"),
    "H2": ({1: 0.25, 2: 0.50, 3: 0.75, 4: 1.0}, "minvar2"),
    "H3": ({1: 0.00, 2: 0.00, 3: 0.75, 4: 1.0}, "minvar2"),
}
ORDER = ["A", "F", "H1", "H2", "H3"]


def _core(close_panel, sig_d, cfg: str):
    """Faithful copy of compute_target_weights with parameterized n_pos gate.

    Returns (weights, basket, regime, safe, n_pos). n_pos=None unless RISK_ON.
    Selection (min-var 3-of-4 at n_pos=4), canary, ranker, safe-selector are
    IDENTICAL to prod across all configs.
    """
    curve, n3_mode = CONFIGS[cfg]
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
        return {safe: 1.0}, None, "DEFENSIVE", safe, None
    n_canary_pos = sum(1 for s in canary_scores if s > 0)
    if CANARY_RULE == "any_positive":
        if n_canary_pos == 0:
            return {safe: 1.0}, None, "DEFENSIVE", safe, None
    elif CANARY_RULE == "all_positive":
        if n_canary_pos < len(canary_scores):
            return {safe: 1.0}, None, "DEFENSIVE", safe, None
    else:
        if n_canary_pos <= len(canary_scores) // 2:
            return {safe: 1.0}, None, "DEFENSIVE", safe, None

    faber = faber_sma_xs(monthly)
    avail = [t for t in universe
             if t in faber.index and pd.notna(faber[t])
             and pd.notna(close_panel.loc[sig_d].get(t, np.nan) if sig_d in close_panel.index else np.nan)]
    if not avail:
        return {safe: 1.0}, None, "DEFENSIVE", safe, None

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
        return {safe: 1.0}, None, "DEFENSIVE", safe, None

    positive_picks = list(positive.index)
    n_pos = len(positive_picks)
    if n_pos == 4:
        picks = _min_var_subset(close_panel, sig_d, positive_picks, CORR_LOOKBACK_DAYS, 3)
    elif n_pos == 3 and n3_mode == "minvar2":
        picks = _min_var_subset(close_panel, sig_d, positive_picks, CORR_LOOKBACK_DAYS, 2)
    else:
        picks = positive_picks

    risky_fraction = curve[min(n_pos, 4)]
    safe_fraction = 1.0 - risky_fraction

    risky_w = {t: 1.0 / len(picks) for t in picks}
    out = {t: w * risky_fraction for t, w in risky_w.items()}
    if safe_fraction > 0:
        out[safe] = out.get(safe, 0.0) + safe_fraction

    return out, tuple(picks), "RISK_ON", safe, n_pos


def weight_fn_for(cfg: str):
    def _wf(close_panel, sig_d):
        out, *_ = _core(close_panel, sig_d, cfg)
        return out
    return _wf


def ctw_for(cfg: str):
    def _ctw(close_panel, sig_d, universe=None, safe_pool=None, canary_assets=None):
        out, basket, regime, safe, _ = _core(close_panel, sig_d, cfg)
        return out, basket, regime, safe
    return _ctw


# ----- gates -----
def _signal_dates(close, start, end):
    midx = (pd.DataFrame({"x": 1}, index=close.index)
            .groupby(pd.Grouper(freq="ME")).tail(1).index)
    return midx[(midx >= start) & (midx <= end)]


def verify_baseline_matches_prod(data) -> None:
    sigs = _signal_dates(data.panel, data.clean_start, data.end)
    close = data.panel
    max_diff = 0.0
    for sig_d in sigs:
        prod, *_ = compute_target_weights(close, sig_d)
        mine, *_ = _core(close, sig_d, "A")
        for k in set(prod) | set(mine):
            max_diff = max(max_diff, abs(prod.get(k, 0.0) - mine.get(k, 0.0)))
    if max_diff > 1e-12:
        raise AssertionError(f"A replica != prod, max weight diff {max_diff:.2e}")
    print(f"[ok] A replica matches prod (max weight diff {max_diff:.2e})")


def isolation_matrix(close, sigs) -> str:
    """For each config vs A: report worst diff at n_pos in {1,2,3,4} and which differ."""
    lines = ["config".ljust(6) + "n1diff".rjust(10) + "n2diff".rjust(10)
             + "n3diff".rjust(10) + "n4diff".rjust(10) + "  changed_npos"]
    lines.append("-" * len(lines[0]))
    # cache A outputs
    a_cache = {}
    for sig_d in sigs:
        a_cache[sig_d] = _core(close, sig_d, "A")
    for cfg in ORDER:
        worst = {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0}
        for sig_d in sigs:
            a_out, _, _, _, n_pos = a_cache[sig_d]
            if n_pos is None:
                # canary-off / defensive: must be identical
                c_out, _, _, _, _ = _core(close, sig_d, cfg)
                d = max(abs(a_out.get(k, 0.0) - c_out.get(k, 0.0)) for k in set(a_out) | set(c_out))
                if d > 1e-12:
                    lines.append(f"!! {cfg} defensive month {sig_d.date()} diff {d:.2e}")
                continue
            c_out, _, _, _, _ = _core(close, sig_d, cfg)
            d = max(abs(a_out.get(k, 0.0) - c_out.get(k, 0.0)) for k in set(a_out) | set(c_out))
            worst[n_pos] = max(worst[n_pos], d)
        changed = [k for k in (1, 2, 3, 4) if worst[k] > 1e-12]
        lines.append(cfg.ljust(6)
                     + f"{worst[1]:.2e}".rjust(10) + f"{worst[2]:.2e}".rjust(10)
                     + f"{worst[3]:.2e}".rjust(10) + f"{worst[4]:.2e}".rjust(10)
                     + "  " + str(changed))
    return "\n".join(lines)


def selection_dump(close, months: list[str]) -> str:
    """At named months: positives (hold-all-3) and min-var-2-of-3 picks."""
    lines = ["month".ljust(9) + "n_pos".rjust(6) + "  positives(holdall-3)".ljust(34)
             + "minvar-2-of-3".ljust(20) + "dropped"]
    lines.append("-" * len(lines[0]))
    sigs_all = _signal_dates(close, close.index[0], close.index[-1])
    by_ym = {d.strftime("%Y-%m"): d for d in sigs_all}
    for ym in months:
        sig_d = by_ym.get(ym)
        if sig_d is None:
            lines.append(ym.ljust(9) + "  (no signal date)")
            continue
        out, basket, regime, safe, n_pos = _core(close, sig_d, "A")
        if regime != "RISK_ON":
            lines.append(ym.ljust(9) + f"  DEFENSIVE (safe={safe})")
            continue
        positives = list(basket)
        if n_pos == 3:
            mv2 = _min_var_subset(close, sig_d, positives, CORR_LOOKBACK_DAYS, 2)
            dropped = [t for t in positives if t not in mv2]
        else:
            mv2 = ["n/a (n_pos!=3)"]
            dropped = []
        lines.append(ym.ljust(9) + str(n_pos).rjust(6) + "  "
                     + ",".join(positives).ljust(32)
                     + ",".join(mv2).ljust(20) + ",".join(dropped))
    return "\n".join(lines)


# ----- metrics -----
def extra_metrics(daily: pd.Series) -> dict:
    d = daily.dropna()
    downside = d[d < 0]
    dd_std = downside.std(ddof=0) * np.sqrt(252)
    sortino = (d.mean() * 252) / dd_std if dd_std > 0 else float("nan")
    return {"Sortino": sortino}


def full_metrics(returns, cash) -> dict:
    m = cpm_live.perf_metrics(returns, cash)
    em = extra_metrics(returns)
    return {
        "Sharpe": m["sharpe"], "Sortino": em["Sortino"], "MaxDD": m["max_drawdown"],
        "Calmar": m["calmar"], "Martin": m["martin"], "CAGR": m["cagr"],
    }


def fmt_table(rows: dict, cols: list, pct_cols: set) -> str:
    head = "config".ljust(8) + "".join(c.rjust(11) for c in cols)
    lines = [head, "-" * len(head)]
    for name in ORDER:
        if name not in rows:
            continue
        m = rows[name]
        cells = []
        for c in cols:
            v = m[c]
            cells.append((f"{v*100:.2f}%" if c in pct_cols else f"{v:.4f}").rjust(11))
        lines.append(name.ljust(8) + "".join(cells))
    return "\n".join(lines)


CRISES = {
    "GFC 2008 (07-09..09-03)": ("2007-09-01", "2009-03-31"),
    "  V-recov 2009 (09-03..09-12)": ("2009-03-01", "2009-12-31"),
    "Euro 2011 (11-05..11-10)": ("2011-05-01", "2011-10-31"),
    "COVID 2020 (20-02..20-04)": ("2020-02-01", "2020-04-30"),
    "  V-recov 2020-04 (20-04..20-08)": ("2020-04-01", "2020-08-31"),
    "2022 bear (22-01..22-10)": ("2022-01-01", "2022-10-31"),
    "2025 tariff (25-02..25-05)": ("2025-02-01", "2025-05-22"),
}


def crisis_table(rets: dict) -> str:
    def cum(x): return (1 + x).prod() - 1
    def mdd(x):
        eq = (1 + x).cumprod()
        return (eq / eq.cummax() - 1).min()
    cfgs = [c for c in ORDER if c in rets]
    head = "crisis".ljust(32) + "".join((c + "_ret").rjust(10) for c in cfgs) \
        + "".join((c + "_DD").rjust(10) for c in cfgs)
    lines = [head, "-" * len(head)]
    for name, (s, e) in CRISES.items():
        cells_ret, cells_dd = [], []
        ok = True
        for c in cfgs:
            w = rets[c].loc[(rets[c].index >= s) & (rets[c].index <= e)]
            if w.empty:
                ok = False
                break
            cells_ret.append(f"{cum(w)*100:.2f}%".rjust(10))
            cells_dd.append(f"{mdd(w)*100:.2f}%".rjust(10))
        if not ok:
            lines.append(name.ljust(32) + "n/a (outside window)")
            continue
        lines.append(name.ljust(32) + "".join(cells_ret) + "".join(cells_dd))
    return "\n".join(lines)


def main():
    print("Loading harness data ...")
    data = H.load_data()
    cash = data.cash
    close = data.panel

    anc = H.verify_anchor(data=data)
    print(f"[ok] anchor Sharpe={anc['Sharpe']:.6f} MaxDD={anc['MaxDD']:.6f} "
          f"Calmar={anc['Calmar']:.6f}")
    verify_baseline_matches_prod(data)

    out = []
    out.append("# CPM low-breadth gate refinements (n_pos=3 focus) -- exploratory\n")
    out.append(f"Anchor gate: Sharpe={anc['Sharpe']:.6f} (target 1.255673), "
               f"MaxDD={anc['MaxDD']*100:.4f}%, Calmar={anc['Calmar']:.6f}")

    sigs_clean = _signal_dates(close, data.clean_start, data.end)
    out.append("\n## GATE: isolation vs A (clean window, worst weight diff by n_pos)")
    out.append("```")
    out.append(isolation_matrix(close, sigs_clean))
    out.append("```")
    out.append("Expected: n4diff=0 all; A row all 0; H1 changes {1,2}; "
               "F changes {1,2,3}; H2 changes {3}; H3 changes {1,2,3}.")

    out.append("\n## n_pos=3 selection dump (min-var-2-of-3 vs hold-all-3)")
    out.append("```")
    out.append(selection_dump(close, ["2009-04", "2020-04",
                                      "2008-06", "2008-07", "2008-08"]))
    out.append("```")

    # ---- SLEEVE level ----
    sleeve_rets = {"clean": {}, "ext": {}}
    for win in ("clean", "ext"):
        start = data.clean_start if win == "clean" else data.ext_start
        rows = {}
        for cfg in ORDER:
            r = H.run_strategy(weight_fn_for(cfg), window=win, data=data)
            sleeve_rets[win][cfg] = r
            rows[cfg] = full_metrics(r, cash)
        out.append(f"\n## SLEEVE ({win}) -- mooex T+1, 10bps")
        out.append("```")
        out.append(fmt_table(rows, ["Sharpe", "Sortino", "MaxDD", "Calmar",
                                    "Martin", "CAGR"], {"MaxDD", "CAGR"}))
        out.append("```")

    out.append("\n### Per-crisis sleeve (EXT window) cum return + maxDD")
    out.append("```")
    out.append(crisis_table(sleeve_rets["ext"]))
    out.append("```")

    # ---- BLEND 60/20/20 ----
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
        print(f"  NDX panel unavailable ({e}); blend CPM+BULL only.")
        ndx_panel = None
    bstart = data.clean_start

    def blend_metrics(art):
        m = cpm_live.perf_metrics(art.blend, bcash)
        return {"Sharpe": m["sharpe"], "MaxDD": m["max_drawdown"], "CAGR": m["cagr"]}

    brows = {}
    _orig_bd = BD.compute_target_weights
    _orig_cl = cpm_live.compute_target_weights
    for cfg in ORDER:
        print(f"Building blend {cfg} (BD.compute_target_weights patched) ...")
        ctw = ctw_for(cfg)
        BD.compute_target_weights = ctw
        cpm_live.compute_target_weights = ctw
        try:
            art = BD.build_artifacts(bpanel, ndx_panel, bstart, bend, include_records=False)
        finally:
            BD.compute_target_weights = _orig_bd
            cpm_live.compute_target_weights = _orig_cl
        brows[cfg] = blend_metrics(art)

    out.append(f"\n## BLEND 60/20/20 (clean {bstart.date()}..{bend.date()}) "
               "-- BD.compute_target_weights patched per config; BULL+NDX identical")
    out.append("```")
    out.append(fmt_table(brows, ["Sharpe", "MaxDD", "CAGR"], {"MaxDD", "CAGR"}))
    out.append("```")

    report = "\n".join(out)
    print("\n" + report)
    rp = ROOT / "research" / "cpm_H_npos3_gate_2026_06_02_raw.txt"
    rp.write_text(report)
    print(f"\n[written] {rp}")


if __name__ == "__main__":
    main()
