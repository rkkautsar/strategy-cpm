"""
Benchmark comparison: our locked spec vs literature benchmarks.

Our locked spec:
  CPM-ext = AAA Pair-EW Extension (CLEAN-7, TIP-only canary, Faber*(1-corr) GPM,
            504d cov, top-4, partial-safe fallback)
  BULL-ext = HAA-Simple Extension (SPY, HYG OR TIP canary, mom_13612U > 0,
             daily DD circuit at -10% / 63d peak)

Literature benchmarks:
  B1: AAA standard (Butler-Philbrick 2012) on CLEAN-7. Multi-asset min-var across
      top-half by 13612U momentum. No canary.
  B2: AAA + TIP canary on CLEAN-7. AAA selection but with HAA-Simple TIP veto.
  B3: HAA-Simple SPY (Keller 2022 canonical). SPY + TIP canary + SPY mom_13612U.
  B4: HAA-Simple QQQ. Replace SPY with QQQ.
  B5: QQQ 12mo trend (Antonacci GEM single-asset). QQQ if r12 > 0 else IEF.

Blends (60/40 and 60/20/20):
  BB1: 60% B2 + 40% B3
  BB2: 60% B2 + 40% B4
  BB3: 60% B2 + 20% B3 + 20% B4
  BB4: 60% B2 + 20% B3 + 20% B5

Ours:
  OURS_60_40: 60% CPM-ext + 40% BULL-ext
  OURS_60_20_20: 60% CPM-ext + 20% BULL-ext + 20% (placeholder NDX or QQQ-trend)

Clean window: 2008-04-30 to 2026-05-22, 10bps/side, no leverage.
"""
import sys, socket, math
socket.setdefaulttimeout(15)
sys.path.insert(0, "/Users/rkautsar/personal/scripts/strategy_cpm")

import pandas as pd
import numpy as np
from itertools import combinations
from scipy.optimize import minimize
from cpm_live import (
    load_panel, perf_metrics, sig_13612U, faber_sma_xs, min_vol_pair,
    best_safe,
)

CLEAN7 = ["SPY", "EFA", "EEM", "VNQ", "GLD", "TLT", "DBC"]
SAFE = ["SHV", "IEF"]


# ============================================================================
# Shared helpers
# ============================================================================
def monthly_signal_dates(close, start, end):
    monthly_idx = pd.DataFrame({"x": 1}, index=close.index).groupby(pd.Grouper(freq="ME")).tail(1)
    return monthly_idx.index[(monthly_idx.index >= start) & (monthly_idx.index <= end)].tolist()


def build_port(close, weights_history, start, end, cost_bps=10.0):
    common = close.index[(close.index >= start) & (close.index <= end)]
    daily = close.ffill().pct_change()
    port = pd.Series(0.0, index=common)
    state = pd.Series("", index=common, dtype=object)
    for i, (sd, w) in enumerate(weights_history):
        fut = common[common > sd]
        if len(fut) < 1:
            continue
        af = fut[0]
        if i + 1 < len(weights_history):
            nf = common[common > weights_history[i + 1][0]]
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


def min_var_weights(candidates, cov):
    n = len(candidates)
    if n == 0:
        return {}
    if n == 1:
        return {candidates[0]: 1.0}
    csub = cov.loc[candidates, candidates].values
    def obj(w): return np.dot(w, np.dot(csub, w))
    cons = ({"type": "eq", "fun": lambda w: np.sum(w) - 1.0},)
    bnds = tuple((0.0, 1.0) for _ in range(n))
    w0 = np.ones(n) / n
    r = minimize(obj, w0, method="SLSQP", bounds=bnds, constraints=cons)
    if r.success:
        return {candidates[i]: float(r.x[i]) for i in range(n)}
    return {c: 1.0 / n for c in candidates}


# ============================================================================
# B1 / B2: AAA standard, with/without TIP canary
# ============================================================================
def run_aaa(panel, start, end, universe, use_canary, cost_bps=10.0):
    cols = sorted(set(universe + SAFE + (["TIP"] if use_canary else [])) & set(panel.columns))
    close = panel[cols]
    daily = close.ffill().pct_change()
    sig_dates = monthly_signal_dates(close, start, end)
    wh = []
    for sd in sig_dates:
        monthly = close.loc[:sd].resample("ME").last()
        safe = best_safe(monthly, sd, SAFE)
        if use_canary:
            tipm = sig_13612U(monthly["TIP"]) if "TIP" in monthly.columns else -999.0
            if not (pd.notna(tipm) and tipm > 0):
                wh.append((sd, {safe: 1.0}))
                continue
        # AAA selection: rank by 13612U; take top-half with positive momentum
        scores = {t: sig_13612U(monthly[t]) for t in universe if t in monthly.columns}
        scores = {t: s for t, s in scores.items() if pd.notna(s)}
        ranked = sorted(scores.items(), key=lambda x: -x[1])
        top_half = max(2, math.ceil(len(universe) / 2))
        top = [t for t, s in ranked[:top_half] if s > 0]
        if len(top) == 0:
            wh.append((sd, {safe: 1.0}))
            continue
        if len(top) == 1:
            wh.append((sd, {top[0]: 0.5, safe: 0.5}))
            continue
        cov = daily.loc[:sd].tail(504)[top].cov() * 252
        w = min_var_weights(top, cov)
        wh.append((sd, w))
    return build_port(close, wh, start, end, cost_bps)


# ============================================================================
# B3 / B4: HAA-Simple single-asset (SPY or QQQ)
# ============================================================================
def run_haa_simple(panel, start, end, asset, cost_bps=10.0):
    cols = sorted(set([asset] + SAFE + ["TIP"]) & set(panel.columns))
    close = panel[cols]
    sig_dates = monthly_signal_dates(close, start, end)
    wh = []
    for sd in sig_dates:
        monthly = close.loc[:sd].resample("ME").last()
        safe = best_safe(monthly, sd, SAFE)
        tipm = sig_13612U(monthly["TIP"]) if "TIP" in monthly.columns else -999.0
        c_ok = pd.notna(tipm) and tipm > 0
        amom = sig_13612U(monthly[asset]) if asset in monthly.columns else -999.0
        a_ok = pd.notna(amom) and amom > 0
        if c_ok and a_ok:
            wh.append((sd, {asset: 1.0}))
        else:
            wh.append((sd, {safe: 1.0}))
    return build_port(close, wh, start, end, cost_bps)


# ============================================================================
# B5: QQQ 12mo trend (Antonacci GEM single-asset)
# ============================================================================
def run_qqq_trend(panel, start, end, cost_bps=10.0):
    cols = sorted(set(["QQQ"] + SAFE) & set(panel.columns))
    close = panel[cols]
    sig_dates = monthly_signal_dates(close, start, end)
    wh = []
    for sd in sig_dates:
        monthly = close.loc[:sd].resample("ME").last()
        safe = best_safe(monthly, sd, SAFE)
        if "QQQ" in monthly.columns and len(monthly["QQQ"]) >= 13:
            r12 = monthly["QQQ"].iloc[-1] / monthly["QQQ"].iloc[-13] - 1
            if pd.notna(r12) and r12 > 0:
                wh.append((sd, {"QQQ": 1.0}))
                continue
        wh.append((sd, {safe: 1.0}))
    return build_port(close, wh, start, end, cost_bps)


# ============================================================================
# OURS_CPM: AAA Pair-EW + GPM penalty (CLEAN-7, TIP-only)
# ============================================================================
def gpm_faber(monthly, daily, sig_d, universe):
    faber = faber_sma_xs(monthly)
    avail = [t for t in universe if t in faber.index and pd.notna(faber[t])]
    daily_lb = daily.loc[:sig_d].tail(260)
    ew = daily_lb[avail].mean(axis=1)
    out = {}
    for t in avail:
        f = faber[t]
        c = daily_lb[t].corr(ew)
        if pd.isna(c): c = 0.0
        out[t] = f * (1.0 - c)
    return pd.Series(out), faber


def run_ours_cpm(panel, start, end, cost_bps=10.0):
    cols = sorted(set(CLEAN7 + SAFE + ["TIP"]) & set(panel.columns))
    close = panel[cols]
    daily = close.ffill().pct_change()
    sig_dates = monthly_signal_dates(close, start, end)
    wh = []
    for sd in sig_dates:
        monthly = close.loc[:sd].resample("ME").last()
        safe = best_safe(monthly, sd, SAFE)
        tipm = sig_13612U(monthly["TIP"]) if "TIP" in monthly.columns else -999.0
        if not (pd.notna(tipm) and tipm > 0):
            wh.append((sd, {safe: 1.0})); continue
        gpm, faber = gpm_faber(monthly, daily, sd, CLEAN7)
        ranked = gpm.sort_values(ascending=False)
        k = max(2, min(4, len(ranked)))
        top = ranked.iloc[:k]
        pos = top[top.index.map(lambda t: faber.get(t, -np.inf) > 0)]
        if len(pos) == 0:
            wh.append((sd, {safe: 1.0})); continue
        if len(pos) == 1:
            wh.append((sd, {pos.index[0]: 0.5, safe: 0.5})); continue
        cands = list(pos.index)
        pair = min_vol_pair(close.loc[:sd, cands], cands, 504)
        if pair is None or len(pair) < 2:
            wh.append((sd, {cands[0]: 1.0})); continue
        wh.append((sd, {pair[0]: 0.5, pair[1]: 0.5}))
    return build_port(close, wh, start, end, cost_bps)


# ============================================================================
# OURS_BULL: HAA-Simple + HYG OR TIP canary + daily DD circuit at -10%
# ============================================================================
def run_ours_bull(panel, start, end, cost_bps=10.0, dd_thresh=-0.10, dd_lookback=63):
    cols = sorted(set(["SPY", "HYG", "TIP"] + SAFE) & set(panel.columns))
    close = panel[cols]
    daily = close.ffill().pct_change()
    sig_dates = monthly_signal_dates(close, start, end)
    wh = []
    for sd in sig_dates:
        monthly = close.loc[:sd].resample("ME").last()
        safe = best_safe(monthly, sd, SAFE)
        hygm = sig_13612U(monthly["HYG"]) if "HYG" in monthly.columns else -999.0
        tipm = sig_13612U(monthly["TIP"]) if "TIP" in monthly.columns else -999.0
        c_ok = (pd.notna(hygm) and hygm > 0) or (pd.notna(tipm) and tipm > 0)
        spym = sig_13612U(monthly["SPY"]) if "SPY" in monthly.columns else -999.0
        a_ok = pd.notna(spym) and spym > 0
        if c_ok and a_ok:
            wh.append((sd, {"SPY": 1.0}, safe))
        else:
            wh.append((sd, {safe: 1.0}, safe))

    common = close.index[(close.index >= start) & (close.index <= end)]
    spy_close = close["SPY"].reindex(common).ffill()
    spy_peak = spy_close.rolling(dd_lookback, min_periods=1).max()
    spy_dd = spy_close / spy_peak - 1.0

    port = pd.Series(0.0, index=common)
    state = pd.Series("", index=common, dtype=object)
    for i, (sd, w, safe) in enumerate(wh):
        fut = common[common > sd]
        if len(fut) < 1: continue
        af = fut[0]
        if i + 1 < len(wh):
            nf = common[common > wh[i + 1][0]]
            ea = nf[0] if len(nf) >= 1 else common[-1] + pd.Timedelta(days=1)
        else:
            ea = end + pd.Timedelta(days=1)
        mask = (common >= af) & (common < ea)
        holding_spy = "SPY" in w
        tripped = False
        for d in common[mask]:
            if holding_spy and not tripped:
                if d in spy_dd.index and pd.notna(spy_dd.loc[d]) and spy_dd.loc[d] <= dd_thresh:
                    tripped = True
            if holding_spy and not tripped:
                port.loc[d] += daily["SPY"].reindex(common).fillna(0.0).loc[d]
                state.loc[d] = "SPY:1.00"
            else:
                sft = safe if holding_spy else list(w.keys())[0]
                port.loc[d] += daily[sft].reindex(common).fillna(0.0).loc[d] if sft in daily.columns else 0.0
                state.loc[d] = f"{sft}:1.00"
    if cost_bps > 0:
        arr = state.values
        if len(arr) > 1:
            flips = np.where(arr[1:] != arr[:-1])[0] + 1
            for f in flips:
                port.iloc[f] -= 2.0 * cost_bps / 10000.0
    return port


def blend(*series_weights):
    """Blend (series, weight) pairs. Aligns to common index, fills with 0."""
    series_list = [s.fillna(0.0) for s, _ in series_weights]
    weights = [w for _, w in series_weights]
    common_idx = series_list[0].index
    for s in series_list[1:]:
        common_idx = common_idx.intersection(s.index)
    out = pd.Series(0.0, index=common_idx)
    for s, w in zip(series_list, weights):
        out += s.reindex(common_idx).fillna(0.0) * w
    return out


def summary(label, p):
    m = perf_metrics(p)
    calmar = m["cagr"] / abs(m["max_drawdown"]) if m["max_drawdown"] != 0 else float("nan")
    return (label, m["sharpe"], m["cagr"] * 100, m["vol"] * 100, m["max_drawdown"] * 100, calmar)


def alpha_beta_corr(strat, bench):
    """OLS regression r_strat = alpha + beta * r_bench + eps on daily returns.
    Returns (alpha_annualized_pct, beta, correlation).
    """
    common = strat.index.intersection(bench.index)
    s = strat.reindex(common).fillna(0.0).values
    b = bench.reindex(common).fillna(0.0).values
    if len(s) < 2 or np.std(b) < 1e-12:
        return float("nan"), float("nan"), float("nan")
    cov = np.cov(s, b, ddof=1)
    beta = cov[0, 1] / cov[1, 1]
    alpha_daily = np.mean(s) - beta * np.mean(b)
    alpha_ann = alpha_daily * 252 * 100  # to %/yr
    corr = np.corrcoef(s, b)[0, 1]
    return alpha_ann, beta, corr


if __name__ == "__main__":
    panel = load_panel(start=pd.Timestamp("1993-01-01"))
    start = pd.Timestamp("2008-04-30")
    end = pd.Timestamp("2026-05-22")

    # Individuals
    print("Running individual strategies...")
    b1 = run_aaa(panel, start, end, CLEAN7, use_canary=False)
    b2 = run_aaa(panel, start, end, CLEAN7, use_canary=True)
    b3 = run_haa_simple(panel, start, end, "SPY")
    b4 = run_haa_simple(panel, start, end, "QQQ")
    b5 = run_qqq_trend(panel, start, end)
    ocpm = run_ours_cpm(panel, start, end)
    obull = run_ours_bull(panel, start, end)

    # SPY buy-hold reference
    common = panel.index[(panel.index >= start) & (panel.index <= end)]
    spybh = panel["SPY"].ffill().pct_change().reindex(common).fillna(0.0)
    qqqbh = panel["QQQ"].ffill().pct_change().reindex(common).fillna(0.0) if "QQQ" in panel.columns else None

    # Blends
    print("Running blends...")
    bb1 = blend((b2, 0.60), (b3, 0.40))
    bb2 = blend((b2, 0.60), (b4, 0.40))
    bb3 = blend((b2, 0.60), (b3, 0.20), (b4, 0.20))
    bb4 = blend((b2, 0.60), (b3, 0.20), (b5, 0.20))
    ours_60_40 = blend((ocpm, 0.60), (obull, 0.40))
    ours_60_20_20_qqq = blend((ocpm, 0.60), (obull, 0.20), (b4, 0.20))
    ours_60_20_20_qqqtrend = blend((ocpm, 0.60), (obull, 0.20), (b5, 0.20))

    rows = []
    rows.append(summary("SPY buy-hold (reference)", spybh))
    if qqqbh is not None:
        rows.append(summary("QQQ buy-hold (reference)", qqqbh))
    rows.append(("---", 0, 0, 0, 0, 0))
    rows.append(summary("B1: AAA standard (no canary, CLEAN-7)", b1))
    rows.append(summary("B2: AAA + TIP canary (CLEAN-7)", b2))
    rows.append(summary("B3: HAA-Simple SPY", b3))
    rows.append(summary("B4: HAA-Simple QQQ", b4))
    rows.append(summary("B5: QQQ 12mo trend (Antonacci GEM)", b5))
    rows.append(("---", 0, 0, 0, 0, 0))
    rows.append(summary("OURS CPM-ext (AAA Pair-EW + GPM, CLEAN-7, TIP)", ocpm))
    rows.append(summary("OURS BULL-ext (HAA-S + HYG-OR-TIP + DD-10%)", obull))
    rows.append(("---", 0, 0, 0, 0, 0))
    rows.append(summary("BB1: 60% B2 + 40% B3 (AAA / HAA-S SPY)", bb1))
    rows.append(summary("BB2: 60% B2 + 40% B4 (AAA / HAA-S QQQ)", bb2))
    rows.append(summary("BB3: 60% B2 + 20% B3 + 20% B4", bb3))
    rows.append(summary("BB4: 60% B2 + 20% B3 + 20% B5 (QQQ trend)", bb4))
    rows.append(("---", 0, 0, 0, 0, 0))
    rows.append(summary("OURS 60/40 (CPM-ext + BULL-ext)", ours_60_40))
    rows.append(summary("OURS 60/20/20 + HAA-S QQQ", ours_60_20_20_qqq))
    rows.append(summary("OURS 60/20/20 + QQQ-trend", ours_60_20_20_qqqtrend))

    print("\n" + "=" * 115)
    print("BENCHMARK COMPARISON (2008-04 to 2026-05, 10bps/side, no leverage)")
    print("=" * 115)
    print(f"{'Strategy':<55} {'Sharpe':>8} {'CAGR':>8} {'Vol':>8} {'MaxDD':>9} {'Calmar':>8}")
    print("-" * 115)
    for r in rows:
        if r[0] == "---":
            print("-" * 115)
            continue
        print(f"{r[0]:<55} {r[1]:>8.3f} {r[2]:>7.2f}% {r[3]:>7.2f}% {r[4]:>8.2f}% {r[5]:>8.2f}")
    print("=" * 115)

    # Alpha/Beta/Corr decomposition
    pairs = [
        # (strategy, benchmark, strategy_label, bench_label)
        (ocpm, b2,    "CPM-ext",          "vs B2 AAA+TIP (canonical sleeve)"),
        (ocpm, spybh, "CPM-ext",          "vs SPY buy-hold"),
        (obull, b3,   "BULL-ext",         "vs B3 HAA-Simple SPY (canonical sleeve)"),
        (obull, spybh,"BULL-ext",         "vs SPY buy-hold"),
        (ours_60_40, bb1, "OURS 60/40",    "vs BB1 60% AAA+TIP / 40% HAA-S SPY"),
        (ours_60_40, bb4, "OURS 60/40",    "vs BB4 60 AAA / 20 HAA-S SPY / 20 QQQ-trend (best lit)"),
        (ours_60_40, spybh, "OURS 60/40",  "vs SPY buy-hold"),
        (ours_60_20_20_qqqtrend, bb4, "OURS 60/20/20 + QQQ-trend", "vs BB4 (matched 60/20/20)"),
        (ours_60_20_20_qqqtrend, spybh, "OURS 60/20/20 + QQQ-trend", "vs SPY buy-hold"),
    ]

    print("\n" + "=" * 115)
    print("ALPHA / BETA / CORRELATION vs SLEEVE-BENCHMARKS (annualized alpha, daily-return OLS)")
    print("=" * 115)
    print(f"{'Strategy':<28} {'Benchmark':<55} {'Alpha':>9} {'Beta':>8} {'Corr':>8}")
    print("-" * 115)
    for strat, bench, sl, bl in pairs:
        a, b, c = alpha_beta_corr(strat, bench)
        print(f"{sl:<28} {bl:<55} {a:>+8.2f}% {b:>8.3f} {c:>8.3f}")
    print("=" * 115)
