#!/usr/bin/env python3
"""
Stagflation 1970s -- CPM CROSS-ASSET structural-resilience test.

QUESTION
--------
The prior test (stagflation_1970s_tip_canary.py) gated a SINGLE EQUITY sleeve
(S&P 500) by a canary; equity-only de-risking still ate large real drawdowns.
This test asks the design question: is CPM's CROSS-ASSET momentum + absolute-
momentum screen STRUCTURALLY stagflation-resilient -- does cross-asset 13612U/
trend ranking rotate into the 1970s inflation winners (gold, commodities) while
the positive-trend screen + partial-safe fallback de-risks equities/bonds?

This runs CPM-like logic (as close to production cpm_live.py as a reduced 1970s
public-data universe allows) WITHOUT the TIP/HYG canary (those assets do not
exist pre-1980). De-risking here comes purely from the absolute-momentum
(positive-trend) screen + strict-style partial-safe fallback -- exactly the
mechanism whose stagflation behavior we want to isolate.

REDUCED 1970s RISKY UNIVERSE (cross-asset; monthly total-return proxies)
-----------------------------------------------------------------------
  1. US equity         : S&P 500 total return (Shiller reconstruction).
                         [production analog: QQQ / SPHQ US sleeve]
  2. Gold              : London gold price; TR = price return, no carry.
                         [production analog: GLD]
  3. Commodities       : BROAD commodity index proxy = PPIACO (Producer Price
                         Index, all commodities; spot) + 3m T-bill collateral
                         yield -> a GSCI-like COLLATERALIZED total-return proxy.
                         [production analog: DBC]
  4. Long Treasury     : FRED GS20 (20y CMT yield) -> par-bond duration TR.
                         [production analog: TLT]
  (International equity / MSCI EAFE OMITTED: no free monthly EAFE TR series for
   the 1970s was sourceable without a paid key. Documented as a limitation; the
   core hypothesis -- gold/commodity rotation under the abs-mom screen -- is
   fully testable without it.)

SAFE POOL (best-of by 13612U, mirrors production SHV/IEF)
--------------------------------------------------------
  - Cash               : FRED TB3MS (3m T-bill).         [production analog: SHV]
  - Intermediate Treasury: FRED GS5 (5y CMT) par-bond TR. [production analog: IEF]

DATA SOURCES (all public; cached under research/data_1970s/)
------------------------------------------------------------
  S&P 500     : Shiller ie_data (datahub mirror) price+dividend -> monthly TR.
  Gold        : datahub core/gold-prices monthly.csv (London gold, USD/oz),
                from 1833; floats from 1968 (controlled at ~$35 until Aug 1971).
  Commodities : FRED PPIACO (all-commodities PPI, 1913+) spot + TB3MS collateral.
  Long Treas. : FRED GS20 (20y CMT yield, 1953+).
  Interm Treas: FRED GS5 (5y CMT yield, 1953+).
  Cash        : FRED TB3MS (3m T-bill).
  CPI         : FRED CPIAUCSL (for real-return context only).

CONSTRUCTIONS
-------------
  S&P 500 TR        : (P_t - P_{t-1} + D_t/12)/P_{t-1}   (Shiller).
  Bond TR (par N)   : income=y_{t-1}/12 ; price_ret=-Dmod_{t-1}*(y_t-y_{t-1}) ;
                      first-order duration (convexity omitted).
  Gold TR           : gold_price.pct_change()            (no carry).
  Commodity TR      : PPIACO.pct_change() + TB3MS/1200   (collateralized proxy).

CPM-LIKE ENGINE (mirrors cpm_live.compute_target_weights, reduced universe)
---------------------------------------------------------------------------
  monthly price index per risky asset (cumulated TR).
  RANKER (production): vol-adjusted Faber 10m SMA distance:
     faber(A)  = (P - SMA10(P)) / SMA10(P)
     score(A)  = faber(A) / vol(A)          vol = trailing 12m std * sqrt(12)
                 (production uses 252-day daily vol; monthly analog = 12m std)
  TOP-HALF        : top_k = ceil(N/2) by score (N=4 -> top_k=2).
  ABS-MOM SCREEN  : keep only picks with raw faber(A) > 0 (positive trend).
  INVERSE-VOL     : weight survivors by 1/sigma_i ; sigma from trailing 24m
                    covariance diagonal (production: 504 trading days ~24m).
  PARTIAL-SAFE    : strict-style breadth scaling. Production divides by 4
                    (=top_k of its 8-asset universe). Reduced universe scales by
                    its own top_k: risky_fraction = min(n_picks, top_k)/top_k ;
                    remainder -> best safe (T-bill or GS5 by 13612U).
  NO CANARY       : TIP/HYG unavailable pre-1980; canary disabled by design so
                    the abs-mom screen + partial-safe is the sole de-risk lever.
  LAG             : signal as of end of month t-1 applied to month t (1m lag).

BASELINES
---------
  buyhold_equity : S&P 500 TR buy & hold.
  sixty_forty    : 60% S&P 500 TR + 40% GS10 Treasury TR, monthly rebalanced.

OUTPUT
------
  research/stagflation_1970s_cpm_crossasset_findings.json
  (markdown findings written separately)
"""
from __future__ import annotations
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
DATA = HERE / "data_1970s"

EVAL_START = pd.Period("1969-02", "M")   # 13m momentum warmup from 1968-01 gold float
EVAL_END = pd.Period("1985-12", "M")
STAG_WINDOWS = {
    "bear_1973_74": (pd.Period("1973-01", "M"), pd.Period("1974-12", "M")),
    "stagflation_1977_82": (pd.Period("1977-01", "M"), pd.Period("1982-12", "M")),
}
RISKY = ["us_equity", "gold", "commodities", "long_treasury"]
SAFE_POOL = ["cash", "interm_treasury"]
TOP_K = math.ceil(len(RISKY) / 2)  # = 2


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------
def _load_fred(name, col):
    df = pd.read_csv(DATA / name)
    df.columns = ["date", col]
    df["date"] = pd.to_datetime(df["date"]).dt.to_period("M")
    return df.set_index("date")[col].astype(float)


def load_inputs():
    cpi = _load_fred("fred_CPIAUCSL.csv", "CPIAUCSL")
    gs5 = _load_fred("fred_GS5.csv", "GS5") / 100.0
    gs10 = _load_fred("fred_GS10.csv", "GS10") / 100.0
    gs20 = _load_fred("fred_GS20.csv", "GS20") / 100.0
    tb3 = _load_fred("fred_TB3MS.csv", "TB3MS") / 100.0
    ppi = _load_fred("fred_PPIACO.csv", "PPIACO")

    g = pd.read_csv(DATA / "gold_monthly.csv")
    g["Date"] = pd.to_datetime(g["Date"]).dt.to_period("M")
    gold = g.set_index("Date")["Price"].astype(float)

    sh = pd.read_csv(DATA / "shiller_sp500_monthly.csv")
    sh["Date"] = pd.to_datetime(sh["Date"]).dt.to_period("M")
    sh = sh.set_index("Date")
    sp_p = pd.to_numeric(sh["SP500"], errors="coerce")
    sp_d = pd.to_numeric(sh["Dividend"], errors="coerce")
    sp_p = sp_p[sp_p > 0]
    return dict(cpi=cpi, gs5=gs5, gs10=gs10, gs20=gs20, tb3=tb3, ppi=ppi,
                gold=gold, sp_p=sp_p, sp_d=sp_d)


# ---------------------------------------------------------------------------
# Constructions (reused from stagflation_1970s_tip_canary.py)
# ---------------------------------------------------------------------------
def par_bond_mod_duration(y, N, freq=2):
    y = float(y)
    m = int(round(N * freq))
    i = y / freq
    c = y / freq
    ts = np.arange(1, m + 1)
    cf = np.full(m, c, dtype=float)
    cf[-1] += 1.0
    pv = cf.copy() if abs(i) < 1e-12 else cf / (1.0 + i) ** ts
    price = pv.sum()
    dmac_years = ((ts * pv).sum() / price) / freq
    return dmac_years / (1.0 + i)


def bond_total_return(yld: pd.Series, N: int) -> pd.Series:
    yld = yld.dropna().sort_index()
    dmod = yld.apply(lambda v: par_bond_mod_duration(v, N))
    y_prev = yld.shift(1)
    dy = yld - y_prev
    return (y_prev / 12.0 - dmod.shift(1) * dy).dropna()


def sp500_total_return(sp_p, sp_d):
    d = sp_d.reindex(sp_p.index)
    p_prev = sp_p.shift(1)
    return ((sp_p - p_prev + d / 12.0) / p_prev).dropna()


def cum_index(tr, base=100.0):
    return base * (1.0 + tr).cumprod()


# ---------------------------------------------------------------------------
# Signals (mirror cpm_live)
# ---------------------------------------------------------------------------
def sig_13612U_at(price: pd.Series, asof: pd.Period) -> float:
    p = price.loc[:asof].dropna()
    if len(p) < 13:
        return np.nan
    last = p.iloc[-1]
    return (last / p.iloc[-2] - 1 + last / p.iloc[-4] - 1
            + last / p.iloc[-7] - 1 + last / p.iloc[-13] - 1) / 4.0


def faber_at(price: pd.Series, asof: pd.Period) -> float:
    """Faber 10m SMA distance (price - SMA10)/SMA10."""
    p = price.loc[:asof].dropna()
    if len(p) < 10:
        return np.nan
    sma = p.iloc[-10:].mean()
    return float(p.iloc[-1] / sma - 1.0)


def vol_12m_at(ret: pd.Series, asof: pd.Period) -> float:
    r = ret.loc[:asof].dropna().iloc[-12:]
    if len(r) < 6:
        return np.nan
    v = float(r.std(ddof=0) * np.sqrt(12))
    return v if v > 1e-9 else 1.0


def inv_vol_weights_at(rets: pd.DataFrame, picks, asof, lookback=24) -> dict:
    if not picks:
        return {}
    sub = rets[picks].loc[:asof].dropna(how="all").iloc[-lookback:]
    if len(sub) < 6:
        return {t: 1.0 / len(picks) for t in picks}
    sigma = sub.std(ddof=0) * np.sqrt(12)
    inv = {}
    for t in picks:
        s = float(sigma.get(t, np.nan))
        if not np.isfinite(s) or s < 1e-12:
            return {tt: 1.0 / len(picks) for tt in picks}
        inv[t] = 1.0 / s
    z = sum(inv.values())
    return {t: inv[t] / z for t in picks}


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------
def metrics(r: pd.Series, rf: pd.Series) -> dict:
    r = r.dropna()
    if r.empty:
        return {}
    n = len(r)
    growth = float((1.0 + r).prod())
    cagr = growth ** (12.0 / n) - 1.0
    vol = float(r.std(ddof=0) * np.sqrt(12))
    ex = r - rf.reindex(r.index).fillna(0.0)
    ex_vol = float(ex.std(ddof=0) * np.sqrt(12))
    sharpe = float(ex.mean() * 12 / ex_vol) if ex_vol > 0 else float("nan")
    eq = (1.0 + r).cumprod()
    maxdd = float((eq / eq.cummax() - 1.0).min())
    return {"n_months": n, "total_return_pct": round((growth - 1) * 100, 2),
            "cagr_pct": round(cagr * 100, 2), "vol_pct": round(vol * 100, 2),
            "sharpe": round(sharpe, 3), "maxdd_pct": round(maxdd * 100, 2)}


# ---------------------------------------------------------------------------
# Reusable CPM-like engine (for robustness variants)
# ---------------------------------------------------------------------------
def run_engine(tr, px, rets_df, risky, safe_pool, eval_months,
               weighting="inv_vol", top_k=None):
    """Run the CPM-like cross-asset engine. weighting in {'inv_vol','equal'}.
    Returns (strat_ret Series, holdings DataFrame)."""
    top_k = top_k or math.ceil(len(risky) / 2)
    sret, holds = {}, {}
    for t in eval_months:
        prev = t - 1
        faber, score = {}, {}
        for a in risky:
            f = faber_at(px[a], prev)
            faber[a] = f
            if pd.notna(f):
                v = vol_12m_at(tr[a], prev)
                score[a] = f / v if (v and v > 0) else np.nan
        score = {k: v for k, v in score.items() if pd.notna(v)}
        ss = {s: sig_13612U_at(px[s], prev) for s in safe_pool}
        ss = {k: v for k, v in ss.items() if pd.notna(v)}
        safe = max(ss, key=ss.get) if ss else "cash"
        w = {}
        if score:
            ranked = sorted(score, key=score.get, reverse=True)[:top_k]
            picks = [a for a in ranked if faber.get(a, -1e9) > 0]
            if picks:
                if weighting == "equal":
                    ivw = {a: 1.0 / len(picks) for a in picks}
                else:
                    ivw = inv_vol_weights_at(rets_df, picks, prev)
                rfrac = min(len(picks), top_k) / top_k
                for a, wt in ivw.items():
                    w[a] = wt * rfrac
                if 1 - rfrac > 0:
                    w[safe] = w.get(safe, 0.0) + (1 - rfrac)
            else:
                w[safe] = 1.0
        else:
            w[safe] = 1.0
        ret, ok = 0.0, True
        for a, wt in w.items():
            ra = tr[a].get(t, np.nan)
            if pd.isna(ra):
                ok = False
                break
            ret += wt * ra
        if ok:
            sret[t] = ret
            holds[t] = w
    s = pd.Series(sret).sort_index()
    h = pd.DataFrame(holds).T.fillna(0.0)
    return s, h


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    d = load_inputs()

    # --- asset monthly total returns ---
    tr = {}
    tr["us_equity"] = sp500_total_return(d["sp_p"], d["sp_d"])
    tr["gold"] = d["gold"].pct_change().dropna()
    tb_m = d["tb3"] / 12.0
    ppi_ret = d["ppi"].pct_change()
    idxc = ppi_ret.index.intersection(tb_m.index)
    tr["commodities"] = (ppi_ret.reindex(idxc) + tb_m.reindex(idxc)).dropna()
    tr["long_treasury"] = bond_total_return(d["gs20"], N=20)
    tr["interm_treasury"] = bond_total_return(d["gs5"], N=5)
    tr["cash"] = tb_m.dropna()
    tr_gs10 = bond_total_return(d["gs10"], N=7)  # 60/40 bond leg

    # price indices
    px = {k: cum_index(v) for k, v in tr.items()}
    rets_df = pd.DataFrame({k: tr[k] for k in RISKY})

    rf = tr["cash"]

    # --- monthly CPM-like allocation with 1m lag ---
    eval_months = pd.period_range(EVAL_START, EVAL_END, freq="M")
    strat_ret = {}
    holdings = {}  # month -> dict weights (applied month)
    regime = {}
    for t in eval_months:
        prev = t - 1
        # ranker score = faber / vol over risky universe, as of prev
        faber = {}
        score = {}
        for a in RISKY:
            f = faber_at(px[a], prev)
            faber[a] = f
            if pd.notna(f):
                v = vol_12m_at(tr[a], prev)
                score[a] = f / v if (v and v > 0) else np.nan
        score = {k: v for k, v in score.items() if pd.notna(v)}
        # best safe by 13612U as of prev
        safe_scores = {s: sig_13612U_at(px[s], prev) for s in SAFE_POOL}
        safe_scores = {k: v for k, v in safe_scores.items() if pd.notna(v)}
        safe = max(safe_scores, key=safe_scores.get) if safe_scores else "cash"

        w = {}
        if score:
            ranked = sorted(score, key=score.get, reverse=True)
            top = ranked[:TOP_K]
            picks = [a for a in top if faber.get(a, -1e9) > 0]  # abs-mom screen
            if picks:
                ivw = inv_vol_weights_at(rets_df, picks, prev)
                risky_fraction = min(len(picks), TOP_K) / TOP_K
                for a, wt in ivw.items():
                    w[a] = wt * risky_fraction
                sf = 1.0 - risky_fraction
                if sf > 0:
                    w[safe] = w.get(safe, 0.0) + sf
                regime[t] = "RISK_ON"
            else:
                w[safe] = 1.0
                regime[t] = "DEFENSIVE"
        else:
            w[safe] = 1.0
            regime[t] = "DEFENSIVE"

        # realize month-t return
        ret = 0.0
        ok = True
        for a, wt in w.items():
            ra = tr[a].get(t, np.nan)
            if pd.isna(ra):
                ok = False
                break
            ret += wt * ra
        if not ok:
            continue
        strat_ret[t] = ret
        holdings[t] = w

    strat = pd.Series(strat_ret).sort_index()

    # --- baselines ---
    bh = tr["us_equity"].reindex(eval_months).dropna()
    sf_idx = tr["us_equity"].index.intersection(tr_gs10.index)
    sixty40 = (0.6 * tr["us_equity"].reindex(sf_idx) + 0.4 * tr_gs10.reindex(sf_idx)).dropna()
    sixty40 = sixty40.reindex(eval_months).dropna()

    # --- output ---
    out = {}
    out["meta"] = {
        "eval_window": [str(EVAL_START), str(EVAL_END)],
        "stag_windows": {k: [str(a), str(b)] for k, (a, b) in STAG_WINDOWS.items()},
        "risky_universe": RISKY, "safe_pool": SAFE_POOL, "top_k": TOP_K,
        "canary": "DISABLED (TIP/HYG unavailable pre-1980; abs-mom screen + partial-safe is sole de-risk lever)",
        "data_sources": {
            "us_equity": "Shiller ie_data (datahub mirror); price+dividend -> monthly TR",
            "gold": "datasets/gold-prices monthly.csv (World Bank Pink Sheet, USD/oz; GENUINE monthly from 1960+, pre-1960 annual-repeated and unused); TR=price return, no carry; floats from 1968 (~$35 peg until Aug 1971)",
            "commodities": "FRED PPIACO (all-commodities PPI, 1913+) spot + FRED TB3MS collateral -> GSCI-like collateralized TR proxy",
            "long_treasury": "FRED GS20 (20y CMT yield) -> par-bond duration TR (N=20)",
            "interm_treasury": "FRED GS5 (5y CMT yield) -> par-bond duration TR (N=5)",
            "cash": "FRED TB3MS (3m T-bill)",
            "cpi": "FRED CPIAUCSL (real-return context only)",
            "sixty40_bond_leg": "FRED GS10 (10y CMT) -> par-bond TR (N=7)",
        },
        "constructions": {
            "sp500_tr": "(P_t - P_{t-1} + D_t/12)/P_{t-1}",
            "bond_tr": "income=y_{t-1}/12 ; price_ret=-Dmod_{t-1}*(y_t-y_{t-1}) ; duration-only",
            "gold_tr": "gold_price.pct_change() (no carry)",
            "commodity_tr": "PPIACO.pct_change() + TB3MS/1200 (collateralized)",
            "ranker": "vol-adjusted Faber: (P-SMA10)/SMA10 / (trailing 12m std*sqrt(12))",
            "abs_mom_screen": "keep picks with raw faber>0",
            "weights": "inverse-vol over picks (trailing 24m cov diag); partial-safe risky_fraction=min(n_picks,top_k)/top_k, remainder->best safe(13612U)",
            "lag": "signal end of month t-1 applied to month t",
        },
        "caveats": [
            "International equity (MSCI EAFE) OMITTED: no free monthly EAFE TR for the 1970s sourceable without paid key.",
            "Commodity sleeve = PPIACO spot + T-bill collateral, NOT a true futures index: no roll/convenience yield, producer-price smoothing, not directly investable. A real GSCI (energy-heavy) would have shown LARGER 1973/1979 oil-shock spikes; PPIACO understates commodity-momentum amplitude. (WTI-based sensitivity reported separately.)",
            "Gold TR = price only; LBMA price effectively pegged ~$35 until Aug 1971 (no investable float for US persons until 1975), so pre-1975 gold returns are partly non-investable.",
            "Bond TR is first-order par-bond duration (convexity omitted); long-Treasury N=20 is an assumption.",
            "Equity = Shiller monthly-average price (not daily close).",
            "Reduced 4-asset risky universe (top_k=2) vs production 8-asset (top_k=4): partial-safe denominator scaled to local top_k; fewer diversifiers than production.",
            "No transaction costs modeled.",
            "Canary disabled by design (see meta.canary).",
        ],
    }

    variants = {"cpm_crossasset": strat, "buyhold_equity": bh, "sixty_forty": sixty40}
    out["full_period"] = {k: metrics(v, rf) for k, v in variants.items()}

    out["stagflation_windows"] = {}
    for wname, (a, b) in STAG_WINDOWS.items():
        rec = {}
        for k, v in variants.items():
            rec[k] = metrics(v.loc[a:b], rf)
        bh_dd = rec["buyhold_equity"].get("maxdd_pct")
        s40_dd = rec["sixty_forty"].get("maxdd_pct")
        rec["cpm_dd_avoided_vs_buyhold_pp"] = round(rec["cpm_crossasset"]["maxdd_pct"] - bh_dd, 2)
        rec["cpm_dd_avoided_vs_6040_pp"] = round(rec["cpm_crossasset"]["maxdd_pct"] - s40_dd, 2)
        out["stagflation_windows"][wname] = rec

    # --- holdings / rotation analysis ---
    hold_df = pd.DataFrame(holdings).T.fillna(0.0).reindex(columns=RISKY + SAFE_POOL, fill_value=0.0)
    # average weights overall + per stagflation window
    out["rotation"] = {
        "avg_weights_full": {k: round(float(hold_df[k].mean()), 4) for k in hold_df.columns},
        "windows": {},
        "inflation_winner_exposure_note": "gold+commodities = the 1970s inflation winners",
    }
    out["rotation"]["avg_weights_full"]["risky_total"] = round(
        float(hold_df[RISKY].sum(axis=1).mean()), 4)
    for wname, (a, b) in STAG_WINDOWS.items():
        sub = hold_df.loc[a:b]
        if sub.empty:
            continue
        aw = {k: round(float(sub[k].mean()), 4) for k in hold_df.columns}
        aw["inflation_winners_gold_plus_commod"] = round(
            float((sub["gold"] + sub["commodities"]).mean()), 4)
        aw["safe_total"] = round(float(sub[SAFE_POOL].sum(axis=1).mean()), 4)
        # months with any gold or commodity exposure
        aw["pct_months_holding_gold"] = round(float((sub["gold"] > 1e-6).mean()) * 100, 1)
        aw["pct_months_holding_commod"] = round(float((sub["commodities"] > 1e-6).mean()) * 100, 1)
        aw["pct_months_holding_inflation_winner"] = round(
            float(((sub["gold"] + sub["commodities"]) > 1e-6).mean()) * 100, 1)
        out["rotation"]["windows"][wname] = aw

    # holdings calendar (every month) for stagflation windows
    out["holdings_calendar"] = {}
    for wname, (a, b) in STAG_WINDOWS.items():
        rows = []
        for t in pd.period_range(a, b, freq="M"):
            if t not in hold_df.index:
                continue
            w = {k: round(float(hold_df.loc[t, k]), 3) for k in hold_df.columns
                 if hold_df.loc[t, k] > 1e-6}
            rows.append({"month": str(t), "regime": regime.get(t),
                         "weights": w,
                         "strat_ret_pct": round(float(strat.get(t, np.nan)) * 100, 2)
                         if pd.notna(strat.get(t, np.nan)) else None})
        out["holdings_calendar"][wname] = rows

    # --- abs-mom screen contribution: compare to no-screen (always hold top_k) ---
    ns_ret = {}
    for t in eval_months:
        prev = t - 1
        faber = {a: faber_at(px[a], prev) for a in RISKY}
        score = {}
        for a in RISKY:
            if pd.notna(faber[a]):
                v = vol_12m_at(tr[a], prev)
                score[a] = faber[a] / v if (v and v > 0) else np.nan
        score = {k: v for k, v in score.items() if pd.notna(v)}
        if not score:
            continue
        ranked = sorted(score, key=score.get, reverse=True)[:TOP_K]
        ivw = inv_vol_weights_at(rets_df, ranked, prev)
        ret = 0.0
        ok = True
        for a, wt in ivw.items():
            ra = tr[a].get(t, np.nan)
            if pd.isna(ra):
                ok = False
                break
            ret += wt * ra
        if ok:
            ns_ret[t] = ret
    noscreen = pd.Series(ns_ret).sort_index()
    out["abs_mom_contribution"] = {
        "definition": "no-screen = same ranker+top_k+inv-vol but ALWAYS fully invested in top_k (no positive-trend filter, no partial-safe). Difference isolates the abs-mom screen + partial-safe.",
        "with_screen": metrics(strat, rf),
        "no_screen": metrics(noscreen, rf),
    }
    for wname, (a, b) in STAG_WINDOWS.items():
        out["abs_mom_contribution"].setdefault("windows", {})[wname] = {
            "with_screen": metrics(strat.loc[a:b], rf),
            "no_screen": metrics(noscreen.loc[a:b], rf),
        }

    # --- commodity rotation contribution: drop commodities+gold from universe ---
    risky_noinfl = ["us_equity", "long_treasury"]
    rd2 = rets_df  # reuse
    ni_ret = {}
    for t in eval_months:
        prev = t - 1
        faber = {a: faber_at(px[a], prev) for a in risky_noinfl}
        score = {}
        for a in risky_noinfl:
            if pd.notna(faber[a]):
                v = vol_12m_at(tr[a], prev)
                score[a] = faber[a] / v if (v and v > 0) else np.nan
        score = {k: v for k, v in score.items() if pd.notna(v)}
        safe_scores = {s: sig_13612U_at(px[s], prev) for s in SAFE_POOL}
        safe_scores = {k: v for k, v in safe_scores.items() if pd.notna(v)}
        safe = max(safe_scores, key=safe_scores.get) if safe_scores else "cash"
        topk2 = math.ceil(len(risky_noinfl) / 2)
        w = {}
        if score:
            ranked = sorted(score, key=score.get, reverse=True)[:topk2]
            picks = [a for a in ranked if faber.get(a, -1e9) > 0]
            if picks:
                ivw = inv_vol_weights_at(rd2, picks, prev)
                rf_frac = min(len(picks), topk2) / topk2
                for a, wt in ivw.items():
                    w[a] = wt * rf_frac
                if 1 - rf_frac > 0:
                    w[safe] = w.get(safe, 0) + (1 - rf_frac)
            else:
                w[safe] = 1.0
        else:
            w[safe] = 1.0
        ret = 0.0
        ok = True
        for a, wt in w.items():
            ra = tr[a].get(t, np.nan)
            if pd.isna(ra):
                ok = False
                break
            ret += wt * ra
        if ok:
            ni_ret[t] = ret
    noinfl = pd.Series(ni_ret).sort_index()
    out["commodity_rotation_contribution"] = {
        "definition": "no-inflation-assets universe = drop gold+commodities (risky={us_equity,long_treasury}); same engine. Difference vs full = value of cross-asset rotation into inflation winners.",
        "full_universe": metrics(strat, rf),
        "no_inflation_assets": metrics(noinfl, rf),
        "windows": {w: {"full_universe": metrics(strat.loc[a:b], rf),
                        "no_inflation_assets": metrics(noinfl.loc[a:b], rf)}
                    for w, (a, b) in STAG_WINDOWS.items()},
    }

    # --- real (CPI) context for buy-hold equity ---
    sp_idx = cum_index(tr["us_equity"].loc[EVAL_START:EVAL_END])
    cpi_lvl = d["cpi"].reindex(sp_idx.index)
    real_sp = (sp_idx / cpi_lvl).dropna()
    out["sp500_real_context"] = {
        "real_maxdd_full_pct": round(float((real_sp / real_sp.cummax() - 1).min()) * 100, 2),
        "nominal_buyhold_maxdd_pct": out["full_period"]["buyhold_equity"]["maxdd_pct"],
    }

    # --- WTI-based commodity sensitivity (energy-heavy, GSCI-like) ---
    wti = _load_fred("fred_WTISPLC.csv", "WTISPLC")
    wti_tr = (wti.pct_change().reindex(idxc) + tb_m.reindex(idxc)).dropna()
    out["commodity_proxy_sensitivity"] = {
        "note": "WTI crude spot + T-bill collateral as an energy-heavy (GSCI-like) commodity alternative to PPIACO.",
        "ppiaco_commod_cagr_pct": metrics(tr["commodities"].loc[EVAL_START:EVAL_END], rf).get("cagr_pct"),
        "wti_commod_cagr_pct": metrics(wti_tr.loc[EVAL_START:EVAL_END], rf).get("cagr_pct"),
        "ppiaco_commod_1977_82_total_pct": metrics(
            tr["commodities"].loc[STAG_WINDOWS["stagflation_1977_82"][0]:STAG_WINDOWS["stagflation_1977_82"][1]], rf).get("total_return_pct"),
        "wti_commod_1977_82_total_pct": metrics(
            wti_tr.loc[STAG_WINDOWS["stagflation_1977_82"][0]:STAG_WINDOWS["stagflation_1977_82"][1]], rf).get("total_return_pct"),
    }

    # --- ROBUSTNESS: separate the structural thesis from the PPIACO low-vol
    #     inverse-vol overweight artifact. Re-run the full engine with
    #     (a) WTI commodity sleeve (realistic vol), (b) equal-weight, (c) both.
    out["robustness"] = {
        "why": "Base run uses inverse-vol weighting + PPIACO commodity sleeve. PPIACO is a smoothed producer-price index with artificially LOW measured vol, so inverse-vol assigns it ~85-95% weight, and PPI rises smoothly -> headline Sharpe/MaxDD are inflated. These variants test whether the cross-asset rotation thesis survives without that artifact.",
        "variants": {},
    }
    tr_wti = dict(tr)
    tr_wti["commodities"] = wti_tr
    px_wti = dict(px)
    px_wti["commodities"] = cum_index(wti_tr)
    rets_wti = rets_df.copy()
    rets_wti["commodities"] = wti_tr
    configs = {
        "base_invvol_ppiaco": (tr, px, rets_df, "inv_vol"),
        "equalweight_ppiaco": (tr, px, rets_df, "equal"),
        "invvol_wti": (tr_wti, px_wti, rets_wti, "inv_vol"),
        "equalweight_wti": (tr_wti, px_wti, rets_wti, "equal"),
    }
    for name, (trc, pxc, rdc, wmode) in configs.items():
        s, h = run_engine(trc, pxc, rdc, RISKY, SAFE_POOL, eval_months, weighting=wmode)
        rec = {"full_period": metrics(s, rf), "stagflation_windows": {}}
        for wn, (a, b) in STAG_WINDOWS.items():
            sub = h.loc[a:b].reindex(columns=RISKY + SAFE_POOL, fill_value=0.0)
            rec["stagflation_windows"][wn] = {
                **metrics(s.loc[a:b], rf),
                "avg_infl_winner_wt": round(float((sub["gold"] + sub["commodities"]).mean()), 4),
                "avg_safe_wt": round(float(sub[SAFE_POOL].sum(axis=1).mean()), 4),
            }
        out["robustness"]["variants"][name] = rec

    def _ser(o):
        if isinstance(o, np.bool_):
            return bool(o)
        if isinstance(o, np.integer):
            return int(o)
        if isinstance(o, np.floating):
            return float(o)
        raise TypeError(str(type(o)))

    OUT = HERE / "stagflation_1970s_cpm_crossasset_findings.json"
    OUT.write_text(json.dumps(out, indent=2, default=_ser))
    print(f"Wrote {OUT}")

    # console summary
    print("\n== FULL PERIOD (1969-02..1985-12) ==")
    for k in variants:
        m = out["full_period"][k]
        print(f"  {k:16s} CAGR {m['cagr_pct']:>6}%  MaxDD {m['maxdd_pct']:>7}%  Sharpe {m['sharpe']:>6}  vol {m['vol_pct']}%")
    for wname in STAG_WINDOWS:
        print(f"\n== {wname} ==")
        for k in variants:
            m = out["stagflation_windows"][wname][k]
            print(f"  {k:16s} ret {m['total_return_pct']:>7}%  MaxDD {m['maxdd_pct']:>7}%  Sharpe {m['sharpe']}")
        r = out["stagflation_windows"][wname]
        print(f"  cpm DD avoided vs buyhold={r['cpm_dd_avoided_vs_buyhold_pp']}pp  vs 60/40={r['cpm_dd_avoided_vs_6040_pp']}pp")
        rot = out["rotation"]["windows"][wname]
        print(f"  avg infl-winner wt={rot['inflation_winners_gold_plus_commod']}  safe={rot['safe_total']}  %mo holding infl-winner={rot['pct_months_holding_inflation_winner']}")
    print("\n== ABS-MOM SCREEN CONTRIBUTION (full) ==")
    a = out["abs_mom_contribution"]
    print(f"  with_screen CAGR {a['with_screen']['cagr_pct']}% MaxDD {a['with_screen']['maxdd_pct']}%")
    print(f"  no_screen   CAGR {a['no_screen']['cagr_pct']}% MaxDD {a['no_screen']['maxdd_pct']}%")
    print("\n== COMMODITY/GOLD ROTATION CONTRIBUTION (full) ==")
    c = out["commodity_rotation_contribution"]
    print(f"  full_universe       CAGR {c['full_universe']['cagr_pct']}% MaxDD {c['full_universe']['maxdd_pct']}%")
    print(f"  no_inflation_assets CAGR {c['no_inflation_assets']['cagr_pct']}% MaxDD {c['no_inflation_assets']['maxdd_pct']}%")
    print(f"\n  real SP buyhold MaxDD={out['sp500_real_context']['real_maxdd_full_pct']}%")
    print(f"  commod proxy: PPIACO CAGR={out['commodity_proxy_sensitivity']['ppiaco_commod_cagr_pct']}% vs WTI CAGR={out['commodity_proxy_sensitivity']['wti_commod_cagr_pct']}%")
    print("\n== ROBUSTNESS (full / 1973-74 MaxDD / 1977-82 MaxDD) ==")
    for name, rec in out["robustness"]["variants"].items():
        fp = rec["full_period"]
        d1 = rec["stagflation_windows"]["bear_1973_74"]
        d2 = rec["stagflation_windows"]["stagflation_1977_82"]
        print(f"  {name:22s} CAGR {fp['cagr_pct']:>6}% MaxDD {fp['maxdd_pct']:>7}% Sharpe {fp['sharpe']:>6} | 73-74 ret {d1['total_return_pct']:>7}% DD {d1['maxdd_pct']:>6}% | 77-82 ret {d2['total_return_pct']:>7}% DD {d2['maxdd_pct']:>6}%")
    return out


if __name__ == "__main__":
    main()
