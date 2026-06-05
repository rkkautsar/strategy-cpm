# -*- coding: utf-8 -*-
"""ANALYST harness (read-only re production; NO production files touched; NO commit).

CPM universe add/swap/remove variants vs production CPM.

Held FIXED at full CPM (everything except the universe):
  rank = m_faber / rv_252 ; screen = m_faber > 0 ; TOP_K = 4 ; inverse-vol weights
  (cov tail 252) ; HYG-or-TIP any-positive 13612U canary ; best-of-safe {SHV, IEF}
  by 13612U ; partial-safe breadth scaling (risky_fraction = n_picks/4).

Execution: mooex (T+1 MOO realistic: prev basket earns overnight close[T]->open[af],
new basket earns intraday open[af]->close[af], compounded), 10bps/side, real opens.

Production CPM anchor (CLEAN): Sharpe 1.1658 / MaxDD -12.97% / Calmar 1.0137.

GATE: cpm_variant_wf(universe=CPM) == compute_target_weights, weight-by-weight,
      and metric anchor match.
"""
import sys, json, itertools
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import bull_spy_live  # noqa: F401
if not hasattr(bull_spy_live, "_vol_gate_ok"):
    bull_spy_live._vol_gate_ok = lambda *a, **k: True
from cpm_live import (
    load_panel, perf_metrics, sig_13612U, best_safe, faber_sma_xs, inv_vol_weights,
    compute_target_weights, RISKY_UNIVERSE, SAFE_POOL, CANARY_ASSETS, DEFAULT_CASH,
    COST_BPS_PER_SIDE, CORR_LOOKBACK_DAYS,
)
import exec_lag_moo_validation_2026_05_30 as H

CONV = "mooex"
SAFE = ["SHV", "IEF"]
TOP_K = 4
CANARY = ["HYG", "TIP"]
ANCHOR_CLEAN = (1.1658, -12.97, 1.0137)

CPM_UNIVERSE = ["QQQ", "SPHQ", "EFA", "EEM", "VNQ", "GLD", "TLT", "DBC"]

VARIANTS = {
    "PROD (CPM)":            CPM_UNIVERSE,
    "1.+IEF (offensive)":    CPM_UNIVERSE + ["IEF"],
    "2.+IWM (US small)":     CPM_UNIVERSE + ["IWM"],
    "3.-GLD":                [t for t in CPM_UNIVERSE if t != "GLD"],
    "4.EEM->VWO":            ["QQQ", "SPHQ", "EFA", "VWO", "VNQ", "GLD", "TLT", "DBC"],
    "5.EFA->VEA":            ["QQQ", "SPHQ", "VEA", "EEM", "VNQ", "GLD", "TLT", "DBC"],
    "6.QQQ->SPY":            ["SPY", "SPHQ", "EFA", "EEM", "VNQ", "GLD", "TLT", "DBC"],
    "7a.cheap-ETF (VWO+VEA)": ["QQQ", "SPHQ", "VEA", "VWO", "VNQ", "GLD", "TLT", "DBC"],
    "7b.HAA-leaning":        ["SPY", "SPHQ", "VEA", "VWO", "VNQ", "TLT", "DBC", "IWM", "IEF"],
    "7c.+IEF -GLD":          [t for t in CPM_UNIVERSE if t != "GLD"] + ["IEF"],
}
# Assets to track selection frequency for (added-to-offensive).
TRACK = {"1.+IEF (offensive)": "IEF", "2.+IWM (US small)": "IWM", "7c.+IEF -GLD": "IEF"}

CRISES = {
    "GFC":          ("2007-10-01", "2009-06-30"),
    "COVID":        ("2020-02-01", "2020-04-30"),
    "2022":         ("2022-01-01", "2022-10-31"),
    "2025-tariff":  ("2025-02-01", "2025-05-22"),
}


def cpm_variant_wf(close, sig_d, universe, top_k=TOP_K, return_picks=False):
    """Full-CPM machinery (faber/rv rank, faber>0 screen, top-K, inv-vol, HYG-or-TIP,
    best-of-safe, partial-safe) over an arbitrary risky `universe`. universe=CPM ==
    compute_target_weights (gated)."""
    monthly = close.loc[:sig_d].resample("ME").last()
    safe = best_safe(monthly, sig_d, SAFE)

    cs = [sig_13612U(monthly[a]) for a in CANARY if a in monthly.columns]
    cs = [s for s in cs if pd.notna(s)]
    if not cs or sum(1 for s in cs if s > 0) == 0:
        return ([], safe) if return_picks else {safe: 1.0}

    present = [t for t in universe if t in monthly.columns]
    faber = faber_sma_xs(monthly)
    avail = [t for t in present
             if sig_d in close.index and pd.notna(close.loc[sig_d].get(t, np.nan))]
    if not avail:
        return ([], safe) if return_picks else {safe: 1.0}

    daily = close[avail].ffill().pct_change()
    rank_score, screen_val = {}, {}
    for t in avail:
        fb = float(faber[t]) if (t in faber.index and pd.notna(faber[t])) else np.nan
        if pd.isna(fb):
            continue
        rv = daily[t].loc[:sig_d].tail(252).std() * np.sqrt(252)
        if pd.isna(rv) or rv < 1e-9:
            rv = 1.0
        rank_score[t] = fb / rv
        screen_val[t] = fb
    if not rank_score:
        return ([], safe) if return_picks else {safe: 1.0}

    ranked = pd.Series(rank_score).sort_values(ascending=False)
    top = ranked.iloc[:min(top_k, len(ranked))]
    picks = [t for t in top.index if screen_val[t] > 0]
    if len(picks) == 0:
        return ([], safe) if return_picks else {safe: 1.0}
    if return_picks:
        return picks, safe

    n_picks = len(picks)
    risky_fraction = min(n_picks, top_k) / float(top_k)
    safe_fraction = 1.0 - risky_fraction
    base_w = inv_vol_weights(close.loc[:sig_d], picks, CORR_LOOKBACK_DAYS)
    out = {t: w * risky_fraction for t, w in base_w.items()}
    if safe_fraction > 0:
        out[safe] = out.get(safe, 0.0) + safe_fraction
    return out


def run_series(close, daily, intraday, overnight, wf, start, end):
    s, _ = H._segment_returns_conv(close, daily, wf, start, end, CONV,
                                   COST_BPS_PER_SIDE, intraday, overnight)
    return s


def met(daily, cash):
    m = perf_metrics(daily, cash)
    return {"sharpe": m.get("sharpe"), "cagr": m.get("cagr"), "vol": m.get("vol"),
            "maxdd": m.get("max_drawdown"), "calmar": m.get("calmar"), "martin": m.get("martin")}


def crisis_dd(ser, lo, hi):
    eq = (1.0 + ser).cumprod().dropna()
    if eq.empty:
        return None
    rm = eq.cummax()
    dd = eq / rm - 1.0
    w = dd.loc[lo:hi]
    if len(w) == 0 or not np.isfinite(w.min()):
        return None
    return float(w.min())


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
    days = (eq.index[-1] - eq.index[0]).days
    yrs = days / 365.25
    if yrs <= 0:
        return np.nan
    cagr = eq.iloc[-1] ** (1 / yrs) - 1
    mdd = (eq / eq.cummax() - 1).min()
    return cagr / abs(mdd) if mdd != 0 else np.nan


def paired_block_bootstrap(var_s, prod_s, B=5000, block=21, seed=42):
    """Paired block bootstrap on marginal (variant - prod). Resample the SAME
    block indices for both series (preserves pairing & dependence). Report
    distribution of Sharpe & Calmar marginals and one-sided p(marginal<=0)."""
    df = pd.concat([var_s.rename("v"), prod_s.rename("p")], axis=1).dropna()
    n = len(df)
    if n < block * 5:
        return None
    rng = np.random.default_rng(seed)
    nblocks = int(np.ceil(n / block))
    idx_all = np.arange(n)
    v = df["v"].to_numpy()
    p = df["p"].to_numpy()
    dindex = df.index
    d_sharpe, d_calmar = [], []
    for _ in range(B):
        starts = rng.integers(0, n - block + 1, size=nblocks)
        sel = np.concatenate([idx_all[s:s + block] for s in starts])[:n]
        vs = pd.Series(v[sel], index=dindex)  # synthetic time axis = original (for calmar yrs)
        ps = pd.Series(p[sel], index=dindex)
        d_sharpe.append(sharpe_of(vs) - sharpe_of(ps))
        d_calmar.append(calmar_of(vs) - calmar_of(ps))
    d_sharpe = np.array(d_sharpe); d_calmar = np.array(d_calmar)
    return {
        "sharpe_marg_mean": float(np.nanmean(d_sharpe)),
        "sharpe_marg_ci": [float(np.nanpercentile(d_sharpe, 2.5)), float(np.nanpercentile(d_sharpe, 97.5))],
        "sharpe_p_le0": float(np.mean(d_sharpe <= 0)),
        "calmar_marg_mean": float(np.nanmean(d_calmar)),
        "calmar_marg_ci": [float(np.nanpercentile(d_calmar, 2.5)), float(np.nanpercentile(d_calmar, 97.5))],
        "calmar_p_le0": float(np.mean(d_calmar <= 0)),
        "n": n, "B": B, "block": block,
    }


def main():
    end = pd.Timestamp("2026-05-22")
    ext_start = pd.Timestamp("1999-03-10")
    clean_start = pd.Timestamp("2008-05-30")

    panel = load_panel(start=ext_start, end=end)
    end = min(end, panel.index[-1])
    cash = panel["SHV"].ffill().pct_change().dropna()

    open_df, close_yf = H.load_open_close()
    intraday = (close_yf / open_df - 1.0).reindex(panel.index)
    overnight = (open_df / close_yf.shift(1) - 1.0).reindex(panel.index)

    all_uni = sorted({t for u in VARIANTS.values() for t in u})
    cols = sorted(set(all_uni + SAFE + CANARY) & set(panel.columns))
    missing = [t for t in all_uni if t not in cols]
    if missing:
        print("WARN missing universe tickers (not in panel):", missing)
    close = panel[cols]
    daily = close.ffill().pct_change()
    print("panel cols:", cols)

    windows = {"CLEAN": (clean_start, end), "EXT": (ext_start, end)}

    def windowed(ser):
        return {wn: met(ser.loc[(ser.index >= ws) & (ser.index <= we)], cash)
                for wn, (ws, we) in windows.items()}

    # ---- production direct anchor ----
    prod_cols = sorted(set(RISKY_UNIVERSE + SAFE_POOL + CANARY_ASSETS + [DEFAULT_CASH]) & set(panel.columns))
    prod_close = panel[prod_cols]
    prod_daily = prod_close.ffill().pct_change()
    prod_s = run_series(prod_close, prod_daily, intraday, overnight,
                        lambda sd: compute_target_weights(prod_close, sd)[0], ext_start, end)
    prod_m = windowed(prod_s)

    # ---- GATE: cpm_variant_wf(CPM) == compute_target_weights weight-by-weight ----
    monthly_idx = (pd.DataFrame({"x": 1}, index=close.index)
                   .groupby(pd.Grouper(freq="ME")).tail(1))
    sigs = monthly_idx.index[(monthly_idx.index >= ext_start) & (monthly_idx.index <= end)].tolist()
    gate_mismatch = 0
    for sd in sigs:
        a = {k: round(v, 6) for k, v in cpm_variant_wf(close, sd, CPM_UNIVERSE).items() if abs(v) > 1e-9}
        b = {k: round(v, 6) for k, v in compute_target_weights(prod_close, sd)[0].items() if abs(v) > 1e-9}
        if a != b:
            gate_mismatch += 1
    gate_wbw = (gate_mismatch == 0)

    c = prod_m["CLEAN"]
    anchor_ok = (abs(c["sharpe"] - ANCHOR_CLEAN[0]) < 5e-4
                 and abs(c["maxdd"] * 100 - ANCHOR_CLEAN[1]) < 0.05
                 and abs(c["calmar"] - ANCHOR_CLEAN[2]) < 5e-4)
    print(f"GATE weight-by-weight mismatch months: {gate_mismatch} (pass={gate_wbw})")
    print(f"ANCHOR clean sharpe={c['sharpe']:.4f} maxdd={c['maxdd']*100:.2f}% calmar={c['calmar']:.4f} (ok={anchor_ok})")

    # ---- run all variants ----
    results = {}
    series_store = {}
    for name, uni in VARIANTS.items():
        if name == "PROD (CPM)":
            ser = prod_s
        else:
            wf = lambda sd, u=uni: cpm_variant_wf(close, sd, u)
            ser = run_series(close, daily, intraday, overnight, wf, ext_start, end)
        series_store[name] = ser
        mw = windowed(ser)
        crisis = {nm: crisis_dd(ser, lo, hi) for nm, (lo, hi) in CRISES.items()}
        # selection frequency for tracked added assets
        selfreq = None
        if name in TRACK:
            tk = TRACK[name]
            n_on, n_pick = 0, 0
            for sd in sigs:
                picks, _ = cpm_variant_wf(close, sd, uni, return_picks=True)
                if picks:
                    n_on += 1
                    if tk in picks:
                        n_pick += 1
            selfreq = {"asset": tk, "risk_on_months": n_on, "picked_months": n_pick,
                       "pick_rate_of_riskon": (n_pick / n_on) if n_on else None,
                       "pick_rate_all": (n_pick / len(sigs)) if sigs else None}
        results[name] = {"metrics": mw, "crisis": crisis, "selfreq": selfreq}
        cm = mw["CLEAN"]
        print(f"{name:<24} CLEAN sharpe={cm['sharpe']:.4f} calmar={cm['calmar']:.4f} "
              f"martin={cm['martin']:.4f} maxdd={cm['maxdd']*100:.2f}%"
              + (f"  [{selfreq['asset']} picked {selfreq['picked_months']}/{selfreq['risk_on_months']} risk-on mo]" if selfreq else ""))

    # ---- bootstrap on any variant beating prod on Sharpe AND Calmar (CLEAN) ----
    pc = prod_m["CLEAN"]
    boots = {}
    for name in VARIANTS:
        if name == "PROD (CPM)":
            continue
        m = results[name]["metrics"]["CLEAN"]
        if (m["sharpe"] > pc["sharpe"]) and (m["calmar"] > pc["calmar"]):
            print(f"BOOTSTRAP (beats prod on Sharpe&Calmar): {name}")
            vs = series_store[name]
            vs_c = vs.loc[(vs.index >= clean_start) & (vs.index <= end)]
            ps_c = prod_s.loc[(prod_s.index >= clean_start) & (prod_s.index <= end)]
            boots[name] = paired_block_bootstrap(vs_c, ps_c, B=5000, block=21)
            print(f"   sharpe_marg={boots[name]['sharpe_marg_mean']:.4f} "
                  f"CI={boots[name]['sharpe_marg_ci']} p(<=0)={boots[name]['sharpe_p_le0']:.3f}")
    if not boots:
        print("No variant beats prod on BOTH Sharpe & Calmar (CLEAN). No bootstrap needed.")

    out = {
        "conv": CONV, "anchor_ok": bool(anchor_ok), "gate_wbw": bool(gate_wbw),
        "gate_mismatch_months": int(gate_mismatch),
        "windows": {k: [str(v[0].date()), str(v[1].date())] for k, v in windows.items()},
        "prod_clean": pc, "results": results, "bootstrap": boots,
        "variants": {k: v for k, v in VARIANTS.items()},
    }
    outpath = Path(__file__).resolve().parent / "cpm_universe_experiments.json"
    with open(outpath, "w") as f:
        json.dump(out, f, indent=2, default=lambda o: None if isinstance(o, float) and np.isnan(o) else o)
    print("wrote", outpath)


if __name__ == "__main__":
    main()
