"""Conditional state analysis: GIVEN HYG+ AND TIP+ (strongest base risk-on),
which additional canaries identify the most bullish sub-state?

Already deployed: HYG+TIP "any positive" rule (defensive when both negative).
HYG+ AND TIP+ subset = 134/213 months in live 18y.

Adds one canary at a time and shows which sub-states have:
  - Highest FCP-EW Sharpe
  - Highest hit rate
  - Smallest tail risk

Then tests pairs of extension canaries (most-bullish refinement).
"""
from __future__ import annotations
import sys
from itertools import combinations, product
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fcp_live import RISKY_UNIVERSE, load_panel, sig_13612W  # type: ignore

ALIASES = {"AGG": "AGG_stitched", "HYG": "HYG_stitched"}
EXTRA_CANARIES = ["SPY", "EEM", "EFA", "VEA", "VWO", "GLD", "TLT", "AGG"]


def monthly_panel(panel): return panel.resample("ME").last()

def fcp15_ew(monthly):
    cols = [c for c in RISKY_UNIVERSE if c in monthly.columns]
    return monthly[cols].pct_change().fillna(0).mean(axis=1)


def state_for_set(monthly, canaries):
    cols = {}
    for c in canaries:
        col = ALIASES.get(c, c)
        if col not in monthly.columns:
            return pd.DataFrame()
        sig = pd.Series(index=monthly.index, dtype=float)
        for dt in monthly.index:
            v = sig_13612W(monthly[col].loc[:dt])
            sig.loc[dt] = v if pd.notna(v) else np.nan
        cols[c] = (sig > 0).astype(float)
    return pd.DataFrame(cols, index=monthly.index).dropna().astype(int)


def compute_stats(returns):
    if len(returns) < 5:
        return None
    rv = returns.values
    mean = rv.mean()
    std = rv.std()
    sharpe = (mean * 12) / (std * np.sqrt(12)) if std > 0 else float("nan")
    p10 = float(np.percentile(rv, 10))
    hit = float((rv > 0).mean() * 100)
    return dict(n=len(rv), mean=mean*100, std=std*100, sharpe=sharpe,
                p10=p10*100, hit=hit)


def main():
    out_path = Path(__file__).parent / "canary_substate_under_hyg_tip.log"
    log_lines = []
    def log(s=""):
        log_lines.append(s); print(s)

    log("=" * 110)
    log("CONDITIONAL CANARY ANALYSIS: under HYG+ AND TIP+ (134 months in live 18y)")
    log("Question: which additional canary state identifies the most bullish sub-state?")
    log("=" * 110)

    panel = load_panel(start=pd.Timestamp("1999-01-01"))
    monthly = monthly_panel(panel)
    ew = fcp15_ew(monthly)
    fwd_ew = ew.shift(-1)
    fwd_spy = monthly["SPY"].pct_change().shift(-1)
    fwd_qqq = monthly["QQQ"].pct_change().shift(-1)

    # Filter to HYG+ AND TIP+ in live 18y
    base_state = state_for_set(monthly, ["HYG", "TIP"])
    base_filter = (base_state["HYG"] == 1) & (base_state["TIP"] == 1)
    base_dates = base_state.loc[base_state.index >= pd.Timestamp("2008-09-30")].index
    base_dates = base_dates[base_filter.reindex(base_dates).fillna(False)]
    log(f"\nBase state HYG+TIP+ in live 18y: {len(base_dates)} months")

    base_fwd_ew = fwd_ew.reindex(base_dates).dropna()
    base_fwd_spy = fwd_spy.reindex(base_dates).dropna()
    bs_ew = compute_stats(base_fwd_ew)
    bs_spy = compute_stats(base_fwd_spy)
    log(f"  Base FCP-EW conditional: Sh={bs_ew['sharpe']:+.2f}  mean={bs_ew['mean']:+.2f}%  "
        f"hit={bs_ew['hit']:.0f}%  p10={bs_ew['p10']:+.2f}%")
    log(f"  Base SPY conditional:    Sh={bs_spy['sharpe']:+.2f}  mean={bs_spy['mean']:+.2f}%  "
        f"hit={bs_spy['hit']:.0f}%  p10={bs_spy['p10']:+.2f}%")
    log("")

    log("=" * 110)
    log("ADDING ONE EXTRA CANARY (8 candidates x 2 states = 16 sub-states; show all)")
    log("=" * 110)
    log("")

    results_single = []
    for extra in EXTRA_CANARIES:
        if ALIASES.get(extra, extra) not in monthly.columns:
            continue
        ext_state = state_for_set(monthly, [extra])
        ext_in_base = ext_state.reindex(base_dates).dropna()
        for v in [0, 1]:
            sign = "+" if v else "-"
            mask = (ext_in_base[extra] == v)
            idx = ext_in_base[mask].index
            if len(idx) < 5:
                continue
            r_ew = fwd_ew.reindex(idx).dropna()
            r_spy = fwd_spy.reindex(idx).dropna()
            s_ew = compute_stats(r_ew)
            s_spy = compute_stats(r_spy)
            if s_ew is None:
                continue
            results_single.append((extra, sign, s_ew, s_spy))

    log(f"  {'Extra':<8s}  state  N    FCP_Sh  FCP_m%  FCP_hit  FCP_p10   SPY_Sh  SPY_m%  SPY_hit")
    log("  " + "-" * 95)
    for extra, sign, s_ew, s_spy in sorted(results_single, key=lambda r: -r[2]["sharpe"]):
        log(f"  {extra:<8s}    {sign}    {s_ew['n']:3d}  {s_ew['sharpe']:+5.2f}  "
            f"{s_ew['mean']:+5.2f}  {s_ew['hit']:5.0f}    {s_ew['p10']:+5.2f}    "
            f"{s_spy['sharpe']:+5.2f}  {s_spy['mean']:+5.2f}  {s_spy['hit']:5.0f}")
    log("")

    log("=" * 110)
    log("ADDING TWO EXTRA CANARIES (best ranked by FCP-EW conditional Sharpe, hit>=70%, n>=15)")
    log("=" * 110)
    log("")
    log(f"  {'Extras':<22s}  state    N    FCP_Sh  FCP_m%  FCP_hit  FCP_p10   SPY_Sh  SPY_m%  SPY_hit")
    log("  " + "-" * 105)

    results_pairs = []
    for c1, c2 in combinations(EXTRA_CANARIES, 2):
        if ALIASES.get(c1, c1) not in monthly.columns: continue
        if ALIASES.get(c2, c2) not in monthly.columns: continue
        ext_state = state_for_set(monthly, [c1, c2])
        ext_in_base = ext_state.reindex(base_dates).dropna()
        for v1, v2 in product([0, 1], repeat=2):
            sign1 = "+" if v1 else "-"
            sign2 = "+" if v2 else "-"
            mask = (ext_in_base[c1] == v1) & (ext_in_base[c2] == v2)
            idx = ext_in_base[mask].index
            if len(idx) < 15:
                continue
            r_ew = fwd_ew.reindex(idx).dropna()
            r_spy = fwd_spy.reindex(idx).dropna()
            s_ew = compute_stats(r_ew)
            s_spy = compute_stats(r_spy)
            if s_ew is None or s_ew["hit"] < 70:
                continue
            label = f"{c1}{sign1} {c2}{sign2}"
            results_pairs.append((label, s_ew, s_spy))

    # Top 20 by FCP-EW Sharpe
    for label, s_ew, s_spy in sorted(results_pairs, key=lambda r: -r[1]["sharpe"])[:20]:
        log(f"  {label:<22s}          {s_ew['n']:3d}  {s_ew['sharpe']:+5.2f}  "
            f"{s_ew['mean']:+5.2f}  {s_ew['hit']:5.0f}    {s_ew['p10']:+5.2f}    "
            f"{s_spy['sharpe']:+5.2f}  {s_spy['mean']:+5.2f}  {s_spy['hit']:5.0f}")

    log("")
    log("=" * 110)
    log("BENCHMARK: original X6 (HYG+TIP+EEM+SPY+) -- THIS IS THE PRODUCTION AGGRESSIVE TRIGGER")
    log("=" * 110)
    ext_state = state_for_set(monthly, ["EEM", "SPY"])
    ext_in_base = ext_state.reindex(base_dates).dropna()
    mask = (ext_in_base["EEM"] == 1) & (ext_in_base["SPY"] == 1)
    idx = ext_in_base[mask].index
    r_ew = fwd_ew.reindex(idx).dropna()
    r_spy = fwd_spy.reindex(idx).dropna()
    s_ew = compute_stats(r_ew)
    s_spy = compute_stats(r_spy)
    log(f"  X6 (EEM+ AND SPY+ on top of HYG+TIP+):  N={s_ew['n']}")
    log(f"    FCP-EW: Sh={s_ew['sharpe']:+.2f}  mean={s_ew['mean']:+.2f}%  hit={s_ew['hit']:.0f}%  p10={s_ew['p10']:+.2f}%")
    log(f"    SPY:    Sh={s_spy['sharpe']:+.2f}  mean={s_spy['mean']:+.2f}%  hit={s_spy['hit']:.0f}%  p10={s_spy['p10']:+.2f}%")

    with open(out_path, "w") as f:
        f.write("\n".join(log_lines))
    print(f"\nLog: {out_path}")


if __name__ == "__main__":
    main()
