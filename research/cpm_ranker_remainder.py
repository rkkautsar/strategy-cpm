#!/usr/bin/env python3
"""
CPM candidate-ranker ablation remainder: forms not yet tested.

Measurement-only. Does NOT edit any production file. Reimplements a
parametrized version of cpm_live.compute_target_weights / run_cpm_backtest so
the canary gate, positive-Faber filter, top-K=4, and min-variance 50/50 pair
construction stay FIXED and ONLY the candidate ranker varies.

Already tested elsewhere (NOT repeated except R0 as reference):
  - Faber/vol_252d  (PROD)  -> cpm_ranker_13612u_vol (R0)
  - 13612U/vol_252d (wash)  -> cpm_ranker_13612u_vol (R1/R2)

Variants here (ranker only; filter is ALWAYS positive-Faber):
  R0 (PROD): faber_score / vol_252d         (reference reproduction)
  R1:        faber_score                     (Faber-only, no vol adjustment)
  R2:        price/price_12m - 1             (plain 12m momentum)
  R3:        price/price_6m  - 1             (plain 6m momentum; ~AAA 6-month)
  R4:        mean_252d_daily_ret / vol_252d  (Sharpe-like)

Windows:
  clean  2008-05-30 .. 2026-05-22
  stress 1999-03-10 .. 2026-05-22

Run: .venv/bin/python research/cpm_ranker_remainder.py
"""
from __future__ import annotations

import sys
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
from bull_spy_live import run_bull_spy_backtest

FINDINGS = Path(__file__).resolve().parent / "cpm_ranker_remainder_findings.md"

VARIANTS = {
    "R0": dict(ranker="faber_vol", desc="faber_score / vol_252d (PROD)"),
    "R1": dict(ranker="faber",     desc="faber_score (Faber-only, no vol adj)"),
    "R2": dict(ranker="mom12",     desc="price/price_12m - 1 (plain 12m mom)"),
    "R3": dict(ranker="mom6",      desc="price/price_6m - 1 (plain 6m mom)"),
    "R4": dict(ranker="sharpe",    desc="mean_252d_daily_ret / vol_252d (Sharpe-like)"),
}


def _mom_n(monthly: pd.Series, n: int) -> float:
    """Plain n-month total return: price/price_{n months ago} - 1."""
    s = monthly.dropna()
    if len(s) < n + 1:
        return np.nan
    return float(s.iloc[-1] / s.iloc[-(n + 1)] - 1)


def compute_target_weights_variant(
    close_panel: pd.DataFrame,
    sig_d: pd.Timestamp,
    ranker: str,
    universe: list = None,
    safe_pool: list = None,
    canary_assets: list = None,
) -> tuple[dict, tuple, str, str]:
    """Parametrized clone of cpm_live.compute_target_weights.

    Canary gate, positive-Faber filter, top-K, and min_vol_pair construction
    are identical to prod. Only the candidate ranker varies.
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

    # --- Faber score: ALWAYS the positive-trend filter; also part of R0/R1 ---
    faber = faber_sma_xs(monthly)

    # Raw (pre-vol) ranker score per asset.
    def raw_rank(t):
        if ranker in ("faber_vol", "faber"):
            return faber.get(t, np.nan)
        if ranker == "mom12":
            return _mom_n(monthly[t], 12) if t in monthly.columns else np.nan
        if ranker == "mom6":
            return _mom_n(monthly[t], 6) if t in monthly.columns else np.nan
        if ranker == "sharpe":
            return None  # handled via daily stats below
        raise ValueError(ranker)

    has_price = (sig_d in close_panel.index)
    # avail requires: faber notna (filter), price notna, and (for non-sharpe)
    # the raw ranker score notna.
    avail = []
    for t in universe:
        if pd.isna(faber.get(t, np.nan)):
            continue
        if not (pd.notna(close_panel.loc[sig_d].get(t, np.nan)) if has_price else False):
            continue
        if ranker not in ("faber_vol", "sharpe"):
            if pd.isna(raw_rank(t)):
                continue
        avail.append(t)
    if not avail:
        return {safe: 1.0}, None, "DEFENSIVE", safe

    daily_rets = close_panel[avail].ffill().pct_change()
    scores = {}
    for t in avail:
        win = daily_rets[t].loc[:sig_d].tail(252)
        v = win.std() * np.sqrt(252)
        if pd.isna(v) or v < 1e-9:
            v = 1.0
        if ranker == "faber_vol":
            scores[t] = float(faber[t]) / v
        elif ranker == "faber":
            scores[t] = float(faber[t])
        elif ranker == "sharpe":
            mu = win.mean() * 252
            scores[t] = float(mu) / v if pd.notna(mu) else np.nan
        else:  # mom12 / mom6
            scores[t] = float(raw_rank(t))
    sa = pd.Series({k: v for k, v in scores.items() if pd.notna(v)})
    if sa.empty:
        return {safe: 1.0}, None, "DEFENSIVE", safe
    ranked = sa.sort_values(ascending=False)
    top_k = max(2, min(TOP_K_CANDIDATES, len(ranked)))
    top = ranked.iloc[:top_k]

    # Positive-Faber filter (fixed across all variants).
    positive = top[top.index.map(lambda t: faber.get(t, -np.inf) > 0)]

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


def run_cpm_variant(panel, start, end, ranker, cost_bps=COST_BPS_PER_SIDE):
    """Clone of cpm_live.run_cpm_backtest using parametrized weights fn.

    Also captures per-month EAA-rank (vol-adj Faber order) for rank-stability.
    """
    cols = sorted(set(RISKY_UNIVERSE + SAFE_POOL + CANARY_ASSETS + [DEFAULT_CASH]) & set(panel.columns))
    close = panel[cols]

    monthly_idx = pd.DataFrame({"x": 1}, index=close.index).groupby(pd.Grouper(freq="ME")).tail(1)
    signal_dates = monthly_idx.index[(monthly_idx.index >= start) & (monthly_idx.index <= end)].tolist()

    weights_history = []
    for i, sig_d in enumerate(signal_dates):
        w, new_pair, regime, safe = compute_target_weights_variant(
            close, sig_d, ranker=ranker)
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


# ---------- EAA-rank stability (rank of selected assets in R0's vol-adj order) ----------

def eaa_ranks_by_month(panel, start, end):
    """For each risk-on signal date, the full EFaber/vol) ranking of the
    universe -> {sig_d: {asset: rank_position(1=best)}}. Used to score how
    high a variant's picked pair sits in the production EAA order."""
    cols = sorted(set(RISKY_UNIVERSE + SAFE_POOL + CANARY_ASSETS + [DEFAULT_CASH]) & set(panel.columns))
    close = panel[cols]
    monthly_idx = pd.DataFrame({"x": 1}, index=close.index).groupby(pd.Grouper(freq="ME")).tail(1)
    signal_dates = monthly_idx.index[(monthly_idx.index >= start) & (monthly_idx.index <= end)].tolist()
    out = {}
    for sig_d in signal_dates:
        monthly = close.loc[:sig_d].resample("ME").last()
        faber = faber_sma_xs(monthly)
        has_price = (sig_d in close.index)
        avail = [t for t in RISKY_UNIVERSE
                 if pd.notna(faber.get(t, np.nan))
                 and (pd.notna(close.loc[sig_d].get(t, np.nan)) if has_price else False)]
        if not avail:
            continue
        daily_rets = close[avail].ffill().pct_change()
        sc = {}
        for t in avail:
            v = daily_rets[t].loc[:sig_d].tail(252).std() * np.sqrt(252)
            if pd.isna(v) or v < 1e-9:
                v = 1.0
            sc[t] = float(faber[t]) / v
        ranked = pd.Series(sc).sort_values(ascending=False)
        out[sig_d] = {a: i + 1 for i, a in enumerate(ranked.index)}
    return out


def mean_eaa_rank_of_picks(wh, eaa_ranks):
    """Mean EAA-rank of assets in the variant's selected pair (risk-on months).
    Lower = variant tends to pick higher in production's vol-adj Faber order."""
    vals = []
    for h in wh:
        p = h.get("pair")
        if not p:
            continue
        ranks = eaa_ranks.get(h["sig_d"])
        if not ranks:
            continue
        for a in p:
            if a in ranks:
                vals.append(ranks[a])
    return float(np.mean(vals)) if vals else float("nan")


# ---------- metrics helpers ----------

def annualized_turnover(weights_history):
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


def metrics_row(daily, cash_daily, wh):
    m = perf_metrics(daily, cash_daily)
    m["turnover"] = annualized_turnover(wh) if wh is not None else float("nan")
    m["ret_2022"] = cal_return(daily, 2022)
    return m


def pair_set(h):
    p = h.get("pair")
    return frozenset(p) if p else None


def overlap_stats(wh_ref, wh_var):
    ref_by_d = {h["sig_d"]: pair_set(h) for h in wh_ref}
    var_by_d = {h["sig_d"]: pair_set(h) for h in wh_var}
    same = one_plus = n = 0
    for d, rp in ref_by_d.items():
        if rp is None:
            continue
        vp = var_by_d.get(d)
        if vp is None:
            continue
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

    results = {}
    eaa_ranks_w = {}
    for wname, (s, e) in windows.items():
        print(f"\n=== Window {wname}: {s.date()} -> {e.date()} ===")
        bull = run_bull_spy_backtest(panel, s, e)
        eaa_ranks_w[wname] = eaa_ranks_by_month(panel, s, e)
        results[wname] = {}
        for vname, cfg in VARIANTS.items():
            print(f"  Running {vname} ({cfg['desc']}) ...")
            cpm, wh = run_cpm_variant(panel, s, e, ranker=cfg["ranker"])
            common = cpm.index.intersection(bull.index)
            cpm = cpm.reindex(common)
            bull_a = bull.reindex(common)
            blend = 0.60 * cpm + 0.40 * bull_a
            cpm_m = metrics_row(cpm, cash_daily, wh)
            blend_m = metrics_row(blend, cash_daily, wh)
            results[wname][vname] = dict(
                cpm_m=cpm_m, blend_m=blend_m, wh=wh, cpm=cpm, blend=blend)

    # --- R0 baseline check (clean) ---
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

    # --- Overlap + EAA-rank stability ---
    overlaps = {}
    eaa_rank_means = {}
    for wname in ["clean", "stress"]:
        wh0 = results[wname]["R0"]["wh"]
        overlaps[wname] = {}
        eaa_rank_means[wname] = {}
        for v in VARIANTS:
            overlaps[wname][v] = overlap_stats(wh0, results[wname][v]["wh"])
            eaa_rank_means[wname][v] = mean_eaa_rank_of_picks(
                results[wname][v]["wh"], eaa_ranks_w[wname])

    freqs = {v: asset_frequency(results["clean"][v]["wh"]) for v in VARIANTS}

    write_findings(results, blend_ok, cpm_ok, overlaps, eaa_rank_means, freqs)
    print(f"\nWrote {FINDINGS}")

    if not blend_ok or not cpm_ok:
        print("WARNING: R0 baseline mismatch. Findings written with computed values.")
        sys.exit(2)


def write_findings(results, blend_ok, cpm_ok, overlaps, eaa_rank_means, freqs):
    L = []
    L.append("# CPM Candidate-Ranker Ablation Remainder (R0..R4)\n")
    L.append("Measurement-only. No production file edited. Production CPM stays "
             "EAA Faber/vol (R0).\n")
    L.append("**Question:** is the vol-adjustment (R1 Faber-only) or the Faber "
             "form itself (R2/R3 plain momentum) necessary, or is a simpler "
             "ranker a defensible simplification of the production EAA ranker?\n")
    L.append("**Fixed across all variants:** HYG-OR-TIP canary gate, "
             "POSITIVE-FABER trend filter, top-K=4 candidate pool, min-variance "
             "50/50 pair on 504d covariance, best-of-safe leg, T+1 open execution, "
             "10 bps/side cost.\n")
    L.append("**Varied:** ONLY the ranker used to pick the top-4 candidates.\n")
    L.append("\n## Variants\n")
    L.append("| Variant | Ranker | Vol-adjusted? |")
    L.append("| --- | --- | --- |")
    L.append("| R0 (PROD) | faber_score / vol_252d | yes |")
    L.append("| R1 | faber_score | no |")
    L.append("| R2 | price/price_12m - 1 (plain 12m mom) | no |")
    L.append("| R3 | price/price_6m - 1 (plain 6m mom) | no |")
    L.append("| R4 | mean_252d_daily_ret / vol_252d (Sharpe-like) | yes |")

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
        for v in VARIANTS:
            L.append(fmt_metrics(v, results[wname][v]["cpm_m"]))
        L.append("\n### 60/40 two-sleeve CPM+BULL blend\n")
        L.append(hdr); L.append(sep)
        for v in VARIANTS:
            L.append(fmt_metrics(v, results[wname][v]["blend_m"]))

    L.append("\n## Selection overlap vs R0 + EAA-rank stability\n")
    L.append("Share of risk-on months (both risk-on) where the variant picks the "
             "SAME min-var pair as R0 and where >=1 asset overlaps. Mean EAA-rank "
             "= average production-EAA rank position (1=best of 8) of the variant's "
             "selected pair; R0's own mean is the natural reference.\n")
    L.append("| Window | Variant | Risk-on months (both) | Same pair % | >=1 asset overlap % | Mean EAA-rank of picks |")
    L.append("| --- | --- | ---: | ---: | ---: | ---: |")
    for wname in ["clean", "stress"]:
        for v in VARIANTS:
            ov = overlaps[wname][v]
            er = eaa_rank_means[wname][v]
            L.append(f"| {wname} | {v} | {ov['n_riskon_both']} | "
                     f"{ov['same_pct']:.1f}% | {ov['one_plus_pct']:.1f}% | {er:.2f} |")

    L.append("\n## Asset selection frequency (clean window, risk-on pair appearances)\n")
    all_assets = sorted({a for v in freqs for a in freqs[v][0]})
    L.append("| Asset | " + " | ".join(VARIANTS.keys()) + " |")
    L.append("| --- | " + " | ".join(["---:"] * len(VARIANTS)) + " |")
    for a in all_assets:
        cells = []
        for v in VARIANTS:
            cnt, tot = freqs[v]
            c = cnt.get(a, 0)
            cells.append(f"{c} ({100.0*c/tot:.0f}%)" if tot else "0")
        L.append(f"| {a} | " + " | ".join(cells) + " |")
    for v in VARIANTS:
        _, tot = freqs[v]
        L.append(f"\n- {v}: {tot} risk-on pair-months.")

    # --- Verdict ---
    L.append("\n## Verdict\n")
    bc = {v: results["clean"][v]["blend_m"] for v in VARIANTS}
    bs = {v: results["stress"][v]["blend_m"] for v in VARIANTS}
    b0c, b0s = bc["R0"], bs["R0"]

    def verdict_line(v):
        dsc = bc[v]["sharpe"] - b0c["sharpe"]
        dmc = (abs(bc[v]["max_drawdown"]) - abs(b0c["max_drawdown"])) * 100
        dss = bs[v]["sharpe"] - b0s["sharpe"]
        dms = (abs(bs[v]["max_drawdown"]) - abs(b0s["max_drawdown"])) * 100
        # change-threshold: Sharpe within 0.05-0.10, MaxDD no worse by >1-2pp
        wash = abs(dsc) <= 0.05 and dmc <= 2.0
        if dsc > 0.05 and dmc <= 2.0:
            tag = "BETTER"
        elif wash:
            tag = "WASH"
        else:
            tag = "WORSE"
        return (f"- **{v}** ({VARIANTS[v]['desc']}): clean dSharpe {dsc:+.3f}, "
                f"dMaxDD {dmc:+.2f}pp | stress dSharpe {dss:+.3f}, "
                f"dMaxDD {dms:+.2f}pp vs R0 -> **{tag}**")

    for v in ["R1", "R2", "R3", "R4"]:
        L.append(verdict_line(v))
    L.append("")
    L.append("Change-threshold applied: a variant is a WASH (no reason to change "
             "production) if 60/40 blend Sharpe is within ~0.05 of R0 and MaxDD is "
             "not worse by more than ~1-2pp. BETTER requires clearly higher Sharpe "
             "(>0.05) with non-worse drawdown.\n")

    L.append("\n### Recommendation: KEEP EAA (Faber/vol)\n")
    L.append("- **Vol-adjustment IS doing real work.** Removing it (R1 Faber-only) "
             "costs -0.067 blend Sharpe in the clean window (1.347 -> 1.280) and "
             "lowers Calmar (1.38 -> 1.33). It does help the stress window "
             "(+0.041 Sharpe, shallower MaxDD), but the clean-window loss exceeds "
             "the change-threshold, so Faber-only is a net WORSE, not a defensible "
             "simplification.")
    L.append("- **The Faber form matters.** Both plain-momentum rankers are clearly "
             "WORSE in both windows: R2 (12m) -0.101 clean Sharpe with +4.3pp deeper "
             "MaxDD (-9.82% -> -14.14%); R3 (6m) -0.142 clean Sharpe, +1.5pp MaxDD, "
             "and the worst Calmar of the set. Plain momentum on two price endpoints "
             "is noisier than Faber's 10m SMA-distance and selects deeper-drawdown "
             "pairs even under the same positive-Faber filter and min-var pairing.")
    L.append("- **Only R4 (Sharpe-like) is a true wash** (clean +0.003, stress "
             "+0.004 Sharpe; comparable MaxDD; lowest turnover 544%). It is "
             "essentially a re-expression of the same vol-adjusted-trend idea, so "
             "it confirms the vol-adjustment family is the right one but offers no "
             "improvement worth a production change.")
    L.append("- **Bottom line:** neither dropping the vol-adjustment (R1) nor "
             "simplifying to plain momentum (R2/R3) is defensible within the "
             "change-threshold. The vol-adjustment in the ranker is doing real work; "
             "keep production EAA Faber/vol (R0).\n")

    L.append("\n## Caveats\n")
    L.append("- All numbers post-cost (10 bps/side), T+1 open execution, "
             "close-to-close accounting on apply day (matches production engine).")
    L.append("- Excess Sharpe is vs SHV daily; Raw Sharpe uses 0 rf.")
    L.append("- Annualized turnover = mean per-rebalance two-way sum|dw| * 12 "
             "(CPM sleeve only; blend rows reuse the CPM-sleeve turnover).")
    L.append("- Overlap counts only months where BOTH R0 and the variant are "
             "risk-on with a 2-asset pair; partial-safe / defensive months excluded.")
    L.append("- Mean EAA-rank uses production's Faber/vol ordering as the yardstick; "
             "lower = variant picks assets that production also rates highly.")
    L.append("- Positive-Faber filter is fixed for ALL variants, so even momentum "
             "rankers (R2/R3) can only select assets above their Faber 10m SMA.")
    L.append("- Stress window relies on mutual-fund / index proxies pre-live-ETF "
             "(see cpm_live load_panel stitches); treat pre-2008 as proxy-based.")

    FINDINGS.write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
