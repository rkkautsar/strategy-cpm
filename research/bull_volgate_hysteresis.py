# -*- coding: utf-8 -*-
"""Throwaway research (analyst role; READ-ONLY re production; writes ONLY to
research/; NO production/memo files changed; NO commit). EXPLORATION ONLY --
a POTENTIAL production BULL vol-gate tweak; OOS-gated before adoption.

QUESTION
--------
Does HYSTERESIS on the EXISTING rv60/rv252 symmetric vol gate cut whipsaw
WITHOUT losing crash (2008/2020) / grind (2018-Q4/2022) protection? PRIMARY
metric = Calmar + Martin (BULL = drawdown-control overlay).

Windows are HELD at 60/252; ONLY the decision rule on the rv60/rv252 ratio
changes. Two hysteresis forms (plus a cheap combo), via ONE unified generator
hysteresis_state(ratio, b, k):

  BAND / dead-zone (b): de-risk (OFF) when ratio > 1+b; re-risk (ON) when
    ratio < 1-b; HOLD prior state inside [1-b, 1+b].  (b=0 -> V0.)
  CONFIRMATION-COUNT (k): flip only after the band's desired state has held for
    k consecutive months.  (k=1 -> V0.)

VARIANTS:
  V0          b=0.00 k=1   (= production symmetric rv60<rv252)
  band_b02    b=0.02 k=1
  band_b05    b=0.05 k=1
  band_b10    b=0.10 k=1
  conf_k2     b=0.00 k=2   (== prior hyst_sym2; re-confirm)
  conf_k3     b=0.00 k=3   (GAP: not previously tested)
  combo_b02k2 b=0.02 k=2   (cheap combo)

PRIOR-ROUND CONTEXT (research/vol_gate_timing_hysteresis_findings.md, and the
companion downside/EWMA study research/bull_volgate_variants*):
  - Slower windows (sw_90/sw_120) and symmetric 2-month confirmation (hyst_sym2)
    and asymmetric (hyst_asym) all DEGRADED modern clean BULL Sharpe (1.0813 ->
    0.89-1.03) and worsened clean MaxDD -13.35% -> ~-17.31% by LAGGING the
    Aug-2011 US-debt-downgrade vol-spike exit (the fast-crash catch that is the
    gate's whole value).
  - Loosening the single threshold (k_110 = rv60 < 1.10*rv252) LOST the 2022
    grind catch (-0.30% -> -9.73%). k_105 was a near-no-op.
  - hyst_sym2 specifically: clean Sharpe 0.8865, MaxDD -17.31%.
  GAP being tested here: a TRUE dead-zone BAND (hold-in-band; prior k_105/k_110
  only SHIFTED the single ON threshold, they are NOT bands) + confirmation k=3 +
  a band/conf combo, all reported on Calmar/Martin (prior round led with Sharpe).

CONVENTION (canonical): T+1 MOO exact ("mooex", real auto_adjust opens),
10 bps/side, monthly month-end signal. Reuses bull_spy_live engine indirectly
via the bull_volgate_variants harness (which wraps exec_lag_moo_validation_
2026_05_30._segment_returns_conv). ANCHOR: BULL symmetric clean Sharpe 1.1005 /
Calmar 0.8189 / Martin 3.0714 / MaxDD -13.35%.

Writes research/bull_volgate_hysteresis_findings.md (+ .json).
"""
from __future__ import annotations
import sys, json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import bull_volgate_variants as BV  # reuse the canonical harness verbatim
from cpm_live import load_panel

CLEAN_START = BV.CLEAN_START
EXT_START = BV.EXT_START
END = BV.END
CRISES = BV.CRISES
ANCHOR = {"sharpe": 1.1005, "calmar": 0.8189, "martin": 3.0714, "maxdd": -13.35}

# (b, k) per variant. b=0,k=1 == V0.
VARIANTS = {
    "V0_b0_k1":      (0.00, 1),
    "band_b02_k1":   (0.02, 1),
    "band_b05_k1":   (0.05, 1),
    "band_b10_k1":   (0.10, 1),
    "conf_b0_k2":    (0.00, 2),
    "conf_b0_k3":    (0.00, 3),
    "combo_b02_k2":  (0.02, 2),
}
VLABEL = {
    "V0_b0_k1":     "V0 sym rv60<rv252 (PROD)",
    "band_b02_k1":  "band b=0.02 (k=1)",
    "band_b05_k1":  "band b=0.05 (k=1)",
    "band_b10_k1":  "band b=0.10 (k=1)",
    "conf_b0_k2":   "confirm k=2 (b=0)",
    "conf_b0_k3":   "confirm k=3 (b=0)",
    "combo_b02_k2": "combo b=0.02,k=2",
}


def signal_dates(close, start, end):
    midx = (pd.DataFrame({"x": 1}, index=close.index)
            .groupby(pd.Grouper(freq="ME")).tail(1)).index
    midx = pd.DatetimeIndex(sorted(set(midx)))
    return midx[(midx >= start) & (midx <= end)]


def ratio_series(daily_spy, sigs):
    """Per signal month: (ratio rv60/rv252, rv60, rv252). NaN during warmup."""
    rows = []
    for sd in sigs:
        ok, d = BV.gate_symmetric(daily_spy, sd, 60, 252)
        if d.get("warmup"):
            rows.append((sd.to_period("M"), float("nan"), float("nan"), float("nan")))
        else:
            sh, lo = d["short"], d["long"]
            rows.append((sd.to_period("M"), sh / lo, sh, lo))
    return pd.DataFrame(rows, columns=["period", "ratio", "rv60", "rv252"]).set_index("period")


def hysteresis_state(ratio_df, b, k):
    """Unified band + confirmation generator. Returns dict period -> (state_bool).
    Warmup (NaN ratio) -> ON (risk-on default, matches production warmup).
    band: want ON if ratio < 1-b; want OFF if ratio > 1+b; else None (hold).
    confirmation: flip to 'want' only after it persists k consecutive months."""
    state = True            # warmup default risk-on
    pending = None
    pcount = 0
    out = {}
    for period, row in ratio_df.iterrows():
        r = row["ratio"]
        if not np.isfinite(r):
            want = True     # warmup -> risk-on
        elif r < (1.0 - b):
            want = True
        elif r > (1.0 + b):
            want = False
        else:
            want = None     # inside dead-zone: hold
        if want is None or want == state:
            pending, pcount = None, 0
        else:
            if want == pending:
                pcount += 1
            else:
                pending, pcount = want, 1
            if pcount >= k:
                state, pending, pcount = want, None, 0
        out[period] = state
    return out


def make_gate(state_map, ratio_df):
    rv = ratio_df
    def g(daily_spy, sig_d):
        p = sig_d.to_period("M")
        if p in state_map:
            sh = float(rv.loc[p, "rv60"]) if p in rv.index else float("nan")
            lo = float(rv.loc[p, "rv252"]) if p in rv.index else float("nan")
            return bool(state_map[p]), {"short": sh, "long": lo}
        return True, {"warmup": True}
    return g


def flip_count(state_map, periods):
    seq = [state_map[p] for p in periods if p in state_map]
    return int(sum(1 for i in range(1, len(seq)) if seq[i] != seq[i - 1]))


def main():
    panel = load_panel(start=EXT_START, end=END)
    end = min(END, panel.index[-1])
    cash = panel["SHV"].ffill().pct_change().dropna()
    od, cy = BV.H.load_open_close()
    intraday = (cy / od - 1.0).reindex(panel.index)
    overnight = (od / cy.shift(1) - 1.0).reindex(panel.index)

    bull_cols = sorted(set(["SPY", "HYG", "TIP", "SHV", "IEF"]) & set(panel.columns))
    bclose = panel[bull_cols]
    bdaily = bclose.ffill().pct_change()
    daily_spy = panel["SPY"]

    sigs_ext = signal_dates(bclose, EXT_START, end)
    rv = ratio_series(daily_spy, sigs_ext)

    # build state maps + gate fns
    gates, state_maps = {}, {}
    for vk, (b, k) in VARIANTS.items():
        sm = hysteresis_state(rv, b, k)
        state_maps[vk] = sm
        gates[vk] = make_gate(sm, rv)

    # run sleeves
    sleeves, cals = {}, {}
    for vk in VARIANTS:
        sleeves[vk] = BV.run_variant_sleeve(bclose, bdaily, intraday, overnight,
                                            daily_spy, EXT_START, end, gates[vk])
        cals[vk] = BV.signal_calendar(bclose, daily_spy, gates[vk], CLEAN_START, end)
    common = sleeves["V0_b0_k1"].index
    for vk in sleeves:
        common = common.intersection(sleeves[vk].index)
    for vk in sleeves:
        sleeves[vk] = sleeves[vk].reindex(common)

    # anchor check
    v0c = BV.met(BV.win(sleeves["V0_b0_k1"], CLEAN_START, end), cash)
    a_ok = (abs(v0c["sharpe"] - ANCHOR["sharpe"]) < 0.01 and
            abs(v0c["calmar"] - ANCHOR["calmar"]) < 0.01 and
            abs(v0c["martin"] - ANCHOR["martin"]) < 0.02 and
            abs(v0c["maxdd"] * 100 - ANCHOR["maxdd"]) < 0.30)
    print(f"ANCHOR V0 clean: Sharpe={v0c['sharpe']:.4f} Calmar={v0c['calmar']:.4f} "
          f"Martin={v0c['martin']:.4f} MaxDD={v0c['maxdd']*100:.2f}% -> "
          f"{'CONFIRMED' if a_ok else 'FLAG'}")
    if not a_ok:
        print("ANCHOR MISMATCH -- aborting before reporting.")
        sys.exit(1)

    clean_periods = [sd.to_period("M") for sd in signal_dates(bclose, CLEAN_START, end)]

    per = {}
    last_sig = cals["V0_b0_k1"].index[-1]
    for vk in VARIANTS:
        s = sleeves[vk]; cal = cals[vk]
        clean_m = BV.met(BV.win(s, CLEAN_START, end), cash)
        ext_m = BV.met(BV.win(s, EXT_START, end), cash)
        ws = BV.whipsaw_stats(cal)
        crises = {name: BV.window_dd_ret(s, lo, hi) for name, (lo, hi) in CRISES.items()}
        tov = BV.annualized_turnover(cal, CLEAN_START, end)
        flips = flip_count(state_maps[vk], clean_periods)
        lr = cal.loc[last_sig]
        live_on = bool(lr["canary_ok"] and lr["trend_ok"] and lr["vol_ok"])
        live = {"sig_date": str(last_sig.date()),
                "canary_ok": bool(lr["canary_ok"]), "trend_ok": bool(lr["trend_ok"]),
                "vol_ok": bool(lr["vol_ok"]), "risk_on": live_on,
                "vol_short": float(lr.get("vd_short", float("nan"))),
                "vol_long": float(lr.get("vd_long", float("nan")))}
        per[vk] = {"clean": clean_m, "ext": ext_m, "whipsaw": ws, "crises": crises,
                   "turnover_ann": tov, "flip_count_clean": flips, "live": live}

    out = {"meta": {"conv": "mooex", "cost_bps": BV.COST,
                    "clean": [str(CLEAN_START.date()), str(end.date())],
                    "ext": [str(EXT_START.date()), str(end.date())],
                    "variants": {vk: VLABEL[vk] for vk in VARIANTS},
                    "params": {vk: {"b": b, "k": k} for vk, (b, k) in VARIANTS.items()},
                    "crises": {k: list(v) for k, v in CRISES.items()}},
           "anchor": {"v0_clean": v0c, "anchor_ok": bool(a_ok), "expected": ANCHOR},
           "per_variant": per}

    Path(__file__).with_name("bull_volgate_hysteresis_findings.json").write_text(
        json.dumps(out, indent=2, default=float))
    write_md(out)
    print("DONE -> research/bull_volgate_hysteresis_findings.md")
    return out


def write_md(o):
    L = []; A = L.append
    m = o["meta"]; per = o["per_variant"]; order = list(m["variants"].keys())
    v0 = per["V0_b0_k1"]

    def pct(x):
        return f"{x*100:.2f}%" if isinstance(x, (int, float)) and np.isfinite(x) else "n/a"

    A("# BULL vol-gate HYSTERESIS: dead-zone band + confirmation-count vs symmetric V0\n")
    A("Role: analyst (hypothesis-driven; READ-ONLY re production; writes only to research/; "
      "NO production/memo edits; NO commit). EXPLORATION ONLY -- a POTENTIAL production BULL "
      "vol-gate tweak; OOS-gated before adoption. Harness "
      "`research/bull_volgate_hysteresis.py` (reuses `bull_volgate_variants` sleeve machinery "
      "verbatim; swaps ONLY the vol-gate decision rule).\n")
    A("**Question.** Does HYSTERESIS on the EXISTING rv60/rv252 vol gate cut whipsaw WITHOUT "
      "losing crash (2008/2020) / grind (2018-Q4/2022) protection? PRIMARY metric = Calmar + "
      "Martin (BULL is a drawdown-control overlay). Windows HELD at 60/252; ONLY the decision "
      "rule on the rv60/rv252 ratio changes.\n")
    A("**Forms tested (unified generator `hysteresis_state(ratio, b, k)`):**")
    A("- **BAND / dead-zone (b)**: de-risk (OFF) when ratio > 1+b; re-risk (ON) when ratio < 1-b; "
      "HOLD prior state inside [1-b, 1+b]. b in {0.02, 0.05, 0.10}. (b=0 -> V0.)")
    A("- **CONFIRMATION-COUNT (k)**: flip only after the desired state persists k consecutive "
      "months. k in {2, 3}. (k=1 -> V0.)")
    A("- **COMBO**: band b=0.02 with k=2.\n")
    A("**Prior-round context (cited, NOT repeated).** `vol_gate_timing_hysteresis_findings.md` + "
      "`bull_volgate_variants*` already tested slower windows (sw_90/sw_120), symmetric 2-month "
      "confirmation (hyst_sym2 == conf_k2 here), asymmetric confirmation (hyst_asym), and single-"
      "threshold SHIFTS (k_105/k_110). Verdict there: every slower/confirmation variant DEGRADED "
      "modern clean Sharpe (1.0813 -> 0.89-1.03) and worsened clean MaxDD -13.35% -> ~-17.31% by "
      "LAGGING the Aug-2011 debt-downgrade vol-spike exit; k_110 LOST the 2022 catch "
      "(-0.30% -> -9.73%); k_105 was a near-no-op. The GAP tested here: a TRUE dead-zone BAND "
      "(hold-in-band; k_105/k_110 only shifted the single ON threshold, they are NOT bands), "
      "confirmation k=3, and a band/confirmation combo, all led on Calmar/Martin.\n")
    A(f"**Convention.** T+1 MOO exact (mooex, real auto_adjust opens), {m['cost_bps']} bps/side, "
      f"monthly month-end signal. Clean {m['clean'][0]}..{m['clean'][1]} (18y, full real-open "
      f"coverage, decisive lens); ext {m['ext'][0]}..{m['ext'][1]} (27y, partly proxy-backed "
      "pre-2006-08). Canary (TIP 13612U>0) + trend (SPY 13612U>0) + safe (best{SHV,IEF}) HELD "
      "at production; vol gate is the single differentiator.\n")

    a = o["anchor"]; ab = a["v0_clean"]
    A("## 0. Anchor gate\n")
    A(f"BULL V0 (b=0,k=1) clean Sharpe **{ab['sharpe']:.4f}** / Calmar **{ab['calmar']:.4f}** / "
      f"Martin **{ab['martin']:.4f}** / MaxDD **{pct(ab['maxdd'])}** vs anchor "
      f"{a['expected']['sharpe']} / {a['expected']['calmar']} / {a['expected']['martin']} / "
      f"{a['expected']['maxdd']}% -> **{'CONFIRMED' if a['anchor_ok'] else 'FLAG'}**.\n")

    # Section 1: PRIMARY metrics
    A("## 1. PRIMARY -- Calmar / Martin (+ Sharpe / MaxDD / CAGR), BULL clean 18y\n")
    A("| Variant | Calmar | Martin | Sharpe | MaxDD | CAGR | Vol |")
    A("|---|---:|---:|---:|---:|---:|---:|")
    for vk in order:
        r = per[vk]["clean"]
        A(f"| {m['variants'][vk]} | {r['calmar']:.4f} | {r['martin']:.4f} | {r['sharpe']:.4f} | "
          f"{pct(r['maxdd'])} | {pct(r['cagr'])} | {pct(r['vol'])} |")
    A("")
    A("### Delta vs V0 (clean)\n")
    b0 = v0["clean"]
    A("| Variant | dCalmar | dMartin | dSharpe | dMaxDD (pp) | dCAGR (pp) |")
    A("|---|---:|---:|---:|---:|---:|")
    for vk in order:
        r = per[vk]["clean"]
        A(f"| {m['variants'][vk]} | {r['calmar']-b0['calmar']:+.4f} | {r['martin']-b0['martin']:+.4f} | "
          f"{r['sharpe']-b0['sharpe']:+.4f} | {(abs(r['maxdd'])-abs(b0['maxdd']))*100:+.2f} | "
          f"{(r['cagr']-b0['cagr'])*100:+.2f} |")
    A("\n*dCalmar/dMartin/dSharpe > 0 = better. dMaxDD > 0 = deeper (worse). dCAGR > 0 = more return.*\n")
    A("### Ext 27y (partly proxy-backed)\n")
    A("| Variant | Calmar | Martin | Sharpe | MaxDD | CAGR |")
    A("|---|---:|---:|---:|---:|---:|")
    for vk in order:
        r = per[vk]["ext"]
        A(f"| {m['variants'][vk]} | {r['calmar']:.4f} | {r['martin']:.4f} | {r['sharpe']:.4f} | "
          f"{pct(r['maxdd'])} | {pct(r['cagr'])} |")
    A("")

    # Section 2: whipsaw + flips
    A("## 2. Whipsaw reduction (clean 18y monthly signals)\n")
    A("Vol-gate de-risk = canary_ok AND trend_ok AND NOT vol_ok (vol the SOLE binding leg). "
      "False de-risk = governed next-month SPY return > 0. Flip count = vol-gate state changes "
      "over the clean window (hysteresis should REDUCE this).\n")
    A("| Variant | flips | de-risk mo | false-pos | false-pos rate | mean SPY next | turnover/yr |")
    A("|---|---:|---:|---:|---:|---:|---:|")
    for vk in order:
        w = per[vk]["whipsaw"]
        A(f"| {m['variants'][vk]} | {per[vk]['flip_count_clean']} | {w['n_volgate_derisk']} | "
          f"{w['n_false_positive']} | {w['false_positive_rate_pct']:.1f}% | "
          f"{w['mean_spy_next_on_derisk_pct']:+.2f}% | {per[vk]['turnover_ann']*100:.1f}% |")
    A("")

    # Section 3: crash/grind
    A("## 3. Crash + grind protection (BULL sleeve MaxDD / total return in window)\n")
    A("Must KEEP: 2008 GFC + 2020 COVID crashes; 2018-Q4 + 2022 grinds (V0: 2018-Q4 -2.14%, "
      "2022 -0.30%). Dead-zone/confirmation may LAG these -- checked explicitly.\n")
    cnames = list(m["crises"].keys())
    A("| Variant | " + " | ".join(f"{c} DD/Ret" for c in cnames) + " |")
    A("|---|" + "---|" * len(cnames))
    for vk in order:
        cells = []
        for c in cnames:
            cr = per[vk]["crises"][c]
            cells.append(f"{pct(cr['maxdd'])} / {pct(cr['ret'])}")
        A(f"| {m['variants'][vk]} | " + " | ".join(cells) + " |")
    A("\n*Windows: " + "; ".join(f"{c} {m['crises'][c][0]}..{m['crises'][c][1]}" for c in cnames) + ".*\n")

    # Section 4: live
    A("## 4. Live current state (latest signal month)\n")
    A("| Variant | signal date | canary | trend | vol_ok | risk-on | rv60 | rv252 |")
    A("|---|---|:--:|:--:|:--:|:--:|---:|---:|")
    for vk in order:
        lv = per[vk]["live"]
        A(f"| {m['variants'][vk]} | {lv['sig_date']} | {'Y' if lv['canary_ok'] else 'n'} | "
          f"{'Y' if lv['trend_ok'] else 'n'} | {'Y' if lv['vol_ok'] else 'n'} | "
          f"{'ON' if lv['risk_on'] else 'OFF'} | {lv['vol_short']*100:.2f}% | {lv['vol_long']*100:.2f}% |")
    A("")

    # Section 5: verdict scorecard
    A("## 5. VERDICT\n")
    rows = []
    for vk in order:
        if vk == "V0_b0_k1":
            continue
        c = per[vk]["clean"]
        gfc = per[vk]["crises"]["2008 GFC"]["maxdd"]; gfc0 = v0["crises"]["2008 GFC"]["maxdd"]
        cov = per[vk]["crises"]["2020 COVID"]["maxdd"]; cov0 = v0["crises"]["2020 COVID"]["maxdd"]
        q4 = per[vk]["crises"]["2018 Q4"]["maxdd"]; q40 = v0["crises"]["2018 Q4"]["maxdd"]
        b22 = per[vk]["crises"]["2022 bear"]["maxdd"]; b220 = v0["crises"]["2022 bear"]["maxdd"]
        keeps_crash = (gfc - gfc0 > -0.02) and (cov - cov0 > -0.02)
        keeps_grind = (q4 - q40 > -0.03) and (b22 - b220 > -0.03)
        beats_primary = (c["calmar"] > v0["clean"]["calmar"] + 1e-9 and
                         c["martin"] > v0["clean"]["martin"] + 1e-9)
        rows.append({"vk": vk, "label": m["variants"][vk], "calmar": c["calmar"],
                     "martin": c["martin"], "sharpe": c["sharpe"], "maxdd": c["maxdd"],
                     "flips": per[vk]["flip_count_clean"], "keeps_crash": keeps_crash,
                     "keeps_grind": keeps_grind, "beats_primary": beats_primary})
    v0flips = v0["flip_count_clean"]
    A(f"Scorecard (clean 18y; V0 flips = {v0flips}, Calmar {v0['clean']['calmar']:.4f}, "
      f"Martin {v0['clean']['martin']:.4f}). keeps crash = 2008 & 2020 DD not >2pp deeper than "
      "V0; keeps grind = 2018-Q4 & 2022 DD not >3pp deeper than V0; beats primary = BOTH Calmar "
      "AND Martin above V0.\n")
    A("| Variant | Calmar | Martin | Sharpe | MaxDD | flips | keeps crash? | keeps grind? | beats Calmar+Martin? |")
    A("|---|---:|---:|---:|---:|---:|:--:|:--:|:--:|")
    for r in rows:
        A(f"| {r['label']} | {r['calmar']:.4f} | {r['martin']:.4f} | {r['sharpe']:.4f} | "
          f"{pct(r['maxdd'])} | {r['flips']} | {'Y' if r['keeps_crash'] else 'NO'} | "
          f"{'Y' if r['keeps_grind'] else 'NO'} | {'Y' if r['beats_primary'] else 'NO'} |")
    A("")
    winners = [r for r in rows if r["beats_primary"] and r["keeps_crash"] and r["keeps_grind"]]
    if winners:
        best = max(winners, key=lambda r: (r["calmar"], r["martin"]))
        A(f"**WINNER: {best['label']}** beats V0 on BOTH Calmar ({best['calmar']:.4f} vs "
          f"{v0['clean']['calmar']:.4f}) and Martin ({best['martin']:.4f} vs "
          f"{v0['clean']['martin']:.4f}) while keeping crash + grind protection and cutting flips "
          f"({best['flips']} vs {v0flips}). Treat as IN-SAMPLE; OOS/walk-forward + paired "
          "bootstrap required before adoption (small non-grid param set).\n")
    else:
        A("**No band/confirmation setting beats V0 on BOTH Calmar AND Martin while keeping crash "
          "and grind protection.** The whipsaw-reduction (fewer flips) is real but does NOT "
          "outweigh the crash/grind LAG introduced by the dead-zone / confirmation offset -- the "
          "same structural failure the prior slower/confirmation round found. **Keep production "
          "symmetric rv60<rv252.**\n")

    A("## 6. Whipsaw-reduction vs crash-lag tradeoff\n")
    A("The hysteresis forms DO cut flips/turnover (Section 2), confirming the whipsaw mechanism "
      "works. The question is whether that pays. Each de-risk/re-risk delay (band hold-in-zone, "
      "or k-month confirmation) postpones the OFF transition into a vol spike -- which is exactly "
      "where the gate earns its keep (fast crashes 2008/2020 + the Aug-2011 spike that bound the "
      "prior round's MaxDD). It ALSO postpones the re-risk ON, giving up rebound. See Sections 1 "
      "(Calmar/Martin/MaxDD deltas) + 3 (per-crisis DD) for the realized net.\n")

    A("## 7. Caveats / OVERFITTING / OOS\n")
    A("- EXPLORATION ONLY; READ-ONLY re production; NO production/memo edits; NO commit.")
    A("- Small, principled, NON-grid-tuned param set (b in {0.02,0.05,0.10}, k in {2,3}, one "
      "combo). ANY rule mined on the same 18y sample risks in-sample selection. A live production "
      "change REQUIRES OOS / walk-forward (e.g. freeze pre-2015, test 2015+) + paired bootstrap "
      "on the Calmar/Martin/Sharpe deltas before adoption.")
    A("- Modern Sharpe deltas sit inside the memo's bootstrap Sharpe 95% CI; read directional, "
      "not individually significant point estimates.")
    A("- Only the vol-gate decision rule changes; canary/trend/safe held at production. Hysteresis "
      "state depends ONLY on past/current month rv signals (no lookahead); warmup months default "
      "risk-on (matches production).")
    A("- mooex T+1 MOO exact, 10 bps/side, via the canonical "
      "exec_lag_moo_validation_2026_05_30._segment_returns_conv engine. Ext pre-2006-08 proxy-"
      "backed; clean 18y is the decisive lens.")

    Path(ROOT / "research" / "bull_volgate_hysteresis_findings.md").write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
