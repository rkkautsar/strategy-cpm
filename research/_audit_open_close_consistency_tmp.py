"""Throwaway diagnostic for 4.5 audit: open/close adjustment consistency.

Checks:
1. cache Open & Close on same adjustment scale (no raw-open vs adj-close 4-15x bug):
   - max intraday |close/open-1| should be sane (<~25%), no split-day explosions.
2. cache Close vs load_panel adjusted close divergence on rebal days (the only
   point where mooex overrides panel cc with cache cc -> seam magnitude).
3. overnight return open[t]/close[t-1]-1 sane on ex-div days (no fake gaps).
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from cpm_live import load_panel, RISKY_UNIVERSE, SAFE_POOL, CANARY_ASSETS, DEFAULT_CASH

OPEN_CACHE = Path("/tmp/cpm_open_cache")
OHLC = ['SPY','QQQ','SPHQ','EFA','EEM','VNQ','GLD','TLT','DBC','SHV','IEF','HYG','TIP']

opens, closes = {}, {}
for t in OHLC:
    d = pd.read_csv(OPEN_CACHE / f"{t}.csv", parse_dates=[0], index_col=0)
    opens[t], closes[t] = d["Open"], d["Close"]
open_df = pd.DataFrame(opens).sort_index()
close_yf = pd.DataFrame(closes).sort_index()

print("=== CHECK 1: intraday close/open-1 (same-scale test; raw-open bug -> >100%%) ===")
intr = (close_yf / open_df - 1.0)
print(f"{'tkr':<6}{'n':>6}{'max|intra|':>12}{'mean|intra|':>13}{'>30%% days':>11}")
for t in OHLC:
    s = intr[t].dropna()
    big = int((s.abs() > 0.30).sum())
    print(f"{t:<6}{len(s):>6}{s.abs().max()*100:>11.2f}%{s.abs().mean()*100:>12.3f}%{big:>11}")

print("\n=== CHECK 3: overnight open[t]/close[t-1]-1 (ex-div fake-gap test) ===")
ovn = (open_df / close_yf.shift(1) - 1.0)
print(f"{'tkr':<6}{'max|ovn|':>11}{'mean|ovn|':>12}{'>15%% days':>11}")
for t in OHLC:
    s = ovn[t].dropna()
    big = int((s.abs() > 0.15).sum())
    print(f"{t:<6}{s.abs().max()*100:>10.2f}%{s.abs().mean()*100:>11.3f}%{big:>11}")

print("\n=== CHECK 2: panel(adj close) vs cache(yf close) divergence on REBAL days ===")
panel = load_panel(start=pd.Timestamp("1999-03-10"), end=pd.Timestamp("2026-05-22"))
clean_start = pd.Timestamp("2008-05-30")
end = panel.index[-1]
monthly_idx = (pd.DataFrame({"x":1}, index=panel.index).groupby(pd.Grouper(freq="ME")).tail(1))
sigs = monthly_idx.index[(monthly_idx.index>=clean_start)&(monthly_idx.index<=end)]
rebal = []
for sd in sigs:
    fut = panel.index[panel.index>sd]
    if len(fut): rebal.append(fut[0])
rebal = pd.DatetimeIndex(rebal)

# mooex rebal-day return = cache cc = close_yf[af]/close_yf[af-1]-1.
# panel cc baseline      = panel[af]/panel[af-1]-1.
# seam per asset/day = mooex_cc - panel_cc. Aggregate at portfolio scale ~ weight-agnostic worst case.
panel_cc = panel.ffill().pct_change()
cache_cc = close_yf.pct_change().reindex(panel.index)
print(f"{'tkr':<6}{'n_rebal':>8}{'max|seam|bps':>13}{'mean|seam|bps':>14}{'>50bps':>8}")
all_seam = []
for t in OHLC:
    if t not in panel_cc.columns: continue
    a = cache_cc[t].reindex(rebal); b = panel_cc[t].reindex(rebal)
    seam = (a - b).dropna()
    if len(seam)==0: continue
    big = int((seam.abs()>0.005).sum())
    all_seam.append(seam.abs())
    print(f"{t:<6}{len(seam):>8}{seam.abs().max()*1e4:>12.1f}{seam.abs().mean()*1e4:>13.2f}{big:>8}")
alls = pd.concat(all_seam)
print(f"\nPOOLED per-asset rebal-day seam: n={len(alls)} mean={alls.mean()*1e4:.3f}bps "
      f"p99={alls.quantile(0.99)*1e4:.1f}bps max={alls.max()*1e4:.1f}bps")
print("(seam only enters on rebal days for assets actually held; ~216 rebal days clean window)")

print("\n=== CHECK 2b: level ratio cache_close/panel_close on rebal days (should ~1.0 live era) ===")
for t in ["SPY","QQQ","GLD","TLT"]:
    r = (close_yf[t].reindex(rebal) / panel[t].reindex(rebal)).dropna()
    print(f"  {t}: ratio mean={r.mean():.5f} std={r.std():.5f} min={r.min():.5f} max={r.max():.5f}")
