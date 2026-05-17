"""85% FCP + 15% top-momentum sleeve when X6 trigger fires.

The 15% sleeve = highest-momentum asset(s) from FCP-15 universe.
No QLD, no leverage. Pure momentum concentration.

Variants:
  M_top1       : 15% in single best momentum (could be QQQ, SPMO, IGM, XLV, etc.)
  M_top2_ew    : 15% split 7.5/7.5 between top-2 momentum
  M_top2_mw    : 15% momentum-weighted top-2 (z-score proportional)
  M_top3_ew    : 15% equal-weight top-3
  M_eq_top1    : 15% top-1 from EQUITY-ONLY subset (excludes GLD/TLT)
  M_eq_top2_ew : 15% top-2 EW from EQUITY-ONLY
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import fcp_live as fcp
from fcp_live import (
    RISKY_UNIVERSE, load_panel, run_fcp_backtest, perf_metrics, sig_13612W,
    faber_sma_xs,
)

ALIASES = {"AGG": "AGG_stitched", "HYG": "HYG_stitched"}


def get_state(monthly, sig_d, canaries):
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


def x6_fires(monthly_full, sig_d):
    state = get_state(monthly_full, sig_d, ["HYG", "TIP", "EEM", "SPY"])
    if state is None:
        return False
    return all(state.values())


def momentum_picks(monthly, sig_d, mode):
    """Return {asset: weight} for the 15% momentum sleeve."""
    score = faber_sma_xs(monthly.loc[:sig_d])
    avail = [t for t in RISKY_UNIVERSE
             if t in score.index and pd.notna(score[t]) and score[t] > 0]
    if not avail:
        return None
    ranked = score[avail].sort_values(ascending=False)

    if mode == "M_top1":
        return {ranked.index[0]: 1.0}
    if mode == "M_top2_ew":
        picks = ranked.index[:2].tolist()
        if len(picks) < 2:
            return {picks[0]: 1.0} if picks else None
        return {picks[0]: 0.5, picks[1]: 0.5}
    if mode == "M_top2_mw":
        picks = ranked.index[:2].tolist()
        if len(picks) < 2:
            return {picks[0]: 1.0} if picks else None
        scores = np.maximum(ranked.iloc[:2].values, 0.001)
        w = scores / scores.sum()
        return {picks[0]: float(w[0]), picks[1]: float(w[1])}
    if mode == "M_top3_ew":
        picks = ranked.index[:3].tolist()
        if len(picks) < 2:
            return {picks[0]: 1.0} if picks else None
        n = len(picks)
        return {p: 1.0/n for p in picks}
    if mode == "M_eq_top1":
        eq_ranked = ranked.loc[[t for t in ranked.index if t not in ("GLD","TLT")]]
        if eq_ranked.empty:
            return None
        return {eq_ranked.index[0]: 1.0}
    if mode == "M_eq_top2_ew":
        eq_ranked = ranked.loc[[t for t in ranked.index if t not in ("GLD","TLT")]]
        picks = eq_ranked.index[:2].tolist()
        if len(picks) < 2:
            return {picks[0]: 1.0} if picks else None
        return {picks[0]: 0.5, picks[1]: 0.5}
    return None


def compute_overlay_returns(panel, sigs, triggers, mode):
    """Daily returns of the momentum overlay sleeve (when trigger fires)."""
    overlay_ret = pd.Series(0.0, index=panel.index)
    daily_ret = panel.ffill().pct_change()
    for i, sig_d in enumerate(sigs):
        if not triggers.get(sig_d, False):
            continue
        future = panel.index[panel.index > sig_d]
        if len(future) < 2:
            continue
        apply_from = future[1]
        if i + 1 < len(sigs):
            next_sig = sigs[i+1]
            nf = panel.index[panel.index > next_sig]
            end_apply = nf[1] if len(nf) >= 2 else panel.index[-1]
        else:
            end_apply = panel.index[-1]
        # Compute momentum picks at sig_d
        monthly = panel.loc[:sig_d].resample("ME").last()
        picks = momentum_picks(monthly, sig_d, mode)
        if not picks:
            continue
        mask = (panel.index >= apply_from) & (panel.index < end_apply)
        for asset, w in picks.items():
            if asset in daily_ret.columns:
                overlay_ret.loc[mask] += w * daily_ret.loc[mask, asset]
    return overlay_ret


def main():
    out = Path(__file__).parent / "aggressive_momentum_overlay.log"
    log_lines = []
    def log(s=""): log_lines.append(s); print(s)

    log("=" * 110)
    log("85% FCP + 15% TOP-MOMENTUM OVERLAY when X6 (HYG+TIP+EEM+SPY+) fires")
    log("Momentum sleeve = top-N highest Faber SMA from FCP-15 universe (no QLD/leverage)")
    log("=" * 110)

    panel = load_panel(start=pd.Timestamp("1999-01-01"))
    start = pd.Timestamp("2008-09-30")
    end = panel.index[-1]

    base, _ = run_fcp_backtest(panel, start, end)
    bm = perf_metrics(base)
    log(f"\nBASE FCP-15: Sh={bm['sharpe']:+.3f}  CAGR={bm['cagr']*100:+.2f}%  DD={bm['max_drawdown']*100:+.2f}%")

    # Compute X6 trigger dates once
    monthly_idx = pd.DataFrame({"x":1}, index=panel.index).groupby(pd.Grouper(freq="ME")).tail(1)
    sigs = monthly_idx.index[(monthly_idx.index >= start) & (monthly_idx.index <= end)].tolist()
    triggers = {}
    for sd in sigs:
        mon = panel.loc[:sd].resample("ME").last()
        triggers[sd] = x6_fires(mon, sd)
    n_fire = sum(triggers.values())
    log(f"X6 fires {n_fire}/{len(sigs)} ({n_fire/len(sigs)*100:.1f}%)")
    log("")

    modes = ["M_top1", "M_top2_ew", "M_top2_mw", "M_top3_ew", "M_eq_top1", "M_eq_top2_ew"]
    swap_pcts = [0.10, 0.15, 0.20, 0.25, 0.30]

    log("=" * 110)
    log(f"  {'Mode':<14s}  {'Swap%':<6s}  Sh      CAGR%   DD%       d_Sh    d_CAGR    d_DD     top_picks_sample")
    log("  " + "-" * 105)
    for mode in modes:
        overlay = compute_overlay_returns(panel, sigs, triggers, mode)
        # Sample what picks fire (first few X6 dates)
        sample = []
        for sd in sigs:
            if not triggers.get(sd): continue
            mon = panel.loc[:sd].resample("ME").last()
            p = momentum_picks(mon, sd, mode)
            if p:
                sample.append(f"{sd.strftime('%Y-%m')}={'/'.join(list(p.keys())[:3])}")
            if len(sample) >= 3: break
        sample_str = ", ".join(sample)

        for sw in swap_pcts:
            firing = pd.Series(0.0, index=base.index)
            for i, sd in enumerate(sigs):
                if not triggers.get(sd): continue
                future = panel.index[panel.index > sd]
                if len(future) < 2: continue
                apply_from = future[1]
                if i+1 < len(sigs):
                    next_sig = sigs[i+1]
                    nf = panel.index[panel.index > next_sig]
                    end_apply = nf[1] if len(nf) >= 2 else panel.index[-1]
                else:
                    end_apply = panel.index[-1]
                mask = (base.index >= apply_from) & (base.index < end_apply)
                firing.loc[mask] = sw
            combined = base * (1 - firing) + firing * overlay.reindex(base.index, fill_value=0)
            m = perf_metrics(combined)
            log(f"  {mode:<14s}  {int(sw*100):2d}%     {m['sharpe']:+.3f}  {m['cagr']*100:+5.2f}  "
                f"{m['max_drawdown']*100:+6.2f}    {m['sharpe']-bm['sharpe']:+.3f}  "
                f"{(m['cagr']-bm['cagr'])*100:+5.2f}pp   "
                f"{(m['max_drawdown']-bm['max_drawdown'])*100:+5.2f}pp")
        log(f"    sample picks: {sample_str}")
        log("")

    log("=" * 110)
    with open(out, "w") as f: f.write("\n".join(log_lines))
    print(f"\nLog: {out}")


if __name__ == "__main__":
    main()
