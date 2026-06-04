"""Throwaway research: validate T+0 MOC vs realistic T+1 MOO vs harsh T+1 MOC.

Question
--------
Production engine fills T+0 MOC: signal at close T, new basket earns
close[T]->close[T+1]. A prior audit (lookahead_audit_2026_05_30.py) penalized
this with exec_lag=1 (earns close[T+1]->close[T+2]) = effectively T+1 MOC, a
FULL extra trading session of lag. But realistic monthly execution is T+1 MOO:
signal after close T, fill at OPEN of T+1. If the overnight gap close[T]->open[T+1]
is small, T+0 MOC ~= T+1 MOO and the engine's same-day fill is a valid proxy,
making the audit's penalty an artifact of the harsher MOC convention.

We validate with REAL OPEN PRICE DATA (yfinance auto_adjust OHLC).

Three conventions (rebal day = first trading day after month-end T, = af):
  T+0 MOC (production):  new basket earns close[T]->close[T+1]  (= cc[af])
                         = overnight gap + intraday day af.
  T+1 MOO (realistic):   new basket earns open[af]->close[af]   (= intraday only)
                         overnight gap close[T]->open[af] NOT credited to new
                         basket (conservative; old==new for the gap).
  T+1 MOC (audit harsh): new basket earns close[af]->close[af+1] (full extra day).

Gate forms (BULL _vol_gate_ok), controlled explicitly via monkeypatch (do NOT
rely on whatever is staged in production):
  RV_20d : RV_20d  < RV_252d crossover  (original / pre-swap)
  RV_60d : RV_60d  < RV_252d crossover  (staged swap, S1-60)

Blend = 0.60*CPM + 0.40*BULL (PRIMARY). BULL solo = SECONDARY.
Metrics: Calmar (primary), MaxDD, vol, CAGR; Sharpe = trailing context only.
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import bull_spy_live
from bull_spy_live import BULL_TICKER, CASH_TICKER, compute_bull_spy_weights
import lookahead_audit_2026_05_30 as audit
from cpm_live import (
    load_panel, compute_target_weights, perf_metrics,
    RISKY_UNIVERSE, SAFE_POOL, CANARY_ASSETS, DEFAULT_CASH, COST_BPS_PER_SIDE,
)

CPM_W, BULL_W = 0.60, 0.40
from engine import (
    OPEN_CACHE,
    OPEN_CACHE_INTRADAY_SANITY_MAX,
    OHLC_TICKERS,
    _assert_open_cache_adjusted,
    load_open_close,
    _segment_returns_conv,
)

# Explicit gates (signature (daily_spy_close, sig_d) -> (bool, diag)).
_ORIG_VOL_GATE = bull_spy_live._vol_gate_ok

def gate_rv(fast, slow=252):
    def g(daily_spy, sig_d):
        sub = daily_spy.loc[:sig_d].pct_change().dropna()
        if len(sub) < slow:
            return True, {"warmup": True}
        vf = float(sub.tail(fast).std() * np.sqrt(252))
        vs = float(sub.tail(slow).std() * np.sqrt(252))
        return (vf < vs), {"vf": vf, "vs": vs}
    return g

GATE_RV20 = gate_rv(20)
GATE_RV60 = gate_rv(60)


def cpm_sleeve_conv(panel, intraday, overnight, start, end, convention):
    cols = sorted(set(RISKY_UNIVERSE + SAFE_POOL + CANARY_ASSETS + [DEFAULT_CASH]) & set(panel.columns))
    close = panel[cols]
    daily_ret = close.ffill().pct_change()
    wf = lambda sd: compute_target_weights(close, sd)[0]
    return _segment_returns_conv(close, daily_ret, wf, start, end, convention,
                                 COST_BPS_PER_SIDE, intraday, overnight)


def bull_sleeve_conv(panel, intraday, overnight, start, end, convention, gate):
    bull_spy_live._vol_gate_ok = gate
    try:
        cols = sorted(set([BULL_TICKER, CASH_TICKER] + list(bull_spy_live.SAFE_POOL)
                          + ["HYG", "TIP"]) & set(panel.columns))
        close = panel[cols]
        daily_ret = panel.ffill().pct_change()
        wf = lambda sd: compute_bull_spy_weights(panel, sd, panel[BULL_TICKER])[0]
        return _segment_returns_conv(close, daily_ret, wf, start, end, convention,
                                     bull_spy_live.COST_BPS_PER_SIDE, intraday, overnight)
    finally:
        bull_spy_live._vol_gate_ok = _ORIG_VOL_GATE


def met(daily, cash, label):
    m = perf_metrics(daily, cash)
    return {"name": label, "sharpe": m.get("sharpe"), "cagr": m.get("cagr"),
            "maxdd": m.get("max_drawdown"), "calmar": m.get("calmar"), "vol": m.get("vol")}


def fmt(rows):
    hdr = f"{'series':<34}{'Calmar':>8}{'MaxDD':>9}{'Vol':>8}{'CAGR':>9}{'Sharpe':>8}"
    out = [hdr, "-" * len(hdr)]
    for r in rows:
        out.append(f"{r['name']:<34}{r['calmar']:>8.3f}{r['maxdd']*100:>8.2f}%"
                   f"{r['vol']*100:>7.2f}%{r['cagr']*100:>8.2f}%{r['sharpe']:>8.3f}")
    return "\n".join(out)


def main():
    end = pd.Timestamp("2026-05-30")
    ext_start = pd.Timestamp("1999-03-10")
    clean_start = pd.Timestamp("2008-05-30")

    panel = load_panel(start=ext_start, end=end)
    end = min(end, panel.index[-1])
    cash_daily = panel["SHV"].ffill().pct_change().dropna()

    open_df, close_yf = load_open_close()
    # intraday return per asset on each day = close_yf/open_yf - 1, reindexed to panel.
    intraday = (close_yf / open_df - 1.0).reindex(panel.index)
    # overnight gap per asset = open_yf[t]/close_yf[prev] - 1
    overnight = (open_df / close_yf.shift(1) - 1.0).reindex(panel.index)

    print(f"Panel {panel.index[0].date()} -> {panel.index[-1].date()} ({len(panel)} rows)")
    print(f"Real OHLC tickers: {OHLC_TICKERS}\n")

    # ---- VERIFY real opens loaded & differ from closes ----
    print("=== VERIFY: real opens differ from closes (yfinance auto_adjust) ===")
    for t in ["SPY", "QQQ", "GLD"]:
        sub = open_df[[t]].join(close_yf[[t]], lsuffix="_open", rsuffix="_close").dropna().tail(3)
        for d, row in sub.iterrows():
            print(f"  {t} {d.date()}  open={row[f'{t}_open']:.4f}  close={row[f'{t}_close']:.4f}  "
                  f"intraday={row[f'{t}_close']/row[f'{t}_open']-1:+.4%}")
    print()

    # ---- STEP 1: overnight gap on REBALANCE days ----
    monthly_idx = (pd.DataFrame({"x": 1}, index=panel.index)
                   .groupby(pd.Grouper(freq="ME")).tail(1))
    sigs = monthly_idx.index[(monthly_idx.index >= clean_start) & (monthly_idx.index <= end)].tolist()
    # rebal day = first trading day after each sig
    rebal_days = []
    for sd in sigs:
        fut = panel.index[panel.index > sd]
        if len(fut):
            rebal_days.append(fut[0])
    rebal_idx = pd.DatetimeIndex(rebal_days)

    print("=== STEP 1: overnight gap close[T]->open[T+1] on REBALANCE days (clean 18y) ===")
    print(f"{'asset':<8}{'n':>5}{'mean|gap|':>11}{'med|gap|':>11}{'std gap':>10}{'mean|cc|day':>13}{'gap/day':>9}")
    print("-" * 67)
    gap_summary = {}
    full_day = close_yf.pct_change().reindex(panel.index)  # close-to-close daily
    for t in ["SPY", "QQQ", "SPHQ", "EFA", "EEM", "VNQ", "GLD", "TLT", "DBC", "HYG", "TIP", "IEF"]:
        g = overnight[t].reindex(rebal_idx).dropna()
        if len(g) < 5:
            continue
        # mean abs full-day move (all days, same asset) for ratio context
        cc = full_day[t].dropna()
        mad_day = cc.abs().mean()
        gap_summary[t] = (len(g), g.abs().mean(), g.abs().median(), g.std(), mad_day)
        print(f"{t:<8}{len(g):>5}{g.abs().mean()*100:>10.3f}%{g.abs().median()*100:>10.3f}%"
              f"{g.std()*100:>9.3f}%{mad_day*100:>12.3f}%{g.abs().mean()/mad_day:>9.2f}")
    print()

    # ---- STEP 2+3: 3 conventions x 2 gates, blend + bull, clean + ext ----
    windows = {
        "CLEAN 18y (2008-05-30..)": (clean_start, end),
        "EXT 27y (1999-03-10..)":   (ext_start, end),
    }
    conventions = [("moc", "T+0 MOC (prod)"), ("mooex", "T+1 MOO exact"),
                   ("moo", "T+1 MOO consrv"), ("moc1", "T+1 MOC (harsh)")]

    # CPM sleeve is gate-independent: compute once per convention.
    cpm_series = {}
    cpm_fb = {}
    for conv, _ in conventions:
        s, fb = cpm_sleeve_conv(panel, intraday, overnight, ext_start, end, conv)
        cpm_series[conv] = s
        cpm_fb[conv] = fb

    # BULL sleeve per (gate, convention).
    gates = [("RV_20d", GATE_RV20), ("RV_60d", GATE_RV60)]
    bull_series = {}
    bull_fb = {}
    for gname, gate in gates:
        for conv, _ in conventions:
            s, fb = bull_sleeve_conv(panel, intraday, overnight, ext_start, end, conv, gate)
            bull_series[(gname, conv)] = s
            bull_fb[(gname, conv)] = fb

    print("=== MOO real-open coverage (n_real rebal days / n_fallback proxy days) ===")
    for conv, _ in conventions:
        if conv in ("moo", "mooex"):
            print(f"  CPM  {conv}: real={cpm_fb[conv][0]} fallback={cpm_fb[conv][1]}")
            for gname, _ in gates:
                fb = bull_fb[(gname, conv)]
                print(f"  BULL {gname} {conv}: real={fb[0]} fallback={fb[1]}")
    print()

    # SANITY: T+0 MOC bull reproduces production run_bull_spy_backtest (RV_60d staged or RV_20d?).
    print("=== SANITY: T+0 MOC vs production run_bull_spy_backtest (clean 18y) ===")
    for gname, gate in gates:
        bull_spy_live._vol_gate_ok = gate
        try:
            prod = bull_spy_live.run_bull_spy_backtest(panel, clean_start, end,
                                                       cost_bps=bull_spy_live.COST_BPS_PER_SIDE)
        finally:
            bull_spy_live._vol_gate_ok = _ORIG_VOL_GATE
        mine = bull_series[(gname, "moc")].loc[clean_start:end]
        mp = perf_metrics(prod, cash_daily)
        mm = perf_metrics(mine, cash_daily)
        print(f"  gate {gname}: prod Calmar={mp['calmar']:.3f} CAGR={mp['cagr']*100:.2f}% "
              f"MaxDD={mp['max_drawdown']*100:.2f}%  ||  mine Calmar={mm['calmar']:.3f} "
              f"CAGR={mm['cagr']*100:.2f}% MaxDD={mm['max_drawdown']*100:.2f}%")
    print()

    # Tables.
    for gname, _ in gates:
        for wname, (ws, we) in windows.items():
            print("=" * 75)
            print(f"GATE {gname}  |  {wname}")
            print("=" * 75)
            # BLEND (primary)
            blend_rows, bull_rows = [], []
            for conv, clabel in conventions:
                c = cpm_series[conv]
                b = bull_series[(gname, conv)]
                common = c.index.intersection(b.index)
                c2 = c.reindex(common); b2 = b.reindex(common)
                blend = CPM_W * c2 + BULL_W * b2
                bl = blend.loc[(blend.index >= ws) & (blend.index <= we)]
                bb = b2.loc[(b2.index >= ws) & (b2.index <= we)]
                if len(bl) >= 5:
                    blend_rows.append(met(bl, cash_daily, f"BLEND {clabel}"))
                if len(bb) >= 5:
                    bull_rows.append(met(bb, cash_daily, f"BULL  {clabel}"))
            print("BLEND 60/40 (PRIMARY):")
            print(fmt(blend_rows))
            print("\nBULL solo (SECONDARY):")
            print(fmt(bull_rows))
            print()

    # ---- Delta summary: MOO vs MOC, MOC1 vs MOC (blend, both gates, both windows) ----
    print("=" * 75)
    print("DELTA SUMMARY (blend): convention vs T+0 MOC baseline")
    print("=" * 75)
    print(f"{'gate':<7}{'win':<7}{'metric':<8}{'MOC':>8}{'MOOex':>8}{'MOOcv':>8}{'MOC1':>8}"
          f"{'MOOex-MOC':>11}{'MOOcv-MOC':>11}")
    print("-" * 76)
    for gname, _ in gates:
        for wkey, (ws, we) in windows.items():
            wlabel = "clean" if "CLEAN" in wkey else "ext"
            mvals = {}
            for conv, _ in conventions:
                c = cpm_series[conv]; b = bull_series[(gname, conv)]
                common = c.index.intersection(b.index)
                blend = CPM_W * c.reindex(common) + BULL_W * b.reindex(common)
                bl = blend.loc[(blend.index >= ws) & (blend.index <= we)]
                mvals[conv] = perf_metrics(bl, cash_daily)
            for mk, lab in [("calmar", "Calmar"), ("max_drawdown", "MaxDD"), ("sharpe", "Sharpe")]:
                moc, mex, mcv, moc1 = (mvals["moc"][mk], mvals["mooex"][mk],
                                       mvals["moo"][mk], mvals["moc1"][mk])
                sc = 100 if mk == "max_drawdown" else 1
                u = "%" if mk == "max_drawdown" else ""
                print(f"{gname:<7}{wlabel:<7}{lab:<8}{moc*sc:>7.3f}{u}{mex*sc:>7.3f}{u}"
                      f"{mcv*sc:>7.3f}{u}{moc1*sc:>7.3f}{u}{(mex-moc)*sc:>+10.3f}{u}"
                      f"{(mcv-moc)*sc:>+10.3f}{u}")
    print("\nDONE")


if __name__ == "__main__":
    main()
