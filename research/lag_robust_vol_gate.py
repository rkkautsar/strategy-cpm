"""Throwaway research: lag-robust BULL vol-gate formulations.

Question
--------
The production BULL sleeve's fast RV_20d-vs-RV_252d crossover gate
(bull_spy_live._vol_gate_ok) carries the same-day-close lookahead: under an
honest 1-trading-day execution lag (exec_lag=1) its clean BULL Sharpe edge
collapses (audit: BULL lag delta -0.173; gate-off lag delta +0.001).

Hypothesis: a SLOWER / lower-cadence vol regime estimator recovers most of the
vol-gate's risk-adjusted benefit while surviving a 1-day exec lag, because a slow
signal does not react to the bar it executes on.

Method
------
Reuse the audit harness UNCHANGED (lookahead_audit_2026_05_30.py) for timing,
CPM sleeve, blend, and metrics. We ONLY swap bull_spy_live._vol_gate_ok via
monkeypatch (binary variants) or wrap the BULL weight fn (continuous S5).

All variants measured under HONEST exec_lag=1 unless the row says same-day.
Blend = 0.60*CPM + 0.40*BULL (both sleeves at the SAME exec_lag).
No threshold scanning: every window/span/target is convention-locked.

Variants
--------
REF-OFF        : vol gate disabled (always True), exec_lag=1   = honest floor
REF-ON-sameday : original RV_20d/252 gate,        exec_lag=0   = inflated ceiling
REF-ON-lag     : original RV_20d/252 gate,        exec_lag=1   = current honest
S1-60          : RV_60d  < RV_252d crossover,     exec_lag=1
S1-120         : RV_120d < RV_252d crossover,     exec_lag=1
S2-EMA         : EMA-vol span20 < EMA-vol span252, exec_lag=1
S3-MONTHLY     : monthly-return vol 12m < 36m,    exec_lag=1   (monthly cadence)
S4-LAGINPUT    : original RV_20d/252 but on close[:T-1], exec_lag=1 (diagnostic)
S5-VOLTGT      : continuous SPY size = min(1, 15%/RV_20d lagged), exec_lag=1 (xcheck)
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import bull_spy_live
from bull_spy_live import BULL_TICKER, CASH_TICKER, compute_bull_spy_weights
import lookahead_audit_2026_05_30 as audit
from cpm_live import perf_metrics

CPM_W, BULL_W = audit.CPM_W, audit.BULL_W

# Save the production gate so we can restore it.
_ORIG_VOL_GATE = bull_spy_live._vol_gate_ok


# --------------------------------------------------------------------------
# Binary vol-gate variants (signature matches _vol_gate_ok: (daily_spy, sig_d))
# Each returns (vol_ok: bool, diag: dict). daily_spy is a SPY close series.
# --------------------------------------------------------------------------

def gate_off(daily_spy, sig_d):
    return True, {"variant": "off"}


def _rv_cross(daily_spy, sig_d, fast, slow=252):
    sub = daily_spy.loc[:sig_d].pct_change().dropna()
    if len(sub) < slow:
        return True, {"warmup": True}
    vf = float(sub.tail(fast).std() * np.sqrt(252))
    vs = float(sub.tail(slow).std() * np.sqrt(252))
    return (vf < vs), {"vf": vf, "vs": vs}


def gate_rv60(daily_spy, sig_d):
    return _rv_cross(daily_spy, sig_d, 60, 252)


def gate_rv120(daily_spy, sig_d):
    return _rv_cross(daily_spy, sig_d, 120, 252)


def gate_ema(daily_spy, sig_d):
    ret = daily_spy.loc[:sig_d].pct_change().dropna()
    if len(ret) < 252:
        return True, {"warmup": True}
    vf = float(ret.ewm(span=20, min_periods=20).std().iloc[-1] * np.sqrt(252))
    vs = float(ret.ewm(span=252, min_periods=252).std().iloc[-1] * np.sqrt(252))
    if not (np.isfinite(vf) and np.isfinite(vs)):
        return True, {"warmup": True}
    return (vf < vs), {"vf": vf, "vs": vs}


def gate_monthly(daily_spy, sig_d):
    # Monthly cadence: realized vol from MONTHLY returns, 12m vs 36m.
    monthly = daily_spy.loc[:sig_d].resample("ME").last()
    mret = monthly.pct_change().dropna()
    if len(mret) < 36:
        return True, {"warmup": True}
    v12 = float(mret.tail(12).std() * np.sqrt(12))
    v36 = float(mret.tail(36).std() * np.sqrt(12))
    return (v12 < v36), {"v12": v12, "v36": v36}


def gate_laginput_rv20(daily_spy, sig_d):
    # Diagnostic: same fast 20/252 crossover, but on close up to T-1.
    idx = daily_spy.index[daily_spy.index <= sig_d]
    if len(idx) < 2:
        return True, {"warmup": True}
    lagged = daily_spy.loc[:idx[-2]]
    return _rv_cross(lagged, idx[-2], 20, 252)


BINARY_VARIANTS = {
    "REF-OFF":     gate_off,
    "S1-60":       gate_rv60,
    "S1-120":      gate_rv120,
    "S2-EMA":      gate_ema,
    "S3-MONTHLY":  gate_monthly,
    "S4-LAGINPUT": gate_laginput_rv20,
}


# --------------------------------------------------------------------------
# S5 continuous vol-target: wraps the production weight fn. Uses LAGGED RV_20d
# (close[:sig_d]) which is honest under exec_lag=1. Scales SPY only when the
# binary gate would be ON (canary AND trend AND original vol_ok); remainder -> safe.
# Target vol 15% annualized is a FITTED parameter -> flagged overfit-risk.
# --------------------------------------------------------------------------
TARGET_VOL = 0.15

def bull_weight_fn_voltgt(panel, sig_d):
    w, regime, diag = compute_bull_spy_weights(panel, sig_d, panel[BULL_TICKER])
    if BULL_TICKER not in w:  # gate off -> already in safe
        return w
    sub = panel[BULL_TICKER].loc[:sig_d].pct_change().dropna()
    if len(sub) < 252:
        return w
    rv = float(sub.tail(20).std() * np.sqrt(252))
    if rv <= 0:
        return w
    scale = min(1.0, TARGET_VOL / rv)
    safe = diag.get("picked_safe", CASH_TICKER)
    out = {BULL_TICKER: scale}
    rem = 1.0 - scale
    if rem > 1e-9:
        out[safe] = out.get(safe, 0.0) + rem
    return out


# --------------------------------------------------------------------------
# Runners
# --------------------------------------------------------------------------

def run_bull(panel, start, end, exec_lag, gate=None, weight_fn=None):
    """Returns BULL daily series. If gate given, monkeypatch _vol_gate_ok.
    If weight_fn given (S5), use audit._segment_returns directly."""
    if weight_fn is not None:
        cols = sorted(set([BULL_TICKER, CASH_TICKER] + list(bull_spy_live.SAFE_POOL)
                          + ["HYG", "TIP"]) & set(panel.columns))
        close = panel[cols]
        daily_ret = panel.ffill().pct_change()
        wf = lambda sd: weight_fn(panel, sd)
        r = audit._segment_returns(close, daily_ret, wf, start, end, exec_lag,
                                   bull_spy_live.COST_BPS_PER_SIDE)
        return r.loc[(r.index >= start) & (r.index <= end)]
    bull_spy_live._vol_gate_ok = gate if gate is not None else _ORIG_VOL_GATE
    try:
        return audit.bull_sleeve(panel, start, end, exec_lag)
    finally:
        bull_spy_live._vol_gate_ok = _ORIG_VOL_GATE


def metrics(daily, cash_daily, label):
    m = perf_metrics(daily, cash_daily)
    return {"name": label, "sharpe": m.get("sharpe"), "cagr": m.get("cagr"),
            "maxdd": m.get("max_drawdown"), "calmar": m.get("calmar"),
            "vol": m.get("vol")}


def main():
    end = pd.Timestamp("2026-05-30")
    ext_start = pd.Timestamp("1999-03-10")
    clean_start = pd.Timestamp("2008-05-30")

    panel = audit.load_panel(start=ext_start, end=end)
    end = min(end, panel.index[-1])
    cash_daily = panel["SHV"].ffill().pct_change().dropna()
    print(f"Panel {panel.index[0].date()} -> {panel.index[-1].date()} ({len(panel)} rows)\n")

    # CPM sleeve once per lag (independent of vol gate).
    cpm = {lag: audit.cpm_sleeve(panel, ext_start, end, lag) for lag in (0, 1)}

    # Build BULL series for each scenario.
    bull_series = {}
    # references
    bull_series["REF-ON-sameday"] = (run_bull(panel, ext_start, end, 0,
                                              gate=_ORIG_VOL_GATE), 0)
    bull_series["REF-ON-lag"] = (run_bull(panel, ext_start, end, 1,
                                          gate=_ORIG_VOL_GATE), 1)
    for name, gate in BINARY_VARIANTS.items():
        bull_series[name] = (run_bull(panel, ext_start, end, 1, gate=gate), 1)
    bull_series["S5-VOLTGT"] = (run_bull(panel, ext_start, end, 1,
                                         weight_fn=bull_weight_fn_voltgt), 1)

    # Order for reporting.
    order = ["REF-OFF", "REF-ON-sameday", "REF-ON-lag",
             "S1-60", "S1-120", "S2-EMA", "S3-MONTHLY", "S4-LAGINPUT", "S5-VOLTGT"]

    # blends per scenario, aligned to matching-lag CPM.
    blends = {}
    bulls = {}
    for name in order:
        b, lag = bull_series[name]
        c = cpm[lag]
        common = c.index.intersection(b.index)
        c2, b2 = c.reindex(common), b.reindex(common)
        bulls[name] = b2
        blends[name] = CPM_W * c2 + BULL_W * b2

    windows = {
        "CLEAN 18y": (clean_start, end),
        "EXT 27y":   (ext_start, end),
        "dot-com":   (pd.Timestamp("2000-03-01"), pd.Timestamp("2002-10-31")),
        "GFC":       (pd.Timestamp("2008-05-30"), pd.Timestamp("2009-06-30")),
        "COVID":     (pd.Timestamp("2020-02-01"), pd.Timestamp("2020-04-30")),
        "2022":      (pd.Timestamp("2022-01-01"), pd.Timestamp("2022-12-31")),
    }

    def table(series_map, title):
        print("=" * 92)
        print(title)
        print("=" * 92)
        for wname, (ws, we) in windows.items():
            print(f"\n-- {wname} --")
            hdr = f"{'variant':<16}{'Sharpe':>8}{'CAGR':>9}{'MaxDD':>9}{'Calmar':>8}{'Vol':>8}"
            print(hdr); print("-" * len(hdr))
            for name in order:
                s = series_map[name]
                sl = s.loc[(s.index >= ws) & (s.index <= we)]
                if len(sl) < 5:
                    continue
                m = metrics(sl, cash_daily, name)
                print(f"{name:<16}{m['sharpe']:>8.3f}{m['cagr']*100:>8.2f}%"
                      f"{m['maxdd']*100:>8.2f}%{m['calmar']:>8.3f}{m['vol']*100:>7.2f}%")

    table(blends, "BLEND 60/40 (PRIMARY)")
    print()
    table(bulls, "BULL solo (SECONDARY)")

    # Ranked verdict table: full-window blend & bull Sharpe + clean MaxDD.
    print("\n" + "=" * 92)
    print("RANK SUMMARY: clean 18y, honest lag (refs noted)")
    print("=" * 92)
    cs, ce = clean_start, end
    rows = []
    for name in order:
        b = bulls[name].loc[cs:ce]
        bl = blends[name].loc[cs:ce]
        mb = perf_metrics(b, cash_daily)
        mblend = perf_metrics(bl, cash_daily)
        rows.append((name, mblend["sharpe"], mblend["max_drawdown"],
                     mb["sharpe"], mb["max_drawdown"]))
    floor = next(r for r in rows if r[0] == "REF-OFF")
    print(f"{'variant':<16}{'BLEND Sh':>9}{'BLEND DD':>10}{'BULL Sh':>9}{'BULL DD':>10}"
          f"{'vs FLOOR(bSh)':>14}")
    print("-" * 70)
    for name, blsh, bldd, bsh, bdd in rows:
        d = blsh - floor[1]
        print(f"{name:<16}{blsh:>9.3f}{bldd*100:>9.2f}%{bsh:>9.3f}{bdd*100:>9.2f}%"
              f"{d:>+14.3f}")
    print("\nDONE")


if __name__ == "__main__":
    main()
