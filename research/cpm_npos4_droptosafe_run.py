"""Exploratory backtest: CPM n_pos=4 'drop-to-safe' variant vs prod renormalize.

HYPOTHESIS
----------
At n_pos=4, prod min-var drops 1 of 4, then renormalizes the 3 survivors to
100% equal-weight (33.3% each, ZERO safe) because risky_fraction = min(n_pos,4)/4
= 1.0. The min-var drop only CONCENTRATES; it does not de-risk.

VARIANT ("drop-to-safe"): send the min-var-dropped 4th slot to SAFE instead of
renormalizing it away -> 3 risk @ 25% + 25% safe (risky_fraction = len(picks)/4
= 0.75). ONLY the n_pos=4 case changes. n_pos in {1,2,3} unchanged.

This script is RESEARCH-ONLY. It does not edit prod. It monkeypatches
cpm_live.compute_target_weights for the blend path and passes a variant
weight_fn directly to the sleeve harness.

Conventions match prod: lagged T+1 MOO (sleeve via cpm_harness mooex engine;
blend via run_cpm_backtest close-to-close T+1), 10 bps/side.
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
# SINGLE n_pos==4 change (risky_fraction = len(picks)/4 instead of 1.0).
# Selection (min-var 3-of-4), canary, ranker, safe-selector are IDENTICAL.
# --------------------------------------------------------------------------
def _core(close_panel, sig_d, drop_to_safe: bool):
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

    if drop_to_safe and n_pos == 4:
        risky_fraction = len(picks) / 4.0       # 3/4 = 0.75  (VARIANT)
    else:
        risky_fraction = min(n_pos, 4) / 4.0     # prod
    safe_fraction = 1.0 - risky_fraction

    risky_w = {t: 1.0 / len(picks) for t in picks}
    out = {t: w * risky_fraction for t, w in risky_w.items()}
    if safe_fraction > 0:
        out[safe] = out.get(safe, 0.0) + safe_fraction

    return out, tuple(picks), "RISK_ON", safe, n_pos


def variant_weight_fn(close_panel, sig_d):
    out, *_ = _core(close_panel, sig_d, drop_to_safe=True)
    return out


def variant_compute_target_weights(close_panel, sig_d, universe=None,
                                    safe_pool=None, canary_assets=None):
    out, basket, regime, safe, _ = _core(close_panel, sig_d, drop_to_safe=True)
    return out, basket, regime, safe


def baseline_weight_fn(close_panel, sig_d):
    out, *_ = _core(close_panel, sig_d, drop_to_safe=False)
    return out


# --------------------------------------------------------------------------
# Self-consistency: baseline_weight_fn must reproduce prod exactly.
# --------------------------------------------------------------------------
def verify_baseline_matches_prod(data) -> None:
    monthly_idx = (pd.DataFrame({"x": 1}, index=data.panel.index)
                   .groupby(pd.Grouper(freq="ME")).tail(1).index)
    sigs = monthly_idx[(monthly_idx >= data.clean_start) & (monthly_idx <= data.end)]
    close = data.panel
    max_diff = 0.0
    for sig_d in sigs:
        prod, *_ = compute_target_weights(close, sig_d)
        mine, *_ = _core(close, sig_d, drop_to_safe=False)
        keys = set(prod) | set(mine)
        for k in keys:
            max_diff = max(max_diff, abs(prod.get(k, 0.0) - mine.get(k, 0.0)))
    if max_diff > 1e-12:
        raise AssertionError(f"baseline replica != prod, max weight diff {max_diff:.2e}")
    print(f"[ok] baseline replica matches prod (max weight diff {max_diff:.2e})")


# --------------------------------------------------------------------------
# Extra metrics not in perf_metrics: Sortino, CVaR(95).
# --------------------------------------------------------------------------
def extra_metrics(daily: pd.Series, cash: pd.Series) -> dict:
    d = daily.dropna()
    cash_a = cash.reindex_like(d).fillna(0.0)
    excess = d - cash_a
    downside = d[d < 0]
    dd_std = downside.std(ddof=0) * np.sqrt(252)
    cagr_mean = d.mean() * 252
    sortino = cagr_mean / dd_std if dd_std > 0 else float("nan")
    # CVaR(95): mean of worst 5% daily returns (loss = negative), annualized? keep daily %.
    q = np.quantile(d.values, 0.05)
    cvar95 = d[d <= q].mean()
    return {"Sortino": sortino, "CVaR95_daily": cvar95}


def turnover_avg(weight_fn, close, sigs) -> float:
    """Average two-way monthly turnover (sum |dw|) across signal dates."""
    prev = {}
    tos = []
    for sig_d in sigs:
        w = weight_fn(close, sig_d)
        keys = set(w) | set(prev)
        to = sum(abs(w.get(k, 0.0) - prev.get(k, 0.0)) for k in keys)
        tos.append(to)
        prev = w
    # drop first (cold-start full ramp) for a cleaner steady-state estimate
    return float(np.mean(tos[1:])) if len(tos) > 1 else float(np.mean(tos))


def npos4_stats(close, sigs) -> dict:
    """How often n_pos==4 vs other RISK_ON counts; fraction of risk-on months."""
    counts = {1: 0, 2: 0, 3: 0, 4: 0}
    risk_on = 0
    total = 0
    for sig_d in sigs:
        _, _, regime, _, n_pos = _core(close, sig_d, drop_to_safe=False)
        total += 1
        if regime == "RISK_ON":
            risk_on += 1
            counts[n_pos] = counts.get(n_pos, 0) + 1
    return {
        "total_months": total,
        "risk_on_months": risk_on,
        "counts": counts,
        "n_pos4_months": counts.get(4, 0),
        "frac_of_riskon": counts.get(4, 0) / risk_on if risk_on else float("nan"),
        "frac_of_all": counts.get(4, 0) / total if total else float("nan"),
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


def crisis_breakdown(base_ret, var_ret, cash):
    crises = {
        "GFC 2007-09..2009-03": ("2007-09-01", "2009-03-31"),
        "Euro/2011 2011-05..2011-10": ("2011-05-01", "2011-10-31"),
        "2015-16 selloff": ("2015-07-01", "2016-02-29"),
        "Q4-2018": ("2018-10-01", "2018-12-31"),
        "COVID 2020-02..2020-04": ("2020-02-01", "2020-04-30"),
        "2022 bear": ("2022-01-01", "2022-10-31"),
    }
    lines = ["crisis window".ljust(30) + "base_ret".rjust(11) + "var_ret".rjust(11)
             + "base_DD".rjust(11) + "var_DD".rjust(11)]
    lines.append("-" * len(lines[0]))
    for name, (s, e) in crises.items():
        for label, ret in (("", base_ret), ("", var_ret)):
            pass
        bw = base_ret.loc[(base_ret.index >= s) & (base_ret.index <= e)]
        vw = var_ret.loc[(var_ret.index >= s) & (var_ret.index <= e)]
        if bw.empty:
            continue
        def cum(x):
            return (1 + x).prod() - 1
        def mdd(x):
            eq = (1 + x).cumprod()
            return (eq / eq.cummax() - 1).min()
        lines.append(name.ljust(30)
                     + f"{cum(bw)*100:.2f}%".rjust(11)
                     + f"{cum(vw)*100:.2f}%".rjust(11)
                     + f"{mdd(bw)*100:.2f}%".rjust(11)
                     + f"{mdd(vw)*100:.2f}%".rjust(11))
    return "\n".join(lines)


def main():
    print("Loading harness data ...")
    data = H.load_data()
    cash = data.cash

    # Anchor sanity (prod through harness).
    anc = H.verify_anchor(data=data)
    print(f"[ok] anchor Sharpe={anc['Sharpe']:.6f} MaxDD={anc['MaxDD']:.6f} "
          f"Calmar={anc['Calmar']:.6f}")
    verify_baseline_matches_prod(data)

    close = data.panel
    out = []
    out.append("# CPM n_pos=4 drop-to-safe vs renormalize -- exploratory\n")

    # ---- n_pos=4 frequency (clean + ext) ----
    for win, start in (("clean", data.clean_start), ("ext", data.ext_start)):
        midx = (pd.DataFrame({"x": 1}, index=close.index)
                .groupby(pd.Grouper(freq="ME")).tail(1).index)
        sigs = midx[(midx >= start) & (midx <= data.end)]
        st = npos4_stats(close, sigs)
        out.append(f"\n## n_pos frequency ({win}: {start.date()}..{data.end.date()})")
        out.append(f"total months: {st['total_months']}, risk-on: {st['risk_on_months']}")
        out.append(f"RISK_ON n_pos counts {{1,2,3,4}}: {st['counts']}")
        out.append(f"n_pos=4 months: {st['n_pos4_months']}  "
                   f"= {st['frac_of_riskon']*100:.1f}% of risk-on, "
                   f"{st['frac_of_all']*100:.1f}% of all months")

    # ---- SLEEVE level (mooex harness) ----
    for win in ("clean", "ext"):
        start = data.clean_start if win == "clean" else data.ext_start
        midx = (pd.DataFrame({"x": 1}, index=close.index)
                .groupby(pd.Grouper(freq="ME")).tail(1).index)
        sigs = midx[(midx >= start) & (midx <= data.end)]

        base_ret = H.run_strategy(baseline_weight_fn, window=win, data=data)
        var_ret = H.run_strategy(variant_weight_fn, window=win, data=data)

        rows = {
            "baseline (renorm)": full_metrics(base_ret, cash, close, sigs, baseline_weight_fn),
            "drop-to-safe (var)": full_metrics(var_ret, cash, close, sigs, variant_weight_fn),
        }
        out.append(f"\n## SLEEVE ({win}) -- mooex T+1, 10bps")
        out.append("```")
        out.append(fmt_table(rows, ["baseline (renorm)", "drop-to-safe (var)"]))
        out.append("```")
        if win == "clean":
            out.append("\n### Per-crisis (sleeve, clean) cum return + maxDD")
            out.append("```")
            out.append(crisis_breakdown(base_ret, var_ret, cash))
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
    print("Building baseline blend ...")
    art_base = BD.build_artifacts(bpanel, ndx_panel, bstart, bend, include_records=False)

    print("Building variant blend (monkeypatched CPM) ...")
    _orig = cpm_live.compute_target_weights
    cpm_live.compute_target_weights = variant_compute_target_weights
    try:
        art_var = BD.build_artifacts(bpanel, ndx_panel, bstart, bend, include_records=False)
    finally:
        cpm_live.compute_target_weights = _orig

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
        "baseline (renorm)": blend_metrics(art_base),
        "drop-to-safe (var)": blend_metrics(art_var),
    }
    out.append(f"\n## BLEND 60/20/20 (clean {bstart.date()}..{bend.date()}) "
               "-- close-to-close T+1, 10bps; BULL+NDX identical")
    out.append("```")
    out.append(fmt_table(brows, ["baseline (renorm)", "drop-to-safe (var)"]))
    out.append("```")
    out.append("\n### Per-crisis (blend, clean)")
    out.append("```")
    out.append(crisis_breakdown(art_base.blend, art_var.blend, bcash))
    out.append("```")

    report = "\n".join(out)
    print("\n" + report)
    rp = ROOT / "research" / "cpm_npos4_droptosafe_findings_raw.txt"
    rp.write_text(report)
    print(f"\n[written] {rp}")


if __name__ == "__main__":
    main()
