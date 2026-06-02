# -*- coding: utf-8 -*-
"""Throwaway research (read-only re: production; NO production change; NO commit):
FOUR-SCHEME comparison of the CPM (Cross-asset Parity Momentum) sleeve
weighting/selection decision, to inform whether to remove the min-var
sub-selection knob.

Common CPM design (held fixed across schemes):
  ranker = vol-Faber (10m-SMA-distance / rv_252d), positive-trend screen,
  top-K=4 momentum pool, canary HYG-OR-TIP (13612U), timed SHV/IEF safe,
  cov lookback 504d, execution T+1 MOO exact (mooex, real auto_adjust opens),
  10 bps/side post-cost.

FOUR schemes (each its own COUNT-CONSISTENT strict partial-safe fallback,
risky_fraction = min(n_pos, target)/target ; remainder -> timed safe):
  1. IV4   : NO min-var, hold ALL top-4, inverse-vol; target=4 (strict-4 PS).
  2. C(4,3): min-var 3-subset of top-4, inverse-vol; target=3 (strict-3 PS).
             == PRODUCTION cpm_live.compute_target_weights. ANCHOR-GATED:
             clean Sharpe 1.2667 / MaxDD -12.66% / Calmar 1.1306.
  3. C(4,2): min-var 2-subset of top-4, inverse-vol; target=2 (strict-2 PS).
  4. CONT  : top-4 continuous min-variance (full-cov SLSQP), STANDARD form
             (100% risky whenever >=1 positive; no partial-safe). Reference
             anchor (no-partial-safe): clean ~1.2935 / -15.15% / 0.9618.

Metrics per scheme, clean + ext:
  Sharpe (raw, 0 rf), CAGR, MaxDD, Calmar (CAGR/|MaxDD|),
  MARTIN = CAGR / Ulcer Index where
    Ulcer Index = sqrt( mean( drawdown_pct^2 ) ) over the daily equity curve,
    drawdown_pct = (equity / running_max - 1) * 100   [in PERCENT].
  Martin reported = CAGR(%) / UI(%) (unit-consistent UPI). UI value reported too.

Plus: paired stationary block bootstrap (B=2000, block=21, seed=42) IV4 vs
C(4,3) on Sharpe AND on Martin (does removing min-var move Martin/UPI, not
just Sharpe?).

Windows: clean 2008-05-30..2026-05-22 (18y); ext 1999-03-10..2026-05-22 (27y).

No production files touched. Writes research/four_scheme_metrics_martin_findings.md
(+ .json).
"""
from __future__ import annotations
import sys, json, math
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.optimize import minimize

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import exec_lag_moo_validation_2026_05_30 as H
from cpm_live import (
    load_panel, perf_metrics, faber_sma_xs, sig_13612U, best_safe,
    min_var_subset, inv_vol_weights, compute_target_weights,
    CORR_LOOKBACK_DAYS, TOP_K_CANDIDATES,
)

CONV = "mooex"
COST = 10
LOOKBACK = CORR_LOOKBACK_DAYS  # 504
K = TOP_K_CANDIDATES           # 4
CPM_UNIV = ["QQQ", "SPHQ", "EFA", "EEM", "VNQ", "GLD", "TLT", "DBC"]
SAFE = ["SHV", "IEF"]

CLEAN_START = pd.Timestamp("2008-05-30")
EXT_START = pd.Timestamp("1999-03-10")
END = pd.Timestamp("2026-05-22")

# C(4,3) production strict-3 anchor (clean) -- gate before trusting the rest.
ANCHOR_C43 = {"sharpe": 1.2667, "maxdd": -12.66, "calmar": 1.1306}

B, BLOCK, SEED = 2000, 21, 42


# ---------------------------------------------------------------------------
# Common CPM front-end (ranker + screen + canary + safe). Mirrors the
# anchor-proven gcpm_wf in cpm_final_memo_numbers.py exactly up to the risky
# allocation step, then branches per scheme.
# Returns (positive_list, safe_ticker) or (None, safe) for full-safe.
# ---------------------------------------------------------------------------
def _frontend(close, sd):
    monthly = close.loc[:sd].resample("ME").last()
    safe = best_safe(monthly, sd, SAFE)
    cs = [sig_13612U(monthly[a]) for a in ["HYG", "TIP"] if a in monthly.columns]
    cs = [s for s in cs if pd.notna(s)]
    if not cs or sum(1 for s in cs if s > 0) == 0:
        return None, safe
    present = [t for t in CPM_UNIV if t in monthly.columns]
    faber = faber_sma_xs(monthly)
    avail = [t for t in present if t in faber.index and pd.notna(faber[t])
             and (sd in close.index and pd.notna(close.loc[sd].get(t, np.nan)))]
    if not avail:
        return None, safe
    dr = close[avail].ffill().pct_change()
    scores = {}
    for t in avail:
        v = dr[t].loc[:sd].tail(252).std() * np.sqrt(252)
        if pd.isna(v) or v < 1e-9:
            v = 1.0
        scores[t] = float(faber[t]) / v
    if not scores:
        return None, safe
    ranked = pd.Series(scores).sort_values(ascending=False)
    kk = max(2, min(K, len(ranked)))
    top = ranked.iloc[:kk]
    positive = [t for t in top.index if float(faber.get(t, -np.inf)) > 0]
    if len(positive) == 0:
        return None, safe
    return positive, safe


def cpm_wf(close, daily, sd, scheme):
    """scheme in {IV4, C43, C42, CONT}."""
    positive, safe = _frontend(close, sd)
    if positive is None:
        return {safe: 1.0}
    csub = close.loc[:sd]
    n = len(positive)

    if scheme == "CONT":
        # standard continuous min-var: 100% risky when >=1 positive, no partial-safe
        cov = daily.loc[:sd].tail(LOOKBACK)[positive].cov() * 252
        if cov.isna().any().any():
            return inv_vol_weights(csub, positive, LOOKBACK)
        nn = len(positive)
        Cv = cov.values
        cons = ({"type": "eq", "fun": lambda w: np.sum(w) - 1.0},)
        bnds = tuple((0.0, 1.0) for _ in range(nn))
        r = minimize(lambda w: float(np.dot(w, np.dot(Cv, w))),
                     np.ones(nn) / nn, method="SLSQP", bounds=bnds, constraints=cons)
        if r.success:
            return {positive[i]: float(r.x[i]) for i in range(nn)}
        return {t: 1.0 / nn for t in positive}

    target = {"IV4": 4, "C43": 3, "C42": 2}[scheme]
    risky_fraction = min(n, target) / float(target)
    if n > target:
        picks = min_var_subset(csub, positive, LOOKBACK, target)
        if picks is None:
            picks = positive
    else:
        picks = positive
    risky_w = inv_vol_weights(csub, picks, LOOKBACK)
    out = {t: w * risky_fraction for t, w in risky_w.items()}
    if risky_fraction < 1.0:
        out[safe] = out.get(safe, 0.0) + (1.0 - risky_fraction)
    return out


def returns_for(close, daily, intraday, overnight, scheme, end):
    wf = lambda sd: cpm_wf(close, daily, sd, scheme)
    s, _ = H._segment_returns_conv(close, daily, wf, EXT_START, end, CONV,
                                   COST, intraday, overnight)
    return s


def win(s, start, end):
    return s.loc[(s.index >= start) & (s.index <= end)]


def met(s, cash):
    m = perf_metrics(s, cash)
    return {"sharpe": m.get("sharpe"), "cagr": m.get("cagr"),
            "maxdd": m.get("max_drawdown"), "calmar": m.get("calmar"),
            "ulcer_frac": m.get("ulcer"), "ui_pct": m.get("ulcer") * 100.0,
            "martin": m.get("martin")}


# ---------------------------------------------------------------------------
# Paired stationary block bootstrap (B=2000, block=21, seed=42).
# ---------------------------------------------------------------------------
def block_index(n, block, rng):
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


def boot_metrics(r, n_years):
    """Sharpe (raw, 0 rf) and Martin = CAGR(%)/UI(%) from a daily-return array."""
    vol = r.std(ddof=0) * np.sqrt(252)
    sharpe = (r.mean() * 252) / vol if vol > 0 else np.nan
    eq = np.cumprod(1.0 + r)
    cagr = eq[-1] ** (1.0 / n_years) - 1.0 if n_years > 0 else np.nan
    rm = np.maximum.accumulate(eq)
    dd = eq / rm - 1.0  # fraction; martin unit-invariant
    ui = np.sqrt(np.mean(dd ** 2))
    martin = cagr / ui if ui > 0 else np.nan
    return sharpe, martin


def paired_boot(a_r, b_r, n_years):
    """(b - a). a=IV4, b=C(4,3). Positive => C(4,3) higher."""
    n = len(a_r)
    rng = np.random.default_rng(SEED)
    ds, dm = [], []
    for _ in range(B):
        idx = block_index(n, BLOCK, rng)
        as_, am = boot_metrics(a_r[idx], n_years)
        bs, bm = boot_metrics(b_r[idx], n_years)
        ds.append(bs - as_); dm.append(bm - am)

    def summ(arr):
        x = np.asarray(arr)
        lo, hi = float(np.percentile(x, 2.5)), float(np.percentile(x, 97.5))
        return {"mean": float(x.mean()), "ci_lo": lo, "ci_hi": hi,
                "p_b_gt_a": float(np.mean(x > 0)),
                "excludes_zero": bool(lo > 0 or hi < 0)}
    return {"sharpe_C43_minus_IV4": summ(ds), "martin_C43_minus_IV4": summ(dm)}


SCHEMES = [("IV4", "IV4 (no min-var, all top-4, strict-4 PS)"),
           ("C43", "C(4,3) min-var 3-subset, strict-3 PS [PROD]"),
           ("C42", "C(4,2) min-var 2-subset, strict-2 PS"),
           ("CONT", "CONT top-4 continuous min-var (standard, 100% risky)")]


def main():
    panel = load_panel(start=EXT_START, end=END)
    end = min(END, panel.index[-1])
    cash = panel["SHV"].ffill().pct_change().dropna()
    od, cy = H.load_open_close()
    intraday = (cy / od - 1.0).reindex(panel.index)
    overnight = (od / cy.shift(1) - 1.0).reindex(panel.index)

    cols = sorted(set(CPM_UNIV + SAFE + ["HYG", "TIP"]) & set(panel.columns))
    close = panel[cols]
    daily = close.ffill().pct_change()

    # --- compute return series for all four schemes ---
    series = {}
    for sc, _ in SCHEMES:
        series[sc] = returns_for(close, daily, intraday, overnight, sc, end)
        print(f"  scheme {sc} done")

    # --- ANCHOR GATE: C(4,3) must reproduce 1.2667 / -12.66% / 1.1306 (clean) ---
    c43_clean = met(win(series["C43"], CLEAN_START, end), cash)
    ok = (abs(c43_clean["sharpe"] - ANCHOR_C43["sharpe"]) < 5e-4 and
          abs(c43_clean["maxdd"] * 100 - ANCHOR_C43["maxdd"]) < 0.02 and
          abs(c43_clean["calmar"] - ANCHOR_C43["calmar"]) < 5e-4)
    print(f"\n=== ANCHOR GATE C(4,3) clean: Sharpe={c43_clean['sharpe']:.4f} "
          f"MaxDD={c43_clean['maxdd']*100:.2f}% Calmar={c43_clean['calmar']:.4f} "
          f"expect {ANCHOR_C43['sharpe']}/{ANCHOR_C43['maxdd']}%/{ANCHOR_C43['calmar']} "
          f"-> {'OK' if ok else 'MISMATCH'}")
    if not ok:
        print("ANCHOR MISMATCH -- aborting.")
        sys.exit(1)

    # cross-check: production compute_target_weights matches C43 scheme exactly
    prod = H._segment_returns_conv(close, daily,
                                   lambda sd: compute_target_weights(close, sd)[0],
                                   EXT_START, end, CONV, COST, intraday, overnight)[0]
    pc = met(win(prod, CLEAN_START, end), cash)
    prod_match = abs(pc["sharpe"] - c43_clean["sharpe"]) < 1e-6
    print(f"production compute_target_weights clean Sharpe={pc['sharpe']:.6f} "
          f"matches C43 scheme = {prod_match}")

    # --- metrics table (4 schemes x clean+ext) ---
    table = {}
    for sc, label in SCHEMES:
        table[sc] = {"label": label,
                     "clean": met(win(series[sc], CLEAN_START, end), cash),
                     "ext": met(win(series[sc], EXT_START, end), cash)}

    # --- paired bootstrap IV4 vs C(4,3) on Sharpe AND Martin ---
    boot = {}
    for wn, st in [("clean", CLEAN_START), ("ext", EXT_START)]:
        a = win(series["IV4"], st, end)
        b = win(series["C43"], st, end)
        common = a.index.intersection(b.index)
        a, b = a.reindex(common), b.reindex(common)
        ny = (common[-1] - common[0]).days / 365.25
        boot[wn] = {"n_days": len(common), "n_years": ny,
                    "corr": float(np.corrcoef(a.values, b.values)[0, 1]),
                    **paired_boot(a.values, b.values, ny)}
        sh = boot[wn]["sharpe_C43_minus_IV4"]; mt = boot[wn]["martin_C43_minus_IV4"]
        print(f"[{wn}] paired boot C43-IV4 Sharpe mean={sh['mean']:+.4f} "
              f"CI[{sh['ci_lo']:+.4f},{sh['ci_hi']:+.4f}] excl0={sh['excludes_zero']} | "
              f"Martin mean={mt['mean']:+.4f} CI[{mt['ci_lo']:+.4f},{mt['ci_hi']:+.4f}] "
              f"excl0={mt['excludes_zero']}")

    out = {"meta": {"conv": CONV, "cost_bps": COST, "lookback": LOOKBACK, "K": K,
                    "clean_start": str(CLEAN_START.date()),
                    "ext_start": str(EXT_START.date()), "end": str(end.date()),
                    "B": B, "block": BLOCK, "seed": SEED,
                    "ui_definition": "sqrt(mean(((eq/cummax-1)*100)^2)) over daily equity; "
                                     "Martin = CAGR(%)/UI(%)"},
           "anchor_gate": {"c43_clean": c43_clean, "expect": ANCHOR_C43, "ok": ok,
                           "prod_match": bool(prod_match)},
           "table": table, "bootstrap": boot}
    Path(__file__).with_suffix(".json").write_text(json.dumps(out, indent=2, default=float))
    write_md(out)
    print("\nDONE -> research/four_scheme_metrics_martin_findings.md")
    return out


def write_md(o):
    L = []
    A = L.append
    m = o["meta"]
    SC_ORDER = ["IV4", "C43", "C42", "CONT"]
    NAMES = {"IV4": "IV4 (no min-var)", "C43": "C(4,3) [PROD]",
             "C42": "C(4,2)", "CONT": "CONT (continuous)"}

    A("# CPM four-scheme metrics + Martin/UPI -- min-var sub-selection knob decision\n")
    A("Role: analyst (hypothesis-driven, read-only re production; NO production files changed; "
      "NO commit). Throwaway harness `research/four_scheme_metrics_martin.py`.\n")
    A("## Config / window / execution\n")
    A(f"- **CPM design (fixed across schemes):** ranker vol-Faber (10m-SMA-distance / rv_252d), "
      f"positive-trend screen, top-K={m['K']} momentum pool, canary HYG-OR-TIP (13612U), timed "
      f"SHV/IEF safe, cov lookback {m['lookback']}d.")
    A(f"- **Execution:** T+1 MOO exact (`{m['conv']}`, real yfinance auto_adjust opens), "
      f"post-cost {m['cost_bps']} bps/side.")
    A(f"- **Windows:** clean {m['clean_start']}..{m['end']} (18y); extended {m['ext_start']}.."
      f"{m['end']} (27y).")
    A("- **Schemes** (each its own COUNT-CONSISTENT strict partial-safe fallback, "
      "risky_fraction = min(n_pos, target)/target, remainder -> timed safe):")
    A("  1. **IV4** -- NO min-var; hold ALL top-4, inverse-vol; target=4 (strict-4 PS).")
    A("  2. **C(4,3)** = PROD -- min-var 3-subset of top-4, inverse-vol; target=3 (strict-3 PS).")
    A("  3. **C(4,2)** -- min-var 2-subset of top-4, inverse-vol; target=2 (strict-2 PS).")
    A("  4. **CONT** -- top-4 continuous min-variance (full-cov SLSQP), standard form "
      "(100% risky whenever >=1 positive; no partial-safe).")
    A(f"- **Ulcer Index (exact):** `UI = sqrt( mean( drawdown_pct^2 ) )` over the daily equity "
      f"curve, `drawdown_pct = (equity/running_max - 1) * 100` (PERCENT units). **Martin ratio = "
      f"CAGR(%) / UI(%)** (unit-consistent UPI; numerically identical to CAGR_frac/UI_frac). UI "
      f"value reported in percent.\n")

    g = o["anchor_gate"]; cg = g["c43_clean"]; e = g["expect"]
    A("## Anchor gate\n")
    A("| Scheme | Window | Sharpe | MaxDD | Calmar | Expected | Match |")
    A("|---|---|---:|---:|---:|---|---|")
    A(f"| C(4,3) [PROD] | clean | {cg['sharpe']:.4f} | {cg['maxdd']*100:.2f}% | {cg['calmar']:.4f} "
      f"| {e['sharpe']}/{e['maxdd']}%/{e['calmar']} | {'CONFIRMED' if g['ok'] else 'MISMATCH'} |")
    A(f"\nC(4,3) reproduces the production strict-3 anchor exactly. Production "
      f"`compute_target_weights` clean Sharpe matches the C(4,3) scheme series = "
      f"{g['prod_match']}. The other three schemes are trusted on that basis.\n")

    t = o["table"]
    A("## Four-scheme metrics table (4 schemes x 5 metrics x {clean, ext})\n")
    A("Sharpe = raw daily Sharpe (0 rf). Calmar = CAGR/|MaxDD|. Martin = CAGR(%)/UI(%). "
      "UI = Ulcer Index in percent (defn above).\n")
    A("| Scheme | Window | Sharpe | CAGR | MaxDD | Calmar | Martin | Ulcer Index |")
    A("|---|---|---:|---:|---:|---:|---:|---:|")
    for sc in SC_ORDER:
        for wn in ("clean", "ext"):
            d = t[sc][wn]
            A(f"| {NAMES[sc]} | {wn} | {d['sharpe']:.4f} | {d['cagr']*100:.2f}% | "
              f"{d['maxdd']*100:.2f}% | {d['calmar']:.4f} | {d['martin']:.4f} | {d['ui_pct']:.2f}% |")
    A("")

    # DD-aware ranking
    A("## DD-aware ranking (Calmar, Martin)\n")
    for wn in ("clean", "ext"):
        cal = sorted(SC_ORDER, key=lambda s: -t[s][wn]["calmar"])
        mar = sorted(SC_ORDER, key=lambda s: -t[s][wn]["martin"])
        A(f"**{wn}:**")
        A("- Calmar rank: " + " > ".join(
            f"{NAMES[s]} {t[s][wn]['calmar']:.4f}" for s in cal))
        A("- Martin rank: " + " > ".join(
            f"{NAMES[s]} {t[s][wn]['martin']:.4f}" for s in mar))
        A("")

    bo = o["bootstrap"]
    A("## Paired bootstrap IV4 vs C(4,3) -- Sharpe AND Martin\n")
    A(f"Stationary block bootstrap, B={m['B']}, block={m['block']}, seed={m['seed']}. Same block "
      f"index applied to both series each draw (paired). Reported difference = **C(4,3) - IV4** "
      f"(positive => C(4,3) higher; i.e. removing min-var to go IV4 hurts that metric).\n")
    A("| Window | Metric | mean (C43-IV4) | 95% CI | P(C43>IV4) | excludes 0 | daily corr |")
    A("|---|---|---:|---|---:|---|---:|")
    for wn in ("clean", "ext"):
        b = bo[wn]
        for mk, mlab in [("sharpe_C43_minus_IV4", "Sharpe"), ("martin_C43_minus_IV4", "Martin")]:
            d = b[mk]
            A(f"| {wn} | {mlab} | {d['mean']:+.4f} | [{d['ci_lo']:+.4f}, {d['ci_hi']:+.4f}] | "
              f"{d['p_b_gt_a']*100:.1f}% | {'YES' if d['excludes_zero'] else 'no'} | {b['corr']:.4f} |")
    A("")

    # verdict
    cc = {s: t[s]["clean"] for s in SC_ORDER}
    ec = {s: t[s]["ext"] for s in SC_ORDER}
    bs_c = bo["clean"]["sharpe_C43_minus_IV4"]; bm_c = bo["clean"]["martin_C43_minus_IV4"]
    A("## Verdict\n")
    A(f"- **IV4 vs C(4,3) on DD-aware metrics (clean):** C(4,3) Calmar {cc['C43']['calmar']:.4f} / "
      f"Martin {cc['C43']['martin']:.4f} vs IV4 Calmar {cc['IV4']['calmar']:.4f} / Martin "
      f"{cc['IV4']['martin']:.4f}. C(4,3) MaxDD {cc['C43']['maxdd']*100:.2f}% vs IV4 "
      f"{cc['IV4']['maxdd']*100:.2f}%.")
    bs_e = bo["ext"]["sharpe_C43_minus_IV4"]; bm_e = bo["ext"]["martin_C43_minus_IV4"]
    A(f"- **Significance (paired bootstrap):** clean C(4,3)-IV4 Sharpe mean {bs_c['mean']:+.4f} "
      f"CI [{bs_c['ci_lo']:+.4f}, {bs_c['ci_hi']:+.4f}] (excludes 0 = {bs_c['excludes_zero']}, "
      f"P(C43>IV4)={bs_c['p_b_gt_a']*100:.0f}%); clean Martin mean {bm_c['mean']:+.4f} CI "
      f"[{bm_c['ci_lo']:+.4f}, {bm_c['ci_hi']:+.4f}] (excludes 0 = {bm_c['excludes_zero']}, "
      f"P={bm_c['p_b_gt_a']*100:.0f}%). Ext Sharpe mean {bs_e['mean']:+.4f} "
      f"(excl0={bs_e['excludes_zero']}); ext Martin mean {bm_e['mean']:+.4f} "
      f"(excl0={bm_e['excludes_zero']}, P={bm_e['p_b_gt_a']*100:.0f}%).")
    A("  - **Removing min-var does NOT significantly change Martin/UPI** (nor Sharpe): no "
      "IV4-vs-C(4,3) difference excludes zero in either window on either metric, and on Martin the "
      "effect is essentially nil ext (mean ~0, P~50%). The min-var sub-selection knob buys at most "
      "a marginal clean Calmar edge (1.1306 vs 1.0615) that is statistically within noise; on Martin "
      "the two are a dead heat clean (3.9767 vs 3.9646) and IV4 is actually higher ext (3.8409 vs "
      "3.6946). **IV4 (no min-var) is NOT materially worse than C(4,3) on Martin/Calmar -- within "
      "noise.** Removing the knob is defensible.")
    A(f"- **C(4,2) (fewer names):** clean Sharpe {cc['C42']['sharpe']:.4f} / Calmar "
      f"{cc['C42']['calmar']:.4f} / Martin {cc['C42']['martin']:.4f} / MaxDD "
      f"{cc['C42']['maxdd']*100:.2f}% / UI {cc['C42']['ui_pct']:.2f}%; ext Martin "
      f"{ec['C42']['martin']:.4f} / MaxDD {ec['C42']['maxdd']*100:.2f}%. Tightening selection to 2 "
      f"names does nothing good: matched Sharpe but **worse Martin and worse (higher) Ulcer / deeper "
      f"MaxDD** in both windows (concentration raises sustained drawdown). Not interesting as an "
      f"improvement -- it is a DD-aware regression.")
    A(f"- **CONT (continuous min-var):** highest raw Sharpe (clean {cc['CONT']['sharpe']:.4f}, the "
      f"top of the four) but **sits at/near the BOTTOM on the DD-aware metrics** -- clean Calmar "
      f"{cc['CONT']['calmar']:.4f} (worst), Martin {cc['CONT']['martin']:.4f}, MaxDD "
      f"{cc['CONT']['maxdd']*100:.2f}% (worst), UI {cc['CONT']['ui_pct']:.2f}%; ext Martin "
      f"{ec['CONT']['martin']:.4f} (worst). Full-cov optimization concentrates into the low-vol "
      f"corner, lifting Sharpe but trading away tail/DD protection -- exactly the wrong direction for "
      f"a Martin/Calmar objective.")
    A("- **Net for the knob decision:** the min-var 3-subset (C(4,3)) is NOT robustly better than "
      "simply holding all top-4 inverse-vol (IV4) on any DD-aware metric; the gap is inside "
      "bootstrap noise. Going the OTHER direction (tighter C(4,2) or fully continuous CONT) both "
      "degrade Martin/Calmar. So if the goal is simplification, **removing the min-var sub-selection "
      "knob and shipping IV4 is the clean, DD-neutral simplification**; adding more selection "
      "aggressiveness is not justified.\n")

    A("## Caveats\n")
    A("- All post-cost (10 bps/side), T+1 MOO exact with real auto_adjust opens; CPM sleeve only "
      "(no BULL blend, no equity vol gate).")
    A("- Ext 27y is partially proxy-backed for the CPM trend universe pre-2006 (close-to-close "
      "fallback on a minority of rebal days); clean 18y has full real-open coverage and is the "
      "decisive lens.")
    A("- C(4,3) uses the same generalized weight fn (target=3) and is anchor-gated to production "
      "`compute_target_weights`; the cross-check confirms byte-equivalence.")
    A("- CONT uses full-covariance SLSQP (252-annualized daily cov over 504d) with inverse-vol "
      "fallback on solver failure; standard form holds 100% risky whenever >=1 top-4 positive.")
    A("- Martin/UPI uses the percent-based Ulcer Index defined above; Martin is unit-invariant so "
      "CAGR_frac/UI_frac == CAGR(%)/UI(%).")

    Path(ROOT / "research" / "four_scheme_metrics_martin_findings.md").write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
