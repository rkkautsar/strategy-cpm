#!/usr/bin/env python3
"""Universe audit: pick frequency + liquidity + slippage."""
from __future__ import annotations
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

ROOT = Path("/Users/rkautsar/personal/scripts")
sys.path.insert(0, str(ROOT / "strategy_fcp"))

from fcp_live import (
    AGGR_FACTORS, DIVERSIFIERS, RISKY_UNIVERSE, SAFE_POOL, CANARY_ASSETS,
    PP_ASSETS, load_panel, run_fcp_backtest,
)

START = pd.Timestamp("2001-08-30")
END = pd.Timestamp.today().normalize()
TRADE_SIZES = [10_000, 50_000, 250_000]


def classify_ticker(t: str) -> str:
    if t in AGGR_FACTORS: return "AGGR factor"
    if t in DIVERSIFIERS: return "diversifier"
    if t in SAFE_POOL: return "safe"
    return "other"


def compute_pick_freq(panel: pd.DataFrame, start, end):
    print("Running FCP backtest for pick frequency ...")
    _, weights_history = run_fcp_backtest(panel, start, end)
    counts = {}; weight_sums = {}
    total_months = len(weights_history)
    for h in weights_history:
        for ticker, w in h["weights"].items():
            counts[ticker] = counts.get(ticker, 0) + 1
            weight_sums[ticker] = weight_sums.get(ticker, 0.0) + w
    rows = []
    for t in counts:
        rows.append({
            "ticker": t, "category": classify_ticker(t),
            "months_picked": counts[t], "pick_pct": 100.0 * counts[t] / total_months,
            "avg_weight_when_picked": weight_sums[t] / counts[t],
            "avg_weight_total": weight_sums[t] / total_months,
        })
    for t in RISKY_UNIVERSE + SAFE_POOL:
        if t not in counts:
            rows.append({"ticker": t, "category": classify_ticker(t),
                         "months_picked": 0, "pick_pct": 0.0,
                         "avg_weight_when_picked": 0.0, "avg_weight_total": 0.0})
    df = pd.DataFrame(rows).sort_values("pick_pct", ascending=False)
    print(f"Total months: {total_months}")
    return df, total_months


def fetch_liquidity_stats(tickers):
    rows = []
    for t in tickers:
        print(f"  Fetching {t} ...")
        try:
            tk = yf.Ticker(t)
            info = tk.info
            try:
                fi = tk.fast_info
                last_price = float(fi.get("last_price", info.get("previousClose", np.nan) or np.nan))
            except Exception:
                last_price = info.get("previousClose", np.nan) or np.nan
            aum = (info.get("totalAssets") or info.get("netAssets") or
                   info.get("totalAssetsValue") or np.nan)
            avg_vol = (info.get("averageVolume") or
                       info.get("averageDailyVolume3Month") or
                       info.get("averageVolume10days") or np.nan)
            bid = info.get("bid", np.nan); ask = info.get("ask", np.nan)
            spread_pct = np.nan
            if bid and ask and bid > 0 and ask > 0:
                spread_pct = (ask - bid) / ((bid + ask) / 2) * 100
            adv_dollar = (avg_vol * last_price) if (pd.notna(avg_vol) and pd.notna(last_price)) else np.nan
            rows.append({"ticker": t, "last_price": last_price, "aum_usd": aum,
                         "avg_volume_3m": avg_vol, "adv_dollar": adv_dollar,
                         "bid_ask_spread_pct": spread_pct})
        except Exception as e:
            print(f"    error: {e}")
            rows.append({"ticker": t, "last_price": np.nan, "aum_usd": np.nan,
                         "avg_volume_3m": np.nan, "adv_dollar": np.nan, "bid_ask_spread_pct": np.nan})
    return pd.DataFrame(rows)


def estimate_slippage(row, trade_size_usd):
    """Slippage estimate (bps per side).
    Sanity rules:
      - For very high-volume ETFs (>$100M ADV), assume tight 1-3 bp spread
        regardless of yfinance bid/ask reading (which is often stale or 0).
      - For low-AUM/low-ADV ETFs, trust larger reported spreads.
    """
    spread = row.get("bid_ask_spread_pct", np.nan)
    adv = row.get("adv_dollar", np.nan)
    aum = row.get("aum_usd", np.nan)
    
    # Cap spread for liquid ETFs - yfinance bid/ask data is often unreliable
    # for very liquid names that just happened to print far apart at the snapshot
    if pd.notna(adv) and adv > 1e9:  # >$1B ADV = always tight in reality
        if pd.isna(spread) or spread > 0.05:
            spread = 0.01  # 1 bp
    elif pd.notna(adv) and adv > 1e8:  # $100M-1B ADV
        if pd.isna(spread) or spread > 0.10:
            spread = 0.02  # 2 bp
    elif pd.isna(spread) or spread <= 0:
        spread = 0.10  # default 10bps for unknown
    
    half_spread_bps = spread * 100 / 2
    
    if pd.isna(adv) or adv <= 0:
        return half_spread_bps + 50.0
    pct_of_adv = trade_size_usd / adv * 100
    if pct_of_adv < 0.1:    impact_bps = 0.5
    elif pct_of_adv < 1.0:  impact_bps = 2.0
    elif pct_of_adv < 5.0:  impact_bps = 8.0
    elif pct_of_adv < 20.0: impact_bps = 25.0
    else:                   impact_bps = 100.0
    return half_spread_bps + impact_bps


def fmt_money(v):
    if pd.isna(v): return "?"
    if v >= 1e9: return f"${v/1e9:.2f}B"
    if v >= 1e6: return f"${v/1e6:.0f}M"
    if v >= 1e3: return f"${v/1e3:.0f}K"
    return f"${v:.0f}"

def fmt_int(v):
    if pd.isna(v): return "?"
    return f"{v:,.0f}"


def main():
    print("Loading panel ...")
    panel = load_panel(start=START, end=END)
    print(f"Panel: {panel.index[0].date()} -> {panel.index[-1].date()}, {len(panel.columns)} assets\n")
    
    freq_df, total_months = compute_pick_freq(panel, START, END)
    
    print("\nFetching liquidity stats ...")
    all_tickers = sorted(set(RISKY_UNIVERSE + SAFE_POOL + CANARY_ASSETS + PP_ASSETS))
    liq_df = fetch_liquidity_stats(all_tickers)
    
    for size in TRADE_SIZES:
        liq_df[f"slip_bps_{size//1000}K"] = liq_df.apply(lambda r: estimate_slippage(r, size), axis=1)
    
    full = freq_df.merge(liq_df, on="ticker", how="outer").sort_values("pick_pct", ascending=False)
    
    print()
    print("=" * 120)
    print(f"FCP UNIVERSE AUDIT - {total_months} months ({START.date()} -> {END.date()})")
    print("=" * 120)
    print()
    print(f"{'Ticker':<8} {'Cat':<12} {'Pick%':>6} {'AvgWt':>6} {'Price':>8} {'AUM':>9} {'AvgVol3m':>14} {'ADV$':>10} {'Spd%':>6} {'S10K':>6} {'S50K':>6} {'S250K':>7}")
    print("-" * 120)
    for _, r in full.iterrows():
        print(f"{r['ticker']:<8} {r.get('category', '-'):<12} "
              f"{r.get('pick_pct', 0):>5.1f}% {r.get('avg_weight_when_picked', 0)*100:>5.0f}% "
              f"{r.get('last_price', float('nan')):>8.2f} "
              f"{fmt_money(r.get('aum_usd')):>9} "
              f"{fmt_int(r.get('avg_volume_3m')):>14} "
              f"{fmt_money(r.get('adv_dollar')):>10} "
              f"{r.get('bid_ask_spread_pct', float('nan')):>5.2f}% "
              f"{r.get('slip_bps_10K', float('nan')):>5.1f}b "
              f"{r.get('slip_bps_50K', float('nan')):>5.1f}b "
              f"{r.get('slip_bps_250K', float('nan')):>6.1f}b")
    
    print()
    print("=" * 120)
    print("DROP CANDIDATES (pick rate < 5%)")
    print("=" * 120)
    drops = full[(full["pick_pct"] < 5) & (full["category"] == "AGGR factor")]
    if len(drops):
        for _, r in drops.iterrows():
            slip_50k = r.get("slip_bps_50K", float("nan"))
            print(f"  {r['ticker']}: picked {r['pick_pct']:.1f}% of months, slippage at $50K = {slip_50k:.1f}bps")
    else:
        print("  None - all factor ETFs picked >= 5% of months")
    
    print()
    print("=" * 120)
    print("LIQUIDITY WARNINGS (slippage at $50K > 15 bps)")
    print("=" * 120)
    illiq = full[full["slip_bps_50K"] > 15]
    if len(illiq):
        for _, r in illiq.iterrows():
            print(f"  {r['ticker']:<8} (cat: {r.get('category','-'):<12}): slip $50K = {r['slip_bps_50K']:.1f}bps, AUM={fmt_money(r['aum_usd'])}, ADV={fmt_money(r['adv_dollar'])}")
    else:
        print("  None")
    
    full.to_csv("/tmp/fcp_universe_audit.csv", index=False)
    print(f"\nSaved: /tmp/fcp_universe_audit.csv")
    
    print()
    print("=" * 120)
    print("STRATEGY-LEVEL SLIPPAGE DRAG (weighted by pick freq + avg weight)")
    print("=" * 120)
    monthly_turnover_pct = 60
    for size_label in ["10K", "50K", "250K"]:
        slip_col = f"slip_bps_{size_label}"
        valid = full.dropna(subset=[slip_col, "avg_weight_total"])
        wt = valid["avg_weight_total"]
        if wt.sum() == 0: continue
        weighted_slip = (valid[slip_col] * wt).sum() / wt.sum()
        annual_drag_pct = (monthly_turnover_pct / 100) * weighted_slip * 2 * 12 / 10000 * 100
        print(f"  Trade size ${size_label}: avg ~{weighted_slip:.1f}bps/side, annual drag ~{annual_drag_pct:.2f}%/yr")


if __name__ == "__main__":
    main()
