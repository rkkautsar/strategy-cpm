"""Throwaway research: WHEN does the 50/50 min-var PAIR beat continuous min-var?

Aggregate already known: continuous min-var beats the 50/50 pair on
Sharpe/Calmar/MaxDD in both windows. This script tests time-varyingly WHERE/WHEN
(if ever) the pair wins, with the extended 27y window in scope.

Reuses research/pair_vs_continuous_minvar.py (same two weighting schemes,
U=R=C=1, cov lookback 504d, mooex T+1 MOO exact, 10 bps/side). The ONLY toggle
is the weighting step (P=1 pair, P=0 continuous).

Outputs (all written to research/pair_when_wins.json):
  1. ROLLING DIFFERENCE: rolling 12m & 36m Sharpe/Calmar/MaxDD for both schemes,
     evaluated at each month-end; difference (pair minus continuous) series;
     win fractions; outperformance date stretches + persistence.
  2. PER-REGIME: pair vs continuous Sharpe/CAGR/MaxDD for dot-com, GFC, COVID,
     2022, plus a few extra stress windows.
  3. WORST-EPISODE / drawdown attribution: largest DD episodes per scheme; in
     episodes where the pair outperforms, diagnose continuous concentration
     (max weight into a single asset before it crashed) vs pair 50% cap.
  4. Verdict feeds research/pair_when_wins_findings.md (written by hand).

No production files touched; no commit.
"""
import sys, json
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

from cpm_live import load_panel, perf_metrics, COST_BPS_PER_SIDE, CORR_LOOKBACK_DAYS
import exec_lag_moo_validation_2026_05_30 as H
from sleeve_vs_benchmark_2026_05_30 import stitch_bil, stitch_agg
import pair_vs_continuous_minvar as PV

CONV = "mooex"
HEAD_BPS = 10


def month_ends(idx, start, end):
    me = (pd.DataFrame({"x": 1}, index=idx).groupby(pd.Grouper(freq="ME")).tail(1)).index
    return me[(me >= start) & (me <= end)].tolist()


def window_metrics(daily_slice, cash):
    """Sharpe/Calmar/MaxDD/CAGR over a return slice."""
    if len(daily_slice) < 20:
        return None
    m = perf_metrics(daily_slice, cash)
    return {"sharpe": m.get("sharpe"), "calmar": m.get("calmar"),
            "maxdd": m.get("max_drawdown"), "cagr": m.get("cagr")}


def rolling_diff(ret_pair, ret_cont, cash, anchors, win_days, label):
    """Step over month-ends; at each, compute trailing-win metrics for both
    schemes; return per-date metrics + difference + win fractions."""
    idx = ret_pair.index
    me = month_ends(idx, anchors[0], anchors[1])
    rows = []
    for d in me:
        lo = d - pd.Timedelta(days=win_days)
        sp = ret_pair.loc[(ret_pair.index > lo) & (ret_pair.index <= d)]
        sc = ret_cont.loc[(ret_cont.index > lo) & (ret_cont.index <= d)]
        mp = window_metrics(sp, cash)
        mc = window_metrics(sc, cash)
        if mp is None or mc is None:
            continue
        rows.append({"date": str(d.date()),
                     "pair": mp, "cont": mc,
                     "d_sharpe": mp["sharpe"] - mc["sharpe"],
                     "d_calmar": (mp["calmar"] - mc["calmar"])
                                 if (mp["calmar"] is not None and mc["calmar"] is not None
                                     and np.isfinite(mp["calmar"]) and np.isfinite(mc["calmar"]))
                                 else None,
                     # rolling-MaxDD: pair wins = shallower (less negative) DD
                     "d_maxdd": mp["maxdd"] - mc["maxdd"]})
    n = len(rows)
    sh = [r["d_sharpe"] for r in rows if r["d_sharpe"] is not None and np.isfinite(r["d_sharpe"])]
    ca = [r["d_calmar"] for r in rows if r["d_calmar"] is not None and np.isfinite(r["d_calmar"])]
    dd = [r["d_maxdd"] for r in rows if r["d_maxdd"] is not None and np.isfinite(r["d_maxdd"])]
    win = {
        "n_windows": n,
        "sharpe_win_frac": float(np.mean([x > 0 for x in sh])) if sh else None,
        "calmar_win_frac": float(np.mean([x > 0 for x in ca])) if ca else None,
        "maxdd_win_frac": float(np.mean([x > 0 for x in dd])) if dd else None,  # pair shallower
        "sharpe_diff_mean": float(np.mean(sh)) if sh else None,
        "sharpe_diff_median": float(np.median(sh)) if sh else None,
        "sharpe_diff_p10": float(np.percentile(sh, 10)) if sh else None,
        "sharpe_diff_p90": float(np.percentile(sh, 90)) if sh else None,
        "maxdd_diff_mean": float(np.mean(dd)) if dd else None,
    }
    # Identify contiguous stretches where pair wins on Sharpe (persistence).
    stretches = []
    cur = None
    for r in rows:
        winning = r["d_sharpe"] is not None and np.isfinite(r["d_sharpe"]) and r["d_sharpe"] > 0
        if winning:
            if cur is None:
                cur = {"start": r["date"], "end": r["date"], "n": 1,
                       "max_d": r["d_sharpe"], "sum_d": r["d_sharpe"]}
            else:
                cur["end"] = r["date"]; cur["n"] += 1
                cur["max_d"] = max(cur["max_d"], r["d_sharpe"]); cur["sum_d"] += r["d_sharpe"]
        else:
            if cur is not None:
                stretches.append(cur); cur = None
    if cur is not None:
        stretches.append(cur)
    stretches.sort(key=lambda s: s["n"], reverse=True)
    return {"win": win, "top_stretches": stretches[:8], "rows": rows, "label": label,
            "win_days": win_days}


REGIMES = {
    "dotcom_2000_2002": ("2000-03-01", "2002-12-31"),
    "gfc_2008_2009": ("2007-10-01", "2009-06-30"),
    "covid_2020": ("2020-02-01", "2020-06-30"),
    "rate_hike_2022": ("2022-01-01", "2022-12-31"),
    "euro_crisis_2011": ("2011-05-01", "2011-12-31"),
    "taper_2013": ("2013-05-01", "2013-12-31"),
    "vol_2015_2016": ("2015-07-01", "2016-02-29"),
    "q4_2018": ("2018-09-01", "2018-12-31"),
    "2023_2024_bull": ("2023-01-01", "2024-12-31"),
}


def drawdown_episodes(ret, top=6, min_depth=0.05):
    """Return largest peak-to-trough drawdown episodes for a return series."""
    eq = (1.0 + ret).cumprod()
    rm = eq.cummax()
    dd = eq / rm - 1.0
    episodes = []
    in_dd = False
    peak_date = eq.index[0]
    for i in range(len(dd)):
        d = dd.iloc[i]
        if not in_dd and d < 0:
            in_dd = True
            peak_date = dd.index[i - 1] if i > 0 else dd.index[i]
            trough_date = dd.index[i]; trough_val = d
        elif in_dd:
            if d < trough_val:
                trough_val = d; trough_date = dd.index[i]
            if d >= 0:  # recovered
                episodes.append({"peak": peak_date, "trough": trough_date,
                                 "recover": dd.index[i], "depth": float(trough_val)})
                in_dd = False
    if in_dd:
        episodes.append({"peak": peak_date, "trough": trough_date,
                         "recover": None, "depth": float(trough_val)})
    episodes = [e for e in episodes if e["depth"] <= -min_depth]
    episodes.sort(key=lambda e: e["depth"])
    return episodes[:top]


def weights_in_window(close, daily, start, end, P):
    sigs = PV.sig_dates(close, pd.Timestamp(start), pd.Timestamp(end))
    ws = PV.weight_series(close, daily, sigs, P)
    out = []
    for sd, w in ws:
        mw, effn = PV.concentration(w)
        held = {k: round(v, 4) for k, v in sorted(w.items(), key=lambda x: -x[1]) if v > 1e-6}
        out.append({"sig": str(sd.date()), "max_w": round(mw, 4),
                    "eff_n": round(effn, 3), "held": held})
    return out


def main():
    end = pd.Timestamp("2026-05-22")
    ext_start = pd.Timestamp("1999-03-10")
    clean_start = pd.Timestamp("2008-05-30")

    panel = load_panel(start=ext_start, end=end)
    end = min(end, panel.index[-1])
    cash = panel["SHV"].ffill().pct_change().dropna()
    panel["BIL"] = stitch_bil(panel)
    panel["AGG"] = stitch_agg(panel)

    open_df, close_yf = H.load_open_close()
    intraday = (close_yf / open_df - 1.0).reindex(panel.index)
    overnight = (open_df / close_yf.shift(1) - 1.0).reindex(panel.index)

    cpm_cols = sorted(set(PV.CPM_PROD_UNIVERSE + PV.CPM_SAFE + ["HYG", "TIP"]) & set(panel.columns))
    close = panel[cpm_cols]
    daily = close.ffill().pct_change()

    # Full-ext daily returns, both schemes, 10 bps.
    print("Computing ext daily returns (both schemes, 10 bps)...")
    ret_pair = PV.returns_for(close, daily, intraday, overnight, ext_start, end, 1, HEAD_BPS)
    ret_cont = PV.returns_for(close, daily, intraday, overnight, ext_start, end, 0, HEAD_BPS)

    out = {"meta": {"conv": CONV, "head_bps": HEAD_BPS, "lookback": CORR_LOOKBACK_DAYS,
                    "clean_start": str(clean_start.date()), "ext_start": str(ext_start.date()),
                    "end": str(end.date())}}

    # ---- verify anchors (CLEAN, 10 bps) ----
    def slc(r, a, b):
        return r.loc[(r.index >= a) & (r.index <= b)]
    vp = perf_metrics(slc(ret_pair, clean_start, end), cash)
    vc = perf_metrics(slc(ret_cont, clean_start, end), cash)
    out["verify_clean"] = {
        "pair": {"sharpe": vp["sharpe"], "calmar": vp["calmar"], "maxdd": vp["max_drawdown"]},
        "cont": {"sharpe": vc["sharpe"], "calmar": vc["calmar"], "maxdd": vc["max_drawdown"]},
        "anchor_pair": "1.2424/0.8704/-16.35%", "anchor_cont": "1.2935/0.9618/-15.15%"}
    print(f"VERIFY pair: {vp['sharpe']:.4f}/{vp['calmar']:.4f}/{vp['max_drawdown']*100:.2f}% (exp 1.2424/0.8704/-16.35%)")
    print(f"VERIFY cont: {vc['sharpe']:.4f}/{vc['calmar']:.4f}/{vc['max_drawdown']*100:.2f}% (exp 1.2935/0.9618/-15.15%)")

    # full-window metrics both windows
    out["full_window"] = {}
    for wn, a in [("CLEAN", clean_start), ("EXT", ext_start)]:
        mp = perf_metrics(slc(ret_pair, a, end), cash)
        mc = perf_metrics(slc(ret_cont, a, end), cash)
        out["full_window"][wn] = {
            "pair": {"sharpe": mp["sharpe"], "calmar": mp["calmar"], "cagr": mp["cagr"], "maxdd": mp["max_drawdown"]},
            "cont": {"sharpe": mc["sharpe"], "calmar": mc["calmar"], "cagr": mc["cagr"], "maxdd": mc["max_drawdown"]}}

    # ---- 1. ROLLING DIFFERENCE ----
    print("Rolling difference (12m & 36m, both windows)...")
    out["rolling"] = {}
    for wn, a in [("CLEAN", clean_start), ("EXT", ext_start)]:
        out["rolling"][wn] = {}
        for win_days, wl in [(365, "12m"), (1095, "36m")]:
            rd = rolling_diff(ret_pair, ret_cont, cash, (a, end), win_days, wl)
            # drop heavy rows from json (keep summary + stretches + sparse series)
            series = [{"date": r["date"], "d_sharpe": round(r["d_sharpe"], 4) if r["d_sharpe"] is not None else None,
                       "d_calmar": round(r["d_calmar"], 4) if r["d_calmar"] is not None else None,
                       "d_maxdd": round(r["d_maxdd"], 4) if r["d_maxdd"] is not None else None}
                      for r in rd["rows"]]
            out["rolling"][wn][wl] = {"win": rd["win"], "top_stretches": rd["top_stretches"],
                                      "series": series}

    # ---- 2. PER-REGIME ----
    print("Per-regime metrics...")
    out["regimes"] = {}
    for name, (a, b) in REGIMES.items():
        a = pd.Timestamp(a); b = pd.Timestamp(b)
        if a < ext_start:
            a = ext_start
        sp = slc(ret_pair, a, b); sc = slc(ret_cont, a, b)
        if len(sp) < 20:
            continue
        mp = perf_metrics(sp, cash); mc = perf_metrics(sc, cash)
        out["regimes"][name] = {
            "start": str(a.date()), "end": str(b.date()), "n_days": len(sp),
            "pair": {"sharpe": mp["sharpe"], "cagr": mp["cagr"], "maxdd": mp["max_drawdown"],
                     "calmar": mp["calmar"], "total_ret": mp["total_return"]},
            "cont": {"sharpe": mc["sharpe"], "cagr": mc["cagr"], "maxdd": mc["max_drawdown"],
                     "calmar": mc["calmar"], "total_ret": mc["total_return"]},
            "pair_wins_sharpe": bool(mp["sharpe"] > mc["sharpe"]),
            "pair_wins_maxdd": bool(mp["max_drawdown"] > mc["max_drawdown"]),
            "pair_wins_totalret": bool(mp["total_return"] > mc["total_return"])}

    # ---- 3. WORST-EPISODE / drawdown attribution ----
    print("Drawdown episodes + weight attribution...")
    out["episodes"] = {}
    for scheme, ret in [("pair", ret_pair), ("cont", ret_cont)]:
        eps = drawdown_episodes(slc(ret, ext_start, end), top=6)
        out["episodes"][scheme] = [{"peak": str(e["peak"].date()), "trough": str(e["trough"].date()),
                                    "recover": str(e["recover"].date()) if e["recover"] else None,
                                    "depth": round(e["depth"], 4)} for e in eps]

    # For each major continuous DD episode, diagnose weights of BOTH schemes in
    # the run-up window (peak-180d .. trough). Also generic key stress windows.
    diag_windows = {
        "gfc_2008": ("2008-06-01", "2009-06-30"),
        "covid_2020": ("2020-01-01", "2020-05-31"),
        "rate_hike_2022": ("2022-01-01", "2022-12-31"),
        "2013_taper": ("2013-04-01", "2013-09-30"),
        "2015_2016": ("2015-06-01", "2016-03-31"),
        "q4_2018": ("2018-08-01", "2019-01-31"),
        "dotcom_2000": ("2000-01-01", "2002-12-31"),
    }
    out["weight_diag"] = {}
    for name, (a, b) in diag_windows.items():
        a = pd.Timestamp(a)
        if a < ext_start:
            a = ext_start
        b = pd.Timestamp(b)
        out["weight_diag"][name] = {
            "pair": weights_in_window(close, daily, a, b, 1),
            "cont": weights_in_window(close, daily, a, b, 0)}

    (HERE / "pair_when_wins.json").write_text(json.dumps(out, indent=2, default=float))
    print("DONE -> pair_when_wins.json")
    # quick console summary of win fractions
    for wn in ("CLEAN", "EXT"):
        for wl in ("12m", "36m"):
            w = out["rolling"][wn][wl]["win"]
            print(f"{wn} {wl}: n={w['n_windows']} sharpe_win={w['sharpe_win_frac']} "
                  f"calmar_win={w['calmar_win_frac']} maxdd_win={w['maxdd_win_frac']} "
                  f"d_sharpe_mean={w['sharpe_diff_mean']:.4f}")
    return out


if __name__ == "__main__":
    main()
