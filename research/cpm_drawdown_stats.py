"""Throwaway research (SCOPED, read-only; writes research/ only): give the memo's
NEW lead claim -- "drawdown / tail-control is CPM's significant edge" -- the same
statistical treatment the Sharpe got, and test its independence from the
canary-GFC-insurance leg.

Reuses research/cpm_benchmarks_proper.py for the benchmark series (CPM /
Canonical_AAA / 60-40 / Naive_12m / BuyHold_InvVol) and the same mooex T+1 MOO
exact, 10 bps/side, monthly, clean-18y harness. Adds:

  1. PAIRED block-bootstrap 95% difference-CIs (B=2000, block=21) for
     CPM-minus-each-benchmark on CALMAR, MARTIN, and MaxDD (not just Sharpe).
  2. GFC-INDEPENDENCE: decompose drawdown advantage by crisis episode
     (GFC 2008-09, COVID 2020, 2022, other), and recompute MaxDD/Calmar
     EXCLUDING the GFC window.
  3. CANARY INDEPENDENCE: build CPM-no-canary (ranker/screen/invvol only, canary
     gate disabled) and ask whether the drawdown edge survives without the
     canary firing in GFC.

ANCHOR: CPM clean Sharpe 1.1910 / MaxDD -12.67% / Calmar 1.0615 / Martin 3.9646.
"""
import sys, math, json
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

import cpm_benchmarks_proper as CB
import exec_lag_moo_validation_2026_05_30 as H
from cpm_live import (
    load_panel, perf_metrics, sig_13612U, best_safe, inv_vol_weights,
    faber_sma_xs, RISKY_UNIVERSE, SAFE_POOL, COST_BPS_PER_SIDE,
    CORR_LOOKBACK_DAYS, TOP_K_CANDIDATES,
)

CONV = "mooex"
SEED = 12345
B = 2000
BLOCK = 21

# Crisis episode windows (inclusive). GFC window covers the post-clean-start crash.
EPISODES = {
    "GFC":   ("2008-05-30", "2009-06-30"),
    "COVID": ("2020-02-01", "2020-04-30"),
    "Y2022": ("2022-01-01", "2022-12-31"),
}


# --------------------------------------------------------------------------
# CPM-no-canary weight function: identical ranker/screen/invvol/partial-safe,
# but the HYG|TIP canary gate is DISABLED (always proceed to the ranker).
# --------------------------------------------------------------------------
def compute_weights_no_canary(close_panel, sig_d):
    universe = RISKY_UNIVERSE
    safe_pool = SAFE_POOL
    monthly = close_panel.loc[:sig_d].resample("ME").last()
    safe = best_safe(monthly, sig_d, safe_pool)

    # NO canary gate here (this is the only difference vs compute_target_weights).
    faber = faber_sma_xs(monthly)
    avail = [t for t in universe
             if t in faber.index and pd.notna(faber[t])
             and pd.notna(close_panel.loc[sig_d].get(t, np.nan) if sig_d in close_panel.index else np.nan)]
    if not avail:
        return {safe: 1.0}

    daily_rets = close_panel[avail].ffill().pct_change()
    scores = {}
    for t in avail:
        v = daily_rets[t].loc[:sig_d].tail(252).std() * np.sqrt(252)
        if pd.isna(v) or v < 1e-9:
            v = 1.0
        scores[t] = float(faber[t]) / v
    ranked = pd.Series(scores).sort_values(ascending=False)
    top_k = max(2, min(TOP_K_CANDIDATES, len(ranked)))
    top = ranked.iloc[:top_k]
    positive = top[top.index.map(lambda t: faber.get(t, -np.inf) > 0)]
    if len(positive) == 0:
        return {safe: 1.0}

    picks = list(positive.index)
    n_picks = len(picks)
    risky_fraction = min(n_picks, 4) / 4.0
    safe_fraction = 1.0 - risky_fraction
    csub = close_panel.loc[:sig_d]
    risky_w = inv_vol_weights(csub, picks, CORR_LOOKBACK_DAYS)
    out = {t: w * risky_fraction for t, w in risky_w.items()}
    if safe_fraction > 0:
        out[safe] = out.get(safe, 0.0) + safe_fraction
    return out


def cpm_no_canary_sleeve(panel, intraday, overnight, start, end):
    cols = sorted(set(RISKY_UNIVERSE + SAFE_POOL + ["HYG", "TIP", "SHV"]) & set(panel.columns))
    close = panel[cols]
    daily_ret = close.ffill().pct_change()
    wf = lambda sd: compute_weights_no_canary(close, sd)
    s, fb = H._segment_returns_conv(close, daily_ret, wf, start, end, CONV,
                                    COST_BPS_PER_SIDE, intraday, overnight)
    return s


# --------------------------------------------------------------------------
# metric helpers
# --------------------------------------------------------------------------
def metric_from_array(r, ann=252):
    """Path-dependent metrics from a daily-return array (bootstrap-safe)."""
    r = np.asarray(r, dtype=float)
    n = len(r)
    if n < 2:
        return dict(cagr=np.nan, maxdd=np.nan, ulcer=np.nan, calmar=np.nan,
                    martin=np.nan, sharpe=np.nan)
    eq = np.cumprod(1.0 + r)
    cagr = eq[-1] ** (ann / n) - 1.0
    rm = np.maximum.accumulate(eq)
    dd = eq / rm - 1.0
    mdd = float(dd.min())
    ulcer = float(np.sqrt(np.mean(dd ** 2)))
    vol = r.std(ddof=0) * np.sqrt(ann)
    sharpe = (r.mean() * ann) / vol if vol > 0 else np.nan
    calmar = cagr / abs(mdd) if mdd != 0 else np.nan
    martin = cagr / ulcer if ulcer > 0 else np.nan
    return dict(cagr=cagr, maxdd=mdd, ulcer=ulcer, calmar=calmar,
                martin=martin, sharpe=sharpe)


def paired_block_bootstrap_metrics(cpm, bench, metrics=("calmar", "martin", "maxdd"),
                                   block=BLOCK, B=B, seed=SEED):
    """Paired block bootstrap of CPM-minus-bench for path-dependent metrics.
    Same resampled block indices applied to BOTH series each draw (paired)."""
    common = cpm.index.intersection(bench.index)
    a = cpm.reindex(common).fillna(0.0).values
    b = bench.reindex(common).fillna(0.0).values
    n = len(a)
    pa, pb = metric_from_array(a), metric_from_array(b)
    points = {m: pa[m] - pb[m] for m in metrics}
    if n < block * 3:
        return {m: dict(point=points[m], lo=np.nan, hi=np.nan,
                        includes_zero=True, n=n, note="insufficient") for m in metrics}
    rng = np.random.default_rng(seed)
    n_blocks = int(math.ceil(n / block))
    starts_pool = np.arange(0, n - block + 1)
    draws = {m: np.empty(B) for m in metrics}
    for i in range(B):
        starts = rng.choice(starts_pool, size=n_blocks, replace=True)
        idx = np.concatenate([np.arange(s, s + block) for s in starts])[:n]
        ma, mb = metric_from_array(a[idx]), metric_from_array(b[idx])
        for m in metrics:
            draws[m][i] = ma[m] - mb[m]
    res = {}
    for m in metrics:
        lo, hi = np.nanpercentile(draws[m], [2.5, 97.5])
        # For maxdd: positive difference means CPM has shallower (less negative) DD = better.
        res[m] = dict(point=float(points[m]), lo=float(lo), hi=float(hi),
                      includes_zero=bool(lo <= 0.0 <= hi), B=B, block=block, n=n)
    return res


def worst_dd_in_window(series, lo, hi):
    """Worst peak-to-trough drawdown of `series` (daily ret) within [lo, hi],
    with equity peak carried from the full clean path up to lo (so the episode
    drawdown is measured from the running high entering the window)."""
    eq = (1.0 + series).cumprod()
    rm = eq.cummax()
    dd = eq / rm - 1.0
    w = dd.loc[lo:hi]
    return float(w.min()) if len(w) else np.nan


def excise_window(series, lo, hi):
    """Return series with [lo,hi] removed (stitched), for ex-GFC recompute."""
    mask = ~((series.index >= lo) & (series.index <= hi))
    return series[mask]


def main():
    end = pd.Timestamp("2026-05-22")
    ext_start = pd.Timestamp("1999-03-10")
    clean_start = pd.Timestamp("2008-05-30")

    panel, intraday, overnight, end = CB.build_data(ext_start, end)
    cash = panel["SHV"].ffill().pct_change().dropna()
    print(f"Panel {panel.index[0].date()} -> {panel.index[-1].date()} ({len(panel)} rows)")
    print(f"Convention={CONV} cost={COST_BPS_PER_SIDE}bps/side B={B} block={BLOCK}\n")

    # --- build all series (reuse CB builders) ---
    cpm, _ = H.cpm_sleeve_conv(panel, intraday, overnight, ext_start, end, CONV)
    cpm_nc = cpm_no_canary_sleeve(panel, intraday, overnight, ext_start, end)

    aaa_cols = [t for t in CB.AAA_UNIVERSE if t in panel.columns] + ["SHV", "IEF"]
    aaa_close = panel[sorted(set(aaa_cols))]
    aaa_daily = aaa_close.ffill().pct_change()
    rwx_fv = panel["RWX"].first_valid_index()
    aaa_ext_start = max(ext_start, (rwx_fv + pd.DateOffset(months=13)) if rwx_fv is not None else ext_start)
    aaa, _ = CB.run_wf(aaa_close, aaa_daily, intraday, overnight, aaa_ext_start, end,
                       CB.make_canonical_aaa_wf(aaa_close, aaa_daily))

    bm_cols = sorted(set(RISKY_UNIVERSE + ["SPY", "IEF", "SHV"]) & set(panel.columns))
    bm_close = panel[bm_cols]
    bm_daily = bm_close.ffill().pct_change()
    sixty, _ = CB.run_wf(bm_close, bm_daily, intraday, overnight, ext_start, end, CB.make_6040_wf(bm_close))
    naive, _ = CB.run_wf(bm_close, bm_daily, intraday, overnight, ext_start, end, CB.make_naive12_wf(bm_close))
    bhiv, _ = CB.run_wf(bm_close, bm_daily, intraday, overnight, ext_start, end, CB.make_buyhold_invvol_wf(bm_close))

    def clip(s):
        return s.loc[(s.index >= clean_start) & (s.index <= end)]

    series = {
        "CPM": clip(cpm),
        "CPM_no_canary": clip(cpm_nc),
        "Canonical_AAA": clip(aaa),
        "60/40": clip(sixty),
        "Naive_12m": clip(naive),
        "BuyHold_InvVol": clip(bhiv),
    }
    benches = ["Canonical_AAA", "60/40", "Naive_12m", "BuyHold_InvVol"]

    out = {"meta": dict(convention=CONV, cost_bps=COST_BPS_PER_SIDE, B=B, block=BLOCK,
                        clean_start=str(clean_start.date()), end=str(end.date()),
                        episodes=EPISODES)}

    # --- full metrics ---
    out["metrics_clean"] = {}
    for nm, s in series.items():
        m = perf_metrics(s, cash)
        out["metrics_clean"][nm] = dict(sharpe=m["sharpe"], cagr=m["cagr"], vol=m["vol"],
                                        maxdd=m["max_drawdown"], calmar=m["calmar"],
                                        martin=m["martin"], ulcer=m["ulcer"])

    print("=== ANCHOR check ===")
    a = out["metrics_clean"]["CPM"]
    print(f"  CPM Sharpe={a['sharpe']:.4f} MaxDD={a['maxdd']*100:.2f}% "
          f"Calmar={a['calmar']:.4f} Martin={a['martin']:.4f}")
    print("  (expect 1.1910 / -12.67% / 1.0615 / 3.9646)\n")

    # ---------------------------------------------------------------
    # 1. PAIRED difference-CIs on Calmar / Martin / MaxDD
    # ---------------------------------------------------------------
    out["diff_ci"] = {}
    cpm_c = series["CPM"]
    for nm in benches:
        out["diff_ci"][nm] = paired_block_bootstrap_metrics(cpm_c, series[nm])

    # ---------------------------------------------------------------
    # 2. GFC decomposition
    # ---------------------------------------------------------------
    out["episode_dd"] = {}  # worst dd per episode per series
    for nm, s in series.items():
        ep = {}
        for ename, (lo, hi) in EPISODES.items():
            ep[ename] = worst_dd_in_window(s, lo, hi)
        # locate where overall MaxDD trough falls
        eq = (1.0 + s).cumprod()
        dd = eq / eq.cummax() - 1.0
        trough = dd.idxmin()
        ep["overall_maxdd"] = float(dd.min())
        ep["trough_date"] = str(trough.date())
        out["episode_dd"][nm] = ep

    # ex-GFC recompute (excise GFC window, stitch remainder)
    glo, ghi = EPISODES["GFC"]
    out["metrics_ex_gfc"] = {}
    for nm, s in series.items():
        sx = excise_window(s, glo, ghi)
        out["metrics_ex_gfc"][nm] = metric_from_array(sx.values)

    # MaxDD gap decomposition: overall gap vs ex-GFC gap (CPM minus bench).
    out["dd_gap_decomp"] = {}
    for nm in benches:
        full_gap = out["metrics_clean"]["CPM"]["maxdd"] - out["metrics_clean"][nm]["maxdd"]
        exg_gap = out["metrics_ex_gfc"]["CPM"]["maxdd"] - out["metrics_ex_gfc"][nm]["maxdd"]
        out["dd_gap_decomp"][nm] = dict(
            full_maxdd_gap=float(full_gap),
            exgfc_maxdd_gap=float(exg_gap),
            # fraction of the advantage that disappears when GFC is removed
            gfc_attributable_frac=float(1.0 - (exg_gap / full_gap)) if full_gap != 0 else np.nan,
        )

    # ---------------------------------------------------------------
    # 3. Canary independence: does CPM-no-canary still dominate on DD?
    # ---------------------------------------------------------------
    out["canary_independence"] = {
        "cpm_maxdd": out["metrics_clean"]["CPM"]["maxdd"],
        "cpm_no_canary_maxdd": out["metrics_clean"]["CPM_no_canary"]["maxdd"],
        "cpm_calmar": out["metrics_clean"]["CPM"]["calmar"],
        "cpm_no_canary_calmar": out["metrics_clean"]["CPM_no_canary"]["calmar"],
        "canary_dd_contribution": float(out["metrics_clean"]["CPM"]["maxdd"]
                                        - out["metrics_clean"]["CPM_no_canary"]["maxdd"]),
        "vs_benchmarks": {},
    }
    # paired CI: CPM-no-canary vs each benchmark on maxdd/calmar/martin
    out["diff_ci_no_canary"] = {}
    for nm in benches:
        out["diff_ci_no_canary"][nm] = paired_block_bootstrap_metrics(
            series["CPM_no_canary"], series[nm])
        still_better_dd = out["metrics_clean"]["CPM_no_canary"]["maxdd"] > out["metrics_clean"][nm]["maxdd"]
        out["canary_independence"]["vs_benchmarks"][nm] = dict(
            nc_maxdd=out["metrics_clean"]["CPM_no_canary"]["maxdd"],
            bench_maxdd=out["metrics_clean"][nm]["maxdd"],
            nc_still_shallower=bool(still_better_dd),
        )

    # canary's GFC-localized contribution
    out["canary_independence"]["gfc_episode_dd"] = {
        "cpm": out["episode_dd"]["CPM"]["GFC"],
        "cpm_no_canary": out["episode_dd"]["CPM_no_canary"]["GFC"],
    }

    Path(__file__).with_suffix(".json").write_text(json.dumps(out, indent=2, default=float))

    # ===================== console =====================
    order = ["CPM", "CPM_no_canary", "Canonical_AAA", "60/40", "Naive_12m", "BuyHold_InvVol"]
    print("=" * 78)
    print("CLEAN 18y metrics")
    print("=" * 78)
    print(f"{'series':<16}{'Sharpe':>8}{'CAGR':>8}{'MaxDD':>9}{'Calmar':>8}{'Martin':>8}{'Ulcer':>8}")
    for nm in order:
        m = out["metrics_clean"][nm]
        print(f"{nm:<16}{m['sharpe']:>8.4f}{m['cagr']*100:>7.2f}%{m['maxdd']*100:>8.2f}%"
              f"{m['calmar']:>8.4f}{m['martin']:>8.4f}{m['ulcer']*100:>7.2f}%")

    def ci_table(dci, title):
        print("\n" + "=" * 78)
        print(title)
        print("=" * 78)
        for met in ("maxdd", "calmar", "martin"):
            print(f"-- {met.upper()} difference (positive = CPM better) --")
            print(f"{'vs benchmark':<18}{'point':>10}{'CI_lo':>10}{'CI_hi':>10}{'incl 0?':>9}{'SIG?':>6}")
            for nm in benches:
                d = dci[nm][met]
                sig = "NO" if d["includes_zero"] else "YES"
                print(f"{nm:<18}{d['point']:>10.4f}{d['lo']:>10.4f}{d['hi']:>10.4f}"
                      f"{str(d['includes_zero']):>9}{sig:>6}")
            print()

    ci_table(out["diff_ci"], "1. PAIRED block-bootstrap 95% CI: CPM - benchmark (B=2000, block=21)")

    print("=" * 78)
    print("2. GFC DECOMPOSITION -- worst drawdown per episode (running-high based)")
    print("=" * 78)
    print(f"{'series':<16}{'GFC':>9}{'COVID':>9}{'2022':>9}{'overallDD':>11}{'trough':>13}")
    for nm in order:
        e = out["episode_dd"][nm]
        print(f"{nm:<16}{e['GFC']*100:>8.2f}%{e['COVID']*100:>8.2f}%{e['Y2022']*100:>8.2f}%"
              f"{e['overall_maxdd']*100:>10.2f}%{e['trough_date']:>13}")

    print("\n-- MaxDD/Calmar EXCLUDING GFC window (excised + stitched) --")
    print(f"{'series':<16}{'MaxDD_exGFC':>12}{'Calmar_exGFC':>13}{'Martin_exGFC':>13}")
    for nm in order:
        m = out["metrics_ex_gfc"][nm]
        print(f"{nm:<16}{m['maxdd']*100:>11.2f}%{m['calmar']:>13.4f}{m['martin']:>13.4f}")

    print("\n-- MaxDD gap decomposition (CPM - bench): full vs ex-GFC --")
    print(f"{'vs benchmark':<18}{'full_gap':>10}{'exGFC_gap':>11}{'GFC_attrib%':>12}")
    for nm in benches:
        g = out["dd_gap_decomp"][nm]
        print(f"{nm:<18}{g['full_maxdd_gap']*100:>9.2f}%{g['exgfc_maxdd_gap']*100:>10.2f}%"
              f"{g['gfc_attributable_frac']*100:>11.1f}%")

    print("\n" + "=" * 78)
    print("3. CANARY INDEPENDENCE")
    print("=" * 78)
    ci = out["canary_independence"]
    print(f"CPM           MaxDD={ci['cpm_maxdd']*100:.2f}%  Calmar={ci['cpm_calmar']:.4f}")
    print(f"CPM_no_canary MaxDD={ci['cpm_no_canary_maxdd']*100:.2f}%  Calmar={ci['cpm_no_canary_calmar']:.4f}")
    print(f"Canary DD contribution (CPM - no_canary) = {ci['canary_dd_contribution']*100:.2f}% "
          f"(positive = canary makes DD shallower)")
    print(f"GFC episode DD:  CPM={ci['gfc_episode_dd']['cpm']*100:.2f}%  "
          f"no_canary={ci['gfc_episode_dd']['cpm_no_canary']*100:.2f}%")
    print("\nDoes CPM-no-canary still beat each benchmark on MaxDD?")
    for nm in benches:
        v = ci["vs_benchmarks"][nm]
        print(f"  vs {nm:<16} nc={v['nc_maxdd']*100:>7.2f}%  bench={v['bench_maxdd']*100:>7.2f}%  "
              f"shallower={v['nc_still_shallower']}")

    ci_table(out["diff_ci_no_canary"],
             "3b. PAIRED CI: CPM-NO-CANARY - benchmark (drawdown edge w/o canary)")

    print("DONE -> json written:", Path(__file__).with_suffix(".json").name)


if __name__ == "__main__":
    main()
