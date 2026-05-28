"""
NDX per-stock intramonth stop loss. Each held stock has its own daily stop;
when it fires, that 20% slot rotates to best_safe until next monthly rebal.

All variants use honest t+1 MOO execution.

Stop signals per stock:
  P1. EMA50 < EMA200 on stock price (death cross style)
  P2. EMA20 < EMA50 on stock price
  P3. SMA50 < SMA200 on stock price (classic death cross)
  P4. 13612W < 0 on stock price (daily-anchored BAA momentum)
  P5. DD < -K * sigma * sqrt(N) on stock equity (vol-units, same as sleeve version)
  P6. DD <= -P% from rolling 63d peak (fixed % per stock)
  P7. Stock close <= 20-day low STRICT (Donchian breakdown per stock)

Sanity gate: +1d lag on top candidates.
"""
import sys, socket
socket.setdefaulttimeout(15)
sys.path.insert(0, "/Users/rkautsar/personal/scripts/strategy_cpm")

import pandas as pd
import numpy as np
from cpm_live import load_panel, perf_metrics, sig_13612U, best_safe
from ndx_sleeve_live import (
    load_ndx_panel, compute_ndx_weights, SAFE_POOL, CASH_TICKER,
    COST_BPS_PER_SIDE, SELECT_K,
)


def get_monthly_history(cpm_panel, ndx_panel, start, end):
    """Recompute the monthly picks history for the NDX sleeve. Returns list of
    {sig_d, sig_d_apply_from, target_weights, safe_pick, selected_stocks}."""
    full_panel = cpm_panel.join(ndx_panel, how="outer", rsuffix="_dup")
    full_panel = full_panel.loc[:, ~full_panel.columns.str.endswith("_dup")]
    monthly_idx = pd.DataFrame({"x": 1}, index=full_panel.index).groupby(
        pd.Grouper(freq="ME")).tail(1).index
    sig_dates = monthly_idx[(monthly_idx >= start) & (monthly_idx <= end)]
    history = []
    for sd in sig_dates:
        target, regime, diag = compute_ndx_weights(cpm_panel, ndx_panel, sd)
        next_loc = full_panel.index.get_indexer([sd], method="bfill")[0] + 1
        if next_loc < len(full_panel.index):
            apply_from = full_panel.index[next_loc]
        else:
            continue
        # Identify safe pick: largest non-stock weight in target
        stocks = [t for t in target if t in ndx_panel.columns]
        safes = [t for t in target if t in SAFE_POOL or t == CASH_TICKER]
        if safes:
            safe = safes[0]
        else:
            cpm_monthly = cpm_panel.loc[:sd].resample("ME").last()
            from ndx_sleeve_live import _pick_safe
            safe = _pick_safe(cpm_monthly)
        history.append({
            "sig_d": sd, "apply_from": apply_from,
            "target": target, "safe": safe, "stocks": stocks,
            "regime": regime,
        })
    return history, full_panel


def compute_per_stock_trigger(stock_price_series, signal_kind, **params):
    """Return bool series: True when per-stock trigger fires (defensive)."""
    p = stock_price_series.ffill()
    if signal_kind == "ema_cross":
        fast = params.get("fast", 50)
        slow = params.get("slow", 200)
        return p.ewm(span=fast, adjust=False).mean() < p.ewm(span=slow, adjust=False).mean()
    if signal_kind == "sma_cross":
        fast = params.get("fast", 50)
        slow = params.get("slow", 200)
        return p.rolling(fast).mean() < p.rolling(slow).mean()
    if signal_kind == "13612W":
        r1 = p.pct_change(22); r3 = p.pct_change(64); r6 = p.pct_change(127); r12 = p.pct_change(253)
        return ((12*r1 + 4*r3 + 2*r6 + r12) / 19) < 0
    if signal_kind == "13612U":
        r1 = p.pct_change(22); r3 = p.pct_change(64); r6 = p.pct_change(127); r12 = p.pct_change(253)
        return ((r1 + r3 + r6 + r12) / 4) < 0
    if signal_kind == "dd_pct":
        K_pct = params.get("threshold", -0.20)
        peak_window = params.get("peak_window", 63)
        rp = p.rolling(peak_window, min_periods=1).max()
        return (p / rp - 1.0) < K_pct
    if signal_kind == "dd_vol_units":
        K = params.get("K", 1.0)
        peak_window = params.get("peak_window", 63)
        ret = p.pct_change()
        sigma_daily = ret.rolling(peak_window).std()
        sigma_window = sigma_daily * np.sqrt(peak_window)
        rp = p.rolling(peak_window, min_periods=1).max()
        dd = p / rp - 1.0
        return dd < -K * sigma_window
    if signal_kind == "dch20_strict":
        N = params.get("N", 20)
        rolling_low = p.shift(1).rolling(N).min()
        return (p <= rolling_low) & p.notna() & rolling_low.notna()
    raise ValueError(signal_kind)


def run_ndx_with_per_stock_stops(history, full_panel, ndx_panel, start, end,
                                    signal_kind=None, signal_params=None,
                                    cost_bps=COST_BPS_PER_SIDE):
    """Re-run NDX backtest with per-stock intramonth stop loss applied.
    Returns daily returns Series.

    Each held stock has its own trigger evaluated daily.
    When trigger fires at day t, that stock's weight rotates to safe STARTING t+1.
    Reset at next monthly signal date.
    """
    # Precompute per-stock trigger series for every stock that ever appears in picks
    all_stocks = set()
    for h in history:
        all_stocks.update(h["stocks"])
    triggers = {}
    if signal_kind is not None:
        for t in all_stocks:
            if t in ndx_panel.columns:
                triggers[t] = compute_per_stock_trigger(ndx_panel[t], signal_kind,
                                                          **(signal_params or {}))

    daily_rets = pd.Series(0.0, index=full_panel.loc[start:end].index)
    # State: cur_w (current per-asset weights). On each new signal apply_from, reset.
    # Per-stock latched-out set: stocks currently in "stopped out" state intramonth.
    history_by_apply = {h["apply_from"]: h for h in history}
    sig_apply_dates = sorted(history_by_apply.keys())
    sig_apply_set = set(sig_apply_dates)

    cur_w = {CASH_TICKER: 1.0}
    cur_stocks = []
    cur_safe = CASH_TICKER
    cur_per_slot = 0.0
    stopped_out = set()  # stocks currently in "stopped out" state this month

    for ts in full_panel.loc[start:end].index:
        # Apply new monthly signal if today is an apply_from date
        if ts in sig_apply_set:
            h = history_by_apply[ts]
            new_w = dict(h["target"])
            # Cost on weight changes
            tovr = sum(abs(cur_w.get(a, 0) - new_w.get(a, 0))
                       for a in set(cur_w) | set(new_w))
            daily_rets.loc[ts] -= tovr * cost_bps / 10000.0
            cur_w = new_w
            cur_stocks = list(h["stocks"])
            cur_safe = h["safe"]
            cur_per_slot = 1.0 / SELECT_K if SELECT_K > 0 else 0.0
            stopped_out = set()

        # Intramonth: check per-stock triggers
        if signal_kind is not None and cur_stocks:
            for stk in list(cur_stocks):
                if stk in stopped_out:
                    continue
                if stk in triggers:
                    trig_series = triggers[stk]
                    # SET TODAY's scale based on current state (T+1 MOO: trigger
                    # at t fires defensive starting t+1). So we check trigger
                    # AFTER computing today's return.
                    pass  # check below after computing return

        # Compute today's portfolio return given cur_w
        prev_loc = full_panel.index.get_loc(ts)
        if prev_loc == 0:
            continue
        prev_d = full_panel.index[prev_loc - 1]
        port_r = 0.0
        delisted_w = 0.0
        for asset, w in list(cur_w.items()):
            if asset not in full_panel.columns:
                delisted_w += w
                del cur_w[asset]
                continue
            today = full_panel.loc[ts, asset]
            yest = full_panel.loc[prev_d, asset]
            if pd.notna(today) and pd.notna(yest) and yest > 0:
                port_r += w * (today / yest - 1)
            elif pd.notna(yest) and yest > 0 and pd.isna(today):
                # Delisting haircut (same as production)
                port_r += w * (-0.10)
                delisted_w += w
                del cur_w[asset]
        if delisted_w > 0:
            cur_w[cur_safe] = cur_w.get(cur_safe, 0.0) + delisted_w
        daily_rets.loc[ts] += port_r

        # NOW (after computing today's return), check per-stock triggers for tomorrow
        # i.e. t+1 MOO honest execution: trigger at t fires defensive at t+1
        if signal_kind is not None and cur_stocks:
            for stk in list(cur_stocks):
                if stk in stopped_out:
                    continue
                if stk in triggers:
                    trig_series = triggers[stk]
                    if ts in trig_series.index and bool(trig_series.loc[ts]):
                        # Trigger fires for tomorrow: rotate stk's slot to safe
                        slot_w = cur_w.pop(stk, 0.0)
                        cur_w[cur_safe] = cur_w.get(cur_safe, 0.0) + slot_w
                        # Cost: 2 * 10bps on this slot (sell stk, buy safe)
                        # Applied tomorrow when state changes; for simplicity charge here
                        daily_rets.loc[ts] -= 2.0 * slot_w * cost_bps / 10000.0
                        stopped_out.add(stk)

    return daily_rets


def metrics_row(label, ret):
    m = perf_metrics(ret)
    cal = m["cagr"] / abs(m["max_drawdown"]) if m["max_drawdown"] != 0 else float("nan")
    return (label, m["sharpe"], m["cagr"] * 100, m["vol"] * 100,
             m["max_drawdown"] * 100, cal)


def print_table(rows, title):
    print("\n" + "=" * 110)
    print(title)
    print("=" * 110)
    print(f"{'Variant':<60} {'Sharpe':>7} {'CAGR':>7} {'Vol':>7} {'MaxDD':>9} {'Calmar':>7}")
    print("-" * 110)
    for r in rows:
        if r[0] == "---":
            print("-" * 110); continue
        print(f"{r[0]:<60} {r[1]:>7.3f} {r[2]:>6.2f}% {r[3]:>6.2f}% {r[4]:>8.2f}% {r[5]:>7.2f}")
    print("=" * 110)


if __name__ == "__main__":
    panel = load_panel(start=pd.Timestamp("1993-01-01"))
    ndx_panel = load_ndx_panel()
    start, end = pd.Timestamp("2008-04-30"), pd.Timestamp("2026-05-22")
    print("Building NDX monthly history...")
    history, full_panel = get_monthly_history(panel, ndx_panel, start, end)
    print(f"Got {len(history)} monthly picks. Computing per-stock variants...")

    rows = []
    # Baseline: NDX raw (no circuit)
    base_ret = run_ndx_with_per_stock_stops(history, full_panel, ndx_panel,
                                              start, end, signal_kind=None)
    rows.append(metrics_row("NDX raw (no per-stock stops, reference)", base_ret))

    # Production baseline: sleeve-level DD-10%/63d (honest)
    from vol_cap import compute_dd_circuit_scale, DD_CIRCUIT_SCALE
    sigs = [h["sig_d"] for h in history]
    sleeve_scale = compute_dd_circuit_scale(base_ret, sigs, -0.10, DD_CIRCUIT_SCALE)
    rows.append(metrics_row("Sleeve DD-10%/63d (current prod, honest)", sleeve_scale * base_ret))
    sleeve_scale_125 = compute_dd_circuit_scale(base_ret, sigs, -0.125, DD_CIRCUIT_SCALE)
    rows.append(metrics_row("Sleeve DD-12.5%/63d (best fixed, honest)", sleeve_scale_125 * base_ret))
    rows.append(("---", 0, 0, 0, 0, 0))

    # Per-stock variants
    test_variants = [
        ("[P1] per-stock EMA50<EMA200 (death cross)", "ema_cross", {"fast": 50, "slow": 200}),
        ("[P2] per-stock EMA20<EMA50", "ema_cross", {"fast": 20, "slow": 50}),
        ("[P3] per-stock SMA50<SMA200 (classic death)", "sma_cross", {"fast": 50, "slow": 200}),
        ("[P3b] per-stock SMA20<SMA50", "sma_cross", {"fast": 20, "slow": 50}),
        ("[P4] per-stock 13612W<0", "13612W", {}),
        ("[P5a] per-stock DD-vol K=1.0/63d", "dd_vol_units", {"K": 1.0, "peak_window": 63}),
        ("[P5b] per-stock DD-vol K=1.5/63d", "dd_vol_units", {"K": 1.5, "peak_window": 63}),
        ("[P5c] per-stock DD-vol K=2.0/63d", "dd_vol_units", {"K": 2.0, "peak_window": 63}),
        ("[P6a] per-stock DD<-15%/63d", "dd_pct", {"threshold": -0.15, "peak_window": 63}),
        ("[P6b] per-stock DD<-20%/63d", "dd_pct", {"threshold": -0.20, "peak_window": 63}),
        ("[P6c] per-stock DD<-25%/63d", "dd_pct", {"threshold": -0.25, "peak_window": 63}),
        ("[P7] per-stock DCH20 STRICT", "dch20_strict", {"N": 20}),
    ]
    for label, kind, params in test_variants:
        ret = run_ndx_with_per_stock_stops(history, full_panel, ndx_panel,
                                             start, end, signal_kind=kind, signal_params=params)
        rows.append(metrics_row(label, ret))

    rows[3:] = sorted(rows[3:], key=lambda r: -r[1] if r[0] != "---" else 0)
    print_table(rows, "NDX per-stock intramonth stop-loss sensitivity (HONEST t+1 MOO, 2008-04 to 2026-05, 10bps)\nBaseline is current production sleeve-level DD-10%/63d.")
