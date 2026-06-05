"""CPM sleeve backtest: R -- M5 drop-to-safe ladder with TOP cell swapped to 100% equity.

RESEARCH-ONLY. Prod untouched, no commit. Reuses canonical harness (mooex T+1,
both-252, 10 bps/side). Reproduces the 1.255673 anchor gate before trusting deltas.

THE RULE (R): TOP_K=5 drop-exactly-1 ladder, IDENTICAL to M5 EXCEPT the n_pos=5 cell.
  n_pos=0 / canary-off -> 100% safe
  n_pos=1 -> 0 names     -> 100% safe
  n_pos=2 -> min-var 1-of-2 @25% (=lowest-vol name) + 75% safe
  n_pos=3 -> min-var 2-of-3 @25% (50%) + 50% safe
  n_pos=4 -> min-var 3-of-4 @25% (75%) + 25% safe
  n_pos=5 -> 100% EQUITY (NOT min-var-4):
      R-SPY: 100% SPY
      R-QQQ: 100% QQQ
M5 (ref) held min-var-4 @25% (=100%) at n_pos=5. R isolates JUST the top-cell swap.

Configs
-------
A     (anchor=prod): TOP_K=4, curve 25/50/75/100, min-var 3-of-4 @ 33.3% at n_pos=4,
      equal-split otherwise. MUST reproduce 1.255673.
B     (ref drop-to-safe): TOP_K=4, hold min(n_pos,3) @25% + safe. curve 25/50/75/75.
M5    (ref TOP_K=5): drop-exactly-1, (n-1) min-var @25% + safe. curve 0/25/50/75/100.
R-SPY (TOP_K=5): = M5 but n_pos=5 -> 100% SPY.
R-QQQ (TOP_K=5): = M5 but n_pos=5 -> 100% QQQ.

SPY/QQQ: panel adjusted-close + OHLC open cache (SPY 1993-01, QQQ 1999-03). QQQ is
in RISKY_UNIVERSE; SPY is external. Same canonical mooex T+1 override as all assets.

BLEND fix: patch build_dashboard.compute_target_weights AND cpm_live.compute_target_weights
(BD imports the symbol into its own namespace). CLEAN blend path; R blend must differ
from A blend (proof printed).
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


_CLOSE = {"panel": None}


def _MV(candidates, m):
    return _min_var_subset(_CLOSE["panel"], _MV.sig_d, candidates, CORR_LOOKBACK_DAYS, m)


# ---- selection rules ----
def _select_A(picks, n_pos):
    if n_pos == 4:
        return _MV(picks, 3)
    return list(picks)


def _select_B(picks, n_pos):
    if n_pos == 4:
        return _MV(picks, 3)
    return list(picks)


def _select_M(picks, n_pos):
    # drop exactly 1: hold (n_pos-1) min-var names; <=1 positive -> hold nothing (all safe)
    if n_pos <= 1:
        return []
    return _MV(picks, n_pos - 1)


CONFIGS = {
    "A":     dict(top_k=4, denom=4, weight_mode="equal_split",    select=_select_A, equity_top=None),
    "B":     dict(top_k=4, denom=4, weight_mode="fixed_per_name", select=_select_B, equity_top=None),
    "M5":    dict(top_k=5, denom=4, weight_mode="fixed_per_name", select=_select_M, equity_top=None),
    "R-SPY": dict(top_k=5, denom=4, weight_mode="fixed_per_name", select=_select_M, equity_top="SPY"),
    "R-QQQ": dict(top_k=5, denom=4, weight_mode="fixed_per_name", select=_select_M, equity_top="QQQ"),
}
ORDER = ["A", "B", "M5", "R-SPY", "R-QQQ"]


def _core(close_panel, sig_d, cfg: str):
    """Parameterized copy of compute_target_weights.

    Canary, ranker math, and safe-selector identical to prod; only TOP_K,
    selection rule, weight mode, and the n_pos==5 equity-top override vary.
    Returns (weights, basket, regime, safe, n_pos). n_pos=None unless RISK_ON.
    """
    p = CONFIGS[cfg]
    top_k_cand = p["top_k"]
    denom = p["denom"]
    weight_mode = p["weight_mode"]
    select = p["select"]
    equity_top = p["equity_top"]

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

    # ---- R top-cell override: at max breadth (n_pos == top_k_cand == 5) go 100% equity ----
    if equity_top is not None and n_pos == top_k_cand:
        return {equity_top: 1.0}, (equity_top,), "RISK_ON", safe, n_pos

    picks = select(positive_picks, n_pos)

    if weight_mode == "equal_split":
        risky_fraction = min(n_pos, denom) / float(denom)
        safe_fraction = 1.0 - risky_fraction
        out = {t: (1.0 / len(picks)) * risky_fraction for t in picks} if picks else {}
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

    if not out:
        out = {safe: 1.0}
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


def verify_R_equals_M5_below_n5(close, sigs) -> str:
    """R-SPY/R-QQQ must equal M5 at every n_pos<5; differ only at n_pos=5."""
    lines = ["R vs M5 weight diff by n_pos (expect 0 at n<5, >0 at n=5):"]
    for rcfg in ("R-SPY", "R-QQQ"):
        worst = {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0, 5: 0.0}
        defensive_diff = 0.0
        for sig_d in sigs:
            r_out, _, _, _, n = _core(close, sig_d, rcfg)
            m_out, _, _, _, _ = _core(close, sig_d, "M5")
            d = max(abs(r_out.get(k, 0.0) - m_out.get(k, 0.0)) for k in set(r_out) | set(m_out))
            if n is None:
                defensive_diff = max(defensive_diff, d)
            else:
                worst[n] = max(worst[n], d)
        lines.append(f"  {rcfg}: defensive={defensive_diff:.2e}  n1={worst[1]:.2e}  "
                     f"n2={worst[2]:.2e}  n3={worst[3]:.2e}  n4={worst[4]:.2e}  "
                     f"n5={worst[5]:.2e}")
    return "\n".join(lines)


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
    nmax = 5 if CONFIGS[cfg]["top_k"] == 5 else 4
    for n in range(1, nmax + 1):
        c = hist.get(n, 0)
        lines.append(f"  n_pos={n}                    : {c:4d} ({100*c/total:5.1f}%)")
    if CONFIGS[cfg]["top_k"] == 5:
        n5 = hist.get(5, 0)
        lines.append(f"  -> n_pos=5 fires {n5} months ({100*n5/total:.1f}% of months) -- "
                     f"these get 100% equity under R")
    return "\n".join(lines)


def n5_sample_months(close, sigs, cfg, k=6) -> str:
    """List a few n_pos=5 months and confirm they hold 100% equity under R."""
    lines = [f"Sample n_pos=5 months ({cfg}) -- confirm 100% equity hold:"]
    found = 0
    for sig_d in sigs:
        out, basket, regime, safe, n = _core(close, sig_d, cfg)
        if n == 5:
            wtxt = ", ".join(f"{k2}={v2*100:.0f}%" for k2, v2 in sorted(out.items(), key=lambda x: -x[1]))
            lines.append(f"  {sig_d.date()}: {wtxt}")
            found += 1
            if found >= k:
                break
    if found == 0:
        lines.append("  (no n_pos=5 months in window)")
    return "\n".join(lines)


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

    for t in ("SPY", "QQQ"):
        if t not in close.columns:
            raise RuntimeError(f"{t} missing from panel")
    spy_start = close["SPY"].first_valid_index()
    qqq_start = close["QQQ"].first_valid_index()
    print(f"[data] SPY panel start {spy_start.date()}, QQQ panel start {qqq_start.date()}")

    anc = H.verify_anchor(data=data)
    print(f"[ok] anchor Sharpe={anc['Sharpe']:.6f} MaxDD={anc['MaxDD']:.6f} "
          f"Calmar={anc['Calmar']:.6f}")
    verify_baseline_matches_prod(data)

    sigs_clean = _signal_dates(close, data.clean_start, data.end)
    sigs_ext = _signal_dates(close, data.ext_start, data.end)

    out = []
    out.append("# CPM sleeve: R -- M5 ladder with TOP cell (n_pos=5) -> 100% equity -- exploratory\n")
    out.append("RESEARCH-ONLY. Prod untouched, no commit. mooex T+1, both-252, 10 bps/side.")
    out.append(f"Anchor gate: Sharpe={anc['Sharpe']:.6f} (target 1.255673), "
               f"MaxDD={anc['MaxDD']*100:.4f}%, Calmar={anc['Calmar']:.6f}")
    out.append(f"SPY panel start {spy_start.date()}; QQQ panel start {qqq_start.date()}; "
               "OHLC open cache: SPY 1993-01, QQQ 1999-03. mooex T+1 same as all assets.")
    out.append("\nConfigs:")
    out.append("  A     : prod baseline. TOP_K=4, curve 25/50/75/100, min-var 3-of-4 @ 33.3% at n=4.")
    out.append("  B     : ref drop-to-safe. TOP_K=4, hold min(n_pos,3) @25% +safe. curve 25/50/75/75.")
    out.append("  M5    : ref. TOP_K=5 drop-exactly-1, (n-1) min-var @25% +safe. curve 0/25/50/75/100.")
    out.append("  R-SPY : = M5 but n_pos=5 -> 100% SPY (NOT min-var-4 @25%).")
    out.append("  R-QQQ : = M5 but n_pos=5 -> 100% QQQ.")
    out.append("  F ref (prior test): sleeve 1.288/-10.71%, blend 1.449/-10.49%.")
    out.append("  P4 ref (100% QQQ at n=4): -22.77% sleeve MaxDD.")

    out.append("\n## R vs M5 weight identity check (expect identical below n=5, differ at n=5)")
    out.append("```")
    out.append(verify_R_equals_M5_below_n5(close, sigs_clean))
    out.append("```")

    out.append("\n## n_pos histograms")
    out.append("```")
    out.append("CLEAN window:")
    out.append(npos_histogram(close, sigs_clean, "M5"))
    out.append("")
    out.append("EXT window:")
    out.append(npos_histogram(close, sigs_ext, "M5"))
    out.append("```")

    out.append("\n## Sample n_pos=5 months (confirm 100% equity hold under R)")
    out.append("```")
    out.append("CLEAN window:")
    out.append(n5_sample_months(close, sigs_clean, "R-SPY"))
    out.append("")
    out.append(n5_sample_months(close, sigs_clean, "R-QQQ"))
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

    ba = blend_series["A"]
    out.append("\n### Patch-worked proof (blend daily-return abs diff vs A)")
    out.append("```")
    for c in ("B", "M5", "R-SPY", "R-QQQ"):
        bc = blend_series[c]
        common = ba.index.intersection(bc.index)
        d = float((ba.loc[common] - bc.loc[common]).abs().max())
        out.append(f"{c} blend vs A blend: max |dret| = {d:.3e}  "
                   f"-> {'DIFFERENT (patch worked)' if d > 1e-12 else 'IDENTICAL (BUG!)'}")
    out.append("```")

    # ---- verdict deltas (clean sleeve) ----
    sc = sleeve_rets["clean"]
    m = {c: full_metrics(sc[c], cash) for c in ORDER}
    out.append("\n## VERDICT (clean sleeve deltas, A = prod)")
    out.append("```")
    for c in ORDER:
        out.append(f"{c:6s} Sharpe={m[c]['Sharpe']:.4f}  Sortino={m[c]['Sortino']:.4f}  "
                   f"MaxDD={m[c]['MaxDD']*100:.2f}%  Calmar={m[c]['Calmar']:.4f}  "
                   f"CAGR={m[c]['CAGR']*100:.2f}%  vol={m[c]['vol']*100:.2f}%")
    out.append("")
    for c in ("B", "M5", "R-SPY", "R-QQQ"):
        out.append(f"{c}-A sleeve: dSharpe={m[c]['Sharpe']-m['A']['Sharpe']:+.4f}  "
                   f"dMaxDD={(m[c]['MaxDD']-m['A']['MaxDD'])*100:+.2f}pp  "
                   f"dCAGR={(m[c]['CAGR']-m['A']['CAGR'])*100:+.2f}pp  "
                   f"dCalmar={m[c]['Calmar']-m['A']['Calmar']:+.4f}")
    out.append("")
    out.append("R vs M5 (isolates the top-cell swap: full-equity vs diluted min-var-4):")
    for c in ("R-SPY", "R-QQQ"):
        out.append(f"  {c}-M5 sleeve: dSharpe={m[c]['Sharpe']-m['M5']['Sharpe']:+.4f}  "
                   f"dMaxDD={(m[c]['MaxDD']-m['M5']['MaxDD'])*100:+.2f}pp  "
                   f"dCAGR={(m[c]['CAGR']-m['M5']['CAGR'])*100:+.2f}pp  "
                   f"dCalmar={m[c]['Calmar']-m['M5']['Calmar']:+.4f}")
    out.append("")
    out.append("SPY vs QQQ at n=5 (which is less bad):")
    out.append(f"  R-QQQ - R-SPY sleeve: dSharpe={m['R-QQQ']['Sharpe']-m['R-SPY']['Sharpe']:+.4f}  "
               f"dMaxDD={(m['R-QQQ']['MaxDD']-m['R-SPY']['MaxDD'])*100:+.2f}pp  "
               f"dCAGR={(m['R-QQQ']['CAGR']-m['R-SPY']['CAGR'])*100:+.2f}pp")
    out.append("")
    out.append("Blend deltas vs A:")
    for c in ("B", "M5", "R-SPY", "R-QQQ"):
        out.append(f"{c}-A blend: dSharpe={brows[c]['Sharpe']-brows['A']['Sharpe']:+.4f}  "
                   f"dMaxDD={(brows[c]['MaxDD']-brows['A']['MaxDD'])*100:+.2f}pp  "
                   f"dCAGR={(brows[c]['CAGR']-brows['A']['CAGR'])*100:+.2f}pp")
    out.append("```")

    report = "\n".join(out)
    print("\n" + report)
    rp = ROOT / "research" / "cpm_R_equity_top5_2026_06_02_raw.txt"
    rp.write_text(report)
    print(f"\n[written] {rp}")


if __name__ == "__main__":
    main()
