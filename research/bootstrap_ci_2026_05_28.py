"""
Bootstrap CI on PROD 60/20/20 blend (current spec, honest t+1 MOO execution).

Stationary block bootstrap of daily returns; B=2000 iterations, block_size=21d
(approx 1 month, captures monthly rebal autocorr). Seed=42.

Metrics reported: Sharpe (annualized, 0 rf), CAGR, Vol, MaxDD, Calmar.
Reports point estimate and percentile CI (2.5%, 25%, 50%, 75%, 97.5%).

Current PROD spec:
  60% CPM-ext  (AAA Pair-EW on CLEAN-7, TIP canary, GPM Faber, top-4 pair)
  20% BULL-ext (HAA-Simple on SPY, HYG OR TIP canary)
  20% NDX     (top-5 PIT NDX by GPM, TIP canary)
"""
import sys, socket
socket.setdefaulttimeout(15)
sys.path.insert(0, "/Users/rkautsar/personal/scripts/strategy_cpm")

import pandas as pd
import numpy as np
from cpm_live import load_panel, run_cpm_backtest, perf_metrics
from bull_spy_live import run_bull_spy_backtest
from ndx_sleeve_live import load_ndx_panel, run_ndx_backtest


def stationary_block_bootstrap(daily, block_size=21, rng=None):
    """Sample contiguous blocks of given size with replacement.
    Output length matches input length."""
    if rng is None:
        rng = np.random.default_rng()
    n = len(daily)
    n_blocks = (n // block_size) + 1
    arr = daily.values
    blocks = []
    for _ in range(n_blocks):
        start_idx = rng.integers(0, n)
        end_idx = start_idx + block_size
        if end_idx <= n:
            blocks.append(arr[start_idx:end_idx])
        else:
            blocks.append(np.concatenate([arr[start_idx:], arr[:end_idx - n]]))
    boot = np.concatenate(blocks)[:n]
    return pd.Series(boot, index=daily.index)


def compute_metrics(daily):
    m = perf_metrics(daily)
    calmar = m["cagr"] / abs(m["max_drawdown"]) if m["max_drawdown"] != 0 else np.nan
    return {
        "Sharpe": m["sharpe"],
        "CAGR": m["cagr"],
        "Vol": m["vol"],
        "MaxDD": m["max_drawdown"],
        "Calmar": calmar,
    }


def bootstrap_ci(daily, n_iter=2000, block_size=21, seed=42):
    rng = np.random.default_rng(seed)
    keys = ["Sharpe", "CAGR", "Vol", "MaxDD", "Calmar"]
    boot_results = {k: [] for k in keys}
    for _ in range(n_iter):
        b = stationary_block_bootstrap(daily, block_size=block_size, rng=rng)
        m = compute_metrics(b)
        for k in keys:
            boot_results[k].append(m[k])
    out = {}
    for k in keys:
        arr = np.array(boot_results[k])
        out[k] = {
            "p2.5": float(np.percentile(arr, 2.5)),
            "p25": float(np.percentile(arr, 25)),
            "p50": float(np.percentile(arr, 50)),
            "p75": float(np.percentile(arr, 75)),
            "p97.5": float(np.percentile(arr, 97.5)),
            "mean": float(arr.mean()),
            "std": float(arr.std()),
        }
    return out


def main():
    print(f"Loading panel and computing sleeves...")
    panel = load_panel(start=pd.Timestamp("1993-01-01"))
    ndx_panel = load_ndx_panel()
    start = pd.Timestamp("2008-05-30")
    end = pd.Timestamp("2026-05-22")

    cpm, _ = run_cpm_backtest(panel, start, end)
    bull_raw = run_bull_spy_backtest(panel, start, end)
    ndx_raw, _ = run_ndx_backtest(panel, ndx_panel, start, end)
    common = cpm.index.intersection(bull_raw.index).intersection(ndx_raw.index)
    cpm = cpm.reindex(common); bull_raw = bull_raw.reindex(common); ndx_raw = ndx_raw.reindex(common).fillna(0.0)
    ndx = ndx_raw
    bull = bull_raw
    blend = 0.60 * cpm + 0.20 * bull + 0.20 * ndx

    print(f"\nPROD 60/20/20 blend, {blend.index.min().date()} -> {blend.index.max().date()}, n={len(blend)} days")
    point = compute_metrics(blend)
    print(f"\nPoint estimates:")
    print(f"  Sharpe: {point['Sharpe']:.3f}")
    print(f"  CAGR:   {point['CAGR']*100:.2f}%")
    print(f"  Vol:    {point['Vol']*100:.2f}%")
    print(f"  MaxDD:  {point['MaxDD']*100:.2f}%")
    print(f"  Calmar: {point['Calmar']:.2f}")

    print(f"\nRunning stationary block bootstrap (B=2000, block=21d, seed=42)...")
    ci = bootstrap_ci(blend, n_iter=2000, block_size=21, seed=42)

    print(f"\n{'='*80}")
    print(f"BOOTSTRAP CI -- PROD 60/20/20 (block bootstrap, B=2000, block=21d)")
    print(f"{'='*80}")
    print(f"{'Metric':<10} {'Point':>8} {'p2.5':>8} {'p25':>8} {'p50':>8} {'p75':>8} {'p97.5':>8}")
    print("-" * 80)
    for k in ["Sharpe", "CAGR", "Vol", "MaxDD", "Calmar"]:
        fmt = "%" if k in ("CAGR", "Vol", "MaxDD") else ""
        if fmt == "%":
            print(f"{k:<10} "
                  f"{point[k]*100:>7.2f}% "
                  f"{ci[k]['p2.5']*100:>7.2f}% "
                  f"{ci[k]['p25']*100:>7.2f}% "
                  f"{ci[k]['p50']*100:>7.2f}% "
                  f"{ci[k]['p75']*100:>7.2f}% "
                  f"{ci[k]['p97.5']*100:>7.2f}%")
        else:
            print(f"{k:<10} "
                  f"{point[k]:>8.3f} "
                  f"{ci[k]['p2.5']:>8.3f} "
                  f"{ci[k]['p25']:>8.3f} "
                  f"{ci[k]['p50']:>8.3f} "
                  f"{ci[k]['p75']:>8.3f} "
                  f"{ci[k]['p97.5']:>8.3f}")
    print(f"{'='*80}")
    print(f"\nInterpretation: 95% CI for Sharpe: [{ci['Sharpe']['p2.5']:.3f}, {ci['Sharpe']['p97.5']:.3f}]")
    print(f"                95% CI for CAGR:   [{ci['CAGR']['p2.5']*100:.2f}%, {ci['CAGR']['p97.5']*100:.2f}%]")
    print(f"                95% CI for MaxDD:  [{ci['MaxDD']['p2.5']*100:.2f}%, {ci['MaxDD']['p97.5']*100:.2f}%]")

    # Save numpy results
    import json
    with open("/Users/rkautsar/personal/scripts/strategy_cpm/research/bootstrap_ci_2026_05_28.json", "w") as f:
        json.dump({"point": point, "ci": ci, "n_iter": 2000, "block_size": 21,
                    "seed": 42, "start": str(start.date()), "end": str(end.date()),
                    "n_days": len(blend)}, f, indent=2)
    print(f"\nSaved JSON: research/bootstrap_ci_2026_05_28.json")


if __name__ == "__main__":
    main()
