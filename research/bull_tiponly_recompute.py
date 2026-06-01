# -*- coding: utf-8 -*-
"""Throwaway research (analyst role; read-only re production; writes only to
research/; NO production/memo files changed; NO commit). Recomputes the CANONICAL
two-sleeve number set under the NEW production spec where the BULL canary was
changed to TIP-ONLY (bull_spy_live.CANARY_ASSETS=["TIP"]). CPM is UNCHANGED
(HYG-OR-TIP). This regenerates the headline that REPLACES the old
1.2485/-10.68%/1.1928 (which assumed BULL HYG-OR-TIP).

Sleeves are taken from the PRODUCTION modules via the canonical harness
exec_lag_moo_validation_2026_05_30 (H):
  - CPM : H.cpm_sleeve_conv  -> cpm_live.compute_target_weights (HYG-OR-TIP, unchanged)
  - BULL: H.bull_sleeve_conv -> bull_spy_live.compute_bull_spy_weights, which now
          reads the production CANARY_ASSETS=["TIP"] => BULL TIP-only. Slow vol gate
          GATE_RV60 (rv_60d<rv_252d) monkeypatched in (= production gate).
  - NDX : moc_vs_moo_analysis.run_ndx_backtest_with_offset(offset=1) (PROD 60/20/20 only).

CANONICAL conventions (held identical to prior anchor-gated sets):
  T+1 MOO exact ("mooex", real auto_adjust opens), post-cost 10 bps/side.
  Windows: clean 2008-05-30..2026-05-22 (18y); ext/stress 1999-03-10..2026-05-22 (27y).
  Metrics from production perf_metrics: CAGR, Vol, raw Sharpe (rf=0),
  Excess Sharpe vs SHV, MaxDD, Calmar (=CAGR/|MaxDD|), Martin, 2022 cal return.

ANCHOR GATE (abort/flag on mismatch):
  CPM-solo clean Sharpe 1.1910 / MaxDD -12.67% / Calmar 1.0615  (UNCHANGED, exact).
  BULL TIP-only clean Sharpe ~1.1005 / MaxDD -13.35% (canary-test mooex run; approx,
  flagged not aborted).

V-effect decomposition (section 6): reuse factorial_decomposition_2026_05_30.bull_wf
holding canary=TIP-only (K=0) and safe=SHV/IEF (S=1), toggling the vol gate V:
  HAA-Simple (TIP+SPY, K=0,V=0,S=1)  ->  BULL-TIP-only (TIP+SPY+vol, K=0,V=1,S=1).

Writes research/bull_tiponly_recompute_findings.md (+ .json).
"""
from __future__ import annotations
import sys, json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import exec_lag_moo_validation_2026_05_30 as H
from cpm_live import load_panel, perf_metrics, sig_13612U, COST_BPS_PER_SIDE
import bull_spy_live
import ndx_sleeve_live as ndx_sleeve
from moc_vs_moo_analysis import run_ndx_backtest_with_offset

CONV = "mooex"
COST = COST_BPS_PER_SIDE  # 10
CLEAN_START = pd.Timestamp("2008-05-30")
EXT_START = pd.Timestamp("1999-03-10")
END = pd.Timestamp("2026-05-22")

# Anchor gate.
ANCHOR_CPM = {"sharpe": 1.1910, "maxdd": -12.67, "calmar": 1.0615}     # exact, UNCHANGED
ANCHOR_BULL = {"sharpe": 1.1005, "maxdd": -13.35}                       # approx (flag only)

SWEEP = [(0.80, 0.20), (0.70, 0.30), (0.60, 0.40), (0.50, 0.50), (0.40, 0.60), (0.30, 0.70)]
B_ITER, BLOCK, SEED = 2000, 21, 42
REGIMES = {
    "Dot-com (2000-03..2002-12)": ("2000-03-01", "2002-12-31"),
    "GFC (2007-10..2009-06)":     ("2007-10-01", "2009-06-30"),
    "COVID (2020-02..2020-06)":   ("2020-02-01", "2020-06-30"),
    "2022 bear (2022-01..2022-12)": ("2022-01-01", "2022-12-31"),
}


# ---- local BULL parametric weight fn (V-effect decomposition) ----
# Mirrors factorial_decomposition_2026_05_30.bull_wf but self-contained (that harness
# imports stale cpm_live symbols removed in the single-stage refactor). Factors:
#   K canary : TIP-only (K=0) vs HYG-OR-TIP (K=1).  V vol gate: off (0) vs rv60<rv252 (1).
#   S safe   : {BIL,AGG} (0) vs {SHV,IEF} (1).  SPY 13612U>0 trend gate fixed-on.
BULL_PROD_SAFE = ["SHV", "IEF"]


def _pick_safe_pool(monthly, pool):
    scores = {}
    for s in pool:
        if s in monthly.columns:
            sc = sig_13612U(monthly[s])
            if pd.notna(sc):
                scores[s] = sc
    return max(scores, key=scores.get) if scores else "SHV"


def bull_wf(close, sig_d, daily_spy, K, V, S):
    monthly = close.loc[:sig_d].resample("ME").last()
    safe = _pick_safe_pool(monthly, BULL_PROD_SAFE if S else ["BIL", "AGG"])
    if K:
        cs = [sig_13612U(monthly[a]) for a in ["HYG", "TIP"] if a in monthly.columns]
        cs = [s for s in cs if pd.notna(s)]
        canary_ok = any(s > 0 for s in cs) if cs else False
    else:
        tipm = sig_13612U(monthly["TIP"]) if "TIP" in monthly.columns else float("nan")
        canary_ok = pd.notna(tipm) and tipm > 0
    spym = sig_13612U(monthly["SPY"]) if "SPY" in monthly.columns else float("nan")
    trend_ok = pd.notna(spym) and spym > 0
    if V:
        sub = daily_spy.loc[:sig_d].pct_change().dropna()
        vol_ok = True if len(sub) < 252 else (float(sub.tail(60).std()) < float(sub.tail(252).std()))
    else:
        vol_ok = True
    return {"SPY": 1.0} if (canary_ok and trend_ok and vol_ok) else {safe: 1.0}


def run_bull_cell(close, daily, intraday, overnight, daily_spy, start, end, K, V, S):
    wf = lambda sd: bull_wf(close, sd, daily_spy, K, V, S)
    s, _ = H._segment_returns_conv(close, daily, wf, start, end, CONV,
                                   COST_BPS_PER_SIDE, intraday, overnight)
    return s


def met(s, cash):
    m = perf_metrics(s, cash)
    return {"sharpe": m.get("sharpe"), "cagr": m.get("cagr"), "vol": m.get("vol"),
            "excess_sharpe": m.get("excess_sharpe"), "maxdd": m.get("max_drawdown"),
            "calmar": m.get("calmar"), "martin": m.get("martin")}


def win(s, start, end):
    return s.loc[(s.index >= start) & (s.index <= end)]


def cal2022(s):
    sub = s.loc["2022-01-01":"2022-12-31"]
    return float((1.0 + sub).prod() - 1.0) if len(sub) else float("nan")


# ---- stationary block bootstrap (matches two_sleeve_60_40_ci_walkforward) ----
def _sbb(daily, block_size=BLOCK, rng=None):
    if rng is None:
        rng = np.random.default_rng()
    n = len(daily); arr = daily.values; blocks = []
    for _ in range((n // block_size) + 1):
        s = rng.integers(0, n); e = s + block_size
        if e <= n:
            blocks.append(arr[s:e])
        else:
            blocks.append(np.concatenate([arr[s:], arr[:e - n]]))
    return pd.Series(np.concatenate(blocks)[:n], index=daily.index)


def bootstrap_ci(daily, n_iter=B_ITER, block_size=BLOCK, seed=SEED):
    rng = np.random.default_rng(seed)
    keys = ["sharpe", "cagr", "vol", "maxdd", "calmar"]
    boot = {k: [] for k in keys}
    for _ in range(n_iter):
        b = _sbb(daily, block_size, rng)
        m = perf_metrics(b)
        boot["sharpe"].append(m.get("sharpe")); boot["cagr"].append(m.get("cagr"))
        boot["vol"].append(m.get("vol")); boot["maxdd"].append(m.get("max_drawdown"))
        boot["calmar"].append(m.get("calmar"))
    out = {}
    for k in keys:
        a = np.array(boot[k], dtype=float); a = a[np.isfinite(a)]
        out[k] = {"p2.5": float(np.percentile(a, 2.5)), "p50": float(np.percentile(a, 50)),
                  "p97.5": float(np.percentile(a, 97.5)), "mean": float(a.mean())}
    return out


def main():
    panel = load_panel(start=EXT_START, end=END)
    end = min(END, panel.index[-1])
    cash = panel["SHV"].ffill().pct_change().dropna()
    od, cy = H.load_open_close()
    intraday = (cy / od - 1.0).reindex(panel.index)
    overnight = (od / cy.shift(1) - 1.0).reindex(panel.index)

    # ---- sleeves ----
    cpm, _ = H.cpm_sleeve_conv(panel, intraday, overnight, EXT_START, end, CONV)
    # BULL reads production CANARY_ASSETS (now ["TIP"]) -> TIP-only.
    assert bull_spy_live.CANARY_ASSETS == ["TIP"], \
        f"production BULL canary must be TIP-only, got {bull_spy_live.CANARY_ASSETS}"
    bull, _ = H.bull_sleeve_conv(panel, intraday, overnight, EXT_START, end, CONV, H.GATE_RV60)
    common = cpm.index.intersection(bull.index)
    cpm = cpm.reindex(common); bull = bull.reindex(common)

    ndx_panel = ndx_sleeve.load_ndx_panel()
    ndx = run_ndx_backtest_with_offset(panel, ndx_panel, EXT_START, end, offset=1)
    ndx = ndx.reindex(common).fillna(0.0)

    # ======================= ANCHOR GATE =======================
    print("=== ANCHOR GATE ===")
    cpm_cl = met(win(cpm, CLEAN_START, end), cash)
    ok_cpm = (abs(cpm_cl["sharpe"] - ANCHOR_CPM["sharpe"]) < 5e-4
              and abs(cpm_cl["maxdd"] * 100 - ANCHOR_CPM["maxdd"]) < 0.02
              and abs(cpm_cl["calmar"] - ANCHOR_CPM["calmar"]) < 5e-4)
    print(f"  CPM-solo clean: Sharpe={cpm_cl['sharpe']:.4f} MaxDD={cpm_cl['maxdd']*100:.2f}% "
          f"Calmar={cpm_cl['calmar']:.4f} expect {ANCHOR_CPM} -> {'OK' if ok_cpm else 'MISMATCH'}")

    bull_cl = met(win(bull, CLEAN_START, end), cash)
    bull_ds = abs(bull_cl["sharpe"] - ANCHOR_BULL["sharpe"])
    bull_dd = abs(bull_cl["maxdd"] * 100 - ANCHOR_BULL["maxdd"])
    ok_bull = (bull_ds < 0.01 and bull_dd < 0.10)
    print(f"  BULL TIP-only clean: Sharpe={bull_cl['sharpe']:.4f} MaxDD={bull_cl['maxdd']*100:.2f}% "
          f"Calmar={bull_cl['calmar']:.4f} expect ~{ANCHOR_BULL} "
          f"(dS={bull_ds:.4f}, dDD={bull_dd:.3f}) -> {'OK' if ok_bull else 'FLAG'}")

    if not ok_cpm:
        print("CPM ANCHOR MISMATCH -- aborting (CPM must be unchanged).")
        sys.exit(1)
    print(f"CPM anchor CONFIRMED. BULL anchor {'CONFIRMED' if ok_bull else 'FLAGGED (does not reproduce ~1.1005/-13.35%)'}\n")

    out = {"meta": {"conv": CONV, "cost_bps": COST,
                    "clean": [str(CLEAN_START.date()), str(end.date())],
                    "stress": [str(EXT_START.date()), str(end.date())],
                    "prod_bull_canary": list(bull_spy_live.CANARY_ASSETS),
                    "cpm_canary": "HYG-OR-TIP (unchanged)",
                    "ndx_convention": "T+1 MOO offset=1 (close-to-close; exact-open engine "
                                      "unsupported for per-stock PIT NDX universe + delisting)",
                    "cpm_bull_convention": "T+1 MOO exact (mooex, real auto_adjust opens)"},
           "anchor": {"cpm_solo_clean": cpm_cl, "cpm_gate_ok": ok_cpm,
                      "bull_tiponly_clean": bull_cl, "bull_gate_ok": ok_bull,
                      "bull_anchor_expected": ANCHOR_BULL}}

    # ======================= SECTION 1: BULL sleeve clean+ext =======================
    out["bull_sleeve"] = {"clean": met(win(bull, CLEAN_START, end), cash),
                          "ext": met(win(bull, EXT_START, end), cash)}

    # ======================= SECTION 2: blends 60/40 + 50/50 + PROD =======================
    prod = 0.60 * cpm + 0.20 * bull + 0.20 * ndx
    sec_blend = {}
    for label, wc, wb in [("60/40", 0.60, 0.40), ("50/50", 0.50, 0.50)]:
        b = wc * cpm + wb * bull
        sec_blend[label] = {"clean": met(win(b, CLEAN_START, end), cash),
                            "ext": met(win(b, EXT_START, end), cash),
                            "ret_2022": cal2022(win(b, CLEAN_START, end))}
    sec_blend["PROD_60_20_20"] = {"clean": met(win(prod, CLEAN_START, end), cash),
                                  "ext": met(win(prod, EXT_START, end), cash),
                                  "ret_2022": cal2022(win(prod, CLEAN_START, end))}
    out["blends"] = sec_blend

    # ======================= SECTION 3: weight-insensitivity sweep =======================
    sweep = []
    for wc, wb in SWEEP:
        b = wc * cpm + wb * bull
        mc = met(win(b, CLEAN_START, end), cash); ms = met(win(b, EXT_START, end), cash)
        sweep.append({"w_cpm": wc, "w_bull": wb,
                      "clean_sharpe": mc["sharpe"], "clean_maxdd": mc["maxdd"],
                      "stress_sharpe": ms["sharpe"], "stress_maxdd": ms["maxdd"]})
    cl_sh = [r["clean_sharpe"] for r in sweep]; st_sh = [r["stress_sharpe"] for r in sweep]
    out["sweep"] = {"sweep": sweep,
                    "clean_band": max(cl_sh) - min(cl_sh), "stress_band": max(st_sh) - min(st_sh),
                    "clean_min": min(cl_sh), "clean_max": max(cl_sh),
                    "stress_min": min(st_sh), "stress_max": max(st_sh),
                    "clean_argmax": SWEEP[int(np.argmax(cl_sh))], "clean_argmin": SWEEP[int(np.argmin(cl_sh))],
                    "stress_argmax": SWEEP[int(np.argmax(st_sh))], "stress_argmin": SWEEP[int(np.argmin(st_sh))]}

    # ======================= SECTION 4: correlation =======================
    out["corr"] = {"clean": float(win(cpm, CLEAN_START, end).corr(win(bull, CLEAN_START, end))),
                   "stress": float(win(cpm, EXT_START, end).corr(win(bull, EXT_START, end)))}

    # side-by-side standalone (clean)
    out["side_by_side_clean"] = {
        "CPM": {**met(win(cpm, CLEAN_START, end), cash), "ret_2022": cal2022(win(cpm, CLEAN_START, end))},
        "BULL": {**met(win(bull, CLEAN_START, end), cash), "ret_2022": cal2022(win(bull, CLEAN_START, end))},
        "NDX": {**met(win(ndx, CLEAN_START, end), cash), "ret_2022": cal2022(win(ndx, CLEAN_START, end))},
        "60/40": {**sec_blend["60/40"]["clean"], "ret_2022": sec_blend["60/40"]["ret_2022"]},
        "50/50": {**sec_blend["50/50"]["clean"], "ret_2022": sec_blend["50/50"]["ret_2022"]},
        "PROD_60_20_20": {**sec_blend["PROD_60_20_20"]["clean"], "ret_2022": sec_blend["PROD_60_20_20"]["ret_2022"]},
    }

    # ======================= SECTION 5: crisis windows + bootstrap CI (60/40 clean) =======================
    blend6040 = 0.60 * cpm + 0.40 * bull
    crisis = {}
    for name, (lo, hi) in REGIMES.items():
        sub = blend6040.loc[(blend6040.index >= pd.Timestamp(lo)) & (blend6040.index <= pd.Timestamp(hi))]
        if len(sub) >= 5:
            m = met(sub, cash)
            crisis[name] = {"cagr": m["cagr"], "maxdd": m["maxdd"], "sharpe": m["sharpe"],
                            "ret": float((1.0 + sub).prod() - 1.0), "n": len(sub)}
        else:
            crisis[name] = {"note": "insufficient data (proxy/NDX coverage)", "n": len(sub)}
    boot_clean = win(blend6040, CLEAN_START, end)
    out["crisis"] = crisis
    out["bootstrap_6040_clean"] = bootstrap_ci(boot_clean)

    # ======================= SECTION 6: V-effect decomposition (HAA-Simple -> BULL TIP-only) =======================
    bull_cols = sorted(set(["SPY", "HYG", "TIP", "SHV", "IEF"]) & set(panel.columns))
    bclose = panel[bull_cols]; bdaily = bclose.ffill().pct_change(); daily_spy = panel["SPY"]
    # K=0 (TIP-only canary), S=1 (SHV/IEF safe) fixed; toggle V.
    haa = run_bull_cell(bclose, bdaily, intraday, overnight, daily_spy, EXT_START, end, K=0, V=0, S=1)
    bullv = run_bull_cell(bclose, bdaily, intraday, overnight, daily_spy, EXT_START, end, K=0, V=1, S=1)
    haa = haa.reindex(common); bullv = bullv.reindex(common)
    # cross-check: bull_wf(K0,V1,S1) ~= production H.bull_sleeve (both TIP-only + vol + SHV/IEF + SPY trend)
    xcheck = met(win(bullv, CLEAN_START, end), cash)
    xc_dS = abs(xcheck["sharpe"] - bull_cl["sharpe"])
    out["v_effect"] = {
        "HAA_Simple_TIP_SPY": {"clean": met(win(haa, CLEAN_START, end), cash),
                               "ext": met(win(haa, EXT_START, end), cash)},
        "BULL_TIP_only_TIP_SPY_vol": {"clean": met(win(bullv, CLEAN_START, end), cash),
                                      "ext": met(win(bullv, EXT_START, end), cash)},
        "xcheck_bullwf_vs_prod_clean": {"bullwf_sharpe": xcheck["sharpe"],
                                        "prod_sharpe": bull_cl["sharpe"], "abs_diff": xc_dS,
                                        "match": xc_dS < 0.02},
    }
    # V main effect deltas (clean + ext), holding K=0,S=1.
    for wlab, ws in [("clean", CLEAN_START), ("ext", EXT_START)]:
        h = met(win(haa, ws, end), cash); v = met(win(bullv, ws, end), cash)
        out["v_effect"][f"V_delta_{wlab}"] = {
            "d_sharpe": v["sharpe"] - h["sharpe"], "d_calmar": v["calmar"] - h["calmar"],
            "d_maxdd_pp": (abs(v["maxdd"]) - abs(h["maxdd"])) * 100, "d_cagr_pp": (v["cagr"] - h["cagr"]) * 100}

    Path(__file__).with_suffix(".json").write_text(json.dumps(out, indent=2, default=float))
    write_md(out)
    print("DONE -> research/bull_tiponly_recompute_findings.md")
    return out


def write_md(o):
    L = []; A = L.append
    m = o["meta"]

    def pct(x):
        return f"{x*100:.2f}%" if x is not None and np.isfinite(x) else "n/a"

    A("# BULL TIP-only recompute -- canonical number set under NEW production\n")
    A("Role: analyst (hypothesis-driven, read-only re production; writes only to research/; "
      "no production/memo files changed; no commit). Harness "
      "`research/bull_tiponly_recompute.py`. Production BULL canary was changed to TIP-ONLY "
      "(`bull_spy_live.CANARY_ASSETS=[\"TIP\"]`); CPM is UNCHANGED (HYG-OR-TIP). This file is the "
      "FRESH number set that REPLACES the old 60/40 headline 1.2485 / -10.68% / 1.1928 (which "
      "assumed BULL HYG-OR-TIP).\n")
    A(f"**Sleeves from production modules** via canonical harness "
      f"`exec_lag_moo_validation_2026_05_30`: CPM = `cpm_live.compute_target_weights` "
      f"(HYG-OR-TIP, unchanged); BULL = `bull_spy_live.compute_bull_spy_weights` reading "
      f"production `CANARY_ASSETS={m['prod_bull_canary']}` (TIP-only) + slow vol gate "
      f"rv_60d<rv_252d; NDX = production sleeve (PROD 60/20/20 only).\n")
    A(f"**Conventions (canonical):** T+1 MOO exact (`mooex`, real auto_adjust opens), post-cost "
      f"{m['cost_bps']} bps/side. Metrics from production `perf_metrics`: CAGR, Vol, raw Sharpe "
      f"(rf=0), Excess Sharpe vs SHV, MaxDD, Calmar (=CAGR/|MaxDD|), Martin, 2022 cal return. "
      f"Windows: clean {m['clean'][0]}..{m['clean'][1]} (18y); ext/stress {m['stress'][0]}.."
      f"{m['stress'][1]} (27y).\n")
    A(f"**NDX leg caveat (PROD 60/20/20 only):** runs on the production path under "
      f"{m['ndx_convention']}. The exact-open (`mooex`) engine cannot run the per-stock PIT NDX "
      f"universe with delisting haircuts, so the NDX 20% leg uses close-to-close T+1 MOO while CPM "
      f"60% and BULL 20% legs use exact-open T+1 MOO. CPM and BULL legs are byte-identical between "
      f"the two-sleeve and PROD rows.\n")

    a = o["anchor"]
    ac = a["cpm_solo_clean"]; ab = a["bull_tiponly_clean"]
    A("## 0. Anchor gate (gate-first)\n")
    A("| Gate | Sharpe | MaxDD | Calmar | Expected | Match |")
    A("|---|---:|---:|---:|---|---|")
    A(f"| CPM-solo (clean, UNCHANGED) | {ac['sharpe']:.4f} | {pct(ac['maxdd'])} | {ac['calmar']:.4f} | "
      f"1.1910 / -12.67% / 1.0615 | {'CONFIRMED' if a['cpm_gate_ok'] else 'MISMATCH'} |")
    A(f"| BULL TIP-only (clean) | {ab['sharpe']:.4f} | {pct(ab['maxdd'])} | {ab['calmar']:.4f} | "
      f"~1.1005 / -13.35% | {'CONFIRMED' if a['bull_gate_ok'] else 'FLAG -- does not reproduce'} |")
    A("")
    if a["cpm_gate_ok"] and a["bull_gate_ok"]:
        A("CPM anchor reproduces exactly (unchanged); BULL TIP-only reproduces ~1.1005 / -13.35% "
          "from the canary-test mooex run. Rest of file trusted on that basis.\n")
    else:
        A("**FLAG:** BULL TIP-only did NOT reproduce the expected ~1.1005 / -13.35% within tolerance "
          "(see Sharpe/MaxDD above). CPM unchanged-anchor still holds. Treat BULL-derived numbers "
          "with care.\n")

    # ---- BULL sleeve ----
    bs = o["bull_sleeve"]
    A("## 1. BULL sleeve (TIP-only) standalone\n")
    A("| Window | CAGR | Vol | Raw Sharpe | Excess Sharpe vs SHV | MaxDD | Calmar |")
    A("|---|---:|---:|---:|---:|---:|---:|")
    for wl, k in [("Clean 18y", "clean"), ("Ext 27y", "ext")]:
        r = bs[k]
        A(f"| {wl} | {pct(r['cagr'])} | {pct(r['vol'])} | {r['sharpe']:.4f} | {r['excess_sharpe']:.4f} | "
          f"{pct(r['maxdd'])} | {r['calmar']:.4f} |")
    A("")

    # ---- blends ----
    sb = o["blends"]
    A("## 2. NEW memo headline -- 60/40 blend (CPM HYG-OR-TIP + BULL TIP-only)\n")
    A("Replaces the old 1.2485 / -10.68% / 1.1928. Clean (18y) + ext (27y); 2022 return on clean. "
      "50/50 split and PROD 60/20/20 (3-sleeve, live NDX) re-cited.\n")
    A("| Portfolio | Window | CAGR | Vol | Raw Sharpe | Excess Sharpe vs SHV | MaxDD | Calmar | 2022 Return |")
    A("|---|---|---:|---:|---:|---:|---:|---:|---:|")
    for label in ("60/40", "50/50"):
        r = sb[label]; c = r["clean"]; e = r["ext"]
        A(f"| **CPM/BULL {label}** | Clean | {pct(c['cagr'])} | {pct(c['vol'])} | {c['sharpe']:.4f} | "
          f"{c['excess_sharpe']:.4f} | {pct(c['maxdd'])} | {c['calmar']:.4f} | **{pct(r['ret_2022'])}** |")
        A(f"| | Ext | {pct(e['cagr'])} | {pct(e['vol'])} | {e['sharpe']:.4f} | {e['excess_sharpe']:.4f} | "
          f"{pct(e['maxdd'])} | {e['calmar']:.4f} | |")
    p = sb["PROD_60_20_20"]; pc = p["clean"]; pe = p["ext"]
    A(f"| *PROD 60/20/20* | Clean | {pct(pc['cagr'])} | {pct(pc['vol'])} | {pc['sharpe']:.4f} | "
      f"{pc['excess_sharpe']:.4f} | {pct(pc['maxdd'])} | {pc['calmar']:.4f} | **{pct(p['ret_2022'])}** |")
    A(f"| | Ext | {pct(pe['cagr'])} | {pct(pe['vol'])} | {pe['sharpe']:.4f} | {pe['excess_sharpe']:.4f} | "
      f"{pct(pe['maxdd'])} | {pe['calmar']:.4f} | |")
    A("")

    # ---- sweep ----
    sw = o["sweep"]
    A("## 3. Weight-insensitivity sweep (80/20 -> 30/70)\n")
    A("| CPM Weight | BULL Weight | Clean Sharpe | Clean MaxDD | Stress Sharpe | Stress MaxDD |")
    A("|---|---|---:|---:|---:|---:|")
    for r in sw["sweep"]:
        A(f"| {r['w_cpm']*100:.0f}% | {r['w_bull']*100:.0f}% | {r['clean_sharpe']:.4f} | "
          f"{pct(r['clean_maxdd'])} | {r['stress_sharpe']:.4f} | {pct(r['stress_maxdd'])} |")
    amx = sw["clean_argmax"]; amn = sw["clean_argmin"]; smx = sw["stress_argmax"]; smn = sw["stress_argmin"]
    A(f"\n- **Clean Sharpe band:** {sw['clean_band']:.4f} (low {sw['clean_min']:.4f} at "
      f"{amn[0]*100:.0f}/{amn[1]*100:.0f}, high {sw['clean_max']:.4f} at {amx[0]*100:.0f}/{amx[1]*100:.0f}).")
    A(f"- **Stress Sharpe band:** {sw['stress_band']:.4f} (low {sw['stress_min']:.4f} at "
      f"{smn[0]*100:.0f}/{smn[1]*100:.0f}, high {sw['stress_max']:.4f} at {smx[0]*100:.0f}/{smx[1]*100:.0f}).")
    flat = (sw["clean_band"] <= 0.10) and (sw["stress_band"] <= 0.10)
    A(f"- **Verdict:** {'FLAT (not weight-fitted)' if flat else 'PEAKED'} -- max Sharpe range "
      f"{max(sw['clean_band'], sw['stress_band']):.4f} across the full 80/20..30/70 sweep.\n")

    # ---- correlation ----
    c = o["corr"]
    A("## 4. CPM-BULL correlation (daily returns)\n")
    A(f"- **Clean:** {c['clean']:.4f}")
    A(f"- **Stress/ext:** {c['stress']:.4f}\n")
    A("### Side-by-side standalone vs blends (clean window)\n")
    sbs = o["side_by_side_clean"]
    cols = [("CPM", "CPM"), ("BULL (TIP-only)", "BULL"), ("NDX", "NDX"),
            ("60/40", "60/40"), ("50/50", "50/50"), ("PROD 60/20/20", "PROD_60_20_20")]
    A("| Metric | " + " | ".join(h for h, _ in cols) + " |")
    A("| --- |" + " --- |" * len(cols))

    def rowm(name, fmt):
        return f"| **{name}** | " + " | ".join(fmt(sbs[k]) for _, k in cols) + " |"
    A(rowm("CAGR", lambda d: pct(d['cagr'])))
    A(rowm("Vol", lambda d: pct(d['vol'])))
    A(rowm("Raw Sharpe", lambda d: f"{d['sharpe']:.4f}"))
    A(rowm("Excess Sharpe", lambda d: f"{d['excess_sharpe']:.4f}"))
    A(rowm("MaxDD", lambda d: pct(d['maxdd'])))
    A(rowm("Calmar", lambda d: f"{d['calmar']:.4f}"))
    A(rowm("2022 Return", lambda d: pct(d['ret_2022'])))
    A("")

    # ---- crisis + bootstrap ----
    cr = o["crisis"]
    A("## 5. Crisis windows + bootstrap CI -- NEW 60/40 blend (clean)\n")
    A("### Crisis-window returns (60/40, mooex)\n")
    A("| Regime | Total Return | CAGR | MaxDD | Sharpe | N days |")
    A("|---|---:|---:|---:|---:|---:|")
    for name, r in cr.items():
        if "note" in r:
            A(f"| {name} | n/a | n/a | n/a | n/a | {r['n']} ({r['note']}) |")
        else:
            A(f"| {name} | {pct(r['ret'])} | {pct(r['cagr'])} | {pct(r['maxdd'])} | {r['sharpe']:.4f} | {r['n']} |")
    A("\n*Note: pre-2008 regimes (Dot-com, GFC start) sit in the proxy-backed extended window; "
      "clean 18y starts 2008-05-30 so GFC partially covered.*\n")
    bc = o["bootstrap_6040_clean"]
    A(f"### Bootstrap 95% CI (stationary block bootstrap, B={B_ITER}, block={BLOCK}d, seed={SEED}; clean window)\n")
    A("| Metric | p2.5 | p50 (median) | p97.5 | mean |")
    A("|---|---:|---:|---:|---:|")
    for k, lab in [("sharpe", "Sharpe"), ("cagr", "CAGR"), ("vol", "Vol"), ("maxdd", "MaxDD"), ("calmar", "Calmar")]:
        d = bc[k]
        if k in ("cagr", "vol", "maxdd"):
            A(f"| {lab} | {pct(d['p2.5'])} | {pct(d['p50'])} | {pct(d['p97.5'])} | {pct(d['mean'])} |")
        else:
            A(f"| {lab} | {d['p2.5']:.4f} | {d['p50']:.4f} | {d['p97.5']:.4f} | {d['mean']:.4f} |")
    A("")

    # ---- V effect ----
    v = o["v_effect"]
    A("## 6. BULL decomposition vs HAA-Simple -- the vol-gate (V) effect\n")
    A("Since BULL canary is now TIP-only (shared with HAA-Simple), the canary is no longer a BULL "
      "differentiator. BULL = HAA-Simple + vol gate. Holding canary=TIP-only and safe=SHV/IEF "
      "fixed at production, the vol gate V is the SINGLE differentiator. Both legs run through the "
      "same mooex harness (local `bull_wf`, K=0/S=1; identical logic to the archived "
      "factorial decomposition cell).\n")
    A("| Variant | Window | CAGR | Vol | Sharpe | MaxDD | Calmar |")
    A("|---|---|---:|---:|---:|---:|---:|")
    for name, key in [("HAA-Simple (TIP+SPY)", "HAA_Simple_TIP_SPY"),
                      ("BULL-TIP-only (TIP+SPY+vol)", "BULL_TIP_only_TIP_SPY_vol")]:
        for wl, wk in [("Clean", "clean"), ("Ext", "ext")]:
            r = v[key][wk]
            A(f"| {name} | {wl} | {pct(r['cagr'])} | {pct(r['vol'])} | {r['sharpe']:.4f} | "
              f"{pct(r['maxdd'])} | {r['calmar']:.4f} |")
    dc = v["V_delta_clean"]; de = v["V_delta_ext"]
    A(f"\n**V main effect (vol gate ON minus OFF), clean:** dSharpe {dc['d_sharpe']:+.4f}, "
      f"dCalmar {dc['d_calmar']:+.4f}, dMaxDD {dc['d_maxdd_pp']:+.2f}pp, dCAGR {dc['d_cagr_pp']:+.2f}pp.")
    A(f"\n**V main effect, ext:** dSharpe {de['d_sharpe']:+.4f}, dCalmar {de['d_calmar']:+.4f}, "
      f"dMaxDD {de['d_maxdd_pp']:+.2f}pp, dCAGR {de['d_cagr_pp']:+.2f}pp.")
    xc = v["xcheck_bullwf_vs_prod_clean"]
    A(f"\n*Cross-check: bull_wf(K=0,V=1,S=1) clean Sharpe {xc['bullwf_sharpe']:.4f} vs production "
      f"BULL sleeve {xc['prod_sharpe']:.4f} (|diff|={xc['abs_diff']:.4f}) -> "
      f"{'MATCH' if xc['match'] else 'MISMATCH (flag)'}.*\n")

    # ---- PROD 60/20/20 ----
    pp = sb["PROD_60_20_20"]["clean"]
    A("## 7. PROD 60/20/20 (CPM-BULL-NDX) under new BULL TIP-only -- dashboard headline\n")
    A("| Metric | Value (clean 18y) |")
    A("|---|---:|")
    A(f"| Raw Sharpe | {pp['sharpe']:.4f} |")
    A(f"| Excess Sharpe vs SHV | {pp['excess_sharpe']:.4f} |")
    A(f"| CAGR | {pct(pp['cagr'])} |")
    A(f"| Vol | {pct(pp['vol'])} |")
    A(f"| MaxDD | {pct(pp['maxdd'])} |")
    A(f"| Calmar | {pp['calmar']:.4f} |")
    A(f"| 2022 Return | {pct(sb['PROD_60_20_20']['ret_2022'])} |")
    A(f"\nNDX leg convention: {m['ndx_convention']} (only the 20% NDX leg; CPM 60% and BULL 20% "
      f"legs are exact-open mooex).\n")

    A("## Caveats\n")
    A("- CPM sleeve UNCHANGED (HYG-OR-TIP); CPM-solo numbers and concentration are NOT recomputed "
      "here, only the unchanged anchor is re-cited (Sharpe 1.1910 / MaxDD -12.67% / Calmar 1.0615).")
    A("- BULL sleeve now TIP-only canary (production change); all BULL-derived rows reflect that.")
    A("- CPM & BULL legs: production weight fns run on T+1 MOO exact (mooex, real auto_adjust "
      "opens), 10 bps/side post-cost, BULL slow gate rv_60d<rv_252d.")
    A("- NDX leg (PROD 60/20/20 + NDX standalone): production NDX sleeve under T+1 MOO offset=1 "
      "close-to-close (exact-open engine unsupported for per-stock PIT universe + delisting).")
    A("- Ext/stress window (1999-03-10..) is partially proxy-backed pre-2006-2008; clean 18y has "
      "full real-open coverage and is the decisive lens. NDX constituent data does not span the "
      "full stress window, so PROD ext-row NDX leg is near-cash pre-data.")
    A("- V-effect (section 6) holds canary=TIP-only and safe=SHV/IEF at production; only the vol "
      "gate toggles. HAA-Simple here uses SHV/IEF safe (not the BIL/AGG supplied-spec variant) to "
      "isolate V apples-to-apples vs production BULL.")
    A("- Bootstrap: stationary block bootstrap, B=2000, block=21d, seed=42; resampled on the 60/40 "
      "clean-window daily series.")

    Path(ROOT / "research" / "bull_tiponly_recompute_findings.md").write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
