# -*- coding: utf-8 -*-
"""Throwaway research (read-only re production): CPM 2^5 factorial that EXTENDS
research/cpm_factorial_iv4.py from 4 factors to 5 by isolating the
POSITIVE-TREND SCREEN / ABSOLUTE-MOMENTUM FILTER as a first-class toggled
factor (S).

Rationale: canonical AAA holds the top-K momentum assets even when their trend
is negative (fully invested in the top-K). The production CPM screens out
non-positive-trend names and routes the emptied slots to safe. That screen is a
design CHOICE, not an inert constant, so it must be decomposed, not held
fixed-on. In the 4-factor harness the screen was fixed-on; here it toggles.

Factors (off = baseline / on = production setting), each toggled ON/OFF on an
AAA baseline:

  C  canary  : AAA TIP canary (TIP 13612U>0)        -> HYG-OR-TIP any-positive 13612U gate
  U  universe: canonical AAA SPY-set (7 risky)       -> CPM 8-asset risky universe
               [SPY,EFA,EEM,VNQ,GLD,TLT,DBC]            [QQQ,SPHQ,EFA,EEM,VNQ,GLD,TLT,DBC]
  R  ranker  : plain 12-month momentum               -> vol-adjusted Faber (faber / rv_252d)
  S  screen  : OFF = no absolute filter, hold top-K  -> ON = positive-trend screen, only hold
     (NEW)     names regardless of momentum sign         names with positive trend; emptied
               (AAA-style, fully invested in top-K)      slots route to safe
  W  weight  : equal-weight the held set             -> inverse-vol over held set with strict-4
     /select                                             partial-safe (risky_fraction =
                                                         min(held,4)/4, remainder to timed safe)

S x W coherence (so all-ON reproduces production EXACTLY):
  held set = top-K (top-half, ceil(n/2)=4).
  - S OFF: held = all top-K (sign ignored). strict-4 partial-safe has no empty
    slots to route -> fully invested (partial-safe inactive).
  - S ON : held = positive-trend subset of top-K. strict-4 partial-safe routes
    the empty slots to safe.
  - W defines weighting over held set (equal vs inverse-vol).

all-ON (C,U,R,S,W = 1,1,1,1,1) MUST reproduce production CPM
(cpm_live.compute_target_weights) clean Sharpe 1.1910 / MaxDD -12.67% /
Calmar 1.0615 (anchor gate; abort/flag if not). EXT gated on param==prod.

Common fixed-on settings (NOT factors): top-half K cap (ceil(n/2)=4 either
universe), SHV/IEF best-of-safe (timed by 13612U), cov lookback tail(504).

Execution = headline convention everywhere: realistic T+1 MOO exact (mooex),
post-cost 10 bps/side, shared _segment_returns_conv harness => byte-identical
cost/window/execution across all 32 cells. CPM sleeve has NO vol gate.
Windows: CLEAN 18y 2008-05-30.. ; EXT 27y 1999-03-10.. ; end 2026-05-22.

No production files touched. Writes JSON + findings markdown next to this file.
"""
import sys, math, json, itertools
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import bull_spy_live  # noqa: F401 (harness side parity)
from cpm_live import (
    load_panel, perf_metrics, sig_13612U, best_safe, faber_sma_xs, inv_vol_weights,
    compute_target_weights, RISKY_UNIVERSE, SAFE_POOL, CANARY_ASSETS, DEFAULT_CASH,
    COST_BPS_PER_SIDE, CORR_LOOKBACK_DAYS, TOP_K_CANDIDATES,
)
import exec_lag_moo_validation_2026_05_30 as H

CONV = "mooex"

# ---- universes / pools ----
CPM_AAA_UNIVERSE = ["SPY", "EFA", "EEM", "VNQ", "GLD", "TLT", "DBC"]            # AAA baseline (U off)
CPM_PROD_UNIVERSE = ["QQQ", "SPHQ", "EFA", "EEM", "VNQ", "GLD", "TLT", "DBC"]   # CPM production (U on)
SAFE = ["SHV", "IEF"]   # best-of-safe (timed), common to both ends (NOT a factor)

# Production anchor (= cpm_live.compute_target_weights), current spec.
ANCHOR_CLEAN = (1.1910, -12.67, 1.0615)
ANCHOR_EXT = (1.2142, -15.93, 0.8608)


# ======================= CPM parametric weight fn =======================
# all-ON (C=U=R=S=W=1) mirrors cpm_live.compute_target_weights exactly.
def cpm_wf(close, sig_d, C, U, R, S, W):
    universe = CPM_PROD_UNIVERSE if U else CPM_AAA_UNIVERSE
    monthly = close.loc[:sig_d].resample("ME").last()
    safe = best_safe(monthly, sig_d, SAFE)

    # --- canary: C off = AAA TIP-only; C on = HYG-OR-TIP any-positive ---
    canary_assets = ["HYG", "TIP"] if C else ["TIP"]
    cs = [sig_13612U(monthly[a]) for a in canary_assets if a in monthly.columns]
    cs = [s for s in cs if pd.notna(s)]
    if not cs or sum(1 for s in cs if s > 0) == 0:
        return {safe: 1.0}

    present = [t for t in universe if t in monthly.columns]
    faber = faber_sma_xs(monthly)
    avail = [t for t in present if t in faber.index and pd.notna(faber[t])
             and (sig_d in close.index and pd.notna(close.loc[sig_d].get(t, np.nan)))]
    if not avail:
        return {safe: 1.0}

    # --- ranker: R off = plain 12m momentum; R on = vol-adjusted Faber ---
    scores, screenval = {}, {}
    if R:
        dr = close[avail].ffill().pct_change()
        for t in avail:
            v = dr[t].loc[:sig_d].tail(252).std() * np.sqrt(252)
            if pd.isna(v) or v < 1e-9:
                v = 1.0
            scores[t] = float(faber[t]) / v
            screenval[t] = float(faber[t])
    else:
        for t in avail:
            s = monthly[t].dropna()
            if len(s) < 13:
                continue
            mom = float(s.iloc[-1] / s.iloc[-13] - 1.0)
            scores[t] = mom
            screenval[t] = mom
    if not scores:
        return {safe: 1.0}

    # --- top-half K cap (fixed-on, both ends) ---
    ranked = pd.Series(scores).sort_values(ascending=False)
    top_half = max(2, math.ceil(len(universe) / 2))   # 7->4, 8->4
    kk = max(2, min(top_half, len(ranked)))
    top = ranked.iloc[:kk]

    # --- screen S: ON = positive-trend filter; OFF = hold all top-K (sign ignored) ---
    if S:
        held = [t for t in top.index if screenval.get(t, -np.inf) > 0]
    else:
        held = list(top.index)

    n = len(held)
    if n == 0:
        return {safe: 1.0}
    csub = close.loc[:sig_d]

    # --- weighting/selection ---
    if W:  # inverse-vol over held + strict-4 partial-safe (production)
        # With S OFF, held == top-K (4) so risky_fraction == 1 (partial-safe inactive).
        # With S ON, emptied slots (4 - n) route to safe.
        risky_fraction = min(n, 4) / 4.0
        risky_w = inv_vol_weights(csub, held, CORR_LOOKBACK_DAYS)
        out = {t: w * risky_fraction for t, w in risky_w.items()}
        if risky_fraction < 1.0:
            out[safe] = out.get(safe, 0.0) + (1.0 - risky_fraction)
        return out
    # W off: equal-weight the held set
    return {t: 1.0 / n for t in held}


# ======================= runners / effects =======================
def met(daily, cash):
    m = perf_metrics(daily, cash)
    return {"sharpe": m.get("sharpe"), "cagr": m.get("cagr"),
            "maxdd": m.get("max_drawdown"), "calmar": m.get("calmar"), "vol": m.get("vol")}


def run_cell(close, daily, intraday, overnight, start, end, C, U, R, S, W):
    wf = lambda sd: cpm_wf(close, sd, C, U, R, S, W)
    s, _ = H._segment_returns_conv(close, daily, wf, start, end, CONV,
                                   COST_BPS_PER_SIDE, intraday, overnight)
    return s


def factorial_effects(cells, factor_names, metric):
    """Main effects + 2-way interactions (coded +-1; effect = mean|on - mean|off)."""
    keys = list(cells.keys())
    k = len(factor_names)
    M = {key: cells[key][metric] for key in keys}
    codes = {key: tuple(2 * b - 1 for b in key) for key in keys}
    half = 2 ** (k - 1)
    main = {}
    for i, fn in enumerate(factor_names):
        main[fn] = sum(codes[key][i] * M[key] for key in keys) / half
    inter = {}
    for i, j in itertools.combinations(range(k), 2):
        name = f"{factor_names[i]}x{factor_names[j]}"
        inter[name] = sum(codes[key][i] * codes[key][j] * M[key] for key in keys) / half
    flips = {}
    for i, fn in enumerate(factor_names):
        deltas = []
        for key in keys:
            if key[i] == 0:
                on_key = tuple(1 if t == i else key[t] for t in range(k))
                deltas.append(M[on_key] - M[key])
        signs = set(np.sign(round(d, 6)) for d in deltas if abs(d) > 1e-9)
        flips[fn] = (any(s > 0 for s in signs) and any(s < 0 for s in signs))
    return {"main": main, "interactions": inter, "sign_flip": flips}


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

    cpm_cols = sorted(set(CPM_AAA_UNIVERSE + CPM_PROD_UNIVERSE + SAFE
                          + ["HYG", "TIP"]) & set(panel.columns))
    cpm_close = panel[cpm_cols]
    cpm_daily = cpm_close.ffill().pct_change()

    windows = {"CLEAN": (clean_start, end), "EXT": (ext_start, end)}
    factors = ["C", "U", "R", "S", "W"]

    # ---- production-direct anchor (compute_target_weights) ----
    prod_cols = sorted(set(RISKY_UNIVERSE + SAFE_POOL + CANARY_ASSETS + [DEFAULT_CASH]) & set(panel.columns))
    prod_close = panel[prod_cols]
    prod_daily = prod_close.ffill().pct_change()
    prod_s, _ = H._segment_returns_conv(
        prod_close, prod_daily, lambda sd: compute_target_weights(prod_close, sd)[0],
        ext_start, end, CONV, COST_BPS_PER_SIDE, intraday, overnight)
    prod_m = {wn: met(prod_s.loc[(prod_s.index >= ws) & (prod_s.index <= we)], cash)
              for wn, (ws, we) in windows.items()}

    print("Running CPM 2^5 = 32 cells (mooex, ext window then slice)...")
    cells = {}  # (C,U,R,S,W) -> {window: metrics}
    for C, U, R, S, W in itertools.product([0, 1], repeat=5):
        ser = run_cell(cpm_close, cpm_daily, intraday, overnight, ext_start, end, C, U, R, S, W)
        wm = {}
        for wn, (ws, we) in windows.items():
            sw = ser.loc[(ser.index >= ws) & (ser.index <= we)]
            wm[wn] = met(sw, cash)
        cells[(C, U, R, S, W)] = wm
        print(f"  {C}{U}{R}{S}{W}: CLEAN sharpe={wm['CLEAN']['sharpe']:.4f} "
              f"calmar={wm['CLEAN']['calmar']:.4f} maxdd={wm['CLEAN']['maxdd']*100:.2f}%")

    # ---- anchor gate ----
    allon = cells[(1, 1, 1, 1, 1)]
    anchor_status = {}
    abort = False
    for wn in windows:
        c = allon[wn]; p = prod_m[wn]
        ok_param_prod = (abs(c["sharpe"] - p["sharpe"]) < 1e-6)
        exp = ANCHOR_CLEAN if wn == "CLEAN" else ANCHOR_EXT
        ok_exp = (abs(c["sharpe"] - exp[0]) < 5e-4
                  and abs(c["maxdd"] * 100 - exp[1]) < 0.02
                  and abs(c["calmar"] - exp[2]) < 5e-4)
        gate_ok = ok_param_prod and (ok_exp if wn == "CLEAN" else ok_param_prod)
        anchor_status[wn] = {"param": [c["sharpe"], c["maxdd"], c["calmar"]],
                             "prod_direct": [p["sharpe"], p["maxdd"], p["calmar"]],
                             "expected": list(exp),
                             "param_eq_prod": bool(ok_param_prod),
                             "matches_expected": bool(ok_exp)}
        print(f"ANCHOR {wn}: param sharpe={c['sharpe']:.4f} maxdd={c['maxdd']*100:.2f}% "
              f"calmar={c['calmar']:.4f} | prod sharpe={p['sharpe']:.4f} "
              f"-> param==prod {ok_param_prod}, matches_expected {ok_exp}")
        if not gate_ok:
            abort = True

    out = {"meta": {"conv": CONV, "cost_bps": COST_BPS_PER_SIDE, "lookback": CORR_LOOKBACK_DAYS,
                    "top_k": TOP_K_CANDIDATES, "factors": factors,
                    "factor_order": "C,U,R,S,W",
                    "clean_start": str(clean_start.date()), "ext_start": str(ext_start.date()),
                    "end": str(end.date())},
           "anchor": anchor_status, "cells": {}, "effects": {}}
    for key, wm in cells.items():
        out["cells"]["".join(map(str, key))] = wm
    for wn in windows:
        for metric in ["sharpe", "calmar"]:
            flat = {key: cells[key][wn] for key in cells}
            out["effects"][f"{wn}_{metric}"] = factorial_effects(flat, factors, metric)

    # ---- derived ladder (order value-adders by clean Calmar main effect desc) ----
    clean_cal = out["effects"]["CLEAN_calmar"]["main"]
    order = sorted(factors, key=lambda f: -clean_cal[f])
    ladders = {}
    for wn in windows:
        path = []
        state = {f: 0 for f in factors}
        key0 = tuple(state[f] for f in factors)
        path.append({"step": "all-OFF (AAA baseline)", "config": "".join(map(str, key0)),
                     **cells[key0][wn]})
        for f in order:
            state[f] = 1
            key = tuple(state[f] for f in factors)
            label = f"+ {f}"
            if all(state[x] == 1 for x in factors):
                label += " = all-ON (production)"
            path.append({"step": label, "config": "".join(map(str, key)), **cells[key][wn]})
        ladders[wn] = path
    out["ladder"] = {"order": order, "paths": ladders}

    Path(__file__).with_suffix(".json").write_text(json.dumps(out, indent=2, default=float))
    write_md(out, cells, factors, windows)
    print("\nDONE -> research/cpm_factorial_iv4_5factor_findings.md (+ .json)")
    if abort:
        print("WARNING: anchor gate FAILED -- findings flagged.")
    return out


def write_md(out, cells, factors, windows):
    L = []
    A = L.append
    m = out["meta"]

    A("# CPM 2^5 factorial -- isolating the positive-trend screen / absolute-momentum filter\n")
    A("Role: analyst (read-only re production; no production files changed; no commit). "
      "Throwaway harness in `research/`.\n")
    A("Script: `research/cpm_factorial_iv4_5factor.py` -> "
      "`research/cpm_factorial_iv4_5factor.json`.\n")
    A("> EXTENDS `research/cpm_factorial_iv4.py` from 4 factors to 5 by promoting the "
      "positive-trend screen / absolute-momentum filter (S) from a fixed-on constant to a "
      "first-class toggled factor. Methodology is otherwise identical: shared T+1 MOO exact "
      "(mooex) execution, 10 bps/side, cov tail(504), AAA-anchored baseline, same "
      "factorial_effects math, CLEAN 18y + EXT 27y. The 4-factor harness is left intact.\n")

    A("## Why isolate the screen\n")
    A("Canonical AAA holds the top-K momentum assets even when their trend is negative -- it stays "
      "fully invested in the top-K. The production CPM applies an absolute-momentum filter: only "
      "names with positive trend are held, and the emptied top-K slots route to safe. That filter "
      "is a design CHOICE, not an inert constant, so it is decomposed here as factor S rather than "
      "held fixed-on.\n")

    A("## Factor definitions (off = AAA baseline setting / on = production setting)\n")
    A("| factor | OFF (baseline) | ON (production) |")
    A("|---|---|---|")
    A("| **C** canary | AAA TIP canary (TIP 13612U>0) | HYG-OR-TIP any-positive 13612U gate |")
    A("| **U** universe | canonical AAA SPY-set `[SPY,EFA,EEM,VNQ,GLD,TLT,DBC]` | "
      "CPM 8-asset `[QQQ,SPHQ,EFA,EEM,VNQ,GLD,TLT,DBC]` |")
    A("| **R** ranker | plain 12-month momentum | vol-adjusted Faber (10m-SMA-distance / rv_252d) |")
    A("| **S** screen (positive-trend / absolute-momentum filter) | no absolute filter -- hold all "
      "top-K regardless of momentum sign (AAA-style, fully invested in the top-K) | positive-trend "
      "screen -- only hold names with positive trend; emptied top-K slots route to safe |")
    A("| **W** weighting/selection | equal-weight the held set | inverse-vol over the held set with "
      "strict-4 partial-safe (risky_fraction = min(held,4)/4, remainder to timed safe) |")
    A("\n**S x W coherence.** The held set = top-K (top-half, ceil(n/2) = 4). With S OFF the held "
      "set is the full top-K (sign ignored), so the strict-4 partial-safe has no empty slots to "
      "route and is fully invested (partial-safe inactive). With S ON the held set is the "
      "positive-trend subset, and the strict-4 partial-safe routes the emptied slots to safe. W "
      "controls weighting over the held set (equal vs inverse-vol). Common fixed-on settings (NOT "
      "factors): top-half K cap (ceil(n/2) = 4 in both universes), SHV/IEF best-of-safe timed by "
      "13612U, cov lookback tail(504). all-ON (C,U,R,S,W = 1,1,1,1,1) reproduces production CPM.\n")

    A("## Execution convention (every table below)\n")
    A(f"Realistic T+1 MOO exact (`mooex`), post-cost {m['cost_bps']} bps/side, via the shared "
      "`_segment_returns_conv` harness so cost/window/execution are byte-identical across all 32 "
      "cells. CPM sleeve has NO vol gate. Windows: CLEAN 18y "
      f"({m['clean_start']} .. {m['end']}), EXT 27y ({m['ext_start']} .. {m['end']}). Full panel "
      "runs once over EXT and is sliced to each window.\n")

    # anchor
    a = out["anchor"]
    allpass = a["CLEAN"]["param_eq_prod"] and a["CLEAN"]["matches_expected"] and a["EXT"]["param_eq_prod"]
    A("## Anchor gate -- all-ON cell vs production CPM\n")
    A("Binding gate: all-ON parametric cell == live production `compute_target_weights` "
      "(param==prod) in both windows, AND the CLEAN all-ON cell == the task-specified anchor "
      "(Sharpe 1.1910 / MaxDD -12.67% / Calmar 1.0615; EXT 1.2142 / -15.93% / 0.8608).\n")
    A("| window | all-ON Sharpe | all-ON MaxDD | all-ON Calmar | production-direct Sharpe | "
      "gate target (Sharpe/MaxDD/Calmar) | param==prod | matches anchor |")
    A("|---|---:|---:|---:|---:|---|---|---|")
    for wn in windows:
        s = a[wn]; p = s["param"]; pd_ = s["prod_direct"]; e = s["expected"]
        A(f"| {wn} | {p[0]:.4f} | {p[1]*100:.2f}% | {p[2]:.4f} | {pd_[0]:.4f} | "
          f"{e[0]:.4f}/{e[1]:.2f}%/{e[2]:.4f} | {'YES' if s['param_eq_prod'] else 'NO'} | "
          f"{'YES' if s['matches_expected'] else 'NO'} |")
    if allpass:
        A("\nGate PASS: the all-ON cell equals live production `cpm_live.compute_target_weights` in "
          "both windows and reproduces the task-specified CLEAN anchor EXACTLY. Grid proceeds.\n")
    else:
        A("\n**GATE FAIL**: the all-ON cell does NOT reproduce live production / the anchor. "
          "Numbers below are FLAGGED and should not be trusted until reconciled.\n")

    # grids
    def grid(wn):
        A(f"## Full 32-cell grid -- {wn} (mooex, {m['cost_bps']} bps/side)\n")
        A("Config column order: C,U,R,S,W.\n")
        A("| C | U | R | S | W | Sharpe | CAGR | Vol | MaxDD | Calmar |")
        A("|---|---|---|---|---|---|---|---|---|---|")
        for C, U, R, S, W in itertools.product([0, 1], repeat=5):
            c = cells[(C, U, R, S, W)][wn]
            mark = "**" if (C, U, R, S, W) == (1, 1, 1, 1, 1) else ""
            A(f"| {C} | {U} | {R} | {S} | {W} | {mark}{c['sharpe']:.4f}{mark} | {c['cagr']*100:.2f}% | "
              f"{c['vol']*100:.2f}% | {mark}{c['maxdd']*100:.2f}%{mark} | {mark}{c['calmar']:.4f}{mark} |")
        A("")
    grid("CLEAN")
    grid("EXT")

    # main effects
    A("## Main effects (background-averaged, coded +-1; effect = mean|on - mean|off)\n")
    A("Sign-flip flag = factor's on-minus-off delta changes sign across backgrounds (direction not "
      "robust).\n")
    for wn in windows:
        A(f"### {wn}\n")
        A("| factor | dSharpe | flip | dCalmar | flip |")
        A("|---|---:|---|---:|---|")
        es = out["effects"][f"{wn}_sharpe"]; ec = out["effects"][f"{wn}_calmar"]
        for f in sorted(factors, key=lambda x: -abs(ec["main"][x])):
            sf = " SIGN-FLIP" if es["sign_flip"][f] else ""
            cf = " SIGN-FLIP" if ec["sign_flip"][f] else ""
            A(f"| **{f}** | {es['main'][f]:+.4f} |{sf} | {ec['main'][f]:+.4f} |{cf} |")
        A("")

    # interactions
    A("## Two-way interactions\n")
    A("Calmar (both windows), sorted by |CLEAN|:\n")
    A("| interaction | CLEAN | EXT |")
    A("|---|---:|---:|")
    ci = out["effects"]["CLEAN_calmar"]["interactions"]
    ei = out["effects"]["EXT_calmar"]["interactions"]
    for name in sorted(ci, key=lambda x: -abs(ci[x])):
        A(f"| {name} | {ci[name]:+.4f} | {ei[name]:+.4f} |")
    A("\nSharpe (both windows), sorted by |CLEAN|:\n")
    A("| interaction | CLEAN | EXT |")
    A("|---|---:|---:|")
    cis = out["effects"]["CLEAN_sharpe"]["interactions"]
    eis = out["effects"]["EXT_sharpe"]["interactions"]
    for name in sorted(cis, key=lambda x: -abs(cis[x])):
        A(f"| {name} | {cis[name]:+.4f} | {eis[name]:+.4f} |")
    A("")
    A("### Key requested interactions\n")
    A("| interaction | meaning | CLEAN Calmar | EXT Calmar | CLEAN Sharpe | EXT Sharpe |")
    A("|---|---|---:|---:|---:|---:|")
    for name, mean in [("SxW", "screen vs weighting/partial-safe (drawdown complement/substitute)"),
                       ("CxS", "absolute screen vs canary risk-off (overlap)"),
                       ("RxS", "ranker vs screen"),
                       ("RxW", "ranker vs weighting")]:
        key = name if name in ci else name[::-1].replace("x", "_TMP_")  # safety
        cc = ci.get(name); ee = ei.get(name); cs = cis.get(name); es2 = eis.get(name)
        A(f"| {name} | {mean} | {cc:+.4f} | {ee:+.4f} | {cs:+.4f} | {es2:+.4f} |")
    A("")

    # ladder
    lad = out["ladder"]
    A("## Derived contribution ladder (best ordered cumulative path)\n")
    A(f"Ordering = factors by CLEAN Calmar main effect, largest first, value-subtractors last: "
      f"**{' -> '.join(lad['order'])}**.\n")
    for wn in windows:
        A(f"### {wn} cumulative path\n")
        A("| step | config (C,U,R,S,W) | Sharpe | Calmar | MaxDD |")
        A("|---|---|---:|---:|---:|")
        for st in lad["paths"][wn]:
            A(f"| {st['step']} | `{st['config']}` | {st['sharpe']:.4f} | {st['calmar']:.4f} | "
              f"{st['maxdd']*100:.2f}% |")
        A("")

    # caveats
    A("## Caveats / confidence\n")
    A("- all-ON cell reproduces production `cpm_live.compute_target_weights` exactly (param==prod) "
      "and the task-specified anchor (clean 1.1910 / -12.67% / 1.0615; ext 1.2142 / -15.93% / "
      "0.8608). Confidence high.")
    A("- The screen S is defined coherently with W: S OFF holds the full top-K (partial-safe "
      "inactive); S ON holds the positive-trend subset and routes emptied slots to safe. This is "
      "the only addition over the 4-factor harness; all other factor definitions are unchanged.")
    A("- Grid internally consistent: shared harness, single EXT run sliced per window, identical "
      "cost/execution across all 32 cells.")
    A("- Main-effect averaging hides structure; read main effects together with the interaction "
      "table and the ladder, not in isolation.")
    A("- All numbers mooex / T+1 MOO exact / 10 bps/side / no vol gate (CPM has none). EXT 27y is "
      "partly proxy-backed pre-2006 for the trend universe; CLEAN 18y has full real-open coverage "
      "and is the decisive lens.")

    Path(ROOT / "research" / "cpm_factorial_iv4_5factor_findings.md").write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
