# -*- coding: utf-8 -*-
"""ANALYST (read-only re production; NO prod/memo/docs touched; NO commit).

QUESTION: Swap the CPM-8 US-equity PAIR QQQ + SPHQ (Nasdaq-tech + S&P quality,
both growth/quality-leaning) -> IWF + IWD (Russell 1000 Growth + Russell 1000
Value), a cleaner growth/value STYLE pair spanning the style axis, under the
FULL CPM mechanism (R1 M1: vol-adj Faber ranker + min-var 3-of-4, TIP-only
canary, top-4, equal-weight, breadth-scaled partial-safe, best-of{SHV,IEF} safe).

HYPOTHESIS: IWF (growth) + IWD (value) are more ORTHOGONAL than QQQ + SPHQ
(both growth/quality) -> the pair spans US-equity styles better, letting the
momentum ranker rotate growth<->value with the regime (more diversification,
potentially better DD). Risk: gives up QQQ concentrated tech-beta; IWD value
drag during 2008-2021 growth-led era.

This is NOT a grid search -- ONE swap (2 tickers), full metrics, vs CPM-8.

Universes:
  CPM-8 (current) = QQQ, SPHQ, EFA, EEM, VNQ, GLD, TLT, DBC   (anchor 1.255673)
  CPM-8 (IWF+IWD) = IWF, IWD,  EFA, EEM, VNQ, GLD, TLT, DBC

GATE (must pass; CLEAN, mooex/T+1 MOO, both-252, 10bps):
  full CPM-8 = 1.255673 (+/-5e-4)

Mechanism = byte-identical cpm_mech_wf reused from
research/cpm_mech_2swap_univ_2026_06_02.py (CPM R1 M1, universe-parametric).

DATA: IWF, IWD absent from frozen panel -> fetched via yfinance auto_adjust
(same adjusted-close convention as the stitched panel) + OHLC into
/tmp/cpm_open_cache for exact mooex. Both inception 2000-05-26 -> CLEAN (2008+)
fully covered; EXT (1999-03-10 start) has ~14mo pre-inception gap where IWF/IWD
are simply unselectable (mechanism handles missing assets). PIT caveat noted ->
trust CLEAN.

DISCIPLINE: point-estimates only (bootstrap skipped per scope); HIGH overfit
caution (single swap, single in-sample window); PIT/cached-data caveat; CPM
prod UNCHANGED (exploratory). Reports corr(IWF,IWD) vs corr(QQQ,SPHQ),
style-rotation behavior (IWF vs IWD months held), selection divergence.
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
import research.exec_lag_moo_validation_2026_05_30 as H  # noqa: E402
from research.cpm_mech_2swap_univ_2026_06_02 import (  # noqa: E402
    cpm_mech_wf, ann_turnover, CONV, TOP_K,
)
from research.cpm_bootstrap_multimetric import (  # noqa: E402
    _sortino_ann, _cvar_ratio_ann,
)

CPM8_CURRENT = ["QQQ", "SPHQ", "EFA", "EEM", "VNQ", "GLD", "TLT", "DBC"]
CPM8_NEW = ["IWF", "IWD", "EFA", "EEM", "VNQ", "GLD", "TLT", "DBC"]

FULL_CPM_ANCHOR = 1.255673  # CLEAN, config 111

# style-slot mapping for divergence (the only differing universe members)
OLD_STYLE = {"QQQ", "SPHQ"}
NEW_STYLE = {"IWF", "IWD"}


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


def style_rotation(close, universe, style_set, start, end):
    """At each monthly rebal, record which style-slot tickers are held (w>0).
    Tracks rotation: months holding each style asset, both, neither."""
    monthly_idx = (pd.DataFrame({"x": 1}, index=close.index)
                   .groupby(pd.Grouper(freq="ME")).tail(1))
    sigs = monthly_idx.index[(monthly_idx.index >= start)
                             & (monthly_idx.index <= end)].tolist()
    sty = sorted(style_set)
    cnt = {t: 0 for t in sty}
    both = neither = 0
    seq = []
    n = 0
    prev_held = None
    switches = 0
    for sd in sigs:
        w = cpm_mech_wf(close, sd, universe)
        held = {t for t in sty if w.get(t, 0.0) > 1e-9}
        for t in held:
            cnt[t] += 1
        if len(held) == len(sty):
            both += 1
        if not held:
            neither += 1
        # rotation tracking: among the single-style-held months, did the held
        # style change vs the prior single-style month?
        if len(held) == 1:
            cur = next(iter(held))
            if prev_held is not None and cur != prev_held:
                switches += 1
            prev_held = cur
        seq.append(sorted(held))
        n += 1
    return {
        "n_rebals": n,
        "held_count": cnt,
        "held_pct": {t: 100.0 * cnt[t] / n if n else float("nan") for t in sty},
        "both_held_count": both,
        "neither_held_count": neither,
        "single_style_switches": switches,
        "seq": ["+".join(s) if s else "-" for s in seq],
    }


def selection_divergence(close, start, end):
    """At each monthly rebal in [start,end], compute held basket (set of
    tickers w>0) for both universes; measure how often the non-style basket
    differs and the style-slot inclusion divergence (collapse style assets to a
    common STYLE label so only genuine selection changes count)."""
    monthly_idx = (pd.DataFrame({"x": 1}, index=close.index)
                   .groupby(pd.Grouper(freq="ME")).tail(1))
    sigs = monthly_idx.index[(monthly_idx.index >= start)
                             & (monthly_idx.index <= end)].tolist()
    n = 0
    basket_diff = 0
    old_style_held = new_style_held = 0
    l1_sum = 0.0
    for sd in sigs:
        wo = cpm_mech_wf(close, sd, CPM8_CURRENT)
        wn = cpm_mech_wf(close, sd, CPM8_NEW)
        setq = {k for k, v in wo.items() if v > 1e-9}
        setn = {k for k, v in wn.items() if v > 1e-9}
        # collapse style assets to count of style slots filled (0/1/2) + label
        ro = (setq - OLD_STYLE) | ({f"STYLE{len(setq & OLD_STYLE)}"})
        rn = (setn - NEW_STYLE) | ({f"STYLE{len(setn & NEW_STYLE)}"})
        if ro != rn:
            basket_diff += 1
        old_style_held += int(bool(setq & OLD_STYLE))
        new_style_held += int(bool(setn & NEW_STYLE))
        # L1 weight distance treating style sleeve as one aggregate slot
        common = (set(wo) | set(wn)) - OLD_STYLE - NEW_STYLE
        l1 = abs(sum(wo.get(k, 0.0) for k in OLD_STYLE)
                 - sum(wn.get(k, 0.0) for k in NEW_STYLE))
        l1 += sum(abs(wo.get(k, 0.0) - wn.get(k, 0.0)) for k in common)
        l1_sum += l1
        n += 1
    return {
        "n_rebals": n,
        "basket_differs_count": basket_diff,
        "basket_differs_pct": 100.0 * basket_diff / n if n else float("nan"),
        "old_style_slot_held_pct": 100.0 * old_style_held / n if n else float("nan"),
        "new_style_slot_held_pct": 100.0 * new_style_held / n if n else float("nan"),
        "mean_L1_weight_dist_styleslot": l1_sum / n if n else float("nan"),
    }


def main():
    end = pd.Timestamp("2026-05-22")
    ext_start = pd.Timestamp("1999-03-10")
    clean_start = pd.Timestamp("2008-05-30")

    panel = load_panel(start=ext_start, end=end)
    end = min(end, panel.index[-1])
    cash = panel[DEFAULT_CASH].ffill().pct_change().dropna()

    # Fetch IWF + IWD adjusted close (same convention) and join.
    for t in ("IWF", "IWD"):
        s = _fetch_cached_adjusted_close(t, ext_start - pd.DateOffset(years=2),
                                         end, "/tmp/cpm_cache")
        if s.empty:
            raise SystemExit(f"FATAL: could not fetch {t}")
        panel = panel.join(s.rename(t), how="left")
    inception = {t: (panel[t].first_valid_index()) for t in ("IWF", "IWD")}

    # OHLC: append IWF/IWD to cache ticker list for exact mooex.
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
        print(f"  {name:20s} CLEAN sharpe={c['sharpe']:.4f} cagr={c['cagr']*100:.2f}% "
              f"maxdd={c['maxdd']*100:.2f}% calmar={c['calmar']:.4f}")

    cur_sh = metrics["CPM8_current"]["CLEAN"]["sharpe"]
    gate = abs(cur_sh - FULL_CPM_ANCHOR) < 5e-4

    # correlations (daily returns), both windows: NEW pair vs OLD pair
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

    # style rotation (NEW universe) + (OLD universe for contrast)
    rotation = {}
    for wn, (ws, we) in windows.items():
        rotation[wn] = {
            "NEW_IWF_IWD": style_rotation(close, CPM8_NEW, NEW_STYLE, ws, we),
            "OLD_QQQ_SPHQ": style_rotation(close, CPM8_CURRENT, OLD_STYLE, ws, we),
        }

    seldiv = {wn: selection_divergence(close, ws, we)
              for wn, (ws, we) in windows.items()}

    new_sh = metrics["CPM8_IWF_IWD_swap"]["CLEAN"]["sharpe"]

    out = {
        "meta": {
            "conv": CONV, "cost_bps": COST_BPS_PER_SIDE, "top_k": TOP_K,
            "lookback": CORR_LOOKBACK_DAYS,
            "mechanism": "CPM FIXED R1 M1 (vol-adj Faber rank + raw-Faber screen, min-var 3-of-4 at n_pos=4, TIP-only canary, top-4, equal-weight, best-of{SHV,IEF} safe, breadth-scaled partial-safe)",
            "clean": f"{clean_start.date()}..{end.date()}",
            "ext": f"{ext_start.date()}..{end.date()}",
            "cpm8_current": CPM8_CURRENT,
            "cpm8_iwf_iwd_swap": CPM8_NEW,
            "swap": "QQQ+SPHQ -> IWF+IWD",
            "iwf_inception": str(inception["IWF"].date()) if inception["IWF"] is not None else None,
            "iwd_inception": str(inception["IWD"].date()) if inception["IWD"] is not None else None,
            "anchor_full_CPM8": FULL_CPM_ANCHOR,
            "caveat": "Single 2-ticker swap, single in-sample window -> HIGH overfit caution. IWF/IWD fetched live (yfinance auto_adjust), both inception 2000-05-26 -> EXT has ~14mo pre-inception gap (style assets unselectable, mechanism falls to other assets/safe); CLEAN fully covered -> trust CLEAN. Point-estimates only; bootstrap skipped per scope. CPM prod UNCHANGED.",
        },
        "gate_current_reproduces_full_CPM8": {
            "actual": cur_sh, "target": FULL_CPM_ANCHOR, "pass": bool(gate)},
        "metrics": metrics,
        "turnover": turnover,
        "correlation": corr,
        "style_rotation": rotation,
        "selection_divergence": seldiv,
        "summary": {
            "d_sharpe_CLEAN": new_sh - cur_sh,
            "d_sortino_CLEAN": metrics["CPM8_IWF_IWD_swap"]["CLEAN"]["sortino"]
                               - metrics["CPM8_current"]["CLEAN"]["sortino"],
            "d_cagr_CLEAN": metrics["CPM8_IWF_IWD_swap"]["CLEAN"]["cagr"]
                            - metrics["CPM8_current"]["CLEAN"]["cagr"],
            "d_maxdd_CLEAN": metrics["CPM8_IWF_IWD_swap"]["CLEAN"]["maxdd"]
                             - metrics["CPM8_current"]["CLEAN"]["maxdd"],
            "d_calmar_CLEAN": metrics["CPM8_IWF_IWD_swap"]["CLEAN"]["calmar"]
                              - metrics["CPM8_current"]["CLEAN"]["calmar"],
            "d_martin_CLEAN": metrics["CPM8_IWF_IWD_swap"]["CLEAN"]["martin"]
                              - metrics["CPM8_current"]["CLEAN"]["martin"],
            "d_sharpe_EXT": metrics["CPM8_IWF_IWD_swap"]["EXT"]["sharpe"]
                            - metrics["CPM8_current"]["EXT"]["sharpe"],
        },
    }
    out_json = Path(__file__).with_suffix(".json")
    out_json.write_text(json.dumps(out, indent=2, default=float))
    print("\nGATE:", json.dumps(out["gate_current_reproduces_full_CPM8"], indent=2, default=float))
    print("CORR:", json.dumps(corr, indent=2, default=float))
    print("SUMMARY:", json.dumps(out["summary"], indent=2, default=float))
    print("ROTATION NEW CLEAN held_pct:", json.dumps(rotation["CLEAN"]["NEW_IWF_IWD"]["held_pct"], default=float))
    print("WROTE", out_json)
    return out


if __name__ == "__main__":
    main()
