"""
BULL-ext: unify on 13612W trend filter (monthly + optionally daily intramonth).

Variants on the live BULL engine:
  A.  Baseline current: monthly 13612U canary + 13612U asset_mom, NO intramonth defense
  B.  Current live: A + sleeve-equity DD-10%/63d intramonth
  C.  M4 proposal: A + daily 13612W < 0 intramonth canary
  D.  Monthly-only 13612W: monthly 13612W canary + 13612W asset_mom, NO intramonth
  E.  Monthly 13612W + daily 13612W intramonth (D + C)
  F.  Hybrid: monthly 13612U + monthly asset_mom 13612W (asset gate only upgraded)
  G.  F + daily 13612W intramonth

All canaries are HYG OR TIP (BULL spec). Window 2008-04-30 to 2026-05-22, 10bps.
"""
import sys, socket
socket.setdefaulttimeout(15)
sys.path.insert(0, "/Users/rkautsar/personal/scripts/strategy_cpm")

import pandas as pd
import numpy as np
from cpm_live import load_panel, perf_metrics, sig_13612U, best_safe
from vol_cap import compute_dd_circuit_scale, DD_CIRCUIT_THRESHOLD, DD_CIRCUIT_SCALE

SAFE = ["SHV", "IEF"]


def sig_13612W(p):
    """Keller BAA weighted momentum: (12r1 + 4r3 + 2r6 + r12) / 19."""
    p = p.dropna()
    if len(p) < 13:
        return np.nan
    last = p.iloc[-1]
    return ((12 * (last / p.iloc[-2] - 1)) +
             (4 * (last / p.iloc[-4] - 1)) +
             (2 * (last / p.iloc[-7] - 1)) +
             (1 * (last / p.iloc[-13] - 1))) / 19.0


def sig_13612W_daily(p):
    p = p.dropna()
    if len(p) < 253:
        return np.nan
    last = p.iloc[-1]
    r1 = last / p.iloc[-22] - 1
    r3 = last / p.iloc[-64] - 1
    r6 = last / p.iloc[-127] - 1
    r12 = last / p.iloc[-253] - 1
    return (12 * r1 + 4 * r3 + 2 * r6 + 1 * r12) / 19.0


def build_bull(panel, start, end, canary_signal="13612U", asset_signal="13612U",
                cost_bps=10.0):
    """Build BULL with specified monthly signal functions (HYG OR TIP canary)."""
    sig_fn = sig_13612U if canary_signal == "13612U" else sig_13612W
    asset_sig_fn = sig_13612U if asset_signal == "13612U" else sig_13612W

    cols = sorted(set(["SPY", "HYG_stitched", "TIP"] + SAFE) & set(panel.columns))
    close = panel[cols]
    sig_dates = (pd.DataFrame({"x": 1}, index=close.index)
                  .groupby(pd.Grouper(freq="ME")).tail(1).index)
    sig_dates = sig_dates[(sig_dates >= start) & (sig_dates <= end)].tolist()

    wh = []
    state_history = []  # daily T/F for "holding SPY"
    for sd in sig_dates:
        monthly = close.loc[:sd].resample("ME").last()
        safe = best_safe(monthly, sd, SAFE)
        hygm = sig_fn(monthly["HYG_stitched"]) if "HYG_stitched" in monthly.columns else -999
        tipm = sig_fn(monthly["TIP"]) if "TIP" in monthly.columns else -999
        c_ok = (pd.notna(hygm) and hygm > 0) or (pd.notna(tipm) and tipm > 0)
        spym = asset_sig_fn(monthly["SPY"])
        a_ok = pd.notna(spym) and spym > 0
        if c_ok and a_ok:
            wh.append((sd, {"SPY": 1.0}, safe))
        else:
            wh.append((sd, {safe: 1.0}, safe))

    common = panel.index[(panel.index >= start) & (panel.index <= end)]
    daily = close.ffill().pct_change()
    port = pd.Series(0.0, index=common)
    state = pd.Series("", index=common, dtype=object)
    holding_spy = pd.Series(False, index=common)
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
        for t, ww in w.items():
            if t in daily.columns:
                port.loc[mask] += daily[t].reindex(common).fillna(0.0).loc[mask] * ww
        state.loc[mask] = "|".join(f"{t}:{ww:.2f}" for t, ww in sorted(w.items()))
        holding_spy.loc[mask] = ("SPY" in w)

    if cost_bps > 0:
        arr = state.values
        if len(arr) > 1:
            flips = np.where(arr[1:] != arr[:-1])[0] + 1
            for f in flips:
                port.iloc[f] -= 2.0 * cost_bps / 10000.0
    return port, holding_spy, sig_dates


def apply_daily_13612W_circuit(returns, holding_spy, sigs, panel):
    spy_price = panel["SPY"].ffill()
    daily_idx = returns.index
    sig_set = set(sigs)
    scale = pd.Series(1.0, index=daily_idx)
    state = 1.0
    trips = 0
    for i, d in enumerate(daily_idx):
        if d in sig_set:
            state = 1.0
        else:
            if holding_spy.iloc[i] and state == 1.0:
                hist = spy_price.loc[:d]
                sig = sig_13612W_daily(hist)
                if pd.notna(sig) and sig < 0:
                    state = 0.0
                    trips += 1
        scale.iloc[i] = state
    return scale * returns, trips


if __name__ == "__main__":
    panel = load_panel(start=pd.Timestamp("1993-01-01"))
    start = pd.Timestamp("2008-04-30")
    end = pd.Timestamp("2026-05-22")

    # A. Baseline: monthly 13612U, no intramonth
    A, A_state, A_sigs = build_bull(panel, start, end, "13612U", "13612U")

    # B. A + sleeve-equity DD-10%/63d
    B_scale = compute_dd_circuit_scale(A, A_sigs, DD_CIRCUIT_THRESHOLD, DD_CIRCUIT_SCALE)
    B = B_scale * A
    trips_B = int((B_scale.diff() < 0).sum())

    # C. A + daily 13612W intramonth
    C, trips_C = apply_daily_13612W_circuit(A, A_state, A_sigs, panel)

    # D. Monthly 13612W canary + 13612W asset_mom, no intramonth
    D, D_state, D_sigs = build_bull(panel, start, end, "13612W", "13612W")

    # E. D + daily 13612W intramonth
    E, trips_E = apply_daily_13612W_circuit(D, D_state, D_sigs, panel)

    # F. Hybrid: monthly canary 13612U + monthly asset_mom 13612W
    F, F_state, F_sigs = build_bull(panel, start, end, "13612U", "13612W")

    # G. F + daily 13612W intramonth
    G, trips_G = apply_daily_13612W_circuit(F, F_state, F_sigs, panel)

    # H. Monthly canary 13612W + monthly asset 13612U
    H, H_state, H_sigs = build_bull(panel, start, end, "13612W", "13612U")

    rows = [
        ("A. Baseline: monthly 13612U canary+asset, no intramonth", A, 0),
        ("B. A + sleeve-equity DD-10% (current live impl)", B, trips_B),
        ("C. A + daily 13612W intramonth (M4 proposed)", C, trips_C),
        ("D. Monthly 13612W canary+asset, no intramonth", D, 0),
        ("E. D + daily 13612W intramonth (unified)", E, trips_E),
        ("F. Monthly 13612U canary + 13612W asset, no intramonth", F, 0),
        ("G. F + daily 13612W intramonth", G, trips_G),
        ("H. Monthly 13612W canary + 13612U asset, no intramonth", H, 0),
    ]

    print("\n" + "=" * 110)
    print("BULL-ext: 13612W trend filter variants (2008-04 to 2026-05, 10bps)")
    print("=" * 110)
    print(f"{'Variant':<60} {'Sharpe':>8} {'CAGR':>8} {'Vol':>8} {'MaxDD':>9} {'Trips':>6}")
    print("-" * 110)
    for label, p, trips in rows:
        m = perf_metrics(p)
        calmar = m['cagr'] / abs(m['max_drawdown']) if m['max_drawdown'] != 0 else float('nan')
        print(f"{label:<60} {m['sharpe']:>8.3f} {m['cagr']*100:>7.2f}% {m['vol']*100:>7.2f}% "
              f"{m['max_drawdown']*100:>8.2f}% {trips:>6d}")
    print("=" * 110)
