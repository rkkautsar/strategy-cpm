"""Aggressive tier: replace min-variance pair with TOP-MOMENTUM when bull state fires.

Tier structure:
  DEFENSIVE  (HYG- AND TIP-)                                -> 100% best safe
  NORMAL     (default)                                       -> FCP-15 min-variance pair (50/50)
  AGGRESSIVE (HYG+ AND TIP+ AND EEM+ AND SPY+)              -> top-momentum mode

Aggressive mode variants:
  AGGR_top1     : 100% single best momentum asset
  AGGR_top2_ew  : Top-2 by momentum, equal-weight 50/50 (no min-variance)
  AGGR_top3_ew  : Top-3 EW
  AGGR_top1_qld : Top-1; if it's QQQ -> use QLD (2x) instead
  AGGR_top2_qld : Top-2 EW; if either is QQQ -> swap to QLD
  AGGR_top1_lev : Top-1 + add 25% QLD overlay (gross 125%)

Compare to:
  BASE (production with FCP-15 min-var, no aggressive tier)
  AGGR_swap15qld (prior winner: 85% FCP + 15% QLD when X6 fires)
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import fcp_live as fcp  # type: ignore
from fcp_live import (
    RISKY_UNIVERSE, SAFE_POOL, CANARY_ASSETS, DEFAULT_CASH,
    load_panel, run_fcp_backtest, perf_metrics, sig_13612W,
)

ALIASES = {"AGG": "AGG_stitched", "HYG": "HYG_stitched"}
ORIGINAL_COMPUTE = fcp.compute_target_weights

_STATE = {"aggr_mode": None, "full_panel": None, "qld_in_universe": False, "qld_price": None}


def get_canary_state_full(monthly, sig_d, canaries):
    state = {}
    for c in canaries:
        col = ALIASES.get(c, c)
        if col not in monthly.columns:
            return None
        v = sig_13612W(monthly[col].loc[:sig_d])
        if pd.isna(v):
            return None
        state[c] = bool(v > 0)
    return state


def aggr_fires(monthly_full, sig_d):
    """X6: HYG+ AND TIP+ AND EEM+ AND SPY+."""
    state = get_canary_state_full(monthly_full, sig_d, ["HYG", "TIP", "EEM", "SPY"])
    if state is None:
        return False
    return all(state.values())


def patched_compute(close_panel, sig_d, prev_pair=None, universe=None,
                     safe_pool=None, canary_assets=None):
    """Tiered: defensive / normal / aggressive (top-momentum)."""
    universe = universe or RISKY_UNIVERSE
    safe_pool = safe_pool or SAFE_POOL
    canary_assets = canary_assets or CANARY_ASSETS

    monthly = close_panel.loc[:sig_d].resample("ME").last()
    safe = fcp.best_safe(monthly, sig_d, safe_pool)

    # Defensive check (HYG- AND TIP-)
    canary_scores = []
    for c in canary_assets:
        if c not in monthly.columns:
            continue
        s = sig_13612W(monthly[c])
        if pd.notna(s):
            canary_scores.append(s)
    if not canary_scores:
        return {safe: 1.0}, None, "DEFENSIVE", safe
    n_pos = sum(1 for s in canary_scores if s > 0)
    if n_pos == 0:
        return {safe: 1.0}, None, "DEFENSIVE", safe

    # Aggressive check (HYG+ AND TIP+ AND EEM+ AND SPY+)
    full_panel = _STATE["full_panel"]
    monthly_full = full_panel.loc[:sig_d].resample("ME").last()
    is_aggr = aggr_fires(monthly_full, sig_d)

    # Score available risky
    score = fcp.faber_sma_xs(monthly)
    avail = [t for t in universe
             if t in score.index and pd.notna(score[t])
             and pd.notna(close_panel.loc[sig_d].get(t, np.nan) if sig_d in close_panel.index else np.nan)]
    if not avail:
        return {safe: 1.0}, None, "DEFENSIVE", safe

    sa = score.loc[avail]
    za = fcp.zscore(sa)
    ranked = sa.sort_values(ascending=False)

    if is_aggr:
        mode = _STATE["aggr_mode"]
        # Pick top-momentum (positive only)
        positive = ranked[ranked > 0]
        if len(positive) == 0:
            return {safe: 1.0}, None, "DEFENSIVE", safe

        if mode == "top1":
            return {positive.index[0]: 1.0}, (positive.index[0], positive.index[0]), "AGGRESSIVE", safe
        if mode == "top2_ew":
            picks = positive.index[:2].tolist()
            if len(picks) == 1:
                return {picks[0]: 0.5, safe: 0.5}, None, "AGGRESSIVE", safe
            return {picks[0]: 0.5, picks[1]: 0.5}, (picks[0], picks[1]), "AGGRESSIVE", safe
        if mode == "top3_ew":
            picks = positive.index[:3].tolist()
            if len(picks) < 2:
                if len(picks) == 1:
                    return {picks[0]: 0.5, safe: 0.5}, None, "AGGRESSIVE", safe
                return {safe: 1.0}, None, "AGGRESSIVE", safe
            w = 1.0 / len(picks)
            return {p: w for p in picks}, tuple(picks[:2]), "AGGRESSIVE", safe
        if mode == "top1_qld":
            top = positive.index[0]
            if top == "QQQ":
                return {"QLD": 1.0}, ("QLD", "QLD"), "AGGRESSIVE", safe
            return {top: 1.0}, (top, top), "AGGRESSIVE", safe
        if mode == "top2_qld":
            picks = positive.index[:2].tolist()
            if len(picks) == 1:
                return {picks[0]: 0.5, safe: 0.5}, None, "AGGRESSIVE", safe
            replaced = ["QLD" if p == "QQQ" else p for p in picks]
            return {replaced[0]: 0.5, replaced[1]: 0.5}, tuple(replaced[:2]), "AGGRESSIVE", safe
        if mode == "top2_mom_weighted":
            picks = positive.index[:2].tolist()
            if len(picks) < 2:
                if len(picks) == 1:
                    return {picks[0]: 0.5, safe: 0.5}, None, "AGGRESSIVE", safe
                return {safe: 1.0}, None, "AGGRESSIVE", safe
            # Weight by momentum (raw score, shifted to positive)
            scores = positive.iloc[:2].values
            # Use raw faber SMA distance as weights; if any negative or near-zero shift
            w_raw = np.maximum(scores, 0.001)
            w = w_raw / w_raw.sum()
            return {picks[0]: float(w[0]), picks[1]: float(w[1])}, (picks[0], picks[1]), "AGGRESSIVE", safe
        if mode == "top2_mom_weighted_qld":
            picks = positive.index[:2].tolist()
            if len(picks) < 2:
                if len(picks) == 1:
                    return {picks[0]: 0.5, safe: 0.5}, None, "AGGRESSIVE", safe
                return {safe: 1.0}, None, "AGGRESSIVE", safe
            scores = positive.iloc[:2].values
            w_raw = np.maximum(scores, 0.001)
            w = w_raw / w_raw.sum()
            replaced = ["QLD" if p == "QQQ" else p for p in picks]
            return {replaced[0]: float(w[0]), replaced[1]: float(w[1])}, tuple(replaced[:2]), "AGGRESSIVE", safe
        if mode == "top3_mom_weighted":
            picks = positive.index[:3].tolist()
            if len(picks) < 2:
                if len(picks) == 1:
                    return {picks[0]: 0.5, safe: 0.5}, None, "AGGRESSIVE", safe
                return {safe: 1.0}, None, "AGGRESSIVE", safe
            scores = positive.iloc[:len(picks)].values
            w_raw = np.maximum(scores, 0.001)
            w = w_raw / w_raw.sum()
            return {p: float(wi) for p, wi in zip(picks, w)}, tuple(picks[:2]), "AGGRESSIVE", safe
        if mode == "equity_top2_mom_weighted":
            equity_only_idx = [t for t in positive.index if t not in ("GLD", "TLT")]
            picks = equity_only_idx[:2]
            if len(picks) < 2:
                if len(picks) == 1:
                    return {picks[0]: 0.5, safe: 0.5}, None, "AGGRESSIVE", safe
                return {safe: 1.0}, None, "AGGRESSIVE", safe
            scores = np.array([positive[p] for p in picks])
            w_raw = np.maximum(scores, 0.001)
            w = w_raw / w_raw.sum()
            return {picks[0]: float(w[0]), picks[1]: float(w[1])}, (picks[0], picks[1]), "AGGRESSIVE", safe
        if mode == "equity_top2_ew":
            equity_only = [t for t in positive.index if t not in ("GLD", "TLT")]
            picks = equity_only[:2]
            if len(picks) < 2:
                if len(picks) == 1:
                    return {picks[0]: 0.5, safe: 0.5}, None, "AGGRESSIVE", safe
                return {safe: 1.0}, None, "AGGRESSIVE", safe
            return {picks[0]: 0.5, picks[1]: 0.5}, (picks[0], picks[1]), "AGGRESSIVE", safe
        if mode == "equity_top3_ew":
            equity_only = [t for t in positive.index if t not in ("GLD", "TLT")]
            picks = equity_only[:3]
            if len(picks) < 2:
                if len(picks) == 1:
                    return {picks[0]: 0.5, safe: 0.5}, None, "AGGRESSIVE", safe
                return {safe: 1.0}, None, "AGGRESSIVE", safe
            w = 1.0 / len(picks)
            return {p: w for p in picks}, tuple(picks[:2]), "AGGRESSIVE", safe
        if mode == "equity_min_var_pair":
            equity_only = [t for t in positive.index if t not in ("GLD", "TLT")]
            if len(equity_only) < 2:
                if len(equity_only) == 1:
                    return {equity_only[0]: 0.5, safe: 0.5}, None, "AGGRESSIVE", safe
                return {safe: 1.0}, None, "AGGRESSIVE", safe
            new_pick = fcp.min_vol_pair(close_panel.loc[:sig_d, equity_only],
                                          equity_only, fcp.CORR_LOOKBACK_DAYS)
            if new_pick is None:
                return {equity_only[0]: 1.0}, None, "AGGRESSIVE", safe
            return {new_pick[0]: 0.5, new_pick[1]: 0.5}, new_pick, "AGGRESSIVE", safe
        if mode == "fcp_with_qld_in_universe":
            # Normal min-var pair selection but with QLD added to candidate pool
            # Bonus: QLD ranked alongside others, selected on merit
            ext_universe = list(universe) + ["QLD"]
            ext_avail = [t for t in ext_universe
                         if t in score.index and pd.notna(score[t])
                         and pd.notna(close_panel.loc[sig_d].get(t, np.nan) if sig_d in close_panel.index else np.nan)]
            ext_sa = score.loc[ext_avail]
            ext_ranked = ext_sa.sort_values(ascending=False)
            top_k = max(2, min(fcp.TOP_K_CANDIDATES, len(ext_ranked)))
            ext_positive = ext_ranked.iloc[:top_k][lambda s: s > 0]
            if len(ext_positive) < 2:
                if len(ext_positive) == 1:
                    return {ext_positive.index[0]: 0.5, safe: 0.5}, None, "AGGRESSIVE", safe
                return {safe: 1.0}, None, "AGGRESSIVE", safe
            cands = list(ext_positive.index)
            new_pick = fcp.min_vol_pair(close_panel.loc[:sig_d, cands], cands, fcp.CORR_LOOKBACK_DAYS)
            if new_pick is None:
                return {cands[0]: 1.0}, None, "AGGRESSIVE", safe
            return {new_pick[0]: 0.5, new_pick[1]: 0.5}, new_pick, "AGGRESSIVE", safe

    # NORMAL mode: production min-variance pair (exact production logic)
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


def add_qld_to_panel(panel):
    """Fetch and add QLD to panel for run_fcp_backtest universe access."""
    qld = yf.Ticker("QLD").history(period="max", auto_adjust=True)["Close"]
    qld.index = pd.DatetimeIndex(qld.index).tz_localize(None)
    qld = qld.reindex(panel.index, method="ffill")
    panel = panel.copy()
    panel["QLD"] = qld
    return panel


def main():
    out_path = Path(__file__).parent / "aggressive_tier_top_mom.log"
    log_lines = []
    def log(s=""):
        log_lines.append(s); print(s)

    log("=" * 110)
    log("AGGRESSIVE TIER: replace min-var pair with TOP-MOMENTUM when X6 bull state fires")
    log("X6: HYG+ AND TIP+ AND EEM+ AND SPY+ (strict 4-positive)")
    log("=" * 110)

    panel = load_panel(start=pd.Timestamp("1999-01-01"))
    panel = add_qld_to_panel(panel)
    log(f"Panel: {panel.index[0].date()} -> {panel.index[-1].date()}, QLD added")

    start = pd.Timestamp("2008-09-30")
    end = panel.index[-1]

    # Baseline (production, no aggressive tier)
    fcp.compute_target_weights = ORIGINAL_COMPUTE
    base_rets, _ = run_fcp_backtest(panel, start, end)
    base_m = perf_metrics(base_rets)
    log("")
    log(f"BASE (production):  Sh={base_m['sharpe']:+.3f}  CAGR={base_m['cagr']*100:+.2f}%  "
        f"Vol={base_m['vol']*100:.2f}%  DD={base_m['max_drawdown']*100:+.2f}%")
    log("")

    # Switch to patched engine
    fcp.compute_target_weights = patched_compute
    _STATE["full_panel"] = panel

    modes = [
        ("top2_ew",                    "Top-2 momentum EW (50/50)"),
        ("top2_mom_weighted",          "Top-2 momentum-weighted (z-score proportional)"),
        ("top2_mom_weighted_qld",      "Top-2 mom-weighted (swap QQQ->QLD)"),
        ("top3_mom_weighted",          "Top-3 momentum-weighted"),
        ("top1",                       "Top-1 momentum (100% single)"),
        ("equity_top2_mom_weighted",   "Top-2 mom-weighted from EQUITY-ONLY"),
    ]

    log("=" * 110)
    log("AGGRESSIVE MODE RESULTS")
    log("=" * 110)
    log("")
    log(f"  {'Mode':<55s}  Sh      CAGR%   DD%      d_Sh    d_CAGR    d_DD")
    log("  " + "-" * 105)
    for mode, label in modes:
        _STATE["aggr_mode"] = mode
        rets, _ = run_fcp_backtest(panel, start, end)
        m = perf_metrics(rets)
        log(f"  {label:<55s}  {m['sharpe']:+.3f}  {m['cagr']*100:+5.2f}  "
            f"{m['max_drawdown']*100:+6.2f}   {m['sharpe']-base_m['sharpe']:+.3f}  "
            f"{(m['cagr']-base_m['cagr'])*100:+5.2f}pp   {(m['max_drawdown']-base_m['max_drawdown'])*100:+5.2f}pp")
    log("")
    log(f"  {'BASE (no aggressive tier, current production)':<55s}  "
        f"{base_m['sharpe']:+.3f}  {base_m['cagr']*100:+5.2f}  {base_m['max_drawdown']*100:+6.2f}    0.000   +0.00pp    +0.00pp")

    fcp.compute_target_weights = ORIGINAL_COMPUTE
    log("")
    log("=" * 110)
    with open(out_path, "w") as f:
        f.write("\n".join(log_lines))
    print(f"\nLog: {out_path}")


if __name__ == "__main__":
    main()
