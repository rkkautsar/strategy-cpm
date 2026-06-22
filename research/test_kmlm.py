#!/usr/bin/env python3
"""
Test: Add KMLM as 9th asset to CPM risky universe.

Compares three variants:
  - Baseline: 8-asset, TOP_K=4, fraction curve {1:0,2:0,3:0.5,4:1.0}
  - Variant A: +KMLM, TOP_K=4, same fraction curve
  - Variant B: +KMLM, TOP_K=5, fraction curve {1:0,2:0,3:0.33,4:0.67,5:1.0}

Uses clean window: 2008-05-30 to 2026-04-30.
KMLM stitched data is merged post-load_panel to avoid modifying data_loader.py.
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

# Variant A: +KMLM, TOP_K=4
A_UNIVERSE = BASELINE_UNIVERSE + ["KMLM"]
A_TOP_K = 4
A_CURVE = {1: 0.0, 2: 0.0, 3: 0.5, 4: 1.0}  # same as baseline

# Variant B: +KMLM, TOP_K=5 (ceil(9/2)=5)
B_TOP_K = 5
B_CURVE = {1: 0.0, 2: 0.0, 3: 0.33, 4: 0.67, 5: 1.0}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_panel_with_kmlm(start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """Load the base panel then merge KMLM stitched data.

    Temporarily patches cpm_live.RISKY_UNIVERSE so that load_panel() includes
    KMLM in its 'needed' set (and downloads/fetches it if needed). Then also
    merges the stitched file for extended history coverage.
    """
    original = cpm_live.RISKY_UNIVERSE
    cpm_live.RISKY_UNIVERSE = original + ["KMLM"]
    try:
        panel = load_panel(start=start, end=end)
    finally:
        cpm_live.RISKY_UNIVERSE = original

    # Ensure KMLM has full extended coverage via the stitched file.
    # The stitched series goes back to 1988, giving us pre-yfinance history.
    kmlm_path = Path(__file__).resolve().parent / "data" / "kmlm_stitched_daily.csv"
    if kmlm_path.exists():
        kmlm = pd.read_csv(kmlm_path, parse_dates=[0], index_col=0)
        # The file's header is "KMLM_stitched" — rename to "KMLM"
        kmlm.columns = ["KMLM"]
        # Align to panel's date range; works whether KMLM already exists or not.
        panel["KMLM"] = kmlm["KMLM"].reindex(panel.index).ffill()
    else:
        print("WARN: kmlm_stitched_daily.csv not found — using yfinance-only data", file=sys.stderr)

    return panel


def run_variant(
    panel: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
    risky_universe: list[str],
    top_k: int,
    fraction_curve: dict[int, float],
    label: str,
) -> pd.Series:
    """Run CPM backtest with the given parameters patched into cpm_live.

    Returns the daily return series.
    """
    # Save originals
    orig_univ = cpm_live.RISKY_UNIVERSE
    orig_topk = cpm_live.TOP_K_CANDIDATES
    orig_curve = cpm_live.CPM_RISKY_FRACTION_CURVE

    try:
        cpm_live.RISKY_UNIVERSE = risky_universe
        cpm_live.TOP_K_CANDIDATES = top_k
        cpm_live.CPM_RISKY_FRACTION_CURVE = fraction_curve

        returns, history = run_cpm_backtest(panel, start, end)
        print(f"  ✓ {label}: {len(returns)} daily obs, {len(history)} months")
        return returns
    finally:
        cpm_live.RISKY_UNIVERSE = orig_univ
        cpm_live.TOP_K_CANDIDATES = orig_topk
        cpm_live.CPM_RISKY_FRACTION_CURVE = orig_curve


def count_kmlm_appearances(
    panel: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
    risky_universe: list[str],
    top_k: int,
    fraction_curve: dict[int, float],
) -> pd.Series:
    """Run the backtest and return a Series: signal_date -> 1 if KMLM in basket else 0."""
    # Reuse run_variant logic but also capture weights_history
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
            # KMLM appears in the basket if it has nonzero weight
            appearances[sig_d] = 1 if weights.get("KMLM", 0.0) > 1e-8 else 0
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
        eq_start = eq[daily.index[mask].min()] / 100_000.0 * 100_000.0
        eq_end = eq[daily.index[mask].max()]
        ann[yr] = eq_end / eq.loc[daily.index[mask].min()] - 1 if mask.sum() > 1 else daily.loc[mask].iloc[0]
    return pd.Series(ann)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 72)
    print("CPM + KMLM Backtest Comparison")
    print(f"Window: {START.date()} → {END.date()}")
    print("=" * 72)

    # 1. Load panel (with KMLM stitched merged)
    print("\nLoading panel data...")
    panel = load_panel_with_kmlm(START, END)
    print(f"  Panel shape: {panel.shape}")
    print(f"  Columns: {sorted(panel.columns.tolist())}")
    print(f"  Date range: {panel.index.min().date()} → {panel.index.max().date()}")

    # Confirm KMLM is in the panel
    assert "KMLM" in panel.columns, "KMLM not found in panel after merge!"
    kmlm_valid = panel["KMLM"].notna().sum()
    print(f"  KMLM non-null days: {kmlm_valid} / {len(panel)}")

    # 2. Run variants
    print("\n" + "-" * 72)
    print("Running backtest variants...")
    print("-" * 72)

    baseline_ret = run_variant(
        panel, START, END,
        BASELINE_UNIVERSE, BASELINE_TOP_K, BASELINE_CURVE,
        "Baseline (8 assets, TOP_K=4)",
    )
    print()

    a_ret = run_variant(
        panel, START, END,
        A_UNIVERSE, A_TOP_K, A_CURVE,
        "Variant A (+KMLM, TOP_K=4)",
    )
    print()

    b_ret = run_variant(
        panel, START, END,
        A_UNIVERSE, B_TOP_K, B_CURVE,
        "Variant B (+KMLM, TOP_K=5, frac={1:0,2:0,3:0.33,4:0.67,5:1.0})",
    )

    # 3. Performance comparison
    print("\n" + "-" * 72)
    print("Performance Metrics")
    print("-" * 72)

    results = {
        "Baseline (8 assets)": baseline_ret,
        "Variant A (+KMLM k=4)": a_ret,
        "Variant B (+KMLM k=5)": b_ret,
    }

    metrics_df_rows = []
    for label, ret in results.items():
        m = perf_metrics(ret)
        metrics_df_rows.append({
            "Label": label,
            "CAGR": m.get("cagr", float("nan")),
            "Vol": m.get("vol", float("nan")),
            "Sharpe": m.get("sharpe", float("nan")),
            "MaxDD": m.get("max_drawdown", float("nan")),
            "Calmar": m.get("calmar", float("nan")),
        })

    metrics_df = pd.DataFrame(metrics_df_rows).set_index("Label")
    # Format percentages nicely
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
    # Format as percentages
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

    # 5. KMLM selection frequency
    print("\n" + "-" * 72)
    print("KMLM Selection Frequency (months where KMLM has nonzero weight)")
    print("-" * 72)

    for label, univ, tk, curve in [
        ("Variant A (+KMLM k=4)", A_UNIVERSE, A_TOP_K, A_CURVE),
        ("Variant B (+KMLM k=5)", A_UNIVERSE, B_TOP_K, B_CURVE),
    ]:
        kmlm_picks = count_kmlm_appearances(panel, START, END, univ, tk, curve)
        total_months = len(kmlm_picks)
        selected_months = int(kmlm_picks.sum())
        pct = selected_months / total_months * 100
        selected_years = sorted(set(kmlm_picks.index[kmlm_picks == 1].year))
        print(f"\n  {label}:")
        print(f"    Selected: {selected_months} / {total_months} months ({pct:.1f}%)")
        if selected_months > 0:
            # Show first/last selections
            sel_dates = kmlm_picks[kmlm_picks == 1].index
            print(f"    First selection: {sel_dates[0].date()}")
            print(f"    Last selection:  {sel_dates[-1].date()}")
            print(f"    Years with selection: {selected_years}")

    # 6. Correlation between variant returns
    print("\n" + "-" * 72)
    print("Return Correlation Matrix")
    print("-" * 72)

    corr_df = pd.DataFrame({k: v for k, v in results.items()})
    display_corr = corr_df.corr()
    print(display_corr.map(lambda v: f"{v:.4f}").to_string())

    # 7. Cumulative wealth comparison
    print("\n" + "-" * 72)
    print("Cumulative Wealth (start=$100k)")
    print("-" * 72)

    eq_df = pd.DataFrame({k: (1 + v).cumprod() * 100_000 for k, v in results.items()})
    final_vals = eq_df.iloc[-1]
    for label in final_vals.index:
        print(f"  {label:35s}: ${final_vals[label]:>10,.0f}")

    # 8. Full-period drawdown stats
    print("\n" + "-" * 72)
    print("Drawdown Statistics")
    print("-" * 72)

    for label, ret in results.items():
        eq = (1 + ret).cumprod() * 100_000
        dd = eq / eq.cummax() - 1
        print(f"  {label:35s}: max DD={dd.min()*100:.2f}%, "
              f"avg DD={dd.mean()*100:.2f}%, "
              f"days in DD={(dd < 0).sum()}")

    print("\nDone.")


if __name__ == "__main__":
    main()
