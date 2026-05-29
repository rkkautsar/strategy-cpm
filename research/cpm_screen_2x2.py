#!/usr/bin/env python3
"""
CPM candidate-screen 2x2: disentangle the top-K cap from the per-asset
positive-Faber (absolute-momentum) filter.

Canary (HYG OR TIP) is UNCHANGED in all four variants. Only the per-asset
screens change. Construction (EAA vol-adj rank -> min-var 50/50 pair, 504d
cov) is otherwise identical to production.

2x2:
  C0 (PROD): K=4 cap + positive-Faber filter.
  A:         NO K cap + positive-Faber filter (min-var pair among ALL positive-trend, up to 8).
  B:         K=4 cap + NO absmom filter (top-4 by EAA regardless of sign).
  D:         NO K cap + NO absmom filter (min-var pair among ALL 8 risky assets).

Outputs research/cpm_screen_2x2_findings.md (written incrementally).
Run: .venv/bin/python research/cpm_screen_2x2.py
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import cpm_live as cpm
from cpm_live import (
    load_panel, perf_metrics,
    faber_sma_xs, best_safe, sig_13612U, min_vol_pair,
    RISKY_UNIVERSE, SAFE_POOL, CANARY_ASSETS, DEFAULT_CASH,
    CANARY_RULE, CORR_LOOKBACK_DAYS, COST_BPS_PER_SIDE,
)
from bull_qqq_live import run_bull_qqq_backtest

FINDINGS = ROOT / "research" / "cpm_screen_2x2_findings.md"
WINDOWS = {
    "clean": (pd.Timestamp("2008-05-30"), pd.Timestamp("2026-05-22")),
    "stress": (pd.Timestamp("1999-03-10"), pd.Timestamp("2026-05-22")),
}
# variant -> (use_k_cap, use_absmom)
VARIANTS = {
    "C0": (True, True),   # PROD
    "A":  (False, True),  # no K cap, keep absmom
    "B":  (True, False),  # K cap, no absmom
    "D":  (False, False), # no K cap, no absmom
}
VARIANT_DESC = {
    "C0": "PROD: K=4 + positive-Faber",
    "A":  "no K cap + positive-Faber",
    "B":  "K=4 + NO absmom (AAA-style top-half)",
    "D":  "no K cap + NO absmom (min-var among all 8)",
}
# Primary blend: 60/40 two-sleeve CPM + BULL-SPY (research default, no NDX).
BLEND_W = {"cpm": 0.60, "bull": 0.40}

_lines: list[str] = []
def emit(s: str = ""):
    _lines.append(s)
    print(s)
    FINDINGS.write_text("\n".join(_lines) + "\n")


# ---------- Variant allocation (replica of compute_target_weights w/ flags) ----------

def compute_variant(close: pd.DataFrame, sig_d: pd.Timestamp,
                    use_k_cap: bool, use_absmom: bool) -> dict:
    """Replicate production allocation with parametrized screens.

    Returns dict with: weights, pair, regime, safe, and diagnostics:
      faber (full series), ranked (EAA vol-adj, all avail), candidates,
      ranks_full (EAA rank of each pair member within ALL avail assets),
      pair_signs (faber sign of each pair member).
    """
    monthly = close.loc[:sig_d].resample("ME").last()
    safe = best_safe(monthly, sig_d, SAFE_POOL)

    # Canary (UNCHANGED across variants)
    canary_scores = []
    for c in CANARY_ASSETS:
        if c not in monthly.columns:
            continue
        s = sig_13612U(monthly[c])
        if pd.notna(s):
            canary_scores.append(s)
    if not canary_scores:
        return {"weights": {safe: 1.0}, "pair": None, "regime": "DEFENSIVE", "safe": safe}
    n_pos = sum(1 for s in canary_scores if s > 0)
    if CANARY_RULE == "any_positive" and n_pos == 0:
        return {"weights": {safe: 1.0}, "pair": None, "regime": "DEFENSIVE", "safe": safe}
    elif CANARY_RULE == "all_positive" and n_pos < len(canary_scores):
        return {"weights": {safe: 1.0}, "pair": None, "regime": "DEFENSIVE", "safe": safe}

    faber = faber_sma_xs(monthly)
    avail = [t for t in RISKY_UNIVERSE
             if t in faber.index and pd.notna(faber[t])
             and (sig_d in close.index and pd.notna(close.loc[sig_d].get(t, np.nan)))]
    if not avail:
        return {"weights": {safe: 1.0}, "pair": None, "regime": "DEFENSIVE", "safe": safe}

    daily_rets = close[avail].ffill().pct_change()
    scores = {}
    for t in avail:
        v = daily_rets[t].loc[:sig_d].tail(252).std() * np.sqrt(252)
        if pd.isna(v) or v < 1e-9:
            v = 1.0
        scores[t] = float(faber[t]) / v
    sa = pd.Series(scores)
    ranked = sa.sort_values(ascending=False)   # EAA vol-adj rank, all avail
    # EAA rank of every asset within full avail universe (1=best)
    rank_full = {t: i + 1 for i, t in enumerate(ranked.index)}

    # K cap
    if use_k_cap:
        k = max(2, min(cpm.TOP_K_CANDIDATES, len(ranked)))
        top = ranked.iloc[:k]
    else:
        top = ranked  # all avail

    # absmom filter
    if use_absmom:
        selected = top[top.index.map(lambda t: faber.get(t, -np.inf) > 0)]
    else:
        selected = top

    # Partial-safe fill if <2 (only reachable when absmom on; B/D always >=2)
    if len(selected) < 2:
        if len(selected) == 1:
            t0 = selected.index[0]
            return {"weights": {t0: 0.5, safe: 0.5}, "pair": None, "regime": "RISK_ON",
                    "safe": safe, "faber": faber, "ranked": ranked, "rank_full": rank_full,
                    "candidates": [t0], "partial": True}
        return {"weights": {safe: 1.0}, "pair": None, "regime": "DEFENSIVE", "safe": safe,
                "faber": faber, "ranked": ranked, "rank_full": rank_full, "candidates": []}

    candidates = list(selected.index)
    pick = min_vol_pair(close.loc[:sig_d, candidates], candidates, CORR_LOOKBACK_DAYS)
    if pick is None:
        return {"weights": {candidates[0]: 1.0}, "pair": None, "regime": "RISK_ON",
                "safe": safe, "faber": faber, "ranked": ranked, "rank_full": rank_full,
                "candidates": candidates}
    pair = tuple(pick)
    ranks_full = tuple(rank_full[a] for a in pair)
    pair_signs = tuple("+" if faber.get(a, -np.inf) > 0 else "-" for a in pair)
    return {"weights": {pair[0]: 0.5, pair[1]: 0.5}, "pair": pair, "regime": "RISK_ON",
            "safe": safe, "faber": faber, "ranked": ranked, "rank_full": rank_full,
            "candidates": candidates, "ranks_full": ranks_full, "pair_signs": pair_signs}


def run_variant_backtest(panel: pd.DataFrame, start, end, use_k_cap, use_absmom,
                         cost_bps=COST_BPS_PER_SIDE):
    """Mirror run_cpm_backtest using compute_variant. Returns (daily_ret, hist, monthly_diag)."""
    cols = sorted(set(RISKY_UNIVERSE + SAFE_POOL + CANARY_ASSETS + [DEFAULT_CASH]) & set(panel.columns))
    close = panel[cols]
    midx = pd.DataFrame({"x": 1}, index=close.index).groupby(pd.Grouper(freq="ME")).tail(1)
    signal_dates = midx.index[(midx.index >= start) & (midx.index <= end)].tolist()

    weights_history = []
    monthly_diag = {}
    for i, sig_d in enumerate(signal_dates):
        d = compute_variant(close, sig_d, use_k_cap, use_absmom)
        monthly_diag[sig_d] = d
        future = close.index[close.index > sig_d]
        if len(future) < 1:
            continue
        apply_from = future[0]
        if i + 1 < len(signal_dates):
            next_sig = signal_dates[i + 1]
            nf = close.index[close.index > next_sig]
            end_apply = nf[0] if len(nf) >= 1 else end
        else:
            end_apply = end
        weights_history.append({"apply_from": apply_from, "end_apply": end_apply,
                                "weights": d["weights"], "sig_d": sig_d,
                                "regime": d["regime"], "safe": d["safe"]})

    all_assets = sorted({a for h in weights_history for a in h["weights"]})
    df_w = pd.DataFrame(0.0, index=close.index, columns=[a for a in all_assets if a in close.columns])
    for h in weights_history:
        mask = (close.index >= h["apply_from"]) & (close.index < h["end_apply"])
        for a, ww in h["weights"].items():
            if a in df_w.columns:
                df_w.loc[mask, a] = ww
    daily_ret = close.ffill().pct_change()
    common = [a for a in df_w.columns if a in daily_ret.columns]
    raw = (df_w[common] * daily_ret[common]).sum(axis=1, min_count=1).fillna(0.0)

    for i in range(len(weights_history)):
        prev = weights_history[i - 1]["weights"] if i > 0 else {}
        curr = weights_history[i]["weights"]
        keys = set(curr) | set(prev)
        turnover = sum(abs(curr.get(k, 0.0) - prev.get(k, 0.0)) for k in keys)
        cost = turnover * cost_bps / 10000.0
        af = weights_history[i]["apply_from"]
        if af in raw.index:
            raw.loc[af] -= cost

    # Per-signal-month realized return (holding-period, post-cost)
    for h in weights_history:
        mask = (raw.index >= h["apply_from"]) & (raw.index < h["end_apply"])
        seg = raw.loc[mask]
        monthly_diag[h["sig_d"]]["realized_ret"] = float((1.0 + seg).prod() - 1.0) if len(seg) else np.nan

    out = raw.loc[(raw.index >= start) & (raw.index <= end)]
    return out, weights_history, monthly_diag


def annualized_turnover(weights_history: list) -> float:
    if not weights_history:
        return float("nan")
    tot = 0.0
    for i in range(1, len(weights_history)):
        prev = weights_history[i - 1]["weights"]
        curr = weights_history[i]["weights"]
        keys = set(prev) | set(curr)
        tot += 0.5 * sum(abs(curr.get(k, 0.0) - prev.get(k, 0.0)) for k in keys)
    yrs = (weights_history[-1]["apply_from"] - weights_history[0]["apply_from"]).days / 365.25
    return tot / yrs if yrs > 0 else float("nan")


def metrics_row(name, daily, cash_daily):
    m = perf_metrics(daily, cash_daily)
    return {"name": name, "sharpe": m["sharpe"], "excess_sharpe": m["excess_sharpe"],
            "cagr": m["cagr"], "vol": m["vol"], "maxdd": m["max_drawdown"],
            "calmar": m["calmar"]}


def cal_year_return(daily: pd.Series, year: int) -> float:
    seg = daily[(daily.index >= pd.Timestamp(f"{year}-01-01")) &
                (daily.index <= pd.Timestamp(f"{year}-12-31"))]
    if seg.empty:
        return float("nan")
    return float((1.0 + seg).prod() - 1.0)


def main():
    emit("# CPM Candidate-Screen 2x2: Top-K Cap vs Positive-Faber Filter")
    emit()
    emit("Generated by `research/cpm_screen_2x2.py` using `.venv/bin/python`.")
    emit("Canary (HYG OR TIP, 13612U any-positive) is UNCHANGED in all four variants; "
         "only the per-asset screens change. Construction otherwise identical to PROD "
         f"(EAA vol-adj rank -> min-var 50/50 pair, {CORR_LOOKBACK_DAYS}d cov).")
    emit()
    emit("| Variant | K cap | absmom filter | Description |")
    emit("|---------|-------|---------------|-------------|")
    for v in ["C0", "A", "B", "D"]:
        kc, am = VARIANTS[v]
        emit(f"| {v} | {'K=4' if kc else 'none'} | {'yes' if am else 'no'} | {VARIANT_DESC[v]} |")
    emit()
    emit(f"Windows: clean {WINDOWS['clean'][0].date()}..{WINDOWS['clean'][1].date()}, "
         f"stress {WINDOWS['stress'][0].date()}..{WINDOWS['stress'][1].date()}. "
         f"Primary blend = 60% CPM + 40% BULL-SPY (two-sleeve, raw).")
    emit()
    emit("Loading panels ...")
    panel = load_panel(start=pd.Timestamp("1993-01-01"))
    emit(f"Panel: {panel.index[0].date()} -> {panel.index[-1].date()}, {len(panel.columns)} cols.")
    emit()

    results = {}
    for wname, (start, end) in WINDOWS.items():
        shv = panel["SHV"].ffill().pct_change().loc[start:end].fillna(0.0)
        emit(f"[{wname}] computing BULL sleeve (variant-independent) ...")
        bull = run_bull_qqq_backtest(panel, start, end)
        for v in ["C0", "A", "B", "D"]:
            kc, am = VARIANTS[v]
            cpm_daily, hist, diag = run_variant_backtest(panel, start, end, kc, am)
            common = cpm_daily.index.intersection(bull.index)
            c = cpm_daily.reindex(common).fillna(0.0)
            b = bull.reindex(common).fillna(0.0)
            blend = BLEND_W["cpm"]*c + BLEND_W["bull"]*b
            shv_c = shv.reindex(common).fillna(0.0)
            results[(wname, v)] = {
                "cpm": metrics_row(f"CPM {v}", c, shv_c),
                "blend": metrics_row(f"Blend {v}", blend, shv_c),
                "turnover": annualized_turnover(hist),
                "cpm_daily": c, "blend_daily": blend, "diag": diag, "hist": hist,
                "cpm_2022": cal_year_return(c, 2022), "blend_2022": cal_year_return(blend, 2022),
            }
            r = results[(wname, v)]
            emit(f"[{wname}] {v}: CPM sharpe={r['cpm']['sharpe']:.3f} cagr={r['cpm']['cagr']*100:.2f}% "
                 f"maxdd={r['cpm']['maxdd']*100:.2f}% | blend sharpe={r['blend']['sharpe']:.3f} "
                 f"cagr={r['blend']['cagr']*100:.2f}%")
    emit()

    # Reproduction check
    emit("## Reproduction check (C0 = PROD, clean window)")
    c0 = results[("clean", "C0")]
    emit(f"CPM standalone:  Sharpe={c0['cpm']['sharpe']:.3f} (target ~1.263), "
         f"CAGR={c0['cpm']['cagr']*100:.2f}% (target ~14.58%)")
    emit(f"60/40 two-sleeve: Sharpe={c0['blend']['sharpe']:.3f} (target ~1.347), "
         f"CAGR={c0['blend']['cagr']*100:.2f}% (target ~13.59%), "
         f"MaxDD={c0['blend']['maxdd']*100:.2f}% (target ~-9.82%)")
    ok_cpm = abs(c0['cpm']['sharpe']-1.263) < 0.03 and abs(c0['cpm']['cagr']-0.1458) < 0.005
    ok_bl = abs(c0['blend']['sharpe']-1.347) < 0.03
    emit(f"Reproduction: CPM {'OK' if ok_cpm else 'MISMATCH'}, blend {'OK' if ok_bl else 'CHECK'}")
    if not ok_cpm:
        emit("**C0 MISMATCH -- halting per task contract (findings written so far).**")
        return
    emit()

    # 1. Performance tables
    for wname in WINDOWS:
        emit(f"## 1. Performance -- {wname} window")
        emit()
        emit("### CPM standalone")
        emit("| Variant | Raw Sharpe | Excess Sharpe(SHV) | CAGR | Vol | MaxDD | Calmar | Ann.Turnover | 2022 ret |")
        emit("|---------|-----------|--------------------|------|-----|-------|--------|--------------|----------|")
        for v in ["C0", "A", "B", "D"]:
            r = results[(wname, v)]; m = r["cpm"]
            star = " (PROD)" if v == "C0" else ""
            emit(f"| {v}{star} | {m['sharpe']:.3f} | {m['excess_sharpe']:.3f} | {m['cagr']*100:.2f}% | "
                 f"{m['vol']*100:.2f}% | {m['maxdd']*100:.2f}% | {m['calmar']:.3f} | "
                 f"{r['turnover']*100:.0f}% | {r['cpm_2022']*100:.2f}% |")
        emit()
        emit("### Full 60/40 two-sleeve blend (CPM + BULL-SPY)")
        emit("| Variant | Raw Sharpe | Excess Sharpe(SHV) | CAGR | Vol | MaxDD | Calmar | 2022 ret |")
        emit("|---------|-----------|--------------------|------|-----|-------|--------|----------|")
        for v in ["C0", "A", "B", "D"]:
            r = results[(wname, v)]; m = r["blend"]
            star = " (PROD)" if v == "C0" else ""
            emit(f"| {v}{star} | {m['sharpe']:.3f} | {m['excess_sharpe']:.3f} | {m['cagr']*100:.2f}% | "
                 f"{m['vol']*100:.2f}% | {m['maxdd']*100:.2f}% | {m['calmar']:.3f} | "
                 f"{r['blend_2022']*100:.2f}% |")
        emit()

    # 2. No-absmom variants: negative-trend holding analysis
    emit("## 2. No-absmom variants (B, D): how often a falling asset is held")
    emit()
    emit("Risk-on month = canary passes AND a min-var pair is selected. "
         "'Holds negative' = >=1 pair member has Faber score <= 0 at signal.")
    emit()
    for wname in WINDOWS:
        emit(f"### {wname} window")
        emit("| Variant | risk-on months | % months holding >=1 neg-trend | mean ret (neg-holding mo) | mean ret (pos-only mo) |")
        emit("|---------|----------------|--------------------------------|---------------------------|------------------------|")
        for v in ["B", "D"]:
            diag = results[(wname, v)]["diag"]
            neg_rets, pos_rets = [], []
            for sd, d in diag.items():
                if d.get("pair") is None or "pair_signs" not in d:
                    continue
                rr = d.get("realized_ret")
                if rr is None or pd.isna(rr):
                    continue
                if "-" in d["pair_signs"]:
                    neg_rets.append(rr)
                else:
                    pos_rets.append(rr)
            nm = len(neg_rets) + len(pos_rets)
            pct_neg = len(neg_rets)/nm*100 if nm else float("nan")
            mn = np.mean(neg_rets)*100 if neg_rets else float("nan")
            mp = np.mean(pos_rets)*100 if pos_rets else float("nan")
            emit(f"| {v} | {nm} | {pct_neg:.1f}% | {mn:.2f}% (n={len(neg_rets)}) | {mp:.2f}% (n={len(pos_rets)}) |")
        emit()

    # 3. No-K variants: EAA rank distribution of selected pair
    emit("## 3. No-K variants (A, D): EAA-rank drift of the min-var pair")
    emit()
    emit("EAA rank = vol-adj Faber rank within ALL available risky assets (1=best, 8=worst). "
         "Bottom-half = rank >= 5 (of 8). C0 shown as reference (K=4 caps candidates to ranks 1-4).")
    emit()
    for wname in WINDOWS:
        emit(f"### {wname} window")
        emit("| Variant | risk-on months | mean pair EAA-rank | % months pair includes bottom-half (rank>=5) | max rank seen |")
        emit("|---------|----------------|--------------------|-----------------------------------------------|---------------|")
        for v in ["C0", "A", "D"]:
            diag = results[(wname, v)]["diag"]
            all_ranks, n_bottom, nm, maxr = [], 0, 0, 0
            for sd, d in diag.items():
                rf = d.get("ranks_full")
                if rf is None:
                    continue
                nm += 1
                all_ranks.extend(rf)
                if max(rf) >= 5:
                    n_bottom += 1
                maxr = max(maxr, max(rf))
            mean_rank = np.mean(all_ranks) if all_ranks else float("nan")
            pct_bottom = n_bottom/nm*100 if nm else float("nan")
            emit(f"| {v} | {nm} | {mean_rank:.2f} | {pct_bottom:.1f}% | {maxr} |")
        emit()

    # 4. Numeric verdict summary
    emit("## 4. Verdict (numeric summary)")
    emit()
    for wname in WINDOWS:
        emit(f"### {wname}")
        cpm_sh = {v: results[(wname, v)]["cpm"]["sharpe"] for v in ["C0","A","B","D"]}
        bl_sh = {v: results[(wname, v)]["blend"]["sharpe"] for v in ["C0","A","B","D"]}
        cpm_dd = {v: results[(wname, v)]["cpm"]["maxdd"] for v in ["C0","A","B","D"]}
        bl_dd = {v: results[(wname, v)]["blend"]["maxdd"] for v in ["C0","A","B","D"]}
        emit("CPM Sharpe: " + ", ".join(f"{v}={cpm_sh[v]:.3f}" for v in ["C0","A","B","D"]))
        emit("Blend Sharpe: " + ", ".join(f"{v}={bl_sh[v]:.3f}" for v in ["C0","A","B","D"]))
        emit("CPM MaxDD: " + ", ".join(f"{v}={cpm_dd[v]*100:.2f}%" for v in ["C0","A","B","D"]))
        emit("Blend MaxDD: " + ", ".join(f"{v}={bl_dd[v]*100:.2f}%" for v in ["C0","A","B","D"]))
        emit()
    emit("Marginal effects (clean, CPM standalone Sharpe):")
    cc = results[("clean", "C0")]["cpm"]["sharpe"]
    cb = results[("clean", "B")]["cpm"]["sharpe"]
    ca = results[("clean", "A")]["cpm"]["sharpe"]
    cd = results[("clean", "D")]["cpm"]["sharpe"]
    emit(f"- Remove absmom (C0->B), K=4 held: {cc:.3f} -> {cb:.3f} ({(cb-cc):+.3f})")
    emit(f"- Remove K cap (C0->A), absmom held: {cc:.3f} -> {ca:.3f} ({(ca-cc):+.3f})")
    emit(f"- Remove both (C0->D): {cc:.3f} -> {cd:.3f} ({(cd-cc):+.3f})")
    emit("")
    emit("(Narrative verdict appended after numeric review.)")
    print("\nDONE. Findings written to", FINDINGS)


if __name__ == "__main__":
    main()
