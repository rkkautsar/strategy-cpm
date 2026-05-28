"""
CPM universe expansion test: add US factor ETFs back (IWF, SPHQ, QQQ, VBR).

Current CPM-ext spec: CLEAN-7 (SPY, EFA, EEM, VNQ, GLD, TLT, DBC).
Test extensions: + IWF, + SPHQ, + QQQ, + VBR (single + combinations).

For each universe variant:
  - Run CPM engine (Faber * (1-corr) ranker, TIP canary, AAA Pair-EW with
    K=ceil(N/2), 504d cov, 50/50 pair). Use current cpm_live.run_cpm_backtest
    with monkey-patched RISKY_UNIVERSE and TOP_K_CANDIDATES.
  - Also run AAA + TIP canary reference (continuous min-var multi-asset) on
    same universe to anchor per-universe alpha decomposition.
  - Compute Sharpe/CAGR/MaxDD/Calmar of standalone CPM-ext on that universe.
  - Compute PROD blend (60 CPM + 20 BULL + 20 NDX with LQD/IEF circuit).
  - Compute alpha/beta/corr vs (1) per-universe AAA+TIP, (2) BB4 lit blend.
"""
import sys, socket, math
socket.setdefaulttimeout(15)
sys.path.insert(0, "/Users/rkautsar/personal/scripts/strategy_cpm")

import pandas as pd
import numpy as np
import cpm_live as cl
from cpm_live import load_panel, perf_metrics
from bull_qqq_live import run_bull_qqq_backtest
from ndx_sleeve_live import load_ndx_panel, run_ndx_backtest
from vol_cap import compute_lqd_ief_circuit_scale, LQD_IEF_SMA_WINDOW

CLEAN7 = ["SPY", "EFA", "EEM", "VNQ", "GLD", "TLT", "DBC"]

UNIVERSE_VARIANTS = {
    "CLEAN-7 (current)":              CLEAN7,
    "CLEAN-7 + QQQ":                  CLEAN7 + ["QQQ"],
    "CLEAN-7 + IWF":                  CLEAN7 + ["IWF"],
    "CLEAN-7 + SPHQ":                 CLEAN7 + ["SPHQ"],
    "CLEAN-7 + VBR":                  CLEAN7 + ["VBR"],
    "CLEAN-7 + QQQ + IWF":            CLEAN7 + ["QQQ", "IWF"],
    "CLEAN-7 + IWF + SPHQ":           CLEAN7 + ["IWF", "SPHQ"],
    "CLEAN-7 + QQQ + SPHQ":           CLEAN7 + ["QQQ", "SPHQ"],
    "CLEAN-7 + QQQ + IWF + SPHQ":     CLEAN7 + ["QQQ", "IWF", "SPHQ"],
    "CLEAN-7 + ALL4 (Q,I,S,V)":       CLEAN7 + ["QQQ", "IWF", "SPHQ", "VBR"],
}


def run_cpm_with_universe(panel, start, end, universe):
    """Patch cl.RISKY_UNIVERSE + TOP_K_CANDIDATES, run, restore."""
    orig_universe = list(cl.RISKY_UNIVERSE)
    orig_topk = cl.TOP_K_CANDIDATES
    try:
        cl.RISKY_UNIVERSE = universe
        cl.TOP_K_CANDIDATES = max(2, math.ceil(len(universe) / 2))
        ret, _ = cl.run_cpm_backtest(panel, start, end)
        return ret
    finally:
        cl.RISKY_UNIVERSE = orig_universe
        cl.TOP_K_CANDIDATES = orig_topk


def run_aaa_tip_on_universe(panel, start, end, universe, cost_bps=10.0):
    """Reference AAA + TIP canary on the same universe (canonical literature)."""
    from cpm_live import sig_13612U, best_safe as _best_safe
    from scipy.optimize import minimize
    SAFE = ["SHV", "IEF"]
    cols = sorted(set(universe + SAFE + ["TIP"]) & set(panel.columns))
    close = panel[cols]
    daily = close.ffill().pct_change()
    monthly_idx = pd.DataFrame({"x": 1}, index=close.index).groupby(pd.Grouper(freq="ME")).tail(1).index
    sig_dates = monthly_idx[(monthly_idx >= start) & (monthly_idx <= end)].tolist()
    wh = []
    for sd in sig_dates:
        monthly = close.loc[:sd].resample("ME").last()
        safe = _best_safe(monthly, sd, SAFE)
        tipm = sig_13612U(monthly["TIP"]) if "TIP" in monthly.columns else float("nan")
        if not (pd.notna(tipm) and tipm > 0):
            wh.append((sd, {safe: 1.0})); continue
        scores = {t: sig_13612U(monthly[t]) for t in universe if t in monthly.columns}
        scores = {t: s for t, s in scores.items() if pd.notna(s)}
        ranked = sorted(scores.items(), key=lambda x: -x[1])
        top_half = max(2, math.ceil(len(universe) / 2))
        top = [t for t, s in ranked[:top_half] if s > 0]
        if not top:
            wh.append((sd, {safe: 1.0})); continue
        if len(top) == 1:
            wh.append((sd, {top[0]: 0.5, safe: 0.5})); continue
        cov = daily.loc[:sd].tail(504)[top].cov() * 252
        n = len(top)
        def obj(w, C=cov.values): return float(np.dot(w, np.dot(C, w)))
        cons = ({"type": "eq", "fun": lambda w: np.sum(w) - 1.0},)
        bnds = tuple((0.0, 1.0) for _ in range(n))
        w0 = np.ones(n) / n
        r = minimize(obj, w0, method="SLSQP", bounds=bnds, constraints=cons)
        weights = {top[i]: float(r.x[i]) for i in range(n)} if r.success else {t: 1.0/n for t in top}
        wh.append((sd, weights))
    common = close.index[(close.index >= start) & (close.index <= end)]
    port = pd.Series(0.0, index=common)
    state = pd.Series("", index=common, dtype=object)
    for i, (sd, w) in enumerate(wh):
        fut = common[common > sd]
        if len(fut) < 1: continue
        af = fut[0]
        if i + 1 < len(wh):
            nf = common[common > wh[i + 1][0]]
            ea = nf[0] if len(nf) >= 1 else common[-1] + pd.Timedelta(days=1)
        else:
            ea = end + pd.Timedelta(days=1)
        mask = (common >= af) & (common < ea)
        for t, ww in w.items():
            if t in daily.columns:
                port.loc[mask] += daily[t].reindex(common).fillna(0.0).loc[mask] * ww
        state.loc[mask] = "|".join(f"{t}:{ww:.2f}" for t, ww in sorted(w.items()))
    if cost_bps > 0:
        arr = state.values
        if len(arr) > 1:
            flips = np.where(arr[1:] != arr[:-1])[0] + 1
            for f in flips:
                port.iloc[f] -= 2.0 * cost_bps / 10000.0
    return port


def alpha_beta_corr(s, b):
    common = s.index.intersection(b.index)
    if len(common) < 30: return (float("nan"),)*3
    sv = s.reindex(common).fillna(0.0).values
    bv = b.reindex(common).fillna(0.0).values
    if np.std(bv) < 1e-12: return (float("nan"),)*3
    cov = np.cov(sv, bv, ddof=1)
    beta = cov[0,1]/cov[1,1]
    alpha = (np.mean(sv) - beta*np.mean(bv)) * 252 * 100
    return alpha, float(beta), float(np.corrcoef(sv, bv)[0, 1])


def ensure_tickers_in_panel(panel, tickers, cache_dir="/tmp/cpm_cache"):
    """Force-fetch any missing tickers via yfinance, merge into panel."""
    import os
    os.makedirs(cache_dir, exist_ok=True)
    missing = [t for t in tickers if t not in panel.columns]
    if not missing:
        return panel
    print(f"Force-fetching missing tickers: {missing}")
    import yfinance as yf
    fetched = {}
    for t in missing:
        cache_path = os.path.join(cache_dir, f"{t}.csv")
        if os.path.exists(cache_path):
            s = pd.read_csv(cache_path, parse_dates=[0], index_col=0).iloc[:, 0]
            s.name = t
            fetched[t] = s
            continue
        d = yf.download(t, start="1995-01-01", auto_adjust=True, progress=False, threads=False)
        if isinstance(d.columns, pd.MultiIndex):
            d = d["Close"]
        c = d["Close"] if "Close" in d.columns else d.iloc[:, 0]
        c = c.dropna(); c.name = t
        c.to_csv(cache_path, header=True)
        fetched[t] = c
    if fetched:
        extras = pd.DataFrame(fetched)
        panel = panel.join(extras, how="outer").sort_index()
    return panel


if __name__ == "__main__":
    panel = load_panel(start=pd.Timestamp("1993-01-01"))
    panel = ensure_tickers_in_panel(panel, ["IWF", "SPHQ", "QQQ", "VBR"])
    ndx_panel = load_ndx_panel()
    start, end = pd.Timestamp("2008-04-30"), pd.Timestamp("2026-05-22")

    # Compute shared sleeves (BULL no circuit; NDX with LQD/IEF circuit)
    print("Computing BULL and NDX once for blend reuse ...")
    bull_raw = run_bull_qqq_backtest(panel, start, end)
    ndx_raw, _ = run_ndx_backtest(panel, ndx_panel, start, end)
    common_idx = bull_raw.index.intersection(ndx_raw.index)
    bull_raw = bull_raw.reindex(common_idx); ndx_raw = ndx_raw.reindex(common_idx).fillna(0.0)
    sigs = (pd.DataFrame({"x": 1}, index=common_idx).groupby(pd.Grouper(freq="ME")).tail(1).index.tolist())
    ndx_scale = compute_lqd_ief_circuit_scale(panel["LQD"], panel["IEF"], common_idx, sigs, sma_window=LQD_IEF_SMA_WINDOW)
    ndx_circ = ndx_scale * ndx_raw

    # BB4 lit blend
    print("Building BB4 reference ...")
    from build_dashboard import bench_bb4_blend
    bb4 = bench_bb4_blend(panel, start, end)

    # Sweep
    print(f"\nUniverse expansion sweep, {len(UNIVERSE_VARIANTS)} variants ...")
    cpm_returns = {}
    aaa_returns = {}
    for label, univ in UNIVERSE_VARIANTS.items():
        # Filter universe to those in panel (to avoid NaN explosions on missing ETFs)
        univ_avail = [t for t in univ if t in panel.columns]
        if len(univ_avail) < len(univ):
            print(f"  WARN: {label}: missing {set(univ) - set(univ_avail)}")
        print(f"  {label} (N={len(univ_avail)}, K={max(2, math.ceil(len(univ_avail)/2))})...", end=" ")
        cpm_returns[label] = run_cpm_with_universe(panel, start, end, univ_avail)
        aaa_returns[label] = run_aaa_tip_on_universe(panel, start, end, univ_avail)
        print("done")

    # Per-universe metrics + alpha decomposition
    print("\n" + "=" * 130)
    print("CPM-ext SLEEVE STANDALONE + ALPHA vs PER-UNIVERSE AAA+TIP (honest t+1 MOO, 2008-04 to 2026-05)")
    print("=" * 130)
    print(f"{'Universe':<32} {'CPM-Sh':>7} {'CPM-CAGR':>9} {'CPM-DD':>9} "
          f"{'AAA-Sh':>7} {'AAA-CAGR':>9} {'Alpha':>8} {'Beta':>6} {'Corr':>6}")
    print("-" * 130)
    rows = []
    for label in UNIVERSE_VARIANTS:
        cpm_r = cpm_returns[label]
        aaa_r = aaa_returns[label]
        m_cpm = perf_metrics(cpm_r); m_aaa = perf_metrics(aaa_r)
        alpha, beta, corr = alpha_beta_corr(cpm_r, aaa_r)
        rows.append((label, m_cpm["sharpe"], m_cpm["cagr"]*100, m_cpm["max_drawdown"]*100,
                       m_aaa["sharpe"], m_aaa["cagr"]*100, alpha, beta, corr))
        print(f"{label:<32} {m_cpm['sharpe']:>7.3f} {m_cpm['cagr']*100:>8.2f}% {m_cpm['max_drawdown']*100:>8.2f}% "
              f"{m_aaa['sharpe']:>7.3f} {m_aaa['cagr']*100:>8.2f}% {alpha:>+7.2f}% {beta:>6.3f} {corr:>6.3f}")
    print("=" * 130)

    # PROD blend with each universe
    print("\n" + "=" * 130)
    print("PROD 60/20/20 BLEND with CPM on each universe (BULL no circuit, NDX with LQD/IEF circuit)")
    print("=" * 130)
    print(f"{'Universe (CPM only)':<32} {'PROD-Sh':>8} {'PROD-CAGR':>10} {'PROD-Vol':>9} "
          f"{'PROD-DD':>9} {'Calmar':>7} {'AvB-Alpha':>10} {'AvB-Beta':>9} {'AvB-Corr':>9}")
    print("-" * 130)
    for label in UNIVERSE_VARIANTS:
        cpm_r = cpm_returns[label]
        common_b = cpm_r.index.intersection(bull_raw.index).intersection(ndx_circ.index)
        blend = (0.60 * cpm_r.reindex(common_b).fillna(0)
                  + 0.20 * bull_raw.reindex(common_b).fillna(0)
                  + 0.20 * ndx_circ.reindex(common_b).fillna(0))
        m = perf_metrics(blend)
        cal = m["cagr"]/abs(m["max_drawdown"]) if m["max_drawdown"] != 0 else float("nan")
        alpha, beta, corr = alpha_beta_corr(blend, bb4)
        delta_sh = m["sharpe"] - rows[0][1] * 0 + 0  # placeholder; we'll show vs current below
        print(f"{label:<32} {m['sharpe']:>8.3f} {m['cagr']*100:>9.2f}% {m['vol']*100:>8.2f}% "
              f"{m['max_drawdown']*100:>8.2f}% {cal:>7.2f} {alpha:>+9.2f}% {beta:>9.3f} {corr:>9.3f}")
    print("=" * 130)
