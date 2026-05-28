"""
NDX intramonth circuit using CANONICAL published stop-loss rules.

All variants honest t+1 MOO. Test alongside current and prior best:

  Reference / current:
    [REF1] NDX raw (no circuit)
    [REF2] DD -10%/63d sleeve-equity (current production)
    [REF3] DD -12.5%/63d (empirical best fixed)
    [REF4] DD -1.0sigma*sqrt(63) (empirical best adaptive, k-sigma synthesis)

  CANONICAL PUBLISHED stops:

    [LK] Lo & Kaminski (2008) "When Do Stop-Loss Rules Stop Losses?"
       Rule (their canonical): exit when SUM(r[t-J+1:t]) <= -gamma
       Their main test settings: J in {3, 6, 12, 18} months, gamma in {4..14}%.
       They recommended J=12 (~252 trading days), gamma=10% on US equity.
       Daily-monitor variant: compute trailing J-day return product, trigger
       when below -gamma. Re-entry at next monthly signal (our convention).

    [WLD] Wilder (1978) ATR-multiple stop
       Rule (canonical): trailing stop at K * ATR_N below highest close since
       entry. Standard K values: 2.0 (aggressive), 2.5, 3.0 (Wilder default).
       Portfolio adaptation: True Range proxy = |daily return| (no OHLC at
       portfolio level). ATR_N = N-day rolling mean of |daily return|. Trigger
       when DD from rolling N-day peak > K * ATR_N.
       Standard parameter: N=14 (Wilder default), K=2.5 or 3.0.

    [KASE] Kase (1991, 1996) DevStops
       Rule: trailing stop at multiple * STDEV of (high-low range) below pivot.
       Canonical multipliers: 1.0 sigma (Dev1, ~86th pctile), 2.2 (Dev2, ~96th),
       3.6 (Dev3, ~99th). Designed for OHLC; on portfolio returns use std of
       |daily return| as range proxy and trigger from rolling high.
       Standard: Dev2 = 2.2 sigma.

Sanity gate (+1d lag) on top candidates.
"""
import sys, socket
socket.setdefaulttimeout(15)
sys.path.insert(0, "/Users/rkautsar/personal/scripts/strategy_cpm")

import pandas as pd
import numpy as np
from cpm_live import load_panel, perf_metrics
from ndx_sleeve_live import load_ndx_panel, run_ndx_backtest
from vol_cap import compute_dd_circuit_scale, DD_CIRCUIT_SCALE


def apply_t_plus_1(sleeve_returns, trigger, sig_dates):
    daily_idx = sleeve_returns.index
    trigger_d = trigger.reindex(daily_idx).fillna(False)
    sig_set = set(sig_dates)
    scale = pd.Series(1.0, index=daily_idx)
    state = 1.0
    trips = 0
    for i, day in enumerate(daily_idx):
        if day in sig_set:
            state = 1.0
        scale.iloc[i] = state
        if bool(trigger_d.iloc[i]):
            if state == 1.0:
                trips += 1
            state = 0.0
    return scale * sleeve_returns, trips


# === Lo-Kaminski (2008) cumulative-return stop ===
def trigger_lo_kaminski(sleeve_returns, J_days, gamma):
    """SUM of cumulative log-return over past J trading days < -gamma.
    J in trading days (e.g., 252 ~ 12mo). gamma as positive decimal (0.10 = 10%).
    """
    # cumulative return over past J days = product(1+r) - 1
    cum = (1.0 + sleeve_returns).rolling(J_days).apply(lambda x: x.prod() - 1.0, raw=True)
    return cum < -gamma


# === Wilder (1978) ATR-multiple stop (portfolio adaptation) ===
def trigger_wilder_atr(sleeve_returns, N, K):
    """Trigger when DD from rolling N-day peak > K * ATR_N.
    ATR proxy = N-day SMA of |daily return| (since no OHLC at portfolio level).
    """
    eq = (1.0 + sleeve_returns).cumprod()
    rp = eq.rolling(N, min_periods=1).max()
    dd_pct = eq / rp - 1.0  # negative
    abs_ret = sleeve_returns.abs()
    atr = abs_ret.rolling(N).mean()
    # ATR in "loss percentage" terms; trigger when DD_pct < -K * ATR
    return dd_pct < -K * atr * N  # scale by N to make ATR comparable to N-day DD


def trigger_wilder_atr_v2(sleeve_returns, N, K):
    """Wilder ATR more direct: stop at distance K*ATR below rolling peak,
    where ATR is N-day mean absolute return. ATR is per-day, so K*ATR*sqrt(N)
    matches the window-scale for DD comparability.
    """
    eq = (1.0 + sleeve_returns).cumprod()
    rp = eq.rolling(N, min_periods=1).max()
    dd_pct = eq / rp - 1.0
    abs_ret = sleeve_returns.abs()
    atr = abs_ret.rolling(N).mean()
    return dd_pct < -K * atr * np.sqrt(N)


# === Kase (1991) DevStops (portfolio adaptation) ===
def trigger_kase_devstop(sleeve_returns, N, K_sigma):
    """Kase DevStop K_sigma analog: trigger when DD from N-day peak >
    K_sigma standard deviations of return range. Std of abs returns over N days,
    scaled by sqrt(N) for window comparability.
    """
    eq = (1.0 + sleeve_returns).cumprod()
    rp = eq.rolling(N, min_periods=1).max()
    dd_pct = eq / rp - 1.0
    abs_ret = sleeve_returns.abs()
    sigma_range = abs_ret.rolling(N).std()
    return dd_pct < -K_sigma * sigma_range * np.sqrt(N)


def metrics_row(label, ret, trips):
    m = perf_metrics(ret)
    cal = m["cagr"] / abs(m["max_drawdown"]) if m["max_drawdown"] != 0 else float("nan")
    return (label, m["sharpe"], m["cagr"] * 100, m["vol"] * 100,
             m["max_drawdown"] * 100, trips, cal)


def print_table(rows, title):
    print("\n" + "=" * 115)
    print(title)
    print("=" * 115)
    print(f"{'Variant':<60} {'Sharpe':>7} {'CAGR':>7} {'Vol':>7} {'MaxDD':>9} {'Trips':>6} {'Calmar':>7}")
    print("-" * 115)
    for r in rows:
        if r[0] == "---":
            print("-" * 115); continue
        print(f"{r[0]:<60} {r[1]:>7.3f} {r[2]:>6.2f}% {r[3]:>6.2f}% {r[4]:>8.2f}% {r[5]:>6d} {r[6]:>7.2f}")
    print("=" * 115)


if __name__ == "__main__":
    panel = load_panel(start=pd.Timestamp("1993-01-01"))
    ndx_panel = load_ndx_panel()
    start, end = pd.Timestamp("2008-04-30"), pd.Timestamp("2026-05-22")
    ndx_raw, _ = run_ndx_backtest(panel, ndx_panel, start, end)
    common = ndx_raw.index[(ndx_raw.index >= start) & (ndx_raw.index <= end)]
    ndx_raw = ndx_raw.reindex(common).fillna(0.0)
    sigs = (pd.DataFrame({"x": 1}, index=common).groupby(pd.Grouper(freq="ME")).tail(1).index.tolist())

    rows = []
    rows.append(metrics_row("[REF1] NDX raw (no circuit)", ndx_raw, 0))
    s1 = compute_dd_circuit_scale(ndx_raw, sigs, -0.10, DD_CIRCUIT_SCALE)
    rows.append(metrics_row("[REF2] DD -10%/63d sleeve-equity (PROD)", s1 * ndx_raw, int((s1.diff() < 0).sum())))
    s2 = compute_dd_circuit_scale(ndx_raw, sigs, -0.125, DD_CIRCUIT_SCALE)
    rows.append(metrics_row("[REF3] DD -12.5%/63d (best fixed)", s2 * ndx_raw, int((s2.diff() < 0).sum())))
    rows.append(("---", 0, 0, 0, 0, 0, 0))

    # Lo-Kaminski canonical sweep
    print("\nRunning Lo-Kaminski (2008) cumulative-return stops...")
    for J_days, J_label in [(63, "3mo"), (126, "6mo"), (252, "12mo"), (378, "18mo")]:
        for gamma in [0.04, 0.06, 0.08, 0.10, 0.12, 0.14]:
            trig = trigger_lo_kaminski(ndx_raw, J_days, gamma)
            ret, trips = apply_t_plus_1(ndx_raw, trig, sigs)
            rows.append(metrics_row(f"[LK] J={J_label} ({J_days}d), gamma={gamma*100:.0f}%", ret, trips))
    rows.append(("---", 0, 0, 0, 0, 0, 0))

    # Wilder ATR canonical
    print("Running Wilder (1978) ATR-multiple stops...")
    for N in [14, 21, 63]:
        for K in [2.0, 2.5, 3.0]:
            trig = trigger_wilder_atr_v2(ndx_raw, N, K)
            ret, trips = apply_t_plus_1(ndx_raw, trig, sigs)
            rows.append(metrics_row(f"[WLD] N={N}d, K={K} (DD < -K*ATR*sqrt(N))", ret, trips))
    rows.append(("---", 0, 0, 0, 0, 0, 0))

    # Kase DevStops canonical (1.0, 2.2, 3.6 sigma)
    print("Running Kase (1991) DevStops...")
    for N in [21, 63]:
        for K_sigma in [1.0, 2.2, 3.6]:
            trig = trigger_kase_devstop(ndx_raw, N, K_sigma)
            ret, trips = apply_t_plus_1(ndx_raw, trig, sigs)
            rows.append(metrics_row(f"[KASE] Dev{K_sigma}sigma, N={N}d", ret, trips))

    # Sort the entire table by Sharpe (except REF1-3 always at top)
    refs = [r for r in rows if r[0].startswith("[REF") or r[0] == "---"][:4]  # REF + first ---
    tested = [r for r in rows if not r[0].startswith("[REF") and r[0] != "---"]
    tested.sort(key=lambda r: -r[1])
    final_rows = refs + tested
    print_table(final_rows, "NDX canonical stop-loss rules (honest t+1 MOO, 2008-04 to 2026-05, 10bps)\nSorted by Sharpe within each family.")
