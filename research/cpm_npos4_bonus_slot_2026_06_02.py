"""Exploratory backtest: CPM n_pos=4 'purposeful breadth-bonus slot' vs current
renormalize and drop-to-safe.

THE IDEA
--------
Current rule at n_pos=4: min-var picks 3-of-4, then renormalizes survivors to
33.3% each -> 100% risky (breadth preserved, full invest, but per-name base
drifts from 25% to 33.3%, a "blind" renormalize).

This study keeps full-invest (100% risky) AND a consistent 25%-per-slot base,
but allocates the freed 25% slot PURPOSEFULLY to ONE of the 3 chosen names:
  two names stay 25%, the breadth-bonus name gets 25%+25% = 50%.
Two sub-variants pick which name gets the bonus:
  E-MOM    : highest vol-adjusted momentum (faber/rv_252d) of the 3 -> conviction tilt
  E-LOWVOL : lowest trailing realized vol (rv_252d) of the 3 -> safety tilt

CONFIGS (full CPM mechanism otherwise identical: TIP canary, vol-adj Faber rank,
EW, SHV/IEF safe; min-var still picks 3-of-4 at n_pos=4; only n_pos=4 weighting
differs; n_pos<4 unchanged from current = breadth-scaled partial-safe, 25%/name):
  A. CURRENT (gate)  min-var 3-of-4, renorm 33.3% each, 100% risky. Anchor 1.255673.
  B. DROP-TO-SAFE    min-var 3-of-4 @ 25% each + 25% safe (75% risky).
  E-MOM              min-var 3-of-4, base 25% each, freed 25% -> highest vol-adj-mom
                     name (-> 50/25/25, 100% risky).
  E-LOWVOL           min-var 3-of-4, base 25% each, freed 25% -> lowest rv_252d name
                     (-> 50/25/25, 100% risky).

RESEARCH-ONLY. Does not edit prod. Sleeve-level focus (mooex T+1, 10bps/side).
High overfit caution: single in-sample; the 50/25/25 tilt is a new DoF, chosen
a-priori with no tuning.
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

MODES = ("current", "drop_to_safe", "mom_bonus", "lowvol_bonus")
LABELS = {
    "current": "A current(33.3)",
    "drop_to_safe": "B drop-to-safe",
    "mom_bonus": "E-MOM 50/25/25",
    "lowvol_bonus": "E-LOWVOL 50/25/25",
}

CRISES = {
    "GFC_2007_10__2009_06": ("2007-10-01", "2009-06-30"),
    "COVID_2020_02__2020_06": ("2020-02-01", "2020-06-30"),
    "Y2022_bear": ("2022-01-01", "2022-12-31"),
    "Y2025_tariff": ("2025-01-01", "2025-05-22"),
}


# --------------------------------------------------------------------------
# Unified core: faithful copy of compute_target_weights through ranking /
# positive filter, then a mode switch for selection + sizing. The "current"
# branch is a byte-for-byte replica of prod (gate-verified below).
# --------------------------------------------------------------------------
def _core(close_panel, sig_d, mode: str):
    """Returns (weights, basket, regime, safe, n_pos)."""
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
    rv = {}
    for t in avail:
        v = daily_rets[t].loc[:sig_d].tail(252).std() * np.sqrt(252)
        if pd.isna(v) or v < 1e-9:
            v = 1.0
        rv[t] = float(v)
        scores[t] = float(faber[t]) / v
    sa = pd.Series(scores)  # vol-adj Faber score (ranking)
    ranked = sa.sort_values(ascending=False)
    top_k = max(2, min(TOP_K_CANDIDATES, len(ranked)))
    top = ranked.iloc[:top_k]
    positive = top[top.index.map(lambda t: faber.get(t, -np.inf) > 0)]

    if len(positive) == 0:
        return {safe: 1.0}, None, "DEFENSIVE", safe, None

    positive_picks = list(positive.index)
    n_pos = len(positive_picks)

    # ---- n_pos<4: identical across ALL modes (current breadth-scaled partial-safe) ----
    if n_pos < 4:
        picks = positive_picks
        risky_fraction = min(n_pos, 4) / 4.0
        safe_fraction = 1.0 - risky_fraction
        out = {t: (1.0 / len(picks)) * risky_fraction for t in picks}
        if safe_fraction > 0:
            out[safe] = out.get(safe, 0.0) + safe_fraction
        return out, tuple(picks), "RISK_ON", safe, n_pos

    # ---- n_pos==4: min-var 3-of-4, then mode-specific sizing ----
    picks = _min_var_subset(close_panel, sig_d, positive_picks, CORR_LOOKBACK_DAYS, 3)

    if mode == "current":
        # renormalize survivors to equal weight -> 33.3% each, 100% risky
        out = {t: 1.0 / len(picks) for t in picks}
        return out, tuple(picks), "RISK_ON", safe, n_pos

    if mode == "drop_to_safe":
        # 25% each + freed 25% to safe (75% risky)
        out = {t: 0.25 for t in picks}
        out[safe] = out.get(safe, 0.0) + 0.25
        return out, tuple(picks), "RISK_ON", safe, n_pos

    if mode in ("mom_bonus", "lowvol_bonus"):
        # base 25% each, freed 25% -> one chosen name (-> 50/25/25), 100% risky
        out = {t: 0.25 for t in picks}
        if mode == "mom_bonus":
            # highest vol-adj momentum among the 3
            bonus = max(picks, key=lambda t: sa.get(t, -np.inf))
        else:
            # lowest trailing realized vol among the 3
            bonus = min(picks, key=lambda t: rv.get(t, np.inf))
        out[bonus] += 0.25
        return out, tuple(picks), "RISK_ON", safe, n_pos

    raise ValueError(mode)


def make_weight_fn(mode: str):
    def fn(close_panel, sig_d):
        out, *_ = _core(close_panel, sig_d, mode)
        return out
    return fn


def verify_current_matches_prod(data) -> None:
    midx = (pd.DataFrame({"x": 1}, index=data.panel.index)
            .groupby(pd.Grouper(freq="ME")).tail(1).index)
    sigs = midx[(midx >= data.clean_start) & (midx <= data.end)]
    close = data.panel
    max_diff = 0.0
    for sig_d in sigs:
        prod, *_ = compute_target_weights(close, sig_d)
        mine, *_ = _core(close, sig_d, "current")
        for k in set(prod) | set(mine):
            max_diff = max(max_diff, abs(prod.get(k, 0.0) - mine.get(k, 0.0)))
    if max_diff > 1e-12:
        raise AssertionError(f"current replica != prod, max weight diff {max_diff:.2e}")
    print(f"[ok] current replica matches prod (max weight diff {max_diff:.2e})")


# --------------------------------------------------------------------------
# Metrics
# --------------------------------------------------------------------------
def extra_metrics(daily: pd.Series) -> dict:
    d = daily.dropna()
    downside = d[d < 0]
    dd_std = downside.std(ddof=0) * np.sqrt(252)
    sortino = (d.mean() * 252) / dd_std if dd_std > 0 else float("nan")
    q = np.quantile(d.values, 0.05)
    cvar95 = d[d <= q].mean()
    return {"Sortino": sortino, "CVaR95_daily": cvar95}


def turnover_avg(weight_fn, close, sigs) -> float:
    prev, tos = {}, []
    for sig_d in sigs:
        w = weight_fn(close, sig_d)
        keys = set(w) | set(prev)
        tos.append(sum(abs(w.get(k, 0.0) - prev.get(k, 0.0)) for k in keys))
        prev = w
    return float(np.mean(tos[1:])) if len(tos) > 1 else float(np.mean(tos))


def full_metrics(returns, cash, close, sigs, weight_fn) -> dict:
    m = cpm_live.perf_metrics(returns, cash)
    em = extra_metrics(returns)
    to = turnover_avg(weight_fn, close, sigs)
    return {
        "Sharpe": m["sharpe"], "exSharpe": m["excess_sharpe"], "Sortino": em["Sortino"],
        "CVaR95_d": em["CVaR95_daily"], "Calmar": m["calmar"], "Martin": m["martin"],
        "MaxDD": m["max_drawdown"], "CAGR": m["cagr"], "vol": m["vol"], "turnover": to,
    }


def fmt_table(rows: dict, order: list) -> str:
    cols = ["Sharpe", "exSharpe", "Sortino", "CVaR95_d", "Calmar", "Martin",
            "MaxDD", "CAGR", "vol", "turnover"]
    head = "config".ljust(20) + "".join(c.rjust(10) for c in cols)
    lines = [head, "-" * len(head)]
    for name in order:
        m = rows[name]
        cells = []
        for c in cols:
            v = m[c]
            if c in ("MaxDD", "CAGR", "vol", "CVaR95_d"):
                cells.append(f"{v*100:.2f}%".rjust(10))
            else:
                cells.append(f"{v:.3f}".rjust(10))
        lines.append(name.ljust(20) + "".join(cells))
    return "\n".join(lines)


def crisis_table(series_by_mode: dict) -> str:
    """Per-crisis MaxDD / total-return per mode."""
    names = [LABELS[m] for m in MODES]
    head = "crisis".ljust(26) + "".join(n.rjust(20) for n in names)
    lines = [head, "-" * len(head)]
    for ck, (a, b) in CRISES.items():
        cells = []
        for m in MODES:
            s = series_by_mode[m].loc[pd.Timestamp(a):pd.Timestamp(b)].dropna()
            if len(s) == 0:
                cells.append("n/a".rjust(20)); continue
            e = (1 + s).cumprod()
            mdd = float((e / e.cummax() - 1.0).min())
            ret = float(e.iloc[-1] - 1.0)
            cells.append(f"{mdd*100:.1f}%/{ret*100:+.1f}%".rjust(20))
        lines.append(ck.ljust(26) + "".join(cells))
    lines.append("")
    lines.append("(cells = MaxDD% / total-return% within window)")
    return "\n".join(lines)


def npos4_bonus_audit(close, sigs) -> str:
    """At n_pos=4, how often does E-MOM vs E-LOWVOL pick the SAME bonus name?
    And distribution of which slot (by momentum rank) gets the bonus."""
    same = 0
    n4 = 0
    mom_is_lowvol = 0
    for sig_d in sigs:
        _, picks_m, reg, _, n_pos = _core(close, sig_d, "mom_bonus")
        if reg != "RISK_ON" or n_pos != 4:
            continue
        n4 += 1
        wm, *_ = _core(close, sig_d, "mom_bonus")
        wl, *_ = _core(close, sig_d, "lowvol_bonus")
        bonus_m = max(wm, key=lambda k: wm[k]) if wm else None
        bonus_l = max(wl, key=lambda k: wl[k]) if wl else None
        if bonus_m == bonus_l:
            same += 1
    lines = [f"n_pos=4 months: {n4}"]
    if n4:
        lines.append(f"  E-MOM bonus == E-LOWVOL bonus (same name): {same} ({same/n4*100:.1f}%)")
        lines.append(f"  differ: {n4-same} ({(n4-same)/n4*100:.1f}%)")
    return "\n".join(lines)


def main():
    print("Loading harness data ...")
    data = H.load_data()
    cash = data.cash
    close = data.panel

    anc = H.verify_anchor(data=data)
    print(f"[ok] anchor Sharpe={anc['Sharpe']:.6f} MaxDD={anc['MaxDD']:.6f} Calmar={anc['Calmar']:.6f}")
    verify_current_matches_prod(data)

    out = ["# CPM n_pos=4 purposeful breadth-bonus slot vs renormalize / drop-to-safe -- exploratory\n"]
    out.append(f"Gate: prod CPM anchor Sharpe={anc['Sharpe']:.6f} (target 1.255673) reproduced.\n")

    out.append("## Per-name weight consistency at n_pos=4 (full mechanism otherwise identical)")
    out.append("```")
    out.append("A current   : 33.3 / 33.3 / 33.3   (100% risky; renorm drifts base off 25%)")
    out.append("B drop-safe : 25 / 25 / 25 + 25 safe (75% risky; consistent 25% base)")
    out.append("E-MOM       : 50 / 25 / 25          (100% risky; 25% base, bonus->hi vol-adj-mom)")
    out.append("E-LOWVOL    : 50 / 25 / 25          (100% risky; 25% base, bonus->lo rv_252d)")
    out.append("n_pos<4     : identical across all modes (breadth-scaled partial-safe, 25%/name)")
    out.append("```")

    weight_fns = {m: make_weight_fn(m) for m in MODES}

    for win in ("clean", "ext"):
        start = data.clean_start if win == "clean" else data.ext_start
        midx = (pd.DataFrame({"x": 1}, index=close.index)
                .groupby(pd.Grouper(freq="ME")).tail(1).index)
        sigs = midx[(midx >= start) & (midx <= data.end)]
        rows = {}
        series_by_mode = {}
        for m in MODES:
            ret = H.run_strategy(weight_fns[m], window=win, data=data)
            series_by_mode[m] = ret
            rows[LABELS[m]] = full_metrics(ret, cash, close, sigs, weight_fns[m])
        out.append(f"\n## SLEEVE metrics ({win}) -- mooex T+1, 10bps/side")
        out.append("```")
        out.append(fmt_table(rows, [LABELS[m] for m in MODES]))
        out.append("```")

        if win == "clean":
            out.append("\n## Per-crisis (clean curve)")
            out.append("```")
            out.append(crisis_table(series_by_mode))
            out.append("```")
            out.append("\n## n_pos=4 bonus-name audit (clean)")
            out.append("```")
            out.append(npos4_bonus_audit(close, sigs))
            out.append("```")

    report = "\n".join(out)
    print("\n" + report)
    rp = ROOT / "research" / "cpm_npos4_bonus_slot_2026_06_02_raw.txt"
    rp.write_text(report)
    print(f"\n[written] {rp}")


if __name__ == "__main__":
    main()
