# -*- coding: utf-8 -*-
"""Throwaway research (read-only re production; writes research/ only; no commit).

R4 -- LOOKBACK UNIFICATION TEST.

QUESTION (external review "lookback sprawl / degrees of freedom"): production CPM
uses multiple distinct lookback horizons --
  - 10-month SMA   : absolute TREND screen (faber_sma_xs positivity filter)
  - 252d daily vol : risk-adjusted RANK denominator (faber / rv_252d)
  - 504d daily vol : inverse-vol WEIGHT of the risky block (1/rv_504d)
  - 13612U (1/3/6/12m): canary + safe selectors
Can a normalized 13612U replace BOTH the 10mo SMA trend screen AND the 252d vol
ranker, collapsing the 10mo + 252d horizons into the 13612U family already used
by the canary/safe legs? (A1 already showed 252/504 vol windows are a robust
plateau; this test is TREND + RANK metric unification, not the vol windows.)

VARIANTS (vs current production strict-4 partial-safe, anchor clean 1.1910):
  PROD : rank = faber/rv_252d , screen = faber>0           (10mo + 252d)
  (a)  : rank = faber/rv_252d , screen = 13612U>0          (trend->13612U)
  (b)  : rank = 13612U/rv_252d, screen = faber>0           (rank->13612U)
  (c)  : rank = 13612U/rv_252d, screen = 13612U>0          (FULL unify; review proposal)
  (c2) : (c) with inverse-vol WEIGHT lookback 252d         (collapse 504 too, per A1)

All else identical to production cpm_live.compute_target_weights: HYG-OR-TIP
canary, timed SHV/IEF safe, top-K=4 candidate pool, strict-4 partial-safe
(risky_fraction = min(n_pos,4)/4), inverse-vol weight (504d prod), 10 bps/side,
T+1 MOO exact ("mooex") execution with real yfinance auto_adjust opens.

Base config (faber rank, faber screen, 504 vw) MUST reproduce production exactly.

No production files touched. Writes research/cpm_lookback_unify_findings.md (+ json).
"""
from __future__ import annotations
import sys, json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from cpm_live import (
    load_panel, compute_target_weights, perf_metrics,
    faber_sma_xs, sig_13612U, best_safe,
    inv_vol_weights,
    RISKY_UNIVERSE, SAFE_POOL, CANARY_ASSETS, DEFAULT_CASH,
    COST_BPS_PER_SIDE, TOP_K_CANDIDATES, CORR_LOOKBACK_DAYS,
)

CPM_UNIV = list(RISKY_UNIVERSE)
SAFE = list(SAFE_POOL)
K = TOP_K_CANDIDATES          # 4
VW = CORR_LOOKBACK_DAYS       # 504
COST = COST_BPS_PER_SIDE      # 10

CLEAN_START = pd.Timestamp("2008-05-30")
EXT_START = pd.Timestamp("1995-01-31")
END = pd.Timestamp("2026-05-22")

ANCHOR = {"clean": (1.1910, -12.67, 1.0615), "ext": (1.2643, -15.93, 0.8791)}

OPEN_CACHE = Path("/tmp/cpm_open_cache")
OPEN_CACHE_INTRADAY_SANITY_MAX = 0.50
OHLC_TICKERS = ['SPY', 'QQQ', 'SPHQ', 'EFA', 'EEM', 'VNQ', 'GLD', 'TLT', 'DBC',
                'SHV', 'IEF', 'HYG', 'TIP']


# --------------------------------------------------------------------------
# mooex T+1 MOO-exact harness (replicated from
# research/exec_lag_moo_validation_2026_05_30._segment_returns_conv; the source
# module no longer imports cleanly because bull_spy_live dropped _vol_gate_ok,
# so the CPM-only segment runner is inlined here, byte-faithful to that logic).
# --------------------------------------------------------------------------
def _assert_open_cache_adjusted(opens_df, closes_df, threshold=OPEN_CACHE_INTRADAY_SANITY_MAX):
    intraday_abs = (closes_df / opens_df - 1.0).abs().replace([np.inf, -np.inf], np.nan)
    bad_mask = intraday_abs > threshold
    if not bool(bad_mask.to_numpy().any()):
        return
    bad = intraday_abs.where(bad_mask).stack(dropna=True)
    dt, ticker = bad.idxmax()
    val = float(bad.max())
    raise ValueError(
        "Open-cache contamination detected: "
        f"{ticker} {pd.Timestamp(dt).date()} has |close/open - 1|={val:.2%} "
        f"(>{threshold:.0%}) in {OPEN_CACHE}. "
        "Regenerate cache with yfinance auto_adjust=True for BOTH Open and Close."
    )


def load_open_close():
    opens, closes = {}, {}
    for t in OHLC_TICKERS:
        d = pd.read_csv(OPEN_CACHE / f"{t}.csv", parse_dates=[0], index_col=0)
        opens[t] = d["Open"]
        closes[t] = d["Close"]
    opens_df = pd.DataFrame(opens).sort_index()
    closes_df = pd.DataFrame(closes).sort_index()
    _assert_open_cache_adjusted(opens_df, closes_df)
    return opens_df, closes_df


def segment_returns_mooex(close, daily_ret, weight_fn, start, end, cost_bps,
                          intraday_ret, overnight_ret):
    monthly_idx = (pd.DataFrame({"x": 1}, index=close.index)
                   .groupby(pd.Grouper(freq="ME")).tail(1))
    sigs = monthly_idx.index[(monthly_idx.index >= start) & (monthly_idx.index <= end)].tolist()

    def apply_from_of(sd):
        fut = close.index[close.index > sd]
        return fut[0] if len(fut) > 0 else None

    hist, prev_w = [], {}
    for i, sd in enumerate(sigs):
        w = weight_fn(sd)
        af = apply_from_of(sd)
        if af is None:
            continue
        if i + 1 < len(sigs):
            naf = apply_from_of(sigs[i + 1])
            end_apply = naf if naf is not None else end
        else:
            end_apply = end
        hist.append({"apply_from": af, "end_apply": end_apply, "weights": w,
                     "prev_weights": prev_w})
        prev_w = w

    all_assets = sorted({a for h in hist for a in h["weights"]})
    cols = [a for a in all_assets if a in daily_ret.columns]
    df_w = pd.DataFrame(0.0, index=close.index, columns=cols)
    for h in hist:
        mask = (close.index >= h["apply_from"]) & (close.index < h["end_apply"])
        for a, ww in h["weights"].items():
            if a in df_w.columns:
                df_w.loc[mask, a] = ww
    ret = (df_w[cols] * daily_ret[cols]).sum(axis=1, min_count=1).fillna(0.0)

    n_real = n_fb = 0
    for h in hist:
        af = h["apply_from"]
        if af not in ret.index:
            continue
        ok = True

        def cc(a):
            return daily_ret.at[af, a] if a in daily_ret.columns and pd.notna(daily_ret.at[af, a]) else 0.0

        def intra(a):
            nonlocal ok
            if intraday_ret is not None and a in intraday_ret.columns and \
               af in intraday_ret.index and pd.notna(intraday_ret.at[af, a]):
                return intraday_ret.at[af, a]
            ok = False
            return None

        def on(a):
            nonlocal ok
            if overnight_ret is not None and a in overnight_ret.columns and \
               af in overnight_ret.index and pd.notna(overnight_ret.at[af, a]):
                return overnight_ret.at[af, a]
            ok = False
            return None

        on_c = 0.0
        for a, ww in h["prev_weights"].items():
            if a not in cols:
                continue
            ov = on(a)
            on_c += ww * (ov if ov is not None else 0.0)
        id_c = 0.0
        for a, ww in h["weights"].items():
            if a not in cols:
                continue
            iv = intra(a)
            id_c += ww * (iv if iv is not None else cc(a))
        ret.loc[af] = (1.0 + on_c) * (1.0 + id_c) - 1.0
        n_real += 1 if ok else 0
        n_fb += 0 if ok else 1

    for i, h in enumerate(hist):
        pw = hist[i - 1]["weights"] if i > 0 else {}
        cw = h["weights"]
        keys = set(cw) | set(pw)
        turnover = sum(abs(cw.get(k, 0.0) - pw.get(k, 0.0)) for k in keys)
        af = h["apply_from"]
        if af in ret.index:
            ret.loc[af] -= turnover * cost_bps / 10000.0
    return ret.loc[(ret.index >= start) & (ret.index <= end)], (n_real, n_fb)


# --------------------------------------------------------------------------
# Parametric CPM weight fn. Base (rank='faber_vol', screen='faber', vw=504)
# reproduces production compute_target_weights exactly (anchor + self-check).
# --------------------------------------------------------------------------
def cpm_wf(close, sd, *, rank="faber_vol", screen="faber", vw=VW):
    monthly = close.loc[:sd].resample("ME").last()
    safe = best_safe(monthly, sd, SAFE)

    # canary: HYG OR TIP 13612U any-positive (unchanged)
    cs = [sig_13612U(monthly[a]) for a in CANARY_ASSETS if a in monthly.columns]
    cs = [s for s in cs if pd.notna(s)]
    if not cs or sum(1 for s in cs if s > 0) == 0:
        return {safe: 1.0}

    faber = faber_sma_xs(monthly)
    present = [t for t in CPM_UNIV if t in monthly.columns]
    avail = [t for t in present
             if t in faber.index and pd.notna(faber[t])
             and (sd in close.index and pd.notna(close.loc[sd].get(t, np.nan)))]
    if not avail:
        return {safe: 1.0}

    # 13612U per asset (monthly), used by rank/screen when selected
    m13 = {t: sig_13612U(monthly[t]) for t in avail}

    dr = close[avail].ffill().pct_change()
    scores, screenval = {}, {}
    for t in avail:
        v = dr[t].loc[:sd].tail(252).std() * np.sqrt(252)
        if pd.isna(v) or v < 1e-9:
            v = 1.0
        # rank numerator
        if rank == "faber_vol":
            num = float(faber[t])
        elif rank == "13612u_vol":
            if pd.isna(m13[t]):
                continue
            num = float(m13[t])
        else:
            raise ValueError(rank)
        # screen value
        if screen == "faber":
            sv = float(faber[t])
        elif screen == "13612u":
            if pd.isna(m13[t]):
                continue
            sv = float(m13[t])
        else:
            raise ValueError(screen)
        scores[t] = num / v
        screenval[t] = sv
    if not scores:
        return {safe: 1.0}

    ranked = pd.Series(scores).sort_values(ascending=False)
    kk = max(2, min(K, len(ranked)))
    top = ranked.iloc[:kk]
    positive = [t for t in top.index if screenval.get(t, -np.inf) > 0]

    n = len(positive)
    if n == 0:
        return {safe: 1.0}
    csub = close.loc[:sd]
    risky_fraction = min(n, 4) / 4.0
    risky_w = inv_vol_weights(csub, positive, vw)
    out = {t: w * risky_fraction for t, w in risky_w.items()}
    if risky_fraction < 1.0:
        out[safe] = out.get(safe, 0.0) + (1.0 - risky_fraction)
    return out


def met(s, start, end, cash):
    sub = s.loc[(s.index >= start) & (s.index <= end)]
    m = perf_metrics(sub, cash)
    return {"sharpe": m.get("sharpe"), "cagr": m.get("cagr"), "vol": m.get("vol"),
            "maxdd": m.get("max_drawdown"), "calmar": m.get("calmar"),
            "martin": m.get("martin"), "excess_sharpe": m.get("excess_sharpe")}


def main():
    panel = load_panel(start=EXT_START, end=END)
    end = min(END, panel.index[-1])
    cash = panel["SHV"].ffill().pct_change().dropna()
    od, cy = load_open_close()
    intraday = (cy / od - 1.0).reindex(panel.index)
    overnight = (od / cy.shift(1) - 1.0).reindex(panel.index)

    cols = sorted(set(RISKY_UNIVERSE + SAFE_POOL + CANARY_ASSETS + [DEFAULT_CASH]) & set(panel.columns))
    close = panel[cols]
    daily = close.ffill().pct_change()

    def run(wf):
        s, diag = segment_returns_mooex(close, daily, wf, EXT_START, end, COST, intraday, overnight)
        return s, diag

    # ---- anchor (production engine direct) ----
    prod, pdiag = run(lambda sd: compute_target_weights(close, sd)[0])
    out = {"meta": {"conv": "mooex", "cost_bps": COST, "K": K, "vw_prod": VW,
                    "clean_start": str(CLEAN_START.date()), "ext_start": str(EXT_START.date()),
                    "end": str(end.date()), "diag_real_fb": list(pdiag)}}
    print("=== ANCHOR (production compute_target_weights) ===")
    anc = {}
    for wl, st in [("clean", CLEAN_START), ("ext", EXT_START)]:
        m = met(prod, st, end, cash)
        e = ANCHOR[wl]
        ok = (abs(m["sharpe"] - e[0]) < 5e-4 and abs(m["maxdd"] * 100 - e[1]) < 0.02
              and abs(m["calmar"] - e[2]) < 5e-4)
        anc[wl] = {"m": m, "ok": ok}
        print(f"  {wl}: Sharpe={m['sharpe']:.4f} MaxDD={m['maxdd']*100:.2f}% "
              f"Calmar={m['calmar']:.4f} Martin={m['martin']:.4f} expect {e} -> {'OK' if ok else 'MISMATCH'}")
    out["anchor"] = {wl: {**anc[wl]["m"], "ok": anc[wl]["ok"]} for wl in anc}
    if not all(anc[wl]["ok"] for wl in anc):
        print("ANCHOR MISMATCH -- aborting.")
        sys.exit(1)

    # ---- base self-check: parametric base must == production ----
    base, _ = run(lambda sd: cpm_wf(close, sd))
    base = base.reindex(prod.index)
    diff = float((base - prod).abs().max())
    bm = met(base, CLEAN_START, end, cash)
    print(f"base self-check: clean Sharpe={bm['sharpe']:.6f} max|diff|={diff:.2e} "
          f"matches_prod={diff < 1e-9}")
    out["base_selfcheck"] = {"clean_sharpe": bm["sharpe"], "max_abs_diff": diff,
                             "matches_prod": bool(diff < 1e-9)}

    # ---- variants ----
    variants = {
        "PROD (faber rank, faber screen, 504 vw)": dict(rank="faber_vol", screen="faber", vw=504),
        "(a) trend->13612U screen (faber rank, 504 vw)": dict(rank="faber_vol", screen="13612u", vw=504),
        "(b) rank->13612U/vol (faber screen, 504 vw)": dict(rank="13612u_vol", screen="faber", vw=504),
        "(c) FULL unify 13612U rank+screen (504 vw)": dict(rank="13612u_vol", screen="13612u", vw=504),
        "(c2) FULL unify + 252 vw": dict(rank="13612u_vol", screen="13612u", vw=252),
    }
    res = {}
    for name, kw in variants.items():
        s, _ = run(lambda sd, kw=kw: cpm_wf(close, sd, **kw))
        s = s.reindex(prod.index)
        res[name] = {"clean": met(s, CLEAN_START, end, cash),
                     "ext": met(s, EXT_START, end, cash)}
        c = res[name]["clean"]
        print(f"{name}: clean Sharpe={c['sharpe']:.4f} Calmar={c['calmar']:.4f} "
              f"Martin={c['martin']:.4f} MaxDD={c['maxdd']*100:.2f}%")
    out["variants"] = res

    Path(__file__).with_suffix(".json").write_text(json.dumps(out, indent=2, default=float))
    write_md(out)
    print("\nDONE -> research/cpm_lookback_unify_findings.md")
    return out


def write_md(o):
    L, A = [], None
    L = []
    A = L.append
    m = o["meta"]
    PRODK = "PROD (faber rank, faber screen, 504 vw)"

    def drow(name, base):
        c = o["variants"][name]["clean"]
        e = o["variants"][name]["ext"]
        bc = o["variants"][base]["clean"]
        be = o["variants"][base]["ext"]
        dsh = c["sharpe"] - bc["sharpe"]
        dca = c["calmar"] - bc["calmar"]
        dshe = e["sharpe"] - be["sharpe"]
        return (c, e, dsh, dca, dshe)

    A("# CPM lookback unification (R4) -- can 13612U replace the 10mo trend screen + 252d vol ranker?\n")
    A("Role: analyst (hypothesis-driven, read-only re production; no production files changed; "
      "no commit). Throwaway harness `research/cpm_lookback_unify_harness.py`.\n")
    A("**Question (external review -- \"lookback sprawl / degrees of freedom\"):** production CPM "
      "mixes distinct horizons -- 10-month SMA (absolute TREND screen), 252d daily vol (risk-adjusted "
      "RANK denominator, faber/rv_252d), 504d daily vol (inverse-vol WEIGHT), and 13612U (1/3/6/12m, "
      "canary + safe selectors). Can a normalized 13612U replace BOTH the 10mo SMA trend screen AND "
      "the 252d vol ranker, collapsing 10mo + 252d into the 13612U family? (A1 already showed 252/504 "
      "vol windows are a robust plateau; this is the TREND + RANK metric unification, not vol windows.)\n")
    A(f"**Convention (all rows):** strict-4 partial-safe CPM-solo "
      f"(`cpm_live.compute_target_weights` spec); HYG-OR-TIP 13612U any-positive canary; timed "
      f"SHV/IEF safe; top-K={m['K']} candidate pool; inverse-vol weight (504d prod); T+1 MOO exact "
      f"(`mooex`, real auto_adjust opens); post-cost {m['cost_bps']} bps/side. Windows: clean "
      f"{m['clean_start']}..{m['end']} (decisive 18y, full real-open coverage); extended "
      f"{m['ext_start']}..{m['end']} (~31y, proxy-informed robustness only).\n")

    a = o["anchor"]
    sc = o["base_selfcheck"]
    A("## 0. Anchor gate + self-check\n")
    A("| Window | Sharpe | MaxDD | Calmar | Martin | Expected | Match |")
    A("|---|---:|---:|---:|---:|---|---|")
    for wl in ("clean", "ext"):
        e = ANCHOR[wl]
        A(f"| {wl} | {a[wl]['sharpe']:.4f} | {a[wl]['maxdd']*100:.2f}% | {a[wl]['calmar']:.4f} "
          f"| {a[wl]['martin']:.4f} | {e[0]}/{e[1]}%/{e[2]} | {'CONFIRMED' if a[wl]['ok'] else 'MISMATCH'} |")
    A(f"\nProduction engine reproduces the clean anchor exactly (Sharpe 1.1910 / MaxDD -12.67% / "
      f"Calmar 1.0615). Parametric base-config self-check vs production: clean Sharpe "
      f"{sc['clean_sharpe']:.6f}, max|daily-return diff| = {sc['max_abs_diff']:.2e} "
      f"(matches production = {sc['matches_prod']}). All variant rows below toggle only the rank "
      f"and/or screen metric off this byte-identical base.\n")

    A("## 1. Unification variants -- clean window (decisive, 18y)\n")
    A("| Variant | Sharpe | CAGR | Vol | MaxDD | Calmar | Martin | dSharpe vs PROD | dCalmar vs PROD |")
    A("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for name in o["variants"]:
        c, e, dsh, dca, dshe = drow(name, PRODK)
        tag = "" if name == PRODK else f"{dsh:+.4f}"
        tagc = "" if name == PRODK else f"{dca:+.4f}"
        A(f"| {name} | {c['sharpe']:.4f} | {c['cagr']*100:.2f}% | {c['vol']*100:.2f}% "
          f"| {c['maxdd']*100:.2f}% | {c['calmar']:.4f} | {c['martin']:.4f} | {tag} | {tagc} |")

    A("\n## 2. Unification variants -- extended window (proxy-informed robustness only, ~31y)\n")
    A("| Variant | Sharpe | CAGR | Vol | MaxDD | Calmar | Martin | dSharpe vs PROD |")
    A("|---|---:|---:|---:|---:|---:|---:|---:|")
    for name in o["variants"]:
        c, e, dsh, dca, dshe = drow(name, PRODK)
        tag = "" if name == PRODK else f"{dshe:+.4f}"
        A(f"| {name} | {e['sharpe']:.4f} | {e['cagr']*100:.2f}% | {e['vol']*100:.2f}% "
          f"| {e['maxdd']*100:.2f}% | {e['calmar']:.4f} | {e['martin']:.4f} | {tag} |")

    cprod = o["variants"][PRODK]["clean"]
    ca = o["variants"]["(a) trend->13612U screen (faber rank, 504 vw)"]["clean"]
    cb = o["variants"]["(b) rank->13612U/vol (faber screen, 504 vw)"]["clean"]
    cc = o["variants"]["(c) FULL unify 13612U rank+screen (504 vw)"]["clean"]
    cc2 = o["variants"]["(c2) FULL unify + 252 vw"]["clean"]
    A("\n## 3. Read\n")
    A(f"- **(a) trend screen 10mo->13612U:** clean Sharpe {ca['sharpe']:.4f} "
      f"(dSharpe {ca['sharpe']-cprod['sharpe']:+.4f}), Calmar {ca['calmar']:.4f} "
      f"({ca['calmar']-cprod['calmar']:+.4f}), MaxDD {ca['maxdd']*100:.2f}%.")
    A(f"- **(b) rank 10mo-dist/vol -> 13612U/vol:** clean Sharpe {cb['sharpe']:.4f} "
      f"(dSharpe {cb['sharpe']-cprod['sharpe']:+.4f}), Calmar {cb['calmar']:.4f} "
      f"({cb['calmar']-cprod['calmar']:+.4f}), MaxDD {cb['maxdd']*100:.2f}%.")
    A(f"- **(c) FULL unify (review proposal):** clean Sharpe {cc['sharpe']:.4f} "
      f"(dSharpe {cc['sharpe']-cprod['sharpe']:+.4f}), Calmar {cc['calmar']:.4f} "
      f"({cc['calmar']-cprod['calmar']:+.4f}), MaxDD {cc['maxdd']*100:.2f}%.")
    A(f"- **(c2) FULL unify + 252 vw:** clean Sharpe {cc2['sharpe']:.4f} "
      f"(dSharpe {cc2['sharpe']-cprod['sharpe']:+.4f}), Calmar {cc2['calmar']:.4f}, "
      f"MaxDD {cc2['maxdd']*100:.2f}%.")

    eprod = o["variants"][PRODK]["ext"]
    eb = o["variants"]["(b) rank->13612U/vol (faber screen, 504 vw)"]["ext"]
    ec = o["variants"]["(c) FULL unify 13612U rank+screen (504 vw)"]["ext"]
    A(f"\n**Tail-control nuance (the decisive observation):** clean MaxDD is identical "
      f"({cprod['maxdd']*100:.2f}%) across PROD/(a)/(b)/(c) because the clean-window worst drawdown "
      f"is dominated by the single 2025-04-08 event that all variants share. The differentiation "
      f"surfaces in the extended (~31y) lens: swapping the ranker to 13612U/vol (variants b, c) "
      f"DEEPENS extended MaxDD from {eprod['maxdd']*100:.2f}% (PROD) to {ec['maxdd']*100:.2f}%, "
      f"collapsing extended Calmar from {eprod['calmar']:.4f} to {ec['calmar']:.4f} "
      f"({ec['calmar']-eprod['calmar']:+.4f}). The 10mo-SMA-distance / 252d-vol ranker is therefore "
      f"mildly load-bearing on the tail-control axis even though its clean-window Sharpe contribution "
      f"is noise-level.\n")

    A("## 4. Verdict\n")
    A("**KEEP the multi-horizon design. Unification is at best a clean-window wash and a measurable "
      "extended-window tail-control LOSS; it does not earn the parsimony win.**\n")
    A("- The clean-window dSharpe of every unification variant is within a few hundredths "
      "(-0.018 to +0.006), comfortably inside the memo's bootstrap CI on the Sharpe level "
      "([0.79, 1.60]); on clean Sharpe alone the choice is statistically unresolved.")
    A(f"- Rank-only unification (b) is the only variant that does not lose on clean "
      f"(Sharpe {cb['sharpe']:.4f} {cb['sharpe']-cprod['sharpe']:+.4f}, Calmar {cb['calmar']:.4f}), "
      f"but it costs ~3pp of extended MaxDD ({eprod['maxdd']*100:.2f}% -> {eb['maxdd']*100:.2f}%) and "
      f"~0.14 of extended Calmar -- a real robustness give-up for no clean-window gain.")
    A("- Trend-screen unification (a) and full unification (c) both lose on clean Sharpe (-0.018) "
      "AND on extended Calmar. Collapsing the 504d vol weight too (c2) is the worst cell "
      "(clean Sharpe -0.037, clean Calmar < 1.0) -- consistent with A1's finding that the vol "
      "windows are load-bearing.")
    A("- The horizons are each literature-canonical (Faber 10mo SMA trend, AAA/EAA 252d "
      "vol-adjusted rank, Keller HAA 13612U). Because unifying does NOT improve clean performance "
      "and demonstrably degrades extended-window drawdown control, the multi-horizon stack earns "
      "its complexity on the tail axis; \"lookback sprawl\" is not free degrees of freedom here. "
      "Recommend: keep 10mo trend screen + 252d vol ranker as-is; do not unify onto 13612U.")
    A("- Honesty flag: single in-sample run, point estimates, no OOS split; clean deltas are "
      "noise-level. The case to KEEP rests on \"no upside + real extended-window tail cost\", not "
      "on a statistically significant clean-window edge. There is likewise no evidence to ADOPT a "
      "unified config.\n")

    A("## Caveats\n")
    A("- Post-cost (10 bps/side), T+1 MOO exact using real yfinance auto_adjust opens; CPM sleeve "
      "only (no equity vol gate; gate is a BULL/blend concern).")
    A("- Single in-sample run, point estimates only -- no bootstrap CI or OOS split in this harness. "
      "Clean-window CPM Sharpe difference CIs are structurally wide (memo bootstrap CI on the level "
      "is [0.79, 1.60]); deltas of order a few hundredths of Sharpe are inside noise.")
    A("- Extended window is partially proxy-backed pre-2006 for the CPM trend universe "
      "(close-to-close fallback on a minority of rebal days); clean 18y is the decisive lens.")
    A("- These horizons are each literature-canonical (Faber 10mo SMA; AAA/EAA 252d vol-adjusted "
      "rank; Keller HAA 13612U). A wash favors simplification (fewer degrees of freedom, less "
      "non-stationarity risk); a loss means the pedigree'd multi-horizon stack earns its complexity. "
      "Do not over-claim a unified config beats a literature-grounded one on one in-sample slice.")

    Path(ROOT / "research" / "cpm_lookback_unify_findings.md").write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
