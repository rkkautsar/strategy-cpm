#!/usr/bin/env python3
"""
Walk-forward rule-freeze validation for FCP.

Tests true OOS performance by "freezing" the current production rule set
and measuring IS vs OOS metrics across 6 temporal splits.

For each freeze year X in {2010, 2012, 2014, 2016, 2018, 2020}:
  IS  = GLOBAL_START .. X-12-31
  OOS = (X+1)-01-01 .. 2026-05-15
  Rule: CURRENT PRODUCTION SPEC (no retuning per freeze year)

Also runs "spec-as-of-freeze-year" variants for 2014 and 2020:
  - HOLD_BUFFER = 3.0  (was 2.5 since 2026-05)
  - AVUV in universe, VBR/XLV not yet added
  => 14-asset risky universe

Deliverables:
  - walk_forward_rule_freeze.log  (full output)
  - Ranked table: freeze_year x (IS Sh, OOS Sh, OOS-IS gap, OOS MaxDD, OOS UPI)
  - Bootstrap Sharpe-diff CI (N=3000, block=21d) per split
  - Sub-window Sharpe consistency across OOS periods
  - 2014/2020 comparison: current spec vs frozen-as-of-year spec

Usage:
  /path/to/.venv/bin/python3 walk_forward_rule_freeze.py
"""
from __future__ import annotations

import sys
import logging
from pathlib import Path

import numpy as np
import pandas as pd

# -- path setup ---------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
FCP_DIR    = SCRIPT_DIR.parent
sys.path.insert(0, str(FCP_DIR))
import fcp_live as fcp

# -- logging ------------------------------------------------------------------
LOG_PATH = SCRIPT_DIR / "walk_forward_rule_freeze.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(str(LOG_PATH), mode="w"),
    ],
)

def logprint(s=""):
    logging.info(s)

# -- Constants ----------------------------------------------------------------
GLOBAL_START = pd.Timestamp("1997-08-31")
GLOBAL_END   = pd.Timestamp("2026-05-15")
FREEZE_YEARS = [2010, 2012, 2014, 2016, 2018, 2020]

# "Spec as-of-2014/2020" frozen variant
# At that time: AVUV in, VBR/XLV not yet added, HOLD_BUFFER=3.0
AGGR_2014  = ["QQQ", "IGM", "SPMO", "XLE", "XRT", "COWZ",
               "SPHQ", "XMMO", "XMHQ", "AVUV"]   # 10 -- no VBR, no XLV
RISKY_2014 = AGGR_2014 + fcp.INTERNATIONAL + fcp.DIVERSIFIERS  # 14 risky

N_BOOT     = 3000
BLOCK_SIZE = 21    # ~1 trading month

# Sub-windows for OOS consistency check
SUBWINDOW_YEARS = [(2011, 2015), (2015, 2018), (2018, 2022), (2022, 2026)]


# -- Metric helpers -----------------------------------------------------------

def ulcer_index(daily_returns: pd.Series) -> float:
    """RMS of drawdowns from running peak (Martin/McCann Ulcer Index)."""
    eq   = (1 + daily_returns).cumprod()
    peak = eq.cummax()
    dd   = (eq / peak) - 1
    return float(np.sqrt((dd ** 2).mean()))


def extended_metrics(daily_returns: pd.Series) -> dict:
    r = daily_returns.dropna()
    if len(r) < 30:
        return dict(sharpe=np.nan, cagr=np.nan, vol=np.nan,
                    max_dd=np.nan, upi=np.nan, years=0.0)
    eq   = (1 + r).cumprod()
    days = (r.index[-1] - r.index[0]).days
    yrs  = days / 365.25
    cagr = (eq.iloc[-1] / eq.iloc[0]) ** (1 / yrs) - 1 if yrs > 0 else np.nan
    vol  = r.std(ddof=0) * np.sqrt(252)
    sh   = (r.mean() * 252) / vol if vol > 0 else np.nan
    mdd  = float((eq / eq.cummax() - 1).min())
    ui   = ulcer_index(r)
    upi  = cagr / ui if ui > 1e-9 else np.nan
    return dict(sharpe=sh, cagr=cagr, vol=vol, max_dd=mdd, upi=upi, years=yrs)


def block_bootstrap_sharpe_diff_ci(
    is_ret: pd.Series,
    oos_ret: pd.Series,
    n_boot: int = 3000,
    block_size: int = 21,
    seed: int = 42,
) -> dict:
    """
    Block bootstrap CI for IS_Sharpe - OOS_Sharpe.
    Resamples each window independently with fixed-length blocks.
    p_val_deg_sig: fraction of boots where OOS_sh >= IS_sh.
      Small p -> degradation likely real (IS consistently beats OOS even in bootstrap).
    """
    rng = np.random.default_rng(seed)

    def sharpe_boot(arr: np.ndarray, n_blocks: int) -> float:
        idx    = rng.integers(0, max(1, len(arr) - block_size + 1), size=n_blocks)
        sample = np.concatenate([arr[i:i + block_size] for i in idx])
        vol    = sample.std(ddof=0) * np.sqrt(252)
        return float(np.nan if vol < 1e-12 else (sample.mean() * 252) / vol)

    is_arr  = is_ret.dropna().values
    oos_arr = oos_ret.dropna().values
    n_is  = max(2, len(is_arr)  // block_size)
    n_oos = max(2, len(oos_arr) // block_size)

    diffs = []
    for _ in range(n_boot):
        si = sharpe_boot(is_arr,  n_is)
        so = sharpe_boot(oos_arr, n_oos)
        if not (np.isnan(si) or np.isnan(so)):
            diffs.append(si - so)
    diffs = np.array(diffs)

    def sh(r):
        v = r.std(ddof=0) * np.sqrt(252)
        return float((r.mean() * 252) / v) if v > 0 else np.nan

    obs = sh(is_ret.dropna()) - sh(oos_ret.dropna())
    return dict(
        obs_diff       = float(obs),
        boot_mean      = float(np.mean(diffs)),
        boot_std       = float(np.std(diffs)),
        ci_lo_95       = float(np.percentile(diffs,  2.5)),
        ci_hi_95       = float(np.percentile(diffs, 97.5)),
        p_val_deg_sig  = float(np.mean(diffs <= 0)),
        n_boot         = len(diffs),
    )


def subwindow_sharpe(oos_returns: pd.Series, windows: list) -> dict:
    result = {}
    for (y0, y1) in windows:
        seg = oos_returns[pd.Timestamp(f"{y0}-01-01"):pd.Timestamp(f"{y1}-01-01")].dropna()
        if len(seg) < 60:
            result[f"{y0}-{y1}"] = np.nan
            continue
        vol = seg.std(ddof=0) * np.sqrt(252)
        result[f"{y0}-{y1}"] = float((seg.mean() * 252) / vol) if vol > 0 else np.nan
    return result


# -- Panel loading ------------------------------------------------------------

def load_full_panel() -> pd.DataFrame:
    logprint("Loading price panel ...")
    _orig = fcp.RISKY_UNIVERSE[:]
    # Expand to include all needed tickers across both spec variants
    fcp.RISKY_UNIVERSE = list(dict.fromkeys(fcp.RISKY_UNIVERSE + ["AVUV", "VBR"]))
    panel = fcp.load_panel(start=GLOBAL_START, end=GLOBAL_END)
    fcp.RISKY_UNIVERSE = _orig
    logprint(f"Panel: {panel.index[0].date()} -> {panel.index[-1].date()}, "
             f"{len(panel.columns)} assets")
    missing = sorted(set(fcp.RISKY_UNIVERSE + ["AVUV"] + fcp.SAFE_POOL +
                         fcp.CANARY_ASSETS) - set(panel.columns))
    if missing:
        logprint(f"WARN tickers absent from panel: {missing}")
    return panel


# -- Run one full-window experiment -------------------------------------------

def run_experiment(
    panel: pd.DataFrame,
    label: str,
    risky_universe: list,
    aggr_factors: list,
    hold_buffer: float,
) -> pd.Series:
    """Patch fcp module globals, backtest full window, restore. Returns daily returns."""
    _rv = fcp.RISKY_UNIVERSE[:]
    _af = fcp.AGGR_FACTORS[:]
    _hb = fcp.HOLD_BUFFER
    fcp.RISKY_UNIVERSE = risky_universe
    fcp.AGGR_FACTORS   = aggr_factors
    fcp.HOLD_BUFFER    = hold_buffer
    logprint(f"  [{label}] universe={len(risky_universe)} risky, buf={hold_buffer}")
    try:
        daily, _ = fcp.run_fcp_backtest(
            panel, GLOBAL_START, GLOBAL_END,
            apply_vol_target=True,
            cost_bps=fcp.COST_BPS_PER_SIDE,
        )
    finally:
        fcp.RISKY_UNIVERSE = _rv
        fcp.AGGR_FACTORS   = _af
        fcp.HOLD_BUFFER    = _hb
    logprint(f"  [{label}] done: {len(daily)} trading days")
    return daily


# -- Main ---------------------------------------------------------------------

def main():
    logprint("=" * 78)
    logprint("FCP WALK-FORWARD RULE-FREEZE VALIDATION")
    logprint(f"Global window : {GLOBAL_START.date()} -> {GLOBAL_END.date()}")
    logprint(f"Freeze years  : {FREEZE_YEARS}")
    logprint(f"Bootstrap     : N={N_BOOT}, block={BLOCK_SIZE}d")
    logprint("=" * 78)

    panel = load_full_panel()

    # --- 1. Current production run -------------------------------------------
    logprint("")
    logprint("-- CURRENT PRODUCTION SPEC --")
    logprint(f"   universe ({len(fcp.RISKY_UNIVERSE)}): {fcp.RISKY_UNIVERSE}")
    logprint(f"   HOLD_BUFFER={fcp.HOLD_BUFFER}  TOP_K={fcp.TOP_K_CANDIDATES}  "
             f"CORR={fcp.CORR_LOOKBACK_DAYS}d  VOL_TARGET={fcp.TARGET_VOL:.0%}  "
             f"COST={fcp.COST_BPS_PER_SIDE}bps/side")
    prod_daily = run_experiment(
        panel, "PROD",
        risky_universe=fcp.RISKY_UNIVERSE,
        aggr_factors=fcp.AGGR_FACTORS,
        hold_buffer=fcp.HOLD_BUFFER,
    )

    # --- 2. Frozen-2014/2020 spec run ----------------------------------------
    logprint("")
    logprint("-- FROZEN-2014/2020 SPEC (14 risky, buf=3.0) --")
    logprint(f"   universe ({len(RISKY_2014)}): {RISKY_2014}")
    spec2014_daily = run_experiment(
        panel, "SPEC-2014",
        risky_universe=RISKY_2014,
        aggr_factors=AGGR_2014,
        hold_buffer=3.0,
    )

    # --- 3. Walk-forward splits: current spec --------------------------------
    logprint("")
    logprint("=" * 78)
    logprint("WALK-FORWARD SPLITS -- CURRENT PRODUCTION SPEC")
    logprint("=" * 78)

    rows      = []
    boot_rows = []

    for fy in FREEZE_YEARS:
        is_end    = pd.Timestamp(f"{fy}-12-31")
        oos_start = pd.Timestamp(f"{fy + 1}-01-01")
        is_ret  = prod_daily[GLOBAL_START:is_end].dropna()
        oos_ret = prod_daily[oos_start:GLOBAL_END].dropna()
        im = extended_metrics(is_ret)
        om = extended_metrics(oos_ret)
        gap = (om["sharpe"] - im["sharpe"]
               if not (np.isnan(im["sharpe"]) or np.isnan(om["sharpe"])) else np.nan)

        rows.append(dict(
            freeze_year=fy,
            is_yrs=round(im["years"], 1), is_sh=im["sharpe"],
            is_cagr=im["cagr"], is_mdd=im["max_dd"], is_upi=im["upi"],
            oos_yrs=round(om["years"], 1), oos_sh=om["sharpe"],
            oos_cagr=om["cagr"], oos_mdd=om["max_dd"], oos_upi=om["upi"],
            sh_gap=gap,
        ))

        logprint(f"\n  Freeze {fy}: IS={im['years']:.1f}y  OOS={om['years']:.1f}y")
        logprint(f"    IS  Sh={im['sharpe']:+.3f}  CAGR={im['cagr']*100:+.2f}%  "
                 f"MaxDD={im['max_dd']*100:.2f}%  UPI={im['upi']:+.3f}")
        logprint(f"    OOS Sh={om['sharpe']:+.3f}  CAGR={om['cagr']*100:+.2f}%  "
                 f"MaxDD={om['max_dd']*100:.2f}%  UPI={om['upi']:+.3f}")
        logprint(f"    delta Sharpe (OOS - IS) = {gap:+.3f}")

        logprint(f"    Bootstrap CI (N={N_BOOT}, block={BLOCK_SIZE}d) ...")
        boot = block_bootstrap_sharpe_diff_ci(is_ret, oos_ret, N_BOOT, BLOCK_SIZE)
        sig_tag = ("*** p<0.05" if boot["p_val_deg_sig"] < 0.05
                   else ("* p<0.15" if boot["p_val_deg_sig"] < 0.15 else "ns"))
        logprint(f"    IS-OOS diff: obs={boot['obs_diff']:+.3f}  "
                 f"boot_mean={boot['boot_mean']:+.3f}  std={boot['boot_std']:.3f}")
        logprint(f"    95% CI: [{boot['ci_lo_95']:+.3f}, {boot['ci_hi_95']:+.3f}]  "
                 f"p_deg_sig={boot['p_val_deg_sig']:.3f}  n={boot['n_boot']}  {sig_tag}")
        boot_rows.append(dict(freeze_year=fy, **boot, sig=sig_tag))

        sw = subwindow_sharpe(oos_ret, SUBWINDOW_YEARS)
        sw_str = "  ".join(
            f"{k}: {v:+.2f}" for k, v in sw.items() if not np.isnan(v)
        )
        logprint(f"    OOS sub-window Sharpes: {sw_str or 'n/a (all <60d)'}")

    # --- 4. Ranked summary table ---------------------------------------------
    logprint("")
    logprint("=" * 78)
    logprint("RANKED SUMMARY TABLE  (sorted by OOS Sharpe desc)")
    logprint("=" * 78)
    df = pd.DataFrame(rows).sort_values("oos_sh", ascending=False)
    hdr = ("  FY   IS_Yrs   IS_Sh  IS_CAGR   IS_DD  IS_UPI"
           " | OOS_Yrs  OOS_Sh OOS_CAGR  OOS_DD OOS_UPI |    dSh")
    logprint(hdr)
    logprint("-" * len(hdr))
    for _, r in df.iterrows():
        logprint(
            f"  {int(r.freeze_year):>4}   {r.is_yrs:>5.1f} "
            f"{r.is_sh:+7.3f} {r.is_cagr*100:+7.2f}% {r.is_mdd*100:6.2f}% {r.is_upi:+7.3f}"
            f" |  {r.oos_yrs:>6.1f} {r.oos_sh:+7.3f} {r.oos_cagr*100:+8.2f}%"
            f" {r.oos_mdd*100:6.2f}% {r.oos_upi:+7.3f}"
            f" | {r.sh_gap:+7.3f}"
        )

    logprint("")
    logprint("Bootstrap significance:")
    logprint("  FY   obs_diff    ci_lo    ci_hi   p_sig  n_boot     verdict")
    logprint("  " + "-" * 62)
    for b in boot_rows:
        logprint(f"  {int(b['freeze_year']):>4} {b['obs_diff']:+9.3f} "
                 f"{b['ci_lo_95']:+8.3f} {b['ci_hi_95']:+8.3f} "
                 f"{b['p_val_deg_sig']:>7.3f} {int(b['n_boot']):>7}  {b['sig']:>10}")

    # --- 5. Sub-window consistency matrix ------------------------------------
    logprint("")
    logprint("=" * 78)
    logprint("OOS SUB-WINDOW SHARPE CONSISTENCY (current prod spec)")
    logprint("  nan = sub-window pre-OOS or < 60 trading days")
    logprint("=" * 78)
    sw_data = []
    for fy in FREEZE_YEARS:
        oos_ret = prod_daily[pd.Timestamp(f"{fy+1}-01-01"):GLOBAL_END].dropna()
        sw = subwindow_sharpe(oos_ret, SUBWINDOW_YEARS)
        sw["freeze_year"] = fy
        sw_data.append(sw)
    sw_df = pd.DataFrame(sw_data).set_index("freeze_year")
    logprint(sw_df.round(3).to_string())

    # --- 6. Spec comparison: 2014 & 2020 ------------------------------------
    logprint("")
    logprint("=" * 78)
    logprint("SPEC COMPARISON: CURRENT-PROD vs FROZEN-AS-OF-YEAR")
    logprint("  current : 15 risky (VBR+XLV, no AVUV), buf=2.5")
    logprint("  frozen  : 14 risky (AVUV, no VBR/XLV),  buf=3.0")
    logprint("=" * 78)

    comp_rows = []
    for fy, slabel, daily in [
        (2014, "current-15/2.5", prod_daily),
        (2014, "frozen-14/3.0",  spec2014_daily),
        (2020, "current-15/2.5", prod_daily),
        (2020, "frozen-14/3.0",  spec2014_daily),
    ]:
        is_end    = pd.Timestamp(f"{fy}-12-31")
        oos_start = pd.Timestamp(f"{fy + 1}-01-01")
        im = extended_metrics(daily[GLOBAL_START:is_end].dropna())
        om = extended_metrics(daily[oos_start:GLOBAL_END].dropna())
        gap = (om["sharpe"] - im["sharpe"]
               if not (np.isnan(im["sharpe"]) or np.isnan(om["sharpe"])) else np.nan)
        comp_rows.append(dict(
            fy=fy, spec=slabel,
            is_sh=im["sharpe"],  is_cagr=im["cagr"],  is_mdd=im["max_dd"],
            oos_sh=om["sharpe"], oos_cagr=om["cagr"], oos_mdd=om["max_dd"],
            oos_upi=om["upi"],   sh_gap=gap,
        ))

    cdf = pd.DataFrame(comp_rows)
    logprint(f"\n  {'FY':>4} {'Spec':>18} |"
             f" {'IS_Sh':>7} {'IS_CAGR':>8} {'IS_DD':>7} |"
             f" {'OOS_Sh':>7} {'OOS_CAGR':>9} {'OOS_DD':>7} {'OOS_UPI':>8} |"
             f" {'dSh':>7}")
    logprint("  " + "-" * 107)
    for _, r in cdf.iterrows():
        logprint(f"  {int(r.fy):>4} {r.spec:>18} |"
                 f" {r.is_sh:+7.3f} {r.is_cagr*100:+7.2f}% {r.is_mdd*100:6.2f}% |"
                 f" {r.oos_sh:+7.3f} {r.oos_cagr*100:+8.2f}%"
                 f" {r.oos_mdd*100:6.2f}% {r.oos_upi:+8.3f} | {r.sh_gap:+7.3f}")

    logprint("")
    logprint("OOS winner per freeze year:")
    for fy in [2014, 2020]:
        sub   = cdf[cdf.fy == fy]
        oos_w = sub.sort_values("oos_sh", ascending=False).iloc[0]
        oos_l = sub.sort_values("oos_sh", ascending=False).iloc[1]
        is_w  = sub.sort_values("is_sh",  ascending=False).iloc[0].spec
        logprint(f"  {fy}: OOS winner={oos_w.spec}  (Sh={oos_w.oos_sh:+.3f})"
                 f"  vs {oos_l.spec}  (Sh={oos_l.oos_sh:+.3f})"
                 f"  delta={oos_w.oos_sh - oos_l.oos_sh:+.3f}"
                 f"  [IS winner={is_w}]")

    # --- 7. Caveats ----------------------------------------------------------
    logprint("")
    logprint("=" * 78)
    logprint("CAVEATS & METHODOLOGY")
    logprint("=" * 78)
    caveats = [
        "1. Rule-freeze: ALL splits use CURRENT PRODUCTION SPEC. No re-tuning per year.",
        "2. IS always starts 1997-08-31. Proxy data pre-2000 may differ from live ETFs.",
        "   Treat IS metrics for early splits (IS starting 1997) with extra caution.",
        "3. Bootstrap CI (N=3000, block=21d): IS-OOS Sharpe gap vs block-resampled noise.",
        "   p_deg_sig < 0.05 => degradation exceeds what noise can explain.",
        "4. AVUV live since Sept-2019; proxy_adjusted_close_daily.csv fills pre-2019.",
        "   Frozen-spec OOS window 2015-2019 uses proxy AVUV; post-2019 uses live.",
        "5. Short OOS (freeze_year=2020: ~5y) has high Sharpe variance. Wide CI normal.",
        "6. NO production changes recommended. Empirical evidence only.",
    ]
    for c in caveats:
        logprint(f"  {c}")

    logprint("")
    logprint(f"DONE. Log -> {LOG_PATH}")


if __name__ == "__main__":
    main()
