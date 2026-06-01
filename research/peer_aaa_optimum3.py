"""Honest implementations of Resolve AAA (paper) and Optimum3 (Newfound/
Tresidder) for fair comparison against CPM.

AAA (Butler, Philbrick, Gordillo 2014 "Adaptive Asset Allocation"):
  - Universe: 10 global asset-class ETFs
  - Signal: 6-month total-return momentum
  - Filter: top-5 by momentum, must be > 0
  - Weighting: minimum-variance optimization on top-5
  - Covariance lookback: 60 trading days (~3mo) per paper
  - Defensive: cash for filtered-out positions
  - Rebalance: monthly EOM

Optimum3 (Tresidder/Newfound, popularized by AllocateSmartly):
  - Universe: ~12 global asset-class ETFs (similar to AAA but broader)
  - Three momentum signals: 1mo, 3mo, 6mo (or 3/6/12mo variant)
  - Each signal independently selects top-K
  - Final weights = average across the 3 sub-portfolios (ensemble)
  - Defensive: cash position when signal is negative
  - Rebalance: monthly

Both run with:
  - 10 bps/side cost
  - SHV cash for filtered positions
  - Total-return prices (yfinance auto_adjust=True)
"""
from __future__ import annotations
import sys
sys.path.insert(0, '.')

import numpy as np
import pandas as pd
import yfinance as yf
from scipy.optimize import minimize
from cpm_live import load_panel, run_cpm_backtest, perf_metrics
import bull_spy_live as bql
from build_dashboard import haa_balanced

COST_BPS = 10
CASH = "SHV"


# ============================================================
# Helper: pull additional ETFs needed for AAA/Optimum3
# ============================================================
def ensure_assets(panel, tickers, start="1995-01-01"):
    """Pull missing tickers from yfinance, merge into panel."""
    missing = [t for t in tickers if t not in panel.columns]
    if not missing:
        return panel
    print(f"  Fetching {len(missing)} extra tickers from yfinance: {missing}")
    for t in missing:
        try:
            d = yf.download(t, start=start, auto_adjust=True, progress=False, threads=False)
            if d.empty:
                continue
            if isinstance(d.columns, pd.MultiIndex):
                d.columns = d.columns.get_level_values(0)
            s = d["Close"].dropna()
            s.name = t
            panel = panel.join(s, how="outer")
        except Exception as e:
            print(f"    {t}: {e}")
    return panel.sort_index()


# ============================================================
# Resolve AAA (Adaptive Asset Allocation)
# ============================================================
AAA_UNIVERSE = ["VTI", "IWM", "VEU", "VWO", "VNQ", "RWX", "TLT", "IEF", "DBC", "GLD"]


def aaa_run(panel, start, end, top_k=5, mom_lookback_months=6,
            cov_lookback_days=60, cost_bps=COST_BPS):
    """Resolve AAA: top-K by 6mo momentum, min-variance weighting."""
    panel = ensure_assets(panel, AAA_UNIVERSE + [CASH])
    daily_rets = panel.ffill().pct_change()
    monthly_idx = pd.DataFrame({"x": 1}, index=panel.index).groupby(
        pd.Grouper(freq="ME")).tail(1)
    sigs = monthly_idx.index[(monthly_idx.index >= start) &
                              (monthly_idx.index <= end)].tolist()
    common = panel.index[(panel.index >= start) & (panel.index <= end)]

    all_tickers = set(AAA_UNIVERSE + [CASH])
    w_per_day = {t: pd.Series(0.0, index=common) for t in all_tickers}
    state_per_day = pd.Series("", index=common, dtype=object)

    for i, sig_d in enumerate(sigs):
        mon = panel.loc[:sig_d].resample("ME").last()
        if len(mon) < mom_lookback_months + 1:
            continue
        # 6-month total return momentum
        mom = mon.iloc[-1] / mon.iloc[-mom_lookback_months - 1] - 1
        mom = mom.dropna()
        avail = [a for a in AAA_UNIVERSE if a in mom.index and not pd.isna(mom[a])]
        if not avail:
            month_w = {CASH: 1.0}
        else:
            # Top-K positive
            mom_avail = mom[avail].sort_values(ascending=False)
            top = mom_avail[mom_avail > 0].head(top_k).index.tolist()
            if not top:
                month_w = {CASH: 1.0}
            elif len(top) == 1:
                month_w = {top[0]: 1.0}
            else:
                # Min-variance weighting on top-K
                daily_sub = daily_rets.loc[:sig_d, top].tail(cov_lookback_days).dropna()
                if len(daily_sub) < 30:
                    # Fallback: equal weight
                    month_w = {t: 1.0 / len(top) for t in top}
                else:
                    cov = daily_sub.cov().values
                    n = len(top)
                    x0 = np.full(n, 1.0 / n)
                    cons = [{"type": "eq", "fun": lambda x: x.sum() - 1}]
                    bnds = [(0, 1) for _ in range(n)]
                    try:
                        res = minimize(
                            lambda w: w @ cov @ w,
                            x0, method="SLSQP", bounds=bnds, constraints=cons,
                            options={"maxiter": 100, "ftol": 1e-8},
                        )
                        if res.success:
                            month_w = dict(zip(top, res.x))
                        else:
                            month_w = {t: 1.0 / len(top) for t in top}
                    except Exception:
                        month_w = {t: 1.0 / len(top) for t in top}

        # Apply weights
        future = common[common > sig_d]
        if len(future) < 2:
            continue
        apply_from = future[1]
        if i + 1 < len(sigs):
            ns = sigs[i + 1]
            nf = common[common > ns]
            end_apply = nf[1] if len(nf) >= 2 else common[-1]
        else:
            end_apply = common[-1] + pd.Timedelta(days=1)
        mask = (common >= apply_from) & (common < end_apply)
        for t, w in month_w.items():
            if t in w_per_day:
                w_per_day[t].loc[mask] = w
        state_per_day.loc[mask] = "+".join(f"{t}:{w:.2f}" for t, w in sorted(month_w.items()))

    port = pd.Series(0.0, index=common)
    for t, w_s in w_per_day.items():
        if t in daily_rets.columns:
            port = port + daily_rets[t].reindex(common).fillna(0.0) * w_s
    if cost_bps > 0:
        la = state_per_day.values
        flips = np.where(la[1:] != la[:-1])[0] + 1
        for f in flips:
            port.iloc[f] -= 2.0 * cost_bps / 10000.0
    return port


# ============================================================
# Optimum3 (Tresidder/Newfound ensemble)
# ============================================================
# Use broader 12-asset universe (typical Optimum3 coverage)
OPTIMUM3_UNIVERSE = ["SPY", "QQQ", "IWM", "VEA", "VEU", "VWO", "VNQ", "DBC",
                     "GLD", "TLT", "IEF", "TIP"]


def optimum3_subportfolio(panel, sig_d, mom_lookback_months, top_k, universe):
    """One sub-portfolio: top-K by single momentum signal."""
    mon = panel.loc[:sig_d].resample("ME").last()
    if len(mon) < mom_lookback_months + 1:
        return {CASH: 1.0}
    mom = mon.iloc[-1] / mon.iloc[-mom_lookback_months - 1] - 1
    mom = mom.dropna()
    avail = [a for a in universe if a in mom.index and not pd.isna(mom[a])]
    if not avail:
        return {CASH: 1.0}
    mom_avail = mom[avail].sort_values(ascending=False)
    top = mom_avail[mom_avail > 0].head(top_k).index.tolist()
    if not top:
        return {CASH: 1.0}
    return {t: 1.0 / len(top) for t in top}  # equal weight within sub-portfolio


def optimum3_run(panel, start, end, top_k=5, signals=(3, 6, 12),
                  cost_bps=COST_BPS):
    """Optimum3: ensemble of top-K from {1, 3, 6}mo or {3, 6, 12}mo signals."""
    panel = ensure_assets(panel, OPTIMUM3_UNIVERSE + [CASH])
    daily_rets = panel.ffill().pct_change()
    monthly_idx = pd.DataFrame({"x": 1}, index=panel.index).groupby(
        pd.Grouper(freq="ME")).tail(1)
    sigs = monthly_idx.index[(monthly_idx.index >= start) &
                              (monthly_idx.index <= end)].tolist()
    common = panel.index[(panel.index >= start) & (panel.index <= end)]

    all_tickers = set(OPTIMUM3_UNIVERSE + [CASH])
    w_per_day = {t: pd.Series(0.0, index=common) for t in all_tickers}
    state_per_day = pd.Series("", index=common, dtype=object)

    for i, sig_d in enumerate(sigs):
        # Three sub-portfolios, average weights
        sub_weights = []
        for mom_months in signals:
            sub = optimum3_subportfolio(panel, sig_d, mom_months, top_k, OPTIMUM3_UNIVERSE)
            sub_weights.append(sub)
        # Average across sub-portfolios
        combined = {}
        for sub in sub_weights:
            for t, w in sub.items():
                combined[t] = combined.get(t, 0) + w / len(sub_weights)

        future = common[common > sig_d]
        if len(future) < 2:
            continue
        apply_from = future[1]
        if i + 1 < len(sigs):
            ns = sigs[i + 1]
            nf = common[common > ns]
            end_apply = nf[1] if len(nf) >= 2 else common[-1]
        else:
            end_apply = common[-1] + pd.Timedelta(days=1)
        mask = (common >= apply_from) & (common < end_apply)
        for t, w in combined.items():
            if t in w_per_day:
                w_per_day[t].loc[mask] = w
        state_per_day.loc[mask] = "+".join(f"{t}:{w:.2f}" for t, w in sorted(combined.items()))

    port = pd.Series(0.0, index=common)
    for t, w_s in w_per_day.items():
        if t in daily_rets.columns:
            port = port + daily_rets[t].reindex(common).fillna(0.0) * w_s
    if cost_bps > 0:
        la = state_per_day.values
        flips = np.where(la[1:] != la[:-1])[0] + 1
        for f in flips:
            port.iloc[f] -= 2.0 * cost_bps / 10000.0
    return port


# ============================================================
# Comparison driver
# ============================================================
def report(name, rets, pad=42):
    if len(rets) == 0:
        print(f"  {name:<{pad}} (no data)")
        return None
    m = perf_metrics(rets)
    print(f"  {name:<{pad}}  Sh {m['sharpe']:>5.3f}  CAGR {m['cagr']*100:>5.2f}%  Vol {m['vol']*100:>5.2f}%  MaxDD {m['max_drawdown']*100:>6.2f}%")
    return m


def main():
    panel = load_panel(start=pd.Timestamp("1993-01-01"))
    end = pd.Timestamp.today().normalize()

    # Run on multiple windows
    windows = [
        ("ETF-live 18y (2008-09 - today)", pd.Timestamp("2008-09-30")),
        ("Post-2010 (cleaner data)",        pd.Timestamp("2010-01-01")),
        ("AAA-aligned 2008+ (older)",      pd.Timestamp("2008-01-01")),
    ]

    for label, start in windows:
        print(f"\n{'='*100}")
        print(f"## {label}: {start.date()} -> {end.date()}")
        print('='*100)
        cpm = run_cpm_backtest(panel, start, end)[0]
        haa = haa_balanced(panel, start, end)
        print(f"\n  Running AAA (top-5 by 6mo mom, min-var on 60d cov) ...")
        aaa = aaa_run(panel, start, end, top_k=5, mom_lookback_months=6, cov_lookback_days=60)
        print(f"  Running Optimum3 ensemble (3mo + 6mo + 12mo, top-5) ...")
        opt3 = optimum3_run(panel, start, end, top_k=5, signals=(3, 6, 12))
        # Common dates
        common = cpm.index.intersection(haa.index).intersection(aaa.index).intersection(opt3.index)
        print(f"\n  Aligned: {len(common)} days")
        print()
        report("CPM standalone (current 13612U)",      cpm.reindex(common).fillna(0))
        report("HAA-Balanced (Keller 2022)",          haa.reindex(common).fillna(0))
        report("AAA (Resolve, paper-faithful)",         aaa.reindex(common).fillna(0))
        report("Optimum3 (Tresidder/Newfound)",       opt3.reindex(common).fillna(0))


if __name__ == "__main__":
    main()
