"""Throwaway research: each sleeve vs its rightful TAA benchmark.

  CPM-solo  vs  AAA + TIP canary   (bench_aaa_tip / B2)
  BULL-solo vs  HAA-simple SPY     (bench_haa_simple / B3)

Identical execution to the strategy numbers: realistic T+1 MOO (mooex), post-cost
10 bps/side, slow vol gate (RV_60d<RV_252d = production default _vol_gate_ok).
Both sleeve and benchmark run through the SAME _segment_returns_conv harness from
exec_lag_moo_validation_2026_05_30.py so cost/window/execution are byte-identical.

Windows:
  CLEAN 18y : 2008-05-30 .. end
  EXT   27y : 1999-03-10 .. end
"""
import sys, math, json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from scipy.optimize import minimize
import bull_spy_live
from cpm_live import (
    load_panel, compute_target_weights, perf_metrics, sig_13612U, best_safe,
    RISKY_UNIVERSE, SAFE_POOL, CANARY_ASSETS, DEFAULT_CASH, COST_BPS_PER_SIDE,
)
from bull_spy_live import BULL_TICKER, CASH_TICKER, compute_bull_spy_weights
import exec_lag_moo_validation_2026_05_30 as H

import yfinance as yf

# Benchmark universes
# CPM benchmark: repo-canonical AAA+TIP (build_dashboard.py:352), SHV/IEF safe.
BENCH_AAA_UNIVERSE = ["SPY", "EFA", "EEM", "VNQ", "GLD", "TLT", "DBC"]
BENCH_SAFE = ["SHV", "IEF"]
# BULL benchmark: user-specified HAA-Simple SPY with {BIL, AGG} best-of-safe.
HAA_SAFE = ["BIL", "AGG"]
DATA_DIR = ROOT / "data"
CONV = "mooex"  # realistic T+1 MOO exact


def stitch_bil(panel):
    """Repo standard (safe_haven_expansion.py:66): BIL live returns post
    2007-05-30, SHV proxy returns before. Returns price series (base 100)."""
    df = yf.download("BIL", start="1995-01-01", progress=False, auto_adjust=True)
    if isinstance(df.columns, pd.MultiIndex):
        tc = df["Close"]["BIL"] if "BIL" in df["Close"].columns else df["Close"].iloc[:, 0]
    else:
        tc = df["Close"] if "Close" in df.columns else df.iloc[:, 0]
    tr = tc.pct_change().reindex(panel.index)
    pr = panel["SHV"].ffill().pct_change().reindex(panel.index)
    inc = pd.Timestamp("2007-05-30")
    out = pd.Series(index=panel.index, dtype=float)
    out.loc[out.index < inc] = pr.loc[out.index < inc]
    out.loc[out.index >= inc] = tr.loc[out.index >= inc]
    return (1.0 + out.fillna(0.0)).cumprod() * 100.0


def stitch_agg(panel):
    """Repo standard AGG stitch: data/agg_stitched_daily.csv (from 1986-12)."""
    s = pd.read_csv(DATA_DIR / "agg_stitched_daily.csv", parse_dates=[0], index_col=0).iloc[:, 0]
    return s.reindex(panel.index).ffill()


# ----- benchmark weight functions (weight_fn(sig_d) -> dict) -----
def make_aaa_tip_wf(close, daily):
    def wf(sd):
        monthly = close.loc[:sd].resample("ME").last()
        safe = best_safe(monthly, sd, BENCH_SAFE)
        tipm = sig_13612U(monthly["TIP"]) if "TIP" in monthly.columns else float("nan")
        if not (pd.notna(tipm) and tipm > 0):
            return {safe: 1.0}
        scores = {t: sig_13612U(monthly[t]) for t in BENCH_AAA_UNIVERSE if t in monthly.columns}
        scores = {t: s for t, s in scores.items() if pd.notna(s)}
        ranked = sorted(scores.items(), key=lambda x: -x[1])
        top_half = max(2, math.ceil(len(BENCH_AAA_UNIVERSE) / 2))
        top = [t for t, s in ranked[:top_half] if s > 0]
        if len(top) == 0:
            return {safe: 1.0}
        if len(top) == 1:
            return {top[0]: 0.5, safe: 0.5}
        cov = daily.loc[:sd].tail(504)[top].cov() * 252
        n = len(top)
        def obj(w, C=cov.values):
            return float(np.dot(w, np.dot(C, w)))
        cons = ({"type": "eq", "fun": lambda w: np.sum(w) - 1.0},)
        bnds = tuple((0.0, 1.0) for _ in range(n))
        r = minimize(obj, np.ones(n)/n, method="SLSQP", bounds=bnds, constraints=cons)
        return {top[i]: float(r.x[i]) for i in range(n)} if r.success else {t: 1.0/n for t in top}
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


def run_bench(panel, intraday, overnight, start, end, wf, universe, safe_pool=BENCH_SAFE):
    cols = sorted(set(universe + safe_pool + ["TIP"]) & set(panel.columns))
    close = panel[cols]
    daily_ret = close.ffill().pct_change()
    return H._segment_returns_conv(close, daily_ret, wf, start, end, CONV,
                                   COST_BPS_PER_SIDE, intraday, overnight)


def met(daily, cash):
    m = perf_metrics(daily, cash)
    return {"sharpe": m.get("sharpe"), "cagr": m.get("cagr"),
            "maxdd": m.get("max_drawdown"), "calmar": m.get("calmar"), "vol": m.get("vol")}


def active_stats(sleeve, bench, cash):
    common = sleeve.index.intersection(bench.index)
    s = sleeve.reindex(common).fillna(0.0)
    b = bench.reindex(common).fillna(0.0)
    ms, mb = met(s, cash), met(b, cash)
    diff = s - b
    te = float(diff.std() * np.sqrt(252))
    ir = float((diff.mean() * 252) / te) if te > 1e-12 else float("nan")
    corr = float(np.corrcoef(s.values, b.values)[0, 1])
    return {
        "sleeve": ms, "bench": mb,
        "d_cagr": ms["cagr"] - mb["cagr"],
        "d_calmar": ms["calmar"] - mb["calmar"],
        "d_sharpe": ms["sharpe"] - mb["sharpe"],
        "d_maxdd": ms["maxdd"] - mb["maxdd"],
        "corr": corr, "te": te, "ir": ir,
        "n": len(common),
    }


def window_total_return(daily, ws, we):
    sub = daily.loc[(daily.index >= ws) & (daily.index <= we)]
    if len(sub) < 2:
        return float("nan")
    return float((1.0 + sub).prod() - 1.0)


def main():
    end = pd.Timestamp("2026-05-22")
    ext_start = pd.Timestamp("1999-03-10")
    clean_start = pd.Timestamp("2008-05-30")

    panel = load_panel(start=ext_start, end=end)
    end = min(end, panel.index[-1])
    cash = panel["SHV"].ffill().pct_change().dropna()

    # HAA-Simple defensive pool {BIL, AGG} via repo standard stitches.
    panel["BIL"] = stitch_bil(panel)
    panel["AGG"] = stitch_agg(panel)
    print(f"BIL stitch (SHV<2007-05-30): {panel['BIL'].dropna().index[0].date()} -> {panel['BIL'].dropna().index[-1].date()}")
    print(f"AGG stitch (agg_stitched_daily.csv): {panel['AGG'].dropna().index[0].date()} -> {panel['AGG'].dropna().index[-1].date()}")

    open_df, close_yf = H.load_open_close()
    intraday = (close_yf / open_df - 1.0).reindex(panel.index)
    overnight = (open_df / close_yf.shift(1) - 1.0).reindex(panel.index)

    print(f"Panel {panel.index[0].date()} -> {panel.index[-1].date()} ({len(panel)} rows)")
    print(f"Convention={CONV}  cost={COST_BPS_PER_SIDE}bps/side  gate=production RV_60d<RV_252d\n")

    # --- sleeves over full ext window (slice per sub-window) ---
    cpm, _ = H.cpm_sleeve_conv(panel, intraday, overnight, ext_start, end, CONV)
    # BULL uses production default _vol_gate_ok (slow RV_60d). Pass it explicitly.
    bull, _ = H.bull_sleeve_conv(panel, intraday, overnight, ext_start, end, CONV,
                                 bull_spy_live._vol_gate_ok)

    # --- benchmarks ---
    aaa_cols = sorted(set(BENCH_AAA_UNIVERSE + BENCH_SAFE + ["TIP"]) & set(panel.columns))
    aaa_close = panel[aaa_cols]
    aaa_daily = aaa_close.ffill().pct_change()
    aaa_wf = make_aaa_tip_wf(aaa_close, aaa_daily)
    aaa, _ = run_bench(panel, intraday, overnight, ext_start, end, aaa_wf, BENCH_AAA_UNIVERSE)

    haa_cols = sorted(set(["SPY"] + HAA_SAFE + ["TIP"]) & set(panel.columns))
    haa_close = panel[haa_cols]
    haa_wf = make_haa_simple_wf(haa_close, "SPY", HAA_SAFE)
    haa, _ = run_bench(panel, intraday, overnight, ext_start, end, haa_wf, ["SPY"], HAA_SAFE)

    windows = {
        "CLEAN_18y": (clean_start, end),
        "EXT_27y": (ext_start, end),
    }

    # --- ANCHOR CHECK ---
    print("=== ANCHOR CHECK (CLEAN 18y, mooex, slow gate) ===")
    cpm_c = cpm.loc[clean_start:end]
    bull_c = bull.loc[clean_start:end]
    print(f"  CPM-solo  Sharpe={met(cpm_c, cash)['sharpe']:.3f}  (expect ~1.24)")
    print(f"  BULL-solo Sharpe={met(bull_c, cash)['sharpe']:.3f}  (expect ~1.08)\n")

    results = {}
    for wname, (ws, we) in windows.items():
        cpm_w = cpm.loc[(cpm.index >= ws) & (cpm.index <= we)]
        bull_w = bull.loc[(bull.index >= ws) & (bull.index <= we)]
        aaa_w = aaa.loc[(aaa.index >= ws) & (aaa.index <= we)]
        haa_w = haa.loc[(haa.index >= ws) & (haa.index <= we)]
        results[wname] = {
            "CPM_vs_AAA": active_stats(cpm_w, aaa_w, cash),
            "BULL_vs_HAA": active_stats(bull_w, haa_w, cash),
        }

    # --- print tables ---
    def fmt_block(title, st):
        sl, bn = st["sleeve"], st["bench"]
        print(title)
        print(f"  {'':<10}{'Sharpe':>8}{'CAGR':>9}{'Vol':>8}{'MaxDD':>9}{'Calmar':>8}")
        print(f"  {'sleeve':<10}{sl['sharpe']:>8.3f}{sl['cagr']*100:>8.2f}%{sl['vol']*100:>7.2f}%{sl['maxdd']*100:>8.2f}%{sl['calmar']:>8.3f}")
        print(f"  {'bench':<10}{bn['sharpe']:>8.3f}{bn['cagr']*100:>8.2f}%{bn['vol']*100:>7.2f}%{bn['maxdd']*100:>8.2f}%{bn['calmar']:>8.3f}")
        print(f"  active: dCAGR={st['d_cagr']*100:+.2f}pp  dCalmar={st['d_calmar']:+.3f}  "
              f"dSharpe={st['d_sharpe']:+.3f}  dMaxDD={st['d_maxdd']*100:+.2f}pp")
        print(f"  corr={st['corr']:.3f}  TE={st['te']*100:.2f}%  IR={st['ir']:+.3f}  n={st['n']}\n")

    for wname in windows:
        print("=" * 70)
        print(f"WINDOW {wname}")
        print("=" * 70)
        fmt_block("CPM-solo vs AAA+TIP:", results[wname]["CPM_vs_AAA"])
        fmt_block("BULL-solo vs HAA-simple SPY:", results[wname]["BULL_vs_HAA"])

    # --- crisis windows ---
    crises = {
        "DotCom_2000_2002": ("2000-03-01", "2002-10-31"),
        "GFC_2008": ("2007-10-01", "2009-03-31"),
        "COVID_2020": ("2020-02-19", "2020-04-30"),
        "Bear_2022": ("2022-01-01", "2022-12-31"),
    }
    print("=" * 70)
    print("CRISIS WINDOWS (total return, sleeve vs benchmark)")
    print("=" * 70)
    print(f"{'window':<20}{'CPM':>9}{'AAA+TIP':>10}{'BULL':>9}{'HAA-S':>9}")
    crisis_out = {}
    for cname, (cs, ce) in crises.items():
        cs, ce = pd.Timestamp(cs), pd.Timestamp(ce)
        r_cpm = window_total_return(cpm, cs, ce)
        r_aaa = window_total_return(aaa, cs, ce)
        r_bull = window_total_return(bull, cs, ce)
        r_haa = window_total_return(haa, cs, ce)
        crisis_out[cname] = {"cpm": r_cpm, "aaa": r_aaa, "bull": r_bull, "haa": r_haa}
        def p(x): return f"{x*100:+.1f}%" if pd.notna(x) else "   n/a"
        print(f"{cname:<20}{p(r_cpm):>9}{p(r_aaa):>10}{p(r_bull):>9}{p(r_haa):>9}")

    out = {"results": results, "crisis": crisis_out,
           "anchor": {"cpm_clean_sharpe": met(cpm_c, cash)["sharpe"],
                      "bull_clean_sharpe": met(bull_c, cash)["sharpe"]}}
    Path(__file__).with_suffix(".json").write_text(json.dumps(out, indent=2, default=float))
    print("\nDONE -> json written")


if __name__ == "__main__":
    main()
