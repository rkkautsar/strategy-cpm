"""Analyst (read-only re prod/memo; writes research/ only; no commit).

Computes the four COMPUTE additions requested by the external memo review:
  1. Common-window EXTENDED comparison (all series share latest common start).
  2. Leave-one-asset-out robustness (clean window).
  3. Calendar-year returns (CPM vs AAA vs 60/40) + max intra-year drawdown.
  4. Worst-interval table (worst 1/3/12m return + longest underwater duration).

Harness parity: reuses the EXACT mooex T+1-MOO harness behind the memo headline
(research/exec_lag_moo_validation_2026_05_30._segment_returns_conv +
research/cpm_benchmarks_proper build_data / weight fns). 10 bps/side, monthly
month-end signal, real-open mooex execution. Reproduces the clean anchor
(Sharpe 1.1910 / MaxDD -12.67% / Calmar 1.0615) BEFORE any new table.

Items 5/6/7 are documentation-driven (DSR + proxy findings) and are folded
directly into the markdown deliverable, not computed here.
"""
import sys, json, math
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

# bull_spy_live bit-rotted (no _vol_gate_ok); CPM sleeve path does not need it.
import bull_spy_live
if not hasattr(bull_spy_live, "_vol_gate_ok"):
    bull_spy_live._vol_gate_ok = lambda *a, **k: (True, {})

import exec_lag_moo_validation_2026_05_30 as H
import cpm_benchmarks_proper as B
from cpm_live import (
    compute_target_weights, perf_metrics, RISKY_UNIVERSE, SAFE_POOL,
    CANARY_ASSETS, DEFAULT_CASH, COST_BPS_PER_SIDE,
)

CONV = "mooex"
END = pd.Timestamp("2026-05-22")
EXT_START = pd.Timestamp("1999-03-10")
CLEAN_START = pd.Timestamp("2008-05-30")


def met(daily, cash):
    m = perf_metrics(daily, cash)
    return {"sharpe": m.get("sharpe"), "cagr": m.get("cagr"), "vol": m.get("vol"),
            "maxdd": m.get("max_drawdown"), "calmar": m.get("calmar"),
            "martin": m.get("martin"), "ulcer": m.get("ulcer")}


def cpm_cols(panel):
    return sorted(set(RISKY_UNIVERSE + SAFE_POOL + CANARY_ASSETS + [DEFAULT_CASH]) & set(panel.columns))


def cpm_sleeve(panel, intraday, overnight, start, end, universe=None):
    cols = cpm_cols(panel)
    close = panel[cols]
    daily = close.ffill().pct_change()
    wf = lambda sd: compute_target_weights(close, sd, universe=universe)[0]
    s, fb = H._segment_returns_conv(close, daily, wf, start, end, CONV,
                                    COST_BPS_PER_SIDE, intraday, overnight)
    return s


def max_dd(eq):
    rm = eq.cummax()
    return float((eq / rm - 1.0).min())


def underwater_days(daily):
    """Longest underwater (drawdown) duration in calendar days."""
    eq = (1.0 + daily).cumprod()
    rm = eq.cummax()
    underwater = eq < rm * (1 - 1e-12)
    longest = pd.Timedelta(0)
    cur_start = None
    last_peak = eq.index[0]
    for d, uw in underwater.items():
        if uw:
            if cur_start is None:
                cur_start = last_peak
        else:
            if cur_start is not None:
                longest = max(longest, d - cur_start)
                cur_start = None
            last_peak = d
    if cur_start is not None:
        longest = max(longest, underwater.index[-1] - cur_start)
    return int(longest.days)


def worst_horizon(daily, months):
    """Worst rolling N-month total return on month-end compounded series."""
    me = (1.0 + daily).cumprod().resample("ME").last()
    rr = me / me.shift(months) - 1.0
    rr = rr.dropna()
    if rr.empty:
        return float("nan"), None
    return float(rr.min()), rr.idxmin()


def main():
    out = {"meta": {"conv": CONV, "cost_bps": COST_BPS_PER_SIDE,
                    "end": str(END.date()), "clean_start": str(CLEAN_START.date()),
                    "ext_start": str(EXT_START.date())}}

    panel, intraday, overnight, end = B.build_data(EXT_START, END)
    cash = panel["SHV"].ffill().pct_change().dropna()
    print(f"Panel {panel.index[0].date()} -> {panel.index[-1].date()} ({len(panel)} rows)\n")

    # ---- build the 5 series via the SAME harness as the headline benchmark run ----
    cpm = cpm_sleeve(panel, intraday, overnight, EXT_START, end)

    aaa_cols = sorted(set([t for t in B.AAA_UNIVERSE if t in panel.columns] + ["SHV", "IEF"]))
    aaa_close = panel[aaa_cols]
    aaa_daily = aaa_close.ffill().pct_change()
    rwx_fv = panel["RWX"].first_valid_index()
    aaa_ext_start = max(EXT_START, (rwx_fv + pd.DateOffset(months=13)) if rwx_fv is not None else EXT_START)
    aaa = B.run_wf(aaa_close, aaa_daily, intraday, overnight, aaa_ext_start, end,
                   B.make_canonical_aaa_wf(aaa_close, aaa_daily))[0]

    bm_cols = sorted(set(RISKY_UNIVERSE + ["SPY", "IEF", "SHV"]) & set(panel.columns))
    bm_close = panel[bm_cols]
    bm_daily = bm_close.ffill().pct_change()
    sixty = B.run_wf(bm_close, bm_daily, intraday, overnight, EXT_START, end, B.make_6040_wf(bm_close))[0]
    naive = B.run_wf(bm_close, bm_daily, intraday, overnight, EXT_START, end, B.make_naive12_wf(bm_close))[0]
    bhiv = B.run_wf(bm_close, bm_daily, intraday, overnight, EXT_START, end, B.make_buyhold_invvol_wf(bm_close))[0]

    series = {"CPM": cpm, "AAA": aaa, "60/40": sixty, "Naive12m": naive, "BuyHoldInvVol": bhiv}

    # ---- ANCHOR ----
    cpm_c = cpm.loc[CLEAN_START:end]
    anchor = met(cpm_c, cash)
    out["anchor"] = anchor
    print("=== ANCHOR (clean 18y, mooex) ===")
    print(f"  Sharpe={anchor['sharpe']:.4f} MaxDD={anchor['maxdd']*100:.2f}% Calmar={anchor['calmar']:.4f}")
    print("  expect 1.1910 / -12.67% / 1.0615\n")

    # ===== ITEM 1: COMMON-WINDOW EXTENDED =====
    # Latest common start across ALL 5 series = AAA (RWX inception + warmup).
    common5 = max(aaa_ext_start, EXT_START)
    # also a 4-series common window EXCLUDING AAA (the binding constraint).
    common4 = EXT_START
    out["item1"] = {"common5_start": str(common5.date()), "common4_start": str(common4.date()),
                    "aaa_ext_start": str(aaa_ext_start.date()),
                    "all5": {}, "ex_aaa_4": {}}
    for nm, s in series.items():
        sc = s.loc[(s.index >= common5) & (s.index <= end)]
        out["item1"]["all5"][nm] = met(sc, cash)
    for nm in ["CPM", "60/40", "Naive12m", "BuyHoldInvVol"]:
        s = series[nm]
        sc = s.loc[(s.index >= common4) & (s.index <= end)]
        out["item1"]["ex_aaa_4"][nm] = met(sc, cash)
    print(f"=== ITEM1 common-window extended (all5 from {common5.date()}) ===")
    for nm in series:
        m = out["item1"]["all5"][nm]
        print(f"  {nm:<14} Sh={m['sharpe']:.3f} CAGR={m['cagr']*100:.2f}% MDD={m['maxdd']*100:.2f}% "
              f"Cal={m['calmar']:.3f} Mar={m['martin']:.3f}")
    print()

    # ===== ITEM 2: LEAVE-ONE-ASSET-OUT (clean) =====
    out["item2"] = {"baseline": anchor, "drops": {}}
    print("=== ITEM2 leave-one-asset-out (clean) ===")
    print(f"  baseline (full 8): Sh={anchor['sharpe']:.4f} MDD={anchor['maxdd']*100:.2f}% Cal={anchor['calmar']:.4f}")
    for drop in RISKY_UNIVERSE:
        red = [a for a in RISKY_UNIVERSE if a != drop]
        s = cpm_sleeve(panel, intraday, overnight, EXT_START, end, universe=red)
        sc = s.loc[(s.index >= CLEAN_START) & (s.index <= end)]
        m = met(sc, cash)
        out["item2"]["drops"][drop] = m
        print(f"  ex-{drop:<5} Sh={m['sharpe']:.4f} ({m['sharpe']-anchor['sharpe']:+.4f}) "
              f"MDD={m['maxdd']*100:.2f}% Cal={m['calmar']:.4f} ({m['calmar']-anchor['calmar']:+.4f})")
    print()

    # ===== ITEM 3: CALENDAR-YEAR RETURNS (clean) =====
    def cal_year(s):
        sc = s.loc[(s.index >= CLEAN_START) & (s.index <= end)]
        rows = {}
        for yr, grp in sc.groupby(sc.index.year):
            tot = float((1.0 + grp).prod() - 1.0)
            eq = (1.0 + grp).cumprod()
            rows[int(yr)] = {"ret": tot, "intra_maxdd": max_dd(eq)}
        return rows
    out["item3"] = {"CPM": cal_year(cpm), "AAA": cal_year(aaa), "60/40": cal_year(sixty)}
    print("=== ITEM3 calendar-year (clean) — CPM ret / intra-DD ===")
    for yr in sorted(out["item3"]["CPM"]):
        c = out["item3"]["CPM"][yr]
        print(f"  {yr}: ret={c['ret']*100:+.2f}% intraDD={c['intra_maxdd']*100:.2f}%")
    print()

    # ===== ITEM 4: WORST-INTERVAL =====
    out["item4"] = {}
    print("=== ITEM4 worst-interval (clean) ===")
    for nm, s in [("CPM", cpm), ("AAA", aaa), ("60/40", sixty)]:
        sc = s.loc[(s.index >= CLEAN_START) & (s.index <= end)]
        w1, d1 = worst_horizon(sc, 1)
        w3, d3 = worst_horizon(sc, 3)
        w12, d12 = worst_horizon(sc, 12)
        uw = underwater_days(sc)
        out["item4"][nm] = {
            "worst_1m": w1, "worst_1m_end": str(d1.date()) if d1 is not None else None,
            "worst_3m": w3, "worst_3m_end": str(d3.date()) if d3 is not None else None,
            "worst_12m": w12, "worst_12m_end": str(d12.date()) if d12 is not None else None,
            "longest_underwater_days": uw,
        }
        print(f"  {nm:<7} 1m={w1*100:.2f}% 3m={w3*100:.2f}% 12m={w12*100:.2f}% uw={uw}d")
    print()

    Path(__file__).with_suffix(".json").write_text(json.dumps(out, indent=2, default=float))
    print("DONE -> json written")


if __name__ == "__main__":
    main()
