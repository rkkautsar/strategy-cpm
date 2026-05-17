#!/usr/bin/env python3
"""
peer_strategy_faithful_reproduction.py

Faithful reproduction of 4 peer TAA strategies for apples-to-apples comparison vs FCP.

Strategies implemented with their OWN engines:
  1. Faber GTAA5 (2007/2009) — SMA10 equal-weight, any asset above 10mo SMA
  2. Antonacci GEM (2014)    — Dual momentum: absolute vs T-bill, then SPY/EFA relative
  3. Keller VAA-G4 (2017)   — 13612W breadth momentum, top-1 risky with safe blend
  4. Keller HAA-Balanced (2023) — TIP canary, top-4 offensive by 13612W

Each run in 3 configurations:
  A. Peer engine + peer universe          (faithful paper reproduction)
  B. Peer engine + FCP-15 universe        (portability of peer engine)
  C. FCP engine + peer universe           (re-run same window, for fair compare)
  D. FCP engine + FCP-15 universe         (production baseline)

Cost: 10bps/side (uniform). Vol-target: OFF for peer engines (faithful), ON for FCP.
Window: 2008-09-30 to today where data allows; else actual first common date.

Deliverables:
  strategy_fcp/research/peer_strategy_faithful_reproduction.log
  strategy_fcp/research/peer_strategy_faithful_reproduction.csv
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

# ── logging ───────────────────────────────────────────────────────────────────
LOG_PATH = Path(__file__).resolve().parent / "peer_strategy_faithful_reproduction.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_PATH, mode="w"),
    ],
)
log = logging.getLogger(__name__)

# ── paths ─────────────────────────────────────────────────────────────────────
SCRIPTS_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SCRIPTS_ROOT))

from strategy_fcp.fcp_live import (
    RISKY_UNIVERSE, SAFE_POOL, CANARY_ASSETS, DEFAULT_CASH,
    TOP_K_CANDIDATES, HOLD_BUFFER, CORR_LOOKBACK_DAYS,
    TARGET_VOL, VOL_LOOKBACK_DAYS, MAX_LEVERAGE, COST_BPS_PER_SIDE,
    load_panel, perf_metrics,
    faber_sma_xs, sig_13612W, zscore, best_safe, min_vol_pair,
)
from strategy_fcp.research.universe_placebo_and_engine_portability import (
    compute_weights_custom, run_backtest_custom,
)

# ── constants ─────────────────────────────────────────────────────────────────
GLOBAL_START = pd.Timestamp("2008-09-30")  # FCP live-only era anchor
GLOBAL_END   = pd.Timestamp.today().normalize()
CACHE_DIR    = "/tmp/fcp_cache"
COST_BPS     = 10.0  # one-way, uniform across all strategies

# FCP-15 production universe
FCP15 = [
    "QQQ", "IGM", "SPMO", "XLE", "XRT", "COWZ",
    "VBR", "SPHQ", "XMMO", "XMHQ", "XLV",
    "VEA", "VWO", "GLD", "TLT",
]
FCP_SAFE   = ["BIL", "SHV", "SHY", "IEF"]
FCP_CANARY = ["SPY", "TIP"]

# Faber GTAA5
FABER_UNIV = ["SPY", "EFA", "IEF", "VNQ", "DBC"]
FABER_CASH = "SHV"

# Antonacci GEM
GEM_RISKY = ["SPY", "EFA"]
GEM_BOND  = "AGG"
GEM_TBILL = "SHV"   # ASSUMPTION: SHV as T-bill proxy (holds 0-3mo T-bills)

# Keller VAA-G4
VAA_RISKY = ["SPY", "VEA", "EEM", "AGG"]
VAA_SAFE  = ["LQD", "IEF", "SHY"]  # as per paper

# Keller HAA-Balanced (2023)
# ASSUMPTION: MTUM launched April 2013 → HAA peer-universe start delayed accordingly
HAA_CANARY    = "TIP"
HAA_OFFENSIVE = ["VTV", "IWM", "OEF", "MTUM", "EFV", "DBC", "TLT", "IEF"]
HAA_SAFE      = ["BIL", "IEF", "TLT"]
HAA_TOP_K     = 4


# ══════════════════════════════════════════════════════════════════════════════
# Peer Engine implementations
# ══════════════════════════════════════════════════════════════════════════════

def faber_gtaa5_weights(monthly: pd.DataFrame, sig_d: pd.Timestamp,
                         universe: list, cash: str = "SHV") -> dict:
    """
    Faber GTAA5 engine.
    Rule: equal-weight any asset where price > 10-month SMA; else cash.
    Faithful to Faber (2007, 2009). No vol targeting, no hold buffer.
    DEVIATION: T+1 execution (FCP mechanics); Faber used month-end.
    DEVIATION: SHV as cash (Faber used 90-day T-bill return).
    """
    sub = monthly.loc[:sig_d]
    avail = [t for t in universe if t in sub.columns
             and sub[t].first_valid_index() is not None]
    if len(sub) < 10 or not avail:
        return {cash: 1.0}
    sma10 = sub[avail].rolling(10).mean().iloc[-1]
    last  = sub[avail].iloc[-1]
    above = [t for t in avail if pd.notna(last[t]) and pd.notna(sma10[t])
             and last[t] > sma10[t]]
    if not above:
        return {cash: 1.0}
    w = 1.0 / len(above)
    return {t: w for t in above}


def gem_weights(monthly: pd.DataFrame, sig_d: pd.Timestamp,
                risky_universe=None,
                spy: str = "SPY", efa: str = "EFA",
                bond: str = "AGG", tbill: str = "SHV") -> dict:
    """
    Antonacci GEM engine.
    Original (3-asset):
      1. Absolute filter: SPY 12mo > T-bill 12mo → risk-on
      2. Relative: SPY 12mo >= EFA 12mo → SPY, else EFA
      3. Risk-off → AGG
    Extended (N-asset / FCP-15):
      1. Same absolute filter
      2. If risk-on: top-1 from risky_universe by 12mo return
      3. If risk-off: bond (or tbill if bond missing)
    ASSUMPTION: T-bill proxy = SHV. 12mo = monthly price t / price t-12 - 1.
    """
    sub = monthly.loc[:sig_d]
    if len(sub) < 13:
        return {bond: 1.0}

    def mom12(ticker):
        if ticker not in sub.columns:
            return np.nan
        now = sub[ticker].iloc[-1]
        ago = sub[ticker].iloc[-13]
        if pd.isna(now) or pd.isna(ago) or ago == 0:
            return np.nan
        return now / ago - 1

    spy_ret   = mom12(spy)
    tbill_ret = mom12(tbill)
    if pd.isna(spy_ret) or pd.isna(tbill_ret):
        return {bond: 1.0}

    # Absolute momentum filter
    if spy_ret <= tbill_ret:
        b = bond if (bond in sub.columns and pd.notna(sub[bond].iloc[-1])) else tbill
        return {b: 1.0}

    # Risk-on
    if risky_universe is None:
        efa_ret = mom12(efa)
        if pd.isna(efa_ret):
            return {spy: 1.0}
        return {spy: 1.0} if spy_ret >= efa_ret else {efa: 1.0}
    else:
        scores = {t: mom12(t) for t in risky_universe}
        scores = {t: v for t, v in scores.items() if pd.notna(v)}
        if not scores:
            return {spy: 1.0}
        best = max(scores, key=scores.get)
        return {best: 1.0}


def vaa_g4_weights(monthly: pd.DataFrame, sig_d: pd.Timestamp,
                   risky: list = None, safe: list = None) -> dict:
    """
    Keller VAA-G4 engine (Keller & Butler 2017).
    Signal: 13612W = (12*r1 + 4*r3 + 2*r6 + r12) / 19 on all assets.
    Breadth = count of risky with positive 13612W.
    breadth==n: 100% top-risky. breadth==0: 100% best-safe.
    1<=breadth<n: risky_frac=breadth/n top-risky, (1-risky_frac) best-safe.
    Extended for FCP-15: same rules, denominator = len(risky).
    ASSUMPTION: safe pool = LQD, IEF, SHY (as per paper).
    """
    if risky is None: risky = VAA_RISKY
    if safe  is None: safe  = VAA_SAFE
    sub = monthly.loc[:sig_d]
    if len(sub) < 13:
        return {safe[0]: 1.0}

    def s13(t):
        col = sub[t] if t in sub.columns else None
        if col is None: return np.nan
        if isinstance(col, pd.DataFrame): col = col.iloc[:, 0]
        return sig_13612W(col)

    risky_sc = {t: v for t in risky for v in [s13(t)] if pd.notna(v)}
    safe_sc  = {t: v for t in safe  for v in [s13(t)] if pd.notna(v)}
    best_safe_t   = max(safe_sc,  key=safe_sc.get)  if safe_sc  else (safe[0] if safe else "SHY")
    if not risky_sc:
        return {best_safe_t: 1.0}
    best_risky_t  = max(risky_sc, key=risky_sc.get)
    n       = len(risky)
    breadth = sum(1 for v in risky_sc.values() if v > 0)
    if breadth == n:
        return {best_risky_t: 1.0}
    elif breadth == 0:
        return {best_safe_t: 1.0}
    else:
        rf = breadth / n
        sf = 1.0 - rf
        return {best_risky_t: rf, best_safe_t: sf}


def haa_balanced_weights(monthly: pd.DataFrame, sig_d: pd.Timestamp,
                          offensive: list = None, safe: list = None,
                          canary: str = "TIP", top_k: int = 4) -> dict:
    """
    Keller HAA-Balanced engine (Keller & Keuning 2023).
    Canary: TIP. 13612W(TIP)>0 → risk-on; else → best-safe by 13612W.
    Risk-on: equal-weight top-4 offensive by 13612W.
    ASSUMPTION: safe pool = BIL, IEF, TLT. T+1 execution.
    ASSUMPTION: MTUM live April 2013 → peer-universe start delayed.
    """
    if offensive is None: offensive = HAA_OFFENSIVE
    if safe      is None: safe      = HAA_SAFE
    sub = monthly.loc[:sig_d]
    if len(sub) < 13:
        return {safe[0]: 1.0}

    def s13(t):
        col = sub[t] if t in sub.columns else None
        if col is None: return np.nan
        if isinstance(col, pd.DataFrame): col = col.iloc[:, 0]
        return sig_13612W(col)

    canary_score = s13(canary)
    risk_on = pd.notna(canary_score) and canary_score > 0

    safe_sc = {t: v for t in safe for v in [s13(t)] if pd.notna(v)}
    best_safe_t = max(safe_sc, key=safe_sc.get) if safe_sc else (safe[0] if safe else "BIL")

    if not risk_on:
        return {best_safe_t: 1.0}

    off_sc = {t: v for t in offensive for v in [s13(t)] if pd.notna(v)}
    if not off_sc:
        return {best_safe_t: 1.0}
    ranked   = sorted(off_sc.items(), key=lambda x: -x[1])
    selected = [t for t, _ in ranked[:top_k]]
    if not selected:
        return {best_safe_t: 1.0}
    w = 1.0 / len(selected)
    return {t: w for t in selected}


# ══════════════════════════════════════════════════════════════════════════════
# Generic monthly backtest runner (peer engines)
# ══════════════════════════════════════════════════════════════════════════════

def run_peer_backtest(
    panel: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
    signal_fn,
    signal_kwargs: dict,
    all_assets: list,
    cost_bps: float = COST_BPS,
    apply_vol_target: bool = False,
    vol_target: float = TARGET_VOL,
    vol_lookback: int = VOL_LOOKBACK_DAYS,
    max_leverage: float = MAX_LEVERAGE,
) -> pd.Series:
    """
    Generic monthly-rebalance backtest for peer engines.
    T+1 MOC execution, 10bps/side cost on turnover.
    Vol-target overlay optional (default OFF for peer engines).
    """
    avail = list(dict.fromkeys(a for a in all_assets if a in panel.columns))
    close = panel[avail].ffill()

    monthly_ends = close.resample("ME").last().index
    signal_dates = [d for d in monthly_ends if start <= d <= end]

    weights_history = []
    prev_w = {}

    for i, sig_d in enumerate(signal_dates):
        monthly = close.loc[:sig_d].resample("ME").last()
        w = signal_fn(monthly, sig_d, **signal_kwargs)
        total = sum(w.values())
        if total > 0:
            w = {k: v / total for k, v in w.items()}
        else:
            w = {}

        future = close.index[close.index > sig_d]
        if len(future) < 2:
            continue
        apply_from = future[1]  # T+1

        nxt = signal_dates[i + 1] if i + 1 < len(signal_dates) else end
        nxt_future = close.index[close.index > nxt]
        end_apply = nxt_future[1] if len(nxt_future) >= 2 else end

        weights_history.append({
            "sig_d": sig_d, "apply_from": apply_from, "end_apply": end_apply,
            "weights": w, "prev_w": prev_w.copy(),
        })
        prev_w = w.copy()

    if not weights_history:
        return pd.Series(dtype=float)

    all_held = sorted({a for h in weights_history for a in h["weights"]})
    all_held = [a for a in all_held if a in close.columns]
    df_w = pd.DataFrame(0.0, index=close.index, columns=all_held)
    for h in weights_history:
        mask = (close.index >= h["apply_from"]) & (close.index < h["end_apply"])
        for a, ww in h["weights"].items():
            if a in df_w.columns:
                df_w.loc[mask, a] = ww

    daily_ret = close.pct_change()
    common = [a for a in all_held if a in daily_ret.columns]
    raw_returns = (df_w[common] * daily_ret[common]).sum(axis=1, min_count=1).fillna(0.0)

    for h in weights_history:
        curr = h["weights"]; prev = h["prev_w"]
        keys = set(curr) | set(prev)
        turnover = sum(abs(curr.get(k, 0.0) - prev.get(k, 0.0)) for k in keys)
        cost = turnover * cost_bps / 10_000.0
        af = h["apply_from"]
        if af in raw_returns.index:
            raw_returns.loc[af] -= cost

    if apply_vol_target:
        realized = raw_returns.rolling(vol_lookback).std() * np.sqrt(252)
        scale = (vol_target / realized).clip(upper=max_leverage).shift(1).fillna(1.0)
        raw_returns = raw_returns * scale

    return raw_returns.loc[(raw_returns.index >= start) & (raw_returns.index <= end)]


# ══════════════════════════════════════════════════════════════════════════════
# Extended metrics
# ══════════════════════════════════════════════════════════════════════════════

def extended_metrics(daily: pd.Series, label: str = "") -> dict:
    daily = daily.dropna()
    if len(daily) < 30:
        return {"label": label, "sharpe": np.nan, "cagr": np.nan, "vol": np.nan,
                "max_dd": np.nan, "sortino": np.nan, "calmar": np.nan, "upi": np.nan,
                "years": 0.0, "actual_start": "N/A"}
    eq   = (1.0 + daily).cumprod()
    days = (eq.index[-1] - eq.index[0]).days
    yrs  = days / 365.25
    cagr   = (eq.iloc[-1] / eq.iloc[0]) ** (1 / yrs) - 1 if yrs > 0 else np.nan
    vol    = daily.std(ddof=0) * np.sqrt(252)
    mu_ann = daily.mean() * 252
    sharpe = mu_ann / vol if vol > 0 else np.nan
    roll_max = eq.cummax()
    dd       = (eq / roll_max - 1)
    max_dd   = dd.min()
    down     = daily[daily < 0]
    down_vol = down.std(ddof=0) * np.sqrt(252) if len(down) > 1 else np.nan
    sortino  = mu_ann / down_vol if down_vol and down_vol > 0 else np.nan
    calmar   = cagr / abs(max_dd) if max_dd != 0 and pd.notna(max_dd) else np.nan
    ulcer    = np.sqrt((dd ** 2).mean())
    upi      = mu_ann / ulcer if ulcer > 0 else np.nan
    return {"label": label, "sharpe": sharpe, "cagr": cagr, "vol": vol,
            "max_dd": max_dd, "sortino": sortino, "calmar": calmar, "upi": upi,
            "years": yrs, "actual_start": daily.index[0].strftime("%Y-%m-%d")}


# ══════════════════════════════════════════════════════════════════════════════
# Data loading
# ══════════════════════════════════════════════════════════════════════════════

def load_full_panel() -> pd.DataFrame:
    log.info("Loading base FCP panel ...")
    panel = load_panel(cache_dir=CACHE_DIR)
    log.info(f"  FCP base: {panel.index[0].date()} to {panel.index[-1].date()}, {len(panel.columns)} cols")

    peer_tickers = sorted(set(
        FABER_UNIV + [FABER_CASH] +
        GEM_RISKY + [GEM_BOND, GEM_TBILL] +
        VAA_RISKY + VAA_SAFE +
        HAA_OFFENSIVE + HAA_SAFE + [HAA_CANARY] +
        ["EEM", "EFA", "VNQ", "VTV", "OEF", "LQD"]
    ) - set(panel.columns))

    log.info(f"Fetching {len(peer_tickers)} peer tickers: {peer_tickers}")
    os.makedirs(CACHE_DIR, exist_ok=True)
    fetched = {}
    for t in peer_tickers:
        cp = Path(CACHE_DIR) / f"{t}.csv"
        if cp.exists():
            try:
                s = pd.read_csv(cp, parse_dates=[0], index_col=0).iloc[:, 0]
                s.name = t; fetched[t] = s; continue
            except Exception:
                pass
        try:
            d = yf.download(t, start="1995-01-01", auto_adjust=True, progress=False, threads=False)
            if isinstance(d.columns, pd.MultiIndex):
                d = d["Close"]
            c = d["Close"] if "Close" in d.columns else d.iloc[:, 0]
            c = c.dropna(); c.name = t
            c.to_csv(cp, header=True)
            fetched[t] = c
            log.info(f"  {t}: {c.index[0].date()} to {c.index[-1].date()}")
        except Exception as e:
            log.warning(f"  Cannot fetch {t}: {e}")

    if fetched:
        extras = pd.DataFrame(fetched)
        panel = panel.join(extras, how="outer").sort_index()
    log.info(f"Full panel: {panel.index[0].date()} to {panel.index[-1].date()}, {len(panel.columns)} cols")
    return panel


# ══════════════════════════════════════════════════════════════════════════════
# FCP engine on peer universe helper
# ══════════════════════════════════════════════════════════════════════════════

def run_fcp_on_universe(panel, start, end, universe, safe_pool, canary_assets, label=""):
    needed = [a for a in universe + safe_pool + canary_assets if a in panel.columns]
    first_dates = [panel[a].first_valid_index() for a in needed if panel[a].first_valid_index() is not None]
    actual_start = max(start, max(first_dates)) if first_dates else start
    rets = run_backtest_custom(
        panel=panel, start=actual_start, end=end,
        universe=universe, safe_pool=safe_pool, canary_assets=canary_assets,
        top_k=TOP_K_CANDIDATES, hold_buffer=HOLD_BUFFER,
        apply_vol_target=True, cost_bps=COST_BPS,
    )
    m = extended_metrics(rets, label=label)
    return m, rets


def run_peer_on_universe(panel, start, end, signal_fn, signal_kwargs,
                          all_assets, label="", apply_vol_target=False):
    avail = list(dict.fromkeys(a for a in all_assets if a in panel.columns))
    if not avail:
        return {"label": label, "sharpe": np.nan, "cagr": np.nan, "vol": np.nan,
                "max_dd": np.nan, "sortino": np.nan, "calmar": np.nan, "upi": np.nan,
                "years": 0.0, "actual_start": "N/A"}
    first_dates = [panel[a].first_valid_index() for a in avail if panel[a].first_valid_index() is not None]
    actual_start = max(start, max(first_dates)) if first_dates else start
    rets = run_peer_backtest(
        panel=panel, start=actual_start, end=end,
        signal_fn=signal_fn, signal_kwargs=signal_kwargs,
        all_assets=avail, cost_bps=COST_BPS, apply_vol_target=apply_vol_target,
    )
    m = extended_metrics(rets, label=label)
    return m


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

def main():
    log.info("peer_strategy_faithful_reproduction.py — START")
    log.info(f"Standard window: {GLOBAL_START.date()} to {GLOBAL_END.date()}")
    log.info("Cost: 10bps/side (uniform). FCP: vol-target ON. Peer engines: vol-target OFF.")
    log.info("")

    panel = load_full_panel()
    log.info("")

    results = []

    # ── BASELINE: FCP + FCP-15 ────────────────────────────────────────────────
    log.info("=" * 70)
    log.info("BASELINE: FCP engine + FCP-15 (production)")
    log.info("=" * 70)
    m, _ = run_fcp_on_universe(
        panel, GLOBAL_START, GLOBAL_END,
        universe=FCP15, safe_pool=FCP_SAFE, canary_assets=FCP_CANARY,
        label="FCP-production | FCP-15 | FCP-engine",
    )
    log.info(f"  Sh={m['sharpe']:.3f}  CAGR={m['cagr']*100:.2f}%  DD={m['max_dd']*100:.2f}%  "
             f"[{m['actual_start']}  {m['years']:.1f}y]")
    results.append(m)

    # ── 1. FABER GTAA5 ────────────────────────────────────────────────────────
    log.info("")
    log.info("=" * 70)
    log.info("STRATEGY 1: Faber GTAA5")
    log.info(f"  Universe: {FABER_UNIV}  Cash: {FABER_CASH}")
    log.info("  Rule: equal-weight price>SMA10; else SHV. No vol-target.")
    log.info("  ASSUMPTION: SHV as T-bill proxy. T+1 execution.")
    log.info("=" * 70)
    faber_assets = FABER_UNIV + [FABER_CASH]
    faber_kwargs = {"universe": FABER_UNIV, "cash": FABER_CASH}

    log.info("\n[1A] Faber engine + Faber-5 universe (paper reproduction)")
    m = run_peer_on_universe(panel, GLOBAL_START, GLOBAL_END,
        faber_gtaa5_weights, faber_kwargs, faber_assets,
        label="Faber-GTAA5 | Faber-5 | Faber-engine")
    log.info(f"  Sh={m['sharpe']:.3f}  CAGR={m['cagr']*100:.2f}%  DD={m['max_dd']*100:.2f}%  "
             f"[{m['actual_start']}  {m['years']:.1f}y]")
    results.append(m)

    log.info("\n[1B] Faber engine + FCP-15 universe")
    m = run_peer_on_universe(panel, GLOBAL_START, GLOBAL_END,
        faber_gtaa5_weights, {"universe": FCP15, "cash": FABER_CASH},
        FCP15 + [FABER_CASH],
        label="Faber-GTAA5 | FCP-15 | Faber-engine")
    log.info(f"  Sh={m['sharpe']:.3f}  CAGR={m['cagr']*100:.2f}%  DD={m['max_dd']*100:.2f}%  "
             f"[{m['actual_start']}  {m['years']:.1f}y]")
    results.append(m)

    log.info("\n[1C] FCP engine + Faber-5 universe")
    m, _ = run_fcp_on_universe(panel, GLOBAL_START, GLOBAL_END,
        universe=FABER_UNIV, safe_pool=FCP_SAFE, canary_assets=FCP_CANARY,
        label="Faber-GTAA5 | Faber-5 | FCP-engine")
    log.info(f"  Sh={m['sharpe']:.3f}  CAGR={m['cagr']*100:.2f}%  DD={m['max_dd']*100:.2f}%  "
             f"[{m['actual_start']}  {m['years']:.1f}y]")
    results.append(m)

    # ── 2. ANTONACCI GEM ──────────────────────────────────────────────────────
    log.info("")
    log.info("=" * 70)
    log.info("STRATEGY 2: Antonacci GEM")
    log.info(f"  Risky: {GEM_RISKY}  Bond: {GEM_BOND}  T-bill proxy: {GEM_TBILL}")
    log.info("  Rule: SPY 12mo > T-bill → top SPY/EFA by 12mo; else AGG")
    log.info("  No vol-target. T+1 execution.")
    log.info("  ASSUMPTION: SHV as T-bill proxy (tracks 0-3mo T-bills).")
    log.info("=" * 70)
    gem_assets  = GEM_RISKY + [GEM_BOND, GEM_TBILL]
    gem_kwargs  = {"risky_universe": None, "spy": "SPY", "efa": "EFA",
                   "bond": GEM_BOND, "tbill": GEM_TBILL}

    log.info("\n[2A] GEM engine + GEM-3 universe (paper reproduction)")
    m = run_peer_on_universe(panel, GLOBAL_START, GLOBAL_END,
        gem_weights, gem_kwargs, gem_assets,
        label="GEM | GEM-3 | GEM-engine")
    log.info(f"  Sh={m['sharpe']:.3f}  CAGR={m['cagr']*100:.2f}%  DD={m['max_dd']*100:.2f}%  "
             f"[{m['actual_start']}  {m['years']:.1f}y]")
    results.append(m)

    log.info("\n[2B] GEM engine + FCP-15 universe")
    log.info("  ASSUMPTION: SPY used for absolute momentum filter (external to FCP-15 risky basket).")
    log.info("  ASSUMPTION: defensive=TLT (in FCP-15; natural bond defensive). Risk-on: top-1 FCP-15 by 12mo.")
    # SPY must be in all_assets so absolute filter can fire; TLT is defensive (in FCP-15)
    gem_fcp15_kwargs = {"risky_universe": FCP15, "spy": "SPY", "efa": "EFA",
                        "bond": "TLT", "tbill": GEM_TBILL}
    m = run_peer_on_universe(panel, GLOBAL_START, GLOBAL_END,
        gem_weights, gem_fcp15_kwargs, FCP15 + ["SPY", GEM_TBILL],
        label="GEM | FCP-15 | GEM-engine")
    log.info(f"  Sh={m['sharpe']:.3f}  CAGR={m['cagr']*100:.2f}%  DD={m['max_dd']*100:.2f}%  "
             f"[{m['actual_start']}  {m['years']:.1f}y]")
    results.append(m)

    log.info("\n[2C] FCP engine + GEM-3 universe")
    m, _ = run_fcp_on_universe(panel, GLOBAL_START, GLOBAL_END,
        universe=GEM_RISKY + [GEM_BOND], safe_pool=FCP_SAFE, canary_assets=FCP_CANARY,
        label="GEM | GEM-3 | FCP-engine")
    log.info(f"  Sh={m['sharpe']:.3f}  CAGR={m['cagr']*100:.2f}%  DD={m['max_dd']*100:.2f}%  "
             f"[{m['actual_start']}  {m['years']:.1f}y]")
    results.append(m)

    # ── 3. VAA-G4 ─────────────────────────────────────────────────────────────
    log.info("")
    log.info("=" * 70)
    log.info("STRATEGY 3: Keller VAA-G4")
    log.info(f"  Risky: {VAA_RISKY}  Safe: {VAA_SAFE}")
    log.info("  Rule: 13612W breadth; breadth/n risky, rest safe. No vol-target.")
    log.info("  ASSUMPTION: live dates (no synthetic back-extension for EEM/VEA).")
    log.info("=" * 70)
    vaa_assets = VAA_RISKY + VAA_SAFE
    vaa_kwargs = {"risky": VAA_RISKY, "safe": VAA_SAFE}

    log.info("\n[3A] VAA engine + VAA-G4 universe (paper reproduction)")
    m = run_peer_on_universe(panel, GLOBAL_START, GLOBAL_END,
        vaa_g4_weights, vaa_kwargs, vaa_assets,
        label="VAA-G4 | VAA-7 | VAA-engine")
    log.info(f"  Sh={m['sharpe']:.3f}  CAGR={m['cagr']*100:.2f}%  DD={m['max_dd']*100:.2f}%  "
             f"[{m['actual_start']}  {m['years']:.1f}y]")
    results.append(m)

    log.info("\n[3B] VAA engine + FCP-15 universe")
    log.info("  ASSUMPTION: breadth denominator=15. Safe pool: LQD/IEF/SHY unchanged.")
    m = run_peer_on_universe(panel, GLOBAL_START, GLOBAL_END,
        vaa_g4_weights, {"risky": FCP15, "safe": VAA_SAFE},
        FCP15 + VAA_SAFE,
        label="VAA-G4 | FCP-15 | VAA-engine")
    log.info(f"  Sh={m['sharpe']:.3f}  CAGR={m['cagr']*100:.2f}%  DD={m['max_dd']*100:.2f}%  "
             f"[{m['actual_start']}  {m['years']:.1f}y]")
    results.append(m)

    log.info("\n[3C] FCP engine + VAA-G4 universe")
    m, _ = run_fcp_on_universe(panel, GLOBAL_START, GLOBAL_END,
        universe=VAA_RISKY, safe_pool=FCP_SAFE, canary_assets=FCP_CANARY,
        label="VAA-G4 | VAA-7 | FCP-engine")
    log.info(f"  Sh={m['sharpe']:.3f}  CAGR={m['cagr']*100:.2f}%  DD={m['max_dd']*100:.2f}%  "
             f"[{m['actual_start']}  {m['years']:.1f}y]")
    results.append(m)

    # ── 4. HAA-BALANCED ───────────────────────────────────────────────────────
    log.info("")
    log.info("=" * 70)
    log.info("STRATEGY 4: Keller HAA-Balanced (2023)")
    log.info(f"  Canary: {HAA_CANARY}  Offensive: {HAA_OFFENSIVE}")
    log.info(f"  Safe: {HAA_SAFE}  Top-K: {HAA_TOP_K}")
    log.info("  Rule: 13612W(TIP)>0 → risk-on → top-4 offensive; else best-safe.")
    log.info("  No vol-target. T+1 execution.")
    log.info("  ASSUMPTION: MTUM live April 2013 → peer-universe start ~2013-05.")
    log.info("  ASSUMPTION: BIL as primary safe pool anchor.")
    log.info("=" * 70)
    haa_assets = HAA_OFFENSIVE + HAA_SAFE + [HAA_CANARY]
    haa_kwargs = {"offensive": HAA_OFFENSIVE, "safe": HAA_SAFE,
                  "canary": HAA_CANARY, "top_k": HAA_TOP_K}

    log.info("\n[4A] HAA engine + HAA-Balanced universe (paper reproduction)")
    m = run_peer_on_universe(panel, GLOBAL_START, GLOBAL_END,
        haa_balanced_weights, haa_kwargs, haa_assets,
        label="HAA-Balanced | HAA-Bal | HAA-engine")
    log.info(f"  Sh={m['sharpe']:.3f}  CAGR={m['cagr']*100:.2f}%  DD={m['max_dd']*100:.2f}%  "
             f"[{m['actual_start']}  {m['years']:.1f}y]")
    results.append(m)

    log.info("\n[4B] HAA engine + FCP-15 universe")
    log.info("  ASSUMPTION: offensive=FCP-15, canary=TIP, safe=BIL/IEF/TLT.")
    haa_fcp15_kwargs = {"offensive": FCP15, "safe": HAA_SAFE,
                        "canary": HAA_CANARY, "top_k": HAA_TOP_K}
    m = run_peer_on_universe(panel, GLOBAL_START, GLOBAL_END,
        haa_balanced_weights, haa_fcp15_kwargs, FCP15 + HAA_SAFE + [HAA_CANARY],
        label="HAA-Balanced | FCP-15 | HAA-engine")
    log.info(f"  Sh={m['sharpe']:.3f}  CAGR={m['cagr']*100:.2f}%  DD={m['max_dd']*100:.2f}%  "
             f"[{m['actual_start']}  {m['years']:.1f}y]")
    results.append(m)

    log.info("\n[4C] FCP engine + HAA-Balanced universe (offensive basket as risky)")
    m, _ = run_fcp_on_universe(panel, GLOBAL_START, GLOBAL_END,
        universe=HAA_OFFENSIVE, safe_pool=FCP_SAFE, canary_assets=FCP_CANARY,
        label="HAA-Balanced | HAA-Bal | FCP-engine")
    log.info(f"  Sh={m['sharpe']:.3f}  CAGR={m['cagr']*100:.2f}%  DD={m['max_dd']*100:.2f}%  "
             f"[{m['actual_start']}  {m['years']:.1f}y]")
    results.append(m)

    # ══════════════════════════════════════════════════════════════════════════
    # SUMMARY TABLE
    # ══════════════════════════════════════════════════════════════════════════
    log.info("")
    log.info("=" * 70)
    log.info("FINAL COMPARISON TABLE")
    log.info("=" * 70)
    log.info("")

    hdr = (f"{'Strategy':<30} {'Universe':<10} {'Engine':<13} "
           f"{'Sh':>6} {'CAGR':>7} {'Vol':>6} {'DD':>7} "
           f"{'Sort':>6} {'Cal':>5} {'UPI':>5} {'Yrs':>4}")
    log.info(hdr)
    log.info("-" * len(hdr))

    def fmt_pct(v):
        return f"{v*100:.2f}%" if pd.notna(v) else "N/A"
    def fmt_f(v, d=3):
        return f"{v:.{d}f}" if pd.notna(v) else "N/A"

    for r in results:
        parts = r["label"].split(" | ")
        strat = parts[0] if len(parts)>0 else ""
        univ  = parts[1] if len(parts)>1 else ""
        eng   = parts[2] if len(parts)>2 else ""
        log.info(
            f"{strat:<30} {univ:<10} {eng:<13} "
            f"{fmt_f(r['sharpe']):>6} {fmt_pct(r['cagr']):>7} "
            f"{fmt_pct(r['vol']):>6} {fmt_pct(r['max_dd']):>7} "
            f"{fmt_f(r['sortino']):>6} {fmt_f(r['calmar'],2):>5} "
            f"{fmt_f(r['upi'],2):>5} {r['years']:>4.1f}"
        )

    # ── Analysis ──────────────────────────────────────────────────────────────
    log.info("")
    log.info("=" * 70)
    log.info("ANALYSIS: ENGINE vs UNIVERSE DECOMPOSITION")
    log.info("=" * 70)

    def get_sh(parts_required):
        for r in results:
            if all(p in r["label"] for p in parts_required):
                return r["sharpe"]
        return np.nan

    fcp15_sh = get_sh(["FCP-15", "FCP-engine"])

    log.info("")
    log.info("Q1: Does FCP ENGINE beat peer engine on SAME peer universe?")
    log.info("    (FCP-engine vs peer-engine, both on peer universe)")
    log.info("")
    rows = [
        ("Faber GTAA5", "Faber-GTAA5", "Faber-5", "Faber-engine"),
        ("GEM",         "GEM",         "GEM-3",   "GEM-engine"),
        ("VAA-G4",      "VAA-G4",      "VAA-7",   "VAA-engine"),
        ("HAA-Balanced","HAA-Balanced","HAA-Bal",  "HAA-engine"),
    ]
    for label, strat_tag, univ_tag, peer_eng in rows:
        sh_peer = get_sh([strat_tag, univ_tag, peer_eng])
        sh_fcp  = get_sh([strat_tag, univ_tag, "FCP-engine"])
        if pd.notna(sh_peer) and pd.notna(sh_fcp):
            d = sh_fcp - sh_peer
            v = "FCP BETTER" if d > 0.05 else ("PARITY" if abs(d) <= 0.05 else "Peer BETTER")
            log.info(f"  {label:<20}: FCP={sh_fcp:.3f}  peer={sh_peer:.3f}  delta={d:+.3f}  {v}")
        else:
            log.info(f"  {label:<20}: data missing")

    log.info("")
    log.info("Q2: Does FCP UNIVERSE beat peer universe on SAME peer engine?")
    log.info("    (FCP-15 vs peer universe, both with peer engine)")
    log.info("")
    for label, strat_tag, univ_tag, peer_eng in rows:
        sh_peer_univ = get_sh([strat_tag, univ_tag, peer_eng])
        sh_fcp_univ  = get_sh([strat_tag, "FCP-15", peer_eng])
        if pd.notna(sh_peer_univ) and pd.notna(sh_fcp_univ):
            d = sh_fcp_univ - sh_peer_univ
            v = "FCP-15 BETTER" if d > 0.05 else ("PARITY" if abs(d) <= 0.05 else "Peer univ BETTER")
            log.info(f"  {label:<20}: FCP-15={sh_fcp_univ:.3f}  peer-univ={sh_peer_univ:.3f}  delta={d:+.3f}  {v}")
        else:
            log.info(f"  {label:<20}: data missing")

    log.info("")
    log.info("Q3: FCP-engine vs peer-engine on FCP-15 (same playing field)")
    log.info(f"    FCP baseline (FCP-engine, FCP-15): {fcp15_sh:.3f}")
    log.info("")
    for label, strat_tag, _, peer_eng in rows:
        sh = get_sh([strat_tag, "FCP-15", peer_eng])
        if pd.notna(sh) and pd.notna(fcp15_sh):
            d = fcp15_sh - sh
            log.info(f"  {label:<20} engine on FCP-15: {sh:.3f}  (FCP edge: {d:+.3f})")
        else:
            log.info(f"  {label:<20} engine on FCP-15: N/A")

    log.info("")
    log.info("INTERPRETATION GUIDE:")
    log.info("  Engine alpha: FCP-engine > peer-engine on SAME universe (Q1)")
    log.info("  Universe alpha: FCP-15 > peer-univ on SAME engine (Q2)")
    log.info("  Co-tuning: if FCP wins Q3 but not Q1/Q2, FCP = engine+universe synergy")

    # ── CSV ───────────────────────────────────────────────────────────────────
    csv_path = Path(__file__).resolve().parent / "peer_strategy_faithful_reproduction.csv"
    pd.DataFrame(results).to_csv(csv_path, index=False)
    log.info("")
    log.info(f"CSV: {csv_path}")
    log.info("peer_strategy_faithful_reproduction.py — DONE")
    log.info(f"Log: {LOG_PATH}")


if __name__ == "__main__":
    main()
