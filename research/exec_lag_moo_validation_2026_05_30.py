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
OPEN_CACHE = Path("/tmp/cpm_open_cache")
OPEN_CACHE_INTRADAY_SANITY_MAX = 0.50
OHLC_TICKERS = ['SPY','QQQ','SPHQ','EFA','EEM','VNQ','GLD','TLT','DBC','SHV','IEF','HYG','TIP']

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


def _assert_open_cache_adjusted(opens_df, closes_df, threshold=OPEN_CACHE_INTRADAY_SANITY_MAX):
    intraday_abs = (closes_df / opens_df - 1.0).abs().replace([np.inf, -np.inf], np.nan)
    bad_mask = intraday_abs > threshold
    if not bool(bad_mask.to_numpy().any()):
        return
    bad = intraday_abs.where(bad_mask).stack(dropna=True)
    dt, ticker = bad.idxmax()
    val = float(bad.max())
    raise ValueError(
        "Open-cache contamination detected: "
        f"{ticker} {pd.Timestamp(dt).date()} has |close/open - 1|={val:.2%} "
        f"(>{threshold:.0%}) in {OPEN_CACHE}. "
        "Regenerate cache with yfinance auto_adjust=True for BOTH Open and Close."
    )


def load_open_close():
    """Return (open_df, close_df) of REAL yfinance auto_adjust OHLC, aligned union index."""
    OPEN_CACHE.mkdir(parents=True, exist_ok=True)

    opens, closes = {}, {}
    for t in OHLC_TICKERS:
        p = OPEN_CACHE / f"{t}.csv"
        if not p.exists():
            d = yf.download(t, start="1999-01-01", auto_adjust=True, progress=False, threads=False)
            if isinstance(d.columns, pd.MultiIndex):
                lvl0 = d.columns.get_level_values(0)
                lvl1 = d.columns.get_level_values(1)
                if "Open" in lvl0 and "Close" in lvl0:
                    d.columns = lvl0
                elif "Open" in lvl1 and "Close" in lvl1:
                    d.columns = lvl1
                else:
                    d.columns = [c[0] if isinstance(c, tuple) else c for c in d.columns]
            d = d[["Open", "Close"]].dropna()
            d.index.name = "Date"
            d.to_csv(p)

        d = pd.read_csv(p, parse_dates=[0], index_col=0)
        opens[t] = d["Open"]
        closes[t] = d["Close"]

    opens_df = pd.DataFrame(opens).sort_index()
    closes_df = pd.DataFrame(closes).sort_index()
    _assert_open_cache_adjusted(opens_df, closes_df)
    return opens_df, closes_df


# ---------------------------------------------------------------------------
# Segment backtest with explicit execution convention, real opens.
# convention in {"moc", "moo", "moc1"}.
#   moc  : audit exec_lag=0 economics (production same-day-close).
#   moc1 : audit exec_lag=1 economics (harsh full extra day).
#   moo  : exec_lag=0 weight placement; on rebal day af override new-basket
#          return cc[af] -> intraday[af] = close_yf[af]/open_yf[af]-1 (real opens).
# ---------------------------------------------------------------------------

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

    # MOO conventions: override rebal-day (apply_from) return.
    #   moo   : conservative -> new basket earns intraday only (overnight gap dropped).
    #   mooex : exact realistic -> old basket earns overnight close[T]->open[af],
    #           then new basket earns intraday open[af]->close[af] (compounded).
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

    # turnover costs at each apply_from
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
