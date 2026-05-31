# -*- coding: utf-8 -*-
"""Throwaway research (READ-ONLY re: production): CPM robustness sweeps.

Convention: mooex (T+1 MOO exact, real yfinance opens), 10 bps/side, monthly
signal. Clean window 2008-05-30..2026-05-22 (18y), ext 1999-03-10..2026-05-22.

Anchor (must reproduce): CPM clean Sharpe 1.1910 / MaxDD -12.67% / Calmar 1.0615.

Sweeps:
  1. top-K {3,4,5,6} x cov/vol lookback {252,504}   (baseline K=4, lb=504)
  2. ranking/screen momentum: faber_voladj (baseline) vs 13612U vs 12m vs 6m vs 3m
  3. cost {0,5,10,20,30} bps/side                    (baseline 10)
  4. subperiod split-half (~2017) + rolling 36m Sharpe (min/median/max)
  6. weighting: inverse-vol (baseline) vs equal-weight across positives

Start-date sensitivity (#5) intentionally DROPPED (redundant with block-bootstrap
CI + split-half + rolling-36m). Min-variance weighting intentionally NOT tested
(obvious loser, = AAA baseline W-factor in factorial).

Writes research/cpm_robust_param_findings.md (+ .json). No production files touched.
"""
from __future__ import annotations
import sys, json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import exec_lag_moo_validation_2026_05_30 as H
from cpm_live import (
    load_panel, perf_metrics, faber_sma_xs, sig_13612U, best_safe,
    inv_vol_weights, RISKY_UNIVERSE, SAFE_POOL, CANARY_ASSETS, DEFAULT_CASH,
)

CS = pd.Timestamp("2008-05-30")
EXT = pd.Timestamp("1999-03-10")
END = pd.Timestamp("2026-05-22")
SPLIT = pd.Timestamp("2017-01-01")
ANCHOR = {"sharpe": 1.1910, "maxdd": -0.1267, "calmar": 1.0615}

# Baseline knobs
BASE = dict(top_k=4, lookback=504, mom="faber_voladj", weighting="invvol")
COST_BASE = 10


# ---------------------------------------------------------------------------
# Parametrized CPM weight function (mirrors production compute_target_weights,
# with top_k / cov-lookback / momentum-fn / weighting-scheme as knobs).
# ---------------------------------------------------------------------------
def _mom_measure(monthly: pd.DataFrame, mom: str) -> pd.Series:
    """Per-asset momentum measure used for ranking AND positive screen.
    Returns a Series indexed by universe asset (NaN where insufficient history)."""
    cols = [c for c in RISKY_UNIVERSE if c in monthly.columns]
    if mom == "faber_voladj":
        return faber_sma_xs(monthly[cols]) if len(monthly) >= 10 else pd.Series(np.nan, index=cols)
    out = {}
    for t in cols:
        s = monthly[t].dropna()
        if mom == "13612U":
            out[t] = sig_13612U(s)
        elif mom in ("12m", "6m", "3m"):
            n = {"12m": 13, "6m": 7, "3m": 4}[mom]
            out[t] = (s.iloc[-1] / s.iloc[-n] - 1.0) if len(s) >= n else np.nan
        else:
            raise ValueError(mom)
    return pd.Series(out)


def cpm_weights_param(close, sig_d, *, top_k, lookback, mom, weighting):
    monthly = close.loc[:sig_d].resample("ME").last()
    safe = best_safe(monthly, sig_d, SAFE_POOL)

    # Canary (unchanged): HYG OR TIP 13612U positive.
    cscores = [sig_13612U(monthly[c]) for c in CANARY_ASSETS if c in monthly.columns]
    cscores = [s for s in cscores if pd.notna(s)]
    if not cscores or sum(1 for s in cscores if s > 0) == 0:
        return {safe: 1.0}

    measure = _mom_measure(monthly, mom)  # raw momentum / faber distance
    has_price = sig_d in close.index
    avail = [t for t in RISKY_UNIVERSE
             if t in measure.index and pd.notna(measure[t])
             and has_price and pd.notna(close.loc[sig_d].get(t, np.nan))]
    if not avail:
        return {safe: 1.0}

    if mom == "faber_voladj":
        daily_rets = close[avail].ffill().pct_change()
        scores = {}
        for t in avail:
            v = daily_rets[t].loc[:sig_d].tail(252).std() * np.sqrt(252)
            if pd.isna(v) or v < 1e-9:
                v = 1.0
            scores[t] = float(measure[t]) / v
        rank = pd.Series(scores).sort_values(ascending=False)
        screen_val = measure  # positive screen on RAW faber distance
    else:
        rank = measure[avail].sort_values(ascending=False)
        screen_val = measure

    k = max(2, min(top_k, len(rank)))
    top = rank.iloc[:k]
    positive = top[top.index.map(lambda t: screen_val.get(t, -np.inf) > 0)]
    if len(positive) == 0:
        return {safe: 1.0}

    picks = list(positive.index)
    n_picks = len(picks)
    risky_fraction = min(n_picks, top_k) / float(top_k)  # strict-K partial-safe
    safe_fraction = 1.0 - risky_fraction

    if weighting == "invvol":
        rw = inv_vol_weights(close.loc[:sig_d], picks, lookback)
    elif weighting == "equal":
        rw = {t: 1.0 / n_picks for t in picks}
    else:
        raise ValueError(weighting)

    out = {t: w * risky_fraction for t, w in rw.items()}
    if safe_fraction > 0:
        out[safe] = out.get(safe, 0.0) + safe_fraction
    return out


# ---------------------------------------------------------------------------
def run_series(panel, intraday, overnight, *, top_k, lookback, mom, weighting, cost):
    cols = sorted(set(RISKY_UNIVERSE + SAFE_POOL + CANARY_ASSETS + [DEFAULT_CASH]) & set(panel.columns))
    close = panel[cols]
    daily_ret = close.ffill().pct_change()
    wf = lambda sd: cpm_weights_param(close, sd, top_k=top_k, lookback=lookback,
                                      mom=mom, weighting=weighting)
    s, fb = H._segment_returns_conv(close, daily_ret, wf, EXT, END, "mooex",
                                    cost, intraday, overnight)
    return s, fb


def metr(s, cash, lo, hi):
    sub = s.loc[(s.index >= lo) & (s.index <= hi)]
    m = perf_metrics(sub, cash)
    return {"sharpe": m.get("sharpe"), "calmar": m.get("calmar"),
            "maxdd": m.get("max_drawdown"), "cagr": m.get("cagr"), "vol": m.get("vol")}


def rolling_sharpe(s, lo, hi, months=36):
    sub = s.loc[(s.index >= lo) & (s.index <= hi)]
    me = sub.resample("ME").apply(lambda x: (1 + x).prod() - 1)  # monthly returns
    win = months
    vals = []
    for i in range(win, len(me) + 1):
        w = me.iloc[i - win:i]
        mu = w.mean() * 12
        sd = w.std(ddof=0) * np.sqrt(12)
        if sd > 0:
            vals.append(mu / sd)
    if not vals:
        return None
    a = np.array(vals)
    return {"n": len(a), "min": float(a.min()), "median": float(np.median(a)),
            "max": float(a.max())}


def main():
    panel = load_panel(start=EXT, end=END)
    open_df, close_yf = H.load_open_close()
    intraday = (close_yf / open_df - 1.0).reindex(panel.index)
    overnight = (open_df / close_yf.shift(1) - 1.0).reindex(panel.index)
    cash = panel["SHV"].ffill().pct_change()

    results = {"convention": "mooex", "cost_bps_side": COST_BASE,
               "clean_window": [str(CS.date()), str(END.date())],
               "ext_window": [str(EXT.date()), str(END.date())],
               "anchor": ANCHOR}

    # ---- Anchor check (baseline) ----
    base_s, base_fb = run_series(panel, intraday, overnight, cost=COST_BASE, **BASE)
    bclean = metr(base_s, cash, CS, END)
    bext = metr(base_s, cash, EXT, END)
    results["baseline"] = {"clean": bclean, "ext": bext, "fallback": base_fb}
    print("ANCHOR baseline clean: Sharpe %.4f MaxDD %.4f Calmar %.4f (expect 1.1910/-0.1267/1.0615)"
          % (bclean["sharpe"], bclean["maxdd"], bclean["calmar"]))

    bs = bclean["sharpe"]; bc = bclean["calmar"]; bd = bclean["maxdd"]

    def drow(m):
        return dict(m, dS=m["sharpe"] - bs, dC=m["calmar"] - bc, dD=m["maxdd"] - bd)

    # ---- 1. top-K x cov/vol lookback ----
    grid = []
    for k in [3, 4, 5, 6]:
        for lb in [252, 504]:
            s, _ = run_series(panel, intraday, overnight, cost=COST_BASE,
                              top_k=k, lookback=lb, mom="faber_voladj", weighting="invvol")
            c = drow(metr(s, cash, CS, END))
            e = metr(s, cash, EXT, END)
            grid.append({"K": k, "lookback": lb, "clean": c, "ext": e})
            print("K=%d lb=%d  clean S=%.4f C=%.4f DD=%.4f  (dS=%+.4f)  ext S=%.4f"
                  % (k, lb, c["sharpe"], c["calmar"], c["maxdd"], c["dS"], e["sharpe"]))
    results["sweep1_K_lookback"] = grid

    # ---- 2. momentum function ----
    moms = []
    for mom in ["faber_voladj", "13612U", "12m", "6m", "3m"]:
        s, _ = run_series(panel, intraday, overnight, cost=COST_BASE,
                          top_k=4, lookback=504, mom=mom, weighting="invvol")
        c = drow(metr(s, cash, CS, END))
        e = metr(s, cash, EXT, END)
        moms.append({"mom": mom, "clean": c, "ext": e})
        print("mom=%-12s clean S=%.4f C=%.4f DD=%.4f (dS=%+.4f) ext S=%.4f"
              % (mom, c["sharpe"], c["calmar"], c["maxdd"], c["dS"], e["sharpe"]))
    results["sweep2_momentum"] = moms

    # ---- 3. cost ----
    costs = []
    for cb in [0, 5, 10, 20, 30]:
        s, _ = run_series(panel, intraday, overnight, cost=cb, **BASE)
        c = drow(metr(s, cash, CS, END))
        costs.append({"cost_bps": cb, "clean": c})
        print("cost=%2d  clean S=%.4f CAGR=%.4f C=%.4f DD=%.4f (dS=%+.4f)"
              % (cb, c["sharpe"], c["cagr"], c["calmar"], c["maxdd"], c["dS"]))
    results["sweep3_cost"] = costs

    # ---- 4. subperiod + rolling 36m (on baseline series) ----
    h1 = metr(base_s, cash, CS, SPLIT - pd.Timedelta(days=1))
    h2 = metr(base_s, cash, SPLIT, END)
    roll = rolling_sharpe(base_s, CS, END, 36)
    results["sweep4_subperiod"] = {"first_half": h1, "second_half": h2,
                                   "split": str(SPLIT.date()), "rolling36m": roll}
    print("H1 %s..%s S=%.4f C=%.4f DD=%.4f" % (CS.date(), (SPLIT - pd.Timedelta(days=1)).date(),
          h1["sharpe"], h1["calmar"], h1["maxdd"]))
    print("H2 %s..%s S=%.4f C=%.4f DD=%.4f" % (SPLIT.date(), END.date(),
          h2["sharpe"], h2["calmar"], h2["maxdd"]))
    print("rolling36m", roll)

    # ---- 6. weighting scheme ----
    wsch = []
    for w in ["invvol", "equal"]:
        s, _ = run_series(panel, intraday, overnight, cost=COST_BASE,
                          top_k=4, lookback=504, mom="faber_voladj", weighting=w)
        c = drow(metr(s, cash, CS, END))
        e = metr(s, cash, EXT, END)
        wsch.append({"weighting": w, "clean": c, "ext": e})
        print("weighting=%-7s clean S=%.4f C=%.4f DD=%.4f (dS=%+.4f) ext S=%.4f"
              % (w, c["sharpe"], c["calmar"], c["maxdd"], c["dS"], e["sharpe"]))
    results["sweep6_weighting"] = wsch

    out_json = Path(__file__).resolve().parent / "cpm_robust_param_findings.json"
    out_json.write_text(json.dumps(results, indent=2))
    print("\nWROTE", out_json)
    return results


if __name__ == "__main__":
    main()
