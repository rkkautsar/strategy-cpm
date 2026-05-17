#!/usr/bin/env python3
"""
cleaner_universe_experiments.py
================================
EXPERIMENT: How does FCP performance change with cleaner universe substitutions
for short-history factor ETFs?

Current FCP-15 short-history problem:
  SPMO  live 2015-10  proxy=SPY (20y of SPY masquerading as momentum)
  COWZ  live 2016-12  proxy=SPY (21y of SPY masquerading as FCF-quality)
  AVUV  live 2019-09  proxy=DFSVX (~24y of DFA Small Value mutual fund)
  AVUV also redundant with VBR (both US small-cap value)

Experiments:
  EXP A — Drop short-history names individually and combined
  EXP B — Swap with longer-live substitutes (SPMO->MTUM, COWZ->PRF, AVUV->SLYV)
  EXP C — International swap VEA/VWO -> EFA/EEM (6+2yr more live history)
  EXP D — Combined clean: drop AVUV, SPMO->MTUM, COWZ->PRF, VEA/VWO->EFA/EEM

Windows:
  Hybrid-28y : 1997-08-31 (proxy-stitched)
  Live-18y   : 2008-09-30 (cleanest common window)
  All-live   : first date all retained/substitute assets have actual live data + 12mo warmup

Settings: HOLD_BUFFER=2.5, vol-target=ON, cost=10bps/side (20bps RT)

Output:
  strategy_fcp/research/cleaner_universe_experiments.log
  strategy_fcp/research/cleaner_universe_results.csv
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import strategy_fcp.fcp_live as fcp
from strategy_fcp.fcp_live import (
    load_panel,
    run_fcp_backtest,
    SAFE_POOL, CANARY_ASSETS, DEFAULT_CASH, PP_ASSETS,
)

LOG_PATH = Path(__file__).parent / "cleaner_universe_experiments.log"

# ─────────────────────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────────────────────

_log_lines: list[str] = []


def log(line: str = "") -> None:
    _log_lines.append(line)
    print(line, flush=True)


def flush_log() -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text("\n".join(_log_lines) + "\n", encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# Baseline universe
# ─────────────────────────────────────────────────────────────────────────────

BASELINE_AGGR = ["QQQ", "IGM", "SPMO", "XLE", "XRT", "COWZ", "AVUV",
                 "VBR", "SPHQ", "XMMO", "XMHQ"]
BASELINE_INTL = ["VEA", "VWO"]
BASELINE_DIV  = ["GLD", "TLT"]
BASELINE_UNIV = BASELINE_AGGR + BASELINE_INTL + BASELINE_DIV

# ETF first live trading day (non-proxy, actual ETF inception).
# Used only to compute the all-live window start. Source: ETF issuer disclosures.
LIVE_INCEPTION: dict[str, pd.Timestamp] = {
    "QQQ":  pd.Timestamp("1999-03-10"),
    "IGM":  pd.Timestamp("2001-05-17"),
    "SPMO": pd.Timestamp("2015-10-13"),
    "XLE":  pd.Timestamp("1998-12-22"),
    "XRT":  pd.Timestamp("2006-06-23"),
    "COWZ": pd.Timestamp("2016-12-16"),
    "AVUV": pd.Timestamp("2019-09-24"),
    "VBR":  pd.Timestamp("2004-01-30"),
    "SPHQ": pd.Timestamp("2005-12-06"),
    "XMMO": pd.Timestamp("2005-07-08"),
    "XMHQ": pd.Timestamp("2006-12-15"),
    "VEA":  pd.Timestamp("2007-07-20"),
    "VWO":  pd.Timestamp("2005-03-04"),
    "GLD":  pd.Timestamp("2004-11-18"),
    "TLT":  pd.Timestamp("2002-07-30"),
    # Substitutes
    "MTUM": pd.Timestamp("2013-04-16"),
    "PRF":  pd.Timestamp("2005-12-22"),
    "SLYV": pd.Timestamp("2000-09-25"),
    "EFA":  pd.Timestamp("2001-11-01"),
    "EEM":  pd.Timestamp("2003-04-14"),
}

_NON_RISKY = set(SAFE_POOL) | {DEFAULT_CASH}


def all_live_start(universe: list) -> pd.Timestamp:
    """Latest live inception among risky assets + 12-month SMA warmup."""
    dates = [LIVE_INCEPTION[t] for t in universe if t in LIVE_INCEPTION and t not in _NON_RISKY]
    if not dates:
        return pd.Timestamp("2010-01-01")
    return max(dates) + pd.DateOffset(months=12)


# ─────────────────────────────────────────────────────────────────────────────
# Variant definitions
# ─────────────────────────────────────────────────────────────────────────────

def make_univ(aggr=None, intl=None, div=None) -> list:
    return (aggr or BASELINE_AGGR) + (intl or BASELINE_INTL) + (div or BASELINE_DIV)


_swap3 = {"SPMO": "MTUM", "COWZ": "PRF", "AVUV": "SLYV"}

VARIANTS: dict[str, list] = {
    # ── Baseline ───────────────────────────────────────────────────────────
    "FCP-15 (baseline)":     BASELINE_UNIV,

    # ── EXP A: drop short-history names ────────────────────────────────────
    "A1 drop-SPMO":          make_univ(aggr=[t for t in BASELINE_AGGR if t != "SPMO"]),
    "A2 drop-COWZ":          make_univ(aggr=[t for t in BASELINE_AGGR if t != "COWZ"]),
    "A3 drop-AVUV":          make_univ(aggr=[t for t in BASELINE_AGGR if t != "AVUV"]),
    "A4 drop-all3":          make_univ(aggr=[t for t in BASELINE_AGGR if t not in {"SPMO","COWZ","AVUV"}]),
    "A5 drop-AVUV-ctrl":     make_univ(aggr=[t for t in BASELINE_AGGR if t != "AVUV"]),  # same as A3; control label

    # ── EXP B: replace with cleaner substitutes ─────────────────────────────
    "B1 SPMO->MTUM":         make_univ(aggr=[("MTUM" if t == "SPMO" else t) for t in BASELINE_AGGR]),
    "B2 COWZ->PRF":          make_univ(aggr=[("PRF"  if t == "COWZ" else t) for t in BASELINE_AGGR]),
    "B3 AVUV->SLYV":         make_univ(aggr=[("SLYV" if t == "AVUV" else t) for t in BASELINE_AGGR]),
    "B4 all3-swaps":         make_univ(aggr=[_swap3.get(t, t) for t in BASELINE_AGGR]),

    # ── EXP C: longer-history international ───────────────────────────────
    "C1 VEA->EFA VWO->EEM":  make_univ(intl=["EFA", "EEM"]),

    # ── EXP D: combined clean (final candidate) ────────────────────────────
    "D combined-clean":      ["QQQ","IGM","MTUM","XLE","XRT","PRF","VBR","SPHQ",
                               "XMMO","XMHQ","EFA","EEM","GLD","TLT"],
}


# ─────────────────────────────────────────────────────────────────────────────
# Metric helpers (inline — no external dependency on fcp_aaa_sota_extended)
# ─────────────────────────────────────────────────────────────────────────────

def _ulcer_index(eq_s: pd.Series) -> float:
    dd = (eq_s / eq_s.cummax() - 1) * 100.0
    return float(np.sqrt((dd ** 2).mean()))


def _pain_index(eq_s: pd.Series) -> float:
    dd = (eq_s / eq_s.cummax() - 1) * 100.0
    return float(-dd.mean())


def _ann_to(weights_hist: list, window_start: pd.Timestamp, window_end: pd.Timestamp) -> float:
    """Annualized one-way turnover computed from the weights_history list."""
    total_to = 0.0
    n_months = 0
    for i, h in enumerate(weights_hist):
        af = h["apply_from"]
        if af < window_start or af > window_end:
            continue
        prev_w = weights_hist[i - 1]["weights"] if i > 0 else {}
        curr_w = h["weights"]
        keys = set(curr_w) | set(prev_w)
        to = sum(abs(curr_w.get(k, 0.0) - prev_w.get(k, 0.0)) for k in keys)
        total_to += to
        n_months += 1
    if n_months == 0:
        return float("nan")
    return total_to / n_months * 12.0  # annualise


def compute_metrics(
    label: str,
    window_name: str,
    daily: pd.Series,
    weights_hist: list,
) -> dict:
    r = daily.dropna()
    if len(r) < 120:
        return {}
    eq = (1.0 + r).cumprod()
    n_y = len(r) / 252.0
    cagr = eq.iloc[-1] ** (1.0 / n_y) - 1
    vol = r.std() * np.sqrt(252)
    sharpe = (r.mean() * 252) / vol if vol > 0 else float("nan")
    dd_s = eq / eq.cummax() - 1
    mdd = float(dd_s.min())

    # Ulcer / UPI
    ulcer = _ulcer_index(eq)
    upi   = (cagr * 100.0) / ulcer if ulcer > 0 else float("nan")
    pain  = _pain_index(eq)

    # Sortino (downside below 0)
    neg = r[r < 0]
    dn_std = neg.std() * np.sqrt(252) if len(neg) > 1 else float("nan")
    sortino = (r.mean() * 252) / dn_std if dn_std and dn_std > 0 else float("nan")

    # Calmar
    calmar = cagr / abs(mdd) if mdd < 0 else float("nan")

    # Annualized turnover
    ann_to = _ann_to(weights_hist, r.index[0], r.index[-1])

    return {
        "variant":  label,
        "window":   window_name,
        "start":    r.index[0].date().isoformat(),
        "end":      r.index[-1].date().isoformat(),
        "years":    round(n_y, 1),
        "CAGR%":    round(cagr * 100, 2),
        "Vol%":     round(vol * 100, 2),
        "Sharpe":   round(sharpe, 3),
        "MaxDD%":   round(mdd * 100, 2),
        "UPI":      round(upi, 3),
        "Pain%":    round(pain, 3),
        "Sortino":  round(sortino, 3),
        "Calmar":   round(calmar, 3),
        "AnnTO%":   round(ann_to * 100, 1),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Pick frequency + pair diff helpers
# ─────────────────────────────────────────────────────────────────────────────

def pick_frequency(weights_hist: list, universe: list) -> dict[str, float]:
    """Fraction of risk-on months each asset appeared in selected pair."""
    counts: dict[str, int] = {t: 0 for t in universe}
    total_risk_on = 0
    for h in weights_hist:
        risky = {k: v for k, v in h["weights"].items() if k not in _NON_RISKY}
        if risky:
            total_risk_on += 1
            for t in risky:
                counts[t] = counts.get(t, 0) + 1
    if total_risk_on == 0:
        return {t: 0.0 for t in universe}
    return {t: counts.get(t, 0) / total_risk_on for t in universe}


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

HYBRID_START = pd.Timestamp("1997-08-31")
LIVE_START   = pd.Timestamp("2008-09-30")
END          = pd.Timestamp.today().normalize()


def main() -> None:
    log("=" * 80)
    log("FCP CLEANER UNIVERSE EXPERIMENTS")
    log(f"Generated : {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}")
    log(f"HOLD_BUFFER={fcp.HOLD_BUFFER}  vol-target=ON  cost=10bps/side")
    log("=" * 80)

    # ── Build superset panel (fetch all assets needed across all variants) ──
    all_risky = sorted({t for univ in VARIANTS.values() for t in univ})
    log(f"\nLoading panel for superset of {len(all_risky)} risky assets + safe/canary …")

    _orig_risky  = fcp.RISKY_UNIVERSE
    _orig_buffer = fcp.HOLD_BUFFER
    fcp.RISKY_UNIVERSE = all_risky + list(set(SAFE_POOL + CANARY_ASSETS + PP_ASSETS + [DEFAULT_CASH]))
    panel = load_panel(start=HYBRID_START, end=END)
    fcp.RISKY_UNIVERSE = _orig_risky  # restore before first run

    log(f"Panel     : {panel.index[0].date()} → {panel.index[-1].date()}, {len(panel.columns)} assets")

    # ── Asset coverage check ──────────────────────────────────────────────
    log("\n── Asset availability ───────────────────────────────────────────────")
    log(f"  {'Ticker':<6}  {'In proxy':<10}  {'Panel first valid':<20}  {'Live inception'}")
    for t in all_risky:
        in_proxy = t in panel.columns
        fvi = panel[t].first_valid_index().date().isoformat() if in_proxy and panel[t].first_valid_index() else "N/A"
        live = LIVE_INCEPTION.get(t, pd.NaT)
        live_s = live.date().isoformat() if pd.notna(live) else "unknown"
        log(f"  {t:<6}  {'yes' if in_proxy else 'MISSING':<10}  {fvi:<20}  {live_s}")

    # ── Enforce HOLD_BUFFER = 2.5 throughout ─────────────────────────────
    fcp.HOLD_BUFFER = 2.5

    # ── Run all variants ──────────────────────────────────────────────────
    all_rows:       list[dict]       = []
    pick_freq_map:  dict[str, dict]  = {}   # hybrid-window pick freq per variant
    wh_map:         dict[str, list]  = {}   # hybrid weights_history per variant

    for label, universe in VARIANTS.items():
        log(f"\n{'━'*70}")
        log(f"VARIANT : {label}")
        log(f"Universe ({len(universe)}): {universe}")

        missing = [t for t in universe if t not in panel.columns or panel[t].isnull().all()]
        if missing:
            log(f"  ⚠ SKIP: assets missing from panel: {missing}")
            continue

        al_start = all_live_start(universe)
        log(f"  All-live window start: {al_start.date()}")

        windows = [
            ("Hybrid-28y", HYBRID_START),
            ("Live-18y",   LIVE_START),
            ("All-live",   al_start),
        ]

        # Patch module-level universe
        fcp.RISKY_UNIVERSE = universe

        for wname, wstart in windows:
            if al_start >= END - pd.DateOffset(years=2) and wname == "All-live":
                log(f"  {wname}: all-live start {al_start.date()} too recent, skip")
                continue
            if wstart > END - pd.DateOffset(years=1):
                log(f"  {wname}: window too short, skip")
                continue

            t0 = time.time()
            try:
                daily, wh = run_fcp_backtest(
                    panel, wstart, END,
                    apply_vol_target=True,
                    cost_bps=10,
                )
            except Exception as exc:
                log(f"  {wname}: ERROR {exc}")
                continue
            elapsed = time.time() - t0

            m = compute_metrics(label, wname, daily, wh)
            if m:
                all_rows.append(m)
                log(
                    f"  {wname:<12} Sh={m['Sharpe']:+.3f}  CAGR={m['CAGR%']:+.2f}%"
                    f"  DD={m['MaxDD%']:.2f}%  UPI={m['UPI']:.3f}"
                    f"  Sortino={m['Sortino']:.3f}  TO={m['AnnTO%']:.0f}%"
                    f"  [{elapsed:.1f}s]"
                )

            # Stash hybrid weights_history for pick-freq
            if wname == "Hybrid-28y":
                wh_map[label]       = wh
                pick_freq_map[label] = pick_frequency(wh, universe)

        # Restore
        fcp.RISKY_UNIVERSE = _orig_risky

    # Restore buffer
    fcp.HOLD_BUFFER = _orig_buffer

    # ─────────────────────────────────────────────────────────────────────
    # Results tables
    # ─────────────────────────────────────────────────────────────────────
    df = pd.DataFrame(all_rows)
    if df.empty:
        log("\nNo results — check panel coverage.")
        flush_log()
        return

    csv_path = LOG_PATH.parent / "cleaner_universe_results.csv"
    df.to_csv(csv_path, index=False)
    log(f"\nFull results CSV → {csv_path}")

    log("\n" + "=" * 80)
    log("RESULTS — sorted by Live-18y Sharpe DESC")
    log("=" * 80)

    COLS_SHOW = ["variant", "years", "CAGR%", "Vol%", "Sharpe", "MaxDD%",
                 "UPI", "Sortino", "Calmar", "Pain%", "AnnTO%"]

    for wname in ["All-live", "Live-18y", "Hybrid-28y"]:
        sub = df[df["window"] == wname].sort_values("Sharpe", ascending=False).reset_index(drop=True)
        if sub.empty:
            continue
        log(f"\n── {wname}  ({sub['start'].iloc[0]} → {sub['end'].iloc[0]}) ──")
        log(sub[COLS_SHOW].to_string(index=True, float_format=lambda x: f"{x:.3f}"))

    # ─────────────────────────────────────────────────────────────────────
    # Pick frequency (Hybrid window)
    # ─────────────────────────────────────────────────────────────────────
    log("\n" + "=" * 80)
    log("PICK FREQUENCY — % of risk-on months selected (Hybrid window)")
    log("=" * 80)

    for label in VARIANTS:
        if label not in pick_freq_map:
            continue
        pf = pick_freq_map[label]
        total_months = len(wh_map[label])
        risk_on = sum(1 for h in wh_map[label]
                      if any(k not in _NON_RISKY for k in h["weights"]))
        log(f"\n{label}  [{total_months} months, {risk_on} risk-on ({risk_on/total_months*100:.0f}%)]:")
        for t, freq in sorted(pf.items(), key=lambda x: -x[1]):
            bar = "█" * int(freq * 30)
            log(f"  {t:<6}  {freq*100:5.1f}%  {bar}")

    # ─────────────────────────────────────────────────────────────────────
    # Pair composition diff vs baseline (Hybrid window)
    # ─────────────────────────────────────────────────────────────────────
    log("\n" + "=" * 80)
    log("PAIR COMPOSITION DIFF vs FCP-15 baseline (Hybrid window, pick-freq delta)")
    log("  ▲ = more often selected in variant  ▼ = less often selected")
    log("=" * 80)

    base_label = "FCP-15 (baseline)"
    if base_label in pick_freq_map:
        base_pf = pick_freq_map[base_label]
        for label in VARIANTS:
            if label == base_label or label not in pick_freq_map:
                continue
            pf = pick_freq_map[label]
            all_tickers = sorted(set(base_pf) | set(pf))
            diffs = {t: pf.get(t, 0.0) - base_pf.get(t, 0.0) for t in all_tickers}
            meaningful = {t: d for t, d in diffs.items() if abs(d) > 0.01}
            if not meaningful:
                log(f"\n{label}: no meaningful pick-freq change vs baseline")
                continue
            log(f"\n{label}:")
            for t, d in sorted(meaningful.items(), key=lambda x: -abs(x[1])):
                sign = "▲" if d > 0 else "▼"
                log(f"  {t:<6}  {sign} {abs(d)*100:.1f}pp"
                    f"  (base={base_pf.get(t,0)*100:.1f}%"
                    f"  →  new={pf.get(t,0)*100:.1f}%)")

    # ─────────────────────────────────────────────────────────────────────
    # Live-18y Sharpe ranking summary (clean one-liner per variant)
    # ─────────────────────────────────────────────────────────────────────
    log("\n" + "=" * 80)
    log("RANKED SUMMARY — Live-18y Sharpe (primary sort)")
    log("=" * 80)

    live18 = df[df["window"] == "Live-18y"].sort_values("Sharpe", ascending=False)
    if not live18.empty:
        base_sh = live18.loc[live18["variant"] == base_label, "Sharpe"]
        base_sh = float(base_sh.iloc[0]) if not base_sh.empty else float("nan")
        log(f"  {'Rank':<4} {'Variant':<30} {'Sharpe':>7} {'Δ vs base':>9} "
            f"{'CAGR%':>7} {'MaxDD%':>7} {'UPI':>6} {'AnnTO%':>7}")
        log("  " + "-" * 78)
        for rank, (_, row) in enumerate(live18.iterrows(), 1):
            delta = row["Sharpe"] - base_sh
            sign  = "+" if delta >= 0 else ""
            log(f"  {rank:<4} {row['variant']:<30} {row['Sharpe']:>7.3f} "
                f"{sign}{delta:>8.3f}  {row['CAGR%']:>6.2f}  "
                f"{row['MaxDD%']:>6.2f}  {row['UPI']:>5.3f}  {row['AnnTO%']:>6.0f}%")

    log("\n" + "=" * 80)
    log("CAVEATS")
    log("=" * 80)
    log("""
1. SPMO/COWZ in proxy panel use SPY as proxy (1995-2015 / 1995-2016).
   This inflates hybrid-window Sharpe for FCP-15 baseline if SPY was a strong
   signal in those eras — the proxy is a reasonable broad-market stand-in but
   misrepresents factor-specific behavior.

2. AVUV in proxy panel uses DFSVX (DFA US Small Cap Value mutual fund).
   Better match than SPY but still proxy; correlation with live AVUV ~0.97.

3. MTUM / PRF / SLYV have NO proxy chains — only live yfinance data.
   Before their live start they simply are absent from candidate pool.
   Hybrid window results for B1/B2/B3/B4/D partially reflect this truncated
   pre-live period (fewer candidates available in early years).

4. EFA and EEM in proxy panel share the same proxies as VEA and VWO
   (VGTSX → VEA/EFA, VEIEX → VWO/EEM). Hybrid-window difference C1 vs
   baseline is essentially cosmetic; meaningful only on All-live window.

5. All-live window for AVUV = 2020-09 (only ~5.5y). Treat as directional
   signal only; sampling variance dominates.

6. VBR from yfinance cache (starts 2004-01-30); no proxy extension.

7. HOLD_BUFFER held at 2.5z per production setting throughout.
   No parameter re-optimisation across variants.

8. DO NOT recommend production changes based solely on this output.
   Evidence only; out-of-sample validation required before any universe change.
""")

    flush_log()
    log(f"Log → {LOG_PATH}")


if __name__ == "__main__":
    main()
