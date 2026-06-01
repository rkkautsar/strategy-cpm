# -*- coding: utf-8 -*-
"""Analyst research (read-only re production; writes only research/; NO prod/memo
change; NO commit). OUT-OF-SAMPLE extension of the BULL 10y3m-inversion candidate.

Question
--------
The candidate BULL enhancement is "10y3m yield-curve inversion ADDED to the
rv_60d<rv_252d (rv60) vol gate". Its clean-window (2008+) edge looked
CONCENTRATED in COVID-2020 (n=1, overfit flag). Here we EXTEND the backtest over
T10Y3M's full FRED history (1982-01+, daily) to test whether the 10y3m overlay's
value is COVID-only or holds across multiple recessions/grinds, AND whether the
rv60 vol gate's grind-protection replicates across 1990/2001 too.

Three first-class rungs, every table, full 1982-2026 window:
  (a) HAA-Simple   = BULL trend-only (canary + SPY 13612U), NO vol gate.
  (b) BULL rv60    = trend + rv60 vol gate (current production).
  (c) BULL rv60+yc = trend + rv60 + 10y3m inversion ADD (candidate).

Marginals over the extended history:
  (b)-(a) = does the rv60 vol gate earn its keep net (grind protection)?
  (c)-(b) = does 10y3m add on top across >=3 independent recessions, or only COVID?

Data (daily -- correct frequency for the rv gate)
-------------------------------------------------
Equity SPY: repo proxy SPY (load_panel, 1995+) spliced backward with yfinance
  SPY auto_adjust TR (1993-1995) and ^GSPC price returns (pre-1993, NO dividends
  -- FLAG). rv_60d/rv_252d computed at DAILY frequency throughout.
Safe IEF (7-10y): repo IEF proxy (1991-10+) spliced backward with a synthetic
  10y constant-maturity total return from FRED DGS10 (carry + duration*-dyield,
  D=7.5). Cash SHV: repo SHV proxy (1991-10+) spliced backward with synthetic
  T-bill carry from FRED DTB3.
Canary TIP: repo TIP proxy (2000-06+) spliced backward with a SYNTHETIC,
  INFLATION-AWARE TIPS proxy = synthetic nominal 10y (IEF synth) + CPI principal
  accrual (FRED CPIAUCSL MoM, distributed daily). Real TIPS market began 1997;
  repo proxy starts 2000-06, so 1982-2000 uses the synthetic. FLAG. Canary is a
  secondary gate here.
Gate data: FRED T10Y3M (1982-01-04+, daily), cached research/_macro_cache/.

Conventions: production T+1 close-to-close execution
(bull_spy_live.run_bull_spy_backtest, 10 bps/side), gates monkeypatched into
bull_spy_live._vol_gate_ok. This is consistent across the full 1982-2026 window
(real-open MOO data only exists 1999+, so we use the production close-to-close
backtester for apples-to-apples over the extended history; numbers differ
slightly from the mooex clean-window study, noted).

Writes research/bull_10y3m_extended_1982_findings.md (+ .json).
"""
from __future__ import annotations
import sys, json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from cpm_live import load_panel, perf_metrics, COST_BPS_PER_SIDE
import bull_spy_live

CACHE = Path(__file__).resolve().parent / "_macro_cache"
CACHE.mkdir(exist_ok=True)

FULL_START = pd.Timestamp("1982-01-31")   # T10Y3M live 1982-01-04
CLEAN_START = pd.Timestamp("2008-05-30")  # continuity sub-window
END = pd.Timestamp("2026-05-22")

# 10y constant-maturity modified duration approx for synth bond TR.
IEF_DURATION = 7.5

# Episodes: (label, lo, hi). DD = max drawdown within window; ret = total return.
EPISODES = [
    ("1990 recession",   "1990-06-01", "1991-03-31"),
    ("2000-02 dot-com",  "2000-03-01", "2002-10-31"),
    ("2008-09 GFC",      "2007-10-01", "2009-06-30"),
    ("2011 euro/dgrade", "2011-05-01", "2011-12-31"),
    ("2015 china/oil",   "2015-07-01", "2016-02-29"),
    ("2018-Q4",          "2018-10-01", "2018-12-31"),
    ("2020-COVID",       "2020-02-01", "2020-06-30"),
    ("2022 grind",       "2022-01-01", "2022-12-31"),
]


# ----------------------- data fetch -----------------------
def _fred(series):
    p = CACHE / f"{series}.csv"
    if p.exists():
        s = pd.read_csv(p, parse_dates=[0], index_col=0).iloc[:, 0]
        s.index = pd.to_datetime(s.index)
        return s.dropna()
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"
    d = pd.read_csv(url, parse_dates=[0], index_col=0)
    d = d[d[series] != "."].astype(float)
    s = d[series].dropna()
    s.to_frame(series).to_csv(p)
    return s


def _yf(ticker, fname, start="1957-01-01"):
    p = CACHE / fname
    if p.exists():
        s = pd.read_csv(p, parse_dates=[0], index_col=0).iloc[:, 0]
        s.index = pd.to_datetime(s.index)
        return s.dropna()
    import yfinance as yf
    d = yf.download(ticker, start=start, progress=False, auto_adjust=True)
    s = d["Close"]
    if isinstance(s, pd.DataFrame):
        s = s.iloc[:, 0]
    s = s.dropna()
    s.to_frame("close").to_csv(p)
    return s


def _level_from_returns(ret: pd.Series, base=100.0) -> pd.Series:
    return base * (1.0 + ret.fillna(0.0)).cumprod()


def build_extended_panel():
    """Return (panel, prov) where panel has SPY/SHV/IEF/TIP daily levels 1982+.
    Real repo proxy where available; synthetic/spliced backward."""
    base = load_panel(start=pd.Timestamp("1980-01-01"), end=END)
    idx_repo = base.index

    # macro / fred
    dgs10 = _fred("DGS10")
    dtb3 = _fred("DTB3")
    cpi = _fred("CPIAUCSL")
    t10y3m = _fred("T10Y3M")
    gspc = _yf("^GSPC", "GSPC.csv")
    spy_yf = _yf("SPY", "SPY_yf.csv", start="1993-01-01")

    # union daily index: business days 1982..END unioned with repo index
    bidx = pd.bdate_range(FULL_START - pd.DateOffset(months=18), END)
    full_idx = bidx.union(idx_repo)
    full_idx = full_idx[(full_idx >= pd.Timestamp("1980-06-01")) & (full_idx <= END)]

    # ---- equity SPY return splice ----
    spy_repo_ret = base["SPY"].reindex(full_idx).ffill(limit=3).pct_change()
    spy_yf_ret = spy_yf.reindex(full_idx).ffill(limit=3).pct_change()
    gspc_ret = gspc.reindex(full_idx).ffill(limit=3).pct_change()
    spy_ret = spy_repo_ret.copy()
    spy_ret = spy_ret.where(spy_ret.notna(), spy_yf_ret)
    spy_ret = spy_ret.where(spy_ret.notna(), gspc_ret)
    SPY = _level_from_returns(spy_ret)

    # ---- synthetic nominal 10y TR from DGS10 (carry + duration return) ----
    y10 = dgs10.reindex(full_idx).ffill()
    dy10 = y10.diff() / 100.0           # yield change in decimal
    carry10 = (y10.shift(1) / 100.0) / 252.0
    ief_synth_ret = carry10 - IEF_DURATION * dy10

    # ---- cash from DTB3 ----
    y3m = dtb3.reindex(full_idx).ffill()
    cash_synth_ret = (y3m.shift(1) / 100.0) / 252.0

    # ---- CPI daily inflation (MoM distributed) ----
    cpi_daily = cpi.reindex(full_idx).interpolate(method="time").ffill().bfill()
    cpi_infl = cpi_daily.pct_change().clip(-0.02, 0.02)  # guard interp artefacts

    # ---- synthetic inflation-aware TIP = nominal10 + cpi accrual ----
    tip_synth_ret = ief_synth_ret + cpi_infl

    # ---- splice safe/canary: repo proxy where available else synth ----
    ief_repo_ret = base["IEF"].reindex(full_idx).ffill(limit=3).pct_change()
    IEF_ret = ief_repo_ret.where(ief_repo_ret.notna(), ief_synth_ret)
    IEF = _level_from_returns(IEF_ret)

    shv_repo_ret = base["SHV"].reindex(full_idx).ffill(limit=3).pct_change()
    SHV_ret = shv_repo_ret.where(shv_repo_ret.notna(), cash_synth_ret)
    SHV = _level_from_returns(SHV_ret)

    tip_repo_ret = base["TIP"].reindex(full_idx).ffill(limit=3).pct_change()
    TIP_ret = tip_repo_ret.where(tip_repo_ret.notna(), tip_synth_ret)
    TIP = _level_from_returns(TIP_ret)

    panel = pd.DataFrame({"SPY": SPY, "SHV": SHV, "IEF": IEF, "TIP": TIP}).sort_index()
    panel = panel.dropna(how="all")

    prov = {
        "SPY_repo_start": str(base["SPY"].dropna().index[0].date()),
        "SPY_yf_start": str(spy_yf.index[0].date()),
        "GSPC_start": str(gspc.index[0].date()),
        "IEF_repo_start": str(base["IEF"].dropna().index[0].date()),
        "SHV_repo_start": str(base["SHV"].dropna().index[0].date()),
        "TIP_repo_start": str(base["TIP"].dropna().index[0].date()),
        "DGS10": [str(dgs10.index[0].date()), str(dgs10.index[-1].date())],
        "DTB3": [str(dtb3.index[0].date()), str(dtb3.index[-1].date())],
        "CPIAUCSL": [str(cpi.index[0].date()), str(cpi.index[-1].date())],
        "T10Y3M": [str(t10y3m.index[0].date()), str(t10y3m.index[-1].date())],
        "panel_range": [str(panel.index[0].date()), str(panel.index[-1].date())],
    }
    return panel, t10y3m, prov


# ----------------------- gates -----------------------
def gate_always_on(daily_spy, sig_d):
    return True, {"haa": True}


def gate_rv60(daily_spy, sig_d):
    sub = daily_spy.loc[:sig_d].pct_change().dropna()
    if len(sub) < 252:
        return True, {"warmup": True}
    rv60 = float(sub.tail(60).std() * np.sqrt(252))
    rv252 = float(sub.tail(252).std() * np.sqrt(252))
    return (rv60 < rv252), {"rv60": rv60, "rv252": rv252}


def make_gate_rv60_yc(spread):
    def g(daily_spy, sig_d):
        rv_ok, d = gate_rv60(daily_spy, sig_d)
        s = spread.loc[:sig_d]
        if len(s) == 0:
            yc_ok = True  # warmup risk-on
            d2 = {"yc_warmup": True}
        else:
            sv = float(s.iloc[-1])
            yc_ok = sv >= 0.0
            d2 = {"spread": sv, "not_inverted": yc_ok}
        return (rv_ok and yc_ok), {**d, **d2}
    return g


# ----------------------- backtest + metrics -----------------------
def run_bull(panel, gate, start, end):
    orig = bull_spy_live._vol_gate_ok
    bull_spy_live._vol_gate_ok = gate
    try:
        return bull_spy_live.run_bull_spy_backtest(panel, start, end,
                                                   cost_bps=COST_BPS_PER_SIDE)
    finally:
        bull_spy_live._vol_gate_ok = orig


def regime_stats(panel, gate, start, end):
    """months, safe months, flips, turnover/yr under a gate."""
    orig = bull_spy_live._vol_gate_ok
    bull_spy_live._vol_gate_ok = gate
    try:
        midx = (pd.DataFrame({"x": 1}, index=panel.index)
                .groupby(pd.Grouper(freq="ME")).tail(1))
        sigs = midx.index[(midx.index >= start) & (midx.index <= end)].tolist()
        regimes = []
        for sd in sigs:
            w, lab, _ = bull_spy_live.compute_bull_spy_weights(panel, sd, panel["SPY"])
            regimes.append("SPY" if "SPY" in w else "SAFE")
    finally:
        bull_spy_live._vol_gate_ok = orig
    n = len(regimes)
    n_safe = sum(1 for r in regimes if r == "SAFE")
    flips = sum(1 for i in range(1, n) if regimes[i] != regimes[i - 1])
    yrs = (sigs[-1] - sigs[0]).days / 365.25 if n > 1 else 1.0
    return n, n_safe, flips, (flips / yrs if yrs > 0 else float("nan"))


def met(s, cash):
    m = perf_metrics(s, cash)
    return {"sharpe": m.get("sharpe"), "cagr": m.get("cagr"), "vol": m.get("vol"),
            "maxdd": m.get("max_drawdown"), "calmar": m.get("calmar")}


def dd_in(s, lo, hi):
    sub = s.loc[(s.index >= pd.Timestamp(lo)) & (s.index <= pd.Timestamp(hi))]
    if len(sub) < 3:
        return float("nan")
    eq = (1.0 + sub).cumprod()
    return float((eq / eq.cummax() - 1.0).min())


def ret_in(s, lo, hi):
    sub = s.loc[(s.index >= pd.Timestamp(lo)) & (s.index <= pd.Timestamp(hi))]
    return float((1.0 + sub).prod() - 1.0) if len(sub) else float("nan")


def main():
    panel, t10y3m, prov = build_extended_panel()
    end = min(END, panel.index[-1])
    cash = panel["SHV"].ffill().pct_change().dropna()
    print("panel", prov["panel_range"], "rows", len(panel))

    gates = {
        "a_HAA_simple (trend only)":   gate_always_on,
        "b_BULL rv60 (prod)":          gate_rv60,
        "c_BULL rv60+10y3m (cand)":    make_gate_rv60_yc(t10y3m),
    }

    series = {}
    rows = {}
    for name, gate in gates.items():
        s_full = run_bull(panel, gate, FULL_START, end)
        series[name] = s_full
        n, ns, fl, tpy = regime_stats(panel, gate, FULL_START, end)
        rec = {
            "full": met(s_full.loc[FULL_START:end], cash),
            "clean": met(s_full.loc[CLEAN_START:end], cash),
            "months": n, "safe_months": ns, "safe_frac": ns / n if n else float("nan"),
            "flips": fl, "turnover_per_yr": tpy,
            "episodes": {},
        }
        for lbl, lo, hi in EPISODES:
            rec["episodes"][lbl] = {"dd": dd_in(s_full, lo, hi), "ret": ret_in(s_full, lo, hi)}
        rows[name] = rec
        f = rec["full"]
        print(f"{name:32s} FULL sh={f['sharpe']:.3f} cal={f['calmar']:.2f} "
              f"dd={f['maxdd']*100:6.2f}% cagr={f['cagr']*100:.2f}% safe={rec['safe_frac']*100:.0f}%")

    # marginals per episode
    A = "a_HAA_simple (trend only)"
    B = "b_BULL rv60 (prod)"
    C = "c_BULL rv60+10y3m (cand)"
    marg = {"b_minus_a": {}, "c_minus_b": {}}
    for lbl, _, _ in EPISODES:
        ea, eb, ec = rows[A]["episodes"][lbl], rows[B]["episodes"][lbl], rows[C]["episodes"][lbl]
        marg["b_minus_a"][lbl] = {
            "d_ret_pp": (eb["ret"] - ea["ret"]) * 100,
            "d_dd_pp": (abs(eb["dd"]) - abs(ea["dd"])) * 100,
        }
        marg["c_minus_b"][lbl] = {
            "d_ret_pp": (ec["ret"] - eb["ret"]) * 100,
            "d_dd_pp": (abs(ec["dd"]) - abs(eb["dd"])) * 100,
        }

    out = {
        "meta": {
            "window_full": [str(FULL_START.date()), str(end.date())],
            "window_clean": [str(CLEAN_START.date()), str(end.date())],
            "cost_bps": COST_BPS_PER_SIDE,
            "convention": "T+1 close-to-close (production run_bull_spy_backtest), gates monkeypatched",
            "ief_duration": IEF_DURATION,
            "provenance": prov,
            "sources": {
                "equity": "repo proxy SPY (load_panel 1995+) <- yfinance SPY TR (1993-95) <- ^GSPC price (pre-1993, NO div)",
                "safe_IEF": "repo IEF proxy (1991-10+) <- synth 10y CMT TR from FRED DGS10 (D=7.5)",
                "cash_SHV": "repo SHV proxy (1991-10+) <- synth T-bill carry from FRED DTB3",
                "canary_TIP": "repo TIP proxy (2000-06+) <- synth inflation-aware TIPS = synth nominal10 + CPI accrual (FRED CPIAUCSL); real TIPS mkt 1997",
                "gate_T10Y3M": "FRED T10Y3M daily 1982-01-04+",
            },
        },
        "rungs": rows,
        "marginals_per_episode": marg,
        "episodes_def": [{"label": l, "lo": lo, "hi": hi} for l, lo, hi in EPISODES],
    }
    Path(__file__).with_suffix(".json").write_text(json.dumps(out, indent=2, default=float))
    write_md(out)
    print("DONE -> research/bull_10y3m_extended_1982_findings.md")
    return out


def write_md(o):
    L = []; A = L.append
    m = o["meta"]; R = o["rungs"]; eps = [e["label"] for e in o["episodes_def"]]
    order = ["a_HAA_simple (trend only)", "b_BULL rv60 (prod)", "c_BULL rv60+10y3m (cand)"]

    def pct(x):
        return f"{x*100:.2f}%" if x is not None and np.isfinite(x) else "n/a"

    def f4(x):
        return f"{x:.4f}" if x is not None and np.isfinite(x) else "n/a"

    def sp(x):  # signed pp
        return f"{x:+.2f}" if x is not None and np.isfinite(x) else "n/a"

    A("# BULL 10y3m-inversion + rv60 -- extended OOS over T10Y3M full history (1982-2026)\n")
    A("Role: analyst (read-only re production; writes only research/; no production/memo files "
      "changed; no commit). Harness `research/bull_10y3m_extended_1982.py`.\n")
    A("**Question:** the candidate BULL enhancement is 10y3m yield-curve inversion ADDED to the "
      "rv_60d<rv_252d (rv60) vol gate. Its clean-window (2008+) edge looked CONCENTRATED in "
      "COVID-2020 (n=1). Extend over T10Y3M's full FRED history (1982-01+, daily): is the 10y3m "
      "overlay's value COVID-only or multi-crisis robust? And does the rv60 vol gate's "
      "grind-protection replicate across 1990/2001 at the correct DAILY frequency over more "
      "history?\n")
    A("**Three first-class rungs** (every table): **(a) HAA-Simple** = BULL trend-only (canary + "
      "SPY 13612U), NO vol gate; **(b) BULL rv60** = trend + rv60 vol gate (current production); "
      "**(c) BULL rv60+10y3m** = trend + rv60 + 10y3m inversion ADD (candidate). Marginals: "
      "(b)-(a) = does rv60 earn its keep; (c)-(b) = does 10y3m add on top.\n")
    A(f"**Convention:** {m['convention']}, {m['cost_bps']} bps/side. Full window "
      f"{m['window_full'][0]}..{m['window_full'][1]}; continuity sub-window (clean) "
      f"{m['window_clean'][0]}..{m['window_clean'][1]}. BULL sleeve only (no CPM blend; this study "
      "isolates the gate). 10y3m gate: risk-on when T10Y3M >= 0 (not inverted), contemporaneous "
      "(L0, the cleanest spec from the prior study); warmup defaults risk-on.\n")

    A("**Data sources + provenance:**\n")
    A("| Leg | Source chain |")
    A("|---|---|")
    for k, v in m["sources"].items():
        A(f"| {k} | {v} |")
    A("")
    pr = m["provenance"]
    A(f"FRED windows: DGS10 {pr['DGS10'][0]}..{pr['DGS10'][1]}, DTB3 {pr['DTB3'][0]}..{pr['DTB3'][1]}, "
      f"CPIAUCSL {pr['CPIAUCSL'][0]}..{pr['CPIAUCSL'][1]}, T10Y3M {pr['T10Y3M'][0]}..{pr['T10Y3M'][1]}. "
      f"Repo-proxy real-data starts: SPY {pr['SPY_repo_start']}, IEF {pr['IEF_repo_start']}, "
      f"SHV {pr['SHV_repo_start']}, TIP {pr['TIP_repo_start']}. Panel {pr['panel_range'][0]}.."
      f"{pr['panel_range'][1]}. Synth 10y modified duration D={m['ief_duration']}.\n")

    # 1. full-window headline
    A("## 1. Full-window 1982-2026 -- headline metrics (BULL sleeve)\n")
    A("| Rung | Sharpe | CAGR | Vol | MaxDD | Calmar | Safe mo % | Turnover/yr |")
    A("|---|---:|---:|---:|---:|---:|---:|---:|")
    for name in order:
        r = R[name]; b = r["full"]
        A(f"| {name} | {f4(b['sharpe'])} | {pct(b['cagr'])} | {pct(b['vol'])} | {pct(b['maxdd'])} | "
          f"{f4(b['calmar'])} | {r['safe_frac']*100:.0f}% | {r['turnover_per_yr']:.2f} |")
    A("")
    A("Marginals (full window): "
      f"(b)-(a) Sharpe {sp((R[order[1]]['full']['sharpe']-R[order[0]]['full']['sharpe']))}, "
      f"Calmar {sp((R[order[1]]['full']['calmar']-R[order[0]]['full']['calmar']))}, "
      f"MaxDD {sp((abs(R[order[1]]['full']['maxdd'])-abs(R[order[0]]['full']['maxdd']))*100)}pp; "
      f"(c)-(b) Sharpe {sp((R[order[2]]['full']['sharpe']-R[order[1]]['full']['sharpe']))}, "
      f"Calmar {sp((R[order[2]]['full']['calmar']-R[order[1]]['full']['calmar']))}, "
      f"MaxDD {sp((abs(R[order[2]]['full']['maxdd'])-abs(R[order[1]]['full']['maxdd']))*100)}pp.\n")

    # 2. clean continuity
    A("## 2. Continuity check -- clean sub-window 2008-05-30..\n")
    A("Sanity vs prior mooex study (numbers differ slightly: this study uses production "
      "close-to-close T+1, the prior used mooex real-open T+1).\n")
    A("| Rung | Sharpe | CAGR | Vol | MaxDD | Calmar |")
    A("|---|---:|---:|---:|---:|---:|")
    for name in order:
        b = R[name]["clean"]
        A(f"| {name} | {f4(b['sharpe'])} | {pct(b['cagr'])} | {pct(b['vol'])} | {pct(b['maxdd'])} | "
          f"{f4(b['calmar'])} |")
    A("")

    # 3. per-episode DD
    A("## 3. Per-episode max drawdown (BULL sleeve)\n")
    A("| Episode | (a) HAA | (b) rv60 | (c) rv60+yc |")
    A("|---|---:|---:|---:|")
    for lbl in eps:
        A(f"| {lbl} | {pct(R[order[0]]['episodes'][lbl]['dd'])} | "
          f"{pct(R[order[1]]['episodes'][lbl]['dd'])} | {pct(R[order[2]]['episodes'][lbl]['dd'])} |")
    A("")

    # 4. per-episode return
    A("## 4. Per-episode total return (BULL sleeve)\n")
    A("| Episode | (a) HAA | (b) rv60 | (c) rv60+yc |")
    A("|---|---:|---:|---:|")
    for lbl in eps:
        A(f"| {lbl} | {pct(R[order[0]]['episodes'][lbl]['ret'])} | "
          f"{pct(R[order[1]]['episodes'][lbl]['ret'])} | {pct(R[order[2]]['episodes'][lbl]['ret'])} |")
    A("")

    # 5. marginals
    mb = o["marginals_per_episode"]["b_minus_a"]
    mc = o["marginals_per_episode"]["c_minus_b"]
    A("## 5. Marginal effects per episode (return pp / drawdown pp)\n")
    A("(b)-(a) = rv60 vol gate contribution; (c)-(b) = 10y3m overlay contribution. "
      "d_ret +ve = gate added return; d_dd -ve = gate made drawdown shallower (better).\n")
    A("| Episode | (b)-(a) d_ret | (b)-(a) d_dd | (c)-(b) d_ret | (c)-(b) d_dd |")
    A("|---|---:|---:|---:|---:|")
    for lbl in eps:
        A(f"| {lbl} | {sp(mb[lbl]['d_ret_pp'])} | {sp(mb[lbl]['d_dd_pp'])} | "
          f"{sp(mc[lbl]['d_ret_pp'])} | {sp(mc[lbl]['d_dd_pp'])} |")
    A("")

    A("## 6. Verdict\n")
    A("_Filled after run inspection -- see end of file._\n")

    Path(ROOT / "research" / "bull_10y3m_extended_1982_findings.md").write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
