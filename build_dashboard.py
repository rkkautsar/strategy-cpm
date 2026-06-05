#!/usr/bin/env python3
"""
Build a single-file mobile-friendly static HTML dashboard for CPM strategy.

Delegates to the dashboard/ package for page assembly.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import cpm_live as cpm_module
from cpm_live import (
    RISKY_UNIVERSE, SAFE_POOL,
    CANARY_ASSETS, DEFAULT_CASH,
    CORR_LOOKBACK_DAYS, COST_BPS_PER_SIDE,
    TOP_K_CANDIDATES,
    load_panel,
    perf_metrics, compute_target_weights, sig_13612U,
)
from rpv_live import (
    COST_BPS_PER_SIDE as RPV_COST_BPS_PER_SIDE,
    compute_rpv_weights,
    compute_rpv_signals,
)
from ndx_sleeve_live import (
    compute_ndx_weights,
    run_ndx_backtest,
    COST_BPS_PER_SIDE as NDX_COST_BPS_PER_SIDE,
    PRICES_FILE as NDX_PRICES_FILE,
)
from core import cached_value_backtest

# Production blend: 60% CPM + 15% NDX + 15% VAL + 10% RPV
from config import CPM_WEIGHT as CPM_W, NDX_WEIGHT as NDX_W, VAL_WEIGHT as VAL_W, RPV_WEIGHT as RPV_W
RPV_BLEND = RPV_W

from dashboard_engine import (
    faber_gtaa5,
    keller_vaa_g4,
    _haa_safe_pick,
    _haa_run,
    haa_simple,
    haa_balanced,
    sixty_forty,
    qqq_trend_follow,
    _b_monthly_signal_dates,
    _b_build_port,
    bench_aaa_tip,
    bench_haa_simple,
    bench_qqq_12mo_trend,
    bench_static_pp_qqq,
    bench_bb4_blend,
    bench_blend_4leg,
    alpha_beta_corr,
    cpm_signal_records,
    _compute_cpm_signal_records,
    _load_macro_mooex_legs,
    _rebuild_ndx_constituent_opens_cache,
    _tail_refresh_ndx_opens_cache,
    _load_ndx_constituent_mooex_legs,
    rpv_signal_records,
    ndx_signal_records,
    build_artifacts,
    BOOTSTRAP_SINGLE_B,
    BOOTSTRAP_PAIRED_B,
    EXT_START,
    CASH_TICKER,
    RPV_EQUITY_TICKER,
)

__all__ = [
    "faber_gtaa5", "keller_vaa_g4", "_haa_safe_pick", "_haa_run", "haa_simple", "haa_balanced",
    "sixty_forty", "qqq_trend_follow", "_b_monthly_signal_dates", "_b_build_port", "bench_aaa_tip",
    "bench_haa_simple", "bench_qqq_12mo_trend", "bench_static_pp_qqq", "bench_bb4_blend", "bench_blend_4leg", "alpha_beta_corr",
    "cpm_signal_records", "_compute_cpm_signal_records", "_load_macro_mooex_legs", "_rebuild_ndx_constituent_opens_cache",
    "_tail_refresh_ndx_opens_cache", "_load_ndx_constituent_mooex_legs", "rpv_signal_records", "ndx_signal_records",
    "build_artifacts", "BOOTSTRAP_SINGLE_B", "BOOTSTRAP_PAIRED_B", "EXT_START", "CASH_TICKER", "RPV_EQUITY_TICKER",
    "CPM_W", "NDX_W", "VAL_W", "RPV_W", "RPV_BLEND", "load_panel", "compute_target_weights", "perf_metrics"
]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2008-05-30")
    ap.add_argument("--end", default=None)
    ap.add_argument("--out", default=str(ROOT / "cpm_dashboard.html"))
    args = ap.parse_args()

    from dashboard.context import build_context
    from dashboard.assemble import build

    print("Building Dashboard Context...")
    ctx = build_context(args)
    
    print("Assembling HTML...")
    html = build(args, ctx)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        f.write(html)
    print(f"\nDashboard written: {out_path}")
    print(f"File size: {out_path.stat().st_size / 1024:.1f} KB")

if __name__ == "__main__":
    main()
