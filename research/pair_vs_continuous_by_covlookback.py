"""Throwaway research (analyst, read-only re production): how does the
equal-weight 50/50 min-var PAIR vs CONTINUOUS min-var comparison change across
the COVARIANCE LOOKBACK length?

Hypothesis (DeMiguel 2009 estimation-error mechanism): continuous min-var
overfits noisy covariance, so at SHORTER lookbacks (more estimation error)
continuous DEGRADES relative to the pair (possibly the pair wins); at LONGER
lookbacks (more stable covariance) continuous holds/extends its edge.

Reuses research/pair_vs_continuous_minvar.cpm_wf_lb (P toggles weighting,
lookback parametrizes the cov window) and exec_lag_moo_validation
_segment_returns_conv (mooex T+1 MOO exact). Everything held at production
U=R=C=1, K=4, 10 bps/side. Only weighting (pair vs continuous) and cov lookback
vary; selection logic identical.

Windows: CLEAN 18y (2008-05-30..), EXT 27y (1999-03-10..).

No production files touched. Writes findings md + json next to this file.
"""
import sys, json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from cpm_live import load_panel, perf_metrics, COST_BPS_PER_SIDE
import exec_lag_moo_validation_2026_05_30 as H
from sleeve_vs_benchmark_2026_05_30 import stitch_bil, stitch_agg
from pair_vs_continuous_minvar import (
    cpm_wf_lb, sig_dates, weight_series, analyze_weights, CONV,
    CPM_PROD_UNIVERSE, CPM_SAFE,
)

LOOKBACKS = [126, 252, 504, 756, 1008, 1260]
PROD_LB = 504


def returns_for_lb(close, daily, intraday, overnight, start, end, P, lb, cost_bps):
    wf = lambda sd: cpm_wf_lb(close, daily, sd, P, lb)
    s, _ = H._segment_returns_conv(close, daily, wf, start, end, CONV,
                                   cost_bps, intraday, overnight)
    return s


def met(daily, cash):
    m = perf_metrics(daily, cash)
    return {"sharpe": float(m.get("sharpe")), "cagr": float(m.get("cagr")),
            "maxdd": float(m.get("max_drawdown")), "calmar": float(m.get("calmar")),
            "vol": float(m.get("vol"))}


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

    windows = {"CLEAN": (clean_start, end), "EXT": (ext_start, end)}

    out = {"meta": {"conv": CONV, "cost_bps_prod": COST_BPS_PER_SIDE,
                    "lookbacks": LOOKBACKS, "prod_lb": PROD_LB,
                    "clean_start": str(clean_start.date()),
                    "ext_start": str(ext_start.date()), "end": str(end.date())},
           "grid": {}, "concentration": {}}

    # Compute full-ext return series once per (P, lb) at 10 bps, slice to windows.
    print("Computing return series per (scheme, lookback) @10bps...")
    ret_cache = {}
    for P in (1, 0):
        for lb in LOOKBACKS:
            ret_cache[(P, lb)] = returns_for_lb(close, daily, intraday, overnight,
                                                ext_start, end, P, lb, 10)
            print(f"  P={P} lb={lb} done")

    for wn, (ws_, we_) in windows.items():
        grid = {}
        for lb in LOOKBACKS:
            row = {}
            for P, label in [(1, "pair"), (0, "continuous")]:
                s = ret_cache[(P, lb)]
                sw = s.loc[(s.index >= ws_) & (s.index <= we_)]
                row[label] = met(sw, cash)
            # continuous-minus-pair deltas
            row["delta_cont_minus_pair"] = {
                "sharpe": row["continuous"]["sharpe"] - row["pair"]["sharpe"],
                "calmar": row["continuous"]["calmar"] - row["pair"]["calmar"],
                "maxdd": row["continuous"]["maxdd"] - row["pair"]["maxdd"],
                "cagr": row["continuous"]["cagr"] - row["pair"]["cagr"],
            }
            grid[lb] = row
        out["grid"][wn] = grid

    # Concentration cross-check (EXT signal set; per-lookback continuous weights).
    print("Concentration cross-check (continuous, per lookback)...")
    sigs_ext = sig_dates(close, ext_start, end)
    n_years_ext = (end - ext_start).days / 365.25
    for lb in LOOKBACKS:
        conc = {}
        for P, label in [(1, "pair"), (0, "continuous")]:
            ws = weight_series(close, daily, sigs_ext, P, lb)
            wa = analyze_weights(ws, n_years_ext)
            conc[label] = {
                "avg_max_weight_all": wa["avg_max_weight_all"],
                "avg_max_weight_riskon": wa["avg_max_weight_riskon"],
                "max_single_weight": wa["max_single_weight"],
                "avg_eff_n_riskon": wa["avg_eff_n_riskon"],
            }
        out["concentration"][lb] = conc

    Path(__file__).with_suffix(".json").write_text(json.dumps(out, indent=2, default=float))

    # ---- verify anchors at 504d CLEAN 10bps ----
    print("\n=== VERIFY anchors (CLEAN, 504d, 10 bps) ===")
    p = out["grid"]["CLEAN"][504]["pair"]
    c = out["grid"]["CLEAN"][504]["continuous"]
    print(f"  pair      : sharpe={p['sharpe']:.4f} maxdd={p['maxdd']*100:.2f}% calmar={p['calmar']:.4f}"
          f"  (expect 1.2424/-16.35%/0.8704)")
    print(f"  continuous: sharpe={c['sharpe']:.4f} maxdd={c['maxdd']*100:.2f}% calmar={c['calmar']:.4f}"
          f"  (expect 1.2935/-15.15%/0.9618)")
    print("\nDONE -> json written")
    return out


if __name__ == "__main__":
    main()
