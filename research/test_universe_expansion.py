#!/usr/bin/env python3
"""
Test: Add IWM and/or LQD to CPM risky universe.

Compares four variants:
  1. Baseline:  8 assets (QQQ,SPHQ,EFA,EEM,VNQ,GLD,TLT,DBC), TOP_K=4
  2. +IWM:      9 assets, TOP_K=5, fraction curve {1:0,2:0,3:0.33,4:0.67,5:1.0}
  3. +LQD:      9 assets, TOP_K=5, fraction curve {1:0,2:0,3:0.33,4:0.67,5:1.0}
  4. +IWM+LQD: 10 assets, TOP_K=5, fraction curve {1:0,2:0,3:0.33,4:0.67,5:1.0}

Uses clean window: 2008-05-30 to 2026-04-30.

Data notes:
  - IWM is already in the proxy CSV (proxy_adjusted_close_daily.csv).
    load_panel will fetch it when RISKY_UNIVERSE includes it.
  - LQD is loaded by load_panel as a stitched file (lqd_stitched_daily.csv).
    It's already in the panel columns unconditionally.
  - No special data loading needed — just patch RISKY_UNIVERSE before calling
    load_panel and it handles everything.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Ensure we can import from the repo root
sys.path.insert(0, str(Path(__file__).resolve().parent))

import cpm_live
from cpm_live import run_cpm_backtest
from data_loader import load_panel
from core import perf_metrics


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
START = pd.Timestamp("2008-05-30")
END = pd.Timestamp("2026-04-30")  # matches EVAL_END

# Baseline config
BASELINE_UNIVERSE = list(cpm_live.RISKY_UNIVERSE)  # 8 assets
BASELINE_TOP_K = 4
BASELINE_CURVE = {1: 0.0, 2: 0.0, 3: 0.5, 4: 1.0}

# Expanded configs: 9 or 10 assets use TOP_K=5 with stretched curve
EXPANDED_TOP_K = 5
EXPANDED_CURVE = {1: 0.0, 2: 0.0, 3: 0.33, 4: 0.67, 5: 1.0}

# Variant definitions
VARIANTS = {
    "Baseline (8 assets)": {
        "universe": BASELINE_UNIVERSE,
        "top_k": BASELINE_TOP_K,
        "curve": BASELINE_CURVE,
        "extra": [],
    },
    "+IWM (9 assets)": {
        "universe": BASELINE_UNIVERSE + ["IWM"],
        "top_k": EXPANDED_TOP_K,
        "curve": EXPANDED_CURVE,
        "extra": ["IWM"],
    },
    "+LQD (9 assets)": {
        "universe": BASELINE_UNIVERSE + ["LQD"],
        "top_k": EXPANDED_TOP_K,
        "curve": EXPANDED_CURVE,
        "extra": ["LQD"],
    },
    "+IWM+LQD (10 assets)": {
        "universe": BASELINE_UNIVERSE + ["IWM", "LQD"],
        "top_k": EXPANDED_TOP_K,
        "curve": EXPANDED_CURVE,
        "extra": ["IWM", "LQD"],
    },
}

# Asset class mapping for coverage analysis
ASSET_CLASS = {
    "QQQ":  "US Growth/Tech",
    "SPHQ": "US Quality",
    "EFA":  "Intl Developed",
    "EEM":  "Intl Emerging",
    "VNQ":  "Real Estate",
    "GLD":  "Gold",
    "TLT":  "Long Treasuries",
    "DBC":  "Commodities",
    "IWM":  "US Small Cap",
    "LQD":  "IG Credit",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_panel_expanded(
    start: pd.Timestamp, end: pd.Timestamp, extra_assets: list[str]
) -> pd.DataFrame:
    """Load the panel with extra assets added to RISKY_UNIVERSE temporarily.

    For IWM: it's in the proxy CSV, so load_panel will include it when present
    in RISKY_UNIVERSE.
    For LQD: load_panel already loads LQD unconditionally via the stitched file.
    Patching RISKY_UNIVERSE ensures both are in the 'needed' set for yfinance
    fallback if needed.
    """
    original = cpm_live.RISKY_UNIVERSE
    expanded = sorted(set(original + extra_assets))
    cpm_live.RISKY_UNIVERSE = expanded
    try:
        panel = load_panel(start=start, end=end)
    finally:
        cpm_live.RISKY_UNIVERSE = original
    return panel


def run_variant(
    panel: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
    risky_universe: list[str],
    top_k: int,
    fraction_curve: dict[int, float],
    label: str,
) -> tuple[pd.Series, list]:
    """Run CPM backtest with the given parameters patched into cpm_live.

    Returns (daily_return_series, history_list).
    """
    orig_univ = cpm_live.RISKY_UNIVERSE
    orig_topk = cpm_live.TOP_K_CANDIDATES
    orig_curve = cpm_live.CPM_RISKY_FRACTION_CURVE

    try:
        cpm_live.RISKY_UNIVERSE = risky_universe
        cpm_live.TOP_K_CANDIDATES = top_k
        cpm_live.CPM_RISKY_FRACTION_CURVE = fraction_curve

        returns, history = run_cpm_backtest(panel, start, end)
        print(f"  ✓ {label}: {len(returns)} daily obs, {len(history)} months")
        return returns, history
    finally:
        cpm_live.RISKY_UNIVERSE = orig_univ
        cpm_live.TOP_K_CANDIDATES = orig_topk
        cpm_live.CPM_RISKY_FRACTION_CURVE = orig_curve


def count_asset_appearances(
    panel: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
    risky_universe: list[str],
    top_k: int,
    fraction_curve: dict[int, float],
    asset_ticker: str,
) -> pd.Series:
    """Run the backtest and return a Series: signal_date -> 1 if asset has nonzero weight."""
    orig_univ = cpm_live.RISKY_UNIVERSE
    orig_topk = cpm_live.TOP_K_CANDIDATES
    orig_curve = cpm_live.CPM_RISKY_FRACTION_CURVE

    try:
        cpm_live.RISKY_UNIVERSE = risky_universe
        cpm_live.TOP_K_CANDIDATES = top_k
        cpm_live.CPM_RISKY_FRACTION_CURVE = fraction_curve

        _, history = run_cpm_backtest(panel, start, end)

        appearances = {}
        for h in history:
            sig_d = h["sig_d"]
            weights = h["weights"]
            appearances[sig_d] = 1 if weights.get(asset_ticker, 0.0) > 1e-8 else 0
        return pd.Series(appearances).sort_index()
    finally:
        cpm_live.RISKY_UNIVERSE = orig_univ
        cpm_live.TOP_K_CANDIDATES = orig_topk
        cpm_live.CPM_RISKY_FRACTION_CURVE = orig_curve


def year_by_year_returns(daily: pd.Series) -> pd.Series:
    """Compute calendar-year total returns from a daily return series."""
    eq = (1.0 + daily).cumprod()
    years = sorted(set(daily.index.year))
    ann = {}
    for yr in years:
        mask = daily.index.year == yr
        if mask.sum() == 0:
            continue
        yr_start = eq[daily.index[mask].min()]
        yr_end = eq[daily.index[mask].max()]
        ann[yr] = yr_end / yr_start - 1
    return pd.Series(ann)


def asset_class_coverage(universe: list[str]) -> pd.Series:
    """Return a Series mapping each asset to its class, plus a coverage summary."""
    return pd.Series({t: ASSET_CLASS.get(t, "Unknown") for t in universe}, name="Asset Class")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 72)
    print("CPM + IWM/LQD Universe Expansion Comparison")
    print(f"Window: {START.date()} → {END.date()}")
    print("=" * 72)

    # Determine max extra assets needed
    all_extras = sorted({a for v in VARIANTS.values() for a in v["extra"]})

    # 1. Load panel (with all needed assets available)
    print("\nLoading panel data (with expanded universe)...")
    panel = load_panel_expanded(START, END, all_extras)
    print(f"  Panel shape: {panel.shape}")
    print(f"  Columns: {sorted(panel.columns.tolist())}")
    print(f"  Date range: {panel.index.min().date()} → {panel.index.max().date()}")

    # Verify extra assets are present
    for ticker in all_extras:
        if ticker in panel.columns:
            valid = panel[ticker].notna().sum()
            print(f"  {ticker} non-null days: {valid} / {len(panel)}")
        else:
            print(f"  WARN: {ticker} not found in panel!", file=sys.stderr)

    # 2. Run all variants
    print("\n" + "-" * 72)
    print("Running backtest variants...")
    print("-" * 72)

    results = {}       # label -> daily returns
    histories = {}     # label -> history list

    for label, cfg in VARIANTS.items():
        ret, hist = run_variant(
            panel, START, END,
            cfg["universe"], cfg["top_k"], cfg["curve"], label,
        )
        results[label] = ret
        histories[label] = hist

    # 3. Performance comparison
    print("\n" + "-" * 72)
    print("Performance Metrics")
    print("-" * 72)

    metrics_rows = []
    for label, ret in results.items():
        m = perf_metrics(ret)
        metrics_rows.append({
            "Label": label,
            "CAGR": m.get("cagr", float("nan")),
            "Vol": m.get("vol", float("nan")),
            "Sharpe": m.get("sharpe", float("nan")),
            "MaxDD": m.get("max_drawdown", float("nan")),
            "Calmar": m.get("calmar", float("nan")),
        })

    metrics_df = pd.DataFrame(metrics_rows).set_index("Label")
    for col in ["CAGR", "Vol", "MaxDD"]:
        metrics_df[col] = metrics_df[col].map(lambda v: f"{v*100:.2f}%")
    for col in ["Sharpe", "Calmar"]:
        metrics_df[col] = metrics_df[col].map(lambda v: f"{v:.3f}" if pd.notna(v) else "N/A")
    print(metrics_df.to_string())

    # 4. Year-by-year returns
    print("\n" + "-" * 72)
    print("Year-by-Year Returns")
    print("-" * 72)

    yby_data = {}
    for label, ret in results.items():
        yby_data[label] = year_by_year_returns(ret)

    yby_df = pd.DataFrame(yby_data)
    yby_df.index.name = "Year"
    print(yby_df.map(lambda v: f"{v*100:+.2f}%").to_string())

    # Summary statistics on year-by-year
    print("\nYear-by-Year Summary:")
    summary_rows = []
    for label in yby_data:
        s = yby_data[label]
        summary_rows.append({
            "Label": label,
            "Mean": f"{s.mean()*100:+.2f}%",
            "Median": f"{s.median()*100:+.2f}%",
            "Min": f"{s.min()*100:+.2f}%",
            "Max": f"{s.max()*100:+.2f}%",
            "Positive": f"{(s > 0).sum()}/{len(s)}",
        })
    print(pd.DataFrame(summary_rows).set_index("Label").to_string())

    # 5. Asset class coverage
    print("\n" + "-" * 72)
    print("Asset Class Coverage")
    print("-" * 72)

    # Collect unique classes for the legend
    all_classes = sorted({ASSET_CLASS.get(t, "Unknown") for t in all_extras + BASELINE_UNIVERSE})
    coverage_rows = []
    for label, cfg in VARIANTS.items():
        row = {"Variant": label}
        for cls in all_classes:
            assets_in_class = [t for t in cfg["universe"] if ASSET_CLASS.get(t) == cls]
            if assets_in_class:
                row[cls] = ", ".join(assets_in_class)
            else:
                row[cls] = "—"
        coverage_rows.append(row)

    coverage_df = pd.DataFrame(coverage_rows).set_index("Variant")
    print(coverage_df.to_string())

    # Also show a count summary
    print("\nAsset count by class:")
    count_rows = []
    for label, cfg in VARIANTS.items():
        row = {"Variant": label, "Total": len(cfg["universe"])}
        for cls in all_classes:
            row[cls] = sum(1 for t in cfg["universe"] if ASSET_CLASS.get(t) == cls)
        count_rows.append(row)
    print(pd.DataFrame(count_rows).set_index("Variant").to_string())

    # 6. Asset selection frequency (IWM and LQD appearances)
    print("\n" + "-" * 72)
    print("Asset Selection Frequency")
    print("-" * 72)

    for ticker in all_extras:
        print(f"\n  --- {ticker} ({ASSET_CLASS.get(ticker, 'Unknown')}) ---")
        for label, cfg in VARIANTS.items():
            if ticker not in cfg["universe"]:
                continue  # skip variants that don't include this asset
            picks = count_asset_appearances(
                panel, START, END,
                cfg["universe"], cfg["top_k"], cfg["curve"], ticker,
            )
            total_months = len(picks)
            selected_months = int(picks.sum())
            pct = selected_months / total_months * 100 if total_months > 0 else 0
            print(f"\n    {label}:")
            print(f"      Selected: {selected_months} / {total_months} months ({pct:.1f}%)")
            if selected_months > 0:
                sel_dates = picks[picks == 1].index
                print(f"      First selection: {sel_dates[0].date()}")
                print(f"      Last selection:  {sel_dates[-1].date()}")
                selected_years = sorted(set(sel_dates.year))
                print(f"      Years with selection: {selected_years}")

    # 7. Correlation between variant returns
    print("\n" + "-" * 72)
    print("Return Correlation Matrix")
    print("-" * 72)

    corr_df = pd.DataFrame(results)
    print(corr_df.corr().map(lambda v: f"{v:.4f}").to_string())

    # 8. Cumulative wealth comparison
    print("\n" + "-" * 72)
    print("Cumulative Wealth (start=$100k)")
    print("-" * 72)

    eq_df = pd.DataFrame({k: (1 + v).cumprod() * 100_000 for k, v in results.items()})
    final_vals = eq_df.iloc[-1]
    for label in final_vals.index:
        print(f"  {label:30s}: ${final_vals[label]:>10,.0f}")

    # 9. Full-period drawdown stats
    print("\n" + "-" * 72)
    print("Drawdown Statistics")
    print("-" * 72)

    dd_rows = []
    for label, ret in results.items():
        eq = (1 + ret).cumprod() * 100_000
        dd = eq / eq.cummax() - 1
        dd_rows.append({
            "Variant": label,
            "Max DD": f"{dd.min()*100:.2f}%",
            "Avg DD": f"{dd.mean()*100:.2f}%",
            "Days in DD": (dd < 0).sum(),
        })
    print(pd.DataFrame(dd_rows).set_index("Variant").to_string())

    # 10. Drawdown in key stress periods
    print("\n" + "-" * 72)
    print("Stress Period Drawdowns")
    print("-" * 72)

    stress_periods = [
        ("GFC (2008-06 to 2009-02)", "2008-06-01", "2009-02-28"),
        ("COVID (2020-02 to 2020-03)", "2020-02-01", "2020-03-31"),
        ("2022 Rate Hike (2022-01 to 2022-10)", "2022-01-01", "2022-10-31"),
    ]

    for period_name, s, e in stress_periods:
        s_ts, e_ts = pd.Timestamp(s), pd.Timestamp(e)
        print(f"\n  {period_name}:")
        for label, ret in results.items():
            sub = ret[(ret.index >= s_ts) & (ret.index <= e_ts)]
            if len(sub) == 0:
                print(f"    {label:30s}: no data")
                continue
            eq = (1 + sub).cumprod()
            dd = eq / eq.cummax() - 1
            total_ret = eq.iloc[-1] - 1
            print(f"    {label:30s}: return={total_ret*100:+.2f}%, max DD={dd.min()*100:.2f}%")

    print("\nDone.")


if __name__ == "__main__":
    main()
