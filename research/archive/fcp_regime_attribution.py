#!/usr/bin/env python3
"""
FCP Regime / Crisis Attribution Analysis
=========================================
Empirical question: when does FCP shine vs hurt?

For each crisis window and regime bucket:
  - FCP return / Sharpe / MaxDD
  - SPY, 60/40 (SPY+IEF monthly rebalance), PP-IEF static benchmarks
  - % months canary RISK_ON during window
  - Top pair holdings frequency
  - Average vol-target leverage during RISK_ON periods

Production spec (frozen):
  Universe (15 risky): QQQ,IGM,SPMO,XLE,XRT,COWZ,VBR,SPHQ,XMMO,XMHQ,XLV,VEA,VWO,GLD,TLT
  HOLD_BUFFER=2.5, TOP_K=7, vol-target @10%, 10bps/side cost

Save:
  script: strategy_fcp/research/fcp_regime_attribution.py
  log:    strategy_fcp/research/fcp_regime_attribution.log
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path
from collections import Counter

import numpy as np
import pandas as pd

# ── path setup ────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent.parent  # strategy_fcp/
sys.path.insert(0, str(SCRIPT_DIR))

from fcp_live import (
    load_panel,
    run_fcp_backtest,
    run_pp_backtest,
    RISKY_UNIVERSE,
    SAFE_POOL,
    CANARY_ASSETS,
    DEFAULT_CASH,
    PP_ASSETS,
    PP_WEIGHTS,
    TARGET_VOL,
    VOL_LOOKBACK_DAYS,
    MAX_LEVERAGE,
    COST_BPS_PER_SIDE,
)

warnings.filterwarnings("ignore")

# ── window definitions ─────────────────────────────────────────────────────────
CRISIS_WINDOWS = [
    ("dot-com bust",          "2000-03-01", "2002-09-30"),
    ("GFC",                   "2007-10-01", "2009-03-31"),
    ("EU debt scare",         "2010-05-01", "2010-08-31"),
    ("EU+US downgrade",       "2011-08-01", "2011-10-31"),
    ("oil/China shock",       "2015-08-01", "2016-02-29"),
    ("Q4 2018 selloff",       "2018-10-01", "2018-12-31"),
    ("COVID crash",           "2020-02-01", "2020-04-30"),
    ("COVID rally",           "2020-04-01", "2020-12-31"),
    ("reopening/inflation",   "2021-01-01", "2021-12-31"),
    ("2022 rate-shock bear",  "2022-01-01", "2022-10-31"),
    ("AI rally",              "2023-01-01", "2024-12-31"),
    ("2025-2026 cross-asset", "2025-01-01", "2026-05-16"),
]

REGIME_WINDOWS = [
    ("Low-vol bull 2013-2018", "2013-01-01", "2018-12-31"),
    ("Full backtest period",   "2001-09-01", "2026-05-16"),
]

# ── helpers ───────────────────────────────────────────────────────────────────

def window_metrics(daily, start, end):
    """Metrics for a daily return series over a specific window."""
    sub = daily.loc[start:end].dropna()
    if len(sub) < 5:
        return dict(total_return=float("nan"), cagr=float("nan"),
                    vol=float("nan"), sharpe=float("nan"), max_drawdown=float("nan"))
    eq = (1.0 + sub).cumprod()
    days = max((eq.index[-1] - eq.index[0]).days, 1)
    yrs = days / 365.25
    total_ret = eq.iloc[-1] - 1.0
    cagr = eq.iloc[-1] ** (1.0 / max(yrs, 1 / 252)) - 1.0
    vol = sub.std(ddof=0) * np.sqrt(252)
    sharpe = (sub.mean() * 252) / vol if vol > 1e-9 else float("nan")
    mdd = (eq / eq.cummax() - 1.0).min()
    return dict(total_return=total_ret, cagr=cagr, vol=vol, sharpe=sharpe, max_drawdown=mdd)


def build_6040(spy, ief, start, end):
    """60/40 (SPY/IEF) monthly rebalanced daily returns."""
    common = spy.index.intersection(ief.index)
    s = spy.reindex(common).fillna(0.0)
    b = ief.reindex(common).fillna(0.0)
    monthly_eom = pd.date_range(start, end, freq="ME")
    out = pd.Series(0.0, index=common)
    for i, d in enumerate(monthly_eom):
        nxt = monthly_eom[i + 1] if i + 1 < len(monthly_eom) else end
        mask = (out.index > d) & (out.index <= nxt)
        out.loc[mask] = 0.60 * s.loc[mask] + 0.40 * b.loc[mask]
    return out.loc[start:end]


def canary_stats(weights_history, start, end):
    months_total = 0
    months_risk_on = 0
    pair_counter = Counter()
    for h in weights_history:
        sig_d = h.get("sig_d")
        if sig_d is None:
            continue
        if not (start <= sig_d <= end):
            continue
        months_total += 1
        if h.get("regime") == "RISK_ON":
            months_risk_on += 1
            risky_w = {k: v for k, v in h["weights"].items()
                       if k not in SAFE_POOL and k != DEFAULT_CASH}
            if risky_w:
                pair_key = " + ".join(sorted(risky_w.keys()))
                pair_counter[pair_key] += 1
    pct = months_risk_on / months_total if months_total else 0.0
    top = pair_counter.most_common(3)
    return dict(pct_risk_on=pct, n_months=months_total,
                n_risk_on=months_risk_on, top_pairs=top)


def avg_leverage(leverage_daily, regime_per_day, start, end):
    mask = (leverage_daily.index >= start) & (leverage_daily.index <= end)
    lev_sub = leverage_daily.loc[mask]
    reg_sub = regime_per_day.loc[mask]
    risk_on_lev = lev_sub[reg_sub == "RISK_ON"].dropna()
    return risk_on_lev.mean() if len(risk_on_lev) > 0 else float("nan")


def fmt(v, pct=True, digits=1):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "   n/a"
    if pct:
        return f"{v * 100:+7.{digits}f}%"
    return f"{v:6.{digits+1}f}"


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    BACKTEST_START = pd.Timestamp("1999-01-01")
    BACKTEST_END   = pd.Timestamp("2026-05-16")

    print("=" * 80)
    print("FCP REGIME / CRISIS ATTRIBUTION ANALYSIS")
    print(f"Production spec: 15 risky, HOLD_BUFFER=2.5, TOP_K=7, vol-target 10%, 10bps/side")
    print("=" * 80)

    print("\n[1/6] Loading price panel ...")
    panel = load_panel(start=BACKTEST_START, end=BACKTEST_END)
    print(f"      Panel: {panel.index[0].date()} -> {panel.index[-1].date()}, "
          f"{len(panel.columns)} assets")

    print("\n[2/6] Running FCP backtest (with vol-target, 10bps cost) ...")
    fcp_net, weights_history = run_fcp_backtest(
        panel, BACKTEST_START, BACKTEST_END,
        apply_vol_target=True, cost_bps=COST_BPS_PER_SIDE,
    )
    print(f"      FCP net: {len(fcp_net)} trading days, "
          f"{len(weights_history)} monthly signals")

    print("[3/6] Running FCP gross (no vol-target, no cost) for leverage series ...")
    fcp_gross, _ = run_fcp_backtest(
        panel, BACKTEST_START, BACKTEST_END,
        apply_vol_target=False, cost_bps=0,
    )

    # Leverage daily series
    realized_vol = fcp_gross.rolling(VOL_LOOKBACK_DAYS).std() * np.sqrt(252)
    leverage_series = (TARGET_VOL / realized_vol).clip(upper=MAX_LEVERAGE).shift(1).fillna(1.0)

    # Regime per day
    regime_per_day = pd.Series("DEFENSIVE", index=fcp_net.index)
    for h in weights_history:
        af = h.get("apply_from", h.get("sig_d"))
        ea = h.get("end_apply", BACKTEST_END + pd.Timedelta(days=1))
        if af is not None and ea is not None:
            mask = (fcp_net.index >= af) & (fcp_net.index < ea)
            regime_per_day.loc[mask] = h.get("regime", "DEFENSIVE")

    print("[4/6] Building benchmarks (SPY, 60/40, PP-IEF) ...")
    spy_ret = panel["SPY"].ffill().pct_change().loc[BACKTEST_START:BACKTEST_END].fillna(0.0)
    ief_col = "IEF" if "IEF" in panel.columns else None
    ief_ret = panel[ief_col].ffill().pct_change().loc[BACKTEST_START:BACKTEST_END].fillna(0.0) \
              if ief_col else spy_ret * 0.0
    s6040 = build_6040(spy_ret, ief_ret, BACKTEST_START, BACKTEST_END)
    pp_ret = run_pp_backtest(panel, BACKTEST_START, BACKTEST_END)

    # SPY rolling metrics for dynamic regimes
    spy_vol_60d = spy_ret.rolling(60).std() * np.sqrt(252)
    spy_cum = (1 + spy_ret).cumprod()
    spy_6mo = spy_cum / spy_cum.shift(126) - 1.0

    print("[5/6] Computing window metrics ...")
    print()

    all_windows = CRISIS_WINDOWS + REGIME_WINDOWS
    rows = []

    for label, ws, we in all_windows:
        wstart = pd.Timestamp(ws)
        wend   = pd.Timestamp(we)
        wstart_eff = max(wstart, fcp_net.index[0])
        wend_eff   = min(wend,   fcp_net.index[-1])

        m_fcp = window_metrics(fcp_net,  wstart_eff, wend_eff)
        m_spy = window_metrics(spy_ret,  wstart_eff, wend_eff)
        m_60  = window_metrics(s6040,    wstart_eff, wend_eff)
        m_pp  = window_metrics(pp_ret,   wstart_eff, wend_eff)
        can   = canary_stats(weights_history, wstart_eff, wend_eff)
        lev   = avg_leverage(leverage_series, regime_per_day, wstart_eff, wend_eff)

        rows.append(dict(
            label=label, wstart=wstart, wend=wend,
            wstart_eff=wstart_eff, wend_eff=wend_eff,
            fcp=m_fcp, spy=m_spy, s6040=m_60, pp=m_pp,
            canary=can, avg_lev=lev,
        ))

    # Dynamic regime buckets
    dynamic_rows = []
    for regime_label, condition, _s in [
        ("High-vol (SPY 60d vol>20%)", spy_vol_60d > 0.20, spy_vol_60d),
        ("Risk-off (SPY 6mo ret<0%)",  spy_6mo < 0.0,      spy_6mo),
        ("Risk-on (SPY 6mo ret>10%)",  spy_6mo > 0.10,     spy_6mo),
    ]:
        mask = condition.reindex(fcp_net.index).fillna(False)
        days = int(mask.sum())
        if days < 20:
            continue
        fcp_sub  = fcp_net[mask]
        spy_sub  = spy_ret.reindex(fcp_net.index)[mask]
        s60_sub  = s6040.reindex(fcp_net.index)[mask]
        pp_sub   = pp_ret.reindex(fcp_net.index)[mask]

        def cond_metrics(sub):
            if len(sub) < 5:
                return {}
            ann_ret = sub.mean() * 252
            vol = sub.std(ddof=0) * np.sqrt(252)
            sh = ann_ret / vol if vol > 1e-9 else float("nan")
            return dict(ann_ret=ann_ret, vol=vol, sharpe=sh, n_days=len(sub))

        lev_sub = leverage_series.reindex(fcp_net.index)[mask]
        reg_sub = regime_per_day.reindex(fcp_net.index)[mask]
        lev_mean = lev_sub[reg_sub == "RISK_ON"].dropna().mean()
        dynamic_rows.append(dict(
            label=regime_label, days=days,
            fcp=cond_metrics(fcp_sub), spy=cond_metrics(spy_sub),
            s6040=cond_metrics(s60_sub), pp=cond_metrics(pp_sub),
            avg_lev=lev_mean,
        ))

    # ── print report ──────────────────────────────────────────────────────────
    print("[6/6] Writing report ...")
    print()
    sep = "=" * 130

    print(sep)
    print("SECTION 1: CRISIS & REGIME WINDOW COMPARISON TABLE")
    print(sep)
    print(
        f"{'Window':<26s}  {'Period':>22s}"
        f"  {'FCPRet':>8s}  {'FCPSh':>5s}  {'FCPdd':>7s}"
        f"  {'SPYRet':>8s}  {'SPYSh':>5s}  {'SPYdd':>7s}"
        f"  {'6040Ret':>8s}  {'6040Sh':>5s}  {'6040dd':>7s}"
        f"  {'PPRet':>8s}  {'PPSh':>5s}  {'PPdd':>7s}"
        f"  {'Alpha':>8s}"
        f"  {'%RiskOn':>7s}  {'AvgLev':>6s}"
    )
    print("-" * 130)

    crisis_rows = rows[:len(CRISIS_WINDOWS)]
    regime_rows = rows[len(CRISIS_WINDOWS):]

    for group_label, group_rows in [("Crisis windows", crisis_rows),
                                     ("Regime buckets", regime_rows)]:
        print(f"--- {group_label} ---")
        for r in group_rows:
            label_s = r["label"][:25]
            period  = f"{r['wstart_eff'].date()} / {r['wend_eff'].date()}"
            fcp     = r["fcp"]
            spy     = r["spy"]
            s60     = r["s6040"]
            pp      = r["pp"]
            can     = r["canary"]
            lev     = r["avg_lev"]

            fcp_ret = fcp.get("total_return", float("nan"))
            spy_ret_ = spy.get("total_return", float("nan"))
            alpha   = fcp_ret - spy_ret_ if not (np.isnan(fcp_ret) or np.isnan(spy_ret_)) else float("nan")

            lev_str = f"{lev:5.2f}" if not np.isnan(lev) else "  n/a"
            line = (
                f"{label_s:<26s}  {period:>22s}"
                f"  {fmt(fcp_ret):>8s}  {fmt(fcp.get('sharpe'), pct=False):>5s}  {fmt(fcp.get('max_drawdown')):>8s}"
                f"  {fmt(spy_ret_):>8s}  {fmt(spy.get('sharpe'), pct=False):>5s}  {fmt(spy.get('max_drawdown')):>8s}"
                f"  {fmt(s60.get('total_return')):>8s}  {fmt(s60.get('sharpe'), pct=False):>5s}  {fmt(s60.get('max_drawdown')):>8s}"
                f"  {fmt(pp.get('total_return')):>8s}  {fmt(pp.get('sharpe'), pct=False):>5s}  {fmt(pp.get('max_drawdown')):>8s}"
                f"  {fmt(alpha):>8s}"
                f"  {can['pct_risk_on']*100:6.0f}%  {lev_str}"
            )
            print(line)
        print()

    print(sep)
    print("SECTION 2: CRISIS WINDOW DETAIL — CANARY STATE & TOP PAIRS")
    print(sep)
    for r in crisis_rows:
        can = r["canary"]
        label = r["label"]
        period = f"{r['wstart_eff'].date()} to {r['wend_eff'].date()}"
        fcp_ret = r["fcp"].get("total_return", float("nan"))
        spy_ret_ = r["spy"].get("total_return", float("nan"))
        alpha = fcp_ret - spy_ret_ if not (np.isnan(fcp_ret) or np.isnan(spy_ret_)) else float("nan")

        if not np.isnan(alpha):
            verdict = "SHIELD ★" if alpha > 0.05 else "HURT ✗" if alpha < -0.05 else "NEUTRAL ≈"
        else:
            verdict = "NO DATA"

        print(f"\n  [{verdict}] {label}  ({period})")
        print(f"    FCP:  ret={fmt(fcp_ret)}  Sharpe={fmt(r['fcp'].get('sharpe'),pct=False)}  MaxDD={fmt(r['fcp'].get('max_drawdown'))}")
        print(f"    SPY:  ret={fmt(spy_ret_)}  Sharpe={fmt(r['spy'].get('sharpe'),pct=False)}  MaxDD={fmt(r['spy'].get('max_drawdown'))}")
        print(f"    60/40: ret={fmt(r['s6040'].get('total_return'))}  PP: ret={fmt(r['pp'].get('total_return'))}")
        print(f"    Alpha (FCP-SPY): {fmt(alpha)}")
        print(f"    Canary: {can['pct_risk_on']*100:.0f}% RISK_ON "
              f"({can['n_risk_on']}/{can['n_months']} signal months)")
        avg_lev_val = r["avg_lev"]
        lev_str = f"{avg_lev_val:.2f}x" if not np.isnan(avg_lev_val) else "n/a"
        print(f"    Avg vol-target leverage (RISK_ON days): {lev_str}")
        if can["top_pairs"]:
            print(f"    Top pair holdings:")
            for pair_str, cnt in can["top_pairs"]:
                print(f"      {pair_str}  ({cnt} signal months)")
        else:
            print(f"    Top pairs: [all defensive - safe asset held]")

    print()
    print(sep)
    print("SECTION 3: DYNAMIC REGIME BUCKETS (conditioned days, non-contiguous)")
    print(sep)
    print(f"Note: ann_ret = daily_mean * 252 (not geometric CAGR); MaxDD not reported (non-contiguous)")
    print(f"\n{'Regime':<36s}  {'Days':>5s}  "
          f"{'FCP AnnRet':>10s}  {'FCP Sh':>6s}  "
          f"{'SPY AnnRet':>10s}  {'SPY Sh':>6s}  "
          f"{'60/40 AnnRet':>12s}  {'60/40 Sh':>8s}  "
          f"{'PP AnnRet':>9s}  {'PP Sh':>6s}  {'AvgLev':>6s}")
    print("-" * 110)
    for r in dynamic_rows:
        fcp  = r["fcp"]
        spy  = r["spy"]
        s60  = r["s6040"]
        pp   = r["pp"]
        lev  = r["avg_lev"]
        lev_str = f"{lev:.2f}" if not np.isnan(lev) else "   n/a"
        print(f"{r['label']:<36s}  {r['days']:>5d}  "
              f"{fmt(fcp.get('ann_ret')):>10s}  {fmt(fcp.get('sharpe'), pct=False):>6s}  "
              f"{fmt(spy.get('ann_ret')):>10s}  {fmt(spy.get('sharpe'), pct=False):>6s}  "
              f"{fmt(s60.get('ann_ret')):>12s}  {fmt(s60.get('sharpe'), pct=False):>8s}  "
              f"{fmt(pp.get('ann_ret')):>9s}  {fmt(pp.get('sharpe'), pct=False):>6s}  "
              f"{lev_str:>6s}")

    # ── narrative ─────────────────────────────────────────────────────────────
    print()
    print(sep)
    print("SECTION 4: QUALITATIVE NARRATIVE")
    print(sep)

    shields = [r for r in crisis_rows
               if not np.isnan(r["fcp"].get("total_return", float("nan")))
               and not np.isnan(r["spy"].get("total_return", float("nan")))
               and r["fcp"]["total_return"] - r["spy"]["total_return"] > 0.05]
    hurts   = [r for r in crisis_rows
               if not np.isnan(r["fcp"].get("total_return", float("nan")))
               and not np.isnan(r["spy"].get("total_return", float("nan")))
               and r["fcp"]["total_return"] - r["spy"]["total_return"] < -0.05]
    neutrals = [r for r in crisis_rows if r not in shields and r not in hurts]

    print(f"\n>>> CRISES WHERE FCP SHIELDED (alpha > +5% vs SPY): {len(shields)}")
    for r in shields:
        can = r["canary"]
        alpha = r["fcp"]["total_return"] - r["spy"]["total_return"]
        dd_gap = r["fcp"]["max_drawdown"] - r["spy"]["max_drawdown"]
        print(f"\n  {r['label']} ({r['wstart_eff'].date()} -> {r['wend_eff'].date()})")
        print(f"    FCP {fmt(r['fcp']['total_return'])} vs SPY {fmt(r['spy']['total_return'])} | alpha {fmt(alpha)} | DD gap {fmt(dd_gap)} (FCP-SPY, negative = FCP better)")
        print(f"    Canary: {can['pct_risk_on']*100:.0f}% months risk-on ({can['n_risk_on']}/{can['n_months']})")
        if can["top_pairs"]:
            print(f"    Dominant hold: {can['top_pairs'][0][0]}")

    print(f"\n>>> CRISES WHERE FCP HURT (alpha < -5% vs SPY): {len(hurts)}")
    for r in hurts:
        can = r["canary"]
        alpha = r["fcp"]["total_return"] - r["spy"]["total_return"]
        dd_gap = r["fcp"]["max_drawdown"] - r["spy"]["max_drawdown"]
        print(f"\n  {r['label']} ({r['wstart_eff'].date()} -> {r['wend_eff'].date()})")
        print(f"    FCP {fmt(r['fcp']['total_return'])} vs SPY {fmt(r['spy']['total_return'])} | alpha {fmt(alpha)} | DD gap {fmt(dd_gap)}")
        print(f"    Canary: {can['pct_risk_on']*100:.0f}% months risk-on | "
              f"may reflect momentum chase or whipsaw")
        if can["top_pairs"]:
            print(f"    Dominant hold: {can['top_pairs'][0][0]}")

    print(f"\n>>> NEUTRAL / MIXED (|alpha| < 5%): {len(neutrals)}")
    for r in neutrals:
        alpha = r["fcp"].get("total_return", float("nan")) - r["spy"].get("total_return", float("nan"))
        print(f"  {r['label']}: FCP {fmt(r['fcp'].get('total_return'))} vs SPY {fmt(r['spy'].get('total_return'))} | alpha {fmt(alpha)}")

    print("""
─────────────────────────────────────────────────────────────────────────────
CANARY INTERPRETATION:
  0% risk-on during crash      = canary fired early (clean defensive posture)
  100% risk-on during crash    = canary missed / fired after the fact
  Partial risk-on during crash = partial protection; check for month-end timing gap

VOL-TARGET LEVERAGE:
  avg_lev < 0.80 = systematically de-risked (high realized vol period)
  avg_lev ~ 1.00 = near-target
  avg_lev = 1.00 = MAX_LEVERAGE cap hit (MAX_LEVERAGE=1.0, no borrowing)

DATA CONFIDENCE BY ERA:
  HIGH  : 2010-present  (most ETFs live; proxy only for COWZ/SPMO/XMMO/XMHQ)
  MEDIUM: 2007-2010     (VBR live 2004; GLD stitched; major ETFs live)
  LOW   : 2000-2007     (COWZ/SPMO/XMMO/XMHQ/VBR/VEA/VWO heavily proxied)
─────────────────────────────────────────────────────────────────────────────
""")

    print("=" * 80)
    print("END OF REPORT")
    print("=" * 80)


if __name__ == "__main__":
    main()
