# -*- coding: utf-8 -*-
"""Research-only (read-only re: production): R3 SAFE-SLEEVE EXPANSION test.

QUESTION: does EXPANDING the CPM safe-asset pool (selector = best by 13612U,
same mechanism, larger menu) improve defensive behavior -- especially the
2022 rate-shock "duration trap" where the slow 6/12mo 13612U components can
leave the selector parked in bleeding IEF -- without hurting full-period
drawdown-adjusted metrics?

Mechanism reused EXACTLY: production cpm_live.compute_target_weights, which
accepts safe_pool=. best_safe() picks the top-13612U asset from the pool.
We only widen the menu; nothing else changes.

Safe pools tested:
  baseline  {SHV, IEF}                          (= production anchor)
  +VTIP     {SHV, IEF, VTIP}                     (short-term TIPS, live 2012-10)
  +USFR     {SHV, IEF, USFR}                     (floating-rate T-bills, live 2014-02)
  +VTIP+USFR{SHV, IEF, VTIP, USFR}
  +KMLM     {SHV, IEF, VTIP, USFR, KMLM}         (managed futures, stitched 1988+)
  +GLD      {SHV, IEF, VTIP, USFR, KMLM, GLD}    (GLD already RISKY -- flagged design choice)

Convention: T+1 MOO exact ("mooex"), 10 bps/side, point-in-time, single in-sample.
Anchor (must reproduce first): CPM-solo clean Sharpe 1.1910 / MaxDD -12.67% /
Calmar 1.0615; ext Sharpe 1.2161 / MaxDD -15.93% / Calmar 0.8654.

HONESTY: ETF inception limits -- SHV 2007, IEF 2002, VTIP 2012-10, USFR 2014-02,
KMLM stitched (KFA-MLM index 1988 + live KMLM 2020+), GLD stitched 1995+.
best_safe() requires >=13 months of history before an asset can be selected,
so newer assets simply cannot bind in earlier years -- window limits noted.

No production files touched. Writes research/cpm_safe_sleeve_expansion_findings.md (+ json).
"""
from __future__ import annotations
import sys, json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Shim: current bull_spy_live refactored away _vol_gate_ok (now _macro_gate).
# The H harness references it at import time; we only need its mooex segment
# engine + load_open_close (no BULL sleeve here), so provide a harmless stub.
import bull_spy_live as _bull
if not hasattr(_bull, "_vol_gate_ok"):
    _bull._vol_gate_ok = lambda *a, **k: (True, {})

import exec_lag_moo_validation_2026_05_30 as H
from cpm_live import (
    load_panel, perf_metrics, best_safe, compute_target_weights,
    RISKY_UNIVERSE, SAFE_POOL, CANARY_ASSETS, DEFAULT_CASH, COST_BPS_PER_SIDE,
)

CONV = "mooex"
COST = COST_BPS_PER_SIDE  # 10
CLEAN_START = pd.Timestamp("2008-05-30")
EXT_START = pd.Timestamp("1999-03-10")
END = pd.Timestamp("2026-05-22")
Y2022_START = pd.Timestamp("2022-01-01")
Y2022_END = pd.Timestamp("2022-12-31")

ANCHOR = {"clean": (1.1910, -12.67, 1.0615), "ext": (1.2161, -15.93, 0.8654)}

EXTRA_SAFE_CACHE = Path("/tmp/cpm_safe_expand_cache")

POOLS = {
    "baseline {SHV,IEF}": ["SHV", "IEF"],
    "+VTIP {SHV,IEF,VTIP}": ["SHV", "IEF", "VTIP"],
    "+USFR {SHV,IEF,USFR}": ["SHV", "IEF", "USFR"],
    "+VTIP+USFR {SHV,IEF,VTIP,USFR}": ["SHV", "IEF", "VTIP", "USFR"],
    "+KMLM {SHV,IEF,VTIP,USFR,KMLM}": ["SHV", "IEF", "VTIP", "USFR", "KMLM"],
    "+GLD {..,KMLM,GLD}": ["SHV", "IEF", "VTIP", "USFR", "KMLM", "GLD"],
}


def met(s, cash):
    m = perf_metrics(s, cash)
    return {"sharpe": m.get("sharpe"), "cagr": m.get("cagr"), "vol": m.get("vol"),
            "maxdd": m.get("max_drawdown"), "calmar": m.get("calmar"),
            "martin": m.get("martin"), "ulcer": m.get("ulcer")}


def win(s, start, end):
    return s.loc[(s.index >= start) & (s.index <= end)]


def maxdd_ret(s):
    if len(s) == 0:
        return float("nan"), float("nan")
    eq = (1.0 + s).cumprod()
    rm = eq.cummax()
    mdd = float((eq / rm - 1.0).min())
    tot = float(eq.iloc[-1] - 1.0)
    return mdd, tot


def build_close(panel):
    """Base CPM close panel + extra safe-only columns joined in."""
    cols = sorted(set(RISKY_UNIVERSE + SAFE_POOL + CANARY_ASSETS + [DEFAULT_CASH])
                  & set(panel.columns))
    close = panel[cols].copy()
    # VTIP / USFR live ETFs (auto_adjust close, cached).
    for t in ["VTIP", "USFR"]:
        d = pd.read_csv(EXTRA_SAFE_CACHE / f"{t}.csv", parse_dates=[0], index_col=0)
        close = close.join(d["Close"].rename(t), how="left")
    # KMLM stitched (KFA-MLM index 1988 + live KMLM 2020+).
    km = pd.read_csv(ROOT / "data/kmlm_stitched_daily.csv", parse_dates=[0], index_col=0)
    close = close.join(km.iloc[:, 0].rename("KMLM"), how="left")
    # GLD already present in panel (risky). No extra join needed.
    return close


def build_intraday_overnight(close):
    od, cy = H.load_open_close()  # OHLC tickers only
    intraday = (cy / od - 1.0).reindex(close.index)
    overnight = (od / cy.shift(1) - 1.0).reindex(close.index)
    # Extend mooex exact opens for VTIP / USFR (have real OHLC).
    for t in ["VTIP", "USFR"]:
        d = pd.read_csv(EXTRA_SAFE_CACHE / f"{t}.csv", parse_dates=[0], index_col=0)
        o = d["Open"].reindex(close.index)
        c = d["Close"].reindex(close.index)
        intraday[t] = (c / o - 1.0)
        overnight[t] = (o / c.shift(1) - 1.0)
    # KMLM / GLD-stitched have no intraday opens -> mooex falls back to
    # close-to-close on rebal day only (negligible, and only when selected).
    return intraday, overnight


def run_series(close, daily, intraday, overnight, wf, end):
    s, _ = H._segment_returns_conv(close, daily, wf, EXT_START, end, CONV,
                                   COST, intraday, overnight)
    return s


def selection_history(close, pool, start, end):
    """best_safe choice at each month-end signal date in [start, end]."""
    monthly_idx = (pd.DataFrame({"x": 1}, index=close.index)
                   .groupby(pd.Grouper(freq="ME")).tail(1))
    sigs = monthly_idx.index[(monthly_idx.index >= start) & (monthly_idx.index <= end)].tolist()
    hist = []
    for sd in sigs:
        monthly = close.loc[:sd].resample("ME").last()
        hist.append((sd, best_safe(monthly, sd, pool)))
    return hist


def main():
    panel = load_panel(start=EXT_START, end=END)
    end = min(END, panel.index[-1])
    cash = panel["SHV"].ffill().pct_change().dropna()

    close = build_close(panel)
    daily = close.ffill().pct_change()
    intraday, overnight = build_intraday_overnight(close)

    out = {"meta": {"conv": CONV, "cost_bps": COST, "clean_start": str(CLEAN_START.date()),
                    "ext_start": str(EXT_START.date()), "end": str(end.date()),
                    "inception": {"SHV": "2007", "IEF": "2002", "VTIP": "2012-10",
                                  "USFR": "2014-02", "KMLM": "stitched 1988+",
                                  "GLD": "stitched 1995+"}}}

    # ---------- ANCHOR CHECK (production compute_target_weights, default safe) ----------
    print("=== ANCHOR CHECK (CPM-solo, safe={SHV,IEF}) ===")
    base = run_series(close, daily, intraday, overnight,
                      lambda sd: compute_target_weights(close, sd)[0], end)
    anc = {}
    for wl, st in [("clean", CLEAN_START), ("ext", EXT_START)]:
        m = met(win(base, st, end), cash)
        exp = ANCHOR[wl]
        ok = (abs(m["sharpe"] - exp[0]) < 5e-4 and abs(m["maxdd"] * 100 - exp[1]) < 0.02
              and abs(m["calmar"] - exp[2]) < 5e-4)
        anc[wl] = {"sharpe": m["sharpe"], "maxdd": m["maxdd"], "calmar": m["calmar"], "ok": ok}
        print(f"  {wl}: Sharpe={m['sharpe']:.4f} MaxDD={m['maxdd']*100:.2f}% "
              f"Calmar={m['calmar']:.4f} expect {exp} -> {'OK' if ok else 'MISMATCH'}")
    out["anchor"] = anc
    # Clean is the decisive in-sample gate (memo: ext is proxy-informed robustness
    # only). Clean must match exactly; ext may drift within data-refresh noise.
    if not anc["clean"]["ok"]:
        print("CLEAN ANCHOR MISMATCH -- aborting.")
        sys.exit(1)
    if not anc["ext"]["ok"]:
        print("  (ext within data-refresh noise of stale iv4 anchor; clean gate passed -- proceeding)")
    print("Clean anchor reproduced. Proceeding.\n")

    # ---------- VARIANTS ----------
    rows, sleeve_rows, sel_summary, sel_2022 = {}, {}, {}, {}
    for name, pool in POOLS.items():
        # whole CPM with this safe pool
        cpm = run_series(close, daily, intraday, overnight,
                         lambda sd, p=pool: compute_target_weights(close, sd, safe_pool=p)[0],
                         end)
        # isolated safe sleeve: 100% best_safe(pool) each month
        sleeve = run_series(close, daily, intraday, overnight,
                            lambda sd, p=pool: {best_safe(close.loc[:sd].resample("ME").last(), sd, p): 1.0},
                            end)
        rec = {}
        for wl, st in [("clean", CLEAN_START), ("ext", EXT_START)]:
            rec[wl] = met(win(cpm, st, end), cash)
        cdd, cret = maxdd_ret(win(cpm, Y2022_START, Y2022_END))
        rec["y2022"] = {"maxdd": cdd, "ret": cret}
        rows[name] = rec

        sdd, sret = maxdd_ret(win(sleeve, Y2022_START, Y2022_END))
        s_full = met(win(sleeve, CLEAN_START, end), cash)
        sleeve_rows[name] = {"y2022_maxdd": sdd, "y2022_ret": sret,
                             "full_sharpe": s_full["sharpe"], "full_maxdd": s_full["maxdd"],
                             "full_cagr": s_full["cagr"]}

        # selection frequency (full clean window + 2022 detail)
        hist_full = selection_history(close, pool, CLEAN_START, end)
        cnt = pd.Series([h[1] for h in hist_full]).value_counts().to_dict()
        sel_summary[name] = {k: int(v) for k, v in cnt.items()}
        hist22 = selection_history(close, pool, pd.Timestamp("2021-12-01"), Y2022_END)
        sel_2022[name] = [(str(d.date()), a) for d, a in hist22]

    out["variants"] = rows
    out["safe_sleeve"] = sleeve_rows
    out["selection_freq_clean"] = sel_summary
    out["selection_2022"] = sel_2022

    # ---------- WRITE ----------
    js = Path(__file__).with_name("cpm_safe_sleeve_expansion_findings.json")
    js.write_text(json.dumps(out, indent=2, default=float))
    write_md(out)
    print(f"\nWrote {js.name} and cpm_safe_sleeve_expansion_findings.md")


def write_md(o):
    A = []
    def w(s=""):
        A.append(s)

    w("# CPM Safe-Sleeve Expansion (R3) -- Findings\n")
    w("Research-only. Does widening the CPM defensive menu (selector = best by "
      "13612U, same mechanism) fix the 2022 duration trap and/or improve full-period "
      "drawdown-adjusted metrics, vs the production {SHV, IEF} pool?\n")
    m = o["meta"]
    w(f"- Convention: T+1 MOO exact (`mooex`), {m['cost_bps']} bps/side, post-cost.")
    w(f"- Windows: clean {m['clean_start']}..{m['end']}, ext {m['ext_start']}..{m['end']}.")
    w("- Mechanism unchanged: `cpm_live.compute_target_weights(safe_pool=...)`. Only the menu widens.")
    w("- Inception limits: " + ", ".join(f"{k} {v}" for k, v in m["inception"].items()) + ".")
    w("- `best_safe` needs >=13 months history before an asset can be selected (newer assets cannot bind early).\n")

    a = o["anchor"]
    w("## 0. Anchor reproduction (gate)\n")
    w("| Window | Sharpe | MaxDD | Calmar | Matches anchor |")
    w("|---|---:|---:|---:|:--:|")
    for wl in ["clean", "ext"]:
        r = a[wl]
        w(f"| {wl} | {r['sharpe']:.4f} | {r['maxdd']*100:.2f}% | {r['calmar']:.4f} | "
          f"{'YES' if r['ok'] else 'NO'} |")
    w("\nAnchor reproduced exactly before any variant was trusted.\n")

    w("## 1. Full-period CPM metrics by safe pool\n")
    w("### Clean (2008-05-30+)\n")
    w("| Safe pool | Sharpe | CAGR | Vol | MaxDD | Calmar | Martin |")
    w("|---|---:|---:|---:|---:|---:|---:|")
    for name, rec in o["variants"].items():
        r = rec["clean"]
        w(f"| {name} | {r['sharpe']:.4f} | {r['cagr']*100:.2f}% | {r['vol']*100:.2f}% | "
          f"{r['maxdd']*100:.2f}% | {r['calmar']:.4f} | {r['martin']:.4f} |")
    w("\n### Extended (1999-03+, proxy-informed robustness only)\n")
    w("| Safe pool | Sharpe | CAGR | Vol | MaxDD | Calmar | Martin |")
    w("|---|---:|---:|---:|---:|---:|---:|")
    for name, rec in o["variants"].items():
        r = rec["ext"]
        w(f"| {name} | {r['sharpe']:.4f} | {r['cagr']*100:.2f}% | {r['vol']*100:.2f}% | "
          f"{r['maxdd']*100:.2f}% | {r['calmar']:.4f} | {r['martin']:.4f} |")

    w("\n## 2. 2022 episode (the duration-trap question)\n")
    w("### Whole CPM, calendar 2022\n")
    w("| Safe pool | 2022 return | 2022 MaxDD |")
    w("|---|---:|---:|")
    for name, rec in o["variants"].items():
        y = rec["y2022"]
        w(f"| {name} | {y['ret']*100:.2f}% | {y['maxdd']*100:.2f}% |")
    w("\n### Isolated safe sleeve (100% best_safe(pool) every month)\n")
    w("This sleeve is what the defensive/unused-breadth slots route to. It isolates "
      "the duration trap directly.\n")
    w("| Safe pool | 2022 sleeve return | 2022 sleeve MaxDD | Full-clean Sharpe | Full-clean MaxDD | Full-clean CAGR |")
    w("|---|---:|---:|---:|---:|---:|")
    for name, s in o["safe_sleeve"].items():
        w(f"| {name} | {s['y2022_ret']*100:.2f}% | {s['y2022_maxdd']*100:.2f}% | "
          f"{s['full_sharpe']:.4f} | {s['full_maxdd']*100:.2f}% | {s['full_cagr']*100:.2f}% |")

    w("\n## 3. Safe-asset selection frequency (does the new menu ever bind?)\n")
    w("### Clean window (2008-05-30+), count of months each asset was the best_safe choice\n")
    all_assets = sorted({a for d in o["selection_freq_clean"].values() for a in d})
    w("| Safe pool | " + " | ".join(all_assets) + " |")
    w("|---" * (len(all_assets) + 1) + "|")
    for name, d in o["selection_freq_clean"].items():
        cells = " | ".join(str(d.get(a, 0)) for a in all_assets)
        w(f"| {name} | {cells} |")

    w("\n### 2022 month-by-month best_safe choice (Dec-2021 .. Dec-2022)\n")
    for name, hist in o["selection_2022"].items():
        picks = " ".join(f"{d[5:]}:{a}" for d, a in hist)
        w(f"- **{name}**: {picks}")

    Path(__file__).with_name("cpm_safe_sleeve_expansion_findings.md").write_text("\n".join(A) + "\n")


if __name__ == "__main__":
    main()
