"""
Comprehensive audit of FCP-15 risky universe (post-XLV-add, post-AVUV-drop).

For each asset:
  1. Role / factor exposure (qualitative)
  2. Selection frequency by FCP (% of months in pair)
  3. Top pair partners (which other assets it's most often paired with)
  4. Average correlation to other risky assets
  5. Live history availability
"""
from __future__ import annotations
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import strategy_fcp.fcp_live as fcp
from strategy_fcp.fcp_live import (
    load_panel, run_fcp_backtest, compute_target_weights,
    RISKY_UNIVERSE, AGGR_FACTORS, INTERNATIONAL, DIVERSIFIERS,
)


# Asset role / factor classification
ROLES = {
    "QQQ":  "US Large-cap Growth/Tech (NASDAQ-100)",
    "IGM":  "US Expanded Tech Sector (broader tech)",
    "SPMO": "US Large-cap Momentum (S&P 500 Momentum)",
    "XLE":  "US Energy Sector",
    "XRT":  "US Retail Sector",
    "COWZ": "US Free Cash Flow Yield (Cash Cows 100)",
    "VBR":  "US Small-cap Value",
    "SPHQ": "US Large-cap Quality",
    "XMMO": "US Mid-cap Momentum",
    "XMHQ": "US Mid-cap Quality",
    "XLV":  "US Healthcare Sector (defensive growth)",
    "VEA":  "International Developed Equity",
    "VWO":  "Emerging Markets Equity",
    "GLD":  "Gold (inflation hedge / equity diversifier)",
    "TLT":  "Long US Treasury (rate / deflation hedge)",
}

INCEPTION = {
    "QQQ": "1999-03-10", "IGM": "2001-03-13", "SPMO": "2015-10-09",
    "XLE": "1998-12-22", "XRT": "2006-06-22", "COWZ": "2016-12-19",
    "VBR": "2004-01-30", "SPHQ": "2005-12-09", "XMMO": "2005-03-10",
    "XMHQ": "2005-12-09", "XLV": "1998-12-22", "VEA": "2007-07-20",
    "VWO": "2005-03-04", "GLD": "2004-11-18", "TLT": "2002-07-22",
}


def get_eom(panel, start, end):
    idx = panel.loc[start:end].index
    return list(pd.Series(idx).groupby(idx.to_period("M")).last())


def main():
    panel = load_panel(start=pd.Timestamp("1995-01-01"))
    end = panel.index.max()
    hybrid_start = pd.Timestamp("1997-08-31")
    live_start = pd.Timestamp("2008-09-30")

    # 1. Replay FCP and capture pair holdings each month
    print("Replaying FCP to capture pair holdings (live-only window)...")
    eom_dates = get_eom(panel, live_start, end)
    pair_history = []
    prev_pair = None
    for d in eom_dates:
        try:
            w, new_pair, regime, _ = compute_target_weights(panel, d, prev_pair)
            pair_history.append((d, w, new_pair, regime))
            prev_pair = new_pair
        except Exception:
            pair_history.append((d, {}, None, "ERR"))

    # Filter to risk-on months (those with a pair)
    risk_on = [(d, w, pair, regime) for d, w, pair, regime in pair_history if pair is not None]
    n_risk_on = len(risk_on)
    n_total = len(pair_history)

    print(f"\nWindow: {live_start.date()} to {end.date()}")
    print(f"Total months: {n_total}, risk-on months: {n_risk_on} ({n_risk_on/n_total*100:.0f}%)")

    # 2. Selection frequency per asset
    asset_picks = Counter()
    for _, _, pair, _ in risk_on:
        for a in pair:
            asset_picks[a] += 1

    # 3. Pair partner frequency
    partners = defaultdict(Counter)  # asset -> Counter(other -> count)
    for _, _, pair, _ in risk_on:
        a, b = list(pair)
        partners[a][b] += 1
        partners[b][a] += 1

    # 4. Correlation matrix on live data
    returns = panel[RISKY_UNIVERSE].loc[live_start:end].pct_change().dropna()
    corr = returns.corr()

    # 5. Print full audit
    print("\n" + "=" * 130)
    print(f"FCP-{len(RISKY_UNIVERSE)} UNIVERSE AUDIT (live-only 18y, post-XLV/post-AVUV)")
    print("=" * 130)
    print(f"\n{'Asset':<6} {'Role':<48} {'Live':<12} {'Picks':>8} {'%RiskOn':>9} {'AvgCorr':>9} {'TopPartner':<20}")
    print("-" * 130)

    rows = []
    for asset in RISKY_UNIVERSE:
        n_picks = asset_picks.get(asset, 0)
        pct = n_picks / n_risk_on * 100 if n_risk_on > 0 else 0
        avg_c = (corr[asset].sum() - 1) / (len(RISKY_UNIVERSE) - 1)
        top_partners = partners[asset].most_common(3)
        top_str = ", ".join(f"{p}({c})" for p, c in top_partners) if top_partners else "-"
        role = ROLES.get(asset, "?")
        live = INCEPTION.get(asset, "?")
        rows.append((asset, role, live, n_picks, pct, avg_c, top_str))
        print(f"{asset:<6} {role:<48} {live:<12} {n_picks:>8} {pct:>8.1f}% {avg_c:>+8.3f} {top_str:<20}")

    # 6. Sort by selection frequency
    print("\n" + "=" * 130)
    print("SORTED BY SELECTION FREQUENCY (most-picked first)")
    print("=" * 130)
    rows_by_picks = sorted(rows, key=lambda r: -r[3])
    print(f"\n{'Asset':<6}  {'%RiskOn':>9}  {'AvgCorr':>8}  Role")
    for asset, role, live, picks, pct, avg_c, _ in rows_by_picks:
        bar = "#" * int(pct / 2)
        print(f"{asset:<6}  {pct:>8.1f}%  {avg_c:>+7.3f}  {bar} {role}")

    # 7. Top 10 most-frequent pairs
    print("\n" + "=" * 130)
    print("TOP 15 MOST-FREQUENT PAIRS")
    print("=" * 130)
    pair_counter = Counter()
    for _, _, pair, _ in risk_on:
        pair_counter[frozenset(pair)] += 1
    for pair, count in pair_counter.most_common(15):
        a, b = sorted(list(pair))
        pct = count / n_risk_on * 100
        c = corr.loc[a, b]
        print(f"  {a:>5} + {b:<5}  picked {count:>3} months ({pct:>4.1f}%)  corr={c:+.3f}  {ROLES.get(a, '?')[:30]} | {ROLES.get(b, '?')[:30]}")

    # 8. Ungrouped pairs by category (E-E, E-D, D-D)
    EQUITIES = {"QQQ","IGM","SPMO","XLE","XRT","COWZ","VBR","SPHQ","XMMO","XMHQ","XLV","VEA","VWO"}
    DEFENSIVES = {"GLD","TLT"}

    cats = {"E+E":0, "E+D":0, "D+D":0, "other":0}
    for _, _, pair, _ in risk_on:
        a, b = list(pair)
        ka = "E" if a in EQUITIES else ("D" if a in DEFENSIVES else "?")
        kb = "E" if b in EQUITIES else ("D" if b in DEFENSIVES else "?")
        key = "+".join(sorted([ka, kb]))
        if key in cats: cats[key] += 1
        else: cats["other"] += 1

    print("\n" + "=" * 130)
    print("PAIR COMPOSITION BY CATEGORY")
    print("=" * 130)
    for k, v in cats.items():
        if v == 0: continue
        print(f"  {k}: {v} months ({v/n_risk_on*100:.1f}%)")
    print(f"  Total risk-on: {n_risk_on}")

    # 9. Defensive months breakdown
    defensive_count = sum(1 for _, _, pair, regime in pair_history if pair is None)
    print(f"\n  DEFENSIVE (canary blocked, 100% safe): {defensive_count} months ({defensive_count/n_total*100:.1f}%)")

    # 10. Assets that NEVER get picked
    never_picked = [a for a in RISKY_UNIVERSE if asset_picks.get(a, 0) == 0]
    if never_picked:
        print(f"\n  ASSETS NEVER PICKED: {never_picked}")


if __name__ == "__main__":
    main()
