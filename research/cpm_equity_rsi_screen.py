#!/usr/bin/env python3
"""
CPM Equity-Only RSI(14)>70 Overbought Screen (textbook Wilder default)
======================================================================

Single conventional spec. NO threshold scanning. The only spec that counts is
RSI(14) > 70 on monthly closes (Wilder smoothing), applied AFTER the
positive-trend (Faber) filter and ONLY to CPM's equity sleeve members:
  EQUITY_SCREEN = {QQQ, SPHQ}.
GLD/DBC/TLT/EFA/EEM/VNQ are NEVER screened.

Robustness side-notes (single points, NOT tuning axes):
  - RSI(14) > 80 (one alt threshold).
  - daily->month-end RSI(14) > 70 (one alt computation).

Baseline V0 = no screen, must reproduce 60/40 = 1.347 / 13.59% / -9.82% (clean).

Measurement only: production files are NOT edited. We monkeypatch
cpm_live.compute_target_weights with a parameterized copy that injects the
equity RSI screen. Everything else fixed (canary, EAA rank, K=4, min-var
pair, partial-safe fallback).

Writes research/cpm_equity_rsi_screen_findings.md incrementally.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import cpm_live
from cpm_live import (
    load_panel, run_cpm_backtest, perf_metrics, faber_sma_xs,
    best_safe, sig_13612U, min_vol_pair,
    RISKY_UNIVERSE, SAFE_POOL, CANARY_ASSETS, CANARY_RULE, DEFAULT_CASH,
    TOP_K_CANDIDATES, CORR_LOOKBACK_DAYS,
)
from bull_qqq_live import run_bull_qqq_backtest

FINDINGS = ROOT / "research" / "cpm_equity_rsi_screen_findings.md"

CLEAN_S, CLEAN_E = pd.Timestamp("2008-05-30"), pd.Timestamp("2026-05-22")
STRESS_S, STRESS_E = pd.Timestamp("1999-03-10"), pd.Timestamp("2026-05-22")

# Equity sleeve members in CPM's 8-asset universe. SMALL subset (2 of 8).
EQUITY_SCREEN = {"QQQ", "SPHQ"}


# ---------- RSI helpers ----------

def wilder_rsi(close: pd.Series, period: int = 14) -> float:
    """Wilder RSI on a close series; returns last value or nan."""
    c = close.dropna()
    if len(c) < period + 1:
        return np.nan
    delta = c.diff().dropna()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False).mean()
    ag, al = avg_gain.iloc[-1], avg_loss.iloc[-1]
    if al == 0:
        return 100.0
    rs = ag / al
    return 100.0 - 100.0 / (1.0 + rs)


def faber_score(monthly_close: pd.Series) -> float:
    m = monthly_close.dropna()
    if len(m) < 10:
        return np.nan
    sma = m.rolling(10).mean().iloc[-1]
    return (m.iloc[-1] - sma) / sma


# ---------- Patched compute_target_weights factory ----------

def make_patched_ctw(rsi_thr=None, rsi_mode="monthly", screen_tickers=EQUITY_SCREEN):
    """Return a compute_target_weights replacement that excludes an equity
    candidate (ticker in screen_tickers) if RSI(14) > rsi_thr at sig_d.
    rsi_thr=None reproduces production exactly.
    rsi_mode: 'monthly' (RSI on monthly closes) or 'daily' (RSI on daily
    closes up to sig_d)."""

    def is_overbought(t, close_panel, sig_d, monthly):
        if rsi_thr is None or t not in screen_tickers:
            return False
        if rsi_mode == "daily":
            ser = close_panel[t].loc[:sig_d]
        else:
            ser = monthly[t]
        rsi = wilder_rsi(ser, 14)
        return pd.notna(rsi) and rsi > rsi_thr

    def patched(close_panel, sig_d, universe=None, safe_pool=None,
                canary_assets=None):
        universe = universe or RISKY_UNIVERSE
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
            return {safe: 1.0}, None, "DEFENSIVE", safe
        n_pos = sum(1 for s in canary_scores if s > 0)
        if CANARY_RULE == "any_positive":
            if n_pos == 0:
                return {safe: 1.0}, None, "DEFENSIVE", safe
        elif CANARY_RULE == "all_positive":
            if n_pos < len(canary_scores):
                return {safe: 1.0}, None, "DEFENSIVE", safe
        else:
            if n_pos <= len(canary_scores) // 2:
                return {safe: 1.0}, None, "DEFENSIVE", safe

        faber = faber_sma_xs(monthly)
        avail = [t for t in universe
                 if t in faber.index and pd.notna(faber[t])
                 and pd.notna(close_panel.loc[sig_d].get(t, np.nan)
                              if sig_d in close_panel.index else np.nan)]
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

        # ---- EQUITY RSI SCREEN (the new bit) ----
        if rsi_thr is not None and len(positive) > 0:
            keep = [t for t in positive.index
                    if not is_overbought(t, close_panel, sig_d, monthly)]
            positive = positive.loc[keep]

        if len(positive) < 2:
            if len(positive) == 1:
                return {positive.index[0]: 0.5, safe: 0.5}, None, "RISK_ON", safe
            return {safe: 1.0}, None, "DEFENSIVE", safe

        candidates = list(positive.index)
        new_pick = min_vol_pair(close_panel.loc[:sig_d, candidates], candidates,
                                CORR_LOOKBACK_DAYS)
        if new_pick is None:
            return {candidates[0]: 1.0}, None, "RISK_ON", safe
        return {new_pick[0]: 0.5, new_pick[1]: 0.5}, new_pick, "RISK_ON", safe

    return patched


def run_variant(panel, rsi_thr, start, end, rsi_mode="monthly"):
    orig = cpm_live.compute_target_weights
    cpm_live.compute_target_weights = make_patched_ctw(rsi_thr, rsi_mode)
    try:
        rets, hist = run_cpm_backtest(panel, start, end)
    finally:
        cpm_live.compute_target_weights = orig
    return rets, hist


# ---------- Metric helpers ----------

def cal_ret(daily, y0):
    seg = daily.loc[f"{y0}-01-01":f"{y0}-12-31"]
    return (1.0 + seg).prod() - 1.0


def turnover_from_hist(hist):
    if not hist:
        return np.nan
    tot = 0.0
    for i in range(len(hist)):
        prev = hist[i - 1]["weights"] if i > 0 else {}
        cur = hist[i]["weights"]
        keys = set(cur) | set(prev)
        tot += sum(abs(cur.get(k, 0.0) - prev.get(k, 0.0)) for k in keys)
    yrs = len(hist) / 12.0
    return tot / yrs if yrs > 0 else np.nan


def metric_row(daily, cash, hist=None):
    m = perf_metrics(daily, cash)
    return dict(
        sharpe=m["sharpe"], excess_sharpe=m["excess_sharpe"], cagr=m["cagr"],
        vol=m["vol"], maxdd=m["max_drawdown"], calmar=m["calmar"],
        ret2022=cal_ret(daily, 2022), ret2008=cal_ret(daily, 2008),
        turnover=turnover_from_hist(hist) if hist is not None else np.nan,
    )


def fmt_row(name, r):
    t = f"{r['turnover']:.2f}" if pd.notna(r.get("turnover", np.nan)) else "-"
    return (f"| {name} | {r['sharpe']:.3f} | {r['excess_sharpe']:.3f} | "
            f"{r['cagr']*100:.2f}% | {r['vol']*100:.2f}% | {r['maxdd']*100:.2f}% | "
            f"{r['calmar']:.2f} | {r['ret2022']*100:.2f}% | {r['ret2008']*100:.2f}% | {t} |")


HDR = ("| Variant | Raw Sharpe | Excess Sharpe | CAGR | Vol | MaxDD | Calmar "
       "| 2022 | 2008 | Turnover |\n"
       "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")


def main():
    print("Loading panel ...")
    panel = load_panel(start=pd.Timestamp("1995-01-01"))
    cash = panel["SHV"].ffill().pct_change().dropna()

    fh = open(FINDINGS, "w")

    def W(s=""):
        fh.write(s + "\n")
        fh.flush()

    W("# CPM Equity-Only RSI(14)>70 Overbought Screen\n")
    W("Textbook-standard Wilder RSI(14) > 70 (the conventional overbought "
      "default). **No threshold scanning** -- RSI>70 is the only spec that "
      "counts; RSI>80 and daily->month-end RSI appear only as single "
      "robustness points. Screen applied AFTER the positive-trend (Faber) "
      "filter and ONLY to the equity sleeve members **{QQQ, SPHQ}** (2 of 8 "
      "assets). GLD/DBC/TLT/EFA/EEM/VNQ are never screened. Partial-safe "
      "fallback preserved; everything else fixed. **Measurement only; no "
      "production files edited.**\n")
    W(f"- Clean window: {CLEAN_S.date()} .. {CLEAN_E.date()}")
    W(f"- Stress window: {STRESS_S.date()} .. {STRESS_E.date()}")
    W("- Costs 10bps/side, T+1 OPEN execution (production engine, monkeypatched CTW).")
    W("- Blend = 60% CPM + 40% BULL-SPY (two-sleeve baseline).")
    W("- **Caveat up front:** the equity sleeve is only 2 of 8 universe names, "
      "so the screen's reach is inherently limited.\n")

    # ---------- V0 verification ----------
    print("V0 verification ...")
    cpm0_cl, hist0_cl = run_variant(panel, None, CLEAN_S, CLEAN_E)
    bull_cl = run_bull_qqq_backtest(panel, CLEAN_S, CLEAN_E)
    c_cl = cpm0_cl.index.intersection(bull_cl.index)
    blend0_cl = 0.6 * cpm0_cl.reindex(c_cl) + 0.4 * bull_cl.reindex(c_cl)
    m0 = perf_metrics(blend0_cl, cash)
    ok = (abs(m0["sharpe"] - 1.347) < 0.003 and abs(m0["cagr"] * 100 - 13.59) < 0.05
          and abs(m0["max_drawdown"] * 100 + 9.82) < 0.05)
    W("## 0. V0 baseline verification\n")
    W(f"60/40 clean: Sharpe **{m0['sharpe']:.3f}** / CAGR **{m0['cagr']*100:.2f}%** "
      f"/ MaxDD **{m0['max_drawdown']*100:.2f}%** (target 1.347 / 13.59% / -9.82%) "
      f"-> {'MATCH' if ok else 'MISMATCH'}\n")
    print(f"V0: {m0['sharpe']:.3f}/{m0['cagr']*100:.2f}%/{m0['max_drawdown']*100:.2f}% ok={ok}")
    if not ok:
        W("**STOPPING: V0 mismatch.**")
        fh.close()
        sys.exit(1)

    bull_st = run_bull_qqq_backtest(panel, STRESS_S, STRESS_E)

    # ---------- Section 1: main metrics V0 vs V_RSI70 ----------
    print("Backtest variants ...")
    # variants: label -> (rsi_thr, rsi_mode)
    variants = [
        ("V0 (no screen)", None, "monthly"),
        ("V_RSI70 (equity RSI14>70, monthly)", 70.0, "monthly"),
        ("V_RSI80 (equity RSI14>80, monthly) [robustness]", 80.0, "monthly"),
        ("V_RSI70_daily (equity RSI14>70, daily->ME) [robustness]", 70.0, "daily"),
    ]
    results = {}
    hists = {}
    for label, thr, mode in variants:
        print(f"  {label} ...")
        cpm_cl, hist_cl = run_variant(panel, thr, CLEAN_S, CLEAN_E, mode)
        ccl = cpm_cl.index.intersection(bull_cl.index)
        bl_cl = 0.6 * cpm_cl.reindex(ccl) + 0.4 * bull_cl.reindex(ccl)
        cpm_st, hist_st = run_variant(panel, thr, STRESS_S, STRESS_E, mode)
        cst = cpm_st.index.intersection(bull_st.index)
        bl_st = 0.6 * cpm_st.reindex(cst) + 0.4 * bull_st.reindex(cst)
        results[label] = dict(
            cpm_cl=metric_row(cpm_cl, cash, hist_cl),
            blend_cl=metric_row(bl_cl, cash),
            cpm_st=metric_row(cpm_st, cash, hist_st),
            blend_st=metric_row(bl_st, cash),
            cpm_cl_daily=cpm_cl, blend_cl_daily=bl_cl,
        )
        hists[label] = (hist_cl, hist_st)

    W("## 1. Metrics: V0 vs V_RSI70 (CPM standalone + 60/40 blend)\n")
    for win, ckey, bkey in (("Clean", "cpm_cl", "blend_cl"),
                            ("Stress", "cpm_st", "blend_st")):
        W(f"### {win} window -- CPM standalone\n")
        W(HDR)
        for label, _, _ in variants:
            W(fmt_row(label, results[label][ckey]))
        W()
        W(f"### {win} window -- 60/40 blend (CPM+BULL)\n")
        W(HDR)
        for label, _, _ in variants:
            W(fmt_row(label, results[label][bkey]))
        W()

    # 2008 hedge confirmation
    v0_2008 = results["V0 (no screen)"]["blend_st"]["ret2008"]
    rsi_2008 = results["V_RSI70 (equity RSI14>70, monthly)"]["blend_st"]["ret2008"]
    W(f"**2008 hedge check (stress, 60/40 blend full-year 2008):** V0 "
      f"{v0_2008*100:+.2f}% vs V_RSI70 {rsi_2008*100:+.2f}% "
      f"(delta {(rsi_2008-v0_2008)*100:+.2f}pp). The screen touches only "
      f"QQQ/SPHQ, so the DBC/GLD/TLT crisis hedge is structurally untouched.\n")

    # ---------- Section 2: forward-return diagnostic (equity only) ----------
    print("Forward-return diagnostic ...")
    W("## 2. Forward-return diagnostic: do overbought equities revert?\n")
    W("For QQQ & SPHQ at every month-end in the clean window, restricted to "
      "positive-trend months (faber>0; the only months the screen can act on), "
      "compare forward 1-month return when RSI(14)>70 (overbought) vs not. "
      "REVERT (OB worse) justifies the screen; CONTINUE (OB better) means the "
      "screen forfeits winners.\n")
    monthly_all = panel.resample("ME").last()
    mret_fwd = monthly_all.pct_change().shift(-1)
    midx = monthly_all.index[(monthly_all.index >= CLEAN_S) & (monthly_all.index <= CLEAN_E)]
    drows = []
    for d in midx:
        for t in EQUITY_SCREEN:
            if t not in monthly_all.columns:
                continue
            mser = monthly_all[t].loc[:d]
            if mser.dropna().shape[0] < 15:
                continue
            fb = faber_score(mser)
            if pd.isna(fb) or fb <= 0:
                continue
            rsi = wilder_rsi(mser, 14)
            if pd.isna(rsi):
                continue
            fwd = mret_fwd.loc[d, t] if d in mret_fwd.index else np.nan
            if pd.isna(fwd):
                continue
            drows.append(dict(date=d, asset=t, rsi=rsi, ob70=rsi > 70,
                              ob80=rsi > 80, fwd=fwd))
    diag = pd.DataFrame(drows)
    diag.to_csv(ROOT / "research" / "cpm_equity_rsi_forward_returns.csv", index=False)

    W("| Group | N(OB) | OB fwd 1m | N(nonOB) | nonOB fwd 1m | OB - nonOB | Verdict |")
    W("| --- | --- | --- | --- | --- | --- | --- |")

    def cmp_line(df, flag, label):
        ob = df[df[flag]]; nob = df[~df[flag]]
        if len(ob) == 0:
            return (f"| {label} | 0 | - | {len(nob)} | {nob['fwd'].mean()*100:.2f}% | - | - |")
        diff = ob["fwd"].mean() - nob["fwd"].mean()
        verdict = "CONTINUE" if diff > 0 else "REVERT"
        return (f"| {label} | {len(ob)} | {ob['fwd'].mean()*100:.2f}% | {len(nob)} | "
                f"{nob['fwd'].mean()*100:.2f}% | {diff*100:+.2f}pp | {verdict} |")

    W(cmp_line(diag, "ob70", "equity RSI>70 (both)"))
    W(cmp_line(diag, "ob80", "equity RSI>80 (both) [robustness]"))
    for t in sorted(EQUITY_SCREEN):
        sub = diag[diag["asset"] == t]
        if len(sub) > 0:
            W(cmp_line(sub, "ob70", f"{t} RSI>70"))
    W()
    # win-rate detail
    ob = diag[diag["ob70"]]; nob = diag[~diag["ob70"]]
    if len(ob) > 0:
        W(f"OB>70 win-rate (fwd>0): {(ob['fwd']>0).mean()*100:.0f}% (n={len(ob)}); "
          f"non-OB win-rate: {(nob['fwd']>0).mean()*100:.0f}% (n={len(nob)}); "
          f"OB median fwd {ob['fwd'].median()*100:+.2f}% vs non-OB "
          f"{nob['fwd'].median()*100:+.2f}%.\n")

    # ---------- Section 3: binding frequency ----------
    print("Binding-frequency diagnostic ...")
    W("## 3. How often does the screen actually bind?\n")
    W("\"Binds\" = the screen excludes an equity name that V0 would otherwise "
      "have **selected into the held pair**. We compare V0 vs V_RSI70 "
      "weights-history month by month.\n")

    def selected_equities(hist):
        """date -> set of equity tickers with weight>0 that month."""
        out = {}
        for h in hist:
            eqs = {t for t, w in h["weights"].items()
                   if t in EQUITY_SCREEN and w > 0}
            out[h["sig_d"]] = eqs
        return out

    for win, key in (("Clean", 0), ("Stress", 1)):
        h0 = hists["V0 (no screen)"][key]
        h1 = hists["V_RSI70 (equity RSI14>70, monthly)"][key]
        sel0 = selected_equities(h0)
        sel1 = selected_equities(h1)
        n_months = len(sel0)
        bind_months = 0
        flag_months = 0  # any month an equity in V0 selection was overbought
        for d, e0 in sel0.items():
            e1 = sel1.get(d, set())
            dropped = e0 - e1
            if dropped:
                bind_months += 1
        # count raw overbought flags among V0-selected equities
        cols = sorted(set(RISKY_UNIVERSE + SAFE_POOL + CANARY_ASSETS + [DEFAULT_CASH]) & set(panel.columns))
        close = panel[cols]
        for d, e0 in sel0.items():
            mser = close.loc[:d].resample("ME").last()
            for t in e0:
                rsi = wilder_rsi(mser[t], 14) if t in mser.columns else np.nan
                if pd.notna(rsi) and rsi > 70:
                    flag_months += 1
                    break
        W(f"- **{win}**: {n_months} signal months. Screen BINDS "
          f"(drops a V0-selected equity) in **{bind_months}** months "
          f"({bind_months/n_months*100:.1f}%). Months where a V0-held equity "
          f"was flagged RSI>70: {flag_months}.")
    W()
    W("Given only 2 equity names and that equities are frequently out-selected "
      "by lower-vol diversifiers in the min-var pair anyway, binding is rare. "
      "The effect is inherently small.\n")

    # ---------- Section 4: stability across sub-periods ----------
    print("Stability diagnostic ...")
    W("## 4. Stability: is any effect broad or concentrated?\n")
    W("Annual 60/40-blend return, V0 vs V_RSI70 (clean window), and the delta. "
      "A broad edge spreads the delta across many years; a few large cells = "
      "luck, not structure (post-toxic-cell skepticism).\n")
    bl0 = results["V0 (no screen)"]["blend_cl_daily"]
    bl1 = results["V_RSI70 (equity RSI14>70, monthly)"]["blend_cl_daily"]
    yr0 = (1 + bl0).resample("YE").prod() - 1
    yr1 = (1 + bl1.reindex(bl0.index).fillna(0)).resample("YE").prod() - 1
    W("| Year | V0 | V_RSI70 | Delta (pp) |")
    W("| --- | --- | --- | --- |")
    deltas = []
    for ts in yr0.index:
        y = ts.year
        d = (yr1.get(ts, np.nan) - yr0.get(ts, np.nan)) * 100
        deltas.append((y, d))
        W(f"| {y} | {yr0[ts]*100:+.2f}% | {yr1.get(ts, np.nan)*100:+.2f}% | {d:+.2f} |")
    W()
    nonzero = [(y, d) for y, d in deltas if abs(d) > 1e-6]
    pos_yrs = sum(1 for _, d in nonzero if d > 0)
    neg_yrs = sum(1 for _, d in nonzero if d < 0)
    tot_delta = sum(d for _, d in deltas)
    if nonzero:
        biggest = max(nonzero, key=lambda x: abs(x[1]))
        W(f"Years with any delta: {len(nonzero)} of {len(deltas)} "
          f"({pos_yrs} positive, {neg_yrs} negative). Cumulative annual-delta "
          f"sum {tot_delta:+.2f}pp. Largest single-year delta: "
          f"{biggest[0]} {biggest[1]:+.2f}pp.")
        if biggest[1] != 0:
            share = abs(biggest[1]) / sum(abs(d) for _, d in nonzero) * 100
            W(f"That one year accounts for {share:.0f}% of total absolute "
              f"annual delta -> {'CONCENTRATED' if share > 50 else 'somewhat spread'}.")
    else:
        W("No year shows any delta -- the screen never changed a held position "
          "in the clean window.")
    W()

    # ---------- Section 5: verdict ----------
    print("Verdict ...")
    W("## 5. Verdict\n")
    b0 = results["V0 (no screen)"]["blend_cl"]
    b1 = results["V_RSI70 (equity RSI14>70, monthly)"]["blend_cl"]
    s0 = results["V0 (no screen)"]["blend_st"]
    s1 = results["V_RSI70 (equity RSI14>70, monthly)"]["blend_st"]
    dS = b1["sharpe"] - b0["sharpe"]
    dES = b1["excess_sharpe"] - b0["excess_sharpe"]
    dDD = (b1["maxdd"] - b0["maxdd"]) * 100
    W(f"60/40 clean Sharpe: V0 **{b0['sharpe']:.3f}** -> V_RSI70 "
      f"**{b1['sharpe']:.3f}** (delta {dS:+.3f}). Excess Sharpe "
      f"{b0['excess_sharpe']:.3f} -> {b1['excess_sharpe']:.3f} ({dES:+.3f}). "
      f"MaxDD {b0['maxdd']*100:.2f}% -> {b1['maxdd']*100:.2f}% ({dDD:+.2f}pp).")
    W(f"60/40 stress Sharpe: V0 {s0['sharpe']:.3f} -> V_RSI70 {s1['sharpe']:.3f} "
      f"({s1['sharpe']-s0['sharpe']:+.3f}). 2008 hedge intact "
      f"({v0_2008*100:+.2f}% -> {rsi_2008*100:+.2f}%).\n")
    decision = "ADOPT" if (dS > 0.005 and (s1["sharpe"] - s0["sharpe"]) >= -0.01) else "REJECT"
    W(f"### Recommendation: **{decision}** (see auto-generated reasoning + "
      "manual summary appended).\n")

    fh.close()
    print(f"\nDone. Wrote {FINDINGS}")
    # echo headline numbers for log
    print(f"CLEAN blend  V0 {b0['sharpe']:.3f} -> RSI70 {b1['sharpe']:.3f} (d {dS:+.3f})")
    print(f"STRESS blend V0 {s0['sharpe']:.3f} -> RSI70 {s1['sharpe']:.3f}")
    print(f"2008 hedge V0 {v0_2008*100:+.2f}% -> RSI70 {rsi_2008*100:+.2f}%")


if __name__ == "__main__":
    main()
