"""TRUE NDX mooex: delta overlay with REAL constituent opens (not cc fallback).

Mirrors research/cpm_mooex_migration_recompute.py NDX delta-overlay design, but
injects NDX-constituent intraday/overnight legs (from research/ndx_opens_cache.parquet)
into the engine so NDX-active rebalance days earn the real overnight gap instead of
falling back to close-to-close. CPM/BULL unchanged (canonical mooex).
"""
from pathlib import Path
import sys
import json
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import cpm_live
from cpm_live import perf_metrics, COST_BPS_PER_SIDE, compute_target_weights
import bull_spy_live
from bull_spy_live import BULL_TICKER, CASH_TICKER, compute_bull_spy_weights, run_bull_spy_backtest
import ndx_sleeve_live
from ndx_sleeve_live import compute_ndx_weights, run_ndx_backtest, load_ndx_panel
from research import cpm_harness
from research import exec_lag_moo_validation_2026_05_30 as eng

CLEAN = pd.Timestamp("2008-05-30")
EXT = pd.Timestamp("1999-03-10")
END = pd.Timestamp("2026-05-22")
OPENS = ROOT / "research" / "ndx_opens_cache.parquet"
KEYS = ("sharpe", "excess_sharpe", "cagr", "vol", "max_drawdown", "calmar", "martin")


def M(s, cash, lo, hi):
    sc = s.loc[(s.index >= lo) & (s.index <= hi)]
    m = perf_metrics(sc, cash)
    return {k: m.get(k) for k in KEYS}


def main():
    d = cpm_harness.load_data(end=END, clean_start=CLEAN, ext_start=EXT)
    panel, cash = d.panel, d.cash

    # CPM / BULL canonical mooex (unchanged)
    cpm_mooex = cpm_harness.run_strategy(compute_target_weights, window="ext", data=d)
    cpm_cc, _ = cpm_live.run_cpm_backtest(panel, EXT, END)

    def bull_wf(sd):
        return compute_bull_spy_weights(panel, sd, panel[BULL_TICKER])[0]
    cols_b = sorted(set([BULL_TICKER, CASH_TICKER] + list(bull_spy_live.SAFE_POOL) + ["HYG", "TIP"]) & set(panel.columns))
    close_b = panel[cols_b]
    dr_b = panel.ffill().pct_change()
    bull_mooex, _ = eng._segment_returns_conv(close_b, dr_b, bull_wf, EXT, END, "mooex", COST_BPS_PER_SIDE, d.intraday, d.overnight)
    bull_cc = run_bull_spy_backtest(panel, EXT, END)

    # ---- NDX with REAL constituent opens ----
    ndx_panel = load_ndx_panel()
    full = panel.join(ndx_panel, how="outer", rsuffix="_dup")
    full = full.loc[:, ~full.columns.str.endswith("_dup")]
    full = full.loc[full.index <= END]
    dr_n = full.ffill().pct_change()

    cache = pd.read_parquet(OPENS)
    c_open, c_close = cache["Open"], cache["Close"]
    intr_c = (c_close / c_open - 1.0)
    ovn_c = (c_open / c_close.shift(1) - 1.0)
    # sanity mask: implausible intraday -> NaN (engine falls back to cc for that cell)
    bad = intr_c.abs() > 0.5
    intr_c = intr_c.mask(bad)
    ovn_c = ovn_c.mask(bad)

    # macro legs (current cache) + constituent legs, reindexed to full panel
    intr = d.intraday.reindex(full.index)
    ovn = d.overnight.reindex(full.index)
    add_cols = [c for c in intr_c.columns if c not in intr.columns]
    intr = intr.join(intr_c[add_cols].reindex(full.index))
    ovn = ovn.join(ovn_c[add_cols].reindex(full.index))

    def ndx_wf(sd):
        return compute_ndx_weights(panel, ndx_panel, sd)[0]
    ndx_eng_moc, _ = eng._segment_returns_conv(full, dr_n, ndx_wf, EXT, END, "moc", ndx_sleeve_live.COST_BPS_PER_SIDE, intr, ovn)
    ndx_eng_mooex, ndx_fb = eng._segment_returns_conv(full, dr_n, ndx_wf, EXT, END, "mooex", ndx_sleeve_live.COST_BPS_PER_SIDE, intr, ovn)
    ndx_cc, _ = run_ndx_backtest(panel, ndx_panel, EXT, END)
    ndx_delta = (ndx_eng_mooex - ndx_eng_moc).reindex(ndx_cc.index).fillna(0.0)
    ndx_mooex = ndx_cc + ndx_delta

    def blend(c, b, n, wc, wb, wn):
        idx = c.index.intersection(b.index).intersection(n.index)
        return (wc * c.reindex(idx).fillna(0.0) + wb * b.reindex(idx).fillna(0.0)
                + wn * n.reindex(idx).fillna(0.0))

    prod_mooex = blend(cpm_mooex, bull_mooex, ndx_mooex, 0.6, 0.2, 0.2)
    prod_cc = blend(cpm_cc, bull_cc, ndx_cc, 0.6, 0.2, 0.2)

    out = {}
    for wlabel, lo in (("clean", CLEAN), ("ext", EXT)):
        out[wlabel] = {
            "NDX_cc": M(ndx_cc, cash, lo, END),
            "NDX_mooex_true": M(ndx_mooex, cash, lo, END),
            "PROD_cc": M(prod_cc, cash, lo, END),
            "PROD_mooex_true": M(prod_mooex, cash, lo, END),
        }
    out["coverage"] = {
        "ndx_rebal_real": ndx_fb[0],
        "ndx_rebal_fallback": ndx_fb[1],
        "ndx_delta_nonzero_clean": int((ndx_delta.loc[CLEAN:END] != 0).sum()),
        "constituent_opens_tickers": int(c_open.notna().any().sum()),
        "universe_tickers": int(ndx_panel.shape[1]),
    }
    print(json.dumps(out, indent=2, default=lambda x: None if pd.isna(x) else round(float(x), 6)))

    def line(name, m):
        return (f"{name:<26} Sh={m['sharpe']:.4f} ExcSh={m['excess_sharpe']:.4f} "
                f"CAGR={m['cagr']*100:7.3f}% Vol={m['vol']*100:6.3f}% "
                f"MaxDD={m['max_drawdown']*100:8.3f}% Calmar={m['calmar']:.4f} Martin={m['martin']:.4f}")
    for wlabel, lo in (("CLEAN", CLEAN), ("EXT", EXT)):
        k = wlabel.lower()
        print(f"\n=== {wlabel} ===")
        for nm in ("NDX_cc", "NDX_mooex_true", "PROD_cc", "PROD_mooex_true"):
            print(line(nm, out[k][nm]))
    print("\ncoverage:", json.dumps(out["coverage"]))


if __name__ == "__main__":
    main()
