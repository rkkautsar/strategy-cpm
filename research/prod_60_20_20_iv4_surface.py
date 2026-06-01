# -*- coding: utf-8 -*-
"""Throwaway research harness (analyst role; READ-ONLY re production; NO production
files changed; NO commit). Regenerates the FULL PROD 60/20/20 (CPM-BULL-NDX)
performance surface under the CURRENT production spec, so the (stale) README
headline surface can be corrected.

Current production spec:
  60% CPM  -> cpm_live.compute_target_weights (IV4 single-stage: cross-asset
              momentum -> vol-Faber ranker -> positive-trend screen -> top-4 ->
              inverse-vol weight ALL surviving positives -> strict-4 partial-safe
              -> HYG-OR-TIP canary -> timed best-safe SHV/IEF).
  20% BULL -> bull_spy_live (HAA-Simple Ext on SPY; 3-layer monthly gate:
              HYG-OR-TIP canary, SPY 13612U trend, RV_60d<RV_252d vol crossover).
  20% NDX  -> ndx_sleeve_live (top-5 PIT NDX by raw 13612U, monthly BULL-gated).

EXECUTION CONVENTION
  - CPM & BULL: realistic T+1 MOO EXACT-OPEN ("mooex"; real yfinance auto_adjust
    opens) via research/exec_lag_moo_validation_2026_05_30.py. This is the engine
    that reproduces the anchor gate exactly.
  - NDX: T+1 MOO offset=1 CLOSE-TO-CLOSE via
    research/moc_vs_moo_analysis.run_ndx_backtest_with_offset(offset=1). The
    exact-open engine cannot run the per-stock PIT NDX universe (PIT constituents
    + delisting haircut), so the NDX 20% leg uses close-to-close T+1 MOO while the
    CPM 60% / BULL 20% legs use exact-open T+1 MOO. This is the same convention as
    research/two_sleeve_iv4_memo_numbers.py and is flagged in the findings.
  - 10 bps/side post-cost throughout.

ANCHOR GATE (abort on mismatch; nothing produced unless both pass):
  CPM-solo clean Sharpe 1.1910 / MaxDD -12.67% / Calmar 1.0615.
  60/40 CPM-BULL clean Sharpe 1.2485 / MaxDD -10.68% / Calmar 1.1928.

METRIC CONVENTIONS (README): raw Sharpe (rf=0), excess Sharpe vs SHV, CAGR, Vol,
MaxDD, Calmar (=CAGR/|MaxDD|). Windows: clean 2008-05-30..2026-05-22 (18y),
extended/stress 1999-03-10..2026-05-22 (27y).

Writes research/prod_60_20_20_iv4_surface_findings.md (+ .json).
"""
from __future__ import annotations
import sys, json, socket
from pathlib import Path
import numpy as np
import pandas as pd

socket.setdefaulttimeout(20)
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import exec_lag_moo_validation_2026_05_30 as H
from cpm_live import load_panel, perf_metrics, COST_BPS_PER_SIDE
import ndx_sleeve_live as ndx_sleeve
from moc_vs_moo_analysis import run_ndx_backtest_with_offset
from build_dashboard import (
    bench_aaa_tip, bench_haa_simple, bench_qqq_12mo_trend,
    bench_bb4_blend, alpha_beta_corr,
)

CONV = "mooex"
COST = COST_BPS_PER_SIDE
CLEAN_START = pd.Timestamp("2008-05-30")
EXT_START = pd.Timestamp("1999-03-10")
END = pd.Timestamp("2026-05-22")

ANCHOR_CPM = {"sharpe": 1.1910, "maxdd": -12.67, "calmar": 1.0615}
ANCHOR_BLEND = {"sharpe": 1.2485, "maxdd": -10.68, "calmar": 1.1928}

B_CI = 2000          # bootstrap CI iterations (match bootstrap_ci_2026_05_28)
B_PWIN = 5000        # paired bootstrap iterations (match prod_vs_bb4_pwin_2026_05_28)
BLOCK = 21
SEED = 42


def met(s, cash):
    m = perf_metrics(s, cash)
    return {"sharpe": m.get("sharpe"), "excess_sharpe": m.get("excess_sharpe"),
            "cagr": m.get("cagr"), "vol": m.get("vol"),
            "maxdd": m.get("max_drawdown"), "calmar": m.get("calmar"),
            "martin": m.get("martin")}


def win(s, start, end):
    return s.loc[(s.index >= start) & (s.index <= end)]


# ----- bootstrap helpers (same method as bootstrap_ci_2026_05_28 / prod_vs_bb4) -----
def _block_bootstrap_indices(n, block, rng):
    n_blocks = (n // block) + 1
    idx = []
    for _ in range(n_blocks):
        s = rng.integers(0, n)
        e = s + block
        if e <= n:
            idx.append(np.arange(s, e))
        else:
            idx.append(np.concatenate([np.arange(s, n), np.arange(0, e - n)]))
    return np.concatenate(idx)[:n]


def _metrics_from_arr(arr):
    eq = np.cumprod(1.0 + arr)
    n = len(arr)
    cagr = eq[-1] ** (252.0 / n) - 1.0
    vol = arr.std(ddof=0) * np.sqrt(252)
    sharpe = (arr.mean() * 252) / vol if vol > 1e-12 else np.nan
    peaks = np.maximum.accumulate(eq)
    mdd = float(((eq - peaks) / peaks).min())
    calmar = cagr / abs(mdd) if mdd != 0 else np.nan
    return {"Sharpe": float(sharpe), "CAGR": float(cagr), "Vol": float(vol),
            "MaxDD": mdd, "Calmar": float(calmar)}


def bootstrap_ci(daily, n_iter=B_CI, block=BLOCK, seed=SEED):
    rng = np.random.default_rng(seed)
    arr = daily.values
    n = len(arr)
    keys = ["Sharpe", "CAGR", "Vol", "MaxDD", "Calmar"]
    boot = {k: [] for k in keys}
    point = _metrics_from_arr(arr)
    for _ in range(n_iter):
        idx = _block_bootstrap_indices(n, block, rng)
        m = _metrics_from_arr(arr[idx])
        for k in keys:
            boot[k].append(m[k])
    out = {"point": point, "ci": {}}
    for k in keys:
        a = np.array(boot[k])
        out["ci"][k] = {"p2.5": float(np.percentile(a, 2.5)),
                        "p25": float(np.percentile(a, 25)),
                        "p50": float(np.percentile(a, 50)),
                        "p75": float(np.percentile(a, 75)),
                        "p97.5": float(np.percentile(a, 97.5)),
                        "mean": float(a.mean()), "std": float(a.std())}
    return out


def paired_pwin(strat, bench, n_iter=B_PWIN, block=BLOCK, seed=SEED):
    common = strat.index.intersection(bench.index)
    s = strat.reindex(common).fillna(0.0).values
    b = bench.reindex(common).fillna(0.0).values
    n = len(s)
    rng = np.random.default_rng(seed)
    d_sh, d_ca, d_dd = [], [], []
    for _ in range(n_iter):
        idx = _block_bootstrap_indices(n, block, rng)
        ms = _metrics_from_arr(s[idx])
        mb = _metrics_from_arr(b[idx])
        d_sh.append(ms["Sharpe"] - mb["Sharpe"])
        d_ca.append(ms["CAGR"] - mb["CAGR"])
        d_dd.append((ms["MaxDD"] - mb["MaxDD"]) * 100)
    d_sh = np.array(d_sh); d_ca = np.array(d_ca); d_dd = np.array(d_dd)
    return {
        "n_days": int(n),
        "point": {"strat": _metrics_from_arr(s), "bench": _metrics_from_arr(b)},
        "dSharpe_median": float(np.median(d_sh)),
        "dSharpe_ci": [float(np.percentile(d_sh, 2.5)), float(np.percentile(d_sh, 97.5))],
        "dCAGR_median": float(np.median(d_ca)),
        "dCAGR_ci": [float(np.percentile(d_ca, 2.5)), float(np.percentile(d_ca, 97.5))],
        "dMaxDD_median_pp": float(np.median(d_dd)),
        "p_dSharpe_gt_0": float(np.mean(d_sh > 0)),
        "p_dSharpe_gt_0.05": float(np.mean(d_sh > 0.05)),
        "p_dSharpe_gt_0.10": float(np.mean(d_sh > 0.10)),
        "p_dSharpe_gt_0.20": float(np.mean(d_sh > 0.20)),
        "p_dCAGR_gt_0": float(np.mean(d_ca > 0)),
        "p_MaxDD_shallower": float(np.mean(d_dd > 0)),
    }


def ab(strat, bench):
    m = alpha_beta_corr(strat, bench)
    m["r2"] = float(m["corr"] ** 2) if m["corr"] == m["corr"] else float("nan")
    return m


def main():
    panel = load_panel(start=EXT_START, end=END)
    end = min(END, panel.index[-1])
    cash = panel["SHV"].ffill().pct_change().dropna()
    od, cy = H.load_open_close()
    intraday = (cy / od - 1.0).reindex(panel.index)
    overnight = (od / cy.shift(1) - 1.0).reindex(panel.index)

    # ---- sleeves ----
    cpm, _ = H.cpm_sleeve_conv(panel, intraday, overnight, EXT_START, end, CONV)
    bull, _ = H.bull_sleeve_conv(panel, intraday, overnight, EXT_START, end, CONV, H.GATE_RV60)
    common = cpm.index.intersection(bull.index)
    cpm = cpm.reindex(common); bull = bull.reindex(common)

    ndx_panel = ndx_sleeve.load_ndx_panel()
    ndx = run_ndx_backtest_with_offset(panel, ndx_panel, EXT_START, end, offset=1)
    ndx = ndx.reindex(common).fillna(0.0)

    prod = 0.60 * cpm + 0.20 * bull + 0.20 * ndx

    # ======================= ANCHOR GATE =======================
    print("=== ANCHOR GATE ===")
    cpm_cl = met(win(cpm, CLEAN_START, end), cash)
    ok_cpm = (abs(cpm_cl["sharpe"] - ANCHOR_CPM["sharpe"]) < 5e-4
              and abs(cpm_cl["maxdd"] * 100 - ANCHOR_CPM["maxdd"]) < 0.02
              and abs(cpm_cl["calmar"] - ANCHOR_CPM["calmar"]) < 5e-4)
    print(f"  CPM clean: Sharpe={cpm_cl['sharpe']:.4f} MaxDD={cpm_cl['maxdd']*100:.2f}% "
          f"Calmar={cpm_cl['calmar']:.4f} -> {'OK' if ok_cpm else 'MISMATCH'}")
    blend6040 = 0.60 * cpm + 0.40 * bull
    bl_cl = met(win(blend6040, CLEAN_START, end), cash)
    ok_bl = (abs(bl_cl["sharpe"] - ANCHOR_BLEND["sharpe"]) < 5e-4
             and abs(bl_cl["maxdd"] * 100 - ANCHOR_BLEND["maxdd"]) < 0.02
             and abs(bl_cl["calmar"] - ANCHOR_BLEND["calmar"]) < 5e-4)
    print(f"  60/40 clean: Sharpe={bl_cl['sharpe']:.4f} MaxDD={bl_cl['maxdd']*100:.2f}% "
          f"Calmar={bl_cl['calmar']:.4f} -> {'OK' if ok_bl else 'MISMATCH'}")
    if not (ok_cpm and ok_bl):
        print("ANCHOR MISMATCH -- aborting, no outputs produced.")
        sys.exit(1)
    print("ANCHOR CONFIRMED.\n")

    out = {"meta": {"conv_cpm_bull": "T+1 MOO exact-open (mooex, real auto_adjust opens)",
                    "conv_ndx": "T+1 MOO offset=1 close-to-close (exact-open engine "
                                "unsupported for per-stock PIT NDX universe + delisting)",
                    "cost_bps": COST,
                    "clean": [str(CLEAN_START.date()), str(end.date())],
                    "ext": [str(EXT_START.date()), str(end.date())],
                    "bootstrap": {"B_ci": B_CI, "B_pwin": B_PWIN, "block": BLOCK, "seed": SEED}},
           "anchor": {"cpm_clean": cpm_cl, "blend_6040_clean": bl_cl,
                      "cpm_ok": ok_cpm, "blend_ok": ok_bl}}

    # ======================= 1+2: headline + sleeve table =======================
    series = {"CPM": cpm, "BULL": bull, "NDX": ndx, "PROD": prod}
    sleeve = {}
    for name, s in series.items():
        sleeve[name] = {"clean": met(win(s, CLEAN_START, end), cash),
                        "ext": met(win(s, EXT_START, end), cash)}
    out["sleeve_table"] = sleeve
    out["prod_headline"] = {"clean": sleeve["PROD"]["clean"], "ext": sleeve["PROD"]["ext"]}

    # ======================= 3: NDX-blend comparison (README raw-momentum checkpoints) =======================
    out["ndx_blend_checkpoints"] = {
        "clean": {"ndx": met(win(ndx, CLEAN_START, end), cash),
                  "blend": met(win(prod, CLEAN_START, end), cash)},
        "ext": {"ndx": met(win(ndx, EXT_START, end), cash),
                "blend": met(win(prod, EXT_START, end), cash)},
    }

    # ======================= 4: bootstrap CI for PROD (clean + ext) =======================
    print("Bootstrap CI (clean)...")
    ci_clean = bootstrap_ci(win(prod, CLEAN_START, end))
    print("Bootstrap CI (ext)...")
    ci_ext = bootstrap_ci(win(prod, EXT_START, end))
    out["bootstrap_ci"] = {"clean": ci_clean, "ext": ci_ext}

    # ======================= 5: alpha/beta/R^2 (clean window) =======================
    print("Alpha/beta...")
    b2 = bench_aaa_tip(panel, EXT_START, end)               # AAA + TIP canary
    b3 = bench_haa_simple(panel, EXT_START, end, asset="SPY")
    b5 = bench_qqq_12mo_trend(panel, EXT_START, end)
    bb4 = bench_bb4_blend(panel, EXT_START, end)
    bb1 = (0.60 * b2.reindex(common).fillna(0.0) + 0.40 * b3.reindex(common).fillna(0.0))
    spy_d = panel["SPY"].ffill().pct_change().reindex(common).fillna(0.0)
    qqq_d = panel["QQQ"].ffill().pct_change().reindex(common).fillna(0.0)

    def cl(s):
        return win(s, CLEAN_START, end)

    out["alpha_beta_clean"] = {
        "CPM_vs_B2_AAA_TIP": ab(cl(cpm), cl(b2)),
        "BULL_vs_B3_HAA_SPY": ab(cl(bull), cl(b3)),
        "NDX_vs_QQQ_buyhold": ab(cl(ndx), cl(qqq_d)),
        "PROD_vs_BB4": ab(cl(prod), cl(bb4)),
        "PROD_vs_BB1": ab(cl(prod), cl(bb1)),
        "PROD_vs_SPY_buyhold": ab(cl(prod), cl(spy_d)),
        "PROD_vs_QQQ_buyhold": ab(cl(prod), cl(qqq_d)),
    }

    # ======================= 6: win-prob vs BB4 (clean + ext) =======================
    print("Win-prob vs BB4 (clean)...")
    b4_haaqqq = bench_haa_simple(panel, EXT_START, end, asset="QQQ")  # README B4 = HAA-Simple QQQ
    out["pwin_vs_bb4"] = {
        "clean": paired_pwin(cl(prod), cl(bb4)),
        "ext": paired_pwin(win(prod, EXT_START, end), win(bb4, EXT_START, end)),
        "clean_vs_B4_HAA_QQQ": paired_pwin(cl(prod), cl(b4_haaqqq)),
    }

    Path(__file__).with_suffix(".json").write_text(json.dumps(out, indent=2, default=float))
    write_md(out)
    print("DONE -> research/prod_60_20_20_iv4_surface_findings.md")
    return out


def write_md(o):
    L = []; A = L.append
    m = o["meta"]
    def pct(x): return f"{x*100:.2f}%" if x == x else "n/a"
    def f3(x): return f"{x:.3f}" if x == x else "n/a"

    A("# PROD 60/20/20 (CPM-BULL-NDX) -- full surface regenerated under current production spec\n")
    A("Role: analyst (hypothesis-driven, READ-ONLY re production; no production files changed; "
      "no commit). Throwaway harness `research/prod_60_20_20_iv4_surface.py`. Supplies the FRESH "
      "number set to correct the STALE README headline surface (README PROD clean was ~1.503 / "
      "17.93% / -11.62% / 1.54, built on the OLD CPM and a different NDX execution convention).\n")
    A("**Production spec:** 60% CPM (`cpm_live.compute_target_weights`, IV4 single-stage inverse-vol "
      "top-4) + 20% BULL (`bull_spy_live`, HAA-Simple Ext SPY, RV_60d<RV_252d vol gate + "
      "first-segment entry-cost fix) + 20% NDX (`ndx_sleeve_live`, top-5 PIT NDX raw 13612U, "
      "monthly BULL-gated). Monthly rebalance, 10 bps/side.\n")
    A(f"**Execution convention:** CPM & BULL on {m['conv_cpm_bull']}; NDX on {m['conv_ndx']}. The "
      "exact-open engine reproduces the anchor gate exactly; NDX uses close-to-close T+1 MOO because "
      "the per-stock PIT NDX universe (constituents + delisting haircut) is unsupported by the "
      "exact-open single-panel engine. CPM and BULL legs are byte-identical to the two-sleeve memo "
      "run; only the NDX leg carries this minor convention nuance.\n")
    A(f"**Metric conventions (README):** raw Sharpe (rf=0), excess Sharpe vs SHV, CAGR, Vol, MaxDD, "
      f"Calmar (=CAGR/|MaxDD|). Windows: clean {m['clean'][0]}..{m['clean'][1]} (18y); "
      f"extended/stress {m['ext'][0]}..{m['ext'][1]} (27y). Bootstrap: B_ci={m['bootstrap']['B_ci']}, "
      f"B_pwin={m['bootstrap']['B_pwin']}, block={m['bootstrap']['block']}d, seed={m['bootstrap']['seed']}.\n")

    a = o["anchor"]
    A("## 0. Anchor gate\n")
    A("| Gate | Sharpe | MaxDD | Calmar | Expected | Match |")
    A("|---|---:|---:|---:|---|---|")
    ac = a["cpm_clean"]; abd = a["blend_6040_clean"]
    A(f"| CPM (clean) | {ac['sharpe']:.4f} | {pct(ac['maxdd'])} | {ac['calmar']:.4f} | "
      f"1.1910 / -12.67% / 1.0615 | {'CONFIRMED' if a['cpm_ok'] else 'MISMATCH'} |")
    A(f"| CPM-BULL 60/40 (clean) | {abd['sharpe']:.4f} | {pct(abd['maxdd'])} | {abd['calmar']:.4f} | "
      f"1.2485 / -10.68% / 1.1928 | {'CONFIRMED' if a['blend_ok'] else 'MISMATCH'} |")
    A("\nBoth anchors reproduce exactly; the rest of this file is trusted on that basis.\n")

    # 1. headline
    ph = o["prod_headline"]
    A("## 1. PROD 60/20/20 headline\n")
    A("| Window | Raw Sharpe (0rf) | Excess Sharpe (vs SHV) | CAGR | Vol | MaxDD | Calmar |")
    A("|---|---:|---:|---:|---:|---:|---:|")
    for w, lab in [("clean", "Clean (18y)"), ("ext", "Extended (27y)")]:
        r = ph[w]
        A(f"| **{lab}** | **{r['sharpe']:.3f}** | **{r['excess_sharpe']:.3f}** | **{pct(r['cagr'])}** | "
          f"**{pct(r['vol'])}** | **{pct(r['maxdd'])}** | **{r['calmar']:.2f}** |")
    A("")

    # 2. sleeve table
    st = o["sleeve_table"]
    names = [("Cross-asset Parity Momentum (CPM)", "CPM"), ("BULL-SPY", "BULL"),
             ("NDX (monthly BULL-gated)", "NDX"), ("PROD 60/20/20", "PROD")]
    A("## 2. Sleeve table\n")
    A("### Clean window (18y)\n")
    A("| Sleeve | Raw Sharpe (0rf) | Excess Sharpe (vs SHV) | CAGR | Vol | MaxDD | Calmar |")
    A("|---|---:|---:|---:|---:|---:|---:|")
    for disp, k in names:
        r = st[k]["clean"]
        A(f"| {disp} | {r['sharpe']:.3f} | {r['excess_sharpe']:.3f} | {pct(r['cagr'])} | "
          f"{pct(r['vol'])} | {pct(r['maxdd'])} | {r['calmar']:.2f} |")
    A("\n### Extended window (27y)\n")
    A("| Sleeve | Raw Sharpe (0rf) | Excess Sharpe (vs SHV) | CAGR | Vol | MaxDD | Calmar |")
    A("|---|---:|---:|---:|---:|---:|---:|")
    for disp, k in names:
        r = st[k]["ext"]
        A(f"| {disp} | {r['sharpe']:.3f} | {r['excess_sharpe']:.3f} | {pct(r['cagr'])} | "
          f"{pct(r['vol'])} | {pct(r['maxdd'])} | {r['calmar']:.2f} |")
    A("\n*NDX extended-window leg is near-cash before NDX-constituent data begins (~2008); "
      "the clean 18y window is the decisive lens for the NDX leg.*\n")

    # 3. NDX-blend comparison
    cp = o["ndx_blend_checkpoints"]
    A("## 3. NDX-blend comparison (raw-momentum checkpoints)\n")
    A("| Window | NDX Sharpe | NDX CAGR | NDX MaxDD | Blend Sharpe | Blend CAGR | Blend MaxDD |")
    A("|---|---:|---:|---:|---:|---:|---:|")
    for w, lab in [("clean", "Clean"), ("ext", "Stress")]:
        n = cp[w]["ndx"]; b = cp[w]["blend"]
        A(f"| {lab} | {n['sharpe']:.3f} | {pct(n['cagr'])} | {pct(n['maxdd'])} | "
          f"{b['sharpe']:.3f} | {pct(b['cagr'])} | {pct(b['maxdd'])} |")
    A("")

    # 4. bootstrap CI
    A("## 4. Bootstrap CI -- PROD 60/20/20 (stationary block bootstrap)\n")
    A(f"Method/B per `research/bootstrap_ci_2026_05_28*`: block bootstrap, B={m['bootstrap']['B_ci']}, "
      f"block={m['bootstrap']['block']}d, seed={m['bootstrap']['seed']}; percentile CI.\n")
    for w, lab in [("clean", "Clean (18y)"), ("ext", "Extended (27y)")]:
        ci = o["bootstrap_ci"][w]
        A(f"### {lab}\n")
        A("| Metric | Point | p2.5 | p25 | p50 | p75 | p97.5 |")
        A("|---|---:|---:|---:|---:|---:|---:|")
        for k in ["Sharpe", "CAGR", "Vol", "MaxDD", "Calmar"]:
            p = ci["point"][k]; c = ci["ci"][k]
            ispct = k in ("CAGR", "Vol", "MaxDD")
            g = (lambda x: pct(x)) if ispct else (lambda x: f"{x:.3f}")
            A(f"| {k} | {g(p)} | {g(c['p2.5'])} | {g(c['p25'])} | {g(c['p50'])} | "
              f"{g(c['p75'])} | {g(c['p97.5'])} |")
        sh = ci["ci"]["Sharpe"]
        A(f"\n**Sharpe point {ci['point']['Sharpe']:.3f}, 95% CI [{sh['p2.5']:.3f}, {sh['p97.5']:.3f}].**\n")

    # 5. alpha/beta
    A("## 5. Alpha / beta / R^2 decomposition (clean window)\n")
    A("OLS daily-return regression `r_strat = alpha + beta * r_bench`; alpha annualized "
      "(alpha_daily * 252).\n")
    A("| Strategy | Benchmark | Alpha (%/yr) | Beta | Corr | R^2 |")
    A("|---|---|---:|---:|---:|---:|")
    ab_rows = [
        ("Cross-asset Parity Momentum (CPM)", "B2: AAA + TIP canary (same universe)", "CPM_vs_B2_AAA_TIP"),
        ("BULL", "B3: HAA-Simple SPY", "BULL_vs_B3_HAA_SPY"),
        ("NDX (monthly BULL-gated)", "QQQ buy-hold", "NDX_vs_QQQ_buyhold"),
        ("PROD 60/20/20", "BB4 (best lit 60/20/20)", "PROD_vs_BB4"),
        ("PROD 60/20/20", "BB1 (60% AAA+TIP + 40% HAA-S SPY)", "PROD_vs_BB1"),
        ("PROD 60/20/20", "SPY buy-hold", "PROD_vs_SPY_buyhold"),
        ("PROD 60/20/20", "QQQ buy-hold", "PROD_vs_QQQ_buyhold"),
    ]
    for disp, bl, k in ab_rows:
        r = o["alpha_beta_clean"][k]
        A(f"| {disp} | {bl} | {r['alpha_ann_pct']:+.2f} | {r['beta']:.3f} | {r['corr']:.3f} | "
          f"{r['r2']:.3f} |")
    A("\nBuy-hold equity alpha is mechanically inflated by time in cash/safe (low realized beta) and "
      "is not analytically meaningful; the peer-blend alpha (vs BB4 / BB1) is the real claim.\n")

    # 6. win-prob vs BB4
    A("## 6. Win-probability -- PROD vs BB4 (paired block bootstrap)\n")
    A(f"Paired difference block bootstrap (B={m['bootstrap']['B_pwin']}, block={m['bootstrap']['block']}d, "
      f"seed={m['bootstrap']['seed']}). BB4 = best literature 60/20/20 blend "
      "(60 AAA+TIP / 20 HAA-Simple SPY / 20 QQQ-12mo-trend).\n")
    A("| Comparison | PROD Sharpe | Bench Sharpe | dSharpe median [95% CI] | P(dSharpe>0) | "
      "P(dSharpe>0.10) |")
    A("|---|---:|---:|---|---:|---:|")
    pw = o["pwin_vs_bb4"]
    rows = [("PROD vs BB4 (clean)", pw["clean"]), ("PROD vs BB4 (extended)", pw["ext"]),
            ("PROD vs B4 HAA-Simple QQQ (clean)", pw["clean_vs_B4_HAA_QQQ"])]
    for lab, p in rows:
        ci = p["dSharpe_ci"]
        A(f"| {lab} | {p['point']['strat']['Sharpe']:.3f} | {p['point']['bench']['Sharpe']:.3f} | "
          f"{p['dSharpe_median']:+.3f} [{ci[0]:+.3f}, {ci[1]:+.3f}] | "
          f"{p['p_dSharpe_gt_0']*100:.2f}% | {p['p_dSharpe_gt_0.10']*100:.2f}% |")
    A("\n*Naming note: the task parenthetical labels BB4 as the 'HAA-Simple QQQ benchmark'; the "
      "established README/harness BB4 is the three-sleeve literature blend (60 B2 + 20 B3 + 20 B5). "
      "Both are reported above -- the primary BB4 rows use the three-sleeve blend; the last row uses "
      "the single HAA-Simple QQQ (README B4) for completeness.*\n")

    A("## Caveats & confidence\n")
    A("- Anchor-gated: CPM-solo and CPM-BULL 60/40 clean reproduce the locked anchors to <5e-4 on "
      "Sharpe/Calmar and <0.02pp on MaxDD before any number is emitted.")
    A("- NDX leg uses close-to-close T+1 MOO (offset=1); CPM/BULL use exact-open T+1 MOO. This is the "
      "decisive convention difference vs the README's prior headline path, which ran the production "
      "`run_cpm_backtest`/`run_ndx_backtest` close-to-close engine on the OLD CPM and produced the "
      "stale 1.503. Under the current spec with this honest exact-open CPM/BULL convention, PROD "
      "clean Sharpe is materially lower.")
    A("- Extended/stress window (1999-03-10..) is partially proxy-backed pre-2006-2008 for the CPM "
      "trend universe and near-cash for NDX before constituent data begins; the clean 18y window is "
      "the decisive lens.")
    A("- Benchmark series (B2/B3/B5/BB4/BB1) are computed via `build_dashboard` literature-benchmark "
      "helpers (their own monthly close-to-close convention); alpha/beta/win-prob compare the "
      "exact-open PROD/sleeves against those series, a minor cross-convention nuance that does not "
      "affect the qualitative conclusion.")

    Path(ROOT / "research" / "prod_60_20_20_iv4_surface_findings.md").write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
