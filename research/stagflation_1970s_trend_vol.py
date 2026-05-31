#!/usr/bin/env python3
"""
Stagflation 1970s: do the TREND filter and VOL gate protect EQUITY where the
TIP canary did NOT?

CONTEXT
-------
The companion test (stagflation_1970s_tip_canary.py) showed the synthetic-TIP
13612U canary does NOT protect a S&P 500 equity sleeve through the real 1973-74
and 1977-82 stagflation drawdowns: tip_only de-risked 0 useful months and its
1973-74 MaxDD == buy & hold (-39.16%). This script tests the strategies' OTHER
defenses on the SAME equity sleeve, SAME harness/data:

  1. TREND  : risk-on iff S&P-500's OWN 13612U absolute (time-series) momentum
              > 0. This is CPM's positive-trend screen and BULL's SPY trend gate.
  2. VOL    : risk-on iff realized-vol(60d) < realized-vol(252d) on S&P 500
              daily returns. Vol-expansion -> de-risk.
  3. TREND_AND_VOL : risk-on iff BOTH pass.
  4. References: buyhold (always on); tip_only (the known failure) for contrast.

All variants: monthly rebalance, signal at end of month t applied to month t+1
(1-month implementation lag, no lookahead), defensive leg = 3-month T-bill.

DATA (reuses stagflation_1970s_tip_canary loaders + adds daily index)
---------------------------------------------------------------------
* S&P 500 monthly TOTAL return: Shiller ie_data (datahub mirror), reconstructed
  TR_t = (P_t - P_{t-1} + D_t/12)/P_{t-1}. (monthly-average price; NOT daily
  close.) Used for: the equity sleeve return AND the TREND 13612U signal.
* S&P 500 DAILY close: Yahoo Finance ^GSPC daily (cached gspc_daily.csv),
  1967-01-03 .. 1985-12-31, 4770 obs. PRICE-ONLY (no dividends; irrelevant for
  realized vol). Used ONLY for the VOL gate (rv_60d / rv_252d).
* Cash / defensive: FRED TB3MS (3m T-bill), monthly = rate/1200.

VOL GATE construction
---------------------
  daily log returns r_d = ln(C_d / C_{d-1}).
  At each month-end (last trading day m of month t):
     rv_60d  = std(last 60 daily r_d)  * sqrt(252)
     rv_252d = std(last 252 daily r_d) * sqrt(252)
     vol_on(t) = rv_60d < rv_252d
  Signal computed at month-end t, applied to month t+1 (same 1-month lag).
  (annualization factor cancels in the ratio; kept for readability.)

OUTPUT
------
  research/stagflation_1970s_trend_vol_findings.json
  research/stagflation_1970s_trend_vol_findings.md (written by companion writer)
"""
from __future__ import annotations
import json
from pathlib import Path

import numpy as np
import pandas as pd

# reuse the existing harness verbatim
from stagflation_1970s_tip_canary import (
    DATA, EVAL_START, EVAL_END, STAG_WINDOWS,
    load_inputs, bond_total_return, sp500_total_return, cum_index,
    sig_13612U_at, metrics,
)

HERE = Path(__file__).resolve().parent


# ---------------------------------------------------------------------------
# Daily S&P 500 loader + vol-gate signal
# ---------------------------------------------------------------------------
def load_daily_sp() -> pd.Series:
    df = pd.read_csv(DATA / "gspc_daily.csv")
    df["date"] = pd.to_datetime(df["date"])
    s = df.set_index("date")["close"].astype(float).sort_index()
    return s


def vol_gate_monthly(daily_close: pd.Series, win_fast=60, win_slow=252) -> pd.DataFrame:
    """Month-end realized-vol gate. Returns DataFrame indexed by month Period
    with columns rv_fast, rv_slow, vol_on (computed AS OF month-end t)."""
    r = np.log(daily_close / daily_close.shift(1)).dropna()
    # last trading day of each month
    grp = r.groupby(r.index.to_period("M"))
    rows = []
    rvals = r.values
    ridx = r.index
    # cumulative position lookup: for each month-end, take trailing windows
    for per, sub in grp:
        end_pos = ridx.get_loc(sub.index[-1])
        if isinstance(end_pos, slice):
            end_pos = end_pos.stop - 1
        if end_pos + 1 < win_slow:
            rows.append((per, np.nan, np.nan, np.nan))
            continue
        fast = rvals[end_pos + 1 - win_fast: end_pos + 1]
        slow = rvals[end_pos + 1 - win_slow: end_pos + 1]
        rv_fast = float(fast.std(ddof=0) * np.sqrt(252))
        rv_slow = float(slow.std(ddof=0) * np.sqrt(252))
        rows.append((per, rv_fast, rv_slow, rv_fast < rv_slow))
    df = pd.DataFrame(rows, columns=["month", "rv_fast", "rv_slow", "vol_on"]).set_index("month")
    return df


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    d = load_inputs()
    cpi_infl = d["cpi"].pct_change()

    # synthetic TIP (for the known-failure reference) -- same as companion
    tr_gs5 = bond_total_return(d["gs5"], N=5)
    idx = tr_gs5.index.intersection(cpi_infl.index)
    tr_tip = (tr_gs5.reindex(idx) + cpi_infl.reindex(idx)).dropna()
    px_tip = cum_index(tr_tip)

    # equity sleeve
    tr_sp = sp500_total_return(d["sp_p"], d["sp_d"])
    px_sp = cum_index(tr_sp)          # monthly TR index -> TREND 13612U signal
    rf = d["tb3"] / 12.0

    # daily vol gate
    daily = load_daily_sp()
    vg = vol_gate_monthly(daily)

    # ---- per-month signals (as of end of month t) ----
    all_months = pd.period_range(EVAL_START - 1, EVAL_END, freq="M")
    sig_rows = []
    for t in all_months:
        sig_rows.append({
            "month": t,
            "trend": sig_13612U_at(px_sp, t),     # S&P own 13612U
            "tip": sig_13612U_at(px_tip, t),
            "vol_on": (bool(vg.loc[t, "vol_on"]) if (t in vg.index and pd.notna(vg.loc[t, "vol_on"])) else np.nan),
            "rv_fast": (float(vg.loc[t, "rv_fast"]) if (t in vg.index and pd.notna(vg.loc[t, "rv_fast"])) else np.nan),
            "rv_slow": (float(vg.loc[t, "rv_slow"]) if (t in vg.index and pd.notna(vg.loc[t, "rv_slow"])) else np.nan),
        })
    sig = pd.DataFrame(sig_rows).set_index("month")

    # ---- backtest: signal at end(t-1) applies to month t ----
    eval_months = pd.period_range(EVAL_START, EVAL_END, freq="M")
    variants = ["trend", "vol", "trend_and_vol", "tip_only", "buyhold"]
    strat_ret = {v: {} for v in variants}
    risk_on = {v: {} for v in variants}
    for t in eval_months:
        prev = t - 1
        s_trend = sig.loc[prev, "trend"] if prev in sig.index else np.nan
        s_tip = sig.loc[prev, "tip"] if prev in sig.index else np.nan
        s_vol = sig.loc[prev, "vol_on"] if prev in sig.index else np.nan
        sp = tr_sp.get(t, np.nan)
        cash = rf.get(t, np.nan)
        if pd.isna(sp):
            continue
        # warmup-safe defaults: NaN signal -> risk-on
        trend_on = (s_trend > 0) if pd.notna(s_trend) else True
        vol_on = bool(s_vol) if pd.notna(s_vol) else True
        tip_on = (s_tip > 0) if pd.notna(s_tip) else True
        decide = {
            "trend": trend_on,
            "vol": vol_on,
            "trend_and_vol": trend_on and vol_on,
            "tip_only": tip_on,
            "buyhold": True,
        }
        for v in variants:
            on = bool(decide[v])
            risk_on[v][t] = on
            strat_ret[v][t] = sp if on else cash

    strat_ret = {v: pd.Series(s).sort_index() for v, s in strat_ret.items()}
    risk_on = {v: pd.Series(s).sort_index() for v, s in risk_on.items()}

    # ---- metrics ----
    out = {}
    out["meta"] = {
        "eval_window": [str(EVAL_START), str(EVAL_END)],
        "stag_windows": {k: [str(a), str(b)] for k, (a, b) in STAG_WINDOWS.items()},
        "variants": {
            "trend": "risk-on iff S&P-500 own 13612U momentum > 0 (absolute/time-series; CPM trend screen, BULL SPY gate)",
            "vol": "risk-on iff rv_60d(S&P daily) < rv_252d(S&P daily)",
            "trend_and_vol": "risk-on iff trend AND vol both pass",
            "tip_only": "risk-on iff synthetic-TIP 13612U > 0 (known failure, contrast)",
            "buyhold": "always risk-on (S&P 500 buy & hold)",
        },
        "data_sources": {
            "sp500_monthly_tr": "Shiller ie_data (datahub mirror); (P_t-P_{t-1}+D_t/12)/P_{t-1}; monthly-average price",
            "sp500_daily": "Yahoo Finance ^GSPC daily close 1967-01..1985-12 (4770 obs); price-only; vol gate only",
            "cash": "FRED TB3MS (3m T-bill)",
            "synthetic_tip": "FRED GS5 TR + realized CPIAUCSL inflation (companion harness)",
        },
        "constructions": {
            "trend_signal": "13612U = mean(1,3,6,12m TR of S&P monthly TR index); end-of-month t -> applied month t+1",
            "vol_signal": "rv = std(daily log ret over window)*sqrt(252); vol_on = rv_60d < rv_252d at month-end t -> applied month t+1",
        },
        "caveats": [
            "TREND signal uses Shiller MONTHLY-AVERAGE S&P price (TR-reconstructed); monthly averaging smooths/lags turning points vs month-end close, may delay trend flips.",
            "VOL gate uses Yahoo ^GSPC DAILY close (price-only, no dividends; irrelevant for vol). Daily index is true daily close, NOT monthly-average -- so vol and trend signals use DIFFERENT price series (documented mismatch).",
            "Equity sleeve return = Shiller monthly TR (consistent with companion harness).",
            "Defensive asset = 3m T-bill; intermediate Treasuries as defensive would change defensive-leg returns (not tested).",
            "Warmup months with insufficient history default to risk-on (no lookahead).",
            "rv windows: 60d ~ 3 calendar months, 252d ~ 12 months; first valid vol signal early 1968.",
        ],
    }

    out["full_period"] = {v: metrics(strat_ret[v], rf) for v in variants}

    # stagflation windows + dd avoided vs buyhold
    out["stagflation_windows"] = {}
    for wname, (a, b) in STAG_WINDOWS.items():
        rec = {}
        for v in variants:
            m = metrics(strat_ret[v].loc[a:b], rf)
            rec[v] = {
                "cagr_pct": m.get("cagr_pct"),
                "total_return_pct": m.get("total_return_pct"),
                "maxdd_pct": m.get("maxdd_pct"),
                "sharpe": m.get("sharpe"),
            }
        bh_dd = rec["buyhold"]["maxdd_pct"]
        for v in variants:
            rec[v]["dd_avoided_vs_buyhold_pp"] = round(rec[v]["maxdd_pct"] - bh_dd, 2)
        out["stagflation_windows"][wname] = rec

    # ---- defensive-month analysis (whipsaw / false positives) ----
    out["defensive_analysis"] = {}
    sp_next = tr_sp.reindex(eval_months)
    for v in variants:
        if v == "buyhold":
            continue
        ro = risk_on[v].reindex(eval_months)
        defensive = ~ro.fillna(True)
        n_def = int(defensive.sum())
        fp = int(((defensive) & (sp_next > 0)).sum())   # whipsaw: defensive but equity rose
        tp = int(((defensive) & (sp_next < 0)).sum())
        down = sp_next < 0
        caught = int(((defensive) & down).sum())
        n_down = int(down.sum())
        out["defensive_analysis"][v] = {
            "n_defensive_months": n_def,
            "false_positive_def_months": fp,
            "true_positive_def_months": tp,
            "false_positive_rate_pct": round(100 * fp / n_def, 1) if n_def else None,
            "equity_down_months_total": n_down,
            "equity_down_months_caught": caught,
            "down_month_capture_pct": round(100 * caught / n_down, 1) if n_down else None,
            "defensive_months": [str(m) for m in eval_months[defensive.values]],
        }

    # ---- timing: signal calendar across stagflation windows ----
    out["signal_calendar"] = {}
    for wname, (a, b) in STAG_WINDOWS.items():
        rows = []
        for t in pd.period_range(a - 1, b - 1, freq="M"):
            if t not in sig.index:
                continue
            applied = t + 1
            st, sv, sti = sig.loc[t, "trend"], sig.loc[t, "vol_on"], sig.loc[t, "tip"]
            rows.append({
                "signal_month": str(t), "applied_month": str(applied),
                "trend_sig": round(float(st), 4) if pd.notna(st) else None,
                "trend_on": bool(st > 0) if pd.notna(st) else None,
                "vol_on": bool(sv) if pd.notna(sv) else None,
                "rv_fast": round(float(sig.loc[t, "rv_fast"]), 4) if pd.notna(sig.loc[t, "rv_fast"]) else None,
                "rv_slow": round(float(sig.loc[t, "rv_slow"]), 4) if pd.notna(sig.loc[t, "rv_slow"]) else None,
                "tip_on": bool(sti > 0) if pd.notna(sti) else None,
                "sp_ret_pct": round(float(tr_sp.get(applied, np.nan)) * 100, 2) if pd.notna(tr_sp.get(applied, np.nan)) else None,
            })
        out["signal_calendar"][wname] = rows

    # ---- timing summary: first defensive month within each window vs peak ----
    out["timing_summary"] = {}
    for wname, (a, b) in STAG_WINDOWS.items():
        # equity peak (cum) within window
        sub_sp = tr_sp.loc[a:b]
        eq = (1 + sub_sp).cumprod()
        peak_month = str(eq.idxmax()) if len(eq) else None
        trough_month = str((eq / eq.cummax()).idxmin()) if len(eq) else None
        rec = {"window": [str(a), str(b)], "equity_peak_month": peak_month,
               "equity_trough_month": trough_month}
        for v in ["trend", "vol", "trend_and_vol", "tip_only"]:
            ro = risk_on[v].loc[a:b]
            defm = ro[~ro.astype(bool)]
            rec[v + "_first_defensive_month"] = str(defm.index[0]) if len(defm) else None
            rec[v + "_n_defensive_in_window"] = int((~ro.astype(bool)).sum())
        out["timing_summary"][wname] = rec

    def _ser(o):
        if isinstance(o, (np.bool_,)):
            return bool(o)
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, (np.floating,)):
            return float(o)
        raise TypeError(str(type(o)))

    OUT = HERE / "stagflation_1970s_trend_vol_findings.json"
    OUT.write_text(json.dumps(out, indent=2, default=_ser))
    print(f"Wrote {OUT}")

    # console summary
    print("\n== FULL PERIOD (1968-1985) ==")
    for v in variants:
        m = out["full_period"][v]
        print(f"  {v:14s} CAGR {m['cagr_pct']:>6}%  MaxDD {m['maxdd_pct']:>7}%  Sharpe {m['sharpe']:>6}  vol {m['vol_pct']}%")
    for wname, (a, b) in STAG_WINDOWS.items():
        print(f"\n== {wname} ({a}..{b}) ==")
        for v in variants:
            r = out["stagflation_windows"][wname][v]
            print(f"  {v:14s} ret {r['total_return_pct']:>7}%  MaxDD {r['maxdd_pct']:>7}%  ddAvoid {r['dd_avoided_vs_buyhold_pp']:>6}pp  Sharpe {r['sharpe']}")
    print("\n== DEFENSIVE (whipsaw) ==")
    for v in ["trend", "vol", "trend_and_vol", "tip_only"]:
        da = out["defensive_analysis"][v]
        print(f"  {v:14s} def={da['n_defensive_months']:>3}  FP(whipsaw)={da['false_positive_def_months']:>3} ({da['false_positive_rate_pct']}%)  downCapture={da['down_month_capture_pct']}%")
    print("\n== TIMING ==")
    for wname in STAG_WINDOWS:
        ts = out["timing_summary"][wname]
        print(f"  {wname}: peak={ts['equity_peak_month']} trough={ts['equity_trough_month']}")
        for v in ["trend", "vol", "trend_and_vol", "tip_only"]:
            print(f"      {v:14s} 1st def={ts[v+'_first_defensive_month']}  n_def={ts[v+'_n_defensive_in_window']}")
    return out


if __name__ == "__main__":
    main()
