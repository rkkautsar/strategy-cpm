"""CPM sleeve backtest: N -- "no breadth ramp" (binary canary -> full-invest).

RESEARCH-ONLY. Prod untouched, no commit. Reuses canonical harness (mooex T+1,
both-252, 10 bps/side). Reproduces the 1.255673 anchor gate before trusting deltas.

THE RULE (N): canary unchanged. When risk-on (TIP 13612U > 0), ALWAYS be 100%
invested -- no n_pos/4 partial-safe scaling. Apply faber>0 filter to top-4 as prod;
among positives select min-var 3-of-4 at n_pos=4 (same as prod), else hold ALL
positives; weight held names EQUALLY to sum to 100% (1/n_held). No safe buffer
when risk-on.
  TIP 13612U <= 0 / canary-off    -> 100% safe (best_safe)
  n_pos=0 while canary-on (degen) -> 100% safe
  n_pos=1 -> 1 name  @ 100%
  n_pos=2 -> 2 names @ 50%
  n_pos=3 -> 3 names @ 33.3%
  n_pos=4 -> min-var-3-of-4 @ 33.3% (= 100%)  [bit-identical to A]
Exposure always 100% when canary-on & >=1 positive; breadth changes name count only.

Configs
-------
A  (anchor = prod): TOP_K=4, ramp curve 25/50/75/100, min-var 3-of-4 @ 33.3% at
   n_pos=4, equal-split of risky_fraction otherwise. MUST reproduce 1.255673.
N  (RULE): TOP_K=4, full-invest curve 100/100/100/100, equal-weight 1/n_held.
F  (reference only, not re-run here): exposure 0/0/50/100, sleeve 1.288/-10.71%.

BLEND fix: patch build_dashboard.compute_target_weights (BD imports the symbol
into its OWN namespace). Patch both for safety. CLEAN blend path; confirm N blend
!= A so patch worked.
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
    # prod: min-var 3-of-4 at n=4, else hold all positives
    if n_pos == 4:
        return _MV(picks, 3)
    return list(picks)


# N uses the SAME selection as A (min-var-3 at n=4, else all). Only weighting
# (full-invest, no safe buffer) differs.
_select_N = _select_A


CONFIGS = {
    "A": dict(top_k=4, denom=4, weight_mode="equal_split", select=_select_A),
    "N": dict(top_k=4, denom=4, weight_mode="equal_full",  select=_select_N),
}
ORDER = ["A", "N"]


def _core(close_panel, sig_d, cfg: str):
    """Parameterized copy of compute_target_weights.

    Canary, ranker math, and safe-selector identical to prod; only the weight
    mode (ramp vs full-invest) and selection rule vary by config.
    Returns (weights, basket, regime, safe, n_pos). n_pos=None unless RISK_ON.
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
        # canary-on but no positives (degenerate) -> 100% safe
        return {safe: 1.0}, None, "DEFENSIVE", safe, None

    positive_picks = list(positive.index)  # descending score order
    n_pos = len(positive_picks)
    picks = select(positive_picks, n_pos)

    if weight_mode == "equal_split":
        # A: ramp -- risky_fraction = min(n_pos, denom)/denom; rest -> safe
        risky_fraction = min(n_pos, denom) / float(denom)
        safe_fraction = 1.0 - risky_fraction
        out = {t: (1.0 / len(picks)) * risky_fraction for t in picks} if picks else {}
        if safe_fraction > 1e-15:
            out[safe] = out.get(safe, 0.0) + safe_fraction
    elif weight_mode == "equal_full":
        # N: no ramp -- full-invest, equal weight 1/n_held, no safe buffer
        out = {t: 1.0 / len(picks) for t in picks} if picks else {safe: 1.0}
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


def verify_N_vs_A(close, sigs) -> str:
    """N must equal A at n_pos=4 (both min-var 3-of-4 @ 33.3% = 100%); differ at
    n_pos in {1,2,3} (N=100% vs A 25/50/75). Defensive/n0 unchanged."""
    worst = {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0}
    defensive_diff = 0.0
    for sig_d in sigs:
        n_out, _, _, _, n = _core(close, sig_d, "N")
        a_out, _, _, _, _ = _core(close, sig_d, "A")
        d = max(abs(n_out.get(k, 0.0) - a_out.get(k, 0.0)) for k in set(n_out) | set(a_out))
        if n is None:
            defensive_diff = max(defensive_diff, d)
        else:
            worst[n] = max(worst[n], d)
    lines = ["N vs A weight diff by n_pos (expect 0 at n=4 & defensive; >0 at n=1,2,3):"]
    lines.append(f"  defensive/n0={defensive_diff:.2e}  n1={worst[1]:.2e}  n2={worst[2]:.2e}  "
                 f"n3={worst[3]:.2e}  n4={worst[4]:.2e}")
    ok4 = worst[4] < 1e-12
    ok_lo = min(worst[1], worst[2], worst[3]) > 1e-9 if any(worst[k] for k in (1, 2, 3)) else True
    lines.append(f"  -> n4 bit-identical: {'YES' if ok4 else 'NO (BUG)'};  "
                 f"n1/2/3 differ: {'YES' if ok_lo else '(some n missing in window)'}")
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
    for n in range(1, 5):
        c = hist.get(n, 0)
        lines.append(f"  n_pos={n}                    : {c:4d} ({100*c/total:5.1f}%)")
    return "\n".join(lines)


def npos1_concentration(close, sigs, cfg) -> str:
    """List every n_pos=1 month and the single asset that gets 100% under cfg."""
    rows = []
    for sig_d in sigs:
        out, basket, regime, safe, n = _core(close, sig_d, cfg)
        if n == 1:
            # the single held name
            asset = basket[0] if basket else "?"
            w = out.get(asset, float("nan"))
            rows.append((sig_d.date(), asset, w))
    lines = [f"n_pos=1 single-name-100% months ({cfg}): {len(rows)} total"]
    if not rows:
        lines.append("  (none)")
        return "\n".join(lines)
    cnt = Counter(a for _, a, _ in rows)
    lines.append("  asset -> count (which single name carries 100% exposure):")
    for a, c in cnt.most_common():
        lines.append(f"    {a:5s} : {c}")
    lines.append("  month-by-month (date, asset, weight):")
    for dt, a, w in rows:
        lines.append(f"    {dt}  {a:5s}  {w*100:.1f}%")
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

    anc = H.verify_anchor(data=data)
    print(f"[ok] anchor Sharpe={anc['Sharpe']:.6f} MaxDD={anc['MaxDD']:.6f} "
          f"Calmar={anc['Calmar']:.6f}")
    verify_baseline_matches_prod(data)

    sigs_clean = _signal_dates(close, data.clean_start, data.end)
    sigs_ext = _signal_dates(close, data.ext_start, data.end)

    out = []
    out.append("# CPM sleeve: N -- 'no breadth ramp' (binary canary -> full-invest) -- exploratory\n")
    out.append("RESEARCH-ONLY. Prod untouched, no commit. mooex T+1, both-252, 10 bps/side.")
    out.append(f"Anchor gate: Sharpe={anc['Sharpe']:.6f} (target 1.255673), "
               f"MaxDD={anc['MaxDD']*100:.4f}%, Calmar={anc['Calmar']:.6f}")
    out.append("\nConfigs:")
    out.append("  A : prod baseline. TOP_K=4, ramp 25/50/75/100, min-var 3-of-4 @ 33.3% at n=4.")
    out.append("  N : RULE. TOP_K=4, NO ramp -- full-invest 100% when risk-on, equal 1/n_held.")
    out.append("      n1->1@100% n2->2@50% n3->3@33.3% n4->min-var-3@33.3%(=A). n0/off->100% safe.")
    out.append("  F : reference only (not re-run): exposure 0/0/50/100, sleeve 1.288/-10.71%.")

    out.append("\n## N vs A weight identity check (clean window)")
    out.append("```")
    out.append(verify_N_vs_A(close, sigs_clean))
    out.append("```")

    out.append("\n## n_pos histograms")
    out.append("```")
    out.append("CLEAN window:")
    out.append(npos_histogram(close, sigs_clean, "N"))
    out.append("")
    out.append("EXT window:")
    out.append(npos_histogram(close, sigs_ext, "N"))
    out.append("```")

    out.append("\n## n_pos=1 concentration tail (single name @ 100% under N)")
    out.append("```")
    out.append("CLEAN window:")
    out.append(npos1_concentration(close, sigs_clean, "N"))
    out.append("")
    out.append("EXT window:")
    out.append(npos1_concentration(close, sigs_ext, "N"))
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

    # prove the patch worked: N blend must NOT be bit-identical to A blend
    ba = blend_series["A"]
    out.append("\n### Patch-worked proof (blend daily-return abs diff vs A)")
    out.append("```")
    for c in ("N",):
        bc = blend_series[c]
        common = ba.index.intersection(bc.index)
        d = float((ba.loc[common] - bc.loc[common]).abs().max())
        out.append(f"{c} blend vs A blend: max |dret| = {d:.3e}  "
                   f"-> {'DIFFERENT (patch worked)' if d > 1e-12 else 'IDENTICAL (BUG!)'}")
    out.append("```")

    # ---- verdict deltas ----
    sc = sleeve_rets["clean"]
    se = sleeve_rets["ext"]
    mc = {c: full_metrics(sc[c], cash) for c in ORDER}
    me = {c: full_metrics(se[c], cash) for c in ORDER}
    out.append("\n## VERDICT (sleeve deltas, A = prod)")
    out.append("```")
    out.append("CLEAN sleeve:")
    for c in ORDER:
        out.append(f"  {c} Sharpe={mc[c]['Sharpe']:.4f}  Sortino={mc[c]['Sortino']:.4f}  "
                   f"MaxDD={mc[c]['MaxDD']*100:.2f}%  Calmar={mc[c]['Calmar']:.4f}  "
                   f"CAGR={mc[c]['CAGR']*100:.2f}%  vol={mc[c]['vol']*100:.2f}%")
    out.append(f"  N-A clean: dSharpe={mc['N']['Sharpe']-mc['A']['Sharpe']:+.4f}  "
               f"dMaxDD={(mc['N']['MaxDD']-mc['A']['MaxDD'])*100:+.2f}pp  "
               f"dCAGR={(mc['N']['CAGR']-mc['A']['CAGR'])*100:+.2f}pp  "
               f"dCalmar={mc['N']['Calmar']-mc['A']['Calmar']:+.4f}")
    out.append("EXT sleeve:")
    for c in ORDER:
        out.append(f"  {c} Sharpe={me[c]['Sharpe']:.4f}  MaxDD={me[c]['MaxDD']*100:.2f}%  "
                   f"Calmar={me[c]['Calmar']:.4f}  CAGR={me[c]['CAGR']*100:.2f}%")
    out.append(f"  N-A ext: dSharpe={me['N']['Sharpe']-me['A']['Sharpe']:+.4f}  "
               f"dMaxDD={(me['N']['MaxDD']-me['A']['MaxDD'])*100:+.2f}pp  "
               f"dCAGR={(me['N']['CAGR']-me['A']['CAGR'])*100:+.2f}pp")
    out.append("Blend deltas vs A:")
    out.append(f"  N-A blend: dSharpe={brows['N']['Sharpe']-brows['A']['Sharpe']:+.4f}  "
               f"dMaxDD={(brows['N']['MaxDD']-brows['A']['MaxDD'])*100:+.2f}pp  "
               f"dCAGR={(brows['N']['CAGR']-brows['A']['CAGR'])*100:+.2f}pp")
    out.append("```")

    report = "\n".join(out)
    print("\n" + report)
    rp = ROOT / "research" / "cpm_N_noramp_2026_06_02_raw.txt"
    rp.write_text(report)
    print(f"\n[written] {rp}")


if __name__ == "__main__":
    main()
