# -*- coding: utf-8 -*-
"""Analyst research (read-only; writes research/ only; NO prod/memo edits, NO commit).

QUESTION: Do RESPECTED published tactical strategies -- canonical AAA and
HAA-Simple -- themselves beat 60/40 at statistical significance? If even they
are within bootstrap noise vs 60/40, then sub-significance is the NORM for this
strategy class, and CPM's not-significant-vs-60/40 result is not a CPM-specific
failing.

This run extends the test toward the Keller paper backtest window using a
RIGOROUS proxy-spliced monthly total-return panel (documented per asset), plus
an 18y ETF-era contrast.

ENGINE: monthly total-return, month-end signal, hold next month, 10 bps/side
turnover cost. (Deep-history proxy series are monthly TR only -> no intraday
opens -> close/monthly execution, NOT the ETF-era mooex T+1 MOO. Stated as a
deviation; it is applied IDENTICALLY to every strategy so the paired
difference-CIs are apples-to-apples.)

STRATEGIES
  60/40        : 0.60 S&P500-TR + 0.40 IEF(7-10y Tsy), monthly rebalance.
  HAA-Simple   : faithful Keller HAA-Simple. Single offensive asset SPY; TIP
                 canary (13612U>0); absolute-momentum filter on SPY (13612U>0);
                 if risk-off hold best-of {cash(T-bill), IEF} by 13612U.
                 (== the all-OFF cell of bull_factorial_faithful_haa.py.)
                 Defensive cash proxy = 3m T-bill (BIL/SHV equivalent).
  AAA-10       : canonical 10-asset AAA [SPY,EZU,EWJ,EEM,IYR,RWX,IEF,TLT,DBC,GLD],
                 top-half (5) by 6m momentum, min-variance weights (36m monthly
                 cov), no canary. RWX (intl REIT) caps history at ~2008.
  AAA-9        : AAA minus RWX (no rigorous intl-REIT proxy exists pre-2006).
                 top-half (5 of 9) by 6m mom, min-var. Power-extension proxy;
                 NON-canonical (flagged). Gold proxy caps history at ~2001.

DIFFERENCE CIs: paired block bootstrap on monthly returns, block=6 months,
B=3000, strategy-minus-60/40, Sharpe and Calmar. Significant <=> 95% CI excludes 0.
"""
import sys, json, math
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.optimize import minimize

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
MACRO = Path(__file__).resolve().parent / "_macro_cache"
from cpm_live import sig_13612U  # canonical 13612U momentum

SEED = 20260531
CLEAN_START = pd.Timestamp("2008-05-31")
END = pd.Timestamp("2026-05-22")
COST_PER_SIDE = 0.0010  # 10 bps/side


# ---------------------------------------------------------------- loaders
def _yf(stem):
    df = pd.read_csv(MACRO / f"{stem}.csv", parse_dates=[0], index_col=0)
    s = df.iloc[:, 0]
    s.index = pd.to_datetime(s.index)
    return s[~s.index.duplicated(keep="last")].sort_index()


def _fred(stem):
    df = pd.read_csv(MACRO / f"{stem}.csv")
    df.columns = ["date", "val"]
    df["date"] = pd.to_datetime(df["date"])
    df["val"] = pd.to_numeric(df["val"], errors="coerce")
    return df.dropna().set_index("date")["val"].sort_index()


def monthly_last(s):
    return s.resample("ME").last()


def to_level_from_returns(monthly_ret):
    """monthly returns (Series) -> level index starting at 1.0 the month before."""
    lvl = (1.0 + monthly_ret.fillna(0.0)).cumprod()
    return lvl


# ---------------------------------------------------------------- proxy builders
def synth_bond_tr(yld_daily, dur):
    """Monthly TR of a constant-maturity par bond from a CMT yield series.
    TR_m ~= carry(y_prev/12) - dur*(y_now - y_prev). yld in percent -> /100."""
    ym = monthly_last(yld_daily) / 100.0
    carry = ym.shift(1) / 12.0
    dprice = -dur * (ym - ym.shift(1))
    return (carry + dprice).dropna()


def splice_levels(segments):
    """segments: list of (priority_label, monthly_level_series) ordered from
    EARLIEST/lowest-priority to LATEST/highest-priority. Build one continuous
    monthly RETURN series, preferring later (higher-quality/real) series where
    they overlap, chaining returns across the splice. Returns (ret, splice_log)."""
    # Convert each level series to monthly returns
    rets = [(lab, lv.pct_change()) for lab, lv in segments]
    # Determine global monthly index
    idx = sorted(set().union(*[set(r.index) for _, r in rets]))
    idx = pd.DatetimeIndex(idx)
    out = pd.Series(index=idx, dtype=float)
    src = pd.Series(index=idx, dtype=object)
    # priority: later in list wins. Apply forward so the real/highest-quality
    # series (last) overwrites earlier proxies in any overlap.
    for lab, r in rets:
        r = r.reindex(idx)
        mask = r.notna()
        out[mask] = r[mask]
        src[mask] = lab
    out = out.dropna()
    src = src.reindex(out.index)
    # splice log: first month of each source block
    log = []
    prev = None
    for d, s in src.items():
        if s != prev:
            log.append((str(d.date()), s))
            prev = s
    return out, log


# ---------------------------------------------------------------- build panel
def shiller_sp500_tr():
    """Monthly S&P 500 TOTAL RETURN level from Shiller data (1871+).
    TR_t = (P_t + D_t/12)/P_{t-1} - 1, P = monthly-avg price, D = annual dividend."""
    df = pd.read_csv(MACRO / "SHILLER_sp500.csv")
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.set_index("Date").sort_index()
    P = pd.to_numeric(df["SP500"], errors="coerce")
    D = pd.to_numeric(df["Dividend"], errors="coerce")
    tr = (P + D / 12.0) / P.shift(1) - 1.0
    tr.index = tr.index.to_period("M").to_timestamp("M")
    return tr.dropna()


def build_panel():
    """Return (monthly_ret DataFrame, levels DataFrame, splice_doc dict)."""
    doc = {}

    # ---- S&P 500 total return: Shiller TR (1871+) / ^SP500TR (1988+) ----
    sp_shiller_lvl = to_level_from_returns(shiller_sp500_tr())
    sp_real = monthly_last(_yf("SP500TR_tr"))
    sp_ret, sp_log = splice_levels([
        ("Shiller S&P500 TR reconstruction", sp_shiller_lvl),
        ("SP500TR (yfinance TR index)", sp_real),
    ])
    doc["SP500"] = sp_log

    # ---- IEF (7-10y Tsy TR): real IEF 2002+ / VFITX 1991+ / DGS10-synth <1991 ----
    ief_real = monthly_last(_yf("IEF_tr"))
    vfitx = monthly_last(_yf("VFITX_tr"))
    ief_synth_ret = synth_bond_tr(_fred("DGS10"), dur=7.5)
    ief_synth_lvl = to_level_from_returns(ief_synth_ret)
    ief_ret, ief_log = splice_levels([
        ("DGS10 synth (7-10y, dur 7.5)", ief_synth_lvl),
        ("VFITX (Vanguard Interm Tsy)", vfitx),
        ("IEF (real ETF)", ief_real),
    ])
    doc["IEF"] = ief_log

    # ---- cash / T-bill (BIL/SHV equiv): FRED DTB3 1954+ ----
    dtb3 = _fred("DTB3") / 100.0
    cash_m = monthly_last(dtb3)
    cash_ret = (cash_m.shift(1) / 12.0).dropna()  # carry only
    doc["CASH"] = [("FRED DTB3 3m T-bill carry", str(cash_ret.index[0].date()))]

    # ---- TIP: real VIPSX 2000-06+ / synth (IEF-track + CPI accrual) before ----
    vipsx = monthly_last(_yf("VIPSX_tr"))
    cpi = _fred("CPIAUCSL")
    cpi_infl = monthly_last(cpi).pct_change()  # realized monthly CPI inflation
    ief_track_ret = ief_ret.copy()             # nominal 7-10y track (spliced above)
    tip_synth_ret = (ief_track_ret + cpi_infl.reindex(ief_track_ret.index)).dropna()
    tip_synth_lvl = to_level_from_returns(tip_synth_ret)
    tip_ret, tip_log = splice_levels([
        ("IEF-track + CPI accrual (synthetic TIPS)", tip_synth_lvl),
        ("VIPSX (Vanguard real TIPS fund)", vipsx),
    ])
    doc["TIP"] = tip_log

    # ---- TLT (20+y Tsy TR): real TLT 2002+ / VUSTX 1986+ ----
    tlt_real = monthly_last(_yf("TLT_tr"))
    vustx = monthly_last(_yf("VUSTX_tr"))
    tlt_ret, tlt_log = splice_levels([
        ("VUSTX (Vanguard Long Tsy)", vustx),
        ("TLT (real ETF)", tlt_real),
    ])
    doc["TLT"] = tlt_log

    # ---- GLD (gold): real GLD 2004+ / GC=F 2000+ (pre-2000 gold not free) ----
    gld_real = monthly_last(_yf("GLD_tr"))
    gcf = monthly_last(_yf("GCF_fut"))
    gld_ret, gld_log = splice_levels([
        ("GC=F (gold front future)", gcf),
        ("GLD (real ETF)", gld_real),
    ])
    doc["GLD"] = gld_log

    # ---- DBC (commodities): real DBC 2006+ / ^SPGSCI 1984+ ----
    dbc_real = monthly_last(_yf("DBC_tr"))
    gsci = monthly_last(_yf("SPGSCI_idx"))
    dbc_ret, dbc_log = splice_levels([
        ("SPGSCI (S&P GSCI index)", gsci),
        ("DBC (real ETF)", dbc_real),
    ])
    doc["DBC"] = dbc_log

    # ---- EEM (EM): real EEM 2003+ / VEIEX 1994+ ----
    eem_real = monthly_last(_yf("EEM_tr"))
    veiex = monthly_last(_yf("VEIEX_tr"))
    eem_ret, eem_log = splice_levels([
        ("VEIEX (Vanguard EM)", veiex),
        ("EEM (real ETF)", eem_real),
    ])
    doc["EEM"] = eem_log

    # ---- EZU (eurozone): real EZU 2000+ / VGTSX total-intl 1996+ (weak proxy) ----
    ezu_real = monthly_last(_yf("EZU_tr"))
    vgtsx = monthly_last(_yf("VGTSX_tr"))
    ezu_ret, ezu_log = splice_levels([
        ("VGTSX (Total Intl, dev-exUS proxy)", vgtsx),
        ("EZU (real ETF)", ezu_real),
    ])
    doc["EZU"] = ezu_log

    # ---- IYR (US REIT): real IYR 2000+ / VGSIX 1996+ ----
    iyr_real = monthly_last(_yf("IYR_tr"))
    vgsix = monthly_last(_yf("VGSIX_tr"))
    iyr_ret, iyr_log = splice_levels([
        ("VGSIX (Vanguard REIT)", vgsix),
        ("IYR (real ETF)", iyr_real),
    ])
    doc["IYR"] = iyr_log

    # ---- EWJ (Japan): real EWJ 1996+ (cap) ----
    ewj = monthly_last(_yf("EWJ_tr"))
    ewj_ret = ewj.pct_change().dropna()
    doc["EWJ"] = [("EWJ (real ETF)", str(ewj.index[1].date()))]

    # ---- RWX (intl REIT): XRFIX mutual fund 1998-11+ / real RWX 2007+ ----
    rwx_real = monthly_last(_yf("RWX_tr"))
    xrfix = monthly_last(_yf("XRFIX_tr"))
    rwx_ret, rwx_log = splice_levels([
        ("XRFIX (intl REIT mutual fund)", xrfix),
        ("RWX (real ETF)", rwx_real),
    ])
    doc["RWX"] = rwx_log

    rets = {
        "SP500": sp_ret, "IEF": ief_ret, "CASH": cash_ret, "TIP": tip_ret,
        "TLT": tlt_ret, "GLD": gld_ret, "DBC": dbc_ret, "EEM": eem_ret,
        "EZU": ezu_ret, "IYR": iyr_ret, "EWJ": ewj_ret, "RWX": rwx_ret,
    }
    # align to month-end grid
    df = pd.DataFrame(rets)
    df.index = df.index.to_period("M").to_timestamp("M")
    df = df[~df.index.duplicated(keep="last")].sort_index()
    levels = (1.0 + df.fillna(0.0)).cumprod()
    return df, levels, doc


# ---------------------------------------------------------------- strategies
def mom_6m_monthly(level):
    lv = level.dropna()
    if len(lv) < 7:
        return np.nan
    return float(lv.iloc[-1] / lv.iloc[-7] - 1.0)


def minvar_monthly(ret_df, picks, lookback=36):
    sub = ret_df[picks].dropna().tail(lookback)
    if len(sub) < 12:
        return {t: 1.0 / len(picks) for t in picks}
    C = (sub.cov() * 12.0).values
    n = len(picks)
    cons = ({"type": "eq", "fun": lambda w: w.sum() - 1.0},)
    bnds = tuple((0.0, 1.0) for _ in range(n))
    r = minimize(lambda w: float(w @ C @ w), np.ones(n) / n,
                 method="SLSQP", bounds=bnds, constraints=cons)
    return {picks[i]: float(r.x[i]) for i in range(n)} if r.success else {t: 1.0 / n for t in picks}


def weights_6040(levels, ret_df, t, uni):
    return {"SP500": 0.60, "IEF": 0.40}


def weights_haa(levels, ret_df, t, uni):
    """Faithful HAA-Simple. uni unused (single offensive SPY)."""
    hist = levels.loc[:t]
    spm = sig_13612U(hist["SP500"])
    tipm = sig_13612U(hist["TIP"])
    risk_on = (pd.notna(tipm) and tipm > 0) and (pd.notna(spm) and spm > 0)
    if risk_on:
        return {"SP500": 1.0}
    # best-of {cash, IEF} by 13612U
    scores = {}
    for s in ("CASH", "IEF"):
        v = sig_13612U(hist[s])
        if pd.notna(v):
            scores[s] = v
    if not scores:
        return {"CASH": 1.0}
    return {max(scores, key=scores.get): 1.0}


# ReSolve Adaptive Asset Allocation (Butler/Philbrick/Gordillo/Varadi,
# SSRN 2328254). 10-asset global universe; DYNAMIC: at each month use only
# assets with >=13 months history, select top-half of AVAILABLE by 6m momentum,
# min-variance weights. Pre-proxy assets (intl-REIT/gold/etc.) simply drop out
# of the available set rather than being fabricated (paper-style stub handling).
AAA_UNIVERSE = ["SP500", "EZU", "EWJ", "EEM", "IYR", "RWX", "IEF", "TLT", "DBC", "GLD"]


def make_weights_aaa(universe):
    def wf(levels, ret_df, t, uni):
        hist = levels.loc[:t]
        avail = [a for a in universe if a in hist.columns and hist[a].dropna().shape[0] >= 13]
        scores = {a: mom_6m_monthly(hist[a]) for a in avail}
        scores = {a: v for a, v in scores.items() if pd.notna(v)}
        if len(scores) < 2:
            return {"IEF": 1.0}
        ranked = sorted(scores, key=lambda a: -scores[a])
        k = max(2, math.ceil(len(scores) / 2))  # top-half of AVAILABLE assets
        top = ranked[:k]
        return minvar_monthly(ret_df.loc[:t], top)
    return wf


def n_available(ret_df, universe, t):
    return sum(1 for a in universe if a in ret_df.columns
              and ret_df.loc[:t, a].dropna().shape[0] >= 13)


# ---------------------------------------------------------------- backtest
def backtest(ret_df, levels, weight_fn, universe, start, end):
    """Monthly: at month-end t pick weights from data<=t, earn return of t+1.
    Apply 10bps/side turnover cost at each rebalance. Returns monthly net series."""
    months = ret_df.index
    months = months[(months >= start) & (months <= end)]
    prev_w = {}
    rec = {}
    for i, t in enumerate(months[:-1]):
        w = weight_fn(levels, ret_df, t, universe)
        w = {k: v for k, v in w.items() if abs(v) > 1e-9}
        nxt = months[i + 1]
        gross = 0.0
        for a, wt in w.items():
            r = ret_df.at[nxt, a] if a in ret_df.columns and nxt in ret_df.index else np.nan
            if pd.isna(r):
                r = 0.0
            gross += wt * r
        # turnover cost
        keys = set(w) | set(prev_w)
        turn = sum(abs(w.get(k, 0.0) - prev_w.get(k, 0.0)) for k in keys)
        cost = turn * COST_PER_SIDE
        rec[nxt] = gross - cost
        prev_w = w
    return pd.Series(rec).sort_index()


# ---------------------------------------------------------------- metrics
def metrics_monthly(r):
    r = r.dropna()
    if len(r) < 6:
        return {"sharpe": np.nan, "cagr": np.nan, "vol": np.nan, "maxdd": np.nan, "calmar": np.nan, "n_months": len(r)}
    mu = r.mean() * 12.0
    vol = r.std(ddof=0) * math.sqrt(12.0)
    sharpe = mu / vol if vol > 0 else np.nan
    eq = (1.0 + r).cumprod()
    cagr = eq.iloc[-1] ** (12.0 / len(r)) - 1.0
    dd = eq / eq.cummax() - 1.0
    maxdd = float(dd.min())
    calmar = cagr / abs(maxdd) if maxdd != 0 else np.nan
    return {"sharpe": float(sharpe), "cagr": float(cagr), "vol": float(vol),
            "maxdd": maxdd, "calmar": float(calmar), "n_months": int(len(r))}


def _sharpe(r):
    v = r.std(ddof=0) * math.sqrt(12.0)
    return (r.mean() * 12.0) / v if v > 0 else np.nan


def _calmar(r):
    eq = np.cumprod(1.0 + r)
    cagr = eq[-1] ** (12.0 / len(r)) - 1.0
    peak = np.maximum.accumulate(eq)
    mdd = (eq / peak - 1.0).min()
    return cagr / abs(mdd) if mdd != 0 else np.nan


def paired_block_bootstrap(a, b, block=6, B=3000, seed=SEED):
    """a, b monthly return Series (strategy, 60/40). diff = a - b on Sharpe & Calmar."""
    common = a.index.intersection(b.index)
    aa = a.reindex(common).fillna(0.0).values
    bb = b.reindex(common).fillna(0.0).values
    n = len(aa)
    res = {"n_months": int(n), "window": [str(common[0].date()), str(common[-1].date())]}
    pt_sh = _sharpe(pd.Series(aa)) - _sharpe(pd.Series(bb))
    pt_ca = _calmar(aa) - _calmar(bb)
    res["sharpe_point"] = float(pt_sh)
    res["calmar_point"] = float(pt_ca)
    if n < block * 4:
        res.update({"insufficient": True})
        return res
    rng = np.random.default_rng(seed)
    nb = math.ceil(n / block)
    pool = np.arange(0, n - block + 1)
    dsh = np.empty(B); dca = np.empty(B)
    for i in range(B):
        st = rng.choice(pool, size=nb, replace=True)
        idx = np.concatenate([np.arange(s, s + block) for s in st])[:n]
        ra, rb = aa[idx], bb[idx]
        dsh[i] = _sharpe(pd.Series(ra)) - _sharpe(pd.Series(rb))
        dca[i] = _calmar(ra) - _calmar(rb)
    for nm, arr, pt in (("sharpe", dsh, pt_sh), ("calmar", dca, pt_ca)):
        lo, hi = np.nanpercentile(arr, [2.5, 97.5])
        res[f"{nm}_ci"] = [float(lo), float(hi)]
        res[f"{nm}_sig"] = bool(not (lo <= 0.0 <= hi))
    return res


# ---------------------------------------------------------------- main
def main():
    ret_df, levels, doc = build_panel()
    print("Panel monthly range:", ret_df.index[0].date(), "->", ret_df.index[-1].date())
    fv = {c: ret_df[c].first_valid_index() for c in ret_df.columns}
    for c in ret_df.columns:
        print(f"  {c:6} first ret month {fv[c].date()}")

    # per-strategy max start = first month all required assets have >=13 months history
    def first_start(assets):
        fvs = [ret_df[a].first_valid_index() for a in assets]
        base = max(fvs)
        # need 13 months of level history for momentum -> add 13 months
        return (base + pd.DateOffset(months=13)).to_period("M").to_timestamp("M")

    haa_assets = ["SP500", "TIP", "IEF", "CASH"]
    s6040_assets = ["SP500", "IEF"]
    haa_start = first_start(haa_assets)
    s6040_start = first_start(s6040_assets)
    # ReSolve AAA paper window starts ~1995; use first month with >=4 assets
    # available, but not before the paper's 1995 start.
    aaa_paper_floor = pd.Timestamp("1995-01-31")
    cand = [t for t in ret_df.index if t >= aaa_paper_floor and n_available(ret_df, AAA_UNIVERSE, t) >= 4]
    aaa_start = cand[0] if cand else aaa_paper_floor

    # DEFINITIVE paper windows (sourced):
    #  AAA (SSRN 2328254): in-sample 1995-2015 ; OOS 2015 -> present
    #  HAA (SSRN 4346906): in-sample Dec1970-Dec2022 ; OOS 2023 -> present
    HAA_IS = (pd.Timestamp("1970-12-31"), pd.Timestamp("2022-12-31"))
    HAA_OOS = (pd.Timestamp("2023-01-31"), END)
    AAA_IS = (aaa_start, pd.Timestamp("2015-12-31"))
    AAA_OOS = (pd.Timestamp("2016-01-31"), END)
    COMMON18 = (CLEAN_START, END)
    swins = {
        "HAA_Simple": {"in_sample": HAA_IS, "paper_oos": HAA_OOS, "common18y": COMMON18},
        "AAA": {"in_sample": AAA_IS, "paper_oos": AAA_OOS, "common18y": COMMON18},
    }

    print(f"\nstarts: 60/40={s6040_start.date()} HAA={haa_start.date()} AAA={aaa_start.date()}")
    for yr in ("1995-06-30", "1997-12-31", "2000-12-31", "2002-12-31"):
        ts = pd.Timestamp(yr)
        print(f"   AAA assets available @ {yr}: {n_available(ret_df, AAA_UNIVERSE, ts)}")

    # series over full panel (then slice per window)
    full_start = ret_df.index[0]
    s6040 = backtest(ret_df, levels, weights_6040, None, full_start, END)
    haa = backtest(ret_df, levels, weights_haa, None, max(haa_start, full_start), END)
    aaa = backtest(ret_df, levels, make_weights_aaa(AAA_UNIVERSE), AAA_UNIVERSE, aaa_start, END)

    series = {"60/40": s6040, "HAA_Simple": haa, "AAA": aaa}

    out = {"meta": {
        "engine": "monthly TR, month-end signal, hold next month, 10bps/side",
        "execution_note": "monthly close (NOT mooex T+1 MOO); applied identically to all strategies",
        "cost_per_side": COST_PER_SIDE, "block_months": 6, "B": 3000,
        "panel_start": str(ret_df.index[0].date()), "panel_end": str(ret_df.index[-1].date()),
        "AAA_definition": "ReSolve Adaptive Asset Allocation (SSRN 2328254); in-sample 1995-2015, OOS 2015->present",
        "HAA_definition": "Keller/Keuning HAA-Simple (SSRN 4346906); in-sample Dec1970-Dec2022, OOS 2023->present",
        "windows": {
            "HAA_in_sample": [str(HAA_IS[0].date()), str(HAA_IS[1].date())],
            "HAA_paper_oos": [str(HAA_OOS[0].date()), str(HAA_OOS[1].date())],
            "AAA_in_sample": [str(AAA_IS[0].date()), str(AAA_IS[1].date())],
            "AAA_paper_oos": [str(AAA_OOS[0].date()), str(AAA_OOS[1].date())],
            "common18y": [str(COMMON18[0].date()), str(COMMON18[1].date())],
        },
        "shortfall": ("AAA: intl-REIT only from XRFIX 1998-11 (paper cites 1997-09) / "
                      "gold from GC=F 2000 -> pre-proxy assets dropped from the available "
                      "set (paper-style 5->4 stub), so early-window AAA uses <10 assets; "
                      "AAA cannot precede ~1995 and intl-REIT not reliable before ~1999. "
                      "HAA: reaches Dec1970 paper start via Shiller S&P TR + DGS10 "
                      "synthetic bond and IEF+CPI synthetic TIP."),
    }, "splice_doc": doc, "starts": {
        "60/40": str(s6040_start.date()), "HAA_Simple": str(haa_start.date()),
        "AAA": str(aaa_start.date()),
    }, "standalone": {}, "diff_ci": {}}

    # per-strategy, per-window standalone metrics (strategy + 60/40) and diff CI
    for nm in ("HAA_Simple", "AAA"):
        s = series[nm]
        out["standalone"][nm] = {}
        out["diff_ci"][nm] = {}
        for wn, (ws, we) in swins[nm].items():
            a = s.loc[(s.index >= ws) & (s.index <= we)]
            b = s6040.loc[(s6040.index >= ws) & (s6040.index <= we)]
            out["standalone"][nm][wn] = {
                "strategy": {**metrics_monthly(a)},
                "60/40": {**metrics_monthly(b)},
                "window": [str(ws.date()), str(we.date())],
            }
            out["diff_ci"][nm][wn] = paired_block_bootstrap(a, b)

    Path(__file__).with_name("cpm_class_significance_sanity.json").write_text(
        json.dumps(out, indent=2, default=float))

    # ---------- console ----------
    WLAB = {"in_sample": "IN-SAMPLE", "paper_oos": "PAPER-OOS", "common18y": "COMMON-18y"}
    for nm in ("HAA_Simple", "AAA"):
        print("\n" + "=" * 86)
        print(f"{nm}  vs 60/40")
        print("=" * 86)
        print(f"{'window':<12}{'range':>24}{'mo':>5}{'Shp(str/6040)':>16}"
              f"{'Cal(str/6040)':>16}{'MDD(str/6040)':>18}")
        for wn in ("in_sample", "paper_oos", "common18y"):
            d = out["standalone"][nm][wn]; st = d["strategy"]; sx = d["60/40"]
            rng = f"{d['window'][0]}..{d['window'][1]}"
            print(f"{WLAB[wn]:<12}{rng:>24}{st['n_months']:>5}"
                  f"{st['sharpe']:>8.3f}/{sx['sharpe']:<7.3f}"
                  f"{st['calmar']:>8.3f}/{sx['calmar']:<7.3f}"
                  f"{st['maxdd']*100:>8.1f}%/{sx['maxdd']*100:<7.1f}%")
        print(f"\n  {'DIFF vs 60/40':<12}{'dSharpe':>9}{'Sharpe 95% CI':>20}{'sig?':>6} | "
              f"{'dCalmar':>9}{'Calmar 95% CI':>20}{'sig?':>6}")
        for wn in ("in_sample", "paper_oos", "common18y"):
            r = out["diff_ci"][nm][wn]
            sh = r.get("sharpe_ci", [float('nan')]*2); ca = r.get("calmar_ci", [float('nan')]*2)
            ins = " INSUF" if r.get("insufficient") else ""
            print(f"  {WLAB[wn]:<12}{r['sharpe_point']:>9.3f}"
                  f"  [{sh[0]:>6.3f},{sh[1]:>6.3f}]{str(r.get('sharpe_sig')):>6} | "
                  f"{r['calmar_point']:>9.3f}  [{ca[0]:>6.3f},{ca[1]:>6.3f}]{str(r.get('calmar_sig')):>6}{ins}")
    print("\nDONE -> json written")


if __name__ == "__main__":
    main()
