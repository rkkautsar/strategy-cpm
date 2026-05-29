# -*- coding: utf-8 -*-
"""Runner for bull_daily_trend_overlay analysis. Writes findings md."""
import sys
from pathlib import Path
import pandas as pd
import numpy as np

ROOT = Path('/Users/rkautsar/personal/scripts/strategy_cpm')
sys.path.insert(0, str(ROOT))

from bull_daily_trend_overlay import (
    build_bull_overlay, apply_cascade_to_ndx, metrics_row, window_maxdd,
    monthly_sig_dates, CPM_W, BULL_W, NDX_W,
)
from cpm_live import load_panel, run_cpm_backtest, perf_metrics
from ndx_sleeve_live import run_ndx_backtest, load_ndx_panel

WINDOWS = {
    "Clean 2008-05-30..2026-05-22": ("2008-05-30", "2026-05-22"),
    "Stress 1999-03-10..2026-05-22": ("1999-03-10", "2026-05-22"),
}

EPISODES = {
    "2008 GFC (2008-05-30..2009-06-30)": ("2008-05-30", "2009-06-30"),
    "2018Q4 (2018-10-01..2018-12-31)": ("2018-10-01", "2018-12-31"),
    "2020 COVID (2020-02-01..2020-04-30)": ("2020-02-01", "2020-04-30"),
    "2020 full (2020-01-01..2020-12-31)": ("2020-01-01", "2020-12-31"),
    "2022 (2022-01-01..2022-12-31)": ("2022-01-01", "2022-12-31"),
}


def fmt(m):
    return (f"{m['raw_sharpe']:.3f} | {m['excess_sharpe']:.3f} | "
            f"{m['cagr']*100:.2f}% | {m['vol']*100:.2f}% | "
            f"{m['maxdd']*100:.2f}% | {m['calmar']:.2f}")


def run():
    end = pd.Timestamp("2026-05-22")
    panel = load_panel(start=pd.Timestamp("1995-01-01"), end=end)
    ndx_panel = load_ndx_panel()

    md = []
    md.append("# BULL Daily 200d-SMA Intramonth Trend-Exit Overlay - Findings\n")
    md.append("Question: does a conventional daily Faber 200-day SMA intramonth crash exit on the BULL sleeve reduce the LIVE 3-sleeve 60/20/20 blend drawdown, and at what CAGR/Sharpe cost? NO tuned percentage (pure SMA cross).\n")
    md.append("Primary eval = LIVE 3-sleeve 60/20/20 blend. BULL standalone + 60/40 two-sleeve reported for reference.\n")
    md.append("\n## Variants\n")
    md.append("- **V0**: monthly-only (prod baseline)\n")
    md.append("- **V1**: daily 200d SMA exit, NO intramonth re-entry, BULL-only (NDX monthly)\n")
    md.append("- **V2**: daily 200d SMA exit, WITH intramonth re-entry on 200d reclaim, BULL-only\n")
    md.append("- **V3**: daily 200d, NO re-entry, cascade exit to NDX intramonth\n")
    md.append("- **V4**: daily 200d, WITH re-entry, cascade exit to NDX intramonth\n")
    md.append("- **V5**: daily 210d SMA (10-month Faber, secondary signal), NO re-entry, BULL-only\n")
    md.append("\nExecution: exit observed at close[d] -> position effective day d+1 (T+1), matching the monthly gate. Safe leg = best-of-safe (SHV/IEF) at sig_d. Cost 10bps/side on every position change (incl intramonth).\n")

    summary_for_verdict = {}

    for wname, (s, e) in WINDOWS.items():
        start, endw = pd.Timestamp(s), pd.Timestamp(e)
        yrs = (endw - start).days / 365.25
        print(f"=== {wname} ===")
        cpm_r, _ = run_cpm_backtest(panel, start, endw)
        ndx_base, _ = run_ndx_backtest(panel, ndx_panel, start, endw)

        # bull variants
        bull = {}
        exit_masks = {}
        events_map = {}
        flips_map = {}
        bull["V0"], _, _, flips_map["V0"] = build_bull_overlay(panel, start, endw, 200, False, daily_overlay=False)
        bull["V1"], exit_masks["V1"], events_map["V1"], flips_map["V1"] = build_bull_overlay(panel, start, endw, 200, False)
        bull["V2"], exit_masks["V2"], events_map["V2"], flips_map["V2"] = build_bull_overlay(panel, start, endw, 200, True)
        bull["V3"], exit_masks["V3"], events_map["V3"], flips_map["V3"] = build_bull_overlay(panel, start, endw, 200, False)
        bull["V4"], exit_masks["V4"], events_map["V4"], flips_map["V4"] = build_bull_overlay(panel, start, endw, 200, True)
        bull["V5"], exit_masks["V5"], events_map["V5"], flips_map["V5"] = build_bull_overlay(panel, start, endw, 210, False)

        # ndx per variant (cascade for V3/V4)
        ndx_var = {v: ndx_base for v in ["V0", "V1", "V2", "V5"]}
        ndx_var["V3"] = apply_cascade_to_ndx(panel, ndx_panel, start, endw, exit_masks["V3"])
        ndx_var["V4"] = apply_cascade_to_ndx(panel, ndx_panel, start, endw, exit_masks["V4"])

        # blends + standalone
        rows_blend = []
        rows_bull = []
        rows_6040 = []
        blends = {}
        for v in ["V0", "V1", "V2", "V3", "V4", "V5"]:
            common = cpm_r.index.intersection(bull[v].index).intersection(ndx_var[v].index)
            blend = CPM_W * cpm_r.loc[common] + BULL_W * bull[v].loc[common] + NDX_W * ndx_var[v].loc[common]
            blends[v] = blend
            rows_blend.append((v, metrics_row(v, blend), flips_map[v] / yrs))
            rows_bull.append((v, metrics_row(v, bull[v].loc[common]), flips_map[v] / yrs))
            # 60/40 two-sleeve = 60% CPM + 40% BULL
            c2 = cpm_r.index.intersection(bull[v].index)
            b6040 = 0.60 * cpm_r.loc[c2] + 0.40 * bull[v].loc[c2]
            rows_6040.append((v, metrics_row(v, b6040), flips_map[v] / yrs))

        summary_for_verdict[wname] = {v: rows_blend[i][1] for i, v in enumerate(["V0","V1","V2","V3","V4","V5"])}

        md.append(f"\n## Window: {wname}  ({yrs:.1f}y)\n")
        md.append("\n### LIVE 3-sleeve 60/20/20 blend (PRIMARY)\n")
        md.append("| Variant | RawSharpe | ExcessSharpe | CAGR | Vol | MaxDD | Calmar | BullFlips/yr |")
        md.append("|---|---|---|---|---|---|---|---|")
        for v, m, tpy in rows_blend:
            md.append(f"| {v} | {fmt(m)} | {tpy:.1f} |")

        md.append("\n### BULL standalone\n")
        md.append("| Variant | RawSharpe | ExcessSharpe | CAGR | Vol | MaxDD | Calmar | Flips/yr |")
        md.append("|---|---|---|---|---|---|---|---|")
        for v, m, tpy in rows_bull:
            md.append(f"| {v} | {fmt(m)} | {tpy:.1f} |")

        md.append("\n### 60/40 two-sleeve (60% CPM + 40% BULL) - reference\n")
        md.append("| Variant | RawSharpe | ExcessSharpe | CAGR | Vol | MaxDD | Calmar |")
        md.append("|---|---|---|---|---|---|---|")
        for v, m, tpy in rows_6040:
            md.append(f"| {v} | {fmt(m)} |")

        # Episodes: blend MaxDD per variant
        md.append("\n### Intramonth-crash episodes - blend MaxDD (and total return)\n")
        ep_in_window = {k: vv for k, vv in EPISODES.items()
                        if pd.Timestamp(vv[0]) >= start and pd.Timestamp(vv[1]) <= endw}
        hdr = "| Episode | " + " | ".join(["V0","V1","V2","V3","V4","V5"]) + " |"
        md.append(hdr)
        md.append("|" + "---|" * (len(["V0","V1","V2","V3","V4","V5"]) + 1))
        for ep, (es, ee) in ep_in_window.items():
            cells = []
            for v in ["V0","V1","V2","V3","V4","V5"]:
                dd, ret = window_maxdd(blends[v], pd.Timestamp(es), pd.Timestamp(ee))
                cells.append(f"{dd*100:.1f}%/{ret*100:+.1f}%")
            md.append(f"| {ep} | " + " | ".join(cells) + " |")
        md.append("\n(cell = MaxDD% / total-return% over the episode window)\n")

        # Whipsaw cohort for V1 (no-reentry, bull-only primary)
        md.append("\n### Whipsaw / false-positive cohort (V1 daily 200d, no re-entry)\n")
        evs = events_map["V1"]
        n = len(evs)
        fwd = np.array([x["fwd_spy_to_monthend"] for x in evs]) if n else np.array([])
        whip = fwd[fwd > 0]   # SPY rose after exit -> missed gains (whipsaw)
        good = fwd[fwd <= 0]  # SPY kept falling -> crash avoided
        md.append(f"- Exit events fired: **{n}** ({n/yrs:.1f}/yr)\n")
        if n:
            md.append(f"- Genuine crashes avoided (SPY fwd<=0 from exit to month-end): **{len(good)}** ({len(good)/n*100:.0f}%), mean fwd SPY {good.mean()*100:+.2f}%\n")
            md.append(f"- Whipsaws (SPY fwd>0, exit locked loss + missed rebound): **{len(whip)}** ({len(whip)/n*100:.0f}%), mean fwd SPY {whip.mean()*100:+.2f}%\n")
            md.append(f"- Net mean fwd SPY across all exits: **{fwd.mean()*100:+.2f}%** (negative = exits net-protective)\n")
            md.append("\n  Exit episodes detail (sig month -> exit day -> fwd SPY to month-end):\n")
            for x in evs:
                md.append(f"  - {x['sig_d'].date()} -> exit {x['exit_day'].date()} -> {x['fwd_spy_to_monthend']*100:+.2f}%\n")

        print(f"  V0 blend MaxDD {rows_blend[0][1]['maxdd']*100:.2f}%  V1 {rows_blend[1][1]['maxdd']*100:.2f}%  V3 {rows_blend[3][1]['maxdd']*100:.2f}%")

    # Verdict
    md.append("\n## Verdict\n")
    clean = summary_for_verdict["Clean 2008-05-30..2026-05-22"]
    stress = summary_for_verdict["Stress 1999-03-10..2026-05-22"]
    md.append("### Blend deltas vs V0 (Clean window)\n")
    v0 = clean["V0"]
    for v in ["V1","V2","V3","V4","V5"]:
        mv = clean[v]
        md.append(f"- {v}: MaxDD {mv['maxdd']*100:.2f}% (d{(mv['maxdd']-v0['maxdd'])*100:+.2f}pp), "
                  f"CAGR {mv['cagr']*100:.2f}% (d{(mv['cagr']-v0['cagr'])*100:+.2f}pp), "
                  f"Sharpe {mv['raw_sharpe']:.3f} (d{mv['raw_sharpe']-v0['raw_sharpe']:+.3f}), "
                  f"Calmar {mv['calmar']:.2f} (d{mv['calmar']-v0['calmar']:+.2f})\n")
    md.append("\n### Blend deltas vs V0 (Stress window)\n")
    v0s = stress["V0"]
    for v in ["V1","V2","V3","V4","V5"]:
        mv = stress[v]
        md.append(f"- {v}: MaxDD {mv['maxdd']*100:.2f}% (d{(mv['maxdd']-v0s['maxdd'])*100:+.2f}pp), "
                  f"CAGR {mv['cagr']*100:.2f}% (d{(mv['cagr']-v0s['cagr'])*100:+.2f}pp), "
                  f"Sharpe {mv['raw_sharpe']:.3f} (d{mv['raw_sharpe']-v0s['raw_sharpe']:+.3f})\n")

    md.append("""
### Synthesis

**1. Where the blend MaxDD actually lives.** V0 blend MaxDD = -11.62% (Clean) is the 2018-Q4 selloff - the one genuine intramonth-crash episode the monthly gate missed (Nov-30 signal stayed risk-on; crash accelerated into late Dec; next re-eval Dec-31). The daily 200d exit fired 2018-10-11 and DID cut that episode: 2018Q4 blend MaxDD -11.6% -> -11.0% (V1 bull-only) -> -8.9% (V3 cascade).

**2. But cutting one episode barely moves the blend floor.** Bull-only (V1): once 2018Q4 is trimmed, the next-worst blend drawdown elsewhere (~-11.5%, not an intramonth crash) becomes binding, so global blend MaxDD improves only +0.14pp (-11.62% -> -11.49%) while CAGR drops -0.49pp and Sharpe -0.027. Net: a wash on DD, a real cost on return. Stress window: V1 MaxDD identical to V0 (-12.69%, 0.00pp) with -0.33pp CAGR.

**3. 2020-COVID is NOT a daily-overlay win.** Contrary to the premise, the monthly gate already handled 2020 (blend DD -9.8%, identical across ALL variants). The Feb-28 month-end signal de-risked BULL for March before the daily 200d cross could add value; the intramonth exit only touched the last 1-2 days of Feb. So of the two hypothesized 'missed' episodes, only 2018-Q4 is real.

**4. The signal is whipsaw-dominated.** Daily 200d exit fired 8x (Clean) / 16x (Stress). Only 38% were genuine crashes avoided; 62% were whipsaws (SPY rose after exit, mean +3.38% Clean / +2.21% Stress missed). Net mean forward SPY across ALL exits = +1.77% (Clean) / +0.88% (Stress) - POSITIVE, i.e. on average the exit fired and then the market went UP. Same false-positive structure as the RV-gate cohort, but worse: the RV gate at least had net-protective true-positive vol asymmetry; this raw SMA cross forfeits return on net.

**5. Cascade (V3) buys more DD but at a steep price.** Cascading the (whipsaw-prone) daily exit to the high-momentum NDX sleeve cuts blend MaxDD by -1.00pp (-11.62% -> -10.63%, Clean) - the only variant with a material DD reduction. But it costs -1.37pp CAGR and -0.081 Sharpe, because the 62% false-positive exits now also forfeit NDX rebound upside. Calmar barely budges (1.54 -> 1.56). In Stress, cascade does NOT even reduce MaxDD (-12.69%, 0.00pp) yet still costs -0.93pp CAGR.

**6. Re-entry (V2/V4) is not a fix.** Allowing 200d-reclaim re-entry recovers some CAGR vs no-reentry but worsens BULL standalone MaxDD to -14.51% (re-entering mid-chop, whipsawed again) and pushes V2 blend MaxDD to -11.72% - WORSE than V0. The 10-month (210d, V5) secondary signal is materially identical to the 200d primary.

### Philosophy cost

The overlay converts BULL (V1/V2/V5) - and for the only DD-meaningful variant V3, ALSO NDX - from a monthly-simple, end-of-month-only strategy into a DAILY-monitored one. That is a large operational/complexity increase (daily SPY-vs-200d check, intramonth rebalances, daily execution discipline) against the explicit monthly-simple design intent.

### Adopt / Reject / Conditional

**REJECT** (all bull-only variants V1/V2/V5): no meaningful blend-DD reduction (<=0.14pp Clean, 0.00pp Stress), a real CAGR cost (-0.3 to -0.5pp), Sharpe/Calmar both down, and the trigger is whipsaw-dominated (62% false positives, net-positive forfeited return). Fails the user's own bar (meaningful MaxDD cut, acceptable CAGR cost, not whipsaw-dominated) on all three counts.

**REJECT** (cascade V3/V4): the only variant with a material DD cut (-1.0pp Clean) pays -1.37pp CAGR and -0.08 Sharpe, leaves Calmar flat, does nothing in the Stress window, and doubles the daily-monitoring burden to two sleeves. The DD/CAGR trade is poor and regime-fragile.

**Bottom line:** The daily 200d-SMA overlay does NOT cleanly reduce the blend drawdown. It cuts the single 2018-Q4 episode but the next-worst non-crash drawdown re-binds the floor, so bull-only is a wash; the only material cut (cascade) is bought with disproportionate CAGR/Sharpe loss and only in one window. Combined with the whipsaw-dominated trigger and the monthly-simple philosophy cost, this is not a worthwhile change. Keep V0.
""")

    out = ROOT / "research" / "bull_daily_trend_overlay_findings.md"
    out.write_text("\n".join(md), encoding="utf-8")
    print(f"\nWrote {out}")


if __name__ == "__main__":
    run()
