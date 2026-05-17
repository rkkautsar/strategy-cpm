#!/usr/bin/env python3
"""
FCP vs ReSolve RDMIX Live Fund — Head-to-Head Comparison
=========================================================

Hypothesis: FCP (backtest, gross) beats ReSolve's live AAA fund (RDMIX, net
of ~1% fee) on Sharpe, CAGR, and MaxDD over the RDMIX live window.

Window: 2018-03-01 to latest RDMIX date (ReSolve sub-advisory began 2018-02;
first full month used is 2018-03 to avoid partial-month inception noise).

Benchmarks:
  - SPY buy-hold
  - 60/40 SPY/IEF monthly-rebalanced
  - PP-IEF static (25/25/25/25 SPY/IEF/GLD/SHV)

Also tests:
  - FCP (net-equiv): subtract 1% p.a. fee analog to RDMIX net-of-fee
  - Bootstrap Sharpe-difference CI (FCP vs RDMIX)
  - Drawdown overlap analysis (worst periods for each)
  - Cross-correlation (are they doing similar things?)

Outputs:
  - Console log (pipe to fcp_vs_resolve_live.log)
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

# Resolve imports from repo root
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from strategy_fcp.fcp_live import load_panel, run_fcp_backtest

# ── Parameters ──────────────────────────────────────────────────────────────
WINDOW_START     = pd.Timestamp("2018-03-01")
FCP_FEE_PER_YEAR = 0.01   # 1.0% to match RDMIX's 0.95% management fee
N_BOOTSTRAP      = 5_000
BLOCK_SIZE_MO    = 6      # months; block bootstrap block size
TOP_N_DD         = 5      # top-N drawdown periods to compare


# ── Helpers ──────────────────────────────────────────────────────────────────

def fetch_series(ticker: str, start: str) -> pd.Series:
    d = yf.download(ticker, start=start, auto_adjust=True, progress=False, threads=False)
    if isinstance(d.columns, pd.MultiIndex):
        close = d["Close"].iloc[:, 0]
    else:
        close = d["Close"] if "Close" in d.columns else d.iloc[:, 0]
    close = close.dropna()
    close.name = ticker
    return close


def prices_to_daily_ret(price: pd.Series) -> pd.Series:
    return price.pct_change().dropna()


def daily_to_monthly(daily: pd.Series) -> pd.Series:
    return (1 + daily).resample("ME").prod() - 1


def annualized_cagr(daily: pd.Series) -> float:
    eq = (1 + daily).cumprod()
    yrs = (eq.index[-1] - eq.index[0]).days / 365.25
    if yrs <= 0:
        return float("nan")
    return eq.iloc[-1] ** (1 / yrs) - 1


def annualized_vol(daily: pd.Series) -> float:
    return daily.std(ddof=1) * np.sqrt(252)


def sharpe(daily: pd.Series) -> float:
    v = annualized_vol(daily)
    if v == 0:
        return float("nan")
    return (daily.mean() * 252) / v


def sortino(daily: pd.Series) -> float:
    neg = daily[daily < 0]
    if len(neg) == 0 or neg.std() == 0:
        return float("nan")
    downside_vol = neg.std(ddof=1) * np.sqrt(252)
    return (daily.mean() * 252) / downside_vol


def max_drawdown(daily: pd.Series) -> float:
    eq = (1 + daily).cumprod()
    return (eq / eq.cummax() - 1).min()


def calmar(daily: pd.Series) -> float:
    mdd = max_drawdown(daily)
    if mdd == 0:
        return float("nan")
    return annualized_cagr(daily) / abs(mdd)


def ulcer_index(daily: pd.Series) -> float:
    eq = (1 + daily).cumprod()
    dd_pct = (eq / eq.cummax() - 1) * 100
    return np.sqrt((dd_pct ** 2).mean())


def upi(daily: pd.Series) -> float:
    ui = ulcer_index(daily)
    if ui == 0:
        return float("nan")
    return annualized_cagr(daily) / (ui / 100)


def total_return(daily: pd.Series) -> float:
    return (1 + daily).prod() - 1


def metrics(daily: pd.Series, label: str = "") -> dict:
    return {
        "label":     label,
        "CAGR%":     round(annualized_cagr(daily) * 100, 2),
        "TotalRet%": round(total_return(daily) * 100, 2),
        "Vol%":      round(annualized_vol(daily) * 100, 2),
        "Sharpe":    round(sharpe(daily), 3),
        "Sortino":   round(sortino(daily), 3),
        "MaxDD%":    round(max_drawdown(daily) * 100, 2),
        "Calmar":    round(calmar(daily), 3),
        "UPI":       round(upi(daily), 3),
        "N_days":    len(daily),
    }


def build_60_40(panel: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.Series:
    cols = [c for c in ["SPY", "IEF"] if c in panel.columns]
    close = panel[cols].ffill()
    daily_ret = close.pct_change()
    monthly_ends = daily_ret.resample("ME").last().index
    monthly_ends = monthly_ends[(monthly_ends >= start) & (monthly_ends <= end)]
    out = pd.Series(0.0, index=daily_ret.index)
    w = {"SPY": 0.60, "IEF": 0.40}
    for i, me in enumerate(monthly_ends):
        nxt = monthly_ends[i + 1] if i + 1 < len(monthly_ends) else end
        seg = daily_ret.index[(daily_ret.index > me) & (daily_ret.index <= nxt)]
        for c in cols:
            out.loc[seg] += w.get(c, 0) * daily_ret.loc[seg, c].fillna(0)
    return out.loc[(out.index >= start) & (out.index <= end)]


def build_pp_ief(panel: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.Series:
    assets = ["SPY", "IEF", "GLD", "SHV"]
    cols = [c for c in assets if c in panel.columns]
    close = panel[cols].ffill()
    daily_ret = close.pct_change()
    monthly_ends = daily_ret.resample("ME").last().index
    monthly_ends = monthly_ends[(monthly_ends >= start) & (monthly_ends <= end)]
    out = pd.Series(0.0, index=daily_ret.index)
    w = {c: 1 / len(cols) for c in cols}
    for i, me in enumerate(monthly_ends):
        nxt = monthly_ends[i + 1] if i + 1 < len(monthly_ends) else end
        seg = daily_ret.index[(daily_ret.index > me) & (daily_ret.index <= nxt)]
        for c in cols:
            out.loc[seg] += w[c] * daily_ret.loc[seg, c].fillna(0)
    return out.loc[(out.index >= start) & (out.index <= end)]


def apply_annual_fee(daily: pd.Series, fee_per_year: float) -> pd.Series:
    daily_fee = (1 + fee_per_year) ** (1 / 252) - 1
    return daily - daily_fee


def block_bootstrap_sharpe_diff(a: pd.Series, b: pd.Series,
                                 n_boot: int = 5000, block: int = 6) -> tuple:
    mo_a = daily_to_monthly(a)
    mo_b = daily_to_monthly(b)
    idx = mo_a.index.intersection(mo_b.index)
    ra = mo_a.reindex(idx).values
    rb = mo_b.reindex(idx).values
    n = len(ra)

    def sh_monthly(r):
        if r.std() == 0:
            return 0.0
        return r.mean() / r.std() * np.sqrt(12)

    obs_diff = sh_monthly(ra) - sh_monthly(rb)
    rng = np.random.default_rng(42)
    diffs = np.empty(n_boot)
    for i in range(n_boot):
        starts = rng.integers(0, n - block + 1, size=(n // block) + 1)
        idx_boot = np.concatenate([np.arange(s, min(s + block, n)) for s in starts])[:n]
        diffs[i] = sh_monthly(ra[idx_boot]) - sh_monthly(rb[idx_boot])

    ci_lo = float(np.percentile(diffs, 2.5))
    ci_hi = float(np.percentile(diffs, 97.5))
    p_val = float(np.mean(diffs <= 0))
    return obs_diff, ci_lo, ci_hi, p_val


def find_top_drawdowns(daily: pd.Series, n: int = 5) -> list:
    eq = (1 + daily).cumprod()
    roll_max = eq.cummax()
    dd = eq / roll_max - 1

    drawdowns = []
    in_dd = False
    peak_i = 0
    for i in range(len(dd)):
        if dd.iloc[i] < -1e-6:
            if not in_dd:
                in_dd = True
                peak_i = max(i - 1, 0)
        else:
            if in_dd:
                trough_i = dd.iloc[peak_i:i].argmin() + peak_i
                drawdowns.append({
                    "peak_date":     dd.index[peak_i],
                    "trough_date":   dd.index[trough_i],
                    "recovery_date": dd.index[i],
                    "dd_pct":        round(dd.iloc[peak_i:i].min() * 100, 2),
                })
                in_dd = False
    if in_dd:
        trough_loc = dd.iloc[peak_i:].argmin() + peak_i
        drawdowns.append({
            "peak_date":     dd.index[peak_i],
            "trough_date":   dd.index[trough_loc],
            "recovery_date": None,
            "dd_pct":        round(dd.iloc[peak_i:].min() * 100, 2),
        })

    drawdowns.sort(key=lambda x: x["dd_pct"])
    return drawdowns[:n]


def drawdown_at_period(daily: pd.Series, peak_date, trough_date) -> float:
    seg = daily.loc[peak_date:trough_date]
    if seg.empty:
        return float("nan")
    eq = (1 + seg).cumprod()
    return (eq / eq.cummax() - 1).min() * 100


def main():
    t0 = time.time()
    print("=" * 90)
    print("  FCP vs ReSolve RDMIX Live Fund — Head-to-Head Comparison")
    print("=" * 90)
    print(f"  Window start: {WINDOW_START.date()}")

    # 1. RDMIX
    print("\n[1] Fetching RDMIX ...")
    rdmix_price = fetch_series("RDMIX", start="2017-12-01")
    rdmix_daily = prices_to_daily_ret(rdmix_price)
    rdmix_daily = rdmix_daily.loc[rdmix_daily.index >= WINDOW_START]
    window_end = rdmix_daily.index[-1]
    print(f"  RDMIX: {rdmix_daily.index[0].date()} -> {window_end.date()} ({len(rdmix_daily)} days)")

    # Backup check TBQRX
    try:
        tbqrx = fetch_series("TBQRX", start="2018-01-01")
        print(f"  TBQRX (backup): {tbqrx.index[0].date()} -> {tbqrx.index[-1].date()} — available, not used")
    except Exception as e:
        print(f"  TBQRX: not available ({e})")

    # 2. FCP backtest
    print(f"\n[2] Loading panel & running FCP ({WINDOW_START.date()} -> {window_end.date()}) ...")
    panel = load_panel(start=WINDOW_START, end=window_end)
    print(f"  Panel: {panel.index[0].date()} -> {panel.index[-1].date()}, {len(panel.columns)} assets")

    fcp_daily_raw, _ = run_fcp_backtest(
        panel, WINDOW_START, window_end, apply_vol_target=True, cost_bps=10
    )
    fcp_daily_raw = fcp_daily_raw.loc[fcp_daily_raw.index >= WINDOW_START]
    fcp_daily_net = apply_annual_fee(fcp_daily_raw, FCP_FEE_PER_YEAR)
    print(f"  FCP gross: {fcp_daily_raw.index[0].date()} -> {fcp_daily_raw.index[-1].date()} ({len(fcp_daily_raw)} days)")

    # 3. Benchmarks
    print("\n[3] Building SPY, 60/40, PP-IEF ...")
    spy_daily = panel["SPY"].ffill().pct_change().loc[WINDOW_START:window_end].fillna(0)
    sixtyforty = build_60_40(panel, WINDOW_START, window_end)
    pp_ief     = build_pp_ief(panel, WINDOW_START, window_end)

    # 4. Align
    common_idx = (fcp_daily_raw.index
                  .intersection(rdmix_daily.index)
                  .intersection(spy_daily.index)
                  .intersection(sixtyforty.index)
                  .intersection(pp_ief.index))
    common_idx = common_idx[common_idx >= WINDOW_START]

    fcp_g = fcp_daily_raw.reindex(common_idx).fillna(0)
    fcp_n = fcp_daily_net.reindex(common_idx).fillna(0)
    rdmix = rdmix_daily.reindex(common_idx).fillna(0)
    spy   = spy_daily.reindex(common_idx).fillna(0)
    s6040 = sixtyforty.reindex(common_idx).fillna(0)
    pp    = pp_ief.reindex(common_idx).fillna(0)
    print(f"  Aligned: {len(common_idx)} days ({common_idx[0].date()} -> {common_idx[-1].date()})")

    # 5. Metrics
    print("\n[4] Computing metrics ...")
    series_map = [
        ("FCP (gross, 10bps cost)",  fcp_g),
        ("FCP (net -1% fee equiv)",  fcp_n),
        ("RDMIX (live, net ~1%)",    rdmix),
        ("SPY buy-hold",             spy),
        ("60/40 SPY/IEF",            s6040),
        ("PP-IEF static",            pp),
    ]
    metric_rows = [metrics(s, lbl) for lbl, s in series_map]

    # Print metrics table
    print("\n" + "=" * 120)
    print("  PERFORMANCE METRICS")
    print("=" * 120)
    hdr = f"  {'Strategy':<30} {'CAGR%':>8} {'TotRet%':>9} {'Vol%':>7} {'Sharpe':>8} {'Sortino':>8} {'MaxDD%':>8} {'Calmar':>8} {'UPI':>7}"
    print(hdr)
    print("  " + "-" * 116)
    for m in metric_rows:
        print(f"  {m['label']:<30} {m['CAGR%']:>8.2f} {m['TotalRet%']:>9.2f} {m['Vol%']:>7.2f}"
              f" {m['Sharpe']:>8.3f} {m['Sortino']:>8.3f} {m['MaxDD%']:>8.2f}"
              f" {m['Calmar']:>8.3f} {m['UPI']:>7.3f}")

    # 6. Cross-correlation
    print("\n[5] Cross-correlation (monthly returns) ...")
    mo_df = pd.DataFrame({
        "FCP_gross": daily_to_monthly(fcp_g),
        "FCP_net":   daily_to_monthly(fcp_n),
        "RDMIX":     daily_to_monthly(rdmix),
        "SPY":       daily_to_monthly(spy),
        "60_40":     daily_to_monthly(s6040),
        "PP_IEF":    daily_to_monthly(pp),
    }).dropna()

    corr = mo_df.corr().round(3)
    print("\n  Pearson correlation (monthly returns):")
    print(corr.to_string())
    fcp_rdmix_corr = corr.loc["FCP_gross", "RDMIX"]
    if fcp_rdmix_corr > 0.7:
        interp = "HIGH — mostly similar factor exposures / timing"
    elif fcp_rdmix_corr > 0.4:
        interp = "MODERATE — overlap in risk-on/off timing, differing alpha sources"
    else:
        interp = "LOW — genuinely different return drivers"
    print(f"\n  FCP vs RDMIX monthly corr: {fcp_rdmix_corr:.3f} -> {interp}")

    # 7. Bootstrap Sharpe CI
    print(f"\n[6] Bootstrap Sharpe-diff CI (N={N_BOOTSTRAP}, block={BLOCK_SIZE_MO}mo) ...")
    obs_g, ci_lo_g, ci_hi_g, p_g = block_bootstrap_sharpe_diff(fcp_g, rdmix, N_BOOTSTRAP, BLOCK_SIZE_MO)
    obs_n, ci_lo_n, ci_hi_n, p_n = block_bootstrap_sharpe_diff(fcp_n, rdmix, N_BOOTSTRAP, BLOCK_SIZE_MO)

    print(f"\n  FCP_gross - RDMIX: {obs_g:+.3f}  95% CI [{ci_lo_g:+.3f}, {ci_hi_g:+.3f}]  P(diff<=0)={p_g:.3f}")
    if ci_lo_g > 0:
        verdict_g = "CI entirely positive -> FCP_gross statistically superior (95%)"
    elif ci_hi_g < 0:
        verdict_g = "CI entirely negative -> RDMIX statistically superior (95%)"
    else:
        verdict_g = "CI spans zero -> difference not significant at 95%"
    print(f"  -> {verdict_g}")

    print(f"\n  FCP_net  - RDMIX: {obs_n:+.3f}  95% CI [{ci_lo_n:+.3f}, {ci_hi_n:+.3f}]  P(diff<=0)={p_n:.3f}")
    if ci_lo_n > 0:
        verdict_n = "CI entirely positive -> FCP_net statistically superior (95%)"
    elif ci_hi_n < 0:
        verdict_n = "CI entirely negative -> RDMIX statistically superior (95%)"
    else:
        verdict_n = "CI spans zero -> difference not significant at 95%"
    print(f"  -> {verdict_n}")

    # 8. Drawdown overlap
    print(f"\n[7] Drawdown overlap analysis (top {TOP_N_DD} each) ...")

    fcp_dds   = find_top_drawdowns(fcp_g,  n=TOP_N_DD)
    rdmix_dds = find_top_drawdowns(rdmix,  n=TOP_N_DD)

    print("\n  Worst FCP drawdowns — what was RDMIX doing concurrently?")
    print(f"  {'Peak':>12} {'Trough':>12} {'Recovery':>12} {'FCP DD%':>9} {'RDMIX DD%':>11} {'Overlap?':>10}")
    print("  " + "-" * 72)
    for dd in fcp_dds:
        r_dd = drawdown_at_period(rdmix, dd["peak_date"], dd["trough_date"])
        rv = dd["recovery_date"].strftime("%Y-%m-%d") if dd["recovery_date"] else "ongoing"
        overlap = "YES" if (pd.notna(r_dd) and r_dd < -1.0) else "no"
        print(f"  {dd['peak_date'].strftime('%Y-%m-%d'):>12} {dd['trough_date'].strftime('%Y-%m-%d'):>12}"
              f" {rv:>12} {dd['dd_pct']:>9.2f}% {r_dd:>10.2f}% {overlap:>10}")

    print("\n  Worst RDMIX drawdowns — what was FCP doing concurrently?")
    print(f"  {'Peak':>12} {'Trough':>12} {'Recovery':>12} {'RDMIX DD%':>11} {'FCP DD%':>9} {'Overlap?':>10}")
    print("  " + "-" * 72)
    for dd in rdmix_dds:
        f_dd = drawdown_at_period(fcp_g, dd["peak_date"], dd["trough_date"])
        rv = dd["recovery_date"].strftime("%Y-%m-%d") if dd["recovery_date"] else "ongoing"
        overlap = "YES" if (pd.notna(f_dd) and f_dd < -1.0) else "no"
        print(f"  {dd['peak_date'].strftime('%Y-%m-%d'):>12} {dd['trough_date'].strftime('%Y-%m-%d'):>12}"
              f" {rv:>12} {dd['dd_pct']:>11.2f}% {f_dd:>9.2f}% {overlap:>10}")

    # 9. Net vs gross verdict
    print("\n[8] Net vs Gross verdict ...")
    fcp_g_sh   = sharpe(fcp_g)
    fcp_n_sh   = sharpe(fcp_n)
    rdmix_sh   = sharpe(rdmix)
    fcp_g_cagr = annualized_cagr(fcp_g) * 100
    fcp_n_cagr = annualized_cagr(fcp_n) * 100
    rdmix_cagr = annualized_cagr(rdmix) * 100

    print(f"  FCP gross: Sharpe {fcp_g_sh:.3f}, CAGR {fcp_g_cagr:.2f}%")
    print(f"  FCP net:   Sharpe {fcp_n_sh:.3f}, CAGR {fcp_n_cagr:.2f}%")
    print(f"  RDMIX:     Sharpe {rdmix_sh:.3f}, CAGR {rdmix_cagr:.2f}%")
    print(f"  Fee drag:  -Sharpe {(fcp_g_sh - fcp_n_sh):.3f}, -CAGR {(fcp_g_cagr - fcp_n_cagr):.2f}pp")
    if fcp_n_sh > rdmix_sh:
        print(f"  -> FCP net BEATS RDMIX net on Sharpe ({fcp_n_sh:.3f} > {rdmix_sh:.3f})")
    else:
        print(f"  -> FCP net TRAILS RDMIX net on Sharpe ({fcp_n_sh:.3f} < {rdmix_sh:.3f}) — fee drag decisive")

    # 10. Caveats
    print("\n" + "=" * 90)
    print("  CAVEATS & ASSUMPTIONS")
    print("=" * 90)
    caveats = [
        "FCP = backtest; RDMIX = live fund. Comparison is backtest vs real-money.",
        "FCP gross cost = 10bps/side; backtest selection bias from prior research possible.",
        "FCP net-equiv: -1.0%/yr daily-subtracted fee drag; no actual advisory fee charged.",
        "RDMIX: 0.95% mgmt fee; net returns used. USD Class I since 2018-02 under ReSolve.",
        "Only 2018-03+ used; pre-2018 RDMIX had different sub-advisor and different strategy.",
        "Vol-target on both: FCP targets 10%, RDMIX targets ~8% — different vol regimes.",
        "Bootstrap CI block=6mo captures most AR(1); longer blocks possible for robustness.",
        "FCP universe finalized with hindsight; some look-ahead bias in universe selection.",
        "ReSolve CAD 8%-vol public returns: 1y=2.17%, 3y=8.10%, 5y=5.03%, incep=5.33%.",
        "RDMIX USD Class I: 5y=5.62%, incep=5.73% (per investresolve.com, as of 2026-05).",
    ]
    for c in caveats:
        print(f"  * {c}")

    elapsed = time.time() - t0
    print(f"\n  Total elapsed: {elapsed:.1f}s")
    print("=" * 90)


if __name__ == "__main__":
    main()
