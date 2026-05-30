"""Throwaway research: ONE consolidated head-to-head of all real CPM weighting
candidates over the SAME top-K=4 trend-qualified pool, with paired block
bootstrap significance, to pick the production weighting.

Two design axes: SUB-SELECTION (how many of the top-K=4 to hold) x WEIGHTING.

Schemes (all over the identical CPM selection: U=R=C=1, K=4 top-half, cov 504d,
mooex T+1 MOO exact, 10 bps/side):
  CONT      = continuous min-variance over all 4 (full-cov SLSQP).
  IV4       = inverse-vol over ALL 4 (whole top-K, no sub-selection).
  INVVOL-3  = select the 3 lowest-variance, inverse-vol weight.
  INVVOL-2  = select the 2 lowest-variance, inverse-vol weight.
  EW2 (ref) = production select-2 equal weight.
  ERC (ref) = equal-risk-contribution over all 4 (full cov).

Delegates weighting/selection to inverse_vol_weighting (CONT/IV2/IV3/IV4/EW2)
and weighting_headtohead (ERC) for EXACT anchor reproduction. Bootstrap
primitives reused from paired_bootstrap_pair_vs_continuous (B=2000, block=21,
seed=42, SAME block index across the compared pair).

Outputs (no production files touched):
  1. ONE metrics table (clean + ext): net/gross Sharpe/CAGR/Vol/MaxDD/Calmar.
  2. Paired block bootstrap: P(beats) + diff-CI for key contrasts.
  3. Estimation sensitivity: cov lookback 504 -> 480/528 mean/max L1 drift.
  4. Concentration: risk-on avg/max single-asset weight, effN.
Writes weighting_consolidated.json + weighting_consolidated_findings.md.
"""
import sys, json
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

from cpm_live import load_panel, perf_metrics, COST_BPS_PER_SIDE, CORR_LOOKBACK_DAYS
import exec_lag_moo_validation_2026_05_30 as H
from sleeve_vs_benchmark_2026_05_30 import stitch_bil, stitch_agg
import inverse_vol_weighting as IVW
import weighting_headtohead as H2H
import paired_bootstrap_pair_vs_continuous as PBC

CONV = "mooex"
B, BLOCK, SEED = PBC.B, PBC.BLOCK, PBC.SEED
CLEAN_START = pd.Timestamp("2008-05-30")
EXT_START = pd.Timestamp("1999-03-10")

# scheme key -> (display label, source module, needs full cov, needs solver)
SCHEMES = [
    ("CONT", "CONT continuous min-var (all 4, full cov)", "IVW", True, True),
    ("IV4", "IV4 inverse-vol all 4 (whole top-K)", "IVW", False, False),
    ("IV3", "INVVOL-3 (select 3 lowest-var, inv-vol)", "IVW", False, False),
    ("IV2", "INVVOL-2 (select 2 lowest-var, inv-vol)", "IVW", False, False),
    ("EW2", "EW-2 pair (production, select-2 equal)", "IVW", False, False),
    ("ERC", "ERC equal-risk-contrib (all 4, full cov)", "H2H", True, True),
]
ANCHORS = {  # CLEAN net 10bps (sharpe, maxdd%, calmar)
    "CONT": (1.2935, -15.15, 0.9618),
    "IV4": (1.1491, -12.67, 1.0614),
    "IV3": (1.2453, -13.19, 1.0824),
    "IV2": (1.2630, -13.14, 1.0945),
    "EW2": (1.2424, -16.35, 0.8704),
}


def _mod(src):
    return IVW if src == "IVW" else H2H


def met(daily, cash):
    m = perf_metrics(daily, cash)
    return {"sharpe": m.get("sharpe"), "cagr": m.get("cagr"),
            "maxdd": m.get("max_drawdown"), "calmar": m.get("calmar"), "vol": m.get("vol")}


def paired_contrast(a_r, b_r, n_years):
    """Paired block bootstrap. diff = (a - b); positive => A better.
    For maxdd both negative => positive diff means A shallower (better)."""
    n = len(a_r)
    rng = np.random.default_rng(SEED)
    ds, dm, dc = [], [], []
    for _ in range(B):
        idx = PBC.block_index(n, BLOCK, rng)
        as_, am, ac = PBC.metrics_from_array(a_r[idx], n_years)
        bs, bm, bc = PBC.metrics_from_array(b_r[idx], n_years)
        ds.append(as_ - bs); dm.append(am - bm); dc.append(ac - bc)

    def summ(arr):
        x = np.asarray(arr)
        lo, hi = float(np.percentile(x, 2.5)), float(np.percentile(x, 97.5))
        return {"p_a_wins": float(np.mean(x > 0)), "mean_a_minus_b": float(x.mean()),
                "ci_lo": lo, "ci_hi": hi, "excludes_zero": bool(lo > 0 or hi < 0)}
    return {"sharpe": summ(ds), "maxdd": summ(dm), "calmar": summ(dc)}


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

    cpm_cols = sorted(set(IVW.CPM_PROD_UNIVERSE + IVW.CPM_SAFE + ["HYG", "TIP"]) & set(panel.columns))
    close = panel[cpm_cols]
    daily = close.ffill().pct_change()

    windows = {"CLEAN": (CLEAN_START, end), "EXT": (EXT_START, end)}

    # ---- return series (ext, all schemes, 0 & 10 bps) ----
    print("Computing return series (ext, all schemes, 0 & 10 bps)...")
    ret = {}
    for key, _, src, _, _ in SCHEMES:
        m = _mod(src)
        for cb in (0, 10):
            ret[(key, cb)] = m.returns_for(close, daily, intraday, overnight,
                                           EXT_START, end, key, cb)
        print(f"  {key} done")

    out = {"meta": {"conv": CONV, "lookback": CORR_LOOKBACK_DAYS,
                    "cost_bps_prod": COST_BPS_PER_SIDE, "K_top_half": 4,
                    "B": B, "block": BLOCK, "seed": SEED,
                    "clean_start": str(CLEAN_START.date()),
                    "ext_start": str(EXT_START.date()), "end": str(end.date())},
           "windows": {}}

    # ---- metrics table + concentration ----
    for wn, (ws_, we_) in windows.items():
        n_years = (we_ - ws_).days / 365.25
        sigs = IVW.sig_dates(close, ws_, we_)
        wd = {"n_years": round(n_years, 4), "schemes": {}}
        for key, label, src, full_cov, solver in SCHEMES:
            m = _mod(src)
            ws = [w for _, w in m.weight_series(close, daily, sigs, key)]
            conc_all = [IVW.concentration(w) for w in ws]
            conc_ron = [IVW.concentration(w) for w in ws if IVW.is_risk_on(w)]
            perf = {}
            for cb in (0, 10):
                s = ret[(key, cb)]
                sw = s.loc[(s.index >= ws_) & (s.index <= we_)]
                perf[cb] = met(sw, cash)
            wd["schemes"][key] = {
                "label": label, "needs_full_cov": full_cov, "needs_solver": solver,
                "gross_0bps": perf[0], "net_10bps": perf[10],
                "riskon_avg_max_weight": float(np.mean([c[0] for c in conc_ron])) if conc_ron else float("nan"),
                "riskon_max_max_weight": float(np.max([c[0] for c in conc_ron])) if conc_ron else float("nan"),
                "riskon_avg_eff_n": float(np.mean([c[1] for c in conc_ron])) if conc_ron else float("nan"),
                "n_risk_on": len(conc_ron),
            }
        out["windows"][wn] = wd

    # ---- paired bootstrap contrasts ----
    print("Paired block bootstrap contrasts...")
    contrasts = [
        ("CONT_vs_IV4", "CONT", "IV4"),
        ("CONT_vs_INVVOL3", "CONT", "IV3"),
        ("CONT_vs_INVVOL2", "CONT", "IV2"),
        ("INVVOL3_vs_IV4", "IV3", "IV4"),
        ("INVVOL2_vs_INVVOL3", "IV2", "IV3"),
    ]
    boot = {}
    for wn, (ws_, we_) in windows.items():
        sl = lambda s: s.loc[(s.index >= ws_) & (s.index <= we_)]
        wb = {}
        for name, a_key, b_key in contrasts:
            a, b = sl(ret[(a_key, 10)]), sl(ret[(b_key, 10)])
            common = a.index.intersection(b.index)
            a, b = a.reindex(common), b.reindex(common)
            n_years = (common[-1] - common[0]).days / 365.25
            res = paired_contrast(a.values, b.values, n_years)
            res["n_days"] = len(common)
            res["corr"] = float(np.corrcoef(a.values, b.values)[0, 1])
            res["a"], res["b"] = a_key, b_key
            wb[name] = res
        boot[wn] = wb
    out["paired_bootstrap"] = boot

    # ---- estimation sensitivity: lookback 504 -> 480/528 (ext sigs) ----
    print("Estimation sensitivity (cov lookback perturbation)...")
    sens = {}
    sigs_ext = IVW.sig_dates(close, EXT_START, end)
    for key, label, src, full_cov, solver in SCHEMES:
        m = _mod(src)
        base = {sd: w for sd, w in m.weight_series(close, daily, sigs_ext, key, 504)}
        moves = {}
        for lb in (480, 528):
            pert = {sd: w for sd, w in m.weight_series(close, daily, sigs_ext, key, lb)}
            ds = [IVW.l1(base[sd], pert[sd]) for sd in sigs_ext]
            moves[lb] = {"mean_l1": float(np.mean(ds)), "max_l1": float(np.max(ds))}
        sens[key] = {"label": label, "needs_full_cov": full_cov,
                     "480": moves[480], "528": moves[528],
                     "avg_mean_l1": float(np.mean([moves[480]["mean_l1"], moves[528]["mean_l1"]]))}
    out["estimation_sensitivity"] = sens

    (HERE / "weighting_consolidated.json").write_text(json.dumps(out, indent=2, default=float))

    # ---- console verify ----
    print("\n=== VERIFY anchors (CLEAN, net 10 bps) ===")
    for key, (es, em, ec) in ANCHORS.items():
        p = out["windows"]["CLEAN"]["schemes"][key]["net_10bps"]
        ok = (abs(p["sharpe"] - es) < 5e-4 and abs(p["maxdd"] * 100 - em) < 2e-2
              and abs(p["calmar"] - ec) < 5e-4)
        print(f"  {key:<5}: sharpe={p['sharpe']:.4f} maxdd={p['maxdd']*100:.2f}% "
              f"calmar={p['calmar']:.4f}  expect {es}/{em}%/{ec}  {'OK' if ok else 'MISMATCH'}")

    print("\n=== CONSOLIDATED HEAD-TO-HEAD (net 10 bps) ===")
    for wn in ("CLEAN", "EXT"):
        print(f"\n[{wn}]  scheme                                      Sharpe   CAGR    Vol     MaxDD    Calmar")
        for key, label, _, _, _ in SCHEMES:
            p = out["windows"][wn]["schemes"][key]["net_10bps"]
            print(f"  {label:<42} {p['sharpe']:.4f}  {p['cagr']*100:5.2f}%  "
                  f"{p['vol']*100:5.2f}%  {p['maxdd']*100:6.2f}%  {p['calmar']:.4f}")

    print("\n=== PAIRED BOOTSTRAP (diff = A - B, net 10 bps) ===")
    for wn in ("CLEAN", "EXT"):
        print(f"\n[{wn}]")
        for name, a_key, b_key in contrasts:
            r = out["paired_bootstrap"][wn][name]
            for metric in ("sharpe", "maxdd", "calmar"):
                d = r[metric]
                star = "*" if d["excludes_zero"] else " "
                print(f"  {name:<22} {metric:<7} P(A wins)={d['p_a_wins']:.3f} "
                      f"meanD={d['mean_a_minus_b']:+.4f} CI[{d['ci_lo']:+.4f},{d['ci_hi']:+.4f}] {star}")
    print("\nDONE -> json written")
    return out


if __name__ == "__main__":
    main()
