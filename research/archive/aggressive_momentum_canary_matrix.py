"""Matrix test: TOP-2 momentum (EW & mw) overlay across various canary triggers.

Tests:
  Triggers:    7 different bull-state triggers (X1...X7) on top of HYG+TIP+
  Overlay:     85% FCP + 15% top-2-EW  OR  85% FCP + 15% top-2-mw
  Swap%:       10%, 15%, 20%, 25%

Output: full matrix of (trigger x overlay-mode x swap%) -> Sh, CAGR, DD
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import fcp_live as fcp
from fcp_live import (RISKY_UNIVERSE, load_panel, run_fcp_backtest,
                       perf_metrics, sig_13612W, faber_sma_xs)

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


# Triggers (all start with HYG+TIP+ to layer on top of deployed canary)
TRIGGERS = [
    ("X0_HYG_TIP_only",      ["HYG","TIP"],         lambda s: s["HYG"] and s["TIP"]),
    ("X4_EEM_SPY",           ["HYG","TIP","EEM","SPY"],     lambda s: all(s.get(c,False) for c in ["HYG","TIP","EEM","SPY"])),
    ("X7_EEM_SPY_TLT-",      ["HYG","TIP","EEM","SPY","TLT"], lambda s: s["HYG"] and s["TIP"] and s["EEM"] and s["SPY"] and not s["TLT"]),
    ("X8_SPY_TIP_EFA_EEM",   ["SPY","TIP","EFA","EEM"],     lambda s: all(s.get(c,False) for c in ["SPY","TIP","EFA","EEM"])),
    ("X9_+HYG (5-pos)",      ["SPY","TIP","EFA","EEM","HYG"], lambda s: all(s.get(c,False) for c in ["SPY","TIP","EFA","EEM","HYG"])),
    ("X10_+HYG+TLT-",        ["SPY","TIP","EFA","EEM","HYG","TLT"], lambda s: s["SPY"] and s["TIP"] and s["EFA"] and s["EEM"] and s["HYG"] and not s["TLT"]),
    ("X11_all4+VWO",         ["SPY","TIP","EEM","VWO","HYG"], lambda s: all(s.get(c,False) for c in ["SPY","TIP","EEM","VWO","HYG"])),
]

OVERLAY_MODES = ["top2_ew", "top2_mw"]
SWAP_PCTS = [1.00]  # 100% replacement when trigger fires


def momentum_picks(monthly, sig_d, mode):
    score = faber_sma_xs(monthly.loc[:sig_d])
    avail = [t for t in RISKY_UNIVERSE
             if t in score.index and pd.notna(score[t]) and score[t] > 0]
    if not avail:
        return None
    ranked = score[avail].sort_values(ascending=False)
    if mode == "top2_ew":
        picks = ranked.index[:2].tolist()
        if len(picks) < 2:
            return {picks[0]: 1.0} if picks else None
        return {picks[0]: 0.5, picks[1]: 0.5}
    if mode == "top2_mw":
        picks = ranked.index[:2].tolist()
        if len(picks) < 2:
            return {picks[0]: 1.0} if picks else None
        scores = np.maximum(ranked.iloc[:2].values, 0.001)
        w = scores / scores.sum()
        return {picks[0]: float(w[0]), picks[1]: float(w[1])}
    return None


def overlay_returns(panel, sigs, triggers, mode):
    overlay_ret = pd.Series(0.0, index=panel.index)
    daily_ret = panel.ffill().pct_change()
    for i, sig_d in enumerate(sigs):
        if not triggers.get(sig_d, False):
            continue
        future = panel.index[panel.index > sig_d]
        if len(future) < 2: continue
        apply_from = future[1]
        if i+1 < len(sigs):
            next_sig = sigs[i+1]
            nf = panel.index[panel.index > next_sig]
            end_apply = nf[1] if len(nf) >= 2 else panel.index[-1]
        else:
            end_apply = panel.index[-1]
        monthly = panel.loc[:sig_d].resample("ME").last()
        picks = momentum_picks(monthly, sig_d, mode)
        if not picks: continue
        mask = (panel.index >= apply_from) & (panel.index < end_apply)
        for asset, w in picks.items():
            if asset in daily_ret.columns:
                overlay_ret.loc[mask] += w * daily_ret.loc[mask, asset]
    return overlay_ret


def compute_combined(base, sigs, triggers, overlay, swap_pct):
    firing = pd.Series(0.0, index=base.index)
    for i, sd in enumerate(sigs):
        if not triggers.get(sd): continue
        future = base.index[base.index > sd]
        if len(future) < 2: continue
        apply_from = future[1]
        if i+1 < len(sigs):
            next_sig = sigs[i+1]
            nf = base.index[base.index > next_sig]
            end_apply = nf[1] if len(nf) >= 2 else base.index[-1]
        else:
            end_apply = base.index[-1]
        mask = (base.index >= apply_from) & (base.index < end_apply)
        firing.loc[mask] = swap_pct
    return base * (1 - firing) + firing * overlay.reindex(base.index, fill_value=0)


def main():
    out = Path(__file__).parent / "aggressive_momentum_canary_matrix.log"
    log_lines = []
    def log(s=""): log_lines.append(s); print(s)

    log("=" * 130)
    log("MATRIX: TOP-2 MOMENTUM (EW & mom-weighted) overlay across canary triggers")
    log("Format: 85% FCP-15 + 15%/etc top-2 momentum sleeve when trigger fires")
    log("=" * 130)

    panel = load_panel(start=pd.Timestamp("1999-01-01"))
    start = pd.Timestamp("2008-09-30")
    end = panel.index[-1]
    base, _ = run_fcp_backtest(panel, start, end)
    bm = perf_metrics(base)
    log(f"\nBASE FCP-15: Sh={bm['sharpe']:+.3f}  CAGR={bm['cagr']*100:+.2f}%  DD={bm['max_drawdown']*100:+.2f}%\n")

    monthly_idx = pd.DataFrame({"x":1}, index=panel.index).groupby(pd.Grouper(freq="ME")).tail(1)
    sigs = monthly_idx.index[(monthly_idx.index >= start) & (monthly_idx.index <= end)].tolist()

    # Pre-compute triggers for each rule
    log("Trigger coverage:")
    trig_dict = {}
    for label, cans, rule in TRIGGERS:
        trig = {}
        for sd in sigs:
            mon = panel.loc[:sd].resample("ME").last()
            state = get_state(mon, sd, cans)
            trig[sd] = (state is not None) and rule(state)
        n = sum(trig.values())
        log(f"  {label:<24s}  fires {n:3d}/{len(sigs)} ({n/len(sigs)*100:5.1f}%)")
        trig_dict[label] = trig
    log("")

    # Pre-compute overlays for each mode
    overlays = {}
    for mode in OVERLAY_MODES:
        # Use universal "always fire" trigger to compute overlay returns
        all_true = {sd: True for sd in sigs}
        overlays[mode] = overlay_returns(panel, sigs, all_true, mode)
    log("Overlay returns precomputed.\n")

    # Matrix
    log("=" * 130)
    log("FULL MATRIX: trigger x overlay_mode x swap%")
    log("=" * 130)
    log(f"  {'Trigger':<22s}  {'Mode':<10s}  {'Swap':<6s}  Sh      d_Sh    CAGR%    d_CAGR    DD%       d_DD")
    log("  " + "-" * 100)

    best_by_sharpe = []
    best_by_cagr = []
    for trig_label, cans, _ in TRIGGERS:
        triggers = trig_dict[trig_label]
        for mode in OVERLAY_MODES:
            overlay = overlays[mode]
            # Restrict overlay to firing months only via compute_combined firing mask
            for sw in SWAP_PCTS:
                combined = compute_combined(base, sigs, triggers, overlay, sw)
                m = perf_metrics(combined)
                d_sh = m['sharpe'] - bm['sharpe']
                d_cagr = (m['cagr'] - bm['cagr']) * 100
                d_dd = (m['max_drawdown'] - bm['max_drawdown']) * 100
                log(f"  {trig_label:<22s}  {mode:<10s}  {int(sw*100):2d}%    {m['sharpe']:+.3f}  "
                    f"{d_sh:+.3f}  {m['cagr']*100:+5.2f}   {d_cagr:+5.2f}pp   "
                    f"{m['max_drawdown']*100:+6.2f}    {d_dd:+5.2f}pp")
                best_by_sharpe.append((m['sharpe'], trig_label, mode, sw, m))
                best_by_cagr.append((m['cagr'], trig_label, mode, sw, m, d_dd))
        log("")

    log("=" * 130)
    log("TOP 10 BY PORTFOLIO SHARPE")
    log("=" * 130)
    for sh, t, mo, sw, m in sorted(best_by_sharpe, key=lambda x: -x[0])[:10]:
        d_sh = sh - bm['sharpe']
        d_cagr = (m['cagr'] - bm['cagr']) * 100
        d_dd = (m['max_drawdown'] - bm['max_drawdown']) * 100
        log(f"  Sh={sh:+.3f}  {t:<22s}  {mo:<10s}  {int(sw*100):2d}%   d_Sh={d_sh:+.3f}  "
            f"d_CAGR={d_cagr:+5.2f}pp  d_DD={d_dd:+5.2f}pp")

    log("")
    log("TOP 10 BY CAGR (with d_DD < 5pp constraint)")
    log("=" * 130)
    filtered = [(c, t, mo, sw, m, dd) for c, t, mo, sw, m, dd in best_by_cagr if dd > -5]
    for cagr, t, mo, sw, m, d_dd in sorted(filtered, key=lambda x: -x[0])[:10]:
        d_sh = m['sharpe'] - bm['sharpe']
        d_cagr = (cagr - bm['cagr']) * 100
        log(f"  CAGR={cagr*100:+.2f}%  {t:<22s}  {mo:<10s}  {int(sw*100):2d}%   "
            f"d_Sh={d_sh:+.3f}  d_CAGR={d_cagr:+5.2f}pp  d_DD={d_dd:+5.2f}pp")

    log("")
    log("=" * 130)
    with open(out, "w") as f: f.write("\n".join(log_lines))
    print(f"\nLog: {out}")


if __name__ == "__main__":
    main()
