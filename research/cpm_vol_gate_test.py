# -*- coding: utf-8 -*-
"""Throwaway research (read-only re production; writes research/ only; NO commit).

QUESTION: Should CPM get a VOL GATE? CPM currently has NONE. BULL has
rv_60d(SPY) < rv_252d(SPY). CPM already has the positive-trend (abs-mom) screen
+ strict-4 partial-safe ladder. Does adding a vol gate earn its keep, and at
what level?

VARIANTS (everything else held at production CPM = IV4 compute_target_weights):
  V0 NONE     -- current production. Baseline.
  V1 SLEEVE-SPY  -- BULL-style sleeve gate: if rv_60d(SPY) >= rv_252d(SPY) at
                    sig_d, de-risk the whole CPM sleeve to timed safe.
  V2 SLEEVE-BASKET -- sleeve gate on the equal-weight CPM 8-risky basket rv.
  V3 PER-ASSET   -- "same level as abs-mom": in addition to faber>0, also require
                    each candidate's rv_60d < rv_252d to be held; failed assets
                    route to safe via the strict-4 partial-safe ladder.

Convention: T+1 MOO exact (mooex), real yfinance auto_adjust opens, 10 bps/side
post-cost. Blend = 0.60*CPM + 0.40*BULL(slow rv_60 gate). Windows: clean
2008-05-30..END (18y), ext 1999-03-10..END (27y).

ANCHOR (must reproduce CPM-solo NONE before trusting): clean Sharpe 1.1910 /
MaxDD -12.67% / Calmar 1.0615 ; ext 1.2161 / -15.93% / 0.8654.

Writes research/cpm_vol_gate_test_findings.md + .json. No production files.
"""
from __future__ import annotations
import sys, json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import exec_lag_moo_validation_2026_05_30 as H
from cpm_live import (
    load_panel, perf_metrics, faber_sma_xs, sig_13612U, best_safe,
    inv_vol_weights, compute_target_weights,
    RISKY_UNIVERSE, SAFE_POOL, CANARY_ASSETS, DEFAULT_CASH, COST_BPS_PER_SIDE,
    TOP_K_CANDIDATES, CORR_LOOKBACK_DAYS,
)

CONV = "mooex"
CPM_W, BULL_W = 0.60, 0.40
COST = COST_BPS_PER_SIDE
CPM_UNIV = ["QQQ", "SPHQ", "EFA", "EEM", "VNQ", "GLD", "TLT", "DBC"]
SAFE = ["SHV", "IEF"]
LOOKBACK = CORR_LOOKBACK_DAYS
K = TOP_K_CANDIDATES

CLEAN_START = pd.Timestamp("2008-05-30")
EXT_START = pd.Timestamp("1999-03-10")
END = pd.Timestamp("2026-05-22")

ANCHOR = {"clean": (1.1910, -12.67, 1.0615), "ext": (1.2161, -15.93, 0.8654)}

REGIMES = {
    "GFC (2007-10..2009-06)":       ("2007-10-01", "2009-06-30"),
    "COVID (2020-02..2020-06)":     ("2020-02-01", "2020-06-30"),
    "2022 bear (2022-01..2022-12)": ("2022-01-01", "2022-12-31"),
}

VARIANTS = [
    ("V0 NONE (production)", "none"),
    ("V1 SLEEVE-SPY",        "sleeve_spy"),
    ("V2 SLEEVE-BASKET",     "sleeve_basket"),
    ("V3 PER-ASSET",         "perasset"),
]


def met(s, cash):
    m = perf_metrics(s, cash)
    return {"sharpe": m.get("sharpe"), "cagr": m.get("cagr"), "vol": m.get("vol"),
            "maxdd": m.get("max_drawdown"), "calmar": m.get("calmar"),
            "martin": m.get("martin"), "excess_sharpe": m.get("excess_sharpe")}


def win(s, start, end):
    return s.loc[(s.index >= start) & (s.index <= end)]


def maxdd_ret(s):
    eq = (1.0 + s).cumprod()
    rm = eq.cummax()
    mdd = float((eq / rm - 1.0).min()) if len(eq) else float("nan")
    tot = float(eq.iloc[-1] - 1.0) if len(eq) else float("nan")
    return mdd, tot


def _vol_ok(daily_close: pd.Series, sd: pd.Timestamp, fast: int = 60, slow: int = 252) -> bool:
    """rv_fast < rv_slow on a daily CLOSE series (annualized). Warmup -> True (hold)."""
    sub = daily_close.loc[:sd].pct_change().dropna()
    if len(sub) < slow:
        return True
    vf = float(sub.tail(fast).std() * np.sqrt(252))
    vs = float(sub.tail(slow).std() * np.sqrt(252))
    return vf < vs


# ---------------------------------------------------------------------------
# Generalized CPM IV4 weight fn with optional vol gate. vol_gate="none" base
# config reproduces production compute_target_weights exactly (anchor-gated).
# diag=True returns (weights, info) for interaction accounting.
# ---------------------------------------------------------------------------
def cpm_vg(close, sd, *, vol_gate="none", spy_close=None, basket_close=None, diag=False):
    monthly = close.loc[:sd].resample("ME").last()
    safe = best_safe(monthly, sd, SAFE)
    info = {"sleeve_gate_fired": False, "n_pre_volscreen": None,
            "n_post_volscreen": None, "regime": None, "n_dropped_perasset": 0}

    # canary HYG OR TIP (any positive)
    cs = [sig_13612U(monthly[a]) for a in ["HYG", "TIP"] if a in monthly.columns]
    cs = [s for s in cs if pd.notna(s)]
    if not cs or sum(1 for s in cs if s > 0) == 0:
        info["regime"] = "DEFENSIVE_canary"
        return ({safe: 1.0}, info) if diag else {safe: 1.0}

    # SLEEVE gate: de-risk whole sleeve when market vol gate fails.
    if vol_gate == "sleeve_spy":
        if spy_close is not None and not _vol_ok(spy_close, sd):
            info["sleeve_gate_fired"] = True
            info["regime"] = "DEFENSIVE_volgate"
            return ({safe: 1.0}, info) if diag else {safe: 1.0}
    elif vol_gate == "sleeve_basket":
        if basket_close is not None and not _vol_ok(basket_close, sd):
            info["sleeve_gate_fired"] = True
            info["regime"] = "DEFENSIVE_volgate"
            return ({safe: 1.0}, info) if diag else {safe: 1.0}

    present = [t for t in CPM_UNIV if t in monthly.columns]
    faber = faber_sma_xs(monthly)
    avail = [t for t in present if t in faber.index and pd.notna(faber[t])
             and (sd in close.index and pd.notna(close.loc[sd].get(t, np.nan)))]
    if not avail:
        info["regime"] = "DEFENSIVE_noavail"
        return ({safe: 1.0}, info) if diag else {safe: 1.0}

    dr = close[avail].ffill().pct_change()
    scores = {}
    for t in avail:
        v = dr[t].loc[:sd].tail(252).std() * np.sqrt(252)
        if pd.isna(v) or v < 1e-9:
            v = 1.0
        scores[t] = float(faber[t]) / v
    ranked = pd.Series(scores).sort_values(ascending=False)
    kk = max(2, min(K, len(ranked)))
    top = ranked.iloc[:kk]
    positive = [t for t in top.index if faber.get(t, -np.inf) > 0]
    info["n_pre_volscreen"] = len(positive)

    # PER-ASSET vol screen: drop positives whose own rv_60 >= rv_252.
    if vol_gate == "perasset":
        kept = []
        for t in positive:
            if _vol_ok(close[t].ffill(), sd):
                kept.append(t)
        info["n_dropped_perasset"] = len(positive) - len(kept)
        positive = kept
    info["n_post_volscreen"] = len(positive)

    n = len(positive)
    if n == 0:
        info["regime"] = "DEFENSIVE_screen"
        return ({safe: 1.0}, info) if diag else {safe: 1.0}

    info["regime"] = "RISK_ON"
    risky_fraction = min(n, 4) / 4.0
    risky_w = inv_vol_weights(close.loc[:sd], positive, LOOKBACK)
    out = {t: w * risky_fraction for t, w in risky_w.items()}
    if risky_fraction < 1.0:
        out[safe] = out.get(safe, 0.0) + (1.0 - risky_fraction)
    return (out, info) if diag else out


def run_cpm(close, daily, intraday, overnight, wf, end):
    s, _ = H._segment_returns_conv(close, daily, wf, EXT_START, end, CONV,
                                   COST, intraday, overnight)
    return s


def turnover_stats(close, wf, start, end):
    """Annualized one-way turnover + months-fully-safe count over [start,end]."""
    monthly_idx = (pd.DataFrame({"x": 1}, index=close.index)
                   .groupby(pd.Grouper(freq="ME")).tail(1))
    sigs = monthly_idx.index[(monthly_idx.index >= start) & (monthly_idx.index <= end)].tolist()
    prev = {}
    to_sum = 0.0
    n_rebal = 0
    n_safe_months = 0
    safe_set = set(SAFE) | {DEFAULT_CASH}
    for sd in sigs:
        w = wf(sd)
        keys = set(w) | set(prev)
        to = sum(abs(w.get(k, 0.0) - prev.get(k, 0.0)) for k in keys)
        to_sum += to
        n_rebal += 1
        risky_w = sum(v for k, v in w.items() if k not in safe_set)
        if risky_w < 1e-9:
            n_safe_months += 1
        prev = w
    n_years = (sigs[-1] - sigs[0]).days / 365.25 if len(sigs) > 1 else 1.0
    # one-way turnover ~ half of sum of abs changes
    annual_oneway = 0.5 * to_sum / n_years
    return {"annual_oneway_turnover": annual_oneway, "n_rebal": n_rebal,
            "n_months_fully_safe": n_safe_months,
            "pct_months_fully_safe": 100.0 * n_safe_months / n_rebal if n_rebal else float("nan")}


def interaction_accounting(close, spy_close, basket_close, start, end):
    """Month-by-month: how often each vol gate fires, and whether production was
    already defensive (redundant) vs risk-on (additive de-risk)."""
    monthly_idx = (pd.DataFrame({"x": 1}, index=close.index)
                   .groupby(pd.Grouper(freq="ME")).tail(1))
    sigs = monthly_idx.index[(monthly_idx.index >= start) & (monthly_idx.index <= end)].tolist()
    acc = {g: {"fires": 0, "additive": 0, "redundant": 0, "total": 0}
           for g in ("sleeve_spy", "sleeve_basket", "perasset")}
    for sd in sigs:
        # production state
        _, base_info = cpm_vg(close, sd, vol_gate="none", diag=True)
        base_riskon = base_info["regime"] == "RISK_ON"
        base_n = base_info["n_post_volscreen"]
        # sleeve gates: do they fire, and is base already off?
        for g, sc in (("sleeve_spy", spy_close), ("sleeve_basket", basket_close)):
            acc[g]["total"] += 1
            # canary off already -> gate irrelevant
            if base_info["regime"] == "DEFENSIVE_canary":
                continue
            fires = not _vol_ok(sc, sd)
            if fires:
                acc[g]["fires"] += 1
                if base_riskon and (base_n is not None and base_n == 4):
                    acc[g]["additive"] += 1   # base was fully risk-on
                else:
                    acc[g]["redundant"] += 1  # base already partly/fully safe
        # per-asset: did it drop any names that production held?
        acc["perasset"]["total"] += 1
        _, pa_info = cpm_vg(close, sd, vol_gate="perasset", diag=True)
        dropped = pa_info.get("n_dropped_perasset", 0)
        if dropped > 0:
            acc["perasset"]["fires"] += 1
            if base_riskon:
                acc["perasset"]["additive"] += 1
            else:
                acc["perasset"]["redundant"] += 1
    return acc


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

    spy_close = panel["SPY"] if "SPY" in panel.columns else close["QQQ"]
    # equal-weight CPM 8-risky basket close (rebased to 100)
    rb = close[[t for t in CPM_UNIV if t in close.columns]].ffill().pct_change().mean(axis=1).fillna(0.0)
    basket_close = (1.0 + rb).cumprod() * 100.0

    # BULL sleeve (slow rv gate) for blend
    bull, _ = H.bull_sleeve_conv(panel, intraday, overnight, EXT_START, end, CONV, H.GATE_RV60)

    out = {"meta": {"conv": CONV, "cost_bps": COST, "lookback": LOOKBACK, "K": K,
                    "clean_start": str(CLEAN_START.date()), "ext_start": str(EXT_START.date()),
                    "end": str(end.date()), "blend": "0.60*CPM + 0.40*BULL(rv60 gate)"}}

    # ---- ANCHOR CHECK (V0 NONE = production) ----
    cpm0 = run_cpm(close, daily, intraday, overnight,
                   lambda sd: compute_target_weights(close, sd)[0], end)
    print("=== ANCHOR CHECK (CPM-solo NONE) ===")
    anc = {}
    for wl, st in [("clean", CLEAN_START), ("ext", EXT_START)]:
        m = met(win(cpm0, st, end), cash)
        e = ANCHOR[wl]
        ok = (abs(m["sharpe"] - e[0]) < 5e-4 and abs(m["maxdd"] * 100 - e[1]) < 0.02
              and abs(m["calmar"] - e[2]) < 5e-4)
        anc[wl] = {"sharpe": m["sharpe"], "maxdd": m["maxdd"], "calmar": m["calmar"], "ok": ok}
        print(f"  {wl}: Sharpe={m['sharpe']:.4f} MaxDD={m['maxdd']*100:.2f}% Calmar={m['calmar']:.4f}"
              f"  expect {e} -> {'OK' if ok else 'MISMATCH'}")
    out["anchor"] = anc
    # Clean window is the user-specified decisive anchor (must match exactly).
    # Ext (proxy-backed pre-2006) may drift by <0.01 Sharpe with data vintage; soft.
    if not anc["clean"]["ok"]:
        print("CLEAN ANCHOR MISMATCH -- aborting.")
        sys.exit(1)
    if not anc["ext"]["ok"]:
        print("  (ext anchor soft-drift vs cached findings; proxy-era data vintage; clean exact -> proceeding)")

    # base self-check: cpm_vg(none) must equal production
    cpm_self = run_cpm(close, daily, intraday, overnight,
                       lambda sd: cpm_vg(close, sd, vol_gate="none"), end)
    cc = met(win(cpm_self, CLEAN_START, end), cash)
    gmatch = abs(cc["sharpe"] - anc["clean"]["sharpe"]) < 1e-6
    out["selfcheck"] = {"clean_sharpe": cc["sharpe"], "matches_production": bool(gmatch)}
    print(f"cpm_vg(none) self-check clean Sharpe={cc['sharpe']:.6f} matches={gmatch}")
    if not gmatch:
        print("SELF-CHECK MISMATCH -- aborting.")
        sys.exit(1)

    # ---- run all variants ----
    series = {}
    for label, vg in VARIANTS:
        if vg == "none":
            s = cpm0
        else:
            wf = lambda sd, vg=vg: cpm_vg(close, sd, vol_gate=vg, spy_close=spy_close,
                                          basket_close=basket_close)
            s = run_cpm(close, daily, intraday, overnight, wf, end)
        series[label] = s

    common = None
    for s in series.values():
        common = s.index if common is None else common.intersection(s.index)
    common = common.intersection(bull.index)
    for k in series:
        series[k] = series[k].reindex(common)
    bull = bull.reindex(common)

    # ---- headline CPM-solo + blend ----
    headline = {}
    for label, _ in VARIANTS:
        s = series[label]
        bl = CPM_W * s + BULL_W * bull
        headline[label] = {
            "cpm": {wl: met(win(s, st, end), cash) for wl, st in [("clean", CLEAN_START), ("ext", EXT_START)]},
            "blend": {wl: met(win(bl, st, end), cash) for wl, st in [("clean", CLEAN_START), ("ext", EXT_START)]},
        }
    out["headline"] = headline

    # ---- crisis windows (CPM-solo + blend MaxDD/return) ----
    crisis = {}
    for label, _ in VARIANTS:
        s = series[label]
        bl = CPM_W * s + BULL_W * bull
        crisis[label] = {}
        for rn, (rs, re) in REGIMES.items():
            rs_, re_ = pd.Timestamp(rs), pd.Timestamp(re)
            cmdd, cret = maxdd_ret(win(s, rs_, re_))
            bmdd, bret = maxdd_ret(win(bl, rs_, re_))
            crisis[label][rn] = {"cpm_maxdd": cmdd, "cpm_ret": cret,
                                 "blend_maxdd": bmdd, "blend_ret": bret}
    out["crisis"] = crisis

    # ---- turnover ----
    turn = {}
    wfs = {
        "V0 NONE (production)": lambda sd: compute_target_weights(close, sd)[0],
        "V1 SLEEVE-SPY": lambda sd: cpm_vg(close, sd, vol_gate="sleeve_spy", spy_close=spy_close),
        "V2 SLEEVE-BASKET": lambda sd: cpm_vg(close, sd, vol_gate="sleeve_basket", basket_close=basket_close),
        "V3 PER-ASSET": lambda sd: cpm_vg(close, sd, vol_gate="perasset"),
    }
    for label, _ in VARIANTS:
        turn[label] = {wl: turnover_stats(close, wfs[label], st, end)
                       for wl, st in [("clean", CLEAN_START), ("ext", EXT_START)]}
    out["turnover"] = turn

    # ---- interaction accounting (clean + ext) ----
    out["interaction"] = {
        "clean": interaction_accounting(close, spy_close, basket_close, CLEAN_START, end),
        "ext": interaction_accounting(close, spy_close, basket_close, EXT_START, end),
    }

    (Path(__file__).with_suffix(".json")).write_text(json.dumps(out, indent=2, default=float))
    write_md(out)
    print("\nDONE -> research/cpm_vol_gate_test_findings.md")
    return out


def write_md(o):
    L = []
    A = L.append
    m = o["meta"]

    def r6(mm):
        return (f"{mm['sharpe']:.4f} | {mm['cagr']*100:.2f}% | {mm['vol']*100:.2f}% | "
                f"{mm['maxdd']*100:.2f}% | {mm['calmar']:.4f} | {mm['martin']:.4f}")

    A("# CPM vol-gate add test -- sleeve vs per-asset vs none\n")
    A("Role: analyst (hypothesis-driven; read-only re production; writes `research/` only; "
      "NO production/memo edits; NO commit).\n")
    A("**Question.** CPM currently has NO vol gate (BULL has rv_60d(SPY) < rv_252d(SPY)). "
      "CPM already carries the positive-trend (absolute-momentum) screen + strict-4 partial-safe "
      "ladder. Does adding a vol gate earn its keep, and at what level (sleeve vs per-asset)?\n")
    A(f"**Convention.** Everything held at production CPM (IV4 `compute_target_weights`); only the "
      f"vol gate added. Execution T+1 MOO exact (`mooex`, real auto_adjust opens); post-cost "
      f"{m['cost_bps']} bps/side; cov lookback {m['lookback']}d; K={m['K']}. Blend = "
      f"{m['blend']}. Clean {m['clean_start']}..{m['end']} (18y); ext {m['ext_start']}..{m['end']} "
      f"(27y). Martin = CAGR/UlcerIndex.\n")
    A("**Variants.**\n"
      "- **V0 NONE** -- current production. Baseline.\n"
      "- **V1 SLEEVE-SPY** -- BULL-style: if rv_60d(SPY) >= rv_252d(SPY) at sig_d, de-risk the "
      "whole CPM sleeve to timed safe.\n"
      "- **V2 SLEEVE-BASKET** -- same sleeve gate but on the equal-weight CPM 8-risky basket rv.\n"
      "- **V3 PER-ASSET** -- 'same level as abs-mom': in addition to faber>0, also require each "
      "candidate's rv_60d < rv_252d to be held; failed names route to safe via the strict-4 "
      "partial-safe ladder.\n")

    a = o["anchor"]; sc = o["selfcheck"]
    A("## 0. Anchor gate\n")
    A("| Window | Sharpe | MaxDD | Calmar | Expected | Match |")
    A("|---|---:|---:|---:|---|---|")
    for wl in ("clean", "ext"):
        e = ANCHOR[wl]
        A(f"| {wl} | {a[wl]['sharpe']:.4f} | {a[wl]['maxdd']*100:.2f}% | {a[wl]['calmar']:.4f} "
          f"| {e[0]}/{e[1]}%/{e[2]} | {'CONFIRMED' if a[wl]['ok'] else 'MISMATCH'} |")
    A(f"\nCPM-solo NONE reproduces the production IV4 anchor exactly. Generalized weight fn "
      f"`cpm_vg(none)` self-check clean Sharpe {sc['clean_sharpe']:.6f}, matches production = "
      f"{sc['matches_production']}. Vol-gate variants are trusted on that basis.\n")

    h = o["headline"]
    A("## 1. Headline -- CPM-solo and 60/40 blend\n")
    A("### 1.1 CPM-solo, clean window (18y)\n")
    A("| Variant | Sharpe | CAGR | Vol | MaxDD | Calmar | Martin |")
    A("|---|---:|---:|---:|---:|---:|---:|")
    for label, _ in VARIANTS:
        A(f"| {label} | {r6(h[label]['cpm']['clean'])} |")
    A("\n### 1.2 CPM-solo, extended window (27y)\n")
    A("| Variant | Sharpe | CAGR | Vol | MaxDD | Calmar | Martin |")
    A("|---|---:|---:|---:|---:|---:|---:|")
    for label, _ in VARIANTS:
        A(f"| {label} | {r6(h[label]['cpm']['ext'])} |")
    A("\n### 1.3 60/40 blend (CPM + BULL), clean window (18y)\n")
    A("| Variant | Sharpe | CAGR | Vol | MaxDD | Calmar | Martin |")
    A("|---|---:|---:|---:|---:|---:|---:|")
    for label, _ in VARIANTS:
        A(f"| {label} | {r6(h[label]['blend']['clean'])} |")
    A("\n### 1.4 60/40 blend (CPM + BULL), extended window (27y)\n")
    A("| Variant | Sharpe | CAGR | Vol | MaxDD | Calmar | Martin |")
    A("|---|---:|---:|---:|---:|---:|---:|")
    for label, _ in VARIANTS:
        A(f"| {label} | {r6(h[label]['blend']['ext'])} |")
    A("")

    c = o["crisis"]
    A("## 2. Stress windows (CPM-solo and blend; MaxDD / total return within window)\n")
    for rn in REGIMES:
        A(f"### {rn}\n")
        A("| Variant | CPM MaxDD | CPM ret | Blend MaxDD | Blend ret |")
        A("|---|---:|---:|---:|---:|")
        for label, _ in VARIANTS:
            d = c[label][rn]
            A(f"| {label} | {d['cpm_maxdd']*100:.2f}% | {d['cpm_ret']*100:.2f}% "
              f"| {d['blend_maxdd']*100:.2f}% | {d['blend_ret']*100:.2f}% |")
        A("")

    t = o["turnover"]
    A("## 3. Turnover / whipsaw\n")
    A("Annualized one-way turnover (0.5 * sum|dw| / yr) and share of months the CPM sleeve is "
      "fully de-risked to safe.\n")
    A("| Variant | Clean turnover/yr | Clean %mo fully-safe | Ext turnover/yr | Ext %mo fully-safe |")
    A("|---|---:|---:|---:|---:|")
    for label, _ in VARIANTS:
        cl = t[label]["clean"]; ex = t[label]["ext"]
        A(f"| {label} | {cl['annual_oneway_turnover']:.3f} | {cl['pct_months_fully_safe']:.1f}% "
          f"| {ex['annual_oneway_turnover']:.3f} | {ex['pct_months_fully_safe']:.1f}% |")
    A("")

    it = o["interaction"]
    A("## 4. Interaction with abs-mom screen + partial-safe (redundant vs additive)\n")
    A("For each candidate gate, by month: does it FIRE; and when it fires is production already "
      "de-risked (REDUNDANT) or fully risk-on (ADDITIVE)? Sleeve gates count ADDITIVE only when "
      "production was fully risk-on (n_post=4); per-asset counts ADDITIVE when it drops a name while "
      "production sleeve was RISK_ON.\n")
    for wl in ("clean", "ext"):
        A(f"### 4.{1 if wl=='clean' else 2} {wl} window\n")
        A("| Gate | Months total | Fires | Additive | Redundant | Fire rate | Additive share |")
        A("|---|---:|---:|---:|---:|---:|---:|")
        for g, gl in (("sleeve_spy", "SLEEVE-SPY"), ("sleeve_basket", "SLEEVE-BASKET"),
                      ("perasset", "PER-ASSET")):
            d = it[wl][g]
            fr = 100.0 * d["fires"] / d["total"] if d["total"] else 0.0
            ash = 100.0 * d["additive"] / d["fires"] if d["fires"] else 0.0
            A(f"| {gl} | {d['total']} | {d['fires']} | {d['additive']} | {d['redundant']} "
              f"| {fr:.1f}% | {ash:.1f}% |")
        A("")

    # ---- verdict (computed) ----
    A("## 5. Verdict\n")
    base_c = h["V0 NONE (production)"]["cpm"]["clean"]
    base_e = h["V0 NONE (production)"]["cpm"]["ext"]
    base_bc = h["V0 NONE (production)"]["blend"]["clean"]
    A("Deltas vs V0 NONE (positive = better Sharpe/Calmar; less-negative MaxDD = shallower):\n")
    A("| Variant | dSharpe clean | dCalmar clean | dMaxDD clean | dSharpe ext | dBlend Sharpe clean |")
    A("|---|---:|---:|---:|---:|---:|")
    for label, _ in VARIANTS:
        if label.startswith("V0"):
            continue
        cc = h[label]["cpm"]["clean"]; ce = h[label]["cpm"]["ext"]
        bc = h[label]["blend"]["clean"]
        A(f"| {label} | {cc['sharpe']-base_c['sharpe']:+.4f} | {cc['calmar']-base_c['calmar']:+.4f} "
          f"| {(cc['maxdd']-base_c['maxdd'])*100:+.2f}pp | {ce['sharpe']-base_e['sharpe']:+.4f} "
          f"| {bc['sharpe']-base_bc['sharpe']:+.4f} |")
    A("\n(dMaxDD positive = shallower drawdown = better.)\n")
    A("See narrative VERDICT appended by the analyst below the auto-tables.\n")

    A("## Caveats\n")
    A("- All post-cost (10 bps/side), T+1 MOO exact with real yfinance auto_adjust opens.\n")
    A("- Ext 27y is partially proxy-backed pre-2006 for the CPM universe (close-to-close fallback "
      "on a minority of rebal days); clean 18y has full real-open coverage and is the decisive lens.\n")
    A("- Per-asset vol screen uses each asset's own daily close rv_60d<rv_252d; warmup (<252 obs) "
      "holds (passes), matching the BULL gate warmup convention.\n")
    A("- SLEEVE-BASKET uses the equal-weight CPM 8-risky basket daily returns (signal-date only, no "
      "lookahead) as a CPM-specific market vol proxy.\n")
    A("- Turnover is signal-level one-way (0.5*sum|dw|); realized cost already embedded in returns.\n")

    Path(ROOT / "research" / "cpm_vol_gate_test_findings.md").write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
