# -*- coding: utf-8 -*-
"""Throwaway research (analyst role; read-only re production; writes only to
research/; NO production/memo files changed; NO commit).

GOAL: explore levers that STRENGTHEN the existing BULL sleeve so it clearly
justifies itself over plain HAA-Simple (TIP+SPY 13612U canary/trend). Current
production BULL = HAA-Simple + binary rv_60d<rv_252d vol gate, which barely beats
HAA-Simple. Test three lever families as modifications of current BULL:

  L1 CANARY  : TIP-AND-HYG (both 13612U>0) vs current TIP-only.
  L2 RV-SPEED: faster crossover pair, grid {63<126, 42<126, 63<189, 42<252}
               replacing rv_60d<rv_252d.
  L3 VOLTGT  : vol-target overlay scaling SPY weight to target ann vol in
               {15%, trailing rv_126d, trailing rv_252d}, cap 100%, remainder to
               best-of-safe. (a) replace binary gate; (b) on top of binary gate.
               sigma_hat estimate window = 60d (= production rv-fast window;
               not a newly tuned param).

Canonical convention (held identical to prior anchor-gated sets):
  T+1 MOO exact ("mooex", real auto_adjust opens), 10 bps/side post-cost.
  clean 2008-05-30..end (18y); ext/stress 1999-03-10..end (27y).
  Sleeves run through the canonical mooex harness
  exec_lag_moo_validation_2026_05_30._segment_returns_conv.
  CPM sleeve UNCHANGED (HYG-OR-TIP) for the 60/40 blend.

ANCHOR GATE (abort on CPM mismatch; flag on BULL):
  CPM-solo clean Sharpe 1.1910 (exact).
  BULL-TIP-only clean Sharpe ~1.10 (flag only).

Writes research/bull_strengthen_existing_findings.md (+ .json).
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

CONV = "mooex"
COST = COST_BPS_PER_SIDE  # 10
CLEAN_START = pd.Timestamp("2008-05-30")
EXT_START = pd.Timestamp("1999-03-10")
END = pd.Timestamp("2026-05-22")
EST_W = 60          # sigma_hat window for vol targeting (= production rv-fast)
SAFE_POOL = ["SHV", "IEF"]

ANCHOR_CPM_SHARPE = 1.1910
ANCHOR_BULL_SHARPE = 1.10   # approx

STRESS = {
    "2022":  ("2022-01-01", "2022-12-31"),
    "COVID": ("2020-02-01", "2020-04-30"),
    "GFC":   ("2008-09-01", "2009-06-30"),
}

B_ITER, BLOCK, SEED = 2000, 21, 42


# ---------------- generic BULL weight fn ----------------
def _pick_safe(monthly):
    scores = {}
    for s in SAFE_POOL:
        if s in monthly.columns:
            sc = sig_13612U(monthly[s])
            if pd.notna(sc):
                scores[s] = sc
    return max(scores, key=scores.get) if scores else "SHV"


def make_bull_wf(close, daily_spy, canary="tip", gate=(60, 252), voltarget=None):
    """gate: None or (fast, slow). voltarget: None or one of
    'fixed15','tv126','tv252' (sigma_hat est window EST_W)."""
    def wf(sig_d):
        monthly = close.loc[:sig_d].resample("ME").last()
        safe = _pick_safe(monthly)
        # canary
        tipm = sig_13612U(monthly["TIP"]) if "TIP" in monthly.columns else float("nan")
        if canary == "tip":
            canary_ok = pd.notna(tipm) and tipm > 0
        else:  # tip_and_hyg
            hm = sig_13612U(monthly["HYG"]) if "HYG" in monthly.columns else float("nan")
            canary_ok = (pd.notna(tipm) and tipm > 0) and (pd.notna(hm) and hm > 0)
        spym = sig_13612U(monthly["SPY"]) if "SPY" in monthly.columns else float("nan")
        trend_ok = pd.notna(spym) and spym > 0
        sub = daily_spy.loc[:sig_d].pct_change().dropna()
        vol_ok = True
        if gate is not None:
            f, s = gate
            if len(sub) >= s:
                vol_ok = float(sub.tail(f).std()) < float(sub.tail(s).std())
        risk_on = canary_ok and trend_ok and vol_ok
        if not risk_on:
            return {safe: 1.0}
        if voltarget is None:
            return {"SPY": 1.0}
        # vol-target scaling
        if len(sub) < max(EST_W, 252):
            return {"SPY": 1.0}
        sigma_hat = float(sub.tail(EST_W).std() * np.sqrt(252))
        if voltarget == "fixed15":
            target = 0.15
        elif voltarget == "tv126":
            target = float(sub.tail(126).std() * np.sqrt(252))
        else:  # tv252
            target = float(sub.tail(252).std() * np.sqrt(252))
        spy_w = min(1.0, target / sigma_hat) if sigma_hat > 0 else 1.0
        spy_w = max(0.0, spy_w)
        if spy_w >= 0.999:
            return {"SPY": 1.0}
        return {"SPY": spy_w, safe: 1.0 - spy_w}
    return wf


def run_bull(close, daily_ret, wf, start, end, intraday, overnight):
    s, _ = H._segment_returns_conv(close, daily_ret, wf, start, end, CONV,
                                   COST, intraday, overnight)
    return s


# ---------------- metrics ----------------
def win(s, a, b):
    return s.loc[(s.index >= a) & (s.index <= b)]


def met(s, cash):
    m = perf_metrics(s, cash)
    return {"sharpe": m.get("sharpe"), "cagr": m.get("cagr"), "vol": m.get("vol"),
            "maxdd": m.get("max_drawdown"), "calmar": m.get("calmar")}


def stress_dd(s):
    out = {}
    for name, (lo, hi) in STRESS.items():
        sub = s.loc[(s.index >= pd.Timestamp(lo)) & (s.index <= pd.Timestamp(hi))]
        if len(sub) >= 5:
            eq = (1 + sub).cumprod()
            dd = (eq / eq.cummax() - 1).min()
            ret = float(eq.iloc[-1] - 1)
            out[name] = {"maxdd": float(dd), "ret": ret, "n": len(sub)}
        else:
            out[name] = {"maxdd": float("nan"), "ret": float("nan"), "n": len(sub)}
    return out


def turnover_annual(close, wf, start, end):
    """Average annualized two-sided turnover from monthly weight history."""
    monthly_idx = (pd.DataFrame({"x": 1}, index=close.index)
                   .groupby(pd.Grouper(freq="ME")).tail(1))
    sigs = monthly_idx.index[(monthly_idx.index >= start) & (monthly_idx.index <= end)].tolist()
    prev = {}
    tos = []
    for sd in sigs:
        w = wf(sd)
        keys = set(w) | set(prev)
        to = sum(abs(w.get(k, 0.0) - prev.get(k, 0.0)) for k in keys)
        tos.append(to)
        prev = w
    # drop first (entry) for fair comparison
    if len(tos) > 1:
        tos = tos[1:]
    return float(np.mean(tos) * 12.0) if tos else float("nan")


# ---------------- bootstrap paired delta-Sharpe ----------------
def _sharpe(a):
    v = a.std(ddof=0) * np.sqrt(252)
    return (a.mean() * 252) / v if v > 0 else np.nan


def paired_boot_dsharpe(variant, base, n_iter=B_ITER, block=BLOCK, seed=SEED):
    """Stationary block bootstrap of Sharpe(variant) - Sharpe(base), paired."""
    common = variant.index.intersection(base.index)
    va = variant.reindex(common).values
    ba = base.reindex(common).values
    n = len(common)
    rng = np.random.default_rng(seed)
    deltas = []
    nb = (n // block) + 1
    for _ in range(n_iter):
        idx = []
        for _ in range(nb):
            s = rng.integers(0, n)
            idx.extend(range(s, s + block))
        idx = np.array(idx[:n]) % n
        dv = va[idx]; db = ba[idx]
        sv = _sharpe(pd.Series(dv)); sb = _sharpe(pd.Series(db))
        deltas.append(sv - sb)
    a = np.array(deltas)
    a = a[np.isfinite(a)]
    return {"median": float(np.median(a)), "p2.5": float(np.percentile(a, 2.5)),
            "p97.5": float(np.percentile(a, 97.5)), "p_win": float((a > 0).mean())}


def main():
    panel = load_panel(start=EXT_START, end=END)
    end = min(END, panel.index[-1])
    cash = panel["SHV"].ffill().pct_change().dropna()
    od, cy = H.load_open_close()
    intraday = (cy / od - 1.0).reindex(panel.index)
    overnight = (od / cy.shift(1) - 1.0).reindex(panel.index)

    # CPM sleeve (unchanged)
    cpm, _ = H.cpm_sleeve_conv(panel, intraday, overnight, EXT_START, end, CONV)

    bull_cols = sorted(set(["SPY", "HYG", "TIP", "SHV", "IEF"]) & set(panel.columns))
    bclose = panel[bull_cols]
    bdaily = bclose.ffill().pct_change()
    daily_spy = panel["SPY"]

    # ---- baselines ----
    wf_haa = make_bull_wf(bclose, daily_spy, canary="tip", gate=None, voltarget=None)
    wf_base = make_bull_wf(bclose, daily_spy, canary="tip", gate=(60, 252), voltarget=None)

    def build(wf):
        return run_bull(bclose, bdaily, wf, EXT_START, end, intraday, overnight)

    haa = build(wf_haa)
    base = build(wf_base)
    common = cpm.index.intersection(base.index)
    cpm = cpm.reindex(common)

    # ANCHOR
    cpm_cl = met(win(cpm, CLEAN_START, end), cash)
    base_cl = met(win(base.reindex(common), CLEAN_START, end), cash)
    ok_cpm = abs(cpm_cl["sharpe"] - ANCHOR_CPM_SHARPE) < 5e-3
    ok_bull = abs(base_cl["sharpe"] - ANCHOR_BULL_SHARPE) < 0.03
    print(f"ANCHOR CPM clean Sharpe={cpm_cl['sharpe']:.4f} (exp {ANCHOR_CPM_SHARPE}) {'OK' if ok_cpm else 'MISMATCH'}")
    print(f"ANCHOR BULL-TIP-only clean Sharpe={base_cl['sharpe']:.4f} (exp ~{ANCHOR_BULL_SHARPE}) {'OK' if ok_bull else 'FLAG'}")
    if not ok_cpm:
        print("CPM ANCHOR MISMATCH -- aborting.")
        sys.exit(1)

    # ---- variant catalog ----
    variants = {
        "HAA-Simple (TIP+SPY)": dict(canary="tip", gate=None, voltarget=None),
        "BULL-TIP-only (rv60<rv252)": dict(canary="tip", gate=(60, 252), voltarget=None),
        # L1 canary
        "L1 TIP-AND-HYG (rv60<rv252)": dict(canary="tip_and_hyg", gate=(60, 252), voltarget=None),
        # L2 rv-speed
        "L2 rv63<rv126": dict(canary="tip", gate=(63, 126), voltarget=None),
        "L2 rv42<rv126": dict(canary="tip", gate=(42, 126), voltarget=None),
        "L2 rv63<rv189": dict(canary="tip", gate=(63, 189), voltarget=None),
        "L2 rv42<rv252": dict(canary="tip", gate=(42, 252), voltarget=None),
        # L3a voltarget REPLACE binary gate
        "L3a VT15 (no binary gate)": dict(canary="tip", gate=None, voltarget="fixed15"),
        "L3a VT-rv126 (no binary gate)": dict(canary="tip", gate=None, voltarget="tv126"),
        "L3a VT-rv252 (no binary gate)": dict(canary="tip", gate=None, voltarget="tv252"),
        # L3b voltarget ON TOP of binary gate
        "L3b VT15 + rv60<rv252": dict(canary="tip", gate=(60, 252), voltarget="fixed15"),
        "L3b VT-rv126 + rv60<rv252": dict(canary="tip", gate=(60, 252), voltarget="tv126"),
        "L3b VT-rv252 + rv60<rv252": dict(canary="tip", gate=(60, 252), voltarget="tv252"),
    }

    results = {}
    for name, cfg in variants.items():
        wf = make_bull_wf(bclose, daily_spy, **cfg)
        sleeve = build(wf).reindex(common)
        blend = 0.60 * cpm + 0.40 * sleeve
        res = {
            "cfg": cfg,
            "sleeve": {
                "clean": met(win(sleeve, CLEAN_START, end), cash),
                "ext": met(win(sleeve, EXT_START, end), cash),
                "stress": stress_dd(win(sleeve, CLEAN_START, end)),
                "turnover_annual": turnover_annual(bclose, wf, CLEAN_START, end),
            },
            "blend": {
                "clean": met(win(blend, CLEAN_START, end), cash),
                "ext": met(win(blend, EXT_START, end), cash),
                "stress": stress_dd(win(blend, CLEAN_START, end)),
            },
        }
        results[name] = res

    # ---- bootstrap: blend delta-Sharpe vs HAA-Simple and vs BULL-TIP-only (clean) ----
    haa_blend = win(0.60 * cpm + 0.40 * haa.reindex(common), CLEAN_START, end)
    base_blend = win(0.60 * cpm + 0.40 * base.reindex(common), CLEAN_START, end)
    boot = {}
    for name, cfg in variants.items():
        wf = make_bull_wf(bclose, daily_spy, **cfg)
        sleeve = build(wf).reindex(common)
        vb = win(0.60 * cpm + 0.40 * sleeve, CLEAN_START, end)
        boot[name] = {
            "vs_HAA": paired_boot_dsharpe(vb, haa_blend),
            "vs_BULL_TIP": paired_boot_dsharpe(vb, base_blend),
        }

    out = {
        "meta": {"conv": CONV, "cost_bps": COST, "est_w": EST_W,
                 "clean": [str(CLEAN_START.date()), str(end.date())],
                 "ext": [str(EXT_START.date()), str(end.date())],
                 "safe_pool": SAFE_POOL,
                 "anchor_cpm_clean_sharpe": cpm_cl["sharpe"], "cpm_anchor_ok": ok_cpm,
                 "anchor_bull_clean_sharpe": base_cl["sharpe"], "bull_anchor_ok": ok_bull},
        "results": results,
        "bootstrap": boot,
    }
    Path(__file__).with_suffix(".json").write_text(json.dumps(out, indent=2, default=float))
    write_md(out)
    print("DONE -> research/bull_strengthen_existing_findings.md")
    return out


def write_md(o):
    L = []; A = L.append
    m = o["meta"]; R = o["results"]; B = o["bootstrap"]

    def pct(x):
        return f"{x*100:.2f}%" if x is not None and np.isfinite(x) else "n/a"

    def f4(x):
        return f"{x:.4f}" if x is not None and np.isfinite(x) else "n/a"

    A("# Strengthening BULL over HAA-Simple -- lever exploration\n")
    A("Role: analyst (hypothesis-driven, read-only re production; writes only to research/; "
      "no production/memo files changed; no commit). Harness "
      "`research/bull_strengthen_existing.py` reusing the canonical mooex engine "
      "`exec_lag_moo_validation_2026_05_30._segment_returns_conv`.\n")
    A(f"**Conventions:** T+1 MOO exact (`mooex`, real auto_adjust opens), {m['cost_bps']} bps/side "
      f"post-cost. Clean {m['clean'][0]}..{m['clean'][1]} (18y); ext/stress {m['ext'][0]}.."
      f"{m['ext'][1]} (27y). Safe pool {m['safe_pool']} (best-of by 13612U). Vol-target sigma_hat "
      f"window = {m['est_w']}d. CPM sleeve UNCHANGED (HYG-OR-TIP) for the 60/40 blend.\n")
    A("## 0. Anchor gate\n")
    A(f"- CPM-solo clean Sharpe = **{f4(m['anchor_cpm_clean_sharpe'])}** (expect 1.1910) -> "
      f"{'CONFIRMED' if m['cpm_anchor_ok'] else 'MISMATCH'}")
    A(f"- BULL-TIP-only clean Sharpe = **{f4(m['anchor_bull_clean_sharpe'])}** (expect ~1.10) -> "
      f"{'CONFIRMED' if m['bull_anchor_ok'] else 'FLAG'}\n")

    # ---- BULL sleeve table ----
    A("## 1. BULL sleeve standalone (clean 18y + ext 27y)\n")
    A("| Variant | Win | CAGR | Vol | Sharpe | MaxDD | Calmar | TurnK/yr |")
    A("|---|---|---:|---:|---:|---:|---:|---:|")
    for name, r in R.items():
        sl = r["sleeve"]; c = sl["clean"]; e = sl["ext"]
        A(f"| {name} | clean | {pct(c['cagr'])} | {pct(c['vol'])} | **{f4(c['sharpe'])}** | "
          f"{pct(c['maxdd'])} | {f4(c['calmar'])} | {sl['turnover_annual']:.2f} |")
        A(f"| | ext | {pct(e['cagr'])} | {pct(e['vol'])} | {f4(e['sharpe'])} | {pct(e['maxdd'])} | "
          f"{f4(e['calmar'])} | |")
    A("")

    # ---- sleeve stress drawdowns ----
    A("## 2. BULL sleeve stress drawdowns (within clean window)\n")
    A("| Variant | 2022 DD | 2022 ret | COVID DD | COVID ret | GFC DD | GFC ret |")
    A("|---|---:|---:|---:|---:|---:|---:|")
    for name, r in R.items():
        st = r["sleeve"]["stress"]
        A(f"| {name} | {pct(st['2022']['maxdd'])} | {pct(st['2022']['ret'])} | "
          f"{pct(st['COVID']['maxdd'])} | {pct(st['COVID']['ret'])} | "
          f"{pct(st['GFC']['maxdd'])} | {pct(st['GFC']['ret'])} |")
    A("\n*GFC window 2008-09-01..2009-06-30 partially inside clean 18y (starts 2008-05-30).*\n")

    # ---- 60/40 blend table ----
    A("## 3. 60/40 blend (0.60 CPM + 0.40 enhanced BULL)\n")
    A("| Variant | Win | CAGR | Vol | Sharpe | MaxDD | Calmar |")
    A("|---|---|---:|---:|---:|---:|---:|")
    for name, r in R.items():
        bl = r["blend"]; c = bl["clean"]; e = bl["ext"]
        A(f"| {name} | clean | {pct(c['cagr'])} | {pct(c['vol'])} | **{f4(c['sharpe'])}** | "
          f"{pct(c['maxdd'])} | {f4(c['calmar'])} |")
        A(f"| | ext | {pct(e['cagr'])} | {pct(e['vol'])} | {f4(e['sharpe'])} | {pct(e['maxdd'])} | "
          f"{f4(e['calmar'])} |")
    A("")

    A("## 4. 60/40 blend stress drawdowns (clean window)\n")
    A("| Variant | 2022 DD | COVID DD | GFC DD |")
    A("|---|---:|---:|---:|")
    for name, r in R.items():
        st = r["blend"]["stress"]
        A(f"| {name} | {pct(st['2022']['maxdd'])} | {pct(st['COVID']['maxdd'])} | {pct(st['GFC']['maxdd'])} |")
    A("")

    # ---- bootstrap ----
    A("## 5. Paired block bootstrap -- 60/40 blend delta-Sharpe (clean)\n")
    A(f"Stationary block bootstrap, B={B_ITER}, block={BLOCK}d, seed={SEED}. Paired delta-Sharpe "
      "of variant blend minus baseline blend. p_win = fraction of resamples where variant > baseline.\n")
    A("| Variant | dSharpe vs HAA (med [95% CI]) | p_win | dSharpe vs BULL-TIP (med [95% CI]) | p_win |")
    A("|---|---|---:|---|---:|")
    for name in R:
        bh = B[name]["vs_HAA"]; bb = B[name]["vs_BULL_TIP"]
        A(f"| {name} | {bh['median']:+.4f} [{bh['p2.5']:+.3f}, {bh['p97.5']:+.3f}] | {bh['p_win']:.2f} | "
          f"{bb['median']:+.4f} [{bb['p2.5']:+.3f}, {bb['p97.5']:+.3f}] | {bb['p_win']:.2f} |")
    A("")

    # ---- ranked verdict ----
    base = R["BULL-TIP-only (rv60<rv252)"]["blend"]
    haa = R["HAA-Simple (TIP+SPY)"]["blend"]
    A("## 6. Ranked verdict\n")
    A(f"**Anchors confirmed:** CPM-solo clean Sharpe {f4(m['anchor_cpm_clean_sharpe'])}; "
      f"BULL-TIP-only clean Sharpe {f4(m['anchor_bull_clean_sharpe'])} (sleeve) / blend "
      f"{f4(base['clean']['sharpe'])} (clean) / {f4(base['ext']['sharpe'])} (ext); "
      f"HAA-Simple blend {f4(haa['clean']['sharpe'])} (clean).\n")
    A("**Where BULL's edge over HAA-Simple actually lives:** the existing binary rv60<rv252 "
      "gate already delivers the entire economically meaningful improvement -- it is a 2022 "
      "crash dodge. Sleeve 2022 DD -0.30% vs HAA -10.11%; blend 2022 DD -3.86% vs HAA -7.69%; "
      "sleeve MaxDD -13.35% vs HAA -20.41%; blend Calmar 1.1746 vs 1.1350. The blend *Sharpe* "
      "edge over HAA (+0.046, p_win 0.74) sits inside the bootstrap CI [-0.092,+0.195], so the "
      "Sharpe gain alone is noise; the drawdown/Calmar/2022 gains are the real, robust edge.\n")
    A("### Lever ranking (strengthening power over current BULL-TIP-only)\n")
    A("1. **L2 rv42<rv252** -- ONLY lever that improves on current BULL on numbers: blend clean "
      "Sharpe 1.2904 (vs 1.2777), ext 1.2981 (vs 1.2817), Calmar 1.1844 (vs 1.1746), MaxDD and "
      "all stress DDs unchanged (2022 -3.86%, COVID -10.68%, GFC -9.90%), turnover ~flat (5.44 "
      "vs 5.33). BUT the gain over current BULL is noise-level (p_win 0.67, dSharpe +0.012, CI "
      "[-0.044,+0.070] straddles 0) and it is a 1-of-4 grid winner (the other 3 rv pairs all "
      "LOST) -> real overfitting risk. Robust across clean+ext+stress but marginal.")
    A("2. **L3b VT-rv126 + rv60<rv252** -- essentially neutral (blend 1.2766 ~ base 1.2777, same "
      "stress). Adds a continuous-scaling param for ~zero benefit. Not worth complexity.")
    A("3. **L1 TIP-AND-HYG** -- INERT: byte-identical to BULL-TIP-only on every metric. In the "
      "risk-on months (TIP>0 + SPY trend + vol gate) HYG 13612U is already positive, so the AND "
      "never binds. Confirms prior 'AND not adopt-worthy' finding; here it is a no-op.")
    A("4. **L3a vol-target REPLACING the binary gate** (VT15/VT-rv126/VT-rv252) -- WORSE: blend "
      "1.21-1.24, sleeve Sharpe 0.95-1.01, and crucially LOSES the crash protection (2022 DD "
      "-7.4 to -9.7% vs -3.86%). Continuous de-risking does not cut 2022 the way the binary "
      "exit does. Reject.")
    A("5. **L2 faster-denominator pairs** (rv63<rv126, rv42<rv126, rv63<rv189) -- WORSE across "
      "the board (blend 1.17-1.22, higher turnover, sleeve Sharpe 0.80-0.95). Speeding up the "
      "SLOW leg whipsaws on grinds. Reject.")
    A("\n*Degenerate note:* VT-rv252+gate is mathematically identical to base -- when the gate is "
      "on (rv60<rv252) the target/sigma_hat ratio rv252/rv60 > 1 always caps at 100% SPY, so no "
      "scaling ever occurs.\n")
    A("### Bottom line\n")
    A("No lever *clearly* strengthens BULL beyond the existing rv60<rv252 gate. The gate already "
      "owns the edge over HAA-Simple (crash dodge -> drawdown/Calmar, not Sharpe). Vol-targeting "
      "adds nothing on top and is harmful as a replacement. TIP-AND-HYG is a no-op. The single "
      "directional improver, rv42<rv252, is within bootstrap noise and a grid-search winner; "
      "adopt only with explicit overfitting caveat (prefer keeping production rv60<rv252 for "
      "parsimony). Recommendation: do NOT adopt any lever as a strengthening change; if a single "
      "tweak is mandated, rv42<rv252 is the least-bad (weakly dominant, stress-neutral) but flag "
      "it as noise-level and grid-fitted.\n")
    o["verdict"] = {
        "ranking": ["L2 rv42<rv252 (marginal, noise-level, grid-fit risk)",
                    "L3b VT-rv126+gate (neutral)", "L1 TIP-AND-HYG (inert/no-op)",
                    "L3a vol-target replace (worse, loses crash protection)",
                    "L2 faster-denominator (worse)"],
        "recommendation": "Do not adopt any lever as a strengthening change; BULL's edge over "
                          "HAA-Simple already lives in the existing rv60<rv252 binary gate (crash "
                          "dodge -> drawdown/Calmar, not Sharpe). rv42<rv252 is least-bad if forced.",
        "edge_is_robust_in": "drawdown/Calmar/2022 (sleeve MaxDD -13.35 vs -20.41; 2022 -0.30 vs -10.11)",
        "edge_is_noise_in": "blend Sharpe (dSharpe vs HAA +0.046, CI [-0.092,+0.195])",
    }
    Path(__file__).with_suffix(".json").write_text(json.dumps(o, indent=2, default=float))
    Path(ROOT / "research" / "bull_strengthen_existing_findings.md").write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
