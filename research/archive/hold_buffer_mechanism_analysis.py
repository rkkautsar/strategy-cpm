#!/usr/bin/env python3
"""Hold Buffer Mechanism Analysis - Fixed: uses actual compute_target_weights with canary."""
from __future__ import annotations
import sys
sys.path.insert(0, "/Users/rkautsar/personal/scripts")

import numpy as np
import pandas as pd
import importlib
from pathlib import Path

import strategy_fcp.fcp_live as fcp_mod
from strategy_fcp.fcp_live import (
    load_panel, faber_sma_xs, sig_13612W, zscore, min_vol_pair, best_safe,
    RISKY_UNIVERSE, SAFE_POOL, CANARY_ASSETS, PP_ASSETS, DEFAULT_CASH,
    TOP_K_CANDIDATES, CORR_LOOKBACK_DAYS,
)

OUT = Path("/Users/rkautsar/personal/scripts/strategy_fcp/research")


def run_holdings_trace(close, start, end, hold_buffer):
    """Run FCP backtest with given HOLD_BUFFER; return holdings per signal date."""
    # Patch HOLD_BUFFER in module
    orig = fcp_mod.HOLD_BUFFER
    fcp_mod.HOLD_BUFFER = hold_buffer

    monthly_idx = pd.DataFrame({"x":1}, index=close.index).groupby(pd.Grouper(freq="ME")).tail(1)
    signal_dates = monthly_idx.index[(monthly_idx.index >= start) & (monthly_idx.index <= end)].tolist()

    holdings = {}
    prev_pair = None
    for sig_d in signal_dates:
        w, new_pair, regime, safe = fcp_mod.compute_target_weights(close, sig_d, prev_pair)
        prev_pair = new_pair
        risky_holdings = tuple(sorted(k for k in w if k not in SAFE_POOL + [DEFAULT_CASH]))
        holdings[sig_d] = {
            "weights": w, "pair": new_pair, "regime": regime,
            "risky": risky_holdings,
        }

    fcp_mod.HOLD_BUFFER = orig
    return holdings


def zscore_distribution_analysis(close):
    monthly = close.resample("ME").last()
    signal_dates = monthly.index[monthly.index >= pd.Timestamp("2008-01-01")]
    rows = []
    for sig_d in signal_dates:
        sub = monthly.loc[:sig_d]
        if len(sub) < 10:
            continue
        score = faber_sma_xs(sub)
        avail = [t for t in RISKY_UNIVERSE if t in score.index and pd.notna(score[t])]
        if len(avail) < 3:
            continue
        sa = score.loc[avail]
        za = zscore(sa)
        sorted_z = za.sort_values(ascending=False).values
        rows.append({
            "date": sig_d, "year": sig_d.year,
            "z_range": sorted_z[0] - sorted_z[-1],
            "gap_top1_top2": sorted_z[0] - sorted_z[1] if len(sorted_z) >= 2 else np.nan,
            "gap_top2_top3": sorted_z[1] - sorted_z[2] if len(sorted_z) >= 3 else np.nan,
            "n_positive_score": (sa > 0).sum(),
        })
    return pd.DataFrame(rows)


def candidate_set_stability(close):
    monthly = close.resample("ME").last()
    signal_dates = monthly.index[monthly.index >= pd.Timestamp("2008-01-01")]
    prev_candidates = None
    rows = []
    for sig_d in signal_dates:
        sub = monthly.loc[:sig_d]
        if len(sub) < 10:
            prev_candidates = None
            continue
        score = faber_sma_xs(sub)
        avail = [t for t in RISKY_UNIVERSE if t in score.index and pd.notna(score[t])]
        if not avail:
            continue
        sa = score.loc[avail]
        ranked = sa.sort_values(ascending=False)
        top_k = max(2, min(TOP_K_CANDIDATES, len(ranked)))
        positive = set(ranked.iloc[:top_k][lambda s: s > 0].index)
        if prev_candidates is not None:
            union = positive | prev_candidates
            j = len(positive & prev_candidates) / len(union) if union else 1.0
            rows.append({
                "date": sig_d, "year": sig_d.year,
                "jaccard_similarity": j,
                "n_new_entrants": len(positive - prev_candidates),
            })
        prev_candidates = positive
    return pd.DataFrame(rows)


def reconstruct_decision_detail(close, sig_d, prev_pair_2z, prev_pair_3z):
    """Get exact z-scores and gap for a signal date under each buffer."""
    monthly = close.loc[:sig_d].resample("ME").last()
    score = faber_sma_xs(monthly)
    avail = [t for t in RISKY_UNIVERSE if t in score.index and pd.notna(score[t])
             and sig_d in close.index and pd.notna(close.loc[sig_d].get(t, np.nan))]
    if not avail:
        return None
    sa = score.loc[avail]
    za = zscore(sa)
    ranked = sa.sort_values(ascending=False)
    top_k = max(2, min(TOP_K_CANDIDATES, len(ranked)))
    positive = ranked.iloc[:top_k][lambda s: s > 0]
    if len(positive) < 2:
        return None
    candidates = list(positive.index)
    new_pick_raw = min_vol_pair(close.loc[:sig_d, candidates], candidates, CORR_LOOKBACK_DAYS)
    if new_pick_raw is None:
        return None

    decisions = {}
    for buf_val, prev_pair in [(2.0, prev_pair_2z), (3.0, prev_pair_3z)]:
        new_set = list(new_pick_raw)
        dec_list = []
        if prev_pair is not None:
            for prior in prev_pair:
                if prior in new_set or prior not in avail:
                    continue
                if sa.get(prior, -np.inf) <= 0:
                    continue
                z_prior = za.get(prior, np.nan)
                if pd.isna(z_prior):
                    continue
                swap_cands = [x for x in new_set if x not in prev_pair]
                if not swap_cands:
                    continue
                swap = min(swap_cands, key=lambda x: za.get(x, np.inf))
                z_swap = za.get(swap, np.nan)
                if pd.isna(z_swap):
                    continue
                gap = z_swap - z_prior
                kept = gap < buf_val
                dec_list.append({
                    "prior": prior, "z_prior": round(z_prior, 3),
                    "swap": swap, "z_swap": round(z_swap, 3),
                    "gap": round(gap, 3), "kept": kept,
                })
                if kept:
                    new_set.remove(swap)
                    new_set.append(prior)
        decisions[buf_val] = dec_list

    top_z = za.sort_values(ascending=False).head(5)

    return {
        "unconstrained": tuple(sorted(new_pick_raw)),
        "faber_top5": sa.sort_values(ascending=False).head(7).to_dict(),
        "z_top5": top_z.to_dict(),
        "decisions_2z": decisions[2.0],
        "decisions_3z": decisions[3.0],
        "positive_candidates": list(positive.index),
    }


def ps(title):
    print("\n" + "=" * 100)
    print(f"  {title}")
    print("=" * 100)


def main():
    print("Loading price panel...")
    panel = load_panel(start=pd.Timestamp("2006-01-01"), end=pd.Timestamp("2026-05-31"))
    cols = sorted(set(RISKY_UNIVERSE + SAFE_POOL + CANARY_ASSETS + PP_ASSETS + [DEFAULT_CASH]) & set(panel.columns))
    close = panel[cols]
    print(f"Panel: {close.shape}, {close.index[0].date()} to {close.index[-1].date()}")

    LIVE_START = pd.Timestamp("2008-09-01")
    LIVE_END   = pd.Timestamp("2026-05-31")

    print("Running 2z backtest...")
    h2z = run_holdings_trace(close, LIVE_START, LIVE_END, 2.0)
    print("Running 3z backtest...")
    h3z = run_holdings_trace(close, LIVE_START, LIVE_END, 3.0)

    monthly_close = close.resample("ME").last()

    # =========================================================================
    # SECTION 1: z-gap at each diverging month
    # =========================================================================
    ps("SECTION 1: Diverging months — exact z-gaps at decision")

    all_dates = sorted(set(h2z.keys()) & set(h3z.keys()))
    diff_dates = [d for d in all_dates if h2z[d]["risky"] != h3z[d]["risky"]]
    same_dates = [d for d in all_dates if h2z[d]["risky"] == h3z[d]["risky"]]

    print(f"\n  Total signal months: {len(all_dates)}")
    print(f"  Differing months: {len(diff_dates)}")
    print(f"  Same months: {len(same_dates)}")
    print()
    print(f"  {'Date':<12} {'Unconstrained':>14} {'2z final':>16} {'3z final':>16}  z-gap detail")
    print("  " + "-" * 110)

    # Reconstruct exact z-gaps by re-running with separate state tracking
    prev_2z_pair = None; prev_3z_pair = None
    prev_2z_pair_from_trace = None; prev_3z_pair_from_trace = None

    pair_state_2z = {}
    pair_state_3z = {}
    for d in all_dates:
        pair_state_2z[d] = h2z[d]["pair"]
        pair_state_3z[d] = h3z[d]["pair"]

    for i, sig_d in enumerate(diff_dates):
        h2 = h2z[sig_d]; h3 = h3z[sig_d]
        prev_d = all_dates[all_dates.index(sig_d) - 1] if all_dates.index(sig_d) > 0 else None
        prev_2z = pair_state_2z.get(prev_d) if prev_d else None
        prev_3z = pair_state_3z.get(prev_d) if prev_d else None

        detail = reconstruct_decision_detail(close, sig_d, prev_2z, prev_3z)
        unc = "/".join(sorted(detail["unconstrained"])) if detail else "?"
        h2_str = "/".join(h2["risky"]) if h2["risky"] else dict(h2["weights"]).keys().__str__()
        h3_str = "/".join(h3["risky"]) if h3["risky"] else "defensive"

        gap_str = ""
        if detail:
            for dec in detail["decisions_3z"]:
                if dec["kept"] and dec["gap"] >= 2.0:
                    gap_str = f"3z KEPT {dec['prior']}(z={dec['z_prior']:.2f}) vs {dec['swap']}(z={dec['z_swap']:.2f}), gap={dec['gap']:.3f}"
            if not gap_str:
                for dec in detail["decisions_3z"]:
                    if dec["kept"]:
                        gap_str = f"3z KEPT {dec['prior']}(z={dec['z_prior']:.2f}) vs {dec['swap']}(z={dec['z_swap']:.2f}), gap={dec['gap']:.3f}"
            if not gap_str and detail["decisions_2z"]:
                d2 = detail["decisions_2z"][0]
                gap_str = f"2z dec: {d2['prior']}({d2['z_prior']:.2f}) vs {d2['swap']}({d2['z_swap']:.2f}), gap={d2['gap']:.3f}"

        print(f"  {sig_d.strftime('%Y-%m-%d'):<12} {unc:>14} {h2_str:>16} {h3_str:>16}  {gap_str}")

    # =========================================================================
    # SECTION 2: Next-month returns
    # =========================================================================
    ps("SECTION 2: Next-month returns — what each buffer earned")
    print(f"\n  {'Month':<10} {'Regime':>8} {'2z R%':>8} {'3z R%':>8} {'Diff':>7}  Asset returns (key)")
    print("  " + "-" * 110)

    for sig_d in diff_dates:
        h2 = h2z[sig_d]; h3 = h3z[sig_d]
        next_months = monthly_close.index[monthly_close.index > sig_d]
        if len(next_months) < 1:
            continue
        nxt = next_months[0]

        key_a = list(set(list(h2["risky"]) + list(h3["risky"])) | {"TLT","GLD","SPHQ","QQQ","IGM","XMHQ"})
        rets = {}
        for a in key_a:
            if a in monthly_close.columns:
                p0 = monthly_close.loc[sig_d, a] if sig_d in monthly_close.index else np.nan
                p1 = monthly_close.loc[nxt, a] if nxt in monthly_close.index else np.nan
                if pd.notna(p0) and pd.notna(p1) and p0 > 0:
                    rets[a] = (p1 / p0 - 1) * 100

        r2 = np.nanmean([rets.get(a, np.nan) for a in h2["risky"]]) if h2["risky"] else 0.0
        r3 = np.nanmean([rets.get(a, np.nan) for a in h3["risky"]]) if h3["risky"] else 0.0
        diff_r = r3 - r2
        astr = "  ".join(f"{a}={rets.get(a,np.nan):+.1f}%" for a in sorted(key_a) if a in rets)
        regime = h2["regime"]
        print(f"  {sig_d.strftime('%Y-%m'):<10} {regime:>8} {r2:>+7.2f}% {r3:>+7.2f}% {diff_r:>+6.2f}%  {astr}")

    # =========================================================================
    # SECTION 3: z-score distribution over time
    # =========================================================================
    ps("SECTION 3: Faber z-score distribution — by year")
    zdist = zscore_distribution_analysis(close)
    yearly = zdist.groupby("year").agg(
        z_range=("z_range","mean"),
        gap_top1_top2=("gap_top1_top2","mean"),
        gap_top2_top3=("gap_top2_top3","mean"),
        n_positive=("n_positive_score","mean"),
    ).round(3)
    print(f"\n  {'Year':<6} {'z_range':>9} {'gap1v2':>8} {'gap2v3':>8} {'n_pos':>7}")
    print("  " + "-" * 46)
    for yr, row in yearly.iterrows():
        m = " ◄" if yr >= 2015 else ""
        print(f"  {yr:<4}  {row['z_range']:>8.3f} {row['gap_top1_top2']:>8.3f} {row['gap_top2_top3']:>8.3f} {row['n_positive']:>7.1f}{m}")
    for label, y0, y1 in [("2008-2014",2008,2014),("2015-2019",2015,2019),("2020-2026",2020,2026)]:
        sub = zdist[(zdist["year"]>=y0)&(zdist["year"]<=y1)]
        print(f"\n  {label}: avg z_range={sub['z_range'].mean():.3f}  gap1v2={sub['gap_top1_top2'].mean():.3f}  gap2v3={sub['gap_top2_top3'].mean():.3f}  n_pos={sub['n_positive'].mean():.1f}")

    # =========================================================================
    # SECTION 4: Candidate set stability
    # =========================================================================
    ps("SECTION 4: Candidate set stability (Jaccard month-over-month)")
    stab = candidate_set_stability(close)
    yearly_stab = stab.groupby("year").agg(
        jaccard_similarity=("jaccard_similarity","mean"),
        n_new_entrants=("n_new_entrants","mean"),
    ).round(3)
    print(f"\n  {'Year':<6} {'Jaccard':>9} {'NewEntrants/mo':>16}")
    print("  " + "-" * 36)
    for yr, row in yearly_stab.iterrows():
        m = " ◄" if yr >= 2015 else ""
        print(f"  {yr:<4}  {row['jaccard_similarity']:>8.3f} {row['n_new_entrants']:>16.2f}{m}")
    for label, y0, y1 in [("2008-2014",2008,2014),("2015-2019",2015,2019),("2020-2026",2020,2026)]:
        sub = stab[(stab["year"]>=y0)&(stab["year"]<=y1)]
        print(f"\n  {label}: avg jaccard={sub['jaccard_similarity'].mean():.3f}  avg new_entrants/mo={sub['n_new_entrants'].mean():.2f}")

    # =========================================================================
    # SECTION 5: Regime context for differing months
    # =========================================================================
    ps("SECTION 5: Regime context — are differing months in transitions?")
    diff_years = pd.Series([d.year for d in diff_dates])
    print(f"\n  Differing months by year:")
    for yr, cnt in diff_years.value_counts().sort_index().items():
        months = [d.strftime('%Y-%m') for d in diff_dates if d.year == yr]
        print(f"    {yr}: {cnt} months — {months}")

    # =========================================================================
    # SECTION 6: IGM vs GLD 2009-2010 returns
    # =========================================================================
    ps("SECTION 6: 2009-2010 cross-section — IGM vs GLD (the 6-month period)")
    a6 = [a for a in ["IGM","QQQ","GLD","TLT","SPHQ","SPY","SHV"] if a in monthly_close.columns]
    r6 = monthly_close.loc["2009-01":"2010-04", a6].pct_change().dropna() * 100
    print(f"\n  {'Date':<10}", end="")
    for a in a6: print(f"  {a:>7}", end="")
    print()
    print("  " + "-" * (12 + 9*len(a6)))
    for dt, row in r6.iterrows():
        flag = " ← DIFF" if dt in [d for d in diff_dates if d.year in (2009,2010)] else ""
        print(f"  {dt.strftime('%Y-%m'):<10}", end="")
        for a in a6: print(f"  {row.get(a,np.nan):>+7.2f}", end="")
        print(flag)
    ph = monthly_close.loc["2009-07":"2010-02", a6]
    if len(ph) > 1:
        cum = (ph / ph.iloc[0] - 1) * 100
        print(f"\n  Cumulative Aug 2009 – Feb 2010 (the hold window):")
        for a in a6: print(f"    {a}: {cum[a].iloc[-1]:+.1f}%")

    # =========================================================================
    # SECTION 7: 2012 returns
    # =========================================================================
    ps("SECTION 7: 2012 — SPHQ/TLT(3z) vs QQQ/GLD/SPHQ(2z)")
    a7 = [a for a in ["SPHQ","TLT","QQQ","GLD","XMHQ","IGM","SPY"] if a in monthly_close.columns]
    r7 = monthly_close.loc["2012-01":"2013-03", a7].pct_change().dropna() * 100
    print(f"\n  {'Date':<10}", end="")
    for a in a7: print(f"  {a:>7}", end="")
    print()
    print("  " + "-" * (12 + 9*len(a7)))
    for dt, row in r7.iterrows():
        flag = " ← DIFF" if dt in [d for d in diff_dates if d.year == 2012] else ""
        print(f"  {dt.strftime('%Y-%m'):<10}", end="")
        for a in a7: print(f"  {row.get(a,np.nan):>+7.2f}", end="")
        print(flag)

    # =========================================================================
    # SECTION 8: 2020 COVID
    # =========================================================================
    ps("SECTION 8: 2019-12/2020-01 — GLD/TLT(3z) vs GLD/SPHQ(2z)")
    a8 = [a for a in ["GLD","TLT","SPHQ","QQQ","SPY","IEF","SHV"] if a in monthly_close.columns]
    r8 = monthly_close.loc["2019-10":"2020-06", a8].pct_change().dropna() * 100
    print(f"\n  {'Date':<10}", end="")
    for a in a8: print(f"  {a:>7}", end="")
    print()
    print("  " + "-" * (12 + 9*len(a8)))
    for dt, row in r8.iterrows():
        flag = " ← DIFF" if dt in [d for d in diff_dates if d.year in (2019,2020)] else ""
        print(f"  {dt.strftime('%Y-%m'):<10}", end="")
        for a in a8: print(f"  {row.get(a,np.nan):>+7.2f}", end="")
        print(flag)

    # =========================================================================
    # SECTION 9: 2011 (the single diverging month)
    # =========================================================================
    ps("SECTION 9: 2011-06 anomaly — what caused it?")
    diff_2011 = [d for d in diff_dates if d.year == 2011]
    if diff_2011:
        for sig_d in diff_2011:
            print(f"\n  {sig_d.strftime('%Y-%m-%d')}:")
            print(f"    2z held: {h2z[sig_d]['risky']}")
            print(f"    3z held: {h3z[sig_d]['risky']}")
            detail = reconstruct_decision_detail(close, sig_d,
                h2z[all_dates[all_dates.index(sig_d)-1]]["pair"] if all_dates.index(sig_d) > 0 else None,
                h3z[all_dates[all_dates.index(sig_d)-1]]["pair"] if all_dates.index(sig_d) > 0 else None)
            if detail:
                print(f"    Unconstrained: {detail['unconstrained']}")
                print(f"    Top Faber scores: {dict(list(detail['faber_top5'].items())[:5])}")
                print(f"    Top z-scores: {dict(list(detail['z_top5'].items())[:5])}")
                print(f"    Decisions 3z: {detail['decisions_3z']}")
                print(f"    Decisions 2z: {detail['decisions_2z']}")
    else:
        print("  No 2011 differing months found in this run.")

    ps("COMPLETE")


if __name__ == "__main__":
    main()
