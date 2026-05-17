"""
FCP component decomposition v2 -- corrected to match production exactly.

Bug fixes from v1:
  - CORR_LOOKBACK_DAYS = 378 (1.5y), not 252
  - PARTIAL fallback (1 cand -> 50/50 cand+safe), not defensive
  - Hold buffer mechanic mirrored exactly from production
  - Faber-z applied to monthly DataFrame, not pre-filtered universe
  - Best-safe rotation uses production fcp_best_safe (BIL/SHV/SHY/IEF), not just SHV/IEF
  - Compare with AND without vol-target overlay
"""
from __future__ import annotations
import sys
from itertools import combinations
from math import ceil
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from strategy_fcp.fcp_live import (
    load_panel, sig_13612W, RISKY_UNIVERSE, SAFE_POOL, CANARY_ASSETS,
    DEFAULT_CASH, faber_sma_xs, min_vol_pair, best_safe as fcp_best_safe,
    zscore, run_fcp_backtest, compute_target_weights,
    TOP_K_CANDIDATES, CORR_LOOKBACK_DAYS, HOLD_BUFFER, COST_BPS_PER_SIDE,
)

LB = CORR_LOOKBACK_DAYS  # 378 (production)
COST_BPS_SIDE = COST_BPS_PER_SIDE


def get_eom_dates(panel, start, end):
    idx = panel.loc[start:end].index
    return list(pd.Series(idx).groupby(idx.to_period("M")).last())


def canary_pass(panel, sig_d, canary_assets=None):
    """Production canary: majority of canaries must have 13612W > 0."""
    monthly = panel.loc[:sig_d].resample("ME").last()
    canary_assets = canary_assets or CANARY_ASSETS
    scs = []
    for c in canary_assets:
        if c not in monthly.columns: continue
        s = sig_13612W(monthly[c])
        if pd.notna(s): scs.append(s)
    if not scs: return False
    n_pos = sum(1 for s in scs if s > 0)
    return n_pos > len(scs) // 2


def fcp_pair_target(panel, sig_d, prev_pair=None,
                    skip_canary=False, hold_buffer=HOLD_BUFFER,
                    top_k=TOP_K_CANDIDATES, lookback=LB):
    """Recreate FCP target weights with toggleable components.
    Mirrors production compute_target_weights exactly except for component skips.
    """
    monthly = panel.loc[:sig_d].resample("ME").last()
    safe = fcp_best_safe(monthly, sig_d, SAFE_POOL)

    # Canary check (skippable)
    if not skip_canary:
        if not canary_pass(panel, sig_d):
            return {safe: 1.0}, None, "DEFENSIVE"

    # Faber-z ranker on full monthly panel
    score = faber_sma_xs(monthly)
    avail = [t for t in RISKY_UNIVERSE
             if t in score.index and pd.notna(score[t])
             and (sig_d in panel.index and pd.notna(panel.loc[sig_d].get(t, np.nan)))]
    if not avail:
        return {safe: 1.0}, None, "DEFENSIVE"

    sa = score.loc[avail]
    za = zscore(sa)
    ranked = sa.sort_values(ascending=False)
    K = max(2, min(top_k, len(ranked)))
    positive = ranked.iloc[:K][lambda s: s > 0]

    # Partial-safe fill if <2 positive (production behavior)
    if len(positive) < 2:
        if len(positive) == 1:
            return {positive.index[0]: 0.5, safe: 0.5}, None, "RISK_ON"
        return {safe: 1.0}, None, "DEFENSIVE"

    candidates = list(positive.index)
    new_pick = min_vol_pair(panel.loc[:sig_d, candidates], candidates, lookback)
    if new_pick is None:
        return {candidates[0]: 1.0}, None, "RISK_ON"

    # Hold buffer (skippable via hold_buffer=0)
    if prev_pair is not None and hold_buffer > 1e-9:
        new_set = list(new_pick)
        for prior in prev_pair:
            if prior in new_set or prior not in avail:
                continue
            if sa.get(prior, -np.inf) <= 0:
                continue
            z_prior = za.get(prior, np.nan)
            if pd.isna(z_prior): continue
            swap_cands = [x for x in new_set if x not in prev_pair]
            if not swap_cands: continue
            swap = min(swap_cands, key=lambda x: za.get(x, np.inf))
            z_swap = za.get(swap, np.nan)
            if pd.isna(z_swap): continue
            if z_swap - z_prior < hold_buffer:
                new_set.remove(swap)
                new_set.append(prior)
        new_pick = tuple(new_set[:2])

    return {new_pick[0]: 0.5, new_pick[1]: 0.5}, new_pick, "RISK_ON"


def make_fcp_variant(skip_canary=False, hold_buffer=HOLD_BUFFER,
                     top_k=TOP_K_CANDIDATES, lookback=LB):
    state = {"prev_pair": None}
    def strat(panel, sig_d):
        weights, new_pair, _ = fcp_pair_target(panel, sig_d, prev_pair=state["prev_pair"],
                                                skip_canary=skip_canary,
                                                hold_buffer=hold_buffer,
                                                top_k=top_k, lookback=lookback)
        state["prev_pair"] = new_pair
        return weights
    return strat


def simulate(panel, start, end, target_fn, cost_bps=COST_BPS_SIDE):
    eom = get_eom_dates(panel, start, end)
    target_at = {}
    for d in eom:
        try:
            w = target_fn(panel, d)
        except Exception:
            continue
        future = panel.loc[d:].index
        if len(future) >= 2:
            target_at[future[1]] = w
    daily_ret = panel.pct_change()
    eq = 1.0
    holdings = {}
    nav = []
    turnovers = []
    for d in panel.loc[start:end].index:
        if holdings:
            r = sum(w * daily_ret.loc[d, t] for t, w in holdings.items()
                    if t in daily_ret.columns and pd.notna(daily_ret.loc[d, t]))
            eq *= (1 + r)
        if d in target_at:
            new_w = target_at[d]
            old_w = holdings.copy()
            all_t = set(old_w.keys()) | set(new_w.keys())
            to = sum(abs(new_w.get(t, 0) - old_w.get(t, 0)) for t in all_t)
            turnovers.append(to)
            eq *= (1 - to * cost_bps / 10000.0)
            holdings = new_w
        nav.append((d, eq))
    df = pd.DataFrame(nav, columns=["date", "equity"]).set_index("date")
    df["daily_ret"] = df["equity"].pct_change()
    return df, np.array(turnovers)


def metrics(eq):
    r = eq["daily_ret"].dropna()
    if r.empty: return {}
    n_y = len(r) / 252.0
    cagr = eq["equity"].iloc[-1] ** (1/n_y) - 1
    vol = r.std() * np.sqrt(252)
    sh = (r.mean()*252) / vol if vol > 0 else np.nan
    dd = (eq["equity"] / eq["equity"].cummax() - 1).min()
    return dict(cagr=cagr, vol=vol, sharpe=sh, maxdd=dd)


def fmt(label, m, to):
    ann_to = to.mean()*12*100 if len(to) else 0
    return (f"  {label:<58s}  Sh {m['sharpe']:+.3f}  CAGR {m['cagr']*100:+5.2f}%  "
            f"DD {m['maxdd']*100:+6.2f}%  Vol {m['vol']*100:5.2f}%  AnnTO {ann_to:>5.0f}%")


def main():
    panel = load_panel(start=pd.Timestamp("1995-01-01"))
    end = panel.index.max()
    hybrid_start = pd.Timestamp("1997-08-31")
    live_start = pd.Timestamp("2008-09-30")

    print("=" * 165)
    print("FCP DECOMPOSITION v2 (corrected: 378d cov, PARTIAL fallback, exact buffer mechanic)")
    print(f"Constants: TOP_K_CANDIDATES={TOP_K_CANDIDATES}, CORR_LOOKBACK_DAYS={CORR_LOOKBACK_DAYS},")
    print(f"           HOLD_BUFFER={HOLD_BUFFER}, COST_BPS_SIDE={COST_BPS_SIDE}")
    print("=" * 165)

    for win_label, start in [
        ("Extended 28.7y", hybrid_start),
        ("Live-only 18y", live_start),
    ]:
        print()
        print("=" * 165)
        print(f">>> {win_label}")
        print("=" * 165)

        # Production reference (with and without vol-target)
        for vt in [True, False]:
            daily_ret, _ = run_fcp_backtest(panel, start, end, apply_vol_target=vt)
            eq = (1 + daily_ret).cumprod()
            df = pd.DataFrame({"equity": eq, "daily_ret": daily_ret})
            tag = "vol-target ON" if vt else "vol-target OFF"
            print(fmt(f"FCP production ({tag})", metrics(df), np.array([0])))

        # My replication (should match production with vol-target OFF)
        print()
        print("[My replication of FCP without vol-target -- should match prod NO-VT]")
        eq, to = simulate(panel, start, end, make_fcp_variant())
        m = metrics(eq)
        print(fmt("FCP replicated (canary + 3z buffer + 7-cand + 378d cov)", m, to))

        print("\n[FCP component disabling]")
        # Drop canary
        eq, to = simulate(panel, start, end, make_fcp_variant(skip_canary=True))
        m = metrics(eq)
        print(fmt("FCP - canary (buffer + 7-cand + 378d cov)", m, to))

        # Drop hold buffer
        eq, to = simulate(panel, start, end, make_fcp_variant(hold_buffer=0))
        m = metrics(eq)
        print(fmt("FCP - hold buffer (canary + 7-cand + 378d cov)", m, to))

        # Drop both
        eq, to = simulate(panel, start, end, make_fcp_variant(skip_canary=True, hold_buffer=0))
        m = metrics(eq)
        print(fmt("FCP - canary - buffer (just pair selection on top-7)", m, to))

        # Reduce top_k
        for k in [3, 5, 7, 10, 15]:
            eq, to = simulate(panel, start, end, make_fcp_variant(top_k=k))
            m = metrics(eq)
            print(fmt(f"FCP top-K={k} (canary + buffer)", m, to))

        # Sweep cov lookback
        print()
        print("[Cov lookback sensitivity (with full FCP machinery)]")
        for lb in [126, 252, 378, 504, 756]:
            eq, to = simulate(panel, start, end, make_fcp_variant(lookback=lb))
            m = metrics(eq)
            print(fmt(f"FCP cov lookback {lb}d", m, to))


if __name__ == "__main__":
    main()
