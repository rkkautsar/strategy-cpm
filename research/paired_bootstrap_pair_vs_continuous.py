"""Throwaway research: PAIRED stationary block bootstrap comparing the production
EW 50/50 min-var PAIR vs CONTINUOUS min-var weighting for the CPM sleeve.

Same CPM selection (U=R=C=1), differs ONLY in weighting step. Their daily return
series are highly correlated, so we resample the SAME block of dates for BOTH
series each iteration (joint resampling preserving pairing), compute each scheme's
Sharpe / MaxDD / Calmar on that resample, and record the sign of (continuous-pair).

Headline = PAIRED. For contrast we also run the NAIVE independent bootstrap
(resample the two series independently) to show how much pairing shrinks the
difference variance.

Config: stationary block bootstrap, B=2000, block=21 days, seed=42
(matches research/bootstrap_ci_2026_05_28.py).
Execution: T+1 MOO exact (mooex), 10 bps/side, cov 504d. Windows: CLEAN 18y
(2008-05-30..) and EXT 27y (1999-03-10..).

No production files touched. Writes findings md next to this file.
Verify: full-sample point metrics reproduce anchors before bootstrapping.
  pair clean 1.2424/0.8704/-16.35% ; continuous clean 1.2935/0.9618/-15.15%.
"""
import sys, json
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

from cpm_live import load_panel, CORR_LOOKBACK_DAYS, COST_BPS_PER_SIDE
import exec_lag_moo_validation_2026_05_30 as H
from sleeve_vs_benchmark_2026_05_30 import stitch_bil, stitch_agg
import pair_vs_continuous_minvar as PVC

B = 2000
BLOCK = 21
SEED = 42
COST = 10

CLEAN_START = pd.Timestamp("2008-05-30")
EXT_START = pd.Timestamp("1999-03-10")


# ---------- metrics from a raw returns array (annualized by n_years) ----------
def metrics_from_array(r, n_years):
    """r: 1d np array of daily returns. n_years: calendar years for CAGR."""
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


# ---------- block-start index generator (stationary block bootstrap) ----------
def block_index(n, block, rng):
    """Return an int index array of length n built from contiguous blocks
    (wraparound at the end), matching bootstrap_ci_2026_05_28 semantics."""
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


def run_window(pair_r, cont_r, n_years, label):
    """pair_r, cont_r: aligned 1d np arrays (same dates). Returns dict of results."""
    n = len(pair_r)

    # ----- PAIRED bootstrap: same block index applied to both series -----
    rng = np.random.default_rng(SEED)
    d_sharpe_p, d_mdd_p, d_calmar_p = [], [], []
    for _ in range(B):
        idx = block_index(n, BLOCK, rng)
        ps, pm, pc = metrics_from_array(pair_r[idx], n_years)
        cs, cm, cc = metrics_from_array(cont_r[idx], n_years)
        d_sharpe_p.append(cs - ps)
        d_mdd_p.append(cm - pm)          # MaxDD diff (both negative); >0 => continuous shallower
        d_calmar_p.append(cc - pc)

    # ----- NAIVE independent bootstrap: separate indices per series -----
    rng = np.random.default_rng(SEED)
    d_sharpe_n, d_mdd_n, d_calmar_n = [], [], []
    for _ in range(B):
        idx_p = block_index(n, BLOCK, rng)
        idx_c = block_index(n, BLOCK, rng)
        ps, pm, pc = metrics_from_array(pair_r[idx_p], n_years)
        cs, cm, cc = metrics_from_array(cont_r[idx_c], n_years)
        d_sharpe_n.append(cs - ps)
        d_mdd_n.append(cm - pm)
        d_calmar_n.append(cc - pc)

    def summarize(arr):
        a = np.asarray(arr)
        return {
            "p_cont_wins": float(np.mean(a > 0)),
            "mean": float(a.mean()),
            "ci_lo": float(np.percentile(a, 2.5)),
            "ci_hi": float(np.percentile(a, 97.5)),
            "excludes_zero": bool(np.percentile(a, 2.5) > 0 or np.percentile(a, 97.5) < 0),
        }

    return {
        "label": label, "n_days": n, "n_years": n_years,
        "paired": {
            "sharpe": summarize(d_sharpe_p),
            "maxdd": summarize(d_mdd_p),
            "calmar": summarize(d_calmar_p),
        },
        "naive": {
            "sharpe": summarize(d_sharpe_n),
            "maxdd": summarize(d_mdd_n),
            "calmar": summarize(d_calmar_n),
        },
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

    cols = sorted(set(PVC.CPM_PROD_UNIVERSE + PVC.CPM_SAFE + ["HYG", "TIP"]) & set(panel.columns))
    close = panel[cols]
    daily = close.ffill().pct_change()

    # Full EXT return series for both schemes @10bps; slice per window.
    print("Computing return series (ext, both schemes @10bps)...")
    pair_full = PVC.returns_for(close, daily, intraday, overnight, EXT_START, end, 1, COST)
    cont_full = PVC.returns_for(close, daily, intraday, overnight, EXT_START, end, 0, COST)

    from cpm_live import perf_metrics
    windows = {"CLEAN": CLEAN_START, "EXT": EXT_START}

    # ---- verify anchors (full-sample point metrics) ----
    print("\n=== VERIFY anchors (full-sample point metrics, 10 bps) ===")
    anchors = {
        "CLEAN": {"pair": (1.2424, 0.8704, -16.35), "cont": (1.2935, 0.9618, -15.15)},
    }
    verify = {}
    for wn, wstart in windows.items():
        pr = pair_full.loc[(pair_full.index >= wstart) & (pair_full.index <= end)]
        cr = cont_full.loc[(cont_full.index >= wstart) & (cont_full.index <= end)]
        mp = perf_metrics(pr, cash); mc = perf_metrics(cr, cash)
        verify[wn] = {
            "pair": {"sharpe": mp["sharpe"], "calmar": mp["calmar"], "maxdd": mp["max_drawdown"]},
            "cont": {"sharpe": mc["sharpe"], "calmar": mc["calmar"], "maxdd": mc["max_drawdown"]},
        }
        print(f"  [{wn}] pair: sharpe={mp['sharpe']:.4f} calmar={mp['calmar']:.4f} maxdd={mp['max_drawdown']*100:.2f}%")
        print(f"  [{wn}] cont: sharpe={mc['sharpe']:.4f} calmar={mc['calmar']:.4f} maxdd={mc['max_drawdown']*100:.2f}%")
        if wn in anchors:
            ep, ec = anchors[wn]["pair"], anchors[wn]["cont"]
            print(f"        expect pair {ep[0]}/{ep[1]}/{ep[2]}% ; cont {ec[0]}/{ec[1]}/{ec[2]}%")

    # ---- bootstrap per window ----
    results = {}
    for wn, wstart in windows.items():
        pr = pair_full.loc[(pair_full.index >= wstart) & (pair_full.index <= end)]
        cr = cont_full.loc[(cont_full.index >= wstart) & (cont_full.index <= end)]
        common = pr.index.intersection(cr.index)
        pr = pr.reindex(common); cr = cr.reindex(common)
        n_years = (common[-1] - common[0]).days / 365.25
        print(f"\nBootstrapping [{wn}] n={len(common)} days, {n_years:.2f}y, B={B}, block={BLOCK}...")
        results[wn] = run_window(pr.values, cr.values, n_years, wn)
        # correlation diagnostic
        results[wn]["daily_corr"] = float(np.corrcoef(pr.values, cr.values)[0, 1])

    payload = {
        "meta": {"B": B, "block": BLOCK, "seed": SEED, "cost_bps": COST,
                 "conv": "mooex", "lookback": CORR_LOOKBACK_DAYS,
                 "clean_start": str(CLEAN_START.date()), "ext_start": str(EXT_START.date()),
                 "end": str(end.date())},
        "verify": verify, "results": results,
    }
    (HERE / "paired_bootstrap_pair_vs_continuous.json").write_text(json.dumps(payload, indent=2, default=float))
    print("\nDONE -> json written")
    return payload


if __name__ == "__main__":
    main()
