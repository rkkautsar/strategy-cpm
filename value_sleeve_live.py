"""Fundamental Value+Quality equity sleeve (VAL).

Spec:
  1. Universe: PIT Nasdaq-100 constituents via index_constitution (2010-06+)
     intersected with PIT Valuein fundamentals coverage and >= 260 trading days
     of price history in the NDX panel.
  2. Fundamentals: PIT value_as_filed facts with accepted_at <= sig_d.
  3. Composites: VALUE (Earnings yield, Book/Price, Sales yield, FCF yield)
     and QUALITY (Gross profitability, ROE, Neg leverage, Accrual flag) EW z-scores.
  4. Selection: Top-half by QUALITY, then cheapest by VALUE.
  5. Trend Filter: Stateful he5_te0 band (ENTER > 1.05 * SMA10m, HOLD >= 1.00 * SMA10m)
     plus held-name QUALITY re-screen (drop held if QUALITY < monthly Q20 of candidate set).
  6. Sizing/Gate: Equal weight 1/K (K=5). Gate OFF -> 100% best-of-safe.
  7. Execution: T+1 OPEN (MOO), 10 bps transaction cost per side, 10% delisting haircut.
"""
from __future__ import annotations
import functools
import json
import os
import pickle
import sys
import tempfile
from pathlib import Path
import numpy as np
import pandas as pd
import index_constitution as ic

from cpm_live import DEFAULT_CASH, SAFE_POOL
from core import sig_13612U
from ndx_sleeve_live import _pick_safe

ROOT = Path(__file__).resolve().parent
DEFAULT_CACHE_DIR = "data/valuein"
SPY_TICKER = "SPY"
SELECT_K = 5
COST_BPS_PER_SIDE = 10
DELISTING_HAIRCUT = -0.10
CASH_TICKER = DEFAULT_CASH

FLOW_CONCEPTS = ["TotalRevenue", "NetIncome", "GrossProfit", "OperatingIncome", "OperatingCashFlow", "CAPEX"]
BS_CONCEPTS = ["TotalAssets", "TotalLiabilities", "StockholdersEquity", "ShortTermDebt", "LongTermDebt", "CommonSharesOutstanding"]

# ===========================================================================
# PIT Static Splits and Manifest Loading (No Network Path allowed)
# ===========================================================================
SPLITS_CALENDAR_PATH = ROOT / "data" / "splits_calendar.json"
SPLITS_COVERED_PATH = ROOT / "data" / "splits_covered_manifest.json"

# Enforce strictly offline compilation
if not SPLITS_CALENDAR_PATH.exists() or not SPLITS_COVERED_PATH.exists():
    raise FileNotFoundError(
        "Static split calendar or covered manifest is missing! "
        "Run 'python scripts/build_static_splits.py' once offline first."
    )

with open(SPLITS_CALENDAR_PATH, "r") as _f:
    _cal_raw = json.load(_f)
    # Parse date strings to pandas Timestamps for point-in-time logic
    SPLIT_CAL = {
        t: [(pd.Timestamp(d), float(f)) for d, f in v]
        for t, v in _cal_raw.items() if v
    }

with open(SPLITS_COVERED_PATH, "r") as _f:
    _cov_raw = json.load(_f)
    COVERED_TICKERS = set(_cov_raw["covered"])


# ===========================================================================
# 1. Local Cache Reader and Builders
# ===========================================================================
from data_loader import load_valuein_cache


def _build_pit_flows(fact: pd.DataFrame) -> dict:
    """(ticker, flow concept) -> DataFrame[period_end, accepted, value] sorted by period_end."""
    flows = fact.loc[fact.standard_concept.isin(FLOW_CONCEPTS),
        ["ticker", "standard_concept", "fiscal_year", "fiscal_period", "period_end", "accepted", "value_as_filed"]].copy()

    if flows.empty:
        return {}
    flows = flows.sort_values(
        ["ticker", "standard_concept", "fiscal_year", "fiscal_period", "accepted", "period_end", "value_as_filed"],
        ascending=[True, True, True, True, True, False, True], kind="stable").reset_index(drop=True)
    flows["_ord"] = np.arange(len(flows), dtype=np.int64)
    fy_keys = ["ticker", "standard_concept", "fiscal_year"]
    direct = flows.loc[flows.fiscal_period.isin(["Q1", "Q2", "Q3", "Q4"]),
        ["ticker", "standard_concept", "period_end", "accepted", "value_as_filed", "_ord"]].rename(columns={"value_as_filed": "value"})
    fy_first = (flows.loc[flows.fiscal_period == "FY", fy_keys + ["period_end", "accepted", "value_as_filed", "_ord"]]
        .sort_values("_ord", kind="stable").drop_duplicates(fy_keys, keep="first"))
    derived = pd.DataFrame(columns=["ticker", "standard_concept", "period_end", "accepted", "value", "_ord"])
    if not fy_first.empty:
        q_first = (flows.loc[flows.fiscal_period.isin(["Q1", "Q2", "Q3", "Q4"]), fy_keys + ["fiscal_period", "value_as_filed", "_ord"]]
            .sort_values("_ord", kind="stable").drop_duplicates(fy_keys + ["fiscal_period"], keep="first"))
        q_pivot = q_first.pivot(index=fy_keys, columns="fiscal_period", values="value_as_filed").reset_index()
        q = fy_first.merge(q_pivot, on=fy_keys, how="left")
        q1 = q.get("Q1", pd.Series(np.nan, index=q.index))
        q2 = q.get("Q2", pd.Series(np.nan, index=q.index))
        q3 = q.get("Q3", pd.Series(np.nan, index=q.index))
        q4 = q.get("Q4", pd.Series(np.nan, index=q.index))
        ok = q4.isna() & q1.notna() & q2.notna() & q3.notna()
        q = q.loc[ok].copy()
        if not q.empty:
            q = q.sort_values(fy_keys, kind="stable")
            q["value"] = q["value_as_filed"] - q1.loc[q.index] - q2.loc[q.index] - q3.loc[q.index]
            q["_ord"] = np.arange(len(q), dtype=np.int64) + (int(direct["_ord"].max()) + 1 if not direct.empty else 0)
            derived = q[["ticker", "standard_concept", "period_end", "accepted", "value", "_ord"]]
    combined = pd.concat([direct, derived], ignore_index=True)
    if combined.empty:
        return {}

    combined = combined.sort_values(["ticker", "standard_concept", "period_end", "value"], kind="stable")
    combined = combined.drop_duplicates(["ticker", "standard_concept", "period_end"], keep="first")
    combined = combined.sort_values(["ticker", "standard_concept", "period_end"]).reset_index(drop=True)
    return {(t, c): g[["period_end", "accepted", "value"]].reset_index(drop=True)
            for (t, c), g in combined.groupby(["ticker", "standard_concept"], sort=False)}


def _build_pit_bs(fact: pd.DataFrame) -> dict:
    """(ticker, bs concept) -> DataFrame[period_end, accepted, value] sorted by period_end."""
    out = {}
    bs = fact[fact.standard_concept.isin(BS_CONCEPTS)]
    if bs.empty:
        return out

    for (tic, con), g in bs.groupby(["ticker", "standard_concept"]):
        df = g[["period_end", "accepted", "_src", "period_start", "value_as_filed"]].rename(columns={"value_as_filed": "value"})
        df["absval"] = df["value"].abs()
        df["_inst"] = df["period_start"].isna().astype(int)
        df = (df.sort_values(["period_end", "_src", "accepted", "_inst", "absval"],
                             ascending=[True, True, True, False, False], kind="stable")
              .drop_duplicates("period_end", keep="first")
              .sort_values("period_end")[["period_end", "accepted", "value"]].reset_index(drop=True))
        out[(tic, con)] = df
    return out


def _ttm_asof(df: pd.DataFrame | None, sig_d: pd.Timestamp, max_span_days: int = 430) -> float:
    """Sum last 4 discrete quarters with accepted <= sig_d (asserting period span <= max_span_days)."""
    if df is None or df.empty:
        return np.nan

    accepted = df["accepted"].to_numpy()
    idx = np.flatnonzero(accepted <= sig_d)
    if idx.size < 4:
        return np.nan

    last4_idx = idx[-4:]
    period_end = df["period_end"].to_numpy()
    span = int((period_end[last4_idx[-1]] - period_end[last4_idx[0]]) / np.timedelta64(1, "D"))
    if span > max_span_days:
        return np.nan

    values = df["value"].to_numpy(dtype="float64", copy=False)
    return float(np.nansum(values[last4_idx]))


def _bs_asof(df: pd.DataFrame | None, sig_d: pd.Timestamp) -> float:
    """Most recent balance-sheet value with accepted <= sig_d."""
    if df is None or df.empty:
        return np.nan

    accepted = df["accepted"].to_numpy()
    idx = np.flatnonzero(accepted <= sig_d)
    if idx.size == 0:
        return np.nan

    values = df["value"].to_numpy(dtype="float64", copy=False)
    return float(values[idx[-1]])


# ===========================================================================
# 2. Factor and Composite Formulation
# ===========================================================================
def _z(s: pd.Series) -> pd.Series:
    s = pd.Series(s, dtype="float64")
    mu, sd = s.mean(), s.std()
    if not (sd and sd > 0):
        return pd.Series(0.0, index=s.index)
    return (s - mu) / sd


def compute_fundamental_composites(cands: dict, sig_d: pd.Timestamp, FLOWS: dict, BS: dict) -> pd.DataFrame:
    """Computes PIT VALUE and QUALITY composites for all eligible candidates."""

    # --- Decision 2b Hybrid Mcap Guard & Loose Absolute Floor ---
    LB = 21
    K = 2.5
    GROSS = 50.0
    LO, HI = 1e6, 1e14

    def _accept_asof(df: pd.DataFrame | None, asof_d: pd.Timestamp) -> tuple[float, pd.Timestamp | None]:
        if df is None or df.empty:
            return np.nan, None
        acc = df["accepted"].to_numpy()
        idx = np.flatnonzero(acc <= asof_d)
        if idx.size == 0:
            return np.nan, None
        return float(df["value"].to_numpy()[idx[-1]]), pd.Timestamp(acc[idx[-1]])

    def cumsplit(ticker: str, d0: pd.Timestamp, d1: pd.Timestamp) -> float:
        s = 1.0
        for d, f in SPLIT_CAL.get(ticker, []):
            if d0 < d <= d1:
                s *= f
        return s

    kept_cands = {}
    for t, ds in cands.items():
        if len(ds) < LB + 1:
            # Fall back to a simple absolute floor check when price history is too short for prior legs
            price = float(ds.iloc[-1])
            shares = _bs_asof(BS.get((t, "CommonSharesOutstanding")), sig_d)
            if pd.notna(shares) and shares > 0 and price > 0:
                mcap_now = price * shares
                if LO <= mcap_now <= HI:
                    kept_cands[t] = ds
            continue

        p_now = float(ds.iloc[-1])
        p_ref = float(ds.iloc[-(LB + 1)])
        rd = ds.index[-(LB + 1)]

        shdf = BS.get((t, "CommonSharesOutstanding"))
        sh_now, acc_now = _accept_asof(shdf, sig_d)
        sh_ref, acc_ref = _accept_asof(shdf, rd)

        if not (p_now > 0 and p_ref > 0 and pd.notna(sh_now) and sh_now > 0 and pd.notna(sh_ref) and sh_ref > 0):
            continue

        mcap_now = p_now * sh_now

        # Leg 1: Loose Absolute Floor
        if mcap_now < LO or mcap_now > HI:
            continue

        # Leg 2: Ratio check (split-corrected vs. gross-50 fallback)
        raw_ratio = (p_now * sh_now) / (p_ref * sh_ref)
        if t in COVERED_TICKERS:
            S = cumsplit(t, acc_ref, acc_now) if (acc_ref and acc_now) else 1.0
            rc = raw_ratio / S
            if rc > K or rc < (1.0 / K):
                continue
        else:
            if raw_ratio > GROSS or raw_ratio < (1.0 / GROSS):
                continue

        kept_cands[t] = ds

    # Re-bind cands to the filtered universe
    cands = kept_cands
    # --- End of Guard Logic ---

    recs = []
    for t, ds in cands.items():
        price = float(ds.iloc[-1])
        shares = _bs_asof(BS.get((t, "CommonSharesOutstanding")), sig_d)
        if not (pd.notna(shares) and shares > 0 and price > 0):
            continue
        mcap = price * shares
        ni = _ttm_asof(FLOWS.get((t, "NetIncome")), sig_d)
        rev = _ttm_asof(FLOWS.get((t, "TotalRevenue")), sig_d)
        gp = _ttm_asof(FLOWS.get((t, "GrossProfit")), sig_d)
        oi = _ttm_asof(FLOWS.get((t, "OperatingIncome")), sig_d)
        ocf = _ttm_asof(FLOWS.get((t, "OperatingCashFlow")), sig_d)
        capex = _ttm_asof(FLOWS.get((t, "CAPEX")), sig_d)
        eq = _bs_asof(BS.get((t, "StockholdersEquity")), sig_d)
        ta = _bs_asof(BS.get((t, "TotalAssets")), sig_d)
        std = _bs_asof(BS.get((t, "ShortTermDebt")), sig_d)
        ltd = _bs_asof(BS.get((t, "LongTermDebt")), sig_d)
        debt = np.nansum([std if pd.notna(std) else 0.0, ltd if pd.notna(ltd) else 0.0])

        # value components (higher = cheaper)
        ey = ni / mcap if pd.notna(ni) else np.nan
        bp = eq / mcap if (pd.notna(eq) and eq > 0) else np.nan
        sy = rev / mcap if pd.notna(rev) else np.nan
        fcf = (ocf - capex) if (pd.notna(ocf) and pd.notna(capex)) else np.nan
        fy = fcf / mcap if pd.notna(fcf) else np.nan

        # quality components (higher = better)
        gpoa = gp / ta if (pd.notna(gp) and pd.notna(ta) and ta > 0) else np.nan
        roe = ni / eq if (pd.notna(ni) and pd.notna(eq) and eq > 0) else np.nan
        lev = -(debt / eq) if (pd.notna(eq) and eq > 0 and (std is not None or ltd is not None)) else np.nan
        accr = (1.0 if (pd.notna(ocf) and pd.notna(ni) and ocf > ni) else 0.0) \
            if (pd.notna(ocf) and pd.notna(ni)) else np.nan

        recs.append(dict(t=t, ey=ey, bp=bp, sy=sy, fy=fy, gpoa=gpoa, roe=roe, lev=lev, accr=accr))
    if not recs:
        return pd.DataFrame()
    df = pd.DataFrame(recs).set_index("t")
    val_cols = ["ey", "bp", "sy", "fy"]
    qual_cols = ["gpoa", "roe", "lev", "accr"]
    vz = pd.DataFrame({c: _z(df[c]).where(df[c].notna()) for c in val_cols})
    qz = pd.DataFrame({c: _z(df[c]).where(df[c].notna()) for c in qual_cols})
    df["VALUE"] = vz.mean(axis=1, skipna=True)
    df["QUALITY"] = qz.mean(axis=1, skipna=True)
    df = df[vz.notna().any(axis=1) & qz.notna().any(axis=1)]
    return df


def valqual_order(ftab: pd.DataFrame, K_select: int = SELECT_K) -> list[str]:
    """Top-half of candidates by QUALITY, then rank by VALUE (descending)."""
    if ftab.empty:
        return []
    med = ftab["QUALITY"].median()
    pool = ftab[ftab["QUALITY"] >= med]
    if len(pool) < K_select:
        pool = ftab  # fall back to whole set if screen too tight
    return pool.sort_values("VALUE", ascending=False).index.tolist()


def trend_info(ds: pd.Series) -> tuple[float, float]:
    """(price, sma10m) PIT from daily series <= sig_d."""
    m = ds.resample("ME").last().dropna()
    price = float(ds.iloc[-1])
    if len(m) < 10:
        return price, np.nan
    last10 = m.tail(10)
    return price, float(last10.mean())


def apply_stateful_trend_band(ftab: pd.DataFrame, trend: dict, state: dict, K_select: int = SELECT_K) -> list[str]:
    """Stateful high-entry/tight-exit (he5_te0) trend logic + held-name QUALITY<Q20 re-screen."""
    if ftab.empty:
        return []
    valid = set(ftab.index)
    q20 = ftab["QUALITY"].quantile(0.20)
    H = state.get("H", [])
    kept = []
    for t in H:
        if t in valid and t in trend:
            p, sma = trend[t]
            if pd.notna(sma) and p >= sma:
                q = ftab.loc[t, "QUALITY"]
                if q < q20:
                    continue
                kept.append(t)
    pool = valqual_order(ftab, K_select)
    new = []
    for t in pool:
        if t in kept or t not in trend:
            continue
        p, sma = trend[t]
        if pd.notna(sma) and p > 1.05 * sma:
            new.append(t)
    picks = (kept + new)[:K_select]
    state["H"] = picks
    return picks


def reconstruct_state(
    cpm_panel: pd.DataFrame,
    ndx_panel: pd.DataFrame,
    sig_d: pd.Timestamp,
    cache_dir: str = DEFAULT_CACHE_DIR,
) -> dict:
    """Reconstruct state chronological history up to last month-end before sig_d."""
    full_panel = cpm_panel.join(ndx_panel, how="outer", rsuffix="_dup")
    full_panel = full_panel.loc[:, ~full_panel.columns.str.endswith("_dup")]
    monthly_idx = pd.DataFrame({"x": 1}, index=full_panel.index).groupby(pd.Grouper(freq="ME")).tail(1).index
    sig_dates = monthly_idx[(monthly_idx >= pd.Timestamp("2010-06-01")) & (monthly_idx < sig_d)]
    
    FLOWS, BS = load_valuein_cache(cache_dir)
    state = {"H": []}
    for sd in sig_dates:
        try:
            pit = ic.constituents_at("nasdaq100", sd.strftime("%Y-%m-%d"))
            pit_tickers = set(pit["symbol"].tolist())
        except Exception:
            continue
        if not pit_tickers:
            continue
            
        cands = {}
        trend = {}
        for t in pit_tickers:
            if t not in ndx_panel.columns:
                continue
            if sd in ndx_panel.index and pd.isna(ndx_panel.loc[sd, t]):
                continue
            ds = ndx_panel[t].loc[:sd].dropna()
            recent = ds.loc[sd - pd.Timedelta(days=30):sd]
            if recent.empty:
                continue
            cands[t] = ds
            p, sma = trend_info(ds)
            trend[t] = (p, sma)
            
        ftab = compute_fundamental_composites(cands, sd, FLOWS, BS)
        if ftab.empty:
            continue
            
        apply_stateful_trend_band(ftab, trend, state)
    return state


# ===========================================================================
# 3. Execution, Gating and Weight Resolution
# ===========================================================================
def _ndx_vol_gate_ok(daily_spy: pd.Series, sig_d: pd.Timestamp) -> tuple[bool, dict]:
    """NDX-local volatility gate: RV20<RV252 on SPY daily returns."""
    sub = daily_spy.loc[:sig_d].pct_change().dropna()
    if len(sub) < 252:
        return True, {"warmup": True, "rv_20": float("nan"), "rv_252": float("nan")}
    rv_20 = float(sub.tail(20).std() * np.sqrt(252))
    rv_252 = float(sub.tail(252).std() * np.sqrt(252))
    vol_ok = rv_20 < rv_252
    return vol_ok, {"rv_20": rv_20, "rv_252": rv_252, "vol_ok": vol_ok}


def compute_value_weights(
    cpm_panel: pd.DataFrame,
    ndx_panel: pd.DataFrame,
    sig_d: pd.Timestamp,
    state: dict | None = None,
    cache_dir: str = DEFAULT_CACHE_DIR,
) -> tuple[dict, str, dict, dict]:
    """Returns (weights, regime, diagnostics, state).

    Flow:
      - Active gate (canary + SPY trend + SPY volatility)
      - If gate is OFF -> 100% best safe asset.
      - If gate is ON -> selection via PIT composites + stateful he5_te0 band.
    """
    cpm_monthly = cpm_panel.loc[:sig_d].resample("ME").last()
    safe = _pick_safe(cpm_monthly)

    tip_sig = sig_13612U(cpm_monthly["TIP"]) if "TIP" in cpm_monthly.columns else float("nan")
    canary_ok = pd.notna(tip_sig) and tip_sig > 0
    spy_sig = sig_13612U(cpm_monthly[SPY_TICKER]) if SPY_TICKER in cpm_monthly.columns else float("nan")
    trend_ok = pd.notna(spy_sig) and spy_sig > 0

    if SPY_TICKER in cpm_panel.columns:
        vol_ok, vdiag = _ndx_vol_gate_ok(cpm_panel[SPY_TICKER], sig_d)
    else:
        vol_ok, vdiag = False, {"rv_20": float("nan"), "rv_252": float("nan"), "vol_ok": False, "missing_spy": True}

    gate_on = canary_ok and trend_ok and vol_ok
    gate_diag = {
        "tip_sig": tip_sig,
        "spy_sig": spy_sig,
        "canary_ok": canary_ok,
        "trend_ok": trend_ok,
        **vdiag,
        "val_gate_on": gate_on,
    }

    if state is None:
        state = reconstruct_state(cpm_panel, ndx_panel, sig_d, cache_dir)

    if not gate_on:
        reasons = []
        if not canary_ok:
            reasons.append("canary_off")
        if not trend_ok:
            reasons.append("spy_trend_off")
        if not vol_ok:
            reasons.append("vol20_crossover_off")
        return ({safe: 1.0}, "GATE_OFF (VAL_defensive)", {
            **gate_diag,
            "selected": [],
            "reason": "; ".join(reasons),
            "picked_safe": safe,
        }, state)

    # Resolve PIT Nasdaq-100 constituents
    try:
        pit = ic.constituents_at("nasdaq100", sig_d.strftime("%Y-%m-%d"))
        pit_tickers = set(pit["symbol"].tolist())
    except Exception:
        pit_tickers = set()

    if len(pit_tickers) == 0:
        return ({SPY_TICKER: 1.0}, "VAL_FALLBACK_SPY", {
            **gate_diag,
            "selected": [SPY_TICKER],
            "reason": "PIT NDX data unavailable; using SPY proxy",
        }, state)

    # Eligible price series
    cands = {}
    trend = {}
    for t in pit_tickers:
        if t not in ndx_panel.columns:
            continue
        if sig_d in ndx_panel.index and pd.isna(ndx_panel.loc[sig_d, t]):
            continue
        ds = ndx_panel[t].loc[:sig_d].dropna()
        # Require >= 260 trading days of price history
        if len(ds) < 260:
            continue
        recent = ds.loc[sig_d - pd.Timedelta(days=30):sig_d]
        if recent.empty:
            continue
        cands[t] = ds
        p, sma = trend_info(ds)
        trend[t] = (p, sma)

    FLOWS, BS = load_valuein_cache(cache_dir)
    ftab = compute_fundamental_composites(cands, sig_d, FLOWS, BS)
    if ftab.empty:
        return ({safe: 1.0}, "VAL_FALLBACK_SAFE_NO_FUND", {
            **gate_diag,
            "selected": [],
            "reason": "No stocks met PIT fundamental criteria",
        }, state)

    selected = apply_stateful_trend_band(ftab, trend, state, SELECT_K)
    
    per_slot = 1.0 / SELECT_K
    weights = {t: per_slot for t in selected}
    cash_share = 1.0 - len(selected) * per_slot
    if cash_share > 1e-9:
        weights[safe] = weights.get(safe, 0.0) + cash_share

    regime = "VAL_ACTIVE" if len(selected) == SELECT_K else f"VAL_PARTIAL_{len(selected)}"
    return (weights, regime, {
        **gate_diag,
        "n_candidates": len(ftab),
        "selected": selected,
    }, state)


# ===========================================================================
# 4. Standalone Backtester
# ===========================================================================
def run_value_backtest(
    cpm_panel: pd.DataFrame,
    ndx_panel: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
    cost_bps: float = COST_BPS_PER_SIDE,
    cache_dir: str = DEFAULT_CACHE_DIR,
) -> tuple[pd.Series, list[dict]]:
    """Run monthly VAL sleeve backtest. Returns (daily_returns, history)."""
    full_panel = cpm_panel.join(ndx_panel, how="outer", rsuffix="_dup")
    full_panel = full_panel.loc[:, ~full_panel.columns.str.endswith("_dup")]

    monthly_idx = pd.DataFrame({"x": 1}, index=full_panel.index).groupby(
        pd.Grouper(freq="ME")).tail(1).index
    sig_dates = monthly_idx[(monthly_idx >= start) & (monthly_idx <= end)]

    daily_rets = pd.Series(0.0, index=full_panel.loc[start:end].index)
    weights_for_date = {}
    history = []

    state = {"H": []}
    for sd in sig_dates:
        target, regime, diag, state = compute_value_weights(cpm_panel, ndx_panel, sd, state, cache_dir)
        next_loc = full_panel.index.get_indexer([sd], method="bfill")[0] + 1
        if next_loc < len(full_panel.index):
            weights_for_date[full_panel.index[next_loc]] = target
        history.append({"sig_d": sd, "regime": regime, "weights": target,
                        "selected": diag.get("selected", [])})

    exec_dates = sorted(weights_for_date.keys())
    cur_w = {CASH_TICKER: 1.0}
    cur_w_idx = 0
    for ts in full_panel.loc[start:end].index:
        while cur_w_idx < len(exec_dates) and exec_dates[cur_w_idx] <= ts:
            new_w = weights_for_date[exec_dates[cur_w_idx]]
            if cur_w != new_w:
                tovr = sum(abs(cur_w.get(a, 0) - new_w.get(a, 0))
                           for a in set(cur_w) | set(new_w))
                daily_rets.loc[ts] -= tovr * cost_bps / 10000.0
            cur_w = new_w
            cur_w_idx += 1
        prev_loc = full_panel.index.get_loc(ts)
        if prev_loc == 0:
            continue
        prev_d = full_panel.index[prev_loc - 1]
        market_open = full_panel.loc[ts].notna().sum() > full_panel.loc[ts].isna().sum()
        port_r = 0.0
        delisted_w = 0.0
        for asset, w in list(cur_w.items()):
            if asset not in full_panel.columns:
                delisted_w += w
                del cur_w[asset]
                continue
            today = full_panel.loc[ts, asset]
            yest = full_panel.loc[prev_d, asset]
            if pd.notna(today) and pd.notna(yest) and yest > 0:
                port_r += w * (today / yest - 1)
            elif market_open and pd.notna(yest) and yest > 0 and pd.isna(today):
                port_r += w * DELISTING_HAIRCUT
                delisted_w += w
                del cur_w[asset]
        if delisted_w > 0:
            existing_safe = next((s for s in SAFE_POOL if s in cur_w), CASH_TICKER)
            cur_w[existing_safe] = cur_w.get(existing_safe, 0.0) + delisted_w
            if existing_safe in full_panel.columns:
                t_cash = full_panel.loc[ts, existing_safe]
                y_cash = full_panel.loc[prev_d, existing_safe]
                if pd.notna(t_cash) and pd.notna(y_cash) and y_cash > 0:
                    port_r += delisted_w * (t_cash / y_cash - 1)
        daily_rets.loc[ts] += port_r

    return daily_rets, history


from core import _val_backtest_checkpoint_path, cached_value_backtest


# ===========================================================================
# 5. Incremental Cache Refresh
# ===========================================================================
def refresh_valuein_cache(cache_dir: str = DEFAULT_CACHE_DIR):
    """Monthly incremental delta refresh. Appends new fact filings."""
    api_key = os.environ.get("VALUEIN_API_KEY")
    if not api_key:
        print("VALUEIN_API_KEY not found in environment. Skipping cache refresh.")
        return
    
    try:
        from valuein_sdk import ValueinClient
    except ImportError:
        print("valuein_sdk not installed. Skipping cache refresh.")
        return
    client = ValueinClient()
    
    cache_path = Path(cache_dir)
    fact_path = cache_path / "fact.parquet"
    if not fact_path.exists():
        print(f"No existing cache found at {fact_path}. Skipping.")
        return
        
    df_old_fact = pd.read_parquet(fact_path)
    max_acc = df_old_fact["accepted_at"].max()
    print(f"Current max accepted_at in cached facts: {max_acc}")
    
    concepts_str = ", ".join(f"'{c}'" for c in FLOW_CONCEPTS + BS_CONCEPTS)
    sql = f"""
        SELECT entity_id, standard_concept, numeric_value, period_start, period_end, fiscal_year, fiscal_period, accepted_at, value_current, value_as_filed, restated
        FROM fact
        WHERE accepted_at > '{max_acc}'
          AND standard_concept IN ({concepts_str})
          AND entity_id IN (
              SELECT DISTINCT LPAD(CAST(cik AS VARCHAR), 10, '0') 
              FROM index_membership 
              WHERE index_name = 'SP500'
          )
    """
    df_new_fact = client.run_query(sql)
    if df_new_fact.empty:
        print("No new facts to append.")
        return
        
    print(f"Found {len(df_new_fact)} new facts. Appending to cache...")
    df_combined = pd.concat([df_old_fact, df_new_fact], ignore_index=True)
    df_combined.to_parquet(fact_path)
    print("Cache refresh complete.")


import hashlib
import pickle
import tempfile

from core import _get_panel_hash, get_cached_sleeve_weight


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh-cache", action="store_true")
    ap.add_argument("--backtest", action="store_true")
    ap.add_argument("--cache-dir", default=DEFAULT_CACHE_DIR)
    args = ap.parse_args()

    if args.refresh_cache:
        refresh_valuein_cache(args.cache_dir)

    if args.backtest:
        from cpm_live import load_panel
        from ndx_sleeve_live import load_ndx_panel
        
        print("Loading panels ...")
        cpm_panel = load_panel(start=pd.Timestamp("2000-01-01"))
        ndx_panel = load_ndx_panel()
        
        start = pd.Timestamp("2010-06-01")
        end = min(cpm_panel.index.max(), ndx_panel.index.max())
        print(f"Running backtest {start.date()} -> {end.date()} ...")
        rets, hist = run_value_backtest(cpm_panel, ndx_panel, start, end, cache_dir=args.cache_dir)
        
        eq = (1 + rets).cumprod()
        yrs = len(rets) / 252.0
        cagr = eq.iloc[-1] ** (1 / yrs) - 1
        vol = rets.std() * np.sqrt(252)
        sharpe = (rets.mean() * 252) / vol if vol > 0 else np.nan
        maxdd = (eq / eq.cummax() - 1).min()
        print(f"VAL Sleeve (he5_te0):")
        print(f"  CAGR:   {cagr*100:.2f}%")
        print(f"  Sharpe: {sharpe:.2f}")
        print(f"  MaxDD:  {maxdd*100:.2f}%")
