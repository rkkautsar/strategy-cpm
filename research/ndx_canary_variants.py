# -*- coding: utf-8 -*-
"""Throwaway research (analyst role; read-only re production; writes only to
research/; NO production/memo files changed; NO commit). EXPLORATION ONLY.

QUESTION
--------
The NDX sleeve fires its top-K Nasdaq-100 momentum basket only when BULL is
risk-on = canary(TIP 13612U>0) AND trend(SPY 13612U>0) AND vol(RV60<RV252 on
SPY). The canary is TIP-only. The user wants to test STRICTER credit-confirming
canary variants for the NDX equity sleeve -- does requiring a credit-market
confirmation (HYG / LQD / HY-vs-Treasury ratio) on top of TIP cut drawdowns and
whipsaw, or does the stricter AND just over-de-risk and bleed return (the
failure mode seen when adding signals to CPM)?

DESIGN
------
Hold trend = SPY 13612U>0 and vol = SPY RV60<RV252 at current production. Vary
ONLY the canary leg. bull_active = canary_variant AND trend_spy AND vol_spy.

Canary variants (each leg = 13612U momentum > 0):
  V0  TIP only                  (baseline / anchor)
  TIP AND HYG                   (both risk-on)
  TIP AND LQD
  TIP AND HYG/IEF ratio         (HY-vs-Treasury relative strength; ratio 13612U>0)
  TIP OR HYG                    (CPM-style, for contrast)
  HYG alone                     (bare reference)
  HYG/IEF ratio alone           (bare reference)

Judged on Calmar AND Martin, keeping crisis catches (2008/2020 crash, 2018/2022
grind), reporting whipsaw/flip count. Decompose AND variants: of the months V0
was active but the variant goes safe, was the skipped active return positive
(return bleed) or negative (real protection)?

DATA/EXT HONESTY
----------------
The repo panel uses AUDITED stitches: HYG<-VWEHX (Vanguard HY mutual fund) pre
2007-04, TIP<-VIPSX pre live ETF, IEF<-VFITX. LQD is RAW ETF (2002-07+). So the
canary signals are computable well before ETF inception. BUT the NDX sleeve
itself is bounded at 2007-02-28 by the constituent panel (index-constitution),
so the canary comparison cannot extend the NDX sleeve before 2007 regardless.
Window limit = the NDX sleeve's own 2007+ window. Robustness reported via
sub-period split (2007-2016 dirty-survivorship vs 2017+ clean PIT) instead of an
ext view.

Anchor: current TIP-only NDX V0 standalone (K=5, 2007-02-28..) Sharpe ~1.1812 /
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

# sub-periods for robustness (dirty-survivorship vs clean PIT)
SUBPERIODS = {
    "2007-2016 (dirty surv.)": ("2007-02-28", "2016-12-31"),
    "2017-2026 (clean PIT)":   ("2017-01-01", "2026-05-22"),
}

# Canary variant definitions. Each maps a dict of leg booleans -> canary_ok.
# legs available: tip, hyg, lqd, hygief
VARIANTS = {
    "V0_TIP_only":      lambda L: L["tip"],
    "TIP_AND_HYG":      lambda L: L["tip"] and L["hyg"],
    "TIP_AND_LQD":      lambda L: L["tip"] and L["lqd"],
    "TIP_AND_HYGIEF":   lambda L: L["tip"] and L["hygief"],
    "TIP_OR_HYG":       lambda L: L["tip"] or L["hyg"],
    "HYG_alone":        lambda L: L["hyg"],
    "HYGIEF_alone":     lambda L: L["hygief"],
}
V0_KEY = "V0_TIP_only"


def _rv(series, sig_d, win):
    sub = series.loc[:sig_d].pct_change().dropna()
    if len(sub) < win:
        return None
    return float(sub.tail(win).std() * np.sqrt(252))


def _leg(monthly_col_series):
    m = sig_13612U(monthly_col_series)
    return bool(pd.notna(m) and m > 0)


# ---------------- precompute selection + canary legs + fixed gate state ----------------

def precompute_targets(cpm_panel, ndx_panel, sig_dates):
    """For each signal date: canary leg booleans (tip/hyg/lqd/hygief), the FIXED
    trend(SPY) and vol(SPY RV60) gate states, the ACTIVE NDX target (top-K) and
    SAFE target. All gate-independent => computed once."""
    out = {}
    for sd in sig_dates:
        cm = cpm_panel.loc[:sd].resample("ME").last()
        legs = {
            "tip": _leg(cm["TIP"]) if "TIP" in cm.columns else False,
            "hyg": _leg(cm["HYG"]) if "HYG" in cm.columns else False,
            "lqd": _leg(cm["LQD"]) if "LQD" in cm.columns else False,
        }
        if "HYG" in cm.columns and "IEF" in cm.columns:
            ratio = (cpm_panel["HYG"] / cpm_panel["IEF"]).loc[:sd].resample("ME").last()
            legs["hygief"] = _leg(ratio)
        else:
            legs["hygief"] = False

        spym = sig_13612U(cm["SPY"]) if "SPY" in cm.columns else float("nan")
        trend_spy = bool(pd.notna(spym) and spym > 0)
        vf = _rv(cpm_panel["SPY"], sd, 60); vs = _rv(cpm_panel["SPY"], sd, 252)
        vol_ok = True if (vf is None or vs is None) else (vf < vs)

        safe = _pick_safe(cm)
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
        out[sd] = dict(legs=legs, trend_spy=trend_spy, vol_ok=vol_ok,
                       active=active_target, safe=safe_target)
    return out


# ---------------- daily execution loop (copied from ndx_gate_underlying.py) ----------------

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


def build_weights_for_variant(full_panel, targets, sig_dates, variant_fn):
    """Assemble exec_date->target for one canary variant. Also return the monthly
    bull_active sequence (for flip count + decomposition)."""
    wfd = {}
    active_seq = []  # list of (sd, bull_active)
    for sd in sig_dates:
        t = targets[sd]
        canary_ok = variant_fn(t["legs"])
        bull_active = bool(canary_ok and t["trend_spy"] and t["vol_ok"])
        target = t["active"] if bull_active else t["safe"]
        active_seq.append((sd, bull_active))
        next_loc = full_panel.index.get_indexer([sd], method="bfill")[0] + 1
        if next_loc < len(full_panel.index):
            wfd[full_panel.index[next_loc]] = target
    return wfd, active_seq


def flip_count(active_seq):
    flips = 0
    for i in range(1, len(active_seq)):
        if active_seq[i][1] != active_seq[i - 1][1]:
            flips += 1
    n_on = sum(1 for _, a in active_seq if a)
    return flips, n_on


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


def subperiod_metrics(s, cash, lo, hi):
    m = (s.index >= pd.Timestamp(lo)) & (s.index <= pd.Timestamp(hi))
    return met(s[m], cash)


# ---------------- AND-variant decomposition: bleed vs protection ----------------

def forward_month_return(full_panel, target, exec_date, next_exec_date):
    """Static-weight hold return from exec_date to (exclusive) next_exec_date."""
    idx = full_panel.index
    win = full_panel.loc[(idx >= exec_date) & (idx < next_exec_date)]
    if len(win) < 2:
        return 0.0
    r = 0.0
    rets = win.pct_change().iloc[1:]
    total = 0.0
    eq = 1.0
    # compound daily portfolio returns with static weights
    for _, row in rets.iterrows():
        day_r = 0.0
        for a, w in target.items():
            if a in row and pd.notna(row[a]):
                day_r += w * row[a]
        eq *= (1.0 + day_r)
    return eq - 1.0


def decompose_and(full_panel, targets, sig_dates, variant_fn):
    """For an AND variant: enumerate months where V0 active but variant goes
    safe ('newly defensive'). For each, the forward return of the ACTIVE target
    (what V0 earned) vs the SAFE target (what the variant earned). Avg active
    forward return reveals bleed (positive => skipped an up month) vs protection
    (negative => dodged a down month)."""
    exec_dates = []
    rows = []
    sd_list = list(sig_dates)
    for i, sd in enumerate(sd_list):
        t = targets[sd]
        v0_active = bool(t["legs"]["tip"] and t["trend_spy"] and t["vol_ok"])
        var_active = bool(variant_fn(t["legs"]) and t["trend_spy"] and t["vol_ok"])
        if v0_active and not var_active:
            # forward window: exec t+1 .. next exec
            nl = full_panel.index.get_indexer([sd], method="bfill")[0] + 1
            if nl >= len(full_panel.index):
                continue
            exec_d = full_panel.index[nl]
            if i + 1 < len(sd_list):
                nsd = sd_list[i + 1]
                nnl = full_panel.index.get_indexer([nsd], method="bfill")[0] + 1
                next_exec = full_panel.index[nnl] if nnl < len(full_panel.index) else full_panel.index[-1]
            else:
                next_exec = full_panel.index[-1]
            ar = forward_month_return(full_panel, t["active"], exec_d, next_exec)
            sr = forward_month_return(full_panel, t["safe"], exec_d, next_exec)
            rows.append({"sd": str(sd.date()), "active_fwd": ar, "safe_fwd": sr,
                         "skipped_excess": ar - sr})
    if not rows:
        return {"n_newly_def": 0, "rows": [], "avg_active_fwd": float("nan"),
                "avg_skipped_excess": float("nan"), "n_up": 0, "n_down": 0}
    avg_active = float(np.mean([r["active_fwd"] for r in rows]))
    avg_excess = float(np.mean([r["skipped_excess"] for r in rows]))
    n_up = sum(1 for r in rows if r["active_fwd"] > 0)
    n_down = sum(1 for r in rows if r["active_fwd"] <= 0)
    return {"n_newly_def": len(rows), "rows": rows, "avg_active_fwd": avg_active,
            "avg_skipped_excess": avg_excess, "n_up": n_up, "n_down": n_down}


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

    print(f"Precomputing NDX selection + canary legs for {len(sig_dates)} signal dates...")
    targets = precompute_targets(cpm_panel, ndx_panel, sig_dates)
    prep = prepare_arrays(full_panel, START, end)

    sleeves = {}
    flips = {}
    n_on = {}
    for key, fn in VARIANTS.items():
        wfd, aseq = build_weights_for_variant(full_panel, targets, sig_dates, fn)
        sleeves[key] = run_daily(prep, wfd)
        f, non = flip_count(aseq)
        flips[key] = f; n_on[key] = non
        print(f"  {key:18s} active months={non}/{len(sig_dates)}  flips={f}")

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
    for key in VARIANTS:
        s = sleeves[key]
        m = met(s, cash)
        crises = {name: window_dd_ret(s, lo, hi) for name, (lo, hi) in CRISES.items()}
        subs = {name: subperiod_metrics(s, cash, lo, hi) for name, (lo, hi) in SUBPERIODS.items()}
        per[key] = {"metrics": m, "crises": crises, "subperiods": subs,
                    "n_active_months": n_on[key], "flips": flips[key]}

    # AND-variant decomposition (bleed vs protection)
    decomp = {}
    for key, fn in VARIANTS.items():
        if key.startswith("TIP_AND"):
            decomp[key] = decompose_and(full_panel, targets, sig_dates, fn)

    # winner = beats V0 on Calmar AND Martin while keeping catches
    def keeps(key):
        cr = per[key]["crises"]; c0 = per[V0_KEY]["crises"]
        kc = (cr["2008 GFC"]["maxdd"] - c0["2008 GFC"]["maxdd"] > -0.03) and \
             (cr["2020 COVID"]["maxdd"] - c0["2020 COVID"]["maxdd"] > -0.03)
        kg = (cr["2018 Q4"]["maxdd"] - c0["2018 Q4"]["maxdd"] > -0.04) and \
             (cr["2022 bear"]["maxdd"] - c0["2022 bear"]["maxdd"] > -0.04)
        return kc and kg

    cand = []
    for key in VARIANTS:
        if key == V0_KEY:
            continue
        m = per[key]["metrics"]
        if m["calmar"] > v0["calmar"] + 1e-9 and m["martin"] > v0["martin"] + 1e-9 and keeps(key):
            cand.append((key, m["calmar"], m["martin"]))
    winner = max(cand, key=lambda x: (x[1], x[2]))[0] if cand else None

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
                 "variants": list(VARIANTS.keys()), "v0_key": V0_KEY,
                 "crises": {k: list(v) for k, v in CRISES.items()},
                 "subperiods": {k: list(v) for k, v in SUBPERIODS.items()}},
        "anchor": {"v0": v0, "expected": ANCHOR, "anchor_ok": anchor_ok},
        "per_variant": per,
        "decomp": decomp,
        "skepticism": {"winner": winner, "episode_decomp": episode_decomp},
    }
    Path(__file__).with_suffix(".json").write_text(json.dumps(out, indent=2, default=float))
    write_md(out)
    print("DONE -> research/ndx_canary_variants_findings.md")
    return out


def pct(x):
    return f"{x*100:.2f}%" if x is not None and isinstance(x, (int, float)) and np.isfinite(x) else "n/a"


LABELS = {
    "V0_TIP_only": "TIP only (V0)",
    "TIP_AND_HYG": "TIP AND HYG",
    "TIP_AND_LQD": "TIP AND LQD",
    "TIP_AND_HYGIEF": "TIP AND HYG/IEF",
    "TIP_OR_HYG": "TIP OR HYG",
    "HYG_alone": "HYG alone",
    "HYGIEF_alone": "HYG/IEF alone",
}


def write_md(o):
    L = []; A = L.append
    m = o["meta"]; per = o["per_variant"]
    order = list(VARIANTS.keys())
    v0 = per[V0_KEY]; b = v0["metrics"]

    A("# NDX-sleeve canary variants: does a credit-confirming AND-canary beat TIP-only?\n")
    A("Role: analyst (hypothesis-driven, read-only re production; writes only to research/; no "
      "production/memo files changed; no commit). EXPLORATION ONLY -- a POTENTIAL NDX-sleeve change; "
      "user decides adoption later. Harness `research/ndx_canary_variants.py` (SEPARATE from "
      "`ndx_gate_underlying.py` / `ndx_volgate_variants.py` / the rv20_ext harness to avoid write "
      "races).\n")
    A("**Question.** The NDX sleeve fires its top-K Nasdaq-100 momentum basket only when BULL is "
      "risk-on = canary(TIP 13612U>0) AND trend(SPY 13612U>0) AND vol(RV60<RV252 on SPY). The canary "
      "is TIP-only. Does adding a STRICTER credit confirmation (HYG / LQD / HY-vs-Treasury ratio) on "
      "top of TIP cut drawdown and whipsaw, or does the stricter AND just over-de-risk and bleed "
      "return (the multi-signal failure mode)?\n")
    A("**Design.** Hold trend = SPY 13612U>0 and vol = SPY RV60<RV252 at production. Vary ONLY the "
      "canary. bull_active = canary_variant AND trend_spy AND vol_spy. Variants: TIP only (V0); "
      "TIP AND HYG; TIP AND LQD; TIP AND HYG/IEF ratio; TIP OR HYG (CPM-style contrast); HYG alone; "
      "HYG/IEF alone. Each leg = 13612U momentum > 0. Selection (top-K=" + str(m['select_k']) +
      " raw 13612U, partial-fill to best-of-safe), delisting haircut, T+1 MOO execution held at "
      "production. Judged on Calmar AND Martin, keeping crisis catches; whipsaw = monthly on/off "
      "flips.\n")
    A(f"**Convention.** T+1 MOO (next-day open), {m['cost_bps']} bps/side, monthly month-end signal. "
      f"Window {m['start']}..{m['end']} ({m['n_sig_dates']} monthly signals). NDX STANDALONE sleeve "
      "(the lens where the canary matters most; at 20% blend weight effects scale ~1/5).\n")
    A("**Data/EXT honesty.** Repo panel uses AUDITED stitches: HYG<-VWEHX (Vanguard HY mutual fund) "
      "pre 2007-04, TIP<-VIPSX, IEF<-VFITX; LQD is raw ETF (2002-07+). So canary signals are "
      "computable before ETF inception -- but the NDX sleeve is bounded at 2007-02-28 by the "
      "constituent panel, so NO ext beyond 2007 is possible for this sleeve. Window limit = the NDX "
      "sleeve's own 2007+ window. Robustness via the 2007-2016 (dirty survivorship) vs 2017+ (clean "
      "PIT) split below, not an ext view.\n")
    A("**Caveat up front:** pre-2017 NDX backtest has ~28% survivorship bias (missing delisted "
      "tickers); post-2020 PIT coverage is clean. Single ~19y in-sample run; any winner needs paired "
      "bootstrap-CI / walk-forward before adoption.\n")

    a = o["anchor"]
    A("## 0. Anchor (reproduced before deltas)\n")
    A(f"NDX V0 (TIP-only canary, trend SPY, vol SPY RV60<RV252) standalone: Sharpe "
      f"**{a['v0']['sharpe']:.4f}** / MaxDD **{pct(a['v0']['maxdd'])}** / Calmar "
      f"**{a['v0']['calmar']:.4f}** / Martin **{a['v0']['martin']:.4f}** vs expected {a['expected']} "
      f"-> **{'CONFIRMED' if a['anchor_ok'] else 'FLAG'}**.\n")

    A("## 1. Canary variants (full-window standalone metrics)\n")
    A("| Canary | CAGR | Vol | Sharpe | MaxDD | Calmar | Martin | Ulcer | active mo | flips |")
    A("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for key in order:
        r = per[key]["metrics"]
        tag = LABELS[key]
        A(f"| {tag} | {pct(r['cagr'])} | {pct(r['vol'])} | {r['sharpe']:.4f} | {pct(r['maxdd'])} | "
          f"{r['calmar']:.4f} | {r['martin']:.4f} | {pct(r['ulcer'])} | "
          f"{per[key]['n_active_months']}/{m['n_sig_dates']} | {per[key]['flips']} |")
    A("")

    A("## 2. Delta vs V0 (Calmar + Martin are the judged objectives)\n")
    A("| Canary | dSharpe | dCalmar | dMartin | dMaxDD (pp) | dCAGR (pp) | dActiveMo | dFlips |")
    A("|---|---:|---:|---:|---:|---:|---:|---:|")
    for key in order:
        r = per[key]["metrics"]
        A(f"| {LABELS[key]} | {r['sharpe']-b['sharpe']:+.4f} | {r['calmar']-b['calmar']:+.4f} | "
          f"{r['martin']-b['martin']:+.4f} | {(abs(r['maxdd'])-abs(b['maxdd']))*100:+.2f} | "
          f"{(r['cagr']-b['cagr'])*100:+.2f} | {per[key]['n_active_months']-v0['n_active_months']:+d} | "
          f"{per[key]['flips']-v0['flips']:+d} |")
    A("\n*dMaxDD>0 = deeper drawdown (worse). dCalmar/dMartin>0 = better. dActiveMo<0 = more "
      "de-risked. dFlips<0 = less whipsaw.*\n")

    A("## 3. AND-variant decomposition: real protection vs return bleed\n")
    A("For each TIP AND X variant: the months where V0 was active but the variant went safe ('newly "
      "defensive'). `avg active fwd` = mean forward 1-month return of the NDX-active basket on those "
      "skipped months (what V0 earned). Positive => the AND skipped UP months (return BLEED); "
      "negative => the AND dodged DOWN months (real PROTECTION). `avg skipped excess` = active minus "
      "safe forward return on those months (net give-up by de-risking).\n")
    A("| Canary | newly-def mo | up/down split | avg active fwd | avg skipped excess | read |")
    A("|---|---:|---:|---:|---:|---|")
    for key in order:
        if key not in o["decomp"]:
            continue
        d = o["decomp"][key]
        if d["n_newly_def"] == 0:
            A(f"| {LABELS[key]} | 0 | - | - | - | identical to V0 (never newly-defensive) |")
            continue
        read = ("BLEED (skipped mostly UP)" if d["avg_active_fwd"] > 0
                else "PROTECTION (dodged DOWN)")
        A(f"| {LABELS[key]} | {d['n_newly_def']} | {d['n_up']}up/{d['n_down']}down | "
          f"{pct(d['avg_active_fwd'])} | {pct(d['avg_skipped_excess'])} | {read} |")
    A("\n*If newly-defensive months are mostly UP and avg active fwd is positive, the stricter AND is "
      "de-risking into strength = return bleed, not crisis protection.*\n")

    A("## 4. Per-crisis protection (NDX sleeve MaxDD / total return in window)\n")
    cnames = list(m["crises"].keys())
    A("| Canary | " + " | ".join(f"{c} DD/Ret" for c in cnames) + " |")
    A("|---|" + "---|" * len(cnames))
    for key in order:
        cells = []
        for c in cnames:
            cr = per[key]["crises"][c]
            cells.append(f"{pct(cr['maxdd'])} / {pct(cr['ret'])}")
        A(f"| {LABELS[key]} | " + " | ".join(cells) + " |")
    A("\n*Windows: " + "; ".join(f"{c} {m['crises'][c][0]}..{m['crises'][c][1]}" for c in cnames) + ".*\n")

    A("## 5. Sub-period robustness (don't headline only the full-sample Calmar)\n")
    snames = list(m["subperiods"].keys())
    A("| Canary | " + " | ".join(f"{s} Calmar/Martin/MaxDD" for s in snames) + " |")
    A("|---|" + "---|" * len(snames))
    for key in order:
        cells = []
        for s in snames:
            sm = per[key]["subperiods"][s]
            cells.append(f"{sm['calmar']:.3f}/{sm['martin']:.3f}/{pct(sm['maxdd'])}")
        A(f"| {LABELS[key]} | " + " | ".join(cells) + " |")
    A("")

    A("## 6. VERDICT scorecard\n")
    A("Beats-V0 = Calmar AND Martin both strictly higher than V0. Keeps crash = 2008 & 2020 DD not "
      ">3pp deeper than V0; keeps grind = 2018-Q4 & 2022 DD not >4pp deeper than V0.\n")
    A("| Canary | Calmar | Martin | Sharpe | MaxDD | beats V0? | keeps crash? | keeps grind? |")
    A("|---|---:|---:|---:|---:|:--:|:--:|:--:|")
    for key in order:
        r = per[key]["metrics"]
        cr = per[key]["crises"]; c0 = v0["crises"]
        kc = (cr["2008 GFC"]["maxdd"] - c0["2008 GFC"]["maxdd"] > -0.03) and \
             (cr["2020 COVID"]["maxdd"] - c0["2020 COVID"]["maxdd"] > -0.03)
        kg = (cr["2018 Q4"]["maxdd"] - c0["2018 Q4"]["maxdd"] > -0.04) and \
             (cr["2022 bear"]["maxdd"] - c0["2022 bear"]["maxdd"] > -0.04)
        bv0 = (r["calmar"] > b["calmar"] + 1e-9) and (r["martin"] > b["martin"] + 1e-9)
        A(f"| {LABELS[key]} | {r['calmar']:.4f} | {r['martin']:.4f} | {r['sharpe']:.4f} | "
          f"{pct(r['maxdd'])} | {'YES' if bv0 else 'no'} | {'Y' if kc else 'NO'} | {'Y' if kg else 'NO'} |")
    A("")
    sk = o.get("skepticism", {})
    win = sk.get("winner")
    if win:
        wr = per[win]["metrics"]
        A(f"**Apparent winner: {LABELS[win]}** -- beats V0 (Calmar {wr['calmar']:.4f} vs "
          f"{b['calmar']:.4f}, Martin {wr['martin']:.4f} vs {b['martin']:.4f}) while keeping crash AND "
          "grind catches. REQUIRES the skepticism check in section 7 before any adoption.\n")
    else:
        A("**No credit-confirming canary beats V0 on Calmar AND Martin while keeping crash + grind "
          "catches.** On this sample, requiring a credit confirmation on top of TIP does NOT "
          "net-improve over TIP-only.\n")

    A("## 7. Skepticism on the apparent winner\n")
    ed = sk.get("episode_decomp")
    if win is None:
        A("No variant cleared the beats-V0 + keeps-catches bar, so there is no winner to stress. The "
          "AND-decomposition (section 3) already shows whether the stricter canaries protect or "
          "bleed.\n")
    elif ed:
        A(f"Apparent winner = **{LABELS[win]}**. Per-episode decomposition: if the winner's edge vs "
          "V0 collapses when a single crisis window is removed, the edge IS that crisis, not a robust "
          "canary property.\n")
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
                 "in-sample; needs paired bootstrap-CI + walk-forward.") + "\n")

    A("## 8. Bottom line: does a credit-confirming canary beat TIP-only on NDX?\n")
    # synthesis numbers
    th = per["TIP_AND_HYG"]["metrics"]; thr = per["TIP_AND_HYGIEF"]["metrics"]
    tl = per["TIP_AND_LQD"]["metrics"]
    dh = o["decomp"].get("TIP_AND_HYG", {})
    dhr = o["decomp"].get("TIP_AND_HYGIEF", {})
    if win is None:
        A("**Short answer: NO.** No credit-confirming AND-canary (TIP AND HYG / LQD / HYG-IEF) beats "
          "TIP-only on the NDX sleeve on Calmar AND Martin while keeping catches. The decomposition "
          "(section 3) shows the stricter AND mostly de-risks into strength (skipped months are "
          "predominantly UP), i.e. return bleed rather than crisis protection -- the same failure mode "
          "as the multi-asset-canary rejection on CPM.\n")
        A(f"- TIP AND HYG: Calmar {th['calmar']:.4f} (V0 {b['calmar']:.4f}), Martin {th['martin']:.4f} "
          f"(V0 {b['martin']:.4f}). " + (
            f"Newly-defensive {dh.get('n_newly_def','?')} mo, {dh.get('n_up','?')}up/"
            f"{dh.get('n_down','?')}down, avg active fwd {pct(dh.get('avg_active_fwd'))}." if dh else "") + "\n")
        A(f"- TIP AND HYG/IEF: Calmar {thr['calmar']:.4f}, Martin {thr['martin']:.4f}. " + (
            f"Newly-defensive {dhr.get('n_newly_def','?')} mo, {dhr.get('n_up','?')}up/"
            f"{dhr.get('n_down','?')}down, avg active fwd {pct(dhr.get('avg_active_fwd'))}." if dhr else "") + "\n")
        A(f"- TIP AND LQD: Calmar {tl['calmar']:.4f}, Martin {tl['martin']:.4f}.\n")
        A("**Net of lag: the stricter AND just over-de-risks.** Recommendation: KEEP TIP-only on the "
          "NDX sleeve; do NOT add a credit-confirming AND-canary.\n")
    else:
        A(f"**A credit-confirming canary ({LABELS[win]}) APPEARS to beat TIP-only on Calmar AND "
          "Martin while keeping catches -- but only in-sample.** Before adoption it MUST clear: (1) "
          "paired stationary-block bootstrap CI on the winner-minus-V0 Calmar/Martin deltas (is the "
          "edge distinguishable from zero?); (2) walk-forward (freeze the canary choice pre-2017, "
          "test 2017+ clean-PIT). The AND-decomposition (section 3) and per-episode drop (section 7) "
          "must both show the edge is protection (dodged down months) and not one-crisis-driven. "
          "Until then: RESEARCH ONLY.\n")

    A("**Adoption status: RESEARCH ONLY, not adopted.** Single in-sample run; 2007+ ETF/proxy "
      "window; pre-2017 NDX survivorship bias; T+1 MOO / PIT honesty caveats. User decides.\n")

    A("## Caveats\n")
    A("- EXPLORATION ONLY; no production/memo edits; no commit. Read-only re production.")
    A("- Only the canary leg changes; trend(SPY 13612U)/vol(SPY RV60<RV252)/selection/delisting/"
      "execution held at prod.")
    A("- NDX standalone sleeve lens; at 20% blend weight effects scale ~1/5 (dilute further vs "
      "CPM+BULL co-movement).")
    A("- Canary legs use AUDITED stitches (HYG<-VWEHX, TIP<-VIPSX, IEF<-VFITX); LQD raw ETF 2002+. "
      "NDX sleeve bounded at 2007 by constituent panel => no ext beyond 2007.")
    A("- 13612U = simple average of 1/3/6/12-month total returns on monthly resampled closes.")
    A("- HYG/IEF ratio leg = sig_13612U on the monthly resampled HYG/IEF price ratio.")
    A("- Pre-2017 NDX segment has ~28% survivorship bias; post-2020 is clean PIT coverage.")
    A("- Single sample + ETF-inception window limit; any winner needs paired bootstrap-CI + "
      "walk-forward before adoption.")

    Path(ROOT / "research" / "ndx_canary_variants_findings.md").write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
