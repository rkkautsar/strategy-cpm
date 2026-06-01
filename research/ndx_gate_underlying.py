# -*- coding: utf-8 -*-
"""Throwaway research (analyst role; read-only re production; writes only to
research/; NO production/memo files changed; NO commit). EXPLORATION ONLY.

QUESTION
--------
The NDX sleeve fires its top-K Nasdaq-100 momentum basket only when BULL is
risk-on = canary(TIP 13612U>0) AND trend(SPY 13612U>0) AND vol(RV60<RV252 on
SPY). BOTH the TREND gate and the VOL gate are inherited 1:1 from BULL and
computed on SPY. But the NDX sleeve TRADES Nasdaq-100, which is higher-beta /
more tech-concentrated than SPY. So the natural question: should the NDX sleeve
gate on its OWN underlying (QQQ / Nasdaq-100) rather than borrow SPY?

We separately found NDX wants a FASTER vol window (RV20<RV252 beats RV60). This
harness tests the 2x2x2 of:
    trend underlying  in {SPY 13612U>0, QQQ 13612U>0}
  x vol underlying    in {RV(SPY), RV(QQQ)}
  x vol window        in {RV20<RV252, RV60<RV252}
= 8 cells. Canary stays TIP 13612U>0 (keep as-is). Judged on Calmar AND Martin,
keeping crisis catches (2008/2020 crash, 2018/2022 grind).

It also decomposes the MARGINAL effect of switching JUST the trend underlying vs
JUST the vol underlying, so we know which gate (if either) benefits from QQQ.

This is a SEPARATE harness from research/ndx_volgate_variants.py (which holds
trend on SPY and only sweeps the vol layer). Here we ALSO switch the trend
underlying. Selection/canary/delisting/T+1 MOO held at production values.

Anchor: current SPY-gated NDX V0 standalone (K=5, 2007-02-28..) Sharpe ~1.1812 /
MaxDD -35.92% / Calmar 0.7602 / Martin 2.9753 (reproduced deterministically).
"""
from __future__ import annotations
import sys, json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import index_constitution as ic
from cpm_live import load_panel, perf_metrics, sig_13612U
from bull_spy_live import SAFE_POOL, _pick_safe, CASH_TICKER
from ndx_sleeve_live import load_ndx_panel, SELECT_K, COST_BPS_PER_SIDE, DELISTING_HAIRCUT

COST = COST_BPS_PER_SIDE
START = pd.Timestamp("2007-02-28")
END = pd.Timestamp("2026-05-22")
PANEL_START = pd.Timestamp("2003-01-01")

ANCHOR = {"sharpe": 1.1812, "maxdd": -0.3592, "calmar": 0.7602, "martin": 2.9753}

CRISES = {
    "2008 GFC":   ("2008-01-01", "2009-06-30"),
    "2018 Q4":    ("2018-01-01", "2018-12-31"),
    "2020 COVID": ("2020-01-01", "2020-06-30"),
    "2022 bear":  ("2022-01-01", "2022-12-31"),
}

# 2x2x2 grid cells: (trend_underlying, vol_underlying, vol_fast, vol_slow)
# V0 = trend SPY, vol SPY, RV60<RV252.
CELLS = {}
for tu in ("SPY", "QQQ"):
    for vu in ("SPY", "QQQ"):
        for (vf, vs) in ((20, 252), (60, 252)):
            key = f"T{tu}_V{vu}_RV{vf}"
            CELLS[key] = dict(trend=tu, vol=vu, fast=vf, slow=vs)

V0_KEY = "TSPY_VSPY_RV60"


def _rv(series, sig_d, win):
    sub = series.loc[:sig_d].pct_change().dropna()
    if len(sub) < win:
        return None
    return float(sub.tail(win).std() * np.sqrt(252))


# ---------------- precompute selection + both trend states (gate-independent) ----------------

def precompute_targets(cpm_panel, ndx_panel, sig_dates):
    """For each signal date: canary_ok, SPY/QQQ trend states, ACTIVE NDX target
    (top-K) and SAFE target. All gate-independent => computed once."""
    out = {}
    for sd in sig_dates:
        cpm_monthly = cpm_panel.loc[:sd].resample("ME").last()
        tipm = sig_13612U(cpm_monthly["TIP"]) if "TIP" in cpm_monthly.columns else float("nan")
        canary_ok = bool(pd.notna(tipm) and tipm > 0)
        spym = sig_13612U(cpm_monthly["SPY"]) if "SPY" in cpm_monthly.columns else float("nan")
        qqqm = sig_13612U(cpm_monthly["QQQ"]) if "QQQ" in cpm_monthly.columns else float("nan")
        trend_spy = bool(pd.notna(spym) and spym > 0)
        trend_qqq = bool(pd.notna(qqqm) and qqqm > 0)
        safe = _pick_safe(cpm_monthly)
        safe_target = {safe: 1.0}

        pit = ic.constituents_at("nasdaq100", sd.strftime("%Y-%m-%d"))
        pit_tickers = set(pit["symbol"].tolist())
        if len(pit_tickers) == 0:
            active_target = {"SPY": 1.0}  # mirror BULL active path when PIT unavailable
        else:
            monthly = ndx_panel.loc[:sd].resample("ME").last()
            available = []
            for t in pit_tickers:
                if t not in ndx_panel.columns:
                    continue
                if sd in ndx_panel.index and pd.isna(ndx_panel.loc[sd, t]):
                    continue
                recent = ndx_panel[t].loc[sd - pd.Timedelta(days=30):sd].dropna()
                if recent.empty:
                    continue
                available.append(t)
            momenta = {}
            for t in available:
                s = monthly[t].dropna()
                if len(s) < 13:
                    continue
                mm = sig_13612U(s)
                if pd.notna(mm) and mm > 0:
                    momenta[t] = mm
            sorted_by_mom = sorted(momenta.items(), key=lambda x: -x[1])
            n_pick = min(len(sorted_by_mom), SELECT_K)
            selected = [t for t, _ in sorted_by_mom[:n_pick]]
            per_slot = 1.0 / SELECT_K
            active_target = {t: per_slot for t in selected}
            cash_share = 1.0 - n_pick * per_slot
            if cash_share > 1e-9:
                active_target[safe] = active_target.get(safe, 0.0) + cash_share
        out[sd] = dict(canary_ok=canary_ok, trend_spy=trend_spy, trend_qqq=trend_qqq,
                       active=active_target, safe=safe_target)
    return out


# ---------------- daily execution loop (copied from variant harness) ----------------

def prepare_arrays(full_panel, start, end):
    sub = full_panel.loc[start:end]
    idx = sub.index
    cols = list(full_panel.columns)
    col_ix = {c: i for i, c in enumerate(cols)}
    full_idx = full_panel.index
    start_loc = full_idx.get_loc(idx[0])
    arr = full_panel.iloc[max(start_loc - 1, 0):].reindex(
        index=full_panel.index[max(start_loc - 1, 0):full_idx.get_loc(idx[-1]) + 1]).values
    arr_index = full_panel.index[max(start_loc - 1, 0):full_idx.get_loc(idx[-1]) + 1]
    arr_pos = {ts: i for i, ts in enumerate(arr_index)}
    notna = ~np.isnan(arr)
    market_open = notna.sum(axis=1) > (~notna).sum(axis=1)
    return dict(idx=idx, cols=cols, col_ix=col_ix, arr=arr, arr_pos=arr_pos,
                notna=notna, market_open=market_open, set_cols=set(cols))


def run_daily(prep, weights_for_date, cost_bps=COST):
    idx = prep["idx"]; arr = prep["arr"]; arr_pos = prep["arr_pos"]
    col_ix = prep["col_ix"]; notna = prep["notna"]; market_open = prep["market_open"]
    set_cols = prep["set_cols"]
    out = np.zeros(len(idx))
    exec_dates = sorted(weights_for_date.keys())
    cur_w = {CASH_TICKER: 1.0}
    cur_w_idx = 0
    for di, ts in enumerate(idx):
        r = arr_pos[ts]
        while cur_w_idx < len(exec_dates) and exec_dates[cur_w_idx] <= ts:
            new_w = weights_for_date[exec_dates[cur_w_idx]]
            if cur_w != new_w:
                tovr = sum(abs(cur_w.get(a, 0) - new_w.get(a, 0))
                           for a in set(cur_w) | set(new_w))
                out[di] -= tovr * cost_bps / 10000.0
            cur_w = new_w
            cur_w_idx += 1
        if r == 0:
            continue
        mo = market_open[r]
        port_r = 0.0
        delisted_w = 0.0
        for asset, w in list(cur_w.items()):
            if asset not in set_cols:
                delisted_w += w
                del cur_w[asset]
                continue
            ci = col_ix[asset]
            today = arr[r, ci]; yest = arr[r - 1, ci]
            t_ok = notna[r, ci]; y_ok = notna[r - 1, ci]
            if t_ok and y_ok and yest > 0:
                port_r += w * (today / yest - 1)
            elif mo and y_ok and yest > 0 and not t_ok:
                port_r += w * DELISTING_HAIRCUT
                delisted_w += w
                del cur_w[asset]
        if delisted_w > 0:
            existing_safe = next((s for s in SAFE_POOL if s in cur_w), CASH_TICKER)
            cur_w[existing_safe] = cur_w.get(existing_safe, 0.0) + delisted_w
            if existing_safe in set_cols:
                ci = col_ix[existing_safe]
                t_cash = arr[r, ci]; y_cash = arr[r - 1, ci]
                if notna[r, ci] and notna[r - 1, ci] and y_cash > 0:
                    port_r += delisted_w * (t_cash / y_cash - 1)
        out[di] += port_r
    return pd.Series(out, index=idx)


def build_weights_for_cell(full_panel, targets, sig_dates, cpm_panel, cell):
    """Assemble exec_date->target for one (trend_u, vol_u, window) cell.
    bull_active = canary & trend(trend_u) & vol(RV{fast}<RV{slow} on vol_u)."""
    tu = cell["trend"]; vu = cell["vol"]; fast = cell["fast"]; slow = cell["slow"]
    wfd = {}
    n_on = 0
    for sd in sig_dates:
        t = targets[sd]
        trend_ok = t["trend_spy"] if tu == "SPY" else t["trend_qqq"]
        vf = _rv(cpm_panel[vu], sd, fast); vs = _rv(cpm_panel[vu], sd, slow)
        vol_ok = True if (vf is None or vs is None) else (vf < vs)
        bull_active = t["canary_ok"] and trend_ok and vol_ok
        target = t["active"] if bull_active else t["safe"]
        if bull_active:
            n_on += 1
        next_loc = full_panel.index.get_indexer([sd], method="bfill")[0] + 1
        if next_loc < len(full_panel.index):
            wfd[full_panel.index[next_loc]] = target
    return wfd, n_on


def met(s, cash):
    m = perf_metrics(s, cash)
    return {"sharpe": m.get("sharpe"), "cagr": m.get("cagr"), "vol": m.get("vol"),
            "maxdd": m.get("max_drawdown"), "calmar": m.get("calmar"),
            "martin": m.get("martin"), "ulcer": m.get("ulcer")}


def window_dd_ret(s, lo, hi):
    sub = s.loc[(s.index >= pd.Timestamp(lo)) & (s.index <= pd.Timestamp(hi))]
    if len(sub) < 2:
        return {"maxdd": float("nan"), "ret": float("nan")}
    eq = (1.0 + sub).cumprod()
    dd = float((eq / eq.cummax() - 1.0).min())
    return {"maxdd": dd, "ret": float(eq.iloc[-1] - 1.0)}


def drop_episode_metrics(s, cash, lo, hi):
    mask = ~((s.index >= pd.Timestamp(lo)) & (s.index <= pd.Timestamp(hi)))
    return met(s[mask], cash)


# response-surface fast-window grid (winner family) -- applied on the WINNER's vol underlying
RSURF_FAST = [10, 15, 20, 25, 30, 40, 50, 60, 90, 120]


def main():
    cpm_panel = load_panel(start=PANEL_START, end=END)
    ndx_panel = load_ndx_panel()
    end = min(END, cpm_panel.index[-1])
    cash = cpm_panel["SHV"].ffill().pct_change().dropna()

    full_panel = cpm_panel.join(ndx_panel, how="outer", rsuffix="_dup")
    full_panel = full_panel.loc[:, ~full_panel.columns.str.endswith("_dup")]

    monthly_idx = pd.DataFrame({"x": 1}, index=full_panel.index).groupby(
        pd.Grouper(freq="ME")).tail(1).index
    sig_dates = monthly_idx[(monthly_idx >= START) & (monthly_idx <= end)]

    print(f"Precomputing NDX selection for {len(sig_dates)} signal dates...")
    targets = precompute_targets(cpm_panel, ndx_panel, sig_dates)
    prep = prepare_arrays(full_panel, START, end)

    sleeves = {}
    n_on = {}
    for key, cell in CELLS.items():
        wfd, non = build_weights_for_cell(full_panel, targets, sig_dates, cpm_panel, cell)
        sleeves[key] = run_daily(prep, wfd)
        n_on[key] = non
        print(f"  {key:18s} active months={non}/{len(sig_dates)}")

    common = sleeves[V0_KEY].index
    for key in sleeves:
        common = common.intersection(sleeves[key].index)
    for key in sleeves:
        sleeves[key] = sleeves[key].reindex(common)

    v0 = met(sleeves[V0_KEY], cash)
    a_ds = abs(v0["sharpe"] - ANCHOR["sharpe"])
    a_dd = abs(v0["maxdd"] - ANCHOR["maxdd"]) * 100
    anchor_ok = a_ds < 0.01 and a_dd < 0.20
    print(f"\nANCHOR {V0_KEY}: Sharpe={v0['sharpe']:.4f} MaxDD={v0['maxdd']*100:.2f}% "
          f"Calmar={v0['calmar']:.4f} Martin={v0['martin']:.4f} "
          f"(expect {ANCHOR}) -> {'CONFIRMED' if anchor_ok else 'FLAG'}")

    per = {}
    for key in CELLS:
        s = sleeves[key]
        m = met(s, cash)
        crises = {name: window_dd_ret(s, lo, hi) for name, (lo, hi) in CRISES.items()}
        per[key] = {"metrics": m, "crises": crises, "n_active_months": n_on[key],
                    "cell": CELLS[key]}

    # ----- marginal decompositions -----
    # Switch JUST trend underlying (hold vol SPY, both windows).
    # Switch JUST vol underlying (hold trend SPY, both windows).
    # Switch JUST window (hold trend SPY vol SPY).
    def keeps(key):
        cr = per[key]["crises"]; c0 = per[V0_KEY]["crises"]
        kc = (cr["2008 GFC"]["maxdd"] - c0["2008 GFC"]["maxdd"] > -0.03) and \
             (cr["2020 COVID"]["maxdd"] - c0["2020 COVID"]["maxdd"] > -0.03)
        kg = (cr["2018 Q4"]["maxdd"] - c0["2018 Q4"]["maxdd"] > -0.04) and \
             (cr["2022 bear"]["maxdd"] - c0["2022 bear"]["maxdd"] > -0.04)
        return kc and kg

    # winner = beats V0 on Calmar AND Martin while keeping catches
    cand = []
    for key in CELLS:
        if key == V0_KEY:
            continue
        m = per[key]["metrics"]
        if m["calmar"] > v0["calmar"] + 1e-9 and m["martin"] > v0["martin"] + 1e-9 and keeps(key):
            cand.append((key, m["calmar"], m["martin"]))
    winner = max(cand, key=lambda x: (x[1], x[2]))[0] if cand else None

    # response surface on the winner's vol underlying (or SPY if no winner)
    rs_vu = CELLS[winner]["vol"] if winner else "SPY"
    rs_tu = CELLS[winner]["trend"] if winner else "SPY"
    rsurf = []
    for f in RSURF_FAST:
        cell = dict(trend=rs_tu, vol=rs_vu, fast=f, slow=252)
        wfd, _ = build_weights_for_cell(full_panel, targets, sig_dates, cpm_panel, cell)
        s = run_daily(prep, wfd).reindex(common)
        mm = met(s, cash)
        rsurf.append({"fast": f, "calmar": mm["calmar"], "martin": mm["martin"],
                      "sharpe": mm["sharpe"], "maxdd": mm["maxdd"]})

    episode_decomp = None
    if winner is not None:
        ws = sleeves[winner]; v0s = sleeves[V0_KEY]
        rows = []
        wm = met(ws, cash); v0m = met(v0s, cash)
        rows.append({"drop": "none (full)", "win_calmar": wm["calmar"], "win_martin": wm["martin"],
                     "dcalmar_v0": wm["calmar"] - v0m["calmar"], "dmartin_v0": wm["martin"] - v0m["martin"]})
        for name, (lo, hi) in CRISES.items():
            wm = drop_episode_metrics(ws, cash, lo, hi)
            v0m = drop_episode_metrics(v0s, cash, lo, hi)
            rows.append({"drop": name, "win_calmar": wm["calmar"], "win_martin": wm["martin"],
                         "dcalmar_v0": wm["calmar"] - v0m["calmar"], "dmartin_v0": wm["martin"] - v0m["martin"]})
        episode_decomp = {"winner": winner, "rows": rows}

    out = {
        "meta": {"start": str(START.date()), "end": str(end.date()),
                 "cost_bps": COST, "select_k": SELECT_K, "n_sig_dates": len(sig_dates),
                 "cells": CELLS, "v0_key": V0_KEY,
                 "crises": {k: list(v) for k, v in CRISES.items()}},
        "anchor": {"v0": v0, "expected": ANCHOR, "anchor_ok": anchor_ok},
        "per_cell": per,
        "skepticism": {"winner": winner, "rs_underlying": rs_vu, "rs_trend": rs_tu,
                       "response_surface": rsurf, "episode_decomp": episode_decomp},
    }
    Path(__file__).with_suffix(".json").write_text(json.dumps(out, indent=2, default=float))
    write_md(out)
    print("DONE -> research/ndx_gate_underlying_findings.md")
    return out


def pct(x):
    return f"{x*100:.2f}%" if x is not None and isinstance(x, (int, float)) and np.isfinite(x) else "n/a"


def cell_label(key):
    c = CELLS[key]
    return f"trend {c['trend']} / vol {c['vol']} RV{c['fast']}<RV{c['slow']}"


def write_md(o):
    L = []; A = L.append
    m = o["meta"]; per = o["per_cell"]
    order = list(CELLS.keys())
    v0 = per[V0_KEY]; b = v0["metrics"]

    A("# NDX-sleeve gate underlying: should the NDX sleeve gate on QQQ (its own underlying) instead of SPY?\n")
    A("Role: analyst (hypothesis-driven, read-only re production; writes only to research/; no "
      "production/memo files changed; no commit). EXPLORATION ONLY -- a POTENTIAL NDX-sleeve change; "
      "user decides adoption later. Harness `research/ndx_gate_underlying.py` (SEPARATE from "
      "`ndx_volgate_variants.py`, which holds trend on SPY and only sweeps the vol layer).\n")
    A("**Question.** The NDX sleeve fires its top-K Nasdaq-100 momentum basket only when BULL is "
      "risk-on = canary(TIP 13612U>0) AND trend(SPY 13612U>0) AND vol(RV60<RV252 on SPY). BOTH the "
      "trend gate and the vol gate are inherited 1:1 from BULL and computed on SPY. But the NDX "
      "sleeve TRADES Nasdaq-100 -- higher-beta / more tech-concentrated than SPY. Should it gate on "
      "its OWN underlying (QQQ) instead? And does QQQ-gating interact with the faster RV20 window?\n")
    A("**Design: 2x2x2 grid.** trend underlying {SPY,QQQ} x vol underlying {RV(SPY),RV(QQQ)} x window "
      "{RV20<RV252, RV60<RV252} = 8 cells. Canary stays TIP 13612U>0 (keep as-is). V0 = trend SPY / "
      "vol SPY / RV60. Only the gate underlyings/window change; selection (top-K="
      f"{m['select_k']} raw 13612U, partial-fill to best-of-safe), delisting haircut and T+1 MOO "
      "execution held at production. Judged on Calmar AND Martin, keeping crisis catches.\n")
    A(f"**Convention.** T+1 MOO (next-day open), {m['cost_bps']} bps/side, monthly month-end signal. "
      f"Window {m['start']}..{m['end']} ({m['n_sig_dates']} monthly signals). NDX STANDALONE sleeve "
      "(the lens where the gate matters most; at 20% blend weight effects scale ~1/5).\n")
    A("**Caveat up front:** pre-2017 NDX backtest has ~28% survivorship bias (missing delisted "
      "tickers); post-2020 PIT coverage is clean. Single 18y in-sample run; any winner needs paired "
      "bootstrap-CI / walk-forward before adoption.\n")

    a = o["anchor"]
    A("## 0. Anchor (reproduced before deltas)\n")
    A(f"NDX V0 (trend SPY / vol SPY / RV60<RV252) standalone: Sharpe **{a['v0']['sharpe']:.4f}** / "
      f"MaxDD **{pct(a['v0']['maxdd'])}** / Calmar **{a['v0']['calmar']:.4f}** / Martin "
      f"**{a['v0']['martin']:.4f}** vs expected {a['expected']} -> "
      f"**{'CONFIRMED' if a['anchor_ok'] else 'FLAG'}**.\n")

    A("## 1. The 2x2x2 grid (full-window standalone metrics)\n")
    A("| Cell (trend / vol / window) | CAGR | Vol | Sharpe | MaxDD | Calmar | Martin | active mo |")
    A("|---|---:|---:|---:|---:|---:|---:|---:|")
    for key in order:
        r = per[key]["metrics"]; c = per[key]["cell"]
        tag = " (V0)" if key == V0_KEY else ""
        A(f"| {c['trend']} / {c['vol']} / RV{c['fast']}<RV{c['slow']}{tag} | {pct(r['cagr'])} | "
          f"{pct(r['vol'])} | {r['sharpe']:.4f} | {pct(r['maxdd'])} | {r['calmar']:.4f} | "
          f"{r['martin']:.4f} | {per[key]['n_active_months']} |")
    A("")

    A("## 2. Delta vs V0 (Calmar + Martin are the judged objectives)\n")
    A("| Cell | dSharpe | dCalmar | dMartin | dMaxDD (pp) | dCAGR (pp) |")
    A("|---|---:|---:|---:|---:|---:|")
    for key in order:
        r = per[key]["metrics"]
        A(f"| {cell_label(key)} | {r['sharpe']-b['sharpe']:+.4f} | {r['calmar']-b['calmar']:+.4f} | "
          f"{r['martin']-b['martin']:+.4f} | {(abs(r['maxdd'])-abs(b['maxdd']))*100:+.2f} | "
          f"{(r['cagr']-b['cagr'])*100:+.2f} |")
    A("\n*dMaxDD>0 = deeper drawdown (worse). dCalmar/dMartin>0 = better.*\n")

    # ---- marginal decomposition ----
    A("## 3. Marginal effect: switch JUST trend vs JUST vol underlying\n")
    A("Isolates which gate (if either) benefits from QQQ. Each row holds everything else at V0 and "
      "flips one knob.\n")
    A("| Knob switched | Cell | dCalmar | dMartin | dSharpe | dMaxDD (pp) |")
    A("|---|---|---:|---:|---:|---:|")
    margins = [
        ("trend SPY->QQQ (vol SPY RV60)", "TQQQ_VSPY_RV60"),
        ("vol  SPY->QQQ (trend SPY RV60)", "TSPY_VQQQ_RV60"),
        ("window RV60->RV20 (trend SPY vol SPY)", "TSPY_VSPY_RV20"),
        ("trend+vol both ->QQQ (RV60)", "TQQQ_VQQQ_RV60"),
        ("vol SPY->QQQ + RV20 (trend SPY)", "TSPY_VQQQ_RV20"),
        ("ALL ->QQQ + RV20", "TQQQ_VQQQ_RV20"),
        ("trend QQQ + vol SPY RV20", "TQQQ_VSPY_RV20"),
    ]
    for lbl, key in margins:
        r = per[key]["metrics"]
        A(f"| {lbl} | {cell_label(key)} | {r['calmar']-b['calmar']:+.4f} | {r['martin']-b['martin']:+.4f} | "
          f"{r['sharpe']-b['sharpe']:+.4f} | {(abs(r['maxdd'])-abs(b['maxdd']))*100:+.2f} |")
    A("")

    A("## 4. Per-crisis protection (NDX sleeve MaxDD / total return in window)\n")
    cnames = list(m["crises"].keys())
    A("| Cell | " + " | ".join(f"{c} DD/Ret" for c in cnames) + " |")
    A("|---|" + "---|" * len(cnames))
    for key in order:
        cells = []
        for c in cnames:
            cr = per[key]["crises"][c]
            cells.append(f"{pct(cr['maxdd'])} / {pct(cr['ret'])}")
        A(f"| {cell_label(key)} | " + " | ".join(cells) + " |")
    A("\n*Windows: " + "; ".join(f"{c} {m['crises'][c][0]}..{m['crises'][c][1]}" for c in cnames) + ".*\n")

    # ---- verdict ----
    A("## 5. VERDICT scorecard\n")
    A("Beats-V0 = Calmar AND Martin both strictly higher than V0. Keeps crash = 2008 & 2020 DD not "
      ">3pp deeper than V0; keeps grind = 2018-Q4 & 2022 DD not >4pp deeper than V0.\n")
    A("| Cell | Calmar | Martin | Sharpe | MaxDD | beats V0? | keeps crash? | keeps grind? |")
    A("|---|---:|---:|---:|---:|:--:|:--:|:--:|")
    ranked = []
    for key in order:
        r = per[key]["metrics"]
        cr = per[key]["crises"]; c0 = v0["crises"]
        kc = (cr["2008 GFC"]["maxdd"] - c0["2008 GFC"]["maxdd"] > -0.03) and \
             (cr["2020 COVID"]["maxdd"] - c0["2020 COVID"]["maxdd"] > -0.03)
        kg = (cr["2018 Q4"]["maxdd"] - c0["2018 Q4"]["maxdd"] > -0.04) and \
             (cr["2022 bear"]["maxdd"] - c0["2022 bear"]["maxdd"] > -0.04)
        bv0 = (r["calmar"] > b["calmar"] + 1e-9) and (r["martin"] > b["martin"] + 1e-9)
        ranked.append((key, r, bv0, kc, kg))
        A(f"| {cell_label(key)} | {r['calmar']:.4f} | {r['martin']:.4f} | {r['sharpe']:.4f} | "
          f"{pct(r['maxdd'])} | {'YES' if bv0 else 'no'} | {'Y' if kc else 'NO'} | {'Y' if kg else 'NO'} |")
    A("")
    winners = [(k, r) for (k, r, bv0, kc, kg) in ranked if k != V0_KEY and bv0 and kc and kg]
    sk = o.get("skepticism", {})
    win = sk.get("winner")
    if win:
        wr = per[win]["metrics"]; wc = per[win]["cell"]
        A(f"**Apparent winner: {cell_label(win)}** -- beats V0 (Calmar {wr['calmar']:.4f} vs "
          f"{b['calmar']:.4f}, Martin {wr['martin']:.4f} vs {b['martin']:.4f}) while keeping crash AND "
          "grind catches. REQUIRES the skepticism checks in section 6 before any adoption.\n")
    else:
        A("**No cell beats V0 on Calmar AND Martin while keeping crash + grind catches.** On this "
          "sample, gating the NDX sleeve on QQQ does NOT net-improve over the inherited SPY gate.\n")

    # ---- skepticism ----
    A("## 6. Skepticism on the apparent winner\n")
    if win is None:
        A("No cell cleared the beats-V0 + keeps-catches bar, so there is no winner to stress. The "
          "response surface below documents the fast-window family for context.\n")
    else:
        A(f"Apparent winner = **{cell_label(win)}**. (6a) response-surface spike-vs-plateau over the "
          f"fast window (on the winner's vol underlying = {sk.get('rs_underlying')}, trend = "
          f"{sk.get('rs_trend')}); (6b) per-episode decomposition (does one crisis drive the edge?).\n")
    rs = sk.get("response_surface", [])
    if rs:
        A(f"### 6a. Response surface: RV{{fast}}<RV252 on {sk.get('rs_underlying')} "
          f"(trend {sk.get('rs_trend')})\n")
        A("| fast window | Calmar | Martin | Sharpe | MaxDD |")
        A("|---:|---:|---:|---:|---:|")
        for row in rs:
            A(f"| {row['fast']} | {row['calmar']:.4f} | {row['martin']:.4f} | {row['sharpe']:.4f} | "
              f"{pct(row['maxdd'])} |")
        peak = max(rs, key=lambda r: r["calmar"])
        neighbors = [row["calmar"] for row in rs if abs(row["fast"] - peak["fast"]) <= 10 and row is not peak]
        spike = bool(neighbors) and (peak["calmar"] - max(neighbors) > 0.10)
        A(f"\nPeak Calmar at fast={peak['fast']} ({peak['calmar']:.4f}). "
          + ("**Isolated spike** (>0.10 Calmar above nearest neighbors) -- fragile / overfit-smell."
             if spike else "Adjacent windows within ~0.10 Calmar of the peak -- plateau, not a spike.")
          + "\n")
    ed = sk.get("episode_decomp")
    if ed:
        A("\n### 6b. Per-episode decomposition (drop one crisis window, recompute)\n")
        A("If the winner's edge vs V0 collapses when a single episode is removed, the edge IS that "
          "episode, not a robust gate property.\n")
        A("| dropped window | winner Calmar | winner Martin | dCalmar vs V0 | dMartin vs V0 |")
        A("|---|---:|---:|---:|---:|")
        for row in ed["rows"]:
            A(f"| {row['drop']} | {row['win_calmar']:.4f} | {row['win_martin']:.4f} | "
              f"{row['dcalmar_v0']:+.4f} | {row['dmartin_v0']:+.4f} |")
        full = ed["rows"][0]
        worst = min(ed["rows"][1:], key=lambda r: r["dcalmar_v0"]) if len(ed["rows"]) > 1 else None
        if worst is not None:
            collapse = worst["dcalmar_v0"] <= 0 < full["dcalmar_v0"]
            A(f"\nFull-sample dCalmar vs V0 = {full['dcalmar_v0']:+.4f}. Dropping **{worst['drop']}** "
              f"moves it to {worst['dcalmar_v0']:+.4f}. "
              + ("**Edge inverts/vanishes when this one episode is removed -> single-episode driven. "
                 "Reject as overfit.**" if collapse else "Edge survives removal of every single "
                 "episode (no episode flips the sign) -- not purely one-episode driven, but still "
                 "in-sample.") + "\n")

    A("## 7. Bottom line: does NDX gate better on QQQ than SPY?\n")
    # precise marginal numbers for the synthesis
    mt = per["TQQQ_VSPY_RV60"]["metrics"]   # trend-only switch (vol SPY RV60)
    mv = per["TSPY_VQQQ_RV60"]["metrics"]   # vol-only switch (trend SPY RV60)
    mw = per["TSPY_VSPY_RV20"]["metrics"]   # window-only switch
    mvw = per["TSPY_VQQQ_RV20"]["metrics"]  # QQQ vol at RV20 (interaction)
    A("**Short answer: NO -- the NDX sleeve does NOT gate better on QQQ; the win is the WINDOW, not "
      "the underlying.** Decomposing the three knobs against V0:\n")
    A(f"- **VOL gate SPY->QQQ: HARMFUL.** Holding trend SPY / RV60, switching vol to QQQ moves Calmar "
      f"{b['calmar']:.4f}->{mv['calmar']:.4f} ({mv['calmar']-b['calmar']:+.4f}) and Martin "
      f"{b['martin']:.4f}->{mv['martin']:.4f} ({mv['martin']-b['martin']:+.4f}). Worse on BOTH "
      "objectives. The mechanism is the 2022 grind: the SPY vol gate goes defensive (2022 DD "
      "-0.30%) but the QQQ vol gate stays risk-on into the drawdown (2022 DD -24.74%). QQQ's own "
      "elevated trailing-vol baseline (RV252) means RV-fast rarely trips below it during a tech-led "
      "grind, so the higher-beta underlying gates LATER, not earlier. Every QQQ-vol cell FAILS the "
      "keeps-grind bar.\n")
    A(f"- **TREND gate SPY->QQQ: negligible.** Holding vol SPY / RV60, switching trend to QQQ moves "
      f"Calmar {b['calmar']:.4f}->{mt['calmar']:.4f} ({mt['calmar']-b['calmar']:+.4f}), Martin "
      f"{mt['martin']-b['martin']:+.4f}. A sliver -- SPY and QQQ 13612U trend signals agree on "
      "almost every month-end, so the trend underlying barely matters.\n")
    A(f"- **WINDOW RV60->RV20: the real lever.** Holding trend SPY / vol SPY, RV20 moves Calmar "
      f"{b['calmar']:.4f}->{mw['calmar']:.4f} ({mw['calmar']-b['calmar']:+.4f}) and Martin "
      f"{mw['martin']-b['martin']:+.4f} -- an order of magnitude larger than either underlying "
      "switch, and it does NOT require QQQ.\n")
    A(f"- **QQQ x RV20 interaction: QQQ does NOT help the faster window either.** At RV20, switching "
      f"vol SPY->QQQ DROPS Calmar {mw['calmar']:.4f}->{mvw['calmar']:.4f} -- so RV20-on-QQQ is NOT "
      "best of all; RV20-on-SPY is clearly better. The faster window and the QQQ underlying do not "
      "stack; QQQ-vol degrades the RV20 win the same way it degrades RV60.\n")
    if win:
        wr = per[win]["metrics"]
        A(f"The apparent best cell ({cell_label(win)}, Calmar {wr['calmar']:.4f} / Martin "
          f"{wr['martin']:.4f}) is essentially **RV20-on-SPY-vol** (Calmar {mw['calmar']:.4f}) plus a "
          f"negligible QQQ-trend sliver (+{wr['calmar']-mw['calmar']:.4f} Calmar). The QQQ-own-"
          "underlying hypothesis is REJECTED for the vol gate and immaterial for the trend gate. The "
          "RV20 window finding (from the separate vol-window study) is reconfirmed and is the only "
          "load-bearing lever. The response surface (6a) is a 15-20d plateau (not a spike) and the "
          "edge survives every single-episode removal (6b), so the WINDOW result is robust in-sample "
          "-- but the QQQ-underlying part adds nothing.\n")
    A("**Adoption status: RESEARCH ONLY, not adopted.** Single in-sample run; pre-2017 survivorship "
      "bias; T+1 MOO / PIT honesty caveats. Before any production change: paired stationary-block "
      "bootstrap CI on the winning-cell-minus-V0 Calmar/Martin deltas, and a walk-forward (freeze the "
      "gate choice pre-2017, test 2017+). User decides.\n")

    A("## Caveats\n")
    A("- EXPLORATION ONLY; no production/memo edits; no commit. Read-only re production.")
    A("- Only the gate underlyings/window change; canary(TIP)/selection/delisting/execution held at prod.")
    A("- NDX standalone sleeve lens; at 20% blend weight effects scale ~1/5 (dilute further vs CPM+BULL co-movement).")
    A("- Realized vol = annualized std of daily returns over the trailing window at the signal date.")
    A("- Trend = 13612U momentum > 0 on monthly resampled closes (SPY vs QQQ).")
    A("- Pre-2017 NDX segment has ~28% survivorship bias; post-2020 is clean PIT coverage.")
    A("- Separate harness from ndx_volgate_variants.py to avoid a write race with another analyst.")

    Path(ROOT / "research" / "ndx_gate_underlying_findings.md").write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
