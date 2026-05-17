"""
ETF chain-stitching experiments for FCP factor universe.

Goal: replace short-history factor ETFs with substitute-then-actual chain:
  - Pre-inception: use longer-history substitute (scaled to splice continuously)
  - Post-inception: use actual ETF

Compares vs FCP-15 baseline + drop variants (A3, A4 from prior experiment).
"""
from __future__ import annotations
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import strategy_fcp.fcp_live as fcp
from strategy_fcp.fcp_live import load_panel, run_fcp_backtest

INCEPTION = {
    "AVUV": "2019-09-25",
    "SPMO": "2015-10-09",
    "COWZ": "2016-12-19",
    "MTUM": "2013-04-19",
    "PRF": "2005-12-22",
    "VBR": "2004-01-30",
    "SLYV": "2000-09-25",
}


def chain_stitch(panel, sub_ticker, target_ticker):
    """Multiplicatively scale sub series so prices are continuous at target inception.
    Returns stitched series with sub before target inception, target after.
    """
    if sub_ticker not in panel.columns or target_ticker not in panel.columns:
        return None
    inception = pd.Timestamp(INCEPTION[target_ticker])
    sub = panel[sub_ticker].dropna()
    tgt = panel[target_ticker].dropna()
    # Find first day of target on or after inception
    target_first = tgt.loc[inception:].index.min()
    if pd.isna(target_first):
        return None
    # Find last sub day strictly before target_first
    sub_pre = sub.loc[:target_first - pd.Timedelta(days=1)]
    if sub_pre.empty:
        return tgt
    sub_last_day = sub_pre.index.max()
    sub_last_price = sub.loc[sub_last_day]
    target_first_price = tgt.loc[target_first]
    # Multiplicative scaling so substitute series ends at same level as target's first price
    scale = target_first_price / sub_last_price
    sub_scaled = sub_pre * scale
    # Concatenate: scaled sub + target
    stitched = pd.concat([sub_scaled, tgt.loc[target_first:]])
    stitched = stitched.sort_index()
    return stitched


def metrics_from_daily(daily_ret):
    eq = (1 + daily_ret).cumprod()
    r = daily_ret.dropna()
    if r.empty: return {}
    n_y = len(r) / 252.0
    cagr = eq.iloc[-1] ** (1/n_y) - 1
    vol = r.std() * np.sqrt(252)
    sh = (r.mean()*252) / vol if vol > 0 else np.nan
    dd = (eq / eq.cummax() - 1).min()
    sortino_dn = r[r < 0].std() * np.sqrt(252) if len(r[r<0]) > 1 else np.nan
    sortino = (r.mean()*252) / sortino_dn if sortino_dn and sortino_dn > 0 else np.nan
    calmar = cagr / abs(dd) if dd < 0 else np.nan
    # Pain / Ulcer
    cummax = eq.cummax()
    dds = (eq / cummax - 1) * 100
    pain = -dds.mean()
    ulcer = float(np.sqrt((dds**2).mean()))
    upi = (cagr*100)/ulcer if ulcer > 0 else np.nan
    return dict(cagr=cagr, vol=vol, sharpe=sh, sortino=sortino, calmar=calmar,
                maxdd=dd, pain=pain, upi=upi)


def fmt(label, m, win):
    return (f"  {label:<32s} {win:<10s}  Sh {m['sharpe']:+.3f}  CAGR {m['cagr']*100:+5.2f}%  "
            f"DD {m['maxdd']*100:+6.2f}%  UPI {m['upi']:+5.2f}  Sor {m['sortino']:+.2f}  "
            f"Pain {m['pain']:+.2f}%")


def run_with_universe(panel_modified, risky, start, end, label):
    """Patch fcp.RISKY_UNIVERSE temporarily, run backtest with vol-target ON."""
    saved_risky = fcp.RISKY_UNIVERSE
    saved_aggr = fcp.AGGR_FACTORS
    saved_intl = fcp.INTERNATIONAL
    saved_div = fcp.DIVERSIFIERS
    saved_buf = fcp.HOLD_BUFFER
    fcp.RISKY_UNIVERSE = risky
    # Also override the components for code paths that reference them
    fcp.AGGR_FACTORS = [t for t in risky if t not in ("VEA","VWO","GLD","TLT","EFA","EEM")]
    fcp.INTERNATIONAL = [t for t in risky if t in ("VEA","VWO","EFA","EEM")]
    fcp.DIVERSIFIERS = [t for t in risky if t in ("GLD","TLT")]
    fcp.HOLD_BUFFER = 2.5
    try:
        daily, _ = run_fcp_backtest(panel_modified, start, end, apply_vol_target=True)
        return metrics_from_daily(daily)
    finally:
        fcp.RISKY_UNIVERSE = saved_risky
        fcp.AGGR_FACTORS = saved_aggr
        fcp.INTERNATIONAL = saved_intl
        fcp.DIVERSIFIERS = saved_div
        fcp.HOLD_BUFFER = saved_buf


def main():
    base_panel = load_panel(start=pd.Timestamp("1995-01-01"))
    end = base_panel.index.max()
    hybrid_start = pd.Timestamp("1997-08-31")
    live_start = pd.Timestamp("2008-09-30")

    # Verify substitute ETFs exist in panel
    print("=" * 165)
    print("ETF availability check:")
    for t in ["MTUM", "PRF", "SLYV", "VBR", "AVUV", "SPMO", "COWZ"]:
        if t in base_panel.columns:
            first = base_panel[t].dropna().index.min()
            print(f"  {t:6s}  panel start: {first.date()}")
        else:
            print(f"  {t:6s}  NOT IN PANEL")
    print()

    # Build chain-stitched series
    panel = base_panel.copy()

    print("Chain stitching:")
    for sub, tgt in [("VBR", "AVUV"), ("MTUM", "SPMO"), ("PRF", "COWZ")]:
        stitched = chain_stitch(panel, sub, tgt)
        if stitched is None:
            print(f"  {sub} -> {tgt}: FAILED (missing data)")
            continue
        col = f"{tgt}_stitched"
        panel[col] = stitched
        print(f"  {sub} -> {tgt}: created column '{col}', spans {stitched.index.min().date()} to {stitched.index.max().date()}")
    print()

    BASELINE_RISKY = list(fcp.RISKY_UNIVERSE)
    print(f"Baseline FCP-15: {BASELINE_RISKY}")
    print()

    # Variants
    # CHAIN-STITCH design: each variant replaces ONE slot with stitched series
    # (substitute pre-inception, actual ETF post-inception). Keep all 15 slots.
    # For E1 (VBR/AVUV redundancy), drop the redundant slot entirely.
    variants = {
        "FCP-15 baseline": BASELINE_RISKY,
        "A3 drop AVUV (control)": [t for t in BASELINE_RISKY if t != "AVUV"],

        # E1: drop AVUV slot, replace VBR with stitched (one small-cap-value slot)
        "E1 stitched VBR<->AVUV (drop dup)": [
            ("AVUV_stitched" if t == "VBR" else t)
            for t in BASELINE_RISKY if t != "AVUV"
        ],

        # E2: replace SPMO slot with stitched MTUM->SPMO
        "E2 stitched MTUM<->SPMO": [
            "SPMO_stitched" if t == "SPMO" else t for t in BASELINE_RISKY
        ],

        # E3: replace COWZ slot with stitched PRF->COWZ
        "E3 stitched PRF<->COWZ": [
            "COWZ_stitched" if t == "COWZ" else t for t in BASELINE_RISKY
        ],

        # E4: ALL three stitches combined (drop AVUV, stitch SPMO, COWZ, VBR)
        "E4 ALL stitched (drop AVUV)": [
            ("AVUV_stitched" if t == "VBR" else
             "SPMO_stitched" if t == "SPMO" else
             "COWZ_stitched" if t == "COWZ" else t)
            for t in BASELINE_RISKY if t != "AVUV"
        ],
    }

    print("=" * 165)
    print("RESULTS  (HOLD_BUFFER=2.5, vol-target ON, 10bps/side cost)")
    print("=" * 165)
    rows = []
    for label, risky in variants.items():
        for win_label, start in [("hybrid28y", hybrid_start), ("live18y", live_start)]:
            try:
                m = run_with_universe(panel, risky, start, end, label)
                rows.append((label, win_label, m))
                print(fmt(label, m, win_label))
            except Exception as e:
                print(f"  {label:<32s} {win_label:<10s}  ERR: {e}")

    # Sorted by live18y Sharpe
    print()
    print("=" * 165)
    print("RANKED by Live-only 18y Sharpe (HOLD_BUFFER=2.5)")
    print("=" * 165)
    live_rows = [(r[0], r[2]) for r in rows if r[1] == "live18y"]
    live_rows.sort(key=lambda x: -x[1]["sharpe"])
    base_sh = next((m["sharpe"] for label, m in live_rows if "baseline" in label), 1.095)
    print(f"  {'Variant':<35s}  {'Sharpe':>8s}  {'Δ':>7s}  {'CAGR':>7s}  {'DD':>8s}  {'UPI':>5s}")
    print("  " + "-" * 90)
    for label, m in live_rows:
        d = m["sharpe"] - base_sh
        print(f"  {label:<35s}  {m['sharpe']:>+7.3f}  {d:>+6.3f}  {m['cagr']*100:>+5.2f}%  {m['maxdd']*100:>+6.2f}%  {m['upi']:>+5.2f}")


if __name__ == "__main__":
    main()
