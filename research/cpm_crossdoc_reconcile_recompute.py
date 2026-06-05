"""Recompute CPM sleeve under both conventions to reconcile memo vs README.

memo/harness path: mooex T+1 exact via cpm_harness (anchor 1.255673).
README/dashboard path: close-to-close T+1 via cpm_live.run_cpm_backtest.
Both: clean window 2008-05-30..2026-05-22, both-252, 10 bps/side, frozen data.
"""
from pathlib import Path
import sys
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import cpm_live
from cpm_live import load_panel, run_cpm_backtest, perf_metrics, EVAL_END
from research import cpm_harness

CLEAN_START = pd.Timestamp("2008-05-30")
END = pd.Timestamp("2026-05-22")

print("CORR_LOOKBACK_DAYS =", cpm_live.CORR_LOOKBACK_DAYS)
print("EVAL_END =", EVAL_END)
print()

# ---- A) harness mooex path (memo anchor) ----
d = cpm_harness.load_data(end=END, clean_start=CLEAN_START)
print("harness data end:", d.end, "clean_start:", d.clean_start)
got = cpm_harness.verify_anchor(data=d)
print("HARNESS verify_anchor (mooex, memo):")
for k, v in got.items():
    print(f"  {k:8s} {v}")
print()

# ---- B) run_cpm_backtest path (README/dashboard) ----
panel = load_panel(start=pd.Timestamp("1999-03-10"), end=END, live=False)
print("panel last:", panel.index[-1])
cash = panel[cpm_live.DEFAULT_CASH].ffill().pct_change()
cpm_rets, _ = run_cpm_backtest(panel, CLEAN_START, END)
cpm_clean = cpm_rets.loc[(cpm_rets.index >= CLEAN_START) & (cpm_rets.index <= END)]
m = perf_metrics(cpm_clean, cash)
print("RUN_CPM_BACKTEST (close-to-close, README/dashboard):")
for k in ("sharpe", "excess_sharpe", "cagr", "vol", "max_drawdown", "calmar", "martin"):
    print(f"  {k:14s} {m.get(k)}")
print("  first/last:", cpm_clean.index[0].date(), cpm_clean.index[-1].date(), "n=", len(cpm_clean))
