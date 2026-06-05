# -*- coding: utf-8 -*-
"""ANALYST (read-only re production; NO production files touched; NO commit).

QUESTION: WHY does the slower Faber 10mo-SMA trend metric beat the faster
13612U on the CPM universe (clean +0.012 Sharpe within-noise; ext +0.14 Calmar
/ +3pp shallower MaxDD), while 13612U beats Faber on the HAA universe?

HYPOTHESIS: high-vol growth/quality names QQQ/SPHQ drive Faber's preference --
a slow 10mo-SMA rides high-momentum/high-vol names through short-term reversals,
while the fast 13612U whipsaws in/out of them (deeper crisis drawdowns); on
flatter/lower-vol assets the speed penalty disappears.

METHOD: flip ONLY the coupled trend metric (Faber <-> 13612U), full CPM stack
otherwise (vol-adjust kept V=1, inverse-vol weighting W=1, HYG-or-TIP canary
C=1, top-4, partial-safe, SHV/IEF best-of-safe; both metrics vol-adjusted in
the rank denominator). Sweep UNIVERSE variants where QQQ/SPHQ are replaced by
SPY. If de-tilting collapses Faber's edge, the high-vol growth names drive it.

Reuses cpm_live engine + exec_lag mooex T+1 harness (same as
cpm_haa_coupled_factorial.py). Clean window = decision lens; ext = full history.
Single in-sample. SPY long history (fine). SPY-swap drops universe cardinality
from 8 -> 7 only in the BOTH-swap variant (noted).
"""
import sys, json, itertools
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import bull_spy_live  # noqa: F401 (harness parity)
if not hasattr(bull_spy_live, "_vol_gate_ok"):
    bull_spy_live._vol_gate_ok = lambda *a, **k: True
from cpm_live import (
    load_panel, perf_metrics, sig_13612U, best_safe, faber_sma_xs, inv_vol_weights,
    compute_target_weights, RISKY_UNIVERSE, SAFE_POOL, CANARY_ASSETS, DEFAULT_CASH,
    COST_BPS_PER_SIDE, CORR_LOOKBACK_DAYS,
)
import exec_lag_moo_validation_2026_05_30 as H

CONV = "mooex"
SAFE = ["SHV", "IEF"]
TOP_K = 4

CPM_UNIVERSE = ["QQQ", "SPHQ", "EFA", "EEM", "VNQ", "GLD", "TLT", "DBC"]
HAA_UNIVERSE = ["SPY", "IWM", "VEA", "VWO", "VNQ", "DBC", "IEF", "TLT"]

UNIVERSE_VARIANTS = {
    "CPM_as_is":        ["QQQ", "SPHQ", "EFA", "EEM", "VNQ", "GLD", "TLT", "DBC"],
    "CPM_both_to_SPY":  ["SPY", "EFA", "EEM", "VNQ", "GLD", "TLT", "DBC"],          # 7 (dedup)
    "CPM_QQQ_to_SPY":   ["SPY", "SPHQ", "EFA", "EEM", "VNQ", "GLD", "TLT", "DBC"],  # 8
    "CPM_SPHQ_to_SPY":  ["QQQ", "SPY", "EFA", "EEM", "VNQ", "GLD", "TLT", "DBC"],   # 8
    "HAA_universe":     ["SPY", "IWM", "VEA", "VWO", "VNQ", "DBC", "IEF", "TLT"],   # 8
}

ANCHOR_CLEAN_FABER = (1.1658, -12.97, 1.0137)   # CPM full, Faber  (Sharpe, MaxDD%, Calmar)
ANCHOR_CLEAN_13612 = (1.1540, -13.32, 0.9876)   # CPM full, 13612U


# ===================== coupled CPM weight fn (full stack; flip T only) =====================
def cpm_wf(close, sig_d, universe, trend, diag=None):
    """Full CPM stack (V=1 vol-adjust, W=1 inverse-vol, C=1 HYG-or-TIP canary,
    top-4, partial-safe, best-of-safe SHV/IEF). trend in {'faber','13612u'}
    flips BOTH the rank numerator AND the absolute screen metric (coupled).
    diag (optional dict) collects per-ticker rank/screen/pick for this month."""
    monthly = close.loc[:sig_d].resample("ME").last()
    safe = best_safe(monthly, sig_d, SAFE)

    # C canary: HYG OR TIP any-positive 13612U
    canary_assets = ["HYG", "TIP"]
    cs = [sig_13612U(monthly[a]) for a in canary_assets if a in monthly.columns]
    cs = [s for s in cs if pd.notna(s)]
    if not cs or sum(1 for s in cs if s > 0) == 0:
        if diag is not None:
            diag["risk_off"] = True
        return {safe: 1.0}

    present = [t for t in universe if t in monthly.columns]
    faber = faber_sma_xs(monthly)
    avail = [t for t in present
             if sig_d in close.index and pd.notna(close.loc[sig_d].get(t, np.nan))]
    if not avail:
        return {safe: 1.0}

    daily = close[avail].ffill().pct_change()
    rank_score, screen_val = {}, {}
    for t in avail:
        u = sig_13612U(monthly[t]) if t in monthly.columns else np.nan
        fb = float(faber[t]) if (t in faber.index and pd.notna(faber[t])) else np.nan
        num = fb if trend == "faber" else u
        if pd.isna(num):
            continue
        rv = daily[t].loc[:sig_d].tail(252).std() * np.sqrt(252)   # V vol-adjust
        if pd.isna(rv) or rv < 1e-9:
            rv = 1.0
        rank_score[t] = num / rv
        screen_val[t] = num   # screen = raw trend metric (NOT vol-adjusted)
    if not rank_score:
        return {safe: 1.0}

    ranked = pd.Series(rank_score).sort_values(ascending=False)
    top = ranked.iloc[:min(TOP_K, len(ranked))]
    picks = [t for t in top.index if pd.notna(screen_val.get(t, np.nan)) and screen_val[t] > 0]

    if diag is not None:
        diag["risk_off"] = False
        diag["safe"] = safe
        diag["rank_order"] = list(ranked.index)
        diag["top4"] = list(top.index)
        diag["picks"] = list(picks)
        diag["rank_score"] = {t: float(rank_score[t]) for t in rank_score}
        diag["screen_val"] = {t: float(screen_val[t]) for t in screen_val}

    if len(picks) == 0:
        return {safe: 1.0}

    n_picks = len(picks)
    risky_fraction = min(n_picks, TOP_K) / float(TOP_K)
    safe_fraction = 1.0 - risky_fraction
    base_w = inv_vol_weights(close.loc[:sig_d], picks, CORR_LOOKBACK_DAYS)   # W
    out = {t: w * risky_fraction for t, w in base_w.items()}
    if safe_fraction > 0:
        out[safe] = out.get(safe, 0.0) + safe_fraction
    if diag is not None:
        diag["weights"] = {k: float(v) for k, v in out.items()}
    return out


# ===================== runners =====================
def met(daily, cash):
    m = perf_metrics(daily, cash)
    return {"sharpe": m.get("sharpe"), "cagr": m.get("cagr"), "vol": m.get("vol"),
            "maxdd": m.get("max_drawdown"), "calmar": m.get("calmar"), "martin": m.get("martin")}


def run_series(close, daily, intraday, overnight, wf, start, end):
    s, _ = H._segment_returns_conv(close, daily, wf, start, end, CONV,
                                   COST_BPS_PER_SIDE, intraday, overnight)
    return s


CRISES = {
    "DotCom": ("2000-03-01", "2002-12-31"),
    "GFC":    ("2007-10-01", "2009-06-30"),
    "COVID":  ("2020-02-01", "2020-04-30"),
    "2022":   ("2022-01-01", "2022-10-31"),
}


def crisis_dd(ser, lo, hi):
    eq = (1.0 + ser).cumprod().dropna()
    if eq.empty:
        return None
    rm = eq.cummax()
    dd = eq / rm - 1.0
    w = dd.loc[lo:hi]
    if len(w) == 0 or not np.isfinite(w.min()):
        return None
    return float(w.min())


def main():
    end = pd.Timestamp("2026-05-22")
    ext_start = pd.Timestamp("1999-03-10")
    clean_start = pd.Timestamp("2008-05-30")

    panel = load_panel(start=ext_start, end=end)
    end = min(end, panel.index[-1])
    cash = panel["SHV"].ffill().pct_change().dropna()

    open_df, close_yf = H.load_open_close()
    intraday = (close_yf / open_df - 1.0).reindex(panel.index)
    overnight = (open_df / close_yf.shift(1) - 1.0).reindex(panel.index)

    allcols = sorted(set(sum(UNIVERSE_VARIANTS.values(), []) + SAFE + ["HYG", "TIP"]) & set(panel.columns))
    close = panel[allcols]
    daily = close.ffill().pct_change()
    print("panel cols:", allcols)
    for nm, u in UNIVERSE_VARIANTS.items():
        miss = [t for t in u if t not in allcols]
        if miss:
            print(f"WARN {nm} missing: {miss}")

    windows = {"CLEAN": (clean_start, end), "EXT": (ext_start, end)}

    def windowed(ser):
        return {wn: met(ser.loc[(ser.index >= ws) & (ser.index <= we)], cash)
                for wn, (ws, we) in windows.items()}

    # ---- production-direct CPM anchor (Faber, full stack) ----
    prod_cols = sorted(set(RISKY_UNIVERSE + SAFE_POOL + CANARY_ASSETS + [DEFAULT_CASH]) & set(panel.columns))
    prod_close = panel[prod_cols]
    prod_daily = prod_close.ffill().pct_change()
    prod_s = run_series(prod_close, prod_daily, intraday, overnight,
                        lambda sd: compute_target_weights(prod_close, sd)[0], ext_start, end)
    prod_m = windowed(prod_s)

    # ---- gate: our cpm_wf(CPM_as_is, faber) == production weight-by-weight ----
    monthly_idx = (pd.DataFrame({"x": 1}, index=close.index)
                   .groupby(pd.Grouper(freq="ME")).tail(1))
    sigs = monthly_idx.index[(monthly_idx.index >= ext_start) & (monthly_idx.index <= end)].tolist()
    gate_mismatch = 0
    for sd in sigs:
        a = {k: round(v, 6) for k, v in cpm_wf(close, sd, CPM_UNIVERSE, "faber").items() if abs(v) > 1e-9}
        b = {k: round(v, 6) for k, v in compute_target_weights(prod_close, sd)[0].items() if abs(v) > 1e-9}
        if a != b:
            gate_mismatch += 1

    # ===================== 1) universe-variant head-to-head =====================
    series = {}      # (variant, trend) -> series
    table = {}       # variant -> {faber:{CLEAN,EXT}, '13612u':..., delta:...}
    for vname, u in UNIVERSE_VARIANTS.items():
        table[vname] = {}
        for trend in ("faber", "13612u"):
            wf = lambda sd, _u=u, _t=trend: cpm_wf(close, sd, _u, _t)
            ser = run_series(close, daily, intraday, overnight, wf, ext_start, end)
            series[(vname, trend)] = ser
            table[vname][trend] = windowed(ser)
        # Faber - 13612U delta
        delta = {}
        for wn in windows:
            f, g = table[vname]["faber"][wn], table[vname]["13612u"][wn]
            delta[wn] = {m: f[m] - g[m] for m in ("sharpe", "calmar", "maxdd")}
        table[vname]["delta_faber_minus_13612u"] = delta

    # anchor check
    fa = table["CPM_as_is"]["faber"]["CLEAN"]
    ga = table["CPM_as_is"]["13612u"]["CLEAN"]
    anchor_faber_ok = (abs(fa["sharpe"] - ANCHOR_CLEAN_FABER[0]) < 5e-4
                       and abs(fa["maxdd"] * 100 - ANCHOR_CLEAN_FABER[1]) < 0.05
                       and abs(fa["calmar"] - ANCHOR_CLEAN_FABER[2]) < 5e-4)
    anchor_13612_ok = (abs(ga["sharpe"] - ANCHOR_CLEAN_13612[0]) < 5e-4
                       and abs(ga["maxdd"] * 100 - ANCHOR_CLEAN_13612[1]) < 0.05
                       and abs(ga["calmar"] - ANCHOR_CLEAN_13612[2]) < 5e-4)

    # ===================== 2) MECHANISM: flips / whipsaw on QQQ/SPHQ vs SPY =====================
    # Collect per-month diagnostics for CPM_as_is (QQQ/SPHQ present) and the
    # single-swap variants (SPY present) under faber vs 13612u.
    def collect_diag(u):
        rows = {"faber": [], "13612u": []}
        for sd in sigs:
            for trend in ("faber", "13612u"):
                d = {}
                cpm_wf(close, sd, u, trend, diag=d)
                d["date"] = sd
                rows[trend].append(d)
        return rows

    def name_flip_stats(rows, names):
        """For each tracked name: count months where pick/hold status differs
        between faber and 13612u, and turnover (entries+exits) within each metric."""
        out = {}
        fab, g = rows["faber"], rows["13612u"]
        n = len(fab)
        for nm in names:
            held_f = [(nm in r.get("picks", [])) for r in fab]
            held_g = [(nm in r.get("picks", [])) for r in g]
            present = [(nm in r.get("rank_score", {})) for r in fab]
            n_present = sum(present)
            disagree = sum(1 for a, b, p in zip(held_f, held_g, present) if p and a != b)
            # turnover = number of state changes across consecutive months (held or not)
            def turns(held):
                return sum(1 for i in range(1, len(held)) if held[i] != held[i - 1])
            out[nm] = {
                "months_present": n_present,
                "held_faber": sum(held_f),
                "held_13612u": sum(held_g),
                "hold_disagreements": disagree,
                "turnover_faber": turns(held_f),
                "turnover_13612u": turns(held_g),
            }
        return out

    mech = {}
    mech["CPM_as_is_QQQ_SPHQ"] = name_flip_stats(collect_diag(CPM_UNIVERSE), ["QQQ", "SPHQ"])
    mech["CPM_QQQ_to_SPY_SPY"] = name_flip_stats(collect_diag(UNIVERSE_VARIANTS["CPM_QQQ_to_SPY"]), ["SPY", "SPHQ"])
    mech["CPM_SPHQ_to_SPY_SPY"] = name_flip_stats(collect_diag(UNIVERSE_VARIANTS["CPM_SPHQ_to_SPY"]), ["QQQ", "SPY"])

    # realized vol profile of the names (full-sample annualized rv) for context
    rv_profile = {}
    for t in ["QQQ", "SPHQ", "SPY", "EFA", "EEM", "VNQ", "GLD", "TLT", "DBC", "IWM", "VEA", "VWO"]:
        if t in daily.columns:
            r = daily[t].dropna()
            rv_profile[t] = float(r.std() * np.sqrt(252))

    # ---- per-universe realized-vol tables over CLEAN window ----
    # (1) clean_vol: annualized daily vol over the whole clean window.
    # (2) mean_rv252: time-average of the rolling rv_252d the strategy ranks on,
    #     sampled at each monthly signal date within the clean window.
    clean_sigs = [sd for sd in sigs if clean_start <= sd <= end]
    rv252_series = {}
    for t in daily.columns:
        rv252_series[t] = daily[t].rolling(252).std() * np.sqrt(252)

    def vol_table(univ):
        rows = {}
        for t in univ:
            if t not in daily.columns:
                continue
            r = daily[t].loc[(daily.index >= clean_start) & (daily.index <= end)].dropna()
            clean_vol = float(r.std() * np.sqrt(252)) if len(r) > 2 else None
            rv_vals = [float(rv252_series[t].loc[:sd].dropna().iloc[-1])
                       for sd in clean_sigs
                       if not rv252_series[t].loc[:sd].dropna().empty]
            mean_rv252 = float(np.mean(rv_vals)) if rv_vals else None
            rows[t] = {"clean_vol": clean_vol, "mean_rv252": mean_rv252}
        ordered = sorted(rows.items(),
                         key=lambda kv: (kv[1]["clean_vol"] if kv[1]["clean_vol"] is not None else -1),
                         reverse=True)
        cvs = [v["clean_vol"] for _, v in ordered if v["clean_vol"] is not None]
        rvs = [v["mean_rv252"] for _, v in ordered if v["mean_rv252"] is not None]
        return {
            "assets_sorted_high_to_low": [{"ticker": k, **v} for k, v in ordered],
            "mean_clean_vol": float(np.mean(cvs)) if cvs else None,
            "mean_mean_rv252": float(np.mean(rvs)) if rvs else None,
        }

    universe_vol_tables = {
        "CPM_universe": vol_table(CPM_UNIVERSE),
        "HAA_universe": vol_table(HAA_UNIVERSE),
        "shared_names_VNQ_DBC_TLT": vol_table(["VNQ", "DBC", "TLT"]),
    }

    # ===================== crisis behavior (Faber vs 13612U on CPM_as_is) =====================
    crisis = {}
    for nm, (lo, hi) in CRISES.items():
        crisis[nm] = {
            "CPM_faber": crisis_dd(series[("CPM_as_is", "faber")], lo, hi),
            "CPM_13612u": crisis_dd(series[("CPM_as_is", "13612u")], lo, hi),
            "CPM_both_to_SPY_faber": crisis_dd(series[("CPM_both_to_SPY", "faber")], lo, hi),
            "CPM_both_to_SPY_13612u": crisis_dd(series[("CPM_both_to_SPY", "13612u")], lo, hi),
        }

    result = {
        "meta": {"conv": CONV, "cost_bps": COST_BPS_PER_SIDE, "lookback": CORR_LOOKBACK_DAYS,
                 "top_k": TOP_K, "clean": f"{clean_start.date()}..{end.date()}",
                 "ext": f"{ext_start.date()}..{end.date()}",
                 "universe_variants": UNIVERSE_VARIANTS, "safe_pool": SAFE,
                 "note": "Full CPM stack; flip ONLY coupled trend metric Faber<->13612U"},
        "gates": {
            "cpm_wf_faber_eq_production": {"weight_mismatches": gate_mismatch, "pass": gate_mismatch == 0},
            "anchor_faber_CLEAN": {"target": list(ANCHOR_CLEAN_FABER),
                                   "actual": [fa["sharpe"], fa["maxdd"], fa["calmar"]],
                                   "pass": bool(anchor_faber_ok)},
            "anchor_13612u_CLEAN": {"target": list(ANCHOR_CLEAN_13612),
                                    "actual": [ga["sharpe"], ga["maxdd"], ga["calmar"]],
                                    "pass": bool(anchor_13612_ok)},
        },
        "benchmark_production_direct": prod_m,
        "head_to_head": table,
        "mechanism_flips": mech,
        "rv_profile_annualized": rv_profile,
        "universe_vol_tables_clean": universe_vol_tables,
        "crisis_dd": crisis,
    }
    out_json = Path(__file__).with_suffix(".json")
    out_json.write_text(json.dumps(result, indent=2, default=float))
    print("\nGATES:", json.dumps(result["gates"], indent=2, default=float))

    # console summary
    print("\n=== Faber - 13612U delta by universe variant ===")
    for vname in UNIVERSE_VARIANTS:
        d = table[vname]["delta_faber_minus_13612u"]
        print(f"{vname:18s} CLEAN dSharpe={d['CLEAN']['sharpe']:+.4f} dCalmar={d['CLEAN']['calmar']:+.4f} "
              f"dMaxDD={d['CLEAN']['maxdd']*100:+.2f}pp | EXT dSharpe={d['EXT']['sharpe']:+.4f} "
              f"dCalmar={d['EXT']['calmar']:+.4f} dMaxDD={d['EXT']['maxdd']*100:+.2f}pp")
    print("\n=== Per-asset realized vol over CLEAN window (annualized) ===")
    for un in ("CPM_universe", "HAA_universe"):
        vt = universe_vol_tables[un]
        print(f"\n{un}  (mean clean_vol={vt['mean_clean_vol']*100:.1f}%  mean rv252={vt['mean_mean_rv252']*100:.1f}%)")
        for row in vt["assets_sorted_high_to_low"]:
            print(f"  {row['ticker']:5s} clean_vol={row['clean_vol']*100:5.1f}%  mean_rv252={row['mean_rv252']*100:5.1f}%")
    print("\nWROTE", out_json)
    return result


if __name__ == "__main__":
    main()
