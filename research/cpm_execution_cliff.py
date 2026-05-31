"""Throwaway research: CPM execution-cliff / month-end-reversal attribution.

Read-only analyst harness. Reuses production SIGNAL/WEIGHT fns from cpm_live.py
UNCHANGED; varies only rebalance timing + decomposes return placement. Does NOT
edit prod or memo. Extends research/cpm_robust_lookahead.py.

ANCHOR: CPM clean close-to-close (cc, exec_lag=0) Sharpe ~1.206 at EOM; the
robustness cliff (EOM 1.21 -> EOM+1 1.01 -> +2 0.97 -> +3 0.91) is reproduced
under the SAME cc/exec_lag=0 convention used by part2 of the prior battery, so
within-battery comparisons are apples-to-apples. (t1_moo EOM = 1.191.)

Battery
-------
1. WIDER REBALANCE-DAY: signal/exec at EOM-2, EOM-1, EOM, EOM+1, EOM+2, EOM+3,
   plus a MID-MONTH rebalance (11th business day of month). Sharpe/Calmar/MaxDD.
2. REVERSAL ATTRIBUTION: decompose each config's daily returns by trading-day
   SINCE rebalance (day 1..N), measure share of P&L earned in first 1-5 days vs
   rest; compare EOM (days 1-5 = turn-of-month window) vs mid-month (days 1-5 =
   ordinary mid-month days). Plus "exclude first N days" Sharpe counterfactual.
3. VERDICT in markdown.
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

CLEAN_START = pd.Timestamp("2008-05-30")
EXT_START = pd.Timestamp("1999-03-10")
EVAL_END = pd.Timestamp("2026-05-22")


def gen_sig_dates(close, start, end, rule):
    """Generate signal dates per month under a timing rule.

    rule = ("eom", k): k business days relative to each month-end last trading day.
                       k=0 -> EOM; k>0 -> k days after; k<0 -> |k| days before.
    rule = ("bdom", n): nth business day of each month (n>=1).
    """
    idx = close.index
    kind, n = rule
    if kind == "eom":
        monthly = pd.DataFrame({"x": 1}, index=idx).groupby(pd.Grouper(freq="ME")).tail(1)
        eom = monthly.index.tolist()
        pos = {d: i for i, d in enumerate(idx)}
        sigs = []
        for d in eom:
            p = pos[d] + n
            if 0 <= p < len(idx):
                sigs.append(idx[p])
        return sorted(set(sigs))
    elif kind == "bdom":
        df = pd.DataFrame({"d": idx}, index=idx)
        sigs = []
        for _, grp in df.groupby(pd.Grouper(freq="ME")):
            days = grp.index
            if len(days) >= n:
                sigs.append(days[n - 1])
        return sorted(set(sigs))
    raise ValueError(rule)


def cpm_cc_returns(close, daily_ret, start, end, rule, exec_lag=0,
                   cost_bps=COST_BPS_PER_SIDE):
    """CPM sleeve daily returns, close-to-close accounting, generalized timing.

    Returns (ret, dsr) where:
      ret = daily return series over [start, end]
      dsr = day-since-rebalance label (1-indexed) per day in same window, NaN if flat
    """
    sigs = [s for s in gen_sig_dates(close, start, end, rule)
            if start - pd.DateOffset(days=45) <= s <= end]

    def apply_from(sd):
        fut = close.index[close.index > sd]
        return fut[exec_lag] if len(fut) > exec_lag else None

    hist, prev_w = [], {}
    for i, sd in enumerate(sigs):
        w = compute_target_weights(close, sd)[0]
        af = apply_from(sd)
        if af is None:
            continue
        if i + 1 < len(sigs):
            naf = apply_from(sigs[i + 1])
            end_apply = naf if naf is not None else end
        else:
            end_apply = end
        hist.append({"af": af, "end": end_apply, "w": w, "pw": prev_w})
        prev_w = w

    cols = sorted({a for h in hist for a in h["w"]} & set(daily_ret.columns))
    df_w = pd.DataFrame(0.0, index=close.index, columns=cols)
    dsr = pd.Series(np.nan, index=close.index)
    for h in hist:
        mask = (close.index >= h["af"]) & (close.index < h["end"])
        for a, ww in h["w"].items():
            if a in df_w.columns:
                df_w.loc[mask, a] = ww
        # day-since-rebalance index within this holding period
        hold_days = close.index[mask]
        for j, day in enumerate(hold_days):
            dsr.loc[day] = j + 1
    ret = (df_w[cols] * daily_ret[cols]).sum(axis=1, min_count=1).fillna(0.0)

    for i, h in enumerate(hist):
        pw = hist[i - 1]["w"] if i > 0 else {}
        cw = h["w"]
        keys = set(cw) | set(pw)
        turnover = sum(abs(cw.get(k, 0.0) - pw.get(k, 0.0)) for k in keys)
        cost = turnover * cost_bps / 10000.0
        if h["af"] in ret.index:
            ret.loc[h["af"]] -= cost

    sel = (ret.index >= start) & (ret.index <= end)
    return ret.loc[sel], dsr.loc[sel]


def metr(daily, cash):
    m = perf_metrics(daily, cash)
    return {"sharpe": m.get("sharpe"), "cagr": m.get("cagr"),
            "maxdd": m.get("max_drawdown"), "calmar": m.get("calmar"),
            "vol": m.get("vol"), "n_days": int(len(daily))}


def sharpe_of(daily, cash):
    if daily.empty:
        return None
    vol = daily.std(ddof=0) * np.sqrt(252)
    return float((daily.mean() * 252) / vol) if vol > 0 else None


def attribution(ret, dsr, cash, caps=(1, 2, 3, 5)):
    """Decompose return placement by day-since-rebalance.

    Returns dict with:
      mean daily ret per day-bucket (1..10), and 'rest'
      share of cumulative arithmetic P&L from days 1..C for each cap C
      Sharpe excluding first C days; Sharpe of only first C days
    """
    out = {}
    valid = dsr.notna()
    r = ret[valid]
    d = dsr[valid].astype(int)

    # mean daily return by exact day-since-rebalance (1..10)
    per_day = {}
    for k in range(1, 11):
        rk = r[d == k]
        per_day[f"day{k}"] = {"mean_ret": float(rk.mean()) if len(rk) else None,
                              "n": int(len(rk))}
    out["mean_ret_by_day_since_rebalance"] = per_day

    total_sum = float(r.sum())
    out["total_arith_sum"] = total_sum
    cap_tbl = {}
    for C in caps:
        early = r[d <= C]
        rest = r[d > C]
        share = float(early.sum() / total_sum) if total_sum != 0 else None
        cap_tbl[f"first_{C}"] = {
            "early_arith_sum": float(early.sum()),
            "early_share_of_total": share,
            "early_n_days": int(len(early)),
            "early_mean_daily": float(early.mean()) if len(early) else None,
            "rest_mean_daily": float(rest.mean()) if len(rest) else None,
            "sharpe_excl_first_C": sharpe_of(rest, cash),
            "sharpe_only_first_C": sharpe_of(early, cash),
        }
    out["cap_table"] = cap_tbl
    return out


def main():
    panel = load_panel(start=EXT_START, end=EVAL_END)
    end = min(EVAL_END, panel.index[-1])
    cash_daily = panel["SHV"].ffill().pct_change().dropna()

    cols = sorted(set(RISKY_UNIVERSE + SAFE_POOL + CANARY_ASSETS + [DEFAULT_CASH]) & set(panel.columns))
    close = panel[cols]
    daily_ret = close.ffill().pct_change()

    results = {"meta": {
        "panel_start": str(panel.index[0].date()),
        "panel_end": str(panel.index[-1].date()),
        "clean_start": str(CLEAN_START.date()),
        "ext_start": str(EXT_START.date()),
        "eval_end": str(end.date()),
        "cost_bps_per_side": COST_BPS_PER_SIDE,
        "convention": "close-to-close (cc), exec_lag=0; matches prior part2 battery",
    }}

    configs = [
        ("eom-2", ("eom", -2)),
        ("eom-1", ("eom", -1)),
        ("eom",   ("eom", 0)),
        ("eom+1", ("eom", 1)),
        ("eom+2", ("eom", 2)),
        ("eom+3", ("eom", 3)),
        ("mid_bdom11", ("bdom", 11)),
        ("first_bdom1", ("bdom", 1)),
    ]

    # ---- PART 1: wider rebalance-day battery ----
    part1 = {}
    rets_store = {}
    for win, ws in [("clean", CLEAN_START), ("ext", EXT_START)]:
        part1[win] = {}
        rets_store[win] = {}
        for name, rule in configs:
            r, dsr = cpm_cc_returns(close, daily_ret, ws, end, rule)
            part1[win][name] = metr(r, cash_daily)
            rets_store[win][name] = (r, dsr)
    results["part1_rebalance_day_battery"] = part1

    # ---- PART 2: reversal attribution (clean window) ----
    part2 = {}
    for name in ["eom", "mid_bdom11", "eom+1", "first_bdom1"]:
        r, dsr = rets_store["clean"][name]
        part2[name] = attribution(r, dsr, cash_daily)
    results["part2_attribution_clean"] = part2

    # ext-window attribution for EOM vs mid only (robustness of the pattern)
    part2_ext = {}
    for name in ["eom", "mid_bdom11"]:
        r, dsr = rets_store["ext"][name]
        part2_ext[name] = attribution(r, dsr, cash_daily)
    results["part2_attribution_ext"] = part2_ext

    print(json.dumps(results, indent=2, default=lambda x: None if x is None else float(x)))
    out = ROOT / "research" / "cpm_execution_cliff_findings.json"
    with open(out, "w") as f:
        json.dump(results, f, indent=2, default=lambda x: None if x is None else float(x))
    print(f"\nSaved {out}")


if __name__ == "__main__":
    main()
