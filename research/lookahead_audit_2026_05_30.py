"""Throwaway research: same-day signal->execution lookahead audit for 60/40 CPM-BULL.

Reuses production SIGNAL/WEIGHT functions unchanged (compute_target_weights,
compute_bull_spy_weights) and ONLY varies the execution-timing of how the
resulting monthly weight vector is applied to daily returns.

Lag convention
--------------
Signal computed at month-end close T using data loc[:T] (inclusive).
daily_ret = close.pct_change(), so the return indexed at day D equals
close[D]/close[D-1]-1 (the move INTO close[D] from the prior close).

  exec_lag=0 (BASELINE, = production today):
      apply_from = future[0] = T+1  (first trading day after T)
      first return earned by new weights = ret[T+1] = close[T+1]/close[T].
      => new basket captures the close[T]->close[T+1] move
      => economically REBALANCED AT close[T] = SAME-DAY-CLOSE fill (MOC).
         You both observe the final close T AND trade at that same close.

  exec_lag=1 (LAGGED, realistic next-bar):
      apply_from = future[1] = T+2
      first return earned by new weights = ret[T+2] = close[T+2]/close[T+1].
      => new basket captures the close[T+1]->close[T+2] move
      => economically REBALANCED AT close[T+1] = one full trading day after
         the signal close = realistic next-day (next-close) execution.

This is the cleanest 1-trading-day shift of the signal->return alignment and
leaves the signal logic itself untouched, isolating the execution-timing effect.
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cpm_live import (
    load_panel, compute_target_weights, perf_metrics,
    RISKY_UNIVERSE, SAFE_POOL, CANARY_ASSETS, DEFAULT_CASH, COST_BPS_PER_SIDE,
)
from bull_spy_live import compute_bull_spy_weights, BULL_TICKER, CASH_TICKER
import bull_spy_live

CPM_W, BULL_W = 0.60, 0.40

# ---------------------------------------------------------------------------
# Generic monthly-gated sleeve backtest with configurable execution lag.
# exec_lag = number of EXTRA trading days beyond future[0].
#   0 -> apply_from = future[0]  (baseline, same-day-close economics)
#   1 -> apply_from = future[1]  (realistic 1-day lag)
# ---------------------------------------------------------------------------

def _segment_returns(close, daily_ret, weight_fn, start, end, exec_lag, cost_bps):
    monthly_idx = (pd.DataFrame({"x": 1}, index=close.index)
                   .groupby(pd.Grouper(freq="ME")).tail(1))
    sigs = monthly_idx.index[(monthly_idx.index >= start) & (monthly_idx.index <= end)].tolist()

    def apply_from_of(sig_d):
        fut = close.index[close.index > sig_d]
        if len(fut) <= exec_lag:
            return None
        return fut[exec_lag]

    weights_history = []
    for i, sig_d in enumerate(sigs):
        w = weight_fn(sig_d)
        af = apply_from_of(sig_d)
        if af is None:
            continue
        if i + 1 < len(sigs):
            naf = apply_from_of(sigs[i + 1])
            end_apply = naf if naf is not None else end
        else:
            end_apply = end
        weights_history.append({"apply_from": af, "end_apply": end_apply,
                                "weights": w, "sig_d": sig_d})

    all_assets = sorted({a for h in weights_history for a in h["weights"]})
    cols = [a for a in all_assets if a in daily_ret.columns]
    df_w = pd.DataFrame(0.0, index=close.index, columns=cols)
    for h in weights_history:
        mask = (close.index >= h["apply_from"]) & (close.index < h["end_apply"])
        for a, ww in h["weights"].items():
            if a in df_w.columns:
                df_w.loc[mask, a] = ww
    ret = (df_w[cols] * daily_ret[cols]).sum(axis=1, min_count=1).fillna(0.0)

    # turnover costs at each apply_from
    for i, h in enumerate(weights_history):
        prev_w = weights_history[i - 1]["weights"] if i > 0 else {}
        curr_w = h["weights"]
        keys = set(curr_w) | set(prev_w)
        turnover = sum(abs(curr_w.get(k, 0.0) - prev_w.get(k, 0.0)) for k in keys)
        cost = turnover * cost_bps / 10000.0
        af = h["apply_from"]
        if af in ret.index:
            ret.loc[af] -= cost
    return ret


def cpm_sleeve(panel, start, end, exec_lag, cost_bps=COST_BPS_PER_SIDE):
    cols = sorted(set(RISKY_UNIVERSE + SAFE_POOL + CANARY_ASSETS + [DEFAULT_CASH]) & set(panel.columns))
    close = panel[cols]
    daily_ret = close.ffill().pct_change()
    wf = lambda sd: compute_target_weights(close, sd)[0]
    r = _segment_returns(close, daily_ret, wf, start, end, exec_lag, cost_bps)
    return r.loc[(r.index >= start) & (r.index <= end)]


def bull_sleeve(panel, start, end, exec_lag, cost_bps=bull_spy_live.COST_BPS_PER_SIDE):
    cols = sorted(set([BULL_TICKER, CASH_TICKER] + list(bull_spy_live.SAFE_POOL) + ["HYG", "TIP"]) & set(panel.columns))
    close = panel[cols]
    daily_ret = panel.ffill().pct_change()
    wf = lambda sd: compute_bull_spy_weights(panel, sd, panel[BULL_TICKER])[0]
    r = _segment_returns(close, daily_ret, wf, start, end, exec_lag, cost_bps)
    return r.loc[(r.index >= start) & (r.index <= end)]


def metrics_row(name, daily, cash_daily):
    m = perf_metrics(daily, cash_daily)
    return {"name": name, "sharpe": m.get("sharpe"), "cagr": m.get("cagr"),
            "maxdd": m.get("max_drawdown"), "calmar": m.get("calmar"),
            "vol": m.get("vol")}


def fmt(rows):
    hdr = f"{'series':<28} {'Sharpe':>7} {'CAGR':>8} {'MaxDD':>8} {'Calmar':>7} {'Vol':>7}"
    out = [hdr, "-" * len(hdr)]
    for r in rows:
        out.append(f"{r['name']:<28} {r['sharpe']:>7.3f} {r['cagr']*100:>7.2f}% "
                   f"{r['maxdd']*100:>7.2f}% {r['calmar']:>7.3f} {r['vol']*100:>6.2f}%")
    return "\n".join(out)


def main():
    end = pd.Timestamp("2026-05-30")
    ext_start = pd.Timestamp("1999-03-10")
    clean_start = pd.Timestamp("2008-05-30")

    panel = load_panel(start=ext_start, end=end)
    end = min(end, panel.index[-1])
    cash_daily = panel["SHV"].ffill().pct_change().dropna()
    print(f"Panel {panel.index[0].date()} -> {panel.index[-1].date()}  ({len(panel)} rows)\n")

    # Run full extended backtest once per (sleeve, lag); slice windows from it.
    series = {}
    for lag in (0, 1):
        cpm = cpm_sleeve(panel, ext_start, end, lag)
        bull = bull_sleeve(panel, ext_start, end, lag)
        common = cpm.index.intersection(bull.index)
        cpm, bull = cpm.reindex(common), bull.reindex(common)
        blend = CPM_W * cpm + BULL_W * bull
        series[lag] = {"CPM": cpm, "BULL": bull, "BLEND 60/40": blend}

    windows = {
        "CLEAN 18y (2008-05-30..)": (clean_start, end),
        "EXTENDED ~27y (1999-03-10..)": (ext_start, end),
        "STRESS dot-com (2000-03..2002-10)": (pd.Timestamp("2000-03-01"), pd.Timestamp("2002-10-31")),
        "STRESS GFC (2008-05-30..2009-06-30)": (pd.Timestamp("2008-05-30"), pd.Timestamp("2009-06-30")),
        "STRESS COVID (2020-02-01..2020-04-30)": (pd.Timestamp("2020-02-01"), pd.Timestamp("2020-04-30")),
        "STRESS 2022 (2022-01-01..2022-12-31)": (pd.Timestamp("2022-01-01"), pd.Timestamp("2022-12-31")),
    }

    for wname, (ws, we) in windows.items():
        print("=" * 78)
        print(wname)
        print("=" * 78)
        for sleeve in ("CPM", "BULL", "BLEND 60/40"):
            rows = []
            for lag, label in ((0, "baseline (same-day)"), (1, "lagged (+1d)")):
                s = series[lag][sleeve]
                sl = s.loc[(s.index >= ws) & (s.index <= we)]
                if len(sl) < 5:
                    continue
                rows.append(metrics_row(f"{sleeve} {label}", sl, cash_daily))
            if len(rows) == 2:
                ds = rows[1]["sharpe"] - rows[0]["sharpe"]
                rows.append({"name": f"{sleeve} DELTA(lag-base)", "sharpe": ds,
                             "cagr": rows[1]["cagr"] - rows[0]["cagr"],
                             "maxdd": rows[1]["maxdd"] - rows[0]["maxdd"],
                             "calmar": rows[1]["calmar"] - rows[0]["calmar"],
                             "vol": rows[1]["vol"] - rows[0]["vol"]})
            print(fmt(rows))
            print()
    print("DONE")


if __name__ == "__main__":
    main()
