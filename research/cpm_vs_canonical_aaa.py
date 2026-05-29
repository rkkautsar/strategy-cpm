"""Throwaway research (SCOPED): correct the CPM-side benchmark to CANONICAL AAA.

CORRECTION TO PRIOR WORK
------------------------
Prior CPM benchmark used "AAA + TIP canary" (bench_aaa_tip, build_dashboard.py:352),
a non-canonical hybrid. Canonical AAA (Adaptive Asset Allocation, Butler-Philbrick
2012) is momentum (13612U) top-half + minimum-variance weighting over the AAA
universe with NO canary / NO TIP gate; defense comes only from whatever rises to
the top of the momentum ranking (incl. bonds/cash via the positive-momentum
screen + best-of-safe fallback).

Canonical AAA is built by REMOVING this block from bench_aaa_tip
(build_dashboard.py around line 363-366):

    tipm = sig_13612U(monthly["TIP"]) if "TIP" in monthly.columns else float("nan")
    if not (pd.notna(tipm) and tipm > 0):
        wh.append((sd, {safe: 1.0})); continue      # <-- the TIP canary, removed

Everything else (universe, 13612U ranker, top-half cap, positive screen,
SLSQP min-var over survivors, SHV/IEF best-of-safe) is IDENTICAL to the repo AAA.

SCOPE (intentionally minimal; NO full 2^4 factorial):
  (1) Corrected headline benchmark: CPM-solo vs canonical AAA (no canary),
      CLEAN 18y + EXT 27y. Sharpe/CAGR/Vol/MaxDD/Calmar + excess Sharpe / IR /
      return correlation. Also report how canonical AAA differs from old AAA+TIP.
  (2) Canonical-AAA all-OFF anchor value itself.
  (3) Canary component contribution: from the canonical-AAA baseline with ALL
      OTHER CPM components at production-on (universe=QQQ/quality set, ranker=
      vol-Faber, pair=50/50 min-var), compare canary input
      NONE vs TIP-only vs HYG-only vs HYG-OR-TIP (Sharpe/Calmar/MaxDD each).
  (4) all-ON CPM anchor reproduction (~Sharpe 1.242 / Calmar 0.870) as a sanity
      check only.

Execution = headline convention everywhere: realistic T+1 MOO exact (mooex),
post-cost 10 bps/side, production slow vol gate is NOT part of CPM (CPM sleeve
has no vol gate). Both sleeve and every benchmark/canary cell run through the
SAME _segment_returns_conv harness => byte-identical cost/window/execution.

No production files touched. Writes JSON next to this file.
"""
import sys, math, json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.optimize import minimize

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import bull_qqq_live  # noqa: F401  (imported for harness side parity)
from cpm_live import (
    load_panel, perf_metrics, sig_13612U, best_safe, faber_sma_xs, min_vol_pair,
    COST_BPS_PER_SIDE, CORR_LOOKBACK_DAYS,
)
import exec_lag_moo_validation_2026_05_30 as H

CONV = "mooex"

# ---- universes / pools ----
AAA_UNIVERSE = ["SPY", "EFA", "EEM", "VNQ", "GLD", "TLT", "DBC"]              # canonical AAA universe
CPM_PROD_UNIVERSE = ["QQQ", "SPHQ", "EFA", "EEM", "VNQ", "GLD", "TLT", "DBC"]  # CPM production universe
SAFE = ["SHV", "IEF"]   # best-of-safe, common to both ends
MINVAR_LOOKBACK = 504   # repo AAA uses tail(504); CPM CORR_LOOKBACK_DAYS=504 too


# ============================================================================
# Benchmark weight functions
# ============================================================================
def _minvar_weights(daily, sd, top):
    cov = daily.loc[:sd].tail(MINVAR_LOOKBACK)[top].cov() * 252
    n = len(top)
    def obj(w, C=cov.values):
        return float(np.dot(w, np.dot(C, w)))
    cons = ({"type": "eq", "fun": lambda w: np.sum(w) - 1.0},)
    bnds = tuple((0.0, 1.0) for _ in range(n))
    r = minimize(obj, np.ones(n) / n, method="SLSQP", bounds=bnds, constraints=cons)
    return {top[i]: float(r.x[i]) for i in range(n)} if r.success else {t: 1.0 / n for t in top}


def make_canonical_aaa_wf(close, daily):
    """CANONICAL AAA: NO canary. 13612U top-half momentum + positive screen +
    SLSQP min-var over survivors + SHV/IEF best-of-safe. Identical to repo
    bench_aaa_tip with the TIP canary block removed."""
    def wf(sd):
        monthly = close.loc[:sd].resample("ME").last()
        safe = best_safe(monthly, sd, SAFE)
        # --- NO TIP canary here (this is exactly the removed block) ---
        scores = {t: sig_13612U(monthly[t]) for t in AAA_UNIVERSE if t in monthly.columns}
        scores = {t: s for t, s in scores.items() if pd.notna(s)}
        ranked = sorted(scores.items(), key=lambda x: -x[1])
        top_half = max(2, math.ceil(len(AAA_UNIVERSE) / 2))
        top = [t for t, s in ranked[:top_half] if s > 0]
        if len(top) == 0:
            return {safe: 1.0}
        if len(top) == 1:
            return {top[0]: 0.5, safe: 0.5}
        return _minvar_weights(daily, sd, top)
    return wf


def make_aaa_tip_wf(close, daily):
    """OLD baseline AAA+TIP (build_dashboard.py:352) for the canonical-vs-hybrid
    comparison. Identical to canonical AAA but WITH the TIP canary gate."""
    def wf(sd):
        monthly = close.loc[:sd].resample("ME").last()
        safe = best_safe(monthly, sd, SAFE)
        tipm = sig_13612U(monthly["TIP"]) if "TIP" in monthly.columns else float("nan")
        if not (pd.notna(tipm) and tipm > 0):
            return {safe: 1.0}
        scores = {t: sig_13612U(monthly[t]) for t in AAA_UNIVERSE if t in monthly.columns}
        scores = {t: s for t, s in scores.items() if pd.notna(s)}
        ranked = sorted(scores.items(), key=lambda x: -x[1])
        top_half = max(2, math.ceil(len(AAA_UNIVERSE) / 2))
        top = [t for t, s in ranked[:top_half] if s > 0]
        if len(top) == 0:
            return {safe: 1.0}
        if len(top) == 1:
            return {top[0]: 0.5, safe: 0.5}
        return _minvar_weights(daily, sd, top)
    return wf


# ============================================================================
# CPM production structure with a parametric canary (for component decomposition)
# Universe = production, ranker = vol-Faber, pair = 50/50 min-var. canary_mode in
#   {"none", "tip", "hyg", "hygortip"}.  "none" == canonical-AAA-style defense
#   (no risk-off gate); "hygortip" == CPM production canary.
# ============================================================================
def make_cpm_prod_canary_wf(close, daily, canary_mode):
    universe = CPM_PROD_UNIVERSE
    def wf(sd):
        monthly = close.loc[:sd].resample("ME").last()
        safe = best_safe(monthly, sd, SAFE)

        # --- canary gate ---
        if canary_mode != "none":
            if canary_mode == "tip":
                ca = ["TIP"]
            elif canary_mode == "hyg":
                ca = ["HYG"]
            else:  # hygortip
                ca = ["HYG", "TIP"]
            cs = [sig_13612U(monthly[a]) for a in ca if a in monthly.columns]
            cs = [s for s in cs if pd.notna(s)]
            if not cs or sum(1 for s in cs if s > 0) == 0:
                return {safe: 1.0}

        # --- vol-adjusted Faber ranker (production) ---
        present = [t for t in universe if t in monthly.columns]
        faber = faber_sma_xs(monthly)
        avail = [t for t in present if t in faber.index and pd.notna(faber[t])
                 and (sd in close.index and pd.notna(close.loc[sd].get(t, np.nan)))]
        if not avail:
            return {safe: 1.0}
        dr = close[avail].ffill().pct_change()
        score = {}
        for t in avail:
            v = dr[t].loc[:sd].tail(252).std() * np.sqrt(252)
            if pd.isna(v) or v < 1e-9:
                v = 1.0
            score[t] = float(faber[t]) / v
        ranked = pd.Series(score).sort_values(ascending=False)
        top_half = max(2, math.ceil(len(universe) / 2))
        top_k = max(2, min(top_half, len(ranked)))
        top = ranked.iloc[:top_k]
        positive = [t for t in top.index if faber.get(t, -np.inf) > 0]

        if len(positive) == 0:
            return {safe: 1.0}
        if len(positive) == 1:
            return {positive[0]: 0.5, safe: 0.5}
        # --- 50/50 min-var pair (production) ---
        pick = min_vol_pair(close.loc[:sd, positive], positive, CORR_LOOKBACK_DAYS)
        if pick is None:
            return {positive[0]: 1.0}
        return {pick[0]: 0.5, pick[1]: 0.5}
    return wf


# ============================================================================
# runners / metrics
# ============================================================================
def met(daily, cash):
    m = perf_metrics(daily, cash)
    return {"sharpe": m.get("sharpe"), "cagr": m.get("cagr"),
            "maxdd": m.get("max_drawdown"), "calmar": m.get("calmar"), "vol": m.get("vol")}


def run_wf(close, daily, intraday, overnight, start, end, wf):
    s, _ = H._segment_returns_conv(close, daily, wf, start, end, CONV,
                                   COST_BPS_PER_SIDE, intraday, overnight)
    return s


def active_stats(sleeve, bench, cash):
    common = sleeve.index.intersection(bench.index)
    s = sleeve.reindex(common).fillna(0.0)
    b = bench.reindex(common).fillna(0.0)
    ms, mb = met(s, cash), met(b, cash)
    diff = s - b
    te = float(diff.std() * np.sqrt(252))
    ir = float((diff.mean() * 252) / te) if te > 1e-12 else float("nan")
    corr = float(np.corrcoef(s.values, b.values)[0, 1])
    return {"sleeve": ms, "bench": mb,
            "d_cagr": ms["cagr"] - mb["cagr"], "d_calmar": ms["calmar"] - mb["calmar"],
            "d_sharpe": ms["sharpe"] - mb["sharpe"], "d_maxdd": ms["maxdd"] - mb["maxdd"],
            "corr": corr, "te": te, "ir": ir, "n": len(common)}


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

    print(f"Panel {panel.index[0].date()} -> {panel.index[-1].date()} ({len(panel)} rows)")
    print(f"Convention={CONV}  cost={COST_BPS_PER_SIDE}bps/side  minvar_lookback={MINVAR_LOOKBACK}\n")

    # ---- CPM-solo sleeve (production) over ext window ----
    cpm, _ = H.cpm_sleeve_conv(panel, intraday, overnight, ext_start, end, CONV)

    # ---- AAA panels ----
    aaa_cols = sorted(set(AAA_UNIVERSE + SAFE + ["TIP"]) & set(panel.columns))
    aaa_close = panel[aaa_cols]
    aaa_daily = aaa_close.ffill().pct_change()
    canon = run_wf(aaa_close, aaa_daily, intraday, overnight, ext_start, end,
                   make_canonical_aaa_wf(aaa_close, aaa_daily))
    aaatip = run_wf(aaa_close, aaa_daily, intraday, overnight, ext_start, end,
                    make_aaa_tip_wf(aaa_close, aaa_daily))

    # ---- canary decomposition panels (production CPM structure) ----
    cpm_cols = sorted(set(CPM_PROD_UNIVERSE + SAFE + ["HYG", "TIP"]) & set(panel.columns))
    cpm_close = panel[cpm_cols]
    cpm_daily = cpm_close.ffill().pct_change()
    canary_series = {}
    for mode in ["none", "tip", "hyg", "hygortip"]:
        canary_series[mode] = run_wf(cpm_close, cpm_daily, intraday, overnight,
                                     ext_start, end, make_cpm_prod_canary_wf(cpm_close, cpm_daily, mode))

    windows = {"CLEAN_18y": (clean_start, end), "EXT_27y": (ext_start, end)}

    # ===== anchor sanity =====
    cpm_c = cpm.loc[clean_start:end]
    print("=== ANCHOR SANITY (CLEAN 18y, mooex) ===")
    mc = met(cpm_c, cash)
    print(f"  CPM-solo all-ON   Sharpe={mc['sharpe']:.3f} Calmar={mc['calmar']:.3f} "
          f"(expect ~1.242/0.870)")
    canon_c = met(canon.loc[clean_start:end], cash)
    print(f"  Canonical AAA off Sharpe={canon_c['sharpe']:.3f} Calmar={canon_c['calmar']:.3f} "
          f"MaxDD={canon_c['maxdd']*100:.2f}%")
    # cross-check: canary 'hygortip' production-structure should ~ CPM-solo all-ON
    hot = met(canary_series["hygortip"].loc[clean_start:end], cash)
    print(f"  CPM prod+HYGorTIP Sharpe={hot['sharpe']:.3f} Calmar={hot['calmar']:.3f} "
          f"(cross-check vs CPM-solo all-ON)\n")

    out = {"benchmark": {}, "canary_decomp": {}, "anchor": {
        "cpm_solo_all_on_clean": mc, "canonical_aaa_all_off_clean": canon_c,
        "cpm_prod_hygortip_clean": hot}}

    # ===== (1) corrected benchmark: CPM vs canonical AAA, + how canonical differs from AAA+TIP =====
    for wn, (ws, we) in windows.items():
        cpm_w = cpm.loc[(cpm.index >= ws) & (cpm.index <= we)]
        canon_w = canon.loc[(canon.index >= ws) & (canon.index <= we)]
        aaatip_w = aaatip.loc[(aaatip.index >= ws) & (aaatip.index <= we)]
        out["benchmark"][wn] = {
            "CPM_vs_canonical_AAA": active_stats(cpm_w, canon_w, cash),
            "canonical_AAA": met(canon_w, cash),
            "AAA_plus_TIP": met(aaatip_w, cash),
        }

    # ===== (3) canary component decomposition =====
    for wn, (ws, we) in windows.items():
        out["canary_decomp"][wn] = {}
        for mode, s in canary_series.items():
            sw = s.loc[(s.index >= ws) & (s.index <= we)]
            out["canary_decomp"][wn][mode] = met(sw, cash)

    Path(__file__).with_suffix(".json").write_text(json.dumps(out, indent=2, default=float))

    # ===== console report =====
    def fmt_block(title, st):
        sl, bn = st["sleeve"], st["bench"]
        print(title)
        print(f"  {'':<14}{'Sharpe':>8}{'CAGR':>9}{'Vol':>8}{'MaxDD':>9}{'Calmar':>8}")
        print(f"  {'CPM-solo':<14}{sl['sharpe']:>8.3f}{sl['cagr']*100:>8.2f}%{sl['vol']*100:>7.2f}%{sl['maxdd']*100:>8.2f}%{sl['calmar']:>8.3f}")
        print(f"  {'canon AAA':<14}{bn['sharpe']:>8.3f}{bn['cagr']*100:>8.2f}%{bn['vol']*100:>7.2f}%{bn['maxdd']*100:>8.2f}%{bn['calmar']:>8.3f}")
        print(f"  active: dCAGR={st['d_cagr']*100:+.2f}pp dCalmar={st['d_calmar']:+.3f} "
              f"dSharpe={st['d_sharpe']:+.3f} dMaxDD={st['d_maxdd']*100:+.2f}pp")
        print(f"  corr={st['corr']:.3f} TE={st['te']*100:.2f}% IR={st['ir']:+.3f} n={st['n']}\n")

    for wn in windows:
        print("=" * 72)
        print(f"WINDOW {wn}   (config: CPM production vs canonical AAA no-canary, mooex, 10bps/side)")
        print("=" * 72)
        fmt_block("CPM-solo vs CANONICAL AAA (no canary):", out["benchmark"][wn]["CPM_vs_canonical_AAA"])
        ca = out["benchmark"][wn]["canonical_AAA"]
        at = out["benchmark"][wn]["AAA_plus_TIP"]
        print("  How canonical AAA (no canary) differs from old AAA+TIP baseline:")
        print(f"    {'':<14}{'Sharpe':>8}{'CAGR':>9}{'MaxDD':>9}{'Calmar':>8}")
        print(f"    {'canon AAA':<14}{ca['sharpe']:>8.3f}{ca['cagr']*100:>8.2f}%{ca['maxdd']*100:>8.2f}%{ca['calmar']:>8.3f}")
        print(f"    {'AAA+TIP(old)':<14}{at['sharpe']:>8.3f}{at['cagr']*100:>8.2f}%{at['maxdd']*100:>8.2f}%{at['calmar']:>8.3f}")
        print(f"    delta(canon-AAA+TIP): dSharpe={ca['sharpe']-at['sharpe']:+.3f} "
              f"dMaxDD={(ca['maxdd']-at['maxdd'])*100:+.2f}pp dCalmar={ca['calmar']-at['calmar']:+.3f}\n")

    print("=" * 72)
    print("CANARY COMPONENT DECOMPOSITION")
    print("  (config: CPM production structure [QQQ/quality universe, vol-Faber ranker,")
    print("   50/50 min-var pair], canary input varied; mooex, 10bps/side)")
    print("=" * 72)
    for wn in windows:
        print(f"\n  {wn}:")
        print(f"    {'canary':<12}{'Sharpe':>8}{'Calmar':>8}{'MaxDD':>9}{'CAGR':>9}")
        base = out["canary_decomp"][wn]["none"]
        for mode in ["none", "tip", "hyg", "hygortip"]:
            m = out["canary_decomp"][wn][mode]
            tag = ""
            if mode != "none":
                tag = f"  (dSharpe={m['sharpe']-base['sharpe']:+.3f} dCalmar={m['calmar']-base['calmar']:+.3f} dMaxDD={(m['maxdd']-base['maxdd'])*100:+.2f}pp vs none)"
            print(f"    {mode:<12}{m['sharpe']:>8.3f}{m['calmar']:>8.3f}{m['maxdd']*100:>8.2f}%{m['cagr']*100:>8.2f}%{tag}")

    print("\nDONE -> json written")


if __name__ == "__main__":
    main()
