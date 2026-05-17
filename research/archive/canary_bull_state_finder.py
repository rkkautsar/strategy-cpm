"""Find the most reliably bullish canary state for aggressive overlay deployment.

For each 2-canary and 3-canary combination, enumerate states and rank by:
  - Conditional FCP-EW Sharpe
  - Hit rate (forward 21d > 0)
  - Conditional mean
  - Tail safety (p10)
  - Sample size (n)

Output: top "green-light" states across all canary sets, ranked by composite
"bull confidence" score.

Definition of "good bull state":
  - Hit rate >= 75% (rarely negative)
  - Conditional Sharpe (annualized) >= 1.5
  - p10 (worst 10% forward month) > -5% (no deep tail)
  - n >= 15 (statistically reliable)
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
CANDIDATES = ["SPY", "TIP", "HYG", "AGG", "EFA", "EEM", "GLD", "TLT", "VEA", "VWO"]


def monthly_panel(panel: pd.DataFrame) -> pd.DataFrame:
    return panel.resample("ME").last()


def fcp15_ew(monthly: pd.DataFrame) -> pd.Series:
    cols = [c for c in RISKY_UNIVERSE if c in monthly.columns]
    return monthly[cols].pct_change().fillna(0).mean(axis=1)


def state_for_set(monthly: pd.DataFrame, canaries: list[str]) -> pd.DataFrame:
    """Returns DataFrame with bool cols per canary, indexed by signal date."""
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
    df = pd.DataFrame(cols, index=monthly.index).dropna()
    return df.astype(int)


def main():
    out_path = Path(__file__).parent / "canary_bull_state_finder.log"
    log_lines = []
    def log(s=""):
        log_lines.append(s); print(s)

    log("=" * 110)
    log("SEARCHING FOR THE MOST 'GREEN-LIGHT' CANARY STATE (for aggressive/leveraged overlay)")
    log("Criteria for shortlist:  hit% >= 75  AND  conditional Sh >= 1.5  AND  p10 >= -5%  AND  n >= 15")
    log("=" * 110)

    panel = load_panel(start=pd.Timestamp("1998-01-01"))
    log(f"Panel: {panel.index[0].date()} -> {panel.index[-1].date()}")
    log("")

    monthly = monthly_panel(panel)
    ew = fcp15_ew(monthly)
    fwd_ew = ew.shift(-1)  # forward 1mo
    fwd_spy = monthly["SPY"].pct_change().shift(-1) if "SPY" in monthly.columns else None
    fwd_qqq = monthly["QQQ"].pct_change().shift(-1) if "QQQ" in monthly.columns else None

    avail_cands = [c for c in CANDIDATES if ALIASES.get(c, c) in monthly.columns]
    log(f"Available canary candidates: {avail_cands}")
    log("")

    all_rows = []

    # Iterate all 1, 2, 3-canary sets (skip 4+ to keep readable)
    for n in [1, 2, 3]:
        for cset in combinations(avail_cands, n):
            cset = list(cset)
            states = state_for_set(monthly, cset)
            if states.empty:
                continue
            # Restrict to live window for primary analysis (data quality)
            live = states.loc[states.index >= pd.Timestamp("2008-09-30")]
            if len(live) < 50:
                continue
            for combo in product([0, 1], repeat=n):
                label = "/".join(["+" if v else "-" for v in combo])
                mask = (live == list(combo)).all(axis=1)
                idx = mask[mask].index
                if len(idx) < 15:
                    continue
                r_ew = fwd_ew.reindex(idx).dropna()
                if len(r_ew) < 15:
                    continue
                mean = float(r_ew.mean())
                std = float(r_ew.std())
                sharpe = (mean * 12) / (std * np.sqrt(12)) if std > 0 else float("nan")
                p10 = float(np.percentile(r_ew, 10))
                hit = float((r_ew > 0).mean() * 100)
                # SPY conditional
                r_spy = fwd_spy.reindex(idx).dropna() if fwd_spy is not None else None
                spy_hit = float((r_spy > 0).mean() * 100) if r_spy is not None else None
                spy_mean = float(r_spy.mean() * 100) if r_spy is not None else None
                # QQQ conditional
                r_qqq = fwd_qqq.reindex(idx).dropna() if fwd_qqq is not None else None
                qqq_hit = float((r_qqq > 0).mean() * 100) if r_qqq is not None else None
                qqq_mean = float(r_qqq.mean() * 100) if r_qqq is not None else None
                # Filter criteria
                if hit < 75 or sharpe < 1.5 or p10 < -5 or len(r_ew) < 15:
                    continue
                all_rows.append({
                    "canaries": "+".join(cset),
                    "state": label,
                    "n": len(r_ew),
                    "FCP_Sh": sharpe,
                    "FCP_mean%": mean * 100,
                    "FCP_hit%": hit,
                    "FCP_p10%": p10 * 100,
                    "SPY_mean%": spy_mean,
                    "SPY_hit%": spy_hit,
                    "QQQ_mean%": qqq_mean,
                    "QQQ_hit%": qqq_hit,
                })

    if not all_rows:
        log("No states matched criteria!")
        with open(out_path, "w") as f:
            f.write("\n".join(log_lines))
        return

    df = pd.DataFrame(all_rows)

    # Show top 20 by FCP-EW Sharpe
    log("=" * 110)
    log("TOP 25 GREEN-LIGHT STATES (live 2008-2026, ranked by FCP-EW conditional Sharpe)")
    log("=" * 110)
    log("")
    log(f"  {'canary set':<20s}  state         N    FCP_Sh  FCP_m%  FCP_hit  FCP_p10  SPY_m%  SPY_hit  QQQ_m%  QQQ_hit")
    log("  " + "-" * 108)
    top = df.sort_values("FCP_Sh", ascending=False).head(25)
    for _, r in top.iterrows():
        log(f"  {r['canaries']:<20s}  {r['state']:<11s}  {int(r['n']):3d}  "
            f"{r['FCP_Sh']:+5.2f}  {r['FCP_mean%']:+5.2f}  {r['FCP_hit%']:5.0f}    {r['FCP_p10%']:+5.2f}    "
            f"{r['SPY_mean%']:+5.2f}   {r['SPY_hit%']:5.0f}   {r['QQQ_mean%']:+5.2f}   {r['QQQ_hit%']:5.0f}")
    log("")

    # Also rank by hit rate (true "never down" signal)
    log("=" * 110)
    log("TOP 15 BY HIT RATE (states almost never negative)")
    log("=" * 110)
    log("")
    log(f"  {'canary set':<20s}  state         N    FCP_hit  SPY_hit  QQQ_hit  FCP_Sh  FCP_m%")
    log("  " + "-" * 105)
    by_hit = df.sort_values("FCP_hit%", ascending=False).head(15)
    for _, r in by_hit.iterrows():
        log(f"  {r['canaries']:<20s}  {r['state']:<11s}  {int(r['n']):3d}  "
            f"{r['FCP_hit%']:5.0f}    {r['SPY_hit%']:5.0f}    {r['QQQ_hit%']:5.0f}    "
            f"{r['FCP_Sh']:+5.2f}  {r['FCP_mean%']:+5.2f}")
    log("")

    # Composite score: hit% * Sh / (1 + |p10|) — reward consistency, penalize tails
    df["composite"] = df["FCP_hit%"] * df["FCP_Sh"] / (1 + abs(df["FCP_p10%"]))
    log("=" * 110)
    log("TOP 15 BY COMPOSITE (hit% * Sh / (1+|p10|))")
    log("=" * 110)
    log("")
    log(f"  {'canary set':<20s}  state         N    composite  FCP_hit  FCP_Sh  FCP_m%  FCP_p10")
    log("  " + "-" * 105)
    by_comp = df.sort_values("composite", ascending=False).head(15)
    for _, r in by_comp.iterrows():
        log(f"  {r['canaries']:<20s}  {r['state']:<11s}  {int(r['n']):3d}  "
            f"{r['composite']:7.2f}   {r['FCP_hit%']:5.0f}    {r['FCP_Sh']:+5.2f}  "
            f"{r['FCP_mean%']:+5.2f}   {r['FCP_p10%']:+5.2f}")
    log("")

    log(f"Total states matching shortlist criteria: {len(df)}")
    with open(out_path, "w") as f:
        f.write("\n".join(log_lines))
    print(f"\nLog: {out_path}")


if __name__ == "__main__":
    main()
