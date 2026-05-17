"""Comprehensive canary rule sweep.

Iterates over a broader rule space than v1/v2:
 - All 2-canary "any positive" rules (28 pairs from 8 candidates)
 - All 2-canary "both positive" rules
 - 3-canary "majority of 3" rules (top 10 most-promising trios)
 - 3-canary "any 1 of 3 positive" rules
 - Single-canary risk-on rules (8)
 - NOCAN baseline
 - CURRENT baseline (SPY+TIP both+)

Then leave-one-year robustness check on top 5 candidates.

Same engine setup as canary_rule_variants_v2 (faithful production with
HYG_stitched + AGG_stitched access via full panel injection).
"""
from __future__ import annotations
import sys
from itertools import combinations
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import fcp_live as fcp  # type: ignore
from fcp_live import (
    RISKY_UNIVERSE, SAFE_POOL, CANARY_ASSETS, DEFAULT_CASH,
    load_panel, run_fcp_backtest, perf_metrics, sig_13612W,
)

# Candidate canaries (with HYG and AGG aliased to stitched series)
CANDIDATES = ["SPY", "TIP", "HYG", "AGG", "EFA", "EEM", "GLD", "TLT"]
ALIASES = {"HYG": "HYG_stitched", "AGG": "AGG_stitched"}

ORIGINAL_COMPUTE = fcp.compute_target_weights
_CURRENT = {"fn": None, "canaries": [], "full_panel": None}


def get_canary_state(monthly_panel, sig_d, canaries):
    state = {}
    for c in canaries:
        col = ALIASES.get(c, c)
        if col not in monthly_panel.columns:
            return None
        s = sig_13612W(monthly_panel[col].loc[:sig_d])
        if pd.isna(s):
            return None
        state[c] = bool(s > 0)
    return state


def patched_compute(close_panel, sig_d, prev_pair=None, universe=None,
                     safe_pool=None, canary_assets=None):
    """Faithful production logic with custom canary rule."""
    universe = universe or RISKY_UNIVERSE
    safe_pool = safe_pool or SAFE_POOL

    monthly = close_panel.loc[:sig_d].resample("ME").last()
    safe = fcp.best_safe(monthly, sig_d, safe_pool)

    rule_fn = _CURRENT["fn"]
    cans = _CURRENT["canaries"]
    full_panel = _CURRENT["full_panel"]
    if cans:
        monthly_full = full_panel.loc[:sig_d].resample("ME").last()
        state = get_canary_state(monthly_full, sig_d, cans)
        if state is None or not rule_fn(state):
            return {safe: 1.0}, None, "DEFENSIVE", safe

    score = fcp.faber_sma_xs(monthly)
    avail = [t for t in universe
             if t in score.index and pd.notna(score[t])
             and pd.notna(close_panel.loc[sig_d].get(t, np.nan) if sig_d in close_panel.index else np.nan)]
    if not avail:
        return {safe: 1.0}, None, "DEFENSIVE", safe

    sa = score.loc[avail]
    za = fcp.zscore(sa)
    ranked = sa.sort_values(ascending=False)
    top_k = max(2, min(fcp.TOP_K_CANDIDATES, len(ranked)))
    positive = ranked.iloc[:top_k][lambda s: s > 0]

    if len(positive) < 2:
        if len(positive) == 1:
            return {positive.index[0]: 0.5, safe: 0.5}, None, "RISK_ON", safe
        return {safe: 1.0}, None, "DEFENSIVE", safe

    candidates = list(positive.index)
    new_pick = fcp.min_vol_pair(close_panel.loc[:sig_d, candidates], candidates, fcp.CORR_LOOKBACK_DAYS)
    if new_pick is None:
        return {candidates[0]: 1.0}, None, "RISK_ON", safe

    if prev_pair is not None and fcp.HOLD_BUFFER > 1e-9:
        new_set = list(new_pick)
        for prior in prev_pair:
            if prior in new_set or prior not in avail:
                continue
            if sa.get(prior, -np.inf) <= 0:
                continue
            z_prior = za.get(prior, np.nan)
            if pd.isna(z_prior):
                continue
            swap_cands = [x for x in new_set if x not in prev_pair]
            if not swap_cands:
                continue
            swap = min(swap_cands, key=lambda x: za.get(x, np.inf))
            z_swap = za.get(swap, np.nan)
            if pd.isna(z_swap):
                continue
            if z_swap - z_prior < fcp.HOLD_BUFFER:
                new_set.remove(swap)
                new_set.append(prior)
        new_pick = tuple(new_set[:2])

    return {new_pick[0]: 0.5, new_pick[1]: 0.5}, new_pick, "RISK_ON", safe


# ---- Rule builders ----

def rule_all_positive(canaries):
    def f(s):
        return all(s.get(c, False) for c in canaries)
    return f

def rule_any_positive(canaries):
    def f(s):
        return any(s.get(c, False) for c in canaries)
    return f

def rule_majority(canaries):
    """Strict majority: n_pos > len/2."""
    threshold = len(canaries) / 2.0
    def f(s):
        n_pos = sum(1 for c in canaries if s.get(c, False))
        return n_pos > threshold
    return f


def build_rules():
    """Generate the rule space."""
    rules = []
    # Baselines
    rules.append(("CURRENT (SPY+TIP both+)", ["SPY","TIP"], rule_all_positive(["SPY","TIP"])))
    rules.append(("NOCAN (always RO)", [], lambda s: True))
    # Single-canary
    for c in CANDIDATES:
        rules.append((f"SINGLE {c}+", [c], rule_any_positive([c])))
    # 2-canary all-positive (28 pairs)
    for pair in combinations(CANDIDATES, 2):
        label = "+".join(pair) + " both+"
        rules.append((f"2AL {label}", list(pair), rule_all_positive(list(pair))))
    # 2-canary any-positive (28 pairs)
    for pair in combinations(CANDIDATES, 2):
        label = "+".join(pair) + " any+"
        rules.append((f"2AN {label}", list(pair), rule_any_positive(list(pair))))
    # 3-canary majority (10 promising trios that include HYG or bond signals)
    trios = [
        ("SPY","TIP","HYG"), ("SPY","TIP","AGG"), ("SPY","HYG","AGG"),
        ("TIP","HYG","AGG"), ("SPY","TIP","EEM"), ("SPY","TIP","EFA"),
        ("SPY","TIP","TLT"), ("SPY","HYG","TLT"), ("HYG","AGG","TLT"),
        ("SPY","EEM","AGG"),
    ]
    for trio in trios:
        label = "+".join(trio) + " maj(2of3)"
        rules.append((f"3MAJ {label}", list(trio), rule_majority(list(trio))))
    # 3-canary any-positive (same trios)
    for trio in trios:
        label = "+".join(trio) + " any+"
        rules.append((f"3AN {label}", list(trio), rule_any_positive(list(trio))))
    return rules


def run_variant(panel, start, end, label, canaries, rule_fn):
    _CURRENT["fn"] = rule_fn
    _CURRENT["canaries"] = canaries
    _CURRENT["full_panel"] = panel
    rets, _ = run_fcp_backtest(panel, start, end)
    m = perf_metrics(rets)
    # Regime %
    monthly_idx = pd.DataFrame({"x": 1}, index=panel.index).groupby(pd.Grouper(freq="ME")).tail(1)
    sigs = monthly_idx.index[(monthly_idx.index >= start) & (monthly_idx.index <= end)].tolist()
    if not canaries:
        pct_ro = 100.0
    else:
        n_ro = 0; n_total = 0
        for sd in sigs:
            mon = panel.loc[:sd].resample("ME").last()
            state = get_canary_state(mon, sd, canaries)
            n_total += 1
            if state is not None and rule_fn(state):
                n_ro += 1
        pct_ro = n_ro / max(1, n_total) * 100
    return m, pct_ro, rets


def leave_one_year(panel, label, canaries, rule_fn, start, end):
    """Compute Sharpe with each year dropped."""
    _CURRENT["fn"] = rule_fn
    _CURRENT["canaries"] = canaries
    _CURRENT["full_panel"] = panel
    rets, _ = run_fcp_backtest(panel, start, end)
    years = sorted(rets.index.year.unique())
    base_sh = perf_metrics(rets)["sharpe"]
    deltas = {}
    for y in years:
        mask = rets.index.year != y
        sub = rets[mask]
        if len(sub) < 252:
            continue
        sh = perf_metrics(sub)["sharpe"]
        deltas[y] = sh - base_sh
    return base_sh, deltas


def main():
    out_path = Path(__file__).parent / "canary_rule_sweep.log"
    log_lines = []
    def log(s=""):
        log_lines.append(s); print(s)

    log("=" * 100)
    log("CANARY RULE COMPREHENSIVE SWEEP")
    log("Faithful production engine. FCP-15, HOLD_BUFFER=2.5, vol-target 10%, 10bps/side.")
    log("=" * 100)

    panel = load_panel(start=pd.Timestamp("1999-01-01"))
    log(f"Panel: {panel.index[0].date()} -> {panel.index[-1].date()}")
    log("")

    fcp.compute_target_weights = patched_compute

    rules = build_rules()
    log(f"Testing {len(rules)} rules on LIVE (2008-09-30) and FULL (2001-08-30) windows")
    log("")

    end = panel.index[-1]
    results = []  # (label, canaries, rule_fn, m_live, ro_live, m_full)
    for i, (label, cans, rfn) in enumerate(rules):
        try:
            m_live, ro_live, _ = run_variant(panel, pd.Timestamp("2008-09-30"), end, label, cans, rfn)
            m_full, _, _       = run_variant(panel, pd.Timestamp("2001-08-30"), end, label, cans, rfn)
            results.append((label, cans, rfn, m_live, ro_live, m_full))
            if (i+1) % 10 == 0:
                log(f"  ...completed {i+1}/{len(rules)}")
        except Exception as e:
            log(f"  ERROR on {label}: {e}")

    log("")
    log("=" * 100)
    log("TOP 15 BY LIVE-18Y SHARPE")
    log("=" * 100)
    log("")
    log(f"  {'Rule':<55s}  Sh_live  CAGR%  DD%      %RO   Sh_full  CAGR%  DD%")
    log("  " + "-" * 110)
    sorted_by_live = sorted(results, key=lambda r: -r[3]["sharpe"])
    for label, cans, rfn, m_l, ro, m_f in sorted_by_live[:15]:
        log(f"  {label:<55s}  {m_l['sharpe']:+.3f}  {m_l['cagr']*100:+5.1f}  "
            f"{m_l['max_drawdown']*100:+6.1f}  {ro:5.1f}   "
            f"{m_f['sharpe']:+.3f}  {m_f['cagr']*100:+5.1f}  {m_f['max_drawdown']*100:+6.1f}")
    log("")

    log("=" * 100)
    log("TOP 15 BY FULL-25Y SHARPE")
    log("=" * 100)
    log("")
    log(f"  {'Rule':<55s}  Sh_full  CAGR%  DD%      Sh_live  CAGR%  DD%   %RO")
    log("  " + "-" * 110)
    sorted_by_full = sorted(results, key=lambda r: -r[5]["sharpe"])
    for label, cans, rfn, m_l, ro, m_f in sorted_by_full[:15]:
        log(f"  {label:<55s}  {m_f['sharpe']:+.3f}  {m_f['cagr']*100:+5.1f}  "
            f"{m_f['max_drawdown']*100:+6.1f}  "
            f"{m_l['sharpe']:+.3f}  {m_l['cagr']*100:+5.1f}  {m_l['max_drawdown']*100:+6.1f}  {ro:5.1f}")
    log("")

    log("=" * 100)
    log("TOP 15 BY AVERAGE(Live, Full) SHARPE -- ROBUST CANDIDATES")
    log("=" * 100)
    log("")
    log(f"  {'Rule':<55s}  avg_Sh   Sh_live  Sh_full  CAGR_live%  CAGR_full%  DD_live%  DD_full%")
    log("  " + "-" * 120)
    by_avg = sorted(results, key=lambda r: -(r[3]["sharpe"] + r[5]["sharpe"]) / 2)
    top_avg = []
    for label, cans, rfn, m_l, ro, m_f in by_avg[:15]:
        avg = (m_l["sharpe"] + m_f["sharpe"]) / 2
        log(f"  {label:<55s}  {avg:+.3f}   {m_l['sharpe']:+.3f}   {m_f['sharpe']:+.3f}   "
            f"{m_l['cagr']*100:+6.1f}      {m_f['cagr']*100:+6.1f}      "
            f"{m_l['max_drawdown']*100:+6.1f}   {m_f['max_drawdown']*100:+6.1f}")
        top_avg.append((label, cans, rfn))
    log("")

    # Leave-one-year on top 5 by average Sharpe
    log("=" * 100)
    log("LEAVE-ONE-YEAR ROBUSTNESS (top 5 by avg Sharpe)")
    log("=" * 100)
    log("")
    for label, cans, rfn in top_avg[:5]:
        log(f"--- {label} ---")
        base_sh, deltas = leave_one_year(panel, label, cans, rfn,
                                          pd.Timestamp("2008-09-30"), end)
        log(f"  Live base Sharpe = {base_sh:+.3f}")
        sorted_deltas = sorted(deltas.items(), key=lambda x: abs(x[1]), reverse=True)
        log(f"  Max |dSh| from any single year removed: {abs(sorted_deltas[0][1]):.3f} (year {sorted_deltas[0][0]})")
        log(f"  Worst 3 year removals (rule needs them):")
        for y, d in sorted(deltas.items(), key=lambda x: x[1])[:3]:
            log(f"    drop {y}: dSh = {d:+.3f}")
        log(f"  Best 3 year removals (rule loses to them):")
        for y, d in sorted(deltas.items(), key=lambda x: -x[1])[:3]:
            log(f"    drop {y}: dSh = {d:+.3f}")
        log("")

    log("=" * 100)
    fcp.compute_target_weights = ORIGINAL_COMPUTE
    with open(out_path, "w") as f:
        f.write("\n".join(log_lines))
    print(f"\nLog: {out_path}")


if __name__ == "__main__":
    main()
