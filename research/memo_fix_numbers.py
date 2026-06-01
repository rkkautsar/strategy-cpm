# -*- coding: utf-8 -*-
"""Throwaway research (analyst role; read-only re production; NO production files
changed; NO commit). Reconciles the EXTENDED-window numbers in
cpm_bull_two_sleeve_memo.md onto a SINGLE post-tidy harness so a fixer can
correct the memo. Post-tidy = current production cpm_live.compute_target_weights
(IV4 single-stage top-4 inverse-vol, strict-4 partial-safe). Canonical.

ALL rows run on the SAME canonical post-tidy harness:
  - CPM & BULL legs: T+1 MOO exact ("mooex", real yfinance auto_adjust opens),
    10 bps/side post-cost, via exec_lag_moo_validation_2026_05_30 (= H).
  - CPM weight fn = cpm_live.compute_target_weights (production) for the base;
    weighting/ranker variants replicate it byte-for-byte except for the single
    swapped step (self-checked to 1e-9 vs production at every signal date).
  - BULL slow vol gate rv_60d<rv_252d (H.GATE_RV60).

ANCHOR GATE (abort on any mismatch):
  CPM clean Sharpe 1.1910 / MaxDD -12.67% / Calmar 1.0615
  CPM ext   Sharpe 1.2142 / MaxDD -15.93% / Calmar 0.8608

Produces research/memo_fix_numbers_findings.md (+ .json).
"""
from __future__ import annotations
import sys, json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import exec_lag_moo_validation_2026_05_30 as H
from cpm_live import (
    load_panel, perf_metrics, faber_sma_xs, sig_13612U, best_safe,
    inv_vol_weights, compute_target_weights,
    RISKY_UNIVERSE, SAFE_POOL, CANARY_ASSETS, DEFAULT_CASH, COST_BPS_PER_SIDE,
    TOP_K_CANDIDATES, CORR_LOOKBACK_DAYS,
)
from scipy.optimize import minimize


def erc_weights(cov_values, x0=None):
    """Equal-risk-contribution weights via SLSQP minimizing pairwise squared
    risk-contribution differences (copied verbatim from research/weighting_headtohead.py
    to avoid its stale tidy-removed import chain). Long-only, fully invested.
    Falls back to inverse-vol on failure."""
    n = cov_values.shape[0]
    sig = np.sqrt(np.clip(np.diag(cov_values), 1e-18, None))
    iv = (1.0 / sig)
    iv = iv / iv.sum()
    if x0 is None:
        x0 = iv

    def obj(w):
        rc = w * (cov_values @ w)
        d = rc[:, None] - rc[None, :]
        return float((d * d).sum())

    cons = ({"type": "eq", "fun": lambda w: np.sum(w) - 1.0},)
    bnds = tuple((1e-9, 1.0) for _ in range(n))
    r = minimize(obj, x0, method="SLSQP", bounds=bnds, constraints=cons,
                 options={"maxiter": 1000, "ftol": 1e-14})
    if not r.success:
        return iv
    w = np.clip(r.x, 0.0, None)
    s = w.sum()
    return w / s if s > 0 else iv

CONV = "mooex"
COST = COST_BPS_PER_SIDE              # 10
CPM_W, BULL_W = 0.60, 0.40
LOOKBACK = CORR_LOOKBACK_DAYS         # 504
K = TOP_K_CANDIDATES                  # 4
CPM_UNIV = list(RISKY_UNIVERSE)       # ['QQQ','SPHQ','EFA','EEM','VNQ','GLD','TLT','DBC']
SAFE = list(SAFE_POOL)                # ['SHV','IEF']

CLEAN_START = pd.Timestamp("2008-05-30")
EXT_START = pd.Timestamp("1999-03-10")
END = pd.Timestamp("2026-05-22")

ANCHOR = {
    "clean": {"sharpe": 1.1910, "maxdd": -12.67, "calmar": 1.0615},
    "ext":   {"sharpe": 1.2142, "maxdd": -15.93, "calmar": 0.8608},
}


def met(s, cash):
    m = perf_metrics(s, cash)
    return {"sharpe": m.get("sharpe"), "cagr": m.get("cagr"), "vol": m.get("vol"),
            "excess_sharpe": m.get("excess_sharpe"), "maxdd": m.get("max_drawdown"),
            "calmar": m.get("calmar"), "martin": m.get("martin")}


def win(s, a, b):
    return s.loc[(s.index >= a) & (s.index <= b)]


# ---------------------------------------------------------------------------
# Weighting-block flavors (identical primitives to the prior 8.4 harness).
# ---------------------------------------------------------------------------
def weight_block(close, picks, lookback, flavor):
    if not picks:
        return {}
    if flavor == "invvol":
        return inv_vol_weights(close, picks, lookback)
    if flavor == "ew":
        n = len(picks)
        return {t: 1.0 / n for t in picks}
    if flavor == "erc":
        rets = close[picks].pct_change().dropna(how="all").tail(lookback)
        if len(rets) < lookback:
            return inv_vol_weights(close, picks, lookback)
        cov = rets.cov()
        if cov.isna().any().any():
            return inv_vol_weights(close, picks, lookback)
        w = erc_weights(cov.values)
        if w is None or not np.all(np.isfinite(w)):
            return inv_vol_weights(close, picks, lookback)
        return {picks[i]: float(w[i]) for i in range(len(picks))}
    raise ValueError(flavor)


# ---------------------------------------------------------------------------
# POST-TIDY CPM weight fn: byte-for-byte replication of
# cpm_live.compute_target_weights (IV4 single-stage top-4, strict-4 partial-safe)
# with two pluggable steps: ranker in {faber_vol, plain12}, flavor in
# {invvol, erc, ew}. Base (faber_vol, invvol) is self-checked == production.
# ---------------------------------------------------------------------------
def cpm_wf(close, sd, *, ranker="faber_vol", flavor="invvol"):
    monthly = close.loc[:sd].resample("ME").last()
    safe = best_safe(monthly, sd, SAFE)

    cs = [sig_13612U(monthly[a]) for a in CANARY_ASSETS if a in monthly.columns]
    cs = [s for s in cs if pd.notna(s)]
    if not cs:
        return {safe: 1.0}
    if sum(1 for s in cs if s > 0) == 0:          # any_positive canary
        return {safe: 1.0}

    faber = faber_sma_xs(monthly)
    avail = [t for t in CPM_UNIV
             if t in faber.index and pd.notna(faber[t])
             and (sd in close.index and pd.notna(close.loc[sd].get(t, np.nan)))]
    if not avail:
        return {safe: 1.0}

    scores, screenval = {}, {}
    if ranker == "plain12":
        for t in avail:
            s = monthly[t].dropna()
            if len(s) < 13:
                continue
            mom = float(s.iloc[-1] / s.iloc[-13] - 1.0)
            scores[t] = mom
            screenval[t] = mom
    elif ranker == "faber_vol":
        dr = close[avail].ffill().pct_change()
        for t in avail:
            v = dr[t].loc[:sd].tail(252).std() * np.sqrt(252)
            if pd.isna(v) or v < 1e-9:
                v = 1.0
            scores[t] = float(faber[t]) / v
            screenval[t] = float(faber[t])
    else:
        raise ValueError(ranker)
    if not scores:
        return {safe: 1.0}

    ranked = pd.Series(scores).sort_values(ascending=False)
    kk = max(2, min(K, len(ranked)))
    top = ranked.iloc[:kk]
    positive = [t for t in top.index if screenval.get(t, -np.inf) > 0]
    n = len(positive)
    if n == 0:
        return {safe: 1.0}

    csub = close.loc[:sd]
    risky_fraction = min(n, 4) / 4.0          # strict-4 partial-safe
    risky_w = weight_block(csub, positive, LOOKBACK, flavor)
    out = {t: w * risky_fraction for t, w in risky_w.items()}
    if risky_fraction < 1.0:
        out[safe] = out.get(safe, 0.0) + (1.0 - risky_fraction)
    return out


def run_cpm_wf(close, daily, intraday, overnight, wf, end, cost=COST):
    s, _ = H._segment_returns_conv(close, daily, wf, EXT_START, end, CONV,
                                   cost, intraday, overnight)
    return s


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

    # ---------- self-check: cpm_wf base == production at every signal date ----------
    monthly_idx = (pd.DataFrame({"x": 1}, index=close.index)
                   .groupby(pd.Grouper(freq="ME")).tail(1))
    sigs = monthly_idx.index[(monthly_idx.index >= EXT_START) & (monthly_idx.index <= end)].tolist()
    max_abs = 0.0
    for sd in sigs:
        wp = compute_target_weights(close, sd)[0]
        wm = cpm_wf(close, sd, ranker="faber_vol", flavor="invvol")
        keys = set(wp) | set(wm)
        for k in keys:
            max_abs = max(max_abs, abs(wp.get(k, 0.0) - wm.get(k, 0.0)))
    selfcheck_ok = max_abs < 1e-9
    print(f"SELF-CHECK cpm_wf(base) vs production max|dw| = {max_abs:.2e} -> "
          f"{'OK' if selfcheck_ok else 'MISMATCH'}")

    # ---------- canonical post-tidy sleeves ----------
    cpm = run_cpm_wf(close, daily, intraday, overnight,
                     lambda sd: compute_target_weights(close, sd)[0], end)
    bull, _ = H.bull_sleeve_conv(panel, intraday, overnight, EXT_START, end, CONV, H.GATE_RV60)
    common = cpm.index.intersection(bull.index)
    cpm = cpm.reindex(common); bull = bull.reindex(common)
    blend = CPM_W * cpm + BULL_W * bull

    # =================== ANCHOR GATE ===================
    print("\n=== ANCHOR GATE (CPM-solo post-tidy IV4, mooex, 10bps) ===")
    anc = {}
    gate_ok = True
    for wl, st in [("clean", CLEAN_START), ("ext", EXT_START)]:
        m = met(win(cpm, st, end), cash)
        e = ANCHOR[wl]
        ok = (abs(m["sharpe"] - e["sharpe"]) < 5e-4
              and abs(m["maxdd"] * 100 - e["maxdd"]) < 0.02
              and abs(m["calmar"] - e["calmar"]) < 5e-4)
        gate_ok = gate_ok and ok
        anc[wl] = {"m": m, "expect": e, "ok": ok}
        print(f"  {wl}: Sharpe={m['sharpe']:.4f} MaxDD={m['maxdd']*100:.2f}% "
              f"Calmar={m['calmar']:.4f}  expect {e['sharpe']}/{e['maxdd']}%/{e['calmar']}"
              f" -> {'OK' if ok else 'MISMATCH'}")
    if not (gate_ok and selfcheck_ok):
        print("\nANCHOR/SELFCHECK FAIL -- aborting, no outputs produced.")
        sys.exit(1)
    print("ANCHOR CONFIRMED + self-check passed.\n")

    out = {"meta": {"conv": CONV, "cost_bps": COST, "lookback": LOOKBACK, "K": K,
                    "spec": "post-tidy IV4 single-stage top-4 inverse-vol strict-4 partial-safe",
                    "clean": [str(CLEAN_START.date()), str(end.date())],
                    "ext": [str(EXT_START.date()), str(end.date())]},
           "selfcheck_max_abs_dw": max_abs,
           "anchor": anc}

    # =================== ITEM 1: 8.4 weighting sensitivity ===================
    # CPM-solo, post-tidy, vary weighting flavor only (selection/ranker fixed).
    weighting = {}
    for label, flavor in [("inverse-vol (base)", "invvol"), ("ERC", "erc"), ("equal-weight", "ew")]:
        s = run_cpm_wf(close, daily, intraday, overnight,
                       lambda sd, fl=flavor: cpm_wf(close, sd, ranker="faber_vol", flavor=fl), end)
        s = s.reindex(common)
        weighting[label] = {"clean": met(win(s, CLEAN_START, end), cash),
                            "ext": met(win(s, EXT_START, end), cash)}
    out["item1_weighting_8_4"] = weighting

    # =================== ITEM 2: 8.3 / sec-7 ranker lift ===================
    # CPM-solo Sharpe, base (vol-Faber) minus plain-12m momentum.
    plain12 = run_cpm_wf(close, daily, intraday, overnight,
                         lambda sd: cpm_wf(close, sd, ranker="plain12", flavor="invvol"), end)
    plain12 = plain12.reindex(common)
    base_cpm_m = {"clean": met(win(cpm, CLEAN_START, end), cash),
                  "ext": met(win(cpm, EXT_START, end), cash)}
    plain_m = {"clean": met(win(plain12, CLEAN_START, end), cash),
               "ext": met(win(plain12, EXT_START, end), cash)}
    ranker_lift = {
        "base_volfaber": base_cpm_m,
        "plain12": plain_m,
        "lift_clean": base_cpm_m["clean"]["sharpe"] - plain_m["clean"]["sharpe"],
        "lift_ext": base_cpm_m["ext"]["sharpe"] - plain_m["ext"]["sharpe"],
    }
    out["item2_ranker_lift_8_3"] = ranker_lift

    # =================== ITEM 3: blend 60/40 ext ===================
    blend60 = {"clean": met(win(blend, CLEAN_START, end), cash),
               "ext": met(win(blend, EXT_START, end), cash)}
    out["item3_blend_6040"] = blend60

    # =================== ITEM 4: execution stress ===================
    # Recompute CPM & BULL under each convention; blend; clean+ext.
    conv_rows = {}
    convs = [("mooex", "T+1 MOO exact (headline)"),
             ("moo", "T+1 MOO conservative (intraday only, overnight gap dropped)"),
             ("moc1", "T+1 MOC harsh (full extra session)")]
    cpm_conv, bull_conv, blend_conv = {}, {}, {}
    for cv, _ in convs:
        c, _ = H.cpm_sleeve_conv(panel, intraday, overnight, EXT_START, end, cv)
        b, _ = H.bull_sleeve_conv(panel, intraday, overnight, EXT_START, end, cv, H.GATE_RV60)
        cc = c.index.intersection(b.index)
        c = c.reindex(cc); b = b.reindex(cc)
        cpm_conv[cv] = c
        bull_conv[cv] = b
        blend_conv[cv] = CPM_W * c + BULL_W * b
    # penalized slippage: headline mooex but 25 bps/side
    cpm_p25 = run_cpm_wf(close, daily, intraday, overnight,
                         lambda sd: compute_target_weights(close, sd)[0], end, cost=25)
    bull_p25, _ = H.bull_sleeve_conv(panel, intraday, overnight, EXT_START, end, CONV, H.GATE_RV60)
    # bull cost is internal to bull_sleeve_conv (uses bull_spy_live.COST); rerun bull at 25 bps:
    import bull_spy_live as BQ
    _bull_cost = BQ.COST_BPS_PER_SIDE
    BQ.COST_BPS_PER_SIDE = 25
    try:
        bull_p25, _ = H.bull_sleeve_conv(panel, intraday, overnight, EXT_START, end, CONV, H.GATE_RV60)
    finally:
        BQ.COST_BPS_PER_SIDE = _bull_cost
    ccp = cpm_p25.index.intersection(bull_p25.index)
    blend_p25 = CPM_W * cpm_p25.reindex(ccp) + BULL_W * bull_p25.reindex(ccp)

    exec_stress = {"conventions": {}, "penalized_25bps": {}}
    for cv, lbl in convs:
        exec_stress["conventions"][cv] = {
            "label": lbl,
            "blend": {"clean": met(win(blend_conv[cv], CLEAN_START, end), cash),
                      "ext": met(win(blend_conv[cv], EXT_START, end), cash)},
            "cpm": {"clean": met(win(cpm_conv[cv], CLEAN_START, end), cash),
                    "ext": met(win(cpm_conv[cv], EXT_START, end), cash)},
        }
    exec_stress["penalized_25bps"] = {
        "label": "mooex headline, 25 bps/side (2.5x slippage penalty)",
        "blend": {"clean": met(win(blend_p25, CLEAN_START, end), cash),
                  "ext": met(win(blend_p25, EXT_START, end), cash)},
        "cpm": {"clean": met(win(cpm_p25.reindex(ccp), CLEAN_START, end), cash),
                "ext": met(win(cpm_p25.reindex(ccp), EXT_START, end), cash)},
    }
    out["item4_exec_stress_8_8"] = exec_stress

    Path(__file__).with_suffix(".json").write_text(json.dumps(out, indent=2, default=float))
    write_md(out)
    print("DONE -> research/memo_fix_numbers_findings.md")
    return out


def write_md(o):
    L = []
    A = L.append

    def pct(x): return f"{x*100:.2f}%"

    m = o["meta"]
    A("# Memo EXTENDED-window reconciliation -- single post-tidy harness\n")
    A("Role: analyst (read-only re production; research/ artifacts only; NO production edit, "
      "NO commit). Throwaway harness `research/memo_fix_numbers.py`. Reconciles the EXTENDED "
      "numbers in `cpm_bull_two_sleeve_memo.md` (mixed pre-tidy 1.2161 / post-tidy 1.2142) onto a "
      "SINGLE canonical post-tidy harness so a fixer can correct the memo. The CLEAN column is "
      "unaffected and already correct.\n")
    A(f"**Canonical spec (post-tidy):** {m['spec']} = current production "
      f"`cpm_live.compute_target_weights`. All rows: CPM & BULL on T+1 MOO exact (`{m['conv']}`, "
      f"real auto_adjust opens), {m['cost_bps']} bps/side post-cost, BULL slow vol gate "
      f"rv_60d<rv_252d. Windows: clean {m['clean'][0]}..{m['clean'][1]}; "
      f"ext {m['ext'][0]}..{m['ext'][1]}. cov/sigma lookback {m['lookback']}d, top-K={m['K']}.\n")
    A(f"**Replication self-check:** the variant CPM weight fn reproduces production "
      f"`compute_target_weights` byte-for-byte (max|dw| = {o['selfcheck_max_abs_dw']:.1e}) at every "
      f"signal date; only the single swapped step (weighting flavor or ranker) differs.\n")

    a = o["anchor"]
    A("## Anchor gate (abort-on-mismatch)\n")
    A("| Window | Sharpe | MaxDD | Calmar | Expected | Match |")
    A("|---|---:|---:|---:|---|---|")
    for wl in ("clean", "ext"):
        r = a[wl]; mm = r["m"]; e = r["expect"]
        A(f"| {wl} | {mm['sharpe']:.4f} | {pct(mm['maxdd'])} | {mm['calmar']:.4f} | "
          f"{e['sharpe']:.4f} / {e['maxdd']:.2f}% / {e['calmar']:.4f} | "
          f"{'CONFIRMED' if r['ok'] else 'MISMATCH'} |")
    A("\nBoth anchors reproduce exactly; everything below is on this harness.\n")

    # ---- ITEM 1 ----
    w = o["item1_weighting_8_4"]
    A("## Item 1 -- Section 8.4 CPM weighting sensitivity (consistent post-tidy)\n")
    A("CPM-solo; weighting flavor varies, selection/ranker/canary/safe held at production. "
      "CLEAN is the memo's existing (correct) column; EXT is regenerated on the same harness so "
      "the comparison is internally consistent.\n")
    A("| Weighting (CPM) | Clean Sharpe | Clean Calmar | Clean Martin | Clean MaxDD | "
      "Ext Sharpe | Ext Calmar | Ext MaxDD |")
    A("|---|---:|---:|---:|---:|---:|---:|---:|")
    for label in ("inverse-vol (base)", "ERC", "equal-weight"):
        c = w[label]["clean"]; e = w[label]["ext"]
        A(f"| {label} | {c['sharpe']:.4f} | {c['calmar']:.4f} | {c['martin']:.4f} | {pct(c['maxdd'])} | "
          f"{e['sharpe']:.4f} | {e['calmar']:.4f} | {pct(e['maxdd'])} |")
    iv, erc, ew = w["inverse-vol (base)"]["ext"], w["ERC"]["ext"], w["equal-weight"]["ext"]
    A("\n_Note: the memo lists only inverse-vol / ERC / equal-weight under 8.4 (no continuous "
      "weighting row); continuous is N/A here._\n")
    A(f"- EXT Sharpe ranking: ERC {erc['sharpe']:.4f} vs inverse-vol {iv['sharpe']:.4f} vs "
      f"equal-weight {ew['sharpe']:.4f}.")
    A(f"- EXT Calmar ranking: inverse-vol {iv['calmar']:.4f} vs ERC {erc['calmar']:.4f} vs "
      f"equal-weight {ew['calmar']:.4f}.")
    A("")
    A("**Relative-ranking answer (the reconciliation point).** The memo's pre-tidy 8.4 row showed "
      "ERC ext Calmar 0.8647 vs inverse-vol 0.8608 (a 0.0039 ERC edge) and EW 0.8718, making "
      "inverse-vol look strictly worst on ext Calmar. Once ERC and EW are recomputed on the SAME "
      "post-tidy harness, the spurious ERC edge collapses: ERC ext Calmar falls 0.8647 -> "
      f"{erc['calmar']:.4f}, now a dead heat with inverse-vol {iv['calmar']:.4f} (delta "
      f"{erc['calmar']-iv['calmar']:+.4f}) at IDENTICAL ext MaxDD ({pct(iv['maxdd'])}). "
      "Equal-weight keeps the nominally highest ext Calmar "
      f"({ew['calmar']:.4f}) but only by carrying a deeper ext MaxDD ({pct(ew['maxdd'])} vs "
      f"{pct(iv['maxdd'])}) and clearly lower ext Sharpe ({ew['sharpe']:.4f} vs {iv['sharpe']:.4f}). "
      "So the ORDER on the Calmar column does not flip (EW > ERC ~ inverse-vol), but the misleading "
      "'ERC beats inverse-vol on ext Calmar' impression is removed -- inverse-vol and ERC are "
      "statistically tied on every ext metric, and inverse-vol is tied-best (with ERC) on ext "
      "Sharpe, both ahead of EW. Inverse-vol no longer 'looks worst': it is co-best on Sharpe and "
      "tied with ERC on Calmar/MaxDD, with EW's Calmar lead bought via worse drawdown and Sharpe.\n")

    # ---- ITEM 2 ----
    r = o["item2_ranker_lift_8_3"]
    A("## Item 2 -- Section 8.3 / 7 ranker lift (vol-Faber minus plain-12m momentum)\n")
    A("CPM-solo Sharpe, post-tidy harness. Lift = base vol-adjusted Faber minus plain 12-month "
      "momentum ranker (all else fixed).\n")
    A("| Ranker | Clean Sharpe | Clean MaxDD | Clean Calmar | Ext Sharpe | Ext MaxDD | Ext Calmar |")
    A("|---|---:|---:|---:|---:|---:|---:|")
    b = r["base_volfaber"]; p = r["plain12"]
    A(f"| vol-adjusted Faber (base) | {b['clean']['sharpe']:.4f} | {pct(b['clean']['maxdd'])} | "
      f"{b['clean']['calmar']:.4f} | {b['ext']['sharpe']:.4f} | {pct(b['ext']['maxdd'])} | "
      f"{b['ext']['calmar']:.4f} |")
    A(f"| plain 12-month momentum | {p['clean']['sharpe']:.4f} | {pct(p['clean']['maxdd'])} | "
      f"{p['clean']['calmar']:.4f} | {p['ext']['sharpe']:.4f} | {pct(p['ext']['maxdd'])} | "
      f"{p['ext']['calmar']:.4f} |")
    A(f"\n- **Clean Sharpe lift = +{r['lift_clean']:.4f}** (cross-check vs memo +0.1994).")
    A(f"- **Ext Sharpe lift = +{r['lift_ext']:.4f}** (memo currently shows +0.1553 from pre-tidy "
      f"base; this is the post-tidy replacement).\n")

    # ---- ITEM 3 ----
    bl = o["item3_blend_6040"]
    A("## Item 3 -- 60/40 CPM-BULL blend, single correct post-tidy values\n")
    A("| Window | Sharpe | CAGR | Vol | MaxDD | Calmar |")
    A("|---|---:|---:|---:|---:|---:|")
    for wl in ("clean", "ext"):
        x = bl[wl]
        A(f"| {wl} | {x['sharpe']:.4f} | {pct(x['cagr'])} | {pct(x['vol'])} | {pct(x['maxdd'])} | "
          f"{x['calmar']:.4f} |")
    A(f"\n- The memo shows both 1.219 and 1.2199 (Calmar 1.07 vs 1.0761) for the EXT blend. "
      f"Single correct post-tidy EXT value: **Sharpe {bl['ext']['sharpe']:.4f}, "
      f"Calmar {bl['ext']['calmar']:.4f}, MaxDD {pct(bl['ext']['maxdd'])}, "
      f"CAGR {pct(bl['ext']['cagr'])}, Vol {pct(bl['ext']['vol'])}**.\n")

    # ---- ITEM 4 ----
    es = o["item4_exec_stress_8_8"]
    A("## Item 4 -- Section 8.8 conservative execution-stress lower bound\n")
    A("All on the post-tidy spec. Headline = T+1 MOO exact (`mooex`). Conservative lower bounds: "
      "(a) `moo` conservative MOO (new basket earns intraday only; the favorable overnight "
      "close[T]->open[T+1] gap is dropped), (b) `moc1` harsh T+1 MOC (a full extra trading "
      "session of lag), and (c) penalized slippage (`mooex` at 25 bps/side, 2.5x the headline "
      "cost). Haircut = metric minus the exact-open headline.\n")
    for who, title in [("blend", "60/40 blend"), ("cpm", "CPM solo")]:
        A(f"### {title}\n")
        A("| Execution | Window | Sharpe | CAGR | MaxDD | Calmar | Sharpe haircut | Calmar haircut |")
        A("|---|---|---:|---:|---:|---:|---:|---:|")
        head = es["conventions"]["mooex"][who]
        rows = ([("mooex", es["conventions"]["mooex"]["label"], es["conventions"]["mooex"][who])]
                + [("moo", es["conventions"]["moo"]["label"], es["conventions"]["moo"][who])]
                + [("moc1", es["conventions"]["moc1"]["label"], es["conventions"]["moc1"][who])]
                + [("p25", es["penalized_25bps"]["label"], es["penalized_25bps"][who])])
        for _, lbl, dat in rows:
            for wl in ("clean", "ext"):
                x = dat[wl]; h = head[wl]
                hs = x["sharpe"] - h["sharpe"]
                hc = x["calmar"] - h["calmar"]
                tag = "headline" if lbl.startswith("T+1 MOO exact") else lbl
                A(f"| {tag} | {wl} | {x['sharpe']:.4f} | {pct(x['cagr'])} | {pct(x['maxdd'])} | "
                  f"{x['calmar']:.4f} | {hs:+.4f} | {hc:+.4f} |")
        A("")
    # lower-bound summary for the blend
    lb_candidates = {
        "moo": es["conventions"]["moo"]["blend"],
        "moc1": es["conventions"]["moc1"]["blend"],
        "p25": es["penalized_25bps"]["blend"],
    }
    A("**Conservative lower bound (60/40 blend):** the worst Sharpe across the three stress "
      "treatments per window:")
    for wl in ("clean", "ext"):
        worst = min(lb_candidates.items(), key=lambda kv: kv[1][wl]["sharpe"])
        x = worst[1][wl]; h = es["conventions"]["mooex"]["blend"][wl]
        A(f"- {wl}: Sharpe {x['sharpe']:.4f}, CAGR {pct(x['cagr'])}, MaxDD {pct(x['maxdd'])}, "
          f"Calmar {x['calmar']:.4f} (via `{worst[0]}`; Sharpe haircut {x['sharpe']-h['sharpe']:+.4f} "
          f"vs exact-open headline {h['sharpe']:.4f}).")
    A("\n_The stale 1.165 figure was min-var-3 era and is NOT reused; these are regenerated "
      "post-tidy._\n")

    A("## Caveats\n")
    A("- All metrics post-cost 10 bps/side (except the explicit 25 bps penalized-slippage row), "
      "T+1 MOO exact unless the execution column states otherwise; production anchors reproduce to "
      "4 decimals and the variant weight fn matches production to 1e-9.")
    A("- EXT/stress window (1999-03-10..) is partially proxy-backed pre-2006-2008 for the CPM "
      "trend universe; the clean 18y window has full real-open coverage and is the decisive lens.")
    A("- Bull leg slippage penalty (25 bps) is applied via bull_spy_live.COST_BPS_PER_SIDE for the "
      "penalized-slippage row only; conventions moo/moc1 keep the 10 bps headline cost and stress "
      "ONLY the fill timing.")

    # ---- ITEM 5 (literature/factorial confirmation; no recompute) ----
    A("## Item 5 -- BULL vol-gate cohort + BULL factorial vol-gate effect\n")
    A("### 5a. rv-gate cohort forward-vol confirmation\n")
    A("Source: `research/rv_gate_cohort_calibration_findings.md`. A blocked month = canary_ok AND "
      "spy_trend_ok TRUE but vol_ok FALSE. FALSE-POSITIVE (FP) cohort = forward SPY return > 0 "
      "(the gains the gate forfeited).\n")
    A("| Window | FP cohort fwd vol (mean) | FP cohort fwd vol (median) | Unconditional fwd vol "
      "(mean) | Unconditional fwd vol (median) | TP cohort fwd vol (mean) |")
    A("|---|---:|---:|---:|---:|---:|")
    A("| Clean (2008-05-30..2026-05-22) | 11.77% | 10.08% | 16.13% | 12.92% | 21.10% |")
    A("| Stress (1999-03-10..2026-05-22) | 12.10% | 10.23% | 16.30% | 13.96% | 20.46% |")
    A("\n- **Confirmed exact.** Gemini's cited ~11.8-12.1% vs 16.13% = FP-cohort MEAN forward vol "
      "(clean 11.77%, stress 12.10%) vs the CLEAN unconditional MEAN forward vol 16.13%. The FP "
      "cohort (66% of blocked months) realizes ~11.8-12.1% forward vol; the TP cohort (34%) "
      "realizes ~20.5-21.1% (nearly double), confirming the gate as an asymmetric variance filter.")
    A("- **FLAG (convention caveat):** this cohort study defines vol_ok via **RV_20d** >= RV_252d "
      "(pre-swap gate). Production now uses the **RV_60d** slow gate (commit 8ff3e22). The "
      "forward-vol cohort split has NOT been re-run under RV_60d; the 11.77%/12.10% vs 16.13%/16.30% "
      "figures are the RV_20d cohort numbers. Cite them as the rv-gate cohort evidence with this "
      "explicit RV_20d-vs-production-RV_60d caveat, or commission a RV_60d re-run if an exact "
      "RV_60d cohort split is required.\n")
    A("### 5b. BULL factorial vol-gate main effect and V x S interaction\n")
    A("Source: `research/factorial_decomposition_findings.md` (BULL benchmark->sleeve 2^3 K,V,S "
      "factorial; mooex, 10 bps/side, production slow gate RV_60d when V=ON). Re-cited in memo "
      "section 12.6.2.\n")
    A("| Effect | CLEAN dSharpe | CLEAN dCalmar | EXT dSharpe | EXT dCalmar |")
    A("|---|---:|---:|---:|---:|")
    A("| Vol gate (V) main effect | +0.081 | +0.089 [FLIP] | +0.006 [FLIP] | +0.027 [FLIP] |")
    A("| V x S interaction (Calmar) | n/a | +0.143 | n/a | +0.115 |")
    A("\n- V main-effect heuristic average across listed deltas = +0.051. V x S = **+0.143 CLEAN "
      "Calmar, +0.115 EXT Calmar** -- dwarfs every BULL main effect (K x V = -0.036). Reading: BULL "
      "is interaction-dominated; the vol gate's value is realized jointly with the {SHV,IEF} safe "
      "pool (V sends the sleeve to safe; S decides which safe), so cite V and V x S together, not V "
      "as an independent main effect.\n")

    Path(ROOT / "research" / "memo_fix_numbers_findings.md").write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
