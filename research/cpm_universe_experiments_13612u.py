# -*- coding: utf-8 -*-
"""ANALYST harness (read-only re production; NO production files touched; NO commit).

CPM universe add/swap/remove variants under the 13612U COUPLED trend metric.

This is the metric-robustness twin of research/cpm_universe_experiments.py (the
Faber sweep). Same universe variants, same full-CPM stack, EXCEPT the coupled
trend metric is flipped Faber -> 13612U:

  rank  = sig_13612U(monthly) / rv_252   (vol-adjust kept)
  screen= sig_13612U(monthly) > 0        (coupled: same metric drives rank+screen)

Held FIXED at full CPM otherwise:
  TOP_K=4 ; inverse-vol weights (cov tail 252) ; HYG-or-TIP any-positive 13612U
  canary ; best-of-safe {SHV, IEF} by 13612U ; partial-safe breadth scaling
  (risky_fraction = n_picks/4) ; both-252 lookbacks.

Execution: mooex (T+1 MOO realistic), 10bps/side, real opens. Identical to the
Faber sweep.

BASELINE = 13612U-CPM (not Faber prod):
  CLEAN Sharpe 1.1540 / MaxDD -13.32% / Calmar 0.9876.

GATES:
  (1) cpm_wf(CPM, faber) == compute_target_weights weight-by-weight (Faber prod
      anchor reproduces).
  (2) cpm_wf(CPM, 13612u) CLEAN metrics reproduce the 13612U-CPM baseline anchor.
"""
import sys, json
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
ANCHOR_CLEAN_FABER = (1.1658, -12.97, 1.0137)   # Faber prod gate
ANCHOR_CLEAN_13612 = (1.1540, -13.32, 0.9876)   # 13612U-CPM baseline (this study)

CPM_UNIVERSE = ["QQQ", "SPHQ", "EFA", "EEM", "VNQ", "GLD", "TLT", "DBC"]

# Same variant set as the Faber sweep.
VARIANTS = {
    "BASE (13612U-CPM)":      CPM_UNIVERSE,
    "1.+IEF (offensive)":     CPM_UNIVERSE + ["IEF"],
    "2.+IWM (US small)":      CPM_UNIVERSE + ["IWM"],
    "3.-GLD":                 [t for t in CPM_UNIVERSE if t != "GLD"],
    "4.EEM->VWO":             ["QQQ", "SPHQ", "EFA", "VWO", "VNQ", "GLD", "TLT", "DBC"],
    "5.EFA->VEA":             ["QQQ", "SPHQ", "VEA", "EEM", "VNQ", "GLD", "TLT", "DBC"],
    "6.QQQ->SPY":             ["SPY", "SPHQ", "EFA", "EEM", "VNQ", "GLD", "TLT", "DBC"],
    "7a.cheap-ETF (VWO+VEA)": ["QQQ", "SPHQ", "VEA", "VWO", "VNQ", "GLD", "TLT", "DBC"],
    "7b.HAA-leaning":         ["SPY", "SPHQ", "VEA", "VWO", "VNQ", "TLT", "DBC", "IWM", "IEF"],
    "7c.+IEF -GLD":           [t for t in CPM_UNIVERSE if t != "GLD"] + ["IEF"],
}
TRACK = {"1.+IEF (offensive)": "IEF", "2.+IWM (US small)": "IWM", "7c.+IEF -GLD": "IEF"}

CRISES = {
    "GFC":          ("2007-10-01", "2009-06-30"),
    "COVID":        ("2020-02-01", "2020-04-30"),
    "2022":         ("2022-01-01", "2022-10-31"),
    "2025-tariff":  ("2025-02-01", "2025-05-22"),
}


def cpm_wf(close, sig_d, universe, trend, top_k=TOP_K, return_picks=False):
    """Full-CPM machinery with COUPLED trend metric flip. trend in {'faber','13612u'}
    flips BOTH the rank numerator AND the absolute screen metric. universe=CPM,
    trend='faber' == compute_target_weights (gated)."""
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
        u = sig_13612U(monthly[t]) if t in monthly.columns else np.nan
        fb = float(faber[t]) if (t in faber.index and pd.notna(faber[t])) else np.nan
        num = fb if trend == "faber" else u
        if pd.isna(num):
            continue
        rv = daily[t].loc[:sig_d].tail(252).std() * np.sqrt(252)
        if pd.isna(rv) or rv < 1e-9:
            rv = 1.0
        rank_score[t] = num / rv
        screen_val[t] = num
    if not rank_score:
        return ([], safe) if return_picks else {safe: 1.0}

    ranked = pd.Series(rank_score).sort_values(ascending=False)
    top = ranked.iloc[:min(top_k, len(ranked))]
    picks = [t for t in top.index if pd.notna(screen_val.get(t, np.nan)) and screen_val[t] > 0]
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


def maxdd_of(r):
    r = r.dropna()
    if len(r) < 2:
        return np.nan
    eq = (1.0 + r).cumprod()
    return float((eq / eq.cummax() - 1).min())


def paired_block_bootstrap(var_s, prod_s, B=5000, block=21, seed=42, dd=False):
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
    d_sharpe, d_calmar, d_dd = [], [], []
    for _ in range(B):
        starts = rng.integers(0, n - block + 1, size=nblocks)
        sel = np.concatenate([idx_all[s:s + block] for s in starts])[:n]
        vs = pd.Series(v[sel], index=dindex)
        ps = pd.Series(p[sel], index=dindex)
        d_sharpe.append(sharpe_of(vs) - sharpe_of(ps))
        d_calmar.append(calmar_of(vs) - calmar_of(ps))
        if dd:
            # marginal in pp: positive = variant shallower (better) drawdown
            d_dd.append((maxdd_of(vs) - maxdd_of(ps)) * 100.0)
    d_sharpe = np.array(d_sharpe); d_calmar = np.array(d_calmar)
    res = {
        "sharpe_marg_mean": float(np.nanmean(d_sharpe)),
        "sharpe_marg_ci": [float(np.nanpercentile(d_sharpe, 2.5)), float(np.nanpercentile(d_sharpe, 97.5))],
        "sharpe_p_le0": float(np.mean(d_sharpe <= 0)),
        "calmar_marg_mean": float(np.nanmean(d_calmar)),
        "calmar_marg_ci": [float(np.nanpercentile(d_calmar, 2.5)), float(np.nanpercentile(d_calmar, 97.5))],
        "calmar_p_le0": float(np.mean(d_calmar <= 0)),
        "n": n, "B": B, "block": block,
    }
    if dd:
        d_dd = np.array(d_dd)
        res.update({
            "dd_marg_mean": float(np.nanmean(d_dd)),
            "dd_marg_ci": [float(np.nanpercentile(d_dd, 2.5)), float(np.nanpercentile(d_dd, 97.5))],
            "dd_p_improve": float(np.mean(d_dd > 0)),
        })
    return res


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

    # ---- Faber production direct anchor (gate 1) ----
    prod_cols = sorted(set(RISKY_UNIVERSE + SAFE_POOL + CANARY_ASSETS + [DEFAULT_CASH]) & set(panel.columns))
    prod_close = panel[prod_cols]
    prod_daily = prod_close.ffill().pct_change()
    prod_s = run_series(prod_close, prod_daily, intraday, overnight,
                        lambda sd: compute_target_weights(prod_close, sd)[0], ext_start, end)
    prod_m = windowed(prod_s)

    monthly_idx = (pd.DataFrame({"x": 1}, index=close.index)
                   .groupby(pd.Grouper(freq="ME")).tail(1))
    sigs = monthly_idx.index[(monthly_idx.index >= ext_start) & (monthly_idx.index <= end)].tolist()

    # GATE 1: cpm_wf(CPM, faber) == compute_target_weights
    gate_mismatch = 0
    for sd in sigs:
        a = {k: round(v, 6) for k, v in cpm_wf(close, sd, CPM_UNIVERSE, "faber").items() if abs(v) > 1e-9}
        b = {k: round(v, 6) for k, v in compute_target_weights(prod_close, sd)[0].items() if abs(v) > 1e-9}
        if a != b:
            gate_mismatch += 1
    gate_wbw = (gate_mismatch == 0)

    cf = prod_m["CLEAN"]
    faber_anchor_ok = (abs(cf["sharpe"] - ANCHOR_CLEAN_FABER[0]) < 5e-4
                       and abs(cf["maxdd"] * 100 - ANCHOR_CLEAN_FABER[1]) < 0.05
                       and abs(cf["calmar"] - ANCHOR_CLEAN_FABER[2]) < 5e-4)
    print(f"GATE1 faber weight-by-weight mismatch months: {gate_mismatch} (pass={gate_wbw})")
    print(f"GATE1 faber clean sharpe={cf['sharpe']:.4f} maxdd={cf['maxdd']*100:.2f}% "
          f"calmar={cf['calmar']:.4f} (ok={faber_anchor_ok})")

    # ---- 13612U-CPM baseline (gate 2) ----
    base_s = run_series(close, daily, intraday, overnight,
                        lambda sd: cpm_wf(close, sd, CPM_UNIVERSE, "13612u"), ext_start, end)
    base_m = windowed(base_s)
    cb = base_m["CLEAN"]
    base_anchor_ok = (abs(cb["sharpe"] - ANCHOR_CLEAN_13612[0]) < 1e-3
                      and abs(cb["maxdd"] * 100 - ANCHOR_CLEAN_13612[1]) < 0.05
                      and abs(cb["calmar"] - ANCHOR_CLEAN_13612[2]) < 1e-3)
    print(f"GATE2 13612U-CPM baseline clean sharpe={cb['sharpe']:.4f} maxdd={cb['maxdd']*100:.2f}% "
          f"calmar={cb['calmar']:.4f} martin={cb['martin']:.4f} (ok={base_anchor_ok})")

    # ---- run all variants under 13612U ----
    results = {}
    series_store = {"BASE (13612U-CPM)": base_s}
    for name, uni in VARIANTS.items():
        if name == "BASE (13612U-CPM)":
            ser = base_s
        else:
            wf = lambda sd, u=uni: cpm_wf(close, sd, u, "13612u")
            ser = run_series(close, daily, intraday, overnight, wf, ext_start, end)
        series_store[name] = ser
        mw = windowed(ser)
        crisis = {nm: crisis_dd(ser, lo, hi) for nm, (lo, hi) in CRISES.items()}
        selfreq = None
        if name in TRACK:
            tk = TRACK[name]
            n_on, n_pick = 0, 0
            for sd in sigs:
                picks, _ = cpm_wf(close, sd, uni, "13612u", return_picks=True)
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

    # ---- bootstrap vs 13612U baseline ----
    bc = base_m["CLEAN"]
    boots = {}
    base_c = base_s.loc[(base_s.index >= clean_start) & (base_s.index <= end)]
    # (a) any variant beating baseline on Sharpe AND Calmar
    for name in VARIANTS:
        if name == "BASE (13612U-CPM)":
            continue
        m = results[name]["metrics"]["CLEAN"]
        if (m["sharpe"] > bc["sharpe"]) and (m["calmar"] > bc["calmar"]):
            print(f"BOOTSTRAP (beats baseline on Sharpe&Calmar): {name}")
            vs = series_store[name]
            vs_c = vs.loc[(vs.index >= clean_start) & (vs.index <= end)]
            boots[name] = paired_block_bootstrap(vs_c, base_c, B=5000, block=21)
            print(f"   sharpe_marg={boots[name]['sharpe_marg_mean']:.4f} "
                  f"CI={boots[name]['sharpe_marg_ci']} p(<=0)={boots[name]['sharpe_p_le0']:.3f}")
    if not boots:
        print("No variant beats baseline on BOTH Sharpe & Calmar (CLEAN).")

    # (d) targeted DD-marginal bootstrap on Treasury-in / gold-out variants
    dd_boots = {}
    for name in ["1.+IEF (offensive)", "7c.+IEF -GLD", "3.-GLD"]:
        vs = series_store[name]
        vs_c = vs.loc[(vs.index >= clean_start) & (vs.index <= end)]
        dd_boots[name] = paired_block_bootstrap(vs_c, base_c, B=5000, block=21, dd=True)
        print(f"DD-BOOT {name}: dd_marg={dd_boots[name]['dd_marg_mean']:.2f}pp "
              f"CI={dd_boots[name]['dd_marg_ci']} p(improve)={dd_boots[name]['dd_p_improve']:.3f}")

    out = {
        "conv": CONV,
        "gate1_faber_wbw_pass": bool(gate_wbw), "gate1_mismatch_months": int(gate_mismatch),
        "gate1_faber_anchor_ok": bool(faber_anchor_ok),
        "gate2_base_anchor_ok": bool(base_anchor_ok),
        "windows": {k: [str(v[0].date()), str(v[1].date())] for k, v in windows.items()},
        "base_clean": bc, "results": results, "bootstrap": boots, "dd_bootstrap": dd_boots,
        "variants": {k: v for k, v in VARIANTS.items()},
    }
    outpath = Path(__file__).resolve().parent / "cpm_universe_experiments_13612u.json"
    with open(outpath, "w") as f:
        json.dump(out, f, indent=2, default=lambda o: None if isinstance(o, float) and np.isnan(o) else o)
    print("wrote", outpath)


if __name__ == "__main__":
    main()
