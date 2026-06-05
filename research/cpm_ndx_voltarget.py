# -*- coding: utf-8 -*-
"""NDX sleeve: does MONTHLY IMPLEMENTABLE VOLATILITY TARGETING (vol-scaled risky
exposure) cut the -31% MaxDD WITHOUT proportional Sharpe/CAGR loss -- and does it
IMPROVE Sharpe/Sortino (the momentum vol-scaling literature result), net of the
extra turnover it churns and out-of-sample?

Analyst role. Read-only re production (ndx_sleeve_live.py / prod / memo NOT
edited). Writes only research/cpm_ndx_voltarget_findings.md (+ .json). No commit.

LITERATURE: Barroso-Santa-Clara 2015, Daniel-Moskowitz 2016, Moreira-Muir 2017,
Harvey 2018 -- constant-vol scaling uniquely cuts MOMENTUM crashes + MaxDD and
often lifts Sharpe. Bongaerts 2020 warns the famous versions have ex-post-k
LOOK-AHEAD bias + high turnover -> we use IMPLEMENTABLE scaling: a FIXED a-priori
target, realized vol from trailing daily returns LAGGED to the signal date, plus
a conditional (lower-turnover) variant. The NDX -31% DD is risk-ON single-stock
vol dispersion (the gate already handles crises -- per-crisis DDs are flat), which
continuous vol-scaling targets directly.

MECHANISM (keeps prod selection + EW WITHIN the risky block):
  exposure_t = clip(target_vol / realized_vol_{t-lag}, 0, CAP)
  risky weights = (prod EW risky block) * exposure_t
  remainder (risky_fraction*(1-exposure_t)) -> safe (SHV/IEF best-of-safe)
  CAP>1 lets calm months lever up (safe weight goes negative = borrow at safe yld).
realized_vol uses daily returns through sig_d (the month-end signal date); since
execution is T+1 MOO this is properly lagged -- NO look-ahead. target_vol is FIXED
a-priori (NOT calibrated ex-post over the sample -- that is the Bongaerts bias);
we report the ACHIEVED unconditional vol + avg exposure, and sweep target/window
/cap/vol-choice as sensitivity (not optimization).

A-PRIORI TARGET CHOICE: a concentrated 5-name single-stock momentum basket runs
~30% annualized typical vol (vs ~12% for the diversified L/S momentum FACTOR in
Barroso). We set the PRIMARY a-priori target_vol = 0.30 for basket-vol so avg
exposure sits near 1 (de-risk in spikes, not a permanent de-gross). The index/QQQ
-vol variant uses target 0.22 (QQQ runs lower vol than the 5-name basket). These
are round a-priori anchors, NOT swept-then-picked; sensitivity reported below.

ENGINE REUSE: monkeypatch ndx_sleeve_live.compute_ndx_weights, then call the
UNMODIFIED ndx_sleeve_live.run_ndx_backtest (gate TIP+SPY-trend+SPY-RV, safe
rotation, T+1 MOO, 10bps/side, delisting haircut, PIT membership all identical).
Only the total risky exposure is scaled. Reuses the prior NDX harness helpers
(_gate_and_candidates, _partial_safe_pack, full_metrics, crisis_metrics,
annual_turnover, walk_forward, win) and the B=2000 block=21 seed=42 paired block
bootstrap.

CONFIGS (NDX sleeve; gate/safe/T+1/10bps/delist/PIT fixed; EW within risky):
  PROD            momentum top-5 EW (no scaling)                       (baseline)
  DERISK          basket-vol scale, CAP 1.0 (de-risk only)   PRIMARY -- DD control
  SYM             basket-vol scale, CAP 1.5 (lever up in calm) literature Sharpe
  CONDITIONAL     basket-vol, de-risk only when vol>trailing median   low-turnover
  DERISK_IDX      QQQ/SPY index-vol scale, CAP 1.0          vol-choice variant
Vol window 60d PRIMARY; 20d as sensitivity. target/cap/window sweeps reported.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cpm_live import load_panel
import ndx_sleeve_live as ndx
from research.cpm_bootstrap_multimetric import paired_block_bootstrap_mm
from research.cpm_ndx_minvar_cvar import (
    _gate_and_candidates,
    _partial_safe_pack,
    full_metrics,
    crisis_metrics,
    annual_turnover,
    walk_forward,
    win,
    EXT_START,
    CLEAN_START,
    END,
)

SPY = ndx.SPY_TICKER
TARGET_BASKET = 0.30      # a-priori annualized vol target, basket-vol configs
TARGET_INDEX = 0.22       # a-priori annualized vol target, index(QQQ)-vol config
WIN_PRIMARY = 60          # trailing daily-return window for realized vol
MED_LOOKBACK = 504        # trailing window for the conditional median threshold


# --------------------------- realized-vol helpers ---------------------------
def _basket_vol(ndx_panel, sel, sig_d, window):
    """Annualized realized vol of the EW basket of `sel`, trailing `window` daily
    returns through sig_d (properly lagged vs T+1 execution). None if degenerate."""
    px = ndx_panel[sel].loc[:sig_d].ffill()
    rets = px.pct_change().dropna(how="all")
    basket = rets.mean(axis=1).dropna().tail(window)
    if len(basket) < max(10, window // 2):
        return None
    v = float(basket.std() * np.sqrt(252))
    return v if np.isfinite(v) and v > 0 else None


def _index_vol(cpm_panel, sig_d, window):
    """Annualized realized vol of QQQ (fallback SPY) trailing `window` days."""
    for tk in ("QQQ", SPY):
        if tk not in cpm_panel.columns:
            continue
        s = cpm_panel[tk].loc[:sig_d].ffill().pct_change().dropna().tail(window)
        if len(s) >= max(10, window // 2):
            v = float(s.std() * np.sqrt(252))
            if np.isfinite(v) and v > 0:
                return v
    return None


def _basket_vol_median(ndx_panel, sel, sig_d, window, med_lb=MED_LOOKBACK):
    """Trailing median of the rolling `window`-day basket vol over the last
    `med_lb` days through sig_d -- the conditional de-risk threshold."""
    px = ndx_panel[sel].loc[:sig_d].ffill()
    rets = px.pct_change().dropna(how="all")
    basket = rets.mean(axis=1).dropna().tail(med_lb)
    if len(basket) < window + 20:
        return None
    roll = basket.rolling(window).std() * np.sqrt(252)
    roll = roll.dropna()
    if roll.empty:
        return None
    return float(roll.median())


# ----------------------------- config weight fn -----------------------------
def make_compute(config, target, cap, window, log):
    """Drop-in replacement for ndx_sleeve_live.compute_ndx_weights.

    PROD selection (momentum top-5) + EW within risky; the TOTAL risky exposure
    is scaled by exposure_t and the freed/borrowed weight flows to/from safe.
    `log` collects per-ON-month (sig_d, regime, realized_vol, exposure)."""

    def compute(cpm_panel, ndx_panel, sig_d):
        status, safe, cands = _gate_and_candidates(cpm_panel, ndx_panel, sig_d)
        if status == "OFF":
            return ({safe: 1.0}, "GATE_OFF", {"selected": []})
        if status == "PROXY":
            return ({SPY: 1.0}, "NDX_FALLBACK_SPY", {"selected": [SPY]})
        if not cands:
            return ({safe: 1.0}, "NDX_NO_POS", {"selected": []})

        names = [t for t, _ in cands]
        K = 5
        sel = names[:K]
        rw = {t: 1.0 / len(sel) for t in sel}
        base = _partial_safe_pack(rw, len(sel), safe, K)  # risky sum=risky_frac
        risky_fraction = min(len(sel), K) / K

        if config == "PROD":
            log.append({"sig_d": str(sig_d.date()), "rv": None, "exposure": 1.0})
            return (base, "NDX_PROD", {"selected": sel})

        # realized vol (lagged through sig_d)
        if config == "DERISK_IDX":
            rv = _index_vol(cpm_panel, sig_d, window)
        else:
            rv = _basket_vol(ndx_panel, sel, sig_d, window)

        if rv is None:
            exposure = 1.0                                  # warmup -> unscaled
        elif config == "CONDITIONAL":
            thr = _basket_vol_median(ndx_panel, sel, sig_d, window)
            if thr is None or rv <= thr:
                exposure = 1.0                              # calm -> unscaled
            else:
                exposure = float(np.clip(target / rv, 0.0, 1.0))
        else:
            exposure = float(np.clip(target / rv, 0.0, cap))

        out = {t: base[t] * exposure for t in sel}
        freed = risky_fraction * (1.0 - exposure)           # >0 derisk, <0 lever
        safe_w = base.get(safe, 0.0) + freed
        if abs(safe_w) > 1e-9:
            out[safe] = out.get(safe, 0.0) + safe_w
        log.append({"sig_d": str(sig_d.date()), "rv": rv, "exposure": exposure})
        return (out, f"NDX_{config}", {"selected": sel})

    return compute


def run_config(cpm_panel, ndx_panel, config, target, cap, window):
    log = []
    orig = ndx.compute_ndx_weights
    ndx.compute_ndx_weights = make_compute(config, target, cap, window, log)
    try:
        r, hist = ndx.run_ndx_backtest(cpm_panel, ndx_panel, EXT_START,
                                       min(END, cpm_panel.index[-1]))
    finally:
        ndx.compute_ndx_weights = orig
    return r, hist, log


def _exposure_stats(log, clean_start):
    """Avg exposure + fraction of de-risked / levered ON-months (clean window)."""
    cs = pd.Timestamp(clean_start)
    on = [e for e in log if e["rv"] is not None
          and pd.Timestamp(e["sig_d"]) >= cs]
    if not on:
        return {"n_on": 0, "avg_exposure": float("nan"),
                "frac_derisk": float("nan"), "frac_lever": float("nan"),
                "avg_rv": float("nan")}
    exps = np.array([e["exposure"] for e in on])
    rvs = np.array([e["rv"] for e in on])
    return {
        "n_on": len(on),
        "avg_exposure": float(exps.mean()),
        "frac_derisk": float((exps < 0.999).mean()),
        "frac_lever": float((exps > 1.001).mean()),
        "avg_rv": float(rvs.mean()),
    }


def main():
    panel = load_panel(start=EXT_START, end=END)
    end = min(END, panel.index[-1])
    ndx_panel = ndx.load_ndx_panel()
    cash = panel["SHV"].ffill().pct_change().dropna()

    # (config, target, cap, window)
    specs = {
        "PROD":        ("PROD",        TARGET_BASKET, 1.0, WIN_PRIMARY),
        "DERISK":      ("DERISK",      TARGET_BASKET, 1.0, WIN_PRIMARY),
        "SYM":         ("SYM",         TARGET_BASKET, 1.5, WIN_PRIMARY),
        "CONDITIONAL": ("CONDITIONAL", TARGET_BASKET, 1.0, WIN_PRIMARY),
        "DERISK_IDX":  ("DERISK_IDX",  TARGET_INDEX,  1.0, WIN_PRIMARY),
    }

    series_clean, series_ext, results = {}, {}, {}
    for name, (cfg, tgt, cap, w) in specs.items():
        print(f"running {name} ...", file=sys.stderr)
        r, hist, log = run_config(panel, ndx_panel, cfg, tgt, cap, w)
        sc = win(r, CLEAN_START, end)
        se = win(r, EXT_START, end)
        series_clean[name] = sc
        series_ext[name] = se
        results[name] = {
            "clean": full_metrics(sc, cash),
            "ext": full_metrics(se, cash),
            "crisis": crisis_metrics(se),
            "turnover_ann": annual_turnover(hist, CLEAN_START),
            "exposure": _exposure_stats(log, CLEAN_START),
            "spec": {"target": tgt, "cap": cap, "window": w},
        }
        m = results[name]["clean"]
        ex = results[name]["exposure"]
        print(f"  {name}: clean Sharpe={m['Sharpe']:.4f} Sortino={m['Sortino']:.4f} "
              f"CVaR={m['CVaR_ratio']:.3f} MaxDD={m['MaxDD']:.4f} CAGR={m['CAGR']:.4f} "
              f"vol={m['vol']:.4f} TO={results[name]['turnover_ann']:.2f} "
              f"avgExp={ex['avg_exposure']:.3f}", file=sys.stderr)

    # ---- sensitivity: target x window for DERISK (basket) + cap sweep --------
    sens = {}
    for tgt in (0.25, 0.30, 0.35):
        for w in (20, 60):
            r, hist, log = run_config(panel, ndx_panel, "DERISK", tgt, 1.0, w)
            sc = win(r, CLEAN_START, end)
            key = f"DERISK_t{int(tgt*100)}_w{w}"
            sens[key] = {**full_metrics(sc, cash),
                         "turnover_ann": annual_turnover(hist, CLEAN_START),
                         "avg_exposure": _exposure_stats(log, CLEAN_START)["avg_exposure"]}
            print(f"  sens {key}: Sharpe={sens[key]['Sharpe']:.4f} "
                  f"MaxDD={sens[key]['MaxDD']:.4f} avgExp={sens[key]['avg_exposure']:.3f}",
                  file=sys.stderr)
    for cap in (1.25, 1.5, 2.0):
        r, hist, log = run_config(panel, ndx_panel, "SYM", TARGET_BASKET, cap, WIN_PRIMARY)
        sc = win(r, CLEAN_START, end)
        key = f"SYM_cap{int(cap*100)}"
        sens[key] = {**full_metrics(sc, cash),
                     "turnover_ann": annual_turnover(hist, CLEAN_START),
                     "avg_exposure": _exposure_stats(log, CLEAN_START)["avg_exposure"]}
        print(f"  sens {key}: Sharpe={sens[key]['Sharpe']:.4f} "
              f"MaxDD={sens[key]['MaxDD']:.4f} avgExp={sens[key]['avg_exposure']:.3f}",
              file=sys.stderr)

    # --------------------------- bootstrap vs PROD ---------------------------
    boot = {}
    base = series_clean["PROD"]
    for name in specs:
        if name == "PROD":
            continue
        print(f"bootstrap {name} vs PROD ...", file=sys.stderr)
        boot[name] = paired_block_bootstrap_mm(series_clean[name], base, cash,
                                               B=2000, block=21, seed=42)

    # ---- walk-forward: any config with a significant clean bootstrap diff OR
    #      a clean Sharpe point estimate beating PROD --------------------------
    wf = {}
    for name in specs:
        if name == "PROD":
            continue
        bb = boot[name]
        sig = any(bb[m]["p_gt0"] >= 0.95 or bb[m]["p_gt0"] <= 0.05
                  for m in ("dSharpe", "dSortino", "dCVaR"))
        if sig or results[name]["clean"]["Sharpe"] > results["PROD"]["clean"]["Sharpe"]:
            wf[name] = walk_forward(series_clean[name], cash, 3)
    wf["PROD"] = walk_forward(base, cash, 3)

    out = {
        "anchor_note": ("PROD reproduces clean Sharpe ~1.28, MaxDD ~-31.4%. Engine "
                        "identical across configs; only total risky exposure scaled. "
                        "Implementable: fixed a-priori target, lagged realized vol, "
                        "capped leverage -- NO ex-post k calibration."),
        "a_priori_targets": {"basket": TARGET_BASKET, "index": TARGET_INDEX,
                             "window_primary": WIN_PRIMARY},
        "window": {"clean": [str(CLEAN_START.date()), str(end.date())],
                   "ext": [str(EXT_START.date()), str(end.date())]},
        "results": results,
        "sensitivity": sens,
        "bootstrap_vs_PROD": boot,
        "walk_forward": wf,
    }
    op = ROOT / "research" / "cpm_ndx_voltarget_findings.json"
    op.write_text(json.dumps(out, indent=2, default=float))
    print("WROTE", op, file=sys.stderr)
    return out


if __name__ == "__main__":
    main()
