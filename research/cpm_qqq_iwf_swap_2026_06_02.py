# -*- coding: utf-8 -*-
"""ANALYST (read-only re production; NO prod/memo/docs touched; NO commit).

QUESTION: Swap QQQ -> IWF in the CPM-8 universe under the FULL CPM mechanism
(R1 M1: vol-adj Faber ranker + min-var 3-of-4, TIP-only canary, top-4,
equal-weight, breadth-scaled partial-safe, best-of {SHV,IEF} safe).

Single-asset check: does a PURER growth factor tilt (IWF = iShares Russell 1000
Growth) vs QQQ (Nasdaq-100 = tech/sector-concentrated index that merely behaves
growth-like) change CPM materially?

This is NOT a grid search -- ONE swap, full metrics, vs current CPM-8.

Universes:
  CPM-8 (current) = QQQ,  SPHQ, EFA, EEM, VNQ, GLD, TLT, DBC   (anchor 1.255673)
  CPM-8 (IWF swap)= IWF,  SPHQ, EFA, EEM, VNQ, GLD, TLT, DBC

GATE (must pass; CLEAN, mooex/T+1 MOO, both-252, 10bps):
  full CPM-8 = 1.255673 (+/-5e-4)

Mechanism = byte-identical cpm_mech_wf reused from
research/cpm_mech_2swap_univ_2026_06_02.py (CPM R1 M1, universe-parametric).

DATA: IWF absent from frozen panel -> fetched via yfinance auto_adjust (same
adjusted-close convention as the stitched panel) + OHLC into /tmp/cpm_open_cache
for exact mooex. IWF inception 2000-05-26 -> CLEAN (2008+) fully covered; EXT
(1999-03-10 start) has ~14mo pre-inception gap where IWF is simply unselectable
(mechanism handles missing assets). PIT caveat noted.

DISCIPLINE: point-estimates only (bootstrap skipped per scope); HIGH overfit
caution (single swap, single in-sample window); PIT/cached-data caveat; CPM
prod UNCHANGED (exploratory). Also report QQQ/IWF correlation + how often the
held basket actually differs between the two universes (effect size).
"""
import sys
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from cpm_live import (  # noqa: E402
    load_panel, perf_metrics, _fetch_cached_adjusted_close,
    DEFAULT_CASH, COST_BPS_PER_SIDE, CORR_LOOKBACK_DAYS,
)
import exec_lag_moo_validation_2026_05_30 as H  # noqa: E402
from research.cpm_mech_2swap_univ_2026_06_02 import (  # noqa: E402
    cpm_mech_wf, ann_turnover, CONV, TOP_K,
)
from research.cpm_bootstrap_multimetric import (  # noqa: E402
    _sortino_ann, _cvar_ratio_ann,
)

CPM8_CURRENT = ["QQQ", "SPHQ", "EFA", "EEM", "VNQ", "GLD", "TLT", "DBC"]
CPM8_IWF = ["IWF", "SPHQ", "EFA", "EEM", "VNQ", "GLD", "TLT", "DBC"]

FULL_CPM_ANCHOR = 1.255673  # CLEAN, config 111


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


def run_series(close, daily, intraday, overnight, universe, start, end):
    wf = lambda sd: cpm_mech_wf(close, sd, universe)
    s, _ = H._segment_returns_conv(close, daily, wf, start, end, CONV,
                                   COST_BPS_PER_SIDE, intraday, overnight)
    return s


def selection_divergence(close, start, end):
    """At each monthly rebal in [start,end], compute the held basket (set of
    tickers with weight>0) for both universes; measure how often baskets differ
    and specifically QQQ-vs-IWF inclusion divergence."""
    monthly_idx = (pd.DataFrame({"x": 1}, index=close.index)
                   .groupby(pd.Grouper(freq="ME")).tail(1))
    sigs = monthly_idx.index[(monthly_idx.index >= start)
                             & (monthly_idx.index <= end)].tolist()
    n = 0
    basket_diff = 0
    qqq_held = iwf_held = 0
    qqq_only = iwf_only = 0  # held growth slot in one universe but not other
    l1_sum = 0.0
    for sd in sigs:
        wq = cpm_mech_wf(close, sd, CPM8_CURRENT)
        wi = cpm_mech_wf(close, sd, CPM8_IWF)
        # restrict basket comparison to the COMMON assets + the growth slot,
        # since QQQ/IWF are the only differing universe members.
        setq = {k for k, v in wq.items() if v > 1e-9}
        seti = {k for k, v in wi.items() if v > 1e-9}
        # map growth slot to a common label for set-equality on the rest
        rq = (setq - {"QQQ"}) | ({"GROWTH"} if "QQQ" in setq else set())
        ri = (seti - {"IWF"}) | ({"GROWTH"} if "IWF" in seti else set())
        if rq != ri:
            basket_diff += 1
        q_in = "QQQ" in setq
        i_in = "IWF" in seti
        qqq_held += int(q_in)
        iwf_held += int(i_in)
        if q_in and not i_in:
            qqq_only += 1
        if i_in and not q_in:
            iwf_only += 1
        # L1 weight distance treating QQQ/IWF as same slot
        keys = (set(wq) | set(wi)) - {"QQQ", "IWF"}
        l1 = abs(wq.get("QQQ", 0.0) - wi.get("IWF", 0.0))
        l1 += sum(abs(wq.get(k, 0.0) - wi.get(k, 0.0)) for k in keys)
        l1_sum += l1
        n += 1
    return {
        "n_rebals": n,
        "basket_differs_count": basket_diff,
        "basket_differs_pct": 100.0 * basket_diff / n if n else float("nan"),
        "qqq_held_count": qqq_held,
        "iwf_held_count": iwf_held,
        "qqq_held_pct": 100.0 * qqq_held / n if n else float("nan"),
        "iwf_held_pct": 100.0 * iwf_held / n if n else float("nan"),
        "qqq_picked_not_iwf": qqq_only,
        "iwf_picked_not_qqq": iwf_only,
        "mean_L1_weight_dist_growthslot": l1_sum / n if n else float("nan"),
    }


def main():
    end = pd.Timestamp("2026-05-22")
    ext_start = pd.Timestamp("1999-03-10")
    clean_start = pd.Timestamp("2008-05-30")

    panel = load_panel(start=ext_start, end=end)
    end = min(end, panel.index[-1])
    cash = panel[DEFAULT_CASH].ffill().pct_change().dropna()

    # Fetch IWF adjusted close (same convention as panel) and join.
    iwf = _fetch_cached_adjusted_close("IWF", ext_start - pd.DateOffset(years=2),
                                       end, "/tmp/cpm_cache")
    if iwf.empty:
        raise SystemExit("FATAL: could not fetch IWF")
    panel = panel.join(iwf.rename("IWF"), how="left")
    iwf_first = panel["IWF"].first_valid_index()

    # OHLC: append IWF to the cache ticker list for exact mooex (file already
    # written by analyst pre-step). Fall back to cc-return if absent.
    if "IWF" not in H.OHLC_TICKERS and (H.OPEN_CACHE / "IWF.csv").exists():
        H.OHLC_TICKERS = list(H.OHLC_TICKERS) + ["IWF"]
    open_df, close_yf = H.load_open_close()
    intraday = (close_yf / open_df - 1.0).reindex(panel.index)
    overnight = (open_df / close_yf.shift(1) - 1.0).reindex(panel.index)

    cols = sorted(set(CPM8_CURRENT + CPM8_IWF + ["SHV", "IEF", "TIP"])
                  & set(panel.columns))
    close = panel[cols]
    daily = close.ffill().pct_change()
    for a in ("QQQ", "IWF"):
        if a not in close.columns:
            raise SystemExit(f"FATAL: {a} not in panel")

    windows = {"CLEAN": (clean_start, end), "EXT": (ext_start, end)}
    configs = {"CPM8_current_QQQ": CPM8_CURRENT, "CPM8_IWF_swap": CPM8_IWF}

    metrics, turnover = {}, {}
    for name, uni in configs.items():
        metrics[name], turnover[name] = {}, {}
        full_ser = run_series(close, daily, intraday, overnight, uni, ext_start, end)
        for wn, (ws, we) in windows.items():
            seg = full_ser.loc[(full_ser.index >= ws) & (full_ser.index <= we)]
            metrics[name][wn] = full_met(seg, cash)
            turnover[name][wn] = ann_turnover(close, uni, ws, we)
        c = metrics[name]["CLEAN"]
        print(f"  {name:18s} CLEAN sharpe={c['sharpe']:.4f} cagr={c['cagr']*100:.2f}% "
              f"maxdd={c['maxdd']*100:.2f}% calmar={c['calmar']:.4f}")

    cur_sh = metrics["CPM8_current_QQQ"]["CLEAN"]["sharpe"]
    gate = abs(cur_sh - FULL_CPM_ANCHOR) < 5e-4

    # QQQ/IWF correlation (daily returns), both windows
    q = daily["QQQ"]; iwfd = daily["IWF"]
    corr = {}
    for wn, (ws, we) in windows.items():
        m = (q.index >= ws) & (q.index <= we)
        pair = pd.concat([q[m], iwfd[m]], axis=1).dropna()
        corr[wn] = {
            "pearson_daily": float(pair.iloc[:, 0].corr(pair.iloc[:, 1])),
            "n_overlap_days": int(len(pair)),
        }

    # selection divergence (CLEAN + EXT)
    seldiv = {wn: selection_divergence(close, ws, we)
              for wn, (ws, we) in windows.items()}

    iwf_sh = metrics["CPM8_IWF_swap"]["CLEAN"]["sharpe"]

    out = {
        "meta": {
            "conv": CONV, "cost_bps": COST_BPS_PER_SIDE, "top_k": TOP_K,
            "lookback": CORR_LOOKBACK_DAYS,
            "mechanism": "CPM FIXED R1 M1 (vol-adj Faber rank + raw-Faber screen, min-var 3-of-4 at n_pos=4, TIP-only canary, top-4, equal-weight, best-of{SHV,IEF} safe, breadth-scaled partial-safe)",
            "clean": f"{clean_start.date()}..{end.date()}",
            "ext": f"{ext_start.date()}..{end.date()}",
            "cpm8_current": CPM8_CURRENT,
            "cpm8_iwf_swap": CPM8_IWF,
            "swap": "QQQ->IWF",
            "iwf_inception_in_panel": str(iwf_first.date()) if iwf_first is not None else None,
            "anchor_full_CPM8": FULL_CPM_ANCHOR,
            "caveat": "Single swap, single in-sample window -> HIGH overfit caution. IWF fetched live (yfinance auto_adjust), inception 2000-05-26 -> EXT has ~14mo pre-inception gap (IWF unselectable, mechanism falls to other assets/safe); CLEAN fully covered. Point-estimates only; bootstrap skipped per scope. CPM prod UNCHANGED.",
        },
        "gate_current_reproduces_full_CPM8": {
            "actual": cur_sh, "target": FULL_CPM_ANCHOR, "pass": bool(gate)},
        "metrics": metrics,
        "turnover": turnover,
        "qqq_iwf_correlation": corr,
        "selection_divergence": seldiv,
        "summary": {
            "d_sharpe_CLEAN": iwf_sh - cur_sh,
            "d_cagr_CLEAN": metrics["CPM8_IWF_swap"]["CLEAN"]["cagr"]
                            - metrics["CPM8_current_QQQ"]["CLEAN"]["cagr"],
            "d_maxdd_CLEAN": metrics["CPM8_IWF_swap"]["CLEAN"]["maxdd"]
                             - metrics["CPM8_current_QQQ"]["CLEAN"]["maxdd"],
            "d_sharpe_EXT": metrics["CPM8_IWF_swap"]["EXT"]["sharpe"]
                            - metrics["CPM8_current_QQQ"]["EXT"]["sharpe"],
        },
    }
    out_json = Path(__file__).with_suffix(".json")
    out_json.write_text(json.dumps(out, indent=2, default=float))
    print("\nGATE:", json.dumps(out["gate_current_reproduces_full_CPM8"], indent=2, default=float))
    print("CORR:", json.dumps(corr, indent=2, default=float))
    print("SELDIV CLEAN:", json.dumps(seldiv["CLEAN"], indent=2, default=float))
    print("SUMMARY:", json.dumps(out["summary"], indent=2, default=float))
    print("WROTE", out_json)
    return out


if __name__ == "__main__":
    main()
