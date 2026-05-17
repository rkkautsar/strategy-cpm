"""
FCP component sensitivity sweep.

Tests the production FCP across:
  - Vol target: ON, OFF, 8%, 10%, 12%, 15%
  - TOP_K: 3, 5, 7, 10, 12, 15
  - HOLD_BUFFER: 0, 1z, 2z, 3z, 4z, 5z
  - CORR_LOOKBACK_DAYS: 126, 189, 252, 378, 504, 756
  - VOL_LOOKBACK_DAYS (for vol target): 21, 42, 63, 126, 252
  - MAX_LEVERAGE: 1.0, 1.2, 1.5, 2.0

Goal: identify which component is most sensitive (likely tuned), which are robust.
"""
from __future__ import annotations
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import strategy_fcp.fcp_live as fcp
from strategy_fcp.fcp_live import load_panel, run_fcp_backtest


def metrics_from_daily(daily_ret):
    eq = (1 + daily_ret).cumprod()
    r = daily_ret.dropna()
    if r.empty: return {}
    n_y = len(r) / 252.0
    cagr = eq.iloc[-1] ** (1/n_y) - 1
    vol = r.std() * np.sqrt(252)
    sh = (r.mean()*252) / vol if vol > 0 else np.nan
    dd = (eq / eq.cummax() - 1).min()
    return dict(cagr=cagr, vol=vol, sharpe=sh, maxdd=dd)


def fmt(label, m):
    return (f"  {label:<48s}  Sh {m['sharpe']:+.3f}  CAGR {m['cagr']*100:+5.2f}%  "
            f"DD {m['maxdd']*100:+6.2f}%  Vol {m['vol']*100:5.2f}%")


def run_with_constants(panel, start, end, **overrides):
    """Temporarily set constants on fcp module, run backtest, restore."""
    saved = {k: getattr(fcp, k) for k in overrides if hasattr(fcp, k)}
    for k, v in overrides.items():
        if hasattr(fcp, k):
            setattr(fcp, k, v)
    try:
        # Use apply_vol_target from overrides if specified, else default to module value
        apply_vt = overrides.pop("apply_vol_target", True)
        daily, _ = run_fcp_backtest(panel, start, end, apply_vol_target=apply_vt)
        return metrics_from_daily(daily)
    finally:
        for k, v in saved.items():
            setattr(fcp, k, v)


def main():
    panel = load_panel(start=pd.Timestamp("1995-01-01"))
    end = panel.index.max()
    hybrid_start = pd.Timestamp("1997-08-31")
    live_start = pd.Timestamp("2008-09-30")

    print("=" * 165)
    print("FCP COMPONENT SENSITIVITY SWEEP")
    print(f"Production constants: TOP_K_CANDIDATES={fcp.TOP_K_CANDIDATES}, CORR_LOOKBACK_DAYS={fcp.CORR_LOOKBACK_DAYS},")
    print(f"  HOLD_BUFFER={fcp.HOLD_BUFFER}, TARGET_VOL={fcp.TARGET_VOL}, VOL_LOOKBACK_DAYS={fcp.VOL_LOOKBACK_DAYS},")
    print(f"  MAX_LEVERAGE={fcp.MAX_LEVERAGE}")
    print("=" * 165)

    for win_label, start in [("Extended 28.7y", hybrid_start), ("Live-only 18y", live_start)]:
        print(f"\n>>> {win_label}")
        print("=" * 165)

        # Production reference
        print("\n[Production reference (vol-target ON / OFF)]")
        for vt in [True, False]:
            m = run_with_constants(panel, start, end, apply_vol_target=vt)
            tag = "ON" if vt else "OFF"
            print(fmt(f"FCP production (vol-target {tag})", m))

        print("\n[TOP_K_CANDIDATES sweep (vol-target ON)]")
        for tk in [3, 5, 7, 10, 12, 15]:
            m = run_with_constants(panel, start, end, TOP_K_CANDIDATES=tk, apply_vol_target=True)
            print(fmt(f"TOP_K = {tk}", m))

        print("\n[HOLD_BUFFER sweep (vol-target ON)]")
        for hb in [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]:
            m = run_with_constants(panel, start, end, HOLD_BUFFER=hb, apply_vol_target=True)
            print(fmt(f"HOLD_BUFFER = {hb}z", m))

        print("\n[CORR_LOOKBACK_DAYS sweep (vol-target ON)]")
        for lb in [126, 189, 252, 378, 504, 756]:
            m = run_with_constants(panel, start, end, CORR_LOOKBACK_DAYS=lb, apply_vol_target=True)
            print(fmt(f"CORR_LOOKBACK = {lb}d", m))

        print("\n[TARGET_VOL sweep (vol-target ON)]")
        for tv in [0.06, 0.08, 0.10, 0.12, 0.15, 0.20]:
            m = run_with_constants(panel, start, end, TARGET_VOL=tv, apply_vol_target=True)
            print(fmt(f"TARGET_VOL = {tv*100:.0f}%", m))

        print("\n[VOL_LOOKBACK_DAYS sweep (vol-target ON)]")
        for vlb in [21, 42, 63, 126, 252]:
            m = run_with_constants(panel, start, end, VOL_LOOKBACK_DAYS=vlb, apply_vol_target=True)
            print(fmt(f"VOL_LOOKBACK = {vlb}d", m))

        print("\n[MAX_LEVERAGE sweep (vol-target ON)]")
        for ml in [1.0, 1.2, 1.5, 2.0]:
            m = run_with_constants(panel, start, end, MAX_LEVERAGE=ml, apply_vol_target=True)
            print(fmt(f"MAX_LEVERAGE = {ml}x", m))


if __name__ == "__main__":
    main()
