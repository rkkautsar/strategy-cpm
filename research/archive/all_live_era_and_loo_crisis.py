#!/usr/bin/env python3
"""
FCP Validation Tests
  TEST 1: All-live post-2016 era (2017-01-01 → today)
           All 15 universe ETFs trade live — COWZ inception 2016-12 is binding.
           Benchmarks: SPY, 60/40, PP-IEF. Bootstrap Sharpe CI B=3000.
  TEST 2: Leave-one-year / leave-one-crisis robustness (18y window)
           Drop each year in 2008-2025, recompute Sharpe/CAGR/DD.
           Drop each crisis window, recompute. Fragility threshold |ΔSh|>0.30.

Run from: /Users/rkautsar/personal/scripts
  python strategy_fcp/research/all_live_era_and_loo_crisis.py
"""
from __future__ import annotations

import sys
import logging
import numpy as np
import pandas as pd
from pathlib import Path

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_PATH = Path(__file__).parent / "all_live_era_and_loo_crisis.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_PATH, mode="w"),
    ],
)
log = logging.getLogger()

# ── Path setup ────────────────────────────────────────────────────────────────
SCRIPTS_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(SCRIPTS_ROOT))

from strategy_fcp.fcp_live import (  # noqa: E402
    load_panel,
    run_fcp_backtest,
    run_pp_backtest,
    RISKY_UNIVERSE,
    COST_BPS_PER_SIDE,
)


# ══════════════════════════════════════════════════════════════════════════════
# Metrics helpers
# ══════════════════════════════════════════════════════════════════════════════

def perf_metrics_ext(daily: pd.Series) -> dict:
    """Sharpe, CAGR, Vol, MaxDD, Sortino, Calmar, UPI."""
    d = daily.dropna()
    nan_row = {k: np.nan for k in ["cagr", "vol", "sharpe", "max_drawdown",
                                    "sortino", "calmar", "upi", "n_years"]}
    if len(d) < 20:
        return nan_row

    eq = (1.0 + d).cumprod()
    yrs = (d.index[-1] - d.index[0]).days / 365.25
    cagr = (eq.iloc[-1] / eq.iloc[0]) ** (1 / yrs) - 1 if yrs > 0 else np.nan
    vol = d.std(ddof=0) * np.sqrt(252)
    ann_ret = d.mean() * 252
    sharpe = ann_ret / vol if vol > 0 else np.nan

    rm = eq.cummax()
    dd_series = eq / rm - 1
    mdd = dd_series.min()
    calmar = cagr / abs(mdd) if pd.notna(mdd) and mdd != 0 else np.nan

    down = d[d < 0]
    ds = down.std(ddof=0) * np.sqrt(252) if len(down) > 5 else np.nan
    sortino = ann_ret / ds if ds and ds > 0 else np.nan

    # UPI = ann_ret / ulcer_index (ulcer in decimal)
    ulcer = np.sqrt((dd_series ** 2).mean())
    upi = ann_ret / ulcer if ulcer > 0 else np.nan

    return dict(cagr=cagr, vol=vol, sharpe=sharpe, max_drawdown=mdd,
                sortino=sortino, calmar=calmar, upi=upi, n_years=round(yrs, 2))


def bootstrap_sharpe_ci(daily: pd.Series, B: int = 3000, block: int = 21,
                         ci: float = 0.95) -> tuple[float, float, float]:
    """Circular block bootstrap 95% Sharpe CI. Returns (lo, hi, point_est)."""
    d = daily.dropna().values
    n = len(d)
    if n < 63:
        return (np.nan, np.nan, np.nan)

    ann = np.sqrt(252)
    point = (d.mean() * 252) / (d.std(ddof=0) * ann)

    rng = np.random.default_rng(42)
    boot = np.empty(B)
    n_blocks = int(np.ceil(n / block))
    for i in range(B):
        starts = rng.integers(0, n, size=n_blocks)
        idx = np.concatenate([np.arange(s, s + block) % n for s in starts])[:n]
        s = d[idx]
        sd = s.std(ddof=0)
        boot[i] = (s.mean() * 252) / (sd * ann) if sd > 0 else np.nan

    alpha = (1 - ci) / 2
    lo = float(np.nanpercentile(boot, alpha * 100))
    hi = float(np.nanpercentile(boot, (1 - alpha) * 100))
    return lo, hi, float(point)


# ══════════════════════════════════════════════════════════════════════════════
# Benchmark helpers
# ══════════════════════════════════════════════════════════════════════════════

def spy_bh(panel: pd.DataFrame, start, end) -> pd.Series:
    return panel["SPY"].ffill().pct_change().loc[start:end].fillna(0.0)


def sixty_forty(panel: pd.DataFrame, start, end) -> pd.Series:
    """60% SPY + 40% IEF, monthly rebalanced."""
    cols = ["SPY", "IEF"]
    missing = [c for c in cols if c not in panel.columns]
    if missing:
        log.warning(f"60/40: missing {missing}, skipping")
        return pd.Series(dtype=float)
    close = panel[cols].ffill()
    monthly_ends = close.resample("ME").last().index
    monthly_ends = monthly_ends[(monthly_ends >= start) & (monthly_ends <= end)]
    dr = close.pct_change()
    w = pd.Series({"SPY": 0.60, "IEF": 0.40})
    out = pd.Series(0.0, index=close.index)
    for i, d in enumerate(monthly_ends):
        nxt = monthly_ends[i + 1] if i + 1 < len(monthly_ends) else end
        seg = close.index[(close.index > d) & (close.index <= nxt)]
        out.loc[seg] = dr.loc[seg].mul(w, axis=1).sum(axis=1).fillna(0.0)
    return out.loc[start:end]


# ══════════════════════════════════════════════════════════════════════════════
# TEST 1 — All-live post-2016 era
# ══════════════════════════════════════════════════════════════════════════════

def run_test1(panel: pd.DataFrame):
    log.info("")
    log.info("=" * 72)
    log.info("TEST 1  All-Live Post-2016 Era")
    log.info("  Window : 2017-01-01 -> today (~9y)")
    log.info("  All 15 universe ETFs trade live -- COWZ inception 2016-12 is binding")
    log.info("  Vol-target ON @10%, 10 bps/side cost")
    log.info("=" * 72)

    start = pd.Timestamp("2017-01-01")
    end   = pd.Timestamp.today().normalize()

    log.info(f"\nRunning FCP backtest {start.date()} -> {end.date()} ...")
    fcp_daily, _ = run_fcp_backtest(panel, start, end)

    log.info("Running PP-IEF backtest ...")
    pp_daily = run_pp_backtest(panel, start, end)

    spy    = spy_bh(panel, start, end)
    s6040  = sixty_forty(panel, start, end)

    common = fcp_daily.index
    combos = [
        ("FCP (standalone)",     fcp_daily),
        ("PP-IEF (25/25/25/25)", pp_daily.reindex(common).fillna(0.0)),
        ("SPY buy-hold",         spy.reindex(common).fillna(0.0)),
        ("60/40 SPY/IEF",        s6040.reindex(common).fillna(0.0)),
    ]

    log.info("")
    hdr = (f"{'Strategy':<26} {'CAGR':>7} {'Vol':>6} {'Sharpe':>7}"
           f" {'MaxDD':>8} {'Sortino':>8} {'Calmar':>7} {'UPI':>7} {'Yrs':>5}")
    log.info(hdr)
    log.info("-" * len(hdr))

    for label, ret in combos:
        m = perf_metrics_ext(ret)
        log.info(
            f"{label:<26}"
            f" {m['cagr']*100:6.2f}%"
            f" {m['vol']*100:5.2f}%"
            f" {m['sharpe']:7.3f}"
            f" {m['max_drawdown']*100:7.2f}%"
            f" {m['sortino']:8.3f}"
            f" {m['calmar']:7.3f}"
            f" {m['upi']:7.3f}"
            f" {m['n_years']:5.1f}"
        )

    # Bootstrap Sharpe CI
    log.info("")
    log.info("Bootstrap Sharpe CI -- FCP standalone (B=3000, block=21d, 95%, circular block):")
    lo, hi, pt = bootstrap_sharpe_ci(fcp_daily, B=3000, block=21)
    m_fcp = perf_metrics_ext(fcp_daily)
    log.info(f"  Point estimate : {pt:.3f}")
    log.info(f"  95% CI         : [{lo:.3f}, {hi:.3f}]")
    log.info(f"  Window         : {m_fcp['n_years']:.1f}y -- CI is wide (expected for <10y)")

    log.info("")
    log.info("CAVEATS:")
    log.info("  . ~9y is short for momentum strategies with infrequent tail events")
    log.info("  . CI width reflects genuine estimation uncertainty -- not a flaw")
    log.info("  . FCP standalone (no PP blend) -- isolates risky sleeve only")
    log.info("  . This window avoids ALL proxy data: clean live-ETF prices throughout")


# ══════════════════════════════════════════════════════════════════════════════
# TEST 2 — Leave-one-year / leave-one-crisis
# ══════════════════════════════════════════════════════════════════════════════

CRISIS_WINDOWS = {
    "GFC 2008":          ("2007-10-01", "2009-03-31"),
    "EU Debt 2010-11":   ("2010-04-01", "2011-10-31"),
    "Oil/China 2015-16": ("2015-06-01", "2016-02-29"),
    "Q4 2018":           ("2018-10-01", "2018-12-31"),
    "COVID 2020":        ("2020-02-01", "2020-04-30"),
    "2022 Bear":         ("2022-01-01", "2022-12-31"),
}


def _sharpe(d: pd.Series) -> float:
    d = d.dropna()
    if len(d) < 20:
        return np.nan
    vol = d.std(ddof=0) * np.sqrt(252)
    return (d.mean() * 252) / vol if vol > 0 else np.nan


def _cagr(d: pd.Series) -> float:
    d = d.dropna()
    if len(d) < 20:
        return np.nan
    eq = (1 + d).cumprod()
    yrs = len(d) / 252
    return eq.iloc[-1] ** (1 / yrs) - 1 if yrs > 0 else np.nan


def _mdd(d: pd.Series) -> float:
    d = d.dropna()
    if len(d) < 2:
        return np.nan
    eq = (1 + d).cumprod()
    return (eq / eq.cummax() - 1).min()


def run_test2(panel: pd.DataFrame):
    log.info("")
    log.info("=" * 72)
    log.info("TEST 2  Leave-One-Year / Leave-One-Crisis Robustness")
    log.info("  Full window : 2007-01-01 -> today (~18y production run)")
    log.info("  Method      : drop each year / crisis -> recompute Sh, CAGR, DD")
    log.info("  Fragility   : |DSh| > 0.30 per spec")
    log.info("=" * 72)

    start_18y = pd.Timestamp("2007-01-01")
    end       = pd.Timestamp.today().normalize()

    log.info(f"\nComputing 18y FCP backtest {start_18y.date()} -> {end.date()} ...")
    full, _ = run_fcp_backtest(panel, start_18y, end)

    baseline_sh   = _sharpe(full)
    baseline_cagr = _cagr(full)
    baseline_dd   = _mdd(full)

    log.info(f"\nBaseline (full window):")
    log.info(f"  Sharpe={baseline_sh:.3f}  CAGR={baseline_cagr*100:.2f}%  MaxDD={baseline_dd*100:.2f}%")
    log.info(f"  N={len(full)} days  ({full.index[0].date()} -> {full.index[-1].date()})")

    # -- Leave-one-year -------------------------------------------------------
    log.info("")
    log.info("-- Leave-One-Year ----------------------------------------------------------")
    hdr = (f"{'Year':>6}  {'Sharpe':>7}  {'DSh':>7}  {'CAGR':>7}  {'DCAGR':>7}"
           f"  {'MaxDD':>7}  {'Flag':>8}")
    log.info(hdr)
    log.info("-" * len(hdr))

    year_rows = []
    for yr in range(2008, 2026):
        dropped = full.loc[full.index.year != yr]
        sh  = _sharpe(dropped)
        cg  = _cagr(dropped)
        dd  = _mdd(dropped)
        dsh = sh - baseline_sh
        dcg = (cg - baseline_cagr) * 100 if pd.notna(cg) else np.nan
        flag = "FRAGILE" if abs(dsh) > 0.30 else ""
        log.info(
            f"{yr:>6}  {sh:7.3f}  {dsh:+7.3f}  {cg*100:6.2f}%  {dcg:+6.2f}pp"
            f"  {dd*100:6.2f}%  {flag:>8}"
        )
        year_rows.append(dict(year=yr, sharpe=sh, delta_sh=dsh,
                               cagr=cg, mdd=dd, fragile=bool(flag)))

    yrdf = pd.DataFrame(year_rows)
    best_yr  = yrdf.loc[yrdf.delta_sh.idxmin()]
    worst_yr = yrdf.loc[yrdf.delta_sh.idxmax()]
    frag_yr  = yrdf[yrdf.fragile]

    log.info("")
    log.info("Summary (leave-one-year):")
    log.info(f"  Most alpha-adding year (drop -> worst Sharpe):  {int(best_yr.year)}"
             f"  DSh={best_yr.delta_sh:+.3f}")
    log.info(f"  Biggest drag year (drop -> best Sharpe):        {int(worst_yr.year)}"
             f"  DSh={worst_yr.delta_sh:+.3f}")
    if not frag_yr.empty:
        log.info(f"  FRAGILE years |DSh|>0.30: {list(frag_yr.year.astype(int))}")
    else:
        log.info("  No fragile years -- |DSh| <= 0.30 for every single-year drop")

    # -- Leave-one-crisis -----------------------------------------------------
    log.info("")
    log.info("-- Leave-One-Crisis --------------------------------------------------------")
    hdr2 = (f"{'Crisis':<22}  {'Sharpe':>7}  {'DSh':>7}  {'CAGR':>7}  {'DCAGR':>7}"
            f"  {'MaxDD':>7}  {'Flag':>8}")
    log.info(hdr2)
    log.info("-" * len(hdr2))

    crisis_rows = []
    for name, (cs, ce) in CRISIS_WINDOWS.items():
        dropped = full.loc[(full.index < cs) | (full.index > ce)]
        sh  = _sharpe(dropped)
        cg  = _cagr(dropped)
        dd  = _mdd(dropped)
        dsh = sh - baseline_sh
        dcg = (cg - baseline_cagr) * 100 if pd.notna(cg) else np.nan
        flag = "FRAGILE" if abs(dsh) > 0.30 else ""
        log.info(
            f"{name:<22}  {sh:7.3f}  {dsh:+7.3f}  {cg*100:6.2f}%  {dcg:+6.2f}pp"
            f"  {dd*100:6.2f}%  {flag:>8}"
        )
        crisis_rows.append(dict(crisis=name, sharpe=sh, delta_sh=dsh,
                                 cagr=cg, mdd=dd, fragile=bool(flag)))

    crdf = pd.DataFrame(crisis_rows)
    best_cr  = crdf.loc[crdf.delta_sh.idxmin()]
    worst_cr = crdf.loc[crdf.delta_sh.idxmax()]
    frag_cr  = crdf[crdf.fragile]

    log.info("")
    log.info("Summary (leave-one-crisis):")
    log.info(f"  Most alpha-adding crisis (drop -> worst Sharpe):  {best_cr.crisis}"
             f"  DSh={best_cr.delta_sh:+.3f}")
    log.info(f"  Biggest drag crisis (drop -> best Sharpe):        {worst_cr.crisis}"
             f"  DSh={worst_cr.delta_sh:+.3f}")
    if not frag_cr.empty:
        log.info(f"  FRAGILE crises |DSh|>0.30: {list(frag_cr.crisis)}")
    else:
        log.info("  No fragile crises -- |DSh| <= 0.30 for every single-crisis drop")

    log.info("")
    log.info("INTERPRETATION GUIDE:")
    log.info("  DSh < 0  removing that period HURTS   -> strategy ADDED alpha there")
    log.info("  DSh > 0  removing that period HELPS   -> strategy STRUGGLED there")
    log.info("  FRAGILE  |DSh| > 0.30 -- single period dominates the Sharpe story")


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

def main():
    log.info("=" * 72)
    log.info("  FCP VALIDATION: ALL-LIVE ERA + LEAVE-ONE-OUT CRISIS ROBUSTNESS")
    log.info("=" * 72)
    log.info(f"Generated : {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log.info(f"Universe  : {RISKY_UNIVERSE}")
    log.info("Config    : HOLD_BUFFER=2.5, TOP_K=7, vol-target ON@10%, 10bps/side")

    log.info("\nLoading panel (from 2006-01-01) ...")
    panel = load_panel(start=pd.Timestamp("2006-01-01"))
    log.info(f"Panel: {panel.index[0].date()} -> {panel.index[-1].date()}, "
             f"{len(panel.columns)} assets")

    if "COWZ" in panel.columns:
        first = panel["COWZ"].first_valid_index()
        log.info(f"COWZ first live date: {first.date() if first else 'N/A'}"
                 f"  (confirms 2016-12 binding constraint for Test 1)")

    run_test1(panel)
    run_test2(panel)

    log.info("")
    log.info("=" * 72)
    log.info(f"DONE.  Log -> {LOG_PATH}")


if __name__ == "__main__":
    main()
