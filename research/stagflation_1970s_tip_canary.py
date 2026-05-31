#!/usr/bin/env python3
"""
Stagflation 1970s TIP-canary efficacy test (foundational, multi-episode).

QUESTION
--------
Does a (synthetic) TIP-momentum canary -- and the credit-OR-TIP / credit-AND-TIP
variants used in production logic -- actually de-risk EQUITY through REAL 1970s
stagflation drawdowns (1973-74, 1977-82)? The prior canary_variant_test.py
skipped this: its panel starts 1995, so 2022 (n=1) was the only real-data
stagflation episode. HYG (high yield) and the ETF risky universe do not exist
pre-1980, so this is NOT a HYG-OR-TIP vs TIP-only production rerun. It is the
foundational question on a single equity sleeve (S&P 500) gated by canary
13612U momentum, with a LONG-HISTORY credit analog (Moody's Baa corporate-bond
total return) standing in for HYG pre-1980.

DATA SOURCES (all public; raw CSVs cached under research/data_1970s/)
--------------------------------------------------------------------
1. S&P 500 monthly price + dividend: Robert Shiller dataset (Yale ie_data),
   datahub mirror datasets/s-and-p-500/data/data.csv (faithful Shiller mirror).
   -> S&P 500 monthly TOTAL return reconstructed (price + reinvested dividend).
2. CPI: FRED CPIAUCSL (monthly, seasonally adjusted, 1947+).
3. Nominal intermediate Treasury: FRED GS5 (5-year constant-maturity yield,
   1953+) -> monthly total return via par-bond duration reconstruction.
   (GS10 also cached for sensitivity.)
4. Credit (HYG analog): FRED BAA (Moody's Seasoned Baa Corporate Bond Yield,
   1919+) -> monthly total return via long-corporate par-bond duration
   reconstruction (N=20y).
5. Cash / defensive asset: FRED TB3MS (3-month T-bill secondary market rate)
   -> monthly = rate/1200.

CONSTRUCTIONS (documented)
--------------------------
* S&P 500 monthly total return:
    TR_t = (P_t - P_{t-1} + D_t/12) / P_{t-1}
  where P = Shiller monthly S&P price, D = Shiller annualized dividend/share
  (so D/12 = month's reinvested dividend). Standard Shiller TR reconstruction.

* Constant-maturity bond total return (Treasury GS5 N=5, Baa N=20):
  Treat as a par coupon bond repriced each month; coupon rate = prior yield.
    income_t      = y_{t-1} / 12
    price_ret_t   = -Dmod_{t-1} * (y_t - y_{t-1})        [first-order, duration]
    TR_t          = income_t + price_ret_t
  Dmod = modified duration of a par bond (semiannual coupons, coupon=yield).
  First-order (duration-only) approximation; convexity omitted (second order;
  the canary uses only the SIGN of 13612U momentum, so this is sufficient).
  Duration assumption documented; Baa N is the main sensitivity (long corp).

* SYNTHETIC TIP -- SAME construction as canary_variant_test.py:
    syn_TIP monthly TR = nominal intermediate-Treasury TR + realized monthly
                         CPI(CPIAUCSL) inflation
  (TIPS principal accretes with CPI; inflation accrual is the piece a nominal
  bond proxy misses.) Cumulated to a price index; used ONLY for the canary
  13612U signal. NO real TIPS exist pre-1997. canary_variant_test.py validated
  this synthetic-vs-real-TIP 13612U SIGN AGREEMENT = 0.84 over 300 overlap
  months (2000-06+); that is the only place the proxy can be checked.

CANARY / TEST LOGIC (13612U, same as production cpm_live.sig_13612U)
--------------------------------------------------------------------
  13612U = mean of 1/3/6/12-month total returns of the canary price index.
  Signal computed at end of month t (>=13 months history); applied to month
  t+1 (1-month implementation lag, no lookahead). Equity sleeve = S&P 500.
  Variants (gate equity risk-on/off):
    1. tip_only      : risk-on iff syn_TIP 13612U > 0
    2. credit_or_tip : risk-on iff (Baa>0 OR  TIP>0)   [HYG-OR-TIP analog]
    3. credit_and_tip: risk-on iff (Baa>0 AND TIP>0)
    4. buyhold       : always risk-on (= S&P 500 buy & hold)
  Defensive months earn the 3-month T-bill.

OUTPUT
------
  research/stagflation_1970s_tip_canary_findings.json
  (markdown findings written separately)
"""
from __future__ import annotations
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
DATA = HERE / "data_1970s"

EVAL_START = pd.Period("1968-01", "M")
EVAL_END = pd.Period("1985-12", "M")
STAG_WINDOWS = {
    "bear_1973_74": (pd.Period("1973-01", "M"), pd.Period("1974-12", "M")),
    "stagflation_1977_82": (pd.Period("1977-01", "M"), pd.Period("1982-12", "M")),
}


# ---------------------------------------------------------------------------
# Loaders -> monthly PeriodIndex series
# ---------------------------------------------------------------------------
def _load_fred(name, col):
    df = pd.read_csv(DATA / name)
    df.columns = ["date", col]
    df["date"] = pd.to_datetime(df["date"]).dt.to_period("M")
    return df.set_index("date")[col].astype(float)


def load_inputs():
    cpi = _load_fred("fred_CPIAUCSL.csv", "CPIAUCSL")
    gs5 = _load_fred("fred_GS5.csv", "GS5") / 100.0
    gs10 = _load_fred("fred_GS10.csv", "GS10") / 100.0
    baa = _load_fred("fred_BAA.csv", "BAA") / 100.0
    tb3 = _load_fred("fred_TB3MS.csv", "TB3MS") / 100.0

    sh = pd.read_csv(DATA / "shiller_sp500_monthly.csv")
    sh["Date"] = pd.to_datetime(sh["Date"]).dt.to_period("M")
    sh = sh.set_index("Date")
    sp_p = pd.to_numeric(sh["SP500"], errors="coerce")
    sp_d = pd.to_numeric(sh["Dividend"], errors="coerce")
    # drop trailing zero-padded rows (mirror pads recent months with 0 dividend)
    sp_p = sp_p[sp_p > 0]
    return dict(cpi=cpi, gs5=gs5, gs10=gs10, baa=baa, tb3=tb3, sp_p=sp_p, sp_d=sp_d)


# ---------------------------------------------------------------------------
# Constructions
# ---------------------------------------------------------------------------
def par_bond_mod_duration(y, N, freq=2):
    """Modified duration of a par bond (coupon rate = yield y, N years)."""
    y = float(y)
    m = int(round(N * freq))
    i = y / freq
    c = y / freq  # par => coupon per period = per-period yield
    ts = np.arange(1, m + 1)
    cf = np.full(m, c, dtype=float)
    cf[-1] += 1.0
    if abs(i) < 1e-12:
        pv = cf.copy()
    else:
        pv = cf / (1.0 + i) ** ts
    price = pv.sum()  # ~= 1.0 at par
    dmac_periods = (ts * pv).sum() / price
    dmac_years = dmac_periods / freq
    dmod = dmac_years / (1.0 + i)
    return dmod


def bond_total_return(yld: pd.Series, N: int) -> pd.Series:
    """Monthly TR of a constant-maturity par bond from its yield series.
    income = y_{t-1}/12 ; price_ret = -Dmod_{t-1}*(y_t - y_{t-1})."""
    yld = yld.dropna().sort_index()
    dmod = yld.apply(lambda v: par_bond_mod_duration(v, N))
    y_prev = yld.shift(1)
    dmod_prev = dmod.shift(1)
    dy = yld - y_prev
    income = y_prev / 12.0
    price_ret = -dmod_prev * dy
    tr = (income + price_ret).dropna()
    return tr


def sp500_total_return(sp_p: pd.Series, sp_d: pd.Series) -> pd.Series:
    """Shiller TR: (P_t - P_{t-1} + D_t/12)/P_{t-1}."""
    idx = sp_p.index
    d = sp_d.reindex(idx)
    p_prev = sp_p.shift(1)
    tr = (sp_p - p_prev + d / 12.0) / p_prev
    return tr.dropna()


def cum_index(tr: pd.Series, base=100.0) -> pd.Series:
    return base * (1.0 + tr).cumprod()


# ---------------------------------------------------------------------------
# Signal (matches cpm_live.sig_13612U on a monthly price series)
# ---------------------------------------------------------------------------
def sig_13612U_at(price: pd.Series, asof: pd.Period) -> float:
    p = price.loc[:asof].dropna()
    if len(p) < 13:
        return np.nan
    last = p.iloc[-1]
    r1 = last / p.iloc[-2] - 1
    r3 = last / p.iloc[-4] - 1
    r6 = last / p.iloc[-7] - 1
    r12 = last / p.iloc[-13] - 1
    return (r1 + r3 + r6 + r12) / 4.0


# ---------------------------------------------------------------------------
# Metrics (monthly)
# ---------------------------------------------------------------------------
def metrics(r: pd.Series, rf: pd.Series) -> dict:
    r = r.dropna()
    if r.empty:
        return {}
    n = len(r)
    growth = float((1.0 + r).prod())
    cagr = growth ** (12.0 / n) - 1.0
    vol = float(r.std(ddof=0) * np.sqrt(12))
    rf_a = rf.reindex(r.index).fillna(0.0)
    ex = r - rf_a
    ex_vol = float(ex.std(ddof=0) * np.sqrt(12))
    sharpe = float(ex.mean() * 12 / ex_vol) if ex_vol > 0 else float("nan")
    eq = (1.0 + r).cumprod()
    dd = (eq / eq.cummax() - 1.0)
    maxdd = float(dd.min())
    return {
        "n_months": n,
        "total_return_pct": round((growth - 1.0) * 100, 2),
        "cagr_pct": round(cagr * 100, 2),
        "vol_pct": round(vol * 100, 2),
        "sharpe": round(sharpe, 3),
        "maxdd_pct": round(maxdd * 100, 2),
    }


def window_maxdd(r: pd.Series, a: pd.Period, b: pd.Period) -> float:
    sub = r.loc[a:b].dropna()
    if sub.empty:
        return float("nan")
    eq = (1.0 + sub).cumprod()
    return float((eq / eq.cummax() - 1.0).min())


def window_total_return(r: pd.Series, a: pd.Period, b: pd.Period) -> float:
    sub = r.loc[a:b].dropna()
    return float((1.0 + sub).prod() - 1.0) if len(sub) else float("nan")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    d = load_inputs()
    cpi_infl = d["cpi"].pct_change()

    # nominal intermediate Treasury TR (5y) + GS10 sensitivity
    tr_gs5 = bond_total_return(d["gs5"], N=5)
    tr_gs10 = bond_total_return(d["gs10"], N=7)  # 10y CMT ~ behaves like ~7y dur bond; doc
    tr_baa = bond_total_return(d["baa"], N=20)

    # synthetic TIP TR = nominal intermediate Treasury TR + realized CPI inflation
    idx = tr_gs5.index.intersection(cpi_infl.index)
    tr_tip = (tr_gs5.reindex(idx) + cpi_infl.reindex(idx)).dropna()

    # S&P 500 total return
    tr_sp = sp500_total_return(d["sp_p"], d["sp_d"])

    # T-bill monthly (defensive asset return)
    rf = d["tb3"] / 12.0

    # canary price indices
    px_tip = cum_index(tr_tip)
    px_baa = cum_index(tr_baa)

    # ---- per-month signals (as of end of month t) ----
    all_months = pd.period_range(EVAL_START - 1, EVAL_END, freq="M")
    sig_rows = []
    for t in all_months:
        sig_rows.append({
            "month": t,
            "tip": sig_13612U_at(px_tip, t),
            "baa": sig_13612U_at(px_baa, t),
        })
    sig = pd.DataFrame(sig_rows).set_index("month")

    # ---- backtest: signal at end(t-1) applies to month t ----
    eval_months = pd.period_range(EVAL_START, EVAL_END, freq="M")
    variants = ["tip_only", "credit_or_tip", "credit_and_tip", "buyhold"]
    strat_ret = {v: {} for v in variants}
    risk_on = {v: {} for v in variants}
    for t in eval_months:
        prev = t - 1
        s_tip = sig.loc[prev, "tip"] if prev in sig.index else np.nan
        s_baa = sig.loc[prev, "baa"] if prev in sig.index else np.nan
        sp = tr_sp.get(t, np.nan)
        cash = rf.get(t, np.nan)
        if pd.isna(sp):
            continue
        decide = {
            "tip_only": (s_tip > 0),
            "credit_or_tip": (s_baa > 0) or (s_tip > 0),
            "credit_and_tip": (s_baa > 0) and (s_tip > 0),
            "buyhold": True,
        }
        for v in variants:
            on = bool(decide[v]) if not (pd.isna(s_tip) and v != "buyhold") else True
            # if signal NaN (insufficient history) default risk-on (warmup safety)
            risk_on[v][t] = on
            strat_ret[v][t] = sp if on else cash

    strat_ret = {v: pd.Series(s).sort_index() for v, s in strat_ret.items()}
    risk_on = {v: pd.Series(s).sort_index() for v, s in risk_on.items()}

    # ---- metrics ----
    out = {}
    out["meta"] = {
        "eval_window": [str(EVAL_START), str(EVAL_END)],
        "stag_windows": {k: [str(a), str(b)] for k, (a, b) in STAG_WINDOWS.items()},
        "data_sources": {
            "sp500": "Shiller ie_data (datahub mirror datasets/s-and-p-500); price+dividend",
            "cpi": "FRED CPIAUCSL",
            "intermediate_treasury": "FRED GS5 (5y CMT yield) -> par-bond duration TR",
            "credit": "FRED BAA (Moody's Baa corp yield) -> par-bond (N=20) duration TR",
            "cash": "FRED TB3MS (3m T-bill)",
        },
        "constructions": {
            "sp500_tr": "(P_t - P_{t-1} + D_t/12)/P_{t-1}",
            "bond_tr": "income=y_{t-1}/12 ; price_ret=-Dmod_{t-1}*(y_t-y_{t-1}) ; duration-only (convexity omitted)",
            "synthetic_tip": "nominal 5y Treasury TR + realized monthly CPIAUCSL inflation (same as canary_variant_test.py)",
            "signal": "13612U = mean(1,3,6,12m returns); end-of-month t signal applied to month t+1",
        },
        "synthetic_tip_proxy_validation": {
            "note": "No real TIPS pre-1997; cannot validate sign in 1970s directly.",
            "overlap_era_sign_agreement_vs_real_TIP": 0.84,
            "overlap_months": 300,
            "source": "research/canary_variant_test_findings.json (2000-06+ overlap)",
        },
        "caveats": [
            "Synthetic TIP is a CPI-accrual proxy; no real TIPS pre-1997. Sign-agreement vs real TIP = 0.84 in post-2000 overlap only.",
            "1970s equity = Shiller S&P monthly (monthly-average price; not daily close).",
            "Bond TR is a first-order par-bond duration reconstruction (convexity omitted); Baa duration N=20 is an assumption (long corporate).",
            "Credit analog = Moody's Baa (investment-grade long corp), NOT high yield; HYG did not exist pre-1980. Baa is the longest-history credit-risk series.",
            "Defensive asset = 3m T-bill; intermediate Treasuries as defensive would change defensive-leg returns (not tested here).",
        ],
    }

    out["full_period"] = {v: metrics(strat_ret[v], rf) for v in variants}

    # stagflation windows
    out["stagflation_windows"] = {}
    for wname, (a, b) in STAG_WINDOWS.items():
        rec = {}
        for v in variants:
            sub = strat_ret[v].loc[a:b]
            m = metrics(sub, rf)
            rec[v] = {
                "cagr_pct": m.get("cagr_pct"),
                "total_return_pct": m.get("total_return_pct"),
                "maxdd_pct": m.get("maxdd_pct"),
                "sharpe": m.get("sharpe"),
            }
        # drawdown avoided vs buyhold
        bh_dd = rec["buyhold"]["maxdd_pct"]
        for v in variants:
            rec[v]["dd_avoided_vs_buyhold_pp"] = round(rec[v]["maxdd_pct"] - bh_dd, 2)
        out["stagflation_windows"][wname] = rec

    # real (CPI-deflated) S&P buy-hold drawdown for context (validate ~-48% real)
    sp_idx = cum_index(tr_sp.loc[EVAL_START:EVAL_END])
    cpi_lvl = d["cpi"].reindex(sp_idx.index)
    real_sp = sp_idx / cpi_lvl
    real_dd = (real_sp / real_sp.cummax() - 1.0)
    out["sp500_real_context"] = {
        "real_maxdd_full_pct": round(float(real_dd.min()) * 100, 2),
        "real_maxdd_1973_74_pct": round(float((real_sp.loc[:STAG_WINDOWS['bear_1973_74'][1]] /
                                       real_sp.loc[:STAG_WINDOWS['bear_1973_74'][1]].cummax() - 1).loc[
                                       STAG_WINDOWS['bear_1973_74'][0]:].min()) * 100, 2),
        "nominal_maxdd_buyhold_full_pct": out["full_period"]["buyhold"]["maxdd_pct"],
    }

    # ---- defensive-month analysis ----
    out["defensive_analysis"] = {}
    sp_next = tr_sp.reindex(eval_months)
    for v in variants:
        if v == "buyhold":
            continue
        ro = risk_on[v].reindex(eval_months)
        defensive = ~ro.fillna(True)
        n_def = int(defensive.sum())
        def_months = [str(m) for m in eval_months[defensive.values]]
        # false positives: defensive but S&P rose that month
        fp = int(((defensive) & (sp_next > 0)).sum())
        # true positives: defensive and S&P fell
        tp = int(((defensive) & (sp_next < 0)).sum())
        # coverage of equity down-months
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
            "defensive_months": def_months,
        }

    # ---- override analysis (OR variant: credit keeps risk-on when TIP de-risks) ----
    sig_e = sig.reindex(pd.period_range(EVAL_START - 1, EVAL_END - 1, freq="M"))
    override_or = []   # tip<=0 & baa>0 -> OR stays on, tip_only would de-risk
    only_tip_on = []   # tip>0 & baa<=0 -> AND would de-risk though tip on
    for t in sig_e.index:
        st, sb = sig_e.loc[t, "tip"], sig_e.loc[t, "baa"]
        if pd.isna(st) or pd.isna(sb):
            continue
        applied = t + 1  # month the decision applies to
        spret = tr_sp.get(applied, np.nan)
        if st <= 0 < sb:
            override_or.append({"signal_month": str(t), "applied_month": str(applied),
                                "tip": round(float(st), 4), "baa": round(float(sb), 4),
                                "sp_ret_pct": round(float(spret) * 100, 2) if pd.notna(spret) else None})
        if sb <= 0 < st:
            only_tip_on.append({"signal_month": str(t), "applied_month": str(applied),
                                "tip": round(float(st), 4), "baa": round(float(sb), 4),
                                "sp_ret_pct": round(float(spret) * 100, 2) if pd.notna(spret) else None})
    or_sp = [x["sp_ret_pct"] for x in override_or if x["sp_ret_pct"] is not None]
    out["override_analysis"] = {
        "definition": "override_or = month TIP 13612U<=0 AND Baa 13612U>0 (credit-OR-TIP stays risk-on though TIP says de-risk). Core user concern: does credit override HURT in stagflation?",
        "n_override_or": len(override_or),
        "override_or_applied_sp_mean_pct": round(float(np.mean(or_sp)), 2) if or_sp else None,
        "override_or_applied_sp_pct_negative": round(100 * float(np.mean(np.array(or_sp) < 0)), 1) if or_sp else None,
        "override_or_months": override_or,
        "n_baa_neg_tip_pos": len(only_tip_on),
        "baa_neg_tip_pos_months": only_tip_on,
    }

    # ---- signal calendar across stagflation windows ----
    out["signal_calendar"] = {}
    for wname, (a, b) in STAG_WINDOWS.items():
        rows = []
        for t in pd.period_range(a - 1, b - 1, freq="M"):
            if t not in sig.index:
                continue
            st, sb = sig.loc[t, "tip"], sig.loc[t, "baa"]
            applied = t + 1
            rows.append({
                "signal_month": str(t), "applied_month": str(applied),
                "tip_sig": round(float(st), 4) if pd.notna(st) else None,
                "baa_sig": round(float(sb), 4) if pd.notna(sb) else None,
                "tip_on": bool(st > 0) if pd.notna(st) else None,
                "baa_on": bool(sb > 0) if pd.notna(sb) else None,
                "sp_ret_pct": round(float(tr_sp.get(applied, np.nan)) * 100, 2) if pd.notna(tr_sp.get(applied, np.nan)) else None,
            })
        out["signal_calendar"][wname] = rows

    def _ser(o):
        if isinstance(o, (np.bool_,)):
            return bool(o)
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, (np.floating,)):
            return float(o)
        raise TypeError(str(type(o)))

    OUT = HERE / "stagflation_1970s_tip_canary_findings.json"
    OUT.write_text(json.dumps(out, indent=2, default=_ser))
    print(f"Wrote {OUT}")

    # console summary
    print("\n== FULL PERIOD (1968-1985) ==")
    for v in variants:
        m = out["full_period"][v]
        print(f"  {v:16s} CAGR {m['cagr_pct']:>6}%  MaxDD {m['maxdd_pct']:>7}%  Sharpe {m['sharpe']:>5}  vol {m['vol_pct']}%")
    for wname, (a, b) in STAG_WINDOWS.items():
        print(f"\n== {wname} ({a}..{b}) ==")
        for v in variants:
            r = out["stagflation_windows"][wname][v]
            print(f"  {v:16s} ret {r['total_return_pct']:>7}%  MaxDD {r['maxdd_pct']:>7}%  ddAvoid {r['dd_avoided_vs_buyhold_pp']:>6}pp  Sharpe {r['sharpe']}")
    print("\n== DEFENSIVE ==")
    for v in ["tip_only", "credit_or_tip", "credit_and_tip"]:
        da = out["defensive_analysis"][v]
        print(f"  {v:16s} def={da['n_defensive_months']:>3}  FP={da['false_positive_def_months']:>3} ({da['false_positive_rate_pct']}%)  downCapture={da['down_month_capture_pct']}%")
    print("\n== OVERRIDE (OR: tip<=0 & baa>0) ==")
    oa = out["override_analysis"]
    print(f"  n_override={oa['n_override_or']}  applied SP mean={oa['override_or_applied_sp_mean_pct']}%  %neg={oa['override_or_applied_sp_pct_negative']}")
    print(f"  real SP buyhold MaxDD full={out['sp500_real_context']['real_maxdd_full_pct']}%  1973-74={out['sp500_real_context']['real_maxdd_1973_74_pct']}%")
    return out


if __name__ == "__main__":
    main()
