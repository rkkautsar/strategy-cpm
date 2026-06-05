"""Exploratory backtest: CPM Variant G family (VAA-inspired select-2) vs prod A.

HYPOTHESIS (Variant G family)
-----------------------------
Prod A selects min-var 3-of-4 risky names at full breadth (3 @ 33.3%). VAA-style
concentration asks: does picking only the min-var PAIR (2 names) improve the
risk-adjusted frontier, crossed with progressively more defensive breadth curves?

SELECTION (min-var 2-of-4):
  Among the n_pos positive-momentum risky assets, pick the equal-weight PAIR
  (2 names) minimizing portfolio variance over C(n_pos,2) pairs, using the SAME
  both-252 covariance the prod min-var-3 uses (_min_var_subset with m=2).
  Hold 2 names splitting risky_fraction equally (each = risky_fraction/2).
  n_pos=1 -> hold the single name at risky_fraction (no pair).
  n_pos=0 / canary-off -> 100% safe (unchanged).

CURVES (n_pos -> risky_fraction for n_pos=1,2,3,4):
  A  (baseline, select-3): 0.25 / 0.50 / 0.75 / 1.00   [== prod]
  G1 (select-2):           0.25 / 0.50 / 0.75 / 1.00
  G2 (select-2):           0.00 / 0.00 / 0.50 / 1.00
  G3 (select-2):           0.00 / 0.00 / 0.00 / 1.00

Canary, safe-selector, momentum signal, universe IDENTICAL to A. ONLY the
selection count (3->2) and the breadth->risky_fraction curve change.

RESEARCH-ONLY. Does not edit prod. Monkeypatches build_dashboard.compute_target_weights
(build_dashboard imports the symbol into its OWN namespace, so patching cpm_live.*
alone silently measures prod A on the blend rows -- the latent bug). Conventions
match prod via cpm_harness: mooex T+1, both-252, 10 bps/side. Reproduces 1.255673.

Template adapted from cpm_F_defensive_breadth_2026_06_02.py.
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


# --------------------------------------------------------------------------
# Config definitions: (select_count, curve dict n_pos->risky_fraction).
# A reproduces prod exactly (select-3, min(n_pos,4)/4 curve).
# --------------------------------------------------------------------------
CONFIGS = {
    "A":  {"select": 3, "curve": {1: 0.25, 2: 0.50, 3: 0.75, 4: 1.00}},
    "G1": {"select": 2, "curve": {1: 0.25, 2: 0.50, 3: 0.75, 4: 1.00}},
    "G2": {"select": 2, "curve": {1: 0.00, 2: 0.00, 3: 0.50, 4: 1.00}},
    "G3": {"select": 2, "curve": {1: 0.00, 2: 0.00, 3: 0.00, 4: 1.00}},
}
LABELS = {
    "A":  "A (prod, select-3)",
    "G1": "G1 (sel-2, 25/50/75/100)",
    "G2": "G2 (sel-2, 0/0/50/100)",
    "G3": "G3 (sel-2, 0/0/0/100)",
}


def _core(close_panel, sig_d, cfg: str):
    """Returns (weights, basket, regime, safe, n_pos). n_pos=None unless RISK_ON."""
    select_count = CONFIGS[cfg]["select"]
    curve = CONFIGS[cfg]["curve"]

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

    # --- selection ---
    if select_count == 3:
        # prod A: min-var 3-of-4 only at full breadth; else hold all positives.
        if n_pos == 4:
            picks = _min_var_subset(close_panel, sig_d, positive_picks, CORR_LOOKBACK_DAYS, 3)
        else:
            picks = positive_picks
    else:  # select-2 (G family)
        if n_pos >= 2:
            picks = _min_var_subset(close_panel, sig_d, positive_picks, CORR_LOOKBACK_DAYS, 2)
        else:
            picks = positive_picks  # single name

    # --- breadth curve ---
    risky_fraction = float(curve[min(n_pos, 4)])
    safe_fraction = 1.0 - risky_fraction

    out = {}
    if risky_fraction > 0:
        risky_w = {t: 1.0 / len(picks) for t in picks}
        out = {t: w * risky_fraction for t, w in risky_w.items()}
    if safe_fraction > 0:
        out[safe] = out.get(safe, 0.0) + safe_fraction

    return out, tuple(picks), "RISK_ON", safe, n_pos


def make_weight_fn(cfg: str):
    def _fn(close_panel, sig_d):
        out, *_ = _core(close_panel, sig_d, cfg)
        return out
    return _fn


def make_ctw(cfg: str):
    def _ctw(close_panel, sig_d, universe=None, safe_pool=None, canary_assets=None):
        out, basket, regime, safe, _ = _core(close_panel, sig_d, cfg)
        return out, basket, regime, safe
    return _ctw


# --------------------------------------------------------------------------
# Self-consistency: cfg "A" must reproduce prod exactly.
# --------------------------------------------------------------------------
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
        keys = set(prod) | set(mine)
        for k in keys:
            max_diff = max(max_diff, abs(prod.get(k, 0.0) - mine.get(k, 0.0)))
    if max_diff > 1e-12:
        raise AssertionError(f"baseline replica != prod, max weight diff {max_diff:.2e}")
    print(f"[ok] baseline replica matches prod (max weight diff {max_diff:.2e})")


# --------------------------------------------------------------------------
# Diff months: which months differ between each G and A; confirm defensive
# (n_pos None) months unchanged across all configs.
# --------------------------------------------------------------------------
def diff_report(close, sigs) -> dict:
    res = {}
    defensive_unchanged = True
    defensive_count = 0
    for cfg in ("G1", "G2", "G3"):
        changed = []
        for sig_d in sigs:
            a_out, _, _, _, a_npos = _core(close, sig_d, "A")
            g_out, _, _, _, g_npos = _core(close, sig_d, cfg)
            keys = set(a_out) | set(g_out)
            diff = max(abs(a_out.get(k, 0.0) - g_out.get(k, 0.0)) for k in keys)
            if a_npos is None:  # defensive / canary-off
                if cfg == "G1":
                    defensive_count += 1
                if diff > 1e-12:
                    defensive_unchanged = False
            elif diff > 1e-12:
                changed.append((sig_d.strftime("%Y-%m"), a_npos))
        res[cfg] = changed
    res["_defensive_unchanged"] = defensive_unchanged
    res["_defensive_count"] = defensive_count
    return res


# --------------------------------------------------------------------------
# Metrics helpers.
# --------------------------------------------------------------------------
def extra_metrics(daily: pd.Series) -> dict:
    d = daily.dropna()
    downside = d[d < 0]
    dd_std = downside.std(ddof=0) * np.sqrt(252)
    sortino = (d.mean() * 252) / dd_std if dd_std > 0 else float("nan")
    q = np.quantile(d.values, 0.05)
    cvar95 = d[d <= q].mean()
    return {"Sortino": sortino, "CVaR95_daily": cvar95}


def npos_stats(close, sigs) -> dict:
    counts = {1: 0, 2: 0, 3: 0, 4: 0}
    risk_on = 0
    defensive = 0
    total = 0
    for sig_d in sigs:
        _, _, regime, _, n_pos = _core(close, sig_d, "A")
        total += 1
        if regime == "RISK_ON":
            risk_on += 1
            counts[n_pos] = counts.get(n_pos, 0) + 1
        else:
            defensive += 1
    return {"total": total, "risk_on": risk_on, "defensive": defensive, "counts": counts}


def full_metrics(returns) -> dict:
    m = cpm_live.perf_metrics(returns, None)
    em = extra_metrics(returns)
    return {
        "Sharpe": m["sharpe"], "Sortino": em["Sortino"],
        "Calmar": m["calmar"], "Martin": m["martin"],
        "MaxDD": m["max_drawdown"], "CAGR": m["cagr"], "vol": m["vol"],
    }


def fmt_table(rows: dict, order: list, cols=None) -> str:
    cols = cols or ["Sharpe", "Sortino", "Calmar", "Martin", "MaxDD", "CAGR", "vol"]
    head = "config".ljust(28) + "".join(c.rjust(11) for c in cols)
    lines = [head, "-" * len(head)]
    for name in order:
        m = rows[name]
        cells = []
        for c in cols:
            v = m[c]
            if c in ("MaxDD", "CAGR", "vol", "CVaR95_d"):
                cells.append(f"{v*100:.2f}%".rjust(11))
            else:
                cells.append(f"{v:.3f}".rjust(11))
        lines.append(name.ljust(28) + "".join(cells))
    return "\n".join(lines)


def crisis_breakdown(rets_by_cfg: dict, order: list):
    crises = {
        "GFC 2008 (2007-09..2009-03)": ("2007-09-01", "2009-03-31"),
        "Euro 2011 (2011-05..2011-10)": ("2011-05-01", "2011-10-31"),
        "COVID 2020 (2020-02..2020-04)": ("2020-02-01", "2020-04-30"),
        "2022 bear (2022-01..2022-10)": ("2022-01-01", "2022-10-31"),
        "2025 tariff (2025-02..2025-05)": ("2025-02-01", "2025-05-22"),
    }
    def cum(x):
        return (1 + x).prod() - 1
    def mdd(x):
        eq = (1 + x).cumprod()
        return (eq / eq.cummax() - 1).min()
    head = "crisis window".ljust(32)
    for c in order:
        head += (c + " ret").rjust(13) + (c + " DD").rjust(13)
    lines = [head, "-" * len(head)]
    for name, (s, e) in crises.items():
        row = name.ljust(32)
        for c in order:
            r = rets_by_cfg[c]
            w = r.loc[(r.index >= s) & (r.index <= e)]
            if w.empty:
                row += "n/a".rjust(13) + "n/a".rjust(13)
            else:
                row += f"{cum(w)*100:.2f}%".rjust(13) + f"{mdd(w)*100:.2f}%".rjust(13)
        lines.append(row)
    return "\n".join(lines)


def main():
    print("Loading harness data ...")
    data = H.load_data()
    close = data.panel

    anc = H.verify_anchor(data=data)
    print(f"[ok] anchor Sharpe={anc['Sharpe']:.6f} MaxDD={anc['MaxDD']:.6f} "
          f"Calmar={anc['Calmar']:.6f}")
    verify_baseline_matches_prod(data)

    out = []
    out.append("# CPM Variant G family (VAA select-2) vs prod A -- exploratory\n")
    out.append(f"Anchor gate: Sharpe={anc['Sharpe']:.6f} (target 1.255673), "
               f"MaxDD={anc['MaxDD']*100:.4f}%, Calmar={anc['Calmar']:.6f}")

    sigs_clean = _signal_dates(close, data.clean_start, data.end)

    # ---- diff months G vs A + defensive invariance ----
    dr = diff_report(close, sigs_clean)
    out.append("\n## Diff months (clean): each G vs A")
    for cfg in ("G1", "G2", "G3"):
        ch = dr[cfg]
        out.append(f"\n{LABELS[cfg]}: {len(ch)} months differ from A")
        toks = [f"{m}(n{n})" for m, n in ch]
        for i in range(0, len(toks), 6):
            out.append("  " + "  ".join(toks[i:i+6]))
    out.append(f"\nDefensive/canary-off months (n_pos=None): {dr['_defensive_count']}, "
               f"unchanged across ALL configs: {dr['_defensive_unchanged']}")

    # ---- n_pos histogram ----
    for win, start in (("clean", data.clean_start), ("ext", data.ext_start)):
        sigs = _signal_dates(close, start, data.end)
        st = npos_stats(close, sigs)
        out.append(f"\n## n_pos histogram ({win}: {start.date()}..{data.end.date()})")
        out.append(f"total months: {st['total']}, risk-on: {st['risk_on']}, "
                   f"defensive: {st['defensive']}")
        out.append(f"RISK_ON n_pos counts {{1,2,3,4}}: {st['counts']}")
        lowb = st['counts'][1] + st['counts'][2]
        out.append(f"low-breadth (n_pos in {{1,2}}): {lowb} "
                   f"({100*lowb/max(st['risk_on'],1):.1f}% of risk-on)")

    # ---- SLEEVE level (mooex harness), clean + ext ----
    sleeve_rets = {"clean": {}, "ext": {}}
    for win in ("clean", "ext"):
        start = data.clean_start if win == "clean" else data.ext_start
        rows = {}
        for cfg in ("A", "G1", "G2", "G3"):
            r = H.run_strategy(make_weight_fn(cfg), window=win, data=data)
            sleeve_rets[win][cfg] = r
            rows[LABELS[cfg]] = full_metrics(r)
        out.append(f"\n## SLEEVE ({win}) -- mooex T+1, 10bps")
        out.append("```")
        out.append(fmt_table(rows, [LABELS[c] for c in ("A", "G1", "G2", "G3")]))
        out.append("```")

    # ---- Per-crisis sleeve (ext window) ----
    out.append("\n### Per-crisis (sleeve, EXT window) cum return + maxDD")
    out.append("```")
    out.append(crisis_breakdown(
        {c: sleeve_rets["ext"][c] for c in ("A", "G1", "G2", "G3")},
        ["A", "G1", "G2", "G3"]))
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
        print(f"  NDX panel unavailable ({e}); blend will use CPM+BULL only.")
        ndx_panel = None
    bstart = data.clean_start

    def blend_metrics(art):
        m = cpm_live.perf_metrics(art.blend, bcash)
        return {
            "Sharpe": m["sharpe"], "Sortino": float("nan"),
            "Calmar": m["calmar"], "Martin": m["martin"],
            "MaxDD": m["max_drawdown"], "CAGR": m["cagr"], "vol": m["vol"],
        }

    brows = {}
    _orig_bd = BD.compute_target_weights
    _orig_cl = cpm_live.compute_target_weights
    for cfg in ("A", "G1", "G2", "G3"):
        print(f"Building blend for {cfg} (build_dashboard.compute_target_weights patched) ...")
        BD.compute_target_weights = make_ctw(cfg)
        cpm_live.compute_target_weights = make_ctw(cfg)
        try:
            art = BD.build_artifacts(bpanel, ndx_panel, bstart, bend, include_records=False)
        finally:
            BD.compute_target_weights = _orig_bd
            cpm_live.compute_target_weights = _orig_cl
        brows[LABELS[cfg]] = blend_metrics(art)

    out.append(f"\n## BLEND 60/20/20 (clean {bstart.date()}..{bend.date()}) "
               "-- build_dashboard.compute_target_weights PATCHED per config; BULL+NDX identical")
    out.append("```")
    out.append(fmt_table(brows, [LABELS[c] for c in ("A", "G1", "G2", "G3")],
                         cols=["Sharpe", "Calmar", "Martin", "MaxDD", "CAGR", "vol"]))
    out.append("```")

    report = "\n".join(out)
    print("\n" + report)
    rp = ROOT / "research" / "cpm_G_select2_breadth_2026_06_02_raw.txt"
    rp.write_text(report)
    print(f"\n[written] {rp}")


if __name__ == "__main__":
    main()
