"""Alternative momentum + selection logic for NDX sleeve.

Phase 1: vary momentum signal (selection = top4-by-mom simple)
Phase 2: vary selection logic (mom = current 13612U)
Phase 3: best combo

Caches per-config returns to research/ndx_sleeve/cache/.
"""
from __future__ import annotations
import sys
import hashlib
import json
import time
from pathlib import Path
from itertools import combinations
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import pandas as pd
import index_constitution as ic

from cpm_live import load_panel, perf_metrics, sig_13612U
from bull_spy_live import compute_bull_spy_weights, CASH_TICKER
from ndx_sleeve_live import load_ndx_panel

CACHE_DIR = Path(__file__).resolve().parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)


# ---------- Momentum signals ----------

def mom_13612U(monthly: pd.Series) -> float:
    return sig_13612U(monthly)

def mom_12_1(monthly: pd.Series) -> float:
    """12-month return excluding the most recent month."""
    if len(monthly) < 13: return float("nan")
    return monthly.iloc[-2] / monthly.iloc[-13] - 1

def mom_6_1(monthly: pd.Series) -> float:
    if len(monthly) < 7: return float("nan")
    return monthly.iloc[-2] / monthly.iloc[-7] - 1

def mom_3mo(monthly: pd.Series) -> float:
    if len(monthly) < 4: return float("nan")
    return monthly.iloc[-1] / monthly.iloc[-4] - 1

def mom_6mo(monthly: pd.Series) -> float:
    if len(monthly) < 7: return float("nan")
    return monthly.iloc[-1] / monthly.iloc[-7] - 1

def mom_12mo(monthly: pd.Series) -> float:
    if len(monthly) < 13: return float("nan")
    return monthly.iloc[-1] / monthly.iloc[-13] - 1

def mom_sharpe12(daily: pd.Series) -> float:
    """12-month return / 12-month vol (annualized Sharpe-like)."""
    r = daily.iloc[-252:].pct_change().dropna()
    if len(r) < 100: return float("nan")
    ann_ret = (1+r).prod() ** (252/len(r)) - 1
    ann_vol = r.std() * np.sqrt(252)
    if ann_vol <= 0: return float("nan")
    return ann_ret / ann_vol


MOM_SIGNALS = {
    "13612U":     ("monthly", mom_13612U),
    "12-1":       ("monthly", mom_12_1),
    "6-1":        ("monthly", mom_6_1),
    "3mo":        ("monthly", mom_3mo),
    "6mo":        ("monthly", mom_6mo),
    "12mo":       ("monthly", mom_12mo),
    "sharpe12":   ("daily",   mom_sharpe12),
}


# ---------- Selection logic (given top-K candidates) ----------

def sel_top_mom(candidates_with_mom, daily_panel, sig_d, k):
    """Just pick top-k by momentum, equal weight."""
    top = sorted(candidates_with_mom.items(), key=lambda x: -x[1])[:k]
    return {t: 1.0/k for t, _ in top}

def sel_downside_vol(candidates_with_mom, daily_panel, sig_d, k, lookback=252):
    """Pick k from top-8 that maximize avg_mom / sqrt(downside_vol_252).
    THIS IS THE CURRENT PRODUCTION LOGIC."""
    daily_rets = daily_panel.loc[:sig_d].pct_change()
    best_score, best_combo = -np.inf, None
    tickers = list(candidates_with_mom.keys())
    for combo in combinations(tickers, k):
        avg_mom = np.mean([candidates_with_mom[t] for t in combo])
        port_ret = daily_rets[list(combo)].iloc[-lookback:].mean(axis=1).dropna()
        if len(port_ret) < 30: continue
        neg = port_ret[port_ret < 0]
        if len(neg) < 5:
            dvol = max(1e-6, port_ret.std() * np.sqrt(252) * 0.1)
        else:
            dvol = neg.std() * np.sqrt(252)
        if dvol <= 0: continue
        score = avg_mom / np.sqrt(dvol)
        if score > best_score:
            best_score, best_combo = score, combo
    if best_combo is None: return None
    return {t: 1.0/k for t in best_combo}

def sel_sharpe_full(candidates_with_mom, daily_panel, sig_d, k, lookback=252):
    """Pick k from top-K that maximize avg_mom / total_vol (Sharpe-like)."""
    daily_rets = daily_panel.loc[:sig_d].pct_change()
    best_score, best_combo = -np.inf, None
    tickers = list(candidates_with_mom.keys())
    for combo in combinations(tickers, k):
        avg_mom = np.mean([candidates_with_mom[t] for t in combo])
        port_ret = daily_rets[list(combo)].iloc[-lookback:].mean(axis=1).dropna()
        if len(port_ret) < 30: continue
        vol = port_ret.std() * np.sqrt(252)
        if vol <= 0: continue
        score = avg_mom / vol
        if score > best_score:
            best_score, best_combo = score, combo
    if best_combo is None: return None
    return {t: 1.0/k for t in best_combo}

def sel_min_var(candidates_with_mom, daily_panel, sig_d, k, lookback=252):
    """Pick k from top-K minimizing portfolio variance (ignore momentum)."""
    from itertools import combinations
    daily_rets = daily_panel.loc[:sig_d].pct_change()
    best_var, best_combo = np.inf, None
    tickers = list(candidates_with_mom.keys())
    for combo in combinations(tickers, k):
        port_ret = daily_rets[list(combo)].iloc[-lookback:].mean(axis=1).dropna()
        if len(port_ret) < 30: continue
        v = port_ret.var()
        if v < best_var:
            best_var, best_combo = v, combo
    if best_combo is None: return None
    return {t: 1.0/k for t in best_combo}

def sel_risk_parity(candidates_with_mom, daily_panel, sig_d, k, lookback=63):
    """Pick top-k by mom, weight by inverse vol (lower vol gets more)."""
    daily_rets = daily_panel.loc[:sig_d].pct_change()
    top = sorted(candidates_with_mom.items(), key=lambda x: -x[1])[:k]
    inv_vols = {}
    for t, _ in top:
        r = daily_rets[t].iloc[-lookback:].dropna()
        if len(r) < 20: continue
        v = r.std()
        if v <= 0: continue
        inv_vols[t] = 1.0 / v
    if not inv_vols: return None
    s = sum(inv_vols.values())
    return {t: v/s for t, v in inv_vols.items()}


SELECTION_LOGICS = {
    "top-mom-simple":   sel_top_mom,           # Just top-k by mom (no risk step)
    "downside-vol":     sel_downside_vol,      # Current PROD (avg_mom / sqrt(dvol))
    "sharpe-full":      sel_sharpe_full,       # avg_mom / vol
    "min-var":          sel_min_var,           # min variance only
    "risk-parity-63d":  sel_risk_parity,       # inv-vol weighted top-k
}


# ---------- Backtest engine ----------

def run_alt_sleeve(start, end_, mom_name="13612U", sel_name="downside-vol",
                   top_k=8, select_k=4, cost_bps=10):
    panel = load_panel(start=pd.Timestamp("1993-01-01"))
    ndx_panel = load_ndx_panel()
    full_panel = panel.join(ndx_panel, how="outer", rsuffix="_dup")
    full_panel = full_panel.loc[:, ~full_panel.columns.str.endswith("_dup")]

    mom_freq, mom_fn = MOM_SIGNALS[mom_name]
    sel_fn = SELECTION_LOGICS[sel_name]

    sig_dates = full_panel.resample("ME").last().index
    sig_dates = sig_dates[(sig_dates >= start) & (sig_dates <= end_)]

    weights_for_date = {}
    for sd in sig_dates:
        bq_w, bq_regime, _ = compute_bull_spy_weights(panel, sd)
        if not bq_regime.startswith("BULL_QQQ"):
            target = {CASH_TICKER: 1.0}
        else:
            pit = ic.constituents_at("nasdaq100", sd.strftime("%Y-%m-%d"))
            pit_tickers = set(pit["symbol"].tolist())
            available = [t for t in pit_tickers if t in ndx_panel.columns]
            monthly = ndx_panel.loc[:sd].resample("ME").last()
            momenta = {}
            for t in available:
                if mom_freq == "monthly":
                    s = monthly[t].dropna()
                    if len(s) < 13: continue
                    m = mom_fn(s)
                else:  # daily
                    s = ndx_panel[t].loc[:sd].dropna()
                    if len(s) < 252: continue
                    m = mom_fn(s)
                if pd.notna(m) and m > 0:
                    momenta[t] = m
            top = dict(sorted(momenta.items(), key=lambda x: -x[1])[:top_k])
            if len(top) < select_k:
                target = {CASH_TICKER: 1.0}
            else:
                weights = sel_fn(top, ndx_panel, sd, select_k)
                target = weights if weights else {CASH_TICKER: 1.0}

        next_loc = full_panel.index.get_indexer([sd], method="bfill")[0] + 1
        if next_loc < len(full_panel.index):
            weights_for_date[full_panel.index[next_loc]] = target

    daily_rets = pd.Series(0.0, index=full_panel.loc[start:end_].index)
    exec_dates = sorted(weights_for_date.keys())
    cur_w = {CASH_TICKER: 1.0}
    cur_w_idx = 0
    for ts in full_panel.loc[start:end_].index:
        while cur_w_idx < len(exec_dates) and exec_dates[cur_w_idx] <= ts:
            new_w = weights_for_date[exec_dates[cur_w_idx]]
            if cur_w != new_w:
                tovr = sum(abs(cur_w.get(a, 0) - new_w.get(a, 0))
                           for a in set(cur_w) | set(new_w))
                daily_rets.loc[ts] -= tovr * cost_bps / 10000 / 2
            cur_w = new_w
            cur_w_idx += 1
        prev_loc = full_panel.index.get_loc(ts)
        if prev_loc == 0: continue
        prev_d = full_panel.index[prev_loc - 1]
        port_r = 0.0
        for asset, w in cur_w.items():
            if asset not in full_panel.columns: continue
            today = full_panel.loc[ts, asset]
            yest = full_panel.loc[prev_d, asset]
            if pd.notna(today) and pd.notna(yest) and yest > 0:
                port_r += w * (today/yest - 1)
        daily_rets.loc[ts] += port_r
    return daily_rets


def cache_key(**params):
    blob = json.dumps(params, sort_keys=True, default=str)
    h = hashlib.sha1(blob.encode()).hexdigest()[:12]
    return CACHE_DIR / f"alt_{h}.parquet"


def cached_run(start, end_, mom_name, sel_name, top_k=8, select_k=4):
    path = cache_key(start=start, end=end_, mom=mom_name, sel=sel_name,
                     top_k=top_k, select_k=select_k)
    if path.exists():
        return pd.read_parquet(path)["r"]
    r = run_alt_sleeve(start, end_, mom_name, sel_name, top_k, select_k)
    pd.DataFrame({"r": r}).to_parquet(path)
    return r


def fmt(label, r, base_sh=None):
    m = perf_metrics(r)
    delta = f"  Δ {m['sharpe']-base_sh:+.3f}" if base_sh is not None else ""
    return (f'  {label:<35}  Sh {m["sharpe"]:>5.3f}  CAGR {m["cagr"]*100:>5.2f}%  '
            f'MaxDD {m["max_drawdown"]*100:>7.2f}%{delta}')


def main():
    start = pd.Timestamp("2007-02-28")
    end = pd.Timestamp("2026-05-19")

    print("="*80)
    print("PHASE 1: Momentum signal (selection fixed = downside-vol baseline)")
    print("="*80)
    base = cached_run(start, end, "13612U", "downside-vol")
    base_sh = perf_metrics(base)["sharpe"]
    print(fmt("13612U (baseline)", base))
    for mom_name in ["12-1", "6-1", "3mo", "6mo", "12mo", "sharpe12"]:
        t0 = time.time()
        r = cached_run(start, end, mom_name, "downside-vol")
        elapsed = time.time() - t0
        cache_note = " (cached)" if elapsed < 0.5 else f"  ({elapsed:.0f}s)"
        print(fmt(mom_name, r, base_sh) + cache_note)

    print()
    print("="*80)
    print("PHASE 2: Selection logic (momentum fixed = 13612U)")
    print("="*80)
    print(fmt("downside-vol (baseline)", base))
    for sel_name in ["top-mom-simple", "sharpe-full", "min-var", "risk-parity-63d"]:
        t0 = time.time()
        r = cached_run(start, end, "13612U", sel_name)
        elapsed = time.time() - t0
        cache_note = " (cached)" if elapsed < 0.5 else f"  ({elapsed:.0f}s)"
        print(fmt(sel_name, r, base_sh) + cache_note)

    print()
    print("="*80)
    print("PHASE 3: Cross-combinations (top 3 mom × top 3 sel)")
    print("="*80)
    # Run all 21 combinations and rank
    results = {}
    for mom_name in MOM_SIGNALS:
        for sel_name in SELECTION_LOGICS:
            t0 = time.time()
            r = cached_run(start, end, mom_name, sel_name)
            results[(mom_name, sel_name)] = perf_metrics(r)
    # Rank by Sharpe
    ranked = sorted(results.items(), key=lambda x: -x[1]["sharpe"])
    print(f"  {'Rank':<5}  {'Momentum':<10}  {'Selection':<20}  {'Sh':>5}  {'CAGR':>6}  {'MaxDD':>7}")
    for i, ((mom, sel), m) in enumerate(ranked[:10], 1):
        mark = " <- PROD" if (mom, sel) == ("13612U", "downside-vol") else ""
        print(f"  {i:>3}.  {mom:<10}  {sel:<20}  {m['sharpe']:>4.3f}  {m['cagr']*100:>5.2f}%  {m['max_drawdown']*100:>6.2f}%{mark}")
    print(f"  ...")
    for i, ((mom, sel), m) in enumerate(ranked[-3:], len(ranked)-2):
        print(f"  {i:>3}.  {mom:<10}  {sel:<20}  {m['sharpe']:>4.3f}  {m['cagr']*100:>5.2f}%  {m['max_drawdown']*100:>6.2f}%")


if __name__ == "__main__":
    main()
