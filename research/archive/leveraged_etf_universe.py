#!/usr/bin/env python3
"""
Research: Leveraged ETF Universe Experiment
============================================
Hypothesis: Adding leveraged ETFs to the FCP-15 universe lets the engine
naturally apply position-level leverage when momentum is strong, improving
CAGR without requiring MAX_LEVERAGE > 1.0 on the portfolio overlay.

Experiments:
  1. Single additions: each leveraged ETF added individually to FCP-15
  2. Pairs: SSO+QLD, TQQQ+UPRO, QLD+TMF, UPRO+UGL
  3. Full leverage universe: TQQQ/UPRO/SSO/QLD/TMF/UGL + XLE/XRT/XLV/VEA/VWO/GLD/TLT
  4. Canary interaction: crisis window DD with TQQQ vs FCP-15 baseline
  5. Single stocks: NVDA + AAPL + MSFT added to FCP-15

Output:
  strategy_fcp/research/leveraged_etf_universe.log

DO NOT MODIFY fcp_live.py. Evidence only.
"""
from __future__ import annotations

import sys
import warnings
from contextlib import contextmanager
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")

# ── Path setup ──────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

import strategy_fcp.fcp_live as fcp
from strategy_fcp.fcp_live import (
    load_panel,
    run_fcp_backtest,
    perf_metrics,
    SAFE_POOL,
    CANARY_ASSETS,
    DEFAULT_CASH,
    PP_ASSETS,
    COST_BPS_PER_SIDE,
)

# ── Constants ─────────────────────────────────────────────────────────────────
FCP15_UNIVERSE = [
    "QQQ", "IGM", "SPMO", "XLE", "XRT", "COWZ",
    "VBR", "SPHQ", "XMMO", "XMHQ", "XLV",
    "VEA", "VWO", "GLD", "TLT",
]

LIVE_START = pd.Timestamp("2008-09-30")   # FCP-15 baseline live-only start
END = pd.Timestamp.today().normalize()

# Leveraged ETF candidates: ticker -> (description, inception_date_str)
LEVERAGED_CANDIDATES = {
    "SSO":  ("2x SPY",   "2006-06-21"),
    "QLD":  ("2x QQQ",   "2006-06-21"),
    "DDM":  ("2x DIA",   "2006-06-21"),
    "SAA":  ("2x small", "2007-11-06"),
    "TQQQ": ("3x QQQ",   "2010-02-09"),
    "UPRO": ("3x SPY",   "2009-06-25"),
    "SPXL": ("3x SPY",   "2008-11-05"),
    "TMF":  ("3x TLT",   "2009-04-16"),
    "UBT":  ("2x TLT",   "2010-01-19"),
    "UGL":  ("2x GLD",   "2008-12-01"),
}

SINGLE_STOCKS = ["NVDA", "AAPL", "MSFT"]

LEVERAGE_PAIRS = [
    ("SSO", "QLD"),
    ("TQQQ", "UPRO"),
    ("QLD", "TMF"),
    ("UPRO", "UGL"),
]

# Experiment 3: full leverage universe (from task spec)
FULL_LEVERAGE_UNIVERSE = [
    "TQQQ", "UPRO", "SSO", "QLD", "TMF", "UGL",
    "XLE", "XRT", "XLV", "VEA", "VWO", "GLD", "TLT",
]

# Experiment 4: crisis windows
CRISIS_WINDOWS = {
    "2018_Q4":    (pd.Timestamp("2018-09-20"), pd.Timestamp("2018-12-31")),
    "2020_COVID": (pd.Timestamp("2020-02-19"), pd.Timestamp("2020-04-06")),
    "2022_bear":  (pd.Timestamp("2022-01-03"), pd.Timestamp("2022-12-30")),
}

WARMUP_MONTHS = 13   # months of history needed for 13612W signal to warm up


# ── Helpers ───────────────────────────────────────────────────────────────────

@contextmanager
def patched_universe(new_universe: list):
    """Temporarily override fcp.RISKY_UNIVERSE for experiment isolation."""
    old = fcp.RISKY_UNIVERSE
    fcp.RISKY_UNIVERSE = list(new_universe)
    try:
        yield
    finally:
        fcp.RISKY_UNIVERSE = old


def metrics(daily: pd.Series) -> dict:
    if daily.empty or len(daily) < 20:
        return {"sharpe": np.nan, "cagr": np.nan, "vol": np.nan, "max_dd": np.nan}
    m = perf_metrics(daily)
    return {
        "sharpe": m["sharpe"],
        "cagr": m["cagr"],
        "vol": m["vol"],
        "max_dd": m["max_drawdown"],
    }


def run_experiment(
    panel: pd.DataFrame,
    universe: list,
    start: pd.Timestamp,
    label: str,
) -> tuple[dict, pd.Series, list]:
    """
    Run FCP backtest with a patched universe.
    Returns: (metrics_dict, daily_returns, weights_history)
    """
    with patched_universe(universe):
        try:
            daily, wh = run_fcp_backtest(panel, start, END, apply_vol_target=True)
            m = metrics(daily)
        except Exception as e:
            print(f"  ERROR in {label}: {e}", file=sys.stderr)
            m = {"sharpe": np.nan, "cagr": np.nan, "vol": np.nan, "max_dd": np.nan}
            daily, wh = pd.Series(dtype=float), []

    m["label"] = label
    m["n_assets"] = len(universe)
    m["start"] = start.date()
    return m, daily, wh


def selection_rate(weights_history: list, ticker: str, min_wt: float = 0.01) -> float:
    """Fraction of all monthly rebalance periods where ticker weight >= min_wt."""
    if not weights_history:
        return 0.0
    n = sum(1 for h in weights_history if h["weights"].get(ticker, 0.0) >= min_wt)
    return n / len(weights_history)


def risk_on_selection_rate(weights_history: list, ticker: str, min_wt: float = 0.01) -> float:
    """Selection rate restricted to RISK_ON months only."""
    risk_on = [h for h in weights_history if h.get("regime") == "RISK_ON"]
    if not risk_on:
        return 0.0
    n = sum(1 for h in risk_on if h["weights"].get(ticker, 0.0) >= min_wt)
    return n / len(risk_on)


def window_max_dd(daily: pd.Series, ws: pd.Timestamp, we: pd.Timestamp) -> float:
    seg = daily.loc[ws:we]
    if len(seg) < 2:
        return np.nan
    eq = (1 + seg).cumprod()
    return float((eq / eq.cummax() - 1).min())


def top_picks_str(weights_history: list, n: int = 5, exclude: list = None) -> str:
    exclude = set(exclude or []) | set(SAFE_POOL) | {DEFAULT_CASH}
    agg: dict[str, float] = {}
    for h in weights_history:
        for a, w in h["weights"].items():
            if a not in exclude:
                agg[a] = agg.get(a, 0.0) + w
    top = sorted(agg, key=agg.get, reverse=True)[:n]
    return ", ".join(top)


def fmt_row(label, n, start, sh, cagr, vol, dd, notes=""):
    def f(v, pct=False, decimals=2):
        if isinstance(v, float) and np.isnan(v):
            return "  N/A"
        return f"{v*100:.{decimals}f}%" if pct else f"{v:.{decimals}f}"
    return (
        f"  {label:<44s} {str(n):>3s} {str(start):>12s}  "
        f"{f(sh):>7s}  {f(cagr, pct=True):>8s}  {f(vol, pct=True):>7s}  {f(dd, pct=True):>8s}  {notes}"
    )


def section(title: str):
    print()
    print("=" * 100)
    print(title)
    print("=" * 100)


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    section("LEVERAGED ETF UNIVERSE EXPERIMENT")
    print(f"FCP-15 live-only baseline  start={LIVE_START.date()}  end={END.date()}")
    print(f"Production params: TOP_K={fcp.TOP_K_CANDIDATES}, HOLD_BUFFER={fcp.HOLD_BUFFER}, "
          f"VOL_TARGET={fcp.TARGET_VOL:.0%}, MAX_LEV={fcp.MAX_LEVERAGE}, cost={COST_BPS_PER_SIDE}bps/side")
    print()

    # ── Pre-load panel with ALL tickers ──────────────────────────────────────
    all_extra = (
        list(LEVERAGED_CANDIDATES.keys())
        + SINGLE_STOCKS
        + [t for t in FULL_LEVERAGE_UNIVERSE if t not in FCP15_UNIVERSE]
    )
    print(f"Fetching all tickers (leveraged ETFs + single stocks) via yfinance...")
    all_needed = list(set(FCP15_UNIVERSE + all_extra))
    with patched_universe(all_needed):
        panel = load_panel(start=LIVE_START - pd.DateOffset(years=2), end=END)
    print(f"Panel: {panel.index[0].date()} -> {panel.index[-1].date()}, {len(panel.columns)} columns")

    # ── Availability check ────────────────────────────────────────────────────
    print("\nTicker availability:")
    print(f"  {'Ticker':6s}  {'Description':12s}  {'Inception':10s}  {'First data':10s}  {'In panel':8s}")
    print(f"  {'-'*65}")
    for tk, (desc, inc) in LEVERAGED_CANDIDATES.items():
        in_panel = tk in panel.columns
        first = panel[tk].dropna().index[0].date() if in_panel else "MISSING"
        print(f"  {tk:6s}  {desc:12s}  {inc:10s}  {str(first):10s}  {'YES' if in_panel else 'NO':8s}")
    for tk in SINGLE_STOCKS:
        in_panel = tk in panel.columns
        first = panel[tk].dropna().index[0].date() if in_panel else "MISSING"
        print(f"  {tk:6s}  {'stock':12s}  {'n/a':10s}  {str(first):10s}  {'YES' if in_panel else 'NO':8s}")

    all_results: list[dict] = []

    # ── BASELINE: FCP-15 ─────────────────────────────────────────────────────
    section("BASELINE: FCP-15 (live-only, 2008-09-30)")
    base_m, base_daily, base_wh = run_experiment(
        panel, FCP15_UNIVERSE, LIVE_START, "FCP-15 baseline"
    )
    base_m["notes"] = top_picks_str(base_wh)
    all_results.append(base_m)
    print(fmt_row(
        base_m["label"], base_m["n_assets"], base_m["start"],
        base_m["sharpe"], base_m["cagr"], base_m["vol"], base_m["max_dd"],
        base_m["notes"],
    ))

    # ── EXPERIMENT 1: Single Additions ───────────────────────────────────────
    section("EXPERIMENT 1: Single Leveraged ETF Additions (FCP-15 + 1)")
    print(f"  {'Label':<44s} {'N':>3s} {'Start':>12s}  {'Sharpe':>7s}  {'CAGR':>8s}  {'Vol':>7s}  {'MaxDD':>8s}  Notes")
    print(f"  {'-'*110}")

    single_results: list[dict] = []

    for tk, (desc, inception) in LEVERAGED_CANDIDATES.items():
        if tk not in panel.columns:
            print(f"  SKIP {tk}: not in panel")
            continue

        inc_ts = pd.Timestamp(inception)
        start_date = max(LIVE_START, inc_ts + pd.DateOffset(months=WARMUP_MONTHS))

        universe = FCP15_UNIVERSE + [tk]
        label = f"FCP-15 + {tk} ({desc})"
        m, daily, wh = run_experiment(panel, universe, start_date, label)

        sel_all  = selection_rate(wh, tk)
        sel_risk = risk_on_selection_rate(wh, tk)
        n_risk_on = sum(1 for h in wh if h.get("regime") == "RISK_ON")
        pct_risk_on = n_risk_on / len(wh) if wh else 0.0

        notes = (f"sel={sel_all:.0%} ({sel_risk:.0%} of risk-on) | "
                 f"risk_on={pct_risk_on:.0%} | top: {top_picks_str(wh, 3, exclude=[tk])}")
        m["notes"] = notes
        m["sel_all"] = sel_all
        m["sel_risk"] = sel_risk
        single_results.append(m)
        all_results.append(m)

        print(fmt_row(label, len(universe), start_date.date(),
                      m["sharpe"], m["cagr"], m["vol"], m["max_dd"], notes))

    valid_singles = [r for r in single_results if not np.isnan(r.get("sharpe", np.nan))]
    if valid_singles:
        best_sh   = max(valid_singles, key=lambda r: r["sharpe"])
        best_cagr = max(valid_singles, key=lambda r: r["cagr"])
        print(f"\n  >> Best Sharpe: {best_sh['label']}  Sh={best_sh['sharpe']:.3f}")
        print(f"  >> Best CAGR:   {best_cagr['label']}  CAGR={best_cagr['cagr']*100:.2f}%")
        picked = sorted([r for r in valid_singles if r.get("sel_all", 0) >= 0.05],
                        key=lambda r: -r["sel_all"])
        ignored = [r for r in valid_singles if r.get("sel_all", 0) < 0.05]
        print(f"\n  Actually selected (sel>=5%): "
              + ", ".join(f"{r['label'].split('+')[1].split()[0]}({r['sel_all']:.0%})" for r in picked))
        print(f"  Essentially ignored (<5%):   "
              + ", ".join(r["label"].split("+")[1].split()[0] for r in ignored))

    # ── EXPERIMENT 2: Leverage Pairs ─────────────────────────────────────────
    section("EXPERIMENT 2: Leverage Pairs (FCP-15 + 2 leveraged)")
    print(f"  {'Label':<44s} {'N':>3s} {'Start':>12s}  {'Sharpe':>7s}  {'CAGR':>8s}  {'Vol':>7s}  {'MaxDD':>8s}  Notes")
    print(f"  {'-'*110}")

    for a, b in LEVERAGE_PAIRS:
        if a not in panel.columns or b not in panel.columns:
            print(f"  SKIP {a}+{b}: missing data")
            continue

        inc_a = pd.Timestamp(LEVERAGED_CANDIDATES[a][1]) if a in LEVERAGED_CANDIDATES else LIVE_START
        inc_b = pd.Timestamp(LEVERAGED_CANDIDATES[b][1]) if b in LEVERAGED_CANDIDATES else LIVE_START
        start_date = max(LIVE_START,
                         max(inc_a, inc_b) + pd.DateOffset(months=WARMUP_MONTHS))

        universe = FCP15_UNIVERSE + [a, b]
        label = f"FCP-15 + {a}+{b}"
        m, daily, wh = run_experiment(panel, universe, start_date, label)

        sel_a = selection_rate(wh, a)
        sel_b = selection_rate(wh, b)
        notes = f"{a}={sel_a:.0%}, {b}={sel_b:.0%} | top: {top_picks_str(wh, 3, exclude=[a, b])}"
        m["notes"] = notes
        all_results.append(m)

        print(fmt_row(label, len(universe), start_date.date(),
                      m["sharpe"], m["cagr"], m["vol"], m["max_dd"], notes))

    # ── EXPERIMENT 3: Full Leverage Universe ──────────────────────────────────
    section("EXPERIMENT 3: Full Leverage Universe (TQQQ/UPRO/SSO/QLD/TMF/UGL + sector/intl)")
    latest_inc = max(
        pd.Timestamp(LEVERAGED_CANDIDATES[t][1])
        for t in FULL_LEVERAGE_UNIVERSE
        if t in LEVERAGED_CANDIDATES
    )
    full_lev_start = max(LIVE_START, latest_inc + pd.DateOffset(months=WARMUP_MONTHS))

    print(f"  Universe ({len(FULL_LEVERAGE_UNIVERSE)}): {FULL_LEVERAGE_UNIVERSE}")
    print(f"  Start: {full_lev_start.date()}")

    m_fl, fl_daily, fl_wh = run_experiment(
        panel, FULL_LEVERAGE_UNIVERSE, full_lev_start, "Full Leverage Universe"
    )

    fl_sel = {tk: selection_rate(fl_wh, tk) for tk in FULL_LEVERAGE_UNIVERSE}
    fl_sel_risk = {tk: risk_on_selection_rate(fl_wh, tk) for tk in FULL_LEVERAGE_UNIVERSE}
    m_fl["notes"] = "sel: " + ", ".join(
        f"{tk}={fl_sel[tk]:.0%}"
        for tk in sorted(fl_sel, key=fl_sel.get, reverse=True)
        if fl_sel[tk] >= 0.03
    )
    all_results.append(m_fl)

    print(fmt_row(
        m_fl["label"], m_fl["n_assets"], m_fl["start"],
        m_fl["sharpe"], m_fl["cagr"], m_fl["vol"], m_fl["max_dd"],
        m_fl["notes"],
    ))

    print("\n  Per-asset selection rates (full leverage universe):")
    print(f"  {'Ticker':8s}  {'All months':12s}  {'Risk-on months':16s}")
    for tk in sorted(FULL_LEVERAGE_UNIVERSE, key=lambda t: -fl_sel.get(t, 0)):
        if fl_sel.get(tk, 0) > 0.01 or fl_sel_risk.get(tk, 0) > 0.01:
            print(f"  {tk:8s}  {fl_sel[tk]:12.1%}  {fl_sel_risk[tk]:16.1%}")

    # ── EXPERIMENT 4: Canary Interaction ──────────────────────────────────────
    section("EXPERIMENT 4: Canary/Hold-Buffer Interaction -- Crisis Window Drawdowns")
    print("  TQQQ added to FCP-15. Does canary protect?")
    print()

    tqqq_inc = pd.Timestamp(LEVERAGED_CANDIDATES["TQQQ"][1])
    tqqq_start = max(LIVE_START, tqqq_inc + pd.DateOffset(months=WARMUP_MONTHS))

    _, base_crisis_daily, base_crisis_wh = run_experiment(
        panel, FCP15_UNIVERSE, tqqq_start, "_crisis_base"
    )
    tqqq_univ = FCP15_UNIVERSE + ["TQQQ"]
    _, tqqq_crisis_daily, tqqq_crisis_wh = run_experiment(
        panel, tqqq_univ, tqqq_start, "_crisis_tqqq"
    )

    n_total = len(tqqq_crisis_wh)
    n_defensive = sum(1 for h in tqqq_crisis_wh if h.get("regime") == "DEFENSIVE")
    print(f"  TQQQ universe: {n_total} months | "
          f"DEFENSIVE={n_defensive} ({n_defensive/n_total:.0%}) | "
          f"RISK_ON={n_total-n_defensive} ({(n_total-n_defensive)/n_total:.0%})")
    tqqq_overall_sel = selection_rate(tqqq_crisis_wh, "TQQQ")
    tqqq_riskonly_sel = risk_on_selection_rate(tqqq_crisis_wh, "TQQQ")
    print(f"  TQQQ selection: {tqqq_overall_sel:.1%} all months | {tqqq_riskonly_sel:.1%} risk-on months")
    print()

    print(f"  {'Window':<20s}  {'FCP-15 DD':>10s}  {'FCP-15+TQQQ DD':>15s}  {'Delta':>8s}  "
          f"{'TQQQ pre-crisis sel (12m)':>26s}")
    print(f"  {'-'*95}")

    for wname, (ws, we) in CRISIS_WINDOWS.items():
        dd_base = window_max_dd(base_crisis_daily, ws, we)
        dd_tqqq = window_max_dd(tqqq_crisis_daily, ws, we)
        delta = dd_tqqq - dd_base

        pre_ws = ws - pd.DateOffset(months=12)
        pre_held = [h for h in tqqq_crisis_wh if pre_ws <= h["sig_d"] < ws]
        pre_sel = (sum(1 for h in pre_held if h["weights"].get("TQQQ", 0) >= 0.01)
                   / len(pre_held) if pre_held else float("nan"))

        def fdd(v):
            return f"{v*100:.2f}%" if not (isinstance(v, float) and np.isnan(v)) else "N/A"
        def fdel(v):
            if isinstance(v, float) and np.isnan(v):
                return "N/A"
            return f"{v*100:+.2f}%"

        print(f"  {wname:<20s}  {fdd(dd_base):>10s}  {fdd(dd_tqqq):>15s}  {fdel(delta):>8s}  "
              f"{pre_sel:.0%} ({len(pre_held)} months)")

    print()
    for label_s, daily_s in [
        (f"FCP-15 ({tqqq_start.date()})", base_crisis_daily),
        (f"FCP-15+TQQQ ({tqqq_start.date()})", tqqq_crisis_daily),
    ]:
        m_c = metrics(daily_s)
        print(f"  {label_s:<45s}: Sh={m_c['sharpe']:.3f} | "
              f"CAGR={m_c['cagr']*100:.2f}% | Vol={m_c['vol']*100:.2f}% | DD={m_c['max_dd']*100:.2f}%")

    print("\n  Months TQQQ was selected (with partner):")
    any_tqqq = False
    for h in tqqq_crisis_wh:
        if h["weights"].get("TQQQ", 0) >= 0.01:
            any_tqqq = True
            partner = [a for a in h["weights"] if a != "TQQQ" and h["weights"][a] >= 0.01]
            print(f"    {h['sig_d'].date()}  TQQQ={h['weights']['TQQQ']:.0%}  "
                  f"partner={partner}  regime={h.get('regime','?')}")
    if not any_tqqq:
        print("    (TQQQ never selected in this window)")

    # ── EXPERIMENT 5: Single Stocks ───────────────────────────────────────────
    section("EXPERIMENT 5: Single Stocks Added to FCP-15 (NVDA, AAPL, MSFT)")

    stocks_universe = FCP15_UNIVERSE + SINGLE_STOCKS
    m_stocks, stocks_daily, stocks_wh = run_experiment(
        panel, stocks_universe, LIVE_START, "FCP-15 + NVDA+AAPL+MSFT"
    )

    stocks_sel = {tk: selection_rate(stocks_wh, tk) for tk in SINGLE_STOCKS}
    stocks_risk_sel = {tk: risk_on_selection_rate(stocks_wh, tk) for tk in SINGLE_STOCKS}

    print(f"\n  {'Ticker':8s}  {'All months':12s}  {'Risk-on months':16s}")
    for tk in SINGLE_STOCKS:
        print(f"  {tk:8s}  {stocks_sel[tk]:12.1%}  {stocks_risk_sel[tk]:16.1%}")

    print("\n  Months single stocks were selected:")
    any_picked = False
    for h in stocks_wh:
        picked = [tk for tk in SINGLE_STOCKS if h["weights"].get(tk, 0) >= 0.01]
        if picked:
            any_picked = True
            print(f"    {h['sig_d'].date()}  "
                  + "  ".join(f"{tk}={h['weights'][tk]:.0%}" for tk in picked)
                  + f"  regime={h.get('regime','?')}")
    if not any_picked:
        print("    (none selected)")

    m_stocks["notes"] = (
        "RISK: single-name concentration | "
        + ", ".join(f"{tk}={stocks_sel[tk]:.0%}" for tk in SINGLE_STOCKS)
    )
    all_results.append(m_stocks)
    print()
    print(fmt_row(
        m_stocks["label"], m_stocks["n_assets"], m_stocks["start"],
        m_stocks["sharpe"], m_stocks["cagr"], m_stocks["vol"], m_stocks["max_dd"],
        m_stocks["notes"],
    ))

    # ── FINAL SUMMARY TABLE ───────────────────────────────────────────────────
    section("FINAL SUMMARY TABLE")
    print(f"  {'Variant':<44s} {'N':>3s} {'Start':>12s}  {'Sharpe':>7s}  {'CAGR':>8s}  "
          f"{'Vol':>7s}  {'MaxDD':>8s}  Notes / Top Picks")
    print(f"  {'-'*130}")

    for r in all_results:
        if r["label"].startswith("_"):
            continue
        print(fmt_row(
            r["label"], r["n_assets"], r["start"],
            r["sharpe"], r["cagr"], r["vol"], r["max_dd"],
            r.get("notes", ""),
        ))

    valid = [r for r in all_results
             if not r["label"].startswith("_") and not np.isnan(r.get("sharpe", np.nan))]
    if valid:
        best_sh   = max(valid, key=lambda r: r["sharpe"])
        best_cagr = max(valid, key=lambda r: r["cagr"])
        worst_dd  = min(valid, key=lambda r: r["max_dd"])
        worst_sh  = min(valid, key=lambda r: r["sharpe"])
        print()
        print(f"  >> Best Sharpe:  {best_sh['label']}  Sh={best_sh['sharpe']:.3f}")
        print(f"  >> Best CAGR:    {best_cagr['label']}  CAGR={best_cagr['cagr']*100:.2f}%")
        print(f"  >> Worst MaxDD:  {worst_dd['label']}  DD={worst_dd['max_dd']*100:.2f}%")
        print(f"  >> Worst Sharpe: {worst_sh['label']}  Sh={worst_sh['sharpe']:.3f}")

    print("\nDone.")


if __name__ == "__main__":
    main()
