# -*- coding: utf-8 -*-
"""Throwaway research (READ-ONLY re: production): CPM regime-conditional scenario table.

Goal: classify the monthly history into regimes and produce a regime-conditional
forward-Sharpe scenario decomposition so a reader can stress the ~0.72 central
forward-Sharpe estimate against their own regime priors.

Convention: mooex (T+1 MOO exact, real yfinance opens), 10 bps/side, monthly signal.
Clean window 2008-05-30..2026-05-22 (18y). Ext 1999-03-10..2026-05-22 (more regime
coverage). Anchor (must reproduce): CPM clean Sharpe 1.1910.

Regime classifier (modern sample, computed per calendar month at PRIOR month-end,
no lookahead):
  - Equity trend sign: SPY trailing 12m total return (>0 uptrend, <=0 downtrend).
  - Realized-vol tercile: SPY trailing 63-trading-day annualized realized vol,
    terciled across the EVAL sample.
  Buckets:
    (A) trending / low-vol : uptrend AND vol NOT in top tercile
    (B) mean-reverting / high-vol (choppy/crisis): downtrend OR vol in top tercile
    (C) stagflation / inflation-rotation: modern sample has NO clean stagflation
        regime (CPI never ran like the 1970s with a sustained equity+bond bear).
        We (i) flag the closest modern analog (2021-04..2022-12 inflation/hiking
        rotation) as a sub-window, and (ii) import the 1970s cross-asset evidence
        (research/stagflation_1970s_cpm_crossasset_findings.md) as the qualitative
        bucket-C data point.

Writes research/cpm_regime_scenarios_findings.md (+ .json). No production files touched.
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
    load_panel, RISKY_UNIVERSE, SAFE_POOL, CANARY_ASSETS, DEFAULT_CASH,
)
import cpm_robust_param_sweep as RPS
import cpm_benchmarks_proper as BP

EXT = pd.Timestamp("1999-03-10")
CS = pd.Timestamp("2008-05-30")
END = pd.Timestamp("2026-05-22")
SPLIT = pd.Timestamp("2017-01-01")
INFL_LO = pd.Timestamp("2021-04-01")
INFL_HI = pd.Timestamp("2022-12-31")
ANCHOR_CLEAN_SHARPE = 1.1910


def monthly_excess(daily_ret: pd.Series, cash_daily: pd.Series) -> pd.Series:
    """Monthly compounded excess return (strategy - cash), indexed by month-end."""
    m_strat = (1 + daily_ret.fillna(0.0)).resample("ME").prod() - 1
    m_cash = (1 + cash_daily.reindex(daily_ret.index).fillna(0.0)).resample("ME").prod() - 1
    return (m_strat - m_cash).dropna()


def ann_sharpe_monthly(m_excess: pd.Series) -> float:
    if len(m_excess) < 2:
        return float("nan")
    sd = m_excess.std(ddof=0) * np.sqrt(12)
    return float((m_excess.mean() * 12) / sd) if sd > 0 else float("nan")


def regime_labels(spy_close: pd.Series, eval_index_months: pd.DatetimeIndex) -> pd.Series:
    """Label each eval month A/B by trend sign + vol tercile, decided at prior ME."""
    spy_daily = spy_close.ffill().pct_change()
    # trailing 63d annualized realized vol, sampled at month-end
    rv = spy_daily.rolling(63).std() * np.sqrt(252)
    rv_me = rv.resample("ME").last()
    # trailing 12m (~252d) total return, sampled at month-end
    m_close = spy_close.resample("ME").last()
    trend12 = m_close / m_close.shift(12) - 1.0

    # tercile cut on the vol values that actually fall in the eval window
    rv_eval = rv_me.reindex(eval_index_months).dropna()
    q1, q2 = rv_eval.quantile([1 / 3, 2 / 3])

    labels = {}
    meta = {}
    for m in eval_index_months:
        # decide using PRIOR month-end info (shift by one ME)
        prior = m - pd.offsets.MonthEnd(1)
        v = rv_me.get(prior, np.nan)
        t = trend12.get(prior, np.nan)
        if pd.isna(v) or pd.isna(t):
            labels[m] = "NA"
            meta[m] = (t, v, None)
            continue
        high_vol = v > q2
        up = t > 0
        if up and not high_vol:
            labels[m] = "A_trending_lowvol"
        else:
            labels[m] = "B_meanrev_highvol"
        meta[m] = (float(t), float(v), labels[m])
    return pd.Series(labels), (float(q1), float(q2)), meta


def main():
    panel = load_panel(start=EXT, end=END)
    open_df, close_yf = H.load_open_close()
    intraday = (close_yf / open_df - 1.0).reindex(panel.index)
    overnight = (open_df / close_yf.shift(1) - 1.0).reindex(panel.index)
    cash_daily = panel["SHV"].ffill().pct_change()

    # ---- CPM baseline series (anchor) ----
    cpm_s, cpm_fb = RPS.run_series(panel, intraday, overnight, cost=RPS.COST_BASE, **RPS.BASE)
    clean_anchor = RPS.metr(cpm_s, cash_daily, CS, END)
    print("ANCHOR clean Sharpe %.4f (expect %.4f)" % (clean_anchor["sharpe"], ANCHOR_CLEAN_SHARPE))

    # ---- Benchmarks (same convention, same panel) ----
    bm_cols = sorted(set(RISKY_UNIVERSE + ["SPY", "IEF", "SHV"]) & set(panel.columns))
    bm_close = panel[bm_cols]
    bm_daily = bm_close.ffill().pct_change()
    sixty_s, _ = BP.run_wf(bm_close, bm_daily, intraday, overnight, EXT, END, BP.make_6040_wf(bm_close))
    spy_daily = bm_daily["SPY"]  # buy-hold equity proxy

    # ---- monthly excess series ----
    m_cpm = monthly_excess(cpm_s, cash_daily)
    m_60 = monthly_excess(sixty_s, cash_daily)
    m_spy = monthly_excess(spy_daily, cash_daily)

    out = {
        "meta": {
            "convention": "mooex", "cost_bps_side": 10,
            "ext_window": [str(EXT.date()), str(END.date())],
            "clean_window": [str(CS.date()), str(END.date())],
            "anchor_clean_sharpe_expected": ANCHOR_CLEAN_SHARPE,
            "anchor_clean_sharpe_reproduced": clean_anchor["sharpe"],
            "classifier": ("SPY trailing-12m trend sign + SPY trailing-63d realized-vol "
                           "tercile, decided at prior month-end (no lookahead). "
                           "A=uptrend & not-top-vol-tercile; B=downtrend OR top-vol-tercile; "
                           "C=stagflation imported from 1970s cross-asset evidence (no clean "
                           "modern stagflation regime)."),
        }
    }

    # ============== run for both EXT and CLEAN samples ==============
    for sample, lo in [("ext", EXT), ("clean", CS)]:
        idx = m_cpm.loc[(m_cpm.index >= lo) & (m_cpm.index <= END)].index
        labels, (q1, q2), meta = regime_labels(panel["SPY"], idx)
        rec = {"vol_terciles_ann": {"q33": q1, "q67": q2}, "n_months_total": int(len(idx)),
               "regimes": {}}
        for reg in ["A_trending_lowvol", "B_meanrev_highvol"]:
            months = labels[labels == reg].index
            mm_cpm = m_cpm.reindex(months).dropna()
            mm_60 = m_60.reindex(months).dropna()
            mm_spy = m_spy.reindex(months).dropna()
            rec["regimes"][reg] = {
                "n_months": int(len(months)),
                "frac_of_sample": float(len(months) / len(idx)) if len(idx) else None,
                "cpm_sharpe": ann_sharpe_monthly(mm_cpm),
                "cpm_mean_ann_excess": float(mm_cpm.mean() * 12),
                "cpm_vol_ann": float(mm_cpm.std(ddof=0) * np.sqrt(12)),
                "spy_sharpe": ann_sharpe_monthly(mm_spy),
                "sixty40_sharpe": ann_sharpe_monthly(mm_60),
            }
        # inflation-rotation sub-window (modern analog for bucket C)
        inf_idx = m_cpm.loc[(m_cpm.index >= INFL_LO) & (m_cpm.index <= INFL_HI)].index
        inf_idx = inf_idx.intersection(idx)
        if len(inf_idx) >= 2:
            rec["inflation_rotation_2021_2022"] = {
                "window": [str(INFL_LO.date()), str(INFL_HI.date())],
                "n_months": int(len(inf_idx)),
                "cpm_sharpe": ann_sharpe_monthly(m_cpm.reindex(inf_idx).dropna()),
                "spy_sharpe": ann_sharpe_monthly(m_spy.reindex(inf_idx).dropna()),
                "sixty40_sharpe": ann_sharpe_monthly(m_60.reindex(inf_idx).dropna()),
            }
        # subperiod 2017-26 (largely trending/low-vol)
        if sample == "clean":
            sp_idx = m_cpm.loc[(m_cpm.index >= SPLIT) & (m_cpm.index <= END)].index
            rec["subperiod_2017_2026"] = {
                "n_months": int(len(sp_idx)),
                "cpm_sharpe": ann_sharpe_monthly(m_cpm.reindex(sp_idx).dropna()),
            }
        out[sample] = rec
        print("\n[%s] terciles q33=%.3f q67=%.3f  N=%d" % (sample, q1, q2, len(idx)))
        for reg, d in rec["regimes"].items():
            print("  %-22s n=%3d frac=%.2f  CPM S=%.3f  SPY S=%.3f  60/40 S=%.3f"
                  % (reg, d["n_months"], d["frac_of_sample"], d["cpm_sharpe"],
                     d["spy_sharpe"], d["sixty40_sharpe"]))

    # ============== 1970s stagflation bucket (imported) ==============
    out["stagflation_1970s_imported"] = {
        "source": "research/stagflation_1970s_cpm_crossasset_findings.md",
        "note": ("Reduced 4-asset cross-asset CPM proxy, 1969-1985, no costs. "
                 "De-artifacted realistic read: CAGR ~19-25%, MaxDD ~-9 to -13%, "
                 "Sharpe ~0.8-1.0. CPM rotated ~90% into gold+commodities, profited "
                 "through 1973-74 (+59 to +184%) and 1977-82 while buy-hold equity "
                 "lost -38.6% (real -50%) and 60/40 -24%."),
        "cpm_sharpe_realistic_range": [0.8, 1.0],
        "buyhold_equity_real": "deeply negative (real MaxDD ~-50%)",
    }

    # ============== forward scenario table ==============
    # base decomposition (from cpm_deflated_sharpe_findings): 1.19 in-sample peak ->
    #   x0.82 selection de-peak -> ~0.98 -> x0.85 execution -> ~0.83 -> x0.88 regime -> ~0.72.
    # Regime-conditional: replace the single 0.88 regime factor with a regime-specific
    # multiplier applied to the post-execution ~0.83 ideal-regime level, anchored to the
    # observed regime-conditional Sharpe RATIOS (regime vs full-sample).
    clean_full = clean_anchor["sharpe"]
    a = out["clean"]["regimes"]["A_trending_lowvol"]["cpm_sharpe"]
    b = out["clean"]["regimes"]["B_meanrev_highvol"]["cpm_sharpe"]
    # post-execution ideal level (in-sample, both regimes) ~0.83
    post_exec = 0.83
    # regime ratio vs clean-full -> scale the post-exec level, then apply a uniform
    # forward de-bias (regime non-stationarity floor) so the sample-weighted center ~0.72.
    ratio_a = a / clean_full
    ratio_b = b / clean_full
    scenarios = {
        "A_trending_lowvol": {
            "hist_cpm_sharpe_clean": a,
            "forward_scenario": round(post_exec * ratio_a * 0.88, 2),
            "note": ("Best-case regime for the modern engine; 2017-26 (Sharpe 1.38) is "
                     "largely this bucket. Forward upside if trend/low-vol persists."),
        },
        "B_meanrev_highvol": {
            "hist_cpm_sharpe_clean": b,
            "forward_scenario": round(post_exec * ratio_b * 0.88, 2),
            "note": ("Choppy/crisis: CPM's tail-control design helps (shallower DD) but "
                     "raw Sharpe compresses; whipsaw + execution slippage bite hardest."),
        },
        "C_stagflation": {
            "hist_cpm_sharpe_1970s": [0.8, 1.0],
            "forward_scenario": round(0.90 * 0.85, 2),  # ~0.77 mid of 0.8-1.0 x exec/de-peak
            "note": ("No clean modern sample; imported 1970s cross-asset evidence. Cross-asset "
                     "rotation into inflation winners is structurally favorable IF the inflation "
                     "assets (GLD/DBC) remain in the live universe. Forward depends on universe "
                     "breadth + costs (1970s proxy had none)."),
        },
    }
    out["forward_scenarios"] = {
        "central_estimate": 0.72,
        "central_range": [0.62, 0.85],
        "base_decomposition": "1.19 IS peak x0.82 de-peak x0.85 exec x0.88 regime = ~0.72",
        "post_exec_ideal_regime_level": post_exec,
        "regime_ratios_vs_clean_full": {"A": ratio_a, "B": ratio_b},
        "table": scenarios,
    }

    # compact 3-row table json
    compact = {
        "convention": "mooex T+1 MOO, 10bps/side, monthly; anchor CPM clean Sharpe 1.1910",
        "central_forward_sharpe": {"central": 0.72, "range": [0.62, 0.85]},
        "rows": [
            {"regime": "A trending / low-vol",
             "hist_cpm_sharpe": round(a, 2),
             "forward_scenario": scenarios["A_trending_lowvol"]["forward_scenario"],
             "note": "best case; 2017-26 (1.38) is mostly this bucket"},
            {"regime": "B mean-reverting / high-vol (choppy/crisis)",
             "hist_cpm_sharpe": round(b, 2),
             "forward_scenario": scenarios["B_meanrev_highvol"]["forward_scenario"],
             "note": "tail-control helps DD; raw Sharpe compresses, whipsaw+slip worst"},
            {"regime": "C stagflation / inflation-rotation (1970s imported)",
             "hist_cpm_sharpe": "0.8-1.0 (1970s proxy)",
             "forward_scenario": scenarios["C_stagflation"]["forward_scenario"],
             "note": "structurally favorable IF GLD/DBC stay in universe; no modern clean sample"},
        ],
    }
    out["compact_table"] = compact

    Path("research/cpm_regime_scenarios_findings.json").write_text(json.dumps(out, indent=2))
    print("\nWROTE research/cpm_regime_scenarios_findings.json")
    print(json.dumps(compact, indent=2))
    return out


if __name__ == "__main__":
    main()
