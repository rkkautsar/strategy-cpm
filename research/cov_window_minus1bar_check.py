"""Throwaway research: MINIMAL one-bar de-overlap test for the CPM weighting step.

Step-1 code audit (see cov_window_alignment_verdict.md) shows the min-var cov
window's LAST return bar is the return realized ON sig_d (close[sig_d-1] ->
close[sig_d]), while the newly-applied weights first earn STRICTLY AFTER sig_d's
close (mooex: intraday open[af]->close[af], af = first bar > sig_d). So the cov
window is already strictly trailing / disjoint -- no one-bar lookahead.

This run PROVES that by shifting the cov window back exactly ONE TRADING BAR
(cov_d = trading bar immediately before sig_d), i.e. strictly excluding sig_d's
own (already non-overlapping) return. If continuous's lag0 edge were an overlap
artifact, removing that bar would kill it. If the edge survives ~intact, lag0 is
legitimate freshest-trailing cov, not overlap.

This is the MINIMAL clean fix (one bar), NOT the cov_lookahead_check.py lag1
(which steps cov back a full MONTH to the prior rebalance date).

Headline convention: T+1 MOO exact (mooex), 10 bps/side, CLEAN 18y + EXT 27y.
Reuses cpm_wf_lag from cov_lookahead_check.py.
"""
import sys, json
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from cpm_live import load_panel, perf_metrics, COST_BPS_PER_SIDE, CORR_LOOKBACK_DAYS
import exec_lag_moo_validation_2026_05_30 as H
from sleeve_vs_benchmark_2026_05_30 import stitch_bil, stitch_agg
from cov_lookahead_check import (
    cpm_wf_lag, sig_dates, CONV, CPM_PROD_UNIVERSE, CPM_SAFE,
)


def build_minus1bar_map(close, sigs):
    """cov_d = trading bar immediately before sig_d (excludes sig_d's own return).
    lag0 baseline would use cov_d = sig_d (includes it)."""
    idx = close.index
    m = {}
    for sd in sigs:
        pos = idx.get_loc(sd)
        m[sd] = idx[pos - 1] if pos > 0 else sd
    return m


def returns_for(close, daily, intraday, overnight, start, end, P, cost_bps, cov_map):
    wf = lambda sd: cpm_wf_lag(close, daily, sd, P, cov_map.get(sd, sd))
    s, _ = H._segment_returns_conv(close, daily, wf, start, end, CONV,
                                   cost_bps, intraday, overnight)
    return s


def met(daily, cash):
    m = perf_metrics(daily, cash)
    return {"sharpe": round(float(m.get("sharpe")), 4),
            "cagr": round(float(m.get("cagr")), 4),
            "maxdd": round(float(m.get("max_drawdown")), 4),
            "calmar": round(float(m.get("calmar")), 4),
            "vol": round(float(m.get("vol")), 4)}


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

    cpm_cols = sorted(set(CPM_PROD_UNIVERSE + CPM_SAFE + ["HYG", "TIP"]) & set(panel.columns))
    close = panel[cpm_cols]
    daily = close.ffill().pct_change()

    sigs_ext = sig_dates(close, ext_start, end)
    # alignment A: lag0 baseline (cov_d = sig_d, includes sig_d return)
    map_lag0 = {sd: sd for sd in sigs_ext}
    # alignment B: minus-1-bar (cov_d = prior trading bar, excludes sig_d return)
    map_m1 = build_minus1bar_map(close, sigs_ext)

    windows = {"CLEAN": (clean_start, end), "EXT": (ext_start, end)}
    aligns = {"lag0_incl_sigd": map_lag0, "minus1bar_excl_sigd": map_m1}

    ret_cache = {}
    for P in (1, 0):
        for an, cm in aligns.items():
            ret_cache[(P, an)] = returns_for(close, daily, intraday, overnight,
                                             ext_start, end, P, COST_BPS_PER_SIDE, cm)
        print(f"scheme P={P} done")

    out = {"meta": {"conv": CONV, "lookback": CORR_LOOKBACK_DAYS,
                    "cost_bps": COST_BPS_PER_SIDE,
                    "clean_start": str(clean_start.date()), "ext_start": str(ext_start.date()),
                    "end": str(end.date()),
                    "aligns": {"lag0_incl_sigd": "cov window ends at sig_d (incl sig_d return)",
                               "minus1bar_excl_sigd": "cov window ends 1 trading bar before sig_d"}},
           "results": {}}

    for wn, (ws_, we_) in windows.items():
        wd = {}
        for an in aligns:
            row = {}
            for P, label in [(1, "pair_5050"), (0, "continuous_minvar")]:
                s = ret_cache[(P, an)]
                sw = s.loc[(s.index >= ws_) & (s.index <= we_)]
                row[label] = met(sw, cash)
            c, p = row["continuous_minvar"], row["pair_5050"]
            row["edge_cont_minus_pair"] = {
                "d_sharpe": round(c["sharpe"] - p["sharpe"], 4),
                "d_maxdd_pp": round((c["maxdd"] - p["maxdd"]) * 100, 2),
                "d_calmar": round(c["calmar"] - p["calmar"], 4),
            }
            wd[an] = row
        out["results"][wn] = wd

    Path(__file__).with_suffix(".json").write_text(json.dumps(out, indent=2, default=float))

    for wn in ("CLEAN", "EXT"):
        print(f"\n=== {wn}: lag0(incl sig_d) vs minus1bar(excl sig_d), 10 bps ===")
        print("  align                pair_Sh  cont_Sh  dSh      cont_DD%  dCalmar")
        for an in aligns:
            r = out["results"][wn][an]
            p, c, e = r["pair_5050"], r["continuous_minvar"], r["edge_cont_minus_pair"]
            print(f"  {an:<20} {p['sharpe']:.4f}  {c['sharpe']:.4f}  {e['d_sharpe']:+.4f}  "
                  f"{c['maxdd']*100:7.2f}  {e['d_calmar']:+.4f}")
    print("\nDONE -> json written")
    return out


if __name__ == "__main__":
    main()
