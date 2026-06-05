"""Full MOOEX migration recompute: all CPM sleeves + blend + benchmarks.

Canonical convention = mooex T+1 exact (the cpm_harness/verify_anchor mechanism).
Same clean window 2008-05-30..2026-05-22 and ext 1999-03-10..2026-05-22, both-252,
10 bps/side, frozen panel (EVAL_END 2026-05-22). Reuses the proven engine
research/exec_lag_moo_validation_2026_05_30._segment_returns_conv (the exact mooex
overnight-gap attribution that cpm_harness uses for CPM).

Method per sleeve
-----------------
- CPM   : cpm_harness.run_strategy(compute_target_weights) (canonical mooex, anchor).
- BULL  : engine _segment_returns_conv with production compute_bull_spy_weights and
          production _vol_gate_ok. eng 'moc' reproduces run_bull_spy_backtest EXACTLY
          (verified), so eng 'mooex' is the faithful mooex BULL series.
- NDX   : delta overlay on the production engine to preserve its delisting-haircut
          logic. ndx_mooex = run_ndx_backtest + (eng_mooex - eng_moc). The delta is
          nonzero only on rebalance days whose old AND new baskets are macro-cached
          (safe ETFs). NDX active days hold individual NDX stocks that have no OHLC in
          the macro open cache, so they FALL BACK to close-to-close (flagged).
Blend   : 0.6*cpm + 0.2*bull + 0.2*ndx of the mooex DAILY series.
CPM-BULL: 0.6*cpm + 0.4*bull (two-sleeve, no NDX).
Benchmarks: buy-holds (SPY/QQQ) are convention-invariant. BB4/B2/B3/B5/60-40/
          static-PP are strategy-rebalanced -> recomputed under mooex via the engine.
"""
from pathlib import Path
import sys
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import cpm_live
from cpm_live import perf_metrics, COST_BPS_PER_SIDE, compute_target_weights
import bull_spy_live
from bull_spy_live import BULL_TICKER, CASH_TICKER, compute_bull_spy_weights, run_bull_spy_backtest
import ndx_sleeve_live
from ndx_sleeve_live import compute_ndx_weights, run_ndx_backtest, load_ndx_panel
from research import cpm_harness
from research import exec_lag_moo_validation_2026_05_30 as eng

CLEAN = pd.Timestamp("2008-05-30")
EXT = pd.Timestamp("1999-03-10")
END = pd.Timestamp("2026-05-22")
KEYS = ("sharpe", "excess_sharpe", "cagr", "vol", "max_drawdown", "calmar", "martin")


def M(s, cash, lo, hi):
    sc = s.loc[(s.index >= lo) & (s.index <= hi)]
    m = perf_metrics(sc, cash)
    return {k: m.get(k) for k in KEYS}


def row(name, m):
    return (f"{name:<40} {m['sharpe']:.4f} {m['excess_sharpe']:.4f} "
            f"{m['cagr']*100:7.3f}% {m['vol']*100:7.3f}% {m['max_drawdown']*100:8.3f}% "
            f"{m['calmar']:.4f} {m['martin']:.4f}")


def hdr():
    return (f"{'series':<40} {'Sharpe':>6} {'ExcSh':>6} {'CAGR':>8} {'Vol':>8} "
            f"{'MaxDD':>9} {'Calmar':>6} {'Martin':>6}")


def main():
    d = cpm_harness.load_data(end=END, clean_start=CLEAN, ext_start=EXT)
    panel, cash = d.panel, d.cash
    print(f"panel {panel.index[0].date()}..{panel.index[-1].date()} n={len(panel)}")
    print(f"CORR_LOOKBACK_DAYS={cpm_live.CORR_LOOKBACK_DAYS} EVAL_END={cpm_live.EVAL_END}\n")

    # ---------- CPM ----------
    cpm_mooex = cpm_harness.run_strategy(compute_target_weights, window="ext", data=d)
    cpm_cc, _ = cpm_live.run_cpm_backtest(panel, EXT, END)

    # ---------- BULL (engine; moc == prod exactly) ----------
    def bull_wf(sd):
        return compute_bull_spy_weights(panel, sd, panel[BULL_TICKER])[0]
    cols_b = sorted(set([BULL_TICKER, CASH_TICKER] + list(bull_spy_live.SAFE_POOL) + ["HYG", "TIP"]) & set(panel.columns))
    close_b = panel[cols_b]
    dr_b = panel.ffill().pct_change()
    bull_moc, _ = eng._segment_returns_conv(close_b, dr_b, bull_wf, EXT, END, "moc", COST_BPS_PER_SIDE, d.intraday, d.overnight)
    bull_mooex, bull_fb = eng._segment_returns_conv(close_b, dr_b, bull_wf, EXT, END, "mooex", COST_BPS_PER_SIDE, d.intraday, d.overnight)
    bull_cc = run_bull_spy_backtest(panel, EXT, END)

    # ---------- NDX (delta overlay on prod engine) ----------
    ndx_panel = load_ndx_panel()
    full = panel.join(ndx_panel, how="outer", rsuffix="_dup")
    full = full.loc[:, ~full.columns.str.endswith("_dup")]
    full = full.loc[full.index <= END]
    dr_n = full.ffill().pct_change()
    intr = d.intraday.reindex(full.index)
    ovn = d.overnight.reindex(full.index)

    def ndx_wf(sd):
        return compute_ndx_weights(panel, ndx_panel, sd)[0]
    ndx_eng_moc, _ = eng._segment_returns_conv(full, dr_n, ndx_wf, EXT, END, "moc", ndx_sleeve_live.COST_BPS_PER_SIDE, intr, ovn)
    ndx_eng_mooex, ndx_fb = eng._segment_returns_conv(full, dr_n, ndx_wf, EXT, END, "mooex", ndx_sleeve_live.COST_BPS_PER_SIDE, intr, ovn)
    ndx_cc, _ = run_ndx_backtest(panel, ndx_panel, EXT, END)
    ndx_delta = (ndx_eng_mooex - ndx_eng_moc).reindex(ndx_cc.index).fillna(0.0)
    ndx_mooex = ndx_cc + ndx_delta

    # ---------- Blends ----------
    def blend(c, b, n, wc, wb, wn):
        idx = c.index.intersection(b.index)
        if n is not None:
            idx = idx.intersection(n.index)
        out = wc * c.reindex(idx).fillna(0.0) + wb * b.reindex(idx).fillna(0.0)
        if n is not None:
            out = out + wn * n.reindex(idx).fillna(0.0)
        return out

    prod_mooex = blend(cpm_mooex, bull_mooex, ndx_mooex, 0.6, 0.2, 0.2)
    prod_cc = blend(cpm_cc, bull_cc, ndx_cc, 0.6, 0.2, 0.2)
    cb_mooex = blend(cpm_mooex, bull_mooex, None, 0.6, 0.4, None)
    cb_cc = blend(cpm_cc, bull_cc, None, 0.6, 0.4, None)

    # ---------- Benchmarks (mooex via engine; buy-holds invariant) ----------
    import build_dashboard as bd
    # weight-history -> engine weight_fn helpers using the exact bench logic.
    def run_bench_conv(wh_fn, cols, conv, lo, hi):
        close = panel[[c for c in cols if c in panel.columns]]
        dr = close.ffill().pct_change()
        wh = dict(wh_fn())
        wf = lambda sd: wh.get(sd, {})
        s, _ = eng._segment_returns_conv(close, dr, wf, lo, hi, conv, 10.0, d.intraday, d.overnight)
        return s

    # Reuse build_dashboard bench functions directly for close-to-close;
    # for mooex, rebuild via engine using extracted weight histories.
    # (We rebuild B2/B3/B5 weight histories by calling the bench internals.)
    bench_results = {}
    # close-to-close (existing functions)
    bb4_cc = bd.bench_bb4_blend(panel, EXT, END)
    sixty40_cc = bd.sixty_forty(panel, EXT, END)
    spy_bh = panel["SPY"].ffill().pct_change()
    qqq_bh = panel["QQQ"].ffill().pct_change()

    # mooex BB4: extract per-sleeve weight histories from bench functions by
    # monkey-capturing. Simpler: re-derive using the same engine on weight_fns.
    from cpm_live import sig_13612U, best_safe as _best_safe
    from scipy.optimize import minimize
    import math, numpy as np
    AAA = bd.BENCH_AAA_UNIVERSE
    SAFE = bd._BENCH_SAFE

    def b2_wf(sd):
        close = panel[sorted(set(AAA + SAFE + ["TIP"]) & set(panel.columns))]
        daily = close.ffill().pct_change()
        monthly = close.loc[:sd].resample("ME").last()
        safe = _best_safe(monthly, sd, SAFE)
        tipm = sig_13612U(monthly["TIP"]) if "TIP" in monthly.columns else float("nan")
        if not (pd.notna(tipm) and tipm > 0):
            return {safe: 1.0}
        scores = {t: sig_13612U(monthly[t]) for t in AAA if t in monthly.columns}
        scores = {t: s for t, s in scores.items() if pd.notna(s)}
        ranked = sorted(scores.items(), key=lambda x: -x[1])
        top_half = max(2, math.ceil(len(AAA) / 2))
        top = [t for t, s in ranked[:top_half] if s > 0]
        if len(top) == 0:
            return {safe: 1.0}
        if len(top) == 1:
            return {top[0]: 0.5, safe: 0.5}
        cov = daily.loc[:sd].tail(504)[top].cov() * 252
        n = len(top)
        def obj(w, C=cov.values): return float(np.dot(w, np.dot(C, w)))
        cons = ({"type": "eq", "fun": lambda w: np.sum(w) - 1.0},)
        bnds = tuple((0.0, 1.0) for _ in range(n))
        r = minimize(obj, np.ones(n) / n, method="SLSQP", bounds=bnds, constraints=cons)
        return {top[i]: float(r.x[i]) for i in range(n)} if r.success else {t: 1.0 / n for t in top}

    def b3_wf(sd):
        close = panel[sorted(set(["SPY"] + SAFE + ["TIP"]) & set(panel.columns))]
        monthly = close.loc[:sd].resample("ME").last()
        safe = _best_safe(monthly, sd, SAFE)
        tipm = sig_13612U(monthly["TIP"]) if "TIP" in monthly.columns else float("nan")
        amom = sig_13612U(monthly["SPY"]) if "SPY" in monthly.columns else float("nan")
        return {"SPY": 1.0} if (pd.notna(tipm) and tipm > 0 and pd.notna(amom) and amom > 0) else {safe: 1.0}

    def b5_wf(sd):
        close = panel[sorted(set(["QQQ"] + SAFE) & set(panel.columns))]
        monthly = close.loc[:sd].resample("ME").last()
        safe = _best_safe(monthly, sd, SAFE)
        if "QQQ" in monthly.columns and len(monthly["QQQ"]) >= 13:
            r12 = monthly["QQQ"].iloc[-1] / monthly["QQQ"].iloc[-13] - 1
            if pd.notna(r12) and r12 > 0:
                return {"QQQ": 1.0}
        return {safe: 1.0}

    def sixty40_wf(sd):
        return {"SPY": 0.6, "IEF": 0.4}

    def eng_bench(wf, cols, conv):
        close = panel[sorted(set(cols) & set(panel.columns))]
        dr = close.ffill().pct_change()
        s, _ = eng._segment_returns_conv(close, dr, wf, EXT, END, conv, 10.0, d.intraday, d.overnight)
        return s

    def bb4_eng(conv):
        b2 = eng_bench(b2_wf, AAA + SAFE + ["TIP"], conv)
        b3 = eng_bench(b3_wf, ["SPY"] + SAFE + ["TIP"], conv)
        b5 = eng_bench(b5_wf, ["QQQ"] + SAFE, conv)
        ix = b2.index.intersection(b3.index).intersection(b5.index)
        return 0.6 * b2.reindex(ix).fillna(0) + 0.2 * b3.reindex(ix).fillna(0) + 0.2 * b5.reindex(ix).fillna(0)
    bb4_engmoc = bb4_eng("moc")    # engine-consistent CC baseline
    bb4_x = bb4_eng("mooex")
    sixty40_engmoc = eng_bench(sixty40_wf, ["SPY", "IEF"], "moc")
    sixty40_x = eng_bench(sixty40_wf, ["SPY", "IEF"], "mooex")

    # ---------- Print tables ----------
    for wlabel, lo in (("CLEAN 2008-05-30..2026-05-22", CLEAN), ("EXT 1999-03-10..2026-05-22", EXT)):
        print("=" * 110)
        print(f"WINDOW: {wlabel}   (convention column: CC=close-to-close OLD, MOOEX=canonical NEW)")
        print("=" * 110)
        print(hdr())
        print("-" * 110)
        pairs = [
            ("PROD 60/20/20 CC", prod_cc), ("PROD 60/20/20 MOOEX", prod_mooex),
            ("CPM-BULL 60/40 CC", cb_cc), ("CPM-BULL 60/40 MOOEX", cb_mooex),
            ("CPM CC", cpm_cc), ("CPM MOOEX", cpm_mooex),
            ("BULL CC(prod)", bull_cc), ("BULL MOOEX", bull_mooex),
            ("NDX CC(prod)", ndx_cc), ("NDX MOOEX", ndx_mooex),
            ("BB4 lit blend CC(prod fn)", bb4_cc), ("BB4 lit blend CC(eng)", bb4_engmoc), ("BB4 lit blend MOOEX(eng)", bb4_x),
            ("60/40 SPY/IEF CC(prod fn)", sixty40_cc), ("60/40 SPY/IEF CC(eng)", sixty40_engmoc), ("60/40 SPY/IEF MOOEX(eng)", sixty40_x),
            ("SPY buy-hold (invariant)", spy_bh), ("QQQ buy-hold (invariant)", qqq_bh),
        ]
        for nm, s in pairs:
            print(row(nm, M(s, cash, lo, END)))
        print()

    print("COVERAGE (rebalance-day real overnight attribution / fallback to cc):")
    print(f"  BULL mooex ext: real={bull_fb[0]} fallback={bull_fb[1]}")
    print(f"  NDX  mooex ext: real={ndx_fb[0]} fallback={ndx_fb[1]}  (fallback = NDX active days holding non-cached individual stocks)")
    print(f"  NDX delta nonzero days (clean): {int((ndx_delta.loc[CLEAN:END] != 0).sum())}")
    print(f"  ndx_panel span: {ndx_panel.index[0].date()}..{ndx_panel.index[-1].date()}")


if __name__ == "__main__":
    main()

