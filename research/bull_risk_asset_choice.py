#!/usr/bin/env python3
"""
BULL sleeve risk-asset choice study.

Question: Is SPY the right broad-equity expression for the BULL sleeve, vs
  A0 SPY  (PROD)
  A1 QQQ  (more beta; note NDX already supplies Nasdaq)
  A2 RSP  (S&P500 equal-weight; de-stacks mega-cap)
  A3 MTUM (momentum factor)
  A4 SPHQ (quality factor; already in CPM universe)

Evaluated primarily on the LIVE 3-sleeve 60/20/20 (CPM 60 / BULL 20 / NDX 20);
also BULL standalone and a BULL/CPM 60/40 reference.

Gate structure + safe pool held FIXED; only the held risk asset varies.
This is achieved by:
  * monkeypatching bull_spy_live.BULL_TICKER (read at call time by
    compute_bull_spy_weights / run_bull_spy_backtest), and
  * monkeypatching ndx_sleeve_live.compute_ndx_weights so the NDX gate keys on
    the *current* BULL ticker instead of the hardcoded "SPY".

NO production file is edited.

Proxy / history handling (FLAGGED in output):
  SPY/QQQ : full proxy history in panel (1995+).
  SPHQ    : panel already carries a production proxy to 1995 (live 2005-12).
  RSP     : live 2003-05-01. Clean window fully live. Stress restricted to
            2003-05-01 (no clean equal-weight proxy pre-2003).
  MTUM    : live 2013-04-18. Backstitched with PDP (Invesco DWA Momentum,
            live 2007-03-01) for the clean window. Stress restricted to
            2007-03-01 (PDP inception).

Usage:  .venv/bin/python research/bull_risk_asset_choice.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import bull_spy_live
import ndx_sleeve_live
from cpm_live import load_panel, run_cpm_backtest, perf_metrics, sig_13612U
from bull_spy_live import run_bull_spy_backtest, compute_bull_spy_weights
from ndx_sleeve_live import load_ndx_panel, run_ndx_backtest

CACHE = Path("/tmp/bull_choice_cache")
CACHE.mkdir(exist_ok=True)

CLEAN_START = pd.Timestamp("2008-05-30")
STRESS_START = pd.Timestamp("1999-03-10")
END = pd.Timestamp("2026-05-22")

CPM_W, BULL_W, NDX_W = 0.60, 0.20, 0.20

VARIANTS = {
    "A0_SPY": "SPY",
    "A1_QQQ": "QQQ",
    "A2_RSP": "RSP",
    "A3_MTUM": "MTUM",
    "A4_SPHQ": "SPHQ",
}

# Per-variant earliest usable date (proxy/inception constraint) for the stress run.
VARIANT_STRESS_FLOOR = {
    "SPY": STRESS_START,
    "QQQ": STRESS_START,
    "SPHQ": STRESS_START,        # panel proxy to 1995
    "RSP": pd.Timestamp("2003-05-01"),   # live inception; no clean EW proxy pre-2003
    "MTUM": pd.Timestamp("2007-03-01"),  # PDP proxy inception
}

SUBPERIODS = {
    "2008": (pd.Timestamp("2008-01-01"), pd.Timestamp("2008-12-31")),
    "2020": (pd.Timestamp("2020-01-01"), pd.Timestamp("2020-12-31")),
    "2022": (pd.Timestamp("2022-01-01"), pd.Timestamp("2022-12-31")),
}


# ---------- data helpers ----------

def fetch(ticker: str, start="1998-01-01") -> pd.Series:
    cp = CACHE / f"{ticker}.csv"
    if cp.exists():
        s = pd.read_csv(cp, parse_dates=[0], index_col=0).iloc[:, 0]
        s.name = ticker
        return s
    d = yf.download(ticker, start=start, end="2026-05-23", auto_adjust=True,
                    progress=False, threads=False)
    if isinstance(d.columns, pd.MultiIndex):
        d = d["Close"]
    c = d["Close"] if "Close" in d.columns else d.iloc[:, 0]
    c = c.dropna(); c.name = ticker
    c.to_csv(cp, header=True)
    return c


def backstitch(live: pd.Series, proxy: pd.Series) -> pd.Series:
    """Extend `live` backward using `proxy` daily returns, level-matched at the
    live inception date."""
    live = live.dropna(); proxy = proxy.dropna()
    if proxy.empty:
        return live
    j = live.index[0]
    anchor = proxy.reindex(proxy.index.union([j])).ffill().loc[j]
    before = proxy[proxy.index < j]
    if before.empty or pd.isna(anchor) or anchor == 0:
        return live
    scaled = before * (live.iloc[0] / anchor)
    return pd.concat([scaled, live]).sort_index()


def build_panel_with(ticker: str, base_panel: pd.DataFrame) -> pd.DataFrame:
    """Return base_panel guaranteed to contain `ticker` (inject/stitch if needed)."""
    panel = base_panel.copy()
    if ticker in panel.columns and panel[ticker].dropna().shape[0] > 100:
        # SPY/QQQ/SPHQ already present (with proxy history).
        return panel
    if ticker == "RSP":
        col = fetch("RSP")
    elif ticker == "MTUM":
        col = backstitch(fetch("MTUM"), fetch("PDP"))
    else:
        col = fetch(ticker)
    panel = panel.drop(columns=[ticker], errors="ignore").join(
        col.rename(ticker), how="outer").sort_index()
    return panel


# ---------- patched NDX gate (keys on current BULL ticker) ----------

_orig_compute_ndx = ndx_sleeve_live.compute_ndx_weights


def patched_compute_ndx_weights(cpm_panel, ndx_panel, sig_d):
    """Copy of ndx_sleeve_live.compute_ndx_weights with the gate keyed on the
    *current* bull_spy_live.BULL_TICKER rather than hardcoded 'SPY'."""
    import index_constitution as ic
    from ndx_sleeve_live import SELECT_K, _pick_safe

    bt = bull_spy_live.BULL_TICKER
    cpm_monthly = cpm_panel.loc[:sig_d].resample("ME").last()
    bull_weights, _, _ = compute_bull_spy_weights(cpm_panel, sig_d)
    bull_active = any(w > 0 for t, w in bull_weights.items() if t == bt)

    if not bull_active:
        safe = _pick_safe(cpm_monthly)
        return ({safe: 1.0}, "GATE_OFF (BULL_defensive)",
                {"selected": [], "reason": "BULL sleeve defensive", "picked_safe": safe})

    pit = ic.constituents_at("nasdaq100", sig_d.strftime("%Y-%m-%d"))
    pit_tickers = set(pit["symbol"].tolist())
    if len(pit_tickers) == 0:
        bq_weights, bq_regime, _ = compute_bull_spy_weights(cpm_panel, sig_d)
        return (bq_weights, "NDX_FALLBACK_BULL",
                {"bull_regime": bq_regime, "selected": list(bq_weights.keys()),
                 "reason": "PIT NDX data unavailable; mirroring BULL sleeve"})

    monthly = ndx_panel.loc[:sig_d].resample("ME").last()
    available = []
    for t in pit_tickers:
        if t not in ndx_panel.columns:
            continue
        if sig_d in ndx_panel.index and pd.isna(ndx_panel.loc[sig_d, t]):
            continue
        recent = ndx_panel[t].loc[sig_d - pd.Timedelta(days=30):sig_d].dropna()
        if recent.empty:
            continue
        available.append(t)

    momenta = {}
    for t in available:
        s = monthly[t].dropna()
        if len(s) < 13:
            continue
        m = sig_13612U(s)
        if pd.notna(m) and m > 0:
            momenta[t] = m

    sorted_by_mom = sorted(momenta.items(), key=lambda x: -x[1])
    n_pick = min(len(sorted_by_mom), SELECT_K)
    selected = [t for t, _ in sorted_by_mom[:n_pick]]
    per_slot = 1.0 / SELECT_K
    weights = {t: per_slot for t in selected}
    cash_share = 1.0 - n_pick * per_slot
    if cash_share > 1e-9:
        safe = _pick_safe(cpm_monthly)
        weights[safe] = weights.get(safe, 0.0) + cash_share
    regime = "NDX_ACTIVE" if n_pick == SELECT_K else f"NDX_PARTIAL_{n_pick}"
    return (weights, regime,
            {"bull_regime": "decoupled", "n_candidates": len(sorted_by_mom),
             "selected": selected, "momenta": {t: momenta[t] for t in selected}})


# ---------- metrics ----------

def metrics_block(daily: pd.Series, cash: pd.Series) -> dict:
    if daily is None or daily.empty:
        return {}
    m = perf_metrics(daily, cash.reindex(daily.index).fillna(0.0))
    return m


def bull_turnover(panel: pd.DataFrame, ticker: str, start, end) -> float:
    """One-way annualized turnover of the BULL sleeve (weight changes at monthly
    signal dates)."""
    monthly_idx = (pd.DataFrame({"x": 1}, index=panel.index)
                   .groupby(pd.Grouper(freq="ME")).tail(1).index)
    sigs = [d for d in monthly_idx if start <= d <= end]
    prev = {}
    tot = 0.0
    for sd in sigs:
        w, _, _ = compute_bull_spy_weights(panel, sd, panel[ticker])
        keys = set(w) | set(prev)
        tot += sum(abs(w.get(k, 0.0) - prev.get(k, 0.0)) for k in keys) / 2.0
        prev = w
    yrs = (sigs[-1] - sigs[0]).days / 365.25 if len(sigs) > 1 else 1.0
    return tot / yrs if yrs > 0 else float("nan")


# ---------- per-variant run ----------

def run_variant(ticker: str, base_panel: pd.DataFrame, ndx_panel: pd.DataFrame,
                run_start: pd.Timestamp, end: pd.Timestamp) -> dict:
    """Backtest CPM/BULL/NDX over [run_start, end]; return dict of daily series."""
    panel = build_panel_with(ticker, base_panel)
    bull_spy_live.BULL_TICKER = ticker
    ndx_sleeve_live.compute_ndx_weights = patched_compute_ndx_weights
    try:
        cpm, _ = run_cpm_backtest(panel, run_start, end)
        bull = run_bull_spy_backtest(panel, run_start, end)
        ndx, _ = run_ndx_backtest(panel, ndx_panel, run_start, end)
    finally:
        ndx_sleeve_live.compute_ndx_weights = _orig_compute_ndx
        bull_spy_live.BULL_TICKER = "SPY"
    common = cpm.index.intersection(bull.index).intersection(ndx.index)
    cpm = cpm.reindex(common); bull = bull.reindex(common); ndx = ndx.reindex(common).fillna(0.0)
    blend3 = CPM_W * cpm + BULL_W * bull + NDX_W * ndx
    blend6040 = 0.6 * cpm + 0.4 * bull   # BULL/CPM 60/40 reference (CPM 60 / BULL 40)
    cash = panel["SHV"].ffill().pct_change().reindex(common).fillna(0.0)
    return dict(panel=panel, cpm=cpm, bull=bull, ndx=ndx,
                blend3=blend3, blend6040=blend6040, cash=cash)


def slice_metrics(series: pd.Series, cash: pd.Series, win) -> dict:
    s = series.loc[(series.index >= win[0]) & (series.index <= win[1])]
    return metrics_block(s, cash)


def fmt_row(name, m) -> str:
    if not m:
        return f"{name:14s}   (no data)"
    return (f"{name:14s} {m.get('sharpe', float('nan')):6.3f} "
            f"{m.get('excess_sharpe', float('nan')):6.3f} "
            f"{m.get('cagr', float('nan'))*100:7.2f} "
            f"{m.get('vol', float('nan'))*100:6.2f} "
            f"{m.get('max_drawdown', float('nan'))*100:8.2f} "
            f"{m.get('calmar', float('nan')):6.2f}")


def main():
    print("Loading base panel (1995+) ...")
    base_panel = load_panel(start=pd.Timestamp("1995-01-01"), end=END)
    ndx_panel = load_ndx_panel()
    print(f"Base panel: {base_panel.index[0].date()} -> {base_panel.index[-1].date()}")

    results = {}
    for key, tk in VARIANTS.items():
        floor = VARIANT_STRESS_FLOOR[tk]
        run_start = min(STRESS_START, floor) if floor <= STRESS_START else floor
        # ensure run covers clean window and warmup
        run_start = min(run_start, CLEAN_START - pd.DateOffset(years=2))
        run_start = max(run_start, pd.Timestamp("1995-01-01"))
        # but never before the asset's data floor
        run_start = max(run_start, floor)
        print(f"\n=== {key} ({tk}) run_start={run_start.date()} ===")
        r = run_variant(tk, base_panel, ndx_panel, run_start, END)
        r["stress_start"] = max(STRESS_START, floor)
        r["turnover_clean"] = bull_turnover(r["panel"], tk, CLEAN_START, END)
        r["turnover_stress"] = bull_turnover(r["panel"], tk, r["stress_start"], END)
        results[key] = r
        print(f"  series {r['blend3'].index[0].date()} -> {r['blend3'].index[-1].date()}")

    # ---- assemble report ----
    out = []
    hdr = f"{'variant':14s} {'Shrp':>6s} {'ExShp':>6s} {'CAGR%':>7s} {'Vol%':>6s} {'MaxDD%':>8s} {'Calm':>6s}"

    def section(title, accessor, win_name, win):
        out.append(f"\n### {title}")
        out.append("```")
        out.append(hdr)
        for key in VARIANTS:
            r = results[key]
            s = accessor(r)
            m = slice_metrics(s, r["cash"], win)
            tn = r["turnover_clean"] if win_name == "clean" else r["turnover_stress"]
            line = fmt_row(key, m)
            if win_name in ("clean", "stress"):
                line += f"  turn/yr={tn:.2f}"
            out.append(line)
        out.append("```")

    out.append("# BULL risk-asset choice -- results")
    out.append(f"Generated. END={END.date()}.  Blend = 60% CPM + 20% BULL + 20% NDX.")
    out.append("Columns: Sharpe, Excess-Sharpe, CAGR%, Vol%, MaxDD%, Calmar.")

    out.append("\n## LIVE 3-sleeve 60/20/20")
    section("Clean window 2008-05-30..2026-05-22", lambda r: r["blend3"], "clean",
            (CLEAN_START, END))
    # stress uses each variant's own start; print floor note
    out.append("\n### Stress window (variant start.. 2026-05-22)")
    out.append("```")
    out.append(hdr)
    for key in VARIANTS:
        r = results[key]
        win = (r["stress_start"], END)
        m = slice_metrics(r["blend3"], r["cash"], win)
        out.append(fmt_row(key, m) + f"  [from {r['stress_start'].date()}] turn/yr={r['turnover_stress']:.2f}")
    out.append("```")
    for nm, win in SUBPERIODS.items():
        section(f"Sub-period {nm}", lambda r: r["blend3"], nm, win)

    out.append("\n## BULL standalone")
    section("Clean window", lambda r: r["bull"], "clean", (CLEAN_START, END))
    out.append("\n### Stress window (variant start..)")
    out.append("```")
    out.append(hdr)
    for key in VARIANTS:
        r = results[key]
        win = (r["stress_start"], END)
        out.append(fmt_row(key, slice_metrics(r["bull"], r["cash"], win))
                   + f"  [from {r['stress_start'].date()}]")
    out.append("```")
    for nm, win in SUBPERIODS.items():
        section(f"Sub-period {nm}", lambda r: r["bull"], nm, win)

    out.append("\n## BULL/CPM 60/40 reference (60% CPM / 40% BULL)")
    section("Clean window", lambda r: r["blend6040"], "clean", (CLEAN_START, END))

    # ---- concentration / overlap diagnostics ----
    out.append("\n## Concentration & overlap diagnostics (clean window)")
    out.append("```")
    out.append(f"{'variant':10s} {'corr(BULL,NDX)':>15s} {'corr(BULL,CPM)':>15s}")
    for key in VARIANTS:
        r = results[key]
        c = r["cash"]
        bw = r["bull"].loc[CLEAN_START:END]
        nw = r["ndx"].loc[CLEAN_START:END]
        cw = r["cpm"].loc[CLEAN_START:END]
        cc = bw.corr(nw)
        cc2 = bw.corr(cw)
        out.append(f"{key:10s} {cc:15.3f} {cc2:15.3f}")
    out.append("```")

    # CPM holdings overlap: fraction of risk-on signal months CPM holds QQQ / SPHQ
    out.append("\n### CPM holds QQQ / SPHQ (fraction of clean-window signal months)")
    base = results["A0_SPY"]["panel"]
    from cpm_live import compute_target_weights
    monthly_idx = (pd.DataFrame({"x": 1}, index=base.index)
                   .groupby(pd.Grouper(freq="ME")).tail(1).index)
    sigs = [d for d in monthly_idx if CLEAN_START <= d <= END]
    n_qqq = n_sphq = n_total = 0
    for sd in sigs:
        w, _, regime, _ = compute_target_weights(base, sd)
        n_total += 1
        if w.get("QQQ", 0) > 0:
            n_qqq += 1
        if w.get("SPHQ", 0) > 0:
            n_sphq += 1
    out.append("```")
    out.append(f"signal months: {n_total}")
    out.append(f"CPM holds QQQ : {n_qqq} ({100*n_qqq/n_total:.1f}%)")
    out.append(f"CPM holds SPHQ: {n_sphq} ({100*n_sphq/n_total:.1f}%)")
    out.append("```")

    report = "\n".join(out)
    print(report)
    Path(ROOT / "research" / "bull_risk_asset_choice_results.txt").write_text(report)
    print("\n[written research/bull_risk_asset_choice_results.txt]")


if __name__ == "__main__":
    main()
