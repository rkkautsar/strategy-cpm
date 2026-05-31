# -*- coding: utf-8 -*-
"""Analyst recompute (read-only re production; writes research/ only; NO prod/memo
edits; NO commit).

GOAL: move the CPM EXTENDED ("ext") window from the old QQQ-inception convention
floor 1999-03-10 (27y) to the engine's TRUE reduced-universe data floor
1995-01-31 (~31y), and recompute the FULL ext number set on that new floor.

Why this is valid (from research/cpm_ext_crises_findings.md): the production
engine `cpm_live.compute_target_weights` ALREADY operates reduced-universe (the
`avail` filter drops missing/NaN assets from ranking), so the continuous curve
runs from 1995-01-31 with no convention change to the engine. VNQ (proxy 1996-05)
is an often-held asset (47.8% of risk-on months) but NEVER bound the start; the
1999-03 floor was a presentation convention at QQQ ETF inception, not a data
floor.

Convention (every table): T+1 MOO exact ("mooex", real auto_adjust opens where
they exist, close-to-close fallback pre-ETF), 10 bps/side post-cost, monthly
month-end signal. CPM = production `compute_target_weights` (HYG-OR-TIP canary,
top-4 inverse-vol, strict-4 partial-safe). No vol gate on the CPM sleeve.

Harnesses reused (production-faithful, anchor-gated):
  - exec_lag_moo_validation_2026_05_30 (H): mooex segment engine + real opens.
  - cpm_headline_gaps_compute (V): drawdown-episode detector + block bootstrap.
  - memo_fix_numbers (MF): production-equivalent cpm_wf for the ranker lift.
  - cpm_factorial_faithful_aaa (FA): 2^6 CPM factorial (memo Section 6, faithful
    AAA all-OFF baseline) cell fn + effects + ladder.

ANCHOR GATE (must reproduce EXACTLY before any ext-1995 number is trusted):
  clean (2008-05-30..) Sharpe 1.1910 / MaxDD -12.67% / Calmar 1.0615
  ext-1999 (1999-03-10..) Sharpe 1.2142 / MaxDD -15.93% / Calmar 0.8608

Writes research/cpm_ext_1995_recompute_findings.md (+ .json).
"""
from __future__ import annotations
import sys, json, itertools
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

import exec_lag_moo_validation_2026_05_30 as H
import cpm_headline_gaps_compute as V
import memo_fix_numbers as MF
import cpm_factorial_faithful_aaa as FA  # memo Section-6 2^6 factorial (faithful AAA baseline)
from cpm_live import (
    load_panel, perf_metrics, compute_target_weights,
    RISKY_UNIVERSE, SAFE_POOL, CANARY_ASSETS, DEFAULT_CASH, COST_BPS_PER_SIDE,
)

CONV = "mooex"
COST = COST_BPS_PER_SIDE

CLEAN_START = pd.Timestamp("2008-05-30")
EXT1999_START = pd.Timestamp("1999-03-10")   # old convention floor (anchor)
EXT1995_START = pd.Timestamp("1995-01-31")   # NEW engine reduced-universe floor
END = pd.Timestamp("2026-05-22")

CPM_UNIV = ["QQQ", "SPHQ", "EFA", "EEM", "VNQ", "GLD", "TLT", "DBC"]
SAFE_SET = set(SAFE_POOL) | {DEFAULT_CASH}

# Live ETF inception (from cpm_ext_extension_feasibility / cpm_ext_crises).
LIVE_INCEPTION = {
    "QQQ": "1999-03-10", "SPHQ": "2005-12-06", "EFA": "2001-08-14",
    "EEM": "2003-04-07", "VNQ": "2004-09-23", "GLD": "2004-11-18",
    "TLT": "2002-07-22", "DBC": "2006-02-03",
    "HYG": "2007-04-11", "TIP": "2003-12-05",
    "SHV": "2007-01-11", "IEF": "2002-07-22",
}

# Crisis trough-search windows (deepest continuous-curve episode troughing within).
CRISES = {
    "LTCM":    ("1998-08-01", "1998-12-31"),
    "Dot-com": ("2000-03-01", "2002-12-31"),
    "GFC":     ("2007-10-01", "2009-06-30"),
    "COVID":   ("2020-02-01", "2020-12-31"),
    "2022":    ("2021-11-01", "2023-06-30"),
}
CRISIS_MID = {  # window midpoint for live/8 coverage call
    "LTCM": "1998-10-16", "Dot-com": "2001-07-31", "GFC": "2008-08-15",
    "COVID": "2020-04-01", "2022": "2022-06-30",
}

# Old ext-1999 headline (memo 5.1) for the delta map.
OLD_EXT = {"sharpe": 1.2142, "cagr": 13.71, "vol": 11.09, "maxdd": -15.93,
           "calmar": 0.8608, "martin": 3.8201, "ulcer": 3.59, "excess_sharpe": 1.0062}


def met8(s, cash):
    m = perf_metrics(s, cash)
    return {"sharpe": m.get("sharpe"), "cagr": m.get("cagr"), "vol": m.get("vol"),
            "maxdd": m.get("max_drawdown"), "calmar": m.get("calmar"),
            "martin": m.get("martin"), "ulcer": m.get("ulcer"),
            "excess_sharpe": m.get("excess_sharpe")}


def win(s, a, b):
    return s.loc[(s.index >= a) & (s.index <= b)]


def block_index(n, block, rng):
    n_blocks = (n // block) + 1
    parts = []
    for _ in range(n_blocks):
        st = int(rng.integers(0, n))
        e = st + block
        if e <= n:
            parts.append(np.arange(st, e))
        else:
            parts.append(np.concatenate([np.arange(st, n), np.arange(0, e - n)]))
    return np.concatenate(parts)[:n]


def sharpe_arr(r):
    sd = r.std()
    return (r.mean() / sd * np.sqrt(252)) if sd > 0 else np.nan


def block_bootstrap_sharpe(daily, B=2000, block=21, seed=42):
    r = daily.dropna().values
    n = len(r)
    rng = np.random.default_rng(seed)
    out = np.empty(B)
    for b in range(B):
        idx = block_index(n, block, rng)
        out[b] = sharpe_arr(r[idx])
    out = out[~np.isnan(out)]
    return {"point": float(sharpe_arr(r)), "low": float(np.percentile(out, 2.5)),
            "median": float(np.percentile(out, 50)), "high": float(np.percentile(out, 97.5)),
            "B": B, "block": block, "seed": seed, "n_eff": int(len(out))}


def paired_bootstrap_sharpe(base_r, alt_r, B=2000, block=21, seed=42):
    """diff = base - alt Sharpe; base = vol-Faber (production)."""
    base_r = np.asarray(base_r); alt_r = np.asarray(alt_r)
    n = len(base_r)
    rng = np.random.default_rng(seed)
    ds = np.empty(B)
    for b in range(B):
        idx = block_index(n, block, rng)
        ds[b] = sharpe_arr(base_r[idx]) - sharpe_arr(alt_r[idx])
    ds = ds[~np.isnan(ds)]
    lo, hi = float(np.percentile(ds, 2.5)), float(np.percentile(ds, 97.5))
    return {"point_diff": float(sharpe_arr(base_r) - sharpe_arr(alt_r)),
            "p_base_beats": float(np.mean(ds > 0)), "ci_lo": lo, "ci_hi": hi,
            "excludes_zero": bool(lo > 0 or hi < 0), "B": B, "block": block, "seed": seed}


def turnover_stats(close, wf, start, end):
    monthly_idx = (pd.DataFrame({"x": 1}, index=close.index)
                   .groupby(pd.Grouper(freq="ME")).tail(1))
    sigs = monthly_idx.index[(monthly_idx.index >= start) & (monthly_idx.index <= end)].tolist()
    prev = {}; to_sum = 0.0; n_rebal = 0; n_safe = 0
    for sd in sigs:
        w = wf(sd)
        keys = set(w) | set(prev)
        to_sum += sum(abs(w.get(k, 0.0) - prev.get(k, 0.0)) for k in keys)
        n_rebal += 1
        risky_w = sum(v for k, v in w.items() if k not in SAFE_SET)
        if risky_w < 1e-9:
            n_safe += 1
        prev = w
    n_years = (sigs[-1] - sigs[0]).days / 365.25 if len(sigs) > 1 else 1.0
    return {"annual_oneway_turnover": 0.5 * to_sum / n_years, "n_rebal": n_rebal,
            "n_months_fully_safe": n_safe,
            "pct_months_fully_safe": 100.0 * n_safe / n_rebal if n_rebal else float("nan"),
            "first_sig": str(sigs[0].date()) if sigs else None,
            "last_sig": str(sigs[-1].date()) if sigs else None}


def concentration(close, wf, start, end):
    """Per-asset share of applied risky daily weight over [start,end]."""
    monthly_idx = (pd.DataFrame({"x": 1}, index=close.index)
                   .groupby(pd.Grouper(freq="ME")).tail(1))
    sigs = monthly_idx.index[(monthly_idx.index >= start) & (monthly_idx.index <= end)].tolist()
    hist = []
    for i, sd in enumerate(sigs):
        w = wf(sd)
        fut = close.index[close.index > sd]
        if len(fut) < 1:
            continue
        af = fut[0]
        if i + 1 < len(sigs):
            nf = close.index[close.index > sigs[i + 1]]
            ea = nf[0] if len(nf) >= 1 else end
        else:
            ea = end
        hist.append((af, ea, w))
    assets = sorted({a for _, _, w in hist for a in w})
    dfw = pd.DataFrame(0.0, index=close.index, columns=assets)
    for af, ea, w in hist:
        mask = (close.index >= af) & (close.index < ea)
        for a, ww in w.items():
            dfw.loc[mask, a] = ww
    dfw = dfw.loc[(dfw.index >= start) & (dfw.index <= end)]
    risky = [a for a in CPM_UNIV if a in dfw.columns]
    tot = dfw[risky].values.sum()
    shares = {a: float(dfw[a].sum() / tot) if tot > 0 else 0.0 for a in risky}
    ordered = sorted(shares.items(), key=lambda x: -x[1])
    top1 = ordered[0] if ordered else (None, 0.0)
    top3 = sum(v for _, v in ordered[:3])
    return {"shares": shares, "ordered": ordered, "top_holding": top1,
            "top3_share": top3}


def live_coverage(mid):
    mid = pd.Timestamp(mid)
    live = [t for t in CPM_UNIV if pd.Timestamp(LIVE_INCEPTION[t]) <= mid]
    return len(live), live


def main():
    panel = load_panel(start=EXT1995_START, end=END)
    end = min(END, panel.index[-1])
    cash = panel["SHV"].ffill().pct_change().dropna()
    od, cy = H.load_open_close()
    intraday = (cy / od - 1.0).reindex(panel.index)
    overnight = (od / cy.shift(1) - 1.0).reindex(panel.index)

    cols = sorted(set(RISKY_UNIVERSE + SAFE_POOL + CANARY_ASSETS + [DEFAULT_CASH]) & set(panel.columns))
    close = panel[cols]
    daily = close.ffill().pct_change()

    print(f"Panel {panel.index[0].date()} -> {end.date()} ({len(panel)} rows)")

    # ============ CPM continuous curve from the new 1995 floor ============
    cpm_full, fb = H.cpm_sleeve_conv(panel, intraday, overnight, EXT1995_START, end, CONV)
    cpm_full = cpm_full.dropna()
    first_valid = cpm_full.index[0]
    print(f"CPM mooex curve {first_valid.date()} -> {cpm_full.index[-1].date()} "
          f"({len(cpm_full)} days); real/fallback rebal = {fb}")

    clean = win(cpm_full, CLEAN_START, end)
    ext99_on95 = win(cpm_full, EXT1999_START, end)  # old window, properly-warmed panel
    ext95 = win(cpm_full, EXT1995_START, end)

    mc = met8(clean, cash)
    me99_on95 = met8(ext99_on95, cash)
    me95 = met8(ext95, cash)

    # ---- ENGINE-UNCHANGED CHECK: reproduce the OLD ext-1999 anchor (1.2142) on the
    # OLD warmup-truncated panel (load start=1999-03-10 -> ~1.25y pre-signal history).
    # The old memo ext figure was computed on that truncated-warmup panel. On the
    # properly-warmed 1995 panel the same window re-slices to ~1.2109 (full 2y warmup).
    panel99 = load_panel(start=EXT1999_START, end=END)
    end99 = min(END, panel99.index[-1])
    intr99 = (cy / od - 1.0).reindex(panel99.index)
    ov99 = (od / cy.shift(1) - 1.0).reindex(panel99.index)
    cpm99, fb99 = H.cpm_sleeve_conv(panel99, intr99, ov99, EXT1999_START, end99, CONV)
    cpm99 = cpm99.dropna()
    me99_old = met8(win(cpm99, EXT1999_START, end99), cash)

    # ---- ANCHOR GATE ----
    anchor_clean_ok = (abs(mc["sharpe"] - 1.1910) < 1e-3 and
                       abs(mc["maxdd"] * 100 + 12.67) < 0.05 and
                       abs(mc["calmar"] - 1.0615) < 5e-3)
    engine_ext99_ok = (abs(me99_old["sharpe"] - 1.2142) < 1e-3 and
                       abs(me99_old["maxdd"] * 100 + 15.93) < 0.05 and
                       abs(me99_old["calmar"] - 0.8608) < 5e-3)
    print("\n=== ANCHOR GATE ===")
    print(f"clean (1995 panel): Sharpe={mc['sharpe']:.4f} MaxDD={mc['maxdd']*100:.2f}% "
          f"Calmar={mc['calmar']:.4f} -> {'OK' if anchor_clean_ok else 'MISMATCH'} "
          f"(expect 1.1910/-12.67%/1.0615)")
    print(f"ext-1999 ENGINE CHECK (1999 panel): Sharpe={me99_old['sharpe']:.4f} "
          f"MaxDD={me99_old['maxdd']*100:.2f}% Calmar={me99_old['calmar']:.4f} "
          f"-> {'OK' if engine_ext99_ok else 'MISMATCH'} (expect 1.2142/-15.93%/0.8608)")
    print(f"ext-1999 re-slice on 1995 panel (full warmup): Sharpe={me99_on95['sharpe']:.4f} "
          f"Calmar={me99_on95['calmar']:.4f}")
    if not (anchor_clean_ok and engine_ext99_ok):
        print("ANCHOR FAIL -- aborting.")
        sys.exit(1)
    print(f"NEW ext-1995: Sharpe={me95['sharpe']:.4f} CAGR={me95['cagr']*100:.2f}% "
          f"Vol={me95['vol']*100:.2f}% MaxDD={me95['maxdd']*100:.2f}% Calmar={me95['calmar']:.4f} "
          f"Martin={me95['martin']:.4f} Ulcer={me95['ulcer']*100:.2f}% "
          f"ExSh={me95['excess_sharpe']:.4f}")

    ext95_years = (ext95.index[-1] - ext95.index[0]).days / 365.25

    out = {"meta": {
        "conv": CONV, "cost_bps": COST,
        "panel_start": str(panel.index[0].date()), "end": str(end.date()),
        "new_ext_start": str(EXT1995_START.date()),
        "first_valid_curve_date": str(first_valid.date()),
        "ext1995_window_years": round(ext95_years, 2),
        "old_ext_start": str(EXT1999_START.date()),
        "clean_start": str(CLEAN_START.date()),
        "mooex_real_fallback_rebal": list(fb),
        "engine": "cpm_live.compute_target_weights (reduced-universe avail filter)",
    }}

    out["anchor_gate"] = {
        "clean": {**mc, "ok": anchor_clean_ok, "expect": [1.1910, -12.67, 1.0615]},
        "ext1999_engine_check_old_panel": {**me99_old, "ok": engine_ext99_ok,
                                           "expect": [1.2142, -15.93, 0.8608]},
        "ext1999_reslice_on_1995_panel": me99_on95,
    }

    # ============ ITEM 1: HEADLINE ext-1995 + delta map ============
    out["headline"] = {"clean": mc, "ext1999_old_panel": me99_old,
                       "ext1999_on_1995_panel": me99_on95, "ext1995": me95}
    delta = {}
    for k in OLD_EXT:
        newv = me95[k] * (100 if k in ("cagr", "vol", "ulcer") else 1)
        if k == "maxdd":
            newv = me95[k] * 100
        delta[k] = {"old_ext1999": OLD_EXT[k], "new_ext1995": round(newv, 4),
                    "delta": round(newv - OLD_EXT[k], 4)}
    out["headline_delta_old1999_to_new1995"] = delta

    # ============ ITEM 2: CRISIS table (continuous curve) ============
    eq_full = (1.0 + cpm_full).cumprod()
    eps = V.drawdown_episodes(eq_full, min_depth=0.04)
    crisis = {}
    for nm, (lo, hi) in CRISES.items():
        e = V.find_episode(eps, lo, hi)
        nlive, livelist = live_coverage(CRISIS_MID[nm])
        if e is None:
            crisis[nm] = {"episode": None, "n_live": nlive, "live": livelist}
            continue
        rec = e["recovery"]
        crisis[nm] = {
            "peak": str(e["peak"].date()), "trough": str(e["trough"].date()),
            "depth_pct": round(e["depth"] * 100, 2),
            "recovery": str(rec.date()) if rec is not None else None,
            "peak_to_trough_days": (e["trough"] - e["peak"]).days,
            "trough_to_recovery_days": ((rec - e["trough"]).days if rec is not None else None),
            "recovered": e["recovered"],
            "n_live": nlive, "live": livelist,
        }
    out["crisis"] = crisis
    print("\n=== CRISIS (continuous 1995 curve) ===")
    for nm in CRISES:
        c = crisis[nm]
        if c.get("peak"):
            print(f"  {nm:<8} {c['peak']}->{c['trough']} {c['depth_pct']:.2f}% rec {c['recovery']} "
                  f"(+{c['trough_to_recovery_days']}d) live {c['n_live']}/8")

    # ============ ITEM 5: TURNOVER + fully-safe ============
    prod_wf = lambda sd: compute_target_weights(close, sd)[0]
    turn = {}
    for wl, st in [("clean", CLEAN_START), ("ext1999", EXT1999_START), ("ext1995", EXT1995_START)]:
        turn[wl] = turnover_stats(close, prod_wf, st, end)
    out["turnover"] = turn
    print("\n=== TURNOVER ===")
    for wl in turn:
        t = turn[wl]
        print(f"  {wl:<8} oneway/yr={t['annual_oneway_turnover']:.3f} "
              f"fully-safe={t['pct_months_fully_safe']:.1f}% ({t['n_months_fully_safe']}/{t['n_rebal']})")

    # ============ ITEM 6: CONCENTRATION ext-1995 ============
    conc = {}
    for wl, st in [("clean", CLEAN_START), ("ext1999", EXT1999_START), ("ext1995", EXT1995_START)]:
        conc[wl] = concentration(close, prod_wf, st, end)
    out["concentration"] = conc
    print("\n=== CONCENTRATION ext-1995 ===")
    th = conc["ext1995"]["top_holding"]
    print(f"  top holding {th[0]} {th[1]*100:.1f}% | top-3 {conc['ext1995']['top3_share']*100:.1f}%")

    # ============ ITEM 7: BOOTSTRAP CI on ext-1995 Sharpe ============
    boot95 = block_bootstrap_sharpe(ext95, B=2000, block=21, seed=42)
    boot_clean = block_bootstrap_sharpe(clean, B=2000, block=21, seed=42)
    out["bootstrap_ext1995_sharpe"] = boot95
    out["bootstrap_clean_sharpe"] = boot_clean
    print(f"\n=== BOOTSTRAP ext-1995 Sharpe: point={boot95['point']:.4f} "
          f"CI[{boot95['low']:.4f},{boot95['high']:.4f}] median={boot95['median']:.4f} ===")

    # ============ ITEM 4: RANKER lift + paired CI over ext-1995 ============
    # MF.cpm_wf base (faber_vol) reproduces production; self-check, then plain12.
    mf_cols = sorted(set(RISKY_UNIVERSE + SAFE_POOL + CANARY_ASSETS + [DEFAULT_CASH]) & set(panel.columns))
    mf_close = panel[mf_cols]
    mf_daily = mf_close.ffill().pct_change()
    base_r = H._segment_returns_conv(
        mf_close, mf_daily, lambda sd: MF.cpm_wf(mf_close, sd, ranker="faber_vol", flavor="invvol"),
        EXT1995_START, end, CONV, COST, intraday, overnight)[0].dropna()
    plain_r = H._segment_returns_conv(
        mf_close, mf_daily, lambda sd: MF.cpm_wf(mf_close, sd, ranker="plain12", flavor="invvol"),
        EXT1995_START, end, CONV, COST, intraday, overnight)[0].dropna()
    # self-check base==production clean Sharpe
    base_clean = met8(win(base_r, CLEAN_START, end), cash)
    ranker_selfcheck = abs(base_clean["sharpe"] - mc["sharpe"]) < 1e-6
    print(f"\nranker base self-check clean Sharpe={base_clean['sharpe']:.6f} matches_prod={ranker_selfcheck}")

    ranker = {}
    for wl, st in [("clean", CLEAN_START), ("ext1999", EXT1999_START), ("ext1995", EXT1995_START)]:
        b = win(base_r, st, end); p = win(plain_r, st, end)
        cmn = b.index.intersection(p.index)
        b = b.reindex(cmn); p = p.reindex(cmn)
        mb = met8(b, cash); mp = met8(p, cash)
        pb = paired_bootstrap_sharpe(b.values, p.values, B=2000, block=21, seed=42)
        ranker[wl] = {"volfaber_sharpe": mb["sharpe"], "plain12_sharpe": mp["sharpe"],
                      "lift": mb["sharpe"] - mp["sharpe"], "paired": pb}
        print(f"  ranker[{wl}] lift={ranker[wl]['lift']:+.4f} "
              f"P(base beats)={pb['p_base_beats']:.3f} CI[{pb['ci_lo']:+.4f},{pb['ci_hi']:+.4f}]")
    out["ranker_selfcheck_matches_prod"] = bool(ranker_selfcheck)
    out["ranker_lift"] = ranker

    # ============ ITEM 3: 2^6 FACTORIAL over ext-1995 (memo Section 6 spec) ============
    fa_cols = sorted(set(FA.AAA_UNIVERSE + FA.CPM_PROD_UNIVERSE + FA.SAFE
                         + ["HYG", "TIP"]) & set(panel.columns))
    fa_close = panel[fa_cols]
    fa_daily = fa_close.ffill().pct_change()
    factors = ["C", "U", "R", "S", "W", "P"]
    print("\n=== FACTORIAL 2^6 over ext-1995 (64 cells, faithful AAA baseline) ===")
    cells = {}
    for combo in itertools.product([0, 1], repeat=6):
        s = FA.run_cell(fa_close, fa_daily, intraday, overnight, EXT1995_START, end, *combo).dropna()
        wm = {}
        for wl, st in [("CLEAN", CLEAN_START), ("EXT1999", EXT1999_START), ("EXT1995", EXT1995_START)]:
            wm[wl] = met8(win(s, st, end), cash)
        cells[combo] = wm
    allon = cells[(1, 1, 1, 1, 1, 1)]
    base000 = cells[(0, 0, 0, 0, 0, 0)]
    # anchor: all-ON clean == 1.1910
    f6_anchor_ok = abs(allon["CLEAN"]["sharpe"] - 1.1910) < 1e-3
    print(f"  factorial all-ON clean Sharpe={allon['CLEAN']['sharpe']:.4f} "
          f"-> {'OK' if f6_anchor_ok else 'MISMATCH'}")
    out["factorial_anchor_allon_clean_ok"] = bool(f6_anchor_ok)
    out["factorial_baseline_000000"] = base000
    out["factorial_allon_111111"] = allon

    eff = {}
    for wl in ("CLEAN", "EXT1999", "EXT1995"):
        for metric in ("sharpe", "calmar"):
            flat = {k: cells[k][wl] for k in cells}
            eff[f"{wl}_{metric}"] = FA.factorial_effects(flat, factors, metric)
    out["factorial_effects"] = eff

    # ladder (dependency order R -> C -> U -> W -> S -> P, matching the memo)
    ladder_order = ["R", "C", "U", "W", "S", "P"]
    ladders = {}
    for wl in ("CLEAN", "EXT1999", "EXT1995"):
        state = {f: 0 for f in factors}
        path = [{"step": "Baseline (AAA)", "config": "000000", **base000[wl]}]
        for f in ladder_order:
            state[f] = 1
            key = tuple(state[x] for x in factors)
            label = f"+{f}" + (" (all-ON production CPM)" if all(state.values()) else "")
            path.append({"step": label, "config": "".join(str(state[x]) for x in factors),
                         **cells[key][wl]})
        ladders[wl] = path
    out["factorial_ladder"] = {"order": ladder_order, "paths": ladders}

    # main-effect table (memo factor order C,U,R,S,W,P)
    print("  main effects (EXT1995): ", {f: round(eff["EXT1995_sharpe"]["main"][f], 4) for f in factors})

    # ============ ITEM 8: PROXY COVERAGE over time ============
    # live risky ETF/8 at year-end snapshots.
    cov_timeline = {}
    for yr in range(1995, 2027):
        snap = pd.Timestamp(f"{yr}-12-31")
        nlive, livelist = live_coverage(snap)
        cov_timeline[str(yr)] = {"n_live": nlive, "live": livelist}
    # reduced-universe availability ladder (first valid in panel)
    fv = {t: (panel[t].first_valid_index() if t in panel.columns else None) for t in CPM_UNIV}
    ladder_avail = {t: (str(d.date()) if d is not None else None)
                    for t, d in sorted(fv.items(), key=lambda x: (x[1] or pd.Timestamp.max))}
    out["proxy_coverage"] = {
        "risky_live_per_year": cov_timeline,
        "panel_availability_ladder": ladder_avail,
        "live_inception": LIVE_INCEPTION,
        "note": ("Risky live ETF/8 by year-end: 0/8 1995-1998 (QQQ ETF 1999-03), 1/8 1999-2000, "
                 "rising through 2001-2006 as EFA/TLT/EEM/VNQ/GLD/SPHQ/DBC list, 8/8 from 2006 "
                 "(DBC 2006-02 last). Pre-1999 fully proxy-backed; clean 2008+ fully live."),
    }

    (HERE / "cpm_ext_1995_recompute.json").write_text(json.dumps(out, indent=2, default=float))
    print("\nWrote research/cpm_ext_1995_recompute.json")
    return out


if __name__ == "__main__":
    main()
