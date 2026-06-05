"""Exploratory backtest: CPM Variant F 'defensive low-breadth gate' vs prod A.

HYPOTHESIS (Variant F)
----------------------
Prod A sizes risky_fraction = min(n_pos,4)/4. Low-breadth months (n_pos=1,2)
get 25%/50% risky. F asks: is low breadth a fragility signal that should be
fully de-risked, accepting it might miss early-recovery upside?

F mapping (only breadth->risky_fraction changes; selection/min-var identical):
  n_pos=0 -> 100% safe              [== A]
  n_pos=1 -> 100% safe  (was 25%)   [CHANGED]
  n_pos=2 -> 100% safe  (was 50%)   [CHANGED]
  n_pos=3 -> 50% risky / 50% safe   [CHANGED from A's 75%]; 3 names @ 16.667% each
  n_pos=4 -> min-var-3 @ 33.3%      [BIT-IDENTICAL to A]

A mapping:
  n_pos=1 -> 1 @ 25%   (E 0.25)
  n_pos=2 -> 2 @ 25%   (E 0.50)
  n_pos=3 -> 3 @ 25%   (E 0.75)
  n_pos=4 -> min-var-3 @ 33.3% (E 1.00)

RESEARCH-ONLY. Does not edit prod. Monkeypatches build_dashboard.compute_target_weights
(build_dashboard imports the symbol into its OWN namespace, so patching cpm_live.*
alone silently measures prod A on the blend rows -- the latent bug). Passes variant
weight_fn to the sleeve harness. Conventions match prod via cpm_harness:
mooex T+1, both-252, 10 bps/side. Reproduces the 1.2557 anchor gate.

Template adapted from cpm_c8_fullinvest3_2026_06_02.py.
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
# Variant weight builder: faithful copy of compute_target_weights, with the
# SINGLE sizing change in the breadth->risky_fraction map. mode="A" reproduces
# prod; mode="F" applies the defensive low-breadth gate. Selection (min-var
# 3-of-4), canary, ranker, safe-selector are IDENTICAL in both modes.
# --------------------------------------------------------------------------
def _core(close_panel, sig_d, mode: str):
    """Returns (weights, basket, regime, safe, n_pos). n_pos=None unless RISK_ON."""
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
    else:
        picks = positive_picks

    if mode == "F":
        # Defensive low-breadth gate: only the breadth->risky_fraction map changes.
        if n_pos >= 4:
            risky_fraction = 1.0          # UNCHANGED vs A (min-var-3 @ 33.3%)
        elif n_pos == 3:
            risky_fraction = 0.5          # was 0.75
        else:  # n_pos in {1, 2}
            risky_fraction = 0.0          # 100% safe (was 0.25 / 0.50)
    else:  # "A" prod
        risky_fraction = min(n_pos, 4) / 4.0
    safe_fraction = 1.0 - risky_fraction

    risky_w = {t: 1.0 / len(picks) for t in picks}
    out = {t: w * risky_fraction for t, w in risky_w.items()}
    if safe_fraction > 0:
        out[safe] = out.get(safe, 0.0) + safe_fraction

    return out, tuple(picks), "RISK_ON", safe, n_pos


def f_weight_fn(close_panel, sig_d):
    out, *_ = _core(close_panel, sig_d, mode="F")
    return out


def f_compute_target_weights(close_panel, sig_d, universe=None,
                             safe_pool=None, canary_assets=None):
    out, basket, regime, safe, _ = _core(close_panel, sig_d, mode="F")
    return out, basket, regime, safe


def baseline_weight_fn(close_panel, sig_d):
    out, *_ = _core(close_panel, sig_d, mode="A")
    return out


# --------------------------------------------------------------------------
# Self-consistency: baseline_weight_fn must reproduce prod exactly.
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
        mine, *_ = _core(close, sig_d, mode="A")
        keys = set(prod) | set(mine)
        for k in keys:
            max_diff = max(max_diff, abs(prod.get(k, 0.0) - mine.get(k, 0.0)))
    if max_diff > 1e-12:
        raise AssertionError(f"baseline replica != prod, max weight diff {max_diff:.2e}")
    print(f"[ok] baseline replica matches prod (max weight diff {max_diff:.2e})")


# --------------------------------------------------------------------------
# CRITICAL GATE: confirm A and F are BIT-IDENTICAL at n_pos in {0,4}.
# n_pos=4 must be identical; n_pos in {1,2,3} must differ.
# --------------------------------------------------------------------------
def verify_f_isolation(close, sigs) -> dict:
    n4_identical = 0
    n4_worst = 0.0
    n4_bad = []
    n123_changed = 0
    n123_unchanged = []
    for sig_d in sigs:
        a_out, _, _, _, n_pos = _core(close, sig_d, mode="A")
        f_out, _, _, _, _ = _core(close, sig_d, mode="F")
        keys = set(a_out) | set(f_out)
        diff = max(abs(a_out.get(k, 0.0) - f_out.get(k, 0.0)) for k in keys)
        if n_pos == 4:
            n4_worst = max(n4_worst, diff)
            if diff <= 1e-12:
                n4_identical += 1
            else:
                n4_bad.append((sig_d, diff))
        elif n_pos in (1, 2, 3):
            if diff > 1e-12:
                n123_changed += 1
            else:
                n123_unchanged.append((sig_d, n_pos))
    return {
        "n_pos4_identical": n4_identical,
        "n_pos4_worst_diff": n4_worst,
        "n_pos4_bad": n4_bad,
        "n_pos123_changed": n123_changed,
        "n_pos123_unchanged": n123_unchanged,
    }


# --------------------------------------------------------------------------
# Extra metrics: Sortino, CVaR(95).
# --------------------------------------------------------------------------
def extra_metrics(daily: pd.Series, cash: pd.Series) -> dict:
    d = daily.dropna()
    downside = d[d < 0]
    dd_std = downside.std(ddof=0) * np.sqrt(252)
    cagr_mean = d.mean() * 252
    sortino = cagr_mean / dd_std if dd_std > 0 else float("nan")
    q = np.quantile(d.values, 0.05)
    cvar95 = d[d <= q].mean()
    return {"Sortino": sortino, "CVaR95_daily": cvar95}


def turnover_avg(weight_fn, close, sigs) -> float:
    prev = {}
    tos = []
    for sig_d in sigs:
        w = weight_fn(close, sig_d)
        keys = set(w) | set(prev)
        to = sum(abs(w.get(k, 0.0) - prev.get(k, 0.0)) for k in keys)
        tos.append(to)
        prev = w
    return float(np.mean(tos[1:])) if len(tos) > 1 else float(np.mean(tos))


def npos_stats(close, sigs) -> dict:
    counts = {1: 0, 2: 0, 3: 0, 4: 0}
    months = {1: [], 2: [], 3: [], 4: []}
    risk_on = 0
    defensive = 0
    total = 0
    for sig_d in sigs:
        _, _, regime, _, n_pos = _core(close, sig_d, mode="A")
        total += 1
        if regime == "RISK_ON":
            risk_on += 1
            counts[n_pos] = counts.get(n_pos, 0) + 1
            months[n_pos].append(sig_d)
        else:
            defensive += 1
    return {
        "total_months": total, "risk_on_months": risk_on,
        "defensive_months": defensive, "counts": counts, "months": months,
    }


def full_metrics(returns, cash, close, sigs, weight_fn) -> dict:
    m = cpm_live.perf_metrics(returns, cash)
    em = extra_metrics(returns, cash)
    to = turnover_avg(weight_fn, close, sigs)
    return {
        "Sharpe": m["sharpe"], "Sortino": em["Sortino"],
        "CVaR95_d": em["CVaR95_daily"], "Calmar": m["calmar"],
        "Martin": m["martin"], "MaxDD": m["max_drawdown"],
        "CAGR": m["cagr"], "vol": m["vol"], "turnover": to,
    }


def fmt_table(rows: dict, order: list) -> str:
    cols = ["Sharpe", "Sortino", "CVaR95_d", "Calmar", "Martin", "MaxDD",
            "CAGR", "vol", "turnover"]
    head = "config".ljust(22) + "".join(c.rjust(11) for c in cols)
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
        lines.append(name.ljust(22) + "".join(cells))
    return "\n".join(lines)


def crisis_breakdown(base_ret, var_ret):
    crises = {
        "GFC 2008 (2007-09..2009-03)": ("2007-09-01", "2009-03-31"),
        "Euro 2011 (2011-05..2011-10)": ("2011-05-01", "2011-10-31"),
        "COVID 2020 (2020-02..2020-04)": ("2020-02-01", "2020-04-30"),
        "2022 bear (2022-01..2022-10)": ("2022-01-01", "2022-10-31"),
        "2025 tariff (2025-02..2025-05)": ("2025-02-01", "2025-05-22"),
    }
    lines = ["crisis window".ljust(32) + "A_ret".rjust(11) + "F_ret".rjust(11)
             + "A_DD".rjust(11) + "F_DD".rjust(11)]
    lines.append("-" * len(lines[0]))
    for name, (s, e) in crises.items():
        bw = base_ret.loc[(base_ret.index >= s) & (base_ret.index <= e)]
        vw = var_ret.loc[(var_ret.index >= s) & (var_ret.index <= e)]
        if bw.empty:
            lines.append(name.ljust(32) + "n/a (outside window)".rjust(44))
            continue
        def cum(x):
            return (1 + x).prod() - 1
        def mdd(x):
            eq = (1 + x).cumprod()
            return (eq / eq.cummax() - 1).min()
        lines.append(name.ljust(32)
                     + f"{cum(bw)*100:.2f}%".rjust(11)
                     + f"{cum(vw)*100:.2f}%".rjust(11)
                     + f"{mdd(bw)*100:.2f}%".rjust(11)
                     + f"{mdd(vw)*100:.2f}%".rjust(11))
    return "\n".join(lines)


def main():
    print("Loading harness data ...")
    data = H.load_data()
    cash = data.cash

    anc = H.verify_anchor(data=data)
    print(f"[ok] anchor Sharpe={anc['Sharpe']:.6f} MaxDD={anc['MaxDD']:.6f} "
          f"Calmar={anc['Calmar']:.6f}")
    verify_baseline_matches_prod(data)

    close = data.panel
    out = []
    out.append("# CPM Variant F (defensive low-breadth gate) vs prod A -- exploratory\n")
    out.append(f"Anchor gate: Sharpe={anc['Sharpe']:.6f} (target 1.255673), "
               f"MaxDD={anc['MaxDD']*100:.4f}%, Calmar={anc['Calmar']:.6f}")

    # ---- CRITICAL GATE: n_pos=4 bit-identical, n_pos in {1,2,3} differ ----
    sigs_clean = _signal_dates(close, data.clean_start, data.end)
    iso = verify_f_isolation(close, sigs_clean)
    out.append("\n## GATE: A vs F isolation (clean window)")
    out.append(f"n_pos=4 months bit-IDENTICAL to A: {iso['n_pos4_identical']} "
               f"(worst weight diff {iso['n_pos4_worst_diff']:.2e})")
    out.append(f"n_pos in {{1,2,3}} CHANGED (expected): {iso['n_pos123_changed']}")
    if iso["n_pos4_bad"]:
        out.append(f"!! n_pos=4 NON-identical months: {iso['n_pos4_bad']}")
    if iso["n_pos123_unchanged"]:
        out.append(f"!! n_pos in {{1,2,3}} unexpectedly UNCHANGED: "
                   f"{iso['n_pos123_unchanged']}")
    gate_ok = (iso["n_pos4_worst_diff"] <= 1e-12 and not iso["n_pos123_unchanged"])
    out.append(f"GATE n_pos=4 BIT-IDENTICAL & n_pos in {{1,2,3}} all changed: "
               f"{'PASS' if gate_ok else 'FAIL'}")

    # ---- n_pos frequency + WHERE low-breadth months land ----
    for win, start in (("clean", data.clean_start), ("ext", data.ext_start)):
        sigs = _signal_dates(close, start, data.end)
        st = npos_stats(close, sigs)
        out.append(f"\n## n_pos frequency ({win}: {start.date()}..{data.end.date()})")
        out.append(f"total months: {st['total_months']}, risk-on: {st['risk_on_months']}, "
                   f"defensive: {st['defensive_months']}")
        out.append(f"RISK_ON n_pos counts {{1,2,3,4}}: {st['counts']}")
        if win == "clean":
            for k in (1, 2, 3):
                mn = [d.strftime("%Y-%m") for d in st["months"][k]]
                out.append(f"\nn_pos={k} months (clean), n={len(mn)}:")
                for i in range(0, len(mn), 8):
                    out.append("  " + "  ".join(mn[i:i+8]))

    # ---- SLEEVE level (mooex harness) ----
    sleeve_rets = {}
    for win in ("clean", "ext"):
        start = data.clean_start if win == "clean" else data.ext_start
        sigs = _signal_dates(close, start, data.end)

        base_ret = H.run_strategy(baseline_weight_fn, window=win, data=data)
        var_ret = H.run_strategy(f_weight_fn, window=win, data=data)
        sleeve_rets[win] = (base_ret, var_ret)

        rows = {
            "A (prod)": full_metrics(base_ret, cash, close, sigs, baseline_weight_fn),
            "F (defensive gate)": full_metrics(var_ret, cash, close, sigs, f_weight_fn),
        }
        out.append(f"\n## SLEEVE ({win}) -- mooex T+1, 10bps")
        out.append("```")
        out.append(fmt_table(rows, ["A (prod)", "F (defensive gate)"]))
        out.append("```")

    # ---- Per-crisis sleeve MaxDD (ext window for full GFC coverage) ----
    out.append("\n### Per-crisis (sleeve, EXT window) cum return + maxDD")
    out.append("```")
    out.append(crisis_breakdown(sleeve_rets["ext"][0], sleeve_rets["ext"][1]))
    out.append("```")

    # ---- BLEND level (build_dashboard 60/20/20) ----
    import build_dashboard as BD
    from cpm_live import load_panel
    print("Loading blend panel + NDX ...")
    bpanel_start = pd.Timestamp("1995-01-01")
    bpanel = load_panel(start=bpanel_start, end=data.end, live=True)
    bend = min(data.end, bpanel.index[-1])
    bcash = bpanel["SHV"].ffill().pct_change().dropna()
    try:
        from ndx_sleeve_live import load_ndx_panel
        ndx_panel = load_ndx_panel()
    except Exception as e:
        print(f"  NDX panel unavailable ({e}); blend will use CPM+BULL only.")
        ndx_panel = None

    bstart = data.clean_start
    print("Building baseline blend (A) ...")
    art_base = BD.build_artifacts(bpanel, ndx_panel, bstart, bend, include_records=False)

    print("Building F blend (monkeypatched CPM via build_dashboard.compute_target_weights) ...")
    # build_dashboard imports compute_target_weights into its OWN namespace,
    # so we MUST patch BD's bound reference (patching cpm_live alone silently
    # measures prod A on the blend rows). Patch both for safety.
    _orig_bd = BD.compute_target_weights
    _orig_cl = cpm_live.compute_target_weights
    BD.compute_target_weights = f_compute_target_weights
    cpm_live.compute_target_weights = f_compute_target_weights
    try:
        art_var = BD.build_artifacts(bpanel, ndx_panel, bstart, bend, include_records=False)
    finally:
        BD.compute_target_weights = _orig_bd
        cpm_live.compute_target_weights = _orig_cl

    def blend_metrics(art):
        m = cpm_live.perf_metrics(art.blend, bcash)
        em = extra_metrics(art.blend, bcash)
        return {
            "Sharpe": m["sharpe"], "Sortino": em["Sortino"],
            "CVaR95_d": em["CVaR95_daily"], "Calmar": m["calmar"],
            "Martin": m["martin"], "MaxDD": m["max_drawdown"],
            "CAGR": m["cagr"], "vol": m["vol"], "turnover": float("nan"),
        }

    brows = {
        "A (prod)": blend_metrics(art_base),
        "F (defensive gate)": blend_metrics(art_var),
    }
    out.append(f"\n## BLEND 60/20/20 (clean {bstart.date()}..{bend.date()}) "
               "-- build_dashboard.compute_target_weights patched; BULL+NDX identical")
    out.append("```")
    out.append(fmt_table(brows, ["A (prod)", "F (defensive gate)"]))
    out.append("```")

    report = "\n".join(out)
    print("\n" + report)
    rp = ROOT / "research" / "cpm_F_defensive_breadth_2026_06_02_raw.txt"
    rp.write_text(report)
    print(f"\n[written] {rp}")


if __name__ == "__main__":
    main()
