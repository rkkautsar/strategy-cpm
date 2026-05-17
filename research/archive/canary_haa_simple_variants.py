"""HAA-Simple style backtest: SPY-only risk asset, various canaries.

Rule template:
  1. Compute canary state (e.g. TIP or HYG or HYG+TIP)
  2. If canary risk-off -> 100% best safe
  3. Else: if SPY 13612W > 0 -> 100% SPY, else 100% best safe

Tests how far back each canary can go (with stitched proxies):
  - TIP proxy = stitched (VIPSX) from ~1996
  - HYG proxy = stitched (VWEHX) from 1980
  - SPY = live from 1993

So canary backtest can go back to ~1997 (need 12mo of canary history).

Compares:
  - HAA-Simple (TIP canary, the canonical Keller spec)
  - HYG alone canary
  - HYG+TIP both+ canary
  - HYG+TIP any+ canary
  - NOCAN (SPY momentum only, no canary)
  - SPY buy-hold baseline
  - 60/40 SPY/IEF baseline
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import fcp_live as fcp  # type: ignore
from fcp_live import (
    SAFE_POOL, DEFAULT_CASH, load_panel, best_safe, perf_metrics, sig_13612W,
)

ALIASES = {"HYG": "HYG_stitched", "AGG": "AGG_stitched"}
COST_BPS = 10  # bps per side


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


def run_haa_simple_variant(panel, start, end, canaries, rule_fn, label,
                            risk_asset="SPY", cost_bps=COST_BPS):
    """Run HAA-Simple style: canary + SPY-momentum filter on SPY-only risk asset."""
    cols_needed = sorted(set([risk_asset] + SAFE_POOL + [DEFAULT_CASH] +
                              [ALIASES.get(c, c) for c in canaries] + ["SPY", "IEF"])
                        & set(panel.columns))
    close = panel[cols_needed]

    monthly_idx = pd.DataFrame({"x": 1}, index=close.index).groupby(pd.Grouper(freq="ME")).tail(1)
    sigs = monthly_idx.index[(monthly_idx.index >= start) & (monthly_idx.index <= end)].tolist()

    weights_history = []
    n_risk = n_def = 0
    for i, sig_d in enumerate(sigs):
        mon_full = panel.loc[:sig_d].resample("ME").last()
        safe = best_safe(mon_full[[c for c in SAFE_POOL if c in mon_full.columns]],
                         sig_d, [c for c in SAFE_POOL if c in mon_full.columns])

        # Canary check
        if canaries:
            state = get_state(mon_full, sig_d, canaries)
            if state is None or not rule_fn(state):
                w = {safe: 1.0}
                n_def += 1
                weights_history.append({"sig_d": sig_d, "weights": w})
                continue

        # SPY momentum filter
        if risk_asset in mon_full.columns:
            spy_sig = sig_13612W(mon_full[risk_asset].loc[:sig_d])
            if pd.isna(spy_sig) or spy_sig <= 0:
                w = {safe: 1.0}
                n_def += 1
                weights_history.append({"sig_d": sig_d, "weights": w})
                continue

        w = {risk_asset: 1.0}
        n_risk += 1
        weights_history.append({"sig_d": sig_d, "weights": w})

    # Build daily returns
    all_assets = sorted({a for h in weights_history for a in h["weights"]})
    df_w = pd.DataFrame(0.0, index=close.index, columns=[a for a in all_assets if a in close.columns])
    for i, h in enumerate(weights_history):
        sig_d = h["sig_d"]
        future = close.index[close.index > sig_d]
        if len(future) < 2:
            continue
        apply_from = future[1]
        if i + 1 < len(weights_history):
            next_sig = weights_history[i + 1]["sig_d"]
            next_future = close.index[close.index > next_sig]
            end_apply = next_future[1] if len(next_future) >= 2 else end
        else:
            end_apply = end
        mask = (close.index >= apply_from) & (close.index < end_apply)
        for a, ww in h["weights"].items():
            if a in df_w.columns:
                df_w.loc[mask, a] = ww

    daily_ret = close.ffill().pct_change()
    common = [a for a in df_w.columns if a in daily_ret.columns]
    raw = (df_w[common] * daily_ret[common]).sum(axis=1, min_count=1).fillna(0.0)

    # Costs
    for i, h in enumerate(weights_history):
        prev_w = weights_history[i - 1]["weights"] if i > 0 else {}
        curr_w = h["weights"]
        turnover = sum(abs(curr_w.get(k, 0.0) - prev_w.get(k, 0.0))
                       for k in set(curr_w) | set(prev_w))
        cost = turnover * cost_bps / 10000.0
        future = close.index[close.index > h["sig_d"]]
        if len(future) >= 2 and future[1] in raw.index:
            raw.loc[future[1]] -= cost

    rets = raw.loc[(raw.index >= start) & (raw.index <= end)]
    pct_risk = n_risk / max(1, n_risk + n_def) * 100
    return rets, pct_risk


def benchmark(panel, asset, start, end):
    r = panel[asset].ffill().pct_change().fillna(0)
    return r.loc[(r.index >= start) & (r.index <= end)]


def benchmark_60_40(panel, start, end):
    spy = panel["SPY"].ffill().pct_change().fillna(0)
    ief = panel["IEF"].ffill().pct_change().fillna(0)
    common = spy.index.intersection(ief.index)
    blend = 0.6 * spy.loc[common] + 0.4 * ief.loc[common]
    return blend.loc[(blend.index >= start) & (blend.index <= end)]


def main():
    out_path = Path(__file__).parent / "canary_haa_simple_variants.log"
    log_lines = []
    def log(s=""):
        log_lines.append(s); print(s)

    log("=" * 100)
    log("HAA-SIMPLE STYLE BACKTEST: SPY-only risk asset with various canaries")
    log("Rule: canary risk-on AND SPY 13612W > 0 -> 100% SPY. Else 100% best safe.")
    log("Cost: 10bps/side per turnover")
    log("=" * 100)

    panel = load_panel(start=pd.Timestamp("1994-01-01"))
    log(f"Panel: {panel.index[0].date()} -> {panel.index[-1].date()}")

    # Earliest valid signal date: 12mo after latest stitched series start
    # TIP_stitched starts 1996, HYG_stitched starts 1980, SPY 1993
    # So 1997-01 is earliest with all signals valid
    earliest = pd.Timestamp("1997-04-30")
    end = panel.index[-1]
    log(f"Backtest window: {earliest.date()} -> {end.date()} ({(end-earliest).days/365.25:.1f}y)")
    log("")

    variants = [
        ("HAA-Simple (TIP)",        ["TIP"],         lambda s: s["TIP"]),
        ("HYG only",                ["HYG"],         lambda s: s["HYG"]),
        ("HYG+TIP both+",           ["HYG","TIP"],   lambda s: s["HYG"] and s["TIP"]),
        ("HYG+TIP any+",            ["HYG","TIP"],   lambda s: s["HYG"] or s["TIP"]),
        ("SPY+TIP both+ (FCP)",     ["SPY","TIP"],   lambda s: s["SPY"] and s["TIP"]),
        ("SPY+HYG both+",           ["SPY","HYG"],   lambda s: s["SPY"] and s["HYG"]),
        ("NOCAN (SPY mom only)",    [],              lambda s: True),
    ]

    results = []
    for label, cans, rfn in variants:
        rets, pct_r = run_haa_simple_variant(panel, earliest, end, cans, rfn, label)
        m = perf_metrics(rets)
        log(f"  {label:32s}  Sh={m['sharpe']:+.3f}  CAGR={m['cagr']*100:+6.2f}%  "
            f"Vol={m['vol']*100:5.2f}%  DD={m['max_drawdown']*100:+6.2f}%  pct_risk={pct_r:.1f}%")
        results.append((label, m, pct_r))

    # Benchmarks
    log("")
    log("  --- Benchmarks ---")
    spy_r = benchmark(panel, "SPY", earliest, end)
    m_spy = perf_metrics(spy_r)
    log(f"  {'SPY buy-hold':32s}  Sh={m_spy['sharpe']:+.3f}  CAGR={m_spy['cagr']*100:+6.2f}%  "
        f"Vol={m_spy['vol']*100:5.2f}%  DD={m_spy['max_drawdown']*100:+6.2f}%")
    ief_r = benchmark(panel, "IEF", earliest, end)
    m_ief = perf_metrics(ief_r)
    log(f"  {'IEF buy-hold':32s}  Sh={m_ief['sharpe']:+.3f}  CAGR={m_ief['cagr']*100:+6.2f}%  "
        f"Vol={m_ief['vol']*100:5.2f}%  DD={m_ief['max_drawdown']*100:+6.2f}%")
    sf_r = benchmark_60_40(panel, earliest, end)
    m_sf = perf_metrics(sf_r)
    log(f"  {'60/40 SPY/IEF':32s}  Sh={m_sf['sharpe']:+.3f}  CAGR={m_sf['cagr']*100:+6.2f}%  "
        f"Vol={m_sf['vol']*100:5.2f}%  DD={m_sf['max_drawdown']*100:+6.2f}%")
    log("")

    log("=" * 100)
    log("Sub-window comparison: LIVE 18y (2008-09-30)")
    log("=" * 100)
    log("")
    live_start = pd.Timestamp("2008-09-30")
    for label, cans, rfn in variants:
        rets, pct_r = run_haa_simple_variant(panel, live_start, end, cans, rfn, label)
        m = perf_metrics(rets)
        log(f"  {label:32s}  Sh={m['sharpe']:+.3f}  CAGR={m['cagr']*100:+6.2f}%  "
            f"DD={m['max_drawdown']*100:+6.2f}%  pct_risk={pct_r:.1f}%")
    spy_l = benchmark(panel, "SPY", live_start, end)
    m_spy_l = perf_metrics(spy_l)
    log(f"  {'SPY buy-hold':32s}  Sh={m_spy_l['sharpe']:+.3f}  CAGR={m_spy_l['cagr']*100:+6.2f}%  "
        f"DD={m_spy_l['max_drawdown']*100:+6.2f}%")
    sf_l = benchmark_60_40(panel, live_start, end)
    m_sf_l = perf_metrics(sf_l)
    log(f"  {'60/40 SPY/IEF':32s}  Sh={m_sf_l['sharpe']:+.3f}  CAGR={m_sf_l['cagr']*100:+6.2f}%  "
        f"DD={m_sf_l['max_drawdown']*100:+6.2f}%")

    log("")
    log("=" * 100)
    log("Sub-window comparison: PRE-CRISIS 1997-2007 (10y, includes dot-com)")
    log("=" * 100)
    log("")
    pre_start = pd.Timestamp("1997-04-30")
    pre_end = pd.Timestamp("2007-12-31")
    for label, cans, rfn in variants:
        rets, pct_r = run_haa_simple_variant(panel, pre_start, pre_end, cans, rfn, label)
        m = perf_metrics(rets)
        log(f"  {label:32s}  Sh={m['sharpe']:+.3f}  CAGR={m['cagr']*100:+6.2f}%  "
            f"DD={m['max_drawdown']*100:+6.2f}%  pct_risk={pct_r:.1f}%")
    spy_p = benchmark(panel, "SPY", pre_start, pre_end)
    m_spy_p = perf_metrics(spy_p)
    log(f"  {'SPY buy-hold':32s}  Sh={m_spy_p['sharpe']:+.3f}  CAGR={m_spy_p['cagr']*100:+6.2f}%  "
        f"DD={m_spy_p['max_drawdown']*100:+6.2f}%")

    log("")
    log("=" * 100)
    with open(out_path, "w") as f:
        f.write("\n".join(log_lines))
    print(f"\nLog: {out_path}")


if __name__ == "__main__":
    main()
