# -*- coding: utf-8 -*-
"""ANALYST OOS robustness for +IEF (read-only re production; NO prod files; NO commit).

Question: is +IEF's rate-shock drawdown benefit OOS-CONSISTENT across sequential
sub-periods AND does it survive leave-2025-out, or is it episode-concentrated in
the 2025-tariff drawdown?

+IEF = full Faber-CPM stack with IEF added to the offensive/risk universe, exactly
as in research/cpm_universe_experiments.py (cpm_variant_wf, CPM_UNIVERSE + ["IEF"]).
+IEF is a fixed universe addition (no hyperparameter), so "walk-forward" =
sequential OOS sub-period stability of the +IEF-vs-prod delta, NOT re-fitting.

Look-ahead control: prod and +IEF daily-return series are produced ONCE by the
canonical causal mooex engine (each month's weights use only data up to sig date).
Folds are pure EVALUATION slices of those already-causal series. No re-fit, no
peeking. Single in-sample stack. clean window = decision lens. 10bps/side, both-252.
"""
import sys, json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from research import cpm_harness as Hn
from cpm_live import compute_target_weights, perf_metrics
# reuse the EXACT +IEF construction from the universe-experiments harness
from research.cpm_universe_experiments import cpm_variant_wf, CPM_UNIVERSE, CRISES

IEF_UNIVERSE = CPM_UNIVERSE + ["IEF"]


def ief_wf(panel, sig_d):
    return cpm_variant_wf(panel, sig_d, IEF_UNIVERSE)


def sub_metrics(ser, lo, hi, cash):
    w = ser.loc[(ser.index >= lo) & (ser.index <= hi)].dropna()
    if len(w) < 30:
        return None
    m = perf_metrics(w, cash)
    return {
        "start": str(w.index[0].date()), "end": str(w.index[-1].date()), "n": int(len(w)),
        "Sharpe": float(m.get("sharpe")), "Calmar": float(m.get("calmar")),
        "MaxDD": float(m.get("max_drawdown")), "CAGR": float(m.get("cagr")),
        "vol": float(m.get("vol")),
    }


def crisis_dd(ser, lo, hi):
    eq = (1.0 + ser).cumprod().dropna()
    if eq.empty:
        return None
    dd = eq / eq.cummax() - 1.0
    w = dd.loc[lo:hi]
    if len(w) == 0 or not np.isfinite(w.min()):
        return None
    return float(w.min())


def maxdd_of(r):
    r = r.dropna()
    if len(r) < 2:
        return np.nan
    eq = (1.0 + r).cumprod()
    return float((eq / eq.cummax() - 1.0).min())


def sharpe_of(r):
    r = r.dropna()
    v = r.std(ddof=0)
    if v <= 0 or len(r) < 2:
        return np.nan
    return (r.mean() * 252) / (v * np.sqrt(252))


def calmar_of(r):
    r = r.dropna()
    if len(r) < 2:
        return np.nan
    eq = (1.0 + r).cumprod()
    yrs = (eq.index[-1] - eq.index[0]).days / 365.25
    if yrs <= 0:
        return np.nan
    cagr = eq.iloc[-1] ** (1 / yrs) - 1
    mdd = (eq / eq.cummax() - 1).min()
    return cagr / abs(mdd) if mdd != 0 else np.nan


def paired_block_bootstrap(var_s, prod_s, B=5000, block=21, seed=42):
    """Paired block bootstrap on marginals (variant - prod): Sharpe, Calmar, and
    MaxDD (positive MaxDD marg = shallower/better DD for +IEF)."""
    df = pd.concat([var_s.rename("v"), prod_s.rename("p")], axis=1).dropna()
    n = len(df)
    if n < block * 5:
        return None
    rng = np.random.default_rng(seed)
    nblocks = int(np.ceil(n / block))
    idx_all = np.arange(n)
    v = df["v"].to_numpy(); p = df["p"].to_numpy(); di = df.index
    ds, dc, dd = [], [], []
    for _ in range(B):
        starts = rng.integers(0, n - block + 1, size=nblocks)
        sel = np.concatenate([idx_all[s:s + block] for s in starts])[:n]
        vs = pd.Series(v[sel], index=di); ps = pd.Series(p[sel], index=di)
        ds.append(sharpe_of(vs) - sharpe_of(ps))
        dc.append(calmar_of(vs) - calmar_of(ps))
        dd.append(maxdd_of(vs) - maxdd_of(ps))  # +ve = +IEF shallower DD
    ds = np.array(ds); dc = np.array(dc); dd = np.array(dd)

    def summ(a, gt=True):
        return {"mean": float(np.nanmean(a)),
                "ci": [float(np.nanpercentile(a, 2.5)), float(np.nanpercentile(a, 97.5))],
                "p_improve": float(np.mean(a > 0)) if gt else float(np.mean(a < 0))}
    return {"n": n, "B": B, "block": block,
            "sharpe": summ(ds), "calmar": summ(dc), "maxdd": summ(dd)}


def main():
    data = Hn.load_data()
    cash = data.cash

    # ---- GATE 1: prod anchor ----
    anchor = Hn.verify_anchor(data=data)
    print(f"[GATE] anchor PASS  Sharpe={anchor['Sharpe']:.4f} MaxDD={anchor['MaxDD']*100:.2f}% Calmar={anchor['Calmar']:.4f}")

    # ---- series (causal, produced once) ----
    prod = Hn.run_strategy(compute_target_weights, window="clean", data=data)
    ief = Hn.run_strategy(ief_wf, window="clean", data=data)

    prod_full = Hn.metrics(prod, data=data)
    ief_full = Hn.metrics(ief, data=data)

    # ---- GATE 2: +IEF full-sample reproduction vs findings ----
    # findings: +IEF CLEAN Sharpe 1.1076 / Calmar 0.9598 / Martin 3.3519 / MaxDD -11.97%
    rep_ok = (abs(ief_full["Sharpe"] - 1.1076) < 5e-4
              and abs(ief_full["Calmar"] - 0.9598) < 5e-4
              and abs(ief_full["MaxDD"] * 100 - (-11.97)) < 0.05)
    print(f"[GATE] +IEF repro Sharpe={ief_full['Sharpe']:.4f} Calmar={ief_full['Calmar']:.4f} "
          f"MaxDD={ief_full['MaxDD']*100:.2f}%  (expect 1.1076/0.9598/-11.97%)  ok={rep_ok}")

    clean_start = data.clean_start
    end = data.end

    # ---- SEQUENTIAL OOS FOLDS: 4 equal consecutive calendar windows ----
    # ~18yr clean span split into 4 contiguous ~4.5yr test windows.
    edges = pd.to_datetime(["2008-05-30", "2013-01-01", "2017-07-01", "2022-01-01", "2026-05-22"])
    fold_bounds = [(edges[i], edges[i + 1] - pd.Timedelta(days=1) if i < 3 else edges[i + 1])
                   for i in range(4)]
    folds = []
    for i, (lo, hi) in enumerate(fold_bounds, 1):
        pm = sub_metrics(prod, lo, hi, cash)
        im = sub_metrics(ief, lo, hi, cash)
        if pm is None or im is None:
            continue
        delta = {"Sharpe": im["Sharpe"] - pm["Sharpe"],
                 "Calmar": im["Calmar"] - pm["Calmar"],
                 "MaxDD_pp": (im["MaxDD"] - pm["MaxDD"]) * 100}  # +ve = +IEF shallower
        folds.append({"fold": i, "lo": str(lo.date()), "hi": str(hi.date()),
                      "prod": pm, "ief": im, "delta": delta})
        print(f"[FOLD {i}] {pm['start']}..{pm['end']}  "
              f"prod S={pm['Sharpe']:.3f} C={pm['Calmar']:.3f} DD={pm['MaxDD']*100:.2f}% | "
              f"ief S={im['Sharpe']:.3f} C={im['Calmar']:.3f} DD={im['MaxDD']*100:.2f}% | "
              f"dS={delta['Sharpe']:+.3f} dC={delta['Calmar']:+.3f} dDD={delta['MaxDD_pp']:+.2f}pp")

    # ---- LEAVE-2025-OUT: 2025-tariff episode is the tail; truncate at 2024-12-31 ----
    lo2 = clean_start; hi2 = pd.Timestamp("2024-12-31")
    prod_x25 = sub_metrics(prod, lo2, hi2, cash)
    ief_x25 = sub_metrics(ief, lo2, hi2, cash)
    delta_x25 = {"Sharpe": ief_x25["Sharpe"] - prod_x25["Sharpe"],
                 "Calmar": ief_x25["Calmar"] - prod_x25["Calmar"],
                 "MaxDD_pp": (ief_x25["MaxDD"] - prod_x25["MaxDD"]) * 100}
    print(f"[LEAVE-2025-OUT] {prod_x25['start']}..{prod_x25['end']}  "
          f"prod S={prod_x25['Sharpe']:.4f} C={prod_x25['Calmar']:.4f} DD={prod_x25['MaxDD']*100:.2f}% | "
          f"ief S={ief_x25['Sharpe']:.4f} C={ief_x25['Calmar']:.4f} DD={ief_x25['MaxDD']*100:.2f}% | "
          f"dS={delta_x25['Sharpe']:+.4f} dC={delta_x25['Calmar']:+.4f} dDD={delta_x25['MaxDD_pp']:+.2f}pp")

    # full-sample delta for reference
    delta_full = {"Sharpe": ief_full["Sharpe"] - prod_full["Sharpe"],
                  "Calmar": ief_full["Calmar"] - prod_full["Calmar"],
                  "MaxDD_pp": (ief_full["MaxDD"] - prod_full["MaxDD"]) * 100}

    # ---- per-crisis DD ----
    crisis = {nm: {"prod": crisis_dd(prod, lo, hi), "ief": crisis_dd(ief, lo, hi)}
              for nm, (lo, hi) in CRISES.items()}
    for nm, c in crisis.items():
        if c["prod"] is not None:
            print(f"[CRISIS {nm:<12}] prod {c['prod']*100:+.2f}%  ief {c['ief']*100:+.2f}%  "
                  f"delta {(c['ief']-c['prod'])*100:+.2f}pp")

    # ---- bootstrap leave-2025-out marginals ----
    prod_x = prod.loc[(prod.index >= lo2) & (prod.index <= hi2)]
    ief_x = ief.loc[(ief.index >= lo2) & (ief.index <= hi2)]
    boot_x25 = paired_block_bootstrap(ief_x, prod_x, B=5000, block=21)
    if boot_x25:
        print(f"[BOOT x25] DD marg {boot_x25['maxdd']['mean']*100:+.2f}pp "
              f"CI[{boot_x25['maxdd']['ci'][0]*100:+.2f},{boot_x25['maxdd']['ci'][1]*100:+.2f}]pp "
              f"p(improve)={boot_x25['maxdd']['p_improve']:.3f} | "
              f"Sharpe marg {boot_x25['sharpe']['mean']:+.4f} p(improve)={boot_x25['sharpe']['p_improve']:.3f}")

    # also bootstrap full-sample DD marginal for direct comparison vs prior p=0.78
    boot_full = paired_block_bootstrap(ief, prod, B=5000, block=21)
    if boot_full:
        print(f"[BOOT full] DD marg {boot_full['maxdd']['mean']*100:+.2f}pp "
              f"CI[{boot_full['maxdd']['ci'][0]*100:+.2f},{boot_full['maxdd']['ci'][1]*100:+.2f}]pp "
              f"p(improve)={boot_full['maxdd']['p_improve']:.3f}")

    out = {
        "anchor": anchor, "gate_repro_ok": bool(rep_ok),
        "prod_full": prod_full, "ief_full": ief_full, "delta_full": delta_full,
        "folds": folds,
        "leave_2025_out": {"prod": prod_x25, "ief": ief_x25, "delta": delta_x25},
        "crisis": crisis,
        "bootstrap_leave2025": boot_x25, "bootstrap_full": boot_full,
        "fold_design": "4 equal contiguous calendar windows over clean 2008-05-30..2026-05-22",
    }
    outpath = Path(__file__).resolve().parent / "cpm_ief_walkforward.json"
    with open(outpath, "w") as f:
        json.dump(out, f, indent=2, default=lambda o: None if isinstance(o, float) and np.isnan(o) else o)
    print("wrote", outpath)


if __name__ == "__main__":
    main()
