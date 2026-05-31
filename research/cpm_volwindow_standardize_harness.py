#!/usr/bin/env python3
"""
CPM vol-window STANDARDIZATION decision harness (research-only).

Decision: standardize the two volatility lookbacks (currently rank-vol=252 in the
m_faber/rv252 ranker, weight-vol=504 in 1/rv504 inverse-vol weighting) to a SINGLE
window -- both-252 or both-504 -- to reduce degrees of freedom. Everything else at
production (canary 13612U, Faber ranker, K=4, mooex T+1 MOO execution).

Reuses:
  - memo_review2_lookback_detilt_harness.cpm_weights_param  (parametrized vol windows)
  - exec_lag_moo_validation_2026_05_30._segment_returns_conv (mooex T+1 MOO)  [anchor xcheck]
  - cpm_live primitives + perf_metrics

Produces the FULL prod / both-252 / both-504 comparison:
  1. anchor reproduction (prod rank252/wt504 mooex == Sharpe 1.1910 / MaxDD -12.67% / Calmar 1.0615)
  2. clean + ext  Sharpe/Calmar/Martin/MaxDD/CAGR
  3. per-crisis MaxDD (GFC 2008, COVID 2020, 2022) -- do all configs keep crisis catches?
  4. turnover (annualized one-way + per-rebal avg)
  5. EOM-offset stability (Sharpe across EOM..EOM+3, std)  -- execution-cliff sensitivity

Windows: clean 2008-05-30..end; ext 1999-03-10..end (END=2026-05-22).
HONESTY: clean = decision lens; ext = robustness; mooex T+1; per-crisis = point
estimates; single in-sample path. This is a PARSIMONY move (fewer DoF), expected
to cost a little, not a performance upgrade.
"""
from __future__ import annotations
import sys, json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import bull_qqq_live as _bq
if not hasattr(_bq, "_vol_gate_ok"):
    _bq._vol_gate_ok = lambda *a, **k: (True, {})

import exec_lag_moo_validation_2026_05_30 as H
import memo_review2_lookback_detilt_harness as A1
from cpm_live import (
    load_panel, perf_metrics,
    RISKY_UNIVERSE, SAFE_POOL, CANARY_ASSETS, DEFAULT_CASH, COST_BPS_PER_SIDE,
)

CLEAN_START = pd.Timestamp("2008-05-30")
EXT_START   = pd.Timestamp("1999-03-10")
END         = pd.Timestamp("2026-05-22")
ANCHOR = {"sharpe": 1.1910, "maxdd": -0.1267, "calmar": 1.0615}

CFGS = {
    "prod (rank252/wt504)":     (252, 504),
    "both-252 (rank252/wt252)": (252, 252),
    "both-504 (rank504/wt504)": (504, 504),
}

# Paired stationary block bootstrap config (matches paired_bootstrap_pair_vs_continuous.py
# / bootstrap_ci_2026_05_28.py semantics; B raised to 5000 per task).
BOOT_B = 5000
BOOT_BLOCK = 21
BOOT_SEED = 42

CRISES = {
    "GFC_2008":  (pd.Timestamp("2008-05-30"), pd.Timestamp("2009-06-30")),
    "COVID_2020": (pd.Timestamp("2020-02-01"), pd.Timestamp("2020-06-30")),
    "Y2022":     (pd.Timestamp("2022-01-01"), pd.Timestamp("2022-12-31")),
}


# ---------------------------------------------------------------------------
# mooex segment returns with EXPLICIT signal dates (offset support) + turnover.
# Mirrors H._segment_returns_conv mooex branch exactly; offset=0 reproduces it.
# ---------------------------------------------------------------------------
def gen_sig_dates(close, start, end, offset):
    idx = close.index
    monthly = pd.DataFrame({"x": 1}, index=idx).groupby(pd.Grouper(freq="ME")).tail(1)
    pos = {d: i for i, d in enumerate(idx)}
    sigs = []
    for d in monthly.index:
        p = pos[d] + offset
        if 0 <= p < len(idx):
            sigs.append(idx[p])
    lo = start - pd.DateOffset(days=45)
    return sorted({s for s in sigs if lo <= s <= end})


def segment_mooex(close, daily_ret, weight_fn, sigs, start, end,
                  cost_bps, intraday_ret, overnight_ret):
    def apply_from(sd):
        fut = close.index[close.index > sd]
        return fut[0] if len(fut) else None

    hist, prev_w = [], {}
    for i, sd in enumerate(sigs):
        w = weight_fn(sd)
        af = apply_from(sd)
        if af is None:
            continue
        if i + 1 < len(sigs):
            naf = apply_from(sigs[i + 1])
            end_apply = naf if naf is not None else end
        else:
            end_apply = end
        hist.append({"apply_from": af, "end_apply": end_apply, "weights": w, "prev_weights": prev_w})
        prev_w = w

    all_assets = sorted({a for h in hist for a in h["weights"]})
    cols = [a for a in all_assets if a in daily_ret.columns]
    df_w = pd.DataFrame(0.0, index=close.index, columns=cols)
    for h in hist:
        mask = (close.index >= h["apply_from"]) & (close.index < h["end_apply"])
        for a, ww in h["weights"].items():
            if a in df_w.columns:
                df_w.loc[mask, a] = ww
    ret = (df_w[cols] * daily_ret[cols]).sum(axis=1, min_count=1).fillna(0.0)

    n_real, n_fb = 0, 0
    for h in hist:
        af = h["apply_from"]
        if af not in ret.index:
            continue
        ok = True

        def cc(a):
            return daily_ret.at[af, a] if a in daily_ret.columns and pd.notna(daily_ret.at[af, a]) else 0.0

        def intra(a):
            nonlocal ok
            if intraday_ret is not None and a in intraday_ret.columns and \
               af in intraday_ret.index and pd.notna(intraday_ret.at[af, a]):
                return intraday_ret.at[af, a]
            ok = False
            return None

        def on(a):
            nonlocal ok
            if overnight_ret is not None and a in overnight_ret.columns and \
               af in overnight_ret.index and pd.notna(overnight_ret.at[af, a]):
                return overnight_ret.at[af, a]
            ok = False
            return None

        on_c = 0.0
        for a, ww in h["prev_weights"].items():
            if a not in cols:
                continue
            ov = on(a)
            on_c += ww * (ov if ov is not None else 0.0)
        id_c = 0.0
        for a, ww in h["weights"].items():
            if a not in cols:
                continue
            iv = intra(a)
            id_c += ww * (iv if iv is not None else cc(a))
        ret.loc[af] = (1.0 + on_c) * (1.0 + id_c) - 1.0
        if ok:
            n_real += 1
        else:
            n_fb += 1

    # turnover + costs
    turnovers = []
    for i, h in enumerate(hist):
        pw = hist[i - 1]["weights"] if i > 0 else {}
        cw = h["weights"]
        keys = set(cw) | set(pw)
        turnover = sum(abs(cw.get(k, 0.0) - pw.get(k, 0.0)) for k in keys)
        turnovers.append((h["apply_from"], turnover))
        cost = turnover * cost_bps / 10000.0
        if h["apply_from"] in ret.index:
            ret.loc[h["apply_from"]] -= cost

    sel = (ret.index >= start) & (ret.index <= end)
    return ret.loc[sel], (n_real, n_fb), turnovers


# ---------------------------------------------------------------------------
# Paired stationary block bootstrap (same block index drawn for both streams).
# ---------------------------------------------------------------------------
def _metrics_from_array(r, n_years):
    """Sharpe, Calmar, Martin from a 1d np array of daily returns."""
    vol = r.std(ddof=0) * np.sqrt(252)
    sharpe = (r.mean() * 252) / vol if vol > 0 else np.nan
    eq = np.cumprod(1.0 + r)
    total = eq[-1]
    cagr = total ** (1.0 / n_years) - 1.0 if n_years > 0 else np.nan
    rm = np.maximum.accumulate(eq)
    dd = eq / rm - 1.0
    mdd = dd.min()
    calmar = cagr / abs(mdd) if mdd != 0 else np.nan
    ulcer = float(np.sqrt(np.mean(dd ** 2)))
    martin = cagr / ulcer if ulcer > 0 else np.nan
    return sharpe, calmar, martin


def _block_index(n, block, rng):
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


def _summ(arr):
    a = np.asarray(arr)
    lo, hi = float(np.percentile(a, 2.5)), float(np.percentile(a, 97.5))
    return {"mean": float(a.mean()), "ci_lo": lo, "ci_hi": hi,
            "excludes_zero": bool(lo > 0 or hi < 0),
            "p_gt0": float(np.mean(a > 0))}


def paired_bootstrap(series_by_cfg, n_years, pairs):
    """series_by_cfg: dict name -> aligned 1d np array (same dates).
    pairs: list of (A, B) -> compute A minus B delta per resample.
    Returns dict[pairlabel][metric] = summary."""
    names = list(series_by_cfg)
    n = len(series_by_cfg[names[0]])
    rng = np.random.default_rng(BOOT_SEED)
    # accumulate per-config metric draws using the SAME block index each iter
    draws = {nm: {"sharpe": [], "calmar": [], "martin": []} for nm in names}
    for _ in range(BOOT_B):
        idx = _block_index(n, BOOT_BLOCK, rng)
        for nm in names:
            s, c, m = _metrics_from_array(series_by_cfg[nm][idx], n_years)
            draws[nm]["sharpe"].append(s)
            draws[nm]["calmar"].append(c)
            draws[nm]["martin"].append(m)
    out = {}
    for (A, Bn) in pairs:
        lbl = f"{A} - {Bn}"
        out[lbl] = {}
        for mk in ("sharpe", "calmar", "martin"):
            d = np.asarray(draws[A][mk]) - np.asarray(draws[Bn][mk])
            out[lbl][mk] = _summ(d)
    return out


def met(daily, cash):
    m = perf_metrics(daily, cash)
    return {"sharpe": m.get("sharpe"), "cagr": m.get("cagr"),
            "maxdd": m.get("max_drawdown"), "calmar": m.get("calmar"),
            "martin": m.get("martin"), "vol": m.get("vol")}


def win(s, a, b):
    return s.loc[(s.index >= a) & (s.index <= b)]


def crisis_maxdd(ret, a, b):
    sub = win(ret, a, b)
    if len(sub) < 5:
        return None
    eq = (1.0 + sub).cumprod()
    dd = eq / eq.cummax() - 1.0
    return float(dd.min())


def turnover_stats(turnovers, start, end):
    vals = [t for (d, t) in turnovers if start <= d <= end]
    if not vals:
        return {}
    n = len(vals)
    # one-way turnover per rebal -> annualized one-way (12 rebals/yr)
    avg = float(np.mean(vals))
    return {"n_rebal": n, "avg_oneway_per_rebal": avg,
            "annualized_oneway": avg * 12.0}


def main():
    out = {"anchor_target": ANCHOR, "crises": {k: [str(v[0].date()), str(v[1].date())] for k, v in CRISES.items()}}
    base_panel, base_intra, base_over = A1.build_panel_and_exec([])
    cash = base_panel["SHV"].ffill().pct_change().dropna()
    end = min(END, base_panel.index[-1])

    needed = sorted(set(list(RISKY_UNIVERSE) + SAFE_POOL + CANARY_ASSETS + [DEFAULT_CASH]) & set(base_panel.columns))
    close = base_panel[needed]
    daily_ret = close.ffill().pct_change()

    # ---- ANCHOR cross-check via the original H harness path (run_cpm) ----
    cpm_prod_H, dgp = A1.run_cpm(base_panel, base_intra, base_over, list(RISKY_UNIVERSE),
                                 252, 504, EXT_START, end)
    a_clean = met(win(cpm_prod_H, CLEAN_START, end), cash)
    ok = (abs(a_clean["sharpe"] - 1.1910) < 1e-3 and abs(a_clean["maxdd"] + 0.1267) < 1e-3
          and abs(a_clean["calmar"] - 1.0615) < 1e-3)
    out["anchor_repro_H"] = {"clean": a_clean, "ok": bool(ok)}
    print(f"[ANCHOR-H] clean Sharpe={a_clean['sharpe']:.4f} MaxDD={a_clean['maxdd']*100:.2f}% "
          f"Calmar={a_clean['calmar']:.4f}  OK={ok}")
    assert ok, "ANCHOR MISMATCH (H path) -- abort"

    # ---- ANCHOR cross-check via OUR segment_mooex (offset=0) ----
    wf_prod = lambda sd: A1.cpm_weights_param(close, sd, list(RISKY_UNIVERSE), 252, 504)
    sigs0 = gen_sig_dates(close, EXT_START, end, 0)
    ret_ours, fb0, _ = segment_mooex(close, daily_ret, wf_prod, sigs0, EXT_START, end,
                                     COST_BPS_PER_SIDE, base_intra, base_over)
    oc = met(win(ret_ours, CLEAN_START, end), cash)
    ok2 = abs(oc["sharpe"] - 1.1910) < 2e-3 and abs(oc["maxdd"] + 0.1267) < 2e-3
    out["anchor_repro_ours"] = {"clean": oc, "ok": bool(ok2)}
    print(f"[ANCHOR-ours] clean Sharpe={oc['sharpe']:.4f} MaxDD={oc['maxdd']*100:.2f}% "
          f"Calmar={oc['calmar']:.4f}  OK={ok2}")

    # ================= FULL COMPARISON over configs =================
    comp = {}
    clean_series, ext_series = {}, {}
    for name, (rl, wl) in CFGS.items():
        wf = lambda sd, rl=rl, wl=wl: A1.cpm_weights_param(close, sd, list(RISKY_UNIVERSE), rl, wl)
        sigs = gen_sig_dates(close, EXT_START, end, 0)
        ret, fb, turns = segment_mooex(close, daily_ret, wf, sigs, EXT_START, end,
                                       COST_BPS_PER_SIDE, base_intra, base_over)
        clean_series[name] = win(ret, CLEAN_START, end)
        ext_series[name] = win(ret, EXT_START, end)
        clean = met(win(ret, CLEAN_START, end), cash)
        ext = met(win(ret, EXT_START, end), cash)
        per_crisis = {ck: crisis_maxdd(ret, a, b) for ck, (a, b) in CRISES.items()}
        tov = turnover_stats(turns, CLEAN_START, end)

        # EOM-offset stability: Sharpe at EOM..EOM+3 (clean window)
        offs = {}
        for k in range(0, 4):
            sk = gen_sig_dates(close, EXT_START, end, k)
            rk, _, _ = segment_mooex(close, daily_ret, wf, sk, EXT_START, end,
                                     COST_BPS_PER_SIDE, base_intra, base_over)
            offs[f"EOM+{k}"] = met(win(rk, CLEAN_START, end), cash)["sharpe"]
        off_vals = [v for v in offs.values() if v is not None]
        off_std = float(np.std(off_vals, ddof=0)) if off_vals else None
        off_mean = float(np.mean(off_vals)) if off_vals else None
        off_minmax = [float(min(off_vals)), float(max(off_vals))] if off_vals else None

        comp[name] = {"clean": clean, "ext": ext, "per_crisis_maxdd": per_crisis,
                      "turnover": tov, "mooex_coverage": {"real": fb[0], "fallback": fb[1]},
                      "eom_offset_sharpe": offs, "eom_offset_std": off_std,
                      "eom_offset_mean": off_mean, "eom_offset_minmax": off_minmax}
        print(f"\n[{name}]")
        print(f"  clean  Sh={clean['sharpe']:.4f} DD={clean['maxdd']*100:.2f}% Cal={clean['calmar']:.4f} "
              f"Mar={clean['martin']:.4f} CAGR={clean['cagr']*100:.2f}%")
        print(f"  ext    Sh={ext['sharpe']:.4f} DD={ext['maxdd']*100:.2f}% Cal={ext['calmar']:.4f} "
              f"Mar={ext['martin']:.4f} CAGR={ext['cagr']*100:.2f}%")
        print(f"  crisisDD GFC={per_crisis['GFC_2008']*100:.2f}% COVID={per_crisis['COVID_2020']*100:.2f}% "
              f"2022={per_crisis['Y2022']*100:.2f}%")
        print(f"  turnover ann1way={tov.get('annualized_oneway',float('nan'))*100:.1f}% "
              f"perRebal={tov.get('avg_oneway_per_rebal',float('nan'))*100:.1f}%")
        print(f"  EOMoffset Sh {['%.3f'%offs[f'EOM+{k}'] for k in range(4)]} std={off_std:.4f}")

    out["comparison"] = comp

    # ================= PAIRED BLOCK BOOTSTRAP =================
    short = {"prod (rank252/wt504)": "prod", "both-252 (rank252/wt252)": "both-252",
             "both-504 (rank504/wt504)": "both-504"}
    pairs = [("both-252", "prod"), ("both-504", "prod"), ("both-252", "both-504")]
    boot = {"meta": {"B": BOOT_B, "block": BOOT_BLOCK, "seed": BOOT_SEED,
                     "conv": "mooex", "cost_bps": COST_BPS_PER_SIDE}}
    for wlabel, series_map in (("clean", clean_series), ("ext", ext_series)):
        aligned = {short[k]: v for k, v in series_map.items()}
        common = None
        for v in aligned.values():
            common = v.index if common is None else common.intersection(v.index)
        arrs = {nm: v.reindex(common).values for nm, v in aligned.items()}
        n_years = (common[-1] - common[0]).days / 365.25
        print(f"\nBootstrapping [{wlabel}] n={len(common)} {n_years:.2f}y B={BOOT_B} block={BOOT_BLOCK}...")
        boot[wlabel] = paired_bootstrap(arrs, n_years, pairs)
        for lbl, mm in boot[wlabel].items():
            for mk in ("sharpe", "calmar", "martin"):
                s = mm[mk]
                flag = "EXCLUDES 0" if s["excludes_zero"] else "includes 0"
                print(f"  [{wlabel}] {lbl:22s} {mk:7s} d={s['mean']:+.4f} "
                      f"CI[{s['ci_lo']:+.4f},{s['ci_hi']:+.4f}] {flag}")
    out["bootstrap"] = boot

    outp = Path(__file__).resolve().parent / "cpm_volwindow_standardize_findings.json"
    outp.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nWrote {outp}")
    return out


if __name__ == "__main__":
    main()
