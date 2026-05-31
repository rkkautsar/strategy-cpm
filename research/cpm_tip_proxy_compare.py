# -*- coding: utf-8 -*-
"""Read-only robustness check: pre-1997 TIP-proxy construction X vs Y.

Adversarial test mirroring AllocateSmartly's "plain IEF for all pre-2003 TIPS"
robustness check. We compare TWO pre-cutover TIP-proxy constructions, EVERYTHING
ELSE IDENTICAL, stitched to the SAME real TIP after the cutover:

  (X) IEF+CPI synthetic = nominal intermediate Treasury total return
                          + realized monthly CPI inflation (FRED CPIAUCSL).
  (Y) plain IEF         = nominal intermediate Treasury total return only
                          (inflation-blind).

Cutover to REAL TIP:
  - Part A (HAA paper window, monthly FRED/Shiller): real TIP = VIPSX monthly TR
    from 2000-07 (first tradeable TIPS fund; 1997 has no tradeable TIPS fund, so
    the synthetic necessarily extends to 2000-06). Pre-2000-07 = X or Y.
  - Part B (CPM extended, daily panel): real TIP = prod tip_stitched (VIPSX,
    2000-06+). Pre-2000-06 TIP is NaN in the prod panel; we inject X or Y over
    1997-12..2000-05 month-ends. Post-2000-06 both use the SAME real TIP, so the
    clean (2008+) window must be IDENTICAL under X and Y (confirms anchor 1.1910).

Harness convention everywhere: mooex T+1 MOO exact, 10 bps/side, monthly signal.

Part A: faithful HAA-Simple over Dec 1970 - Dec 2022 (paper window).
Part B: CPM (HYG-OR-TIP canary) over EXT (1999-03+) and CLEAN (2008-05+).

NO production files touched, NO commit. Writes research/cpm_tip_proxy_compare_*.
"""
import sys, json
from pathlib import Path
import numpy as np
import pandas as pd

REPO = Path("/Users/rkautsar/personal/scripts/strategy_cpm")
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "research"))

DATA70 = REPO / "research" / "data_1970s"
MACRO = REPO / "research" / "_macro_cache"

# reuse audited bond-TR + signal helpers from the 1970s harness
import stagflation_1970s_tip_canary as S70

COST_BPS = 10.0  # per side


# ===========================================================================
# PART A -- HAA-Simple monthly, paper window Dec 1970 - Dec 2022
# ===========================================================================
def _load_fred(name, col):
    df = pd.read_csv(DATA70 / name)
    df.columns = ["date", col]
    df["date"] = pd.to_datetime(df["date"]).dt.to_period("M")
    return df.set_index("date")[col].astype(float)


def _vipsx_monthly_tr():
    """Real TIP monthly total return from VIPSX (Vanguard TIPS), 2000-06+."""
    d = pd.read_csv(MACRO / "VIPSX_tr.csv", parse_dates=["Date"]).set_index("Date")["Close"]
    m = d.resample("ME").last()
    tr = m.pct_change().dropna()
    tr.index = tr.index.to_period("M")
    return tr


def sig_13612U_at(price, asof):
    return S70.sig_13612U_at(price, asof)


def part_a():
    cpi = _load_fred("fred_CPIAUCSL.csv", "CPIAUCSL")
    gs10 = _load_fred("fred_GS10.csv", "GS10") / 100.0
    tb3 = _load_fred("fred_TB3MS.csv", "TB3MS") / 100.0

    sh = pd.read_csv(DATA70 / "shiller_sp500_monthly.csv")
    sh["Date"] = pd.to_datetime(sh["Date"]).dt.to_period("M")
    sh = sh.set_index("Date")
    sp_p = pd.to_numeric(sh["SP500"], errors="coerce")
    sp_d = pd.to_numeric(sh["Dividend"], errors="coerce")
    sp_p = sp_p[sp_p > 0]

    cpi_infl = cpi.pct_change()
    # nominal intermediate Treasury TR: GS10 CMT behaves ~ 7y duration par bond
    tr_ief = S70.bond_total_return(gs10, N=7)
    tr_sp = S70.sp500_total_return(sp_p, sp_d)
    rf = tb3 / 12.0  # monthly T-bill

    tr_tip_real = _vipsx_monthly_tr()
    CUT = pd.Period("2000-07", "M")  # first full month of real TIP (VIPSX inception 2000-06-29)

    # synthetic pre-cutover legs
    idx_pre = tr_ief.index.intersection(cpi_infl.index)
    tr_X_pre = (tr_ief.reindex(idx_pre) + cpi_infl.reindex(idx_pre)).dropna()  # IEF+CPI
    tr_Y_pre = tr_ief.copy()                                                   # plain IEF

    def stitch(pre):
        a = pre[pre.index < CUT]
        b = tr_tip_real[tr_tip_real.index >= CUT]
        return pd.concat([a, b]).sort_index()

    tr_X = stitch(tr_X_pre)
    tr_Y = stitch(tr_Y_pre)

    # cash price index (for best-of-safe 13612U) and IEF/SPY price indices
    px_ief = S70.cum_index(tr_ief)
    px_sp = S70.cum_index(tr_sp)
    px_cash = S70.cum_index(rf)
    px_X = S70.cum_index(tr_X)
    px_Y = S70.cum_index(tr_Y)

    EVAL_START = pd.Period("1970-12", "M")
    EVAL_END = pd.Period("2022-12", "M")

    def run_haa(px_tip):
        """Faithful HAA-Simple. Signal at month t -> hold for month t+1.
        risk-on iff TIP-13612U>0 AND SPY-13612U>0 -> SPY
        else best-of({IEF, cash}) by 13612U. 10bps/side on switch."""
        months = pd.period_range(EVAL_START, EVAL_END, freq="M")
        rets, holds = [], []
        prev = None
        for t in months:
            t_prev = t - 1
            tip_s = sig_13612U_at(px_tip, t_prev)
            spy_s = sig_13612U_at(px_sp, t_prev)
            ief_s = sig_13612U_at(px_ief, t_prev)
            cash_s = sig_13612U_at(px_cash, t_prev)
            if pd.notna(tip_s) and tip_s > 0 and pd.notna(spy_s) and spy_s > 0:
                hold = "SPY"
            else:
                hold = "IEF" if (pd.notna(ief_s) and pd.notna(cash_s) and ief_s >= cash_s) else "CASH"
            # realized month-t return of held asset
            r = {"SPY": tr_sp, "IEF": tr_ief, "CASH": rf}[hold].get(t, np.nan)
            if pd.isna(r):
                continue
            if prev is not None and prev != hold:
                r -= 2 * COST_BPS / 1e4  # full 100% switch: sell+buy
            rets.append((t, r)); holds.append((t, hold)); prev = hold
        s = pd.Series(dict(rets)).sort_index()
        h = pd.Series(dict(holds)).sort_index()
        return s, h

    sX, hX = run_haa(px_X)
    sY, hY = run_haa(px_Y)

    def met(r):
        r = r.dropna()
        n = len(r)
        growth = float((1 + r).prod())
        cagr = growth ** (12 / n) - 1
        rf_a = rf.reindex(r.index).fillna(0.0)
        ex = r - rf_a
        exvol = float(ex.std(ddof=0) * np.sqrt(12))
        sharpe = float(ex.mean() * 12 / exvol) if exvol > 0 else float("nan")
        eq = (1 + r).cumprod()
        maxdd = float((eq / eq.cummax() - 1).min())
        calmar = cagr / abs(maxdd) if maxdd < 0 else float("nan")
        return {"n_months": n, "cagr": round(cagr, 6), "vol": round(float(r.std(ddof=0)*np.sqrt(12)), 6),
                "sharpe": round(sharpe, 4), "maxdd": round(maxdd, 6), "calmar": round(calmar, 4)}

    mX, mY = met(sX), met(sY)

    # where does divergence concentrate? months where the HOLD differs
    common = hX.index.intersection(hY.index)
    diff_months = [str(t) for t in common if hX[t] != hY[t]]
    # per-year cumulative return gap (X - Y)
    cum_gap = ((1 + sX).cumprod() - (1 + sY).cumprod())
    by_year = {}
    for t, r in (sX - sY.reindex(sX.index).fillna(0)).items():
        y = t.year
        by_year[y] = by_year.get(y, 0.0) + float(r)
    # top divergent years by abs additive monthly-return gap
    top_years = sorted(by_year.items(), key=lambda kv: -abs(kv[1]))[:8]

    return {
        "window": "1970-12 .. 2022-12 (paper)",
        "cutover_to_real_tip": str(CUT),
        "real_tip_source": "VIPSX monthly TR (inception 2000-06-29)",
        "X_IEF_plus_CPI": mX,
        "Y_plain_IEF": mY,
        "delta_X_minus_Y": {
            "sharpe": round(mX["sharpe"] - mY["sharpe"], 4),
            "calmar": round(mX["calmar"] - mY["calmar"], 4),
            "maxdd": round(mX["maxdd"] - mY["maxdd"], 6),
            "cagr": round(mX["cagr"] - mY["cagr"], 6),
        },
        "n_months_hold_differs": len(diff_months),
        "hold_differs_months": diff_months,
        "additive_return_gap_by_year_top8": [[y, round(v, 4)] for y, v in top_years],
    }


# ===========================================================================
# PART B -- CPM extended (daily panel), TIP override pre-2000-06
# ===========================================================================
def part_b():
    from cpm_live import load_panel, perf_metrics, COST_BPS_PER_SIDE
    import exec_lag_moo_validation_2026_05_30 as H

    end = pd.Timestamp("2026-05-22")
    ext_start = pd.Timestamp("1999-03-10")
    clean_start = pd.Timestamp("2008-05-30")

    panel = load_panel(start=ext_start, end=end)
    end = min(end, panel.index[-1])
    cash = panel["SHV"].ffill().pct_change().dropna()

    open_df, close_yf = H.load_open_close()
    intraday = (close_yf / open_df - 1.0).reindex(panel.index)
    overnight = (open_df / close_yf.shift(1) - 1.0).reindex(panel.index)

    # CPI monthly inflation (FRED), as a daily-forward-filled monthly accrual
    cpi = _load_fred("fred_CPIAUCSL.csv", "CPIAUCSL")
    cpi_infl_m = cpi.pct_change().dropna()  # PeriodIndex monthly

    tip_first_real = panel["TIP"].first_valid_index()  # 2000-06-29

    # month-end IEF TR (from panel) before real TIP starts; build synthetic TIP idx
    me = panel.resample("ME").last()
    ief_me = me["IEF"].dropna()
    ief_tr_m = ief_me.pct_change().dropna()
    # restrict to pre-real-TIP plus warmup
    pre_mask = ief_tr_m.index < tip_first_real
    ief_tr_pre = ief_tr_m[pre_mask]

    def build_synth_tip(add_cpi):
        # synthetic monthly TR index, anchored so it continuously joins real TIP
        rows = {}
        base = 100.0
        lvl = base
        for dt, r in ief_tr_pre.items():
            per = dt.to_period("M")
            infl = float(cpi_infl_m.get(per, 0.0)) if add_cpi else 0.0
            lvl *= (1 + r + infl)
            rows[dt] = lvl
        s = pd.Series(rows).sort_index()
        return s  # month-end synthetic TIP index (pre real-TIP)

    def override_panel(add_cpi):
        p = panel.copy()
        synth_me = build_synth_tip(add_cpi)
        # write synthetic month-end values into the daily TIP column, ffilled,
        # only on dates strictly before the first real TIP date.
        tip = p["TIP"].copy()
        # daily ffill of month-end synthetic over pre-real-TIP range
        synth_daily = synth_me.reindex(p.index, method="ffill")
        pre_idx = p.index[p.index < tip_first_real]
        tip.loc[pre_idx] = synth_daily.loc[pre_idx]
        p["TIP"] = tip
        return p

    def run(p):
        ser, _ = H.cpm_sleeve_conv(p, intraday, overnight, ext_start, end, "mooex")
        return ser

    pX = override_panel(add_cpi=True)
    pY = override_panel(add_cpi=False)
    sX = run(pX)
    sY = run(pY)

    def met(ser, a, b):
        sw = ser.loc[(ser.index >= a) & (ser.index <= b)]
        m = perf_metrics(sw, cash)
        return {"sharpe": round(m.get("sharpe"), 4), "cagr": round(m.get("cagr"), 6),
                "vol": round(m.get("vol"), 6), "maxdd": round(m.get("max_drawdown"), 6),
                "calmar": round(m.get("calmar"), 4)}

    extX = met(sX, ext_start, end); extY = met(sY, ext_start, end)
    clX = met(sX, clean_start, end); clY = met(sY, clean_start, end)

    # where do daily series differ?
    common = sX.index.intersection(sY.index)
    d = (sX.reindex(common).fillna(0) - sY.reindex(common).fillna(0))
    diff_days = d[d.abs() > 1e-12]
    first_diff = str(diff_days.index[0].date()) if len(diff_days) else None
    last_diff = str(diff_days.index[-1].date()) if len(diff_days) else None

    return {
        "windows": {"EXT": "1999-03-10..%s" % end.date(), "CLEAN": "2008-05-30..%s" % end.date()},
        "tip_real_first": str(tip_first_real.date()),
        "synthetic_override_range": "1997-12..2000-05 month-ends (TIP NaN in prod panel here)",
        "EXT": {"X_IEF_plus_CPI": extX, "Y_plain_IEF": extY,
                "delta_X_minus_Y": {"sharpe": round(extX["sharpe"]-extY["sharpe"], 4),
                                    "calmar": round(extX["calmar"]-extY["calmar"], 4),
                                    "maxdd": round(extX["maxdd"]-extY["maxdd"], 6)}},
        "CLEAN": {"X_IEF_plus_CPI": clX, "Y_plain_IEF": clY,
                  "delta_X_minus_Y": {"sharpe": round(clX["sharpe"]-clY["sharpe"], 4),
                                      "calmar": round(clX["calmar"]-clY["calmar"], 4),
                                      "maxdd": round(clX["maxdd"]-clY["maxdd"], 6)},
                  "anchor_note": "expect CPM clean Sharpe ~1.1910 and X==Y (real TIP post-2000-06)"},
        "n_days_series_differ": int(len(diff_days)),
        "first_diff_day": first_diff,
        "last_diff_day": last_diff,
    }


def main():
    out = {"harness": "mooex T+1 MOO exact, 10 bps/side, monthly signal",
           "constructions": {
               "X": "IEF+CPI synthetic = nominal intermediate Treasury TR (GS10 N=7 / panel IEF) + realized monthly CPIAUCSL inflation",
               "Y": "plain IEF = nominal intermediate Treasury TR only (inflation-blind)"},
           }
    print("=== PART A: HAA-Simple, paper window 1970-12..2022-12 ===")
    out["part_a_haa_simple"] = part_a()
    print(json.dumps(out["part_a_haa_simple"], indent=2))
    print("\n=== PART B: CPM extended + clean ===")
    out["part_b_cpm"] = part_b()
    print(json.dumps(out["part_b_cpm"], indent=2))

    (REPO / "research" / "cpm_tip_proxy_compare_findings.json").write_text(json.dumps(out, indent=2))
    print("\nWROTE research/cpm_tip_proxy_compare_findings.json")
    return out


if __name__ == "__main__":
    main()
