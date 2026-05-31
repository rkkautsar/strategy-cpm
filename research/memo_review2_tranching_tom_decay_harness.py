"""Throwaway research harness: memo review-2 items A4 (tranching mitigation) + C
(TOM structural-vs-cyclical decomposition).

Read-only analyst harness. Reuses production SIGNAL/WEIGHT fns from cpm_live.py
UNCHANGED, and the cpm_execution_cliff.py timing harness (gen_sig_dates,
cpm_cc_returns, sharpe_of) UNCHANGED. Does NOT edit prod or memo; does NOT commit.

ANCHOR: CPM clean close-to-close (cc, exec_lag=0) EOM Sharpe ~1.206 (verified
against research/cpm_tom_decay_findings.json: 1.2063). All within-harness
comparisons use the SAME cc/exec_lag=0 convention, so they are apples-to-apples
with the memo's execution-cliff battery.

A4 -- TRANCHING MITIGATION (illustrative, NOT a production change)
-----------------------------------------------------------------
Question: does splitting the monthly rebalance into multiple tranches across
staggered days around month-end REDUCE execution-timing sensitivity (flatten the
cliff) vs single-day execution, trading a little peak Sharpe for robustness?

Model: a "base offset" o shifts the whole tranche schedule relative to EOM.
  - single : tranches = [(o, 1.0)]
  - 2tr    : tranches = [(o, 0.5), (o+1, 0.5)]
  - 3tr    : tranches = [(o, 1/3), (o+1, 1/3), (o+2, 1/3)]
For each consecutive month we transition the held basket from last month's
realised target w_old to this month's target w_new linearly across tranche days:
held = (1-cum_frac)*w_old + cum_frac*w_new. Total turnover (and thus cost) is
identical to single-day; only its placement across days differs.

Robustness metric: for each scheme, compute Sharpe across the base-offset grid
o in {0,1,2,3} (EOM..EOM+3) and report std/range of Sharpe across that grid.
Lower std/range = flatter cliff = more robust to execution-day timing.

C -- TOM STRUCTURAL vs CYCLICAL
-------------------------------
1. Decay SHAPE: TOM day-1 premium (day1_bp, rest_bp, premium=day1-rest) per
   CALENDAR YEAR (noisy: ~11-12 day-1 obs/yr -> wide CIs, flagged) and rolling.
2. REGIME correlation: annual TOM premium vs an equal-vs-cap breadth proxy
   (RSP/SPY 12m relative return). Negative-coincident drop in the breadth-collapse
   regime (2023-26) => cyclical; smooth secular decline independent of breadth
   => structural.
Convention: identical to cpm_execution_cliff/tom_decay (cc, exec_lag=0, 10bps/side).
"""
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cpm_live import (
    load_panel, perf_metrics, compute_target_weights, _fetch_cached_adjusted_close,
    RISKY_UNIVERSE, SAFE_POOL, CANARY_ASSETS, DEFAULT_CASH, COST_BPS_PER_SIDE,
)
from research.cpm_execution_cliff import gen_sig_dates, cpm_cc_returns, sharpe_of

CLEAN_START = pd.Timestamp("2008-05-30")
EXT_START = pd.Timestamp("1999-03-10")
EVAL_END = pd.Timestamp("2026-05-22")


# --------------------------------------------------------------------------
# A4: tranched return engine
# --------------------------------------------------------------------------
def cpm_tranched_returns(close, daily_ret, start, end, tranches,
                         cost_bps=COST_BPS_PER_SIDE):
    """CPM sleeve daily returns under a multi-tranche execution schedule.

    tranches: list of (offset_bdays_from_eom, fraction). Fractions sum to 1.
              offset 0 = EOM, 1 = EOM+1, etc. Each month, the held basket is
              transitioned linearly from last month's realised target to this
              month's target across the tranche days.

    Same accounting as cpm_cc_returns: close-to-close, signal at EOM, cost =
    turnover * cost_bps charged on each tranche execution day. Total turnover
    (and cost) is invariant to tranching -- only placement differs.
    """
    assert abs(sum(f for _, f in tranches) - 1.0) < 1e-9, "fractions must sum to 1"
    idx = close.index
    pos = {d: i for i, d in enumerate(idx)}

    # EOM signal dates with a backfill buffer so the first in-window month is warm.
    eom_dates = [s for s in gen_sig_dates(close, start, end, ("eom", 0))
                 if start - pd.DateOffset(days=75) <= s <= end]

    # Per-month target weights (computed at EOM signal date).
    targets = []
    for sd in eom_dates:
        w = compute_target_weights(close, sd)[0]
        targets.append((sd, w))

    # Build chronological execution events: (exec_day, held_weight_dict).
    events = []
    for m, (eom, w_new) in enumerate(targets):
        w_old = targets[m - 1][1] if m > 0 else {}
        keys = set(w_old) | set(w_new)
        cum = 0.0
        for (off, frac) in tranches:
            p = pos[eom] + off
            if p < 0 or p >= len(idx):
                continue
            cum += frac
            held = {a: (1 - cum) * w_old.get(a, 0.0) + cum * w_new.get(a, 0.0)
                    for a in keys}
            events.append((idx[p], held))
    events.sort(key=lambda x: x[0])

    cols = sorted({a for _, h in events for a in h} & set(daily_ret.columns))
    df_w = pd.DataFrame(0.0, index=idx, columns=cols)

    # Apply each held vector from its exec day until the next exec day.
    for i, (d, held) in enumerate(events):
        nd = events[i + 1][0] if i + 1 < len(events) else end + pd.Timedelta(days=1)
        mask = (idx >= d) & (idx < nd)
        for a, ww in held.items():
            if a in df_w.columns:
                df_w.loc[mask, a] = ww

    ret = (df_w[cols] * daily_ret[cols]).sum(axis=1, min_count=1).fillna(0.0)

    # Cost: turnover between consecutive held vectors, charged on exec day.
    prev_held = {}
    for (d, held) in events:
        keys = set(held) | set(prev_held)
        turnover = sum(abs(held.get(k, 0.0) - prev_held.get(k, 0.0)) for k in keys)
        cost = turnover * cost_bps / 10000.0
        if d in ret.index:
            ret.loc[d] -= cost
        prev_held = held

    sel = (ret.index >= start) & (ret.index <= end)
    return ret.loc[sel]


def metr(daily, cash):
    m = perf_metrics(daily, cash)
    return {"sharpe": _f(m.get("sharpe")), "cagr": _f(m.get("cagr")),
            "maxdd": _f(m.get("max_drawdown")), "calmar": _f(m.get("calmar")),
            "vol": _f(m.get("vol")), "n_days": int(len(daily))}


def _f(x):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else float(x)


def scheme_tranches(name, o):
    if name == "single":
        return [(o, 1.0)]
    if name == "2tr_5050":
        return [(o, 0.5), (o + 1, 0.5)]
    if name == "3tr_thirds":
        return [(o, 1 / 3), (o + 1, 1 / 3), (o + 2, 1 / 3)]
    raise ValueError(name)


# --------------------------------------------------------------------------
# C: annual TOM premium + breadth regime correlation
# --------------------------------------------------------------------------
def annual_tom(ret, dsr, cash):
    """Per-calendar-year TOM day-1 premium decomposition.

    ~11-12 day-1 observations per year -> estimates are NOISY. We report a
    naive 95% CI on day1_bp using the per-year day-1 sample std (t-ish, large
    relative width expected; flagged).
    """
    valid = dsr.notna()
    r = ret[valid]
    d = dsr[valid].astype(int)
    out = {}
    for yr in range(2008, 2027):
        sel = r.index.year == yr
        rv = r[sel]
        dv = d[sel]
        day1 = rv[dv == 1]
        rest = rv[dv > 1]
        if len(day1) < 3:
            continue
        d1_bp = float(day1.mean() * 1e4)
        rest_bp = float(rest.mean() * 1e4) if len(rest) else None
        se = float(day1.std(ddof=1) / np.sqrt(len(day1)) * 1e4) if len(day1) > 1 else None
        out[str(yr)] = {
            "n_day1": int(len(day1)),
            "day1_bp": d1_bp,
            "rest_bp": rest_bp,
            "premium_bp": (d1_bp - rest_bp) if rest_bp is not None else None,
            "day1_bp_se": se,
            "day1_bp_ci95": ([d1_bp - 1.96 * se, d1_bp + 1.96 * se] if se else None),
        }
    return out


def breadth_proxy(start, end):
    """Annual RSP/SPY relative total return as an equal-vs-cap breadth proxy.

    RSP/SPY rising => breadth healthy (equal weight beats cap weight);
    falling => mega-cap-narrow regime. Returns per-year relative return (%).
    """
    rsp = _fetch_cached_adjusted_close("RSP", start, end, "/tmp/cpm_cache")
    spy = _fetch_cached_adjusted_close("SPY", start, end, "/tmp/cpm_cache")
    df = pd.concat({"RSP": rsp, "SPY": spy}, axis=1).ffill().dropna()
    rel = {}
    for yr in range(2004, 2027):
        seg = df[df.index.year == yr]
        if len(seg) < 50:
            continue
        rsp_ret = seg["RSP"].iloc[-1] / seg["RSP"].iloc[0] - 1
        spy_ret = seg["SPY"].iloc[-1] / seg["SPY"].iloc[0] - 1
        rel[str(yr)] = {
            "rsp_ret_pct": float(rsp_ret * 100),
            "spy_ret_pct": float(spy_ret * 100),
            "rsp_minus_spy_pct": float((rsp_ret - spy_ret) * 100),
        }
    return rel


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
        "eval_end": str(end.date()),
        "cost_bps_per_side": COST_BPS_PER_SIDE,
        "convention": "close-to-close (cc), exec_lag handled via tranche offsets; matches cliff battery",
    }}

    # ===================== A4: tranching cliff =====================
    offsets = [0, 1, 2, 3]   # EOM, EOM+1, EOM+2, EOM+3
    schemes = ["single", "2tr_5050", "3tr_thirds"]
    a4 = {"by_scheme": {}, "robustness": {}, "anchor_eom_single": None}
    for name in schemes:
        a4["by_scheme"][name] = {}
        sharpes = []
        for o in offsets:
            tr = scheme_tranches(name, o)
            r = cpm_tranched_returns(close, daily_ret, CLEAN_START, end, tr)
            m = metr(r, cash_daily)
            a4["by_scheme"][name][f"eom+{o}"] = m
            sharpes.append(m["sharpe"])
        arr = np.array(sharpes, dtype=float)
        a4["robustness"][name] = {
            "sharpe_grid_eom_to_eom3": [float(x) for x in arr],
            "mean_sharpe": float(arr.mean()),
            "peak_sharpe": float(arr.max()),
            "min_sharpe": float(arr.min()),
            "std_sharpe": float(arr.std(ddof=0)),
            "range_sharpe": float(arr.max() - arr.min()),
        }
    a4["anchor_eom_single"] = a4["by_scheme"]["single"]["eom+0"]["sharpe"]
    results["A4_tranching"] = a4

    # ===================== C: TOM structural vs cyclical =====================
    ret, dsr = cpm_cc_returns(close, daily_ret, CLEAN_START, end, ("eom", 0))
    c = {"anchor_full_clean_sharpe": sharpe_of(ret, cash_daily)}

    # C1: annual decay shape
    ann = annual_tom(ret, dsr, cash_daily)
    c["C1_annual_tom_premium"] = ann

    # C2: breadth regime correlation
    breadth = breadth_proxy(pd.Timestamp("2003-01-01"), end)
    c["C2_breadth_proxy_rsp_spy"] = breadth

    # correlation: annual premium_bp vs rsp_minus_spy_pct (overlapping years)
    yrs = sorted(set(ann) & set(breadth))
    prem = np.array([ann[y]["premium_bp"] for y in yrs if ann[y]["premium_bp"] is not None])
    brd = np.array([breadth[y]["rsp_minus_spy_pct"] for y in yrs if ann[y]["premium_bp"] is not None])
    d1 = np.array([ann[y]["day1_bp"] for y in yrs if ann[y]["premium_bp"] is not None])
    yrs_used = [y for y in yrs if ann[y]["premium_bp"] is not None]
    corr_prem = float(np.corrcoef(prem, brd)[0, 1]) if len(prem) > 2 else None
    corr_d1 = float(np.corrcoef(d1, brd)[0, 1]) if len(d1) > 2 else None
    c["C2_correlation"] = {
        "years_used": yrs_used,
        "n": len(yrs_used),
        "corr_premium_vs_breadth": corr_prem,
        "corr_day1_vs_breadth": corr_d1,
        "note": "positive corr => TOM premium high when breadth healthy (RSP>SPY) "
                "=> cyclical/regime-linked; near-zero => breadth-independent => structural",
    }

    results["C_tom_structural_vs_cyclical"] = c

    print(json.dumps(results, indent=2, default=_f))
    out = ROOT / "research" / "memo_review2_A4_C_findings.json"
    with open(out, "w") as f:
        json.dump(results, f, indent=2, default=_f)
    print(f"\nSaved {out}")


if __name__ == "__main__":
    main()
