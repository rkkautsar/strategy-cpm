#!/usr/bin/env python3
"""
FCP + PP-IEF Blend Revisit — current production spec (FCP-15 with XLV).

Hypothesis: the PP-IEF static buffer (25/25/25/25 SPY/IEF/GLD/SHV) may
improve the blended risk-adjusted profile of FCP-15 at some fraction, even
though FCP-15 is now the dominant alpha source and the 70/30 blend is already
in production. This script re-evaluates across the full blend spectrum.

Windows:
  hybrid_start = 1997-08-31  (~28.7y to May 2026)
  live_start   = 2008-09-30  (~17.6y, "live-only 18y" window)

Experiments:
  1. Blend sweep: w_FCP in {1.0, 0.9, ..., 0.2, 0.0}
  2. Optimal blend (max Sharpe, max UPI) on each window
  3. Bootstrap Sharpe-difference: best blend vs FCP vs PP-IEF
  4. Tax-drag scenario: FCP 1.5% p.a. drag, PP-IEF 0.3% p.a. drag

Usage:
    cd /Users/rkautsar/personal/scripts
    python strategy_fcp/research/fcp_pp_blend_revisit.py 2>&1 | tee strategy_fcp/research/fcp_pp_blend_revisit.log
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from strategy_fcp.fcp_live import (
    load_panel,
    run_fcp_backtest,
    run_pp_backtest,
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
HYBRID_START = pd.Timestamp("1997-08-31")
LIVE_START   = pd.Timestamp("2008-09-30")
BLEND_WEIGHTS = [1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.0]

TAX_DRAG_FCP = 0.015   # 1.5% p.a. (high turnover)
TAX_DRAG_PP  = 0.003   # 0.3% p.a. (monthly rebal, mostly buy-hold)

BOOTSTRAP_B     = 3000
BOOTSTRAP_BLOCK = 21
BOOTSTRAP_SEED  = 42

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
_LOG_LINES: list[str] = []

def log(*args):
    line = " ".join(str(a) for a in args)
    print(line)
    _LOG_LINES.append(line)

# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def ulcer_index(eq: pd.Series) -> float:
    eq = eq.dropna()
    if eq.empty:
        return float("nan")
    dd_pct = (eq / eq.cummax() - 1) * 100.0
    return float(np.sqrt((dd_pct ** 2).mean()))


def upi(daily_ret: pd.Series) -> float:
    """UPI (Martin) = CAGR% / Ulcer Index."""
    r = daily_ret.fillna(0)
    eq = (1 + r).cumprod()
    ui = ulcer_index(eq)
    if ui == 0 or np.isnan(ui):
        return float("nan")
    n_y = len(r) / 252.0
    if n_y <= 0:
        return float("nan")
    cagr_pct = (eq.iloc[-1] ** (1 / n_y) - 1) * 100.0
    return cagr_pct / ui


def pain_ratio(daily_ret: pd.Series) -> float:
    """Pain Ratio = CAGR% / mean(|DD%|)."""
    r = daily_ret.fillna(0)
    eq = (1 + r).cumprod()
    dd_pct = (eq / eq.cummax() - 1) * 100.0
    mean_pain = abs(dd_pct).mean()
    if mean_pain == 0 or np.isnan(mean_pain):
        return float("nan")
    n_y = len(r) / 252.0
    if n_y <= 0:
        return float("nan")
    cagr_pct = (eq.iloc[-1] ** (1 / n_y) - 1) * 100.0
    return cagr_pct / mean_pain


def sortino(daily_ret: pd.Series) -> float:
    r = daily_ret.dropna()
    dn = r[r < 0]
    if len(dn) < 2:
        return float("nan")
    dd_ann = dn.std() * np.sqrt(252)
    if dd_ann == 0:
        return float("nan")
    return (r.mean() * 252) / dd_ann


def all_metrics(daily_ret: pd.Series) -> dict:
    r = daily_ret.dropna()
    if r.empty:
        return {}
    eq = (1 + r).cumprod()
    n_y = len(r) / 252.0
    cagr_v = eq.iloc[-1] ** (1 / n_y) - 1 if n_y > 0 else float("nan")
    vol_v  = r.std() * np.sqrt(252)
    sh_v   = (r.mean() * 252) / vol_v if vol_v > 0 else float("nan")
    mdd_v  = (eq / eq.cummax() - 1).min()
    return dict(
        years=round(n_y, 1),
        cagr=cagr_v,
        vol=vol_v,
        sharpe=sh_v,
        sortino=sortino(r),
        maxdd=mdd_v,
        upi=upi(r),
        pain=pain_ratio(r),
    )

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

def block_bootstrap_sharpe_ci(daily: pd.Series,
                               B=BOOTSTRAP_B, block=BOOTSTRAP_BLOCK, seed=BOOTSTRAP_SEED):
    r = daily.dropna().values
    n = len(r)
    if n < block * 2:
        return float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    n_blocks = n // block + 1
    starts = rng.integers(0, n - block + 1, size=(B, n_blocks))
    offsets = np.arange(block)
    idx = (starts[:, :, None] + offsets[None, None, :]).reshape(B, -1)[:, :n]
    samples = r[idx]
    m_ann = samples.mean(axis=1) * 252
    s_ann = samples.std(axis=1) * np.sqrt(252)
    sharpes = np.where(s_ann > 0, m_ann / s_ann, 0.0)
    return float(np.percentile(sharpes, 2.5)), float(np.percentile(sharpes, 97.5))


def bootstrap_diff(daily_a: pd.Series, daily_b: pd.Series,
                   B=BOOTSTRAP_B, block=BOOTSTRAP_BLOCK, seed=BOOTSTRAP_SEED):
    """Returns (point_diff, ci_lo, ci_hi, p_a_wins): Sharpe(a) - Sharpe(b)."""
    df = pd.concat([daily_a.rename("a"), daily_b.rename("b")], axis=1).dropna()
    a, b = df["a"].values, df["b"].values
    n = len(a)
    if n < block * 2:
        return float("nan"), float("nan"), float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    n_blocks = n // block + 1
    starts = rng.integers(0, n - block + 1, size=(B, n_blocks))
    offsets = np.arange(block)
    idx = (starts[:, :, None] + offsets[None, None, :]).reshape(B, -1)[:, :n]
    sa, sb = a[idx], b[idx]
    ma  = sa.mean(axis=1) * 252;  sda = sa.std(axis=1) * np.sqrt(252) + 1e-9
    mb  = sb.mean(axis=1) * 252;  sdb = sb.std(axis=1) * np.sqrt(252) + 1e-9
    diffs = (ma / sda) - (mb / sdb)
    pt_a = (a.mean() * 252) / (a.std() * np.sqrt(252))
    pt_b = (b.mean() * 252) / (b.std() * np.sqrt(252))
    return (
        float(pt_a - pt_b),
        float(np.percentile(diffs, 2.5)),
        float(np.percentile(diffs, 97.5)),
        float((diffs > 0).mean()),
    )

# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def _na(v, fmt):
    if v is None:
        return "  N/A  "
    try:
        if np.isnan(float(v)):
            return "  N/A  "
    except Exception:
        pass
    return fmt % v


def fmt_sweep_row(w, m):
    label = "w_FCP=%.1f" % w
    cagr_s = "%+9.2f%%" % (m["cagr"] * 100) if not np.isnan(m.get("cagr", float("nan"))) else "   N/A   "
    dd_s   = "%+8.2f%%" % (m["maxdd"] * 100) if not np.isnan(m.get("maxdd", float("nan"))) else "  N/A  "
    return ("  %-28s  %8s  %7s  %9s  %8s  %7s  %7s  %7s  %5.1f" % (
        label,
        _na(m.get("sharpe"),  "%.3f"),
        _na(m.get("sortino"), "%.2f"),
        cagr_s,
        dd_s,
        _na(m.get("upi"),  "%.2f"),
        _na(m.get("pain"), "%.2f"),
        _na(m.get("vol"),  "%.3f"),
        m.get("years", float("nan")),
    ))

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    t0 = time.time()
    log("=" * 112)
    log("FCP + PP-IEF BLEND REVISIT — CURRENT PRODUCTION SPEC (FCP-15 with XLV)")
    log("Generated: %s" % pd.Timestamp.now().isoformat())
    log("Windows: Hybrid %s | Live-only %s" % (HYBRID_START.date(), LIVE_START.date()))
    log("Blend ratios w_FCP: %s" % BLEND_WEIGHTS)
    log("Bootstrap B=%d, block=%dd, seed=%d" % (BOOTSTRAP_B, BOOTSTRAP_BLOCK, BOOTSTRAP_SEED))
    log("Tax drag: FCP=%.1f%%/y, PP-IEF=%.1f%%/y" % (TAX_DRAG_FCP * 100, TAX_DRAG_PP * 100))
    log("=" * 112)

    # ── Load panel ──────────────────────────────────────────────────────────
    log("\nLoading price panel...")
    panel = load_panel(start=pd.Timestamp("1995-01-01"))
    end   = panel.index.max()
    log("Panel: %s -> %s, %d assets" % (panel.index[0].date(), end.date(), len(panel.columns)))

    # ── Run base backtests ──────────────────────────────────────────────────
    log("\nRunning FCP standalone backtest (vol-target ON, 10bps/side)...")
    fcp_full, _ = run_fcp_backtest(panel, HYBRID_START, end,
                                   apply_vol_target=True, cost_bps=10)
    log("FCP: %s -> %s (%d days)" % (fcp_full.index[0].date(), fcp_full.index[-1].date(), len(fcp_full)))

    log("Running PP-IEF static backtest (monthly rebal, 25/25/25/25)...")
    pp_full = run_pp_backtest(panel, HYBRID_START, end)
    log("PP:  %s -> %s (%d days)" % (pp_full.index[0].date(), pp_full.index[-1].date(), len(pp_full)))

    common  = fcp_full.index.intersection(pp_full.index)
    fcp_all = fcp_full.reindex(common).fillna(0.0)
    pp_all  = pp_full.reindex(common).fillna(0.0)

    def win(s, start):
        return s.loc[s.index >= start]

    windows = [
        ("Extended 28.7y",  HYBRID_START),
        ("Live-only 18y", LIVE_START),
    ]

    # ── EXPERIMENT 1+2: Blend sweep ─────────────────────────────────────────
    log("\n" + "=" * 112)
    log("EXPERIMENT 1+2: BLEND RATIO SWEEP & OPTIMAL BLEND")
    log("=" * 112)

    results = {}

    for win_label, win_start in windows:
        fw = win(fcp_all, win_start)
        pw = win(pp_all,  win_start)

        log("\n" + "-" * 112)
        log("  Window: %s  (%s -> %s, %.1fy)" % (
            win_label, fw.index[0].date(), fw.index[-1].date(), len(fw) / 252))
        log("-" * 112)
        log("  %-28s  %8s  %7s  %9s  %8s  %7s  %7s  %7s  %5s" % (
            "Strategy", "Sh", "Srt", "CAGR", "MaxDD", "UPI", "Pain", "Vol", "Yrs"))
        log("  " + "-" * 107)

        for w in BLEND_WEIGHTS:
            blended = w * fw + (1 - w) * pw
            m = all_metrics(blended)
            results[(win_label, w)] = m
            log(fmt_sweep_row(w, m))

        sharpes  = {w: results[(win_label, w)].get("sharpe", float("nan")) for w in BLEND_WEIGHTS}
        upis_map = {w: results[(win_label, w)].get("upi",    float("nan")) for w in BLEND_WEIGHTS}
        valid_sh = {w: v for w, v in sharpes.items()  if not np.isnan(v)}
        valid_up = {w: v for w, v in upis_map.items() if not np.isnan(v)}
        best_sh  = max(valid_sh, key=valid_sh.get) if valid_sh else None
        best_up  = max(valid_up, key=valid_up.get) if valid_up else None
        log("\n  >> Max-Sharpe blend : w_FCP=%.1f  Sharpe=%.3f" % (best_sh, sharpes.get(best_sh, float("nan"))))
        log("  >> Max-UPI blend    : w_FCP=%.1f  UPI   =%.2f"    % (best_up, upis_map.get(best_up, float("nan"))))
        log("  >> FCP standalone   : w_FCP=1.0  Sharpe=%.3f  UPI=%.2f" % (
            sharpes.get(1.0, float("nan")), upis_map.get(1.0, float("nan"))))
        log("  >> PP-IEF alone     : w_FCP=0.0  Sharpe=%.3f  UPI=%.2f" % (
            sharpes.get(0.0, float("nan")), upis_map.get(0.0, float("nan"))))

    # ── EXPERIMENT 4: Bootstrap ─────────────────────────────────────────────
    log("\n" + "=" * 112)
    log("EXPERIMENT 4: BOOTSTRAP SHARPE-DIFFERENCE TEST (B=%d, block=%dd)" % (BOOTSTRAP_B, BOOTSTRAP_BLOCK))
    log("  Comparisons: best_blend vs FCP | best_blend vs PP-IEF | FCP vs PP-IEF")
    log("  95% CI = percentile block-bootstrap (Politis-Romano style)")
    log("=" * 112)

    for win_label, win_start in windows:
        fw = win(fcp_all, win_start)
        pw = win(pp_all,  win_start)

        sharpes  = {w: results[(win_label, w)].get("sharpe", float("nan")) for w in BLEND_WEIGHTS}
        valid_sh = {w: v for w, v in sharpes.items() if not np.isnan(v)}
        best_sh  = max(valid_sh, key=valid_sh.get)
        blend_best = best_sh * fw + (1 - best_sh) * pw

        log("\n  Window: %s | Best-Sharpe blend: w_FCP=%.1f" % (win_label, best_sh))
        log("  %-44s  %9s  %8s  %8s  %8s  Verdict" % ("Comparison", "PointDSh", "CI_lo", "CI_hi", "P(A>B)"))

        pairs = [
            ("BestBlend(w=%.1f) vs FCP"    % best_sh, blend_best, "FCP",    fw),
            ("BestBlend(w=%.1f) vs PP-IEF" % best_sh, blend_best, "PP-IEF", pw),
            ("FCP vs PP-IEF",                          fw,         "PP-IEF", pw),
        ]
        for label_a, ser_a, _label_b, ser_b in pairs:
            pt, lo, hi, p_pos = bootstrap_diff(ser_a, ser_b)
            if np.isnan(pt):
                log("  %-44s  (insufficient data)" % label_a)
                continue
            if hi < 0:
                verdict = "B wins (95%)"
            elif lo > 0:
                verdict = "A wins (95%)"
            else:
                verdict = "inconclusive (CI crosses 0)"
            log("  %-44s  %+9.3f  %+8.3f  %+8.3f  %8.3f  %s" % (
                label_a, pt, lo, hi, p_pos, verdict))

        log("\n  Sharpe 95% CI (block bootstrap):")
        for lbl, ser in [("BestBlend(w=%.1f)" % best_sh, blend_best),
                          ("FCP standalone", fw),
                          ("PP-IEF", pw)]:
            ci_lo, ci_hi = block_bootstrap_sharpe_ci(ser)
            r = ser.dropna()
            sh_pt = (r.mean() * 252) / (r.std() * np.sqrt(252))
            log("    %-32s  Sh=%+.3f  95%%CI=[%+.3f, %+.3f]" % (lbl, sh_pt, ci_lo, ci_hi))

    # ── EXPERIMENT 5: Tax drag ──────────────────────────────────────────────
    log("\n" + "=" * 112)
    log("EXPERIMENT 5: TAX-DRAG SCENARIO")
    log("  FCP tax drag:    %.1f%% p.a. -> %.4f%%/day" % (
        TAX_DRAG_FCP * 100, TAX_DRAG_FCP / 252 * 100))
    log("  PP-IEF tax drag: %.1f%% p.a. -> %.4f%%/day" % (
        TAX_DRAG_PP * 100, TAX_DRAG_PP / 252 * 100))
    log("  Method: subtract drag from raw daily return series, then blend")
    log("=" * 112)

    fcp_taxed = fcp_all - TAX_DRAG_FCP / 252.0
    pp_taxed  = pp_all  - TAX_DRAG_PP  / 252.0

    for win_label, win_start in windows:
        ftw = win(fcp_taxed, win_start)
        ptw = win(pp_taxed,  win_start)
        fw0 = win(fcp_all,   win_start)
        pw0 = win(pp_all,    win_start)

        log("\n  Window: %s" % win_label)
        log("  %-22s  %11s  %12s  %11s  %8s  %10s" % (
            "Strategy", "Sh(pre-tax)", "Sh(post-tax)", "CAGR(post)", "MaxDD", "UPI(post)"))
        log("  " + "-" * 90)

        tax_sharpes = {}
        tax_upis    = {}
        for w in BLEND_WEIGHTS:
            bt  = w * ftw + (1 - w) * ptw
            bpt = w * fw0 + (1 - w) * pw0
            mt  = all_metrics(bt)
            mp  = all_metrics(bpt)
            tax_sharpes[w] = mt.get("sharpe", float("nan"))
            tax_upis[w]    = mt.get("upi",    float("nan"))
            cagr_s = "%+.2f%%" % (mt["cagr"] * 100) if not np.isnan(mt.get("cagr", float("nan"))) else "  N/A  "
            dd_s   = "%+.2f%%" % (mt["maxdd"] * 100) if not np.isnan(mt.get("maxdd", float("nan"))) else "  N/A  "
            log("  w_FCP=%.1f  %-10s  %11s  %12s  %11s  %8s  %10s" % (
                w, "",
                _na(mp.get("sharpe"), "%.3f"),
                _na(mt.get("sharpe"), "%.3f"),
                cagr_s, dd_s,
                _na(mt.get("upi"), "%.2f"),
            ))

        valid_tsh = {w: v for w, v in tax_sharpes.items() if not np.isnan(v)}
        valid_tup = {w: v for w, v in tax_upis.items()    if not np.isnan(v)}
        best_tsh  = max(valid_tsh, key=valid_tsh.get) if valid_tsh else None
        best_tup  = max(valid_tup, key=valid_tup.get) if valid_tup else None
        log("\n  >> Tax-adj Max-Sharpe blend: w_FCP=%.1f  Sh=%.3f" % (
            best_tsh, tax_sharpes.get(best_tsh, float("nan"))))
        log("  >> Tax-adj Max-UPI blend:    w_FCP=%.1f  UPI=%.2f" % (
            best_tup, tax_upis.get(best_tup, float("nan"))))

    # ── Summary table ───────────────────────────────────────────────────────
    log("\n" + "=" * 112)
    log("SUMMARY: KEY BLEND RATIOS — BOTH WINDOWS")
    log("=" * 112)

    key_ratios = [1.0, 0.8, 0.7, 0.6, 0.5, 0.3, 0.0]

    for win_label, win_start in windows:
        fw = win(fcp_all, win_start)
        pw = win(pp_all,  win_start)

        sharpes  = {w: results[(win_label, w)].get("sharpe", float("nan")) for w in BLEND_WEIGHTS}
        upis_map = {w: results[(win_label, w)].get("upi",    float("nan")) for w in BLEND_WEIGHTS}
        valid_sh = {w: v for w, v in sharpes.items()  if not np.isnan(v)}
        valid_up = {w: v for w, v in upis_map.items() if not np.isnan(v)}
        best_sh  = max(valid_sh, key=valid_sh.get) if valid_sh else None
        best_up  = max(valid_up, key=valid_up.get) if valid_up else None

        log("\n  %s" % win_label)
        log("  %-22s  %7s  %7s  %9s  %8s  %7s  %7s  Note" % (
            "Strategy", "Sh", "Srt", "CAGR", "MaxDD", "UPI", "Pain"))
        log("  " + "-" * 104)

        for w in key_ratios:
            m = results.get((win_label, w), {})
            if not m:
                continue
            notes = []
            if w == best_sh and w == best_up:
                notes.append("MaxSh+MaxUPI")
            elif w == best_sh:
                notes.append("MaxSharpe")
            elif w == best_up:
                notes.append("MaxUPI")
            if w == 0.7:
                notes.append("production")
            if w == 1.0:
                notes.append("FCP only")
            if w == 0.0:
                notes.append("PP-IEF only")
            note_s = " | ".join(notes)
            cagr_s = "%+.2f%%" % (m["cagr"] * 100) if not np.isnan(m.get("cagr", float("nan"))) else "  N/A  "
            dd_s   = "%+.2f%%" % (m["maxdd"] * 100) if not np.isnan(m.get("maxdd", float("nan"))) else "  N/A  "
            log("  w_FCP=%.1f  %-10s  %7s  %7s  %9s  %8s  %7s  %7s  %s" % (
                w, "",
                _na(m.get("sharpe"),  "%.3f"),
                _na(m.get("sortino"), "%.2f"),
                cagr_s, dd_s,
                _na(m.get("upi"),  "%.2f"),
                _na(m.get("pain"), "%.2f"),
                note_s,
            ))

    elapsed = time.time() - t0
    log("\n" + "=" * 112)
    log("Done in %.1fs" % elapsed)
    log("=" * 112)


if __name__ == "__main__":
    main()
