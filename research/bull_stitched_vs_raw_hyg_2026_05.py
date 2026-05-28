"""
Verify critic's claim: BULL-ext on raw yfinance HYG vs stitched HYG.

Tests:
  A. BULL-ext (current cpm_live live impl, HYG_stitched canary, sleeve-equity DD)
  B. BULL-ext but with HYG_stitched replaced by raw yfinance HYG (live from 2007)
  C. BULL no-DD: just the canary + asset_mom gate, no circuit
  D. HAA-Simple SPY (TIP only, no HYG canary at all)

Window: 2008-04-30 to 2026-05-22, 10bps/side, close-to-close.
"""
import sys, socket, os
socket.setdefaulttimeout(60)
sys.path.insert(0, "/Users/rkautsar/personal/scripts/strategy_cpm")

import pandas as pd
import numpy as np
import yfinance as yf
from cpm_live import load_panel, perf_metrics, sig_13612U, best_safe
from bull_qqq_live import run_bull_qqq_backtest
from vol_cap import compute_dd_circuit_scale, DD_CIRCUIT_THRESHOLD, DD_CIRCUIT_SCALE


def fetch_raw_hyg():
    cache = "/tmp/hyg_raw_yf.csv"
    if os.path.exists(cache):
        return pd.read_csv(cache, index_col=0, parse_dates=True).iloc[:, 0]
    print("Downloading raw HYG via yfinance...")
    df = yf.download("HYG", start="2007-01-01", end="2026-05-31",
                     auto_adjust=True, progress=False)
    s = df["Close"]
    if isinstance(s, pd.DataFrame):
        s = s.iloc[:, 0]
    s.to_csv(cache)
    return s


def run_bull_with_canary_override(panel, start, end, hyg_series_to_use, use_dd=True):
    """Run BULL by patching panel's HYG_stitched column to specified series, then running.
    Returns (raw_sleeve_returns, sleeve_after_dd_circuit)."""
    panel_local = panel.copy()
    if hyg_series_to_use is not None:
        # Replace HYG_stitched with the specified series
        if "HYG_stitched" in panel_local.columns:
            panel_local = panel_local.drop(columns=["HYG_stitched"])
        # Align and join
        hyg_aligned = hyg_series_to_use.reindex(panel_local.index)
        panel_local["HYG_stitched"] = hyg_aligned
    bull_raw = run_bull_qqq_backtest(panel_local, start, end)
    if not use_dd:
        return bull_raw, bull_raw
    sigs = (pd.DataFrame({"x": 1}, index=bull_raw.index)
            .groupby(pd.Grouper(freq="ME")).tail(1).index.tolist())
    scale = compute_dd_circuit_scale(bull_raw, sigs, DD_CIRCUIT_THRESHOLD, DD_CIRCUIT_SCALE)
    return bull_raw, scale * bull_raw


def summary(label, p):
    m = perf_metrics(p)
    return (label, m["sharpe"], m["cagr"] * 100, m["vol"] * 100, m["max_drawdown"] * 100)


if __name__ == "__main__":
    panel = load_panel(start=pd.Timestamp("1993-01-01"))
    start = pd.Timestamp("2008-04-30")
    end = pd.Timestamp("2026-05-22")

    raw_hyg = fetch_raw_hyg()
    print(f"Raw yfinance HYG: {raw_hyg.shape}, {raw_hyg.index.min().date()} -> {raw_hyg.index.max().date()}")
    print(f"Stitched HYG range in panel: {panel['HYG_stitched'].dropna().index.min().date()} -> {panel['HYG_stitched'].dropna().index.max().date()}")
    print()

    # Canary signal divergence in 2008-2010
    print("HYG mom_13612U comparison at key 2008-2009 monthly signal dates (stitched vs raw):")
    monthly_panel = panel.loc[:end].resample("ME").last()
    test_dates = [pd.Timestamp(d) for d in ["2008-05-30", "2008-08-29", "2008-09-30",
                                              "2008-10-31", "2008-11-28", "2008-12-31",
                                              "2009-01-30", "2009-02-27", "2009-03-31"]]
    for d in test_dates:
        try:
            stitched_m = sig_13612U(panel["HYG_stitched"].loc[:d].resample("ME").last())
        except Exception:
            stitched_m = np.nan
        raw_panel = panel.copy()
        raw_panel["HYG_raw"] = raw_hyg.reindex(panel.index)
        try:
            raw_m = sig_13612U(raw_panel["HYG_raw"].loc[:d].resample("ME").last())
        except Exception:
            raw_m = np.nan
        stitched_sign = "POS" if (pd.notna(stitched_m) and stitched_m > 0) else "NEG"
        raw_sign = "POS" if (pd.notna(raw_m) and raw_m > 0) else "NEG"
        flag = "  <-- DIVERGE" if stitched_sign != raw_sign else ""
        print(f"  {d.date()}: stitched={stitched_m:+.4f} ({stitched_sign}) | raw={raw_m if pd.notna(raw_m) else 'NaN':>9} ({raw_sign}){flag}")
    print()

    rows = []
    # A: current live impl (HYG_stitched)
    raw_s, dd_s = run_bull_with_canary_override(panel, start, end, hyg_series_to_use=None, use_dd=True)
    rows.append(summary("A. BULL-ext (HYG_stitched, sleeve DD)  [live impl]", dd_s))
    rows.append(summary("   - no DD (just canary + asset_mom)", raw_s))
    # B: replace HYG_stitched with raw HYG
    raw_h, dd_h = run_bull_with_canary_override(panel, start, end, hyg_series_to_use=raw_hyg, use_dd=True)
    rows.append(summary("B. BULL-ext (raw yfinance HYG, sleeve DD)", dd_h))
    rows.append(summary("   - no DD (just canary + asset_mom)", raw_h))
    # D: HAA-Simple SPY (TIP only) for reference
    # Use canary override technique: set HYG_stitched to all NaN so canary degenerates to TIP-only via fallback
    # But bull_qqq_live likely treats missing as no-canary; simpler: run with a series of all-negative HYG so HYG never triggers
    nan_hyg = pd.Series(np.nan, index=raw_hyg.index)
    # Actually with all-NaN HYG, the canary checks would return NaN-not-positive, leaving only TIP. Test.
    try:
        raw_d, dd_d = run_bull_with_canary_override(panel, start, end, hyg_series_to_use=nan_hyg, use_dd=True)
        rows.append(summary("D. BULL with NaN HYG (effectively TIP-only) + DD", dd_d))
    except Exception as e:
        rows.append(("D. (skipped: NaN HYG causes error)", 0, 0, 0, 0))

    print("=" * 100)
    print("BULL-ext: stitched vs raw HYG, with/without DD circuit (live cpm_live impl)")
    print("=" * 100)
    print(f"{'Variant':<60} {'Sharpe':>8} {'CAGR':>8} {'Vol':>8} {'MaxDD':>8}")
    print("-" * 100)
    for r in rows:
        print(f"{r[0]:<60} {r[1]:>8.3f} {r[2]:>7.2f}% {r[3]:>7.2f}% {r[4]:>8.2f}%")
    print("=" * 100)
    print()
    print("Critic's reproduction (raw HYG, raw-equity DD): Sharpe 0.99 | CAGR 11.82% | MaxDD -15.61%")
