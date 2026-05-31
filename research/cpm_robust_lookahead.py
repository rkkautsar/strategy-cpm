"""Throwaway research: CPM-sleeve execution-realism / lookahead battery.

Read-only analyst harness. Reuses production SIGNAL/WEIGHT fns from cpm_live.py
UNCHANGED; varies only execution timing. Does NOT edit prod or memo.

Battery
-------
1. EXECUTION-DAY LAG (CPM sleeve, clean + extended), 4 conventions using REAL
   yfinance auto_adjust opens cached in /tmp/cpm_open_cache/:
     same_day_moc : signal AND fill at close[T]; new basket earns close[T]->close[T+1]
                    (= production close-to-close convention, optimistic/lookahead-ish).
     t1_moo       : BASELINE; signal at close[T], fill at OPEN of T+1.
                    old basket earns overnight close[T]->open[af], new basket earns
                    intraday open[af]->close[af] (compounded). The memo's claimed model.
     t1_close     : fill at close[T+1]; new basket earns close[T+1]->close[T+2] (skip a session).
     t2_open      : fill at OPEN of T+2; old basket held through close[T]->close[T+1]->open[af2],
                    new basket earns intraday open[af2]->close[af2].
2. TRADING-DAY-OF-MONTH: shift signal/rebal day to month-end +{0,1,2,3} business
   days (close-to-close production accounting); report Sharpe range.
3. LOOKAHEAD AUDIT: code-level PIT confirmation (reported in markdown, not here).

Metrics: Sharpe (primary for this brief), Calmar, MaxDD.
"""
import json
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

OPEN_CACHE = Path("/tmp/cpm_open_cache")
OHLC_TICKERS = ['SPY','QQQ','SPHQ','EFA','EEM','VNQ','GLD','TLT','DBC','SHV','IEF','HYG','TIP']
CLEAN_START = pd.Timestamp("2008-05-30")
EXT_START = pd.Timestamp("1999-03-10")
EVAL_END = pd.Timestamp("2026-05-22")


def load_open_close():
    opens, closes = {}, {}
    for t in OHLC_TICKERS:
        p = OPEN_CACHE / f"{t}.csv"
        if not p.exists():
            continue
        d = pd.read_csv(p, parse_dates=[0], index_col=0)
        opens[t] = d["Open"]
        closes[t] = d["Close"]
    return pd.DataFrame(opens).sort_index(), pd.DataFrame(closes).sort_index()


def cpm_returns(close, daily_ret, start, end, convention, exec_lag,
                intraday=None, overnight=None, sig_offset=0, cost_bps=COST_BPS_PER_SIDE):
    """CPM sleeve daily returns under an explicit execution convention.

    convention: "cc"  -> close-to-close (new basket earns cc on apply_from row)
                "moo" -> overnight(prev w) + intraday(new w) on apply_from row
    exec_lag: 0 => apply_from = first trading day after sig_d
              1 => apply_from = second trading day after sig_d
    sig_offset: business-day shift of the signal/rebal day past month-end (0..3).
    """
    monthly_idx = (pd.DataFrame({"x": 1}, index=close.index)
                   .groupby(pd.Grouper(freq="ME")).tail(1))
    eom = monthly_idx.index[(monthly_idx.index >= start - pd.DateOffset(months=1))
                            & (monthly_idx.index <= end)].tolist()
    # Build signal dates with the business-day offset applied past each month end.
    sigs = []
    for d in eom:
        if sig_offset == 0:
            sd = d
        else:
            fut = close.index[close.index > d]
            if len(fut) <= sig_offset - 1:
                continue
            sd = fut[sig_offset - 1]
        sigs.append(sd)
    sigs = sorted(set(sigs))
    sigs = [s for s in sigs if start - pd.DateOffset(days=40) <= s <= end]

    def apply_from_of(sd):
        fut = close.index[close.index > sd]
        if len(fut) <= exec_lag:
            return None
        return fut[exec_lag]

    hist, prev_w = [], {}
    for i, sd in enumerate(sigs):
        w = compute_target_weights(close, sd)[0]
        af = apply_from_of(sd)
        if af is None:
            continue
        if i + 1 < len(sigs):
            naf = apply_from_of(sigs[i + 1])
            end_apply = naf if naf is not None else end
        else:
            end_apply = end
        hist.append({"af": af, "end": end_apply, "w": w, "pw": prev_w})
        prev_w = w

    cols = sorted({a for h in hist for a in h["w"]} & set(daily_ret.columns))
    df_w = pd.DataFrame(0.0, index=close.index, columns=cols)
    for h in hist:
        mask = (close.index >= h["af"]) & (close.index < h["end"])
        for a, ww in h["w"].items():
            if a in df_w.columns:
                df_w.loc[mask, a] = ww
    ret = (df_w[cols] * daily_ret[cols]).sum(axis=1, min_count=1).fillna(0.0)

    n_real = n_fb = 0
    if convention == "moo":
        for h in hist:
            af = h["af"]
            if af not in ret.index:
                continue
            ok = True
            on_c = 0.0
            for a, ww in h["pw"].items():
                if a not in cols:
                    continue
                if overnight is not None and a in overnight.columns and af in overnight.index \
                        and pd.notna(overnight.at[af, a]):
                    on_c += ww * overnight.at[af, a]
                else:
                    ok = False
            id_c = 0.0
            for a, ww in h["w"].items():
                if a not in cols:
                    continue
                if intraday is not None and a in intraday.columns and af in intraday.index \
                        and pd.notna(intraday.at[af, a]):
                    id_c += ww * intraday.at[af, a]
                else:
                    ok = False
                    id_c += ww * (daily_ret.at[af, a] if pd.notna(daily_ret.at[af, a]) else 0.0)
            ret.loc[af] = (1.0 + on_c) * (1.0 + id_c) - 1.0
            n_real += int(ok)
            n_fb += int(not ok)

    for i, h in enumerate(hist):
        pw = hist[i - 1]["w"] if i > 0 else {}
        cw = h["w"]
        keys = set(cw) | set(pw)
        turnover = sum(abs(cw.get(k, 0.0) - pw.get(k, 0.0)) for k in keys)
        cost = turnover * cost_bps / 10000.0
        if h["af"] in ret.index:
            ret.loc[h["af"]] -= cost

    return ret.loc[(ret.index >= start) & (ret.index <= end)], (n_real, n_fb)


def metr(daily, cash):
    m = perf_metrics(daily, cash)
    return {"sharpe": m.get("sharpe"), "cagr": m.get("cagr"),
            "maxdd": m.get("max_drawdown"), "calmar": m.get("calmar"), "vol": m.get("vol")}


def main():
    panel = load_panel(start=EXT_START, end=EVAL_END)
    end = min(EVAL_END, panel.index[-1])
    cash_daily = panel["SHV"].ffill().pct_change().dropna()

    cols = sorted(set(RISKY_UNIVERSE + SAFE_POOL + CANARY_ASSETS + [DEFAULT_CASH]) & set(panel.columns))
    close = panel[cols]
    daily_ret = close.ffill().pct_change()

    open_df, close_yf = load_open_close()
    intraday = (close_yf / open_df - 1.0).reindex(panel.index)
    overnight = (open_df / close_yf.shift(1) - 1.0).reindex(panel.index)

    results = {"meta": {"panel_start": str(panel.index[0].date()),
                        "panel_end": str(panel.index[-1].date()),
                        "clean_start": str(CLEAN_START.date()),
                        "ext_start": str(EXT_START.date()),
                        "eval_end": str(end.date()),
                        "cost_bps_per_side": COST_BPS_PER_SIDE}}

    # ---- PART 1: execution-day lag, CPM sleeve, 4 conventions ----
    convs = [
        ("same_day_moc", "cc", 0),   # production close-to-close (optimistic same-day)
        ("t1_moo",       "moo", 0),  # BASELINE realistic next-day open
        ("t1_close",     "cc", 1),   # fill at close[T+1]
        ("t2_open",      "moo", 1),  # fill at open[T+2]
    ]
    part1 = {}
    for win, ws in [("clean", CLEAN_START), ("ext", EXT_START)]:
        part1[win] = {}
        for name, conv, lag in convs:
            r, fb = cpm_returns(close, daily_ret, ws, end, conv, lag,
                                intraday, overnight)
            part1[win][name] = {**metr(r, cash_daily), "moo_real": fb[0], "moo_fallback": fb[1]}
    results["part1_exec_lag"] = part1

    # ---- SANITY: production close-to-close vs same_day_moc harness ----
    from cpm_live import run_cpm_backtest
    prod, _ = run_cpm_backtest(panel, CLEAN_START, end, cost_bps=COST_BPS_PER_SIDE)
    results["sanity"] = {
        "prod_engine": metr(prod, cash_daily),
        "harness_same_day_moc_clean": part1["clean"]["same_day_moc"],
    }

    # ---- PART 2: trading-day-of-month shift (close-to-close, exec_lag=0) ----
    part2 = {}
    for win, ws in [("clean", CLEAN_START), ("ext", EXT_START)]:
        part2[win] = {}
        for off in [0, 1, 2, 3]:
            r, _ = cpm_returns(close, daily_ret, ws, end, "cc", 0, sig_offset=off)
            part2[win][f"eom+{off}"] = metr(r, cash_daily)
    results["part2_trading_day_of_month"] = part2

    print(json.dumps(results, indent=2, default=lambda x: None if x is None else float(x)))

    out = ROOT / "research" / "cpm_robust_lookahead_findings.json"
    with open(out, "w") as f:
        json.dump(results, f, indent=2, default=lambda x: None if x is None else float(x))
    print(f"\nSaved {out}")


if __name__ == "__main__":
    main()
