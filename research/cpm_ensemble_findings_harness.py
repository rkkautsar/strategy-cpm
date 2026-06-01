# -*- coding: utf-8 -*-
"""Throwaway analyst harness (READ-ONLY re: production / memo): CPM PARAMETER ENSEMBLE.

Tests the review's central recommendation -- replace the single point-selected
production config (the #1 grid cell, overfit risk) with a small PARAMETER
ENSEMBLE that averages target weights of several sleeves each month. Judged on
FRAGILITY REDUCTION first (EOM-offset stability, turnover/smoothness,
K/ranker independence), not Sharpe maximization.

Reuses production engine via cpm_robust_param_sweep.cpm_weights_param (a
parametrized mirror of cpm_live.compute_target_weights that reproduces the
anchor) and the memo's mooex T+1 MOO harness
(exec_lag_moo_validation_2026_05_30._segment_returns_conv). EOM-offset
stability uses the cc convention + gen_sig_dates from cpm_execution_cliff,
matching the memo's execution-cliff battery (single-day std 0.0560).

ENSEMBLES:
  full  = 0.50 * CoreA + 0.25 * CoreB + 0.25 * CoreC
            CoreA: faber_voladj, K=4, rank252/wt504 (= production)
            CoreB: faber_voladj, K=5, rank252/wt504
            CoreC: 13612U/vol,   K=4, rank252/wt504
  kblend = 0.67 * CoreA + 0.33 * CoreB   (Faber-only K-blend, NO 13612U CoreC)

ANCHOR GATE (must reproduce before analysis):
  single production CoreA => clean Sharpe 1.1910 / MaxDD -12.67% / Calmar 1.0615.

Convention: mooex (T+1 MOO exact) for clean/ext headline metrics + turnover;
cc (exec_lag=0) for the EOM-offset stability battery (apples-to-apples with
the memo cliff numbers). 10 bps/side. Clean 2008-05-30..2026-05-22; ext
1999-03-10..2026-05-22.

Writes research/cpm_ensemble_findings.{md,json}. No production/memo files touched.
"""
from __future__ import annotations
import sys, json
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

from cpm_live import (
    load_panel, perf_metrics, faber_sma_xs, sig_13612U, best_safe, inv_vol_weights,
    RISKY_UNIVERSE, SAFE_POOL, CANARY_ASSETS, DEFAULT_CASH,
)
from cpm_execution_cliff import gen_sig_dates

# NOTE: exec_lag_moo_validation_2026_05_30 (the memo mooex harness) and
# cpm_robust_param_sweep both fail to import now because they reference a
# removed bull_spy_live._vol_gate_ok at module import time. The functions we
# need from them (load_open_close, _segment_returns_conv, cpm_weights_param)
# do NOT depend on that symbol, so they are inlined VERBATIM below to keep the
# mooex T+1 MOO accounting and the parametrized prod-mirror engine identical.

CS = pd.Timestamp("2008-05-30")
EXT = pd.Timestamp("1999-03-10")
END = pd.Timestamp("2026-05-22")
ANCHOR = {"sharpe": 1.1910, "maxdd": -0.1267, "calmar": 1.0615}
ANCHOR_TOL = dict(sharpe=0.01, maxdd=0.01, calmar=0.02)
COST = 10

# ---------------------------------------------------------------------------
# Inlined from exec_lag_moo_validation_2026_05_30.py (load_open_close + the
# mooex segment engine) -- VERBATIM logic, copied only because that module's
# top-level import of bull_spy_live._vol_gate_ok is now broken.
# ---------------------------------------------------------------------------
OPEN_CACHE = Path("/tmp/cpm_open_cache")
OPEN_CACHE_INTRADAY_SANITY_MAX = 0.50
OHLC_TICKERS = ['SPY','QQQ','SPHQ','EFA','EEM','VNQ','GLD','TLT','DBC','SHV','IEF','HYG','TIP']


def _assert_open_cache_adjusted(opens_df, closes_df, threshold=OPEN_CACHE_INTRADAY_SANITY_MAX):
    intraday_abs = (closes_df / opens_df - 1.0).abs().replace([np.inf, -np.inf], np.nan)
    bad = intraday_abs.where(intraday_abs > threshold).stack().dropna()
    if bad.empty:
        return
    dt, ticker = bad.idxmax()
    val = float(bad.max())
    raise ValueError("Open-cache contamination: %s %s |close/open-1|=%.2f%%" % (ticker, pd.Timestamp(dt).date(), val * 100))


def load_open_close():
    opens, closes = {}, {}
    for t in OHLC_TICKERS:
        d = pd.read_csv(OPEN_CACHE / ("%s.csv" % t), parse_dates=[0], index_col=0)
        opens[t] = d["Open"]; closes[t] = d["Close"]
    opens_df = pd.DataFrame(opens).sort_index()
    closes_df = pd.DataFrame(closes).sort_index()
    _assert_open_cache_adjusted(opens_df, closes_df)
    return opens_df, closes_df


def _segment_returns_conv(close, daily_ret, weight_fn, start, end, convention,
                          cost_bps, intraday_ret=None, overnight_ret=None):
    exec_lag = 1 if convention == "moc1" else 0
    monthly_idx = (pd.DataFrame({"x": 1}, index=close.index)
                   .groupby(pd.Grouper(freq="ME")).tail(1))
    sigs = monthly_idx.index[(monthly_idx.index >= start) & (monthly_idx.index <= end)].tolist()

    def apply_from_of(sig_d):
        fut = close.index[close.index > sig_d]
        if len(fut) <= exec_lag:
            return None
        return fut[exec_lag]

    hist = []
    prev_w = {}
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
        hist.append({"apply_from": af, "end_apply": end_apply, "weights": w,
                     "prev_weights": prev_w})
        prev_w = w

    all_assets = sorted({a for h in hist for a in h["weights"]})
    cols = [a for a in all_assets if a in daily_ret.columns]
    df_w = pd.DataFrame(0.0, index=close.index, columns=cols)
    for h in hist:
        mask = (close.index >= h["apply_from"]) & (close.index < h["end_apply"])
        for a, ww in h["weights"].items():
            if a in df_w.columns:
                df_w.loc[mask, a] = ww
    ret = (df_w[cols] * daily_ret[cols]).sum(axis=1, min_count=1).fillna(0.0)

    n_real, n_fallback = 0, 0
    if convention in ("moo", "mooex"):
        for h in hist:
            af = h["apply_from"]
            if af not in ret.index:
                continue
            ok = True

            def cc(a):
                return daily_ret.at[af, a] if a in daily_ret.columns and pd.notna(daily_ret.at[af, a]) else 0.0

            def intra(a):
                nonlocal ok
                if intraday_ret is not None and a in intraday_ret.columns and \
                   af in intraday_ret.index and pd.notna(intraday_ret.at[af, a]):
                    return intraday_ret.at[af, a]
                ok = False
                return None

            def on(a):
                nonlocal ok
                if overnight_ret is not None and a in overnight_ret.columns and \
                   af in overnight_ret.index and pd.notna(overnight_ret.at[af, a]):
                    return overnight_ret.at[af, a]
                ok = False
                return None

            if convention == "moo":
                val = 0.0
                for a, ww in h["weights"].items():
                    if a not in cols:
                        continue
                    iv = intra(a)
                    val += ww * (iv if iv is not None else cc(a))
                ret.loc[af] = val
            else:  # mooex
                on_c = 0.0
                for a, ww in h["prev_weights"].items():
                    if a not in cols:
                        continue
                    ov = on(a)
                    on_c += ww * (ov if ov is not None else 0.0)
                id_c = 0.0
                for a, ww in h["weights"].items():
                    if a not in cols:
                        continue
                    iv = intra(a)
                    id_c += ww * (iv if iv is not None else cc(a))
                ret.loc[af] = (1.0 + on_c) * (1.0 + id_c) - 1.0
            if ok:
                n_real += 1
            else:
                n_fallback += 1

    for i, h in enumerate(hist):
        prev_w = hist[i - 1]["weights"] if i > 0 else {}
        curr_w = h["weights"]
        keys = set(curr_w) | set(prev_w)
        turnover = sum(abs(curr_w.get(k, 0.0) - prev_w.get(k, 0.0)) for k in keys)
        cost = turnover * cost_bps / 10000.0
        af = h["apply_from"]
        if af in ret.index:
            ret.loc[af] -= cost
    return ret.loc[(ret.index >= start) & (ret.index <= end)], (n_real, n_fallback)


# ---------------------------------------------------------------------------
# Inlined from cpm_robust_param_sweep.py (parametrized prod-mirror engine that
# reproduces the anchor) -- VERBATIM logic.
# ---------------------------------------------------------------------------
def _mom_measure(monthly, mom):
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
    cscores = [sig_13612U(monthly[c]) for c in CANARY_ASSETS if c in monthly.columns]
    cscores = [s for s in cscores if pd.notna(s)]
    if not cscores or sum(1 for s in cscores if s > 0) == 0:
        return {safe: 1.0}
    measure = _mom_measure(monthly, mom)
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
        screen_val = measure
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
    risky_fraction = min(n_picks, top_k) / float(top_k)
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
# CoreC sleeve: 13612U/vol ranker (rank = 13612U/vol_252d, positive screen on
# raw 13612U), otherwise identical stack to cpm_weights_param (canary HYG-OR-TIP,
# strict-K partial-safe, inverse-vol wt over surviving positives at wt lookback).
# ---------------------------------------------------------------------------
def weights_13612u_vol(close, sig_d, *, top_k=4, lookback=504):
    monthly = close.loc[:sig_d].resample("ME").last()
    safe = best_safe(monthly, sig_d, SAFE_POOL)

    cscores = [sig_13612U(monthly[c]) for c in CANARY_ASSETS if c in monthly.columns]
    cscores = [s for s in cscores if pd.notna(s)]
    if not cscores or sum(1 for s in cscores if s > 0) == 0:
        return {safe: 1.0}

    cols = [c for c in RISKY_UNIVERSE if c in monthly.columns]
    measure = pd.Series({t: sig_13612U(monthly[t]) for t in cols})  # raw 13612U
    has_price = sig_d in close.index
    avail = [t for t in RISKY_UNIVERSE
             if t in measure.index and pd.notna(measure[t])
             and has_price and pd.notna(close.loc[sig_d].get(t, np.nan))]
    if not avail:
        return {safe: 1.0}

    daily_rets = close[avail].ffill().pct_change()
    scores = {}
    for t in avail:
        v = daily_rets[t].loc[:sig_d].tail(252).std() * np.sqrt(252)
        if pd.isna(v) or v < 1e-9:
            v = 1.0
        scores[t] = float(measure[t]) / v
    rank = pd.Series(scores).sort_values(ascending=False)

    k = max(2, min(top_k, len(rank)))
    top = rank.iloc[:k]
    positive = top[top.index.map(lambda t: measure.get(t, -np.inf) > 0)]  # raw 13612U screen
    if len(positive) == 0:
        return {safe: 1.0}

    picks = list(positive.index)
    n_picks = len(picks)
    risky_fraction = min(n_picks, top_k) / float(top_k)
    safe_fraction = 1.0 - risky_fraction
    rw = inv_vol_weights(close.loc[:sig_d], picks, lookback)
    out = {t: w * risky_fraction for t, w in rw.items()}
    if safe_fraction > 0:
        out[safe] = out.get(safe, 0.0) + safe_fraction
    return out


# ---------- sleeve definitions (weight functions of (close, sig_d)) ----------
def coreA(close, sd):
    return cpm_weights_param(close, sd, top_k=4, lookback=504, mom="faber_voladj", weighting="invvol")

def coreB(close, sd):
    return cpm_weights_param(close, sd, top_k=5, lookback=504, mom="faber_voladj", weighting="invvol")

def coreC(close, sd):
    return weights_13612u_vol(close, sd, top_k=4, lookback=504)


def blend(close, sd, sleeves):
    """sleeves: list of (fn, frac). Returns aggregated weight dict."""
    out = {}
    for fn, frac in sleeves:
        w = fn(close, sd)
        for t, v in w.items():
            out[t] = out.get(t, 0.0) + frac * v
    # normalize tiny float drift
    z = sum(out.values())
    if abs(z - 1.0) > 1e-9 and z > 0:
        out = {t: v / z for t, v in out.items()}
    return out


SLEEVE_SETS = {
    "single": [(coreA, 1.0)],
    "full":   [(coreA, 0.50), (coreB, 0.25), (coreC, 0.25)],
    "kblend": [(coreA, 0.67), (coreB, 0.33)],
}


# ---------- metrics ----------
def metr(s, cash, lo, hi):
    sub = s.loc[(s.index >= lo) & (s.index <= hi)]
    m = perf_metrics(sub, cash)
    return {"sharpe": m.get("sharpe"), "calmar": m.get("calmar"),
            "maxdd": m.get("max_drawdown"), "cagr": m.get("cagr"),
            "vol": m.get("vol"), "martin": m.get("martin"), "ulcer": m.get("ulcer")}


def turnover_oneway(close, weight_fn, lo, hi):
    """One-way annualized turnover = 0.5 * mean_per_rebalance(sum|dw|) * 12.
    Computed on monthly EOM signal dates over [lo, hi]."""
    monthly_idx = (pd.DataFrame({"x": 1}, index=close.index)
                   .groupby(pd.Grouper(freq="ME")).tail(1))
    sigs = monthly_idx.index[(monthly_idx.index >= lo) & (monthly_idx.index <= hi)].tolist()
    prev, tos = {}, []
    for sd in sigs:
        w = weight_fn(close, sd)
        keys = set(w) | set(prev)
        tos.append(sum(abs(w.get(k, 0.0) - prev.get(k, 0.0)) for k in keys))
        prev = w
    if len(tos) <= 1:
        return float("nan")
    # drop first (initialization from empty -> sum=1, not a real rebalance)
    two_way = float(np.mean(tos[1:]) * 12.0)
    return 0.5 * two_way


# ---------- cc returns for EOM-offset stability (matches memo cliff battery) ----------
def cc_returns_wf(close, daily_ret, weight_fn, start, end, offset, cost_bps=COST):
    """Close-to-close (exec_lag=0) CPM returns for an arbitrary weight_fn at a
    signal-date offset `offset` business days from month-end (0=EOM)."""
    sigs = [s for s in gen_sig_dates(close, start, end, ("eom", offset))
            if start - pd.DateOffset(days=45) <= s <= end]

    def apply_from(sd):
        fut = close.index[close.index > sd]
        return fut[0] if len(fut) > 0 else None

    hist, prev_w = [], {}
    for i, sd in enumerate(sigs):
        w = weight_fn(close, sd)
        af = apply_from(sd)
        if af is None:
            continue
        if i + 1 < len(sigs):
            naf = apply_from(sigs[i + 1])
            end_apply = naf if naf is not None else end
        else:
            end_apply = end
        hist.append({"af": af, "end": end_apply, "w": w})
        prev_w = w

    cols = sorted({a for h in hist for a in h["w"]} & set(daily_ret.columns))
    df_w = pd.DataFrame(0.0, index=close.index, columns=cols)
    for h in hist:
        mask = (close.index >= h["af"]) & (close.index < h["end"])
        for a, ww in h["w"].items():
            if a in df_w.columns:
                df_w.loc[mask, a] = ww
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
    return ret.loc[sel]


def sharpe_of(daily):
    if daily.empty:
        return None
    vol = daily.std(ddof=0) * np.sqrt(252)
    return float((daily.mean() * 252) / vol) if vol > 0 else None


def signal_offset_stability(close, daily_ret, weight_fn):
    """Sharpe across SIGNAL-date offsets EOM..EOM+3 (cc). This is the harsher
    'month-end alignment' cliff (memo: 1.2063->1.01->0.97->0.91)."""
    sharpes = []
    for o in [0, 1, 2, 3]:
        r = cc_returns_wf(close, daily_ret, weight_fn, CS, END, o)
        sharpes.append(sharpe_of(r))
    arr = np.array(sharpes, float)
    return {"grid_eom_to_eom3": [float(x) for x in arr],
            "mean": float(arr.mean()), "std": float(arr.std(ddof=0)),
            "range": float(arr.max() - arr.min()),
            "peak": float(arr.max()), "min": float(arr.min())}


def exec_offset_returns_wf(close, daily_ret, weight_fn, offset, cost_bps=COST):
    """cc returns: SIGNAL fixed at month-end (EOM), EXECUTION shifted to EOM+offset.
    Matches the memo tranching battery's single-day scheme (anchor std 0.0560)."""
    idx = close.index
    pos = {d: i for i, d in enumerate(idx)}
    eom_dates = [s for s in gen_sig_dates(close, CS, END, ("eom", 0))
                 if CS - pd.DateOffset(days=75) <= s <= END]
    targets = [(sd, weight_fn(close, sd)) for sd in eom_dates]
    events = []  # (exec_day, weights)
    for sd, w in targets:
        p = pos[sd] + offset
        if 0 <= p < len(idx):
            events.append((idx[p], w))
    events.sort(key=lambda x: x[0])
    cols = sorted({a for _, w in events for a in w} & set(daily_ret.columns))
    df_w = pd.DataFrame(0.0, index=idx, columns=cols)
    for i, (d, w) in enumerate(events):
        nd = events[i + 1][0] if i + 1 < len(events) else END + pd.Timedelta(days=1)
        mask = (idx >= d) & (idx < nd)
        for a, ww in w.items():
            if a in df_w.columns:
                df_w.loc[mask, a] = ww
    ret = (df_w[cols] * daily_ret[cols]).sum(axis=1, min_count=1).fillna(0.0)
    prev = {}
    for (d, w) in events:
        keys = set(w) | set(prev)
        turnover = sum(abs(w.get(k, 0.0) - prev.get(k, 0.0)) for k in keys)
        cost = turnover * cost_bps / 10000.0
        if d in ret.index:
            ret.loc[d] -= cost
        prev = w
    sel = (ret.index >= CS) & (ret.index <= END)
    return ret.loc[sel]


def exec_offset_stability(close, daily_ret, weight_fn):
    """Sharpe across EXECUTION offsets EOM..EOM+3 (signal fixed at EOM), and std.
    This is the memo's 'execution offset' fragility metric (single anchor 0.0560)."""
    sharpes = []
    for o in [0, 1, 2, 3]:
        r = exec_offset_returns_wf(close, daily_ret, weight_fn, o)
        sharpes.append(sharpe_of(r))
    arr = np.array(sharpes, float)
    return {"grid_eom_to_eom3": [float(x) for x in arr],
            "mean": float(arr.mean()), "std": float(arr.std(ddof=0)),
            "range": float(arr.max() - arr.min()),
            "peak": float(arr.max()), "min": float(arr.min())}


def main():
    panel = load_panel(start=EXT, end=END)
    open_df, close_yf = load_open_close()
    intraday = (close_yf / open_df - 1.0).reindex(panel.index)
    overnight = (open_df / close_yf.shift(1) - 1.0).reindex(panel.index)
    cash = panel["SHV"].ffill().pct_change()

    cols = sorted(set(RISKY_UNIVERSE + SAFE_POOL + CANARY_ASSETS + [DEFAULT_CASH]) & set(panel.columns))
    close = panel[cols]
    daily_ret = close.ffill().pct_change()

    def run_mooex(weight_fn):
        wf = lambda sd: weight_fn(close, sd)
        s, fb = _segment_returns_conv(close, daily_ret, wf, EXT, END, "mooex",
                                      COST, intraday, overnight)
        return s, fb

    out = {"convention_headline": "mooex (T+1 MOO exact)",
           "convention_offset": "cc (exec_lag=0), matches memo cliff battery",
           "cost_bps_side": COST,
           "clean_window": [str(CS.date()), str(END.date())],
           "ext_window": [str(EXT.date()), str(END.date())],
           "anchor": ANCHOR, "configs": {}}

    # ---- anchor gate (single CoreA) ----
    s_single, _ = run_mooex(lambda c, sd: blend(c, sd, SLEEVE_SETS["single"]))
    a = metr(s_single, cash, CS, END)
    gate_ok = bool(abs(a["sharpe"] - ANCHOR["sharpe"]) <= ANCHOR_TOL["sharpe"]
                   and abs(a["maxdd"] - ANCHOR["maxdd"]) <= ANCHOR_TOL["maxdd"]
                   and abs(a["calmar"] - ANCHOR["calmar"]) <= ANCHOR_TOL["calmar"])
    print("ANCHOR GATE single CoreA: S=%.4f DD=%.4f C=%.4f  expect %.4f/%.4f/%.4f => %s"
          % (a["sharpe"], a["maxdd"], a["calmar"], ANCHOR["sharpe"], ANCHOR["maxdd"],
             ANCHOR["calmar"], "PASS" if gate_ok else "FAIL"))
    out["anchor_gate_pass"] = gate_ok
    if not gate_ok:
        raise SystemExit("ANCHOR GATE FAILED -- aborting (numbers do not reproduce).")

    # ---- per-config metrics ----
    for name, sleeves in SLEEVE_SETS.items():
        wfn = (lambda sl: (lambda c, sd: blend(c, sd, sl)))(sleeves)
        s, fb = run_mooex(wfn)
        clean = metr(s, cash, CS, END)
        ext = metr(s, cash, EXT, END)
        tov = turnover_oneway(close, wfn, CS, END)
        tov_ext = turnover_oneway(close, wfn, EXT, END)
        exec_stab = exec_offset_stability(close, daily_ret, wfn)
        sig_stab = signal_offset_stability(close, daily_ret, wfn)
        out["configs"][name] = {
            "sleeves": [(fn.__name__ if hasattr(fn, "__name__") else str(fn), fr) for fn, fr in sleeves],
            "clean": clean, "ext": ext,
            "turnover_oneway_clean": tov, "turnover_oneway_ext": tov_ext,
            "exec_offset_stability_cc": exec_stab,
            "signal_offset_stability_cc": sig_stab,
            "mooex_fallback": fb,
        }
        print("\n[%s]" % name)
        print("  clean  S=%.4f C=%.4f DD=%.4f Martin=%.3f vol=%.4f"
              % (clean["sharpe"], clean["calmar"], clean["maxdd"], clean["martin"], clean["vol"]))
        print("  ext    S=%.4f C=%.4f DD=%.4f Martin=%.3f"
              % (ext["sharpe"], ext["calmar"], ext["maxdd"], ext["martin"]))
        print("  turnover one-way/yr clean=%.3f ext=%.3f" % (tov, tov_ext))
        print("  EXEC-offset cc Sharpe grid=%s std=%.4f (memo single anchor 0.0560)"
              % (["%.4f" % x for x in exec_stab["grid_eom_to_eom3"]], exec_stab["std"]))
        print("  SIGNAL-offset cc Sharpe grid=%s std=%.4f"
              % (["%.4f" % x for x in sig_stab["grid_eom_to_eom3"]], sig_stab["std"]))

    # ---- K/ranker independence: standalone sleeve dispersion ----
    standalone = {}
    for nm, fn in [("CoreA_faber_K4", coreA), ("CoreB_faber_K5", coreB), ("CoreC_13612Uvol_K4", coreC)]:
        s, _ = run_mooex(fn)
        m = metr(s, cash, CS, END)
        me = metr(s, cash, EXT, END)
        standalone[nm] = {"clean": m, "ext": me}
        print("  standalone %-20s clean S=%.4f DD=%.4f | ext S=%.4f DD=%.4f"
              % (nm, m["sharpe"], m["maxdd"], me["sharpe"], me["maxdd"]))
    sl_sharpes = [standalone[k]["clean"]["sharpe"] for k in standalone]
    out["standalone_sleeves"] = standalone
    out["sleeve_sharpe_dispersion_clean"] = {
        "sleeves": sl_sharpes, "std": float(np.std(sl_sharpes, ddof=0)),
        "range": float(max(sl_sharpes) - min(sl_sharpes)),
        "note": "dispersion of standalone sleeve Sharpes = the K/ranker selection risk an investor faces choosing a single config; ensemble removes this choice",
    }

    out_json = HERE / "cpm_ensemble_findings.json"
    out_json.write_text(json.dumps(out, indent=2, default=lambda o: float(o) if isinstance(o, (np.floating, np.integer)) else (bool(o) if isinstance(o, np.bool_) else o)))
    print("\nWROTE", out_json)
    return out


if __name__ == "__main__":
    main()
