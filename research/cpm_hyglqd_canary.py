#!/usr/bin/env python3
"""
HYG/LQD credit-spread z-score as a sharper CPM canary signal.

Tests credit-leg canary variants vs production HYG-OR-TIP and HYG-only, in the
60/40 two-sleeve CPM+BULL baseline. MEASUREMENT ONLY -- no production files edited.

Variants (CPM canary; risk-off -> 100% best_safe):
  C0 (PROD)  HYG OR TIP        : 13612U(HYG)>0 OR 13612U(TIP)>0
  C3 HYG-only                  : 13612U(HYG)>0
  Z1 HYG/LQD ratio trend       : 13612U(HYG/LQD ratio)>0
  Z2 HYG/LQD z-score           : z=(ratio-mean252)/std252 ; risk-on if z>thr (thr in {-1,0})
  Z3 breadth-preserving 2-leg  : HYG-trend OR HYG/LQD-z (also AND tested)

Everything else fixed: positive-Faber filter + EAA(vol-adj) rank + K=4 + min-var pair.
Only the CPM canary varies. BULL sleeve fixed at production (HYG OR TIP).

DATA NOTE: HYG live 2007-04 (VWEHX stitch pre); LQD live 2002-07 (VFICX IG corp
bond fund stitch 1993-11+). HYG/LQD ratio is CLEAN post-2007-04; pre-2007 it is a
mutual-fund proxy (VWEHX/VFICX 1999-2002, VWEHX/LQD 2002-2007). Stress-window
HYG/LQD results pre-2007 are PROXY-FLAGGED.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import cpm_live as C
from cpm_live import (
    load_panel,
    run_cpm_backtest,
    faber_sma_xs,
    sig_13612U,
    best_safe,
    min_vol_pair,
    perf_metrics,
)
from bull_spy_live import run_bull_spy_backtest

CLEAN_START = pd.Timestamp("2008-05-30")
STRESS_START = pd.Timestamp("1999-03-10")
END = pd.Timestamp("2026-05-22")

TOP_K = C.TOP_K_CANDIDATES
LOOKBACK = C.CORR_LOOKBACK_DAYS
COST = C.COST_BPS_PER_SIDE
UNIVERSE = C.RISKY_UNIVERSE
SAFE_POOL = C.SAFE_POOL
DEFAULT_CASH = C.DEFAULT_CASH


# ---------- Canary decision functions ----------
# Each returns risk_on: bool. No-data => risk-off (matches production).

def _mom(monthly, c):
    if c not in monthly.columns:
        return np.nan
    return sig_13612U(monthly[c])


def canary_C0(close, monthly, sig_d):
    scores = [_mom(monthly, c) for c in ("HYG", "TIP")]
    scores = [s for s in scores if pd.notna(s)]
    if not scores:
        return False
    return any(s > 0 for s in scores)


def canary_C3(close, monthly, sig_d):
    s = _mom(monthly, "HYG")
    if pd.isna(s):
        return False
    return s > 0


def _ratio_monthly(monthly):
    if "HYG" not in monthly.columns or "LQD" not in monthly.columns:
        return None
    return (monthly["HYG"] / monthly["LQD"]).dropna()


def canary_Z1(close, monthly, sig_d):
    r = _ratio_monthly(monthly)
    if r is None:
        return False
    s = sig_13612U(r)
    if pd.isna(s):
        return False
    return s > 0


def _ratio_z(close, sig_d, win=252):
    if "HYG" not in close.columns or "LQD" not in close.columns:
        return np.nan
    sub = close.loc[:sig_d, ["HYG", "LQD"]].dropna()
    if len(sub) < win + 1:
        return np.nan
    ratio = sub["HYG"] / sub["LQD"]
    roll = ratio.tail(win)
    mu = roll.mean()
    sd = roll.std(ddof=0)
    if pd.isna(sd) or sd == 0:
        return np.nan
    return (ratio.iloc[-1] - mu) / sd


def make_Z2(thr):
    def f(close, monthly, sig_d):
        z = _ratio_z(close, sig_d)
        if pd.isna(z):
            return False
        return z > thr
    f.__name__ = f"canary_Z2_thr{thr}"
    return f


def make_Z3(thr, mode="OR"):
    def f(close, monthly, sig_d):
        hyg = _mom(monthly, "HYG")
        hyg_ok = pd.notna(hyg) and hyg > 0
        z = _ratio_z(close, sig_d)
        z_ok = pd.notna(z) and z > thr
        if pd.isna(hyg) and pd.isna(z):
            return False
        if mode == "OR":
            return hyg_ok or z_ok
        return hyg_ok and z_ok
    f.__name__ = f"canary_Z3_{mode}_thr{thr}"
    return f


# ---------- Variant CPM allocation (production logic, pluggable canary) ----------
# Exact copy of cpm_live.compute_target_weights body except the canary block.

def compute_tw_variant(close_panel, sig_d, canary_fn,
                       universe=UNIVERSE, safe_pool=SAFE_POOL):
    monthly = close_panel.loc[:sig_d].resample("ME").last()
    safe = best_safe(monthly, sig_d, safe_pool)

    if not canary_fn(close_panel, monthly, sig_d):
        return {safe: 1.0}, None, "DEFENSIVE", safe

    faber = faber_sma_xs(monthly)
    avail = [t for t in universe
             if t in faber.index and pd.notna(faber[t])
             and pd.notna(close_panel.loc[sig_d].get(t, np.nan) if sig_d in close_panel.index else np.nan)]
    if not avail:
        return {safe: 1.0}, None, "DEFENSIVE", safe

    daily_rets = close_panel[avail].ffill().pct_change()
    scores = {}
    for t in avail:
        v = daily_rets[t].loc[:sig_d].tail(252).std() * np.sqrt(252)
        if pd.isna(v) or v < 1e-9:
            v = 1.0
        scores[t] = float(faber[t]) / v
    sa = pd.Series(scores)
    ranked = sa.sort_values(ascending=False)
    top_k = max(2, min(TOP_K, len(ranked)))
    top = ranked.iloc[:top_k]
    positive = top[top.index.map(lambda t: faber.get(t, -np.inf) > 0)]

    if len(positive) < 2:
        if len(positive) == 1:
            return {positive.index[0]: 0.5, safe: 0.5}, None, "RISK_ON", safe
        return {safe: 1.0}, None, "DEFENSIVE", safe

    candidates = list(positive.index)
    new_pick = min_vol_pair(close_panel.loc[:sig_d, candidates], candidates, LOOKBACK)
    if new_pick is None:
        return {candidates[0]: 1.0}, None, "RISK_ON", safe
    return {new_pick[0]: 0.5, new_pick[1]: 0.5}, new_pick, "RISK_ON", safe


def run_cpm_variant(panel, start, end, canary_fn, cost_bps=COST):
    """Mirror of cpm_live.run_cpm_backtest with pluggable canary.
    Returns (daily_returns, weights_history)."""
    cols = sorted(set(UNIVERSE + SAFE_POOL + ["HYG", "TIP", "LQD"] + [DEFAULT_CASH]) & set(panel.columns))
    close = panel[cols]

    monthly_idx = pd.DataFrame({"x": 1}, index=close.index).groupby(pd.Grouper(freq="ME")).tail(1)
    signal_dates = monthly_idx.index[(monthly_idx.index >= start) & (monthly_idx.index <= end)].tolist()

    weights_history = []
    for i, sig_d in enumerate(signal_dates):
        w, new_pair, regime, safe = compute_tw_variant(close, sig_d, canary_fn)
        future = close.index[close.index > sig_d]
        if len(future) < 1:
            continue
        apply_from = future[0]
        if i + 1 < len(signal_dates):
            next_sig = signal_dates[i + 1]
            next_future = close.index[close.index > next_sig]
            end_apply = next_future[0] if len(next_future) >= 1 else end
        else:
            end_apply = end
        weights_history.append({
            "apply_from": apply_from, "end_apply": end_apply,
            "weights": w, "sig_d": sig_d, "regime": regime, "safe": safe,
        })

    all_assets = sorted({a for h in weights_history for a in h["weights"]})
    df_w = pd.DataFrame(0.0, index=close.index, columns=[a for a in all_assets if a in close.columns])
    for h in weights_history:
        mask = (close.index >= h["apply_from"]) & (close.index < h["end_apply"])
        for a, ww in h["weights"].items():
            if a in df_w.columns:
                df_w.loc[mask, a] = ww

    daily_ret = close.ffill().pct_change()
    common = [a for a in df_w.columns if a in daily_ret.columns]
    raw_returns = (df_w[common] * daily_ret[common]).sum(axis=1, min_count=1).fillna(0.0)

    for i in range(len(weights_history)):
        prev_w = weights_history[i - 1]["weights"] if i > 0 else {}
        curr_w = weights_history[i]["weights"]
        keys = set(curr_w) | set(prev_w)
        turnover = sum(abs(curr_w.get(k, 0.0) - prev_w.get(k, 0.0)) for k in keys)
        cost = turnover * cost_bps / 10000.0
        af = weights_history[i]["apply_from"]
        if af in raw_returns.index:
            raw_returns.loc[af] -= cost

    out = raw_returns.loc[(raw_returns.index >= start) & (raw_returns.index <= end)]
    return out, weights_history


# ---------- Panel with stitched LQD injected (clean IG proxy back to 1993) ----------

def load_panel_lqd():
    # Load FULL history (no start trim) so 504d covariance + 252d vol lookbacks
    # are fully populated at each window start. Inject stitched LQD (VFICX IG
    # corp bond fund 1993-11+ -> LQD 2002-07+) for clean IG-credit history.
    panel = load_panel()
    lqd_path = ROOT / "data" / "lqd_stitched_daily.csv"
    if lqd_path.exists():
        lqd = pd.read_csv(lqd_path, parse_dates=[0], index_col=0).iloc[:, 0]
        lqd.name = "LQD"
        if "LQD" in panel.columns:
            panel = panel.drop(columns=["LQD"]).join(lqd, how="outer").sort_index()
        else:
            panel = panel.join(lqd, how="outer").sort_index()
    return panel


def annual_turnover(wh):
    """Average annualized one-way turnover from weights_history."""
    if not wh:
        return float("nan")
    tos = []
    for i in range(len(wh)):
        prev = wh[i - 1]["weights"] if i > 0 else {}
        curr = wh[i]["weights"]
        keys = set(prev) | set(curr)
        tos.append(0.5 * sum(abs(curr.get(k, 0.0) - prev.get(k, 0.0)) for k in keys))
    return float(np.mean(tos) * 12.0)


def _dd(daily, a, b):
    seg = daily.loc[a:b]
    if seg.empty:
        return float("nan")
    eq = (1 + seg).cumprod()
    return float((eq / eq.cummax() - 1).min())


def cal_return(daily, year):
    seg = daily.loc[f"{year}-01-01":f"{year}-12-31"]
    if seg.empty:
        return float("nan")
    return float((1 + seg).prod() - 1)


def sub_metrics(daily, a, b, cash=None):
    seg = daily.loc[a:b]
    if seg.empty:
        return {}
    cseg = cash.reindex(seg.index).fillna(0.0) if cash is not None else None
    return perf_metrics(seg, cseg)


# ---------- Cohort / crisis diagnostics ----------

def canary_block_diagnostics(panel, canary_fn, start, end):
    """Months the canary blocks risk-on (independent of Faber), with forward
    1-month CPM-universe (equal-weight risky) AND SPY returns of blocked vs
    allowed months. Splits blocked into bad-forward (correct de-risk) vs
    false-positive (gave up upside)."""
    cols = sorted(set(UNIVERSE + SAFE_POOL + ["HYG", "TIP", "LQD", "SPY", DEFAULT_CASH]) & set(panel.columns))
    close = panel[cols]
    monthly_idx = pd.DataFrame({"x": 1}, index=close.index).groupby(pd.Grouper(freq="ME")).tail(1)
    sig_dates = monthly_idx.index[(monthly_idx.index >= start) & (monthly_idx.index <= end)].tolist()

    risky = [t for t in UNIVERSE if t in panel.columns]
    uni_m = panel[risky].resample("ME").last()
    spy_m = panel["SPY"].resample("ME").last() if "SPY" in panel.columns else None

    blocked_fwd, allowed_fwd, block_dates = [], [], []
    for sig_d in sig_dates:
        m = close.loc[:sig_d].resample("ME").last()
        ok = canary_fn(close, m, sig_d)
        block = not ok
        # forward 1m equal-weight risky-universe return
        after = uni_m.index[uni_m.index > sig_d]
        here = uni_m.index[uni_m.index <= sig_d]
        fwd = np.nan
        if len(after) >= 1 and len(here) >= 1:
            r = (uni_m.loc[after[0]] / uni_m.loc[here[-1]] - 1).dropna()
            if len(r):
                fwd = float(r.mean())
        if block:
            blocked_fwd.append(fwd)
            block_dates.append(sig_d)
        else:
            allowed_fwd.append(fwd)

    def summ(lst):
        arr = np.array([x for x in lst if pd.notna(x)])
        if arr.size == 0:
            return dict(n=0, mean=float("nan"), pct_neg=float("nan"))
        return dict(n=int(arr.size), mean=float(arr.mean()), pct_neg=float((arr < 0).mean() * 100))

    nb = len(blocked_fwd)
    bad = sum(1 for x in blocked_fwd if pd.notna(x) and x < 0)   # correct de-risk
    fp = sum(1 for x in blocked_fwd if pd.notna(x) and x >= 0)   # false positive
    return dict(
        n_months=len(sig_dates), n_blocked=nb,
        pct_blocked=100.0 * nb / len(sig_dates) if sig_dates else float("nan"),
        blocked=summ(blocked_fwd), allowed=summ(allowed_fwd),
        bad_forward=bad, false_positive=fp,
        block_dates=[d.strftime("%Y-%m") for d in block_dates],
    )


def first_block_into_crisis(panel, canary_fns, crisis_start, lookback_start):
    """For each canary, the LAST month it was risk-on before crisis (i.e. how
    EARLY it flipped to risk-off going into the crisis). Returns first risk-off
    month at/after lookback_start that precedes crisis trough."""
    cols = sorted(set(UNIVERSE + SAFE_POOL + ["HYG", "TIP", "LQD", DEFAULT_CASH]) & set(panel.columns))
    close = panel[cols]
    monthly_idx = pd.DataFrame({"x": 1}, index=close.index).groupby(pd.Grouper(freq="ME")).tail(1)
    sig_dates = monthly_idx.index[(monthly_idx.index >= pd.Timestamp(lookback_start)) &
                                  (monthly_idx.index <= pd.Timestamp(crisis_start))].tolist()
    out = {}
    for name, fn in canary_fns.items():
        first_off = None
        for sig_d in sig_dates:
            m = close.loc[:sig_d].resample("ME").last()
            if not fn(close, m, sig_d):
                first_off = sig_d
                break
        out[name] = first_off.strftime("%Y-%m") if first_off is not None else "never"
    return out


# ---------- Main battery ----------

VARIANTS = {
    "C0_PROD_HYGorTIP": canary_C0,
    "C3_HYGonly": canary_C3,
    "Z1_ratio_trend": canary_Z1,
    "Z2_z_gt_-1": make_Z2(-1.0),
    "Z2_z_gt_0": make_Z2(0.0),
    "Z3_OR_z-1": make_Z3(-1.0, "OR"),
    "Z3_AND_z-1": make_Z3(-1.0, "AND"),
}


def fmt_row(name, scope, m, to):
    return (f"| {name} | {scope} | {m.get('sharpe', float('nan')):.3f} | "
            f"{m.get('excess_sharpe', float('nan')):.3f} | {m.get('cagr', float('nan'))*100:.2f}% | "
            f"{m.get('vol', float('nan'))*100:.2f}% | {m.get('max_drawdown', float('nan'))*100:.2f}% | "
            f"{m.get('calmar', float('nan')):.2f} | {to*100:.0f}% |")


def main():
    out_md = ROOT / "research" / "cpm_hyglqd_canary_findings.md"
    print("Loading full-history panel + stitched LQD ...")
    panel = load_panel_lqd()
    print(f"panel {panel.index[0].date()} -> {panel.index[-1].date()} cols={len(panel.columns)}")
    cash_daily = panel["SHV"].ffill().pct_change().dropna()

    # ---- Verification gate: variant-C0 == production run_cpm_backtest ----
    prod_cpm, _ = run_cpm_backtest(panel, CLEAN_START, END, cost_bps=COST)
    var_cpm, _ = run_cpm_variant(panel, CLEAN_START, END, canary_C0, cost_bps=COST)
    com = prod_cpm.index.intersection(var_cpm.index)
    diff = float((prod_cpm.reindex(com) - var_cpm.reindex(com)).abs().max())
    mp = perf_metrics(prod_cpm, cash_daily)
    bull_cl = run_bull_spy_backtest(panel, CLEAN_START, END, cost_bps=COST)
    cb = prod_cpm.index.intersection(bull_cl.index)
    blend0 = 0.6 * prod_cpm.reindex(cb) + 0.4 * bull_cl.reindex(cb)
    mb = perf_metrics(blend0, cash_daily)
    print(f"VERIFY diff={diff:.2e}  CPM {mp['sharpe']:.3f}/{mp['cagr']*100:.2f}%/{mp['vol']*100:.2f}%/{mp['max_drawdown']*100:.2f}%")
    print(f"       blend {mb['sharpe']:.3f}/{mb['cagr']*100:.2f}%/{mb['max_drawdown']*100:.2f}%")
    repro_cpm = abs(mp['sharpe'] - 1.263) < 0.01 and abs(mp['cagr'] - 0.1458) < 0.002
    repro_bl = abs(mb['sharpe'] - 1.347) < 0.01 and abs(mb['max_drawdown'] - (-0.0982)) < 0.003
    assert diff < 1e-9, f"C0 replication mismatch (daily): {diff}"
    if not (repro_cpm and repro_bl):
        print(f"WARNING: C0 metric reproduction off. cpm_ok={repro_cpm} blend_ok={repro_bl}")

    # ---- BULL sleeves (fixed across variants) ----
    bull_st = run_bull_spy_backtest(panel, STRESS_START, END, cost_bps=COST)

    rows_cpm, rows_bl = [], []
    crisis_rows = []
    diag = {}
    for name, fn in VARIANTS.items():
        print(f"=== {name} ===")
        cpm_cl, wh_cl = run_cpm_variant(panel, CLEAN_START, END, fn, cost_bps=COST)
        cpm_st, wh_st = run_cpm_variant(panel, STRESS_START, END, fn, cost_bps=COST)
        com_cl = cpm_cl.index.intersection(bull_cl.index)
        com_st = cpm_st.index.intersection(bull_st.index)
        bl_cl = 0.6 * cpm_cl.reindex(com_cl) + 0.4 * bull_cl.reindex(com_cl)
        bl_st = 0.6 * cpm_st.reindex(com_st) + 0.4 * bull_st.reindex(com_st)

        rows_cpm.append(fmt_row(name, "Clean", perf_metrics(cpm_cl, cash_daily), annual_turnover(wh_cl)))
        rows_cpm.append(fmt_row(name, "Stress*", perf_metrics(cpm_st, cash_daily), annual_turnover(wh_st)))
        rows_bl.append(fmt_row(name, "Clean", perf_metrics(bl_cl, cash_daily), annual_turnover(wh_cl)))
        rows_bl.append(fmt_row(name, "Stress*", perf_metrics(bl_st, cash_daily), annual_turnover(wh_st)))

        # crisis sub-periods (CPM standalone on stress panel; blend too)
        def crow(label, a, b):
            mc = sub_metrics(cpm_st, a, b, cash_daily)
            mbl = sub_metrics(bl_st, a, b, cash_daily)
            return (f"| {name} | {label} | {cal_return(cpm_st, int(a[:4])) if a[5:7]=='01' else float('nan'):.4f} "
                    f"| {mc.get('sharpe', float('nan')):.2f} | {mc.get('max_drawdown', float('nan'))*100:.2f}% "
                    f"| {mbl.get('sharpe', float('nan')):.2f} | {mbl.get('max_drawdown', float('nan'))*100:.2f}% |")
        crisis_rows.append(crow("2008 GFC", "2007-10-01", "2009-06-30"))
        crisis_rows.append(crow("2015-16", "2015-06-01", "2016-06-30"))
        crisis_rows.append(crow("2020 COVID", "2020-01-01", "2020-12-31"))
        crisis_rows.append(crow("2022", "2022-01-01", "2022-12-31"))

        diag[name] = dict(
            clean=canary_block_diagnostics(panel, fn, CLEAN_START, END),
            stress=canary_block_diagnostics(panel, fn, STRESS_START, END),
        )

    # ---- Earliness into credit crises ----
    early = {
        "2008 GFC (off before 2008-09)": first_block_into_crisis(panel, VARIANTS, "2008-09-30", "2007-06-30"),
        "2015-16 credit (off before 2016-02)": first_block_into_crisis(panel, VARIANTS, "2016-02-29", "2015-06-30"),
        "2020 COVID (off before 2020-03)": first_block_into_crisis(panel, VARIANTS, "2020-03-31", "2019-10-31"),
    }

    # ---- Write findings ----
    lines = []
    lines.append("# HYG/LQD Credit-Spread Z-Score as a CPM Canary -- Findings\n")
    lines.append("MEASUREMENT ONLY. No production files edited. Engine fixed (positive-Faber + "
                 "EAA vol-adj rank + K=4 + min-var pair); only the CPM canary varies. BULL sleeve "
                 "fixed at production (HYG OR TIP). Blend = 60% CPM + 40% BULL.\n")
    lines.append("## Verification gate\n")
    lines.append(f"- variant-C0 vs production `run_cpm_backtest` max abs daily-return diff: `{diff:.2e}` (exact).")
    lines.append(f"- C0 CPM standalone (clean): Sharpe {mp['sharpe']:.3f} / CAGR {mp['cagr']*100:.2f}% / "
                 f"vol {mp['vol']*100:.2f}% / MaxDD {mp['max_drawdown']*100:.2f}%  (target 1.263 / 14.58% / 11.30% / -15.41%).")
    lines.append(f"- C0 60/40 blend (clean): Sharpe {mb['sharpe']:.3f} / CAGR {mb['cagr']*100:.2f}% / "
                 f"MaxDD {mb['max_drawdown']*100:.2f}%  (target 1.347 / 13.59% / -9.82%).")
    lines.append(f"- Reproduction: CPM_ok={repro_cpm}, blend_ok={repro_bl}.\n")
    lines.append("## Data caveat\n")
    lines.append("HYG live 2007-04 (VWEHX stitch pre); LQD live 2002-07 (VFICX IG corp bond fund stitch 1993-11+). "
                 "HYG/LQD ratio is CLEAN post-2007-04. Pre-2007 the ratio is a mutual-fund proxy "
                 "(VWEHX/VFICX 1999-2002, VWEHX/LQD 2002-2007). All Stress-window rows for Z1/Z2/Z3 "
                 "are PROXY-FLAGGED (marked Stress*). Clean-window (2008-05-30+) HYG/LQD is fully live.\n")
    lines.append("## CPM standalone metrics\n")
    lines.append("| Variant | Window | Raw Sharpe | Excess Sharpe | CAGR | Vol | MaxDD | Calmar | Turnover |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    lines.extend(rows_cpm)
    lines.append("\n## 60/40 CPM+BULL blend metrics\n")
    lines.append("| Variant | Window | Raw Sharpe | Excess Sharpe | CAGR | Vol | MaxDD | Calmar | Turnover |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    lines.extend(rows_bl)
    lines.append("\n*Stress rows for HYG/LQD variants (Z1/Z2/Z3) are proxy-flagged pre-2007.\n")
    lines.append("## Crisis sub-periods (stress panel)\n")
    lines.append("Cal-return col only meaningful for full calendar years (NaN for partial windows).\n")
    lines.append("| Variant | Crisis | CPM cal-ret | CPM Sharpe | CPM MaxDD | Blend Sharpe | Blend MaxDD |")
    lines.append("|---|---|---|---|---|---|---|")
    lines.extend(crisis_rows)
    lines.append("\n## Cohort / gating diagnostics (% months gated, forward 1m EW-risky return)\n")
    lines.append("Blocked = canary risk-off. bad-forward = blocked & fwd<0 (correct de-risk). "
                 "false-positive = blocked & fwd>=0 (gave up upside).\n")
    lines.append("| Variant | Window | %gated | n_block | blocked mean fwd | blocked %neg | "
                 "allowed mean fwd | bad-fwd | false-pos |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for name in VARIANTS:
        for scope, key in (("Clean", "clean"), ("Stress*", "stress")):
            d = diag[name][key]
            b, a = d["blocked"], d["allowed"]
            lines.append(f"| {name} | {scope} | {d['pct_blocked']:.1f}% | {d['n_blocked']} | "
                         f"{b['mean']*100 if pd.notna(b['mean']) else float('nan'):.2f}% | "
                         f"{b['pct_neg'] if pd.notna(b['pct_neg']) else float('nan'):.0f}% | "
                         f"{a['mean']*100 if pd.notna(a['mean']) else float('nan'):.2f}% | "
                         f"{d['bad_forward']} | {d['false_positive']} |")
    lines.append("\n## Earliness into credit crises (first risk-off month before crisis)\n")
    lines.append("Earlier (lower) month = flips defensive sooner. 'never' = stayed risk-on through window.\n")
    for crisis, res in early.items():
        lines.append(f"- **{crisis}**: " + ", ".join(f"{k}={v}" for k, v in res.items()))
    lines.append("")

    out_md.write_text("\n".join(lines))
    print(f"\nWrote {out_md}")


if __name__ == "__main__":
    main()
