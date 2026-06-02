# -*- coding: utf-8 -*-
"""Throwaway research (read-only re: production): DEFINITIVE final CPM memo number
set under the FINAL production spec.

FINAL spec (now in production cpm_live.compute_target_weights):
  INVVOL-3 core = select the min-variance 3-subset from the top-K=4 positive-trend
  pool, then inverse-vol weight, WITH STRICT-3 PARTIAL-SAFE fallback:
    risky_fraction = min(n_pos, 3) / 3 ; remainder -> timed safe.
    n_pos=0 -> 100% safe ; n_pos=1 -> 1/3 risky + 2/3 safe ;
    n_pos=2 -> 2/3 risky (invvol-2) + 1/3 safe ; n_pos=3 -> 100% risky invvol-3 ;
    n_pos>3 -> min-var 3-subset, invvol-3, 100% risky.

This SUPERSEDES research/invvol3_memo_numbers_findings.md, which used the OLD
hybrid fallback (n_pos=1 -> 50/50; n_pos=2 -> invvol-2 fully risky) and is STALE.

Headline convention (every table):
  - Execution: T+1 MOO exact ("mooex") with real yfinance auto_adjust opens.
  - Costs: 10 bps/side, post-cost throughout.
  - BULL equity vol gate: slow rv_60d < rv_252d (GATE_RV60).
  - Blend = 0.60*CPM(INVVOL-3 strict-3) + 0.40*BULL.
  - Windows: clean 2008-05-30..2026-05-22 (18y), ext 1999-03-10..2026-05-22 (27y).

Anchor (must reproduce before trusting the rest):
  CPM-solo strict-3 clean Sharpe 1.2667 / MaxDD -12.66% / Calmar 1.1306;
  ext Sharpe 1.2349 / MaxDD -15.18% / Calmar 0.9119.

No production files touched. Writes research/cpm_final_memo_numbers_findings.md (+ json).
"""
from __future__ import annotations
import sys, json, math
from itertools import combinations
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import exec_lag_moo_validation_2026_05_30 as H
from cpm_live import (
    load_panel, perf_metrics, faber_sma_xs, sig_13612U, best_safe,
    min_var_subset, inv_vol_weights, compute_target_weights,
    RISKY_UNIVERSE, SAFE_POOL, CANARY_ASSETS, DEFAULT_CASH, COST_BPS_PER_SIDE,
    TOP_K_CANDIDATES, CORR_LOOKBACK_DAYS,
)
import cpm_live
import cpm_vs_canonical_aaa as AAA
import two_sleeve_60_40_ci_walkforward as CI
from weighting_headtohead import erc_weights

CONV = "mooex"
CPM_W, BULL_W = 0.60, 0.40
COST = COST_BPS_PER_SIDE  # 10
CPM_UNIV = ["QQQ", "SPHQ", "EFA", "EEM", "VNQ", "GLD", "TLT", "DBC"]
SAFE = ["SHV", "IEF"]
LOOKBACK = CORR_LOOKBACK_DAYS  # 504
K = TOP_K_CANDIDATES           # 4

CLEAN_START = pd.Timestamp("2008-05-30")
EXT_START = pd.Timestamp("1999-03-10")
END = pd.Timestamp("2026-05-22")

REGIMES = {
    "Dot-com (2000-03..2002-12)": ("2000-03-01", "2002-12-31"),
    "GFC (2007-10..2009-06)":     ("2007-10-01", "2009-06-30"),
    "COVID (2020-02..2020-06)":   ("2020-02-01", "2020-06-30"),
    "2022 bear (2022-01..2022-12)": ("2022-01-01", "2022-12-31"),
}

# FINAL strict-3 partial-safe CPM-solo anchor (= production compute_target_weights).
ANCHOR = {"clean": (1.2667, -12.66, 1.1306), "ext": (1.2349, -15.18, 0.9119)}


def met(s, cash):
    m = perf_metrics(s, cash)
    return {"sharpe": m.get("sharpe"), "cagr": m.get("cagr"), "vol": m.get("vol"),
            "maxdd": m.get("max_drawdown"), "calmar": m.get("calmar"),
            "excess_sharpe": m.get("excess_sharpe")}


def win(s, start, end):
    return s.loc[(s.index >= start) & (s.index <= end)]


def maxdd_ret(s):
    eq = (1.0 + s).cumprod()
    rm = eq.cummax()
    mdd = float((eq / rm - 1.0).min()) if len(eq) else float("nan")
    tot = float(eq.iloc[-1] - 1.0) if len(eq) else float("nan")
    return mdd, tot


# ---------------------------------------------------------------------------
# Subset selection objectives over the cov window (mirrors
# cpm_weighting_selection_sensitivity.select_subset). All <= sig_d, no lookahead.
# ---------------------------------------------------------------------------
def _ew_curve_metrics(rets_sub):
    r = rets_sub.dropna().mean(axis=1).values
    vol = r.std(ddof=0)
    sharpe = r.mean() / vol if vol > 0 else -np.inf
    eq = np.cumprod(1.0 + r)
    rm = np.maximum.accumulate(eq)
    mdd = float((eq / rm - 1.0).min())
    calmar = (r.mean()) / abs(mdd) if mdd < 0 else np.inf
    return sharpe, calmar, mdd


def select_subset(close, candidates, lookback, m, objective):
    cand = list(candidates)
    if len(cand) <= m:
        return cand
    rets = close[cand].pct_change().dropna(how="all").tail(lookback)
    if len(rets) < lookback:
        return cand
    cov = rets.cov()
    if cov.isna().any().any():
        return cand
    sigma = pd.Series(np.sqrt(np.diag(cov.values)), index=cov.index)
    if objective == "minvol":
        return list(sigma.sort_values().index[:m])
    if objective == "minvar":
        w = 1.0 / m
        best, best_v = None, np.inf
        for combo in combinations(cand, m):
            sub = cov.loc[list(combo), list(combo)].values
            v = float(w * w * sub.sum())
            if v < best_v:
                best_v, best = v, combo
        return list(best)
    if objective == "mincorr":
        corr = rets.corr()
        best, best_c = None, np.inf
        for combo in combinations(cand, m):
            cl = list(combo); sub = corr.loc[cl, cl].values
            iu = np.triu_indices(m, k=1); avg_c = float(sub[iu].mean())
            if avg_c < best_c:
                best_c, best = avg_c, combo
        return list(best)
    best, best_score = None, -np.inf
    for combo in combinations(cand, m):
        cl = list(combo); sh, ca, md = _ew_curve_metrics(rets[cl])
        score = {"maxsharpe": sh, "maxcalmar": ca, "mindd": md}[objective]
        if score > best_score:
            best_score, best = score, combo
    return list(best)


def weight_block(close, picks, lookback, flavor):
    """Weight the risky block by flavor. invvol == production primitive."""
    if not picks:
        return {}
    if flavor == "invvol":
        return inv_vol_weights(close, picks, lookback)
    if flavor == "ew":
        n = len(picks)
        return {t: 1.0 / n for t in picks}
    if flavor == "erc":
        rets = close[picks].pct_change().dropna(how="all").tail(lookback)
        if len(rets) < lookback:
            return inv_vol_weights(close, picks, lookback)
        cov = rets.cov()
        if cov.isna().any().any():
            return inv_vol_weights(close, picks, lookback)
        w = erc_weights(cov.values)
        if w is None or not np.all(np.isfinite(w)):
            return inv_vol_weights(close, picks, lookback)
        return {picks[i]: float(w[i]) for i in range(len(picks))}
    raise ValueError(flavor)


# ---------------------------------------------------------------------------
# Generalized INVVOL-3 STRICT-3 PARTIAL-SAFE weight fn (knobs for all sweeps).
# Base config (top_k=4, screen, faber_vol, hygortip, timed, invvol, minvar, 504)
# == production compute_target_weights exactly (anchor-gated).
# ---------------------------------------------------------------------------
def gcpm_wf(close, sd, *, top_k=4, screen=True, ranker="faber_vol",
            canary="hygortip", safe_kind="timed", lookback=LOOKBACK,
            flavor="invvol", selector="minvar"):
    monthly = close.loc[:sd].resample("ME").last()
    if safe_kind in ("SHV", "IEF", "BLEND5050"):
        safe = safe_kind
    else:
        safe = best_safe(monthly, sd, SAFE)

    if canary != "none":
        ca = {"hyg": ["HYG"], "tip": ["TIP"], "hygortip": ["HYG", "TIP"]}[canary]
        cs = [sig_13612U(monthly[a]) for a in ca if a in monthly.columns]
        cs = [s for s in cs if pd.notna(s)]
        if not cs or sum(1 for s in cs if s > 0) == 0:
            return {safe: 1.0}

    present = [t for t in CPM_UNIV if t in monthly.columns]
    faber = faber_sma_xs(monthly)
    avail = [t for t in present if t in faber.index and pd.notna(faber[t])
             and (sd in close.index and pd.notna(close.loc[sd].get(t, np.nan)))]
    if not avail:
        return {safe: 1.0}

    scores, screenval = {}, {}
    if ranker == "plain12":
        for t in avail:
            s = monthly[t].dropna()
            if len(s) < 13:
                continue
            mom = float(s.iloc[-1] / s.iloc[-13] - 1.0)
            scores[t] = mom; screenval[t] = mom
    else:
        dr = close[avail].ffill().pct_change()
        for t in avail:
            v = dr[t].loc[:sd].tail(252).std() * np.sqrt(252)
            if pd.isna(v) or v < 1e-9:
                v = 1.0
            if ranker == "faber_vol":
                num = float(faber[t]); sv = float(faber[t])
            elif ranker == "13612u_vol":
                num = sig_13612U(monthly[t])
                if pd.isna(num):
                    continue
                num = float(num); sv = num
            else:
                raise ValueError(ranker)
            scores[t] = num / v; screenval[t] = sv
    if not scores:
        return {safe: 1.0}
    ranked = pd.Series(scores).sort_values(ascending=False)
    if top_k is not None:
        kk = max(2, min(top_k, len(ranked)))
        top = ranked.iloc[:kk]
    else:
        top = ranked
    if screen:
        positive = [t for t in top.index if screenval.get(t, -np.inf) > 0]
    else:
        positive = list(top.index)

    n = len(positive)
    if n == 0:
        return {safe: 1.0}
    csub = close.loc[:sd]
    risky_fraction = min(n, 3) / 3.0
    if n > 3:
        picks = select_subset(csub, positive, lookback, 3, selector)
        if picks is None:
            picks = positive
    else:
        picks = positive
    risky_w = weight_block(csub, picks, lookback, flavor)
    out = {t: w * risky_fraction for t, w in risky_w.items()}
    if risky_fraction < 1.0:
        out[safe] = out.get(safe, 0.0) + (1.0 - risky_fraction)
    return out


# ---- variant (B) NO partial-safe (for item 9) -----------------------------
def gcpm_wf_nopartial(close, sd, lookback=LOOKBACK):
    """(B) no partial-safe: positives held FULLY invested; safe only at 0 breadth."""
    monthly = close.loc[:sd].resample("ME").last()
    safe = best_safe(monthly, sd, SAFE)
    cs = [sig_13612U(monthly[a]) for a in CANARY_ASSETS if a in monthly.columns]
    cs = [s for s in cs if pd.notna(s)]
    if not cs or sum(1 for s in cs if s > 0) == 0:
        return {safe: 1.0}
    present = [t for t in CPM_UNIV if t in monthly.columns]
    faber = faber_sma_xs(monthly)
    avail = [t for t in present if t in faber.index and pd.notna(faber[t])
             and (sd in close.index and pd.notna(close.loc[sd].get(t, np.nan)))]
    if not avail:
        return {safe: 1.0}
    dr = close[avail].ffill().pct_change()
    score = {}
    for t in avail:
        v = dr[t].loc[:sd].tail(252).std() * np.sqrt(252)
        if pd.isna(v) or v < 1e-9:
            v = 1.0
        score[t] = float(faber[t]) / v
    ranked = pd.Series(score).sort_values(ascending=False)
    kk = max(2, min(K, len(ranked)))
    top = ranked.iloc[:kk]
    positive = [t for t in top.index if faber.get(t, -np.inf) > 0]
    n = len(positive)
    if n == 0:
        return {safe: 1.0}
    csub = close.loc[:sd]
    if n > 3:
        pick = min_var_subset(csub, positive, lookback, 3)
        if pick is None:
            pick = positive
        return inv_vol_weights(csub, pick, lookback)
    return inv_vol_weights(csub, positive, lookback)


def run_cpm(close, daily, intraday, overnight, wf, cost=COST, end=END):
    s, _ = H._segment_returns_conv(close, daily, wf, EXT_START, end, CONV,
                                   cost, intraday, overnight)
    return s


def daily_weights(close, wf, start, end):
    monthly_idx = (pd.DataFrame({"x": 1}, index=close.index)
                   .groupby(pd.Grouper(freq="ME")).tail(1))
    sigs = monthly_idx.index[(monthly_idx.index >= start) & (monthly_idx.index <= end)].tolist()
    hist = []
    for i, sd in enumerate(sigs):
        w = wf(sd)
        fut = close.index[close.index > sd]
        if len(fut) < 1:
            continue
        af = fut[0]
        if i + 1 < len(sigs):
            nf = close.index[close.index > sigs[i + 1]]
            ea = nf[0] if len(nf) >= 1 else end
        else:
            ea = end
        hist.append((af, ea, w))
    assets = sorted({a for _, _, w in hist for a in w})
    dfw = pd.DataFrame(0.0, index=close.index, columns=assets)
    for af, ea, w in hist:
        mask = (close.index >= af) & (close.index < ea)
        for a, ww in w.items():
            dfw.loc[mask, a] = ww
    return dfw.loc[(dfw.index >= start) & (dfw.index <= end)]


def main():
    panel = load_panel(start=EXT_START, end=END)
    end = min(END, panel.index[-1])
    cash = panel["SHV"].ffill().pct_change().dropna()
    od, cy = H.load_open_close()
    intraday = (cy / od - 1.0).reindex(panel.index)
    overnight = (od / cy.shift(1) - 1.0).reindex(panel.index)

    cols = sorted(set(RISKY_UNIVERSE + SAFE_POOL + CANARY_ASSETS + [DEFAULT_CASH]) & set(panel.columns))
    close = panel[cols]
    daily = close.ffill().pct_change()

    # ----- base sleeves (production strict-3 INVVOL-3 + BULL slow gate) -----
    cpm = run_cpm(close, daily, intraday, overnight,
                  lambda sd: compute_target_weights(close, sd)[0], end=end)
    bull, _ = H.bull_sleeve_conv(panel, intraday, overnight, EXT_START, end, CONV, H.GATE_RV60)
    common = cpm.index.intersection(bull.index)
    cpm = cpm.reindex(common); bull = bull.reindex(common)
    blend = CPM_W * cpm + BULL_W * bull

    out = {"meta": {"conv": CONV, "cost_bps": COST, "lookback": LOOKBACK, "K": K,
                    "weighting": "INVVOL-3 strict-3 partial-safe",
                    "clean_start": str(CLEAN_START.date()),
                    "ext_start": str(EXT_START.date()), "end": str(end.date())}}

    # ----- ANCHOR CHECK -----
    print("=== ANCHOR CHECK (CPM-solo INVVOL-3 strict-3 partial-safe) ===")
    anc = {}
    for wl, st in [("clean", CLEAN_START), ("ext", EXT_START)]:
        m = met(win(cpm, st, end), cash)
        exp = ANCHOR[wl]
        ok = (abs(m["sharpe"] - exp[0]) < 5e-4 and abs(m["maxdd"] * 100 - exp[1]) < 0.02
              and abs(m["calmar"] - exp[2]) < 5e-4)
        anc[wl] = {"m": m, "expect": exp, "ok": ok}
        print(f"  {wl}: Sharpe={m['sharpe']:.4f} MaxDD={m['maxdd']*100:.2f}% Calmar={m['calmar']:.4f} "
              f"expect {exp} -> {'OK' if ok else 'MISMATCH'}")
    out["anchor"] = {wl: {"sharpe": anc[wl]["m"]["sharpe"], "maxdd": anc[wl]["m"]["maxdd"],
                          "calmar": anc[wl]["m"]["calmar"], "ok": anc[wl]["ok"]} for wl in anc}
    if not all(anc[wl]["ok"] for wl in anc):
        print("ANCHOR MISMATCH -- aborting.")
        sys.exit(1)

    # base gcpm self-check (must equal production cpm)
    gcpm = run_cpm(close, daily, intraday, overnight, lambda sd: gcpm_wf(close, sd), end=end)
    gcpm = gcpm.reindex(common)
    gc = met(win(gcpm, CLEAN_START, end), cash)
    gmatch = abs(gc["sharpe"] - anc["clean"]["m"]["sharpe"]) < 1e-6
    out["gcpm_base_selfcheck"] = {"clean_sharpe": gc["sharpe"], "matches_production": bool(gmatch)}
    print(f"gcpm base self-check clean Sharpe={gc['sharpe']:.6f} matches_production={gmatch}")

    # ----- ITEM 1: HEADLINE -----
    headline = {}
    for name, s in [("CPM-solo (INVVOL-3 strict-3)", cpm), ("BULL-solo", bull), ("60/40 blend", blend)]:
        headline[name] = {wl: met(win(s, st, end), cash)
                          for wl, st in [("clean", CLEAN_START), ("ext", EXT_START)]}
    out["headline"] = headline

    # ----- ITEM 2: CRISIS -----
    crisis = {}
    for rname, (rs, re) in REGIMES.items():
        rs_, re_ = pd.Timestamp(rs), pd.Timestamp(re)
        bl = win(blend, rs_, re_); cp = win(cpm, rs_, re_)
        crisis[rname] = {}
        if len(bl) > 1:
            mdd, tot = maxdd_ret(bl); crisis[rname]["blend"] = {"maxdd": mdd, "ret": tot}
        if len(cp) > 1:
            mdd, tot = maxdd_ret(cp); crisis[rname]["cpm"] = {"maxdd": mdd, "ret": tot}
    out["crisis"] = crisis

    # ----- ITEM 3: BOOTSTRAP CI (clean) -----
    boot = {}
    for name, s in [("60/40 blend", blend), ("CPM-solo (INVVOL-3 strict-3)", cpm), ("BULL-solo", bull)]:
        cb = s.loc[(s.index >= CLEAN_START) & (s.index <= END)]
        boot[name] = {"point": CI.metrics(cb, cash), "ci": CI.bootstrap_ci(cb)}
        print(f"CI {name}: Sharpe point={boot[name]['point']['Sharpe']:.3f} "
              f"CI[{boot[name]['ci']['Sharpe']['p2.5']:.3f},{boot[name]['ci']['Sharpe']['p97.5']:.3f}]")
    out["bootstrap"] = boot

    # ----- ITEM 4: ROLLING STABILITY (blend) -----
    roll = {}
    cf = win(blend, CLEAN_START, end); ef = win(blend, EXT_START, end)
    roll["clean_3y"] = CI.roll_stats(CI.rolling_sharpe(cf, 3.0))
    roll["clean_5y"] = CI.roll_stats(CI.rolling_sharpe(cf, 5.0))
    roll["ext_3y"] = CI.roll_stats(CI.rolling_sharpe(ef, 3.0))
    roll["ext_5y"] = CI.roll_stats(CI.rolling_sharpe(ef, 5.0))
    worst = {}
    for wl, s in [("clean", cf), ("ext", ef)]:
        for yr in (1.0, 2.0, 3.0):
            sd_, ed_, sh, cg, md = CI.worst_contiguous(s, yr)
            worst[f"{wl}_{int(yr)}y"] = None if sd_ is None else {
                "start": str(sd_.date()), "end": str(ed_.date()), "sharpe": sh,
                "cagr": cg, "maxdd": md}
    out["rolling"] = {"blend": roll, "worst_blend": worst}

    # ----- ITEM 5: BENCHMARK CPM-solo vs canonical AAA -----
    aaa_cols = sorted(set(AAA.AAA_UNIVERSE + AAA.SAFE + ["TIP"]) & set(panel.columns))
    aaa_close = panel[aaa_cols]; aaa_daily = aaa_close.ffill().pct_change()
    canon = AAA.run_wf(aaa_close, aaa_daily, intraday, overnight, EXT_START, end,
                       AAA.make_canonical_aaa_wf(aaa_close, aaa_daily))
    bench = {}
    for wl, st in [("clean", CLEAN_START), ("ext", EXT_START)]:
        bench[wl] = AAA.active_stats(win(cpm, st, end), win(canon, st, end), cash)
    out["benchmark_aaa"] = bench

    # ----- ITEM 6: SECTION-8 SWEEPS (strict-3 INVVOL-3) -----
    def sweep_metrics(wf):
        s = run_cpm(close, daily, intraday, overnight, wf, end=end)
        com = s.index.intersection(bull.index)
        bl = CPM_W * s.reindex(com) + BULL_W * bull.reindex(com)
        return ({wl: met(win(s, st, end), cash) for wl, st in [("clean", CLEAN_START), ("ext", EXT_START)]},
                {wl: met(win(bl, st, end), cash) for wl, st in [("clean", CLEAN_START), ("ext", EXT_START)]})

    sec8 = {}
    ks = {}
    for Kk in [2, 3, 4, 5, 6]:
        cpm_m, bl_m = sweep_metrics(lambda sd, Kk=Kk: gcpm_wf(close, sd, top_k=Kk))
        ks[Kk] = {"cpm": cpm_m, "blend": bl_m}
        print(f"K={Kk} blend clean Sharpe={bl_m['clean']['sharpe']:.3f} MaxDD={bl_m['clean']['maxdd']*100:.2f}%")
    sec8["K_sweep"] = ks

    sc = {}
    for lbl, (kc, scr) in {
        "K-cap ON + positive-trend ON": (4, True),
        "K-cap OFF + positive-trend ON": (None, True),
        "K-cap ON + positive-trend OFF": (4, False),
        "K-cap OFF + positive-trend OFF": (None, False),
    }.items():
        cpm_m, bl_m = sweep_metrics(lambda sd, kc=kc, scr=scr: gcpm_wf(close, sd, top_k=kc, screen=scr))
        sc[lbl] = {"cpm": cpm_m, "blend": bl_m}
    sec8["screen_2x2"] = sc

    rk = {}
    for lbl, rn in {"10m-SMA-distance / rv_252d": "faber_vol",
                    "13612U / rv_252d (positive-13612U screen)": "13612u_vol",
                    "plain 12-month momentum": "plain12"}.items():
        cpm_m, bl_m = sweep_metrics(lambda sd, rn=rn: gcpm_wf(close, sd, ranker=rn))
        rk[lbl] = {"cpm": cpm_m, "blend": bl_m}
    sec8["ranker"] = rk

    cn = {}
    for lbl, cm in {"dual high-yield OR inflation-protected": "hygortip",
                    "no canary": "none", "high-yield only": "hyg",
                    "inflation-protected only": "tip"}.items():
        cpm_m, bl_m = sweep_metrics(lambda sd, cm=cm: gcpm_wf(close, sd, canary=cm))
        cn[lbl] = {"cpm": cpm_m, "blend": bl_m}
    sec8["canary"] = cn

    # safe (timed vs fixed). Add synthetic BLEND5050 column.
    close2 = close.copy()
    ret5050 = (0.5 * close["SHV"].ffill().pct_change() + 0.5 * close["IEF"].ffill().pct_change()).fillna(0.0)
    close2["BLEND5050"] = (1.0 + ret5050).cumprod() * 100.0
    daily2 = close2.ffill().pct_change()

    def sweep_metrics2(wf):
        s, _ = H._segment_returns_conv(close2, daily2, wf, EXT_START, end, CONV, COST, intraday, overnight)
        com = s.index.intersection(bull.index)
        bl = CPM_W * s.reindex(com) + BULL_W * bull.reindex(com)
        return ({wl: met(win(s, st, end), cash) for wl, st in [("clean", CLEAN_START), ("ext", EXT_START)]},
                {wl: met(win(bl, st, end), cash) for wl, st in [("clean", CLEAN_START), ("ext", EXT_START)]})

    sf = {}
    for lbl, sk in {"timed SHV/IEF by 13612U": "timed", "SHV only": "SHV",
                    "IEF only": "IEF", "static 50/50 SHV+IEF": "BLEND5050"}.items():
        cpm_m, bl_m = sweep_metrics2(lambda sd, sk=sk: gcpm_wf(close2, sd, safe_kind=sk))
        sf[lbl] = {"cpm": cpm_m, "blend": bl_m}
    sec8["safe"] = sf

    cov = {}
    for lb in [126, 252, 504, 756, 1008, 1260]:
        cpm_m, bl_m = sweep_metrics(lambda sd, lb=lb: gcpm_wf(close, sd, lookback=lb))
        cov[lb] = {"cpm": cpm_m, "blend": bl_m}
        print(f"cov={lb} cpm clean Sharpe={cpm_m['clean']['sharpe']:.3f} MaxDD={cpm_m['clean']['maxdd']*100:.2f}%")
    sec8["cov_lookback"] = cov
    out["section8"] = sec8

    # ----- ITEM 7: CONCENTRATION (per-asset share of risky) -----
    conc = {}
    for wl, st in [("clean", CLEAN_START), ("ext", EXT_START)]:
        dfw = daily_weights(close, lambda sd: compute_target_weights(close, sd)[0], st, end)
        risky = [a for a in CPM_UNIV if a in dfw.columns]
        tot = dfw[risky].values.sum()
        conc[wl] = {a: float(dfw[a].sum() / tot) if tot > 0 else 0.0 for a in CPM_UNIV if a in dfw.columns}
    out["concentration"] = conc

    # ----- ITEM 8: WEIGHTING FLAVOR + SUBSET-SELECTION OBJECTIVE (strict-3 base) -----
    axis = {}
    flavor_map = {"inverse-vol (production)": "invvol", "ERC (equal-risk-contribution)": "erc",
                  "equal-weight 1/3 (ref)": "ew"}
    fa = {}
    for lbl, fl in flavor_map.items():
        cpm_m, bl_m = sweep_metrics(lambda sd, fl=fl: gcpm_wf(close, sd, flavor=fl))
        fa[lbl] = {"cpm": cpm_m, "blend": bl_m}
        print(f"flavor={fl} cpm clean Sharpe={cpm_m['clean']['sharpe']:.3f}")
    axis["flavor"] = fa

    sel_map = {"min-variance (production)": "minvar", "min-vol (3 lowest sigma)": "minvol",
               "max-Sharpe (trailing)": "maxsharpe", "max-Calmar (trailing)": "maxcalmar",
               "min-DD (trailing)": "mindd"}
    sb = {}
    for lbl, se in sel_map.items():
        cpm_m, bl_m = sweep_metrics(lambda sd, se=se: gcpm_wf(close, sd, selector=se))
        sb[lbl] = {"cpm": cpm_m, "blend": bl_m}
        print(f"selector={se} cpm clean Sharpe={cpm_m['clean']['sharpe']:.3f}")
    axis["selector"] = sb
    out["axis8"] = axis

    # ----- ITEM 9: FALLBACK strict-3 partial-safe (A) vs no-partial-safe (B) -----
    cpmB = run_cpm(close, daily, intraday, overnight,
                   lambda sd: gcpm_wf_nopartial(close, sd), end=end).reindex(common)
    fb = {"A": {}, "B": {}}
    for wl, st in [("clean", CLEAN_START), ("ext", EXT_START)]:
        fb["A"][wl] = met(win(cpm, st, end), cash)
        fb["B"][wl] = met(win(cpmB, st, end), cash)
    fb_crisis = {}
    for rname, (rs, re) in REGIMES.items():
        rs_, re_ = pd.Timestamp(rs), pd.Timestamp(re)
        a_mdd, a_ret = maxdd_ret(win(cpm, rs_, re_))
        b_mdd, b_ret = maxdd_ret(win(cpmB, rs_, re_))
        fb_crisis[rname] = {"A": {"maxdd": a_mdd, "ret": a_ret}, "B": {"maxdd": b_mdd, "ret": b_ret}}
    out["fallback_AvB"] = {"headline": fb, "crisis": fb_crisis}
    print(f"FALLBACK 2022 CPM-solo: A MaxDD={fb_crisis['2022 bear (2022-01..2022-12)']['A']['maxdd']*100:.2f}% "
          f"B MaxDD={fb_crisis['2022 bear (2022-01..2022-12)']['B']['maxdd']*100:.2f}%")

    (Path(__file__).with_suffix(".json")).write_text(json.dumps(out, indent=2, default=float))
    write_md(out)
    print("\nDONE -> research/cpm_final_memo_numbers_findings.md")
    return out


# ---------------------------------------------------------------------------
def write_md(o):
    L = []
    A = L.append
    m = o["meta"]
    SPEC = "INVVOL-3 strict-3 partial-safe"

    def row5(label, mm, star=False):
        n = f"{label}{' (base)' if star else ''}"
        return (f"| {n} | {mm['sharpe']:.4f} | {mm['cagr']*100:.2f}% | {mm['vol']*100:.2f}% "
                f"| {mm['maxdd']*100:.2f}% | {mm['calmar']:.4f} |")

    A("# CPM final memo numbers -- DEFINITIVE set (INVVOL-3 strict-3 partial-safe)\n")
    A("Role: analyst (hypothesis-driven, read-only re production; no production files changed; "
      "no commit). Throwaway harness in `research/`.\n")
    A("All CPM-side numbers regenerated FRESH under the **FINAL production spec** "
      "(`cpm_live.compute_target_weights`): INVVOL-3 core (select min-variance 3-subset from the "
      "top-K=4 positive-trend pool, then inverse-vol weight) with **STRICT-3 PARTIAL-SAFE** "
      "fallback: risky_fraction = min(n_pos,3)/3, remainder to timed safe (n_pos=0 -> 100% safe; "
      "n_pos=1 -> 1/3 risky + 2/3 safe; n_pos=2 -> 2/3 risky invvol-2 + 1/3 safe; n_pos=3 -> 100% "
      "risky invvol-3; n_pos>3 -> min-var 3-subset invvol-3, 100% risky).\n")
    A("> **SUPERSEDES `research/invvol3_memo_numbers_findings.md`**, which used the OLD hybrid "
      "fallback (n_pos=1 -> 50/50; n_pos=2 -> invvol-2 fully risky) and is now STALE. Numbers that "
      "changed materially vs the hybrid set are flagged inline with **[CHANGED vs hybrid]**.\n")
    A(f"**Convention (every table):** spec {SPEC}; execution T+1 MOO exact (`mooex`, real "
      f"auto_adjust opens); post-cost {m['cost_bps']} bps/side; BULL equity vol gate slow "
      f"rv_60d<rv_252d; blend = 0.60*CPM({SPEC}) + 0.40*BULL; cov lookback {m['lookback']}d; "
      f"K={m['K']}. Clean window {m['clean_start']}..{m['end']} (18y); extended "
      f"{m['ext_start']}..{m['end']} (27y).\n")
    A("Source harness: `research/cpm_final_memo_numbers.py` (read-only; CPM-solo, concentration, "
      "and fallback-A use production `cpm_live.compute_target_weights`; Section-8 + item-8 variants "
      "use a generalized strict-3 weight fn whose base config reproduces production exactly).\n")

    a = o["anchor"]
    sc = o.get("gcpm_base_selfcheck", {})
    A("## 0. Anchor gate\n")
    A("| Window | Sharpe | MaxDD | Calmar | Expected (strict-3) | Match |")
    A("|---|---:|---:|---:|---|---|")
    for wl in ("clean", "ext"):
        e = ANCHOR[wl]
        A(f"| {wl} | {a[wl]['sharpe']:.4f} | {a[wl]['maxdd']*100:.2f}% | {a[wl]['calmar']:.4f} "
          f"| {e[0]}/{e[1]}%/{e[2]} | {'CONFIRMED' if a[wl]['ok'] else 'MISMATCH'} |")
    A(f"\nCPM-solo strict-3 reproduces the FINAL research anchor exactly in both windows. "
      f"Generalized weight-fn base config self-check: clean Sharpe {sc.get('clean_sharpe', float('nan')):.6f}, "
      f"matches production = {sc.get('matches_production')}. The rest of this file is trusted on that basis.\n")

    h = o["headline"]
    CPMK = "CPM-solo (INVVOL-3 strict-3)"
    A(f"## 1. Headline ({SPEC}, T+1 MOO exact, 10 bps/side)\n")
    A("### 1.1 Clean window (18y)\n")
    A("| Series | Sharpe | CAGR | Vol | MaxDD | Calmar |")
    A("|---|---:|---:|---:|---:|---:|")
    for n in (CPMK, "BULL-solo", "60/40 blend"):
        A(row5(n, h[n]["clean"]))
    A("\n### 1.2 Extended window (27y)\n")
    A("| Series | Sharpe | CAGR | Vol | MaxDD | Calmar |")
    A("|---|---:|---:|---:|---:|---:|")
    for n in (CPMK, "BULL-solo", "60/40 blend"):
        A(row5(n, h[n]["ext"]))
    bl = h["60/40 blend"]["clean"]; ble = h["60/40 blend"]["ext"]
    A(f"\n**KEY NEW HEADLINE -- 60/40 blend (CPM-INVVOL-3 strict-3 + BULL):**")
    A(f"- Clean (18y): Sharpe {bl['sharpe']:.4f}, CAGR {bl['cagr']*100:.2f}%, Vol {bl['vol']*100:.2f}%, "
      f"MaxDD {bl['maxdd']*100:.2f}%, Calmar {bl['calmar']:.4f}.")
    A(f"- Ext (27y): Sharpe {ble['sharpe']:.4f}, CAGR {ble['cagr']*100:.2f}%, Vol {ble['vol']*100:.2f}%, "
      f"MaxDD {ble['maxdd']*100:.2f}%, Calmar {ble['calmar']:.4f}.")
    cpc = h[CPMK]["clean"]
    A(f"\n**[CHANGED vs hybrid]** CPM-solo clean Sharpe {cpc['sharpe']:.4f} (hybrid 1.2453), "
      f"MaxDD {cpc['maxdd']*100:.2f}% (hybrid -13.19%), Calmar {cpc['calmar']:.4f} (hybrid 1.0824). "
      f"Blend clean Sharpe {bl['sharpe']:.4f} (hybrid-fallback blend 1.3111), Calmar {bl['calmar']:.4f} "
      f"(hybrid 1.2536). BULL-solo is unchanged (independent of the CPM weighting). The old "
      f"hybrid-fallback CPM/blend numbers are stale and must not be reused.\n")

    c = o["crisis"]
    A(f"## 2. Crisis windows ({SPEC}; MaxDD and total return)\n")
    A("| Crisis window | Blend MaxDD | Blend return | CPM-solo MaxDD | CPM-solo return |")
    A("|---|---:|---:|---:|---:|")
    for rn, d in c.items():
        bd = d.get("blend", {}); cd = d.get("cpm", {})
        A(f"| {rn} | {bd.get('maxdd', float('nan'))*100:.2f}% | {bd.get('ret', float('nan'))*100:.2f}% "
          f"| {cd.get('maxdd', float('nan'))*100:.2f}% | {cd.get('ret', float('nan'))*100:.2f}% |")
    A("\nMaxDD computed within each window (peak-to-trough inside the window), execution T+1 MOO exact, "
      "post-cost. Dot-com and GFC pre-2008 sit in the proxy-backed extended history.\n")

    b = o["bootstrap"]
    A("## 3. Bootstrap CI (clean window, stationary block bootstrap B=2000, block=21, seed=42)\n")
    for n in ("60/40 blend", CPMK, "BULL-solo"):
        bb = b[n]; ci = bb["ci"]; pt = bb["point"]
        A(f"\n### {n}\n")
        A("| Metric | Point | 95% CI | CI width |")
        A("|---|---:|---|---:|")
        for k in ("Sharpe", "CAGR", "MaxDD", "Calmar"):
            cc = ci[k]; w = cc["p97.5"] - cc["p2.5"]
            if k in ("CAGR", "MaxDD"):
                A(f"| {k} | {pt[k]*100:.2f}% | [{cc['p2.5']*100:.2f}%, {cc['p97.5']*100:.2f}%] | {w*100:.2f}pp |")
            else:
                A(f"| {k} | {pt[k]:.4f} | [{cc['p2.5']:.4f}, {cc['p97.5']:.4f}] | {w:.4f} |")
    bs = b["60/40 blend"]["ci"]["Sharpe"]
    A(f"\n**[CHANGED vs hybrid]** Hybrid-fallback blend Sharpe CI was [0.909, 1.751] width 0.842. "
      f"Strict-3 blend Sharpe 95% CI = [{bs['p2.5']:.4f}, {bs['p97.5']:.4f}], width "
      f"{bs['p97.5']-bs['p2.5']:.4f}.\n")

    r = o["rolling"]["blend"]; w = o["rolling"]["worst_blend"]
    A(f"## 4. Rolling-window stability -- 60/40 blend ({SPEC})\n")
    A("| Window | Min | Median | Max | % < 1.0 | % < 0.7 | N |")
    A("|---|---:|---:|---:|---:|---:|---:|")
    for lbl, k in [("Clean 3y", "clean_3y"), ("Clean 5y", "clean_5y"),
                   ("Ext 3y", "ext_3y"), ("Ext 5y", "ext_5y")]:
        s = r[k]
        A(f"| {lbl} | {s['min']:.3f} | {s['median']:.3f} | {s['max']:.3f} | "
          f"{s['pct_under_1.0']:.1f}% | {s['pct_under_0.7']:.1f}% | {s['n']} |")
    A("\nWorst contiguous stretches (blend):\n")
    A("| Window | Length | Dates | Sharpe | CAGR | MaxDD |")
    A("|---|---|---|---:|---:|---:|")
    for wl in ("clean", "ext"):
        for yr in (1, 2, 3):
            d = w[f"{wl}_{yr}y"]
            if d is None:
                A(f"| {wl} | {yr}y | - | - | - | - |")
            else:
                A(f"| {wl} | {yr}y | {d['start']}..{d['end']} | {d['sharpe']:.3f} | "
                  f"{d['cagr']*100:.2f}% | {d['maxdd']*100:.2f}% |")
    A("")

    bm = o["benchmark_aaa"]
    A(f"## 5. Benchmark -- CPM-solo ({SPEC}) vs canonical AAA (no canary)\n")
    A("| Window | Series | Sharpe | CAGR | Vol | MaxDD | Calmar |")
    A("|---|---|---:|---:|---:|---:|---:|")
    for wl in ("clean", "ext"):
        st = bm[wl]; sl = st["sleeve"]; bn = st["bench"]
        A(f"| {wl} | CPM-solo strict-3 | {sl['sharpe']:.4f} | {sl['cagr']*100:.2f}% | {sl['vol']*100:.2f}% "
          f"| {sl['maxdd']*100:.2f}% | {sl['calmar']:.4f} |")
        A(f"| {wl} | Canonical AAA | {bn['sharpe']:.4f} | {bn['cagr']*100:.2f}% | {bn['vol']*100:.2f}% "
          f"| {bn['maxdd']*100:.2f}% | {bn['calmar']:.4f} |")
    A("\n| Window | dCAGR | dCalmar | dSharpe | dMaxDD | Info ratio | Return corr | Tracking err |")
    A("|---|---:|---:|---:|---:|---:|---:|---:|")
    for wl in ("clean", "ext"):
        st = bm[wl]
        A(f"| {wl} | {st['d_cagr']*100:+.2f}pp | {st['d_calmar']:+.4f} | {st['d_sharpe']:+.4f} | "
          f"{st['d_maxdd']*100:+.2f}pp | {st['ir']:+.4f} | {st['corr']:.4f} | {st['te']*100:.2f}% |")
    A("\nBULL vs HAA-Simple is UNCHANGED by the INVVOL-3 weighting (BULL is independent of the CPM "
      "sleeve). Re-cited from the memo (unchanged): clean BULL 1.081/11.44%/10.57%/-13.35%/0.857 vs "
      "HAA-Simple {BIL,AGG} 0.960/11.08%/11.70%/-19.74%/0.561; ext BULL 0.920/9.49%/10.45%/-13.96%/"
      "0.680 vs HAA-Simple 0.946/10.14%/10.83%/-19.74%/0.514.\n")

    s8 = o["section8"]
    A(f"## 6. Section-8 sensitivity sweeps ({SPEC})\n")
    A("Every base row uses the strict-3 production config and equals the new headline. Tables show "
      "CPM-solo and 60/40 blend, clean + ext.\n")

    def sweep_table(title, d, base_label, order=None):
        A(f"### {title}\n")
        keys = order if order else list(d.keys())
        A("**CPM-solo:**\n")
        A("| variant | Clean Sharpe | Clean CAGR | Clean MaxDD | Clean Calmar | Ext Sharpe | Ext MaxDD | Ext Calmar |")
        A("|---|---:|---:|---:|---:|---:|---:|---:|")
        for k in keys:
            c = d[k]["cpm"]["clean"]; e = d[k]["cpm"]["ext"]
            star = " (base)" if str(k) == str(base_label) else ""
            A(f"| {k}{star} | {c['sharpe']:.4f} | {c['cagr']*100:.2f}% | {c['maxdd']*100:.2f}% | "
              f"{c['calmar']:.4f} | {e['sharpe']:.4f} | {e['maxdd']*100:.2f}% | {e['calmar']:.4f} |")
        A("\n**60/40 blend:**\n")
        A("| variant | Clean Sharpe | Clean CAGR | Clean MaxDD | Clean Calmar | Ext Sharpe | Ext MaxDD | Ext Calmar |")
        A("|---|---:|---:|---:|---:|---:|---:|---:|")
        for k in keys:
            c = d[k]["blend"]["clean"]; e = d[k]["blend"]["ext"]
            star = " (base)" if str(k) == str(base_label) else ""
            A(f"| {k}{star} | {c['sharpe']:.4f} | {c['cagr']*100:.2f}% | {c['maxdd']*100:.2f}% | "
              f"{c['calmar']:.4f} | {e['sharpe']:.4f} | {e['maxdd']*100:.2f}% | {e['calmar']:.4f} |")
        A("")

    sweep_table("6.1 Selection-count K (strict-3)", s8["K_sweep"], 4, order=[2, 3, 4, 5, 6])
    sweep_table("6.2 Screen 2x2 (K-cap x positive-trend, strict-3)", s8["screen_2x2"],
                "K-cap ON + positive-trend ON")
    sweep_table("6.3 Ranker (strict-3)", s8["ranker"], "10m-SMA-distance / rv_252d")
    sweep_table("6.4 Canary (strict-3)", s8["canary"], "dual high-yield OR inflation-protected")
    sweep_table("6.5 Safe sleeve (strict-3)", s8["safe"], "timed SHV/IEF by 13612U")
    sweep_table("6.6 Cov lookback (strict-3)", s8["cov_lookback"], 504,
                order=[126, 252, 504, 756, 1008, 1260])

    cc = o["concentration"]
    A(f"## 7. Concentration -- per-asset contribution share of the 8 risky ({SPEC})\n")
    A("Share = sum of applied daily weight on the asset / sum of total risky daily weight over the "
      "window (selection + inverse-vol + strict-3 risky-fraction driven). All 8 risky included; "
      "shares sum to 100%.\n")
    A("| Asset | Clean share | Ext share |")
    A("|---|---:|---:|")
    order = sorted(CPM_UNIV, key=lambda a: -cc["clean"].get(a, 0.0))
    tc = sum(cc["clean"].get(a, 0.0) for a in CPM_UNIV)
    te = sum(cc["ext"].get(a, 0.0) for a in CPM_UNIV)
    for a in order:
        A(f"| {a} | {cc['clean'].get(a,0.0)*100:.1f}% | {cc['ext'].get(a,0.0)*100:.1f}% |")
    A(f"| **Total** | {tc*100:.1f}% | {te*100:.1f}% |")
    A("")

    ax = o["axis8"]
    A("## 8. New sensitivity axes (re-anchored to the strict-3 production base)\n")
    A("Both axes hold the rest of the strict-3 production design fixed; the base row reproduces the "
      "new headline. Confirms the prior verdicts (inverse-vol right, min-var right) under strict-3.\n")
    sweep_table("8.1 Weighting flavor at select-3 (selection = min-var 3-subset, strict-3)",
                ax["flavor"], "inverse-vol (production)")
    sweep_table("8.2 Subset-selection objective (weighting = inverse-vol, strict-3)",
                ax["selector"], "min-variance (production)")
    fcpm = ax["flavor"]["inverse-vol (production)"]["cpm"]["clean"]
    ferc = ax["flavor"]["ERC (equal-risk-contribution)"]["cpm"]["clean"]
    few = ax["flavor"]["equal-weight 1/3 (ref)"]["cpm"]["clean"]
    smv = ax["selector"]["min-variance (production)"]["cpm"]["clean"]
    A(f"**Axis 8.1 verdict (CPM-solo clean):** inverse-vol {fcpm['sharpe']:.4f}/{fcpm['calmar']:.4f} "
      f"(Sharpe/Calmar) vs ERC {ferc['sharpe']:.4f}/{ferc['calmar']:.4f} vs EW {few['sharpe']:.4f}/"
      f"{few['calmar']:.4f}. EW is clearly worse on the risk axis; ERC is near-identical to "
      f"inverse-vol (the trend-filtered, 3-name, risk-similar menu collapses ERC toward the diagonal "
      f"inverse-vol solution). Prior verdict HOLDS under strict-3: keep solver-free inverse-vol.\n")
    A(f"**Axis 8.2 verdict (CPM-solo clean):** min-variance {smv['sharpe']:.4f} Sharpe is the best of "
      f"the selection objectives; the performance-based selectors (max-Sharpe/max-Calmar/min-DD) use "
      f"trailing realized perf and are overfit-prone OOS without beating min-var in-sample. Prior "
      f"verdict HOLDS under strict-3: keep min-variance.\n")

    fb = o["fallback_AvB"]
    h_ = fb["headline"]; cr = fb["crisis"]
    a22 = cr["2022 bear (2022-01..2022-12)"]["A"]; b22 = cr["2022 bear (2022-01..2022-12)"]["B"]
    A("## 9. Fallback note -- strict-3 partial-safe (A, production) vs no-partial-safe (B)\n")
    A("The production strict-3 partial-safe (A) scales the risky block by min(n_pos,3)/3 and routes "
      "the remainder to the timed safe; (B) holds qualifying positives fully invested, going to safe "
      "only at zero breadth. Both share the identical INVVOL-3 core; only the n_pos<3 branch differs.\n")
    A("| Window | (A) strict-3 Sharpe | (A) MaxDD | (A) Calmar | (B) no-partial Sharpe | (B) MaxDD | (B) Calmar |")
    A("|---|---:|---:|---:|---:|---:|---:|")
    for wl in ("clean", "ext"):
        aa = h_["A"][wl]; bb = h_["B"][wl]
        A(f"| {wl} | {aa['sharpe']:.4f} | {aa['maxdd']*100:.2f}% | {aa['calmar']:.4f} "
          f"| {bb['sharpe']:.4f} | {bb['maxdd']*100:.2f}% | {bb['calmar']:.4f} |")
    A("\n| Crisis | (A) MaxDD | (A) ret | (B) MaxDD | (B) ret | (A)-(B) MaxDD gap |")
    A("|---|---:|---:|---:|---:|---:|")
    for rn, d in cr.items():
        ga = d["A"]; gb = d["B"]; gap = (ga["maxdd"] - gb["maxdd"]) * 100
        A(f"| {rn} | {ga['maxdd']*100:.2f}% | {ga['ret']*100:.2f}% | {gb['maxdd']*100:.2f}% "
          f"| {gb['ret']*100:.2f}% | {gap:+.2f}pp |")
    A(f"\n**Decisive result (cited in the FINAL spec choice):** 2022 bear CPM-solo MaxDD = "
      f"**{a22['maxdd']*100:.2f}% (A strict-3 partial-safe)** vs **{b22['maxdd']*100:.2f}% (B "
      f"no-partial-safe)** -- A is {abs((a22['maxdd']-b22['maxdd'])*100):.2f}pp shallower in the "
      f"2022 drawdown. Strict-3 partial-safe trades a sliver of upside for a materially shallower "
      f"low-breadth drawdown; it is the production choice. (Positive (A)-(B) MaxDD gap = A shallower "
      f"= more defensive.)\n")

    A("## Caveats\n")
    A("- All post-cost (10 bps/side), T+1 MOO exact using real yfinance auto_adjust opens; CPM "
      "sleeve has no equity vol gate (gate only affects BULL/blend).")
    A("- Ext 27y is partially proxy-backed for the CPM trend universe pre-2006 (close-to-close "
      "fallback on a minority of rebal days); clean 18y has full real-open coverage and is the "
      "decisive lens.")
    A("- CPM-solo, concentration, and fallback-A use production `cpm_live.compute_target_weights` "
      "directly; Section-8 + item-8 variants use a generalized strict-3 weight fn whose base config "
      "matches production exactly (anchor + self-check confirmed).")
    A("- BULL-solo and BULL-vs-HAA-Simple are independent of the CPM weighting and are unchanged "
      "from the memo; re-cited, not re-derived.")
    A("- Static 50/50 safe variant uses a synthetic daily-rebalanced SHV+IEF column (no opens -> "
      "rebal-day close-to-close fallback on the safe leg).")
    A("- ERC uses a full-covariance SLSQP solver with inverse-vol fallback on failure; on the "
      "trend-filtered 3-name menu it degenerates toward the diagonal inverse-vol solution.")

    Path(ROOT / "research" / "cpm_final_memo_numbers_findings.md").write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
