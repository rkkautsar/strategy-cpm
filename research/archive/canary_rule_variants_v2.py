"""Canary rule variants — v2 with PRODUCTION engine (faithful match to fcp_live).

Strategy: monkey-patch compute_target_weights to inject custom canary rule
instead of forking the engine. Ensures pair selection, hold-buffer, top-K logic
all match production exactly.

Variants:
  CURRENT    : SPY+TIP both must be positive (current rule)
  NOCAN      : No canary (always risk-on; trust engine internal risk-off)
  HYG_ONLY   : Risk-on iff HYG+ (single canary)
  OPT_D      : Defensive iff HYG- AND SPY+ AND TIP- (minimal crisis fuse)
  OPT_E      : Defensive iff HYG- AND SPY+ (simpler crisis fuse)
  HYG_TIP    : Risk-on iff HYG+ AND TIP+ (HYG replaces SPY)
  HYG_TIP_ANY: Risk-on iff HYG+ OR TIP+ (at least one bond signal positive)
"""
from __future__ import annotations
import sys
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

# ---- Custom canary state evaluator ----
EXTRA_CANARIES = ["HYG_stitched"]  # HYG aliased
ALIASES = {"HYG": "HYG_stitched"}

def get_canary_state(monthly_panel, sig_d, canaries):
    """Return dict {canary: bool} where bool = (13612W > 0)."""
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


# ---- Canary rules: (state: dict[str,bool]) -> bool (True = risk-on) ----

def rule_current(s): return s.get("SPY", False) and s.get("TIP", False)

def rule_nocan(s): return True

def rule_hyg_only(s): return s.get("HYG", False)

def rule_opt_d(s):
    # Defensive iff HYG- AND SPY+ AND TIP-
    if (not s.get("HYG", True)) and s.get("SPY", False) and (not s.get("TIP", True)):
        return False
    return True

def rule_opt_e(s):
    # Defensive iff HYG- AND SPY+
    if (not s.get("HYG", True)) and s.get("SPY", False):
        return False
    return True

def rule_hyg_tip(s): return s.get("HYG", False) and s.get("TIP", False)

def rule_hyg_tip_any(s): return s.get("HYG", False) or s.get("TIP", False)

VARIANTS = [
    ("CURRENT (SPY+TIP both+)",       ["SPY", "TIP"],       rule_current),
    ("NOCAN (no canary)",             [],                    rule_nocan),
    ("HYG_ONLY (HYG+)",               ["HYG"],              rule_hyg_only),
    ("OPT_D (def iff HYG-,SPY+,TIP-)", ["SPY","TIP","HYG"], rule_opt_d),
    ("OPT_E (def iff HYG-,SPY+)",     ["SPY","HYG"],        rule_opt_e),
    ("HYG_TIP (both+)",               ["HYG","TIP"],        rule_hyg_tip),
    ("HYG_TIP_ANY (either+)",         ["HYG","TIP"],        rule_hyg_tip_any),
]


# ---- Monkey-patch compute_target_weights to use custom rule ----

ORIGINAL_COMPUTE = fcp.compute_target_weights

# Hold current rule + canaries + full panel (for canaries not in close_panel)
_CURRENT_RULE = {"fn": rule_current, "canaries": ["SPY", "TIP"], "full_panel": None}

def patched_compute(close_panel, sig_d, prev_pair=None, universe=None,
                     safe_pool=None, canary_assets=None):
    """Replicate ORIGINAL_COMPUTE but use custom canary rule for risk-on/off check."""
    universe = universe or RISKY_UNIVERSE
    safe_pool = safe_pool or SAFE_POOL

    monthly = close_panel.loc[:sig_d].resample("ME").last()
    safe = fcp.best_safe(monthly, sig_d, safe_pool)

    # Evaluate custom canary rule -- use FULL panel for canaries not in close_panel
    rule_fn = _CURRENT_RULE["fn"]
    custom_canaries = _CURRENT_RULE["canaries"]
    full_panel = _CURRENT_RULE["full_panel"]
    if custom_canaries:
        # Use full_panel monthly for canary lookup, not close_panel
        if full_panel is not None:
            monthly_full = full_panel.loc[:sig_d].resample("ME").last()
            state = get_canary_state(monthly_full, sig_d, custom_canaries)
        else:
            state = get_canary_state(monthly, sig_d, custom_canaries)
        if state is None:
            return {safe: 1.0}, None, "DEFENSIVE", safe
        if not rule_fn(state):
            return {safe: 1.0}, None, "DEFENSIVE", safe
    # else: NOCAN, always proceed to pair selection

    # FROM HERE: REPLICATE production pair selection EXACTLY
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

    # Hold buffer (EXACT production logic)
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


def main():
    out_path = Path(__file__).parent / "canary_rule_variants_v2.log"
    log_lines = []
    def log(s=""):
        log_lines.append(s); print(s)

    log("=" * 100)
    log("CANARY RULE VARIANTS v2 -- PRODUCTION ENGINE (faithful)")
    log("Universe: FCP-15.  Engine: TOP_K=7, HOLD_BUFFER=2.5, vol-target 10%, 10bps/side")
    log("=" * 100)

    panel = load_panel(start=pd.Timestamp("1999-01-01"))
    log(f"Panel: {panel.index[0].date()} -> {panel.index[-1].date()}")
    log("")

    # Inject patched compute
    fcp.compute_target_weights = patched_compute

    results_live = []
    results_full = []

    for label, canaries, rule_fn in VARIANTS:
        _CURRENT_RULE["fn"] = rule_fn
        _CURRENT_RULE["canaries"] = canaries
        _CURRENT_RULE["full_panel"] = panel  # includes HYG_stitched, AGG_stitched, etc.

        # Live window 2008-09-30
        start = pd.Timestamp("2008-09-30")
        end = panel.index[-1]
        rets, _ = run_fcp_backtest(panel, start, end)
        m = perf_metrics(rets)

        # Compute regime distribution by re-checking signal dates
        monthly_idx = pd.DataFrame({"x": 1}, index=panel.index).groupby(pd.Grouper(freq="ME")).tail(1)
        signal_dates = monthly_idx.index[(monthly_idx.index >= start) & (monthly_idx.index <= end)].tolist()
        n_ro = 0; n_def = 0; n_ps = 0
        for sd in signal_dates:
            mon = panel.loc[:sd].resample("ME").last()
            if canaries:
                state = get_canary_state(mon, sd, canaries)
                if state is None or not rule_fn(state):
                    n_def += 1
                    continue
            # Counts as risk-on if rule allows (engine may still partial-safe)
            n_ro += 1
        total = max(1, n_ro + n_def)
        pct_ro = n_ro / total * 100

        log(f"{label}")
        log(f"  Live-18y:  Sh={m['sharpe']:+.3f}  CAGR={m['cagr']*100:+.2f}%  "
            f"Vol={m['vol']*100:.2f}%  DD={m['max_drawdown']*100:+.2f}%  "
            f"pct_RO={pct_ro:.1f}%")
        results_live.append((label, m, pct_ro))

        # Full window 2001-08-30
        start_f = pd.Timestamp("2001-08-30")
        rets_f, _ = run_fcp_backtest(panel, start_f, end)
        m_f = perf_metrics(rets_f)
        log(f"  Full-25y:  Sh={m_f['sharpe']:+.3f}  CAGR={m_f['cagr']*100:+.2f}%  "
            f"Vol={m_f['vol']*100:.2f}%  DD={m_f['max_drawdown']*100:+.2f}%")
        results_full.append((label, m_f))
        log("")

    log("=" * 100)
    log("LIVE 18y SUMMARY (ranked by Sharpe)")
    log("=" * 100)
    log("")
    log("  Rule                                         Sharpe   CAGR%    Vol%    MaxDD%    %RO")
    log("  " + "-" * 95)
    for label, m, ro in sorted(results_live, key=lambda r: -r[1]["sharpe"]):
        log(f"  {label:42s}  {m['sharpe']:+.3f}   {m['cagr']*100:+6.2f}   {m['vol']*100:5.2f}   "
            f"{m['max_drawdown']*100:+6.2f}    {ro:5.1f}")

    log("")
    log("=" * 100)
    log("FULL 25y SUMMARY (ranked by Sharpe)")
    log("=" * 100)
    log("")
    log("  Rule                                         Sharpe   CAGR%    Vol%    MaxDD%")
    log("  " + "-" * 95)
    for label, m in sorted(results_full, key=lambda r: -r[1]["sharpe"]):
        log(f"  {label:42s}  {m['sharpe']:+.3f}   {m['cagr']*100:+6.2f}   {m['vol']*100:5.2f}   "
            f"{m['max_drawdown']*100:+6.2f}")

    log("")
    log("=" * 100)

    # Restore original
    fcp.compute_target_weights = ORIGINAL_COMPUTE

    with open(out_path, "w") as f:
        f.write("\n".join(log_lines))
    print(f"\nLog: {out_path}")


if __name__ == "__main__":
    main()
