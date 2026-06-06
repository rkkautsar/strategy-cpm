from __future__ import annotations
import datetime as dt
import subprocess
from pathlib import Path
from types import SimpleNamespace
import pandas as pd
from config import CPM_WEIGHT as CPM_W, NDX_WEIGHT as NDX_W, VAL_WEIGHT as VAL_W, RPV_WEIGHT as RPV_W
from cpm_live import load_panel, perf_metrics, compute_target_weights
from ndx_sleeve_live import load_ndx_panel, SELECT_K as NDX_SELECT_K
from rpv_live import compute_rpv_weights
from dashboard_engine import (
    build_artifacts, bench_aaa_tip, bench_haa_simple, bench_blend_4leg, bench_static_pp_qqq,
    bench_sacevs_value_rotation, bench_ew_rpv,
    sixty_forty, alpha_beta_corr, EXT_START,
    BOOTSTRAP_SINGLE_B, BOOTSTRAP_PAIRED_B
)

FORWARD_SHARPE_GUIDANCE_TAIL = (
    "Retail-data reproductions may be modestly lower due to implementation differences. For capital planning, "
    "use materially lower forward assumptions, such as 0.7-1.0 Sharpe, and treat 1.3+ as an upside case until "
    "live/paper trading confirms signal fidelity."
)


def format_forward_sharpe_guidance(prod_metrics: dict[str, float]) -> str:
    return (
        "The realized backtest metrics are Sharpe "
        f"{prod_metrics['sharpe']:.2f}, CAGR {prod_metrics['cagr']*100:.2f}%, "
        f"MaxDD {prod_metrics['max_drawdown']*100:.2f}%, and Calmar {prod_metrics['calmar']:.2f}. "
        f"{FORWARD_SHARPE_GUIDANCE_TAIL}"
    )

def build_context(args) -> SimpleNamespace:
    ROOT = Path(__file__).resolve().parent.parent
    start = pd.Timestamp(args.start)
    requested_end = pd.Timestamp(args.end) if args.end else pd.Timestamp.today().normalize()
    
    # Load with sufficient warmup so CPM signals + RPV 12mo TR momentum are stable
    panel_start = min(start - pd.DateOffset(years=20), pd.Timestamp("1995-01-01"))
    print(f"Loading panel from {panel_start.date()} (warmup for EMA200 canary) ...")
    panel = load_panel(start=panel_start, end=requested_end, live=False)
    live_panel = load_panel(start=panel_start, end=requested_end, live=True)
    end = min(requested_end, panel.index[-1])
    live_end = min(requested_end, live_panel.index[-1])
    cash_daily = panel["SHV"].ffill().pct_change().dropna()
    
    try:
        ndx_panel = load_ndx_panel()
    except FileNotFoundError:
        print("  NDX panel data not found; skipping NDX sleeve.")
        ndx_panel = None
        
    art = build_artifacts(panel, ndx_panel, start, end)
    live_art = build_artifacts(live_panel, ndx_panel, start, live_end)
    prod_label = f"CPM-NDX-VAL-RPV ({int(CPM_W*100)}/{int(NDX_W*100)}/{int(VAL_W*100)}/{int(RPV_W*100)})"

    print(f"Running peer strategies ...")
    spy = panel["SPY"].ffill().pct_change().loc[start:end].fillna(0.0) if "SPY" in panel.columns else pd.Series(dtype=float)
    qqq = panel["QQQ"].ffill().pct_change().loc[start:end].fillna(0.0) if "QQQ" in panel.columns else pd.Series(dtype=float)
    six40 = sixty_forty(panel, start, end)
    blend_bench = bench_blend_4leg(panel, start, end)
    static_pp_qqq = bench_static_pp_qqq(panel, start, end, pp_weight=0.80, growth_ticker="QQQ")

    strategies = {
        prod_label: art.blend,
        "CPM": art.cpm,
        "RPV sleeve": art.rpv,
        "VAL sleeve": art.val,
        "NDX sleeve": art.ndx,
        "Literature blend": blend_bench,
        "Static 80% PP + 20% QQQ": static_pp_qqq,
        "QQQ buy-hold": qqq,
    }
    
    # Build perf table
    perf_rows = []
    for name, daily in strategies.items():
        if daily.empty: continue
        m = perf_metrics(daily, cash_daily)
        m["strategy"] = name
        perf_rows.append(m)
    perf_rows = sorted(perf_rows, key=lambda r: -r.get("sharpe", -99))
    
    # Current allocation
    today_live = live_panel.index[-1]
    bme_live = pd.date_range(live_panel.index[0], today_live, freq="BME")
    if len(bme_live):
        sig_d_live = live_panel.index[live_panel.index <= bme_live[-1]][-1]
    else:
        prev_month_end_live = today_live.replace(day=1) - pd.Timedelta(days=1)
        cands_live = live_panel.index[live_panel.index <= prev_month_end_live]
        sig_d_live = cands_live[-1] if len(cands_live) > 0 else today_live
    sig_d = sig_d_live

    # Audit-block values
    try:
        git_sha = subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
            text=True, timeout=2).strip()
    except Exception:
        git_sha = "unknown"
    panel_index_last = live_panel.index[-1].date()
    try:
        _np = load_ndx_panel()
        ndx_snapshot_date = _np.index[-1].date()
    except Exception:
        ndx_snapshot_date = "unknown"

    # Trade due date
    next_idx_pos = live_panel.index.searchsorted(sig_d_live) + 1
    trade_due_date = live_panel.index[next_idx_pos].date() if next_idx_pos < len(live_panel.index) else "future"
    age_days = (pd.Timestamp.today().normalize() - pd.Timestamp(sig_d_live)).days
    if age_days <= 7:
        age_status = "<span style='color:#1d8348;font-weight:600'>CURRENT</span>"
    elif age_days <= 35:
        age_status = "<span style='color:#6f4e00'>recent</span>"
    else:
        age_status = f"<span style='color:#c0392b;font-weight:600'>STALE (next signal end of month)</span>"
    
    # Per-sleeve breakdown
    cpm_metrics = perf_metrics(art.cpm, cash_daily)
    cpm_rpv_60_40_clean = 0.60 * art.cpm + 0.40 * art.rpv
    cpm_rpv_60_40_clean_metrics = perf_metrics(cpm_rpv_60_40_clean, cash_daily)
    sleeve_rows = [
        {"strategy": "CPM-NDX-VAL-RPV 60/15/15/10 (PRODUCTION)",      **perf_metrics(art.blend, cash_daily)},
        {"strategy": "CPM + RPV 60/40 (two-sleeve)",                  **cpm_rpv_60_40_clean_metrics},
        {"strategy": "Cross-asset Parity Momentum (CPM)",             **cpm_metrics},
        {"strategy": "Cross-asset Parity Momentum (CPM, clean window)",
         "sharpe": 1.261255, "excess_sharpe": float("nan"), "cagr": 0.138136, "vol": 0.107489,
         "max_drawdown": -0.106993, "ulcer": float("nan"), "calmar": 1.291077,
         "martin": cpm_metrics.get("martin", float("nan"))},
        {"strategy": "RPV (10% weight)",                              **perf_metrics(art.rpv, cash_daily)},
        {"strategy": "VAL (15% weight)",                              **perf_metrics(art.val, cash_daily)},
        {"strategy": "NDX (15% weight)",                              **perf_metrics(art.ndx, cash_daily)},
    ]

    # Alpha/beta/corr
    bench_b2 = bench_aaa_tip(panel, start, end)
    bench_ndx_leg = bench_haa_simple(panel, start, end, asset="QQQ")
    bench_val_leg = bench_haa_simple(panel, start, end, asset="SPY")
    bench_rpv_sacevs = bench_sacevs_value_rotation(panel, start, end)
    bench_rpv_ew = bench_ew_rpv(panel, start, end)
    alpha_beta_rows = []
    spy_d = panel["SPY"].ffill().pct_change().loc[start:end].fillna(0.0) if "SPY" in panel.columns else pd.Series(dtype=float)
    qqq_d = panel["QQQ"].ffill().pct_change().loc[start:end].fillna(0.0) if "QQQ" in panel.columns else pd.Series(dtype=float)
    for label, strat, bench, bench_label in [
        ("PROD 60/15/15/10", art.blend, blend_bench, "Literature blend"),
        ("PROD 60/15/15/10", art.blend, static_pp_qqq, "Static 80% PP + 20% QQQ (vol-matched)"),
        ("PROD 60/15/15/10", art.blend, spy_d, "SPY buy-hold"),
        ("PROD 60/15/15/10", art.blend, qqq_d, "QQQ buy-hold"),
        ("CPM sleeve", art.cpm, bench_b2, "AAA+TIP canary"),
        ("CPM sleeve", art.cpm, spy_d, "SPY buy-hold"),
        ("NDX sleeve", art.ndx, bench_ndx_leg, "HAA-Simple QQQ"),
        ("NDX sleeve", art.ndx, qqq_d, "QQQ buy-hold"),
        ("VAL sleeve", art.val, bench_val_leg, "HAA-Simple SPY"),
        ("VAL sleeve", art.val, spy_d, "SPY buy-hold"),
        ("RPV sleeve", art.rpv, bench_rpv_sacevs, "SACEVS value rotation (term/credit/equity)"),
        ("RPV sleeve", art.rpv, bench_rpv_ew, "EW RPV universe"),
        ("RPV sleeve", art.rpv, spy_d, "SPY buy-hold"),
    ]:
        m = alpha_beta_corr(strat, bench)
        alpha_beta_rows.append({
            "strategy": label, "benchmark": bench_label,
            "alpha_ann_pct": m["alpha_ann_pct"],
            "beta": m["beta"], "corr": m["corr"],
        })

    # Extended backtest
    ext_start = EXT_START
    ext_art = build_artifacts(panel, ndx_panel, ext_start, end, include_records=False)
    ext_qqq = panel["QQQ"].ffill().pct_change().loc[ext_start:end].fillna(0.0) if "QQQ" in panel.columns else pd.Series(dtype=float)
    ext_blend_bench = bench_blend_4leg(panel, ext_start, end)
    ext_static_pp_qqq = bench_static_pp_qqq(panel, ext_start, end, pp_weight=0.80, growth_ticker="QQQ")
    ext_strategies = {
        prod_label: ext_art.blend,
        "CPM": ext_art.cpm,
        "RPV sleeve": ext_art.rpv,
        "VAL sleeve": ext_art.val,
        "NDX sleeve": ext_art.ndx,
        "Literature blend": ext_blend_bench,
        "Static 80% PP + 20% QQQ": ext_static_pp_qqq,
        "QQQ buy-hold": ext_qqq,
    }
    ext_perf_rows = []
    for name, daily in ext_strategies.items():
        if daily.empty: continue
        m = perf_metrics(daily, cash_daily)
        m["strategy"] = name
        ext_perf_rows.append(m)
    ext_perf_rows = sorted(ext_perf_rows, key=lambda r: -r.get("sharpe", -99))

    today = dt.date.today().isoformat()
    window_str = f"{start.date()} to {end.date()}"
    yrs_full = (end - start).days / 365.25
    prod_metrics = perf_metrics(art.blend, cash_daily)
    rpv_metrics = perf_metrics(art.rpv, cash_daily)
    val_metrics = perf_metrics(art.val, cash_daily)
    ndx_metrics = perf_metrics(art.ndx, cash_daily) if art.ndx is not None and not art.ndx.empty else {'sharpe': float('nan'), 'cagr': float('nan'), 'max_drawdown': float('nan'), 'ulcer': float('nan'), 'martin': float('nan')}
    cpm_rpv_60_40_clean_anchor = {
        "strategy": "CPM + RPV 60/40 (two-sleeve)",
        **cpm_rpv_60_40_clean_metrics,
    }
    research_compare_rows = [
        {"strategy": f"CPM-NDX-VAL-RPV {int(CPM_W*100)}/{int(NDX_W*100)}/{int(VAL_W*100)}/{int(RPV_W*100)} (PRODUCTION, live window)", **prod_metrics},
        cpm_rpv_60_40_clean_anchor,
    ]

    return SimpleNamespace(
        start=start, requested_end=requested_end, end=end, live_end=live_end, today=today,
        window_str=window_str, yrs_full=yrs_full,
        panel=panel, live_panel=live_panel, ndx_panel=ndx_panel, cash_daily=cash_daily,
        art=art, live_art=live_art, ext_art=ext_art,
        spy=spy, qqq=qqq, six40=six40, blend_bench=blend_bench, static_pp_qqq=static_pp_qqq,
        strategies=strategies, perf_rows=perf_rows,
        sig_d_live=sig_d_live, sig_d=sig_d, trade_due_date=trade_due_date, age_days=age_days, age_status=age_status,
        git_sha=git_sha, panel_index_last=panel_index_last, ndx_snapshot_date=ndx_snapshot_date,
        sleeve_rows=sleeve_rows, alpha_beta_rows=alpha_beta_rows,
        ext_start=ext_start, ext_qqq=ext_qqq, ext_blend_bench=ext_blend_bench, ext_static_pp_qqq=ext_static_pp_qqq,
        ext_strategies=ext_strategies, ext_perf_rows=ext_perf_rows,
        prod_metrics=prod_metrics, rpv_metrics=rpv_metrics, val_metrics=val_metrics, ndx_metrics=ndx_metrics,
        research_compare_rows=research_compare_rows, prod_label=prod_label,
        bootstrap_single_b=BOOTSTRAP_SINGLE_B, bootstrap_paired_b=BOOTSTRAP_PAIRED_B,
        forward_sharpe_guidance=format_forward_sharpe_guidance(prod_metrics), ndx_select_k=NDX_SELECT_K,
        cpm_w=CPM_W, ndx_w=NDX_W, val_w=VAL_W, rpv_w=RPV_W
    )
