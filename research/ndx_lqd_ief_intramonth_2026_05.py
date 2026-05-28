"""
NDX intramonth canary: pure credit spread proxies via duration-cancelling ratios.

LQD/IEF and HYG/IEF strip out interest rate moves (both numerator and denominator
have similar 7-10y duration), leaving cleaner credit-spread / risk-on signal.

Variants:
  [LQD/IEF] family:
    - LQD/IEF DD from 63d peak < -gamma
    - LQD/IEF < SMA50
    - LQD/IEF < SMA200
    - LQD/IEF 13612W < 0
    - LQD/IEF z-score < -K vs 252d

  [HYG/IEF] family:
    Same set on HYG/IEF (broader credit signal, includes default risk premium)

  [LQD/IEF + sleeve DD combo]: OR-gate

References: REF1=raw, REF2=DD-10%/63d (current), REF3=DD-12.5% (best fixed),
  REF4=Lo-Kaminski J=63d gamma=8% (canonical).
"""
import sys, socket, os
socket.setdefaulttimeout(60)
sys.path.insert(0, "/Users/rkautsar/personal/scripts/strategy_cpm")

import pandas as pd
import numpy as np
import yfinance as yf
from cpm_live import load_panel, perf_metrics
from ndx_sleeve_live import load_ndx_panel, run_ndx_backtest
from vol_cap import compute_dd_circuit_scale, DD_CIRCUIT_SCALE


def fetch_credit_panel(start="2003-01-01", end="2026-05-31"):
    cache = "/tmp/ndx_credit_panel.csv"
    if os.path.exists(cache):
        df = pd.read_csv(cache, index_col=0, parse_dates=True)
        if {"LQD", "HYG", "IEF"}.issubset(df.columns):
            return df
    data = yf.download(["LQD", "HYG", "IEF"],
                        start=start, end=end, auto_adjust=True,
                        progress=False, threads=True)["Close"]
    data.to_csv(cache)
    return data


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


def lo_kaminski(sleeve, J, gamma):
    cum = (1.0 + sleeve).rolling(J).apply(lambda x: x.prod() - 1.0, raw=True)
    return cum < -gamma


def metrics_row(label, ret, trips):
    m = perf_metrics(ret)
    cal = m["cagr"] / abs(m["max_drawdown"]) if m["max_drawdown"] != 0 else float("nan")
    return (label, m["sharpe"], m["cagr"] * 100, m["vol"] * 100,
             m["max_drawdown"] * 100, trips, cal)


def signal_family(numerator, denominator, label_prefix, sigs, ndx_raw, rows):
    ratio = numerator / denominator
    # DD from 63d peak
    peak = ratio.rolling(63, min_periods=1).max()
    dd = ratio / peak - 1.0
    for gamma in [0.005, 0.01, 0.015, 0.02, 0.03, 0.05]:
        trig = dd < -gamma
        out, t = apply_t_plus_1(ndx_raw, trig, sigs)
        rows.append(metrics_row(f"[{label_prefix}-DD] ratio DD<-{gamma*100:.1f}%/63d", out, t))
    # MA crossovers on ratio
    for slow in [50, 100, 200]:
        trig = ratio < ratio.rolling(slow).mean()
        out, t = apply_t_plus_1(ndx_raw, trig, sigs)
        rows.append(metrics_row(f"[{label_prefix}-SMA] ratio < SMA{slow}", out, t))
    # Z-score
    z = (ratio - ratio.rolling(252).mean()) / ratio.rolling(252).std()
    for K in [1.0, 1.5, 2.0]:
        trig = z < -K
        out, t = apply_t_plus_1(ndx_raw, trig, sigs)
        rows.append(metrics_row(f"[{label_prefix}-Z] ratio z-score < -{K}", out, t))
    # 13612W
    r1 = ratio.pct_change(22); r3 = ratio.pct_change(64)
    r6 = ratio.pct_change(127); r12 = ratio.pct_change(253)
    trig = ((12*r1 + 4*r3 + 2*r6 + r12) / 19) < 0
    out, t = apply_t_plus_1(ndx_raw, trig, sigs)
    rows.append(metrics_row(f"[{label_prefix}-13612W] ratio 13612W < 0", out, t))


def print_table(rows, title):
    print("\n" + "=" * 120)
    print(title)
    print("=" * 120)
    print(f"{'Variant':<65} {'Sharpe':>7} {'CAGR':>7} {'Vol':>7} {'MaxDD':>9} {'Trips':>6} {'Calmar':>7}")
    print("-" * 120)
    for r in rows:
        if r[0] == "---":
            print("-" * 120); continue
        print(f"{r[0]:<65} {r[1]:>7.3f} {r[2]:>6.2f}% {r[3]:>6.2f}% {r[4]:>8.2f}% {r[5]:>6d} {r[6]:>7.2f}")
    print("=" * 120)


if __name__ == "__main__":
    panel = load_panel(start=pd.Timestamp("1993-01-01"))
    ndx_panel = load_ndx_panel()
    start, end = pd.Timestamp("2008-04-30"), pd.Timestamp("2026-05-22")
    ndx_raw, _ = run_ndx_backtest(panel, ndx_panel, start, end)
    common = ndx_raw.index[(ndx_raw.index >= start) & (ndx_raw.index <= end)]
    ndx_raw = ndx_raw.reindex(common).fillna(0.0)
    sigs = (pd.DataFrame({"x": 1}, index=common).groupby(pd.Grouper(freq="ME")).tail(1).index.tolist())

    credit = fetch_credit_panel()
    lqd = credit["LQD"].reindex(common).ffill()
    hyg = credit["HYG"].reindex(common).ffill()
    ief = credit["IEF"].reindex(common).ffill()

    print(f"LQD/IEF and HYG/IEF range: {credit.dropna(how='all').index.min().date()} -> {credit.dropna(how='all').index.max().date()}")

    rows = []
    rows.append(metrics_row("[REF1] NDX raw (no circuit)", ndx_raw, 0))
    s_curr = compute_dd_circuit_scale(ndx_raw, sigs, -0.10, DD_CIRCUIT_SCALE)
    rows.append(metrics_row("[REF2] DD -10%/63d sleeve (current prod)", s_curr * ndx_raw, int((s_curr.diff() < 0).sum())))
    s_125 = compute_dd_circuit_scale(ndx_raw, sigs, -0.125, DD_CIRCUIT_SCALE)
    rows.append(metrics_row("[REF3] DD -12.5%/63d sleeve (best fixed)", s_125 * ndx_raw, int((s_125.diff() < 0).sum())))
    out_lk, t_lk = apply_t_plus_1(ndx_raw, lo_kaminski(ndx_raw, 63, 0.08), sigs)
    rows.append(metrics_row("[REF4] Lo-Kaminski J=63d gamma=8%", out_lk, t_lk))
    rows.append(("---", 0, 0, 0, 0, 0, 0))

    # LQD/IEF family (pure IG credit spread)
    signal_family(lqd, ief, "L/I", sigs, ndx_raw, rows)
    rows.append(("---", 0, 0, 0, 0, 0, 0))
    # HYG/IEF family (broader credit + default)
    signal_family(hyg, ief, "H/I", sigs, ndx_raw, rows)
    rows.append(("---", 0, 0, 0, 0, 0, 0))

    # Combos: sleeve DD-10% OR best credit signal
    dd_scale = compute_dd_circuit_scale(ndx_raw, sigs, -0.10, DD_CIRCUIT_SCALE)
    dd_triggered = (dd_scale == 0.0).reindex(common).fillna(False)
    # Find the best LQD/IEF signal from above
    ratio_li = lqd / ief
    peak_li = ratio_li.rolling(63, min_periods=1).max()
    dd_li = ratio_li / peak_li - 1.0
    ratio_hi = hyg / ief
    peak_hi = ratio_hi.rolling(63, min_periods=1).max()
    dd_hi = ratio_hi / peak_hi - 1.0
    for label, trig in [
        ("L/I DD<-1%", dd_li < -0.01),
        ("L/I DD<-2%", dd_li < -0.02),
        ("L/I SMA50", ratio_li < ratio_li.rolling(50).mean()),
        ("H/I DD<-2%", dd_hi < -0.02),
        ("H/I DD<-3%", dd_hi < -0.03),
        ("H/I SMA50", ratio_hi < ratio_hi.rolling(50).mean()),
    ]:
        combo = dd_triggered | trig.reindex(common).fillna(False)
        out, t = apply_t_plus_1(ndx_raw, combo, sigs)
        rows.append(metrics_row(f"[C-OR] [REF DD -10%] OR [{label}]", out, t))

    # Sort tested by Sharpe (keep refs at top)
    refs = []
    core = []
    in_refs = True
    for r in rows:
        if r[0] == "---":
            if in_refs:
                refs.append(r); in_refs = False
            continue
        if r[0].startswith("[REF"):
            refs.append(r)
        else:
            core.append(r)
    core.sort(key=lambda r: -r[1])
    print_table(refs + core,
                 "NDX with LQD/IEF and HYG/IEF credit-spread canaries (honest t+1 MOO, 2008-04 to 2026-05, 10bps)")
