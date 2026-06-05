"""Exploratory backtest: isolate the min-var 3-of-4 selection value at n_pos=4.

RESEARCH-ONLY. Does not edit prod, does not commit. Reuses canonical harness
(mooex T+1, both-252, 10 bps/side). Reproduces the 1.255673 anchor gate.

Min-var ONLY actively selects at n_pos=4 (picks 3-of-4). At n_pos<=3 all
positives are held (min-var-3-of-3 = hold all). So every config below is
BIT-IDENTICAL to A at n_pos in {1,2,3} and n_pos=0 / canary-off. They differ
from A ONLY at n_pos=4. Curve = A's 25/50/75/100 in all configs.

Configs (only the n_pos=4 selection differs):
  A  (anchor):  min-var 3-of-4 @ 33.3% each   -> MUST reproduce 1.255673
  K1:           hold ALL 4 positives @ 25% each (no selection, full breadth)
  K2:           plain TOP-3 by faber/vol momentum score @ 33.3% each
                (drops the 4th-ranked by momentum; no min-var)

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


# config -> n4_mode (selection at n_pos=4). Curve is A's 25/50/75/100 for all.
CONFIGS = {
    "A":  "minvar3",   # min-var 3-of-4 @ 33.3%
    "K1": "holdall4",  # hold all 4 @ 25%
    "K2": "top3",      # momentum top-3 @ 33.3%
}
ORDER = ["A", "K1", "K2"]


def _select_npos4(close_panel, sig_d, positive_picks, mode):
    """positive_picks is in DESCENDING vol-adj-faber score order (from ranker)."""
    if mode == "minvar3":
        return _min_var_subset(close_panel, sig_d, positive_picks, CORR_LOOKBACK_DAYS, 3)
    if mode == "holdall4":
        return list(positive_picks)
    if mode == "top3":
        return list(positive_picks)[:3]
    raise ValueError(mode)


def _core(close_panel, sig_d, cfg: str):
    """Faithful copy of compute_target_weights with parameterized n_pos=4 select.

    Returns (weights, basket, regime, safe, n_pos). n_pos=None unless RISK_ON.
    Canary, ranker, safe-selector, and the n_pos<=3 path are IDENTICAL to prod
    across all configs (curve = prod min(n_pos,4)/4).
    """
    n4_mode = CONFIGS[cfg]
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

    positive_picks = list(positive.index)  # descending score order
    n_pos = len(positive_picks)
    if n_pos == 4:
        picks = _select_npos4(close_panel, sig_d, positive_picks, n4_mode)
    else:
        picks = positive_picks  # n_pos<=3: hold all (prod behavior)

    risky_fraction = min(n_pos, 4) / 4.0
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
    """For each config vs A: worst weight diff at n_pos in {1,2,3,4} + which differ.

    Expectation: ALL diffs at n_pos in {1,2,3} and defensive == 0; only n4diff>0.
    """
    lines = ["config".ljust(6) + "n1diff".rjust(10) + "n2diff".rjust(10)
             + "n3diff".rjust(10) + "n4diff".rjust(10) + "  changed_npos"]
    lines.append("-" * len(lines[0]))
    a_cache = {sig_d: _core(close, sig_d, "A") for sig_d in sigs}
    for cfg in ORDER:
        worst = {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0}
        for sig_d in sigs:
            a_out, _, _, _, n_pos = a_cache[sig_d]
            c_out, _, _, _, _ = _core(close, sig_d, cfg)
            d = max(abs(a_out.get(k, 0.0) - c_out.get(k, 0.0)) for k in set(a_out) | set(c_out))
            if n_pos is None:
                if d > 1e-12:
                    lines.append(f"!! {cfg} defensive month {sig_d.date()} diff {d:.2e}")
                continue
            worst[n_pos] = max(worst[n_pos], d)
        changed = [k for k in (1, 2, 3, 4) if worst[k] > 1e-12]
        lines.append(cfg.ljust(6)
                     + f"{worst[1]:.2e}".rjust(10) + f"{worst[2]:.2e}".rjust(10)
                     + f"{worst[3]:.2e}".rjust(10) + f"{worst[4]:.2e}".rjust(10)
                     + "  " + str(changed))
    return "\n".join(lines)


def selection_divergence(close, sigs):
    """Across all n_pos=4 months: compare A's min-var-3 pick vs K2's momentum-top-3.

    Returns (summary_text, rows) where rows = list of dicts per n_pos=4 month.
    """
    rows = []
    for sig_d in sigs:
        out, basket, regime, safe, n_pos = _core(close, sig_d, "A")
        if regime != "RISK_ON" or n_pos != 4:
            continue
        # positives are in basket? No -- A's basket is the min-var picks. Recompute positives.
        _, _, _, _, _ = out, basket, regime, safe, n_pos
        # recompute positive_picks (descending score order) directly
        positive_picks = _positive_picks(close, sig_d)
        mv3 = _min_var_subset(close, sig_d, positive_picks, CORR_LOOKBACK_DAYS, 3)
        mom3 = list(positive_picks)[:3]
        mv_drop = [t for t in positive_picks if t not in mv3][0]
        mom_drop = positive_picks[3]  # lowest momentum of the 4
        differ = set(mv3) != set(mom3)
        rows.append({
            "month": sig_d.strftime("%Y-%m"),
            "positives": list(positive_picks),
            "mv3": mv3, "mom3": mom3,
            "mv_drop": mv_drop, "mom_drop": mom_drop,
            "differ": differ,
        })
    n_total = len(rows)
    n_diff = sum(1 for r in rows if r["differ"])
    lines = [f"n_pos=4 months: {n_total} | months where min-var-3 != momentum-3: "
             f"{n_diff} ({100*n_diff/n_total:.1f}%)" if n_total else "no n_pos=4 months"]
    if n_total:
        # which name min-var drops that momentum keeps (mv_drop != mom_drop)
        from collections import Counter
        mv_drops = Counter(r["mv_drop"] for r in rows if r["differ"])
        mom_keeps_mv_drops = Counter(r["mv_drop"] for r in rows if r["differ"])
        lines.append("min-var drops (that momentum would keep) by ticker: "
                     + ", ".join(f"{k}:{v}" for k, v in mv_drops.most_common()))
        # momentum drop name distribution overall
        mom_drop_all = Counter(r["mom_drop"] for r in rows)
        lines.append("momentum-dropped (4th-ranked) by ticker (all n_pos=4): "
                     + ", ".join(f"{k}:{v}" for k, v in mom_drop_all.most_common()))
        mv_drop_all = Counter(r["mv_drop"] for r in rows)
        lines.append("min-var-dropped by ticker (all n_pos=4): "
                     + ", ".join(f"{k}:{v}" for k, v in mv_drop_all.most_common()))
    return "\n".join(lines), rows


def _positive_picks(close_panel, sig_d):
    """Recompute positive_picks (descending score) at sig_d for divergence dump."""
    monthly = close_panel.loc[:sig_d].resample("ME").last()
    faber = faber_sma_xs(monthly)
    avail = [t for t in RISKY_UNIVERSE
             if t in faber.index and pd.notna(faber[t])
             and pd.notna(close_panel.loc[sig_d].get(t, np.nan) if sig_d in close_panel.index else np.nan)]
    daily_rets = close_panel[avail].ffill().pct_change()
    scores = {}
    for t in avail:
        v = daily_rets[t].loc[:sig_d].tail(252).std() * np.sqrt(252)
        if pd.isna(v) or v < 1e-9:
            v = 1.0
        scores[t] = float(faber[t]) / v
    ranked = pd.Series(scores).sort_values(ascending=False)
    top_k = max(2, min(TOP_K_CANDIDATES, len(ranked)))
    top = ranked.iloc[:top_k]
    positive = top[top.index.map(lambda t: faber.get(t, -np.inf) > 0)]
    return list(positive.index)


def divergence_examples(rows, k=8) -> str:
    lines = ["month".ljust(9) + "positives(desc score)".ljust(34)
             + "minvar3".ljust(22) + "mom3".ljust(22)
             + "mv_drop".rjust(8) + "mom_drop".rjust(9)]
    lines.append("-" * len(lines[0]))
    diffs = [r for r in rows if r["differ"]]
    shown = diffs[:k]
    for r in shown:
        lines.append(r["month"].ljust(9)
                     + ",".join(r["positives"]).ljust(32) + "  "
                     + ",".join(r["mv3"]).ljust(20) + "  "
                     + ",".join(r["mom3"]).ljust(20)
                     + r["mv_drop"].rjust(8) + r["mom_drop"].rjust(9))
    if not shown:
        lines.append("(no divergent months)")
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
        "vol": m.get("vol"),
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
    "Euro 2011 (11-05..11-10)": ("2011-05-01", "2011-10-31"),
    "COVID 2020 (20-02..20-04)": ("2020-02-01", "2020-04-30"),
    "2022 bear (22-01..22-10)": ("2022-01-01", "2022-10-31"),
    "2025 tariff (25-02..25-05)": ("2025-02-01", "2025-05-22"),
}


def crisis_table(rets: dict) -> str:
    def cum(x): return (1 + x).prod() - 1
    def mdd(x):
        eq = (1 + x).cumprod()
        return (eq / eq.cummax() - 1).min()
    cfgs = [c for c in ORDER if c in rets]
    head = "crisis".ljust(30) + "".join((c + "_ret").rjust(11) for c in cfgs) \
        + "".join((c + "_DD").rjust(11) for c in cfgs)
    lines = [head, "-" * len(head)]
    for name, (s, e) in CRISES.items():
        cells_ret, cells_dd = [], []
        ok = True
        for c in cfgs:
            w = rets[c].loc[(rets[c].index >= s) & (rets[c].index <= e)]
            if w.empty:
                ok = False
                break
            cells_ret.append(f"{cum(w)*100:.2f}%".rjust(11))
            cells_dd.append(f"{mdd(w)*100:.2f}%".rjust(11))
        if not ok:
            lines.append(name.ljust(30) + "n/a (outside window)")
            continue
        lines.append(name.ljust(30) + "".join(cells_ret) + "".join(cells_dd))
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
    out.append("# CPM min-var 3-of-4 selection value at n_pos=4 -- exploratory\n")
    out.append("RESEARCH-ONLY. Prod untouched, no commit. mooex T+1, both-252, 10 bps/side.")
    out.append(f"Anchor gate: Sharpe={anc['Sharpe']:.6f} (target 1.255673), "
               f"MaxDD={anc['MaxDD']*100:.4f}%, Calmar={anc['Calmar']:.6f}")
    out.append("\nConfigs (n_pos=4 selection only; n_pos<=3 + canary identical to A):")
    out.append("  A : min-var 3-of-4 @ 33.3% (prod anchor)")
    out.append("  K1: hold ALL 4 @ 25% (full breadth, no selection)")
    out.append("  K2: momentum top-3 @ 33.3% (drop 4th-ranked by faber/vol score)")

    sigs_clean = _signal_dates(close, data.clean_start, data.end)
    sigs_ext = _signal_dates(close, data.ext_start, data.end)

    out.append("\n## ISOLATION vs A (clean window, worst weight diff by n_pos)")
    out.append("```")
    out.append(isolation_matrix(close, sigs_clean))
    out.append("```")
    out.append("Expected: A row all 0; K1/K2 nonzero ONLY at n4diff (changed_npos==[4]).")

    out.append("\n## SELECTION DIVERGENCE (all n_pos=4 months, ext window)")
    div_text, div_rows = selection_divergence(close, sigs_ext)
    out.append("```")
    out.append(div_text)
    out.append("")
    out.append("Representative divergent months (min-var-3 != momentum-3):")
    out.append(divergence_examples(div_rows, k=10))
    out.append("```")

    # ---- SLEEVE level ----
    sleeve_rets = {"clean": {}, "ext": {}}
    for win in ("clean", "ext"):
        rows = {}
        for cfg in ORDER:
            r = H.run_strategy(weight_fn_for(cfg), window=win, data=data)
            sleeve_rets[win][cfg] = r
            rows[cfg] = full_metrics(r, cash)
        out.append(f"\n## SLEEVE ({win}) -- mooex T+1, 10bps")
        out.append("```")
        out.append(fmt_table(rows, ["Sharpe", "Sortino", "MaxDD", "Calmar",
                                    "Martin", "CAGR", "vol"], {"MaxDD", "CAGR", "vol"}))
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

    # ---- verdict deltas ----
    sc = sleeve_rets["clean"]
    a_m = full_metrics(sc["A"], cash)
    k1_m = full_metrics(sc["K1"], cash)
    k2_m = full_metrics(sc["K2"], cash)
    out.append("\n## VERDICT (clean sleeve deltas, A = prod min-var)")
    out.append("```")
    out.append(f"A  Sharpe={a_m['Sharpe']:.4f}  MaxDD={a_m['MaxDD']*100:.2f}%  "
               f"CAGR={a_m['CAGR']*100:.2f}%  vol={a_m['vol']*100:.2f}%")
    out.append(f"K1 Sharpe={k1_m['Sharpe']:.4f}  MaxDD={k1_m['MaxDD']*100:.2f}%  "
               f"CAGR={k1_m['CAGR']*100:.2f}%  vol={k1_m['vol']*100:.2f}%")
    out.append(f"K2 Sharpe={k2_m['Sharpe']:.4f}  MaxDD={k2_m['MaxDD']*100:.2f}%  "
               f"CAGR={k2_m['CAGR']*100:.2f}%  vol={k2_m['vol']*100:.2f}%")
    out.append("")
    out.append(f"min-var value vs hold-all-4 (A-K1): dSharpe={a_m['Sharpe']-k1_m['Sharpe']:+.4f}  "
               f"dMaxDD={(a_m['MaxDD']-k1_m['MaxDD'])*100:+.2f}pp  "
               f"dCAGR={(a_m['CAGR']-k1_m['CAGR'])*100:+.2f}pp  "
               f"dVol={(a_m['vol']-k1_m['vol'])*100:+.2f}pp")
    out.append(f"min-var value vs momentum-3 (A-K2): dSharpe={a_m['Sharpe']-k2_m['Sharpe']:+.4f}  "
               f"dMaxDD={(a_m['MaxDD']-k2_m['MaxDD'])*100:+.2f}pp  "
               f"dCAGR={(a_m['CAGR']-k2_m['CAGR'])*100:+.2f}pp  "
               f"dVol={(a_m['vol']-k2_m['vol'])*100:+.2f}pp")
    out.append("```")

    report = "\n".join(out)
    print("\n" + report)
    rp = ROOT / "research" / "cpm_K_npos4_minvar_2026_06_02_raw.txt"
    rp.write_text(report)
    print(f"\n[written] {rp}")


if __name__ == "__main__":
    main()
