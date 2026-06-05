"""Two CPM sleeve backtests: L (TOP_K=5 drop-1 min-var) and B (clean drop-to-safe).

RESEARCH-ONLY. Prod untouched, no commit. Reuses canonical harness (mooex T+1,
both-252, 10 bps/side). Reproduces the 1.255673 anchor gate before trusting deltas.

Configs
-------
A  (baseline = prod): TOP_K=4, curve 25/50/75/100, min-var 3-of-4 @ 33.3% at
   n_pos=4, equal-split of risky_fraction otherwise. MUST reproduce 1.255673.

L  (TOP_K=5 generalized drop-1 min-var):
   - rank ALL 8 risky by vol-adj faber, take TOP_K=5. n_pos = #positive in top-5 (0..5).
   - exposure ramp = n_pos/5 (had to become n/5, not 25/50/75/100, since breadth
     now reaches 5).
   - selection: consistent "drop the 1 worst-variance asset" => min-var
     (n_pos-1)-of-n_pos for n_pos>=3 (n=5->4of5, n=4->3of4, n=3->2of3);
     hold ALL positives for n_pos<=2.
   - held names split risky_fraction equally; remainder -> best_safe. Canary TIP
     unchanged; n_pos=0 / canary-off -> 100% safe.

B  (drop-to-safe, clean blend re-test):
   - same as A EXCEPT at n_pos=4: hold min-var 3-of-4 @ 25% each (75% risky) +
     25% best_safe. per-name weight stays 25% at every breadth; dropped 4th slot's
     25% goes to safe (do NOT renormalize the 3 to 33.3%).
   - curve: n=1->25%, n=2->50%, n=3->75%, n=4->75% risky (3 @25%) +25% safe.

BLEND fix: patch build_dashboard.compute_target_weights (BD imports the symbol
into its OWN namespace; patching cpm_live.* alone silently measures prod A on
the blend rows). Patch both for safety. This is the CLEAN blend path; prior 1.509
for B was a monkeypatch-bug artifact measuring prod-A on both rows.
"""

from __future__ import annotations

from pathlib import Path
import sys
from collections import Counter

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import cpm_live
from cpm_live import (
    RISKY_UNIVERSE, SAFE_POOL, CANARY_ASSETS, CANARY_RULE,
    CORR_LOOKBACK_DAYS,
    best_safe, sig_13612U, faber_sma_xs, _min_var_subset,
    compute_target_weights,
)
from research import cpm_harness as H


# config -> params
# top_k: candidate pool size; denom: ramp denominator; weight_mode:
#   "equal_split"  -> each pick gets risky_fraction/len(picks)
#   "fixed_per_name" -> each pick gets 1/denom, safe gets remainder (drop-to-safe)
# select: callable(picks_desc, n_pos) -> held picks
def _select_A(picks, n_pos):
    if n_pos == 4:
        return _MV(picks, 3)
    return list(picks)


def _select_L(picks, n_pos):
    # consistent drop-1: min-var (n_pos-1)-of-n_pos for n_pos>=3; hold all for <=2
    if n_pos >= 3:
        return _MV(picks, n_pos - 1)
    return list(picks)


def _select_B(picks, n_pos):
    # same selection as A; the difference is in weight_mode (fixed_per_name)
    if n_pos == 4:
        return _MV(picks, 3)
    return list(picks)


# placeholder; bound to a closure over `close` inside main via _set_close
_CLOSE = {"panel": None}


def _MV(candidates, m):
    return _min_var_subset(_CLOSE["panel"], _MV.sig_d, candidates, CORR_LOOKBACK_DAYS, m)


CONFIGS = {
    "A": dict(top_k=4, denom=4, weight_mode="equal_split", select=_select_A),
    "L": dict(top_k=5, denom=5, weight_mode="equal_split", select=_select_L),
    "B": dict(top_k=4, denom=4, weight_mode="fixed_per_name", select=_select_B),
}
ORDER = ["A", "L", "B"]


def _core(close_panel, sig_d, cfg: str):
    """Parameterized copy of compute_target_weights.

    Returns (weights, basket, regime, safe, n_pos). n_pos=None unless RISK_ON.
    Canary, ranker math, and safe-selector are IDENTICAL to prod; only TOP_K,
    ramp denominator, selection rule, and weight mode vary by config.
    """
    p = CONFIGS[cfg]
    top_k_cand = p["top_k"]
    denom = p["denom"]
    weight_mode = p["weight_mode"]
    select = p["select"]

    _CLOSE["panel"] = close_panel
    _MV.sig_d = sig_d

    universe = RISKY_UNIVERSE
    safe_pool = SAFE_POOL
    canary_assets = CANARY_ASSETS

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
        return {safe: 1.0}, None, "DEFENSIVE", safe, None
    n_canary_pos = sum(1 for s in canary_scores if s > 0)
    if CANARY_RULE == "any_positive":
        if n_canary_pos == 0:
            return {safe: 1.0}, None, "DEFENSIVE", safe, None
    elif CANARY_RULE == "all_positive":
        if n_canary_pos < len(canary_scores):
            return {safe: 1.0}, None, "DEFENSIVE", safe, None
    else:
        if n_canary_pos <= len(canary_scores) // 2:
            return {safe: 1.0}, None, "DEFENSIVE", safe, None

    faber = faber_sma_xs(monthly)
    avail = [t for t in universe
             if t in faber.index and pd.notna(faber[t])
             and pd.notna(close_panel.loc[sig_d].get(t, np.nan) if sig_d in close_panel.index else np.nan)]
    if not avail:
        return {safe: 1.0}, None, "DEFENSIVE", safe, None

    daily_rets = close_panel[avail].ffill().pct_change()
    scores = {}
    for t in avail:
        v = daily_rets[t].loc[:sig_d].tail(252).std() * np.sqrt(252)
        if pd.isna(v) or v < 1e-9:
            v = 1.0
        scores[t] = float(faber[t]) / v
    sa = pd.Series(scores)
    ranked = sa.sort_values(ascending=False)
    top_k = max(2, min(top_k_cand, len(ranked)))
    top = ranked.iloc[:top_k]
    positive = top[top.index.map(lambda t: faber.get(t, -np.inf) > 0)]

    if len(positive) == 0:
        return {safe: 1.0}, None, "DEFENSIVE", safe, None

    positive_picks = list(positive.index)  # descending score order
    n_pos = len(positive_picks)
    picks = select(positive_picks, n_pos)

    if weight_mode == "equal_split":
        risky_fraction = min(n_pos, denom) / float(denom)
        safe_fraction = 1.0 - risky_fraction
        out = {t: (1.0 / len(picks)) * risky_fraction for t in picks}
        if safe_fraction > 1e-15:
            out[safe] = out.get(safe, 0.0) + safe_fraction
    elif weight_mode == "fixed_per_name":
        per = 1.0 / float(denom)
        out = {t: per for t in picks}
        safe_fraction = 1.0 - per * len(picks)
        if safe_fraction > 1e-15:
            out[safe] = out.get(safe, 0.0) + safe_fraction
    else:
        raise ValueError(weight_mode)

    return out, tuple(picks), "RISK_ON", safe, n_pos


def weight_fn_for(cfg: str):
    def _wf(close_panel, sig_d):
        out, *_ = _core(close_panel, sig_d, cfg)
        return out
    return _wf


def ctw_for(cfg: str):
    def _ctw(close_panel, sig_d, universe=None, safe_pool=None, canary_assets=None):
        out, basket, regime, safe, _ = _core(close_panel, sig_d, cfg)
        return out, basket, regime, safe
    return _ctw


# ----- gates -----
def _signal_dates(close, start, end):
    midx = (pd.DataFrame({"x": 1}, index=close.index)
            .groupby(pd.Grouper(freq="ME")).tail(1).index)
    return midx[(midx >= start) & (midx <= end)]


def verify_baseline_matches_prod(data) -> None:
    sigs = _signal_dates(data.panel, data.ext_start, data.end)
    close = data.panel
    max_diff = 0.0
    for sig_d in sigs:
        prod, *_ = compute_target_weights(close, sig_d)
        mine, *_ = _core(close, sig_d, "A")
        for k in set(prod) | set(mine):
            max_diff = max(max_diff, abs(prod.get(k, 0.0) - mine.get(k, 0.0)))
    if max_diff > 1e-12:
        raise AssertionError(f"A replica != prod, max weight diff {max_diff:.2e}")
    print(f"[ok] A replica matches prod (max weight diff {max_diff:.2e})")


def verify_B_equals_A_below_n4(close, sigs) -> str:
    """B must be bit-identical to A at n_pos in {0,1,2,3} & defensive; differ only n=4."""
    worst = {0: 0.0, 1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0}
    defensive_diff = 0.0
    for sig_d in sigs:
        a_out, _, _, _, n = _core(close, sig_d, "A")
        b_out, _, _, _, _ = _core(close, sig_d, "B")
        d = max(abs(a_out.get(k, 0.0) - b_out.get(k, 0.0)) for k in set(a_out) | set(b_out))
        if n is None:
            defensive_diff = max(defensive_diff, d)
        else:
            worst[n] = max(worst[n], d)
    lines = ["B vs A weight diff by n_pos (expect 0 except n=4):"]
    lines.append(f"  defensive={defensive_diff:.2e}  n1={worst[1]:.2e}  n2={worst[2]:.2e}  "
                 f"n3={worst[3]:.2e}  n4={worst[4]:.2e}")
    return "\n".join(lines)


# ----- L breadth analysis -----
def npos_histogram(close, sigs, cfg) -> str:
    hist = Counter()
    defensive = 0
    for sig_d in sigs:
        _, _, regime, _, n = _core(close, sig_d, cfg)
        if n is None:
            defensive += 1
        else:
            hist[n] += 1
    total = defensive + sum(hist.values())
    lines = [f"n_pos histogram ({cfg}, {total} signal months):"]
    lines.append(f"  defensive/canary-off/0-pos : {defensive:4d} ({100*defensive/total:5.1f}%)")
    for n in range(1, 6):
        c = hist.get(n, 0)
        lines.append(f"  n_pos={n}                    : {c:4d} ({100*c/total:5.1f}%)")
    n5 = hist.get(5, 0)
    n4 = hist.get(4, 0)
    lines.append(f"  -> n_pos=5 fires {n5} months; n_pos=4 fires {n4} months "
                 f"(ratio 5:4 = {n5}:{n4})")
    return "\n".join(lines)


def npos5_selection_examples(close, sigs, k=8) -> str:
    """At n_pos=5 (L), show which asset min-var 4-of-5 drops."""
    rows = []
    for sig_d in sigs:
        _, basket, regime, _, n = _core(close, sig_d, "L")
        if regime != "RISK_ON" or n != 5:
            continue
        positive_picks = _positive_picks(close, sig_d, top_k_cand=5)
        held = _min_var_subset(close, sig_d, positive_picks, CORR_LOOKBACK_DAYS, 4)
        dropped = [t for t in positive_picks if t not in held]
        rows.append({
            "month": sig_d.strftime("%Y-%m"),
            "positives": list(positive_picks),
            "held4": held,
            "dropped": dropped[0] if dropped else "-",
        })
    lines = [f"n_pos=5 months: {len(rows)} total"]
    if rows:
        drop_counts = Counter(r["dropped"] for r in rows)
        lines.append("min-var-dropped (the 5th) by ticker: "
                     + ", ".join(f"{t}:{c}" for t, c in drop_counts.most_common()))
        lines.append("")
        lines.append("month".ljust(9) + "positives(desc score)".ljust(34)
                     + "held(minvar4)".ljust(30) + "dropped".rjust(8))
        lines.append("-" * 81)
        for r in rows[:k]:
            lines.append(r["month"].ljust(9)
                         + ",".join(r["positives"]).ljust(34)
                         + ",".join(r["held4"]).ljust(30)
                         + r["dropped"].rjust(8))
    return "\n".join(lines)


def _positive_picks(close_panel, sig_d, top_k_cand):
    monthly = close_panel.loc[:sig_d].resample("ME").last()
    faber = faber_sma_xs(monthly)
    avail = [t for t in RISKY_UNIVERSE
             if t in faber.index and pd.notna(faber[t])
             and pd.notna(close_panel.loc[sig_d].get(t, np.nan) if sig_d in close_panel.index else np.nan)]
    daily_rets = close_panel[avail].ffill().pct_change()
    scores = {}
    for t in avail:
        v = daily_rets[t].loc[:sig_d].tail(252).std() * np.sqrt(252)
        if pd.isna(v) or v < 1e-9:
            v = 1.0
        scores[t] = float(faber[t]) / v
    ranked = pd.Series(scores).sort_values(ascending=False)
    top_k = max(2, min(top_k_cand, len(ranked)))
    top = ranked.iloc[:top_k]
    positive = top[top.index.map(lambda t: faber.get(t, -np.inf) > 0)]
    return list(positive.index)


# ----- metrics -----
def extra_metrics(daily: pd.Series) -> dict:
    d = daily.dropna()
    downside = d[d < 0]
    dd_std = downside.std(ddof=0) * np.sqrt(252)
    sortino = (d.mean() * 252) / dd_std if dd_std > 0 else float("nan")
    return {"Sortino": sortino}


def full_metrics(returns, cash) -> dict:
    m = cpm_live.perf_metrics(returns, cash)
    em = extra_metrics(returns)
    return {
        "Sharpe": m["sharpe"], "Sortino": em["Sortino"], "MaxDD": m["max_drawdown"],
        "Calmar": m["calmar"], "Martin": m["martin"], "CAGR": m["cagr"],
        "vol": m.get("vol"),
    }


def fmt_table(rows: dict, cols: list, pct_cols: set) -> str:
    head = "config".ljust(8) + "".join(c.rjust(11) for c in cols)
    lines = [head, "-" * len(head)]
    for name in ORDER:
        if name not in rows:
            continue
        m = rows[name]
        cells = []
        for c in cols:
            v = m[c]
            cells.append((f"{v*100:.2f}%" if c in pct_cols else f"{v:.4f}").rjust(11))
        lines.append(name.ljust(8) + "".join(cells))
    return "\n".join(lines)


CRISES = {
    "GFC 2008 (07-09..09-03)": ("2007-09-01", "2009-03-31"),
    "Euro 2011 (11-05..11-10)": ("2011-05-01", "2011-10-31"),
    "COVID 2020 (20-02..20-04)": ("2020-02-01", "2020-04-30"),
    "2022 bear (22-01..22-10)": ("2022-01-01", "2022-10-31"),
    "2025 tariff (25-02..25-05)": ("2025-02-01", "2025-05-22"),
}


def crisis_table(rets: dict) -> str:
    def cum(x): return (1 + x).prod() - 1
    def mdd(x):
        eq = (1 + x).cumprod()
        return (eq / eq.cummax() - 1).min()
    cfgs = [c for c in ORDER if c in rets]
    head = "crisis".ljust(30) + "".join((c + "_ret").rjust(11) for c in cfgs) \
        + "".join((c + "_DD").rjust(11) for c in cfgs)
    lines = [head, "-" * len(head)]
    for name, (s, e) in CRISES.items():
        cells_ret, cells_dd = [], []
        ok = True
        for c in cfgs:
            w = rets[c].loc[(rets[c].index >= s) & (rets[c].index <= e)]
            if w.empty:
                ok = False
                break
            cells_ret.append(f"{cum(w)*100:.2f}%".rjust(11))
            cells_dd.append(f"{mdd(w)*100:.2f}%".rjust(11))
        if not ok:
            lines.append(name.ljust(30) + "n/a (outside window)")
            continue
        lines.append(name.ljust(30) + "".join(cells_ret) + "".join(cells_dd))
    return "\n".join(lines)


def main():
    print("Loading harness data ...")
    data = H.load_data()
    cash = data.cash
    close = data.panel

    anc = H.verify_anchor(data=data)
    print(f"[ok] anchor Sharpe={anc['Sharpe']:.6f} MaxDD={anc['MaxDD']:.6f} "
          f"Calmar={anc['Calmar']:.6f}")
    verify_baseline_matches_prod(data)

    sigs_clean = _signal_dates(close, data.clean_start, data.end)
    sigs_ext = _signal_dates(close, data.ext_start, data.end)

    out = []
    out.append("# CPM sleeve: L (TOP_K=5 drop-1 min-var) + B (clean drop-to-safe) -- exploratory\n")
    out.append("RESEARCH-ONLY. Prod untouched, no commit. mooex T+1, both-252, 10 bps/side.")
    out.append(f"Anchor gate: Sharpe={anc['Sharpe']:.6f} (target 1.255673), "
               f"MaxDD={anc['MaxDD']*100:.4f}%, Calmar={anc['Calmar']:.6f}")
    out.append("\nConfigs:")
    out.append("  A : prod baseline. TOP_K=4, curve 25/50/75/100, min-var 3-of-4 @ 33.3% at n=4.")
    out.append("  L : TOP_K=5, ramp = n/5, consistent drop-1 min-var (n=5->4of5, 4->3of4,")
    out.append("      3->2of3, hold-all n<=2). Ramp HAD to become n/5 (not 25/50/75/100)")
    out.append("      since breadth now reaches 5. Held names split risky_fraction equally.")
    out.append("  B : drop-to-safe. = A except n=4 holds min-var 3-of-4 @ 25% each (75% risky)")
    out.append("      +25% best_safe (dropped 4th slot's 25% -> safe; the 3 are NOT renorm'd).")

    out.append("\n## B vs A weight identity check (clean window)")
    out.append("```")
    out.append(verify_B_equals_A_below_n4(close, sigs_clean))
    out.append("```")

    out.append("\n## L breadth (n_pos histogram)")
    out.append("```")
    out.append("CLEAN window:")
    out.append(npos_histogram(close, sigs_clean, "L"))
    out.append("")
    out.append("EXT window:")
    out.append(npos_histogram(close, sigs_ext, "L"))
    out.append("```")

    out.append("\n## L selection examples at n_pos=5 (which asset min-var 4-of-5 drops, ext window)")
    out.append("```")
    out.append(npos5_selection_examples(close, sigs_ext, k=10))
    out.append("```")

    # ---- SLEEVE level ----
    sleeve_rets = {"clean": {}, "ext": {}}
    for win in ("clean", "ext"):
        rows = {}
        for cfg in ORDER:
            r = H.run_strategy(weight_fn_for(cfg), window=win, data=data)
            sleeve_rets[win][cfg] = r
            rows[cfg] = full_metrics(r, cash)
        out.append(f"\n## SLEEVE ({win}) -- mooex T+1, 10bps")
        out.append("```")
        out.append(fmt_table(rows, ["Sharpe", "Sortino", "MaxDD", "Calmar",
                                    "Martin", "CAGR", "vol"], {"MaxDD", "CAGR", "vol"}))
        out.append("```")

    out.append("\n### Per-crisis sleeve (EXT window) cum return + maxDD")
    out.append("```")
    out.append(crisis_table(sleeve_rets["ext"]))
    out.append("```")

    # ---- BLEND 60/20/20 ----
    import build_dashboard as BD
    from cpm_live import load_panel
    print("Loading blend panel + NDX ...")
    bpanel = load_panel(start=pd.Timestamp("1995-01-01"), end=data.end, live=True)
    bend = min(data.end, bpanel.index[-1])
    bcash = bpanel["SHV"].ffill().pct_change().dropna()
    try:
        from ndx_sleeve_live import load_ndx_panel
        ndx_panel = load_ndx_panel()
    except Exception as e:
        print(f"  NDX panel unavailable ({e}); blend CPM+BULL only.")
        ndx_panel = None
    bstart = data.clean_start

    def blend_metrics(art):
        m = cpm_live.perf_metrics(art.blend, bcash)
        return {"Sharpe": m["sharpe"], "MaxDD": m["max_drawdown"], "CAGR": m["cagr"]}

    brows = {}
    blend_series = {}
    _orig_bd = BD.compute_target_weights
    _orig_cl = cpm_live.compute_target_weights
    for cfg in ORDER:
        print(f"Building blend {cfg} (BD.compute_target_weights patched) ...")
        ctw = ctw_for(cfg)
        BD.compute_target_weights = ctw
        cpm_live.compute_target_weights = ctw
        try:
            art = BD.build_artifacts(bpanel, ndx_panel, bstart, bend, include_records=False)
        finally:
            BD.compute_target_weights = _orig_bd
            cpm_live.compute_target_weights = _orig_cl
        brows[cfg] = blend_metrics(art)
        blend_series[cfg] = art.blend

    out.append(f"\n## BLEND 60/20/20 (clean {bstart.date()}..{bend.date()}) "
               "-- BD.compute_target_weights patched per config; BULL+NDX identical")
    out.append("```")
    out.append(fmt_table(brows, ["Sharpe", "MaxDD", "CAGR"], {"MaxDD", "CAGR"}))
    out.append("```")

    # prove the patch worked: B blend must NOT be bit-identical to A blend
    ba, bb = blend_series["A"], blend_series["B"]
    common = ba.index.intersection(bb.index)
    blend_max_diff = float((ba.loc[common] - bb.loc[common]).abs().max())
    bl, = (blend_series["L"],)
    common_l = ba.index.intersection(bl.index)
    blend_max_diff_l = float((ba.loc[common_l] - bl.loc[common_l]).abs().max())
    out.append("\n### Patch-worked proof (blend daily-return abs diff vs A)")
    out.append("```")
    out.append(f"B blend vs A blend: max |dret| = {blend_max_diff:.3e}  "
               f"-> {'DIFFERENT (patch worked)' if blend_max_diff > 1e-12 else 'IDENTICAL (BUG!)'}")
    out.append(f"L blend vs A blend: max |dret| = {blend_max_diff_l:.3e}  "
               f"-> {'DIFFERENT (patch worked)' if blend_max_diff_l > 1e-12 else 'IDENTICAL (BUG!)'}")
    out.append("```")

    # ---- verdict deltas (clean sleeve) ----
    sc = sleeve_rets["clean"]
    m = {c: full_metrics(sc[c], cash) for c in ORDER}
    out.append("\n## VERDICT (clean sleeve deltas, A = prod)")
    out.append("```")
    for c in ORDER:
        out.append(f"{c}  Sharpe={m[c]['Sharpe']:.4f}  Sortino={m[c]['Sortino']:.4f}  "
                   f"MaxDD={m[c]['MaxDD']*100:.2f}%  Calmar={m[c]['Calmar']:.4f}  "
                   f"CAGR={m[c]['CAGR']*100:.2f}%  vol={m[c]['vol']*100:.2f}%")
    out.append("")
    for c in ("L", "B"):
        out.append(f"{c}-A: dSharpe={m[c]['Sharpe']-m['A']['Sharpe']:+.4f}  "
                   f"dMaxDD={(m[c]['MaxDD']-m['A']['MaxDD'])*100:+.2f}pp  "
                   f"dCAGR={(m[c]['CAGR']-m['A']['CAGR'])*100:+.2f}pp  "
                   f"dCalmar={m[c]['Calmar']-m['A']['Calmar']:+.4f}")
    out.append("")
    out.append("Blend deltas vs A:")
    for c in ("L", "B"):
        out.append(f"{c}-A blend: dSharpe={brows[c]['Sharpe']-brows['A']['Sharpe']:+.4f}  "
                   f"dMaxDD={(brows[c]['MaxDD']-brows['A']['MaxDD'])*100:+.2f}pp  "
                   f"dCAGR={(brows[c]['CAGR']-brows['A']['CAGR'])*100:+.2f}pp")
    out.append("```")

    report = "\n".join(out)
    print("\n" + report)
    rp = ROOT / "research" / "cpm_LB_topk5_droptosafe_2026_06_02_raw.txt"
    rp.write_text(report)
    print(f"\n[written] {rp}")


if __name__ == "__main__":
    main()
