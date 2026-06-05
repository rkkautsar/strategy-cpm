"""ANALYST research-only (no prod/memo edits; no commit).

ITEM 2: peer offset-cliff under the CANONICAL mooex convention.

Recompute the signal/rebalance offset (EOM, EOM+1, EOM+2, EOM+3) Sharpe for CPM
AND for the AAA and HAA benchmarks, under mooex (T+1 MOO exact), both-252, 10
bps/side, CLEAN 2008-05-30..2026-05-22. This is the SAME convention as the
canonical CPM anchor (EOM CPM = 1.2557), so the table is internally consistent.

NOTE on the memo's stated CPM cliff (1.2557 -> 0.9743 -> 0.9628 -> 0.8714): the
EOM value 1.2557 is the canonical mooex anchor, but the offsets 0.9743/0.9628/
0.8714 came from the both-252 rebaseline run whose own EOM was 1.1658 (a different
weighting config). This recompute produces a single internally consistent set.

A separate already-published peer cliff exists under cc/exec_lag=0 (T+0 MOC):
research/cpm_execution_cliff_peer_sanity_2026_06_01.{py,json} (CPM 1.2063 ->
1.0127 -> 0.9747 -> 0.9090; AAA 0.9961 ->...; HAA 0.9839 ->...). We add the mooex
version here for apples-to-apples with the memo's mooex anchor.

AAA = canonical 10-asset Adaptive Asset Allocation (Butler-Philbrick 2012 style):
  top-half by 6m momentum, SLSQP min-variance weights, no canary. Universe
  [SPY,EZU,EWJ,EEM,IYR,RWX,IEF,TLT,DBC,GLD]; SHV/IEF fallback. (4 extra tickers
  EWJ/RWX/EZU/IYR from research/_macro_cache; those lack open-cache OHLC so mooex
  falls back to close-to-close for them -- flagged.)
HAA = Keller-Keuning Hybrid simple: TIP 13612U canary + SPY 13612U trend +
  best-of-safe{SHV,IEF} by 13612U.
"""
import sys
import json
import math
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.optimize import minimize

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import cpm_live
from cpm_live import (
    load_panel, compute_target_weights, perf_metrics, sig_13612U, best_safe,
    RISKY_UNIVERSE, SAFE_POOL, CANARY_ASSETS, DEFAULT_CASH, COST_BPS_PER_SIDE,
)
from cpm_execution_cliff import gen_sig_dates
from research import exec_lag_moo_validation_2026_05_30 as eng

CLEAN = pd.Timestamp("2008-05-30")
EXT = pd.Timestamp("1999-03-10")
END = pd.Timestamp("2026-05-22")
MACRO = Path(__file__).resolve().parent / "_macro_cache"
AAA_UNIVERSE = ["SPY", "EZU", "EWJ", "EEM", "IYR", "RWX", "IEF", "TLT", "DBC", "GLD"]
AAA_EXTRA = ["EWJ", "RWX", "EZU", "IYR"]
HAA_SAFE = ["SHV", "IEF"]
MINVAR_LOOKBACK = 504
OFFSETS = [("EOM", ("eom", 0)), ("EOM+1", ("eom", 1)), ("EOM+2", ("eom", 2)), ("EOM+3", ("eom", 3))]


def mooex_returns_for_sigs(close, daily_ret, weight_fn, sigs, start, end,
                           cost_bps, intraday_ret, overnight_ret):
    """mooex (T+1 MOO exact) segment returns for an EXPLICIT list of signal dates.

    Faithful to research.exec_lag_moo_validation_2026_05_30._segment_returns_conv
    mooex branch (overnight close[T]->open[af] on OLD basket, then intraday
    open[af]->close[af] on NEW basket, compounded; cc fallback when opens absent);
    only the signal-date generator differs (offset calendar instead of EOM)."""
    sigs = [s for s in sigs if start - pd.DateOffset(days=45) <= s <= end]

    def apply_from(sd):
        fut = close.index[close.index > sd]
        return fut[0] if len(fut) > 0 else None

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
        hist.append({"apply_from": af, "end_apply": end_apply, "weights": w, "prev_weights": prev_w})
        prev_w = w

    all_assets = sorted({a for h in hist for a in h["weights"]})
    cols = [a for a in all_assets if a in daily_ret.columns]
    df_w = pd.DataFrame(0.0, index=close.index, columns=cols)
    for h in hist:
        mask = (close.index >= h["apply_from"]) & (close.index < h["end_apply"])
        for a, ww in h["weights"].items():
            if a in df_w.columns:
                df_w.loc[mask, a] = ww
    ret = (df_w[cols] * daily_ret[cols]).sum(axis=1, min_count=1).fillna(0.0)

    n_real, n_fb = 0, 0
    for h in hist:
        af = h["apply_from"]
        if af not in ret.index:
            continue
        ok = True

        def cc(a):
            return daily_ret.at[af, a] if a in daily_ret.columns and pd.notna(daily_ret.at[af, a]) else 0.0

        def intra(a):
            nonlocal ok
            if (intraday_ret is not None and a in intraday_ret.columns and af in intraday_ret.index
                    and pd.notna(intraday_ret.at[af, a])):
                return intraday_ret.at[af, a]
            ok = False
            return None

        def on(a):
            nonlocal ok
            if (overnight_ret is not None and a in overnight_ret.columns and af in overnight_ret.index
                    and pd.notna(overnight_ret.at[af, a])):
                return overnight_ret.at[af, a]
            ok = False
            return None

        on_c = 0.0
        for a, ww in h["prev_weights"].items():
            if a not in cols:
                continue
            ov = on(a)
            on_c += ww * (ov if ov is not None else 0.0)
        id_c = 0.0
        for a, ww in h["weights"].items():
            if a not in cols:
                continue
            iv = intra(a)
            id_c += ww * (iv if iv is not None else cc(a))
        ret.loc[af] = (1.0 + on_c) * (1.0 + id_c) - 1.0
        n_real += int(ok)
        n_fb += int(not ok)

    for i, h in enumerate(hist):
        pw = hist[i - 1]["weights"] if i > 0 else {}
        cw = h["weights"]
        keys = set(cw) | set(pw)
        turnover = sum(abs(cw.get(k, 0.0) - pw.get(k, 0.0)) for k in keys)
        cost = turnover * cost_bps / 10000.0
        if h["apply_from"] in ret.index:
            ret.loc[h["apply_from"]] -= cost

    return ret.loc[(ret.index >= start) & (ret.index <= end)], (n_real, n_fb)


# ---- AAA builders ----
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
    return float(p.iloc[-1] / p.iloc[-7] - 1.0) if len(p) >= 7 else np.nan


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


def met(daily, cash):
    m = perf_metrics(daily, cash)
    return {"sharpe": m.get("sharpe"), "cagr": m.get("cagr"),
            "maxdd": m.get("max_drawdown"), "calmar": m.get("calmar")}


def main():
    panel = load_panel(start=EXT, end=END, live=False)
    panel = panel.loc[panel.index <= END]
    cash = panel["SHV"].ffill().pct_change().dropna()
    # merge AAA extra tickers
    for t in AAA_EXTRA:
        d = pd.read_csv(MACRO / f"{t}_ohlc.csv", parse_dates=["Date"], index_col="Date")
        panel = panel.join(d[["Close"]].rename(columns={"Close": t}), how="left")
    panel = panel.sort_index()
    panel = panel.loc[panel.index <= END]

    open_df, close_df = eng.load_open_close()
    intraday = (close_df / open_df - 1.0).reindex(panel.index)
    overnight = (open_df / close_df.shift(1) - 1.0).reindex(panel.index)

    # CPM
    cpm_cols = sorted(set(RISKY_UNIVERSE + SAFE_POOL + CANARY_ASSETS + [DEFAULT_CASH]) & set(panel.columns))
    cpm_close = panel[cpm_cols]
    cpm_daily = cpm_close.ffill().pct_change()
    cpm_wf = lambda sd: compute_target_weights(cpm_close, sd)[0]

    # AAA (gate start by RWX inception + warmup)
    aaa_cols = sorted(set([t for t in AAA_UNIVERSE if t in panel.columns] + ["SHV", "IEF"]))
    aaa_close = panel[aaa_cols]
    aaa_daily = aaa_close.ffill().pct_change()
    aaa_wf = make_canonical_aaa_wf(aaa_close, aaa_daily)
    rwx_fv = panel["RWX"].first_valid_index() if "RWX" in panel.columns else None
    aaa_start = max(CLEAN, (rwx_fv + pd.DateOffset(months=13)) if rwx_fv is not None else CLEAN)

    # HAA
    haa_cols = sorted(set(["SPY"] + HAA_SAFE + ["TIP"]) & set(panel.columns))
    haa_close = panel[haa_cols]
    haa_daily = haa_close.ffill().pct_change()
    haa_wf = make_haa_simple_wf(haa_close, "SPY", HAA_SAFE)

    strategies = {
        "CPM": (cpm_close, cpm_daily, cpm_wf, CLEAN, COST_BPS_PER_SIDE),
        "AAA": (aaa_close, aaa_daily, aaa_wf, aaa_start, 10.0),
        "HAA": (haa_close, haa_daily, haa_wf, CLEAN, 10.0),
    }

    results = {"meta": {
        "convention": "mooex (T+1 MOO exact)",
        "window_clean": f"{CLEAN.date()}..{END.date()}",
        "aaa_start": str(aaa_start.date()),
        "rwx_first_valid": str(rwx_fv.date()) if rwx_fv is not None else None,
        "cost_bps": 10, "both252": cpm_live.CORR_LOOKBACK_DAYS == 252,
        "offsets": [o[0] for o in OFFSETS],
        "aaa_universe": AAA_UNIVERSE, "aaa_extra_no_opens": AAA_EXTRA,
        "note": ("AAA extra tickers EWJ/RWX/EZU/IYR have no open-cache OHLC; mooex "
                 "falls back to close-to-close for those legs on rebalance days. "
                 "n_real/n_fallback rebalance-day coverage reported per strategy."),
    }, "sharpe_by_offset": {}, "full": {}, "coverage": {}}

    for name, (close, daily, wf, wstart, cb) in strategies.items():
        results["sharpe_by_offset"][name] = {}
        results["full"][name] = {}
        results["coverage"][name] = {}
        for olabel, rule in OFFSETS:
            sigs = gen_sig_dates(close, wstart, END, rule)
            r, fb = mooex_returns_for_sigs(close, daily, wf, sigs, wstart, END, cb, intraday, overnight)
            m = met(r, cash)
            results["sharpe_by_offset"][name][olabel] = m["sharpe"]
            results["full"][name][olabel] = m
            results["coverage"][name][olabel] = {"n_real": fb[0], "n_fallback": fb[1]}
            print(f"{name:<5}{olabel:<6} Sharpe={m['sharpe']:.4f} Calmar={m['calmar']:.4f} "
                  f"MaxDD={m['maxdd']*100:.2f}% (real={fb[0]} fb={fb[1]})")
        print()

    # degradation
    deg = {}
    for name in strategies:
        s = results["sharpe_by_offset"][name]
        e0, e3 = s["EOM"], s["EOM+3"]
        deg[name] = {"eom": e0, "eom3": e3, "abs": e3 - e0, "pct": (e3 - e0) / e0 * 100 if e0 else None}
    results["degradation"] = deg

    print("=== mooex offset cliff (CLEAN) Sharpe ===")
    print(f"{'strat':<6}{'EOM':>9}{'EOM+1':>9}{'EOM+2':>9}{'EOM+3':>9}{'absdeg':>9}{'%deg':>8}")
    for name in strategies:
        s = results["sharpe_by_offset"][name]
        d = deg[name]
        print(f"{name:<6}{s['EOM']:>9.4f}{s['EOM+1']:>9.4f}{s['EOM+2']:>9.4f}{s['EOM+3']:>9.4f}"
              f"{d['abs']:>+9.4f}{d['pct']:>+7.1f}%")

    out = ROOT / "research" / "cpm_research_grade_offset_cliff.json"
    out.write_text(json.dumps(results, indent=2, default=lambda x: None if (x is None or (isinstance(x, float) and pd.isna(x))) else float(x)))
    print(f"\nWROTE {out}")


if __name__ == "__main__":
    main()
