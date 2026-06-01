"""
NDX monthly canary with LQD/IEF — clean re-test (patch bug fixed).

Reimplements compute_ndx_weights with custom canary check so the TIP-only check
doesn't override our custom logic.
"""
import sys, socket, os
socket.setdefaulttimeout(60)
sys.path.insert(0, "/Users/rkautsar/personal/scripts/strategy_cpm")

import pandas as pd
import numpy as np
import yfinance as yf
import ndx_sleeve_live as ndx_mod
from cpm_live import load_panel, perf_metrics, sig_13612U
from ndx_sleeve_live import (
    load_ndx_panel, run_ndx_backtest, SAFE_POOL, CASH_TICKER, SELECT_K,
    COST_BPS_PER_SIDE, _pick_safe,
)
from vol_cap import compute_dd_circuit_scale, DD_CIRCUIT_SCALE
import index_constitution as ic
from bull_spy_live import compute_bull_spy_weights


def fetch_credit():
    cache = "/tmp/ndx_credit_panel.csv"
    if os.path.exists(cache):
        return pd.read_csv(cache, index_col=0, parse_dates=True)
    data = yf.download(["LQD", "HYG", "IEF"], start="2003-01-01", end="2026-05-31",
                        auto_adjust=True, progress=False, threads=True)["Close"]
    data.to_csv(cache)
    return data


def lqd_ief_signals(credit_panel, daily_index):
    """Return dict of sig_date -> (mom_canary, sma50_canary) booleans."""
    lqd = credit_panel["LQD"].reindex(daily_index).ffill()
    ief = credit_panel["IEF"].reindex(daily_index).ffill()
    ratio = lqd / ief
    monthly_ratio = ratio.resample("ME").last()
    sma50 = ratio.rolling(50).mean()
    out_mom = {}
    out_sma50 = {}
    for d in daily_index:
        mon = ratio.loc[:d].resample("ME").last()
        if len(mon) >= 13:
            r1 = mon.iloc[-1] / mon.iloc[-2] - 1
            r3 = mon.iloc[-1] / mon.iloc[-4] - 1
            r6 = mon.iloc[-1] / mon.iloc[-7] - 1
            r12 = mon.iloc[-1] / mon.iloc[-13] - 1
            mom = (r1 + r3 + r6 + r12) / 4
            out_mom[d] = bool(pd.notna(mom) and mom > 0)
        else:
            out_mom[d] = True
        if pd.notna(sma50.loc[d]) and pd.notna(ratio.loc[d]):
            out_sma50[d] = bool(ratio.loc[d] > sma50.loc[d])
        else:
            out_sma50[d] = True
    return out_mom, out_sma50


def compute_ndx_weights_custom_canary(cpm_panel, ndx_panel, sig_d,
                                         canary_check_fn):
    """Reimpl of compute_ndx_weights with PLUGGABLE monthly canary check.

    canary_check_fn(monthly: pd.DataFrame, sig_d: pd.Timestamp) -> bool
    True means risk-on; False means defensive.
    """
    monthly = cpm_panel.loc[:sig_d].resample("ME").last()
    if not canary_check_fn(monthly, sig_d):
        safe = _pick_safe(monthly)
        return ({safe: 1.0}, "NDX_CUSTOM_DEFENSIVE", {"selected": []})

    # Step 2-4 same as original (PIT, GPM, top-K)
    pit = ic.constituents_at("nasdaq100", sig_d.strftime("%Y-%m-%d"))
    pit_tickers = set(pit["symbol"].tolist())
    if len(pit_tickers) == 0:
        bq_weights, bq_regime, _ = compute_bull_spy_weights(cpm_panel, sig_d)
        return (bq_weights, "NDX_FALLBACK_BULL", {"selected": list(bq_weights.keys())})
    monthly = cpm_panel.loc[:sig_d].resample("ME").last()
    available = []
    for t in pit_tickers:
        if t not in ndx_panel.columns:
            continue
        if sig_d in ndx_panel.index and pd.isna(ndx_panel.loc[sig_d, t]):
            continue
        recent = ndx_panel[t].loc[sig_d - pd.Timedelta(days=30):sig_d].dropna()
        if recent.empty:
            continue
        available.append(t)
    daily_rets_lookback = ndx_panel[available].ffill().pct_change().loc[:sig_d].tail(260)
    ew_ret = daily_rets_lookback.mean(axis=1)
    momenta = {}
    for t in available:
        s = ndx_panel[t].resample("ME").last().dropna()
        if len(s) < 13:
            continue
        m = sig_13612U(s)
        if pd.notna(m) and m > 0:
            corr = daily_rets_lookback[t].corr(ew_ret)
            if pd.isna(corr): corr = 0.0
            momenta[t] = m * (1.0 - corr)
    sorted_by_mom = sorted(momenta.items(), key=lambda x: -x[1])
    n_pick = min(len(sorted_by_mom), SELECT_K)
    selected = [t for t, _ in sorted_by_mom[:n_pick]]
    per_slot = 1.0 / SELECT_K
    weights = {t: per_slot for t in selected}
    cash_share = 1.0 - n_pick * per_slot
    if cash_share > 1e-9:
        safe = _pick_safe(monthly)
        weights[safe] = weights.get(safe, 0.0) + cash_share
    regime = "NDX_ACTIVE" if n_pick == SELECT_K else f"NDX_PARTIAL_{n_pick}"
    return (weights, regime, {"selected": selected})


def make_canary_checker(kind, lqd_ief_mom, lqd_ief_sma):
    def chk(monthly, sig_d):
        tip_mom = sig_13612U(monthly["TIP"]) if "TIP" in monthly.columns else float("nan")
        tip_ok = pd.notna(tip_mom) and tip_mom > 0
        lqdief_mom_ok = lqd_ief_mom.get(sig_d, True)
        lqdief_sma_ok = lqd_ief_sma.get(sig_d, True)
        if kind == "TIP_ONLY":
            return tip_ok
        if kind == "TIP_OR_LQDIEF_MOM":
            return tip_ok or lqdief_mom_ok
        if kind == "TIP_AND_LQDIEF_MOM":
            return tip_ok and lqdief_mom_ok
        if kind == "LQDIEF_MOM_ONLY":
            return lqdief_mom_ok
        if kind == "TIP_OR_LQDIEF_SMA":
            return tip_ok or lqdief_sma_ok
        if kind == "TIP_AND_LQDIEF_SMA":
            return tip_ok and lqdief_sma_ok
        if kind == "LQDIEF_SMA_ONLY":
            return lqdief_sma_ok
        raise ValueError(kind)
    return chk


def run_ndx_with_custom_canary(panel, ndx_panel, start, end, canary_kind,
                                  lqd_ief_mom, lqd_ief_sma,
                                  cost_bps=COST_BPS_PER_SIDE):
    """Run NDX with custom monthly canary. Mirrors run_ndx_backtest but with
    canary check pluggable."""
    full_panel = panel.join(ndx_panel, how="outer", rsuffix="_dup")
    full_panel = full_panel.loc[:, ~full_panel.columns.str.endswith("_dup")]
    monthly_idx = pd.DataFrame({"x": 1}, index=full_panel.index).groupby(
        pd.Grouper(freq="ME")).tail(1).index
    sig_dates = monthly_idx[(monthly_idx >= start) & (monthly_idx <= end)]
    chk = make_canary_checker(canary_kind, lqd_ief_mom, lqd_ief_sma)
    daily_rets = pd.Series(0.0, index=full_panel.loc[start:end].index)
    weights_for_date = {}
    for sd in sig_dates:
        target, _, _ = compute_ndx_weights_custom_canary(panel, ndx_panel, sd, chk)
        next_loc = full_panel.index.get_indexer([sd], method="bfill")[0] + 1
        if next_loc < len(full_panel.index):
            weights_for_date[full_panel.index[next_loc]] = target
    exec_dates = sorted(weights_for_date.keys())
    cur_w = {CASH_TICKER: 1.0}
    cur_w_idx = 0
    for ts in full_panel.loc[start:end].index:
        while cur_w_idx < len(exec_dates) and exec_dates[cur_w_idx] <= ts:
            new_w = weights_for_date[exec_dates[cur_w_idx]]
            if cur_w != new_w:
                tovr = sum(abs(cur_w.get(a, 0) - new_w.get(a, 0))
                           for a in set(cur_w) | set(new_w))
                daily_rets.loc[ts] -= tovr * cost_bps / 10000.0
            cur_w = new_w
            cur_w_idx += 1
        prev_loc = full_panel.index.get_loc(ts)
        if prev_loc == 0: continue
        prev_d = full_panel.index[prev_loc - 1]
        market_open = full_panel.loc[ts].notna().sum() > full_panel.loc[ts].isna().sum()
        port_r = 0.0; delisted_w = 0.0
        for asset, w in list(cur_w.items()):
            if asset not in full_panel.columns:
                delisted_w += w; del cur_w[asset]; continue
            today = full_panel.loc[ts, asset]
            yest = full_panel.loc[prev_d, asset]
            if pd.notna(today) and pd.notna(yest) and yest > 0:
                port_r += w * (today / yest - 1)
            elif market_open and pd.notna(yest) and yest > 0 and pd.isna(today):
                port_r += w * (-0.10); delisted_w += w; del cur_w[asset]
        if delisted_w > 0:
            existing_safe = next((s for s in SAFE_POOL if s in cur_w), CASH_TICKER)
            cur_w[existing_safe] = cur_w.get(existing_safe, 0.0) + delisted_w
            if existing_safe in full_panel.columns:
                t_cash = full_panel.loc[ts, existing_safe]
                y_cash = full_panel.loc[prev_d, existing_safe]
                if pd.notna(t_cash) and pd.notna(y_cash) and y_cash > 0:
                    port_r += delisted_w * (t_cash / y_cash - 1)
        daily_rets.loc[ts] += port_r
    return daily_rets


def metrics_line(label, ret, dd_circuit_label=""):
    m = perf_metrics(ret)
    cal = m["cagr"] / abs(m["max_drawdown"]) if m["max_drawdown"] != 0 else float("nan")
    return f"{label:<50} {dd_circuit_label:<25} Sh={m['sharpe']:>6.3f} | CAGR={m['cagr']*100:>6.2f}% | DD={m['max_drawdown']*100:>7.2f}% | Cal={cal:>4.2f}"


if __name__ == "__main__":
    panel = load_panel(start=pd.Timestamp("1993-01-01"))
    ndx_panel = load_ndx_panel()
    credit = fetch_credit()
    start, end = pd.Timestamp("2008-04-30"), pd.Timestamp("2026-05-22")
    monthly_idx = pd.DataFrame({"x": 1}, index=panel.index).groupby(pd.Grouper(freq="ME")).tail(1).index
    sig_dates = monthly_idx[(monthly_idx >= start) & (monthly_idx <= end)]
    lqd_ief_mom, lqd_ief_sma = lqd_ief_signals(credit, sig_dates)

    print("=" * 130)
    print("NDX monthly canary variants (LQD/IEF as additional canary) -- no intramonth circuit")
    print("=" * 130)
    canary_variants = [
        ("TIP_ONLY (current spec)", "TIP_ONLY"),
        ("LQDIEF_MOM_ONLY", "LQDIEF_MOM_ONLY"),
        ("TIP_OR_LQDIEF_MOM", "TIP_OR_LQDIEF_MOM"),
        ("TIP_AND_LQDIEF_MOM", "TIP_AND_LQDIEF_MOM"),
        ("LQDIEF_SMA_ONLY (daily SMA50 at sig_d)", "LQDIEF_SMA_ONLY"),
        ("TIP_OR_LQDIEF_SMA", "TIP_OR_LQDIEF_SMA"),
        ("TIP_AND_LQDIEF_SMA", "TIP_AND_LQDIEF_SMA"),
    ]
    rets = {}
    for label, ck in canary_variants:
        ret = run_ndx_with_custom_canary(panel, ndx_panel, start, end, ck,
                                            lqd_ief_mom, lqd_ief_sma)
        rets[ck] = ret
        print(metrics_line(label, ret, ""))

    print()
    print("=" * 130)
    print("Same monthly canary variants + sleeve DD-10%/63d intramonth circuit")
    print("=" * 130)
    sigs_list = [d for d in sig_dates]
    for label, ck in canary_variants:
        ret = rets[ck]
        scale = compute_dd_circuit_scale(ret, sigs_list, -0.10, DD_CIRCUIT_SCALE)
        ret_circ = scale * ret
        print(metrics_line(label, ret_circ, "+DD-10%/63d"))

    print()
    print("=" * 130)
    print("Same monthly canary variants + LQD/IEF<SMA50 intramonth circuit")
    print("=" * 130)
    # LQD/IEF daily SMA50 as intramonth circuit
    lqd = credit["LQD"]
    ief = credit["IEF"]
    common_idx = panel.index[(panel.index >= start) & (panel.index <= end)]
    ratio_li = (lqd / ief).reindex(common_idx).ffill()
    sma50_trig = ratio_li < ratio_li.rolling(50).mean()

    def apply_t_plus_1(sleeve_ret, trigger, sig_dates_list):
        sig_set = set(sig_dates_list)
        scale = pd.Series(1.0, index=sleeve_ret.index)
        state = 1.0
        for i, day in enumerate(sleeve_ret.index):
            if day in sig_set: state = 1.0
            scale.iloc[i] = state
            if bool(trigger.reindex(sleeve_ret.index).fillna(False).iloc[i]):
                state = 0.0
        return scale * sleeve_ret

    for label, ck in canary_variants:
        ret = rets[ck]
        ret_circ = apply_t_plus_1(ret, sma50_trig, sigs_list)
        print(metrics_line(label, ret_circ, "+LQD/IEF<SMA50"))
