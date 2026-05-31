#!/usr/bin/env python3
"""
Canary variant test: HYG-OR-TIP (any-positive 13612U) vs TIP-only vs none.

Decision: should the dual-canary (HYG OR TIP) be dropped to TIP-only?
Toggle ONLY the canary input on each sleeve; hold everything else at production.

Faithful execution = mooex (same framework that produces the production anchor:
  CPM clean Sharpe 1.1910, BULL 1.0813, 60/40 blend 1.2485).

Read-only re production. Writes to research/ only. No production/memo edits.

Windows:
  clean = 2008-05-30 .. 2026-05-22  (fully REAL TIP[VIPSX 2000-06+] + REAL HYG)
  ext   = 1999-03-10 .. 2026-05-22

TIP proxy reality:
  - Real TIP (VIPSX stitch) in panel starts 2000-06; 13612U signal from 2001-06.
  - clean window: 100% real TIP, no proxy needed (decision-relevant).
  - ext window pre-2001-06: production has NO TIP signal => TIP-only forced
    defensive (artifact). We add a CPI-aware synthetic TIP (IEF nominal total
    return + realized monthly CPI inflation accrual) to de-bias the ext window.
  - 1970s stagflation sleeve backtest is INFEASIBLE: panel starts 1995, risky
    ETF universe + HYG credit proxy do not extend pre-1980/1995. Documented in
    findings; verdict rests on real-TIP era (clean window, incl. 2022 stagflation).
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import cpm_live
import bull_qqq_live
import research.exec_lag_moo_validation_2026_05_30 as H
from cpm_live import (
    load_panel, perf_metrics, faber_sma_xs, sig_13612U, best_safe, inv_vol_weights,
    RISKY_UNIVERSE, SAFE_POOL, DEFAULT_CASH, TOP_K_CANDIDATES, CORR_LOOKBACK_DAYS,
)
from bull_qqq_live import BULL_TICKER

CLEAN = pd.Timestamp("2008-05-30")
EXT = pd.Timestamp("1999-03-10")
END = pd.Timestamp("2026-05-22")
CONV = "mooex"

ANCHOR = {"cpm": 1.1910, "bull": 1.0813, "blend": 1.2485}

_PROD_CPM = cpm_live.compute_target_weights
_PROD_CANARY_CPM = list(cpm_live.CANARY_ASSETS)
_PROD_CANARY_BULL = list(bull_qqq_live.CANARY_ASSETS)
_PROD_MACRO = bull_qqq_live._macro_gate


# ---------------------------------------------------------------------------
# Faithful CPM compute with NO canary gate (everything else == production).
# Mirrors cpm_live.compute_target_weights exactly minus the canary block.
# ---------------------------------------------------------------------------
def cpm_compute_nocanary(close_panel, sig_d, universe=None, safe_pool=None,
                         canary_assets=None):
    universe = universe or RISKY_UNIVERSE
    safe_pool = safe_pool or SAFE_POOL
    monthly = close_panel.loc[:sig_d].resample("ME").last()
    safe = best_safe(monthly, sig_d, safe_pool)
    # --- canary block removed (always risk-on) ---
    faber = faber_sma_xs(monthly)
    avail = [t for t in universe
             if t in faber.index and pd.notna(faber[t])
             and pd.notna(close_panel.loc[sig_d].get(t, np.nan) if sig_d in close_panel.index else np.nan)]
    if not avail:
        return {safe: 1.0}, None, "DEFENSIVE", safe
    daily_rets = close_panel[avail].ffill().pct_change()
    scores = {}
    for t in avail:
        v = daily_rets[t].loc[:sig_d].tail(252).std() * np.sqrt(252)
        if pd.isna(v) or v < 1e-9:
            v = 1.0
        scores[t] = float(faber[t]) / v
    sa = pd.Series(scores)
    ranked = sa.sort_values(ascending=False)
    top_k = max(2, min(TOP_K_CANDIDATES, len(ranked)))
    top = ranked.iloc[:top_k]
    positive = top[top.index.map(lambda t: faber.get(t, -np.inf) > 0)]
    if len(positive) == 0:
        return {safe: 1.0}, None, "DEFENSIVE", safe
    picks = list(positive.index)
    n_picks = len(picks)
    risky_fraction = min(n_picks, 4) / 4.0
    safe_fraction = 1.0 - risky_fraction
    csub = close_panel.loc[:sig_d]
    risky_w = inv_vol_weights(csub, picks, CORR_LOOKBACK_DAYS)
    out = {t: w * risky_fraction for t, w in risky_w.items()}
    if safe_fraction > 0:
        out[safe] = out.get(safe, 0.0) + safe_fraction
    return out, tuple(picks), "RISK_ON", safe


def _bull_macro_always_on(monthly, sig_d):
    return (True, {"hyg_sig": float("nan"), "tip_sig": float("nan"), "canary_ok": True})


def set_cpm_canary(mode):
    """mode in {'tip','hygortip','none'}"""
    if mode == "none":
        H.compute_target_weights = cpm_compute_nocanary
    else:
        H.compute_target_weights = _PROD_CPM
        cpm_live.CANARY_ASSETS = ["TIP"] if mode == "tip" else ["HYG", "TIP"]


def reset_cpm_canary():
    H.compute_target_weights = _PROD_CPM
    cpm_live.CANARY_ASSETS = list(_PROD_CANARY_CPM)


def set_bull_canary(mode):
    if mode == "none":
        bull_qqq_live._macro_gate = _bull_macro_always_on
    else:
        bull_qqq_live._macro_gate = _PROD_MACRO
        bull_qqq_live.CANARY_ASSETS = ["TIP"] if mode == "tip" else ["HYG", "TIP"]


def reset_bull_canary():
    bull_qqq_live._macro_gate = _PROD_MACRO
    bull_qqq_live.CANARY_ASSETS = list(_PROD_CANARY_BULL)


# ---------------------------------------------------------------------------
# CPI-aware synthetic TIP (pre-real-TIP de-bias for ext window).
# Construction (documented): monthly synthetic TIPS total return =
#   IEF nominal intermediate-Treasury total return + realized monthly CPI inflation.
# (TIPS principal accretes with CPI; the inflation accrual is the missing piece
#  in a nominal-bond proxy.) Cumulated to a monthly price index, reindexed to
#  daily (ffill). Used ONLY for the canary 13612U signal (TIP is canary-only).
# ---------------------------------------------------------------------------
def build_synthetic_tip(panel):
    cpi = pd.read_csv("/tmp/cpi_test.csv", parse_dates=[0], index_col=0)["CPIAUCSL"]
    cpi.index = cpi.index + pd.offsets.MonthEnd(0)  # CPI dated 1st -> align month-end
    cpi_infl = cpi.pct_change()  # monthly realized inflation
    ief_m = panel["IEF"].resample("ME").last()
    ief_ret = ief_m.pct_change()
    idx = ief_ret.index.intersection(cpi_infl.index)
    syn_ret = ief_ret.reindex(idx) + cpi_infl.reindex(idx)
    syn_ret = syn_ret.dropna()
    syn_price_m = 100.0 * (1.0 + syn_ret).cumprod()
    # daily series: place at month-end trading days, ffill
    daily = pd.Series(np.nan, index=panel.index)
    me = panel.resample("ME").last().index
    for m_end in syn_price_m.index:
        # last panel trading day on/before calendar month-end
        cand = panel.index[panel.index <= m_end]
        if len(cand):
            daily.loc[cand[-1]] = syn_price_m.loc[m_end]
    daily = daily.ffill()
    # Splice: synthetic before real-TIP availability, REAL TIP after (rescaled
    # so the synthetic level matches real at the first real-TIP date). This keeps
    # the post-2000 era on real data; synthetic only backfills the pre-2000 gap.
    real = panel["TIP"]
    real_start = real.first_valid_index()
    spliced = daily.copy()
    if real_start is not None and real_start in daily.index and pd.notna(daily.loc[real_start]):
        scale = real.loc[real_start] / daily.loc[real_start]
        spliced = daily * scale
        spliced.loc[spliced.index >= real_start] = real.loc[real.index >= real_start]
        spliced = spliced.ffill()
    return spliced, syn_price_m, cpi_infl


def validate_synthetic(panel, syn_price_m):
    """Sign-agreement of 13612U(synthetic) vs 13612U(real TIP) over overlap."""
    real_m = panel["TIP"].resample("ME").last()
    agree, n = 0, 0
    rows = []
    for m_end in real_m.index:
        if pd.isna(real_m.loc[m_end]):
            continue
        rser = real_m.loc[:m_end].dropna()
        sser = syn_price_m.loc[:m_end].dropna()
        if len(rser) < 13 or len(sser) < 13:
            continue
        rs = sig_13612U(rser)
        ss = sig_13612U(sser)
        if pd.isna(rs) or pd.isna(ss):
            continue
        n += 1
        if (rs > 0) == (ss > 0):
            agree += 1
    return {"overlap_months": n, "sign_agreement": agree / n if n else float("nan")}


# ---------------------------------------------------------------------------
# Sleeve runners (mooex framework).
# ---------------------------------------------------------------------------
def run_cpm(panel, intr, on, start, end):
    return H.cpm_sleeve_conv(panel, intr, on, start, end, CONV)[0]


def run_bull(panel, intr, on, start, end):
    return H.bull_sleeve_conv(panel, intr, on, start, end, CONV, H.GATE_RV60)[0]


def win(s, start, end):
    return s.loc[(s.index >= start) & (s.index <= end)]


def metrics(s, cash):
    m = perf_metrics(s, cash)
    return {"sharpe": round(m["sharpe"], 4), "calmar": round(m["calmar"], 4),
            "maxdd": round(m["max_drawdown"] * 100, 2), "cagr": round(m["cagr"] * 100, 2),
            "vol": round(m["vol"] * 100, 2)}


def period_total_return(s, start, end):
    sub = s.loc[(s.index >= start) & (s.index <= end)]
    return float((1.0 + sub).prod() - 1.0) if len(sub) else float("nan")


def period_maxdd(s, start, end):
    sub = s.loc[(s.index >= start) & (s.index <= end)]
    if not len(sub):
        return float("nan")
    eq = (1.0 + sub).cumprod()
    return float((eq / eq.cummax() - 1.0).min())


# ---------------------------------------------------------------------------
# Block bootstrap on daily Sharpe difference (A - B), is diff within noise?
# ---------------------------------------------------------------------------
def block_bootstrap_sharpe_diff(a, b, block=21, reps=2000, seed=7):
    common = a.index.intersection(b.index)
    a = a.reindex(common).fillna(0.0).values
    b = b.reindex(common).fillna(0.0).values
    n = len(a)
    rng = np.random.default_rng(seed)
    nb = int(np.ceil(n / block))

    def sharpe(x):
        sd = x.std(ddof=0)
        return (x.mean() * 252) / (sd * np.sqrt(252)) if sd > 0 else 0.0

    obs = sharpe(a) - sharpe(b)
    diffs = np.empty(reps)
    for r in range(reps):
        starts = rng.integers(0, n, size=nb)
        idx = np.concatenate([np.arange(s, s + block) % n for s in starts])[:n]
        diffs[r] = sharpe(a[idx]) - sharpe(b[idx])
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    return {"obs_diff": round(float(obs), 4), "ci_lo": round(float(lo), 4),
            "ci_hi": round(float(hi), 4),
            "within_noise": bool(lo <= 0.0 <= hi)}


# ---------------------------------------------------------------------------
# State analysis: TIP-negative AND HYG-positive override months.
# These are months where HYG-OR-TIP stays risk-on but TIP-only would de-risk.
# Same canary signal feeds both sleeves; report the override calendar plus the
# risky sleeve's realized forward (next-month) return in those months.
# ---------------------------------------------------------------------------
def canary_signal_table(panel, tip_col="TIP"):
    m = panel.resample("ME").last()
    rows = []
    for me in m.index:
        h = sig_13612U(m["HYG"].loc[:me]) if "HYG" in m else np.nan
        t = sig_13612U(m[tip_col].loc[:me]) if tip_col in m else np.nan
        rows.append({"month": me, "hyg": h, "tip": t})
    return pd.DataFrame(rows).set_index("month")


def override_analysis(panel, sig_tbl, sleeve_daily, label, start, end, spy_daily):
    """For override months (tip<=0 & hyg>0) within window, realized next-month
    return of the sleeve, and of SPY (risky proxy)."""
    m_close = panel.resample("ME").last()
    months = [me for me in sig_tbl.index
              if start <= me <= end and pd.notna(sig_tbl.loc[me, "hyg"])
              and pd.notna(sig_tbl.loc[me, "tip"])]
    override = [me for me in months
               if sig_tbl.loc[me, "tip"] <= 0 < sig_tbl.loc[me, "hyg"]]
    risk_on_tip = [me for me in months if sig_tbl.loc[me, "tip"] > 0]

    def fwd_month_ret(series_daily, me):
        after = series_daily.index[series_daily.index > me]
        if not len(after):
            return np.nan
        nxt_me = (me + pd.offsets.MonthEnd(1))
        seg = series_daily.loc[(series_daily.index > me) & (series_daily.index <= nxt_me + pd.offsets.MonthEnd(0))]
        # simpler: take next ~21 trading days
        seg = series_daily.loc[series_daily.index > me].iloc[:21]
        return float((1.0 + seg).prod() - 1.0) if len(seg) else np.nan

    spy_fwd = [fwd_month_ret(spy_daily, me) for me in override]
    sleeve_fwd = [fwd_month_ret(sleeve_daily, me) for me in override]
    spy_fwd = [x for x in spy_fwd if pd.notna(x)]
    sleeve_fwd = [x for x in sleeve_fwd if pd.notna(x)]
    return {
        "label": label,
        "n_months_total": len(months),
        "n_override": len(override),
        "override_months": [str(me.date()) for me in override],
        "spy_fwd_mean_pct": round(float(np.mean(spy_fwd)) * 100, 3) if spy_fwd else None,
        "spy_fwd_vol_pct": round(float(np.std(spy_fwd, ddof=0)) * 100, 3) if spy_fwd else None,
        "spy_fwd_pct_neg": round(float(np.mean(np.array(spy_fwd) < 0)) * 100, 1) if spy_fwd else None,
        "sleeve_fwd_mean_pct": round(float(np.mean(sleeve_fwd)) * 100, 3) if sleeve_fwd else None,
    }


# ===========================================================================
def main():
    print("Loading panel ...")
    panel = load_panel(start=pd.Timestamp("1995-01-01"), end=END)
    end = min(END, panel.index[-1])
    cash = panel["SHV"].ffill().pct_change().dropna()
    od, cy = H.load_open_close()
    intr = (cy / od - 1.0).reindex(panel.index)
    on = (od / cy.shift(1) - 1.0).reindex(panel.index)
    spy_daily = panel["SPY"].ffill().pct_change()

    out = {"windows": {"clean": [str(CLEAN.date()), str(end.date())],
                       "ext": [str(EXT.date()), str(end.date())]},
           "conv": CONV, "anchor": ANCHOR}

    # ---- synthetic TIP ----
    print("Building CPI-aware synthetic TIP ...")
    syn_daily, syn_price_m, cpi_infl = build_synthetic_tip(panel)
    out["synthetic_tip"] = {
        "construction": "monthly syn TIPS total return = IEF nominal total return + realized monthly CPI(CPIAUCSL) inflation; cumulated to price index; canary-only use",
        "validation": validate_synthetic(panel, syn_price_m),
        "syn_signal_start": str(syn_price_m.dropna().index[12].date()) if syn_price_m.dropna().shape[0] > 12 else None,
    }
    panel_syn = panel.copy()
    panel_syn["TIP"] = syn_daily

    # ---- ANCHOR GATE ----
    print("Anchor gate ...")
    reset_cpm_canary(); reset_bull_canary()
    cpm_p = run_cpm(panel, intr, on, EXT, end)
    bull_p = run_bull(panel, intr, on, EXT, end)
    common = cpm_p.index.intersection(bull_p.index)
    cpm_p = cpm_p.reindex(common); bull_p = bull_p.reindex(common)
    blend_p = 0.6 * cpm_p + 0.4 * bull_p
    a_cpm = metrics(win(cpm_p, CLEAN, end), cash)["sharpe"]
    a_bull = metrics(win(bull_p, CLEAN, end), cash)["sharpe"]
    a_blend = metrics(win(blend_p, CLEAN, end), cash)["sharpe"]
    anchor_ok = (abs(a_cpm - ANCHOR["cpm"]) < 5e-4 and abs(a_bull - ANCHOR["bull"]) < 5e-4
                 and abs(a_blend - ANCHOR["blend"]) < 5e-4)
    out["anchor_check"] = {"cpm": a_cpm, "bull": a_bull, "blend": a_blend, "ok": anchor_ok}
    print(f"  anchor cpm={a_cpm} bull={a_bull} blend={a_blend} OK={anchor_ok}")
    assert anchor_ok, "ANCHOR MISMATCH - aborting"

    MODES = ["tip", "hygortip", "none"]

    # ---- CPM sleeve variants ----
    print("CPM sleeve variants ...")
    cpm_series = {}  # (mode, ext_proxy) -> series
    out["cpm_sleeve"] = {}
    for mode in MODES:
        set_cpm_canary(mode); reset_bull_canary()
        # clean window: real TIP (panel)
        s = run_cpm(panel, intr, on, EXT, end)
        cpm_series[(mode, "real")] = s
        rec = {"clean": metrics(win(s, CLEAN, end), cash),
               "ext_prodTIP": metrics(win(s, EXT, end), cash)}
        # ext window with synthetic TIP (only matters for tip-using modes)
        if mode in ("tip", "hygortip"):
            s_syn = run_cpm(panel_syn, intr, on, EXT, end)
            cpm_series[(mode, "syn")] = s_syn
            rec["ext_synTIP"] = metrics(win(s_syn, EXT, end), cash)
        out["cpm_sleeve"][mode] = rec
    reset_cpm_canary()

    # ---- BULL sleeve variants ----
    print("BULL sleeve variants ...")
    bull_series = {}
    out["bull_sleeve"] = {}
    for mode in MODES:
        reset_cpm_canary(); set_bull_canary(mode)
        s = run_bull(panel, intr, on, EXT, end)
        bull_series[(mode, "real")] = s
        rec = {"clean": metrics(win(s, CLEAN, end), cash),
               "ext_prodTIP": metrics(win(s, EXT, end), cash)}
        if mode in ("tip", "hygortip"):
            s_syn = run_bull(panel_syn, intr, on, EXT, end)
            bull_series[(mode, "syn")] = s_syn
            rec["ext_synTIP"] = metrics(win(s_syn, EXT, end), cash)
        out["bull_sleeve"][mode] = rec
    reset_bull_canary()

    # ---- 60/40 blend variants ----
    print("60/40 blend variants ...")
    out["blend_6040"] = {}
    # joint variation (both sleeves same canary), real TIP
    for mode in MODES:
        c = cpm_series[(mode, "real")]; b = bull_series[(mode, "real")]
        ci = c.index.intersection(b.index)
        bl = 0.6 * c.reindex(ci) + 0.4 * b.reindex(ci)
        out["blend_6040"][f"joint_{mode}"] = {
            "clean": metrics(win(bl, CLEAN, end), cash),
            "ext_prodTIP": metrics(win(bl, EXT, end), cash)}
    # CPM-only variation (BULL held at prod hygortip)
    b_prod = bull_series[("hygortip", "real")]
    for mode in MODES:
        c = cpm_series[(mode, "real")]
        ci = c.index.intersection(b_prod.index)
        bl = 0.6 * c.reindex(ci) + 0.4 * b_prod.reindex(ci)
        out["blend_6040"][f"cpm_{mode}__bull_prod"] = {
            "clean": metrics(win(bl, CLEAN, end), cash)}
    # BULL-only variation (CPM held at prod hygortip)
    c_prod = cpm_series[("hygortip", "real")]
    for mode in MODES:
        b = bull_series[(mode, "real")]
        ci = c_prod.index.intersection(b.index)
        bl = 0.6 * c_prod.reindex(ci) + 0.4 * b.reindex(ci)
        out["blend_6040"][f"cpm_prod__bull_{mode}"] = {
            "clean": metrics(win(bl, CLEAN, end), cash)}

    # ---- bootstrap: HYG-OR-TIP vs TIP-only (clean) ----
    print("Bootstrap noise ...")
    out["bootstrap_clean"] = {}
    out["bootstrap_clean"]["cpm_hygortip_vs_tip"] = block_bootstrap_sharpe_diff(
        win(cpm_series[("hygortip", "real")], CLEAN, end),
        win(cpm_series[("tip", "real")], CLEAN, end))
    out["bootstrap_clean"]["bull_hygortip_vs_tip"] = block_bootstrap_sharpe_diff(
        win(bull_series[("hygortip", "real")], CLEAN, end),
        win(bull_series[("tip", "real")], CLEAN, end))
    blh = 0.6 * cpm_series[("hygortip", "real")] + 0.4 * bull_series[("hygortip", "real")]
    blt = 0.6 * cpm_series[("tip", "real")] + 0.4 * bull_series[("tip", "real")]
    out["bootstrap_clean"]["blend_hygortip_vs_tip"] = block_bootstrap_sharpe_diff(
        win(blh, CLEAN, end), win(blt, CLEAN, end))

    # ---- C x V redundancy cross-check (BULL) ----
    # Does the rv_60d vol gate make the BULL canary redundant? Compare BULL
    # none / tip / hygortip (all keep trend + vol gate ON, prod GATE_RV60).
    out["bull_canary_redundancy"] = {
        "note": "all BULL variants keep SPY trend + rv_60d vol gate; only canary toggled",
        "clean_sharpe": {m: out["bull_sleeve"][m]["clean"]["sharpe"] for m in MODES},
        "clean_calmar": {m: out["bull_sleeve"][m]["clean"]["calmar"] for m in MODES},
        "clean_maxdd": {m: out["bull_sleeve"][m]["clean"]["maxdd"] for m in MODES},
        "prior_CxV_calmar_delta": -0.018,
    }

    # ---- state analysis (override months) ----
    print("State analysis ...")
    sig_real = canary_signal_table(panel, "TIP")
    sig_syn = canary_signal_table(panel_syn, "TIP")
    out["state_analysis"] = {
        "definition": "override = month where TIP 13612U<=0 AND HYG 13612U>0 (HYG-OR-TIP stays risk-on, TIP-only de-risks)",
        "clean_realTIP": {
            "cpm": override_analysis(panel, sig_real, cpm_series[("hygortip", "real")],
                                     "cpm", CLEAN, end, spy_daily),
            "bull": override_analysis(panel, sig_real, bull_series[("hygortip", "real")],
                                      "bull", CLEAN, end, spy_daily),
        },
        "ext_realTIP": {
            "cpm": override_analysis(panel, sig_real, cpm_series[("hygortip", "real")],
                                     "cpm", EXT, end, spy_daily),
        },
        "ext_synTIP": {
            "cpm": override_analysis(panel_syn, sig_syn, cpm_series.get(("hygortip", "syn"), cpm_series[("hygortip", "real")]),
                                     "cpm", EXT, end, spy_daily),
        },
    }

    # ---- attribution: HYG-OR-TIP minus TIP-only return concentration ----
    # Sum of daily return diff (hygortip - tip) by calendar year, clean window.
    def yearly_diff(a, b):
        common = a.index.intersection(b.index)
        d = (a.reindex(common).fillna(0.0) - b.reindex(common).fillna(0.0))
        d = win(d, CLEAN, end)
        g = (1.0 + d).groupby(d.index.year).prod() - 1.0
        return {int(y): round(float(v) * 100, 3) for y, v in g.items()}
    out["yearly_diff_clean_pct"] = {
        "cpm_hygortip_minus_tip": yearly_diff(cpm_series[("hygortip", "real")], cpm_series[("tip", "real")]),
        "bull_hygortip_minus_tip": yearly_diff(bull_series[("hygortip", "real")], bull_series[("tip", "real")]),
    }

    # ---- stagflation episodes (real-data, clean window) ----
    print("Stagflation episodes ...")
    episodes = {
        "2022_full": ("2022-01-01", "2022-12-31"),
        "2021H2": ("2021-07-01", "2021-12-31"),
        "2022H1_worst": ("2022-01-01", "2022-06-30"),
    }
    stag = {}
    for ename, (s0, s1) in episodes.items():
        s0t, s1t = pd.Timestamp(s0), pd.Timestamp(s1)
        rec = {}
        for sleeve_name, ser_map in [("cpm", cpm_series), ("bull", bull_series)]:
            for mode in ("tip", "hygortip"):
                ser = ser_map[(mode, "real")]
                rec[f"{sleeve_name}_{mode}"] = {
                    "ret_pct": round(period_total_return(ser, s0t, s1t) * 100, 2),
                    "maxdd_pct": round(period_maxdd(ser, s0t, s1t) * 100, 2)}
        for mode in ("tip", "hygortip"):
            bl = 0.6 * cpm_series[(mode, "real")] + 0.4 * bull_series[(mode, "real")]
            rec[f"blend_{mode}"] = {
                "ret_pct": round(period_total_return(bl, s0t, s1t) * 100, 2),
                "maxdd_pct": round(period_maxdd(bl, s0t, s1t) * 100, 2)}
        # override months in this episode
        ov = [str(me.date()) for me in sig_real.index
              if s0t <= me <= s1t and pd.notna(sig_real.loc[me, "hyg"]) and pd.notna(sig_real.loc[me, "tip"])
              and sig_real.loc[me, "tip"] <= 0 < sig_real.loc[me, "hyg"]]
        # also count pure HYG and TIP signs across the episode
        signs = [{"month": str(me.date()),
                  "hyg": round(float(sig_real.loc[me, "hyg"]), 4),
                  "tip": round(float(sig_real.loc[me, "tip"]), 4)}
                 for me in sig_real.index if s0t <= me <= s1t and pd.notna(sig_real.loc[me, "hyg"]) and pd.notna(sig_real.loc[me, "tip"])]
        rec["override_months"] = ov
        rec["canary_signs"] = signs
        stag[ename] = rec
    out["stagflation"] = stag
    out["stagflation_1970s"] = {
        "feasible": False,
        "reason": "panel starts 1995-01; risky ETF universe and HYG credit proxy (VWEHX from 1980) do not extend to 1973-74/1977-82; nominal-bond series (IEF stitch) starts 1993-10 so even a CPI-aware synthetic TIP cannot be built pre-1994. 1970s sleeve and even canary-signal backtest is infeasible.",
        "handling": "FALLBACK: verdict rests on real-TIP era (2000-06+ signal; clean window 2008+), with 2022 as the in-sample real-data stagflation episode. 1970s IEF-proxy result is NOT computed and does NOT drive the decision.",
    }

    def _ser(o):
        if isinstance(o, (np.bool_,)):
            return bool(o)
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, (np.floating,)):
            return float(o)
        raise TypeError(str(type(o)))
    OUT_JSON = ROOT / "research" / "canary_variant_test_findings.json"
    OUT_JSON.write_text(json.dumps(out, indent=2, default=_ser))
    print(f"Wrote {OUT_JSON}")
    return out


if __name__ == "__main__":
    main()
