"""Canary 2^n state analysis.

For each canary set, enumerate all 2^n binary states (positive/negative per
canary by 13612W), then for each state compute forward 21d (1mo) stats for
SPY, QQQ, IEF, GLD, FCP-15 equal-weight: mean, median, hit rate, std.

User can then DESIGN the risk-on/risk-off rule from the data rather than
assume "all-positive = risk-on".

Iterative: start SPY+TIP, then test adding one canary at a time:
  - International: EFA, EEM
  - Diversifier: GLD, SHV, AGG
  - Credit: HYG (if data avail)
  - Bond breadth: TLT
"""
from __future__ import annotations

import sys
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

# Add strategy_fcp to path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fcp_live import RISKY_UNIVERSE, load_panel, sig_13612W  # type: ignore


# ---- Config ----

# AGG -> AGG_stitched, HYG -> HYG_stitched (VWEHX pre-2007 + live HYG post)
CANARY_ALIASES = {"AGG": "AGG_stitched", "HYG": "HYG_stitched"}

CANARY_CANDIDATES = ["SPY", "TIP", "EFA", "EEM", "GLD", "SHV", "AGG",
                     "HYG", "TLT", "VWO", "VEA", "BND"]

WATCH_ASSETS = ["SPY", "QQQ", "IEF", "GLD", "TLT", "FCP15_EW"]

# Canary sets to test (iterative)
CANARY_SETS = [
    ["SPY", "TIP"],                  # current baseline
    ["SPY", "TIP", "EFA"],           # + international developed
    ["SPY", "TIP", "EEM"],           # + emerging
    ["SPY", "TIP", "VEA"],           # + international (VEA, EFA alt)
    ["SPY", "TIP", "GLD"],           # + gold canary
    ["SPY", "TIP", "AGG"],           # + agg bonds (DAA-inspired)
    ["SPY", "TIP", "HYG"],           # + credit (HYG)
    ["SPY", "TIP", "TLT"],           # + long bonds (yield-curve adjacent)
    # 4-canary
    ["SPY", "TIP", "EFA", "AGG"],
    ["SPY", "TIP", "EEM", "HYG"],
    # Pure literature
    ["EEM", "AGG"],                  # DAA original
    ["SPY", "EEM", "EFA", "AGG"],    # VAA-G4 / BAA canary
    # HYG paired with each single canary (find HYG's best partner)
    ["HYG"],                         # HYG alone
    ["HYG", "TIP"],                  # HYG + TIP
    ["HYG", "SPY"],                  # HYG + SPY
    ["HYG", "AGG"],                  # HYG + AGG
    ["HYG", "EEM"],                  # HYG + EEM
    ["HYG", "GLD"],                  # HYG + GLD (curiosity)
    ["HYG", "TLT"],                  # HYG + TLT (bond breadth)
]


def monthly_panel(panel: pd.DataFrame) -> pd.DataFrame:
    """Convert daily panel to month-end."""
    return panel.resample("ME").last()


def fcp15_ew_monthly(monthly: pd.DataFrame) -> pd.Series:
    """Equal-weight monthly return of FCP-15 universe."""
    cols = [c for c in RISKY_UNIVERSE if c in monthly.columns]
    rets = monthly[cols].pct_change().fillna(0)
    return rets.mean(axis=1)


def fwd_1mo_returns(monthly: pd.DataFrame, asset: str) -> pd.Series:
    """Forward 1-month return for an asset, indexed by signal date (t)."""
    if asset == "FCP15_EW":
        ew = fcp15_ew_monthly(monthly)
        # ew.iloc[t] is the return DURING month t. We want forward from signal t.
        return ew.shift(-1)
    if asset not in monthly.columns:
        return pd.Series(dtype=float)
    monthly_ret = monthly[asset].pct_change()
    return monthly_ret.shift(-1)


def canary_states(monthly: pd.DataFrame, canaries: list[str]) -> pd.DataFrame:
    """Return DataFrame indexed by signal-date with one bool column per canary
    (1 if 13612W > 0, else 0). Months with any missing canary are dropped."""
    out = {}
    for c in canaries:
        if c not in monthly.columns:
            print(f"  WARN: canary {c} not in panel, skipping set")
            return pd.DataFrame()
        s = monthly[c].apply(lambda x: x)  # placeholder
        # Compute 13612W on the price series
        sig_series = pd.Series(index=monthly.index, dtype=float)
        for i, dt in enumerate(monthly.index):
            window = monthly[c].loc[:dt]
            try:
                v = sig_13612W(window)
                sig_series.iloc[i] = v
            except Exception:
                sig_series.iloc[i] = np.nan
        out[c] = (sig_series > 0).astype(int)
    df = pd.DataFrame(out, index=monthly.index)
    df = df.dropna()
    return df


def state_label(row: pd.Series) -> str:
    """Convert bool row to '+/+/-/' style label."""
    return "/".join(["+" if v else "-" for v in row])


def analyze_set(monthly: pd.DataFrame, canaries: list[str],
                start: pd.Timestamp = None, end: pd.Timestamp = None) -> pd.DataFrame:
    """For each 2^n state, compute fwd-1mo stats per WATCH_ASSETS."""
    states = canary_states(monthly, canaries)
    if states.empty:
        return pd.DataFrame()
    if start is not None:
        states = states.loc[states.index >= start]
    if end is not None:
        states = states.loc[states.index <= end]
    # Build forward returns for each watch asset
    fwd = {a: fwd_1mo_returns(monthly, a) for a in WATCH_ASSETS}

    state_strs = states.apply(state_label, axis=1)

    rows = []
    n = len(canaries)
    # Enumerate all 2^n states; include empty buckets too
    for combo in product([0, 1], repeat=n):
        label = "/".join(["+" if v else "-" for v in combo])
        mask = (state_strs == label)
        n_months = int(mask.sum())
        row = {"state": label, "n_months": n_months}
        if n_months == 0:
            for a in WATCH_ASSETS:
                row[f"{a}_mean%"] = np.nan
                row[f"{a}_med%"] = np.nan
                row[f"{a}_hit%"] = np.nan
                row[f"{a}_std%"] = np.nan
            rows.append(row)
            continue
        idx = mask[mask].index
        for a in WATCH_ASSETS:
            r = fwd[a].reindex(idx).dropna()
            if len(r) == 0:
                for k in ["mean%", "med%", "std%", "sharpe", "sortino", "p10%", "hit%", "WL", "skew"]:
                    row[f"{a}_{k}"] = np.nan
            else:
                rv = r.values
                mean = float(rv.mean())
                std = float(rv.std())
                downside = rv[rv < 0]
                dstd = float(downside.std()) if len(downside) > 1 else float("nan")
                wins = rv[rv > 0]
                losses = rv[rv < 0]
                wl = (float(wins.mean()) / -float(losses.mean())
                       if len(wins) > 0 and len(losses) > 0 else float("nan"))
                # Annualize Sharpe/Sortino (12 monthly periods)
                sharpe = (mean * 12) / (std * np.sqrt(12)) if std > 0 else float("nan")
                sortino = (mean * 12) / (dstd * np.sqrt(12)) if not np.isnan(dstd) and dstd > 0 else float("nan")
                skew = float(pd.Series(rv).skew()) if len(rv) >= 3 else float("nan")
                row[f"{a}_mean%"] = mean * 100
                row[f"{a}_med%"] = float(np.median(rv)) * 100
                row[f"{a}_std%"] = std * 100
                row[f"{a}_sharpe"] = sharpe
                row[f"{a}_sortino"] = sortino
                row[f"{a}_p10%"] = float(np.percentile(rv, 10)) * 100
                row[f"{a}_hit%"] = float((rv > 0).mean() * 100)
                row[f"{a}_WL"] = wl
                row[f"{a}_skew"] = skew
        rows.append(row)
    df = pd.DataFrame(rows).sort_values("n_months", ascending=False)
    return df


def fmt_table(df: pd.DataFrame, canaries: list[str], focus_asset: str = "FCP15_EW") -> str:
    """Show full distribution metrics for the focus_asset across all states."""
    if df.empty:
        return "(no data)\n"
    header_state = "/".join(canaries)
    state_w = max(len(header_state), 10)
    lines = []
    lines.append(f"  Focus asset: {focus_asset}")
    lines.append(f"  {'State (' + header_state + ')':<{state_w+10}}  N    mean%   med%   std%  Sharpe  Sortino   p10%   hit%    W/L  skew")
    lines.append(f"  {'-'*120}")
    for _, r in df.iterrows():
        if r["n_months"] == 0:
            continue
        a = focus_asset
        lines.append(
            f"  {r['state']:>{state_w}}  "
            f"{int(r['n_months']):3d}  "
            f"{r[f'{a}_mean%']:+6.2f}  {r[f'{a}_med%']:+6.2f}  {r[f'{a}_std%']:5.2f}  "
            f"{r[f'{a}_sharpe']:+6.2f}  {r[f'{a}_sortino']:+7.2f}  "
            f"{r[f'{a}_p10%']:+6.2f}  {r[f'{a}_hit%']:5.1f}  {r[f'{a}_WL']:5.2f}  {r[f'{a}_skew']:+5.2f}"
        )
    return "\n".join(lines) + "\n"


def fmt_compact_per_asset(df: pd.DataFrame, canaries: list[str]) -> str:
    """Compact: per-state Sharpe across all watch assets for quick scan."""
    if df.empty:
        return "(no data)\n"
    header_state = "/".join(canaries)
    state_w = max(len(header_state), 10)
    lines = []
    lines.append(f"  Conditional ANNUALIZED Sharpe per state:")
    lines.append(f"  {'State (' + header_state + ')':<{state_w+10}}  N    SPY    QQQ    IEF    GLD    TLT   FCP-EW")
    lines.append(f"  {'-'*90}")
    for _, r in df.iterrows():
        if r["n_months"] == 0:
            continue
        vals = [r[f"{a}_sharpe"] for a in WATCH_ASSETS]
        line = f"  {r['state']:>{state_w}}  {int(r['n_months']):3d}  "
        line += "  ".join(f"{v:+5.2f}" for v in vals)
        lines.append(line)
    return "\n".join(lines) + "\n"


def main():
    out_path = Path(__file__).parent / "canary_state_2n_analysis.log"
    log_lines = []

    def log(s: str = ""):
        log_lines.append(s)
        print(s)

    log("=" * 100)
    log("CANARY 2^n STATE ANALYSIS")
    log(f"Watch assets: {WATCH_ASSETS}")
    log(f"Signal: 13612W = (12*r1 + 4*r3 + 2*r6 + r12) / 19  (>0 = positive)")
    log(f"Forward window: 21 trading days (~1 calendar month)")
    log("=" * 100)
    log("")

    panel = load_panel(start=pd.Timestamp("1998-01-01"))
    log(f"Panel: {panel.index[0].date()} -> {panel.index[-1].date()}, {len(panel.columns)} assets")

    # Check availability
    missing = [c for c in CANARY_CANDIDATES if c not in panel.columns]
    if missing:
        log(f"Missing canary candidates from panel: {missing}")
    avail = [c for c in CANARY_CANDIDATES if c in panel.columns]
    log(f"Available canary candidates: {avail}")
    log("")

    monthly = monthly_panel(panel)
    log(f"Monthly panel: {len(monthly)} months ({monthly.index[0].date()} -> {monthly.index[-1].date()})")
    log("")

    # Two windows
    windows = [
        ("FULL 2001-2026", pd.Timestamp("2001-08-30"), None),
        ("LIVE 2008-2026", pd.Timestamp("2008-09-30"), None),
    ]

    for cset in CANARY_SETS:
            # Apply aliases (e.g. AGG -> AGG_stitched)
        cset_resolved = [CANARY_ALIASES.get(c, c) for c in cset]
        cset_display = cset
        missing_in_set = [c for c in cset_resolved if c not in monthly.columns]
        if missing_in_set:
            log(f"\n--- Canary set {cset} SKIPPED (missing: {missing_in_set}) ---\n")
            continue

        log("")
        log("#" * 100)
        log(f"# Canary set: {cset_display}  (2^{len(cset_display)} = {2**len(cset_display)} states)")
        log("#" * 100)
        log("")

        for wlabel, wstart, wend in windows:
            df = analyze_set(monthly, cset_resolved, start=wstart, end=wend)
            log(f"--- {wlabel} ---")
            log(fmt_table(df, cset_display, focus_asset="FCP15_EW"))
            log(fmt_compact_per_asset(df, cset_display))

            non_empty = df[df["n_months"] > 0]
            if not non_empty.empty:
                # Sort states by FCP-EW conditional Sharpe (best gating metric)
                log("  States ranked by FCP15_EW conditional Sharpe (best risk-on candidates first):")
                ranked = non_empty.sort_values("FCP15_EW_sharpe", ascending=False)
                for _, rr in ranked.iterrows():
                    log(f"    state={rr['state']}  N={int(rr['n_months']):3d}  "
                        f"FCP-EW Sh={rr['FCP15_EW_sharpe']:+.2f}  "
                        f"mean={rr['FCP15_EW_mean%']:+.2f}%  "
                        f"std={rr['FCP15_EW_std%']:.2f}%  "
                        f"p10={rr['FCP15_EW_p10%']:+.2f}%  hit={rr['FCP15_EW_hit%']:.0f}%")
                log("")

    log("=" * 100)
    log("DONE")
    log("=" * 100)

    with open(out_path, "w") as f:
        f.write("\n".join(log_lines))
    print(f"\nLog written: {out_path}")


if __name__ == "__main__":
    main()
