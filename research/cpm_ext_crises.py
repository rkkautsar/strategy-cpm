"""Analyst research (SCOPED, read-only re production; writes research/ only; no
prod/memo edits; no commit).

GOAL: build an honest EXTENDED-window crisis table for CPM showing every crisis
the extended continuous curve can cover -- LTCM (1998), dot-com (2000-02),
GFC (2008) -- on the same continuous-curve basis the memo uses for GFC
(-11.88%). Plus: per-crisis proxy coverage, VNQ selection frequency, the true
reduced-universe data floor, and a pragmatic SPY/VEIEX extension to maximize
LTCM/dot-com lead-in.

Three curves:
  A) PRODUCTION-PROXY reduced-universe curve. The production engine
     (compute_target_weights) ALREADY drops assets that are missing/NaN from the
     ranking (avail filter), so it natively operates reduced-universe. The proxy
     panel floors most risky assets at 1995-01-04, QQQ(=NDX) reaches 1985,
     TLT(=VUSTX) 1986. So the curve reaches ~1996 after the 13-month faber
     warmup -- VNQ/EFA do NOT bind it.
  B) PRAGMATIC EXTENSION curve (CPM-LIKE, not production): substitute the
     US-equity sleeve with SPY/^GSPC and prepend EEM<-VEIEX (real EM fund,
     1994-05) and SPHQ<-^GSPC (crude quality proxy) below the 1995-01 floor, to
     push the floor toward ~1994 for maximal LTCM/dot-com lead-in. HEAVILY
     CAVEATED: fewer assets + synthetic EM/quality => NOT the production strategy.

Engine + harness reused: cpm_live + the mooex T+1 MOO-exact validation harness.
"""
import sys, json
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

import cpm_benchmarks_proper as CB
import exec_lag_moo_validation_2026_05_30 as H
from cpm_live import (
    compute_target_weights, faber_sma_xs, RISKY_UNIVERSE, SAFE_POOL,
    CANARY_ASSETS, CORR_LOOKBACK_DAYS, _fetch_cached_adjusted_close,
)

CONV = "mooex"
CACHE = "/tmp/cpm_cache"

LIVE_INCEPTION = {
    "QQQ": "1999-03-10", "SPHQ": "2005-12-06", "EFA": "2001-08-14",
    "EEM": "2003-04-07", "VNQ": "2004-09-23", "GLD": "2004-11-18",
    "TLT": "2002-07-22", "DBC": "2006-02-03",
    "HYG": "2007-04-11", "TIP": "2003-12-05",
    "SHV": "2007-01-11", "IEF": "2002-07-22",
}

CRISES = {
    "LTCM":    ("1998-08-01", "1998-12-31"),
    "Dot-com": ("2000-03-01", "2002-12-31"),
    "GFC":     ("2007-10-01", "2009-06-30"),
}


def dd_episode(eq, lo, hi):
    """Peak/trough/depth/recovery for the worst drawdown of equity curve `eq`
    whose trough lies in [lo, hi]. Running high carried from curve start."""
    eq = eq.dropna()
    rm = eq.cummax()
    dd = eq / rm - 1.0
    w = dd.loc[lo:hi]
    if len(w) == 0 or not np.isfinite(w.min()):
        return None
    trough_date = w.idxmin()
    depth = float(w.min())
    peak_val = float(rm.loc[trough_date])
    pre = eq.loc[:trough_date]
    peak_date = pre[pre >= peak_val * (1 - 1e-9)].index[-1]
    post = eq.loc[trough_date:]
    recs = post[(post >= peak_val) & (post.index > trough_date)]
    recovery_date = recs.index[0] if len(recs) else None
    rec_days = (recovery_date - trough_date).days if recovery_date is not None else None
    return dict(
        peak_date=str(peak_date.date()), trough_date=str(trough_date.date()),
        depth=depth,
        recovery_date=str(recovery_date.date()) if recovery_date is not None else None,
        trough_to_recovery_days=rec_days,
        peak_to_trough_days=(trough_date - peak_date).days,
        curve_start=str(eq.index[0].date()),
        leadin_days_curvestart_to_peak=(peak_date - eq.index[0]).days,
    )


def crisis_table(eq):
    return {nm: dd_episode(eq, lo, hi) for nm, (lo, hi) in CRISES.items()}


def show_table(title, table):
    print("\n" + "=" * 86)
    print(title)
    print("=" * 86)
    print(f"{'Crisis':<10}{'Peak':>12}{'Trough':>12}{'Depth':>9}{'Recovery':>12}"
          f"{'T->R d':>8}{'P->T d':>8}{'lead-in d':>10}")
    for nm in CRISES:
        d = table.get(nm)
        if d is None:
            print(f"{nm:<10}{'n/a (curve starts after window)':>40}")
            continue
        print(f"{nm:<10}{d['peak_date']:>12}{d['trough_date']:>12}{d['depth']*100:>8.2f}%"
              f"{str(d['recovery_date']):>12}{str(d['trough_to_recovery_days']):>8}"
              f"{d['peak_to_trough_days']:>8}{d['leadin_days_curvestart_to_peak']:>10}")


def monthly_diag(close, sleeve_start, end):
    """Per-month regime/basket diagnostics + selection counts + availability."""
    monthly_idx = (pd.DataFrame({"x": 1}, index=close.index)
                   .groupby(pd.Grouper(freq="ME")).tail(1)).index
    sigs = [d for d in monthly_idx if sleeve_start <= d <= end]
    pick_counts = {t: 0 for t in RISKY_UNIVERSE}
    riskon = 0
    avail_counts = []
    for sd in sigs:
        w, basket, regime, safe = compute_target_weights(close, sd)
        monthly = close.loc[:sd].resample("ME").last()
        faber = faber_sma_xs(monthly)
        n_avail = sum(1 for t in RISKY_UNIVERSE
                      if t in faber.index and pd.notna(faber[t])
                      and (sd in close.index and pd.notna(close.loc[sd].get(t, np.nan))))
        avail_counts.append((sd, n_avail))
        if regime == "RISK_ON" and basket:
            riskon += 1
            for t in basket:
                if t in pick_counts:
                    pick_counts[t] += 1
    return sigs, pick_counts, riskon, avail_counts


def splice_below(existing, proxy):
    """Return existing series with `proxy` (return-chained, level-matched at the
    join) prepended for dates strictly before existing.first_valid_index()."""
    existing = existing.dropna()
    proxy = proxy.dropna()
    if existing.empty or proxy.empty:
        return existing
    join = existing.index[0]
    # nearest proxy date <= join
    pj = proxy.index[proxy.index <= join]
    if len(pj) == 0:
        return existing
    pj = pj[-1]
    factor = existing.iloc[0] / proxy.loc[pj]
    pre = proxy[proxy.index < join] * factor
    return pd.concat([pre, existing]).sort_index()


def main():
    end = pd.Timestamp("2026-05-22")
    panel_start = pd.Timestamp("1995-01-01")
    panel, intraday, overnight, end = CB.build_data(panel_start, end)
    print(f"Panel {panel.index[0].date()} -> {panel.index[-1].date()} ({len(panel)} rows)")

    fv = {t: (panel[t].first_valid_index() if t in panel.columns else None)
          for t in RISKY_UNIVERSE + SAFE_POOL + CANARY_ASSETS}
    binding_all = max(d for d in (fv[t] for t in RISKY_UNIVERSE + SAFE_POOL) if d is not None)
    binding_no_vnq = max(d for t, d in fv.items()
                         if t in RISKY_UNIVERSE + SAFE_POOL and t != "VNQ" and d is not None)
    binding_no_vnq_efa = max(d for t, d in fv.items()
                             if t in RISKY_UNIVERSE + SAFE_POOL and t not in ("VNQ", "EFA")
                             and d is not None)
    ladder = sorted(((t, fv[t]) for t in RISKY_UNIVERSE if fv[t] is not None), key=lambda x: x[1])
    print("ALL-PRESENT binding:", binding_all.date(),
          "| no-VNQ:", binding_no_vnq.date(),
          "| no-VNQ/EFA:", binding_no_vnq_efa.date())
    print("Risky-8 availability ladder:", {t: str(d.date()) for t, d in ladder})

    # ---------------- PART A: production-proxy reduced-universe curve ----------------
    cols = sorted(set(RISKY_UNIVERSE + SAFE_POOL + CANARY_ASSETS) & set(panel.columns))
    close = panel[cols]
    sleeve_start = pd.Timestamp("1995-01-31")
    cpmA, fbA = H.cpm_sleeve_conv(panel, intraday, overnight, sleeve_start, end, CONV)
    cpmA = cpmA.dropna()
    eqA = (1.0 + cpmA).cumprod()
    print(f"\n[A] prod-proxy curve {cpmA.index[0].date()} -> {cpmA.index[-1].date()} "
          f"({len(cpmA)} days); mooex real/fallback rebal = {fbA}")

    sigsA, picksA, riskonA, availA = monthly_diag(close, sleeve_start, end)
    n_months = len(sigsA)
    first_ge = {k: None for k in (4, 5, 6, 7, 8)}
    for d, n in availA:
        for k in first_ge:
            if first_ge[k] is None and n >= k:
                first_ge[k] = d

    sel = {t: dict(picked_months=picksA[t],
                   pct_of_riskon=round(100.0 * picksA[t] / riskonA, 1) if riskonA else None,
                   pct_of_all=round(100.0 * picksA[t] / n_months, 1) if n_months else None)
           for t in RISKY_UNIVERSE}

    print(f"\n[A] months={n_months} risk-on={riskonA}")
    print("[A] selection frequency (months in top-4 risk-on basket):")
    for t in sorted(RISKY_UNIVERSE, key=lambda x: -picksA[x]):
        s = sel[t]
        print(f"    {t:<5} {picksA[t]:>4} mo  {s['pct_of_riskon']:>5}% of risk-on  "
              f"{s['pct_of_all']:>5}% of all months")
    print("[A] reduced-universe first month with >=k risky assets available:")
    for k in (4, 5, 6, 7, 8):
        print(f"    >={k}: {first_ge[k].date() if first_ge[k] is not None else None}")

    tableA = crisis_table(eqA)
    show_table(f"[A] CRISIS DRAWDOWNS -- production-proxy reduced-universe curve "
               f"(from {cpmA.index[0].date()})", tableA)

    # ---------------- PART B: pragmatic SPY/VEIEX extension (CPM-LIKE) ----------------
    print("\n[B] building pragmatic extension panel (fetch ^GSPC, VEIEX)...")
    gspc = _fetch_cached_adjusted_close("^GSPC", pd.Timestamp("1990-01-01"), end, CACHE)
    veiex = _fetch_cached_adjusted_close("VEIEX", pd.Timestamp("1990-01-01"), end, CACHE)
    print(f"    ^GSPC {gspc.index.min().date() if len(gspc) else None}.. ; "
          f"VEIEX {veiex.index.min().date() if len(veiex) else None}..")

    extp = panel.copy()
    # EEM <- VEIEX below EEM's current floor (real EM fund, 1994-05)
    extp["EEM"] = splice_below(extp["EEM"], veiex)
    # SPHQ <- ^GSPC below SPHQ's current floor (CRUDE quality proxy -- caveat)
    extp["SPHQ"] = splice_below(extp["SPHQ"], gspc)
    # US-equity substitution test: QQQ proxy already = NDX(1985); we ALSO splice
    # ^GSPC below QQQ's floor so the US-equity sleeve never binds the floor.
    extp["QQQ"] = splice_below(extp["QQQ"], gspc)
    extp = extp.sort_index()

    # rebuild intraday/overnight on the wider index (no opens pre-ETF -> mooex
    # falls back to close-to-close, already handled by the harness)
    ext_intraday = intraday.reindex(extp.index)
    ext_overnight = overnight.reindex(extp.index)

    fvE = {t: extp[t].first_valid_index() for t in RISKY_UNIVERSE if t in extp.columns}
    ladderE = sorted(fvE.items(), key=lambda x: x[1])
    print("[B] extended availability ladder:", {t: str(d.date()) for t, d in ladderE})

    closeE = extp[cols]
    ext_sleeve_start = pd.Timestamp("1994-01-31")
    cpmB, fbB = H.cpm_sleeve_conv(extp, ext_intraday, ext_overnight, ext_sleeve_start, end, CONV)
    cpmB = cpmB.dropna()
    eqB = (1.0 + cpmB).cumprod()
    print(f"[B] extension curve {cpmB.index[0].date()} -> {cpmB.index[-1].date()} "
          f"({len(cpmB)} days); mooex real/fallback rebal = {fbB}")

    sigsB, picksB, riskonB, availB = monthly_diag(closeE, ext_sleeve_start, end)
    first_geE = {k: None for k in (4, 5, 6, 7, 8)}
    for d, n in availB:
        for k in first_geE:
            if first_geE[k] is None and n >= k:
                first_geE[k] = d
    print("[B] extension first month with >=k risky assets:")
    for k in (4, 5, 6, 7, 8):
        print(f"    >={k}: {first_geE[k].date() if first_geE[k] is not None else None}")

    tableB = crisis_table(eqB)
    show_table(f"[B] CRISIS DRAWDOWNS -- pragmatic SPY/VEIEX extension (CPM-LIKE, from "
               f"{cpmB.index[0].date()})", tableB)

    # ---------------- proxy coverage per crisis ----------------
    cov = {}
    for nm, (lo, hi) in CRISES.items():
        mid = pd.Timestamp(lo) + (pd.Timestamp(hi) - pd.Timestamp(lo)) / 2
        live = [t for t in RISKY_UNIVERSE if pd.Timestamp(LIVE_INCEPTION[t]) <= mid]
        proxy = [t for t in RISKY_UNIVERSE if pd.Timestamp(LIVE_INCEPTION[t]) > mid]
        live_cs = [t for t in ("HYG", "TIP", "SHV", "IEF") if pd.Timestamp(LIVE_INCEPTION[t]) <= mid]
        proxy_cs = [t for t in ("HYG", "TIP", "SHV", "IEF") if pd.Timestamp(LIVE_INCEPTION[t]) > mid]
        cov[nm] = dict(window_mid=str(mid.date()), risky_live=live, risky_proxy=proxy,
                       n_risky_live=len(live), n_risky_proxy=len(proxy),
                       canarysafe_live=live_cs, canarysafe_proxy=proxy_cs)

    print("\n" + "=" * 86)
    print("PROXY COVERAGE per crisis (risky-8 live ETF vs proxy at window midpoint)")
    print("=" * 86)
    for nm in CRISES:
        c = cov[nm]
        print(f"{nm:<10} mid={c['window_mid']}  LIVE {c['n_risky_live']}/8: {','.join(c['risky_live']) or '-'}")
        print(f"{'':<22}PROXY {c['n_risky_proxy']}/8: {','.join(c['risky_proxy']) or '-'}")
        print(f"{'':<22}canary/safe live: {','.join(c['canarysafe_live']) or '-'} | "
              f"proxy: {','.join(c['canarysafe_proxy']) or '-'}")

    # ---------------- LTCM reliability ----------------
    ltA = tableA["LTCM"]
    ltB = tableB["LTCM"]
    ltcm_reliability = dict(
        prodproxy=dict(curve_start=ltA["curve_start"], peak=ltA["peak_date"],
                       leadin_days=ltA["leadin_days_curvestart_to_peak"], depth=ltA["depth"]),
        extension=dict(curve_start=ltB["curve_start"], peak=ltB["peak_date"],
                       leadin_days=ltB["leadin_days_curvestart_to_peak"], depth=ltB["depth"]),
    )

    out = dict(
        meta=dict(convention=CONV, cost_bps=10,
                  panel_start=str(panel.index[0].date()), panel_end=str(end.date()),
                  binding_all_present=str(binding_all.date()),
                  binding_without_vnq=str(binding_no_vnq.date()),
                  binding_without_vnq_efa=str(binding_no_vnq_efa.date()),
                  risky_availability_ladder={t: str(d.date()) for t, d in ladder},
                  reduced_universe_first_ge={str(k): (str(v.date()) if v else None)
                                             for k, v in first_ge.items()},
                  live_inception=LIVE_INCEPTION, crises=CRISES),
        partA_prodproxy=dict(curve_start=str(cpmA.index[0].date()),
                             n_months=n_months, riskon_months=riskonA,
                             mooex_real_fallback=list(fbA),
                             selection_frequency=sel, crisis_dd=tableA),
        partB_extension=dict(curve_start=str(cpmB.index[0].date()),
                             extended_ladder={t: str(d.date()) for t, d in ladderE},
                             ext_first_ge={str(k): (str(v.date()) if v else None)
                                           for k, v in first_geE.items()},
                             mooex_real_fallback=list(fbB),
                             gspc_first=str(gspc.index.min().date()) if len(gspc) else None,
                             veiex_first=str(veiex.index.min().date()) if len(veiex) else None,
                             crisis_dd=tableB,
                             caveat="CPM-LIKE not production: SPY/^GSPC US-equity "
                                    "substitute, EEM<-VEIEX, SPHQ<-^GSPC crude quality; "
                                    "fewer assets pre-1996; no real opens pre-ETF."),
        proxy_coverage=cov, ltcm_reliability=ltcm_reliability,
    )
    Path(__file__).with_suffix(".json").write_text(json.dumps(out, indent=2, default=float))

    print("\n" + "=" * 86)
    print("LTCM RELIABILITY")
    print("=" * 86)
    print(f"  [A] prod-proxy : curve {ltcm_reliability['prodproxy']['curve_start']}  "
          f"peak {ltcm_reliability['prodproxy']['peak']}  "
          f"lead-in {ltcm_reliability['prodproxy']['leadin_days']}d  "
          f"depth {ltcm_reliability['prodproxy']['depth']*100:.2f}%")
    print(f"  [B] extension  : curve {ltcm_reliability['extension']['curve_start']}  "
          f"peak {ltcm_reliability['extension']['peak']}  "
          f"lead-in {ltcm_reliability['extension']['leadin_days']}d  "
          f"depth {ltcm_reliability['extension']['depth']*100:.2f}%")
    print("\nDONE ->", Path(__file__).with_suffix(".json").name)


if __name__ == "__main__":
    main()
