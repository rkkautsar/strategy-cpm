#!/usr/bin/env python3
"""
Stagflation 1970s: ACTUAL combined BULL stack (canary AND trend AND vol),
not the legs separately. Benchmark vs HAA-Simple and buy & hold.

THIS IS A 1970s BACKTEST ONLY. No production / memo implication.

QUESTION
--------
The companion scripts ran the legs separately:
  trend-only       1973-74 MaxDD -9.22%
  trend+vol        1973-74 MaxDD -6.85%
This script runs the FULL production BULL stack as ONE strategy, adapted to
1970s data, and compares it head-to-head with HAA-Simple and buy & hold.

BULL STACK (production logic, 1970s adaptation)
-----------------------------------------------
Risk-on iff ALL three pass (AND):
  (a) CANARY : synthetic-TIP 13612U > 0
  (b) TREND  : S&P 500 13612U > 0
  (c) VOL    : rv_60d(S&P daily) < rv_252d(S&P daily)
Risk-on  -> 100% S&P 500 monthly TR.
Else     -> SAFE = best of {cash (3m T-bill), IEF (GS5 par-bond TR)} by 13612U.

We use the TIP-ONLY canary (not HYG-OR-TIP) because HYG / a credit risky
universe does not exist pre-1980. The companion tip_canary test showed
synthetic-TIP 13612U is effectively ALWAYS-ON in this era (it de-risked 0
useful months), so the canary leg is present but expected to be NON-BINDING --
this isolates whether trend+vol do the protective work with the canary inert.

HAA-Simple BENCHMARK
--------------------
Risk-on iff (synthetic-TIP 13612U > 0) AND (S&P 13612U > 0)  [NO vol gate]
  Risk-on -> 100% S&P 500 TR. Else -> best of {IEF, cash} by 13612U.
(= BULL stack minus the vol gate; clean attribution of the vol leg.)

BUY & HOLD: always 100% S&P 500 TR.

HARNESS / DATA: reuses stagflation_1970s_tip_canary + trend_vol verbatim.
  * S&P 500 monthly TR: Shiller ie_data (monthly-average price reconstruction)
  * S&P 500 daily close: Yahoo ^GSPC (vol gate only, price-only)
  * synthetic TIP: FRED GS5 par-bond TR + realized CPIAUCSL inflation
  * IEF analog: FRED GS5 par-bond TR (5y CMT duration reconstruction)
  * cash: FRED TB3MS (3m T-bill)
  monthly rebalance, signal end(t) -> applied month t+1 (1-month lag).

OUTPUT
  research/stagflation_1970s_bull_stack_findings.json
  research/stagflation_1970s_bull_stack_findings.md (companion writer)
"""
from __future__ import annotations
import json
from pathlib import Path

import numpy as np
import pandas as pd

from stagflation_1970s_tip_canary import (
    EVAL_START, EVAL_END, STAG_WINDOWS,
    load_inputs, bond_total_return, sp500_total_return, cum_index,
    sig_13612U_at, metrics,
)
from stagflation_1970s_trend_vol import load_daily_sp, vol_gate_monthly

HERE = Path(__file__).resolve().parent


def main():
    d = load_inputs()
    cpi_infl = d["cpi"].pct_change()

    # legs
    tr_gs5 = bond_total_return(d["gs5"], N=5)          # IEF analog (5y Treasury TR)
    idx = tr_gs5.index.intersection(cpi_infl.index)
    tr_tip = (tr_gs5.reindex(idx) + cpi_infl.reindex(idx)).dropna()
    px_tip = cum_index(tr_tip)

    tr_sp = sp500_total_return(d["sp_p"], d["sp_d"])
    px_sp = cum_index(tr_sp)
    rf = d["tb3"] / 12.0                                # cash monthly return

    # safe-leg price indices for 13612U selection
    px_ief = cum_index(tr_gs5)
    px_cash = cum_index(rf.dropna())

    # vol gate (daily)
    daily = load_daily_sp()
    vg = vol_gate_monthly(daily)

    # ---- per-month signals as of end of month t ----
    all_months = pd.period_range(EVAL_START - 1, EVAL_END, freq="M")
    rows = []
    for t in all_months:
        rows.append({
            "month": t,
            "trend": sig_13612U_at(px_sp, t),
            "tip": sig_13612U_at(px_tip, t),
            "ief": sig_13612U_at(px_ief, t),
            "cash": sig_13612U_at(px_cash, t),
            "vol_on": (bool(vg.loc[t, "vol_on"]) if (t in vg.index and pd.notna(vg.loc[t, "vol_on"])) else np.nan),
            "rv_fast": (float(vg.loc[t, "rv_fast"]) if (t in vg.index and pd.notna(vg.loc[t, "rv_fast"])) else np.nan),
            "rv_slow": (float(vg.loc[t, "rv_slow"]) if (t in vg.index and pd.notna(vg.loc[t, "rv_slow"])) else np.nan),
        })
    sig = pd.DataFrame(rows).set_index("month")

    # ---- backtest ----
    eval_months = pd.period_range(EVAL_START, EVAL_END, freq="M")
    variants = ["bull_stack", "haa_simple", "buyhold"]
    strat_ret = {v: {} for v in variants}
    risk_on = {v: {} for v in variants}
    safe_choice = {v: {} for v in variants}   # which safe asset used in defensive months
    binding_leg = {}                          # which leg(s) failed for bull_stack defensive months

    for t in eval_months:
        prev = t - 1
        if prev not in sig.index:
            continue
        s_trend = sig.loc[prev, "trend"]
        s_tip = sig.loc[prev, "tip"]
        s_vol = sig.loc[prev, "vol_on"]
        s_ief = sig.loc[prev, "ief"]
        s_cash = sig.loc[prev, "cash"]
        sp = tr_sp.get(t, np.nan)
        cash_ret = rf.get(t, np.nan)
        ief_ret = tr_gs5.get(t, np.nan)
        if pd.isna(sp):
            continue

        # warmup-safe: NaN signal -> that gate passes (risk-on bias, no lookahead)
        trend_on = (s_trend > 0) if pd.notna(s_trend) else True
        vol_on = bool(s_vol) if pd.notna(s_vol) else True
        tip_on = (s_tip > 0) if pd.notna(s_tip) else True

        # safe-asset selection: best of {cash, IEF} by 13612U (NaN -> -inf so other wins)
        ci = s_cash if pd.notna(s_cash) else -np.inf
        ii = s_ief if pd.notna(s_ief) else -np.inf
        if ii >= ci:
            safe_asset, safe_ret = "IEF", ief_ret
        else:
            safe_asset, safe_ret = "cash", cash_ret
        if pd.isna(safe_ret):   # fallback if chosen safe return missing
            safe_asset, safe_ret = "cash", cash_ret

        # BULL stack: AND of three gates
        bull_on = trend_on and vol_on and tip_on
        risk_on["bull_stack"][t] = bull_on
        if bull_on:
            strat_ret["bull_stack"][t] = sp
            safe_choice["bull_stack"][t] = "EQUITY"
        else:
            strat_ret["bull_stack"][t] = safe_ret
            safe_choice["bull_stack"][t] = safe_asset
            # attribution: which gates failed
            failed = []
            if not tip_on:
                failed.append("canary")
            if not trend_on:
                failed.append("trend")
            if not vol_on:
                failed.append("vol")
            binding_leg[str(t)] = failed

        # HAA-Simple: canary AND trend, no vol
        haa_on = tip_on and trend_on
        risk_on["haa_simple"][t] = haa_on
        if haa_on:
            strat_ret["haa_simple"][t] = sp
            safe_choice["haa_simple"][t] = "EQUITY"
        else:
            strat_ret["haa_simple"][t] = safe_ret
            safe_choice["haa_simple"][t] = safe_asset

        # buy & hold
        risk_on["buyhold"][t] = True
        strat_ret["buyhold"][t] = sp
        safe_choice["buyhold"][t] = "EQUITY"

    strat_ret = {v: pd.Series(s).sort_index() for v, s in strat_ret.items()}
    risk_on = {v: pd.Series(s).sort_index() for v, s in risk_on.items()}
    safe_choice = {v: pd.Series(s).sort_index() for v, s in safe_choice.items()}

    # ---- metrics ----
    out = {}
    out["meta"] = {
        "disclaimer": "1970s BACKTEST ONLY. No production or memo implication.",
        "eval_window": [str(EVAL_START), str(EVAL_END)],
        "stag_windows": {k: [str(a), str(b)] for k, (a, b) in STAG_WINDOWS.items()},
        "strategies": {
            "bull_stack": "risk-on iff (TIP 13612U>0) AND (S&P 13612U>0) AND (rv60<rv252); on->100% S&P; off->best of {cash,IEF} by 13612U",
            "haa_simple": "risk-on iff (TIP 13612U>0) AND (S&P 13612U>0); on->100% S&P; off->best of {cash,IEF} by 13612U (= bull_stack minus vol gate)",
            "buyhold": "always 100% S&P 500 TR",
        },
        "data_sources": {
            "sp500_monthly_tr": "Shiller ie_data; (P_t-P_{t-1}+D_t/12)/P_{t-1}; monthly-average price",
            "sp500_daily": "Yahoo ^GSPC daily close (price-only; vol gate only)",
            "synthetic_tip": "FRED GS5 par-bond TR + realized CPIAUCSL inflation",
            "ief_analog": "FRED GS5 (5y CMT) par-bond duration TR",
            "cash": "FRED TB3MS (3m T-bill)",
        },
        "prior_leg_results_1973_74_maxdd_pct": {"trend_only": -9.22, "trend_and_vol": -6.85},
        "caveats": [
            "Synthetic TIP (CPI-accrual proxy); no real TIPS pre-1997; sign-agreement vs real TIP 0.84 in post-2000 overlap only.",
            "TREND signal uses Shiller MONTHLY-AVERAGE S&P price; averaging smooths/lags turning points vs month-end close.",
            "VOL gate uses Yahoo ^GSPC DAILY close -- different price series than trend (documented mismatch).",
            "IEF analog = 5y CMT par-bond duration TR (convexity omitted), NOT the real IEF ETF.",
            "Canary uses TIP-only (no HYG/credit pre-1980); expected non-binding (always-on) in this era.",
            "Warmup months with insufficient history default each gate to pass (no lookahead).",
        ],
    }

    out["full_period"] = {v: metrics(strat_ret[v], rf) for v in variants}

    out["stagflation_windows"] = {}
    for wname, (a, b) in STAG_WINDOWS.items():
        rec = {}
        for v in variants:
            m = metrics(strat_ret[v].loc[a:b], rf)
            rec[v] = {"cagr_pct": m.get("cagr_pct"), "total_return_pct": m.get("total_return_pct"),
                      "maxdd_pct": m.get("maxdd_pct"), "sharpe": m.get("sharpe")}
        bh_dd = rec["buyhold"]["maxdd_pct"]
        for v in variants:
            rec[v]["dd_avoided_vs_buyhold_pp"] = round(rec[v]["maxdd_pct"] - bh_dd, 2)
        out["stagflation_windows"][wname] = rec

    # ---- binding-leg analysis (bull_stack defensive months) ----
    bl_counts = {"canary": 0, "trend": 0, "vol": 0}
    bl_sole = {"canary": 0, "trend": 0, "vol": 0}
    for t, failed in binding_leg.items():
        for leg in failed:
            bl_counts[leg] += 1
        if len(failed) == 1:
            bl_sole[failed[0]] += 1
    out["binding_leg_analysis"] = {
        "definition": "For each bull_stack DEFENSIVE month, which gate(s) failed (were binding).",
        "leg_failure_counts": bl_counts,
        "sole_binding_counts": bl_sole,
        "canary_binding_any_month": bl_counts["canary"],
        "canary_is_noninert": bl_counts["canary"] > 0,
        "per_month": binding_leg,
    }

    # ---- defensive / whipsaw / safe-asset analysis ----
    out["defensive_analysis"] = {}
    sp_next = tr_sp.reindex(eval_months)
    for v in ["bull_stack", "haa_simple"]:
        ro = risk_on[v].reindex(eval_months)
        defensive = ~ro.fillna(True)
        n_def = int(defensive.sum())
        fp = int(((defensive) & (sp_next > 0)).sum())
        tp = int(((defensive) & (sp_next < 0)).sum())
        down = sp_next < 0
        caught = int(((defensive) & down).sum())
        n_down = int(down.sum())
        sc = safe_choice[v].reindex(eval_months)
        n_ief = int((sc == "IEF").sum())
        n_cash = int((sc == "cash").sum())
        out["defensive_analysis"][v] = {
            "n_defensive_months": n_def,
            "whipsaw_false_positive_months": fp,
            "true_positive_def_months": tp,
            "false_positive_rate_pct": round(100 * fp / n_def, 1) if n_def else None,
            "equity_down_months_total": n_down,
            "equity_down_months_caught": caught,
            "down_month_capture_pct": round(100 * caught / n_down, 1) if n_down else None,
            "safe_asset_IEF_months": n_ief,
            "safe_asset_cash_months": n_cash,
            "defensive_months": [str(m) for m in eval_months[defensive.values]],
        }

    # ---- vol-leg attribution: months where bull_stack defensive but HAA risk-on ----
    ro_bull = risk_on["bull_stack"].reindex(eval_months)
    ro_haa = risk_on["haa_simple"].reindex(eval_months)
    vol_only_def = eval_months[(~ro_bull.fillna(True).values) & (ro_haa.fillna(True).values)]
    vol_only_sp = tr_sp.reindex(vol_only_def)
    out["vol_leg_attribution"] = {
        "definition": "Months bull_stack went defensive but HAA-Simple stayed risk-on => the VOL gate was the sole extra protection.",
        "n_months": int(len(vol_only_def)),
        "months": [str(m) for m in vol_only_def],
        "applied_sp_ret_mean_pct": round(float(vol_only_sp.mean()) * 100, 2) if len(vol_only_sp) else None,
        "applied_sp_pct_negative": round(100 * float((vol_only_sp < 0).mean()), 1) if len(vol_only_sp) else None,
    }

    # ---- signal calendar for stagflation windows ----
    out["signal_calendar"] = {}
    for wname, (a, b) in STAG_WINDOWS.items():
        cal = []
        for t in pd.period_range(a - 1, b - 1, freq="M"):
            if t not in sig.index:
                continue
            applied = t + 1
            st, sv, sti = sig.loc[t, "trend"], sig.loc[t, "vol_on"], sig.loc[t, "tip"]
            cal.append({
                "signal_month": str(t), "applied_month": str(applied),
                "tip_on": bool(sti > 0) if pd.notna(sti) else None,
                "trend_on": bool(st > 0) if pd.notna(st) else None,
                "vol_on": bool(sv) if pd.notna(sv) else None,
                "bull_risk_on": bool(risk_on["bull_stack"].get(applied)) if applied in risk_on["bull_stack"].index else None,
                "haa_risk_on": bool(risk_on["haa_simple"].get(applied)) if applied in risk_on["haa_simple"].index else None,
                "bull_safe_asset": str(safe_choice["bull_stack"].get(applied)) if applied in safe_choice["bull_stack"].index else None,
                "sp_ret_pct": round(float(tr_sp.get(applied, np.nan)) * 100, 2) if pd.notna(tr_sp.get(applied, np.nan)) else None,
            })
        out["signal_calendar"][wname] = cal

    def _ser(o):
        if isinstance(o, (np.bool_,)):
            return bool(o)
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, (np.floating,)):
            return float(o)
        raise TypeError(str(type(o)))

    OUT = HERE / "stagflation_1970s_bull_stack_findings.json"
    OUT.write_text(json.dumps(out, indent=2, default=_ser))
    print(f"Wrote {OUT}")

    # console
    print("\n== FULL PERIOD (1968-1985) ==")
    for v in variants:
        m = out["full_period"][v]
        print(f"  {v:12s} CAGR {m['cagr_pct']:>6}%  MaxDD {m['maxdd_pct']:>7}%  Sharpe {m['sharpe']:>6}  vol {m['vol_pct']}%")
    for wname, (a, b) in STAG_WINDOWS.items():
        print(f"\n== {wname} ({a}..{b}) ==")
        for v in variants:
            r = out["stagflation_windows"][wname][v]
            print(f"  {v:12s} ret {r['total_return_pct']:>7}%  MaxDD {r['maxdd_pct']:>7}%  ddAvoid {r['dd_avoided_vs_buyhold_pp']:>6}pp  Sharpe {r['sharpe']}")
    print("\n== BINDING LEG (bull_stack defensive months) ==")
    print(f"  counts {out['binding_leg_analysis']['leg_failure_counts']}  sole {out['binding_leg_analysis']['sole_binding_counts']}")
    print(f"  canary non-inert? {out['binding_leg_analysis']['canary_is_noninert']}")
    print("\n== DEFENSIVE ==")
    for v in ["bull_stack", "haa_simple"]:
        da = out["defensive_analysis"][v]
        print(f"  {v:12s} def={da['n_defensive_months']:>3}  whipsaw={da['whipsaw_false_positive_months']:>3} ({da['false_positive_rate_pct']}%)  downCap={da['down_month_capture_pct']}%  IEF={da['safe_asset_IEF_months']} cash={da['safe_asset_cash_months']}")
    va = out["vol_leg_attribution"]
    print(f"\n== VOL-LEG ATTRIB == n={va['n_months']} appliedSPmean={va['applied_sp_ret_mean_pct']}% %neg={va['applied_sp_pct_negative']}")
    return out


if __name__ == "__main__":
    main()
