"""Throwaway research: is the CPM ranker's VOL-ADJUSTMENT redundant once
INVERSE-VOL weighting handles vol downstream?

Hypothesis: the production ranker is vol-adjusted Faber  m_faber / rv_252d  ->
penalizes high-vol assets in RANKING. Inverse-vol weighting (w prop 1/sigma)
ALSO penalizes high-vol in WEIGHTING. Under INVVOL weighting the vol term may be
double-counted, so plain-momentum ranking should match/beat vol-Faber.

Grid = RANKER x WEIGHTING.

Rankers (score used for top-half cut; positive-trend screen always m_faber>0
EXCEPT where the ranker has no faber, then we screen on the ranker score > 0):
  volfaber : m_faber / rv_252d        (production)   -- positive screen = faber>0
  faber    : m_faber alone            (price/SMA10-1)-- positive screen = faber>0
  mom13612 : 13612U avg(1/3/6/12m)                   -- positive screen = score>0
  mom12    : plain 12m total return                  -- positive screen = score>0

  NOTE: faber/volfaber share the SAME positive screen (faber>0) and the SAME
  candidate pool, differing only in the ORDER (and thus which survive the
  top-half K cut when >K positives). mom13612/mom12 use their own score sign.

Weightings (selection = min-var m-subset, identical to inverse_vol_weighting):
  EW2  : 2 lowest-variance pair, 50/50          (vol NOT used in weighting)
  IV2  : 2 lowest-variance pair, inverse-vol
  IV3  : 3 lowest-variance triplet, inverse-vol

Execution: T+1 MOO exact (mooex), 10 bps/side. Windows: CLEAN 18y 2008-05-30,
EXT 27y 1999-03-10. K top-half = 4. cov lookback 504d. U=C on (prod universe +
HYG-OR-TIP canary). Reuses inverse_vol_weighting helpers byte-identical.

Anchor: volfaber x EW2 must reproduce production CPM-solo  CLEAN 1.2424.
        volfaber x IV2/IV3 must reproduce inverse_vol_weighting findings.

No production files touched.
"""
import sys, math, json
from itertools import combinations
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from cpm_live import (
    load_panel, perf_metrics, sig_13612U, best_safe, faber_sma_xs,
    COST_BPS_PER_SIDE, CORR_LOOKBACK_DAYS,
)
import exec_lag_moo_validation_2026_05_30 as H
from sleeve_vs_benchmark_2026_05_30 import stitch_bil, stitch_agg
# reuse byte-identical helpers from the inverse-vol harness
from inverse_vol_weighting import (
    _cov_window, min_var_subset, inv_vol_weights, CPM_PROD_UNIVERSE, CPM_SAFE,
    sig_dates, l1, basket, met,
)

CONV = "mooex"


def mom12(p: pd.Series) -> float:
    """Plain 12-month total return momentum."""
    p = p.dropna()
    if len(p) < 13:
        return np.nan
    return float(p.iloc[-1] / p.iloc[-13] - 1.0)


def rank_candidates(close, monthly, sig_d, ranker, top_half):
    """Return (positive, ranked_index) for the chosen ranker.
    `positive` = trend-qualified survivors after top-half K cut, used for
    weighting. Mirrors factorial/inverse-vol candidate construction."""
    universe = CPM_PROD_UNIVERSE
    present = [t for t in universe if t in monthly.columns]
    faber = faber_sma_xs(monthly)
    avail = [t for t in present if t in faber.index and pd.notna(faber[t])
             and (sig_d in close.index and pd.notna(close.loc[sig_d].get(t, np.nan)))]
    if not avail:
        return [], faber

    if ranker == "volfaber":
        dr = close[avail].ffill().pct_change()
        score = {}
        for t in avail:
            v = dr[t].loc[:sig_d].tail(252).std() * np.sqrt(252)
            if pd.isna(v) or v < 1e-9:
                v = 1.0
            score[t] = float(faber[t]) / v
        ranked = pd.Series(score).sort_values(ascending=False)
        top_k = max(2, min(top_half, len(ranked)))
        top = ranked.iloc[:top_k]
        positive = [t for t in top.index if faber.get(t, -np.inf) > 0]
    elif ranker == "faber":
        score = {t: float(faber[t]) for t in avail}
        ranked = pd.Series(score).sort_values(ascending=False)
        top_k = max(2, min(top_half, len(ranked)))
        top = ranked.iloc[:top_k]
        positive = [t for t in top.index if faber.get(t, -np.inf) > 0]
    elif ranker == "mom13612":
        score = {t: sig_13612U(monthly[t]) for t in avail}
        score = {t: s for t, s in score.items() if pd.notna(s)}
        ranked = pd.Series(score).sort_values(ascending=False)
        top_k = max(2, min(top_half, len(ranked)))
        top = ranked.iloc[:top_k]
        positive = [t for t in top.index if score.get(t, -np.inf) > 0]
    elif ranker == "mom12":
        score = {t: mom12(monthly[t]) for t in avail}
        score = {t: s for t, s in score.items() if pd.notna(s)}
        ranked = pd.Series(score).sort_values(ascending=False)
        top_k = max(2, min(top_half, len(ranked)))
        top = ranked.iloc[:top_k]
        positive = [t for t in top.index if score.get(t, -np.inf) > 0]
    else:
        raise ValueError(ranker)
    return positive, faber


def cpm_wf(close, daily, sig_d, ranker, scheme, lookback):
    """Parametrized CPM weight fn: ranker x weighting. U=C on (prod universe,
    HYG-OR-TIP any-positive canary). Fallback identical to inverse_vol harness."""
    monthly = close.loc[:sig_d].resample("ME").last()
    safe = best_safe(monthly, sig_d, CPM_SAFE)

    cscores = [sig_13612U(monthly[a]) for a in ["HYG", "TIP"] if a in monthly.columns]
    cscores = [s for s in cscores if pd.notna(s)]
    if not cscores:
        return {safe: 1.0}
    if sum(1 for s in cscores if s > 0) == 0:
        return {safe: 1.0}

    top_half = max(2, math.ceil(len(CPM_PROD_UNIVERSE) / 2))
    positive, _ = rank_candidates(close, monthly, sig_d, ranker, top_half)

    if len(positive) == 0:
        return {safe: 1.0}
    if len(positive) == 1:
        return {positive[0]: 0.5, safe: 0.5}

    csub = close.loc[:sig_d]
    if scheme == "EW2":
        m, n_pos = 2, len(positive)
        if n_pos < m:
            return {t: 1.0 / n_pos for t in positive}
        pick = min_var_subset(csub, positive, lookback, m)
        if pick is None:
            return {t: 1.0 / n_pos for t in positive}
        return {t: 1.0 / m for t in pick}

    m = {"IV2": 2, "IV3": 3}[scheme]
    n_pos = len(positive)
    if n_pos < m:
        return inv_vol_weights(csub, positive, lookback)
    pick = min_var_subset(csub, positive, lookback, m)
    if pick is None:
        return inv_vol_weights(csub, positive, lookback)
    return inv_vol_weights(csub, pick, lookback)


def returns_for(close, daily, intraday, overnight, start, end, ranker, scheme, cost_bps):
    wf = lambda sd: cpm_wf(close, daily, sd, ranker, scheme, CORR_LOOKBACK_DAYS)
    s, _ = H._segment_returns_conv(close, daily, wf, start, end, CONV,
                                   cost_bps, intraday, overnight)
    return s


RANKERS = [("volfaber", "vol-Faber (prod)"), ("faber", "plain Faber"),
           ("mom13612", "13612U"), ("mom12", "plain 12m mom")]
WEIGHTS = [("EW2", "EW-2"), ("IV2", "INVVOL-2"), ("IV3", "INVVOL-3")]


def selected_basket(close, daily, sig_d, ranker, scheme, lookback):
    """Risk-on basket selected (tickers, ignoring safe-only fallbacks)."""
    w = cpm_wf(close, daily, sig_d, ranker, scheme, lookback)
    return basket(w) - set(CPM_SAFE)


def main():
    end = pd.Timestamp("2026-05-22")
    ext_start = pd.Timestamp("1999-03-10")
    clean_start = pd.Timestamp("2008-05-30")

    panel = load_panel(start=ext_start, end=end)
    end = min(end, panel.index[-1])
    cash = panel["SHV"].ffill().pct_change().dropna()
    panel["BIL"] = stitch_bil(panel)
    panel["AGG"] = stitch_agg(panel)

    open_df, close_yf = H.load_open_close()
    intraday = (close_yf / open_df - 1.0).reindex(panel.index)
    overnight = (open_df / close_yf.shift(1) - 1.0).reindex(panel.index)

    cpm_cols = sorted(set(CPM_PROD_UNIVERSE + CPM_SAFE + ["HYG", "TIP"]) & set(panel.columns))
    close = panel[cpm_cols]
    daily = close.ffill().pct_change()

    windows = {"CLEAN": (clean_start, end), "EXT": (ext_start, end)}
    cost_grid = [0, 10, 25]

    out = {"meta": {"conv": CONV, "lookback": CORR_LOOKBACK_DAYS,
                    "cost_bps_prod": COST_BPS_PER_SIDE, "K_top_half": top_half_const(),
                    "universe": "U=C on (prod 8-asset, HYG-OR-TIP canary)",
                    "clean_start": str(clean_start.date()), "ext_start": str(ext_start.date()),
                    "end": str(end.date())},
           "windows": {}, "overlap": {}}

    print("Computing return series (ext, ranker x weighting x cost)...")
    ret_cache = {}
    for ranker, _ in RANKERS:
        for scheme, _ in WEIGHTS:
            for cb in cost_grid:
                ret_cache[(ranker, scheme, cb)] = returns_for(
                    close, daily, intraday, overnight, ext_start, end, ranker, scheme, cb)
        print(f"  ranker {ranker} done")

    for wn, (ws_, we_) in windows.items():
        wd = {"cells": {}}
        for ranker, rlab in RANKERS:
            for scheme, slab in WEIGHTS:
                perf = {}
                for cb in cost_grid:
                    s = ret_cache[(ranker, scheme, cb)]
                    sw = s.loc[(s.index >= ws_) & (s.index <= we_)]
                    perf[cb] = met(sw, cash)
                wd["cells"][f"{ranker}|{scheme}"] = {
                    "ranker": rlab, "weighting": slab, "perf": perf}
        out["windows"][wn] = wd

    # ===== SELECTION OVERLAP: vol-Faber vs plain-momentum rankers =====
    print("Computing selection overlap (vol-Faber vs others)...")
    for wn, (ws_, we_) in windows.items():
        sigs = sig_dates(close, ws_, we_)
        ov = {}
        for scheme, slab in WEIGHTS:
            base = [selected_basket(close, daily, sd, "volfaber", scheme, CORR_LOOKBACK_DAYS)
                    for sd in sigs]
            for ranker, rlab in RANKERS:
                if ranker == "volfaber":
                    continue
                alt = [selected_basket(close, daily, sd, ranker, scheme, CORR_LOOKBACK_DAYS)
                       for sd in sigs]
                # consider only months where BOTH are risk-on (non-empty basket)
                both_on = [(b, a) for b, a in zip(base, alt) if b and a]
                n_both = len(both_on)
                identical = sum(1 for b, a in both_on if b == a)
                jac = [len(b & a) / len(b | a) for b, a in both_on]
                # risk-on agreement (both risk-on vs disagree)
                ron_b = sum(1 for b in base if b)
                ron_a = sum(1 for a in alt if a)
                ron_disagree = sum(1 for b, a in zip(base, alt) if bool(b) != bool(a))
                ov[f"{ranker}|{scheme}"] = {
                    "n_sigs": len(sigs), "n_both_riskon": n_both,
                    "frac_identical_basket": identical / n_both if n_both else float("nan"),
                    "mean_jaccard": float(np.mean(jac)) if jac else float("nan"),
                    "volfaber_riskon_months": ron_b, "alt_riskon_months": ron_a,
                    "riskon_state_disagree": ron_disagree,
                }
        out["overlap"][wn] = ov

    Path(__file__).with_suffix(".json").write_text(json.dumps(out, indent=2, default=float))

    # ===== console =====
    print("\n=== VERIFY anchors (CLEAN, 10 bps) ===")
    a_ew = out["windows"]["CLEAN"]["cells"]["volfaber|EW2"]["perf"][10]
    a_iv2 = out["windows"]["CLEAN"]["cells"]["volfaber|IV2"]["perf"][10]
    a_iv3 = out["windows"]["CLEAN"]["cells"]["volfaber|IV3"]["perf"][10]
    print(f"  volfaber x EW2 : sharpe={a_ew['sharpe']:.4f} calmar={a_ew['calmar']:.4f} "
          f"maxdd={a_ew['maxdd']*100:.2f}%  (expect 1.2424/0.8704/-16.35%)")
    print(f"  volfaber x IV2 : sharpe={a_iv2['sharpe']:.4f} calmar={a_iv2['calmar']:.4f} "
          f"maxdd={a_iv2['maxdd']*100:.2f}%")
    print(f"  volfaber x IV3 : sharpe={a_iv3['sharpe']:.4f} calmar={a_iv3['calmar']:.4f} "
          f"maxdd={a_iv3['maxdd']*100:.2f}%")

    for wn in ("CLEAN", "EXT"):
        print(f"\n=== GRID [{wn}] net 10 bps ===")
        print(f"  {'ranker':<18}{'weighting':<11}{'Sharpe':>8}{'CAGR':>8}{'MaxDD':>9}{'Calmar':>8}")
        for ranker, rlab in RANKERS:
            for scheme, slab in WEIGHTS:
                p = out["windows"][wn]["cells"][f"{ranker}|{scheme}"]["perf"][10]
                print(f"  {rlab:<18}{slab:<11}{p['sharpe']:>8.4f}{p['cagr']*100:>7.2f}%"
                      f"{p['maxdd']*100:>8.2f}%{p['calmar']:>8.4f}")

    # redundancy: vol-Faber minus plain (faber) under each weighting
    print("\n=== REDUNDANCY: vol-Faber MINUS plain-Faber (Sharpe), net 10bps ===")
    for wn in ("CLEAN", "EXT"):
        line = f"  [{wn}] "
        for scheme, slab in WEIGHTS:
            vf = out["windows"][wn]["cells"][f"volfaber|{scheme}"]["perf"][10]["sharpe"]
            pf = out["windows"][wn]["cells"][f"faber|{scheme}"]["perf"][10]["sharpe"]
            line += f"{slab}: {vf-pf:+.4f}   "
        print(line)

    print("\nDONE -> json written")
    return out


def top_half_const():
    return max(2, math.ceil(len(CPM_PROD_UNIVERSE) / 2))


if __name__ == "__main__":
    main()
