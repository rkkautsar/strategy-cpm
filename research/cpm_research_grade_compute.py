"""ANALYST research-only (no prod/memo/README/dashboard edits; no commit).

Computes research-grade tables requested by the oracle review, all under the
CANONICAL convention: mooex (T+1 MOO exact), both-252, clean window
2008-05-30..2026-05-22 (+ext 1999-03-10), memo bootstrap params B=2000 block=21
seed=42.

ITEM 1  cost sensitivity: CPM sleeve + PROD blend Sharpe/Calmar/CAGR at 10/25/50
        bps per side (mooex). Built via the canonical build_dashboard sleeve
        construction (CPM/BULL engine mooex + NDX prod-cc + constituent-opens
        mooex delta overlay), with the per-side cost parametrized on all sleeves.
ITEM 4  README PROD bootstrap reconcile: stationary block bootstrap (B=2000,
        block=21, seed=42) on the SAME mooex-accounted PROD blend series as the
        headline (so Point == 1.4424 / 16.33% / -10.49% / 1.5566), giving the
        corrected CI bounds.

Outputs JSON -> research/cpm_research_grade_compute.json
"""
import sys
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import cpm_live
from cpm_live import (
    load_panel, perf_metrics, compute_target_weights,
    RISKY_UNIVERSE, SAFE_POOL, CANARY_ASSETS, DEFAULT_CASH,
)
import bull_spy_live
from bull_spy_live import BULL_TICKER, CASH_TICKER, compute_bull_spy_weights
import ndx_sleeve_live
from ndx_sleeve_live import compute_ndx_weights, run_ndx_backtest, load_ndx_panel
import build_dashboard as bd
from research import exec_lag_moo_validation_2026_05_30 as eng

CLEAN = pd.Timestamp("2008-05-30")
EXT = pd.Timestamp("1999-03-10")
END = pd.Timestamp("2026-05-22")
CPM_W, BULL_W, NDX_W = 0.60, 0.20, 0.20


def metrics(s, cash, lo, hi):
    sc = s.loc[(s.index >= lo) & (s.index <= hi)]
    m = perf_metrics(sc, cash)
    return {"sharpe": m.get("sharpe"), "cagr": m.get("cagr"), "vol": m.get("vol"),
            "maxdd": m.get("max_drawdown"), "calmar": m.get("calmar"), "martin": m.get("martin")}


def build_sleeves(panel, ndx_panel, macro_intraday, macro_overnight,
                  ndx_intraday_full, ndx_overnight_full, full_panel, cost_bps):
    """Replicates build_dashboard.build_artifacts sleeve construction with the
    per-side cost parametrized identically on all three sleeves. cost_bps=10.0
    reproduces the canonical headline."""
    run_start = max(EXT, panel.index.min())

    # CPM (engine mooex)
    cpm_cols = sorted(set(RISKY_UNIVERSE + SAFE_POOL + CANARY_ASSETS + [DEFAULT_CASH]) & set(panel.columns))
    cpm_close = panel[cpm_cols]
    cpm_daily = cpm_close.ffill().pct_change()
    cpm_wf = lambda sd: compute_target_weights(cpm_close, sd)[0]
    cpm_full, _ = eng._segment_returns_conv(cpm_close, cpm_daily, cpm_wf, run_start, END,
                                            "mooex", cost_bps, macro_intraday, macro_overnight)

    # BULL (engine mooex)
    bull_cols = sorted(set([BULL_TICKER, CASH_TICKER] + list(bull_spy_live.SAFE_POOL) + ["HYG", "TIP"]) & set(panel.columns))
    bull_close = panel[bull_cols]
    bull_daily = panel.ffill().pct_change()
    bull_wf = lambda sd: compute_bull_spy_weights(panel, sd, panel[BULL_TICKER])[0]
    bull_full, _ = eng._segment_returns_conv(bull_close, bull_daily, bull_wf, run_start, END,
                                             "mooex", cost_bps, macro_intraday, macro_overnight)

    # NDX (prod cc at cost + constituent-opens mooex delta at cost)
    ndx_cc_full, _ = run_ndx_backtest(panel, ndx_panel, run_start, END, cost_bps=cost_bps)
    ndx_daily = full_panel.ffill().pct_change()
    ndx_wf = lambda sd: compute_ndx_weights(panel, ndx_panel, sd)[0]
    ndx_moc_full, _ = eng._segment_returns_conv(full_panel, ndx_daily, ndx_wf, run_start, END,
                                                "moc", cost_bps, ndx_intraday_full, ndx_overnight_full)
    ndx_mooex_full, _ = eng._segment_returns_conv(full_panel, ndx_daily, ndx_wf, run_start, END,
                                                  "mooex", cost_bps, ndx_intraday_full, ndx_overnight_full)
    ndx_delta = (ndx_mooex_full - ndx_moc_full).reindex(ndx_cc_full.index).fillna(0.0)
    ndx_full = ndx_cc_full + ndx_delta

    common = cpm_full.index.intersection(bull_full.index).intersection(ndx_full.index)
    cpm = cpm_full.reindex(common)
    bull = bull_full.reindex(common)
    ndx = ndx_full.reindex(common).fillna(0.0)
    blend = CPM_W * cpm + BULL_W * bull + NDX_W * ndx
    return cpm, bull, ndx, blend


# ---------------- bootstrap (item 4): byte-identical to bootstrap_ci_2026_05_28 ----------------
def stationary_block_bootstrap(daily, block_size, rng):
    n = len(daily)
    n_blocks = (n // block_size) + 1
    arr = daily.values
    blocks = []
    for _ in range(n_blocks):
        s = rng.integers(0, n)
        e = s + block_size
        if e <= n:
            blocks.append(arr[s:e])
        else:
            blocks.append(np.concatenate([arr[s:], arr[:e - n]]))
    return pd.Series(np.concatenate(blocks)[:n], index=daily.index)


def boot_metrics(daily):
    m = perf_metrics(daily)
    calmar = m["cagr"] / abs(m["max_drawdown"]) if m["max_drawdown"] != 0 else np.nan
    return {"Sharpe": m["sharpe"], "CAGR": m["cagr"], "Vol": m["vol"],
            "MaxDD": m["max_drawdown"], "Calmar": calmar}


def bootstrap_ci(daily, n_iter=2000, block_size=21, seed=42):
    rng = np.random.default_rng(seed)
    keys = ["Sharpe", "CAGR", "Vol", "MaxDD", "Calmar"]
    boot = {k: [] for k in keys}
    for _ in range(n_iter):
        b = stationary_block_bootstrap(daily, block_size, rng)
        m = boot_metrics(b)
        for k in keys:
            boot[k].append(m[k])
    out = {}
    for k in keys:
        a = np.array(boot[k], dtype=float)
        a = a[np.isfinite(a)]
        out[k] = {p: float(np.percentile(a, q)) for p, q in
                  [("p2.5", 2.5), ("p25", 25), ("p50", 50), ("p75", 75), ("p97.5", 97.5)]}
        out[k]["mean"] = float(a.mean())
    return out


def main():
    panel_start = pd.Timestamp("1995-01-01")
    panel = load_panel(start=panel_start, end=END, live=False)
    panel = panel.loc[panel.index <= END]
    cash = panel["SHV"].ffill().pct_change().dropna()
    ndx_panel = load_ndx_panel()

    # legs (built once)
    macro_eng, macro_intraday, macro_overnight = bd._load_macro_mooex_legs(panel.index)
    full_panel = panel.join(ndx_panel, how="outer", rsuffix="_dup")
    full_panel = full_panel.loc[:, ~full_panel.columns.str.endswith("_dup")]
    full_panel = full_panel.loc[full_panel.index <= END]
    ndx_intr, ndx_ovn = bd._load_ndx_constituent_mooex_legs(full_panel.index)
    intr_full = macro_intraday.reindex(full_panel.index)
    ovn_full = macro_overnight.reindex(full_panel.index)
    add_cols = [c for c in ndx_intr.columns if c not in intr_full.columns]
    if add_cols:
        intr_full = intr_full.join(ndx_intr[add_cols], how="left")
        ovn_full = ovn_full.join(ndx_ovn[add_cols], how="left")

    out = {"meta": {
        "convention": "mooex (T+1 MOO exact)", "both252": True,
        "clean": f"{CLEAN.date()}..{END.date()}", "ext": f"{EXT.date()}..{END.date()}",
        "panel_rows": int(len(panel)), "corr_lookback": cpm_live.CORR_LOOKBACK_DAYS,
        "blend_weights": [CPM_W, BULL_W, NDX_W],
        "note": ("PROD = canonical build_dashboard sleeve construction (CPM/BULL engine "
                 "mooex + NDX prod-cc + constituent-opens mooex delta). Cost applied per-side "
                 "to all three sleeves."),
    }}

    # ---- ITEM 1: cost sensitivity ----
    cost_rows = {}
    base_blend = None
    for cb in (10.0, 25.0, 50.0):
        cpm, bull, ndx, blend = build_sleeves(panel, ndx_panel, macro_intraday, macro_overnight,
                                              intr_full, ovn_full, full_panel, cb)
        if cb == 10.0:
            base_blend = blend
        cost_rows[f"{int(cb)}bps"] = {
            "CPM_clean": metrics(cpm, cash, CLEAN, END),
            "PROD_clean": metrics(blend, cash, CLEAN, END),
            "CPM_ext": metrics(cpm, cash, EXT, END),
            "PROD_ext": metrics(blend, cash, EXT, END),
        }
        print(f"[cost {int(cb)}bps] CPM clean Sharpe={cost_rows[f'{int(cb)}bps']['CPM_clean']['sharpe']:.4f} "
              f"PROD clean Sharpe={cost_rows[f'{int(cb)}bps']['PROD_clean']['sharpe']:.4f}")
    out["item1_cost_sensitivity"] = cost_rows

    # ---- ITEM 4: README PROD bootstrap reconcile (clean window, mooex blend) ----
    blend_clean = base_blend.loc[(base_blend.index >= CLEAN) & (base_blend.index <= END)]
    point = boot_metrics(blend_clean)
    print(f"\n[bootstrap] PROD mooex clean Point: Sharpe={point['Sharpe']:.4f} CAGR={point['CAGR']*100:.2f}% "
          f"Vol={point['Vol']*100:.2f}% MaxDD={point['MaxDD']*100:.2f}% Calmar={point['Calmar']:.4f}")
    ci = bootstrap_ci(blend_clean, n_iter=2000, block_size=21, seed=42)
    out["item4_bootstrap_reconcile"] = {
        "n_days": int(len(blend_clean)),
        "point": point, "ci": ci,
        "params": {"B": 2000, "block": 21, "seed": 42, "method": "stationary block bootstrap"},
    }

    outpath = ROOT / "research" / "cpm_research_grade_compute.json"
    outpath.write_text(json.dumps(out, indent=2, default=lambda x: None if (x is None or (isinstance(x, float) and pd.isna(x))) else float(x)))
    print(f"\nWROTE {outpath}")


if __name__ == "__main__":
    main()
