"""Throwaway research (SCOPED, read-only; writes research/ only).

QUESTION (user): the bond-buffer exploration reported a de-lever-only vol-target
CAP overlay (never levers up) that trimmed MaxDD to -8.10% / Calmar 1.051 -- but
that number was measured on the dyn-safe-40% BUFFERED base, and only partial
metrics were reported. This harness measures the FULL performance profile of the
cap-only overlay applied DIRECTLY to the both-252 CPM (no bond buffer), to decide
whether it is worth adopting as a pure DEFENSIVE overlay (adds NO leverage,
aligns with CPM's capital-preservation thesis).

DELIVERABLES:
  1. Reproduce both-252 CPM anchor (Sharpe 1.1658 / MaxDD -12.97% / Calmar 1.0137).
  2. Threshold sweep -> response surface (plateau vs spike / overfit smell).
  3. Full metrics best/representative cap vs CPM.
  4. Per-crisis: GFC 2008 / COVID 2020 / 2022.
  5. Turnover of the overlay (and explicit cost charged).
  6. Paired stationary block bootstrap (B=5000, block~21) on marginal (cap-CPM)
     for Sharpe AND Calmar AND Martin -- CI excludes/includes 0?
  7. Skepticism: per-episode removal -- is the DD trim broad-based or 1 episode?

VOL-CAP MECHANISM (documented exactly):
  - Vol estimate = REALIZED TRAILING vol of the strategy's own post-cost daily
    return series over `lookback` days (annualized), NOT ex-ante weights x cov.
  - POINT-IN-TIME: exposure on day t uses the trailing vol computed THROUGH day
    t-1 (rolling std then .shift(1)) -> no look-ahead.
  - exposure_t = clip(target_vol / realized_vol_{t-1}, upper=1.0). CAP = de-lever
    only; exposure never exceeds 1.0 (never levers up in calm).
  - De-levered notional (1 - exposure_t) earns CASH (SHV) -> excess exposure goes
    to cash, the mechanism the user described.
  - Overlay turnover cost = |exposure_t - exposure_{t-1}| * COST_BPS_PER_SIDE,
    charged daily ON TOP of the monthly CPM rebalance cost already baked into r.

Reuses production engine (cpm_live, pinned CORR_LOOKBACK_DAYS=252 via the bond-
buffer harness import) + the memo mooex T+1 MOO exact accounting.
"""
import sys, math, json
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

# Importing the bond-buffer harness pins cpm_live.CORR_LOOKBACK_DAYS=252
# in-process and wires the mooex T+1 accounting (build_data/run_wf/cpm_wf/met).
import cpm_bond_buffer_leverage_harness as BB
from cpm_live import perf_metrics, COST_BPS_PER_SIDE

CLEAN_START = BB.CLEAN_START      # 2008-05-30
EXT_START = BB.EXT_START
SEED = 12345
B = 5000
BLOCK = 21
LOOKBACK = 21

CRISES = {
    "GFC_2008": ("2008-05-30", "2009-06-30"),
    "COVID_2020": ("2020-02-01", "2020-06-30"),
    "Bear_2022": ("2022-01-01", "2022-12-31"),
    # CPM's BINDING MaxDD (-12.97%) troughs 2025-04-08 (tariff selloff), not the
    # classic crises -- included so per-crisis/episode-removal cover the real DD.
    "Tariff_2025": ("2025-01-01", "2025-06-30"),
}


# ---------------------------------------------------------------------------
# vol-cap overlay
# ---------------------------------------------------------------------------
def volcap_overlay(r, cash, target_vol, lookback=LOOKBACK, cost_bps=COST_BPS_PER_SIDE):
    """De-lever-only vol-target cap applied to a post-cost daily return series.

    Returns (overlay_return_series, exposure_series). See module docstring for
    the exact (point-in-time, never-lever) mechanism."""
    rv = r.rolling(lookback).std(ddof=0) * np.sqrt(252)
    expo = (target_vol / rv).clip(upper=1.0).shift(1).fillna(1.0)
    cash_a = cash.reindex(r.index).fillna(0.0)
    gross = expo * r + (1.0 - expo) * cash_a
    turn = expo.diff().abs().fillna(0.0)
    net = gross - turn * (cost_bps / 10000.0)
    return net, expo


def annual_turnover(expo):
    yrs = (expo.index[-1] - expo.index[0]).days / 365.25
    return float(expo.diff().abs().sum() / yrs) if yrs > 0 else float("nan")


# ---------------------------------------------------------------------------
# metric helpers
# ---------------------------------------------------------------------------
def met(daily, cash):
    m = perf_metrics(daily, cash)
    return {"sharpe": m.get("sharpe"), "cagr": m.get("cagr"), "vol": m.get("vol"),
            "maxdd": m.get("max_drawdown"), "calmar": m.get("calmar"),
            "martin": m.get("martin"), "ulcer": m.get("ulcer")}


def metrics_arr(r):
    """Sharpe/Calmar/Martin/MaxDD/CAGR/vol on a raw daily-return numpy array."""
    r = np.asarray(r, dtype=float)
    n = len(r)
    if n < 2:
        return dict(sharpe=np.nan, calmar=np.nan, martin=np.nan, maxdd=np.nan,
                    cagr=np.nan, vol=np.nan)
    eq = np.cumprod(1.0 + r)
    yrs = n / 252.0
    cagr = eq[-1] ** (1.0 / yrs) - 1.0 if eq[-1] > 0 else -1.0
    vol = r.std(ddof=0) * math.sqrt(252)
    sharpe = (r.mean() * 252) / vol if vol > 0 else np.nan
    rm = np.maximum.accumulate(eq)
    dd = eq / rm - 1.0
    mdd = dd.min()
    ulcer = math.sqrt(np.mean(dd ** 2))
    calmar = cagr / abs(mdd) if mdd != 0 else np.nan
    martin = cagr / ulcer if ulcer > 0 else np.nan
    return dict(sharpe=sharpe, calmar=calmar, martin=martin, maxdd=mdd,
                cagr=cagr, vol=vol)


def maxdd_arr(r):
    r = np.asarray(r, dtype=float)
    eq = np.cumprod(1.0 + r)
    rm = np.maximum.accumulate(eq)
    return float((eq / rm - 1.0).min())


def paired_bootstrap_multi(a_s, b_s, metrics=("sharpe", "calmar", "martin"),
                           block=BLOCK, B=B, seed=SEED):
    """Stationary-block paired bootstrap of (metric(a) - metric(b)) for several
    metrics at once. Resamples a common block index for both legs (paired)."""
    common = a_s.index.intersection(b_s.index)
    a = a_s.reindex(common).fillna(0.0).values
    b = b_s.reindex(common).fillna(0.0).values
    n = len(a)
    pt = {m: metrics_arr(a)[m] - metrics_arr(b)[m] for m in metrics}
    if n < block * 3:
        return {m: {"point": pt[m], "lo": np.nan, "hi": np.nan, "includes_zero": True}
                for m in metrics}
    rng = np.random.default_rng(seed)
    pool = np.arange(0, n - block + 1)
    p = 1.0 / block  # stationary bootstrap: geometric block lengths, mean=block
    draws = {m: np.empty(B) for m in metrics}
    for i in range(B):
        idx = []
        while len(idx) < n:
            start = rng.integers(0, n)
            L = rng.geometric(p)
            seg = (np.arange(start, start + L) % n)
            idx.extend(seg.tolist())
        idx = np.array(idx[:n])
        ma, mb = metrics_arr(a[idx]), metrics_arr(b[idx])
        for m in metrics:
            draws[m][i] = ma[m] - mb[m]
    res = {}
    for m in metrics:
        lo, hi = np.nanpercentile(draws[m], [2.5, 97.5])
        res[m] = {"point": float(pt[m]), "lo": float(lo), "hi": float(hi),
                  "includes_zero": bool(lo <= 0.0 <= hi)}
    return res


# ---------------------------------------------------------------------------
def main():
    panel, intraday, overnight, end = BB.build_data()
    cash = panel["SHV"].ffill().pct_change().dropna()
    from cpm_live import RISKY_UNIVERSE, SAFE_POOL, CANARY_ASSETS, DEFAULT_CASH
    bm_cols = sorted(set(RISKY_UNIVERSE + SAFE_POOL + CANARY_ASSETS +
                         [DEFAULT_CASH, "SPY", "IEF", "TLT", "BND"]) & set(panel.columns))
    close = panel[bm_cols]
    daily = close.ffill().pct_change()
    print(f"Panel {panel.index[0].date()} -> {end.date()} ({len(panel)} rows)")
    print(f"cost={COST_BPS_PER_SIDE}bps/side  lookback={LOOKBACK}d  B={B} block={BLOCK}\n")

    def clean(s):
        return s.loc[(s.index >= CLEAN_START) & (s.index <= end)]

    out = {"meta": {"cost_bps": COST_BPS_PER_SIDE, "lookback": LOOKBACK,
                    "B": B, "block": BLOCK, "clean_start": str(CLEAN_START.date()),
                    "end": str(end.date()),
                    "mechanism": "realized trailing vol of strategy returns, "
                                 "shift(1) point-in-time, exposure=clip(target/rv,<=1), "
                                 "de-levered notional earns cash, daily overlay cost charged"},
           "anchor": {}, "sweep": {}, "best": {}, "per_crisis": {},
           "turnover": {}, "bootstrap": {}, "episode_removal": {}}

    # ---- anchor (gate) ----
    cpm = BB.run_wf(close, daily, intraday, overnight, EXT_START, end, BB.cpm_wf(close))
    cpm_c = clean(cpm)
    mc = met(cpm_c, cash)
    out["anchor"]["CPM_both252"] = mc
    print("=== ANCHOR (CLEAN 18y, mooex both-252) ===")
    print(f"  CPM Sharpe={mc['sharpe']:.4f} MaxDD={mc['maxdd']*100:.2f}% "
          f"Calmar={mc['calmar']:.4f} Martin={mc['martin']:.4f} Vol={mc['vol']*100:.2f}% "
          f"CAGR={mc['cagr']*100:.2f}%")
    print("  (target both-252: 1.1658 / -12.97% / 1.0137)\n")

    cpm_vol = mc["vol"]

    # ---- sanity: reproduce prior -8.10% on dyn-safe-40% buffered base ----
    base_s = clean(BB.run_wf(close, daily, intraday, overnight, CLEAN_START, end,
                             BB.diversifier_dyn_wf(close, 0.4)))
    # prior construction (expo*r, no cash credit, no overlay cost) at target=CPM vol
    rv = base_s.rolling(21).std(ddof=0) * np.sqrt(252)
    expo_prior = (cpm_vol / rv).clip(upper=1.0).shift(1).fillna(1.0)
    prior_cap = expo_prior * base_s
    mprior = met(prior_cap, cash)
    out["anchor"]["prior_volcap_on_dynsafe40"] = mprior
    print(f"  SANITY (prior construction, cap on dyn-safe-40% base, target={cpm_vol*100:.2f}%): "
          f"MaxDD={mprior['maxdd']*100:.2f}% Calmar={mprior['calmar']:.4f} "
          f"(prior reported -8.10% / 1.051)\n")

    # ---- (2) THRESHOLD SWEEP on CPM ----
    print("=== (2) THRESHOLD SWEEP: vol-cap on CPM (clean 18y) ===")
    print(f"  {'target':>7} {'Sharpe':>7} {'Vol':>6} {'MaxDD':>8} {'Calmar':>7} "
          f"{'Martin':>7} {'CAGR':>6} {'turn/yr':>7}")
    targets = [0.07, 0.08, 0.09, 0.10, 0.11, 0.12, 0.13, 0.14, 0.15]
    for tv in targets:
        net, expo = volcap_overlay(cpm_c, cash, tv)
        m = met(net, cash)
        m["turnover"] = annual_turnover(expo)
        out["sweep"][f"target_{int(tv*100)}"] = m
        print(f"  {tv*100:5.0f}%  {m['sharpe']:7.4f} {m['vol']*100:5.1f}% "
              f"{m['maxdd']*100:7.2f}% {m['calmar']:7.4f} {m['martin']:7.4f} "
              f"{m['cagr']*100:5.2f}% {m['turnover']:6.1f}x")
    print(f"  {'CPM(none)':>7} {mc['sharpe']:7.4f} {mc['vol']*100:5.1f}% "
          f"{mc['maxdd']*100:7.2f}% {mc['calmar']:7.4f} {mc['martin']:7.4f} "
          f"{mc['cagr']*100:5.2f}%   0.0x\n")

    # robustness: lookback sensitivity at representative target=11% (=CPM vol)
    print("  lookback sensitivity @ target=11%:")
    for lb in [10, 21, 42, 63]:
        net, expo = volcap_overlay(cpm_c, cash, 0.11, lookback=lb)
        m = met(net, cash)
        out["sweep"][f"target_11_lb{lb}"] = {**m, "turnover": annual_turnover(expo)}
        print(f"    lb={lb:>2}d: MaxDD={m['maxdd']*100:6.2f}% Calmar={m['calmar']:.4f} "
              f"Sharpe={m['sharpe']:.4f} turn={annual_turnover(expo):.1f}x")
    print()

    # ---- (3) BEST/REPRESENTATIVE: pick target=CPM vol (11%) as decision point ----
    rep_target = round(cpm_vol, 4)
    net_rep, expo_rep = volcap_overlay(cpm_c, cash, rep_target)
    m_rep = met(net_rep, cash)
    m_rep["turnover"] = annual_turnover(expo_rep)
    out["best"]["target"] = rep_target
    out["best"]["cap"] = m_rep
    out["best"]["cpm"] = mc
    print(f"=== (3) REPRESENTATIVE CAP (target={rep_target*100:.2f}% = CPM vol) vs CPM ===")
    for label, m in [("CPM both-252", mc), ("CPM + vol-cap", m_rep)]:
        print(f"  {label:>15}: Sharpe={m['sharpe']:.4f} CAGR={m['cagr']*100:5.2f}% "
              f"Vol={m['vol']*100:5.2f}% MaxDD={m['maxdd']*100:7.2f}% "
              f"Calmar={m['calmar']:.4f} Martin={m['martin']:.4f} Ulcer={m['ulcer']*100:.2f}%")
    print(f"  CAGR cost: {(m_rep['cagr']-mc['cagr'])*100:+.2f}pp   "
          f"MaxDD change: {(m_rep['maxdd']-mc['maxdd'])*100:+.2f}pp   "
          f"overlay turnover: {m_rep['turnover']:.1f}x/yr\n")

    # ---- (4) PER-CRISIS ----
    print("=== (4) PER-CRISIS (CPM vs CPM+cap, target=11%) ===")
    print(f"  {'episode':>12} {'CPM_ret':>8} {'cap_ret':>8} {'CPM_dd':>8} {'cap_dd':>8}")
    for name, (s, e) in CRISES.items():
        s, e = pd.Timestamp(s), pd.Timestamp(e)
        cpm_w = cpm_c.loc[(cpm_c.index >= s) & (cpm_c.index <= e)]
        cap_w = net_rep.loc[(net_rep.index >= s) & (net_rep.index <= e)]
        cpm_ret = float((1 + cpm_w).prod() - 1)
        cap_ret = float((1 + cap_w).prod() - 1)
        cpm_dd = maxdd_arr(cpm_w.values)
        cap_dd = maxdd_arr(cap_w.values)
        out["per_crisis"][name] = {"cpm_ret": cpm_ret, "cap_ret": cap_ret,
                                   "cpm_maxdd": cpm_dd, "cap_maxdd": cap_dd}
        print(f"  {name:>12} {cpm_ret*100:7.2f}% {cap_ret*100:7.2f}% "
              f"{cpm_dd*100:7.2f}% {cap_dd*100:7.2f}%")
    print("  (cap_ret < CPM_ret in recovery = upside bleed; cap_dd > CPM_dd = better)\n")

    # ---- (5) TURNOVER summary ----
    out["turnover"]["overlay_annual"] = m_rep["turnover"]
    out["turnover"]["overlay_cost_bps_per_turn"] = COST_BPS_PER_SIDE
    # gross-of-overlay-cost vs net to isolate cost drag
    gross_net, _ = volcap_overlay(cpm_c, cash, rep_target, cost_bps=0.0)
    m_gross = met(gross_net, cash)
    out["turnover"]["cap_cagr_gross"] = m_gross["cagr"]
    out["turnover"]["cap_cagr_net"] = m_rep["cagr"]
    out["turnover"]["overlay_cost_drag_pp"] = (m_gross["cagr"] - m_rep["cagr"]) * 100
    print("=== (5) TURNOVER / COST ===")
    print(f"  overlay annual turnover: {m_rep['turnover']:.1f}x/yr  "
          f"(one-sided |dExpo| sum / yr)")
    print(f"  overlay cost drag: {(m_gross['cagr']-m_rep['cagr'])*100:.3f}pp CAGR "
          f"(gross {m_gross['cagr']*100:.2f}% -> net {m_rep['cagr']*100:.2f}%)\n")

    # ---- (6) BOOTSTRAP marginal (cap - CPM) ----
    print(f"=== (6) PAIRED STATIONARY BLOCK BOOTSTRAP (B={B}, block~{BLOCK}) ===")
    print("  marginal = (CPM+cap) - CPM, clean window")
    bs = paired_bootstrap_multi(net_rep, cpm_c, metrics=("sharpe", "calmar", "martin"))
    out["bootstrap"] = bs
    for m in ("sharpe", "calmar", "martin"):
        d = bs[m]
        print(f"  d{m:>7}: {d['point']:+.4f}  CI[{d['lo']:+.4f}, {d['hi']:+.4f}]  "
              f"{'(includes 0)' if d['includes_zero'] else '(EXCLUDES 0 -> significant)'}")
    print()

    # ---- (7) EPISODE-REMOVAL skepticism on MaxDD ----
    print("=== (7) EPISODE-REMOVAL: is the DD trim broad-based? ===")
    full_cpm_dd = maxdd_arr(cpm_c.values)
    full_cap_dd = maxdd_arr(net_rep.values)
    out["episode_removal"]["full"] = {"cpm_maxdd": full_cpm_dd, "cap_maxdd": full_cap_dd,
                                      "improvement_pp": (full_cap_dd - full_cpm_dd) * 100}
    print(f"  FULL: CPM {full_cpm_dd*100:.2f}% -> cap {full_cap_dd*100:.2f}% "
          f"({(full_cap_dd-full_cpm_dd)*100:+.2f}pp)")
    for name, (s, e) in CRISES.items():
        s, e = pd.Timestamp(s), pd.Timestamp(e)
        mask = ~((cpm_c.index >= s) & (cpm_c.index <= e))
        cpm_x = cpm_c.loc[mask]
        cap_x = net_rep.loc[mask]
        cpm_dd = maxdd_arr(cpm_x.values)
        cap_dd = maxdd_arr(cap_x.values)
        out["episode_removal"][f"ex_{name}"] = {"cpm_maxdd": cpm_dd, "cap_maxdd": cap_dd,
                                                "improvement_pp": (cap_dd - cpm_dd) * 100}
        print(f"  ex-{name:>10}: CPM {cpm_dd*100:7.2f}% -> cap {cap_dd*100:7.2f}% "
              f"({(cap_dd-cpm_dd)*100:+.2f}pp)")
    print("  (if improvement collapses when one episode removed -> driven by that episode)\n")

    Path(__file__).with_suffix(".json").write_text(json.dumps(out, indent=2, default=float))
    print(f"Wrote {Path(__file__).with_suffix('.json').name}")


if __name__ == "__main__":
    main()
