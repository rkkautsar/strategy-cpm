# -*- coding: utf-8 -*-
"""Throwaway research (analyst role; read-only re production; writes only to
research/; NO production/memo files changed; NO commit). EXPLORATION ONLY --
validates the FASTER vol-gate window (RV20<RV252 on SPY) hypothesis on BOTH the
NDX sleeve and the BULL sleeve with the full discipline (paired bootstrap CI +
walk-forward + response-surface plateau + per-episode removal).

HYPOTHESIS
----------
RV60<RV252 (V0, inherited from BULL) is too SLOW for the high-beta NDX sleeve; a
FASTER window (RV20<RV252) re-risks quicker post-spike and de-risks earlier into
drawdowns. Initial single-run NDX result: RV20 Calmar 0.96 / Martin 4.18 / MaxDD
-31.4% vs V0 0.76 / 2.98 / -35.9% vs no-gate 0.78 / 2.27 / -38.8%, keeps crisis
catches. This DIRECTLY questions the pending decision to DROP the BULL vol gate
(RV60 was within-noise vs no-gate). If RV20 rescues BULL too, the move is RETUNE
to RV20, not drop.

DECISIVE TESTS (per sleeve)
  1. Reproduce V0 anchor + RV20.
  2. Paired stationary block bootstrap (B=5000, block 21d) on the marginal
     RV20-minus-V0 AND RV20-minus-no-gate for Calmar/Martin/Sharpe. Does the CI
     EXCLUDE 0?
  3. Walk-forward: select window OOS (freeze pre-2017, apply 2017+, weight the
     post-2017 genuine-OOS slice heavily for NDX given pre-2017 survivorship).
  4. Response surface (fast-window plateau vs spike) + per-episode removal.

VERDICT per sleeve: adopt RV20 / keep RV60 / drop-to-no-gate. Explicit on whether
the queued BULL drop should be REPLACED by an RV20 retune.

HONESTY: t+1 MOO, point-in-time, single 18y in-sample, NDX pre-2017 ~28%
survivorship bias. Reproduce anchors before deltas. No adoption without user
confirmation.

Writes research/rv20_window_validation_findings.md (+ .json).
"""
from __future__ import annotations
import sys, json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from cpm_live import load_panel, perf_metrics, sig_13612U, COST_BPS_PER_SIDE

# ---- NDX engine reuse ----
import ndx_volgate_variants as NV
# ---- BULL engine reuse ----
import exec_lag_moo_validation_2026_05_30 as H
import bull_volgate_variants as BV

OUT_JSON = Path(__file__).with_suffix(".json")
OUT_MD = ROOT / "research" / "rv20_window_validation_findings.md"

B_ITER, BLOCK, SEED = 5000, 21, 42
WF_SPLIT = pd.Timestamp("2017-01-01")          # genuine-OOS boundary (clean PIT)
WINDOWS = [10, 15, 20, 25, 30, 40, 50, 60, 90, 120]

NDX_ANCHOR = {"sharpe": 1.1812, "maxdd": -0.3592, "calmar": 0.7602, "martin": 2.9753}
BULL_ANCHOR = {"sharpe": 1.1005, "maxdd": -0.1335, "calmar": 0.8189, "martin": 3.0714}


# ============================ shared helpers ============================

def metrics_of(daily, cash):
    m = perf_metrics(daily, cash)
    return {"sharpe": m.get("sharpe"), "calmar": m.get("calmar"), "martin": m.get("martin"),
            "maxdd": m.get("max_drawdown"), "cagr": m.get("cagr"), "vol": m.get("vol")}


def paired_block_bootstrap(base, alt, cash, label, n_iter=B_ITER, block=BLOCK, seed=SEED):
    """PAIRED stationary block bootstrap on marginal = metric(alt) - metric(base).
    SAME random time blocks drawn from BOTH daily streams; preserves contemporaneous
    pairing. Reports CI of deltas for Calmar/Martin/Sharpe and P(delta>0)."""
    base = base.dropna()
    alt = alt.reindex(base.index).fillna(0.0)
    idx = base.index
    cash_a = cash.reindex(idx).fillna(0.0)
    n = len(idx)
    ab, aa, ac = base.values, alt.values, cash_a.values
    rng = np.random.default_rng(seed)
    keys = ["calmar", "martin", "sharpe"]
    deltas = {k: [] for k in keys}
    for _ in range(n_iter):
        pos = []
        while len(pos) < n:
            s = int(rng.integers(0, n))
            for j in range(block):
                pos.append((s + j) % n)
        pos = np.array(pos[:n])
        sb = pd.Series(ab[pos], index=idx)
        sa = pd.Series(aa[pos], index=idx)
        sc = pd.Series(ac[pos], index=idx)
        mb = metrics_of(sb, sc); ma = metrics_of(sa, sc)
        for k in keys:
            if mb[k] is not None and ma[k] is not None and np.isfinite(mb[k]) and np.isfinite(ma[k]):
                deltas[k].append(ma[k] - mb[k])
    out = {"label": label}
    for k in keys:
        a = np.array(deltas[k], dtype=float); a = a[np.isfinite(a)]
        out[k] = {"p2.5": float(np.percentile(a, 2.5)), "p50": float(np.percentile(a, 50)),
                  "p97.5": float(np.percentile(a, 97.5)), "mean": float(a.mean()),
                  "share_gt0_pct": float(100.0 * np.mean(a > 0)),
                  "excludes_0": bool(np.percentile(a, 2.5) > 0 or np.percentile(a, 97.5) < 0),
                  "n": int(len(a))}
    return out


def win(s, lo, hi):
    return s.loc[(s.index >= pd.Timestamp(lo)) & (s.index <= pd.Timestamp(hi))]


# ============================ NDX section ============================

def run_ndx():
    print("=== NDX sleeve ===")
    cpm_panel = load_panel(start=NV.PANEL_START, end=NV.END)
    ndx_panel = NV.load_ndx_panel()
    end = min(NV.END, cpm_panel.index[-1])
    cash = cpm_panel["SHV"].ffill().pct_change().dropna()

    full_panel = cpm_panel.join(ndx_panel, how="outer", rsuffix="_dup")
    full_panel = full_panel.loc[:, ~full_panel.columns.str.endswith("_dup")]
    monthly_idx = pd.DataFrame({"x": 1}, index=full_panel.index).groupby(
        pd.Grouper(freq="ME")).tail(1).index
    sig_dates = monthly_idx[(monthly_idx >= NV.START) & (monthly_idx <= end)]

    print(f"  precomputing NDX selection for {len(sig_dates)} signal dates...")
    targets = NV.precompute_targets(cpm_panel, ndx_panel, sig_dates)
    prep = NV.prepare_arrays(full_panel, NV.START, end)

    def sleeve_for_window(fast):
        g = NV.gate_realized("SPY")(fast, 252)
        wfd, _ = NV.build_weights_for_date(full_panel, targets, sig_dates, cpm_panel, g)
        return NV.run_daily(prep, wfd)

    def sleeve_nogate():
        wfd, _ = NV.build_weights_for_date(full_panel, targets, sig_dates, cpm_panel, NV.gate_none())
        return NV.run_daily(prep, wfd)

    # build sleeves for all candidate windows + nogate
    sleeves = {f: sleeve_for_window(f) for f in WINDOWS}
    sleeves["NOGATE"] = sleeve_nogate()
    common = None
    for s in sleeves.values():
        common = s.index if common is None else common.intersection(s.index)
    sleeves = {k: v.reindex(common) for k, v in sleeves.items()}
    cash_c = cash.reindex(common).fillna(0.0)

    v0 = sleeves[60]; rv20 = sleeves[20]; ng = sleeves["NOGATE"]

    # anchor check
    v0m = metrics_of(v0, cash_c)
    anchor_ok = (abs(v0m["sharpe"] - NDX_ANCHOR["sharpe"]) < 0.01 and
                 abs(v0m["maxdd"] - NDX_ANCHOR["maxdd"]) * 100 < 0.20)
    print(f"  ANCHOR V0(RV60): Sharpe={v0m['sharpe']:.4f} MaxDD={v0m['maxdd']*100:.2f}% "
          f"Calmar={v0m['calmar']:.4f} Martin={v0m['martin']:.4f} -> "
          f"{'CONFIRMED' if anchor_ok else 'FLAG'}")
    rv20m = metrics_of(rv20, cash_c)
    ngm = metrics_of(ng, cash_c)
    print(f"  RV20: Calmar={rv20m['calmar']:.4f} Martin={rv20m['martin']:.4f} MaxDD={rv20m['maxdd']*100:.2f}%")
    print(f"  NOGATE: Calmar={ngm['calmar']:.4f} Martin={ngm['martin']:.4f} MaxDD={ngm['maxdd']*100:.2f}%")

    # response surface
    rsurf = []
    for f in WINDOWS:
        m = metrics_of(sleeves[f], cash_c)
        rsurf.append({"fast": f, **{k: m[k] for k in ("calmar", "martin", "sharpe", "maxdd")}})

    # bootstrap marginals
    print("  bootstrap RV20-minus-V0 ...")
    boot_v0 = paired_block_bootstrap(v0, rv20, cash_c, "RV20 - V0(RV60)")
    print("  bootstrap RV20-minus-NOGATE ...")
    boot_ng = paired_block_bootstrap(ng, rv20, cash_c, "RV20 - no-gate")

    # walk-forward: select window on train(<2017), eval on test(>=2017)
    train_lo, train_hi = common[0], WF_SPLIT - pd.Timedelta(days=1)
    test_lo, test_hi = WF_SPLIT, common[-1]
    wf_rows = []
    for f in WINDOWS:
        s = sleeves[f]
        tr = metrics_of(win(s, train_lo, train_hi), cash_c)
        te = metrics_of(win(s, test_lo, test_hi), cash_c)
        wf_rows.append({"fast": f, "train_calmar": tr["calmar"], "train_martin": tr["martin"],
                        "test_calmar": te["calmar"], "test_martin": te["martin"],
                        "test_sharpe": te["sharpe"], "test_maxdd": te["maxdd"]})
    sel_window = max(wf_rows, key=lambda r: (r["train_calmar"] if np.isfinite(r["train_calmar"]) else -9))["fast"]
    best_test = max(wf_rows, key=lambda r: (r["test_calmar"] if np.isfinite(r["test_calmar"]) else -9))["fast"]
    # nogate on test
    ng_test = metrics_of(win(ng, test_lo, test_hi), cash_c)
    v0_test = metrics_of(win(v0, test_lo, test_hi), cash_c)

    # per-episode removal of RV20 vs V0 and vs NOGATE
    def drop_metrics(s, lo, hi):
        mask = ~((s.index >= pd.Timestamp(lo)) & (s.index <= pd.Timestamp(hi)))
        return metrics_of(s[mask], cash_c[mask])
    ep_rows = []
    full_w = metrics_of(rv20, cash_c); full_v0 = metrics_of(v0, cash_c); full_ng = metrics_of(ng, cash_c)
    ep_rows.append({"drop": "none (full)", "win_calmar": full_w["calmar"], "win_martin": full_w["martin"],
                    "dcal_v0": full_w["calmar"] - full_v0["calmar"], "dmar_v0": full_w["martin"] - full_v0["martin"],
                    "dcal_ng": full_w["calmar"] - full_ng["calmar"], "dmar_ng": full_w["martin"] - full_ng["martin"]})
    for name, (lo, hi) in NV.CRISES.items():
        wm = drop_metrics(rv20, lo, hi); vm = drop_metrics(v0, lo, hi); nm = drop_metrics(ng, lo, hi)
        ep_rows.append({"drop": name, "win_calmar": wm["calmar"], "win_martin": wm["martin"],
                        "dcal_v0": wm["calmar"] - vm["calmar"], "dmar_v0": wm["martin"] - vm["martin"],
                        "dcal_ng": wm["calmar"] - nm["calmar"], "dmar_ng": wm["martin"] - nm["martin"]})

    # per-crisis protection for V0/RV20/NOGATE
    crisis = {}
    for name, (lo, hi) in NV.CRISES.items():
        crisis[name] = {"V0": NV.window_dd_ret(v0, lo, hi), "RV20": NV.window_dd_ret(rv20, lo, hi),
                        "NOGATE": NV.window_dd_ret(ng, lo, hi)}

    return {
        "anchor_ok": anchor_ok, "v0": v0m, "rv20": rv20m, "nogate": ngm,
        "window": str(common[0].date()) + ".." + str(common[-1].date()),
        "response_surface": rsurf,
        "boot_v0": boot_v0, "boot_ng": boot_ng,
        "walkforward": {"train": [str(train_lo.date()), str(train_hi.date())],
                        "test": [str(test_lo.date()), str(test_hi.date())],
                        "selected_window_train": sel_window, "best_window_test": best_test,
                        "rows": wf_rows, "nogate_test": ng_test, "v0_test": v0_test,
                        "rv20_test": metrics_of(win(rv20, test_lo, test_hi), cash_c)},
        "episode_removal": ep_rows, "crisis": crisis,
    }


# ============================ BULL section ============================

def gate_nogate_bull(d, s):
    return True, {}


def run_bull():
    print("=== BULL sleeve ===")
    panel = load_panel(start=BV.EXT_START, end=BV.END)
    end = min(BV.END, panel.index[-1])
    cash = panel["SHV"].ffill().pct_change().dropna()
    od, cy = H.load_open_close()
    intraday = (cy / od - 1.0).reindex(panel.index)
    overnight = (od / cy.shift(1) - 1.0).reindex(panel.index)
    bull_cols = sorted(set(["SPY", "HYG", "TIP", "SHV", "IEF"]) & set(panel.columns))
    bclose = panel[bull_cols]
    bdaily = bclose.ffill().pct_change()
    daily_spy = panel["SPY"]

    def sleeve_for_window(fast):
        g = lambda d, s: BV.gate_symmetric(d, s, fast, 252)
        return BV.run_variant_sleeve(bclose, bdaily, intraday, overnight, daily_spy,
                                     BV.EXT_START, end, g)

    sleeves = {f: sleeve_for_window(f) for f in WINDOWS}
    sleeves["NOGATE"] = BV.run_variant_sleeve(bclose, bdaily, intraday, overnight, daily_spy,
                                              BV.EXT_START, end, gate_nogate_bull)
    common = None
    for s in sleeves.values():
        common = s.index if common is None else common.intersection(s.index)
    sleeves = {k: v.reindex(common) for k, v in sleeves.items()}

    # CLEAN window is the decisive lens
    cl_lo, cl_hi = BV.CLEAN_START, end
    cash_cl = cash

    def m_clean(s):
        return metrics_of(win(s, cl_lo, cl_hi), cash_cl)

    v0 = sleeves[60]; rv20 = sleeves[20]; ng = sleeves["NOGATE"]
    v0m = m_clean(v0); rv20m = m_clean(rv20); ngm = m_clean(ng)
    anchor_ok = (abs(v0m["sharpe"] - BULL_ANCHOR["sharpe"]) < 0.02 and
                 abs(v0m["calmar"] - BULL_ANCHOR["calmar"]) < 0.01 and
                 abs(v0m["martin"] - BULL_ANCHOR["martin"]) < 0.05)
    print(f"  ANCHOR V0(RV60) clean: Sharpe={v0m['sharpe']:.4f} Calmar={v0m['calmar']:.4f} "
          f"Martin={v0m['martin']:.4f} MaxDD={v0m['maxdd']*100:.2f}% -> "
          f"{'CONFIRMED' if anchor_ok else 'FLAG'}")
    print(f"  RV20 clean: Calmar={rv20m['calmar']:.4f} Martin={rv20m['martin']:.4f} MaxDD={rv20m['maxdd']*100:.2f}%")
    print(f"  NOGATE clean: Calmar={ngm['calmar']:.4f} Martin={ngm['martin']:.4f} MaxDD={ngm['maxdd']*100:.2f}%")

    # response surface (clean)
    rsurf = []
    for f in WINDOWS:
        m = m_clean(sleeves[f])
        rsurf.append({"fast": f, **{k: m[k] for k in ("calmar", "martin", "sharpe", "maxdd")}})

    # crisis protection (clean-relevant windows)
    crisis = {}
    for name, (lo, hi) in BV.CRISES.items():
        crisis[name] = {"V0": BV.window_dd_ret(v0, lo, hi), "RV20": BV.window_dd_ret(rv20, lo, hi),
                        "NOGATE": BV.window_dd_ret(ng, lo, hi)}

    # bootstrap on clean window: RV20-minus-V0 AND RV20-minus-nogate (KEY: vs nogate)
    v0_cl = win(v0, cl_lo, cl_hi); rv20_cl = win(rv20, cl_lo, cl_hi); ng_cl = win(ng, cl_lo, cl_hi)
    print("  bootstrap RV20-minus-V0 (clean) ...")
    boot_v0 = paired_block_bootstrap(v0_cl, rv20_cl, cash_cl, "RV20 - V0(RV60)")
    print("  bootstrap RV20-minus-NOGATE (clean) ...")
    boot_ng = paired_block_bootstrap(ng_cl, rv20_cl, cash_cl, "RV20 - no-gate(HAA-Simple)")

    # per-episode removal RV20 vs V0 and vs nogate (clean window)
    def drop_metrics(s, lo, hi):
        s = win(s, cl_lo, cl_hi)
        mask = ~((s.index >= pd.Timestamp(lo)) & (s.index <= pd.Timestamp(hi)))
        return metrics_of(s[mask], cash_cl)
    ep_rows = []
    fw = m_clean(rv20); fv = m_clean(v0); fn = m_clean(ng)
    ep_rows.append({"drop": "none (full)", "win_calmar": fw["calmar"], "win_martin": fw["martin"],
                    "dcal_v0": fw["calmar"] - fv["calmar"], "dmar_v0": fw["martin"] - fv["martin"],
                    "dcal_ng": fw["calmar"] - fn["calmar"], "dmar_ng": fw["martin"] - fn["martin"]})
    for name, (lo, hi) in BV.CRISES.items():
        wm = drop_metrics(rv20, lo, hi); vm = drop_metrics(v0, lo, hi); nm = drop_metrics(ng, lo, hi)
        ep_rows.append({"drop": name, "win_calmar": wm["calmar"], "win_martin": wm["martin"],
                        "dcal_v0": wm["calmar"] - vm["calmar"], "dmar_v0": wm["martin"] - vm["martin"],
                        "dcal_ng": wm["calmar"] - nm["calmar"], "dmar_ng": wm["martin"] - nm["martin"]})

    # walk-forward: train clean<2017, test >=2017
    train_lo, train_hi = cl_lo, WF_SPLIT - pd.Timedelta(days=1)
    test_lo, test_hi = WF_SPLIT, end
    wf_rows = []
    for f in WINDOWS:
        s = sleeves[f]
        tr = metrics_of(win(s, train_lo, train_hi), cash_cl)
        te = metrics_of(win(s, test_lo, test_hi), cash_cl)
        wf_rows.append({"fast": f, "train_calmar": tr["calmar"], "train_martin": tr["martin"],
                        "test_calmar": te["calmar"], "test_martin": te["martin"],
                        "test_sharpe": te["sharpe"], "test_maxdd": te["maxdd"]})
    sel_window = max(wf_rows, key=lambda r: (r["train_calmar"] if np.isfinite(r["train_calmar"]) else -9))["fast"]
    best_test = max(wf_rows, key=lambda r: (r["test_calmar"] if np.isfinite(r["test_calmar"]) else -9))["fast"]
    ng_test = metrics_of(win(ng, test_lo, test_hi), cash_cl)
    v0_test = metrics_of(win(v0, test_lo, test_hi), cash_cl)
    rv20_test = metrics_of(win(rv20, test_lo, test_hi), cash_cl)

    return {
        "anchor_ok": anchor_ok, "v0": v0m, "rv20": rv20m, "nogate": ngm,
        "clean_window": [str(cl_lo.date()), str(cl_hi.date())],
        "response_surface": rsurf, "crisis": crisis,
        "boot_v0": boot_v0, "boot_ng": boot_ng, "episode_removal": ep_rows,
        "walkforward": {"train": [str(train_lo.date()), str(train_hi.date())],
                        "test": [str(test_lo.date()), str(test_hi.date())],
                        "selected_window_train": sel_window, "best_window_test": best_test,
                        "rows": wf_rows, "nogate_test": ng_test, "v0_test": v0_test,
                        "rv20_test": rv20_test},
    }


# ============================ report ============================

def pct(x):
    return f"{x*100:.2f}%" if x is not None and isinstance(x, (int, float)) and np.isfinite(x) else "n/a"


def f4(x):
    return f"{x:.4f}" if x is not None and isinstance(x, (int, float)) and np.isfinite(x) else "n/a"


def boot_table(A, boot):
    A("| Marginal metric | p2.5 | p50 | p97.5 | mean | P(d>0) | excludes 0? |")
    A("|---|---:|---:|---:|---:|---:|:--:|")
    for k, lab in [("calmar", "Calmar"), ("martin", "Martin"), ("sharpe", "Sharpe")]:
        c = boot[k]
        A(f"| {lab} | {c['p2.5']:+.4f} | {c['p50']:+.4f} | {c['p97.5']:+.4f} | {c['mean']:+.4f} | "
          f"{c['share_gt0_pct']:.1f}% | {'YES' if c['excludes_0'] else 'NO (includes 0)'} |")
    A("")


def rsurf_table(A, rs):
    A("| fast window | Calmar | Martin | Sharpe | MaxDD |")
    A("|---:|---:|---:|---:|---:|")
    for r in rs:
        A(f"| {r['fast']} | {f4(r['calmar'])} | {f4(r['martin'])} | {f4(r['sharpe'])} | {pct(r['maxdd'])} |")
    A("")


def wf_table(A, wf):
    A(f"Train {wf['train'][0]}..{wf['train'][1]} -> Test {wf['test'][0]}..{wf['test'][1]}. "
      f"Window selected on TRAIN Calmar = **{wf['selected_window_train']}**; "
      f"best window on TEST Calmar = **{wf['best_window_test']}**.\n")
    A("| fast | train Calmar | train Martin | test Calmar | test Martin | test Sharpe | test MaxDD |")
    A("|---:|---:|---:|---:|---:|---:|---:|")
    for r in wf["rows"]:
        A(f"| {r['fast']} | {f4(r['train_calmar'])} | {f4(r['train_martin'])} | {f4(r['test_calmar'])} | "
          f"{f4(r['test_martin'])} | {f4(r['test_sharpe'])} | {pct(r['test_maxdd'])} |")
    A("")


def episode_table(A, rows):
    A("| dropped window | RV20 Calmar | RV20 Martin | dCalmar vs V0 | dMartin vs V0 | dCalmar vs no-gate | dMartin vs no-gate |")
    A("|---|---:|---:|---:|---:|---:|---:|")
    for r in rows:
        A(f"| {r['drop']} | {f4(r['win_calmar'])} | {f4(r['win_martin'])} | {r['dcal_v0']:+.4f} | "
          f"{r['dmar_v0']:+.4f} | {r['dcal_ng']:+.4f} | {r['dmar_ng']:+.4f} |")
    A("")


def write_md(ndx, bull):
    L = []; A = L.append
    A("# Faster vol-gate window (RV20<RV252) validation -- NDX + BULL sleeves\n")
    A("Role: analyst (hypothesis-driven; read-only re production; writes only to research/; no "
      "production/memo edits; no commit). EXPLORATION ONLY. Harness "
      "`research/rv20_window_validation.py` (reuses ndx_volgate_variants + bull_volgate_variants + "
      "exec_lag_moo_validation engines verbatim).\n")
    A("**Hypothesis.** RV60<RV252 (V0, inherited from BULL) is too SLOW for high-beta NDX; a FASTER "
      "window (RV20<RV252 on SPY) re-risks quicker post-spike and de-risks earlier into drawdowns. "
      "If RV20 also rescues BULL, the queued decision to DROP the BULL gate (RV60 within-noise vs "
      "no-gate) should become a RETUNE to RV20, not a drop.\n")
    A(f"**Discipline.** Paired stationary block bootstrap (B={B_ITER}, block {BLOCK}d) on the "
      "marginal RV20-minus-V0 AND RV20-minus-no-gate for Calmar/Martin/Sharpe (CI exclude 0?); "
      f"walk-forward (freeze window pre-{WF_SPLIT.year}, test {WF_SPLIT.year}+); response-surface "
      "plateau-vs-spike; per-episode removal. Same skepticism that killed the CPM PC1 gate.\n")
    A("**Honesty guards.** T+1 MOO, point-in-time membership, single 18y in-sample, NDX pre-2017 "
      "~28% survivorship bias (so the post-2017 genuine-OOS walk-forward slice is weighted heavily). "
      "Anchors reproduced before deltas. No adoption without explicit user confirmation.\n")

    # ===================== NDX =====================
    A("\n## NDX sleeve\n")
    A(f"Window {ndx['window']}. Anchor V0(RV60): Sharpe **{f4(ndx['v0']['sharpe'])}** / MaxDD "
      f"**{pct(ndx['v0']['maxdd'])}** / Calmar **{f4(ndx['v0']['calmar'])}** / Martin "
      f"**{f4(ndx['v0']['martin'])}** -> **{'CONFIRMED' if ndx['anchor_ok'] else 'FLAG'}**. "
      f"RV20: Calmar **{f4(ndx['rv20']['calmar'])}** / Martin **{f4(ndx['rv20']['martin'])}** / MaxDD "
      f"**{pct(ndx['rv20']['maxdd'])}**. No-gate: Calmar **{f4(ndx['nogate']['calmar'])}** / Martin "
      f"**{f4(ndx['nogate']['martin'])}** / MaxDD **{pct(ndx['nogate']['maxdd'])}**.\n")

    A("### NDX 1. Paired bootstrap CI -- RV20 minus V0(RV60)\n")
    boot_table(A, ndx["boot_v0"])
    A("### NDX 2. Paired bootstrap CI -- RV20 minus no-gate\n")
    boot_table(A, ndx["boot_ng"])

    A("### NDX 3. Walk-forward (freeze window pre-2017, test 2017+ genuine OOS / clean PIT)\n")
    wf_table(A, ndx["walkforward"])
    wf = ndx["walkforward"]
    A(f"No-gate test Calmar {f4(wf['nogate_test']['calmar'])} / Martin {f4(wf['nogate_test']['martin'])}; "
      f"V0 test Calmar {f4(wf['v0_test']['calmar'])} / Martin {f4(wf['v0_test']['martin'])}; "
      f"RV20 test Calmar {f4(wf['rv20_test']['calmar'])} / Martin {f4(wf['rv20_test']['martin'])}.\n")

    A("### NDX 4. Response surface RV{fast}<RV252 SPY (full window)\n")
    rsurf_table(A, ndx["response_surface"])

    A("### NDX 5. Per-episode removal (drop one crisis, recompute RV20 edge)\n")
    episode_table(A, ndx["episode_removal"])

    A("### NDX 6. Per-crisis protection (MaxDD / total return)\n")
    cn = list(ndx["crisis"].keys())
    A("| Variant | " + " | ".join(f"{c}" for c in cn) + " |")
    A("|---|" + "---|" * len(cn))
    for lab in ["V0", "RV20", "NOGATE"]:
        cells = []
        for c in cn:
            cr = ndx["crisis"][c][lab]
            cells.append(f"{pct(cr['maxdd'])} / {pct(cr['ret'])}")
        A(f"| {lab} | " + " | ".join(cells) + " |")
    A("")

    # ===================== BULL =====================
    A("\n## BULL sleeve\n")
    A(f"Clean window {bull['clean_window'][0]}..{bull['clean_window'][1]}. Anchor V0(RV60): Sharpe "
      f"**{f4(bull['v0']['sharpe'])}** / Calmar **{f4(bull['v0']['calmar'])}** / Martin "
      f"**{f4(bull['v0']['martin'])}** / MaxDD **{pct(bull['v0']['maxdd'])}** -> "
      f"**{'CONFIRMED' if bull['anchor_ok'] else 'FLAG'}**. RV20: Calmar **{f4(bull['rv20']['calmar'])}** "
      f"/ Martin **{f4(bull['rv20']['martin'])}** / MaxDD **{pct(bull['rv20']['maxdd'])}**. No-gate "
      f"(HAA-Simple): Calmar **{f4(bull['nogate']['calmar'])}** / Martin **{f4(bull['nogate']['martin'])}** "
      f"/ MaxDD **{pct(bull['nogate']['maxdd'])}**.\n")

    A("### BULL 1. Paired bootstrap CI -- RV20 minus V0(RV60)\n")
    boot_table(A, bull["boot_v0"])
    A("### BULL 2. Paired bootstrap CI -- RV20 minus no-gate (KEY: does faster beat no-gate?)\n")
    boot_table(A, bull["boot_ng"])

    A("### BULL 3. Response surface RV{fast}<RV252 SPY (clean 18y)\n")
    rsurf_table(A, bull["response_surface"])

    A("### BULL 4. Per-episode removal (drop one crisis, recompute RV20 edge)\n")
    episode_table(A, bull["episode_removal"])

    A("### BULL 5. Walk-forward (freeze window pre-2017, test 2017+)\n")
    wf_table(A, bull["walkforward"])

    A("### BULL 6. Per-crisis protection (MaxDD / total return) -- keep 2008/2020 crash + 2018/2022 grind\n")
    cn = list(bull["crisis"].keys())
    A("| Variant | " + " | ".join(f"{c}" for c in cn) + " |")
    A("|---|" + "---|" * len(cn))
    for lab in ["V0", "RV20", "NOGATE"]:
        cells = []
        for c in cn:
            cr = bull["crisis"][c][lab]
            cells.append(f"{pct(cr['maxdd'])} / {pct(cr['ret'])}")
        A(f"| {lab} | " + " | ".join(cells) + " |")
    A("")

    # placeholder for verdicts (filled by hand after seeing numbers)
    A("\n## VERDICT (auto-summary; see analysis prose)\n")
    nv = ndx; bv = bull
    A(f"- **NDX RV20 vs V0:** Calmar CI excludes 0 = **{nv['boot_v0']['calmar']['excludes_0']}**, "
      f"Martin CI excludes 0 = **{nv['boot_v0']['martin']['excludes_0']}**, Sharpe CI excludes 0 = "
      f"**{nv['boot_v0']['sharpe']['excludes_0']}**.")
    A(f"- **NDX RV20 vs no-gate:** Calmar CI excludes 0 = **{nv['boot_ng']['calmar']['excludes_0']}**, "
      f"Martin CI excludes 0 = **{nv['boot_ng']['martin']['excludes_0']}**, Sharpe CI excludes 0 = "
      f"**{nv['boot_ng']['sharpe']['excludes_0']}**.")
    A(f"- **NDX walk-forward:** train-selected window = {nv['walkforward']['selected_window_train']}, "
      f"best test window = {nv['walkforward']['best_window_test']}.")
    A(f"- **BULL RV20 vs V0:** Calmar CI excludes 0 = **{bv['boot_v0']['calmar']['excludes_0']}**, "
      f"Martin CI excludes 0 = **{bv['boot_v0']['martin']['excludes_0']}**.")
    A(f"- **BULL RV20 vs no-gate:** Calmar CI excludes 0 = **{bv['boot_ng']['calmar']['excludes_0']}**, "
      f"Martin CI excludes 0 = **{bv['boot_ng']['martin']['excludes_0']}**.")
    A(f"- **BULL walk-forward:** train-selected window = {bv['walkforward']['selected_window_train']}, "
      f"best test window = {bv['walkforward']['best_window_test']}.\n")

    A("## Caveats\n")
    A("- EXPLORATION ONLY; no production/memo edits; no commit. Read-only re production.")
    A("- Only the vol-gate WINDOW changes; canary/trend/selection/safe/delisting/execution held at prod.")
    A("- NDX standalone sleeve lens; at 20% blend weight effects scale ~1/5. Pre-2017 ~28% "
      "survivorship bias -> post-2017 walk-forward slice weighted heavily.")
    A("- BULL clean 18y is the decisive lens (full real-open coverage); T+1 MOO exact, 10 bps/side.")
    A("- Paired stationary block bootstrap resamples episodes preserving contemporaneous pairing; "
      "DD-based metrics (Calmar/Martin) lean on ~2 grind catches so wide CIs expected.")
    A("- No adoption without explicit user confirmation.")

    OUT_MD.write_text("\n".join(L) + "\n")


def main():
    ndx = run_ndx()
    bull = run_bull()
    out = {"meta": {"B_iter": B_ITER, "block": BLOCK, "seed": SEED,
                    "wf_split": str(WF_SPLIT.date()), "windows": WINDOWS},
           "ndx": ndx, "bull": bull}
    OUT_JSON.write_text(json.dumps(out, indent=2, default=float))
    write_md(ndx, bull)
    print(f"DONE -> {OUT_MD}")
    return out


if __name__ == "__main__":
    main()
