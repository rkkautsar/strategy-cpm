#!/usr/bin/env python3
"""
canary_audit_and_breadth_tiering.py
====================================
EXPERIMENT: FCP canary design audit + breadth tiering.

Part A: SPY+TIP canary state forward predictive power (4 states x assets x 2 windows)
Part B: Alternative canary sets comparison (7 configs x production FCP engine)
Part C: Breadth tiering (5-level allocation using 4-canary SPY+VEA+EEM+AGG)

CRITICAL: Exploratory audit only. Does NOT modify fcp_live.py.

Output: strategy_fcp/research/canary_audit_and_breadth_tiering.log
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from strategy_fcp.fcp_live import (
    load_panel,
    RISKY_UNIVERSE, SAFE_POOL, DEFAULT_CASH,
    faber_sma_xs, sig_13612W, best_safe, min_vol_pair,
    HOLD_BUFFER, TOP_K_CANDIDATES, CORR_LOOKBACK_DAYS,
    TARGET_VOL, VOL_LOOKBACK_DAYS, MAX_LEVERAGE, COST_BPS_PER_SIDE,
)

LOG_PATH = Path(__file__).parent / "canary_audit_and_breadth_tiering.log"

# ---------- Production constants ----------
TOP_K    = TOP_K_CANDIDATES     # 7
HOLD_BUF = HOLD_BUFFER          # 2.5
CORR_LB  = CORR_LOOKBACK_DAYS   # 378
VOL_LB   = VOL_LOOKBACK_DAYS    # 63
TV_BASE  = TARGET_VOL           # 0.10
MAX_LEV  = MAX_LEVERAGE         # 1.0
COST_BPS = COST_BPS_PER_SIDE    # 10

# ---------- Windows ----------
LIVE_START = pd.Timestamp("2008-09-30")
FULL_START = pd.Timestamp("2001-08-30")

# ---------- Canary configs ----------
CANARY_PROD    = ["SPY", "TIP"]
CANARY_VAA4    = ["SPY", "VEA", "EEM", "AGG"]
CANARY_VAA4TIP = ["SPY", "VEA", "EEM", "AGG", "TIP"]
CANARY_SPY1    = ["SPY"]
CANARY_GLDTLT  = ["GLD", "TLT"]

# =====================================================================
# LOGGING
# =====================================================================
_lines: list[str] = []

def log(s: str = "") -> None:
    _lines.append(s)
    print(s, flush=True)

def flush_log() -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text("\n".join(_lines) + "\n", encoding="utf-8")

# =====================================================================
# METRICS
# =====================================================================
def calc_metrics(r: pd.Series) -> dict:
    r = r.dropna()
    if len(r) < 20:
        return dict(cagr=np.nan, vol=np.nan, sharpe=np.nan, maxdd=np.nan,
                    sortino=np.nan, years=0.0)
    eq   = (1.0 + r).cumprod()
    n_y  = len(r) / 252.0
    cagr = eq.iloc[-1] ** (1.0 / n_y) - 1.0
    vol  = r.std(ddof=0) * np.sqrt(252)
    sh   = (r.mean() * 252) / vol if vol > 0 else np.nan
    mdd  = (eq / eq.cummax() - 1.0).min()
    dn   = r[r < 0].std(ddof=0) * np.sqrt(252)
    so   = (r.mean() * 252) / dn if dn > 0 else np.nan
    return dict(cagr=cagr, vol=vol, sharpe=sh, maxdd=mdd, sortino=so, years=round(n_y, 1))

# =====================================================================
# CUSTOM CANARY SIGNALS
# =====================================================================
def sig_6mo_sma(p: pd.Series) -> float:
    """Faber 6-month SMA: (price - SMA6) / SMA6."""
    p = p.dropna()
    if len(p) < 6:
        return np.nan
    sma = float(p.iloc[-6:].mean())
    return (float(p.iloc[-1]) - sma) / sma if sma > 0 else np.nan

# =====================================================================
# ENGINE HELPERS
# =====================================================================
def zscore_series(s: pd.Series) -> pd.Series:
    sd = s.std()
    if pd.isna(sd) or sd == 0:
        return pd.Series(0.0, index=s.index)
    return (s - s.mean()) / sd


def pick_top1(sa: pd.Series, za: pd.Series, avail: list,
              prev_sel) -> str | None:
    """Top-1 asset by Faber score with hold buffer."""
    pos = sa.loc[avail][sa.loc[avail] > 0].sort_values(ascending=False)
    if pos.empty:
        return None
    best = pos.index[0]
    if prev_sel and len(prev_sel) >= 1 and HOLD_BUF > 1e-9:
        prior = prev_sel[0]
        if prior != best and prior in avail and sa.get(prior, -np.inf) > 0:
            z_p = za.get(prior, np.nan)
            z_b = za.get(best, np.nan)
            if pd.notna(z_p) and pd.notna(z_b) and (z_b - z_p) < HOLD_BUF:
                best = prior
    return best


def hold_buffer_apply(new_list: list, prev_sel,
                      avail: list, sa: pd.Series, za: pd.Series, n: int) -> list:
    """Production hold-buffer logic extended to n slots."""
    if prev_sel is None or HOLD_BUF < 1e-9:
        return new_list[:n]
    result = list(new_list)
    for prior in prev_sel:
        if prior in result or prior not in avail:
            continue
        if sa.get(prior, -np.inf) <= 0:
            continue
        z_prior = za.get(prior, np.nan)
        if not pd.notna(z_prior):
            continue
        swap_cands = [x for x in result if x not in prev_sel]
        if not swap_cands:
            continue
        swap = min(swap_cands, key=lambda x: za.get(x, np.inf))
        z_swap = za.get(swap, np.nan)
        if not pd.notna(z_swap):
            continue
        if z_swap - z_prior < HOLD_BUF:
            result.remove(swap)
            result.append(prior)
    return result[:n]

# =====================================================================
# GENERIC FCP BACKTEST ENGINE
# =====================================================================
def run_generic_backtest(
    panel: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
    *,
    canary_assets: list,
    min_positive: int,
    canary_signal_fn=None,
    universe: list = None,
    safe_pool: list = None,
    target_vol: float = 0.10,
    cost_bps: float = 10,
    pair_mode: str = "pair",
    risky_frac: float = 1.0,
):
    universe  = universe or RISKY_UNIVERSE
    safe_pool = safe_pool or SAFE_POOL
    sig_fn    = canary_signal_fn or sig_13612W

    cols  = sorted(set(universe + safe_pool + canary_assets + [DEFAULT_CASH]) & set(panel.columns))
    close = panel[cols]
    dret  = close.ffill().pct_change()

    monthly_idx  = pd.DataFrame({"x": 1}, index=close.index).groupby(pd.Grouper(freq="ME")).tail(1)
    signal_dates = monthly_idx.index[(monthly_idx.index >= start) & (monthly_idx.index <= end)].tolist()

    weights_history = []
    diag = {"n_riskon": 0, "n_defensive": 0, "riskon_dates": [], "defensive_dates": []}
    prev_pair = None

    for i, sig_d in enumerate(signal_dates):
        monthly = close.loc[:sig_d].resample("ME").last()
        safe    = best_safe(monthly, sig_d, safe_pool)

        scores = []
        for c in canary_assets:
            if c not in monthly.columns:
                continue
            s = sig_fn(monthly[c])
            if pd.notna(s):
                scores.append(s)

        n_pos   = sum(1 for s in scores if s > 0)
        risk_on = (len(scores) > 0) and (n_pos >= min_positive)

        if not risk_on:
            w = {safe: 1.0}
            prev_pair = None
            diag["n_defensive"] += 1
            diag["defensive_dates"].append(sig_d)
        else:
            diag["n_riskon"] += 1
            diag["riskon_dates"].append(sig_d)

            score = faber_sma_xs(monthly)
            avail = [t for t in universe
                     if t in score.index and pd.notna(score[t])
                     and pd.notna(close.loc[sig_d, t] if sig_d in close.index else np.nan)]

            if not avail:
                w = {safe: 1.0}
                prev_pair = None
            else:
                sa = score.loc[avail]
                za = zscore_series(sa)
                ranked   = sa.sort_values(ascending=False)
                top_k_n  = max(2, min(TOP_K, len(ranked)))
                positive = ranked.iloc[:top_k_n][lambda s: s > 0]

                if pair_mode == "single":
                    best = pick_top1(sa, za, avail, prev_pair)
                    if best is None:
                        w = {safe: 1.0}
                        prev_pair = None
                    else:
                        w = {best: risky_frac}
                        if risky_frac < 1.0 - 1e-6:
                            w[safe] = 1.0 - risky_frac
                        prev_pair = (best,)
                else:
                    if len(positive) < 2:
                        if len(positive) == 1:
                            a = positive.index[0]
                            w = {a: 0.5 * risky_frac}
                            rem = 1.0 - 0.5 * risky_frac
                            if rem > 1e-6:
                                w[safe] = w.get(safe, 0.0) + rem
                        else:
                            w = {safe: 1.0}
                        prev_pair = None
                    else:
                        cands    = list(positive.index)
                        new_pick = min_vol_pair(close.loc[:sig_d, cands], cands, CORR_LB)
                        if new_pick is None:
                            new_pick = (cands[0], cands[1])
                        new_set  = hold_buffer_apply(list(new_pick), prev_pair, avail, sa, za, 2)
                        new_pick = tuple(new_set[:2])
                        w = {new_pick[0]: 0.5 * risky_frac, new_pick[1]: 0.5 * risky_frac}
                        rem = 1.0 - risky_frac
                        if rem > 1e-6:
                            w[safe] = w.get(safe, 0.0) + rem
                        prev_pair = new_pick

        future = close.index[close.index > sig_d]
        if len(future) < 2:
            continue
        apply_from = future[1]
        if i + 1 < len(signal_dates):
            nxt     = signal_dates[i + 1]
            nxt_fut = close.index[close.index > nxt]
            end_app = nxt_fut[1] if len(nxt_fut) >= 2 else end
        else:
            end_app = end
        weights_history.append({"apply_from": apply_from, "end_apply": end_app,
                                 "weights": w, "sig_d": sig_d})

    if not weights_history:
        return pd.Series(dtype=float), diag

    all_a = sorted({a for h in weights_history for a in h["weights"]})
    df_w  = pd.DataFrame(0.0, index=close.index,
                         columns=[a for a in all_a if a in close.columns])
    for h in weights_history:
        mask = (close.index >= h["apply_from"]) & (close.index < h["end_apply"])
        for a, ww in h["weights"].items():
            if a in df_w.columns:
                df_w.loc[mask, a] = ww

    common = [a for a in df_w.columns if a in dret.columns]
    raw    = (df_w[common] * dret[common]).sum(axis=1, min_count=1).fillna(0.0)

    for i, h in enumerate(weights_history):
        prev_w = weights_history[i - 1]["weights"] if i > 0 else {}
        curr_w = h["weights"]
        keys   = set(curr_w) | set(prev_w)
        tov    = sum(abs(curr_w.get(k, 0.0) - prev_w.get(k, 0.0)) for k in keys)
        af     = h["apply_from"]
        if af in raw.index:
            raw.loc[af] -= tov * cost_bps / 10_000.0

    realized = raw.rolling(VOL_LB).std() * np.sqrt(252)
    scale    = (target_vol / realized.replace(0, np.nan)).clip(upper=MAX_LEV).shift(1).fillna(1.0)
    scaled   = (raw * scale).loc[(raw.index >= start) & (raw.index <= end)]
    return scaled, diag


# =====================================================================
# BREADTH-TIERED BACKTEST ENGINE
# =====================================================================
def run_tiered_backtest(
    panel: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
    *,
    canary_4: list,
    universe: list = None,
    safe_pool: list = None,
    tier_config: dict,
    target_vol: float = 0.10,
    tv_by_tier: dict | None = None,
    cost_bps: float = 10,
):
    universe  = universe or RISKY_UNIVERSE
    safe_pool = safe_pool or SAFE_POOL
    cols      = sorted(set(universe + safe_pool + canary_4 + [DEFAULT_CASH]) & set(panel.columns))
    close     = panel[cols]
    dret      = close.ffill().pct_change()

    monthly_idx  = pd.DataFrame({"x": 1}, index=close.index).groupby(pd.Grouper(freq="ME")).tail(1)
    signal_dates = monthly_idx.index[(monthly_idx.index >= start) & (monthly_idx.index <= end)].tolist()

    weights_history = []
    breadth_counts  = {b: 0 for b in range(5)}
    prev_pair = None

    for i, sig_d in enumerate(signal_dates):
        monthly = close.loc[:sig_d].resample("ME").last()
        safe    = best_safe(monthly, sig_d, safe_pool)

        bscores = []
        for c in canary_4:
            if c not in monthly.columns:
                continue
            s = sig_13612W(monthly[c])
            if pd.notna(s):
                bscores.append(s)
        breadth = sum(1 for s in bscores if s > 0)
        breadth_counts[breadth] += 1

        pair_mode, risky_frac = tier_config.get(breadth, ("safe", 0.0))

        if risky_frac <= 0 or pair_mode == "safe":
            w = {safe: 1.0}
            prev_pair = None
        else:
            score = faber_sma_xs(monthly)
            avail = [t for t in universe
                     if t in score.index and pd.notna(score[t])
                     and pd.notna(close.loc[sig_d, t] if sig_d in close.index else np.nan)]

            if not avail:
                w = {safe: 1.0}
                prev_pair = None
            else:
                sa = score.loc[avail]
                za = zscore_series(sa)
                ranked   = sa.sort_values(ascending=False)
                top_k_n  = max(2, min(TOP_K, len(ranked)))
                positive = ranked.iloc[:top_k_n][lambda s: s > 0]

                if pair_mode == "single":
                    best = pick_top1(sa, za, avail, prev_pair)
                    if best is None:
                        w = {safe: 1.0}
                        prev_pair = None
                    else:
                        w = {best: risky_frac}
                        if risky_frac < 1.0 - 1e-6:
                            w[safe] = 1.0 - risky_frac
                        prev_pair = (best,)
                else:
                    if len(positive) < 2:
                        if len(positive) == 1:
                            a = positive.index[0]
                            w = {a: 0.5 * risky_frac}
                            rem = 1.0 - 0.5 * risky_frac
                            if rem > 1e-6:
                                w[safe] = w.get(safe, 0.0) + rem
                        else:
                            w = {safe: 1.0}
                        prev_pair = None
                    else:
                        cands    = list(positive.index)
                        new_pick = min_vol_pair(close.loc[:sig_d, cands], cands, CORR_LB)
                        if new_pick is None:
                            new_pick = (cands[0], cands[1])
                        new_set  = hold_buffer_apply(list(new_pick), prev_pair, avail, sa, za, 2)
                        new_pick = tuple(new_set[:2])
                        w = {new_pick[0]: 0.5 * risky_frac, new_pick[1]: 0.5 * risky_frac}
                        rem = 1.0 - risky_frac
                        if rem > 1e-6:
                            w[safe] = w.get(safe, 0.0) + rem
                        prev_pair = new_pick

        future = close.index[close.index > sig_d]
        if len(future) < 2:
            continue
        apply_from = future[1]
        if i + 1 < len(signal_dates):
            nxt     = signal_dates[i + 1]
            nxt_fut = close.index[close.index > nxt]
            end_app = nxt_fut[1] if len(nxt_fut) >= 2 else end
        else:
            end_app = end
        weights_history.append({"apply_from": apply_from, "end_apply": end_app,
                                 "weights": w, "sig_d": sig_d, "breadth": breadth})

    if not weights_history:
        return pd.Series(dtype=float), breadth_counts

    all_a = sorted({a for h in weights_history for a in h["weights"]})
    df_w  = pd.DataFrame(0.0, index=close.index,
                         columns=[a for a in all_a if a in close.columns])
    tv_map = pd.Series(target_vol, index=close.index)

    for h in weights_history:
        mask = (close.index >= h["apply_from"]) & (close.index < h["end_apply"])
        for a, ww in h["weights"].items():
            if a in df_w.columns:
                df_w.loc[mask, a] = ww
        if tv_by_tier is not None:
            b = h["breadth"]
            tv_map.loc[mask] = tv_by_tier.get(b, target_vol)

    common = [a for a in df_w.columns if a in dret.columns]
    raw    = (df_w[common] * dret[common]).sum(axis=1, min_count=1).fillna(0.0)

    for i, h in enumerate(weights_history):
        prev_w = weights_history[i - 1]["weights"] if i > 0 else {}
        curr_w = h["weights"]
        keys   = set(curr_w) | set(prev_w)
        tov    = sum(abs(curr_w.get(k, 0.0) - prev_w.get(k, 0.0)) for k in keys)
        af     = h["apply_from"]
        if af in raw.index:
            raw.loc[af] -= tov * cost_bps / 10_000.0

    realized = raw.rolling(VOL_LB).std() * np.sqrt(252)
    if tv_by_tier is not None:
        scale = (tv_map / realized.replace(0, np.nan)).clip(upper=MAX_LEV).shift(1).fillna(1.0)
    else:
        scale = (target_vol / realized.replace(0, np.nan)).clip(upper=MAX_LEV).shift(1).fillna(1.0)
    scaled = (raw * scale).loc[(raw.index >= start) & (raw.index <= end)]
    return scaled, breadth_counts


# =====================================================================
# FORWARD RETURN HELPERS
# =====================================================================
def _fwd_21(dret: pd.DataFrame | pd.Series, sig_d: pd.Timestamp, ticker: str):
    if isinstance(dret, pd.Series):
        dret = dret.to_frame(ticker)
    if ticker not in dret.columns:
        return None
    idx   = dret.index.searchsorted(sig_d, side="right")
    sub   = dret[ticker].iloc[idx: idx + 21].dropna()
    if len(sub) < 10:
        return None
    return float((1 + sub).prod() - 1)


def _fwd_maxdd_21(dret: pd.DataFrame, sig_d: pd.Timestamp, ticker: str):
    if ticker not in dret.columns:
        return None
    idx = dret.index.searchsorted(sig_d, side="right")
    sub = dret[ticker].iloc[idx: idx + 21].dropna()
    if len(sub) < 5:
        return None
    eq = (1 + sub).cumprod()
    return float((eq / eq.cummax() - 1).min())


# =====================================================================
# PART A
# =====================================================================
def part_a(panel: pd.DataFrame) -> None:
    log("=" * 100)
    log("PART A: SPY+TIP CANARY STATE FORWARD PREDICTIVE POWER")
    log("=" * 100)
    log("Signal: 13612W = (12*r1 + 4*r3 + 2*r6 + r12) / 19")
    log("States: both_pos | spy_only | tip_only | both_neg")
    log("Forward window: 21 trading days (~1 calendar month)")
    log("")

    obs_tickers = [t for t in ["SPY", "QQQ", "GLD", "TLT", "IEF"] if t in panel.columns]
    fcp15       = [t for t in RISKY_UNIVERSE if t in panel.columns]
    EW_LABEL    = "FCP15_EW"

    # Include TIP and other canary assets so sig_13612W can see them
    canary_obs = ["SPY", "TIP", "VEA", "EEM", "AGG"]
    close   = panel[[t for t in list(dict.fromkeys(obs_tickers + fcp15 + canary_obs)) if t in panel.columns]].copy()
    monthly = close.resample("ME").last()
    dret    = close.ffill().pct_change()

    for win_label, win_start in [("FULL 2001-2026", FULL_START), ("LIVE 2008-2026", LIVE_START)]:
        log(f"\n--- {win_label} ---")
        dates = monthly.index[(monthly.index >= win_start) & (monthly.index <= panel.index[-1])]

        rows = []
        for d in dates:
            sub_m   = monthly.loc[:d]
            spy_sig = sig_13612W(sub_m["SPY"]) if "SPY" in sub_m.columns else np.nan
            tip_sig = sig_13612W(sub_m["TIP"]) if "TIP" in sub_m.columns else np.nan
            spy_pos = pd.notna(spy_sig) and spy_sig > 0
            tip_pos = pd.notna(tip_sig) and tip_sig > 0

            if spy_pos and tip_pos:
                state = "both_pos"
            elif spy_pos:
                state = "spy_only"
            elif tip_pos:
                state = "tip_only"
            else:
                state = "both_neg"

            row = {"date": d, "state": state}
            for t in obs_tickers:
                row[f"fwd_{t}"] = _fwd_21(dret, d, t)
            fcp_fwds = [_fwd_21(dret, d, t) for t in fcp15 if t in dret.columns]
            fcp_fwds = [x for x in fcp_fwds if x is not None]
            row[f"fwd_{EW_LABEL}"] = float(np.mean(fcp_fwds)) if fcp_fwds else np.nan
            row["fwd_SPY_maxdd"]   = _fwd_maxdd_21(dret, d, "SPY")
            rows.append(row)

        df    = pd.DataFrame(rows).set_index("date")
        total = len(df)
        states_order = ["both_pos", "spy_only", "tip_only", "both_neg"]

        # State frequency
        counts = df["state"].value_counts()
        log(f"\n  State frequencies (n={total} months):")
        for st in states_order:
            n = counts.get(st, 0)
            log(f"    {st:12s}: {n:4d} months ({100.0*n/max(1,total):5.1f}%)")

        # Forward return table
        fwd_cols   = [f"fwd_{t}" for t in obs_tickers] + [f"fwd_{EW_LABEL}", "fwd_SPY_maxdd"]
        fwd_labels = obs_tickers + [EW_LABEL, "SPY_maxDD"]

        log(f"\n  Forward 21d stats by state (mean% | median% | p25% | p75% | hit%>0):")
        log(f"  {'State':12s}  {'Asset':12s}  {'N':>4}  {'Mean':>7}  {'Median':>7}"
            f"  {'p25':>7}  {'p75':>7}  {'Hit%':>6}")
        log("  " + "-" * 75)

        for st in states_order:
            sub = df[df["state"] == st]
            for col, lbl in zip(fwd_cols, fwd_labels):
                vals = sub[col].dropna() * 100.0
                if len(vals) < 3:
                    continue
                hit = 100.0 * (vals > 0).sum() / len(vals)
                log(f"  {st:12s}  {lbl:12s}  {len(vals):>4d}  "
                    f"{vals.mean():>+7.2f}  {vals.median():>+7.2f}  "
                    f"{vals.quantile(0.25):>+7.2f}  {vals.quantile(0.75):>+7.2f}  "
                    f"{hit:>6.1f}%")
            log("  " + "-" * 75)

        log(f"\n  KEY CONTRASTS (both_pos vs rest):")
        for col, lbl in [("fwd_SPY", "SPY"), (f"fwd_{EW_LABEL}", EW_LABEL), ("fwd_IEF", "IEF")]:
            if col not in df.columns:
                continue
            bp   = df[df["state"] == "both_pos"][col].dropna() * 100.0
            rest = df[df["state"] != "both_pos"][col].dropna() * 100.0
            log(f"    {lbl:12s}: both_pos mean={bp.mean():+.2f}%  rest mean={rest.mean():+.2f}%"
                f"  diff={bp.mean()-rest.mean():+.2f}pp  "
                f"(both_pos hit={100*(bp>0).mean():.0f}%  rest hit={100*(rest>0).mean():.0f}%)")

        log(f"\n  SIGNAL SEPARATION (mean fwd SPY per state, best→worst):")
        state_spy_means = []
        for st in states_order:
            sub = df[df["state"] == st]["fwd_SPY"].dropna() * 100.0
            if len(sub) > 0:
                state_spy_means.append((st, float(sub.mean()), len(sub)))
        for st, mn, n in sorted(state_spy_means, key=lambda x: -x[1]):
            log(f"    {st:12s}: fwd_SPY mean={mn:+.2f}%  (n={n})")


# =====================================================================
# PART B
# =====================================================================
def part_b(panel: pd.DataFrame) -> None:
    log("\n")
    log("=" * 100)
    log("PART B: ALTERNATIVE CANARY SETS ON FCP-15 PRODUCTION ENGINE")
    log("=" * 100)
    log(f"Universe: {RISKY_UNIVERSE}")
    log(f"Window: Live 2008-2026 (18y), TV=0.10, pair mode, cost=10bps")
    log("")

    spy_dret = panel["SPY"].ffill().pct_change() if "SPY" in panel.columns else None
    end      = panel.index[-1]

    configs = [
        ("SPY alone (13612W)",          CANARY_SPY1,    1,  None),
        ("SPY+TIP (13612W, current)",   CANARY_PROD,    2,  None),
        ("SPY+VEA+EEM+AGG (3-of-4)",    CANARY_VAA4,    3,  None),
        ("SPY+VEA+EEM+AGG (4-of-4)",    CANARY_VAA4,    4,  None),
        ("SPY+VEA+EEM+AGG+TIP (3of5)", CANARY_VAA4TIP, 3,  None),
        ("SPY (6mo SMA)",               CANARY_SPY1,    1,  sig_6mo_sma),
        ("GLD+TLT (13612W, 2-of-2)",    CANARY_GLDTLT,  2,  None),
    ]

    rows = []
    for label, can, minp, sig_fn in configs:
        t0 = time.time()
        log(f"  Running: {label} ...")
        # Validate canary assets in panel
        missing_can = [c for c in can if c not in panel.columns]
        if missing_can:
            log(f"    SKIP: missing {missing_can}")
            continue

        daily, diag = run_generic_backtest(
            panel, LIVE_START, end,
            canary_assets=can, min_positive=minp,
            canary_signal_fn=sig_fn,
            universe=RISKY_UNIVERSE, safe_pool=SAFE_POOL,
            target_vol=TV_BASE, cost_bps=COST_BPS,
            pair_mode="pair", risky_frac=1.0,
        )

        m   = calc_metrics(daily)
        tot = diag["n_riskon"] + diag["n_defensive"]
        pct = 100.0 * diag["n_riskon"] / max(1, tot)

        spy_ro, spy_def = [], []
        if spy_dret is not None:
            for sig_d in diag["riskon_dates"]:
                v = _fwd_21(spy_dret, sig_d, "SPY")
                if v is not None:
                    spy_ro.append(v)
            for sig_d in diag["defensive_dates"]:
                v = _fwd_21(spy_dret, sig_d, "SPY")
                if v is not None:
                    spy_def.append(v)

        avg_ro  = 100.0 * np.mean(spy_ro)  if spy_ro  else np.nan
        avg_def = 100.0 * np.mean(spy_def) if spy_def else np.nan
        hit_def = 100.0 * sum(1 for x in spy_def if x < 0) / len(spy_def) if spy_def else np.nan

        rows.append(dict(
            label=label, years=m["years"], pct_ro=pct,
            sharpe=m["sharpe"], cagr=m.get("cagr", np.nan),
            maxdd=m.get("maxdd", np.nan), sortino=m.get("sortino", np.nan),
            spy_ro=avg_ro, spy_def=avg_def, def_hit=hit_def,
            elapsed=time.time() - t0,
        ))
        log(f"    Sh={m['sharpe']:+.3f}  CAGR={m.get('cagr',np.nan)*100:+.2f}%  "
            f"MaxDD={m.get('maxdd',np.nan)*100:+.2f}%  %RO={pct:.1f}%  [{time.time()-t0:.1f}s]")

    log("")
    log("  COMPARISON TABLE")
    hdr = (f"  {'Config':38s} | {'Yr':>4} | {'%RO':>5} | {'Sharpe':>7} | "
           f"{'CAGR%':>7} | {'MaxDD%':>7} | {'Sortino':>7} | "
           f"{'SPY|RO':>7} | {'SPY|DEF':>7} | {'DEF_hit':>8}")
    log(hdr)
    log("  " + "-" * 105)
    for r in rows:
        def _f(v, fmt): return format(v, fmt) if pd.notna(v) else "    nan"
        log(
            f"  {r['label']:38s} | {r['years']:>4.1f} | {r['pct_ro']:>5.1f}% | "
            f"{_f(r['sharpe'],'+7.3f')} | {_f(r['cagr']*100 if pd.notna(r['cagr']) else np.nan,'+7.2f')}% | "
            f"{_f(r['maxdd']*100 if pd.notna(r['maxdd']) else np.nan,'+7.2f')}% | "
            f"{_f(r['sortino'],'+7.3f')} | "
            f"{_f(r['spy_ro'],'+7.2f')}% | {_f(r['spy_def'],'+7.2f')}% | "
            f"{_f(r['def_hit'],'>8.1f')}%"
        )

    log("")
    log("  LEGEND:")
    log("  SPY|RO   = avg fwd 1mo SPY return when canary fires RISK_ON  (higher = strategy picks good months)")
    log("  SPY|DEF  = avg fwd 1mo SPY return when canary fires DEFENSIVE (lower = better crisis detection)")
    log("  DEF_hit% = pct defensive calls where SPY actually fell next month")
    log("  Best canary: highest Sharpe + SPY|RO high + SPY|DEF low + DEF_hit% high")


# =====================================================================
# PART C
# =====================================================================
def part_c(panel: pd.DataFrame) -> None:
    log("\n")
    log("=" * 100)
    log("PART C: BREADTH TIERING WITH 4-CANARY SPY+VEA+EEM+AGG")
    log("=" * 100)
    log(f"Canary: {CANARY_VAA4}, all using 13612W")
    log(f"Breadth = # of canaries with 13612W > 0")
    log("")
    log("  Tier configs:")
    log("  BINARY-CURRENT   : SPY+TIP all-pos → pair 100% (production equiv)")
    log("  BINARY-VAA4-MAJ  : VAA4 3-of-4 majority → pair 100%")
    log("  TIERED-STD       : b4=single100%  b3=pair100%  b2=pair50%  b1=pair25%  b0=safe")
    log("  TIERED-VOLVAR    : b4=single100%+TV20  b3=pair100%+TV10  b2=pair50%+TV10  b<=1=safe")
    log("")

    end = panel.index[-1]

    TIER_STD = {
        4: ("single", 1.00),
        3: ("pair",   1.00),
        2: ("pair",   0.50),
        1: ("pair",   0.25),
        0: ("safe",   0.00),
    }
    TIER_VOLVAR = {
        4: ("single", 1.00),
        3: ("pair",   1.00),
        2: ("pair",   0.50),
        1: ("safe",   0.00),
        0: ("safe",   0.00),
    }
    TV_BY_TIER_VV = {4: 0.20, 3: 0.10, 2: 0.10, 1: 0.10, 0: 0.10}

    all_results = []

    for win_label, win_start in [("Live-18y", LIVE_START), ("Full-25y", FULL_START)]:
        log(f"\n--- Window: {win_label} ({win_start.date()}) ---")

        # Binary-Current
        t0 = time.time()
        log("  Running Binary-Current (SPY+TIP, pair) ...")
        bc_d, bc_diag = run_generic_backtest(
            panel, win_start, end,
            canary_assets=CANARY_PROD, min_positive=2,
            universe=RISKY_UNIVERSE, safe_pool=SAFE_POOL,
            target_vol=TV_BASE, cost_bps=COST_BPS, pair_mode="pair", risky_frac=1.0,
        )
        log(f"    done {time.time()-t0:.1f}s")

        # Binary VAA4 majority
        t0 = time.time()
        log("  Running Binary-VAA4-Maj (3-of-4, pair) ...")
        bv_d, bv_diag = run_generic_backtest(
            panel, win_start, end,
            canary_assets=CANARY_VAA4, min_positive=3,
            universe=RISKY_UNIVERSE, safe_pool=SAFE_POOL,
            target_vol=TV_BASE, cost_bps=COST_BPS, pair_mode="pair", risky_frac=1.0,
        )
        log(f"    done {time.time()-t0:.1f}s")

        # Tiered standard
        t0 = time.time()
        log("  Running Tiered-Standard (5-level, TV=0.10) ...")
        ts_d, ts_bc = run_tiered_backtest(
            panel, win_start, end,
            canary_4=CANARY_VAA4,
            universe=RISKY_UNIVERSE, safe_pool=SAFE_POOL,
            tier_config=TIER_STD, target_vol=TV_BASE, cost_bps=COST_BPS,
        )
        log(f"    done {time.time()-t0:.1f}s")

        # Tiered vol-var
        t0 = time.time()
        log("  Running Tiered-VolVar (b4=TV20) ...")
        tv_d, tv_bc = run_tiered_backtest(
            panel, win_start, end,
            canary_4=CANARY_VAA4,
            universe=RISKY_UNIVERSE, safe_pool=SAFE_POOL,
            tier_config=TIER_VOLVAR, target_vol=TV_BASE,
            tv_by_tier=TV_BY_TIER_VV, cost_bps=COST_BPS,
        )
        log(f"    done {time.time()-t0:.1f}s")

        def pct_ro(d):
            tot = d["n_riskon"] + d["n_defensive"]
            return 100.0 * d["n_riskon"] / max(1, tot)

        def bc_str(bc):
            tot = sum(bc.values())
            return "  ".join(f"b{b}={100*bc[b]/max(1,tot):.0f}%" for b in range(5))

        for label, daily, extra in [
            (f"Binary-Current   SPY+TIP  [{win_label}]", bc_d, f"pct_ro={pct_ro(bc_diag):.1f}%"),
            (f"Binary-VAA4-Maj  3-of-4   [{win_label}]", bv_d, f"pct_ro={pct_ro(bv_diag):.1f}%"),
            (f"Tiered-Standard  5-level  [{win_label}]", ts_d, bc_str(ts_bc)),
            (f"Tiered-VolVar    b4=TV20  [{win_label}]", tv_d, bc_str(tv_bc)),
        ]:
            m = calc_metrics(daily)
            all_results.append({**m, "label": label, "win": win_label, "extra": extra})

        # Breadth distribution detail
        log(f"\n  Breadth distribution [{win_label}]:")
        tier_mode_labels = {4: "single100%", 3: "pair100%", 2: "pair50%", 1: "pair25%", 0: "safe"}
        for bc_label, bc in [("Tiered-Standard", ts_bc), ("Tiered-VolVar", tv_bc)]:
            tot = sum(bc.values())
            log(f"    {bc_label}:")
            for b in range(4, -1, -1):
                n = bc[b]
                log(f"      Breadth {b} ({tier_mode_labels[b]:12s}): {n:3d} mo ({100*n/max(1,tot):.1f}%)")

    # Summary table
    log("")
    log("  FULL SUMMARY TABLE")
    log(f"  {'Strategy':50s} | {'Yr':>4} | {'Sharpe':>7} | {'CAGR%':>7} | {'MaxDD%':>7} | {'Sortino':>7} | Breadth distribution")
    log("  " + "-" * 115)
    for r in all_results:
        def _f(v, fmt): return format(v, fmt) if pd.notna(v) else "    nan"
        log(
            f"  {r['label']:50s} | {r['years']:>4.1f} | "
            f"{_f(r['sharpe'],'+7.3f')} | "
            f"{_f(r['cagr']*100 if pd.notna(r.get('cagr')) else np.nan,'+7.2f')}% | "
            f"{_f(r['maxdd']*100 if pd.notna(r.get('maxdd')) else np.nan,'+7.2f')}% | "
            f"{_f(r['sortino'],'+7.3f')} | {r['extra']}"
        )

    log("")
    log("  INTERPRETATION GUIDE:")
    log("  1. Does Tiered-Standard beat Binary-Current on Sharpe? → tiering adds value")
    log("  2. Does Tiered-VolVar beat Tiered-Standard on Sharpe without proportional DD increase?")
    log("     → concentrated top-1 with higher TV at breadth-4 is empirically warranted")
    log("  3. Compare SPY+TIP vs VAA4-Majority binary: better canary changes regime-on% meaningfully")
    log("  4. MaxDD is the risk cost of concentration. If it jumps >3pp, concentration is too costly.")


# =====================================================================
# MAIN
# =====================================================================
def main() -> None:
    t_total = time.time()
    log("=" * 100)
    log("FCP CANARY AUDIT & BREADTH TIERING EXPERIMENT")
    log(f"Run: {pd.Timestamp.today().isoformat()[:19]}")
    log(f"Universe ({len(RISKY_UNIVERSE)}): {RISKY_UNIVERSE}")
    log(f"Safe pool: {SAFE_POOL}")
    log(f"Prod canary: {CANARY_PROD} (both must have 13612W > 0)")
    log(f"Constants: TOP_K={TOP_K}, HOLD_BUF={HOLD_BUF}, CORR_LB={CORR_LB}d, "
        f"VOL_LB={VOL_LB}d, TV={TV_BASE}, MAX_LEV={MAX_LEV}, COST={COST_BPS}bps")
    log("=" * 100)

    log("\nLoading panel ...")
    panel = load_panel(start=pd.Timestamp("2000-01-01"))
    if "AGG_stitched" in panel.columns and "AGG" not in panel.columns:
        panel = panel.rename(columns={"AGG_stitched": "AGG"})
    log(f"Panel: {panel.index[0].date()} -> {panel.index[-1].date()}, {panel.shape[1]} assets")
    log(f"VAA4 canary assets available: {[c for c in CANARY_VAA4 if c in panel.columns]}")

    part_a(panel)
    part_b(panel)
    part_c(panel)

    log("")
    log("=" * 100)
    log(f"TOTAL ELAPSED: {(time.time()-t_total)/60:.1f} minutes")
    log("=" * 100)
    flush_log()
    print(f"\nLog written: {LOG_PATH}", flush=True)


if __name__ == "__main__":
    main()
