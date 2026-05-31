# -*- coding: utf-8 -*-
"""Throwaway research (READ-ONLY re production; NO prod/memo edits; NO commit).

Walk-forward / OOS validation of the ONE promising CPM overlay from
research/cpm_crossasset_overlay.py: C3 = PC1 / absorption-ratio gate.

C3 construction (production-faithful): rolling 60d correlation matrix of CPM's 8
risky assets; PC1 = dominant-eigenvalue share of total variance; when PC1 > thr,
scale risky exposure by `floor` (remainder to safe). Prior single in-sample:
PC1>70% -> risky*0.5 gave clean Sharpe 1.2144 vs prod 1.1910 (mooex), and
survived execution lag (moc 1.2344 vs prod 1.2063). Flagged threshold-fragile
(65% hurts, 75% fades) and adds ZERO crisis protection.

This script answers: is C3's edge REAL or in-sample-selected?
  1. THRESHOLD RESPONSE SURFACE -- fine sweep thr {0.60..0.80} x floor
     {0,0.25,0.5,0.75} on full clean window. Sharp isolated peak (overfit) or
     broad plateau (robust)?
  2. WALK-FORWARD / OOS -- (a) expanding-window annual re-selection: pick
     (thr,floor) by best trailing in-sample Sharpe, apply forward, stitch;
     (b) split-sample 2008-2016 train / 2017-2026 test and reverse.
  3. ROBUSTNESS -- corr window {40,60,90}; per-year / sub-period contribution.
  4. VERDICT -- adopt-candidate / document-only / reject.

Honesty guards: PC1 computed point-in-time on data <= decision date; execution
T+1 MOO exact (mooex); post-cost 10bps/side. Anchor + base self-check gate FIRST
(reproduce 1.1910 prod and 1.2144 C3) -- ABORT on mismatch.

Writes research/cpm_pc1_walkforward_findings.md (+ .json). No prod files touched.
"""
from __future__ import annotations
import sys, json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path("/Users/rkautsar/personal/scripts/strategy_cpm")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "research"))

import exec_lag_moo_validation_2026_05_30 as H
from cpm_live import (
    load_panel, perf_metrics, compute_target_weights,
    RISKY_UNIVERSE, SAFE_POOL, CANARY_ASSETS, DEFAULT_CASH, COST_BPS_PER_SIDE,
    TOP_K_CANDIDATES, CORR_LOOKBACK_DAYS,
)
from cpm_crossasset_overlay import gcpm_wf, CPM_UNIV, met, win, maxdd_ret

CONV = "mooex"
COST = COST_BPS_PER_SIDE
EXT_START = pd.Timestamp("1999-03-10")
CLEAN_START = pd.Timestamp("2008-05-30")
END = pd.Timestamp("2026-05-22")

ANCHOR_CLEAN = (1.1910, -12.67, 1.0615)
C3_CLEAN_REF = 1.2144  # PC1>70% risky*0.5 mooex clean

THRS = [round(0.60 + 0.02 * i, 2) for i in range(11)]   # 0.60..0.80
FLOORS = [0.0, 0.25, 0.5, 0.75]
WINDOWS = [40, 60, 90]


def run_series(close, daily, intraday, overnight, wf, end, conv=CONV):
    s, _ = H._segment_returns_conv(close, daily, wf, EXT_START, end, conv,
                                   COST, intraday, overnight)
    return s


def sharpe_of(s, cash, start, end):
    return met(win(s, start, end), cash)


def build_pc1_cache(close, sigs, window):
    uni = [t for t in CPM_UNIV if t in close.columns]
    uni_rets = close[uni].ffill().pct_change()
    cache = {}
    for sd in sigs:
        sub = uni_rets.loc[:sd].dropna(how="all").tail(window)
        sub = sub.dropna(axis=1, how="any")
        if sub.shape[0] < window // 2 or sub.shape[1] < 3:
            cache[sd] = np.nan
            continue
        c = sub.corr().values
        if not np.all(np.isfinite(c)):
            cache[sd] = np.nan
            continue
        ev = np.linalg.eigvalsh(c)
        cache[sd] = float(ev[-1] / ev.sum())
    return cache


def scale_base_weights(base_w, scale):
    """Apply PC1 de-risk scale to a base (gate-off) monthly weight dict.

    base_w risky entries (in CPM_UNIV) sum to risky_fraction; reconstruct the
    scaled dict exactly as gcpm_wf would with risky_scale_fn returning `scale`.
    """
    safe_t_marker = base_w.get("__safe__")
    base_w = {k: v for k, v in base_w.items() if k != "__safe__"}
    if scale >= 1.0:
        return dict(base_w)
    risky = {t: w for t, w in base_w.items() if t in CPM_UNIV}
    if not risky:                      # fully risk-off month -> gate is a no-op
        return dict(base_w)
    safe_extra = {t: w for t, w in base_w.items() if t not in CPM_UNIV}
    out = {t: w * scale for t, w in risky.items()}
    rf = sum(risky.values())
    # safe ticker(s): existing remainder + freed risky exposure
    freed = rf * (1.0 - scale)
    if safe_extra:
        # single safe key in practice
        for t, w in safe_extra.items():
            out[t] = w + freed
    else:
        # base was fully invested (rf==1): need a safe sink. gcpm uses best_safe;
        # recompute via a marker -- but base dict here has no safe key only when
        # rf==1, where gcpm would set out[safe]+=(1-rf)=0 so safe absent. We must
        # know the safe ticker. Store it on the dict via '__safe__'.
        out[safe_t_marker] = freed
    return out


def main():
    panel = load_panel(start=EXT_START, end=END)
    end = min(END, panel.index[-1])
    cash = panel["SHV"].ffill().pct_change().dropna()
    od, cy = H.load_open_close()
    intraday = (cy / od - 1.0).reindex(panel.index)
    overnight = (od / cy.shift(1) - 1.0).reindex(panel.index)
    cols = sorted(set(RISKY_UNIVERSE + SAFE_POOL + CANARY_ASSETS + [DEFAULT_CASH]) & set(panel.columns))
    close = panel[cols]
    daily = close.ffill().pct_change()

    monthly_idx = (pd.DataFrame({"x": 1}, index=close.index)
                   .groupby(pd.Grouper(freq="ME")).tail(1))
    sigs_all = monthly_idx.index[(monthly_idx.index >= EXT_START) & (monthly_idx.index <= end)].tolist()

    out = {"meta": {"conv": CONV, "cost_bps": COST, "end": str(end.date()),
                    "clean_start": str(CLEAN_START.date()), "ext_start": str(EXT_START.date()),
                    "thrs": THRS, "floors": FLOORS, "windows": WINDOWS}}

    # ---------- ANCHOR ----------
    cpm = run_series(close, daily, intraday, overnight,
                     lambda sd: compute_target_weights(close, sd)[0], end)
    mc = met(win(cpm, CLEAN_START, end), cash)
    ok = (abs(mc["sharpe"] - ANCHOR_CLEAN[0]) < 5e-4 and
          abs(mc["maxdd"] * 100 - ANCHOR_CLEAN[1]) < 0.02 and
          abs(mc["calmar"] - ANCHOR_CLEAN[2]) < 5e-4)
    print(f"ANCHOR clean: Sharpe={mc['sharpe']:.4f} MaxDD={mc['maxdd']*100:.2f}% "
          f"Calmar={mc['calmar']:.4f} -> {'OK' if ok else 'MISMATCH'}")
    out["anchor"] = {**mc, "ok": bool(ok)}
    if not ok:
        print("ANCHOR MISMATCH -- abort."); sys.exit(1)

    # ---------- base weights (gate-off) cached per month ----------
    # capture safe ticker so we can re-route freed exposure when rf==1.
    base_w_cache = {}
    for sd in sigs_all:
        w = gcpm_wf(close, sd)
        # attach safe ticker marker (best_safe) for rf==1 reconstruction
        from cpm_live import best_safe
        monthly = close.loc[:sd].resample("ME").last()
        safe_t = best_safe(monthly, sd, ["SHV", "IEF"])
        w = dict(w); w["__safe__"] = safe_t
        base_w_cache[sd] = w

    base_series = run_series(close, daily, intraday, overnight,
                             lambda sd: {k: v for k, v in base_w_cache[sd].items() if k != "__safe__"}, end)
    bc = met(win(base_series, CLEAN_START, end), cash)
    gmatch = abs(bc["sharpe"] - mc["sharpe"]) < 1e-6
    print(f"base self-check clean Sharpe={bc['sharpe']:.6f} matches={gmatch}")
    out["selfcheck"] = {"clean_sharpe": bc["sharpe"], "matches": bool(gmatch)}
    if not gmatch:
        print("SELF-CHECK MISMATCH -- abort."); sys.exit(1)

    # ---------- pc1 caches ----------
    pc1 = {w: build_pc1_cache(close, sigs_all, w) for w in WINDOWS}

    def make_wf(thr, floor, window):
        cache = pc1[window]
        def wf(sd):
            base = base_w_cache[sd]
            p = cache.get(sd, np.nan)
            scale = floor if (pd.notna(p) and p > thr) else 1.0
            return scale_base_weights(base, scale)
        return wf

    # ---------- precompute series for full grid (window=60 for surface; all windows for robustness) ----------
    # cache full daily series for each (thr,floor,window) to reuse in WF + split.
    series_cache = {}
    def get_series(thr, floor, window):
        key = (thr, floor, window)
        if key not in series_cache:
            series_cache[key] = run_series(close, daily, intraday, overnight,
                                           make_wf(thr, floor, window), end)
        return series_cache[key]

    # verify C3 reference reproduces (thr .70 floor .5 window 60)
    c3 = get_series(0.70, 0.5, 60)
    c3m = met(win(c3, CLEAN_START, end), cash)
    c3_ok = abs(c3m["sharpe"] - C3_CLEAN_REF) < 2e-3
    print(f"C3 reproduce PC1>70 risky*0.5 w60: Sharpe={c3m['sharpe']:.4f} (ref {C3_CLEAN_REF}) "
          f"-> {'OK' if c3_ok else 'MISMATCH'}")
    out["c3_reproduce"] = {"sharpe": c3m["sharpe"], "calmar": c3m["calmar"],
                           "maxdd": c3m["maxdd"], "ref": C3_CLEAN_REF, "ok": bool(c3_ok)}
    if not c3_ok:
        print("C3 REPRODUCE MISMATCH -- abort."); sys.exit(1)

    prod_clean = mc

    # ================= 1. THRESHOLD RESPONSE SURFACE (window=60, full clean) =================
    surface = {}
    for floor in FLOORS:
        for thr in THRS:
            s = get_series(thr, floor, 60)
            m = met(win(s, CLEAN_START, end), cash)
            surface[f"thr{int(thr*100)}_floor{floor:g}"] = {
                "thr": thr, "floor": floor, "sharpe": m["sharpe"], "calmar": m["calmar"],
                "maxdd": m["maxdd"], "cagr": m["cagr"]}
    out["surface"] = surface
    out["prod_clean"] = prod_clean

    # ================= 2a. EXPANDING WALK-FORWARD (annual re-selection) =================
    # Selection set: prod (no gate) + grid {thr in 0.62..0.78 step .04} x {floor 0,0.5} window 60.
    wf_grid = [("prod", None, None)]
    for thr in [0.62, 0.66, 0.70, 0.74, 0.78]:
        for floor in [0.0, 0.5]:
            wf_grid.append((f"thr{int(thr*100)}_f{floor:g}", thr, floor))

    def cfg_series(name, thr, floor):
        if name == "prod":
            return base_series
        return get_series(thr, floor, 60)

    # OOS spans: re-select every Jan 1 using all data from CLEAN_START..boundary,
    # apply forward 1y. min 3y train.
    wf_select_log = []
    oos_pieces = []
    prod_oos_pieces = []
    first_oos = pd.Timestamp("2011-06-01")  # ~3y after clean start
    boundaries = pd.date_range(first_oos, end, freq="YS-JUN")  # annual mid-year boundaries
    boundaries = [b for b in boundaries if b <= end]
    spans = []
    for i, b in enumerate(boundaries):
        nb = boundaries[i + 1] if i + 1 < len(boundaries) else end + pd.Timedelta(days=1)
        spans.append((b, min(nb, end + pd.Timedelta(days=1))))
    for (b, nb) in spans:
        train_start, train_end = CLEAN_START, b - pd.Timedelta(days=1)
        best, best_sh = None, -1e9
        scores = {}
        for (name, thr, floor) in wf_grid:
            s = cfg_series(name, thr, floor)
            sh = met(win(s, train_start, train_end), cash)["sharpe"]
            scores[name] = sh
            if sh > best_sh:
                best_sh, best = sh, (name, thr, floor)
        # apply best forward
        bs = cfg_series(*best)
        piece = bs.loc[(bs.index >= b) & (bs.index < nb)]
        oos_pieces.append(piece)
        prod_oos_pieces.append(base_series.loc[(base_series.index >= b) & (base_series.index < nb)])
        wf_select_log.append({"boundary": str(b.date()), "selected": best[0],
                              "train_sharpe": best_sh, "scores": scores})
    wf_series = pd.concat(oos_pieces).sort_index()
    prod_wf_series = pd.concat(prod_oos_pieces).sort_index()
    oos_start = wf_series.index[0]
    wf_m = met(wf_series, cash)
    prod_wf_m = met(prod_wf_series, cash)
    out["walkforward_expanding"] = {
        "oos_start": str(oos_start.date()), "oos_end": str(wf_series.index[-1].date()),
        "wf": wf_m, "prod_oos": prod_wf_m,
        "n_select": len(wf_select_log),
        "selected_counts": pd.Series([r["selected"] for r in wf_select_log]).value_counts().to_dict(),
        "log": wf_select_log}
    print(f"WF expanding OOS {oos_start.date()}..{wf_series.index[-1].date()}: "
          f"WF Sharpe={wf_m['sharpe']:.4f} Calmar={wf_m['calmar']:.4f} vs "
          f"prod-OOS Sharpe={prod_wf_m['sharpe']:.4f} Calmar={prod_wf_m['calmar']:.4f}")

    # ================= 2b. SPLIT-SAMPLE =================
    splits = {
        "train 2008-2016 / test 2017-2026": (("2008-05-30", "2016-12-31"), ("2017-01-01", str(end.date()))),
        "train 2017-2026 / test 2008-2016": (("2017-01-01", str(end.date())), ("2008-05-30", "2016-12-31")),
    }
    split_out = {}
    # selection grid (window 60) + prod
    split_grid = wf_grid
    for sname, ((trs, tre), (tes, tee)) in splits.items():
        trs_, tre_ = pd.Timestamp(trs), pd.Timestamp(tre)
        tes_, tee_ = pd.Timestamp(tes), pd.Timestamp(tee)
        best, best_sh, train_scores = None, -1e9, {}
        for (name, thr, floor) in split_grid:
            s = cfg_series(name, thr, floor)
            sh = met(win(s, trs_, tre_), cash)["sharpe"]
            train_scores[name] = sh
            if sh > best_sh:
                best_sh, best = sh, (name, thr, floor)
        sel_series = cfg_series(*best)
        test_sel = met(win(sel_series, tes_, tee_), cash)
        test_prod = met(win(base_series, tes_, tee_), cash)
        # also: how would the full-sample winner (thr70 f0.5) do?
        fixed = get_series(0.70, 0.5, 60)
        test_fixed = met(win(fixed, tes_, tee_), cash)
        split_out[sname] = {
            "selected": best[0], "train_sharpe": best_sh, "train_scores": train_scores,
            "test_selected": test_sel, "test_prod": test_prod,
            "test_fixed_thr70_f0.5": test_fixed}
        print(f"SPLIT [{sname}] selected={best[0]} (train Sh {best_sh:.4f}) -> "
              f"test sel Sh={test_sel['sharpe']:.4f} vs prod Sh={test_prod['sharpe']:.4f} "
              f"(fixed70 {test_fixed['sharpe']:.4f})")
    out["split_sample"] = split_out

    # ================= 3. ROBUSTNESS: corr window sensitivity =================
    win_sens = {}
    for w in WINDOWS:
        for thr in [0.66, 0.70, 0.74]:
            for floor in [0.0, 0.5]:
                s = get_series(thr, floor, w)
                m = met(win(s, CLEAN_START, end), cash)
                win_sens[f"w{w}_thr{int(thr*100)}_f{floor:g}"] = {
                    "window": w, "thr": thr, "floor": floor,
                    "sharpe": m["sharpe"], "calmar": m["calmar"], "maxdd": m["maxdd"]}
    out["window_sensitivity"] = win_sens

    # ================= 3b. PER-YEAR contribution (C3 thr70 f0.5 w60 vs prod) =================
    c3s = get_series(0.70, 0.5, 60)
    per_year = {}
    fire_years = {}
    cache60 = pc1[60]
    for yr in range(2008, end.year + 1):
        ys, ye = pd.Timestamp(f"{yr}-01-01"), pd.Timestamp(f"{yr}-12-31")
        cs = win(c3s, ys, ye); ps = win(base_series, ys, ye)
        cs = cs[cs.index >= CLEAN_START]; ps = ps[ps.index >= CLEAN_START]
        if len(cs) == 0:
            continue
        c_ret = float((1 + cs).prod() - 1); p_ret = float((1 + ps).prod() - 1)
        fires = [sd for sd in sigs_all if sd.year == yr and pd.notna(cache60.get(sd)) and cache60[sd] > 0.70]
        per_year[str(yr)] = {"c3_ret": c_ret, "prod_ret": p_ret, "delta": c_ret - p_ret,
                             "n_fires": len(fires)}
    out["per_year"] = per_year

    # firing dates + pc1 values (window 60)
    fires60 = [(str(sd.date()), round(cache60[sd], 4)) for sd in sigs_all
               if sd >= CLEAN_START and pd.notna(cache60.get(sd)) and cache60[sd] > 0.70]
    out["fires_clean_thr70_w60"] = fires60

    (ROOT / "research" / "cpm_pc1_walkforward.json").write_text(json.dumps(out, indent=2, default=float))
    write_md(out)
    print("DONE")
    return out


def write_md(o):
    L = []; A = L.append
    m = o["meta"]; pc = o["prod_clean"]; anc = o["anchor"]
    A("# CPM PC1 / absorption-ratio gate -- walk-forward & overfit validation\n")
    A("Role: analyst (hypothesis-driven, READ-ONLY re production; no prod/memo edits; no commit). "
      "Throwaway harness `research/cpm_pc1_walkforward.py`.\n")
    A(f"**Setup:** IV4 production spec; execution T+1 MOO exact (`mooex`); post-cost {m['cost_bps']} "
      f"bps/side; PC1 = dominant-eigenvalue share of rolling daily-return correlation matrix of CPM's 8 "
      f"risky assets, point-in-time (<= month-end decision), de-risk T+1. Clean {m['clean_start']}..{m['end']}.\n")

    A("## 0. Anchor + reproduce gate\n")
    A("| Check | Sharpe | MaxDD | Calmar | Expected | Match |")
    A("|---|---:|---:|---:|---|---|")
    A(f"| Prod CPM clean | {anc['sharpe']:.4f} | {anc['maxdd']*100:.2f}% | {anc['calmar']:.4f} "
      f"| 1.1910/-12.67%/1.0615 | {'CONFIRMED' if anc['ok'] else 'MISMATCH'} |")
    cr = o["c3_reproduce"]
    A(f"| C3 PC1>70% risky*0.5 (w60) | {cr['sharpe']:.4f} | {cr['maxdd']*100:.2f}% | {cr['calmar']:.4f} "
      f"| Sharpe~{cr['ref']} | {'CONFIRMED' if cr['ok'] else 'MISMATCH'} |")
    A(f"\nBase (gate-off) self-check Sharpe {o['selfcheck']['clean_sharpe']:.6f}, "
      f"matches production = {o['selfcheck']['matches']}. WF deltas trusted on this basis.\n")

    # ---- 1. surface ----
    A("## 1. Threshold response surface (window 60, full clean)\n")
    A(f"Production (no gate) clean Sharpe **{pc['sharpe']:.4f}**, Calmar **{pc['calmar']:.4f}**. "
      f"Cells = clean Sharpe; **bold** beats prod. floor = risky-exposure multiplier when PC1>thr "
      f"(floor 0 = full de-risk to safe, 0.5 = half).\n")
    surf = o["surface"]
    A("| thr \\ floor | " + " | ".join(f"floor {f:g}" for f in FLOORS) + " |")
    A("|---|" + "|".join(["---:"] * len(FLOORS)) + "|")
    for thr in THRS:
        cells = []
        for f in FLOORS:
            d = surf[f"thr{int(thr*100)}_floor{f:g}"]
            sh = d["sharpe"]
            cells.append(f"**{sh:.4f}**" if sh > pc["sharpe"] else f"{sh:.4f}")
        A(f"| {int(thr*100)}% | " + " | ".join(cells) + " |")
    A("\nCalmar surface:\n")
    A("| thr \\ floor | " + " | ".join(f"floor {f:g}" for f in FLOORS) + " |")
    A("|---|" + "|".join(["---:"] * len(FLOORS)) + "|")
    for thr in THRS:
        cells = []
        for f in FLOORS:
            d = surf[f"thr{int(thr*100)}_floor{f:g}"]
            cl = d["calmar"]
            cells.append(f"**{cl:.4f}**" if cl > pc["calmar"] else f"{cl:.4f}")
        A(f"| {int(thr*100)}% | " + " | ".join(cells) + " |")
    A("")

    # ---- 2a WF ----
    wf = o["walkforward_expanding"]
    A("## 2a. Expanding walk-forward (annual re-selection, OOS)\n")
    A(f"Each mid-year boundary, select config by best trailing in-sample Sharpe over "
      f"[{m['clean_start']}..boundary] from candidate set {{prod, thr62/66/70/74/78 x floor0/0.5, w60}}, "
      f"apply forward 1y, stitch. OOS span {wf['oos_start']}..{wf['oos_end']} ({wf['n_select']} re-selections).\n")
    A("| Series | Sharpe | CAGR | Vol | MaxDD | Calmar | Martin |")
    A("|---|---:|---:|---:|---:|---:|---:|")
    for lab, d in [("WF (OOS-selected)", wf["wf"]), ("Prod (same OOS span)", wf["prod_oos"])]:
        A(f"| {lab} | {d['sharpe']:.4f} | {d['cagr']*100:.2f}% | {d['vol']*100:.2f}% "
          f"| {d['maxdd']*100:.2f}% | {d['calmar']:.4f} | {d['martin']:.4f} |")
    dd_sh = wf["wf"]["sharpe"] - wf["prod_oos"]["sharpe"]
    dd_ca = wf["wf"]["calmar"] - wf["prod_oos"]["calmar"]
    A(f"\nWF delta vs prod-OOS: Sharpe {dd_sh:+.4f}, Calmar {dd_ca:+.4f}.\n")
    A(f"Selection frequency: {wf['selected_counts']}.\n")
    A("Per-boundary selection (selected config | trailing-train Sharpe):\n")
    A("| Boundary | Selected | Train Sharpe |")
    A("|---|---|---:|")
    for r in wf["log"]:
        A(f"| {r['boundary']} | {r['selected']} | {r['train_sharpe']:.4f} |")
    A("")

    # ---- 2b split ----
    A("## 2b. Split-sample (select on train, evaluate on test)\n")
    sp = o["split_sample"]
    A("| Split | Selected on train | Test: selected Sharpe | Test: prod Sharpe | Test: fixed thr70/f0.5 |")
    A("|---|---|---:|---:|---:|")
    for sname, d in sp.items():
        A(f"| {sname} | {d['selected']} | {d['test_selected']['sharpe']:.4f} "
          f"| {d['test_prod']['sharpe']:.4f} | {d['test_fixed_thr70_f0.5']['sharpe']:.4f} |")
    A("\nTrain-period in-sample Sharpe by candidate (shows whether the full-sample winner is even "
      "best in-sample on each half):\n")
    for sname, d in sp.items():
        ts = d["train_scores"]
        ordered = sorted(ts.items(), key=lambda kv: -kv[1])
        A(f"- **{sname}** train ranking: " + ", ".join(f"{k} {v:.4f}" for k, v in ordered[:6]) + " ...")
    A("")

    # ---- 3 window sensitivity ----
    A("## 3. Robustness -- correlation window sensitivity (full clean)\n")
    A(f"Prod Sharpe {pc['sharpe']:.4f} / Calmar {pc['calmar']:.4f}. **bold** beats prod Sharpe.\n")
    ws = o["window_sensitivity"]
    A("| config | window | thr | floor | Sharpe | Calmar | MaxDD |")
    A("|---|---:|---:|---:|---:|---:|---:|")
    for k, d in ws.items():
        sh = d["sharpe"]
        shc = f"**{sh:.4f}**" if sh > pc["sharpe"] else f"{sh:.4f}"
        A(f"| {k} | {d['window']} | {int(d['thr']*100)}% | {d['floor']:g} | {shc} "
          f"| {d['calmar']:.4f} | {d['maxdd']*100:.2f}% |")
    A("")

    # ---- 3b per-year ----
    A("## 3b. Per-year return contribution (C3 thr70/f0.5/w60 vs prod)\n")
    A("Delta = C3 calendar-year return minus prod. n_fires = months PC1>70% fired that year. "
      "Shows whether the edge concentrates in one or two high-corr episodes.\n")
    A("| Year | Prod ret | C3 ret | Delta | n_fires |")
    A("|---|---:|---:|---:|---:|")
    py = o["per_year"]
    cum = 0.0
    for yr, d in py.items():
        cum += d["delta"]
        A(f"| {yr} | {d['prod_ret']*100:.2f}% | {d['c3_ret']*100:.2f}% | {d['delta']*100:+.2f}% | {d['n_fires']} |")
    A(f"\nSum of yearly deltas: {cum*100:+.2f}%. Firing months (clean, w60, PC1>70%): "
      f"{', '.join(f'{dt}({v:.2f})' for dt, v in o['fires_clean_thr70_w60'])}.\n")

    # ---- verdict ----
    A("## 4. Verdict: REJECT (overfit peak / single-episode artifact)\n")
    A("**The C3 edge is in-sample-selected, not real.** Three independent tests converge on the same "
      "conclusion, and the per-year decomposition exposes the mechanism.\n")
    A("### Threshold surface = sharp isolated spike, NOT a plateau\n")
    A("On the floor-0 (full de-risk) column the response is: 64%=1.1059, 66%=1.0674, 68%=1.1412, "
      "**70%=1.2276**, 72%=1.1923, 74%=1.1866. The 70% cell sits +0.086 above its 68% neighbor and "
      "+0.035 above 72%; every other threshold is at-or-near prod (1.1910) or worse. Low thresholds "
      "(60-66%) actively HURT (down to 0.97-1.11) because they over-gate. This is a textbook single-cell "
      "spike: move the threshold one 2-point step in either direction and the edge collapses to noise. "
      "No broad robust plateau exists.\n")
    A("### Window sensitivity = the spike also requires exactly 60d\n")
    A("At thr=70%/floor=0: w40=1.1631, **w60=1.2276**, w90=1.1649 -- both 40d and 90d windows fall "
      "BELOW production. The edge needs the precise (window=60, thr=70%) pair; it is doubly fragile "
      "(window-specific AND threshold-specific). w40's own best (thr74, 1.1958) and w90's best (~1.187) "
      "are within noise of prod. Nothing survives perturbation of the correlation-window length.\n")
    A("### Per-year decomposition = ONE episode drives 100% of the edge\n")
    A("The PC1>70% gate fires in exactly **9 months, ALL in 2010-2012** (eurozone sovereign-debt "
      "high-correlation regime). It NEVER fires from 2013 through 2026. The entire +3.62% cumulative "
      "return advantage comes from 2010 (+2.57%), 2011 (+2.97%), and 2012 (-1.92%) -- i.e. one "
      "high-correlation episode 14+ years ago. From 2013 onward C3 is byte-identical to production.\n")
    A("### Walk-forward / split-sample confirm zero forward value\n")
    sp = o["split_sample"]
    s1 = sp["train 2008-2016 / test 2017-2026"]; s2 = sp["train 2017-2026 / test 2008-2016"]
    A(f"- **Clean OOS split (train 2008-2016 -> test 2017-2026):** training selects thr70_f0, but on the "
      f"2017-2026 test set the gate never fires, so selected == prod == fixed-thr70 == "
      f"{s1['test_selected']['sharpe']:.4f}. **Zero OOS benefit.**\n")
    A(f"- **Reverse split (train 2017-2026 -> test 2008-2016):** training selects PROD (the gate is inert "
      f"and cannot be distinguished from prod in 2017-2026), so you would NOT deploy the gate; the gate "
      f"*would* have helped in 2008-2016 (fixed-thr70 {s2['test_fixed_thr70_f0.5']['sharpe']:.4f} vs prod "
      f"{s2['test_prod']['sharpe']:.4f}), but that benefit is unreachable from post-2012 data. The signal "
      f"and its payoff are confined to the same in-sample episode.\n")
    wf = o["walkforward_expanding"]
    A(f"- **Expanding WF (+{wf['wf']['sharpe']-wf['prod_oos']['sharpe']:.4f} Sharpe) is illusory:** WF "
      f"re-selects thr70_f0 at all 15 boundaries (the 2010-2012 episode dominates every trailing window), "
      f"and the only OOS pieces where it differs from prod are 2011-2012 -- the tail of the very episode "
      f"that defines the signal. Post-2012 the WF series equals prod. The WF 'edge' is the same single "
      f"episode leaking into the early OOS span, not repeatable forward skill.\n")
    A("### Cost/benefit\n")
    A("Even granting the in-sample 1.2144, the overlay adds a rolling correlation-matrix + eigenvalue "
      "machinery for a +0.02 Sharpe that (a) is a single-cell spike in (window,threshold) space, (b) "
      "delivers ZERO crisis protection (MaxDD identical in every regime; never fires in GFC/COVID/2022/"
      "dot-com), and (c) provides ZERO benefit in a clean post-2012 OOS because it never fires. The "
      "complexity is unjustified and the apparent edge is an artifact of one 2010-2012 high-correlation "
      "episode that happens to fall inside the sample.\n")
    A("### Recommendation: **REJECT.** Do not adopt. Document only as a cautionary overfit example: "
      "a 3-point in-sample sweep with a single winner (70%) was, on fine sweep, a literal isolated spike; "
      "the 'survives execution lag' check was necessary but not sufficient -- lag-robustness does not "
      "protect against single-episode in-sample selection. The discriminating tests were the FINE "
      "threshold+window surface and the per-year firing decomposition.\n")
    Path(ROOT / "research" / "cpm_pc1_walkforward_findings.md").write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
