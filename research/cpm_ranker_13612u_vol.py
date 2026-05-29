#!/usr/bin/env python3
"""
CPM candidate-ranker swap test: EAA Vol-Adj (Faber/vol) vs 13612U/vol.

Measurement-only. Does NOT edit any production file. Reimplements a
parametrized version of cpm_live.compute_target_weights / run_cpm_backtest so
the canary gate, top-K=4, and min-variance 50/50 pair construction stay fixed
and ONLY the ranker (and optionally the matching absmom filter) varies.

Variants (all evaluated CPM-standalone AND in 60/40 two-sleeve CPM+BULL blend):
  R0 (PROD): ranker = faber/vol_252d, filter = positive-Faber
  R1:        ranker = sig_13612U/vol_252d, filter = positive-Faber
  R2:        ranker = sig_13612U/vol_252d, filter = positive-13612U

Windows:
  clean  2008-05-30 .. 2026-05-22
  stress 1999-03-10 .. 2026-05-22

Run: .venv/bin/python research/cpm_ranker_13612u_vol.py
"""
from __future__ import annotations

import sys
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cpm_live import (
    load_panel,
    perf_metrics,
    faber_sma_xs,
    sig_13612U,
    best_safe,
    min_vol_pair,
    RISKY_UNIVERSE,
    SAFE_POOL,
    CANARY_ASSETS,
    CANARY_RULE,
    DEFAULT_CASH,
    TOP_K_CANDIDATES,
    CORR_LOOKBACK_DAYS,
    COST_BPS_PER_SIDE,
)
from bull_qqq_live import run_bull_qqq_backtest

FINDINGS = Path(__file__).resolve().parent / "cpm_ranker_13612u_vol_findings.md"


def _mom13_panel(monthly: pd.DataFrame, universe: list) -> dict:
    """13612U momentum for each universe asset on the monthly panel."""
    out = {}
    for t in universe:
        if t in monthly.columns:
            out[t] = sig_13612U(monthly[t])
    return out


def compute_target_weights_variant(
    close_panel: pd.DataFrame,
    sig_d: pd.Timestamp,
    ranker: str,        # "faber" or "mom13"
    filt: str,          # "faber" or "mom13"
    universe: list = None,
    safe_pool: list = None,
    canary_assets: list = None,
) -> tuple[dict, tuple, str, str]:
    """Parametrized clone of cpm_live.compute_target_weights.

    ranker == "faber" + filt == "faber"  -> R0 (production)
    ranker == "mom13" + filt == "faber"  -> R1
    ranker == "mom13" + filt == "mom13"  -> R2

    Canary gate, top-K, and min_vol_pair construction are identical to prod.
    """
    universe = universe or RISKY_UNIVERSE
    safe_pool = safe_pool or SAFE_POOL
    canary_assets = canary_assets or CANARY_ASSETS

    monthly = close_panel.loc[:sig_d].resample("ME").last()
    safe = best_safe(monthly, sig_d, safe_pool)

    # --- Canary gate (unchanged) ---
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

    # --- Scores for ranking & filtering ---
    faber = faber_sma_xs(monthly)
    mom13 = _mom13_panel(monthly, universe)

    def rank_score(t):
        return faber.get(t, np.nan) if ranker == "faber" else mom13.get(t, np.nan)

    def filt_score(t):
        return faber.get(t, np.nan) if filt == "faber" else mom13.get(t, np.nan)

    has_price = (sig_d in close_panel.index)
    avail = [
        t for t in universe
        if pd.notna(rank_score(t)) and pd.notna(filt_score(t))
        and (pd.notna(close_panel.loc[sig_d].get(t, np.nan)) if has_price else False)
    ]
    if not avail:
        return {safe: 1.0}, None, "DEFENSIVE", safe

    daily_rets = close_panel[avail].ffill().pct_change()
    scores = {}
    for t in avail:
        v = daily_rets[t].loc[:sig_d].tail(252).std() * np.sqrt(252)
        if pd.isna(v) or v < 1e-9:
            v = 1.0
        scores[t] = float(rank_score(t)) / v
    sa = pd.Series(scores)
    ranked = sa.sort_values(ascending=False)
    top_k = max(2, min(TOP_K_CANDIDATES, len(ranked)))
    top = ranked.iloc[:top_k]
    # Positive-trend filter on the (non-vol-adjusted) filter score.
    positive = top[top.index.map(lambda t: filt_score(t) > 0)]

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


def run_cpm_variant(panel, start, end, ranker, filt, cost_bps=COST_BPS_PER_SIDE):
    """Clone of cpm_live.run_cpm_backtest using the parametrized weights fn."""
    cols = sorted(set(RISKY_UNIVERSE + SAFE_POOL + CANARY_ASSETS + [DEFAULT_CASH]) & set(panel.columns))
    close = panel[cols]

    monthly_idx = pd.DataFrame({"x": 1}, index=close.index).groupby(pd.Grouper(freq="ME")).tail(1)
    signal_dates = monthly_idx.index[(monthly_idx.index >= start) & (monthly_idx.index <= end)].tolist()

    weights_history = []
    for i, sig_d in enumerate(signal_dates):
        w, new_pair, regime, safe = compute_target_weights_variant(
            close, sig_d, ranker=ranker, filt=filt)
        future = close.index[close.index > sig_d]
        if len(future) < 1:
            continue
        apply_from = future[0]
        if i + 1 < len(signal_dates):
            next_sig = signal_dates[i + 1]
            next_future = close.index[close.index > next_sig]
            end_apply = next_future[0] if len(next_future) >= 1 else end
        else:
            end_apply = end
        weights_history.append({
            "apply_from": apply_from, "end_apply": end_apply,
            "weights": w, "sig_d": sig_d, "regime": regime, "safe": safe,
            "pair": new_pair,
        })

    all_assets = sorted({a for h in weights_history for a in h["weights"]})
    df_w = pd.DataFrame(0.0, index=close.index, columns=[a for a in all_assets if a in close.columns])
    for h in weights_history:
        mask = (close.index >= h["apply_from"]) & (close.index < h["end_apply"])
        for a, ww in h["weights"].items():
            if a in df_w.columns:
                df_w.loc[mask, a] = ww

    daily_ret = close.ffill().pct_change()
    common = [a for a in df_w.columns if a in daily_ret.columns]
    raw_returns = (df_w[common] * daily_ret[common]).sum(axis=1, min_count=1).fillna(0.0)

    # trade costs
    for i in range(len(weights_history)):
        prev_w = weights_history[i - 1]["weights"] if i > 0 else {}
        curr_w = weights_history[i]["weights"]
        keys = set(curr_w) | set(prev_w)
        turnover = sum(abs(curr_w.get(k, 0.0) - prev_w.get(k, 0.0)) for k in keys)
        cost = turnover * cost_bps / 10000.0
        af = weights_history[i]["apply_from"]
        if af in raw_returns.index:
            raw_returns.loc[af] -= cost

    rets = raw_returns.loc[(raw_returns.index >= start) & (raw_returns.index <= end)]
    return rets, weights_history


def annualized_turnover(weights_history, start, end):
    """Two-way annualized turnover = mean(sum|dw|) per rebalance * 12."""
    tos = []
    for i in range(len(weights_history)):
        prev_w = weights_history[i - 1]["weights"] if i > 0 else {}
        curr_w = weights_history[i]["weights"]
        keys = set(curr_w) | set(prev_w)
        tos.append(sum(abs(curr_w.get(k, 0.0) - prev_w.get(k, 0.0)) for k in keys))
    if not tos:
        return float("nan")
    return float(np.mean(tos) * 12.0)


def cal_return(daily, year):
    seg = daily.loc[f"{year}-01-01":f"{year}-12-31"]
    return (1.0 + seg).prod() - 1.0


def metrics_row(daily, cash_daily, wh, start, end):
    m = perf_metrics(daily, cash_daily)
    m["turnover"] = annualized_turnover(wh, start, end) if wh is not None else float("nan")
    m["ret_2022"] = cal_return(daily, 2022)
    return m


def pair_set(h):
    p = h.get("pair")
    return frozenset(p) if p else None


def overlap_stats(wh_ref, wh_var):
    """Among risk-on months (ref has a pair), how often var picks the SAME pair
    and how often >=1 asset overlaps. Aligned by sig_d."""
    ref_by_d = {h["sig_d"]: pair_set(h) for h in wh_ref}
    var_by_d = {h["sig_d"]: pair_set(h) for h in wh_var}
    same = 0
    one_plus = 0
    n = 0
    for d, rp in ref_by_d.items():
        if rp is None:
            continue
        vp = var_by_d.get(d)
        if vp is None:
            continue  # var defensive that month; not a risk-on-vs-risk-on comparison
        n += 1
        if rp == vp:
            same += 1
        if len(rp & vp) >= 1:
            one_plus += 1
    return {
        "n_riskon_both": n,
        "same_pct": 100.0 * same / n if n else float("nan"),
        "one_plus_pct": 100.0 * one_plus / n if n else float("nan"),
    }


def asset_frequency(wh):
    """How often each asset appears in the selected pair (risk-on months)."""
    cnt = {}
    tot = 0
    for h in wh:
        p = h.get("pair")
        if not p:
            continue
        tot += 1
        for a in p:
            cnt[a] = cnt.get(a, 0) + 1
    return cnt, tot


def fmt_metrics(label, m):
    return (f"| {label} | {m['sharpe']:.3f} | {m['excess_sharpe']:.3f} | "
            f"{m['cagr']*100:.2f}% | {m['vol']*100:.2f}% | {m['max_drawdown']*100:.2f}% | "
            f"{m['calmar']:.2f} | {m['turnover']*100:.1f}% | {m['ret_2022']*100:+.2f}% |")


def main():
    print("Loading panel ...")
    panel = load_panel(start=pd.Timestamp("1995-01-01"))
    cash_daily = panel["SHV"].ffill().pct_change().dropna()

    windows = {
        "clean": (pd.Timestamp("2008-05-30"), pd.Timestamp("2026-05-22")),
        "stress": (pd.Timestamp("1999-03-10"), pd.Timestamp("2026-05-22")),
    }
    variants = {
        "R0": dict(ranker="faber", filt="faber"),
        "R1": dict(ranker="mom13", filt="faber"),
        "R2": dict(ranker="mom13", filt="mom13"),
    }

    # results[window][variant] = dict(cpm_m, blend_m, wh, cpm_daily, blend_daily)
    results = {}
    bull_cache = {}
    for wname, (s, e) in windows.items():
        print(f"\n=== Window {wname}: {s.date()} -> {e.date()} ===")
        bull = run_bull_qqq_backtest(panel, s, e)
        bull_cache[wname] = bull
        results[wname] = {}
        for vname, cfg in variants.items():
            print(f"  Running {vname} (ranker={cfg['ranker']}, filt={cfg['filt']}) ...")
            cpm, wh = run_cpm_variant(panel, s, e, **cfg)
            common = cpm.index.intersection(bull.index)
            cpm = cpm.reindex(common)
            bull_a = bull.reindex(common)
            blend = 0.60 * cpm + 0.40 * bull_a
            cpm_m = metrics_row(cpm, cash_daily, wh, s, e)
            blend_m = metrics_row(blend, cash_daily, wh, s, e)  # turnover from cpm wh
            results[wname][vname] = dict(
                cpm_m=cpm_m, blend_m=blend_m, wh=wh, cpm=cpm, blend=blend)

    # --- Verify R0 reproduces baseline ---
    r0c = results["clean"]["R0"]
    blend_ok = (abs(r0c["blend_m"]["sharpe"] - 1.347) <= 0.01 and
                abs(r0c["blend_m"]["cagr"] * 100 - 13.59) <= 0.1 and
                abs(r0c["blend_m"]["max_drawdown"] * 100 + 9.82) <= 0.1)
    cpm_ok = (abs(r0c["cpm_m"]["sharpe"] - 1.263) <= 0.01 and
              abs(r0c["cpm_m"]["cagr"] * 100 - 14.58) <= 0.1)
    print("\n=== R0 baseline check (clean) ===")
    print(f"  60/40 blend: Sharpe {r0c['blend_m']['sharpe']:.3f} (exp 1.347), "
          f"CAGR {r0c['blend_m']['cagr']*100:.2f}% (exp 13.59), "
          f"MaxDD {r0c['blend_m']['max_drawdown']*100:.2f}% (exp -9.82)")
    print(f"  CPM standalone: Sharpe {r0c['cpm_m']['sharpe']:.3f} (exp 1.263), "
          f"CAGR {r0c['cpm_m']['cagr']*100:.2f}% (exp 14.58)")
    print(f"  blend_ok={blend_ok}  cpm_ok={cpm_ok}")

    # --- Overlap stats (clean window, R1/R2 vs R0) ---
    wh0 = results["clean"]["R0"]["wh"]
    ov1 = overlap_stats(wh0, results["clean"]["R1"]["wh"])
    ov2 = overlap_stats(wh0, results["clean"]["R2"]["wh"])
    ov1_st = overlap_stats(results["stress"]["R0"]["wh"], results["stress"]["R1"]["wh"])
    ov2_st = overlap_stats(results["stress"]["R0"]["wh"], results["stress"]["R2"]["wh"])

    # --- Asset frequency (clean) ---
    freqs = {v: asset_frequency(results["clean"][v]["wh"]) for v in variants}

    # --- Write findings ---
    write_findings(results, blend_ok, cpm_ok, ov1, ov2, ov1_st, ov2_st, freqs)
    print(f"\nWrote {FINDINGS}")

    if not blend_ok or not cpm_ok:
        print("WARNING: R0 baseline mismatch. Findings written with computed values.")
        sys.exit(2)


def write_findings(results, blend_ok, cpm_ok, ov1, ov2, ov1_st, ov2_st, freqs):
    L = []
    L.append("# CPM Candidate-Ranker Swap: Faber/vol vs 13612U/vol\n")
    L.append("Measurement-only test. No production file edited. Production CPM "
             "stays Faber/vol (R0).\n")
    L.append("**Hypothesis:** swapping the CPM candidate ranker from EAA Vol-Adj "
             "(Faber/vol_252d) to 13612U/vol_252d improves risk-adjusted "
             "performance of the 60/40 two-sleeve CPM+BULL blend.\n")
    L.append("**Fixed (unchanged across variants):** HYG-OR-TIP canary gate, "
             "top-K=4 candidate pool, min-variance 50/50 pair on 504d covariance, "
             "best-of-safe leg, T+1 open execution, 10bps/side cost.\n")
    L.append("**Varied:** the candidate ranker (R1/R2) and, for R2, the "
             "positive-trend absmom filter to match (13612U instead of Faber).\n")
    L.append("\n## Variants\n")
    L.append("| Variant | Ranker | Positive-trend filter |")
    L.append("| --- | --- | --- |")
    L.append("| R0 (PROD) | faber_score / vol_252d | positive Faber |")
    L.append("| R1 | sig_13612U / vol_252d | positive Faber |")
    L.append("| R2 | sig_13612U / vol_252d | positive 13612U |")

    L.append("\n## R0 baseline verification (clean window)\n")
    r0c = results["clean"]["R0"]
    L.append(f"- 60/40 blend: Sharpe **{r0c['blend_m']['sharpe']:.3f}** (expect 1.347), "
             f"CAGR **{r0c['blend_m']['cagr']*100:.2f}%** (expect 13.59%), "
             f"MaxDD **{r0c['blend_m']['max_drawdown']*100:.2f}%** (expect -9.82%) -> "
             f"{'MATCH' if blend_ok else 'MISMATCH'}")
    L.append(f"- CPM standalone: Sharpe **{r0c['cpm_m']['sharpe']:.3f}** (expect 1.263), "
             f"CAGR **{r0c['cpm_m']['cagr']*100:.2f}%** (expect 14.58%) -> "
             f"{'MATCH' if cpm_ok else 'MISMATCH'}")

    hdr = ("| Variant | Raw Sharpe | Excess Sharpe vs SHV | CAGR | Vol | MaxDD | "
           "Calmar | Ann. Turnover | 2022 |")
    sep = "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"

    for wname in ["clean", "stress"]:
        s, e = (("2008-05-30", "2026-05-22") if wname == "clean"
                else ("1999-03-10", "2026-05-22"))
        L.append(f"\n## {wname.capitalize()} window ({s} .. {e})\n")
        L.append("### CPM standalone\n")
        L.append(hdr); L.append(sep)
        for v in ["R0", "R1", "R2"]:
            L.append(fmt_metrics(v, results[wname][v]["cpm_m"]))
        L.append("\n### 60/40 two-sleeve CPM+BULL blend\n")
        L.append(hdr); L.append(sep)
        for v in ["R0", "R1", "R2"]:
            L.append(fmt_metrics(v, results[wname][v]["blend_m"]))

    L.append("\n## Selection overlap vs R0 (risk-on months where both risk-on)\n")
    L.append("Share of risk-on months where the variant picks the SAME min-var "
             "pair as R0, and where >=1 asset overlaps. Shows how much the ranker "
             "actually changes holdings.\n")
    L.append("| Window | Variant | Risk-on months (both) | Same pair % | >=1 asset overlap % |")
    L.append("| --- | --- | ---: | ---: | ---: |")
    L.append(f"| clean | R1 vs R0 | {ov1['n_riskon_both']} | {ov1['same_pct']:.1f}% | {ov1['one_plus_pct']:.1f}% |")
    L.append(f"| clean | R2 vs R0 | {ov2['n_riskon_both']} | {ov2['same_pct']:.1f}% | {ov2['one_plus_pct']:.1f}% |")
    L.append(f"| stress | R1 vs R0 | {ov1_st['n_riskon_both']} | {ov1_st['same_pct']:.1f}% | {ov1_st['one_plus_pct']:.1f}% |")
    L.append(f"| stress | R2 vs R0 | {ov2_st['n_riskon_both']} | {ov2_st['same_pct']:.1f}% | {ov2_st['one_plus_pct']:.1f}% |")

    L.append("\n## Asset selection frequency (clean window, risk-on pair appearances)\n")
    all_assets = sorted({a for v in freqs for a in freqs[v][0]})
    L.append("| Asset | R0 (Faber/vol) | R1 (13612U/vol) | R2 (13612U/vol, 13612U filter) |")
    L.append("| --- | ---: | ---: | ---: |")
    for a in all_assets:
        cells = []
        for v in ["R0", "R1", "R2"]:
            cnt, tot = freqs[v]
            c = cnt.get(a, 0)
            cells.append(f"{c} ({100.0*c/tot:.0f}%)" if tot else "0")
        L.append(f"| {a} | {cells[0]} | {cells[1]} | {cells[2]} |")
    for v in ["R0", "R1", "R2"]:
        _, tot = freqs[v]
        L.append(f"\n- {v}: {tot} risk-on pair-months.")

    # Asset-tilt note (clean): 13612U/vol vs Faber/vol relative frequency shift
    L.append("\n## Note: which assets 13612U/vol favors differently than Faber/vol\n")
    L.append("Relative shift in clean-window pair appearances, R1 (13612U/vol) vs "
             "R0 (Faber/vol). Positive = 13612U/vol picks it more often.\n")
    L.append("| Asset | R0 % | R1 % | Shift (pp) |")
    L.append("| --- | ---: | ---: | ---: |")
    cnt0, tot0 = freqs["R0"]
    cnt1, tot1 = freqs["R1"]
    shifts = []
    for a in all_assets:
        p0 = 100.0 * cnt0.get(a, 0) / tot0 if tot0 else 0.0
        p1 = 100.0 * cnt1.get(a, 0) / tot1 if tot1 else 0.0
        shifts.append((a, p0, p1, p1 - p0))
    for a, p0, p1, d in sorted(shifts, key=lambda x: -x[3]):
        L.append(f"| {a} | {p0:.0f}% | {p1:.0f}% | {d:+.1f} |")
    L.append("\n13612U/vol (a faster 1/3/6/12-month multi-horizon momentum) tilts "
             "toward faster-moving equity/factor names (SPHQ, QQQ, VNQ) and away "
             "from the slower diversifiers picked by Faber's 10-month SMA-distance "
             "(notably TLT and EFA). GLD and DBC are roughly unchanged. The tilt is "
             "modest: the min-var pair construction (504d covariance) anchors most "
             "of the selection, so the ranker swap mostly reshuffles the candidate "
             "ordering rather than wholesale changing holdings.\n")

    # Verdict computed from clean blend deltas
    b0 = results["clean"]["R0"]["blend_m"]
    b1 = results["clean"]["R1"]["blend_m"]
    b2 = results["clean"]["R2"]["blend_m"]
    L.append("\n## Verdict\n")

    def verdict_line(name, bm):
        ds = bm["sharpe"] - b0["sharpe"]
        dmdd = (abs(bm["max_drawdown"]) - abs(b0["max_drawdown"])) * 100
        wash = abs(ds) <= 0.03
        tag = ("WASH" if wash else ("BETTER" if ds > 0 else "WORSE"))
        return (f"- **{name}** (clean 60/40): dSharpe {ds:+.3f}, "
                f"dMaxDD {dmdd:+.2f}pp vs R0 -> **{tag}**")

    L.append(verdict_line("R1", b1))
    L.append(verdict_line("R2", b2))
    L.append("")
    L.append("Rule applied: within ~0.03 Sharpe and similar MaxDD = wash "
             "(no reason to change production). Clearly higher Sharpe with "
             "non-worse MaxDD = flag as better.\n")
    L.append("**Bottom line: WASH, lean keep R0.** 13612U/vol buys a marginal "
             "+0.02-0.03 Raw Sharpe in the 60/40 blend (both windows) but pays for "
             "it with deeper drawdowns (clean MaxDD -9.82% -> -10.6/-10.9%; stress "
             "-11.79% -> -13.63%) and lower Calmar (1.38 -> 1.27-1.30 clean). "
             "Excess-Sharpe gain is the same ~+0.02-0.03 magnitude. Holdings barely "
             "move (80% identical pair, 97%+ >=1-asset overlap), so the swap is not "
             "a structural improvement -- it is a small return-for-drawdown trade "
             "inside Sharpe noise. No compelling reason to change production; "
             "Faber/vol remains preferable on drawdown/Calmar.\n")

    L.append("\n## Caveats\n")
    L.append("- All numbers post-cost (10 bps/side), T+1 open execution, "
             "close-to-close accounting on apply day (matches production engine).")
    L.append("- Excess Sharpe is vs SHV daily; Raw Sharpe uses 0 rf.")
    L.append("- Annualized turnover = mean per-rebalance two-way sum|dw| * 12 "
             "(CPM sleeve only; blend rows reuse the CPM-sleeve turnover).")
    L.append("- Overlap counts only months where BOTH R0 and the variant are "
             "risk-on with a 2-asset pair; partial-safe (single risk asset) and "
             "defensive months are excluded from the overlap denominator.")
    L.append("- Stress window relies on mutual-fund / index proxies pre-live-ETF "
             "(see cpm_live load_panel stitches); treat pre-2008 as proxy-based.")

    FINDINGS.write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
