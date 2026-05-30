# -*- coding: utf-8 -*-
"""Throwaway research (read-only re: production; no production files changed, no
commit): RE-VALIDATE whether the CPM ranker's VOL-ADJUSTMENT earns its keep under
the FINAL production spec (strict-3 partial-safe INVVOL-3), and check
TRIPLE-VOL-COUNTING (ranker /rv_252d + min-var SELECTION + inverse-vol WEIGHTING).

FINAL spec (held fixed; identical to cpm_live.compute_target_weights):
  rank by ranker -> positive-trend screen -> top-K=4 -> min-variance 3-subset
  -> inverse-vol weight -> strict-3 partial-safe (risky=min(n_pos,3)/3, remainder
  to timed safe) -> HYG-OR-TIP any-positive 13612U canary -> timed SHV/IEF safe.
  cov 504d, execution T+1 MOO exact (mooex), 10 bps/side, post-cost.
  Clean 2008-05-30..2026-05-22 (18y); ext 1999-03-10..2026-05-22 (27y).

Vary ONLY the ranker (everything else at final spec):
  faber_vol  (PRODUCTION): m_faber / rv_252d.
  faber      (plain):      m_faber alone (NO vol division).
  13612u_vol:              13612U / rv_252d (positive-13612U screen).
  plain12:                 plain 12-month total-return momentum.

This harness imports the FINAL-spec weight fn machinery from
cpm_final_memo_numbers and adds the plain-"faber" ranker branch (faber_vol stays
byte-identical so the anchor still reproduces).

Anchor gate: faber_vol must reproduce CPM-solo strict-3 clean 1.2667 / -12.66% /
1.1306 (ext 1.2349 / -15.18% / 0.9119) BEFORE any variant is trusted.

Writes research/ranker_revalidation_final_spec.json (+ findings md via separate step).
"""
from __future__ import annotations
import sys, json
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

import exec_lag_moo_validation_2026_05_30 as H
from cpm_live import (
    load_panel, perf_metrics, faber_sma_xs, sig_13612U, best_safe,
    inv_vol_weights, compute_target_weights, RISKY_UNIVERSE, SAFE_POOL,
    CANARY_ASSETS, DEFAULT_CASH, COST_BPS_PER_SIDE, CORR_LOOKBACK_DAYS,
    TOP_K_CANDIDATES,
)
import cpm_final_memo_numbers as M  # final-spec gcpm_wf, select_subset, weight_block, met, win, run_cpm

CONV = "mooex"
COST = COST_BPS_PER_SIDE  # 10
LOOKBACK = CORR_LOOKBACK_DAYS  # 504
K = TOP_K_CANDIDATES  # 4
CPM_UNIV = M.CPM_UNIV
SAFE = M.SAFE

CLEAN_START = pd.Timestamp("2008-05-30")
EXT_START = pd.Timestamp("1999-03-10")
END = pd.Timestamp("2026-05-22")

B, BLOCK, SEED = 2000, 21, 42

ANCHOR = {"clean": (1.2667, -12.66, 1.1306), "ext": (1.2349, -15.18, 0.9119)}

RANKERS = [
    ("faber_vol", "vol-Faber (PRODUCTION) m_faber/rv_252d"),
    ("faber", "plain Faber m_faber"),
    ("13612u_vol", "13612U/rv_252d"),
    ("plain12", "plain 12m total-return momentum"),
]


# ---------------------------------------------------------------------------
# Final-spec weight fn with the plain-"faber" branch added. faber_vol / 13612u_vol
# / plain12 are byte-identical to M.gcpm_wf; "faber" = m_faber with NO vol division.
# ---------------------------------------------------------------------------
def gcpm_wf_r(close, sd, ranker, *, top_k=K, screen=True, canary="hygortip",
              safe_kind="timed", lookback=LOOKBACK, flavor="invvol", selector="minvar"):
    if ranker != "faber":
        return M.gcpm_wf(close, sd, top_k=top_k, screen=screen, ranker=ranker,
                         canary=canary, safe_kind=safe_kind, lookback=lookback,
                         flavor=flavor, selector=selector)

    # ----- plain Faber branch (mirrors M.gcpm_wf exactly, minus /v) -----
    monthly = close.loc[:sd].resample("ME").last()
    if safe_kind in ("SHV", "IEF", "BLEND5050"):
        safe = safe_kind
    else:
        safe = best_safe(monthly, sd, SAFE)

    if canary != "none":
        ca = {"hyg": ["HYG"], "tip": ["TIP"], "hygortip": ["HYG", "TIP"]}[canary]
        cs = [sig_13612U(monthly[a]) for a in ca if a in monthly.columns]
        cs = [s for s in cs if pd.notna(s)]
        if not cs or sum(1 for s in cs if s > 0) == 0:
            return {safe: 1.0}

    present = [t for t in CPM_UNIV if t in monthly.columns]
    faber = faber_sma_xs(monthly)
    avail = [t for t in present if t in faber.index and pd.notna(faber[t])
             and (sd in close.index and pd.notna(close.loc[sd].get(t, np.nan)))]
    if not avail:
        return {safe: 1.0}

    scores, screenval = {}, {}
    for t in avail:
        scores[t] = float(faber[t])
        screenval[t] = float(faber[t])
    if not scores:
        return {safe: 1.0}
    ranked = pd.Series(scores).sort_values(ascending=False)
    if top_k is not None:
        kk = max(2, min(top_k, len(ranked)))
        top = ranked.iloc[:kk]
    else:
        top = ranked
    if screen:
        positive = [t for t in top.index if screenval.get(t, -np.inf) > 0]
    else:
        positive = list(top.index)

    n = len(positive)
    if n == 0:
        return {safe: 1.0}
    csub = close.loc[:sd]
    risky_fraction = min(n, 3) / 3.0
    if n > 3:
        picks = M.select_subset(csub, positive, lookback, 3, selector)
        if picks is None:
            picks = positive
    else:
        picks = positive
    risky_w = M.weight_block(csub, picks, lookback, flavor)
    out = {t: w * risky_fraction for t, w in risky_w.items()}
    if risky_fraction < 1.0:
        out[safe] = out.get(safe, 0.0) + (1.0 - risky_fraction)
    return out


# ----- basket / selection diagnostics ------------------------------------
def risky_basket(close, sd, ranker):
    w = gcpm_wf_r(close, sd, ranker)
    return frozenset(t for t in w if t in CPM_UNIV)


def topk_set(close, sd, ranker):
    """Top-K positive-trend pool (pre min-var), and risk-on flag."""
    monthly = close.loc[:sd].resample("ME").last()
    ca = ["HYG", "TIP"]
    cs = [sig_13612U(monthly[a]) for a in ca if a in monthly.columns]
    cs = [s for s in cs if pd.notna(s)]
    risk_on = bool(cs) and sum(1 for s in cs if s > 0) > 0
    if not risk_on:
        return frozenset(), False
    present = [t for t in CPM_UNIV if t in monthly.columns]
    faber = faber_sma_xs(monthly)
    avail = [t for t in present if t in faber.index and pd.notna(faber[t])
             and (sd in close.index and pd.notna(close.loc[sd].get(t, np.nan)))]
    if not avail:
        return frozenset(), risk_on
    if ranker == "plain12":
        sc = {}
        for t in avail:
            s = monthly[t].dropna()
            if len(s) >= 13:
                sc[t] = float(s.iloc[-1] / s.iloc[-13] - 1.0)
        sv = sc
    elif ranker == "faber":
        sc = {t: float(faber[t]) for t in avail}
        sv = sc
    else:
        dr = close[avail].ffill().pct_change()
        sc, sv = {}, {}
        for t in avail:
            v = dr[t].loc[:sd].tail(252).std() * np.sqrt(252)
            if pd.isna(v) or v < 1e-9:
                v = 1.0
            if ranker == "faber_vol":
                num = float(faber[t]); s2 = float(faber[t])
            else:  # 13612u_vol
                nn = sig_13612U(monthly[t])
                if pd.isna(nn):
                    continue
                num = float(nn); s2 = num
            sc[t] = num / v; sv[t] = s2
    if not sc:
        return frozenset(), risk_on
    ranked = pd.Series(sc).sort_values(ascending=False)
    kk = max(2, min(K, len(ranked)))
    top = ranked.iloc[:kk]
    positive = frozenset(t for t in top.index if sv.get(t, -np.inf) > 0)
    return positive, risk_on


def sig_dates(close, start, end):
    midx = (pd.DataFrame({"x": 1}, index=close.index)
            .groupby(pd.Grouper(freq="ME")).tail(1))
    return midx.index[(midx.index >= start) & (midx.index <= end)].tolist()


# ----- bootstrap ----------------------------------------------------------
def metrics_from_array(r, n_years):
    vol = r.std(ddof=0) * np.sqrt(252)
    sharpe = (r.mean() * 252) / vol if vol > 0 else np.nan
    eq = np.cumprod(1.0 + r)
    total = eq[-1]
    cagr = total ** (1.0 / n_years) - 1.0 if n_years > 0 else np.nan
    rm = np.maximum.accumulate(eq)
    mdd = (eq / rm - 1.0).min()
    calmar = cagr / abs(mdd) if mdd != 0 else np.nan
    return sharpe, mdd, calmar


def block_index(n, block, rng):
    n_blocks = (n // block) + 1
    parts = []
    for _ in range(n_blocks):
        s = int(rng.integers(0, n))
        e = s + block
        if e <= n:
            parts.append(np.arange(s, e))
        else:
            parts.append(np.concatenate([np.arange(s, n), np.arange(0, e - n)]))
    return np.concatenate(parts)[:n]


def paired_boot(base_r, alt_r, n_years):
    """diff = base - alt for each metric. base = vol-Faber (production).
    Sharpe/Calmar: diff>0 => base better. MaxDD (both <0): diff>0 => base shallower."""
    n = len(base_r)
    rng = np.random.default_rng(SEED)
    ds, dm, dc = [], [], []
    for _ in range(B):
        idx = block_index(n, BLOCK, rng)
        bs, bm, bc = metrics_from_array(base_r[idx], n_years)
        as_, am, ac = metrics_from_array(alt_r[idx], n_years)
        ds.append(bs - as_)
        dm.append(bm - am)
        dc.append(bc - ac)

    def summ(arr):
        a = np.asarray(arr)
        lo, hi = float(np.percentile(a, 2.5)), float(np.percentile(a, 97.5))
        return {"p_base_beats": float(np.mean(a > 0)), "mean": float(a.mean()),
                "ci_lo": lo, "ci_hi": hi, "excludes_zero": bool(lo > 0 or hi < 0)}

    return {"sharpe": summ(ds), "maxdd": summ(dm), "calmar": summ(dc)}


def main():
    panel = load_panel(start=EXT_START, end=END)
    end = min(END, panel.index[-1])
    cash = panel["SHV"].ffill().pct_change().dropna()
    od, cy = H.load_open_close()
    intraday = (cy / od - 1.0).reindex(panel.index)
    overnight = (od / cy.shift(1) - 1.0).reindex(panel.index)

    cols = sorted(set(RISKY_UNIVERSE + SAFE_POOL + CANARY_ASSETS + [DEFAULT_CASH]) & set(panel.columns))
    close = panel[cols]
    daily = close.ffill().pct_change()

    out = {"meta": {"conv": CONV, "cost_bps": COST, "lookback": LOOKBACK, "K": K,
                    "spec": "FINAL strict-3 partial-safe INVVOL-3 (cpm_live.compute_target_weights)",
                    "clean_start": str(CLEAN_START.date()), "ext_start": str(EXT_START.date()),
                    "end": str(end.date()), "B": B, "block": BLOCK, "seed": SEED}}

    # ----- ANCHOR GATE: production via compute_target_weights -----
    cpm_prod = M.run_cpm(close, daily, intraday, overnight,
                         lambda sd: compute_target_weights(close, sd)[0], end=end)
    print("=== ANCHOR GATE (production compute_target_weights) ===")
    anc = {}
    for wl, st in [("clean", CLEAN_START), ("ext", EXT_START)]:
        m = M.met(M.win(cpm_prod, st, end), cash)
        exp = ANCHOR[wl]
        ok = (abs(m["sharpe"] - exp[0]) < 5e-4 and abs(m["maxdd"] * 100 - exp[1]) < 0.02
              and abs(m["calmar"] - exp[2]) < 5e-4)
        anc[wl] = {"m": m, "ok": ok}
        print(f"  {wl}: Sharpe={m['sharpe']:.4f} MaxDD={m['maxdd']*100:.2f}% Calmar={m['calmar']:.4f} "
              f"expect {exp} -> {'OK' if ok else 'MISMATCH'}")
    if not all(anc[wl]["ok"] for wl in anc):
        print("ANCHOR MISMATCH -- aborting.")
        sys.exit(1)

    # ----- gcpm_wf_r faber_vol self-check must equal production -----
    gcpm_fv = M.run_cpm(close, daily, intraday, overnight,
                        lambda sd: gcpm_wf_r(close, sd, "faber_vol"), end=end)
    common = cpm_prod.index.intersection(gcpm_fv.index)
    sc = M.met(M.win(gcpm_fv.reindex(common), CLEAN_START, end), cash)
    selfmatch = abs(sc["sharpe"] - anc["clean"]["m"]["sharpe"]) < 1e-9
    print(f"gcpm_wf_r faber_vol self-check clean Sharpe={sc['sharpe']:.6f} matches_prod={selfmatch}")
    out["anchor"] = {wl: {"sharpe": anc[wl]["m"]["sharpe"], "maxdd": anc[wl]["m"]["maxdd"],
                          "calmar": anc[wl]["m"]["calmar"], "ok": anc[wl]["ok"]} for wl in anc}
    out["selfcheck_faber_vol_matches_prod"] = bool(selfmatch)

    # ----- ITEM 1: headline per ranker under final spec -----
    series = {}
    headline = {}
    for rk, lab in RANKERS:
        s = M.run_cpm(close, daily, intraday, overnight,
                      lambda sd, rk=rk: gcpm_wf_r(close, sd, rk), end=end).reindex(common)
        series[rk] = s
        headline[rk] = {"label": lab,
                        "clean": M.met(M.win(s, CLEAN_START, end), cash),
                        "ext": M.met(M.win(s, EXT_START, end), cash)}
        c = headline[rk]["clean"]; e = headline[rk]["ext"]
        print(f"[{rk:11s}] clean Sh={c['sharpe']:.4f} DD={c['maxdd']*100:.2f}% Ca={c['calmar']:.4f} "
              f"| ext Sh={e['sharpe']:.4f} DD={e['maxdd']*100:.2f}% Ca={e['calmar']:.4f}")
    out["headline"] = headline

    # ----- ITEM 2: paired bootstrap vol-Faber vs {plain-Faber, 13612U} -----
    boot = {}
    for alt in ("faber", "13612u_vol"):
        boot[alt] = {}
        for wl, st in [("clean", CLEAN_START), ("ext", EXT_START)]:
            bs = M.win(series["faber_vol"], st, end)
            as_ = M.win(series[alt], st, end)
            cmn = bs.index.intersection(as_.index)
            bs = bs.reindex(cmn).values; as_ = as_.reindex(cmn).values
            n_years = (cmn[-1] - cmn[0]).days / 365.25
            boot[alt][wl] = paired_boot(bs, as_, n_years)
            sh = boot[alt][wl]["sharpe"]
            print(f"BOOT volFaber vs {alt} [{wl}] Sharpe diff mean={sh['mean']:+.4f} "
                  f"CI[{sh['ci_lo']:+.4f},{sh['ci_hi']:+.4f}] P(volFaber beats)={sh['p_base_beats']:.3f} "
                  f"excl0={sh['excludes_zero']}")
    out["bootstrap"] = boot

    # ----- ITEM 3: triple-vol-counting -- vol-Faber minus plain-Faber under final
    #               spec vs how it was under equal-weight/pair (re-cite prior study)
    tvc = {}
    for wl in ("clean", "ext"):
        vf = headline["faber_vol"][wl]; pf = headline["faber"][wl]
        tvc[wl] = {"d_sharpe": vf["sharpe"] - pf["sharpe"],
                   "d_maxdd_pp": (vf["maxdd"] - pf["maxdd"]) * 100,
                   "d_calmar": vf["calmar"] - pf["calmar"]}
    out["triple_vol_counting"] = tvc

    # ----- ITEM 4: selection overlap vol-Faber vs plain-Faber -----
    overlap = {}
    for wl, st in [("clean", CLEAN_START), ("ext", EXT_START)]:
        sigs = sig_dates(close, st, end)
        n_sig = len(sigs)
        same_basket = same_topk = both_riskon = 0
        state_disagree = 0
        jac = []
        for sd in sigs:
            tv, on_v = topk_set(close, sd, "faber_vol")
            tp, on_p = topk_set(close, sd, "faber")
            if on_v != on_p:
                state_disagree += 1
            bv = risky_basket(close, sd, "faber_vol")
            bp = risky_basket(close, sd, "faber")
            if bv and bp:
                both_riskon += 1
                if bv == bp:
                    same_basket += 1
                jac.append(len(bv & bp) / len(bv | bp))
            if on_v and on_p:
                if tv == tp:
                    same_topk += 1
        overlap[wl] = {
            "n_sigs": n_sig, "both_riskon": both_riskon,
            "frac_same_basket": same_basket / both_riskon if both_riskon else float("nan"),
            "mean_jaccard": float(np.mean(jac)) if jac else float("nan"),
            "frac_same_topk_when_both_on": same_topk / both_riskon if both_riskon else float("nan"),
            "riskon_state_disagree": state_disagree,
        }
        print(f"OVERLAP [{wl}] same_basket={overlap[wl]['frac_same_basket']:.3f} "
              f"jac={overlap[wl]['mean_jaccard']:.3f} state_disagree={state_disagree}/{n_sig}")
    out["overlap"] = overlap

    (HERE / "ranker_revalidation_final_spec.json").write_text(json.dumps(out, indent=2, default=float))
    print("\nDONE -> ranker_revalidation_final_spec.json")
    return out


if __name__ == "__main__":
    main()
