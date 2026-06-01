#!/usr/bin/env python3
"""Convex (KMLM managed-futures) defensive-leg study.

Tests whether replacing/augmenting the shared SHV/IEF defensive leg with a
managed-futures trend sleeve (KMLM) makes the safe leg CONVEX (profits in
sustained crashes = crisis alpha), reducing blend drawdown and adding crisis
return -- vs the current SHV/IEF-only defense.

Variants (applied to the SHARED safe selection unless noted):
  D0 (PROD): best_safe = argmax 13612U over {SHV, IEF}
  D1: best_safe = argmax 13612U over {SHV, IEF, KMLM}   (KMLM competes via momentum)
  D2: defensive = 50% best_safe(SHV/IEF) + 50% KMLM      (fixed convex slice)
  D3: defensive = 100% KMLM                               (pure crisis-alpha defense)
  D4: D2-style convex defense ONLY on BULL sleeve safe (CPM keeps SHV/IEF; NDX
      inherits BULL's safe selector -> also convex)

Measurement only. No production file is edited. KMLM history uses a STITCHED
managed-futures proxy (KFA-MLM index 1988-2020 + live KMLM ETF 2020+); flag the
proxy clearly.

Run: PYTHONPATH=. .venv/bin/python research/bull_kmlm_convex_safe.py
"""
from __future__ import annotations

import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import cpm_live
import bull_spy_live
import ndx_sleeve_live
from cpm_live import load_panel, perf_metrics, run_cpm_backtest
from bull_spy_live import run_bull_spy_backtest
from ndx_sleeve_live import load_ndx_panel, run_ndx_backtest
from build_dashboard import build_artifacts, CPM_W, BULL_W, NDX_W

KMLM_STITCH = ROOT / "data" / "kmlm_stitched_daily.csv"
CLEAN_START = pd.Timestamp("2008-05-30")
STRESS_START = pd.Timestamp("1999-03-10")
END = pd.Timestamp("2026-05-22")

# Crisis episodes (calendar slices for the crisis-alpha check)
CRISES = {
    "2008": (pd.Timestamp("2008-01-01"), pd.Timestamp("2008-12-31")),
    "2020": (pd.Timestamp("2020-01-01"), pd.Timestamp("2020-12-31")),
    "2022": (pd.Timestamp("2022-01-01"), pd.Timestamp("2022-12-31")),
}

# Save originals for restore
_ORIG = {
    "cpm_best_safe": cpm_live.best_safe,
    "cpm_safe_pool": list(cpm_live.SAFE_POOL),
    "bull_pick_safe": bull_spy_live._pick_safe,
    "bull_safe_pool": list(bull_spy_live.SAFE_POOL),
    "ndx_pick_safe": ndx_sleeve_live._pick_safe,
}


def restore():
    cpm_live.best_safe = _ORIG["cpm_best_safe"]
    cpm_live.SAFE_POOL = list(_ORIG["cpm_safe_pool"])
    bull_spy_live._pick_safe = _ORIG["bull_pick_safe"]
    bull_spy_live.SAFE_POOL = list(_ORIG["bull_safe_pool"])
    ndx_sleeve_live._pick_safe = _ORIG["ndx_pick_safe"]


def _safe_13612(sub: pd.DataFrame, pool: list[str]) -> str:
    """Replicate best-of-safe(SHV/IEF) by 13612U on a monthly frame."""
    avail = [s for s in pool if s in sub.columns and sub[s].first_valid_index() is not None]
    if not avail:
        return "SHV"
    if len(sub) < 13:
        return avail[0]
    best_t, best_m = avail[0], -np.inf
    for t in avail:
        s = sub[t].dropna()
        if len(s) < 13:
            continue
        r1 = float(s.iloc[-1] / s.iloc[-2] - 1)
        r3 = float(s.iloc[-1] / s.iloc[-4] - 1)
        r6 = float(s.iloc[-1] / s.iloc[-7] - 1)
        r12 = float(s.iloc[-1] / s.iloc[-13] - 1)
        m = (r1 + r3 + r6 + r12) / 4
        if m > best_m:
            best_m, best_t = m, t
    return best_t


def build_panel():
    """Load PROD panel, overwrite KMLM with the stitched managed-futures proxy."""
    panel = load_panel(start=pd.Timestamp("1995-01-01"), end=END)
    kmlm = pd.read_csv(KMLM_STITCH, parse_dates=[0], index_col=0).iloc[:, 0]
    kmlm.name = "KMLM"
    # Reindex stitched KMLM onto panel trading days, ffill (piecewise pre-ETF).
    panel = panel.drop(columns=[c for c in ["KMLM"] if c in panel.columns])
    panel = panel.join(kmlm.reindex(panel.index, method="ffill").to_frame("KMLM"))
    return panel


def add_smix(panel: pd.DataFrame, name: str = "SMIX50") -> pd.DataFrame:
    """Add synthetic safe column = monthly-rebalanced 50% best(SHV/IEF) + 50% KMLM.

    The SHV/IEF leg follows the SAME monthly 13612U best-of-safe decision used
    in PROD, so the synthetic captures the time-varying short/intermediate
    duration choice. 50/50 weights reset each month (within-month drift left as
    a minor approximation vs daily rebalancing -- see caveat).
    """
    rets = panel.ffill().pct_change()
    sig = (pd.DataFrame({"x": 1}, index=panel.index)
           .groupby(pd.Grouper(freq="ME")).tail(1).index)
    out = pd.Series(0.0, index=panel.index)
    last = panel.index[-1] + pd.Timedelta(days=1)
    for i, sd in enumerate(sig):
        sub = panel.loc[:sd].resample("ME").last()
        choice = _safe_13612(sub, ["SHV", "IEF"])
        future = panel.index[panel.index > sd]
        if len(future) < 1:
            continue
        af = future[0]
        if i + 1 < len(sig):
            nf = panel.index[panel.index > sig[i + 1]]
            ea = nf[0] if len(nf) >= 1 else last
        else:
            ea = last
        mask = (panel.index >= af) & (panel.index < ea)
        out.loc[mask] = (0.5 * rets.loc[mask, choice].fillna(0.0)
                         + 0.5 * rets.loc[mask, "KMLM"].fillna(0.0))
    price = (1.0 + out).cumprod() * 100.0
    panel = panel.copy()
    panel[name] = price
    return panel


def apply_variant(variant: str, panel: pd.DataFrame) -> pd.DataFrame:
    """Patch shared safe selection for the variant. Returns possibly-augmented panel."""
    restore()
    if variant == "D0":
        return panel
    if variant == "D1":
        cpm_live.SAFE_POOL = ["SHV", "IEF", "KMLM"]
        bull_spy_live.SAFE_POOL = ["SHV", "IEF", "KMLM"]
        return panel
    if variant == "D2":
        panel = add_smix(panel)
        cpm_live.SAFE_POOL = ["SHV", "IEF", "SMIX50"]
        bull_spy_live.SAFE_POOL = ["SHV", "IEF", "SMIX50"]
        cpm_live.best_safe = lambda monthly, sig_d, safe_pool: "SMIX50"
        bull_spy_live._pick_safe = lambda monthly: "SMIX50"
        ndx_sleeve_live._pick_safe = lambda monthly: "SMIX50"
        return panel
    if variant == "D3":
        cpm_live.SAFE_POOL = ["SHV", "IEF", "KMLM"]
        bull_spy_live.SAFE_POOL = ["SHV", "IEF", "KMLM"]
        cpm_live.best_safe = lambda monthly, sig_d, safe_pool: "KMLM"
        bull_spy_live._pick_safe = lambda monthly: "KMLM"
        ndx_sleeve_live._pick_safe = lambda monthly: "KMLM"
        return panel
    if variant == "D4":
        panel = add_smix(panel)
        # CPM keeps SHV/IEF (best_safe untouched). BULL + NDX get convex safe.
        bull_spy_live.SAFE_POOL = ["SHV", "IEF", "SMIX50"]
        bull_spy_live._pick_safe = lambda monthly: "SMIX50"
        ndx_sleeve_live._pick_safe = lambda monthly: "SMIX50"
        return panel
    raise ValueError(variant)


def metrics_row(daily: pd.Series, cash: pd.Series, turnover: float | None = None) -> dict:
    m = perf_metrics(daily, cash)
    return {
        "sharpe": m.get("sharpe", float("nan")),
        "excess_sharpe": m.get("excess_sharpe", float("nan")),
        "cagr": m.get("cagr", float("nan")),
        "vol": m.get("vol", float("nan")),
        "maxdd": m.get("max_drawdown", float("nan")),
        "calmar": m.get("calmar", float("nan")),
        "turnover": turnover if turnover is not None else float("nan"),
    }


def blend_turnover(panel, ndx_panel, start, end) -> float:
    """Annualized one-way blend turnover from monthly sleeve target weights."""
    _, cpm_hist = run_cpm_backtest(panel, start, end)
    _, ndx_hist = run_ndx_backtest(panel, ndx_panel, start, end)
    sig = (pd.DataFrame({"x": 1}, index=panel.index)
           .groupby(pd.Grouper(freq="ME")).tail(1).index)
    sig = [d for d in sig if start <= d <= end]
    cpm_by = {h["sig_d"]: h["weights"] for h in cpm_hist}
    ndx_by = {h["sig_d"]: h["weights"] for h in ndx_hist}
    prev = {}
    tos = []
    for sd in sig:
        bw, _, _ = bull_spy_live.compute_bull_spy_weights(panel, sd, panel["SPY"])
        cw = cpm_by.get(sd, {})
        nw = ndx_by.get(sd, {})
        blend = {}
        for k, v in cw.items():
            blend[k] = blend.get(k, 0.0) + CPM_W * v
        for k, v in bw.items():
            blend[k] = blend.get(k, 0.0) + BULL_W * v
        for k, v in nw.items():
            blend[k] = blend.get(k, 0.0) + NDX_W * v
        keys = set(blend) | set(prev)
        to = sum(abs(blend.get(k, 0.0) - prev.get(k, 0.0)) for k in keys) / 2.0
        tos.append(to)
        prev = blend
    # first month is full turnover; annualize average monthly one-way turnover
    return float(np.mean(tos[1:]) * 12.0) if len(tos) > 1 else float("nan")


def run_window(variant, panel, ndx_panel, start, end, cash, want_turnover=True):
    """Return dict of metric rows for blend / cpm / bull standalone."""
    panel = apply_variant(variant, panel)
    art = build_artifacts(panel, ndx_panel, start, end, include_records=False)
    cpm_d, _ = run_cpm_backtest(panel, start, end)
    bull_d = run_bull_spy_backtest(panel, start, end)
    to = blend_turnover(panel, ndx_panel, start, end) if want_turnover else None
    out = {
        "blend": metrics_row(art.blend, cash, to),
        "cpm": metrics_row(cpm_d, cash),
        "bull": metrics_row(bull_d, cash),
        "_blend_daily": art.blend,
        "_cpm_daily": cpm_d,
        "_bull_daily": bull_d,
    }
    restore()
    return out


def crisis_metrics(daily: pd.Series, cash: pd.Series) -> dict:
    """Total return + MaxDD over crisis slices."""
    res = {}
    for name, (s, e) in CRISES.items():
        seg = daily.loc[(daily.index >= s) & (daily.index <= e)]
        if seg.empty:
            res[name] = (float("nan"), float("nan"))
            continue
        eq = (1 + seg).cumprod()
        tr = eq.iloc[-1] - 1
        dd = (eq / eq.cummax() - 1).min()
        res[name] = (tr, dd)
    return res


def monthly_ret(daily: pd.Series) -> pd.Series:
    return (1 + daily).resample("ME").prod() - 1


def main():
    print("Loading panel + stitched KMLM proxy ...")
    base_panel = build_panel()
    ndx_panel = load_ndx_panel()
    cash = base_panel["SHV"].ffill().pct_change().dropna()
    kmlm_check = base_panel["KMLM"].dropna()
    print(f"KMLM stitched proxy: {kmlm_check.index[0].date()} -> {kmlm_check.index[-1].date()}")

    variants = ["D0", "D1", "D2", "D3", "D4"]
    results = {}

    # --- Clean window (primary) ---
    print("\n=== CLEAN window 2008-05-30 .. 2026-05-22 ===")
    for v in variants:
        results[("clean", v)] = run_window(v, base_panel, ndx_panel, CLEAN_START, END, cash)
        b = results[("clean", v)]["blend"]
        print(f"{v} blend: Sharpe {b['sharpe']:.3f} CAGR {b['cagr']*100:.2f}% "
              f"Vol {b['vol']*100:.2f}% MaxDD {b['maxdd']*100:.2f}% "
              f"Calmar {b['calmar']:.2f} TO {b['turnover']*100:.0f}%")

    # --- Stress window ---
    print("\n=== STRESS window 1999-03-10 .. 2026-05-22 ===")
    for v in variants:
        results[("stress", v)] = run_window(v, base_panel, ndx_panel, STRESS_START, END, cash,
                                            want_turnover=False)
        b = results[("stress", v)]["blend"]
        print(f"{v} blend: Sharpe {b['sharpe']:.3f} CAGR {b['cagr']*100:.2f}% "
              f"Vol {b['vol']*100:.2f}% MaxDD {b['maxdd']*100:.2f}% Calmar {b['calmar']:.2f}")

    # --- 60/40 two-sleeve (CPM/BULL) per variant, clean window ---
    print("\n=== 60/40 two-sleeve (CPM/BULL) clean window ===")
    six40 = {}
    for v in variants:
        r = results[("clean", v)]
        common = r["_cpm_daily"].index.intersection(r["_bull_daily"].index)
        b6040 = 0.6 * r["_cpm_daily"].loc[common] + 0.4 * r["_bull_daily"].loc[common]
        six40[v] = metrics_row(b6040, cash)
        m = six40[v]
        print(f"{v}: Sharpe {m['sharpe']:.3f} CAGR {m['cagr']*100:.2f}% "
              f"MaxDD {m['maxdd']*100:.2f}%")

    # --- Crisis-alpha: KMLM raw returns + blend deltas vs D0 ---
    print("\n=== Crisis episodes: blend total return / MaxDD by variant (clean) ===")
    kmlm_m = monthly_ret(base_panel["KMLM"].ffill().pct_change().fillna(0.0))
    crisis_tbl = {}
    for v in variants:
        crisis_tbl[v] = crisis_metrics(results[("clean", v)]["_blend_daily"], cash)
    for cname in CRISES:
        print(f"-- {cname} --")
        for v in variants:
            tr, dd = crisis_tbl[v][cname]
            print(f"   {v}: TR {tr*100:+.2f}%  MaxDD {dd*100:.2f}%")

    # KMLM raw return per crisis year
    print("\n=== KMLM (stitched) raw calendar-year return in crisis episodes ===")
    kmlm_d = base_panel["KMLM"].ffill().pct_change().fillna(0.0)
    for cname, (s, e) in CRISES.items():
        seg = kmlm_d.loc[(kmlm_d.index >= s) & (kmlm_d.index <= e)]
        tr = (1 + seg).prod() - 1 if not seg.empty else float("nan")
        print(f"   {cname}: KMLM {tr*100:+.2f}%")

    # --- Crisis vs calm decomposition: monthly (variant - D0) blend delta ---
    print("\n=== Convex-leg marginal effect: monthly blend delta vs D0 (clean) ===")
    d0_m = monthly_ret(results[("clean", "D0")]["_blend_daily"])
    crisis_months = pd.Series(False, index=d0_m.index)
    for s, e in CRISES.values():
        crisis_months |= (d0_m.index >= s) & (d0_m.index <= e)
    for v in ["D1", "D2", "D3", "D4"]:
        vm = monthly_ret(results[("clean", v)]["_blend_daily"]).reindex(d0_m.index)
        delta = (vm - d0_m).dropna()
        active = delta[delta.abs() > 1e-6]
        cm = crisis_months.reindex(delta.index).fillna(False)
        crisis_sum = delta[cm].sum()
        calm_sum = delta[~cm].sum()
        n_active = len(active)
        print(f"{v}: crisis-months cum delta {crisis_sum*100:+.2f}%  "
              f"calm cum delta {calm_sum*100:+.2f}%  "
              f"(active months with nonzero delta: {n_active})")

    # Persist a structured dump for the findings writer
    import json
    dump = {}
    for (win, v), r in results.items():
        dump[f"{win}:{v}"] = {"blend": r["blend"], "cpm": r["cpm"], "bull": r["bull"]}
    dump["six40_clean"] = six40
    dump["crisis_tbl"] = {v: {c: list(crisis_tbl[v][c]) for c in CRISES} for v in variants}
    out_json = ROOT / "research" / "bull_kmlm_convex_safe_results.json"
    out_json.write_text(json.dumps(dump, indent=2, default=float))
    print(f"\nWrote {out_json}")


if __name__ == "__main__":
    main()
