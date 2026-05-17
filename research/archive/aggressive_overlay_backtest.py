"""Aggressive overlay backtest.

Add a TQQQ (3x QQQ) overlay sleeve when STRICT bull-state canary fires.
Tests 3 strict triggers:

  TRIGGER_A: HYG+ AND TLT-                (~34% coverage, Sh 1.87 conditional)
  TRIGGER_B: HYG+ AND EEM+ AND TLT-       (~27% coverage, Sh 2.51 conditional)
  TRIGGER_C: TIP+ AND EEM+ AND TLT-       (~20% coverage, Sh 2.69 conditional)

Overlay structure:
  Base: 100% FCP-15 (production)
  When trigger fires: add OVERLAY% to TQQQ on top of FCP base
  Funded by margin (gross exposure > 100%) - tests both 25% and 50% overlay

Tested on live-only 18y window (TQQQ inception 2010-02 means earlier years
use QLD or simulated 3x QQQ proxy).
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
from fcp_live import load_panel, run_fcp_backtest, perf_metrics, sig_13612W

ALIASES = {"AGG": "AGG_stitched", "HYG": "HYG_stitched"}


def fetch_or_simulate_tqqq(panel: pd.DataFrame) -> pd.Series:
    """Get TQQQ daily prices; if pre-inception, simulate as 3x QQQ daily returns
    with -1.5% annualized expense ratio drag (TQQQ ER ~0.86% + leverage decay)."""
    end_dt = panel.index[-1]
    tqqq_live = yf.Ticker("TQQQ").history(period="max", auto_adjust=True)["Close"]
    tqqq_live.index = pd.DatetimeIndex(tqqq_live.index).tz_localize(None)
    tqqq_live = tqqq_live.reindex(panel.index, method="ffill")

    # Simulate pre-inception via 3x QQQ daily returns - drag
    qqq = panel["QQQ"]
    qqq_ret = qqq.pct_change()
    drag = 0.015 / 252  # 1.5%/yr daily drag (ER + decay)
    sim_ret = 3 * qqq_ret - drag
    sim_price = (1 + sim_ret).cumprod()
    sim_price = sim_price / sim_price.iloc[0] * 100  # arbitrary start

    inception = pd.Timestamp("2010-02-11")
    # Splice: sim before inception, live after, scaled to match level
    if inception in tqqq_live.index and not pd.isna(tqqq_live.loc[inception]):
        scale = tqqq_live.loc[inception] / sim_price.loc[inception]
        sim_price_scaled = sim_price * scale
        stitched = sim_price_scaled.copy()
        stitched.loc[inception:] = tqqq_live.loc[inception:]
        return stitched.ffill()
    return sim_price


def get_canary_state(monthly, sig_d, canaries):
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


def trigger_a(s): return s.get("HYG", False) and not s.get("TLT", True)
def trigger_b(s): return s.get("HYG", False) and s.get("EEM", False) and not s.get("TLT", True)
def trigger_c(s): return s.get("TIP", False) and s.get("EEM", False) and not s.get("TLT", True)


def compute_trigger_dates(panel, start, end, canaries, rule_fn):
    """For each signal date, evaluate if trigger fires."""
    monthly_idx = pd.DataFrame({"x": 1}, index=panel.index).groupby(pd.Grouper(freq="ME")).tail(1)
    sigs = monthly_idx.index[(monthly_idx.index >= start) & (monthly_idx.index <= end)].tolist()
    triggers = {}
    for sig_d in sigs:
        monthly = panel.loc[:sig_d].resample("ME").last()
        state = get_canary_state(monthly, sig_d, canaries)
        triggers[sig_d] = (state is not None) and rule_fn(state)
    return triggers, sigs


def compute_overlay_returns(panel, sigs, triggers, overlay_pct=0.25,
                             overlay_asset_price=None):
    """Daily returns of TQQQ overlay weighted by trigger state.
    Holds overlay_pct in TQQQ from T+1 after trigger fires until next sig date."""
    overlay_ret = overlay_asset_price.pct_change().fillna(0)
    pos = pd.Series(0.0, index=panel.index)
    for i, sig_d in enumerate(sigs):
        if not triggers.get(sig_d, False):
            continue
        future = panel.index[panel.index > sig_d]
        if len(future) < 2:
            continue
        apply_from = future[1]
        if i + 1 < len(sigs):
            next_sig = sigs[i + 1]
            next_future = panel.index[panel.index > next_sig]
            end_apply = next_future[1] if len(next_future) >= 2 else panel.index[-1]
        else:
            end_apply = panel.index[-1]
        mask = (panel.index >= apply_from) & (panel.index < end_apply)
        pos.loc[mask] = overlay_pct
    return pos * overlay_ret


def main():
    out_path = Path(__file__).parent / "aggressive_overlay_backtest.log"
    log_lines = []
    def log(s=""):
        log_lines.append(s); print(s)

    log("=" * 110)
    log("AGGRESSIVE OVERLAY BACKTEST - TQQQ (3x QQQ) sleeve when strict bull-state fires")
    log("Base: 100% FCP-15 (production with HYG+TIP any+ canary).")
    log("Overlay: +OVERLAY% TQQQ on top of base (gross exposure > 100% when firing)")
    log("=" * 110)

    panel = load_panel(start=pd.Timestamp("1999-01-01"))
    log(f"Panel: {panel.index[0].date()} -> {panel.index[-1].date()}")

    # Add HYG_stitched, AGG_stitched if missing (they should be via load_panel)
    needed = ["HYG_stitched", "AGG_stitched", "EEM", "TLT", "TIP", "QQQ"]
    missing = [c for c in needed if c not in panel.columns]
    if missing:
        log(f"WARNING: missing columns: {missing}")
        return

    log("Fetching TQQQ (live + 3x QQQ simulated pre-inception)...")
    tqqq = fetch_or_simulate_tqqq(panel)
    log(f"TQQQ series: {tqqq.dropna().index[0].date()} -> {tqqq.dropna().index[-1].date()}")
    log("")

    start = pd.Timestamp("2008-09-30")
    end = panel.index[-1]

    # Base FCP-15 returns (production)
    base_rets, _ = run_fcp_backtest(panel, start, end)
    base_m = perf_metrics(base_rets)
    log(f"BASE (FCP-15 production):  Sh={base_m['sharpe']:+.3f}  CAGR={base_m['cagr']*100:+.2f}%  "
        f"Vol={base_m['vol']*100:.2f}%  DD={base_m['max_drawdown']*100:+.2f}%")
    log("")

    # Build overlay asset price series
    qld_live = yf.Ticker("QLD").history(period="max", auto_adjust=True)["Close"]
    qld_live.index = pd.DatetimeIndex(qld_live.index).tz_localize(None)
    qld_live = qld_live.reindex(panel.index, method="ffill")
    qqq_price = panel["QQQ"]
    spy_price = panel["SPY"]

    triggers_defs = [
        ("A: HYG+ AND TLT-",            ["HYG", "TLT"],         trigger_a),
        ("B: HYG+ AND EEM+ AND TLT-",   ["HYG", "EEM", "TLT"],  trigger_b),
        ("C: TIP+ AND EEM+ AND TLT-",   ["TIP", "EEM", "TLT"],  trigger_c),
    ]

    overlay_assets = [
        ("TQQQ (3x)", tqqq),
        ("QLD  (2x)", qld_live),
        ("QQQ  (1x)", qqq_price),
        ("SPY  (1x)", spy_price),
    ]

    for label, cans, rule_fn in triggers_defs:
        log(f"--- TRIGGER {label} ---")
        triggers, sigs = compute_trigger_dates(panel, start, end, cans, rule_fn)
        n_fire = sum(1 for v in triggers.values() if v)
        coverage = n_fire / len(sigs) * 100
        log(f"  Fires {n_fire}/{len(sigs)} months ({coverage:.1f}%)")
        log(f"  Base (no overlay):  Sh={base_m['sharpe']:+.3f}  CAGR={base_m['cagr']*100:+.2f}%  DD={base_m['max_drawdown']*100:+.2f}%")
        log("")

        # ADDITIVE OVERLAY (requires margin, gross > 100%)
        log(f"  -- ADDITIVE overlay (gross > 100%, requires margin) --")
        for asset_label, asset_px in overlay_assets:
            if asset_px.dropna().empty:
                continue
            for overlay_pct in [0.25, 0.50]:
                overlay_rets = compute_overlay_returns(panel, sigs, triggers,
                                                         overlay_pct=overlay_pct,
                                                         overlay_asset_price=asset_px)
                combined = base_rets.add(overlay_rets.reindex(base_rets.index, fill_value=0.0), fill_value=0)
                m = perf_metrics(combined)
                log(f"    +{int(overlay_pct*100):2d}% {asset_label:11s}  Sh={m['sharpe']:+.3f}  "
                    f"CAGR={m['cagr']*100:+.2f}%  DD={m['max_drawdown']*100:+.2f}%  "
                    f"d_Sh={m['sharpe']-base_m['sharpe']:+.3f}  d_CAGR={(m['cagr']-base_m['cagr'])*100:+.2f}pp")
            log("")

        # SWAP OVERLAY (no margin: replace FCP with overlay during trigger)
        log(f"  -- SWAP overlay (no margin, gross=100%: replace FCP with overlay when firing) --")
        for asset_label, asset_px in overlay_assets:
            if asset_px.dropna().empty:
                continue
            for swap_pct in [0.25, 0.50]:
                overlay_rets = compute_overlay_returns(panel, sigs, triggers,
                                                         overlay_pct=swap_pct,
                                                         overlay_asset_price=asset_px)
                # During firing: reduce FCP by swap_pct, add swap_pct in overlay asset
                # Net: base_rets - swap_pct*base_rets*(when firing) + overlay_rets
                # Build a daily "firing" mask
                firing_mask = pd.Series(0.0, index=panel.index)
                for i, sig_d in enumerate(sigs):
                    if not triggers.get(sig_d, False):
                        continue
                    future = panel.index[panel.index > sig_d]
                    if len(future) < 2: continue
                    apply_from = future[1]
                    if i + 1 < len(sigs):
                        next_sig = sigs[i + 1]
                        next_future = panel.index[panel.index > next_sig]
                        end_apply = next_future[1] if len(next_future) >= 2 else panel.index[-1]
                    else:
                        end_apply = panel.index[-1]
                    mask = (panel.index >= apply_from) & (panel.index < end_apply)
                    firing_mask.loc[mask] = swap_pct
                firing_mask = firing_mask.reindex(base_rets.index, fill_value=0.0)
                overlay_aligned = overlay_rets.reindex(base_rets.index, fill_value=0.0)
                combined = base_rets * (1 - firing_mask) + overlay_aligned
                m = perf_metrics(combined)
                log(f"    {int(swap_pct*100):2d}% swap {asset_label:11s}  Sh={m['sharpe']:+.3f}  "
                    f"CAGR={m['cagr']*100:+.2f}%  DD={m['max_drawdown']*100:+.2f}%  "
                    f"d_Sh={m['sharpe']-base_m['sharpe']:+.3f}  d_CAGR={(m['cagr']-base_m['cagr'])*100:+.2f}pp")
            log("")
        log("")

    log("=" * 110)
    log("INTERPRETATION GUIDE")
    log("=" * 110)
    log("")
    log("  - overlay=0% confirms base FCP-15 unaffected.")
    log("  - Look for: positive Sharpe AND positive CAGR delta with bounded DD widening.")
    log("  - Gross exposure when firing = 100% (base) + overlay% = e.g. 125% or 150%.")
    log("  - DD widening should be smaller than CAGR gain for trigger to be worth using.")
    log("  - TQQQ pre-2010 is SIMULATED 3x QQQ with 1.5%/y decay drag. Pre-2010 results")
    log("    less trustworthy than 2010+.")
    log("")

    with open(out_path, "w") as f:
        f.write("\n".join(log_lines))
    print(f"\nLog: {out_path}")


if __name__ == "__main__":
    main()
