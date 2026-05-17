#!/usr/bin/env python3
"""
universe_placebo_and_engine_portability.py

Two validation tests on FCP production spec.

TEST 1 — UNIVERSE PERTURBATION / PLACEBO TEST
  N=50 random 15-ETF draws from a 40+ ETF candidate pool.
  Each trial runs the FULL FCP engine (same HOLD_BUFFER=2.5, TOP_K=7,
  vol-target 10%, 10bps/side) on the random universe.
  Start date = live-only (latest inception in that draw).
  Compare distribution vs FCP-15 production Sharpe.

TEST 2 — ENGINE PORTABILITY vs PEER UNIVERSES
  FCP engine applied unchanged to:
    HAA-Balanced, HAA-Simple, VAA-G4, Faber-GTAA5
  Compare resulting Sharpe to literature-reported paper Sharpes
  and to FCP-15 production.

Output:
  strategy_fcp/research/universe_placebo_and_engine_portability.log
"""
from __future__ import annotations

import logging
import random
import sys
import time
import traceback
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

# ── logging ───────────────────────────────────────────────────────────────────
LOG_PATH = Path(__file__).resolve().parent / "universe_placebo_and_engine_portability.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_PATH, mode="w"),
    ],
)
log = logging.getLogger(__name__)

# ── paths / imports ───────────────────────────────────────────────────────────
SCRIPTS_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SCRIPTS_ROOT))

from strategy_fcp.fcp_live import (
    RISKY_UNIVERSE, SAFE_POOL, CANARY_ASSETS, DEFAULT_CASH,
    TOP_K_CANDIDATES, HOLD_BUFFER, CORR_LOOKBACK_DAYS,
    TARGET_VOL, VOL_LOOKBACK_DAYS, MAX_LEVERAGE, COST_BPS_PER_SIDE,
    load_panel, perf_metrics,
    faber_sma_xs, sig_13612W, zscore, best_safe, min_vol_pair,
)

# ── experiment constants ──────────────────────────────────────────────────────
RANDOM_SEED       = 42
N_PLACEBO_TRIALS  = 50
GLOBAL_START      = pd.Timestamp("2001-08-30")
GLOBAL_END        = pd.Timestamp("2026-05-01")
CACHE_DIR         = "/tmp/fcp_cache"
MIN_WINDOW_YEARS  = 3.0   # skip trial if live window < 3y

# Paper Sharpe reference values from published literature.
# Different sample periods, cost assumptions (some zero-cost), data sources.
# Treat as rough directional orientation only.
PAPER_SHARPES = {
    "HAA-Balanced":  1.32,   # Keller & Butler 2023, SSRN
    "HAA-Simple":    1.18,   # Keller & Butler 2023, SSRN
    "VAA-G4":        1.44,   # Keller & Butler 2016, SSRN (no transaction cost)
    "Faber-GTAA5":   0.74,   # Faber 2006 (GTAA), no transaction cost
}

# ── candidate pool for placebo test ──────────────────────────────────────────
# ~40 ETFs: US factors, sectors, international, bonds/diversifiers.
# Excludes FCP-15 production names to keep pools blind to our selection.
CANDIDATE_POOL = [
    # US factors
    "SPYG", "SPYV", "MTUM", "USMV", "IWF", "IWD", "IJR", "IJH",
    "RPV", "RPG", "DGRO", "SCHD", "VIG", "VYM", "DSI",
    # US sector
    "XLI", "XLP", "XLU", "XLY", "XLB", "XLF", "XBI", "ITB", "IYR", "IYW",
    # International
    "EFG", "EFV", "DXJ", "EWJ", "EWG", "EWU", "FXI",
    # Bonds / diversifiers
    "AGG", "LQD", "MBB", "EDV", "TLH", "VTIP", "IAU", "USO",
]

# Peer universes for Test 2.
PEER_UNIVERSES = {
    "HAA-Balanced": {
        "risky":  ["SPY", "IWM", "VEA", "VWO", "VNQ", "DBC", "IEF", "TLT"],
        "safe":   ["BIL", "SHV", "SHY", "IEF"],
        "canary": ["SPY", "TIP"],
    },
    "HAA-Simple": {
        "risky":  ["SPY", "IWM", "VEA", "VWO"],
        "safe":   ["BIL", "SHV", "SHY", "IEF"],
        "canary": ["SPY", "TIP"],
    },
    "VAA-G4": {
        "risky":  ["SPY", "VEA", "EEM", "AGG"],
        "safe":   ["BIL", "SHV", "SHY", "IEF"],
        "canary": ["SPY", "TIP"],
    },
    "Faber-GTAA5": {
        "risky":  ["SPY", "EFA", "IEF", "VNQ", "DBC"],
        "safe":   ["BIL", "SHV", "SHY", "IEF"],
        "canary": ["SPY", "TIP"],
    },
}


# ── parameterized FCP engine ──────────────────────────────────────────────────

def compute_weights_custom(
    close_panel: pd.DataFrame,
    sig_d: pd.Timestamp,
    prev_pair,
    universe: list,
    safe_pool: list,
    canary_assets: list,
    top_k: int = TOP_K_CANDIDATES,
    hold_buffer: float = HOLD_BUFFER,
    corr_lookback: int = CORR_LOOKBACK_DAYS,
):
    """Parameterized version of compute_target_weights."""
    monthly = close_panel.loc[:sig_d].resample("ME").last()
    safe = best_safe(monthly, sig_d, safe_pool)

    canary_scores = []
    for c in canary_assets:
        if c not in monthly.columns:
            continue
        s = sig_13612W(monthly[c])
        if pd.notna(s):
            canary_scores.append(s)
    if not canary_scores:
        return {safe: 1.0}, None, "DEFENSIVE", safe
    n_pos = sum(1 for s in canary_scores if s > 0)
    if n_pos <= len(canary_scores) // 2:
        return {safe: 1.0}, None, "DEFENSIVE", safe

    score = faber_sma_xs(monthly)
    avail = [
        t for t in universe
        if t in score.index
        and pd.notna(score[t])
        and pd.notna(close_panel.loc[sig_d].get(t, np.nan)
                     if sig_d in close_panel.index else np.nan)
    ]
    if not avail:
        return {safe: 1.0}, None, "DEFENSIVE", safe

    sa = score.loc[avail]
    za = zscore(sa)
    ranked = sa.sort_values(ascending=False)
    top_k_eff = max(2, min(top_k, len(ranked)))
    positive = ranked.iloc[:top_k_eff][lambda s: s > 0]

    if len(positive) < 2:
        if len(positive) == 1:
            return {positive.index[0]: 0.5, safe: 0.5}, None, "RISK_ON", safe
        return {safe: 1.0}, None, "DEFENSIVE", safe

    candidates = list(positive.index)
    new_pick = min_vol_pair(close_panel.loc[:sig_d, candidates], candidates, corr_lookback)
    if new_pick is None:
        return {candidates[0]: 1.0}, None, "RISK_ON", safe

    # Hold buffer
    if prev_pair is not None and hold_buffer > 1e-9:
        new_set = list(new_pick)
        for prior in prev_pair:
            if prior in new_set or prior not in avail:
                continue
            if sa.get(prior, -np.inf) <= 0:
                continue
            z_prior = za.get(prior, np.nan)
            if pd.isna(z_prior):
                continue
            swap_cands = [x for x in new_set if x not in prev_pair]
            if not swap_cands:
                continue
            swap = min(swap_cands, key=lambda x: za.get(x, np.inf))
            z_swap = za.get(swap, np.nan)
            if pd.isna(z_swap):
                continue
            if z_swap - z_prior < hold_buffer:
                new_set.remove(swap)
                new_set.append(prior)
        new_pick = tuple(new_set[:2])

    return {new_pick[0]: 0.5, new_pick[1]: 0.5}, new_pick, "RISK_ON", safe


def run_backtest_custom(
    panel: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
    universe: list,
    safe_pool: list,
    canary_assets: list,
    top_k: int = TOP_K_CANDIDATES,
    hold_buffer: float = HOLD_BUFFER,
    apply_vol_target: bool = True,
    cost_bps: float = COST_BPS_PER_SIDE,
) -> pd.Series:
    """
    Fully parameterized FCP backtest. Returns daily return series.
    Same mechanics as production run_fcp_backtest() with configurable
    universe, safe_pool, and canary_assets.
    """
    all_needed = sorted(
        set(universe + safe_pool + canary_assets + [DEFAULT_CASH]) & set(panel.columns)
    )
    close = panel[all_needed]

    monthly_idx = (
        pd.DataFrame({"x": 1}, index=close.index)
        .groupby(pd.Grouper(freq="ME"))
        .tail(1)
    )
    signal_dates = monthly_idx.index[
        (monthly_idx.index >= start) & (monthly_idx.index <= end)
    ].tolist()

    weights_history = []
    prev_pair = None

    for i, sig_d in enumerate(signal_dates):
        w, new_pair, regime, safe = compute_weights_custom(
            close, sig_d, prev_pair,
            universe=universe, safe_pool=safe_pool, canary_assets=canary_assets,
            top_k=top_k, hold_buffer=hold_buffer,
        )
        prev_pair = new_pair
        future = close.index[close.index > sig_d]
        if len(future) < 2:
            continue
        apply_from = future[1]
        if i + 1 < len(signal_dates):
            next_sig = signal_dates[i + 1]
            next_future = close.index[close.index > next_sig]
            end_apply = next_future[1] if len(next_future) >= 2 else end
        else:
            end_apply = end
        weights_history.append({
            "apply_from": apply_from,
            "end_apply":  end_apply,
            "weights":    w,
        })

    all_assets = sorted({a for h in weights_history for a in h["weights"]})
    df_w = pd.DataFrame(
        0.0, index=close.index,
        columns=[a for a in all_assets if a in close.columns],
    )
    for h in weights_history:
        mask = (close.index >= h["apply_from"]) & (close.index < h["end_apply"])
        for a, ww in h["weights"].items():
            if a in df_w.columns:
                df_w.loc[mask, a] = ww

    daily_ret = close.ffill().pct_change()
    common = [a for a in df_w.columns if a in daily_ret.columns]
    raw_returns = (
        df_w[common].multiply(daily_ret[common])
        .sum(axis=1, min_count=1)
        .fillna(0.0)
    )

    # Transaction costs
    for i, h in enumerate(weights_history):
        prev_w = weights_history[i - 1]["weights"] if i > 0 else {}
        curr_w = h["weights"]
        keys = set(curr_w) | set(prev_w)
        turnover = sum(abs(curr_w.get(k, 0.0) - prev_w.get(k, 0.0)) for k in keys)
        cost = turnover * cost_bps / 10_000.0
        af = h["apply_from"]
        if af in raw_returns.index:
            raw_returns.loc[af] -= cost

    # Vol-target overlay
    if apply_vol_target:
        realized = raw_returns.rolling(VOL_LOOKBACK_DAYS).std() * np.sqrt(252)
        scale = (TARGET_VOL / realized).clip(upper=MAX_LEVERAGE).shift(1).fillna(1.0)
        raw_returns = raw_returns * scale

    return raw_returns.loc[(raw_returns.index >= start) & (raw_returns.index <= end)]


# ── data helpers ─────────────────────────────────────────────────────────────

def fetch_extra_etfs(tickers: list, panel: pd.DataFrame) -> pd.DataFrame:
    """Fetch tickers not in panel from yfinance. Log failures."""
    missing = sorted(set(tickers) - set(panel.columns))
    if not missing:
        return panel
    log.info(f"Fetching {len(missing)} tickers from yfinance: {missing}")
    fetched = {}
    failed = []
    for t in missing:
        cache_path = Path(CACHE_DIR) / f"{t}.csv"
        if cache_path.exists():
            try:
                s = pd.read_csv(cache_path, parse_dates=[0], index_col=0).iloc[:, 0]
                s.name = t
                fetched[t] = s
                continue
            except Exception:
                pass
        try:
            d = yf.download(
                t, start="1990-01-01",
                end=GLOBAL_END.strftime("%Y-%m-%d"),
                auto_adjust=True, progress=False, threads=False,
            )
            if isinstance(d.columns, pd.MultiIndex):
                d = d["Close"]
            c = d["Close"] if "Close" in d.columns else d.iloc[:, 0]
            c = c.dropna(); c.name = t
            c.to_csv(cache_path, header=True)
            fetched[t] = c
        except Exception as e:
            log.warning(f"  FAILED {t}: {e}")
            failed.append(t)
        time.sleep(0.1)
    if failed:
        log.warning(f"Could not fetch {len(failed)} tickers: {failed}")
    if fetched:
        extras = pd.DataFrame(fetched)
        panel = panel.join(extras, how="outer").sort_index()
    return panel


def inception_date(panel: pd.DataFrame, ticker: str):
    if ticker not in panel.columns:
        return None
    s = panel[ticker].dropna()
    return s.index[0] if not s.empty else None


# ── TEST 1: Placebo ───────────────────────────────────────────────────────────

def run_placebo_tests(panel: pd.DataFrame) -> pd.DataFrame:
    log.info("=" * 70)
    log.info("TEST 1: UNIVERSE PERTURBATION / PLACEBO TEST")
    log.info("=" * 70)

    available = [t for t in CANDIDATE_POOL if t in panel.columns]
    unavailable = [t for t in CANDIDATE_POOL if t not in panel.columns]
    log.info(f"Candidate pool: {len(CANDIDATE_POOL)} requested")
    log.info(f"  In panel: {len(available)}: {available}")
    if unavailable:
        log.info(f"  NOT available (skipped from pool): {len(unavailable)}: {unavailable}")

    if len(available) < 15:
        log.error("Fewer than 15 candidates available — cannot run placebo.")
        return pd.DataFrame()

    rng = random.Random(RANDOM_SEED)
    results = []
    skipped_count = 0

    log.info(f"\nRunning {N_PLACEBO_TRIALS} placebo trials (seed={RANDOM_SEED}) ...")

    INTL_SET   = {"EFG","EFV","DXJ","EWJ","EWG","EWU","FXI"}
    BOND_SET   = {"AGG","LQD","MBB","EDV","TLH","VTIP","IAU","USO"}
    SECTOR_SET = {"XLI","XLP","XLU","XLY","XLB","XLF","XBI","ITB","IYR","IYW"}
    FACTOR_SET = {"SPYG","SPYV","MTUM","USMV","IWF","IWD","IJR","IJH",
                  "RPV","RPG","DGRO","SCHD","VIG","VYM","DSI"}

    for trial_i in range(N_PLACEBO_TRIALS):
        draw = rng.sample(available, k=min(15, len(available)))

        inceptions = [inception_date(panel, t) for t in draw]
        inceptions_valid = [d for d in inceptions if d is not None]
        if not inceptions_valid:
            skipped_count += 1
            continue
        live_start = max(inceptions_valid)
        effective_start = live_start + pd.DateOffset(months=12)
        window_yrs = (GLOBAL_END - effective_start).days / 365.25

        composition = {
            "n_intl":   sum(1 for t in draw if t in INTL_SET),
            "n_bonds":  sum(1 for t in draw if t in BOND_SET),
            "n_sector": sum(1 for t in draw if t in SECTOR_SET),
            "n_factor": sum(1 for t in draw if t in FACTOR_SET),
        }

        row_base = {
            "trial":      trial_i + 1,
            "universe":   ",".join(draw),
            "live_start": live_start.date() if hasattr(live_start,"date") else live_start,
            "window_yrs": round(window_yrs, 2),
            "skipped":    False,
            **composition,
        }

        if window_yrs < MIN_WINDOW_YEARS:
            log.info(
                f"  Trial {trial_i+1:3d} | SKIPPED (window {window_yrs:.1f}y < {MIN_WINDOW_YEARS}y) "
                f"| start={live_start.date() if hasattr(live_start,'date') else live_start}"
            )
            skipped_count += 1
            results.append({**row_base, "sharpe": np.nan, "cagr": np.nan, "max_dd": np.nan, "skipped": True})
            continue

        try:
            daily = run_backtest_custom(
                panel=panel,
                start=effective_start,
                end=GLOBAL_END,
                universe=draw,
                safe_pool=SAFE_POOL,
                canary_assets=CANARY_ASSETS,
                top_k=TOP_K_CANDIDATES,
                hold_buffer=HOLD_BUFFER,
                apply_vol_target=True,
                cost_bps=COST_BPS_PER_SIDE,
            )
            m = perf_metrics(daily)
            sh = m.get("sharpe", np.nan)
            cg = m.get("cagr", np.nan)
            dd = m.get("max_drawdown", np.nan)
            log.info(
                f"  Trial {trial_i+1:3d} | start={effective_start.date()} "
                f"({window_yrs:.1f}y) | "
                f"Sh={sh:.3f} CAGR={cg*100:.1f}% DD={dd*100:.1f}% | "
                f"{draw}"
            )
            results.append({**row_base, "sharpe": sh, "cagr": cg, "max_dd": dd})
        except Exception as e:
            log.warning(f"  Trial {trial_i+1:3d} | ERROR: {e}")
            skipped_count += 1
            results.append({**row_base, "sharpe": np.nan, "cagr": np.nan, "max_dd": np.nan, "skipped": True})

    log.info(f"\nPlacebo raw: {N_PLACEBO_TRIALS - skipped_count} valid, {skipped_count} skipped/error")
    return pd.DataFrame(results)


def analyze_placebo(df: pd.DataFrame, fcp_sharpe: float) -> None:
    valid = df[~df["skipped"] & df["sharpe"].notna()].copy() if not df.empty else pd.DataFrame()
    if valid.empty:
        log.info("No valid placebo trials.")
        return

    sharpes = valid["sharpe"].values
    median_sh = np.nanmedian(sharpes)
    mean_sh   = np.nanmean(sharpes)
    p10 = np.nanpercentile(sharpes, 10)
    p25 = np.nanpercentile(sharpes, 25)
    p75 = np.nanpercentile(sharpes, 75)
    p90 = np.nanpercentile(sharpes, 90)
    pct_beat  = (sharpes >= fcp_sharpe).mean() * 100
    fcp_pctile = np.mean(sharpes <= fcp_sharpe) * 100

    log.info("\n" + "─" * 70)
    log.info("PLACEBO DISTRIBUTION ANALYSIS")
    log.info("─" * 70)
    log.info(f"  FCP-15 production Sharpe:       {fcp_sharpe:.3f}")
    log.info(f"  Placebo count (valid):           {len(valid)}")
    log.info(f"  Placebo Sharpe mean:             {mean_sh:.3f}")
    log.info(f"  Placebo Sharpe median:           {median_sh:.3f}")
    log.info(f"  Placebo Sharpe p10 / p25:        {p10:.3f} / {p25:.3f}")
    log.info(f"  Placebo Sharpe p75 / p90:        {p75:.3f} / {p90:.3f}")
    log.info(f"  % placebos beating FCP-15:       {pct_beat:.1f}%")
    log.info(f"  FCP-15 percentile vs placebos:   {fcp_pctile:.1f}th")

    if pct_beat < 10 and fcp_pctile > 85:
        verdict = "RARE-GOOD: FCP-15 top decile. Universe selection likely captures real edge."
    elif pct_beat < 25:
        verdict = "ABOVE-AVERAGE: FCP-15 top quartile. Some universe selection value."
    elif pct_beat < 50:
        verdict = "MIDDLING: FCP-15 slightly above median. Weak universe-selection evidence."
    else:
        verdict = "NO EDGE: Majority of random pools match/beat FCP-15. Universe selection marginal."
    log.info(f"\n  VERDICT: {verdict}")

    # Composition stratification
    log.info("\n  Stratified averages by universe composition:")
    for col, label in [
        ("n_bonds",  "bonds in draw"),
        ("n_intl",   "intl in draw"),
        ("n_sector", "sectors in draw"),
        ("n_factor", "factors in draw"),
    ]:
        if col not in valid.columns:
            continue
        g = valid.groupby(col)["sharpe"].agg(["mean","count"]).reset_index()
        for _, row in g.iterrows():
            log.info(f"    {label}={int(row[col])}: avg_Sh={row['mean']:.3f} n={int(row['count'])}")


# ── TEST 2: Engine portability ────────────────────────────────────────────────

def run_engine_portability(panel: pd.DataFrame, fcp_sharpe: float) -> pd.DataFrame:
    log.info("\n" + "=" * 70)
    log.info("TEST 2: ENGINE PORTABILITY vs PEER UNIVERSES")
    log.info("=" * 70)

    results = []

    for name, spec in PEER_UNIVERSES.items():
        risky  = spec["risky"]
        safe   = spec["safe"]
        canary = spec["canary"]

        # Resolve AGG -> AGG_stitched if needed
        risky_r = []
        for t in risky:
            if t not in panel.columns and f"{t}_stitched" in panel.columns:
                risky_r.append(f"{t}_stitched")
                log.info(f"  {name}: {t} -> {t}_stitched (proxy)")
            else:
                risky_r.append(t)

        missing = [t for t in risky_r + safe + canary if t not in panel.columns]
        if missing:
            log.warning(f"  {name}: missing {missing} — SKIPPED")
            results.append({
                "universe": name, "sharpe": np.nan, "cagr": np.nan,
                "max_dd": np.nan, "window_yrs": np.nan,
                "paper_sharpe": PAPER_SHARPES.get(name, np.nan),
                "delta_vs_paper": np.nan, "skipped": True,
            })
            continue

        inceptions = [inception_date(panel, t) for t in risky_r + canary]
        inceptions = [d for d in inceptions if d is not None]
        if not inceptions:
            log.warning(f"  {name}: no inception dates — SKIPPED")
            continue
        live_start = max(inceptions)
        effective_start = max(live_start + pd.DateOffset(months=12), GLOBAL_START)
        window_yrs = (GLOBAL_END - effective_start).days / 365.25

        log.info(f"\n  {name}: start={effective_start.date()} ({window_yrs:.1f}y) risky={risky_r}")
        try:
            daily = run_backtest_custom(
                panel=panel,
                start=effective_start,
                end=GLOBAL_END,
                universe=risky_r,
                safe_pool=[t for t in safe if t in panel.columns],
                canary_assets=[t for t in canary if t in panel.columns],
                top_k=TOP_K_CANDIDATES,
                hold_buffer=HOLD_BUFFER,
                apply_vol_target=True,
                cost_bps=COST_BPS_PER_SIDE,
            )
            m = perf_metrics(daily)
            eng_sh   = m.get("sharpe", np.nan)
            paper_sh = PAPER_SHARPES.get(name, np.nan)
            delta    = (eng_sh - paper_sh) if (pd.notna(eng_sh) and pd.notna(paper_sh)) else np.nan
            log.info(
                f"    FCP-engine Sh={eng_sh:.3f}  CAGR={m.get('cagr',np.nan)*100:.1f}%  "
                f"DD={m.get('max_drawdown',np.nan)*100:.1f}%  |  "
                f"paper_Sh={paper_sh:.2f}  delta={delta:+.3f}"
            )
            results.append({
                "universe":      name,
                "sharpe":        eng_sh,
                "cagr":          m.get("cagr", np.nan),
                "max_dd":        m.get("max_drawdown", np.nan),
                "window_yrs":    round(window_yrs, 2),
                "paper_sharpe":  paper_sh,
                "delta_vs_paper": delta,
                "skipped":       False,
            })
        except Exception as e:
            log.error(f"  {name}: ERROR — {e}")
            traceback.print_exc()
            results.append({
                "universe": name, "sharpe": np.nan, "cagr": np.nan,
                "max_dd": np.nan, "window_yrs": np.nan,
                "paper_sharpe": PAPER_SHARPES.get(name, np.nan),
                "delta_vs_paper": np.nan, "skipped": True,
            })

    return pd.DataFrame(results)


def interpret_portability(df: pd.DataFrame, fcp_sharpe: float) -> None:
    log.info("\n" + "─" * 70)
    log.info("ENGINE PORTABILITY SUMMARY TABLE")
    log.info("─" * 70)
    log.info(f"  {'Universe':20s} {'EngSh':>7s} {'PaperSh':>8s} {'DeltaPaper':>11s} {'DeltaFCP15':>11s} {'Window':>7s}")
    log.info("  " + "-" * 66)
    for _, row in df.iterrows():
        if row.get("skipped"):
            log.info(f"  {row['universe']:20s}  SKIPPED")
            continue
        d_paper = row.get("delta_vs_paper", np.nan)
        d_fcp   = (row["sharpe"] - fcp_sharpe) if pd.notna(row["sharpe"]) else np.nan
        log.info(
            f"  {row['universe']:20s} "
            f"{row['sharpe']:7.3f} "
            f"{row['paper_sharpe']:8.2f} "
            f"{d_paper:+11.3f} "
            f"{d_fcp:+11.3f} "
            f"{row['window_yrs']:6.1f}y"
        )

    valid = df[~df.get("skipped", False) & df["sharpe"].notna()] if not df.empty else pd.DataFrame()
    if valid.empty:
        return

    pos = valid[valid["delta_vs_paper"].notna() & (valid["delta_vs_paper"] > 0)]
    neg = valid[valid["delta_vs_paper"].notna() & (valid["delta_vs_paper"] <= 0)]

    log.info(f"\n  Universes where FCP engine BEATS paper Sharpe: {len(pos)}/{len(valid)}")
    for _, r in pos.iterrows():
        log.info(f"    {r['universe']}: FCP-engine={r['sharpe']:.3f} vs paper={r['paper_sharpe']:.2f} (+{r['delta_vs_paper']:.3f})")
    log.info(f"  Universes where FCP engine TRAILS paper Sharpe: {len(neg)}/{len(valid)}")
    for _, r in neg.iterrows():
        log.info(f"    {r['universe']}: FCP-engine={r['sharpe']:.3f} vs paper={r['paper_sharpe']:.2f} ({r['delta_vs_paper']:.3f})")

    avg_delta = valid["delta_vs_paper"].mean()
    log.info(f"\n  Mean delta (FCP engine vs paper): {avg_delta:+.3f}")

    all_below_fcp = (valid["sharpe"] < fcp_sharpe).all()
    any_near_fcp  = (valid["sharpe"] >= fcp_sharpe * 0.90).any()

    if all_below_fcp and not any_near_fcp:
        log.info(
            "\n  INTERPRETATION: FCP engine on peer universes consistently underperforms FCP-15."
            "\n  Universe is doing substantial work, not engine mechanics alone."
            "\n  Engine portability: LIMITED."
        )
    elif all_below_fcp and any_near_fcp:
        log.info(
            "\n  INTERPRETATION: FCP engine reaches 90%+ of FCP-15 Sharpe on >=1 peer universe."
            "\n  Engine has portable alpha. Both universe + engine contribute."
        )
    else:
        log.info(
            "\n  INTERPRETATION: FCP engine matches/exceeds FCP-15 on >=1 peer universe."
            "\n  Engine is portable. Universe selection may not be primary driver."
        )

    log.info(
        "\n  CAVEAT: Paper Sharpes from published literature. Different sample windows,"
        "\n  cost assumptions (some zero-cost), data sources. Delta estimates directional only."
    )


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    log.info("universe_placebo_and_engine_portability.py — START")
    log.info(f"FCP-15 universe: {RISKY_UNIVERSE}")
    log.info(
        f"Engine: TOP_K={TOP_K_CANDIDATES}, HOLD_BUFFER={HOLD_BUFFER}, "
        f"VOL_TARGET={TARGET_VOL:.0%}, COST={COST_BPS_PER_SIDE}bps/side"
    )

    # 1. Load base panel
    log.info("\nLoading base panel ...")
    panel = load_panel(start=pd.Timestamp("1995-01-01"), end=GLOBAL_END, cache_dir=CACHE_DIR)
    log.info(f"Base panel: {panel.index[0].date()} -> {panel.index[-1].date()}, {len(panel.columns)} cols")

    # 2. Fetch additional ETFs
    all_extra = list(
        set(CANDIDATE_POOL)
        | {t for spec in PEER_UNIVERSES.values() for t in spec["risky"] + spec["safe"] + spec["canary"]}
    )
    panel = fetch_extra_etfs(all_extra, panel)
    log.info(f"Augmented panel: {len(panel.columns)} cols")

    # 3. FCP-15 baseline
    log.info("\nRunning FCP-15 production baseline ...")
    from strategy_fcp.fcp_live import run_fcp_backtest
    fcp_daily, _ = run_fcp_backtest(
        panel=panel, start=GLOBAL_START, end=GLOBAL_END,
        apply_vol_target=True, cost_bps=COST_BPS_PER_SIDE,
    )
    fcp_m = perf_metrics(fcp_daily)
    fcp_sharpe = fcp_m.get("sharpe", np.nan)
    log.info(
        f"FCP-15: Sh={fcp_sharpe:.3f}  CAGR={fcp_m.get('cagr',np.nan)*100:.2f}%  "
        f"DD={fcp_m.get('max_drawdown',np.nan)*100:.2f}%  "
        f"[{GLOBAL_START.date()} -> {GLOBAL_END.date()}]"
    )

    # 4. Placebo test
    placebo_df = run_placebo_tests(panel)
    analyze_placebo(placebo_df, fcp_sharpe)

    # 5. Engine portability
    portability_df = run_engine_portability(panel, fcp_sharpe)
    interpret_portability(portability_df, fcp_sharpe)

    # 6. Save CSV artifacts
    out_dir = Path(__file__).parent
    if not placebo_df.empty:
        p = out_dir / "universe_placebo_results.csv"
        placebo_df.to_csv(p, index=False)
        log.info(f"\nPlacebo CSV: {p}")
    if not portability_df.empty:
        p2 = out_dir / "engine_portability_results.csv"
        portability_df.to_csv(p2, index=False)
        log.info(f"Portability CSV: {p2}")

    log.info("\nuniverse_placebo_and_engine_portability.py — DONE")
    log.info(f"Log: {LOG_PATH}")


if __name__ == "__main__":
    main()
