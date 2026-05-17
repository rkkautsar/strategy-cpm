"""Sweep TSMOM momentum-function variants on AGGR universe."""
import sys
sys.path.insert(0, "/Users/rkautsar/personal/scripts/strategy_cam")

import numpy as np
import pandas as pd
from aggr_core import (
    AGGRESSIVE_TICKERS, SAFE_ASSETS, download_prices,
    month_end_rebalance_dates, perf_metrics,
)
from aggr_benchmark import _segment_returns, align_curves, compute_summary, run_spy_bh

UNIVERSE = AGGRESSIVE_TICKERS
CASH = "SHV"

start = pd.Timestamp("2008-01-01")
end = pd.Timestamp.today().normalize()
tickers = sorted(set(UNIVERSE + SAFE_ASSETS + ["SPY"]))
download_start = start - pd.DateOffset(years=5)
print(f"Downloading {len(tickers)} tickers...")
close = download_prices(tickers=tickers, start=download_start, end=end, cache_path="/tmp/yfinance_aggr_cache")


# ---- TSMOM signal generators ----
# Each returns a Series of bool/float per asset; True = "in trend" / hold.

def sig_12m_sign(monthly: pd.DataFrame) -> pd.Series:
    """Classic Moskowitz: 12m total return > 0."""
    if len(monthly) < 13: return pd.Series(False, index=monthly.columns)
    r12 = monthly.iloc[-1] / monthly.iloc[-13] - 1.0
    return r12 > 0

def sig_12_1_sign(monthly: pd.DataFrame) -> pd.Series:
    """12m skip-1 sign (industry-standard, removes 1m reversal)."""
    if len(monthly) < 14: return pd.Series(False, index=monthly.columns)
    r = monthly.iloc[-2] / monthly.iloc[-14] - 1.0
    return r > 0

def sig_6m_sign(monthly: pd.DataFrame) -> pd.Series:
    """Faster 6m trend."""
    if len(monthly) < 7: return pd.Series(False, index=monthly.columns)
    r = monthly.iloc[-1] / monthly.iloc[-7] - 1.0
    return r > 0

def sig_3m_sign(monthly: pd.DataFrame) -> pd.Series:
    """Very fast 3m trend."""
    if len(monthly) < 4: return pd.Series(False, index=monthly.columns)
    r = monthly.iloc[-1] / monthly.iloc[-4] - 1.0
    return r > 0

def sig_multi_lookback_avg(monthly: pd.DataFrame) -> pd.Series:
    """Avg of 3/6/9/12m sign (Hurst/AQR-style multi-horizon)."""
    if len(monthly) < 13: return pd.Series(False, index=monthly.columns)
    sigs = []
    for lb in (3, 6, 9, 12):
        if len(monthly) > lb:
            r = monthly.iloc[-1] / monthly.iloc[-lb-1] - 1.0
            sigs.append((r > 0).astype(float))
    avg = pd.concat(sigs, axis=1).mean(axis=1)
    return avg >= 0.5  # majority

def sig_sma200(daily_close: pd.DataFrame) -> pd.Series:
    """Faber-style: price > 200-day SMA."""
    if len(daily_close) < 200: return pd.Series(False, index=daily_close.columns)
    sma = daily_close.rolling(200).mean().iloc[-1]
    last = daily_close.iloc[-1]
    return last > sma

def sig_sma10m(monthly: pd.DataFrame) -> pd.Series:
    """Faber-style monthly: price > 10-month SMA."""
    if len(monthly) < 10: return pd.Series(False, index=monthly.columns)
    sma = monthly.rolling(10).mean().iloc[-1]
    return monthly.iloc[-1] > sma

def sig_above_cash(monthly: pd.DataFrame) -> pd.Series:
    """12m return > cash (SHV) 12m return."""
    if len(monthly) < 13: return pd.Series(False, index=monthly.columns)
    r = monthly.iloc[-1] / monthly.iloc[-13] - 1.0
    cash_r = r.get(CASH, 0.0)
    return r > cash_r

def sig_breakout_252(daily_close: pd.DataFrame) -> pd.Series:
    """Donchian-style: price near 252d high (within 5%)."""
    if len(daily_close) < 252: return pd.Series(False, index=daily_close.columns)
    hi = daily_close.rolling(252).max().iloc[-1]
    last = daily_close.iloc[-1]
    return (last / hi) >= 0.95


SIGNALS = {
    "TSMOM_12m":         (sig_12m_sign, "monthly"),
    "TSMOM_12_1":        (sig_12_1_sign, "monthly"),
    "TSMOM_6m":          (sig_6m_sign, "monthly"),
    "TSMOM_3m":          (sig_3m_sign, "monthly"),
    "TSMOM_MultiLB":     (sig_multi_lookback_avg, "monthly"),
    "TSMOM_SMA200d":     (sig_sma200, "daily"),
    "TSMOM_SMA10m":      (sig_sma10m, "monthly"),
    "TSMOM_AboveCash":   (sig_above_cash, "monthly"),
    "TSMOM_Breakout252": (sig_breakout_252, "daily"),
}


def run_tsmom_variant(close: pd.DataFrame, sig_fn, mode: str, universe: list[str], cash: str = CASH) -> pd.Series:
    dates = month_end_rebalance_dates(close.index, start, end)
    monthly = close.resample("ME").last()
    weights_map = {}
    for d in dates:
        if mode == "monthly":
            sig = sig_fn(monthly.loc[:d])
        else:
            sig = sig_fn(close.loc[:d])
        avail_in_universe = [t for t in universe if pd.notna(close.loc[d].get(t, np.nan))]
        survivors = [t for t in avail_in_universe if bool(sig.get(t, False))]
        if not survivors:
            if cash in close.columns and pd.notna(close.loc[d].get(cash, np.nan)):
                weights_map[d] = {cash: 1.0}
            else:
                weights_map[d] = {}
            continue
        w = 1.0 / len(survivors)
        weights_map[d] = {t: w for t in survivors}
    return _segment_returns(close, weights_map, dates, end)


results = {}
for name, (fn, mode) in SIGNALS.items():
    print(f"Running {name}...")
    results[name] = run_tsmom_variant(close, fn, mode, UNIVERSE)

print("Running SPY_BH...")
results["SPY_BH"] = run_spy_bh(close, start, end)["daily"]

aligned, equity = align_curves(results, 100_000.0)
summary = compute_summary(aligned, equity)
print()
print(f"Window: {aligned.index[0].date()} -> {aligned.index[-1].date()}")
print(summary.to_string(index=False, float_format=lambda x: f"{x:.4f}"))
summary.to_csv("/tmp/tsmom_variants_summary.csv", index=False)
equity.to_csv("/tmp/tsmom_variants_equity.csv")

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(11, 6))
    for col in equity.columns:
        ax.plot(equity.index, equity[col], label=col, linewidth=1.0)
    ax.set_yscale("log")
    ax.set_title(f"TSMOM signal variants on AGGR universe ({equity.index[0].date()}–{equity.index[-1].date()})")
    ax.legend(fontsize=8, loc="upper left")
    ax.grid(True, which="both", alpha=0.3)
    fig.tight_layout()
    fig.savefig("/tmp/tsmom_variants_equity.png", dpi=120)
    print("Wrote /tmp/tsmom_variants_equity.png")
except Exception as e:
    print(f"Plot skipped: {e}")
