"""Throwaway research: VALIDATION GAUNTLET for inverse-vol weighting schemes
(INVVOL-2, INVVOL-3) vs the production EW 50/50 min-var PAIR (EW-2) on the
DRAWDOWN objective. Read-only re: production; no production files touched.

Question: is the inverse-vol MaxDD/Calmar advantage over EW-2 a genuine,
statistically-robust AND persistent upgrade, or an in-sample / episode-driven
artifact (directional-but-within-noise like continuous-vs-pair was)?

Schemes (CPM sleeve, U=R=C=1, cov 504d, mooex T+1 MOO exact, K=4 top-half):
  EW2  = production 50/50 min-var pair  (clean 1.2424/-16.35%/0.8704)
  IV2  = INVVOL-2 (2 lowest-var, w prop 1/sigma) (clean 1.2630/-13.14%/1.0945)
  IV3  = INVVOL-3 (3 lowest-var, inverse-vol)     (clean 1.2453/-13.19%/1.0824)
  CONT = continuous min-var (reference)           (clean 1.2935/-15.15%/0.9618)

PART 1 -- PAIRED stationary block bootstrap (B=2000, block=21, seed=42). The
SAME resampled block index is applied to BOTH series each iteration (variants of
the same selection -> highly correlated -> paired mandatory). Naive independent
bootstrap reported only as a contrast. Pairs: {IV2 vs EW2}, {IV3 vs EW2},
{IV2 vs CONT}, {IV3 vs CONT}. Windows: CLEAN 18y, EXT 27y. Metrics: Sharpe,
MaxDD (less-negative=better), Calmar. Reports P(challenger beats baseline),
diff mean + 95% CI, CI-excludes-zero.

PART 2 -- ROLLING / SUB-PERIOD persistence. Rolling 12m (252d) and 36m (756d)
Calmar & MaxDD diffs (IV2-EW2, IV3-EW2), monthly step. Fraction of windows the
challenger wins. Per-regime MaxDD (dot-com, GFC, COVID, 2022).

Verify: all four scheme anchors reproduce before bootstrapping.
"""
import sys, json
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

from cpm_live import load_panel, perf_metrics, CORR_LOOKBACK_DAYS, COST_BPS_PER_SIDE
import exec_lag_moo_validation_2026_05_30 as H
from sleeve_vs_benchmark_2026_05_30 import stitch_bil, stitch_agg
import inverse_vol_weighting as IVW

B = 2000
BLOCK = 21
SEED = 42
COST = 10

CLEAN_START = pd.Timestamp("2008-05-30")
EXT_START = pd.Timestamp("1999-03-10")

# challenger vs baseline pairs; diff = challenger - baseline (>0 => challenger wins)
PAIRS = [
    ("IV2", "EW2", "INVVOL-2 vs EW-2"),
    ("IV3", "EW2", "INVVOL-3 vs EW-2"),
    ("IV2", "CONT", "INVVOL-2 vs continuous"),
    ("IV3", "CONT", "INVVOL-3 vs continuous"),
]

REGIMES = {
    "dot-com (2000-2002)": ("2000-03-01", "2002-12-31"),
    "GFC (2007-2009)":     ("2007-10-01", "2009-06-30"),
    "COVID (2020)":        ("2020-02-01", "2020-06-30"),
    "2022 bear":           ("2022-01-01", "2022-12-31"),
}


def metrics_from_array(r, n_years):
    vol = r.std(ddof=0) * np.sqrt(252)
    sharpe = (r.mean() * 252) / vol if vol > 0 else np.nan
    eq = np.cumprod(1.0 + r)
    total = eq[-1]
    cagr = total ** (1.0 / n_years) - 1.0 if n_years > 0 else np.nan
    rm = np.maximum.accumulate(eq)
    dd = eq / rm - 1.0
    mdd = dd.min()
    calmar = cagr / abs(mdd) if mdd != 0 else np.nan
    return sharpe, mdd, calmar


def maxdd_from_array(r):
    eq = np.cumprod(1.0 + r)
    rm = np.maximum.accumulate(eq)
    return float((eq / rm - 1.0).min())


def block_index(n, block, rng):
    n_blocks = (n // block) + 1
    parts = []
    for _ in range(n_blocks):
        s = int(rng.integers(0, n))
        e = s + block
        if e <= n:
            parts.append(np.arange(s, e))
        else:
            parts.append(np.concatenate([np.arange(s, n), np.arange(0, e - n)]))
    return np.concatenate(parts)[:n]


def summarize(arr):
    a = np.asarray(arr)
    lo, hi = np.percentile(a, 2.5), np.percentile(a, 97.5)
    return {
        "p_challenger_wins": float(np.mean(a > 0)),
        "mean": float(a.mean()),
        "ci_lo": float(lo), "ci_hi": float(hi),
        "excludes_zero": bool(lo > 0 or hi < 0),
    }


def paired_bootstrap(chal_r, base_r, n_years):
    n = len(chal_r)
    # PAIRED
    rng = np.random.default_rng(SEED)
    ds, dm, dc = [], [], []
    for _ in range(B):
        idx = block_index(n, BLOCK, rng)
        cs, cm, cc = metrics_from_array(chal_r[idx], n_years)
        bs, bm, bc = metrics_from_array(base_r[idx], n_years)
        ds.append(cs - bs); dm.append(cm - bm); dc.append(cc - bc)
    # NAIVE independent
    rng = np.random.default_rng(SEED)
    ns, nm, nc = [], [], []
    for _ in range(B):
        ic = block_index(n, BLOCK, rng)
        ib = block_index(n, BLOCK, rng)
        cs, cm, cc = metrics_from_array(chal_r[ic], n_years)
        bs, bm, bc = metrics_from_array(base_r[ib], n_years)
        ns.append(cs - bs); nm.append(cm - bm); nc.append(cc - bc)
    return {
        "paired": {"sharpe": summarize(ds), "maxdd": summarize(dm), "calmar": summarize(dc)},
        "naive":  {"sharpe": summarize(ns), "maxdd": summarize(nm), "calmar": summarize(nc)},
        "daily_corr": float(np.corrcoef(chal_r, base_r)[0, 1]),
    }


def rolling_diffs(chal, base, window):
    """chal, base: aligned daily-return Series. window: trading days.
    Monthly step. Returns dict with win fractions and per-window arrays."""
    common = chal.index.intersection(base.index)
    chal = chal.reindex(common); base = base.reindex(common)
    # monthly step anchor = each month-end position
    me = pd.Series(range(len(common)), index=common).groupby(
        pd.Grouper(freq="ME")).last().dropna().astype(int).values
    recs = []
    for pos in me:
        if pos + 1 < window:
            continue
        cr = chal.values[pos + 1 - window: pos + 1]
        br = base.values[pos + 1 - window: pos + 1]
        ny = window / 252.0
        cs, cm, cc = metrics_from_array(cr, ny)
        bs, bm, bc = metrics_from_array(br, ny)
        recs.append({"date": str(common[pos].date()),
                     "d_maxdd": cm - bm, "d_calmar": cc - bc,
                     "chal_maxdd": cm, "base_maxdd": bm})
    if not recs:
        return {"n_windows": 0}
    dmdd = np.array([r["d_maxdd"] for r in recs])
    dcal = np.array([r["d_calmar"] for r in recs])
    return {
        "n_windows": len(recs),
        "frac_win_maxdd": float(np.mean(dmdd > 0)),
        "frac_tie_maxdd": float(np.mean(np.abs(dmdd) < 1e-9)),
        "frac_win_calmar": float(np.mean(dcal > 0)),
        "mean_d_maxdd": float(dmdd.mean()),
        "median_d_maxdd": float(np.median(dmdd)),
        "mean_d_calmar": float(dcal.mean()),
        "median_d_calmar": float(np.median(dcal)),
        "max_d_maxdd": float(dmdd.max()),
        "min_d_maxdd": float(dmdd.min()),
        "windows": recs,
    }


def main():
    end = pd.Timestamp("2026-05-22")
    panel = load_panel(start=EXT_START, end=end)
    end = min(end, panel.index[-1])
    cash = panel["SHV"].ffill().pct_change().dropna()
    panel["BIL"] = stitch_bil(panel)
    panel["AGG"] = stitch_agg(panel)

    open_df, close_yf = H.load_open_close()
    intraday = (close_yf / open_df - 1.0).reindex(panel.index)
    overnight = (open_df / close_yf.shift(1) - 1.0).reindex(panel.index)

    cols = sorted(set(IVW.CPM_PROD_UNIVERSE + IVW.CPM_SAFE + ["HYG", "TIP"]) & set(panel.columns))
    close = panel[cols]
    daily = close.ffill().pct_change()

    print("Computing return series (ext, EW2/IV2/IV3/CONT @10bps)...")
    series = {}
    for sch in ("EW2", "IV2", "IV3", "CONT"):
        series[sch] = IVW.returns_for(close, daily, intraday, overnight, EXT_START, end, sch, COST)
        print(f"  {sch} done")

    windows = {"CLEAN": CLEAN_START, "EXT": EXT_START}

    # ---- verify anchors ----
    print("\n=== VERIFY anchors (full-sample point metrics, 10 bps) ===")
    expect = {
        "CLEAN": {"EW2": (1.2424, -16.35, 0.8704), "IV2": (1.2630, -13.14, 1.0945),
                  "IV3": (1.2453, -13.19, 1.0824), "CONT": (1.2935, -15.15, 0.9618)},
    }
    verify = {}
    for wn, wstart in windows.items():
        verify[wn] = {}
        for sch in ("EW2", "IV2", "IV3", "CONT"):
            s = series[sch]
            sw = s.loc[(s.index >= wstart) & (s.index <= end)]
            m = perf_metrics(sw, cash)
            verify[wn][sch] = {"sharpe": m["sharpe"], "maxdd": m["max_drawdown"], "calmar": m["calmar"]}
            exp = expect.get(wn, {}).get(sch)
            tag = ""
            if exp:
                ok = (abs(m["sharpe"] - exp[0]) < 5e-4 and abs(m["max_drawdown"] * 100 - exp[1]) < 0.02
                      and abs(m["calmar"] - exp[2]) < 5e-4)
                tag = f"  expect {exp[0]}/{exp[1]}%/{exp[2]}  {'OK' if ok else 'MISMATCH'}"
            print(f"  [{wn}] {sch:5} sharpe={m['sharpe']:.4f} maxdd={m['max_drawdown']*100:.2f}% "
                  f"calmar={m['calmar']:.4f}{tag}")

    # ---- Part 1: paired bootstrap ----
    boot = {}
    for wn, wstart in windows.items():
        boot[wn] = {}
        # align all four on common index for this window
        sl = {sch: series[sch].loc[(series[sch].index >= wstart) & (series[sch].index <= end)]
              for sch in series}
        common = sl["EW2"].index
        for sch in sl:
            common = common.intersection(sl[sch].index)
        n_years = (common[-1] - common[0]).days / 365.25
        arrs = {sch: sl[sch].reindex(common).values for sch in sl}
        for chal, base, label in PAIRS:
            print(f"\nBootstrapping [{wn}] {label}  n={len(common)} {n_years:.2f}y...")
            res = paired_bootstrap(arrs[chal], arrs[base], n_years)
            res["label"] = label
            boot[wn][f"{chal}_vs_{base}"] = res

    # ---- Part 2: rolling persistence ----
    rolling = {}
    for wn, wstart in windows.items():
        rolling[wn] = {}
        sl = {sch: series[sch].loc[(series[sch].index >= wstart) & (series[sch].index <= end)]
              for sch in series}
        for chal in ("IV2", "IV3"):
            for win_lbl, win in (("12m", 252), ("36m", 756)):
                rolling[wn][f"{chal}_vs_EW2_{win_lbl}"] = rolling_diffs(sl[chal], sl["EW2"], win)

    # ---- Part 2b: per-regime MaxDD ----
    regime = {}
    for rname, (rs, re) in REGIMES.items():
        rs_, re_ = pd.Timestamp(rs), pd.Timestamp(re)
        regime[rname] = {}
        for sch in ("EW2", "IV2", "IV3", "CONT"):
            s = series[sch]
            sw = s.loc[(s.index >= rs_) & (s.index <= re_)]
            regime[rname][sch] = maxdd_from_array(sw.values) if len(sw) > 1 else None

    payload = {
        "meta": {"B": B, "block": BLOCK, "seed": SEED, "cost_bps": COST, "conv": "mooex",
                 "lookback": CORR_LOOKBACK_DAYS, "K_top_half": 4,
                 "clean_start": str(CLEAN_START.date()), "ext_start": str(EXT_START.date()),
                 "end": str(end.date())},
        "verify": verify, "bootstrap": boot, "rolling": rolling, "regime": regime,
    }
    (HERE / "invvol_validation.json").write_text(json.dumps(payload, indent=2, default=float))
    print("\nDONE -> invvol_validation.json written")
    return payload


if __name__ == "__main__":
    main()
