"""Throwaway research (read-only analyst): is CPM's month-end EXECUTION CLIFF
GENERIC to monthly month-end TAA, or CPM-specific?

Question
--------
The memo reports CPM degrading as the SIGNAL/REBALANCE calendar shifts off true
month-end (cliff): EOM Sharpe ~1.21 -> EOM+1 ~1.01 -> EOM+2 ~0.97 -> EOM+3 ~0.91
(~-25%). The review framed this as a CPM crowding/fragility vulnerability. Test
whether two CANONICAL monthly month-end TAA strategies show the SAME cliff under
the IDENTICAL offset battery.

Strategies
----------
  CPM         : production sleeve (cpm_live.compute_target_weights).
  AAA-style   : memo's primary external comparator = canonical 10-asset AAA
                (cpm_benchmarks_proper.make_canonical_aaa_wf): top-half by 6m
                momentum, SLSQP min-variance weights, no canary.
  HAA-Simple  : TIP 13612U canary + SPY 13612U trend + best-of-safe{SHV,IEF}
                by 13612U (sleeve_vs_benchmark_2026_05_30.make_haa_simple_wf,
                safe_pool=[SHV,IEF]). Same config as the now-BULL sleeve.

Convention (APPLES-TO-APPLES with the published CPM cliff)
---------------------------------------------------------
Reuses the memo's cliff harness convention EXACTLY: cpm_execution_cliff.gen_sig_dates
+ close-to-close (cc) accounting, exec_lag=0 (signal at close of the offset day,
new basket applied from the next trading day's close-to-close = production T+0
MOC economics; this IS the convention behind the published EOM 1.2063 cliff
anchor). 10 bps/side. Generalized to accept any weight_fn so all three strategies
go through byte-identical timing/cost/window machinery.

OFFSET BATTERY: EOM, EOM+1, EOM+2, EOM+3 business days (rebalance-CALENDAR shift,
NOT a fill-convention change). Window: CLEAN 18y 2008-05-30 .. 2026-05-22.

Outputs: side-by-side Sharpe table (each strategy at EOM..EOM+3), absolute and %
degradation EOM->EOM+3, next to CPM. Verdict: generic vs CPM-specific.
"""
import json
import math
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from scipy.optimize import minimize
from cpm_live import (
    load_panel, compute_target_weights, perf_metrics, sig_13612U, best_safe,
    RISKY_UNIVERSE, SAFE_POOL, CANARY_ASSETS, DEFAULT_CASH, COST_BPS_PER_SIDE,
)
from cpm_execution_cliff import gen_sig_dates, sharpe_of

CLEAN_START = pd.Timestamp("2008-05-30")
EVAL_END = pd.Timestamp("2026-05-22")
EXT_START = pd.Timestamp("1999-03-10")
HAA_SAFE = ["SHV", "IEF"]
OFFSETS = [("EOM", ("eom", 0)), ("EOM+1", ("eom", 1)),
           ("EOM+2", ("eom", 2)), ("EOM+3", ("eom", 3))]

# ----- inlined weight builders (bit-identical to the cited source modules; copied
#       to avoid importing exec_lag_moo_validation, which references a now-removed
#       bull_spy_live._vol_gate_ok at module load) -----
# AAA-style: cpm_benchmarks_proper.make_canonical_aaa_wf (canonical 10-asset).
MACRO = Path(__file__).resolve().parent / "_macro_cache"
AAA_UNIVERSE = ["SPY", "EZU", "EWJ", "EEM", "IYR", "RWX", "IEF", "TLT", "DBC", "GLD"]
AAA_EXTRA = ["EWJ", "RWX", "EZU", "IYR"]
MINVAR_LOOKBACK = 504


def _minvar_weights(daily, sd, top):
    cov = daily.loc[:sd].tail(MINVAR_LOOKBACK)[top].cov() * 252
    n = len(top)
    def obj(w, C=cov.values):
        return float(np.dot(w, np.dot(C, w)))
    cons = ({"type": "eq", "fun": lambda w: np.sum(w) - 1.0},)
    bnds = tuple((0.0, 1.0) for _ in range(n))
    r = minimize(obj, np.ones(n) / n, method="SLSQP", bounds=bnds, constraints=cons)
    return {top[i]: float(r.x[i]) for i in range(n)} if r.success else {t: 1.0 / n for t in top}


def _mom_6m(p):
    p = p.dropna()
    if len(p) < 7:
        return np.nan
    return float(p.iloc[-1] / p.iloc[-7] - 1.0)


def make_canonical_aaa_wf(close, daily):
    uni = [t for t in AAA_UNIVERSE if t in close.columns]
    def wf(sd):
        monthly = close.loc[:sd].resample("ME").last()
        scores = {t: _mom_6m(monthly[t]) for t in uni if t in monthly.columns}
        scores = {t: s for t, s in scores.items() if pd.notna(s)}
        if len(scores) < 2:
            return {best_safe(monthly, sd, ["IEF", "SHV"]): 1.0}
        ranked = sorted(scores.items(), key=lambda x: -x[1])
        top_half = max(2, math.ceil(len(uni) / 2))
        top = [t for t, _ in ranked[:top_half]]
        return _minvar_weights(daily, sd, top)
    return wf


# HAA-Simple: sleeve_vs_benchmark_2026_05_30.make_haa_simple_wf (safe_pool=[SHV,IEF]).
def make_haa_simple_wf(close, asset="SPY", safe_pool=HAA_SAFE):
    def wf(sd):
        monthly = close.loc[:sd].resample("ME").last()
        safe = best_safe(monthly, sd, safe_pool)
        tipm = sig_13612U(monthly["TIP"]) if "TIP" in monthly.columns else float("nan")
        c_ok = pd.notna(tipm) and tipm > 0
        amom = sig_13612U(monthly[asset]) if asset in monthly.columns else float("nan")
        a_ok = pd.notna(amom) and amom > 0
        return {asset: 1.0} if (c_ok and a_ok) else {safe: 1.0}
    return wf


def cc_returns(close, daily_ret, start, end, rule, weight_fn, exec_lag=0,
               cost_bps=COST_BPS_PER_SIDE):
    """Generalized close-to-close sleeve returns with offset timing.

    IDENTICAL economics to cpm_execution_cliff.cpm_cc_returns, except the weight
    function is injected (so AAA / HAA-Simple / CPM share the harness)."""
    sigs = [s for s in gen_sig_dates(close, start, end, rule)
            if start - pd.DateOffset(days=45) <= s <= end]

    def apply_from(sd):
        fut = close.index[close.index > sd]
        return fut[exec_lag] if len(fut) > exec_lag else None

    hist, prev_w = [], {}
    for i, sd in enumerate(sigs):
        w = weight_fn(sd)
        af = apply_from(sd)
        if af is None:
            continue
        if i + 1 < len(sigs):
            naf = apply_from(sigs[i + 1])
            end_apply = naf if naf is not None else end
        else:
            end_apply = end
        hist.append({"af": af, "end": end_apply, "w": w})
        prev_w = w

    cols = sorted({a for h in hist for a in h["w"]} & set(daily_ret.columns))
    df_w = pd.DataFrame(0.0, index=close.index, columns=cols)
    for h in hist:
        mask = (close.index >= h["af"]) & (close.index < h["end"])
        for a, ww in h["w"].items():
            if a in df_w.columns:
                df_w.loc[mask, a] = ww
    ret = (df_w[cols] * daily_ret[cols]).sum(axis=1, min_count=1).fillna(0.0)

    for i, h in enumerate(hist):
        pw = hist[i - 1]["w"] if i > 0 else {}
        cw = h["w"]
        keys = set(cw) | set(pw)
        turnover = sum(abs(cw.get(k, 0.0) - pw.get(k, 0.0)) for k in keys)
        cost = turnover * cost_bps / 10000.0
        if h["af"] in ret.index:
            ret.loc[h["af"]] -= cost

    sel = (ret.index >= start) & (ret.index <= end)
    return ret.loc[sel]


def metr(daily, cash):
    m = perf_metrics(daily, cash)
    return {"sharpe": m.get("sharpe"), "cagr": m.get("cagr"),
            "maxdd": m.get("max_drawdown"), "calmar": m.get("calmar"),
            "n_days": int(len(daily))}


def main():
    panel = load_panel(start=EXT_START, end=EVAL_END)
    end = min(EVAL_END, panel.index[-1])
    cash = panel["SHV"].ffill().pct_change().dropna()

    # merge the 4 extra AAA tickers (EWJ/RWX/EZU/IYR) from _macro_cache
    for t in AAA_EXTRA:
        d = pd.read_csv(MACRO / f"{t}_ohlc.csv", parse_dates=["Date"], index_col="Date")
        panel = panel.join(d[["Close"]].rename(columns={"Close": t}), how="left")
    panel = panel.sort_index()
    panel = panel[panel.index <= end]

    # --- CPM sleeve panel/close ---
    cpm_cols = sorted(set(RISKY_UNIVERSE + SAFE_POOL + CANARY_ASSETS + [DEFAULT_CASH]) & set(panel.columns))
    cpm_close = panel[cpm_cols]
    cpm_daily = cpm_close.ffill().pct_change()
    cpm_wf = lambda sd: compute_target_weights(cpm_close, sd)[0]

    # --- AAA-style panel/close (canonical 10-asset + SHV/IEF safe) ---
    aaa_cols = sorted(set([t for t in AAA_UNIVERSE if t in panel.columns] + ["SHV", "IEF"]))
    aaa_close = panel[aaa_cols]
    aaa_daily = aaa_close.ffill().pct_change()
    aaa_wf = make_canonical_aaa_wf(aaa_close, aaa_daily)
    # AAA start gated by RWX inception (2006-12) + 12m momentum warmup; clean OK.
    rwx_fv = panel["RWX"].first_valid_index() if "RWX" in panel.columns else None
    aaa_min_start = max(CLEAN_START, (rwx_fv + pd.DateOffset(months=13)) if rwx_fv is not None else CLEAN_START)

    # --- HAA-Simple panel/close (SPY + SHV/IEF safe + TIP canary) ---
    haa_cols = sorted(set(["SPY"] + HAA_SAFE + ["TIP"]) & set(panel.columns))
    haa_close = panel[haa_cols]
    haa_daily = haa_close.ffill().pct_change()
    haa_wf = make_haa_simple_wf(haa_close, "SPY", HAA_SAFE)

    strategies = {
        "CPM":        (cpm_close, cpm_daily, cpm_wf, CLEAN_START),
        "AAA-style":  (aaa_close, aaa_daily, aaa_wf, aaa_min_start),
        "HAA-Simple": (haa_close, haa_daily, haa_wf, CLEAN_START),
    }

    print(f"Panel {panel.index[0].date()} -> {panel.index[-1].date()} ({len(panel)} rows)")
    print(f"RWX first valid: {rwx_fv.date() if rwx_fv is not None else None}; AAA clean start: {aaa_min_start.date()}")
    print(f"Convention: cc / exec_lag=0 (memo cliff anchor), {COST_BPS_PER_SIDE} bps/side")
    print(f"Window: CLEAN {CLEAN_START.date()} .. {end.date()}\n")

    results = {"meta": {
        "panel_start": str(panel.index[0].date()),
        "panel_end": str(end.date()),
        "clean_start": str(CLEAN_START.date()),
        "aaa_clean_start": str(aaa_min_start.date()),
        "rwx_first_valid": str(rwx_fv.date()) if rwx_fv is not None else None,
        "cost_bps_per_side": COST_BPS_PER_SIDE,
        "convention": "close-to-close (cc), exec_lag=0; matches memo cliff anchor EOM 1.2063",
        "offsets": [o[0] for o in OFFSETS],
        "haa_safe": HAA_SAFE,
        "aaa_universe": AAA_UNIVERSE,
    }, "sharpe_by_offset": {}, "full_metrics": {}}

    for name, (close, daily, wf, win_start) in strategies.items():
        results["sharpe_by_offset"][name] = {}
        results["full_metrics"][name] = {}
        for olabel, rule in OFFSETS:
            r = cc_returns(close, daily, win_start, end, rule, wf)
            m = metr(r, cash)
            results["sharpe_by_offset"][name][olabel] = m["sharpe"]
            results["full_metrics"][name][olabel] = m

    # ---- baseline gate: print EOM baselines ----
    print("=== BASELINE GATE (true-EOM Sharpe; reproduce before cliff) ===")
    print(f"  CPM        EOM Sharpe = {results['sharpe_by_offset']['CPM']['EOM']:.4f}  (expect ~1.206 cc)")
    print(f"  AAA-style  EOM Sharpe = {results['sharpe_by_offset']['AAA-style']['EOM']:.4f}")
    print(f"  HAA-Simple EOM Sharpe = {results['sharpe_by_offset']['HAA-Simple']['EOM']:.4f}\n")

    # ---- side-by-side cliff table ----
    print("=" * 78)
    print("EXECUTION-CLIFF PEER SANITY: Sharpe by signal/rebalance offset (CLEAN 18y)")
    print("=" * 78)
    hdr = f"{'strategy':<13}{'EOM':>9}{'EOM+1':>9}{'EOM+2':>9}{'EOM+3':>9}{'abs deg':>10}{'% deg':>9}"
    print(hdr)
    print("-" * len(hdr))
    deg = {}
    for name in ["CPM", "AAA-style", "HAA-Simple"]:
        s = results["sharpe_by_offset"][name]
        e0, e3 = s["EOM"], s["EOM+3"]
        abs_d = e3 - e0
        pct_d = (abs_d / e0 * 100.0) if e0 else float("nan")
        deg[name] = {"eom": e0, "eom3": e3, "abs": abs_d, "pct": pct_d}
        print(f"{name:<13}{s['EOM']:>9.4f}{s['EOM+1']:>9.4f}{s['EOM+2']:>9.4f}"
              f"{s['EOM+3']:>9.4f}{abs_d:>+10.4f}{pct_d:>+8.1f}%")
    results["degradation_eom_to_eom3"] = deg

    print("\nMemo-published CPM cliff (reference): EOM 1.2063 / EOM+1 1.01 / EOM+2 0.97 / EOM+3 0.91 (~-25%)")

    out = ROOT / "research" / "cpm_execution_cliff_peer_sanity_2026_06_01.json"
    out.write_text(json.dumps(results, indent=2, default=lambda x: None if x is None else float(x)))
    print(f"\nSaved {out}")


if __name__ == "__main__":
    main()
