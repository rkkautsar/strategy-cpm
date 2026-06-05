"""T+1 MOC (moc1) canonical recompute: all CPM sleeves + blend + benchmarks.

Computes the three execution conventions side-by-side for the canonical-shift memo:
  moc   = T+0 MOC  (production close-to-close; standard/comparable number)
  mooex = T+1 MOO  (overnight gap + intraday; needs opens cache)
  moc1  = T+1 MOC  (canonical; CLOSE-ONLY, exec_lag=1, full coverage, no opens)

Same clean window 2008-05-30..2026-05-22 and ext 1999-03-10..2026-05-22, both-252,
10 bps/side, frozen panel (EVAL_END 2026-05-22). Reuses the proven engine
research/exec_lag_moo_validation_2026_05_30._segment_returns_conv.

Method per sleeve (delta-overlay preserves prod logic exactly; the delta between
two engine conventions is the pure execution-lag effect):
  CPM   : engine directly (matches cpm_harness anchor for mooex). Also prod CC.
  BULL  : engine moc == run_bull_spy_backtest EXACTLY (verified). prod CC.
  NDX   : prod run_ndx_backtest (CC) + engine delta. For moc1 the delta is
          (eng_moc1 - eng_moc), pure close-based -> FULL coverage (no opens cache,
          no constituent-opens fallback). This is the key simplification vs mooex.
Blend  : 0.6*cpm + 0.2*bull + 0.2*ndx (PROD). CPM-BULL: 0.6*cpm + 0.4*bull.
Benchmarks: buy-holds invariant; BB4/BB1(60-40) strategy-rebalanced via engine.
"""
from pathlib import Path
import sys
import json
import math
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import cpm_live
from cpm_live import perf_metrics, COST_BPS_PER_SIDE, compute_target_weights, sig_13612U, best_safe as _best_safe
import bull_spy_live
from bull_spy_live import BULL_TICKER, CASH_TICKER, compute_bull_spy_weights, run_bull_spy_backtest
import ndx_sleeve_live
from ndx_sleeve_live import compute_ndx_weights, run_ndx_backtest, load_ndx_panel
from research import cpm_harness
from research import exec_lag_moo_validation_2026_05_30 as eng
from scipy.optimize import minimize
import build_dashboard as bd

CLEAN = pd.Timestamp("2008-05-30")
EXT = pd.Timestamp("1999-03-10")
END = pd.Timestamp("2026-05-22")
KEYS = ("sharpe", "excess_sharpe", "cagr", "vol", "max_drawdown", "calmar", "martin")
CONVS = ("moc", "mooex", "moc1")


def M(s, cash, lo, hi):
    sc = s.loc[(s.index >= lo) & (s.index <= hi)]
    m = perf_metrics(sc, cash)
    return {k: m.get(k) for k in KEYS}


def main():
    d = cpm_harness.load_data(end=END, clean_start=CLEAN, ext_start=EXT)
    panel, cash = d.panel, d.cash
    print(f"panel {panel.index[0].date()}..{panel.index[-1].date()} n={len(panel)}")
    print(f"CORR_LOOKBACK_DAYS={cpm_live.CORR_LOOKBACK_DAYS} EVAL_END={cpm_live.EVAL_END}\n")
    daily_ret = panel.ffill().pct_change()

    # ---------- CPM (engine all convs) ----------
    cpm = {}
    for c in CONVS:
        wf = lambda sd: compute_target_weights(panel, sd)[0]
        s, _ = eng._segment_returns_conv(panel, daily_ret, wf, EXT, END, c, COST_BPS_PER_SIDE, d.intraday, d.overnight)
        cpm[c] = s
    cpm_prod, _ = cpm_live.run_cpm_backtest(panel, EXT, END)

    # ---------- BULL (engine; moc == prod exactly) ----------
    cols_b = sorted(set([BULL_TICKER, CASH_TICKER] + list(bull_spy_live.SAFE_POOL) + ["HYG", "TIP"]) & set(panel.columns))
    close_b = panel[cols_b]
    dr_b = panel.ffill().pct_change()
    def bull_wf(sd):
        return compute_bull_spy_weights(panel, sd, panel[BULL_TICKER])[0]
    bull = {}
    bull_fb = {}
    for c in CONVS:
        s, fb = eng._segment_returns_conv(close_b, dr_b, bull_wf, EXT, END, c, COST_BPS_PER_SIDE, d.intraday, d.overnight)
        bull[c] = s
        bull_fb[c] = fb
    bull_prod = run_bull_spy_backtest(panel, EXT, END)

    # ---------- NDX (prod CC + engine delta; moc1 is pure-close -> full coverage) ----------
    ndx_panel = load_ndx_panel()
    full = panel.join(ndx_panel, how="outer", rsuffix="_dup")
    full = full.loc[:, ~full.columns.str.endswith("_dup")]
    full = full.loc[full.index <= END]
    dr_n = full.ffill().pct_change()
    intr = d.intraday.reindex(full.index)
    ovn = d.overnight.reindex(full.index)
    def ndx_wf(sd):
        return compute_ndx_weights(panel, ndx_panel, sd)[0]
    ndx_eng = {}
    ndx_fb = {}
    for c in CONVS:
        s, fb = eng._segment_returns_conv(full, dr_n, ndx_wf, EXT, END, c, ndx_sleeve_live.COST_BPS_PER_SIDE, intr, ovn)
        ndx_eng[c] = s
        ndx_fb[c] = fb
    ndx_prod, _ = run_ndx_backtest(panel, ndx_panel, EXT, END)
    ndx = {}
    for c in CONVS:
        delta = (ndx_eng[c] - ndx_eng["moc"]).reindex(ndx_prod.index).fillna(0.0)
        ndx[c] = ndx_prod + delta
    # moc1 delta coverage: pure close-based, so no fallback issue
    ndx_moc1_delta_nonzero = int((ndx[ "moc1"].loc[CLEAN:END] - ndx_prod.loc[CLEAN:END] != 0).sum())

    # ---------- Blends ----------
    def blend(c, b, n, wc, wb, wn):
        idx = c.index.intersection(b.index)
        if n is not None:
            idx = idx.intersection(n.index)
        out = wc * c.reindex(idx).fillna(0.0) + wb * b.reindex(idx).fillna(0.0)
        if n is not None:
            out = out + wn * n.reindex(idx).fillna(0.0)
        return out

    prod = {c: blend(cpm[c], bull[c], ndx[c], 0.6, 0.2, 0.2) for c in CONVS}
    cb = {c: blend(cpm[c], bull[c], None, 0.6, 0.4, None) for c in CONVS}
    # prod CC reference from actual prod sleeves (sanity)
    prod_prodsleeves = blend(cpm_prod, bull_prod, ndx_prod, 0.6, 0.2, 0.2)
    cb_prodsleeves = blend(cpm_prod, bull_prod, None, 0.6, 0.4, None)

    # ---------- Benchmarks ----------
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
        def obj(w, C=cov.values):
            return float(np.dot(w, np.dot(C, w)))
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

    def bb1_eng(conv):
        # BB1 = simplest literature 60/40 = 0.6*B2(AAA+TIP) + 0.4*B3(HAA-S SPY)
        b2 = eng_bench(b2_wf, AAA + SAFE + ["TIP"], conv)
        b3 = eng_bench(b3_wf, ["SPY"] + SAFE + ["TIP"], conv)
        ix = b2.index.intersection(b3.index)
        return 0.6 * b2.reindex(ix).fillna(0) + 0.4 * b3.reindex(ix).fillna(0)

    bb4 = {c: bb4_eng(c) for c in CONVS}
    bb1 = {c: bb1_eng(c) for c in CONVS}
    sixty40 = {c: eng_bench(sixty40_wf, ["SPY", "IEF"], c) for c in CONVS}
    spy_bh = panel["SPY"].ffill().pct_change()
    qqq_bh = panel["QQQ"].ffill().pct_change()

    # ---------- Assemble output ----------
    out = {"meta": {
        "panel_start": str(panel.index[0].date()), "panel_end": str(panel.index[-1].date()),
        "n": len(panel), "clean": str(CLEAN.date()), "ext": str(EXT.date()), "end": str(END.date()),
        "corr_lookback": cpm_live.CORR_LOOKBACK_DAYS, "cost_bps_per_side": COST_BPS_PER_SIDE,
        "ndx_moc1_delta_nonzero_days_clean": ndx_moc1_delta_nonzero,
        "bull_fb": {c: bull_fb[c] for c in CONVS},
        "ndx_fb": {c: ndx_fb[c] for c in CONVS},
    }}
    series_map = {
        "CPM": cpm, "BULL": bull, "NDX": ndx, "PROD": prod, "CPM-BULL": cb,
        "BB4": bb4, "BB1": bb1, "60-40": sixty40,
    }
    invariant = {"SPY_buyhold": spy_bh, "QQQ_buyhold": qqq_bh}
    for wlabel, lo in (("clean", CLEAN), ("ext", EXT)):
        out[wlabel] = {}
        for name, sdict in series_map.items():
            out[wlabel][name] = {c: M(sdict[c], cash, lo, END) for c in CONVS}
        for name, s in invariant.items():
            out[wlabel][name] = M(s, cash, lo, END)
        # prod-sleeve reference (CC)
        out[wlabel]["PROD_prodsleeves_cc"] = M(prod_prodsleeves, cash, lo, END)
        out[wlabel]["CPM_prod_cc"] = M(cpm_prod, cash, lo, END)
        out[wlabel]["BULL_prod_cc"] = M(bull_prod, cash, lo, END)
        out[wlabel]["NDX_prod_cc"] = M(ndx_prod, cash, lo, END)

    outpath = ROOT / "research" / "cpm_t1moc_canonical_numbers.json"
    with open(outpath, "w") as f:
        json.dump(out, f, indent=2, default=lambda x: None if pd.isna(x) else round(float(x), 6))
    print(f"wrote {outpath}\n")

    # ---------- Pretty tables ----------
    def hdr():
        return (f"{'series':<26}{'conv':<7}{'Sharpe':>8}{'ExcSh':>8}{'CAGR':>9}{'Vol':>8}"
                f"{'MaxDD':>9}{'Calmar':>8}{'Martin':>8}")

    def line(name, conv, m):
        return (f"{name:<26}{conv:<7}{m['sharpe']:>8.4f}{m['excess_sharpe']:>8.4f}"
                f"{m['cagr']*100:>8.2f}%{m['vol']*100:>7.2f}%{m['max_drawdown']*100:>8.2f}%"
                f"{m['calmar']:>8.4f}{m['martin']:>8.4f}")

    for wlabel, lo in (("CLEAN 2008-05-30..2026-05-22", "clean"), ("EXT 1999-03-10..2026-05-22", "ext")):
        print("=" * 90)
        print(f"WINDOW: {wlabel}")
        print("=" * 90)
        print(hdr())
        print("-" * 90)
        for name in ("CPM", "BULL", "NDX", "PROD", "CPM-BULL", "BB4", "BB1", "60-40"):
            for c in CONVS:
                print(line(name, c, out[lo][name][c]))
            print("-" * 90)
        for name in ("SPY_buyhold", "QQQ_buyhold"):
            print(line(name, "inv", out[lo][name]))
        print()

    print("=== EXECUTION-LAG TABLE (CPM + PROD): Sharpe / Calmar / MaxDD ===")
    print(f"{'series':<8}{'window':<7}{'metric':<8}{'T+0 MOC':>10}{'T+1 MOO':>10}{'T+1 MOC':>10}")
    print("-" * 53)
    for name in ("CPM", "PROD"):
        for lo in ("clean", "ext"):
            for mk, lab in (("sharpe", "Sharpe"), ("calmar", "Calmar"), ("max_drawdown", "MaxDD")):
                v = [out[lo][name][c][mk] for c in CONVS]
                if mk == "max_drawdown":
                    print(f"{name:<8}{lo:<7}{lab:<8}{v[0]*100:>9.2f}%{v[1]*100:>9.2f}%{v[2]*100:>9.2f}%")
                else:
                    print(f"{name:<8}{lo:<7}{lab:<8}{v[0]:>10.4f}{v[1]:>10.4f}{v[2]:>10.4f}")
    print()
    print("COVERAGE / SANITY:")
    print(f"  NDX moc1 delta nonzero days (clean): {ndx_moc1_delta_nonzero} "
          f"(moc1 is close-only, no opens-cache fallback)")
    print(f"  BULL fallback (mooex needs opens; moc1 should be 0,0): "
          f"mooex={bull_fb['mooex']} moc1={bull_fb['moc1']}")
    print(f"  NDX  fallback: mooex={ndx_fb['mooex']} moc1={ndx_fb['moc1']}")
    print(f"  CPM prod CC vs engine moc (clean Sharpe): "
          f"prod={out['clean']['CPM_prod_cc']['sharpe']:.4f} eng_moc={out['clean']['CPM']['moc']['sharpe']:.4f}")
    print(f"  PROD prodsleeves CC vs blend(eng moc) (clean Sharpe): "
          f"prodsleeves={out['clean']['PROD_prodsleeves_cc']['sharpe']:.4f} blend_moc={out['clean']['PROD']['moc']['sharpe']:.4f}")


if __name__ == "__main__":
    main()
