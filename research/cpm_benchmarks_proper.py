"""Throwaway research (SCOPED, read-only): replace the bespoke 8-of-10 AAA bench
with a CANONICAL 10-asset AAA + investor-relevant alternatives, full metric set,
and paired block-bootstrap difference-CIs for CPM-minus-each-benchmark Sharpe.

Convention everywhere = headline: T+1 MOO exact (mooex), 10 bps/side, monthly
month-end signal. Same _segment_returns_conv harness as the headline run, so
cost/window/execution are byte-identical across CPM and every benchmark.

Benchmarks:
  (A) CANONICAL AAA 10-asset: [SPY, EZU, EWJ, EEM, IYR, RWX, IEF, TLT, DBC, GLD],
      top-half (5) by 6m total-return momentum, SLSQP min-variance weight over
      survivors, NO canary, NO cash/positive filter (defense = bonds rising in
      the relative-momentum rank). RWX inception 2006-12 -> ext == clean.
  (B) 60/40: SPY 0.60 / IEF 0.40, monthly rebal.
  (C) Naive 12m momentum on CPM risky universe: positive-12m screen, equal-weight
      survivors, SHV when none. NO canary, NO inverse-vol.
  (D) Buy-hold inverse-vol on CPM risky universe: static inverse-vol (504d) over
      all 8 risky assets, monthly rebal, no momentum/canary.
  CPM: production sleeve (cpm_sleeve_conv).

Data sources:
  - load_panel(): in-repo frozen stitched panel (CPM/AAA closes; GLD/TLT/IEF/SHV/
    HYG/TIP stitched from Vanguard funds; QQQ via NDX proxy pre-1999).
  - /tmp/cpm_open_cache (yfinance auto_adjust OHLC) for mooex real opens.
  - research/_macro_cache/{EWJ,RWX,EZU,IYR}_ohlc.csv (yfinance auto_adjust OHLC,
    fetched 2026-05-31) for the canonical AAA non-CPM tickers.
"""
import sys, math, json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.optimize import minimize

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import bull_spy_live  # noqa: F401 (harness parity)
from cpm_live import (
    load_panel, perf_metrics, sig_13612U, best_safe, inv_vol_weights,
    RISKY_UNIVERSE, COST_BPS_PER_SIDE, CORR_LOOKBACK_DAYS,
)
import exec_lag_moo_validation_2026_05_30 as H

CONV = "mooex"
MACRO = Path(__file__).resolve().parent / "_macro_cache"
AAA_UNIVERSE = ["SPY", "EZU", "EWJ", "EEM", "IYR", "RWX", "IEF", "TLT", "DBC", "GLD"]
AAA_EXTRA = ["EWJ", "RWX", "EZU", "IYR"]   # not in load_panel; from _macro_cache
MINVAR_LOOKBACK = 504
SEED = 12345


# --------------------------------------------------------------------------
# panel / execution data with the 4 extra AAA tickers merged in
# --------------------------------------------------------------------------
def build_data(ext_start, end):
    panel = load_panel(start=ext_start, end=end)
    end = min(end, panel.index[-1])

    open_df, close_yf = H.load_open_close()
    extra_open, extra_close = {}, {}
    for t in AAA_EXTRA:
        d = pd.read_csv(MACRO / f"{t}_ohlc.csv", parse_dates=["Date"], index_col="Date")
        extra_open[t] = d["Open"]
        extra_close[t] = d["Close"]
        panel = panel.join(d[["Close"]].rename(columns={"Close": t}), how="left")
    open_df = open_df.join(pd.DataFrame(extra_open), how="outer").sort_index()
    close_yf = close_yf.join(pd.DataFrame(extra_close), how="outer").sort_index()

    panel = panel.sort_index()
    panel = panel[panel.index <= end]
    intraday = (close_yf / open_df - 1.0).reindex(panel.index)
    overnight = (open_df / close_yf.shift(1) - 1.0).reindex(panel.index)
    return panel, intraday, overnight, end


# --------------------------------------------------------------------------
# weight functions
# --------------------------------------------------------------------------
def _minvar_weights(daily, sd, top):
    cov = daily.loc[:sd].tail(MINVAR_LOOKBACK)[top].cov() * 252
    n = len(top)
    def obj(w, C=cov.values):
        return float(np.dot(w, np.dot(C, w)))
    cons = ({"type": "eq", "fun": lambda w: np.sum(w) - 1.0},)
    bnds = tuple((0.0, 1.0) for _ in range(n))
    r = minimize(obj, np.ones(n) / n, method="SLSQP", bounds=bnds, constraints=cons)
    return {top[i]: float(r.x[i]) for i in range(n)} if r.success else {t: 1.0 / n for t in top}


def mom_6m(p):
    p = p.dropna()
    if len(p) < 7:
        return np.nan
    return float(p.iloc[-1] / p.iloc[-7] - 1.0)


def mom_12m(p):
    p = p.dropna()
    if len(p) < 13:
        return np.nan
    return float(p.iloc[-1] / p.iloc[-13] - 1.0)


def make_canonical_aaa_wf(close, daily):
    """Canonical AAA: top-half (ceil(N/2)) by 6m momentum, SLSQP min-var weights.
    No canary, no positive/cash filter."""
    uni = [t for t in AAA_UNIVERSE if t in close.columns]
    def wf(sd):
        monthly = close.loc[:sd].resample("ME").last()
        scores = {t: mom_6m(monthly[t]) for t in uni if t in monthly.columns}
        scores = {t: s for t, s in scores.items() if pd.notna(s)}
        if len(scores) < 2:
            return {best_safe(monthly, sd, ["IEF", "SHV"]): 1.0}
        ranked = sorted(scores.items(), key=lambda x: -x[1])
        top_half = max(2, math.ceil(len(uni) / 2))
        top = [t for t, _ in ranked[:top_half]]
        return _minvar_weights(daily, sd, top)
    return wf


def make_6040_wf(close):
    def wf(sd):
        return {"SPY": 0.60, "IEF": 0.40}
    return wf


def make_naive12_wf(close):
    uni = [t for t in RISKY_UNIVERSE if t in close.columns]
    def wf(sd):
        monthly = close.loc[:sd].resample("ME").last()
        surv = [t for t in uni if t in monthly.columns and (mom_12m(monthly[t]) or -1) > 0]
        if not surv:
            return {"SHV": 1.0}
        w = 1.0 / len(surv)
        return {t: w for t in surv}
    return wf


def make_buyhold_invvol_wf(close):
    uni = [t for t in RISKY_UNIVERSE if t in close.columns]
    def wf(sd):
        avail = [t for t in uni if t in close.columns and close.loc[:sd, t].first_valid_index() is not None]
        if not avail:
            return {"SHV": 1.0}
        w = inv_vol_weights(close.loc[:sd], avail, CORR_LOOKBACK_DAYS)
        return w if w else {t: 1.0 / len(avail) for t in avail}
    return wf


# --------------------------------------------------------------------------
# runners / metrics
# --------------------------------------------------------------------------
def run_wf(close, daily, intraday, overnight, start, end, wf):
    s, fb = H._segment_returns_conv(close, daily, wf, start, end, CONV,
                                    COST_BPS_PER_SIDE, intraday, overnight)
    return s, fb


def full_met(daily, cash):
    m = perf_metrics(daily, cash)
    return {"sharpe": m.get("sharpe"), "cagr": m.get("cagr"), "vol": m.get("vol"),
            "maxdd": m.get("max_drawdown"), "calmar": m.get("calmar"),
            "martin": m.get("martin"), "ulcer": m.get("ulcer")}


def sharpe_of(r):
    v = r.std(ddof=0) * np.sqrt(252)
    return float((r.mean() * 252) / v) if v > 0 else float("nan")


def paired_block_bootstrap(cpm, bench, block=21, B=2000, seed=SEED):
    common = cpm.index.intersection(bench.index)
    a = cpm.reindex(common).fillna(0.0).values
    b = bench.reindex(common).fillna(0.0).values
    n = len(a)
    point = sharpe_of(pd.Series(a)) - sharpe_of(pd.Series(b))
    if n < block * 3:
        return {"point": point, "lo": float("nan"), "hi": float("nan"),
                "includes_zero": True, "n": n, "note": "insufficient"}
    rng = np.random.default_rng(seed)
    n_blocks = int(math.ceil(n / block))
    starts_pool = np.arange(0, n - block + 1)
    diffs = np.empty(B)
    for i in range(B):
        starts = rng.choice(starts_pool, size=n_blocks, replace=True)
        idx = np.concatenate([np.arange(s, s + block) for s in starts])[:n]
        ra, rb = a[idx], b[idx]
        va = ra.std(ddof=0) * np.sqrt(252)
        vb = rb.std(ddof=0) * np.sqrt(252)
        sa = (ra.mean() * 252) / va if va > 0 else np.nan
        sb = (rb.mean() * 252) / vb if vb > 0 else np.nan
        diffs[i] = sa - sb
    lo, hi = np.nanpercentile(diffs, [2.5, 97.5])
    return {"point": float(point), "lo": float(lo), "hi": float(hi),
            "includes_zero": bool(lo <= 0.0 <= hi), "B": B, "block": block, "n": n}


def main():
    end = pd.Timestamp("2026-05-22")
    ext_start = pd.Timestamp("1999-03-10")
    clean_start = pd.Timestamp("2008-05-30")

    panel, intraday, overnight, end = build_data(ext_start, end)
    cash = panel["SHV"].ffill().pct_change().dropna()
    print(f"Panel {panel.index[0].date()} -> {panel.index[-1].date()} ({len(panel)} rows)")
    for t in AAA_EXTRA:
        fv = panel[t].first_valid_index()
        print(f"  {t} first valid close: {fv.date() if fv is not None else None}")
    print(f"Convention={CONV} cost={COST_BPS_PER_SIDE}bps/side minvar_lb={MINVAR_LOOKBACK}\n")

    # CPM sleeve over ext
    cpm, _ = H.cpm_sleeve_conv(panel, intraday, overnight, ext_start, end, CONV)

    # AAA panel: canonical 10-asset; ext constrained by RWX (2006-12)+12m warmup
    aaa_cols = [t for t in AAA_UNIVERSE if t in panel.columns] + ["SHV", "IEF"]
    aaa_close = panel[sorted(set(aaa_cols))]
    aaa_daily = aaa_close.ffill().pct_change()
    rwx_fv = panel["RWX"].first_valid_index()
    aaa_ext_start = max(ext_start, (rwx_fv + pd.DateOffset(months=13)) if rwx_fv is not None else ext_start)
    aaa, aaa_fb = run_wf(aaa_close, aaa_daily, intraday, overnight, aaa_ext_start, end,
                         make_canonical_aaa_wf(aaa_close, aaa_daily))

    # CPM-universe benchmarks panel
    bm_cols = sorted(set(RISKY_UNIVERSE + ["SPY", "IEF", "SHV"]) & set(panel.columns))
    bm_close = panel[bm_cols]
    bm_daily = bm_close.ffill().pct_change()
    sixty, _ = run_wf(bm_close, bm_daily, intraday, overnight, ext_start, end, make_6040_wf(bm_close))
    naive, _ = run_wf(bm_close, bm_daily, intraday, overnight, ext_start, end, make_naive12_wf(bm_close))
    bhiv, _ = run_wf(bm_close, bm_daily, intraday, overnight, ext_start, end, make_buyhold_invvol_wf(bm_close))

    series = {"CPM": cpm, "Canonical_AAA": aaa, "60/40": sixty,
              "Naive_12m": naive, "BuyHold_InvVol": bhiv}
    # ext start per series
    ext_starts = {"CPM": ext_start, "Canonical_AAA": aaa_ext_start, "60/40": ext_start,
                  "Naive_12m": ext_start, "BuyHold_InvVol": ext_start}

    out = {"meta": {"convention": CONV, "cost_bps": COST_BPS_PER_SIDE,
                    "minvar_lookback": MINVAR_LOOKBACK, "panel_end": str(end.date()),
                    "aaa_universe": AAA_UNIVERSE, "aaa_ext_start": str(aaa_ext_start.date()),
                    "rwx_first_valid": str(rwx_fv.date()) if rwx_fv is not None else None},
           "clean": {}, "ext": {}, "diff_ci": {}}

    # anchor sanity
    cpm_c = cpm.loc[clean_start:end]
    mc = full_met(cpm_c, cash)
    print("=== ANCHOR (CLEAN 18y, mooex) ===")
    print(f"  CPM Sharpe={mc['sharpe']:.4f} MaxDD={mc['maxdd']*100:.2f}% Calmar={mc['calmar']:.4f}")
    print("  (expect 1.1910 / -12.67% / 1.0615)\n")
    out["anchor"] = {"cpm_clean": mc}

    # metrics
    for name, s in series.items():
        sc = s.loc[(s.index >= clean_start) & (s.index <= end)]
        out["clean"][name] = full_met(sc, cash)
        es = ext_starts[name]
        se = s.loc[(s.index >= es) & (s.index <= end)]
        out["ext"][name] = {**full_met(se, cash), "start": str(es.date())}

    # difference CIs (clean window, paired block bootstrap)
    for name, s in series.items():
        if name == "CPM":
            continue
        cw = cpm.loc[(cpm.index >= clean_start) & (cpm.index <= end)]
        bw = s.loc[(s.index >= clean_start) & (s.index <= end)]
        out["diff_ci"][name] = paired_block_bootstrap(cw, bw, block=21, B=2000)

    Path(__file__).with_suffix(".json").write_text(json.dumps(out, indent=2, default=float))

    # ---- console ----
    order = ["CPM", "Canonical_AAA", "60/40", "Naive_12m", "BuyHold_InvVol"]
    def tbl(win):
        print(f"{'series':<16}{'Sharpe':>8}{'CAGR':>8}{'Vol':>7}{'MaxDD':>9}{'Calmar':>8}{'Martin':>8}{'Ulcer':>8}")
        for nm in order:
            m = out[win][nm]
            print(f"{nm:<16}{m['sharpe']:>8.4f}{m['cagr']*100:>7.2f}%{m['vol']*100:>6.2f}%"
                  f"{m['maxdd']*100:>8.2f}%{m['calmar']:>8.4f}{m['martin']:>8.4f}{m['ulcer']*100:>7.2f}%")

    print("=" * 72)
    print("CLEAN 18y (2008-05-30 -> end)")
    print("=" * 72)
    tbl("clean")
    print("\n" + "=" * 72)
    print("EXT (per-series start; Canonical AAA limited by RWX 2006-12 inception)")
    print("=" * 72)
    print(f"{'series':<16}{'start':>12}{'Sharpe':>8}{'CAGR':>8}{'MaxDD':>9}{'Calmar':>8}{'Martin':>8}")
    for nm in order:
        m = out["ext"][nm]
        print(f"{nm:<16}{m['start']:>12}{m['sharpe']:>8.4f}{m['cagr']*100:>7.2f}%"
              f"{m['maxdd']*100:>8.2f}%{m['calmar']:>8.4f}{m['martin']:>8.4f}")

    print("\n" + "=" * 72)
    print("PAIRED BLOCK-BOOTSTRAP 95% CI: CPM-minus-benchmark Sharpe (CLEAN, B=2000, block=21)")
    print("=" * 72)
    print(f"{'vs benchmark':<18}{'dSharpe':>9}{'CI_lo':>9}{'CI_hi':>9}{'incl 0?':>9}")
    for nm in order[1:]:
        d = out["diff_ci"][nm]
        print(f"{nm:<18}{d['point']:>9.4f}{d['lo']:>9.4f}{d['hi']:>9.4f}{str(d['includes_zero']):>9}")
    print("\nDONE -> json written")


if __name__ == "__main__":
    main()
