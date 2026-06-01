#!/usr/bin/env python3
"""
Memo review-2 robustness harness: A1 (vol-lookback standardization) + A2 (US-equity de-tilt).

Reuses production CPM engine (cpm_live.compute_target_weights) and the mooex T+1 MOO
harness (exec_lag_moo_validation_2026_05_30._segment_returns_conv / load_open_close).

A1: rank-vol vs weight-vol lookback (prod = rank 252 / weight 504).
    - both-252: rank tail(252) std, inverse-vol weight lookback=252
    - both-504: rank tail(504) std, inverse-vol weight lookback=504
    - prod:     rank tail(252) std, inverse-vol weight lookback=504

A2: replace US-factor block (QQQ, SPHQ) with de-tilted equity.
    - PRIMARY: both QQQ+SPHQ -> single SPY (broad US equity, no tech/quality tilt)
    - SECONDARY: single-ticker growth-engine swaps (VUG/IWF/QUAL/MTUM/IWD)

NOTE: research only. Does NOT edit memo/prod. Does NOT commit.
Windows: clean 2008-05-30..2026-05-22; ext (robustness) 1999-03-10..2026-05-22.
For late-inception swap tickers, effective start = max(clean_start, first_valid + 400 cal days).
"""
from __future__ import annotations
import sys, json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

# bull_spy_live no longer exposes _vol_gate_ok; shim so H imports (we never use BULL here).
import bull_spy_live as _bq
if not hasattr(_bq, "_vol_gate_ok"):
    _bq._vol_gate_ok = lambda *a, **k: (True, {})

import exec_lag_moo_validation_2026_05_30 as H
from cpm_live import (
    load_panel, perf_metrics, compute_target_weights,
    faber_sma_xs, best_safe, sig_13612U, inv_vol_weights,
    RISKY_UNIVERSE, SAFE_POOL, CANARY_ASSETS, DEFAULT_CASH,
    CANARY_RULE, TOP_K_CANDIDATES, COST_BPS_PER_SIDE,
)

CLEAN_START = pd.Timestamp("2008-05-30")
EXT_START   = pd.Timestamp("1999-03-10")
END         = pd.Timestamp("2026-05-22")
SWAP_OHLC   = Path("/tmp/cpm_swap_ohlc")

ANCHOR = {"sharpe": 1.1910, "maxdd": -0.1267, "calmar": 1.0615}


# ---------------------------------------------------------------------------
# Parametrized CPM weight function (faithful copy of compute_target_weights,
# exposing rank-vol lookback and weight-vol lookback as parameters).
# ---------------------------------------------------------------------------
def cpm_weights_param(close_panel, sig_d, universe, rank_lb, weight_lb,
                      safe_pool=None, canary_assets=None):
    safe_pool = safe_pool or SAFE_POOL
    canary_assets = canary_assets or CANARY_ASSETS

    monthly = close_panel.loc[:sig_d].resample("ME").last()
    safe = best_safe(monthly, sig_d, safe_pool)

    canary_scores = []
    for c in canary_assets:
        if c not in monthly.columns:
            continue
        s = sig_13612U(monthly[c])
        if pd.notna(s):
            canary_scores.append(s)
    if not canary_scores:
        return {safe: 1.0}
    n_pos = sum(1 for s in canary_scores if s > 0)
    if CANARY_RULE == "any_positive":
        if n_pos == 0:
            return {safe: 1.0}
    elif CANARY_RULE == "all_positive":
        if n_pos < len(canary_scores):
            return {safe: 1.0}
    else:
        if n_pos <= len(canary_scores) // 2:
            return {safe: 1.0}

    faber = faber_sma_xs(monthly)
    avail = [t for t in universe
             if t in faber.index and pd.notna(faber[t])
             and pd.notna(close_panel.loc[sig_d].get(t, np.nan) if sig_d in close_panel.index else np.nan)]
    if not avail:
        return {safe: 1.0}

    daily_rets = close_panel[avail].ffill().pct_change()
    scores = {}
    for t in avail:
        v = daily_rets[t].loc[:sig_d].tail(rank_lb).std() * np.sqrt(252)
        if pd.isna(v) or v < 1e-9:
            v = 1.0
        scores[t] = float(faber[t]) / v
    sa = pd.Series(scores)
    ranked = sa.sort_values(ascending=False)
    top_k = max(2, min(TOP_K_CANDIDATES, len(ranked)))
    top = ranked.iloc[:top_k]
    positive = top[top.index.map(lambda t: faber.get(t, -np.inf) > 0)]
    if len(positive) == 0:
        return {safe: 1.0}

    picks = list(positive.index)
    n_picks = len(picks)
    risky_fraction = min(n_picks, 4) / 4.0
    safe_fraction = 1.0 - risky_fraction

    csub = close_panel.loc[:sig_d]
    risky_w = inv_vol_weights(csub, picks, weight_lb)
    out = {t: w * risky_fraction for t, w in risky_w.items()}
    if safe_fraction > 0:
        out[safe] = out.get(safe, 0.0) + safe_fraction
    return out


# ---------------------------------------------------------------------------
# Data plumbing
# ---------------------------------------------------------------------------
def build_panel_and_exec(swap_tickers):
    """Base proxy panel + swap-ticker adjusted-close columns; plus intraday/overnight
    return frames (real OHLC where available, else cc fallback inside _segment_returns_conv)."""
    panel = load_panel(start=EXT_START, end=END)
    open_df, close_yf = H.load_open_close()

    swap_open, swap_close = {}, {}
    for t in swap_tickers:
        p = SWAP_OHLC / f"{t}.csv"
        if not p.exists():
            continue
        d = pd.read_csv(p, parse_dates=[0], index_col=0)
        swap_open[t] = d["Open"]; swap_close[t] = d["Close"]
        if t not in panel.columns:
            panel = panel.join(d["Close"].rename(t), how="outer").sort_index()
    panel = panel.loc[panel.index <= END]

    for t in swap_open:
        open_df = open_df.reindex(open_df.index.union(swap_open[t].index))
        close_yf = close_yf.reindex(close_yf.index.union(swap_close[t].index))
        open_df[t] = swap_open[t].reindex(open_df.index)
        close_yf[t] = swap_close[t].reindex(close_yf.index)
    open_df = open_df.sort_index(); close_yf = close_yf.sort_index()

    intraday = (close_yf / open_df - 1.0).reindex(panel.index)
    overnight = (open_df / close_yf.shift(1) - 1.0).reindex(panel.index)
    return panel, intraday, overnight


def run_cpm(panel, intraday, overnight, universe, rank_lb, weight_lb, start, end):
    needed = sorted(set(universe + SAFE_POOL + CANARY_ASSETS + [DEFAULT_CASH]) & set(panel.columns))
    close = panel[needed]
    daily_ret = close.ffill().pct_change()
    wf = lambda sd: cpm_weights_param(close, sd, universe, rank_lb, weight_lb)
    ret, diag = H._segment_returns_conv(close, daily_ret, wf, start, end, "mooex",
                                        COST_BPS_PER_SIDE, intraday, overnight)
    return ret, diag


def met(daily, cash):
    m = perf_metrics(daily, cash)
    return {"sharpe": m.get("sharpe"), "cagr": m.get("cagr"),
            "maxdd": m.get("max_drawdown"), "calmar": m.get("calmar"),
            "martin": m.get("martin"), "vol": m.get("vol")}


def win(s, a, b):
    return s.loc[(s.index >= a) & (s.index <= b)]


def eff_start(panel, universe, base_start):
    """Effective start: latest of base_start and (first_valid + 400 cal days) over swap tickers
    that are NOT in the base proxy panel history pre-base_start."""
    es = base_start
    for t in universe:
        if t not in panel.columns:
            continue
        fv = panel[t].first_valid_index()
        if fv is None:
            continue
        cand = fv + pd.Timedelta(days=400)
        if cand > es:
            es = cand
    return es


def main():
    out = {"anchor_target": ANCHOR, "results": {}}
    base_panel, base_intra, base_over = build_panel_and_exec([])
    cash = base_panel["SHV"].ffill().pct_change().dropna()
    end = min(END, base_panel.index[-1])

    # ---- ANCHOR REPRODUCTION (production engine, prod universe, rank252/weight504) ----
    cpm_prod, dgp = run_cpm(base_panel, base_intra, base_over, list(RISKY_UNIVERSE),
                            252, 504, EXT_START, end)
    a_clean = met(win(cpm_prod, CLEAN_START, end), cash)
    a_ext = met(win(cpm_prod, EXT_START, end), cash)
    out["anchor_repro"] = {"clean": a_clean, "ext": a_ext, "mooex": dgp}
    ok = (abs(a_clean["sharpe"] - 1.1910) < 1e-3 and abs(a_clean["maxdd"] + 0.1267) < 1e-3
          and abs(a_clean["calmar"] - 1.0615) < 1e-3)
    out["anchor_ok"] = bool(ok)
    print(f"[ANCHOR] clean Sharpe={a_clean['sharpe']:.4f} MaxDD={a_clean['maxdd']*100:.2f}% "
          f"Calmar={a_clean['calmar']:.4f} Martin={a_clean['martin']:.4f}  OK={ok}")
    assert ok, "ANCHOR MISMATCH -- abort"

    # =================== A1: VOL-LOOKBACK STANDARDIZATION ===================
    a1_cfgs = {
        "prod (rank252/wt504)": (252, 504),
        "both-252 (rank252/wt252)": (252, 252),
        "both-504 (rank504/wt504)": (504, 504),
    }
    a1 = {}
    for name, (rl, wl) in a1_cfgs.items():
        ret, dg = run_cpm(base_panel, base_intra, base_over, list(RISKY_UNIVERSE),
                          rl, wl, EXT_START, end)
        a1[name] = {"clean": met(win(ret, CLEAN_START, end), cash),
                    "ext": met(win(ret, EXT_START, end), cash), "mooex": dg}
        print(f"[A1] {name:28s} clean Sh={a1[name]['clean']['sharpe']:.4f} "
              f"DD={a1[name]['clean']['maxdd']*100:.2f}% Cal={a1[name]['clean']['calmar']:.3f} "
              f"Mar={a1[name]['clean']['martin']:.3f}")
    out["results"]["A1"] = a1

    # =================== A2: US-EQUITY DE-TILT ===================
    # PRIMARY: QQQ+SPHQ -> single SPY
    spy_univ = ["SPY", "EFA", "EEM", "VNQ", "GLD", "TLT", "DBC"]
    panel_spy, intra_spy, over_spy = build_panel_and_exec(["SPY"])
    cash_spy = panel_spy["SHV"].ffill().pct_change().dropna()
    end_spy = min(END, panel_spy.index[-1])
    ret_spy, dg_spy = run_cpm(panel_spy, intra_spy, over_spy, spy_univ, 252, 504, EXT_START, end_spy)
    a2_primary = {"universe": spy_univ,
                  "clean": met(win(ret_spy, CLEAN_START, end_spy), cash_spy),
                  "ext": met(win(ret_spy, EXT_START, end_spy), cash_spy),
                  "mooex": dg_spy}
    out["results"]["A2_primary_SPY"] = a2_primary
    print(f"[A2-PRIMARY SPY] clean Sh={a2_primary['clean']['sharpe']:.4f} "
          f"DD={a2_primary['clean']['maxdd']*100:.2f}% Cal={a2_primary['clean']['calmar']:.3f} "
          f"Mar={a2_primary['clean']['martin']:.3f}")

    # SECONDARY: single-ticker growth-engine swaps
    sec_cfgs = {
        "QQQ->VUG":  ["VUG", "SPHQ", "EFA", "EEM", "VNQ", "GLD", "TLT", "DBC"],
        "QQQ->IWF":  ["IWF", "SPHQ", "EFA", "EEM", "VNQ", "GLD", "TLT", "DBC"],
        "SPHQ->QUAL":["QQQ", "QUAL", "EFA", "EEM", "VNQ", "GLD", "TLT", "DBC"],
        "SPHQ->MTUM":["QQQ", "MTUM", "EFA", "EEM", "VNQ", "GLD", "TLT", "DBC"],
        "QQQ->IWD (cyclical/value)": ["IWD", "SPHQ", "EFA", "EEM", "VNQ", "GLD", "TLT", "DBC"],
    }
    a2_sec = {}
    for name, univ in sec_cfgs.items():
        swaps = [t for t in univ if t not in RISKY_UNIVERSE]
        pnl, intra, over = build_panel_and_exec(swaps)
        csh = pnl["SHV"].ffill().pct_change().dropna()
        e = min(END, pnl.index[-1])
        es = eff_start(pnl, univ, CLEAN_START)
        ret, dg = run_cpm(pnl, intra, over, univ, 252, 504, es, e)
        a2_sec[name] = {"universe": univ, "eff_start": str(es.date()),
                        "clean_like": met(win(ret, es, e), csh), "mooex": dg}
        print(f"[A2-SEC] {name:28s} start={es.date()} Sh={a2_sec[name]['clean_like']['sharpe']:.4f} "
              f"DD={a2_sec[name]['clean_like']['maxdd']*100:.2f}% Cal={a2_sec[name]['clean_like']['calmar']:.3f}")
    out["results"]["A2_secondary"] = a2_sec

    # Re-run prod restricted to each secondary's effective start (apples-to-apples baseline)
    a2_baselines = {}
    for name, cfg in a2_sec.items():
        es = pd.Timestamp(cfg["eff_start"])
        b = met(win(cpm_prod, es, end), cash)
        a2_baselines[name] = b
    out["results"]["A2_secondary_prod_baselines"] = a2_baselines

    outp = Path(__file__).resolve().parent / "memo_review2_A1_A2_findings.json"
    outp.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nWrote {outp}")
    return out


if __name__ == "__main__":
    main()
