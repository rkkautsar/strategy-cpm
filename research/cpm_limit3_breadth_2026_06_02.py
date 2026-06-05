"""Exploratory backtest: CPM 'limit breadth to 3 slots' (denom 3) vs current
renormalize and drop-to-safe -- removing the n_pos=3->4 exposure cliff.

THE DISCONTINUITY
-----------------
Current rule: risky_fraction = min(n_pos,4)/4 with min-var 3-of-4 at n_pos=4.
  n_pos=3 -> 3 names @ 25% = 75% risky.
  n_pos=4 -> min-var picks 3 names, renormalized to 33.3% each = 100% risky.
Same ~3 names held, but exposure jumps 75% -> 100%. That step is the cliff:
the 4th positive momentum signal flips the book from 75% to fully invested
without adding a 4th name.

CONFIGS (full CPM mechanism otherwise identical: TIP canary, vol-adj Faber
rank, EW, SHV/IEF safe):
  A. CURRENT (gate)     top-4 pool, min-var 3-of-4 @ n_pos=4, denom 4,
                        renormalize survivors. Reproduces anchor 1.255673.
  B. DROP-TO-SAFE       top-4 pool, min-var 3-of-4 @ n_pos=4, dropped slot ->
                        safe (denom 4): n_pos=4 -> 3x25% + 25% safe (75% cap).
  C. LIMIT-3 + MIN-VAR  candidate pool top-4 by momentum, min-var picks 3,
                        DENOM 3 (risky_fraction=min(n_pos,3)/3, per-name 1/3).
                        n_pos>=3 -> 3 names @ 1/3 = 100% (min-var swaps which 3
                        at n_pos=4); n_pos=2 -> 67%+33% safe; n_pos=1 -> 33%+67%
                        safe. NO n_pos=3->4 jump.
  D. LIMIT-3 PLAIN      top-3 by momentum directly (no min-var), denom 3,
                        per-name 1/3. Same breadth scaling as C, holds the 3
                        highest-momentum. Isolates min-var value at 3 slots.

NOTE: C/D are MORE AGGRESSIVE at low breadth (denom 3: n_pos=1->33%,
n_pos=2->67%) vs current/drop-to-safe (denom 4: 25%, 50%).

RESEARCH-ONLY. Does not edit prod. Sleeve-level focus (mooex T+1, 10bps/side).
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

MODES = ("current", "drop_to_safe", "limit3_minvar", "limit3_plain")
LABELS = {
    "current": "A current(denom4)",
    "drop_to_safe": "B drop-to-safe",
    "limit3_minvar": "C limit3+minvar",
    "limit3_plain": "D limit3 plain",
}


# --------------------------------------------------------------------------
# Unified core: faithful copy of compute_target_weights through the ranking /
# positive filter, then a mode switch for selection + sizing. The "current"
# branch is a byte-for-byte replica of prod (gate-verified below).
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

    positive_picks = list(positive.index)  # ranked desc by vol-adj momentum
    n_pos = len(positive_picks)

    # ---- selection + sizing per mode ----
    if mode in ("current", "drop_to_safe"):
        # denom 4; min-var 3-of-4 at n_pos==4
        if n_pos == 4:
            picks = _min_var_subset(close_panel, sig_d, positive_picks, CORR_LOOKBACK_DAYS, 3)
        else:
            picks = positive_picks
        if mode == "drop_to_safe" and n_pos == 4:
            risky_fraction = len(picks) / 4.0       # 0.75 cap
        else:
            risky_fraction = min(n_pos, 4) / 4.0    # prod
    elif mode == "limit3_minvar":
        # denom 3; cap at 3 names, min-var chooses 3-of-4 at n_pos==4
        if n_pos == 4:
            picks = _min_var_subset(close_panel, sig_d, positive_picks, CORR_LOOKBACK_DAYS, 3)
        else:
            picks = positive_picks            # n_pos in {1,2,3}
        risky_fraction = min(n_pos, 3) / 3.0
    elif mode == "limit3_plain":
        # denom 3; top-3 by momentum directly (no min-var)
        picks = positive_picks[:3]
        risky_fraction = min(n_pos, 3) / 3.0
    else:
        raise ValueError(mode)

    safe_fraction = 1.0 - risky_fraction
    risky_w = {t: 1.0 / len(picks) for t in picks}
    out = {t: w * risky_fraction for t, w in risky_w.items()}
    if safe_fraction > 0:
        out[safe] = out.get(safe, 0.0) + safe_fraction

    return out, tuple(picks), "RISK_ON", safe, n_pos


def make_weight_fn(mode: str):
    def fn(close_panel, sig_d):
        out, *_ = _core(close_panel, sig_d, mode)
        return out
    return fn


# --------------------------------------------------------------------------
# Gate: 'current' replica must reproduce prod compute_target_weights exactly.
# --------------------------------------------------------------------------
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
def extra_metrics(daily: pd.Series, cash: pd.Series) -> dict:
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


def npos_stats(close, sigs, mode="current") -> dict:
    counts = {1: 0, 2: 0, 3: 0, 4: 0}
    risk_on = 0
    total = 0
    for sig_d in sigs:
        _, _, regime, _, n_pos = _core(close, sig_d, mode)
        total += 1
        if regime == "RISK_ON":
            risk_on += 1
            counts[n_pos] = counts.get(n_pos, 0) + 1
    return {"total": total, "risk_on": risk_on, "counts": counts}


def full_metrics(returns, cash, close, sigs, weight_fn) -> dict:
    m = cpm_live.perf_metrics(returns, cash)
    em = extra_metrics(returns, cash)
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


def exposure_by_npos_table() -> str:
    """Deterministic risky-exposure (% invested) by n_pos and #names, per rule."""
    # (risky_fraction, n_names) per n_pos
    def cur(n):  # denom 4, min-var3 at n=4
        nm = 3 if n == 4 else n
        return min(n, 4) / 4.0, nm
    def dts(n):
        nm = 3 if n == 4 else n
        rf = (3 / 4.0) if n == 4 else min(n, 4) / 4.0
        return rf, nm
    def lim(n):
        nm = min(n, 3)
        return min(n, 3) / 3.0, nm
    rules = {"A current": cur, "B drop-safe": dts, "C/D limit3": lim}
    lines = ["n_pos".ljust(8) + "".join(k.rjust(16) for k in rules)]
    lines.append("-" * len(lines[0]))
    for n in (1, 2, 3, 4):
        cells = []
        for k, f in rules.items():
            rf, nm = f(n)
            cells.append(f"{rf*100:.1f}% / {nm}nm".rjust(16))
        lines.append(str(n).ljust(8) + "".join(cells))
    lines.append("")
    lines.append("(% = risky exposure invested; nm = number of risky names)")
    lines.append("CLIFF check n_pos 3->4 (same ~3 names): "
                 "A 75%->100% JUMP | B 75%->75% flat | C/D 100%->100% flat")
    return "\n".join(lines)


def main():
    print("Loading harness data ...")
    data = H.load_data()
    cash = data.cash
    close = data.panel

    anc = H.verify_anchor(data=data)
    print(f"[ok] anchor Sharpe={anc['Sharpe']:.6f} MaxDD={anc['MaxDD']:.6f} Calmar={anc['Calmar']:.6f}")
    verify_current_matches_prod(data)

    out = ["# CPM limit-breadth-to-3 vs current renormalize / drop-to-safe -- exploratory\n"]
    out.append(f"Gate: prod CPM anchor Sharpe={anc['Sharpe']:.6f} (target 1.255673) reproduced.\n")

    # ---- Consistency: exposure-by-n_pos (deterministic from rule) ----
    out.append("## (i) Risky-exposure by n_pos -- consistency / cliff check")
    out.append("```")
    out.append(exposure_by_npos_table())
    out.append("```")

    # ---- n_pos distribution (selection identical across A/B/C-minvar; D differs only
    #      in which 3 held at n_pos=4, not in n_pos counts) ----
    out.append("\n## (ii) n_pos distribution (selection-stage breadth)")
    for win, start in (("clean", data.clean_start), ("ext", data.ext_start)):
        midx = (pd.DataFrame({"x": 1}, index=close.index)
                .groupby(pd.Grouper(freq="ME")).tail(1).index)
        sigs = midx[(midx >= start) & (midx <= data.end)]
        st = npos_stats(close, sigs, "current")
        c = st["counts"]
        ro = st["risk_on"]
        out.append(f"\n{win} ({start.date()}..{data.end.date()}): "
                   f"total={st['total']} risk-on={ro} defensive={st['total']-ro}")
        if ro:
            out.append("  RISK_ON n_pos counts {1,2,3,4}: " + str(c))
            out.append("  share of risk-on: " + ", ".join(
                f"n={k}:{c[k]/ro*100:.1f}%" for k in (1, 2, 3, 4)))
            out.append(f"  low-breadth (n_pos<=2) = {(c[1]+c[2])/ro*100:.1f}% of risk-on "
                       "(where C/D denom-3 aggression bites)")

    # ---- Sleeve metrics for A/B/C/D, clean + ext ----
    weight_fns = {m: make_weight_fn(m) for m in MODES}
    for win in ("clean", "ext"):
        start = data.clean_start if win == "clean" else data.ext_start
        midx = (pd.DataFrame({"x": 1}, index=close.index)
                .groupby(pd.Grouper(freq="ME")).tail(1).index)
        sigs = midx[(midx >= start) & (midx <= data.end)]
        rows = {}
        for m in MODES:
            ret = H.run_strategy(weight_fns[m], window=win, data=data)
            rows[LABELS[m]] = full_metrics(ret, cash, close, sigs, weight_fns[m])
        out.append(f"\n## SLEEVE metrics ({win}) -- mooex T+1, 10bps/side")
        out.append("```")
        out.append(fmt_table(rows, [LABELS[m] for m in MODES]))
        out.append("```")

    report = "\n".join(out)
    print("\n" + report)
    rp = ROOT / "research" / "cpm_limit3_breadth_2026_06_02_raw.txt"
    rp.write_text(report)
    print(f"\n[written] {rp}")


if __name__ == "__main__":
    main()
