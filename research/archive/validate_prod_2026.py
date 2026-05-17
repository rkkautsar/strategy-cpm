"""
Validation of NEW PRODUCTION design (May 2026):
  70% FCP + 30% MAX-TOP2 (12-1 momentum eligibility, top-2 Faber rank,
  HYG/TIP+VIX<35 macro gate, SHV cash fallback)

Tests:
  1. Block bootstrap CI on production blend Sharpe/CAGR/MaxDD (live + extended)
  2. Walk-forward filter robustness: 12-1 momentum vs Faber 10mo vs no-filter,
     rolling 5y OOS windows starting 2010
  3. VIX threshold sensitivity: 25/30/35/40/no-cap on production blend
  4. Universe sensitivity: drop one ticker at a time from BULL_UNIVERSE
  5. Blend ratio sensitivity: 50/50 -> 100/0 FCP/MAX-TOP2

Output: research/validate_prod_2026.log
"""
import sys, os
sys.path.insert(0, "/Users/rkautsar/personal/scripts/strategy_fcp")

import numpy as np
import pandas as pd
from fcp_live import load_panel, perf_metrics, run_fcp_backtest
import max_fcp_live as mfl

np.random.seed(42)

LOG_PATH = "/Users/rkautsar/personal/scripts/strategy_fcp/research/validate_prod_2026.log"
log_f = open(LOG_PATH, "w")

def log(s=""):
    print(s, flush=True)
    log_f.write(s + "\n"); log_f.flush()

def covid_dd(d):
    sub = d.loc["2020-01-01":"2020-08-01"]
    if sub.empty: return 0
    eq = (1+sub).cumprod(); rm = eq.rolling(63, min_periods=20).max()
    return float((eq/rm-1).min()*100)

def stats(d):
    if d.empty or len(d) < 10: return dict(sharpe=0, cagr=0, max_drawdown=0)
    yrs = len(d)/252
    eq = (1+d).cumprod()
    return dict(
        sharpe=d.mean()*252/(d.std()*np.sqrt(252)) if d.std()>0 else 0,
        cagr=eq.iloc[-1]**(1/yrs)-1 if yrs>0 else 0,
        max_drawdown=(eq/eq.cummax()-1).min(),
    )

def faber_dist(s, sd, n=10):
    sd_s = s.loc[:sd].dropna()
    if len(sd_s) < n: return float("nan")
    return (sd_s.iloc[-1] - sd_s.iloc[-n:].mean()) / sd_s.iloc[-n:].mean()

def momentum_12(s, sd):
    sd_s = s.loc[:sd].dropna()
    if len(sd_s) < 13: return float("nan")
    return sd_s.iloc[-1] / sd_s.iloc[-13] - 1


# Load panel
log("Loading panel ...")
panel = load_panel(start=pd.Timestamp("1995-01-01"))
log(f"Panel: {panel.index[0].date()} -> {panel.index[-1].date()}, {len(panel.columns)} assets\n")

LIVE_START = pd.Timestamp("2008-09-30")
EXT_START = pd.Timestamp("1997-08-30")
END = panel.index[-1]


# =========================================================================
# 1. BLOCK BOOTSTRAP CI on production blend
# =========================================================================
def block_bootstrap_ci(returns, n_boot=2000, block_size=21, seed=42):
    """Block-bootstrap of daily returns. Returns dict of (lo, hi, point) for each metric."""
    rng = np.random.default_rng(seed)
    n = len(returns)
    n_blocks = (n + block_size - 1) // block_size
    rets_arr = returns.values
    sharpes, cagrs, dds = [], [], []
    for _ in range(n_boot):
        starts = rng.integers(0, n - block_size, size=n_blocks)
        idx = np.concatenate([np.arange(s, s + block_size) for s in starts])[:n]
        boot = pd.Series(rets_arr[idx])
        sharpes.append(boot.mean()*252/(boot.std()*np.sqrt(252)) if boot.std()>0 else 0)
        eq = (1+boot).cumprod()
        cagrs.append(eq.iloc[-1]**(252/len(boot))-1 if len(boot)>0 else 0)
        dds.append((eq/eq.cummax()-1).min())
    return dict(
        sharpe=(np.percentile(sharpes,2.5), np.percentile(sharpes,97.5), np.median(sharpes)),
        cagr=(np.percentile(cagrs,2.5), np.percentile(cagrs,97.5), np.median(cagrs)),
        max_drawdown=(np.percentile(dds,2.5), np.percentile(dds,97.5), np.median(dds)),
    )

log("=" * 80)
log("1. BLOCK BOOTSTRAP CI on production blend (70% FCP + 30% MAX-TOP2)")
log("=" * 80)

for label, START in [("LIVE 18y", LIVE_START), ("EXTENDED 28y", EXT_START)]:
    fcp_rets, _ = run_fcp_backtest(panel, START, END)
    mt2 = mfl.run_max_fcp_backtest(panel, START, END, apply_pp_overlay=False)
    common = fcp_rets.index.intersection(mt2.index)
    blend = 0.7 * fcp_rets.loc[common] + 0.3 * mt2.loc[common]
    point = stats(blend)
    log(f"\n--- {label} ({blend.index[0].date()} -> {blend.index[-1].date()}, {len(blend)} days) ---")
    log(f"Point estimates: Sh={point['sharpe']:.3f} CAGR={point['cagr']*100:.2f}% DD={point['max_drawdown']*100:.2f}%")
    log("Bootstrapping (2000 reps, block size 21 days) ...")
    ci = block_bootstrap_ci(blend, n_boot=2000, block_size=21)
    log(f"Sharpe : 95% CI [{ci['sharpe'][0]:.3f}, {ci['sharpe'][1]:.3f}]  median {ci['sharpe'][2]:.3f}")
    log(f"CAGR   : 95% CI [{ci['cagr'][0]*100:.2f}%, {ci['cagr'][1]*100:.2f}%]  median {ci['cagr'][2]*100:.2f}%")
    log(f"MaxDD  : 95% CI [{ci['max_drawdown'][0]*100:.2f}%, {ci['max_drawdown'][1]*100:.2f}%]  median {ci['max_drawdown'][2]*100:.2f}%")


# =========================================================================
# 2. WALK-FORWARD: filter robustness
# =========================================================================
log("\n" + "=" * 80)
log("2. WALK-FORWARD: per-asset filter robustness on MAX-TOP2 sleeve")
log("=" * 80)
log("Tests if 12-1 momentum filter wins OOS or is in-sample fit")

orig = mfl._rank_candidates

def make_ranker(filter_fn):
    def ranker(monthly, sd):
        ranked = []
        for u in mfl.BULL_UNIVERSE:
            if u not in monthly.columns: continue
            if not filter_fn(monthly[u], sd): continue
            r = faber_dist(monthly[u], sd, 10)
            if pd.isna(r): continue
            ranked.append((u, r))
        ranked.sort(key=lambda x: -x[1])
        return ranked
    return ranker

filters = {
    "12-1 mom > 0 (PROD)":   make_ranker(lambda s,sd: (m := momentum_12(s,sd)) is not None and pd.notna(m) and m > 0),
    "Faber 10mo dist > 0":    make_ranker(lambda s,sd: (d := faber_dist(s,sd,10)) is not None and pd.notna(d) and d > 0),
    "Faber 6mo dist > 0":     make_ranker(lambda s,sd: (d := faber_dist(s,sd,6)) is not None and pd.notna(d) and d > 0),
    "NO filter (macro only)": make_ranker(lambda s,sd: True),
}

# Rolling 5y OOS windows
windows = [
    ("2010-2015", pd.Timestamp("2010-01-01"), pd.Timestamp("2015-01-01")),
    ("2013-2018", pd.Timestamp("2013-01-01"), pd.Timestamp("2018-01-01")),
    ("2016-2021", pd.Timestamp("2016-01-01"), pd.Timestamp("2021-01-01")),
    ("2019-2024", pd.Timestamp("2019-01-01"), pd.Timestamp("2024-01-01")),
    ("2021-2026", pd.Timestamp("2021-01-01"), END),
]

log(f"\nRolling 5y OOS windows -- standalone MAX-TOP2 Sharpe per window:")
log(f"{'Window':12s} | " + " | ".join(f"{lab:24s}" for lab in filters.keys()))
log("-" * 130)
for wname, ws, we in windows:
    row = [wname]
    for lab, ranker in filters.items():
        mfl._rank_candidates = ranker
        try:
            r = mfl.run_max_fcp_backtest(panel, ws, we, apply_pp_overlay=False)
            m = stats(r)
            row.append(f"Sh={m['sharpe']:5.2f} CAGR={m['cagr']*100:4.1f}% DD={m['max_drawdown']*100:5.1f}%")
        except Exception as e:
            row.append(f"ERR")
    log(f"{row[0]:12s} | " + " | ".join(f"{c:24s}" for c in row[1:]))
mfl._rank_candidates = orig

log(f"\nRolling 5y OOS windows -- 70/30 PROD blend Sharpe per window:")
log(f"{'Window':12s} | " + " | ".join(f"{lab:24s}" for lab in filters.keys()))
log("-" * 130)
for wname, ws, we in windows:
    row = [wname]
    fcp, _ = run_fcp_backtest(panel, ws, we)
    for lab, ranker in filters.items():
        mfl._rank_candidates = ranker
        try:
            r = mfl.run_max_fcp_backtest(panel, ws, we, apply_pp_overlay=False)
            common = fcp.index.intersection(r.index)
            b = 0.7 * fcp.loc[common] + 0.3 * r.loc[common]
            m = stats(b)
            row.append(f"Sh={m['sharpe']:5.2f} CAGR={m['cagr']*100:4.1f}% DD={m['max_drawdown']*100:5.1f}%")
        except Exception as e:
            row.append(f"ERR")
    log(f"{row[0]:12s} | " + " | ".join(f"{c:24s}" for c in row[1:]))
mfl._rank_candidates = orig


# =========================================================================
# 3. VIX threshold sensitivity
# =========================================================================
log("\n" + "=" * 80)
log("3. VIX THRESHOLD sensitivity (production filter setting was 35)")
log("=" * 80)

orig_vix = mfl.VIX_THRESHOLD
log(f"\n{'VIX threshold':16s} | LIVE 18y blend (Sh / CAGR / DD / COVID) | EXT 28y blend")
log("-" * 100)
for vix_t in [None, 25, 30, 35, 40, 45]:
    mfl.VIX_THRESHOLD = vix_t if vix_t is not None else 1e9  # no cap
    label = "no cap" if vix_t is None else f"< {vix_t}"
    cells = []
    for START in [LIVE_START, EXT_START]:
        fcp, _ = run_fcp_backtest(panel, START, END)
        mt2 = mfl.run_max_fcp_backtest(panel, START, END, apply_pp_overlay=False)
        common = fcp.index.intersection(mt2.index)
        b = 0.7 * fcp.loc[common] + 0.3 * mt2.loc[common]
        m = stats(b)
        cells.append(f"Sh={m['sharpe']:.2f} CAGR={m['cagr']*100:5.2f}% DD={m['max_drawdown']*100:6.2f}% COVID={covid_dd(b):+5.1f}%")
    log(f"  {label:14s} | {cells[0]:42s} | {cells[1]}")
mfl.VIX_THRESHOLD = orig_vix


# =========================================================================
# 4. Universe sensitivity (drop one ticker at a time)
# =========================================================================
log("\n" + "=" * 80)
log("4. UNIVERSE SENSITIVITY: drop one ticker at a time from BULL_UNIVERSE")
log("=" * 80)

orig_universe = list(mfl.BULL_UNIVERSE)
log(f"\nOriginal universe: {orig_universe}")
log(f"\n{'Dropped':10s} | LIVE 18y blend (Sh / CAGR / DD / COVID) | EXT 28y blend")
log("-" * 100)
for drop in [None] + orig_universe:
    if drop is None:
        mfl.BULL_UNIVERSE = list(orig_universe)
        label = "(none)"
    else:
        mfl.BULL_UNIVERSE = [u for u in orig_universe if u != drop]
        label = drop
    cells = []
    for START in [LIVE_START, EXT_START]:
        fcp, _ = run_fcp_backtest(panel, START, END)
        mt2 = mfl.run_max_fcp_backtest(panel, START, END, apply_pp_overlay=False)
        common = fcp.index.intersection(mt2.index)
        b = 0.7 * fcp.loc[common] + 0.3 * mt2.loc[common]
        m = stats(b)
        cells.append(f"Sh={m['sharpe']:.2f} CAGR={m['cagr']*100:5.2f}% DD={m['max_drawdown']*100:6.2f}% COVID={covid_dd(b):+5.1f}%")
    log(f"  {label:8s} | {cells[0]:42s} | {cells[1]}")
mfl.BULL_UNIVERSE = orig_universe


# =========================================================================
# 5. Blend ratio sensitivity
# =========================================================================
log("\n" + "=" * 80)
log("5. BLEND RATIO sensitivity (production = 70/30)")
log("=" * 80)

log(f"\n{'FCP/MAX':10s} | LIVE 18y blend | EXT 28y blend")
log("-" * 110)
for w_fcp in [1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.0]:
    cells = []
    for START in [LIVE_START, EXT_START]:
        fcp, _ = run_fcp_backtest(panel, START, END)
        mt2 = mfl.run_max_fcp_backtest(panel, START, END, apply_pp_overlay=False)
        common = fcp.index.intersection(mt2.index)
        b = w_fcp * fcp.loc[common] + (1 - w_fcp) * mt2.loc[common]
        m = stats(b)
        cells.append(f"Sh={m['sharpe']:.2f} CAGR={m['cagr']*100:5.2f}% DD={m['max_drawdown']*100:6.2f}% COVID={covid_dd(b):+5.1f}%")
    log(f"  {int(w_fcp*100):2d}/{int((1-w_fcp)*100):2d}    | {cells[0]:48s} | {cells[1]}")


log("\n\n=== VALIDATION COMPLETE ===")
log_f.close()
print(f"\nResults written to: {LOG_PATH}")
