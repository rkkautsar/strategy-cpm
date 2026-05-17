#!/usr/bin/env python3
"""
higher_vol_concentration.py
============================
EXPERIMENT: Higher-CAGR FCP variants via concentration (no leverage on vol-target).

Hypothesis: Higher TARGET_VOL + concentration (single best asset, inverse-vol
weighting, drop partial-safe fill) increases CAGR without borrowing, trading
drawdown for return. Tests whether signal concentration adds alpha beyond the
vol-target uplift alone.

Universe & fixed params (identical to production):
  RISKY_UNIVERSE (15): QQQ IGM SPMO XLE XRT COWZ VBR SPHQ XMMO XMHQ XLV VEA VWO GLD TLT
  HOLD_BUFFER=2.5, TOP_K=7, CORR_LOOKBACK=378d, VOL_LOOKBACK=63d
  MAX_LEVERAGE=1.0 (de-risk only), COST=10bps/side

Experiments:
  1. pair_mode @ TARGET_VOL=0.15:
       A. pair_50_50   -- min-var pair, equal weight (production selection)
       B. single       -- top momentum-ranked asset, 100%
       C. triple_equal -- min-var triple, 1/3 each
  2. pair_inv_vol vs pair_50_50 @ TARGET_VOL=0.15
       pair_inv_vol: same pair selection, weight by 1/vol(63d) renormalized
  3. partial_safe_mode @ TARGET_VOL=0.15:
       half -- 50% asset + 50% safe when only 1 positive (production)
       full -- 100% to single positive asset (no safe fill)
  4. All 8 combinations (pair_mode x partial_safe) @ TARGET_VOL=0.15;
       identify winner by Sharpe on Live-18y
  5. TARGET_VOL sweep [0.10,0.12,0.14,0.16,0.18,0.20] on winning variant

Windows:
  Live-18y     : 2008-09-30 (primary)
  Extended-28y : 1997-08-31 (secondary, proxy-stitched)

Output:
  strategy_fcp/research/higher_vol_concentration.log
"""
from __future__ import annotations

import sys
import time
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

# Import ONLY non-mutating helpers / data loader from production (no engine side-effects).
from strategy_fcp.fcp_live import (
    load_panel,
    RISKY_UNIVERSE, SAFE_POOL, CANARY_ASSETS, DEFAULT_CASH,
    faber_sma_xs, sig_13612W, best_safe, min_vol_pair,
)

LOG_PATH = Path(__file__).parent / "higher_vol_concentration.log"

# ---------- Fixed production constants (unchanged) ----------------------------
HOLD_BUFFER   = 2.5
TOP_K         = 7
CORR_LOOKBACK = 378
VOL_LOOKBACK  = 63
MAX_LEVERAGE  = 1.0
COST_BPS      = 10
UNIVERSE      = RISKY_UNIVERSE   # 15 assets

# ---------- Windows -----------------------------------------------------------
LIVE_START   = pd.Timestamp("2008-09-30")
HYBRID_START = pd.Timestamp("1997-08-31")

# ---------- Logging -----------------------------------------------------------
_lines: list[str] = []

def log(s: str = "") -> None:
    _lines.append(s)
    print(s, flush=True)

def flush_log() -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text("\n".join(_lines) + "\n", encoding="utf-8")


# ---------- Metrics -----------------------------------------------------------

def ulcer_index_pct(eq: pd.Series) -> float:
    """RMS of %-drawdown-from-peak. Matches fcp_with_2z_buffer.py convention."""
    roll_max = eq.cummax()
    dd_pct   = (eq / roll_max - 1.0) * 100.0
    return float(np.sqrt((dd_pct ** 2).mean()))


def max_dd_duration_days(eq: pd.Series) -> int:
    """Longest consecutive trading-day streak below prior peak."""
    peak       = eq.cummax()
    underwater = (eq < peak)
    max_dur, cur = 0, 0
    for u in underwater:
        if u:
            cur += 1
            if cur > max_dur:
                max_dur = cur
        else:
            cur = 0
    return max_dur


def calc_metrics(daily_ret: pd.Series) -> dict:
    r = daily_ret.dropna()
    if r.empty:
        return {}
    eq   = (1.0 + r).cumprod()
    n_y  = len(r) / 252.0
    cagr = eq.iloc[-1] ** (1.0 / n_y) - 1.0 if n_y > 0 else float("nan")
    vol  = r.std(ddof=0) * np.sqrt(252)
    sh   = (r.mean() * 252) / vol if vol > 0 else float("nan")
    mdd  = (eq / eq.cummax() - 1.0).min()
    ui   = ulcer_index_pct(eq)
    upi  = (cagr * 100.0) / ui if ui > 1e-9 else float("nan")   # CAGR% / Ulcer%
    dur  = max_dd_duration_days(eq)
    dn   = r[r < 0].std(ddof=0) * np.sqrt(252) if (r < 0).sum() > 1 else float("nan")
    sortino = (r.mean() * 252) / dn if dn and dn > 0 else float("nan")
    return dict(cagr=cagr, vol=vol, sharpe=sh, maxdd=mdd,
                upi=upi, dd_dur=dur, sortino=sortino, years=round(n_y, 1))


# ---------- Concentration helpers ---------------------------------------------

def _zscore(s: pd.Series) -> pd.Series:
    sd = s.std()
    return (s - s.mean()) / sd if sd > 0 else pd.Series(0.0, index=s.index)


def min_vol_triple(daily: pd.DataFrame, candidates: list, lookback: int) -> tuple | None:
    """Triple with lowest equal-weight (1/3:1/3:1/3) portfolio variance over lookback."""
    if len(candidates) < 3:
        return None
    rets = daily[candidates].iloc[-lookback:].pct_change().dropna(how="all")
    if len(rets) < 30:
        return None
    cov  = rets.cov()
    best, best_var = None, float("inf")
    for a, b, c in combinations(candidates, 3):
        # var_p = (1/9)(var_a+var_b+var_c+2cov_ab+2cov_ac+2cov_bc)
        v = (1.0 / 9.0) * (
            cov.loc[a, a] + cov.loc[b, b] + cov.loc[c, c]
            + 2 * cov.loc[a, b] + 2 * cov.loc[a, c] + 2 * cov.loc[b, c]
        )
        if pd.notna(v) and v < best_var:
            best_var = v
            best = (a, b, c)
    return best


def inv_vol_weights(daily: pd.DataFrame, tickers: list, vol_lookback: int) -> dict[str, float]:
    """Weights proportional to 1/sigma_i (renormalized) using vol_lookback-day realized vol."""
    rets  = daily[tickers].iloc[-vol_lookback:].pct_change().dropna(how="all")
    vols  = rets.std(ddof=0) * np.sqrt(252)
    inv   = {t: 1.0 / v for t, v in vols.items() if v > 0}
    total = sum(inv.values())
    if total == 0:
        return {t: 1.0 / len(tickers) for t in tickers}
    return {t: w / total for t, w in inv.items()}


# ---------- Hold-buffer helper ------------------------------------------------

def _apply_hold_buffer(
    new_set: list,
    prev_selection: tuple | None,
    avail: list,
    sa: pd.Series,
    za: pd.Series,
    hold_buffer: float,
    n_slots: int,
) -> list:
    """
    For each prior member not already in new_set, block the weakest new entrant
    if that entrant doesn't beat the prior by hold_buffer z-score units.
    Production-identical logic extended to n_slots > 2.
    """
    if prev_selection is None or hold_buffer < 1e-9:
        return new_set
    result = list(new_set)
    for prior in prev_selection:
        if prior in result or prior not in avail:
            continue
        if sa.get(prior, -np.inf) <= 0:
            continue
        z_prior = za.get(prior, float("nan"))
        if not pd.notna(z_prior):
            continue
        swap_cands = [x for x in result if x not in prev_selection]
        if not swap_cands:
            continue
        swap   = min(swap_cands, key=lambda x: za.get(x, float("inf")))
        z_swap = za.get(swap, float("nan"))
        if not pd.notna(z_swap):
            continue
        if z_swap - z_prior < hold_buffer:
            result.remove(swap)
            result.append(prior)
    return result[:n_slots]


# ---------- Core allocation logic ---------------------------------------------

def compute_weights_v2(
    close_panel: pd.DataFrame,
    sig_d: pd.Timestamp,
    prev_selection: tuple | None,
    *,
    pair_mode: str,
    partial_safe_mode: str,
    top_k: int = TOP_K,
    hold_buffer: float = HOLD_BUFFER,
    corr_lookback: int = CORR_LOOKBACK,
    vol_lookback: int = VOL_LOOKBACK,
    universe: list = UNIVERSE,
    safe_pool: list = SAFE_POOL,
    canary_assets: list = CANARY_ASSETS,
) -> tuple[dict, tuple | None, str, str]:
    """
    Returns (weights_dict, new_selection, regime, safe_ticker).

    pair_mode:
      pair_50_50   -- min-var pair, 50/50 (production)
      single       -- top-ranked asset, 100%
      triple_equal -- min-var triple, 1/3 each
      pair_inv_vol -- min-var pair, weighted by 1/vol(63d)

    partial_safe_mode (applies when exactly 1 positive asset exists, pair/triple modes):
      half -- 50% asset + 50% safe (production)
      full -- 100% to asset (no safe fill)

    Note: for 'single', partial_safe is irrelevant (1 asset always sufficient).
    """
    monthly = close_panel.loc[:sig_d].resample("ME").last()
    safe    = best_safe(monthly, sig_d, safe_pool)

    # Canary check (strict majority -- same as production)
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
    if n_pos <= len(canary_scores) // 2:
        return {safe: 1.0}, None, "DEFENSIVE", safe

    # Faber SMA-10m ranking
    score = faber_sma_xs(monthly)
    avail = [
        t for t in universe
        if t in score.index
        and pd.notna(score[t])
        and pd.notna(close_panel.loc[sig_d, t] if sig_d in close_panel.index else float("nan"))
    ]
    if not avail:
        return {safe: 1.0}, None, "DEFENSIVE", safe

    sa       = score.loc[avail]
    za       = _zscore(sa)
    ranked   = sa.sort_values(ascending=False)
    top_k_n  = max(2, min(top_k, len(ranked)))
    positive = ranked.iloc[:top_k_n][lambda s: s > 0]

    # ---- single: picks 1 asset; partial_safe irrelevant ----
    if pair_mode == "single":
        if positive.empty:
            return {safe: 1.0}, None, "DEFENSIVE", safe
        candidates = list(positive.index)
        new_best   = candidates[0]
        # z-buffer: hold prior if new rank-1 doesn't clear the threshold
        if prev_selection and len(prev_selection) >= 1 and hold_buffer > 1e-9:
            prior = prev_selection[0]
            if prior != new_best and prior in avail and sa.get(prior, -float("inf")) > 0:
                z_prior = za.get(prior, float("nan"))
                z_new   = za.get(new_best, float("nan"))
                if pd.notna(z_prior) and pd.notna(z_new) and (z_new - z_prior) < hold_buffer:
                    new_best = prior
        return {new_best: 1.0}, (new_best,), "RISK_ON", safe

    # ---- pair_50_50 / pair_inv_vol ----
    if pair_mode in ("pair_50_50", "pair_inv_vol"):
        if positive.empty:
            return {safe: 1.0}, None, "DEFENSIVE", safe
        candidates = list(positive.index)
        if len(candidates) == 1:
            if partial_safe_mode == "half":
                return {candidates[0]: 0.5, safe: 0.5}, None, "RISK_ON", safe
            else:
                return {candidates[0]: 1.0}, None, "RISK_ON", safe
        # 2+ candidates -> min-var pair
        new_pick = min_vol_pair(close_panel.loc[:sig_d, candidates], candidates, corr_lookback)
        if new_pick is None:
            return {candidates[0]: 1.0}, None, "RISK_ON", safe
        new_set  = _apply_hold_buffer(list(new_pick), prev_selection, avail, sa, za, hold_buffer, 2)
        new_pick = tuple(new_set[:2])
        if pair_mode == "pair_50_50":
            return {new_pick[0]: 0.5, new_pick[1]: 0.5}, new_pick, "RISK_ON", safe
        else:  # pair_inv_vol
            sub = close_panel.loc[:sig_d, list(new_pick)]
            ww  = inv_vol_weights(sub, list(new_pick), vol_lookback)
            return ww, new_pick, "RISK_ON", safe

    # ---- triple_equal ----
    if pair_mode == "triple_equal":
        if positive.empty:
            return {safe: 1.0}, None, "DEFENSIVE", safe
        candidates = list(positive.index)
        if len(candidates) == 1:
            if partial_safe_mode == "half":
                return {candidates[0]: 0.5, safe: 0.5}, None, "RISK_ON", safe
            else:
                return {candidates[0]: 1.0}, None, "RISK_ON", safe
        if len(candidates) == 2:
            # Fallback to pair (no safe fill regardless of partial_safe_mode)
            new_pick = min_vol_pair(close_panel.loc[:sig_d, candidates], candidates, corr_lookback)
            if new_pick is None:
                new_pick = tuple(candidates[:2])
            new_set  = _apply_hold_buffer(list(new_pick), prev_selection, avail, sa, za, hold_buffer, 2)
            p = tuple(new_set[:2])
            return {p[0]: 0.5, p[1]: 0.5}, p, "RISK_ON", safe
        # 3+ candidates -> min-var triple
        new_pick = min_vol_triple(close_panel.loc[:sig_d, candidates], candidates, corr_lookback)
        if new_pick is None:
            new_pick = tuple(candidates[:3])
        new_set  = _apply_hold_buffer(list(new_pick), prev_selection, avail, sa, za, hold_buffer, 3)
        new_pick = tuple(new_set[:3])
        w = 1.0 / len(new_pick)
        return {a: w for a in new_pick}, new_pick, "RISK_ON", safe

    raise ValueError(f"Unknown pair_mode: {pair_mode!r}")


# ---------- Backtest engine ---------------------------------------------------

def run_backtest_raw(
    panel: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
    pair_mode: str,
    partial_safe_mode: str,
    top_k: int = TOP_K,
    hold_buffer: float = HOLD_BUFFER,
    corr_lookback: int = CORR_LOOKBACK,
    vol_lookback: int = VOL_LOOKBACK,
    cost_bps: float = COST_BPS,
    universe: list = None,
) -> pd.Series:
    """Run FCP engine without vol-target overlay. Returns raw daily return series."""
    universe = universe or UNIVERSE
    cols  = sorted(set(universe + SAFE_POOL + CANARY_ASSETS + [DEFAULT_CASH]) & set(panel.columns))
    close = panel[cols]

    monthly_idx  = (pd.DataFrame({"x": 1}, index=close.index)
                    .groupby(pd.Grouper(freq="ME")).tail(1))
    signal_dates = monthly_idx.index[
        (monthly_idx.index >= start) & (monthly_idx.index <= end)
    ].tolist()

    weights_history: list[dict] = []
    prev_selection: tuple | None = None

    for i, sig_d in enumerate(signal_dates):
        w, new_sel, regime, safe = compute_weights_v2(
            close, sig_d, prev_selection,
            pair_mode=pair_mode,
            partial_safe_mode=partial_safe_mode,
            top_k=top_k,
            hold_buffer=hold_buffer,
            corr_lookback=corr_lookback,
            vol_lookback=vol_lookback,
            universe=universe,
        )
        prev_selection = new_sel
        future = close.index[close.index > sig_d]
        if len(future) < 2:
            continue
        apply_from = future[1]
        if i + 1 < len(signal_dates):
            nxt     = signal_dates[i + 1]
            nxt_fut = close.index[close.index > nxt]
            end_apply = nxt_fut[1] if len(nxt_fut) >= 2 else end
        else:
            end_apply = end
        weights_history.append(
            {"apply_from": apply_from, "end_apply": end_apply, "weights": w}
        )

    if not weights_history:
        return pd.Series(dtype=float)

    all_assets = sorted({a for h in weights_history for a in h["weights"]})
    df_w = pd.DataFrame(0.0, index=close.index,
                        columns=[a for a in all_assets if a in close.columns])
    for h in weights_history:
        mask = (close.index >= h["apply_from"]) & (close.index < h["end_apply"])
        for a, ww in h["weights"].items():
            if a in df_w.columns:
                df_w.loc[mask, a] = ww

    daily_ret = close.ffill().pct_change()
    common    = [a for a in df_w.columns if a in daily_ret.columns]
    raw       = (df_w[common] * daily_ret[common]).sum(axis=1, min_count=1).fillna(0.0)

    # Trade costs at each rebalance
    for i in range(len(weights_history)):
        prev_w = weights_history[i - 1]["weights"] if i > 0 else {}
        curr_w = weights_history[i]["weights"]
        keys   = set(curr_w) | set(prev_w)
        tov    = sum(abs(curr_w.get(k, 0.0) - prev_w.get(k, 0.0)) for k in keys)
        af     = weights_history[i]["apply_from"]
        if af in raw.index:
            raw.loc[af] -= tov * cost_bps / 10_000.0

    return raw.loc[(raw.index >= start) & (raw.index <= end)]


def apply_vol_target(
    raw: pd.Series,
    target_vol: float,
    max_leverage: float = MAX_LEVERAGE,
    vol_lookback: int = VOL_LOOKBACK,
) -> tuple[pd.Series, float]:
    """
    Apply vol-target overlay to raw returns.
    Returns (scaled_returns, clip_pct) where clip_pct = % of days desired scale > max_lev.
    """
    realized = raw.rolling(vol_lookback).std() * np.sqrt(252)
    desired  = target_vol / realized.replace(0, float("nan"))
    scale    = desired.clip(upper=max_leverage).shift(1).fillna(1.0)
    scaled   = raw * scale
    valid    = desired.dropna()
    clip_pct = 100.0 * (valid > max_leverage).sum() / len(valid) if len(valid) else 0.0
    return scaled, float(clip_pct)


# ---------- Variant runner ----------------------------------------------------

def run_variant(
    panel: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
    label: str,
    pair_mode: str,
    partial_safe_mode: str,
    target_vol: float,
    **kw,
) -> dict:
    t0     = time.time()
    raw    = run_backtest_raw(panel, start, end, pair_mode, partial_safe_mode, **kw)
    scaled, clip_pct = apply_vol_target(raw, target_vol)
    m      = calc_metrics(scaled)
    m.update(
        label=label,
        target_vol=target_vol,
        pair_mode=pair_mode,
        partial_safe_mode=partial_safe_mode,
        clip_pct=clip_pct,
        elapsed=time.time() - t0,
    )
    return m


def _fv(v, fmt):
    try:
        return format(v, fmt)
    except Exception:
        return "  nan"


def fmt_row(m: dict) -> str:
    return (
        f"  {m.get('label',''):<46s}"
        f"  tv={m['target_vol']:.2f}"
        f"  Sh {_fv(m.get('sharpe'), '+.3f'):>7s}"
        f"  CAGR {_fv(m.get('cagr', 0)*100, '+6.2f'):>7s}%"
        f"  rVol {_fv(m.get('vol', 0)*100, '5.2f'):>6s}%"
        f"  DD {_fv(m.get('maxdd', 0)*100, '+6.2f'):>7s}%"
        f"  UPI {_fv(m.get('upi', 0), '+5.2f'):>7s}"
        f"  DDur {m.get('dd_dur', 0):4d}d"
        f"  clip {m.get('clip_pct', 0):4.1f}%"
        f"  [{m.get('elapsed', 0):.1f}s]"
    )


# ---------- Main --------------------------------------------------------------

def main() -> None:
    log("=" * 120)
    log("FCP CONCENTRATION EXPERIMENTS -- higher_vol_concentration.py")
    log(f"Run date : {pd.Timestamp.today().date()}")
    log(f"Universe : {UNIVERSE}")
    log(
        f"Fixed    : HOLD_BUFFER={HOLD_BUFFER}, TOP_K={TOP_K}, "
        f"CORR_LOOKBACK={CORR_LOOKBACK}d, VOL_LOOKBACK={VOL_LOOKBACK}d, "
        f"MAX_LEVERAGE={MAX_LEVERAGE}, COST={COST_BPS}bps/side"
    )
    log("=" * 120)

    log("\nLoading panel ...")
    panel = load_panel(start=pd.Timestamp("1995-01-01"))
    end   = panel.index.max()
    log(f"Panel: {panel.index[0].date()} -> {end.date()}, {len(panel.columns)} assets")

    # Production reference
    log("\n" + "-" * 120)
    log("PRODUCTION REFERENCE -- TARGET_VOL=0.10, pair_50_50, partial_safe=half")
    log("-" * 120)
    for win_label, win_start in [("Live-18y", LIVE_START), ("Extended-28y", HYBRID_START)]:
        m = run_variant(panel, win_start, end, f"PROD ref [{win_label}]",
                        pair_mode="pair_50_50", partial_safe_mode="half", target_vol=0.10)
        log(fmt_row(m))

    # EXP 1: pair_mode @ TARGET_VOL=0.15
    log("\n" + "-" * 120)
    log("EXP 1: pair_mode comparison -- TARGET_VOL=0.15")
    log("  A. pair_50_50   -- min-var pair, 50/50 (production selection, higher TV)")
    log("  B. single       -- top momentum-ranked asset, 100%")
    log("  C. triple_equal -- min-var triple, 1/3 each")
    log("-" * 120)
    exp1_modes = [
        ("pair_50_50",   "A pair_50_50"),
        ("single",       "B single"),
        ("triple_equal", "C triple_equal"),
    ]
    for win_label, win_start in [("Live-18y", LIVE_START), ("Extended-28y", HYBRID_START)]:
        log(f"\n  [{win_label}]")
        for mode, lbl in exp1_modes:
            m = run_variant(panel, win_start, end, f"{lbl} [{win_label}]",
                            pair_mode=mode, partial_safe_mode="half", target_vol=0.15)
            log(fmt_row(m))

    # EXP 2: inverse-vol weighting @ TARGET_VOL=0.15
    log("\n" + "-" * 120)
    log("EXP 2: inverse-vol pair weighting vs 50/50 -- TARGET_VOL=0.15")
    log("-" * 120)
    exp2_modes = [
        ("pair_50_50",   "pair_50_50   (equal weight)"),
        ("pair_inv_vol", "pair_inv_vol (1/vol weight)"),
    ]
    for win_label, win_start in [("Live-18y", LIVE_START), ("Extended-28y", HYBRID_START)]:
        log(f"\n  [{win_label}]")
        for mode, lbl in exp2_modes:
            m = run_variant(panel, win_start, end, f"{lbl} [{win_label}]",
                            pair_mode=mode, partial_safe_mode="half", target_vol=0.15)
            log(fmt_row(m))

    # EXP 3: partial_safe_mode @ TARGET_VOL=0.15
    log("\n" + "-" * 120)
    log("EXP 3: partial_safe_mode -- half vs full @ TARGET_VOL=0.15")
    log("  half: 50% asset + 50% safe when 1 positive (production)")
    log("  full: 100% to asset, no safe fill")
    log("-" * 120)
    for win_label, win_start in [("Live-18y", LIVE_START), ("Extended-28y", HYBRID_START)]:
        log(f"\n  [{win_label}]")
        for ps, lbl in [("half", "partial_safe=half"), ("full", "partial_safe=full")]:
            m = run_variant(panel, win_start, end, f"{lbl} [{win_label}]",
                            pair_mode="pair_50_50", partial_safe_mode=ps, target_vol=0.15)
            log(fmt_row(m))

    # EXP 4: all 8 combos
    log("\n" + "-" * 120)
    log("EXP 4: all combinations (pair_mode x partial_safe) @ TARGET_VOL=0.15")
    log("-" * 120)
    combos = [
        ("pair_50_50",   "half",  "pair_50_50   + half   [baseline]"),
        ("pair_50_50",   "full",  "pair_50_50   + full"),
        ("single",       "half",  "single       + half"),
        ("single",       "full",  "single       + full"),
        ("triple_equal", "half",  "triple_equal + half"),
        ("triple_equal", "full",  "triple_equal + full"),
        ("pair_inv_vol", "half",  "pair_inv_vol + half"),
        ("pair_inv_vol", "full",  "pair_inv_vol + full"),
    ]
    exp4_live: list[dict] = []
    for win_label, win_start in [("Live-18y", LIVE_START), ("Extended-28y", HYBRID_START)]:
        log(f"\n  [{win_label}]")
        for pm, ps, lbl in combos:
            m = run_variant(panel, win_start, end, f"{lbl} [{win_label}]",
                            pair_mode=pm, partial_safe_mode=ps, target_vol=0.15)
            log(fmt_row(m))
            if win_label == "Live-18y":
                exp4_live.append({**m, "pm": pm, "ps": ps})

    winner = max(exp4_live, key=lambda x: x["sharpe"])
    win_pm = winner["pm"]
    win_ps = winner["ps"]
    log(f"\n  >> EXP4 Winner (Live-18y Sharpe): pair_mode={win_pm!r}  partial_safe={win_ps!r}")
    log(f"     {fmt_row(winner)}")

    # EXP 5: TARGET_VOL sweep on winner
    vol_sweep = [0.10, 0.12, 0.14, 0.16, 0.18, 0.20]
    log("\n" + "-" * 120)
    log(f"EXP 5: TARGET_VOL sweep on winner (pair_mode={win_pm!r}, partial_safe={win_ps!r})")
    log(f"  Sweep: {vol_sweep}")
    log("-" * 120)
    exp5_live: list[dict] = []
    for win_label2, win_start in [("Live-18y", LIVE_START), ("Extended-28y", HYBRID_START)]:
        log(f"\n  [{win_label2}]")
        for tv in vol_sweep:
            m = run_variant(panel, win_start, end, f"tv={tv:.2f} [{win_label2}]",
                            pair_mode=win_pm, partial_safe_mode=win_ps, target_vol=tv)
            log(fmt_row(m))
            if win_label2 == "Live-18y":
                exp5_live.append(m)

    best_cal = min(exp5_live,
                   key=lambda x: abs(x["vol"] - x["target_vol"]) + x["clip_pct"] / 1000)
    log(
        f"\n  >> Best calibrated tv (realized~target, low clip): "
        f"TARGET_VOL={best_cal['target_vol']:.2f}  "
        f"realized={best_cal['vol']*100:.2f}%  clip={best_cal['clip_pct']:.1f}%"
    )

    # Final summary table
    log("\n" + "=" * 120)
    log("FINAL SUMMARY TABLE -- Live-18y window, all TARGET_VOL=0.15 unless noted")
    hdr = (
        f"  {'variant':<46s} | {'tv':>4} | {'rVol%':>6} | {'Sharpe':>7} | "
        f"{'CAGR%':>7} | {'MaxDD%':>7} | {'UPI':>6} | {'DDur':>6} | {'clip%':>6}"
    )
    log(hdr)
    log("  " + "-" * 110)

    summary_specs = [
        ("PROD baseline tv=0.10",         "pair_50_50",   "half", 0.10),
        ("A  pair_50_50   tv=0.15",       "pair_50_50",   "half", 0.15),
        ("B  single       tv=0.15",       "single",       "half", 0.15),
        ("C  triple_equal tv=0.15",       "triple_equal", "half", 0.15),
        ("   pair_inv_vol tv=0.15",       "pair_inv_vol", "half", 0.15),
        ("   pair_50_50  +full tv=0.15",  "pair_50_50",   "full", 0.15),
        ("B+ single      +full tv=0.15",  "single",       "full", 0.15),
        ("C+ triple      +full tv=0.15",  "triple_equal", "full", 0.15),
        ("   inv_vol     +full tv=0.15",  "pair_inv_vol", "full", 0.15),
        (f"WINNER {win_pm}+{win_ps} tv={best_cal['target_vol']:.2f}",
         win_pm, win_ps, best_cal["target_vol"]),
    ]

    for lbl, pm, ps, tv in summary_specs:
        m = run_variant(panel, LIVE_START, end, lbl,
                        pair_mode=pm, partial_safe_mode=ps, target_vol=tv)
        log(
            f"  {lbl:<46s} | {tv:.2f} | {_fv(m.get('vol',0)*100,'6.2f')} | "
            f"{_fv(m.get('sharpe'),'+7.3f')} | "
            f"{_fv(m.get('cagr',0)*100,'+7.2f')}% | "
            f"{_fv(m.get('maxdd',0)*100,'+7.2f')}% | "
            f"{_fv(m.get('upi',0),'+6.2f')} | "
            f"{m.get('dd_dur', 0):5d}d | {m.get('clip_pct', 0):5.1f}%"
        )

    log("\n" + "=" * 120)
    log("Done.")
    flush_log()
    log(f"\nLog written: {LOG_PATH}")


if __name__ == "__main__":
    main()
