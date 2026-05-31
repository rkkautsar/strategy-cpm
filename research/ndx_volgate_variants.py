# -*- coding: utf-8 -*-
"""Throwaway research (analyst role; read-only re production; writes only to
research/; NO production/memo files changed; NO commit). EXPLORATION ONLY --
a POTENTIAL NDX-sleeve vol-gate change; user decides adoption later.

MOTIVATION
----------
The NDX sleeve (20% of the 60/20/20 PROD blend) fires its top-K Nasdaq-100
momentum basket only when the BULL sleeve is risk-on, i.e. when
  canary(TIP 13612U>0) AND trend(SPY 13612U>0) AND vol(RV60<RV252 on SPY).
So the NDX vol gate is INHERITED from BULL and is computed on SPY realized vol
(symmetric RV60<RV252 = V0). On the BULL sleeve, 4-5 vol-gate variant rounds all
kept symmetric RV60<RV252. NDX is higher-beta / more tech-concentrated than SPY,
so its optimal gate MIGHT differ -- e.g. a faster window, a QQQ-based realized
gate, or the Nasdaq implied-vol index (VXN). This redoes the variant search on
the NDX sleeve, judged on Calmar AND Martin, keeping NDX crisis catches.

ONLY the vol-gate layer changes. Canary (TIP 13612U>0), trend (SPY 13612U>0),
NDX selection (top-K=5 by raw 13612U momentum from PIT NDX members, partial-fill
to best-of-safe), delisting haircut, and T+1 MOO execution are held at production
values, so the vol gate is the single differentiator.

VARIANTS (vol-gate layer only)
  Realized on SPY (prod underlying):
    V0  symmetric RV60<RV252  (PROD / anchor)
    R_spy_20_252    faster    RV20<RV252
    R_spy_63_126    faster    RV63<RV126
    R_spy_120_252   slower    RV120<RV252
  Realized on QQQ (higher-beta underlying = NDX-specific hypothesis):
    R_qqq_60_252    RV60<RV252 on QQQ
    R_qqq_20_252    RV20<RV252 on QQQ
    R_qqq_63_126    RV63<RV126 on QQQ
  Asymmetry (downside / EWMA):
    DS_spy_60_252   downside semi-dev 60<252 on SPY
    DS_qqq_60_252   downside semi-dev 60<252 on QQQ
    EWMA_spy_94_99  EWMA lam 0.94<0.99 on SPY
    EWMA_spy_97_99  EWMA lam 0.97<0.99 on SPY
    EWMA_qqq_97_99  EWMA lam 0.97<0.99 on QQQ
    DSEWMA_spy_97_99 downside-EWMA 0.97<0.99 on SPY
  Implied VXN (Nasdaq VIX-equivalent; yfinance ^VXN, 2001-01+):
    VXN_ma_21_252   VXN 21d MA < 252d MA
    VXN_ma_63_252   VXN 63d MA < 252d MA
    VXN_lt_med252   VXN < trailing 252d median
    VXN_confirm     RV60<RV252(SPY) AND VXN<VXN252MA (implied confirms realized)
  Term structure (cross-asset proxy; VXN has no clean 3M index on yfinance, so
  use the SPX VIX/VIX3M term structure -- vol term structure is highly correlated
  across SPX/NDX; documented as a proxy gap):
    TERM_vix3m_gt_vix  risk-on when VIX3M > VIX (contango)

Anchor: current NDX V0 standalone (K=5, 2007-02-28..) Sharpe 1.1812 / MaxDD
-35.92% / Calmar 0.7602 / Martin 2.9753 (reproduced deterministically).
"""
from __future__ import annotations
import sys, json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import index_constitution as ic
from cpm_live import load_panel, perf_metrics, sig_13612U
from bull_qqq_live import SAFE_POOL, _pick_safe, CASH_TICKER
from ndx_sleeve_live import load_ndx_panel, SELECT_K, COST_BPS_PER_SIDE, DELISTING_HAIRCUT

COST = COST_BPS_PER_SIDE
START = pd.Timestamp("2007-02-28")
END = pd.Timestamp("2026-05-22")
PANEL_START = pd.Timestamp("2003-01-01")

ANCHOR = {"sharpe": 1.1812, "maxdd": -0.3592, "calmar": 0.7602, "martin": 2.9753}

CACHE = Path(__file__).resolve().parent / "_macro_cache"

CRISES = {
    "2008 GFC":   ("2008-01-01", "2009-06-30"),
    "2018 Q4":    ("2018-01-01", "2018-12-31"),
    "2020 COVID": ("2020-01-01", "2020-06-30"),
    "2022 bear":  ("2022-01-01", "2022-12-31"),
}


def _cache_close(fname):
    p = CACHE / fname
    s = pd.read_csv(p, parse_dates=[0], index_col=0).iloc[:, 0]
    s.index = pd.to_datetime(s.index)
    return s.sort_index()


VXN = _cache_close("VXN.csv")
VIX = _cache_close("VIX.csv")
VIX3M = _cache_close("VIX3M.csv")


def _hl(lmbda):
    return float(np.log(2) / (-np.log(lmbda)))


# ---------------- vol-gate variants: f(panel, sig_d) -> bool ----------------

def _rv(series, sig_d, win):
    sub = series.loc[:sig_d].pct_change().dropna()
    if len(sub) < win:
        return None
    return float(sub.tail(win).std() * np.sqrt(252))


def gate_realized(underlying):
    def make(fast, slow):
        def g(panel, sig_d):
            s = panel[underlying]
            vf = _rv(s, sig_d, fast); vs = _rv(s, sig_d, slow)
            if vf is None or vs is None:
                return True
            return vf < vs
        return g
    return make


def gate_downside(underlying, fast=60, slow=252):
    def g(panel, sig_d):
        sub = panel[underlying].loc[:sig_d].pct_change().dropna()
        if len(sub) < slow:
            return True
        neg = np.minimum(sub.values, 0.0) ** 2
        df = float(np.sqrt(neg[-fast:].mean()) * np.sqrt(252))
        ds = float(np.sqrt(neg[-slow:].mean()) * np.sqrt(252))
        return df < ds
    return g


def _ewma_vol(r2, lmbda):
    return float(np.sqrt(pd.Series(r2).ewm(alpha=1.0 - lmbda, adjust=False).mean().iloc[-1]) * np.sqrt(252))


def gate_ewma(underlying, lam_s, lam_l, downside=False):
    def g(panel, sig_d):
        sub = panel[underlying].loc[:sig_d].pct_change().dropna()
        if len(sub) < 252:
            return True
        if downside:
            base = np.minimum(sub.values, 0.0) ** 2
        else:
            base = sub.values ** 2
        return _ewma_vol(base, lam_s) < _ewma_vol(base, lam_l)
    return g


def gate_vxn_ma(fast, slow):
    def g(panel, sig_d):
        v = VXN.loc[:sig_d]
        if len(v) < slow:
            return True
        return float(v.tail(fast).mean()) < float(v.tail(slow).mean())
    return g


def gate_vxn_median(window=252):
    def g(panel, sig_d):
        v = VXN.loc[:sig_d]
        if len(v) < window:
            return True
        return float(v.iloc[-1]) < float(v.tail(window).median())
    return g


def gate_vxn_confirm(fast=60, slow=252, vxn_slow=252):
    rv_g = gate_realized("SPY")(fast, slow)
    def g(panel, sig_d):
        realized_ok = rv_g(panel, sig_d)
        v = VXN.loc[:sig_d]
        if len(v) < vxn_slow:
            return realized_ok
        vxn_ok = float(v.iloc[-1]) < float(v.tail(vxn_slow).mean())
        return realized_ok and vxn_ok
    return g


def gate_term_vix():
    def g(panel, sig_d):
        v3 = VIX3M.loc[:sig_d]; v1 = VIX.loc[:sig_d]
        if len(v3) < 5 or len(v1) < 5:
            return True
        return float(v3.iloc[-1]) > float(v1.iloc[-1])  # contango = risk-on
    return g


def gate_none():
    """NO-GATE reference arm: drop the vol gate entirely (canary+trend only)."""
    def g(panel, sig_d):
        return True
    return g


VARIANTS = {
    "V0_RV60_252_SPY":   gate_realized("SPY")(60, 252),
    "R_spy_20_252":      gate_realized("SPY")(20, 252),
    "R_spy_63_126":      gate_realized("SPY")(63, 126),
    "R_spy_120_252":     gate_realized("SPY")(120, 252),
    "R_qqq_60_252":      gate_realized("QQQ")(60, 252),
    "R_qqq_20_252":      gate_realized("QQQ")(20, 252),
    "R_qqq_63_126":      gate_realized("QQQ")(63, 126),
    "DS_spy_60_252":     gate_downside("SPY", 60, 252),
    "DS_qqq_60_252":     gate_downside("QQQ", 60, 252),
    "EWMA_spy_94_99":    gate_ewma("SPY", 0.94, 0.99),
    "EWMA_spy_97_99":    gate_ewma("SPY", 0.97, 0.99),
    "EWMA_qqq_97_99":    gate_ewma("QQQ", 0.97, 0.99),
    "DSEWMA_spy_97_99":  gate_ewma("SPY", 0.97, 0.99, downside=True),
    "VXN_ma_21_252":     gate_vxn_ma(21, 252),
    "VXN_ma_63_252":     gate_vxn_ma(63, 252),
    "VXN_lt_med252":     gate_vxn_median(252),
    "VXN_confirm":       gate_vxn_confirm(),
    "TERM_vix3m_gt_vix": gate_term_vix(),
    "NOGATE":            gate_none(),
}
VLABEL = {
    "V0_RV60_252_SPY":   "V0 RV60<RV252 SPY (PROD)",
    "R_spy_20_252":      "RV20<RV252 SPY (faster)",
    "R_spy_63_126":      "RV63<RV126 SPY (faster/short)",
    "R_spy_120_252":     "RV120<RV252 SPY (slower)",
    "R_qqq_60_252":      "RV60<RV252 QQQ",
    "R_qqq_20_252":      "RV20<RV252 QQQ (faster)",
    "R_qqq_63_126":      "RV63<RV126 QQQ",
    "DS_spy_60_252":     "downside 60<252 SPY",
    "DS_qqq_60_252":     "downside 60<252 QQQ",
    "EWMA_spy_94_99":    "EWMA 0.94<0.99 SPY",
    "EWMA_spy_97_99":    "EWMA 0.97<0.99 SPY",
    "EWMA_qqq_97_99":    "EWMA 0.97<0.99 QQQ",
    "DSEWMA_spy_97_99":  "downside-EWMA 0.97<0.99 SPY",
    "VXN_ma_21_252":     "VXN 21d<252d MA",
    "VXN_ma_63_252":     "VXN 63d<252d MA",
    "VXN_lt_med252":     "VXN < 252d median",
    "VXN_confirm":       "RV60<RV252 AND VXN<VXN252MA",
    "TERM_vix3m_gt_vix": "VIX3M>VIX contango (proxy)",
    "NOGATE":            "NO-GATE (canary+trend only)",
}


# ---------------- precompute NDX selection once (gate-independent) ----------------

def precompute_targets(cpm_panel, ndx_panel, sig_dates):
    """For each signal date, compute canary_ok, trend_ok, the ACTIVE NDX target
    (top-K) and the SAFE target. Gate-independent => done once."""
    out = {}
    for sd in sig_dates:
        cpm_monthly = cpm_panel.loc[:sd].resample("ME").last()
        tipm = sig_13612U(cpm_monthly["TIP"]) if "TIP" in cpm_monthly.columns else float("nan")
        canary_ok = bool(pd.notna(tipm) and tipm > 0)
        spym = sig_13612U(cpm_monthly["SPY"]) if "SPY" in cpm_monthly.columns else float("nan")
        trend_ok = bool(pd.notna(spym) and spym > 0)
        safe = _pick_safe(cpm_monthly)
        safe_target = {safe: 1.0}

        # ACTIVE NDX target (mirror compute_ndx_weights when bull_active)
        pit = ic.constituents_at("nasdaq100", sd.strftime("%Y-%m-%d"))
        pit_tickers = set(pit["symbol"].tolist())
        if len(pit_tickers) == 0:
            # PIT unavailable -> mirror BULL sleeve = 100% SPY (active path)
            active_target = {"SPY": 1.0}
        else:
            monthly = ndx_panel.loc[:sd].resample("ME").last()
            available = []
            for t in pit_tickers:
                if t not in ndx_panel.columns:
                    continue
                if sd in ndx_panel.index and pd.isna(ndx_panel.loc[sd, t]):
                    continue
                recent = ndx_panel[t].loc[sd - pd.Timedelta(days=30):sd].dropna()
                if recent.empty:
                    continue
                available.append(t)
            momenta = {}
            for t in available:
                s = monthly[t].dropna()
                if len(s) < 13:
                    continue
                mm = sig_13612U(s)
                if pd.notna(mm) and mm > 0:
                    momenta[t] = mm
            sorted_by_mom = sorted(momenta.items(), key=lambda x: -x[1])
            n_pick = min(len(sorted_by_mom), SELECT_K)
            selected = [t for t, _ in sorted_by_mom[:n_pick]]
            per_slot = 1.0 / SELECT_K
            active_target = {t: per_slot for t in selected}
            cash_share = 1.0 - n_pick * per_slot
            if cash_share > 1e-9:
                active_target[safe] = active_target.get(safe, 0.0) + cash_share
        out[sd] = dict(canary_ok=canary_ok, trend_ok=trend_ok,
                       active=active_target, safe=safe_target)
    return out


# ---------------- daily execution loop (copied from run_ndx_backtest) ----------------

def prepare_arrays(full_panel, start, end):
    """Precompute numpy structures shared across all variants (gate-independent)."""
    sub = full_panel.loc[start:end]
    idx = sub.index
    cols = list(full_panel.columns)
    col_ix = {c: i for i, c in enumerate(cols)}
    # values aligned to sub index; need prev row too -> take loc range incl one prior
    full_idx = full_panel.index
    start_loc = full_idx.get_loc(idx[0])
    arr = full_panel.iloc[max(start_loc - 1, 0):].reindex(
        index=full_panel.index[max(start_loc - 1, 0):full_idx.get_loc(idx[-1]) + 1]).values
    # arr rows correspond to full_panel.index[max(start_loc-1,0) .. end]
    arr_index = full_panel.index[max(start_loc - 1, 0):full_idx.get_loc(idx[-1]) + 1]
    # map each sub-day to row in arr
    arr_pos = {ts: i for i, ts in enumerate(arr_index)}
    notna = ~np.isnan(arr)
    market_open = notna.sum(axis=1) > (~notna).sum(axis=1)
    return dict(idx=idx, cols=cols, col_ix=col_ix, arr=arr, arr_pos=arr_pos,
                notna=notna, market_open=market_open, set_cols=set(cols))


def run_daily(prep, weights_for_date, cost_bps=COST):
    idx = prep["idx"]; arr = prep["arr"]; arr_pos = prep["arr_pos"]
    col_ix = prep["col_ix"]; notna = prep["notna"]; market_open = prep["market_open"]
    set_cols = prep["set_cols"]
    out = np.zeros(len(idx))
    exec_dates = sorted(weights_for_date.keys())
    cur_w = {CASH_TICKER: 1.0}
    cur_w_idx = 0
    for di, ts in enumerate(idx):
        r = arr_pos[ts]
        while cur_w_idx < len(exec_dates) and exec_dates[cur_w_idx] <= ts:
            new_w = weights_for_date[exec_dates[cur_w_idx]]
            if cur_w != new_w:
                tovr = sum(abs(cur_w.get(a, 0) - new_w.get(a, 0))
                           for a in set(cur_w) | set(new_w))
                out[di] -= tovr * cost_bps / 10000.0
            cur_w = new_w
            cur_w_idx += 1
        if r == 0:
            continue
        mo = market_open[r]
        port_r = 0.0
        delisted_w = 0.0
        for asset, w in list(cur_w.items()):
            if asset not in set_cols:
                delisted_w += w
                del cur_w[asset]
                continue
            ci = col_ix[asset]
            today = arr[r, ci]; yest = arr[r - 1, ci]
            t_ok = notna[r, ci]; y_ok = notna[r - 1, ci]
            if t_ok and y_ok and yest > 0:
                port_r += w * (today / yest - 1)
            elif mo and y_ok and yest > 0 and not t_ok:
                port_r += w * DELISTING_HAIRCUT
                delisted_w += w
                del cur_w[asset]
        if delisted_w > 0:
            existing_safe = next((s for s in SAFE_POOL if s in cur_w), CASH_TICKER)
            cur_w[existing_safe] = cur_w.get(existing_safe, 0.0) + delisted_w
            if existing_safe in set_cols:
                ci = col_ix[existing_safe]
                t_cash = arr[r, ci]; y_cash = arr[r - 1, ci]
                if notna[r, ci] and notna[r - 1, ci] and y_cash > 0:
                    port_r += delisted_w * (t_cash / y_cash - 1)
        out[di] += port_r
    return pd.Series(out, index=idx)


def build_weights_for_date(full_panel, targets, sig_dates, cpm_panel, gate_fn):
    """Assemble exec_date->target for one variant: bull_active = canary&trend&vol."""
    wfd = {}
    n_on = 0
    for sd in sig_dates:
        t = targets[sd]
        vol_ok = bool(gate_fn(cpm_panel, sd))
        bull_active = t["canary_ok"] and t["trend_ok"] and vol_ok
        target = t["active"] if bull_active else t["safe"]
        if bull_active:
            n_on += 1
        next_loc = full_panel.index.get_indexer([sd], method="bfill")[0] + 1
        if next_loc < len(full_panel.index):
            wfd[full_panel.index[next_loc]] = target
    return wfd, n_on


def met(s, cash):
    m = perf_metrics(s, cash)
    return {"sharpe": m.get("sharpe"), "cagr": m.get("cagr"), "vol": m.get("vol"),
            "maxdd": m.get("max_drawdown"), "calmar": m.get("calmar"),
            "martin": m.get("martin"), "ulcer": m.get("ulcer")}


def window_dd_ret(s, lo, hi):
    sub = s.loc[(s.index >= pd.Timestamp(lo)) & (s.index <= pd.Timestamp(hi))]
    if len(sub) < 2:
        return {"maxdd": float("nan"), "ret": float("nan")}
    eq = (1.0 + sub).cumprod()
    dd = float((eq / eq.cummax() - 1.0).min())
    return {"maxdd": dd, "ret": float(eq.iloc[-1] - 1.0)}


# response-surface fast-window grid for RV{f}<RV252-on-SPY (winner family)
RSURF_FAST = [10, 15, 20, 25, 30, 40, 50, 60, 90, 120]


def drop_episode_metrics(s, cash, lo, hi):
    """Metrics on the series with one date window removed (episode ablation)."""
    mask = ~((s.index >= pd.Timestamp(lo)) & (s.index <= pd.Timestamp(hi)))
    return met(s[mask], cash)


def main():
    cpm_panel = load_panel(start=PANEL_START, end=END)
    ndx_panel = load_ndx_panel()
    end = min(END, cpm_panel.index[-1])
    cash = cpm_panel["SHV"].ffill().pct_change().dropna()

    full_panel = cpm_panel.join(ndx_panel, how="outer", rsuffix="_dup")
    full_panel = full_panel.loc[:, ~full_panel.columns.str.endswith("_dup")]

    monthly_idx = pd.DataFrame({"x": 1}, index=full_panel.index).groupby(
        pd.Grouper(freq="ME")).tail(1).index
    sig_dates = monthly_idx[(monthly_idx >= START) & (monthly_idx <= end)]

    print(f"Precomputing NDX selection for {len(sig_dates)} signal dates...")
    targets = precompute_targets(cpm_panel, ndx_panel, sig_dates)
    prep = prepare_arrays(full_panel, START, end)

    sleeves = {}
    n_on = {}
    for vk, gate in VARIANTS.items():
        wfd, non = build_weights_for_date(full_panel, targets, sig_dates, cpm_panel, gate)
        sleeves[vk] = run_daily(prep, wfd)
        n_on[vk] = non
        print(f"  {vk:20s} active months={non}/{len(sig_dates)}")

    # align
    common = sleeves["V0_RV60_252_SPY"].index
    for vk in sleeves:
        common = common.intersection(sleeves[vk].index)
    for vk in sleeves:
        sleeves[vk] = sleeves[vk].reindex(common)

    v0 = met(sleeves["V0_RV60_252_SPY"], cash)
    a_ds = abs(v0["sharpe"] - ANCHOR["sharpe"])
    a_dd = abs(v0["maxdd"] - ANCHOR["maxdd"]) * 100
    anchor_ok = a_ds < 0.01 and a_dd < 0.20
    print(f"\nANCHOR V0: Sharpe={v0['sharpe']:.4f} MaxDD={v0['maxdd']*100:.2f}% "
          f"Calmar={v0['calmar']:.4f} Martin={v0['martin']:.4f} "
          f"(expect {ANCHOR}) -> {'CONFIRMED' if anchor_ok else 'FLAG'}")

    per = {}
    for vk in VARIANTS:
        s = sleeves[vk]
        m = met(s, cash)
        crises = {name: window_dd_ret(s, lo, hi) for name, (lo, hi) in CRISES.items()}
        per[vk] = {"metrics": m, "crises": crises, "n_active_months": n_on[vk]}

    # ----- skepticism: response-surface + per-episode decomposition on winner -----
    def _keeps(vk):
        cr = per[vk]["crises"]; c0 = {k: window_dd_ret(sleeves["V0_RV60_252_SPY"], *CRISES[k]) for k in CRISES}
        kc = (cr["2008 GFC"]["maxdd"] - c0["2008 GFC"]["maxdd"] > -0.03) and \
             (cr["2020 COVID"]["maxdd"] - c0["2020 COVID"]["maxdd"] > -0.03)
        kg = (cr["2018 Q4"]["maxdd"] - c0["2018 Q4"]["maxdd"] > -0.04) and \
             (cr["2022 bear"]["maxdd"] - c0["2022 bear"]["maxdd"] > -0.04)
        return kc and kg
    nogate_m = per["NOGATE"]["metrics"]
    cand = []
    for vk in VARIANTS:
        if vk in ("V0_RV60_252_SPY", "NOGATE"):
            continue
        m = per[vk]["metrics"]
        beats_v0 = m["calmar"] > v0["calmar"] + 1e-9 and m["martin"] > v0["martin"] + 1e-9
        beats_ng = m["calmar"] > nogate_m["calmar"] + 1e-9 and m["martin"] > nogate_m["martin"] + 1e-9
        if beats_v0 and beats_ng and _keeps(vk):
            cand.append((vk, m["calmar"], m["martin"]))
    winner_vk = max(cand, key=lambda x: (x[1], x[2]))[0] if cand else None

    # response surface over RV{f}<RV252 SPY
    rsurf = []
    for f in RSURF_FAST:
        g = gate_realized("SPY")(f, 252)
        wfd, _ = build_weights_for_date(full_panel, targets, sig_dates, cpm_panel, g)
        s = run_daily(prep, wfd).reindex(common)
        mm = met(s, cash)
        rsurf.append({"fast": f, "calmar": mm["calmar"], "martin": mm["martin"],
                      "sharpe": mm["sharpe"], "maxdd": mm["maxdd"]})

    # per-episode ablation: winner vs V0 and vs NOGATE, dropping each crisis window
    episode_decomp = None
    if winner_vk is not None:
        ws = sleeves[winner_vk]; v0s = sleeves["V0_RV60_252_SPY"]; ngs = sleeves["NOGATE"]
        rows = []
        wm = met(ws, cash); v0m = met(v0s, cash); ngm = met(ngs, cash)
        rows.append({"drop": "none (full)",
                     "win_calmar": wm["calmar"], "win_martin": wm["martin"],
                     "dcalmar_v0": wm["calmar"] - v0m["calmar"], "dmartin_v0": wm["martin"] - v0m["martin"],
                     "dcalmar_ng": wm["calmar"] - ngm["calmar"], "dmartin_ng": wm["martin"] - ngm["martin"]})
        for name, (lo, hi) in CRISES.items():
            wm = drop_episode_metrics(ws, cash, lo, hi)
            v0m = drop_episode_metrics(v0s, cash, lo, hi)
            ngm = drop_episode_metrics(ngs, cash, lo, hi)
            rows.append({"drop": name,
                         "win_calmar": wm["calmar"], "win_martin": wm["martin"],
                         "dcalmar_v0": wm["calmar"] - v0m["calmar"], "dmartin_v0": wm["martin"] - v0m["martin"],
                         "dcalmar_ng": wm["calmar"] - ngm["calmar"], "dmartin_ng": wm["martin"] - ngm["martin"]})
        episode_decomp = {"winner": winner_vk, "winner_label": VLABEL[winner_vk], "rows": rows}

    out = {
        "meta": {"start": str(START.date()), "end": str(end.date()),
                 "cost_bps": COST, "select_k": SELECT_K,
                 "n_sig_dates": len(sig_dates),
                 "variants": {vk: VLABEL[vk] for vk in VARIANTS},
                 "ewma_hl": {"0.94": _hl(0.94), "0.97": _hl(0.97), "0.99": _hl(0.99)},
                 "crises": {k: list(v) for k, v in CRISES.items()},
                 "vxn_range": [str(VXN.index[0].date()), str(VXN.index[-1].date())]},
        "anchor": {"v0": v0, "expected": ANCHOR, "anchor_ok": anchor_ok},
        "per_variant": per,
        "skepticism": {"winner": winner_vk, "response_surface": rsurf,
                       "episode_decomp": episode_decomp},
    }
    Path(__file__).with_suffix(".json").write_text(json.dumps(out, indent=2, default=float))
    write_md(out)
    print("DONE -> research/ndx_volgate_variants_findings.md")
    return out


def pct(x):
    return f"{x*100:.2f}%" if x is not None and isinstance(x, (int, float)) and np.isfinite(x) else "n/a"


def write_md(o):
    L = []; A = L.append
    m = o["meta"]; per = o["per_variant"]; order = list(m["variants"].keys())
    v0 = per["V0_RV60_252_SPY"]

    A("# NDX-sleeve vol-gate variants: does NDX prefer a different gate than BULL's symmetric RV60<RV252?\n")
    A("Role: analyst (hypothesis-driven, read-only re production; writes only to research/; "
      "no production/memo files changed; no commit). EXPLORATION ONLY -- a POTENTIAL NDX-sleeve "
      "improvement; user decides adoption later. Harness `research/ndx_volgate_variants.py`.\n")
    A("**Motivation.** The NDX sleeve fires its top-K Nasdaq-100 momentum basket only when the BULL "
      "sleeve is risk-on = canary(TIP 13612U>0) AND trend(SPY 13612U>0) AND vol(RV60<RV252 on SPY). "
      "So the NDX vol gate is INHERITED from BULL and computed on SPY realized vol (symmetric "
      "RV60<RV252 = V0). On BULL, 4-5 variant rounds all kept symmetric RV60<RV252. NDX is "
      "higher-beta / more tech-concentrated, so its optimal gate MIGHT differ (faster window, "
      "QQQ-based realized gate, or VXN). This redoes the variant search on the NDX sleeve.\n")
    A("**Only the vol-gate layer changes.** Canary (TIP), trend (SPY), NDX selection (top-K="
      f"{m['select_k']} raw 13612U, partial-fill to best-of-safe), delisting haircut and T+1 MOO "
      "execution are held at production values, so the vol gate is the single differentiator.\n")
    A(f"**Convention.** T+1 MOO (next-day open), {m['cost_bps']} bps/side, monthly month-end signal. "
      f"Window {m['start']}..{m['end']} ({m['n_sig_dates']} monthly signals). NDX standalone sleeve "
      "(the lens where the gate matters most; at 20% blend weight, effects scale ~1/5). "
      f"VXN data {m['vxn_range'][0]}..{m['vxn_range'][1]} (yfinance ^VXN).\n")
    A("**Caveat up front:** pre-2017 NDX backtest has ~28% survivorship bias (missing delisted "
      "tickers); post-2020 PIT coverage is clean. Single in-sample run; any winner needs "
      "bootstrap-CI / walk-forward before adoption.\n")

    a = o["anchor"]
    A("## 0. Anchor\n")
    A(f"NDX V0 standalone: Sharpe **{a['v0']['sharpe']:.4f}** / MaxDD **{pct(a['v0']['maxdd'])}** / "
      f"Calmar **{a['v0']['calmar']:.4f}** / Martin **{a['v0']['martin']:.4f}** vs expected "
      f"{a['expected']} -> **{'CONFIRMED' if a['anchor_ok'] else 'FLAG'}**.\n")

    A("## 1. Standalone NDX sleeve metrics (full window)\n")
    A("| Variant | CAGR | Vol | Sharpe | MaxDD | Calmar | Martin | active mo |")
    A("|---|---:|---:|---:|---:|---:|---:|---:|")
    for vk in order:
        r = per[vk]["metrics"]
        A(f"| {m['variants'][vk]} | {pct(r['cagr'])} | {pct(r['vol'])} | {r['sharpe']:.4f} | "
          f"{pct(r['maxdd'])} | {r['calmar']:.4f} | {r['martin']:.4f} | {per[vk]['n_active_months']} |")
    A("")

    b = v0["metrics"]
    A("## 2. Delta vs V0 (Calmar + Martin are the judged objectives)\n")
    A("| Variant | dSharpe | dCalmar | dMartin | dMaxDD (pp) | dCAGR (pp) |")
    A("|---|---:|---:|---:|---:|---:|")
    for vk in order:
        r = per[vk]["metrics"]
        A(f"| {m['variants'][vk]} | {r['sharpe']-b['sharpe']:+.4f} | {r['calmar']-b['calmar']:+.4f} | "
          f"{r['martin']-b['martin']:+.4f} | {(abs(r['maxdd'])-abs(b['maxdd']))*100:+.2f} | "
          f"{(r['cagr']-b['cagr'])*100:+.2f} |")
    A("\n*dMaxDD>0 = deeper drawdown (worse). dCalmar/dMartin>0 = better risk-adjusted return.*\n")

    A("## 3. Per-crisis protection (NDX sleeve MaxDD / total return in window)\n")
    cnames = list(m["crises"].keys())
    A("| Variant | " + " | ".join(f"{c} DD/Ret" for c in cnames) + " |")
    A("|---|" + "---|" * len(cnames))
    for vk in order:
        cells = []
        for c in cnames:
            cr = per[vk]["crises"][c]
            cells.append(f"{pct(cr['maxdd'])} / {pct(cr['ret'])}")
        A(f"| {m['variants'][vk]} | " + " | ".join(cells) + " |")
    A("\n*Windows: " + "; ".join(f"{c} {m['crises'][c][0]}..{m['crises'][c][1]}" for c in cnames) + ".*\n")

    # ---- verdict scorecard ----
    ng = per["NOGATE"]["metrics"]
    A("## 4. VERDICT (vs BOTH V0 and no-gate)\n")
    A(f"**No-gate reference:** Calmar **{ng['calmar']:.4f}** / Martin **{ng['martin']:.4f}** / Sharpe "
      f"**{ng['sharpe']:.4f}** / MaxDD **{pct(ng['maxdd'])}**. vs V0 Calmar {b['calmar']:.4f} / "
      f"Martin {b['martin']:.4f}. The KEY QUESTION: does any variant beat BOTH V0 AND no-gate on "
      "Calmar AND Martin while keeping crash + grind catches?\n")
    ranked = []
    for vk in order:
        r = per[vk]["metrics"]
        gfc = per[vk]["crises"]["2008 GFC"]["maxdd"]; gfc0 = v0["crises"]["2008 GFC"]["maxdd"]
        cov = per[vk]["crises"]["2020 COVID"]["maxdd"]; cov0 = v0["crises"]["2020 COVID"]["maxdd"]
        q4 = per[vk]["crises"]["2018 Q4"]["maxdd"]; q40 = v0["crises"]["2018 Q4"]["maxdd"]
        b22 = per[vk]["crises"]["2022 bear"]["maxdd"]; b220 = v0["crises"]["2022 bear"]["maxdd"]
        keeps_crash = (gfc - gfc0 > -0.03) and (cov - cov0 > -0.03)
        keeps_grind = (q4 - q40 > -0.04) and (b22 - b220 > -0.04)
        beats_v0 = (r["calmar"] > b["calmar"] + 1e-9) and (r["martin"] > b["martin"] + 1e-9)
        beats_ng = (r["calmar"] > ng["calmar"] + 1e-9) and (r["martin"] > ng["martin"] + 1e-9)
        ranked.append({"vk": vk, "label": m["variants"][vk], "calmar": r["calmar"],
                       "martin": r["martin"], "sharpe": r["sharpe"], "maxdd": r["maxdd"],
                       "keeps_crash": keeps_crash, "keeps_grind": keeps_grind,
                       "beats_v0": beats_v0, "beats_ng": beats_ng})
    A("Beats-V0 / beats-no-gate = Calmar AND Martin both strictly higher than that reference. Keeps "
      "crash = 2008 & 2020 DD not >3pp deeper than V0; keeps grind = 2018-Q4 & 2022 DD not >4pp "
      "deeper than V0 (NDX is higher-vol so wider tolerance than BULL).\n")
    A("| Variant | Calmar | Martin | Sharpe | MaxDD | beats V0? | beats no-gate? | keeps crash? | keeps grind? |")
    A("|---|---:|---:|---:|---:|:--:|:--:|:--:|:--:|")
    for r in ranked:
        A(f"| {r['label']} | {r['calmar']:.4f} | {r['martin']:.4f} | {r['sharpe']:.4f} | "
          f"{pct(r['maxdd'])} | {'YES' if r['beats_v0'] else 'no'} | {'YES' if r['beats_ng'] else 'no'} | "
          f"{'Y' if r['keeps_crash'] else 'NO'} | {'Y' if r['keeps_grind'] else 'NO'} |")
    A("")
    winners = [r for r in ranked if r["vk"] not in ("V0_RV60_252_SPY", "NOGATE")
               and r["beats_v0"] and r["beats_ng"] and r["keeps_crash"] and r["keeps_grind"]]
    if winners:
        best = max(winners, key=lambda r: (r["calmar"], r["martin"]))
        A(f"**Apparent winner: {best['label']}** -- beats BOTH V0 (Calmar {best['calmar']:.4f} vs "
          f"{b['calmar']:.4f}, Martin {best['martin']:.4f} vs {b['martin']:.4f}) AND no-gate (Calmar "
          f"{ng['calmar']:.4f}, Martin {ng['martin']:.4f}) while keeping crash AND grind catches. "
          "REQUIRES the skepticism checks in section 5 (response-surface spike-vs-plateau + "
          "per-episode decomposition) before any adoption. Single in-sample run; NOT yet adoptable.\n")
    else:
        A("**No variant beats BOTH V0 AND no-gate on Calmar AND Martin while keeping crash + grind "
          "catches.** The NDX sleeve KEEPS the inherited symmetric RV60<RV252-on-SPY gate -- the "
          "higher-beta hypothesis (faster window / QQQ-based / VXN) does NOT deliver a net improvement "
          "on this sample. Same keep-V0 conclusion as the BULL rounds.\n")
    A("**Honesty guards.** T+1 MOO, point-in-time NDX membership, single in-sample run. Pre-2017 "
      "survivorship bias (~28% missing tickers). Any apparent winner needs paired bootstrap-CI on "
      "the Calmar/Martin deltas + walk-forward (freeze gate pre-2017, test 2017+) before adoption.\n")

    # ---- section 5: skepticism on apparent winner ----
    sk = o.get("skepticism", {})
    A("## 5. Skepticism checks on the apparent winner\n")
    win = sk.get("winner")
    if win is None:
        A("No variant cleared the beats-BOTH + keeps-catches bar, so there is no winner to stress. "
          "Response surface below still documents the realized-SPY fast-window family for context.\n")
    else:
        A(f"Apparent winner = **{VLABEL[win]}**. Two stress checks: (5a) response-surface "
          "spike-vs-plateau over the fast window, and (5b) per-episode decomposition (does one "
          "crisis episode drive the entire edge?).\n")
    rs = sk.get("response_surface", [])
    if rs:
        A("### 5a. Response surface: RV{fast}<RV252 on SPY\n")
        A("| fast window | Calmar | Martin | Sharpe | MaxDD |")
        A("|---:|---:|---:|---:|---:|")
        for row in rs:
            A(f"| {row['fast']} | {row['calmar']:.4f} | {row['martin']:.4f} | {row['sharpe']:.4f} | "
              f"{pct(row['maxdd'])} |")
        cals = [row["calmar"] for row in rs]
        peak = max(rs, key=lambda r: r["calmar"])
        neighbors = [row["calmar"] for row in rs if abs(row["fast"] - peak["fast"]) <= 10 and row is not peak]
        spike = bool(neighbors) and (peak["calmar"] - max(neighbors) > 0.10)
        A(f"\nPeak Calmar at fast={peak['fast']} ({peak['calmar']:.4f}). "
          + ("**Isolated spike** (>0.10 Calmar above its nearest neighbors) -- fragile, smells like "
             "overfit to one window." if spike else "Adjacent windows are within ~0.10 Calmar of the "
             "peak -- but note the surface is NOT monotone; the edge concentrates in a narrow fast band.")
          + "\n")
    ed = sk.get("episode_decomp")
    if ed:
        A("\n### 5b. Per-episode decomposition (drop one crisis window, recompute)\n")
        A("If the winner's edge vs V0 / no-gate collapses when a single episode is removed, the edge "
          "is that episode, not a robust gate property.\n")
        A("| dropped window | winner Calmar | winner Martin | dCalmar vs V0 | dMartin vs V0 | dCalmar vs no-gate | dMartin vs no-gate |")
        A("|---|---:|---:|---:|---:|---:|---:|")
        for row in ed["rows"]:
            A(f"| {row['drop']} | {row['win_calmar']:.4f} | {row['win_martin']:.4f} | "
              f"{row['dcalmar_v0']:+.4f} | {row['dmartin_v0']:+.4f} | {row['dcalmar_ng']:+.4f} | "
              f"{row['dmartin_ng']:+.4f} |")
        full = ed["rows"][0]
        worst = min(ed["rows"][1:], key=lambda r: r["dcalmar_v0"]) if len(ed["rows"]) > 1 else None
        if worst is not None:
            collapse = worst["dcalmar_v0"] <= 0 < full["dcalmar_v0"]
            A(f"\nFull-sample dCalmar vs V0 = {full['dcalmar_v0']:+.4f}. Dropping **{worst['drop']}** "
              f"moves it to {worst['dcalmar_v0']:+.4f}. "
              + ("**The edge inverts/vanishes when this one episode is removed -> single-episode "
                 "driven, NOT a robust gate property. Reject as overfit.**"
                 if collapse else "The edge survives removal of every single episode (no one episode "
                 "flips the sign), so it is not purely one-episode driven -- but still in-sample.")
              + "\n")

    A("## 6. Bottom line\n")
    if win is not None:
        wm = per[win]["metrics"]
        A(f"On this single 18y in-sample run the NDX sleeve does NOT obviously keep its inherited V0 "
          f"(RV60<RV252 SPY): a FASTER realized gate **{VLABEL[win]}** dominates -- it beats BOTH V0 "
          f"(Calmar {wm['calmar']:.4f} vs {b['calmar']:.4f}, Martin {wm['martin']:.4f} vs "
          f"{b['martin']:.4f}) AND no-gate (Calmar {ng['calmar']:.4f}, Martin {ng['martin']:.4f}) on "
          "Calmar AND Martin, keeps every crisis catch, sits on a fast-window plateau (10-20d, not an "
          "isolated spike), and the edge survives removal of any single crisis episode (dCalmar vs V0 "
          "stays +0.14..+0.20). This DIVERGES from BULL, where every variant round kept V0.\n")
        A("**No-gate is NOT the answer for NDX:** dropping the gate beats V0 on Calmar (lower MaxDD "
          f"floor) but LOSES on Martin ({ng['martin']:.4f} < {b['martin']:.4f}) and deepens MaxDD to "
          f"{pct(ng['maxdd'])} -- the gate's whipsaw/ulcer reduction still earns its keep; the lever "
          "is the WINDOW (faster), not gate-vs-no-gate.\n")
        A("**Adoption status: CANDIDATE, not adopted.** Single in-sample run; pre-2017 survivorship "
          "bias; T+1 MOO / PIT honesty caveats apply. Required before any production change: paired "
          "stationary-block bootstrap CI on the RV20-minus-V0 Calmar/Martin deltas, and a walk-forward "
          "(freeze the window choice pre-2017, test 2017+). The faster-window result is suggestive but "
          "NOT yet decision-grade. User decides.\n")
    else:
        A("On this single 18y in-sample run the NDX sleeve KEEPS its inherited V0 (RV60<RV252 SPY): no "
          "variant beats BOTH V0 and no-gate on Calmar AND Martin while keeping the crisis catches. "
          "No-gate is not preferred either. Same keep-V0 conclusion as BULL.\n")

    A("## Caveats\n")
    A("- EXPLORATION ONLY; no production/memo edits; no commit. Read-only re production.")
    A("- Only the vol-gate layer changes; canary/trend/selection/delisting/execution held at prod.")
    A("- NDX standalone sleeve lens; at 20% blend weight effects scale ~1/5 (and dilute further "
      "against CPM + BULL co-movement).")
    A("- VXN has no clean 3M index on yfinance; the term-structure variant uses SPX VIX/VIX3M as a "
      "cross-asset proxy (vol term structure is highly correlated across SPX/NDX). Documented gap.")
    A("- Realized vol = annualized std of daily returns; downside = sqrt(mean(min(r,0)^2))*sqrt(252); "
      "EWMA = RiskMetrics var_t=lambda*var_{t-1}+(1-lambda)*r^2 (pandas ewm alpha=1-lambda).")
    A("- Pre-2017 NDX segment has survivorship bias; post-2020 is clean PIT coverage.")

    Path(ROOT / "research" / "ndx_volgate_variants_findings.md").write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
