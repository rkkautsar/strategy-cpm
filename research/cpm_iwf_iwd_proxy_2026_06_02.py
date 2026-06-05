# -*- coding: utf-8 -*-
"""ANALYST (read-only re production; NO prod/memo/docs touched; NO commit).

FOLLOW-UP to research/cpm_iwf_iwd_swap_2026_06_02.py.

PRIOR ISSUE: that swap test live-fetched IWF/IWD (inception 2000-05-26), so the
EXTENDED (EXT) window had a ~14mo pre-inception gap where IWF/IWD were simply
unselectable -> the EXT comparison was flagged UNTRUSTWORTHY. Raw EXT *hinted*
IWF+IWD slightly BETTER (1.2712 vs current 1.2549) but with the gap that was not
a valid head-to-head.

THIS RUN: PROXY IWF/IWD back through the full EXT window and re-run for a
trustworthy extended comparison.

PROXY METHOD (mirrors the project's existing pre-ETF stitch convention, e.g.
research/archive/stitch_kmlm.py and the data/*_stitched_daily.csv files):
  - IWF (Russell 1000 Growth ETF) <- VIGRX (Vanguard Growth Index, inception
    1992-10-30) for dates BEFORE IWF inception (2000-05-26); live IWF after.
  - IWD (Russell 1000 Value  ETF) <- VIVAX (Vanguard Value  Index, inception
    1992-10-30) for dates BEFORE IWD inception (2000-05-26); live IWD after.
  Return-continuous splice: scale the proxy so proxy[inception] == ETF[inception]
  (scale = ETF[inception] / PROXY[inception]); take scaled-proxy for dates <
  inception (the proxy's OWN daily return drives the boundary day) and live ETF
  for dates >= inception. This is the same return-continuous splice the repo uses
  for KMLM/QQQ/TLT/etc. (only difference: daily proxy here, not monthly).

APPLES-TO-APPLES with the BASELINE (QQQ+SPHQ):
  - The QQQ+SPHQ baseline in EXT is ITSELF proxied: QQQ <- NDX index proxy
    (data/qqq_stitched_daily.csv, 1985-10..1999-03) and SPHQ <- the long-history
    proxy panel column (data/proxy_adjusted_close_daily.csv, 1995+). So both
    sides of the comparison use pre-ETF proxies through EXT.
  - mooex (T+1 MOO) execution: on a rebalance day with no real OHLC the harness
    FALLS BACK to close-to-close (see exec_lag_moo_validation_2026_05_30
    _segment_returns_conv). Baseline SPHQ has no OHLC pre-2005 -> already uses
    cc-fallback in EXT. Proxied IWF/IWD have no OHLC pre-2000-05-26 -> use the
    SAME cc-fallback. Methodology matched.

GATES (must pass):
  - CLEAN full CPM-8 anchor = 1.255673 (+/-5e-4)
  - CLEAN CPM8 IWF+IWD swap should reproduce the prior 1.2417 (CLEAN unchanged;
    proxy only touches pre-2000 EXT, so CLEAN is byte-identical to the prior run).

DISCIPLINE: point-estimates only; HIGH overfit caution (single 2-ticker swap,
single in-sample window); proxy sources/dates stated; CPM prod UNCHANGED.
"""
import sys
import json
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from cpm_live import (  # noqa: E402
    load_panel, perf_metrics, _fetch_cached_adjusted_close,
    DEFAULT_CASH, COST_BPS_PER_SIDE, CORR_LOOKBACK_DAYS,
)
import research.exec_lag_moo_validation_2026_05_30 as H  # noqa: E402
from research.cpm_mech_2swap_univ_2026_06_02 import (  # noqa: E402
    cpm_mech_wf, ann_turnover, CONV, TOP_K,
)
from research.cpm_bootstrap_multimetric import (  # noqa: E402
    _sortino_ann, _cvar_ratio_ann,
)

CPM8_CURRENT = ["QQQ", "SPHQ", "EFA", "EEM", "VNQ", "GLD", "TLT", "DBC"]
CPM8_NEW = ["IWF", "IWD", "EFA", "EEM", "VNQ", "GLD", "TLT", "DBC"]

FULL_CPM_ANCHOR = 1.255673   # CLEAN, config 111 (QQQ+SPHQ)
PRIOR_SWAP_CLEAN = 1.2417    # CLEAN CPM8 IWF+IWD swap, prior live-fetch run

OLD_STYLE = {"QQQ", "SPHQ"}
NEW_STYLE = {"IWF", "IWD"}

PROXY_MAP = {"IWF": "VIGRX", "IWD": "VIVAX"}


def full_met(daily, cash):
    m = perf_metrics(daily, cash)
    x = daily.values
    return {
        "sharpe": m.get("sharpe"),
        "sortino": _sortino_ann(x, None),
        "cvar95_ratio": _cvar_ratio_ann(x, q=0.05),
        "calmar": m.get("calmar"),
        "martin": m.get("martin"),
        "maxdd": m.get("max_drawdown"),
        "cagr": m.get("cagr"),
        "vol": m.get("vol"),
    }


def build_stitched_proxy(etf, proxy_ticker, start, end):
    """Return-continuous stitch: scaled proxy pre-ETF-inception, live ETF after.

    scale = ETF[inception] / PROXY[inception]; proxy_scaled = proxy*scale used for
    dates < inception (proxy's own daily return drives the boundary day), live ETF
    for dates >= inception. Mirrors the repo's KMLM/QQQ/TLT stitch convention.
    """
    live = _fetch_cached_adjusted_close(etf, start, end, "/tmp/cpm_cache")
    if live.empty:
        raise SystemExit(f"FATAL: could not fetch live {etf}")
    inception = live.first_valid_index()

    prox = yf.download(proxy_ticker, start=start, end=end + pd.Timedelta(days=1),
                       auto_adjust=True, progress=False)["Close"]
    if isinstance(prox, pd.DataFrame):
        prox = prox.iloc[:, 0]
    prox = prox.dropna()
    prox.index = pd.to_datetime(prox.index).tz_localize(None)
    if inception not in prox.index:
        raise SystemExit(f"FATAL: {proxy_ticker} missing inception day {inception}")

    scale = float(live.loc[inception]) / float(prox.loc[inception])
    prox_scaled = prox * scale
    pre = prox_scaled[prox_scaled.index < inception]
    stitched = pd.concat([pre, live]).sort_index()
    stitched = stitched[~stitched.index.duplicated(keep="last")]
    info = {
        "etf": etf, "proxy": proxy_ticker,
        "inception": str(inception.date()),
        "proxy_first": str(prox.index[0].date()),
        "scale": scale,
        "pre_rows": int(len(pre)),
        "live_rows": int(len(live)),
        "stitched_first": str(stitched.index[0].date()),
        "stitched_last": str(stitched.index[-1].date()),
    }
    return stitched.rename(etf), inception, info


def run_series(close, daily, intraday, overnight, universe, start, end):
    wf = lambda sd: cpm_mech_wf(close, sd, universe)
    s, _ = H._segment_returns_conv(close, daily, wf, start, end, CONV,
                                   COST_BPS_PER_SIDE, intraday, overnight)
    return s


def main():
    end = pd.Timestamp("2026-05-22")
    ext_start = pd.Timestamp("1999-03-10")
    clean_start = pd.Timestamp("2008-05-30")

    panel = load_panel(start=ext_start, end=end)
    end = min(end, panel.index[-1])
    cash = panel[DEFAULT_CASH].ffill().pct_change().dropna()

    # Build PROXY-BACKED IWF/IWD and join (overwrite any prior live-only column).
    proxy_info = {}
    inception = {}
    for etf, prox in PROXY_MAP.items():
        s, inc, info = build_stitched_proxy(
            etf, prox, ext_start - pd.DateOffset(years=2), end)
        inception[etf] = inc
        proxy_info[etf] = info
        if etf in panel.columns:
            panel = panel.drop(columns=[etf])
        panel = panel.join(s, how="left")

    # OHLC: append IWF/IWD to cache list for exact mooex POST-inception (pre is
    # cc-fallback, identical to baseline SPHQ pre-2005).
    for t in ("IWF", "IWD"):
        if t not in H.OHLC_TICKERS and (H.OPEN_CACHE / f"{t}.csv").exists():
            H.OHLC_TICKERS = list(H.OHLC_TICKERS) + [t]
    open_df, close_yf = H.load_open_close()
    intraday = (close_yf / open_df - 1.0).reindex(panel.index)
    overnight = (open_df / close_yf.shift(1) - 1.0).reindex(panel.index)

    cols = sorted(set(CPM8_CURRENT + CPM8_NEW + ["SHV", "IEF", "TIP"])
                  & set(panel.columns))
    close = panel[cols]
    daily = close.ffill().pct_change()
    for a in ("QQQ", "SPHQ", "IWF", "IWD"):
        if a not in close.columns:
            raise SystemExit(f"FATAL: {a} not in panel")

    # Coverage report (does the proxy now fill the full EXT window?)
    cov = {}
    for a in ("QQQ", "SPHQ", "IWF", "IWD"):
        fv = close[a].first_valid_index()
        cov[a] = str(fv.date()) if fv is not None else None

    windows = {"CLEAN": (clean_start, end), "EXT": (ext_start, end)}
    configs = {"CPM8_current": CPM8_CURRENT, "CPM8_IWF_IWD_swap": CPM8_NEW}

    metrics, turnover = {}, {}
    for name, uni in configs.items():
        metrics[name], turnover[name] = {}, {}
        full_ser = run_series(close, daily, intraday, overnight, uni, ext_start, end)
        for wn, (ws, we) in windows.items():
            seg = full_ser.loc[(full_ser.index >= ws) & (full_ser.index <= we)]
            metrics[name][wn] = full_met(seg, cash)
            turnover[name][wn] = ann_turnover(close, uni, ws, we)
        c = metrics[name]["CLEAN"]
        e = metrics[name]["EXT"]
        print(f"  {name:20s} CLEAN sh={c['sharpe']:.4f} cagr={c['cagr']*100:.2f}% "
              f"mdd={c['maxdd']*100:.2f}% | EXT sh={e['sharpe']:.4f} "
              f"cagr={e['cagr']*100:.2f}% mdd={e['maxdd']*100:.2f}%")

    cur_sh = metrics["CPM8_current"]["CLEAN"]["sharpe"]
    new_sh = metrics["CPM8_IWF_IWD_swap"]["CLEAN"]["sharpe"]
    gate_anchor = abs(cur_sh - FULL_CPM_ANCHOR) < 5e-4
    gate_swap = abs(new_sh - PRIOR_SWAP_CLEAN) < 5e-4

    # correlations (daily returns), both windows
    def pair_corr(a, b, ws, we):
        m = (daily.index >= ws) & (daily.index <= we)
        p = pd.concat([daily[a][m], daily[b][m]], axis=1).dropna()
        return {"pearson_daily": float(p.iloc[:, 0].corr(p.iloc[:, 1])),
                "n_overlap_days": int(len(p))}
    corr = {}
    for wn, (ws, we) in windows.items():
        corr[wn] = {
            "corr_IWF_IWD": pair_corr("IWF", "IWD", ws, we),
            "corr_QQQ_SPHQ": pair_corr("QQQ", "SPHQ", ws, we),
        }

    out = {
        "meta": {
            "conv": CONV, "cost_bps": COST_BPS_PER_SIDE, "top_k": TOP_K,
            "lookback": CORR_LOOKBACK_DAYS,
            "mechanism": "CPM FIXED R1 M1 (vol-adj Faber rank + raw-Faber screen, min-var 3-of-4 at n_pos=4, TIP-only canary, top-4, equal-weight, best-of{SHV,IEF} safe, breadth-scaled partial-safe)",
            "clean": f"{clean_start.date()}..{end.date()}",
            "ext": f"{ext_start.date()}..{end.date()}",
            "cpm8_current": CPM8_CURRENT,
            "cpm8_iwf_iwd_swap": CPM8_NEW,
            "swap": "QQQ+SPHQ -> IWF+IWD (PROXY-BACKED EXT)",
            "proxy_map": PROXY_MAP,
            "proxy_info": proxy_info,
            "coverage_first_valid": cov,
            "anchor_full_CPM8": FULL_CPM_ANCHOR,
            "prior_swap_clean": PRIOR_SWAP_CLEAN,
            "caveat": (
                "IWF<-VIGRX, IWD<-VIVAX return-continuous stitch (proxy[inception]"
                " scaled to ETF[inception]); proxy daily from 1992-10-30, live ETFs"
                " from 2000-05-26. EXT now fully covered for the style pair. mooex"
                " uses cc-fallback for IWF/IWD pre-2000-05-26 (no OHLC), identical to"
                " baseline SPHQ pre-2005. Residual caveat: VIGRX/VIVAX are Russell-"
                "1000-Growth/Value PROXIES (not the exact index/ETF) for the pre-2000"
                " sub-window; minor style-construction drift possible. Single 2-ticker"
                " swap, single in-sample window -> HIGH overfit caution. Point-"
                "estimates only. CPM prod UNCHANGED."),
        },
        "gates": {
            "current_reproduces_full_CPM8": {
                "actual": cur_sh, "target": FULL_CPM_ANCHOR, "pass": bool(gate_anchor)},
            "swap_clean_reproduces_prior": {
                "actual": new_sh, "target": PRIOR_SWAP_CLEAN, "pass": bool(gate_swap)},
        },
        "metrics": metrics,
        "turnover": turnover,
        "correlation": corr,
        "summary": {
            "d_sharpe_CLEAN": new_sh - cur_sh,
            "d_cagr_CLEAN": metrics["CPM8_IWF_IWD_swap"]["CLEAN"]["cagr"]
                            - metrics["CPM8_current"]["CLEAN"]["cagr"],
            "d_maxdd_CLEAN": metrics["CPM8_IWF_IWD_swap"]["CLEAN"]["maxdd"]
                             - metrics["CPM8_current"]["CLEAN"]["maxdd"],
            "d_calmar_CLEAN": metrics["CPM8_IWF_IWD_swap"]["CLEAN"]["calmar"]
                              - metrics["CPM8_current"]["CLEAN"]["calmar"],
            "d_sharpe_EXT": metrics["CPM8_IWF_IWD_swap"]["EXT"]["sharpe"]
                            - metrics["CPM8_current"]["EXT"]["sharpe"],
            "d_cagr_EXT": metrics["CPM8_IWF_IWD_swap"]["EXT"]["cagr"]
                          - metrics["CPM8_current"]["EXT"]["cagr"],
            "d_maxdd_EXT": metrics["CPM8_IWF_IWD_swap"]["EXT"]["maxdd"]
                           - metrics["CPM8_current"]["EXT"]["maxdd"],
            "d_calmar_EXT": metrics["CPM8_IWF_IWD_swap"]["EXT"]["calmar"]
                            - metrics["CPM8_current"]["EXT"]["calmar"],
        },
    }
    out_json = Path(__file__).with_suffix(".json")
    out_json.write_text(json.dumps(out, indent=2, default=float))
    print("\nPROXY INFO:", json.dumps(proxy_info, indent=2, default=float))
    print("COVERAGE:", json.dumps(cov, indent=2, default=float))
    print("GATES:", json.dumps(out["gates"], indent=2, default=float))
    print("CORR:", json.dumps(corr, indent=2, default=float))
    print("SUMMARY:", json.dumps(out["summary"], indent=2, default=float))
    print("WROTE", out_json)
    return out


if __name__ == "__main__":
    main()
