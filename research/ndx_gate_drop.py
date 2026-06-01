# -*- coding: utf-8 -*-
"""Throwaway research (analyst role; read-only re production; writes only to
research/; NO production/memo files changed; NO commit). EXPLORATION ONLY.

QUESTION: Does the NDX sleeve's vol gate (RV60<RV252, inherited via the monthly
BULL active state) earn its keep over a no-gate (canary+trend-only) NDX baseline?
Mirrors the BULL drop-vol-gate analysis (research/bull_gate_baseline_attribution.py).

NDX gate architecture (confirmed from ndx_sleeve_live.compute_ndx_weights +
bull_spy_live.compute_bull_spy_weights):
  - NDX is ACTIVE (holds top-5 PIT Nasdaq-100 stocks by raw 13612U momentum)
    iff the BULL sleeve is risk-on: canary_ok AND spy_trend_ok AND vol_ok.
    canary_ok = TIP 13612U > 0; spy_trend_ok = SPY 13612U > 0;
    vol_ok = RV60d < RV252d (annualized, SPY daily). <- THE VOL GATE.
  - BULL defensive -> NDX = 100% best-of-safe (SHV/IEF by 13612U).
So the NDX vol gate IS the SPY RV60<RV252 crossover, inherited 1:1 from BULL.

BASELINE = drop vol_ok from the NDX activation test (canary+trend only).
Everything else identical (same stock selection, same safe, same engine).

(A) Anchor: reproduce production NDX standalone (with gate) clean window.
(B) Baseline vs gate: marginal Calmar/Martin/Sharpe/CAGR/MaxDD + per-crisis MaxDD
    (2008 GFC, 2020 COVID, 2018-Q4, 2022).
(C) Decisive: paired stationary block bootstrap (B=5000, block=21d) on the
    marginal (gate minus no-gate); CI of Calmar/Martin/Sharpe deltas.
(D) Attribution: every vol-gate de-risk (canary&trend ok, vol NOT ok -> NDX to
    safe) classified crash/grind-save vs whipsaw by forward Nasdaq (QQQ) return.

HONESTY: t+1 MOO (offset=1 close-to-close NDX engine; exact-open unsupported for
per-stock universe). Point-in-time signals. Single in-sample 18y -> flag. NDX
constituent prices refreshed 2026-05-29 so anchor CAGR/Sharpe drift ~1pp/0.02 vs
frozen memo (MaxDD reproduces exactly); marginal uses SAME data both arms so the
delta is unaffected.

Writes research/ndx_gate_drop_findings.md (+ .json).
"""
from __future__ import annotations
import sys, json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from cpm_live import load_panel, perf_metrics, sig_13612U, COST_BPS_PER_SIDE
import ndx_sleeve_live as ndx_sleeve
import bull_spy_live as B
from bull_spy_live import _macro_gate, _spy_trend_ok, _vol_gate_ok, _pick_safe

CLEAN_START = pd.Timestamp("2008-05-30")
EXT_START = pd.Timestamp("1999-03-10")
END = pd.Timestamp("2026-05-22")
COST = COST_BPS_PER_SIDE

# Production NDX standalone clean anchor (README / two_sleeve_iv4_memo_numbers).
# MaxDD reproduces exactly; CAGR/Sharpe drift from 2026-05-29 price refresh.
ANCHOR_NDX = {"sharpe": 1.186, "maxdd": -35.92, "calmar": 0.84, "cagr": 30.01, "excess_sharpe": 1.132}

CRISES = {
    "2008 GFC":      ("2008-05-30", "2009-06-30"),
    "2020 COVID":    ("2020-01-01", "2020-06-30"),
    "2018-Q4 grind": ("2018-09-01", "2018-12-31"),
    "2022 grind":    ("2022-01-01", "2022-12-31"),
}

B_ITER, BLOCK, SEED = 5000, 21, 42


# ---------------- gate-state helper (canary / trend / vol legs) ----------------
def gate_legs(cpm_panel, sig_d):
    """Return (canary_ok, trend_ok, vol_ok) for the BULL/NDX activation test."""
    monthly = cpm_panel.loc[:sig_d].resample("ME").last()
    canary_ok, _ = _macro_gate(monthly, sig_d)
    trend_ok, _ = _spy_trend_ok(monthly, sig_d)
    vol_ok, _ = _vol_gate_ok(cpm_panel[B.BULL_TICKER], sig_d)
    return bool(canary_ok), bool(trend_ok), bool(vol_ok)


# ---------------- NDX weight fn with switchable vol gate ----------------
def compute_ndx_weights_variant(cpm_panel, ndx_panel, sig_d, use_vol: bool):
    """Identical to ndx_sleeve.compute_ndx_weights EXCEPT the BULL active test
    optionally drops vol_ok. use_vol=True -> production (canary&trend&vol).
    use_vol=False -> baseline (canary&trend only)."""
    canary_ok, trend_ok, vol_ok = gate_legs(cpm_panel, sig_d)
    bull_active = canary_ok and trend_ok and (vol_ok if use_vol else True)

    cpm_monthly = cpm_panel.loc[:sig_d].resample("ME").last()
    if not bull_active:
        safe = _pick_safe(cpm_monthly)
        return ({safe: 1.0}, "GATE_OFF", {"selected": []})

    import index_constitution as ic
    pit = ic.constituents_at("nasdaq100", sig_d.strftime("%Y-%m-%d"))
    pit_tickers = set(pit["symbol"].tolist())
    if len(pit_tickers) == 0:
        # PIT unavailable -> mirror BULL (extra BULL exposure). Production parity.
        bw, _, _ = B.compute_bull_spy_weights(cpm_panel, sig_d)
        return (bw, "NDX_FALLBACK_BULL", {"selected": list(bw.keys())})

    monthly = ndx_panel.loc[:sig_d].resample("ME").last()
    available = []
    for t in pit_tickers:
        if t not in ndx_panel.columns:
            continue
        if sig_d in ndx_panel.index and pd.isna(ndx_panel.loc[sig_d, t]):
            continue
        recent = ndx_panel[t].loc[sig_d - pd.Timedelta(days=30):sig_d].dropna()
        if recent.empty:
            continue
        available.append(t)

    momenta = {}
    for t in available:
        s = monthly[t].dropna()
        if len(s) < 13:
            continue
        m = sig_13612U(s)
        if pd.notna(m) and m > 0:
            momenta[t] = m

    sorted_by_mom = sorted(momenta.items(), key=lambda x: -x[1])
    n_pick = min(len(sorted_by_mom), ndx_sleeve.SELECT_K)
    selected = [t for t, _ in sorted_by_mom[:n_pick]]
    per_slot = 1.0 / ndx_sleeve.SELECT_K
    weights = {t: per_slot for t in selected}
    cash_share = 1.0 - n_pick * per_slot
    if cash_share > 1e-9:
        safe = _pick_safe(cpm_monthly)
        weights[safe] = weights.get(safe, 0.0) + cash_share
    regime = "NDX_ACTIVE" if n_pick == ndx_sleeve.SELECT_K else f"NDX_PARTIAL_{n_pick}"
    return (weights, regime, {"selected": selected})


# ---------------- offset backtest (clone of run_ndx_backtest_with_offset, weight_fn injected) ----------------
def run_ndx_variant(cpm_panel, ndx_panel, start, end, use_vol, offset=1, cost_bps=COST):
    full_panel = cpm_panel.join(ndx_panel, how="outer", rsuffix="_dup")
    full_panel = full_panel.loc[:, ~full_panel.columns.str.endswith("_dup")]
    monthly_idx = pd.DataFrame({"x": 1}, index=full_panel.index).groupby(
        pd.Grouper(freq="ME")).tail(1).index
    sig_dates = monthly_idx[(monthly_idx >= start) & (monthly_idx <= end)]
    daily_rets = pd.Series(0.0, index=full_panel.loc[start:end].index)
    weights_for_date = {}
    for sd in sig_dates:
        target, _, _ = compute_ndx_weights_variant(cpm_panel, ndx_panel, sd, use_vol)
        next_loc = full_panel.index.get_indexer([sd], method="bfill")[0] + offset
        if next_loc < len(full_panel.index):
            weights_for_date[full_panel.index[next_loc]] = target
    exec_dates = sorted(weights_for_date.keys())
    cur_w = {ndx_sleeve.CASH_TICKER: 1.0}
    cur_w_idx = 0
    for ts in full_panel.loc[start:end].index:
        while cur_w_idx < len(exec_dates) and exec_dates[cur_w_idx] <= ts:
            new_w = weights_for_date[exec_dates[cur_w_idx]]
            if cur_w != new_w:
                tovr = sum(abs(cur_w.get(a, 0) - new_w.get(a, 0))
                           for a in set(cur_w) | set(new_w))
                daily_rets.loc[ts] -= tovr * cost_bps / 10000.0
            cur_w = new_w
            cur_w_idx += 1
        prev_loc = full_panel.index.get_loc(ts)
        if prev_loc == 0:
            continue
        prev_d = full_panel.index[prev_loc - 1]
        market_open = full_panel.loc[ts].notna().sum() > full_panel.loc[ts].isna().sum()
        port_r = 0.0
        delisted_w = 0.0
        for asset, w in list(cur_w.items()):
            if asset not in full_panel.columns:
                delisted_w += w
                del cur_w[asset]
                continue
            today = full_panel.loc[ts, asset]
            yest = full_panel.loc[prev_d, asset]
            if pd.notna(today) and pd.notna(yest) and yest > 0:
                port_r += w * (today / yest - 1)
            elif market_open and pd.notna(yest) and yest > 0 and pd.isna(today):
                port_r += w * ndx_sleeve.DELISTING_HAIRCUT
                delisted_w += w
                del cur_w[asset]
        if delisted_w > 0:
            existing_safe = next((s for s in ndx_sleeve.SAFE_POOL if s in cur_w), ndx_sleeve.CASH_TICKER)
            cur_w[existing_safe] = cur_w.get(existing_safe, 0.0) + delisted_w
        daily_rets.loc[ts] += port_r
    return daily_rets


# ---------------- metrics ----------------
def fullmet(s, cash):
    m = perf_metrics(s, cash)
    return {"sharpe": m.get("sharpe"), "cagr": m.get("cagr"), "vol": m.get("vol"),
            "maxdd": m.get("max_drawdown"), "calmar": m.get("calmar"),
            "martin": m.get("martin"), "excess_sharpe": m.get("excess_sharpe")}


def _metrics_of(daily, cash):
    m = perf_metrics(daily, cash)
    return {"sharpe": m.get("sharpe"), "calmar": m.get("calmar"), "martin": m.get("martin")}


def win(s, start, end):
    return s.loc[(s.index >= start) & (s.index <= end)]


def cal2022(s):
    sub = s.loc["2022-01-01":"2022-12-31"]
    return float((1 + sub).prod() - 1) if len(sub) else float("nan")


def window_dd(s, lo, hi):
    sub = s.loc[(s.index >= pd.Timestamp(lo)) & (s.index <= pd.Timestamp(hi))]
    if len(sub) < 2:
        return {"maxdd": float("nan"), "ret": float("nan"), "n": len(sub)}
    eq = (1.0 + sub).cumprod()
    return {"maxdd": float((eq / eq.cummax() - 1.0).min()),
            "ret": float(eq.iloc[-1] - 1.0), "n": len(sub)}


def paired_block_bootstrap_marginal(base, gate, cash, n_iter=B_ITER, block=BLOCK, seed=SEED):
    """PAIRED stationary block bootstrap on marginal (gate minus baseline). Same
    random time blocks drawn from BOTH streams; delta = metric(gate)-metric(base)."""
    base = base.dropna(); gate = gate.reindex(base.index).fillna(0.0)
    idx = base.index
    cash_a = cash.reindex(idx).fillna(0.0)
    n = len(idx)
    ab = base.values; av = gate.values; ac = cash_a.values
    rng = np.random.default_rng(seed)
    keys = ["calmar", "martin", "sharpe"]
    deltas = {k: [] for k in keys}
    abs_g = {k: [] for k in keys}; abs_b = {k: [] for k in keys}
    for _ in range(n_iter):
        pos = []
        while len(pos) < n:
            s = int(rng.integers(0, n))
            for j in range(block):
                pos.append((s + j) % n)
        pos = np.array(pos[:n])
        sb = pd.Series(ab[pos], index=idx)
        sv = pd.Series(av[pos], index=idx)
        sc = pd.Series(ac[pos], index=idx)
        mb = _metrics_of(sb, sc); mv = _metrics_of(sv, sc)
        for k in keys:
            if mb[k] is not None and mv[k] is not None and np.isfinite(mb[k]) and np.isfinite(mv[k]):
                deltas[k].append(mv[k] - mb[k]); abs_g[k].append(mv[k]); abs_b[k].append(mb[k])
    out = {}
    for k in keys:
        a = np.array(deltas[k], dtype=float); a = a[np.isfinite(a)]
        out[k] = {"p2.5": float(np.percentile(a, 2.5)), "p50": float(np.percentile(a, 50)),
                  "p97.5": float(np.percentile(a, 97.5)), "mean": float(a.mean()),
                  "share_delta_gt_0_pct": float(100.0 * np.mean(a > 0)),
                  "excludes_0": bool(np.percentile(a, 2.5) > 0 or np.percentile(a, 97.5) < 0),
                  "n": int(len(a)),
                  "gate_median": float(np.percentile(np.array(abs_g[k]), 50)),
                  "base_median": float(np.percentile(np.array(abs_b[k]), 50))}
    return out


# ---------------- de-risk decision calendar + attribution (QQQ forward proxy) ----------------
def attribution(cpm_panel, start, end):
    """Every vol-gate de-risk activation: canary&trend ok but vol NOT ok (vol gate
    forces NDX to safe). Classify by forward Nasdaq (QQQ) governed-month return."""
    qqq_m = cpm_panel["QQQ"].resample("ME").last()
    qqq_mret = qqq_m.pct_change()
    by_period = pd.Series(qqq_mret.values, index=qqq_mret.index.to_period("M"))

    def fwd(period, k):
        vals = []
        for j in range(1, k + 1):
            p = period + j
            if p not in by_period.index or np.isnan(by_period.loc[p]):
                return np.nan
            vals.append(float(by_period.loc[p]))
        return float(np.prod([1 + v for v in vals]) - 1.0)

    midx = pd.DataFrame({"x": 1}, index=cpm_panel.index).groupby(pd.Grouper(freq="ME")).tail(1).index
    midx = pd.DatetimeIndex(sorted(set(midx)))
    sigs = midx[(midx >= start) & (midx <= end)]
    rows = []
    for sd in sigs:
        canary_ok, trend_ok, vol_ok = gate_legs(cpm_panel, sd)
        if not (canary_ok and trend_ok and not vol_ok):
            continue  # not a vol-gate-sole-binding de-risk
        applied = sd.to_period("M") + 1
        f1 = fwd(applied - 1, 1); f2 = fwd(applied - 1, 2); f3 = fwd(applied - 1, 3)
        if np.isnan(f1):
            cls = "unknown"
        elif f1 > 0:
            cls = "whipsaw"
        elif f1 <= -0.04:
            cls = "crash-save"
        else:
            cls = "grind-save"
        rows.append({"applied_month": str(applied.to_timestamp(how="end").normalize().date()),
                     "qqq_fwd1": f1, "qqq_fwd2": f2, "qqq_fwd3": f3, "class": cls})
    return rows


def count_flips(cpm_panel, ndx_panel, start, end, use_vol):
    """Allocation state changes (active <-> safe) of the NDX sleeve."""
    midx = pd.DataFrame({"x": 1}, index=cpm_panel.index).groupby(pd.Grouper(freq="ME")).tail(1).index
    midx = pd.DatetimeIndex(sorted(set(midx)))
    sigs = midx[(midx >= start) & (midx <= end)]
    states = []
    for sd in sigs:
        canary_ok, trend_ok, vol_ok = gate_legs(cpm_panel, sd)
        active = canary_ok and trend_ok and (vol_ok if use_vol else True)
        states.append(int(active))
    return int(np.sum(np.abs(np.diff(np.array(states)))))


def main():
    panel = load_panel(start=EXT_START, end=END)
    end = min(END, panel.index[-1])
    cash = panel["SHV"].ffill().pct_change().dropna()
    ndx_panel = ndx_sleeve.load_ndx_panel()

    print("Running NDX with-gate (production)...")
    gate = run_ndx_variant(panel, ndx_panel, EXT_START, end, use_vol=True)
    print("Running NDX no-gate (canary+trend only)...")
    base = run_ndx_variant(panel, ndx_panel, EXT_START, end, use_vol=False)

    common = gate.index.intersection(base.index)
    gate = gate.reindex(common).fillna(0.0)
    base = base.reindex(common).fillna(0.0)
    qqq = panel["QQQ"].ffill().pct_change().reindex(common).fillna(0.0)

    # ANCHOR
    g_cl = fullmet(win(gate, CLEAN_START, end), cash)
    dMaxDD = abs(g_cl["maxdd"] * 100 - ANCHOR_NDX["maxdd"])
    anchor_ok_maxdd = dMaxDD < 0.5
    anchor_ok_sharpe = abs(g_cl["sharpe"] - ANCHOR_NDX["sharpe"]) < 0.05
    print(f"ANCHOR NDX gate clean: Sharpe={g_cl['sharpe']:.4f} MaxDD={g_cl['maxdd']*100:.2f}% "
          f"Calmar={g_cl['calmar']:.4f} CAGR={g_cl['cagr']*100:.2f}% "
          f"-> MaxDD {'OK' if anchor_ok_maxdd else 'FLAG'} Sharpe {'OK' if anchor_ok_sharpe else 'DRIFT'}")

    def mblock(s):
        return {"clean": fullmet(win(s, CLEAN_START, end), cash),
                "ext": fullmet(win(s, EXT_START, end), cash),
                "ret_2022": cal2022(win(s, CLEAN_START, end))}

    A_gate = mblock(gate); A_base = mblock(base)
    flips_gate = count_flips(panel, ndx_panel, CLEAN_START, end, True)
    flips_base = count_flips(panel, ndx_panel, CLEAN_START, end, False)

    crises = {}
    for name, (lo, hi) in CRISES.items():
        b = window_dd(base, lo, hi); v = window_dd(gate, lo, hi); q = window_dd(qqq, lo, hi)
        crises[name] = {"window": [lo, hi], "QQQ": q, "baseline": b, "gate": v,
                        "marginal_dd_pp": (v["maxdd"] - b["maxdd"]) * 100,
                        "marginal_ret_pp": (v["ret"] - b["ret"]) * 100}

    boot = paired_block_bootstrap_marginal(win(base, CLEAN_START, end), win(gate, CLEAN_START, end), cash)

    attrib = attribution(panel, CLEAN_START, end)
    n_crash = sum(1 for r in attrib if r["class"] == "crash-save")
    n_grind = sum(1 for r in attrib if r["class"] == "grind-save")
    n_whip = sum(1 for r in attrib if r["class"] == "whipsaw")
    n_unk = sum(1 for r in attrib if r["class"] == "unknown")
    bp_saved = sum(-r["qqq_fwd1"] for r in attrib if r["class"] in ("crash-save", "grind-save") and not np.isnan(r["qqq_fwd1"]))
    bp_givenup = sum(r["qqq_fwd1"] for r in attrib if r["class"] == "whipsaw" and not np.isnan(r["qqq_fwd1"]))

    cl_b, cl_v = A_base["clean"], A_gate["clean"]
    ext_b, ext_v = A_base["ext"], A_gate["ext"]
    out = {
        "meta": {"conv": "ndx_offset1_c2c", "cost_bps": COST,
                 "clean": [str(CLEAN_START.date()), str(end.date())],
                 "ext": [str(EXT_START.date()), str(end.date())],
                 "crises": {k: list(v) for k, v in CRISES.items()},
                 "gate_def": "NDX active iff canary(TIP 13612U>0) AND trend(SPY 13612U>0) AND vol(RV60<RV252). vol gate = the dropped leg.",
                 "select_k": ndx_sleeve.SELECT_K,
                 "note_data": "NDX constituent prices refreshed 2026-05-29; anchor CAGR/Sharpe drift ~1pp/0.02 vs frozen memo (MaxDD exact). Marginal uses SAME data both arms."},
        "anchor": {"gate_clean": g_cl, "expected": ANCHOR_NDX,
                   "maxdd_ok": bool(anchor_ok_maxdd), "sharpe_ok": bool(anchor_ok_sharpe),
                   "dMaxDD_pp": dMaxDD},
        "A_baseline_marginal": {
            "baseline": A_base, "gate": A_gate,
            "marginal_clean": {"dSharpe": cl_v["sharpe"] - cl_b["sharpe"],
                               "dCalmar": cl_v["calmar"] - cl_b["calmar"],
                               "dMartin": cl_v["martin"] - cl_b["martin"],
                               "dMaxDD_pp": (abs(cl_v["maxdd"]) - abs(cl_b["maxdd"])) * 100,
                               "dCAGR_pp": (cl_v["cagr"] - cl_b["cagr"]) * 100,
                               "dVol_pp": (cl_v["vol"] - cl_b["vol"]) * 100},
            "marginal_ext": {"dSharpe": ext_v["sharpe"] - ext_b["sharpe"],
                             "dCalmar": ext_v["calmar"] - ext_b["calmar"],
                             "dMartin": ext_v["martin"] - ext_b["martin"],
                             "dMaxDD_pp": (abs(ext_v["maxdd"]) - abs(ext_b["maxdd"])) * 100,
                             "dCAGR_pp": (ext_v["cagr"] - ext_b["cagr"]) * 100},
            "flips_baseline": flips_base, "flips_gate": flips_gate,
            "flips_added_by_gate": flips_gate - flips_base, "crises": crises},
        "D_bootstrap_marginal": {
            "method": f"PAIRED stationary block bootstrap B={B_ITER} block={BLOCK}d seed={SEED} clean. "
                      "Same blocks both streams; delta=metric(gate)-metric(base).",
            "ci": boot},
        "B_attribution": {
            "definition": "de-risk = canary_ok AND trend_ok AND NOT vol_ok (vol sole binding; NDX forced to safe). "
                          "class by governed next-month QQQ return (Nasdaq proxy): >0 whipsaw; <=-4% crash-save; (-4%,0] grind-save.",
            "n_total": len(attrib), "n_crash_save": n_crash, "n_grind_save": n_grind,
            "n_whipsaw": n_whip, "n_unknown": n_unk, "save_count": n_crash + n_grind,
            "whipsaw_rate_pct": (100.0 * n_whip / len(attrib)) if attrib else float("nan"),
            "bp_saved_by_TP_pct": bp_saved * 100, "bp_givenup_by_FP_pct": bp_givenup * 100,
            "net_bp_pct": (bp_saved - bp_givenup) * 100, "months": attrib},
    }
    Path(__file__).with_suffix(".json").write_text(json.dumps(out, indent=2, default=float))
    write_md(out)
    print("DONE -> research/ndx_gate_drop_findings.md")
    return out


def write_md(o):
    L = []; A = L.append
    m = o["meta"]
    def pct(x): return f"{x*100:.2f}%" if x is not None and isinstance(x, (int, float)) and np.isfinite(x) else "n/a"
    def f4(x): return f"{x:.4f}" if x is not None and np.isfinite(x) else "n/a"
    def pp(x): return f"{x:+.2f}pp" if x is not None and np.isfinite(x) else "n/a"

    AB = o["A_baseline_marginal"]; mc = AB["marginal_clean"]; me = AB["marginal_ext"]
    ci = o["D_bootstrap_marginal"]["ci"]; Bx = o["B_attribution"]; a = o["anchor"]
    cal_excl = ci["calmar"]["excludes_0"]

    A("# NDX vol gate: drop-vol-gate marginal analysis (mirror of BULL)\n")
    A("Role: analyst (hypothesis-driven; read-only re production; writes only to research/; no "
      "production/memo edits; no commit). EXPLORATION ONLY. Harness "
      "`research/ndx_gate_drop.py` (clones the production NDX offset=1 engine, injects a "
      "switchable vol gate).\n")
    A("**Question.** The NDX sleeve holds top-5 PIT Nasdaq-100 stocks when ACTIVE, else best-of-safe. "
      "Activation = the monthly BULL risk-on state = canary(TIP 13612U>0) AND trend(SPY 13612U>0) AND "
      "**vol(RV60<RV252)**. The vol gate is inherited 1:1 from BULL. Does it earn its keep over a "
      "no-gate (canary+trend-only) NDX baseline? NDX is higher-beta than BULL, so the gate could "
      "matter MORE -- tested honestly, not assumed to mirror BULL.\n")

    A("## BOTTOM LINE (decisive)\n")
    A(f"- **No-gate baseline (canary+trend only) clean: Calmar {f4(AB['baseline']['clean']['calmar'])} / "
      f"MaxDD {pct(AB['baseline']['clean']['maxdd'])} / Sharpe {f4(AB['baseline']['clean']['sharpe'])} / "
      f"CAGR {pct(AB['baseline']['clean']['cagr'])}.** With-gate (production): "
      f"{f4(AB['gate']['clean']['calmar'])} / {pct(AB['gate']['clean']['maxdd'])} / "
      f"{f4(AB['gate']['clean']['sharpe'])} / {pct(AB['gate']['clean']['cagr'])}.")
    A(f"- **Gate POINT marginal: Calmar {mc['dCalmar']:+.4f}, Martin {mc['dMartin']:+.4f}, "
      f"MaxDD {mc['dMaxDD_pp']:+.2f}pp, Sharpe {mc['dSharpe']:+.4f}, CAGR {mc['dCAGR_pp']:+.2f}pp.**")
    A(f"- **PAIRED BLOCK-BOOTSTRAP CI on the marginal {'EXCLUDES' if cal_excl else 'INCLUDES'} 0 for Calmar "
      f"[{ci['calmar']['p2.5']:+.4f}, {ci['calmar']['p97.5']:+.4f}]"
      f"{'' if cal_excl else ' -> within noise'}.** "
      f"Martin [{ci['martin']['p2.5']:+.4f}, {ci['martin']['p97.5']:+.4f}] excl0={ci['martin']['excludes_0']}; "
      f"Sharpe [{ci['sharpe']['p2.5']:+.4f}, {ci['sharpe']['p97.5']:+.4f}] excl0={ci['sharpe']['excludes_0']}.")
    A(f"- **Attribution: {Bx['save_count']} saves / {Bx['n_whipsaw']} whipsaws "
      f"(whipsaw rate {Bx['whipsaw_rate_pct']:.0f}%), net {Bx['net_bp_pct']:+.1f}% gross QQQ over 18y.**\n")

    A("## 0. Anchor gate\n")
    av = a["gate_clean"]
    A(f"NDX with-gate (production) clean: Sharpe **{f4(av['sharpe'])}** / MaxDD **{pct(av['maxdd'])}** / "
      f"Calmar **{f4(av['calmar'])}** / CAGR **{pct(av['cagr'])}** / ExcessSharpe **{f4(av['excess_sharpe'])}** "
      f"vs frozen anchor {a['expected']['sharpe']} / {a['expected']['maxdd']}% / {a['expected']['calmar']} / "
      f"{a['expected']['cagr']}% / {a['expected']['excess_sharpe']} -> **MaxDD "
      f"{'MATCH' if a['maxdd_ok'] else 'FLAG'}** (d={a['dMaxDD_pp']:.3f}pp), Sharpe "
      f"{'MATCH' if a['sharpe_ok'] else 'DRIFT'}. {m['note_data']}\n")

    A("## (A) Baseline (no vol gate) vs with-gate + marginal\n")
    A("| Series | Window | CAGR | Vol | Sharpe | MaxDD | Calmar | Martin |")
    A("|---|---|---:|---:|---:|---:|---:|---:|")
    for lab, key in [("Baseline (canary+trend)", "baseline"), ("Gate (+vol)", "gate")]:
        for wl, wk in [("Clean 18y", "clean"), ("Ext 27y", "ext")]:
            r = AB[key][wk]
            A(f"| {lab} | {wl} | {pct(r['cagr'])} | {pct(r['vol'])} | {f4(r['sharpe'])} | "
              f"{pct(r['maxdd'])} | {f4(r['calmar'])} | {f4(r['martin'])} |")
    A("")
    A("**Gate marginal = gate minus baseline:**")
    A(f"- Clean: dSharpe **{mc['dSharpe']:+.4f}**, dCalmar **{mc['dCalmar']:+.4f}**, dMartin "
      f"**{mc['dMartin']:+.4f}**, dMaxDD **{mc['dMaxDD_pp']:+.2f}pp** (negative=shallower), dCAGR "
      f"**{mc['dCAGR_pp']:+.2f}pp**, dVol **{mc['dVol_pp']:+.2f}pp**.")
    A(f"- Ext: dSharpe **{me['dSharpe']:+.4f}**, dCalmar **{me['dCalmar']:+.4f}**, dMartin "
      f"**{me['dMartin']:+.4f}**, dMaxDD **{me['dMaxDD_pp']:+.2f}pp**, dCAGR **{me['dCAGR_pp']:+.2f}pp**.")
    A(f"- Flips (NDX active<->safe, clean): baseline **{AB['flips_baseline']}**, gate "
      f"**{AB['flips_gate']}** (gate ADDED **{AB['flips_added_by_gate']}**).\n")
    A("### Per-crisis MaxDD: baseline vs gate (QQQ shown for scale)\n")
    A("| Crisis | Window | QQQ DD | Baseline DD | Gate DD | Gate dMaxDD | Gate dRet |")
    A("|---|---|---:|---:|---:|---:|---:|")
    for name, c in AB["crises"].items():
        w = c["window"]
        A(f"| {name} | {w[0]}..{w[1]} | {pct(c['QQQ']['maxdd'])} | {pct(c['baseline']['maxdd'])} | "
          f"{pct(c['gate']['maxdd'])} | {pp(c['marginal_dd_pp'])} | {pp(c['marginal_ret_pp'])} |")
    A("\n*dMaxDD>0 => gate drawdown SHALLOWER than baseline (gate helped). ~0 => canary+trend already "
      "caught it; gate inert. dRet<0 with dMaxDD~0 => whipsaw cost.*\n")

    A("## (D) DECISIVE -- paired block-bootstrap CI on the marginal\n")
    A(f"**Method.** {o['D_bootstrap_marginal']['method']}\n")
    A("| Marginal (gate minus baseline) | p2.5 | p50 | p97.5 | mean | P(delta>0) | CI excludes 0? |")
    A("|---|---:|---:|---:|---:|---:|:--:|")
    for k, lab in [("calmar", "Calmar"), ("martin", "Martin"), ("sharpe", "Sharpe")]:
        c = ci[k]
        A(f"| **{lab}** | {c['p2.5']:+.4f} | {c['p50']:+.4f} | {c['p97.5']:+.4f} | {c['mean']:+.4f} | "
          f"{c['share_delta_gt_0_pct']:.1f}% | {'YES' if c['excludes_0'] else 'NO (includes 0)'} |")
    A("")
    A(f"**KEY -- does the marginal-Calmar CI exclude 0?** "
      f"**{'YES -- gate edge statistically distinguishable from noise.' if cal_excl else 'NO -- the 95% CI INCLUDES 0; the gate edge is within noise.'}** "
      f"(Calmar delta 95% CI [{ci['calmar']['p2.5']:+.4f}, {ci['calmar']['p97.5']:+.4f}], "
      f"P(delta>0)={ci['calmar']['share_delta_gt_0_pct']:.1f}%, median {ci['calmar']['p50']:+.4f}.)\n")

    A("## (B) De-risk attribution -- every vol-gate activation classified\n")
    A(f"**Definition.** {Bx['definition']}\n")
    A(f"- Total de-risk activations: **{Bx['n_total']}** | Crash-saves **{Bx['n_crash_save']}** | "
      f"Grind-saves **{Bx['n_grind_save']}** | Whipsaws **{Bx['n_whipsaw']}** | unknown **{Bx['n_unknown']}**")
    A(f"- Saves vs whipsaws: **{Bx['save_count']} saves / {Bx['n_whipsaw']} whipsaws** "
      f"(whipsaw rate **{Bx['whipsaw_rate_pct']:.1f}%**)")
    A(f"- bp SAVED by TP (QQQ loss avoided): **{Bx['bp_saved_by_TP_pct']:+.2f}%** | "
      f"bp GIVEN UP by FP (QQQ upside forgone): **{Bx['bp_givenup_by_FP_pct']:+.2f}%** | "
      f"NET **{Bx['net_bp_pct']:+.2f}%**\n")
    A("| Applied month | QQQ fwd1 | QQQ fwd2 | QQQ fwd3 | Class |")
    A("|---|---:|---:|---:|---|")
    for r in Bx["months"]:
        A(f"| {r['applied_month']} | "
          f"{(str(round(r['qqq_fwd1']*100,2))+'%') if not np.isnan(r['qqq_fwd1']) else 'n/a'} | "
          f"{(str(round(r['qqq_fwd2']*100,2))+'%') if not np.isnan(r['qqq_fwd2']) else 'n/a'} | "
          f"{(str(round(r['qqq_fwd3']*100,2))+'%') if not np.isnan(r['qqq_fwd3']) else 'n/a'} | {r['class']} |")
    A("")

    A("## VERDICT\n")
    earned = [n for n, c in AB["crises"].items() if c["marginal_dd_pp"] > 1.0]
    inert = [n for n, c in AB["crises"].items() if abs(c["marginal_dd_pp"]) <= 1.0]
    reopened = [n for n, c in AB["crises"].items() if c["marginal_dd_pp"] < -1.0]
    A(f"- Gate materially reduced per-crisis DD (>+1pp shallower) in: **{earned if earned else 'none'}**")
    A(f"- Gate ~inert per-crisis (canary+trend already caught it): **{inert if inert else 'none'}**")
    A(f"- Gate made DD WORSE (whipsaw, >1pp deeper) in: **{reopened if reopened else 'none'}**")
    A(f"- Attribution: **{Bx['save_count']} saves / {Bx['n_whipsaw']} whipsaws** "
      f"({Bx['whipsaw_rate_pct']:.0f}% whipsaw), net **{Bx['net_bp_pct']:+.1f}%** gross QQQ.\n")
    A("### Does the NDX vol gate earn its keep?\n")
    if cal_excl and mc["dCalmar"] > 0:
        A("**YES (statistically).** The marginal-Calmar CI EXCLUDES 0 and the point estimate is "
          "positive -- the NDX gate's risk-adjusted edge survives episode-resampling, UNLIKE BULL "
          "(whose CI included 0). The higher-beta NDX sleeve genuinely benefits from the vol gate.\n")
    else:
        A("**NO -- within noise, same as BULL.** The marginal-Calmar CI INCLUDES 0, so the NDX gate's "
          "risk-adjusted edge is NOT statistically distinguishable from noise across reshuffled history. "
          "Despite NDX being higher-beta (where the gate could matter more), the drop-vol-gate result "
          "mirrors the BULL finding: the point estimate may look positive but rests on too few episodes "
          "to be reliable. Crash protection comes mostly from canary+trend; the vol gate adds whipsaw.\n")
    A("### Direct comparison to BULL\n")
    A("| | BULL (prior) | NDX (this) |")
    A("|---|---|---|")
    A(f"| Marginal Calmar (point) | +0.25 | {mc['dCalmar']:+.4f} |")
    A(f"| Marginal-Calmar CI | [-0.30, +0.60] (incl 0) | [{ci['calmar']['p2.5']:+.4f}, {ci['calmar']['p97.5']:+.4f}] ({'excl' if cal_excl else 'incl'} 0) |")
    A(f"| Whipsaw rate | 59% | {Bx['whipsaw_rate_pct']:.0f}% |")
    A(f"| CAGR cost/yr | -0.67pp | {mc['dCAGR_pp']:+.2f}pp |")
    A(f"| Crisis win | only 2022 | {earned if earned else 'none'} |")
    A("")

    A("## Caveats\n")
    A("- EXPLORATION ONLY; no production/memo edits; no commit.")
    A("- NDX engine: T+1 MOO offset=1 close-to-close (exact-open engine unsupported for the per-stock "
      "PIT universe + delisting haircut), 10 bps/side, monthly month-end signal. Baseline and gate share "
      "the SAME stock selection, safe pool, and engine -- the vol gate (RV60<RV252) is the SINGLE "
      "differentiator (apples-to-apples).")
    A("- ANCHOR drift: NDX constituent prices were refreshed 2026-05-29 (yfinance auto_adjust re-adjusts "
      "full history), so reproduced anchor CAGR/Sharpe drift ~1pp/0.02 vs the frozen memo; MaxDD "
      "reproduces exactly (-35.92%). The marginal (gate vs no-gate) uses the SAME refreshed data on both "
      "arms, so the DELTA is unaffected by the drift.")
    A("- Attribution forward returns use calendar-month QQQ close-to-close as a Nasdaq proxy for what the "
      "NDX stock basket gave up while forced to safe (the sleeve's actual held names vary month to month; "
      "QQQ is a coarse but unbiased beta proxy). The save/whipsaw SPLIT is the robust signal.")
    A("- Per-crisis MaxDD from each window start (intra-window peak); understates DD if the episode peak "
      "preceded the window. 2018-Q4 = 2018-09-01..12-31.")
    A("- Survivorship bias on NDX selection pre-2017 (~28% delisted tickers missing from PIT prices); "
      "post-2020 PIT coverage clean. This affects BOTH arms equally (same selection).")
    A("- Single 18y in-sample. NDX PIT data starts 2006-01, so ext window NDX leg is near-cash pre-data; "
      "clean 18y is the decisive lens. No adoption without explicit user confirmation.")

    Path(ROOT / "research" / "ndx_gate_drop_findings.md").write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
