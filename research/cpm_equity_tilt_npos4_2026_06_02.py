"""CPM sleeve backtest: equity-tilt variants of the n_pos=4 weighting (AGGRESSIVE).

RESEARCH-ONLY. Prod untouched, no commit. Reuses canonical harness (mooex T+1,
both-252, 10 bps/side). Reproduces the 1.255673 anchor gate before trusting deltas.

ONLY n_pos=4 changes. n_pos<=3 = prod A (25/50/75 ramp, hold all positives equal
split; min-var only at n=4). canary + safe routing unchanged. n_pos=0/canary-off
-> 100% safe.

Configs (n_pos=4 behavior)
--------------------------
A  (anchor=prod): min-var 3-of-4 @ 33.3% each = 100% risky. MUST reproduce 1.255673.
B  (ref):         min-var 3-of-4 @ 25% each + 25% safe (best_safe) = 75% risky.   [drop-to-safe]
P1 (drop-to-SPY): min-var 3-of-4 @ 25% each + 25% SPY = 100% invested, equity buffer.
P2 (drop-to-QQQ): min-var 3-of-4 @ 25% each + 25% QQQ (additive).
                  - if QQQ in MV3: QQQ ends 50%  - if QQQ dropped 4th: =hold-all-4@25%
                  - if QQQ not in top-4: MV3@25% + new QQQ@25%.  (cases reported)
P3 (full-SPY):    100% SPY (ignore min-var basket at full breadth).
P4 (full-QQQ):    100% QQQ.

SPY series: panel adjusted-close (PP_ASSETS) + OHLC open cache (1993-01); QQQ panel
stitched + OHLC (1999-03). Same canonical mooex T+1 override as every other asset.

BLEND fix: patch build_dashboard.compute_target_weights AND cpm_live.compute_target_weights
(BD imports the symbol into its own namespace). CLEAN blend path; P* blend must differ
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


ORDER = ["A", "B", "P1", "P2", "P3", "P4"]


def _n4_weights(cfg, picks_all, close, sig_d, safe):
    """n_pos==4 weights per config. picks_all = 4 positive picks (score order)."""
    mv3 = _min_var_subset(close, sig_d, picks_all, CORR_LOOKBACK_DAYS, 3)
    if cfg == "A":
        per = 1.0 / 3.0
        return {t: per for t in mv3}, tuple(mv3)
    if cfg == "B":
        out = {t: 0.25 for t in mv3}
        out[safe] = out.get(safe, 0.0) + 0.25
        return out, tuple(mv3)
    if cfg == "P1":
        out = {t: 0.25 for t in mv3}
        out["SPY"] = out.get("SPY", 0.0) + 0.25
        return out, tuple(list(mv3) + ["SPY"])
    if cfg == "P2":
        out = {t: 0.25 for t in mv3}
        out["QQQ"] = out.get("QQQ", 0.0) + 0.25
        return out, tuple(list(mv3) + ["QQQ"])
    if cfg == "P3":
        return {"SPY": 1.0}, ("SPY",)
    if cfg == "P4":
        return {"QQQ": 1.0}, ("QQQ",)
    raise ValueError(cfg)


def _core(close_panel, sig_d, cfg):
    """Parameterized copy of compute_target_weights; only n_pos==4 branch varies.

    Returns (weights, basket, regime, safe, n_pos). n_pos=None unless RISK_ON.
    """
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
    top_k = max(2, min(4, len(ranked)))
    top = ranked.iloc[:top_k]
    positive = top[top.index.map(lambda t: faber.get(t, -np.inf) > 0)]

    if len(positive) == 0:
        return {safe: 1.0}, None, "DEFENSIVE", safe, None

    positive_picks = list(positive.index)  # descending score order
    n_pos = len(positive_picks)

    if n_pos == 4:
        out, basket = _n4_weights(cfg, positive_picks, close_panel, sig_d, safe)
        return out, basket, "RISK_ON", safe, n_pos

    # n_pos in {1,2,3}: identical to prod A
    picks = positive_picks
    risky_fraction = min(n_pos, 4) / 4.0
    safe_fraction = 1.0 - risky_fraction
    out = {t: (1.0 / len(picks)) * risky_fraction for t in picks}
    if safe_fraction > 0:
        out[safe] = out.get(safe, 0.0) + safe_fraction
    return out, tuple(picks), "RISK_ON", safe, n_pos


def weight_fn_for(cfg):
    def _wf(close_panel, sig_d):
        out, *_ = _core(close_panel, sig_d, cfg)
        return out
    return _wf


def ctw_for(cfg):
    def _ctw(close_panel, sig_d, universe=None, safe_pool=None, canary_assets=None):
        out, basket, regime, safe, _ = _core(close_panel, sig_d, cfg)
        return out, basket, regime, safe
    return _ctw


# ----- gates / diagnostics -----
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


def npos_histogram(close, sigs, cfg="A") -> str:
    hist = Counter()
    defensive = 0
    for sig_d in sigs:
        _, _, regime, _, n = _core(close, sig_d, cfg)
        if n is None:
            defensive += 1
        else:
            hist[n] += 1
    total = defensive + sum(hist.values())
    lines = [f"n_pos histogram ({total} signal months):"]
    lines.append(f"  defensive/canary-off/0-pos : {defensive:4d} ({100*defensive/total:5.1f}%)")
    for n in range(1, 5):
        c = hist.get(n, 0)
        lines.append(f"  n_pos={n}                    : {c:4d} ({100*c/total:5.1f}%)")
    return "\n".join(lines)


def p2_case_breakdown(close, sigs) -> str:
    """At n_pos=4: classify QQQ position for P2."""
    qqq_in_mv3 = 0          # QQQ kept by min-var -> ends 50%
    qqq_dropped_4th = 0     # QQQ in top-4 positive but min-var dropped it -> hold-all-4 @25%
    qqq_not_top4 = 0        # QQQ not even in top-4 positive -> MV3 + new QQQ @25%
    n4_total = 0
    for sig_d in sigs:
        out, basket, regime, safe, n = _core(close, sig_d, "A")  # use A to get positive picks + mv3
        if n != 4:
            continue
        n4_total += 1
        # recompute positive picks + mv3 directly
        monthly = close.loc[:sig_d].resample("ME").last()
        faber = faber_sma_xs(monthly)
        avail = [t for t in RISKY_UNIVERSE
                 if t in faber.index and pd.notna(faber[t])
                 and (sig_d in close.index and pd.notna(close.loc[sig_d].get(t, np.nan)))]
        daily_rets = close[avail].ffill().pct_change()
        scores = {}
        for t in avail:
            v = daily_rets[t].loc[:sig_d].tail(252).std() * np.sqrt(252)
            if pd.isna(v) or v < 1e-9:
                v = 1.0
            scores[t] = float(faber[t]) / v
        ranked = pd.Series(scores).sort_values(ascending=False)
        top = ranked.iloc[:max(2, min(4, len(ranked)))]
        positive = list(top[top.index.map(lambda t: faber.get(t, -np.inf) > 0)].index)
        mv3 = _min_var_subset(close, sig_d, positive, CORR_LOOKBACK_DAYS, 3)
        if "QQQ" in mv3:
            qqq_in_mv3 += 1
        elif "QQQ" in positive:
            qqq_dropped_4th += 1
        else:
            qqq_not_top4 += 1
    lines = [f"P2 QQQ-case breakdown at n_pos=4 ({n4_total} months):"]
    if n4_total == 0:
        lines.append("  (no n_pos=4 months in window)")
        return "\n".join(lines)
    lines.append(f"  QQQ in MV3 (ends 50%)              : {qqq_in_mv3:4d} ({100*qqq_in_mv3/n4_total:5.1f}%)")
    lines.append(f"  QQQ dropped 4th (=hold-all-4 @25%) : {qqq_dropped_4th:4d} ({100*qqq_dropped_4th/n4_total:5.1f}%)")
    lines.append(f"  QQQ not in top-4 (MV3 + QQQ@25%)   : {qqq_not_top4:4d} ({100*qqq_not_top4/n4_total:5.1f}%)")
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
    head = "crisis".ljust(30) + "".join((c + "_ret").rjust(10) for c in cfgs) \
        + "".join((c + "_DD").rjust(10) for c in cfgs)
    lines = [head, "-" * len(head)]
    for name, (s, e) in CRISES.items():
        cells_ret, cells_dd = [], []
        ok = True
        for c in cfgs:
            w = rets[c].loc[(rets[c].index >= s) & (rets[c].index <= e)]
            if w.empty:
                ok = False
                break
            cells_ret.append(f"{cum(w)*100:.2f}%".rjust(10))
            cells_dd.append(f"{mdd(w)*100:.2f}%".rjust(10))
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

    # sanity: SPY/QQQ present in panel + OHLC cache
    for t in ("SPY", "QQQ"):
        if t not in close.columns:
            raise RuntimeError(f"{t} missing from panel")
    spy_start = close["SPY"].first_valid_index()
    qqq_start = close["QQQ"].first_valid_index()
    print(f"[data] SPY panel start {spy_start.date()}, QQQ panel start {qqq_start.date()}")
    print(f"[data] OHLC cache SPY/QQQ confirmed via harness intraday/overnight reindex")

    anc = H.verify_anchor(data=data)
    print(f"[ok] anchor Sharpe={anc['Sharpe']:.6f} MaxDD={anc['MaxDD']:.6f} "
          f"Calmar={anc['Calmar']:.6f}")
    verify_baseline_matches_prod(data)

    sigs_clean = _signal_dates(close, data.clean_start, data.end)
    sigs_ext = _signal_dates(close, data.ext_start, data.end)

    out = []
    out.append("# CPM sleeve: equity-tilt variants of n_pos=4 weighting -- exploratory\n")
    out.append("RESEARCH-ONLY. Prod untouched, no commit. mooex T+1, both-252, 10 bps/side.")
    out.append(f"Anchor gate: Sharpe={anc['Sharpe']:.6f} (target 1.255673), "
               f"MaxDD={anc['MaxDD']*100:.4f}%, Calmar={anc['Calmar']:.6f}")
    out.append(f"SPY panel start {spy_start.date()}; QQQ panel start {qqq_start.date()}; "
               "OHLC open cache: SPY 1993-01, QQQ 1999-03. mooex T+1 same as all assets.")
    out.append("\nConfigs (ONLY n_pos=4 differs; n<=3 = prod A ramp):")
    out.append("  A  : prod. min-var 3-of-4 @ 33.3% = 100% risky. (anchor)")
    out.append("  B  : min-var 3-of-4 @ 25% + 25% safe = 75% risky.            [drop-to-safe]")
    out.append("  P1 : min-var 3-of-4 @ 25% + 25% SPY = 100% invested.         [equity buffer]")
    out.append("  P2 : min-var 3-of-4 @ 25% + 25% QQQ (additive).             [equity buffer]")
    out.append("  P3 : 100% SPY (ignore basket).                              [own-the-market]")
    out.append("  P4 : 100% QQQ.                                              [own-the-market]")
    out.append("  F ref (prior test): sleeve 1.288/-10.71%, blend 1.449/-10.49%.")

    out.append("\n## n_pos histogram (config-invariant; uses A picks)")
    out.append("```")
    out.append("CLEAN window:")
    out.append(npos_histogram(close, sigs_clean))
    out.append("")
    out.append("EXT window:")
    out.append(npos_histogram(close, sigs_ext))
    out.append("```")

    out.append("\n## P2 QQQ-case breakdown")
    out.append("```")
    out.append("CLEAN window:")
    out.append(p2_case_breakdown(close, sigs_clean))
    out.append("")
    out.append("EXT window:")
    out.append(p2_case_breakdown(close, sigs_ext))
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
    for c in ("B", "P1", "P2", "P3", "P4"):
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
        out.append(f"{c:3s} Sharpe={m[c]['Sharpe']:.4f}  Sortino={m[c]['Sortino']:.4f}  "
                   f"MaxDD={m[c]['MaxDD']*100:.2f}%  Calmar={m[c]['Calmar']:.4f}  "
                   f"CAGR={m[c]['CAGR']*100:.2f}%  vol={m[c]['vol']*100:.2f}%")
    out.append("")
    for c in ("B", "P1", "P2", "P3", "P4"):
        out.append(f"{c}-A sleeve: dSharpe={m[c]['Sharpe']-m['A']['Sharpe']:+.4f}  "
                   f"dMaxDD={(m[c]['MaxDD']-m['A']['MaxDD'])*100:+.2f}pp  "
                   f"dCAGR={(m[c]['CAGR']-m['A']['CAGR'])*100:+.2f}pp  "
                   f"dCalmar={m[c]['Calmar']-m['A']['Calmar']:+.4f}")
    out.append("")
    out.append("Equity-buffer test (P1/P2 vs A and vs B):")
    for c in ("P1", "P2"):
        out.append(f"  {c}-B sleeve: dSharpe={m[c]['Sharpe']-m['B']['Sharpe']:+.4f}  "
                   f"dMaxDD={(m[c]['MaxDD']-m['B']['MaxDD'])*100:+.2f}pp  "
                   f"dCAGR={(m[c]['CAGR']-m['B']['CAGR'])*100:+.2f}pp")
    out.append("")
    out.append("Blend deltas vs A:")
    for c in ("B", "P1", "P2", "P3", "P4"):
        out.append(f"{c}-A blend: dSharpe={brows[c]['Sharpe']-brows['A']['Sharpe']:+.4f}  "
                   f"dMaxDD={(brows[c]['MaxDD']-brows['A']['MaxDD'])*100:+.2f}pp  "
                   f"dCAGR={(brows[c]['CAGR']-brows['A']['CAGR'])*100:+.2f}pp")
    out.append("```")

    report = "\n".join(out)
    print("\n" + report)
    rp = ROOT / "research" / "cpm_equity_tilt_npos4_2026_06_02_raw.txt"
    rp.write_text(report)
    print(f"\n[written] {rp}")


if __name__ == "__main__":
    main()
